"""Closed project-help read on the existing enrolled COO owner.

Source identities address one explicitly enrolled original mission. They are
not grants, native-session attestations, dispatch, consumption or acceptance.
The host re-proves them against current Workspace owners on every read.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

CATALOGUE = "coo.project_help.v1"
# Explicit ordinary API catalogue only. Legacy help outputs retain their
# original v1 wire, and native publication contracts do not inherit this set.
API_REQUESTER_CATALOGUE = "coo.project_help_requester.v1"
ACTION = "read_project_help"
TOOL = "executive_project_help"
FRAME_SCHEMA = "mastermind.ceo_ingress.coo_project_help.v1"
RESULT_SCHEMA = "mastermind.coo_project_help_result.v1"
EXECUTION_RESULT_SCHEMA = "mastermind.coo_project_help_result.v2"
EXECUTION_WITNESS_SCHEMA = "mastermind.project_execution_input_read_witness.v1"
EXECUTION_READ_QUALIFICATION = "CURRENT_DATA_EXECUTION_RESOURCE_READ"
SCOPE_SCHEMA = "mastermind.project_help_scope.v1"
PLAN_SCHEMA = "mastermind.project_help_source_plan.v1"
MAX_REQUEST_BYTES = 8192
MAX_RESPONSE_BYTES = 32 * 1024
MAX_TARGETS = 16
PRIVATE_READ_MAX_SECONDS = 25.0
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_REPOSITORIES = {"mastermindx-market-intelligence/Mastermind", "mastermindx-market-intelligence/macro"}
_FRAME_KEYS = {"schema", "principal", "session_principal", "workspace_principal",
               "principal_context", "capability_profile_digest"}
_RESULT_KEYS = {"schema", "catalogue", "principal_context", "capability_profile_digest",
                "workspace_principal", "scope", "observation", "relationships", "targets",
                "execution_routes", "execution_authority", "native_origin_attested"}
_TARGET_KEYS = {"target_ref", "kind", "generation", "addressable", "continuation_operation_key",
                "work_ref", "root_job_id"}


def _refuse():
    raise ValueError("PROJECT_HELP_UNAVAILABLE")


def _shape(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _refuse()


def _text(value, maximum=256):
    if type(value) is not str or not 0 < len(value) <= maximum or not value.isprintable() or value != value.strip():
        _refuse()
    return value


def _digest(value):
    if type(value) is not str or _SHA.fullmatch(value) is None:
        _refuse()
    return value


def encode(value, *, limit=MAX_RESPONSE_BYTES):
    try:
        body = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
            separators=(",", ":")).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _refuse()
    if len(body) > limit:
        _refuse()
    return body


def decode(raw, *, limit=MAX_RESPONSE_BYTES):
    from common.coo_agentos_context_contract import decode as decode_context
    return decode_context(raw, limit=limit)


def _selection(value):
    from common.workspace_project_plan_contract import validate_selection
    return validate_selection(value)


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def source_plan(value):
    from common.project_task_contract import _path
    _shape(value, {"schema", "work_ref", "source", "contract_sha256"})
    if value["schema"] != PLAN_SCHEMA:
        _refuse()
    _selection({"work_ref": value["work_ref"]})
    _digest(value["contract_sha256"])
    source = value["source"]
    _shape(source, {"repository", "commit", "path", "content_sha256"})
    if source["repository"] not in _REPOSITORIES or type(source["commit"]) is not str or not _COMMIT.fullmatch(source["commit"]):
        _refuse()
    path = _text(source["path"], 512)
    _path(path, plan=True)
    if (path.startswith("/") or "\\" in path or not path.endswith(".md")
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or any(character in path for character in "?#%")):
        _refuse()
    _digest(source["content_sha256"])
    encode(value, limit=2048)
    return copy.deepcopy(value)


def scope(value):
    from common.executive_workspace_contract import _check_job_id
    _shape(value, {"schema", "root_job_id", "source_plan"})
    if value["schema"] != SCOPE_SCHEMA or not _check_job_id(value["root_job_id"]):
        _refuse()
    source_plan(value["source_plan"])
    return copy.deepcopy(value)


def arguments(value):
    return _selection(value)


def validate_frame(value):
    from common import coo_agentos_context_contract as context_wire
    _shape(value, _FRAME_KEYS)
    if value["schema"] != FRAME_SCHEMA:
        _refuse()
    context_wire.validate_current_frame({key: value[key] for key in (
        "principal", "workspace_principal", "principal_context", "capability_profile_digest")}
        | {"schema": context_wire.CURRENT_FRAME_SCHEMA})
    # This is the original verified Executive projection, serialized by the
    # App. Reusing six facts does not fabricate token times or a principal.
    from control_plane.principal_projection import NeutralPrincipalProjection, neutral_principal_projection
    import dataclasses
    raw = value["session_principal"]
    _shape(raw, {field.name for field in dataclasses.fields(NeutralPrincipalProjection)})
    if type(raw["scopes"]) is not list:
        _refuse()
    principal = neutral_principal_projection(**(raw | {"scopes": tuple(raw["scopes"])}))
    facts = value["principal"]
    if (any(getattr(principal, key) != facts[key] for key in (
            "policy_id", "issuer_digest", "subject_digest", "client_ref", "resource"))
            or list(principal.scopes) != facts["scopes"]
            or "mastermind.executive.read" not in principal.scopes):
        _refuse()
    encode(value, limit=MAX_REQUEST_BYTES)
    return copy.deepcopy(value)


def context_matches_source_plan(context, selected, *, source_ref=None):
    """Compare actual parser output; this comparison creates no authority."""
    selected = source_plan(selected)
    if (type(context) is not dict
            or context.get("schema") != "mastermind.project_task_context.v1"
            or context.get("execution_authority") is not False
            or context.get("workstream") != selected["work_ref"]
            or context.get("source_path") != selected["source"]["path"]
            or context.get("source_sha256") != selected["source"]["content_sha256"]
            or context.get("contract_sha256") != selected["contract_sha256"]):
        _refuse()
    if source_ref is not None:
        source = selected["source"]
        expected = f"https://github.com/{source['repository']}/blob/{source['commit']}/{source['path']}"
        if source_ref != expected:
            _refuse()
    return True


def unavailable_targets(reason):
    if reason not in {"SESSION_BRIDGE_NOT_COMPOSED", "CURRENT_TARGETS_UNAVAILABLE", "TARGET_BUDGET_EXCEEDED"}:
        _refuse()
    return {"state": "UNAVAILABLE", "reason_codes": [reason], "items": [],
            "scope": "ORIGINAL_EXECUTIVE_ROOT", "coverage": "CURRENT_INSTALLED_SESSION_BRIDGE"}


def unavailable_routes(reason="CAPACITY_READ_NOT_COMPOSED"):
    if reason not in {"CAPACITY_READ_NOT_COMPOSED", "CURRENT_CAPACITY_UNAVAILABLE", "CAPACITY_CONTEXT_OVER_BUDGET"}:
        _refuse()
    return {"state": "UNAVAILABLE", "reason_codes": [reason], "capacity": None,
        "scope": "ESTATE_CAPACITY_NOT_TASK_PLACEMENT", "task_placement": "NOT_EVALUATED",
        "new_execution_authorized": False}


def observed_routes(capacity):
    from common.workspace_capacity_fabric_contract import validate_result as validate_capacity
    validate_capacity(capacity)
    if capacity["availability"] != "AVAILABLE":
        _refuse()
    if len(capacity["resources"]) > 16 or len(encode(capacity, limit=262144)) > 12 * 1024:
        return unavailable_routes("CAPACITY_CONTEXT_OVER_BUDGET")
    return {"state": "AVAILABLE", "reason_codes": [], "capacity": copy.deepcopy(capacity),
        "scope": "ESTATE_CAPACITY_NOT_TASK_PLACEMENT", "task_placement": "NOT_EVALUATED",
        "new_execution_authorized": False}


def validate_execution_witness(value, *, selected_scope, project_plan_sha256):
    """Closed read evidence; only the original input owner can qualify it."""
    selected = scope(selected_scope)
    _shape(value, {"schema", "selection", "original_source_sha256", "input_reference_sha256",
        "input_artifact_sha256", "input_payload_sha256", "input_context_sha256",
        "original_source_plan", "current_adoption", "execution_authorized"})
    if (value["schema"] != EXECUTION_WITNESS_SCHEMA
            or value["selection"] != {"work_ref": selected["source_plan"]["work_ref"],
                "root_job_id": selected["root_job_id"]}
            or value["execution_authorized"] is not False
            or source_plan(value["original_source_plan"]) != selected["source_plan"]):
        _refuse()
    for key in ("original_source_sha256", "input_reference_sha256", "input_artifact_sha256",
                "input_payload_sha256", "input_context_sha256"):
        _digest(value[key])
    _digest(project_plan_sha256)
    if value["current_adoption"] != {
            "state": "MATCHES_ORIGINAL_ADOPTED_SOURCE_AND_BYTES",
            "source_plan_sha256": digest(selected["source_plan"]),
            "project_plan_sha256": project_plan_sha256}:
        _refuse()
    return copy.deepcopy(value)


def validate_result(value, *, expected_context, capability_profile_digest,
                    expected_workspace_principal, expected_scope=None):
    from common import coo_agentos_context_contract as context_wire
    execution = type(value) is dict and value.get("schema") == EXECUTION_RESULT_SCHEMA
    _shape(value, _RESULT_KEYS | {"original_execution"} if execution else _RESULT_KEYS)
    context_wire.context(expected_context)
    context_wire.workspace_principal(expected_workspace_principal)
    _digest(capability_profile_digest)
    selected = scope(value["scope"])
    if (value["schema"] not in {RESULT_SCHEMA, EXECUTION_RESULT_SCHEMA} or value["catalogue"] != CATALOGUE
            or value["principal_context"] != expected_context
            or value["capability_profile_digest"] != capability_profile_digest
            or value["workspace_principal"] != expected_workspace_principal
            or selected["source_plan"]["work_ref"] != expected_context["work_ref"]
            or expected_scope is not None and selected != scope(expected_scope)
            or value["execution_authority"] is not False
            or value["native_origin_attested"] is not False):
        _refuse()
    observation = value["observation"]
    _shape(observation, {"mission_owner_sha256", "project_plan_sha256", "relationship", "currentness", "mission"})
    _digest(observation["mission_owner_sha256"])
    _digest(observation["project_plan_sha256"])
    if execution:
        validate_execution_witness(value["original_execution"], selected_scope=selected,
            project_plan_sha256=observation["project_plan_sha256"])
    if observation["relationship"] != "SEPARATE_READS_WITH_BEFORE_AFTER_GUARDS" or observation["currentness"] != "CURRENT_AT_ACQUISITION":
        _refuse()
    mission = observation["mission"]
    _shape(mission, {"qualification", "root_origin_sha256", "mission_read_state", "diagnostics", "transport", "execution_authorized"})
    _shape(mission["transport"], {"dispatch_state", "reason", "actionable", "historical"})
    if (mission["execution_authorized"] is not False
            or type(mission["transport"]["actionable"]) is not bool
            or type(mission["transport"]["historical"]) is not bool):
        _refuse()
    if type(mission["diagnostics"]) is not list or len(mission["diagnostics"]) > 32:
        _refuse()
    for diagnostic in mission["diagnostics"]:
        _text(diagnostic, 1024)
    _text(mission["transport"]["dispatch_state"])
    if mission["transport"]["reason"] is not None:
        _text(mission["transport"]["reason"], 512)
    if mission["qualification"] == "CURRENT_MISSION":
        if mission["mission_read_state"] != "CURRENT" or mission["root_origin_sha256"] is not None:
            _refuse()
    elif mission["qualification"] in {"CURRENT_DATA_CARD_WITH_UNOBSERVED_DISPATCH", EXECUTION_READ_QUALIFICATION}:
        _digest(mission["root_origin_sha256"])
        if (mission["mission_read_state"] != "PARTIAL" or mission["transport"] != {
                "dispatch_state": "UNKNOWN", "reason": "dispatch_evidence_not_supplied",
                "actionable": False, "historical": True}):
            _refuse()
    else:
        _refuse()
    if execution != (mission["qualification"] == EXECUTION_READ_QUALIFICATION):
        _refuse()
    from common.paperclip_contract import validate_context
    validate_context(value["relationships"], work_ref=expected_context["work_ref"])
    routes = value["execution_routes"]
    _shape(routes, {"state", "reason_codes", "capacity", "scope", "task_placement", "new_execution_authorized"})
    if routes["state"] == "UNAVAILABLE":
        if (type(routes["reason_codes"]) is not list or len(routes["reason_codes"]) != 1
                or routes != unavailable_routes(routes["reason_codes"][0])):
            _refuse()
    elif routes["state"] != "AVAILABLE" or routes != observed_routes(routes["capacity"]):
        _refuse()
    targets = value["targets"]
    _shape(targets, {"state", "reason_codes", "items", "scope", "coverage"})
    if (targets["scope"] != "ORIGINAL_EXECUTIVE_ROOT"
            or targets["coverage"] != "CURRENT_INSTALLED_SESSION_BRIDGE"
            or type(targets["items"]) is not list or len(targets["items"]) > MAX_TARGETS):
        _refuse()
    if targets["state"] == "UNAVAILABLE":
        if type(targets["reason_codes"]) is not list or len(targets["reason_codes"]) != 1 or targets != unavailable_targets(targets["reason_codes"][0]):
            _refuse()
    elif targets["state"] == "AVAILABLE":
        if targets["reason_codes"] != []:
            _refuse()
        refs = set()
        for target in targets["items"]:
            _shape(target, _TARGET_KEYS)
            for key in _TARGET_KEYS - {"addressable"}:
                _text(target[key], 512)
            if (target["kind"] not in {"fabric_attempt", "codex"}
                    or target["addressable"] is not True
                    or target["work_ref"] != expected_context["work_ref"]
                    or target["root_job_id"] != selected["root_job_id"]
                    or target["target_ref"] in refs):
                _refuse()
            refs.add(target["target_ref"])
    else:
        _refuse()
    encode(value)
    return copy.deepcopy(value)


def result(*, principal_context, capability_profile_digest, workspace_principal,
           selected_scope, mission_identity, plan_identity, mission_read, targets,
           original_execution=None):
    value = {"schema": RESULT_SCHEMA if original_execution is None else EXECUTION_RESULT_SCHEMA,
        "catalogue": CATALOGUE,
        "principal_context": copy.deepcopy(principal_context),
        "capability_profile_digest": capability_profile_digest,
        "workspace_principal": copy.deepcopy(workspace_principal), "scope": scope(selected_scope),
        "observation": {"mission_owner_sha256": mission_identity, "project_plan_sha256": plan_identity,
            "relationship": "SEPARATE_READS_WITH_BEFORE_AFTER_GUARDS", "currentness": "CURRENT_AT_ACQUISITION",
            "mission": copy.deepcopy(mission_read)},
        "relationships": {"state": "UNAVAILABLE", "reason": "company_not_composed", "newWorkAuthorized": False},
        "targets": copy.deepcopy(targets),
        "execution_routes": unavailable_routes(),
        "execution_authority": False, "native_origin_attested": False}
    if original_execution is not None:
        value["original_execution"] = copy.deepcopy(original_execution)
    return validate_result(value, expected_context=principal_context,
        capability_profile_digest=capability_profile_digest,
        expected_workspace_principal=workspace_principal, expected_scope=selected_scope)


def render(value):
    """Bounded evidence supplied by a qualified read port, not an authority."""
    value = validate_result(value, expected_context=value["principal_context"],
        capability_profile_digest=value["capability_profile_digest"],
        expected_workspace_principal=value["workspace_principal"])
    return ("Project help at this acquisition (read-only evidence). A reachable session is not "
            "a teammate relationship, available capacity, a placement grant or parent consumption. "
            "Revalidate through the original owner before contacting or dispatching.\n" + encode(value).decode("utf-8"))


def read_identity(value):
    """Stable delivered facts; original acquisition receipts remain in value.

    A fresh mission receipt and Company observation time may differ on repeated
    reads of unchanged owners. This comparison is valid only after each result
    has independently passed its existing authentication/currentness owners.
    """
    validate_result(value, expected_context=value["principal_context"],
        capability_profile_digest=value["capability_profile_digest"],
        expected_workspace_principal=value["workspace_principal"])
    stable = copy.deepcopy({key: val for key, val in value.items() if key != "observation"})
    if stable["relationships"]["state"] == "AVAILABLE":
        stable["relationships"].pop("observedAt")
    stable["project_plan_sha256"] = value["observation"]["project_plan_sha256"]
    stable["mission_read"] = value["observation"]["mission"]
    return digest(stable)
