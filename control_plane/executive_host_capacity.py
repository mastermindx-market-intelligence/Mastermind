"""Closed, read-only host-capacity evidence contract.

The contract binds an already validated HP0 snapshot by digest and copied
normalized facts.  It contains no capacity state, ranking, admission, resource
reservation, or Runtime authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from control_plane.executive_host_pressure import (
    BOOT_REF_RE,
    HOST_REF_RE,
    INT64_MAX,
    HostPressureContractError,
    canonical_host_pressure_json,
    validate_host_pressure_snapshot,
)


SNAPSHOT_SCHEMA = "mastermind.host_capacity_snapshot/v1"
MAX_SAMPLE_WINDOW_MS = 10_000
MAX_TOTAL_OBSERVATION_WINDOW_MS = 3_600_000
MAX_SNAPSHOT_BYTES = 32_768
CAPACITY_POOL_REF_RE = re.compile(r"^capacity-pool-[0-9a-f]{64}$")
HP0_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

MEMORY_GROUP_FIELDS = (
    "physical_memory_bytes",
    "vm_page_size_bytes",
    "vm_free_pages",
    "vm_inactive_pages",
    "vm_speculative_pages",
    "vm_compressed_pages",
)
SWAP_GROUP_FIELDS = ("swap_total_bytes", "swap_used_bytes")
POOL_GROUP_FIELDS = ("pool_total_bytes", "pool_free_bytes")
HP0_FACT_FIELDS = (
    "hp0_observed_at_ms",
    "hp0_sample_window_ms",
    "logical_cpu_count",
    "load1_milli",
    "load_ratio_milli",
    "hp0_telemetry_status",
)
SNAPSHOT_FIELDS = frozenset(
    {
        "schema",
        "host_ref",
        "boot_ref",
        "observed_at_ms",
        "sample_window_ms",
        "total_observation_window_ms",
        "capacity_pool_ref",
        "hp0_sha256",
        *HP0_FACT_FIELDS,
        *MEMORY_GROUP_FIELDS,
        *SWAP_GROUP_FIELDS,
        *POOL_GROUP_FIELDS,
        "telemetry_status",
        "unknown_fields",
    }
)
UNKNOWNABLE_FIELDS = tuple(
    sorted((*MEMORY_GROUP_FIELDS, *SWAP_GROUP_FIELDS, *POOL_GROUP_FIELDS))
)
_TELEMETRY_STATUSES = frozenset({"COMPLETE", "PARTIAL"})


class HostCapacityContractError(ValueError):
    """A closed, non-secret host-capacity contract refusal."""


def _refuse(code: str) -> None:
    raise HostCapacityContractError(code)


def _integer(
    value: Any,
    *,
    code: str,
    minimum: int = 0,
    maximum: int = INT64_MAX,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _refuse(code)
    return value


def _reference(value: Any, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _refuse("REFERENCE_INVALID")
    return value


def hp0_digest(value: Mapping[str, Any]) -> str:
    """Return the canonical SHA-256 digest for a valid HP0 snapshot."""

    try:
        normalized = validate_host_pressure_snapshot(value)
        rendered = canonical_host_pressure_json(normalized)
    except HostPressureContractError as exc:
        raise HostCapacityContractError("HP0_SNAPSHOT_INVALID") from exc
    return hashlib.sha256(rendered).hexdigest()


def validate_hp0_binding(
    value: Mapping[str, Any], host_ref: str, boot_ref: str
) -> dict[str, Any]:
    """Validate HP0 and extract its exact identity-bound normalized facts."""

    try:
        normalized = validate_host_pressure_snapshot(value)
    except HostPressureContractError as exc:
        raise HostCapacityContractError("HP0_SNAPSHOT_INVALID") from exc
    if normalized["host_ref"] != host_ref or normalized["boot_ref"] != boot_ref:
        _refuse("HP0_REFERENCE_MISMATCH")
    return {
        "hp0_sha256": hp0_digest(normalized),
        "hp0_observed_at_ms": normalized["observed_at_ms"],
        "hp0_sample_window_ms": normalized["sample_window_ms"],
        "logical_cpu_count": normalized["logical_cpu_count"],
        "load1_milli": normalized["load1_milli"],
        "load_ratio_milli": normalized["load_ratio_milli"],
        "hp0_telemetry_status": normalized["telemetry_status"],
    }


def validate_host_capacity_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a defensive canonical-value copy or refuse the closed contract."""

    if not isinstance(value, Mapping) or set(value) != SNAPSHOT_FIELDS:
        _refuse("SNAPSHOT_FIELDS_INVALID")
    if value.get("schema") != SNAPSHOT_SCHEMA:
        _refuse("SNAPSHOT_SCHEMA_INVALID")

    host_ref = _reference(value.get("host_ref"), HOST_REF_RE)
    boot_ref = _reference(value.get("boot_ref"), BOOT_REF_RE)
    capacity_pool_ref = _reference(
        value.get("capacity_pool_ref"), CAPACITY_POOL_REF_RE
    )
    observed_at_ms = _integer(
        value.get("observed_at_ms"),
        code="OBSERVED_AT_INVALID",
        minimum=1,
    )
    sample_window_ms = _integer(
        value.get("sample_window_ms"),
        code="SAMPLE_WINDOW_INVALID",
        minimum=1,
        maximum=MAX_SAMPLE_WINDOW_MS,
    )
    total_observation_window_ms = _integer(
        value.get("total_observation_window_ms"),
        code="TOTAL_OBSERVATION_WINDOW_INVALID",
        minimum=1,
        maximum=MAX_TOTAL_OBSERVATION_WINDOW_MS,
    )
    if total_observation_window_ms < sample_window_ms:
        _refuse("TOTAL_WINDOW_MISMATCH")
    if type(value.get("hp0_sha256")) is not str or HP0_SHA256_RE.fullmatch(
        value["hp0_sha256"]
    ) is None:
        _refuse("HP0_DIGEST_INVALID")

    hp0_observed_at_ms = _integer(
        value.get("hp0_observed_at_ms"),
        code="HP0_FACT_INVALID",
        minimum=1,
    )
    hp0_sample_window_ms = _integer(
        value.get("hp0_sample_window_ms"),
        code="HP0_FACT_INVALID",
        minimum=1,
        maximum=5_000,
    )
    hp0_start_ms = hp0_observed_at_ms - hp0_sample_window_ms
    expected_total_observation_window_ms = observed_at_ms - hp0_start_ms
    if total_observation_window_ms != expected_total_observation_window_ms:
        _refuse("TOTAL_WINDOW_MISMATCH")
    logical_cpu_count = _integer(
        value.get("logical_cpu_count"),
        code="HP0_FACT_INVALID",
        minimum=1,
        maximum=4_096,
    )
    load1_milli = _integer(
        value.get("load1_milli"), code="HP0_FACT_INVALID"
    )
    load_ratio_milli = _integer(
        value.get("load_ratio_milli"), code="HP0_FACT_INVALID"
    )
    if load_ratio_milli != load1_milli // logical_cpu_count:
        _refuse("HP0_FACT_INVALID")
    if value.get("hp0_telemetry_status") not in {"COMPLETE", "PARTIAL"}:
        _refuse("HP0_FACT_INVALID")

    unknown_fields = value.get("unknown_fields")
    if (
        type(unknown_fields) is not list
        or unknown_fields != sorted(set(unknown_fields))
        or any(field not in UNKNOWNABLE_FIELDS for field in unknown_fields)
    ):
        _refuse("UNKNOWN_FIELDS_INVALID")
    observed_unknowns: list[str] = []
    normalized_metrics: dict[str, int | None] = {}
    for field in UNKNOWNABLE_FIELDS:
        field_value = value.get(field)
        if field_value is None:
            normalized_metrics[field] = None
            observed_unknowns.append(field)
            continue
        code = (
            "MEMORY_METRIC_INVALID"
            if field in MEMORY_GROUP_FIELDS
            else "SWAP_METRIC_INVALID"
            if field in SWAP_GROUP_FIELDS
            else "POOL_METRIC_INVALID"
        )
        minimum = 1 if field == "physical_memory_bytes" else 0
        if field == "vm_page_size_bytes":
            minimum = 1
        normalized_metrics[field] = _integer(
            field_value, code=code, minimum=minimum
        )
    if unknown_fields != observed_unknowns:
        _refuse("UNKNOWN_FIELDS_MISMATCH")

    swap_total = normalized_metrics["swap_total_bytes"]
    swap_used = normalized_metrics["swap_used_bytes"]
    if swap_total is not None and swap_used is not None and swap_used > swap_total:
        _refuse("SWAP_PAIR_INVALID")
    pool_total = normalized_metrics["pool_total_bytes"]
    pool_free = normalized_metrics["pool_free_bytes"]
    if pool_total is not None and pool_free is not None and pool_free > pool_total:
        _refuse("POOL_PAIR_INVALID")

    telemetry_status = value.get("telemetry_status")
    if telemetry_status not in _TELEMETRY_STATUSES:
        _refuse("TELEMETRY_STATUS_INVALID")
    expected_status = "PARTIAL" if unknown_fields else "COMPLETE"
    if telemetry_status != expected_status:
        _refuse("TELEMETRY_STATUS_MISMATCH")

    return {
        "schema": SNAPSHOT_SCHEMA,
        "host_ref": host_ref,
        "boot_ref": boot_ref,
        "observed_at_ms": observed_at_ms,
        "sample_window_ms": sample_window_ms,
        "total_observation_window_ms": total_observation_window_ms,
        "capacity_pool_ref": capacity_pool_ref,
        "hp0_sha256": value["hp0_sha256"],
        "hp0_observed_at_ms": hp0_observed_at_ms,
        "hp0_sample_window_ms": hp0_sample_window_ms,
        "logical_cpu_count": logical_cpu_count,
        "load1_milli": load1_milli,
        "load_ratio_milli": load_ratio_milli,
        "hp0_telemetry_status": value["hp0_telemetry_status"],
        **normalized_metrics,
        "telemetry_status": telemetry_status,
        "unknown_fields": list(unknown_fields),
    }


def canonical_host_capacity_json(value: Mapping[str, Any]) -> bytes:
    """Render one validated snapshot as bounded canonical UTF-8 JSON."""

    normalized = validate_host_capacity_snapshot(value)
    try:
        rendered = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise HostCapacityContractError("SNAPSHOT_JSON_INVALID") from exc
    payload = (rendered + "\n").encode("ascii")
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise HostCapacityContractError("SNAPSHOT_TOO_LARGE")
    return payload


__all__ = [
    "BOOT_REF_RE",
    "CAPACITY_POOL_REF_RE",
    "HOST_REF_RE",
    "HP0_FACT_FIELDS",
    "INT64_MAX",
    "MAX_SAMPLE_WINDOW_MS",
    "MAX_SNAPSHOT_BYTES",
    "MAX_TOTAL_OBSERVATION_WINDOW_MS",
    "MEMORY_GROUP_FIELDS",
    "POOL_GROUP_FIELDS",
    "SNAPSHOT_FIELDS",
    "SNAPSHOT_SCHEMA",
    "SWAP_GROUP_FIELDS",
    "UNKNOWNABLE_FIELDS",
    "HostCapacityContractError",
    "canonical_host_capacity_json",
    "hp0_digest",
    "validate_hp0_binding",
    "validate_host_capacity_snapshot",
]


# Additive Linux observation wire. The v1 admission owner above is unchanged.
# COMPLETE here means complete for the named observation profile, NOT schedulable.
NATIVE_SNAPSHOT_SCHEMA = "mastermind.host_capacity_snapshot/v2"
NATIVE_OBSERVATION_PROFILE = "linux-native-observation/v1"
NATIVE_MAX_WINDOW_MS = 5_000
_NATIVE_BINDING_KEYS = frozenset({
    "host_ref", "boot_ref", "capacity_pool_ref", "source_generation_sha256",
    "execution_scope_sha256", "namespace_sha256", "ancestry_sha256",
})
_NATIVE_SCOPE_KEYS = frozenset({
    "kind", "execution_scope_sha256", "namespace_sha256", "ancestry_sha256",
})
_NATIVE_FIELDS = frozenset({
    "schema", "platform", "observation_profile", "host_ref", "boot_ref",
    "capacity_pool_ref", "source_generation_sha256", "scope", "observed_at_ms",
    "sample_window_ms", "total_observation_window_ms", "metrics",
    "telemetry_status", "unknown_fields",
})
_NATIVE_NA = frozenset({
    "darwin_vm_counters", "darwin_fseventsd", "host_cpu_full_pressure",
})
_NATIVE_REASONS = frozenset({
    "MISSING", "PERMISSION_DENIED", "TIMEOUT", "MALFORMED", "OVERFLOW",
    "SOURCE_MOVED", "BOOT_DRIFT", "STALE", "FUTURE", "WINDOW_INVALID",
    "COUNTER_REGRESSION", "NO_COUNTER_DELTA", "NOT_SUPPORTED",
    "SCOPE_UNQUALIFIED", "MOUNT_MISMATCH",
})
_NATIVE_UNITS = {
    "host_usable_memory_bytes": "bytes_usable",
    "host_available_memory_estimate_bytes": "bytes_estimate",
    "host_swap_total_bytes": "bytes",
    "host_swap_used_bytes": "bytes",
    "host_cpu_busy_milli_pct": "milli_percent",
    "host_logical_cpu_count": "logical_cpus",
    "effective_cpu_capacity_millicores": "millicores_ceiling",
    "effective_memory_headroom_estimate_bytes": "bytes_estimate",
    "disk_usable_bytes": "bytes_unprivileged",
    "pool_total_bytes": "bytes",
    "darwin_vm_counters": "not_applicable",
    "darwin_fseventsd": "not_applicable",
    "host_cpu_full_pressure": "not_applicable",
    "pswpin_pages_delta": "pages_delta",
    "pswpout_pages_delta": "pages_delta",
    **{
        f"{resource}_{kind}_{metric}": (
            "microseconds" if metric == "total" else "milli_percent"
        )
        for resource in ("cpu", "memory", "io")
        for kind in (("some",) if resource == "cpu" else ("some", "full"))
        for metric in ("avg10", "avg60", "avg300", "total")
    },
}


def _native_object(value: Any, keys: frozenset[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        _refuse("NATIVE_FIELDS_INVALID")
    return value


def _native_binding(value: Any) -> dict[str, str]:
    source = _native_object(value, _NATIVE_BINDING_KEYS)
    patterns = {
        "host_ref": HOST_REF_RE,
        "boot_ref": BOOT_REF_RE,
        "capacity_pool_ref": CAPACITY_POOL_REF_RE,
    }
    return {
        key: _reference(source[key], patterns.get(key, HP0_SHA256_RE))
        for key in sorted(_NATIVE_BINDING_KEYS)
    }


def _native_metrics(value: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
    source = _native_object(value, frozenset(_NATIVE_UNITS))
    normalized: dict[str, dict[str, Any]] = {}
    unknown: list[str] = []
    for name in sorted(_NATIVE_UNITS):
        metric = _native_object(source[name], frozenset({"value", "null_reason"}))
        number, reason = metric["value"], metric["null_reason"]
        if name in _NATIVE_NA:
            if number is not None or reason != "NOT_APPLICABLE":
                _refuse("NATIVE_APPLICABILITY_INVALID")
        elif number is None:
            if type(reason) is not str or reason not in _NATIVE_REASONS:
                _refuse("NATIVE_NULL_REASON_INVALID")
            unknown.append(name)
        else:
            if reason is not None:
                _refuse("NATIVE_NULL_REASON_INVALID")
            minimum = 1 if name in {"host_usable_memory_bytes", "host_logical_cpu_count"} else 0
            maximum = INT64_MAX
            if name == "host_logical_cpu_count":
                maximum = 4096
            elif _NATIVE_UNITS[name] == "milli_percent":
                maximum = 100_000
            number = _integer(number, code="NATIVE_METRIC_INVALID", minimum=minimum, maximum=maximum)
        normalized[name] = {"value": number, "null_reason": reason}

    def bounded_pair(lower: str, upper: str, factor: int = 1) -> None:
        a, b = normalized[lower]["value"], normalized[upper]["value"]
        if a is not None and b is not None and a > b * factor:
            _refuse("NATIVE_METRIC_PAIR_INVALID")

    bounded_pair("host_available_memory_estimate_bytes", "host_usable_memory_bytes")
    bounded_pair("effective_memory_headroom_estimate_bytes", "host_available_memory_estimate_bytes")
    bounded_pair("effective_cpu_capacity_millicores", "host_logical_cpu_count", 1000)
    bounded_pair("host_swap_used_bytes", "host_swap_total_bytes")
    bounded_pair("disk_usable_bytes", "pool_total_bytes")
    return normalized, unknown


def validate_native_host_capacity_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a Linux observation; never normalize it into v1 admission evidence.

    Owner references are syntactically validated, not authenticated by this pure
    function. Capture, enrollment and the consuming reader retain that boundary.
    """
    source = _native_object(value, _NATIVE_FIELDS)
    if (source["schema"] != NATIVE_SNAPSHOT_SCHEMA or source["platform"] != "linux"
            or source["observation_profile"] != NATIVE_OBSERVATION_PROFILE):
        _refuse("NATIVE_SCHEMA_INVALID")
    scope = _native_object(source["scope"], _NATIVE_SCOPE_KEYS)
    if scope["kind"] != "cgroup-v2":
        _refuse("NATIVE_SCOPE_INVALID")
    binding = _native_binding({
        **{key: source[key] for key in ("host_ref", "boot_ref", "capacity_pool_ref", "source_generation_sha256")},
        **{key: scope[key] for key in _NATIVE_SCOPE_KEYS if key != "kind"},
    })
    observed = _integer(source["observed_at_ms"], code="NATIVE_WINDOW_INVALID")
    sample = _integer(source["sample_window_ms"], code="NATIVE_WINDOW_INVALID", minimum=1, maximum=NATIVE_MAX_WINDOW_MS)
    span = _integer(source["total_observation_window_ms"], code="NATIVE_WINDOW_INVALID", minimum=sample, maximum=NATIVE_MAX_WINDOW_MS)
    if observed < span:
        _refuse("NATIVE_WINDOW_INVALID")
    metrics, unknown = _native_metrics(source["metrics"])
    supplied_unknown = source["unknown_fields"]
    if type(supplied_unknown) is not list or supplied_unknown != unknown:
        _refuse("NATIVE_UNKNOWN_FIELDS_INVALID")
    expected_status = "PARTIAL" if unknown else "COMPLETE"
    if source["telemetry_status"] != expected_status:
        _refuse("NATIVE_TELEMETRY_STATUS_INVALID")
    return {
        "schema": NATIVE_SNAPSHOT_SCHEMA,
        "platform": "linux",
        "observation_profile": NATIVE_OBSERVATION_PROFILE,
        **{key: binding[key] for key in ("host_ref", "boot_ref", "capacity_pool_ref", "source_generation_sha256")},
        "scope": {"kind": "cgroup-v2", **{key: binding[key] for key in sorted(_NATIVE_SCOPE_KEYS - {"kind"})}},
        "observed_at_ms": observed,
        "sample_window_ms": sample,
        "total_observation_window_ms": span,
        "metrics": metrics,
        "telemetry_status": expected_status,
        "unknown_fields": list(unknown),
    }


def build_native_host_capacity_snapshot(
    metrics: Mapping[str, Any], *, binding: Mapping[str, Any],
    observed_at_ms: int, sample_window_ms: int, total_observation_window_ms: int,
) -> dict[str, Any]:
    """Seal the structural envelope over already-captured native metric pairs.

    No host read, identity minting, signature, freshness clock, placement or
    Runtime effect occurs. Caller is the trusted capture composition, not a model.
    The unchanged Linux arithmetic producer may remain standard-library-only.
    """
    bound = _native_binding(binding)
    values, unknown = _native_metrics(metrics)
    return validate_native_host_capacity_snapshot({
        "schema": NATIVE_SNAPSHOT_SCHEMA, "platform": "linux",
        "observation_profile": NATIVE_OBSERVATION_PROFILE,
        **{key: bound[key] for key in ("host_ref", "boot_ref", "capacity_pool_ref", "source_generation_sha256")},
        "scope": {"kind": "cgroup-v2", **{key: bound[key] for key in _NATIVE_SCOPE_KEYS if key != "kind"}},
        "observed_at_ms": observed_at_ms, "sample_window_ms": sample_window_ms,
        "total_observation_window_ms": total_observation_window_ms,
        "metrics": values, "unknown_fields": unknown,
        "telemetry_status": "PARTIAL" if unknown else "COMPLETE",
    })


def canonical_native_host_capacity_json(value: Mapping[str, Any]) -> bytes:
    normalized = validate_native_host_capacity_snapshot(value)
    payload = (json.dumps(normalized, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
    if len(payload) > MAX_SNAPSHOT_BYTES:
        _refuse("NATIVE_SNAPSHOT_TOO_LARGE")
    return payload


def project_native_host_capacity(
    value: Mapping[str, Any], *, expected_binding: Mapping[str, Any],
    now_ms: int, max_age_ms: int,
) -> dict[str, Any]:
    """Bounded reader composition with owner-supplied identity and clock policy.

    The caller must authenticate capture and expected_binding independently;
    digest equality is integrity evidence, never origin or execution authority.
    COMPLETE observations still do not authorize placement or physical BEGIN.
    """
    snapshot = validate_native_host_capacity_snapshot(value)
    expected = _native_binding(expected_binding)
    actual = {
        **{key: snapshot[key] for key in ("host_ref", "boot_ref", "capacity_pool_ref", "source_generation_sha256")},
        **{key: snapshot["scope"][key] for key in _NATIVE_SCOPE_KEYS if key != "kind"},
    }
    if actual != expected:
        _refuse("NATIVE_BINDING_MISMATCH")
    now = _integer(now_ms, code="NATIVE_CLOCK_INVALID")
    age = _integer(max_age_ms, code="NATIVE_CLOCK_INVALID", minimum=1)
    if snapshot["observed_at_ms"] > now:
        _refuse("NATIVE_FUTURE_DATED")
    start = snapshot["observed_at_ms"] - snapshot["total_observation_window_ms"]
    if now - start > age:
        _refuse("NATIVE_STALE")
    return {
        "schema": "mastermind.native_host_capacity_read/v1",
        **expected,
        "platform": snapshot["platform"],
        "observation_profile": snapshot["observation_profile"],
        "observed_at_ms": snapshot["observed_at_ms"],
        "sample_window_ms": snapshot["sample_window_ms"],
        "total_observation_window_ms": snapshot["total_observation_window_ms"],
        "snapshot_sha256": hashlib.sha256(canonical_native_host_capacity_json(snapshot)).hexdigest(),
        "metrics": {key: {**metric, "unit": _NATIVE_UNITS[key]} for key, metric in snapshot["metrics"].items()},
        "telemetry_status": snapshot["telemetry_status"],
        "unknown_fields": list(snapshot["unknown_fields"]),
        "capability": "OBSERVATION_ONLY",
        "admission_state": "NOT_EVALUATED",
        "can_place_work": False,
    }


__all__ += [
    "NATIVE_SNAPSHOT_SCHEMA", "NATIVE_OBSERVATION_PROFILE",
    "build_native_host_capacity_snapshot", "validate_native_host_capacity_snapshot",
    "canonical_native_host_capacity_json", "project_native_host_capacity",
]
