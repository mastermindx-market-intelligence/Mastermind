"""Static three-tool service profile and exact result checks; no SDK or I/O."""
import copy
from collections.abc import Mapping

from control_plane import ceo_request
from control_plane.executive_inference_contract import TOOLS, intent_id, normalize_request, validate_result
from integrations.executive_mcp.schemas import ToolSpec
from integrations.executive_mcp.web_ceo import FABRIC_V2_TOOL_SPEC

MCP_PATH = "/mcp/service-inference"
_KEY = {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,95}$", "maxLength": 96}

def _object(properties):
    return {"type":"object", "additionalProperties":False, "required":list(properties), "properties":properties}

_RESULT_PROPERTIES = {key: copy.deepcopy(FABRIC_V2_TOOL_SPEC.input_schema["properties"][key])
                      for key in ("view", "root_job_id", "job_id", "attempt_id", "result_envelope_digest")}
_RESULT_PROPERTIES["view"] = {"const":"result"}
TOOL_SPECS = (
    ToolSpec(TOOLS[0], "Submit one bounded READ/RESEARCH service intent; acceptance is not execution. Reconcile uncertainty without resubmitting.",
        _object({"operation_key":_KEY, "objective":{"type":"string", "minLength":1, "maxLength":ceo_request.MAX_OBJECTIVE_CHARS}}), "Service admission or uncertainty", False),
    ToolSpec(TOOLS[1], "Reconcile the original operation key without submission or retry.",
        _object({"operation_key":_KEY}), "Original service receipt or refusal", True),
    ToolSpec(TOOLS[2], "Read only an exact canonical Fabric terminal result belonging to this service operation.",
        _object(dict(_RESULT_PROPERTIES, operation_key=_KEY)), "Canonical Fabric result or refusal", True),
)

def validate_arguments(name, value):
    if name == TOOLS[0]:
        return normalize_request(value)
    if not isinstance(value, Mapping) or "operation_key" not in value:
        raise ValueError("service operation identity required")
    intent_id(value["operation_key"])
    if name == TOOLS[1] and set(value) == {"operation_key"}:
        return dict(value)
    if name == TOOLS[2]:
        from integrations.executive_mcp.web_ceo import validate_web_ceo_v2_tool_arguments
        selection = {k: v for k, v in value.items() if k != "operation_key"}
        if selection.get("view") != "result":
            raise ValueError("only exact terminal result selection is exposed")
        return dict(validate_web_ceo_v2_tool_arguments(name, selection), operation_key=value["operation_key"])
    raise ValueError("unknown service tool or fields")
