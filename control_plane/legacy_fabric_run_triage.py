"""Read-only fleet view over the installed Fabric's per-run status contract.

This intentionally does not become Executive Job or provider status authority:
the incumbent fabric_task.py reports native observations. In particular a
terminal transport state never grants a retry, model switch, queue, or worker
transfer. Caller supplies exact run IDs from its original commission.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any
import re
import subprocess

_RUN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_ACTIONS = {
    "ACTIVE_OR_WAITING": "OBSERVE_INCUMBENT_CONTROLLER",
    "SETTLING": "AWAIT_CANONICAL_SETTLEMENT",
    "EFFECT_UNKNOWN": "RECONCILE_ORIGINAL_EFFECT",
    "STATUS_UNREADABLE": "RECONCILE_ORIGINAL_STATUS",
    "NOT_FOUND": "VERIFY_ORIGINAL_RUN_ID",
    "RESULT_UNAVAILABLE": "RECONCILE_RESULT_AVAILABILITY",
    "TERMINAL_FAILURE": "CLASSIFY_ORIGINAL_TERMINAL_FAILURE",
    "RECONCILED_PRESTART_FAILURE": "CLASSIFY_ORIGINAL_TERMINAL_FAILURE",
    "RECONCILED_PREEXEC_FAILURE": "CLASSIFY_ORIGINAL_TERMINAL_FAILURE",
}


def _validate_run_id(value: object) -> str:
    if type(value) is not str or not _RUN.fullmatch(value):
        raise ValueError("run ID must match the incumbent Fabric identifier")
    return value


def _result(run_id: str, action: str, *, state: str | None = None,
            accepted: bool = False) -> dict[str, Any]:
    return {
        "schema_version": "mastermind.legacy_fabric_run_triage/v1",
        "run_id": run_id,
        "observed_state": state,
        "next_action": action,
        "accepted": accepted,
        "authority_effect": "NONE",
        "retry_authorized": False,
        "model_switch_authorized": False,
        "queue_confirmed": False,
        "provider_quota_known": False,
        "provider_context_known": False,
        "return_consumed_by_parent": False,
    }


def project_legacy_fabric_run(value: object) -> dict[str, Any]:
    """Project only documented incumbent status fields without raw log strings."""
    if not isinstance(value, Mapping):
        return _result("", "RECONCILE_ORIGINAL_STATUS")
    run_id = value.get("run_id")
    if not isinstance(run_id, str) or _RUN.fullmatch(run_id) is None:
        return _result("", "RECONCILE_ORIGINAL_STATUS")
    if value.get("schema") != "mastermind.fabric_task_status.v1":
        return _result(run_id, "RECONCILE_ORIGINAL_STATUS")
    state = value.get("state")
    if type(state) is not str:
        return _result(run_id, "RECONCILE_ORIGINAL_STATUS")
    if state == "TERMINAL":
        if value.get("signal") == "effect_unknown":
            return _result(run_id, "RECONCILE_ORIGINAL_EFFECT", state=state)
        if (type(value.get("rc")) is int and value["rc"] == 0
                and value.get("signal") == "ok"):
            if value.get("result_available") is not True:
                return _result(run_id, "RECONCILE_RESULT_AVAILABILITY", state=state)
            if (value.get("accepted") is True
                    and value.get("acceptance_state") == "ACCEPTED"):
                return _result(run_id, "CONSUME_ACCEPTED_RETURN", state=state, accepted=True)
            return _result(run_id, "REVIEW_DELIVERED_RESULT", state=state)
        return _result(run_id, "CLASSIFY_ORIGINAL_TERMINAL_FAILURE", state=state)
    return _result(run_id, _ACTIONS.get(state, "RECONCILE_ORIGINAL_STATUS"), state=state)


def project_legacy_fleet(
    run_ids: Sequence[str], status_reader: Callable[[str], object],
) -> dict[str, Any]:
    """Read one prevalidated, bounded set. A failed read is *not* a dead run."""
    if (not isinstance(run_ids, (tuple, list)) or not 1 <= len(run_ids) <= 100):
        raise ValueError("provide 1..100 original run IDs")
    checked = [_validate_run_id(value) for value in run_ids]
    if len(set(checked)) != len(checked):
        raise ValueError("duplicate run ID")
    if not callable(status_reader):
        raise TypeError("status reader must be callable")
    outcomes = []
    for run_id in checked:
        try:
            status = status_reader(run_id)
            result = project_legacy_fabric_run(status)
            if result["run_id"] != run_id:
                result = _result(run_id, "RECONCILE_ORIGINAL_STATUS")
        except (OSError, TimeoutError, subprocess.TimeoutExpired, ValueError, RuntimeError):
            result = _result(run_id, "RECONCILE_ORIGINAL_STATUS")
        outcomes.append(result)
    counts = Counter(row["next_action"] for row in outcomes)
    return {
        "schema_version": "mastermind.legacy_fabric_fleet_triage/v1",
        "authority_effect": "NONE",
        "operation_performed": False,
        "run_count": len(outcomes),
        "runs": outcomes,
        "count_by_action": dict(sorted(counts.items())),
        "scope": "ORIGINAL_NATIVE_RUN_STATUS_ONLY",
        "executor_admission": "NOT_OBSERVED",
        "provider_pool_reallocation": "NOT_AUTHORIZED",
    }
