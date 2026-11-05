"""Closed request syntax for the incumbent fresh conversation composition.

Pure data only. No preview digest, request, or response grants admission.
"""
from __future__ import annotations

import hashlib
import json
import re

SCHEMA = "mastermind.executive.fresh_conversation.v1"
RESULT_SCHEMA = "mastermind.executive.fresh_conversation_result.v1"
DATA_SCHEMA = "mastermind.executive.fresh_conversation_data.v1"
ROUTES = {f"/os/executive/conversation/{operation}": operation
          for operation in ("preview", "create", "status", "read", "consume", "turn")}
ROUTES.update({"/os/executive/conversation/consume/status": "consume_status",
    "/os/executive/conversation/turn/preview": "turn_preview",
    "/os/executive/conversation/turn/status": "turn_status",
    "/os/executive/conversation/turn/read": "turn_read"})
MODIFYING = frozenset({"create", "consume", "turn"})
DUAL_RESOURCE = MODIFYING | {"preview", "turn_preview"}
PRINCIPAL_FIELDS = frozenset({"policy_id", "issuer", "issuer_digest", "resource", "subject_digest",
    "client_ref", "scopes", "issued_at", "expires_at", "jti_digest"})
_WORK = re.compile(r"WS:[A-Za-z0-9][A-Za-z0-9._-]{0,68}\Z")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")


def validate_request(value, *, operation):
    if type(operation) is not str or operation not in {"preview", "create", "status", "read", "consume", "turn", "turn_status", "turn_read", "consume_status", "turn_preview"}:
        raise ValueError("invalid operation")
    reference_mode = "reference" in value if type(value) is dict else False
    if reference_mode and operation not in {"consume", "turn", "turn_status", "turn_read", "consume_status", "turn_preview"}:
        raise ValueError("unexpected reference")
    keys = {"work_ref", "reference" if reference_mode else "operation_key"}
    if operation in {"preview", "create", "turn", "turn_preview"}:
        keys.add("message")
    if operation in {"consume", "turn", "consume_status", "turn_preview"}:
        keys.add("initial_digest")
    if operation in {"turn", "turn_status", "turn_read", "turn_preview"}:
        keys.add("turn_key")
    if operation == "create" or (operation == "turn" and type(value) is dict and "preview_digest" in value):
        keys.add("preview_digest")
    if type(value) is not dict or set(value) != keys:
        raise ValueError("invalid request")
    if (type(value["work_ref"]) is not str or not _WORK.fullmatch(value["work_ref"])
            or (not reference_mode and (type(value["operation_key"]) is not str or not _KEY.fullmatch(value["operation_key"])))):
        raise ValueError("invalid selector")
    if reference_mode:
        validate_reference(value["reference"])
        if value["reference"]["work_ref"] != value["work_ref"]:
            raise ValueError("foreign work reference")
    if "turn_key" in keys and (type(value["turn_key"]) is not str or not _KEY.fullmatch(value["turn_key"])):
        raise ValueError("invalid turn key")
    if "initial_digest" in keys and (type(value["initial_digest"]) is not str or not _HEX.fullmatch(value["initial_digest"])):
        raise ValueError("invalid initial digest")
    if "message" in keys:
        message = value["message"]
        if (type(message) is not str or not message.strip() or len(message) > 700
                or any((ord(c) < 32 and c not in "\t\n\r") or 127 <= ord(c) <= 159 for c in message)):
            raise ValueError("invalid message")
        try:
            if len(message.encode("utf-8", errors="strict")) > 2800:
                raise ValueError("invalid message")
        except UnicodeEncodeError:
            raise ValueError("invalid message") from None
    if "preview_digest" in keys and (type(value["preview_digest"]) is not str
            or not _HEX.fullmatch(value["preview_digest"])):
        raise ValueError("invalid preview")
    return dict(value)


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8", errors="strict")).hexdigest()


def admission_arguments(request, scoped_operation_key):
    selected = validate_request({key: request[key] for key in
        ("work_ref", "operation_key", "message")}, operation="preview")
    if type(scoped_operation_key) is not str or not _KEY.fullmatch(scoped_operation_key):
        raise ValueError("invalid operation key")
    return dict(operation_key=scoped_operation_key, objective=selected["message"],
        department="executive-infrastructure", priority=0, execution_profile="research_only",
        workstream=selected["work_ref"], attempt_limit=1)


def validate_private_frame(value):
    if (type(value) is not dict or set(value) != {"schema", "operation", "principal", "workspace_principal", "arguments"}
            or value["schema"] != SCHEMA):
        raise ValueError("invalid frame")
    operation = value["operation"]
    arguments = validate_request(value["arguments"], operation=operation)
    def principal(raw):
        if (type(raw) is not dict or set(raw) != PRINCIPAL_FIELDS
                or any(type(raw[k]) is not str or not 1 <= len(raw[k]) <= 2048
                    for k in PRINCIPAL_FIELDS - {"scopes", "issued_at", "expires_at", "jti_digest"})
                or type(raw["issued_at"]) is not int or type(raw["expires_at"]) is not int
                or type(raw["scopes"]) is not list or not 1 <= len(raw["scopes"]) <= 16
                or len(set(raw["scopes"])) != len(raw["scopes"])
                or any(type(scope) is not str or not 1 <= len(scope) <= 96 for scope in raw["scopes"])
                or (raw["jti_digest"] is not None and (type(raw["jti_digest"]) is not str or not _HEX.fullmatch(raw["jti_digest"])))):
            raise ValueError("invalid principal")
        return {**raw, "scopes": list(raw["scopes"])}
    p = principal(value["principal"])
    workspace = value["workspace_principal"]
    if operation in DUAL_RESOURCE:
        workspace = principal(workspace)
    elif workspace is not None:
        raise ValueError("unexpected read principal")
    return dict(schema=SCHEMA, operation=operation, principal=p, workspace_principal=workspace, arguments=arguments)


def validate_data(value, request):
    if type(value) is dict and value.get("schema") == "mastermind.executive.fresh_conversation_turn_preview.v1":
        return validate_turn_preview(value, request)
    if type(value) is dict and value.get("schema") == "mastermind.executive.fresh_conversation_turn_data.v1":
        return validate_turn_data(value, request)
    keys = {"schema", "operation_key", "work_ref", "state", "effect", "parent_consumed",
        "preview", "locator", "session", "result", "can_send"}
    if (type(value) is not dict or set(value) != keys or value["schema"] != DATA_SCHEMA
            or any(value[key] != request[key] for key in ("work_ref", "operation_key"))
            or value["state"] not in {"PREVIEW_READY", "ABSENT", "ADMITTED", "CREATED", "SETTLED", "RECONCILIATION_REQUIRED"}
            or value["effect"] not in {"NONE", "ADMITTED", "COMMITTED"}
            or value["parent_consumed"] is not False or value["can_send"] is not False):
        raise ValueError("invalid response")
    if value["state"] == "CREATED":
        if (type(value["session"]) is not dict or set(value["session"]) != {"attempt_id", "generation", "binding_digest"}
                or not _HEX.fullmatch(value["session"]["binding_digest"])):
            raise ValueError("invalid created session")
    elif value["session"] is not None:
        raise ValueError("unexpected session")
    if value["locator"] is not None:
        locator = value["locator"]
        if (type(locator) is not dict or set(locator) != {"work_ref", "root_job_id", "job_id", "attempt_id"}
                or locator["work_ref"] != request["work_ref"] or type(locator["root_job_id"]) is not str
                or any(locator[k] is not None and type(locator[k]) is not str for k in ("job_id", "attempt_id"))):
            raise ValueError("invalid locator")
    if value["result"] is not None:
        result = value["result"]
        if (type(result) is not dict or set(result) != {"digest", "envelope"}
                or type(result["envelope"]) is not dict or canonical_digest(result["envelope"]) != result["digest"]
                or len(json.dumps(result["envelope"], ensure_ascii=False).encode("utf-8")) > 16384):
            raise ValueError("invalid result")
    return dict(value)


def validate_turn_data(value, request):
    keys = {"schema", "work_ref", "operation_key", "reference", "turn_key", "state", "effect",
        "initial_consumption", "locator", "result", "parent_consumed", "can_send"}
    if (type(value) is not dict or set(value) != keys
            or value["schema"] != "mastermind.executive.fresh_conversation_turn_data.v1"
            or value["work_ref"] != request["work_ref"]
            or value["operation_key"] != request.get("operation_key")
            or value["reference"] != request.get("reference")
            or value["turn_key"] != request.get("turn_key")
            or value["state"] not in {"CONSUMED", "ABSENT", "RECONCILIATION_REQUIRED", "RECORDED"}
            or value["effect"] not in {"NONE", "COMMITTED", "UNKNOWN"}
            or value["parent_consumed"] is not False or type(value["can_send"]) is not bool
            or (value["can_send"] is True and value["state"] != "CONSUMED")):
        raise ValueError("invalid turn data")
    consumption = value["initial_consumption"]
    if consumption is not None and (type(consumption) is not dict
            or set(consumption) != {"state", "event_id", "event_sha256", "initial_digest"}
            or consumption["state"] != "CONSUMED" or type(consumption["event_id"]) is not int
            or consumption["event_id"] < 1 or any(type(consumption[key]) is not str
                or not _HEX.fullmatch(consumption[key]) for key in ("event_sha256", "initial_digest"))):
        raise ValueError("invalid consumption")
    locator = value["locator"]
    if (type(locator) is not dict or set(locator) != {"work_ref", "root_job_id", "job_id", "attempt_id"}
            or locator["work_ref"] != request["work_ref"]
            or type(locator["root_job_id"]) is not str or not locator["root_job_id"]
            or any((type(locator[key]) is not str or not locator[key])
                and not (value["state"] == "ABSENT" and locator[key] is None) for key in ("job_id", "attempt_id"))):
        raise ValueError("invalid original locator")
    if value["state"] == "RECORDED":
        result = value["result"]
        if (consumption is None or type(result) is not dict or set(result) != {"digest", "envelope"}
                or type(result["envelope"]) is not dict or canonical_digest(result["envelope"]) != result["digest"]
                or len(json.dumps(result["envelope"], ensure_ascii=False).encode()) > 16384):
            raise ValueError("invalid turn result")
    elif value["result"] is not None:
        raise ValueError("unexpected turn result")
    if value["state"] == "CONSUMED" and consumption is None:
        raise ValueError("missing consumption")
    return dict(value)


def validate_reference(value):
    keys = {"schema", "work_ref", "root_job_id", "root_event_id", "root_event_sha256", "principal_scope_sha256"}
    if (type(value) is not dict or set(value) != keys or value["schema"] != "mastermind.fresh_conversation_reference.v1"
            or type(value["work_ref"]) is not str or not _WORK.fullmatch(value["work_ref"])
            or type(value["root_job_id"]) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value["root_job_id"])
            or type(value["root_event_id"]) is not int or value["root_event_id"] < 1
            or any(type(value[key]) is not str or not _HEX.fullmatch(value[key])
                for key in ("root_event_sha256", "principal_scope_sha256"))):
        raise ValueError("invalid conversation reference")
    return dict(value)


def validate_turn_preview(value, request):
    keys = {"schema", "work_ref", "operation_key", "reference", "turn_key", "state", "effect",
        "initial_consumption", "locator", "preview_digest", "parent_consumed", "can_send"}
    if (type(value) is not dict or set(value) != keys
            or value["schema"] != "mastermind.executive.fresh_conversation_turn_preview.v1"
            or value["state"] != "TURN_READY" or value["effect"] != "NONE"
            or value["parent_consumed"] is not False or value["can_send"] is not True
            or type(value["preview_digest"]) is not str or not _HEX.fullmatch(value["preview_digest"])):
        raise ValueError("invalid turn preview")
    # Reuse the exact closed selector/receipt/locator checks without changing
    # the retained turn-result schema or granting authority from public DATA.
    validate_turn_data({**{k: v for k, v in value.items() if k != "preview_digest"},
        "schema": "mastermind.executive.fresh_conversation_turn_data.v1",
        "state": "CONSUMED", "result": None}, request)
    return dict(value)
