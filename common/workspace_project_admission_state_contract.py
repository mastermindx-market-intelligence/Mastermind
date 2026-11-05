"""Closed read-qualified state/capability body for workspace project admission.

Pure DTO validator for the ``project_admission_state`` workspace read route.
The request frame reuses the shared principal owner
(:mod:`common.executive_workspace_contract`): selection and principal are
validated by projecting the frame onto the existing
``mastermind.executive_workspace_read.v3`` / ``admitted_plan`` frame, and
this module owns only the ``admission_expires_at`` projection plus its own
canonical byte cap including the trailing newline.  The response body below
is the distinct read-qualified state/capability contract; Runtime pause
event law and the action/status wire are other owners.

Inert by construction: no clock or timestamp observation, no registry,
controller, dispatcher, effect, mutation authorizer or grant check.  The
``can_pause`` flag only projects the served state, and the opaque
``project_admission:<64 lower hex>`` ``target_ref`` is an owner-qualified
read selection identity — never a grant or token.  A consumer must recheck
the actual owner when acting, and a renderer must not derive permission
from either.  ``state == NOT_SUSPENDED`` with ``current_receipt is None``
means no suspension record from a qualified owner — never a running, ready
or autonomy proof.  A read principal alone never makes a body AVAILABLE:
the parent's actual v4 scope grant plus the actual Root provenance, cache,
permission and read before/after guards live outside this pure validator.
"""

import json
import re

from common import executive_workspace_contract as _workspace

__all__ = [
    "AVAILABILITY_AVAILABLE",
    "AVAILABILITY_UNAVAILABLE",
    "BODY_SCHEMA",
    "CAPABILITY_OPERATION",
    "FRAME_SCHEMA",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "OPERATION",
    "RECEIPT_SCHEMA",
    "STATE_NOT_SUSPENDED",
    "STATE_PAUSED",
    "TARGET_REF_PREFIX",
    "UNAVAILABLE_REASON_CODES",
    "selection",
    "validate_body",
    "validate_frame",
]

FRAME_SCHEMA = "mastermind.workspace_project_admission_read.v1"
OPERATION = "project_admission_state"
BODY_SCHEMA = "mastermind.workspace_project_admission_state.v1"
MAX_REQUEST_BYTES = 16384
MAX_RESPONSE_BYTES = 32768

RECEIPT_SCHEMA = "mastermind.workstream_admission_suspension_receipt.v1"
CAPABILITY_OPERATION = "pause_workstream_admission"
TARGET_REF_PREFIX = "project_admission:"
AVAILABILITY_AVAILABLE = "AVAILABLE"
AVAILABILITY_UNAVAILABLE = "UNAVAILABLE"
STATE_NOT_SUSPENDED = "NOT_SUSPENDED"
STATE_PAUSED = "PAUSED"
UNAVAILABLE_REASON_CODES = frozenset({
    "INVALID_INPUT", "ACCESS_DENIED", "SOURCE_UNAVAILABLE",
    "SOURCE_CHANGED", "ROOT_MISMATCH", "OWNER_NOT_READY",
})

_FRAME_KEYS = {"schema", "operation", "selection", "principal", "admission_expires_at"}
_BODY_KEYS = {"schema", "selection", "availability", "state", "capability",
              "current_receipt", "reason_codes"}
_RECEIPT_KEYS = {"schema", "work_ref", "state", "event_id", "command_id",
                 "request_digest", "committed_at_ms"}
_CAPABILITY_KEYS = {"operation", "target_ref", "can_pause"}
_TARGET_REF = re.compile(r"project_admission:[0-9a-f]{64}")
_COMMAND_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_REQUEST_DIGEST = re.compile(r"[0-9a-f]{64}")


def _detached(value, message):
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError) as error:
        raise ValueError(message) from error


def selection(value):
    """Validate the exact workspace v3 read selection; return a detached copy.

    Thin wrapper over the shared owner selector — the principal owner stays
    the single grammar authority and this module does not reinvent it.
    Raises ``ValueError("invalid_input")`` on any deviation.
    """
    try:
        return _workspace.v3_selection(value)
    except ValueError as error:
        raise ValueError("invalid_input") from error


def validate_frame(frame):
    """Validate one project admission read request frame; return a detached copy.

    Exact closed keys ``schema`` / ``operation`` / ``selection`` /
    ``principal`` / ``admission_expires_at`` with the frozen schema and
    operation, a positive non-bool integer ``admission_expires_at``, and
    selection plus principal validated by the shared owner via the projected
    ``mastermind.executive_workspace_read.v3`` / ``admitted_plan`` frame.
    This module then owns its own canonical request byte cap including the
    trailing newline.  Raises ``ValueError("invalid_input")`` on any
    deviation, including every owner rejection.
    """
    if (type(frame) is not dict or set(frame) != _FRAME_KEYS
            or frame["schema"] != FRAME_SCHEMA or frame["operation"] != OPERATION
            or type(frame["admission_expires_at"]) is not int
            or frame["admission_expires_at"] <= 0):
        raise ValueError("invalid_input")
    try:
        _workspace.validate_v3_frame({
            "schema": _workspace.FRAME_SCHEMA_V3,
            "operation": "admitted_plan",
            "selection": frame["selection"],
            "principal": frame["principal"],
        })
    except ValueError as error:
        raise ValueError("invalid_input") from error
    try:
        if len(_workspace.canonical(frame)) + 1 > MAX_REQUEST_BYTES:
            raise ValueError("invalid_input")
    except ValueError as error:
        raise ValueError("invalid_input") from error
    return _detached(frame, "invalid_input")


def validate_body(value, expected):
    """Validate one project admission state body; return canonical wire bytes.

    ``value`` is the closed read body DTO and ``expected`` the exact
    selection pair the qualified owner actually served.  Returns the single
    canonical ``{"ok": true, "result": <body>}`` UTF-8 serialization
    including the trailing newline within :data:`MAX_RESPONSE_BYTES`, built
    from a detached copy of ``value``.  Raises
    ``ValueError("source_unavailable")`` on any deviation, including a
    malformed ``expected``.  Pure validator: nothing here observes a clock,
    authorizes mutation or derives permission from the read principal.
    """
    if (type(value) is not dict or set(value) != _BODY_KEYS
            or value["schema"] != BODY_SCHEMA):
        raise ValueError("source_unavailable")
    served = _served_selection(value["selection"])
    if (_workspace.canonical(_served_selection(expected))
            != _workspace.canonical(served)):
        raise ValueError("source_unavailable")
    availability = value["availability"]
    if type(availability) is not str:
        raise ValueError("source_unavailable")
    if availability == AVAILABILITY_AVAILABLE:
        _check_available(value, served)
    elif availability == AVAILABILITY_UNAVAILABLE:
        _check_unavailable(value)
    else:
        raise ValueError("source_unavailable")
    envelope = {"ok": True, "result": _detached(value, "source_unavailable")}
    try:
        payload = _workspace.canonical(envelope)
        if len(payload) + 1 > MAX_RESPONSE_BYTES:
            raise ValueError("source_unavailable")
    except ValueError as error:
        raise ValueError("source_unavailable") from error
    return payload + b"\n"


def _served_selection(value):
    try:
        return _workspace.v3_selection(value)
    except ValueError as error:
        raise ValueError("source_unavailable") from error


def _check_available(value, served):
    reason_codes = value["reason_codes"]
    if type(reason_codes) is not list or reason_codes:
        raise ValueError("source_unavailable")
    state = value["state"]
    if type(state) is not str or state not in (STATE_NOT_SUSPENDED, STATE_PAUSED):
        raise ValueError("source_unavailable")
    capability = value["capability"]
    if (type(capability) is not dict or set(capability) != _CAPABILITY_KEYS
            or capability["operation"] != CAPABILITY_OPERATION
            or type(capability["target_ref"]) is not str
            or _TARGET_REF.fullmatch(capability["target_ref"]) is None
            or type(capability["can_pause"]) is not bool):
        raise ValueError("source_unavailable")
    if state == STATE_NOT_SUSPENDED:
        # No suspension record from the qualified owner — never a running,
        # ready or autonomy proof.
        if capability["can_pause"] is not True or value["current_receipt"] is not None:
            raise ValueError("source_unavailable")
        return
    if capability["can_pause"] is not False:
        raise ValueError("source_unavailable")
    _check_receipt(value["current_receipt"], served)


def _check_receipt(receipt, served):
    if (type(receipt) is not dict or set(receipt) != _RECEIPT_KEYS
            or receipt["schema"] != RECEIPT_SCHEMA
            or receipt["state"] != STATE_PAUSED
            or receipt["work_ref"] != served["work_ref"]
            or type(receipt["event_id"]) is not int or receipt["event_id"] <= 0
            or type(receipt["command_id"]) is not str
            or _COMMAND_ID.fullmatch(receipt["command_id"]) is None
            or type(receipt["request_digest"]) is not str
            or _REQUEST_DIGEST.fullmatch(receipt["request_digest"]) is None
            or type(receipt["committed_at_ms"]) is not int
            or receipt["committed_at_ms"] < 0):
        raise ValueError("source_unavailable")


def _check_unavailable(value):
    if (value["state"] is not None or value["capability"] is not None
            or value["current_receipt"] is not None):
        raise ValueError("source_unavailable")
    reason_codes = value["reason_codes"]
    if type(reason_codes) is not list or not reason_codes:
        raise ValueError("source_unavailable")
    if any(type(reason) is not str or reason not in UNAVAILABLE_REASON_CODES
           for reason in reason_codes):
        raise ValueError("source_unavailable")
