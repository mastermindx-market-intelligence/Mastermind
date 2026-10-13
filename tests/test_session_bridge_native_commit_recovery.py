"""Parent recovery remains strict after a bound native reply admission."""
import copy
import dataclasses
import asyncio

import pytest

from integrations.session_bridge import runtime_return as module
from integrations.session_bridge.schemas import BridgeError
from tests.test_session_bridge_runtime_return import (
    setup, bind, begin_commit, populate, original_predecessor, reconcile, NATIVE,
)


def prepare(s):
    bind(s)
    begin_commit(s)
    populate(s)
    request, reply = [item['message'] for item in s.service.items]
    s.service.items.insert(0, {'message': original_predecessor(s),
                               'primary_ts': '1788000000.123456'})
    assert reconcile(s)['action'] == 'DUPLICATE'
    binding = s.owner.resolve(native_session_id=NATIVE,
        operation_key=s.args['operation_key'], in_reply_to=request['message_key'])
    return binding, reply


def admit(s, binding, reply):
    with s.owner.native_reply_commit_fence(binding, reply, guard=lambda conn: None):
        pass


@pytest.mark.parametrize('reply_visible', [False, True])
@pytest.mark.parametrize('target_retired', [False, True])
def test_parent_retry_after_native_admission_is_read_only(setup, monkeypatch, reply_visible, target_retired):
    s = setup
    binding, reply = prepare(s)
    admit(s, binding, reply)
    if not reply_visible:
        s.service.items.pop()  # Native outcome unknown; CONTINUE remains exact.
    s.owner = type(s.owner)(s.runtime, fabric=s.owner.fabric, codex=s.owner.codex,
        socket_path=s.owner.socket_path, service_call=s.service)
    if target_retired:
        def gone(*args, **kwargs):
            pytest.fail('read-only parent recovery consulted the retired worker')
        monkeypatch.setattr(s.owner, '_target', gone)
        monkeypatch.setattr(type(s.runtime), 'current_harness_binding_source', gone)
    before = s.runtime.events.list_events()
    sends = sum(c['operation'] == 'send_message' for c in s.service.calls)
    for _ in range(2):
        assert reconcile(s)['action'] == 'DUPLICATE'
    assert s.runtime.events.list_events() == before
    assert sum(c['operation'] == 'send_message' for c in s.service.calls) == sends


def test_native_unknown_remains_sticky_and_continue_cannot_recommit(setup):
    s = setup
    binding, reply = prepare(s)
    admit(s, binding, reply)
    s.service.items.pop()
    assert reconcile(s)['action'] == 'DUPLICATE'
    with pytest.raises(BridgeError):
        admit(s, binding, reply)
    with pytest.raises(BridgeError):
        begin_commit(s)
    s.service.items.pop()  # Now the original CONTINUE is absent too.
    with pytest.raises(BridgeError):
        reconcile(s)


@pytest.mark.parametrize('reply_visible', [False, True])
def test_original_parent_reads_committed_result_without_reviving_retired_writer(setup, monkeypatch, reply_visible):
    from integrations.session_bridge.native_read import NativeReplyReader
    s = setup
    binding, reply = prepare(s)
    admit(s, binding, reply)
    if not reply_visible:
        s.service.items.pop()
    def retired(*_args, **_kwargs):
        pytest.fail('canonical result read consulted retired session authority')
    monkeypatch.setattr(s.owner, '_target', retired)
    monkeypatch.setattr(type(s.runtime), 'current_harness_binding_source', retired)
    reader = NativeReplyReader(s.owner, socket_path=s.owner.socket_path,
        service_call=s.service, projected_principal=True)
    before = s.runtime.events.list_events()
    sends = sum(c['operation'] == 'send_message' for c in s.service.calls)
    if reply_visible:
        result = asyncio.run(reader(s.projection, {'operation_key': s.args['operation_key']}))
        assert result['fingerprint'] == reply['fingerprint']
        assert result['text'] == reply['body']['completed']
        assert result['parent_consumed'] is False
    else:
        with pytest.raises(BridgeError):
            asyncio.run(reader(s.projection, {'operation_key': s.args['operation_key']}))
    assert s.runtime.events.list_events() == before
    assert sum(c['operation'] == 'send_message' for c in s.service.calls) == sends


@pytest.mark.parametrize('fault', [None, 'missing_reply', 'retired_writer', 'changed_reply'])
def test_service_cleanup_requires_exact_visible_commit_and_current_writer(setup, monkeypatch, fault):
    s = setup
    binding, reply = prepare(s)
    admit(s, binding, reply)
    prior_calls = len(s.service.calls)
    if fault == 'missing_reply':
        s.service.items.pop()
    elif fault == 'retired_writer':
        def retired(*_args, **_kwargs):
            raise module.BridgeError('binding_unavailable', 'retired writer')
        monkeypatch.setattr(type(s.runtime), 'current_harness_binding_source', retired)
    elif fault == 'changed_reply':
        s.service.items[-1]['message']['body']['completed'] = 'Foreign result.'
    before = s.runtime.events.list_events()
    if fault is None:
        result = asyncio.run(s.owner.require_committed_native_reply(read_ref=bind(s)))
        assert result == reply
    else:
        with pytest.raises(BridgeError):
            asyncio.run(s.owner.require_committed_native_reply(read_ref=bind(s)))
    assert s.runtime.events.list_events() == before
    assert all(call['operation'] == 'read_thread' for call in s.service.calls[prior_calls:])


@pytest.mark.parametrize('fault', [
    'kind', 'actor', 'command', 'aggregate_type', 'aggregate_id', 'job', 'attempt', 'worker', 'schema',
    'request_id', 'request_id_bool', 'request_digest', 'message_key',
    'extra', 'missing', 'fingerprint', 'message_digest', 'binding_digest',
    'duplicate', 'unexpected',
])
def test_foreign_or_malformed_native_event_cannot_be_ignored(setup, fault):
    s = setup
    binding, reply = prepare(s)
    with s.runtime.store.transaction() as conn:
        request, payload = s.owner._native_commit_source(binding, reply, connection=conn)
    values = dict(aggregate_type='session_bridge_continue', aggregate_id=request.aggregate_id,
        event_type=module._NATIVE_COMMIT_EVENT, actor=module._ACTOR,
        job_id=request.job_id, attempt_id=request.attempt_id, worker_id=request.worker_id,
        payload=copy.deepcopy(payload), command_id=module._NATIVE_COMMIT_PREFIX + request.aggregate_id)
    if fault in {'job', 'attempt', 'worker'}:
        s.runtime.workers.register_worker('worker-foreign', provider='codex',
            account_label='test', worker_type='codex', quota_classes=['default'])
        other_job = s.runtime.jobs.create_job('Foreign fixture job')
        other_lease = s.runtime.attempts.claim_job(other_job.job_id,
            worker_id='worker-foreign', quota_class='default')
        values[{'job':'job_id', 'attempt':'attempt_id', 'worker':'worker_id'}[fault]] = {
            'job':other_job.job_id, 'attempt':other_lease.attempt.attempt_id,
            'worker':'worker-foreign'}[fault]
    elif fault in {'kind', 'actor', 'command', 'aggregate_type', 'aggregate_id'}:
        field = {'kind':'event_type', 'command':'command_id', 'job':'job_id',
                 'attempt':'attempt_id', 'worker':'worker_id'}.get(fault, fault)
        values[field] = 'foreign'
    elif fault in {'schema', 'request_id', 'request_id_bool', 'request_digest', 'message_key',
                    'fingerprint', 'message_digest', 'binding_digest'}:
        field = {'request_id':'request_event_id', 'request_id_bool':'request_event_id',
                 'request_digest':'request_event_sha256', 'message_digest':'message_sha256',
                 'binding_digest':'binding_sha256'}.get(fault, fault)
        values['payload'][field] = (True if fault == 'request_id_bool' else
            request.event_id + 1 if fault == 'request_id' else
            '0'*64 if fault == 'request_digest' else
            'asd-native-reply-'+'0'*40 if fault == 'message_key' else 'foreign')
    elif fault == 'extra':
        values['payload']['extra'] = 'unbounded'
    elif fault == 'missing':
        values['payload'].pop('binding_sha256')
    else:
        admit(s, binding, reply)
        values['command_id'] = 'extra-event'
        if fault == 'unexpected':
            values['event_type'] = 'UNEXPECTED'
    with s.runtime.store.transaction() as conn:
        s.runtime.store.append_event(conn, **values)
    with pytest.raises(BridgeError):
        reconcile(s)


def test_unchanged_continue_marker_validation_is_not_bypassed(setup, monkeypatch):
    s = setup
    binding, reply = prepare(s)
    admit(s, binding, reply)
    original = s.runtime.store.get_event_by_command_id
    command = module._COMMIT_PREFIX + module._request_key(s.args['operation_key'])
    def corrupt(command_id, **kwargs):
        event = original(command_id, **kwargs)
        if command_id == command:
            return dataclasses.replace(event, payload={**event.payload, 'message_sha256':'0'*64})
        return event
    monkeypatch.setattr(s.runtime.store, 'get_event_by_command_id', corrupt)
    with pytest.raises(BridgeError):
        reconcile(s)
