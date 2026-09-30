"""R33: CooCycle domain entry and scheduling progression.

Three scheduling discriminators (frozen pre-change):

1. ``test_cycle_creates_v2_domain_with_deterministic_command`` --
   a strict v2 root that declares the COO domain operator profile is
   still child-free before the cycle runs.  The cycle itself must call
   ``create_cycle_domain`` with the ``coo-cycle:{root_id}:create-domain:0``
   command, while a flat v2 root keeps the ``create_cycle_planner`` /
   ``create-planner:0`` identity.

2. ``test_cycle_reconciles_active_descendant_while_domain_waits`` --
   once a checkpointed domain has a sealed plan admitted, the cycle must
   reconcile its active exact descendant (or dispatch an eligible queued
   descendant) before considering the domain itself.  The domain stays
   checkpointed; the outcome is a meaningful ``CooCycleOutcome``, not a
   bare ``None``.

3. ``test_cycle_creates_required_review_before_consumption`` --
   after a depth-2 work result completes, the cycle must create the
   required independent reviewer through ``create_cycle_review`` before
   any consumption path runs.

Real Runtime public mutation/validation APIs only.  Typed external
adapters and the test-only COO-domain profile enabling via the
canonical R6A admitting-registry proxy are allowed.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.executive_agent_capabilities import (
    COO_DOMAIN_EXECUTION_PROFILE,
)
from control_plane.executive_coo_cycle import CooCycle, CooCycleOutcome
from control_plane.executive_runtime import (
    ExecutionCapabilityRegistry,
    INTERACTIVE_TX5_EXECUTION_PROFILE,
    JobStatus,
    Runtime,
    StateConflict,
)


# -- shared fixtures/helpers -------------------------------------------------


def _flat_v2_intent(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": INTENT_SCHEMA_V2,
        "intent_id": "CEO-R32-FLAT-001",
        "actor": "ceo-sol",
        "objective": "Schedule exactly one bounded cycle (flat).",
        "department": "executive-infrastructure",
        "priority": 9,
        "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
        "execution_contract": {"requested_authorities": ["READ"], "attempt_limit": 2},
        "intent_kind": "executive_coo_cycle",
        "business_impact": "material",
    }
    value.update(overrides)
    return value


# -- Test 1: domain creator + provenance ----------------------------------


def test_cycle_creates_v2_domain_with_deterministic_command(
    tmp_path: Path,
) -> None:
    """v2 root + COO domain operator binding -> ``create_cycle_domain``.

    Uses the real strict-v2 intent writer and workspace setup, but stops
    before the domain child exists.  Therefore the observed child can only
    come from CooCycle's public Runtime domain creator.
    """
    from test_executive_coo_hierarchy import (
        _r6a_runtime_with_operator,
        _r6a_setup_workspace,
        _v2_intent,
    )

    workspace = _r6a_setup_workspace(tmp_path)
    runtime = _r6a_runtime_with_operator(tmp_path / "runtime")
    registry = ExecutionCapabilityRegistry.load()
    profile = registry.profiles[COO_DOMAIN_EXECUTION_PROFILE]
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    binding = {
        "eligible_quota_classes": ["codex-coo", "codex-coo-default"],
        "provider": "codex",
        "model": "gpt-test",
        "effort": "low",
        "cost_class": "small",
        "base_sha": base_sha,
        "routing_policy_version": "test-routing",
        "execution_profile_id": COO_DOMAIN_EXECUTION_PROFILE,
        "execution_profile_digest": profile.profile_digest,
        "capability_policy_version": registry.policy_version,
        "capability_policy_digest": registry.policy_digest,
        "operator_eligible_quota_classes": ["codex-coo-operator"],
        "operator_provider": "codex",
        "operator_model": "gpt-test",
        "operator_effort": "low",
        "operator_cost_class": "small",
        "operator_routing_policy_version": "test-routing",
        "operator_execution_profile_id": COO_DOMAIN_EXECUTION_PROFILE,
        "operator_execution_profile_digest": profile.profile_digest,
        "operator_capability_policy_version": registry.policy_version,
        "operator_capability_policy_digest": registry.policy_digest,
        "operator_harness_binary_digest": "a" * 64,
        "operator_harness_version": "0.147.0",
        "operator_harness_armed": True,
    }
    intent = _v2_intent(intent_id="CEO-R33-DOMAIN-CYCLE-CREATION")
    intent["grounding"] = {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40}
    intent["execution_contract"] = {
        "requested_authorities": ["READ"],
        "branch": "codex/r6a-domain",
        "worktree": str(workspace),
        "attempt_limit": 2,
    }
    receipt = submit_intent(
        runtime,
        intent,
        workspace_root=workspace.parent,
        execution_binding=binding,
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    assert root.constraints.get("operator_execution_profile_id") == (
        COO_DOMAIN_EXECUTION_PROFILE
    )
    assert not [
        job for job in runtime.jobs.list_jobs() if job.parent_job_id == root.job_id
    ]

    outcome = CooCycle(runtime).run_once(root.job_id)
    assert outcome.action == "DOMAIN_CREATED", outcome
    assert outcome.command_id == f"coo-cycle:{root.job_id}:create-domain:0"
    children = [
        job for job in runtime.jobs.list_jobs() if job.parent_job_id == root.job_id
    ]
    assert len(children) == 1
    child = children[0]
    assert child.job_id == outcome.selected_job_id
    assert child.orchestration_role == "plan"
    assert child.constraints.get("execution_profile_id") == (
        COO_DOMAIN_EXECUTION_PROFILE
    )
    expected_command = f"coo-cycle:{root.job_id}:create-domain:0"
    assert child.orchestration_provenance["command_id"] == expected_command
    assert child.orchestration_provenance["creator"] == "coo_cycle"


def test_cycle_creates_planner_for_flat_v2_root(tmp_path: Path) -> None:
    """Flat v2 root keeps ``create_cycle_planner`` + ``create-planner:0``."""

    runtime = Runtime.at(tmp_path)
    receipt = submit_intent(
        runtime, _flat_v2_intent(intent_id="CEO-R32-FLAT-002")
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    outcome = CooCycle(runtime).run_once(root.job_id)
    assert isinstance(outcome, CooCycleOutcome)
    assert outcome.action == "PLANNER_CREATED", outcome
    assert outcome.command_id == f"coo-cycle:{root.job_id}:create-planner:0"


def test_pre_admission_validation_rejects_unrelated_child(
    tmp_path: Path,
) -> None:
    """A forged, non-command-aware child cannot enter the pre-admission root."""

    runtime = Runtime.at(tmp_path)
    receipt = submit_intent(
        runtime, _flat_v2_intent(intent_id="CEO-R32-FORGERY-001")
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    with pytest.raises(StateConflict, match="provenance source is not the closed wire"):
        runtime.jobs.create_job(
            "forged child",
            parent_job_id=root.job_id,
            requested_authorities=["READ"],
            constraints={"cost_class": "small"},
            attempt_limit=1,
            command_id="external:rogue:create:1",
            orchestration_role="work",
        )
    assert not [
        job for job in runtime.jobs.list_jobs() if job.parent_job_id == root.job_id
    ]
    assert CooCycle(runtime).run_once(root.job_id).action == "PLANNER_CREATED"


# -- Test 2: domain descendant scheduling ----------------------------------


def test_cycle_reconciles_active_descendant_while_domain_waits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cycle reconciles an active exact descendant, not the domain.

    Uses the existing ``_r7a_seed_active_domain_with_review`` helper
    to set up a checkpointed domain with a sealed plan and a single
    depth-2 work leaf admitted by the test (same real Runtime path the
    cycle uses).  Then dispatches the work leaf so it is ACTIVE, and
    finally runs the cycle with a recording dispatcher.
    """
    from test_executive_coo_hierarchy import (
        _r7a_dispatch_cycle_work,
        _r7a_runtime_with_work_and_review_workers,
        _r7a_seed_active_domain_with_review,
    )

    runtime, root, domain, _adapter, _dispatch = (
        _r7a_seed_active_domain_with_review(tmp_path, monkeypatch=monkeypatch)
    )
    _r7a_runtime_with_work_and_review_workers(runtime)

    domain_attempt_id = domain.current_attempt_id
    leaves = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}",
    )
    assert len(leaves) == 1
    work = leaves[0]
    assert work.parent_job_id == domain.job_id
    assert work.root_job_id == root.job_id

    work_dispatch = _r7a_dispatch_cycle_work(
        runtime,
        root_job_id=root.job_id,
        work_job_id=work.job_id,
        worker_id="worker-r6a-work",
        quota_class="codex-coo",
    )

    # Dispatcher must never receive the waiting domain id while an exact
    # descendant is active.  An active incumbent is a durable reconcilable
    # unit of work, so it must be dispatched through the public Runtime
    # boundary and yield a receipt; ``None`` is reserved for preclaim
    # unavailability and cannot reconcile active work.
    dispatched: list[tuple[str, str]] = []

    def dispatcher(job_id: str, command_id: str):
        dispatched.append((job_id, command_id))
        receipt = runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            worker_id="worker-r6a-work",
            quota_class="codex-coo",
        )
        assert receipt is not None and receipt.outcome == "ACTIVE"
        return receipt

    outcome = CooCycle(runtime, dispatcher=dispatcher).run_once(root.job_id)
    assert isinstance(outcome, CooCycleOutcome), outcome
    assert outcome is not None
    assert dispatched, "cycle must attempt at least one descendant dispatch"
    assert all(
        job_id != domain.job_id for job_id, _cmd in dispatched
    ), dispatched
    after = runtime.jobs.get_job(domain.job_id)
    assert after is not None
    assert after.current_attempt_id == domain.current_attempt_id
    # The cycle must produce a meaningful outcome action, not bare None.
    assert outcome.action == "DISPATCHED", outcome
    assert outcome.selected_job_id == work.job_id
    assert outcome.receipt["outcome"] == "ACTIVE"
    after_work = runtime.jobs.get_job(work.job_id)
    assert after_work is not None
    assert after_work.status == "RUNNING"
    assert after_work.current_attempt_id == outcome.receipt["attempt"]["attempt_id"]


# -- Test 3: review creation before consumption ----------------------------


def test_cycle_creates_required_review_before_consumption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After completed depth-2 work, the cycle creates the required reviewer.

    Re-uses the canonical ``_r7a_complete_work`` helper to seal a real
    work role result through the inert OHF runtime boundary, then runs
    the cycle.  The discriminator only asserts the cycle reaches
    ``REVIEW_CREATED`` before any consumption projection runs; the
    consumption seam remains out of scope for R33.
    """
    from test_executive_coo_hierarchy import (
        _r7a_complete_work,
        _r7a_dispatch_cycle_work,
        _r7a_plan_digest_for_domain,
        _r7a_runtime_with_work_and_review_workers,
        _r7a_seed_active_domain_with_review,
    )

    runtime, root, domain, _adapter, _dispatch = (
        _r7a_seed_active_domain_with_review(tmp_path, monkeypatch=monkeypatch)
    )
    _r7a_runtime_with_work_and_review_workers(runtime)
    domain_attempt_id = domain.current_attempt_id
    leaves = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}",
    )
    work = leaves[0]
    assert work.review_required is True
    plan_digest = _r7a_plan_digest_for_domain(
        runtime, root.job_id, domain_attempt_id
    )
    work_dispatch = _r7a_dispatch_cycle_work(
        runtime,
        root_job_id=root.job_id,
        work_job_id=work.job_id,
        worker_id="worker-r6a-work",
        quota_class="codex-coo",
    )
    _r7a_complete_work(
        runtime,
        work_dispatch,
        plan_attempt_id=domain_attempt_id,
        plan_digest=plan_digest,
        identity_seed=32001,
    )
    completed = runtime.jobs.get_job(work.job_id)
    assert completed is not None and completed.status == "COMPLETED"
    assert not [
        job for job in runtime.jobs.list_jobs() if job.reviews_job_id == work.job_id
    ]

    outcome = CooCycle(runtime).run_once(root.job_id)
    assert isinstance(outcome, CooCycleOutcome)
    assert outcome.action == "REVIEW_CREATED", outcome
    assert outcome.command_id == (
        f"coo-cycle:{root.job_id}:create-review:{work.job_id}:1"
    )


# -- R35: exact domain/no-admission and descendant scheduling ---------------


def _r35_seed_waiting_domain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from test_executive_coo_hierarchy import (
        _r7a_runtime_with_work_and_review_workers,
        _r7a_seed_active_domain_with_review,
    )

    runtime, root, domain, adapter, _command = (
        _r7a_seed_active_domain_with_review(tmp_path, monkeypatch=monkeypatch)
    )
    _r7a_runtime_with_work_and_review_workers(runtime)
    return runtime, root, domain, adapter


def _r35_dispatcher(runtime: Runtime):
    dispatched: list[tuple[str, str, object]] = []

    def dispatcher(job_id: str, command_id: str):
        job = runtime.jobs.get_job(job_id)
        assert job is not None
        if job.orchestration_role == "review":
            worker_id = "worker-r6a-review"
        else:
            worker_id = "worker-r6a-work"
        dispatched.append((job_id, command_id, job.orchestration_role))
        return runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            worker_id=worker_id,
            quota_class="codex-coo",
        )

    return dispatched, dispatcher


def _r36_v3_execution_binding(*, base_sha: str) -> dict[str, Any]:
    """Host-owned v3 binding for the two-work domain overlap fixtures.

    Copies the legitimate COO-domain operator binding used by the R6A
    public submit path, then adds the reviewed v3 placement union.  The
    union is exactly ``codex`` / ``codex-coo`` so both initial work steps
    project inside the admitted host composition.
    """

    registry = ExecutionCapabilityRegistry.load()
    profile = registry.profiles[COO_DOMAIN_EXECUTION_PROFILE]
    return {
        "eligible_quota_classes": ["codex-coo", "codex-coo-default"],
        "provider": "codex",
        "model": "gpt-test",
        "effort": "low",
        "cost_class": "small",
        "base_sha": base_sha,
        "routing_policy_version": "test-routing",
        "execution_profile_id": COO_DOMAIN_EXECUTION_PROFILE,
        "execution_profile_digest": profile.profile_digest,
        "capability_policy_version": registry.policy_version,
        "capability_policy_digest": registry.policy_digest,
        "operator_eligible_quota_classes": ["codex-coo-operator"],
        "operator_provider": "codex",
        "operator_model": "gpt-test",
        "operator_effort": "low",
        "operator_cost_class": "small",
        "operator_routing_policy_version": "test-routing",
        "operator_execution_profile_id": COO_DOMAIN_EXECUTION_PROFILE,
        "operator_execution_profile_digest": profile.profile_digest,
        "operator_capability_policy_version": registry.policy_version,
        "operator_capability_policy_digest": registry.policy_digest,
        "operator_harness_binary_digest": "a" * 64,
        "operator_harness_version": "0.147.0",
        "operator_harness_armed": True,
        "host_execution_binding_version": "mastermind.host_execution_binding/v3",
        "work_placement_union": [
            {"provider_realm": "codex", "quota_class": "codex-coo"},
        ],
    }


def _r36_seed_waiting_v3_domain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, unsafe_overlap: bool
):
    import control_plane.executive_operator_supervisor as operator_supervisor_module
    from test_executive_coo_hierarchy import (
        _AttemptStatus,
        _canonical_bytes,
        _ExecutiveOperatorSupervisor,
        _r6a_runtime_with_operator,
        _r6a_setup_workspace,
        _r7a_domain_envelope_review_required,
        _r7a_runtime_with_work_and_review_workers,
        _R6AFakeRegistryLoader,
        _R6APromptSource,
        _R7ADomainAdapter,
        _v2_intent,
    )

    def canonical_result(self, turn):
        attempt = self.runtime.attempts.get_attempt(turn.attempt_id)
        assert attempt is not None
        job = self.runtime.jobs.get_job(attempt.job_id)
        assert job is not None
        envelope = json.loads(
            _r7a_domain_envelope_review_required(job, attempt)
        )
        role_result = envelope["role_result"]
        role_result["schema_version"] = "mastermind.execution_plan/v3"
        role_result["steps"][0]["placement"] = {
            "provider_realm": "codex",
            "quota_class": "codex-coo",
        }
        role_result["steps"][0]["prerequisite_step_ids"] = []
        role_result["steps"].append(
            {
                "ordinal": 1,
                "step_id": "r36-step-2",
                "objective": "Remain an independent initial sibling.",
                "business_impact": "routine",
                "review_required": False,
                "requested_authorities": (
                    ["READ", "WRITE_BRANCH"] if unsafe_overlap else ["READ"]
                ),
                "allowed_write_paths": (
                    ["control_plane/example.py"] if unsafe_overlap else []
                ),
                "validation_ids": [],
                "attempt_limit": 1,
                "cost_class": "small",
                "placement": {
                    "provider_realm": "codex",
                    "quota_class": "codex-coo",
                },
                "prerequisite_step_ids": [],
            }
        )
        return _canonical_bytes(envelope).decode("utf-8")

    workspace = _r6a_setup_workspace(tmp_path)
    runtime = _r6a_runtime_with_operator(tmp_path / "runtime")
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    contract: dict[str, Any] = {
        "requested_authorities": ["READ"],
        "branch": "codex/r6a-domain",
        "worktree": str(workspace),
        "attempt_limit": 2,
    }
    if unsafe_overlap:
        contract["requested_authorities"] = ["READ", "WRITE_BRANCH"]
        contract["allowed_write_paths"] = ["control_plane/example.py"]
    intent = _v2_intent(
        intent_id=(
            "CEO-R36-V3-UNSAFE-OVERLAP"
            if unsafe_overlap
            else "CEO-R36-V3-SAFE-OVERLAP"
        ),
        business_impact="routine",
    )
    intent["grounding"] = {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40}
    intent["execution_contract"] = contract
    receipt = submit_intent(
        runtime,
        intent,
        workspace_root=workspace.parent,
        execution_binding=_r36_v3_execution_binding(base_sha=base_sha),
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    domain = runtime.jobs.create_cycle_domain(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-domain:0",
    )

    monkeypatch.setattr(_R7ADomainAdapter, "_canonical_result", canonical_result)
    monkeypatch.setattr(
        operator_supervisor_module,
        "ExecutionCapabilityRegistry",
        _R6AFakeRegistryLoader,
    )
    adapters: list[Any] = []

    def factory(loader):
        adapter = _R7ADomainAdapter(runtime)
        adapters.append(adapter)
        return adapter

    supervisor = _ExecutiveOperatorSupervisor(
        runtime,
        adapter_factory=factory,
        prompt_source=_R6APromptSource(),
    )
    dispatch_command_id = (
        f"coo-cycle:{root.job_id}:dispatch:{domain.job_id}:attempt:1"
    )
    outcome = asyncio.run(
        supervisor.start_cycle_job(domain.job_id, command_id=dispatch_command_id)
    )
    assert outcome.outcome == "ACTIVE"
    attempt = runtime.attempts.get_attempt(outcome.attempt.attempt_id)
    assert attempt is not None and attempt.status is _AttemptStatus.CHECKPOINTED
    active_domain = runtime.jobs.get_job(domain.job_id)
    assert active_domain is not None
    assert active_domain.current_attempt_id == outcome.attempt.attempt_id
    _r7a_runtime_with_work_and_review_workers(runtime)
    return runtime, root, active_domain, adapters[0]


def _r36_register_second_work_worker(runtime: Runtime) -> None:
    registry = ExecutionCapabilityRegistry.load()
    profile = registry.profiles[COO_DOMAIN_EXECUTION_PROFILE]
    runtime.workers.register_worker(
        "worker-r36-work",
        provider="codex",
        account_label="worker-r36-work@company",
        worker_type="fixture",
        capabilities=[],
        quota_classes={
            "codex-coo": {
                "provider": "codex",
                "model": "gpt-test",
                "effort": "low",
                "cost_class": "small",
                "capabilities": [],
                "metadata": {
                    "routing_policy_version": "test-routing",
                    "execution_profile_id": COO_DOMAIN_EXECUTION_PROFILE,
                    "execution_profile_digest": profile.profile_digest,
                    "capability_policy_version": registry.policy_version,
                    "capability_policy_digest": registry.policy_digest,
                },
            }
        },
    )


def test_cycle_admits_sealed_checkpointed_domain_without_manual_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, root, domain, _adapter = _r35_seed_waiting_domain(
        tmp_path, monkeypatch
    )
    assert domain.status is JobStatus.CHECKPOINTED
    assert domain.orchestration_role == "plan"
    assert domain.constraints["execution_profile_id"] == (
        COO_DOMAIN_EXECUTION_PROFILE
    )
    assert not [
        job
        for job in runtime.jobs.list_jobs()
        if job.parent_job_id == domain.job_id
    ]

    outcome = CooCycle(runtime).run_once(root.job_id)

    assert outcome.action == "PLAN_ADMITTED", outcome
    assert outcome.selected_job_id == domain.job_id
    assert outcome.command_id == (
        f"coo-cycle:{root.job_id}:admit-plan:{domain.current_attempt_id}"
    )
    leaves = [
        job
        for job in runtime.jobs.list_jobs()
        if job.parent_job_id == domain.job_id
    ]
    assert [job.job_id for job in leaves] == outcome.receipt["work_job_ids"]
    assert leaves[0].status is JobStatus.QUEUED


def test_waiting_domain_dispatches_first_queued_work_before_consumption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, root, domain, _adapter = _r35_seed_waiting_domain(
        tmp_path, monkeypatch
    )
    admission = CooCycle(runtime).run_once(root.job_id)
    assert admission.action == "PLAN_ADMITTED", admission
    work = runtime.jobs.get_job(admission.receipt["work_job_ids"][0])
    assert work is not None and work.status is JobStatus.QUEUED
    dispatched, dispatcher = _r35_dispatcher(runtime)

    outcome = CooCycle(runtime, dispatcher=dispatcher).run_once(root.job_id)

    assert outcome.action == "DISPATCHED", outcome
    assert outcome.selected_job_id == work.job_id
    assert outcome.command_id == (
        f"coo-cycle:{root.job_id}:dispatch:{work.job_id}:attempt:1"
    )
    assert dispatched == [
        (work.job_id, outcome.command_id, "work")
    ], dispatched
    after_work = runtime.jobs.get_job(work.job_id)
    assert after_work is not None and after_work.status is JobStatus.RUNNING
    assert not runtime.jobs.validated_cycle_block(root.job_id)


def test_next_tick_after_review_created_dispatches_actual_reviewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_executive_coo_hierarchy import (
        _r7a_complete_work,
        _r7a_plan_digest_for_domain,
    )

    runtime, root, domain, _adapter = _r35_seed_waiting_domain(
        tmp_path, monkeypatch
    )
    admission = CooCycle(runtime).run_once(root.job_id)
    work = runtime.jobs.get_job(admission.receipt["work_job_ids"][0])
    assert work is not None
    work_dispatch = runtime.attempts.dispatch_cycle_job(
        work.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{work.job_id}:attempt:1",
        worker_id="worker-r6a-work",
        quota_class="codex-coo",
    )
    assert work_dispatch is not None and work_dispatch.outcome == "ACTIVE"
    _r7a_complete_work(
        runtime,
        work_dispatch,
        plan_attempt_id=domain.current_attempt_id,
        plan_digest=_r7a_plan_digest_for_domain(
            runtime, root.job_id, domain.current_attempt_id
        ),
        identity_seed=33501,
    )
    review_created = CooCycle(runtime).run_once(root.job_id)
    assert review_created.action == "REVIEW_CREATED", review_created
    review = runtime.jobs.get_job(review_created.selected_job_id)
    assert review is not None and review.status is JobStatus.QUEUED
    dispatched, dispatcher = _r35_dispatcher(runtime)

    outcome = CooCycle(runtime, dispatcher=dispatcher).run_once(root.job_id)

    assert outcome.action == "DISPATCHED", outcome
    assert outcome.selected_job_id == review.job_id
    assert outcome.command_id == (
        f"coo-cycle:{root.job_id}:dispatch:{review.job_id}:attempt:1"
    )
    assert dispatched == [
        (review.job_id, outcome.command_id, "review")
    ], dispatched


def test_read_only_work_overlap_is_eligible_but_domain_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, root, domain, _adapter = _r35_seed_waiting_domain(
        tmp_path, monkeypatch
    )
    admission = CooCycle(runtime).run_once(root.job_id)
    work_ids = admission.receipt["work_job_ids"]
    first = runtime.jobs.get_job(work_ids[0])
    assert first is not None
    assert CooCycle(runtime)._is_read_only_frontier_work(first)
    assert CooCycle(runtime)._active_attempt_is_current_and_live(first) is False
    first_dispatch = runtime.attempts.dispatch_cycle_job(
        first.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{first.job_id}:attempt:1",
        worker_id="worker-r6a-work",
        quota_class="codex-coo",
    )
    assert first_dispatch is not None
    live_first = runtime.jobs.get_job(first.job_id)
    assert live_first is not None
    cycle = CooCycle(runtime)
    assert cycle._active_attempt_is_current_and_live(live_first)

    assert not cycle._is_read_only_frontier_work(domain)
    assert not cycle._ready_frontier_open([domain], [], {})
    assert not cycle._ready_frontier_candidate(domain, [live_first])


def test_read_only_work_overlap_dispatches_domain_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, root, _domain, _adapter = _r36_seed_waiting_v3_domain(
        tmp_path, monkeypatch, unsafe_overlap=False
    )
    _r36_register_second_work_worker(runtime)
    admission = CooCycle(runtime).run_once(root.job_id)
    assert admission.action == "PLAN_ADMITTED", admission
    work_ids = admission.receipt["work_job_ids"]
    first = runtime.jobs.get_job(work_ids[0])
    second = runtime.jobs.get_job(work_ids[1])
    assert first is not None
    assert second is not None
    first_dispatch = runtime.attempts.dispatch_cycle_job(
        first.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{first.job_id}:attempt:1",
        worker_id="worker-r6a-work",
        quota_class="codex-coo",
    )
    assert first_dispatch is not None
    dispatched, dispatcher = _r35_dispatcher(runtime)

    def second_dispatcher(job_id: str, command_id: str):
        job = runtime.jobs.get_job(job_id)
        assert job is not None
        worker_id = (
            "worker-r36-work"
            if job.plan_step_id == "r36-step-2"
            else "worker-r6a-work"
        )
        dispatched.append((job_id, command_id, job.orchestration_role))
        return runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            worker_id=worker_id,
            quota_class="codex-coo",
        )

    outcome = CooCycle(
        runtime, dispatcher=second_dispatcher
    ).run_once(root.job_id)

    assert outcome.action == "DISPATCHED", outcome
    assert outcome.selected_job_id == second.job_id
    assert dispatched == [
        (second.job_id, outcome.command_id, "work")
    ], dispatched


def test_unsafe_work_overlap_refuses_domain_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, root, _domain, _adapter = _r36_seed_waiting_v3_domain(
        tmp_path, monkeypatch, unsafe_overlap=True
    )
    admission = CooCycle(runtime).run_once(root.job_id)
    assert admission.action == "PLAN_ADMITTED", admission
    work_ids = admission.receipt["work_job_ids"]
    first = runtime.jobs.get_job(work_ids[0])
    second = runtime.jobs.get_job(work_ids[1])
    assert first is not None
    assert second is not None
    first_dispatch = runtime.attempts.dispatch_cycle_job(
        first.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{first.job_id}:attempt:1",
        worker_id="worker-r6a-work",
        quota_class="codex-coo",
    )
    assert first_dispatch is not None
    dispatched, dispatcher = _r35_dispatcher(runtime)

    outcome = CooCycle(runtime, dispatcher=dispatcher).run_once(root.job_id)

    assert outcome.action == "DISPATCHED", outcome
    assert outcome.selected_job_id == first.job_id
    assert [job_id for job_id, _command, _role in dispatched] == [first.job_id]
    after_second = runtime.jobs.get_job(second.job_id)
    assert after_second is not None
    assert after_second.attempt_count == 0


def test_finite_halt_and_interactive_fence_precede_domain_scheduling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_executive_coo_hierarchy import _r6a_submit_domain_root
    from test_executive_finite_guards import (
        MutableClock as _MutableClock,
        _arm,
        _bound_definition,
        _issue,
    )
    from test_executive_coo_hierarchy import _v2_intent

    runtime, root, _domain, _workspace = _r6a_submit_domain_root(tmp_path)
    clock = _MutableClock()
    runtime.store.clock = clock
    domain = runtime.jobs.get_job(_domain.job_id)
    intent = _v2_intent(intent_id="CEO-R6A-DOMAIN-ADMISSION")
    intent["execution_contract"] = {
        "requested_authorities": ["READ"],
        "branch": "codex/r6a-domain",
        "worktree": str(_workspace),
        "attempt_limit": 2,
    }
    definition = _bound_definition(
        root,
        intent,
        runtime=runtime,
        cap=10,
        expires_at_ms=clock.value + 3_600_000,
    )
    runtime.store.bind_finite_control_context(_issue(definition))
    _arm(runtime, _issue(definition))
    clock.advance(seconds=7_200)
    spent = CooCycle(runtime).run_once(root.job_id)

    assert spent.action == "NO_NEW_WORK", spent
    assert spent.receipt["halt_reason"] == "expired"

    halted = CooCycle(runtime).run_once(root.job_id)

    assert halted.action == "NO_NEW_WORK", halted
    assert halted.receipt["halt_reason"] == "expired"


def _r42_arm_finite_domain_root(runtime: Runtime, root, workspace: Path):
    """Bind and arm the submitted root before any live tree Attempt exists."""

    from test_executive_coo_hierarchy import _v2_intent
    from test_executive_finite_guards import (
        MutableClock as _MutableClock,
        _arm,
        _bound_definition,
        _issue,
    )

    clock = _MutableClock()
    runtime.store.clock = clock
    intent = _v2_intent(intent_id="CEO-R6A-DOMAIN-ADMISSION")
    intent["execution_contract"] = {
        "requested_authorities": ["READ"],
        "branch": "codex/r6a-domain",
        "worktree": str(workspace),
        "attempt_limit": 2,
    }
    definition = _bound_definition(
        root,
        intent,
        runtime=runtime,
        cap=10,
        expires_at_ms=clock.value + 3_600_000,
    )
    runtime.store.bind_finite_control_context(_issue(definition))
    _arm(runtime, _issue(definition))
    return clock


def _r42_checkpoint_reviewed_domain(
    runtime: Runtime,
    root,
    domain,
    monkeypatch: pytest.MonkeyPatch,
):
    """Dispatch the already-armed domain through the public supervisor path."""

    import control_plane.executive_operator_supervisor as operator_supervisor_module
    from test_executive_coo_hierarchy import (
        _AttemptStatus,
        _ExecutiveOperatorSupervisor,
        _r7a_runtime_with_work_and_review_workers,
        _R6AFakeRegistryLoader,
        _R6APromptSource,
        _R7ADomainAdapter,
    )

    monkeypatch.setattr(
        operator_supervisor_module,
        "ExecutionCapabilityRegistry",
        _R6AFakeRegistryLoader,
    )
    adapters: list[Any] = []

    def factory(loader):
        adapter = _R7ADomainAdapter(runtime)
        adapters.append(adapter)
        return adapter

    supervisor = _ExecutiveOperatorSupervisor(
        runtime,
        adapter_factory=factory,
        prompt_source=_R6APromptSource(),
    )
    dispatch_command_id = (
        f"coo-cycle:{root.job_id}:dispatch:{domain.job_id}:attempt:1"
    )
    outcome = asyncio.run(
        supervisor.start_cycle_job(domain.job_id, command_id=dispatch_command_id)
    )
    assert outcome.outcome == "ACTIVE"
    attempt = runtime.attempts.get_attempt(outcome.attempt.attempt_id)
    assert attempt is not None and attempt.status is _AttemptStatus.CHECKPOINTED
    active_domain = runtime.jobs.get_job(domain.job_id)
    assert active_domain is not None
    assert active_domain.current_attempt_id == outcome.attempt.attempt_id
    _r7a_runtime_with_work_and_review_workers(runtime)
    return active_domain, adapters[0]


def _r42_tree_snapshot(runtime: Runtime, root_job_id: str) -> dict[str, Any]:
    jobs = sorted(
        (
            {
                "job_id": job.job_id,
                "status": str(job.status),
                "attempt_count": job.attempt_count,
                "current_attempt_id": job.current_attempt_id,
                "orchestration_role": job.orchestration_role,
            }
            for job in runtime.jobs.list_jobs()
            if job.root_job_id == root_job_id
        ),
        key=lambda item: str(item["job_id"]),
    )
    attempts: list[dict[str, Any]] = []
    for job in runtime.jobs.list_jobs():
        if job.root_job_id != root_job_id or not job.current_attempt_id:
            continue
        attempt = runtime.attempts.get_attempt(job.current_attempt_id)
        assert attempt is not None
        attempts.append(
            {
                "attempt_id": attempt.attempt_id,
                "job_id": attempt.job_id,
                "status": str(attempt.status),
            }
        )
    attempts.sort(key=lambda item: str(item["attempt_id"]))
    return {"jobs": jobs, "attempts": attempts}


def _r42_seed_settled_reviewed_finite_domain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Public submit/bind/arm, then domain/work/review, then consumption projection.

    Arms the root while the created domain still has no Attempt.  The
    remaining lifecycle uses the existing hermetic operator adapter and
    work/review completion helpers.
    """

    from test_executive_coo_hierarchy import (
        _r6a_submit_domain_root,
        _r7a_dispatch_cycle_work,
        _r7a_plan_digest_for_domain,
        _r7a_review_body,
    )
    from test_executive_finite_guards import (
        _complete_ohf_role as _finite_complete_ohf_role,
    )

    runtime, root, domain, workspace = _r6a_submit_domain_root(tmp_path)
    assert domain.current_attempt_id is None
    assert domain.attempt_count == 0
    _r42_arm_finite_domain_root(runtime, root, workspace)
    domain, _adapter = _r42_checkpoint_reviewed_domain(
        runtime, root, domain, monkeypatch
    )
    domain_attempt_id = domain.current_attempt_id
    assert domain_attempt_id is not None
    leaves = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}",
    )
    work = leaves[0]
    plan_digest = _r7a_plan_digest_for_domain(
        runtime, root.job_id, domain_attempt_id
    )
    work_dispatch = _r7a_dispatch_cycle_work(
        runtime,
        root_job_id=root.job_id,
        work_job_id=work.job_id,
        worker_id="worker-r6a-work",
        quota_class="codex-coo",
    )
    work_body = {
        "schema_version": "mastermind.work_result/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": domain_attempt_id,
        "plan_digest": plan_digest,
        "plan_step_id": "r6a-step-1",
        "repair_round": 0,
        "artifacts": [],
        "evidence_digests": [],
    }
    work_seal, _terminal = _finite_complete_ohf_role(
        runtime, work_dispatch, work_body, identity_seed=42001
    )
    review = runtime.jobs.create_cycle_review(
        root.job_id,
        work.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-review:{work.job_id}:1",
    )
    review_dispatch = _r7a_dispatch_cycle_work(
        runtime,
        root_job_id=root.job_id,
        work_job_id=review.job_id,
        worker_id="worker-r6a-review",
        quota_class="codex-coo",
    )
    reviewed_digest = (
        work_seal["role_result_digest"]
        if isinstance(work_seal, dict)
        else work_seal.role_result_digest
    )
    review_body = _r7a_review_body(
        root_id=root.job_id,
        plan_attempt_id=domain_attempt_id,
        plan_digest=plan_digest,
        target_job_id=work.job_id,
        target_attempt_id=work_dispatch.attempt.attempt_id,
        target_result_digest=reviewed_digest,
        repair_round=0,
        verdict="approve",
        plan_step_id="r6a-step-1",
    )
    _finite_complete_ohf_role(
        runtime, review_dispatch, review_body, identity_seed=42002
    )
    projection = runtime.jobs.project_cycle_domain_consumption(
        root.job_id, domain_attempt_id=domain_attempt_id
    )
    settled_domain = runtime.jobs.get_job(domain.job_id)
    completed_work = runtime.jobs.get_job(work.job_id)
    completed_review = runtime.jobs.get_job(review.job_id)
    assert settled_domain is not None
    assert settled_domain.status is JobStatus.CHECKPOINTED
    assert settled_domain.attempt_count == 1
    assert completed_work is not None
    assert completed_work.status == JobStatus.COMPLETED
    assert completed_review is not None
    assert completed_review.status == JobStatus.COMPLETED
    assert projection["consumption_projection_digest"]
    assert projection["revisions"][0]["current_job_id"] == work.job_id
    assert projection["revisions"][0]["qualifying_review_job_id"] == review.job_id
    return runtime, root, settled_domain, work, review, projection


def _r42_recording_dispatcher(
    runtime: Runtime, *, lease_owner: str = "executive-coo-cycle"
):
    dispatched: list[tuple[str, str]] = []

    def dispatcher(job_id: str, command_id: str):
        dispatched.append((job_id, command_id))
        return runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            lease_owner=lease_owner,
        )

    return dispatched, dispatcher


def test_settled_domain_consumption_refuses_current_policy_pin_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_executive_finite_guards import DRIFT_PIN

    runtime, root, domain, work, review, projection = (
        _r42_seed_settled_reviewed_finite_domain(tmp_path, monkeypatch)
    )
    domain_attempt_id = domain.current_attempt_id
    before = _r42_tree_snapshot(runtime, root.job_id)

    class _DriftedCooPolicy:
        policy_sha256 = DRIFT_PIN

        @staticmethod
        def load():
            return _DriftedCooPolicy()

    import control_plane.executive_coo_cycle as coo_cycle_module

    monkeypatch.setattr(coo_cycle_module, "CooCyclePolicy", _DriftedCooPolicy)
    dispatched, dispatcher = _r42_recording_dispatcher(
        runtime, lease_owner="executive-coo-operator"
    )

    outcome = CooCycle(runtime, dispatcher=dispatcher).run_once(root.job_id)

    assert outcome.action == "NO_NEW_WORK", outcome
    assert outcome.receipt["halt_reason"] is None
    assert outcome.receipt["expired"] is False
    assert outcome.receipt["exhausted"] is False
    control = outcome.receipt["finite_control"]
    assert control["armed"] is True
    assert control["bound"] is True
    assert control["context_proven"] is True
    assert control["current_policy_pin_drift"] is True
    assert control["refusal_reasons"] == []
    assert control["advisory_first_issuance"] == [
        {
            "authorized_first_launch": False,
            "already_issued": True,
            "halt_reason": "already_issued",
        }
    ]
    assert control["settled_incumbent_job_id"] is None
    assert dispatched == []
    assert _r42_tree_snapshot(runtime, root.job_id) == before
    assert runtime.jobs.get_job(domain.job_id).status is JobStatus.CHECKPOINTED
    assert runtime.jobs.get_job(domain.job_id).attempt_count == 1
    assert runtime.attempts.get_attempt(domain_attempt_id).status == (
        JobStatus.CHECKPOINTED
    )
    assert projection["consumption_projection_digest"]
    assert projection["revisions"][0]["current_job_id"] == work.job_id
    assert projection["revisions"][0]["qualifying_review_job_id"] == review.job_id


def test_settled_domain_consumption_dispatches_with_matching_policy_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, root, domain, _work, _review, projection = (
        _r42_seed_settled_reviewed_finite_domain(tmp_path, monkeypatch)
    )
    dispatched, dispatcher = _r42_recording_dispatcher(
        runtime, lease_owner="executive-coo-operator"
    )

    outcome = CooCycle(runtime, dispatcher=dispatcher).run_once(root.job_id)

    assert outcome.action == "DISPATCHED", outcome
    assert outcome.selected_job_id == domain.job_id
    assert outcome.command_id == (
        f"coo-cycle:{root.job_id}:dispatch:{domain.job_id}:attempt:"
        f"{domain.attempt_count}"
    )
    assert dispatched == [(domain.job_id, outcome.command_id)]
    assert outcome.receipt["consumption_projection_digest"] == (
        projection["consumption_projection_digest"]
    )


def test_settled_domain_consumption_surfaces_projection_state_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, root, domain, _work, _review, _projection = (
        _r42_seed_settled_reviewed_finite_domain(tmp_path, monkeypatch)
    )
    domain_attempt_id = domain.current_attempt_id
    before = _r42_tree_snapshot(runtime, root.job_id)

    def unavailable_projection(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise StateConflict("domain consumption requires an active domain")

    dispatched, dispatcher = _r42_recording_dispatcher(runtime)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            runtime.jobs,
            "project_cycle_domain_consumption",
            unavailable_projection,
        )
        with pytest.raises(StateConflict, match="requires an active domain"):
            CooCycle(runtime, dispatcher=dispatcher).run_once(root.job_id)

    assert dispatched == []
    assert _r42_tree_snapshot(runtime, root.job_id) == before
    assert runtime.jobs.get_job(domain.job_id).status is JobStatus.CHECKPOINTED
    assert runtime.attempts.get_attempt(domain_attempt_id).status == (
        JobStatus.CHECKPOINTED
    )


def test_settled_domain_consumption_binds_requested_projection_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, root, domain, _work, _review, projection = (
        _r42_seed_settled_reviewed_finite_domain(tmp_path, monkeypatch)
    )
    requested: list[tuple[str, str]] = []

    def recording_projection(root_job_id: str, *, domain_attempt_id: str):
        requested.append((root_job_id, domain_attempt_id))
        return projection

    recording_receipt: list[dict[str, str]] = []
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            runtime.jobs,
            "project_cycle_domain_consumption",
            recording_projection,
        )
        def recording_dispatcher(job_id: str, command_id: str):
            recording_receipt.append(
                {
                    "job_id": job_id,
                    "command_id": command_id,
                }
            )
            return {
                "job_id": job_id,
                "command_id": command_id,
                "outcome": "BOUND",
            }

        outcome = CooCycle(runtime, dispatcher=recording_dispatcher).run_once(
            root.job_id
        )

    assert outcome.action == "DISPATCHED", outcome
    assert requested == [(root.job_id, domain.current_attempt_id)]
    assert recording_receipt == [
        {
            "job_id": domain.job_id,
            "command_id": outcome.command_id,
        }
    ]
    assert outcome.receipt["consumption_projection_digest"] == (
        projection["consumption_projection_digest"]
    )


def test_interactive_operator_remains_outside_one_shot_cycle(
    tmp_path: Path,
) -> None:
    from test_executive_coo_hierarchy import (
        _r6a_runtime_with_operator,
        _r6a_setup_workspace,
        _v2_intent,
    )

    workspace = _r6a_setup_workspace(tmp_path)
    runtime = _r6a_runtime_with_operator(tmp_path / "runtime")
    registry = ExecutionCapabilityRegistry.load()
    profile = registry.profiles[INTERACTIVE_TX5_EXECUTION_PROFILE]
    intent = _v2_intent(intent_id="CEO-R35-INTERACTIVE-FENCE")
    intent["execution_contract"] = {
        "requested_authorities": ["READ"],
        "branch": "codex/r35-interactive",
        "worktree": str(workspace),
        "attempt_limit": 2,
    }
    submit_intent(
        runtime,
        intent,
        workspace_root=workspace.parent,
        execution_binding={
            "eligible_quota_classes": ["codex-coo"],
            "provider": "codex",
            "model": "gpt-test",
            "effort": "low",
            "cost_class": "small",
            "base_sha": "a" * 40,
            "routing_policy_version": "test-routing",
            "execution_profile_id": "codex-test-work",
            "execution_profile_digest": "b" * 64,
            "capability_policy_version": registry.policy_version,
            "capability_policy_digest": registry.policy_digest,
            "operator_eligible_quota_classes": ["codex-coo-operator"],
            "operator_provider": "codex",
            "operator_model": "gpt-test",
            "operator_effort": "low",
            "operator_cost_class": "small",
            "operator_routing_policy_version": "test-routing",
            "operator_execution_profile_id": INTERACTIVE_TX5_EXECUTION_PROFILE,
            "operator_execution_profile_digest": profile.profile_digest,
            "operator_capability_policy_version": registry.policy_version,
            "operator_capability_policy_digest": registry.policy_digest,
            "operator_harness_binary_digest": "a" * 64,
            "operator_harness_version": "0.147.0",
            "operator_harness_armed": True,
        },
    )
    root = runtime.jobs.list_jobs()[0]
    planner = runtime.jobs.create_interactive_operator(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-interactive:0",
    )

    assert planner.constraints["execution_profile_id"] == (
        INTERACTIVE_TX5_EXECUTION_PROFILE
    )

    fence = CooCycle(runtime).run_once(root.job_id)
    assert fence.action == "NO_ACTION", fence
    assert fence.selected_job_id == planner.job_id
    assert fence.receipt["reason"] == (
        "interactive_profile_not_owned_by_one_shot_cycle"
    )


# -- R102: active flat planner reconciliation (R101-F1) ----------------------


def test_cycle_reconciles_active_flat_planner_same_job(
    tmp_path: Path,
) -> None:
    """R101-F1: a live flat-v2 ordinary planner must reach the dispatcher.

    The frozen R100 candidate filtered every ``orchestration_role == "plan"``
    Job out of step 7 incumbent reconciliation, so a dispatched flat
    planner was silently skipped and the cycle returned ``NO_ACTION``
    without ever calling the dispatcher.  Public-path reproduction:

    1. strict flat v2 root through ``submit_intent``;
    2. planner through ``runtime.jobs.create_cycle_planner``;
    3. dispatch that planner once through the public
       ``runtime.attempts.dispatch_cycle_job`` boundary;
    4. ``CooCycle(runtime, dispatcher).run_once(root_id)`` with a dispatcher
       that replays the same command.

    The expected behaviour: the cycle reconciles the planner's exact
    active Attempt through the dispatcher with the original command and
    never claims a replacement or a different Job.
    """

    runtime = Runtime.at(tmp_path)
    receipt = submit_intent(
        runtime, _flat_v2_intent(intent_id="CEO-R102-FLAT-PLANNER-RECONCILE")
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None

    created = CooCycle(runtime).run_once(root.job_id)
    assert created.action == "PLANNER_CREATED", created
    planner = runtime.jobs.get_job(created.selected_job_id)
    assert planner is not None
    assert planner.orchestration_role == "plan"
    assert planner.constraints.get("execution_profile_id") != (
        COO_DOMAIN_EXECUTION_PROFILE
    )
    assert planner.constraints.get("delegation_scope_digest") is None

    runtime.workers.register_worker(
        "worker-r102-flat",
        provider="codex",
        account_label="worker-r102-flat@company",
        worker_type="fixture",
        capabilities=[],
        quota_classes={
            "default": {
                "provider": "codex",
                "model": "gpt-test",
                "effort": "low",
                "cost_class": "small",
                "capabilities": [],
                "metadata": {},
            }
        },
    )

    original_command = (
        f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"
    )
    first = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=original_command,
        worker_id="worker-r102-flat",
        quota_class="default",
    )
    assert first is not None and first.outcome == "ACTIVE"
    live_planner = runtime.jobs.get_job(planner.job_id)
    assert live_planner is not None
    assert live_planner.status is JobStatus.RUNNING
    assert live_planner.attempt_count == 1
    original_attempt_id = live_planner.current_attempt_id

    children_before = runtime.jobs.list_jobs()
    dispatched_calls: list[tuple[str, str]] = []

    def dispatcher(job_id: str, command_id: str):
        dispatched_calls.append((job_id, command_id))
        return runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            worker_id="worker-r102-flat",
            quota_class="default",
        )

    outcome = CooCycle(runtime, dispatcher=dispatcher).run_once(root.job_id)

    assert dispatched_calls == [
        (planner.job_id, original_command)
    ], dispatched_calls
    assert outcome is not None
    assert outcome.action == "DISPATCHED", outcome
    assert outcome.selected_job_id == planner.job_id
    assert outcome.command_id == original_command
    after_planner = runtime.jobs.get_job(planner.job_id)
    assert after_planner is not None
    assert after_planner.job_id == original_command.split(":")[3]
    assert after_planner.current_attempt_id == original_attempt_id, (
        "must reconcile the same Job/Attempt; never claim a replacement"
    )
    children_after = runtime.jobs.list_jobs()
    assert len(children_after) == len(children_before), (
        "must not create a second Job"
    )
