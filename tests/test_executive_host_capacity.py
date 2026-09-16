"""Closed-contract tests for read-only Darwin host capacity evidence."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from control_plane.executive_host_capacity import (
    BOOT_REF_RE,
    CAPACITY_POOL_REF_RE,
    HOST_REF_RE,
    INT64_MAX,
    MAX_SNAPSHOT_BYTES,
    MAX_TOTAL_OBSERVATION_WINDOW_MS,
    SNAPSHOT_FIELDS,
    SNAPSHOT_SCHEMA,
    HostCapacityContractError,
    canonical_host_capacity_json,
    validate_hp0_binding,
    validate_host_capacity_snapshot,
)


HOST_REF = "host-" + "a" * 64
BOOT_REF = "boot-" + "b" * 64
POOL_REF = "capacity-pool-" + "c" * 64
HP0_DIGEST = "5cb3334d42e1874f052f65ca6d34c1996ae764c2c82a2b09eb8799808d27d569"


def _hp0() -> dict:
    return {
        "schema": "mastermind.host_pressure_snapshot/v1",
        "host_ref": HOST_REF,
        "boot_ref": BOOT_REF,
        "observed_at_ms": 1_788_991_999_000,
        "sample_window_ms": 3,
        "logical_cpu_count": 24,
        "load1_milli": 12_345,
        "load_ratio_milli": 514,
        "fseventsd_process_count": 2,
        "fseventsd_cpu_milli_pct": 140_500,
        "fseventsd_rss_bytes": 307_200,
        "telemetry_status": "COMPLETE",
        "unknown_fields": [],
    }


def _snapshot() -> dict:
    return {
        "schema": SNAPSHOT_SCHEMA,
        "host_ref": HOST_REF,
        "boot_ref": BOOT_REF,
        "observed_at_ms": 1_788_992_000_000,
        "sample_window_ms": 4,
        "total_observation_window_ms": 1_003,
        "capacity_pool_ref": POOL_REF,
        "hp0_sha256": HP0_DIGEST,
        "hp0_observed_at_ms": 1_788_991_999_000,
        "hp0_sample_window_ms": 3,
        "logical_cpu_count": 24,
        "load1_milli": 12_345,
        "load_ratio_milli": 514,
        "hp0_telemetry_status": "COMPLETE",
        "physical_memory_bytes": 206158430208,
        "vm_page_size_bytes": 16384,
        "vm_free_pages": 0,
        "vm_inactive_pages": 4_946_036,
        "vm_speculative_pages": 151_931,
        "vm_compressed_pages": 3_699_714,
        "swap_total_bytes": 7_516_192_768,
        "swap_used_bytes": 6_249_234_432,
        "pool_total_bytes": 0,
        "pool_free_bytes": 0,
        "telemetry_status": "COMPLETE",
        "unknown_fields": [],
    }


def _refuse(value: object, code: str) -> None:
    with pytest.raises(HostCapacityContractError, match=code):
        validate_host_capacity_snapshot(value)


def test_snapshot_contract_is_closed_and_canonical() -> None:
    value = _snapshot()
    normalized = validate_host_capacity_snapshot(value)

    assert normalized == value
    assert normalized is not value
    payload = canonical_host_capacity_json(value)
    assert payload.endswith(b"\n")
    assert b"\n" not in payload[:-1]
    assert json.loads(payload) == value
    assert payload == json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii") + b"\n"
    assert len(payload) <= MAX_SNAPSHOT_BYTES


def test_snapshot_contract_rejects_internally_inconsistent_total_observation_window() -> None:
    value = _snapshot()
    value["total_observation_window_ms"] += 1
    _refuse(value, "TOTAL_WINDOW_MISMATCH")


def test_snapshot_contract_rejects_extra_missing_and_schema_drift() -> None:
    extra = _snapshot()
    extra["extra"] = True
    _refuse(extra, "SNAPSHOT_FIELDS_INVALID")

    missing = _snapshot()
    del missing["vm_free_pages"]
    _refuse(missing, "SNAPSHOT_FIELDS_INVALID")

    schema = _snapshot()
    schema["schema"] = "mastermind.host_capacity_snapshot/v2"
    _refuse(schema, "SNAPSHOT_SCHEMA_INVALID")


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("observed_at_ms", 0, "OBSERVED_AT_INVALID"),
        ("observed_at_ms", True, "OBSERVED_AT_INVALID"),
        ("observed_at_ms", INT64_MAX + 1, "OBSERVED_AT_INVALID"),
        ("sample_window_ms", 0, "SAMPLE_WINDOW_INVALID"),
        ("sample_window_ms", 10_001, "SAMPLE_WINDOW_INVALID"),
        ("sample_window_ms", True, "SAMPLE_WINDOW_INVALID"),
        ("total_observation_window_ms", 0, "TOTAL_OBSERVATION_WINDOW_INVALID"),
        ("total_observation_window_ms", MAX_TOTAL_OBSERVATION_WINDOW_MS + 1, "TOTAL_OBSERVATION_WINDOW_INVALID"),
        ("physical_memory_bytes", 0, "MEMORY_METRIC_INVALID"),
        ("physical_memory_bytes", -1, "MEMORY_METRIC_INVALID"),
        ("physical_memory_bytes", True, "MEMORY_METRIC_INVALID"),
        ("physical_memory_bytes", INT64_MAX + 1, "MEMORY_METRIC_INVALID"),
        ("vm_page_size_bytes", 0, "MEMORY_METRIC_INVALID"),
        ("vm_free_pages", -1, "MEMORY_METRIC_INVALID"),
        ("vm_inactive_pages", True, "MEMORY_METRIC_INVALID"),
        ("vm_speculative_pages", INT64_MAX + 1, "MEMORY_METRIC_INVALID"),
        ("vm_compressed_pages", -1, "MEMORY_METRIC_INVALID"),
        ("swap_total_bytes", -1, "SWAP_METRIC_INVALID"),
        ("swap_used_bytes", True, "SWAP_METRIC_INVALID"),
        ("pool_total_bytes", -1, "POOL_METRIC_INVALID"),
        ("pool_free_bytes", INT64_MAX + 1, "POOL_METRIC_INVALID"),
        ("hp0_observed_at_ms", 0, "HP0_FACT_INVALID"),
        ("hp0_sample_window_ms", 0, "HP0_FACT_INVALID"),
        ("logical_cpu_count", 0, "HP0_FACT_INVALID"),
        ("load1_milli", -1, "HP0_FACT_INVALID"),
        ("load_ratio_milli", True, "HP0_FACT_INVALID"),
    ],
)
def test_snapshot_contract_fails_closed_on_numeric_drift(
    field: str, value: object, code: str
) -> None:
    snapshot = _snapshot()
    snapshot[field] = value
    _refuse(snapshot, code)


def test_snapshot_contract_rejects_reference_and_digest_drift() -> None:
    assert HOST_REF_RE.fullmatch(HOST_REF)
    assert BOOT_REF_RE.fullmatch(BOOT_REF)
    assert CAPACITY_POOL_REF_RE.fullmatch(POOL_REF)

    invalid_refs = [
        ("host_ref", "host-" + "A" * 64),
        ("host_ref", "../host"),
        ("boot_ref", "boot-short"),
        ("capacity_pool_ref", "/Volumes/Pool"),
        ("capacity_pool_ref", "pool:host:name"),
        ("capacity_pool_ref", "capacity-pool-" + "z" * 64),
        ("hp0_sha256", "D" * 64),
        ("hp0_sha256", "d" * 63),
    ]
    for field, value in invalid_refs:
        snapshot = _snapshot()
        snapshot[field] = value
        expected = "HP0_DIGEST_INVALID" if field == "hp0_sha256" else "REFERENCE_INVALID"
        _refuse(snapshot, expected)


def test_snapshot_contract_rejects_hp0_fact_and_status_drift() -> None:
    snapshot = _snapshot()
    snapshot["hp0_telemetry_status"] = "UNKNOWN"
    _refuse(snapshot, "HP0_FACT_INVALID")

    snapshot = _snapshot()
    snapshot["load_ratio_milli"] = 513
    _refuse(snapshot, "HP0_FACT_INVALID")

    snapshot = _snapshot()
    snapshot["sample_window_ms"] = 5
    snapshot["total_observation_window_ms"] = 4
    _refuse(snapshot, "TOTAL_WINDOW_MISMATCH")


def test_snapshot_contract_rejects_pair_ordering_and_status_drift() -> None:
    swap = _snapshot()
    swap["swap_used_bytes"] = swap["swap_total_bytes"] + 1
    _refuse(swap, "SWAP_PAIR_INVALID")

    pool = _snapshot()
    pool["pool_free_bytes"] = pool["pool_total_bytes"] + 1
    _refuse(pool, "POOL_PAIR_INVALID")

    status = _snapshot()
    status["telemetry_status"] = "UNKNOWN"
    _refuse(status, "TELEMETRY_STATUS_INVALID")


def test_unknown_fields_are_exact_sorted_null_pairs() -> None:
    snapshot = _snapshot()
    memory_fields = [
        "physical_memory_bytes",
        "vm_page_size_bytes",
        "vm_free_pages",
        "vm_inactive_pages",
        "vm_speculative_pages",
        "vm_compressed_pages",
    ]
    swap_fields = ["swap_total_bytes", "swap_used_bytes"]
    pool_fields = ["pool_total_bytes", "pool_free_bytes"]
    unknown = sorted(memory_fields + swap_fields + pool_fields)

    for field in unknown:
        snapshot[field] = None
    snapshot["telemetry_status"] = "PARTIAL"
    snapshot["unknown_fields"] = list(reversed(unknown))
    _refuse(snapshot, "UNKNOWN_FIELDS_INVALID")

    snapshot["unknown_fields"] = unknown + ["host_ref"]
    _refuse(snapshot, "UNKNOWN_FIELDS_INVALID")

    snapshot["unknown_fields"] = unknown[:-1]
    _refuse(snapshot, "UNKNOWN_FIELDS_MISMATCH")

    snapshot["unknown_fields"] = unknown
    normalized = validate_host_capacity_snapshot(snapshot)
    assert normalized["telemetry_status"] == "PARTIAL"
    assert normalized["unknown_fields"] == unknown

    snapshot["vm_free_pages"] = 0
    _refuse(snapshot, "UNKNOWN_FIELDS_MISMATCH")


def test_observed_zero_is_valid_only_after_successful_observation() -> None:
    snapshot = _snapshot()
    assert snapshot["vm_free_pages"] == 0
    assert snapshot["pool_total_bytes"] == 0
    assert snapshot["pool_free_bytes"] == 0
    assert validate_host_capacity_snapshot(snapshot)["telemetry_status"] == "COMPLETE"

    snapshot["vm_free_pages"] = None
    snapshot["telemetry_status"] = "PARTIAL"
    snapshot["unknown_fields"] = ["vm_free_pages"]
    assert validate_host_capacity_snapshot(snapshot)["unknown_fields"] == ["vm_free_pages"]


def test_hp0_binding_recomputes_digest_and_copies_normalized_facts() -> None:
    hp0 = _hp0()
    binding = validate_hp0_binding(hp0, HOST_REF, BOOT_REF)
    expected = hashlib.sha256(
        json.dumps(
            hp0, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")
        + b"\n"
    ).hexdigest()

    assert binding == {
        "hp0_sha256": expected,
        "hp0_observed_at_ms": 1_788_991_999_000,
        "hp0_sample_window_ms": 3,
        "logical_cpu_count": 24,
        "load1_milli": 12_345,
        "load_ratio_milli": 514,
        "hp0_telemetry_status": "COMPLETE",
    }


def test_hp0_binding_rejects_schema_host_boot_and_fact_tampering() -> None:
    host = copy.deepcopy(_hp0())
    host["host_ref"] = "host-" + "9" * 64
    with pytest.raises(HostCapacityContractError, match="HP0_REFERENCE_MISMATCH"):
        validate_hp0_binding(host, HOST_REF, BOOT_REF)

    boot = copy.deepcopy(_hp0())
    boot["boot_ref"] = "boot-" + "9" * 64
    with pytest.raises(HostCapacityContractError, match="HP0_REFERENCE_MISMATCH"):
        validate_hp0_binding(boot, HOST_REF, BOOT_REF)

    malformed = copy.deepcopy(_hp0())
    malformed["logical_cpu_count"] = True
    with pytest.raises(HostCapacityContractError, match="HP0_SNAPSHOT_INVALID"):
        validate_hp0_binding(malformed, HOST_REF, BOOT_REF)

    tampered = copy.deepcopy(_hp0())
    tampered["load1_milli"] = 12_346
    tampered["load_ratio_milli"] = 515
    with pytest.raises(HostCapacityContractError, match="HP0_SNAPSHOT_INVALID"):
        validate_hp0_binding(tampered, HOST_REF, BOOT_REF)


def test_canonical_output_never_contains_private_root_or_mount_text() -> None:
    snapshot = _snapshot()
    snapshot["capacity_pool_ref"] = POOL_REF
    payload = canonical_host_capacity_json(snapshot)

    assert b"/Volumes" not in payload
    assert b"localhost" not in payload
    assert b"Macintosh" not in payload
    assert POOL_REF.encode("ascii") in payload


def test_canonical_output_is_boundedly_encoded() -> None:
    snapshot = _snapshot()
    canonical_host_capacity_json(snapshot)
    assert MAX_SNAPSHOT_BYTES <= 32768
