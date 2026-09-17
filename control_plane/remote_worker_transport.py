"""Closed authenticated transport contract for the MH1 remote Worker Broker.

This module owns only wire validation, framing, local TLS binding, and transport
classification.  It does not select hosts/workers, own lifecycle state, retry
modifying work, or expose endpoints/certificate material in durable receipts.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import math
import re
import ssl
from pathlib import Path
from typing import Any, Mapping

REMOTE_BROKER_REQUEST_SCHEMA = "mastermind.remote_worker_broker_request/v1"
REMOTE_BROKER_RESPONSE_SCHEMA = "mastermind.remote_worker_broker_response/v1"
MAX_FRAME_BYTES = 1024 * 1024

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")
_BROKER_OPERATION_RE = re.compile(
    r"^(?:[A-Za-z0-9][A-Za-z0-9._-]{1,127}|"
    r"[A-Za-z0-9][A-Za-z0-9._-]{1,118}/v[1-9][0-9]{0,5})$"
)
_HOST_REF_RE = re.compile(r"^host-[0-9a-f]{64}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_RESERVED_UNBOUND_HOST_REFS = frozenset({"local-unbound"})
_REQUEST_KEYS = frozenset({
    "schema", "host_ref", "job_id", "attempt_id", "worker_id", "operation_id",
    "broker_operation", "request_sha256", "broker_request",
})
_RESPONSE_KEYS = frozenset({
    "schema", "host_ref", "job_id", "attempt_id", "worker_id", "operation_id",
    "broker_operation", "request_sha256", "outcome", "broker_response", "observed_at_ms",
})
_IDENTITY_KEYS = ("host_ref", "job_id", "attempt_id", "worker_id", "operation_id")


class TransportValidationError(ValueError):
    """A closed transport contract or local binding was invalid."""


class TransportEffect(enum.Enum):
    NO_EFFECT = "no_effect"
    EFFECT_UNKNOWN = "effect_unknown"


class TransportError(RuntimeError):
    """Sanitized remote transport failure with explicit effect classification."""

    def __init__(self, code: str, classification: TransportEffect) -> None:
        self.code = str(code)
        self.classification = classification
        super().__init__(f"remote worker transport {self.code}")


@dataclasses.dataclass(frozen=True)
class BrokerTransportBinding:
    """Root-managed local connection material; never part of the wire envelope."""

    endpoint: tuple[str, int]
    ca_path: Path
    client_cert_path: Path
    client_key_path: Path
    expected_server_fingerprint: str
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        try:
            host, port = self.endpoint
        except (TypeError, ValueError) as exc:
            raise TransportValidationError("transport binding is invalid") from exc
        if not isinstance(host, str) or not host or len(host) > 253:
            raise TransportValidationError("transport binding is invalid")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise TransportValidationError("transport binding is invalid")
        if not _HEX64_RE.fullmatch(str(self.expected_server_fingerprint)):
            raise TransportValidationError("transport binding is invalid")
        if not 0.1 <= float(self.timeout_seconds) <= 3600:
            raise TransportValidationError("transport binding is invalid")
        for value in (self.ca_path, self.client_cert_path, self.client_key_path):
            path = Path(value)
            if not path.is_absolute() or not path.is_file():
                raise TransportValidationError("transport binding is invalid")


def _canonical_bytes(value: Any) -> bytes:
    _reject_non_finite(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TransportValidationError("transport document is not canonical JSON") from exc


def _reject_non_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise TransportValidationError("transport document contains non-finite number")
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TransportValidationError("transport object keys must be strings")
            _reject_non_finite(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_non_finite(child)


def validate_host_ref(value: Any) -> str:
    if (
        not isinstance(value, str)
        or (
            _HEX64_RE.fullmatch(value) is None
            and _HOST_REF_RE.fullmatch(value) is None
        )
        or value in _RESERVED_UNBOUND_HOST_REFS
    ):
        raise TransportValidationError("transport identity is invalid")
    return value


def validate_broker_operation(value: Any) -> str:
    if not isinstance(value, str) or _BROKER_OPERATION_RE.fullmatch(value) is None:
        raise TransportValidationError("transport identity is invalid")
    return value


def _validate_id(name: str, value: Any) -> str:
    if name == "host_ref":
        return validate_host_ref(value)
    if name == "broker_operation":
        return validate_broker_operation(value)
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise TransportValidationError("transport identity is invalid")
    return value


def request_sha256(request: Mapping[str, Any]) -> str:
    document = dict(request)
    document.pop("request_sha256", None)
    return hashlib.sha256(_canonical_bytes(document)).hexdigest()


def build_request(
    identity: Mapping[str, Any], broker_operation: str, broker_request: Mapping[str, Any]
) -> dict[str, Any]:
    if set(identity) != set(_IDENTITY_KEYS):
        raise TransportValidationError("transport identity is invalid")
    document: dict[str, Any] = {
        "schema": REMOTE_BROKER_REQUEST_SCHEMA,
        **{key: _validate_id(key, identity[key]) for key in _IDENTITY_KEYS},
        "broker_operation": _validate_id("broker_operation", broker_operation),
        "broker_request": dict(broker_request),
    }
    document["request_sha256"] = request_sha256(document)
    return document


def validate_request(
    request: Mapping[str, Any],
    *,
    expected_host_ref: str,
    allowed_worker_ids: set[str] | frozenset[str],
    allowed_operations: set[str] | frozenset[str],
) -> dict[str, Any]:
    if not isinstance(request, Mapping) or set(request) != _REQUEST_KEYS:
        raise TransportValidationError("remote request shape is invalid")
    if request.get("schema") != REMOTE_BROKER_REQUEST_SCHEMA:
        raise TransportValidationError("remote request schema is invalid")
    for key in _IDENTITY_KEYS:
        _validate_id(key, request.get(key))
    if request["host_ref"] != expected_host_ref:
        raise TransportValidationError("remote request identity is invalid")
    if request["worker_id"] not in allowed_worker_ids:
        raise TransportValidationError("remote request identity is invalid")
    operation = _validate_id("broker_operation", request.get("broker_operation"))
    if operation not in allowed_operations:
        raise TransportValidationError("remote request operation is not allowed")
    payload = request.get("broker_request")
    if not isinstance(payload, Mapping):
        raise TransportValidationError("remote request payload is invalid")
    if len(_canonical_bytes(dict(request))) > MAX_FRAME_BYTES:
        raise TransportValidationError("request exceeds transport ceiling")
    actual_hash = request.get("request_sha256")
    if not isinstance(actual_hash, str) or not _HEX64_RE.fullmatch(actual_hash):
        raise TransportValidationError("remote request hash is invalid")
    if actual_hash != request_sha256(request):
        raise TransportValidationError("remote request hash is invalid")
    return dict(request)


def validate_response(response: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(response, Mapping) or set(response) != _RESPONSE_KEYS:
        raise TransportValidationError("remote response shape is invalid")
    if response.get("schema") != REMOTE_BROKER_RESPONSE_SCHEMA:
        raise TransportValidationError("remote response schema is invalid")
    for key in _IDENTITY_KEYS:
        _validate_id(key, response.get(key))
        if response.get(key) != request.get(key):
            raise TransportValidationError("remote response identity does not match request")
    if response.get("broker_operation") != request.get("broker_operation"):
        raise TransportValidationError("remote response identity does not match request")
    if response.get("request_sha256") != request.get("request_sha256"):
        raise TransportValidationError("remote response identity does not match request")
    if response.get("outcome") not in {"ok", "refused", "error"}:
        raise TransportValidationError("remote response outcome is invalid")
    observed = response.get("observed_at_ms")
    if isinstance(observed, bool) or not isinstance(observed, int) or observed < 0:
        raise TransportValidationError("remote response observation is invalid")
    if len(_canonical_bytes(dict(response))) > MAX_FRAME_BYTES:
        raise TransportValidationError("response exceeds transport ceiling")
    return dict(response)


def encode_frame(payload: bytes) -> bytes:
    if not isinstance(payload, (bytes, bytearray)):
        raise TransportValidationError("frame payload must be bytes")
    payload = bytes(payload)
    if len(payload) > MAX_FRAME_BYTES:
        raise TransportValidationError("frame exceeds transport ceiling")
    return len(payload).to_bytes(4, "big") + payload


def decode_frame(frame: bytes) -> bytes:
    if not isinstance(frame, (bytes, bytearray)) or len(frame) < 4:
        raise TransportValidationError("frame is truncated")
    frame = bytes(frame)
    size = int.from_bytes(frame[:4], "big")
    if size > MAX_FRAME_BYTES:
        raise TransportValidationError("frame exceeds transport ceiling")
    if len(frame) < 4 + size:
        raise TransportValidationError("frame is truncated")
    if len(frame) != 4 + size:
        raise TransportValidationError("frame has trailing bytes")
    return frame[4:]


def build_client_ssl_context(binding: BrokerTransportBinding) -> ssl.SSLContext:
    try:
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(binding.ca_path))
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        context.load_cert_chain(
            certfile=str(binding.client_cert_path), keyfile=str(binding.client_key_path)
        )
        return context
    except (OSError, ssl.SSLError) as exc:
        raise TransportValidationError("transport binding TLS material is invalid") from exc