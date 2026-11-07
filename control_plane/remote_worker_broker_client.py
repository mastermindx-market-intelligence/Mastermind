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
import secrets
import ssl
import time
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
    payload_retargets_authority,
    validate_response,
    MAX_HOST_OBSERVATION_RESPONSE_BYTES,
    MAX_SECRETARY_RESPONSE_BYTES,
    build_host_observation_request,
    build_secretary_request, build_meta_request,
    decode_host_observation_response,
    decode_secretary_request, decode_meta_request,
    decode_secretary_response, decode_meta_response,
    secretary_request_session_id,
    validate_host_ref,
    validate_secretary_native_id,
    validate_secretary_operation,
    validate_secretary_root_id,
)
from common import workspace_byok_read_contract as byok_workspace
from common.hermes_role_status_contract import (
    RoleStatusError, project_observation, validate_source_pins,
)

_READ_ONLY_OPERATIONS = frozenset(
    {
        "capacity-observe/v1",
        "attended-secret-canary",
        "ohf-identity",
        "ohf-materialization-status",
        "ohf-native-begin-status",
    }
)
_BOUND_PAYLOAD_IDENTITY_KEYS = frozenset({"session_epoch_id", "process_generation_id"})
_SECRETARY_TOTAL_BUDGET_SECONDS = 10.0


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
        self._host_observation: tuple[str, str, str] | None = None
        self._secretary_conversation: tuple[str, str, str, str, str] | None = None
        self._conversation_role: str | None = None
        operations = frozenset(allowed_operations)
        if not operations or any(not isinstance(value, str) for value in operations):
            raise TransportValidationError("remote broker client operations are invalid")
        normalized_identity = dict(identity)
        for operation in operations:
            build_request(normalized_identity, operation, {})
        payload_identity = self._validated_payload_identity(bound_payload_identity or {})
        self.identity = normalized_identity
        self.allowed_operations = operations
        self.bound_payload_identity = payload_identity

    @classmethod
    def for_host_observation(
        cls, binding: BrokerTransportBinding, *, host_ref: str,
        expected_host_binding_sha256: str, expected_implementation_sha: str,
    ) -> RemoteWorkerBrokerClient:
        """Bind the fixed read family without manufacturing a Worker identity."""
        if not isinstance(binding, BrokerTransportBinding):
            raise TransportValidationError("host observation binding is invalid")
        validate_host_ref(host_ref)
        try:
            validate_source_pins(expected_host_binding_sha256, expected_implementation_sha)
        except RoleStatusError:
            raise TransportValidationError("host observation binding is invalid") from None
        instance = cls.__new__(cls)
        instance.binding = binding
        instance.identity = {}
        instance.allowed_operations = frozenset()
        instance.bound_payload_identity = {}
        instance._host_observation = (host_ref, expected_host_binding_sha256, expected_implementation_sha)
        instance._secretary_conversation = None
        instance._conversation_role = None
        return instance

    @classmethod
    def _for_conversation(
        cls, binding: BrokerTransportBinding, *, host_ref: str, root_id: str,
        session_id: str, expected_host_binding_sha256: str,
        expected_implementation_sha: str, role: str,
    ) -> RemoteWorkerBrokerClient:
        """Bind one explicit conversation without manufacturing a Worker identity."""
        if type(role) is not str or role not in {"mmsecretary", "mmmeta"}:
            raise TransportValidationError("native conversation role is invalid")
        if not isinstance(binding, BrokerTransportBinding):
            raise TransportValidationError("secretary conversation binding is invalid")
        validate_host_ref(host_ref)
        validate_secretary_root_id(root_id)
        try:
            validate_source_pins(expected_host_binding_sha256, expected_implementation_sha)
        except RoleStatusError:
            raise TransportValidationError("secretary conversation binding is invalid") from None
        try:
            session = validate_secretary_native_id(session_id)
        except TransportValidationError:
            raise TransportValidationError("secretary conversation binding is invalid") from None
        instance = cls.__new__(cls)
        instance.binding = binding
        instance.identity = {}
        instance.allowed_operations = frozenset()
        instance.bound_payload_identity = {}
        instance._host_observation = None
        instance._conversation_role = role
        instance._secretary_conversation = (
            host_ref, root_id, session,
            expected_host_binding_sha256, expected_implementation_sha,
        )
        return instance

    @classmethod
    def for_secretary_conversation(
        cls, binding: BrokerTransportBinding, *, host_ref: str, root_id: str,
        session_id: str, expected_host_binding_sha256: str,
        expected_implementation_sha: str,
    ) -> RemoteWorkerBrokerClient:
        return cls._for_conversation(
            binding, host_ref=host_ref, root_id=root_id, session_id=session_id,
            expected_host_binding_sha256=expected_host_binding_sha256,
            expected_implementation_sha=expected_implementation_sha, role="mmsecretary")


    @classmethod
    def for_meta_conversation(
        cls, binding: BrokerTransportBinding, *, host_ref: str, root_id: str,
        session_id: str, expected_host_binding_sha256: str,
        expected_implementation_sha: str,
    ) -> RemoteWorkerBrokerClient:
        return cls._for_conversation(
            binding, host_ref=host_ref, root_id=root_id, session_id=session_id,
            expected_host_binding_sha256=expected_host_binding_sha256,
            expected_implementation_sha=expected_implementation_sha, role="mmmeta")

    async def read_hermes_roles(self) -> dict[str, Any]:
        """Read the fixed pair once under one total, at-most-four-second budget."""
        if self._host_observation is None:
            raise TransportError("host_observation_not_bound", TransportEffect.NO_EFFECT)
        host_ref, expected_binding, expected_implementation = self._host_observation
        request = build_host_observation_request(host_ref, secrets.token_hex(32))
        budget = min(4.0, float(self.binding.timeout_seconds))
        loop = asyncio.get_running_loop()
        deadline = loop.time() + budget
        writer = None
        try:
            async with asyncio.timeout_at(deadline):
                reader, writer = await self._open_connection()
                if not self._server_pin_matches(writer):
                    return byok_workspace.unavailable()
                writer.write(encode_frame(self._canonical_bytes(request)))
                await writer.drain()
                header = await reader.readexactly(4)
                size = int.from_bytes(header, "big")
                if not 0 < size <= MAX_HOST_OBSERVATION_RESPONSE_BYTES:
                    return byok_workspace.unavailable()
                raw = await reader.readexactly(size)
                response = decode_host_observation_response(raw, request)
                if loop.time() >= deadline:
                    return byok_workspace.unavailable()
                if response["state"] == "UNAVAILABLE":
                    return byok_workspace.unavailable(response["reason_code"])
                result = project_observation(
                    response["observation"], expected_host_binding_sha256=expected_binding,
                    expected_implementation_sha=expected_implementation, now_ms=time.time_ns() // 1_000_000,
                )
                if loop.time() >= deadline:
                    return byok_workspace.unavailable()
                if not byok_workspace.current(result, now_ms=time.time_ns() // 1_000_000):
                    return byok_workspace.unavailable("SOURCE_STALE")
                return result
        except RoleStatusError as exc:
            return byok_workspace.unavailable(exc.code)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, OSError, ssl.SSLError,
                TransportValidationError, TypeError, ValueError):
            return byok_workspace.unavailable()
        finally:
            if writer is not None:
                # Waiting for an SSL close after the deadline would add a
                # second budget. This read-only one-shot owns no reply writes.
                with suppress(Exception):
                    writer.close()
                    transport = getattr(writer, "transport", None)
                    if transport is not None:
                        transport.abort()

    async def _request_conversation(
        self, request: Mapping[str, Any], *, role: str, before_write=None
    ) -> dict[str, Any]:
        """Send one closed Secretary request over the incumbent mTLS transport.

        The conversation is bound to one session and one qualified source.
        There is no redirect, proxy fallback or retry.  A submit is never
        resent: any uncertainty after the framed write is EFFECT_UNKNOWN.
        """
        selection = self._secretary_conversation
        if (type(role) is not str or role not in {"mmsecretary", "mmmeta"}
                or selection is None or self._host_observation is not None
                or self._conversation_role != role):
            raise TransportError("secretary_not_bound" if role == "mmsecretary" else "meta_not_bound",
                                 TransportEffect.NO_EFFECT)
        build_wire, decode_request, decode_response = (
            (build_secretary_request, decode_secretary_request, decode_secretary_response)
            if role == "mmsecretary" else
            (build_meta_request, decode_meta_request, decode_meta_response))
        host_ref, root_id, session_id, expected_binding, expected_implementation = selection
        try:
            operation = validate_secretary_operation(request)
            if secretary_request_session_id(operation) != session_id:
                raise TransportValidationError("secretary session is not bound")
            wire = build_wire(
                host_ref, root_id, expected_binding, expected_implementation, operation,
            )
            sealed = self._canonical_bytes(wire)
            wire = decode_request(sealed)
            operation = wire["request"]
            frame = encode_frame(sealed)
        except TransportValidationError as exc:
            raise TransportError(
                "secretary_request_invalid" if role == "mmsecretary" else "meta_request_invalid",
                TransportEffect.NO_EFFECT
            ) from exc
        modifying = operation["operation"] == "submit"
        if modifying and not callable(before_write):
            raise TransportError("before_write_required", TransportEffect.NO_EFFECT)
        # One total deadline covers connect, pin, write and reply.  There is no
        # renewable per-read budget.
        budget = min(_SECRETARY_TOTAL_BUDGET_SECONDS, float(self.binding.timeout_seconds))
        loop = asyncio.get_running_loop()
        deadline = loop.time() + budget
        writer = None
        write_started = False
        try:
            async with asyncio.timeout_at(deadline):
                try:
                    reader, writer = await self._open_connection()
                except (asyncio.TimeoutError, OSError, ssl.SSLError,
                        TransportValidationError) as exc:
                    raise TransportError("unavailable", TransportEffect.NO_EFFECT) from exc
                if not self._server_pin_matches(writer):
                    raise TransportError(
                        "server_identity_mismatch", TransportEffect.NO_EFFECT
                    )
                if before_write is not None:
                    # The guard runs once, after the connection and its pin,
                    # immediately before the single framed write.  A refusal or
                    # a failure here has produced no effect.
                    try:
                        callback_request = json.loads(self._canonical_bytes(operation))
                        if (before_write(operation["operation"], callback_request) is not None
                                or self._canonical_bytes(callback_request) != self._canonical_bytes(operation)):
                            raise ValueError("invalid local foreground guard")
                    except Exception:
                        raise TransportError(
                            "before_write_refused", TransportEffect.NO_EFFECT
                        ) from None
                if loop.time() >= deadline:
                    raise asyncio.TimeoutError()
                write_started = True
                writer.write(frame)
                await writer.drain()
                header = await reader.readexactly(4)
                size = int.from_bytes(header, "big")
                if not 0 < size <= MAX_SECRETARY_RESPONSE_BYTES:
                    raise TransportError(
                        "response_invalid",
                        TransportEffect.EFFECT_UNKNOWN
                        if (write_started and modifying)
                        else TransportEffect.NO_EFFECT,
                    )
                raw = await reader.readexactly(size)
                response = decode_response(raw, wire)
                if loop.time() >= deadline:
                    raise asyncio.TimeoutError()
                if response["outcome"] == "refused":
                    # A refusal proven before forwarding is not an effect.
                    raise TransportError("refused", TransportEffect.NO_EFFECT)
                return dict(response["result"])
        except TransportError:
            raise
        except asyncio.CancelledError as exc:
            # The framed write may already have reached the Secretary owner.
            # Cancellation cannot authorize another submit.
            raise TransportError(
                "secretary_request_cancelled" if role == "mmsecretary" else "meta_request_cancelled",
                TransportEffect.EFFECT_UNKNOWN if write_started and modifying else TransportEffect.NO_EFFECT,
            ) from exc
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
            raise TransportError(
                "response_unavailable",
                TransportEffect.EFFECT_UNKNOWN
                if (write_started and modifying)
                else TransportEffect.NO_EFFECT,
            ) from exc
        finally:
            if writer is not None:
                # Closing and aborting must not wait past the total deadline.
                with suppress(Exception):
                    writer.close()
                    transport = getattr(writer, "transport", None)
                    if transport is not None:
                        transport.abort()

    async def request_secretary(
        self, request: Mapping[str, Any], *, before_write=None,
    ) -> dict[str, Any]:
        return await self._request_conversation(request, role="mmsecretary", before_write=before_write)


    async def request_meta(
        self, request: Mapping[str, Any], *, before_write=None,
    ) -> dict[str, Any]:
        return await self._request_conversation(request, role="mmmeta", before_write=before_write)

    @staticmethod
    def _validated_payload_identity(value: Mapping[str, str]) -> dict[str, str]:
        payload_identity = dict(value)
        if payload_identity and set(payload_identity) != _BOUND_PAYLOAD_IDENTITY_KEYS:
            raise TransportValidationError("remote broker payload identity is invalid")
        if any(
            not isinstance(item, str) or COMMAND_ID_RE.fullmatch(item) is None
            for item in payload_identity.values()
        ):
            raise TransportValidationError("remote broker payload identity is invalid")
        return payload_identity

    def bind_payload_identity(
        self, *, session_epoch_id: str, process_generation_id: str
    ) -> None:
        """Bind one Runtime-issued OHF generation after allocation, exactly once."""

        if self._host_observation is not None:
            raise TransportValidationError("host observation cannot bind a Worker identity")
        if self._secretary_conversation is not None:
            raise TransportValidationError(
                "secretary conversation cannot bind a Worker identity"
            )

        payload_identity = self._validated_payload_identity({
            "session_epoch_id": session_epoch_id,
            "process_generation_id": process_generation_id,
        })
        if self.bound_payload_identity:
            if self.bound_payload_identity != payload_identity:
                raise TransportValidationError(
                    "remote broker payload identity is already bound"
                )
            return
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
        foreground_start_receipt=None,
        before_write=None,
    ) -> dict[str, Any]:
        if operation not in self.allowed_operations:
            raise TransportError("operation_not_allowed", TransportEffect.NO_EFFECT)
        if not isinstance(payload, Mapping):
            raise TransportError("request_invalid", TransportEffect.NO_EFFECT)
        try:
            retargets = payload_retargets_authority(
                operation,
                payload,
                self.identity,
                bound_payload_identity=self.bound_payload_identity,
            )
        except TransportValidationError as exc:
            raise TransportError("request_invalid", TransportEffect.NO_EFFECT) from exc
        if retargets:
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
            from control_plane.foreground_operation import require_start_transmission, ForegroundOperationRefusal
            try:
                require_start_transmission(operation, json.loads(encoded)["broker_request"],
                                           foreground_start_receipt)
            except (ForegroundOperationRefusal, KeyError, TypeError, ValueError):
                raise TransportError("foreground_start_refused", TransportEffect.NO_EFFECT) from None
            if before_write is not None:
                try:
                    if (operation not in {"ohf-start", "ohf-resume", "ohf-begin-turn"}
                            or not callable(before_write)
                            or before_write(operation, json.loads(encoded)["broker_request"]) is not None):
                        raise ValueError("invalid local foreground guard")
                except Exception:
                    raise TransportError("foreground_start_refused", TransportEffect.NO_EFFECT) from None
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
        before_write=None,
    ) -> dict[str, Any]:
        """Synchronous structural seam used by existing operator adapters."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.request(operation, payload, timeout_seconds=timeout_seconds,
                             **({"before_write": before_write} if before_write is not None else {}))
            )
        raise TransportError("sync_context_invalid", TransportEffect.NO_EFFECT)


__all__ = ["RemoteWorkerBrokerClient"]
