"""Closed project pause/resume capability read, separate from action receipts.

Permissions are qualified owner facts at this read, never reusable grants.
Current state cannot be derived from a historical action result. No I/O/effects.
"""
import json
import re

from common import executive_workspace_contract as workspace
from common import workspace_project_admission_contract as pause
from common.workspace_project_admission_selection import selection

FRAME_SCHEMA = "mastermind.workspace_project_admission_control_read.v1"
OPERATION = "project_admission_control"
BODY_SCHEMA = "mastermind.workspace_project_admission_control.v1"
MAX_REQUEST_BYTES = 16384
MAX_RESPONSE_BYTES = 32768
REASONS = {"INVALID_INPUT", "ACCESS_DENIED", "SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "ROOT_MISMATCH", "OWNER_NOT_READY"}
_HEX = re.compile(r"[0-9a-f]{64}")


def validate_frame(value):
    if (type(value) is not dict or set(value) != {"schema", "operation", "selection", "principal", "admission_expires_at"}
            or value["schema"] != FRAME_SCHEMA or value["operation"] != OPERATION
            or type(value["admission_expires_at"]) is not int or value["admission_expires_at"] <= 0):
        raise ValueError("invalid_input")
    selection(value["selection"])
    pause.validate_principal(value["principal"])
    if len(workspace.canonical(value)) + 1 > MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    return json.loads(workspace.canonical(value))


def validate_body(value, expected):
    if (type(value) is not dict or set(value) != {"schema", "selection", "availability", "state", "permissions", "owner_context", "current_receipt", "pause_token", "reason_codes"}
            or value["schema"] != BODY_SCHEMA or selection(value["selection"]) != selection(expected)):
        raise ValueError("source_unavailable")
    if value["availability"] == "UNAVAILABLE":
        if (any(value[key] is not None for key in ("state", "permissions", "owner_context", "current_receipt", "pause_token"))
                or type(value["reason_codes"]) is not list or len(value["reason_codes"]) != 1
                or value["reason_codes"][0] not in REASONS):
            raise ValueError("source_unavailable")
    elif value["availability"] == "AVAILABLE":
        permissions, context, receipt = value["permissions"], value["owner_context"], value["current_receipt"]
        if (value["reason_codes"] != [] or type(permissions) is not dict or set(permissions) != {"pause", "resume"}
                or any(type(flag) is not bool for flag in permissions.values()) or not any(permissions.values())
                or type(context) is not dict or set(context) != {"principal_scope"}
                or type(context["principal_scope"]) is not str or _HEX.fullmatch(context["principal_scope"]) is None):
            raise ValueError("source_unavailable")
        state = value["state"]
        if state == "NOT_SUSPENDED":
            if receipt is not None or value["pause_token"] is not None:
                raise ValueError("source_unavailable")
        elif state == "PAUSED":
            from control_plane.workstream_resumption_contract import pause_receipt_digest
            checked = pause.validate_receipt(receipt, {**value["selection"], "command_id": receipt.get("command_id") if type(receipt) is dict else None})
            token = {"event_id": checked["event_id"], "receipt_digest": pause_receipt_digest(checked)}
            from common.workspace_project_resumption_contract import validate_pause_token
            if validate_pause_token(value["pause_token"]) != token:
                raise ValueError("source_unavailable")
        elif state == "RESUMED":
            from common import workspace_project_resumption_contract as resume
            resume.validate_receipt(receipt, {**value["selection"], "command_id": receipt.get("command_id") if type(receipt) is dict else None})
            if value["pause_token"] is not None:
                raise ValueError("source_unavailable")
        else:
            raise ValueError("source_unavailable")
    else:
        raise ValueError("source_unavailable")
    workspace.bounded_canonical({"ok": True, "result": value}, limit=MAX_RESPONSE_BYTES - 1)
    return json.loads(workspace.canonical(value))
