"""control_plane.work_queue_projection — read-only workspace work-queue view.

PURE compositor over the Executive root-list (``mastermind.fabric_job_root_list.v2``).
Encodes the eight binding truth rules (R1-R8) from the parent ruling 5805095742
and the design freeze (Figma 138:8).  Never infers lifecycle, ownership,
capacity, or acceptance from anything except its named inputs.

Top-level document key set is closed; per-row keys are closed; the
group list is closed and ordered.  Composing twice from the same inputs
yields byte-identical canonical JSON.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from control_plane.executive_runtime import JobStatus

WORK_QUEUE_SCHEMA = "mastermind.workspace_work_queue.v1"
_ROOT_LIST_SCHEMA = "mastermind.fabric_job_root_list.v2"
_AUTONOMY_SCHEMA = "mastermind.autonomy_control_room.v1"

#: Closed group list and its deterministic ordering.
_GROUP_ORDER: tuple[str, ...] = (
    "EFFECT_EXCEPTION",
    "NEEDS_SOL",
    "NEEDS_WORKER",
    "WAITING_CAPACITY",
    "RUNNING",
    "QUEUED",
    "COMPLETED_NOT_ACCEPTED",
    "TERMINAL",
    "UNKNOWN",
)
_GROUP_SET = frozenset(_GROUP_ORDER)

#: Job lifecycle pre-START set (R3, R8).
_PRE_START_STATUSES = frozenset({"QUEUED"})

#: Closed top-level document key set.
OUTPUT_KEYS: frozenset[str] = frozenset({
    "schema",
    "generated_at",
    "availability",
    "lifecycle_source",
    "effect_exception",
    "coverage",
    "groups",
    "source_observation",
    "reason_codes",
})

#: Closed coverage envelope keys.
COVERAGE_KEYS: frozenset[str] = frozenset({"count", "total", "truncated", "completeness"})

#: lifecycle_source shape — top keys and runtime echo keys (verbatim copy).
_LIFECYCLE_SOURCE_TOP_KEYS: frozenset[str] = frozenset({"schema", "runtime"})
_RUNTIME_ECHO_KEYS: frozenset[str] = frozenset({
    "root",
    "db_present",
    "identity",
    "acquisition",
})

#: Closed per-row key set.
ROW_KEYS: frozenset[str] = frozenset({
    "root_job_id",
    "lifecycle",
    "next_actor",
    "capacity",
    "effect",
    "acceptance",
    "group",
})

#: Closed lifecycle column keys.
_LIFECYCLE_KEYS: frozenset[str] = frozenset({
    "status",
    "source",
    "orchestration_role",
    "depth",
})

#: Closed next_actor / capacity / effect column keys.
_NEXT_ACTOR_KEYS: frozenset[str] = frozenset({"value", "source", "reason"})
_CAPACITY_KEYS: frozenset[str] = frozenset({"value", "source", "reason"})
_EFFECT_KEYS: frozenset[str] = frozenset({"value", "source", "reason"})

#: Closed acceptance column keys (mirrors fabric_job_view._acceptance_v2).
ACCEPTANCE_KEYS: frozenset[str] = frozenset({"state", "producer_owner", "reason"})

#: Closed queue-level effect_exception keys.
QUEUE_EFFECT_EXCEPTION_KEYS: frozenset[str] = frozenset({"value", "scope", "observable"})

#: Root-list shape mirrors ``fabric_job_view.ROOT_LIST_KEYS``.
_ROOT_LIST_KEYS: frozenset[str] = frozenset({
    "schema",
    "generated_at",
    "runtime",
    "roots",
    "count",
    "total",
    "truncated",
    "degraded",
})
_ROOT_LIST_RUNTIME_KEYS: frozenset[str] = frozenset({
    "root",
    "db_present",
    "identity",
    "acquisition",
})
_ROOT_ROW_KEYS: frozenset[str] = frozenset({
    "job_id",
    "status",
    "depth",
    "parent_job_id",
    "orchestration_role",
})

#: Closed ``lifecycle_source.runtime.acquisition`` keys; verbatim echo.
_ACQUISITION_KEYS: frozenset[str] = frozenset({
    "schema",
    "query",
    "owner",
    "snapshot_digest",
    "budgets",
    "truncation",
    "provenance",
    "generation",
})

#: Closed lifecycle→group table over the Executive JobStatus enum (R8).
#: Every enum member is mapped explicitly — no default branch swallows a new member.
_JOB_STATUS_GROUPS: dict[str, str] = {
    JobStatus.QUEUED.value: "QUEUED",
    JobStatus.RUNNING.value: "RUNNING",
    JobStatus.CHECKPOINTED.value: "RUNNING",
    JobStatus.RATE_LIMITED.value: "RUNNING",
    JobStatus.CANCEL_REQUESTED.value: "RUNNING",
    JobStatus.COMPLETED.value: "COMPLETED_NOT_ACCEPTED",
    JobStatus.FAILED.value: "TERMINAL",
    JobStatus.LOST.value: "TERMINAL",
    JobStatus.CANCELLED.value: "TERMINAL",
}

_REASON_LIFECYCLE_UNAVAILABLE = "LIFECYCLE_UNAVAILABLE"
_BOUNDED_UNAVAILABLE_PHRASE = "bounded acquisition unavailable"


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_root_list(root_list: Any) -> Mapping[str, Any]:
    """Strict shape validation; raise ValueError on anything else."""
    if not isinstance(root_list, Mapping):
        raise ValueError("root_list must be a mapping")
    if root_list.get("schema") != _ROOT_LIST_SCHEMA:
        raise ValueError(
            f"root_list schema must equal {_ROOT_LIST_SCHEMA!r}, got {root_list.get('schema')!r}"
        )
    if set(root_list) != _ROOT_LIST_KEYS:
        raise ValueError(
            f"root_list keys must equal {sorted(_ROOT_LIST_KEYS)}, got {sorted(root_list)}"
        )
    runtime = root_list.get("runtime")
    if not isinstance(runtime, Mapping) or set(runtime) != _ROOT_LIST_RUNTIME_KEYS:
        raise ValueError("root_list runtime envelope malformed")
    acquisition = runtime.get("acquisition")
    if not isinstance(acquisition, Mapping) or set(acquisition) != _ACQUISITION_KEYS:
        raise ValueError("root_list runtime.acquisition envelope malformed")
    roots = root_list.get("roots")
    if not isinstance(roots, list):
        raise ValueError("root_list roots must be a list")
    for row in roots:
        if not isinstance(row, Mapping) or set(row) != _ROOT_ROW_KEYS:
            raise ValueError(f"root row keys invalid: {row!r}")
        if not isinstance(row["job_id"], str) or not row["job_id"]:
            raise ValueError(f"root row job_id invalid: {row!r}")
        if not isinstance(row["status"], str) or not row["status"]:
            raise ValueError(f"root row status invalid: {row!r}")
        if not isinstance(row["depth"], int) or row["depth"] < 0:
            raise ValueError(f"root row depth invalid: {row!r}")
    count, total, truncated, degraded = (
        root_list.get("count"),
        root_list.get("total"),
        root_list.get("truncated"),
        root_list.get("degraded"),
    )
    if not isinstance(count, int) or count < 0:
        raise ValueError("root_list count invalid")
    if total is not None and (not isinstance(total, int) or total < 0):
        raise ValueError("root_list total invalid")
    if not isinstance(truncated, bool):
        raise ValueError("root_list truncated invalid")
    if not isinstance(degraded, list) or not all(isinstance(d, str) for d in degraded):
        raise ValueError("root_list degraded invalid")
    return root_list


def _validate_accountability(value: Any) -> Mapping[str, Mapping[str, Any]] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("accountability must be a mapping or None")
    for ref, row in value.items():
        if not isinstance(ref, str) or not ref:
            raise ValueError("accountability key invalid")
        if not isinstance(row, Mapping):
            raise ValueError("accountability row must be a mapping")
        if set(row) != {"next_actor", "evidence_ref", "observed_at"}:
            raise ValueError("accountability row keys invalid")
        if row["next_actor"] not in ("SOL", "WORKER"):
            raise ValueError(f"accountability next_actor invalid: {row['next_actor']!r}")
        for str_key in ("evidence_ref", "observed_at"):
            if not isinstance(row[str_key], str) or not row[str_key]:
                raise ValueError(f"accountability row {str_key} invalid")
    return value


def _validate_placement(value: Any) -> Mapping[str, Mapping[str, Any]] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("placement must be a mapping or None")
    for ref, row in value.items():
        if not isinstance(ref, str) or not ref:
            raise ValueError("placement key invalid")
        if not isinstance(row, Mapping):
            raise ValueError("placement row must be a mapping")
        if set(row) != {"state", "evidence_ref", "observed_at"}:
            raise ValueError("placement row keys invalid")
        if row["state"] != "WAITING":
            raise ValueError(f"placement row state invalid: {row['state']!r}")
        for str_key in ("evidence_ref", "observed_at"):
            if not isinstance(row[str_key], str) or not row[str_key]:
                raise ValueError(f"placement row {str_key} invalid")
    return value


def _validate_effects(value: Any) -> Mapping[str, Mapping[str, Any]] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("effects must be a mapping or None")
    for ref, row in value.items():
        if not isinstance(ref, str) or not ref:
            raise ValueError("effects key invalid")
        if not isinstance(row, Mapping):
            raise ValueError("effects row must be a mapping")
        if set(row) != {"state", "carrier"}:
            raise ValueError("effects row keys invalid")
        if row["state"] not in ("EFFECT_UNKNOWN", "NONE"):
            raise ValueError(f"effects row state invalid: {row['state']!r}")
        if not isinstance(row["carrier"], str) or not row["carrier"]:
            raise ValueError("effects row carrier invalid")
    return value


def _lifecycle_unavailable(root_list: Mapping[str, Any]) -> bool:
    """R1: refuse lifecycle when the Runtime is degraded or absent."""
    runtime = root_list["runtime"]
    if runtime.get("db_present") is not True:
        return True
    acquisition = runtime["acquisition"]
    generation = acquisition.get("generation")
    state = generation.get("state") if isinstance(generation, Mapping) else None
    if state != "SAME":
        return True
    degraded = root_list.get("degraded") or []
    for entry in degraded:
        if isinstance(entry, str) and _BOUNDED_UNAVAILABLE_PHRASE in entry:
            return True
    return False


def _lifecycle_source(root_list: Mapping[str, Any]) -> dict[str, Any]:
    """Echo the root list's schema + runtime identity + acquisition receipt."""
    runtime = root_list["runtime"]
    return {
        "schema": root_list["schema"],
        "runtime": {
            "root": runtime.get("root"),
            "db_present": runtime.get("db_present"),
            "identity": runtime.get("identity"),
            "acquisition": dict(runtime["acquisition"]),
        },
    }


def _coverage(root_list: Mapping[str, Any]) -> dict[str, Any]:
    """R7: explicit count/total/truncated/completeness copy from the root list."""
    count = int(root_list["count"])
    truncated = bool(root_list["truncated"])
    total: int | None = root_list["total"] if not truncated else None
    acquisition = root_list["runtime"]["acquisition"]
    provenance_state = acquisition.get("provenance", {}).get("state") if isinstance(
        acquisition.get("provenance"), Mapping
    ) else None
    completeness = "PARTIAL" if truncated or provenance_state == "PARTIAL" else "COMPLETE"
    coverage = {
        "count": count,
        "total": total,
        "truncated": truncated,
        "completeness": completeness,
    }
    assert set(coverage) == COVERAGE_KEYS
    return coverage


def _queue_effect_exception(control_room: Any) -> dict[str, Any]:
    """R4: queue-level effect_exception from control_room.autonomy."""
    if not isinstance(control_room, Mapping):
        return {"value": "UNKNOWN", "scope": "RUNTIME_CURRENT_WORKER", "observable": False}
    autonomy = control_room.get("autonomy")
    if not isinstance(autonomy, Mapping) or autonomy.get("schema") != _AUTONOMY_SCHEMA:
        return {"value": "UNKNOWN", "scope": "RUNTIME_CURRENT_WORKER", "observable": False}
    responsibilities = autonomy.get("responsibilities")
    if not isinstance(responsibilities, list):
        return {"value": "UNKNOWN", "scope": "RUNTIME_CURRENT_WORKER", "observable": False}
    for row in responsibilities:
        if not isinstance(row, Mapping):
            continue
        placement = row.get("placement_state")
        if isinstance(placement, Mapping) and placement.get("value") == "EFFECT_UNKNOWN":
            return {
                "value": "EFFECT_UNKNOWN",
                "scope": "RUNTIME_CURRENT_WORKER",
                "observable": True,
            }
    return {"value": "NONE", "scope": "RUNTIME_CURRENT_WORKER", "observable": False}


def _acceptance() -> dict[str, Any]:
    """R5: acceptance is ALWAYS NOT_PROJECTED in this projection."""
    return {
        "state": "NOT_PROJECTED",
        "producer_owner": None,
        "reason": "product acceptance has no producer in this projection",
    }


def _next_actor(ref: str, accountability: Mapping[str, Mapping[str, Any]] | None) -> dict[str, Any]:
    """R2: only the explicit Agent OS accountability input carries next_actor."""
    if accountability is None or ref not in accountability:
        return {"value": "UNKNOWN", "source": "AGENT_OS", "reason": "no_producer"}
    next_actor = accountability[ref]["next_actor"]
    if next_actor == "SOL":
        return {"value": "NEEDS_SOL", "source": "AGENT_OS", "reason": "evidence_supplied"}
    return {"value": "NEEDS_WORKER", "source": "AGENT_OS", "reason": "evidence_supplied"}


def _capacity(
    ref: str,
    status: str,
    placement: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """R3: WAITING_CAPACITY only when pre-START AND placement evidence."""
    if placement is None or ref not in placement:
        return {"value": "UNKNOWN", "source": "AUTONOMY", "reason": "no_producer"}
    if status in _PRE_START_STATUSES:
        return {
            "value": "WAITING_CAPACITY",
            "source": "AUTONOMY",
            "reason": "pre_start_placement_evidence",
        }
    return {"value": "NOT_APPLICABLE", "source": "AUTONOMY", "reason": "post_start_lifecycle"}


def _effect(ref: str, effects: Mapping[str, Mapping[str, Any]] | None) -> dict[str, Any]:
    """R4: only an explicit effects input carries effect state."""
    if effects is None or ref not in effects:
        return {"value": "UNKNOWN", "source": "EFFECT_PRODUCER", "reason": "no_producer"}
    state = effects[ref]["state"]
    return {"value": state, "source": "EFFECT_PRODUCER", "reason": "evidence_supplied"}


def _row_group(row: Mapping[str, Any]) -> str:
    """Group precedence: EFFECT_EXCEPTION sticky → next_actor → capacity → lifecycle."""
    effect = row["effect"]
    next_actor = row["next_actor"]
    capacity = row["capacity"]
    status = row["lifecycle"]["status"]
    # R4: EFFECT_UNKNOWN sticky — takes the EFFECT_EXCEPTION group regardless of lifecycle
    # and can never be WAITING_CAPACITY.
    if effect["value"] == "EFFECT_UNKNOWN":
        return "EFFECT_EXCEPTION"
    # R2: explicit next_actor evidence wins over the lifecycle group so an admitted
    # but unowned queued Job lands in the right Needs-* group.
    if next_actor["value"] == "NEEDS_SOL":
        return "NEEDS_SOL"
    if next_actor["value"] == "NEEDS_WORKER":
        return "NEEDS_WORKER"
    # R3: WAITING_CAPACITY only when pre-START AND placement evidence supplied.
    if capacity["value"] == "WAITING_CAPACITY":
        return "WAITING_CAPACITY"
    # R8: closed lifecycle→group mapping; everything else falls through to UNKNOWN.
    return _JOB_STATUS_GROUPS.get(status, "UNKNOWN")


def _row(
    ref: str,
    row: Mapping[str, Any],
    *,
    accountability: Mapping[str, Mapping[str, Any]] | None,
    placement: Mapping[str, Mapping[str, Any]] | None,
    effects: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    lifecycle = {
        "status": row["status"],
        "source": "EXECUTIVE_RUNTIME",
        "orchestration_role": row["orchestration_role"],
        "depth": row["depth"],
    }
    built = {
        "root_job_id": ref,
        "lifecycle": lifecycle,
        "next_actor": _next_actor(ref, accountability),
        "capacity": _capacity(ref, row["status"], placement),
        "effect": _effect(ref, effects),
        "acceptance": _acceptance(),
        "group": None,  # filled after we know all columns
    }
    built["group"] = _row_group(built)
    assert set(built) == ROW_KEYS
    assert set(built["lifecycle"]) == _LIFECYCLE_KEYS
    assert set(built["next_actor"]) == _NEXT_ACTOR_KEYS
    assert set(built["capacity"]) == _CAPACITY_KEYS
    assert set(built["effect"]) == _EFFECT_KEYS
    assert set(built["acceptance"]) == ACCEPTANCE_KEYS
    return built


def _empty_groups() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in _GROUP_ORDER}


# ---------------------------------------------------------------------------
# public composer
# ---------------------------------------------------------------------------


def compose_work_queue_v1(
    root_list: Mapping[str, Any],
    *,
    control_room: Mapping[str, Any] | None = None,
    accountability: Mapping[str, Mapping[str, Any]] | None = None,
    placement: Mapping[str, Mapping[str, Any]] | None = None,
    effects: Mapping[str, Mapping[str, Any]] | None = None,
    generated_at: str | None = None,
    source_observation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure: render the workspace work-queue from its named inputs only.

    The composer never reads the Runtime; it consumes only the
    ``mastermind.fabric_job_root_list.v2`` document passed in ``root_list``
    plus optional Agent OS evidence inputs and the optional control-room
    document for the queue-level ``effect_exception`` read.  When the
    caller supplies ``source_observation`` (the existing CCR-and-Runtime
    observation receipt), it is attached verbatim under that key.
    """
    validated_root = _validate_root_list(root_list)
    validated_accountability = _validate_accountability(accountability)
    validated_placement = _validate_placement(placement)
    validated_effects = _validate_effects(effects)
    lifecycle_source = _lifecycle_source(validated_root)
    effect_exception = _queue_effect_exception(control_room)
    assert set(effect_exception) == QUEUE_EFFECT_EXCEPTION_KEYS
    document_generated_at = generated_at or _utc_now()

    if _lifecycle_unavailable(validated_root):
        unavailable = {
            "schema": WORK_QUEUE_SCHEMA,
            "generated_at": document_generated_at,
            "availability": "UNAVAILABLE",
            "lifecycle_source": lifecycle_source,
            "effect_exception": effect_exception,
            "coverage": _coverage(validated_root),
            "groups": _empty_groups(),
            "source_observation": dict(source_observation) if isinstance(source_observation, Mapping) else None,
            "reason_codes": [_REASON_LIFECYCLE_UNAVAILABLE],
        }
        assert set(unavailable) == OUTPUT_KEYS
        return unavailable

    groups = _empty_groups()
    for row in validated_root["roots"]:
        built = _row(
            str(row["job_id"]),
            row,
            accountability=validated_accountability,
            placement=validated_placement,
            effects=validated_effects,
        )
        groups[built["group"]].append(built)
    # Deterministic order: sort each group by root_job_id ascending.
    for key in _GROUP_ORDER:
        groups[key] = sorted(groups[key], key=lambda item: item["root_job_id"])

    document = {
        "schema": WORK_QUEUE_SCHEMA,
        "generated_at": document_generated_at,
        "availability": "AVAILABLE",
        "lifecycle_source": lifecycle_source,
        "effect_exception": effect_exception,
        "coverage": _coverage(validated_root),
        "groups": groups,
        "source_observation": dict(source_observation) if isinstance(source_observation, Mapping) else None,
        "reason_codes": [],
    }
    assert set(document) == OUTPUT_KEYS
    assert set(document["groups"]) == _GROUP_SET
    return document


__all__ = [
    "WORK_QUEUE_SCHEMA",
    "OUTPUT_KEYS",
    "ROW_KEYS",
    "ACCEPTANCE_KEYS",
    "COVERAGE_KEYS",
    "compose_work_queue_v1",
]