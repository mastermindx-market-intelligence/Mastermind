from __future__ import annotations

import asyncio
import hashlib
import json
import ssl
import struct
from pathlib import Path
from typing import Any

import pytest

from control_plane.remote_worker_broker_client import (
    RemoteBrokerAuthenticationError,
    RemoteBrokerEffectUnknownError,
    RemoteBrokerUnavailableError,
    RemoteWorkerBrokerClient,
)
from control_plane.remote_worker_transport import (
    BrokerTransportBinding,
    RemoteBrokerResponse,
)


JOB_ID = "JOB-901"
ATTEMPT_ID = "ATT-" + "a" * 32
WORKER_ID = "codex-pro-01"
HOST_REF = "host-studio"
SERVER_DER = b"server-cert-der"


def _binding() -> BrokerTransportBinding:
    return BrokerTransportBinding(
        host_ref=HOST_REF,
        endpoint_host="studio.mesh.test",
        endpoint_port=9443,
        expected_server_certificate_sha256=hashlib.sha256(SERVER_DER).hexdigest(),
        client_certificate_path=Path("/tmp/client.crt"),
        client_private_key_path=Path("/tmp/client.key"),
        ca_certificate_path=Path("/tmp/ca.crt"),
        timeout_seconds=3,
    )


def _client() -> RemoteWorkerBrokerClient:
    return RemoteWorkerBrokerClient(
        _binding(),
        job_id=JOB_ID,
        attempt_id=ATTEMPT_ID,
        worker_id=WORKER_ID,
    )


def _start_payload(*, prompt: str = "do work") -> dict[str, Any]:
    return {
        "launch_spec": {
            "run_id": ATTEMPT_ID,
            "job_id": JOB_ID,
            "worker_id": WORKER_ID,
            "prompt": prompt,
        },
        "validation_commands": [],
    }


class _FakeSSLObject:
    def __init__(self, peer_der: bytes = SERVER_DER) -> None:
        self.peer_der = peer_der

    def getpeercert(self, *, binary_form: bool = False) -> bytes | dict[str, Any]:
        if binary_form:
            return self.peer_der
        return {}


class _FakeReader:
    def __init__(self, response: bytes = b"") -> None:
        self.response = response
        self.offset = 0

    async def readexactly(self, count: int) -> bytes:
        end = self.offset + count
        if end > len(self.response):
            partial = self.response[self.offset :]
            self.offset = len(self.response)
            raise asyncio.IncompleteReadError(partial=partial, expected=count)
        result = self.response[self.offset : end]
        self.offset = end
        return result


class _FakeWriter:
    def __init__(self, *, peer_der: bytes = SERVER_DER, drain_error: Exception | None = None) -> None:
        self.ssl_object = _FakeSSLObject(peer_der)
        self.drain_error = drain_error
        self.writes: list[bytes] = []
        self.closed = False

    def get_extra_info(self, name: str) -> Any:
        if name == "ssl_object":
            return self.ssl_object
        return None

    def write(self, data: bytes) -> None:
        self.writes.append(bytes(data))

    async def drain(self) -> None:
        if self.drain_error is not None:
            raise self.drain_error

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


def _frame_response(client: RemoteWorkerBrokerClient, operation: str, payload: dict[str, Any]) -> bytes:
    request = client._build_remote_request(operation, payload)
    broker_response = {
        "schema_version": "mastermind.executive_worker_broker_response/v1",
        "request_id": request.broker_request["request_id"],
        "operation": operation,
        "ok": True,
        "result": {"ok": "remote"},
    }
    response = RemoteBrokerResponse.build(
        request=request,
        outcome="completed",
        broker_response=broker_response,
        observed_at="2026-09-13T19:00:00Z",
    )
    body = json.dumps(
        response.to_mapping(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return struct.pack("!I", len(body)) + body


def _patch_success(monkeypatch: pytest.MonkeyPatch, client: RemoteWorkerBrokerClient, operation: str, payload: dict[str, Any]) -> _FakeWriter:
    reader = _FakeReader(_frame_response(client, operation, payload))
    writer = _FakeWriter()

    async def open_connection(*args: Any, **kwargs: Any) -> tuple[_FakeReader, _FakeWriter]:
        return reader, writer

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    monkeypatch.setattr(client, "_build_ssl_context", lambda: ssl.create_default_context())
    return writer


def test_client_binds_one_exact_remote_attempt() -> None:
    with pytest.raises(Exception):
        RemoteWorkerBrokerClient(
            _binding(), job_id="", attempt_id=ATTEMPT_ID, worker_id=WORKER_ID
        )
    with pytest.raises(Exception):
        RemoteWorkerBrokerClient(
            _binding(), job_id=JOB_ID, attempt_id="ATT-bad", worker_id=WORKER_ID
        )
    with pytest.raises(Exception):
        RemoteWorkerBrokerClient(
            _binding(), job_id=JOB_ID, attempt_id=ATTEMPT_ID, worker_id=""
        )


def test_payload_identity_drift_refuses_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    calls = 0

    async def open_connection(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        raise AssertionError("network must not be reached")

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    payload = _start_payload()
    payload["launch_spec"]["worker_id"] = "other-worker"
    with pytest.raises(Exception):
        client.request_sync("start", payload)
    assert calls == 0


def test_successful_remote_call_returns_existing_broker_result(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    payload = {"run_id": ATTEMPT_ID, "fresh_uid_sweep": False}
    writer = _patch_success(monkeypatch, client, "status", payload)
    assert client.request_sync("status", payload) == {"ok": "remote"}
    assert len(writer.writes) == 1
    assert writer.closed is True


def test_connect_failure_before_write_is_no_effect_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    calls = 0

    async def open_connection(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        raise OSError("offline")

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    monkeypatch.setattr(client, "_build_ssl_context", lambda: ssl.create_default_context())
    with pytest.raises(RemoteBrokerUnavailableError):
        client.request_sync("start", _start_payload())
    assert calls == 1


def test_request_write_failure_is_effect_unknown_for_modifying_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    writer = _FakeWriter(drain_error=OSError("link lost"))

    async def open_connection(*args: Any, **kwargs: Any) -> tuple[_FakeReader, _FakeWriter]:
        return _FakeReader(), writer

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    monkeypatch.setattr(client, "_build_ssl_context", lambda: ssl.create_default_context())
    with pytest.raises(RemoteBrokerEffectUnknownError):
        client.request_sync("start", _start_payload())
    assert len(writer.writes) == 1


def test_response_loss_is_effect_unknown_and_never_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    writer = _FakeWriter()
    calls = 0

    async def open_connection(*args: Any, **kwargs: Any) -> tuple[_FakeReader, _FakeWriter]:
        nonlocal calls
        calls += 1
        return _FakeReader(), writer

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    monkeypatch.setattr(client, "_build_ssl_context", lambda: ssl.create_default_context())
    with pytest.raises(RemoteBrokerEffectUnknownError):
        client.request_sync("start", _start_payload())
    assert calls == 1
    assert len(writer.writes) == 1


def test_response_loss_for_read_is_unavailable_not_effect_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    writer = _FakeWriter()

    async def open_connection(*args: Any, **kwargs: Any) -> tuple[_FakeReader, _FakeWriter]:
        return _FakeReader(), writer

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    monkeypatch.setattr(client, "_build_ssl_context", lambda: ssl.create_default_context())
    with pytest.raises(RemoteBrokerUnavailableError):
        client.request_sync("status", {"run_id": ATTEMPT_ID, "fresh_uid_sweep": False})


def test_server_fingerprint_mismatch_refuses_before_request_write(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    writer = _FakeWriter(peer_der=b"wrong-server")

    async def open_connection(*args: Any, **kwargs: Any) -> tuple[_FakeReader, _FakeWriter]:
        return _FakeReader(), writer

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    monkeypatch.setattr(client, "_build_ssl_context", lambda: ssl.create_default_context())
    with pytest.raises(RemoteBrokerAuthenticationError):
        client.request_sync("start", _start_payload())
    assert writer.writes == []


def test_same_legacy_modification_key_rejects_changed_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    calls = 0

    async def open_connection(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        raise OSError("offline")

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    monkeypatch.setattr(client, "_build_ssl_context", lambda: ssl.create_default_context())
    with pytest.raises(RemoteBrokerUnavailableError):
        client.request_sync("start", _start_payload(prompt="first"))
    with pytest.raises(Exception, match="changed|reused|different"):
        client.request_sync("start", _start_payload(prompt="second"))
    assert calls == 1


def test_read_operations_may_use_distinct_payload_bound_operation_ids() -> None:
    client = _client()
    first = client._build_remote_request(
        "status", {"run_id": ATTEMPT_ID, "fresh_uid_sweep": False}
    )
    second = client._build_remote_request(
        "status", {"run_id": ATTEMPT_ID, "fresh_uid_sweep": True}
    )
    assert first.operation_id != second.operation_id
