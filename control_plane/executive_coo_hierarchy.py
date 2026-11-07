"""Pure bounded-tree checks used by the existing Executive Runtime.

No store, dispatcher, lease, provider selection, or lifecycle is defined here.
Callers supply rows from their current Runtime transaction.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.executive_coo_policy import CooCyclePolicy, HIERARCHY_POLICY_SHA256


class HierarchyError(ValueError):
    pass


def validate_grant(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "policy_sha256", "descendant_limit", "max_depth"
    }:
        raise HierarchyError("hierarchy grant is not the closed wire")
    if value["policy_sha256"] != HIERARCHY_POLICY_SHA256:
        raise HierarchyError("hierarchy grant policy is not v2")
    if (type(value["descendant_limit"]) is not int
            or not 2 <= value["descendant_limit"] <= 16
            or type(value["max_depth"]) is not int
            or not 1 <= value["max_depth"] <= 3):
        raise HierarchyError("hierarchy grant bounds are invalid")
    return dict(value)


def inherited_grant(parent_depth: int, parent_grant: Mapping[str, Any],
                    delegation: Mapping[str, Any]) -> dict[str, Any]:
    """Construct a coordinator's immutable grant after plan reservation."""
    parent = validate_grant(parent_grant)
    if (type(parent_depth) is not int or not 0 <= parent_depth < 3
            or not isinstance(delegation, Mapping)
            or set(delegation) != {"descendant_limit", "max_depth"}):
        raise HierarchyError("invalid coordinator delegation")
    child = validate_grant({"policy_sha256": parent["policy_sha256"], **delegation})
    if (child["descendant_limit"] >= parent["descendant_limit"]
            or not parent_depth + 1 < child["max_depth"] <= parent["max_depth"]):
        raise HierarchyError("coordinator grant widens its ancestor")
    return child


def root_grant() -> dict[str, Any]:
    policy = CooCyclePolicy.load(version=2)
    return {"policy_sha256": policy.policy_sha256,
            "descendant_limit": policy.max_children_total,
            "max_depth": policy.max_depth}


def validate_tree(rows: Sequence[Mapping[str, Any]], original_root_id: str) -> dict[str, Mapping[str, Any]]:
    """Validate one whole bounded root, including retained terminal descendants."""
    if len(rows) > 17:
        raise HierarchyError("original root descendant allowance exceeded")
    jobs = {str(row["job_id"]): row for row in rows}
    if len(jobs) != len(rows) or original_root_id not in jobs:
        raise HierarchyError("missing root or duplicate job identity")
    root = jobs[original_root_id]
    if (root["parent_job_id"] is not None or root["root_job_id"] != original_root_id
            or root["depth"] != 0):
        raise HierarchyError("original root identity invalid")
    for job_id, row in jobs.items():
        if row["root_job_id"] != original_root_id:
            raise HierarchyError("job changes original root")
        if job_id == original_root_id:
            continue
        if type(row["depth"]) is not int or not 1 <= row["depth"] <= 3:
            raise HierarchyError("job depth exceeds original root")
        parent = jobs.get(str(row["parent_job_id"]))
        if parent is None or parent["depth"] + 1 != row["depth"]:
            raise HierarchyError("job ancestry is missing or cyclic")
        if parent["orchestration_role"] != "aggregation":
            raise HierarchyError("leaf job cannot own descendants")
    return jobs


def ancestors(jobs: Mapping[str, Mapping[str, Any]], job_id: str) -> list[Mapping[str, Any]]:
    if job_id not in jobs:
        raise HierarchyError("coordinator does not exist")
    result, seen = [], set()
    current: str | None = job_id
    while current is not None:
        if current in seen or current not in jobs or len(seen) > 3:
            raise HierarchyError("invalid coordinator ancestry")
        seen.add(current)
        row = jobs[current]
        result.append(row)
        current = row["parent_job_id"]
    return result


def assert_admission_open(jobs: Mapping[str, Mapping[str, Any]], coordinator_id: str) -> None:
    """Run inside the same transaction as reservation/Job creation."""
    for row in ancestors(jobs, coordinator_id):
        if (row["orchestration_role"] != "aggregation" or row["status"] != "QUEUED"
                or row["cancel_requested_at_ms"] is not None
                or row["current_attempt_id"] is not None or row["attempt_count"] != 0):
            raise HierarchyError("coordinator or ancestor closed to new work")


def descendant_ids(jobs: Mapping[str, Mapping[str, Any]], coordinator_id: str) -> set[str]:
    if coordinator_id not in jobs:
        raise HierarchyError("coordinator does not exist")
    return {job_id for job_id in jobs if job_id != coordinator_id
            and any(row["job_id"] == coordinator_id for row in ancestors(jobs, job_id)[1:])}


def assert_creation_capacity(jobs: Mapping[str, Mapping[str, Any]], coordinator_id: str,
                             grants: Mapping[str, Mapping[str, Any]]) -> None:
    """Every materialized Job charges every ancestor; terminal Jobs stay charged.

    Up-front plan reservations additionally partition each coordinator allowance.
    This check is the final transaction-local bound, never a replacement for the
    immutable plan reservation.
    """
    assert_admission_open(jobs, coordinator_id)
    if jobs[coordinator_id]["depth"] + 1 > 3:
        raise HierarchyError("new child exceeds maximum depth")
    for row in ancestors(jobs, coordinator_id):
        grant = validate_grant(grants.get(row["job_id"]))
        if jobs[coordinator_id]["depth"] + 1 > grant["max_depth"]:
            raise HierarchyError("new child exceeds ancestor depth grant")
        if len(descendant_ids(jobs, row["job_id"])) + 1 > grant["descendant_limit"]:
            raise HierarchyError("new child exceeds ancestor descendant allowance")
