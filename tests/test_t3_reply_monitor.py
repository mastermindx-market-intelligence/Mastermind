"""Real Runtime/subscription/delivery ownership; fake native and HTTPS peers."""
import asyncio
import copy
import dataclasses
import json

import pytest

from integrations.session_bridge.t3_reply_monitor import RuntimeT3ReplyMonitor
from integrations.session_bridge.t3_native_watch import T3NativeReturnWait
from integrations.session_bridge.t3_native_client import Run, Thread, Scope, T3NativeClient, Unavailable
from integrations.session_bridge.t3_reply_events import T3ReturnEffectUnknown
from integrations.session_bridge.web_reply_event_rpc import EventSubscribeRequest, EventUnsubscribeRequest
from tests.test_t3_reply_host import t3_host, pending_question, URL, SECRET
from tests.test_t3_native_client import THREAD, SCOPE, Native, SCHEMAS, schema
from tests.test_session_bridge_reply_event_host_integration import authenticated_receiver


def enable(case):
    def observer(*args, **kwargs):
        return T3NativeReturnWait(*args, **kwargs, timeout_ms=1, minimum_interval_seconds=0.01)
    case.host.t3_monitor = RuntimeT3ReplyMonitor(case.host, observer_factory=observer)
    return case.host.t3_monitor


async def subscribe(case, *, url=URL, request_ref=None):
    req = EventSubscribeRequest(request_ref or case.binding['request_ref'], url, SECRET, 600000)
    value = await case.host.handle_frame(case.frame('subscribe', req))
    assert value['ok'] is True, value
    return value['data']


async def until(predicate):
    for _ in range(300):
        if predicate(): return
        await asyncio.sleep(0.01)
    raise AssertionError('bounded fake-native observation did not reach expected state')


def test_subscribe_automatically_observes_final_native_reply_and_sends_once(t3_host):
    case = t3_host
    async def scenario():
        monitor = enable(case)
        await subscribe(case)
        await until(lambda: len(case.sent) == 2)
        await until(lambda: all(o.task.done() for o in monitor.observers.values()))
        assert len(monitor.observers) == 1
        assert case.sent[-1][0]['data']['message_key'].startswith('t3-native-reply-')
        assert case.sent[-1][0]['data']['parent_consumed'] is False
        original = next(iter(monitor.observers.values()))
        await monitor.reconcile()
        assert next(iter(monitor.observers.values())) is original
        assert len(case.sent) == 2
        assert all(name not in {'t3_thread_launch', 't3_thread_send', 't3_thread_interrupt'} for name, _ in case.native.calls)
        await case.host.close_native_returns()
    asyncio.run(scenario())


def test_question_then_final_are_observed_without_manual_producer_call(t3_host):
    case = t3_host
    question = pending_question(case)
    previous = case.native.responses['t3_pending_request']
    case.native.responses['t3_pending_request'] = lambda args: (
        {'structuredContent': {'requestIds': ['pending-1']}} if args['action'] == 'list' else previous(args))
    async def scenario():
        monitor = enable(case)
        await subscribe(case)
        await until(lambda: len(case.sent) == 2)
        assert case.sent[-1][0]['data']['message_key'].startswith('t3-native-question-')
        await until(lambda: next(iter(monitor.observers.values())).observations >= 2)
        assert len(case.sent) == 2  # Unchanged question cannot cause duplicate sends.
        question['status'] = 'resolved'
        case.native.detail['thread'].update(status='completed', activeRunId=None, pendingRequestCount=0)
        case.native.responses['t3_thread_wait']['structuredContent'].update(status='completed', timedOut=False)
        await until(lambda: len(case.sent) == 3)
        assert case.sent[-1][0]['data']['message_key'].startswith('t3-native-reply-')
        assert case.sent[-1][0]['data']['read_ref'] == case.sent[1][0]['data']['read_ref']
        await case.host.close_native_returns()
    asyncio.run(scenario())


def test_current_subscribers_to_same_run_share_one_native_observer(t3_host):
    case = t3_host
    pending_question(case)
    case.native.responses['t3_pending_request'] = {'structuredContent': {'requestIds': []}}
    async def scenario():
        monitor = enable(case)
        first = await subscribe(case)
        second = await subscribe(case, url=URL + '/second')
        assert first['subscription_id'] != second['subscription_id']
        assert len(monitor.observers) == 1
        observer = next(iter(monitor.observers.values()))
        await until(lambda: observer.observations >= 1)
        await monitor.reconcile()
        assert next(iter(monitor.observers.values())) is observer
        await case.host.close_native_returns()
    asyncio.run(scenario())


def test_unsubscribe_removes_only_its_original_source_and_stops_last_observer(t3_host):
    case = t3_host
    pending_question(case)
    case.native.responses['t3_pending_request'] = {'structuredContent': {'requestIds': []}}
    async def scenario():
        monitor = enable(case)
        first = await subscribe(case)
        second = await subscribe(case, url=URL + '/second')
        observer = next(iter(monitor.observers.values()))
        for subscription, url, remaining in ((first, URL, 1), (second, URL + '/second', 0)):
            req = EventUnsubscribeRequest(request_ref=case.binding['request_ref'], callback_url=url)
            value = await case.host.handle_frame(case.frame('unsubscribe', req))
            assert value['ok'] is True, value
            assert len(monitor.observers) == remaining
        assert observer.task.done()
        assert len(case.sent) == 2  # Two verification challenges, no event send.
        await case.host.close_native_returns()
    asyncio.run(scenario())


def test_restart_uses_retained_subscription_without_new_callback_registration(t3_host):
    case = t3_host
    async def scenario():
        await subscribe(case)  # Original owner not monitoring yet.
        assert len(case.sent) == 1
        case.host = case.make_host()
        monitor = enable(case)
        await case.host.start_native_returns()
        await until(lambda: len(case.sent) == 2)
        assert len(monitor.observers) == 1
        assert len([p for p, _ in case.sent if p.get('type') == 'verification']) == 1
        await case.host.close_native_returns()
    asyncio.run(scenario())


def test_expired_subscriber_stops_native_observation_without_callback(t3_host):
    case = t3_host
    pending_question(case)
    case.native.responses['t3_pending_request'] = {'structuredContent': {'requestIds': []}}
    async def scenario():
        monitor = enable(case)
        await subscribe(case)
        observer = next(iter(monitor.observers.values()))
        await until(lambda: observer.observations >= 1)
        case.auth.now[0] += 3601
        await until(lambda: observer.task.done())
        assert observer.state == 'STOPPED'
        assert len(case.sent) == 1
        assert not case.host.store.active_subscriptions()
        await case.host.close_native_returns()
    asyncio.run(scenario())


def test_denied_native_access_stops_without_automatic_reconnect_or_worker_replay(t3_host):
    case = t3_host
    async def scenario():
        await subscribe(case)
        async def denied(*args): raise Unavailable('native grant revoked')
        case.source.native_client = denied
        monitor = enable(case)
        await monitor.reconcile()
        observer = next(iter(monitor.observers.values()))
        await until(lambda: observer.task.done())
        assert observer.state == 'UNAVAILABLE'
        await monitor.reconcile()
        assert next(iter(monitor.observers.values())) is observer
        assert len(case.sent) == 1
        await case.host.close_native_returns()
    asyncio.run(scenario())


def test_monitor_capacity_refuses_without_starting_an_unbounded_subset(t3_host):
    case = t3_host
    async def scenario():
        monitor = enable(case)
        monitor.maximum_original_runs = 0  # Fault-injection of the runtime limit.
        await subscribe(case)
        assert not monitor.observers
        assert monitor.last_error == 'ORIGINAL_NATIVE_OBSERVATION_UNAVAILABLE'
        assert len(case.sent) == 1
        await case.host.close_native_returns()
    asyncio.run(scenario())


def test_monitor_does_not_activate_without_explicit_host_selection(t3_host):
    case = t3_host
    async def scenario():
        await subscribe(case)
        assert case.host.t3_monitor is None
        result = await case.host.start_native_returns()
        assert result['state'] == 'NOT_SELECTED'
        assert len(case.sent) == 1
    asyncio.run(scenario())


def test_native_wait_failure_and_unknown_commit_are_terminal_no_replay(t3_host):
    case = t3_host
    async def scenario():
        for unknown in (False, True):
            calls = []
            async def resolve(): return case.auth.principal, Run(THREAD, 'run-1', 'original-request', 'launched'), case.client
            async def consume(*args):
                calls.append('consume')
                if unknown: raise T3ReturnEffectUnknown('observe', case.binding['request_ref'], case.binding['read_ref'])
                raise Unavailable('native source unavailable')
            observer = T3NativeReturnWait(resolve, consume, capacity=asyncio.Semaphore(1), timeout_ms=1,
                                          minimum_interval_seconds=0.01)
            await observer.start()
            await observer.task
            assert observer.state == ('EFFECT_UNKNOWN' if unknown else 'UNAVAILABLE')
            assert calls == ['consume']
            with pytest.raises(Unavailable): await observer.start()
            await observer.close()
            assert observer.state == ('EFFECT_UNKNOWN' if unknown else 'UNAVAILABLE')
    asyncio.run(scenario())


def test_close_drains_admitted_result_effect_instead_of_cancelling_it(t3_host):
    case = t3_host
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def resolve(): return case.auth.principal, Run(THREAD, 'run-1', 'original-request', 'launched'), case.client
        async def consume(*args):
            entered.set()
            await release.wait()
            return False
        observer = T3NativeReturnWait(resolve, consume, capacity=asyncio.Semaphore(1), timeout_ms=1,
                                      minimum_interval_seconds=0.01)
        await observer.start()
        await entered.wait()
        closing = asyncio.create_task(observer.close())
        await asyncio.sleep(0)
        assert not closing.done()
        assert not observer.task.cancelled()
        release.set()
        await closing
        assert observer.state == 'STOPPED'
    asyncio.run(scenario())


def test_native_wait_is_capped_below_remaining_original_invocation_budget(t3_host):
    case = t3_host
    class BudgetedRead:
        def remaining_wait_ms(self): return 1200
        async def __call__(self, name, arguments): return await case.native(name, arguments)
    async def scenario():
        client = T3NativeClient(SCOPE, BudgetedRead(), SCHEMAS)
        async def resolve(): return case.auth.principal, Run(THREAD, 'run-1', 'original-request', 'launched'), client
        async def consume(*args): return False
        observer = T3NativeReturnWait(resolve, consume, capacity=asyncio.Semaphore(1))
        baseline_calls = len(case.native.calls)
        await observer.start()
        await observer.task
        waits = [args for name, args in case.native.calls[baseline_calls:] if name == 't3_thread_wait']
        assert len(waits) == 1 and waits[0]['timeoutMs'] == 950
        assert observer.state == 'STOPPED'
    asyncio.run(scenario())


@pytest.mark.parametrize('budget', [0, -1, True, 30001])
def test_unqualified_native_wait_budget_stops_before_native_call(t3_host, budget):
    case = t3_host
    class BudgetedRead:
        def remaining_wait_ms(self): return budget
        async def __call__(self, name, arguments): raise AssertionError('no native call allowed')
    async def scenario():
        client = T3NativeClient(SCOPE, BudgetedRead(), SCHEMAS)
        async def resolve(): return case.auth.principal, Run(THREAD, 'run-1', 'original-request', 'launched'), client
        async def consume(*args): raise AssertionError('no result effect allowed')
        observer = T3NativeReturnWait(resolve, consume, capacity=asyncio.Semaphore(1))
        await observer.start()
        await observer.task
        assert observer.state == 'UNAVAILABLE' and observer.observations == 0
    asyncio.run(scenario())
