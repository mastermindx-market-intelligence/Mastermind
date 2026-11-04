"""A fixed READ shape, without a new principal, grant or mutation operation.

Integration must retain the incumbent Workspace permission and selected-source
brackets. Validating this frame alone authorizes no source acquisition.
"""
import hashlib
import re
from common.executive_workspace_contract import (
    FRAME_SCHEMA_V3, MAX_REQUEST_BYTES, canonical, validate_v3_frame, v3_selection,
    validate_available_plan_observation, bounded_canonical,
)

FRAME_SCHEMA = "mastermind.workspace_autonomy_read.v1"
BODY_SCHEMA = "mastermind.workspace_autonomy_read_result.v1"
OPERATION = "autonomy"
MAX_RESPONSE_BYTES = 32768
REASONS = frozenset({"SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "POLICY_MISMATCH", "OVER_BUDGET"})


def validate_frame(frame):
    if (type(frame) is not dict
            or set(frame) != {"schema", "operation", "selection", "principal"}
            or frame["schema"] != FRAME_SCHEMA or frame["operation"] != "autonomy"):
        raise ValueError("invalid_input")
    validate_v3_frame({**frame, "schema": FRAME_SCHEMA_V3, "operation": "admitted_plan"})
    if len(canonical(frame)) + 1 > MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    return frame


def unavailable(selected, reason):
    selected = v3_selection(selected)
    if reason not in REASONS:
        raise ValueError("invalid_input")
    return {"ok": True, "result": {
        "schema": BODY_SCHEMA, "selection": dict(selected),
        "availability": "UNAVAILABLE", "reason_codes": [reason],
        "source_observation": None, "policy": None,
    }}


def validate_body(value):
    """Fixed release guard; source policy ceilings are not an action grant."""
    if (type(value) is not dict or set(value) != {"schema", "selection", "availability",
            "reason_codes", "source_observation", "policy"} or value["schema"] != BODY_SCHEMA):
        raise ValueError("invalid_input")
    selected = v3_selection(value["selection"])
    if value["availability"] == "UNAVAILABLE":
        if (type(value["reason_codes"]) is not list or len(value["reason_codes"]) != 1
                or value["reason_codes"][0] not in REASONS
                or value["source_observation"] is not None or value["policy"] is not None):
            raise ValueError("invalid_input")
    elif value["availability"] == "AVAILABLE":
        if value["reason_codes"] != []:
            raise ValueError("invalid_input")
        validate_available_plan_observation(value["source_observation"], selected)
        policy = value["policy"]
        if (type(policy) is not dict or set(policy) != {"scope", "policy_sha", "source_sha256",
                "plan_digest", "reservation_digest", "limits"} or policy["scope"] != "ADMITTED_ROOT"
                or any(type(policy[k]) is not str or re.fullmatch(r"[0-9a-f]{64}", policy[k]) is None
                    for k in ("policy_sha", "source_sha256", "plan_digest", "reservation_digest"))):
            raise ValueError("invalid_input")
        limits = policy["limits"]
        keys = {"schema_version", "max_fan_out_per_parent", "max_depth", "max_repair_rounds",
                "max_review_attempts_per_job", "max_children_total", "max_attempts_per_orchestration_job",
                "review_job_attempt_limit", "allowed_child_cost_classes"}
        if (type(limits) is not dict or set(limits) != keys
                or any(type(limits[k]) is not int or not 0 <= limits[k] <= 1_000_000
                    for k in keys - {"allowed_child_cost_classes"})
                or limits["schema_version"] not in (1, 2)
                or type(limits["allowed_child_cost_classes"]) is not list
                or not 1 <= len(limits["allowed_child_cost_classes"]) <= 16
                or any(type(x) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", x) is None
                    for x in limits["allowed_child_cost_classes"])
                or len(set(limits["allowed_child_cost_classes"])) != len(limits["allowed_child_cost_classes"])
                or hashlib.sha256(canonical(limits)).hexdigest() != policy["policy_sha"]):
            raise ValueError("invalid_input")
    else:
        raise ValueError("invalid_input")
    bounded_canonical(value, limit=MAX_RESPONSE_BYTES - 1)
    return value
