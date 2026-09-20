from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest

from integrations.workbench_action_mcp.action_artifacts import (
    ACTION_PURPOSE_CLOSED_COMMAND,
    ActionArtifactIdentity,
    ActionArtifactUncertain,
    ActionProcessRecord,
    adopt_artifact_store,
    artifact_name,
    claim_action,
    read_action_process,
    write_action_process,
)


def _open_store(path: Path):
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    os.set_inheritable(fd, False)
    return fd, adopt_artifact_store(fd)


def _identity(store, **changes: object) -> ActionArtifactIdentity:
    values: dict[str, object] = {
        "action_id": "a" * 32,
        "purpose": ACTION_PURPOSE_CLOSED_COMMAND,
        "subject_digest": "b" * 64,
        "client_ref": "client-ref",
        "resource": "https://workbench.example.test/mcp",
        "project_ref": "project:alpha",
        "context_ref": "context:alpha",
        "responsibility_ref": "responsibility:alpha",
        "operation_ref": "operation:alpha",
        "owner_ref": "owner:alpha",
        "generation": "generation:alpha",
        "root_device": 1,
        "root_inode": 2,
        "store_device": store.device,
        "store_inode": store.inode,
        "host_id": "c" * 64,
        "boot_session_id": "boot-alpha",
        "relative_path": "canary.txt",
        "source_identity": "1:2:33188:501:20:1:12:100:101",
    }
    values.update(changes)
    return ActionArtifactIdentity(**values)  # type: ignore[arg-type]


def _write(store, identity) -> ActionProcessRecord:
    return write_action_process(
        store,
        identity,
        pid=123,
        process_start_identity="100.000001",
        pgid=123,
        session_id=123,
        host_id=identity.host_id,
        boot_session_id=identity.boot_session_id,
        recorded_at_ms=101,
    )


def test_process_record_is_durable_immutable_and_bound_to_prior_claim(tmp_path: Path) -> None:
    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _identity(store)
        with pytest.raises(ActionArtifactUncertain):
            _write(store, identity)
        assert claim_action(store, identity, claimed_at_ms=100).created
        record = _write(store, identity)
        assert read_action_process(store, identity) == record
        assert record == ActionProcessRecord(
            schema="mastermind.workbench_command_process.v1",
            identity=identity,
            pid=123,
            process_start_identity="100.000001",
            pgid=123,
            session_id=123,
            host_id=identity.host_id,
            boot_session_id=identity.boot_session_id,
            recorded_at_ms=101,
        )
        before = (tmp_path / "store" / artifact_name(identity.action_id, "process")).read_bytes()
        with pytest.raises(FileExistsError):
            _write(store, identity)
        assert (tmp_path / "store" / artifact_name(identity.action_id, "process")).read_bytes() == before
    finally:
        os.close(fd)


def test_process_record_read_requires_exact_action_and_host_binding(tmp_path: Path) -> None:
    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _identity(store)
        assert claim_action(store, identity, claimed_at_ms=100).created
        _write(store, identity)
        with pytest.raises(ActionArtifactUncertain):
            read_action_process(store, dataclasses.replace(identity, client_ref="other"))
        with pytest.raises(ActionArtifactUncertain):
            write_action_process(
                store,
                identity,
                pid=123,
                process_start_identity="100.000001",
                pgid=123,
                session_id=123,
                host_id="d" * 64,
                boot_session_id=identity.boot_session_id,
                recorded_at_ms=101,
            )
    finally:
        os.close(fd)


@pytest.mark.parametrize("damage", ["duplicate", "extra", "wrong_type", "oversized"])
def test_process_record_corruption_is_never_accepted(tmp_path: Path, damage: str) -> None:
    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _identity(store)
        assert claim_action(store, identity, claimed_at_ms=100).created
        _write(store, identity)
        path = tmp_path / "store" / artifact_name(identity.action_id, "process")
        raw = path.read_text()
        if damage == "duplicate":
            raw = raw.replace('"pid":123', '"pid":999,"pid":123')
        elif damage == "extra":
            raw = raw[:-1] + ',"details":{"argv":["/bin/sh"]}}'
        elif damage == "wrong_type":
            raw = raw.replace('"pid":123', '"pid":true')
        else:
            raw = raw + ("x" * 5000)
        path.write_text(raw)
        with pytest.raises(ActionArtifactUncertain):
            read_action_process(store, identity)
    finally:
        os.close(fd)
