"""Read-only composition and advice over the incumbent ExecutionPlan contract.

This is a planner consumer, never admission, authentication, routing or a scheduler.
Templates only add dependency edges. Identity, scopes, review and grants are copied
unchanged. Runtime must still validate and admit the actual sealed planner result.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from control_plane.executive_coo_policy import CooCyclePolicy, CooCyclePolicyError
from control_plane.executive_orchestration_result import (
    PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5,
    _identifier, _validate_plan, canonical_bytes, canonical_digest,
    MAX_CANONICAL_RESULT_BYTES,
)
from scripts.ohf.redaction import evidence_contains_secret, redact_evidence


METHODS = {
    "direct": "One cohesive executor; retain its required independent review.",
    "pipeline": "Ordered work with each step depending on its predecessor.",
    "fanout_join": "Independent leaves followed by a caller-supplied integration step.",
    "hierarchical": "Existing v5 coordinators with explicit inherited allowances.",
    "custom": "Preserve an orchestrator-authored DAG under the same contract.",
}
_DEPENDENCY_SCHEMAS = {PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5}


class GraphPlanningError(ValueError):
    """Invalid planning request, not a runtime or provider refusal."""


def _validated(plan: Any, root: str, attempt: str) -> dict[str, Any]:
    # Reuse the sole plan-shape owner rather than maintaining a competing schema.
    # A synthetic COMPLETED envelope would misrepresent a prospective candidate.
    _identifier(root, name="expected_root_job_id")
    _identifier(attempt, name="expected_plan_attempt_id")
    if len(canonical_bytes(plan)) > MAX_CANONICAL_RESULT_BYTES:
        raise GraphPlanningError("candidate exceeds incumbent byte limit")
    result = _validate_plan(plan, outer={
        "run_id": attempt, "expected_root_job_id": root,
    })
    if evidence_contains_secret(result) or redact_evidence(result) != result:
        raise GraphPlanningError("candidate contains redaction-triggering material")
    return result


def compose_plan(plan: Mapping[str, Any], *, expected_root_job_id: str,
                 expected_plan_attempt_id: str, method: str = "custom") -> dict[str, Any]:
    """Return an ordinary ExecutionPlan; never invent identities or remove edges."""
    if method not in METHODS:
        raise GraphPlanningError("unknown graph method")
    candidate = copy.deepcopy(_validated(plan, expected_root_job_id, expected_plan_attempt_id))
    steps = candidate["steps"]
    has_coordinator = any(step.get("delegation") is not None for step in steps)
    if method == "direct" and (len(steps) != 1 or has_coordinator):
        raise GraphPlanningError("direct requires exactly one non-delegating step")
    if method == "hierarchical" and (
        candidate["schema_version"] != PLAN_SCHEMA_V5 or not has_coordinator
    ):
        raise GraphPlanningError("hierarchical requires an explicit v5 coordinator")
    if method in {"pipeline", "fanout_join"}:
        if candidate["schema_version"] not in _DEPENDENCY_SCHEMAS:
            raise GraphPlanningError("method requires a dependency-carrying plan version")
        if method == "pipeline":
            for index, step in enumerate(steps[1:], 1):
                dependencies = set(step["prerequisite_step_ids"])
                dependencies.add(steps[index - 1]["step_id"])
                step["prerequisite_step_ids"] = [
                    prior["step_id"] for prior in steps[:index]
                    if prior["step_id"] in dependencies
                ]
        else:
            if len(steps) < 3 or has_coordinator:
                raise GraphPlanningError("fanout_join requires at least two leaves and one integration step")
            if any(step["prerequisite_step_ids"] for step in steps[:-1]):
                raise GraphPlanningError("fanout_join cannot erase existing leaf dependencies")
            steps[-1]["prerequisite_step_ids"] = [step["step_id"] for step in steps[:-1]]
    return _validated(candidate, expected_root_job_id, expected_plan_attempt_id)


def _dependency_facts(steps: list[dict[str, Any]]) -> tuple[dict[str, set[str]], list[list[str]], int]:
    ancestors: dict[str, set[str]] = {}
    levels: dict[str, int] = {}
    for step in steps:
        identity = step["step_id"]
        prerequisites = step.get("prerequisite_step_ids", [])
        ancestors[identity] = set(prerequisites)
        for prerequisite in prerequisites:
            ancestors[identity].update(ancestors[prerequisite])
        levels[identity] = 1 + max((levels[p] for p in prerequisites), default=0)
    layers = [[identity for identity, level in levels.items() if level == n]
              for n in range(1, max(levels.values()) + 1)]
    # Dilworth: maximum antichain = vertices - maximum matching in the
    # transitive dependency relation. Layer width alone can underestimate it.
    matched: dict[str, str] = {}

    def augment(left: str, seen: set[str]) -> bool:
        for right in ancestors:
            if left not in ancestors[right] or right in seen:
                continue
            seen.add(right)
            if right not in matched or augment(matched[right], seen):
                matched[right] = left
                return True
        return False

    matches = sum(augment(identity, set()) for identity in ancestors)
    return ancestors, layers, len(steps) - matches


def _static_prefix(path: str) -> tuple[str, ...]:
    result = []
    for component in path.split("/"):
        if any(char in component for char in "*?["):
            break
        result.append(component)
    return tuple(result)


def _may_overlap(left: str, right: str) -> bool:
    # Deliberately conservative for globs/subtrees; this is a custody warning,
    # not a replacement for the runtime's actual path/permission validator.
    a, b = _static_prefix(left), _static_prefix(right)
    length = min(len(a), len(b))
    return a[:length] == b[:length]


def analyze_plan(plan: Mapping[str, Any], *, expected_root_job_id: str,
                 expected_plan_attempt_id: str, method: str = "custom",
                 policy_path: str | None = None, coordinator_depth: int | None = None,
                 descendant_limit: int | None = None, max_depth: int | None = None) -> dict[str, Any]:
    """Static candidate analysis; caller-supplied limits are never an issued grant."""
    candidate = compose_plan(plan, expected_root_job_id=expected_root_job_id,
                             expected_plan_attempt_id=expected_plan_attempt_id, method=method)
    hierarchical = candidate["schema_version"] == PLAN_SCHEMA_V5
    policy = CooCyclePolicy.load(policy_path, version=2 if hierarchical else 1)
    nested = hierarchical and candidate["coordinator_job_id"] != candidate["root_job_id"]
    if nested and any(value is None for value in (coordinator_depth, descendant_limit, max_depth)):
        raise GraphPlanningError("nested plan requires all three declared inherited bounds")
    depth = 0 if coordinator_depth is None else coordinator_depth
    limit = policy.max_children_total if descendant_limit is None else descendant_limit
    ceiling = policy.max_depth if max_depth is None else max_depth
    if any(type(value) is not int for value in (depth, limit, ceiling)):
        raise GraphPlanningError("declared bounds must be integers")
    if (not 0 <= depth < ceiling <= policy.max_depth
            or not 1 <= limit <= policy.max_children_total
            or (not nested and depth != 0) or (nested and depth == 0)):
        raise GraphPlanningError("declared bounds conflict with the plan or policy")

    steps = candidate["steps"]
    breakdown = [{"kind": "planner", "reserved_descendants": 1}]
    for step in steps:
        delegation = step.get("delegation")
        slots = (1 + delegation["descendant_limit"] if delegation is not None
                 else policy.reserved_step_slots(review_required=step["review_required"]))
        breakdown.append({"step_id": step["step_id"],
                          "kind": "coordinator_subtree" if delegation else "work_review_repair",
                          "reserved_descendants": slots})
    demand = sum(item["reserved_descendants"] for item in breakdown)
    reservation_error = None
    try:
        if hierarchical:
            reserved = policy.reserved_hierarchy_children(tuple(steps), coordinator_depth=depth,
                                                          descendant_limit=limit, max_depth=ceiling)
        else:
            reserved = policy.reserved_children_total(tuple(step["review_required"] for step in steps))
        if reserved != demand:
            raise GraphPlanningError("reservation breakdown disagrees with canonical policy")
        if reserved > limit:
            raise CooCyclePolicyError("plan capacity exceeds declared tighter descendant limit")
    except CooCyclePolicyError as exc:
        reservation_error = str(exc)

    ancestors, layers, width = _dependency_facts(steps)
    findings = []
    for index, left in enumerate(steps):
        for right in steps[index + 1:]:
            if left["step_id"] in ancestors[right["step_id"]]:
                continue
            overlaps = [(a, b) for a in left["allowed_write_paths"]
                        for b in right["allowed_write_paths"] if _may_overlap(a, b)]
            if overlaps:
                findings.append({"code": "UNORDERED_WRITE_SCOPE_MAY_OVERLAP",
                                 "step_ids": [left["step_id"], right["step_id"]],
                                 "scope_pair_count": len(overlaps)})
    if reservation_error:
        findings.append({"code": "DECLARED_POLICY_INCOMPATIBLE", "detail": reservation_error})
    prerequisites = {p for step in steps for p in step.get("prerequisite_step_ids", [])}
    return {
        "schema": "mastermind.fabric_graph_advice.v1",
        "method": method, "candidate_plan": candidate,
        "candidate_plan_digest": canonical_digest(candidate),
        "contract_status": "VALID", "static_status": "NEEDS_ATTENTION" if findings else "COMPATIBLE",
        "admission_state": "NOT_REQUESTED", "runtime_changed": False,
        "declared_bounds_authenticated": False,
        "integration_contract_semantics": "NOT_EVALUATED",
        "policy_sha256": policy.policy_sha256,
        "policy_selection": "prospective candidate schema; not authenticated admitted-root policy",
        "policy_source_sha256": policy.source_sha256,
        "reservation": {"demand": demand, "limit": limit,
                        "shortfall": max(0, demand - limit), "capacity_fits": demand <= limit,
                        "policy_compatible": reservation_error is None,
                        "breakdown": breakdown},
        "dependency_layers": layers, "dependency_depth": len(layers),
        "dependency_width": width, "declared_coordinator_depth": depth,
        "dependency_scope": "current candidate steps; coordinator subplans are unexpanded",
        "declared_max_runtime_depth": ceiling,
        "terminal_step_ids": [s["step_id"] for s in steps if s["step_id"] not in prerequisites],
        "findings": findings,
        "checks_not_performed": ["runtime_admission", "live_capacity", "root_effect_reconciliation",
                                 "source_custody", "reviewer_independence", "product_acceptance",
                                 "provider_eligibility", "token_or_money_budget_admission"],
        "guidance": [
            "Dependency width is potential parallelism, not available or admitted concurrency.",
            "Reservations include possible review/repair descendants, not predicted worker usage.",
            "Reservation demand is a capacity bound, not a token, money or economic-efficiency estimate.",
            "Sequential execution does not refund cumulative descendant reservations.",
            "Dependency edges do not prove the join carries the original integration and acceptance obligations.",
            "Never remove required review, reset roots or widen grants to make a graph fit.",
        ],
    }
