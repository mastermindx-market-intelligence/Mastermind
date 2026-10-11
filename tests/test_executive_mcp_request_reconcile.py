"""V3 request reconciliation crosses real MCP/App auth and only the status seam."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import dataclasses
import json
import os
from pathlib import Path
import sys

import httpx
import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_executive_mcp_web_ceo_sessions as session_fixture
    import test_mastermind_executive_app_asgi as fixture
    from test_executive_mcp_web_ceo_v3 import FakeMdm
finally:
    sys.path.pop(0)

from control_plane import ceo_request
from control_plane.executive_ceo_ingress import STATUS_SCHEMA_V2
from integrations.executive_mcp import server as transport
from integrations.executive_mcp import web_ceo_v3 as v3
from integrations.executive_mcp.schemas import GatewayError
from integrations.mastermind_executive_app import app as app_module
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient,
    CeoIngressResponse,
    TRANSPORT_NOT_SENT,
    TRANSPORT_SENT_OK,
    TRANSPORT_SENT_UNKNOWN,
)

rsa_key = fixture.rsa_key
short_socket_root = fixture.short_socket_root
settings = session_fixture.settings
REF = "req-4a8daf76317cfe92f436991444c58281"
RECEIPT = {
    "intent_id": ceo_request.automated_intent_id(REF),
    "job_id": "JOB-existing",
    "dispatched": False,
}
PATH = "/v1/tools/submit_ceo_intent/reconcile"


@asynccontextmanager
async def connection(settings):
    owners = session_fixture.Owners()
    projector = session_fixture.Projector()
    app = transport.build_web_ceo_v3_mcp_app(
        dataclasses.replace(settings, read_from_ceo_ingress=True),
        audit_sink=session_fixture.Sink(), mdm_reader=FakeMdm(),
        session_target_projector=projector,
        session_reply_handler=owners.reply, session_summon_handler=owners.summon,
    )
    async with app._app.router.lifespan_context(app._app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            yield client
    assert owners.reply_calls == [] and owners.summon_calls == [] and projector.calls == []


def capture_status(monkeypatch, outcome=None):
    frames = []

    async def send_frame(_self, path, frame):
        frames.append((path, frame))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome or CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True, result=RECEIPT)

    async def forbidden_submit(*args, **kwargs):
        pytest.fail("reconciliation must never compose an admission")

    monkeypatch.setattr(CeoIngressClient, "send_frame", send_frame)
    monkeypatch.setattr(app_module, "compose_admission", forbidden_submit)
    return frames


def assert_one_status(frames, settings):
    assert frames == [(settings.ceo_ingress_socket_path, {"schema": STATUS_SCHEMA_V2, "request_ref": REF})]


async def reconcile(client, token, arguments=None):
    return await session_fixture.call(
        client, token, v3.RECONCILE_TOOL_NAME,
        {"request_ref": REF} if arguments is None else arguments,
    )


def test_listing_advertises_read_only_behavior_and_submit_authorization(settings, rsa_key, monkeypatch):
    frames = capture_status(monkeypatch)

    async def run():
        async with connection(settings) as client:
            response = await session_fixture.rpc(client, fixture._read_token(rsa_key), "tools/list")
            tools = {tool["name"]: tool for tool in response.json()["result"]["tools"]}
            tool = tools[v3.RECONCILE_TOOL_NAME]
            assert tool["inputSchema"] == v3.RECONCILE_TOOL_SPEC.input_schema
            assert tool["annotations"]["readOnlyHint"] is True
            assert tool["annotations"]["destructiveHint"] is False
            assert tool["securitySchemes"] == tools["submit_ceo_intent"]["securitySchemes"]
            assert tool["_meta"]["securitySchemes"] == tool["securitySchemes"]
            assert tool["securitySchemes"] != tools["executive_state"]["securitySchemes"]
    asyncio.run(run())
    assert frames == []


def test_read_token_refused_before_status_and_challenged_for_submit(settings, rsa_key, monkeypatch):
    frames = capture_status(monkeypatch)

    async def run():
        async with connection(settings) as client:
            response, payload = await reconcile(client, fixture._read_token(rsa_key))
            assert payload["error"]["code"] == "scope_refused"
            result = response.json()["result"]
            assert result["isError"] is True
            challenge = result["_meta"]["mcp/www_authenticate"][0]
            assert all(scope in challenge for scope in settings.policies.submit.required_scopes)
    asyncio.run(run())
    assert frames == []


def test_submit_token_reads_one_exact_status_through_existing_app_route(settings, rsa_key, monkeypatch):
    frames = capture_status(monkeypatch)
    calls = []
    real_create = app_module.create_web_ceo_v3_app

    def observed_app(configured, **kwargs):
        app = real_create(configured, **kwargs)

        async def wrapped(scope, receive, send):
            request = await receive()
            calls.append((scope["path"], json.loads(request["body"])))

            async def replay():
                return request

            await app(scope, replay, send)

        wrapped.aclose = app.aclose
        return wrapped

    monkeypatch.setattr(app_module, "create_web_ceo_v3_app", observed_app)

    async def run():
        async with connection(settings) as client:
            response, payload = await reconcile(client, fixture._submit_token(rsa_key))
            assert response.json()["result"]["isError"] is False
            assert payload == {"ok": True, "status": "accepted", "request_ref": REF, "receipt": RECEIPT}
    asyncio.run(run())
    assert calls == [(PATH, {"request_ref": REF})]
    assert_one_status(frames, settings)


@pytest.mark.parametrize("arguments", [
    {}, {"request_ref": ""}, {"request_ref": "auto-existing"}, {"request_ref": "req-short"},
    {"request_ref": "req-UPPER123"}, {"request_ref": "req-" + "a" * 97},
    {"request_ref": REF + "\n"}, {"request_ref": " " + REF},
    {"request_ref": 123}, {"request_ref": None}, {"request_ref": [REF]},
    {"request_ref": REF, "operation_key": "new-operation"},
    {"request_ref": REF, "objective": "submit"}, {"request_ref": REF, "retry": True},
    {"request_ref": REF, "endpoint": "/v1/tools/submit_ceo_intent"},
])
def test_invalid_or_extra_fields_never_reach_app(settings, rsa_key, monkeypatch, arguments):
    frames = capture_status(monkeypatch)
    with pytest.raises(GatewayError):
        v3.validate_web_ceo_v3_tool_arguments(v3.RECONCILE_TOOL_NAME, arguments)

    async def run():
        async with connection(settings) as client:
            _response, payload = await reconcile(client, fixture._submit_token(rsa_key), arguments)
            assert payload["error"]["code"] == "invalid_input"
    asyncio.run(run())
    assert frames == []


@pytest.mark.parametrize("reference", [REF, "req-a1234567", "req-a._-1234", "req-" + "a" * 96])
def test_canonical_reference_domain_is_preserved_exactly(reference):
    arguments = {"request_ref": reference}
    jsonschema.validate(arguments, v3.RECONCILE_TOOL_SPEC.input_schema)
    assert v3.validate_web_ceo_v3_tool_arguments(v3.RECONCILE_TOOL_NAME, arguments) == arguments


@pytest.mark.parametrize("outcome,status,code", [
    (CeoIngressResponse(transport=TRANSPORT_SENT_UNKNOWN), "effect_unknown", "effect_unknown"),
    (CeoIngressResponse(transport=TRANSPORT_NOT_SENT), "ingress_unavailable", "ingress_unavailable"),
    (CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=False, error={"code": "not_found", "message": "absent"}), "refused", "not_found"),
    (CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=False, error={"code": "operation_conflict", "message": "conflict"}), "operation_conflict", "operation_conflict"),
    (CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=False, error={"code": "backend_unavailable", "message": "unavailable"}), "refused", "backend_unavailable"),
    (CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True, result={"dispatched": True}), "effect_unknown", "effect_unknown"),
    (CeoIngressResponse(
        transport=TRANSPORT_SENT_OK,
        ok=True,
        result={"intent_id": "auto-00000000000000000000000000000000", "job_id": "JOB-wrong", "dispatched": False},
    ), "effect_unknown", "effect_unknown"),
    (OSError("lost status response"), "effect_unknown", "effect_unknown"),
])
def test_status_outcomes_preserve_identity_without_retry(settings, rsa_key, monkeypatch, outcome, status, code):
    frames = capture_status(monkeypatch, outcome)

    async def run():
        async with connection(settings) as client:
            response, payload = await reconcile(client, fixture._submit_token(rsa_key))
            assert response.json()["result"]["isError"] is True
            assert payload["status"] == status
            assert payload["request_ref"] == REF
            assert payload["error"]["code"] == code
            if status == "effect_unknown":
                message = payload["error"]["message"]
                assert v3.RECONCILE_TOOL_NAME in message
                assert f"intent_id={ceo_request.automated_intent_id(REF)}" in message
                assert "does not authorize resubmission" in message
    asyncio.run(run())
    assert_one_status(frames, settings)


@pytest.mark.parametrize("damage", ["malformed", "mismatched_ref", "oversized", "escaped_oversized", "exception", "untrusted_auth"])
def test_damaged_app_reply_is_same_request_unknown_after_one_status(settings, rsa_key, monkeypatch, damage):
    frames = capture_status(monkeypatch)
    real_create = app_module.create_web_ceo_v3_app

    def damaged_app(configured, **kwargs):
        app = real_create(configured, **kwargs)

        async def wrapped(scope, receive, send):
            events = []

            async def collect(event):
                events.append(event)

            await app(scope, receive, collect)
            if damage == "exception":
                raise OSError("lost after status read")
            payload = json.loads(b"".join(event.get("body", b"") for event in events))
            status, headers = 200, []
            if damage == "malformed":
                body = b"{"
            elif damage == "oversized":
                body = b" " * 262145
            elif damage == "escaped_oversized":
                payload["receipt"]["large"] = '"' * 110000
                body = json.dumps(payload).encode()
            elif damage == "untrusted_auth":
                body = b'{"ok":false,"error":{"code":"scope_refused","message":"private diagnostic"}}'
                status, headers = 403, [(b"www-authenticate", b"private challenge")]
            else:
                payload["request_ref"] = "req-another1"
                body = json.dumps(payload).encode()
            await send({"type": "http.response.start", "status": status, "headers": headers})
            await send({"type": "http.response.body", "body": body})

        wrapped.aclose = app.aclose
        return wrapped

    monkeypatch.setattr(app_module, "create_web_ceo_v3_app", damaged_app)

    async def run():
        async with connection(settings) as client:
            response, payload = await reconcile(client, fixture._submit_token(rsa_key))
            assert response.json()["result"]["isError"] is True
            assert payload["status"] == "effect_unknown"
            assert payload["request_ref"] == REF
            assert "private" not in json.dumps(response.json())
    asyncio.run(run())
    assert_one_status(frames, settings)


def test_prior_profiles_and_intent_reader_do_not_accept_request_reconcile():
    from integrations.executive_mcp import schemas, web_ceo, web_ceo_sessions
    for validate in (
        schemas.validate_tool_arguments, web_ceo.validate_web_ceo_tool_arguments,
        web_ceo.validate_web_ceo_v2_tool_arguments,
        web_ceo_sessions.validate_web_ceo_sessions_tool_arguments,
    ):
        with pytest.raises(GatewayError):
            validate(v3.RECONCILE_TOOL_NAME, {"request_ref": REF})
    with pytest.raises(GatewayError):
        v3.validate_web_ceo_v3_tool_arguments("ceo_intent_status", {"request_ref": REF})


@pytest.mark.parametrize("mutation", ["wrong_issuer", "wrong_resource", "duplicate_authorization"])
def test_invalid_auth_stops_before_status(settings, rsa_key, monkeypatch, mutation):
    frames = capture_status(monkeypatch)
    token = fixture._submit_token(rsa_key)
    if mutation == "wrong_issuer":
        token = fixture._submit_token(rsa_key, iss="https://issuer.invalid/")
    if mutation == "wrong_resource":
        token = fixture._submit_token(rsa_key, aud="https://resource.invalid/")
    headers = list(session_fixture.headers(token).items())
    if mutation == "duplicate_authorization":
        headers.append(("authorization", f"Bearer {token}"))

    async def run():
        async with connection(settings) as client:
            response = await client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": v3.RECONCILE_TOOL_NAME, "arguments": {"request_ref": REF}},
            })
            assert response.status_code in (401, 403), response.text
    asyncio.run(run())
    assert frames == []


def test_real_committed_request_is_recovered_without_new_job_or_attempt(settings, rsa_key, tmp_path, short_socket_root, monkeypatch):
    """Only the initial fixture submit creates a Job; MCP status recovers it."""
    from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
    from integrations.executive_mcp.installed import InstalledExecutiveReaders

    real_create = app_module.create_web_ceo_v3_app
    submitted = []
    calls = []

    def lost_submit_app(configured, **kwargs):
        app = real_create(configured, **kwargs)

        async def wrapped(scope, receive, send):
            calls.append(scope["path"])
            if scope["path"] != "/v1/tools/submit_ceo_intent":
                await app(scope, receive, send)
                return
            events = []

            async def collect(event):
                events.append(event)

            await app(scope, receive, collect)
            submitted.append(json.loads(b"".join(event.get("body", b"") for event in events)))
            assert submitted[-1]["status"] == "accepted"
            raise OSError("deliberate loss after the real initial admission")

        wrapped.aclose = app.aclose
        return wrapped

    monkeypatch.setattr(app_module, "create_web_ceo_v3_app", lost_submit_app)

    async def run():
        service = fixture._real_service(
            tmp_path, socket_root=short_socket_root,
            mastermind_root=Path(settings.mastermind_root), macro_root=Path(settings.macro_root_flag),
        )
        readers = InstalledExecutiveReaders(
            repo_root=Path(settings.mastermind_root), macro_root=Path(settings.macro_root_flag),
            runtime_root=service.config.runtime_root,
        )
        service = ExecutiveControlService(
            service.config, supervisor_factory=lambda runtime: fixture._NoExecutionSupervisor(),
            ceo_ingress_socket_path=settings.ceo_ingress_socket_path,
            ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=readers, ceo_ingress_armed=False,
            ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=os.geteuid(), armed=True, grounding_provider=readers, read_provider=readers,
            ),
        )
        await service.start()
        try:
            async with connection(settings) as client:
                token = fixture._submit_token(rsa_key)
                _response, unknown = await session_fixture.call(client, token, "submit_ceo_intent", {
                    "operation_key": "v3-request-recovery-canary",
                    "objective": "Read the board packet and summarize open risks.",
                    "department": "executive-infrastructure", "priority": 5,
                    "execution_profile": "research_only",
                })
                assert unknown["status"] == "effect_unknown", unknown
                assert len(submitted) == 1
                assert submitted[0].get("status") == "accepted", submitted[0]
                assert unknown["request_ref"] == submitted[0]["request_ref"]
                message = unknown["error"]["message"]
                assert v3.RECONCILE_TOOL_NAME in message
                assert (
                    f"intent_id={ceo_request.automated_intent_id(unknown['request_ref'])}"
                    in message
                )
                original_jobs = service.runtime.jobs.list_jobs()
                assert len(original_jobs) == 1

                async def forbidden_submit(*args, **kwargs):
                    pytest.fail("status recovery must not submit again")

                monkeypatch.setattr(app_module, "compose_admission", forbidden_submit)
                _response, settled = await reconcile(client, token, {"request_ref": unknown["request_ref"]})
                assert settled["status"] == "accepted", settled
                assert settled["request_ref"] == unknown["request_ref"]
                assert settled["receipt"]["job_id"] == original_jobs[0].job_id
                assert settled["receipt"]["dispatched"] is False
                assert [j.job_id for j in service.runtime.jobs.list_jobs()] == [original_jobs[0].job_id]
                assert service.runtime.attempts.list_attempts() == []
                assert service.runtime.workers.list_workers() == []
        finally:
            await service.close()
            await readers.aclose()
    asyncio.run(run())
    assert calls == ["/v1/tools/submit_ceo_intent", PATH]
