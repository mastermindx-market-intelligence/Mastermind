"""Pure contract and accounting tests for inactive M2 physical resources."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from control_plane.executive_physical_resources import (
    PhysicalResourceRefusal,
    apply_physical_observation,
    bounded_wait_ms,
    evaluate_begin,
    evaluate_reservation,
    load_physical_resource_policy,
    physical_request_fingerprint,
    settle_physical_accounting,
    validate_physical_request,
)


ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "config" / "executive_physical_resources.json"
INT64_MAX = (1 << 63) - 1


def _demand(dimension, pool, peak, *, baseline="base-1"):
    units = {
        "memory_bytes": "bytes", "disk_bytes": "bytes",
        "cpu_us_per_window": "cpu_us", "io_bytes_per_window": "io_bytes",
        "heavy_phase_count": "count",
    }
    return {
        "dimension": dimension,
        "capacity_pool_id": pool,
        "qualified_incremental_peak": peak,
        "window_binding": {"unit": units[dimension], "window_ms": 1000, "baseline_id": baseline, "boot_id": "boot-test"},
    }


def _request():
    return {
        "operation_key": "ssd-create-1",
        "host_id": "host-test",
        "boot_id": "boot-test",
        "owner_id": "owner-test",
        "carrier_id": "carrier-test",
        "command_id": "physical:test:reserve:1",
        "source_binding": {
            "commit_sha": "a" * 40, "helper_sha256": "b" * 64,
            "common_git_store": {"realpath": "/synthetic/git", "device": 1, "inode": 2},
            "destination": {"realpath": "/synthetic/tree", "device": 3, "capacity_pool_id": "external"},
        },
        "policy_binding": {"revision": "policy-test-1", "sha256": "c" * 64},
        "caller_binding": {"session_id": "session-test", "pid": 123, "start_id": "start-test"},
        "acquisition_time_ms": 100,
        "phases": [
            {
                "phase_key": "create",
                "profile": "SSD_CREATE_FETCH_SPARSE",
                "duration_ms": 1000,
                "effect_scope": ["create_external_sparse_tree"],
                "demands": [
                    _demand("memory_bytes", "memory", 20),
                    _demand("disk_bytes", "git-store", 30),
                    _demand("disk_bytes", "external", 40),
                    _demand("cpu_us_per_window", "cpu", 10),
                    _demand("io_bytes_per_window", "io", 15),
                    _demand("heavy_phase_count", "heavy", 1),
                ],
            }
        ],
    }


def _policy():
    return {
        "schema": "mastermind.physical_resource_policy.v1",
        "production_armed": True,
        "qualification": "SYNTHETIC_TEST_ONLY",
        "policy_revision": "policy-test-1",
        "authority_receipt": "synthetic-authority",
        "qualification_evidence": ["synthetic-evidence"],
        "canonical_runtime": {
            "runtime_id": "runtime-test", "host_id": "host-test", "boot_id": "boot-test",
            "endpoint": "synthetic://runtime", "database_identity": "db-test", "schema_identity": "schema-test",
        },
        "physical_pools": [
            {"capacity_pool_id": p, "protected_reserve": r}
            for p, r in (("memory", 10), ("git-store", 10), ("external", 10), ("cpu", 10), ("io", 10), ("heavy", 0))
        ],
        "allowed_callers": [{"owner_id": "owner-test", "carrier_id": "carrier-test", "session_id": "session-test"}],
        "profiles": [{
            "profile": "SSD_CREATE_FETCH_SPARSE",
            "qualified_duration_ms": 1000,
            "qualification_evidence": ["synthetic-profile-evidence"],
            "effect_scope": ["create_external_sparse_tree"],
            "qualified_demands": copy.deepcopy(_request()["phases"][0]["demands"]),
        }],
        "windows": {"cpu_window_ms": 1000, "io_window_ms": 1000, "normalization_evidence": "synthetic"},
        "limits": {
            "cpu_budget_us": 100, "cpu_protected_us": 10, "memory_budget_bytes": 100,
            "memory_protected_bytes": 10, "internal_protected_bytes": 10,
            "external_protected_bytes": 10, "io_budget_bytes": 100,
            "io_protected_bytes": 10, "max_heavy_phases": 2,
        },
        "freshness": {"sample_max_age_ms": 10, "sample_cadence_ms": 5, "decision_to_effect_max_ms": 10},
        "waits": {"service_request_max_ms": 20, "database_lock_max_ms": 15},
        "recovery": {"reservation_horizon_ms": 100, "reconciliation_interval_ms": 10},
    }


def _observations():
    return {
        "host_id": "host-test", "boot_id": "boot-test", "policy_revision": "policy-test-1",
        "sequence": 7, "required_sequence": 7, "observed_at_ms": 95,
        "pools": {p: {"available": 100, "baseline_id": "base-1", "included_materializations": []}
                  for p in ("memory", "git-store", "external", "cpu", "io", "heavy")},
    }


def _reserved_charges():
    charges = []
    for demand in _request()["phases"][0]["demands"]:
        charges.append({
            **copy.deepcopy(demand),
            "remaining_charge": demand["qualified_incremental_peak"],
            "attributed_materialized_or_active": 0,
            "attribution": None,
        })
    return charges


def test_unarmed_policy_preserves_nulls_and_refuses_admission():
    policy = load_physical_resource_policy(POLICY_PATH)
    assert policy["production_armed"] is False
    assert policy["limits"]["memory_budget_bytes"] is None
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_reservation(_request(), policy=policy, current_charges=[], observations=_observations(), decision_time_ms=100)
    assert exc.value.code == "POLICY_UNARMED"


def test_production_loader_rejects_synthetic_policy_and_claimed_verified_context(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(_policy()), encoding="utf-8")
    with pytest.raises(PhysicalResourceRefusal) as exc:
        load_physical_resource_policy(path)
    assert exc.value.code == "SYNTHETIC_POLICY_REFUSED"
    qualified = _policy(); qualified["qualification"] = "QUALIFIED"
    path.write_text(json.dumps(qualified), encoding="utf-8")
    with pytest.raises(PhysicalResourceRefusal) as exc:
        load_physical_resource_policy(path)
    assert exc.value.code == "RESOURCE_SCHEMA_UNADMITTED"
    unarmed = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    path.write_text(json.dumps(unarmed), encoding="utf-8")
    with pytest.raises(PhysicalResourceRefusal) as exc:
        load_physical_resource_policy(path, claimed_context={"verified": True})
    assert exc.value.code == "CLAIMED_CONTEXT_REFUSED"


def test_required_numeric_fields_reject_bool_float_string_negative_and_overflow():
    for bad in (True, 1.5, "1", -1, INT64_MAX + 1):
        request = _request()
        request["phases"][0]["demands"][0]["qualified_incremental_peak"] = bad
        with pytest.raises(PhysicalResourceRefusal) as exc:
            validate_physical_request(request)
        assert exc.value.code == "INVALID_NUMERIC_FIELD"
    overflow_charges = [
        {**_reserved_charges()[0], "remaining_charge": INT64_MAX},
        {**_reserved_charges()[0], "remaining_charge": 1},
    ]
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_reservation(_request(), policy=_policy(), current_charges=overflow_charges, observations=_observations(), decision_time_ms=100)
    assert exc.value.code == "NUMERIC_OVERFLOW"
    malformed = []
    value = _request(); value["phases"][0]["demands"][0]["dimension"] = []
    malformed.append(value)
    value = _request(); value["phases"][0]["effect_scope"] = [["not-text"]]
    malformed.append(value)
    value = _request(); value["owner_id"] = "   "
    malformed.append(value)
    value = _request(); value["source_binding"]["common_git_store"] = []
    malformed.append(value)
    value = _request(); value["command_id"] = "other-command"
    malformed.append(value)
    for value in malformed:
        with pytest.raises(PhysicalResourceRefusal) as exc:
            validate_physical_request(value)
        assert exc.value.code == "INVALID_CONTRACT"


def test_request_fingerprint_excludes_acquisition_time_but_binds_owner_carrier_source():
    request = _request()
    normalized = validate_physical_request(request)
    assert validate_physical_request(normalized) == normalized
    assert set(normalized["phases"][0]["demands"][0]) == {
        "dimension", "capacity_pool_id", "qualified_incremental_peak", "window_binding"
    }
    original = physical_request_fingerprint(request)
    later = copy.deepcopy(request); later["acquisition_time_ms"] = 999
    assert physical_request_fingerprint(later) == original
    replay = copy.deepcopy(request); replay["command_id"] = "physical:test:reserve:2"
    assert physical_request_fingerprint(replay) == original
    for path in (("owner_id",), ("carrier_id",), ("source_binding", "commit_sha")):
        changed = copy.deepcopy(request); target = changed
        for key in path[:-1]: target = target[key]
        target[path[-1]] = "d" * 40 if path[-1] == "commit_sha" else "changed"
        assert physical_request_fingerprint(changed) != original


def test_shared_apfs_pool_cannot_be_spent_as_two_volumes():
    request = _request()
    request["phases"][0]["demands"][1]["capacity_pool_id"] = "shared-disk"
    request["phases"][0]["demands"][2]["capacity_pool_id"] = "shared-disk"
    policy = _policy(); policy["physical_pools"].append({"capacity_pool_id": "shared-disk", "protected_reserve": 40})
    policy["profiles"][0]["qualified_demands"] = copy.deepcopy(request["phases"][0]["demands"])
    observations = _observations(); observations["pools"]["shared-disk"] = {"available": 100, "baseline_id": "base-1", "included_materializations": []}
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_reservation(request, policy=policy, current_charges=[], observations=observations, decision_time_ms=100)
    assert exc.value.code == "INSUFFICIENT_CAPACITY"
    unlike = _request()
    unlike["phases"][0]["demands"][0]["capacity_pool_id"] = "cpu"
    unlike_policy = _policy()
    unlike_policy["profiles"][0]["qualified_demands"] = copy.deepcopy(unlike["phases"][0]["demands"])
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_reservation(unlike, policy=unlike_policy, current_charges=[], observations=_observations(), decision_time_ms=100)
    assert exc.value.code == "MIXED_POOL_DIMENSIONS"
    for dimension_index, peak in ((0, 91), (5, 3)):
        over_limit = _request()
        over_limit["phases"][0]["demands"][dimension_index]["qualified_incremental_peak"] = peak
        over_policy = _policy()
        over_policy["profiles"][0]["qualified_demands"] = copy.deepcopy(over_limit["phases"][0]["demands"])
        observations = _observations()
        observations["pools"][over_limit["phases"][0]["demands"][dimension_index]["capacity_pool_id"]]["available"] = 1000
        with pytest.raises(PhysicalResourceRefusal) as exc:
            evaluate_reservation(over_limit, policy=over_policy, current_charges=[], observations=observations, decision_time_ms=100)
        assert exc.value.code == "INSUFFICIENT_CAPACITY"


def test_internal_git_and_external_materialization_demands_are_both_required():
    for missing_pool in ("git-store", "external"):
        request = _request()
        request["phases"][0]["demands"] = [d for d in request["phases"][0]["demands"] if d["capacity_pool_id"] != missing_pool]
        with pytest.raises(PhysicalResourceRefusal) as exc:
            evaluate_reservation(request, policy=_policy(), current_charges=[], observations=_observations(), decision_time_ms=100)
        assert exc.value.code == "PROFILE_DEMAND_MISMATCH"
    wrong_caller = _request(); wrong_caller["owner_id"] = "other-owner"
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_reservation(wrong_caller, policy=_policy(), current_charges=[], observations=_observations(), decision_time_ms=100)
    assert exc.value.code == "CALLER_UNQUALIFIED"


def test_begin_counts_own_reserved_demand_exactly_once():
    charges = _reserved_charges()
    observations = _observations(); observations["pools"]["external"]["available"] = 90
    result = evaluate_begin(_request(), policy=_policy(), current_charges=charges, observations=observations, decision_time_ms=100)
    assert result["admitted"] is True and result["fresh_begin"] is True
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_begin(_request(), policy=_policy(), current_charges=charges[:-1], observations=observations, decision_time_ms=100)
    assert exc.value.code == "MISSING_RESERVED_CHARGE"


def test_stale_boot_window_sequence_and_policy_movement_refuse():
    expected = {"boot": "BOOT_MISMATCH", "window": "STALE_OBSERVATION", "sequence": "SEQUENCE_MISMATCH", "policy": "POLICY_MOVED"}
    for mutation, code in expected.items():
        observations = _observations(); policy = _policy()
        if mutation == "boot": observations["boot_id"] = "stale"
        elif mutation == "window": observations["observed_at_ms"] = 89
        elif mutation == "sequence": observations["sequence"] = 6
        else: policy["policy_revision"] = "moved"
        with pytest.raises(PhysicalResourceRefusal) as exc:
            evaluate_begin(_request(), policy=policy, current_charges=_reserved_charges(), observations=observations, decision_time_ms=100)
        assert exc.value.code == code
    request = _request(); request["phases"][0]["demands"][3]["window_binding"]["window_ms"] = 999
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_reservation(request, policy=_policy(), current_charges=[], observations=_observations(), decision_time_ms=100)
    assert exc.value.code == "WINDOW_MISMATCH"


def test_materialization_reduction_requires_matching_free_space_baseline():
    demand = {**_demand("disk_bytes", "external", 40), "remaining_charge": 40, "attributed_materialized_or_active": 40, "attribution": {"attribution_id": "mat-1", "baseline_id": "base-1"}}
    stale = settle_physical_accounting([demand], {"terminal_effect_state": "UNKNOWN", "pools": {"external": {"baseline_id": "base-2", "included_materializations": []}}})
    mismatched = settle_physical_accounting([demand], {"terminal_effect_state": "TERMINAL", "process_terminal": True, "descendants_terminal": True, "pools": {"external": {"baseline_id": "base-3", "included_materializations": ["mat-1"]}}})
    matched = settle_physical_accounting([demand], {"terminal_effect_state": "TERMINAL", "process_terminal": True, "descendants_terminal": True, "pools": {"external": {"baseline_id": "base-1", "included_materializations": ["mat-1"]}}})
    assert stale["charges"][0]["remaining_charge"] == 40
    assert mismatched["charges"][0]["remaining_charge"] == 40
    assert matched["charges"][0]["remaining_charge"] == 0
    unproven = settle_physical_accounting([demand], {"terminal_effect_state": "NO_EFFECT", "positive_no_effect": False, "pools": {}})
    proven = settle_physical_accounting([demand], {"terminal_effect_state": "NO_EFFECT", "positive_no_effect": True, "pools": {}})
    assert unproven["charges"][0]["remaining_charge"] == 40
    assert proven["charges"][0]["remaining_charge"] == 0


def test_observed_overrun_is_charged_and_does_not_expand_grant():
    demand = {**_demand("memory_bytes", "memory", 20), "remaining_charge": 20, "attributed_materialized_or_active": 0, "attribution": None}
    result = apply_physical_observation([demand], {"usage": {"memory": 35}, "attribution_id": "sample-1", "baseline_id": "base-1"})
    assert result["charges"][0]["qualified_incremental_peak"] == 20
    assert result["charges"][0]["remaining_charge"] == 35
    assert result["charges"][0]["attributed_materialized_or_active"] == 35
    assert result["charges"][0]["attribution"] == {"attribution_id": "sample-1", "baseline_id": "base-1"}
    assert result["overrun"] is True


def test_low_instantaneous_sample_does_not_erase_future_peak():
    demand = {**_demand("memory_bytes", "memory", 20), "remaining_charge": 20, "attributed_materialized_or_active": 0, "attribution": None}
    result = apply_physical_observation([demand], {"usage": {"memory": 2}, "attribution_id": "sample-2", "baseline_id": "base-1"})
    assert result["charges"][0]["remaining_charge"] == 20
    assert result["overrun"] is False


def test_unqualified_full_build_and_expansion_classes_refuse():
    for profile in ("FULL_BUILD", "EXPAND_CHECKOUT"):
        request = _request(); request["phases"][0]["profile"] = profile
        with pytest.raises(PhysicalResourceRefusal) as exc:
            evaluate_reservation(request, policy=_policy(), current_charges=[], observations=_observations(), decision_time_ms=100)
        assert exc.value.code == "PROFILE_UNQUALIFIED"
    for mutation in ("peak", "window", "duration", "evidence"):
        request = _request(); policy = _policy()
        if mutation == "peak": request["phases"][0]["demands"][0]["qualified_incremental_peak"] -= 1
        elif mutation == "window": request["phases"][0]["demands"][0]["window_binding"]["baseline_id"] = "other"
        elif mutation == "duration": request["phases"][0]["duration_ms"] -= 1
        else: policy["profiles"][0]["qualification_evidence"] = []
        with pytest.raises(PhysicalResourceRefusal) as exc:
            evaluate_reservation(request, policy=policy, current_charges=[], observations=_observations(), decision_time_ms=100)
        assert exc.value.code in {"PROFILE_DEMAND_MISMATCH", "PROFILE_DURATION_MISMATCH", "POLICY_UNQUALIFIED"}


def test_fresh_begin_false_never_calls_effect_stub():
    calls = []
    begin_result = evaluate_reservation(_request(), policy=_policy(), current_charges=[], observations=_observations(), decision_time_ms=100)
    if begin_result["fresh_begin"]:
        calls.append("effect")
    assert calls == []


def test_wait_budget_is_bounded_and_unset_caps_refuse():
    assert bounded_wait_ms(_policy(), remaining_start_ms=12) == 12
    for field in ("service_request_max_ms", "database_lock_max_ms"):
        policy = _policy(); policy["waits"][field] = None
        with pytest.raises(PhysicalResourceRefusal) as exc:
            bounded_wait_ms(policy, remaining_start_ms=12)
        assert exc.value.code == "WAIT_BUDGET_UNQUALIFIED"
