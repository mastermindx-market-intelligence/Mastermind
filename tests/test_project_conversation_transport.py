"""Real signed Executive READ and incumbent client, temporary IPC only.

Fixtures are exact retained e86/D4B producer DTOs, not user sessions. The
private Runtime/peer authorization remains the receiving service's contract.
"""
import asyncio
import copy
import json
import tempfile
from pathlib import Path
from types import MethodType

import pytest

from common import project_conversation_read_contract as wire
from integrations.mastermind_executive_app.gateway import CeoIngressClient, CeoIngressResponse, TRANSPORT_SENT_OK
from integrations.mastermind_executive_app.project_conversation_transport import (
    ProjectConversationReadClient, ProjectConversationTransportApp, ROUTES, validate_result,
)
from tests import test_mastermind_os_session_transport as session
from tests import test_mastermind_executive_app_asgi as auth

rsa_key = auth.rsa_key
F = Path(__file__).parents[1] / 'app/mastermind_os/src/fixtures'
LEGACY = json.loads((F / 'project-conversation-catalogue-owner.json').read_text())
FRESH = json.loads((F / 'project-fresh-conversation-owner.json').read_text())
EXECUTION = json.loads((F / 'project-execution-history-owner.json').read_text())
CASES = {
    'catalogue': ({'work_ref': LEGACY['catalogue']['work_ref']}, LEGACY['catalogue']),
    'read': (LEGACY['selection'], LEGACY['read']),
    'fresh_references': ({'work_ref': FRESH['catalogue']['work_ref']}, FRESH['catalogue']),
    'fresh_read': (FRESH['initial_read']['reference'], FRESH['initial_read']),
    'execution_references': ({'work_ref': EXECUTION['catalogue']['work_ref']}, EXECUTION['catalogue']),
    'execution_read': (EXECUTION['completed_read']['reference'], EXECUTION['completed_read']),
}


def setup(rsa_key, operation='catalogue', after=lambda: None, result=None):
    owner, _, clock, audit = session.make_app(rsa_key)
    calls = []
    client = CeoIngressClient()

    async def peer(self, path, frame, **kwargs):
        calls.append((path, copy.deepcopy(frame)))
        after()
        return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True,
            result=copy.deepcopy(CASES[operation][1] if result is None else result))

    client._send_frame = MethodType(peer, client)
    reader = ProjectConversationReadClient('/no-live-project-conversation.sock', client=client)
    return ProjectConversationTransportApp(reader, auth_owner=owner), calls, clock, audit


async def exchange(app, token, operation='catalogue', arguments=None, *, body=None,
                   path=None, method='POST', scheme='https', query=b'', raw_path=None,
                   changes=(), on_receive=lambda: None, state=None):
    path = path or next(key for key, value in ROUTES.items() if value == operation)
    packet = json.dumps({'arguments': CASES[operation][0] if arguments is None else arguments}).encode() if body is None else body
    headers = [(b'host', b'mcp.mastermind-x.com'), (b'content-type', b'application/json'),
               (b'authorization', ('Bearer ' + token).encode())]
    for key, value in changes:
        if value is None:
            headers = [(k, v) for k, v in headers if k != key]
        else:
            headers.append((key, value))
    events = []

    async def receive():
        on_receive()
        return {'type': 'http.request', 'body': packet}

    async def send(event):
        events.append(event)

    await app({'type': 'http', 'method': method, 'scheme': scheme, 'path': path,
               'raw_path': path.encode() if raw_path is None else raw_path,
               'query_string': query, 'headers': headers, 'state': state or {}}, receive, send)
    status = events[0]['status']
    raw = b''.join(e.get('body', b'') for e in events[1:])
    assert len(raw) <= 32768
    assert token.encode() not in raw and b'PRIVATE-' not in raw
    hs = dict(events[0]['headers'])
    assert hs[b'cache-control'] == b'no-store' and hs[b'x-content-type-options'] == b'nosniff'
    return status, json.loads(raw) if raw else None


@pytest.mark.parametrize('operation', CASES)
@pytest.mark.parametrize('submit', [False, True])
def test_signed_read_exact_source_dto_over_real_incumbent_unix_client(rsa_key, operation, submit):
    async def run():
        owner, _, _, _ = session.make_app(rsa_key)
        observed = []
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'read.sock'

            async def serve(reader, writer):
                frame = wire.decode_frame(await reader.readline())
                observed.append(frame)
                writer.write((json.dumps({'ok': True, 'result': CASES[operation][1]}, ensure_ascii=False) + '\n').encode())
                await writer.drain()
                writer.close()
                await writer.wait_closed()

            server = await asyncio.start_unix_server(serve, path=str(path))
            try:
                client = ProjectConversationReadClient(path, client=CeoIngressClient())
                app = ProjectConversationTransportApp(client, auth_owner=owner)
                token = (auth._submit_token if submit else auth._read_token)(rsa_key)
                status, data = await exchange(app, token, operation)
                assert status == 200 and data == CASES[operation][1]
                assert len(observed) == 1
                frame = observed[0]
                assert frame['operation'] == operation and frame['arguments'] == CASES[operation][0]
                assert set(frame) == {'schema', 'operation', 'principal', 'arguments'}
                assert frame['principal']['policy_id'] == ('bsc-e1-test-submit' if submit else 'bsc-e1-test-read')
                assert 'token' not in frame and 'workspace_principal' not in frame
            finally:
                server.close()
                await server.wait_closed()
    asyncio.run(run())


@pytest.mark.parametrize('claims', [
    {'aud': 'https://foreign.example/mcp'}, {'sub': 'foreign-user'}, {'scope': 'mastermind.executive.intent.submit'},
    {'scope': 'mastermind.executive.read unrelated'}, {'exp': auth.NOW - 1},
])
def test_wrong_resource_principal_scopes_or_expiry_never_reads(rsa_key, claims):
    app, calls, _, _ = setup(rsa_key)
    claims = dict(claims)
    token = auth._token(rsa_key, scope=claims.pop('scope', auth.READ_SCOPE), **claims)
    assert asyncio.run(exchange(app, token))[0] == 401
    assert calls == []


@pytest.mark.parametrize('change', [
    {'query': b'work_ref=WS:OTHER'}, {'raw_path': b'/os/executive/session/%63onversations'},
    {'method': 'GET'}, {'scheme': 'http'}, {'path': '/os/executive/session/send'},
    {'changes': [(b'host', b'foreign.example')]}, {'changes': [(b'origin', b'https://foreign.example')]},
    {'changes': [(b'authorization', b'Bearer duplicate')]}, {'changes': [(b'content-encoding', b'gzip')]},
    {'changes': [(b'transfer-encoding', b'chunked')]}, {'changes': [(b'content-length', b'9')]},
    {'changes': [(b'content-type', b'application/json')]},
])
def test_framing_and_headers_fail_before_private_read(rsa_key, change):
    app, calls, _, _ = setup(rsa_key)
    assert asyncio.run(exchange(app, auth._read_token(rsa_key), **change))[0] != 200
    assert calls == []


@pytest.mark.parametrize('operation', CASES)
def test_extra_or_mixed_selectors_and_state_principal_cannot_supply_authority(rsa_key, operation):
    app, calls, _, _ = setup(rsa_key, operation)
    args = dict(CASES[operation][0], operation_key='invented')
    assert asyncio.run(exchange(app, auth._read_token(rsa_key), operation, args,
        state={'principal': 'injected', 'history_context': {'reply_read': True}}))[0] == 400
    assert calls == []


@pytest.mark.parametrize('packet', [b'{"arguments":{"work_ref":"WS:ONE","work_ref":"WS:OTHER"}}',
    b'{"arguments":{"work_ref":"WS:ONE"},"principal":{}}', b'{"arguments":NaN}',
    b'\xff', b' ' * 8193, b'{}', b'[]'])
def test_invalid_closed_body_never_reads_or_echoes_data(rsa_key, packet):
    app, calls, _, _ = setup(rsa_key)
    assert asyncio.run(exchange(app, auth._read_token(rsa_key), body=packet))[0] == 400
    assert calls == []


def test_expiry_after_body_withholds_before_socket_and_ignores_asgi_state(rsa_key):
    app, calls, clock, _ = setup(rsa_key)
    def expired(): clock[0] = auth.NOW + 301
    assert asyncio.run(exchange(app, auth._read_token(rsa_key), on_receive=expired,
        state={'principal': 'actual-looking-but-foreign'}))[0] == 401
    assert calls == []


def test_late_revocation_after_one_read_withholds_body_without_retry(rsa_key):
    app, calls, _, audit = setup(rsa_key)
    def revoked(): audit.fail = True
    # Trusted test peer executes the revocation only after the one fixed call.
    original = app._reader._client._send_frame
    async def late(self, *args, **kwargs):
        result = await original(*args, **kwargs)
        revoked()
        return result
    client = app._reader._client
    client._send_frame = MethodType(late, client)
    app._reader._inner = client._send_frame
    status, data = asyncio.run(exchange(app, auth._read_token(rsa_key)))
    assert status == 401 and set(data) == {'error'} and len(calls) == 1


def test_auth_owner_replacement_during_receive_refuses_before_private_call(rsa_key):
    app, calls, _, _ = setup(rsa_key)
    def replace(): app._owner._read_pair = tuple(list(app._owner._read_pair))
    assert asyncio.run(exchange(app, auth._read_token(rsa_key), on_receive=replace))[0] == 401
    assert calls == []


@pytest.mark.parametrize('operation', CASES)
def test_foreign_work_or_response_selectors_are_withheld(rsa_key, operation):
    bad = copy.deepcopy(CASES[operation][1])
    if operation in {'fresh_read', 'execution_read'}: bad['reference']['root_event_sha256'] = '0' * 64
    else: bad['work_ref'] = 'WS:FOREIGN'
    app, calls, _, _ = setup(rsa_key, operation, result=bad)
    status, result = asyncio.run(exchange(app, auth._read_token(rsa_key), operation))
    assert status == 503 and result == {'error': 'project_conversations_unavailable'}
    assert len(calls) == 1


@pytest.mark.parametrize('field', ['digest', 'run', 'consumption', 'epoch', 'can_send', 'extra'])
def test_fresh_source_result_tuple_and_read_only_state_are_closed(field):
    value = copy.deepcopy(FRESH['archived_read'])
    if field == 'digest': value['initial_result']['digest'] = '0' * 64
    if field == 'run': value['locator']['attempt_id'] = 'ATT-foreign'
    if field == 'consumption': value['initial_consumption']['initial_digest'] = '0' * 64
    if field == 'epoch': value['epoch'] = FRESH['initial_read']['epoch']
    if field == 'can_send': value['can_send'] = True
    if field == 'extra': value['operation_key'] = 'PRIVATE-KEY'
    with pytest.raises(Exception):
        validate_result(value, 'fresh_read', FRESH['initial_read']['reference'])


def test_actual_archived_followup_dto_remains_exact_without_fake_target_or_key():
    assert validate_result(FRESH['archived_read'], 'fresh_read', FRESH['initial_read']['reference']) == FRESH['archived_read']
