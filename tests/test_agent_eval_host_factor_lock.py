"""A2 host-generation evidence-lock conformance tests.

Synthetic PUBLIC_SAFE fixtures only.  No provider calls, credentials, process
spawn, routing, placement, or production effect.  These tests prove immutable
run-to-snapshot evidence binding, not process-to-host causality.
"""
from __future__ import annotations

import copy

import pytest

from scripts.agent_eval import host_factor_lock, validity
from scripts.agent_eval.errors import ContractError
from tests.agent_eval_factories import (
    REPO_REF_BASE,
    build_alternate_configuration,
    build_baseline_configuration,
    build_baseline_scenario,
    build_run_draft,
    build_two_arm_experiment,
)

HOST_REF = "host-" + "a" * 64
OTHER_HOST_REF = "host-" + "d" * 64
BOOT_REF = "boot-" + "b" * 64
OTHER_BOOT_REF = "boot-" + "e" * 64
POOL_REF = "capacity-pool-" + "c" * 64
HP0_DIGEST = "5cb3334d42e1874f052f65ca6d34c1996ae764c2c82a2b09eb8799808d27d569"

VALIDATOR_KW = {
    "validator_id": "mastermind.eval_r0_finalizer.v1",
    "validator_version": "1",
    "validator_code_ref": REPO_REF_BASE,
    "validated_at": "2026-09-16T12:00:00Z",
    "created_at": "2026-09-16T12:00:01Z",
}


def _snapshot(*, host_ref: str = HOST_REF, boot_ref: str = BOOT_REF) -> dict:
    return {
        "schema": "mastermind.host_capacity_snapshot/v1",
        "host_ref": host_ref,
        "boot_ref": boot_ref,
        "observed_at_ms": 1_789_552_000_000,
        "sample_window_ms": 4,
        "total_observation_window_ms": 1_003,
        "capacity_pool_ref": POOL_REF,
        "hp0_sha256": HP0_DIGEST,
        "hp0_observed_at_ms": 1_789_551_999_000,
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


def _graph():
    scenario = build_baseline_scenario()
    config_a = build_baseline_configuration()
    config_b = build_alternate_configuration()
    experiment = build_two_arm_experiment(scenario, config_a, config_b)
    return scenario, config_a, config_b, experiment


def _host_artifact(arm_id: str, snapshot: dict) -> dict:
    return {
        "artifact_ref": f"{REPO_REF_BASE}#fixtures/{arm_id}/host-capacity.json",
        "digest": host_factor_lock.host_capacity_snapshot_digest(snapshot),
        "kind": "OTHER",
    }


def _finalized_run(scenario, configuration, experiment, *, arm_id: str, snapshot: dict) -> dict:
    draft = build_run_draft(
        scenario,
        configuration,
        experiment,
        arm_id=arm_id,
        replicate_index=1,
    )
    draft["evidence"]["artifacts"] = [_host_artifact(arm_id, snapshot)]
    return validity.finalize_run_receipt(
        scenario,
        configuration,
        experiment,
        draft,
        **VALIDATOR_KW,
    )


def _codes(excinfo) -> set[str]:
    return {defect.code for defect in excinfo.value.defects}


def test_same_host_and_boot_evidence_generation_is_verified() -> None:
    scenario, config_a, config_b, experiment = _graph()
    snapshot = _snapshot()
    left = _finalized_run(scenario, config_a, experiment, arm_id="arm_a", snapshot=snapshot)
    right = _finalized_run(scenario, config_b, experiment, arm_id="arm_b", snapshot=snapshot)

    result = host_factor_lock.verify_host_factor_evidence_lock(left, snapshot, right, snapshot)

    assert result["scope"] == "HOST_FACTOR_EVIDENCE_LOCK_VERIFIED"
    assert result["host_ref"] == HOST_REF
    assert result["boot_ref"] == BOOT_REF
    assert result["left"]["run_id"] == left["run_id"]
    assert result["right"]["run_id"] == right["run_id"]
    assert result["left"]["run_digest"] == left["run_digest"]
    assert result["right"]["run_digest"] == right["run_digest"]
    assert "artifact_ref" not in result["left"]
    assert "artifact_ref" not in result["right"]
    assert "execution_host_proven" not in result
    assert "process_host_binding" not in result
    assert set(result) == {"scope", "host_ref", "boot_ref", "left", "right"}


def test_host_mismatch_refuses_evidence_lock() -> None:
    scenario, config_a, config_b, experiment = _graph()
    left_snapshot = _snapshot()
    right_snapshot = _snapshot(host_ref=OTHER_HOST_REF)
    left = _finalized_run(scenario, config_a, experiment, arm_id="arm_a", snapshot=left_snapshot)
    right = _finalized_run(scenario, config_b, experiment, arm_id="arm_b", snapshot=right_snapshot)

    with pytest.raises(ContractError) as excinfo:
        host_factor_lock.verify_host_factor_evidence_lock(left, left_snapshot, right, right_snapshot)

    assert "HOST_FACTOR_HOST_MISMATCH" in _codes(excinfo)


def test_boot_generation_mismatch_refuses_evidence_lock() -> None:
    scenario, config_a, config_b, experiment = _graph()
    left_snapshot = _snapshot()
    right_snapshot = _snapshot(boot_ref=OTHER_BOOT_REF)
    left = _finalized_run(scenario, config_a, experiment, arm_id="arm_a", snapshot=left_snapshot)
    right = _finalized_run(scenario, config_b, experiment, arm_id="arm_b", snapshot=right_snapshot)

    with pytest.raises(ContractError) as excinfo:
        host_factor_lock.verify_host_factor_evidence_lock(left, left_snapshot, right, right_snapshot)

    assert "HOST_FACTOR_BOOT_MISMATCH" in _codes(excinfo)


def test_run_must_bind_exact_snapshot_digest() -> None:
    scenario, config_a, config_b, experiment = _graph()
    snapshot = _snapshot()
    left = _finalized_run(scenario, config_a, experiment, arm_id="arm_a", snapshot=snapshot)
    right = _finalized_run(scenario, config_b, experiment, arm_id="arm_b", snapshot=snapshot)

    forged_snapshot = _snapshot(boot_ref=OTHER_BOOT_REF)
    with pytest.raises(ContractError) as excinfo:
        host_factor_lock.verify_host_factor_evidence_lock(left, forged_snapshot, right, snapshot)

    assert "HOST_CAPACITY_EVIDENCE_MISSING" in _codes(excinfo)


def test_missing_host_snapshot_evidence_refuses() -> None:
    scenario, config_a, config_b, experiment = _graph()
    snapshot = _snapshot()
    left = _finalized_run(scenario, config_a, experiment, arm_id="arm_a", snapshot=snapshot)
    right = _finalized_run(scenario, config_b, experiment, arm_id="arm_b", snapshot=snapshot)

    # Re-finalize a valid run that has no host-capacity evidence artifact.
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=2)
    unbound = validity.finalize_run_receipt(
        scenario,
        config_a,
        experiment,
        draft,
        **VALIDATOR_KW,
    )

    with pytest.raises(ContractError) as excinfo:
        host_factor_lock.verify_host_factor_evidence_lock(unbound, snapshot, right, snapshot)

    assert "HOST_CAPACITY_EVIDENCE_MISSING" in _codes(excinfo)
    assert left["run_id"] != unbound["run_id"]


def test_post_finalization_evidence_injection_refuses_stale_run_digest() -> None:
    scenario, config_a, config_b, experiment = _graph()
    snapshot = _snapshot()
    right = _finalized_run(scenario, config_b, experiment, arm_id="arm_b", snapshot=snapshot)

    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=2)
    finalized_without_host = validity.finalize_run_receipt(
        scenario,
        config_a,
        experiment,
        draft,
        **VALIDATOR_KW,
    )
    forged = copy.deepcopy(finalized_without_host)
    forged["evidence"]["artifacts"] = [_host_artifact("arm_a", snapshot)]

    with pytest.raises(ContractError) as excinfo:
        host_factor_lock.verify_host_factor_evidence_lock(forged, snapshot, right, snapshot)

    assert "DIGEST_MISMATCH" in _codes(excinfo)


def test_malformed_host_snapshot_refuses_without_echo() -> None:
    scenario, config_a, config_b, experiment = _graph()
    snapshot = _snapshot()
    left = _finalized_run(scenario, config_a, experiment, arm_id="arm_a", snapshot=snapshot)
    right = _finalized_run(scenario, config_b, experiment, arm_id="arm_b", snapshot=snapshot)
    hostile = copy.deepcopy(snapshot)
    hostile["extra_secret_like_value"] = "SECRET_SENTINEL_DO_NOT_ECHO"

    with pytest.raises(ContractError) as excinfo:
        host_factor_lock.verify_host_factor_evidence_lock(left, hostile, right, snapshot)

    assert "HOST_CAPACITY_SNAPSHOT_INVALID" in _codes(excinfo)
    assert "SECRET_SENTINEL_DO_NOT_ECHO" not in str(excinfo.value)


def test_snapshot_digest_is_exact_canonical_owner_bytes() -> None:
    snapshot = _snapshot()
    digest = host_factor_lock.host_capacity_snapshot_digest(snapshot)

    assert len(digest) == 64
    assert digest == host_factor_lock.host_capacity_snapshot_digest(copy.deepcopy(snapshot))
    changed = copy.deepcopy(snapshot)
    changed["physical_memory_bytes"] += 1
    assert host_factor_lock.host_capacity_snapshot_digest(changed) != digest
