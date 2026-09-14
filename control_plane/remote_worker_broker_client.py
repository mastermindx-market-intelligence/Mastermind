"""Control-side authenticated MH1 client for one already-claimed remote Worker.

The client is transport only. It binds one exact Executive Job/Attempt/Worker/host
context to the existing Worker Broker protocol. It never selects a worker, owns a
queue, or retries a modifying operation after bytes may have crossed the network.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import ssl
import struct
from collections.abc import Mapping
from typing import Any

from control_plane.executive_worker_broker import (
    BROKER_REQUEST_SCHEMA_VERSION,
    BROKER_RESPONSE_SCHEMA_VERSION,
    BrokerProtocolError,
    RemoteBrokerError,
)
from control_plane.remote_worker_transport import (
    BrokerTransportBinding,
    RemoteBrokerRequest,
    RemoteBrokerResponse,
    RemoteWorkerTransportError,
    assert_operation_replay_compatible,
    canonical_json_bytes,
)

_FRAME_HEADER = struct.Struct("!I")
_MAX_FRAME_BYTES = 16 * 1024 * 1024
_READ_ONLY_OPERATIONS = frozenset(
    {
        "status",
        "ohf-validate",
        "ohf-identity",
        "ohf-materialization-status",
        "ohf-collect-turn",
        "ohf-reconcile",
    }
)


class RemoteWorkerBrokerClientError(RuntimeError):
    """Base fail-closed MH1 client error."""


class RemoteBrokerUnavailableError(RemoteWorkerBrokerClientError):
    """No modifying bytes were proven submitted, or a read path became unavailable."""


class RemoteBrokerAuthenticationError(RemoteWorkerBrokerClientError):
    """The TLS server identity did not match the reviewed host binding."""


class RemoteBrokerEffectUnknownError(RemoteWorkerBrokerClientError):
    """A modifying request may have taken effect and must not be resent."""


class RemoteBrokerReplayRefusedError(RemoteWorkerBrokerClientError):
    """A modifying operation already crossed the transport effect boundary."""


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _operation_command_id(payload: Mapping[str, Any]) -> str | None:
    raw = payload.get("operation_id")
    if not isinstance(raw, Mapping):
        return None
    command_id = raw.get("command_id")
    if not isinstance(command_id, str) or not command_id:
        return None
    return command_id


def _logical_operation_id(
    operation: str,
    payload: Mapping[str, Any],
    *,
    attempt_id: str,
) -> str:
    native = _operation_command_id(payload)
    if native is not None:
        return native
    if operation == "ohf-deliver-attention":
        nudge_id = payload.get("nudge_id")
        if isinstance(nudge_id, str) and nudge_id:
            return "mh1:nudge:" + hashlib.sha256(nudge_id.encode()).hexdigest()[:32]
    if operation in {"start", "cancel", "collect"}:
        return f"mh1:{operation}:{attempt_id}"
    return f"mh1:{operation}:{_digest(payload)[:32]}"


def _broker_request_id(operation_id: str, operation: str) -> str:
    material = f"{operation_id}\x00{operation}".encode("utf-8")
    return "mh1-req-" + hashlib.sha256(material).hexdigest()[:32]


def _validate_payload_identity(
    operation: str,
    payload: Mapping[str, Any],
    *,
    job_id: str,
    attempt_id: str,
    worker_id: str,
) -> None:
    expected_direct = {
        "job_id": job_id,
        "attempt_id": attempt_id,
        "run_id": attempt_id,
        "worker_id": worker_id,
    }
    for field, expected in expected_direct.items():
        if field in payload and payload[field] != expected:
            raise BrokerProtocolError(f"remote {field} does not match bound Attempt")

    launch = payload.get("launch_spec")
    if operation == "start" and not isinstance(launch, Mapping):
        raise BrokerProtocolError("remote start requires launch_spec")
    if isinstance(launch, Mapping):
        for field, expected in (("run_id", attempt_id), ("job_id", job_id), ("worker_id", worker_id)):
            if field in launch and launch[field] != expected:
                raise BrokerProtocolError(f"remote launch_spec {field} identity drifted")
    nested_checks = (
        ("generation", "worker_id", worker_id),
        ("epoch", "worker_id", worker_id),
        ("epoch", "attempt_id", attempt_id),
        ("turn", "attempt_id", attempt_id),
        ("requested", "worker_id", worker_id),
        ("provider_session", "worker_id", worker_id),
    )
    for container_name, field, expected in nested_checks:
        container = payload.get(container_name)
        if isinstance(container, Mapping) and field in container:
            if container[field] != expected:
                raise BrokerProtocolError(
                    f"remote {container_name}.{field} identity drifted"
                )


def _is_modifying(operation: str) -> bool:
    return operation not in _READ_ONLY_OPERATIONS


async def _read_frame(
    reader: asyncio.StreamReader,
    *,
    max_bytes: int,
    timeout_seconds: float,
) -> bytes:
    header = await asyncio.wait_for(
        reader.readexactly(_FRAME_HEADER.size), timeout=timeout_seconds
    )
    (size,) = _FRAME_HEADER.unpack(header)
    if size < 2 or size > max_bytes:
        raise BrokerProtocolError("remote response frame size is invalid")
    return await asyncio.wait_for(reader.readexactly(size), timeout=timeout_seconds)


class RemoteWorkerBrokerClient:
    """One-attempt MH1 client exposing the existing WorkerBrokerClient seam."""

    def __init__(
        self,
        binding: BrokerTransportBinding,
        *,
        job_id: str,
        attempt_id: str,
        worker_id: str,
        max_request_bytes: int = 1024 * 1024,
        max_response_bytes: int = _MAX_FRAME_BYTES,
    ) -> None:
        self.binding = binding
        self.job_id = job_id
        self.attempt_id = attempt_id
        self.worker_id = worker_id
        self.max_request_bytes = int(max_request_bytes)
        self.max_response_bytes = int(max_response_bytes)
        if not 1024 <= self.max_request_bytes <= _MAX_FRAME_BYTES:
            raise RemoteWorkerTransportError("remote request ceiling is invalid")
        if not 1024 <= self.max_response_bytes <= _MAX_FRAME_BYTES:
            raise RemoteWorkerTransportError("remote response ceiling is invalid")
        self._operation_contracts: dict[str, RemoteBrokerRequest] = {}
        self._submitted_modifications: set[str] = set()
        self._validate_bound_context()

    def _validate_bound_context(self) -> None:
        probe = {
            "schema_version": BROKER_REQUEST_SCHEMA_VERSION,
            "request_id": "mh1-bind-probe",
            "operation": "status",
            "payload": {},
        }
        RemoteBrokerRequest.build(
            host_ref=self.binding.host_ref,
            job_id=self.job_id,
            attempt_id=self.attempt_id,
            worker_id=self.worker_id,
            operation_id="mh1:bind-probe",
            broker_operation="status",
            broker_request=probe,
        )

    def _build_ssl_context(self) -> ssl.SSLContext:
        context = ssl.create_default_context(
            ssl.Purpose.SERVER_AUTH,
            cafile=str(self.binding.ca_certificate_path),
        )
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.check_hostname = True
        context.load_cert_chain(
            certfile=str(self.binding.client_certificate_path),
            keyfile=str(self.binding.client_private_key_path),
        )
        return context

    def _build_remote_request(
        self,
        operation: str,
        payload: Mapping[str, Any],
    ) -> RemoteBrokerRequest:
        if not isinstance(operation, str) or not operation:
            raise BrokerProtocolError("remote broker operation is invalid")
        if not isinstance(payload, Mapping):
            raise BrokerProtocolError("remote broker payload must be an object")
        payload_dict = dict(payload)
        _validate_payload_identity(
            operation,
            payload_dict,
            job_id=self.job_id,
            attempt_id=self.attempt_id,
            worker_id=self.worker_id,
        )
        operation_id = _logical_operation_id(
            operation, payload_dict, attempt_id=self.attempt_id
        )
        broker_request = {
            "schema_version": BROKER_REQUEST_SCHEMA_VERSION,
            "request_id": _broker_request_id(operation_id, operation),
            "operation": operation,
            "payload": payload_dict,
        }
        request = RemoteBrokerRequest.build(
            host_ref=self.binding.host_ref,
            job_id=self.job_id,
            attempt_id=self.attempt_id,
            worker_id=self.worker_id,
            operation_id=operation_id,
            broker_operation=operation,
            broker_request=broker_request,
        )
        if _is_modifying(operation):
            prior = self._operation_contracts.get(operation_id)
            if prior is not None:
                assert_operation_replay_compatible(prior, request)
            else:
                self._operation_contracts[operation_id] = request
        return request

    def _verify_server_identity(self, writer: asyncio.StreamWriter) -> None:
        ssl_object = writer.get_extra_info("ssl_object")
        if ssl_object is None:
            raise RemoteBrokerAuthenticationError(
                "remote TLS session is unavailable"
            )
        peer_der = ssl_object.getpeercert(binary_form=True)
        if not isinstance(peer_der, bytes) or not peer_der:
            raise RemoteBrokerAuthenticationError(
                "remote server certificate is unavailable"
            )
        observed = hashlib.sha256(peer_der).hexdigest()
        if not hmac.compare_digest(
            observed,
            self.binding.expected_server_certificate_sha256,
        ):
            raise RemoteBrokerAuthenticationError(
                "remote server certificate fingerprint mismatch"
            )

    def _encode_request(self, request: RemoteBrokerRequest) -> bytes:
        payload = canonical_json_bytes(request.to_mapping())
        if len(payload) > self.max_request_bytes:
            raise BrokerProtocolError("remote request exceeds the client ceiling")
        return _FRAME_HEADER.pack(len(payload)) + payload

    def _decode_response(
        self,
        raw: bytes,
        request: RemoteBrokerRequest,
    ) -> RemoteBrokerResponse:
        try:
            document = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BrokerProtocolError(
                "remote response is not valid UTF-8 JSON"
            ) from exc
        if not isinstance(document, dict):
            raise BrokerProtocolError("remote response must be an object")
        try:
            return RemoteBrokerResponse.from_mapping(
                document, expected_request=request
            )
        except RemoteWorkerTransportError as exc:
            raise BrokerProtocolError(
                "remote response envelope is invalid"
            ) from exc

    def _broker_result(
        self,
        response: RemoteBrokerResponse,
        request: RemoteBrokerRequest,
    ) -> dict[str, Any]:
        broker = dict(response.broker_response)
        expected_id = request.broker_request["request_id"]
        if (
            broker.get("schema_version") != BROKER_RESPONSE_SCHEMA_VERSION
            or broker.get("request_id") != expected_id
            or broker.get("operation") != request.broker_operation
        ):
            raise BrokerProtocolError(
                "remote Worker Broker response identity is invalid"
            )
        if response.outcome == "effect_unknown":
            raise RemoteBrokerEffectUnknownError(
                "remote broker reported unknown external effect"
            )
        if response.outcome == "broker_unavailable":
            if _is_modifying(request.broker_operation):
                raise RemoteBrokerEffectUnknownError(
                    "remote broker became unavailable after submission"
                )
            raise RemoteBrokerUnavailableError("remote broker is unavailable")
        if response.outcome not in {
            "completed",
            "broker_refused",
            "gateway_refused",
        }:
            raise BrokerProtocolError("remote broker outcome is unsupported")
        if broker.get("ok") is not True:
            error = broker.get("error")
            if not isinstance(error, Mapping):
                raise BrokerProtocolError("remote broker error response is malformed")
            code = str(error.get("code") or "RemoteBrokerError")
            message = str(
                error.get("message") or "remote Worker Broker rejected the request"
            )[:500]
            raise RemoteBrokerError(code, message)
        result = broker.get("result")
        if not isinstance(result, Mapping):
            raise BrokerProtocolError("remote Worker Broker result must be an object")
        return dict(result)

    async def request(
        self,
        operation: str,
        payload: Mapping[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        request = self._build_remote_request(operation, payload)
        modifying = _is_modifying(operation)
        if modifying and request.operation_id in self._submitted_modifications:
            raise RemoteBrokerReplayRefusedError(
                "remote modifying operation already crossed the transport boundary"
            )
        timeout = (
            self.binding.timeout_seconds
            if timeout_seconds is None
            else float(timeout_seconds)
        )
        if not 0.1 <= timeout <= 25 * 60 * 60:
            raise BrokerProtocolError("remote request timeout is outside the safe range")
        try:
            context = self._build_ssl_context()
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    self.binding.endpoint_host,
                    self.binding.endpoint_port,
                    ssl=context,
                    server_hostname=self.binding.endpoint_host,
                ),
                timeout=timeout,
            )
        except (OSError, ssl.SSLError, TimeoutError) as exc:
            raise RemoteBrokerUnavailableError(
                "remote Worker Broker connection failed before request submission"
            ) from exc

        submitted = False
        try:
            self._verify_server_identity(writer)
            frame = self._encode_request(request)
            if modifying:
                self._submitted_modifications.add(request.operation_id)
                submitted = True
            writer.write(frame)
            await asyncio.wait_for(writer.drain(), timeout=timeout)
            raw = await _read_frame(
                reader,
                max_bytes=self.max_response_bytes,
                timeout_seconds=timeout,
            )
            response = self._decode_response(raw, request)
        except RemoteBrokerAuthenticationError:
            raise
        except asyncio.CancelledError as exc:
            if submitted:
                raise RemoteBrokerEffectUnknownError(
                    "remote modifying request was cancelled after submission"
                ) from exc
            raise
        except Exception as exc:
            if submitted:
                raise RemoteBrokerEffectUnknownError(
                    "remote modifying request lost a trustworthy completion response"
                ) from exc
            raise RemoteBrokerUnavailableError(
                "remote Worker Broker read path became unavailable"
            ) from exc
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

        try:
            return self._broker_result(response, request)
        except BrokerProtocolError as exc:
            if modifying:
                raise RemoteBrokerEffectUnknownError(
                    "remote modifying response could not be authenticated as complete"
                ) from exc
            raise

    def request_sync(
        self,
        operation: str,
        payload: Mapping[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.request(
                    operation,
                    payload,
                    timeout_seconds=timeout_seconds,
                )
            )
        raise RemoteWorkerBrokerClientError(
            "request_sync cannot run inside an active event loop"
        )


__all__ = [
    "RemoteBrokerAuthenticationError",
    "RemoteBrokerEffectUnknownError",
    "RemoteBrokerReplayRefusedError",
    "RemoteBrokerUnavailableError",
    "RemoteWorkerBrokerClient",
    "RemoteWorkerBrokerClientError",
]
