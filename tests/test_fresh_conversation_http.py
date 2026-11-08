"""Signed dual-resource public leaf -> actual private handler/Runtime/OHF.

Fixed BFF client serialization/lifetime is actual code. The already-verified
private kernel peer and provider are named inert seams; no Unix socket, native
process, production account, installed/public-edge deployment is claimed.
The separate exact profile/mount/native route joins remain integration checks.
"""
import asyncio
import dataclasses
import json
import os
from pathlib import Path
import time

import pytest

from common import fresh_conversation_contract as wire
from common.executive_workspace_contract import PRINCIPAL_KEYS
from control_plane.principal_projection import neutral_principal_projection
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.mastermind_executive_app.gateway import CeoIngressClient, CeoIngressResponse, TRANSPORT_SENT_OK
from integrations.mastermind_executive_app.os_transport import OsExecutiveTransportApp
from integrations.mastermind_executive_app.fresh_conversation_transport import (
    FreshConversationTransportApp, InstalledFreshConversationClient,
)
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig
from tests import test_mastermind_executive_app_asgi as auth
from tests import test_workspace_read_app as workspace_auth
from tests.test_fresh_conversation import case, cleanup

rsa_key = auth.rsa_key


class Sink:
    def __init__(self): self.events = []
    def emit(self, event): self.events.append(event)


async def post(app, operation, arguments, executive_token, workspace_token=None, *, change=None, timeout_seconds=15):
    path = "/os/executive/conversation/" + operation.replace("_", "/")
    scope = dict(type="http", asgi={"version": "3.0", "spec_version": "2.4"}, http_version="1.1",
        scheme="https", method="POST", path=path, raw_path=path.encode(), root_path="", query_string=b"",
        headers=[(b"host", b"mcp.mastermind-x.com"), (b"content-type", b"application/json"),
            (b"authorization", ("Bearer " + executive_token).encode())],
        client=("127.0.0.1", 39999), server=("mcp.mastermind-x.com", 443))
    if workspace_token:
        scope["headers"].append((b"x-mastermind-workspace-authorization", ("Bearer " + workspace_token).encode()))
    if change: scope.update(change)
    frames, output = asyncio.Queue(), []
    await frames.put(dict(type="http.request", body=json.dumps({"arguments": arguments}).encode(), more_body=False))
    async def send(value): output.append(value)
    await asyncio.wait_for(app(scope, frames.get, send), timeout_seconds)
    status = next(value["status"] for value in output if value["type"] == "http.response.start")
    raw = b"".join(value.get("body", b"") for value in output if value["type"] == "http.response.body")
    return status, json.loads(raw) if raw else None


async def mounted(tmp_path, rsa_key, monkeypatch, *, case_factory=None, executive_policy=None, workspace_policy=None, claims=None):
    now = lambda: int(time.time())
    ep = auth._submit_policy() if executive_policy is None else executive_policy
    ea = JwtAuthenticator(policy=ep, jwks_cache=auth._FakeJwksCache(rsa_key))
    sink = Sink()
    ev = MastermindTokenVerifier(authenticator=ea, policy=ep, now=now, audit_sink=sink)
    token = auth._submit_token(rsa_key, **({} if claims is None else claims), iat=now()-1, nbf=now()-1, exp=now()+600)
    verified = await ea.verify_token(token, now=now())
    assert verified is not None
    principal = neutral_principal_projection(**dataclasses.asdict(verified))
    service, runtime, owner, principal, request, adapters = (case(tmp_path, principal) if case_factory is None else case_factory(principal))
    service._fixture_fresh_owner = owner
    backend = owner._app.workspace_read_provider_factory(runtime)
    wp = (workspace_auth._workspace_policy(policy_id="workspace-test",
        allowed_subject_digests=list(ep.allowed_subject_digests)) if workspace_policy is None else workspace_policy)
    wa = JwtAuthenticator(policy=wp, jwks_cache=auth._FakeJwksCache(rsa_key))
    wv = MastermindTokenVerifier(authenticator=wa, policy=wp, now=now, audit_sink=sink)
    wt_claims={} if claims is None else {key:value for key,value in claims.items() if key!="aud"}
    wt = auth._token(rsa_key, scope=workspace_auth.SCOPE, aud=workspace_auth.RESOURCE,
        **wt_claims, iat=now()-1, nbf=now()-1, exp=now()+600)
    def authorize(value):
        return backend.authorize({key: list(value.scopes) if key == "scopes" else getattr(value, key)
            for key in PRINCIPAL_KEYS})
    authorize.binding_digest = lambda value: "e" * 64 if authorize(value) else None
    class NoWorkspaceCall:
        async def request(self, frame): raise AssertionError("unexpected generic workspace call")
    wc = WorkspaceAppConfig(authenticator=wa, now=now, authorize_principal=authorize, client=NoWorkspaceCall())
    async def inner(scope, receive, send):
        from starlette.responses import Response
        await Response(status_code=404)(scope, receive, send)
    executive = OsExecutiveTransportApp(inner, submit_verifier=ev, submit_authenticator=ea, clock=now)
    client = CeoIngressClient()
    calls = []
    async def actual_private(socket_path, frame, **options):
        calls.append(frame)
        source = options.get("foreground_source")
        if frame["operation"] in wire.MODIFYING:
            assert options["keep_write_open"] is True and source is not None
            source.require_live()
        elif source is not None:
            raise AssertionError("read acquired creation attendance")
        reader = asyncio.StreamReader() if source else None
        service._fixture_active_private_reader = reader
        result = await owner.handle_frame(frame, reader=reader,
            host_current=source.require_live if source else lambda: None)
        if frame["operation"] == "consume" and getattr(service, "_fixture_lose_consume_return", False):
            raise OSError("inert original consume return lost after actual owner commit")
        return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True, result=result)
    monkeypatch.setattr(client, "_send_frame", actual_private)
    leaf = FreshConversationTransportApp(inner, executive=executive, workspace_config=wc,
        workspace_verifier=wv, client=InstalledFreshConversationClient("/private/tmp/inert-existing-app.sock", client))
    return leaf, token, wt, service, runtime, request, adapters, calls, sink


def test_signed_preview_create_original_read_duplicate_and_reopen(tmp_path, rsa_key, monkeypatch):
    async def run():
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        try:
            code, preview = await post(app, "preview", request, token, wt)
            assert code == 200 and preview["ok"] and not runtime.jobs.list_jobs(), preview
            create = {**request, "preview_digest": preview["data"]["preview"]["digest"]}
            code, first = await post(app, "create", create, token, wt)
            assert code == 200 and first["ok"] and first["data"]["state"] == "CREATED", first
            selected = {key: request[key] for key in ("work_ref", "operation_key")}
            code, result = await post(app, "read", selected, token)
            assert code == 200 and result["data"]["result"] and not result["data"]["parent_consumed"]
            before = runtime.events.list_events()
            code, duplicate = await post(app, "create", create, token, wt)
            assert code == 200 and duplicate["data"]["locator"] == first["data"]["locator"]
            assert runtime.events.list_events() == before and adapters[0].begin_turn_calls == 1
            code, reopened = await post(app, "status", selected, token)
            assert code == 200 and reopened["data"]["locator"] == first["data"]["locator"]
            assert len(runtime.jobs.list_jobs()) == 2 and len(runtime.attempts.list_attempts()) == 1
            assert sink.events and all("Bearer" not in repr(frame) for frame in calls)
            # Retain one coherent actual run for the typed consumer. Only
            # public requests/responses and finite actual Runtime counts are
            # exported; signed tokens/private peer frames never leave fixture.
            destination = os.environ.get("S34_SIGNED_FIXTURE_OUTPUT")
            if destination:
                captured = {"schema": "mastermind.s34.signed_fixture.v1",
                    "source_revision": os.environ["S34_SOURCE_REVISION"],
                    "seams": ["synthetic fixture authority/host readiness", "actual RS256 verifier",
                        "inert private kernel peer forwarding actual serialized frame",
                        "inert physical native/provider account"],
                    "request": request, "create_request": create,
                    "preview": preview, "create": first, "read": result,
                    "duplicate": duplicate, "status": reopened,
                    "actual_counts": {"jobs": len(runtime.jobs.list_jobs()),
                        "attempts": len(runtime.attempts.list_attempts()),
                        "provider_begin_turns": adapters[0].begin_turn_calls},
                    "created_job_ids": [j.job_id for j in runtime.jobs.list_jobs()],
                    "retained_creation_event_ids": [event.event_id for event in runtime.events.list_events()
                        if event.event_type == "JOB_CREATED"]}
                with Path(destination).open("x", encoding="utf-8") as stream:
                    json.dump(captured, stream, ensure_ascii=False, sort_keys=True, indent=2)
                    stream.write("\n")
        finally:
            await cleanup(service)
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["query", "raw_alias", "method", "workspace_absent", "wrong_resource", "foreign_client"])
def test_fixed_routes_and_resource_identity_refuse_before_private_read(tmp_path, rsa_key, monkeypatch, fault):
    async def run():
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        change = None
        if fault == "query": change = {"query_string": b"work_ref=WS:ONE"}
        elif fault == "raw_alias": change = {"raw_path": b"/os/executive/conversation/%70review"}
        elif fault == "method": change = {"method": "GET"}
        elif fault == "workspace_absent": wt = None
        elif fault == "wrong_resource": wt = token
        elif fault == "foreign_client": wt = auth._token(rsa_key, scope=workspace_auth.SCOPE,
            aud=workspace_auth.RESOURCE, client_id="foreign-client", iat=int(time.time())-1,
            nbf=int(time.time())-1, exp=int(time.time())+600)
        code, _ = await post(app, "preview", request, token, wt, change=change)
        assert code in {400, 401, 403, 404} and not calls and not adapters and not runtime.jobs.list_jobs()
    asyncio.run(run())
