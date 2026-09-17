"""Pure contract and accounting tests for inactive M2 physical resources."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from control_plane.executive_host_pressure import canonical_host_pressure_json
from control_plane.executive_host_capacity import canonical_host_capacity_json, validate_host_capacity_snapshot
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
HP1_HOST_REF = "host-" + "a" * 64
HP1_BOOT_REF = "boot-" + "b" * 64


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
        "window_binding": {"unit": units[dimension], "window_ms": 1000, "baseline_id": baseline, "boot_id": HP1_BOOT_REF},
    }


def _request():
    return {
        "operation_key": "ssd-create-1",
        "host_id": HP1_HOST_REF,
        "boot_id": HP1_BOOT_REF,
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
            "runtime_id": "runtime-test", "host_id": HP1_HOST_REF, "boot_id": HP1_BOOT_REF,
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
        "host_id": HP1_HOST_REF, "boot_id": HP1_BOOT_REF, "policy_revision": "policy-test-1",
        "sequence": 7, "required_sequence": 7, "observed_at_ms": 95,
        "pools": {p: {"available": 100, "baseline_id": "base-1", "included_materializations": []}
                  for p in ("memory", "git-store", "external", "cpu", "io", "heavy")},
        "host_pressure_evidence": _host_pressure_evidence(),
    }


def _host_pressure_snapshot(*, host_ref=HP1_HOST_REF, boot_ref=HP1_BOOT_REF, observed_at_ms=95, partial=False, extreme=False):
    cpu_count = 10
    load1_milli = INT64_MAX if extreme else 2500
    snapshot = {
        "schema": "mastermind.host_pressure_snapshot/v1",
        "host_ref": host_ref,
        "boot_ref": boot_ref,
        "observed_at_ms": observed_at_ms,
        "sample_window_ms": 5,
        "logical_cpu_count": cpu_count,
        "load1_milli": load1_milli,
        "load_ratio_milli": load1_milli // cpu_count,
        "fseventsd_process_count": 1,
        "fseventsd_cpu_milli_pct": None if partial else (INT64_MAX if extreme else 500),
        "fseventsd_rss_bytes": None if partial else (INT64_MAX if extreme else 4096),
        "telemetry_status": "PARTIAL" if partial else "COMPLETE",
        "unknown_fields": ["fseventsd_cpu_milli_pct", "fseventsd_rss_bytes"] if partial else [],
    }
    return snapshot


def _host_pressure_evidence(snapshot=None, *, digest=None):
    snapshot = copy.deepcopy(snapshot or _host_pressure_snapshot())
    if digest is None:
        digest = hashlib.sha256(canonical_host_pressure_json(snapshot)).hexdigest()
    return {"snapshot": snapshot, "snapshot_sha256": digest}


def _hp1_context(*, snapshot=None, digest=None):
    request = _request()
    request["host_id"] = HP1_HOST_REF
    request["boot_id"] = HP1_BOOT_REF
    for phase in request["phases"]:
        for demand in phase["demands"]:
            demand["window_binding"]["boot_id"] = HP1_BOOT_REF
    policy = _policy()
    policy["canonical_runtime"]["host_id"] = HP1_HOST_REF
    policy["canonical_runtime"]["boot_id"] = HP1_BOOT_REF
    policy["profiles"][0]["qualified_demands"] = copy.deepcopy(request["phases"][0]["demands"])
    observations = _observations()
    observations["host_id"] = HP1_HOST_REF
    observations["boot_id"] = HP1_BOOT_REF
    observations["host_pressure_evidence"] = _host_pressure_evidence(snapshot, digest=digest)
    return request, policy, observations


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
    own_charges = _reserved_charges()
    linked_charge = copy.deepcopy(own_charges[0])
    linked_charge["qualified_incremental_peak"] = 5
    linked_charge["remaining_charge"] = 5
    request, policy, observations = _hp1_context()
    observations["pools"]["memory"]["available"] = 35
    observations["pools"]["external"]["available"] = 90

    # The broker has already proved the operation's own reservation rows.  The
    # pure accounting layer must include every co-resident charge exactly once,
    # independent of row order, rather than infer ownership from a global row.
    for charges in ([linked_charge, *own_charges], [*own_charges, linked_charge]):
        result = evaluate_begin(
            request,
            policy=policy,
            current_charges=charges,
            observations=observations,
            decision_time_ms=100,
        )
        assert result["admitted"] is True and result["fresh_begin"] is True

    insufficient = copy.deepcopy(observations)
    insufficient["pools"]["memory"]["available"] = 34
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_begin(
            request,
            policy=policy,
            current_charges=[linked_charge, *own_charges],
            observations=insufficient,
            decision_time_ms=100,
        )
    assert exc.value.code == "INSUFFICIENT_CAPACITY"

    overflow_charges = copy.deepcopy(own_charges)
    overflow_charges[0]["remaining_charge"] = (1 << 63) - 1
    overflow_linked = copy.deepcopy(linked_charge)
    overflow_linked["remaining_charge"] = 1
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_begin(
            request,
            policy=policy,
            current_charges=[overflow_linked, *overflow_charges],
            observations=observations,
            decision_time_ms=100,
        )
    assert exc.value.code == "NUMERIC_OVERFLOW"


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


def test_hp1a_valid_exact_host_pressure_snapshot_binds_begin_result_identity():
    request, policy, observations = _hp1_context()
    expected = observations["host_pressure_evidence"]
    result = evaluate_begin(
        request, policy=policy, current_charges=_reserved_charges(),
        observations=observations, decision_time_ms=100,
    )
    assert result["host_pressure_snapshot_sha256"] == expected["snapshot_sha256"]
    assert result["host_pressure_observed_at_ms"] == 95


def test_hp1a_missing_host_pressure_evidence_refuses():
    request, policy, observations = _hp1_context()
    observations.pop("host_pressure_evidence")
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_begin(request, policy=policy, current_charges=_reserved_charges(), observations=observations, decision_time_ms=100)
    assert exc.value.code == "HOST_PRESSURE_MISSING"


def test_hp1a_invalid_host_pressure_schema_refuses_before_hash_authority():
    request, policy, observations = _hp1_context()
    observations["host_pressure_evidence"] = {
        "snapshot": {**_host_pressure_snapshot(), "schema": "other"},
        "snapshot_sha256": "0" * 64,
    }
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_begin(request, policy=policy, current_charges=_reserved_charges(), observations=observations, decision_time_ms=100)
    assert exc.value.code == "HOST_PRESSURE_SCHEMA_INVALID"


def test_hp1a_host_pressure_digest_mismatch_refuses():
    request, policy, observations = _hp1_context(digest="0" * 64)
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_begin(request, policy=policy, current_charges=_reserved_charges(), observations=observations, decision_time_ms=100)
    assert exc.value.code == "HOST_PRESSURE_HASH_MISMATCH"


def test_hp1a_incomplete_host_pressure_telemetry_refuses():
    request, policy, observations = _hp1_context(snapshot=_host_pressure_snapshot(partial=True))
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_begin(request, policy=policy, current_charges=_reserved_charges(), observations=observations, decision_time_ms=100)
    assert exc.value.code == "HOST_PRESSURE_INCOMPLETE"


@pytest.mark.parametrize(
    ("field", "snapshot", "code"),
    [
        ("host", _host_pressure_snapshot(host_ref="host-" + "c" * 64), "HOST_BINDING_MISMATCH"),
        ("boot", _host_pressure_snapshot(boot_ref="boot-" + "d" * 64), "BOOT_GENERATION_MISMATCH"),
        ("future", _host_pressure_snapshot(observed_at_ms=101), "HOST_PRESSURE_FUTURE_DATED"),
        ("stale", _host_pressure_snapshot(observed_at_ms=89), "HOST_PRESSURE_STALE"),
    ],
)
def test_hp1a_host_generation_and_freshness_refusals(field, snapshot, code):
    del field
    request, policy, observations = _hp1_context(snapshot=snapshot)
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_begin(request, policy=policy, current_charges=_reserved_charges(), observations=observations, decision_time_ms=100)
    assert exc.value.code == code


def test_hp1a_extreme_descriptive_metrics_do_not_gain_hidden_gate_authority():
    snapshot = _host_pressure_snapshot(extreme=True)
    request, policy, observations = _hp1_context(snapshot=snapshot)
    result = evaluate_begin(
        request, policy=policy, current_charges=_reserved_charges(),
        observations=observations, decision_time_ms=100,
    )
    assert result["fresh_begin"] is True
    assert result["host_pressure_snapshot_sha256"] == hashlib.sha256(canonical_host_pressure_json(snapshot)).hexdigest()


# FP1B RED: host-scoped physical qualification.
FP1B_HOST_A = HP1_HOST_REF
FP1B_BOOT_A = HP1_BOOT_REF
FP1B_POOL_A = "capacity-pool-" + "1" * 64
FP1B_HOST_B = "host-" + "c" * 64
FP1B_BOOT_B = "boot-" + "d" * 64
FP1B_POOL_B = "capacity-pool-" + "2" * 64


def _fp1b_capacity_snapshot(
    *,
    host_ref=FP1B_HOST_A,
    boot_ref=FP1B_BOOT_A,
    capacity_pool_ref=FP1B_POOL_A,
    observed_at_ms=98,
    partial=False,
    extreme=False,
):
    hp0 = _host_pressure_snapshot(
        host_ref=host_ref,
        boot_ref=boot_ref,
        observed_at_ms=observed_at_ms - 3,
        extreme=extreme,
    )
    hp0_observed_at_ms = hp0["observed_at_ms"]
    hp0_sample_window_ms = hp0["sample_window_ms"]
    hp0_start_ms = hp0_observed_at_ms - hp0_sample_window_ms
    unknown_fields = ["swap_used_bytes"] if partial else []
    huge = INT64_MAX if extreme else 64 * 1024**3
    value = {
        "schema": "mastermind.host_capacity_snapshot/v1",
        "host_ref": host_ref,
        "boot_ref": boot_ref,
        "observed_at_ms": observed_at_ms,
        "sample_window_ms": 3,
        "total_observation_window_ms": observed_at_ms - hp0_start_ms,
        "capacity_pool_ref": capacity_pool_ref,
        "hp0_sha256": hashlib.sha256(canonical_host_pressure_json(hp0)).hexdigest(),
        "hp0_observed_at_ms": hp0_observed_at_ms,
        "hp0_sample_window_ms": hp0_sample_window_ms,
        "logical_cpu_count": hp0["logical_cpu_count"],
        "load1_milli": hp0["load1_milli"],
        "load_ratio_milli": hp0["load_ratio_milli"],
        "hp0_telemetry_status": hp0["telemetry_status"],
        "physical_memory_bytes": huge,
        "vm_page_size_bytes": 4096,
        "vm_free_pages": INT64_MAX if extreme else 1_000_000,
        "vm_inactive_pages": INT64_MAX if extreme else 500_000,
        "vm_speculative_pages": INT64_MAX if extreme else 100_000,
        "vm_compressed_pages": INT64_MAX if extreme else 200_000,
        "swap_total_bytes": INT64_MAX if extreme else 4 * 1024**3,
        "swap_used_bytes": None if partial else (INT64_MAX if extreme else 1024**3),
        "pool_total_bytes": INT64_MAX if extreme else 500 * 1024**3,
        "pool_free_bytes": INT64_MAX if extreme else 300 * 1024**3,
        "telemetry_status": "PARTIAL" if partial else "COMPLETE",
        "unknown_fields": unknown_fields,
    }
    # Fail the fixture itself before it is used as policy evidence.
    return validate_host_capacity_snapshot(value)


def _fp1b_capacity_evidence(snapshot=None, *, digest=None):
    snapshot = copy.deepcopy(snapshot or _fp1b_capacity_snapshot())
    if digest is None:
        digest = hashlib.sha256(canonical_host_capacity_json(snapshot)).hexdigest()
    return {"snapshot": snapshot, "snapshot_sha256": digest}


def _fp1b_host_qualification(*, host_id, boot_id, capacity_pool_ref, reserve=10):
    request = _request()
    request["host_id"] = host_id
    request["boot_id"] = boot_id
    for phase in request["phases"]:
        for demand in phase["demands"]:
            demand["window_binding"]["boot_id"] = boot_id
    base = _policy()
    return {
        "host_id": host_id,
        "boot_id": boot_id,
        "capacity_pool_ref": capacity_pool_ref,
        "qualification_revision": "host-qualification-1",
        "qualification_evidence": ["synthetic-host-evidence"],
        "physical_pools": [
            {"capacity_pool_id": p, "protected_reserve": reserve if p == "memory" else r}
            for p, r in (("memory", 10), ("git-store", 10), ("external", 10), ("cpu", 10), ("io", 10), ("heavy", 0))
        ],
        "profiles": [{
            "profile": "SSD_CREATE_FETCH_SPARSE",
            "qualified_duration_ms": 1000,
            "qualification_evidence": ["synthetic-profile-evidence"],
            "effect_scope": ["create_external_sparse_tree"],
            "qualified_demands": copy.deepcopy(request["phases"][0]["demands"]),
        }],
        "windows": copy.deepcopy(base["windows"]),
        "limits": copy.deepcopy(base["limits"]),
    }


def _fp1b_policy(*, host_a_reserve=10, host_b_reserve=10):
    base = _policy()
    central_runtime = copy.deepcopy(base["canonical_runtime"])
    central_runtime.update({
        "runtime_id": "runtime-control",
        "host_id": "host-" + "e" * 64,
        "boot_id": "boot-" + "f" * 64,
        "endpoint": "synthetic://control-runtime",
        "database_identity": "db-control",
        "schema_identity": "schema-control",
    })
    return {
        "schema": "mastermind.physical_resource_policy.v2",
        "production_armed": True,
        "qualification": "SYNTHETIC_TEST_ONLY",
        "policy_revision": "policy-test-1",
        "authority_receipt": "synthetic-authority",
        "qualification_evidence": ["synthetic-multihost-evidence"],
        "canonical_runtime": central_runtime,
        "allowed_callers": copy.deepcopy(base["allowed_callers"]),
        "host_qualifications": [
            _fp1b_host_qualification(
                host_id=FP1B_HOST_A,
                boot_id=FP1B_BOOT_A,
                capacity_pool_ref=FP1B_POOL_A,
                reserve=host_a_reserve,
            ),
            _fp1b_host_qualification(
                host_id=FP1B_HOST_B,
                boot_id=FP1B_BOOT_B,
                capacity_pool_ref=FP1B_POOL_B,
                reserve=host_b_reserve,
            ),
        ],
        "freshness": copy.deepcopy(base["freshness"]),
        "waits": copy.deepcopy(base["waits"]),
        "recovery": copy.deepcopy(base["recovery"]),
    }


def _fp1b_context(*, host="a", snapshot=None, policy=None):
    if host == "a":
        host_id, boot_id, pool_ref = FP1B_HOST_A, FP1B_BOOT_A, FP1B_POOL_A
    else:
        host_id, boot_id, pool_ref = FP1B_HOST_B, FP1B_BOOT_B, FP1B_POOL_B
    request = _request()
    request["host_id"] = host_id
    request["boot_id"] = boot_id
    for phase in request["phases"]:
        for demand in phase["demands"]:
            demand["window_binding"]["boot_id"] = boot_id
    observations = _observations()
    observations["host_id"] = host_id
    observations["boot_id"] = boot_id
    observations["host_pressure_evidence"] = _host_pressure_evidence(
        _host_pressure_snapshot(host_ref=host_id, boot_ref=boot_id)
    )
    observations["host_capacity_evidence"] = _fp1b_capacity_evidence(
        snapshot or _fp1b_capacity_snapshot(
            host_ref=host_id,
            boot_ref=boot_id,
            capacity_pool_ref=pool_ref,
        )
    )
    return request, copy.deepcopy(policy or _fp1b_policy()), observations



def _fp1b_global_runtime_policy():
    return _fp1b_policy()


def test_fp1b_v2_keeps_one_central_runtime_while_qualifying_multiple_physical_hosts():
    policy = _fp1b_global_runtime_policy()
    request_a, _, observations_a = _fp1b_context(host="a", policy=policy)
    request_b, _, observations_b = _fp1b_context(host="b", policy=policy)
    result_a = evaluate_reservation(
        request_a,
        policy=policy,
        current_charges=[],
        observations=observations_a,
        decision_time_ms=100,
    )
    result_b = evaluate_reservation(
        request_b,
        policy=policy,
        current_charges=[],
        observations=observations_b,
        decision_time_ms=100,
    )
    assert result_a["admitted"] is True
    assert result_b["admitted"] is True
    assert policy["canonical_runtime"]["host_id"] not in {request_a["host_id"], request_b["host_id"]}
    assert all("canonical_runtime" not in host for host in policy["host_qualifications"])


def test_fp1b_host_qualification_cannot_define_a_second_canonical_runtime():
    request, policy, observations = _fp1b_context(host="a")
    policy["host_qualifications"][0]["canonical_runtime"] = copy.deepcopy(
        policy["canonical_runtime"]
    )
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_reservation(
            request,
            policy=policy,
            current_charges=[],
            observations=observations,
            decision_time_ms=100,
        )
    assert exc.value.code == "INVALID_CONTRACT"

def test_fp1b_unqualified_request_host_refuses_before_capacity_accounting():
    request, policy, observations = _fp1b_context()
    request["host_id"] = "host-" + "f" * 64
    observations["host_id"] = request["host_id"]
    observations["host_pressure_evidence"] = _host_pressure_evidence(
        _host_pressure_snapshot(host_ref=request["host_id"], boot_ref=request["boot_id"])
    )
    observations["host_capacity_evidence"] = _fp1b_capacity_evidence(
        _fp1b_capacity_snapshot(
            host_ref=request["host_id"],
            boot_ref=request["boot_id"],
            capacity_pool_ref=FP1B_POOL_A,
        )
    )
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_reservation(
            request,
            policy=policy,
            current_charges=[],
            observations=observations,
            decision_time_ms=100,
        )
    assert exc.value.code == "HOST_UNQUALIFIED"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("boot", "HOST_QUALIFICATION_GENERATION_MISMATCH"),
        ("evidence_host", "HOST_CAPACITY_HOST_MISMATCH"),
        ("evidence_boot", "HOST_CAPACITY_BOOT_MISMATCH"),
        ("pool", "HOST_CAPACITY_POOL_MISMATCH"),
        ("partial", "HOST_CAPACITY_INCOMPLETE"),
        ("future", "HOST_CAPACITY_FUTURE_DATED"),
        ("stale", "HOST_CAPACITY_STALE"),
    ],
)
def test_fp1b_selected_host_generation_and_capacity_evidence_fail_closed(mutation, expected):
    request, policy, observations = _fp1b_context()
    if mutation == "boot":
        request["boot_id"] = "boot-" + "9" * 64
        observations["boot_id"] = request["boot_id"]
        for phase in request["phases"]:
            for demand in phase["demands"]:
                demand["window_binding"]["boot_id"] = request["boot_id"]
        observations["host_pressure_evidence"] = _host_pressure_evidence(
            _host_pressure_snapshot(host_ref=request["host_id"], boot_ref=request["boot_id"])
        )
        observations["host_capacity_evidence"] = _fp1b_capacity_evidence(
            _fp1b_capacity_snapshot(
                host_ref=request["host_id"],
                boot_ref=request["boot_id"],
                capacity_pool_ref=FP1B_POOL_A,
            )
        )
    else:
        kw = {
            "host_ref": request["host_id"],
            "boot_ref": request["boot_id"],
            "capacity_pool_ref": FP1B_POOL_A,
        }
        if mutation == "evidence_host":
            kw["host_ref"] = FP1B_HOST_B
        elif mutation == "evidence_boot":
            kw["boot_ref"] = FP1B_BOOT_B
        elif mutation == "pool":
            kw["capacity_pool_ref"] = FP1B_POOL_B
        elif mutation == "partial":
            kw["partial"] = True
        elif mutation == "future":
            kw["observed_at_ms"] = 101
        elif mutation == "stale":
            kw["observed_at_ms"] = 89
        observations["host_capacity_evidence"] = _fp1b_capacity_evidence(
            _fp1b_capacity_snapshot(**kw)
        )
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_reservation(
            request,
            policy=policy,
            current_charges=[],
            observations=observations,
            decision_time_ms=100,
        )
    assert exc.value.code == expected


def test_fp1b_selected_host_uses_only_its_static_reserve_even_with_same_pool_ids():
    policy = _fp1b_policy(host_a_reserve=30, host_b_reserve=10)
    request_a, _, observations_a = _fp1b_context(host="a", policy=policy)
    observations_a["pools"]["memory"]["available"] = 45
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_reservation(
            request_a,
            policy=policy,
            current_charges=[],
            observations=observations_a,
            decision_time_ms=100,
        )
    assert exc.value.code == "INSUFFICIENT_CAPACITY"

    request_b, _, observations_b = _fp1b_context(host="b", policy=policy)
    observations_b["pools"]["memory"]["available"] = 45
    result = evaluate_reservation(
        request_b,
        policy=policy,
        current_charges=[],
        observations=observations_b,
        decision_time_ms=100,
    )
    assert result["admitted"] is True


def test_fp1b_extreme_raw_capacity_magnitudes_never_gain_ranking_or_admission_authority():
    request, policy, observations = _fp1b_context(
        snapshot=_fp1b_capacity_snapshot(extreme=True)
    )
    ordinary = evaluate_reservation(
        request,
        policy=policy,
        current_charges=[],
        observations=observations,
        decision_time_ms=100,
    )
    assert ordinary["admitted"] is True
    assert "selected_host" not in ordinary
    assert "ranking" not in ordinary
    assert "economics" not in ordinary
    assert "model" not in ordinary



def test_fp1b_valid_begin_binds_capacity_and_pressure_evidence_without_new_authority():
    request, policy, observations = _fp1b_context(host="a")
    result = evaluate_begin(
        request,
        policy=policy,
        current_charges=_reserved_charges(),
        observations=observations,
        decision_time_ms=100,
    )
    capacity_digest = hashlib.sha256(
        canonical_host_capacity_json(observations["host_capacity_evidence"]["snapshot"])
    ).hexdigest()
    pressure_digest = hashlib.sha256(
        canonical_host_pressure_json(observations["host_pressure_evidence"]["snapshot"])
    ).hexdigest()
    assert result["fresh_begin"] is True
    assert result["host_capacity_snapshot_sha256"] == capacity_digest
    assert result["host_pressure_snapshot_sha256"] == pressure_digest
    assert result["host_qualification_revision"] == "host-qualification-1"
    assert "selected_host" not in result
    assert "ranking" not in result
    assert "economics" not in result


def test_fp1b_v1_synthetic_policy_cannot_admit_a_noncanonical_host():
    request = _request()
    request["host_id"] = FP1B_HOST_B
    observations = _observations()
    observations["host_id"] = FP1B_HOST_B
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_reservation(
            request,
            policy=_policy(),
            current_charges=[],
            observations=observations,
            decision_time_ms=100,
        )
    assert exc.value.code == "HOST_UNQUALIFIED"


def test_fp1b_begin_refuses_capacity_snapshot_bound_to_a_different_hp0_sample():
    request, policy, observations = _fp1b_context(host="a")
    capacity = copy.deepcopy(observations["host_capacity_evidence"]["snapshot"])
    capacity["hp0_sha256"] = "e" * 64
    observations["host_capacity_evidence"] = _fp1b_capacity_evidence(capacity)
    with pytest.raises(PhysicalResourceRefusal) as exc:
        evaluate_begin(
            request,
            policy=policy,
            current_charges=_reserved_charges(),
            observations=observations,
            decision_time_ms=100,
        )
    assert exc.value.code == "HOST_CAPACITY_PRESSURE_MISMATCH"

def test_fp1b_production_source_policy_remains_v1_unarmed_and_grant_free():
    source = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    assert source["schema"] == "mastermind.physical_resource_policy.v1"
    assert source["production_armed"] is False
    assert source["qualification"] == "UNQUALIFIED"
    assert source["physical_pools"] == []
    assert source["profiles"] == []
    assert source["allowed_callers"] == []
