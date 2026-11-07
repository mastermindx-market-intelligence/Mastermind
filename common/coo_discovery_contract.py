"""Finite discovery tools and owner results; no auth, transport or state owner."""
from __future__ import annotations
import hashlib
import json

from common import coo_agentos_context_contract as context
from common import workspace_discovery_correction_contract as correction
from common import workspace_discovery_original_contract as original
from common.workspace_project_knowledge_read_contract import selection as current_selection
from common.workspace_project_knowledge_contract import validate_discovery_source
from common.workspace_source_operation_contract import validate_status
from common.workspace_source_operation_wire import validate_witness

CATALOGUE = context.DISCOVERY_CATALOGUE
SOURCE_TOOL = "executive_project_discovery_source"
CORRECTION_TOOL = "executive_project_discovery_correction"
TOOLS = (SOURCE_TOOL, CORRECTION_TOOL)
READ_ACTION = "read_project_discovery"
CORRECTION_ACTION = "correct_project_discovery"
RESULT_SCHEMA = "mastermind.coo_project_discovery_result.v1"
MAX_RESULT_BYTES = 160 * 1024


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("invalid_discovery_tool")


def arguments(tool, value):
    if tool == SOURCE_TOOL:
        if type(value) is dict and value.get("mode") == "current":
            _keys(value, {"mode", "work_ref", "discovery_ref", "expected_source_commit"})
            current_selection({k: v for k, v in value.items() if k != "mode"}, operation="project_discovery_source")
        else:
            _keys(value, {"mode", "lookup"})
            if value["mode"] != "original": raise ValueError("invalid_discovery_tool")
            correction.validate_lookup(value["lookup"])
    elif tool == CORRECTION_TOOL:
        if type(value) is not dict or type(value.get("operation")) is not str:
            raise ValueError("invalid_discovery_tool")
        mode = value["operation"]
        if mode == "prepare":
            _keys(value, {"operation", "request"}); correction.validate_request(value["request"])
        elif mode in {"read", "reconcile", "submit"}:
            _keys(value, {"operation", "lookup", "preview_witness"} if mode == "submit" else {"operation", "lookup"})
            correction.validate_lookup(value["lookup"])
            if mode == "submit": validate_witness(value["preview_witness"])
        else: raise ValueError("invalid_discovery_tool")
    else: raise ValueError("invalid_discovery_tool")
    raw = correction.canonical(value)
    if len(raw) > 32 * 1024: raise ValueError("invalid_discovery_tool")
    return json.loads(raw)


def operation(tool, value):
    return value["mode"] if tool == SOURCE_TOOL else value["operation"]


def lookup(tool, value):
    value = arguments(tool, value)
    if tool == SOURCE_TOOL and value["mode"] == "current":
        return {k: v for k, v in value.items() if k != "mode"}
    return correction.request_lookup(value["request"]) if operation(tool, value) == "prepare" else value["lookup"]


def action(tool, value):
    return READ_ACTION if tool == SOURCE_TOOL and value["mode"] == "current" else CORRECTION_ACTION


def mutating(tool, value):
    return tool == CORRECTION_TOOL and value["operation"] in {"prepare", "submit", "reconcile"}


def workspace_scope(principal):
    context.workspace_principal(principal)
    return hashlib.sha256(correction.canonical(principal)).hexdigest()


def validate_data(tool, value, body, *, workspace_principal):
    """Qualify the unchanged actual Workspace body before exposing it."""
    selected, mode, scope = lookup(tool, value), operation(tool, value), workspace_scope(workspace_principal)
    if tool == SOURCE_TOOL:
        if mode == "original": return original.validate(body, lookup=selected, principal_scope=scope)
        body = validate_discovery_source(body)
        if (body["selection"] != {k: selected[k] for k in ("work_ref", "discovery_ref")}
                or body["availability"] != "AVAILABLE" or body["source"]["commit"] != selected["expected_source_commit"]
                or body.get("code_context") is None or body.get("data_observation") is None):
            raise ValueError("discovery_source_unavailable")
        return body
    if mode == "prepare": return correction.validate_preview(body, request=value["request"], principal_scope=scope)
    body = validate_status(body)
    if (body["selection"] != {k: selected[k] for k in ("action", "request_id", "work_ref")}
            or body["owner_context"] != {"principal_scope": scope}
            or body["request_sha256"] not in (None, selected["request_sha256"])
            or (mode == "submit" and body["recipe_fingerprint_sha256"] not in
                (None, value["preview_witness"]["recipe_fingerprint_sha256"]))):
        raise ValueError("discovery_operation_mismatch")
    sources = [] if body["receipt"] is None else body["receipt"]["sources"]
    if sources:
        correction.validate_sources(selected, scope, sources)
        if ({source["path"] for source in sources} != set(correction.expected_paths(selected, scope))
                or len({source["commit"] for source in sources}) != 1):
            raise ValueError("discovery_operation_mismatch")
    return body


def result(tool, value, *, state, reason, principal_context=None, capability_profile_digest=None,
           workspace_principal=None, data=None):
    value = arguments(tool, value)
    selected = lookup(tool, value)
    pairs = {"OBSERVED": {"OWNER_RESULT"},
             "NOT_DISPATCHED": {"AUTHORITY_UNAVAILABLE", "INVALID_INPUT", "SOURCE_UNAVAILABLE", "ORIGINAL_OPERATION_UNRESOLVED"},
             "EFFECT_UNKNOWN": {"ORIGINAL_OUTCOME_UNKNOWN"},
             "UNAVAILABLE": {"SOURCE_UNAVAILABLE", "AUTHORITY_UNAVAILABLE"}}
    if type(state) is not str or type(reason) is not str or reason not in pairs.get(state, set()):
        raise ValueError("invalid_discovery_result")
    if state == "EFFECT_UNKNOWN" and not mutating(tool, value):
        raise ValueError("invalid_discovery_result")
    if state == "UNAVAILABLE" and mutating(tool, value):
        raise ValueError("invalid_discovery_result")
    identities = (principal_context, capability_profile_digest, workspace_principal)
    if any(item is not None for item in identities):
        if any(item is None for item in identities): raise ValueError("invalid_discovery_result")
        checked_context = context.context(principal_context)
        context._digest(capability_profile_digest); context.workspace_principal(workspace_principal)
        if checked_context.work_ref != selected["work_ref"]: raise ValueError("invalid_discovery_result")
    if state == "OBSERVED":
        if reason != "OWNER_RESULT" or any(item is None for item in identities):
            raise ValueError("invalid_discovery_result")
        data = validate_data(tool, value, data, workspace_principal=workspace_principal)
    elif data is not None or reason == "OWNER_RESULT":
        raise ValueError("invalid_discovery_result")
    body = {"schema": RESULT_SCHEMA, "catalogue": CATALOGUE, "tool": tool,
        "operation": operation(tool, value), "selection": selected, "state": state, "reason": reason,
        "principal_context": principal_context, "capability_profile_digest": capability_profile_digest,
        "workspace_principal": workspace_principal, "data": data}
    return context.decode(context.encode(body, limit=MAX_RESULT_BYTES), limit=MAX_RESULT_BYTES)


def validate_result(body, *, tool, value, expected_context, capability_profile_digest, workspace_principal):
    if type(body) is not dict: raise ValueError("invalid_discovery_result")
    rebuilt = result(tool, value, **{k: body.get(k) for k in (
        "state", "reason", "principal_context", "capability_profile_digest", "workspace_principal", "data")})
    if rebuilt != body: raise ValueError("invalid_discovery_result")
    if body["state"] == "OBSERVED" and (body["principal_context"] != expected_context
            or body["capability_profile_digest"] != capability_profile_digest
            or body["workspace_principal"] != workspace_principal):
        raise ValueError("discovery_result_owner_changed")
    if body["principal_context"] is not None and (body["principal_context"] != expected_context
            or body["capability_profile_digest"] != capability_profile_digest
            or body["workspace_principal"] != workspace_principal):
        raise ValueError("discovery_result_owner_changed")
    return rebuilt
