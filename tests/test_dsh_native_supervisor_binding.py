"""Claim-bound native construction reuses incumbent Supervisor currentness."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from control_plane import executive_runtime as rt
from control_plane.executive_operator_supervisor import (
    ExecutiveOperatorSupervisor, ExecutiveOperatorSupervisorError,
)
from control_plane.native_conversation_result import ROLE_RESULT_CONTRACT
from test_dsh_native_runtime_binding import _stored
from test_dsh_native_runtime_result import _started_native, _turn, _NativeTurnAdapter
from test_dsh_native_runtime_resume import _release, _resume


def _case(tmp_path, monkeypatch, *, resume=False):
    f = _started_native(tmp_path, monkeypatch)
    turn, observation = _turn(f)
    ref = f.runtime.operator_harness.seal_native_conversation_result(
        turn=turn, observation=observation, **f.lease)
    if resume:
        _release(f)
        f = _resume(f)
    lease = rt.AttemptLease(f.runtime.attempts.get_attempt(f.epoch.attempt_id), f.dispatch.lease_token)
    return f, lease, ref


@pytest.mark.parametrize("resume", [False, True])
def test_native_constructor_retains_historical_result_and_current_claim(tmp_path, monkeypatch, resume):
    f, lease, ref = _case(tmp_path, monkeypatch, resume=resume)
    constructed = []
    def factory(attempt, requested, loader, *, recovery):
        assert recovery and attempt.attempt_id == lease.attempt.attempt_id
        assert requested == f.requested
        assert f.runtime.jobs.get_planner_producer_binding(attempt.job_id) is None
        adapter = _NativeTurnAdapter(f)
        constructed.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(f.runtime, claimed_adapter_factory=factory,
                                              prompt_source=SimpleNamespace())
    adapter = supervisor._adapter_for_attempt(lease, f.requested, lambda _: "unused",
                                              recovery=True, expected_native_result=ref)
    assert constructed == [adapter]
    assert adapter.calls == 0
    assert f.runtime.operator_harness.current_writer_generation(f.epoch) == f.generation
    payload = f.runtime.operator_harness.native_conversation_result(attempt_id=f.epoch.attempt_id, reference=ref)
    assert payload["turn"]["process_generation_id"] != f.generation.process_generation_id if resume else (
        payload["turn"]["process_generation_id"] == f.generation.process_generation_id)


@pytest.mark.parametrize("kind", ["wrong_profile", "foreign_ref", "planner_seal", "root_drift", "quota_drift"])
def test_native_constructor_refuses_before_factory_on_binding_drift(tmp_path, monkeypatch, kind):
    f, lease, ref = _case(tmp_path, monkeypatch)
    calls = []
    supervisor = ExecutiveOperatorSupervisor(f.runtime,
        claimed_adapter_factory=lambda *a, **k: calls.append(True), prompt_source=SimpleNamespace())
    requested = f.requested
    kwargs = dict(recovery=True, expected_native_result=ref)
    if kind == "wrong_profile":
        requested = replace(requested, harness_kind="codex-app-server", provider="openai-codex")
    elif kind == "foreign_ref":
        kwargs["expected_native_result"] = replace(ref, event_id=ref.event_id+1)
    elif kind == "planner_seal":
        kwargs["expected_recovery_seal"] = "{}"
    elif kind == "root_drift":
        root = f.runtime.jobs.get_job(f.root.job_id)
        with f.runtime.store.transaction() as connection:
            connection.execute("UPDATE jobs SET constraints_json=? WHERE job_id=?",
                (rt._json_dumps(dict(root.constraints, operator_model="moved-model")), root.job_id))
    elif kind == "quota_drift":
        with f.runtime.store.transaction() as connection:
            connection.execute("UPDATE worker_quota_classes SET model=? WHERE worker_id=? AND quota_class=?",
                               ("moved-model", f.epoch.worker_id, "dsh-native"))
    with pytest.raises((rt.StateConflict, ExecutiveOperatorSupervisorError)):
        supervisor._adapter_for_attempt(lease, requested, lambda _: "unused", **kwargs)
    assert calls == []


def test_native_construction_refuses_binding_change_during_factory(tmp_path, monkeypatch):
    f, lease, ref = _case(tmp_path, monkeypatch)
    calls = []
    def factory(*_args, **_kwargs):
        calls.append(True)
        job = f.runtime.jobs.get_job(f.job.job_id)
        with f.runtime.store.transaction() as connection:
            connection.execute("UPDATE jobs SET constraints_json=? WHERE job_id=?",
                (rt._json_dumps(dict(job.constraints, model="moved-model")), job.job_id))
        return _NativeTurnAdapter(f)
    supervisor = ExecutiveOperatorSupervisor(f.runtime, claimed_adapter_factory=factory,
                                              prompt_source=SimpleNamespace())
    with pytest.raises((rt.StateConflict, ExecutiveOperatorSupervisorError)):
        supervisor._adapter_for_attempt(lease, f.requested, lambda _: "unused",
                                        recovery=True, expected_native_result=ref)
    assert calls == [True]


def test_native_constructor_cannot_use_legacy_factory_or_role_adapter(tmp_path, monkeypatch):
    f, lease, ref = _case(tmp_path, monkeypatch)
    calls = []
    supervisor = ExecutiveOperatorSupervisor(f.runtime,
        adapter_factory=lambda *a: calls.append(True), prompt_source=SimpleNamespace())
    with pytest.raises(ExecutiveOperatorSupervisorError, match="claim-aware"):
        supervisor._adapter_for_attempt(lease, f.requested, lambda _: "unused", recovery=True)
    assert calls == []
    legacy = _NativeTurnAdapter(f)
    legacy.result_contract = ROLE_RESULT_CONTRACT
    supervisor = ExecutiveOperatorSupervisor(f.runtime,
        claimed_adapter_factory=lambda *a, **k: legacy, prompt_source=SimpleNamespace())
    with pytest.raises(ExecutiveOperatorSupervisorError, match="native adapter differs"):
        supervisor._adapter_for_attempt(lease, f.requested, lambda _: "unused", recovery=True,
                                        expected_native_result=ref)


def test_disabled_native_storage_cannot_enter_fresh_claim_join(tmp_path, monkeypatch):
    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
    from test_dsh_native_runtime_binding import CANDIDATE

    runtime, root, job = _stored(tmp_path)
    disabled = ExecutionCapabilityRegistry.load(CANDIDATE)
    assert disabled.profiles["operator.dsh.native-conversation.v1"].enabled is False
    monkeypatch.setattr(ExecutionCapabilityRegistry, "load", classmethod(lambda cls: disabled))
    with pytest.raises(rt.StateConflict, match="capability policy"):
        runtime.jobs.assert_frontier_planner_execution(job.job_id)
    assert runtime.attempts.list_attempts() == []
