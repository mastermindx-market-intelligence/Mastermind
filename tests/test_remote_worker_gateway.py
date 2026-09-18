from __future__ import annotations

import asyncio
import hashlib
import json
import ssl
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

from control_plane.executive_worker_broker import BROKER_RESPONSE_SCHEMA_VERSION
from control_plane.remote_worker_transport import encode_frame
from ops.executive_os.remote_worker_gateway import RemoteWorkerGateway
from ops.executive_os.remote_worker_gateway_config import (
    REMOTE_WORKER_GATEWAY_CONFIG_SCHEMA,
    RemoteWorkerGatewayConfig,
)
from tests.test_remote_worker_transport import (
    HOST_REF,
    _certificate_fixture,
    _openssl_available,
    _request,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class _GatewayFixture:
    config: RemoteWorkerGatewayConfig
    gateway: RemoteWorkerGateway
    server: asyncio.AbstractServer
    endpoint: tuple[str, int]
    unix_server: asyncio.AbstractServer
    broker_socket: Path
    control_cert: Path
    control_key: Path


def _cert_sha256(path: Path) -> str:
    der = ssl.PEM_cert_to_DER_cert(path.read_text(encoding="utf-8"))
    return hashlib.sha256(der).hexdigest()


async def _fake_broker(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    raw = await reader.readline()
    broker_request = json.loads(raw)
    response = {
        "schema_version": BROKER_RESPONSE_SCHEMA_VERSION,
        "request_id": broker_request["request_id"],
        "operation": broker_request["operation"],
        "ok": True,
        "result": {"worker": broker_request["payload"]["run_id"]},
    }
    writer.write(
        (json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def _gateway_fixture(tmp_path: Path) -> _GatewayFixture:
    ca_key, ca_cert, _ = _certificate_fixture(
        tmp_path,
        name="gateway-ca",
        common_name="Gateway CA",
        san="DNS:ca.invalid",
        ca=True,
    )
    server_key, server_cert, _ = _certificate_fixture(
        tmp_path,
        name="gateway-server",
        common_name="localhost",
        san="DNS:localhost",
        issuer_key=ca_key,
        issuer_cert=ca_cert,
    )
    control_key, control_cert, _ = _certificate_fixture(
        tmp_path,
        name="gateway-control",
        common_name="control",
        san="DNS:control.invalid",
        issuer_key=ca_key,
        issuer_cert=ca_cert,
    )
    broker_socket = Path("/tmp") / f"mh1-{uuid.uuid4().hex[:12]}.sock"
    unix_server = await asyncio.start_unix_server(_fake_broker, path=str(broker_socket))
    config = RemoteWorkerGatewayConfig(
        schema=REMOTE_WORKER_GATEWAY_CONFIG_SCHEMA,
        host_ref=HOST_REF,
        listen_host="127.0.0.1",
        listen_port=0,
        certificate_path=server_cert,
        key_path=server_key,
        ca_path=ca_cert,
        expected_control_fingerprint=_cert_sha256(control_cert),
        broker_socket_path=broker_socket,
        allowed_worker_ids={"WORKER-001"},
        allowed_operations={"status"},
    )
    gateway = RemoteWorkerGateway(config)
    server = await gateway.start_server()
    endpoint = server.sockets[0].getsockname()[:2]
    return _GatewayFixture(
        config=config,
        gateway=gateway,
        server=server,
        endpoint=(str(endpoint[0]), int(endpoint[1])),
        unix_server=unix_server,
        broker_socket=broker_socket,
        control_cert=control_cert,
        control_key=control_key,
    )


async def _close_gateway(fixture: _GatewayFixture) -> None:
    fixture.server.close()
    await fixture.server.wait_closed()
    fixture.unix_server.close()
    await fixture.unix_server.wait_closed()
    fixture.broker_socket.unlink(missing_ok=True)


def _client_context(
    *, ca: Path, cert: Path | None = None, key: Path | None = None
) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca))
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    if cert is not None and key is not None:
        context.load_cert_chain(certfile=str(cert), keyfile=str(key))
    return context


async def _exchange(
    endpoint: tuple[str, int],
    context: ssl.SSLContext,
    request: dict,
    *,
    server_hostname: str = "localhost",
) -> dict:
    reader, writer = await asyncio.open_connection(
        *endpoint, ssl=context, server_hostname=server_hostname
    )
    try:
        encoded = json.dumps(
            request,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
        writer.write(encode_frame(encoded))
        await writer.drain()
        header = await reader.readexactly(4)
        size = int.from_bytes(header, "big")
        return json.loads(await reader.readexactly(size))
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.mark.skipif(not _openssl_available(), reason="openssl unavailable")
async def test_loopback_mtls_one_read_request_end_to_end(tmp_path: Path) -> None:
    fixture = await _gateway_fixture(tmp_path)
    context = _client_context(
        ca=fixture.config.ca_path,
        cert=fixture.control_cert,
        key=fixture.control_key,
    )
    try:
        response = await _exchange(fixture.endpoint, context, _request())
        assert response["outcome"] == "ok"
        assert response["broker_response"] == {"worker": "RUN-001"}
        assert response["host_ref"] == HOST_REF
        assert response["worker_id"] == "WORKER-001"
        assert response["request_sha256"] == _request()["request_sha256"]
    finally:
        await _close_gateway(fixture)


@pytest.mark.skipif(not _openssl_available(), reason="openssl unavailable")
async def test_missing_client_certificate_never_reaches_broker(tmp_path: Path) -> None:
    fixture = await _gateway_fixture(tmp_path)
    calls = 0

    async def broker_call(*args: object, **kwargs: object) -> dict:
        nonlocal calls
        calls += 1
        return {}

    fixture.gateway.broker_call = broker_call
    context = _client_context(ca=fixture.config.ca_path)
    try:
        try:
            reader, writer = await asyncio.open_connection(
                *fixture.endpoint, ssl=context, server_hostname="localhost"
            )
        except (ssl.SSLError, ConnectionResetError, OSError):
            pass
        else:
            writer.write(encode_frame(b"{}"))
            await writer.drain()
            assert await reader.read() == b""
            writer.close()
            await writer.wait_closed()
        assert calls == 0
    finally:
        await _close_gateway(fixture)


@pytest.mark.skipif(not _openssl_available(), reason="openssl unavailable")
async def test_wrong_control_certificate_fingerprint_refused_before_broker(
    tmp_path: Path,
) -> None:
    fixture = await _gateway_fixture(tmp_path)
    other_key, other_cert, _ = _certificate_fixture(
        tmp_path,
        name="other-control",
        common_name="other-control",
        san="DNS:other.invalid",
        issuer_key=tmp_path / "gateway-ca.key",
        issuer_cert=fixture.config.ca_path,
    )
    calls = 0

    async def broker_call(*args: object, **kwargs: object) -> dict:
        nonlocal calls
        calls += 1
        return {}

    fixture.gateway.broker_call = broker_call
    context = _client_context(ca=fixture.config.ca_path, cert=other_cert, key=other_key)
    try:
        reader, writer = await asyncio.open_connection(
            *fixture.endpoint, ssl=context, server_hostname="localhost"
        )
        writer.write(encode_frame(json.dumps(_request()).encode()))
        await writer.drain()
        assert await reader.read() == b""
        writer.close()
        await writer.wait_closed()
        assert calls == 0
    finally:
        await _close_gateway(fixture)


@pytest.mark.skipif(not _openssl_available(), reason="openssl unavailable")
async def test_client_rejects_server_hostname_mismatch(tmp_path: Path) -> None:
    fixture = await _gateway_fixture(tmp_path)
    context = _client_context(
        ca=fixture.config.ca_path,
        cert=fixture.control_cert,
        key=fixture.control_key,
    )
    try:
        with pytest.raises(ssl.SSLCertVerificationError):
            await asyncio.open_connection(
                *fixture.endpoint, ssl=context, server_hostname="wrong.invalid"
            )
    finally:
        await _close_gateway(fixture)


@pytest.mark.skipif(not _openssl_available(), reason="openssl unavailable")
async def test_closed_request_refusals_never_reach_broker(tmp_path: Path) -> None:
    fixture = await _gateway_fixture(tmp_path)
    calls: list[str] = []

    async def broker_call(operation: str, payload: dict) -> dict:
        calls.append(operation)
        return {"should": "not happen"}

    fixture.gateway.broker_call = broker_call
    context = _client_context(
        ca=fixture.config.ca_path,
        cert=fixture.control_cert,
        key=fixture.control_key,
    )
    try:
        for mutation in (
            {"host_ref": "b" * 64},
            {"worker_id": "WORKER-002"},
            {"job_id": "../JOB-002"},
            {"attempt_id": "../ATT-002"},
            {"request_sha256": "0" * 64},
            {"broker_operation": "start"},
            {"socket_path": "/tmp/owned.sock"},
        ):
            response = await _exchange(fixture.endpoint, context, {**_request(), **mutation})
            assert response["outcome"] == "refused"
            assert response["broker_response"] is None
        assert calls == []
    finally:
        await _close_gateway(fixture)


@pytest.mark.skipif(not _openssl_available(), reason="openssl unavailable")
async def test_oversize_request_closes_without_broker_call(tmp_path: Path) -> None:
    fixture = await _gateway_fixture(tmp_path)
    calls = 0

    async def broker_call(*args: object, **kwargs: object) -> dict:
        nonlocal calls
        calls += 1
        return {}

    fixture.gateway.broker_call = broker_call
    context = _client_context(
        ca=fixture.config.ca_path,
        cert=fixture.control_cert,
        key=fixture.control_key,
    )
    try:
        reader, writer = await asyncio.open_connection(
            *fixture.endpoint, ssl=context, server_hostname="localhost"
        )
        writer.write((1024 * 1024 + 1).to_bytes(4, "big"))
        await writer.drain()
        assert await reader.read() == b""
        writer.close()
        await writer.wait_closed()
        assert calls == 0
    finally:
        await _close_gateway(fixture)


@pytest.mark.skipif(not _openssl_available(), reason="openssl unavailable")
async def test_gateway_restart_has_no_history_or_state(tmp_path: Path) -> None:
    fixture = await _gateway_fixture(tmp_path)
    context = _client_context(
        ca=fixture.config.ca_path,
        cert=fixture.control_cert,
        key=fixture.control_key,
    )
    try:
        first = await _exchange(fixture.endpoint, context, _request())
        assert first["outcome"] == "ok"
        fixture.server.close()
        await fixture.server.wait_closed()

        replacement = RemoteWorkerGateway(fixture.config)
        assert set(vars(replacement)) == {
            "config",
            "_broker_client",
            "broker_call",
            "_ssl_context",
        }
        fixture.gateway = replacement
        fixture.server = await replacement.start_server()
        endpoint = fixture.server.sockets[0].getsockname()[:2]
        fixture.endpoint = (str(endpoint[0]), int(endpoint[1]))
        second = await _exchange(fixture.endpoint, context, _request())
        assert second["outcome"] == "ok"
    finally:
        await _close_gateway(fixture)


def _placeholder_config(tmp_path: Path, *, listen_host: str) -> RemoteWorkerGatewayConfig:
    for name in ("server.pem", "server.key", "ca.pem"):
        (tmp_path / name).write_text("placeholder", encoding="utf-8")
    return RemoteWorkerGatewayConfig(
        schema=REMOTE_WORKER_GATEWAY_CONFIG_SCHEMA,
        host_ref=HOST_REF,
        listen_host=listen_host,
        listen_port=443,
        certificate_path=tmp_path / "server.pem",
        key_path=tmp_path / "server.key",
        ca_path=tmp_path / "ca.pem",
        expected_control_fingerprint="0" * 64,
        broker_socket_path=tmp_path / "broker.sock",
        allowed_worker_ids={"WORKER-001"},
        allowed_operations={"status"},
    )


def test_config_accepts_explicit_tailscale_cgnat_address(tmp_path: Path) -> None:
    config = _placeholder_config(tmp_path, listen_host="100.64.0.7")
    assert config.listen_host == "100.64.0.7"


@pytest.mark.parametrize("address", ["0.0.0.0", "::", "8.8.8.8", "example.com"])
def test_config_refuses_wildcard_public_or_non_ip_listener(
    tmp_path: Path, address: str
) -> None:
    with pytest.raises(ValueError, match="listen address"):
        _placeholder_config(tmp_path, listen_host=address)


def test_config_refuses_relative_broker_socket(tmp_path: Path) -> None:
    config = _placeholder_config(tmp_path, listen_host="127.0.0.1")
    values = {
        field.name: getattr(config, field.name)
        for field in config.__dataclass_fields__.values()
    }
    values["broker_socket_path"] = Path("relative.sock")
    with pytest.raises(ValueError, match="broker socket"):
        RemoteWorkerGatewayConfig(**values)


def test_config_refuses_non_string_worker_allowlist_identity(tmp_path: Path) -> None:
    config = _placeholder_config(tmp_path, listen_host="127.0.0.1")
    values = {
        field.name: getattr(config, field.name)
        for field in config.__dataclass_fields__.values()
    }
    values["allowed_worker_ids"] = {12}
    with pytest.raises(ValueError, match="worker allowlist"):
        RemoteWorkerGatewayConfig(**values)
