"""Bounded private App-peer carrier for existing source-operation owners.

This independently authored contract validates values only. The authenticated
HTTP owner supplies the exact verified frame and original expiry; the kernel
App-peer owner and current sealed distinct-action grant still qualify every
read/commit. Nothing here authenticates a principal, checks a clock or retries.
"""
from __future__ import annotations
import json
import re

from common.workspace_source_operation_contract import validate_lookup, validate_advance
from common.executive_workspace_contract import PRINCIPAL_KEYS, RESOURCE, SCOPE

FRAME_SCHEMA = "mastermind.workspace_source_operation_frame.v1"
MAX_REQUEST_BYTES = 98304
MAX_CONTROL_REQUEST_BYTES = 32768
MAX_RESPONSE_BYTES = 32768
_PREFIXES = {"publish_project_proposal": "mmos-project-create-",
             "publish_project_plan_proposal": "mmos-project-plan-proposal-", "ADOPT_PLAN": "mmos-project-adopt-",
             "ACCEPT_DIRECTION": "mmos-direction-accept-", "add_project_file": "mmos-project-file-add-",
             "set_project_communication_preference": "mmos-project-preference-set-"}
_KNOWLEDGE = {"add_project_file", "set_project_communication_preference"}
_MAX_INT = 2**53 - 1


def _fail():
    raise ValueError("invalid_source_operation_frame")


def _tree(value, depth=0, count=None):
    if count is None: count = [0]
    count[0] += 1
    if depth > 24 or count[0] > 16384: _fail()
    if type(value) is dict:
        if any(type(key) is not str for key in value): _fail()
        return {key: _tree(item, depth + 1, count) for key, item in value.items()}
    if type(value) is list:
        return [_tree(item, depth + 1, count) for item in value]
    if value is None or type(value) in (str, bool): return value
    if type(value) is int and -_MAX_INT <= value <= _MAX_INT: return value
    _fail()


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys): _fail()


def _hex(value, size):
    if type(value) is not str or re.fullmatch("[0-9a-f]{" + str(size) + "}", value) is None: _fail()


def _identity(value):
    if type(value) is not dict or value.get("action") not in _PREFIXES: _fail()
    action = value["action"]
    if type(value.get("request_id")) is not str or re.fullmatch(re.escape(_PREFIXES[action]) + "[0-9a-f]{40}", value["request_id"]) is None: _fail()
    return action


def validate_knowledge_lookup(value):
    _keys(value, {"action", "request_id", "work_ref", "source_commit", "base_revision",
                  "request_sha256", "expected_preference_revision"})
    if _identity(value) not in _KNOWLEDGE: _fail()
    validate_lookup({"schema": "mastermind.workspace_source_operation_lookup.v1",
                     **{k: value[k] for k in ("action", "request_id", "work_ref")}})
    _hex(value["source_commit"], 40); _hex(value["base_revision"], 64); _hex(value["request_sha256"], 64)
    if value["expected_preference_revision"] is not None:
        if value["action"] == "add_project_file": _fail()
        _hex(value["expected_preference_revision"], 64)
    return dict(value)


def validate_witness(value):
    _keys(value, {"original_input", "recipe_fingerprint_sha256"})
    _hex(value["recipe_fingerprint_sha256"], 64)
    ref = value["original_input"]
    _keys(ref, {"schema", "input_ref", "artifact_sha256", "payload_sha256"})
    if (ref["schema"] != "mastermind.terminal_original_input_reference.v1"
            or type(ref["input_ref"]) is not str
            or re.fullmatch(r"terminal-input:[0-9a-f]{64}", ref["input_ref"]) is None): _fail()
    _hex(ref["artifact_sha256"], 64); _hex(ref["payload_sha256"], 64)


def operation_request_limit(operation, value):
    """Only a closed, bounded UTF-8 file prepare gets the larger envelope.

    This is a transport bound, never recipe/source/action qualification. The
    actual fixed compiler remains responsible for canonical record laws.
    """
    try:
        if operation != 'prepare' or type(value) is not dict or set(value) != {'action','request'} or value['action'] != 'add_project_file':
            return MAX_CONTROL_REQUEST_BYTES
        body=value['request']
        if type(body) is not dict or set(body) != {'schema','request_id','work_ref','source_commit','base_revision','file'} or body['schema'] != 'mastermind.project_file_add_request.v1':
            return MAX_CONTROL_REQUEST_BYTES
        _identity({'action':value['action'],'request_id':body['request_id']})
        validate_lookup({'schema':'mastermind.workspace_source_operation_lookup.v1','action':value['action'],
            'request_id':body['request_id'],'work_ref':body['work_ref']})
        _hex(body['source_commit'],40);_hex(body['base_revision'],64)
        file=body['file']
        if (type(file) is not dict or set(file) != {'display_name','media_type','content_utf8'}
                or type(file['display_name']) is not str or not 1<=len(file['display_name'].encode('utf-8'))<=128
                or file['media_type'] not in {'text/markdown','text/plain'}
                or type(file['content_utf8']) is not str or not 1<=len(file['content_utf8'].encode('utf-8'))<=32768):
            return MAX_CONTROL_REQUEST_BYTES
        return MAX_REQUEST_BYTES
    except (ValueError,TypeError,KeyError,UnicodeError):
        return MAX_CONTROL_REQUEST_BYTES


def validate_operation_request(operation, request):
    value = _tree(request)
    if operation == "prepare":
        _keys(value, {"action", "request"})
        body = value["request"]
        if type(body) is not dict or set(body) & {"principal", "verified_expires_at", "operation"}: _fail()
        action = _identity({"action": value["action"], "request_id": body.get("request_id")})
        if action == "publish_project_proposal":
            if "work_ref" in body: _fail()
        else:
            validate_lookup({"schema": "mastermind.workspace_source_operation_lookup.v1", "action": action,
                             "request_id": body["request_id"], "work_ref": body.get("work_ref")})
    elif operation in {"read", "reconcile"}:
        if type(value) is not dict: _fail()
        if value.get("action") in _KNOWLEDGE: validate_knowledge_lookup(value)
        else: validate_lookup(value)
    elif operation == "submit":
        _keys(value, {"action", "request_id", "work_ref", "preview_witness"})
        validate_lookup({"schema": "mastermind.workspace_source_operation_lookup.v1",
                         **{k: value[k] for k in ("action", "request_id", "work_ref")}})
        validate_witness(value["preview_witness"])
    elif operation == "advance": validate_advance(value)
    else: _fail()
    encoded=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
    if len(encoded)>operation_request_limit(operation,value):_fail()
    return value


def validate_frame(value):
    try:
        value = _tree(value)
        _keys(value, {"schema", "operation", "principal", "verified_expires_at", "request"})
        if value["schema"] != FRAME_SCHEMA or type(value["operation"]) is not str: _fail()
        expires = value["verified_expires_at"]
        if type(expires) is not int or not 0 <= expires <= _MAX_INT: _fail()
        principal = value["principal"]
        _keys(principal, PRINCIPAL_KEYS)
        if principal["resource"] != RESOURCE or principal["scopes"] != [SCOPE]: _fail()
        if any(type(principal[k]) is not str or not 1 <= len(principal[k]) <= 256
               or not principal[k].isascii() or any(ord(c) < 32 or ord(c) == 127 for c in principal[k])
               for k in PRINCIPAL_KEYS - {"scopes"}): _fail()
        value["request"] = validate_operation_request(value["operation"], value["request"])
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
        if len(encoded) > MAX_REQUEST_BYTES: _fail()
        return value
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        _fail()


def decode_frame(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_REQUEST_BYTES: _fail()
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value: _fail()
            value[key] = item
        return value
    def constant(_): _fail()
    try:
        return validate_frame(json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=constant))
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        _fail()
