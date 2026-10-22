"""A2-FRESH finite-root admission and fresh-effect transaction guards.

These tests exercise the *next* behavioural slice on top of the frozen
A1-ARM partial Runtime: a bound finite-control context must admit only
its own exact strict-v2 intent (root admission), and every fresh
execution effect on a finite-armed root (child creation, claim, requeue,
block, retry decision, capacity carrier) must be refused unless the
durable arm projection still matches the bound context, the live policy
and persisted host binding still equal the arm pins, the in-transaction
clock is inside the window, and the all-history attempt count is below
the cap.

Read-only status and every exact command replay stay available after
cutoff.  Fresh refusals write nothing: no diagnostic Events, no Job,
Attempt, or quota mutations.

The canonical fixture bodies (``MutableClock``, ``_v2_intent``,
``_register``, ``_v3_execution_binding``/armed v2 derivation,
``_orchestration_profile``, ``_orchestration_attestation``,
``_complete_ohf_role``, the finite definition/issue/arm helpers, the TX9
restore-detach SQL) are copies of the pointers named by the accepted
A1-ARM contract, kept in this file so the module stands alone.  The
private composition producer is used here explicitly as a test fixture:
it is not a wire, sandbox, or installation proof.

Every ``pytest.raises(StateConflict, match=...)`` refusal below is the
required behaviour-RED on the unguarded frozen baseline: today those
operations wrongly succeed.  Positive controls (armed-cycle families,
legacy no-context behaviour, replays) pass before and after the guards.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest

import control_plane.executive_runtime as executive_runtime
from control_plane.ceo_intent import (
    CeoIntentError,
    INTENT_SCHEMA,
    INTENT_SCHEMA_V2,
    intent_fingerprint,
    submit_intent,
    validate_intent,
)
from control_plane.executive_authority import ExecutiveAuthorityPolicy
from control_plane.executive_coo_policy import CooCyclePolicy
from control_plane.executive_orchestration_principal import (
    OperatorPrincipalObservation,
)
from control_plane.executive_orchestration_result import (
    RESULT_SCHEMA,
    RawRoleResultObservation,
    canonical_bytes as result_canonical_bytes,
    canonical_digest as result_digest,
)
from control_plane.executive_runtime import (
    FiniteControlContext,
    OrchestrationDispatchOutcome,
    Runtime,
    StateConflict,
    finite_host_binding_digest,
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

TEST_CONFIG_PIN = hashlib.sha256(
    b"a2-fresh-labelled-test-config-snapshot"
).hexdigest()
TEST_SOURCE_RELEASE_PIN = hashlib.sha256(
    b"a2-fresh-labelled-test-source-release-manifest"
).hexdigest()
TEST_BINDING_PIN = hashlib.sha256(
    b"a2-fresh-labelled-test-composition-binding"
).hexdigest()
ATTESTATION_A = hashlib.sha256(b"a2-fresh-test-attestation-one").hexdigest()

DRIFT_PIN = "9" * 64


# ---------------------------------------------------------------------------
# canonical fixture copies (phase1fc / finite_arm pointers)
# ---------------------------------------------------------------------------


class MutableClock:
    def __init__(self, value: int = 1_800_000_000_000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value

    def advance(self, *, seconds: int) -> None:
        self.value += seconds * 1_000


def _canonical(value) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _full_snapshot(runtime: Runtime) -> dict[str, list[dict[str, Any]]]:
    """Exact full rows of every state a fresh effect could mutate."""

    path = runtime.store.path
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:

        def rows(table: str, order: str) -> list[dict[str, Any]]:
            return [
                dict(row)
                for row in connection.execute(
                    f"SELECT * FROM {table} ORDER BY {order}"
                )
            ]

        return {
            "jobs": rows("jobs", "job_id"),
            "attempts": rows("attempts", "attempt_id"),
            "quota": rows("worker_quota_classes", "worker_id, quota_class"),
            "events": rows("events", "event_id"),
        }
    finally:
        connection.close()


def _v2_intent(**overrides):
    value = {
        "schema": INTENT_SCHEMA_V2,
        "intent_id": "CEO-A2FRESH-001",
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
            },
            **{
                name: {
                    "provider": "codex",
                    "capabilities": ["read", "research"],
                    "cost_class": "small",
                    "model": "gpt-5.6-sol",
                    "effort": "xhigh",
                    "metadata": {
                        "routing_policy_version": "a2f-routing",
                        "execution_profile_id": "a2f-execution",
                        "execution_profile_digest": "b" * 64,
                        "capability_policy_version": "a2f-capability",
                        "capability_policy_digest": "c" * 64,
                    },
                }
                for name in ("codex-operator", "codex-hf1q-step")
            },
        },
    )


def _v3_execution_binding():
    return {
        "eligible_quota_classes": ["codex-hf1q-step"],
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "effort": "xhigh",
        "cost_class": "small",
        "base_sha": "a" * 40,
        "routing_policy_version": "a2f-routing",
        "execution_profile_id": "a2f-execution",
        "execution_profile_digest": "b" * 64,
        "capability_policy_version": "a2f-capability",
        "capability_policy_digest": "c" * 64,
        "operator_eligible_quota_classes": ["codex-operator"],
        "operator_provider": "codex",
        "operator_model": "gpt-5.6-sol",
        "operator_effort": "xhigh",
        "operator_cost_class": "small",
        "operator_routing_policy_version": "a2f-routing",
        "operator_execution_profile_id": "a2f-execution",
        "operator_execution_profile_digest": "b" * 64,
        "operator_capability_policy_version": "a2f-capability",
        "operator_capability_policy_digest": "c" * 64,
        "operator_harness_binary_digest": "d" * 64,
        "operator_harness_version": "a2f-harness",
        "operator_harness_armed": False,
        "host_execution_binding_version": (
            "mastermind.host_execution_binding/v3"
        ),
        "work_placement_union": [
            {"provider_realm": "codex", "quota_class": "codex-hf1q-step"},
        ],
    }


def _v2_armed_binding():
    """COPY of the v3 fixture minus v3-only fields, armed for the fixture."""

    binding = _v3_execution_binding()
    binding.pop("work_placement_union", None)
    binding.pop("host_execution_binding_version", None)
    binding["operator_harness_armed"] = True
    return binding


def _orchestration_profile(dispatch: OrchestrationDispatchOutcome):
    attempt = dispatch.attempt
    return RequestedExecutionProfile(
        worker_id=str(attempt.worker_id),
        provider="codex",
        requested_model="fixture-model",
        harness_kind="fixture",
        harness_binary_digest="a" * 64,
        harness_version="1",
        workspace=WorkspaceIdentity("/tmp/work", "b" * 40, 1, 2, 0, 0),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash=str(attempt.authority_policy_hash),
        auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
    )


def _orchestration_attestation(profile: RequestedExecutionProfile):
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


def _complete_ohf_role(
    runtime: Runtime,
    dispatch: OrchestrationDispatchOutcome,
    role_result: dict[str, Any],
    *,
    identity_seed: int,
    before_settlement=None,
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
    start = OperationId(f"ohf-op:a2f-{identity_seed}-start")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        operation_id=start,
    )
    assert harness.commit_provider_dispatch(
        attempt_id=sealed.attempt_id, operation_id=start,
        operation_kind="start_session", fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    ) is True
    process = ProcessIdentityObservation(
        identity_seed, identity_seed, f"start-{identity_seed}", "boot-a2f"
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
            "path": f"/tmp/a2f-codex-home-{identity_seed}",
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
    turn_op = OperationId(f"ohf-op:a2f-{identity_seed}-turn")
    turn = harness.reserve_turn(
        epoch=epoch,
        generation=generation,
        operation_id=turn_op,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    assert harness.commit_provider_dispatch(
        attempt_id=sealed.attempt_id, operation_id=turn_op,
        operation_kind="begin_turn", fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    ) is True
    native_turn = f"NATIVE-{identity_seed}"
    harness.acknowledge_turn(
        turn=turn,
        operation_id=turn_op,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        observation=TurnStartObservation(native_turn, True),
    )
    if before_settlement is not None:
        before_settlement()
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


# ---------------------------------------------------------------------------
# finite-control fixture helpers (finite_arm pointers)
# ---------------------------------------------------------------------------


def _finite_root(runtime: Runtime, intent_id: str, **intent_overrides):
    envelope = _v2_intent(intent_id=intent_id, **intent_overrides)
    receipt = submit_intent(
        runtime, envelope, execution_binding=_v2_armed_binding()
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    return envelope, root


def _bound_definition(
    root,
    envelope,
    *,
    cap: int = 340,
    attestation: str = ATTESTATION_A,
    expires_at_ms: int | None = None,
    runtime: Runtime | None = None,
    overrides: dict | None = None,
) -> dict:
    now = runtime.store.now_ms() if runtime is not None else 0
    value = {
        "schema_version": executive_runtime.FINITE_CONTROL_CONTEXT_SCHEMA,
        "mode": "manual_finite",
        "phase": "admission_only",
        "intent_id": envelope["intent_id"],
        "intent_fingerprint": intent_fingerprint(validate_intent(envelope)),
        "config_snapshot_sha256": TEST_CONFIG_PIN,
        "source_release_sha256": TEST_SOURCE_RELEASE_PIN,
        "authority_policy_sha256": ExecutiveAuthorityPolicy.load().sha256,
        "coo_policy_sha256": CooCyclePolicy.load().policy_sha256,
        "binding_digest_sha256": TEST_BINDING_PIN,
        "host_binding_digest_sha256": finite_host_binding_digest(root.constraints),
        "control_attestation_digest": attestation,
    }
    if overrides:
        value.update(overrides)
    bound = {
        "phase": "bound",
        "root_job_id": root.job_id,
        "max_total_attempts": cap,
        "expires_at_ms": (
            int(expires_at_ms) if expires_at_ms is not None else now + 3_600_000
        ),
    }
    value.update(bound)
    return value


def _precomputed_admission_definition(envelope, **kwargs) -> dict:
    """Admission definition whose host pin is derived before creation.

    ``_normalise_constraints`` is idempotent over the armed binding slice,
    so the digest of the pre-computed constraints equals the digest of the
    constraints the strict-v2 create path will persist (verified against a
    real persisted root on this baseline).
    """

    constraints = executive_runtime._normalise_constraints(_v2_armed_binding())
    value = {
        "schema_version": executive_runtime.FINITE_CONTROL_CONTEXT_SCHEMA,
        "mode": "manual_finite",
        "phase": "admission_only",
        "intent_id": envelope["intent_id"],
        "intent_fingerprint": intent_fingerprint(validate_intent(envelope)),
        "config_snapshot_sha256": TEST_CONFIG_PIN,
        "source_release_sha256": TEST_SOURCE_RELEASE_PIN,
        "authority_policy_sha256": ExecutiveAuthorityPolicy.load().sha256,
        "coo_policy_sha256": CooCyclePolicy.load().policy_sha256,
        "binding_digest_sha256": TEST_BINDING_PIN,
        "host_binding_digest_sha256": finite_host_binding_digest(constraints),
        "control_attestation_digest": ATTESTATION_A,
    }
    value.update(kwargs)
    return value


def _issue(definition: dict) -> FiniteControlContext:
    return executive_runtime._issue_finite_control_context(
        definition,
        _producer_capability=(
            executive_runtime._FINITE_CONTROL_COMPOSITION_PRODUCER
        ),
    )


def _arm(runtime: Runtime, context: FiniteControlContext):
    return runtime.jobs.arm_finite_cycle(
        context.definition["root_job_id"], owner_issued_policy=context
    )


# ---------------------------------------------------------------------------
# armed-store and cycle-state builders
# ---------------------------------------------------------------------------


def _plan_steps(count: int, *, review_required: bool = False):
    return [
        {
            "ordinal": ordinal,
            "step_id": f"step-{ordinal}",
            "objective": f"A2-FRESH inert step {ordinal}.",
            "business_impact": "routine",
            "review_required": review_required,
            "requested_authorities": ["READ"],
            "allowed_write_paths": [],
            "validation_ids": [],
            "attempt_limit": 2,
            "cost_class": "small",
        }
        for ordinal in range(count)
    ]


class _CycleState:
    """Handles of one armed cycle driven to a named state."""

    def __init__(self, runtime, envelope, root, definition, context, arm_event,
                 clock, planner, planner_dispatch, plan_body, work_jobs):
        self.runtime = runtime
        self.envelope = envelope
        self.root = root
        self.definition = definition
        self.context = context
        self.arm_event = arm_event
        self.clock = clock
        self.planner = planner
        self.planner_dispatch = planner_dispatch
        self.plan_body = plan_body
        self.work_jobs = work_jobs

    def work(self, index: int):
        return self.work_jobs[index]

    def dispatch_command(self, job_id: str, attempt_number: int) -> str:
        return (
            f"coo-cycle:{self.root.job_id}:dispatch:{job_id}:"
            f"attempt:{attempt_number}"
        )


def _drive_to_admitted(
    base: Path,
    clock: MutableClock,
    *,
    steps: int,
    review_required: bool = False,
    cap: int = 8,
    ttl_seconds: int = 3_600,
    intent_id: str = "CEO-A2FRESH-001",
    finite: bool = True,
    **intent_overrides,
) -> _CycleState:
    base.mkdir(parents=True, exist_ok=True)
    runtime = Runtime.at(base, clock=clock)
    _register(runtime, "worker-a")
    _register(runtime, "worker-b")
    if steps > 1:
        # Two material steps reserve 19 children (>16); the multistep cases
        # exercise routine work and, where needed, one independent review.
        intent_overrides.setdefault("business_impact", "routine")
    envelope, root = _finite_root(runtime, intent_id, **intent_overrides)
    definition = context = arm_event = None
    if finite:
        definition = _bound_definition(
            root,
            envelope,
            runtime=runtime,
            cap=cap,
            expires_at_ms=clock.value + ttl_seconds * 1_000,
        )
        context = _issue(definition)
        runtime.store.bind_finite_control_context(context)
        arm_event = _arm(runtime, context)
    planner = runtime.jobs.create_cycle_planner(
        root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0"
    )
    planner_dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="worker-a",
    )
    assert isinstance(planner_dispatch, OrchestrationDispatchOutcome)
    plan_body = {
        "schema_version": "mastermind.execution_plan/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner_dispatch.attempt.attempt_id,
        "steps": _plan_steps(steps, review_required=review_required),
    }
    if steps > 1 and review_required:
        for step in plan_body["steps"][1:]:
            step["review_required"] = False
    _complete_ohf_role(
        runtime, planner_dispatch, plan_body, identity_seed=9101
    )
    admitted = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=(
            f"coo-cycle:{root.job_id}:admit-plan:"
            f"{planner_dispatch.attempt.attempt_id}"
        ),
    )
    work_jobs = [
        job for job in admitted if job.orchestration_role == "work"
    ]
    assert len(work_jobs) == steps
    return _CycleState(
        runtime,
        envelope,
        root,
        definition,
        context,
        arm_event,
        clock,
        planner,
        planner_dispatch,
        plan_body,
        work_jobs,
    )


def _work_result_body(root_id, plan_attempt_id, plan_digest_value, step_id):
    return {
        "schema_version": "mastermind.work_result/v1",
        "root_job_id": root_id,
        "plan_attempt_id": plan_attempt_id,
        "plan_digest": plan_digest_value,
        "plan_step_id": step_id,
        "repair_round": 0,
        "artifacts": [],
        "evidence_digests": [],
    }


def _complete_work(state: _CycleState, index: int) -> None:
    work = state.work(index)
    dispatch = state.runtime.attempts.dispatch_cycle_job(
        work.job_id,
        command_id=state.dispatch_command(work.job_id, 1),
        worker_id="worker-a",
    )
    assert isinstance(dispatch, OrchestrationDispatchOutcome)
    body = _work_result_body(
        state.root.job_id,
        state.planner_dispatch.attempt.attempt_id,
        result_digest(state.plan_body),
        str(work.plan_step_id),
    )
    _complete_ohf_role(
        state.runtime, dispatch, body, identity_seed=9200 + index
    )


def _sealed_result_digest(runtime: Runtime, job_id: str) -> str:
    with runtime.store.read() as connection:
        row = connection.execute(
            """
            SELECT payload_json FROM events
            WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED' AND job_id=?
            """,
            (job_id,),
        ).fetchone()
    assert row is not None
    return str(json.loads(str(row[0]))["role_result_digest"])


def _complete_review(
    state: _CycleState, index: int, *, verdict: str, identity_seed: int
):
    """Create, dispatch, and complete one review; return (review, seal)."""

    runtime = state.runtime
    work = state.work(index)
    review = runtime.jobs.create_cycle_review(
        state.root.job_id,
        work.job_id,
        command_id=(
            f"coo-cycle:{state.root.job_id}:create-review:{work.job_id}:1"
        ),
    )
    dispatch = runtime.attempts.dispatch_cycle_job(
        review.job_id,
        command_id=state.dispatch_command(review.job_id, 1),
        worker_id="worker-b",
    )
    assert isinstance(dispatch, OrchestrationDispatchOutcome)
    work_job = runtime.jobs.get_job(work.job_id)
    assert work_job is not None and work_job.plan_digest is not None
    body = {
        "schema_version": "mastermind.review_result/v1",
        "root_job_id": state.root.job_id,
        "plan_attempt_id": state.planner_dispatch.attempt.attempt_id,
        "plan_digest": str(work_job.plan_digest),
        "plan_step_id": str(work.plan_step_id),
        "reviewed_job_id": work.job_id,
        "reviewed_attempt_id": _current_attempt_id(runtime, work.job_id),
        "reviewed_result_digest": _sealed_result_digest(runtime, work.job_id),
        "repair_round": 0,
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
    seal, _terminal = _complete_ohf_role(
        runtime, dispatch, body, identity_seed=identity_seed
    )
    return review, seal


def _current_attempt_id(runtime: Runtime, job_id: str) -> str:
    with runtime.store.read() as connection:
        row = connection.execute(
            "SELECT current_attempt_id FROM jobs WHERE job_id=?", (job_id,)
        ).fetchone()
    assert row is not None and row[0] is not None
    return str(row[0])


def _tx9_detach(runtime: Runtime, attempt, suffix: str) -> None:
    """COPY of the phase1fc TX9 restore-detach fixture (direct SQL)."""

    with runtime.store.transaction() as connection:
        connection.execute(
            """
            UPDATE attempts
            SET execution_mode='OPERATOR_HARNESS',
                requested_execution_profile_json='{}',
                requested_execution_profile_digest=?
            WHERE attempt_id=?
            """,
            ("f" * 64, attempt.attempt_id),
        )
        connection.execute(
            """
            INSERT INTO harness_session_epochs(
              session_epoch_id,attempt_id,worker_id,epoch_number,
              provider_session_id,state,created_at_ms
            ) VALUES(?,?,?,?,?,'CURRENT',1)
            """,
            (
                f"EPOCH-{suffix}",
                attempt.attempt_id,
                attempt.worker_id,
                1,
                f"SESSION-{suffix}",
            ),
        )
        connection.execute(
            """
            INSERT INTO process_generations(
              process_generation_id,session_epoch_id,worker_id,
              provider_session_id,generation_number,started_at_ms,
              executive_writer_held,provider_writer_state,created_at_ms
            ) VALUES(?,?,?,?,?,1,1,'HELD',1)
            """,
            (
                f"GEN-{suffix}",
                f"EPOCH-{suffix}",
                attempt.worker_id,
                f"SESSION-{suffix}",
                1,
            ),
        )
    assert runtime.operator_harness.invalidate_after_restore() == 1


def _tampered_arm_copy(base: Path, name: str, mutate) -> Path:
    """Copied database with the arm payload mutated behind the immutability
    triggers, restoring their exact stored DDL (known fixture mechanism)."""

    target = base.parent / f"tampered-{name}"
    shutil.copytree(base, target)
    database = target / "data" / "control_plane" / "executive.sqlite3"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        triggers = connection.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='trigger' AND tbl_name='events'"
        ).fetchall()
        for row in triggers:
            connection.execute(f"DROP TRIGGER {row['name']}")
        mutate(connection)
        for row in triggers:
            connection.execute(str(row["sql"]))
        connection.commit()
    finally:
        connection.close()
    return target


# ---------------------------------------------------------------------------
# 1. root admission under an admission-only finite context
# ---------------------------------------------------------------------------


def test_admission_only_exact_strict_v2_intent_admits_once_with_zero_extra_writes(
    tmp_path,
):
    envelope = _v2_intent(intent_id="CEO-A2FRESH-ADMIT-001")
    definition = _precomputed_admission_definition(envelope)
    context = _issue(definition)
    runtime = Runtime.at(tmp_path, clock=MutableClock(1_800_000_000_000))
    runtime.store.bind_finite_control_context(context)
    _register(runtime, "worker-a")

    receipt = submit_intent(
        runtime, envelope, execution_binding=_v2_armed_binding()
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    assert root.orchestration_role == "aggregation"
    assert root.orchestration_provenance is not None
    assert root.orchestration_provenance["source_id"] == envelope["intent_id"]
    assert (
        root.orchestration_provenance["source_digest"]
        == definition["intent_fingerprint"]
    )
    assert (
        finite_host_binding_digest(root.constraints)
        == definition["host_binding_digest_sha256"]
    )
    with runtime.store.read() as connection:
        job_created = int(
            connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='JOB_CREATED'"
            ).fetchone()[0]
        )
    assert job_created == 1

    before = _full_snapshot(runtime)
    replay = submit_intent(
        runtime, envelope, execution_binding=_v2_armed_binding()
    )
    assert replay["job_id"] == receipt["job_id"]
    assert _full_snapshot(runtime) == before


def test_admission_only_refuses_foreign_drifted_and_malformed_roots(tmp_path):
    envelope = _v2_intent(intent_id="CEO-A2FRESH-ADMIT-002")

    def fresh(case: str, *, pin_overrides=None):
        definition = _precomputed_admission_definition(
            envelope, **(pin_overrides or {})
        )
        runtime = Runtime.at(
            tmp_path / case, clock=MutableClock(1_800_000_000_000)
        )
        runtime.store.bind_finite_control_context(_issue(definition))
        return runtime

    # (a) a different strict-v2 intent id is foreign to the pinned admission
    runtime = fresh("foreign")
    before = _full_snapshot(runtime)
    with pytest.raises(CeoIntentError, match="admission"):
        submit_intent(
            runtime,
            _v2_intent(intent_id="CEO-A2FRESH-ADMIT-OTHER"),
            execution_binding=_v2_armed_binding(),
        )
    assert _full_snapshot(runtime) == before

    # (b) the pinned intent id with a drifted body (different fingerprint)
    runtime = fresh("fingerprint")
    before = _full_snapshot(runtime)
    with pytest.raises(CeoIntentError, match="admission"):
        submit_intent(
            runtime,
            _v2_intent(
                intent_id="CEO-A2FRESH-ADMIT-002",
                objective="A different objective entirely.",
            ),
            execution_binding=_v2_armed_binding(),
        )
    assert _full_snapshot(runtime) == before

    # (c) a v1 intent (role-null generic Job, no execution binding) is not
    # the pinned strict-v2 aggregation root
    runtime = fresh("v1")
    v1 = _v2_intent(intent_id="CEO-A2FRESH-ADMIT-002")
    v1["schema"] = INTENT_SCHEMA
    v1.pop("intent_kind")
    v1.pop("business_impact")
    before = _full_snapshot(runtime)
    with pytest.raises(CeoIntentError, match="admission"):
        submit_intent(runtime, v1)
    assert _full_snapshot(runtime) == before

    # (d) a generic role-null root is not the pinned intent's root
    runtime = fresh("generic")
    before = _full_snapshot(runtime)
    with pytest.raises(StateConflict, match="admission"):
        runtime.jobs.create_job("generic root under admission context")
    assert _full_snapshot(runtime) == before

    # (e) the pinned intent with a drifted host execution binding
    runtime = fresh("binding")
    drifted_binding = _v2_armed_binding()
    drifted_binding["operator_harness_version"] = "drifted-harness"
    before = _full_snapshot(runtime)
    with pytest.raises(CeoIntentError, match="admission"):
        submit_intent(
            runtime, envelope, execution_binding=drifted_binding
        )
    assert _full_snapshot(runtime) == before


def test_bound_context_admits_no_fresh_root_of_any_kind(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    state = _drive_to_admitted(
        tmp_path, clock, steps=1, intent_id="CEO-A2FRESH-BOUND-ROOT"
    )
    runtime = state.runtime

    before = _full_snapshot(runtime)
    with pytest.raises(
        CeoIntentError, match="finite admission refuses"
    ):
        submit_intent(
            runtime,
            _v2_intent(intent_id="CEO-A2FRESH-BOUND-SECOND"),
            execution_binding=_v2_armed_binding(),
        )
    assert _full_snapshot(runtime) == before

    before = _full_snapshot(runtime)
    with pytest.raises(
        StateConflict, match="finite admission refuses"
    ):
        runtime.jobs.create_job("legacy root under bound context")
    assert _full_snapshot(runtime) == before


# ---------------------------------------------------------------------------
# 2. bound context without an arm, and drifted contexts
# ---------------------------------------------------------------------------


def test_unarmed_bound_context_refuses_every_fresh_family(tmp_path):
    clock = MutableClock(1_800_000_000_000)

    # (a) no arm yet: even the reserved planner refuses
    runtime = Runtime.at(tmp_path / "noarm", clock=clock)
    _register(runtime, "worker-a")
    envelope, root = _finite_root(runtime, "CEO-A2FRESH-UNARMED-001")
    definition = _bound_definition(
        root,
        envelope,
        runtime=runtime,
        cap=8,
        expires_at_ms=clock.value + 3_600_000,
    )
    runtime.store.bind_finite_control_context(_issue(definition))
    before = _full_snapshot(runtime)
    with pytest.raises(StateConflict, match="no durable arm"):
        runtime.jobs.create_cycle_planner(
            root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0"
        )
    assert _full_snapshot(runtime) == before

    # (b) planner created before the bind: dispatch/block now refuse
    runtime = Runtime.at(tmp_path / "latebind", clock=clock)
    _register(runtime, "worker-a")
    envelope, root = _finite_root(runtime, "CEO-A2FRESH-UNARMED-002")
    planner = runtime.jobs.create_cycle_planner(
        root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0"
    )
    definition = _bound_definition(
        root,
        envelope,
        runtime=runtime,
        cap=8,
        expires_at_ms=clock.value + 3_600_000,
    )
    runtime.store.bind_finite_control_context(_issue(definition))
    before = _full_snapshot(runtime)
    with pytest.raises(StateConflict, match="no durable arm"):
        runtime.attempts.dispatch_cycle_job(
            planner.job_id,
            command_id=(
                f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"
            ),
            worker_id="worker-a",
        )
    assert _full_snapshot(runtime) == before
    with pytest.raises(StateConflict, match="no durable arm"):
        runtime.jobs.block_cycle(
            root.job_id,
            selected_job_id=planner.job_id,
            reason="state_conflict",
            command_id=(
                f"coo-cycle:{root.job_id}:block:state_conflict:{planner.job_id}"
            ),
        )
    assert _full_snapshot(runtime) == before


def test_drifted_context_pins_refuse_fresh_work(tmp_path, monkeypatch):
    clock = MutableClock(1_800_000_000_000)

    # handoff-ready tree armed under the valid definition
    state = _drive_to_admitted(
        tmp_path / "armed",
        clock,
        steps=1,
        review_required=True,
        intent_id="CEO-A2FRESH-DRIFT-001",
    )
    _complete_work(state, 0)
    _complete_review(state, 0, verdict="approve", identity_seed=9301)
    handoff_command = (
        f"coo-cycle:{state.root.job_id}:aggregation-handoff:1"
    )

    def drifted_store(case: str, **overrides):
        target = tmp_path / f"drift-{case}"
        shutil.copytree(tmp_path / "armed", target)
        runtime = Runtime.at(target, clock=clock)
        definition = dict(state.definition)
        definition.update(overrides)
        runtime.store.bind_finite_control_context(_issue(definition))
        return runtime

    def refuse_handoff(runtime, fragment):
        before = _full_snapshot(runtime)
        with pytest.raises(StateConflict, match=fragment):
            runtime.jobs.create_cycle_handoff(
                state.root.job_id, command_id=handoff_command
            )
        assert _full_snapshot(runtime) == before

    # (a) drifted cap pin
    refuse_handoff(drifted_store("cap", max_total_attempts=7), "no longer matches")
    # (b) drifted host binding pin
    refuse_handoff(
        drifted_store("host", host_binding_digest_sha256=DRIFT_PIN),
        "no longer matches",
    )
    # (c) drifted intent fingerprint pin
    refuse_handoff(
        drifted_store("fingerprint", intent_fingerprint=DRIFT_PIN),
        "no longer matches",
    )
    # A fresh qualified observation is not an immutable stable-arm pin.
    observed = drifted_store("attestation", control_attestation_digest=DRIFT_PIN)
    handed_off = observed.jobs.create_cycle_handoff(
        state.root.job_id, command_id=handoff_command
    )
    assert handed_off["root_job_id"] == state.root.job_id

    # (e) live authority policy drifted from the arm pin (synthetic loader)
    class _SyntheticAuthorityPolicy:
        sha256 = DRIFT_PIN

        @staticmethod
        def load():
            return _SyntheticAuthorityPolicy()

    monkeypatch.setattr(
        executive_runtime,
        "ExecutiveAuthorityPolicy",
        _SyntheticAuthorityPolicy,
    )
    refuse_handoff(drifted_store("authority"), "authority policy pin differs")
    monkeypatch.undo()

    # (f) live COO policy drifted from the arm pin (synthetic loader)
    class _SyntheticCooPolicy:
        policy_sha256 = DRIFT_PIN

        @staticmethod
        def load():
            return _SyntheticCooPolicy()

    monkeypatch.setattr(
        executive_runtime,
        "CooCyclePolicy",
        _SyntheticCooPolicy,
    )
    refuse_handoff(drifted_store("coo"), "COO plan admission identity/digest is invalid")
    monkeypatch.undo()


# ---------------------------------------------------------------------------
# 3. reopened unbound stores, malformed stored arms, legacy behaviour
# ---------------------------------------------------------------------------


def test_reopened_unbound_store_refuses_armed_root_but_keeps_legacy(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    state = _drive_to_admitted(
        tmp_path / "armed",
        clock,
        steps=2,
        intent_id="CEO-A2FRESH-REOPEN-001",
    )
    work = state.work(1)

    # a fresh process on the same database has no bound context
    reopened = Runtime.at(tmp_path / "armed", clock=clock)
    before = _full_snapshot(reopened)
    with pytest.raises(StateConflict, match="without its bound context"):
        reopened.attempts.dispatch_cycle_job(
            work.job_id,
            command_id=state.dispatch_command(work.job_id, 1),
            worker_id="worker-a",
        )
    assert _full_snapshot(reopened) == before
    planner_replay = reopened.jobs.create_cycle_planner(
        state.root.job_id,
        command_id=f"coo-cycle:{state.root.job_id}:create-planner:0",
    )
    assert planner_replay.job_id == state.planner.job_id
    assert _full_snapshot(reopened) == before

    # the pure historical read stays available after reopen
    status = reopened.jobs.finite_cycle_status(state.root.job_id)
    assert status is not None
    assert status["spent"] >= 1
    assert status["expired"] is False

    # legacy trees without any arm keep their untouched behaviour
    legacy_root = reopened.jobs.create_job("legacy root on reopened store")
    lease = reopened.broker.claim(legacy_root.job_id, worker_id="worker-a")
    assert lease is not None
    assert lease.attempt.job_id == legacy_root.job_id

    # the dedicated bound store also refuses a foreign legacy root
    with pytest.raises(
        StateConflict, match="finite admission refuses"
    ):
        state.runtime.jobs.create_job("foreign legacy root on bound store")


def test_malformed_stored_arm_refuses_instead_of_reading_unarmed(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    state = _drive_to_admitted(
        tmp_path / "armed",
        clock,
        steps=2,
        intent_id="CEO-A2FRESH-TAMPER-001",
    )
    work = state.work(1)

    def mutate(connection):
        row = connection.execute(
            "SELECT payload_json FROM events WHERE event_type=? AND aggregate_id=?",
            (
                executive_runtime.COO_FINITE_DRIVE_ARMED_EVENT_TYPE,
                state.root.job_id,
            ),
        ).fetchone()
        payload = json.loads(str(row[0]))
        payload["max_total_attempts"] = payload["max_total_attempts"] + 1
        connection.execute(
            "UPDATE events SET payload_json=? WHERE event_type=? AND aggregate_id=?",
            (
                _canonical(payload),
                executive_runtime.COO_FINITE_DRIVE_ARMED_EVENT_TYPE,
                state.root.job_id,
            ),
        )

    target = _tampered_arm_copy(tmp_path / "armed", "cap", mutate)
    runtime = Runtime.at(target, clock=clock)
    runtime.store.bind_finite_control_context(state.context)
    before = _full_snapshot(runtime)
    with pytest.raises(StateConflict, match="COO_FINITE_DRIVE_ARMED"):
        runtime.attempts.dispatch_cycle_job(
            work.job_id,
            command_id=state.dispatch_command(work.job_id, 1),
            worker_id="worker-a",
        )
    assert _full_snapshot(runtime) == before
    with pytest.raises(StateConflict, match="COO_FINITE_DRIVE_ARMED"):
        runtime.jobs.finite_cycle_status(state.root.job_id)


# ---------------------------------------------------------------------------
# 4. armed positive cycle and cutoff families
# ---------------------------------------------------------------------------


def test_armed_cycle_positive_through_review_and_handoff(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    state = _drive_to_admitted(
        tmp_path,
        clock,
        steps=1,
        review_required=True,
        intent_id="CEO-A2FRESH-HAPPY-001",
    )
    _complete_work(state, 0)
    review, _seal = _complete_review(
        state, 0, verdict="approve", identity_seed=9401
    )

    handoff = state.runtime.jobs.create_cycle_handoff(
        state.root.job_id,
        command_id=f"coo-cycle:{state.root.job_id}:aggregation-handoff:1",
    )
    assert handoff["revisions"][0]["current_job_id"] == state.work(0).job_id
    assert (
        handoff["revisions"][0]["qualifying_review_job_id"] == review.job_id
    )

    status = state.runtime.jobs.finite_cycle_status(state.root.job_id)
    assert status is not None
    assert status["spent"] == 3
    assert status["remaining"] == 8 - 3
    assert status["expired"] is False
    assert status["exhausted"] is False


def test_expired_window_refuses_each_fresh_family_with_zero_writes(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    state = _drive_to_admitted(
        tmp_path,
        clock,
        steps=3,
        ttl_seconds=120,
        intent_id="CEO-A2FRESH-EXPIRE-001",
    )
    _complete_work(state, 0)
    # one detached TX9 attempt waits for a retry decision, one step stays QUEUED
    work2 = state.work(2)
    tx9_dispatch = state.runtime.attempts.dispatch_cycle_job(
        work2.job_id,
        command_id=state.dispatch_command(work2.job_id, 1),
        worker_id="worker-a",
    )
    assert isinstance(tx9_dispatch, OrchestrationDispatchOutcome)
    _tx9_detach(state.runtime, tx9_dispatch.attempt, "A2F-EXPIRE-TX9")
    projection = state.runtime.jobs.project_retry_safety(
        work2.job_id, expected_attempt_id=tx9_dispatch.attempt.attempt_id
    )
    work1 = state.work(1)
    admit_command = (
        f"coo-cycle:{state.root.job_id}:admit-plan:"
        f"{state.planner_dispatch.attempt.attempt_id}"
    )

    clock.advance(seconds=121)

    runtime = state.runtime
    before = _full_snapshot(runtime)

    # claim family
    with pytest.raises(StateConflict, match="expired"):
        runtime.attempts.dispatch_cycle_job(
            work1.job_id,
            command_id=state.dispatch_command(work1.job_id, 1),
            worker_id="worker-a",
        )
    assert _full_snapshot(runtime) == before

    # block family
    with pytest.raises(StateConflict, match="expired"):
        runtime.jobs.block_cycle(
            state.root.job_id,
            selected_job_id=work1.job_id,
            reason="state_conflict",
            command_id=(
                f"coo-cycle:{state.root.job_id}:block:state_conflict:"
                f"{work1.job_id}"
            ),
        )
    assert _full_snapshot(runtime) == before

    # retry-decision family (SAFE_REQUEUE material is genuinely available)
    with pytest.raises(StateConflict, match="expired"):
        runtime.jobs.commit_coo_retry_decision(
            state.root.job_id,
            selected_job_id=work2.job_id,
            expectation=projection,
        )
    assert _full_snapshot(runtime) == before

    # the pre-existing orchestration-role refusal for direct requeue stays
    with pytest.raises(StateConflict, match="atomic COO retry decision"):
        runtime.jobs.requeue_job(work2.job_id)
    assert _full_snapshot(runtime) == before

    # repeated refusals write no diagnostics
    with pytest.raises(StateConflict, match="expired"):
        runtime.attempts.dispatch_cycle_job(
            work1.job_id,
            command_id=state.dispatch_command(work1.job_id, 1),
            worker_id="worker-a",
        )
    assert _full_snapshot(runtime) == before

    # read-only status and the exact admission replay stay available
    status = runtime.jobs.finite_cycle_status(state.root.job_id)
    assert status is not None and status["expired"] is True
    replay = runtime.jobs.admit_cycle_plan(
        state.root.job_id, command_id=admit_command
    )
    assert [job.job_id for job in replay] == [
        job.job_id for job in state.work_jobs
    ]
    assert _full_snapshot(runtime) == before


def test_expired_window_refuses_repair_creation(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    state = _drive_to_admitted(
        tmp_path,
        clock,
        steps=1,
        review_required=True,
        ttl_seconds=120,
        intent_id="CEO-A2FRESH-EXPIRE-REPAIR-001",
    )
    _complete_work(state, 0)
    review, seal = _complete_review(
        state, 0, verdict="reject", identity_seed=9451
    )
    work = state.work(0)
    repair_command = (
        f"coo-cycle:{state.root.job_id}:create-repair:{work.job_id}:"
        f"{review.job_id}:{seal['role_result_digest']}:1"
    )

    clock.advance(seconds=121)

    runtime = state.runtime
    before = _full_snapshot(runtime)
    with pytest.raises(StateConflict, match="expired"):
        runtime.jobs.create_cycle_repair(
            state.root.job_id,
            work.job_id,
            review.job_id,
            command_id=repair_command,
        )
    assert _full_snapshot(runtime) == before
    status = runtime.jobs.finite_cycle_status(state.root.job_id)
    assert status is not None and status["expired"] is True


def test_exhausted_cap_allows_final_slot_then_refuses_across_stores(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    state = _drive_to_admitted(
        tmp_path,
        clock,
        steps=2,
        cap=2,
        intent_id="CEO-A2FRESH-CAP-001",
    )
    work0 = state.work(0)
    work1 = state.work(1)

    # planner attempt (1) is spent; the final slot (2) still admits
    final = state.runtime.attempts.dispatch_cycle_job(
        work0.job_id,
        command_id=state.dispatch_command(work0.job_id, 1),
        worker_id="worker-a",
    )
    assert isinstance(final, OrchestrationDispatchOutcome)

    status = state.runtime.jobs.finite_cycle_status(state.root.job_id)
    assert status is not None
    assert status["spent"] == 2
    assert status["exhausted"] is True

    before = _full_snapshot(state.runtime)
    with pytest.raises(StateConflict, match="attempt cap"):
        state.runtime.attempts.dispatch_cycle_job(
            work1.job_id,
            command_id=state.dispatch_command(work1.job_id, 1),
            worker_id="worker-a",
        )
    assert _full_snapshot(state.runtime) == before

    # a second process bound to the same context sees the same history
    second = Runtime.at(tmp_path, clock=clock)
    second.store.bind_finite_control_context(state.context)
    before_second = _full_snapshot(second)
    with pytest.raises(StateConflict, match="attempt cap"):
        second.attempts.dispatch_cycle_job(
            work1.job_id,
            command_id=state.dispatch_command(work1.job_id, 1),
            worker_id="worker-a",
        )
    assert _full_snapshot(second) == before_second

    # exact dispatch replay of the claimed attempt still resolves
    replay = second.attempts.dispatch_cycle_job(
        work0.job_id,
        command_id=state.dispatch_command(work0.job_id, 1),
        worker_id="worker-a",
    )
    assert isinstance(replay, OrchestrationDispatchOutcome)
    assert replay.attempt.attempt_id == final.attempt.attempt_id
    assert _full_snapshot(second) == before_second


def test_inflight_settlement_is_not_blocked_after_cutoff(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    state = _drive_to_admitted(
        tmp_path,
        clock,
        steps=2,
        ttl_seconds=20,
        intent_id="CEO-A2FRESH-SETTLE-001",
    )
    work0 = state.work(0)
    dispatch = state.runtime.attempts.dispatch_cycle_job(
        work0.job_id,
        command_id=state.dispatch_command(work0.job_id, 1),
        worker_id="worker-a",
    )
    assert isinstance(dispatch, OrchestrationDispatchOutcome)

    # Issue start and turn before finite cutoff; settle within its 60s lease.
    body = _work_result_body(
        state.root.job_id,
        state.planner_dispatch.attempt.attempt_id,
        result_digest(state.plan_body),
        str(work0.plan_step_id),
    )
    _complete_ohf_role(
        state.runtime, dispatch, body, identity_seed=9501,
        before_settlement=lambda: clock.advance(seconds=21),
    )
    settled = state.runtime.jobs.get_job(work0.job_id)
    assert settled is not None
    assert settled.status is executive_runtime.JobStatus.COMPLETED

    # but the next fresh claim on the sibling step refuses
    work1 = state.work(1)
    with pytest.raises(StateConflict, match="expired"):
        state.runtime.attempts.dispatch_cycle_job(
            work1.job_id,
            command_id=state.dispatch_command(work1.job_id, 1),
            worker_id="worker-a",
        )


# ---------------------------------------------------------------------------
# 5. retry decisions, atomicity, and the clock boundary
# ---------------------------------------------------------------------------


def test_tx9_safe_requeue_under_arm_and_post_cutoff_refusal_with_replay(
    tmp_path,
):
    clock = MutableClock(1_800_000_000_000)
    state = _drive_to_admitted(
        tmp_path,
        clock,
        steps=2,
        ttl_seconds=120,
        intent_id="CEO-A2FRESH-TX9-001",
    )
    work0 = state.work(0)
    runtime = state.runtime

    # first detached attempt: committed inside the window
    first = runtime.attempts.dispatch_cycle_job(
        work0.job_id,
        command_id=state.dispatch_command(work0.job_id, 1),
        worker_id="worker-a",
    )
    assert isinstance(first, OrchestrationDispatchOutcome)
    _tx9_detach(runtime, first.attempt, "A2F-TX9-1")
    first_projection = runtime.jobs.project_retry_safety(
        work0.job_id, expected_attempt_id=first.attempt.attempt_id
    )
    committed = runtime.jobs.commit_coo_retry_decision(
        state.root.job_id,
        selected_job_id=work0.job_id,
        expectation=first_projection,
    )
    assert committed.action == "REQUEUED"
    assert committed.receipt["requeue_kind"] == "TX9_DETACHED"
    requeue_command = committed.command_id

    # Restore invalidation quarantines worker-a; a distinct eligible worker
    # owns the second canonical claim (do not bypass its quarantine).
    second = runtime.attempts.dispatch_cycle_job(
        work0.job_id,
        command_id=state.dispatch_command(work0.job_id, 2),
        worker_id="worker-b",
    )
    assert isinstance(second, OrchestrationDispatchOutcome)
    _tx9_detach(runtime, second.attempt, "A2F-TX9-2")
    second_projection = runtime.jobs.project_retry_safety(
        work0.job_id, expected_attempt_id=second.attempt.attempt_id
    )

    clock.advance(seconds=121)

    # the fresh retry decision on the second attempt refuses after cutoff
    before = _full_snapshot(runtime)
    with pytest.raises(StateConflict, match="expired"):
        runtime.jobs.commit_coo_retry_decision(
            state.root.job_id,
            selected_job_id=work0.job_id,
            expectation=second_projection,
        )
    assert _full_snapshot(runtime) == before

    # the committed first receipt replays after cutoff without new writes
    replay = runtime.jobs.requeue_job(work0.job_id, command_id=requeue_command)
    assert replay.event_id == committed.receipt["event_id"]
    assert _full_snapshot(runtime) == before
    replay_decision = runtime.jobs.commit_coo_retry_decision(
        state.root.job_id,
        selected_job_id=work0.job_id,
        expectation=first_projection,
    )
    assert replay_decision.action == "REQUEUED"
    assert _full_snapshot(runtime) == before


def test_guard_passing_mutation_rolls_back_atomically(tmp_path, monkeypatch):
    clock = MutableClock(1_800_000_000_000)
    state = _drive_to_admitted(
        tmp_path,
        clock,
        steps=2,
        intent_id="CEO-A2FRESH-ATOMIC-001",
    )
    runtime = state.runtime
    work1 = state.work(1)
    before = _full_snapshot(runtime)

    def failing_append(*args, **kwargs):
        raise RuntimeError("fixture crash inside the fresh mutation")

    monkeypatch.setattr(
        executive_runtime.RuntimeStore, "append_event", failing_append
    )
    try:
        with pytest.raises(RuntimeError, match="fixture crash"):
            runtime.attempts.dispatch_cycle_job(
                work1.job_id,
                command_id=state.dispatch_command(work1.job_id, 1),
                worker_id="worker-a",
            )
    finally:
        monkeypatch.undo()
    assert _full_snapshot(runtime) == before


def test_clock_is_sampled_inside_the_write_transaction(tmp_path, monkeypatch):
    clock = MutableClock(1_800_000_000_000)
    state = _drive_to_admitted(
        tmp_path,
        clock,
        steps=2,
        ttl_seconds=600,
        intent_id="CEO-A2FRESH-RACE-001",
    )
    work1 = state.work(1)
    runtime = state.runtime
    expiry = state.definition["expires_at_ms"]

    holder = sqlite3.connect(runtime.store.path, timeout=10)
    holder.execute("BEGIN IMMEDIATE")
    outcome: dict[str, Any] = {}

    def blocked_dispatch():
        try:
            outcome["lease"] = runtime.attempts.dispatch_cycle_job(
                work1.job_id,
                command_id=state.dispatch_command(work1.job_id, 1),
                worker_id="worker-a",
            )
        except Exception as error:  # noqa: BLE001 - captured for assertion
            outcome["error"] = error

    trying_transaction = threading.Event()
    original_transaction = runtime.store.transaction

    @contextlib.contextmanager
    def observed_transaction():
        # claim_job sampled its outer clock before reaching this owner.
        trying_transaction.set()
        with original_transaction() as connection:
            yield connection

    monkeypatch.setattr(runtime.store, "transaction", observed_transaction)
    thread = threading.Thread(target=blocked_dispatch)
    thread.start()
    assert trying_transaction.wait(timeout=10)
    # Our separate connection still owns BEGIN IMMEDIATE. No elapsed-time
    # guess decides whether the claimant's pre-transaction sample happened.
    clock.value = expiry + 5_000
    holder.commit()
    holder.close()
    thread.join(timeout=10)
    assert not thread.is_alive()

    assert "lease" not in outcome
    assert isinstance(outcome.get("error"), StateConflict)
    assert "expired" in str(outcome["error"])
    with runtime.store.read() as connection:
        created = int(
            connection.execute(
                "SELECT COUNT(*) FROM attempts WHERE job_id=?", (work1.job_id,)
            ).fetchone()[0]
        )
    assert created == 0


# ---------------------------------------------------------------------------
# 6. capacity carriers on finite-controlled source roots
# ---------------------------------------------------------------------------


def _c2_ready(
    base: Path,
    clock: MutableClock,
    *,
    finite: bool,
    intent_id: str,
):
    """Drive one genuine reviewed COO root to the aggregation handoff edge,
    optionally under a valid bound+armed finite context, then make the COO
    fixture workers ineligible and admit exactly one Codex READ candidate."""

    state = _drive_to_admitted(
        base,
        clock,
        steps=1,
        review_required=True,
        finite=finite,
        intent_id=intent_id,
        workstream="WS:A2FRESH_C2",
    )
    _complete_work(state, 0)
    _complete_review(state, 0, verdict="approve", identity_seed=9601)
    runtime = state.runtime
    root = state.root
    runtime.jobs.create_cycle_handoff(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:aggregation-handoff:1",
    )

    runtime.workers.set_worker_status("worker-a", status="OFFLINE")
    runtime.workers.set_worker_status("worker-b", status="OFFLINE")
    runtime.workers.register_worker(
        "c2-codex-read",
        provider="codex",
        account_label="c2-a2f-primary",
        worker_type="codex",
        capabilities=["read"],
        quota_classes={
            "codex-hf1q-step": {
                "provider": "codex",
                "model": "gpt-5.6-sol",
                "effort": "xhigh",
                "cost_class": "small",
                "capabilities": ["read"],
            }
        },
    )
    with runtime.store.read() as connection:
        source_revision = int(
            connection.execute(
                "SELECT version FROM jobs WHERE job_id=?", (root.job_id,)
            ).fetchone()[0]
        )
    return state, source_revision


def test_c2_carrier_refused_under_context_and_under_persisted_arm(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    state, source_revision = _c2_ready(
        tmp_path / "armed",
        clock,
        finite=True,
        intent_id="CEO-A2FRESH-C2-001",
    )
    runtime = state.runtime

    before = _full_snapshot(runtime)
    with pytest.raises(StateConflict, match="finite-controlled source root"):
        runtime.commit_initial_capacity_placement(
            state.root.job_id,
            expected_source_root_revision=source_revision,
        )
    assert _full_snapshot(runtime) == before

    # even a reopened process with no bound context sees the persisted arm
    reopened = Runtime.at(tmp_path / "armed", clock=clock)
    before_reopened = _full_snapshot(reopened)
    with pytest.raises(StateConflict, match="finite-controlled source root"):
        reopened.commit_initial_capacity_placement(
            state.root.job_id,
            expected_source_root_revision=source_revision,
        )
    assert _full_snapshot(reopened) == before_reopened

    # the historical finite status read is unaffected
    assert reopened.jobs.finite_cycle_status(state.root.job_id) is not None


def test_c2_uncontrolled_store_still_commits_and_replays(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    state, source_revision = _c2_ready(
        tmp_path,
        clock,
        finite=False,
        intent_id="CEO-A2FRESH-C2-PLAIN",
    )
    runtime = state.runtime

    outcome = runtime.commit_initial_capacity_placement(
        state.root.job_id,
        expected_source_root_revision=source_revision,
    )
    assert outcome.carrier_disposition == "created"
    assert outcome.fresh_attempt_lease is not None

    before = _full_snapshot(runtime)
    replay = runtime.commit_initial_capacity_placement(
        state.root.job_id,
        expected_source_root_revision=source_revision,
    )
    assert replay.carrier_job_id == outcome.carrier_job_id
    assert replay.fresh_attempt_lease is None
    assert _full_snapshot(runtime) == before


# ---------------------------------------------------------------------------
# 7. public facades cannot bypass the finite refusals
# ---------------------------------------------------------------------------


def test_public_facades_cannot_bypass_the_finite_refusal(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    state = _drive_to_admitted(
        tmp_path,
        clock,
        steps=2,
        ttl_seconds=120,
        intent_id="CEO-A2FRESH-FACADE-001",
    )
    work1 = state.work(1)
    runtime = state.runtime
    exact_command = state.dispatch_command(work1.job_id, 1)

    clock.advance(seconds=121)

    before = _full_snapshot(runtime)
    with pytest.raises(StateConflict, match="expired"):
        runtime.attempts.dispatch_cycle_job(
            work1.job_id, command_id=exact_command, worker_id="worker-a"
        )
    with pytest.raises(StateConflict, match="expired"):
        runtime.jobs.assign_job(work1.job_id, "worker-a")
    with pytest.raises(StateConflict, match="expired"):
        runtime.broker.claim(work1.job_id, worker_id="worker-a")
    with pytest.raises(StateConflict, match="expired"):
        runtime.broker.dispatch(work1.job_id)
    with pytest.raises(StateConflict, match="expired"):
        runtime.attempts.claim_job(
            work1.job_id,
            worker_id="worker-a",
            command_id=exact_command,
            _coo_cycle_dispatch_capability=(
                executive_runtime._COO_CYCLE_DISPATCH_CAPABILITY
            ),
        )
    assert _full_snapshot(runtime) == before


def test_two_connections_race_one_remaining_attempt_on_independent_quotas(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    state = _drive_to_admitted(
        tmp_path, clock, steps=2, cap=2,
        intent_id="CEO-A2FRESH-LAST-SLOT-RACE",
    )
    second = Runtime.at(tmp_path, clock=clock)
    second.store.bind_finite_control_context(state.context)
    rendezvous = threading.Barrier(3)
    outcomes: list[Any] = [None, None]

    def claim(index, runtime, worker):
        rendezvous.wait(timeout=10)
        try:
            job = state.work(index)
            outcomes[index] = runtime.attempts.dispatch_cycle_job(
                job.job_id, command_id=state.dispatch_command(job.job_id, 1),
                worker_id=worker,
            )
        except StateConflict as exc:
            outcomes[index] = exc

    threads = [
        threading.Thread(target=claim, args=(0, state.runtime, "worker-a")),
        threading.Thread(target=claim, args=(1, second, "worker-b")),
    ]
    for thread in threads:
        thread.start()
    rendezvous.wait(timeout=10)
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    winners = [value for value in outcomes if isinstance(value, OrchestrationDispatchOutcome)]
    losers = [value for value in outcomes if isinstance(value, StateConflict)]
    assert len(winners) == len(losers) == 1
    assert "attempt cap" in str(losers[0])
    with state.runtime.store.read() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM attempts a JOIN jobs j ON j.job_id=a.job_id WHERE j.root_job_id=?",
            (state.root.job_id,),
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM worker_quota_classes WHERE held_attempt_id IS NOT NULL"
        ).fetchone()[0] == 1
    assert state.runtime.jobs.finite_cycle_status(state.root.job_id)["spent"] == 2


@pytest.mark.parametrize('phase', ['foreign', 'admission'])
@pytest.mark.parametrize('owner_method', [
    'seal_operator_harness_attempt', 'bind_start_result', 'seal_attestation',
    'acknowledge_turn', 'record_candidate_evidence', 'seal_orchestration_role_result',
    'record_graceful_stop', 'abandon_epoch', 'complete_attempt',
])
def test_incumbent_ohf_mutation_owners_refuse_wrong_context(tmp_path, monkeypatch, phase, owner_method):
    from test_executive_finite_reservations import _claimed, _snapshot
    runtime, clock, root, dispatch, profile, context = _claimed(tmp_path, cap=2, seal=False)
    other = Runtime.at(tmp_path, clock=clock)
    if phase == 'foreign':
        envelope2, root2 = _finite_root(other, 'CEO-ISOLATION-OTHER')
        other.store.bind_finite_control_context(_issue(_bound_definition(
            root2, envelope2, runtime=other, expires_at_ms=clock.value+20000)))
    else:
        other.store.bind_finite_control_context(_issue(_precomputed_admission_definition(_v2_intent())))
    own_registry = runtime.attempts if owner_method == 'complete_attempt' else runtime.operator_harness
    foreign_registry = other.attempts if owner_method == 'complete_attempt' else other.operator_harness
    actual = getattr(foreign_registry, owner_method)
    visits = []
    class ObservedRefusal(Exception):
        pass
    def checked(*args, **kwargs):
        before = _snapshot(runtime)
        with pytest.raises(StateConflict, match='finite'):
            actual(*args, **kwargs)
        assert _snapshot(runtime) == before
        visits.append(owner_method)
        raise ObservedRefusal()
    monkeypatch.setattr(own_registry, owner_method, checked)
    plan = {'schema_version':'mastermind.execution_plan/v1','root_job_id':root.job_id,
            'plan_attempt_id':dispatch.attempt.attempt_id,'steps':_plan_steps(1)}
    with pytest.raises(ObservedRefusal):
        _complete_ohf_role(runtime, dispatch, plan, identity_seed=9401)
    assert visits == [owner_method]


def test_bound_bulk_reconciliation_selects_only_its_root_and_target_foreign_refuses(tmp_path):
    from test_executive_finite_reservations import _claimed, _snapshot
    runtime, clock, root, dispatch, profile, context = _claimed(tmp_path)
    foreign = Runtime.at(tmp_path, clock=clock)
    _register(foreign, 'worker-b')
    envelope2, root2 = _finite_root(foreign, 'CEO-RECONCILE-OTHER')
    planner2 = foreign.jobs.create_cycle_planner(root2.job_id,command_id=f'coo-cycle:{root2.job_id}:create-planner:0')
    second = foreign.attempts.dispatch_cycle_job(planner2.job_id,
        command_id=f'coo-cycle:{root2.job_id}:dispatch:{planner2.job_id}:attempt:1',worker_id='worker-b')
    assert isinstance(second, OrchestrationDispatchOutcome)
    before = _snapshot(runtime)
    with pytest.raises(StateConflict,match='foreign'):
        runtime.attempts.reconcile_expired(attempt_id=second.attempt.attempt_id)
    assert _snapshot(runtime)==before
    clock.advance(seconds=61)
    foreign_before = foreign.attempts.get_attempt(second.attempt.attempt_id)
    values = runtime.attempts.reconcile_expired()
    assert [value.attempt_id for value in values] == [dispatch.attempt.attempt_id]
    assert foreign.attempts.get_attempt(second.attempt.attempt_id) == foreign_before
    # No-context recovery remains available even when finite owner is expired.
    values = foreign.attempts.reconcile_expired(attempt_id=second.attempt.attempt_id)
    assert [value.attempt_id for value in values] == [second.attempt.attempt_id]


@pytest.mark.parametrize('phase', ['foreign', 'admission'])
def test_worker_status_cannot_mutate_a_held_foreign_attempt(tmp_path, phase):
    from test_executive_finite_reservations import _claimed, _snapshot
    runtime, clock, root, dispatch, profile, context = _claimed(tmp_path)
    other=Runtime.at(tmp_path,clock=clock)
    if phase=='foreign':
        envelope2,root2=_finite_root(other,'CEO-STATUS-OTHER')
        other.store.bind_finite_control_context(_issue(_bound_definition(root2,envelope2,runtime=other,
            expires_at_ms=clock.value+20000)))
    else:
        other.store.bind_finite_control_context(_issue(_precomputed_admission_definition(_v2_intent())))
    before=_snapshot(runtime)
    with pytest.raises(StateConflict,match='finite'):
        other.workers.set_worker_status('worker-a','DRAINING')
    assert _snapshot(runtime)==before


def test_cycle_child_final_write_rechecks_deadline_after_lineage(tmp_path, monkeypatch):
    clock=MutableClock()
    state=_drive_to_admitted(tmp_path,clock,steps=1,review_required=True)
    _complete_work(state,0)
    before=_full_snapshot(state.runtime)
    original=executive_runtime._assert_orchestration_lineage_for_create
    reached=[]
    def validate(*args,**kwargs):
        result=original(*args,**kwargs)
        if kwargs['role']=='review':
            reached.append(True)
            clock.value=state.definition['expires_at_ms']
        return result
    monkeypatch.setattr(executive_runtime,'_assert_orchestration_lineage_for_create',validate)
    with pytest.raises(StateConflict,match='expired'):
        state.runtime.jobs.create_cycle_review(state.root.job_id,state.work(0).job_id,
            command_id=f'coo-cycle:{state.root.job_id}:create-review:{state.work(0).job_id}:1')
    assert reached and _full_snapshot(state.runtime)==before
