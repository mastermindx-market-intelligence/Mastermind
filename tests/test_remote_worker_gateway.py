from __future__ import annotations

import asyncio
import json
import struct
from pathlib import Path
from typing import Any

import pytest

import ops.executive_os.remote_worker_gateway as gateway_module
from control_plane.executive_worker_broker import (
    BROKER_REQUEST_SCHEMA_VERSION,
    BrokerProtocolError,
    RemoteBrokerError,
)
from control_plane.remote_worker_transport import (
    RemoteBrokerRequest,
    RemoteBrokerResponse,
    RemoteWorkerTransportError,
    canonical_json_bytes,
)
from ops.executive_os.remote_worker_gateway import (
    GatewayAuthenticationError,
    GatewayBindingError,
    GatewayProtocolError,
    RemoteWorkerGateway,
    RemoteWorkerGatewayError,
    _read_frame,
    build_server_ssl_context,
)
from ops.executive_os.remote_worker_gateway_config import (
    GATEWAY_CONFIG_SCHEMA,
    RemoteWorkerGatewayConfig,
    RemoteWorkerGatewayConfigError,
)


HOST_REF = "host-01234567"
JOB_ID = "JOB-321"
ATTEMPT_ID = "ATT-0123456789abcdef0123456789abcdef"
WORKER_ID = "codex-pro-01"
PEER_CERT = b"control-client-certificate-der"
PEER_SHA = __import__("hashlib").sha256(PEER_CERT).hexdigest()
_FRAME = struct.Struct("!I")


def _config(**overrides: Any) -> RemoteWorkerGatewayConfig:
    values: dict[str, Any] = {
        "schema": GATEWAY_CONFIG_SCHEMA,
        "host_ref": HOST_REF,
        "listen_host": "100.83.4.23",
        "listen_port": 9443,
        "server_certificate_path": Path("/var/db/mastermind/tls/server.crt"),
        "server_private_key_path": Path("/var/db/mastermind/tls/server.key"),
        "ca_certificate_path": Path("/var/db/mastermind/tls/ca.crt"),
        "expected_control_client_certificate_sha256": PEER_SHA,
        "worker_broker_socket_path": Path(
            "/var/run/mastermind-executive/worker-codex-pro-01.sock"
        ),
        "allowed_worker_ids": (WORKER_ID,),
        "max_request_bytes": 2 * 1024 * 1024,
        "max_response_bytes": 4 * 1024 * 1024,
        "read_timeout_seconds": 3.0,
        "local_broker_timeout_seconds": 3.0,
    }
    values.update(overrides)
    return RemoteWorkerGatewayConfig(**values)


def _broker_request(
    operation: str = "status",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": BROKER_REQUEST_SCHEMA_VERSION,
        "request_id": "req-0123456789abcdef",
        "operation": operation,
        "payload": payload if payload is not None else {"run_id": ATTEMPT_ID},
    }


def _request(
    *,
    operation: str = "status",
    host_ref: str = HOST_REF,
    worker_id: str = WORKER_ID,
    operation_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> RemoteBrokerRequest:
    return RemoteBrokerRequest.build(
        host_ref=host_ref,
        job_id=JOB_ID,
        attempt_id=ATTEMPT_ID,
        worker_id=worker_id,
        operation_id=(
            operation_id or f"mh1-op:{ATTEMPT_ID}:{operation}"
        ),
        broker_operation=operation,
        broker_request=_broker_request(operation, payload),
    )


def _start_request(*, job_id: str = JOB_ID, worker_id: str = WORKER_ID) -> RemoteBrokerRequest:
    payload = {
        "launch_spec": {
            "run_id": ATTEMPT_ID,
            "job_id": job_id,
            "worker_id": worker_id,
        },
        "validation_commands": [],
    }
    return _request(operation="start", worker_id=WORKER_ID, payload=payload)


class _FakeSSLObject:
    def __init__(self, certificate: bytes | None) -> None:
        self.certificate = certificate

    def getpeercert(self, *, binary_form: bool = False) -> bytes | None:
        assert binary_form is True
        return self.certificate


class _FakeWriter:
    def __init__(self, certificate: bytes | None = PEER_CERT) -> None:
        self.ssl_object = _FakeSSLObject(certificate)
        self.buffer = bytearray()
        self.closed = False

    def get_extra_info(self, name: str) -> object | None:
        return self.ssl_object if name == "ssl_object" else None

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


async def _run_handler(
    gateway: RemoteWorkerGateway,
    request: RemoteBrokerRequest,
    writer: _FakeWriter,
) -> None:
    payload = canonical_json_bytes(request.to_mapping())
    reader = asyncio.StreamReader()
    reader.feed_data(_FRAME.pack(len(payload)) + payload)
    reader.feed_eof()
    await gateway.handle_connection(reader, writer)


def _decode_written_response(writer: _FakeWriter) -> dict[str, Any]:
    assert len(writer.buffer) >= _FRAME.size
    (size,) = _FRAME.unpack(bytes(writer.buffer[: _FRAME.size]))
    payload = bytes(writer.buffer[_FRAME.size :])
    assert len(payload) == size
    value = json.loads(payload.decode("utf-8"))
    assert isinstance(value, dict)
    return value


def test_gateway_config_is_closed_and_cannot_bind_wildcard_interface() -> None:
    raw = {
        "schema": GATEWAY_CONFIG_SCHEMA,
        "host_ref": HOST_REF,
        "listen_host": "100.83.4.23",
        "listen_port": 9443,
        "server_certificate_path": "/var/db/mastermind/tls/server.crt",
        "server_private_key_path": "/var/db/mastermind/tls/server.key",
        "ca_certificate_path": "/var/db/mastermind/tls/ca.crt",
        "expected_control_client_certificate_sha256": PEER_SHA,
        "worker_broker_socket_path": (
            "/var/run/mastermind-executive/worker-codex-pro-01.sock"
        ),
        "allowed_worker_ids": [WORKER_ID],
        "max_request_bytes": 2 * 1024 * 1024,
        "max_response_bytes": 4 * 1024 * 1024,
        "read_timeout_seconds": 3.0,
        "local_broker_timeout_seconds": 3.0,
    }
    config = RemoteWorkerGatewayConfig.from_mapping(raw)
    assert config.worker_broker_socket_path == Path(
        "/var/run/mastermind-executive/worker-codex-pro-01.sock"
    )
    raw["extra_socket"] = "/tmp/evil.sock"
    with pytest.raises(RemoteWorkerGatewayConfigError, match="exactly"):
        RemoteWorkerGatewayConfig.from_mapping(raw)
    with pytest.raises(RemoteWorkerGatewayConfigError, match="private interface"):
        _config(listen_host="0.0.0.0")


def test_gateway_config_hides_private_key_and_client_fingerprint_from_repr() -> None:
    rendered = repr(_config())
    assert "server.key" not in rendered
    assert PEER_SHA not in rendered


def test_server_tls_context_requires_verified_client_certificate(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, Any] = {}

    class FakeContext:
        def __init__(self, protocol: object) -> None:
            observed["protocol"] = protocol
            self.minimum_version = None
            self.verify_mode = None
            self.check_hostname = None

        def load_cert_chain(self, *, certfile: str, keyfile: str) -> None:
            observed["certfile"] = certfile
            observed["keyfile"] = keyfile

        def load_verify_locations(self, *, cafile: str) -> None:
            observed["cafile"] = cafile

    monkeypatch.setattr(gateway_module.ssl, "SSLContext", FakeContext)
    context = build_server_ssl_context(_config())
    assert context.verify_mode == gateway_module.ssl.CERT_REQUIRED
    assert context.check_hostname is False
    assert observed["cafile"] == "/var/db/mastermind/tls/ca.crt"
    assert observed["keyfile"] == "/var/db/mastermind/tls/server.key"


def test_wrong_client_fingerprint_is_refused_before_broker() -> None:
    gateway = RemoteWorkerGateway(_config())
    with pytest.raises(GatewayAuthenticationError, match="certificate identity"):
        asyncio.run(
            gateway.process_request(
                _request(),
                peer_certificate_der=b"wrong-client-certificate",
            )
        )


def test_missing_client_certificate_produces_no_gateway_response() -> None:
    gateway = RemoteWorkerGateway(_config())
    writer = _FakeWriter(certificate=None)
    asyncio.run(_run_handler(gateway, _request(), writer))
    assert writer.closed is True
    assert writer.buffer == b""


def test_host_and_worker_binding_fail_before_local_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = RemoteWorkerGateway(_config())
    calls = 0

    async def should_not_forward(_request: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise AssertionError("local broker must not be reached")

    monkeypatch.setattr(gateway, "_forward_local", should_not_forward)
    with pytest.raises(GatewayBindingError, match="host_ref"):
        asyncio.run(
            gateway.process_request(
                _request(host_ref="host-87654321"),
                peer_certificate_der=PEER_CERT,
            )
        )
    with pytest.raises(GatewayBindingError, match="worker_id"):
        asyncio.run(
            gateway.process_request(
                _request(worker_id="codex-pro-02"),
                peer_certificate_der=PEER_CERT,
            )
        )
    assert calls == 0


def test_unknown_broker_operation_is_refused_before_local_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = RemoteWorkerGateway(_config())
    called = False

    async def should_not_forward(_request: dict[str, Any]) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("local broker must not be reached")

    monkeypatch.setattr(gateway, "_forward_local", should_not_forward)
    with pytest.raises(GatewayProtocolError, match="not allowed"):
        asyncio.run(
            gateway.process_request(
                _request(operation="shell"),
                peer_certificate_der=PEER_CERT,
            )
        )
    assert called is False


def test_start_identity_mismatch_is_refused_before_local_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = RemoteWorkerGateway(_config())
    called = False

    async def should_not_forward(_request: dict[str, Any]) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("local broker must not be reached")

    monkeypatch.setattr(gateway, "_forward_local", should_not_forward)
    with pytest.raises(GatewayBindingError, match="launch_spec job_id"):
        asyncio.run(
            gateway.process_request(
                _start_request(job_id="JOB-999"),
                peer_certificate_der=PEER_CERT,
            )
        )
    assert called is False


def test_hash_mismatch_is_rejected_by_remote_envelope() -> None:
    wire = _request().to_mapping()
    wire["request_sha256"] = "0" * 64
    with pytest.raises(RemoteWorkerTransportError, match="hash"):
        RemoteBrokerRequest.from_mapping(wire)


def test_oversized_frame_is_refused_without_reading_body() -> None:
    async def exercise() -> None:
        reader = asyncio.StreamReader()
        reader.feed_data(_FRAME.pack(4097))
        reader.feed_eof()
        await _read_frame(reader, max_bytes=4096, timeout=1.0)

    with pytest.raises(GatewayProtocolError, match="frame size"):
        asyncio.run(exercise())


def test_malformed_json_is_deterministically_refused_after_peer_auth() -> None:
    writer = _FakeWriter()

    async def exercise() -> None:
        reader = asyncio.StreamReader()
        raw = b"{not-json"
        reader.feed_data(_FRAME.pack(len(raw)) + raw)
        reader.feed_eof()
        await RemoteWorkerGateway(_config()).handle_connection(reader, writer)

    asyncio.run(exercise())
    assert writer.closed is True
    assert writer.buffer == b""


def test_pre_effect_binding_failure_returns_gateway_refusal() -> None:
    gateway = RemoteWorkerGateway(_config())
    request = _request(host_ref="host-87654321")
    writer = _FakeWriter()
    asyncio.run(_run_handler(gateway, request, writer))
    response = RemoteBrokerResponse.from_mapping(
        _decode_written_response(writer),
        expected_request=request,
    )
    assert response.outcome == "gateway_refused"
    assert response.broker_response["ok"] is False


def test_local_broker_client_uses_only_configured_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Any] = {}

    class FakeClient:
        def __init__(
            self,
            socket_path: Path,
            *,
            timeout_seconds: float,
            max_response_bytes: int,
        ) -> None:
            observed["socket_path"] = Path(socket_path)
            observed["timeout"] = timeout_seconds
            observed["max_response_bytes"] = max_response_bytes

        async def request(
            self,
            operation: str,
            payload: dict[str, Any],
            *,
            timeout_seconds: float,
        ) -> dict[str, Any]:
            observed["operation"] = operation
            observed["payload"] = payload
            return {"state": "RUNNING"}

    monkeypatch.setattr(gateway_module, "WorkerBrokerClient", FakeClient)
    gateway = RemoteWorkerGateway(_config())
    request = _request(
        payload={
            "run_id": ATTEMPT_ID,
            "socket_path": "/tmp/request-controlled.sock",
        }
    )
    response = asyncio.run(
        gateway.process_request(request, peer_certificate_der=PEER_CERT)
    )
    assert observed["socket_path"] == Path(
        "/var/run/mastermind-executive/worker-codex-pro-01.sock"
    )
    assert observed["socket_path"] != Path("/tmp/request-controlled.sock")
    assert response.outcome == "completed"


def test_typed_broker_effect_unknown_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def request(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            raise RemoteBrokerError(
                "BrokerEffectUnknownError",
                "provider effect may have begun",
            )

    monkeypatch.setattr(gateway_module, "WorkerBrokerClient", FakeClient)
    response = asyncio.run(
        RemoteWorkerGateway(_config()).process_request(
            _request(),
            peer_certificate_der=PEER_CERT,
        )
    )
    assert response.outcome == "effect_unknown"
    assert response.broker_response["error"]["code"] == "BrokerEffectUnknownError"


def test_unknown_local_broker_outcome_propagates_once_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def request(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            raise BrokerProtocolError("broker closed after request write")

    monkeypatch.setattr(gateway_module, "WorkerBrokerClient", FakeClient)
    with pytest.raises(RemoteWorkerGatewayError, match="outcome is unavailable"):
        asyncio.run(
            RemoteWorkerGateway(_config()).process_request(
                _request(),
                peer_certificate_der=PEER_CERT,
            )
        )
    assert calls == 1


def test_connection_closes_without_response_when_local_effect_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = RemoteWorkerGateway(_config())
    calls = 0

    async def unknown(_request: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise RemoteWorkerGatewayError("local Worker Broker outcome is unavailable")

    monkeypatch.setattr(gateway, "_forward_local", unknown)
    writer = _FakeWriter()
    asyncio.run(_run_handler(gateway, _request(), writer))
    assert calls == 1
    assert writer.closed is True
    assert writer.buffer == b""


def test_gateway_restart_requires_no_history_or_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def status(_request: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": gateway_module.BROKER_RESPONSE_SCHEMA_VERSION,
            "request_id": "req-local",
            "operation": "status",
            "ok": True,
            "result": {"state": "RUNNING"},
        }

    first = RemoteWorkerGateway(_config())
    second = RemoteWorkerGateway(_config())
    monkeypatch.setattr(first, "_forward_local", status)
    monkeypatch.setattr(second, "_forward_local", status)

    first_response = asyncio.run(
        first.process_request(
            _request(operation_id=f"mh1-op:{ATTEMPT_ID}:status-a"),
            peer_certificate_der=PEER_CERT,
        )
    )
    second_response = asyncio.run(
        second.process_request(
            _request(operation_id=f"mh1-op:{ATTEMPT_ID}:status-b"),
            peer_certificate_der=PEER_CERT,
        )
    )
    assert first_response.outcome == "completed"
    assert second_response.outcome == "completed"
    assert set(vars(first)) - {"config", "_forward_local"} == set()
    assert set(vars(second)) - {"config", "_forward_local"} == set()
