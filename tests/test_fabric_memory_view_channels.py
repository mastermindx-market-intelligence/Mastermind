"""Prospective v3 restrictions through real incumbent owner and inert SQLite.

The v3 rows below are deliberately NOT issuer-authenticated fixtures. They
exercise fail-closed disclosure, not issuance, source rights, participant origin,
study admission or a deployed M2/Linux transport. No live operation is read.
"""
import copy
import io
import json
from unittest import mock

import pytest
from tests.test_fabric_participant_owner import case, participant, reserve, _native_owner_modules
import importlib

@pytest.fixture(scope="module",autouse=True)
def _view_native_modules(_native_owner_modules):
    global owner_module,view,fabric_task,artifact_delivery
    owner_module=importlib.import_module('fabric_operator_owner')
    view=importlib.import_module('fabric_memory_view')
    fabric_task=importlib.import_module('fabric_task')
    artifact_delivery=importlib.import_module('artifact_delivery')
    yield



def bind_unissued_v3(c):
    c['owner'].reserve(c['cap']['token'], c['request'])
    stored = {'schema': view.SCHEMA, 'request': c['request'],
              'participant': {'private_audit': 'NEVER_DISCLOSE_RAW_AUDIT',
                              'peer_rating': 'NEVER_DISCLOSE_PEER'}}
    raw = owner_module.canonical(stored)
    with c['owner'].transaction() as con:
        con.execute('UPDATE operator_child_authorizations SET request_json=?,request_digest=? WHERE run_id=?',
                    (raw, owner_module.digest(raw.encode()), c['request']['run_id']))
    return stored


@pytest.mark.parametrize('channel', ['status', 'result', 'wait', 'returns', 'acknowledge', 'child_binding'])
def test_generic_owner_channels_refuse_before_original_read(case, channel):
    bind_unissued_v3(case)
    o, token, rid = case['owner'], case['cap']['token'], case['request']['run_id']
    with mock.patch.object(fabric_task, 'inspect_run', side_effect=AssertionError('no original status read')), \
         mock.patch.object(fabric_task, 'read_result', side_effect=AssertionError('no original result read')):
        with pytest.raises(owner_module.DelegationRefused, match=view.VIEW_REQUIRED):
            if channel in ('status', 'result'): o.observe(token, channel, rid)
            elif channel == 'wait': o.wait(token, rid, 1)
            elif channel == 'returns': o.returns(token)
            elif channel == 'acknowledge': o.acknowledge(token, rid, 'a' * 64)
            else: o.child_binding(token, rid)
    with o.transaction() as con:
        row = con.execute('SELECT acknowledged_sha256 FROM operator_child_authorizations WHERE run_id=?', (rid,)).fetchone()
        assert row['acknowledged_sha256'] is None


@pytest.mark.parametrize('extra', [None, 'packet', 'condition', 'role', 'source', 'authenticated', 'disagreement', 'issuer'])
def test_no_caller_value_can_mint_issuer_or_consume_child_budget(case, extra):
    o, token = case['owner'], case['cap']['token']
    before = o.describe(token)
    lookup = {'run_id': case['request']['run_id']}
    if extra is not None: lookup[extra] = True
    with mock.patch.object(owner_module.subprocess, 'Popen', side_effect=AssertionError('no dispatch')):
        with pytest.raises(owner_module.DelegationRefused):
            o.dispatch_memory_participant(token, lookup)
    assert o.describe(token) == before
    assert not list((case['here'] / 'state/remote_sub').iterdir())


def test_dedicated_result_requires_actual_issuer_not_generic_complete_bytes(case):
    bind_unissued_v3(case)
    with mock.patch.object(fabric_task, 'inspect_run', side_effect=AssertionError('no original read')), \
         mock.patch.object(fabric_task, 'read_result', side_effect=AssertionError('no raw bytes')):
        with pytest.raises(owner_module.DelegationRefused, match=view.ISSUER_UNAVAILABLE):
            case['owner'].memory_participant_result(case['cap']['token'], {'run_id': case['request']['run_id']})


@pytest.mark.parametrize('defect', ['digest', 'duplicate', 'noncanonical'])
def test_mutated_authorization_never_falls_back_to_generic(case, defect):
    stored = bind_unissued_v3(case)
    raw = owner_module.canonical(stored)
    if defect == 'duplicate': raw = '{"schema":"old",' + raw[1:]
    elif defect == 'noncanonical': raw += ' '
    digest = 'a' * 64 if defect == 'digest' else owner_module.digest(raw.encode())
    with case['owner'].transaction() as con:
        con.execute('UPDATE operator_child_authorizations SET request_json=?,request_digest=? WHERE run_id=?',
                    (raw, digest, case['request']['run_id']))
    with mock.patch.object(fabric_task, 'inspect_run', side_effect=AssertionError('no original read')):
        with pytest.raises(owner_module.DelegationRefused):
            case['owner'].observe(case['cap']['token'], 'result', case['request']['run_id'])


@pytest.mark.parametrize('channel', ['inspect', 'result', 'wait', 'cli_status', 'cli_result', 'cli_artifacts', 'cli_continue', 'artifact_qualify', 'artifact_current', 'artifact_observe'])
def test_actual_generic_adapters_refuse_bound_run_before_reader_or_transport(case, monkeypatch, channel):
    bind_unissued_v3(case)
    monkeypatch.setattr(fabric_task, 'HERE', case['here'])
    monkeypatch.setattr(artifact_delivery, 'HERE', case['here'])
    rid = case['request']['run_id']
    with mock.patch.object(fabric_task, '_inspect_run', side_effect=AssertionError('no private status')), \
         mock.patch.object(fabric_task, '_result_snapshot', side_effect=AssertionError('no private result')), \
         mock.patch.object(artifact_delivery, 'transport', side_effect=AssertionError('no remote transport')):
        if channel == 'inspect':
            with pytest.raises(owner_module.DelegationRefused): fabric_task.inspect_run(rid)
        elif channel == 'result':
            with pytest.raises(owner_module.DelegationRefused): fabric_task.read_result(rid)
        elif channel == 'wait':
            with pytest.raises(owner_module.DelegationRefused): fabric_task.wait_for(rid, timeout=1, interval=1)
        elif channel.startswith('cli_'):
            args = {'cli_status': ['status', rid], 'cli_result': ['result', rid],
                    'cli_artifacts': ['artifacts', rid, '--root', 'inert-root', '--parent', 'inert-operator', '--host', 'ubuntu0', '--stdout-sha256', 'a'*64, '--destination', '/tmp/unused', '--path', '/tmp/unused/file'],
                    'cli_continue': ['status', rid, '--follow']}[channel]
            assert fabric_task.main(args) == 75
        elif channel == 'artifact_qualify':
            with pytest.raises(owner_module.DelegationRefused): artifact_delivery.qualify({'run_id': rid})
        else:
            flag = '--current-output' if channel == 'artifact_current' else '--observe-run'
            monkeypatch.setattr(owner_module.sys, 'argv', ['artifact_delivery.py', flag, rid, '--root', 'inert-root', '--destination', '/tmp/unused'])
            assert artifact_delivery.main() == 75


def test_expired_or_wrong_operator_cannot_observe_v3(case):
    bind_unissued_v3(case)
    with mock.patch.object(fabric_task, 'inspect_run', side_effect=AssertionError('no status')):
        with pytest.raises(owner_module.DelegationRefused):
            case['owner'].memory_participant_result('0'*64, {'run_id': case['request']['run_id']})
        case['owner'].clock = lambda: 5000
        with pytest.raises(owner_module.DelegationRefused):
            case['owner'].memory_participant_result(case['cap']['token'], {'run_id': case['request']['run_id']})


def test_v1_v2_rows_remain_on_original_generic_path(case):
    _, binding = reserve(case)
    state = {'state': 'ACTIVE_OR_WAITING', 'result_available': False}
    with mock.patch.object(fabric_task, 'inspect_run', return_value=state):
        assert case['owner'].observe(case['cap']['token'], 'status', case['request']['run_id']) is state
    view.require_generic_channel(case['here'], case['request']['run_id'])


@pytest.mark.parametrize('defect', ['missing_database', 'missing_row', 'downgraded_row'])
def test_fixed_packet_marker_preserves_restriction_when_authorization_custody_is_lost(case, monkeypatch, defect):
    bind_unissued_v3(case)
    rid = case['request']['run_id']
    (case['here'] / 'state/remote_sub' / (rid + '.request.packet')).write_bytes(view.PACKET_PREFIX + b'PRIVATE_INPUT_NOT_READ_OR_RETURNED')
    if defect == 'missing_database':
        case['owner'].db.unlink()
    else:
        with case['owner'].transaction() as con:
            if defect == 'missing_row': con.execute('DELETE FROM operator_child_authorizations WHERE run_id=?', (rid,))
            else:
                raw = owner_module.canonical(case['request'])
                con.execute('UPDATE operator_child_authorizations SET request_json=?,request_digest=? WHERE run_id=?', (raw, owner_module.digest(raw.encode()), rid))
    monkeypatch.setattr(fabric_task, 'HERE', case['here'])
    with mock.patch.object(fabric_task, '_result_snapshot', side_effect=AssertionError('no result read')):
        with pytest.raises(owner_module.DelegationRefused): fabric_task.read_result(rid)


def test_generic_request_cannot_claim_new_packet_protocol_or_replace_existing_v3(case):
    o, token = case['owner'], case['cap']['token']
    request = dict(case['request'], packet=view.PACKET_PREFIX.decode() + 'caller data')
    before = o.describe(token)
    with pytest.raises(owner_module.DelegationRefused): o.reserve(token, request)
    assert o.describe(token) == before
    bind_unissued_v3(case)
    with mock.patch.object(owner_module.subprocess, 'Popen', side_effect=AssertionError('no dispatch')):
        with pytest.raises(owner_module.DelegationRefused): o.dispatch(token, case['request'])


def test_direct_observation_api_refuses_before_packet_log_or_environment_read(case, monkeypatch):
    import run_observation_delivery
    bind_unissued_v3(case)
    monkeypatch.setattr(artifact_delivery, 'HERE', case['here'])
    with mock.patch.object(artifact_delivery, 'local_file', side_effect=AssertionError('no private packet/log read')):
        with pytest.raises(owner_module.DelegationRefused, match=view.VIEW_REQUIRED):
            run_observation_delivery.artifact_snapshot(case['request']['run_id'], case['request']['root'])


def test_public_reclaim_api_cannot_use_private_status_to_bypass_view(case, monkeypatch):
    bind_unissued_v3(case)
    monkeypatch.setattr(fabric_task, 'HERE', case['here'])
    with mock.patch.object(fabric_task, '_inspect_run', side_effect=AssertionError('no private status')):
        with pytest.raises(owner_module.DelegationRefused, match=view.VIEW_REQUIRED):
            fabric_task.plan_accepted_macro_worktree_release(case['request']['run_id'], root_id=case['request']['root'], parent_run_id=case['request']['parent'], pinned_sha='a'*40)


@pytest.mark.parametrize('schema', ['mastermind.fabric_bound_child_authorization.v4', 'unknown', None])
def test_unknown_authorization_family_never_authorizes_generic_raw_result(case, schema):
    stored = bind_unissued_v3(case)
    stored['schema'] = schema
    raw = owner_module.canonical(stored)
    with case['owner'].transaction() as con:
        con.execute('UPDATE operator_child_authorizations SET request_json=?,request_digest=? WHERE run_id=?',
                    (raw, owner_module.digest(raw.encode()), case['request']['run_id']))
    with mock.patch.object(fabric_task, 'inspect_run', side_effect=AssertionError('no private status')):
        with pytest.raises(owner_module.DelegationRefused, match=view.VIEW_REQUIRED):
            case['owner'].observe(case['cap']['token'], 'result', case['request']['run_id'])


def test_exact_frozen_linux_packet_cannot_enter_ordinary_packet_dispatch(case):
    import base64
    from pathlib import Path
    fixture=json.loads((Path(__file__).parent/'fixtures/native_memory_packet_a6.json').read_bytes())
    packet=base64.b64decode(fixture['packet_base64'])
    assert packet.startswith(view.PACKET_PREFIX)
    request=dict(case['request'],packet=packet.decode())
    before=case['owner'].describe(case['cap']['token'])
    with mock.patch.object(owner_module.subprocess,'Popen',side_effect=AssertionError('no generic dispatch')):
        with pytest.raises(owner_module.DelegationRefused):case['owner'].dispatch(case['cap']['token'],request)
    assert case['owner'].describe(case['cap']['token'])==before
