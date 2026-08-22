"""Pure contract law for ``mastermind.executive_hot_state.v1``.

Both the control-plane producer and an integrations-layer consumer need the
same exact vocabulary and semantic validation without pulling Runtime or a
third-party transport SDK across the boundary.  This module is stdlib-only and
contains no I/O, discovery, state, cache, database, or lifecycle behavior.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

STATE_REQUEST_SCHEMA = "mastermind.executive_ceo_ingress_state.v1"
HOT_STATE_SCHEMA = "mastermind.executive_hot_state.v1"
BOOT_PACKET_SCHEMA = "mastermind.ceo_boot_packet.v1"
MAX_STATE_BYTES = 8192

JOB_STATUS_VALUES = (
    "QUEUED",
    "RUNNING",
    "CHECKPOINTED",
    "RATE_LIMITED",
    "FAILED",
    "LOST",
    "CANCEL_REQUESTED",
    "COMPLETED",
    "CANCELLED",
)
ATTEMPT_STATUS_VALUES = (
    "CLAIMED",
    "RUNNING",
    "CHECKPOINTED",
    "CANCEL_REQUESTED",
    "RATE_LIMITED",
    "FAILED",
    "LOST",
    "COMPLETED",
    "CANCELLED",
)
WORKER_STATUS_VALUES = (
    "AVAILABLE",
    "BUSY",
    "DRAINING",
    "RATE_LIMITED",
    "OFFLINE",
    "ERROR",
)

DEGRADATION_CODES = frozenset(
    {
        "GROUNDING_UNAVAILABLE",
        "SERVICE_STATE_UNKNOWN",
        "RUNTIME_JOBS_UNAVAILABLE",
        "RUNTIME_ATTEMPTS_UNAVAILABLE",
        "RUNTIME_WORKERS_UNAVAILABLE",
    }
)

_TOP_KEYS = frozenset(
    {
        "schema",
        "generated_at",
        "snapshot_hash",
        "grounding",
        "service",
        "generic_operator_mutations",
        "runtime",
        "degraded",
        "do_not_submit",
    }
)
_GROUNDING_KEYS = frozenset({"mastermind_sha", "macro_sha", "boot_packet_schema"})
_SERVICE_KEYS = frozenset({"service_state", "ceo_admission"})
_RUNTIME_KEYS = frozenset({"projection_state", "jobs", "attempts", "workers"})
_SUBPROJECTION_KEYS = frozenset({"total", "by_status"})
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA64_RE = re.compile(r"^[0-9a-f]{64}$")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def semantic_snapshot_hash(value: Mapping[str, Any]) -> str:
    semantic = dict(value)
    semantic.pop("generated_at", None)
    semantic.pop("snapshot_hash", None)
    return hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()


def _exact_keys(value: Any, expected: frozenset[str]) -> bool:
    return isinstance(value, Mapping) and set(value) == expected


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _valid_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_subprojection(value: Any, statuses: tuple[str, ...]) -> bool:
    if not _exact_keys(value, _SUBPROJECTION_KEYS):
        return False
    total = value["total"]
    by_status = value["by_status"]
    if not _valid_nonnegative_int(total):
        return False
    if not isinstance(by_status, Mapping) or set(by_status) != set(statuses):
        return False
    if any(not _valid_nonnegative_int(by_status[name]) for name in statuses):
        return False
    return sum(by_status[name] for name in statuses) == total


def validate_hot_state_document(value: Any) -> bool:
    """Return whether ``value`` is one exact, self-consistent R0 V1 document."""

    if not _exact_keys(value, _TOP_KEYS):
        return False
    if value["schema"] != HOT_STATE_SCHEMA or not _valid_timestamp(value["generated_at"]):
        return False
    if not isinstance(value["snapshot_hash"], str) or _SHA64_RE.fullmatch(
        value["snapshot_hash"]
    ) is None:
        return False

    grounding = value["grounding"]
    if not _exact_keys(grounding, _GROUNDING_KEYS):
        return False
    grounding_null = all(grounding[name] is None for name in _GROUNDING_KEYS)
    grounding_valid = (
        isinstance(grounding["mastermind_sha"], str)
        and _SHA40_RE.fullmatch(grounding["mastermind_sha"]) is not None
        and isinstance(grounding["macro_sha"], str)
        and _SHA40_RE.fullmatch(grounding["macro_sha"]) is not None
        and grounding["boot_packet_schema"] == BOOT_PACKET_SCHEMA
    )
    if not (grounding_null or grounding_valid):
        return False

    service = value["service"]
    if not _exact_keys(service, _SERVICE_KEYS):
        return False
    service_state = service["service_state"]
    ceo_admission = service["ceo_admission"]
    if service_state not in {"READY", "AWAITING_CANARY", "QUARANTINED", "UNKNOWN"}:
        return False
    if service_state == "QUARANTINED":
        valid_admission = ceo_admission == "BLOCKED_QUARANTINED"
    elif service_state == "UNKNOWN":
        valid_admission = ceo_admission == "BLOCKED_UNSAFE_STATE"
    else:
        valid_admission = ceo_admission in {"READY", "UNARMED"}
    if not valid_admission:
        return False
    expected_operator = {
        "READY": "AVAILABLE",
        "AWAITING_CANARY": "BLOCKED_AWAITING_CANARY",
        "QUARANTINED": "BLOCKED_QUARANTINED",
        "UNKNOWN": "UNKNOWN",
    }[service_state]
    if value["generic_operator_mutations"] != expected_operator:
        return False

    runtime = value["runtime"]
    if not _exact_keys(runtime, _RUNTIME_KEYS):
        return False
    statuses_by_name = {
        "jobs": JOB_STATUS_VALUES,
        "attempts": ATTEMPT_STATUS_VALUES,
        "workers": WORKER_STATUS_VALUES,
    }
    available = 0
    for name, statuses in statuses_by_name.items():
        projection = runtime[name]
        if projection is not None:
            if not _valid_subprojection(projection, statuses):
                return False
            available += 1
    expected_projection_state = (
        "OK" if available == 3 else "UNAVAILABLE" if available == 0 else "DEGRADED"
    )
    if runtime["projection_state"] != expected_projection_state:
        return False

    degraded = value["degraded"]
    if (
        not isinstance(degraded, list)
        or any(not isinstance(item, str) for item in degraded)
        or degraded != sorted(set(degraded))
        or not set(degraded).issubset(DEGRADATION_CODES)
    ):
        return False
    expected_degradation_presence = {
        "GROUNDING_UNAVAILABLE": grounding_null,
        "SERVICE_STATE_UNKNOWN": service_state == "UNKNOWN",
        "RUNTIME_JOBS_UNAVAILABLE": runtime["jobs"] is None,
        "RUNTIME_ATTEMPTS_UNAVAILABLE": runtime["attempts"] is None,
        "RUNTIME_WORKERS_UNAVAILABLE": runtime["workers"] is None,
    }
    if any(
        (code in degraded) != expected
        for code, expected in expected_degradation_presence.items()
    ):
        return False

    do_not_submit = value["do_not_submit"]
    if not isinstance(do_not_submit, bool):
        return False
    expected_do_not_submit = not (
        grounding_valid
        and service_state in {"READY", "AWAITING_CANARY"}
        and ceo_admission == "READY"
        and runtime["projection_state"] == "OK"
        and not degraded
    )
    if do_not_submit is not expected_do_not_submit:
        return False

    try:
        if semantic_snapshot_hash(value) != value["snapshot_hash"]:
            return False
        if len(canonical_json_bytes(value)) > MAX_STATE_BYTES:
            return False
    except (TypeError, ValueError):
        return False
    return True
