from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import threading
from pathlib import Path

import pytest

from control_plane.executive_privileged_action import (
    REQUEST_SCHEMA,
    STATUS_REQUEST_SCHEMA,
    canonical_request_bytes,
    validate_request,
)
from control_plane.executive_privileged_broker import (
    BROKER_CONFIG_SCHEMA,
    RECONCILE_REQUEST_SCHEMA,
    RECONCILIATION_SCHEMA,
    STATUS_RECONCILED_NOT_APPLIED,
    PrivilegedActionBroker,
    PrivilegedBrokerConfig,
    PrivilegedBrokerError,
    ReconciledNotAppliedError,
    serve_connection,
    validate_reconciliation_pair,
)
from scripts import mmx_privileged_reconcile


TARGET_ID = "fi-b4493b5-ready-deviceauth-20260923"
TARGET_RELEASE = "a" * 40
CURRENT_RELEASE = "b" * 40
READINESS_SHA = "c" * 64
AUTH_IDENTITY = {"uid": 451, "gid": 451, "mode": 0o600, "inode": 101}
BINARY_IDENTITY = {
    "path": "/Library/Application Support/MastermindExecutive/bin/codex-0.147.0",
    "version": "0.147.0",
    "sha256": "1" * 64,
    "team_identifier": "2DC432GLL2",
    "uid": 0,
    "gid": 0,
    "mode": 0o555,
    "inode": 202,
}


def _target_request() -> dict[str, object]:
    return {
        "schema": REQUEST_SCHEMA,
        "request_id": TARGET_ID,
        "action": "executive.worker_auth.verify_ready",
        "args": {
            "expected_credential_kind": "device-auth",
            "workspace_binding_class": "company-workspace-admin-attested",
            "credential_expires_at": "2026-09-30T02:00:00Z",
        },
    }


def _evidence(**changes) -> dict[str, object]:
    value: dict[str, object] = {
        "readiness_receipt_sha256": READINESS_SHA,
        "readiness_document": {
            "schema_version": "mastermind.executive_provider_readiness/v2",
            "passed": True,
            "refusal": None,
            "observed_at": "2026-09-21T22:49:00Z",
            "expected_credential_kind": "device-auth",
            "workspace_binding_class": "company-workspace-admin-attested",
            "credential_expires_at": "2026-09-22T10:30:00Z",
            "credential_lstat": dict(AUTH_IDENTITY),
            "codex_binary": dict(BINARY_IDENTITY),
            "provider_identity": {
                "credential_lstat": dict(AUTH_IDENTITY),
                "codex_binary": dict(BINARY_IDENTITY),
            },
        },
        "readiness_transaction_lock_present": False,
        "verify_ready_processes": (),
        "current_auth_identity": dict(AUTH_IDENTITY),
        "current_binary_identity": dict(BINARY_IDENTITY),
    }
    value.update(changes)
    return value


def _broker(tmp_path: Path, *, evidence=None) -> PrivilegedActionBroker:
    release = tmp_path / CURRENT_RELEASE
    release.mkdir(parents=True)
    config = PrivilegedBrokerConfig(
        release_root=release,
        receipt_root=tmp_path / "receipts",
        allowed_peer_uids=(450, 501),
        timeout_seconds=30,
        broker_version="test",
    )
    return PrivilegedActionBroker(
        config,
        executor=lambda *_a, **_k: subprocess.CompletedProcess([], 0, b"", b""),
        require_root=False,
        trust_validator=lambda _config: None,
        reconciliation_observer=lambda: dict(evidence or _evidence()),
    )


def _marker(broker: PrivilegedActionBroker, *, action=None) -> tuple[str, bytes]:
    raw = _target_request()
    if action is not None:
        raw["action"] = action
        raw["args"] = {}
    validated = validate_request(raw)
    digest = hashlib.sha256(canonical_request_bytes(validated)).hexdigest()
    value = {
        "schema": "mastermind.executive_privileged_action_inflight.v1",
        "request_id": TARGET_ID,
        "request_sha256": digest,
        "action": validated.action,
        "effect_class": validated.effect_class,
        "started_at": "2026-09-23T01:46:34Z",
        "release_sha": TARGET_RELEASE,
    }
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path = broker.inflight_path(TARGET_ID)
    path.write_bytes(encoded)
    path.chmod(0o600)
    return digest, encoded


def _reconcile_request(digest: str, marker_bytes: bytes) -> dict[str, object]:
    return {
        "schema": RECONCILE_REQUEST_SCHEMA,
        "target_request_id": TARGET_ID,
        "target_request_sha256": digest,
        "target_marker_sha256": hashlib.sha256(marker_bytes).hexdigest(),
        "target_release_sha": TARGET_RELEASE,
        "readiness_receipt_sha256": READINESS_SHA,
        "expected_credential_kind": "device-auth",
        "workspace_binding_class": "company-workspace-admin-attested",
        "credential_expires_at": "2026-09-30T02:00:00Z",
    }


def _status() -> dict[str, str]:
    return {"schema": STATUS_REQUEST_SCHEMA, "request_id": TARGET_ID}


def test_reconcile_is_create_only_marker_preserving_and_idempotent(tmp_path: Path) -> None:
    broker = _broker(tmp_path)
    digest, marker_bytes = _marker(broker)
    request = _reconcile_request(digest, marker_bytes)

    record, replayed = broker.reconcile_not_applied(request, peer_uid=501)
    second, second_replayed = broker.reconcile_not_applied(request, peer_uid=501)

    assert replayed is False
    assert second_replayed is True
    assert second == record
    assert record["schema"] == RECONCILIATION_SCHEMA
    assert record["classification"] == "NOT_APPLIED"
    assert record["target_request_id"] == TARGET_ID
    assert broker.inflight_path(TARGET_ID).read_bytes() == marker_bytes
    assert broker.reconciliation_path(TARGET_ID).is_file()


def test_reconciled_status_is_durable_and_original_request_cannot_replay(tmp_path: Path) -> None:
    calls = []
    broker = _broker(tmp_path)
    broker._executor = lambda *a, **k: calls.append((a, k)) or subprocess.CompletedProcess([], 0, b"", b"")
    digest, marker_bytes = _marker(broker)
    broker.reconcile_not_applied(_reconcile_request(digest, marker_bytes), peer_uid=501)

    projection = broker.query_status(_status(), peer_uid=501)
    assert projection["status"] == STATUS_RECONCILED_NOT_APPLIED
    assert projection["marker_release_sha"] == TARGET_RELEASE
    assert projection["reconciliation"]["classification"] == "NOT_APPLIED"

    with pytest.raises(ReconciledNotAppliedError):
        broker.handle(_target_request(), peer_uid=501)
    assert calls == []


@pytest.mark.parametrize(
    "evidence",
    [
        _evidence(readiness_receipt_sha256="d" * 64),
        _evidence(readiness_transaction_lock_present=True),
        _evidence(verify_ready_processes=("123 root provision-worker-auth.sh --verify-ready",)),
        _evidence(current_auth_identity={**AUTH_IDENTITY, "inode": 999}),
        _evidence(current_binary_identity={**BINARY_IDENTITY, "inode": 999}),
        _evidence(
            readiness_document={
                **_evidence()["readiness_document"],
                "credential_expires_at": "2026-09-30T02:00:00Z",
            }
        ),
        _evidence(
            readiness_document={
                "schema_version": "mastermind.executive_provider_readiness/v2",
                "passed": True,
                "refusal": None,
                "observed_at": "2026-09-23T01:46:35Z",
            }
        ),
    ],
)
def test_reconcile_refuses_when_not_applied_evidence_is_incomplete(
    tmp_path: Path, evidence: dict[str, object]
) -> None:
    broker = _broker(tmp_path, evidence=evidence)
    digest, marker_bytes = _marker(broker)
    with pytest.raises(PrivilegedBrokerError):
        broker.reconcile_not_applied(
            _reconcile_request(digest, marker_bytes),
            peer_uid=501,
        )
    assert broker.inflight_path(TARGET_ID).read_bytes() == marker_bytes
    assert not broker.reconciliation_path(TARGET_ID).exists()


def test_reconcile_refuses_wrong_marker_hash_or_non_readiness_action(tmp_path: Path) -> None:
    broker = _broker(tmp_path)
    digest, marker_bytes = _marker(broker)
    request = _reconcile_request(digest, marker_bytes)
    request["target_marker_sha256"] = "d" * 64
    with pytest.raises(PrivilegedBrokerError):
        broker.reconcile_not_applied(request, peer_uid=501)

    other = _broker(tmp_path / "other")
    digest, marker_bytes = _marker(other, action="executive.services.start")
    with pytest.raises(PrivilegedBrokerError):
        other.reconcile_not_applied(
            _reconcile_request(digest, marker_bytes),
            peer_uid=501,
        )


def test_reconciliation_pair_refuses_unreviewed_namespace_shape(tmp_path: Path) -> None:
    broker = _broker(tmp_path)
    digest, marker_bytes = _marker(broker)
    broker.reconcile_not_applied(_reconcile_request(digest, marker_bytes), peer_uid=501)
    record = broker.reconciliation_path(TARGET_ID)
    outside = tmp_path / "outside"
    outside.mkdir()
    relocated = outside / record.name
    relocated.write_bytes(record.read_bytes())

    with pytest.raises(PrivilegedBrokerError):
        validate_reconciliation_pair(
            broker.inflight_path(TARGET_ID),
            relocated,
            expected_request_id=TARGET_ID,
            require_root_metadata=False,
        )


def test_terminal_receipt_and_reconciliation_can_never_coexist(tmp_path: Path) -> None:
    broker = _broker(tmp_path)
    digest, marker_bytes = _marker(broker)
    broker.reconcile_not_applied(_reconcile_request(digest, marker_bytes), peer_uid=501)
    broker.receipt_path(TARGET_ID).write_text("{}\n", encoding="utf-8")

    with pytest.raises(PrivilegedBrokerError, match="both terminal and reconciliation"):
        validate_reconciliation_pair(
            broker.inflight_path(TARGET_ID),
            broker.reconciliation_path(TARGET_ID),
            expected_request_id=TARGET_ID,
            require_root_metadata=False,
        )
    with pytest.raises(PrivilegedBrokerError):
        broker.query_status(_status(), peer_uid=501)
def test_reconciled_status_requires_original_marker_to_remain_intact(tmp_path: Path) -> None:
    broker = _broker(tmp_path)
    digest, marker_bytes = _marker(broker)
    broker.reconcile_not_applied(_reconcile_request(digest, marker_bytes), peer_uid=501)
    broker.inflight_path(TARGET_ID).write_text("tampered\n", encoding="utf-8")
    with pytest.raises(PrivilegedBrokerError):
        broker.query_status(_status(), peer_uid=501)


def test_wire_dispatches_reconciliation_schema_without_effect_executor(tmp_path: Path) -> None:
    class MemoryConnection:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload
            self.sent = bytearray()

        def recv(self, _size: int) -> bytes:
            payload, self.payload = self.payload, b""
            return payload

        def sendall(self, payload: bytes) -> None:
            self.sent.extend(payload)

    broker = _broker(tmp_path)
    digest, marker_bytes = _marker(broker)
    request = _reconcile_request(digest, marker_bytes)
    payload = (json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n").encode()
    connection = MemoryConnection(payload)

    serve_connection(broker, connection, peer_resolver=lambda _connection: 501)
    response = json.loads(bytes(connection.sent))
    assert response["ok"] is True
    assert response["reconciled"] is True
    assert response["replayed"] is False
    assert response["reconciliation"]["classification"] == "NOT_APPLIED"
def test_helper_builds_exact_request_and_validates_response() -> None:
    values = [
        "reconcile-not-applied",
        "--request-id", TARGET_ID,
        "--request-sha256", "1" * 64,
        "--marker-sha256", "2" * 64,
        "--marker-release-sha", TARGET_RELEASE,
        "--readiness-receipt-sha256", READINESS_SHA,
        "--expected-credential-kind", "device-auth",
        "--workspace-binding-class", "company-workspace-admin-attested",
        "--credential-expires-at", "2026-09-30T02:00:00Z",
    ]
    digest = hashlib.sha256(
        canonical_request_bytes(validate_request(_target_request()))
    ).hexdigest()
    values[values.index("1" * 64)] = digest
    request = mmx_privileged_reconcile.build_reconcile_request(values)
    assert request == {
        "schema": RECONCILE_REQUEST_SCHEMA,
        "target_request_id": TARGET_ID,
        "target_request_sha256": digest,
        "target_marker_sha256": "2" * 64,
        "target_release_sha": TARGET_RELEASE,
        "readiness_receipt_sha256": READINESS_SHA,
        "expected_credential_kind": "device-auth",
        "workspace_binding_class": "company-workspace-admin-attested",
        "credential_expires_at": "2026-09-30T02:00:00Z",
    }
    response = {
        "schema": "mastermind.executive_privileged_action_response.v1",
        "ok": True,
        "reconciled": True,
        "replayed": False,
        "reconciliation": {
            "schema": RECONCILIATION_SCHEMA,
            "classification": "NOT_APPLIED",
            "target_request_id": TARGET_ID,
            "target_request_sha256": digest,
            "target_action": "executive.worker_auth.verify_ready",
            "target_effect_class": "CREDENTIAL_ADMIN_READINESS",
            "target_started_at": "2026-09-23T01:46:34Z",
            "target_release_sha": TARGET_RELEASE,
            "target_marker_sha256": "2" * 64,
            "readiness_receipt_sha256": READINESS_SHA,
            "readiness_observed_at": "2026-09-21T22:49:00Z",
            "expected_credential_kind": "device-auth",
            "workspace_binding_class": "company-workspace-admin-attested",
            "credential_expires_at": "2026-09-30T02:00:00Z",
            "readiness_transaction_lock_absent": True,
            "verify_ready_process_absent": True,
            "readiness_identity_current": True,
            "target_deadline_absent": True,
            "reconciler_release_sha": CURRENT_RELEASE,
            "reconciled_at": "2026-09-23T02:00:00Z",
            "broker_version": "test",
        },
    }
    assert mmx_privileged_reconcile.validate_reconcile_response(
        response, expected_request_id=TARGET_ID
    )["reconciliation"]["target_request_id"] == TARGET_ID


def test_helper_transport_uses_one_connection_and_never_retries(tmp_path: Path) -> None:
    socket_path = tmp_path / "broker.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(1)
    accepts = []

    def serve_once() -> None:
        connection, _ = listener.accept()
        accepts.append(True)
        with connection:
            data = b""
            while not data.endswith(b"\n"):
                data += connection.recv(4096)
            request = json.loads(data)
            response = {
                "schema": "mastermind.executive_privileged_action_response.v1",
                "ok": True,
                "reconciled": True,
                "replayed": False,
                "reconciliation": {
                    "schema": RECONCILIATION_SCHEMA,
                    "classification": "NOT_APPLIED",
                    "target_request_id": request["target_request_id"],
                },
            }
            connection.sendall(
                (json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n").encode()
            )

    thread = threading.Thread(target=serve_once)
    thread.start()
    digest = hashlib.sha256(
        canonical_request_bytes(validate_request(_target_request()))
    ).hexdigest()
    request = _reconcile_request(digest, b"marker")
    response = mmx_privileged_reconcile.send_reconcile_request(
        request, socket_path=socket_path, timeout_seconds=2
    )
    thread.join(2)
    listener.close()
    assert response["ok"] is True
    assert accepts == [True]
