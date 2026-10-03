"""Closed release frames on the existing CeoIngress connection.

Parsing is not authentication. Control must qualify the connected installed
Gateway before consuming the projected principal. These helpers hold no Runtime,
key, queue, token registry, or effect authority.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import re

from control_plane.ceo_request import app_request_ref, CeoRequestError
from control_plane.executive_authority import release_principal_projection, ReleaseAuthorityDenied
from control_plane.principal_projection import (
    NeutralPrincipalProjection, neutral_principal_projection,
)
from control_plane.executive_release_contract import approval_ref_for

FRAME_SCHEMA = "mastermind.executive_release_control/v1"
RESPONSE_SCHEMA = "mastermind.executive_release_control_result/v1"
MAX_FRAME_BYTES = 49152
MAX_RESPONSE_BYTES = 65536
MAX_TOKEN_BYTES = 32768
OPERATIONS = frozenset({
    "approve_release_transition", "prepare_release_transition",
    "commit_prepared_release_transition", "reconcile_release_transition",
})
_KEYS = {
    "approve_release_transition": frozenset({"operation_key", "action", "transition_digest"}),
    "prepare_release_transition": frozenset({"operation_key", "approved_transition_ref"}),
    "commit_prepared_release_transition": frozenset({"operation_key", "prepared_token"}),
    "reconcile_release_transition": frozenset({"operation_key"}),
}
_PRINCIPAL_KEYS = frozenset({
    "policy_id", "issuer", "issuer_digest", "resource", "subject_digest",
    "client_ref", "scopes", "issued_at", "expires_at",
})
_HEX = re.compile(r"[0-9a-f]{64}", re.ASCII)
_MAX_INT = (1 << 63) - 1


class ReleaseIngressError(ValueError):
    """Bounded fixed diagnostic, never an echo of a token or principal."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _fail(code):
    raise ReleaseIngressError(code)


def validate_arguments(operation: str, arguments: object) -> dict:
    if type(operation) is not str or operation not in OPERATIONS:
        _fail("RELEASE_OPERATION_INVALID")
    if not isinstance(arguments, Mapping) or set(arguments) != _KEYS[operation]:
        _fail("RELEASE_ARGUMENTS_INVALID")
    value = dict(arguments)
    if "operation_key" in value:
        if type(value["operation_key"]) is not str:
            _fail("RELEASE_OPERATION_KEY_INVALID")
        try:
            app_request_ref(value["operation_key"])
        except (CeoRequestError, ValueError, TypeError):
            _fail("RELEASE_OPERATION_KEY_INVALID")
    if operation == "approve_release_transition":
        if value["action"] not in ("executive.release.upgrade", "executive.release.rollback"):
            _fail("RELEASE_ACTION_INVALID")
        if type(value["transition_digest"]) is not str or _HEX.fullmatch(value["transition_digest"]) is None:
            _fail("RELEASE_TRANSITION_INVALID")
    elif operation == "prepare_release_transition":
        if value["approved_transition_ref"] != approval_ref_for(value["operation_key"]):
            _fail("RELEASE_APPROVAL_REF_MISMATCH")
    elif operation == "commit_prepared_release_transition":
        token = value["prepared_token"]
        if type(token) is not str or not 0 < len(token) <= MAX_TOKEN_BYTES or not token.isascii():
            _fail("RELEASE_TOKEN_INVALID")
    return value


def _principal_fields(principal: NeutralPrincipalProjection) -> dict:
    if type(principal) is not NeutralPrincipalProjection:
        _fail("RELEASE_PRINCIPAL_INVALID")
    try:
        release_principal_projection(principal)
    except (ValueError, ReleaseAuthorityDenied):
        _fail("RELEASE_PRINCIPAL_INVALID")
    if (type(principal.issued_at) is not int or type(principal.expires_at) is not int
            or not 0 <= principal.issued_at < principal.expires_at <= _MAX_INT // 1000):
        _fail("RELEASE_PRINCIPAL_INVALID")
    result = {key: getattr(principal, key) for key in _PRINCIPAL_KEYS if key != "scopes"}
    result["scopes"] = list(principal.scopes)
    return result


def project_frame(operation: str, arguments: object, *, principal: NeutralPrincipalProjection) -> dict:
    """Gateway-owned projection after its existing JWT verifier succeeds."""
    result = {"schema": FRAME_SCHEMA, "operation": operation,
              "arguments": validate_arguments(operation, arguments),
              "principal": _principal_fields(principal)}
    encode_frame(result)
    return result


def encode_frame(frame: Mapping) -> bytes:
    try:
        raw = json.dumps(frame, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _fail("RELEASE_FRAME_INVALID")
    if len(raw) > MAX_FRAME_BYTES:
        _fail("RELEASE_FRAME_TOO_LARGE")
    return raw


@dataclass(frozen=True)
class ReleaseFrame:
    operation: str
    arguments: dict
    principal: NeutralPrincipalProjection


def validate_frame(frame: object) -> ReleaseFrame:
    """Shape-check only; the caller still owes live installed-peer proof."""
    if not isinstance(frame, Mapping) or set(frame) != {"schema", "operation", "arguments", "principal"}:
        _fail("RELEASE_FRAME_INVALID")
    if frame["schema"] != FRAME_SCHEMA:
        _fail("RELEASE_FRAME_INVALID")
    encode_frame(frame)
    arguments = validate_arguments(frame["operation"], frame["arguments"])
    fields = frame["principal"]
    if not isinstance(fields, Mapping) or set(fields) != _PRINCIPAL_KEYS or type(fields["scopes"]) is not list:
        _fail("RELEASE_PRINCIPAL_INVALID")
    try:
        principal = neutral_principal_projection(**{**fields, "scopes": tuple(fields["scopes"]), "jti_digest": None})
        _principal_fields(principal)
    except (TypeError, ValueError):
        _fail("RELEASE_PRINCIPAL_INVALID")
    return ReleaseFrame(frame["operation"], arguments, principal)


def decode_frame(raw: bytes) -> ReleaseFrame:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_FRAME_BYTES or not raw.endswith(b"\n"):
        _fail("RELEASE_FRAME_INVALID")
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                _fail("RELEASE_FRAME_DUPLICATE_KEY")
            out[key] = value
        return out
    def reject_number(_):
        _fail("RELEASE_FRAME_NUMBER_INVALID")
    try:
        frame = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs,
                           parse_float=reject_number, parse_constant=reject_number)
    except (UnicodeError, ValueError, RecursionError):
        _fail("RELEASE_FRAME_INVALID")
    return validate_frame(frame)
