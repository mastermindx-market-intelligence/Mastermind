"""Real plugin registry, local transaction owner and native admission boundaries."""
import base64
import copy
import json
import time
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import hermes_yaml as yaml

from agent import launch_credential_binding as binding
from gateway import session_launch_credentials as grants
from hermes_state_runtime import RuntimeStoreError


@pytest.fixture(autouse=True)
def fresh_launch_process_metadata(monkeypatch):
    from hermes_cli import plugins_launch_credentials
    monkeypatch.setattr(plugins_launch_credentials, '_launch_witness', None)


def _declaration():
    return {
        'version': 1, 'operation_env': 'TEST_RUN_ID',
        'withheld_env': ['TEST_AGENT_PRIVATE_KEY'],
        'context_env': ['TEST_RUN_ID', 'TEST_URL', 'TEST_RUNTIME_URL', 'TEST_RUNTIME_EXPIRES'],
        'required_context': ['TEST_RUN_ID', 'TEST_URL'],
        'context_types': {'TEST_RUN_ID': 'uuid', 'TEST_URL': 'http_url', 'TEST_RUNTIME_URL': 'http_url'},
        'same_origin': [['TEST_URL', 'TEST_RUNTIME_URL']],
        'credentials': [{'env': 'TEST_RUN_TOKEN', 'required': True, 'expiry_env': None, 'jwt_exp': True,
                         'jwt_claims': {'run_id': 'TEST_RUN_ID'}, 'required_context': []},
                        {'env': 'TEST_RUNTIME_TOKEN', 'required': False, 'expiry_env': 'TEST_RUNTIME_EXPIRES',
                         'jwt_exp': False, 'jwt_claims': {}, 'required_context': ['TEST_RUNTIME_URL']}],
    }


def _environment(run='00000000-0000-4000-8000-000000000003'):
    payload = base64.urlsafe_b64encode(json.dumps({'run_id': run, 'exp': time.time() + 3600}).encode()).decode().rstrip('=')
    return {'TEST_RUN_ID': run, 'TEST_URL': 'http://127.0.0.1:3100',
            'TEST_RUN_TOKEN': 'fixture.' + payload + '.fixture',
            'TEST_RUNTIME_URL': 'http://127.0.0.1:3100/mcp/tools',
            'TEST_RUNTIME_EXPIRES': datetime.fromtimestamp(time.time() + 1800, UTC).isoformat(),
            'TEST_RUNTIME_TOKEN': 'synthetic-runtime-tool-token',
            'TEST_AGENT_PRIVATE_KEY': 'synthetic-persistent-agent-identity-key',
            'HERMES_REQUIRED_LAUNCH_BINDING': 'test-orchestrator'}


def _profile(home, *, isolation='in_process'):
    home.mkdir()
    plug = home / 'plugins' / 'launch-probe'
    plug.mkdir(parents=True)
    (plug / 'plugin.yaml').write_text(yaml.safe_dump({
        'name': 'launch-probe', 'version': '0.1.0', 'kind': 'standalone',
        'launch_credentials': {'test-orchestrator': _declaration()},
    }))
    (plug / '__init__.py').write_text('def register(ctx):\n    ctx.register_launch_credentials("test-orchestrator")\n')
    (home / 'config.yaml').write_text(yaml.safe_dump({
        'model': {'provider': 'custom', 'default': 'fixture-model', 'base_url': 'http://invalid.invalid/v1'},
        'platform_toolsets': {'cli': []},
        'terminal': {'backend': 'local', 'client_env_passthrough': _declaration()['context_env']},
        'plugins': {'enabled': ['launch-probe'], 'isolation': isolation},
    }))
    return plug


async def _owner(home, monkeypatch, *, isolation='in_process'):
    from gateway import run
    from gateway.config import GatewayConfig
    from gateway.session import SessionStore
    from gateway.session_authority import initialize_session_authority
    from gateway.session_controls import AuthorityConnection
    _profile(home, isolation=isolation)
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setattr(run, '_hermes_home', home)
    store = SessionStore(home / 'sessions', GatewayConfig())
    runner = SimpleNamespace(session_store=store, _session_db=store._db, adapters={}, _draining=False,
                             _cached_agent_for=lambda route: None, _adapter_for_source=lambda source: None,
                             _evict_cached_agent=lambda route: None)
    runner._adapter_for_source = lambda source: runner.adapters.get(source.platform)
    authority = await initialize_session_authority(runner, profile_id=str(home), instance_id='fixture')
    return authority, AuthorityConnection(authority, object(), {'user_id': 'owner'})


def _params(owner, request='run', env=None):
    from gateway.session_authorities import owner_scope
    from hermes_cli.plugins_launch_credentials import collect_launch_credentials
    with owner_scope(owner):
        payload = collect_launch_credentials(env or _environment())
    return {'request_id': request, 'source': 'tool', 'cwd': owner.profile_id, 'toolsets': [],
            'client_env': dict(payload['context']), binding.PRIVATE_FIELD: payload}


def _row(connection, *, admission='first', principal=None, finite=True, generation=1):
    return {'principal_id': principal or connection.actor.subject, 'admission_id': admission,
            'generation': generation, 'payload': {'finite': finite}}


@pytest.mark.asyncio
async def test_native_create_and_overlapping_retry_publish_one_private_grant(tmp_path, monkeypatch):
    from gateway.session_local import stage_local_session, create_local_session
    from hermes_state_local import commit_local_session, local_receipt
    owner, connection = await _owner(tmp_path / 'home', monkeypatch)
    try:
        params = _params(owner)
        first = stage_local_session(owner, connection.actor, copy.deepcopy(params), client_local=True)
        second = stage_local_session(owner, connection.actor, copy.deepcopy(params), client_local=True)
        first_lease, second_lease = first.on_create.lease, second.on_create.lease
        saved = commit_local_session(owner.db, epoch=owner.epoch, receipt=first)
        assert commit_local_session(owner.db, epoch=owner.epoch, receipt=second) == saved
        assert first_lease._values and not second_lease._values
        ref = create_local_session(owner, connection.actor, copy.deepcopy(params), client_local=True)
        assert ref.session_id == first['session_id']
        receipt = local_receipt(owner.db, ref.session_id)
        token = params[binding.PRIVATE_FIELD]['credentials']['TEST_RUN_TOKEN']
        assert token not in json.dumps(receipt) and binding.PRIVATE_FIELD not in json.dumps(receipt)
        assert list(grants._keys(owner).values()).count(first_lease) == 1
        changed = copy.deepcopy(params)
        changed[binding.PRIVATE_FIELD]['credentials']['TEST_RUN_TOKEN'] += 'different'
        with pytest.raises(RuntimeStoreError):
            create_local_session(owner, connection.actor, changed, client_local=True)
        assert first_lease._values
    finally:
        grants.release(owner, list(owner.sessions))
        await connection.close()
        owner.db.close()


@pytest.mark.asyncio
async def test_native_policy_claim_denial_does_not_revoke_valid_run(tmp_path, monkeypatch):
    from gateway.session_local import create_local_session
    from gateway.session_authorities import owner_scope
    owner, connection = await _owner(tmp_path / 'home', monkeypatch)
    try:
        params = _params(owner)
        ref = create_local_session(owner, connection.actor, params, client_local=True)
        held = grants._keys(owner)[grants._slot(owner, ref.session_id)]
        with owner_scope(owner), grants.admission_scope(owner, ref, _row(connection)):
            for wrong in (_row(connection, admission='other'), _row(connection, principal='other')):
                with pytest.raises(RuntimeStoreError):
                    with grants.admission_scope(owner, ref, wrong):
                        pytest.fail('wrong claim executed')
            with pytest.raises(RuntimeStoreError, match='already_active'):
                with grants.admission_scope(owner, ref, _row(connection)):
                    pytest.fail('duplicate execution entered')
            assert grants._keys(owner)[grants._slot(owner, ref.session_id)] is held
            with binding.tool_dispatch_scope(ref.session_id, 'terminal', {}):
                assert binding.tool_environment() == params[binding.PRIVATE_FIELD]['credentials']
        assert not held._values
        with pytest.raises(RuntimeStoreError, match='unavailable'):
            with grants.admission_scope(owner, ref, _row(connection, admission='later', generation=2)):
                pytest.fail('reused settled run')
    finally:
        await connection.close()
        owner.db.close()


@pytest.mark.asyncio
async def test_remote_create_and_unsupported_frozen_modes_fail_before_publication(tmp_path, monkeypatch):
    from gateway.session_local import create_local_session
    from gateway.session_policy import build_policy
    owner, connection = await _owner(tmp_path / 'home', monkeypatch)
    try:
        params = _params(owner)
        with pytest.raises(RuntimeStoreError, match='scope_mismatch'):
            create_local_session(owner, connection.actor, params, client_local=False)
        assert not owner.sessions
        plain = {key: value for key, value in params.items() if key != binding.PRIVATE_FIELD}
        policy = build_policy(plain, yaml.safe_load((tmp_path / 'home' / 'config.yaml').read_text()), client_local=True)
        for mode in ('ssh', 'docker', 'modal'):
            remote = replace(policy, terminal_json=json.dumps({'TERMINAL_ENV': mode}))
            with pytest.raises(RuntimeStoreError, match='execution_mode_unsupported'):
                grants.require_supported_policy(owner, remote)
        managed = replace(policy, config_json=json.dumps({'gateway': {'managed_workers': True}}))
        with pytest.raises(RuntimeStoreError, match='execution_mode_unsupported'):
            grants.require_supported_policy(owner, managed)
    finally:
        await connection.close()
        owner.db.close()


@pytest.mark.asyncio
async def test_cancel_retires_unclaimed_grant_and_exact_retry_cannot_restore_it(tmp_path, monkeypatch):
    from gateway.session_local import create_local_session
    owner, connection = await _owner(tmp_path / 'home', monkeypatch)
    try:
        params = _params(owner)
        ref = create_local_session(owner, connection.actor, params, client_local=True)
        held = grants._keys(owner)[grants._slot(owner, ref.session_id)]
        grants.release_unclaimed(owner, ref.session_id)
        assert not held._values
        with pytest.raises(RuntimeStoreError, match='unavailable'):
            with grants.admission_scope(owner, ref, _row(connection)):
                pytest.fail('cancelled grant executed')
        with pytest.raises(RuntimeStoreError, match='unavailable'):
            create_local_session(owner, connection.actor, params, client_local=True)
    finally:
        await connection.close()
        owner.db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('isolation', ['in_process', 'host'])
async def test_real_plugin_registration_and_old_gateway_refusal(tmp_path, monkeypatch, isolation):
    from gateway.session_authorities import owner_scope
    from hermes_cli.plugins_launch_credentials import declarations, launch_parameters, strip_daemon_credentials
    from hermes_cli.gateway_client import GatewayClientError
    owner, connection = await _owner(tmp_path / 'home', monkeypatch, isolation=isolation)
    try:
        env = _environment()
        with owner_scope(owner):
            assert 'test-orchestrator' in declarations()
            for parameters, caps in (([], []), ([binding.PRIVATE_FIELD], []), ([], [binding.CAPABILITY])):
                with pytest.raises(GatewayClientError, match='unsupported'):
                    launch_parameters(parameters, caps, environ=env)
            received = launch_parameters([binding.PRIVATE_FIELD], [binding.CAPABILITY], environ=env)
            assert received[binding.PRIVATE_FIELD]['credentials']['TEST_RUN_TOKEN'] == env['TEST_RUN_TOKEN']
            stripped = strip_daemon_credentials(env)
            assert 'TEST_RUN_TOKEN' not in stripped and 'HERMES_REQUIRED_LAUNCH_BINDING' not in stripped
    finally:
        await connection.close()
        owner.db.close()


def test_missing_required_plugin_refuses_before_connection(monkeypatch, tmp_path):
    from hermes_cli.gateway_session_store import GatewaySessionStore
    from hermes_cli.gateway_client import GatewayClientError
    from hermes_cli.gateway_connection import GatewayConnection
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setenv('HERMES_REQUIRED_LAUNCH_BINDING', 'deliberately-not-installed')
    attempted = []
    monkeypatch.setattr(GatewayConnection, 'shared', lambda: attempted.append(True))
    with pytest.raises(GatewayClientError, match='plugin_unavailable'):
        GatewaySessionStore()
    assert not attempted


@pytest.mark.parametrize('name', ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'HERMES_RPC_TOKEN', 'GATEWAY_RELAY_TOKEN'])
@pytest.mark.parametrize('destination', ['credentials', 'withheld_env'])
def test_provider_and_runtime_credential_destinations_are_reserved(name, destination):
    from hermes_cli.plugins_launch_credentials import assert_tool_destinations
    spec = _declaration()
    if destination == 'credentials':
        spec['credentials'][0]['env'] = name
    else:
        spec['withheld_env'] = [name]
    with pytest.raises(binding.LaunchCredentialError, match='destination_owned'):
        assert_tool_destinations(spec)


@pytest.mark.parametrize('name', ['OPENAI_API_KEY', 'GATEWAY_RELAY_TOKEN'])
def test_owned_withheld_names_refuse_before_child_spawn(tmp_path, monkeypatch, name):
    from hermes_cli import gateway_runtime_start, plugin_host
    home = tmp_path / 'home'
    plugin = _profile(home, isolation='host')
    manifest = yaml.safe_load((plugin / 'plugin.yaml').read_text())
    manifest['launch_credentials']['test-orchestrator']['withheld_env'] = [name]
    (plugin / 'plugin.yaml').write_text(yaml.safe_dump(manifest))
    monkeypatch.setenv('HERMES_HOME', str(home))
    for key, value in _environment().items():
        monkeypatch.setenv(key, value)
    attempted = []
    monkeypatch.setattr(gateway_runtime_start.subprocess, 'Popen', lambda *a, **kw: attempted.append(True))
    with pytest.raises(binding.LaunchCredentialError, match='destination_owned'):
        plugin_host.PluginHost(SimpleNamespace(home_path=str(home))).ensure_started()
    with pytest.raises(binding.LaunchCredentialError, match='destination_owned'):
        gateway_runtime_start.spawn_unmanaged_gateway(home, deadline=time.monotonic() + 10)
    assert not attempted


def test_provider_metadata_failure_refuses_without_echoing_exception(monkeypatch):
    import providers
    import traceback
    from hermes_cli.plugins_launch_credentials import assert_tool_destinations
    secret = 'synthetic-sensitive-provider-metadata'
    def fail():
        raise RuntimeError(secret)
    monkeypatch.setattr(providers, 'list_providers', fail)
    with pytest.raises(binding.LaunchCredentialError, match='ownership_unavailable') as caught:
        assert_tool_destinations(_declaration())
    assert secret not in ''.join(traceback.format_exception(caught.value))


def test_reentrant_provider_metadata_refuses_child_launch(tmp_path, monkeypatch):
    import providers
    from hermes_cli.plugins_launch_credentials import launch_secret_names
    home = tmp_path / 'home'
    _profile(home)
    monkeypatch.setenv('HERMES_HOME', str(home))
    for key, value in _environment().items():
        monkeypatch.setenv(key, value)
    attempts = []
    depth = 0
    def reentrant_metadata():
        nonlocal depth
        depth += 1
        attempts.append(depth)
        try:
            launch_secret_names()
            pytest.fail('reentrant child launch was allowed')
        finally:
            depth -= 1
    monkeypatch.setattr(providers, 'list_providers', reentrant_metadata)
    with pytest.raises(binding.LaunchCredentialError, match='ownership_unavailable'):
        launch_secret_names()
    assert attempts and set(attempts) == {1}


@pytest.mark.asyncio
async def test_native_finite_execution_wrapper_binds_and_retires_tool_access(tmp_path, monkeypatch):
    from gateway.session_authorities import owner_scope
    from gateway.session_local import create_local_session
    from gateway.session_finite import execute_finite_admission
    from gateway import session_ingress
    from tools.environments.local import _make_run_env
    owner, connection = await _owner(tmp_path / 'home', monkeypatch)
    async def consumer(authority, ref, row):
        with binding.tool_dispatch_scope(ref.session_id, 'terminal', {}):
            return _make_run_env({}).get('TEST_RUN_TOKEN')
    monkeypatch.setattr(session_ingress, 'execute_admission', consumer)
    try:
        params = _params(owner)
        ref = create_local_session(owner, connection.actor, params, client_local=True)
        with owner_scope(owner):
            result = await execute_finite_admission(owner, ref, _row(connection))
        assert result == params[binding.PRIVATE_FIELD]['credentials']['TEST_RUN_TOKEN']
        assert grants._slot(owner, ref.session_id) not in grants._keys(owner)
        assert binding.bound_credentials() is None and 'TEST_RUN_TOKEN' not in _make_run_env({})
    finally:
        await connection.close()
        owner.db.close()


def test_required_launch_reads_metadata_without_importing_plugin_code(tmp_path, monkeypatch):
    from hermes_cli import plugins
    from hermes_cli.plugins_launch_credentials import collect_launch_credentials, launch_secret_names
    home = tmp_path / 'home'
    plug = _profile(home, isolation='host')
    (plug / '__init__.py').write_text('raise AssertionError("plugin code must not run during preflight")\n')
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setattr(plugins, 'discover_plugins', lambda *a, **kw: pytest.fail('preflight started discovery'))
    env = _environment()
    assert launch_secret_names(environ=env) == {'TEST_RUN_TOKEN', 'TEST_RUNTIME_TOKEN', 'TEST_AGENT_PRIVATE_KEY'}
    payload = collect_launch_credentials(env)
    assert payload['credentials']['TEST_RUNTIME_TOKEN'] == env['TEST_RUNTIME_TOKEN']
    assert env['TEST_AGENT_PRIVATE_KEY'] not in json.dumps(payload)
    assert collect_launch_credentials({k: v for k, v in env.items()
                                      if k != 'HERMES_REQUIRED_LAUNCH_BINDING'}) is None


@pytest.mark.parametrize('invalid', ['disabled', 'malformed', 'ambiguous', 'version', 'safe_mode'])
def test_unusable_manifest_refuses_before_connection(tmp_path, monkeypatch, invalid):
    from hermes_cli.gateway_session_store import GatewaySessionStore
    from hermes_cli.gateway_client import GatewayClientError
    from hermes_cli.gateway_connection import GatewayConnection
    home = tmp_path / 'home'
    plug = _profile(home)
    cfg = yaml.safe_load((home / 'config.yaml').read_text())
    manifest = yaml.safe_load((plug / 'plugin.yaml').read_text())
    from hermes_cli import plugins_manifest
    # A source archive has no installed Hermes distribution/version metadata.
    monkeypatch.setattr(plugins_manifest, 'running_hermes_version', lambda: '0.23.0')
    def duplicate():
        other = home / 'plugins' / 'other-launch-probe'
        other.mkdir()
        (other / 'plugin.yaml').write_text(yaml.safe_dump({**manifest, 'name': 'other-launch-probe'}))
        (other / '__init__.py').write_text((plug / '__init__.py').read_text())
        cfg['plugins']['enabled'].append('other-launch-probe')
    mutations = {
        'disabled': lambda: cfg['plugins'].update(disabled=['launch-probe']),
        'malformed': lambda: manifest['launch_credentials']['test-orchestrator'].update(credentials=[]),
        'version': lambda: manifest.update(requires_hermes='>=999.0'),
        'safe_mode': lambda: monkeypatch.setenv('HERMES_SAFE_MODE', '1'),
        'ambiguous': duplicate,
    }
    mutations[invalid]()
    (plug / 'plugin.yaml').write_text(yaml.safe_dump(manifest))
    (home / 'config.yaml').write_text(yaml.safe_dump(cfg))
    monkeypatch.setenv('HERMES_HOME', str(home))
    for key, value in _environment().items():
        monkeypatch.setenv(key, value)
    attempted = []
    monkeypatch.setattr(GatewayConnection, 'shared', lambda: attempted.append(True))
    with pytest.raises(GatewayClientError, match='plugin_unavailable|ambiguous_launch'):
        GatewaySessionStore()
    assert not attempted


def test_plugin_host_and_daemon_strip_before_and_after_profile_overlays(tmp_path, monkeypatch):
    import os
    from hermes_cli import plugin_host, gateway_runtime_start
    from tools.environments import local
    home = tmp_path / 'home'
    _profile(home, isolation='host')
    monkeypatch.setenv('HERMES_HOME', str(home))
    env = _environment()
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-incumbent-provider-key')
    monkeypatch.setenv('GH_TOKEN', 'synthetic-undeclared-ambient-key')
    monkeypatch.setenv('GATEWAY_RELAY_TOKEN', 'synthetic-ambient-relay-token')
    native = local.served_profile_child_env
    observed = []
    def overlay(*, base, target_home, inherit_credentials):
        assert inherit_credentials is True
        assert not {'TEST_RUN_TOKEN', 'TEST_RUNTIME_TOKEN', 'TEST_AGENT_PRIVATE_KEY', 'HERMES_REQUIRED_LAUNCH_BINDING'} & base.keys()
        if not observed:  # PluginHost retains its pre-existing hermes_subprocess_env scrub.
            assert 'GH_TOKEN' not in base and 'GATEWAY_RELAY_TOKEN' not in base
        observed.append('base-stripped')
        result = native(base=base, target_home=target_home, inherit_credentials=inherit_credentials)
        assert result['OPENAI_API_KEY'] == 'synthetic-incumbent-provider-key'
        result.update({name: env[name] for name in ('TEST_RUN_TOKEN', 'TEST_RUNTIME_TOKEN', 'TEST_AGENT_PRIVATE_KEY')})
        return result
    monkeypatch.setattr(local, 'served_profile_child_env', overlay)
    monkeypatch.setattr(plugin_host, '_hosted_ambient_credentials', lambda home: {
        'GH_TOKEN': 'synthetic-hosted-provider-key', 'TEST_RUNTIME_TOKEN': env['TEST_RUNTIME_TOKEN']})
    host = plugin_host.PluginHost(SimpleNamespace(home_path=str(home)))
    child = host._env()
    assert child['GH_TOKEN'] == 'synthetic-hosted-provider-key'
    assert child['OPENAI_API_KEY'] == 'synthetic-incumbent-provider-key'
    assert not {'TEST_RUN_TOKEN', 'TEST_RUNTIME_TOKEN', 'TEST_AGENT_PRIVATE_KEY', 'HERMES_REQUIRED_LAUNCH_BINDING'} & child.keys()
    spawned = []
    def capture(command, **kw):
        spawned.append(kw['env'])
        return SimpleNamespace(pid=12345)
    monkeypatch.setattr(gateway_runtime_start, 'start_gateway_job', lambda *a, **kw: None)
    monkeypatch.setattr(gateway_runtime_start.subprocess, 'Popen', capture)
    gateway_runtime_start.spawn_unmanaged_gateway(home, deadline=time.monotonic() + 10)
    assert len(spawned) == 1 and observed == ['base-stripped', 'base-stripped']
    assert spawned[0]['OPENAI_API_KEY'] == 'synthetic-incumbent-provider-key'
    assert not {'TEST_RUN_TOKEN', 'TEST_RUNTIME_TOKEN', 'TEST_AGENT_PRIVATE_KEY', 'HERMES_REQUIRED_LAUNCH_BINDING'} & spawned[0].keys()
    assert os.environ['TEST_RUN_TOKEN'] == env['TEST_RUN_TOKEN']


@pytest.mark.asyncio
async def test_binding_owner_replacement_cannot_accept_old_launch(tmp_path, monkeypatch):
    from gateway.session_authorities import owner_scope
    from hermes_cli.plugins_launch_credentials import declarations, manifest_declarations
    owner, connection = await _owner(tmp_path / 'home', monkeypatch)
    try:
        params = _params(owner)
        with owner_scope(owner):
            assert 'test-orchestrator' in declarations()
            original = manifest_declarations()['test-orchestrator']['declaration']
        replacement = copy.deepcopy(original)
        replacement['plugin_owner']['key'] = 'different-plugin'
        with pytest.raises(binding.LaunchCredentialError, match='declaration_changed'):
            binding.validate(replacement, params[binding.PRIVATE_FIELD])
        from hermes_cli.plugins import get_plugin_manager
        with owner_scope(owner):
            entry = get_plugin_manager()._launch_credential_bindings['test-orchestrator']
            entry['plugin_key'] = 'different-plugin'
            from hermes_cli.plugins_launch_credentials import declaration_for
            with pytest.raises(binding.LaunchCredentialError, match='plugin_unavailable'):
                declaration_for('test-orchestrator')
    finally:
        await connection.close()
        owner.db.close()


@pytest.mark.parametrize('target_binding', ['absent', 'different'])
def test_child_removal_follows_launch_profile_not_routed_profile(tmp_path, monkeypatch, target_binding):
    from hermes_cli.plugin_host import PluginHost
    from hermes_cli.plugins_loader import _plugin_home_scope
    from hermes_cli import gateway_runtime_start
    from tools.environments import local
    from hermes_cli import plugins_launch_credentials
    from hermes_constants import get_hermes_home
    launch, target = tmp_path / 'launch', tmp_path / 'target'
    _profile(launch)
    target_plugin = _profile(target)
    data = yaml.safe_load((target_plugin / 'plugin.yaml').read_text())
    if target_binding == 'absent':
        data.pop('launch_credentials')
    else:
        data['launch_credentials']['test-orchestrator']['credentials'][0]['env'] = 'OTHER_RUN_TOKEN'
    (target_plugin / 'plugin.yaml').write_text(yaml.safe_dump(data))
    monkeypatch.setenv('HERMES_HOME', str(launch))
    for key, value in _environment().items():
        monkeypatch.setenv(key, value)
    native_metadata = plugins_launch_credentials.assert_tool_destinations
    metadata_homes = []
    def launch_metadata(spec):
        metadata_homes.append(get_hermes_home().resolve())
        assert metadata_homes[-1] == launch.resolve()
        return native_metadata(spec)
    monkeypatch.setattr(plugins_launch_credentials, 'assert_tool_destinations', launch_metadata)
    native = local.served_profile_child_env
    observed = []
    def capture(*, base, target_home, inherit_credentials):
        assert not {'TEST_RUN_TOKEN', 'TEST_RUNTIME_TOKEN', 'TEST_AGENT_PRIVATE_KEY', 'HERMES_REQUIRED_LAUNCH_BINDING'} & base.keys()
        observed.append(str(target_home))
        return native(base=base, target_home=target_home, inherit_credentials=inherit_credentials)
    monkeypatch.setattr(local, 'served_profile_child_env', capture)
    with _plugin_home_scope(target):
        child = PluginHost(SimpleNamespace(home_path=str(target)))._env()
    assert observed == [str(target)]
    assert not {'TEST_RUN_TOKEN', 'TEST_RUNTIME_TOKEN', 'TEST_AGENT_PRIVATE_KEY', 'HERMES_REQUIRED_LAUNCH_BINDING'} & child.keys()
    spawned = []
    monkeypatch.setattr(gateway_runtime_start, 'start_gateway_job', lambda *a, **kw: None)
    def start(command, **kw):
        spawned.append(kw['env'])
        return SimpleNamespace(pid=12345)
    monkeypatch.setattr(gateway_runtime_start.subprocess, 'Popen', start)
    with _plugin_home_scope(target):
        gateway_runtime_start.spawn_unmanaged_gateway(target, deadline=time.monotonic() + 10)
    assert len(spawned) == 1 and observed == [str(target), str(target)]
    assert len(metadata_homes) >= 2
    assert not {'TEST_RUN_TOKEN', 'TEST_RUNTIME_TOKEN', 'TEST_AGENT_PRIVATE_KEY', 'HERMES_REQUIRED_LAUNCH_BINDING'} & spawned[0].keys()


@pytest.mark.parametrize('drift', ['declaration', 'binding', 'origin', 'marker_removed'])
def test_manifest_drift_after_preflight_refuses_any_child_start(tmp_path, monkeypatch, drift):
    from hermes_cli.plugin_host import PluginHost
    from hermes_cli.plugins_launch_credentials import verify_required_binding
    from hermes_cli import gateway_runtime_start
    home = tmp_path / 'home'
    plugin = _profile(home)
    monkeypatch.setenv('HERMES_HOME', str(home))
    for key, value in _environment().items():
        monkeypatch.setenv(key, value)
    verify_required_binding()
    if drift == 'declaration':
        data = yaml.safe_load((plugin / 'plugin.yaml').read_text())
        data['launch_credentials']['test-orchestrator']['credentials'][0]['env'] = 'OTHER_RUN_TOKEN'
        (plugin / 'plugin.yaml').write_text(yaml.safe_dump(data))
    elif drift == 'binding':
        monkeypatch.setenv('HERMES_REQUIRED_LAUNCH_BINDING', 'other-binding')
    elif drift == 'origin':
        other = tmp_path / 'other'
        _profile(other)
        monkeypatch.setenv('HERMES_HOME', str(other))
    else:
        monkeypatch.delenv('HERMES_REQUIRED_LAUNCH_BINDING')
    attempted = []
    monkeypatch.setattr(gateway_runtime_start.subprocess, 'Popen', lambda *a, **kw: attempted.append(True))
    with pytest.raises(binding.LaunchCredentialError, match='owner_changed|plugin_unavailable'):
        PluginHost(SimpleNamespace(home_path=str(home))).ensure_started()
    with pytest.raises(binding.LaunchCredentialError, match='owner_changed|plugin_unavailable'):
        gateway_runtime_start.spawn_unmanaged_gateway(home, deadline=time.monotonic() + 10)
    assert not attempted
