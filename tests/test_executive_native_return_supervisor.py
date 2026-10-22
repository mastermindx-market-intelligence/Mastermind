"""Native return planner admission on existing Runtime/OHF; provider is inert."""
import asyncio
import dataclasses

import pytest

from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor, ExecutiveOperatorSupervisorError
from control_plane.executive_runtime import AttemptLease, AttemptStatus, JobStatus
from control_plane.operator_harness_contract import NativeHelperPolicy
from tests.test_executive_operator_supervisor import _ActiveAdapter, _PromptSource, _seed_dispatchable_operator_planner

NATIVE_PROFILE = "operator.appserver.interactive.native-return.v1"

def _case(tmp_path):
    runtime, root, planner = _seed_dispatchable_operator_planner(
        tmp_path, operator_model_alias="coo.operator.native-return")
    adapters = []
    def factory(loader):
        adapter = _ActiveAdapter(runtime, loader, cancel_during_collect=False)
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(runtime, adapter_factory=factory, prompt_source=_PromptSource())
    return runtime, root, planner, supervisor, adapters

def test_native_profile_uses_actual_claim_seal_turn_result_and_cleanup(tmp_path):
    runtime, root, planner, supervisor, adapters = _case(tmp_path)
    outcome = asyncio.run(supervisor.start_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"))
    assert outcome.outcome == "TERMINAL"
    assert runtime.jobs.get_job(planner.job_id).status is JobStatus.COMPLETED
    assert runtime.attempts.get_attempt(outcome.attempt.attempt_id).status is AttemptStatus.COMPLETED
    assert len(adapters) == 1 and adapters[0].begin_turn_calls == adapters[0].stop_calls == 1
    requested = adapters[0].profile
    assert requested.provider == "openai-codex" and requested.harness_kind == "codex-app-server"
    assert requested.native_helper_policy is NativeHelperPolicy.DISABLED
    assert not requested.write_capable and requested.allowed_write_paths == ()
    assert tuple(c.name for c in requested.capabilities.required) == ("mastermind-native-return",)
    with runtime.store.read() as conn:
        assert conn.execute("SELECT state FROM harness_session_epochs WHERE attempt_id=?",
            (outcome.attempt.attempt_id,)).fetchone()[0] == "ABANDONED"

@pytest.mark.parametrize("change", [
    {"profile_id":"unreviewed.native"}, {"execution_surface":"codex-cli-sealed"},
    {"sandbox_policy":"workspace-write"}, {"approval_policy":"on-request"},
    {"network_policy":"loopback-browser-only"}, {"write_capable":True},
    {"auth_realm":"personal-interactive"}, {"skills":("foreign",)},
    {"plugins":("foreign",)}, {"skill_grants":(object(),)},
    {"resource_grants":(object(),)}, {"native_helper":object()},
    {"native_helper_policy":NativeHelperPolicy.PARENT_READ_ONLY_CEILING},
    {"mcp_server_grants":"wrong_mcp"}, {"mcp_server_grants":"extra_mcp"},
    {"mcp_server_grants":()},
])
def test_native_profile_cannot_borrow_or_widen_another_lane(tmp_path, monkeypatch, change):
    runtime, root, planner, supervisor, adapters = _case(tmp_path)
    dispatch = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1")
    assert dispatch is not None and dispatch.lease_token
    registry = ExecutionCapabilityRegistry.load()
    change = dict(change)
    mcp_change = change.get("mcp_server_grants")
    if mcp_change in ("wrong_mcp", "extra_mcp"):
        docs = registry.mcp_servers["openai-developer-docs-v1"]
        change["mcp_server_grants"] = ((docs,) if mcp_change == "wrong_mcp" else
            (registry.mcp_servers["native-return-mcp-v1"], docs))
    profiles = dict(registry.profiles)
    profiles[NATIVE_PROFILE] = dataclasses.replace(profiles[NATIVE_PROFILE], **change)
    monkeypatch.setattr(ExecutionCapabilityRegistry, "load", classmethod(
        lambda cls: dataclasses.replace(registry, profiles=profiles)))
    with pytest.raises(ExecutiveOperatorSupervisorError, match="reviewed rich read-only"):
        supervisor._requested_profile(planner, AttemptLease(dispatch.attempt, dispatch.lease_token))
    assert adapters == []

@pytest.mark.parametrize("part", ["quota","job"])
def test_native_profile_requires_codex_provider_before_adapter(tmp_path, monkeypatch, part):
    runtime, root, planner, supervisor, adapters = _case(tmp_path)
    dispatch = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1")
    assert dispatch is not None and dispatch.lease_token
    if part == "job":
        planner = dataclasses.replace(planner, constraints={**planner.constraints,"provider":"foreign"})
    else:
        original = runtime.workers.get_quota_class
        monkeypatch.setattr(runtime.workers,"get_quota_class",lambda *args: dataclasses.replace(original(*args),provider="foreign"))
    with pytest.raises(ExecutiveOperatorSupervisorError, match="provider drifted"):
        supervisor._requested_profile(planner, AttemptLease(dispatch.attempt, dispatch.lease_token))
    assert adapters == []
