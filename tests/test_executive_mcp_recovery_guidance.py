"""Existing MCP tools must explain unknown-result recovery without a new write."""
import asyncio
import json
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_mastermind_executive_app_asgi as fixture
finally:
    sys.path.pop(0)

from control_plane import ceo_request
from integrations.executive_mcp import server as transport
from integrations.mastermind_executive_app import app as app_module
from integrations.mastermind_executive_app.admission import AdmissionOutcome

rsa_key = fixture.rsa_key
BUILDERS = [transport.build_executive_mcp_app, transport.build_web_ceo_mcp_app,
            transport.build_web_ceo_v2_mcp_app]
PAYLOAD = {"operation_key":"mcp-recovery-guidance-001", "objective":"Read the fixture.",
           "department":"executive-infrastructure", "priority":5, "execution_profile":"research_only"}

class Sink:
    def emit(self, event):
        pass


def execute(builder, rsa_key, tmp_path, monkeypatch, outcome, *, read_only_token=False):
    calls=[]
    async def compose(request):
        calls.append(request)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    monkeypatch.setattr(app_module, "compose_admission", compose)
    settings=fixture._real_app_settings(rsa_key, mastermind_root=tmp_path/"unused-mm",
        macro_root=tmp_path/"unused-macro", ceo_ingress_socket_path=tmp_path/"must-not-open.sock")
    async def exercise():
        app=builder(settings,audit_sink=Sink())
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://127.0.0.1") as client:
                token=(fixture._read_token if read_only_token else fixture._submit_token)(rsa_key)
                response=await client.post("/mcp",headers={"authorization":"Bearer "+token,
                    "accept":"application/json, text/event-stream", "mcp-protocol-version":"2025-06-18"},
                    json={"jsonrpc":"2.0","id":1,"method":"tools/call",
                          "params":{"name":"submit_ceo_intent","arguments":PAYLOAD}})
                assert response.status_code==200,response.text
                result=response.json()["result"]
                return result,json.loads(result["content"][0]["text"])
    result=asyncio.run(exercise())
    return result,calls


@pytest.mark.parametrize("builder", BUILDERS)
@pytest.mark.parametrize("failure", ["known_unknown","exception","wrong_identity"])
def test_unknown_guidance_names_existing_status_tool_and_exact_intent(builder,failure,rsa_key,tmp_path,monkeypatch):
    request_ref=ceo_request.app_request_ref(PAYLOAD["operation_key"])
    if failure=="exception":
        outcome=RuntimeError("untrusted inner error must not be forwarded")
    else:
        outcome=AdmissionOutcome(status="effect_unknown",
            request_ref=request_ref if failure=="known_unknown" else "req-wrong00000000",
            code="effect_unknown",message="backend prose is not a recovery identifier")
    (result,body),calls=execute(builder,rsa_key,tmp_path,monkeypatch,outcome)
    assert len(calls)==1
    assert result["isError"] is True
    assert set(body)=={"ok","status","request_ref","error"}
    assert body["ok"] is False and body["status"]=="effect_unknown"
    assert body["request_ref"]==request_ref
    assert set(body["error"])=={"code","message"}
    assert body["error"]["code"]=="effect_unknown"
    message=body["error"]["message"]
    assert "ceo_intent_status" in message
    assert "intent_id="+ceo_request.automated_intent_id(request_ref) in message
    assert "not_found" in message and "does not authorize resubmission" in message
    assert "untrusted inner error" not in message
    assert "backend prose" not in message
    assert "req-wrong" not in message
    assert "receipt" not in body


@pytest.mark.parametrize("builder", BUILDERS)
@pytest.mark.parametrize("status", ["accepted","refused"])
def test_known_result_or_refusal_is_not_rewritten(builder,status,rsa_key,tmp_path,monkeypatch):
    ref=ceo_request.app_request_ref(PAYLOAD["operation_key"])
    if status=="accepted":
        receipt={"job_id":"JOB-001","dispatched":False,"status":"QUEUED"}
        outcome=AdmissionOutcome(status=status,request_ref=ref,receipt=receipt)
    else:
        outcome=AdmissionOutcome(status=status,request_ref=ref,code="authority_refused",message="original exact refusal")
    (result,body),calls=execute(builder,rsa_key,tmp_path,monkeypatch,outcome)
    assert len(calls)==1 and body["status"]==status and body["request_ref"]==ref
    if status=="accepted":
        assert result["isError"] is False and body["receipt"]==receipt
    else:
        assert result["isError"] is True
        assert body["error"]=={"code":"authority_refused","message":"original exact refusal"}


@pytest.mark.parametrize("builder", BUILDERS)
def test_read_permission_cannot_use_recovery_guidance_to_submit(builder,rsa_key,tmp_path,monkeypatch):
    (result,body),calls=execute(builder,rsa_key,tmp_path,monkeypatch,
        RuntimeError("must not be called"),read_only_token=True)
    assert not calls
    assert result["isError"] is True
    assert body["error"]["code"]=="scope_refused"
    assert "request_ref" not in body
