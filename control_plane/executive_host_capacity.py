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
