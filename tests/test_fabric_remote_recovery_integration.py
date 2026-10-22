"""V2 remote coordinates stay pinned across actual Runtime lease adoption."""
import asyncio
import copy
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import executive_fabric_adapter as adapter_module
from control_plane import worker_execution_contract as contract
from control_plane.executive_supervisor import ExecutiveSupervisor, SupervisorError
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry, CapabilityPolicyError,
    adapter_supports_execution_surface,
)
from control_plane.executive_worker_broker import BrokerStateError
from control_plane.worker_execution_contract import CleanupPolicy, WorkerRecoveryBinding
from test_executive_fabric_adapter import _fixture
from test_executive_fabric_adapter_fencing import RetainedClient, adopt
from test_fabric_remote_recovery_contract import fixture as remote_fixture


def started_remote(tmp_path, monkeypatch):
    client = RetainedClient()
    runtime, job, lease, adapter, spec, payload = _fixture(tmp_path, monkeypatch, client)
    spec = dataclasses.replace(spec,
        result_schema_path=Path(spec.run_dir) / 'input' / 'schema.json')
    payload['launch_spec']['result_schema_path'] = str(spec.result_schema_path)
    local = tmp_path / 'control' / spec.run_id / 'input'
    local.mkdir(parents=True)
    prompt = local / 'prompt.txt'
    prompt.write_text(spec.prompt)
    prompt.chmod(0o600)
    context = dict(input_root=str(local), source_workspace=str(tmp_path / 'source'))
    original_resolve = adapter._resolve

    def install_resolver(target):
        def resolve(s, *, launch, control_recovery=None):
            attempt, physical, wire = original_resolve(s, launch=launch)
            wire = copy.deepcopy(wire)
            selected = (control_recovery if control_recovery is not None
                        else target._control_recovery.get(s.run_id))
            if selected is not None:
                wire['control_recovery'] = dict(selected)
            return attempt, physical, wire
        monkeypatch.setattr(target, '_resolve', resolve)

    install_resolver(adapter)
    client.spec = spec
    ref = asyncio.run(adapter.start(spec, lease=lease, control_recovery=context))
    runtime.attempts.record_process(spec.run_id,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
        provider_session_id=ref.provider_session_id)
    runtime.attempts.mark_running(spec.run_id,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token)
    binding = WorkerRecoveryBinding.bind(adapter_id='attended-fabric', spec=spec,
        process_ref=ref, prompt_path=prompt, control_recovery=context)
    recovered = adapter_module.AttendedFabricWorkerAdapter(runtime, adapter.binding_source,
        client_factory=lambda physical: client)
    install_resolver(recovered)
    return runtime, lease, recovered, spec, ref, binding, client


def test_v2_adoption_uses_original_remote_generation_and_only_status(tmp_path, monkeypatch):
    rt, lease, adapter, spec, ref, binding, client = started_remote(tmp_path, monkeypatch)
    replacement = adopt(rt, lease)
    assert adapter.reattach(spec, binding, lease=replacement) == ref
    assert adapter.control_recovery_context(spec) == dict(binding.control_recovery)
    assert ref.stdout_path.startswith('/srv/fabric/')
    assert client.calls == ['start', 'status']


def test_recomputed_public_context_hash_cannot_bypass_original_pin_or_open_prompt(tmp_path, monkeypatch):
    rt, lease, adapter, spec, ref, binding, client = started_remote(tmp_path, monkeypatch)
    replacement = adopt(rt, lease)
    raw = binding.to_dict()
    material = raw['launch_spec']
    material['control_recovery']['input_root'] = '/foreign/' + spec.run_id + '/input'
    material['prompt_path'] = material['control_recovery']['input_root'] + '/prompt.txt'
    material['control_recovery_sha256'] = contract._control_recovery_digest(
        raw['launch_spec_sha256'], material)
    damaged = WorkerRecoveryBinding.from_dict(raw)
    def forbidden(*args, **kwargs):
        raise AssertionError('untrusted prompt must not be opened')
    monkeypatch.setattr(WorkerRecoveryBinding, 'recover_launch_spec', forbidden)
    with pytest.raises(BrokerStateError, match='original launch pin'):
        adapter.reattach(spec, damaged, lease=replacement)
    assert client.calls == ['start']
    assert not adapter._control_recovery


@pytest.mark.parametrize('damage', ['input_root', 'source_workspace', 'cleanup'])
def test_supervisor_rejects_foreign_control_coordinates_before_prompt_read(tmp_path, monkeypatch, damage):
    spec, ref, prompt, context = remote_fixture(tmp_path)
    original = dict(context)
    if damage != 'cleanup':
        context[damage] = '/foreign/' + damage
    # Construct a self-consistent public document; this is still not authority.
    good = WorkerRecoveryBinding.bind(adapter_id='attended-fabric', spec=spec,
        process_ref=ref, prompt_path=prompt, control_recovery=original)
    raw = good.to_dict()
    material = raw['launch_spec']
    material['control_recovery'] = context
    material['control_recovery_sha256'] = contract._control_recovery_digest(
        raw['launch_spec_sha256'], material)
    supervisor = object.__new__(ExecutiveSupervisor)
    supervisor.cleanup_policy = (CleanupPolicy.FABRIC_PROCESS_GROUP if damage != 'cleanup'
                                 else CleanupPolicy.DEDICATED_UID)
    supervisor._job = lambda job_id: SimpleNamespace(worktree=original['source_workspace'])
    supervisor._run_dir = lambda run_id: Path(original['input_root']).parent
    attempt = SimpleNamespace(attempt_id=spec.run_id, job_id=spec.job_id,
                              launch_metadata={'worker_recovery_binding': raw})
    def forbidden(*args, **kwargs):
        raise AssertionError('foreign prompt must not be opened')
    monkeypatch.setattr(WorkerRecoveryBinding, 'recover_launch_spec', forbidden)
    with pytest.raises(SupervisorError, match='Control recovery coordinates'):
        supervisor._validated_recovery_binding(attempt)


def test_finite_profile_is_not_runtime_admission_and_native_profile_is_preserved(tmp_path):
    registry = ExecutionCapabilityRegistry.load()
    # The reviewed finite capability contract is now source-qualified. Its
    # existence alone still cannot select or admit an ordinary paid worker.
    profile = registry.resolve('fabric.attended.claude.bounded.v1')
    assert profile.execution_surface == 'claude-code'
    assert profile.sandbox_policy == 'read-only' and not profile.write_capable
    assert profile.network_policy == 'disabled'
    from control_plane.model_router import ModelRouter, RoutingPolicyError
    router = ModelRouter.load()
    assert not router.providers['minimax'].enabled
    assert not router.model_aliases['minimax.attended'].worker_eligible
    with pytest.raises(RoutingPolicyError):
        router.resolve_model_alias('minimax.attended')
    proposal = json.loads(Path(
        'integrations/session_bridge/proposals/attended_claude_profile.json').read_text())
    assert proposal['status'] == 'UNINSTALLED_PROPOSAL'
    assert proposal['profile']['enabled'] is False
    candidate = json.loads(Path('config/executive_agent_capabilities.json').read_text())
    candidate['profiles'][proposal['profile_id']] = proposal['profile']
    candidate_path = tmp_path / 'capabilities.json'
    candidate_path.write_text(json.dumps(candidate))
    with pytest.raises(CapabilityPolicyError, match='disabled'):
        ExecutionCapabilityRegistry.load(candidate_path).resolve(proposal['profile_id'])
    assert registry.policy_version == '2026-10-14.attended-qualification'
    assert registry.resolve('operator.appserver.interactive.native-return.v1').enabled
    assert adapter_supports_execution_surface('attended-fabric', 'claude-code')
    assert not adapter_supports_execution_surface('attended-fabric', 'codex-app-server')


def test_attended_worker_cannot_take_legacy_missing_profile_exemption():
    supervisor = object.__new__(ExecutiveSupervisor)
    supervisor.runtime = SimpleNamespace(workers=SimpleNamespace(
        get_worker=lambda worker_id: SimpleNamespace(worker_type='attended-fabric')))
    with pytest.raises(SupervisorError, match='exact finite attended read-only profile'):
        supervisor._validate_execution_profile(SimpleNamespace(constraints={}),
            SimpleNamespace(attempt=SimpleNamespace(worker_id='worker-1')))


@pytest.mark.parametrize('profile_id', [
    'sealed.worker.claude.readonly.no-extensions.v1',
    'sealed.worker.claude.write.no-extensions.v1',
])
def test_supervisor_cannot_substitute_a_generic_claude_profile_for_attended_grant(tmp_path, profile_id):
    from test_executive_supervisor import (
        _runtime_and_routed_job, _supervisor, FakeAdapter, FakeInspector,
    )
    runtime, job_id, _ = _runtime_and_routed_job(tmp_path,
        profile_id=profile_id, provider='minimax', worker_type='attended-fabric')
    adapter = FakeAdapter(FakeInspector())
    supervisor = _supervisor(runtime, tmp_path, adapter)
    with pytest.raises(SupervisorError, match='exact finite attended read-only profile'):
        asyncio.run(supervisor.start_job(job_id))
    assert adapter.spec is None
