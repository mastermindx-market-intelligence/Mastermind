"""Fixed project conversation READs; no registration or mutation owner.

The actual installed OsSessionTransportApp owns the audited verifier pairs.
This leaf reuses that exact current owner; neither history-context booleans,
ASGI state nor the private principal syntax supplies authentication. The
receiving service must independently qualify its App peer and Runtime owners.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from starlette.responses import Response

from common import project_conversation_read_contract as wire
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.mastermind_executive_app.gateway import CeoIngressClient, TRANSPORT_SENT_OK
from integrations.mastermind_executive_app.os_session_transport import OsSessionTransportApp
from integrations.mastermind_executive_app.os_transport import (
    _OS_HTTP_HEADERS, _bearer_token, _parse_body, RECEIVE_DEADLINE_SECONDS,
)
from integrations.session_bridge.installed import principal_frame

ROUTES = {
    '/os/executive/session/conversations': 'catalogue',
    '/os/executive/session/conversation-read': 'read',
    '/os/executive/session/fresh-conversations': 'fresh_references',
    '/os/executive/session/fresh-conversation-read': 'fresh_read',
    '/os/executive/session/project-executions': 'execution_references',
    '/os/executive/session/project-execution-read': 'execution_read',
}
_HEX = re.compile(r'[0-9a-f]{64}')
_JOB_STATES = ('QUEUED', 'RUNNING', 'CHECKPOINTED', 'RATE_LIMITED', 'FAILED', 'LOST', 'CANCEL_REQUESTED', 'COMPLETED', 'CANCELLED')


def _fail():
    raise ValueError('project_conversation_unavailable')


def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail()
    return value


def _json(value):
    """Detached built-in JSON only, with no user object serializer invocation."""
    def check(item, depth=0):
        if depth > 48:
            _fail()
        if item is None or type(item) in (bool, int, float, str):
            return
        if type(item) is list:
            for child in item:
                check(child, depth + 1)
        elif type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    _fail()
                check(child, depth + 1)
        else:
            _fail()
    check(value)
    packet = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8', errors='strict')
    if len(packet) > wire.MAX_RESPONSE_BYTES:
        _fail()
    return json.loads(packet)


def _hex(value):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        _fail()
    return value


def _literal(value, limit):
    if type(value) is not str or not value or len(value.encode('utf-8', errors='strict')) > limit:
        _fail()
    return value


def _clock(value):
    _literal(value, 128)
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)', value) is None:
        _fail()
    datetime.fromisoformat(value.replace('Z', '+00:00'))


def _message(value):
    _literal(value, 2800)
    if (len(value) > 700 or not value.strip()
            or any(ord(c) < 32 and c not in '\t\n\r' or 127 <= ord(c) <= 159 for c in value)):
        _fail()


def _revision(reference, requests):
    return hashlib.sha256(json.dumps({'conversation_ref': reference, 'requests': requests},
        sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()


def _payload(value, locator):
    from control_plane.executive_orchestration_result import validate_envelope
    _closed(value, ('digest', 'envelope'))
    envelope = value['envelope']
    if type(envelope) is not dict or locator['job_id'] is None or locator['attempt_id'] is None:
        _fail()
    validate_envelope(envelope, expected_job_id=locator['job_id'], expected_run_id=locator['attempt_id'],
                      expected_worker_id=envelope.get('worker_id'), expected_role=envelope.get('role'),
                      expected_root_job_id=locator['root_job_id'])
    encoded = json.dumps(envelope, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    if _hex(value['digest']) != hashlib.sha256(encoded).hexdigest():
        _fail()


def _execution_goal(value):
    _literal(value, 16000)
    if len(value) > 4000 or not value.strip() or "\x00" in value:
        _fail()


def _execution_result(data, operation, arguments):
    from common.project_execution_private_contract import validate_previous_run
    work = arguments['work_ref']
    if operation == 'execution_references':
        _closed(data, ('schema', 'work_ref', 'state', 'coverage', 'entries', 'can_send'))
        coverage = _closed(data['coverage'], ('state', 'limit', 'returned'))
        if (data['schema'] != 'mastermind.project_execution_references.v1'
                or data['work_ref'] != work or data['state'] != 'AVAILABLE' or data['can_send'] is not False
                or coverage['state'] not in ('COMPLETE', 'PARTIAL')
                or type(coverage['limit']) is not int or coverage['limit'] != 8
                or type(data['entries']) is not list or len(data['entries']) > 8
                or type(coverage['returned']) is not int or coverage['returned'] != len(data['entries'])):
            _fail()
        roots, previous_id = set(), None
        for row in data['entries']:
            _closed(row, ('kind', 'reference', 'goal', 'root_state'))
            ref = wire.arguments(row['reference'], 'execution_read')
            if (row['kind'] != 'project_execution' or ref['work_ref'] != work
                    or ref['root_job_id'] in roots or row['root_state'] not in _JOB_STATES
                    or previous_id is not None and ref['root_event_id'] >= previous_id):
                _fail()
            roots.add(ref['root_job_id'])
            previous_id = ref['root_event_id']
            _execution_goal(row['goal'])
        return
    _closed(data, ('schema', 'kind', 'reference', 'state', 'goal', 'continuation_mode',
                   'locator', 'previous_run', 'result', 'parent_witness', 'can_send'))
    reference = wire.arguments(data['reference'], 'execution_read')
    locator = _closed(data['locator'], ('work_ref', 'root_job_id', 'job_id', 'attempt_id'))
    if (data['schema'] != 'mastermind.project_execution_window.v1' or data['kind'] != 'project_execution'
            or reference != arguments or data['state'] not in _JOB_STATES or data['can_send'] is not False
            or data['continuation_mode'] not in ('DURABLE', 'ATTENDED') or locator['work_ref'] != work
            or locator['root_job_id'] != reference['root_job_id'] or locator['job_id'] != reference['root_job_id']):
        _fail()
    if locator['attempt_id'] is not None:
        _literal(locator['attempt_id'], 128)
    _execution_goal(data['goal'])
    if data['previous_run'] is not None:
        previous = validate_previous_run(data['previous_run'])
        if previous['root_job_id'] == reference['root_job_id'] or previous['root_event_id'] >= reference['root_event_id']:
            _fail()
    if data['state'] != 'COMPLETED':
        if data['result'] is not None or data['parent_witness'] is not None:
            _fail()
        return
    result = _closed(data['result'], ('digest', 'envelope', 'terminal_receipt_sha256'))
    witness = validate_previous_run(data['parent_witness'])
    _payload({key: result[key] for key in ('digest', 'envelope')}, locator)
    _hex(result['terminal_receipt_sha256'])
    if (result['envelope'].get('role') != 'aggregation'
            or any(witness[key] != reference[key] for key in ('root_job_id', 'root_event_id',
                'root_event_sha256', 'project_execution_source_sha256'))
            or witness['attempt_id'] != locator['attempt_id']
            or witness['result_envelope_sha256'] != result['digest']
            or witness['terminal_receipt_sha256'] != result['terminal_receipt_sha256']):
        _fail()


def validate_result(value, operation, arguments):
    """Closed source DTO/selector binding, not a second source authority."""
    data = _json(value)
    work = arguments['work_ref']
    if operation in ('execution_references', 'execution_read'):
        _execution_result(data, operation, arguments)
        return data
    if operation == 'catalogue':
        _closed(data, ('schema', 'work_ref', 'coverage', 'conversations', 'next_cursor', 'high_water', 'can_send'))
        if (data['schema'] != 'mastermind.project_conversation_catalogue.v1' or data['work_ref'] != work
                or data['coverage'] != 'PARTIAL' or data['can_send'] is not False
                or type(data['high_water']) is not int or data['high_water'] < 0
                or type(data['conversations']) is not list or len(data['conversations']) > 8):
            _fail()
        if data['next_cursor'] is not None:
            wire.arguments({'work_ref': work, 'cursor': data['next_cursor']}, 'catalogue')
        refs = set()
        for row in data['conversations']:
            _closed(row, ('conversation_ref', 'revision', 'root_job_id', 'title', 'last_request_at', 'requests'))
            wire.arguments({key: (work if key == 'work_ref' else row[key]) for key in
                            ('work_ref', 'conversation_ref', 'revision', 'requests')}, 'read')
            if (row['conversation_ref'] in refs or row['title'] is not None
                    or row['revision'] != _revision(row['conversation_ref'], row['requests'])):
                _fail()
            refs.add(row['conversation_ref'])
            _literal(row['root_job_id'], 256)
            _clock(row['last_request_at'])
    elif operation == 'read':
        _closed(data, ('schema', 'work_ref', 'conversation_ref', 'revision', 'root_job_id', 'title', 'coverage', 'can_send', 'turns'))
        if (data['schema'] != 'mastermind.project_conversation_read.v1' or data['work_ref'] != work
                or data['conversation_ref'] != arguments['conversation_ref'] or data['revision'] != arguments['revision']
                or data['title'] is not None or data['coverage'] != 'PARTIAL' or data['can_send'] is not False
                or data['revision'] != _revision(arguments['conversation_ref'], arguments['requests'])
                or type(data['turns']) is not list or len(data['turns']) != len(arguments['requests'])):
            _fail()
        _literal(data['root_job_id'], 256)
        for turn, selected in zip(data['turns'], arguments['requests']):
            _closed(turn, ('read_ref', 'request_revision', 'requested_at', 'instruction', 'stop_condition', 'reply', 'state'))
            if any(turn[k] != selected[k] for k in selected):
                _fail()
            _clock(turn['requested_at'])
            if turn['state'] == 'UNAVAILABLE':
                if any(turn[k] is not None for k in ('instruction', 'stop_condition', 'reply')):
                    _fail()
            elif turn['state'] == 'AVAILABLE':
                _literal(turn['instruction'], 8192)
                _literal(turn['stop_condition'], 8192)
                reply = _closed(turn['reply'], ('text', 'next_step', 'read_ref', 'message_key', 'fingerprint', 'parent_consumed'))
                if reply['read_ref'] != turn['read_ref'] or reply['parent_consumed'] is not False:
                    _fail()
                for key in ('text', 'next_step', 'message_key'):
                    _literal(reply[key], 16384)
                _hex(reply['fingerprint'])
            else:
                _fail()
    elif operation == 'fresh_references':
        _closed(data, ('schema', 'work_ref', 'state', 'coverage', 'entries'))
        coverage = _closed(data['coverage'], ('state', 'limit', 'returned'))
        if (data['schema'] != 'mastermind.fresh_conversation_references.v1' or data['work_ref'] != work
                or data['state'] != 'AVAILABLE' or coverage['state'] not in ('COMPLETE', 'PARTIAL')
                or type(coverage['limit']) is not int or coverage['limit'] != 8
                or type(data['entries']) is not list or len(data['entries']) > 8
                or type(coverage['returned']) is not int or coverage['returned'] != len(data['entries'])):
            _fail()
        roots = set()
        for row in data['entries']:
            _closed(row, ('kind', 'reference', 'initial_message', 'root_state'))
            ref = wire.arguments(row['reference'], 'fresh_read')
            if (ref['work_ref'] != work or ref['root_job_id'] in roots or row['kind'] != 'fresh_native'
                    or row['root_state'] not in ('QUEUED', 'RUNNING', 'CHECKPOINTED', 'RATE_LIMITED', 'FAILED', 'LOST', 'CANCEL_REQUESTED', 'COMPLETED', 'CANCELLED')):
                _fail()
            roots.add(ref['root_job_id'])
            _message(row['initial_message'])
    elif operation == 'fresh_read':
        _closed(data, ('schema', 'kind', 'reference', 'state', 'locator', 'epoch', 'initial_message',
                       'initial_result', 'initial_consumption', 'turns', 'can_send', 'parent_consumed'))
        locator = _closed(data['locator'], ('work_ref', 'root_job_id', 'job_id', 'attempt_id'))
        if (data['schema'] != 'mastermind.fresh_conversation_window.v1' or data['kind'] != 'fresh_native'
                or wire.arguments(data['reference'], 'fresh_read') != arguments or data['can_send'] is not False
                or data['parent_consumed'] is not False or locator['work_ref'] != work
                or locator['root_job_id'] != arguments['root_job_id']
                or data['state'] not in ('ADMITTED', 'RETAINED', 'SETTLED', 'RECONCILIATION_REQUIRED')):
            _fail()
        for key in ('job_id', 'attempt_id'):
            if locator[key] is not None:
                _literal(locator[key], 128)
        if locator['attempt_id'] is not None and locator['job_id'] is None:
            _fail()
        _message(data['initial_message'])
        if (data['state'] == 'RETAINED') != (data['epoch'] is not None):
            _fail()
        if data['epoch'] is not None:
            epoch = _closed(data['epoch'], ('attempt_id', 'binding_digest', 'generation_digest'))
            if epoch['attempt_id'] != locator['attempt_id'] or epoch['attempt_id'] is None:
                _fail()
            _hex(epoch['binding_digest']); _hex(epoch['generation_digest'])
        initial = data['initial_result']
        if initial is not None:
            _payload(initial, locator)
        if data['state'] == 'SETTLED' and initial is None:
            _fail()
        consumed = data['initial_consumption']
        if consumed is not None:
            _closed(consumed, ('state', 'event_id', 'event_sha256', 'initial_digest'))
            if (consumed['state'] != 'CONSUMED' or type(consumed['event_id']) is not int or consumed['event_id'] <= 0
                    or initial is None or consumed['initial_digest'] != initial['digest']):
                _fail()
            _hex(consumed['event_sha256'])
        if type(data['turns']) is not list or len(data['turns']) > 1:
            _fail()
        for turn in data['turns']:
            _closed(turn, ('turn_key', 'message', 'state', 'result', 'parent_consumed'))
            if turn['parent_consumed'] is not False or consumed is None or turn['state'] not in ('RECORDED', 'RECONCILIATION_REQUIRED'):
                _fail()
            _literal(turn['turn_key'], 128); _message(turn['message'])
            if (turn['state'] == 'RECORDED') != (turn['result'] is not None):
                _fail()
            if turn['result'] is not None:
                _payload(turn['result'], locator)
    else:
        _fail()
    return data


class ProjectConversationReadClient:
    """One fixed configured socket, actual incumbent client, one READ frame."""
    def __init__(self, socket_path, *, client: CeoIngressClient):
        if type(client) is not CeoIngressClient or not isinstance(socket_path, (str, Path)):
            raise TypeError('actual CeoIngressClient and fixed socket required')
        path = str(socket_path)
        if not path.startswith('/') or '\0' in path or len(path) > 4096:
            raise ValueError('fixed socket required')
        self._client, self._path = client, path
        self._fixed_path = path
        self._send, self._inner = client.send_frame, client._send_frame

    def current(self):
        return (self._path == self._fixed_path and self._client.send_frame == self._send
                and self._client._send_frame == self._inner)

    async def read(self, principal, operation, arguments):
        if type(principal) is not VerifiedPrincipal or not self.current():
            _fail()
        frame = wire.frame(dict(schema=wire.SCHEMA, operation=operation,
                                principal=principal_frame(principal), arguments=arguments))
        wire.encode_frame(frame)  # Bound the complete frame, including LF.
        response = await self._send(self._path, frame)
        if not self.current() or response.transport != TRANSPORT_SENT_OK or response.ok is not True:
            _fail()
        # The incumbent client enforces the complete outer socket frame cap.
        result = validate_result(response.result, operation, frame['arguments'])
        if len(json.dumps({'ok': True, 'result': result}, ensure_ascii=False, allow_nan=False).encode('utf-8')) + 1 > wire.MAX_RESPONSE_BYTES:
            _fail()
        return result


class ProjectConversationTransportApp:
    ROUTES = tuple(ROUTES)

    def __init__(self, reader: ProjectConversationReadClient, *, auth_owner: OsSessionTransportApp):
        if type(reader) is not ProjectConversationReadClient or type(auth_owner) is not OsSessionTransportApp:
            raise TypeError('actual project reader and installed session auth owner required')
        self._reader, self._owner = reader, auth_owner
        self._reader_read, self._reader_current = reader.read, reader.current
        self._pairs = (auth_owner._read_pair, auth_owner._submit_pair)
        self._clock = auth_owner._clock
        self._methods = (auth_owner._authenticate, auth_owner._same_principal)

    def _current(self):
        owner = self._owner
        return (owner._read_pair is self._pairs[0] and owner._submit_pair is self._pairs[1]
                and owner._clock is self._clock and (owner._authenticate, owner._same_principal) == self._methods
                and self._reader.read == self._reader_read and self._reader.current == self._reader_current
                and self._reader_current())

    async def _same(self, scope, principal):
        return self._current() and await self._methods[1](scope, principal, self._pairs) and self._current()

    async def __call__(self, scope, receive, send):
        if scope.get('type') != 'http':
            return
        path = scope.get('path')
        operation = ROUTES.get(path) if type(path) is str else None
        if operation is None or not OsSessionTransportApp._framing_ok(scope):
            response = Response(status_code=404, headers=_OS_HTTP_HEADERS)
        else:
            response = await self._request(operation, scope, receive)
        await response(scope, receive, send)

    async def _request(self, operation, scope, receive):
        def refusal(status=503):
            return Response(b'{"error":"project_conversations_unavailable"}', status_code=status,
                            media_type='application/json', headers=_OS_HTTP_HEADERS)
        try:
            headers = scope.get('headers') or ()
            if type(headers) not in (tuple, list) or any(type(x) not in (tuple, list) or len(x) != 2
                    or any(type(v) is not bytes for v in x) for x in headers):
                return refusal(403)
            values = lambda name: [v for k, v in headers if k.lower() == name]
            if (values(b'host') != [b'mcp.mastermind-x.com'] or len(values(b'origin')) > 1
                    or values(b'origin') not in ([], [b'https://mcp.mastermind-x.com'])
                    or len(values(b'authorization')) != 1 or values(b'transfer-encoding')):
                return refusal(403)
            if not OsSessionTransportApp._json_content_type(headers):
                return refusal(400)
            lengths = values(b'content-length')
            if len(lengths) > 1 or lengths and (not re.fullmatch(rb'[0-9]+', lengths[0]) or int(lengths[0]) > wire.MAX_REQUEST_BYTES):
                return refusal(400)
            try:
                token = _bearer_token(values(b'authorization')[0])
            except Exception:
                return refusal(401)
            if not self._current():
                return refusal(401)
            principal = await self._methods[0](token, self._pairs)
            if principal is None or not self._current():
                return refusal(401)
            body = bytearray()
            async with asyncio.timeout(RECEIVE_DEADLINE_SECONDS):
                for _ in range(128):
                    event = await receive()
                    if (type(event) is not dict or event.get('type') != 'http.request'
                            or type(event.get('body', b'')) is not bytes or type(event.get('more_body', False)) is not bool):
                        return refusal(400)
                    chunk = event.get('body', b'')
                    if len(body) + len(chunk) > wire.MAX_REQUEST_BYTES:
                        return refusal(400)
                    body.extend(chunk)
                    if not event.get('more_body', False):
                        break
                else:
                    return refusal(400)
            if lengths and int(lengths[0]) != len(body):
                return refusal(400)
            try:
                request = _closed(_parse_body(bytes(body)), ('arguments',))
                arguments = wire.arguments(request['arguments'], operation)
            except Exception:
                return refusal(400)
            if not await self._same(scope, principal):
                return refusal(401)
            data = await self._reader_read(principal, operation, arguments)
            if not await self._same(scope, principal):
                return refusal(401)
            return Response(json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'),
                            status_code=200, media_type='application/json', headers=_OS_HTTP_HEADERS)
        except Exception:
            return refusal()
