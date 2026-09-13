from __future__ import annotations

from pathlib import Path

import pytest

from control_plane.remote_worker_transport import (
    REMOTE_BROKER_REQUEST_SCHEMA,
    REMOTE_BROKER_RESPONSE_SCHEMA,
    BrokerTransportBinding,
    RemoteBrokerRequest,
    RemoteBrokerResponse,
    RemoteOperationConflict,
    RemoteWorkerTransportError,
    assert_operation_replay_compatible,
    broker_request_sha256,
)


JOB_ID = "JOB-321"
ATTEMPT_ID = "ATT-0123456789abcdef0123456789abcdef"
WORKER_ID = "codex-pro-01"
HOST_REF = "host-01234567"
OPERATION_ID = f"mh1-op:{ATTEMPT_ID}:start"
BROKER_OPERATION = "start"


def _broker_request(prompt: str = "bounded work") -> dict[str, object]:
    return {
        "schema_version": "mastermind.executive_worker_broker_request/v1",
        "request_id": "req-0123456789abcdef",
        "operation": BROKER_OPERATION,
        "payload": {"prompt": prompt, "flags": ["a", "b"]},
    }


def _request(prompt: str = "bounded work") -> RemoteBrokerRequest:
    return RemoteBrokerRequest.build(
        host_ref=HOST_REF,
        job_id=JOB_ID,
        attempt_id=ATTEMPT_ID,
        worker_id=WORKER_ID,
        operation_id=OPERATION_ID,
        broker_operation=BROKER_OPERATION,
        broker_request=_broker_request(prompt),
    )


def test_remote_request_shape_is_closed_and_hash_bound() -> None:
    request = _request()
    wire = request.to_mapping()
    assert set(wire) == {
        "schema",
        "host_ref",
        "job_id",
        "attempt_id",
        "worker_id",
        "operation_id",
        "broker_operation",
        "request_sha256",
        "broker_request",
    }
    assert wire["schema"] == REMOTE_BROKER_REQUEST_SCHEMA
    assert wire["request_sha256"] == broker_request_sha256(wire["broker_request"])
    assert RemoteBrokerRequest.from_mapping(wire) == request


def test_remote_request_rejects_unknown_key_and_hash_mismatch() -> None:
    wire = _request().to_mapping()
    wire["extra"] = True
    with pytest.raises(RemoteWorkerTransportError, match="exactly"):
        RemoteBrokerRequest.from_mapping(wire)

    wire = _request().to_mapping()
    wire["request_sha256"] = "0" * 64
    with pytest.raises(RemoteWorkerTransportError, match="hash"):
        RemoteBrokerRequest.from_mapping(wire)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("job_id", "job-321"),
        ("attempt_id", "ATT-not-a-real-attempt"),
        ("worker_id", "bad worker"),
        ("host_ref", "bad host"),
        ("operation_id", "bad operation"),
        ("broker_operation", "bad operation"),
    ],
)
def test_remote_request_rejects_malformed_identity(field: str, value: str) -> None:
    wire = _request().to_mapping()
    wire[field] = value
    with pytest.raises(RemoteWorkerTransportError):
        RemoteBrokerRequest.from_mapping(wire)


def test_remote_request_payload_is_immutable_after_build() -> None:
    source = _broker_request()
    request = RemoteBrokerRequest.build(
        host_ref=HOST_REF,
        job_id=JOB_ID,
        attempt_id=ATTEMPT_ID,
        worker_id=WORKER_ID,
        operation_id=OPERATION_ID,
        broker_operation=BROKER_OPERATION,
        broker_request=source,
    )
    source["payload"]["prompt"] = "mutated outside"  # type: ignore[index]
    assert request.to_mapping()["broker_request"]["payload"]["prompt"] == "bounded work"
    with pytest.raises(TypeError):
        request.broker_request["payload"]["prompt"] = "mutated inside"  # type: ignore[index]


def test_same_operation_identity_refuses_changed_payload_or_identity() -> None:
    original = _request("one")
    changed = _request("two")
    with pytest.raises(RemoteOperationConflict, match="payload"):
        assert_operation_replay_compatible(original, changed)

    drift = RemoteBrokerRequest.build(
        host_ref=HOST_REF,
        job_id=JOB_ID,
        attempt_id=ATTEMPT_ID,
        worker_id="codex-pro-02",
        operation_id=OPERATION_ID,
        broker_operation=BROKER_OPERATION,
        broker_request=_broker_request("one"),
    )
    with pytest.raises(RemoteOperationConflict, match="identity"):
        assert_operation_replay_compatible(original, drift)


def test_different_operation_identity_does_not_conflict() -> None:
    original = _request("one")
    other = RemoteBrokerRequest.build(
        host_ref=HOST_REF,
        job_id=JOB_ID,
        attempt_id=ATTEMPT_ID,
        worker_id=WORKER_ID,
        operation_id=f"mh1-op:{ATTEMPT_ID}:status",
        broker_operation="status",
        broker_request={**_broker_request("two"), "operation": "status"},
    )
    assert_operation_replay_compatible(original, other)


def test_response_shape_and_exact_request_identity_round_trip() -> None:
    request = _request()
    response = RemoteBrokerResponse.build(
        request=request,
        outcome="completed",
        broker_response={"ok": True, "result": {"state": "RUNNING"}},
        observed_at="2026-09-13T19:30:00Z",
    )
    wire = response.to_mapping()
    assert set(wire) == {
        "schema",
        "host_ref",
        "job_id",
        "attempt_id",
        "worker_id",
        "operation_id",
        "request_sha256",
        "outcome",
        "broker_response",
        "observed_at",
    }
    assert wire["schema"] == REMOTE_BROKER_RESPONSE_SCHEMA
    assert RemoteBrokerResponse.from_mapping(wire, expected_request=request) == response


def test_response_rejects_identity_drift_and_unknown_keys() -> None:
    request = _request()
    wire = RemoteBrokerResponse.build(
        request=request,
        outcome="completed",
        broker_response={"ok": True},
        observed_at="2026-09-13T19:30:00+00:00",
    ).to_mapping()
    wire["worker_id"] = "codex-pro-02"
    with pytest.raises(RemoteWorkerTransportError, match="identity"):
        RemoteBrokerResponse.from_mapping(wire, expected_request=request)

    wire = RemoteBrokerResponse.build(
        request=request,
        outcome="completed",
        broker_response={"ok": True},
        observed_at="2026-09-13T19:30:00+00:00",
    ).to_mapping()
    wire["endpoint"] = "private.example"
    with pytest.raises(RemoteWorkerTransportError, match="exactly"):
        RemoteBrokerResponse.from_mapping(wire, expected_request=request)


def test_response_rejects_naive_or_invalid_observation_time() -> None:
    request = _request()
    wire = RemoteBrokerResponse.build(
        request=request,
        outcome="completed",
        broker_response={"ok": True},
        observed_at="2026-09-13T19:30:00Z",
    ).to_mapping()
    wire["observed_at"] = "2026-09-13T19:30:00"
    with pytest.raises(RemoteWorkerTransportError, match="timezone"):
        RemoteBrokerResponse.from_mapping(wire, expected_request=request)


def test_transport_binding_is_local_only_and_strict() -> None:
    binding = BrokerTransportBinding(
        host_ref=HOST_REF,
        endpoint_host="worker-1.tailnet.ts.net",
        endpoint_port=9443,
        expected_server_certificate_sha256="a" * 64,
        client_certificate_path=Path("/var/db/mastermind/tls/client.crt"),
        client_private_key_path=Path("/var/db/mastermind/tls/client.key"),
        ca_certificate_path=Path("/var/db/mastermind/tls/ca.crt"),
        timeout_seconds=15.0,
    )
    assert binding.host_ref == HOST_REF
    assert "client.key" not in repr(binding)
    assert "worker-1.tailnet.ts.net" not in repr(binding)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"endpoint_host": "https://worker.example"},
        {"endpoint_port": 0},
        {"expected_server_certificate_sha256": "not-a-digest"},
        {"client_certificate_path": Path("relative/client.crt")},
        {"client_private_key_path": Path("relative/client.key")},
        {"ca_certificate_path": Path("relative/ca.crt")},
        {"timeout_seconds": 0.0},
    ],
)
def test_transport_binding_rejects_unsafe_values(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "host_ref": HOST_REF,
        "endpoint_host": "worker-1.tailnet.ts.net",
        "endpoint_port": 9443,
        "expected_server_certificate_sha256": "a" * 64,
        "client_certificate_path": Path("/var/db/mastermind/tls/client.crt"),
        "client_private_key_path": Path("/var/db/mastermind/tls/client.key"),
        "ca_certificate_path": Path("/var/db/mastermind/tls/ca.crt"),
        "timeout_seconds": 15.0,
    }
    values.update(kwargs)
    with pytest.raises(RemoteWorkerTransportError):
        BrokerTransportBinding(**values)  # type: ignore[arg-type]
