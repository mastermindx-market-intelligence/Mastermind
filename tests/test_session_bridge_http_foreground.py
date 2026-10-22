import asyncio
import json
from pathlib import Path
import pytest
from starlette.requests import Request
import test_executive_mcp_web_ceo_sessions as host
import test_mastermind_executive_app_asgi as auth
from integrations.session_bridge import http_foreground as life
rsa_key = host.rsa_key
short_socket_root = host.short_socket_root
settings = host.settings

from integrations.executive_mcp import server as transport
from integrations.mastermind_executive_app import gateway

async def drive(app, token, entered, *, disconnect=True):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "session_summon", "arguments": {"objective": "bounded qualification",
        "execution_profile": "research_only", "operation_key": "candidate-source-only",
        "department": "executive-infrastructure", "priority": 0,
        "workstream": "WS:SESSION-BRIDGE"}}}).encode()
    headers = {**host.headers(token), "host": "127.0.0.1", "content-type": "application/json"}
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1", "scheme": "http", "method": "POST", "path": "/mcp",
        "raw_path": b"/mcp", "root_path": "", "query_string": b"",
        "headers": [(k.encode(),v.encode()) for k,v in headers.items()],
        "client": ("127.0.0.1", 39999), "server": ("127.0.0.1", 80)}
    frames, outputs = asyncio.Queue(), []
    await frames.put({"type": "http.request", "body": body, "more_body": False})
    async def receive(): return await frames.get()
    async def send(frame): outputs.append(frame)
    async with app._app.router.lifespan_context(app._app):
        task = asyncio.create_task(app(scope, receive, send))
        if entered is not None:
            await asyncio.wait_for(entered.wait(), 3)
            if disconnect: await frames.put({"type": "http.disconnect"})
        await asyncio.wait_for(task, 3)
    data = b"".join(x.get("body",b"") for x in outputs if x["type"]=="http.response.body")
    return json.loads(data)

def app_for(settings, summon):
    return transport.build_web_ceo_sessions_mcp_app(settings, audit_sink=host.Sink(),
        session_target_projector=host.Projector(), session_reply_handler=host.Owners().reply,
        session_summon_handler=summon)

def inner(data): return json.loads(data["result"]["content"][0]["text"])

def test_upstream_disconnect_closes_actual_unix_peer_and_reports_original_unknown(settings,rsa_key,short_socket_root):
    async def run():
        entered, peer_eof = asyncio.Event(), asyncio.Event()
        frame = {}
        async def peer(reader,writer):
            frame.update(json.loads(await reader.readline()))
            entered.set()
            try:
                assert await reader.read() == b""
                peer_eof.set()
            finally:
                writer.close(); await writer.wait_closed()
        socket = short_socket_root/"actual-candidate.sock"
        listener = await asyncio.start_unix_server(peer, str(socket))
        async def summon(principal,args):
            client = gateway.CeoIngressClient()
            response = await client.send_foreground_frame(socket, {"schema":
                "mastermind.executive_ceo_ingress_session_bridge.v1", "tool":"session_summon",
                "principal": {}, "arguments":args})
            return {"transport": response.transport}
        try:
            result = await drive(app_for(settings,summon),auth._submit_token(rsa_key),entered)
            await asyncio.wait_for(peer_eof.wait(),1)
            assert inner(result)["error"]["code"] == "effect_unknown"
            assert frame["schema"] == "mastermind.executive_ceo_ingress_session_bridge_foreground.v1"
        finally:
            listener.close(); await listener.wait_closed()
    asyncio.run(run())

def test_bounded_deadline_ends_actual_handler_and_handle(settings,rsa_key,monkeypatch):
    original = life.owned_request
    def short(scope,receive): return original(scope,receive,deadline_seconds=0.05)
    monkeypatch.setattr(life,"owned_request",short)
    async def run():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        held = []
        async def summon(principal,args):
            held.append(life.current_request()); entered.set()
            try: await asyncio.Event().wait()
            finally: cancelled.set()
        result = await drive(app_for(settings,summon),auth._submit_token(rsa_key),entered,disconnect=False)
        assert cancelled.is_set()
        assert inner(result)["error"]["code"] == "effect_unknown"
        with pytest.raises(life.HttpForegroundClosed): held[0].require_live()
        with pytest.raises(life.HttpForegroundClosed): life.current_request()
    asyncio.run(run())

def test_actual_authenticated_success_retains_request_until_result_then_closes(settings,rsa_key):
    async def run():
        held=[]
        resume=asyncio.Event()
        late=[]
        async def copied_task():
            await resume.wait()
            with pytest.raises(life.HttpForegroundClosed): life.current_request()
        async def summon(principal,args):
            source=life.current_request();held.append(source)
            late.append(asyncio.create_task(copied_task()))
            await asyncio.sleep(0)
            source.require_live()
            assert 0<source.remaining_seconds()<=300
            return {"same_request":True,"operation_key":args["operation_key"]}
        result=await drive(app_for(settings,summon),auth._submit_token(rsa_key),None,disconnect=False)
        assert inner(result)["ok"] is True
        assert inner(result)["data"]["same_request"] is True
        with pytest.raises(life.HttpForegroundClosed):held[0].require_live()
        resume.set()
        await asyncio.wait_for(late[0],1)
    asyncio.run(run())

def test_read_only_bearer_cannot_bind_submit_request(settings,rsa_key):
    async def run():
        async def forbidden(principal,args):raise AssertionError("submit authority cannot come from transport")
        result=await drive(app_for(settings,forbidden),auth._read_token(rsa_key),None,disconnect=False)
        assert result["result"]["isError"] is True
    asyncio.run(run())

def test_direct_foreground_transport_without_actual_request_refuses_before_connect(tmp_path):
    async def run():
        response=await gateway.CeoIngressClient().send_foreground_frame(tmp_path/"absent.sock",
            {"schema":"mastermind.executive_ceo_ingress_session_bridge.v1",
             "tool":"session_summon","principal":{},"arguments":{}})
        assert response.transport==gateway.TRANSPORT_NOT_SENT
        assert "upstream" in response.detail
    asyncio.run(run())

def test_forged_scope_object_cannot_bind_verified_request():
    class DTO:pass
    request=Request({"type":"http",life._SCOPE_KEY:DTO()})
    with pytest.raises(life.HttpForegroundClosed):
        with life.bind_request(request,DTO()):pass


def test_expired_bound_request_cannot_fall_back_to_incumbent_transport(tmp_path):
    from types import SimpleNamespace
    from integrations.session_bridge.installed import InstalledSessionBridgeClient
    from integrations.session_bridge.schemas import BridgeError
    from tests.test_session_bridge_installed import PRINCIPAL
    calls=[]
    class Transport:
        async def send_frame(self,*args):calls.append("legacy");raise AssertionError("expired fallback")
        async def send_foreground_frame(self,*args):calls.append("foreground");raise AssertionError("expired send")
    async def run():
        async def receive():await asyncio.Event().wait()
        async with life.owned_request({"type":"http"},receive) as scope:
            now=int(life.time.time())
            with life.bind_request(Request(scope),SimpleNamespace(issued_at=now-1,expires_at=now+10)) as source:
                source.close()
                client=InstalledSessionBridgeClient(tmp_path/"absent.sock",client=Transport())
                with pytest.raises(BridgeError) as raised:
                    await client.summon(PRINCIPAL,{"objective":"bounded", "execution_profile":"research_only",
                        "operation_key":"expired-origin", "department":"executive-infrastructure",
                        "priority":0,"workstream":"WS:SESSION-BRIDGE"})
                assert raised.value.code=="effect_unknown"
        assert calls==[]
    asyncio.run(run())
