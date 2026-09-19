"""Control-side MH1 client for one authenticated remote Worker Broker request.

The client is bound to one existing host/job/attempt/worker/operation identity.
It performs no placement, lifecycle mutation, retry, failover, or persistence.
For modifying operations, any uncertainty after request transmission begins is
classified EFFECT_UNKNOWN and is never retried automatically.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import ssl
from contextlib import suppress
from typing import Any, Mapping

from control_plane.operator_harness_contract import COMMAND_ID_RE
from control_plane.remote_worker_transport import (
    MAX_FRAME_BYTES,
    BrokerTransportBinding,
    TransportEffect,
    TransportError,
    TransportValidationError,
    build_client_ssl_context,
    build_request,
    encode_frame,
    validate_response,
)

_READ_ONLY_OPERATIONS = frozenset(
    {
        "ohf-identity",
        "ohf-materialization-status",
    }
)
_BOUND_AUTHORITY_KEYS = frozenset({"host_ref", "job_id", "attempt_id", "worker_id"})
_BOUND_PAYLOAD_IDENTITY_KEYS = frozenset({"session_epoch_id", "process_generation_id"})


class RemoteWorkerBrokerClient:
    """One-request-per-connection mTLS client bound to one Executive identity."""

    def __init__(
        self,
        binding: BrokerTransportBinding,
        identity: Mapping[str, Any],
        *,
        allowed_operations: set[str] | frozenset[str],
        bound_payload_identity: Mapping[str, str] | None = None,
    ) -> None:
        self.binding = binding
        operations = frozenset(allowed_operations)
        if not operations or any(not isinstance(value, str) for value in operations):
            raise TransportValidationError("remote broker client operations are invalid")
        normalized_identity = dict(identity)
        for operation in operations:
            build_request(normalized_identity, operation, {})
        payload_identity = dict(bound_payload_identity or {})
        if payload_identity and set(payload_identity) != _BOUND_PAYLOAD_IDENTITY_KEYS:
            raise TransportValidationError("remote broker payload identity is invalid")
        if any(
            not isinstance(value, str) or COMMAND_ID_RE.fullmatch(value) is None
            for value in payload_identity.values()
        ):
            raise TransportValidationError("remote broker payload identity is invalid")
        self.identity = normalized_identity
        self.allowed_operations = operations
        self.bound_payload_identity = payload_identity

    async def _open_connection(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        context = build_client_ssl_context(self.binding)
        host, port = self.binding.endpoint
        return await asyncio.wait_for(
            asyncio.open_connection(
                host,
                port,
                ssl=context,
                server_hostname=host,
                ssl_handshake_timeout=self.binding.timeout_seconds,
            ),
            timeout=self.binding.timeout_seconds,
        )

    def _server_pin_matches(self, writer: asyncio.StreamWriter) -> bool:
        ssl_object = writer.get_extra_info("ssl_object")
        if ssl_object is None:
            return False
        certificate = ssl_object.getpeercert(binary_form=True)
        if not certificate:
            return False
        observed = hashlib.sha256(certificate).hexdigest()
        return observed == self.binding.expected_server_fingerprint

    def _payload_retargets_authority(self, value: Any) -> bool:
        if isinstance(value, Mapping):
            for key, child in value.items():
                name = str(key)
                if name in _BOUND_AUTHORITY_KEYS and child != self.identity[name]:
                    return True
                if name in _BOUND_PAYLOAD_IDENTITY_KEYS:
                    expected = self.bound_payload_identity.get(name)
                    if expected is None or child != expected:
                        return True
                if self._payload_retargets_authority(child):
                    return True
            return False
        if isinstance(value, (list, tuple)):
            return any(self._payload_retargets_authority(child) for child in value)
        return False

    @staticmethod
    def _operation_is_observational(operation: str, payload: Mapping[str, Any]) -> bool:
        if operation == "status":
            return payload.get("fresh_uid_sweep", False) is False
        return operation in _READ_ONLY_OPERATIONS

    @staticmethod
    def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
        try:
            return json.dumps(
                dict(value),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise TransportValidationError("remote broker request is not canonical JSON") from exc

    async def _read_response(self, reader: asyncio.StreamReader) -> dict[str, Any]:
        header = await asyncio.wait_for(
            reader.readexactly(4), timeout=self.binding.timeout_seconds
        )
        size = int.from_bytes(header, "big")
        if size > MAX_FRAME_BYTES:
            raise TransportValidationError("remote broker response exceeds transport ceiling")
        payload = await asyncio.wait_for(
            reader.readexactly(size), timeout=self.binding.timeout_seconds
        )
        document = json.loads(payload.decode("utf-8", errors="strict"))
        if not isinstance(document, dict):
            raise TransportValidationError("remote broker response must be an object")
        return document

    async def request(
        self,
        operation: str,
        payload: Mapping[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if operation not in self.allowed_operations:
            raise TransportError("operation_not_allowed", TransportEffect.NO_EFFECT)
        if not isinstance(payload, Mapping):
            raise TransportError("request_invalid", TransportEffect.NO_EFFECT)
        if self._payload_retargets_authority(payload):
            raise TransportError("payload_identity_override", TransportEffect.NO_EFFECT)

        if timeout_seconds is not None:
            effective_timeout = float(timeout_seconds)
            if not 0.1 <= effective_timeout <= 3600:
                raise TransportError("timeout_invalid", TransportEffect.NO_EFFECT)
        else:
            effective_timeout = self.binding.timeout_seconds

        try:
            request = build_request(self.identity, operation, payload)
            encoded = self._canonical_bytes(request)
            frame = encode_frame(encoded)
        except TransportValidationError as exc:
            raise TransportError("request_invalid", TransportEffect.NO_EFFECT) from exc

        modifying = not self._operation_is_observational(operation, payload)
        try:
            reader, writer = await asyncio.wait_for(
                self._open_connection(), timeout=effective_timeout
            )
        except (asyncio.TimeoutError, OSError, ssl.SSLError, TransportValidationError) as exc:
            raise TransportError("unavailable", TransportEffect.NO_EFFECT) from exc

        write_started = False
        try:
            if not self._server_pin_matches(writer):
                raise TransportError("server_identity_mismatch", TransportEffect.NO_EFFECT)

            write_started = True
            writer.write(frame)
            await asyncio.wait_for(writer.drain(), timeout=effective_timeout)
            response = await asyncio.wait_for(
                self._read_response(reader), timeout=effective_timeout
            )
            validated = validate_response(response, request)
            outcome = validated["outcome"]
            if outcome == "refused":
                raise TransportError("refused", TransportEffect.NO_EFFECT)
            if outcome == "error":
                classification = (
                    TransportEffect.EFFECT_UNKNOWN if modifying else TransportEffect.NO_EFFECT
                )
                raise TransportError("remote_error", classification)
            broker_response = validated.get("broker_response")
            if not isinstance(broker_response, Mapping):
                classification = (
                    TransportEffect.EFFECT_UNKNOWN if modifying else TransportEffect.NO_EFFECT
                )
                raise TransportError("response_invalid", classification)
            return dict(broker_response)
        except TransportError:
            raise
        except (
            asyncio.IncompleteReadError,
            asyncio.TimeoutError,
            OSError,
            ssl.SSLError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TransportValidationError,
            TypeError,
            ValueError,
        ) as exc:
            classification = (
                TransportEffect.EFFECT_UNKNOWN
                if write_started and modifying
                else TransportEffect.NO_EFFECT
            )
            raise TransportError("response_unavailable", classification) from exc
        finally:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    def request_sync(
        self,
        operation: str,
        payload: Mapping[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Synchronous structural seam used by existing operator adapters."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.request(operation, payload, timeout_seconds=timeout_seconds)
            )
        raise TransportError("sync_context_invalid", TransportEffect.NO_EFFECT)


__all__ = ["RemoteWorkerBrokerClient"]
