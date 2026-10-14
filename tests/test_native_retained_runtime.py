"""Retained native turns reuse Runtime/OHF; providers remain inert here."""
import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.executive_runtime import AttemptLease, JobStatus, StateConflict, _interactive_tx5_admitted
from control_plane.operator_harness_contract import OperationId, TurnStartObservation, ReconcileObservation, ProcessLiveness, ProviderWriterState
from tests.test_executive_operator_supervisor import _ActiveAdapter, _PromptSource, _seed_dispatchable_operator_planner

NATIVE_PROFILE = "operator.appserver.interactive.native-return.v1"


def _case(tmp_path, *, interactive=True):
    return _seed_dispatchable_operator_planner(
        tmp_path, operator_model_alias="coo.operator.native-return",
        interactive_operator=interactive)


def test_explicit_native_interactive_creation_preserves_the_sealed_root_profile(tmp_path):
    runtime, root, planner = _case(tmp_path)
    assert planner.constraints["execution_profile_id"] == NATIVE_PROFILE
    assert planner.constraints["execution_profile_digest"] == root.constraints["operator_execution_profile_digest"]
    with runtime.store.read() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (planner.job_id,)).fetchone()
        assert _interactive_tx5_admitted(row) is True


def test_ordinary_native_planner_does_not_acquire_retained_turn_authority(tmp_path):
    runtime, root, planner = _case(tmp_path, interactive=False)
    with runtime.store.read() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (planner.job_id,)).fetchone()
        assert _interactive_tx5_admitted(row) is False


def test_native_interactive_child_remains_outside_one_shot_coo_dispatch(tmp_path):
    runtime, root, planner = _case(tmp_path)
    outcome = CooCycle(runtime).run_once(root.job_id)
    assert outcome.action == "NO_ACTION"
    assert outcome.receipt["reason"] == "interactive_profile_not_owned_by_one_shot_cycle"
    assert runtime.attempts.list_attempts() == []


def test_bounded_native_return_cannot_admit_children_that_need_a_retained_parent(tmp_path):
    runtime, supervisor, retained, _adapter = _retained(tmp_path)
    before = runtime.events.list_events()
    with pytest.raises(StateConflict, match="bounded native return"):
        runtime.jobs.admit_cycle_plan(retained.job.root_job_id,
            command_id=f"coo-cycle:{retained.job.root_job_id}:admit-plan:{retained.session.attempt_id}")
    assert runtime.events.list_events() == before
    assert len(runtime.jobs.list_jobs()) == 2


def test_native_retained_first_seal_and_followup_use_the_same_current_writer(tmp_path):
    runtime, root, planner = _case(tmp_path)
    dispatch = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1")
    assert dispatch is not None and dispatch.lease_token
    lease = AttemptLease(dispatch.attempt, dispatch.lease_token)
    adapter = _ActiveAdapter(runtime, lambda _: "Bounded inert instruction; output schema", cancel_during_collect=False)
    supervisor = ExecutiveOperatorSupervisor(runtime, adapter_factory=lambda _: adapter, prompt_source=_PromptSource())
    requested = supervisor._requested_profile(planner, lease)
    driver = supervisor._orchestrator(lease, adapter)
    session = driver.start_attempt(attempt_id=lease.attempt.attempt_id,
        requested=requested, operation_id=OperationId("ohf-op:native-retained:start"))
    first = driver.run_turn(session, operation_id=OperationId("ohf-op:native-retained:plan"))
    before = runtime.events.get_event_by_command_id(f"orchestration-result-seal:{session.attempt_id}")
    second = driver.run_turn(session, operation_id=OperationId("ohf-op:native-retained:followup"))
    assert first.turn.turn_id != second.turn.turn_id
    assert runtime.events.get_event_by_command_id(f"orchestration-result-seal:{session.attempt_id}") == before
    assert runtime.jobs.get_job(planner.job_id).status is JobStatus.RUNNING
    facts = runtime.current_harness_binding_source(session.attempt_id)
    assert facts.process_generation_id == session.generation.process_generation_id
    assert facts.provider_session_id == session.observation.provider_session_id
    assert adapter.stop_calls == 0


@pytest.mark.parametrize("field", ["operator_execution_profile_digest", "operator_capability_policy_digest"])
def test_native_interactive_creation_cannot_refresh_a_stale_root_seal(tmp_path, field):
    runtime, root, _planner = _case(tmp_path, interactive=False)
    with runtime.store.transaction() as connection:
        constraints = {**root.constraints, field: "f" * 64}
        from control_plane.executive_runtime import _json_dumps
        connection.execute("UPDATE jobs SET constraints_json=? WHERE job_id=?", (_json_dumps(constraints), root.job_id))
    with pytest.raises(StateConflict, match="native.*identity"):
        runtime.jobs.create_interactive_operator(root.job_id,
            command_id=f"coo-cycle:{root.job_id}:create-interactive:0")


class _NativeAdapter(_ActiveAdapter):
    def begin_turn(self, *, turn, **_kwargs):
        self.begin_turn_calls += 1
        self.prompts.append(self.turn_input_loader(turn))
        return TurnStartObservation(self.native_turn_id, True)


def _retained(tmp_path):
    runtime, root, job = _case(tmp_path)
    adapters = []
    def factory(loader):
        adapter = _NativeAdapter(runtime, loader, cancel_during_collect=False)
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(runtime, adapter_factory=factory, prompt_source=_PromptSource())
    retained = asyncio.run(supervisor.start_retained_native_job(job.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{job.job_id}:attempt:1"))
    return runtime, supervisor, retained, adapters[0]


def test_retained_supervisor_keeps_writer_until_existing_terminal_cleanup(tmp_path):
    runtime, supervisor, retained, adapter = _retained(tmp_path)
    supervisor._require_retained_native(retained)
    assert adapter.begin_turn_calls == 1 and adapter.stop_calls == 0
    assert runtime.jobs.get_job(retained.job.job_id).status is JobStatus.RUNNING
    asyncio.run(supervisor.finish_retained_native_job(retained))
    assert adapter.stop_calls == 1
    assert runtime.jobs.get_job(retained.job.job_id).status is JobStatus.COMPLETED
    with pytest.raises(StateConflict):
        supervisor._require_retained_native(retained)


def test_one_shot_supervisor_refuses_native_retention_before_capacity_claim(tmp_path):
    runtime, root, job = _case(tmp_path)
    supervisor = ExecutiveOperatorSupervisor(runtime,
        adapter_factory=lambda _: pytest.fail("provider construction happened"), prompt_source=_PromptSource())
    with pytest.raises(StateConflict, match="interactive"):
        asyncio.run(supervisor.start_cycle_job(job.job_id,
            command_id=f"coo-cycle:{root.job_id}:dispatch:{job.job_id}:attempt:1"))
    assert runtime.attempts.list_attempts() == []


def test_ordinary_native_job_cannot_select_the_retained_driver(tmp_path):
    runtime, root, job = _case(tmp_path, interactive=False)
    supervisor = ExecutiveOperatorSupervisor(runtime,
        adapter_factory=lambda _: pytest.fail("provider construction happened"), prompt_source=_PromptSource())
    with pytest.raises(StateConflict, match="explicit interactive"):
        asyncio.run(supervisor.start_retained_native_job(job.job_id,
            command_id=f"coo-cycle:{root.job_id}:dispatch:{job.job_id}:attempt:1"))
    assert runtime.attempts.list_attempts() == []


def _source(runtime, retained, monkeypatch, *, ack=True, changed=False, foreign=False):
    """Only canonical-carrier/ACK reads are fixtures; Runtime and turns are real."""
    from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector, RuntimeCodexTargetProjector
    from integrations.session_bridge.runtime_return import RuntimeSessionReturn
    fabric = RuntimeFabricTargetProjector(runtime)
    source = RuntimeSessionReturn(runtime, fabric=fabric,
        codex=RuntimeCodexTargetProjector(fabric, owner_configured=lambda: True),
        socket_path=Path("/private/tmp/inert-native-return.sock"))
    captured = {"event": {"event_id": 123}, "request": {
        "attempt_id": retained.session.attempt_id,
        "job_id": "foreign-job" if foreign else retained.job.job_id,
        "worker_id": retained.lease.attempt.worker_id,
        "operation_key": "original-operation",
        "carrier": {"workspace_id": "T-FIXTURE", "channel_id": "C-FIXTURE"}},
        "message": {"message_key": "continue-fixture", "body": {
            "instruction": "Read the exact source and report the recovery step.",
            "stop_condition": "Return one useful finding."}}}
    reads = []
    async def read(**_kwargs):
        reads.append(True)
        return {**captured, "event": {"event_id": 999}} if changed and len(reads) > 1 else captured
    monkeypatch.setattr(source, "read_continuation_source", read)
    monkeypatch.setattr(source, "resolve", lambda **_kwargs: "same-source-binding")
    def require_ack(*_args, **_kwargs):
        if not ack:
            raise StateConflict("original native ACK is not persisted")
        return "original-ack-command"
    monkeypatch.setattr(source, "require_native_ack", require_ack)
    return source


def test_post_ack_turn_uses_canonical_continue_and_preserves_initial_seal(tmp_path, monkeypatch):
    runtime, supervisor, retained, adapter = _retained(tmp_path)
    source = _source(runtime, retained, monkeypatch)
    seal_id = f"orchestration-result-seal:{retained.session.attempt_id}"
    before = runtime.events.get_event_by_command_id(seal_id)
    asyncio.run(supervisor.run_native_continuation(retained, source=source, read_ref="fixture-read"))
    assert adapter.begin_turn_calls == 2 and adapter.stop_calls == 0
    assert "Read the exact source and report the recovery step." in adapter.prompts[-1]
    assert '"operation_key":"original-operation"' in adapter.prompts[-1]
    assert '"in_reply_to":"continue-fixture"' in adapter.prompts[-1]
    assert runtime.events.get_event_by_command_id(seal_id) == before
    supervisor._require_retained_native(retained)


def test_same_canonical_continue_cannot_replay_the_provider_turn(tmp_path, monkeypatch):
    runtime, supervisor, retained, adapter = _retained(tmp_path)
    source = _source(runtime, retained, monkeypatch)
    asyncio.run(supervisor.run_native_continuation(retained, source=source, read_ref="fixture-read"))
    before = runtime.events.list_events()
    with pytest.raises(StateConflict, match="retryable"):
        asyncio.run(supervisor.run_native_continuation(retained, source=source, read_ref="fixture-read"))
    assert adapter.begin_turn_calls == 2 and runtime.events.list_events() == before


def test_retained_handle_loses_authority_when_the_original_writer_is_released(tmp_path):
    runtime, supervisor, retained, adapter = _retained(tmp_path)
    runtime.operator_harness.record_reconcile_observation(
        generation=retained.session.generation,
        observation=ReconcileObservation(ProcessLiveness.PROVEN_DEAD, adapter.process,
            False, ProviderWriterState.RELEASED, adapter.provider_session_id),
        fence_generation=retained.lease.attempt.fence_generation,
        lease_token=retained.lease.lease_token)
    with pytest.raises(StateConflict):
        supervisor._require_retained_native(retained)
    assert adapter.begin_turn_calls == 1 and adapter.stop_calls == 0


@pytest.mark.parametrize("fault", ["ack", "changed", "foreign", "owner"])
def test_native_followup_refuses_bad_source_before_turn_intent_or_provider_io(tmp_path, monkeypatch, fault):
    runtime, supervisor, retained, adapter = _retained(tmp_path)
    source = _source(runtime, retained, monkeypatch,
        ack=fault != "ack", changed=fault == "changed", foreign=fault == "foreign")
    if fault == "owner":
        retained = replace(retained, owner=object())
    before = runtime.events.list_events()
    with pytest.raises(StateConflict):
        asyncio.run(supervisor.run_native_continuation(retained, source=source, read_ref="fixture-read"))
    assert adapter.begin_turn_calls == 1 and runtime.events.list_events() == before
