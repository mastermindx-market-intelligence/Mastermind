"""Recovery uses original bounded evidence and never grants ownership by pathname."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import socket
import tempfile
import threading

import pytest

from integrations.mastermind_browser_link.endpoint_evidence import (
    NativeEndpointEvidence, capture_native_endpoint,
)
from integrations.mastermind_browser_link.native_channel import (
    LinkProtocolError, open_private_server, close_private_server,
)
from integrations.mastermind_browser_link.tool_contract import ACTION_TOOL
from integrations.workbench_action_mcp import action_artifacts as artifacts
from integrations.workbench_action_mcp.fleet_ops import inspect_artifact_evidence
from integrations.workbench_browser_mcp import link_session as link_module
from integrations.workbench_browser_mcp.relay import BrowserRelayError, BrowserRequestRefused
from tests.workbench_action_mcp.test_action_artifacts import _identity, _open_store
from tests.test_mastermind_browser_link_native import connected, Peer, until, arguments


def descriptor():
    return artifacts.BrowserResourceDescriptor(
        start_ref="original-signed-reference", owner_pid=os.getpid(),
        owner_start_identity="fixture-owner-start", profile_grant_json='{"schema":"fixture"}',
    )


def resource_identity(store, **changes):
    return _identity(purpose="browser_resource", relative_path="browser:" + "a" * 32,
                     store_device=store.device, store_inode=store.inode, **changes)


def test_v2_claim_retains_original_descriptor_and_fleet_uses_same_qualification(tmp_path):
    fd, store = _open_store(tmp_path / "store")
    try:
        identity = resource_identity(store)
        original = descriptor()
        with artifacts.acquire_store_writer(store):
            first = artifacts.claim_action(store, identity, claimed_at_ms=10, descriptor=original)
            artifacts.finalize_action(store, identity, effect_state="APPLIED", observed_sha256=None,
                                      completed_at_ms=20, durability="durable")
            snapshot = artifacts.enumerate_action_evidence(store)
        assert first.claim.schema == artifacts.ACTION_RESOURCE_CLAIM_SCHEMA
        assert snapshot[0].claim.descriptor == original
        assert inspect_artifact_evidence(str(tmp_path / "store")).completed_action_count == 1
        # Canonical reader, not a lossy JSON shape check, governs the new schema.
        claim_path = tmp_path / "store" / (identity.action_id + ".claim")
        value = json.loads(claim_path.read_text())
        value["claimed_at_ms"] = -1
        claim_path.write_text(json.dumps(value))
        assert inspect_artifact_evidence(str(tmp_path / "store")).unresolved_action_ids == (identity.action_id,)
    finally:
        os.close(fd)


def test_descriptor_is_browser_resource_only_and_v1_retains_original_bound(tmp_path):
    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _identity(store_device=store.device, store_inode=store.inode)
        with pytest.raises(artifacts.ActionArtifactError):
            artifacts.claim_action(store, identity, claimed_at_ms=10, descriptor=descriptor())
        claim = artifacts.claim_action(store, identity, claimed_at_ms=10).claim
        assert claim.schema == artifacts.ACTION_CLAIM_SCHEMA and claim.descriptor is None
        path = tmp_path / "store" / (identity.action_id + ".claim")
        path.write_bytes(path.read_bytes() + b" " * 4096)
        assert artifacts.classify_action(store, identity).evidence_status == "uncertain"
    finally:
        os.close(fd)


def test_complete_enumeration_refuses_overflow_or_orphan(tmp_path):
    fd, store = _open_store(tmp_path / "store")
    try:
        for letter in ("a", "b"):
            artifacts.claim_action(store, resource_identity(store, action_id=letter * 32),
                                   claimed_at_ms=10, descriptor=descriptor())
        with artifacts.acquire_store_writer(store):
            with pytest.raises(artifacts.ActionArtifactUncertain, match="bound"):
                artifacts.enumerate_action_evidence(store, maximum_actions=1)
            assert len(artifacts.enumerate_action_evidence(store)) == 2
        orphan = tmp_path / "store" / ("c" * 32 + ".result")
        orphan.write_text("{}")
        orphan.chmod(0o600)
        with artifacts.acquire_store_writer(store), pytest.raises(artifacts.ActionArtifactUncertain, match="orphan"):
            artifacts.enumerate_action_evidence(store)
    finally:
        os.close(fd)


def test_foreign_process_or_disappeared_process_refuses_complete_snapshot(tmp_path, monkeypatch):
    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _identity(store_device=store.device, store_inode=store.inode)
        artifacts.claim_action(store, identity, claimed_at_ms=10)
        path = tmp_path / "store" / (identity.action_id + ".process")
        path.write_text("{}")
        path.chmod(0o600)
        with pytest.raises(artifacts.ActionArtifactUncertain, match="unexpected"):
            artifacts.enumerate_action_evidence(store)
        path.unlink()
        identity = resource_identity(store, action_id="b" * 32)
        artifacts.claim_action(store, identity, claimed_at_ms=10, descriptor=descriptor())
        path = tmp_path / "store" / (identity.action_id + ".process")
        path.write_text("{}")
        path.chmod(0o600)
        monkeypatch.setattr(artifacts, "read_action_process", lambda *_: None)
        with pytest.raises(artifacts.ActionArtifactUncertain, match="disappeared"):
            artifacts.enumerate_action_evidence(store)
    finally:
        os.close(fd)


def test_endpoint_receipt_rejects_replacement_ctime_and_parent_drift():
    with tempfile.TemporaryDirectory(prefix="mmx-evidence-", dir="/tmp") as directory:
        parent = Path(directory)
        path = parent / "native.sock"
        before = parent.stat()
        server = open_private_server(path, owner_uid=os.geteuid())
        replacement = None
        try:
            receipt = capture_native_endpoint(server, path, parent_identity=(before.st_dev, before.st_ino))
            assert NativeEndpointEvidence.from_document(receipt.document()) == receipt
            assert receipt.qualify(path)
            with pytest.raises(LinkProtocolError):
                replace(receipt, socket_ctime_ns=receipt.socket_ctime_ns - 1).remove_after_owner_proved_absence(path)
            with pytest.raises(LinkProtocolError):
                replace(receipt, parent_inode=receipt.parent_inode + 1).remove_after_owner_proved_absence(path)
            assert path.exists()
            path.unlink()
            replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            replacement.bind(str(path))
            path.chmod(0o600)
            with pytest.raises(LinkProtocolError):
                receipt.remove_after_owner_proved_absence(path)
            assert path.exists()
        finally:
            close_private_server(server, path, owner_uid=os.geteuid())
            if replacement is not None:
                replacement.close()


def test_owned_endpoint_cleanup_is_idempotent_after_positive_owner_fence():
    with tempfile.TemporaryDirectory(prefix="mmx-evidence-", dir="/tmp") as directory:
        parent = Path(directory)
        path = parent / "native.sock"
        before = parent.stat()
        server = open_private_server(path, owner_uid=os.geteuid())
        receipt = capture_native_endpoint(server, path, parent_identity=(before.st_dev, before.st_ino))
        # Test fixture owns this listener; simulate crash after receipt persistence.
        server.close()
        receipt.remove_after_owner_proved_absence(path)
        receipt.remove_after_owner_proved_absence(path)
        assert not path.exists()
        close_private_server(server, path, owner_uid=os.geteuid())


def test_pending_write_is_quarantined_before_waiter_wakes_across_native_reconnect(monkeypatch):
    release_waiter = threading.Event()
    class HeldEvent:
        def __init__(self):
            self.event = threading.Event()
        def set(self):
            self.event.set()
        def wait(self, timeout):
            ready = self.event.wait(timeout)
            assert release_waiter.wait(5)
            return ready
    pending_type = link_module._Pending
    monkeypatch.setattr(link_module, "_Pending",
                        lambda kind, tab_id: pending_type(kind, tab_id, event=HeldEvent()))
    with connected() as (session, peer, config), ThreadPoolExecutor(1) as pool:
        future = pool.submit(session.call_with_identity, "lost-old", ACTION_TOOL, arguments())
        peer.receive()
        peer.process.stdin.close()
        until(lambda: session._active is None)
        session._reader_thread.join(timeout=2)
        replacement = Peer(session.enrollment, config, generation="generation-2")
        try:
            replacement.ready()
            until(lambda: session._active is not None)
            with pytest.raises(BrowserRequestRefused):
                session.call_with_identity("new-attempt", ACTION_TOOL, arguments(generation="generation-2"))
            release_waiter.set()
            with pytest.raises(BrowserRelayError):
                future.result(timeout=3)
        finally:
            release_waiter.set()
            replacement.close()
