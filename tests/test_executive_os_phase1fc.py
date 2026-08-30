"""Load-bearing deterministic Phase 1F-C policy/schema/runtime boundaries."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import subprocess
from pathlib import Path

import pytest

import control_plane.executive_coo_cycle as executive_coo_cycle
import control_plane.executive_runtime as executive_runtime
from control_plane.executive_coo_cycle import CooCycle
from control_plane.ceo_intent import (
    INTENT_SCHEMA_V2,
    RECEIPT_SCHEMA_V2,
    submit_intent,
)
from control_plane.executive_orchestration_principal import (
    OperatorPrincipalObservation,
    OrchestrationPrincipalError,
    validate_provider_home_identity,
)
from control_plane.executive_orchestration_result import (
    GOLDEN_ROLE_SCHEMA_DIGESTS,
    RAW_OBSERVATION_SCHEMA,
    RESULT_SCHEMA,
    OrchestrationResultError,
    RawRoleResultObservation,
    canonical_bytes as result_canonical_bytes,
    canonical_digest as result_digest,
    validate_envelope,
)
from control_plane.executive_runtime import (
    ExecutiveSchemaUpgradeRequired,
    JobRequeueOutcome,
    OrchestrationDispatchOutcome,
    PersistenceError,
    Runtime,
    StateConflict,
)
from control_plane.operator_harness_contract import (
    AuthRealmFact,
    AuthRealmRequirement,
    CandidateResult,
    CapabilityManifest,
    EventCursor,
    NativeHelperPolicy,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    TurnStartObservation,
    WorkspaceIdentity,
)
from scripts.executive_os_phase1fc_acceptance import run_acceptance


def _v2_intent(**overrides):
    value = {
        "schema": INTENT_SCHEMA_V2,
        "intent_id": "CEO-PHASE1FC-001",
        "actor": "ceo-sol",
        "objective": "Run one inert deterministic COO cycle.",
        "department": "executive-infrastructure",
        "priority": 9,
        "grounding": {
            "mastermind_sha": "a" * 40,
            "macro_sha": "b" * 40,
        },
        "execution_contract": {
            "requested_authorities": ["READ"],
            "attempt_limit": 2,
        },
        "intent_kind": "executive_coo_cycle",
        "business_impact": "material",
    }
    value.update(overrides)
    return value


def _register(runtime: Runtime, worker_id: str = "worker-1") -> None:
    runtime.workers.register_worker(
        worker_id,
        provider="codex",
        account_label=f"{worker_id}@company",
        worker_type="mock",
        capabilities=["read", "research"],
        quota_classes={
            "default": {
                "provider": "codex",
                "capabilities": ["read", "research"],
                "cost_class": "small",
            }
        },
    )


def _source(source_id: str = "coo-source") -> dict[str, str]:
    return {
        "schema_version": "mastermind.executive_orchestration_provenance_source/v1",
        "creator": "coo_cycle",
        "source_id": source_id,
        "source_digest": hashlib.sha256(source_id.encode()).hexdigest(),
    }


def _dispatched_planner(runtime: Runtime):
    receipt = submit_intent(runtime, _v2_intent())
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="worker-a",
    )
    assert isinstance(dispatch, OrchestrationDispatchOutcome)
    return root, planner, dispatch


def _orchestration_profile(dispatch: OrchestrationDispatchOutcome) -> RequestedExecutionProfile:
    attempt = dispatch.attempt
    return RequestedExecutionProfile(
        worker_id=str(attempt.worker_id),
        provider="codex",
        requested_model="fixture-model",
        harness_kind="fixture",
        harness_binary_digest="a" * 64,
        harness_version="1",
        workspace=WorkspaceIdentity("/tmp/work", "b" * 40, 1, 2, os.getuid(), os.getgid()),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash=str(attempt.authority_policy_hash),
        auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
    )


def _orchestration_attestation(
    profile: RequestedExecutionProfile,
) -> ObservedHarnessAttestation:
    return ObservedHarnessAttestation(
        served_model=profile.requested_model,
        harness_version=profile.harness_version,
        harness_binary_digest=profile.harness_binary_digest,
        capabilities=(),
        effective_skills=(),
        effective_mcp=(),
        effective_plugins_or_apps=(),
        sandbox_state=profile.sandbox_policy,
        approval_state=profile.approval_policy,
        network_state=profile.network_policy,
        effective_config_digest=None,
        auth=AuthRealmFact(worker_id=profile.worker_id, provider=profile.provider),
        workspace=profile.workspace,
        supports_subagent_capability_ceiling=ObservedTriState.UNKNOWN,
    )


def _g1_recovery_fixture(tmp_path: Path, *, with_turn: bool = True):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    _root, _planner, dispatch = _dispatched_planner(runtime)
    assert dispatch.lease_token is not None
    harness = runtime.operator_harness
    profile = _orchestration_profile(dispatch)
    sealed = harness.seal_operator_harness_attempt(
        dispatch.attempt.attempt_id,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
    )
    start = OperationId("ohf-op:g1-recovery-start")
    epoch, g1 = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        operation_id=start,
    )
    process = ProcessIdentityObservation(2101, 2101, "start-2101", "boot-test")
    harness.bind_start_result(
        epoch=epoch,
        generation=g1,
        operation_id=start,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        provider_session_id="SESSION-G1",
        process=process,
    )
    principal = OperatorPrincipalObservation(
        attempt_id=sealed.attempt_id,
        worker_id="worker-a",
        process_generation_id=g1.process_generation_id,
        provider_session_id="SESSION-G1",
        process_identity={
            "pid": process.pid,
            "pgid": process.pgid,
            "process_start_identity": process.process_start_identity,
            "boot_id": process.boot_id,
        },
        os_principal_name="fixture-principal",
        os_principal_uid=os.getuid(),
        provider_home_identity={
            "path": "/tmp/phase1fc-codex-home",
            "device": 1,
            "inode": 2,
            "uid": os.getuid(),
            "gid": os.getgid(),
            "mode": 0o700,
        },
        observed_at_ms=runtime.store.now_ms(),
    )
    harness.seal_attestation(
        generation=g1,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
        attestation=_orchestration_attestation(profile),
        principal_observation=principal,
    )
    turn = None
    turn_op = None
    if with_turn:
        turn_op = OperationId("ohf-op:g1-recovery-turn")
        turn = harness.reserve_turn(
            epoch=epoch,
            generation=g1,
            operation_id=turn_op,
            fence_generation=sealed.fence_generation,
            lease_token=dispatch.lease_token,
        )
        harness.acknowledge_turn(
            turn=turn,
            operation_id=turn_op,
            fence_generation=sealed.fence_generation,
            lease_token=dispatch.lease_token,
            observation=TurnStartObservation("NATIVE-G1", True),
        )
    harness.record_reconcile_observation(
        generation=g1,
        observation=ReconcileObservation(
            process_liveness=ProcessLiveness.PROVEN_DEAD,
            observed_process=process,
            provider_session_reachable=True,
            provider_writer_state=ProviderWriterState.RELEASED,
            observed_provider_session_id="SESSION-G1",
        ),
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    return runtime, dispatch, sealed, profile, principal, epoch, g1, turn, turn_op


def _complete_ohf_role(
    runtime: Runtime,
    dispatch: OrchestrationDispatchOutcome,
    role_result: dict[str, Any],
    *,
    identity_seed: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Complete one typed role entirely through inert OHF Runtime boundaries."""

    assert dispatch.lease_token is not None
    attempt = dispatch.attempt
    job = runtime.jobs.get_job(attempt.job_id)
    assert job is not None and job.orchestration_role
    harness = runtime.operator_harness
    profile = _orchestration_profile(dispatch)
    sealed = harness.seal_operator_harness_attempt(
        attempt.attempt_id,
        fence_generation=attempt.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
    )
    start = OperationId(f"ohf-op:complete-{identity_seed}-start")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        operation_id=start,
    )
    process = ProcessIdentityObservation(
        identity_seed, identity_seed, f"start-{identity_seed}", "boot-test"
    )
    provider_session = f"SESSION-{identity_seed}"
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=start,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        provider_session_id=provider_session,
        process=process,
    )
    principal = OperatorPrincipalObservation(
        attempt_id=sealed.attempt_id,
        worker_id=str(sealed.worker_id),
        process_generation_id=generation.process_generation_id,
        provider_session_id=provider_session,
        process_identity={
            "pid": process.pid,
            "pgid": process.pgid,
            "process_start_identity": process.process_start_identity,
            "boot_id": process.boot_id,
        },
        os_principal_name=f"fixture-principal-{identity_seed}",
        os_principal_uid=identity_seed,
        provider_home_identity={
            "path": f"/tmp/phase1fc-codex-home-{identity_seed}",
            "device": identity_seed,
            "inode": identity_seed + 1,
            "uid": identity_seed,
            "gid": identity_seed,
            "mode": 0o700,
        },
        observed_at_ms=runtime.store.now_ms(),
    )
    harness.seal_attestation(
        generation=generation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
        attestation=_orchestration_attestation(profile),
        principal_observation=principal,
    )
    turn_op = OperationId(f"ohf-op:complete-{identity_seed}-turn")
    turn = harness.reserve_turn(
        epoch=epoch,
        generation=generation,
        operation_id=turn_op,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    native_turn = f"NATIVE-{identity_seed}"
    harness.acknowledge_turn(
        turn=turn,
        operation_id=turn_op,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        observation=TurnStartObservation(native_turn, True),
    )
    artifact_digest = hashlib.sha256(f"artifact-{identity_seed}".encode()).hexdigest()
    harness.record_candidate_evidence(
        turn=turn,
        candidate=CandidateResult(
            attempt.attempt_id,
            epoch.session_epoch_id,
            generation.process_generation_id,
            artifact_digest,
            "typed fixture candidate",
        ),
        events=(),
        cursor=EventCursor(
            attempt.attempt_id,
            epoch.session_epoch_id,
            generation.process_generation_id,
            turn_id=turn.turn_id,
        ),
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    envelope = {
        "schema_version": RESULT_SCHEMA,
        "job_id": job.job_id,
        "run_id": attempt.attempt_id,
        "worker_id": str(attempt.worker_id),
        "role": job.orchestration_role,
        "status": "COMPLETED",
        "role_result": role_result,
        "summary": "bounded typed fixture result",
        "current_state": "complete",
        "next_actions": [],
        "errors": [],
        "validations": [],
    }
    canonical = result_canonical_bytes(envelope).decode("utf-8")
    observation = RawRoleResultObservation(
        attempt_id=attempt.attempt_id,
        session_epoch_id=epoch.session_epoch_id,
        process_generation_id=generation.process_generation_id,
        turn_id=turn.turn_id,
        provider_session_id=provider_session,
        provider_native_turn_id=native_turn,
        provider_turn_artifact_digest=artifact_digest,
        canonical_result_json=canonical,
        canonical_result_digest=hashlib.sha256(canonical.encode()).hexdigest(),
        canonical_result_byte_length=len(canonical.encode()),
    )
    seal = harness.seal_orchestration_role_result(
        turn=turn,
        observation=observation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    death = ReconcileObservation(
        process_liveness=ProcessLiveness.PROVEN_DEAD,
        observed_process=process,
        provider_session_reachable=True,
        provider_writer_state=ProviderWriterState.RELEASED,
        observed_provider_session_id=provider_session,
    )
    harness.record_graceful_stop(
        generation=generation,
        observation=death,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    harness.abandon_epoch(
        epoch=epoch,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    terminal = {
        "schema_version": "mastermind.orchestration_terminal_receipt/v1",
        "status": "COMPLETED",
        "job_id": job.job_id,
        "attempt_id": attempt.attempt_id,
        "orchestration_role": job.orchestration_role,
        "execution_mode": "OPERATOR_HARNESS",
        "result_seal_command_id": f"orchestration-result-seal:{attempt.attempt_id}",
        "result_evidence": None,
        "result_envelope": envelope,
        "result_envelope_digest": result_digest(envelope),
        "artifact_receipt_digest": result_digest([]),
        "validation_receipt_digest": result_digest([]),
        "effective_grant_digest": attempt.effective_grant_digest,
    }
    terminal["terminal_evidence_digest"] = result_digest(terminal)
    runtime.attempts.complete_attempt(
        attempt.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        payload=terminal,
    )
    return seal, terminal


def _create_exact_v3(path: Path) -> None:
    path.parent.mkdir(parents=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            """
            CREATE TABLE schema_migrations (
              version INTEGER PRIMARY KEY,
              name TEXT NOT NULL UNIQUE,
              checksum TEXT NOT NULL,
              applied_at_ms INTEGER NOT NULL
            )
            """
        )
        for version, name, statements in executive_runtime._MIGRATIONS[:3]:
            for statement in statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations VALUES(?,?,?,?)",
                (
                    version,
                    name,
                    executive_runtime._migration_checksum(statements),
                    version,
                ),
            )
        connection.commit()
    finally:
        connection.close()


def test_fresh_schema_v4_has_exact_additive_columns_and_migration(tmp_path):
    runtime = Runtime.at(tmp_path)

    with runtime.store.read() as connection:
        migrations = connection.execute(
            "SELECT version,name FROM schema_migrations ORDER BY version"
        ).fetchall()
        job_columns = [row[1] for row in connection.execute("PRAGMA table_info(jobs)")]
        attempt_columns = [
            row[1] for row in connection.execute("PRAGMA table_info(attempts)")
        ]

    assert [tuple(row) for row in migrations][-1] == (
        4,
        "executive_phase1fc_orchestration_contract",
    )
    assert job_columns[-8:] == [
        "orchestration_role",
        "orchestration_provenance_json",
        "orchestration_provenance_digest",
        "plan_attempt_id",
        "plan_digest",
        "plan_step_id",
        "repair_round",
        "supersedes_job_id",
    ]
    assert attempt_columns[-6:] == [
        "effective_grant_json",
        "effective_grant_digest",
        "placement_snapshot_json",
        "placement_snapshot_digest",
        "execution_principal_snapshot_json",
        "execution_principal_snapshot_digest",
    ]


def test_existing_v3_normal_open_refuses_without_mode_bytes_or_sidecars(tmp_path):
    path = tmp_path / "data" / "control_plane" / "executive.sqlite3"
    _create_exact_v3(path)
    path.chmod(0o640)
    before = (hashlib.sha256(path.read_bytes()).hexdigest(), stat.S_IMODE(path.stat().st_mode))

    with pytest.raises(ExecutiveSchemaUpgradeRequired, match="explicit offline"):
        Runtime.at(tmp_path)

    after = (hashlib.sha256(path.read_bytes()).hexdigest(), stat.S_IMODE(path.stat().st_mode))
    assert after == before
    assert not path.with_name(f"{path.name}-wal").exists()
    assert not path.with_name(f"{path.name}-shm").exists()


def test_existing_v4_with_partial_ddl_refuses_before_writer_or_sidecar(tmp_path):
    runtime = Runtime.at(tmp_path)
    path = runtime.store.path
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER attempts_orchestration_job_contract_insert")
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    before = (
        hashlib.sha256(path.read_bytes()).hexdigest(),
        stat.S_IMODE(path.stat().st_mode),
        path.stat().st_mtime_ns,
        sorted(item.name for item in path.parent.iterdir()),
    )
    with pytest.raises(PersistenceError, match="exact reviewed DDL"):
        Runtime.at(tmp_path)
    after = (
        hashlib.sha256(path.read_bytes()).hexdigest(),
        stat.S_IMODE(path.stat().st_mode),
        path.stat().st_mtime_ns,
        sorted(item.name for item in path.parent.iterdir()),
    )
    assert after == before


def test_fresh_create_refuses_an_inode_that_appears_during_parent_creation(
    tmp_path, monkeypatch
):
    path = tmp_path / "data" / "control_plane" / "executive.sqlite3"
    real_mkdir = Path.mkdir
    injected = False

    def racing_mkdir(self, *args, **kwargs):
        nonlocal injected
        result = real_mkdir(self, *args, **kwargs)
        if self == path.parent and not injected:
            injected = True
            path.write_bytes(b"foreign")
            path.chmod(0o644)
        return result

    monkeypatch.setattr(Path, "mkdir", racing_mkdir)
    with pytest.raises(ExecutiveSchemaUpgradeRequired, match="appeared"):
        Runtime.at(tmp_path)
    assert path.read_bytes() == b"foreign"
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_barrier_is_lstat_checked_and_race_rolls_back(tmp_path):
    runtime = Runtime.at(tmp_path)
    barrier = runtime.store.upgrade_barrier_path
    os.symlink(barrier.with_name("missing-target"), barrier)
    with pytest.raises(PersistenceError, match="barrier"):
        runtime.jobs.create_job("must not write")
    barrier.unlink()

    with pytest.raises(PersistenceError, match="before write commit"):
        with runtime.store.transaction() as connection:
            connection.execute(
                "UPDATE workers SET updated_at_ms=updated_at_ms WHERE 0"
            )
            barrier.write_text("{}", encoding="utf-8")
    barrier.unlink()
    assert runtime.jobs.list_jobs() == []


def test_role_null_hierarchy_preserves_depth_two_and_v4_pairs_null(tmp_path):
    runtime = Runtime.at(tmp_path)
    root = runtime.jobs.create_job("legacy root")
    child = runtime.jobs.create_job("legacy child", parent_job_id=root.job_id)
    grandchild = runtime.jobs.create_job(
        "legacy grandchild", parent_job_id=child.job_id
    )

    assert (root.depth, child.depth, grandchild.depth) == (0, 1, 2)
    assert all(job.orchestration_role is None for job in (root, child, grandchild))


def test_strict_v2_root_stays_unclaimed_and_planner_claim_seals_grants(tmp_path):
    runtime = Runtime.at(tmp_path)
    receipt = submit_intent(runtime, _v2_intent())
    root = runtime.jobs.get_job(receipt["job_id"])
    assert receipt["schema"] == RECEIPT_SCHEMA_V2
    assert root is not None
    assert root.orchestration_role == "aggregation"
    assert root.parent_job_id is None and root.root_job_id == root.job_id
    assert root.business_impact == "material"
    assert root.orchestration_provenance["creator"] == "ceo_intent"

    _register(runtime)
    with pytest.raises(StateConflict, match="handoff"):
        runtime.attempts.claim_job(root.job_id)
    assert runtime.jobs.get_job(root.job_id).status.value == "QUEUED"
    with pytest.raises(StateConflict, match="command-aware COO cycle"):
        runtime.jobs.create_job(
            "forged planner",
            parent_job_id=root.job_id,
            requested_authorities=["READ"],
            constraints={"cost_class": "small"},
            attempt_limit=2,
            command_id=f"coo-cycle:{root.job_id}:create-planner:forged",
            orchestration_role="plan",
            orchestration_provenance=_source("planner-1"),
        )

    create_command = f"coo-cycle:{root.job_id}:create-planner:0"
    planner = runtime.jobs.create_cycle_planner(
        root.job_id, command_id=create_command
    )
    assert runtime.jobs.create_cycle_planner(
        root.job_id, command_id=create_command
    ).job_id == planner.job_id
    assert len([job for job in runtime.jobs.list_jobs() if job.parent_job_id == root.job_id]) == 1
    assert [
        event
        for event in runtime.events.list_events(job_id=root.job_id)
        if event.event_type == "COO_PLAN_ADMITTED"
    ] == []
    with pytest.raises(StateConflict, match="exact command-bound"):
        runtime.attempts.claim_job(planner.job_id)

    dispatch_command = (
        f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"
    )
    lease = runtime.attempts.dispatch_cycle_job(
        planner.job_id, command_id=dispatch_command
    )
    assert lease is not None
    replay = runtime.attempts.dispatch_cycle_job(
        planner.job_id, command_id=dispatch_command
    )
    assert replay is not None and replay.attempt.attempt_id == lease.attempt.attempt_id
    assert lease.attempt.effective_grant["authorities"] == ["READ"]
    assert lease.attempt.effective_grant["write_paths"] == []
    assert lease.attempt.placement_snapshot["account_label"] == "worker-1@company"
    assert len(lease.attempt.effective_grant_digest) == 64
    assert len(lease.attempt.placement_snapshot_digest) == 64
    with pytest.raises(StateConflict, match="command-bound claim"):
        runtime.broker.select_worker(planner)


def test_generic_aggregation_and_legacy_parent_orchestration_child_refuse(tmp_path):
    runtime = Runtime.at(tmp_path)
    with pytest.raises(StateConflict, match="strict CEO intent v2"):
        runtime.jobs.create_job(
            "forged root",
            requested_authorities=["READ"],
            attempt_limit=2,
            command_id="ceo-intent:forged",
            orchestration_role="aggregation",
            orchestration_provenance=_source("forged"),
        )
    legacy = runtime.jobs.create_job("legacy root")
    with pytest.raises(StateConflict, match="strict v2 aggregation root"):
        runtime.jobs.create_cycle_planner(
            legacy.job_id,
            command_id=f"coo-cycle:{legacy.job_id}:create-planner:0",
        )
    receipt = submit_intent(runtime, _v2_intent(intent_id="CEO-PHASE1FC-LEGACY"))
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    for create_planner in (False, True):
        before = len(runtime.jobs.list_jobs())
        with pytest.raises(StateConflict, match="role-null child"):
            runtime.jobs.create_job("legacy intruder", parent_job_id=root.job_id)
        assert len(runtime.jobs.list_jobs()) == before
        if not create_planner:
            runtime.jobs.create_cycle_planner(
                root.job_id,
                command_id=f"coo-cycle:{root.job_id}:create-planner:0",
            )


def test_terminal_root_cannot_mint_planner_and_generic_cycle_children_refuse(tmp_path):
    runtime = Runtime.at(tmp_path)
    receipt = submit_intent(runtime, _v2_intent())
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE jobs SET status='CANCELLED' WHERE job_id=?", (root.job_id,)
        )
    with pytest.raises(StateConflict, match="otherwise eligible QUEUED root"):
        runtime.jobs.create_cycle_planner(
            root.job_id,
            command_id=f"coo-cycle:{root.job_id}:create-planner:0",
        )

    runtime2 = Runtime.at(tmp_path / "other")
    receipt2 = submit_intent(runtime2, _v2_intent(intent_id="CEO-PHASE1FC-002"))
    root2 = runtime2.jobs.get_job(receipt2["job_id"])
    assert root2 is not None
    with pytest.raises(StateConflict, match="review orchestration Job grant requires READ"):
        runtime2.jobs.create_job(
            "forged review",
            parent_job_id=root2.job_id,
            requested_authorities=["RUN_TESTS"],
            validation_commands=[["python3", "-m", "pytest", "-q"]],
            constraints={"cost_class": "small"},
            attempt_limit=1,
            command_id=f"coo-cycle:{root2.job_id}:review:forged",
            reviews_job_id="JOB-MISSING",
            orchestration_role="review",
            orchestration_provenance=_source("review-forged"),
            plan_attempt_id="ATT-MISSING",
            plan_digest="a" * 64,
            plan_step_id="step-1",
            repair_round=0,
        )

    runtime3 = Runtime.at(tmp_path / "dispatch")
    _register(runtime3, "worker-a")
    receipt3 = submit_intent(
        runtime3, _v2_intent(intent_id="CEO-PHASE1FC-DISPATCH")
    )
    root3 = runtime3.jobs.get_job(receipt3["job_id"])
    assert root3 is not None
    planner = runtime3.jobs.create_cycle_planner(
        root3.job_id,
        command_id=f"coo-cycle:{root3.job_id}:create-planner:0",
    )
    with runtime3.store.transaction() as connection:
        connection.execute(
            "UPDATE jobs SET status='CANCELLED' WHERE job_id=?", (root3.job_id,)
        )
    before_attempts = runtime3.attempts.list_attempts(planner.job_id)
    before_events = runtime3.events.list_events(job_id=planner.job_id)
    before_quota = runtime3.workers.get_quota_class("worker-a", "default")
    with pytest.raises(StateConflict, match="eligible root"):
        runtime3.attempts.dispatch_cycle_job(
            planner.job_id,
            command_id=(
                f"coo-cycle:{root3.job_id}:dispatch:{planner.job_id}:attempt:1"
            ),
            worker_id="worker-a",
        )
    assert runtime3.attempts.list_attempts(planner.job_id) == before_attempts
    assert runtime3.events.list_events(job_id=planner.job_id) == before_events
    assert runtime3.workers.get_quota_class("worker-a", "default") == before_quota
    with pytest.raises(StateConflict, match="exact-root/job deterministic"):
        runtime3.attempts.dispatch_cycle_job(
            planner.job_id,
            command_id=(
                f"coo-cycle:{root3.job_id}:dispatch:{planner.job_id}:attempt:01"
            ),
            worker_id="worker-a",
        )


def test_plan_cannot_add_read_or_run_tests_and_child_depth_is_one(tmp_path):
    runtime = Runtime.at(tmp_path)
    root_receipt = submit_intent(
        runtime,
        _v2_intent(
            execution_contract={
                "requested_authorities": ["READ", "RUN_TESTS"],
                "validation_commands": [["python3", "-m", "pytest", "-q"]],
                "attempt_limit": 2,
            }
        ),
    )
    root = runtime.jobs.get_job(root_receipt["job_id"])
    with pytest.raises(StateConflict, match="READ only"):
        runtime.jobs.create_job(
            "bad planner",
            parent_job_id=root.job_id,
            requested_authorities=["READ", "RUN_TESTS"],
            validation_commands=[["python3", "-m", "pytest", "-q"]],
            constraints={"cost_class": "small"},
            attempt_limit=2,
            command_id="coo-cycle:root:planner:bad",
            orchestration_role="plan",
            orchestration_provenance=_source("bad-planner"),
        )
    with pytest.raises(StateConflict, match="explicitly contain READ"):
        runtime.jobs.create_job(
            "no-read planner",
            parent_job_id=root.job_id,
            requested_authorities=["RESEARCH"],
            constraints={"cost_class": "small"},
            attempt_limit=2,
            command_id="coo-cycle:root:planner:no-read",
            orchestration_role="plan",
            orchestration_provenance=_source("no-read"),
        )


def test_tx9_detached_requeue_is_evidence_bound_and_event_first(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    root, planner, dispatch = _dispatched_planner(runtime)
    attempt = dispatch.attempt
    with runtime.store.transaction() as connection:
        connection.execute(
            """
            UPDATE attempts
            SET execution_mode='OPERATOR_HARNESS',
                requested_execution_profile_json='{}',
                requested_execution_profile_digest=?,
                result_json='{"attempt_evidence":"keep"}'
            WHERE attempt_id=?
            """,
            ("f" * 64, attempt.attempt_id),
        )
        connection.execute(
            """
            UPDATE jobs SET result_json='{"job_evidence":"keep"}' WHERE job_id=?
            """,
            (planner.job_id,),
        )
        connection.execute(
            """
            INSERT INTO harness_session_epochs(
              session_epoch_id,attempt_id,worker_id,epoch_number,
              provider_session_id,state,created_at_ms
            ) VALUES('EPOCH-TX9',?,?,1,'SESSION-TX9','CURRENT',1)
            """,
            (attempt.attempt_id, attempt.worker_id),
        )
        connection.execute(
            """
            INSERT INTO process_generations(
              process_generation_id,session_epoch_id,worker_id,
              provider_session_id,generation_number,started_at_ms,
              executive_writer_held,provider_writer_state,created_at_ms
            ) VALUES('GEN-TX9','EPOCH-TX9',?,'SESSION-TX9',1,1,1,'HELD',1)
            """,
            (attempt.worker_id,),
        )
    assert runtime.operator_harness.invalidate_after_restore() == 1
    _register(runtime, "worker-b")  # unrelated worker/quota Events do not block.

    with runtime.store.read() as connection:
        before_job = dict(
            connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (planner.job_id,)
            ).fetchone()
        )
        before_attempt = dict(
            connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt.attempt_id,)
            ).fetchone()
        )
        before_quota = dict(
            connection.execute(
                """
                SELECT * FROM worker_quota_classes
                WHERE worker_id='worker-a' AND quota_class='default'
                """
            ).fetchone()
        )
    requeue_command = (
        f"coo-cycle:{root.job_id}:requeue:{planner.job_id}:{attempt.attempt_id}"
    )
    outcome = runtime.jobs.requeue_job(
        planner.job_id, command_id=requeue_command
    )
    assert isinstance(outcome, JobRequeueOutcome)
    assert outcome.requeue_kind == "TX9_DETACHED"

    with runtime.store.read() as connection:
        after_job = dict(
            connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (planner.job_id,)
            ).fetchone()
        )
        after_attempt = dict(
            connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt.attempt_id,)
            ).fetchone()
        )
        after_quota = dict(
            connection.execute(
                """
                SELECT * FROM worker_quota_classes
                WHERE worker_id='worker-a' AND quota_class='default'
                """
            ).fetchone()
        )
    mutable_job_fields = {
        "status",
        "assigned_worker_id",
        "assigned_quota_class",
        "current_attempt_id",
        "updated_at_ms",
        "version",
    }
    assert {
        key: value for key, value in after_job.items() if key not in mutable_job_fields
    } == {
        key: value for key, value in before_job.items() if key not in mutable_job_fields
    }
    assert after_attempt == before_attempt
    assert after_quota == before_quota
    assert after_job["result_json"] == '{"job_evidence":"keep"}'

    second = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:2",
        worker_id="worker-b",
    )
    assert isinstance(second, OrchestrationDispatchOutcome)
    assert second.attempt.worker_id == "worker-b"
    current_before_replay = runtime.jobs.get_job(planner.job_id)
    quota_before_replay = runtime.workers.get_quota_class("worker-b", "default")
    replay = runtime.jobs.requeue_job(planner.job_id, command_id=requeue_command)
    assert isinstance(replay, JobRequeueOutcome)
    assert replay.event_id == outcome.event_id
    assert runtime.jobs.get_job(planner.job_id) == current_before_replay
    assert runtime.workers.get_quota_class("worker-b", "default") == quota_before_replay
    with pytest.raises(StateConflict, match="another target"):
        runtime.jobs.requeue_job(root.job_id, command_id=requeue_command)


def test_tx9_exact_worker_and_quota_cutoff_and_snapshot_drift_refuse(tmp_path):
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker(
        "worker-a",
        provider="codex",
        account_label="worker-a@company",
        worker_type="mock",
        capabilities=["read"],
        quota_classes={
            "default": {"provider": "codex", "cost_class": "small"},
            "other": {"provider": "codex", "cost_class": "small"},
        },
    )
    root, planner, dispatch = _dispatched_planner(runtime)
    with runtime.store.transaction() as connection:
        connection.execute(
            """
            UPDATE attempts SET execution_mode='OPERATOR_HARNESS',
              requested_execution_profile_json='{}',
              requested_execution_profile_digest=? WHERE attempt_id=?
            """,
            ("f" * 64, dispatch.attempt.attempt_id),
        )
    runtime.operator_harness.invalidate_after_restore()
    _register(runtime, "worker-b")
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection,
            aggregate_type="quota_class",
            aggregate_id="worker-a:other",
            event_type="TEST_UNRELATED_QUOTA",
            worker_id="worker-a",
            quota_class="other",
        )
        runtime.store.append_event(
            connection,
            aggregate_type="quota_class",
            aggregate_id="worker-b:default",
            event_type="TEST_UNRELATED_WORKER",
            worker_id="worker-b",
            quota_class="default",
        )
    command = (
        f"coo-cycle:{root.job_id}:requeue:{planner.job_id}:"
        f"{dispatch.attempt.attempt_id}"
    )
    outcome = runtime.jobs.requeue_job(planner.job_id, command_id=command)
    assert isinstance(outcome, JobRequeueOutcome)
    with runtime.store.transaction() as connection:
        connection.execute(
            """
            UPDATE worker_quota_classes SET version=version+1
            WHERE worker_id='worker-a' AND quota_class='default'
            """
        )
    with pytest.raises(StateConflict, match="snapshot drifted"):
        runtime.attempts.dispatch_cycle_job(
            planner.job_id,
            command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:2",
            worker_id="worker-b",
        )
    assert len(runtime.attempts.list_attempts(planner.job_id)) == 1


def test_tx9_exact_worker_quota_later_event_blocks_without_mutation(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    root, planner, dispatch = _dispatched_planner(runtime)
    with runtime.store.transaction() as connection:
        connection.execute(
            """
            UPDATE attempts SET execution_mode='OPERATOR_HARNESS',
              requested_execution_profile_json='{}',
              requested_execution_profile_digest=? WHERE attempt_id=?
            """,
            ("f" * 64, dispatch.attempt.attempt_id),
        )
    runtime.operator_harness.invalidate_after_restore()
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection,
            aggregate_type="quota_class",
            aggregate_id="worker-a:default",
            event_type="TEST_EXACT_INVALIDATED_QUOTA",
            worker_id="worker-a",
            quota_class="default",
        )
    before = runtime.jobs.get_job(planner.job_id)
    command = (
        f"coo-cycle:{root.job_id}:requeue:{planner.job_id}:"
        f"{dispatch.attempt.attempt_id}"
    )
    with pytest.raises(StateConflict, match="later Event"):
        runtime.jobs.requeue_job(planner.job_id, command_id=command)
    assert runtime.jobs.get_job(planner.job_id) == before


def test_dispatch_replay_returns_terminal_outcome_and_refuses_target_drift(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    root, planner, dispatch = _dispatched_planner(runtime)
    assert dispatch.outcome == "ACTIVE" and dispatch.lease_token
    runtime.attempts.fail_attempt(
        dispatch.attempt.attempt_id,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
        payload={"summary": "fixture failure", "errors": ["failed"]},
    )
    command = f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"
    replay = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=command,
        worker_id="worker-a",
    )
    assert isinstance(replay, OrchestrationDispatchOutcome)
    assert replay.outcome == "TERMINAL"
    assert replay.lease_token is None
    assert replay.attempt.attempt_id == dispatch.attempt.attempt_id
    with pytest.raises(StateConflict, match="semantic target drifted"):
        runtime.attempts.dispatch_cycle_job(
            planner.job_id,
            command_id=command,
            worker_id="worker-b",
        )


@pytest.mark.parametrize("path", ["/a/./b", "/a/../b", "/a//b", "/a/b/"])
def test_provider_home_path_aliases_refuse(path):
    with pytest.raises(OrchestrationPrincipalError, match="canonical absolute"):
        validate_provider_home_identity(
            {"path": path, "device": 1, "inode": 2, "uid": 451, "gid": 451, "mode": 448}
        )


def test_orchestration_tx4_atomically_seals_principal_and_admission_before_tx5(
    tmp_path: Path,
) -> None:
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    _root, _planner, dispatch = _dispatched_planner(runtime)
    assert dispatch.lease_token is not None
    attempt = dispatch.attempt
    harness = runtime.operator_harness
    profile = _orchestration_profile(dispatch)
    sealed = harness.seal_operator_harness_attempt(
        attempt.attempt_id,
        fence_generation=attempt.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
    )
    start = OperationId("ohf-op:phase1fc-start")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        operation_id=start,
    )
    process = ProcessIdentityObservation(1201, 1201, "start-1201", "boot-test")
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=start,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        provider_session_id="SESSION-1201",
        process=process,
    )
    with pytest.raises(StateConflict, match="ALLOW|active-work admitted"):
        harness.reserve_turn(
            epoch=epoch,
            generation=generation,
            operation_id=OperationId("ohf-op:phase1fc-premature-turn"),
            fence_generation=sealed.fence_generation,
            lease_token=dispatch.lease_token,
        )

    principal = OperatorPrincipalObservation(
        attempt_id=sealed.attempt_id,
        worker_id="worker-a",
        process_generation_id=generation.process_generation_id,
        provider_session_id="SESSION-1201",
        process_identity={
            "pid": process.pid,
            "pgid": process.pgid,
            "process_start_identity": process.process_start_identity,
            "boot_id": process.boot_id,
        },
        os_principal_name="fixture-principal",
        os_principal_uid=os.getuid(),
        provider_home_identity={
            "path": "/tmp/phase1fc-codex-home",
            "device": 1,
            "inode": 2,
            "uid": os.getuid(),
            "gid": os.getgid(),
            "mode": 0o700,
        },
        observed_at_ms=runtime.store.now_ms(),
    )
    forged = OperatorPrincipalObservation.from_dict(
        {**principal.to_dict(), "worker_id": "worker-forged"}
    )
    with pytest.raises(StateConflict, match="principal evidence is invalid|binding is invalid"):
        harness.seal_attestation(
            generation=generation,
            fence_generation=sealed.fence_generation,
            lease_token=dispatch.lease_token,
            requested=profile,
            attestation=_orchestration_attestation(profile),
            principal_observation=forged,
        )
    with runtime.store.read() as connection:
        row = connection.execute(
            "SELECT observed_attestation_digest FROM process_generations "
            "WHERE process_generation_id=?",
            (generation.process_generation_id,),
        ).fetchone()
        event_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE attempt_id=? AND "
            "event_type IN ('OHF_ATTESTATION_OBSERVED','OHF_LAUNCH_DECISION',"
            "'ORCHESTRATION_WORK_ADMITTED')",
            (sealed.attempt_id,),
        ).fetchone()[0]
    assert row["observed_attestation_digest"] is None
    assert event_count == 0

    digest = harness.seal_attestation(
        generation=generation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
        attestation=_orchestration_attestation(profile),
        principal_observation=principal,
    )
    assert (
        harness.seal_attestation(
            generation=generation,
            fence_generation=sealed.fence_generation,
            lease_token=dispatch.lease_token,
            requested=profile,
            attestation=_orchestration_attestation(profile),
            principal_observation=principal,
        )
        == digest
    )
    admission = runtime.events.get_event_by_command_id(
        f"ohf-work-admit:{generation.process_generation_id}"
    )
    assert admission is not None
    assert admission.payload["principal_observation"] == principal.to_dict()
    current = runtime.attempts.get_attempt(sealed.attempt_id)
    assert current is not None and current.execution_principal_snapshot_digest
    turn = harness.reserve_turn(
        epoch=epoch,
        generation=generation,
        operation_id=OperationId("ohf-op:phase1fc-turn"),
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    assert turn.process_generation_id == generation.process_generation_id


def test_orchestration_g1_pre_candidate_loss_allows_one_freshly_admitted_g2_turn(
    tmp_path: Path,
) -> None:
    (
        runtime,
        dispatch,
        sealed,
        profile,
        principal,
        epoch,
        g1,
        _turn,
        _turn_op,
    ) = _g1_recovery_fixture(tmp_path)
    harness = runtime.operator_harness
    resume = OperationId("ohf-op:g1-recovery-resume")
    g2 = harness.reserve_same_epoch_resume(
        epoch=epoch,
        old_generation=g1,
        operation_id=resume,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    process2 = ProcessIdentityObservation(2102, 2102, "start-2102", "boot-test")
    harness.bind_resume_result(
        epoch=epoch,
        generation=g2,
        operation_id=resume,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        provider_session_id="SESSION-G1",
        process=process2,
    )
    principal2 = OperatorPrincipalObservation.from_dict(
        {
            **principal.to_dict(),
            "process_generation_id": g2.process_generation_id,
            "process_identity": {
                "pid": process2.pid,
                "pgid": process2.pgid,
                "process_start_identity": process2.process_start_identity,
                "boot_id": process2.boot_id,
            },
        }
    )
    harness.seal_attestation(
        generation=g2,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
        attestation=_orchestration_attestation(profile),
        principal_observation=principal2,
    )

    g2_turn_op = OperationId("ohf-op:g2-turn")
    g2_turn = harness.reserve_turn(
        epoch=epoch,
        generation=g2,
        operation_id=g2_turn_op,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )

    assert g2_turn.process_generation_id == g2.process_generation_id
    assert (
        harness.reserve_turn(
            epoch=epoch,
            generation=g2,
            operation_id=g2_turn_op,
            fence_generation=sealed.fence_generation,
            lease_token=dispatch.lease_token,
        )
        == g2_turn
    )
    with pytest.raises(StateConflict, match="G1 recovery|cardinality"):
        harness.reserve_turn(
            epoch=epoch,
            generation=g2,
            operation_id=OperationId("ohf-op:g2-turn-extra"),
            fence_generation=sealed.fence_generation,
            lease_token=dispatch.lease_token,
        )


@pytest.mark.parametrize("closing_evidence", ["no_turn", "checkpoint", "candidate", "effect_unknown"])
def test_orchestration_g2_refuses_without_complete_g1_pre_candidate_predicate(
    tmp_path: Path, closing_evidence: str
) -> None:
    with_turn = closing_evidence != "no_turn"
    (
        runtime,
        dispatch,
        sealed,
        _profile,
        _principal,
        epoch,
        g1,
        turn,
        turn_op,
    ) = _g1_recovery_fixture(tmp_path, with_turn=with_turn)
    with runtime.store.transaction() as connection:
        if closing_evidence == "checkpoint":
            runtime.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=str(dispatch.attempt.job_id),
                event_type="JOB_CHECKPOINTED",
                job_id=str(dispatch.attempt.job_id),
                attempt_id=sealed.attempt_id,
                worker_id=sealed.worker_id,
                quota_class=sealed.quota_class,
                payload={"checkpoint_sequence": 1},
            )
        elif closing_evidence == "candidate":
            assert turn is not None
            runtime.store.append_event(
                connection,
                aggregate_type="operator_turn",
                aggregate_id=turn.turn_id,
                event_type="OHF_CANDIDATE_RESULT_RECORDED",
                command_id=f"ohf-candidate:{turn.turn_id}",
                job_id=str(dispatch.attempt.job_id),
                attempt_id=sealed.attempt_id,
                worker_id=sealed.worker_id,
                quota_class=sealed.quota_class,
                payload={"closed_fixture": True},
            )
        elif closing_evidence == "effect_unknown":
            assert turn_op is not None
            runtime.store.append_event(
                connection,
                aggregate_type="operator_operation",
                aggregate_id=turn_op.command_id,
                event_type="EFFECT_UNKNOWN",
                command_id=f"{turn_op.command_id}:effect-unknown",
                job_id=str(dispatch.attempt.job_id),
                attempt_id=sealed.attempt_id,
                worker_id=sealed.worker_id,
                quota_class=sealed.quota_class,
                payload={"fixture": "ambiguous"},
            )

    before = runtime.events.list_events(job_id=str(dispatch.attempt.job_id))
    with pytest.raises(StateConflict, match="G1 recovery"):
        runtime.operator_harness.reserve_same_epoch_resume(
            epoch=epoch,
            old_generation=g1,
            operation_id=OperationId(f"ohf-op:refused-{closing_evidence}"),
            fence_generation=sealed.fence_generation,
            lease_token=dispatch.lease_token,
        )
    assert runtime.events.list_events(job_id=str(dispatch.attempt.job_id)) == before


def _result_envelope(role: str, role_result: dict) -> dict:
    return {
        "schema_version": RESULT_SCHEMA,
        "job_id": "JOB-100",
        "run_id": "ATT-100",
        "worker_id": "worker-1",
        "role": role,
        "status": "COMPLETED",
        "role_result": role_result,
        "summary": "bounded result",
        "current_state": "complete",
        "next_actions": [],
        "errors": [],
        "validations": [],
    }


def _plan_body() -> dict:
    return {
        "schema_version": "mastermind.execution_plan/v1",
        "root_job_id": "JOB-001",
        "plan_attempt_id": "ATT-100",
        "steps": [
            {
                "ordinal": 0,
                "step_id": "step-1",
                "objective": "Do bounded work",
                "business_impact": "routine",
                "review_required": False,
                "requested_authorities": ["READ"],
                "allowed_write_paths": ["control_plane/file.py"],
                "validation_ids": [],
                "attempt_limit": 2,
                "cost_class": "small",
            }
        ],
    }


def test_plan_result_closed_wire_round_trips_and_rejects_authority_path_and_duplicates():
    envelope = _result_envelope("plan", _plan_body())
    validated = validate_envelope(
        envelope,
        expected_job_id="JOB-100",
        expected_run_id="ATT-100",
        expected_worker_id="worker-1",
        expected_role="plan",
        expected_root_job_id="JOB-001",
    )
    assert result_canonical_bytes(validated) == result_canonical_bytes(envelope)

    empty = json.loads(json.dumps(envelope))
    empty["role_result"]["steps"][0]["requested_authorities"] = []
    with pytest.raises(OrchestrationResultError, match="1..16"):
        validate_envelope(
            empty,
            expected_job_id="JOB-100",
            expected_run_id="ATT-100",
            expected_worker_id="worker-1",
            expected_role="plan",
            expected_root_job_id="JOB-001",
        )
    absolute = json.loads(json.dumps(envelope))
    absolute["role_result"]["steps"][0]["allowed_write_paths"] = ["/tmp/x"]
    with pytest.raises(OrchestrationResultError, match="canonical path"):
        validate_envelope(
            absolute,
            expected_job_id="JOB-100",
            expected_run_id="ATT-100",
            expected_worker_id="worker-1",
            expected_role="plan",
            expected_root_job_id="JOB-001",
        )
    duplicate = json.loads(json.dumps(envelope))
    duplicate["next_actions"] = ["same", "same"]
    with pytest.raises(OrchestrationResultError, match="duplicate"):
        validate_envelope(
            duplicate,
            expected_job_id="JOB-100",
            expected_run_id="ATT-100",
            expected_worker_id="worker-1",
            expected_role="plan",
            expected_root_job_id="JOB-001",
        )


@pytest.mark.parametrize(
    ("field", "bad"),
    [("business_impact", {}), ("cost_class", [])],
)
def test_plan_enum_wrong_json_types_raise_typed_refusal(field, bad):
    envelope = _result_envelope("plan", _plan_body())
    envelope["role_result"]["steps"][0][field] = bad
    with pytest.raises(OrchestrationResultError):
        validate_envelope(
            envelope,
            expected_job_id="JOB-100",
            expected_run_id="ATT-100",
            expected_worker_id="worker-1",
            expected_role="plan",
            expected_root_job_id="JOB-001",
        )


@pytest.mark.parametrize(("field", "bad"), [("verdict", {}), ("severity", [])])
def test_review_enum_wrong_json_types_raise_typed_refusal(field, bad):
    body = {
        "schema_version": "mastermind.review_result/v1",
        "root_job_id": "JOB-001",
        "plan_attempt_id": "ATT-PLAN",
        "plan_digest": "a" * 64,
        "plan_step_id": "step-1",
        "reviewed_job_id": "JOB-WORK",
        "reviewed_attempt_id": "ATT-WORK",
        "reviewed_result_digest": "b" * 64,
        "repair_round": 0,
        "verdict": "reject",
        "evidence_digests": [],
        "findings": [
            {
                "code": "blocking-finding",
                "severity": "blocking",
                "message": "blocked",
                "evidence_digests": [],
            }
        ],
    }
    if field == "verdict":
        body["verdict"] = bad
    else:
        body["findings"][0]["severity"] = bad
    with pytest.raises(OrchestrationResultError):
        validate_envelope(
            _result_envelope("review", body),
            expected_job_id="JOB-100",
            expected_run_id="ATT-100",
            expected_worker_id="worker-1",
            expected_role="review",
        )


def test_aggregation_review_triplet_is_all_null_or_all_nonnull():
    body = {
        "schema_version": "mastermind.aggregation_result/v1",
        "root_job_id": "JOB-100",
        "handoff_digest": "a" * 64,
        "policy_sha": "b" * 64,
        "plan_attempt_id": "ATT-001",
        "plan_digest": "c" * 64,
        "revisions": [
            {
                "ordinal": 0,
                "plan_step_id": "step-1",
                "current_job_id": "JOB-101",
                "current_attempt_id": "ATT-101",
                "current_result_digest": "d" * 64,
                "repair_round": 0,
                "review_required": False,
                "qualifying_review_job_id": "JOB-102",
                "qualifying_review_attempt_id": None,
                "qualifying_review_result_digest": None,
            }
        ],
        "aggregate_summary": "summary",
        "evidence_digests": [],
    }
    with pytest.raises(OrchestrationResultError, match="nullability"):
        validate_envelope(
            _result_envelope("aggregation", body),
            expected_job_id="JOB-100",
            expected_run_id="ATT-100",
            expected_worker_id="worker-1",
            expected_role="aggregation",
        )


def test_raw_observation_freezes_schema_bytes_length_and_digest():
    envelope = _result_envelope("plan", _plan_body())
    text = result_canonical_bytes(envelope).decode("utf-8")
    kwargs = {
        "attempt_id": "ATT-100",
        "session_epoch_id": "EPOCH-1",
        "process_generation_id": "GEN-1",
        "turn_id": "TURN-1",
        "provider_session_id": "THREAD-1",
        "provider_native_turn_id": "NATIVE-1",
        "provider_turn_artifact_digest": "e" * 64,
        "canonical_result_json": text,
        "canonical_result_digest": hashlib.sha256(text.encode()).hexdigest(),
        "canonical_result_byte_length": len(text.encode()),
    }
    observation = RawRoleResultObservation(**kwargs)
    assert observation.schema_version == RAW_OBSERVATION_SCHEMA
    assert result_digest(envelope) == observation.canonical_result_digest
    with pytest.raises(OrchestrationResultError, match="schema"):
        RawRoleResultObservation(**kwargs, schema_version="wrong")


def test_run_once_cycle_blocks_generic_failed_with_retry_evidence_and_replays(
    tmp_path,
):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    receipt = submit_intent(runtime, _v2_intent(intent_id="CEO-CYCLE-ONE-STEP"))
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    cycle = CooCycle(
        runtime,
        dispatcher=lambda job_id, command_id: runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id
        ),
    )

    created = cycle.run_once(root.job_id)
    assert created.action == "PLANNER_CREATED"
    assert created.command_id == f"coo-cycle:{root.job_id}:create-planner:0"
    planner_id = str(created.selected_job_id)
    assert runtime.attempts.list_attempts(planner_id) == []

    dispatched = cycle.run_once(root.job_id)
    assert dispatched.action == "DISPATCHED"
    first = runtime.jobs.get_job(planner_id)
    assert first is not None and first.attempt_count == 1
    attempt = runtime.attempts.get_attempt(str(first.current_attempt_id))
    assert attempt is not None
    with runtime.store.read() as connection:
        token = connection.execute(
            "SELECT lease_token FROM attempts WHERE attempt_id=?", (attempt.attempt_id,)
        ).fetchone()[0]
    runtime.attempts.fail_attempt(
        attempt.attempt_id,
        fence_generation=attempt.fence_generation,
        lease_token=str(token),
        payload={"summary": "fixture adverse", "errors": ["failed"]},
    )

    failed_before = runtime.jobs.get_job(planner_id)
    blocked = cycle.run_once(root.job_id)
    assert blocked.action == "BLOCKED"
    assert blocked.receipt["reason"] == "state_conflict"
    retry_evidence = {
        "retry_safety": "GENERIC_FAILED",
        "terminal_status": "FAILED",
        "job_id": planner_id,
        "attempt_id": attempt.attempt_id,
        "attempt_job_id": planner_id,
        "current_attempt_id": attempt.attempt_id,
        "provenance_digest": first.orchestration_provenance_digest,
        "retry_lineage_available": True,
        "effect_unknown": False,
        "writer_or_provider_generation_live": False,
        "candidate_present": False,
        "result_present": True,
        "seal_present": False,
        "effective_grant_non_modifying": True,
    }
    expected_digest = hashlib.sha256(
        json.dumps(
            retry_evidence,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    assert blocked.receipt["evidence"] == {
        "retry_safety": {
            "schema_version": "mastermind.executive_retry_safety_receipt/v1",
            "decision": "NEEDS_RECONCILIATION",
            "evidence": retry_evidence,
            "evidence_digest": expected_digest,
        }
    }
    assert runtime.jobs.get_job(planner_id) == failed_before
    assert not any(
        event.event_type == "JOB_REQUEUED"
        for event in runtime.events.list_events(job_id=planner_id)
    )
    events_before = runtime.events.list_events(job_id=root.job_id)
    replay = cycle.run_once(root.job_id)
    assert replay.to_dict() == blocked.to_dict()
    assert runtime.events.list_events(job_id=root.job_id) == events_before


def test_coo_retry_gate_requeues_only_exact_tx9_detached_lost(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    root, planner, dispatch = _dispatched_planner(runtime)
    attempt = dispatch.attempt
    with runtime.store.transaction() as connection:
        connection.execute(
            """
            UPDATE attempts SET execution_mode='OPERATOR_HARNESS',
              requested_execution_profile_json='{}',
              requested_execution_profile_digest=? WHERE attempt_id=?
            """,
            ("f" * 64, attempt.attempt_id),
        )
        connection.execute(
            """
            INSERT INTO harness_session_epochs(
              session_epoch_id,attempt_id,worker_id,epoch_number,
              provider_session_id,state,created_at_ms
            ) VALUES('EPOCH-COO-TX9',?,?,1,'SESSION-COO-TX9','CURRENT',1)
            """,
            (attempt.attempt_id, attempt.worker_id),
        )
        connection.execute(
            """
            INSERT INTO process_generations(
              process_generation_id,session_epoch_id,worker_id,
              provider_session_id,generation_number,started_at_ms,
              executive_writer_held,provider_writer_state,created_at_ms
            ) VALUES('GEN-COO-TX9','EPOCH-COO-TX9',?,'SESSION-COO-TX9',1,1,1,'HELD',1)
            """,
            (attempt.worker_id,),
        )
    assert runtime.operator_harness.invalidate_after_restore() == 1
    before_events = runtime.events.list_events(job_id=planner.job_id)

    requeued = CooCycle(runtime).run_once(root.job_id)

    command = (
        f"coo-cycle:{root.job_id}:requeue:{planner.job_id}:{attempt.attempt_id}"
    )
    assert requeued.action == "REQUEUED"
    assert requeued.selected_job_id == planner.job_id
    assert requeued.command_id == command
    assert requeued.receipt["requeue_kind"] == "TX9_DETACHED"
    retry_evidence = {
        "retry_safety": "SAFE_PRE_EFFECT_INFRASTRUCTURE",
        "terminal_status": "LOST",
        "job_id": planner.job_id,
        "attempt_id": attempt.attempt_id,
        "attempt_job_id": planner.job_id,
        "current_attempt_id": attempt.attempt_id,
        "provenance_digest": requeued.receipt["payload"]["tx9_evidence_digest"],
        "retry_lineage_available": True,
        "effect_unknown": False,
        "writer_or_provider_generation_live": False,
        "candidate_present": False,
        "result_present": False,
        "seal_present": False,
        "effective_grant_non_modifying": True,
    }
    expected_digest = hashlib.sha256(
        json.dumps(
            retry_evidence,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    assert requeued.receipt["retry_safety"] == {
        "schema_version": "mastermind.executive_retry_safety_receipt/v1",
        "decision": "SAFE_REQUEUE",
        "evidence": retry_evidence,
        "evidence_digest": expected_digest,
    }
    after_events = runtime.events.list_events(job_id=planner.job_id)
    assert [event.event_type for event in after_events[len(before_events) :]] == [
        "JOB_REQUEUED"
    ]
    assert runtime.jobs.get_job(planner.job_id).status is executive_runtime.JobStatus.QUEUED
    current_before_replay = runtime.jobs.get_job(planner.job_id)
    replay = runtime.jobs.requeue_job(planner.job_id, command_id=command)
    assert replay.event_id == requeued.receipt["event_id"]
    assert runtime.jobs.get_job(planner.job_id) == current_before_replay


@pytest.mark.parametrize(
    ("terminal", "retry_safety", "decision"),
    [
        ("RATE_LIMITED", "UNKNOWN", "NEEDS_RECONCILIATION"),
        ("LOST", "EFFECT_UNKNOWN", "NEEDS_RECONCILIATION"),
    ],
)
def test_coo_retry_gate_blocks_unproven_recoverable_statuses_without_requeue(
    tmp_path, terminal, retry_safety, decision
):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    root, planner, dispatch = _dispatched_planner(runtime)
    attempt = dispatch.attempt
    with runtime.store.read() as connection:
        lease_token = str(
            connection.execute(
                "SELECT lease_token FROM attempts WHERE attempt_id=?",
                (attempt.attempt_id,),
            ).fetchone()[0]
        )
    if terminal == "RATE_LIMITED":
        runtime.attempts.rate_limit_attempt(
            attempt.attempt_id,
            fence_generation=attempt.fence_generation,
            lease_token=lease_token,
        )
    else:
        with runtime.store.transaction() as connection:
            connection.execute(
                "UPDATE attempts SET provider_session_id='PROVIDER-LOST' WHERE attempt_id=?",
                (attempt.attempt_id,),
            )
        runtime.attempts.mark_lost(
            attempt.attempt_id,
            fence_generation=attempt.fence_generation,
            lease_token=lease_token,
            reason="fixture process absent",
            verified_process_absent=True,
        )
    terminal_before = runtime.jobs.get_job(planner.job_id)

    blocked = CooCycle(runtime).run_once(root.job_id)

    assert blocked.action == "BLOCKED"
    assert blocked.receipt["reason"] == "state_conflict"
    assert blocked.receipt["evidence"]["retry_safety"]["decision"] == decision
    assert (
        blocked.receipt["evidence"]["retry_safety"]["evidence"]["retry_safety"]
        == retry_safety
    )
    assert (
        blocked.receipt["evidence"]["retry_safety"]["evidence"]["attempt_id"]
        == attempt.attempt_id
    )
    assert runtime.jobs.get_job(planner.job_id) == terminal_before
    assert not any(
        event.event_type == "JOB_REQUEUED"
        for event in runtime.events.list_events(job_id=planner.job_id)
    )


def test_dispatch_return_crash_replays_same_claim_without_block_or_sentinel_mutation(
    tmp_path: Path,
) -> None:
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    receipt = submit_intent(
        runtime, _v2_intent(intent_id="CEO-CYCLE-DISPATCH-RETURN-CRASH")
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    sentinel = runtime.jobs.create_job("unrelated queued sentinel")
    sentinel_before = sentinel.to_dict()
    claimed: list[OrchestrationDispatchOutcome] = []

    def claim_then_raise(job_id: str, command_id: str):
        outcome = runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id="worker-a"
        )
        assert outcome is not None
        claimed.append(outcome)
        if len(claimed) == 1:
            raise RuntimeError("fixture crash after durable exact claim")
        return outcome

    cycle = CooCycle(runtime, dispatcher=claim_then_raise)
    created = cycle.run_once(root.job_id)
    assert created.action == "PLANNER_CREATED"
    planner_id = str(created.selected_job_id)

    with pytest.raises(RuntimeError, match="after durable exact claim"):
        cycle.run_once(root.job_id)

    planner_after_crash = runtime.jobs.get_job(planner_id)
    assert planner_after_crash is not None
    assert planner_after_crash.attempt_count == 1
    first_attempt_id = planner_after_crash.current_attempt_id
    with runtime.store.read() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='COO_CYCLE_BLOCKED' "
            "AND job_id=?",
            (root.job_id,),
        ).fetchone()[0] == 0

    replay = cycle.run_once(root.job_id)

    assert replay.action == "DISPATCHED"
    assert replay.receipt["attempt"]["attempt_id"] == first_attempt_id
    assert runtime.jobs.get_job(planner_id).attempt_count == 1
    assert runtime.jobs.get_job(sentinel.job_id).to_dict() == sentinel_before


def test_dispatch_none_after_claim_refuses_second_mutation_and_replays_same_attempt(
    tmp_path: Path,
) -> None:
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    receipt = submit_intent(
        runtime, _v2_intent(intent_id="CEO-CYCLE-DISPATCH-NONE-AFTER-CLAIM")
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    first_outcome: OrchestrationDispatchOutcome | None = None

    def claim_then_none(job_id: str, command_id: str):
        nonlocal first_outcome
        first_outcome = runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id="worker-a"
        )
        assert first_outcome is not None
        return None

    cycle = CooCycle(runtime, dispatcher=claim_then_none)
    created = cycle.run_once(root.job_id)
    planner_id = str(created.selected_job_id)
    with pytest.raises(StateConflict, match="ambiguous after durable Job transition"):
        cycle.run_once(root.job_id)
    assert first_outcome is not None
    with runtime.store.read() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='COO_CYCLE_BLOCKED' "
            "AND job_id=?",
            (root.job_id,),
        ).fetchone()[0] == 0

    cycle.dispatcher = lambda job_id, command_id: runtime.attempts.dispatch_cycle_job(
        job_id, command_id=command_id, worker_id="worker-a"
    )
    replay = cycle.run_once(root.job_id)
    assert replay.action == "DISPATCHED"
    assert replay.receipt["attempt"]["attempt_id"] == (
        first_outcome.attempt.attempt_id
    )
    assert runtime.jobs.get_job(planner_id).attempt_count == 1


def _cycle_through_completed_work(
    tmp_path: Path,
    *,
    intent_id: str,
    review_workers: list[str],
):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    _register(runtime, "worker-b")
    receipt = submit_intent(runtime, _v2_intent(intent_id=intent_id))
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    dispatches: list[OrchestrationDispatchOutcome] = []
    review_index = 0

    def accepted_dispatch(job_id: str, command_id: str):
        nonlocal review_index
        job = runtime.jobs.get_job(job_id)
        assert job is not None
        if job.orchestration_role == "review":
            worker = review_workers[review_index]
            review_index += 1
        else:
            worker = "worker-a"
        outcome = runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id=worker
        )
        assert outcome is not None
        dispatches.append(outcome)
        return outcome

    cycle = CooCycle(runtime, dispatcher=accepted_dispatch)
    assert cycle.run_once(root.job_id).action == "PLANNER_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    planner = dispatches[-1]
    plan_body = {
        "schema_version": "mastermind.execution_plan/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner.attempt.attempt_id,
        "steps": [
            {
                "ordinal": 0,
                "step_id": "step-1",
                "objective": "Perform one bounded read-only task.",
                "business_impact": "routine",
                "review_required": True,
                "requested_authorities": ["READ"],
                "allowed_write_paths": [],
                "validation_ids": [],
                "attempt_limit": 1,
                "cost_class": "small",
            }
        ],
    }
    _complete_ohf_role(runtime, planner, plan_body, identity_seed=3201)
    admission = cycle.run_once(root.job_id)
    assert admission.action == "PLAN_ADMITTED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    work = dispatches[-1]
    work_body = {
        "schema_version": "mastermind.work_result/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner.attempt.attempt_id,
        "plan_digest": result_digest(plan_body),
        "plan_step_id": "step-1",
        "repair_round": 0,
        "artifacts": [],
        "evidence_digests": [],
    }
    work_seal, _terminal = _complete_ohf_role(
        runtime, work, work_body, identity_seed=3202
    )
    return runtime, cycle, dispatches, root, planner, work, work_seal


def _review_body(
    *,
    root_id: str,
    plan_attempt_id: str,
    plan_digest: str,
    target_job_id: str,
    target_attempt_id: str,
    target_result_digest: str,
    repair_round: int,
    verdict: str,
) -> dict[str, Any]:
    return {
        "schema_version": "mastermind.review_result/v1",
        "root_job_id": root_id,
        "plan_attempt_id": plan_attempt_id,
        "plan_digest": plan_digest,
        "plan_step_id": "step-1",
        "reviewed_job_id": target_job_id,
        "reviewed_attempt_id": target_attempt_id,
        "reviewed_result_digest": target_result_digest,
        "repair_round": repair_round,
        "verdict": verdict,
        "evidence_digests": [],
        "findings": (
            []
            if verdict == "approve"
            else [
                {
                    "code": "REPAIR_REQUIRED",
                    "severity": "blocking",
                    "message": "The bounded work needs one repair.",
                    "evidence_digests": [],
                }
            ]
        ),
    }


def test_void_review_replacement_approval_reaches_handoff(tmp_path: Path) -> None:
    runtime, cycle, dispatches, root, planner, work, work_seal = (
        _cycle_through_completed_work(
            tmp_path,
            intent_id="CEO-CYCLE-VOID-REPLACEMENT",
            review_workers=["worker-a", "worker-b"],
        )
    )
    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    void_review = dispatches[-1]
    plan_digest = runtime.jobs.get_job(work.attempt.job_id).plan_digest
    void_body = _review_body(
        root_id=root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=str(plan_digest),
        target_job_id=work.attempt.job_id,
        target_attempt_id=work.attempt.attempt_id,
        target_result_digest=work_seal["role_result_digest"],
        repair_round=0,
        verdict="approve",
    )
    _complete_ohf_role(runtime, void_review, void_body, identity_seed=3203)

    replacement = cycle.run_once(root.job_id)
    assert replacement.action == "REVIEW_CREATED"
    assert replacement.command_id.endswith(":2")
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    independent_review = dispatches[-1]
    approve_body = dict(void_body)
    _complete_ohf_role(
        runtime, independent_review, approve_body, identity_seed=3204
    )

    handoff = cycle.run_once(root.job_id)
    assert handoff.action == "HANDOFF_CREATED"
    material = runtime.jobs.get_cycle_handoff(root.job_id)
    assert material["revisions"][0]["qualifying_review_job_id"] == (
        independent_review.attempt.job_id
    )
    assert any(
        item["job_id"] == void_review.attempt.job_id and item["independent"] is False
        for item in material["rejected_history"]
    )


def test_independent_reject_creates_exact_digest_bound_repair(tmp_path: Path) -> None:
    runtime, cycle, dispatches, root, planner, work, work_seal = (
        _cycle_through_completed_work(
            tmp_path,
            intent_id="CEO-CYCLE-REJECT-REPAIR",
            review_workers=["worker-b", "worker-b"],
        )
    )
    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    rejecting_review = dispatches[-1]
    plan_digest = runtime.jobs.get_job(work.attempt.job_id).plan_digest
    reject_body = _review_body(
        root_id=root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=str(plan_digest),
        target_job_id=work.attempt.job_id,
        target_attempt_id=work.attempt.attempt_id,
        target_result_digest=work_seal["role_result_digest"],
        repair_round=0,
        verdict="reject",
    )
    reject_seal, _ = _complete_ohf_role(
        runtime, rejecting_review, reject_body, identity_seed=3213
    )

    repair_created = cycle.run_once(root.job_id)
    assert repair_created.action == "REPAIR_CREATED"
    assert repair_created.command_id == (
        f"coo-cycle:{root.job_id}:create-repair:{work.attempt.job_id}:"
        f"{rejecting_review.attempt.job_id}:{reject_seal['role_result_digest']}:1"
    )
    with pytest.raises(StateConflict, match="current|replacement"):
        runtime.jobs.create_cycle_review(
            root.job_id,
            work.attempt.job_id,
            command_id=(
                f"coo-cycle:{root.job_id}:create-review:{work.attempt.job_id}:2"
            ),
        )
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    repair = dispatches[-1]
    repair_body = {
        "schema_version": "mastermind.repair_result/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner.attempt.attempt_id,
        "plan_digest": str(plan_digest),
        "plan_step_id": "step-1",
        "repair_round": 1,
        "supersedes_job_id": work.attempt.job_id,
        "rejected_review_job_id": rejecting_review.attempt.job_id,
        "rejected_review_result_digest": reject_seal["role_result_digest"],
        "artifacts": [],
        "evidence_digests": [],
    }
    repair_seal, _ = _complete_ohf_role(
        runtime, repair, repair_body, identity_seed=3214
    )
    with pytest.raises(StateConflict, match="review|approval|current"):
        runtime.jobs.create_cycle_handoff(
            root.job_id,
            command_id=f"coo-cycle:{root.job_id}:aggregation-handoff:1",
        )
    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    repair_review = dispatches[-1]
    approve_repair = _review_body(
        root_id=root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=str(plan_digest),
        target_job_id=repair.attempt.job_id,
        target_attempt_id=repair.attempt.attempt_id,
        target_result_digest=repair_seal["role_result_digest"],
        repair_round=1,
        verdict="approve",
    )
    _complete_ohf_role(runtime, repair_review, approve_repair, identity_seed=3215)
    assert cycle.run_once(root.job_id).action == "HANDOFF_CREATED"
    handoff = runtime.jobs.get_cycle_handoff(root.job_id)
    assert handoff["revisions"][0]["current_job_id"] == repair.attempt.job_id
    assert handoff["revisions"][0]["repair_round"] == 1


def test_run_once_typed_plan_work_independent_review_and_aggregation_complete(
    tmp_path: Path,
) -> None:
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    _register(runtime, "worker-b")
    receipt = submit_intent(
        runtime, _v2_intent(intent_id="CEO-CYCLE-HAPPY-TYPED")
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    dispatches: list[OrchestrationDispatchOutcome] = []

    def accepted_dispatch(job_id: str, command_id: str):
        job = runtime.jobs.get_job(job_id)
        worker = "worker-b" if job and job.orchestration_role == "review" else "worker-a"
        outcome = runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id=worker
        )
        assert outcome is not None
        dispatches.append(outcome)
        return outcome

    cycle = CooCycle(runtime, dispatcher=accepted_dispatch)
    assert cycle.run_once(root.job_id).action == "PLANNER_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    planner_dispatch = dispatches[-1]
    plan_body = {
        "schema_version": "mastermind.execution_plan/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner_dispatch.attempt.attempt_id,
        "steps": [
            {
                "ordinal": 0,
                "step_id": "step-1",
                "objective": "Perform one bounded read-only task.",
                "business_impact": "routine",
                "review_required": True,
                "requested_authorities": ["READ"],
                "allowed_write_paths": [],
                "validation_ids": [],
                "attempt_limit": 1,
                "cost_class": "small",
            }
        ],
    }
    _complete_ohf_role(runtime, planner_dispatch, plan_body, identity_seed=3101)
    admitted = cycle.run_once(root.job_id)
    assert admitted.action == "PLAN_ADMITTED"
    work_id = admitted.receipt["work_job_ids"][0]

    work_dispatched = cycle.run_once(root.job_id)
    assert work_dispatched.action == "DISPATCHED"
    work_dispatch = dispatches[-1]
    plan_digest = result_digest(plan_body)
    work_body = {
        "schema_version": "mastermind.work_result/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner_dispatch.attempt.attempt_id,
        "plan_digest": plan_digest,
        "plan_step_id": "step-1",
        "repair_round": 0,
        "artifacts": [],
        "evidence_digests": [],
    }
    work_seal, _ = _complete_ohf_role(
        runtime, work_dispatch, work_body, identity_seed=3102
    )
    assert work_dispatch.attempt.job_id == work_id

    created_review = cycle.run_once(root.job_id)
    assert created_review.action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    review_dispatch = dispatches[-1]
    review_body = {
        "schema_version": "mastermind.review_result/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner_dispatch.attempt.attempt_id,
        "plan_digest": plan_digest,
        "plan_step_id": "step-1",
        "reviewed_job_id": work_id,
        "reviewed_attempt_id": work_dispatch.attempt.attempt_id,
        "reviewed_result_digest": work_seal["role_result_digest"],
        "repair_round": 0,
        "verdict": "approve",
        "evidence_digests": [],
        "findings": [],
    }
    review_seal, _ = _complete_ohf_role(
        runtime, review_dispatch, review_body, identity_seed=3103
    )

    handoff_outcome = cycle.run_once(root.job_id)
    assert handoff_outcome.action == "HANDOFF_CREATED"
    handoff = runtime.jobs.get_cycle_handoff(root.job_id)
    assert handoff["revisions"][0]["qualifying_review_result_digest"] == (
        review_seal["role_result_digest"]
    )
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    aggregation_dispatch = dispatches[-1]
    aggregation_body = {
        "schema_version": "mastermind.aggregation_result/v1",
        "root_job_id": root.job_id,
        "handoff_digest": handoff["handoff_digest"],
        "policy_sha": handoff["policy_sha"],
        "plan_attempt_id": handoff["plan_attempt_id"],
        "plan_digest": handoff["plan_digest"],
        "revisions": [
            {
                key: item[key]
                for key in {
                    "ordinal",
                    "plan_step_id",
                    "current_job_id",
                    "current_attempt_id",
                    "current_result_digest",
                    "repair_round",
                    "review_required",
                    "qualifying_review_job_id",
                    "qualifying_review_attempt_id",
                    "qualifying_review_result_digest",
                }
            }
            for item in handoff["revisions"]
        ],
        "aggregate_summary": "One bounded reviewed result is ready.",
        "evidence_digests": [],
    }
    _complete_ohf_role(
        runtime, aggregation_dispatch, aggregation_body, identity_seed=3104
    )
    assert runtime.jobs.get_job(root.job_id).status is executive_runtime.JobStatus.COMPLETED
    assert cycle.run_once(root.job_id).action == "NO_ACTION"


def test_run_once_without_accepted_supervisor_blocks_before_claim(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    receipt = submit_intent(
        runtime, _v2_intent(intent_id="CEO-CYCLE-NO-SUPERVISOR")
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    created = CooCycle(runtime).run_once(root.job_id)
    planner_id = str(created.selected_job_id)

    blocked = CooCycle(runtime).run_once(root.job_id)

    assert blocked.action == "BLOCKED"
    assert blocked.receipt["reason"] == "exact_dispatch_unavailable"
    assert runtime.attempts.list_attempts(planner_id) == []
    assert runtime.jobs.get_job(planner_id).status is executive_runtime.JobStatus.QUEUED


def test_run_once_cycle_blocks_non_v2_root_without_touching_unrelated_job(tmp_path):
    runtime = Runtime.at(tmp_path)
    invalid = runtime.jobs.create_job("legacy root")
    sentinel = runtime.jobs.create_job("unrelated sentinel")

    outcome = CooCycle(runtime).run_once(invalid.job_id)

    assert outcome.action == "BLOCKED"
    assert outcome.receipt["reason"] == "invalid_root"
    assert runtime.jobs.get_job(sentinel.job_id) == sentinel
    assert runtime.attempts.list_attempts() == []


def test_run_once_cycle_persists_reviewed_policy_digest_when_policy_is_invalid(
    tmp_path, monkeypatch
):
    runtime = Runtime.at(tmp_path)
    receipt = submit_intent(runtime, _v2_intent(intent_id="CEO-CYCLE-BAD-POLICY"))
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None

    def invalid_policy():
        raise executive_coo_cycle.CooCyclePolicyError("fixture policy drift")

    monkeypatch.setattr(
        executive_coo_cycle.CooCyclePolicy, "load", staticmethod(invalid_policy)
    )
    outcome = CooCycle(runtime).run_once(root.job_id)

    assert outcome.action == "BLOCKED"
    assert outcome.receipt["reason"] == "invalid_policy"
    assert outcome.receipt["policy_sha"] == executive_coo_cycle.EXPECTED_POLICY_SHA256
    assert outcome.receipt["evidence"] == {"error_type": "CooCyclePolicyError"}


def test_five_role_schema_golden_digests_are_frozen():
    assert GOLDEN_ROLE_SCHEMA_DIGESTS == {
        "plan": "8413f6b0777e2adceff2a9fd262760bf1d01c5cc92314e6abb5f8dc1079bbbe4",
        "work": "cc4953a932c9e4031dbdcdc6e444a77381cce12acf6a06f33b095f626d3b5f89",
        "review": "a0e853358f325d95b9d94c61161c40e7e7bae67e44679614b5ebea229b3d102c",
        "repair": "2f105a0b3c3bd55c0118fb003b13dd25e7074402d8d963d294944341ea47f90f",
        "aggregation": "7a042278d90f4d3e477c5f9d4c51a8553c64ac53947a70ccb40e96fea55ca933",
    }


def test_coo_cycle_cli_help_is_inert_and_requires_existing_runtime_root(tmp_path):
    from scripts.executive_os_coo_cycle import _parser

    script = Path(__file__).parents[1] / "scripts" / "executive_os_coo_cycle.py"
    before = sorted(tmp_path.rglob("*"))
    top_help = subprocess.run(
        ["python3", str(script), "--help"],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    run_help = subprocess.run(
        ["python3", str(script), "run-once", "--help"],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert top_help.returncode == 0 and run_help.returncode == 0
    assert "--root" in top_help.stdout
    assert "--parent" in run_help.stdout
    assert "--root" not in run_help.stdout
    exact_form = _parser().parse_args(["run-once", "--parent", "JOB-nnn"])
    assert exact_form.root == Path(__file__).parents[1]
    overridden = _parser().parse_args(
        ["--root", str(tmp_path), "run-once", "--parent", "JOB-nnn"]
    )
    assert overridden.root == tmp_path
    assert sorted(tmp_path.rglob("*")) == before


def test_offline_acceptance_receipt_is_deterministic_and_proves_tx9_quarantine():
    receipt = run_acceptance("90db9baf5bcc5f2221e3c9870c2aa09a95293c99")
    assert receipt["cycle"]["actions"] == [
        "PLANNER_CREATED",
        "DISPATCHED",
        "BLOCKED",
    ]
    assert receipt["cycle"]["planner_attempt_count"] == 1
    assert len(receipt["cycle"]["supervisor_dispatch_calls"]) == 1
    assert receipt["cycle"]["replay_matches_blocked"] is True
    assert receipt["cycle"]["events_before_replay"] == (
        receipt["cycle"]["events_after_replay"]
    )
    assert receipt["receipt_digest"] == (
        "1becf689c3a66999fd057276cc9354a10e461a96d18e1026994aad484d8d268a"
    )
    assert receipt["dispatch_boundary"]["acceptance_digest"] == (
        "02af618a1a926bde4b6a92fb2e697aa3b2d41538ae81350dbd954891a5dd2bcc"
    )
    assert receipt["dispatch_crash_replay"]["acceptance_digest"] == (
        "a0a176226052ee6cc43f2948d53bbb3ac68157795cbaf09cae3932e0a35e2bdf"
    )
    assert receipt["happy_path"]["acceptance_digest"] == (
        "ad407cf21645592cbfe420dda862ee7946874829559ffd194c6815fd320f4d8a"
    )
    assert receipt["repair_path"]["acceptance_digest"] == (
        "97d3c734230dd430733eb9f5cd8a52bd6f1263f42d09ba7ad65d80069eae63f2"
    )
    assert receipt["void_replacement"]["acceptance_digest"] == (
        "be6176fa45f80467923b9c283e9b696f303a4ed2fea5b9e655c8971afcc96b62"
    )
    assert receipt["cycle"]["acceptance_digest"] == (
        "8453e9c1fe127bef1d8b67d7f01bd441dc5e4bf6c210d52b9400603f5f1a914c"
    )
    assert receipt["tx9"]["acceptance_digest"] == (
        "9a43476a06fb3ecc4351b96d5646c7b0e521fd30092c3882bc5e8d4532825585"
    )
    assert receipt["tx9"]["quota_byte_state_equal"] is True
    assert receipt["tx9"]["quarantined_worker_excluded"] is True
    assert receipt["dispatch_boundary"]["attempt_count"] == 0
    assert receipt["dispatch_boundary"]["blocked_reason"] == (
        "exact_dispatch_unavailable"
    )
    assert receipt["inertness"] == {
        "temporary_runtime_boundary": True,
        "runtime_roots_removed_on_exit": True,
        "provider_adapters_constructed": 0,
        "provider_calls": 0,
        "executive_supervisor_fixture_instances": 6,
        "host_install_or_migration_calls": 0,
        "production_armed": False,
    }
