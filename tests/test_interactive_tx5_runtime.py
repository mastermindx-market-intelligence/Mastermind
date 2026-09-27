from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.executive_operator_supervisor import (
    ExecutiveOperatorSupervisor,
    ExecutiveOperatorSupervisorError,
)
from control_plane.executive_orchestration_result import (
    RESULT_SCHEMA,
    RawRoleResultObservation,
    canonical_bytes,
)
from control_plane.executive_orchestration_principal import (
    OperatorPrincipalObservation,
)
from control_plane.executive_coo_cycle import CooCycle, CooCyclePolicy
from control_plane.executive_runtime import (
    AttemptLease,
    JobStatus,
    INTERACTIVE_TX5_EXECUTION_PROFILE,
    INTERACTIVE_TX5_MAX_TURNS_PER_GENERATION,
    orchestration_digest,
    OrchestrationDispatchOutcome,
    Runtime,
    StateConflict,
    _json_dumps,
    _COO_CYCLE_PLANNER_CREATION_CAPABILITY,
    _interactive_in_flight_turn_id,
)
from control_plane.operator_harness_contract import (
    AuthRealmFact,
    AuthRealmRequirement,
    CandidateResult,
    CapabilityManifest,
    EventCursor,
    NativeHelperPolicy,
    NormalizedEvent,
    ObservedHarnessAttestation,
    ObservedCapabilityIdentity,
    OperationId,
    OperationReceiptKind,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    TurnStartObservation,
    WorkspaceIdentity,
    ObservedTriState,
    operation_receipt_command_id,
)


def _intent(intent_id: str) -> dict:
    return {
        "schema": INTENT_SCHEMA_V2,
        "intent_id": intent_id,
        "actor": "ceo-sol",
        "objective": "Operate one bounded interactive session.",
        "department": "executive-infrastructure",
        "priority": 9,
        "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
        "execution_contract": {
            "requested_authorities": ["READ"],
            "attempt_limit": 2,
        },
        "intent_kind": "executive_coo_cycle",
        "business_impact": "routine",
    }


def _profile(lease: OrchestrationDispatchOutcome) -> RequestedExecutionProfile:
    attempt = lease.attempt
    return RequestedExecutionProfile(
        worker_id=attempt.worker_id,
        provider="openai-codex",
        requested_model="gpt-5.6-sol",
        harness_kind="codex-app-server",
        harness_binary_digest="a" * 64,
        harness_version="0.147.0",
        workspace=WorkspaceIdentity(
            "/tmp/mastermind-interactive", "b" * 40, 1, 2, os.getuid(), os.getgid()
        ),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash=attempt.authority_policy_hash,
        auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
    )


def _json_dumps_loads(value: str) -> dict:
    return json.loads(value)


def _attestation(profile: RequestedExecutionProfile) -> ObservedHarnessAttestation:
    observed = tuple(
        ObservedCapabilityIdentity(
            kind=item.kind,
            name=item.name,
            skill_content_digest=item.skill_content_digest,
            tool_schema_digest=item.tool_schema_digest,
            mcp_server_identity=item.mcp_server_identity,
            mcp_server_version=item.mcp_server_version,
            mcp_auth_status=item.mcp_auth_status,
            resource_contract_digest=item.resource_contract_digest,
        )
        for item in profile.capabilities.required
    )
    return ObservedHarnessAttestation(
        served_model=profile.requested_model,
        harness_version=profile.harness_version,
        harness_binary_digest=profile.harness_binary_digest,
        capabilities=observed,
        effective_skills=(),
        effective_mcp=(),
        effective_plugins_or_apps=(),
        sandbox_state=profile.sandbox_policy,
        approval_state=profile.approval_policy,
        network_state=profile.network_policy,
        effective_config_digest=profile.expected_config_digest or "d" * 64,
        auth=AuthRealmFact(worker_id=profile.worker_id, provider=profile.provider),
        workspace=profile.workspace,
        supports_subagent_capability_ceiling=ObservedTriState.FALSE,
    )


def _started_interactive(tmp_path: Path):
    now_ms = 1_800_000_000_000
    runtime = Runtime.at(
        tmp_path / "runtime",
        clock=lambda: now_ms,
        lease_seconds=3_600,
    )
    runtime.workers.register_worker(
        "worker-a",
        provider="codex",
        account_label="worker-a@company",
        worker_type="fixture",
        capabilities=["read", "research"],
        quota_classes={
            "default": {
                "provider": "codex",
                "capabilities": ["read", "research"],
                "cost_class": "small",
                "metadata": {
                    "routing_policy_version": "interactive-routing",
                    "execution_profile_id": INTERACTIVE_TX5_EXECUTION_PROFILE,
                    "execution_profile_digest": (
                        ExecutionCapabilityRegistry.load()
                        .resolve(INTERACTIVE_TX5_EXECUTION_PROFILE)
                        .profile_digest
                    ),
                    "capability_policy_version": (
                        ExecutionCapabilityRegistry.load().policy_version
                    ),
                    "capability_policy_digest": (
                        ExecutionCapabilityRegistry.load().policy_digest
                    ),
                },
            }
        },
    )
    receipt = submit_intent(runtime, _intent("CEO-INTERACTIVE-FIXTURE"))
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    parent = runtime.jobs.create_interactive_operator(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-interactive:0",
    )
    assert parent.orchestration_role == "plan"
    assert parent.constraints["execution_profile_id"] == (
        INTERACTIVE_TX5_EXECUTION_PROFILE
    )
    dispatch = runtime.attempts.dispatch_cycle_job(
        parent.job_id,
        command_id=(
            f"coo-cycle:{root.job_id}:dispatch:{parent.job_id}:attempt:1"
        ),
        worker_id="worker-a",
    )
    assert isinstance(dispatch, OrchestrationDispatchOutcome)
    assert dispatch.lease_token is not None
    harness = runtime.operator_harness
    sealed = harness.seal_operator_harness_attempt(
        dispatch.attempt.attempt_id,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        requested=_profile(dispatch),
    )
    start = OperationId("ohf-op:interactive-start")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        operation_id=start,
    )
    process = ProcessIdentityObservation(2101, 2101, "interactive-start", "boot")
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=start,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        provider_session_id="SESSION-INTERACTIVE",
        process=process,
    )
    principal = OperatorPrincipalObservation(
        attempt_id=sealed.attempt_id,
        worker_id=sealed.worker_id,
        process_generation_id=generation.process_generation_id,
        provider_session_id="SESSION-INTERACTIVE",
        process_identity={
            "pid": process.pid,
            "pgid": process.pgid,
            "process_start_identity": process.process_start_identity,
            "boot_id": process.boot_id,
        },
        os_principal_name="fixture-principal",
        os_principal_uid=9301,
        provider_home_identity={
            "path": "/tmp/mastermind-interactive-home",
            "device": 1,
            "inode": 2,
            "uid": 9301,
            "gid": 9301,
            "mode": 0o700,
        },
        observed_at_ms=runtime.store.now_ms(),
    )
    harness.seal_attestation(
        generation=generation,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        requested=_profile(dispatch),
        attestation=_attestation(_profile(dispatch)),
        principal_observation=principal,
    )
    return runtime, root, parent, dispatch, epoch, generation


def _shutdown_interactive(
    runtime: Runtime,
    dispatch: OrchestrationDispatchOutcome,
    epoch,
    generation,
):
    runtime.operator_harness.record_reconcile_observation(
        generation=generation,
        observation=ReconcileObservation(
            ProcessLiveness.PROVEN_DEAD,
            ProcessIdentityObservation(2101, 2101, "interactive-start", "boot"),
            True,
            ProviderWriterState.RELEASED,
            "SESSION-INTERACTIVE",
        ),
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
    )
    runtime.operator_harness.abandon_epoch(
        epoch=epoch,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
    )


def _reserve_turn(
    runtime: Runtime,
    dispatch: OrchestrationDispatchOutcome,
    epoch,
    generation,
    ordinal: int,
):
    return runtime.operator_harness.reserve_turn(
        epoch=epoch,
        generation=generation,
        operation_id=OperationId(f"ohf-op:turn:{dispatch.attempt.attempt_id}:{ordinal}"),
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
    )


def _acknowledge_turn(
    runtime: Runtime,
    dispatch: OrchestrationDispatchOutcome,
    turn,
    operation_id: OperationId,
):
    runtime.operator_harness.acknowledge_turn(
        turn=turn,
        operation_id=operation_id,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
        observation=TurnStartObservation(f"native-{turn.turn_id}", True),
    )


def _record_candidate(
    runtime: Runtime,
    dispatch: OrchestrationDispatchOutcome,
    turn,
):
    runtime.operator_harness.record_candidate_evidence(
        turn=turn,
        candidate=CandidateResult(
            turn.attempt_id,
            turn.session_epoch_id,
            turn.process_generation_id,
            "e" * 64,
            f"collected {turn.turn_id}",
        ),
        events=(
            NormalizedEvent(
                turn.attempt_id,
                turn.session_epoch_id,
                turn.process_generation_id,
                turn.turn_id,
                "turn.completed",
                payload_redacted={"status": "complete"},
            ),
        ),
        cursor=EventCursor(
            turn.attempt_id,
            turn.session_epoch_id,
            turn.process_generation_id,
            local_sequence=1,
            turn_id=turn.turn_id,
        ),
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
    )


def _observation_for_plan(
    runtime: Runtime,
    dispatch: OrchestrationDispatchOutcome,
    epoch,
    generation,
    turn,
    envelope,
):
    canonical = canonical_bytes(envelope).decode("utf-8")
    return RawRoleResultObservation(
        attempt_id=dispatch.attempt.attempt_id,
        session_epoch_id=epoch.session_epoch_id,
        process_generation_id=generation.process_generation_id,
        turn_id=turn.turn_id,
        provider_session_id="SESSION-INTERACTIVE",
        provider_native_turn_id=f"native-{turn.turn_id}",
        provider_turn_artifact_digest="e" * 64,
        canonical_result_json=canonical,
        canonical_result_digest=hashlib.sha256(canonical.encode()).hexdigest(),
        canonical_result_byte_length=len(canonical.encode()),
    )


def _exact_target_admission_direct(
    runtime: Runtime,
    root,
    parent,
    dispatch,
    epoch,
    generation,
    *,
    epoch_id,
    provider_session_id,
    plan_envelope,
    selected_worker_id: str,
    selected_worker_uid: int,
):
    attempt = dispatch.attempt
    plan_turn, plan_seal = _sealed_plan_result(
        runtime, root, parent, dispatch, epoch, generation
    )
    del plan_turn
    members = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:admit-plan:{attempt.attempt_id}",
    )
    if len(members) != 1:
        raise StateConflict("UID fixture admitted an unexpected work cardinality")
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE worker_quota_classes SET metadata_json=? "
            "WHERE worker_id=? AND quota_class='default'",
            (_json_dumps({"broker_uid": selected_worker_uid}), selected_worker_id),
        )
    return members[0]


def _sealed_plan_result(runtime, root, parent, dispatch, epoch, generation):
    operation = OperationId(f"ohf-op:turn:{dispatch.attempt.attempt_id}:plan")
    turn = runtime.operator_harness.reserve_turn(
        epoch=epoch,
        generation=generation,
        operation_id=operation,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
    )
    _acknowledge_turn(runtime, dispatch, turn, operation)
    _record_candidate(runtime, dispatch, turn)
    envelope = _canonical_plan(runtime, root, dispatch)
    observation = _observation_for_plan(
        runtime, dispatch, epoch, generation, turn, envelope
    )
    return turn, runtime.operator_harness.seal_orchestration_role_result(
        turn=turn,
        observation=observation,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
    )


def test_interactive_survives_plan_seal_but_later_candidate_cannot_reseal(
    tmp_path: Path,
):
    runtime, root, parent, dispatch, epoch, generation = _started_interactive(
        tmp_path
    )
    sealed_turn, seal = _sealed_plan_result(
        runtime, root, parent, dispatch, epoch, generation
    )
    assert seal["job_id"] == parent.job_id
    second = _reserve_turn(runtime, dispatch, epoch, generation, 2)
    assert second.turn_id != sealed_turn.turn_id
    second_operation = OperationId(
        f"ohf-op:turn:{dispatch.attempt.attempt_id}:2"
    )
    _acknowledge_turn(runtime, dispatch, second, second_operation)
    _record_candidate(runtime, dispatch, second)
    with pytest.raises(
        StateConflict, match="role result seal command replay drifted"
    ):
        runtime.operator_harness.seal_orchestration_role_result(
            turn=second,
            observation=_observation_for_plan(
                runtime,
                dispatch,
                epoch,
                generation,
                second,
                _canonical_plan(runtime, root, dispatch),
            ),
            fence_generation=dispatch.attempt.fence_generation,
            lease_token=str(dispatch.lease_token),
        )
    assert runtime.jobs.get_job(parent.job_id).status.value == "RUNNING"
    assert runtime.jobs.create_interactive_operator(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-interactive:0",
    ).job_id == parent.job_id


def test_planner_second_generation_one_turn_remains_refused(tmp_path: Path):
    from control_plane.operator_harness_contract import TurnStartObservation

    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker(
        "worker-a",
        provider="codex",
        account_label="worker-a@company",
        worker_type="fixture",
        capabilities=["read", "research"],
        quota_classes={
            "default": {
                "provider": "codex",
                "capabilities": ["read", "research"],
                "cost_class": "small",
            }
        },
    )
    receipt = submit_intent(runtime, _intent("CEO-PLANNER-TX5"))
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    parent = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    dispatch = runtime.attempts.dispatch_cycle_job(
        parent.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{parent.job_id}:attempt:1",
        worker_id="worker-a",
    )
    assert isinstance(dispatch, OrchestrationDispatchOutcome)
    profile = _profile(dispatch)
    sealed = runtime.operator_harness.seal_operator_harness_attempt(
        dispatch.attempt.attempt_id,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
    )
    start = OperationId("ohf-op:planner-start")
    epoch, generation = runtime.operator_harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        operation_id=start,
    )
    runtime.operator_harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=start,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        provider_session_id="SESSION-PLANNER",
        process=ProcessIdentityObservation(3101, 3101, "planner", "boot"),
    )
    runtime.operator_harness.seal_attestation(
        generation=generation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
        attestation=_attestation(profile),
        principal_observation=OperatorPrincipalObservation(
            attempt_id=sealed.attempt_id,
            worker_id=sealed.worker_id,
            process_generation_id=generation.process_generation_id,
            provider_session_id="SESSION-PLANNER",
            process_identity={
                "pid": 3101,
                "pgid": 3101,
                "process_start_identity": "planner",
                "boot_id": "boot",
            },
            os_principal_name="fixture-principal",
            os_principal_uid=9401,
            provider_home_identity={
                "path": "/tmp/planner-home",
                "device": 1,
                "inode": 3,
                "uid": 9401,
                "gid": 9401,
                "mode": 0o700,
            },
            observed_at_ms=runtime.store.now_ms(),
        ),
    )
    first = runtime.operator_harness.reserve_turn(
        epoch=epoch,
        generation=generation,
        operation_id=OperationId("ohf-op:planner-turn:1"),
        fence_generation=sealed.fence_generation,
        lease_token=str(dispatch.lease_token),
    )
    runtime.operator_harness.acknowledge_turn(
        turn=first,
        operation_id=OperationId("ohf-op:planner-turn:1"),
        fence_generation=sealed.fence_generation,
        lease_token=str(dispatch.lease_token),
        observation=TurnStartObservation("native-planner", True),
    )
    with pytest.raises(StateConflict, match="orchestration TX-5 cardinality"):
        runtime.operator_harness.reserve_turn(
            epoch=epoch,
            generation=generation,
            operation_id=OperationId("ohf-op:planner-turn:2"),
            fence_generation=sealed.fence_generation,
            lease_token=str(dispatch.lease_token),
        )


def test_interactive_g2_allows_recovery_turn_only(tmp_path: Path):
    runtime, root, parent, dispatch, epoch, g1 = _started_interactive(tmp_path)
    operation = OperationId(f"ohf-op:turn:{dispatch.attempt.attempt_id}:g1")
    turn = runtime.operator_harness.reserve_turn(
        epoch=epoch,
        generation=g1,
        operation_id=operation,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
    )
    _acknowledge_turn(runtime, dispatch, turn, operation)
    interrupt = OperationId(f"ohf-op:interrupt:{turn.turn_id}")
    runtime.operator_harness.reserve_turn_operation(
        turn=turn,
        operation_id=interrupt,
        operation_kind="interrupt_turn",
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
    )
    runtime.operator_harness.apply_turn_operation(
        turn=turn,
        operation_id=interrupt,
        operation_kind="interrupt_turn",
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
    )
    runtime.operator_harness.record_reconcile_observation(
        generation=g1,
        observation=ReconcileObservation(
            ProcessLiveness.PROVEN_DEAD,
            ProcessIdentityObservation(2101, 2101, "interactive-start", "boot"),
            True,
            ProviderWriterState.RELEASED,
            "SESSION-INTERACTIVE",
        ),
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
    )
    resume = OperationId("ohf-op:interactive-resume")
    g2 = runtime.operator_harness.reserve_same_epoch_resume(
        epoch=epoch,
        old_generation=g1,
        operation_id=resume,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
    )
    process2 = ProcessIdentityObservation(2102, 2102, "interactive-resume", "boot")
    runtime.operator_harness.bind_resume_result(
        epoch=epoch,
        generation=g2,
        operation_id=resume,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
        provider_session_id="SESSION-INTERACTIVE",
        process=process2,
    )
    principal = runtime.operator_harness.admitted_principal_observation(g1)
    assert principal is not None
    profile = _profile(dispatch)
    runtime.operator_harness.seal_attestation(
        generation=g2,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
        requested=profile,
        attestation=_attestation(profile),
        principal_observation=OperatorPrincipalObservation.from_dict(
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
        ),
    )
    g2_operation = OperationId(f"ohf-op:turn:{dispatch.attempt.attempt_id}:g2")
    g2_turn = runtime.operator_harness.reserve_turn(
        epoch=epoch,
        generation=g2,
        operation_id=g2_operation,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
    )
    with pytest.raises(
        StateConflict,
        match="G1 recovery found a competing TX-5 INTENT",
    ):
        runtime.operator_harness.reserve_turn(
            epoch=epoch,
            generation=g2,
            operation_id=OperationId(f"ohf-op:turn:{dispatch.attempt.attempt_id}:g2-extra"),
            fence_generation=dispatch.attempt.fence_generation,
            lease_token=str(dispatch.lease_token),
        )
    _acknowledge_turn(runtime, dispatch, g2_turn, g2_operation)
    with pytest.raises(
        StateConflict,
        match="G1 recovery found a competing TX-5 INTENT",
    ):
        runtime.operator_harness.reserve_turn(
            epoch=epoch,
            generation=g2,
            operation_id=OperationId(
                f"ohf-op:turn:{dispatch.attempt.attempt_id}:g2-second"
            ),
            fence_generation=dispatch.attempt.fence_generation,
            lease_token=str(dispatch.lease_token),
        )
    assert runtime.jobs.get_job(parent.job_id).orchestration_role == "plan"


def test_interactive_supervisor_refuses_and_restart_reconciliation_skips(
    tmp_path: Path,
):
    runtime, root, parent, dispatch, epoch, generation = _started_interactive(
        tmp_path
    )
    _shutdown_interactive(runtime, dispatch, epoch, generation)
    supervisor = ExecutiveOperatorSupervisor(
        runtime,
        adapter_factory=lambda _loader: None,  # type: ignore[arg-type]
        prompt_source=lambda *args, **kwargs: "unused",  # type: ignore[arg-type]
    )
    job = runtime.jobs.get_job(parent.job_id)
    assert job is not None
    lease = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
    assert lease is not None
    with pytest.raises(
        ExecutiveOperatorSupervisorError,
        match="refuses the interactive profile before claim",
    ):
        supervisor._requested_profile(job, AttemptLease(lease, dispatch.lease_token))
    receipts = supervisor.reconcile_restart(requeue_lost=True)
    skipped = [
        receipt.attempt_id for receipt in receipts
        if receipt.attempt_id == dispatch.attempt.attempt_id
    ]
    assert skipped == [dispatch.attempt.attempt_id]
    assert runtime.attempts.get_attempt(
        dispatch.attempt.attempt_id
    ).status.value == "RUNNING"



def _interactive_identity_cases():
    return (
        "execution_profile_digest",
        "capability_policy_version",
        "capability_policy_digest",
    )


def _stored_parent_constraints(runtime: Runtime, parent) -> dict:
    with runtime.store.read() as connection:
        row = connection.execute(
            "SELECT constraints_json FROM jobs WHERE job_id=?", (parent.job_id,)
        ).fetchone()
    return json.loads(row["constraints_json"])


def _write_parent_constraints(runtime: Runtime, parent, constraints: dict) -> None:
    with runtime.store.transaction() as connection:
        updated = connection.execute(
            "UPDATE jobs SET constraints_json=? WHERE job_id=?",
            (_json_dumps(constraints), parent.job_id),
        )
        if updated.rowcount != 1:
            raise StateConflict("interactive identity fixture update failed")


def _identity_snapshot(runtime: Runtime, job_id: str) -> tuple[object, tuple]:
    return (
        runtime.jobs.get_job(job_id),
        tuple(runtime.attempts.list_attempts(job_id)),
        tuple(runtime.events.list_events(job_id=job_id)),
    )


def test_interactive_identity_fields_must_be_exact_current_and_nonempty(tmp_path):
    for field in _interactive_identity_cases():
        runtime, _root, parent, _dispatch, _epoch, _generation = (
            _started_interactive(tmp_path / f"malformed-{field}")
        )
        constraints = _stored_parent_constraints(runtime, parent)
        constraints[field] = {"unexpected": "type"}
        _write_parent_constraints(runtime, parent, constraints)
        with pytest.raises(
            StateConflict,
            match="interactive (stored capability identity is malformed|capability identity is stale)",
        ):
            runtime.operator_harness.reserve_turn(
                epoch=_epoch,
                generation=_generation,
                operation_id=OperationId(f"ohf-op:identity-malformed:{field}"),
                fence_generation=_dispatch.attempt.fence_generation,
                lease_token=str(_dispatch.lease_token),
            )

    for field in _interactive_identity_cases():
        runtime, _root, parent, _dispatch, _epoch, _generation = (
            _started_interactive(tmp_path / f"missing-{field}")
        )
        constraints = _stored_parent_constraints(runtime, parent)
        del constraints[field]
        _write_parent_constraints(runtime, parent, constraints)
        with pytest.raises(
            StateConflict,
            match="interactive stored capability identity is malformed",
        ):
            runtime.operator_harness.reserve_turn(
                epoch=_epoch,
                generation=_generation,
                operation_id=OperationId(f"ohf-op:identity-missing:{field}"),
                fence_generation=_dispatch.attempt.fence_generation,
                lease_token=str(_dispatch.lease_token),
            )


def test_interactive_identity_staleness_fails_closed(tmp_path, monkeypatch):
    from control_plane import executive_agent_capabilities as capabilities

    runtime, root, parent, _dispatch, _epoch, _generation = _started_interactive(
        tmp_path
    )
    stale_values = {
        "execution_profile_digest": "0" * 64,
        "capability_policy_version": "older-policy",
        "capability_policy_digest": "1" * 64,
    }
    for field, value in stale_values.items():
        constraints = _stored_parent_constraints(runtime, parent)
        constraints[field] = value
        _write_parent_constraints(runtime, parent, constraints)
        with pytest.raises(StateConflict, match="capability identity is stale"):
            runtime.operator_harness.reserve_turn(
                epoch=_epoch,
                generation=_generation,
                operation_id=OperationId(f"ohf-op:identity-stale:{field}"),
                fence_generation=_dispatch.attempt.fence_generation,
                lease_token=str(_dispatch.lease_token),
            )

    policy = tmp_path / "updated-capabilities.json"
    policy.write_text(
        Path(capabilities.DEFAULT_CAPABILITY_POLICY_PATH).read_text(), encoding="utf-8"
    )
    monkeypatch.setattr(capabilities, "DEFAULT_CAPABILITY_POLICY_PATH", policy)
    document = json.loads(policy.read_text())
    document["policy_version"] = "updated-20260927"
    policy.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(StateConflict, match="capability identity is stale"):
        runtime.operator_harness.reserve_turn(
            epoch=_epoch,
            generation=_generation,
            operation_id=OperationId("ohf-op:identity-stale-check"),
            fence_generation=_dispatch.attempt.fence_generation,
            lease_token=str(_dispatch.lease_token),
        )


def test_forged_interactive_profile_id_blocks_before_coo_no_action(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    runtime.workers.register_worker(
        "worker-a",
        provider="codex",
        account_label="worker-a@company",
        worker_type="fixture",
        capabilities=["read", "research"],
        quota_classes={"default": {"provider": "codex", "cost_class": "small"}},
    )
    receipt = submit_intent(runtime, _intent("CEO-FORGED-INTERACTIVE"))
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    profile = ExecutionCapabilityRegistry.load().resolve(
        INTERACTIVE_TX5_EXECUTION_PROFILE
    )
    registry = ExecutionCapabilityRegistry.load()
    forged = runtime.jobs.create_job(
        "Forged interactive profile child",
        department=root.department,
        priority=root.priority,
        authority_level=root.authority_level,
        branch=root.branch,
        worktree=root.worktree,
        constraints={
            "execution_profile_id": INTERACTIVE_TX5_EXECUTION_PROFILE,
            "execution_profile_digest": profile.profile_digest,
            "capability_policy_version": registry.policy_version,
            "capability_policy_digest": registry.policy_digest,
            "cost_class": "small",
        },
        attempt_limit=1,
        requested_authorities=["READ"],
        allowed_write_paths=[],
        validation_commands=[],
        command_id=f"coo-cycle:{root.job_id}:create-forged:0",
        parent_job_id=root.job_id,
        owner_seat="coo",
        escalation_target="coo",
        business_impact=root.business_impact,
        review_required=False,
        orchestration_role="plan",
        orchestration_provenance={
            "schema_version": (
                "mastermind.executive_orchestration_provenance_source/v1"
            ),
            "creator": "coo_cycle",
            "source_id": root.job_id,
            "source_digest": root.orchestration_provenance_digest,
        },
        _coo_cycle_planner_capability=_COO_CYCLE_PLANNER_CREATION_CAPABILITY,
    )
    outcome = CooCycle(runtime).run_once(root.job_id)
    assert outcome.action == "BLOCKED"
    assert outcome.receipt["reason"] == "lineage_invalid"
    assert forged.orchestration_provenance["command_id"] != (
        f"coo-cycle:{root.job_id}:create-interactive:0"
    )


def test_interactive_coo_pre_admission_skips_and_service_refuses(tmp_path):
    import asyncio

    from control_plane.executive_service import ExecutiveControlService, ServiceConfig

    runtime, root, parent, _dispatch, _epoch, _generation = _started_interactive(
        tmp_path
    )
    outcome = CooCycle(runtime).run_once(root.job_id)
    assert outcome.action == "NO_ACTION"
    assert outcome.receipt["reason"] == (
        "interactive_profile_not_owned_by_one_shot_cycle"
    )

    assert runtime.jobs.get_job(parent.job_id).status is JobStatus.RUNNING
    before = _identity_snapshot(runtime, parent.job_id)

    class RefusalSupervisor:
        def __init__(self):
            self.calls = 0

        async def start_cycle_job(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("interactive plan reached the planner supervisor")

        def reconcile_restart(self, *_args, **_kwargs):
            return []

    supervisor = RefusalSupervisor()
    config = ServiceConfig(
        runtime_root=tmp_path,
        socket_path=tmp_path / "executive.sock",
        proof_source_repository=tmp_path / "source",
        proof_workspace_root=tmp_path / "workspace",
        proof_base_sha="a" * 40,
        coo_autonomy_armed=True,
        coo_operator_harness_armed=True,
    )
    service = ExecutiveControlService(
        config,
        supervisor_factory=lambda _r: supervisor,
        autonomy_guard=lambda: None,
        operator_supervisor_factory=lambda _runtime, _supervisor: supervisor,
        operator_identity_verifier=lambda: None,
    )
    service.runtime = runtime
    service.operator_supervisor = supervisor
    service._require_bound_coo_job = lambda job: job
    command_id = (
        f"coo-cycle:{root.job_id}:dispatch:{parent.job_id}:attempt:2"
    )
    with pytest.raises(
        StateConflict,
        match="interactive plan Jobs are not routed to the planner supervisor",
    ):
        asyncio.run(service._dispatch_cycle_job_exact(parent.job_id, command_id))
    assert supervisor.calls == 0
    assert _identity_snapshot(runtime, parent.job_id) == before


def _uid_join_fixture(tmp_path: Path):
    runtime, root, parent, dispatch, _epoch, _generation = _started_interactive(
        tmp_path
    )
    runtime.workers.register_worker(
        "worker-b",
        provider="codex",
        account_label="worker-b-company",
        worker_type="fixture",
        capabilities=["read", "research"],
        quota_classes={
            "default": {
                "provider": "codex",
                "model": "gpt-5.6-sol",
                "effort": "xhigh",
                "capabilities": ["read", "research"],
                "cost_class": "small",
                "metadata": {"broker_uid": 9301},
            }
        },
    )
    parent = runtime.jobs.get_job(parent.job_id)
    assert parent is not None
    plan_envelope = {
        "schema_version": RESULT_SCHEMA,
        "job_id": parent.job_id,
        "run_id": dispatch.attempt.attempt_id,
        "worker_id": str(dispatch.attempt.worker_id),
        "role": "plan",
        "status": "COMPLETED",
        "role_result": {
            "schema_version": "mastermind.execution_plan/v1",
            "root_job_id": root.job_id,
            "plan_attempt_id": dispatch.attempt.attempt_id,
            "steps": [
                {
                    "ordinal": 0,
                    "step_id": "step-interactive",
                    "objective": "Read one reserved fixture step.",
                    "business_impact": "routine",
                    "review_required": False,
                    "requested_authorities": ["READ"],
                    "allowed_write_paths": [],
                    "validation_ids": [],
                    "attempt_limit": 1,
                    "cost_class": "small",
                }
            ],
        },
        "summary": "bounded interactive plan result",
        "current_state": "complete",
        "next_actions": [],
        "errors": [],
        "validations": [],
    }
    work = _exact_target_admission_direct(
        runtime,
        root,
        parent,
        dispatch,
        _epoch,
        _generation,
        epoch_id=_epoch.session_epoch_id,
        provider_session_id="SESSION-INTERACTIVE",
        plan_envelope=plan_envelope,
        selected_worker_id="worker-b",
        selected_worker_uid=9401,
    )
    with runtime.store.read() as connection:
        row = connection.execute(
            """
            SELECT a.status,j.status AS job_status,j.orchestration_role,
                   j.parent_job_id,j.root_job_id
            FROM attempts a JOIN jobs j ON j.job_id=a.job_id
            WHERE a.attempt_id=?
            """,
            (dispatch.attempt.attempt_id,),
        ).fetchone()
    now = runtime.store.now_ms()
    definition = {
        "schema_version": "mastermind.exact_worker_claim_target/v1",
        "operation_key": str(root.orchestration_provenance["source_id"]),
        "root_job_id": root.job_id,
        "job_id": work.job_id,
        "worker_id": "worker-b",
        "quota_class": "default",
        "expected_provider": "codex",
        "expected_account_label": "worker-b-company",
        "expected_model": "gpt-5.6-sol",
        "expected_effort": "xhigh",
        "expected_cost_class": "small",
        "expected_capabilities": ["read", "research"],
        "excluded_worker_ids": [dispatch.attempt.worker_id],
        "source_owner": "executive-control",
        "source_generation": "fixture-generation-1",
        "authority_policy_hash": work.authority_policy_hash,
        "expires_at_ms": now + 60_000,
    }
    observation = {
        "schema_version": "mastermind.exact_worker_target_observation/v1",
        "source_sha256": "d" * 64,
        "control_attestation_sha256": "e" * 64,
        "observed_at_ms": now,
        "max_age_ms": 30_000,
    }
    command_id = (
        f"coo-cycle:{root.job_id}:dispatch:{work.job_id}:attempt:1"
    )
    return runtime, root, parent, work, definition, observation, command_id


def _issue_target(definition, observation):
    from control_plane import executive_runtime as runtime_module

    return runtime_module._issue_exact_worker_claim_target(
        definition,
        observation,
        _producer_capability=runtime_module._EXACT_WORKER_TARGET_PRODUCER,
        revalidate=lambda: None,
    )


def test_exact_target_same_broker_uid_refuses_without_claim(tmp_path):
    (runtime, root, parent, work, definition, observation, command_id) = (
        _uid_join_fixture(tmp_path)
    )
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE worker_quota_classes SET metadata_json=? "
            "WHERE worker_id='worker-b' AND quota_class='default'",
            (_json_dumps({"broker_uid": 9301}),),
        )
    target = _issue_target(definition, observation)
    with pytest.raises(StateConflict, match="conflicts with parent"):
        runtime.attempts.dispatch_cycle_job(
            work.job_id,
            command_id=command_id,
            exact_target=target,
        )
    assert runtime.attempts.list_attempts(work.job_id) == []


def test_exact_target_unproven_broker_uid_refuses_without_claim(tmp_path):
    (runtime, root, parent, work, definition, observation, command_id) = (
        _uid_join_fixture(tmp_path)
    )
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE worker_quota_classes SET metadata_json=? "
            "WHERE worker_id='worker-b' AND quota_class='default'",
            ("{}",),
        )
    target = _issue_target(definition, observation)
    with pytest.raises(StateConflict, match="UID cannot be proven"):
        runtime.attempts.dispatch_cycle_job(
            work.job_id,
            command_id=command_id,
            exact_target=target,
        )
    assert runtime.attempts.list_attempts(work.job_id) == []


def test_exact_target_different_worker_and_uid_can_compose(tmp_path):
    (runtime, root, parent, work, definition, observation, command_id) = (
        _uid_join_fixture(tmp_path)
    )
    definition = {**definition, "worker_id": "worker-b"}
    target = _issue_target(definition, observation)
    outcome = runtime.attempts.dispatch_cycle_job(
        work.job_id,
        command_id=command_id,
        exact_target=target,
    )
    assert outcome is not None
    assert outcome.attempt.worker_id == "worker-b"
    parent_job = runtime.jobs.get_job(parent.job_id)
    assert parent_job is not None and parent_job.status is JobStatus.RUNNING
    assert runtime.attempts.get_attempt(
        outcome.attempt.attempt_id
    ).worker_id == "worker-b"
    assert len(runtime.attempts.list_attempts(work.job_id)) == 1


def test_interactive_capability_is_exact_read_only_appserver(tmp_path: Path):
    profile = ExecutionCapabilityRegistry.load().resolve(
        INTERACTIVE_TX5_EXECUTION_PROFILE
    )
    assert profile.enabled is True
    assert profile.execution_surface == "codex-app-server"
    assert profile.auth_realm == "dedicated-worker-account"
    assert profile.sandbox_policy == "read-only"
    assert profile.approval_policy == "never"
    assert profile.network_policy == "disabled"
    assert profile.write_capable is False
    assert profile.skills == ()
    assert profile.mcp_servers == ()
    assert profile.resource_grants == ()
    assert profile.plugins == ()


def test_interactive_finite_sequence_replay_and_in_flight(tmp_path: Path):
    runtime, root, parent, dispatch, epoch, generation = _started_interactive(
        tmp_path
    )
    first_op = OperationId(f"ohf-op:turn:{dispatch.attempt.attempt_id}:1")
    first = _reserve_turn(runtime, dispatch, epoch, generation, 1)
    replay = _reserve_turn(runtime, dispatch, epoch, generation, 1)
    assert first.turn_id == replay.turn_id
    with runtime.store.read() as connection:
        assert _interactive_in_flight_turn_id(
            connection, generation.process_generation_id
        )
    with pytest.raises(StateConflict, match="already has an in-flight turn"):
        _reserve_turn(runtime, dispatch, epoch, generation, 2)
    _acknowledge_turn(runtime, dispatch, first, first_op)
    with pytest.raises(StateConflict, match="already has an in-flight turn"):
        _reserve_turn(runtime, dispatch, epoch, generation, 2)
    _record_candidate(runtime, dispatch, first)
    second_op = OperationId(f"ohf-op:turn:{dispatch.attempt.attempt_id}:2")
    second = _reserve_turn(runtime, dispatch, epoch, generation, 2)
    _acknowledge_turn(runtime, dispatch, second, second_op)
    _record_candidate(runtime, dispatch, second)
    with pytest.raises(StateConflict, match="operation is not retryable"):
        _reserve_turn(runtime, dispatch, epoch, generation, 1)
    with pytest.raises(StateConflict, match="operation is not retryable"):
        _reserve_turn(runtime, dispatch, epoch, generation, 2)


def test_interactive_turn_nine_is_refused(tmp_path: Path):
    runtime, root, parent, dispatch, epoch, generation = _started_interactive(
        tmp_path
    )
    for ordinal in range(1, INTERACTIVE_TX5_MAX_TURNS_PER_GENERATION + 1):
        operation = OperationId(
            f"ohf-op:turn:{dispatch.attempt.attempt_id}:{ordinal}"
        )
        turn = _reserve_turn(runtime, dispatch, epoch, generation, ordinal)
        _acknowledge_turn(runtime, dispatch, turn, operation)
        _record_candidate(runtime, dispatch, turn)
    with pytest.raises(
        StateConflict,
        match="interactive TX-5 cardinality is exhausted",
    ):
        _reserve_turn(runtime, dispatch, epoch, generation, 9)


def test_interactive_effect_unknown_blocks_and_exact_replay_blocks(tmp_path):
    runtime, _root, _parent, dispatch, epoch, generation = _started_interactive(
        tmp_path
    )
    operation = OperationId(f"ohf-op:turn:{dispatch.attempt.attempt_id}:1")
    turn = _reserve_turn(runtime, dispatch, epoch, generation, 1)
    assert runtime.operator_harness.record_effect_unknown(
        attempt_id=dispatch.attempt.attempt_id,
        operation_id=operation,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=str(dispatch.lease_token),
        phase="begin_turn",
        detail="fixture unknown",
    )
    with pytest.raises(StateConflict, match="not retryable"):
        _reserve_turn(runtime, dispatch, epoch, generation, 1)
    with pytest.raises(StateConflict, match="in-flight"):
        _reserve_turn(runtime, dispatch, epoch, generation, 2)


def test_interactive_applied_requires_collection_before_next_turn(tmp_path):
    runtime, _root, _parent, dispatch, epoch, generation = _started_interactive(
        tmp_path
    )
    operation = OperationId(f"ohf-op:turn:{dispatch.attempt.attempt_id}:1")
    turn = _reserve_turn(runtime, dispatch, epoch, generation, 1)
    _acknowledge_turn(runtime, dispatch, turn, operation)
    with pytest.raises(StateConflict, match="in-flight"):
        _reserve_turn(runtime, dispatch, epoch, generation, 2)
    _record_candidate(runtime, dispatch, turn)
    _reserve_turn(runtime, dispatch, epoch, generation, 2)


def _canonical_plan(runtime, root, dispatch):
    return {
        "schema_version": RESULT_SCHEMA,
        "job_id": runtime.jobs.get_job(dispatch.job_id).job_id,
        "run_id": dispatch.attempt.attempt_id,
        "worker_id": str(dispatch.attempt.worker_id),
        "role": "plan",
        "status": "COMPLETED",
        "role_result": {
            "schema_version": "mastermind.execution_plan/v1",
            "root_job_id": root.job_id,
            "plan_attempt_id": dispatch.attempt.attempt_id,
            "steps": [
                {
                    "ordinal": 0,
                    "step_id": "step-interactive",
                    "objective": "One reserved read-only step.",
                    "business_impact": "routine",
                    "review_required": False,
                    "requested_authorities": ["READ"],
                    "allowed_write_paths": [],
                    "validation_ids": [],
                    "attempt_limit": 1,
                    "cost_class": "small",
                }
            ],
        },
        "summary": "interactive immutable plan result",
        "current_state": "complete",
        "next_actions": [],
        "errors": [],
        "validations": [],
    }
