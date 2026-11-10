from __future__ import annotations

import asyncio
import dataclasses
import errno
import os
import stat
import threading
from pathlib import Path

import pytest

from integrations.workbench_action_mcp import patch_port
from integrations.workbench_action_mcp.action_artifacts import (
    ActionHostBinding,
    artifact_name,
)
from integrations.workbench_action_mcp.patch_port import ProjectActionRefused
from tests.workbench_action_mcp.test_patch_port import Harness, _sha


def _action_id(harness: Harness, action_ref: str) -> str:
    prepared = harness.codec.decode_evidence(action_ref, now_ms=harness.clock)
    return prepared.action_id


def test_v1_schema_and_nested_path_fail_closed(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    harness = Harness(tmp_path, allowed_paths=("nested/file.txt", "leaf.txt"))
    try:
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(
                harness.prepare(
                    harness.caller,
                    {
                        "project_ref": harness.project_ref,
                        "relative_path": "nested/file.txt",
                        "mode": "CREATE",
                        "new_text": "x\n",
                    },
                )
            )
        assert caught.value.code == "ACTION_INVALID"
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.commit(harness.caller, "not-a-v2-token"))
        assert caught.value.code == "ACTION_INVALID"
    finally:
        harness.close()


def test_concurrent_same_action_publishes_once(tmp_path: Path) -> None:
    target = tmp_path / "once.txt"
    harness = Harness(tmp_path, allowed_paths=("once.txt",), threaded=True)
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "once.txt",
                    "mode": "CREATE",
                    "new_text": "only-once\n",
                },
            )
        )

        async def both() -> list[object]:
            return await asyncio.gather(
                harness.commit(harness.caller, prepared["action_ref"]),
                harness.commit(harness.caller, prepared["action_ref"]),
                return_exceptions=True,
            )

        results = asyncio.run(both())
        states = []
        for result in results:
            if isinstance(result, ProjectActionRefused):
                assert result.code == "ACTION_UNAVAILABLE"
                continue
            assert isinstance(result, dict)
            states.append(result["effect_state"])
        assert "APPLIED" in states
        assert all(state in {"APPLIED", "EFFECT_UNKNOWN"} for state in states)
        assert target.read_text() == "only-once\n"
        assert target.stat().st_nlink == 1
    finally:
        harness.close()


def test_distinct_actions_same_preimage_are_serialized_or_refused(tmp_path: Path) -> None:
    target = tmp_path / "shared.txt"
    original = b"shared\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("shared.txt",), threaded=True)
    try:
        first = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "shared.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "shared",
                    "new_text": "alpha",
                },
            )
        )
        second = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "shared.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "shared",
                    "new_text": "beta",
                },
            )
        )

        async def both() -> list[object]:
            return await asyncio.gather(
                harness.commit(harness.caller, first["action_ref"]),
                harness.commit(harness.caller, second["action_ref"]),
                return_exceptions=True,
            )

        results = asyncio.run(both())
        applied = 0
        for result in results:
            if isinstance(result, ProjectActionRefused):
                assert result.code in {"ACTION_UNAVAILABLE", "ACTION_PREIMAGE_MISMATCH", "ACTION_SOURCE_CHANGED"}
                continue
            assert isinstance(result, dict)
            if result["effect_state"] == "APPLIED":
                applied += 1
            else:
                assert result["effect_state"] == "EFFECT_UNKNOWN"
        assert applied == 1
        assert target.read_text() in {"alpha\n", "beta\n"}
    finally:
        harness.close()


def test_reply_loss_while_physical_write_is_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "pending.txt"
    original = b"before\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("pending.txt",), threaded=True)
    hold = threading.Event()
    at_gate = threading.Event()

    def gate(_prepared) -> None:
        at_gate.set()
        if not hold.wait(timeout=5):
            raise TimeoutError("publication hold was not released")

    monkeypatch.setattr(patch_port, "_publication_gate", gate)
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "pending.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "before",
                    "new_text": "after",
                },
            )
        )

        async def exercise() -> tuple[dict[str, object], dict[str, object]]:
            task = asyncio.create_task(
                harness.commit(harness.caller, prepared["action_ref"])
            )
            try:
                await asyncio.get_running_loop().run_in_executor(None, lambda: at_gate.wait(5))
                assert at_gate.is_set()
                lost = await harness.reconcile(harness.caller, prepared["action_ref"])
                hold.set()
                committed = await task
                return lost, committed
            finally:
                # Release and drain before asyncio.run shuts down its executor,
                # including when the pending-read assertion itself fails.
                hold.set()
                await asyncio.gather(task, return_exceptions=True)

        lost, committed = asyncio.run(exercise())
        assert lost["effect_state"] == "EFFECT_UNKNOWN"
        assert committed["effect_state"] == "APPLIED"
        assert target.read_text() == "after\n"
    finally:
        hold.set()
        harness.close()


def test_expired_at_worker_and_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "deadline.txt"
    original = b"old\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("deadline.txt",))
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "deadline.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "old",
                    "new_text": "new",
                },
            )
        )
        harness.clock = prepared["expires_at_ms"] + 1
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert caught.value.code == "ACTION_EXPIRED"
        assert target.read_bytes() == original
        assert not any(harness.store_path.glob("*.claim"))

        harness.clock = prepared["expires_at_ms"] - 5_000
        second = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "deadline.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "old",
                    "new_text": "gate",
                },
            )
        )

        def expire(_prepared) -> None:
            harness.clock = second["expires_at_ms"] + 1

        monkeypatch.setattr(patch_port, "_publication_gate", expire)
        expired = asyncio.run(harness.commit(harness.caller, second["action_ref"]))
        assert expired["effect_state"] == "NOT_APPLIED"
        assert target.read_bytes() == original
    finally:
        harness.close()


def test_expired_evidence_read_under_live_authority(tmp_path: Path) -> None:
    target = tmp_path / "evidence.txt"
    original = b"old\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("evidence.txt",))
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "evidence.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "old",
                    "new_text": "new",
                },
            )
        )
        applied = asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert applied["effect_state"] == "APPLIED"
        harness.clock = prepared["expires_at_ms"] + 1
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert caught.value.code == "ACTION_EXPIRED"
        reconciled = asyncio.run(
            harness.reconcile(harness.caller, prepared["action_ref"])
        )
        assert reconciled["effect_state"] == "APPLIED"
        assert target.read_text() == "new\n"
    finally:
        harness.close()


def test_deleted_create_and_restored_replace_do_not_replay_after_restart(tmp_path: Path) -> None:
    created = tmp_path / "created.txt"
    replaced = tmp_path / "replaced.txt"
    original = b"keep\n"
    replaced.write_bytes(original)
    first = Harness(tmp_path, allowed_paths=("created.txt", "replaced.txt"))
    try:
        create_ref = asyncio.run(
            first.prepare(
                first.caller,
                {
                    "project_ref": first.project_ref,
                    "relative_path": "created.txt",
                    "mode": "CREATE",
                    "new_text": "made\n",
                },
            )
        )
        replace_ref = asyncio.run(
            first.prepare(
                first.caller,
                {
                    "project_ref": first.project_ref,
                    "relative_path": "replaced.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "keep",
                    "new_text": "changed",
                },
            )
        )
        assert asyncio.run(first.commit(first.caller, create_ref["action_ref"]))["effect_state"] == "APPLIED"
        assert asyncio.run(first.commit(first.caller, replace_ref["action_ref"]))["effect_state"] == "APPLIED"
        created.unlink()
        replaced.write_bytes(original)
        store_dir = first.store_path
    finally:
        first.close()

    restarted = Harness(
        tmp_path,
        allowed_paths=("created.txt", "replaced.txt"),
        store_dir=store_dir,
    )
    try:
        create_replay = asyncio.run(
            restarted.commit(restarted.caller, create_ref["action_ref"])
        )
        replace_replay = asyncio.run(
            restarted.commit(restarted.caller, replace_ref["action_ref"])
        )
        assert create_replay["effect_state"] == "APPLIED"
        assert replace_replay["effect_state"] == "APPLIED"
        assert not created.exists()
        assert replaced.read_bytes() == original
        assert asyncio.run(
            restarted.reconcile(restarted.caller, create_ref["action_ref"])
        )["effect_state"] == "APPLIED"
    finally:
        restarted.close()


def test_retained_store_replacement_and_corruption_are_unknown(tmp_path: Path) -> None:
    target = tmp_path / "store.txt"
    original = b"old\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("store.txt",))
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "store.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "old",
                    "new_text": "new",
                },
            )
        )
        assert asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))["effect_state"] == "APPLIED"
        action_id = _action_id(harness, prepared["action_ref"])
        (harness.store_path / artifact_name(action_id, "result")).write_text("{bad")
        corrupted = asyncio.run(harness.reconcile(harness.caller, prepared["action_ref"]))
        assert corrupted["effect_state"] == "EFFECT_UNKNOWN"
    finally:
        harness.close()

    replacement = Harness(
        tmp_path,
        allowed_paths=("store.txt",),
        store_dir=tmp_path / "replacement-store",
    )
    try:
        observed = asyncio.run(
            replacement.reconcile(replacement.caller, prepared["action_ref"])
        )
        assert observed["effect_state"] == "EFFECT_UNKNOWN"
    finally:
        replacement.close()


def test_same_byte_inode_swap_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "swap.txt"
    original = b"same-bytes\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("swap.txt",))
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "swap.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "same-bytes",
                    "new_text": "changed",
                },
            )
        )
        inode = target.stat().st_ino
        replacement = tmp_path / "swap-replacement.txt"
        replacement.write_bytes(original)
        assert replacement.stat().st_ino != inode
        os.replace(replacement, target)
        assert target.stat().st_ino != inode
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert caught.value.code == "ACTION_SOURCE_CHANGED"
        assert target.read_bytes() == original
    finally:
        harness.close()


def test_wrong_host_boot_channel_and_project_refuse(tmp_path: Path) -> None:
    target = tmp_path / "bound.txt"
    original = b"old\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("bound.txt",))
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "bound.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "old",
                    "new_text": "new",
                },
            )
        )
        from integrations.workbench_action_mcp.contracts import ProjectActionBinding
        from integrations.workbench_action_mcp.patch_port import create_text_patch_port

        def resolve_ok(caller, project_ref):
            if caller != harness.caller or project_ref != harness.project_ref:
                return None
            return ProjectActionBinding(caller, project_ref, harness.scope)

        async def run_io(operation):
            return operation()

        _, wrong_host_commit, _ = create_text_patch_port(
            resolve_binding=resolve_ok,
            clock_ms=lambda: harness.clock,
            run_io=run_io,
            token_codec=harness.codec,
            artifact_store=harness.store,
            host=ActionHostBinding(host_id="d" * 64, boot_session_id=harness.host.boot_session_id),
            action_ttl_ms=60_000,
        )
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(wrong_host_commit(harness.caller, prepared["action_ref"]))
        assert caught.value.code == "ACTION_BINDING_CHANGED"

        _, wrong_boot_commit, wrong_boot_reconcile = create_text_patch_port(
            resolve_binding=resolve_ok,
            clock_ms=lambda: harness.clock,
            run_io=run_io,
            token_codec=harness.codec,
            artifact_store=harness.store,
            host=ActionHostBinding(host_id=harness.host.host_id, boot_session_id="boot-other"),
            action_ttl_ms=60_000,
        )
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(wrong_boot_commit(harness.caller, prepared["action_ref"]))
        assert caught.value.code == "ACTION_BINDING_CHANGED"
        observed = asyncio.run(
            wrong_boot_reconcile(harness.caller, prepared["action_ref"])
        )
        assert observed["effect_state"] == "EFFECT_UNKNOWN"

        other_caller = dataclasses.replace(harness.caller, client_ref="other-channel")
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.commit(other_caller, prepared["action_ref"]))
        assert caught.value.code == "ACTION_BINDING_CHANGED"

        def resolve_other_project(caller, project_ref):
            return ProjectActionBinding(caller, "project:other", harness.scope)

        _, wrong_project_commit, _ = create_text_patch_port(
            resolve_binding=resolve_other_project,
            clock_ms=lambda: harness.clock,
            run_io=run_io,
            token_codec=harness.codec,
            artifact_store=harness.store,
            host=harness.host,
            action_ttl_ms=60_000,
        )
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(wrong_project_commit(harness.caller, prepared["action_ref"]))
        # The token still names project:alpha; a changed live project binding
        # must not admit mutation.
        assert caught.value.code == "ACTION_BINDING_CHANGED"
        assert target.read_bytes() == original
    finally:
        harness.close()


def test_foreign_temp_collision_is_not_unlinked(tmp_path: Path) -> None:
    target = tmp_path / "temp.txt"
    original = b"old\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("temp.txt",))
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "temp.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "old",
                    "new_text": "new",
                },
            )
        )
        action_id = _action_id(harness, prepared["action_ref"])
        foreign = tmp_path / f".mmx-workbench-action-{action_id}.tmp"
        foreign.write_text("foreign-temp\n")
        inode = foreign.stat().st_ino
        result = asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert result["effect_state"] == "EFFECT_UNKNOWN"
        assert foreign.exists()
        assert foreign.read_text() == "foreign-temp\n"
        assert foreign.stat().st_ino == inode
        assert target.read_bytes() == original
    finally:
        harness.close()


def test_foreign_temp_swap_is_not_published(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "swaptemp.txt"
    original = b"old\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("swaptemp.txt",))
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "swaptemp.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "old",
                    "new_text": "new",
                },
            )
        )
        action_id = _action_id(harness, prepared["action_ref"])
        temp_name = f".mmx-workbench-action-{action_id}.tmp"

        def swap(_prepared) -> None:
            path = tmp_path / temp_name
            if path.exists():
                path.unlink()
            path.write_text("injected\n")

        monkeypatch.setattr(patch_port, "_publication_gate", swap)
        result = asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert result["effect_state"] == "EFFECT_UNKNOWN"
        assert target.read_bytes() == original
        leftover = tmp_path / temp_name
        if leftover.exists():
            assert leftover.read_text() == "injected\n"
    finally:
        harness.close()


def test_directory_fsync_uncertainty_is_not_applied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "fsync.txt"
    original = b"old\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("fsync.txt",))
    project_ino = os.fstat(harness.root_fd).st_ino
    real_fsync = os.fsync

    def injected(fd: int) -> None:
        try:
            info = os.fstat(fd)
        except OSError:
            return real_fsync(fd)
        if stat.S_ISDIR(info.st_mode) and info.st_ino == project_ino:
            raise OSError(errno.EIO, "injected directory fsync failure")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", injected)
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "fsync.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "old",
                    "new_text": "new",
                },
            )
        )
        result = asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert result["effect_state"] == "EFFECT_UNKNOWN"
        reconciled = asyncio.run(
            harness.reconcile(harness.caller, prepared["action_ref"])
        )
        assert reconciled["effect_state"] == "EFFECT_UNKNOWN"
    finally:
        harness.close()


@pytest.mark.parametrize("damage", ["corrupt_orphan", "valid_orphan", "corrupt_claim"])
def test_port_cannot_claim_unresolved_existing_evidence(tmp_path, damage):
    target = tmp_path / "leaf.txt"
    harness = Harness(tmp_path, allowed_paths=("leaf.txt",))
    try:
        prepared = asyncio.run(harness.prepare(harness.caller, {
            "project_ref": harness.project_ref, "relative_path": "leaf.txt",
            "mode": "CREATE", "new_text": "once\n",
        }))
        action_id = _action_id(harness, prepared["action_ref"])
        claim_path = harness.store_path / artifact_name(action_id, "claim")
        result_path = harness.store_path / artifact_name(action_id, "result")
        if damage == "corrupt_orphan":
            result_path.write_text("{")
        else:
            assert asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))["effect_state"] == "APPLIED"
            target.unlink()
            if damage == "valid_orphan":
                claim_path.unlink()
            else:
                claim_path.write_text("{")
        before = result_path.read_bytes()
        reply = asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert reply["effect_state"] == "EFFECT_UNKNOWN"
        assert not target.exists()
        assert result_path.read_bytes() == before
        if damage.endswith("orphan"):
            assert not claim_path.exists()
    finally:
        harness.close()


@pytest.mark.parametrize("stage", ["before_claim", "after_claim", "after_publication"])
@pytest.mark.parametrize("reader", ["leaf", "parent"])
def test_project_reader_close_uncertainty_survives_at_every_boundary(tmp_path, monkeypatch, stage, reader):
    from integrations.workbench_action_mcp.action_artifacts import ActionArtifactUncertain

    target = tmp_path / "leaf.txt"
    target.write_text("before\n")
    harness = Harness(tmp_path, allowed_paths=("leaf.txt",))
    real_close = os.close
    fired = False
    try:
        prepared = asyncio.run(harness.prepare(harness.caller, {
            "project_ref": harness.project_ref, "relative_path": "leaf.txt", "mode": "REPLACE",
            "expected_sha256": _sha(b"before\n"), "old_text": "before", "new_text": "after",
        }))
        action_id = _action_id(harness, prepared["action_ref"])
        claim_path = harness.store_path / artifact_name(action_id, "claim")

        def close(fd):
            nonlocal fired
            opened = os.fstat(fd)
            appropriate = (opened.st_ino == target.stat().st_ino if reader == "leaf" else
                           opened.st_ino == harness.scope.root_inode and fd != harness.root_fd)
            claimed = claim_path.exists()
            published = target.read_text() == "after\n"
            matches = {"before_claim": not claimed,
                       "after_claim": claimed and not published,
                       "after_publication": published}[stage]
            real_close(fd)
            if appropriate and matches and not fired:
                fired = True
                raise OSError("reader close acknowledgement uncertain")

        monkeypatch.setattr(patch_port.os, "close", close)
        if stage == "before_claim":
            with pytest.raises(ProjectActionRefused):
                asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
            assert not claim_path.exists()
        else:
            reply = asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
            assert reply["effect_state"] == "EFFECT_UNKNOWN"
            assert reply["cleanup_state"] == "UNCERTAIN"
        assert fired and harness.store.cleanup_uncertain
        assert target.read_text() == ("after\n" if stage == "after_publication" else "before\n")
        monkeypatch.setattr(patch_port.os, "close", real_close)
        with pytest.raises(ActionArtifactUncertain):
            harness.store.raise_if_cleanup_uncertain()
        with pytest.raises(ProjectActionRefused):
            asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        reconciled = asyncio.run(harness.reconcile(harness.caller, prepared["action_ref"]))
        assert reconciled["cleanup_state"] == "UNCERTAIN"
        assert harness.store.cleanup_uncertain
    finally:
        monkeypatch.setattr(patch_port.os, "close", real_close)
        harness.close()


@pytest.mark.parametrize("boundary", ["unlock", "mutex_close", "receipt_close"])
def test_postpublication_cleanup_is_visible_with_historical_effect(tmp_path, monkeypatch, boundary):
    from integrations.workbench_action_mcp import action_artifacts as artifacts

    target = tmp_path / "leaf.txt"
    harness = Harness(tmp_path, allowed_paths=("leaf.txt",))
    real_close, real_flock = os.close, artifacts.fcntl.flock
    fired = False
    try:
        prepared = asyncio.run(harness.prepare(harness.caller, {
            "project_ref": harness.project_ref, "relative_path": "leaf.txt", "mode": "CREATE",
            "new_text": "once\n",
        }))
        result_path = harness.store_path / artifact_name(_action_id(harness, prepared["action_ref"]), "result")

        def close(fd):
            nonlocal fired
            opened = os.fstat(fd)
            match = False
            if result_path.exists():
                match = (boundary == "receipt_close" and opened.st_ino == result_path.stat().st_ino or
                         boundary == "mutex_close" and opened.st_ino == harness.store.inode and fd != harness.store_fd)
            real_close(fd)
            if match and not fired:
                fired = True
                raise OSError("close acknowledgement uncertain")

        def flock(fd, operation):
            nonlocal fired
            real_flock(fd, operation)
            if boundary == "unlock" and operation == artifacts.fcntl.LOCK_UN:
                fired = True
                raise OSError("unlock acknowledgement uncertain")

        monkeypatch.setattr(artifacts.os, "close", close)
        monkeypatch.setattr(artifacts.fcntl, "flock", flock)
        result = asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert fired
        assert result["effect_state"] == "EFFECT_UNKNOWN"
        assert result["cleanup_state"] == "UNCERTAIN"
        assert target.read_text() == "once\n"
        monkeypatch.setattr(artifacts.os, "close", real_close)
        monkeypatch.setattr(artifacts.fcntl, "flock", real_flock)
        historical = asyncio.run(harness.reconcile(harness.caller, prepared["action_ref"]))
        assert historical["effect_state"] == "APPLIED"
        assert historical["cleanup_state"] == "UNCERTAIN"
        assert harness.store.cleanup_uncertain
        with pytest.raises(artifacts.ActionArtifactUncertain):
            harness.store.raise_if_cleanup_uncertain()
    finally:
        monkeypatch.setattr(artifacts.os, "close", real_close)
        monkeypatch.setattr(artifacts.fcntl, "flock", real_flock)
        harness.close()


def test_claim_writer_close_uncertainty_forbids_publication(tmp_path, monkeypatch):
    from integrations.workbench_action_mcp import action_artifacts as artifacts

    harness = Harness(tmp_path, allowed_paths=("leaf.txt",))
    real_close = os.close
    fired = False
    try:
        prepared = asyncio.run(harness.prepare(harness.caller, {
            "project_ref": harness.project_ref, "relative_path": "leaf.txt", "mode": "CREATE",
            "new_text": "once\n",
        }))
        claim_path = harness.store_path / artifact_name(_action_id(harness, prepared["action_ref"]), "claim")

        def close(fd):
            nonlocal fired
            match = claim_path.exists() and os.fstat(fd).st_ino == claim_path.stat().st_ino
            real_close(fd)
            if match and not fired:
                fired = True
                raise OSError("claim close uncertain")

        monkeypatch.setattr(artifacts.os, "close", close)
        result = asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert fired
        assert result["effect_state"] == "EFFECT_UNKNOWN"
        assert result["cleanup_state"] == "UNCERTAIN"
        assert not (tmp_path / "leaf.txt").exists()
        assert claim_path.exists()
        assert harness.store.cleanup_uncertain
    finally:
        monkeypatch.setattr(artifacts.os, "close", real_close)
        harness.close()
