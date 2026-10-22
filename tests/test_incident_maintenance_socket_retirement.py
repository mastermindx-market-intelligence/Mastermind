"""Maintenance retains full guards and truthfully reports socket mutation."""
import json
from types import SimpleNamespace as S
from unittest.mock import Mock

import pytest

from control_plane import executive_incident_maintenance as m
from scripts import executive_os_incident_maintenance as entry
from tests.test_incident_maintenance_transitions import world


@pytest.fixture
def residual(world, monkeypatch):
    candidate = object()
    events = []
    deadlines = []
    monkeypatch.setattr(m.retirement, '_candidate', Mock(return_value=candidate))
    def excluded(*, deadline_monotonic_ns):
        events.append('excluded')
        deadlines.append(deadline_monotonic_ns)
        return S(boot_id='same-boot', census=S(observer='own'))
    monkeypatch.setattr(m.host, '_observe_old_owner_exclusion', excluded)
    def retire(handles, observed):
        assert observed is candidate and handles is world.handles[0]
        events.append('rename')
        return ('retained-identity',)
    monkeypatch.setattr(m.retirement, '_retire', retire)
    monkeypatch.setattr(m.retirement, '_recheck_retained',
                        lambda handles, identity: events.append('retained-recheck'))
    return S(events=events, deadlines=deadlines, world=world)


@pytest.mark.parametrize('initial', ['LOADED_IDLE', 'UNLOADED'])
def test_retirement_is_bracketed_by_original_exclusion_and_same_deadline(residual, initial):
    residual.world.broker = initial
    result = m._stop_incident_broker()
    assert residual.events == ['excluded', 'rename', 'excluded', 'retained-recheck']
    assert len(set(residual.deadlines)) == 1
    assert result['socket_retirement_attempted'] is True
    assert result['origin_custody'] is result['provider_called'] is False
    assert residual.world.cleanup == residual.world.handles


@pytest.mark.parametrize('field,value', [('boot_id', 'other-boot'), ('observer', 'other-owner')])
def test_pre_retirement_owner_drift_forbids_rename(residual, monkeypatch, field, value):
    observation = S(boot_id='same-boot', census=S(observer='own'))
    setattr(observation if field == 'boot_id' else observation.census, field, value)
    monkeypatch.setattr(m.host, '_observe_old_owner_exclusion', Mock(return_value=observation))
    with pytest.raises(m.BrokerMaintenanceError, match='RETIREMENT_OWNER_DRIFT') as failure:
        m._stop_incident_broker()
    assert not failure.value.socket_retirement_attempted
    assert 'rename' not in residual.events


@pytest.mark.parametrize('case', ['content', 'source', 'arms', 'exclusion', 'deadline'])
def test_all_changed_pre_retirement_guards_precede_rename(residual, monkeypatch, case):
    if case == 'content': residual.world.content_drift_at = 4
    if case == 'source': residual.world.source_drift = True
    if case == 'arms':
        original = m._require_closed_arms
        calls = []
        def check(*args):
            calls.append(1)
            if len(calls) > 1: raise ValueError('changed arms')
            return original(*args)
        monkeypatch.setattr(m, '_require_closed_arms', check)
    if case == 'exclusion':
        monkeypatch.setattr(m.host, '_observe_old_owner_exclusion', Mock(side_effect=OSError('unqueryable')))
    if case == 'deadline':
        monkeypatch.setattr(m.retirement, '_candidate', Mock(side_effect=m.release.ReleaseObservationError('DEADLINE_EXCEEDED')))
    with pytest.raises(m.BrokerMaintenanceError) as failure:
        m._stop_incident_broker()
    assert not failure.value.socket_retirement_attempted
    assert 'rename' not in residual.events


@pytest.mark.parametrize('case', ['rename', 'retained', 'post_owner', 'post_content', 'cleanup'])
def test_failure_after_retirement_attempt_is_uncertain_even_when_already_unloaded(
    residual, monkeypatch, capsys, case,
):
    residual.world.broker = 'UNLOADED'
    if case == 'rename': monkeypatch.setattr(m.retirement, '_retire', Mock(side_effect=OSError('unknown rename')))
    if case == 'retained': monkeypatch.setattr(m.retirement, '_recheck_retained', Mock(side_effect=ValueError('changed')))
    if case == 'post_owner':
        monkeypatch.setattr(m.host, '_observe_old_owner_exclusion', Mock(side_effect=[
            S(boot_id='same-boot', census=S(observer='own')),
            S(boot_id='same-boot', census=S(observer='other'))]))
    if case == 'post_content': residual.world.content_drift_at = 4
    if case == 'cleanup': monkeypatch.setattr(m.namespace, '_release_namespace', Mock(side_effect=OSError('cleanup')))
    assert entry.main([]) == 75
    result = json.loads(capsys.readouterr().out)
    assert result['socket_retirement_attempted'] is True
    assert result['disable_attempted'] is result['bootout_attempted'] is False
    assert result['origin_custody'] is result['provider_called'] is False
    assert residual.world.commands == []
    assert residual.events.count('rename') <= 1


def test_missing_retirement_boolean_cannot_be_reported_success(monkeypatch, capsys):
    monkeypatch.setattr(entry, '_stop_incident_broker', Mock(return_value={
        'maintenance_state':'BROKER_STOPPED_OBSERVED', 'disable_attempted':False,
        'bootout_attempted':False, 'origin_custody':False, 'provider_called':False}))
    assert entry.main([]) == 75
    assert json.loads(capsys.readouterr().out)['socket_retirement_attempted'] is None


@pytest.mark.parametrize('initial', ['LOADED_IDLE', 'UNLOADED'])
def test_occupied_retained_slot_refuses_before_any_modifying_verb(world, monkeypatch, initial):
    world.broker = initial
    monkeypatch.setattr(m.retirement, '_require_retained_absent', Mock(
        side_effect=m.retirement.SocketRetirementError('BROKER_MAINTENANCE_RETAINED_SOCKET_OCCUPIED')))
    rename = Mock(side_effect=AssertionError('no rename permitted'))
    monkeypatch.setattr(m.retirement, '_retire', rename)
    with pytest.raises(m.BrokerMaintenanceError, match='RETAINED_SOCKET_OCCUPIED') as failure:
        m._stop_incident_broker()
    assert world.commands == []
    assert not failure.value.disable_attempted and not failure.value.bootout_attempted
    assert not failure.value.socket_retirement_attempted
    assert world.cleanup == world.handles and len(world.handles) == 1
    rename.assert_not_called()
