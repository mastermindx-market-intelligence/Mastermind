"""Explicit existing-service native-profile composition, all host IO fake/private."""
import asyncio
import copy
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from integrations.session_bridge.t3_reply_native_access import InstalledT3ReplyNativeAccess, validate_native_return_config
from integrations.session_bridge.reply_event_host_composition import validate_reply_event_host_config, build_installed_reply_event_host
from integrations.session_bridge.t3_dot_native_owner import NativeDotFleetOwner
from integrations.session_bridge.t3_native_client import Scope, Unavailable, Conflict, Rejected
from integrations.session_bridge.web_reply_subscription_owner import owner_key
from tests.test_t3_dot_native_owner import profile, Runner
from tests.test_session_bridge_reply_event_host_integration import authenticated_receiver
from tests.test_t3_reply_host import t3_host


@pytest.fixture
def native_access(tmp_path, authenticated_receiver):
    auth = authenticated_receiver
    value = profile()
    file = tmp_path / 'existing-native-profile.json'
    data = json.dumps(value).encode()
    file.write_bytes(data)
    file.chmod(0o600)
    config = {'enabled': True, 'profiles': [{'owner_key': owner_key(auth.principal),
        'profile_path': str(file), 'profile_sha256': hashlib.sha256(data).hexdigest()}]}
    runner, enabled, created = Runner(), [True], []
    def factory(*args, **kwargs):
        selected = NativeDotFleetOwner(*args, runner=runner, **kwargs)
        created.append(selected)
        return selected
    access = InstalledT3ReplyNativeAccess(auth.policies, config, owner_factory=factory,
                                         current_selection=lambda: enabled[0])
    scope = Scope(value['connection_id'], value['local_environment_id'], 'project-1')
    return auth, access, scope, runner, file, enabled, created, config


def test_original_oauth_account_uses_fixed_native_profile_and_reuses_only_catalog(native_access):
    auth, access, scope, runner, _, _, created, _ = native_access
    async def scenario():
        first = await access(auth.principal, scope)
        second = await access(auth.principal, scope)
        assert first.scope == second.scope == scope
        assert len(created) == 1
        assert len([call for call in runner.calls if 'native-catalog' in call.argv]) == 1
        assert all('t3_thread_launch' not in call.argv and 't3_thread_send' not in call.argv for call in runner.calls)
    asyncio.run(scenario())


def test_native_selection_disarm_is_checked_before_every_profile_access(native_access):
    auth, access, scope, runner, _, enabled, _, _ = native_access
    assert access.current(auth.principal) == auth.principal
    enabled[0] = False
    with pytest.raises(Unavailable): asyncio.run(access(auth.principal, scope))
    assert not runner.calls


def test_profile_digest_change_invalidates_cached_catalog_without_rebinding(native_access):
    auth, access, scope, runner, file, _, created, _ = native_access
    asyncio.run(access(auth.principal, scope))
    calls = len(runner.calls)
    file.write_bytes(file.read_bytes() + b' ')
    with pytest.raises((ValueError, Unavailable)): asyncio.run(access(auth.principal, scope))
    assert len(runner.calls) == calls and len(created) == 1


def test_foreign_account_or_connection_never_reaches_native_owner(native_access):
    auth, access, scope, runner, _, _, _, _ = native_access
    foreign = dataclasses.replace(auth.principal, subject_digest='e' * 64)
    with pytest.raises(ValueError): asyncio.run(access(foreign, scope))
    with pytest.raises(Conflict): asyncio.run(access(auth.principal, dataclasses.replace(scope, connection_id='other')))
    assert not runner.calls


def test_unknown_remote_environment_cannot_be_selected_by_a_request(native_access):
    auth, access, scope, runner, _, _, _, _ = native_access
    with pytest.raises(Rejected) as denied:
        asyncio.run(access(auth.principal, dataclasses.replace(scope, environment_id='not-enrolled')))
    assert denied.value.code == 'capability_denied'
    assert not runner.calls


def test_native_return_profile_requires_all_needed_read_capabilities(native_access):
    auth, access, scope, runner, file, _, _, config = native_access
    value = json.loads(file.read_text())
    value['operations'].remove('t3_questions_read')
    data = json.dumps(value).encode()
    file.write_bytes(data)
    config['profiles'][0]['profile_sha256'] = hashlib.sha256(data).hexdigest()
    access = InstalledT3ReplyNativeAccess(auth.policies, config, current_selection=lambda: True)
    with pytest.raises(Unavailable): asyncio.run(access(auth.principal, scope))
    assert not runner.calls


@pytest.mark.parametrize('change', [
    {'enabled': False}, {'enabled': 1}, {'profiles': []}, {'token': 'forbidden'},
    {'profiles': [{'owner_key': 'a' * 64, 'profile_path': '/safe/../other', 'profile_sha256': 'b' * 64}]},
])
def test_native_return_configuration_is_closed_and_has_no_credential_input(change):
    original = {'enabled': True, 'profiles': [{'owner_key': 'a' * 64,
                'profile_path': '/qualified/native.json', 'profile_sha256': 'b' * 64}]}
    with pytest.raises(ValueError): validate_native_return_config({**original, **change})


def test_duplicate_original_account_profile_is_ambiguous_not_a_fallback_pool():
    row = {'owner_key': 'a' * 64, 'profile_path': '/qualified/native.json', 'profile_sha256': 'b' * 64}
    with pytest.raises(ValueError): validate_native_return_config({'enabled': True, 'profiles': [row, row]})


def test_native_return_opt_in_does_not_expand_other_profiles():
    from ops.executive_os.executive_mcp_entry import validate_document
    from tests.test_executive_coo_install_binding import base_document
    base = base_document()
    assert validate_document(base).get('t3_returns_armed', False) is False
    for change in ({'t3_returns_armed': True}, {'t3_returns_armed': 'true'},
                   {'t3_returns_armed': True, 'reply_events_armed': True},
                   {'t3_returns_armed': True, 'executive_mcp_profile': 'web_ceo_v3'}):
        with pytest.raises(ValueError): validate_document({**base, **change})
    selected = validate_document({**base, 'executive_mcp_profile': 'web_ceo_v3',
                                  'reply_events_armed': True, 't3_returns_armed': True})
    assert selected['t3_returns_armed'] is True


def test_service_disarm_accepts_no_hidden_native_profile_or_key_inputs(native_access):
    *_, config = native_access
    assert validate_reply_event_host_config(None) is None
    assert validate_reply_event_host_config({'armed': False}) is None
    with pytest.raises(ValueError): validate_reply_event_host_config({'armed': False, 'native_t3': config})
    explicit = {'armed': True, 'mcp_config_path': '/owner/receiver.json',
        'storage_key_path': '/owner/subscription.key', 'storage_key_id': 'existing', 'native_t3': config}
    assert validate_reply_event_host_config(explicit)['native_t3'] == config


def test_actual_host_factory_attaches_source_and_monitor_only_after_both_selections(t3_host, native_access, monkeypatch):
    from integrations.session_bridge import reply_event_host_composition as module
    from integrations.session_bridge.runtime_reply_subscriptions import ExecutiveReplyCipher
    case = t3_host
    *_, config = native_access
    selected = [True]
    case.auth.policies.native_returns_selected = lambda: selected[0]
    monkeypatch.setattr(module, 'InstalledReplyPolicySelection', lambda *a, **k: case.auth.policies)
    monkeypatch.setattr(module, '_provisioned_cipher', lambda *a, **k: ExecutiveReplyCipher('fixture', b'x' * 32))
    value = {'armed': True, 'mcp_config_path': '/owner/receiver.json',
        'storage_key_path': '/owner/subscription.key', 'storage_key_id': 'existing', 'native_t3': config}
    host = build_installed_reply_event_host(case.runtime, value, release_sha='a' * 40,
        peer_uid=450, dialogue_socket_path=case.owner.socket_path, native_owner_configured=lambda: False)
    assert host.returns.t3_replies is not None
    assert host.t3_monitor is not None
    assert not host.t3_monitor.observers  # Composition alone has no subscriptions or native effects.
    assert not case.sent
    selected[0] = False
    with pytest.raises((ValueError, Unavailable)):
        host.returns.t3_replies.current(case.auth.principal)
