"""Optional producer: signed MCP -> fixed target -> original App/Control owner."""
import asyncio
import json

import httpx
import pytest

from integrations.executive_mcp.server import build_principal_ruling_mcp_app
from integrations.mastermind_executive_app.principal_dialogue import PrincipalDialogueForwardResult
from integrations.mastermind_executive_app.principal_ruling_http import (
    PRINCIPAL_RULING_MCP_PATH as PATH, PrincipalRulingTarget,
)
from tests import test_executive_principal_dialogue_forward as fixture
from tests import test_principal_app_original_worker_journey as journey

rsa_key = fixture.rsa_key


def headers(token):
    return {"authorization": "Bearer " + token,
        "accept": "application/json, text/event-stream", "content-type": "application/json",
        "mcp-protocol-version": "2025-06-18"}


def rpc(method="tools/call", name="ruling", arguments=None):
    data = {"jsonrpc": "2.0", "id": 1, "method": method}
    if method == "tools/call":
        data["params"] = {"name": name, "arguments": fixture.RULING if arguments is None else arguments}
    return data


def payload(response):
    assert response.status_code == 200, response.text
    return json.loads(response.json()["result"]["content"][0]["text"])


def target():
    return PrincipalRulingTarget("WS:ONE", fixture.obligation_id(), fixture.SURFACE)


@pytest.mark.parametrize("field,value", [("work_ref", "foreign work"), ("obligation_id", "WAKE-invalid"),
    ("reasoning_surface", "invalid surface"), ("work_ref", None)])
def test_host_selection_must_be_exact(field, value):
    import dataclasses
    with pytest.raises(ValueError):
        dataclasses.replace(target(), **{field: value})


def test_static_ruling_facet_sends_one_exact_host_target(rsa_key, tmp_path):
    core, token, _, client = fixture.setup_client(rsa_key, tmp_path,
        response=fixture.sent_ok(fixture.ruling_envelope()))
    app = build_principal_ruling_mcp_app(core, target=target())

    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
                listed = await http.post(PATH, headers=headers(token), json=rpc("tools/list"))
                tools = listed.json()["result"]["tools"]
                assert [tool["name"] for tool in tools] == ["ruling"]
                assert set(tools[0]["inputSchema"]["properties"]) == set(fixture.RULING)
                assert tools[0]["securitySchemes"][0]["scopes"] == list(core.settings.policy.required_scopes)
                result = payload(await http.post(PATH, headers=headers(token), json=rpc()))
                assert result["ok"] is True and result["obligation_id"] == target().obligation_id
                assert result["result"]["data"] == {"ruling": "recorded"}
    asyncio.run(exercise())
    assert len(client.frames) == 1
    assert client.frames[0]["obligation_id"] == target().obligation_id
    assert client.frames[0]["arguments"] == fixture.RULING


@pytest.mark.parametrize("fault", ["transport_lost", "post_send_auth", "not_sent"])
def test_transport_outcome_retains_original_obligation_without_replay(rsa_key, tmp_path, fault):
    from integrations.mastermind_executive_app.gateway import (
        TRANSPORT_NOT_SENT, TRANSPORT_SENT_UNKNOWN, CeoIngressResponse,
    )
    core, token, current, client = fixture.setup_client(rsa_key, tmp_path,
        response=fixture.sent_ok(fixture.ruling_envelope()))
    if fault == "transport_lost": client.exc = OSError("PRIVATE_CANARY")
    elif fault == "post_send_auth": client.after_send = lambda: current["binding"].update(enabled=False)
    else: client.response = CeoIngressResponse(transport=TRANSPORT_NOT_SENT)
    app = build_principal_ruling_mcp_app(core, target=target())
    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
                response = await http.post(PATH, headers=headers(token), json=rpc())
                result = payload(response)
                assert result["ok"] is False and result["result"] is None
                assert result["obligation_id"] == target().obligation_id
                assert result["transport"] == (TRANSPORT_NOT_SENT if fault == "not_sent" else TRANSPORT_SENT_UNKNOWN)
                assert "PRIVATE_CANARY" not in response.text
    asyncio.run(exercise())
    assert len(client.frames) == 1


@pytest.mark.parametrize("fault", ["missing_auth", "duplicate_auth", "wrong_scope", "binding", "grant", "owed",
    "caller", "obligation", "work", "continue", "extra", "duplicate_json", "nonfinite", "oversized"])
def test_unqualified_or_ambiguous_request_never_sends(rsa_key, tmp_path, fault):
    core, token, current, client = fixture.setup_client(rsa_key, tmp_path)
    request_headers = headers(token)
    body = rpc()
    # Avoid sharing mutable fixture data across test cases.
    body = json.loads(json.dumps(body))
    if fault == "missing_auth": del request_headers["authorization"]
    elif fault == "duplicate_auth":
        request_headers = list(request_headers.items()) + [("Authorization", "Bearer invalid")]
    elif fault == "wrong_scope":
        request_headers = headers(fixture.fixture.fixture._read_token(rsa_key))
    elif fault == "binding": current["binding"]["enabled"] = False
    elif fault == "grant":
        import dataclasses
        current["authority"] = dataclasses.replace(current["authority"], principal_actions=("bounded_intent",))
    elif fault == "owed": current["mission"]["principal"]["owed_turn"]["seat"] = "worker"
    elif fault in {"caller", "obligation", "work"}:
        body["params"]["arguments"][{"caller": "caller", "obligation": "obligation_id", "work": "work_ref"}[fault]] = "foreign"
    elif fault == "continue": body["params"]["name"] = "continue"
    elif fault == "extra": body["params"]["arguments"]["peer_uid"] = 458
    raw = json.dumps(body).encode()
    if fault == "duplicate_json": raw = raw.replace(b'"selected_option":', b'"selected_option":"opt-other","selected_option":')
    elif fault == "nonfinite": raw = raw.replace(b'"id": 1', b'"id": NaN')
    elif fault == "oversized": raw = b" " * 65537
    app = build_principal_ruling_mcp_app(core, target=target())
    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
                response = await http.post(PATH, headers=request_headers, content=raw)
                if fault == "oversized": assert response.status_code == 413
                if fault == "missing_auth":
                    assert response.status_code == 401
                    assert core.settings.policy.resource_metadata_url in response.headers["www-authenticate"]
                if fault in {"duplicate_auth", "duplicate_json", "nonfinite", "oversized"}:
                    assert response.json()["ok"] is False
                    assert set(response.json()["error"]) == {"code", "message"}
                if fault in {"grant", "owed", "caller", "obligation", "work", "continue", "extra"}:
                    # These must reach the authenticated semantic/tool fence;
                    # a generic HTTP Content-Type refusal proves nothing here.
                    assert response.status_code == 200, response.text
                if response.status_code == 200:
                    assert response.json()["result"]["isError"] is True
                else:
                    assert response.status_code in (400, 401, 403, 413)
    asyncio.run(exercise())
    assert client.frames == []


@pytest.mark.parametrize("path,method", [(PATH+"/", "POST"), (PATH+"?x=1", "POST"),
    ("/mcp%2Fprincipal-ruling", "POST"), ("/mcp/coo", "POST"), (PATH, "GET")])
def test_only_literal_selected_route_is_exposed(rsa_key, tmp_path, path, method):
    core, token, _, client = fixture.setup_client(rsa_key, tmp_path)
    app = build_principal_ruling_mcp_app(core, target=target())
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
            response = await http.request(method, path, headers=headers(token), json=rpc())
            assert response.status_code == 404
            assert response.json() == {"ok": False, "error": {"code": "not_found", "message": "route not found"}}
    asyncio.run(exercise())
    assert client.frames == []


@pytest.mark.parametrize("lose_response", [False, True])
@pytest.mark.parametrize("host_local", [False, True])
def test_signed_mcp_consumption_and_original_response_recovery(tmp_path, monkeypatch, rsa_key, lose_response, host_local):
    async def through_mcp(core, request, *, work_ref, obligation_id, arguments, reasoning_surface):
        app = build_principal_ruling_mcp_app(core,
            target=PrincipalRulingTarget(work_ref, obligation_id, reasoning_surface))
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
                h = headers(request.headers["authorization"].removeprefix("Bearer "))
                result = payload(await http.post(PATH, headers=h, json=rpc(arguments=arguments)))
        return PrincipalDialogueForwardResult(result["obligation_id"], result["transport"], result["result"])

    monkeypatch.setattr(journey, "forward_principal_ruling", through_mcp)
    journey.test_signed_app_forward_to_original_worker(tmp_path, monkeypatch, rsa_key, lose_response, host_local)


def test_post_send_response_budget_retains_uncertainty_without_second_send(rsa_key, tmp_path, monkeypatch):
    from integrations.executive_mcp import server
    from integrations.mastermind_executive_app.gateway import TRANSPORT_SENT_UNKNOWN
    # Lower only the serialization budget to reach the final defensive branch
    # with an otherwise valid, bounded inner result and the actual forwarder.
    monkeypatch.setattr(server, "MAX_RESPONSE_BYTES", 4097)
    core, token, _, client = fixture.setup_client(rsa_key, tmp_path,
        response=fixture.sent_ok(fixture.ruling_envelope()))
    app = build_principal_ruling_mcp_app(core, target=target())
    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
                result = payload(await http.post(PATH, headers=headers(token), json=rpc()))
                assert result["transport"] == TRANSPORT_SENT_UNKNOWN
                assert result["obligation_id"] == target().obligation_id
                assert result["ok"] is False and result["result"] is None
    asyncio.run(exercise())
    assert len(client.frames) == 1


def test_actual_asgi_lifespan_passes_through_boundary(rsa_key, tmp_path):
    core, token, _, client = fixture.setup_client(rsa_key, tmp_path)
    app = build_principal_ruling_mcp_app(core, target=target())
    async def exercise():
        events, received = asyncio.Queue(), asyncio.Queue()
        task = asyncio.create_task(app({"type": "lifespan", "asgi": {"version": "3.0"}},
            events.get, received.put))
        await events.put({"type": "lifespan.startup"})
        assert (await asyncio.wait_for(received.get(), 5))["type"] == "lifespan.startup.complete"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
            response = await http.post(PATH, headers=headers(token), json=rpc("tools/list"))
            assert response.status_code == 200
        await events.put({"type": "lifespan.shutdown"})
        assert (await asyncio.wait_for(received.get(), 5))["type"] == "lifespan.shutdown.complete"
        await asyncio.wait_for(task, 5)
    asyncio.run(exercise())
    assert client.frames == []


@pytest.mark.parametrize("header,value", [("host", "attacker.invalid"), ("origin", "https://attacker.invalid")])
def test_sdk_transport_security_blocks_foreign_host_and_origin(rsa_key, tmp_path, header, value):
    core, token, _, client = fixture.setup_client(rsa_key, tmp_path)
    app = build_principal_ruling_mcp_app(core, target=target())
    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
                response = await http.post(PATH, headers={**headers(token), header: value}, json=rpc())
                assert response.status_code == (421 if header == "host" else 403)
    asyncio.run(exercise())
    assert client.frames == []
