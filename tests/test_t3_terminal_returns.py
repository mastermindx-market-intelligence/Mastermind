"""Terminal failures are facts, not invented worker answers or accepted work."""
import asyncio
import dataclasses
import json

import pytest

from integrations.session_bridge.t3_native_client import TERMINAL, Conflict, Unavailable
from integrations.session_bridge.t3_terminal_reply import observe, validate_public, READ_SCHEMA
from integrations.session_bridge.t3_reply_events import T3ReturnEffectUnknown
from integrations.session_bridge.native_read import NativeReplyReader
from integrations.session_bridge.return_tools import NativeReplyReadTool
from tests import test_session_bridge_installed as installed
from tests.test_t3_reply_host import t3_host
from tests.test_t3_reply_monitor import enable, subscribe, until
from tests.test_session_bridge_reply_event_host_integration import authenticated_receiver


def terminate(case, status):
    case.native.detail['thread'].update(status=status, activeRunId=None, pendingRequestCount=0)
    case.native.detail['items'] = []
    case.native.responses['t3_thread_wait'] = {'structuredContent': {
        'threadId': 'thread-1', 'runId': 'run-1', 'status': status, 'timedOut': False}}


@pytest.mark.parametrize('status', sorted(TERMINAL))
def test_terminal_status_reaches_original_subscriber_without_fabricated_answer(t3_host, status):
    case = t3_host
    terminate(case, status)
    async def scenario():
        monitor = enable(case)
        await subscribe(case)
        await until(lambda: len(case.sent) == 2)
        await until(lambda: all(o.task.done() for o in monitor.observers.values()))
        packet = case.sent[-1][0]
        assert packet['data']['message_key'].startswith('t3-native-status-')
        assert 'without a qualified answer' in packet['data']['summary']
        reader = NativeReplyReader(case.owner, socket_path=case.owner.socket_path,
            clock=lambda: case.auth.now[0], t3_replies=case.source)
        reply = await NativeReplyReadTool(reader).handle(installed.PRINCIPAL, 'session_reply_read',
            {'read_ref': packet['data']['read_ref'], 'message_key': packet['data']['message_key']})
        assert reply['ok'] is True, reply
        result = reply['data']
        assert result['schema'] == READ_SCHEMA and result['native_status'] == status
        assert result['native_terminal'] is True and result['answer_qualified'] is False
        assert result['successful'] is False and result['parent_consumed'] is False
        assert 'answer' not in result and 'error_message' not in result
        await case.host.close_native_returns()
    asyncio.run(scenario())


def test_terminal_observation_is_idempotent_and_read_does_not_create_events(t3_host):
    case = t3_host
    terminate(case, 'failed')
    async def scenario():
        first = await observe(case.source, case.auth.principal, case.binding['request_ref'])
        second = await observe(case.source, case.auth.principal, case.binding['request_ref'])
        assert first == second
        before = [event.to_dict() for event in case.runtime.store.list_events()]
        value = await case.source.read(case.auth.principal,
            {'read_ref': first['read_ref'], 'message_key': first['message_key']})
        assert value['successful'] is False
        assert [event.to_dict() for event in case.runtime.store.list_events()] == before
        assert len([row for row in before if row['event_type'] == 'T3_ORIGINAL_TERMINAL_OBSERVED']) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('status', ['running', 'queued', 'unknown', 'blocked'])
def test_nonterminal_or_unknown_status_cannot_be_declared_terminal(t3_host, status):
    case = t3_host
    terminate(case, status)
    before = len(case.runtime.store.list_events())
    with pytest.raises(Unavailable):
        asyncio.run(observe(case.source, case.auth.principal, case.binding['request_ref']))
    assert len(case.runtime.store.list_events()) == before


def test_timeout_does_not_prove_terminal_even_if_status_string_says_completed(t3_host):
    case = t3_host
    terminate(case, 'completed')
    case.native.responses['t3_thread_wait']['structuredContent']['timedOut'] = True
    with pytest.raises(Unavailable):
        asyncio.run(observe(case.source, case.auth.principal, case.binding['request_ref']))


def test_successful_answer_cannot_be_reclassified_as_no_answer_failure(t3_host):
    case = t3_host  # Native fixture has a complete original answer.
    with pytest.raises(Unavailable):
        asyncio.run(observe(case.source, case.auth.principal, case.binding['request_ref']))


def test_changed_terminal_status_never_substitutes_for_exact_notification(t3_host):
    case = t3_host
    terminate(case, 'failed')
    async def scenario():
        receipt = await observe(case.source, case.auth.principal, case.binding['request_ref'])
        terminate(case, 'cancelled')
        with pytest.raises(Conflict):
            await case.source.read(case.auth.principal,
                {'read_ref': receipt['read_ref'], 'message_key': receipt['message_key']})
    asyncio.run(scenario())


def test_terminal_status_is_not_default_successful_reply(t3_host):
    case = t3_host
    terminate(case, 'failed')
    async def scenario():
        receipt = await observe(case.source, case.auth.principal, case.binding['request_ref'])
        with pytest.raises(Unavailable):
            await case.source.read(case.auth.principal, {'read_ref': receipt['read_ref']})
    asyncio.run(scenario())


def test_foreign_account_and_expired_binding_cannot_read_terminal(t3_host):
    case = t3_host
    terminate(case, 'interrupted')
    async def scenario():
        receipt = await observe(case.source, case.auth.principal, case.binding['request_ref'])
        arguments = {key: receipt[key] for key in ('read_ref', 'message_key')}
        with pytest.raises((Unavailable, ValueError)):
            await case.source.read(dataclasses.replace(case.auth.principal, subject_digest='e' * 64), arguments)
        case.auth.now[0] += 3601
        with pytest.raises(Unavailable): await case.source.read(case.auth.principal, arguments)
    asyncio.run(scenario())


def test_terminal_public_contract_refuses_false_success_or_extra_error_text(t3_host):
    case = t3_host
    terminate(case, 'rolled_back')
    async def scenario():
        receipt = await observe(case.source, case.auth.principal, case.binding['request_ref'])
        value = await case.source.read(case.auth.principal,
            {key: receipt[key] for key in ('read_ref', 'message_key')})
        for delta in ({'successful': True}, {'answer_qualified': True}, {'parent_consumed': True},
                      {'answer': 'made up'}, {'error_message': 'private diagnostic'}, {'native_terminal': False}):
            with pytest.raises(ValueError): validate_public({**value, **delta})
    asyncio.run(scenario())


def test_terminal_lost_commit_ack_is_unknown_and_never_replays(t3_host, monkeypatch):
    case = t3_host
    terminate(case, 'failed')
    actual = case.runtime.events.get_event_by_command_id
    def lost(command):
        if command.startswith('t3-terminal-'): raise OSError('fixture lost ack')
        return actual(command)
    monkeypatch.setattr(case.runtime.events, 'get_event_by_command_id', lost)
    with pytest.raises(T3ReturnEffectUnknown):
        asyncio.run(observe(case.source, case.auth.principal, case.binding['request_ref']))
    events = [event for event in case.runtime.store.list_events() if event.event_type == 'T3_ORIGINAL_TERMINAL_OBSERVED']
    assert len(events) == 1
    assert not case.sent
