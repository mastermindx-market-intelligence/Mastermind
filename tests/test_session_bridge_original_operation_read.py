"""Original-operation recovery over real Runtime provenance; no live proof."""
import asyncio
import dataclasses
from pathlib import Path

import pytest

from integrations.session_bridge.native_read import NativeReplyReader
from integrations.session_bridge.return_tools import NativeReplyReadTool
from integrations.session_bridge.schemas import BridgeError
from test_session_bridge_runtime_return import setup, populate


def tool(s):
    return NativeReplyReadTool(NativeReplyReader(
        s.owner, socket_path=Path('/private/tmp/original-operation-read.sock'),
        service_call=s.service))


def events(s):
    return [e.to_dict() for e in s.runtime.events.list_events(job_id=s.epoch.job_id)]


def test_lost_read_ref_recovers_exact_reply_using_original_operation_only(setup):
    s = setup
    expected_ref = populate(s)
    before = events(s)
    s.service.calls.clear()
    result = asyncio.run(tool(s).handle(s.principal, 'session_reply_read',
        {'operation_key': s.args['operation_key']}))
    assert result['ok'] is True
    assert result['data']['read_ref'] == expected_ref
    assert result['data']['text'] == 'The bounded finding is confirmed.'
    assert result['data']['reply_committed'] is True
    assert result['data']['parent_consumed'] is False
    assert s.service.calls and all(c['operation'] == 'read_thread' for c in s.service.calls)
    assert events(s) == before


def test_reference_resolution_uses_original_provenance_without_target_revival(setup):
    s = setup
    expected_ref = populate(s)
    before = events(s)
    s.enabled[0] = False
    s.service.calls.clear()
    assert s.owner.resolve_operation_read_ref(principal=s.projection,
        operation_key=s.args['operation_key']) == expected_ref
    assert not s.service.calls
    assert events(s) == before


@pytest.mark.parametrize('change', [
    {'subject_digest': 'f' * 64}, {'client_ref': 'foreign'},
    {'issuer_digest': 'f' * 64}, {'resource': 'https://foreign.invalid'},
    {'scopes': ()}, {'expires_at': 1},
])
def test_original_operation_does_not_disclose_foreign_or_expired_provenance(setup, change):
    s = setup
    populate(s)
    before = events(s)
    s.service.calls.clear()
    result = asyncio.run(tool(s).handle(dataclasses.replace(s.principal, **change),
        'session_reply_read', {'operation_key': s.args['operation_key']}))
    assert result['ok'] is False
    assert result['error']['code'] == 'reply_unavailable'
    assert not s.service.calls
    assert events(s) == before


@pytest.mark.parametrize('args', [
    {'operation_key': ''}, {'operation_key': 'a' * 257}, {'operation_key': 1},
    {'operation_key': 'bad key'}, {'operation_key': 'original', 'read_ref': 'reply'},
    {'operation_key': 'original', 'resubmit': True},
    {'operation_key': 'original', 'target_ref': 'new'},
])
def test_invalid_operation_reads_fail_before_any_owner_effect(setup, args):
    s = setup
    before = events(s)
    result = asyncio.run(tool(s).handle(s.principal, 'session_reply_read', args))
    assert result['ok'] is False
    assert result['error']['code'] == 'invalid_input'
    assert not s.service.calls
    assert events(s) == before


def test_unknown_original_operation_does_not_create_provenance(setup):
    s = setup
    before = events(s)
    result = asyncio.run(tool(s).handle(s.principal, 'session_reply_read',
        {'operation_key': 'never-submitted'}))
    assert result['ok'] is False
    assert result['error']['code'] == 'reply_unavailable'
    assert not s.service.calls
    assert events(s) == before
