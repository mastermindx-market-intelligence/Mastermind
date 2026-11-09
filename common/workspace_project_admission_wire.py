"""Closed wire selection for fixed project-admission endpoints, no routing owner."""
import json
from common import executive_workspace_contract as workspace
from common import workspace_project_admission_contract as pause
from common import workspace_project_resumption_contract as resume
from common import workspace_project_admission_control_contract as control

SCHEMAS = frozenset({pause.FRAME_SCHEMA, pause.STATUS_FRAME_SCHEMA, resume.FRAME_SCHEMA, resume.STATUS_FRAME_SCHEMA, control.FRAME_SCHEMA})
MAX_REQUEST_BYTES = 16384
MAX_RESPONSE_BYTES = 32768


def is_project_admission_frame(frame):
    return type(frame) is dict and type(frame.get("schema")) is str and frame["schema"] in SCHEMAS


def classify(frame):
    if not is_project_admission_frame(frame):
        raise ValueError("invalid_input")
    schema = frame["schema"]
    if schema == control.FRAME_SCHEMA:
        return control, "current"
    return (resume if schema in {resume.FRAME_SCHEMA, resume.STATUS_FRAME_SCHEMA} else pause), ("status" if schema in {pause.STATUS_FRAME_SCHEMA, resume.STATUS_FRAME_SCHEMA} else "action")


def validate_frame(frame):
    wire, mode = classify(frame)
    return wire.validate_frame(frame) if mode == "current" else wire.validate_frame(frame, status=mode == "status")


def decode_frame(raw):
    if type(raw) is not bytes or len(raw) > MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("invalid_input")
            value[key] = item
        return value
    def invalid(_):
        raise ValueError("invalid_input")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)
        return validate_frame(value)
    except (TypeError, ValueError, UnicodeError):
        raise ValueError("invalid_input") from None


def validate_result(value, frame):
    wire, mode = classify(frame)
    if type(value) is not dict or set(value) != {"ok", "result"} or value["ok"] is not True:
        raise ValueError("source_unavailable")
    selected = frame["selection"]
    body = (wire.validate_body(value["result"], selected) if mode == "current" else
        wire.validate_status_result(value["result"], selected) if mode == "status" else wire.validate_action_result(value["result"], selected))
    workspace.bounded_canonical({"ok": True, "result": body}, limit=MAX_RESPONSE_BYTES - 1)
    return {"ok": True, "result": body}


def withheld(frame, *, attempted=False, reason="SOURCE_UNAVAILABLE"):
    wire, mode = classify(frame)
    selected = dict(frame["selection"])
    if mode == "current":
        body = {"schema": control.BODY_SCHEMA, "selection": selected, "availability": "UNAVAILABLE", "state": None,
            "permissions": None, "owner_context": None, "current_receipt": None, "pause_token": None, "reason_codes": [reason]}
    elif mode == "status":
        body = {"schema": wire.STATUS_RESULT_SCHEMA, "selection": selected, "state": "UNAVAILABLE", "receipt": None, "reason_codes": [reason]}
    else:
        body = {"schema": wire.ACTION_RESULT_SCHEMA, "selection": selected,
            "disposition": "EFFECT_UNKNOWN" if attempted else "NOT_DISPATCHED", "receipt": None,
            "reason_codes": ["OWNER_OUTCOME_UNCONFIRMED" if attempted else reason]}
    return validate_result({"ok": True, "result": body}, frame)
