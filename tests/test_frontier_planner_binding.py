"""The selected CEO must join the root planner's actual admitted identity."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from control_plane import executive_runtime as runtime_module
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.executive_orchestration_result import PLAN_SCHEMA_V1, PLAN_SCHEMA_V3
from control_plane.executive_runtime import AttemptStatus, Runtime, StateConflict
from control_plane.executive_supervisor import ReconcileStatus
from control_plane.frontier_selection import resolve_selection, selection_provenance
from control_plane.model_router import ModelRouter
from control_plane.operator_harness_orchestrator import OperatorHarnessOrchestrator
from control_plane.operator_harness_contract import (
    ProcessIdentityObservation, ProcessLiveness, ProviderWriterState, ReconcileObservation,
)
from test_executive_operator_supervisor import _Clock, _PromptSource, _seed_dispatchable_operator_planner
from test_planner_producer_binding import (
    _VersionedAdapter, _claim, _created, _replace_created, _seed_bound_sealed,
)


def _selection(**changes):
    selected = resolve_selection(ModelRouter.load(), "frontier.orchestrator")
    selected.update(changes)
    return selected


def _assert_no_execution(runtime):
    assert runtime.attempts.list_attempts() == []
    with runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM harness_session_epochs").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM worker_quota_classes WHERE fence_counter!=0 OR held_attempt_id IS NOT NULL"
        ).fetchone()[0] == 0


def test_selected_ceo_joins_distinct_executable_profile_through_real_runtime(tmp_path):
    selected = _selection()
    runtime, root, planner = _seed_dispatchable_operator_planner(
        tmp_path, frontier_selection=selected, plan_schema_version=PLAN_SCHEMA_V3,
        routing_capacity=True,
    )
    original = _created(runtime, root)
    producer = runtime.jobs.get_planner_producer_binding(planner.job_id)
    assert runtime.jobs.assert_frontier_planner_execution(planner.job_id) == selected
    assert selected["worker_eligible"] is False
    assert planner.constraints["execution_profile_digest"] != selected["execution_profile_digest"]
    assert "frontier_selection" not in producer  # Original root remains the sole retention owner.
    adapters = []
    def factory(_attempt, requested, loader, *, recovery):
        assert not recovery
        assert requested.requested_model == selected["model"]
        executable = ModelRouter.load().capability_registry.resolve(planner.constraints["execution_profile_id"])
        assert requested.capabilities == executable.capability_manifest(
            harness_binary_digest=requested.harness_binary_digest,
        )
        assert requested.expected_config_digest == executable.expected_config_digest
        adapter = _VersionedAdapter(runtime, loader, PLAN_SCHEMA_V3)
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(
        runtime, claimed_adapter_factory=factory, prompt_source=_PromptSource(),
        plan_schema_version=PLAN_SCHEMA_V3,
    )
    command = f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"
    outcome = asyncio.run(supervisor.start_cycle_job(planner.job_id, command_id=command))
    assert outcome.outcome == "TERMINAL"
    assert adapters[0].start_calls == adapters[0].begin_turn_calls == 1
    assert _created(runtime, root) == original
    assert runtime.jobs.get_planner_producer_binding(planner.job_id) == producer


@pytest.mark.parametrize("change", [
    {"provider_alias": "anthropic"}, {"model": "another-frontier-model"}, {"effort": "high"},
    {"routing_policy_version": "another-routing-policy"},
    {"capability_policy_version": "another-capability-policy"},
    {"capability_policy_digest": "b" * 64},
])
def test_selected_ceo_mismatch_refuses_before_planner_insertion(tmp_path, change):
    runtime, root, _ = _seed_dispatchable_operator_planner(
        tmp_path, create_planner=False, frontier_selection=_selection(**change),
    )
    with pytest.raises(StateConflict, match="selected CEO"):
        runtime.jobs.create_cycle_planner(
            root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0",
            plan_schema_version=PLAN_SCHEMA_V3,
        )
    assert [job.job_id for job in runtime.jobs.list_jobs()] == [root.job_id]
    _assert_no_execution(runtime)


@pytest.mark.parametrize("armed,version", [(False, PLAN_SCHEMA_V3), (True, None)])
def test_selected_ceo_requires_armed_lane_and_retained_native_producer(tmp_path, armed, version):
    runtime, root, _ = _seed_dispatchable_operator_planner(
        tmp_path, create_planner=False, frontier_selection=_selection(),
        operator_harness_armed=armed,
    )
    with pytest.raises(StateConflict, match="selected CEO"):
        runtime.jobs.create_cycle_planner(
            root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0",
            plan_schema_version=version,
        )
    assert len(runtime.jobs.list_jobs()) == 1
    _assert_no_execution(runtime)


def test_selected_ceo_partial_root_provenance_never_becomes_legacy_omission(tmp_path):
    runtime, root, _ = _seed_dispatchable_operator_planner(
        tmp_path, create_planner=False, frontier_selection=_selection(),
    )
    payload = _created(runtime, root)
    del payload["provenance"]["frontier_selection_digest"]
    _replace_created(runtime, root, payload)
    with pytest.raises(StateConflict, match="selected CEO"):
        runtime.jobs.create_cycle_planner(
            root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0",
            plan_schema_version=PLAN_SCHEMA_V3,
        )
    assert len(runtime.jobs.list_jobs()) == 1
    _assert_no_execution(runtime)


def test_historical_command_replay_is_preserved_but_mismatched_fresh_claim_refuses(tmp_path, monkeypatch):
    # Represent a predecessor that admitted a selection and planner independently.
    with monkeypatch.context() as predecessor:
        predecessor.setattr(runtime_module, "_assert_root_frontier_planner_join",
                            lambda *a, **k: None, raising=False)
        runtime, root, planner = _seed_dispatchable_operator_planner(
            tmp_path, frontier_selection=_selection(model="historically-requested-model"),
            plan_schema_version=PLAN_SCHEMA_V3,
        )
    producer = runtime.jobs.get_planner_producer_binding(planner.job_id)
    reopened = Runtime.at(tmp_path / "runtime")
    replay = reopened.jobs.create_cycle_planner(
        root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    assert replay.job_id == planner.job_id
    assert reopened.jobs.get_planner_producer_binding(planner.job_id) == producer
    with pytest.raises(StateConflict, match="selected CEO"):
        _claim(reopened, root, planner)
    _assert_no_execution(reopened)


def test_selected_ceo_cannot_fall_back_to_available_sealed_capacity(tmp_path, monkeypatch):
    with monkeypatch.context() as predecessor:
        predecessor.setattr(runtime_module, "_assert_root_frontier_planner_join",
                            lambda *a, **k: None, raising=False)
        runtime, root, planner = _seed_dispatchable_operator_planner(
            tmp_path, frontier_selection=_selection(), operator_harness_armed=False,
            routing_capacity=True,
        )
    with pytest.raises(StateConflict, match="selected CEO"):
        runtime.attempts.dispatch_cycle_job(
            planner.job_id,
            command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
            worker_id="routing-worker",
        )
    _assert_no_execution(runtime)


def test_selected_ceo_is_rechecked_after_adapter_construction(tmp_path):
    runtime, root, planner = _seed_dispatchable_operator_planner(
        tmp_path, frontier_selection=_selection(), plan_schema_version=PLAN_SCHEMA_V3,
    )
    lease = _claim(runtime, root, planner)
    calls = []
    def factory(_attempt, _requested, _loader, *, recovery):
        calls.append("construct")
        assert not recovery
        payload = _created(runtime, root)
        payload["provenance"].update(selection_provenance(
            "frontier.orchestrator", _selection(model="changed-during-construction"),
        ))
        _replace_created(runtime, root, payload)
        return SimpleNamespace(plan_contract="executive-plan-v3")
    supervisor = ExecutiveOperatorSupervisor(
        runtime, claimed_adapter_factory=factory, prompt_source=_PromptSource(),
        plan_schema_version=PLAN_SCHEMA_V3,
    )
    requested = supervisor._requested_profile(planner, lease)
    with pytest.raises(StateConflict, match="selected CEO"):
        supervisor._adapter_for_attempt(lease, requested, lambda _turn: "", recovery=False)
    assert calls == ["construct"]
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id).status is AttemptStatus.CLAIMED
    with runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM harness_session_epochs").fetchone()[0] == 0


def test_sealed_predecessor_result_recovery_does_not_require_new_selection_admission(tmp_path, monkeypatch):
    with monkeypatch.context() as predecessor:
        predecessor.setattr(runtime_module, "_assert_root_frontier_planner_join",
                            lambda *a, **k: None, raising=False)
        clock, runtime, _root, planner, attempt, retained = _seed_bound_sealed(
            tmp_path, predecessor, frontier_selection=_selection(model="historically-requested-model"),
        )
    producer = runtime.jobs.get_planner_producer_binding(planner.job_id)
    reopened = Runtime.at(tmp_path / "runtime", clock=clock)
    with pytest.raises(StateConflict, match="selected CEO"):
        reopened.jobs.assert_frontier_planner_execution(planner.job_id)
    adapters = []
    def factory(_attempt, requested, loader, *, recovery):
        assert recovery and requested == retained["session"].launch.requested
        adapter = _VersionedAdapter(reopened, loader, PLAN_SCHEMA_V1)
        adapter.profile = requested
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(
        reopened, claimed_adapter_factory=factory, prompt_source=_PromptSource(),
    )
    assert [outcome.status for outcome in supervisor.reconcile_restart()] == [ReconcileStatus.OPERATOR_RECOVERED]
    adapter = adapters[0]
    assert adapter.start_calls == adapter.resume_calls == adapter.begin_turn_calls == adapter.read_calls == 0
    assert adapter.stop_calls == 1
    assert reopened.attempts.get_attempt(attempt.attempt_id).status is AttemptStatus.COMPLETED
    assert reopened.jobs.get_planner_producer_binding(planner.job_id) == producer


@pytest.mark.parametrize("live_existing", [True, False])
@pytest.mark.parametrize("selection_matches", [True, False])
def test_unsealed_restart_checks_choice_before_any_fresh_turn_or_resume(
    tmp_path, monkeypatch, live_existing, selection_matches,
):
    class CrashBeforeResult(BaseException):
        pass

    class InitialAdapter(_VersionedAdapter):
        def read_events(self, *args, **kwargs):
            raise CrashBeforeResult()

    clock, retained, initial_adapters = _Clock(), {}, []
    selected = _selection(**({} if selection_matches else {"model": "historically-requested-model"}))
    with monkeypatch.context() as predecessor:
        predecessor.setattr(runtime_module, "_assert_root_frontier_planner_join",
                            lambda *a, **k: None, raising=False)
        runtime, root, planner = _seed_dispatchable_operator_planner(
            tmp_path, clock=clock, frontier_selection=selected,
            plan_schema_version=PLAN_SCHEMA_V3, routing_capacity=True,
        )
        def factory(_attempt, _requested, loader, *, recovery):
            assert not recovery
            adapter = InitialAdapter(runtime, loader, PLAN_SCHEMA_V3)
            initial_adapters.append(adapter)
            return adapter
        supervisor = ExecutiveOperatorSupervisor(
            runtime, claimed_adapter_factory=factory, prompt_source=_PromptSource(),
            plan_schema_version=PLAN_SCHEMA_V3,
        )
        run_turn = OperatorHarnessOrchestrator.run_turn
        def interrupt(orchestrator, session, **kwargs):
            retained["session"] = session
            if live_existing:
                raise CrashBeforeResult()
            # A resumable dead G1 must retain its original TX-5 intent.
            return run_turn(orchestrator, session, **kwargs)
        predecessor.setattr(OperatorHarnessOrchestrator, "run_turn", interrupt)
        with pytest.raises(CrashBeforeResult):
            asyncio.run(supervisor.start_cycle_job(
                planner.job_id,
                command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
            ))
    session = retained["session"]
    attempt = runtime.attempts.get_attempt(session.attempt_id)
    assert attempt.status is AttemptStatus.RUNNING
    assert initial_adapters[0].start_calls == 1
    assert initial_adapters[0].begin_turn_calls == (0 if live_existing else 1)
    assert initial_adapters[0].stop_calls == 0
    assert runtime.events.get_event_by_command_id(f"orchestration-result-seal:{attempt.attempt_id}") is None
    clock.advance(1000)
    reopened, adapters = Runtime.at(tmp_path / "runtime", clock=clock), []

    class RecoveryAdapter(_VersionedAdapter):
        def reconcile(self, generation):
            if live_existing:
                return super().reconcile(generation)
            return ReconcileObservation(
                ProcessLiveness.PROVEN_DEAD, self.process, False,
                ProviderWriterState.RELEASED, self.provider_session_id,
                self.profile.expected_config_digest,
            )

        def resume_session(self, **kwargs):
            self.process = ProcessIdentityObservation(3202, 3202, "start-3202", "boot-test")
            return super().resume_session(**kwargs)

    def recovery_factory(_attempt, requested, loader, *, recovery):
        assert recovery and requested == session.launch.requested
        adapter = RecoveryAdapter(reopened, loader, PLAN_SCHEMA_V3)
        adapter.profile = requested
        adapters.append(adapter)
        return adapter

    supervisor = ExecutiveOperatorSupervisor(
        reopened, claimed_adapter_factory=recovery_factory, prompt_source=_PromptSource(),
        plan_schema_version=PLAN_SCHEMA_V3,
    )
    outcomes = supervisor.reconcile_restart()
    if selection_matches:
        assert [item.status for item in outcomes] == [ReconcileStatus.OPERATOR_RECOVERED]
        assert len(adapters) == 1
        assert adapters[0].start_calls == 0
        assert adapters[0].resume_calls == (0 if live_existing else 1)
        assert adapters[0].begin_turn_calls == adapters[0].read_calls == adapters[0].stop_calls == 1
        assert reopened.attempts.get_attempt(attempt.attempt_id).status is AttemptStatus.COMPLETED
    else:
        assert [item.status for item in outcomes] == [ReconcileStatus.IDENTITY_AMBIGUOUS]
        assert adapters == []
        assert reopened.attempts.get_attempt(attempt.attempt_id).status is AttemptStatus.RUNNING
        with reopened.store.read() as connection:
            assert connection.execute("SELECT COUNT(*) FROM harness_session_epochs").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM process_generations").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM process_generations WHERE executive_writer_held=1").fetchone()[0] == 1
