"""Closed, read-only host-pressure evidence contract.

This module validates and renders one bounded observation.  It does not sample
hosts, classify capacity, reserve resources, mutate Runtime state, or infer
process ownership.  Those responsibilities remain with their existing owners.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


SNAPSHOT_SCHEMA = "mastermind.host_pressure_snapshot/v1"
INT64_MAX = (1 << 63) - 1
MAX_SAMPLE_WINDOW_MS = 5_000
HOST_REF_RE = re.compile(r"^host-[0-9a-f]{64}$")
BOOT_REF_RE = re.compile(r"^boot-[0-9a-f]{64}$")
SNAPSHOT_FIELDS = frozenset(
    {
        "schema",
        "host_ref",
        "boot_ref",
        "observed_at_ms",
        "sample_window_ms",
        "logical_cpu_count",
        "load1_milli",
        "load_ratio_milli",
        "fseventsd_process_count",
        "fseventsd_cpu_milli_pct",
        "fseventsd_rss_bytes",
        "telemetry_status",
        "unknown_fields",
    }
)
_UNKNOWNABLE_FIELDS = (
    "fseventsd_cpu_milli_pct",
    "fseventsd_rss_bytes",
)
_TELEMETRY_STATUSES = frozenset({"COMPLETE", "PARTIAL"})


class HostPressureContractError(ValueError):
    """A closed, non-secret host-pressure contract refusal."""


def _refuse(code: str) -> None:
    raise HostPressureContractError(code)


def _integer(
    value: Any,
    *,
    minimum: int = 0,
    maximum: int = INT64_MAX,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _refuse("INTEGER_INVALID")
    return value


def _reference(value: Any, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _refuse("REFERENCE_INVALID")
    return value


def validate_host_pressure_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a defensive canonical-value copy or refuse the closed contract."""

    if not isinstance(value, Mapping) or set(value) != SNAPSHOT_FIELDS:
        _refuse("SNAPSHOT_FIELDS_INVALID")
    if value.get("schema") != SNAPSHOT_SCHEMA:
        _refuse("SNAPSHOT_SCHEMA_INVALID")

    host_ref = _reference(value.get("host_ref"), HOST_REF_RE)
    boot_ref = _reference(value.get("boot_ref"), BOOT_REF_RE)
    observed_at_ms = _integer(value.get("observed_at_ms"), minimum=1)
    sample_window_ms = _integer(
        value.get("sample_window_ms"),
        minimum=1,
        maximum=MAX_SAMPLE_WINDOW_MS,
    )
    logical_cpu_count = value.get("logical_cpu_count")
    if type(logical_cpu_count) is not int or not 1 <= logical_cpu_count <= 4_096:
        _refuse("CPU_COUNT_INVALID")
    load1_milli = _integer(value.get("load1_milli"))
    load_ratio_milli = _integer(value.get("load_ratio_milli"))
    if load_ratio_milli != load1_milli // logical_cpu_count:
        _refuse("LOAD_RATIO_MISMATCH")
    fseventsd_process_count = _integer(value.get("fseventsd_process_count"))

    unknown_fields = value.get("unknown_fields")
    if (
        type(unknown_fields) is not list
        or unknown_fields != sorted(set(unknown_fields))
        or any(field not in _UNKNOWNABLE_FIELDS for field in unknown_fields)
    ):
        _refuse("UNKNOWN_FIELDS_INVALID")

    normalized_optional: dict[str, int | None] = {}
    observed_unknowns: list[str] = []
    for field in _UNKNOWNABLE_FIELDS:
        field_value = value.get(field)
        if field_value is None:
            normalized_optional[field] = None
            observed_unknowns.append(field)
        else:
            normalized_optional[field] = _integer(field_value)
    if unknown_fields != observed_unknowns:
        _refuse("UNKNOWN_FIELDS_MISMATCH")

    telemetry_status = value.get("telemetry_status")
    if telemetry_status not in _TELEMETRY_STATUSES:
        _refuse("TELEMETRY_STATUS_INVALID")
    expected_status = "PARTIAL" if unknown_fields else "COMPLETE"
    if telemetry_status != expected_status:
        _refuse("TELEMETRY_STATUS_MISMATCH")

    if not unknown_fields and fseventsd_process_count == 0:
        if (
            normalized_optional["fseventsd_cpu_milli_pct"] != 0
            or normalized_optional["fseventsd_rss_bytes"] != 0
        ):
            _refuse("FSEVENTSD_ZERO_COUNT_MISMATCH")

    return {
        "schema": SNAPSHOT_SCHEMA,
        "host_ref": host_ref,
        "boot_ref": boot_ref,
        "observed_at_ms": observed_at_ms,
        "sample_window_ms": sample_window_ms,
        "logical_cpu_count": logical_cpu_count,
        "load1_milli": load1_milli,
        "load_ratio_milli": load_ratio_milli,
        "fseventsd_process_count": fseventsd_process_count,
        "fseventsd_cpu_milli_pct": normalized_optional["fseventsd_cpu_milli_pct"],
        "fseventsd_rss_bytes": normalized_optional["fseventsd_rss_bytes"],
        "telemetry_status": telemetry_status,
        "unknown_fields": list(unknown_fields),
    }


def canonical_host_pressure_json(value: Mapping[str, Any]) -> bytes:
    """Render one validated snapshot as bounded canonical UTF-8 JSON."""

    normalized = validate_host_pressure_snapshot(value)
    try:
        rendered = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:  # defensive; validation owns shape
        raise HostPressureContractError("SNAPSHOT_JSON_INVALID") from exc
    return (rendered + "\n").encode("utf-8")


__all__ = [
    "BOOT_REF_RE",
    "HOST_REF_RE",
    "INT64_MAX",
    "MAX_SAMPLE_WINDOW_MS",
    "SNAPSHOT_FIELDS",
    "SNAPSHOT_SCHEMA",
    "HostPressureContractError",
    "canonical_host_pressure_json",
    "validate_host_pressure_snapshot",
]
