"""Closed installation shape: each invalid case starts from a qualified pair."""
from dataclasses import asdict
import pytest
from integrations.executive_content_contract import (
    ContentObserverProfile, ContentObserverProfiles, digest,
)
from test_executive_content_observer import profile


def pair(web=None):
    web = profile(client_ref='a' * 64) if web is None else web
    data = asdict(web)
    data.update(client_ref='c' * 64, permission_digest='d' * 64, operation_id='mac-operation')
    data['viewer_binding_digest'] = digest({key: data[key] for key in (
        'policy_id', 'issuer_digest', 'subject_digest', 'client_ref',
    )})
    data['profile_digest'] = digest({key: value for key, value in data.items() if key != 'profile_digest'})
    mac = ContentObserverProfile.from_mapping(data)
    return web, mac, {
        'schema': 'mastermind.executive_content_profiles.v1',
        'profiles': {
            'web': {'enabled': True, 'profile': asdict(web)},
            'mac': {'enabled': True, 'profile': asdict(mac)},
        },
    }


def test_typed_and_wire_roundtrip_disabled_retention_and_null():
    web, mac, value = pair()
    assert ContentObserverProfiles.from_mapping(value).to_mapping() == value
    typed = ContentObserverProfiles.from_mapping(value)
    assert ContentObserverProfiles.from_mapping(typed) == typed
    value['profiles']['web']['enabled'] = False
    assert ContentObserverProfiles.from_mapping(value).web.profile == web
    value['profiles']['web']['profile'] = None
    assert ContentObserverProfiles.from_mapping(value).web.profile is None


@pytest.mark.parametrize('field', ['client_ref', 'permission_digest', 'operation_id', 'viewer_binding_digest', 'profile_digest'])
def test_duplicate_binding_rejects_whole_config_even_if_disabled(field):
    web, mac, value = pair()
    value['profiles']['mac']['enabled'] = False
    data = value['profiles']['mac']['profile']
    data[field] = getattr(web, field)
    if field not in ('viewer_binding_digest', 'profile_digest'):
        data['viewer_binding_digest'] = digest({key: data[key] for key in (
            'policy_id', 'issuer_digest', 'subject_digest', 'client_ref',
        )})
        data['profile_digest'] = digest({key: v for key, v in data.items() if key != 'profile_digest'})
    with pytest.raises(ValueError):
        ContentObserverProfiles.from_mapping(value)


@pytest.mark.parametrize('field', ['installation_id', 'installation_generation', 'release_sha', 'policy_id', 'issuer_digest', 'source_ref', 'job_id', 'attempt_id', 'session_epoch_id', 'process_generation_id', 'local_turn_id'])
def test_mixed_installation_or_turn_rejects_whole_config(field):
    _, _, value = pair()
    data = value['profiles']['mac']['profile']
    data[field] = ('a' * len(data[field])) if field.endswith('sha') or field.endswith('digest') else data[field] + '-other'
    data['viewer_binding_digest'] = digest({key: data[key] for key in (
        'policy_id', 'issuer_digest', 'subject_digest', 'client_ref',
    )})
    data['profile_digest'] = digest({key: v for key, v in data.items() if key != 'profile_digest'})
    with pytest.raises(ValueError):
        ContentObserverProfiles.from_mapping(value)


@pytest.mark.parametrize('mutation', ['unknown', 'missing', 'integer', 'null_enabled', 'extra_slot_field'])
def test_closed_slot_shape(mutation):
    _, _, value = pair()
    if mutation == 'unknown':
        value['profiles']['other'] = value['profiles']['web']
    elif mutation == 'missing':
        del value['profiles']['mac']
    elif mutation == 'integer':
        value['profiles']['web']['enabled'] = 1
    elif mutation == 'null_enabled':
        value['profiles']['web']['profile'] = None
    else:
        value['profiles']['web']['principal'] = 'caller'
    with pytest.raises(ValueError):
        ContentObserverProfiles.from_mapping(value)


def test_both_profiles_restart_requires_new_owner_enrollment_operation(tmp_path):
    import asyncio
    from control_plane.executive_content_observer import ContentRefused, ExecutiveContentObserver
    from control_plane.visible_turn_projection import VisibleTurnProjection
    from integrations.executive_content_contract import ContentProfileKey, ACCESS_SCHEMA
    from test_steward_content_integration import fixture
    from test_executive_content_observer_reconcile import _DirectBroker

    clock, runtime, web, adapter, broker = fixture(tmp_path)
    web, mac, envelope = pair(web)
    observer = ExecutiveContentObserver(
        runtime=runtime, broker_client=_DirectBroker(broker),
        profile_loader=lambda: envelope, now=lambda: clock.value // 1000,
    )
    async def exercise():
        for key in (ContentProfileKey.web, ContentProfileKey.mac):
            assert (await observer.enroll(key))['status'] == 'ACTIVE'
        adapter.visible_turn_projection = VisibleTurnProjection()
        for key, selected in ((ContentProfileKey.web, web), (ContentProfileKey.mac, mac)):
            assert (await observer.status(key))['status'] == 'ABSENT'
            with pytest.raises(ContentRefused, match='GRANT_INVALIDATED'):
                await observer.enroll(key)
            assert not (await observer.handle_frame(selected.frame(ACCESS_SCHEMA)))['ok']
        assert not adapter.visible_turn_projection._grants
    asyncio.run(exercise())


def test_terminal_history_bound_evicts_authority_without_adapter_retention(tmp_path):
    import asyncio
    from dataclasses import replace
    from types import SimpleNamespace
    from control_plane.visible_turn_projection import VisibleTurnProjection
    from test_steward_content_integration import fixture
    from test_executive_content_observer_reconcile import _observer, _terminal_run_absent

    clock, runtime, web, adapter, broker = fixture(tmp_path)
    async def exercise():
        observer = _observer(runtime, broker, web, clock)
        await observer.enroll()
        generation = broker._operator_run.generation
        await _terminal_run_absent(broker, adapter)
        observation = broker._operator_terminal[web.process_generation_id][1]
        for index in range(33):
            next_generation = replace(generation, process_generation_id='history-' + str(index))
            state = SimpleNamespace(
                generation=next_generation,
                adapter=SimpleNamespace(visible_turn_projection=VisibleTurnProjection()),
            )
            await broker._remember_operator_terminal(state, observation)
        assert len(broker._operator_terminal) == 32
        assert web.process_generation_id not in broker._operator_terminal
        assert not hasattr(broker, '_observer_projection')
        assert (await observer.status())['status'] == 'ABSENT'
        assert (await observer.revoke())['status'] == 'ABSENT'
    asyncio.run(exercise())


def test_expired_profile_reconciles_enabled_and_disabled_slots(tmp_path):
    import asyncio
    from control_plane.executive_content_observer import ContentRefused, ExecutiveContentObserver
    from integrations.executive_content_contract import ContentProfileKey, epoch
    from test_steward_content_integration import fixture
    from test_executive_content_observer_reconcile import _DirectBroker

    clock, runtime, web, adapter, broker = fixture(tmp_path)
    web, mac, envelope = pair(web)
    observer = ExecutiveContentObserver(
        runtime=runtime, broker_client=_DirectBroker(broker),
        profile_loader=lambda: envelope, now=lambda: clock.value // 1000,
    )
    async def exercise():
        for key in (ContentProfileKey.web, ContentProfileKey.mac):
            await observer.enroll(key)
        observer.now = lambda: epoch(web.expires_at) + 1
        envelope['profiles']['web']['enabled'] = False
        for key in (ContentProfileKey.web, ContentProfileKey.mac):
            assert (await observer.status(key))['status'] == 'ACTIVE'
            assert (await observer.revoke(key))['status'] == 'REVOKED'
            with pytest.raises(ContentRefused, match='ACCESS_DENIED'):
                await observer.enroll(key)
    asyncio.run(exercise())
