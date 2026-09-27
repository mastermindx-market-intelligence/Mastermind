from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import os
from pathlib import Path

import pytest

from integrations.workbench_action_mcp.action_artifacts import (
    ActionHostBinding,
    adopt_artifact_store,
)
from integrations.workbench_action_mcp.contracts import (
    ActionCaller,
    ActionScope,
    ActionTokenCodec,
    ProjectActionBinding,
)
from integrations.workbench_action_mcp.patch_port import (
    ProjectActionRefused,
    create_text_patch_port,
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class Harness:
    def __init__(
        self,
        root: Path,
        *,
        allowed_paths: tuple[str, ...],
        host_id: str = "b" * 64,
        boot_session_id: str = "boot-session-alpha",
        store_dir: Path | None = None,
        threaded: bool = False,
        admission_evidence=None,
    ) -> None:
        self.clock = 1_800_000_000_000
        self.root = root
        self.root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        os.set_inheritable(self.root_fd, False)
        root_stat = os.fstat(self.root_fd)
        self.store_path = store_dir if store_dir is not None else root / "mmx-action-store"
        self.store_path.mkdir(mode=0o700, exist_ok=True)
        os.chmod(self.store_path, 0o700)
        self.store_fd = os.open(
            self.store_path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
        )
        os.set_inheritable(self.store_fd, False)
        self.store = adopt_artifact_store(self.store_fd)
        self.host = ActionHostBinding(host_id=host_id, boot_session_id=boot_session_id)
        self.caller = ActionCaller(
            subject_digest="a" * 64,
            client_ref="client-ref",
            resource="https://workbench.example.test/mcp",
            scopes=("workbench.action",),
            expires_at=self.clock // 1000 + 3600,
        )
        self.scope = ActionScope(
            root_fd=self.root_fd,
            root_device=root_stat.st_dev,
            root_inode=root_stat.st_ino,
            context_ref="context:alpha",
            responsibility_ref="responsibility:alpha",
            operation_ref="operation:alpha",
            owner_ref="owner:alpha",
            generation="generation:alpha",
            allowed_paths=allowed_paths,
            expires_at_ms=self.clock + 300_000,
            committed_head="1" * 40,
        )
        self.project_ref = "project:alpha"
        self.codec = ActionTokenCodec(b"k" * 32)

        def resolve(caller: ActionCaller, project_ref: str):
            if caller != self.caller or project_ref != self.project_ref:
                return None
            return ProjectActionBinding(caller, project_ref, self.scope)

        async def run_io(operation):
            if not threaded:
                return operation()
            return await asyncio.get_running_loop().run_in_executor(None, operation)

        self.prepare, self.commit, self.reconcile = create_text_patch_port(
            resolve_binding=resolve,
            clock_ms=lambda: self.clock,
            run_io=run_io,
            token_codec=self.codec,
            artifact_store=self.store,
            host=self.host,
            action_ttl_ms=60_000,
            admission_evidence=admission_evidence,
        )

    def close(self) -> None:
        os.close(self.root_fd)
        os.close(self.store_fd)


def test_replace_prepare_commit_reconcile_and_replay(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    original = b"alpha\nbeta\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("sample.py",))
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "sample.py",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "beta",
                    "new_text": "gamma",
                },
            )
        )
        assert target.read_bytes() == original
        assert prepared["status"] == "PREPARED"
        assert prepared["preimage_sha256"] == _sha(original)
        expected = b"alpha\ngamma\n"
        assert prepared["postimage_sha256"] == _sha(expected)

        result = asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert result["effect_state"] == "APPLIED"
        assert result["observed_sha256"] == _sha(expected)
        assert target.read_bytes() == expected

        reconciled = asyncio.run(
            harness.reconcile(harness.caller, prepared["action_ref"])
        )
        assert reconciled["effect_state"] == "APPLIED"
        replay = asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert replay["effect_state"] == "APPLIED"
        assert target.read_bytes() == expected
    finally:
        harness.close()


def test_create_is_not_applied_until_commit_and_replay_is_read_only(tmp_path: Path) -> None:
    target = tmp_path / "created.txt"
    harness = Harness(tmp_path, allowed_paths=("created.txt",))
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "created.txt",
                    "mode": "CREATE",
                    "new_text": "created\n",
                },
            )
        )
        assert not target.exists()
        before = asyncio.run(harness.reconcile(harness.caller, prepared["action_ref"]))
        assert before["effect_state"] == "EFFECT_UNKNOWN"

        applied = asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert applied["effect_state"] == "APPLIED"
        assert target.read_text() == "created\n"
        inode = target.stat().st_ino
        replay = asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert replay["effect_state"] == "APPLIED"
        assert target.stat().st_ino == inode
    finally:
        harness.close()


def test_lost_commit_reply_is_reconciled_without_second_write(tmp_path: Path) -> None:
    target = tmp_path / "lost.txt"
    original = b"before\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("lost.txt",))
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "lost.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "before",
                    "new_text": "after",
                },
            )
        )
        asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        inode = target.stat().st_ino
        reconciled = asyncio.run(
            harness.reconcile(harness.caller, prepared["action_ref"])
        )
        assert reconciled["effect_state"] == "APPLIED"
        assert target.read_text() == "after\n"
        assert target.stat().st_ino == inode
    finally:
        harness.close()


def test_changed_preimage_never_gets_clobbered(tmp_path: Path) -> None:
    target = tmp_path / "race.txt"
    original = b"one\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("race.txt",))
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "race.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "one",
                    "new_text": "two",
                },
            )
        )
        target.write_text("foreign\n")
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert caught.value.code == "ACTION_PREIMAGE_MISMATCH"
        assert target.read_text() == "foreign\n"
    finally:
        harness.close()


def test_binding_change_after_prepare_refuses_without_effect(tmp_path: Path) -> None:
    target = tmp_path / "binding.txt"
    original = b"old\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("binding.txt",))
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "binding.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "old",
                    "new_text": "new",
                },
            )
        )
        harness.scope = dataclasses.replace(
            harness.scope, generation="generation:replacement"
        )
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert caught.value.code == "ACTION_BINDING_CHANGED"
        assert target.read_bytes() == original
    finally:
        harness.close()


def test_symlink_and_outside_allowlist_are_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    harness = Harness(tmp_path, allowed_paths=("link.txt",))
    try:
        with pytest.raises(ProjectActionRefused):
            asyncio.run(
                harness.prepare(
                    harness.caller,
                    {
                        "project_ref": harness.project_ref,
                        "relative_path": "link.txt",
                        "mode": "REPLACE",
                        "expected_sha256": _sha(outside.read_bytes()),
                        "old_text": "outside",
                        "new_text": "inside",
                    },
                )
            )
        assert outside.read_text() == "outside\n"
        with pytest.raises(ProjectActionRefused):
            asyncio.run(
                harness.prepare(
                    harness.caller,
                    {
                        "project_ref": harness.project_ref,
                        "relative_path": "not-allowed.txt",
                        "mode": "CREATE",
                        "new_text": "x",
                    },
                )
            )
    finally:
        harness.close()


def test_tamper_wrong_caller_and_expiry_refuse(tmp_path: Path) -> None:
    target = tmp_path / "guard.txt"
    original = b"old\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("guard.txt",))
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "guard.txt",
                    "mode": "REPLACE",
                    "expected_sha256": _sha(original),
                    "old_text": "old",
                    "new_text": "new",
                },
            )
        )
        token = prepared["action_ref"]
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.commit(harness.caller, tampered))
        assert caught.value.code == "ACTION_INVALID"

        other = dataclasses.replace(harness.caller, client_ref="other-client")
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.commit(other, token))
        assert caught.value.code == "ACTION_BINDING_CHANGED"

        harness.clock += 61_000
        reconciled = asyncio.run(harness.reconcile(harness.caller, token))
        assert reconciled["effect_state"] == "EFFECT_UNKNOWN"
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.commit(harness.caller, token))
        assert caught.value.code == "ACTION_EXPIRED"
        assert target.read_bytes() == original
    finally:
        harness.close()


# ---------------------------------------------------------------------------
# Durable pre-dispatch admission evidence (#670).  The port never reads the
# ledger itself: it consumes one closed verdict from the entry point, and only
# REFUSED_ONLY over an untouched source turns artifact absence into
# NOT_APPLIED.
# ---------------------------------------------------------------------------


class _Verdicts:
    def __init__(self, verdict: object) -> None:
        self.verdict = verdict
        self.calls: list[object] = []

    def __call__(self, action_ref: object) -> str:
        self.calls.append(action_ref)
        if isinstance(self.verdict, BaseException):
            raise self.verdict
        return self.verdict  # type: ignore[return-value]


def _prepared_replace(harness: Harness, original: bytes) -> str:
    prepared = asyncio.run(
        harness.prepare(
            harness.caller,
            {
                "project_ref": harness.project_ref,
                "relative_path": "sample.py",
                "mode": "REPLACE",
                "expected_sha256": _sha(original),
                "old_text": "beta",
                "new_text": "gamma",
            },
        )
    )
    return prepared["action_ref"]


def test_unclaimed_action_stays_unknown_without_admission_evidence(tmp_path: Path) -> None:
    """The OAuth adapter composes the port without a ledger reader: artifact
    absence is EFFECT_UNKNOWN exactly as before."""

    target = tmp_path / "sample.py"
    original = b"alpha\nbeta\n"
    target.write_bytes(original)
    harness = Harness(tmp_path, allowed_paths=("sample.py",))
    try:
        action_ref = _prepared_replace(harness, original)
        reconciled = asyncio.run(harness.reconcile(harness.caller, action_ref))
        assert reconciled["effect_state"] == "EFFECT_UNKNOWN"
        assert reconciled["observed_sha256"] == _sha(original)
    finally:
        harness.close()


@pytest.mark.parametrize(
    "verdict,expected",
    [
        ("REFUSED_ONLY", "NOT_APPLIED"),
        ("ACCEPTED", "EFFECT_UNKNOWN"),
        ("ABSENT", "EFFECT_UNKNOWN"),
        ("UNCERTAIN", "EFFECT_UNKNOWN"),
        ("not_applied", "EFFECT_UNKNOWN"),
        (None, "EFFECT_UNKNOWN"),
        (RuntimeError("ledger unavailable"), "EFFECT_UNKNOWN"),
    ],
)
def test_unclaimed_action_maps_only_refused_only_to_not_applied(
    tmp_path: Path, verdict, expected
) -> None:
    target = tmp_path / "sample.py"
    original = b"alpha\nbeta\n"
    target.write_bytes(original)
    evidence = _Verdicts(verdict)
    harness = Harness(tmp_path, allowed_paths=("sample.py",), admission_evidence=evidence)
    try:
        action_ref = _prepared_replace(harness, original)
        reconciled = asyncio.run(harness.reconcile(harness.caller, action_ref))
        assert reconciled["effect_state"] == expected
        assert reconciled["observed_sha256"] == _sha(original)
        assert evidence.calls == [action_ref]
        assert target.read_bytes() == original
        assert os.listdir(harness.store_path) == []
    finally:
        harness.close()


@pytest.mark.parametrize("drift", ["postimage", "foreign", "absent"])
def test_unclaimed_refused_action_with_moved_source_stays_unknown(
    tmp_path: Path, drift: str
) -> None:
    target = tmp_path / "sample.py"
    original = b"alpha\nbeta\n"
    target.write_bytes(original)
    evidence = _Verdicts("REFUSED_ONLY")
    harness = Harness(tmp_path, allowed_paths=("sample.py",), admission_evidence=evidence)
    try:
        action_ref = _prepared_replace(harness, original)
        if drift == "postimage":
            target.write_bytes(b"alpha\ngamma\n")
        elif drift == "foreign":
            target.write_bytes(b"foreign\n")
        else:
            target.unlink()
        reconciled = asyncio.run(harness.reconcile(harness.caller, action_ref))
        assert reconciled["effect_state"] == "EFFECT_UNKNOWN"
        # Source evidence conflicts, so the ledger is never even consulted.
        assert evidence.calls == []
    finally:
        harness.close()


def test_unclaimed_create_is_not_applied_only_while_target_is_absent(tmp_path: Path) -> None:
    evidence = _Verdicts("REFUSED_ONLY")
    harness = Harness(tmp_path, allowed_paths=("fresh.py",), admission_evidence=evidence)
    try:
        prepared = asyncio.run(
            harness.prepare(
                harness.caller,
                {
                    "project_ref": harness.project_ref,
                    "relative_path": "fresh.py",
                    "mode": "CREATE",
                    "new_text": "created\n",
                },
            )
        )
        action_ref = prepared["action_ref"]
        absent = asyncio.run(harness.reconcile(harness.caller, action_ref))
        assert absent["effect_state"] == "NOT_APPLIED"
        assert absent["observed_sha256"] is None
        (tmp_path / "fresh.py").write_bytes(b"created\n")
        present = asyncio.run(harness.reconcile(harness.caller, action_ref))
        assert present["effect_state"] == "EFFECT_UNKNOWN"
        assert evidence.calls == [action_ref]
    finally:
        harness.close()


def test_artifact_evidence_outranks_admission_evidence(tmp_path: Path) -> None:
    """Once a claim exists the ledger is irrelevant: the artifact store is the
    effect owner and the verdict callback is never consulted."""

    target = tmp_path / "sample.py"
    original = b"alpha\nbeta\n"
    target.write_bytes(original)
    evidence = _Verdicts("REFUSED_ONLY")
    harness = Harness(tmp_path, allowed_paths=("sample.py",), admission_evidence=evidence)
    try:
        action_ref = _prepared_replace(harness, original)
        committed = asyncio.run(harness.commit(harness.caller, action_ref))
        assert committed["effect_state"] == "APPLIED"
        reconciled = asyncio.run(harness.reconcile(harness.caller, action_ref))
        assert reconciled["effect_state"] == "APPLIED"
        assert evidence.calls == []
    finally:
        harness.close()


def test_admission_evidence_must_be_callable(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        Harness(tmp_path, allowed_paths=("sample.py",), admission_evidence="REFUSED_ONLY")
