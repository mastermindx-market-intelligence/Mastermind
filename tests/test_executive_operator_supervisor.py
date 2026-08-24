"""End-to-end Runtime proofs for the read-only Executive Operator supervisor."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.executive_orchestration_principal import (
    OSProcessCredentialObservation,
    OperatorPrincipalObservation,
    ProviderHomeIdentityObservation,
)
from control_plane.executive_orchestration_result import (
    RESULT_SCHEMA,
    RawRoleResultObservation,
    canonical_bytes,
)
from control_plane.executive_runtime import (
    AttemptStatus,
    JobStatus,
    OrchestrationDispatchOutcome,
    Runtime,
)
from control_plane.executive_supervisor import ReconcileStatus
from control_plane.model_router import ModelRouter
from control_plane.operator_harness_contract import (
    AuthRealmFact,
    AuthRealmRequirement,
    CandidateResult,
    CapabilityManifest,
    EventCursor,
    NativeHelperPolicy,
    NormalizedEvent,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    OperationReceiptKind,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProfileValidation,
    ProfileValidation,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    SessionStartObservation,
    TurnRef,
    TurnStartObservation,
    WorkspaceIdentity,
)
from control_plane.operator_harness_orchestrator import OperatorOperationApplied


class _Clock:
    def __init__(self) -> None:
        self.value = 1_900_000_000_000

    def __call__(self) -> int:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += seconds * 1000


def _intent() -> dict:
    return {
        "schema": INTENT_SCHEMA_V2,
        "intent_id": "CEO-G2-RECOVERY-001",
        "actor": "ceo-sol",
        "objective": "Produce one bounded read-only execution plan.",
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


def _profile(dispatch: OrchestrationDispatchOutcome) -> RequestedExecutionProfile:
    attempt = dispatch.attempt
    return RequestedExecutionProfile(
        worker_id=attempt.worker_id,
        provider="openai-codex",
        requested_model="gpt-5.6-sol",
        harness_kind="codex-app-server",
        harness_binary_digest="a" * 64,
        harness_version="0.147.0",
        workspace=WorkspaceIdentity(
            "/tmp/mastermind-g2-recovery", "b" * 40, 1, 2, os.getuid(), os.getgid()
        ),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash=attempt.authority_policy_hash,
        auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
    )


def _attestation(profile: RequestedExecutionProfile) -> ObservedHarnessAttestation:
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
        effective_config_digest="d" * 64,
        auth=AuthRealmFact(worker_id=profile.worker_id, provider=profile.provider),
        workspace=profile.workspace,
        supports_subagent_capability_ceiling=ObservedTriState.FALSE,
    )


def _seed_expired_g1(
    tmp_path: Path, *, observed_dead: bool = True, with_turn: bool = True
):
    clock = _Clock()
    runtime = Runtime.at(tmp_path, clock=clock, lease_seconds=2)
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
    receipt = submit_intent(runtime, _intent())
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
    assert dispatch.lease_token is not None
    profile = _profile(dispatch)
    harness = runtime.operator_harness
    sealed = harness.seal_operator_harness_attempt(
        dispatch.attempt.attempt_id,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
    )
    start_op = OperationId("ohf-op:g2-recovery-start")
    epoch, g1 = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        operation_id=start_op,
    )
    process = ProcessIdentityObservation(2101, 2101, "start-2101", "boot-test")
    harness.bind_start_result(
        epoch=epoch,
        generation=g1,
        operation_id=start_op,
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
            "path": "/tmp/mastermind-g2-provider-home",
            "device": 3,
            "inode": 4,
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
        attestation=_attestation(profile),
        principal_observation=principal,
    )
    if with_turn:
        turn_op = OperationId("ohf-op:g2-recovery-turn")
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
    if observed_dead:
        harness.record_reconcile_observation(
            generation=g1,
            observation=ReconcileObservation(
                ProcessLiveness.PROVEN_DEAD,
                process,
                False,
                ProviderWriterState.RELEASED,
                "SESSION-G1",
                "d" * 64,
            ),
            fence_generation=sealed.fence_generation,
            lease_token=dispatch.lease_token,
        )
    return clock, runtime, root, planner, dispatch, profile, epoch


def _seed_expired_unstarted_claim(tmp_path: Path):
    clock = _Clock()
    runtime = Runtime.at(tmp_path, clock=clock, lease_seconds=2)
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
    receipt = submit_intent(runtime, _intent())
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
    assert dispatch.lease_token is not None
    runtime.operator_harness.seal_operator_harness_attempt(
        dispatch.attempt.attempt_id,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        requested=_profile(dispatch),
    )
    return clock, runtime, planner, dispatch


class _RecoveryAdapter:
    def __init__(
        self,
        runtime: Runtime,
        profile: RequestedExecutionProfile,
        loader,
        *,
        live_existing: bool = False,
    ) -> None:
        self.runtime = runtime
        self.profile = profile
        self.loader = loader
        self.live_existing = live_existing
        self.process = (
            ProcessIdentityObservation(2101, 2101, "start-2101", "boot-test")
            if live_existing
            else ProcessIdentityObservation(2202, 2202, "start-2202", "boot-test")
        )
        self.provider_session_id = "SESSION-G1"
        self.native_turn_id = "NATIVE-G1" if live_existing else "NATIVE-G2"
        self.resume_calls = 0
        self.begin_turn_calls = 0
        self.cancel_calls = 0
        self.read_calls = 0

    def reconcile(self, generation):
        process = ProcessIdentityObservation(2101, 2101, "start-2101", "boot-test")
        return ReconcileObservation(
            ProcessLiveness.ALIVE if self.live_existing else ProcessLiveness.PROVEN_DEAD,
            process,
            True if self.live_existing else False,
            ProviderWriterState.HELD if self.live_existing else ProviderWriterState.RELEASED,
            self.provider_session_id,
            "d" * 64,
        )

    def resume_session(self, *, provider_session, **_kwargs):
        self.resume_calls += 1
        assert provider_session.provider_session_id == self.provider_session_id
        return SessionStartObservation(self.provider_session_id, self.process)

    def observed_attestation(self, _generation):
        return _attestation(self.profile)

    def observe_process_credentials(self, _generation):
        return OSProcessCredentialObservation(
            {
                "pid": self.process.pid,
                "pgid": self.process.pgid,
                "process_start_identity": self.process.process_start_identity,
                "boot_id": self.process.boot_id,
            },
            "fixture-principal",
            os.getuid(),
        )

    def observe_provider_home_identity(self, _generation):
        return ProviderHomeIdentityObservation(
            {
                "path": "/tmp/mastermind-g2-provider-home",
                "device": 3,
                "inode": 4,
                "uid": os.getuid(),
                "gid": os.getgid(),
                "mode": 0o700,
            }
        )

    def begin_turn(self, *, turn, **_kwargs):
        self.begin_turn_calls += 1
        assert "output schema" in self.loader(turn)
        return TurnStartObservation(self.native_turn_id, True)

    def read_events(self, cursor, *, timeout_seconds):
        self.read_calls += 1
        assert timeout_seconds > 0 and cursor.turn_id
        return (
            (
                NormalizedEvent(
                    cursor.attempt_id,
                    cursor.session_epoch_id,
                    cursor.process_generation_id,
                    cursor.turn_id,
                    "turn.completed",
                    payload_redacted={"status": "complete"},
                ),
            ),
            EventCursor(
                cursor.attempt_id,
                cursor.session_epoch_id,
                cursor.process_generation_id,
                local_sequence=1,
                turn_id=cursor.turn_id,
            ),
        )

    def collect_candidate_result(self, turn):
        return CandidateResult(
            turn.attempt_id,
            turn.session_epoch_id,
            turn.process_generation_id,
            "e" * 64,
            "recovered plan",
        )

    def _canonical_result(self, turn) -> str:
        attempt = self.runtime.attempts.get_attempt(turn.attempt_id)
        assert attempt is not None
        job = self.runtime.jobs.get_job(attempt.job_id)
        assert job is not None
        envelope = {
            "schema_version": RESULT_SCHEMA,
            "job_id": job.job_id,
            "run_id": attempt.attempt_id,
            "worker_id": attempt.worker_id,
            "role": "plan",
            "status": "COMPLETED",
            "role_result": {
                "schema_version": "mastermind.execution_plan/v1",
                "root_job_id": job.root_job_id,
                "plan_attempt_id": attempt.attempt_id,
                "steps": [
                    {
                        "ordinal": 0,
                        "step_id": "step-1",
                        "objective": "Perform one bounded read-only follow-up.",
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
            "summary": "Recovered one exact planner session.",
            "current_state": "complete",
            "next_actions": [],
            "errors": [],
            "validations": [],
        }
        return canonical_bytes(envelope).decode("utf-8")

    def observe_raw_role_result(self, turn):
        value = self._canonical_result(turn)
        return RawRoleResultObservation(
            attempt_id=turn.attempt_id,
            session_epoch_id=turn.session_epoch_id,
            process_generation_id=turn.process_generation_id,
            turn_id=turn.turn_id,
            provider_session_id=self.provider_session_id,
            provider_native_turn_id=self.native_turn_id,
            provider_turn_artifact_digest="e" * 64,
            canonical_result_json=value,
            canonical_result_digest=hashlib.sha256(value.encode()).hexdigest(),
            canonical_result_byte_length=len(value.encode()),
        )

    def graceful_stop(self, _generation, **_kwargs):
        return ReconcileObservation(
            ProcessLiveness.PROVEN_DEAD,
            self.process,
            False,
            ProviderWriterState.RELEASED,
            self.provider_session_id,
            "d" * 64,
        )

    def cancel(self, _generation, **_kwargs):
        self.cancel_calls += 1
        return ReconcileObservation(
            ProcessLiveness.PROVEN_DEAD,
            self.process,
            False,
            ProviderWriterState.RELEASED,
            self.provider_session_id,
            "d" * 64,
        )


class _PromptSource:
    def _prompt(self, *_args):
        return "Read the exact Job and produce the bounded plan."


def _seed_dispatchable_operator_planner(tmp_path: Path):
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "g2-planner"
    workspace.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "codex/g2-planner"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "fixture@mastermind.invalid"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Mastermind Fixture"],
        cwd=workspace,
        check=True,
    )
    (workspace / "README.md").write_text("G2 fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture"], cwd=workspace, check=True
    )
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    runtime = Runtime.at(tmp_path / "runtime")
    router = ModelRouter.load()
    sealed = router.model_aliases["coo.sealed"]
    operator = router.model_aliases["coo.operator.readonly"]
    binding = {
        "eligible_quota_classes": ["codex-coo", "codex-coo-default"],
        "provider": sealed.provider_alias,
        "model": sealed.model,
        "effort": sealed.effort,
        "cost_class": sealed.cost_class,
        "base_sha": base_sha,
        "routing_policy_version": router.policy_version,
        "execution_profile_id": sealed.execution_profile_id,
        "execution_profile_digest": sealed.execution_profile_digest,
        "capability_policy_version": sealed.capability_policy_version,
        "capability_policy_digest": sealed.capability_policy_digest,
        "operator_eligible_quota_classes": ["codex-coo-operator"],
        "operator_provider": operator.provider_alias,
        "operator_model": operator.model,
        "operator_effort": operator.effort,
        "operator_cost_class": operator.cost_class,
        "operator_routing_policy_version": router.policy_version,
        "operator_execution_profile_id": operator.execution_profile_id,
        "operator_execution_profile_digest": operator.execution_profile_digest,
        "operator_capability_policy_version": operator.capability_policy_version,
        "operator_capability_policy_digest": operator.capability_policy_digest,
        "operator_harness_binary_digest": "a" * 64,
        "operator_harness_version": "0.147.0",
        "operator_harness_armed": True,
    }
    runtime.workers.register_worker(
        "worker-a",
        provider=operator.provider_alias,
        account_label="worker-a@company",
        worker_type="fixture",
        capabilities=list(operator.capabilities),
        quota_classes={
            "codex-coo-operator": {
                "provider": operator.provider_alias,
                "model": operator.model,
                "effort": operator.effort,
                "cost_class": operator.cost_class,
                "capabilities": list(operator.capabilities),
                "metadata": {
                    "routing_policy_version": router.policy_version,
                    "execution_profile_id": operator.execution_profile_id,
                    "execution_profile_digest": operator.execution_profile_digest,
                    "capability_policy_version": operator.capability_policy_version,
                    "capability_policy_digest": operator.capability_policy_digest,
                    "harness_binary_digest": "a" * 64,
                    "harness_version": "0.147.0",
                },
            }
        },
    )
    intent = _intent()
    intent["grounding"] = {"mastermind_sha": base_sha, "macro_sha": "b" * 40}
    intent["execution_contract"] = {
        "requested_authorities": ["READ"],
        "branch": "codex/g2-planner",
        "worktree": str(workspace),
        "attempt_limit": 2,
    }
    receipt = submit_intent(
        runtime,
        intent,
        workspace_root=workspace_root,
        execution_binding=binding,
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    return runtime, root, planner


class _ActiveAdapter(_RecoveryAdapter):
    def __init__(self, runtime: Runtime, loader, *, cancel_during_collect: bool):
        self.runtime = runtime
        self.turn_input_loader = loader
        self.profile: RequestedExecutionProfile | None = None
        self.process = ProcessIdentityObservation(
            3101, 3101, "start-3101", "boot-test"
        )
        self.provider_session_id = "SESSION-ACTIVE"
        self.native_turn_id = "NATIVE-ACTIVE"
        self.resume_calls = 0
        self.begin_turn_calls = 0
        self.cancel_calls = 0
        self.stop_calls = 0
        self.read_calls = 0
        self.cancel_during_collect = cancel_during_collect

    def validate_requested_profile(self, requested):
        self.profile = requested
        return ProfileValidation(requested, True, ())

    def start_session(self, **_kwargs):
        return SessionStartObservation(self.provider_session_id, self.process)

    def observed_attestation(self, _generation):
        assert self.profile is not None
        return _attestation(self.profile)

    def begin_turn(self, *, turn, **_kwargs):
        self.begin_turn_calls += 1
        assert "output schema" in self.turn_input_loader(turn)
        return TurnStartObservation(self.native_turn_id, True)

    def read_events(self, cursor, *, timeout_seconds):
        if self.cancel_during_collect:
            attempt = self.runtime.attempts.get_attempt(cursor.attempt_id)
            assert attempt is not None
            self.runtime.jobs.cancel_job(attempt.job_id)
        return super().read_events(cursor, timeout_seconds=timeout_seconds)

    def graceful_stop(self, generation, **kwargs):
        self.stop_calls += 1
        return super().graceful_stop(generation, **kwargs)

    def reconcile(self, _generation):
        return ReconcileObservation(
            ProcessLiveness.ALIVE,
            self.process,
            True,
            ProviderWriterState.HELD,
            self.provider_session_id,
            "d" * 64,
        )


def test_fresh_operator_planner_completes_one_session_and_releases_epoch(
    tmp_path: Path,
) -> None:
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path)
    adapters: list[_ActiveAdapter] = []

    def factory(loader):
        adapter = _ActiveAdapter(runtime, loader, cancel_during_collect=False)
        adapters.append(adapter)
        return adapter

    supervisor = ExecutiveOperatorSupervisor(
        runtime,
        adapter_factory=factory,  # type: ignore[arg-type]
        prompt_source=_PromptSource(),  # type: ignore[arg-type]
    )
    outcome = asyncio.run(
        supervisor.start_cycle_job(
            planner.job_id,
            command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        )
    )
    assert outcome.outcome == "TERMINAL"
    attempt = runtime.attempts.get_attempt(outcome.attempt.attempt_id)
    job = runtime.jobs.get_job(planner.job_id)
    assert attempt is not None and attempt.status is AttemptStatus.COMPLETED
    assert job is not None and job.status is JobStatus.COMPLETED
    assert len(adapters) == 1
    assert adapters[0].begin_turn_calls == 1
    assert adapters[0].stop_calls == 1
    assert adapters[0].cancel_calls == 0
    with runtime.store.read() as connection:
        epoch = connection.execute(
            "SELECT state FROM harness_session_epochs WHERE attempt_id=?",
            (attempt.attempt_id,),
        ).fetchone()
    assert epoch["state"] == "ABANDONED"


def test_active_operator_cancellation_finishes_cancelled_not_quarantined(
    tmp_path: Path,
) -> None:
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path)
    adapters: list[_ActiveAdapter] = []

    def factory(loader):
        adapter = _ActiveAdapter(runtime, loader, cancel_during_collect=True)
        adapters.append(adapter)
        return adapter

    supervisor = ExecutiveOperatorSupervisor(
        runtime,
        adapter_factory=factory,  # type: ignore[arg-type]
        prompt_source=_PromptSource(),  # type: ignore[arg-type]
    )
    with pytest.raises(OperatorOperationApplied):
        asyncio.run(
            supervisor.start_cycle_job(
                planner.job_id,
                command_id=(
                    f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"
                ),
            )
        )
    attempt = runtime.attempts.list_attempts()[0]
    job = runtime.jobs.get_job(planner.job_id)
    assert attempt.status is AttemptStatus.CANCELLED
    assert job is not None and job.status is JobStatus.CANCELLED
    assert len(adapters) == 1
    assert adapters[0].cancel_calls == 1
    assert adapters[0].stop_calls == 0


def test_restart_waits_for_expiry_then_resumes_same_attempt_and_session(
    tmp_path: Path,
) -> None:
    clock, runtime, _root, _planner, dispatch, profile, epoch = _seed_expired_g1(
        tmp_path, with_turn=True
    )
    adapters: list[_RecoveryAdapter] = []

    def factory(loader):
        adapter = _RecoveryAdapter(runtime, profile, loader)
        adapters.append(adapter)
        return adapter

    supervisor = ExecutiveOperatorSupervisor(
        runtime,
        adapter_factory=factory,  # type: ignore[arg-type]
        prompt_source=_PromptSource(),  # type: ignore[arg-type]
    )
    waiting = supervisor.reconcile_restart()
    assert [item.status for item in waiting] == [
        ReconcileStatus.AWAITING_LEASE_EXPIRY
    ]

    clock.advance(3)
    recovered = supervisor.reconcile_restart()
    assert [item.status for item in recovered] == [
        ReconcileStatus.OPERATOR_RECOVERED
    ]
    attempt = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
    assert attempt is not None and attempt.status is AttemptStatus.COMPLETED
    with runtime.store.read() as connection:
        generations = connection.execute(
            """
            SELECT generation_number,provider_session_id
            FROM process_generations WHERE session_epoch_id=?
            ORDER BY generation_number
            """,
            (epoch.session_epoch_id,),
        ).fetchall()
        epoch_row = connection.execute(
            """SELECT state,provider_session_id FROM harness_session_epochs
               WHERE session_epoch_id=?""",
            (epoch.session_epoch_id,),
        ).fetchone()
    assert [(row[0], row[1]) for row in generations] == [
        (1, "SESSION-G1"),
        (2, "SESSION-G1"),
    ]
    assert epoch_row["state"] == "ABANDONED"
    assert epoch_row["provider_session_id"] == "SESSION-G1"
    assert len(adapters) == 1
    assert supervisor.reconcile_restart() == []


def test_restart_dead_g1_without_acknowledged_turn_remains_fenced(
    tmp_path: Path,
) -> None:
    clock, runtime, _root, _planner, dispatch, profile, epoch = _seed_expired_g1(
        tmp_path, with_turn=False
    )

    supervisor = ExecutiveOperatorSupervisor(
        runtime,
        adapter_factory=lambda loader: _RecoveryAdapter(
            runtime, profile, loader
        ),  # type: ignore[arg-type]
        prompt_source=_PromptSource(),  # type: ignore[arg-type]
    )
    clock.advance(3)
    recovered = supervisor.reconcile_restart()
    assert [item.status for item in recovered] == [
        ReconcileStatus.IDENTITY_AMBIGUOUS
    ]
    attempt = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
    assert attempt is not None and attempt.status is AttemptStatus.RUNNING
    with runtime.store.read() as connection:
        generations = connection.execute(
            """SELECT generation_number FROM process_generations
               WHERE session_epoch_id=? ORDER BY generation_number""",
            (epoch.session_epoch_id,),
        ).fetchall()
    assert [row[0] for row in generations] == [1]


@pytest.mark.parametrize("observed_dead", [False, True])
def test_restart_completes_existing_sealed_result_without_recollect_or_resume(
    tmp_path: Path, observed_dead: bool
) -> None:
    clock, runtime, _root, _planner, dispatch, profile, epoch = _seed_expired_g1(
        tmp_path, observed_dead=False, with_turn=True
    )
    with runtime.store.read() as connection:
        row = connection.execute(
            """SELECT payload_json FROM events
               WHERE attempt_id=? AND aggregate_type='operator_operation'
                 AND event_type=? ORDER BY event_id""",
                (
                    dispatch.attempt.attempt_id,
                    OperationReceiptKind.INTENT.value,
                ),
        ).fetchall()
    turns = [
        json.loads(item["payload_json"])
        for item in row
        if json.loads(item["payload_json"]).get("operation_kind") == "begin_turn"
    ]
    assert len(turns) == 1
    value = turns[0]
    turn = TurnRef(
        value["turn_id"],
        value["session_epoch_id"],
        value["process_generation_id"],
        value["attempt_id"],
    )
    sealing_adapter = _RecoveryAdapter(
        runtime, profile, lambda _turn: "unused", live_existing=True
    )
    cursor = EventCursor(
        turn.attempt_id,
        turn.session_epoch_id,
        turn.process_generation_id,
        turn_id=turn.turn_id,
    )
    events, next_cursor = sealing_adapter.read_events(
        cursor, timeout_seconds=30.0
    )
    runtime.operator_harness.record_candidate_evidence(
        turn=turn,
        candidate=sealing_adapter.collect_candidate_result(turn),
        events=events,
        cursor=next_cursor,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
    )
    runtime.operator_harness.seal_orchestration_role_result(
        turn=turn,
        observation=sealing_adapter.observe_raw_role_result(turn),
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
    )
    adapters: list[_RecoveryAdapter] = []

    def factory(loader):
        adapter = _RecoveryAdapter(
            runtime,
            profile,
            loader,
            live_existing=not observed_dead,
        )
        adapters.append(adapter)
        return adapter

    supervisor = ExecutiveOperatorSupervisor(
        runtime,
        adapter_factory=factory,  # type: ignore[arg-type]
        prompt_source=_PromptSource(),  # type: ignore[arg-type]
    )
    clock.advance(3)
    recovered = supervisor.reconcile_restart()
    assert [item.status for item in recovered] == [
        ReconcileStatus.OPERATOR_RECOVERED
    ]
    attempt = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
    assert attempt is not None and attempt.status is AttemptStatus.COMPLETED
    assert len(adapters) == 1
    assert adapters[0].read_calls == 0
    assert adapters[0].begin_turn_calls == 0
    assert adapters[0].resume_calls == 0
    with runtime.store.read() as connection:
        epoch_row = connection.execute(
            "SELECT state FROM harness_session_epochs WHERE session_epoch_id=?",
            (epoch.session_epoch_id,),
        ).fetchone()
    assert epoch_row["state"] == "ABANDONED"


@pytest.mark.parametrize("with_turn", [False, True])
def test_restart_reconnects_live_g1_and_collects_without_allocating_g2(
    tmp_path: Path, with_turn: bool
) -> None:
    clock, runtime, _root, _planner, dispatch, profile, epoch = _seed_expired_g1(
        tmp_path, observed_dead=False, with_turn=with_turn
    )

    def factory(loader):
        return _RecoveryAdapter(
            runtime, profile, loader, live_existing=True
        )

    supervisor = ExecutiveOperatorSupervisor(
        runtime,
        adapter_factory=factory,  # type: ignore[arg-type]
        prompt_source=_PromptSource(),  # type: ignore[arg-type]
    )
    clock.advance(3)
    recovered = supervisor.reconcile_restart()
    assert [item.status for item in recovered] == [
        ReconcileStatus.OPERATOR_RECOVERED
    ]
    attempt = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
    assert attempt is not None and attempt.status is AttemptStatus.COMPLETED
    with runtime.store.read() as connection:
        generations = connection.execute(
            """SELECT generation_number FROM process_generations
               WHERE session_epoch_id=? ORDER BY generation_number""",
            (epoch.session_epoch_id,),
        ).fetchall()
    assert [row[0] for row in generations] == [1]


@pytest.mark.parametrize(
    ("observed_dead", "with_turn"),
    [(False, False), (False, True), (True, False), (True, True)],
)
def test_restart_cancellation_wins_without_collect_or_resume(
    tmp_path: Path, observed_dead: bool, with_turn: bool
) -> None:
    clock, runtime, _root, planner, dispatch, profile, epoch = _seed_expired_g1(
        tmp_path, observed_dead=observed_dead, with_turn=with_turn
    )
    adapters: list[_RecoveryAdapter] = []

    def factory(loader):
        adapter = _RecoveryAdapter(
            runtime,
            profile,
            loader,
            live_existing=not observed_dead,
        )
        adapters.append(adapter)
        return adapter

    supervisor = ExecutiveOperatorSupervisor(
        runtime,
        adapter_factory=factory,  # type: ignore[arg-type]
        prompt_source=_PromptSource(),  # type: ignore[arg-type]
    )
    cancelled = runtime.jobs.cancel_job(planner.job_id)
    assert cancelled.status is JobStatus.CANCEL_REQUESTED
    clock.advance(3)

    recovered = supervisor.reconcile_restart()
    assert [item.status for item in recovered] == [
        ReconcileStatus.MISSING_CANCELLED
    ]
    attempt = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
    job = runtime.jobs.get_job(planner.job_id)
    assert attempt is not None and attempt.status is AttemptStatus.CANCELLED
    assert job is not None and job.status is JobStatus.CANCELLED
    assert len(adapters) == 1
    assert adapters[0].resume_calls == 0
    assert adapters[0].begin_turn_calls == 0
    assert adapters[0].cancel_calls == (0 if observed_dead else 1)
    with runtime.store.read() as connection:
        epoch_row = connection.execute(
            "SELECT state FROM harness_session_epochs WHERE session_epoch_id=?",
            (epoch.session_epoch_id,),
        ).fetchone()
    assert epoch_row["state"] == "ABANDONED"
    assert supervisor.reconcile_restart() == []


def test_restart_cancellation_before_session_releases_without_provider_call(
    tmp_path: Path,
) -> None:
    clock, runtime, planner, dispatch = _seed_expired_unstarted_claim(tmp_path)

    def unexpected_factory(_loader):
        raise AssertionError("pre-session cancellation must not construct an adapter")

    supervisor = ExecutiveOperatorSupervisor(
        runtime,
        adapter_factory=unexpected_factory,
        prompt_source=_PromptSource(),  # type: ignore[arg-type]
    )
    cancelled = runtime.jobs.cancel_job(planner.job_id)
    assert cancelled.status is JobStatus.CANCEL_REQUESTED
    clock.advance(3)

    recovered = supervisor.reconcile_restart()
    assert [item.status for item in recovered] == [
        ReconcileStatus.MISSING_CANCELLED
    ]
    attempt = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
    job = runtime.jobs.get_job(planner.job_id)
    assert attempt is not None and attempt.status is AttemptStatus.CANCELLED
    assert job is not None and job.status is JobStatus.CANCELLED
