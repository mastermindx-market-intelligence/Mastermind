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

from common.hermes_role_status_contract import (
    RoleStatusError, closed_json, validate_observation, validate_source_pins,
)

REMOTE_BROKER_REQUEST_SCHEMA = "mastermind.remote_worker_broker_request/v1"
REMOTE_BROKER_RESPONSE_SCHEMA = "mastermind.remote_worker_broker_response/v1"
MAX_FRAME_BYTES = 1024 * 1024
REMOTE_HOST_OBSERVATION_REQUEST_SCHEMA = "mastermind.remote_host_observation_request/v1"
REMOTE_HOST_OBSERVATION_RESPONSE_SCHEMA = "mastermind.remote_host_observation_response/v1"
HERMES_ROLE_OBSERVATION_OPERATION = "hermes-role-metadata-read/v1"
MAX_HOST_OBSERVATION_REQUEST_BYTES = 1024
MAX_HOST_OBSERVATION_RESPONSE_BYTES = 8192
REMOTE_HERMES_SECRETARY_REQUEST_SCHEMA = "mastermind.remote_hermes_secretary_request/v1"
REMOTE_HERMES_SECRETARY_RESPONSE_SCHEMA = "mastermind.remote_hermes_secretary_response/v1"
MAX_SECRETARY_REQUEST_BYTES = 64 * 1024
MAX_SECRETARY_RESPONSE_BYTES = 512 * 1024
_HOST_REQUEST_KEYS = frozenset({"schema", "host_ref", "operation", "nonce", "request_sha256"})
_HOST_RESPONSE_KEYS = _HOST_REQUEST_KEYS | {"state", "reason_code", "observation"}
_HOST_UNAVAILABLE_REASONS = frozenset({"SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "SOURCE_STALE"})

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
_BOUND_AUTHORITY_KEYS = frozenset({"host_ref", "job_id", "attempt_id", "worker_id"})
_BOUND_PAYLOAD_IDENTITY_KEYS = frozenset({"session_epoch_id", "process_generation_id"})
_ATTEMPT_RUN_OPERATIONS = frozenset({
    "start", "status", "collect", "cancel", "validate", "attended-secret-canary",
    "assignment-seal", "assignment-seal-prepare", "assignment-seal-commit", "assignment-seal-finalize",
})
_SECRETARY_REQUEST_KEYS = frozenset({
    "schema", "host_ref", "root_id", "host_binding_sha256",
    "implementation_sha", "request", "request_sha256",
})
_SECRETARY_RESPONSE_KEYS = frozenset({
    "schema", "host_ref", "root_id", "host_binding_sha256",
    "implementation_sha", "request_sha256", "outcome", "result",
})
_SECRETARY_REFUSAL_KEYS = frozenset({"code"})
_SECRETARY_OUTCOMES = frozenset({"ok", "refused"})
_SECRETARY_OBSERVE_KEYS = frozenset({"operation", "session_id"})
_SECRETARY_SUBMIT_KEYS = frozenset({"operation", "target", "submission_id", "text"})
_SECRETARY_READ_ORIGINAL_KEYS = frozenset({
    "operation", "session_id", "submission_id", "input_sha256",
})
_SECRETARY_READ_ORIGINAL_OPTIONAL_KEYS = frozenset({"admission_id"})
_SECRETARY_NATIVE_RESULT_SCHEMA = "mastermind.hermes_secretary_native_control/v1"
_SECRETARY_NATIVE_RESULT_STATUSES = frozenset({
    "TARGET", "OBSERVED", "ADMITTED", "NOT_SUBMITTED", "REFUSED",
    "EFFECT_UNKNOWN", "UNAVAILABLE",
})
_SECRETARY_REFUSAL_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_SECRETARY_NATIVE_ID_MAX = 1024
_SECRETARY_NATIVE_MAX_INPUT_BYTES = 16 * 1024
_SECRETARY_NATIVE_TARGET_KEYS = frozenset({
    "profile_id", "session_id", "principal_id", "instance_id",
    "authority_epoch", "revision", "execution_generation",
})


REMOTE_HERMES_META_REQUEST_SCHEMA = "mastermind.remote_hermes_meta_request/v1"
REMOTE_HERMES_META_RESPONSE_SCHEMA = "mastermind.remote_hermes_meta_response/v1"
_META_NATIVE_RESULT_SCHEMA = "mastermind.hermes_meta_native_control/v1"


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


def payload_retargets_authority(
    broker_operation: str,
    payload: Mapping[str, Any],
    identity: Mapping[str, Any],
    *,
    bound_payload_identity: Mapping[str, str] | None = None,
) -> bool:
    """Return whether a broker payload disagrees with its authenticated envelope.

    Ordinary Worker Broker runs are Attempt-owned, so their ``run_id`` aliases
    the outer ``attempt_id``.  OHF generation identities remain bound only when
    the control-side owner supplies their established values; the gateway does
    not invent a second generation registry.
    """

    operation = validate_broker_operation(broker_operation)
    if not isinstance(payload, Mapping) or set(identity) != set(_IDENTITY_KEYS):
        raise TransportValidationError("remote request payload identity is invalid")
    normalized_identity = {
        key: _validate_id(key, identity.get(key)) for key in _IDENTITY_KEYS
    }
    payload_identity: Mapping[str, str] | None
    if bound_payload_identity is None:
        payload_identity = None
    elif isinstance(bound_payload_identity, Mapping):
        payload_identity = bound_payload_identity
    else:
        raise TransportValidationError("remote request payload identity is invalid")

    def retargets(value: Any) -> bool:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if not isinstance(key, str):
                    raise TransportValidationError(
                        "remote request payload identity is invalid"
                    )
                if (
                    key in _BOUND_AUTHORITY_KEYS
                    and child != normalized_identity[key]
                ):
                    return True
                if (
                    key == "run_id"
                    and operation in _ATTEMPT_RUN_OPERATIONS
                    and child != normalized_identity["attempt_id"]
                ):
                    return True
                if (
                    payload_identity is not None
                    and key in _BOUND_PAYLOAD_IDENTITY_KEYS
                ):
                    expected = payload_identity.get(key)
                    if expected is None or child != expected:
                        return True
                if retargets(child):
                    return True
            return False
        if isinstance(value, (list, tuple)):
            return any(retargets(child) for child in value)
        return False

    return retargets(payload)


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
    envelope_identity = {key: request[key] for key in _IDENTITY_KEYS}
    if payload_retargets_authority(operation, payload, envelope_identity):
        raise TransportValidationError("remote request payload retargets authority")
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


def decode_request_document(raw: bytes) -> dict[str, Any]:
    """Strictly decode a bounded frame after the incumbent peer authentication."""
    try:
        value = closed_json(raw, limit=MAX_FRAME_BYTES)
    except RoleStatusError:
        raise TransportValidationError("remote request JSON is invalid") from None
    if type(value) is not dict:
        raise TransportValidationError("remote request JSON is invalid")
    return value


def build_host_observation_request(host_ref: str, nonce: str) -> dict[str, Any]:
    value = {"schema": REMOTE_HOST_OBSERVATION_REQUEST_SCHEMA,
             "host_ref": validate_host_ref(host_ref),
             "operation": HERMES_ROLE_OBSERVATION_OPERATION, "nonce": nonce}
    value["request_sha256"] = request_sha256(value)
    return validate_host_observation_request(value, expected_host_ref=host_ref)


def validate_host_observation_request(value, *, expected_host_ref: str) -> dict[str, Any]:
    validate_host_ref(expected_host_ref)
    if (type(value) is not dict or set(value) != _HOST_REQUEST_KEYS
            or value["schema"] != REMOTE_HOST_OBSERVATION_REQUEST_SCHEMA
            or value["host_ref"] != expected_host_ref
            or value["operation"] != HERMES_ROLE_OBSERVATION_OPERATION
            or type(value["nonce"]) is not str or _HEX64_RE.fullmatch(value["nonce"]) is None
            or type(value["request_sha256"]) is not str
            or _HEX64_RE.fullmatch(value["request_sha256"]) is None
            or value["request_sha256"] != request_sha256(value)
            or len(_canonical_bytes(value)) > MAX_HOST_OBSERVATION_REQUEST_BYTES):
        raise TransportValidationError("remote host observation request is invalid")
    return dict(value)


def decode_host_observation_request(raw: bytes, *, expected_host_ref: str) -> dict[str, Any]:
    if len(raw) > MAX_HOST_OBSERVATION_REQUEST_BYTES:
        raise TransportValidationError("remote host observation request exceeds ceiling")
    return validate_host_observation_request(decode_request_document(raw), expected_host_ref=expected_host_ref)


def validate_host_observation_response(value, request) -> dict[str, Any]:
    validate_host_observation_request(request, expected_host_ref=request.get("host_ref"))
    if (type(value) is not dict or set(value) != _HOST_RESPONSE_KEYS
            or value["schema"] != REMOTE_HOST_OBSERVATION_RESPONSE_SCHEMA
            or any(value[key] != request[key] for key in ("host_ref", "operation", "nonce", "request_sha256"))):
        raise TransportValidationError("remote host observation response is invalid")
    if value["state"] == "OBSERVED":
        if value["reason_code"] != "OBSERVED":
            raise TransportValidationError("remote host observation response is invalid")
        try:
            validate_observation(value["observation"])
        except RoleStatusError:
            raise TransportValidationError("remote host observation response is invalid") from None
    elif (value["state"] != "UNAVAILABLE" or type(value["reason_code"]) is not str
          or value["reason_code"] not in _HOST_UNAVAILABLE_REASONS or value["observation"] is not None):
        raise TransportValidationError("remote host observation response is invalid")
    raw = _canonical_bytes(value)
    if len(raw) > MAX_HOST_OBSERVATION_RESPONSE_BYTES:
        raise TransportValidationError("remote host observation response exceeds ceiling")
    return json.loads(raw)


def build_host_observation_response(request, *, observation=None, reason_code="SOURCE_UNAVAILABLE") -> dict[str, Any]:
    value = {key: request[key] for key in ("host_ref", "operation", "nonce", "request_sha256")}
    value.update({"schema": REMOTE_HOST_OBSERVATION_RESPONSE_SCHEMA,
                  "state": "OBSERVED" if observation is not None else "UNAVAILABLE",
                  "reason_code": "OBSERVED" if observation is not None else reason_code,
                  "observation": observation})
    return validate_host_observation_response(value, request)


def decode_host_observation_response(raw: bytes, request) -> dict[str, Any]:
    try:
        value = closed_json(raw, limit=MAX_HOST_OBSERVATION_RESPONSE_BYTES)
    except RoleStatusError:
        raise TransportValidationError("remote host observation response JSON is invalid") from None
    return validate_host_observation_response(value, request)


# --- Remote Hermes Secretary wire family -------------------------------------
#
# The native Secretary admission owner lives in
# integrations/hermes_runtime/native_session_control.py.  The control_plane
# layer must not depend on integrations (see
# control_plane/github_review_socket_contract.py), so the native identifier,
# target and text rules are repeated here verbatim and pinned by a parity test
# instead of imported.  These validators only inspect the document; they never
# reach a native client or a runtime.


def validate_secretary_native_id(value: Any) -> str:
    """Native Secretary identifier semantics; a bool is never an identifier."""
    if (
        type(value) is not str
        or not value
        or len(value) > _SECRETARY_NATIVE_ID_MAX
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise TransportValidationError("secretary native identity is invalid")
    return value


def validate_secretary_native_text(value: Any) -> str:
    """Native Secretary finite input semantics; bounded UTF-8 text."""
    if (
        type(value) is not str
        or not value.strip()
        or len(value.encode("utf-8")) > _SECRETARY_NATIVE_MAX_INPUT_BYTES
    ):
        raise TransportValidationError("secretary native text is invalid")
    return value


def validate_secretary_native_target(value: Any) -> dict[str, Any]:
    """Native Secretary target semantics; exact keys and bool-is-not-int."""
    if type(value) is not dict or set(value) != _SECRETARY_NATIVE_TARGET_KEYS:
        raise TransportValidationError("secretary native target is invalid")
    for key in ("profile_id", "session_id", "principal_id", "instance_id"):
        validate_secretary_native_id(value[key])
    for key in ("authority_epoch", "revision", "execution_generation"):
        item = value[key]
        if type(item) is not int or item < (1 if key == "authority_epoch" else 0):
            raise TransportValidationError("secretary native target is invalid")
    return dict(value)


def validate_secretary_operation(value: Any) -> dict[str, Any]:
    """Validate one closed native Secretary operation request."""
    if type(value) is not dict:
        raise TransportValidationError("secretary request is invalid")
    operation = value.get("operation")
    if operation == "observe":
        if set(value) != _SECRETARY_OBSERVE_KEYS:
            raise TransportValidationError("secretary request is invalid")
        validate_secretary_native_id(value["session_id"])
    elif operation == "submit":
        if set(value) != _SECRETARY_SUBMIT_KEYS:
            raise TransportValidationError("secretary request is invalid")
        validate_secretary_native_target(value["target"])
        validate_secretary_native_id(value["submission_id"])
        validate_secretary_native_text(value["text"])
    elif operation == "read_original":
        keys = set(value)
        if keys not in (
            _SECRETARY_READ_ORIGINAL_KEYS,
            _SECRETARY_READ_ORIGINAL_KEYS | _SECRETARY_READ_ORIGINAL_OPTIONAL_KEYS,
        ):
            raise TransportValidationError("secretary request is invalid")
        validate_secretary_native_id(value["session_id"])
        validate_secretary_native_id(value["submission_id"])
        digest = value["input_sha256"]
        if type(digest) is not str or _HEX64_RE.fullmatch(digest) is None:
            raise TransportValidationError("secretary request is invalid")
        if "admission_id" in value:
            validate_secretary_native_id(value["admission_id"])
    else:
        raise TransportValidationError("secretary request is invalid")
    return dict(value)


def secretary_request_session_id(value: Any) -> str:
    """Return the native session id that one closed request targets."""
    request = validate_secretary_operation(value)
    if request["operation"] == "submit":
        return request["target"]["session_id"]
    return request["session_id"]


def validate_secretary_root_id(value: Any) -> str:
    """The bounded root identifier carried by the Secretary wire family."""
    return _validate_id("root_id", value)


def _validate_secretary_pins(host_binding_sha256: Any, implementation_sha: Any) -> None:
    try:
        validate_source_pins(host_binding_sha256, implementation_sha)
    except RoleStatusError:
        raise TransportValidationError("secretary source pins are invalid") from None


def _conversation_schemas(role: str) -> tuple[str, str, str]:
    # Selected by an installed constructor, never by an optional request field.
    if type(role) is str and role == "mmsecretary":
        return (REMOTE_HERMES_SECRETARY_REQUEST_SCHEMA,
                REMOTE_HERMES_SECRETARY_RESPONSE_SCHEMA, _SECRETARY_NATIVE_RESULT_SCHEMA)
    if type(role) is str and role == "mmmeta":
        return (REMOTE_HERMES_META_REQUEST_SCHEMA,
                REMOTE_HERMES_META_RESPONSE_SCHEMA, _META_NATIVE_RESULT_SCHEMA)
    raise TransportValidationError("native conversation role is invalid")


def _validate_conversation_request(value: Any, *, role: str) -> dict[str, Any]:
    request_schema, _, _ = _conversation_schemas(role)
    if type(value) is not dict or set(value) != _SECRETARY_REQUEST_KEYS:
        raise TransportValidationError("secretary request shape is invalid")
    if value["schema"] != request_schema:
        raise TransportValidationError("secretary request schema is invalid")
    validate_host_ref(value["host_ref"])
    validate_secretary_root_id(value["root_id"])
    _validate_secretary_pins(value["host_binding_sha256"], value["implementation_sha"])
    validate_secretary_operation(value["request"])
    digest = value["request_sha256"]
    if type(digest) is not str or _HEX64_RE.fullmatch(digest) is None:
        raise TransportValidationError("secretary request hash is invalid")
    if digest != request_sha256(value):
        raise TransportValidationError("secretary request hash is invalid")
    if len(_canonical_bytes(value)) > MAX_SECRETARY_REQUEST_BYTES:
        raise TransportValidationError("secretary request exceeds transport ceiling")
    return dict(value)


def _build_conversation_request(
    host_ref: str,
    root_id: str,
    host_binding_sha256: str,
    implementation_sha: str,
    request: Mapping[str, Any], *, role: str,
) -> dict[str, Any]:
    """Bind one closed native conversation to its authenticated host."""
    request_schema, _, _ = _conversation_schemas(role)
    value: dict[str, Any] = {
        "schema": request_schema,
        "host_ref": validate_host_ref(host_ref),
        "root_id": validate_secretary_root_id(root_id),
        "host_binding_sha256": host_binding_sha256,
        "implementation_sha": implementation_sha,
        "request": validate_secretary_operation(request),
    }
    _validate_secretary_pins(value["host_binding_sha256"], value["implementation_sha"])
    value["request_sha256"] = request_sha256(value)
    return _validate_conversation_request(value, role=role)


def _decode_conversation_request(raw: bytes, *, role: str) -> dict[str, Any]:
    """Strictly decode a bounded Secretary request frame."""
    if type(raw) is not bytes or len(raw) > MAX_SECRETARY_REQUEST_BYTES:
        raise TransportValidationError("secretary request exceeds transport ceiling")
    try:
        value = closed_json(raw, limit=MAX_SECRETARY_REQUEST_BYTES)
    except RoleStatusError:
        raise TransportValidationError("secretary request JSON is invalid") from None
    if type(value) is not dict:
        raise TransportValidationError("secretary request JSON is invalid")
    return _validate_conversation_request(value, role=role)


def _validate_conversation_result(value: Any, *, outcome: str, role: str) -> dict[str, Any]:
    """Validate the strict bounded result from the selected native owner."""
    _, _, native_schema = _conversation_schemas(role)
    if type(value) is not dict:
        raise TransportValidationError("secretary result is invalid")
    if outcome == "refused":
        # A refusal proven before forwarding carries a code and no invented
        # native receipt.
        if set(value) != _SECRETARY_REFUSAL_KEYS:
            raise TransportValidationError("secretary refusal result is invalid")
        code = value["code"]
        if type(code) is not str or _SECRETARY_REFUSAL_CODE_RE.fullmatch(code) is None:
            raise TransportValidationError("secretary refusal code is invalid")
        return dict(value)
    if outcome != "ok":
        raise TransportValidationError("secretary response outcome is invalid")
    # The actual native-control result, including its own refusal and unknown
    # states, is preserved exactly as the native owner produced it.
    if value.get("schema") != native_schema:
        raise TransportValidationError("secretary result is invalid")
    if value.get("status") not in _SECRETARY_NATIVE_RESULT_STATUSES:
        raise TransportValidationError("secretary result is invalid")
    return dict(value)


def _validate_conversation_response(value: Any, request: Mapping[str, Any], *, role: str) -> dict[str, Any]:
    _, response_schema, _ = _conversation_schemas(role)
    bound = _validate_conversation_request(request, role=role)
    if type(value) is not dict or set(value) != _SECRETARY_RESPONSE_KEYS:
        raise TransportValidationError("secretary response shape is invalid")
    if value["schema"] != response_schema:
        raise TransportValidationError("secretary response schema is invalid")
    for key in (
        "host_ref", "root_id", "host_binding_sha256",
        "implementation_sha", "request_sha256",
    ):
        if value[key] != bound[key]:
            raise TransportValidationError(
                "secretary response identity does not match request"
            )
    if value["outcome"] not in _SECRETARY_OUTCOMES:
        raise TransportValidationError("secretary response outcome is invalid")
    _validate_conversation_result(value["result"], outcome=value["outcome"], role=role)
    if len(_canonical_bytes(value)) > MAX_SECRETARY_RESPONSE_BYTES:
        raise TransportValidationError("secretary response exceeds transport ceiling")
    return dict(value)


def _build_conversation_response(
    request: Mapping[str, Any], *, outcome: str, result: Mapping[str, Any], role: str
) -> dict[str, Any]:
    """Echo one request's bound identity with its closed result."""
    _, response_schema, _ = _conversation_schemas(role)
    bound = _validate_conversation_request(request, role=role)
    if outcome not in _SECRETARY_OUTCOMES:
        raise TransportValidationError("secretary response outcome is invalid")
    value: dict[str, Any] = {
        "schema": response_schema,
        "host_ref": bound["host_ref"],
        "root_id": bound["root_id"],
        "host_binding_sha256": bound["host_binding_sha256"],
        "implementation_sha": bound["implementation_sha"],
        "request_sha256": bound["request_sha256"],
        "outcome": outcome,
        "result": _validate_conversation_result(result, outcome=outcome, role=role),
    }
    return _validate_conversation_response(value, bound, role=role)


def _decode_conversation_response(raw: bytes, request: Mapping[str, Any], *, role: str) -> dict[str, Any]:
    """Strictly decode a bounded Secretary response frame against its request."""
    if type(raw) is not bytes or len(raw) > MAX_SECRETARY_RESPONSE_BYTES:
        raise TransportValidationError("secretary response exceeds transport ceiling")
    try:
        value = closed_json(raw, limit=MAX_SECRETARY_RESPONSE_BYTES)
    except RoleStatusError:
        raise TransportValidationError("secretary response JSON is invalid") from None
    if type(value) is not dict:
        raise TransportValidationError("secretary response JSON is invalid")
    return _validate_conversation_response(value, request, role=role)



def validate_secretary_request(value: Any) -> dict[str, Any]:
    return _validate_conversation_request(value, role="mmsecretary")


def build_secretary_request(
    host_ref: str, root_id: str, host_binding_sha256: str,
    implementation_sha: str, request: Mapping[str, Any],
) -> dict[str, Any]:
    return _build_conversation_request(
        host_ref, root_id, host_binding_sha256, implementation_sha, request, role="mmsecretary")


def decode_secretary_request(raw: bytes) -> dict[str, Any]:
    return _decode_conversation_request(raw, role="mmsecretary")


def validate_secretary_result(value: Any, *, outcome: str) -> dict[str, Any]:
    return _validate_conversation_result(value, outcome=outcome, role="mmsecretary")


def validate_secretary_response(value: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    return _validate_conversation_response(value, request, role="mmsecretary")


def build_secretary_response(
    request: Mapping[str, Any], *, outcome: str, result: Mapping[str, Any],
) -> dict[str, Any]:
    return _build_conversation_response(request, outcome=outcome, result=result, role="mmsecretary")


def decode_secretary_response(raw: bytes, request: Mapping[str, Any]) -> dict[str, Any]:
    return _decode_conversation_response(raw, request, role="mmsecretary")



def validate_meta_request(value: Any) -> dict[str, Any]:
    return _validate_conversation_request(value, role="mmmeta")


def build_meta_request(
    host_ref: str, root_id: str, host_binding_sha256: str,
    implementation_sha: str, request: Mapping[str, Any],
) -> dict[str, Any]:
    return _build_conversation_request(
        host_ref, root_id, host_binding_sha256, implementation_sha, request, role="mmmeta")


def decode_meta_request(raw: bytes) -> dict[str, Any]:
    return _decode_conversation_request(raw, role="mmmeta")


def validate_meta_result(value: Any, *, outcome: str) -> dict[str, Any]:
    return _validate_conversation_result(value, outcome=outcome, role="mmmeta")


def validate_meta_response(value: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    return _validate_conversation_response(value, request, role="mmmeta")


def build_meta_response(
    request: Mapping[str, Any], *, outcome: str, result: Mapping[str, Any],
) -> dict[str, Any]:
    return _build_conversation_response(request, outcome=outcome, result=result, role="mmmeta")


def decode_meta_response(raw: bytes, request: Mapping[str, Any]) -> dict[str, Any]:
    return _decode_conversation_response(raw, request, role="mmmeta")
