"""control_plane.work_queue_projection — read-only workspace work-queue view.

PURE compositor over the Executive root-list (``mastermind.fabric_job_root_list.v2``).
Encodes the eight binding truth rules (R1-R8) from the parent ruling 5805095742
and the design freeze (Figma 138:8).  Never infers lifecycle, ownership,
capacity, or acceptance from anything except its named inputs.

Top-level document key set is closed; per-row keys are closed; the
group list is closed and ordered.  Composing twice from the same inputs
yields byte-identical canonical JSON.

``generated_at`` is the composer wall-clock (or the caller-supplied value) —
NOT a snapshot freshness fact.  The receipt of snapshot freshness is
separately carried through the :class:`source_observation` envelope;
``generated_at`` only records when this compositor ran.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from control_plane.executive_runtime import JobStatus
from control_plane.fabric_job_view import (
    _BOUNDED_UNAVAILABLE_NOTE,
    _GENERATION_CONFLICT_NOTE,
    _ROOT_ENUMERATION_NOTE,
)
from common.executive_workspace_contract import QUEUE_EFFECT_EXCEPTION_REASONS

WORK_QUEUE_SCHEMA = "mastermind.workspace_work_queue.v1"
_ROOT_LIST_SCHEMA = "mastermind.fabric_job_root_list.v2"
_AUTONOMY_SCHEMA = "mastermind.autonomy_control_room.v1"

#: Evidence freshness: max age (seconds) admitted for an ``observed_at``
#: against the caller-supplied ``evidence_as_of`` anchor.
EVIDENCE_MAX_AGE_S = 900

#: Strict RFC3339 UTC pattern required for every ``observed_at``.  Microsecond
#: fraction is permitted but optional; trailing ``Z`` is mandatory.
_OBSERVED_AT_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$"
)

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

#: Job lifecycle pre-START set (R3, R8).
_PRE_START_STATUSES = frozenset({"QUEUED"})

#: Group names the next_actor override is allowed to act on (B4).  The
#: override fires only when the lifecycle-group would be QUEUED or RUNNING;
#: COMPLETED → COMPLETED_NOT_ACCEPTED and FAILED/LOST/CANCELLED → TERMINAL
#: are terminal/completed and never re-classify under accountability.
_OVERRIDE_APPLICABLE_GROUPS = frozenset({"QUEUED", "RUNNING"})

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

#: Closed next_actor / capacity / effect column keys — ``evidence_ref`` and
#: ``observed_at`` carry the producer's receipt; both are null when no
#: producer supplied evidence for the row.
_NEXT_ACTOR_KEYS: frozenset[str] = frozenset({"value", "source", "reason", "evidence_ref", "observed_at"})
_CAPACITY_KEYS: frozenset[str] = frozenset({"value", "source", "reason", "evidence_ref", "observed_at"})
_EFFECT_KEYS: frozenset[str] = frozenset({"value", "source", "reason", "evidence_ref", "observed_at"})

#: Closed acceptance column keys (mirrors fabric_job_view._acceptance_v2).
ACCEPTANCE_KEYS: frozenset[str] = frozenset({"state", "producer_owner", "reason"})

#: Closed queue-level effect_exception keys (N7: ``reason`` added).
QUEUE_EFFECT_EXCEPTION_KEYS: frozenset[str] = frozenset({"value", "scope", "observable", "reason"})

#: Closed queue-level effect_exception reason vocabulary.
_QUEUE_EFFECT_EXCEPTION_REASON_CONTROL_ROOM_MISSING = "control_room_missing"
_QUEUE_EFFECT_EXCEPTION_REASON_AUTONOMY_MISSING = "autonomy_missing"
_QUEUE_EFFECT_EXCEPTION_REASON_NO_EXCEPTION_OBSERVED = "no_exception_observed"
_QUEUE_EFFECT_EXCEPTION_REASON_EXCEPTION_OBSERVED = "exception_observed"
#: N4: emitted by the read service's typed refusal body when the CCR
#: bracket itself refused before the composer could read autonomy — the
#: composer's own vocabulary is preserved (``control_room_missing`` and
#: ``autonomy_missing`` describe the composer's view of a missing or
#: malformed control room document, not the read service's).
_QUEUE_EFFECT_EXCEPTION_REASON_READ_REFUSED = "read_refused"

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

#: Closed lifecycle→group table over the Executive JobStatus enum (R8, B4).
#: Every enum member is mapped explicitly — the composer raises ``ValueError``
#: on an unmapped status so the closed-table invariant can never be silently
#: widened by a new enum member sneaking past the validator.
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
#: B3: queue-level EFFECT_UNKNOWN but no per-row effect attribution.
_REASON_EFFECT_NOT_ROW_ATTRIBUTED = "effect_not_row_attributed"
#: N3: root-list degraded notes present on an AVAILABLE document.
_REASON_LIFECYCLE_DEGRADED = "lifecycle_degraded"
#: Shared prefix that distinguishes the producer's bounded-unavailable
#: family.  Both :data:`fabric_job_view._BOUNDED_UNAVAILABLE_NOTE` and
#: the legacy :func:`fabric_job_view.list_roots_v2` failure path
#: (which appends the bounded first line of the underlying error after
#: the colon) match by this prefix.  Used by the closed-set predicates
#: below so the bounded-unavailable detection stays in ONE place.
_BOUNDED_UNAVAILABLE_PHRASE = "bounded acquisition unavailable"

#: Closed set of degraded-note phrases that warrant a ``lifecycle_degraded``
#: reason code on an AVAILABLE document.  Sourced from
#: :mod:`control_plane.fabric_job_view` constants so the composer never
#: re-types the strings.  ``_ROOT_ENUMERATION_NOTE`` is informational only —
#: every bounded acquisition surfaces it, so it never contributes to the
#: reason code (the producer's degraded list still echoes it verbatim).
#: The bounded-unavailable note is matched by the shared prefix phrase
#: (:func:`_is_bounded_unavailable_note`), not by exact equality on the
#: constant — the producer's legacy path appends arbitrary detail after
#: the colon.
_DEGRADATION_NOTES: tuple[str, ...] = (
    _BOUNDED_UNAVAILABLE_NOTE,
    "bounded root discovery truncated; omitted roots are not counted",
    _GENERATION_CONFLICT_NOTE,
)


def _is_bounded_unavailable_note(entry: Any) -> bool:
    """One closed-set predicate for the bounded-unavailable producer family.

    The producer's exact emission is
    :data:`fabric_job_view._BOUNDED_UNAVAILABLE_NOTE`; the legacy
    :func:`fabric_job_view.list_roots_v2` failure path appends an
    arbitrary failure first line after the colon.  Both share the prefix
    :data:`_BOUNDED_UNAVAILABLE_PHRASE` — that is the closed-set
    invariant.  Used by BOTH :func:`_lifecycle_unavailable` (drives the
    UNAVAILABLE branch) and :func:`_is_degradation_note` (drives the
    ``lifecycle_degraded`` reason code on AVAILABLE) so the two sites
    cannot drift.
    """
    return isinstance(entry, str) and entry.startswith(_BOUNDED_UNAVAILABLE_PHRASE)


def _is_degradation_note(entry: Any) -> bool:
    """Closed-set predicate over the root list's ``degraded`` entries.

    The bounded-unavailable family is matched by the shared prefix
    :func:`_is_bounded_unavailable_note` (the producer appends detail
    after the colon — anything from the canonical constant down to
    ``"bounded acquisition unavailable: disk I/O error"`` counts).  The
    other two notes are matched exactly.  Anything else is informational
    only and is echoed in ``lifecycle_source.degraded`` without
    contributing a reason code.
    """
    if _is_bounded_unavailable_note(entry):
        return True
    if not isinstance(entry, str):
        return False
    for phrase in _DEGRADATION_NOTES:
        if entry == phrase:
            return True
    return False


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_observed_at(observed_at: str) -> datetime:
    """Strict RFC3339 UTC parse — refuse anything outside the canonical shape.

    A trailing ``Z`` is mandatory; an optional 1–6-digit microsecond fraction
    is permitted.  Naive values, ``+00:00`` offsets, leap-second markers and
    non-UTC locales never admit — anything else surfaces as ``ValueError``.

    Calendar-invalid but pattern-valid values (e.g. ``2026-02-30T00:00:00Z``,
    ``2026-01-01T23:59:60Z``) are wrapped to the module's own message so the
    caller never sees ``strptime``'s text or leaks the day/month names.
    """
    if not isinstance(observed_at, str) or _OBSERVED_AT_PATTERN.fullmatch(observed_at) is None:
        raise ValueError(
            f"observed_at invalid: must match RFC3339 UTC like 2026-09-23T00:00:00Z, got {observed_at!r}"
        )
    try:
        return datetime.strptime(observed_at, "%Y-%m-%dT%H:%M:%S.%fZ" if "." in observed_at
                                  else "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(
            f"observed_at invalid: must match RFC3339 UTC like 2026-09-23T00:00:00Z, got {observed_at!r}"
        ) from exc


def _parse_evidence_as_of(evidence_as_of: str) -> datetime:
    """Strict RFC3339 UTC parse for the evidence anchor.

    N9: error message reads ``evidence_as_of invalid`` so callers can
    distinguish evidence anchor from a per-row observed_at rejection.
    """
    if not isinstance(evidence_as_of, str) or _OBSERVED_AT_PATTERN.fullmatch(evidence_as_of) is None:
        raise ValueError(
            f"evidence_as_of invalid: must match RFC3339 UTC like 2026-09-23T00:00:00Z, got {evidence_as_of!r}"
        )
    try:
        return datetime.strptime(evidence_as_of, "%Y-%m-%dT%H:%M:%S.%fZ" if "." in evidence_as_of
                                  else "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(
            f"evidence_as_of invalid: must match RFC3339 UTC like 2026-09-23T00:00:00Z, got {evidence_as_of!r}"
        ) from exc


def _evidence_freshness(
    observed_at: str,
    *,
    evidence_as_of: datetime,
    evidence_max_age_s: int,
) -> bool:
    """Return ``True`` when ``observed_at`` is within the validity window.

    Refuses (returns False) when ``observed_at`` is older than
    ``evidence_as_of - evidence_max_age_s`` OR later than ``evidence_as_of``.
    Callers must already have parsed ``observed_at`` through :func:`_parse_observed_at`.
    """
    observed_dt = _parse_observed_at(observed_at)
    age_s = (evidence_as_of - observed_dt).total_seconds()
    return 0 <= age_s <= evidence_max_age_s


def _ensure_key_set(d: Mapping[str, Any], keys: frozenset[str], *, label: str) -> None:
    if set(d) != keys:
        raise ValueError(f"{label} keys must equal {sorted(keys)}, got {sorted(d)}")


def _ensure_required_producers_evidence(
    *,
    accountability: Mapping[str, Mapping[str, Any]] | None,
    placement: Mapping[str, Mapping[str, Any]] | None,
    effects: Mapping[str, Mapping[str, Any]] | None,
    evidence_as_of: str | None,
) -> datetime | None:
    """When any producer is non-None, ``evidence_as_of`` MUST be supplied.

    Returns the parsed evidence anchor when supplied, else ``None``.
    """
    any_producer = any(value is not None for value in (accountability, placement, effects))
    if any_producer and evidence_as_of is None:
        raise ValueError("evidence_as_of is required when any producer is supplied")
    if evidence_as_of is None:
        return None
    return _parse_evidence_as_of(evidence_as_of)


def _validate_root_list(root_list: Any) -> Mapping[str, Any]:
    """Strict shape validation; raise ValueError on anything else."""
    if not isinstance(root_list, Mapping):
        raise ValueError("root_list must be a mapping")
    if root_list.get("schema") != _ROOT_LIST_SCHEMA:
        raise ValueError(
            f"root_list schema must equal {_ROOT_LIST_SCHEMA!r}, got {root_list.get('schema')!r}"
        )
    _ensure_key_set(root_list, _ROOT_LIST_KEYS, label="root_list")
    runtime = root_list.get("runtime")
    if not isinstance(runtime, Mapping) or set(runtime) != _ROOT_LIST_RUNTIME_KEYS:
        raise ValueError("root_list runtime envelope malformed")
    acquisition = runtime.get("acquisition")
    if not isinstance(acquisition, Mapping) or set(acquisition) != _ACQUISITION_KEYS:
        raise ValueError("root_list runtime.acquisition envelope malformed")
    roots = root_list.get("roots")
    if not isinstance(roots, list):
        raise ValueError("root_list roots must be a list")
    seen_job_ids: set[str] = set()
    for row in roots:
        if not isinstance(row, Mapping) or set(row) != _ROOT_ROW_KEYS:
            raise ValueError(f"root row keys invalid: {row!r}")
        job_id = row["job_id"]
        if not isinstance(job_id, str) or not job_id:
            raise ValueError(f"root row job_id invalid: {row!r}")
        if job_id in seen_job_ids:
            raise ValueError(f"root row duplicate job_id: {job_id!r}")
        seen_job_ids.add(job_id)
        if not isinstance(row["status"], str) or not row["status"]:
            raise ValueError(f"root row status invalid: {row!r}")
        if row["status"] not in _JOB_STATUS_GROUPS:
            raise ValueError(f"root row status not mapped: {row['status']!r}")
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
        # Observed_at must parse as strict RFC3339 UTC; a producer's evidence
        # is rejected up front rather than later silently failing the row.
        _parse_observed_at(row["observed_at"])
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
        _parse_observed_at(row["observed_at"])
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
        if set(row) != {"state", "carrier", "evidence_ref", "observed_at"}:
            raise ValueError("effects row keys invalid")
        if row["state"] not in ("EFFECT_UNKNOWN", "NONE"):
            raise ValueError(f"effects row state invalid: {row['state']!r}")
        if not isinstance(row["carrier"], str) or not row["carrier"]:
            raise ValueError("effects row carrier invalid")
        for str_key in ("evidence_ref", "observed_at"):
            if not isinstance(row[str_key], str) or not row[str_key]:
                raise ValueError(f"effects row {str_key} invalid")
        _parse_observed_at(row["observed_at"])
    return value


def _lifecycle_unavailable(root_list: Mapping[str, Any]) -> bool:
    """R1: refuse lifecycle when the Runtime is degraded or absent.

    B1: the bounded-unavailable detection uses the SHARED predicate
    :func:`_is_bounded_unavailable_note` — the same predicate the
    reason-code gate (:func:`_is_degradation_note`) uses for the
    ``lifecycle_degraded`` code on AVAILABLE documents.  One closed set,
    one predicate, both sites.
    """
    runtime = root_list["runtime"]
    if runtime.get("db_present") is not True:
        return True
    acquisition = runtime["acquisition"]
    generation = acquisition.get("generation")
    state = generation.get("state") if isinstance(generation, Mapping) else None
    if state != "SAME":
        return True
    degraded = root_list.get("degraded") or []
    return any(_is_bounded_unavailable_note(entry) for entry in degraded)


def _lifecycle_source(root_list: Mapping[str, Any]) -> dict[str, Any]:
    """Echo the root list's schema + runtime identity + acquisition receipt.

    N3: ``degraded`` is echoed verbatim — the producer's degradation list
    is not silently dropped.  The downstream caller decides whether a
    non-empty list warrants a ``lifecycle_degraded`` reason code.
    """
    runtime = root_list["runtime"]
    return {
        "schema": root_list["schema"],
        "runtime": {
            "root": runtime.get("root"),
            "db_present": runtime.get("db_present"),
            "identity": runtime.get("identity"),
            "acquisition": dict(runtime["acquisition"]),
        },
        "degraded": list(root_list.get("degraded") or []),
    }


def _coverage_for_unavailable(root_list: Mapping[str, Any]) -> dict[str, Any]:
    """UNAVAILABLE branch coverage: zero rows, never claim COMPLETE (B2)."""
    return {
        "count": 0,
        "total": None,
        "truncated": bool(root_list["truncated"]),
        "completeness": "PARTIAL",
    }


def _coverage(root_list: Mapping[str, Any]) -> dict[str, Any]:
    """R7/N4: explicit count/total/truncated/completeness copy from the root list.

    ``completeness`` is PARTIAL when the source is known to be incomplete —
    the root list reports ``truncated: True``, ``provenance.state == "PARTIAL"``,
    or ``total is None`` (the producer could not enumerate the universe).
    """
    count = int(root_list["count"])
    truncated = bool(root_list["truncated"])
    total: int | None = root_list["total"] if not truncated else None
    acquisition = root_list["runtime"]["acquisition"]
    provenance_state = acquisition.get("provenance", {}).get("state") if isinstance(
        acquisition.get("provenance"), Mapping
    ) else None
    completeness = ("PARTIAL" if truncated or total is None
                    or provenance_state == "PARTIAL" else "COMPLETE")
    return {
        "count": count,
        "total": total,
        "truncated": truncated,
        "completeness": completeness,
    }


def _queue_effect_exception(control_room: Any) -> dict[str, Any]:
    """R4/N7: queue-level effect_exception from control_room.autonomy.

    ``reason`` distinguishes "could not look" (control_room or autonomy
    absent) from "looked, found no exception" so the queue-level EFFECT_UNKNOWN
    state is never confused with a healthy empty read.  The emitted
    ``reason`` is asserted against the closed
    :data:`common.executive_workspace_contract.QUEUE_EFFECT_EXCEPTION_REASONS`
    vocabulary so the composer can never silently introduce a new member.
    """
    if not isinstance(control_room, Mapping):
        result = {"value": "UNKNOWN", "scope": "RUNTIME_CURRENT_WORKER",
                  "observable": False, "reason": _QUEUE_EFFECT_EXCEPTION_REASON_CONTROL_ROOM_MISSING}
    else:
        autonomy = control_room.get("autonomy")
        if not isinstance(autonomy, Mapping) or autonomy.get("schema") != _AUTONOMY_SCHEMA:
            result = {"value": "UNKNOWN", "scope": "RUNTIME_CURRENT_WORKER",
                      "observable": False, "reason": _QUEUE_EFFECT_EXCEPTION_REASON_AUTONOMY_MISSING}
        else:
            responsibilities = autonomy.get("responsibilities")
            if not isinstance(responsibilities, list):
                result = {"value": "UNKNOWN", "scope": "RUNTIME_CURRENT_WORKER",
                          "observable": False, "reason": _QUEUE_EFFECT_EXCEPTION_REASON_AUTONOMY_MISSING}
            else:
                observed = False
                for row in responsibilities:
                    if not isinstance(row, Mapping):
                        continue
                    placement = row.get("placement_state")
                    if isinstance(placement, Mapping) and placement.get("value") == "EFFECT_UNKNOWN":
                        observed = True
                        break
                if observed:
                    result = {
                        "value": "EFFECT_UNKNOWN",
                        "scope": "RUNTIME_CURRENT_WORKER",
                        "observable": True,
                        "reason": _QUEUE_EFFECT_EXCEPTION_REASON_EXCEPTION_OBSERVED,
                    }
                else:
                    result = {"value": "NONE", "scope": "RUNTIME_CURRENT_WORKER",
                              "observable": False,
                              "reason": _QUEUE_EFFECT_EXCEPTION_REASON_NO_EXCEPTION_OBSERVED}
    # Closed-set guard: the composer's emitted ``reason`` MUST be a member
    # of the contract's effect_exception reason vocabulary.
    assert result["reason"] in QUEUE_EFFECT_EXCEPTION_REASONS, (
        f"_queue_effect_exception emitted reason {result['reason']!r} "
        f"not in QUEUE_EFFECT_EXCEPTION_REASONS="
        f"{sorted(QUEUE_EFFECT_EXCEPTION_REASONS)}"
    )
    return result


def _acceptance() -> dict[str, Any]:
    """R5: acceptance is ALWAYS NOT_PROJECTED in this projection."""
    return {
        "state": "NOT_PROJECTED",
        "producer_owner": None,
        "reason": "product acceptance has no producer in this projection",
    }


def _no_producer_column(reason: str, source: str | None) -> dict[str, Any]:
    """No-producer column shape: explicit source=None for closed-key-set guard."""
    return {
        "value": "UNKNOWN",
        "source": source,
        "reason": reason,
        "evidence_ref": None,
        "observed_at": None,
    }


def _next_actor(
    ref: str,
    accountability: Mapping[str, Mapping[str, Any]] | None,
    *,
    evidence_as_of: datetime | None,
    evidence_max_age_s: int,
) -> dict[str, Any]:
    """R2: only the explicit Agent OS accountability input carries next_actor.

    A stale or future-dated ``observed_at`` falls back to ``UNKNOWN`` with
    ``reason: "evidence_stale"``; the ``evidence_ref``/``observed_at`` are
    still carried so the staleness is auditable in the column dict.
    """
    if accountability is None or ref not in accountability:
        return _no_producer_column("no_producer", source=None)
    row = accountability[ref]
    evidence_ref = row["evidence_ref"]
    observed_at = row["observed_at"]
    if evidence_as_of is None or not _evidence_freshness(
        observed_at, evidence_as_of=evidence_as_of,
        evidence_max_age_s=evidence_max_age_s,
    ):
        return {
            "value": "UNKNOWN",
            "source": None,
            "reason": "evidence_stale",
            "evidence_ref": evidence_ref,
            "observed_at": observed_at,
        }
    if row["next_actor"] == "SOL":
        return {
            "value": "NEEDS_SOL", "source": "AGENT_OS", "reason": "evidence_supplied",
            "evidence_ref": evidence_ref, "observed_at": observed_at,
        }
    return {
        "value": "NEEDS_WORKER", "source": "AGENT_OS", "reason": "evidence_supplied",
        "evidence_ref": evidence_ref, "observed_at": observed_at,
    }


def _capacity(
    ref: str,
    status: str,
    placement: Mapping[str, Mapping[str, Any]] | None,
    *,
    evidence_as_of: datetime | None,
    evidence_max_age_s: int,
) -> dict[str, Any]:
    """R3/B1: WAITING_CAPACITY only when pre-START AND placement evidence.

    The lifecycle test fires FIRST: any post-START row is
    ``NOT_APPLICABLE`` regardless of whether placement evidence was
    supplied.  A pre-START row without placement evidence is
    ``UNKNOWN`` (``no_producer``); with placement evidence, the
    capacity is ``WAITING_CAPACITY``.  Stale placement evidence falls
    back to ``UNKNOWN`` with ``reason: "evidence_stale"`` (so the row
    cannot be promoted to ``WAITING_CAPACITY``).
    """
    if status not in _PRE_START_STATUSES:
        # B4: provenance is the Executive Runtime lifecycle (the row's
        # status, not placement evidence) — no Capacity producer was
        # consulted; "AUTONOMY" mislabels who actually emitted this column.
        return {
            "value": "NOT_APPLICABLE", "source": "EXECUTIVE_RUNTIME",
            "reason": "post_start_lifecycle",
            "evidence_ref": None, "observed_at": None,
        }
    if placement is None or ref not in placement:
        return _no_producer_column("no_producer", source=None)
    row = placement[ref]
    evidence_ref = row["evidence_ref"]
    observed_at = row["observed_at"]
    if evidence_as_of is None or not _evidence_freshness(
        observed_at, evidence_as_of=evidence_as_of,
        evidence_max_age_s=evidence_max_age_s,
    ):
        return {
            "value": "UNKNOWN",
            "source": None,
            "reason": "evidence_stale",
            "evidence_ref": evidence_ref,
            "observed_at": observed_at,
        }
    return {
        "value": "WAITING_CAPACITY", "source": "AUTONOMY",
        "reason": "pre_start_placement_evidence",
        "evidence_ref": evidence_ref, "observed_at": observed_at,
    }


def _effect(
    ref: str,
    effects: Mapping[str, Mapping[str, Any]] | None,
    *,
    evidence_as_of: datetime | None,
    evidence_max_age_s: int,
) -> dict[str, Any]:
    """R4: only an explicit effects input carries effect state.

    EFFECT_UNKNOWN is sticky: a stale ``observed_at`` does NOT clear the
    exception (R4 — staleness never reverses a recorded effect), the
    reason reads ``"evidence_supplied_stale"`` instead.  ``NONE`` from
    a producer without evidence still falls back to ``UNKNOWN`` because
    the producer's value carries no operational meaning on its own.
    """
    if effects is None or ref not in effects:
        return _no_producer_column("no_producer", source=None)
    row = effects[ref]
    state = row["state"]
    evidence_ref = row["evidence_ref"]
    observed_at = row["observed_at"]
    fresh = evidence_as_of is not None and _evidence_freshness(
        observed_at, evidence_as_of=evidence_as_of,
        evidence_max_age_s=evidence_max_age_s,
    )
    if not fresh:
        if state == "EFFECT_UNKNOWN":
            # R4 sticky: keep the exception, label the staleness.
            return {
                "value": state, "source": "EFFECT_PRODUCER",
                "reason": "evidence_supplied_stale",
                "evidence_ref": evidence_ref, "observed_at": observed_at,
            }
        # Stale NONE / other state: fall back to no-producer UNKNOWN.
        return {
            "value": "UNKNOWN", "source": None,
            "reason": "evidence_stale",
            "evidence_ref": evidence_ref, "observed_at": observed_at,
        }
    return {
        "value": state, "source": "EFFECT_PRODUCER",
        "reason": "evidence_supplied",
        "evidence_ref": evidence_ref, "observed_at": observed_at,
    }


def _row_group(row: Mapping[str, Any]) -> str:
    """Group precedence: EFFECT_EXCEPTION sticky → next_actor → capacity → lifecycle.

    B4: the NEEDS_SOL/NEEDS_WORKER override fires ONLY when the
    lifecycle-group is QUEUED or RUNNING.  COMPLETED → COMPLETED_NOT_ACCEPTED
    and FAILED/LOST/CANCELLED → TERMINAL are terminal/completed groups and
    are NEVER overridden by accountability — those rows may still carry a
    ``next_actor`` column value for audit, but their group is decided by
    the lifecycle alone.
    """
    effect = row["effect"]
    next_actor = row["next_actor"]
    capacity = row["capacity"]
    status = row["lifecycle"]["status"]
    if effect["value"] == "EFFECT_UNKNOWN":
        return "EFFECT_EXCEPTION"
    lifecycle_group = _JOB_STATUS_GROUPS[status]
    if (lifecycle_group in _OVERRIDE_APPLICABLE_GROUPS
            and next_actor["value"] in ("NEEDS_SOL", "NEEDS_WORKER")):
        return next_actor["value"]
    if capacity["value"] == "WAITING_CAPACITY":
        return "WAITING_CAPACITY"
    return lifecycle_group


def _row(
    ref: str,
    row: Mapping[str, Any],
    *,
    accountability: Mapping[str, Mapping[str, Any]] | None,
    placement: Mapping[str, Mapping[str, Any]] | None,
    effects: Mapping[str, Mapping[str, Any]] | None,
    evidence_as_of: datetime | None,
    evidence_max_age_s: int,
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
        "next_actor": _next_actor(ref, accountability,
                                  evidence_as_of=evidence_as_of,
                                  evidence_max_age_s=evidence_max_age_s),
        "capacity": _capacity(ref, row["status"], placement,
                              evidence_as_of=evidence_as_of,
                              evidence_max_age_s=evidence_max_age_s),
        "effect": _effect(ref, effects,
                          evidence_as_of=evidence_as_of,
                          evidence_max_age_s=evidence_max_age_s),
        "acceptance": _acceptance(),
        "group": None,  # filled after we know all columns
    }
    built["group"] = _row_group(built)
    _ensure_key_set(built, ROW_KEYS, label="row")
    _ensure_key_set(built["lifecycle"], _LIFECYCLE_KEYS, label="lifecycle column")
    _ensure_key_set(built["next_actor"], _NEXT_ACTOR_KEYS, label="next_actor column")
    _ensure_key_set(built["capacity"], _CAPACITY_KEYS, label="capacity column")
    _ensure_key_set(built["effect"], _EFFECT_KEYS, label="effect column")
    _ensure_key_set(built["acceptance"], ACCEPTANCE_KEYS, label="acceptance column")
    return built


def _empty_groups() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in _GROUP_ORDER}


# ---------------------------------------------------------------------------
# derive per-row producers from the autonomy control room
# ---------------------------------------------------------------------------


def derive_work_producers_v1(control_room: Any) -> dict[str, Any]:
    """Derive typed per-row producer inputs from the autonomy control room.

    Returns ``{"accountability": mapping|None, "placement": mapping|None,
    "effects": mapping|None, "evidence_as_of": str|None,
    "skipped": list[str]}`` ready for :func:`compose_work_queue_v1`.

    WQ-PROD-1 round 2 — closed eligibility + falsifiable freshness:

    - ``observed_at`` is the OLDEST
      ``validity.card.sources[*].observed_at`` (lexicographic minimum,
      which is chronological minimum for RFC3339 UTC).  It is NEVER
      ``qualified_at`` — the autonomy projection pins
      ``qualified_at == autonomy.generated_at`` for every card
      (see :mod:`control_plane.autonomy_control_room_projection`
      line ~1678), so using ``qualified_at`` would make the
      ``EVIDENCE_MAX_AGE_S`` window inert (age is always zero).  It
      is NEVER ``autonomy.generated_at`` either — the render clock
      would still defeat the freshness window.  ``evidence_as_of``
      stays ``autonomy.generated_at`` so the composer can anchor
      every row's freshness window against the render clock.
    - A card is eligible only when ``root_job_id`` is a non-empty
      string, ``runtime_root_state == "RESOLVED"``,
      ``root_job_ambiguous is False``, ``freshness == "current"``,
      ``is_actionable is True``,
      ``validity.card`` is a Mapping with ``valid_for_ms`` an int
      (not ``None``), and ``validity.card.sources`` is a non-empty
      list whose every entry has a parseable ``observed_at``.
      ``placement_state.value == "EFFECT_UNKNOWN"`` cards are
      EXEMPT from ``is_actionable`` and ``valid_for_ms`` (the
      projection itself de-presents EFFECT_UNKNOWN cards; an
      exception must never be hidden by an eligibility gate) but
      still require RESOLVED + unambiguous + a parseable source
      ``observed_at``.  Anything else records a per-card skip
      token: ``unresolved_root``, ``ambiguous_root``,
      ``freshness_<value>``, ``not_actionable``,
      ``unqualified_validity``, ``no_source_observations``,
      ``effect_unknown_without_source``, ``missing_responsibility_ref``.
    - Accountability emits ``SOL`` only when
      ``owed_turn.seat == "ceo"`` AND
      ``owed_turn.reason`` ∈ {``blocker_targets_seat``,
      ``agent_os_declared_blocker_targets_seat``,
      ``attention_targets_seat``}; ``WORKER`` analogously when
      ``seat == "worker"`` AND the reason is in the same set.
      ``worker_runtime_present``, ``no_owed_turn_signal``, ``coo``,
      ``chairman``, ``unknown``, missing owed_turn → no
      accountability row + skip token ``owed_<seat>_<reason>``.
      (The previous ``coo → WORKER`` mapping is dropped — the
      contract has no COO actor.)
    - Effects (``placement_state.value == "EFFECT_UNKNOWN"``) are
      exempt from the ``is_actionable`` / ``valid_for_ms`` gates
      but still require RESOLVED + unambiguous + a parseable
      source ``observed_at``; otherwise skip token
      ``effect_unknown_without_source``.  Stale effects still stick
      in the composer — R4 carrier rule unchanged.
    - Placement (``WAITING_CAPACITY``) follows the same eligibility
      as accountability minus the owed-turn condition.
    - ``evidence_ref`` is ``validity.card.proof_ref`` when a
      non-empty string, else ``responsibility_ref`` (proof_ref is
      content-addressed over the card's sources; see
      :mod:`control_plane.autonomy_control_room_projection`
      lines ~1663-1678).

    WQ-PROD-1 round 2 — conflict resolution:

    All eligible cards per root are collected first; for each
    producer independently, if 2+ cards on the same root derive
    DIFFERENT values (different ``next_actor`` for accountability;
    placement present-vs-absent counts as agreement only when both
    sides agree; effects with different carriers for effects) the
    producer emits NO row on that root and records
    ``<root>:conflict_<accountability|placement|effects>``.
    Agreeing duplicates (all cards derive the same value or all
    derive no value) keep the first card's row (in the autonomy
    section's own sort order: chairman_decision_required /
    is_actionable / seat_rank / responsibility_ref) and record
    ``<root>:duplicate_card``.

    ``skipped`` is the pure function's audit return and is NOT a
    top-level document key — the composer's closed
    :data:`OUTPUT_KEYS` set is unchanged.  The read path never
    reads ``skipped``; tests assert against the pure function's
    return value.

    When the control room is missing the autonomy section, the
    autonomy schema is wrong, ``responsibilities`` is not a list,
    or ``autonomy.generated_at`` is not parseable RFC3339 UTC,
    all three producers are ``None`` and ``evidence_as_of`` is
    ``None`` (today's behaviour — every row ``UNKNOWN/no_producer``).

    A returned producer mapping that ended with zero rows is
    replaced by ``None`` (never an empty mapping) so the
    composer's ``evidence_as_of required when any producer
    supplied`` invariant is preserved.  A malformed derivation
    raises ``ValueError`` from the existing validators — never a
    silent leak.
    """
    skipped: list[str] = []
    # Default: empty / missing / malformed autonomy → no producer.
    if not isinstance(control_room, Mapping):
        return {"accountability": None, "placement": None, "effects": None,
                "evidence_as_of": None, "skipped": []}
    autonomy = control_room.get("autonomy")
    if not isinstance(autonomy, Mapping) or autonomy.get("schema") != _AUTONOMY_SCHEMA:
        return {"accountability": None, "placement": None, "effects": None,
                "evidence_as_of": None, "skipped": []}
    responsibilities = autonomy.get("responsibilities")
    if not isinstance(responsibilities, list):
        return {"accountability": None, "placement": None, "effects": None,
                "evidence_as_of": None, "skipped": []}
    generated_at = autonomy.get("generated_at")
    # N9: malformed ``generated_at`` is the same refusal shape as
    # ``_parse_evidence_as_of`` would raise — the whole derivation
    # aborts cleanly without per-row fallout.
    try:
        if not isinstance(generated_at, str):
            raise ValueError
        _parse_evidence_as_of(generated_at)
    except ValueError:
        return {"accountability": None, "placement": None, "effects": None,
                "evidence_as_of": None, "skipped": []}

    # B3: collect ALL eligible cards per root first; resolve conflicts
    # per producer afterwards.  An eligibility skip records a per-card
    # token; an in-eligibility-card drop is silent (no root_job_id).
    per_root: dict[str, list[dict[str, Any]]] = {}
    for raw in responsibilities:
        if not isinstance(raw, Mapping):
            continue
        root_job_id = raw.get("root_job_id")
        if not isinstance(root_job_id, str) or not root_job_id:
            continue
        responsibility_ref = raw.get("responsibility_ref")
        if not isinstance(responsibility_ref, str) or not responsibility_ref:
            skipped.append(f"{root_job_id}:missing_responsibility_ref")
            continue
        view, skip_token = _evaluate_card(raw, responsibility_ref)
        if skip_token is not None:
            skipped.append(f"{root_job_id}:{skip_token}")
            continue
        per_root.setdefault(root_job_id, []).append(view)

    accountability: dict[str, dict[str, Any]] = {}
    placement: dict[str, dict[str, Any]] = {}
    effects: dict[str, dict[str, Any]] = {}
    for root_job_id, views in per_root.items():
        acc_row, pl_row, eff_row, conflict_tokens = _resolve_root(root_job_id, views)
        for token in conflict_tokens:
            skipped.append(token)
        if acc_row is not None:
            accountability[root_job_id] = acc_row
        if pl_row is not None:
            placement[root_job_id] = pl_row
        if eff_row is not None:
            effects[root_job_id] = eff_row

    result = {
        "accountability": accountability if accountability else None,
        "placement": placement if placement else None,
        "effects": effects if effects else None,
        "evidence_as_of": generated_at,
        "skipped": skipped,
    }
    # Run the existing validators so a derivation bug surfaces as a
    # ``ValueError`` rather than a leaked malformed mapping.  The
    # validators reject bad row shapes that the deriver might miss
    # (e.g. an empty ``carrier``); the read service's existing
    # try/except translates that into the typed ``projection_refused``
    # refusal exactly like a composer-raised ``ValueError``.
    _validate_accountability(result["accountability"])
    _validate_placement(result["placement"])
    _validate_effects(result["effects"])
    return result


#: Closed set of ``owed_turn.reason`` values that qualify a card for
#: the accountability row — see ``derive_work_producers_v1`` B1 contract.
_VALID_OWED_TURN_REASONS: frozenset[str] = frozenset({
    "blocker_targets_seat",
    "agent_os_declared_blocker_targets_seat",
    "attention_targets_seat",
})


def _evaluate_card(
    raw: Mapping[str, Any],
    responsibility_ref: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return (view, skip_token) for one responsibility card.

    ``view`` (when non-None) carries:

    - ``accountability``: ``"SOL"`` / ``"WORKER"`` / ``None`` when the
      card's owed_turn seat/reason don't qualify.
    - ``accountability_skip_reason``: per-card skip token recorded
      when the seat/reason don't produce a row; ``None`` otherwise.
    - ``placement``: ``"WAITING"`` / ``None``.
    - ``effects``: carrier string (the current worker ``attempt_id``
      when present and non-empty, else the ``responsibility_ref``) /
      ``None``.
    - ``observed_at``: the OLDEST parseable source observed_at, or
      ``None`` when no source has a parseable stamp (the caller
      already recorded the skip token).
    - ``evidence_ref``: ``validity.card.proof_ref`` when a non-empty
      string, else ``responsibility_ref``.

    Returns ``(None, skip_token)`` when the card is not eligible —
    the token is one of: ``unresolved_root``, ``ambiguous_root``,
    ``freshness_<value>``, ``not_actionable``, ``unqualified_validity``,
    ``no_source_observations``, ``effect_unknown_without_source``.
    """
    if raw.get("runtime_root_state") != "RESOLVED":
        return None, "unresolved_root"
    if raw.get("root_job_ambiguous") is not False:
        return None, "ambiguous_root"

    placement_state = raw.get("placement_state")
    placement_value = (placement_state.get("value")
                       if isinstance(placement_state, Mapping) else None)
    is_effect_unknown = placement_value == "EFFECT_UNKNOWN"

    freshness = raw.get("freshness")
    if freshness != "current":
        freshness_token = freshness if isinstance(freshness, str) else "unknown"
        return None, f"freshness_{freshness_token}"

    validity = raw.get("validity")
    card_validity = validity.get("card") if isinstance(validity, Mapping) else None
    is_validity_mapping = isinstance(card_validity, Mapping)
    valid_for_ms = card_validity.get("valid_for_ms") if is_validity_mapping else None
    proof_ref = card_validity.get("proof_ref") if is_validity_mapping else None
    sources = card_validity.get("sources") if is_validity_mapping else None

    # B1: EFFECT_UNKNOWN cards are exempted from ``is_actionable`` and
    # ``valid_for_ms`` gates — the projection itself de-presents
    # EFFECT_UNKNOWN cards; an exception must never be hidden by an
    # eligibility gate.  Every other producer (accountability,
    # placement) is subject to the full gate.
    if not is_effect_unknown:
        if raw.get("is_actionable") is not True:
            return None, "not_actionable"
        if not isinstance(valid_for_ms, int):
            return None, "unqualified_validity"

    if not isinstance(sources, list) or not sources:
        return None, ("effect_unknown_without_source" if is_effect_unknown
                      else "no_source_observations")

    # OLDEST parseable source observed_at — RFC3339 UTC sorts
    # lexicographically the same as chronologically.
    parsed_observed: list[str] = []
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        obs = source.get("observed_at")
        if not isinstance(obs, str):
            continue
        try:
            _parse_observed_at(obs)
        except ValueError:
            continue
        parsed_observed.append(obs)
    if not parsed_observed:
        return None, ("effect_unknown_without_source" if is_effect_unknown
                      else "no_source_observations")
    oldest_observed = min(parsed_observed)
    evidence_ref = proof_ref if isinstance(proof_ref, str) and proof_ref else responsibility_ref

    # Owed turn → accountability.
    owed_turn = raw.get("owed_turn")
    seat = owed_turn.get("seat") if isinstance(owed_turn, Mapping) else None
    reason = owed_turn.get("reason") if isinstance(owed_turn, Mapping) else None
    accountability_value: str | None = None
    accountability_skip_reason: str | None = None
    if seat == "ceo" and reason in _VALID_OWED_TURN_REASONS:
        accountability_value = "SOL"
    elif seat == "worker" and reason in _VALID_OWED_TURN_REASONS:
        accountability_value = "WORKER"
    else:
        seat_token = seat if isinstance(seat, str) else "missing"
        reason_token = reason if isinstance(reason, str) else "missing"
        accountability_skip_reason = f"owed_{seat_token}_{reason_token}"

    placement_value_emitted: str | None = None
    if placement_value == "WAITING_CAPACITY":
        placement_value_emitted = "WAITING"

    effects_carrier: str | None = None
    if is_effect_unknown:
        current_worker = raw.get("current_worker")
        attempt_id = (current_worker.get("attempt_id")
                      if isinstance(current_worker, Mapping) else None)
        if isinstance(attempt_id, str) and attempt_id:
            effects_carrier = attempt_id
        else:
            effects_carrier = responsibility_ref

    return ({
        "accountability": accountability_value,
        "accountability_skip_reason": accountability_skip_reason,
        "placement": placement_value_emitted,
        "effects": effects_carrier,
        "observed_at": oldest_observed,
        "evidence_ref": evidence_ref,
    }, None)


def _resolve_root(
    root_job_id: str,
    views: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None,
           dict[str, Any] | None, list[str]]:
    """Resolve per-producer conflicts for one root.

    For each producer independently: if all cards derive the same
    value (or all derive no value), keep the first card's value
    (``accountability``/``placement``/``effects`` fields of the
    first view).  If any disagreement on a producer, that producer
    emits NO row and a ``<root>:conflict_<producer>`` token is
    recorded.  Per-card accountability skip tokens (the
    ``accountability_skip_reason`` of each view) are recorded
    regardless of conflict state.

    When 2+ cards agree (no conflict tokens), record the
    ``<root>:duplicate_card`` token once.  Conflict roots do NOT
    record ``duplicate_card`` — the cards are not "agreeing
    duplicates".
    """
    skip_tokens: list[str] = []

    # Per-card accountability skip tokens are recorded regardless of
    # conflict state — they are the auditable reason each card did
    # or didn't produce a row.
    for view in views:
        if view["accountability_skip_reason"]:
            skip_tokens.append(f"{root_job_id}:{view['accountability_skip_reason']}")

    # Accountability conflict.
    distinct_acc = sorted({v["accountability"] for v in views
                           if v["accountability"] is not None})
    acc_row: dict[str, Any] | None = None
    if not distinct_acc:
        # All cards produced no accountability row — agreement on "no row".
        pass
    elif len(distinct_acc) > 1:
        skip_tokens.append(f"{root_job_id}:conflict_accountability")
    else:
        first = views[0]
        if first["accountability"] is not None:
            acc_row = {
                "next_actor": first["accountability"],
                "evidence_ref": first["evidence_ref"],
                "observed_at": first["observed_at"],
            }

    # Placement conflict — agreement counts only when both sides agree.
    placement_present = [v["placement"] is not None for v in views]
    pl_row: dict[str, Any] | None = None
    if any(placement_present) and not all(placement_present):
        skip_tokens.append(f"{root_job_id}:conflict_placement")
    elif all(placement_present):
        first = views[0]
        pl_row = {
            "state": first["placement"],
            "evidence_ref": first["evidence_ref"],
            "observed_at": first["observed_at"],
        }

    # Effects conflict — agreement requires the same carrier.
    distinct_eff = sorted({v["effects"] for v in views
                           if v["effects"] is not None})
    eff_row: dict[str, Any] | None = None
    if not distinct_eff:
        pass
    elif len(distinct_eff) > 1:
        skip_tokens.append(f"{root_job_id}:conflict_effects")
    else:
        first = views[0]
        eff_row = {
            "state": "EFFECT_UNKNOWN",
            "carrier": first["effects"],
            "evidence_ref": first["evidence_ref"],
            "observed_at": first["observed_at"],
        }

    # Agreeing duplicates → one ``duplicate_card`` token per root.
    if len(views) > 1 and not any(":conflict_" in t for t in skip_tokens):
        skip_tokens.append(f"{root_job_id}:duplicate_card")

    return acc_row, pl_row, eff_row, skip_tokens


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
    evidence_as_of: str | None = None,
    evidence_max_age_s: int = EVIDENCE_MAX_AGE_S,
) -> dict[str, Any]:
    """Pure: render the workspace work-queue from its named inputs only.

    The composer never reads the Runtime; it consumes only the
    ``mastermind.fabric_job_root_list.v2`` document passed in ``root_list``
    plus optional Agent OS evidence inputs and the optional control-room
    document for the queue-level ``effect_exception`` read.  When the
    caller supplies ``source_observation`` (the existing CCR-and-Runtime
    observation receipt), it is attached verbatim under that key.

    B3: ``evidence_as_of`` is REQUIRED when any producer (accountability,
    placement, effects) is supplied; ``observed_at`` values that are
    older than ``evidence_as_of - evidence_max_age_s`` or later than
    ``evidence_as_of`` are not admitted — the corresponding row falls
    back to the no-producer value with ``reason: "evidence_stale"``.
    Effects are the exception: a stale ``EFFECT_UNKNOWN`` STILL sticks
    (R4); staleness never clears a recorded exception.
    """
    validated_root = _validate_root_list(root_list)
    validated_accountability = _validate_accountability(accountability)
    validated_placement = _validate_placement(placement)
    validated_effects = _validate_effects(effects)
    evidence_anchor = _ensure_required_producers_evidence(
        accountability=validated_accountability,
        placement=validated_placement,
        effects=validated_effects,
        evidence_as_of=evidence_as_of,
    )
    lifecycle_source = _lifecycle_source(validated_root)
    effect_exception = _queue_effect_exception(control_room)
    _ensure_key_set(effect_exception, QUEUE_EFFECT_EXCEPTION_KEYS, label="queue effect_exception")
    document_generated_at = generated_at or _utc_now()

    if _lifecycle_unavailable(validated_root):
        unavailable = {
            "schema": WORK_QUEUE_SCHEMA,
            "generated_at": document_generated_at,
            "availability": "UNAVAILABLE",
            "lifecycle_source": lifecycle_source,
            "effect_exception": effect_exception,
            "coverage": _coverage_for_unavailable(validated_root),
            "groups": _empty_groups(),
            "source_observation": dict(source_observation) if isinstance(source_observation, Mapping) else None,
            "reason_codes": [_REASON_LIFECYCLE_UNAVAILABLE],
        }
        _ensure_key_set(unavailable, OUTPUT_KEYS, label="unavailable document")
        return unavailable

    groups = _empty_groups()
    for row in validated_root["roots"]:
        built = _row(
            str(row["job_id"]),
            row,
            accountability=validated_accountability,
            placement=validated_placement,
            effects=validated_effects,
            evidence_as_of=evidence_anchor,
            evidence_max_age_s=evidence_max_age_s,
        )
        groups[built["group"]].append(built)
    # Deterministic order: sort each group by root_job_id ascending.
    for key in _GROUP_ORDER:
        groups[key] = sorted(groups[key], key=lambda item: item["root_job_id"])

    # B3/N3: build the deterministic reason_codes list for the AVAILABLE
    # branch.  WQ-PROD-1 round 2: ``effect_not_row_attributed`` fires
    # whenever the queue-level EFFECT_UNKNOWN was observed by
    # ``_queue_effect_exception`` AND no rendered row carries
    # ``effect.value == "EFFECT_UNKNOWN"`` — coverage gap, regardless
    # of whether ``effects`` was supplied.  An empty ``effects`` map
    # whose root is not in the bounded root list still leaves the gap
    # (the code stays).  ``lifecycle_degraded`` fires when at least
    # one entry of the root list's degraded list matches a closed-set
    # degradation phrase (bounded acquisition unavailable, bounded
    # discovery truncation, generation CONFLICT).  Informational notes
    # (e.g. ``_ROOT_ENUMERATION_NOTE``) are echoed verbatim in
    # ``lifecycle_source.degraded`` but never contribute a reason
    # code.
    row_has_effect_unknown = any(
        row["effect"]["value"] == "EFFECT_UNKNOWN"
        for group_rows in groups.values() for row in group_rows
    )
    reason_codes: list[str] = []
    if (effect_exception.get("value") == "EFFECT_UNKNOWN"
            and not row_has_effect_unknown):
        reason_codes.append(_REASON_EFFECT_NOT_ROW_ATTRIBUTED)
    if any(_is_degradation_note(entry) for entry in validated_root.get("degraded") or []):
        reason_codes.append(_REASON_LIFECYCLE_DEGRADED)
    reason_codes.sort()

    document = {
        "schema": WORK_QUEUE_SCHEMA,
        "generated_at": document_generated_at,
        "availability": "AVAILABLE",
        "lifecycle_source": lifecycle_source,
        "effect_exception": effect_exception,
        "coverage": _coverage(validated_root),
        "groups": groups,
        "source_observation": dict(source_observation) if isinstance(source_observation, Mapping) else None,
        "reason_codes": reason_codes,
    }
    _ensure_key_set(document, OUTPUT_KEYS, label="document")
    _ensure_key_set(document["groups"], frozenset(_GROUP_ORDER), label="groups keys")
    return document


__all__ = [
    "WORK_QUEUE_SCHEMA",
    "OUTPUT_KEYS",
    "ROW_KEYS",
    "ACCEPTANCE_KEYS",
    "COVERAGE_KEYS",
    "EVIDENCE_MAX_AGE_S",
    "compose_work_queue_v1",
    "derive_work_producers_v1",
    "_DEGRADATION_NOTES",
    "_is_degradation_note",
    "_BOUNDED_UNAVAILABLE_NOTE",
    "_GENERATION_CONFLICT_NOTE",
    "_ROOT_ENUMERATION_NOTE",
]