"""Read-only canonical standing-instruction content; no Runtime state/grant.

Authored content revision is a source identity, never active/paused evidence.
Source publication neither schedules work nor resumes an instruction gate.
"""
import hashlib
import json
import re
from functools import wraps

from common import executive_workspace_contract as workspace
from common.workspace_project_plan_contract import validate_selection, validate_source
from common.workspace_project_admission_contract import validate_principal

FRAME_SCHEMA = "mastermind.workspace_project_instructions_read.v1"
OPERATION = "project_instructions"
BODY_SCHEMA = "mastermind.workspace_project_instructions.v1"
PUBLIC_BODY_SCHEMA = "mastermind.workspace_project_instructions.v2"
MAX_REQUEST_BYTES = 16384
MAX_RESPONSE_BYTES = 32768
REASONS = {"ACCESS_DENIED", "SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "OWNER_NOT_READY", "RECORD_NOT_FOUND", "RECORD_INVALID", "CONTENT_OVER_BUDGET"}
_INSTRUCTION = re.compile(r"INS:[A-Z0-9]+(?:-[A-Z0-9]+)*")


def _closed(reason):
    def decorate(fn):
        @wraps(fn)
        def checked(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except (TypeError, ValueError, KeyError, OverflowError, RecursionError):
                raise ValueError(reason) from None
        return checked
    return decorate



def instruction_ref(value):
    if (type(value) is not str or not 6 <= len(value) <= 68
            or _INSTRUCTION.fullmatch(value) is None):
        raise ValueError("invalid_input")
    return value


@_closed("source_unavailable")
def authored_instruction(value):
    if type(value) is not dict or set(value) != {"instruction_ref", "text"}:
        raise ValueError("source_unavailable")
    ref = instruction_ref(value["instruction_ref"])
    text = value["text"]
    if (type(text) is not str or not text.strip() or len(text) > 4096
            or any((ord(c) < 32 and c not in "\n\r\t") or ord(c) == 127 for c in text)):
        raise ValueError("source_unavailable")
    material = {"instruction_ref": ref, "text": text}
    revision = hashlib.sha256(workspace.canonical(material)).hexdigest()
    return {**material, "revision": revision}


@_closed("invalid_input")
def validate_frame(value):
    if (type(value) is not dict or set(value) != {"schema", "operation", "selection", "principal"}
            or value["schema"] != FRAME_SCHEMA or value["operation"] != OPERATION):
        raise ValueError("invalid_input")
    validate_selection(value["selection"])
    validate_principal(value["principal"])
    if len(workspace.canonical(value)) + 1 > MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    return json.loads(workspace.canonical(value))


@_closed("source_unavailable")
def validate_body(value, expected=None):
    if expected is None and type(value) is dict:
        expected = value.get("selection")
    if (type(value) is not dict or set(value) != {"schema", "selection", "availability", "source", "declaration", "instructions", "reason_codes"}
            or value["schema"] != BODY_SCHEMA or validate_selection(value["selection"]) != validate_selection(expected)):
        raise ValueError("source_unavailable")
    if value["availability"] == "AVAILABLE":
        validate_source(value["source"], expected["work_ref"])
        if (value["declaration"] not in {"NOT_DECLARED", "SUPPLIED"} or value["reason_codes"] != []
                or type(value["instructions"]) is not list or len(value["instructions"]) > 16):
            raise ValueError("source_unavailable")
        refs = []
        for row in value["instructions"]:
            if type(row) is not dict or set(row) != {"instruction_ref", "text", "revision"}:
                raise ValueError("source_unavailable")
            if row != authored_instruction({key: row[key] for key in ("instruction_ref", "text")}):
                raise ValueError("source_unavailable")
            refs.append(row["instruction_ref"])
        if len(set(refs)) != len(refs) or value["declaration"] == "NOT_DECLARED" and refs:
            raise ValueError("source_unavailable")
    elif value["availability"] == "UNAVAILABLE":
        if (any(value[key] is not None for key in ("source", "declaration", "instructions"))
                or type(value["reason_codes"]) is not list or len(value["reason_codes"]) != 1
                or value["reason_codes"][0] not in REASONS):
            raise ValueError("source_unavailable")
    else:
        raise ValueError("source_unavailable")
    workspace.bounded_canonical({"ok": True, "result": value}, limit=MAX_RESPONSE_BYTES - 1)
    return json.loads(workspace.canonical(value))


def unavailable(work_ref, reason="SOURCE_UNAVAILABLE"):
    selected = validate_selection({"work_ref": work_ref})
    if type(reason) is not str or reason not in REASONS:
        raise ValueError("source_unavailable")
    return validate_body({"schema": BODY_SCHEMA, "selection": selected,
        "availability": "UNAVAILABLE", "source": None, "declaration": None,
        "instructions": None, "reason_codes": [reason]}, selected)


@_closed("source_unavailable")
def validate_public_body(value,expected=None):
    if type(value) is not dict or set(value)!={"schema","selection","availability","source","declaration","instructions","reason_codes","recovery_identity"} or value['schema']!=PUBLIC_BODY_SCHEMA:
        raise ValueError('source_unavailable')
    base=validate_body({**{key:item for key,item in value.items() if key!='recovery_identity'},'schema':BODY_SCHEMA},expected)
    identity=value['recovery_identity']
    if base['availability']=='AVAILABLE':
        if type(identity) is not dict or set(identity)!={'principal_scope'} or type(identity['principal_scope']) is not str or re.fullmatch('[0-9a-f]{64}',identity['principal_scope']) is None:raise ValueError('source_unavailable')
    elif identity is not None:raise ValueError('source_unavailable')
    workspace.bounded_canonical({'ok':True,'result':value},limit=MAX_RESPONSE_BYTES-1)
    return json.loads(workspace.canonical(value))


def public_body(body,*,recovery_identity):
    base=validate_body(body)
    return validate_public_body({**base,'schema':PUBLIC_BODY_SCHEMA,'recovery_identity':recovery_identity if base['availability']=='AVAILABLE' else None})


@_closed("source_unavailable")
def from_canonical_projection(value, expected):
    """Close the real Macro helper's content body without promoting authority."""
    if (type(value) is not dict or set(value) != {"schema", "selection", "source", "declaration", "instructions"}
            or value["schema"] != "mastermind.agentos.standing_instructions.v1"):
        raise ValueError("source_unavailable")
    return validate_body({**value, "schema": BODY_SCHEMA, "availability": "AVAILABLE", "reason_codes": []}, expected)
