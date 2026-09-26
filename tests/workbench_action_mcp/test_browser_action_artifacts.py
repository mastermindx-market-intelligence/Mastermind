from __future__ import annotations

import os
from pathlib import Path

import pytest

from integrations.workbench_action_mcp.action_artifacts import (
    ACTION_PURPOSE_BROWSER_ACTION,
    ACTION_PURPOSE_BROWSER_RESOURCE,
    ActionArtifactIdentity,
    ActionArtifactUncertain,
    adopt_artifact_store,
    claim_action,
    finalize_action,
    write_action_process,
)
from integrations.workbench_action_mcp.fleet_ops import inspect_artifact_evidence


def _store(root: Path):
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    os.set_inheritable(fd, False)
    return fd, adopt_artifact_store(fd)


def _identity(store, action_id: str, purpose: str) -> ActionArtifactIdentity:
    return ActionArtifactIdentity(
        action_id=action_id,
        purpose=purpose,
        subject_digest="a" * 64,
        client_ref="client:browser",
        resource="https://workbench.example/browser",
        project_ref="project:browser",
        context_ref="context:browser",
        responsibility_ref="responsibility:browser",
        operation_ref="operation:browser",
        owner_ref="owner:browser",
        generation="generation:browser",
        root_device=1,
        root_inode=2,
        store_device=store.device,
        store_inode=store.inode,
        host_id="b" * 64,
        boot_session_id="boot:browser",
        relative_path="browser:" + action_id,
        source_identity="c" * 64,
    )


def test_browser_action_reuses_existing_claim_result_owner(tmp_path: Path):
    root = tmp_path / "artifacts"
    fd, store = _store(root)
    try:
        identity = _identity(store, "1" * 32, ACTION_PURPOSE_BROWSER_ACTION)
        assert claim_action(store, identity, claimed_at_ms=10).created is True
        finalize_action(
            store,
            identity,
            effect_state="APPLIED",
            observed_sha256=None,
            completed_at_ms=11,
            durability="durable",
            details={"tool": "browser_click"},
        )
        evidence = inspect_artifact_evidence(str(root))
        assert evidence.completed_action_count == 1
        assert evidence.unresolved_action_ids == ()
    finally:
        os.close(fd)


def test_browser_resource_can_persist_process_identity_in_same_store(tmp_path: Path):
    root = tmp_path / "artifacts"
    fd, store = _store(root)
    try:
        identity = _identity(store, "2" * 32, ACTION_PURPOSE_BROWSER_RESOURCE)
        claim_action(store, identity, claimed_at_ms=20)
        write_action_process(
            store,
            identity,
            pid=1234,
            process_start_identity="1700000000.000001",
            pgid=1234,
            session_id=1234,
            host_id=identity.host_id,
            boot_session_id=identity.boot_session_id,
            recorded_at_ms=21,
        )
        finalize_action(
            store,
            identity,
            effect_state="APPLIED",
            observed_sha256=None,
            completed_at_ms=22,
            durability="durable",
            details={"relay": "ready"},
        )
        evidence = inspect_artifact_evidence(str(root))
        assert evidence.completed_action_count == 1
        assert evidence.unresolved_action_ids == ()
    finally:
        os.close(fd)


def test_browser_resource_pending_process_blocks_lease_renewal(tmp_path: Path):
    root = tmp_path / "artifacts"
    fd, store = _store(root)
    try:
        identity = _identity(store, "3" * 32, ACTION_PURPOSE_BROWSER_RESOURCE)
        claim_action(store, identity, claimed_at_ms=30)
        write_action_process(
            store,
            identity,
            pid=1235,
            process_start_identity="1700000000.000002",
            pgid=1235,
            session_id=1235,
            host_id=identity.host_id,
            boot_session_id=identity.boot_session_id,
            recorded_at_ms=31,
        )
        evidence = inspect_artifact_evidence(str(root))
        assert evidence.unresolved_action_ids == ("3" * 32,)
        assert evidence.completed_action_count == 0
    finally:
        os.close(fd)


def test_browser_action_cannot_write_process_artifact(tmp_path: Path):
    root = tmp_path / "artifacts"
    fd, store = _store(root)
    try:
        identity = _identity(store, "4" * 32, ACTION_PURPOSE_BROWSER_ACTION)
        claim_action(store, identity, claimed_at_ms=40)
        with pytest.raises(ActionArtifactUncertain, match="purpose"):
            write_action_process(
                store,
                identity,
                pid=1236,
                process_start_identity="1700000000.000003",
                pgid=1236,
                session_id=1236,
                host_id=identity.host_id,
                boot_session_id=identity.boot_session_id,
                recorded_at_ms=41,
            )
    finally:
        os.close(fd)
