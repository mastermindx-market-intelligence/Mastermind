from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from control_plane.executive_worker_broker import WorkerBrokerClient
from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from control_plane.remote_worker_transport import (
    REMOTE_BROKER_RESPONSE_SCHEMA,
    BrokerTransportBinding,
    TransportEffect,
    TransportError,
    TransportValidationError,
    build_request,
    encode_frame,
)
from tests.test_remote_worker_gateway import (
    _cert_sha256,
    _close_gateway,
    _gateway_fixture,
    _openssl_available,
)
from tests.test_remote_worker_transport import HOST_REF, IDENTITY

pytestmark = pytest.mark.anyio

_PEER_CERT = b"peer-certificate-der"
_BOUND_PAYLOAD_IDENTITY = {
    "session_epoch_id": "EPOCH-001",
    "process_generation_id": "GEN-001",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class _Paths:
    ca: Path
    cert: Path
    key: Path


@pytest.fixture
def paths(tmp_path: Path) -> _Paths:
    for name in ("ca.pem", "client.pem", "client.key"):
        (tmp_path / name).write_bytes(b"fixture")
    return _Paths(tmp_path / "ca.pem", tmp_path / "client.pem", tmp_path / "client.key")


def _binding(
    paths: _Paths,
    *,
    fingerprint: str | None = None,
    endpoint: tuple[str, int] = ("127.0.0.1", 7443),
) -> BrokerTransportBinding:
    return BrokerTransportBinding(
        endpoint=endpoint,
        ca_path=paths.ca,
        client_cert_path=paths.cert,
        client_key_path=paths.key,
        expected_server_fingerprint=(
            fingerprint or hashlib.sha256(_PEER_CERT).hexdigest()
        ),
    )


def _client(paths: _Paths) -> RemoteWorkerBrokerClient:
    return RemoteWorkerBrokerClient(
        _binding(paths),
        IDENTITY,
        allowed_operations={
            "status",
            "start",
            "ohf-validate",
            "ohf-start",
            "ohf-read-events",
            "ohf-deliver-attention",
        },
    )


def _response(
    request: dict,
    *,
    outcome: str = "ok",
    broker_response: dict | None = None,
    **overrides: object,
) -> dict:
    response = {
        "schema": REMOTE_BROKER_RESPONSE_SCHEMA,
        "host_ref": request["host_ref"],
        "job_id": request["job_id"],
        "attempt_id": request["attempt_id"],
        "worker_id": request["worker_id"],
        "operation_id": request["operation_id"],
        "broker_operation": request["broker_operation"],
        "request_sha256": request["request_sha256"],
        "outcome": outcome,
        "broker_response": broker_response,
        "observed_at_ms": 1,
    }
    response.update(overrides)
    return response


def _frame(document: dict) -> bytes:
    encoded = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return encode_frame(encoded)


class _SSLObject:
    def __init__(self, certificate: bytes = _PEER_CERT) -> None:
        self.certificate = certificate

    def getpeercert(self, binary_form: bool = False) -> bytes | dict:
        if binary_form:
            return self.certificate
        return {}


class _Writer:
    def __init__(
        self,
        *,
        certificate: bytes = _PEER_CERT,
        fail_write: bool = False,
        fail_drain: bool = False,
    ) -> None:
        self.ssl_object = _SSLObject(certificate)
        self.fail_write = fail_write
        self.fail_drain = fail_drain
        self.written = bytearray()
        self.closed = False

    def get_extra_info(self, name: str) -> object | None:
        return self.ssl_object if name == "ssl_object" else None

    def write(self, data: bytes) -> None:
        if self.fail_write:
            raise OSError("private partial write")
        self.written.extend(data)

    async def drain(self) -> None:
        if self.fail_drain:
            raise OSError("private drain failure")

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data

    async def readexactly(self, count: int) -> bytes:
        if count > len(self.data):
            partial = self.data
            self.data = b""
            raise asyncio.IncompleteReadError(partial, count)
        value = self.data[:count]
        self.data = self.data[count:]
        return value


async def test_pre_write_connect_failure_is_no_effect(paths: _Paths) -> None:
    client = _client(paths)
    attempts = 0

    async def unavailable() -> object:
        nonlocal attempts
        attempts += 1
        raise OSError("private endpoint /secret.sock")

    client._open_connection = unavailable
    with pytest.raises(TransportError) as raised:
        await client.request("start", {"run_id": "ATT-001"})
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert attempts == 1
    assert "private" not in str(raised.value)


@pytest.mark.parametrize("failure", ["write", "drain", "lost-response", "invalid-response"])
async def test_modifying_post_write_uncertainty_is_effect_unknown_and_zero_retry(
    paths: _Paths, failure: str
) -> None:
    client = _client(paths)
    calls = 0
    writer = _Writer(fail_write=failure == "write", fail_drain=failure == "drain")
    reader_data = b""
    if failure == "invalid-response":
        reader_data = encode_frame(b"not-json")

    async def exchange() -> object:
        nonlocal calls
        calls += 1
        return _Reader(reader_data), writer

    client._open_connection = exchange
    with pytest.raises(TransportError) as raised:
        await client.request("start", {"run_id": "ATT-001"})
    assert raised.value.classification is TransportEffect.EFFECT_UNKNOWN
    assert calls == 1
    assert "private" not in str(raised.value)


async def test_read_only_post_write_loss_is_no_effect_and_zero_retry(paths: _Paths) -> None:
    client = _client(paths)
    calls = 0

    async def exchange() -> object:
        nonlocal calls
        calls += 1
        return _Reader(b""), _Writer()

    client._open_connection = exchange
    with pytest.raises(TransportError) as raised:
        await client.request("status", {"run_id": "ATT-001"})
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert calls == 1


@pytest.mark.parametrize(
    ("operation", "payload"),
    [
        ("validate", {"run_id": "ATT-001", "argv": ["true"], "timeout_seconds": 1}),
        ("ohf-validate", {"requested": {}}),
        ("ohf-reconcile-absence", {}),
        ("status", {"fresh_uid_sweep": True}),
    ],
)
async def test_effectful_broker_operations_become_effect_unknown_after_write(
    paths: _Paths, operation: str, payload: dict
) -> None:
    client = RemoteWorkerBrokerClient(
        _binding(paths),
        IDENTITY,
        allowed_operations={operation},
    )
    calls = 0

    async def exchange() -> object:
        nonlocal calls
        calls += 1
        return _Reader(b""), _Writer()

    client._open_connection = exchange
    with pytest.raises(TransportError) as raised:
        await client.request(operation, payload)
    assert raised.value.classification is TransportEffect.EFFECT_UNKNOWN
    assert calls == 1


async def test_generation_identity_requires_explicit_binding(paths: _Paths) -> None:
    client = RemoteWorkerBrokerClient(
        _binding(paths),
        IDENTITY,
        allowed_operations={"ohf-reconcile"},
    )
    called = False

    async def should_not_connect() -> object:
        nonlocal called
        called = True
        raise AssertionError("network must not be reached")

    client._open_connection = should_not_connect
    payload = {
        "generation": {
            "process_generation_id": "GEN-001",
            "session_epoch_id": "EPOCH-001",
            "generation_number": 1,
            "worker_id": IDENTITY["worker_id"],
        }
    }
    with pytest.raises(TransportError) as raised:
        await client.request("ohf-reconcile", payload)
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert raised.value.code == "payload_identity_override"
    assert called is False


async def test_generation_identity_cannot_retarget_bound_generation(paths: _Paths) -> None:
    client = RemoteWorkerBrokerClient(
        _binding(paths),
        IDENTITY,
        allowed_operations={"ohf-cancel"},
        bound_payload_identity=_BOUND_PAYLOAD_IDENTITY,
    )
    called = False

    async def should_not_connect() -> object:
        nonlocal called
        called = True
        raise AssertionError("network must not be reached")

    client._open_connection = should_not_connect
    payload = {
        "generation": {
            "process_generation_id": "GEN-OTHER",
            "session_epoch_id": "EPOCH-001",
            "generation_number": 1,
            "worker_id": IDENTITY["worker_id"],
        },
        "operation_id": {"command_id": "CMD-001"},
        "reason": "bounded cancel",
    }
    with pytest.raises(TransportError) as raised:
        await client.request("ohf-cancel", payload)
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert raised.value.code == "payload_identity_override"
    assert called is False


async def test_bound_reconcile_post_write_loss_is_effect_unknown(paths: _Paths) -> None:
    client = RemoteWorkerBrokerClient(
        _binding(paths),
        IDENTITY,
        allowed_operations={"ohf-reconcile"},
        bound_payload_identity=_BOUND_PAYLOAD_IDENTITY,
    )
    payload = {
        "generation": {
            "process_generation_id": "GEN-001",
            "session_epoch_id": "EPOCH-001",
            "generation_number": 1,
            "worker_id": IDENTITY["worker_id"],
        }
    }

    async def exchange() -> object:
        return _Reader(b""), _Writer()

    client._open_connection = exchange
    with pytest.raises(TransportError) as raised:
        await client.request("ohf-reconcile", payload)
    assert raised.value.classification is TransportEffect.EFFECT_UNKNOWN


async def test_server_pin_mismatch_refuses_before_any_request_bytes(paths: _Paths) -> None:
    client = RemoteWorkerBrokerClient(
        _binding(paths, fingerprint="0" * 64),
        IDENTITY,
        allowed_operations={"start"},
    )
    writer = _Writer()

    async def exchange() -> object:
        return _Reader(b""), writer

    client._open_connection = exchange
    with pytest.raises(TransportError) as raised:
        await client.request("start", {"run_id": "ATT-001"})
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert raised.value.code == "server_identity_mismatch"
    assert writer.written == b""


@pytest.mark.parametrize(
    "payload",
    [
        {"job_id": "JOB-002"},
        {"nested": {"worker_id": "WORKER-002"}},
        {"items": [{"host_ref": "b" * 64}]},
        {"attempt_id": "ATT-002"},
        {"run_id": "ATT-002"},
    ],
)
async def test_payload_cannot_retarget_bound_authority(paths: _Paths, payload: dict) -> None:
    client = _client(paths)
    called = False

    async def should_not_connect() -> object:
        nonlocal called
        called = True
        raise AssertionError("network must not be reached")

    client._open_connection = should_not_connect
    with pytest.raises(TransportError) as raised:
        await client.request("status", payload)
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert raised.value.code == "payload_identity_override"
    assert called is False


async def test_adapter_identity_echo_and_operation_id_payload_are_allowed_when_bound(
    paths: _Paths,
) -> None:
    client = _client(paths)
    payload = {
        "attempt_id": IDENTITY["attempt_id"],
        "operation_id": {"provider_operation_id": "P-001"},
        "instruction": "continue exact task",
    }
    request = build_request(IDENTITY, "ohf-deliver-attention", payload)
    writer = _Writer()

    async def exchange() -> object:
        return _Reader(
            _frame(_response(request, broker_response={"observation": {"accepted": True}}))
        ), writer

    client._open_connection = exchange
    result = await client.request("ohf-deliver-attention", payload)
    assert result == {"observation": {"accepted": True}}


async def test_unknown_operation_is_refused_before_network(paths: _Paths) -> None:
    client = _client(paths)
    with pytest.raises(TransportError) as raised:
        await client.request("collect", {"run_id": "ATT-001"})
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert raised.value.code == "operation_not_allowed"


async def test_bound_response_identity_drift_hides_broker_payload(paths: _Paths) -> None:
    client = _client(paths)
    request = build_request(IDENTITY, "status", {"run_id": "ATT-001"})
    response = _response(
        request,
        broker_response={"secret": "broker-payload"},
        worker_id="WORKER-002",
    )

    async def exchange() -> object:
        return _Reader(_frame(response)), _Writer()

    client._open_connection = exchange
    with pytest.raises(TransportError) as raised:
        await client.request("status", {"run_id": "ATT-001"})
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert "broker-payload" not in str(raised.value)


async def test_remote_refusal_is_no_effect_even_for_modifying_operation(paths: _Paths) -> None:
    client = _client(paths)
    request = build_request(IDENTITY, "start", {"run_id": "ATT-001"})

    async def exchange() -> object:
        return _Reader(_frame(_response(request, outcome="refused"))), _Writer()

    client._open_connection = exchange
    with pytest.raises(TransportError) as raised:
        await client.request("start", {"run_id": "ATT-001"})
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert raised.value.code == "refused"


async def test_remote_error_after_modifying_forward_is_effect_unknown(paths: _Paths) -> None:
    client = _client(paths)
    request = build_request(IDENTITY, "ohf-start", {"requested": {}})

    async def exchange() -> object:
        return _Reader(_frame(_response(request, outcome="error"))), _Writer()

    client._open_connection = exchange
    with pytest.raises(TransportError) as raised:
        await client.request("ohf-start", {"requested": {}})
    assert raised.value.classification is TransportEffect.EFFECT_UNKNOWN
    assert raised.value.code == "remote_error"


async def test_read_only_success_returns_only_validated_broker_response(paths: _Paths) -> None:
    client = _client(paths)
    request = build_request(IDENTITY, "status", {"run_id": "ATT-001"})

    async def exchange() -> object:
        return _Reader(
            _frame(_response(request, broker_response={"state": "RUNNING"}))
        ), _Writer()

    client._open_connection = exchange
    result = await client.request("status", {"run_id": "ATT-001"})
    assert result == {"state": "RUNNING"}


def test_client_constructor_refuses_invalid_bound_identity(paths: _Paths) -> None:
    with pytest.raises(TransportValidationError):
        RemoteWorkerBrokerClient(
            _binding(paths),
            {**IDENTITY, "host_ref": "not-a-host-ref"},
            allowed_operations={"status"},
        )


@pytest.mark.skipif(not _openssl_available(), reason="openssl unavailable")
async def test_real_client_crosses_mtls_gateway_to_fixed_broker(tmp_path: Path) -> None:
    fixture = await _gateway_fixture(tmp_path)
    binding = BrokerTransportBinding(
        endpoint=("localhost", fixture.endpoint[1]),
        ca_path=fixture.config.ca_path,
        client_cert_path=fixture.control_cert,
        client_key_path=fixture.control_key,
        expected_server_fingerprint=_cert_sha256(fixture.config.certificate_path),
    )
    client = RemoteWorkerBrokerClient(
        binding,
        IDENTITY,
        allowed_operations={"status"},
    )
    try:
        result = await client.request("status", {"run_id": "ATT-001"})
        assert result == {"worker": "ATT-001"}
    finally:
        await _close_gateway(fixture)


def test_request_sync_structural_seam_matches_existing_worker_client() -> None:
    remote = inspect.signature(RemoteWorkerBrokerClient.request_sync)
    local = inspect.signature(WorkerBrokerClient.request_sync)
    assert tuple(remote.parameters) == tuple(local.parameters)
    assert "timeout_seconds" in remote.parameters


async def test_capacity_observe_post_write_loss_is_no_effect_and_zero_retry(
    paths: _Paths,
) -> None:
    client = RemoteWorkerBrokerClient(
        _binding(paths),
        IDENTITY,
        allowed_operations={"capacity-observe/v1"},
    )
    calls = 0

    async def exchange() -> object:
        nonlocal calls
        calls += 1
        return _Reader(b""), _Writer()

    client._open_connection = exchange
    with pytest.raises(TransportError) as raised:
        await client.request(
            "capacity-observe/v1",
            {
                "schema_version": (
                    "mastermind.executive_worker_capacity_observe_request/v1"
                )
            },
        )
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert calls == 1
