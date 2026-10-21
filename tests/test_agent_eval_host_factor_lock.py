"""A2 host-generation evidence-lock conformance tests.

Synthetic PUBLIC_SAFE fixtures only.  No provider calls, credentials, process
spawn, routing, placement, or production effect.  These tests prove immutable
run-to-snapshot evidence binding, not process-to-host causality.
"""
from __future__ import annotations

import copy

import pytest

from scripts import agent_eval_host_factor_lock as host_factor_lock
from scripts.agent_eval import validity
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


def test_same_finalized_run_cannot_satisfy_both_sides() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    snapshot = _snapshot()
    run = _finalized_run(scenario, config_a, experiment, arm_id="arm_a", snapshot=snapshot)

    with pytest.raises(ContractError) as excinfo:
        host_factor_lock.verify_host_factor_evidence_lock(run, snapshot, run, snapshot)

    assert "HOST_FACTOR_RUN_DUPLICATE" in _codes(excinfo)


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


def test_duplicate_host_snapshot_digest_refuses_as_ambiguous() -> None:
    scenario, config_a, config_b, experiment = _graph()
    snapshot = _snapshot()
    right = _finalized_run(scenario, config_b, experiment, arm_id="arm_b", snapshot=snapshot)

    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=2)
    first = _host_artifact("arm_a", snapshot)
    second = {**first, "artifact_ref": f"{REPO_REF_BASE}#fixtures/arm_a/duplicate-host-capacity.json"}
    draft["evidence"]["artifacts"] = [first, second]
    ambiguous = validity.finalize_run_receipt(
        scenario,
        config_a,
        experiment,
        draft,
        **VALIDATOR_KW,
    )

    with pytest.raises(ContractError) as excinfo:
        host_factor_lock.verify_host_factor_evidence_lock(ambiguous, snapshot, right, snapshot)

    assert "HOST_CAPACITY_EVIDENCE_AMBIGUOUS" in _codes(excinfo)


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

    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64
    assert digest == host_factor_lock.host_capacity_snapshot_digest(copy.deepcopy(snapshot))
    changed = copy.deepcopy(snapshot)
    changed["physical_memory_bytes"] += 1
    assert host_factor_lock.host_capacity_snapshot_digest(changed) != digest


# A2 source-boundary repair regressions. Principal source plan:
# harness-convergence-a2-boundary-repair-20260917-sol-001 / PR #692.
# Keep these tests inside Agent Eval's existing scope fence.

def test_host_bridge_is_explicitly_outside_the_inert_core() -> None:
    from pathlib import Path
    from tests import test_agent_eval_inertness as fence

    root = Path(__file__).resolve().parents[1]
    assert (root / "scripts/agent_eval_host_factor_lock.py").is_file()
    assert not (root / "scripts/agent_eval/host_factor_lock.py").exists()
    assert "control_plane" in fence.FORBIDDEN_IMPORT_MODULES
    # Do not exempt any core module or shrink the core's discovery surface.
    expected = set((root / "scripts/agent_eval").glob("*.py"))
    expected.add(root / "scripts/agent_evaluation.py")
    assert set(fence.PRODUCTION_FILES) == expected


def test_host_bridge_wave_has_only_exact_authorized_paths() -> None:
    from tests import test_agent_eval_inertness as fence

    admitted = {
        "scripts/agent_eval_host_factor_lock.py",
        "tests/test_agent_eval_host_factor_lock.py",
        "docs/superpowers/plans/2026-09-17-agent-eval-host-factor-boundary-repair.md",
    }
    for path in admitted:
        assert path in fence.ALLOWED_PATHS, path
        assert fence._changed_path_is_allowed(path)
        assert fence._is_program_surface_path(path)
    assert fence._fence_not_applicable_reason(admitted) is None
    for path in (
        "scripts/agent_eval/host_factor_lock.py",
        "scripts/agent_eval_host_factor_other.py",
        "scripts/agent_eval/arbitrary_runtime_bridge.py",
        "tests/test_agent_eval_host_factor_other.py",
        "control_plane/executive_host_capacity.py",
        "config/host_factor.json",
        ".github/workflows/host_factor.yml",
    ):
        assert not fence._changed_path_is_allowed(path), path


def test_host_bridge_has_a_closed_pure_owner_dependency_closure() -> None:
    import ast
    from pathlib import Path
    from tests import test_agent_eval_inertness as fence

    root = Path(__file__).resolve().parents[1]
    bridge = root / "scripts/agent_eval_host_factor_lock.py"
    assert bridge.is_file()
    allowed_bridge_imports = {
        "__future__", "hashlib", "collections.abc", "typing",
        "control_plane.executive_host_capacity", "scripts.agent_eval",
        "scripts.agent_eval.errors",
    }
    assert fence._imported_module_names(fence._parse(bridge)) == allowed_bridge_imports
    closure = {
        "scripts/agent_eval_host_factor_lock.py": {"control_plane.executive_host_capacity"},
        "control_plane/__init__.py": set(),
        "control_plane/executive_host_capacity.py": {"control_plane.executive_host_pressure"},
        "control_plane/executive_host_pressure.py": set(),
    }
    for relative, allowed_owners in closure.items():
        tree = fence._parse(root / relative)
        imports = fence._imported_module_names(tree)
        owners = {n for n in imports if n == "control_plane" or n.startswith("control_plane.")}
        assert owners == allowed_owners, relative
        forbidden = {
            n for n in imports
            if any(n == v or n.startswith(v + ".") for v in fence.FORBIDDEN_IMPORT_MODULES)
        }
        assert forbidden == allowed_owners, relative
        assert not (fence._dotted_attribute_accesses(tree) & fence.FORBIDDEN_ATTRIBUTE_ACCESS)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "__import__"}, relative


def test_host_bridge_reuses_canonical_owner_functions() -> None:
    from control_plane import executive_host_capacity as owner

    assert host_factor_lock.validate_host_capacity_snapshot is owner.validate_host_capacity_snapshot
    assert host_factor_lock.canonical_host_capacity_json is owner.canonical_host_capacity_json


def test_host_bridge_import_reads_no_environment_and_creates_no_effect(tmp_path) -> None:
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert (root / "scripts/agent_eval_host_factor_lock.py").is_file()
    script = f"""
import sys, os, json, hashlib, re, typing, collections.abc, datetime, uuid, unicodedata
sys.dont_write_bytecode = True
sys.path.insert(0, {str(root)!r})
class NoEnvironment(dict):
    def __getitem__(self, key): raise AssertionError('ambient environment read')
    def get(self, key, default=None): raise AssertionError('ambient environment read')
    def __iter__(self): raise AssertionError('ambient environment enumeration')
    def keys(self): raise AssertionError('ambient environment enumeration')
    def items(self): raise AssertionError('ambient environment enumeration')
    def values(self): raise AssertionError('ambient environment enumeration')
    def __contains__(self, key): raise AssertionError('ambient environment read')
os.environ = NoEnvironment()
def audit(event, args):
    if event.startswith(('socket.', 'subprocess.', 'sqlite3.')) or event in {{'os.system', 'os.fork', 'os.posix_spawn'}}:
        raise AssertionError('forbidden import effect: ' + event)
sys.addaudithook(audit)
from scripts import agent_eval_host_factor_lock
assert {{n for n in sys.modules if n.startswith('control_plane.')}} == {{
    'control_plane.executive_host_capacity', 'control_plane.executive_host_pressure'}}
"""
    before = set(tmp_path.iterdir())
    result = subprocess.run(
        [sys.executable, "-B", "-c", script], cwd=tmp_path, capture_output=True,
        text=True, timeout=15, env={"PATH": os.environ.get("PATH", "")},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert set(tmp_path.iterdir()) == before


def test_host_bridge_real_verification_needs_no_ambient_environment(monkeypatch) -> None:
    import os

    scenario, config_a, config_b, experiment = _graph()
    snapshot = _snapshot()
    left = _finalized_run(scenario, config_a, experiment, arm_id="arm_a", snapshot=snapshot)
    right = _finalized_run(scenario, config_b, experiment, arm_id="arm_b", snapshot=snapshot)
    class NoEnvironment(dict):
        def __getitem__(self, key):
            raise AssertionError("ambient environment read")
        def get(self, key, default=None):
            raise AssertionError("ambient environment read")
    monkeypatch.setattr(os, "environ", NoEnvironment())
    result = host_factor_lock.verify_host_factor_evidence_lock(left, snapshot, right, snapshot)
    assert result["scope"] == "HOST_FACTOR_EVIDENCE_LOCK_VERIFIED"
    assert result["left"]["run_digest"] == left["run_digest"]
