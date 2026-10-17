"""Test-local genuine claimed Work Attempt -> fail-closed V4 Skill identity.

These tests use the existing COO v3 plan admission and SQLite Runtime;
there is no provider/session launch or production V4 policy installation.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.ceo_intent import submit_intent
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.executive_operator_supervisor import (
    ExecutiveOperatorSupervisor,
    ExecutiveOperatorSupervisorError,
)
from control_plane.executive_runtime import (
    AttemptLease, OrchestrationDispatchOutcome, Runtime, StateConflict,
)
from tests.test_executive_os_phase1fc import (
    _complete_ohf_role,
    _v2_intent,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
V4_POLICY = (
    REPO_ROOT / "scripts/ohf/fixtures/"
    "executive_agent_capabilities_v4_mastermind_operator.json"
)
PROFILE_ID = "operator.appserver.readonly.mastermind-operator.v1"
BINARY_DIGEST = "a" * 64
MODEL = "gpt-5.6-sol"
EFFORT = "xhigh"


def _seed_claimed_work(
    tmp_path: Path, *, dispatch_work: bool = True, review_required: bool = False,
):
    """Create the genuine Runtime claim, not a role-swapped fake planner."""
    workspace_root = tmp_path / "workspaces"
    worktree = workspace_root / "reviewed-work"
    worktree.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "codex/reviewed-work"],
                   cwd=worktree, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@mastermind.invalid"],
                   cwd=worktree, check=True)
    subprocess.run(["git", "config", "user.name", "Mastermind Fixture"],
                   cwd=worktree, check=True)
    (worktree / "README.md").write_text("Exact read-only Work fixture\n")
    subprocess.run(["git", "add", "."], cwd=worktree, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "original source"],
                   cwd=worktree, check=True)
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=worktree, text=True,
    ).strip()
    registry = ExecutionCapabilityRegistry.load(V4_POLICY, source_root=REPO_ROOT)
    profile = registry.resolve(PROFILE_ID)
    assert not registry.production_armed
    assert not profile.write_capable and len(profile.skill_grants) == 4
    rt = Runtime.at(tmp_path / "runtime")
    metadata = {
        "routing_policy_version": "fph0-routing",
        "execution_profile_id": profile.profile_id,
        "execution_profile_digest": profile.profile_digest,
        "capability_policy_version": registry.policy_version,
        "capability_policy_digest": registry.policy_digest,
        "harness_binary_digest": BINARY_DIGEST,
        "harness_version": "0.159.3",
    }
    rt.workers.register_worker(
        "worker-a", provider="codex", account_label="fixture@company",
        worker_type="mock", capabilities=["read", "research"],
        quota_classes={
            "codex-hf1q-step": {
                "provider": "codex",
                "capabilities": ["read", "research"],
                "cost_class": "small",
                "model": MODEL,
                "effort": EFFORT,
                "metadata": metadata,
            },
        },
    )
    original = _v2_intent(
        intent_id="CEO-V4-SKILL-WORK-001",
        execution_contract={
            "requested_authorities": ["READ"],
            "attempt_limit": 2,
            "branch": "codex/reviewed-work",
            "worktree": str(worktree),
        },
    )
    receipt = submit_intent(rt, original, workspace_root=workspace_root)
    root = rt.jobs.get_job(receipt["job_id"])
    assert root is not None and root.worktree == str(worktree)
    with rt.store.transaction() as connection:
        connection.execute(
            "UPDATE jobs SET constraints_json=? WHERE job_id=?",
            (
                json.dumps(
                    {
                        **root.constraints,
                        "provider": "codex",
                        "base_sha": source_sha,
                        "model": MODEL,
                        "effort": EFFORT,
                        "eligible_quota_classes": ["codex-hf1q-step"],
                        "work_placement_union": [
                            {
                                "provider_realm": "codex",
                                "quota_class": "codex-hf1q-step",
                            }
                        ],
                        **metadata,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                root.job_id,
            ),
        )
    planner = rt.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    claimed_plan = rt.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="worker-a",
        quota_class="codex-hf1q-step",
    )
    assert isinstance(claimed_plan, OrchestrationDispatchOutcome)
    body = {
        "schema_version": "mastermind.execution_plan/v3",
        "root_job_id": root.job_id,
        "plan_attempt_id": claimed_plan.attempt.attempt_id,
        "steps": [
            {
                "ordinal": 0,
                "step_id": "step-0",
                "objective": "Observe exact source without file mutations",
                "business_impact": "routine",
                "review_required": review_required,
                "requested_authorities": ["READ"],
                "allowed_write_paths": [],
                "validation_ids": [],
                "attempt_limit": 1,
                "cost_class": "small",
                "prerequisite_step_ids": [],
                "placement": {
                    "provider_realm": "codex",
                    "quota_class": "codex-hf1q-step",
                },
            },
        ],
    }
    _complete_ohf_role(rt, claimed_plan, body, identity_seed=8817)
    admitted = rt.jobs.admit_cycle_plan(
        root.job_id,
        command_id=(
            f"coo-cycle:{root.job_id}:admit-plan:"
            f"{claimed_plan.attempt.attempt_id}"
        ),
    )
    assert len(admitted) == 1
    job = admitted[0]
    assert job.orchestration_role == "work"
    assert job.worktree == str(worktree)
    assert job.requested_authorities == ["READ"]
    assert not job.allowed_write_paths and not job.validation_commands
    lease = None
    if dispatch_work:
        dispatched = rt.attempts.dispatch_cycle_job(
            job.job_id,
            command_id=(
                f"coo-cycle:{root.job_id}:dispatch:"
                f"{job.job_id}:attempt:1"
            ),
            worker_id="worker-a",
            quota_class="codex-hf1q-step",
        )
        assert isinstance(dispatched, OrchestrationDispatchOutcome)
        assert dispatched.lease_token is not None
        assert dispatched.attempt.requested_execution_profile_digest is None
        lease = AttemptLease(dispatched.attempt, dispatched.lease_token)
    return rt, job, lease, registry, profile, source_sha


def test_claimed_readonly_work_can_bind_exact_v4_skills_before_provider(tmp_path, monkeypatch):
    rt, job, lease, registry, policy_profile, _source_sha = _seed_claimed_work(tmp_path)
    monkeypatch.setattr(ExecutionCapabilityRegistry, "load", lambda *_, **__: registry)
    supervisor = ExecutiveOperatorSupervisor(
        rt, claimed_adapter_factory=lambda *_a, **_kw: object(),
        prompt_source=object(),
    )
    assert lease is not None
    requested = supervisor._requested_profile(job, lease)
    assert requested.sandbox_policy == "read-only"
    assert requested.write_capable is False and requested.allowed_write_paths == ()
    assert requested.capabilities == policy_profile.capability_manifest(
        harness_binary_digest=BINARY_DIGEST,
    )
    assert requested.workspace.workspace_path == job.worktree
    assert len(
        [c for c in requested.capabilities.required if c.kind == "skill"]
    ) == 4
    assert rt.attempts.get_attempt(lease.attempt.attempt_id).status.value == "CLAIMED"

def test_default_installed_v3_refuses_nonplanner_before_claim_or_provider(tmp_path):
    rt, job, lease, registry, _profile, _source = _seed_claimed_work(
        tmp_path, dispatch_work=False,
    )
    assert lease is None and not registry.production_armed
    calls = []

    def candidate(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("no adapter before original Runtime admission")

    supervisor = ExecutiveOperatorSupervisor(
        rt, claimed_adapter_factory=candidate, prompt_source=object(),
    )
    with pytest.raises(
        StateConflict, match="nonplanner V4 Skill policy is not installed",
    ):
        asyncio.run(supervisor.start_cycle_job(
            job.job_id,
            command_id=f"coo-cycle:{job.root_job_id}:dispatch:{job.job_id}:attempt:1",
        ))
    fresh = rt.jobs.get_job(job.job_id)
    assert fresh is not None and fresh.attempt_count == 0
    assert fresh.current_attempt_id is None
    assert calls == []


def test_readonly_work_refuses_synthetic_writes_or_profile_reselection(
    tmp_path, monkeypatch,
):
    rt, job, lease, registry, _profile, _source = _seed_claimed_work(tmp_path)
    assert lease is not None
    monkeypatch.setattr(ExecutionCapabilityRegistry, "load", lambda *_, **__: registry)
    supervisor = ExecutiveOperatorSupervisor(
        rt, claimed_adapter_factory=lambda *_a, **_kw: object(),
        prompt_source=object(),
    )
    for hostile in (
        dataclasses.replace(job, orchestration_role="repair"),
        dataclasses.replace(job, requested_authorities=["READ", "WRITE_BRANCH"]),
        dataclasses.replace(job, allowed_write_paths=[job.worktree]),
        dataclasses.replace(job, validation_commands=[["pytest", "-q"]]),
        dataclasses.replace(job, constraints={
            **job.constraints, "execution_profile_id":
                "operator.appserver.write.mastermind-operator.v1",
        }),
        dataclasses.replace(job, constraints={
            **job.constraints, "execution_profile_digest": "f" * 64,
        }),
    ):
        with pytest.raises(ExecutiveOperatorSupervisorError):
            supervisor._requested_profile(hostile, lease)
    attempt = rt.attempts.get_attempt(lease.attempt.attempt_id)
    assert attempt is not None and attempt.requested_execution_profile_digest is None


def test_claimed_work_profile_seals_immutably_and_uses_work_result_schema(
    tmp_path, monkeypatch,
):
    rt, job, lease, registry, _profile, _source = _seed_claimed_work(tmp_path)
    assert lease is not None
    monkeypatch.setattr(ExecutionCapabilityRegistry, "load", lambda *_, **__: registry)
    prompt_source = SimpleNamespace(_prompt=lambda *_a, **_kw: "fixture work prompt")
    supervisor = ExecutiveOperatorSupervisor(
        rt, claimed_adapter_factory=lambda *_a, **_kw: object(),
        prompt_source=prompt_source,
    )
    requested = supervisor._requested_profile(job, lease)
    prompt = supervisor._prompt(job, lease)
    assert "mastermind.work_result/v1" in prompt
    assert "fixture work prompt" in prompt
    sealed = rt.operator_harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=requested,
    )
    assert sealed.status.value == "CLAIMED"
    assert sealed.execution_mode == "OPERATOR_HARNESS"
    assert isinstance(sealed.requested_execution_profile_digest, str)
    assert len(sealed.requested_execution_profile_digest) == 64
    replay = rt.operator_harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=requested,
    )
    assert replay.requested_execution_profile_digest == sealed.requested_execution_profile_digest
    with pytest.raises(StateConflict, match="already sealed"):
        rt.operator_harness.seal_operator_harness_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            requested=dataclasses.replace(requested, requested_model="wrong-model"),
        )


def test_claimed_readonly_work_runs_through_existing_ohf_role_seal(
    tmp_path, monkeypatch,
):
    """Synthetic provider, genuine Runtime Work Job/Attempt and sealed result."""
    from test_executive_operator_supervisor import _ActiveAdapter, _PromptSource, _attestation
    from control_plane.executive_orchestration_result import (
        RESULT_SCHEMA, canonical_bytes,
    )
    from control_plane.executive_runtime import JobStatus, AttemptStatus

    rt, job, lease, registry, original_profile, _source = _seed_claimed_work(
        tmp_path, dispatch_work=False,
    )
    assert lease is None
    monkeypatch.setattr(ExecutionCapabilityRegistry, "load", lambda *_, **__: registry)
    adapters = []

    class WorkAdapter(_ActiveAdapter):
        def observed_attestation(self, generation):
            assert self.profile is not None
            return dataclasses.replace(
                _attestation(self.profile),
                effective_skills=original_profile.skills,
            )

        def _canonical_result(self, turn):
            attempt = self.runtime.attempts.get_attempt(turn.attempt_id)
            assert attempt is not None
            original_job = self.runtime.jobs.get_job(attempt.job_id)
            assert original_job is not None
            assert original_job.orchestration_role == "work"
            envelope = {
                "schema_version": RESULT_SCHEMA,
                "job_id": original_job.job_id,
                "run_id": attempt.attempt_id,
                "worker_id": attempt.worker_id,
                "role": "work",
                "status": "COMPLETED",
                "role_result": {
                    "schema_version": "mastermind.work_result/v1",
                    "root_job_id": original_job.root_job_id,
                    "plan_attempt_id": original_job.plan_attempt_id,
                    "plan_digest": original_job.plan_digest,
                    "plan_step_id": original_job.plan_step_id,
                    "repair_round": original_job.repair_round,
                    "artifacts": [],
                    "evidence_digests": [],
                },
                "summary": "Completed one exact read-only Work result fixture.",
                "current_state": "complete",
                "next_actions": [],
                "errors": [],
                "validations": [],
            }
            return canonical_bytes(envelope).decode("utf-8")

    def factory(attempt, requested, loader, *, recovery):
        assert recovery is False
        assert attempt.status.value == "CLAIMED"
        assert requested.sandbox_policy == "read-only"
        assert requested.write_capable is False
        assert tuple(x.kind for x in requested.capabilities.required).count("skill") == 4
        adapter = WorkAdapter(rt, loader, cancel_during_collect=False)
        adapters.append(adapter)
        return adapter

    supervisor = ExecutiveOperatorSupervisor(
        rt, claimed_adapter_factory=factory, prompt_source=_PromptSource(),
    )
    outcome = asyncio.run(supervisor.start_cycle_job(
        job.job_id,
        command_id=f"coo-cycle:{job.root_job_id}:dispatch:{job.job_id}:attempt:1",
    ))
    assert outcome.outcome == "TERMINAL"
    actual = rt.attempts.get_attempt(outcome.attempt.attempt_id)
    current_job = rt.jobs.get_job(job.job_id)
    assert actual is not None and actual.status is AttemptStatus.COMPLETED
    assert current_job is not None and current_job.status is JobStatus.COMPLETED
    assert actual.requested_execution_profile_digest is not None
    assert len(adapters) == 1
    assert adapters[0].begin_turn_calls == 1
    assert adapters[0].stop_calls == 1
    assert adapters[0].cancel_calls == 0
    assert "mastermind.work_result/v1" in adapters[0].prompts[0]
    with rt.store.read() as conn:
        rows = conn.execute(
            "SELECT event_type FROM events WHERE attempt_id=? AND "
            "event_type='ORCHESTRATION_ROLE_RESULT_SEALED'",
            (actual.attempt_id,),
        ).fetchall()
    assert len(rows) == 1

def test_claimed_independent_review_reuses_existing_v4_skill_identity(
    tmp_path, monkeypatch,
):
    """Actual COO Work completion and independently claimed review child."""
    from control_plane.executive_orchestration_result import canonical_digest

    rt, work, lease, registry, expected, _source = _seed_claimed_work(
        tmp_path, dispatch_work=False, review_required=True,
    )
    assert lease is None
    original = rt.workers.get_quota_class("worker-a", "codex-hf1q-step")
    assert original is not None
    rt.workers.register_worker(
        "worker-b", provider="codex", account_label="separate-review@company",
        worker_type="mock", capabilities=["read", "research"],
        quota_classes={
            "codex-hf1q-step": {
                "provider": original.provider,
                "capabilities": ["read", "research"],
                "cost_class": original.cost_class,
                "model": original.model,
                "effort": original.effort,
                "metadata": original.metadata,
            }
        },
    )
    work_dispatch = rt.attempts.dispatch_cycle_job(
        work.job_id,
        command_id=(
            f"coo-cycle:{work.root_job_id}:dispatch:"
            f"{work.job_id}:attempt:1"
        ),
        worker_id="worker-a",
        quota_class="codex-hf1q-step",
    )
    assert isinstance(work_dispatch, OrchestrationDispatchOutcome)
    work_body = {
        "schema_version": "mastermind.work_result/v1",
        "root_job_id": work.root_job_id,
        "plan_attempt_id": work.plan_attempt_id,
        "plan_digest": work.plan_digest,
        "plan_step_id": work.plan_step_id,
        "repair_round": work.repair_round,
        "artifacts": [],
        "evidence_digests": [],
    }
    _complete_ohf_role(rt, work_dispatch, work_body, identity_seed=8821)
    reviewed = rt.jobs.get_job(work.job_id)
    assert reviewed is not None and reviewed.status.value == "COMPLETED"
    review = rt.jobs.create_cycle_review(
        work.root_job_id, work.job_id,
        command_id=f"coo-cycle:{work.root_job_id}:create-review:{work.job_id}:1",
    )
    assert review.orchestration_role == "review"
    assert review.requested_authorities == ["READ"]
    assert review.worktree == work.worktree
    review_dispatch = rt.attempts.dispatch_cycle_job(
        review.job_id,
        command_id=(
            f"coo-cycle:{work.root_job_id}:dispatch:"
            f"{review.job_id}:attempt:1"
        ),
        worker_id="worker-b",
        quota_class="codex-hf1q-step",
    )
    assert isinstance(review_dispatch, OrchestrationDispatchOutcome)
    assert review_dispatch.lease_token is not None
    assert review_dispatch.attempt.worker_id == "worker-b"
    monkeypatch.setattr(ExecutionCapabilityRegistry, "load", lambda *_, **__: registry)
    supervisor = ExecutiveOperatorSupervisor(
        rt, claimed_adapter_factory=lambda *_a, **_kw: object(),
        prompt_source=SimpleNamespace(_prompt=lambda *_args, **_kwargs: "Review"),
    )
    bound = supervisor._requested_profile(
        review, AttemptLease(review_dispatch.attempt, review_dispatch.lease_token),
    )
    assert bound.write_capable is False and bound.allowed_write_paths == ()
    assert bound.capabilities == expected.capability_manifest(
        harness_binary_digest=BINARY_DIGEST,
    )
    prompt = supervisor._prompt(
        review, AttemptLease(review_dispatch.attempt, review_dispatch.lease_token),
    )
    assert "mastermind.review_result/v1" in prompt

    # Exercise the original claimed-attempt supervisor method and the real
    # review-result schema. The adapter is a fake provider, not a grant.
    from test_executive_operator_supervisor import _ActiveAdapter, _PromptSource, _attestation
    from control_plane.executive_orchestration_result import (
        RESULT_SCHEMA, canonical_bytes,
    )
    from control_plane.executive_runtime import AttemptStatus, JobStatus
    event = rt.events.get_event_by_command_id(
        f"orchestration-result-seal:{work_dispatch.attempt.attempt_id}"
    )
    assert event is not None
    work_digest = event.payload["role_result_digest"]
    reviewed_attempt_id = work_dispatch.attempt.attempt_id
    adapters = []

    class ReviewAdapter(_ActiveAdapter):
        def observed_attestation(self, generation):
            assert self.profile is not None
            return dataclasses.replace(
                _attestation(self.profile), effective_skills=expected.skills,
            )

        def _canonical_result(self, turn):
            attempt = self.runtime.attempts.get_attempt(turn.attempt_id)
            assert attempt is not None
            sealed_job = self.runtime.jobs.get_job(attempt.job_id)
            assert sealed_job is not None
            assert sealed_job.orchestration_role == "review"
            body = {
                "schema_version": "mastermind.review_result/v1",
                "root_job_id": sealed_job.root_job_id,
                "plan_attempt_id": sealed_job.plan_attempt_id,
                "plan_digest": sealed_job.plan_digest,
                "plan_step_id": sealed_job.plan_step_id,
                "reviewed_job_id": work.job_id,
                "reviewed_attempt_id": reviewed_attempt_id,
                "reviewed_result_digest": work_digest,
                "repair_round": sealed_job.repair_round,
                "verdict": "approve",
                "evidence_digests": [],
                "findings": [],
            }
            envelope = {
                "schema_version": RESULT_SCHEMA,
                "job_id": sealed_job.job_id,
                "run_id": attempt.attempt_id,
                "worker_id": attempt.worker_id,
                "role": "review",
                "status": "COMPLETED",
                "role_result": body,
                "summary": "Independently reviewed one read-only Work result.",
                "current_state": "complete",
                "next_actions": [],
                "errors": [],
                "validations": [],
            }
            return canonical_bytes(envelope).decode("utf-8")

    def factory(attempt, requested, loader, *, recovery):
        assert recovery is False
        assert attempt.worker_id == "worker-b"
        assert requested.worker_id == "worker-b"
        assert requested.write_capable is False
        assert requested.capabilities == expected.capability_manifest(
            harness_binary_digest=BINARY_DIGEST,
        )
        adapter = ReviewAdapter(rt, loader, cancel_during_collect=False)
        adapters.append(adapter)
        return adapter

    review_supervisor = ExecutiveOperatorSupervisor(
        rt,
        claimed_adapter_factory=factory,
        prompt_source=_PromptSource(),
    )
    outcome = review_supervisor._run_claimed(
        review, AttemptLease(review_dispatch.attempt, review_dispatch.lease_token),
    )
    assert outcome.outcome == "TERMINAL"
    completed = rt.attempts.get_attempt(review_dispatch.attempt.attempt_id)
    finished_review = rt.jobs.get_job(review.job_id)
    assert completed is not None and completed.status is AttemptStatus.COMPLETED
    assert finished_review is not None and finished_review.status is JobStatus.COMPLETED
    assert len(adapters) == 1
    assert adapters[0].begin_turn_calls == 1 and adapters[0].stop_calls == 1
    assert "mastermind.review_result/v1" in adapters[0].prompts[0]
    with rt.store.read() as connection:
        receipt = connection.execute(
            "SELECT event_type FROM events WHERE attempt_id=? "
            "AND event_type='ORCHESTRATION_ROLE_RESULT_SEALED'",
            (completed.attempt_id,),
        ).fetchall()
    assert len(receipt) == 1
