"""SQLite integration coverage for the production-inert OHF P1B state plane."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import replace

import pytest

from control_plane.executive_runtime import (
    OHF_CHECKPOINT_OPERATION_SCHEMA_VERSION,
    OrchestrationDispatchOutcome,
    Runtime,
    RuntimeStore,
    StateConflict,
    _json_dumps,
    _json_loads,
)
from control_plane.operator_harness_contract import (
    AuthRealmFact,
    AuthRealmRequirement,
    CapabilityManifest,
    CandidateResult,
    CheckpointObservation,
    EventCursor,
    NativeHelperPolicy,
    NormalizedEvent,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    OperationReceiptKind,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    TurnRef,
    TurnStartObservation,
    WorkspaceIdentity,
    operation_receipt_command_id,
)
from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.executive_orchestration_principal import (
    OperatorPrincipalObservation,
)


def _lease(tmp_path):
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker(
        "worker-01", provider="codex", account_label="one", worker_type="test"
    )
    job = runtime.jobs.create_job("OHF state-plane test")
    lease = runtime.attempts.claim_job(job.job_id)
    assert lease is not None
    return runtime, lease


def _profile(lease):
    return RequestedExecutionProfile(
        worker_id=lease.attempt.worker_id,
        provider="codex",
        requested_model="test-model",
        harness_kind="fake",
        harness_binary_digest="a" * 64,
        harness_version="1",
        workspace=WorkspaceIdentity("/tmp/work", "b" * 40, 1, 2, 3, 4),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash=lease.attempt.authority_policy_hash,
        auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
    )


def _attestation(profile):
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


def _started(tmp_path):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    profile = _profile(lease)
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
    )
    operation = OperationId("ohf-op:checkpoint-fixture-start")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=operation,
    )
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=operation,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(101, 101, "start", "boot"),
    )
    return runtime, lease, epoch, generation


def _checkpoint(candidate):
    return CheckpointObservation(
        {"summary": "checkpoint", "current_state": candidate}
    )


def _commit(runtime, lease, generation, suffix, candidate="first"):
    harness = runtime.operator_harness
    operation = OperationId(f"ohf-op:{suffix}")
    harness.reserve_checkpoint_operation(
        generation=generation,
        operation_id=operation,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    return harness.apply_checkpoint_operation(
        generation=generation,
        operation_id=operation,
        observation=_checkpoint(candidate),
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )


def _raw_generation(generation, *, number=None, worker=None):
    return replace(
        generation,
        generation_number=generation.generation_number
        if number is None
        else number,
        worker_id=generation.worker_id if worker is None else worker,
    )


def test_cctx0_checkpoint_generation_ownership_is_exact(tmp_path):
    runtime, lease, _epoch, generation = _started(tmp_path)
    harness = runtime.operator_harness
    wrong_number = _raw_generation(generation, number=2)
    wrong_worker = _raw_generation(generation, worker="intruder")
    for bad in (wrong_number, wrong_worker):
        with pytest.raises(
            StateConflict,
            match=r"^OHF epoch/generation refs are not exactly owned by the lease$",
        ):
            harness.reserve_checkpoint_operation(
                generation=bad,
                operation_id=OperationId(
                    f"ohf-op:reserve-{bad.generation_number}-{bad.worker_id}"
                ),
                fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
            )
    for bad in (wrong_number, wrong_worker):
        operation = OperationId(
            f"ohf-op:apply-{bad.generation_number}-{bad.worker_id}"
        )
        with pytest.raises(
            StateConflict,
            match=r"^OHF epoch/generation refs are not exactly owned by the lease$",
        ):
            harness.apply_checkpoint_operation(
                generation=bad,
                operation_id=operation,
                observation=_checkpoint("bad"),
                fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
            )
    writer_operation = OperationId("ohf-op:checkpoint-writer-held")
    harness.reserve_checkpoint_operation(
        generation=generation,
        operation_id=writer_operation,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE process_generations SET executive_writer_held=0 WHERE process_generation_id=?",
            (generation.process_generation_id,),
        )
    for call in (
        lambda: harness.reserve_checkpoint_operation(
            generation=generation,
            operation_id=OperationId("ohf-op:checkpoint-writer-reserve"),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        ),
        lambda: harness.apply_checkpoint_operation(
            generation=generation,
            operation_id=writer_operation,
            observation=_checkpoint("writer"),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        ),
    ):
        with pytest.raises(StateConflict, match="OHF epoch/generation refs"):
            call()
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE process_generations SET executive_writer_held=1 WHERE process_generation_id=?",
            (generation.process_generation_id,),
        )
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE harness_session_epochs SET state='TERMINAL' WHERE session_epoch_id=?",
            (generation.session_epoch_id,),
        )
    for call in (
        lambda: harness.reserve_checkpoint_operation(
            generation=generation,
            operation_id=OperationId("ohf-op:cctx-terminal-reserve"),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        ),
        lambda: harness.apply_checkpoint_operation(
            generation=generation,
            operation_id=writer_operation,
            observation=_checkpoint("terminal"),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        ),
    ):
        with pytest.raises(StateConflict, match="OHF epoch/generation refs"):
            call()
    for fence, token in (
        (lease.attempt.fence_generation + 1, lease.lease_token),
        (lease.attempt.fence_generation, "wrong-token"),
    ):
        with pytest.raises(StateConflict):
            harness.reserve_checkpoint_operation(
                generation=generation,
                operation_id=OperationId(
                    f"ohf-op:fence-{fence}-{bool(token == 'wrong-token')}"
                ),
                fence_generation=fence,
                lease_token=token,
            )


def test_cctx0_checkpoint_sequence_is_monotonic_and_intents_are_stale_closed(tmp_path):
    runtime, lease, _epoch, generation = _started(tmp_path)
    harness = runtime.operator_harness
    first = _commit(runtime, lease, generation, "checkpoint-1", "candidate-1")
    assert first.checkpoint["current_state"] == "candidate-1"
    stale = OperationId("ohf-op:checkpoint-stale")
    harness.reserve_checkpoint_operation(
        generation=generation,
        operation_id=stale,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    second = _commit(runtime, lease, generation, "checkpoint-2", "candidate-2")
    assert second.checkpoint["current_state"] == "candidate-2"
    with pytest.raises(StateConflict, match="does not match INTENT"):
        harness.apply_checkpoint_operation(
            generation=generation,
            operation_id=stale,
            observation=_checkpoint("late"),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    attempt = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert attempt is not None
    assert attempt.checkpoint_sequence == 2
    with runtime.store.read() as connection:
        stored_attempt = connection.execute(
            "SELECT checkpoint_json FROM attempts WHERE attempt_id=?",
            (lease.attempt.attempt_id,),
        ).fetchone()
    assert stored_attempt is not None
    assert stored_attempt["checkpoint_json"] == _json_dumps(second.checkpoint)
    events = runtime.events.list_events(job_id=str(lease.attempt.job_id))
    payloads = [
        event.payload["checkpoint_sequence"]
        for event in events
        if event.event_type == "JOB_CHECKPOINTED"
    ]
    assert payloads == [1, 2]


def test_cctx0_checkpoint_operation_replay_is_idempotent(tmp_path):
    runtime, lease, _epoch, generation = _started(tmp_path)
    harness = runtime.operator_harness
    operation = OperationId("ohf-op:checkpoint-replay")
    harness.reserve_checkpoint_operation(
        generation=generation,
        operation_id=operation,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    observation = _checkpoint("replay")
    first = harness.apply_checkpoint_operation(
        generation=generation,
        operation_id=operation,
        observation=observation,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    second = harness.apply_checkpoint_operation(
        generation=generation,
        operation_id=operation,
        observation=observation,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    assert second == first
    with pytest.raises(StateConflict, match="checkpoint operation INTENT preconditions failed"):
        harness.reserve_checkpoint_operation(
            generation=generation,
            operation_id=operation,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    with pytest.raises(StateConflict, match="does not match INTENT"):
        harness.apply_checkpoint_operation(
            generation=generation,
            operation_id=OperationId("ohf-op:checkpoint-no-intent"),
            observation=observation,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    with runtime.store.read() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='JOB_CHECKPOINTED'"
        ).fetchone()[0]
    assert count == 1


def test_cctx0_checkpoint_survives_runtime_restart_and_preserves_intent(tmp_path):
    runtime, lease, _epoch, generation = _started(tmp_path)
    harness = runtime.operator_harness
    _commit(runtime, lease, generation, "restart-1", "restart-candidate-1")
    pending = OperationId("ohf-op:restart-pending")
    harness.reserve_checkpoint_operation(
        generation=generation,
        operation_id=pending,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    database = tmp_path / "data" / "control_plane" / "executive.sqlite3"
    restarted = Runtime.from_store(
        RuntimeStore(tmp_path, database_path=database)
    )
    attempt = restarted.attempts.get_attempt(lease.attempt.attempt_id)
    assert attempt is not None and attempt.checkpoint_sequence == 1
    job = restarted.jobs.get_job(str(lease.attempt.job_id))
    assert job is not None
    assert job.checkpoint["current_state"] == "restart-candidate-1"
    with restarted.store.read() as connection:
        stored = connection.execute(
            "SELECT checkpoint_json FROM attempts WHERE attempt_id=?",
            (lease.attempt.attempt_id,),
        ).fetchone()
    assert stored is not None
    assert _json_loads(stored["checkpoint_json"], fallback={}) == job.checkpoint
    applied = restarted.operator_harness.apply_checkpoint_operation(
        generation=generation,
        operation_id=pending,
        observation=_checkpoint("restart-candidate-2"),
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    assert applied.checkpoint["current_state"] == "restart-candidate-2"


def _orchestration_checkpoint_fixture(tmp_path):
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker(
        "worker-a",
        provider="codex",
        account_label="worker-a@company",
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
    receipt = submit_intent(
        runtime,
        {
            "schema": INTENT_SCHEMA_V2,
            "intent_id": "CEO-CCTX0-D7",
            "actor": "ceo-sol",
            "objective": "CCTX0 generation-bound checkpoint fence",
            "department": "executive-infrastructure",
            "priority": 9,
            "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
            "execution_contract": {
                "requested_authorities": ["READ"],
                "attempt_limit": 2,
            },
            "intent_kind": "executive_coo_cycle",
            "business_impact": "material",
        },
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    planner = runtime.jobs.create_cycle_planner(
        root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0"
    )
    dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=(
            f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"
        ),
        worker_id="worker-a",
    )
    assert isinstance(dispatch, OrchestrationDispatchOutcome)
    assert dispatch.lease_token is not None
    harness = runtime.operator_harness

    class DispatchLease:
        attempt = dispatch.attempt

    profile = _profile(DispatchLease())
    sealed = harness.seal_operator_harness_attempt(
        dispatch.attempt.attempt_id,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
    )
    start = OperationId("ohf-op:cctx0-d7-start")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        operation_id=start,
    )
    process = ProcessIdentityObservation(2101, 2101, "cctx0-start", "boot")
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=start,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        provider_session_id="S1",
        process=process,
    )
    principal = OperatorPrincipalObservation(
        attempt_id=sealed.attempt_id,
        worker_id=sealed.worker_id,
        process_generation_id=generation.process_generation_id,
        provider_session_id="S1",
        process_identity={
            "pid": process.pid,
            "pgid": process.pgid,
            "process_start_identity": process.process_start_identity,
            "boot_id": process.boot_id,
        },
        os_principal_name="fixture-principal",
        os_principal_uid=os.getuid(),
        provider_home_identity={
            "path": "/tmp/cctx0-codex-home",
            "device": 1,
            "inode": 2,
            "uid": os.getuid(),
            "gid": os.getgid(),
            "mode": 0o700,
        },
        observed_at_ms=runtime.store.now_ms(),
    )
    harness.seal_attestation(
        generation=generation,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
        attestation=_attestation(profile),
        principal_observation=principal,
    )
    turn = harness.reserve_turn(
        epoch=epoch,
        generation=generation,
        operation_id=OperationId("ohf-op:cctx0-d7-turn"),
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
    )
    harness.acknowledge_turn(
        turn=turn,
        operation_id=OperationId("ohf-op:cctx0-d7-turn"),
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        observation=TurnStartObservation("native-cctx0", True),
    )
    checkpoint_operation = OperationId("ohf-op:cctx0-d7-checkpoint")
    harness.reserve_checkpoint_operation(
        generation=generation,
        operation_id=checkpoint_operation,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
    )
    harness.apply_checkpoint_operation(
        generation=generation,
        operation_id=checkpoint_operation,
        observation=_checkpoint("d7"),
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
    )
    harness.record_reconcile_observation(
        generation=generation,
        observation=ReconcileObservation(
            process_liveness=ProcessLiveness.PROVEN_DEAD,
            observed_process=process,
            provider_session_reachable=True,
            provider_writer_state=ProviderWriterState.RELEASED,
            observed_provider_session_id="S1",
        ),
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
    )
    return runtime, dispatch


def test_cctx0_checkpoint_closes_g1_and_legacy_refusal_remains(tmp_path):
    runtime, dispatch = _orchestration_checkpoint_fixture(tmp_path)
    assert dispatch.lease_token is not None
    start = runtime.events.get_event_by_command_id("ohf-op:cctx0-d7-start")
    assert start is not None
    epoch, generation = runtime.operator_harness.generation_refs(
        str(start.payload.get("process_generation_id") or "")
    )
    with pytest.raises(
        StateConflict,
        match="orchestration G1 recovery was closed by durable work evidence",
    ):
        runtime.operator_harness.reserve_same_epoch_resume(
            epoch=epoch,
            old_generation=generation,
            operation_id=OperationId("ohf-op:cctx0-d7-resume"),
            fence_generation=dispatch.attempt.fence_generation,
            lease_token=dispatch.lease_token,
        )
    with runtime.store.read() as connection:
        checkpoint_events = connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='JOB_CHECKPOINTED'",
        ).fetchone()[0]
    assert checkpoint_events == 1
    checkpoint_operation = OperationId("ohf-op:cctx0-d7-checkpoint")
    applied = runtime.events.get_event_by_command_id(
        operation_receipt_command_id(
            checkpoint_operation, OperationReceiptKind.APPLIED
        )
    )
    assert applied is not None
    assert (
        applied.payload["schema_version"]
        == OHF_CHECKPOINT_OPERATION_SCHEMA_VERSION
    )
    assert applied.payload["checkpoint_sequence"] == 1
    checkpoint_event = runtime.events.list_events(
        job_id=str(dispatch.attempt.job_id)
    )
    assert any(
        event.event_type == "JOB_CHECKPOINTED"
        and event.payload == {"checkpoint_sequence": 1}
        for event in checkpoint_event
    )
    with pytest.raises(
        StateConflict,
        match="orchestration OHF checkpoints require a generation-bound API",
    ):
        runtime.attempts.checkpoint_attempt(
            dispatch.attempt.attempt_id,
            fence_generation=dispatch.attempt.fence_generation,
            lease_token=dispatch.lease_token,
            payload={"legacy": "refused"},
        )


def test_tx1_to_tx5_is_event_plane_only_and_never_uses_legacy_identity(tmp_path):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    profile = _profile(lease)
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
    )
    assert sealed.execution_mode == "OPERATOR_HARNESS"
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        operation_id=OperationId("ohf-op:start-1"),
    )
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=OperationId("ohf-op:start-1"),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(11, 11, "start", "boot"),
    )
    assert harness.seal_attestation(
        generation=generation,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
        attestation=_attestation(profile),
    )
    turn = harness.reserve_turn(
        epoch=epoch,
        generation=generation,
        operation_id=OperationId("ohf-op:turn-1"),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    harness.acknowledge_turn(
        turn=turn,
        operation_id=OperationId("ohf-op:turn-1"),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    current = runtime.attempts.get_attempt(sealed.attempt_id)
    assert (
        current is not None
        and current.pid is None
        and current.provider_session_id is None
    )
    with pytest.raises(StateConflict, match="legacy Attempt identity"):
        runtime.attempts.record_process_exit(
            sealed.attempt_id,
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
            exit_code=0,
            provider_session_id="must-refuse",
        )
    assert runtime.events.get_event_by_command_id("ohf-op:turn-1:applied") is not None


def test_v3_writer_and_process_identity_constraints_are_enforced(tmp_path):
    runtime, lease = _lease(tmp_path)
    runtime.operator_harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=_profile(lease),
    )
    epoch, generation = runtime.operator_harness.reserve_start(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        operation_id=OperationId("ohf-op:constraint-1"),
    )
    with pytest.raises(StateConflict, match="database invariant"):
        with runtime.store.transaction() as connection:
            connection.execute(
                """
                INSERT INTO process_generations(
                    process_generation_id,session_epoch_id,worker_id,
                    generation_number,pid,pgid,process_start_identity,boot_id,
                    started_at_ms,executive_writer_held,provider_writer_state,
                    created_at_ms
                ) VALUES('other',?,?,2,1,1,NULL,'boot',1,1,'UNKNOWN',1)
                """,
                (epoch.session_epoch_id, lease.attempt.worker_id),
            )
    assert generation.generation_number == 1


def test_tx9_invalidates_only_rich_live_authority_and_preserves_session_evidence(
    tmp_path,
):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=_profile(lease),
    )
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=OperationId("ohf-op:restore-start"),
    )
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=OperationId("ohf-op:restore-start"),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(21, 21, "start", "boot"),
    )
    assert harness.invalidate_after_restore() == 1
    with runtime.store.read() as connection:
        attempt = connection.execute(
            "SELECT status FROM attempts WHERE attempt_id=?", (sealed.attempt_id,)
        ).fetchone()
        epoch_row = connection.execute(
            "SELECT state,provider_session_id FROM harness_session_epochs WHERE session_epoch_id=?",
            (epoch.session_epoch_id,),
        ).fetchone()
        generation_row = connection.execute(
            "SELECT executive_writer_held,provider_session_id FROM process_generations WHERE process_generation_id=?",
            (generation.process_generation_id,),
        ).fetchone()
    assert attempt["status"] == "LOST"
    assert tuple(epoch_row) == ("ABANDONED", "S1")
    assert tuple(generation_row) == (0, "S1")
    assert (
        runtime.events.get_event_by_command_id(f"ohf-restore:{sealed.attempt_id}")
        is not None
    )


def test_tx10_tx11_resume_uses_typed_intent_and_matching_replay_is_noop(tmp_path):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=_profile(lease),
    )
    epoch, g1 = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=OperationId("ohf-op:resume-start"),
    )
    harness.bind_start_result(
        epoch=epoch,
        generation=g1,
        operation_id=OperationId("ohf-op:resume-start"),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(31, 31, "start-1", "boot"),
    )
    profile = _profile(lease)
    harness.seal_attestation(
        generation=g1,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
        attestation=_attestation(profile),
    )
    harness.record_reconcile_observation(
        generation=g1,
        observation=ReconcileObservation(
            process_liveness=ProcessLiveness.PROVEN_DEAD,
            observed_process=ProcessIdentityObservation(31, 31, "start-1", "boot"),
            provider_session_reachable=True,
            provider_writer_state=ProviderWriterState.RELEASED,
            observed_provider_session_id="S1",
        ),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    op = OperationId("ohf-op:resume-1")
    g2 = harness.reserve_same_epoch_resume(
        epoch=epoch,
        old_generation=g1,
        operation_id=op,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    assert (
        harness.reserve_same_epoch_resume(
            epoch=epoch,
            old_generation=g1,
            operation_id=op,
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
        )
        == g2
    )
    assert (
        harness.bind_resume_result(
            epoch=epoch,
            generation=g2,
            operation_id=op,
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
            provider_session_id="S1",
            process=ProcessIdentityObservation(32, 32, "start-2", "boot"),
        )
        == g2
    )
    assert (
        harness.bind_resume_result(
            epoch=epoch,
            generation=g2,
            operation_id=op,
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
            provider_session_id="S1",
            process=ProcessIdentityObservation(32, 32, "start-2", "boot"),
        )
        == g2
    )
    with pytest.raises(StateConflict, match="already applied"):
        harness.bind_resume_result(
            epoch=epoch,
            generation=g2,
            operation_id=op,
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
            provider_session_id="S1",
            process=ProcessIdentityObservation(33, 33, "changed", "boot"),
        )


def test_tx8_abandoned_epoch_allocates_exact_next_epoch_without_writer_steal(tmp_path):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    profile = _profile(lease)
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
    )
    e1, g1 = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=OperationId("ohf-op:e1"),
    )
    harness.bind_start_result(
        epoch=e1,
        generation=g1,
        operation_id=OperationId("ohf-op:e1"),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(41, 41, "start-1", "boot"),
    )
    harness.record_hard_process_death(
        generation=g1,
        observation=ReconcileObservation(
            ProcessLiveness.PROVEN_DEAD,
            ProcessIdentityObservation(41, 41, "start-1", "boot"),
            True,
            ProviderWriterState.UNKNOWN,
            "S1",
        ),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    harness.abandon_epoch(
        epoch=e1,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )

    e2, g2 = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=OperationId("ohf-op:e2"),
    )
    assert e2.epoch_number == 2 and g2.generation_number == 1
    with runtime.store.read() as connection:
        assert (
            connection.execute(
                "SELECT SUM(executive_writer_held) FROM process_generations WHERE session_epoch_id=?",
                (e1.session_epoch_id,),
            ).fetchone()[0]
            == 0
        )


def test_applied_and_effect_unknown_are_mutually_exclusive(tmp_path):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    profile = _profile(lease)
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
    )
    op = OperationId("ohf-op:terminal-exclusive")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=op,
    )
    with pytest.raises(StateConflict, match="database invariant"):
        with runtime.store.transaction() as connection:
            connection.execute(
                """
                INSERT INTO process_generations(
                  process_generation_id,session_epoch_id,worker_id,
                  provider_session_id,generation_number,started_at_ms,
                  executive_writer_held,provider_writer_state,created_at_ms
                ) VALUES('inverse-session',?,?,'S1',2,1,0,'UNKNOWN',1)
                """,
                (epoch.session_epoch_id, lease.attempt.worker_id),
            )
    with pytest.raises(StateConflict, match="database invariant"):
        with runtime.store.transaction() as connection:
            connection.execute(
                """
                UPDATE process_generations SET provider_session_id='S1'
                WHERE process_generation_id=?
                """,
                (generation.process_generation_id,),
            )
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=op,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(51, 51, "start", "boot"),
    )
    assert (
        harness.record_effect_unknown(
            attempt_id=sealed.attempt_id,
            operation_id=op,
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
            phase="post_apply",
            detail="safe-code",
        )
        is False
    )
    assert (
        runtime.events.get_event_by_command_id(
            operation_receipt_command_id(op, OperationReceiptKind.EFFECT_UNKNOWN)
        )
        is None
    )


def test_candidate_requires_exact_tx5_intent_and_applied_provenance(tmp_path):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    profile = _profile(lease)
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
    )
    start = OperationId("ohf-op:candidate-start")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=start,
    )
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=start,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(61, 61, "start", "boot"),
    )
    harness.seal_attestation(
        generation=generation,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
        attestation=_attestation(profile),
    )
    op = OperationId("ohf-op:candidate-turn")
    turn = harness.reserve_turn(
        epoch=epoch,
        generation=generation,
        operation_id=op,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    candidate = CandidateResult(
        turn.attempt_id,
        turn.session_epoch_id,
        turn.process_generation_id,
        "f" * 64,
        "Bearer sk-provider-secret user@example.com",
    )
    cursor = EventCursor(
        turn.attempt_id,
        turn.session_epoch_id,
        turn.process_generation_id,
        turn_id=turn.turn_id,
    )
    with pytest.raises(StateConflict, match="TX-5 APPLIED"):
        harness.record_candidate_evidence(
            turn=turn,
            candidate=candidate,
            events=(),
            cursor=cursor,
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
        )
    forged = TurnRef(
        "forged-turn",
        turn.session_epoch_id,
        turn.process_generation_id,
        turn.attempt_id,
    )
    with pytest.raises(StateConflict, match="TX-5 INTENT"):
        harness.record_candidate_evidence(
            turn=forged,
            candidate=candidate,
            events=(),
            cursor=EventCursor(
                turn.attempt_id,
                turn.session_epoch_id,
                turn.process_generation_id,
                turn_id="forged-turn",
            ),
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
        )
    harness.acknowledge_turn(
        turn=turn,
        operation_id=op,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    malicious_event = NormalizedEvent(
        turn.attempt_id,
        turn.session_epoch_id,
        turn.process_generation_id,
        turn.turn_id,
        "provider",
        provider_event_id="sk-event-secret",
        payload_redacted={"API_KEY": "must-not-persist"},
    )
    harness.record_candidate_evidence(
        turn=turn,
        candidate=candidate,
        events=(malicious_event,),
        cursor=cursor,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    with runtime.store.read() as connection:
        persisted = connection.execute(
            "SELECT payload_json FROM events WHERE command_id=?",
            (f"ohf-candidate:{turn.turn_id}",),
        ).fetchone()[0]
    assert "sk-provider-secret" not in persisted
    assert "user@example.com" not in persisted
    assert "must-not-persist" not in persisted


def test_raw_sql_cannot_mutate_ohf_identity_or_bound_session_projection(tmp_path):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=_profile(lease),
    )
    op = OperationId("ohf-op:immutable")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=op,
    )
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=op,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(71, 71, "start", "boot"),
    )
    with pytest.raises(StateConflict, match="database invariant"):
        with runtime.store.transaction() as connection:
            connection.execute(
                """
                INSERT INTO process_generations(
                  process_generation_id,session_epoch_id,worker_id,
                  provider_session_id,generation_number,started_at_ms,
                  executive_writer_held,provider_writer_state,created_at_ms
                ) VALUES('missing-session',?,?,NULL,2,1,0,'UNKNOWN',1)
                """,
                (epoch.session_epoch_id, lease.attempt.worker_id),
            )
    mutations = [
        (
            "UPDATE harness_session_epochs SET attempt_id='forged' WHERE session_epoch_id=?",
            epoch.session_epoch_id,
        ),
        (
            "UPDATE harness_session_epochs SET worker_id='forged' WHERE session_epoch_id=?",
            epoch.session_epoch_id,
        ),
        (
            "UPDATE harness_session_epochs SET epoch_number=9 WHERE session_epoch_id=?",
            epoch.session_epoch_id,
        ),
        (
            "UPDATE process_generations SET session_epoch_id='forged' WHERE process_generation_id=?",
            generation.process_generation_id,
        ),
        (
            "UPDATE process_generations SET provider_session_id=NULL WHERE process_generation_id=?",
            generation.process_generation_id,
        ),
        (
            "UPDATE process_generations SET provider_session_id='S2' WHERE process_generation_id=?",
            generation.process_generation_id,
        ),
    ]
    for sql, target in mutations:
        with pytest.raises(StateConflict, match="database invariant"):
            with runtime.store.transaction() as connection:
                connection.execute(sql, (target,))
    with runtime.store.read() as connection:
        assert (
            connection.execute(
                """
            SELECT e.provider_session_id,g.provider_session_id
            FROM harness_session_epochs e
            JOIN process_generations g
              ON g.session_epoch_id=e.session_epoch_id
            WHERE g.process_generation_id=?
            """,
                (generation.process_generation_id,),
            ).fetchone()[:]
            == ("S1", "S1")
        )


@pytest.mark.parametrize("same_worker", [True, False])
def test_other_attempt_lease_cannot_target_durable_refs(tmp_path, same_worker):
    runtime = Runtime.at(tmp_path)
    if same_worker:
        runtime.workers.register_worker(
            "shared",
            provider="codex",
            account_label="one",
            worker_type="test",
            quota_classes=("qa", "qb"),
        )
        workers = ("shared", "shared")
    else:
        runtime.workers.register_worker(
            "worker-a",
            provider="codex",
            account_label="one",
            worker_type="test",
            quota_classes=("qa",),
        )
        runtime.workers.register_worker(
            "worker-b",
            provider="codex",
            account_label="two",
            worker_type="test",
            quota_classes=("qb",),
        )
        workers = ("worker-a", "worker-b")
    leases = []
    for index, quota in enumerate(("qa", "qb")):
        job = runtime.jobs.create_job(
            f"job-{quota}", constraints={"eligible_quota_classes": [quota]}
        )
        lease = runtime.attempts.claim_job(
            job.job_id, worker_id=workers[index], quota_class=quota
        )
        assert lease is not None
        profile = _profile(lease)
        runtime.operator_harness.seal_operator_harness_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            requested=profile,
        )
        op = OperationId(f"ohf-op:{quota}-start")
        epoch, generation = runtime.operator_harness.reserve_start(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            operation_id=op,
        )
        runtime.operator_harness.bind_start_result(
            epoch=epoch,
            generation=generation,
            operation_id=op,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            provider_session_id=f"S-{quota}",
            process=ProcessIdentityObservation(
                801 if quota == "qa" else 802,
                801 if quota == "qa" else 802,
                f"start-{quota}",
                "boot",
            ),
        )
        runtime.operator_harness.seal_attestation(
            generation=generation,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            requested=profile,
            attestation=_attestation(profile),
        )
        leases.append((lease, epoch, generation))
    lease_a, epoch_a, _ = leases[0]
    lease_b, epoch_b, generation_b = leases[1]
    forged_epoch = type(epoch_a)(
        epoch_b.session_epoch_id,
        epoch_a.attempt_id,
        epoch_a.worker_id,
        epoch_b.epoch_number,
    )
    with pytest.raises(StateConflict, match="owned|exact"):
        runtime.operator_harness.reserve_turn(
            epoch=forged_epoch,
            generation=generation_b,
            operation_id=OperationId("ohf-op:cross-turn"),
            fence_generation=lease_a.attempt.fence_generation,
            lease_token=lease_a.lease_token,
        )
    with pytest.raises(StateConflict, match="owned"):
        runtime.operator_harness.reserve_same_epoch_resume(
            epoch=forged_epoch,
            old_generation=generation_b,
            operation_id=OperationId("ohf-op:cross-resume"),
            fence_generation=lease_a.attempt.fence_generation,
            lease_token=lease_a.lease_token,
        )

    turn_op = OperationId("ohf-op:target-turn")
    turn_b = runtime.operator_harness.reserve_turn(
        epoch=epoch_b,
        generation=generation_b,
        operation_id=turn_op,
        fence_generation=lease_b.attempt.fence_generation,
        lease_token=lease_b.lease_token,
    )
    forged_turn = TurnRef(
        turn_b.turn_id,
        turn_b.session_epoch_id,
        turn_b.process_generation_id,
        lease_a.attempt.attempt_id,
    )
    with pytest.raises(StateConflict, match="TX-5 target mismatch"):
        runtime.operator_harness.acknowledge_turn(
            turn=forged_turn,
            operation_id=turn_op,
            fence_generation=lease_a.attempt.fence_generation,
            lease_token=lease_a.lease_token,
        )
    forged_candidate = CandidateResult(
        forged_turn.attempt_id,
        forged_turn.session_epoch_id,
        forged_turn.process_generation_id,
        "f" * 64,
        "candidate",
    )
    forged_cursor = EventCursor(
        forged_turn.attempt_id,
        forged_turn.session_epoch_id,
        forged_turn.process_generation_id,
        turn_id=forged_turn.turn_id,
    )
    with pytest.raises(StateConflict, match="TX-5 INTENT"):
        runtime.operator_harness.record_candidate_evidence(
            turn=forged_turn,
            candidate=forged_candidate,
            events=(),
            cursor=forged_cursor,
            fence_generation=lease_a.attempt.fence_generation,
            lease_token=lease_a.lease_token,
        )
    assert (
        runtime.events.get_event_by_command_id(
            operation_receipt_command_id(turn_op, OperationReceiptKind.APPLIED)
        )
        is None
    )
    assert (
        runtime.events.get_event_by_command_id(f"ohf-candidate:{turn_b.turn_id}")
        is None
    )


def test_other_attempt_lease_cannot_poison_provider_dispatch(tmp_path):
    runtime = Runtime.at(tmp_path)
    leases = []
    for worker in ("worker-a", "worker-b"):
        runtime.workers.register_worker(
            worker,
            provider="codex",
            account_label=worker,
            worker_type="test",
        )
        job = runtime.jobs.create_job(f"dispatch-{worker}")
        lease = runtime.attempts.claim_job(job.job_id, worker_id=worker)
        assert lease is not None
        runtime.operator_harness.seal_operator_harness_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            requested=_profile(lease),
        )
        leases.append(lease)

    lease_a, lease_b = leases
    operation = OperationId("ohf-op:dispatch-owner-a")
    runtime.operator_harness.reserve_start(
        lease_a.attempt.attempt_id,
        fence_generation=lease_a.attempt.fence_generation,
        lease_token=lease_a.lease_token,
        operation_id=operation,
    )
    with pytest.raises(StateConflict, match="matching operation INTENT"):
        runtime.operator_harness.commit_provider_dispatch(
            attempt_id=lease_b.attempt.attempt_id,
            operation_id=operation,
            operation_kind="start_session",
            fence_generation=lease_b.attempt.fence_generation,
            lease_token=lease_b.lease_token,
        )
    assert (
        runtime.events.get_event_by_command_id(f"{operation.command_id}:dispatch")
        is None
    )
    assert runtime.operator_harness.commit_provider_dispatch(
        attempt_id=lease_a.attempt.attempt_id,
        operation_id=operation,
        operation_kind="start_session",
        fence_generation=lease_a.attempt.fence_generation,
        lease_token=lease_a.lease_token,
    )
