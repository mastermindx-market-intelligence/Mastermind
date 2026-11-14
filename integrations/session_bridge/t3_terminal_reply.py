"""Truthful terminal-without-qualified-answer notifications in the original owner.

No error text is invented or copied from an untrusted callback. Native terminal
status and original identities are observed again; a digest-only Runtime event
supports the same canonical read and signed subscription delivery as replies.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .t3_native_client import TERMINAL, Conflict, Unavailable
from .t3_reply_events import (_hash, _AGGREGATE, _ACTOR, _ID, _SHA,
    REQUEST_PREFIX, READ_PREFIX, is_t3_request_ref, is_t3_read_ref, T3ReturnEffectUnknown)
from .web_reply_events import EVENT_NAME

READ_SCHEMA = 'mastermind.t3_original_terminal_read.v1'
OBSERVATION_SCHEMA = 'mastermind.t3_original_terminal_observation.v1'
KEY_PREFIX = 't3-native-status-'
COMMAND_PREFIX = 't3-terminal-'
EVENT = 'T3_ORIGINAL_TERMINAL_OBSERVED'
_FIELDS = {'schema', 'request_ref', 'read_ref', 'owner_key', 'native_status',
           'terminal_sha256', 'message_key', 'observed_at'}
_PUBLIC = {'schema', 'request_ref', 'read_ref', 'message_key', 'environment_id', 'project_id',
           'thread_id', 'run_id', 'native_status', 'terminal_sha256', 'native_terminal',
           'answer_qualified', 'successful', 'reply_committed', 'parent_consumed'}


def _digest(status):
    return _hash({'native_status': status, 'answer_qualified': False})


def _identity(request_ref, status):
    return _hash({'request_ref': request_ref, 'terminal_sha256': _digest(status)})


def validate_public(value):
    if (type(value) is not dict or set(value) != _PUBLIC or value['schema'] != READ_SCHEMA
            or not is_t3_request_ref(value['request_ref']) or not is_t3_read_ref(value['read_ref'])
            or value['request_ref'][len(REQUEST_PREFIX):] != value['read_ref'][len(READ_PREFIX):]
            or value['native_status'] not in TERMINAL or value['native_terminal'] is not True
            or value['answer_qualified'] is not False or value['successful'] is not False
            or value['reply_committed'] is not True or value['parent_consumed'] is not False
            or value['terminal_sha256'] != _digest(value['native_status'])
            or value['message_key'] != KEY_PREFIX + _identity(value['request_ref'], value['native_status'])):
        raise ValueError('Original native terminal notification is unqualified')
    for field in ('environment_id', 'project_id', 'thread_id', 'run_id'):
        if type(value[field]) is not str or not _ID.fullmatch(value[field]):
            raise ValueError('Original native terminal identity is invalid')
    return dict(value)


async def _native(source, principal, request_ref):
    projection, event, binding, run = source._binding(principal, request_ref)
    client = await source._client(projection, run)
    terminal = await client.wait(run, timeout_ms=1, include_children=False)
    if terminal['timedOut'] is not False or terminal['status'] not in TERMINAL:
        raise Unavailable('Original native terminal state is not proven')
    result = await client.original_result(run)
    if (result.run != run or result.status != terminal['status']
            or result.complete is not False or result.answer is not None):
        raise Unavailable('Original run is not a terminal result without a qualified answer')
    current, current_event, _, _ = source._binding(principal, request_ref)
    if current_event.to_dict() != event.to_dict():
        raise Conflict('Original terminal source changed during observation')
    await source._client(current, run)
    return binding, run, result


def _validate(event, binding, status, message_key):
    ident = _identity(binding['request_ref'], status)
    if (event is None or event.event_type != EVENT or event.aggregate_type != _AGGREGATE
            or event.aggregate_id != binding['request_ref'] or event.actor != _ACTOR
            or event.command_id != COMMAND_PREFIX + ident or type(event.payload) is not dict):
        raise Conflict('Original terminal observation is unqualified')
    value = event.payload
    if (set(value) != _FIELDS or value['schema'] != OBSERVATION_SCHEMA
            or value['request_ref'] != binding['request_ref'] or value['read_ref'] != binding['read_ref']
            or value['owner_key'] != binding['owner_key'] or value['native_status'] != status
            or value['terminal_sha256'] != _digest(status)
            or value['message_key'] != message_key or message_key != KEY_PREFIX + ident
            or type(value['observed_at']) is not int
            or not binding['created_at'] <= value['observed_at'] < binding['expires_at']):
        raise Conflict('Original terminal observation provenance changed')
    return value


async def observe(source, principal, request_ref):
    binding, _, result = await _native(source, principal, request_ref)
    ident = _identity(request_ref, result.status)
    command, key = COMMAND_PREFIX + ident, KEY_PREFIX + ident
    payload = {'schema': OBSERVATION_SCHEMA, 'request_ref': request_ref, 'read_ref': binding['read_ref'],
        'owner_key': binding['owner_key'], 'native_status': result.status,
        'terminal_sha256': _digest(result.status), 'message_key': key, 'observed_at': source.clock()}
    source._binding(principal, request_ref)
    attempted = False
    try:
        with source.runtime.store.transaction() as connection:
            previous = source.runtime.store.get_event_by_command_id(command, connection=connection)
            if previous is None:
                attempted = True
                source.runtime.store.append_event(connection, aggregate_type=_AGGREGATE,
                    aggregate_id=request_ref, event_type=EVENT, actor=_ACTOR, command_id=command, payload=payload)
        event = source.runtime.events.get_event_by_command_id(command)
        _validate(event, binding, result.status, key)
        source._binding(principal, request_ref)
    except (Exception, asyncio.CancelledError):
        if attempted:
            raise T3ReturnEffectUnknown('observe_terminal', request_ref, binding['read_ref']) from None
        raise
    return {'request_ref': request_ref, 'read_ref': binding['read_ref'], 'message_key': key,
            'event_command_id': command, 'reply_committed': True, 'native_terminal': True,
            'successful': False, 'delivered': False, 'parent_consumed': False}


async def _committed(source, principal, request_ref, message_key):
    binding, run, result = await _native(source, principal, request_ref)
    ident = _identity(request_ref, result.status)
    event = source.runtime.events.get_event_by_command_id(COMMAND_PREFIX + ident)
    observed = _validate(event, binding, result.status, message_key)
    source._binding(principal, request_ref)
    return binding, run, result, observed


async def read(source, principal, request_ref, message_key):
    binding, run, result, observed = await _committed(source, principal, request_ref, message_key)
    return validate_public({'schema': READ_SCHEMA, 'request_ref': request_ref, 'read_ref': binding['read_ref'],
        'message_key': message_key, 'environment_id': run.thread.scope.environment_id,
        'project_id': run.thread.scope.project_id, 'thread_id': run.thread.thread_id, 'run_id': run.run_id,
        'native_status': result.status, 'terminal_sha256': observed['terminal_sha256'],
        'native_terminal': True, 'answer_qualified': False, 'successful': False,
        'reply_committed': True, 'parent_consumed': False})


async def project(source, principal, request_ref, message_key):
    from .runtime_reply_delivery import ResolvedReplyEvent
    binding, _, _, observed = await _committed(source, principal, request_ref, message_key)
    event = {'eventId': 'evt-' + message_key[len(KEY_PREFIX):], 'name': EVENT_NAME,
        'timestamp': datetime.fromtimestamp(observed['observed_at'], timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'cursor': None, 'data': {'request_ref': request_ref, 'read_ref': binding['read_ref'],
            'message_key': message_key, 'in_reply_to': request_ref,
            'summary': 'The original T3 run ended without a qualified answer. Read its exact terminal status; do not infer success or restart it automatically.',
            'reply_committed': True, 'parent_consumed': False}}
    return ResolvedReplyEvent(event, binding['read_ref'], binding['owner_key'])
