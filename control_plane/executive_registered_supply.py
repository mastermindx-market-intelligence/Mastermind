"""Registered quota supply for observability, never model placement.

The Executive Capacity and Model Router owners alone can admit an execution.
Registered pool state does not prove account quota, host readiness, model
equivalence, provider access, or shared-budget independence.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any
import sqlite3

_STATUSES = frozenset({"AVAILABLE", "BUSY", "RATE_LIMITED", "DRAINING", "OFFLINE", "ERROR"})
_MAX_CLASSES = 64


def _unbound() -> dict[str, Any]:
    return {
        "schema_version": "mastermind.registered_supply_observation/v1",
        "scope": "JOB_ALLOWLIST_REGISTRATIONS_ONLY",
        "authority_effect": "NONE",
        "can_reserve": False,
        "route_qualified": False,
        "independent_budget_proven": False,
        "shared_quota_verified": False,
        "telemetry_freshness_verified": False,
        "reset_eta": None,
        "registered_total": None,
        "registered_free_count": None,
        "state_counts": {},
        "next_action": "REQUIRE_CANONICAL_CAPACITY_SCOPE",
    }


def registered_supply_projection(
    connection: sqlite3.Connection, constraints: Mapping[str, Any] | object,
) -> dict[str, Any]:
    """Project only registered states of a Job's pre-existing quota allowlist.

    A free registration is NOT a qualified route and is never sufficient for
    dispatch. All quotas are counted, including stopped and BUSY registrations;
    provider/account/model secrets and IDs are deliberately not returned.
    """
    if not isinstance(constraints, Mapping):
        return _unbound()
    candidates = constraints.get("eligible_quota_classes")
    if (not isinstance(candidates, list) or not candidates
            or len(candidates) > _MAX_CLASSES
            or any(type(v) is not str or not v or v != v.strip()
                   or len(v) > 128 for v in candidates)
            or len(set(candidates)) != len(candidates)):
        return _unbound()

    marks = ",".join("?" for _ in candidates)
    observed = connection.execute(
        "SELECT q.status,q.held_attempt_id,w.identity_status "
        "FROM worker_quota_classes q JOIN workers w ON w.worker_id=q.worker_id "
        f"WHERE q.quota_class IN ({marks}) ORDER BY q.worker_id,q.quota_class",
        tuple(candidates),
    ).fetchall()
    states = Counter(str(row["status"]) for row in observed)
    unknown = any(key not in _STATUSES for key in states)
    free = sum(
        row["status"] == "AVAILABLE" and row["held_attempt_id"] is None
        and row["identity_status"] == "ONLINE"
        for row in observed
    )
    # No guessed routing entitlement or wake/ETA: only reflect local registry.
    result = _unbound()
    result.update(
        registered_total=len(observed),
        registered_free_count=int(free),
        state_counts=dict(sorted(states.items())),
        next_action=(
            "REQUIRE_CAPACITY_STATE_RECONCILIATION" if unknown else
            "REQUEST_EXISTING_PLACEMENT_REVALIDATION" if free else
            "WAIT_FOR_EXISTING_CAPACITY_OWNER"
        ),
    )
    return result
