"""Durable native COMMIT admission on real Runtime SQLite; no provider effect."""
import dataclasses
import sqlite3

import pytest

from integrations.session_bridge.schemas import BridgeError
from tests.test_session_bridge_runtime_return import setup, populate, NATIVE


def prepared(s):
    populate(s)
    request, reply = [item['message'] for item in s.service.items]
    s.service.items.pop()
    binding = s.owner.resolve(native_session_id=NATIVE,
        operation_key=s.args['operation_key'], in_reply_to=request['message_key'])
    return binding, reply


def fence(s, binding, message, guard=lambda connection: None):
    return s.owner.native_reply_commit_fence(binding, message, guard=guard)


def test_commit_marker_is_durable_before_handoff_and_writer_is_locked(setup):
    s = setup
    binding, message = prepared(s)
    observed = []
    def guard(connection):
        assert connection.in_transaction
        observed.append(connection)
    with fence(s, binding, message, guard):
        # A separate reader can already see the committed admission marker.
        events = s.runtime.events.list_events(aggregate_type='session_bridge_continue')
        assert len([e for e in events if e.event_type == 'SESSION_BRIDGE_NATIVE_REPLY_COMMIT_STARTED']) == 1
        with sqlite3.connect(s.runtime.store.path, timeout=0) as competitor:
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                competitor.execute('BEGIN IMMEDIATE')
    assert len(observed) == 2
    # No Runtime fence leaks into the response wait.
    with sqlite3.connect(s.runtime.store.path, timeout=0) as competitor:
        competitor.execute('BEGIN IMMEDIATE')
        competitor.rollback()


def test_second_invocation_cannot_commit_even_after_new_owner_instance(setup):
    s = setup
    binding, message = prepared(s)
    with fence(s, binding, message):
        pass
    owner = type(s.owner)(s.runtime, fabric=s.owner.fabric, codex=s.owner.codex,
                          socket_path=s.owner.socket_path, service_call=s.service)
    with pytest.raises(BridgeError, match='reconciliation'):
        with owner.native_reply_commit_fence(binding, message, guard=lambda conn: None):
            pytest.fail('duplicate COMMIT')


def test_revocation_before_marker_is_definite_pre_effect(setup):
    s = setup
    binding, message = prepared(s)
    before = s.runtime.events.list_events()
    def refused(connection):
        raise ValueError('revoked')
    with pytest.raises(BridgeError):
        with fence(s, binding, message, refused):
            pytest.fail('revoked COMMIT')
    assert s.runtime.events.list_events() == before


def test_handoff_between_durable_admission_and_commit_never_writes(setup):
    s = setup
    binding, message = prepared(s)
    calls = []
    def revoke_second(connection):
        calls.append(connection)
        if len(calls) == 2:
            raise ValueError('writer changed')
    with pytest.raises(BridgeError):
        with fence(s, binding, message, revoke_second):
            pytest.fail('COMMIT after handoff')
    assert len(calls) == 2
    # Unknown remains sticky even if the former writer comes back.
    with pytest.raises(BridgeError):
        with fence(s, binding, message):
            pytest.fail('replayed uncertain operation')


def test_failure_after_commit_does_not_rollback_admission(setup):
    s = setup
    binding, message = prepared(s)
    with pytest.raises(RuntimeError):
        with fence(s, binding, message):
            raise RuntimeError('transport crashed after handoff')
    with pytest.raises(BridgeError):
        with fence(s, binding, message):
            pytest.fail('replayed lost response')


@pytest.mark.parametrize('field,value', [
    ('native_session_id', '22222222-2222-4444-8888-999999999999'),
    ('process_generation_id', 'other-generation'), ('binding_generation', 999),
    ('binding_id', 'bind-other'), ('thread_ts', '1788000099.123456'),
])
def test_changed_binding_cannot_enter_commit_fence(setup, field, value):
    s = setup
    binding, message = prepared(s)
    before = s.runtime.events.list_events()
    with pytest.raises(BridgeError):
        with fence(s, dataclasses.replace(binding, **{field: value}), message):
            pytest.fail('foreign binding committed')
    assert s.runtime.events.list_events() == before
