"""Stateless mTLS gateway from MH1 transport to the host-local Worker Broker.

The gateway authenticates one control certificate, validates one closed remote
request, forwards only its fixed broker operation/payload to the configured
AF_UNIX Worker Broker, returns one identity-bound response, and closes.  It
owns no Job/Attempt/Worker state, retry ledger, queue, cursor, or provider state.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import ssl
import time
from contextlib import suppress
from typing import Any, Mapping

from control_plane.executive_worker_broker import WorkerBrokerClient
from control_plane.remote_worker_transport import (
    REMOTE_BROKER_RESPONSE_SCHEMA,
    REMOTE_HERMES_SECRETARY_REQUEST_SCHEMA, REMOTE_HERMES_META_REQUEST_SCHEMA,
    MAX_SECRETARY_RESPONSE_BYTES,
    build_secretary_response, decode_secretary_request, build_meta_response, decode_meta_request,
    TransportEffect, TransportError,
    TransportValidationError,
    encode_frame,
    validate_request,
    REMOTE_HOST_OBSERVATION_REQUEST_SCHEMA,
    MAX_HOST_OBSERVATION_RESPONSE_BYTES,
    build_host_observation_response,
    decode_host_observation_request,
    decode_request_document,
)
from common.hermes_role_status_contract import RoleStatusError
from ops.executive_os.remote_worker_gateway_config import (
    FABRIC_BROKER_TARGET,
    GatewayConfig,
    HostObservationGatewayConfig,
    HermesSecretaryGatewayConfig, HermesConversationGatewayConfig,
    RemoteWorkerGatewayConfig,
)
from ops.executive_os.remote_assignment_control import seal_original_assignment


class RemoteWorkerGateway:
    """One-request-per-connection authenticated gateway with no durable state."""

    def __init__(self, config: GatewayConfig) -> None:
        if type(config) not in (RemoteWorkerGatewayConfig, HostObservationGatewayConfig,
                                HermesSecretaryGatewayConfig, HermesConversationGatewayConfig):
            raise TypeError("config must be a closed gateway profile")
        self.config = config
        self._host_observer = None
        self._secretary_forwarder = None
        self._secretary_host_binding_sha256 = None
        self._meta_forwarder = None
        self._meta_host_binding_sha256 = None
        self._broker_client = None
        self.broker_call = self._call_broker
        self._ssl_context = self._build_server_ssl_context()
        if type(config) is not RemoteWorkerGatewayConfig:
            return
        client_arguments: dict[str, Any] = {}
        if config.broker_target == FABRIC_BROKER_TARGET:
            # Only the explicit Fabric target pins the broker peer uid; the
            # socket path and identity always come from the config, never from
            # a caller-supplied override.
            client_arguments["expected_peer_uid"] = config.expected_broker_peer_uid
        self._broker_client = WorkerBrokerClient(
            config.broker_socket_path,
            timeout_seconds=config.request_timeout_seconds,
            **client_arguments,
        )
        # Deliberate seam for hermetic tests; production uses the fixed AF_UNIX
        # WorkerBrokerClient above and never accepts a caller-supplied socket.

    def _build_server_ssl_context(self) -> ssl.SSLContext:
        try:
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            context.minimum_version = ssl.TLSVersion.TLSv1_3
            context.maximum_version = ssl.TLSVersion.TLSv1_3
            context.verify_mode = ssl.CERT_REQUIRED
            context.load_verify_locations(cafile=str(self.config.ca_path))
            context.load_cert_chain(
                certfile=str(self.config.certificate_path),
                keyfile=str(self.config.key_path),
            )
            return context
        except (OSError, ssl.SSLError) as exc:
            raise ValueError("remote worker gateway TLS configuration is invalid") from exc

    async def start_server(self) -> asyncio.AbstractServer:
        """Start the explicit private-interface listener and return its handle."""

        return await asyncio.start_server(
            self._handle_connection,
            host=self.config.listen_host,
            port=self.config.listen_port,
            ssl=self._ssl_context,
            ssl_handshake_timeout=self.config.request_timeout_seconds,
            start_serving=True,
        )

    async def _call_broker(self, operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if type(self.config) is not RemoteWorkerGatewayConfig or self._broker_client is None:
            raise ValueError("host observation profile has no broker capability")
        return await self._broker_client.request(
            operation,
            payload,
            timeout_seconds=self.config.request_timeout_seconds,
        )

    async def _dispatch_authenticated(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if type(self.config) is not RemoteWorkerGatewayConfig:
            raise ValueError("host observation profile has no broker capability")
        if request["broker_operation"] == "assignment-seal":
            binding = self.config.assignment_control
            if binding is None:
                raise ValueError("gateway assignment Control is not configured")
            if self.config.broker_target == FABRIC_BROKER_TARGET:
                return await seal_original_assignment(binding, request, self.broker_call,
                                                      fabric_target=True)
            return await seal_original_assignment(binding, request, self.broker_call)
        return await self.broker_call(str(request["broker_operation"]),
                                      dict(request["broker_request"]))

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        host_read = False
        host_response_sent = False
        conversation_call = False
        conversation_response_sent = False
        started = asyncio.get_running_loop().time()
        try:
            if not self._peer_is_expected_control(writer):
                return
            try:
                raw = await self._read_frame(reader)
                document = decode_request_document(raw)
            except (
                asyncio.IncompleteReadError,
                asyncio.TimeoutError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                TransportValidationError,
            ):
                return
            if not isinstance(document, dict):
                return

            if document.get("schema") in (REMOTE_HERMES_SECRETARY_REQUEST_SCHEMA,
                                           REMOTE_HERMES_META_REQUEST_SCHEMA):
                conversation_call = True
                is_meta = document["schema"] == REMOTE_HERMES_META_REQUEST_SCHEMA
                decode = decode_meta_request if is_meta else decode_secretary_request
                dispatch = self._meta_request if is_meta else self._secretary_request
                try:
                    request = decode(raw)
                    deadline = started + min(10.0, float(self.config.request_timeout_seconds))
                    if asyncio.get_running_loop().time() >= deadline:
                        return
                    async with asyncio.timeout_at(deadline):
                        response = await dispatch(request, deadline=deadline)
                        encoded = self._canonical_response_bytes(response)
                        if len(encoded) > min(MAX_SECRETARY_RESPONSE_BYTES, self.config.max_frame_bytes):
                            return
                        if asyncio.get_running_loop().time() >= deadline:
                            return
                        writer.write(encode_frame(encoded))
                        await writer.drain()
                        conversation_response_sent = True
                except (asyncio.CancelledError, Exception):
                    # No forged nonexecution receipt after any possible native
                    # write. The original remote client owns reconciliation.
                    return
                return

            if document.get("schema") == REMOTE_HOST_OBSERVATION_REQUEST_SCHEMA:
                host_read = True
                try:
                    request = decode_host_observation_request(raw, expected_host_ref=self.config.host_ref)
                    deadline = started + min(4.0, float(self.config.request_timeout_seconds))
                    if asyncio.get_running_loop().time() >= deadline:
                        return
                    async with asyncio.timeout_at(deadline):
                        response = await self._observe_host_request(request)
                        encoded = self._canonical_response_bytes(response)
                        if len(encoded) > min(MAX_HOST_OBSERVATION_RESPONSE_BYTES, self.config.max_frame_bytes):
                            response = build_host_observation_response(request)
                            encoded = self._canonical_response_bytes(response)
                        writer.write(encode_frame(encoded))
                        await writer.drain()
                        host_response_sent = True
                except (asyncio.TimeoutError, TransportValidationError, OSError):
                    return
                return

            if type(self.config) is not RemoteWorkerGatewayConfig:
                # Refuse before entering the Worker grammar or any broker
                # callback, including authenticated status/collect requests.
                refusal = self._bound_response(document, outcome="refused", broker_response=None)
                if refusal is not None:
                    await self._write_response(writer, refusal)
                return

            try:
                request = validate_request(
                    document,
                    expected_host_ref=self.config.host_ref,
                    allowed_worker_ids=self.config.allowed_worker_ids,
                    allowed_operations=self.config.allowed_operations,
                )
            except TransportValidationError:
                refusal = self._bound_response(document, outcome="refused", broker_response=None)
                if refusal is not None:
                    await self._write_response(writer, refusal)
                return

            try:
                result = await asyncio.wait_for(
                    self._dispatch_authenticated(request),
                    timeout=self.config.request_timeout_seconds,
                )
                response = self._bound_response(
                    request,
                    outcome="ok",
                    broker_response=dict(result),
                )
            except Exception:
                # Never forward local socket paths, broker exceptions, or provider
                # details.  The control-side client applies modifying-operation
                # EFFECT_UNKNOWN law to a post-forward remote error.
                response = self._bound_response(
                    request,
                    outcome="error",
                    broker_response=None,
                )
            if response is not None:
                await self._write_response(writer, response)
        finally:
            writer.close()
            if ((host_read and not host_response_sent)
                    or (conversation_call and not conversation_response_sent)):
                with suppress(Exception):
                    transport = getattr(writer, "transport", None)
                    if transport is not None:
                        transport.abort()
            elif not host_read and not conversation_call:
                with suppress(Exception):
                    await writer.wait_closed()

    async def _secretary_request(self, request: Mapping[str, Any], *,
                                 deadline: float) -> dict[str, Any]:
        return await self._conversation_request(request, role="mmsecretary", deadline=deadline)

    async def _meta_request(self, request: Mapping[str, Any], *,
                            deadline: float) -> dict[str, Any]:
        return await self._conversation_request(request, role="mmmeta", deadline=deadline)

    async def _conversation_request(self, request: Mapping[str, Any], *,
                                    role: str, deadline: float) -> dict[str, Any]:
        """One bound native call; no Worker grammar, retry, or synthetic receipt."""
        if role == "mmsecretary":
            build_response = build_secretary_response
            allowed = type(self.config) in (HermesSecretaryGatewayConfig, HermesConversationGatewayConfig)
            binding = self.config.hermes_secretary_conversation if allowed else None
            forwarder, host_pin = self._secretary_forwarder, self._secretary_host_binding_sha256
        elif role == "mmmeta":
            build_response = build_meta_response
            allowed = type(self.config) is HermesConversationGatewayConfig
            binding = self.config.hermes_meta_conversation if allowed else None
            forwarder, host_pin = self._meta_forwarder, self._meta_host_binding_sha256
        else:
            raise TransportValidationError("native conversation role is invalid")

        def refused(code):
            return build_response(request, outcome="refused", result={"code": code})

        if not allowed:
            return refused("PROFILE_UNAVAILABLE")
        inner = request["request"]
        target = inner.get("target") if inner["operation"] == "submit" else inner
        if (request["host_ref"] != self.config.host_ref
                or request["root_id"] != binding.root_id
                or request["implementation_sha"] != binding.implementation_sha
                or request["host_binding_sha256"] != host_pin
                or target["session_id"] != binding.session_id):
            return refused("BINDING_CHANGED")
        if forwarder is None:
            return refused("SERVICE_UNAVAILABLE")
        try:
            result = await forwarder.request(inner, deadline=deadline)
        except TransportError as exc:
            if exc.classification is TransportEffect.NO_EFFECT:
                return refused("NATIVE_FORWARDING_UNAVAILABLE")
            raise
        return build_response(request, outcome="ok", result=result)

    async def _observe_host_request(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """One fixed host read; never enter the Worker Broker grammar."""
        if self.config.hermes_role_metadata_read is None or self._host_observer is None:
            return build_host_observation_response(request)
        try:
            observation = await self._host_observer.read_pair()
            return build_host_observation_response(request, observation=observation)
        except RoleStatusError as exc:
            return build_host_observation_response(request, reason_code=exc.code)
        except Exception:
            return build_host_observation_response(request)

    def _peer_is_expected_control(self, writer: asyncio.StreamWriter) -> bool:
        ssl_object = writer.get_extra_info("ssl_object")
        if ssl_object is None:
            return False
        certificate = ssl_object.getpeercert(binary_form=True)
        if not certificate:
            return False
        observed = hashlib.sha256(certificate).hexdigest()
        return observed == self.config.expected_control_fingerprint

    async def _read_frame(self, reader: asyncio.StreamReader) -> bytes:
        header = await asyncio.wait_for(
            reader.readexactly(4), timeout=self.config.request_timeout_seconds
        )
        size = int.from_bytes(header, "big")
        if size > self.config.max_frame_bytes:
            raise TransportValidationError("frame exceeds gateway ceiling")
        return await asyncio.wait_for(
            reader.readexactly(size), timeout=self.config.request_timeout_seconds
        )

    def _bound_response(
        self,
        request: Mapping[str, Any],
        *,
        outcome: str,
        broker_response: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        required = (
            "host_ref",
            "job_id",
            "attempt_id",
            "worker_id",
            "operation_id",
            "broker_operation",
            "request_sha256",
        )
        if any(not isinstance(request.get(key), str) for key in required):
            return None
        return {
            "schema": REMOTE_BROKER_RESPONSE_SCHEMA,
            "host_ref": request["host_ref"],
            "job_id": request["job_id"],
            "attempt_id": request["attempt_id"],
            "worker_id": request["worker_id"],
            "operation_id": request["operation_id"],
            "broker_operation": request["broker_operation"],
            "request_sha256": request["request_sha256"],
            "outcome": outcome,
            "broker_response": None if broker_response is None else dict(broker_response),
            "observed_at_ms": time.time_ns() // 1_000_000,
        }

    async def _write_response(
        self, writer: asyncio.StreamWriter, response: Mapping[str, Any]
    ) -> None:
        encoded = self._canonical_response_bytes(response)
        if len(encoded) > self.config.max_frame_bytes:
            bounded = dict(response)
            bounded["outcome"] = "error"
            bounded["broker_response"] = None
            encoded = self._canonical_response_bytes(bounded)
        writer.write(encode_frame(encoded))
        await asyncio.wait_for(
            writer.drain(), timeout=self.config.request_timeout_seconds
        )

    @staticmethod
    def _canonical_response_bytes(response: Mapping[str, Any]) -> bytes:
        try:
            return json.dumps(
                dict(response),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise TransportValidationError("gateway response is not canonical JSON") from exc
