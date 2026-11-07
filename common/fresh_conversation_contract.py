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


def validate_request(value, *, operation, schema=SCHEMA):
    if schema == NATIVE_SCHEMA:
        return validate_native_request(value, operation=operation)
    if schema != SCHEMA:
        raise ValueError("invalid conversation schema")
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


def admission_arguments(request, scoped_operation_key, *, schema=SCHEMA):
    selected = validate_request({key: request[key] for key in
        ("work_ref", "operation_key", "message")}, operation="preview", schema=schema)
    if type(scoped_operation_key) is not str or not _KEY.fullmatch(scoped_operation_key):
        raise ValueError("invalid operation key")
    objective = native_objective(selected["message"]) if schema == NATIVE_SCHEMA else selected["message"]
    return dict(operation_key=scoped_operation_key, objective=objective,
        department="executive-infrastructure", priority=0, execution_profile="research_only",
        workstream=selected["work_ref"], attempt_limit=1)


def _validate_principal(raw):
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


def validate_private_frame(value):
    if type(value) is dict and value.get("schema") == NATIVE_SCHEMA:
        return validate_native_private_frame(value)
    if (type(value) is not dict or set(value) != {"schema", "operation", "principal", "workspace_principal", "arguments"}
            or value["schema"] != SCHEMA):
        raise ValueError("invalid frame")
    operation = value["operation"]
    arguments = validate_request(value["arguments"], operation=operation)
    p = _validate_principal(value["principal"])
    workspace = value["workspace_principal"]
    if operation in DUAL_RESOURCE:
        workspace = _validate_principal(workspace)
    elif workspace is not None:
        raise ValueError("unexpected read principal")
    return dict(schema=SCHEMA, operation=operation, principal=p, workspace_principal=workspace, arguments=arguments)


def validate_data(value, request, *, schema=SCHEMA):
    if schema == NATIVE_SCHEMA:
        return validate_native_data(value, request)
    if schema != SCHEMA:
        raise ValueError("invalid conversation schema")
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

# Native v2 is an explicit product contract on the existing carrier. These
# values select syntax only; installed owners still decide all admission.
NATIVE_SCHEMA = "mastermind.executive.fresh_conversation.v2"
NATIVE_RESULT_SCHEMA = "mastermind.executive.fresh_conversation_result.v2"
NATIVE_DATA_SCHEMA = "mastermind.executive.fresh_conversation_data.v2"
NATIVE_TURN_DATA_SCHEMA = "mastermind.executive.fresh_conversation_turn_data.v2"
NATIVE_TURN_PREVIEW_SCHEMA = "mastermind.executive.fresh_conversation_turn_preview.v2"
NATIVE_CONTROL_DATA_SCHEMA = "mastermind.executive.fresh_conversation_control_data.v2"
NATIVE_RESULT_CONTRACT = "mastermind.dsh_native_conversation/v1"
NATIVE_MESSAGE_BYTES = 128 * 1024
NATIVE_MAX_REQUEST_BYTES = 512 * 1024
NATIVE_MAX_RESPONSE_BYTES = 32 * 1024
NATIVE_ROUTES = {
    "/os/executive/conversation/v2/" + path: operation
    for path, operation in (
        ("preview", "preview"), ("create", "create"), ("status", "status"), ("read", "read"),
        ("recover", "recover"),
        ("consume", "consume"), ("consume/status", "consume_status"),
        ("turn/preview", "turn_preview"), ("turn", "turn"),
        ("turn/status", "turn_status"), ("turn/read", "turn_read"), ("turn/recover", "turn_recover"),
        ("resume/preview", "resume_preview"), ("resume", "resume"), ("resume/status", "resume_status"),
        ("stop", "stop"), ("stop/status", "stop_status"))
}
NATIVE_MODIFYING = frozenset({"create", "consume", "turn", "resume", "stop", "recover", "turn_recover"})
NATIVE_DUAL_RESOURCE = NATIVE_MODIFYING | {"preview", "turn_preview", "resume_preview"}
NATIVE_PASSIVE = frozenset({"status", "read", "consume_status", "turn_status", "turn_read", "resume_status", "stop_status"})


def modifying_operations(schema):
    if schema == SCHEMA:
        return MODIFYING
    if schema == NATIVE_SCHEMA:
        return NATIVE_MODIFYING
    raise ValueError("invalid conversation schema")


def dual_resource_operations(schema):
    if schema == SCHEMA:
        return DUAL_RESOURCE
    if schema == NATIVE_SCHEMA:
        return NATIVE_DUAL_RESOURCE
    raise ValueError("invalid conversation schema")


def validate_native_message(value):
    if (type(value) is not str or not value.strip()
            or any((ord(c) < 32 and c not in "\t\n\r") or 127 <= ord(c) <= 159 for c in value)):
        raise ValueError("invalid native message")
    try:
        if len(value.encode("utf-8", errors="strict")) > NATIVE_MESSAGE_BYTES:
            raise ValueError("invalid native message")
    except UnicodeEncodeError:
        raise ValueError("invalid native message") from None
    return value


def native_message_identity(value):
    value = validate_native_message(value)
    raw = value.encode("utf-8", errors="strict")
    return {"sha256": hashlib.sha256(raw).hexdigest(), "utf8_bytes": len(raw)}


def native_objective(value):
    identity = native_message_identity(value)
    return json.dumps({"mode": "fresh_native_conversation", "result_contract": NATIVE_RESULT_CONTRACT,
        "message_sha256": identity["sha256"], "message_utf8_bytes": identity["utf8_bytes"]},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _native_id(value):
    from integrations.deepseek_harness.native_protocol import native_id
    return native_id(value)


def _hex(value, label):
    if type(value) is not str or not _HEX.fullmatch(value):
        raise ValueError("invalid " + label)
    return value


def _key(value, label):
    if type(value) is not str or not _KEY.fullmatch(value):
        raise ValueError("invalid " + label)
    return value


def _bounded_json(value, limit, *, newline=False):
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode("utf-8", errors="strict")
    except (ValueError, TypeError, UnicodeEncodeError):
        raise ValueError("invalid native JSON") from None
    if len(raw) + int(newline) > limit:
        raise ValueError("native encoded frame exceeds byte limit")
    return raw + (b"\n" if newline else b"")


def validate_native_request(value, *, operation):
    if type(operation) is not str or operation not in NATIVE_ROUTES.values():
        raise ValueError("invalid native operation")
    if type(value) is not dict:
        raise ValueError("invalid native request")
    reference_mode = "reference" in value
    if reference_mode and operation in {"preview", "create"}:
        raise ValueError("native creation requires its original operation key")
    keys = {"work_ref", "reference" if reference_mode else "operation_key"}
    if operation in {"preview", "create", "turn_preview", "turn"}:
        keys.add("message")
    if operation in {"consume", "consume_status", "turn_preview", "turn"}:
        keys.add("initial_digest")
    if operation in {"turn_preview", "turn", "turn_status", "turn_read", "turn_recover"}:
        keys.add("turn_key")
    if operation in {"resume_preview", "resume", "resume_status"}:
        keys.add("resume_key")
    if operation in {"stop", "stop_status"}:
        keys.add("stop_key")
    if operation in {"create", "turn", "resume"}:
        keys.add("preview_digest")
    if operation in {"resume_preview", "resume"}:
        keys.add("expected_result_digest")
    if operation == "stop":
        keys.update({"turn_id", "binding_digest"})
    if (set(value) != keys or type(value["work_ref"]) is not str or not _WORK.fullmatch(value["work_ref"])):
        raise ValueError("invalid native selector")
    if reference_mode:
        if validate_reference(value["reference"])["work_ref"] != value["work_ref"]:
            raise ValueError("foreign native reference")
    else:
        _key(value["operation_key"], "operation key")
    for name in ("turn_key", "resume_key", "stop_key"):
        if name in keys:
            _key(value[name], name)
    for name in ("preview_digest", "initial_digest", "expected_result_digest", "binding_digest"):
        if name in keys:
            _hex(value[name], name)
    if "turn_id" in keys:
        _native_id(value["turn_id"])
    if "message" in keys:
        validate_native_message(value["message"])
    return dict(value)


def validate_native_private_frame(value):
    if (type(value) is not dict or set(value) != {"schema", "operation", "principal", "workspace_principal", "arguments"}
            or value["schema"] != NATIVE_SCHEMA):
        raise ValueError("invalid native frame")
    operation = value["operation"]
    arguments = validate_native_request(value["arguments"], operation=operation)
    p = _validate_principal(value["principal"])
    workspace = value["workspace_principal"]
    if operation in NATIVE_DUAL_RESOURCE:
        workspace = _validate_principal(workspace)
    elif workspace is not None:
        raise ValueError("unexpected native read principal")
    frame = dict(schema=NATIVE_SCHEMA, operation=operation, principal=p, workspace_principal=workspace, arguments=arguments)
    _bounded_json(frame, NATIVE_MAX_REQUEST_BYTES, newline=True)
    return frame


def validate_native_result(value):
    from control_plane.native_conversation_result import NativeConversationResultRef, DSH_NATIVE_RESULT_CONTRACT
    if (type(value) is not dict or set(value) != {"contract", "digest", "reference"}
            or value["contract"] != DSH_NATIVE_RESULT_CONTRACT):
        raise ValueError("invalid native result")
    reference = NativeConversationResultRef.from_wire(value["reference"])
    if value["digest"] != reference.seal_digest:
        raise ValueError("native result digest differs from original seal")
    return {"contract": DSH_NATIVE_RESULT_CONTRACT, "digest": reference.seal_digest, "reference": reference.to_wire()}


def _native_selector(value, request):
    if value["reference"] is not None:
        validate_reference(value["reference"])
    if (value["work_ref"] != request["work_ref"]
            or value["operation_key"] != request.get("operation_key")
            or value["reference"] != request.get("reference")
            or value["parent_consumed"] is not False):
        raise ValueError("native response selector differs")


def _native_locator(value, request, *, require_child=False):
    if (type(value) is not dict or set(value) != {"work_ref", "root_job_id", "job_id", "attempt_id"}
            or value["work_ref"] != request["work_ref"]):
        raise ValueError("invalid native locator")
    if request.get("reference") is not None and value["root_job_id"] != request["reference"]["root_job_id"]:
        raise ValueError("native locator belongs to another original root")
    if require_child and (value["job_id"] is None or value["attempt_id"] is None):
        raise ValueError("native response lacks its original child and Attempt")
    _native_id(value["root_job_id"])
    for key in ("job_id", "attempt_id"):
        if value[key] is not None:
            _native_id(value[key])


def _native_session(value):
    if (type(value) is not dict or set(value) != {
            "attempt_id", "session_epoch_id", "process_generation_id", "provider_session_id", "binding_digest"}):
        raise ValueError("invalid native session projection")
    for key in ("attempt_id", "session_epoch_id", "process_generation_id", "provider_session_id"):
        _native_id(value[key])
    _hex(value["binding_digest"], "native binding")


def _native_active_turn(value):
    if type(value) is not dict or set(value) != {"turn_id", "begin_operation_id"}:
        raise ValueError("invalid native active-turn projection")
    for key in value:
        _native_id(value[key])


def _native_consumption(value):
    if (type(value) is not dict or set(value) != {"state", "event_id", "event_sha256", "initial_digest"}
            or value["state"] != "CONSUMED" or type(value["event_id"]) is not int
            or not 1 <= value["event_id"] <= 2**53 - 1):
        raise ValueError("invalid native consumption")
    _hex(value["event_sha256"], "consumption Event")
    _hex(value["initial_digest"], "initial digest")


def validate_native_data(value, request):
    if type(value) is not dict:
        raise ValueError("invalid native response")
    schema = value.get("schema")
    if schema == NATIVE_TURN_DATA_SCHEMA or schema == NATIVE_TURN_PREVIEW_SCHEMA:
        return _validate_native_turn_data(value, request)
    if schema == NATIVE_CONTROL_DATA_SCHEMA:
        return _validate_native_control_data(value, request)
    keys = {"schema", "work_ref", "operation_key", "reference", "state", "effect", "parent_consumed",
            "preview", "locator", "session", "active_turn", "result", "head_result", "can_send", "can_resume", "can_stop"}
    if (set(value) != keys or schema != NATIVE_DATA_SCHEMA
            or value["state"] not in {"PREVIEW_READY", "ABSENT", "ADMITTED", "ACTIVE", "CREATED", "IDLE", "SETTLED", "RECONCILIATION_REQUIRED"}
            or value["effect"] not in {"NONE", "ADMITTED", "COMMITTED", "UNKNOWN"}
            or any(type(value[key]) is not bool for key in ("can_send", "can_resume", "can_stop"))):
        raise ValueError("invalid native response")
    _native_selector(value, request)
    state = value["state"]
    if state in {"ABSENT", "PREVIEW_READY"}:
        if (any(value[key] is not None for key in ("locator", "session", "active_turn", "result", "head_result"))
                or any(value[key] for key in ("can_send", "can_resume", "can_stop"))
                or value["effect"] != "NONE"):
            raise ValueError("native pre-admission state cannot carry a session or effect")
    if state == "ADMITTED" and (value["locator"] is None or value["session"] is not None
            or value["active_turn"] is not None or value["result"] is not None or value["head_result"] is not None
            or any(value[key] for key in ("can_send", "can_resume", "can_stop"))):
        raise ValueError("native admitted state lacks its original pending locator")
    if state in {"CREATED", "IDLE"} and (value["locator"] is None or value["session"] is None
            or value["result"] is None or value["head_result"] is None):
        raise ValueError("native settled session lacks its original result anchors")
    if state in {"SETTLED", "RECONCILIATION_REQUIRED"} and any(value[key] for key in ("can_send", "can_resume", "can_stop")):
        raise ValueError("native withheld state cannot project usable controls")
    if value["locator"] is not None:
        _native_locator(value["locator"], request, require_child=state in {"ACTIVE", "CREATED", "IDLE"})
    if value["session"] is not None:
        _native_session(value["session"])
        if value["locator"] is None or value["locator"]["attempt_id"] != value["session"]["attempt_id"]:
            raise ValueError("native session locator differs")
    if value["active_turn"] is not None:
        _native_active_turn(value["active_turn"])
        if value["session"] is None or value["state"] != "ACTIVE":
            raise ValueError("native active turn lacks original session")
    elif value["state"] == "ACTIVE":
        raise ValueError("native active state lacks original turn")
    for key in ("result", "head_result"):
        if value[key] is not None:
            validate_native_result(value[key])
    if value["head_result"] is not None and value["result"] is None:
        raise ValueError("native head lacks original initial anchor")
    if ((value["can_stop"] and value["active_turn"] is None)
            or (value["can_send"] and (value["state"] != "CREATED" or value["session"] is None or value["head_result"] is None))
            or (value["can_resume"] and (value["state"] != "IDLE" or value["session"] is None or value["head_result"] is None))):
        raise ValueError("invalid native control projection")
    preview = value["preview"]
    if value["state"] == "PREVIEW_READY":
        if (type(preview) is not dict or set(preview) != {"digest", "profile_digest", "source_digest", "grounding", "attempt_limit", "worker_account"}
                or type(preview["grounding"]) is not dict or type(preview["attempt_limit"]) is not int or preview["attempt_limit"] != 1
                or preview["worker_account"] != "REGISTERED_NOT_SESSION_ATTESTED"):
            raise ValueError("invalid native preview")
        for key in ("digest", "profile_digest", "source_digest"):
            _hex(preview[key], "native preview")
    elif preview is not None:
        raise ValueError("unexpected native preview")
    _bounded_json(value, NATIVE_MAX_RESPONSE_BYTES)
    return dict(value)


def _validate_native_turn_data(value, request):
    preview = value["schema"] == NATIVE_TURN_PREVIEW_SCHEMA
    keys = {"schema", "work_ref", "operation_key", "reference", "turn_key", "state", "effect",
            "initial_consumption", "locator", "parent_consumed", "can_send"}
    keys.add("preview_digest" if preview else "result")
    if (set(value) != keys or value["turn_key"] != request.get("turn_key")
            or value["state"] not in ({"TURN_READY"} if preview else {"CONSUMED", "ABSENT", "RECONCILIATION_REQUIRED", "RECORDED"})
            or value["effect"] not in {"NONE", "COMMITTED", "UNKNOWN"} or type(value["can_send"]) is not bool
            or (value["can_send"] and value["state"] not in {"TURN_READY", "CONSUMED"})):
        raise ValueError("invalid native turn data")
    _native_selector(value, request)
    _native_locator(value["locator"], request, require_child=value["state"] != "ABSENT")
    consumption = value["initial_consumption"]
    if consumption is not None:
        _native_consumption(consumption)
        if "initial_digest" in request and consumption["initial_digest"] != request["initial_digest"]:
            raise ValueError("native initial anchor differs")
    if value["state"] in {"TURN_READY", "CONSUMED", "RECORDED"} and consumption is None:
        raise ValueError("native turn lacks original consumption")
    if preview:
        _hex(value["preview_digest"], "native Send preview")
        if value["effect"] != "NONE" or value["can_send"] is not True:
            raise ValueError("invalid native Send preview")
    elif value["state"] == "RECORDED":
        validate_native_result(value["result"])
    elif value["result"] is not None:
        raise ValueError("unexpected native turn result")
    _bounded_json(value, NATIVE_MAX_RESPONSE_BYTES)
    return dict(value)


def _validate_native_control_data(value, request):
    keys = {"schema", "work_ref", "operation_key", "reference", "kind", "control_key", "state", "effect",
            "locator", "session", "active_turn", "operation_id", "receipt", "head_result", "preview_digest", "parent_consumed", "target"}
    if (set(value) != keys or value["kind"] not in {"stop", "resume"}
            or value["control_key"] != request.get(value["kind"] + "_key")
            or value["state"] not in {"RESUME_READY", "ABSENT", "INTENT", "APPLIED", "EFFECT_UNKNOWN", "RECONCILIATION_REQUIRED"}
            or value["effect"] not in {"NONE", "COMMITTED", "UNKNOWN"}):
        raise ValueError("invalid native control data")
    _native_selector(value, request)
    if value["state"] == "ABSENT" and (value["effect"] != "NONE" or any(value[key] is not None
            for key in ("target", "session", "active_turn", "operation_id", "receipt", "head_result", "preview_digest"))):
        raise ValueError("absent native control cannot carry an operation or receipt")
    if value["state"] == "RESUME_READY" and value["operation_id"] is not None:
        raise ValueError("native resume preview cannot carry an operation")
    target = value["target"]
    # Historical target comes from the original control-request Event. Current
    # session/turn projections may advance; their shape grants no authority.
    # The original owner must join request Event -> operation -> receipt.
    if value["state"] in {"RESUME_READY", "INTENT", "APPLIED", "EFFECT_UNKNOWN"} and target is None:
        raise ValueError("native control lacks its original target")
    if target is not None:
        field = "turn_id" if value["kind"] == "stop" else "expected_result_digest"
        if type(target) is not dict or set(target) != {field, "binding_digest"}:
            raise ValueError("invalid native original control target")
        _hex(target["binding_digest"], "original target binding")
        if field == "turn_id":
            _native_id(target[field])
        else:
            _hex(target[field], "original target result")
        for name in target:
            if name in request and target[name] != request[name]:
                raise ValueError("native control target differs from the original request")
    if value["state"] == "RESUME_READY" and (value["locator"] is None or value["session"] is None
            or value["head_result"] is None or value["active_turn"] is not None or value["receipt"] is not None):
        raise ValueError("native resume preview lacks its original idle session")
    if value["locator"] is not None:
        _native_locator(value["locator"], request, require_child=value["state"] != "ABSENT")
    if value["session"] is not None:
        _native_session(value["session"])
        if value["locator"] is None or value["locator"]["attempt_id"] != value["session"]["attempt_id"]:
            raise ValueError("native control session locator differs")
    if value["active_turn"] is not None:
        _native_active_turn(value["active_turn"])
        if value["session"] is None:
            raise ValueError("native control turn lacks session")
    if value["head_result"] is not None:
        validate_native_result(value["head_result"])
    operation = value["operation_id"]
    if operation is not None:
        _native_id(operation)
    receipt = value["receipt"]
    if receipt is not None:
        from control_plane.operator_harness_contract import OperationId, OperationReceiptKind, operation_receipt_command_id
        if (operation is None or type(receipt) is not dict
                or set(receipt) != {"kind", "command_id", "event_id", "event_sha256"}
                or type(receipt["event_id"]) is not int or not 1 <= receipt["event_id"] <= 2**53 - 1):
            raise ValueError("invalid native control receipt")
        kind = OperationReceiptKind(receipt["kind"])
        if kind not in {OperationReceiptKind.INTENT, OperationReceiptKind.APPLIED, OperationReceiptKind.EFFECT_UNKNOWN}:
            raise ValueError("invalid native control receipt kind")
        expected_command = operation if kind is OperationReceiptKind.INTENT else operation_receipt_command_id(OperationId(operation), kind)
        if receipt["command_id"] != expected_command:
            raise ValueError("native control receipt belongs to another operation")
        _hex(receipt["event_sha256"], "native control Event")
        if value["state"] in {"INTENT", "APPLIED", "EFFECT_UNKNOWN"} and kind is not getattr(OperationReceiptKind, value["state"]):
            raise ValueError("native control receipt state differs")
    elif value["state"] in {"INTENT", "APPLIED", "EFFECT_UNKNOWN"}:
        raise ValueError("native control state lacks its original receipt")
    if value["state"] == "RESUME_READY":
        if value["kind"] != "resume" or value["effect"] != "NONE":
            raise ValueError("invalid native resume preview")
        if value["head_result"]["digest"] != request["expected_result_digest"]:
            raise ValueError("native resume head differs from expected original result")
        if target["binding_digest"] != value["session"]["binding_digest"]:
            raise ValueError("native resume target binding differs from current idle session")
        _hex(value["preview_digest"], "native resume preview")
    elif value["preview_digest"] is not None:
        raise ValueError("unexpected native control preview")
    _bounded_json(value, NATIVE_MAX_RESPONSE_BYTES)
    return dict(value)


def validate_native_response(value, request, *, operation):
    validate_native_request(request, operation=operation)
    if (type(value) is not dict or set(value) != {"schema", "operation", "ok", "data", "error"}
            or value["schema"] != NATIVE_RESULT_SCHEMA or value["operation"] != operation
            or type(value["ok"]) is not bool):
        raise ValueError("invalid native response wrapper")
    if value["ok"]:
        if value["error"] is not None:
            raise ValueError("unexpected native error")
        data = validate_native_data(value["data"], request)
        expected = (NATIVE_DATA_SCHEMA if operation in {"preview", "create", "status", "read", "recover"}
            else NATIVE_TURN_PREVIEW_SCHEMA if operation == "turn_preview"
            else NATIVE_CONTROL_DATA_SCHEMA if operation.startswith(("resume", "stop"))
            else NATIVE_TURN_DATA_SCHEMA)
        if data["schema"] != expected:
            raise ValueError("native response contract differs from operation")
        states = {
            "consume": {"CONSUMED"}, "consume_status": {"ABSENT", "CONSUMED"},
            "turn": {"ABSENT", "RECONCILIATION_REQUIRED", "RECORDED"},
            "turn_status": {"ABSENT", "RECONCILIATION_REQUIRED", "RECORDED"},
            "turn_read": {"ABSENT", "RECONCILIATION_REQUIRED", "RECORDED"},
            "turn_recover": {"ABSENT", "RECONCILIATION_REQUIRED", "RECORDED"},
            "turn_preview": {"TURN_READY"}, "resume_preview": {"RESUME_READY"},
            "resume": {"RECONCILIATION_REQUIRED", "INTENT", "APPLIED", "EFFECT_UNKNOWN"},
            "stop": {"RECONCILIATION_REQUIRED", "INTENT", "APPLIED", "EFFECT_UNKNOWN"},
            "resume_status": {"ABSENT", "RECONCILIATION_REQUIRED", "INTENT", "APPLIED", "EFFECT_UNKNOWN"},
            "stop_status": {"ABSENT", "RECONCILIATION_REQUIRED", "INTENT", "APPLIED", "EFFECT_UNKNOWN"},
        }
        if operation in states and data["state"] not in states[operation]:
            raise ValueError("native response state differs from operation")
        if operation in {"consume_status", "turn", "turn_status", "turn_read", "turn_recover"} and data["can_send"]:
            raise ValueError("native original recovery cannot authorize another Send")
        if ((operation == "preview") != (data["state"] == "PREVIEW_READY")
                or (operation == "turn_preview") != (data["state"] == "TURN_READY")
                or (operation == "resume_preview") != (data["state"] == "RESUME_READY")):
            raise ValueError("native preview response differs from operation")
        if operation in NATIVE_PASSIVE | {"preview", "turn_preview", "resume_preview", "recover", "turn_recover"} and data["effect"] != "NONE":
            raise ValueError("native passive response cannot claim a new effect")
        if expected == NATIVE_CONTROL_DATA_SCHEMA and data["kind"] != operation.split("_", 1)[0]:
            raise ValueError("native control kind differs")
    else:
        error = value["error"]
        if (value["data"] is not None or type(error) is not dict or set(error) != {"code", "message"}
                or type(error["code"]) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", error["code"])
                or type(error["message"]) is not str or not 1 <= len(error["message"]) <= 256):
            raise ValueError("invalid native refusal")
    # Include the incumbent private transport wrapper and terminating newline.
    _bounded_json({"ok": True, "result": value}, NATIVE_MAX_RESPONSE_BYTES, newline=True)
    return dict(value)
