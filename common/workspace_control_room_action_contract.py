"""Closed action framing on the existing authenticated Workspace App peer.

These are synchronous transport facts, not an effect ledger or a new owner.
The host derives admission expiry from the verified principal. The original
Control Room owner still validates bindings and owns every actual effect.
"""
from __future__ import annotations

import json

from common.executive_workspace_contract import (
    FRAME_SCHEMA as WORKSPACE_SCHEMA, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES,
    canonical, validate_frame as validate_workspace_frame,
)

FRAME_SCHEMA = "mastermind.workspace_control_room_action.v1"
RESULT_SCHEMA = "mastermind.workspace_control_room_action_result.v1"
OPERATIONS = frozenset({"open", "bind", "unbind", "refresh-builds"})
DISPOSITIONS = frozenset({"NOT_DISPATCHED", "OWNER_RETURNED", "EFFECT_UNKNOWN"})


def _payload(operation, value):
    if type(value) is not dict:
        raise ValueError("invalid_input")
    keys = set(value)
    if operation in {"open", "unbind"}:
        allowed = {"binding_id", "target_surface", "owed_context"} if operation == "open" else {"binding_id"}
        if (not {"binding_id"} <= keys <= allowed
                or type(value["binding_id"]) is not str or not value["binding_id"]):
            raise ValueError("invalid_input")
        if operation == "open" and value.get("target_surface") is not None:
            if type(value["target_surface"]) is not str or value["target_surface"] not in {"default", "desktop"}:
                raise ValueError("invalid_input")
        # Presence is retained, including explicit null/malformed owed context.
        # The incumbent owner refuses it; it cannot become ordinary Open.
    elif operation == "bind":
        if (not {"work_ref", "role", "provider", "locator"} <= keys
                or not keys <= {"work_ref", "role", "provider", "locator", "seat_ref"}
                or any(type(value[key]) is not str for key in ("work_ref", "role", "provider"))
                or type(value["locator"]) is not dict
                or (value.get("seat_ref") is not None and type(value["seat_ref"]) is not str)):
            raise ValueError("invalid_input")
    elif operation == "refresh-builds":
        if keys:
            raise ValueError("invalid_input")
    else:
        raise ValueError("invalid_input")


def validate_frame(value):
    """Validate and detach one action request; this does not grant admission."""
    try:
        if (type(value) is not dict
                or set(value) != {"schema", "operation", "principal", "admission_expires_at", "payload"}
                or value["schema"] != FRAME_SCHEMA
                or type(value["operation"]) is not str or value["operation"] not in OPERATIONS
                or type(value["admission_expires_at"]) is not int or value["admission_expires_at"] <= 0):
            raise ValueError("invalid_input")
        validate_workspace_frame({
            "schema": WORKSPACE_SCHEMA, "operation": "programs",
            "selection": None, "principal": value["principal"],
        })
        _payload(value["operation"], value["payload"])
        raw = canonical(value)
        if len(raw) + 1 > MAX_REQUEST_BYTES:
            raise ValueError("invalid_input")
        return json.loads(raw)
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ValueError("invalid_input") from None


def _unknown_outcome():
    return {
        "ok": False, "failure_kind": "effect_unknown",
        "detail": (
            "The action may have run. Read current state and reconcile its original "
            "target before deciding what to do next."
        ),
        "next_action": "read_current_state", "retryable": False,
    }


def validate_result(value, *, operation):
    """Keep action custody visible across transport failure or result withholding.

    OWNER_RETURNED means only that the original operation returned this outcome.
    It is neither success proof nor a statement that no effect occurred.
    NOT_DISPATCHED requires either refusal before first-effect admission or
    the original owner's explicit no-provider precondition refusal. A provider
    outcome with a similarly named failure kind supplies no such proof.
    """
    try:
        if (type(operation) is not str or operation not in OPERATIONS
                or type(value) is not dict
                or set(value) != {"schema", "operation", "status", "disposition", "outcome"}
                or value["schema"] != RESULT_SCHEMA or value["operation"] != operation
                or type(value["status"]) is not int
                or type(value["disposition"]) is not str or value["disposition"] not in DISPOSITIONS
                or type(value["outcome"]) is not dict):
            raise ValueError("source_unavailable")
        disposition, status = value["disposition"], value["status"]
        if disposition == "EFFECT_UNKNOWN":
            if status != 503 or value["outcome"] != _unknown_outcome():
                raise ValueError("source_unavailable")
        elif disposition == "OWNER_RETURNED":
            if status != 200:
                raise ValueError("source_unavailable")
        elif (status not in {400, 403, 409, 503}
              or value["outcome"].get("failure_kind") == "effect_unknown"):
            raise ValueError("source_unavailable")
        raw = canonical({"ok": True, "result": value})
        if len(raw) + 1 > MAX_RESPONSE_BYTES:
            raise ValueError("source_unavailable")
        return json.loads(raw)["result"]
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ValueError("source_unavailable") from None


def action_result(operation, outcome, *, status, disposition):
    return validate_result({
        "schema": RESULT_SCHEMA, "operation": operation, "status": status,
        "disposition": disposition, "outcome": outcome,
    }, operation=operation)


def unknown_result(operation):
    return action_result(operation, _unknown_outcome(), status=503, disposition="EFFECT_UNKNOWN")


def refused_result(operation, *, code, status):
    if (code, status) not in {
        ("invalid_input", 400), ("access_denied", 403), ("source_unavailable", 503),
    }:
        raise ValueError("source_unavailable")
    return action_result(operation, {
        "ok": False, "error": {"code": code, "message": "Control Room action is unavailable."},
    }, status=status, disposition="NOT_DISPATCHED")


def _unique_object(pairs):
    """Reject repeated decoded names at every object depth."""
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("invalid_json")
        value[key] = item
    return value


def _reject_constant(_value):
    raise ValueError("invalid_json")


def _strict_json(raw, *, limit, code):
    """Decode original bounded JSON octets, never a reserialized mapping."""
    try:
        if type(raw) is not bytes or not raw or len(raw) > limit:
            raise ValueError(code)
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ValueError(code) from None


def decode_frame(raw):
    """Decode the raw action request retained by the existing App peer."""
    return validate_frame(_strict_json(
        raw, limit=MAX_REQUEST_BYTES, code="invalid_input",
    ))


def decode_payload(raw, *, operation):
    """Decode an HTTP body for an operation fixed by the route."""
    try:
        if type(operation) is not str or operation not in OPERATIONS:
            raise ValueError("invalid_input")
        value = _strict_json(raw, limit=MAX_REQUEST_BYTES, code="invalid_input")
        _payload(operation, value)
        encoded = canonical(value)
        if len(encoded) + 1 > MAX_REQUEST_BYTES:
            raise ValueError("invalid_input")
        return json.loads(encoded)
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ValueError("invalid_input") from None


def decode_result_envelope(raw, *, operation):
    """Decode the complete private response for the originally sent action."""
    try:
        value = _strict_json(raw, limit=MAX_RESPONSE_BYTES, code="source_unavailable")
        if type(value) is not dict or set(value) != {"ok", "result"} or value["ok"] is not True:
            raise ValueError("source_unavailable")
        return {"ok": True, "result": validate_result(value["result"], operation=operation)}
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ValueError("source_unavailable") from None
