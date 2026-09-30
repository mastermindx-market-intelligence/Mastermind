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
    TransportValidationError,
    encode_frame,
    validate_request,
)
from ops.executive_os.remote_worker_gateway_config import RemoteWorkerGatewayConfig


class RemoteWorkerGateway:
    """One-request-per-connection authenticated gateway with no durable state."""

    def __init__(self, config: RemoteWorkerGatewayConfig) -> None:
        self.config = config
        self._broker_client = WorkerBrokerClient(
            config.broker_socket_path,
            timeout_seconds=config.request_timeout_seconds,
        )
        # Deliberate seam for hermetic tests; production uses the fixed AF_UNIX
        # WorkerBrokerClient above and never accepts a caller-supplied socket.
        self.broker_call = self._call_broker
        self._ssl_context = self._build_server_ssl_context()

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
        return await self._broker_client.request(
            operation,
            payload,
            timeout_seconds=self.config.request_timeout_seconds,
        )

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            if not self._peer_is_expected_control(writer):
                return
            try:
                raw = await self._read_frame(reader)
                document = json.loads(raw.decode("utf-8", errors="strict"))
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
                    self.broker_call(
                        str(request["broker_operation"]),
                        dict(request["broker_request"]),
                    ),
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
            with suppress(Exception):
                await writer.wait_closed()

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
