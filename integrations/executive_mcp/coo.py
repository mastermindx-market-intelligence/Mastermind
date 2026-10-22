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

COO_SERVER_NAME = "mastermind-executive-coo"
COO_SERVER_VERSION = "1.0.0"
COO_MCP_PATH = "/mcp/coo"
COO_READ_NAMES = ("executive_state", "executive_inbox", "executive_fabric")
_WORK = {"type": "string", "pattern": "^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$", "maxLength": 72}


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
    "8d4ff58a30c02b717788b80fdfd1c5b8b35493dc11dd76cac351cde7b4509d72"
)


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
        expected = {"work_ref"} if name == "executive_mandate" else {"work_ref", "request_ref"}
        if set(arguments) != expected or not _check_work_ref(arguments.get("work_ref")):
            raise ValueError()
        if name == "principal_intent_status":
            principal_intent_id(arguments["request_ref"])
        return dict(arguments)
    except CooPrincipalRequestInternalError as exc:
        raise GatewayError("internal_error", "COO request policy is unavailable") from exc
    except (TypeError, ValueError) as exc:
        raise GatewayError("invalid_input", "invalid COO request or mission selector") from exc
