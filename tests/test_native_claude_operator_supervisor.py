"""Native profile consumption without enabling policy or starting a provider."""
from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry,
)
from control_plane.executive_operator_supervisor import (
    ExecutiveOperatorSupervisor,
    ExecutiveOperatorSupervisorError,
)
from control_plane.operator_harness_contract import WorkspaceIdentity
from test_executive_agent_capabilities import _claude_candidate_policy, _write


def prepared(tmp_path, monkeypatch, *, admitted=True):
    registry = ExecutionCapabilityRegistry.load(_write(tmp_path, _claude_candidate_policy()))
    candidate = registry.profiles["operator.claude.readonly.v1"]
    # Admission is simulated only for the consumer tests. The production parser
    # still refuses enabling this candidate, and the disabled case uses resolve.
    profile = dataclasses.replace(candidate, enabled=True) if admitted else candidate
    profiles = {profile.profile_id: profile}
    registry = dataclasses.replace(registry, profiles=profiles)
    monkeypatch.setattr(ExecutionCapabilityRegistry, "load", lambda: registry)
    constraints = {
        "execution_profile_id": profile.profile_id,
        "execution_profile_digest": profile.profile_digest,
        "capability_policy_version": registry.policy_version,
        "capability_policy_digest": registry.policy_digest,
        "harness_binary_digest": "a" * 64,
        "harness_version": "2.1.275",
        "provider": "claude", "model": "claude-opus-4-6", "effort": "high",
    }
    quota = SimpleNamespace(metadata=dict(constraints), provider="claude",
                            model=constraints["model"], effort=constraints["effort"])
    calls = []
    def quota_reader(worker_id, quota_class):
        calls.append((worker_id, quota_class))
        return quota
    runtime = SimpleNamespace(workers=SimpleNamespace(get_quota_class=quota_reader))
    def no_provider(*args):
        pytest.fail("profile resolution called a provider")
    supervisor = ExecutiveOperatorSupervisor(runtime, adapter_factory=no_provider,
                                            prompt_source=None)
    workspace = WorkspaceIdentity(str(tmp_path), "b" * 40, 1, 2, 459, 459)
    monkeypatch.setattr(supervisor, "_workspace_identity", lambda job: workspace)
    job = SimpleNamespace(constraints=constraints, orchestration_role="plan",
                          requested_authorities=["READ"], allowed_write_paths=[],
                          validation_commands=[])
    lease = SimpleNamespace(attempt=SimpleNamespace(worker_id="claude8-native-01",
                            quota_class="native-plan", authority_policy_hash="c"*64))
    return supervisor, job, lease, quota, profiles, calls


def test_exact_admitted_native_profile_retains_worker_quota_and_policy(tmp_path, monkeypatch):
    supervisor, job, lease, quota, profiles, calls = prepared(tmp_path, monkeypatch)
    requested = supervisor._requested_profile(job, lease)
    profile = profiles[job.constraints["execution_profile_id"]]
    assert calls == [("claude8-native-01", "native-plan")]
    assert requested.worker_id == lease.attempt.worker_id
    assert (requested.provider, requested.harness_kind) == ("claude", "claude-agent-sdk")
    assert requested.requested_model == quota.model
    assert requested.authority_policy_hash == lease.attempt.authority_policy_hash
    assert requested.capabilities == profile.capability_manifest(harness_binary_digest="a"*64)
    assert requested.expected_config_digest == profile.expected_config_digest
    assert requested.write_capable is False and requested.allowed_write_paths == ()


def test_disabled_native_profile_still_refuses_ordinary_admission(tmp_path, monkeypatch):
    supervisor, job, lease, *_ = prepared(tmp_path, monkeypatch, admitted=False)
    with pytest.raises(ExecutiveOperatorSupervisorError, match="disabled"):
        supervisor._requested_profile(job, lease)


@pytest.mark.parametrize("change", [
    {"execution_surface": "codex-app-server"}, {"profile_id": "invented-native"},
    {"network_policy": "loopback-browser-only"}, {"sandbox_policy": "workspace-write"},
    {"approval_policy": "on-request"}, {"write_capable": True},
    {"auth_realm": "shared-account"}, {"skills": ("unexpected",)},
    {"plugins": ("unexpected",)}, {"skill_grants": (object(),)},
    {"mcp_server_grants": (object(),)}, {"resource_grants": (object(),)},
    {"native_helper": object()},
])
def test_native_profile_cannot_borrow_or_expand_another_lane(tmp_path, monkeypatch, change):
    supervisor, job, lease, _, profiles, _ = prepared(tmp_path, monkeypatch)
    key = job.constraints["execution_profile_id"]
    profiles[key] = dataclasses.replace(profiles[key], **change)
    with pytest.raises(ExecutiveOperatorSupervisorError, match="reviewed rich read-only"):
        supervisor._requested_profile(job, lease)


@pytest.mark.parametrize("field", [
    "execution_profile_digest", "capability_policy_version", "capability_policy_digest",
    "harness_binary_digest", "harness_version", "model", "effort", "provider",
])
def test_postclaim_quota_drift_refuses_before_provider(tmp_path, monkeypatch, field):
    supervisor, job, lease, quota, *_ = prepared(tmp_path, monkeypatch)
    if field in {"provider", "model", "effort"}:
        setattr(quota, field, "drift")
    else:
        quota.metadata[field] = "drift"
    with pytest.raises(ExecutiveOperatorSupervisorError, match="drifted"):
        supervisor._requested_profile(job, lease)


def test_native_profile_requires_exact_job_provider(tmp_path, monkeypatch):
    supervisor, job, lease, *_ = prepared(tmp_path, monkeypatch)
    job.constraints["provider"] = "codex"
    with pytest.raises(ExecutiveOperatorSupervisorError, match="provider drifted"):
        supervisor._requested_profile(job, lease)


def test_native_consumption_does_not_admit_work_roles_or_writes(tmp_path, monkeypatch):
    supervisor, job, lease, *_ = prepared(tmp_path, monkeypatch)
    job.orchestration_role = "work"
    with pytest.raises(ExecutiveOperatorSupervisorError, match="planner role"):
        supervisor._requested_profile(job, lease)
    job.orchestration_role = "plan"
    job.allowed_write_paths = ["result.md"]
    with pytest.raises(ExecutiveOperatorSupervisorError, match="closed read-only"):
        supervisor._requested_profile(job, lease)


def test_native_consumer_connects_to_real_worker_factory_without_provider_work(tmp_path, monkeypatch):
    native = pytest.importorskip("control_plane.claude_operator_adapter",
                                reason="separate native source is not composed")
    from scripts import executive_os_phase1c_worker as worker
    from test_native_claude_worker_factory import prepared as worker_prepared

    original_load = ExecutionCapabilityRegistry.load
    value, profiles, _, worker_requested, _ = worker_prepared(tmp_path, monkeypatch)
    monkeypatch.setattr(ExecutionCapabilityRegistry, "load", original_load)
    supervisor, job, lease, quota, _, _ = prepared(tmp_path, monkeypatch)
    workspace = Path(value["workspace_root"])
    (workspace / "README.md").write_text("native consumer construction fixture\n")
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True)
    subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "-qm", "native consumer fixture"], cwd=workspace, check=True)
    job.worktree = str(workspace)
    job.constraints["base_sha"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=workspace, text=True).strip()
    monkeypatch.setattr(supervisor, "_workspace_identity",
                        ExecutiveOperatorSupervisor._workspace_identity.__get__(supervisor))
    job.constraints["harness_binary_digest"] = worker_requested.harness_binary_digest
    quota.metadata["harness_binary_digest"] = worker_requested.harness_binary_digest
    requested = supervisor._requested_profile(job, lease)
    monkeypatch.setattr(ExecutionCapabilityRegistry, "load",
                        lambda: SimpleNamespace(profiles=profiles))
    monkeypatch.setattr(worker, "_native_claude_adapter_types",
                        lambda: (native.ClaudeOperatorAdapter, native.ClaudeReadbackPolicyObserver))
    value["worker_id"] = requested.worker_id
    broker = worker._build_broker(value, autonomy_guard=lambda: None)
    adapter = broker.operator_adapter_factory(workspace, lambda turn: "not dispatched", requested)
    assert isinstance(adapter, native.ClaudeOperatorAdapter)
    assert adapter.configured_workspace == requested.workspace
    assert adapter.worker_id == requested.worker_id
    assert adapter.validate_requested_profile(requested).accepted
    assert adapter._generations == {}
    assert broker.adapter is None and broker.validation_adapter is None
