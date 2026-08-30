#!/usr/bin/env python3
"""Deterministic offline acceptance harness for inert Executive OS Phase 1F-C."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

import control_plane.executive_runtime as executive_runtime
from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_coo_policy import CooCyclePolicy
from control_plane.executive_orchestration_principal import (
    OperatorPrincipalObservation,
)
from control_plane.executive_orchestration_result import (
    GOLDEN_ROLE_SCHEMA_DIGESTS,
    RESULT_SCHEMA,
    RawRoleResultObservation,
    canonical_bytes as result_canonical_bytes,
    canonical_digest as result_digest,
)
from control_plane.executive_runtime import (
    JobStatus,
    OrchestrationDispatchOutcome,
    Runtime,
    StateConflict,
    WorkerStatus,
)
from control_plane.executive_supervisor import ExecutiveSupervisor
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

ACCEPTANCE_ID = "P1FC-INERT-ACCEPTANCE-V1"
CYCLE_ACCEPTANCE_ID = "P1FC-BOUNDED-CYCLE-REPLAY-V1"
HAPPY_PATH_ACCEPTANCE_ID = "P1FC-TYPED-HAPPY-SUPERVISOR-V1"
REPAIR_PATH_ACCEPTANCE_ID = "P1FC-REJECT-REPAIR-LINEAGE-V1"
VOID_PATH_ACCEPTANCE_ID = "P1FC-VOID-REPLACEMENT-INDEPENDENCE-V1"
DISPATCH_REPLAY_ACCEPTANCE_ID = "P1FC-SUPERVISOR-CLAIM-CRASH-REPLAY-V1"
DISPATCH_BOUNDARY_ACCEPTANCE_ID = "P1FC-EXACT-DISPATCH-BOUNDARY-V1"
TX9_ACCEPTANCE_ID = "P1FC-TX9-QUARANTINE-V1"

# Acceptance evidence must be byte-identical across the macOS control host and
# Linux hosted CI.  These are inert fixture identities, not observations of the
# process running the harness and not live execution-principal evidence.
_FIXTURE_WORKSPACE_UID = 501
_FIXTURE_WORKSPACE_GID = 20


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _intent(intent_id: str) -> dict[str, Any]:
    return {
        "schema": INTENT_SCHEMA_V2,
        "intent_id": intent_id,
        "actor": "ceo-sol",
        "objective": "Prove one inert deterministic COO cycle.",
        "department": "executive-infrastructure",
        "priority": 9,
        "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
        "execution_contract": {
            "requested_authorities": ["READ"],
            "attempt_limit": 2,
        },
        "intent_kind": "executive_coo_cycle",
        "business_impact": "material",
    }


def _register(runtime: Runtime, worker_id: str) -> None:
    runtime.workers.register_worker(
        worker_id,
        provider="codex",
        account_label=f"{worker_id}@acceptance",
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


def _lease_token(runtime: Runtime, attempt_id: str) -> str:
    with runtime.store.read() as connection:
        row = connection.execute(
            "SELECT lease_token FROM attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
    assert row is not None and row["lease_token"]
    return str(row["lease_token"])


class _ExactSupervisorFixtureDispatcher:
    """Exercise ``ExecutiveSupervisor.start_cycle_job`` and stop before launch.

    The real supervisor owns the command-bound exact-Job claim.  The fixture
    overrides only its post-claim launch method, so no provider adapter is
    constructed or called.  Worker availability is explicitly arranged before
    each claim to produce deterministic independent-review identities.
    """

    def __init__(
        self,
        runtime: Runtime,
        root: Path,
        *,
        review_workers: tuple[str, ...] = (),
    ) -> None:
        self.runtime = runtime
        self.calls: list[dict[str, str]] = []
        self.review_workers = review_workers
        self.review_index = 0
        self.current_command_id: str | None = None
        self.crash_after_claim_once = False
        self._crashed = False
        # ``adapter`` is deliberately None.  A supplied inert inspector prevents
        # construction of any provider-specific execution adapter; neither is
        # consulted because the post-claim launch method below is the stop line.
        self.supervisor = ExecutiveSupervisor(
            runtime,
            None,  # type: ignore[arg-type]
            codex_home=root / "fixture-provider-home-never-opened",
            inspector=object(),  # type: ignore[arg-type]
            instance_id="phase1fc-deterministic-acceptance",
        )
        self.supervisor._start_claimed_job = self._stop_before_provider  # type: ignore[method-assign]

    def _select_worker(self, job_id: str) -> str:
        job = self.runtime.jobs.get_job(job_id)
        assert job is not None
        if job.orchestration_role == "review":
            if self.review_index >= len(self.review_workers):
                raise AssertionError("acceptance review-worker fixture is exhausted")
            selected = self.review_workers[self.review_index]
            self.review_index += 1
        else:
            selected = "worker-a"
        primary_quota = self.runtime.workers.get_quota_class("worker-a", "default")
        if (
            selected == "worker-a"
            and primary_quota is not None
            and primary_quota.status is WorkerStatus.ERROR
        ):
            selected = "worker-b"
        for worker_id in ("worker-a", "worker-b"):
            worker = self.runtime.workers.get_worker(worker_id)
            if worker is None:
                continue
            desired = (
                WorkerStatus.AVAILABLE
                if worker_id == selected
                else WorkerStatus.OFFLINE
            )
            quota = self.runtime.workers.get_quota_class(worker_id, "default")
            if quota is not None and quota.status is WorkerStatus.ERROR:
                # TX-9 quarantine evidence is immutable input, never fixture
                # worker-selection state to heal or rewrite.
                continue
            if (
                quota is not None
                and worker_id == selected
                and quota.status is WorkerStatus.BUSY
            ):
                continue
            if quota is not None and quota.status is not desired:
                self.runtime.workers.set_worker_status(
                    worker_id, desired, quota_class="default"
                )
        return selected

    async def _stop_before_provider(self, job_id: str, lease):
        assert self.current_command_id is not None
        return OrchestrationDispatchOutcome(
            command_id=self.current_command_id,
            job_id=job_id,
            attempt=lease.attempt,
            outcome="ACTIVE",
            lease_token=lease.lease_token,
        )

    def __call__(self, job_id: str, command_id: str) -> OrchestrationDispatchOutcome:
        selected_worker = self._select_worker(job_id)
        self.current_command_id = command_id
        outcome = asyncio.run(
            self.supervisor.start_cycle_job(job_id, command_id=command_id)
        )
        assert isinstance(outcome, OrchestrationDispatchOutcome)
        self.calls.append(
            {
                "job_id": job_id,
                "command_id": command_id,
                "attempt_id": outcome.attempt.attempt_id,
                "worker_id": selected_worker,
                "supervisor_instance_id": self.supervisor.instance_id,
            }
        )
        if self.crash_after_claim_once and not self._crashed:
            self._crashed = True
            raise RuntimeError("deterministic fixture crash after exact supervisor claim")
        return outcome


def _orchestration_profile(
    dispatch: OrchestrationDispatchOutcome,
) -> RequestedExecutionProfile:
    attempt = dispatch.attempt
    return RequestedExecutionProfile(
        worker_id=str(attempt.worker_id),
        provider="codex",
        requested_model="fixture-model",
        harness_kind="fixture",
        harness_binary_digest="a" * 64,
        harness_version="1",
        workspace=WorkspaceIdentity(
            "/tmp/phase1fc-work",
            "b" * 40,
            1,
            2,
            _FIXTURE_WORKSPACE_UID,
            _FIXTURE_WORKSPACE_GID,
        ),
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


def _complete_fixture_role(
    runtime: Runtime,
    dispatch: OrchestrationDispatchOutcome,
    role_result: dict[str, Any],
    *,
    identity_seed: int,
) -> dict[str, Any]:
    """Complete one typed role through inert OHF Runtime boundaries."""

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
    start = OperationId(f"ohf-op:acceptance-{identity_seed}-start")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        operation_id=start,
    )
    process = ProcessIdentityObservation(
        identity_seed, identity_seed, f"start-{identity_seed}", "boot-acceptance"
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
            "path": f"/tmp/phase1fc-provider-home-{identity_seed}",
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
    turn_op = OperationId(f"ohf-op:acceptance-{identity_seed}-turn")
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
    artifact_digest = hashlib.sha256(
        f"artifact-{identity_seed}".encode("utf-8")
    ).hexdigest()
    harness.record_candidate_evidence(
        turn=turn,
        candidate=CandidateResult(
            attempt.attempt_id,
            epoch.session_epoch_id,
            generation.process_generation_id,
            artifact_digest,
            "typed deterministic fixture candidate",
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
        "summary": "bounded typed deterministic fixture result",
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
        canonical_result_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        canonical_result_byte_length=len(canonical.encode("utf-8")),
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
    latest_attempt = runtime.attempts.get_attempt(attempt.attempt_id)
    assert latest_attempt is not None
    with runtime.store.read() as connection:
        admission_event = connection.execute(
            """SELECT payload_json FROM events
               WHERE aggregate_type='process_generation' AND aggregate_id=?
                 AND event_type='ORCHESTRATION_WORK_ADMITTED'""",
            (generation.process_generation_id,),
        ).fetchone()
    assert admission_event is not None
    admission = json.loads(str(admission_event["payload_json"]))
    proof = {
        "role": job.orchestration_role,
        "job_id": job.job_id,
        "attempt_id": attempt.attempt_id,
        "worker_id": attempt.worker_id,
        "session_epoch_id": epoch.session_epoch_id,
        "process_generation_id": generation.process_generation_id,
        "turn_id": turn.turn_id,
        "effective_grant_digest": latest_attempt.effective_grant_digest,
        "placement_snapshot_digest": latest_attempt.placement_snapshot_digest,
        "execution_principal_snapshot_digest": (
            latest_attempt.execution_principal_snapshot_digest
        ),
        "principal_observation_digest": admission["principal_observation_digest"],
        "work_admission_digest": result_digest(admission),
        "candidate_artifact_digest": artifact_digest,
        "result_envelope_digest": seal["result_envelope_digest"],
        "role_result_digest": seal["role_result_digest"],
        "terminal_evidence_digest": terminal["terminal_evidence_digest"],
    }
    proof["proof_digest"] = _digest(proof)
    return proof


def _dispatch_boundary_receipt(root: Path) -> dict[str, Any]:
    """Prove the default cycle has no claim/provider authority."""

    runtime = Runtime.at(root, clock=lambda: 1_777_000_000_000)
    _register(runtime, "worker-a")
    admitted = submit_intent(runtime, _intent("CEO-ACCEPTANCE-DISPATCH-BOUNDARY"))
    root_id = str(admitted["job_id"])
    cycle = CooCycle(runtime)
    planner = cycle.run_once(root_id)
    blocked = cycle.run_once(root_id)
    with runtime.store.read() as connection:
        attempt_count = int(connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0])
    proof = {
        "acceptance_id": DISPATCH_BOUNDARY_ACCEPTANCE_ID,
        "root_job_id": root_id,
        "planner_job_id": planner.selected_job_id,
        "planner_action": planner.action,
        "dispatch_action": blocked.action,
        "dispatch_command_id": blocked.command_id,
        "blocked_reason": blocked.receipt.get("reason"),
        "attempt_count": attempt_count,
        "provider_calls": 0,
    }
    assert proof["planner_action"] == "PLANNER_CREATED"
    assert proof["dispatch_action"] == "BLOCKED"
    assert proof["blocked_reason"] == "exact_dispatch_unavailable"
    assert proof["attempt_count"] == 0
    proof["acceptance_digest"] = _digest(proof)
    return proof


def _dispatch_crash_replay_receipt(root_path: Path) -> dict[str, Any]:
    runtime = Runtime.at(root_path, clock=lambda: 1_777_000_050_000)
    _register(runtime, "worker-a")
    admitted = submit_intent(
        runtime, _intent("CEO-ACCEPTANCE-SUPERVISOR-CLAIM-CRASH")
    )
    root_id = str(admitted["job_id"])
    sentinel = runtime.jobs.create_job("unrelated queued sentinel")
    sentinel_before = sentinel.to_dict()
    dispatcher = _ExactSupervisorFixtureDispatcher(runtime, root_path)
    dispatcher.crash_after_claim_once = True
    cycle = CooCycle(runtime, dispatcher=dispatcher)
    created = cycle.run_once(root_id)
    assert created.action == "PLANNER_CREATED"
    raised = False
    try:
        cycle.run_once(root_id)
    except RuntimeError as exc:
        raised = "after exact supervisor claim" in str(exc)
    assert raised
    planner_id = str(created.selected_job_id)
    planner_after_crash = runtime.jobs.get_job(planner_id)
    assert planner_after_crash is not None and planner_after_crash.current_attempt_id
    attempt_id = str(planner_after_crash.current_attempt_id)
    with runtime.store.read() as connection:
        blocked_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='COO_CYCLE_BLOCKED' "
                "AND job_id=?",
                (root_id,),
            ).fetchone()[0]
        )
    replay = cycle.run_once(root_id)
    assert replay.action == "DISPATCHED"
    assert replay.receipt["attempt"]["attempt_id"] == attempt_id
    planner_after_replay = runtime.jobs.get_job(planner_id)
    assert planner_after_replay is not None
    proof = {
        "acceptance_id": DISPATCH_REPLAY_ACCEPTANCE_ID,
        "root_job_id": root_id,
        "planner_job_id": planner_id,
        "ambiguous_return_raised": raised,
        "attempt_id_after_crash": attempt_id,
        "attempt_id_after_replay": replay.receipt["attempt"]["attempt_id"],
        "attempt_count_after_replay": planner_after_replay.attempt_count,
        "blocked_event_count": blocked_count,
        "supervisor_dispatch_calls": dispatcher.calls,
        "sentinel": _sentinel_proof(runtime, sentinel_before),
    }
    assert proof["attempt_id_after_crash"] == proof["attempt_id_after_replay"]
    assert proof["attempt_count_after_replay"] == 1
    assert proof["blocked_event_count"] == 0
    proof["acceptance_digest"] = _digest(proof)
    return proof


def _typed_plan(root_id: str, plan_attempt_id: str) -> dict[str, Any]:
    return {
        "schema_version": "mastermind.execution_plan/v1",
        "root_job_id": root_id,
        "plan_attempt_id": plan_attempt_id,
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


def _typed_review(
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


def _typed_fixture_through_work(
    root_path: Path,
    *,
    intent_id: str,
    review_workers: tuple[str, ...],
    identity_seed: int,
) -> tuple[
    Runtime,
    CooCycle,
    _ExactSupervisorFixtureDispatcher,
    Any,
    OrchestrationDispatchOutcome,
    dict[str, Any],
    OrchestrationDispatchOutcome,
    dict[str, Any],
    dict[str, Any],
]:
    runtime = Runtime.at(root_path, clock=lambda: 1_777_000_200_000)
    _register(runtime, "worker-a")
    _register(runtime, "worker-b")
    admitted = submit_intent(runtime, _intent(intent_id))
    root = runtime.jobs.get_job(str(admitted["job_id"]))
    assert root is not None
    sentinel = runtime.jobs.create_job("unrelated queued sentinel")
    sentinel_before = sentinel.to_dict()
    dispatcher = _ExactSupervisorFixtureDispatcher(
        runtime, root_path, review_workers=review_workers
    )
    cycle = CooCycle(runtime, dispatcher=dispatcher)
    created = cycle.run_once(root.job_id)
    assert created.action == "PLANNER_CREATED"
    dispatched = cycle.run_once(root.job_id)
    assert dispatched.action == "DISPATCHED"
    planner = runtime.attempts.get_attempt(
        str(runtime.jobs.get_job(str(created.selected_job_id)).current_attempt_id)
    )
    assert planner is not None
    planner_dispatch = OrchestrationDispatchOutcome(
        command_id=str(dispatched.command_id),
        job_id=planner.job_id,
        attempt=planner,
        outcome="ACTIVE",
        lease_token=_lease_token(runtime, planner.attempt_id),
    )
    plan_body = _typed_plan(root.job_id, planner.attempt_id)
    plan_proof = _complete_fixture_role(
        runtime, planner_dispatch, plan_body, identity_seed=identity_seed
    )
    plan_admission = cycle.run_once(root.job_id)
    assert plan_admission.action == "PLAN_ADMITTED"
    work_dispatch_outcome = cycle.run_once(root.job_id)
    assert work_dispatch_outcome.action == "DISPATCHED"
    work_job = runtime.jobs.get_job(str(work_dispatch_outcome.selected_job_id))
    assert work_job is not None and work_job.current_attempt_id
    work_attempt = runtime.attempts.get_attempt(str(work_job.current_attempt_id))
    assert work_attempt is not None
    work_dispatch = OrchestrationDispatchOutcome(
        command_id=str(work_dispatch_outcome.command_id),
        job_id=work_job.job_id,
        attempt=work_attempt,
        outcome="ACTIVE",
        lease_token=_lease_token(runtime, work_attempt.attempt_id),
    )
    plan_digest = result_digest(plan_body)
    work_body = {
        "schema_version": "mastermind.work_result/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner.attempt_id,
        "plan_digest": plan_digest,
        "plan_step_id": "step-1",
        "repair_round": 0,
        "artifacts": [],
        "evidence_digests": [],
    }
    work_proof = _complete_fixture_role(
        runtime, work_dispatch, work_body, identity_seed=identity_seed + 1
    )
    return (
        runtime,
        cycle,
        dispatcher,
        root,
        planner_dispatch,
        plan_proof,
        work_dispatch,
        work_proof,
        sentinel_before,
    )


def _sentinel_proof(
    runtime: Runtime, sentinel_before: dict[str, Any]
) -> dict[str, Any]:
    sentinel_id = str(sentinel_before["job_id"])
    sentinel_after = runtime.jobs.get_job(sentinel_id)
    assert sentinel_after is not None
    proof = {
        "job_id": sentinel_id,
        "before_digest": _digest(sentinel_before),
        "after_digest": _digest(sentinel_after.to_dict()),
        "attempt_count": len(runtime.attempts.list_attempts(sentinel_id)),
    }
    assert proof["before_digest"] == proof["after_digest"]
    assert proof["attempt_count"] == 0
    return proof


def _happy_path_receipt(root_path: Path) -> dict[str, Any]:
    (
        runtime,
        cycle,
        dispatcher,
        root,
        planner,
        plan_proof,
        work,
        work_proof,
        sentinel_before,
    ) = _typed_fixture_through_work(
        root_path,
        intent_id="CEO-ACCEPTANCE-TYPED-HAPPY",
        review_workers=("worker-b",),
        identity_seed=4101,
    )
    review_created = cycle.run_once(root.job_id)
    assert review_created.action == "REVIEW_CREATED"
    review_dispatched = cycle.run_once(root.job_id)
    assert review_dispatched.action == "DISPATCHED"
    review_job = runtime.jobs.get_job(str(review_dispatched.selected_job_id))
    assert review_job is not None and review_job.current_attempt_id
    review_attempt = runtime.attempts.get_attempt(str(review_job.current_attempt_id))
    assert review_attempt is not None
    review_dispatch = OrchestrationDispatchOutcome(
        command_id=str(review_dispatched.command_id),
        job_id=review_job.job_id,
        attempt=review_attempt,
        outcome="ACTIVE",
        lease_token=_lease_token(runtime, review_attempt.attempt_id),
    )
    review_body = _typed_review(
        root_id=root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=str(runtime.jobs.get_job(work.job_id).plan_digest),
        target_job_id=work.job_id,
        target_attempt_id=work.attempt.attempt_id,
        target_result_digest=work_proof["role_result_digest"],
        repair_round=0,
        verdict="approve",
    )
    review_proof = _complete_fixture_role(
        runtime, review_dispatch, review_body, identity_seed=4103
    )
    handoff_outcome = cycle.run_once(root.job_id)
    assert handoff_outcome.action == "HANDOFF_CREATED"
    handoff = runtime.jobs.get_cycle_handoff(root.job_id)
    root_dispatch_outcome = cycle.run_once(root.job_id)
    assert root_dispatch_outcome.action == "DISPATCHED"
    root_job = runtime.jobs.get_job(root.job_id)
    assert root_job is not None and root_job.current_attempt_id
    root_attempt = runtime.attempts.get_attempt(str(root_job.current_attempt_id))
    assert root_attempt is not None
    aggregation_dispatch = OrchestrationDispatchOutcome(
        command_id=str(root_dispatch_outcome.command_id),
        job_id=root.job_id,
        attempt=root_attempt,
        outcome="ACTIVE",
        lease_token=_lease_token(runtime, root_attempt.attempt_id),
    )
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
        "aggregate_summary": "One bounded independently reviewed result is ready.",
        "evidence_digests": [],
    }
    aggregation_proof = _complete_fixture_role(
        runtime, aggregation_dispatch, aggregation_body, identity_seed=4104
    )
    final = runtime.jobs.get_job(root.job_id)
    assert final is not None and final.status is JobStatus.COMPLETED
    assert cycle.run_once(root.job_id).action == "NO_ACTION"
    proof: dict[str, Any] = {
        "acceptance_id": HAPPY_PATH_ACCEPTANCE_ID,
        "root_job_id": root.job_id,
        "actions": [
            "PLANNER_CREATED",
            "DISPATCHED",
            "PLAN_ADMITTED",
            "DISPATCHED",
            "REVIEW_CREATED",
            "DISPATCHED",
            "HANDOFF_CREATED",
            "DISPATCHED",
            "NO_ACTION",
        ],
        "supervisor_dispatch_calls": dispatcher.calls,
        "role_proofs": [plan_proof, work_proof, review_proof, aggregation_proof],
        "handoff_digest": handoff["handoff_digest"],
        "handoff_event_command_id": handoff["command_id"],
        "independent_workers": {
            "work": work_proof["worker_id"],
            "review": review_proof["worker_id"],
            "different": work_proof["worker_id"] != review_proof["worker_id"],
        },
        "sentinel": _sentinel_proof(runtime, sentinel_before),
        "root_status": final.status.value,
    }
    assert proof["independent_workers"]["different"] is True
    proof["acceptance_digest"] = _digest(proof)
    return proof


def _repair_path_receipt(root_path: Path) -> dict[str, Any]:
    (
        runtime,
        cycle,
        dispatcher,
        root,
        planner,
        plan_proof,
        work,
        work_proof,
        sentinel_before,
    ) = _typed_fixture_through_work(
        root_path,
        intent_id="CEO-ACCEPTANCE-REJECT-REPAIR",
        review_workers=("worker-b", "worker-b"),
        identity_seed=4201,
    )
    first_review_created = cycle.run_once(root.job_id)
    assert first_review_created.action == "REVIEW_CREATED"
    first_review_dispatched = cycle.run_once(root.job_id)
    assert first_review_dispatched.action == "DISPATCHED"
    first_review_job = runtime.jobs.get_job(str(first_review_dispatched.selected_job_id))
    assert first_review_job is not None and first_review_job.current_attempt_id
    first_review_attempt = runtime.attempts.get_attempt(
        str(first_review_job.current_attempt_id)
    )
    assert first_review_attempt is not None
    first_review_dispatch = OrchestrationDispatchOutcome(
        command_id=str(first_review_dispatched.command_id),
        job_id=first_review_job.job_id,
        attempt=first_review_attempt,
        outcome="ACTIVE",
        lease_token=_lease_token(runtime, first_review_attempt.attempt_id),
    )
    plan_digest = str(runtime.jobs.get_job(work.job_id).plan_digest)
    reject_body = _typed_review(
        root_id=root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=plan_digest,
        target_job_id=work.job_id,
        target_attempt_id=work.attempt.attempt_id,
        target_result_digest=work_proof["role_result_digest"],
        repair_round=0,
        verdict="reject",
    )
    reject_proof = _complete_fixture_role(
        runtime, first_review_dispatch, reject_body, identity_seed=4203
    )
    repair_created = cycle.run_once(root.job_id)
    assert repair_created.action == "REPAIR_CREATED"
    assert reject_proof["role_result_digest"] in str(repair_created.command_id)
    late_predecessor_review_refused = False
    try:
        runtime.jobs.create_cycle_review(
            root.job_id,
            work.job_id,
            command_id=f"coo-cycle:{root.job_id}:create-review:{work.job_id}:2",
        )
    except StateConflict:
        late_predecessor_review_refused = True
    assert late_predecessor_review_refused
    repair_dispatched = cycle.run_once(root.job_id)
    assert repair_dispatched.action == "DISPATCHED"
    repair_job = runtime.jobs.get_job(str(repair_dispatched.selected_job_id))
    assert repair_job is not None and repair_job.current_attempt_id
    repair_attempt = runtime.attempts.get_attempt(str(repair_job.current_attempt_id))
    assert repair_attempt is not None
    repair_dispatch = OrchestrationDispatchOutcome(
        command_id=str(repair_dispatched.command_id),
        job_id=repair_job.job_id,
        attempt=repair_attempt,
        outcome="ACTIVE",
        lease_token=_lease_token(runtime, repair_attempt.attempt_id),
    )
    repair_body = {
        "schema_version": "mastermind.repair_result/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner.attempt.attempt_id,
        "plan_digest": plan_digest,
        "plan_step_id": "step-1",
        "repair_round": 1,
        "supersedes_job_id": work.job_id,
        "rejected_review_job_id": first_review_job.job_id,
        "rejected_review_result_digest": reject_proof["role_result_digest"],
        "artifacts": [],
        "evidence_digests": [],
    }
    repair_proof = _complete_fixture_role(
        runtime, repair_dispatch, repair_body, identity_seed=4204
    )
    handoff_before_current_approval_refused = False
    try:
        runtime.jobs.create_cycle_handoff(
            root.job_id,
            command_id=f"coo-cycle:{root.job_id}:aggregation-handoff:1",
        )
    except StateConflict:
        handoff_before_current_approval_refused = True
    assert handoff_before_current_approval_refused
    repair_review_created = cycle.run_once(root.job_id)
    assert repair_review_created.action == "REVIEW_CREATED"
    repair_review_dispatched = cycle.run_once(root.job_id)
    assert repair_review_dispatched.action == "DISPATCHED"
    repair_review_job = runtime.jobs.get_job(
        str(repair_review_dispatched.selected_job_id)
    )
    assert repair_review_job is not None and repair_review_job.current_attempt_id
    repair_review_attempt = runtime.attempts.get_attempt(
        str(repair_review_job.current_attempt_id)
    )
    assert repair_review_attempt is not None
    repair_review_dispatch = OrchestrationDispatchOutcome(
        command_id=str(repair_review_dispatched.command_id),
        job_id=repair_review_job.job_id,
        attempt=repair_review_attempt,
        outcome="ACTIVE",
        lease_token=_lease_token(runtime, repair_review_attempt.attempt_id),
    )
    approve_repair = _typed_review(
        root_id=root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=plan_digest,
        target_job_id=repair_job.job_id,
        target_attempt_id=repair_attempt.attempt_id,
        target_result_digest=repair_proof["role_result_digest"],
        repair_round=1,
        verdict="approve",
    )
    approve_proof = _complete_fixture_role(
        runtime, repair_review_dispatch, approve_repair, identity_seed=4205
    )
    handoff_outcome = cycle.run_once(root.job_id)
    assert handoff_outcome.action == "HANDOFF_CREATED"
    handoff = runtime.jobs.get_cycle_handoff(root.job_id)
    revision = handoff["revisions"][0]
    assert revision["current_job_id"] == repair_job.job_id
    assert revision["qualifying_review_job_id"] == repair_review_job.job_id
    proof = {
        "acceptance_id": REPAIR_PATH_ACCEPTANCE_ID,
        "root_job_id": root.job_id,
        "repair_command_id": repair_created.command_id,
        "late_predecessor_review_refused": late_predecessor_review_refused,
        "handoff_before_current_approval_refused": (
            handoff_before_current_approval_refused
        ),
        "current_revision_job_id": revision["current_job_id"],
        "current_revision_round": revision["repair_round"],
        "qualifying_review_job_id": revision["qualifying_review_job_id"],
        "handoff_digest": handoff["handoff_digest"],
        "supervisor_dispatch_calls": dispatcher.calls,
        "role_proofs": [
            plan_proof,
            work_proof,
            reject_proof,
            repair_proof,
            approve_proof,
        ],
        "sentinel": _sentinel_proof(runtime, sentinel_before),
    }
    proof["acceptance_digest"] = _digest(proof)
    return proof


def _void_replacement_receipt(root_path: Path) -> dict[str, Any]:
    (
        runtime,
        cycle,
        dispatcher,
        root,
        planner,
        plan_proof,
        work,
        work_proof,
        sentinel_before,
    ) = _typed_fixture_through_work(
        root_path,
        intent_id="CEO-ACCEPTANCE-VOID-REPLACEMENT",
        review_workers=("worker-a", "worker-b"),
        identity_seed=4301,
    )
    first_created = cycle.run_once(root.job_id)
    assert first_created.action == "REVIEW_CREATED"
    first_dispatched = cycle.run_once(root.job_id)
    assert first_dispatched.action == "DISPATCHED"
    first_job = runtime.jobs.get_job(str(first_dispatched.selected_job_id))
    assert first_job is not None and first_job.current_attempt_id
    first_attempt = runtime.attempts.get_attempt(str(first_job.current_attempt_id))
    assert first_attempt is not None
    first_dispatch = OrchestrationDispatchOutcome(
        command_id=str(first_dispatched.command_id),
        job_id=first_job.job_id,
        attempt=first_attempt,
        outcome="ACTIVE",
        lease_token=_lease_token(runtime, first_attempt.attempt_id),
    )
    plan_digest = str(runtime.jobs.get_job(work.job_id).plan_digest)
    approve_body = _typed_review(
        root_id=root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=plan_digest,
        target_job_id=work.job_id,
        target_attempt_id=work.attempt.attempt_id,
        target_result_digest=work_proof["role_result_digest"],
        repair_round=0,
        verdict="approve",
    )
    void_proof = _complete_fixture_role(
        runtime, first_dispatch, approve_body, identity_seed=4303
    )
    replacement_created = cycle.run_once(root.job_id)
    assert replacement_created.action == "REVIEW_CREATED"
    assert str(replacement_created.command_id).endswith(":2")
    replacement_dispatched = cycle.run_once(root.job_id)
    assert replacement_dispatched.action == "DISPATCHED"
    replacement_job = runtime.jobs.get_job(
        str(replacement_dispatched.selected_job_id)
    )
    assert replacement_job is not None and replacement_job.current_attempt_id
    replacement_attempt = runtime.attempts.get_attempt(
        str(replacement_job.current_attempt_id)
    )
    assert replacement_attempt is not None
    replacement_dispatch = OrchestrationDispatchOutcome(
        command_id=str(replacement_dispatched.command_id),
        job_id=replacement_job.job_id,
        attempt=replacement_attempt,
        outcome="ACTIVE",
        lease_token=_lease_token(runtime, replacement_attempt.attempt_id),
    )
    replacement_proof = _complete_fixture_role(
        runtime, replacement_dispatch, approve_body, identity_seed=4304
    )
    handoff_outcome = cycle.run_once(root.job_id)
    assert handoff_outcome.action == "HANDOFF_CREATED"
    handoff = runtime.jobs.get_cycle_handoff(root.job_id)
    revision = handoff["revisions"][0]
    void_history = [
        item
        for item in handoff["rejected_history"]
        if item["job_id"] == first_job.job_id and item["independent"] is False
    ]
    assert len(void_history) == 1
    assert revision["qualifying_review_job_id"] == replacement_job.job_id
    proof = {
        "acceptance_id": VOID_PATH_ACCEPTANCE_ID,
        "root_job_id": root.job_id,
        "void_review_job_id": first_job.job_id,
        "void_review_worker_id": void_proof["worker_id"],
        "reviewed_worker_id": work_proof["worker_id"],
        "replacement_review_job_id": replacement_job.job_id,
        "replacement_review_worker_id": replacement_proof["worker_id"],
        "replacement_command_id": replacement_created.command_id,
        "qualifying_review_job_id": revision["qualifying_review_job_id"],
        "handoff_digest": handoff["handoff_digest"],
        "supervisor_dispatch_calls": dispatcher.calls,
        "role_proofs": [
            plan_proof,
            work_proof,
            void_proof,
            replacement_proof,
        ],
        "sentinel": _sentinel_proof(runtime, sentinel_before),
    }
    assert proof["void_review_worker_id"] == proof["reviewed_worker_id"]
    assert proof["replacement_review_worker_id"] != proof["reviewed_worker_id"]
    proof["acceptance_digest"] = _digest(proof)
    return proof


def _cycle_receipt(root: Path) -> dict[str, Any]:
    runtime = Runtime.at(root, clock=lambda: 1_777_000_000_000)
    _register(runtime, "worker-a")
    admitted = submit_intent(runtime, _intent("CEO-ACCEPTANCE-CYCLE"))
    root_id = str(admitted["job_id"])
    dispatcher = _ExactSupervisorFixtureDispatcher(runtime, root)
    cycle = CooCycle(runtime, dispatcher=dispatcher)
    outcomes = [cycle.run_once(root_id)]
    outcomes.append(cycle.run_once(root_id))
    planner_id = str(outcomes[0].selected_job_id)
    planner = runtime.jobs.get_job(planner_id)
    assert planner is not None and planner.current_attempt_id
    first = runtime.attempts.get_attempt(str(planner.current_attempt_id))
    assert first is not None
    runtime.attempts.fail_attempt(
        first.attempt_id,
        fence_generation=first.fence_generation,
        lease_token=_lease_token(runtime, first.attempt_id),
        payload={"summary": "deterministic adverse fixture", "errors": ["failed"]},
    )
    outcomes.append(cycle.run_once(root_id))
    planner = runtime.jobs.get_job(planner_id)
    assert planner is not None and planner.current_attempt_id
    events_before = len(runtime.events.list_events(job_id=root_id))
    replay = cycle.run_once(root_id)
    events_after = len(runtime.events.list_events(job_id=root_id))
    action_receipts = [outcome.to_dict() for outcome in outcomes]
    normalized = {
        "acceptance_id": CYCLE_ACCEPTANCE_ID,
        "root_job_id": root_id,
        "actions": [item["action"] for item in action_receipts],
        "command_ids": [item["command_id"] for item in action_receipts],
        "selected_job_ids": [item["selected_job_id"] for item in action_receipts],
        "blocked_reason": action_receipts[-1]["receipt"].get("reason"),
        "replay_outcome_digest": replay.to_dict()["outcome_digest"],
        "replay_matches_blocked": replay.to_dict() == action_receipts[-1],
        "planner_attempt_count": planner.attempt_count,
        "events_before_replay": events_before,
        "events_after_replay": events_after,
        "supervisor_dispatch_calls": dispatcher.calls,
    }
    assert normalized["actions"] == ["PLANNER_CREATED", "DISPATCHED", "BLOCKED"]
    assert normalized["planner_attempt_count"] == 1
    assert len(normalized["supervisor_dispatch_calls"]) == 1
    assert normalized["replay_matches_blocked"] is True
    assert events_before == events_after
    normalized["acceptance_digest"] = _digest(normalized)
    return normalized


def _tx9_receipt(root: Path) -> dict[str, Any]:
    runtime = Runtime.at(root, clock=lambda: 1_777_000_100_000)
    _register(runtime, "worker-a")
    admitted = submit_intent(runtime, _intent("CEO-ACCEPTANCE-TX9"))
    root_id = str(admitted["job_id"])
    dispatcher = _ExactSupervisorFixtureDispatcher(runtime, root)
    cycle = CooCycle(runtime, dispatcher=dispatcher)
    planner_outcome = cycle.run_once(root_id)
    dispatch_outcome = cycle.run_once(root_id)
    planner_id = str(planner_outcome.selected_job_id)
    planner = runtime.jobs.get_job(planner_id)
    assert planner is not None and planner.current_attempt_id
    attempt = runtime.attempts.get_attempt(str(planner.current_attempt_id))
    assert attempt is not None
    active_dispatch = OrchestrationDispatchOutcome(
        command_id=str(dispatch_outcome.command_id),
        job_id=planner_id,
        attempt=attempt,
        outcome="ACTIVE",
        lease_token=_lease_token(runtime, attempt.attempt_id),
    )
    profile = _orchestration_profile(active_dispatch)
    sealed = runtime.operator_harness.seal_operator_harness_attempt(
        attempt.attempt_id,
        fence_generation=attempt.fence_generation,
        lease_token=str(active_dispatch.lease_token),
        requested=profile,
    )
    start = OperationId("ohf-op:acceptance-tx9-start")
    epoch, generation = runtime.operator_harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=str(active_dispatch.lease_token),
        operation_id=start,
    )
    process = ProcessIdentityObservation(
        4401, 4401, "start-4401", "boot-acceptance"
    )
    runtime.operator_harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=start,
        fence_generation=sealed.fence_generation,
        lease_token=str(active_dispatch.lease_token),
        provider_session_id="SESSION-TX9-ACCEPTANCE",
        process=process,
    )
    assert runtime.operator_harness.invalidate_after_restore() == 1
    with runtime.store.read() as connection:
        quota_before = dict(
            connection.execute(
                """SELECT * FROM worker_quota_classes
                   WHERE worker_id='worker-a' AND quota_class='default'"""
            ).fetchone()
        )
    _register(runtime, "worker-b")
    requeued = cycle.run_once(root_id)
    with runtime.store.read() as connection:
        quota_after = dict(
            connection.execute(
                """SELECT * FROM worker_quota_classes
                   WHERE worker_id='worker-a' AND quota_class='default'"""
            ).fetchone()
        )
    continued = cycle.run_once(root_id)
    current = runtime.jobs.get_job(planner_id)
    assert current is not None and current.current_attempt_id
    fresh = runtime.attempts.get_attempt(str(current.current_attempt_id))
    assert fresh is not None
    proof = {
        "acceptance_id": TX9_ACCEPTANCE_ID,
        "root_job_id": root_id,
        "planner_job_id": planner_id,
        "invalidated_attempt_id": attempt.attempt_id,
        "invalidated_worker_id": attempt.worker_id,
        "invalidated_session_epoch_id": epoch.session_epoch_id,
        "invalidated_process_generation_id": generation.process_generation_id,
        "invalidated_quota_digest_before": _digest(quota_before),
        "invalidated_quota_digest_after_requeue": _digest(quota_after),
        "quota_byte_state_equal": quota_before == quota_after,
        "requeue_action": requeued.action,
        "requeue_kind": requeued.receipt.get("requeue_kind"),
        "requeue_command_id": requeued.command_id,
        "continuation_action": continued.action,
        "fresh_attempt_id": fresh.attempt_id,
        "fresh_worker_id": fresh.worker_id,
        "quarantined_worker_excluded": fresh.worker_id != attempt.worker_id,
        "initial_dispatch_command_id": dispatch_outcome.command_id,
        "supervisor_dispatch_calls": dispatcher.calls,
    }
    assert proof["quota_byte_state_equal"] is True
    assert proof["requeue_kind"] == "TX9_DETACHED"
    assert proof["quarantined_worker_excluded"] is True
    proof["acceptance_digest"] = _digest(proof)
    return proof


def run_acceptance(release_sha: str) -> dict[str, Any]:
    if len(release_sha) != 40 or any(ch not in "0123456789abcdef" for ch in release_sha):
        raise ValueError("release SHA must be exactly 40 lowercase hexadecimal characters")
    original_uuid4 = executive_runtime.uuid4
    original_token = executive_runtime.secrets.token_urlsafe
    counter = iter(range(1, 10_000))
    executive_runtime.uuid4 = lambda: uuid.UUID(int=next(counter))
    executive_runtime.secrets.token_urlsafe = lambda _n=32: "fixture-lease-token"
    try:
        with tempfile.TemporaryDirectory(prefix="mastermind-p1fc-acceptance-") as tmp:
            boundary = Path(tmp).resolve()
            dispatch_boundary = _dispatch_boundary_receipt(boundary / "dispatch-boundary")
            dispatch_crash_replay = _dispatch_crash_replay_receipt(
                boundary / "dispatch-crash-replay"
            )
            happy_path = _happy_path_receipt(boundary / "happy-path")
            repair_path = _repair_path_receipt(boundary / "repair-path")
            void_replacement = _void_replacement_receipt(
                boundary / "void-replacement"
            )
            cycle = _cycle_receipt(boundary / "cycle")
            tx9 = _tx9_receipt(boundary / "tx9")
            receipt: dict[str, Any] = {
                "schema_version": "mastermind.executive_phase1fc_acceptance/v1",
                "acceptance_id": ACCEPTANCE_ID,
                "release_sha": release_sha,
                "policy_sha": CooCyclePolicy.load().policy_sha256,
                "role_schema_digests": dict(GOLDEN_ROLE_SCHEMA_DIGESTS),
                "dispatch_boundary": dispatch_boundary,
                "dispatch_crash_replay": dispatch_crash_replay,
                "happy_path": happy_path,
                "repair_path": repair_path,
                "void_replacement": void_replacement,
                "cycle": cycle,
                "tx9": tx9,
                "inertness": {
                    "temporary_runtime_boundary": True,
                    "runtime_roots_removed_on_exit": True,
                    "provider_adapters_constructed": 0,
                    "provider_calls": 0,
                    "executive_supervisor_fixture_instances": 6,
                    "host_install_or_migration_calls": 0,
                    "production_armed": False,
                },
            }
            receipt["receipt_digest"] = _digest(receipt)
            return receipt
    finally:
        executive_runtime.uuid4 = original_uuid4
        executive_runtime.secrets.token_urlsafe = original_token


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-sha", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(
        json.dumps(
            run_acceptance(args.release_sha), sort_keys=True, separators=(",", ":")
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
