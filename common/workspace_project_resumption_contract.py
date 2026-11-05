"""Closed Resume action/status DTOs over the existing Workspace principal.

Shape checks confer no authority. The authenticated owner separately requires
its independent scoped Resume grant and compares the actual current Pause.
Unknown/absent original receipt never permits automatic replay/replacement.
"""
from common import executive_workspace_contract as workspace
from common import workspace_project_admission_contract as pause
from common.workspace_project_admission_selection import selection as project_selection

FRAME_SCHEMA = ACTION_FRAME_SCHEMA = "mastermind.workspace_project_resumption_action.v1"
OPERATION = "resume_workstream_admission"
STATUS_FRAME_SCHEMA = "mastermind.workspace_project_resumption_status.v1"
STATUS_OPERATION = "read_resume_command"
ACTION_RESULT_SCHEMA = "mastermind.workspace_project_resumption_action_result.v1"
STATUS_RESULT_SCHEMA = "mastermind.workspace_project_resumption_status_result.v1"
RECEIPT_SCHEMA = "mastermind.workstream_admission_resumption_receipt.v1"
MAX_REQUEST_BYTES = 16384
MAX_RESPONSE_BYTES = 32768


def selection(value):
    return project_selection(value, command=True)


def validate_pause_token(value):
    pause._exact_keys(value, {"event_id", "receipt_digest"})
    pause._exact_int(value["event_id"], minimum=1)
    if type(value["receipt_digest"]) is not str or pause._REQUEST_DIGEST.fullmatch(value["receipt_digest"]) is None:
        raise ValueError("invalid_input")
    return pause._detached(value)


def validate_frame(value, status=False):
    keys = {"schema", "operation", "selection", "principal", "admission_expires_at"}
    pause._exact_keys(value, keys if status else keys | {"pause_token"})
    if value["schema"] != (STATUS_FRAME_SCHEMA if status else FRAME_SCHEMA) or value["operation"] != (STATUS_OPERATION if status else OPERATION):
        raise ValueError("invalid_input")
    selection(value["selection"])
    pause.validate_principal(value["principal"])
    pause._exact_int(value["admission_expires_at"], minimum=1)
    if not status:
        validate_pause_token(value["pause_token"])
    if len(workspace.canonical(value)) + 1 > MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    return pause._detached(value)


def validate_receipt(value, expected):
    selected = selection(expected)
    pause._exact_keys(value, {"schema", "work_ref", "state", "event_id", "command_id", "request_digest", "committed_at_ms", "pause_event_id", "pause_receipt_digest"})
    if (value["schema"] != RECEIPT_SCHEMA or value["state"] != "RESUMED"
            or value["work_ref"] != selected["work_ref"] or value["command_id"] != selected["command_id"]):
        raise ValueError("invalid_input")
    pause._exact_int(value["event_id"], minimum=1)
    pause._exact_int(value["pause_event_id"], minimum=1)
    pause._exact_int(value["committed_at_ms"], minimum=0)
    if (value["event_id"] <= value["pause_event_id"] or any(type(value[key]) is not str or pause._REQUEST_DIGEST.fullmatch(value[key]) is None
            for key in ("request_digest", "pause_receipt_digest"))):
        raise ValueError("invalid_input")
    return pause._detached(value)


def _result(value, expected, *, status):
    schema = STATUS_RESULT_SCHEMA if status else ACTION_RESULT_SCHEMA
    field = "state" if status else "disposition"
    pause._exact_keys(value, {"schema", "selection", field, "receipt", "reason_codes"})
    selected = selection(expected)
    if value["schema"] != schema or selection(value["selection"]) != selected:
        raise ValueError("invalid_input")
    disposition = value[field]
    if disposition == ("OBSERVED" if status else "COMMITTED"):
        validate_receipt(value["receipt"], selected)
        if value["reason_codes"] != []:
            raise ValueError("invalid_input")
    elif status and disposition == "NOT_OBSERVED":
        if value["receipt"] is not None or value["reason_codes"] != []:
            raise ValueError("invalid_input")
    elif disposition == ("UNAVAILABLE" if status else "NOT_DISPATCHED"):
        pause._paired_no_receipt(value["receipt"], value["reason_codes"], pause.UNAVAILABLE_REASON_CODES if status else pause.NOT_DISPATCHED_REASON_CODES)
    elif not status and disposition == "EFFECT_UNKNOWN":
        pause._paired_no_receipt(value["receipt"], value["reason_codes"], pause.EFFECT_UNKNOWN_REASON_CODES)
    else:
        raise ValueError("invalid_input")
    workspace.bounded_canonical({"ok": True, "result": value}, limit=MAX_RESPONSE_BYTES - 1)
    return pause._detached(value)


def validate_action_result(value, expected):
    return _result(value, expected, status=False)


def validate_status_result(value, expected):
    return _result(value, expected, status=True)


def canonical_request_bytes(value, status=False):
    return workspace.canonical(validate_frame(value, status=status)) + b"\n"


def response_envelope_bytes(value, expected, status=False):
    checked = _result(value, expected, status=status)
    return workspace.canonical({"ok": True, "result": checked}) + b"\n"
