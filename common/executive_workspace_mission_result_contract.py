"""Closed compound Mission/Result read. Frozen v1/v2/v3 grammars stay untouched.

The frame is a distinct schema. Its selection reuses the incumbent five-field
Result selector. The body carries the final Mission v3 document and the full
Workspace Result body, or neither.
"""
from __future__ import annotations

from common.executive_workspace_contract import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    MAX_RESULT_RESPONSE_BYTES,
    PRINCIPAL_KEYS,
    RESOURCE,
    RESULT_BODY_SCHEMA,
    SCOPE,
    bounded_canonical,
    canonical,
    v2_selection,
)

FRAME_SCHEMA = "mastermind.executive_workspace_mission_result_read.v1"
OPERATION = "mission_result"
BODY_SCHEMA = "mastermind.workspace_mission_result.v1"
MISSION_SCHEMA = "mastermind.mission_workspace.v3"
MAX_COMPOUND_RESPONSE_BYTES = MAX_RESPONSE_BYTES
MAX_NESTED_RESULT_RESPONSE_BYTES = MAX_RESULT_RESPONSE_BYTES
COMPOUND_REFUSAL_REASONS = frozenset({
    "SOURCE_UNAVAILABLE",
    "SOURCE_CHANGED",
    "OVER_BUDGET",
    "RESPONSE_OVER_BUDGET",
})
_BODY_KEYS = frozenset({
    "schema", "selection", "availability", "reason_codes", "mission", "role_result",
})


def selection(value):
    """The compound selector is the existing five-field Result selector."""

    return v2_selection(value, "result")


def validate_frame(frame):
    """Validate one closed compound frame. v2 operation grammar is not widened."""

    if (type(frame) is not dict or set(frame) != {"schema", "operation", "selection", "principal"}
            or frame["schema"] != FRAME_SCHEMA or frame["operation"] != OPERATION
            or type(frame["principal"]) is not dict or set(frame["principal"]) != PRINCIPAL_KEYS
            or frame["principal"]["resource"] != RESOURCE or frame["principal"]["scopes"] != [SCOPE]
            or any(type(frame["principal"][key]) is not str or not 1 <= len(frame["principal"][key]) <= 256
                   for key in PRINCIPAL_KEYS - {"scopes"})):
        raise ValueError("invalid_input")
    selection(frame["selection"])
    if len(canonical(frame)) + 1 > MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    return frame


def _reason_codes(value):
    if (type(value) is not list or not value or len(value) > len(COMPOUND_REFUSAL_REASONS)
            or any(type(item) is not str or item not in COMPOUND_REFUSAL_REASONS for item in value)
            or len(set(value)) != len(value)):
        raise ValueError("invalid_input")
    return list(value)


def validate_body(body):
    """Closed top-level compound body. Nested documents keep their own schemas."""

    if type(body) is not dict or set(body) != _BODY_KEYS or body["schema"] != BODY_SCHEMA:
        raise ValueError("invalid_input")
    selected = selection(body["selection"])
    availability = body["availability"]
    if availability == "AVAILABLE":
        mission, role_result = body["mission"], body["role_result"]
        if (body["reason_codes"] != [] or type(mission) is not dict or type(role_result) is not dict
                or mission.get("schema") != MISSION_SCHEMA
                or role_result.get("schema") != RESULT_BODY_SCHEMA):
            raise ValueError("invalid_input")
    elif availability == "UNAVAILABLE":
        _reason_codes(body["reason_codes"])
        if body["mission"] is not None or body["role_result"] is not None:
            raise ValueError("invalid_input")
    else:
        raise ValueError("invalid_input")
    return body


def unavailable_body(selected, reasons):
    """Discard both documents. ``reasons`` is one or more closed compound reasons."""

    if type(reasons) is str:
        reasons = [reasons]
    selected = selection(selected)
    return {
        "schema": BODY_SCHEMA,
        "selection": dict(selected),
        "availability": "UNAVAILABLE",
        "reason_codes": _reason_codes(reasons),
        "mission": None,
        "role_result": None,
    }


def unavailable(selected, reasons):
    return {"ok": True, "result": unavailable_body(selected, reasons)}


def nested_result_envelope_fits(role_result):
    """Whole nested Result socket envelope plus LF, independent of the compound cap."""

    try:
        bounded_canonical(
            {"ok": True, "result": role_result},
            limit=MAX_NESTED_RESULT_RESPONSE_BYTES - 1,
        )
    except (TypeError, ValueError):
        return False
    return True


def compound_envelope_fits(body):
    """Whole compound socket envelope plus LF. This cannot admit an oversized Result."""

    try:
        bounded_canonical(
            {"ok": True, "result": body},
            limit=MAX_COMPOUND_RESPONSE_BYTES - 1,
        )
    except (TypeError, ValueError):
        return False
    return True
