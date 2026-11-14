"""Original-return observation on the existing Runtime subscription lifecycle.

Durable subscription, account authorization, source bindings and delivery effects
remain in their incumbent owners. This object holds only live read-task handles;
it never launches inference, stores messages, retries a failed source, or routes
workers. A restart derives work from accepted, unexpired subscriptions.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable

from .t3_native_client import Run, Conflict, Unavailable, TERMINAL
from .t3_native_watch import T3NativeReturnWait
from .t3_reply_events import is_t3_request_ref, is_t3_read_ref
from .web_reply_subscription_owner import owner_key, SubscriptionUnavailable
from .runtime_reply_authorization_owner import ObservedReplyPolicyDenial


def _key(principal, run: Run):
    scope = run.thread.scope
    return (owner_key(principal), scope.connection_id, scope.environment_id,
            scope.project_id, run.thread.thread_id, run.run_id)


class RuntimeT3ReplyMonitor:
    def __init__(self, host, *, maximum_native_waits=12, maximum_original_runs=64,
                 observer_factory: Callable = T3NativeReturnWait):
        from .installed_reply_events import RuntimeReplyEventHost
        if (type(host) is not RuntimeReplyEventHost or host.returns.t3_replies is None
                or type(maximum_native_waits) is not int or not 1 <= maximum_native_waits <= 16
                or type(maximum_original_runs) is not int or not 1 <= maximum_original_runs <= 128
                or not callable(observer_factory)):
            raise TypeError("Exact existing reply host and bounded native observation required")
        self.host, self.source = host, host.returns.t3_replies
        self.capacity = asyncio.Semaphore(maximum_native_waits)
        self.maximum_original_runs = maximum_original_runs
        self.observer_factory = observer_factory
        self.observers, self.targets = {}, {}
        self._lock = asyncio.Lock()
        self.closed, self.last_error = False, None

    async def _selection(self, record):
        snapshot = await self.host.store.snapshot(record.subscription_id)
        if snapshot.record != record or self.host.clock() >= record.expires_at:
            raise SubscriptionUnavailable("Original subscriber changed or expired")
        audience = self.host.audiences.capture(record.subscription_id)
        principal = self.host.audiences.current(audience)
        projection, _, binding, run = self.source._binding(principal, record.request_ref)
        if binding['read_ref'] != record.read_ref or owner_key(projection) != record.owner_key:
            raise Unavailable("Original subscriber source identity changed")
        return projection, run

    async def _current_targets(self, key):
        result = []
        for record in self.targets.get(key, ()):
            try:
                principal, run = await self._selection(record)
                if _key(principal, run) != key:
                    raise Conflict("Original observer target changed")
                result.append((record, principal, run))
            except ObservedReplyPolicyDenial as denial:
                await self.host.audiences.revoke_observed(denial)
            except (SubscriptionUnavailable, Unavailable):
                continue
        return result

    async def _resolve(self, key):
        if self.closed or not self.host.enabled:
            return None
        targets = await self._current_targets(key)
        if not targets:
            return None
        _, principal, run = targets[0]
        client = await self.source._client(principal, run)
        # Native client construction may await access discovery. Recheck the
        # retained subscriber before its subsequent exact-run wait.
        if not await self._current_targets(key):
            return None
        return principal, run, client

    async def _consume(self, key, _principal, original_run, state):
        targets = await self._current_targets(key)
        if self.closed or not targets:
            return False
        if (_key(targets[0][1], original_run) != key
                or state.get('runId') != original_run.run_id
                or state.get('threadId') != original_run.thread.thread_id):
            raise Conflict("Native observation differs from original run")
        unique = {}
        for record, principal, run in targets:
            unique.setdefault(record.request_ref, (principal, run))
        if state.get('status') in TERMINAL and state.get('timedOut') is False:
            for request_ref, (principal, run) in unique.items():
                client = await self.source._client(principal, run)
                observed = await client.original_result(run)
                if observed.status not in TERMINAL:
                    raise Conflict("Original terminal run changed before return")
                if observed.complete is True and type(observed.answer) is str:
                    await self.host.observe_t3_reply(principal, request_ref)
                else:
                    await self.host.observe_t3_terminal(principal, request_ref)
            return False
        principal, run = next(iter(unique.values()))
        client = await self.source._client(principal, run)
        pending = await client.pending_questions(run.thread)
        if len(pending) > 32:
            raise Unavailable("Pending native questions exceed bounded observation capacity")
        for request_id in pending:
            question = await client.read_question(run.thread, request_id)
            if (question.get('threadId') != run.thread.thread_id
                    or type(question.get('runId')) is not str
                    or question.get('kind') != 'user_input'):
                raise Unavailable("Native question provenance is unavailable")
            if question['runId'] != run.run_id or question.get('status') != 'pending':
                continue  # Never deliver an older/newer run's question.
            for request_ref, (current, _) in unique.items():
                try:
                    await self.host.observe_t3_question(current, request_ref, request_id)
                except Conflict:
                    # An input can be answered between the list and exact read.
                    # The canonical source did not authorize a stale send.
                    continue
        return True

    async def reconcile(self):
        """Restore/update live read handles from current original subscriptions.

        Called on service startup and accepted subscribe/unsubscribe, never by a
        timer, caller-supplied event payload or a new queue. Existing failed or
        uncertain handles remain held, not automatically replaced.
        """
        async with self._lock:
            if self.closed or not self.host.enabled:
                raise Unavailable("Original reply observer owner is closed")
            desired = {}
            for record in self.host.store.active_subscriptions(limit=128):
                if not is_t3_request_ref(record.request_ref) or not is_t3_read_ref(record.read_ref):
                    continue
                try:
                    principal, run = await self._selection(record)
                except ObservedReplyPolicyDenial as denial:
                    await self.host.audiences.revoke_observed(denial)
                    continue
                except (SubscriptionUnavailable, Unavailable):
                    continue
                desired.setdefault(_key(principal, run), []).append(record)
            if len(desired) > self.maximum_original_runs:
                self.last_error = 'ORIGINAL_NATIVE_OBSERVATION_CAPACITY'
                raise Unavailable("Original native observation capacity exceeded")
            self.targets = {key: tuple(rows) for key, rows in desired.items()}
            for key in tuple(self.observers):
                if key not in desired:
                    await self.observers[key].close()
                    del self.observers[key]
            for key in desired:
                if key in self.observers:
                    continue  # Terminal, unavailable and uncertain are not retry permission.
                observer = self.observer_factory(
                    lambda key=key: self._resolve(key),
                    lambda principal, run, state, key=key: self._consume(key, principal, run, state),
                    capacity=self.capacity)
                if not isinstance(observer, T3NativeReturnWait):
                    raise TypeError("Existing original native wait adapter required")
                self.observers[key] = observer
                await observer.start()
            self.last_error = None
            return {'original_runs': len(self.observers), 'native_inference_started': False}

    async def close(self):
        async with self._lock:
            self.closed = True
            self.targets = {}
            results = await asyncio.gather(*(observer.close() for observer in self.observers.values()),
                                           return_exceptions=True)
            if any(isinstance(result, BaseException) for result in results):
                self.last_error = 'ORIGINAL_NATIVE_OBSERVER_CLOSE_UNCONFIRMED'
                raise Unavailable("Original native observer close is unconfirmed")

    def status(self, principal):
        projection, principal_key, _ = self.source._admit(principal)
        rows = []
        for key, observer in self.observers.items():
            if key[0] != principal_key:
                continue
            # This is a live-handle projection, not a global transcript or
            # permission grant. Canonical reads still revalidate original scope.
            rows.append(dict(observer.status(), environment_id=key[2], project_id=key[3],
                             thread_id=key[4], run_id=key[5]))
        return {'schema': 'mastermind.t3_original_monitor_status.v1', 'closed': self.closed,
                'observer_count': len(rows), 'observers': rows, 'error': self.last_error,
                'durable_source': 'existing_runtime_reply_subscriptions',
                'native_inference_started': False, 'parent_consumed': False}
