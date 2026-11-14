"""HTTP bearer MCP -> private bridge -> Runtime -> signed fake callback -> exact read.

This exercises the installed classes and full source composition. Native and
HTTPS peers are fake; no production account, worker or real Dot is involved.
"""
import asyncio
import base64
import dataclasses
import json
import socket
import time
from types import SimpleNamespace

import httpx
import pytest

import test_executive_mcp_web_ceo_sessions as host_fixture
import test_mastermind_executive_app_asgi as auth_fixture
from control_plane.executive_runtime import Runtime
from integrations.executive_mcp import server
from integrations.mastermind_executive_app.gateway import CeoIngressResponse, TRANSPORT_SENT_OK
from integrations.session_bridge.installed import InstalledSessionBridgeClient, build_runtime_session_bridge
from integrations.session_bridge.installed_reply_events import RuntimeReplyEventHost, InstalledReplyEventClient
from integrations.session_bridge.return_tools import NativeReplyReadTool
from integrations.session_bridge.reply_policy_selection import ReplyPolicySelection
from integrations.session_bridge.runtime_reply_subscriptions import ExecutiveReplyCipher
from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector, RuntimeCodexTargetProjector
from integrations.session_bridge.runtime_return import RuntimeSessionReturn
from integrations.session_bridge.t3_native_client import T3NativeClient, Run, Unavailable
from integrations.session_bridge.t3_reply_events import T3OriginalReplySource
from integrations.session_bridge.t3_reply_monitor import RuntimeT3ReplyMonitor
from integrations.session_bridge.t3_native_watch import T3NativeReturnWait
from integrations.session_bridge.t3_return_tools import T3ReturnTools, RuntimeT3ReturnControl, LINK, STATUS
from integrations.session_bridge.web_reply_event_rpc import WebReplyEventRpc
from tests.test_t3_native_client import Native, SCHEMAS, SCOPE, THREAD, schema
from tests.test_session_bridge_web_reply_event_asgi import wire, request

rsa_key = host_fixture.rsa_key
short_socket_root = host_fixture.short_socket_root
settings = host_fixture.settings


@pytest.fixture
def full_path(settings, rsa_key, tmp_path):
    now = int(time.time())
    settings = dataclasses.replace(settings, clock=lambda: now, read_from_ceo_ingress=True)
    policies = ReplyPolicySelection((settings.policies,))
    runtime, native, sent, frames = Runtime.at(tmp_path / 'return-runtime'), Native(), [], []
    native.detail['thread'].update(status='running', activeRunId='run-1', pendingRequestCount=1)
    native.responses['t3_thread_wait'] = {'structuredContent': {'threadId': THREAD.thread_id,
        'runId': 'run-1', 'status': 'running', 'timedOut': True}}
    question = {'threadId': THREAD.thread_id, 'runId': 'run-1', 'requestId': 'pending-1',
        'kind': 'user_input', 'status': 'pending', 'questions': [{'id': 'dataset', 'question': 'Which dataset?'}]}
    native.responses['t3_pending_request'] = lambda args: {'structuredContent':
        {'requestIds': ['pending-1']} if args['action'] == 'list' else question}
    schemas = dict(SCHEMAS, t3_pending_request=schema('environmentId', 'threadId', 'action', 'requestId', 'answers'))
    native_client = T3NativeClient(SCOPE, native, schemas)
    def current(principal):
        policies.select(principal)
        return principal
    async def access(principal, scope):
        current(principal)
        if scope != SCOPE: raise Unavailable('fixture scope not enrolled')
        return native_client
    source = T3OriginalReplySource(runtime, access, current=current, clock=lambda: now, enabled=True)
    fabric = RuntimeFabricTargetProjector(runtime)
    codex = RuntimeCodexTargetProjector(fabric, owner_configured=lambda: False)
    returns = RuntimeSessionReturn(runtime, fabric=fabric, codex=codex,
        socket_path=tmp_path / 'unused-dialogue.sock', t3_replies=source)
    class HTTPS:
        def request(self, method, path, body=None, headers=None):
            packet = json.loads(body)
            sent.append((packet, headers))
            self.body = json.dumps({'challenge': packet['challenge']}).encode() if packet.get('type') == 'verification' else b'accepted'
        def getresponse(self): return SimpleNamespace(status=200, read=lambda limit: self.body)
        def close(self): pass
    def dns(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
    event_host = RuntimeReplyEventHost(returns, ExecutiveReplyCipher('fixture', b'k' * 32), policies,
        clock=lambda: now, enabled=True, resolver=dns, connector=lambda *args: HTTPS())
    event_host.t3_monitor = RuntimeT3ReplyMonitor(event_host,
        observer_factory=lambda *a, **k: T3NativeReturnWait(*a, **k, timeout_ms=1, minimum_interval_seconds=0.02))
    bridge = build_runtime_session_bridge(runtime, dialogue_socket_path=returns.socket_path,
        codex_owner_configured=lambda: False, t3_replies=source,
        t3_return_control=RuntimeT3ReturnControl(event_host))
    class PrivatePeer:
        async def send_frame(self, path, frame):
            frames.append(frame)
            if 'tool' in frame:
                bridge.validate_frame(frame)
                result = await bridge.handle_frame(frame)
            else:
                event_host.validate_frame(frame)
                result = await event_host.handle_frame(frame)
            return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True, result=result)
    peer = PrivatePeer()
    client = InstalledSessionBridgeClient(settings.ceo_ingress_socket_path, client=peer)
    event_client = InstalledReplyEventClient(settings.ceo_ingress_socket_path, policies, client=peer)
    tools, reader = T3ReturnTools(client), NativeReplyReadTool(client)
    owners = host_fixture.Owners()
    async def no_mdm(**kwargs): raise AssertionError('T3 return cannot call MDM')
    app = server.build_web_ceo_v3_mcp_app(settings, audit_sink=host_fixture.Sink(),
        mdm_reader=SimpleNamespace(list_macos_devices=no_mdm, device=no_mdm),
        session_target_projector=host_fixture.Projector(), session_reply_handler=owners.reply,
        session_summon_handler=owners.summon, session_reply_read_tool=reader,
        reply_event_rpc=WebReplyEventRpc(event_client, clock=lambda: now), t3_return_tools=tools)
    token = auth_fixture._submit_token(rsa_key, iat=now - 10, nbf=now - 10, exp=now + 600)
    read_token = auth_fixture._read_token(rsa_key, iat=now - 10, nbf=now - 10, exp=now + 600)
    return SimpleNamespace(app=app, host=event_host, native=native, sent=sent, frames=frames,
        token=token, read_token=read_token, question=question,
        run=dataclasses.asdict(Run(THREAD, 'run-1', 'original-request', 'launched')))


async def until(predicate):
    for _ in range(300):
        if predicate(): return
        await asyncio.sleep(0.01)
    raise AssertionError('source consumer journey failed to reach bounded observation')


def test_authenticated_original_dot_journey_links_subscribes_receives_and_reads_question(full_path):
    case = full_path
    async def scenario():
        try:
            async with case.app._app.router.lifespan_context(case.app._app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=case.app), base_url='http://127.0.0.1') as http:
                    response, linked = await host_fixture.call(http, case.token, LINK, {'run': case.run})
                    assert response.status_code == 200 and linked['ok'] is True, linked
                    binding = linked['data']['binding']
                    assert not case.sent
                    event = {'name': 'session.reply_committed', 'arguments': {'request_ref': binding['request_ref']},
                        'delivery': {'mode': 'webhook', 'url': 'https://receiver.example.com/original-dot',
                            'secret': 'whsec_' + base64.b64encode(b's' * 32).decode()}, 'cursor': None}
                    subscribed = await http.post('/mcp', headers=wire(case.token), json=request('events/subscribe', event))
                    assert subscribed.status_code == 200 and 'result' in subscribed.json(), subscribed.text
                    await until(lambda: len(case.sent) == 2)
                    notification, headers = case.sent[1]
                    assert 'signature' in ' '.join(headers)
                    assert notification['data']['message_key'].startswith('t3-native-question-')
                    response, reply = await host_fixture.call(http, case.token, 'session_reply_read',
                        {'read_ref': notification['data']['read_ref'], 'message_key': notification['data']['message_key']})
                    assert response.status_code == 200 and reply['ok'] is True, reply
                    assert reply['data']['questions'] == case.question['questions']
                    assert reply['data']['run_complete'] is False and reply['data']['parent_consumed'] is False
                    response, status = await host_fixture.call(http, case.token, STATUS,
                        {'request_ref': binding['request_ref']})
                    assert response.status_code == 200 and status['ok'] is True, status
                    assert status['data']['observer']['native_inference_started'] is False
                    assert all(name not in {'t3_thread_launch', 't3_thread_send'} for name, _ in case.native.calls)
        finally:
            await case.host.close_native_returns()
    asyncio.run(scenario())


def test_actual_mcp_read_token_cannot_link_native_return(full_path):
    case = full_path
    async def scenario():
        async with case.app._app.router.lifespan_context(case.app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=case.app), base_url='http://127.0.0.1') as http:
                response, value = await host_fixture.call(http, case.read_token, LINK, {'run': case.run})
                assert response.status_code == 403 or value.get('ok') is False, value
                assert not case.frames and not case.native.calls and not case.sent
    asyncio.run(scenario())


def test_actual_mcp_catalog_exposes_narrow_return_tools_without_shell(full_path):
    case = full_path
    async def scenario():
        async with case.app._app.router.lifespan_context(case.app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=case.app), base_url='http://127.0.0.1') as http:
                response = await host_fixture.rpc(http, case.token, 'tools/list')
                assert response.status_code == 200, response.text
                tools = {tool['name']: tool for tool in response.json()['result']['tools']}
                assert LINK in tools and STATUS in tools and 'session_reply_read' in tools
                assert not {'start_process', 'read_file', 'ssh', 'bash'} & set(tools)
                assert tools[LINK]['annotations']['readOnlyHint'] is False
                assert tools[LINK]['annotations']['idempotentHint'] is False
                assert tools[STATUS]['annotations']['readOnlyHint'] is True
                assert tools[LINK]['securitySchemes'] != tools[STATUS]['securitySchemes']
        assert not case.frames and not case.native.calls
    asyncio.run(scenario())
