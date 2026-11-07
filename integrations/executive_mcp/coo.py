"""Static COO tool contract; no SDK, authentication, state or installation."""
from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping

from common.executive_workspace_contract import _check_work_ref
from control_plane.coo_principal_request import (
    normalize_principal_request, principal_intent_id, CooPrincipalRequestInternalError,
)
from integrations.executive_mcp.schemas import (
    GatewayError,
    ToolSpec,
    canonical_json,
    tool_spec,
)
from integrations.executive_mcp.web_ceo import (
    validate_web_ceo_v2_tool_arguments, web_ceo_v2_tool_spec,
)
from integrations.hermes_delegate.schema import (
    COMMAND_RE, SELECTED_CHILD_ACTIONS, SubmissionError, parse_selected_child,
)

COO_SERVER_NAME = "mastermind-executive-coo"
COO_SERVER_VERSION = "1.0.0"
COO_MCP_PATH = "/mcp/coo"
COO_READ_NAMES = ("executive_state", "executive_inbox", "executive_fabric")
_WORK = {"type": "string", "pattern": "^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$", "maxLength": 72}
#: The canonical coo-cycle dispatch command the host already froze.
_SELECTED_CHILD_COMMAND = {
    "type": "string", "pattern": COMMAND_RE.pattern, "maxLength": 294,
}


def _submit_spec():
    original = tool_spec("submit_ceo_intent")
    shape = copy.deepcopy(original.input_schema)
    shape["required"] = list(shape["required"]) + ["workstream"]
    shape["properties"]["workstream"] = dict(_WORK)
    shape["properties"]["attempt_limit"]["maximum"] = 2
    return ToolSpec("submit_principal_intent", "Submit one bounded in-mission COO request. Acceptance is not execution; reconcile an uncertain result by its original request reference.", shape, "Role-neutral durable principal receipt or explicit uncertainty.", False)


COO_TOOL_SPECS = (
    ToolSpec("executive_mandate", "Read the current owner-qualified mandate for one assigned mission. The projection grants no authority.",
             {"type": "object", "additionalProperties": False, "required": ["work_ref"], "properties": {"work_ref": dict(_WORK)}}, "Current mandate with explicit degradation.", True),
    *(copy.deepcopy(web_ceo_v2_tool_spec(name)) for name in COO_READ_NAMES),
    _submit_spec(),
    ToolSpec("principal_intent_status", "Reconcile one prior COO request without creating or retrying work.",
             {"type": "object", "additionalProperties": False, "required": ["request_ref", "work_ref"], "properties": {
                 "work_ref": dict(_WORK), "request_ref": {"type": "string", "pattern": "^req-coo-[0-9a-f]{32}$", "maxLength": 40}}}, "Original role-neutral receipt or explicit refusal.", True),
    ToolSpec("mmx_delegate", "Submit or observe exactly the Executive child the authenticated host already froze, under its canonical command reference. The model cannot select, create, review, consume or cancel a child.",
             {"type": "object", "additionalProperties": False, "required": ["action", "command"], "properties": {
                 "action": {"type": "string", "enum": sorted(SELECTED_CHILD_ACTIONS)},
                 "command": dict(_SELECTED_CHILD_COMMAND)}},
             "Current selected-child envelope for the exact original command, with its canonical Attempt and three-valued live submit.", False),
)
COO_TOOL_NAMES = tuple(spec.name for spec in COO_TOOL_SPECS)


def coo_tool_schema_snapshot():
    """Return the exact authority-bearing COO tools/list projection.

    Descriptions/output prose are deliberately excluded, matching
    observed_mcp_tool_schema_digest: tool names, input schemas, output schemas
    and security annotations are the capability-bearing fields.
    """

    return [
        {
            "annotations": copy.deepcopy(spec.annotations),
            "input_schema": copy.deepcopy(spec.input_schema),
            "name": spec.name,
            "output_schema": None,
        }
        for spec in sorted(COO_TOOL_SPECS, key=lambda item: item.name)
    ]


def coo_tool_schema_digest():
    return hashlib.sha256(canonical_json(coo_tool_schema_snapshot())).hexdigest()


COO_TOOL_SCHEMA_DIGEST = (
    "5cf2a0de4a47686c545d1ee3d9c388ab4dc94c880cb0670140de2eca2e54f550"
)

# A separate reviewed catalogue. Existing descriptors and the v1 digest above
# retain their exact meaning for every currently enrolled principal.
from common import coo_agentos_context_contract as context_wire

COO_CONTEXT_TOOL_SPECS = (*COO_TOOL_SPECS, ToolSpec(context_wire.TOOL,
    "Read the complete canonical Agent OS context for one explicitly enrolled mission from its adopted snapshot. This read grants no execution authority.",
    {"type": "object", "additionalProperties": False, "required": ["work_ref"],
     "properties": {"work_ref": dict(_WORK)}},
    "Exact adopted context bytes and source/runtime receipt, with explicit degradation and omission accounting.", True))
COO_CONTEXT_TOOL_NAMES = tuple(spec.name for spec in COO_CONTEXT_TOOL_SPECS)
COO_CONTEXT_TOOL_SCHEMA_DIGEST = "5fa24aa1d907d66d0ca0a56168617f955e09d063f532cf527fe0d7b923fb50af"
COO_CURRENT_CONTEXT_TOOL_SPECS = (*COO_TOOL_SPECS, ToolSpec(context_wire.CURRENT_TOOL,
    "Read current canonical Agent OS context for an enrolled mission using independently authenticated Executive and Workspace resources. This read grants no execution authority.",
    {"type": "object", "additionalProperties": False, "required": ["work_ref"],
     "properties": {"work_ref": dict(_WORK)}},
    "Exact current DATA context with pinned CODE, original publication and source/runtime evidence.", True))
COO_CURRENT_CONTEXT_TOOL_NAMES = tuple(spec.name for spec in COO_CURRENT_CONTEXT_TOOL_SPECS)


def coo_context_tool_schema_snapshot():
    return [{"annotations": copy.deepcopy(spec.annotations), "input_schema": copy.deepcopy(spec.input_schema),
             "name": spec.name, "output_schema": None}
            for spec in sorted(COO_CONTEXT_TOOL_SPECS, key=lambda item: item.name)]


def coo_context_tool_schema_digest():
    return hashlib.sha256(canonical_json(coo_context_tool_schema_snapshot())).hexdigest()


def coo_current_context_tool_schema_digest():
    snapshot = [{"annotations": copy.deepcopy(spec.annotations), "input_schema": copy.deepcopy(spec.input_schema),
                 "name": spec.name, "output_schema": None}
                for spec in sorted(COO_CURRENT_CONTEXT_TOOL_SPECS, key=lambda item: item.name)]
    return hashlib.sha256(canonical_json(snapshot)).hexdigest()


def catalogue_specs(catalogue):
    if catalogue == context_wire.LEGACY_CATALOGUE: return COO_TOOL_SPECS
    if catalogue == context_wire.CATALOGUE: return COO_CONTEXT_TOOL_SPECS
    if catalogue == context_wire.CURRENT_CATALOGUE: return COO_CURRENT_CONTEXT_TOOL_SPECS
    raise GatewayError("invalid_input", "unknown COO catalogue")


def validate_coo_context_tool_arguments(name, arguments):
    if name not in {context_wire.TOOL, context_wire.CURRENT_TOOL}:
        return validate_coo_tool_arguments(name, arguments)
    try:
        from common.workspace_project_plan_contract import validate_selection
        if type(arguments) is not dict or set(arguments) != {"work_ref"} or not _check_work_ref(arguments["work_ref"]):
            raise ValueError()
        validate_selection(arguments)
        return dict(arguments)
    except (ValueError, TypeError):
        raise GatewayError("invalid_input", "invalid COO context selector") from None


def validate_coo_tool_arguments(name, arguments):
    if name not in COO_TOOL_NAMES:
        raise GatewayError("invalid_input", "unknown COO tool")
    if name in COO_READ_NAMES:
        return validate_web_ceo_v2_tool_arguments(name, arguments)
    if not isinstance(arguments, Mapping):
        raise GatewayError("invalid_input", "COO arguments must be an object")
    try:
        if name == "submit_principal_intent":
            return normalize_principal_request(arguments, expected_work_ref=arguments.get("workstream"))
        if name == "mmx_delegate":
            # The closed selected-child branch: the action and the exact
            # canonical command the host already froze. Nothing else.
            return parse_selected_child(arguments)
        expected = {"work_ref"} if name == "executive_mandate" else {"work_ref", "request_ref"}
        if set(arguments) != expected or not _check_work_ref(arguments.get("work_ref")):
            raise ValueError()
        if name == "principal_intent_status":
            principal_intent_id(arguments["request_ref"])
        return dict(arguments)
    except CooPrincipalRequestInternalError as exc:
        raise GatewayError("internal_error", "COO request policy is unavailable") from exc
    except SubmissionError as exc:
        raise GatewayError("invalid_input", "invalid selected-child request") from exc
    except (TypeError, ValueError) as exc:
        raise GatewayError("invalid_input", "invalid COO request or mission selector") from exc
