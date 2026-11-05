"""The real Runtime/COO timer-to-work path, with inert execution boundaries."""
from __future__ import annotations

import asyncio
import dataclasses
import json
from types import SimpleNamespace

import pytest

from control_plane import coo_observation as observation
from control_plane.executive_authority import ExecutiveAuthorityPolicy
from control_plane.executive_coo_cycle import CooCycle, CooCycleOutcome, _ReviewCapacityPressure
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.executive_orchestration_result import canonical_digest
from control_plane.executive_runtime import (
    JobStatus, ObservationUnavailable, Runtime, StateConflict,
)
from control_plane.executive_service import ExecutiveControlService
from control_plane.executive_supervisor import ExecutiveSupervisor, _planner_routing_options
from test_coo_observation import spec
from test_executive_operator_supervisor import (
    _PromptSource, _seed_dispatchable_operator_planner,
)
from test_native_plan_v3_optin import _ObservationPlanAdapter
from test_executive_os_phase1fc import _complete_ohf_role
from test_executive_service import _config, _coo_intent, _request, _service
from test_executive_coo_tick_liveness import _prepared_pair, _children, _until


def _prepared(tmp_path, *, sibling=False, review_sibling=False, admit=True, host=None):
    clock = [1_800_000_000_000]
    version = "mastermind.execution_plan/v6"
    runtime, root, planner = _seed_dispatchable_operator_planner(
        tmp_path, clock=lambda: clock[0], plan_schema_version=version, routing_capacity=True)
    step = {"ordinal": 0, "step_id": "timer-step", "objective": "Consume bounded timer evidence.",
            "business_impact": "routine", "review_required": False, "requested_authorities": ["READ"],
            "allowed_write_paths": [], "validation_ids": [], "attempt_limit": 1, "cost_class": "small",
            "placement": {"provider_realm": "codex", "quota_class": "codex-coo"},
            "prerequisite_step_ids": [], "observation_gate": spec(clock[0] + 1000, clock[0] + 10000)}
    steps = [step]
    if sibling:
        steps.append(dict(step, ordinal=1, step_id="ready-sibling", observation_gate=None,
                          review_required=review_sibling))
    plan = {}

    class Adapter(_ObservationPlanAdapter):
        def _canonical_result(self, turn):
            envelope = json.loads(super()._canonical_result(turn))
            envelope["role_result"]["steps"] = steps
            plan.update(envelope["role_result"])
            return json.dumps(envelope, sort_keys=True, separators=(",", ":"))

    supervisor = ExecutiveOperatorSupervisor(runtime,
        claimed_adapter_factory=lambda attempt, requested, loader, recovery: Adapter(runtime, loader, version),
        prompt_source=_PromptSource(), plan_schema_version=version)
    dispatch = asyncio.run(supervisor.start_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"))
    assert dispatch.outcome == "TERMINAL"
    command = f"coo-cycle:{root.job_id}:admit-plan:{dispatch.attempt.attempt_id}"
    host = host or observation.TimerObservationHost("test-executive")
    members = runtime.jobs.admit_cycle_plan(root.job_id, command_id=command,
                                           observation_host=host) if admit else []
    return SimpleNamespace(runtime=runtime, root=root, planner=planner, dispatch=dispatch,
        plan=plan, clock=clock, host=host, command=command, members=members, path=tmp_path / "runtime")


def _cycle(case):
    return CooCycle(case.runtime, observation_host=case.host,
        dispatcher=lambda job_id, command_id: case.runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id))


def _counts(runtime):
    with runtime.store.read() as connection:
        return tuple(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                     for table in ("jobs", "attempts", "events"))


def _create(case, manifest=None):
    manifest = manifest or case.runtime.jobs.project_cycle_work_dependency_manifest(
        case.root.job_id, "timer-step")
    command = (f"coo-cycle:{case.root.job_id}:create-work:timer-step:"
               f"{manifest['dependency_manifest_digest']}")
    return case.runtime.jobs.create_cycle_work(case.root.job_id, "timer-step",
        dependency_manifest=manifest, command_id=command, observation_host=case.host)


def test_pending_has_no_work_attempt_or_writes_and_does_not_block_root(tmp_path):
    case = _prepared(tmp_path)
    assert case.members == []
    before = _counts(case.runtime)
    for _ in range(2):
        outcome = _cycle(case).run_once(case.root.job_id)
        assert outcome.action == "NO_ACTION" and outcome.receipt["reason"] == "observation_pending"
        assert _counts(case.runtime) == before
    assert not any(event.event_type == "COO_CYCLE_BLOCKED"
                   for event in case.runtime.events.list_events(job_id=case.root.job_id))


def test_pending_does_not_hold_independent_ready_sibling(tmp_path):
    case = _prepared(tmp_path, sibling=True)
    assert [job.plan_step_id for job in case.members] == ["ready-sibling"]
    outcome = _cycle(case).run_once(case.root.job_id)
    assert outcome.action == "DISPATCHED"
    assert outcome.selected_job_id == case.members[0].job_id
    assert not any(job.plan_step_id == "timer-step" for job in case.runtime.jobs.list_jobs())


def test_due_reopen_materializes_once_and_actual_prompt_consumes_evidence(tmp_path):
    case = _prepared(tmp_path)
    case.runtime = Runtime.at(case.path, clock=lambda: case.clock[0])
    assert _cycle(case).run_once(case.root.job_id).receipt["reason"] == "observation_pending"
    case.clock[0] += 1000
    first = _cycle(case).run_once(case.root.job_id)
    assert first.action == "OBSERVATION_RECORDED" and first.receipt["disposition"] == "MATERIAL"
    case.runtime = Runtime.at(case.path, clock=lambda: case.clock[0])
    case.clock[0] += 20000  # Acquisition deadline does not invalidate historical evidence.
    replay = case.runtime.jobs.advance_cycle_observation(case.root.job_id, "timer-step", observation_host=None)
    assert replay["created"] is False and replay["event_id"] == first.receipt["event_id"]
    manifest = case.runtime.jobs.project_cycle_work_dependency_manifest(case.root.job_id, "timer-step")
    work = _create(case, manifest)
    assert _create(case, manifest).job_id == work.job_id
    outcome = _cycle(case).run_once(case.root.job_id)
    assert outcome.action == "DISPATCHED" and outcome.selected_job_id == work.job_id
    current = case.runtime.jobs.get_job(work.job_id)
    attempt = case.runtime.attempts.get_attempt(current.current_attempt_id)
    value = case.runtime.jobs.read_cycle_observation_input(work.job_id, attempt.attempt_id)
    assert value["evidence"] == first.receipt["record"]
    assert value["observation"]["event_id"] == first.receipt["event_id"]
    supervisor = ExecutiveSupervisor(case.runtime, SimpleNamespace(inspector=object()))
    prompt = supervisor._prompt(current, attempt)
    assert observation.INPUT_SCHEMA in prompt
    assert first.receipt["record"]["evidence_digest"] in prompt
    assert '"observed_at_ms": 1800000001000' in prompt
    with pytest.raises(StateConflict, match="Attempt"):
        case.runtime.jobs.read_cycle_observation_input(work.job_id, case.dispatch.attempt.attempt_id)
    with pytest.raises(StateConflict, match="byte budget"):
        case.runtime.jobs.read_cycle_observation_input(work.job_id, attempt.attempt_id, max_bytes=10)
    events = case.runtime.events.list_events(job_id=case.root.job_id)
    assert sum(event.event_type == observation.EVENT_TYPE for event in events) == 1
    assert len([job for job in case.runtime.jobs.list_jobs() if job.plan_step_id == "timer-step"]) == 1


def test_missing_host_refuses_plan_without_partial_admission(tmp_path):
    case = _prepared(tmp_path, admit=False)
    before = _counts(case.runtime)
    with pytest.raises(ObservationUnavailable):
        case.runtime.jobs.admit_cycle_plan(case.root.job_id, command_id=case.command)
    assert _counts(case.runtime) == before
    outcome = CooCycle(case.runtime).run_once(case.root.job_id)
    assert outcome.action == "NO_ACTION" and outcome.receipt["reason"] == "observation_host_unavailable"
    assert _counts(case.runtime) == before


def test_expiry_stays_unsatisfied_and_never_creates_work(tmp_path):
    case = _prepared(tmp_path)
    case.clock[0] += 10000
    out = _cycle(case).run_once(case.root.job_id)
    assert out.action == "OBSERVATION_RECORDED" and out.receipt["disposition"] == "EXPIRED"
    before = _counts(case.runtime)
    assert _cycle(case).run_once(case.root.job_id).receipt["reason"] == "observation_unsatisfied"
    with pytest.raises(StateConflict, match="not satisfied"):
        _create(case)
    assert _counts(case.runtime) == before


def test_host_absent_after_evidence_is_temporary_and_resumes_same_work(tmp_path):
    case = _prepared(tmp_path)
    case.clock[0] += 1000
    first = _cycle(case).run_once(case.root.job_id)
    assert first.action == "OBSERVATION_RECORDED"
    case.runtime = Runtime.at(case.path, clock=lambda: case.clock[0])
    before = _counts(case.runtime)
    waiting = CooCycle(case.runtime).run_once(case.root.job_id)
    assert waiting.action == "NO_ACTION"
    assert waiting.receipt["observations"]["timer-step"]["reason"] == "observation_host_unavailable"
    assert _counts(case.runtime) == before
    resumed = _cycle(case).run_once(case.root.job_id)
    assert resumed.action == "WORK_CREATED"
    events = case.runtime.events.list_events(job_id=case.root.job_id)
    assert sum(event.event_type == observation.EVENT_TYPE for event in events) == 1
    assert not any(event.event_type == "COO_CYCLE_BLOCKED" for event in events)


def test_host_absent_after_evidence_still_allows_ready_sibling(tmp_path):
    case = _prepared(tmp_path, sibling=True)
    case.clock[0] += 1000
    assert _cycle(case).run_once(case.root.job_id).action == "OBSERVATION_RECORDED"
    cycle = CooCycle(case.runtime, dispatcher=lambda job_id, command_id:
        case.runtime.attempts.dispatch_cycle_job(job_id, command_id=command_id))
    outcome = cycle.run_once(case.root.job_id)
    assert outcome.action == "DISPATCHED" and outcome.selected_job_id == case.members[0].job_id
    assert not any(job.plan_step_id == "timer-step" for job in case.runtime.jobs.list_jobs())


def _review_pressure_case(tmp_path):
    case = _prepared(tmp_path, sibling=True, review_sibling=True)
    target = case.members[0]
    work = case.runtime.attempts.dispatch_cycle_job(target.job_id,
        command_id=f"coo-cycle:{case.root.job_id}:dispatch:{target.job_id}:attempt:1")
    _complete_ohf_role(case.runtime, work, {"schema_version": "mastermind.work_result/v1",
        "root_job_id": case.root.job_id, "plan_attempt_id": case.dispatch.attempt.attempt_id,
        "plan_digest": canonical_digest(case.plan), "plan_step_id": target.plan_step_id,
        "repair_round": 0, "artifacts": [], "evidence_digests": []}, identity_seed=8810)
    review = case.runtime.jobs.create_cycle_review(case.root.job_id, target.job_id,
        command_id=f"coo-cycle:{case.root.job_id}:create-review:{target.job_id}:1")
    case.clock[0] += 1000
    return case, review


def test_preclaim_review_pressure_records_materializes_then_dispatches_independent_gate(tmp_path):
    case, review = _review_pressure_case(tmp_path)
    calls = []

    def dispatch(job_id, command_id):
        calls.append(job_id)
        if job_id == review.job_id:
            return None
        return case.runtime.attempts.dispatch_cycle_job(job_id, command_id=command_id)

    cycle = CooCycle(case.runtime, observation_host=case.host, dispatcher=dispatch)
    before = _counts(case.runtime)
    assert cycle.run_once(case.root.job_id).action == "OBSERVATION_RECORDED"
    assert calls == [review.job_id]
    assert _counts(case.runtime) == (before[0], before[1], before[2] + 1)
    calls.clear()
    created = cycle.run_once(case.root.job_id)
    assert created.action == "WORK_CREATED" and calls == [review.job_id]
    calls.clear()
    started = cycle.run_once(case.root.job_id)
    assert started.action == "DISPATCHED" and started.selected_job_id == created.selected_job_id
    assert calls == [review.job_id, created.selected_job_id]
    assert case.runtime.jobs.get_job(review.job_id).attempt_count == 0
    assert case.runtime.jobs.pending_cycle_dispatch_effect_unknown(case.root.job_id) is None


def _register_independent_reviewer(case, review):
    constraints = review.constraints
    case.runtime.workers.register_worker("independent-reviewer", provider=constraints["provider"],
        account_label="independent-reviewer@company", worker_type="fixture",
        capabilities=["read", "research"], quota_classes={"codex-coo": {
            "provider": constraints["provider"], "model": constraints["model"],
            "effort": constraints["effort"], "cost_class": constraints["cost_class"],
            "capabilities": ["read", "research"], "metadata": {key: constraints[key]
                for key in ("routing_policy_version", "execution_profile_id", "execution_profile_digest",
                            "capability_policy_version", "capability_policy_digest")},
        }})


@pytest.mark.parametrize("raises", [False, True])
def test_review_claim_uncertainty_prevents_timer_acquisition(tmp_path, raises):
    case, review = _review_pressure_case(tmp_path)
    _register_independent_reviewer(case, review)
    calls = []

    def lost(job_id, command_id):
        assert job_id == review.job_id
        calls.append(job_id)
        receipt = case.runtime.attempts.dispatch_cycle_job(job_id, command_id=command_id,
            worker_id="independent-reviewer", quota_class="codex-coo")
        assert receipt is not None
        if raises:
            raise RuntimeError("synthetic response loss")
        return None

    with pytest.raises((StateConflict, RuntimeError)):
        CooCycle(case.runtime, observation_host=case.host, dispatcher=lost).run_once(case.root.job_id)
    assert calls == [review.job_id]
    assert case.runtime.jobs.pending_cycle_dispatch_effect_unknown(case.root.job_id) is not None
    assert not any(event.event_type == observation.EVENT_TYPE
                   for event in case.runtime.events.list_events(job_id=case.root.job_id))


def test_accepted_prerequisite_does_not_inherit_unrelated_review_capacity_pressure(tmp_path):
    case, review = _review_pressure_case(tmp_path)
    target = case.runtime.jobs.get_job(review.reviews_job_id)
    # Exercise the scheduling seam with retained-state-shaped inert projections.
    # A real two-review-plus-gate plan exceeds the current 17-child reservation
    # budget; this test must not weaken that production policy to reach a branch.
    accepted = dataclasses.replace(target, job_id="JOB-ACCEPTED-FIXTURE", plan_step_id="accepted-before")
    approved = dataclasses.replace(review, job_id="JOB-APPROVED-FIXTURE", status=JobStatus.COMPLETED,
        reviews_job_id=accepted.job_id, plan_step_id=accepted.plan_step_id)
    children = [job for job in case.runtime.jobs.list_jobs() if job.parent_job_id == case.root.job_id]
    children.extend([accepted, approved])
    current = {job.plan_step_id: {"current_job_id": job.job_id, "review_required": True}
               for job in (target, accepted)}
    admission = next(event.payload for event in case.runtime.events.list_events(job_id=case.root.job_id)
                     if event.event_type == "COO_PLAN_ADMITTED")
    before = _counts(case.runtime)
    calls = []
    cycle = CooCycle(case.runtime, dispatcher=lambda job_id, command: calls.append(job_id))
    pressure = cycle._drain_current_reviews(case.root.job_id, children, current,
        {"ready-sibling": 1, "accepted-before": 2}, case.plan, admission["policy_sha"])
    assert isinstance(pressure, _ReviewCapacityPressure)
    assert calls == [review.job_id] and _counts(case.runtime) == before
    gate = dict(case.plan["steps"][0], prerequisite_step_ids=["accepted-before"])
    assert pressure.allows_observation_step(gate)
    assert not pressure.allows_observation_step(dict(gate, prerequisite_step_ids=[target.plan_step_id]))


def test_cancelled_root_cannot_satisfy_gate(tmp_path):
    case = _prepared(tmp_path)
    case.runtime.jobs.cancel_job(case.root.job_id)
    case.clock[0] += 1000
    before = _counts(case.runtime)
    result = case.runtime.jobs.advance_cycle_observation(case.root.job_id, "timer-step",
                                                       observation_host=case.host)
    assert result["disposition"] == "CANCELLED" and not result["created"]
    assert _counts(case.runtime) == before


def test_host_and_current_authority_drift_refuse_fresh_effects(tmp_path, monkeypatch):
    case = _prepared(tmp_path)
    case.clock[0] += 1000
    before = _counts(case.runtime)
    with pytest.raises(StateConflict, match="binding changed"):
        case.runtime.jobs.advance_cycle_observation(case.root.job_id, "timer-step",
            observation_host=observation.TimerObservationHost("another-host"))
    assert _counts(case.runtime) == before
    policy = ExecutiveAuthorityPolicy.load()
    monkeypatch.setattr(ExecutiveAuthorityPolicy, "load", classmethod(lambda cls, path=None:
        dataclasses.replace(policy, sha256="9" * 64)))
    with pytest.raises(StateConflict, match="policy drifted"):
        case.runtime.jobs.advance_cycle_observation(case.root.job_id, "timer-step", observation_host=case.host)
    assert _counts(case.runtime) == before


def test_historical_replay_survives_policy_drift_but_new_work_does_not(tmp_path, monkeypatch):
    case = _prepared(tmp_path); case.clock[0] += 1000
    result = case.runtime.jobs.advance_cycle_observation(case.root.job_id, "timer-step", observation_host=case.host)
    policy = ExecutiveAuthorityPolicy.load()
    monkeypatch.setattr(ExecutiveAuthorityPolicy, "load", classmethod(lambda cls, path=None:
        dataclasses.replace(policy, sha256="9" * 64)))
    replay = case.runtime.jobs.advance_cycle_observation(case.root.job_id, "timer-step", observation_host=None)
    assert replay["record"] == result["record"] and not replay["created"]
    with pytest.raises(StateConflict, match="policy drifted"):
        _create(case)


def test_coherently_altered_manifest_does_not_create_work(tmp_path):
    case = _prepared(tmp_path); case.clock[0] += 1000
    case.runtime.jobs.advance_cycle_observation(case.root.job_id, "timer-step", observation_host=case.host)
    manifest = case.runtime.jobs.project_cycle_work_dependency_manifest(case.root.job_id, "timer-step")
    manifest["observation"]["event_id"] += 1
    manifest.pop("dependency_manifest_digest")
    manifest["dependency_manifest_digest"] = canonical_digest(manifest)
    before = _counts(case.runtime)
    with pytest.raises(StateConflict, match="no longer current"):
        _create(case, manifest)
    assert _counts(case.runtime) == before


def test_v6_prompt_does_not_advertise_v5_delegation_or_model_override(tmp_path):
    case = _prepared(tmp_path, admit=False)
    options = _planner_routing_options(case.runtime, case.planner)
    assert options["plan_schema"] == "mastermind.execution_plan/v6"
    assert options["fixed_placements"] and options["observation_source_kinds"] == ["timer"]
    assert "hierarchy" not in options and "manual_override_plan_schema" not in options


def test_service_observations_are_explicit_and_do_not_select_a_producer(tmp_path):
    config = _config(tmp_path)
    service = ExecutiveControlService(config)
    assert service._observation_host is None
    with pytest.raises(ValueError, match="armed service"):
        ExecutiveControlService(config, observation_host=observation.TimerObservationHost("host"))
    with pytest.raises(ValueError, match="armed COO"):
        dataclasses.replace(config, coo_observations_armed=True)
    armed = dataclasses.replace(config, coo_autonomy_armed=True, coo_observations_armed=True)
    first = ExecutiveControlService(armed, autonomy_guard=lambda: None)
    second = ExecutiveControlService(armed, autonomy_guard=lambda: None)
    assert first._observation_host == second._observation_host
    assert isinstance(first._observation_host, observation.TimerObservationHost)


@pytest.mark.parametrize("change", [
    {"requested_authorities": ["READ", "WRITE"]},
    {"requested_authorities": ["READ", "RUN_TESTS"]},
    {"allowed_write_paths": ["src/"]}, {"validation_ids": ["unit"]},
    {"step_id": "review-target"}, {"prerequisite_step_ids": ["review-target"]},
])
def test_review_capacity_never_widens_a_non_read_or_coupled_step(change):
    pressure = _ReviewCapacityPressure(
        CooCycleOutcome("root", "NO_ACTION", None, None, {}), frozenset({"review-target"}))
    step = {"step_id": "independent", "observation_gate": {},
            "requested_authorities": ["READ"], "allowed_write_paths": [],
            "validation_ids": [], "prerequisite_step_ids": []}
    assert pressure.allows_observation_step(step)
    assert not pressure.allows_observation_step(dict(step, **change))


@pytest.mark.parametrize("reason", ["observation_pending", "observation_unsatisfied"])
def test_existing_selector_rotates_multiple_parked_roots_without_a_new_queue(tmp_path, reason):
    async def exercise():
        async with _prepared_pair(tmp_path) as (config, service, ids, _):
            intent = _coo_intent(config, "third-parked-root")
            intent["priority"] = 7
            third = await _request(service, "submit-ceo-intent", {"intent": intent})
            assert third["ok"]
            ids.append(third["result"]["job_id"])
            before = _counts(service.runtime)
            for current, following in zip(ids, [ids[1], ids[2], ids[0]]):
                # Scheduling hints intentionally carry no authority. The real
                # selector must still qualify all three admitted service roots.
                service._coo_last_outcome = CooCycleOutcome(current, "NO_ACTION", None, None,
                    {"reason": reason}).to_dict()
                assert service._next_bound_coo_root(previous_root_id=current) == following
            assert _counts(service.runtime) == before
            service._coo_last_outcome = CooCycleOutcome(ids[0], "NO_ACTION", None, None,
                {"reason": "unrelated"}).to_dict()
            assert service._next_bound_coo_root(previous_root_id=ids[0]) == ids[0]
    asyncio.run(exercise())


def test_background_tick_advances_ready_root_between_timer_waits(tmp_path):
    async def exercise():
        async with _prepared_pair(tmp_path) as (config, seed, ids, _):
            await seed.close()
            finish_gate = asyncio.Event()
            running, _ = _service(tmp_path, config=dataclasses.replace(config,
                coo_tick_interval_seconds=1.0, shutdown_grace_seconds=3.0), finish_gate=finish_gate)
            await running.start()
            seen = []
            actual = running._run_coo_cycle

            async def cycle(root_id):
                seen.append(root_id)
                if root_id == ids[0]:
                    outcome = CooCycleOutcome(root_id, "NO_ACTION", None, None,
                        {"reason": "observation_pending"})
                    running._coo_last_outcome = outcome.to_dict()
                    return outcome
                return await actual(root_id)

            running._run_coo_cycle = cycle
            try:
                assert await _until(lambda: len(seen) >= 3, timeout=6.0)
                assert seen[:3] == [ids[0], ids[1], ids[0]]
                assert _children(running, ids[1])
                assert running.runtime.jobs.get_job(ids[0]).attempt_count == 0
                assert running.runtime.jobs.validated_cycle_block(ids[0]) is None
            finally:
                finish_gate.set()
                await running.close()
    asyncio.run(exercise())
