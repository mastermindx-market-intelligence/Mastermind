"""Stateless mutually authenticated MH1 gateway for one host-local Worker Broker.

The gateway is transport only. It owns no Executive lifecycle state, queue,
placement, retry journal, provider credential, or provider selection. Each
connection carries exactly one bounded request to the one configured local
AF_UNIX Worker Broker socket and then closes.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import ssl
import struct
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from control_plane.executive_worker_broker import (
    BROKER_REQUEST_SCHEMA_VERSION,
    BROKER_RESPONSE_SCHEMA_VERSION,
    BROKER_UNAVAILABLE_ERROR_CODE,
    BrokerProtocolError,
    RemoteBrokerError,
    WorkerBrokerClient,
    _ALLOWED_OPERATIONS,
)
from control_plane.remote_worker_transport import (
    RemoteBrokerRequest,
    RemoteBrokerResponse,
    RemoteWorkerTransportError,
    canonical_json_bytes,
)

try:
    from ops.executive_os.remote_worker_gateway_config import (
        RemoteWorkerGatewayConfig,
        load_gateway_config,
    )
except ModuleNotFoundError:  # pragma: no cover - installed direct-script mode
    from remote_worker_gateway_config import (  # type: ignore[no-redef]
        RemoteWorkerGatewayConfig,
        load_gateway_config,
    )

_FRAME_HEADER = struct.Struct("!I")
_BROKER_REQUEST_KEYS = frozenset({"schema_version", "request_id", "operation", "payload"})
_ID_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-")


class RemoteWorkerGatewayError(RuntimeError):
    """Base fail-closed gateway error."""


class GatewayAuthenticationError(RemoteWorkerGatewayError):
    """The network peer did not match the configured control principal."""


class GatewayProtocolError(RemoteWorkerGatewayError):
    """The remote envelope or local broker frame violated the closed protocol."""


class GatewayBindingError(RemoteWorkerGatewayError):
    """The request did not match this host/Worker gateway binding."""


def _bounded_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 128
        and value[0].isalnum()
        and all(ch in _ID_CHARS for ch in value)
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def certificate_sha256(der_bytes: bytes) -> str:
    if not isinstance(der_bytes, bytes) or not der_bytes:
        raise GatewayAuthenticationError("peer certificate is unavailable")
    return hashlib.sha256(der_bytes).hexdigest()


def build_server_ssl_context(config: RemoteWorkerGatewayConfig) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = False
    context.load_cert_chain(
        certfile=str(config.server_certificate_path),
        keyfile=str(config.server_private_key_path),
    )
    context.load_verify_locations(cafile=str(config.ca_certificate_path))
    return context


async def _read_frame(reader: asyncio.StreamReader, *, max_bytes: int, timeout: float) -> bytes:
    try:
        header = await asyncio.wait_for(reader.readexactly(_FRAME_HEADER.size), timeout=timeout)
    except (asyncio.IncompleteReadError, TimeoutError) as exc:
        raise GatewayProtocolError("remote request frame header is incomplete") from exc
    (size,) = _FRAME_HEADER.unpack(header)
    if size < 2 or size > max_bytes:
        raise GatewayProtocolError("remote request frame size is outside the allowed range")
    try:
        return await asyncio.wait_for(reader.readexactly(size), timeout=timeout)
    except (asyncio.IncompleteReadError, TimeoutError) as exc:
        raise GatewayProtocolError("remote request frame body is incomplete") from exc


async def _write_frame(writer: asyncio.StreamWriter, value: Mapping[str, Any], *, max_bytes: int) -> None:
    payload = canonical_json_bytes(value)
    if len(payload) > max_bytes:
        raise GatewayProtocolError("remote response exceeds the configured ceiling")
    writer.write(_FRAME_HEADER.pack(len(payload)) + payload)
    await writer.drain()


def _parse_json_object(raw: bytes, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GatewayProtocolError(f"{field} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise GatewayProtocolError(f"{field} must be a JSON object")
    return value


def _validate_broker_request(request: RemoteBrokerRequest) -> dict[str, Any]:
    raw = request.to_mapping()["broker_request"]
    if not isinstance(raw, dict) or set(raw) != _BROKER_REQUEST_KEYS:
        raise GatewayProtocolError("embedded Worker Broker request fields are invalid")
    if raw.get("schema_version") != BROKER_REQUEST_SCHEMA_VERSION:
        raise GatewayProtocolError("embedded Worker Broker request schema is unsupported")
    request_id = raw.get("request_id")
    if not _bounded_id(request_id):
        raise GatewayProtocolError("embedded Worker Broker request_id is invalid")
    operation = raw.get("operation")
    if operation != request.broker_operation or operation not in _ALLOWED_OPERATIONS:
        raise GatewayProtocolError("embedded Worker Broker operation is not allowed")
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        raise GatewayProtocolError("embedded Worker Broker payload must be an object")
    return raw

def _validate_bound_identity(
    request: RemoteBrokerRequest,
    broker_request: Mapping[str, Any],
) -> None:
    payload = broker_request["payload"]
    assert isinstance(payload, dict)
    direct_expected = {
        "job_id": request.job_id,
        "attempt_id": request.attempt_id,
        "run_id": request.attempt_id,
        "worker_id": request.worker_id,
    }
    for field, expected in direct_expected.items():
        if field in payload and payload[field] != expected:
            raise GatewayBindingError(
                f"embedded {field} does not match remote identity"
            )

    launch_spec = payload.get("launch_spec")
    if request.broker_operation == "start":
        if not isinstance(launch_spec, dict):
            raise GatewayBindingError("start request is missing launch_spec identity")
        required = {
            "run_id": request.attempt_id,
            "job_id": request.job_id,
            "worker_id": request.worker_id,
        }
        for field, expected in required.items():
            if launch_spec.get(field) != expected:
                raise GatewayBindingError(
                    f"launch_spec {field} does not match remote identity"
                )
    elif isinstance(launch_spec, dict):
        for field, expected in (
            ("run_id", request.attempt_id),
            ("job_id", request.job_id),
            ("worker_id", request.worker_id),
        ):
            if field in launch_spec and launch_spec[field] != expected:
                raise GatewayBindingError(
                    f"launch_spec {field} does not match remote identity"
                )

    generation = payload.get("generation")
    if isinstance(generation, dict) and "worker_id" in generation:
        if generation["worker_id"] != request.worker_id:
            raise GatewayBindingError(
                "generation worker_id does not match remote identity"
            )


def _validate_local_response(
    response: Any,
    *,
    broker_request: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise GatewayProtocolError(
            "local Worker Broker response must be an object"
        )
    required = {"schema_version", "request_id", "operation", "ok"}
    if not required.issubset(response):
        raise GatewayProtocolError(
            "local Worker Broker response is missing identity fields"
        )
    if response.get("schema_version") != BROKER_RESPONSE_SCHEMA_VERSION:
        raise GatewayProtocolError(
            "local Worker Broker response schema is unsupported"
        )
    if (
        response.get("request_id") != broker_request.get("request_id")
        or response.get("operation") != broker_request.get("operation")
    ):
        raise GatewayProtocolError(
            "local Worker Broker response identity drifted"
        )
    if type(response.get("ok")) is not bool:
        raise GatewayProtocolError(
            "local Worker Broker response ok field is invalid"
        )
    if response["ok"] is True:
        if set(response) != required | {"result"}:
            raise GatewayProtocolError(
                "local Worker Broker success response is malformed"
            )
    return response

def _broker_outcome(response: Mapping[str, Any]) -> str:
    if response.get("ok") is True:
        return "completed"
    error = response.get("error")
    code = error.get("code") if isinstance(error, Mapping) else None
    if code == "BrokerEffectUnknownError":
        return "effect_unknown"
    if code == BROKER_UNAVAILABLE_ERROR_CODE:
        return "broker_unavailable"
    return "broker_refused"


class RemoteWorkerGateway:
    def __init__(self, config: RemoteWorkerGatewayConfig) -> None:
        self.config = config

    def _authorize_peer(self, peer_certificate_der: bytes) -> None:
        observed = certificate_sha256(peer_certificate_der)
        if not hmac.compare_digest(
            observed,
            self.config.expected_control_client_certificate_sha256,
        ):
            raise GatewayAuthenticationError(
                "control client certificate identity mismatch"
            )

    def _authorize_binding(self, request: RemoteBrokerRequest) -> None:
        if request.host_ref != self.config.host_ref:
            raise GatewayBindingError(
                "remote host_ref does not match this gateway"
            )
        if request.worker_id not in self.config.allowed_worker_ids:
            raise GatewayBindingError(
                "remote worker_id is not allowed on this gateway"
            )

    async def _forward_local(
        self,
        broker_request: Mapping[str, Any],
    ) -> dict[str, Any]:
        client = WorkerBrokerClient(
            self.config.worker_broker_socket_path,
            timeout_seconds=self.config.local_broker_timeout_seconds,
            max_response_bytes=self.config.max_response_bytes,
        )
        operation = str(broker_request["operation"])
        payload = broker_request["payload"]
        assert isinstance(payload, dict)
        try:
            result = await client.request(
                operation,
                payload,
                timeout_seconds=self.config.local_broker_timeout_seconds,
            )
        except RemoteBrokerError as exc:
            return {
                "schema_version": BROKER_RESPONSE_SCHEMA_VERSION,
                "request_id": str(broker_request["request_id"]),
                "operation": operation,
                "ok": False,
                "error": {
                    "code": exc.code,
                    "message": str(exc)[:500],
                },
            }
        except (BrokerProtocolError, TimeoutError, OSError) as exc:
            raise RemoteWorkerGatewayError(
                "local Worker Broker outcome is unavailable"
            ) from exc
        return {
            "schema_version": BROKER_RESPONSE_SCHEMA_VERSION,
            "request_id": str(broker_request["request_id"]),
            "operation": operation,
            "ok": True,
            "result": result,
        }

    async def process_request(
        self,
        request: RemoteBrokerRequest,
        *,
        peer_certificate_der: bytes,
    ) -> RemoteBrokerResponse:
        self._authorize_peer(peer_certificate_der)
        self._authorize_binding(request)
        broker_request = _validate_broker_request(request)
        _validate_bound_identity(request, broker_request)
        broker_response = await self._forward_local(broker_request)
        return RemoteBrokerResponse.build(
            request=request,
            outcome=_broker_outcome(broker_response),
            broker_response=broker_response,
            observed_at=_utc_now(),
        )

    async def handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        request: RemoteBrokerRequest | None = None
        peer_authorized = False
        try:
            ssl_object = writer.get_extra_info("ssl_object")
            if ssl_object is None:
                raise GatewayAuthenticationError("TLS session is unavailable")
            peer_der = ssl_object.getpeercert(binary_form=True)
            self._authorize_peer(peer_der)
            peer_authorized = True
            raw = await _read_frame(
                reader,
                max_bytes=self.config.max_request_bytes,
                timeout=self.config.read_timeout_seconds,
            )
            document = _parse_json_object(raw, field="remote request")
            try:
                request = RemoteBrokerRequest.from_mapping(document)
            except RemoteWorkerTransportError as exc:
                raise GatewayProtocolError(
                    "remote request envelope is invalid"
                ) from exc
            response = await self.process_request(
                request,
                peer_certificate_der=peer_der,
            )
            await _write_frame(
                writer,
                response.to_mapping(),
                max_bytes=self.config.max_response_bytes,
            )
        except GatewayAuthenticationError:
            pass
        except (GatewayProtocolError, GatewayBindingError):
            if request is not None and peer_authorized:
                refused = RemoteBrokerResponse.build(
                    request=request,
                    outcome="gateway_refused",
                    broker_response={
                        "schema_version": BROKER_RESPONSE_SCHEMA_VERSION,
                        "request_id": str(
                            request.broker_request.get("request_id") or "invalid"
                        )[:128],
                        "operation": request.broker_operation,
                        "ok": False,
                        "error": {
                            "code": "RemoteWorkerGatewayRefusal",
                            "message": (
                                "remote Worker Broker gateway refused the request"
                            ),
                        },
                    },
                    observed_at=_utc_now(),
                )
                try:
                    await _write_frame(
                        writer,
                        refused.to_mapping(),
                        max_bytes=self.config.max_response_bytes,
                    )
                except (OSError, RemoteWorkerGatewayError, RemoteWorkerTransportError):
                    pass
        except RemoteWorkerGatewayError:
            # The local broker call may already have crossed its effect boundary.
            # Close without a response so the control-side client classifies the
            # modifying operation as EFFECT_UNKNOWN; never synthesize no-effect.
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def serve_forever(self) -> None:
        context = build_server_ssl_context(self.config)
        server = await asyncio.start_server(
            self.handle_connection,
            host=self.config.listen_host,
            port=self.config.listen_port,
            ssl=context,
            limit=self.config.max_request_bytes + _FRAME_HEADER.size,
        )
        async with server:
            await server.serve_forever()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve the stateless MH1 Worker Broker gateway"
    )
    parser.add_argument("--config", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = load_gateway_config(args.config)
    gateway = RemoteWorkerGateway(config)
    try:
        asyncio.run(gateway.serve_forever())
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "GatewayAuthenticationError",
    "GatewayBindingError",
    "GatewayProtocolError",
    "RemoteWorkerGateway",
    "RemoteWorkerGatewayError",
    "build_server_ssl_context",
    "certificate_sha256",
    "main",
]
