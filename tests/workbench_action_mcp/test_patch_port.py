from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import os
from pathlib import Path

import pytest

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
    def __init__(self, root: Path, *, allowed_paths: tuple[str, ...]) -> None:
        self.clock = 1_800_000_000_000
        self.root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        root_stat = os.fstat(self.root_fd)
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

        def resolve(caller: ActionCaller, project_ref: str):
            if caller != self.caller or project_ref != self.project_ref:
                return None
            return ProjectActionBinding(caller, project_ref, self.scope)

        async def run_io(operation):
            return operation()

        self.prepare, self.commit, self.reconcile = create_text_patch_port(
            resolve_binding=resolve,
            clock_ms=lambda: self.clock,
            run_io=run_io,
            token_codec=ActionTokenCodec(b"k" * 32),
            action_ttl_ms=60_000,
        )

    def close(self) -> None:
        os.close(self.root_fd)


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
        assert before["effect_state"] == "NOT_APPLIED"

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
        result = asyncio.run(harness.commit(harness.caller, prepared["action_ref"]))
        assert result["effect_state"] == "EFFECT_UNKNOWN"
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
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.reconcile(harness.caller, token))
        assert caught.value.code == "ACTION_EXPIRED"
        assert target.read_bytes() == original
    finally:
        harness.close()
