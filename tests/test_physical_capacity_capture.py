"""Closed-contract tests for the physical capacity capture payload builder."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from control_plane.executive_host_capacity import (
    SNAPSHOT_SCHEMA,
    canonical_host_capacity_json,
)
from control_plane.physical_capacity_capture import (
    BINDING_FIELDS,
    CAPTURE_CAPABILITY,
    CAPTURE_SCHEMA,
    MAX_PAYLOAD_BYTES,
    CapacityCaptureInvalid,
    build_capture_payload,
)


HOST_REF = "host-" + "a" * 64
BOOT_REF = "boot-" + "b" * 64
POOL_REF = "capacity-pool-" + "c" * 64
HP0_DIGEST = "5cb3334d42e1874f052f65ca6d34c1996ae764c2c82a2b09eb8799808d27d569"


def _binding() -> dict:
    return {
        "host_ref": HOST_REF,
        "boot_ref": BOOT_REF,
        "capacity_pool_ref": POOL_REF,
        "operation_key": "finite-initial:JOB-3",
        "request_fingerprint": "c" * 64,
        "source_commit_sha": "d" * 40,
        "source_helper_sha256": "e" * 64,
        "policy_revision": "sol-led-project-executive-2026-10-04",
        "host_qualification_revision": "darwin-observation-only-2026-10-04",
        "runtime_identity_sha256": "9" * 64,
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
        "physical_memory_bytes": 206_158_430_208,
        "vm_page_size_bytes": 16_384,
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


def _digest(value: dict) -> str:
    return hashlib.sha256(canonical_host_capacity_json(value)).hexdigest()


def _capture(snapshot: dict | None = None, **overrides) -> dict:
    kwargs = {
        "snapshot": _snapshot() if snapshot is None else snapshot,
        "expected_binding": _binding(),
        "snapshot_sha256": None,
        "decision_time_ms": 1_788_992_000_100,
        "max_age_ms": 60_000,
    }
    if "snapshot_sha256" not in overrides:
        kwargs["snapshot_sha256"] = _digest(kwargs["snapshot"])
    kwargs.update(overrides)
    return build_capture_payload(**kwargs)


def _refuse(**overrides) -> None:
    with pytest.raises(CapacityCaptureInvalid, match="CAPACITY_CAPTURE_INVALID"):
        _capture(**overrides)


def test_capture_payload_is_closed_canonical_and_bounded() -> None:
    payload = _capture()

    assert set(payload) == {
        "schema",
        "snapshot",
        "snapshot_sha256",
        "binding",
        "decision_time_ms",
        "capability",
        "can_place_work",
    }
    assert payload["schema"] == CAPTURE_SCHEMA
    assert payload["capability"] == CAPTURE_CAPABILITY == "OBSERVATION_ONLY"
    assert payload["can_place_work"] is False
    assert type(payload["decision_time_ms"]) is int
    assert set(payload["binding"]) == set(BINDING_FIELDS)
    assert payload["snapshot"] == _snapshot()
    assert payload["snapshot"] is not _snapshot()
    assert payload["snapshot_sha256"] == _digest(payload["snapshot"])

    encoded = canonical_payload_bytes(payload)
    assert encoded.endswith(b"\n")
    assert len(encoded) <= MAX_PAYLOAD_BYTES
    assert json.loads(encoded) == payload


def test_capture_payload_refuses_snapshot_digest_mismatch() -> None:
    _refuse(snapshot_sha256="0" * 64)

    snapshot = _snapshot()
    snapshot["vm_free_pages"] = 1
    _refuse(snapshot=snapshot, snapshot_sha256=_digest(_snapshot()))

    _refuse(snapshot_sha256="F" * 64)
    _refuse(snapshot_sha256=None)
    _refuse(snapshot_sha256=123)


def test_capture_payload_refuses_binding_source_drift() -> None:
    binding = _binding()
    binding["host_ref"] = "host-" + "1" * 64
    _refuse(expected_binding=binding)

    binding = _binding()
    binding["boot_ref"] = "boot-" + "2" * 64
    _refuse(expected_binding=binding)

    binding = _binding()
    binding["capacity_pool_ref"] = "capacity-pool-" + "3" * 64
    _refuse(expected_binding=binding)

    binding = _binding()
    binding["source_commit_sha"] = "z" * 40
    _refuse(expected_binding=binding)

    binding = _binding()
    binding["source_helper_sha256"] = "e" * 63
    _refuse(expected_binding=binding)

    binding = _binding()
    binding["runtime_identity_sha256"] = "9" * 64 + "extra"
    _refuse(expected_binding=binding)

    binding = _binding()
    del binding["policy_revision"]
    _refuse(expected_binding=binding)

    binding = _binding()
    binding["extra"] = True
    _refuse(expected_binding=binding)


def test_capture_payload_refuses_future_decision_and_oldest_window() -> None:
    _refuse(decision_time_ms=1_788_991_998_000)

    snapshot = _snapshot()
    snapshot["observed_at_ms"] = 1_788_992_000_200
    snapshot["total_observation_window_ms"] = 1_203
    _refuse(
        snapshot=snapshot,
        snapshot_sha256=_digest(snapshot),
        decision_time_ms=1_788_992_000_100,
    )

    _refuse(decision_time_ms=0)
    _refuse(decision_time_ms=True)
    _refuse(decision_time_ms="now")


def test_capture_payload_refuses_invalid_owner_max_age() -> None:
    _refuse(max_age_ms=0)
    _refuse(max_age_ms=-1)
    _refuse(max_age_ms=True)
    _refuse(max_age_ms="60000")


def test_oldest_total_window_age_is_enforced_at_inclusive_boundary() -> None:
    snapshot = _snapshot()
    decision = snapshot["observed_at_ms"] + 10
    oldest_age = snapshot["total_observation_window_ms"] + 10
    assert _capture(snapshot, decision_time_ms=decision, max_age_ms=oldest_age)["decision_time_ms"] == decision
    with pytest.raises(ValueError, match="CAPACITY_CAPTURE_INVALID"):
        _capture(snapshot, decision_time_ms=decision, max_age_ms=oldest_age - 1)


def test_provenance_revision_may_be_a_digest_but_cannot_be_a_path() -> None:
    binding = _binding()
    binding["policy_revision"] = "f" * 64
    assert _capture(expected_binding=binding)["binding"]["policy_revision"] == "f" * 64
    binding["policy_revision"] = "../private"
    _refuse(expected_binding=binding)


def test_capture_payload_refuses_secret_and_extra_snapshot_fields() -> None:
    snapshot = _snapshot()
    snapshot["operator_note"] = "should not be embedded"
    _refuse(snapshot=snapshot, snapshot_sha256=_digest(_snapshot()))

    snapshot = _snapshot()
    snapshot["vm_free_pages"] = None
    snapshot["telemetry_status"] = "PARTIAL"
    snapshot["unknown_fields"] = ["vm_free_pages"]
    payload = _capture(snapshot=snapshot)
    assert payload["snapshot"]["vm_free_pages"] is None
    assert payload["snapshot"]["telemetry_status"] == "PARTIAL"

    snapshot = _snapshot()
    del snapshot["swap_used_bytes"]
    _refuse(snapshot=snapshot, snapshot_sha256=_digest(_snapshot()))

    snapshot = _snapshot()
    snapshot["schema"] = "mastermind.host_capacity_snapshot/v2"
    _refuse(snapshot=snapshot, snapshot_sha256=_digest(_snapshot()))


def test_capture_payload_refuses_secret_binding_values() -> None:
    binding = _binding()
    binding["policy_revision"] = "-----BEGIN PRIVATE KEY-----"
    _refuse(expected_binding=binding)

    binding = _binding()
    binding["host_qualification_revision"] = "token=" + "a" * 40
    _refuse(expected_binding=binding)

    binding = _binding()
    binding["policy_revision"] = "rev/path"
    _refuse(expected_binding=binding)

    binding = _binding()
    binding["policy_revision"] = "policy\nrevision"
    _refuse(expected_binding=binding)

    binding = _binding()
    binding["policy_revision"] = ""
    _refuse(expected_binding=binding)

    binding = _binding()
    binding["policy_revision"] = "rev" * 60
    _refuse(expected_binding=binding)

    binding = _binding()
    binding["operation_key"] = "bad\tkey"
    _refuse(expected_binding=binding)

    binding = _binding()
    binding["operation_key"] = "k" * 161
    _refuse(expected_binding=binding)

    binding = _binding()
    binding["request_fingerprint"] = ""
    _refuse(expected_binding=binding)


def test_capture_payload_does_not_mutate_inputs() -> None:
    snapshot = _snapshot()
    binding = _binding()
    snapshot_before = copy.deepcopy(snapshot)
    binding_before = copy.deepcopy(binding)

    payload = _capture(snapshot, expected_binding=binding)

    assert snapshot == snapshot_before
    assert binding == binding_before
    assert payload["snapshot"] is not snapshot
    assert payload["binding"] is not binding
    assert payload["binding"]["host_ref"] == binding["host_ref"]


def canonical_payload_bytes(value: dict) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")
        + b"\n"
    )
