"""Exercise the actual Control factory without sockets, credentials or providers."""
from types import SimpleNamespace

import pytest

from scripts import executive_os_phase1c as cli
from control_plane import executive_worker_broker as broker
from control_plane.remote_codex_operator_adapter import RemoteCodexOperatorAdapter
from test_ceo_submit_armed_composition import _raw, _write


def capture(tmp_path, monkeypatch, *, runtime=None, prompt_source=None, **kwargs):
    raw = cli.load_control_config(_write(tmp_path, _raw(tmp_path)))
    captured = {}
    client = object()
    monkeypatch.setattr(broker, 'WorkerBrokerClient', lambda *a, **k: client)
    monkeypatch.setattr(cli, 'activate_launchd_socket', lambda name: object())
    def service(config, **bindings):
        captured.update(bindings)
        return SimpleNamespace(config=config)
    monkeypatch.setattr(cli, 'ExecutiveControlService', service)
    result = cli._service_from_config(raw, **kwargs)
    supervisor = captured['operator_supervisor_factory'](
        runtime if runtime is not None else object(),
        prompt_source if prompt_source is not None else object())
    return result, supervisor, client


def test_control_factory_preserves_explicit_claim_bound_constructor(tmp_path, monkeypatch):
    def factory(attempt, requested, loader, *, recovery):
        raise AssertionError('construction must remain deferred until claim')
    _, supervisor, _ = capture(tmp_path, monkeypatch,
        claimed_operator_adapter_factory=factory)
    assert supervisor._claimed_adapter_factory is factory
    assert supervisor.adapter_factory is None


def test_default_control_proxy_refuses_foreign_worker_before_broker_io(tmp_path, monkeypatch):
    result, supervisor, client = capture(tmp_path, monkeypatch)
    factory = supervisor._claimed_adapter_factory
    requested = SimpleNamespace(worker_id='different-worker',
        provider='openai-codex', harness_kind='codex-app-server')
    with pytest.raises(cli.ServiceError, match='configured operator worker'):
        factory(SimpleNamespace(worker_id='different-worker'), requested,
            lambda turn: '', recovery=False)
    requested.worker_id = result.config.worker_id
    adapter = factory(SimpleNamespace(worker_id=result.config.worker_id),
        requested, lambda turn: '', recovery=False)
    assert isinstance(adapter, RemoteCodexOperatorAdapter) and adapter.client is client


@pytest.mark.parametrize('recovery', [False, True])
@pytest.mark.parametrize('field,value', [
    ('provider', 'claude'), ('harness_kind', 'claude-agent-sdk'),
    ('worker_id', 'foreign-worker'),
])
def test_default_binding_cannot_relabel_native_or_foreign_operator(tmp_path, monkeypatch, recovery, field, value):
    result, supervisor, _ = capture(tmp_path, monkeypatch)
    requested = SimpleNamespace(worker_id=result.config.worker_id,
        provider='openai-codex', harness_kind='codex-app-server')
    setattr(requested, field, value)
    with pytest.raises(cli.ServiceError, match='configured operator worker'):
        supervisor._claimed_adapter_factory(
            SimpleNamespace(worker_id=result.config.worker_id), requested,
            lambda turn: '', recovery=recovery)


def test_invalid_composition_refuses_before_control_or_worker_socket(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('invalid factory reached socket construction')
    monkeypatch.setattr(broker, 'WorkerBrokerClient', forbidden)
    monkeypatch.setattr(cli, 'activate_launchd_socket', forbidden)
    with pytest.raises(cli.ServiceError, match='callable'):
        cli._service_from_config({}, claimed_operator_adapter_factory=object())


def test_real_control_composition_completes_claim_selected_runtime_attempt(tmp_path, monkeypatch):
    import asyncio
    from test_executive_operator_supervisor import (
        _ActiveAdapter, _PromptSource, _seed_dispatchable_operator_planner,
    )
    from control_plane.executive_runtime import AttemptStatus
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path / 'job')
    calls = []
    def factory(attempt, requested, loader, *, recovery):
        assert attempt == runtime.attempts.get_attempt(attempt.attempt_id)
        assert requested.worker_id == attempt.worker_id == 'worker-a'
        assert not recovery
        calls.append(attempt.attempt_id)
        return _ActiveAdapter(runtime, loader, cancel_during_collect=False)
    result, supervisor, _ = capture(tmp_path, monkeypatch,
        runtime=runtime, prompt_source=_PromptSource(),
        claimed_operator_adapter_factory=factory)
    assert result.config.worker_id == 'codex-01'
    outcome = asyncio.run(supervisor.start_cycle_job(planner.job_id,
        command_id=f'coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1'))
    assert outcome.attempt.status is AttemptStatus.COMPLETED
    assert calls == [outcome.attempt.attempt_id]
    assert outcome.attempt.worker_id == 'worker-a'


@pytest.mark.parametrize('native', [False, True])
def test_same_control_path_drives_distinct_claimed_provider_profiles(tmp_path, monkeypatch, native):
    import asyncio
    import dataclasses
    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
    from control_plane.model_router import ModelRouter
    from control_plane.executive_runtime import AttemptStatus
    from test_executive_agent_capabilities import _claude_candidate_policy, _write as write_policy
    from test_executive_operator_supervisor import _ActiveAdapter, _PromptSource, _seed_dispatchable_operator_planner
    router = ModelRouter.load()
    expected = ('openai-codex', 'codex-app-server')
    if native:
        # An explicitly synthetic admission fixture, never a production policy arm.
        registry = ExecutionCapabilityRegistry.load(write_policy(tmp_path, _claude_candidate_policy()))
        profile = dataclasses.replace(registry.profiles['operator.claude.readonly.v1'], enabled=True)
        registry = dataclasses.replace(registry,
            profiles={**registry.profiles, profile.profile_id: profile})
        router.capability_registry = registry
        router.model_aliases = {key: dataclasses.replace(alias,
            capability_policy_version=registry.policy_version,
            capability_policy_digest=registry.policy_digest)
            for key, alias in router.model_aliases.items()}
        router.model_aliases['coo.operator.readonly'] = dataclasses.replace(
            router.model_aliases['coo.operator.readonly'], provider_alias='claude',
            execution_profile_id=profile.profile_id, execution_profile_digest=profile.profile_digest,
            model='claude-fixture-exact', adapter_id='claude-code')
        monkeypatch.setattr(ModelRouter, 'load', lambda *a, **k: router)
        monkeypatch.setattr(ExecutionCapabilityRegistry, 'load', lambda *a, **k: registry)
        expected = ('claude', 'claude-agent-sdk')
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path / 'job')
    seen = []
    def factory(attempt, requested, loader, *, recovery):
        assert (requested.provider, requested.harness_kind) == expected
        assert requested.worker_id == attempt.worker_id
        assert not recovery
        seen.append(requested)
        return _ActiveAdapter(runtime, loader, cancel_during_collect=False)
    _, supervisor, _ = capture(tmp_path, monkeypatch, runtime=runtime,
        prompt_source=_PromptSource(), claimed_operator_adapter_factory=factory)
    outcome = asyncio.run(supervisor.start_cycle_job(planner.job_id,
        command_id=f'coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1'))
    assert outcome.attempt.status is AttemptStatus.COMPLETED and len(seen) == 1
    assert outcome.attempt.requested_execution_profile['provider'] == expected[0]
