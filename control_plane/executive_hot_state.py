"""Transport-neutral Executive hot-state projection for MAS-108 / B1.

The projector is deliberately a read-only view over one already-open
``Runtime`` plus the already-injected PR-A trusted-grounding provider.  It owns
no socket, database connection, cache, cursor, lifecycle state, or discovery
path.  In particular it never reads the CEO boot packet, Agent OS, GitHub,
Slack, Linear, subprocess output, or raw SQLite.

R0 source law:
``research/EXECUTIVE_OS_CEO_INGRESS_STATE_R0_AUTHORIZATION_2026-08-21.md``.
"""
from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from common.executive_hot_state_contract import (
    ATTEMPT_STATUS_VALUES,
    BOOT_PACKET_SCHEMA,
    DEGRADATION_CODES,
    HOT_STATE_SCHEMA,
    JOB_STATUS_VALUES,
    MAX_STATE_BYTES,
    STATE_REQUEST_SCHEMA,
    WORKER_STATUS_VALUES,
    canonical_json_bytes,
    semantic_snapshot_hash,
    validate_hot_state_document,
)

__all__ = [
    "BOOT_PACKET_SCHEMA",
    "DEGRADATION_CODES",
    "HOT_STATE_SCHEMA",
    "HotStateTooLarge",
    "JOB_STATUS_VALUES",
    "ATTEMPT_STATUS_VALUES",
    "MAX_STATE_BYTES",
    "STATE_REQUEST_SCHEMA",
    "WORKER_STATUS_VALUES",
    "build_hot_state",
    "canonical_json_bytes",
]


_GROUNDING_KEYS = frozenset({"mastermind_sha", "macro_sha", "boot_packet_schema"})
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class _GroundingProvider(Protocol):
    def observe(self) -> Mapping[str, str]: ...


class HotStateTooLarge(RuntimeError):
    """The exact semantic V1 document exceeds its fail-closed source bound."""


def _utc_seconds(value: datetime | None) -> str:
    observed = value if value is not None else datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    observed = observed.astimezone(timezone.utc).replace(microsecond=0)
    return observed.strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_grounding(value: Any) -> dict[str, str] | None:
    if not isinstance(value, Mapping) or set(value) != _GROUNDING_KEYS:
        return None
    mastermind_sha = value.get("mastermind_sha")
    macro_sha = value.get("macro_sha")
    boot_packet_schema = value.get("boot_packet_schema")
    if not isinstance(mastermind_sha, str) or _SHA_RE.fullmatch(mastermind_sha) is None:
        return None
    if not isinstance(macro_sha, str) or _SHA_RE.fullmatch(macro_sha) is None:
        return None
    if boot_packet_schema != BOOT_PACKET_SCHEMA:
        return None
    return {
        "mastermind_sha": mastermind_sha,
        "macro_sha": macro_sha,
        "boot_packet_schema": BOOT_PACKET_SCHEMA,
    }


async def _project_grounding(
    provider: _GroundingProvider,
) -> tuple[dict[str, str | None], bool]:
    try:
        raw = await asyncio.to_thread(provider.observe)
    except Exception:
        raw = None
    grounding = _coerce_grounding(raw)
    if grounding is not None:
        return grounding, True
    return {
        "mastermind_sha": None,
        "macro_sha": None,
        "boot_packet_schema": None,
    }, False


def _status_value(value: Any) -> str | None:
    if isinstance(value, Enum):
        value = value.value
    return value if isinstance(value, str) else None


async def _project_registry(
    list_records: Any,
    status_values: Sequence[str],
) -> dict[str, Any] | None:
    try:
        records = await asyncio.to_thread(list_records)
        if not isinstance(records, list):
            return None
        counts = {status: 0 for status in status_values}
        for record in records:
            status = _status_value(getattr(record, "status", None))
            if status not in counts:
                return None
            counts[status] += 1
        if sum(counts.values()) != len(records):
            return None
        return {"total": len(records), "by_status": counts}
    except Exception:
        return None


def _normalise_service_state(raw: Any) -> tuple[str, bool]:
    if raw in {"READY", "AWAITING_CANARY", "QUARANTINED"}:
        return str(raw), True
    return "UNKNOWN", False


def _service_projection(raw: Any, *, ceo_ingress_armed: bool) -> tuple[dict[str, str], str]:
    service_state, known = _normalise_service_state(raw)
    if service_state == "QUARANTINED":
        admission = "BLOCKED_QUARANTINED"
    elif not known:
        admission = "BLOCKED_UNSAFE_STATE"
    elif ceo_ingress_armed is not True:
        admission = "UNARMED"
    else:
        admission = "READY"

    generic_operator = {
        "READY": "AVAILABLE",
        "AWAITING_CANARY": "BLOCKED_AWAITING_CANARY",
        "QUARANTINED": "BLOCKED_QUARANTINED",
        "UNKNOWN": "UNKNOWN",
    }[service_state]
    return {
        "service_state": service_state,
        "ceo_admission": admission,
    }, generic_operator


async def build_hot_state(
    *,
    runtime: Any,
    grounding_provider: _GroundingProvider,
    service_state: Any,
    ceo_ingress_armed: bool,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build one exact ``mastermind.executive_hot_state.v1`` snapshot.

    Registry projections are intentionally independent: one failed typed read
    becomes ``null`` plus its fixed degradation code while the other current
    values remain usable.  No prior snapshot is accepted as input, so stale
    success values cannot be laundered into a new response.
    """

    degraded: list[str] = []

    grounding, grounding_available = await _project_grounding(grounding_provider)
    if not grounding_available:
        degraded.append("GROUNDING_UNAVAILABLE")

    service, generic_operator = _service_projection(
        service_state, ceo_ingress_armed=ceo_ingress_armed
    )
    if service["service_state"] == "UNKNOWN":
        degraded.append("SERVICE_STATE_UNKNOWN")

    jobs, attempts, workers = await asyncio.gather(
        _project_registry(runtime.jobs.list_jobs, JOB_STATUS_VALUES),
        _project_registry(runtime.attempts.list_attempts, ATTEMPT_STATUS_VALUES),
        _project_registry(runtime.workers.list_workers, WORKER_STATUS_VALUES),
    )
    for projection, code in (
        (jobs, "RUNTIME_JOBS_UNAVAILABLE"),
        (attempts, "RUNTIME_ATTEMPTS_UNAVAILABLE"),
        (workers, "RUNTIME_WORKERS_UNAVAILABLE"),
    ):
        if projection is None:
            degraded.append(code)

    available_count = sum(item is not None for item in (jobs, attempts, workers))
    projection_state = (
        "OK" if available_count == 3 else "UNAVAILABLE" if available_count == 0 else "DEGRADED"
    )
    degraded = sorted(set(degraded))
    if not set(degraded).issubset(DEGRADATION_CODES):  # defensive closed-vocabulary fence
        raise RuntimeError("hot-state degradation vocabulary widened")

    semantic: dict[str, Any] = {
        "schema": HOT_STATE_SCHEMA,
        "grounding": grounding,
        "service": service,
        "generic_operator_mutations": generic_operator,
        "runtime": {
            "projection_state": projection_state,
            "jobs": jobs,
            "attempts": attempts,
            "workers": workers,
        },
        "degraded": degraded,
        "do_not_submit": not (
            grounding_available
            and service["service_state"] in {"READY", "AWAITING_CANARY"}
            and service["ceo_admission"] == "READY"
            and projection_state == "OK"
            and not degraded
        ),
    }
    snapshot_hash = semantic_snapshot_hash(semantic)
    result = {
        "schema": HOT_STATE_SCHEMA,
        "generated_at": _utc_seconds(generated_at),
        "snapshot_hash": snapshot_hash,
        "grounding": grounding,
        "service": service,
        "generic_operator_mutations": generic_operator,
        "runtime": semantic["runtime"],
        "degraded": degraded,
        "do_not_submit": semantic["do_not_submit"],
    }
    if len(canonical_json_bytes(result)) > MAX_STATE_BYTES:
        raise HotStateTooLarge("Executive hot-state exceeds the 8,192-byte source limit")
    if not validate_hot_state_document(result):
        raise RuntimeError("Executive hot-state contract validation failed")
    return result
