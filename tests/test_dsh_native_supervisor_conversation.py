"""Native Supervisor consumer with real Runtime and explicit inert host seams.

Positive cases use the unpatched canonical policy and config projection.
Original-input custody and provider observations remain inert. C13 covers
the actual nominal input source; these cases exercise its Supervisor consumer.
"""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from control_plane import executive_runtime as rt
from control_plane import fresh_conversation_admission as input_owner
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_operator_supervisor import (
    ExecutiveOperatorSupervisor, ExecutiveOperatorSupervisorError, RetainedNativeOperatorSession,
)
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
from test_dsh_native_runtime_result import _started_native, _NativeTurnAdapter, _orchestrator
from test_dsh_native_supervisor_binding import _case as history_case
from tests.test_executive_operator_supervisor import _ActiveAdapter


MESSAGE = "  原生对话\nKeep the exact input.  "


def _case(tmp_path, monkeypatch):
    f = _started_native(tmp_path, monkeypatch, claim_only=True, worktree=tmp_path / "workspace")
    adapters, inputs = [], []
    class InertNative(_NativeTurnAdapter, _ActiveAdapter, RemoteOperatorHarnessAdapter):
        def __init__(self, loader):
            _ActiveAdapter.__init__(self, f.runtime, loader, cancel_during_collect=False)
            _NativeTurnAdapter.__init__(self, f)
            self._fresh_effect_guard = self._foreground_attempt_id = None
        def start_session(self, **kwargs):
            f.generation, f.epoch = kwargs["generation"], kwargs["epoch"]
            f.session_id = self.provider_session_id
            return _ActiveAdapter.start_session(self, **kwargs)
        def observed_attestation(self, generation):
            return replace(_ActiveAdapter.observed_attestation(self, generation),
                           effective_plugins_or_apps=("mastermind-company",))
        def begin_turn(self, **kwargs):
            self.prompts.append(self.turn_input_loader(kwargs["turn"]))
            hook = getattr(f, "after_prompt", None)
            if hook is not None: hook()
            from control_plane.operator_harness_wire import to_wire
            payload = {key: to_wire(kwargs[key]) for key in ("operation_id", "turn", "generation", "launch")}
            options = self._fresh_write_options("ohf-begin-turn", payload)
            if options: options["before_write"]("ohf-begin-turn", payload)
            return _NativeTurnAdapter.begin_turn(self, **kwargs)
        def graceful_stop(self, generation, **kwargs):
            observed = _ActiveAdapter.graceful_stop(self, generation, **kwargs)
            return replace(observed, observed_config_digest=
                           self.observed_attestation(generation).effective_config_digest)
        def cancel(self, generation, **kwargs):
            observed = _ActiveAdapter.cancel(self, generation, **kwargs)
            return replace(observed, observed_config_digest=
                           self.observed_attestation(generation).effective_config_digest)
        def reconcile(self, generation):
            from control_plane.operator_harness_contract import ProcessLiveness, ProviderWriterState
            observed = _ActiveAdapter.reconcile(self, generation)
            return replace(observed,
                process_liveness=ProcessLiveness.PROVEN_DEAD if self.stop_calls or self.cancel_calls else ProcessLiveness.ALIVE,
                provider_writer_state=ProviderWriterState.RELEASED if self.stop_calls or self.cancel_calls else ProviderWriterState.HELD,
                observed_config_digest=self.observed_attestation(generation).effective_config_digest)
        def observe_raw_role_result(self, _turn):
            pytest.fail("native conversation was read as a planner envelope")
    def factory(attempt, requested, loader, *, recovery):
        assert not recovery and attempt.attempt_id == f.dispatch.attempt.attempt_id
        assert requested.provider == "acp" and requested.harness_kind == "dsh-native-web-acp"
        adapter = InertNative(loader)
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(f.runtime, claimed_adapter_factory=factory,
        workspace_identity_source=lambda attempt, job: f.requested.workspace,
        prompt_source=SimpleNamespace(_prompt=lambda *a, **k: pytest.fail("planner prompt was built")))
    def original_input(runtime, job, operation, *, supervisor):
        assert runtime is f.runtime and job.job_id == f.job.job_id
        inputs.append((job.job_id, supervisor))
        return MESSAGE
    monkeypatch.setattr(input_owner, "require_native_initial_message", original_input)
    lease = rt.AttemptLease(f.dispatch.attempt, f.dispatch.lease_token)
    return f, supervisor, lease, adapters, inputs


def test_native_initial_supervisor_retains_original_result_without_role_envelope(tmp_path, monkeypatch):
    f, supervisor, lease, adapters, inputs = _case(tmp_path, monkeypatch)
    observations = []
    def active(value, present):
        observations.append((value, present))
        if present:
            assert supervisor._require_active_native_turn(value).attempt_id == lease.attempt.attempt_id
        else:
            assert value.withdrawn
    retained = supervisor._run_claimed(f.job, lease, retain_native=True, _active_turn_observer=active)
    assert type(retained) is RetainedNativeOperatorSession
    assert retained.canonical_plan_json is None and retained.native_result is not None
    assert len(adapters) == 1 and adapters[0].prompts == [MESSAGE]
    assert adapters[0].calls == 1 and adapters[0].stop_calls == 0 and len(inputs) >= 2
    assert all(owner is supervisor for _, owner in inputs)
    assert [present for _, present in observations] == [True, False]
    assert observations[0][0] is observations[1][0]
    result = f.runtime.operator_harness.native_conversation_result(
        attempt_id=retained.session.attempt_id, reference=retained.native_result)
    assert result["job_id"] == f.job.job_id
    assert supervisor._require_retained_native(retained).provider_session_id == retained.session.observation.provider_session_id
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.RUNNING
    assert not any(e.event_type == "ORCHESTRATION_ROLE_RESULT_SEALED" for e in f.runtime.events.list_events())
    with pytest.raises(rt.StateConflict, match="planner CONTINUE"):
        asyncio.run(supervisor.run_native_continuation(retained, source=object(), read_ref="not-a-source"))
    with pytest.raises(rt.StateConflict):
        replace(retained, canonical_plan_json="{}")


def test_native_source_is_rechecked_before_initial_message_dispatch(tmp_path, monkeypatch):
    f, supervisor, lease, adapters, inputs = _case(tmp_path, monkeypatch)
    calls = []
    def changed(*a, **k):
        calls.append(True)
        return MESSAGE if len(calls) == 1 else MESSAGE + " changed"
    monkeypatch.setattr(input_owner, "require_native_initial_message", changed)
    with pytest.raises(Exception):
        supervisor._run_claimed(f.job, lease, retain_native=True)
    assert len(adapters) == 1 and adapters[0].calls == 0
    assert adapters[0].stop_calls == 1
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.FAILED
    assert not any(e.event_type == "OHF_NATIVE_CONVERSATION_RESULT_SEALED" for e in f.runtime.events.list_events())


def test_native_retained_start_requires_nominal_input_before_capacity_claim(tmp_path, monkeypatch):
    f = _started_native(tmp_path, monkeypatch, unclaimed=True)
    supervisor = ExecutiveOperatorSupervisor(f.runtime,
        claimed_adapter_factory=lambda *a, **k: pytest.fail("adapter constructed before original source"),
        prompt_source=SimpleNamespace())
    with pytest.raises((ValueError, rt.StateConflict)):
        asyncio.run(supervisor.start_retained_native_job(f.job.job_id,
            command_id=f"coo-cycle:{f.root.job_id}:dispatch:{f.job.job_id}:attempt:1"))
    assert f.runtime.attempts.list_attempts() == []


@pytest.mark.parametrize("resumed", [False, True])
def test_native_retained_reader_keeps_historical_result_separate_from_current_writer(tmp_path, monkeypatch, resumed):
    f, lease, reference = history_case(tmp_path, monkeypatch, resume=resumed)
    supervisor = ExecutiveOperatorSupervisor(f.runtime,
        claimed_adapter_factory=lambda *a, **k: pytest.fail("history reader constructed adapter"),
        prompt_source=SimpleNamespace())
    _, _, adapter, session = _orchestrator(f)
    retained = RetainedNativeOperatorSession(supervisor, f.job, lease, session, adapter,
                                             native_result=reference)
    facts = supervisor._require_retained_native(retained)
    assert facts.process_generation_id == f.generation.process_generation_id
    payload = f.runtime.operator_harness.native_conversation_result(attempt_id=f.epoch.attempt_id, reference=reference)
    assert (payload["turn"]["process_generation_id"] != facts.process_generation_id) is resumed
    with pytest.raises(rt.StateConflict):
        supervisor._require_retained_native(replace(retained,
            native_result=replace(reference, event_id=reference.event_id + 1)))


@pytest.mark.parametrize("claimed", [False, True])
def test_original_coo_excludes_native_conversation_from_one_shot_planning(tmp_path, monkeypatch, claimed):
    f = _started_native(tmp_path, monkeypatch, claim_only=claimed, unclaimed=not claimed)
    before = f.runtime.events.list_events()
    outcome = CooCycle(f.runtime).run_once(f.root.job_id)
    assert outcome.action == "NO_ACTION"
    assert outcome.receipt["reason"] == "interactive_profile_not_owned_by_one_shot_cycle"
    assert len(f.runtime.jobs.list_jobs()) == 2
    assert f.runtime.events.list_events() == before


def test_native_initial_input_is_rechecked_at_original_final_prewrite(tmp_path, monkeypatch):
    f, supervisor, lease, adapters, _ = _case(tmp_path, monkeypatch)
    current = [MESSAGE]
    monkeypatch.setattr(input_owner, "require_native_initial_message", lambda *a, **k: current[0])
    f.after_prompt = lambda: current.__setitem__(0, MESSAGE + " changed after loading")
    # Explicit inert foreground/input authority seam. The qualified transport's
    # actual payload-bound final pre-write guard is exercised unchanged.
    operation = SimpleNamespace(require_root=lambda root: None, _require_live=lambda: None)
    with pytest.raises(Exception):
        supervisor._run_claimed(f.job, lease, retain_native=True, foreground_operation=operation)
    assert len(adapters) == 1 and adapters[0].calls == 0
    assert adapters[0].stop_calls == 1
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.FAILED
