"""T3 handoff selector -> actual signed COO MCP read -> current original owners.

The source grant is the distinct, disabled-by-default T3 API-principal profile,
explicitly enabled only in this disposable fixture. This proves that declared
API source/profile path, not a production enrollment or native-origin
attestation. MCP ClientSession, both JWT verifiers, CooApp and the actual
Workspace/Mission/adopted-plan owners execute. The private App-to-Control join
is an explicit same-process callback. No native agent, model, socket service,
profile installation or production connection is launched.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import dataclasses
import json
import threading
from types import SimpleNamespace

import httpx
import jwt
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from common import coo_project_help_contract as wire
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry, HERMES_NATIVE_PROJECT_HELP_PROFILE_ID,
    T3_API_PROJECT_HELP_PROFILE_ID, T3_API_PRINCIPAL_EXECUTION_SURFACE,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.executive_mcp import server
from integrations.mastermind_executive_app.app import AppSettings
from integrations.mastermind_executive_app.coo import CooAppSettings
from integrations.mastermind_executive_app.coo_binding import COO_SCOPES, principal_frame
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import (
    principal_frame as workspace_frame, workspace_authorizers,
)
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from integrations.session_bridge.installed import (
    build_runtime_session_bridge, principal_frame as session_frame,
)
from integrations.session_bridge.project_task_context import load_context
from integrations.session_bridge.t3_project_team_cli import launch_request
from tests import test_executive_coo_app as app_tests
from tests.test_coo_project_help_authority import (
    qualified_help, full_joined, owner, env, isolated_git_env, identity, ROOT, _frame,
)
from tests.test_t3_project_team import team_fixture

rsa_key = app_tests.rsa_key


def _source_handoff(f, *, foreign_commit=False):
    source = f.source_plan["source"]
    context = load_context(workspace_root=f.j["integrator"], relative_path=source["path"],
                           workstream=f.work, expected_sha256=source["content_sha256"])
    commit = "f" * 40 if foreign_commit else source["commit"]
    source_ref = f"https://github.com/{source['repository']}/blob/{commit}/{source['path']}"
    # This team is a task description only. Its requested paths are not a
    # permission, and the emitted native launch is never executed in this test.
    team = team_fixture()
    team = dataclasses.replace(team, mission=dataclasses.replace(team.mission, source_ref=source_ref))
    prepared = launch_request(team, project_id="fixture-native-project",
        environment_id="fixture-native-environment", request_id="project-help-read",
        project_context=context, project_source_ref=source_ref)
    document = json.JSONDecoder().raw_decode(prepared["arguments"]["message"].split("\n", 1)[1])[0]
    guidance = json.loads(document["objective"].rsplit("\n", 1)[1])["project_help"]
    assert prepared["effect_state"] == "NOT_DISPATCHED"
    assert guidance["read_state"] == "NOT_READ" and guidance["execution_authority"] is False
    assert guidance["native_origin_attested"] is False and "root_job_id" not in guidance
    return context, source_ref, guidance


@pytest.fixture
def signed_help(qualified_help, rsa_key, tmp_path):
    """Extend the incumbent signed-resource/App factory with the actual v6 owner."""
    f = qualified_help
    # Select the actual new source profile through its existing registry and
    # mission row. Never relabel the fixture's original Hermes enrollment.
    raw = json.loads(f.policy_path.read_bytes())
    assert raw["profiles"][T3_API_PROJECT_HELP_PROFILE_ID]["enabled"] is False
    raw["profiles"][T3_API_PROJECT_HELP_PROFILE_ID]["enabled"] = True
    raw["profiles"][HERMES_NATIVE_PROJECT_HELP_PROFILE_ID]["enabled"] = False
    f.policy_path.write_text(json.dumps(raw))
    registry = ExecutionCapabilityRegistry.load(f.policy_path, source_root=ROOT)
    profile = registry.profiles[T3_API_PROJECT_HELP_PROFILE_ID]
    assert profile.execution_surface == T3_API_PRINCIPAL_EXECUTION_SURFACE
    f.coo["missions"][0].update(capability_profile_id=profile.profile_id,
        capability_profile_digest=profile.profile_digest)
    f.frame = _frame(f)
    assert f.provider.source.catalogue_for_principal(principal_frame(f.principal), work_ref=f.work) == wire.CATALOGUE
    factory = f.j["factory"]
    clock = [f.j["workspace"].issued_at + 5]
    policy = dataclasses.replace(factory.policies.read,
        policy_id="project-help-coo", required_scopes=COO_SCOPES)
    assert json.loads(json.dumps(dataclasses.asdict(policy))) == f.coo["policy"]
    cache = app_tests.fixture._FakeJwksCache(rsa_key)

    def bearer(selected):
        return jwt.encode(dict(iss=selected.issuer, sub="inert-chairman", aud=selected.resource,
            client_id="inert-client", scope=" ".join(selected.required_scopes),
            iat=f.j["workspace"].issued_at, nbf=f.j["workspace"].issued_at,
            exp=f.j["workspace"].expires_at), rsa_key, algorithm="RS256",
            headers={"kid": app_tests.fixture.KID, "typ": "at+jwt"})

    token, second = bearer(policy), bearer(factory.workspace_policy)
    principal = asyncio.run(JwtAuthenticator(policy=policy, jwks_cache=cache).verify_token(token, now=clock[0]))
    wauth = JwtAuthenticator(policy=factory.workspace_policy, jwks_cache=cache)
    workspace = asyncio.run(wauth.verify_token(second, now=clock[0]))
    # No fabricated VerifiedPrincipal and no relabeling of another enrollment.
    assert principal_frame(principal) == principal_frame(f.principal)
    assert workspace_frame(workspace) == workspace_frame(f.j["workspace"])
    authorize, _ = workspace_authorizers(policy=factory.workspace_policy,
        load_bindings=lambda: legacy_workspace_document(f.j["document"], factory.workspace_policy))
    sink = app_tests.Sink()
    config = WorkspaceAppConfig(authenticator=wauth, now=lambda: clock[0], authorize_principal=authorize,
        client=CeoIngressWorkspaceClient(tmp_path / "never-opened-workspace.sock"))
    verifier = MastermindTokenVerifier(authenticator=wauth, policy=factory.workspace_policy,
        now=config.now, audit_sink=sink)
    workspace_app = server.AuditedWorkspaceApp(create_workspace_app(config), verifier,
        authenticator=wauth, authorize_principal=authorize, fresh_workspace_config=config)
    base = AppSettings(policies=factory.policies, mastermind_root=f.j["source_root"],
        macro_root_flag=None, environ={}, ceo_ingress_socket_path=tmp_path / "never-opened-control.sock",
        read_from_ceo_ingress=True, jwks_cache=cache, clock=lambda: clock[0])
    bridge = build_runtime_session_bridge(f.j["runtime"], dialogue_socket_path=tmp_path / "never-opened-dialogue.sock")
    reads, attempts, failures, after = [], [], [], [lambda: None]

    def authority(who, work_ref):
        return f.provider.source.for_principal(principal_frame(who), work_ref)[2]

    async def project_help(who, workspace_who, context, digest):
        frame = {"schema": wire.FRAME_SCHEMA, "principal": principal_frame(who),
            "session_principal": session_frame(who), "workspace_principal": workspace_frame(workspace_who),
            "principal_context": dataclasses.asdict(context), "capability_profile_digest": digest}
        attempts.append(frame)
        try:
            value = await f.provider.read_project_help(frame, session_bridge_owner=bridge)
        except Exception as error:
            import traceback
            failures.append((type(error).__name__, [(entry.name, entry.lineno)
                for entry in traceback.extract_tb(error.__traceback__)]))
            raise
        reads.append(frame)
        after[0]()
        return value

    settings = CooAppSettings(executive=base, policy=policy, load_binding=lambda: f.coo["binding"],
        authority_provider=authority, mission_provider=lambda *_: pytest.fail("unrelated mission read"),
        catalogue_provider=lambda who, work_ref=None: f.provider.source.catalogue_for_principal(
            principal_frame(who), work_ref=work_ref), project_help_provider=project_help)
    return SimpleNamespace(f=f, settings=settings, workspace_app=workspace_app, token=token,
        second=second, sink=sink, clock=clock, reads=reads, attempts=attempts,
        failures=failures, after=after, principal=principal)


@asynccontextmanager
async def _session(s, *, legacy=False):
    settings = s.settings
    if legacy:
        settings = dataclasses.replace(settings, catalogue_provider=None, project_help_provider=None)
    # This is the exact private factory mounted by the existing production
    # Executive HTTP owner, not a test server implementation or new client.
    app = server._build_coo_mcp_app(settings, audit_sink=s.sink, workspace_app=s.workspace_app)
    headers = {"authorization": "Bearer " + s.token,
               "x-mastermind-workspace-authorization": "Bearer " + s.second}
    async with app._app.router.lifespan_context(app._app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1", headers=headers) as http_client:
            async with streamable_http_client("http://127.0.0.1/mcp/coo", http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as client:
                    initialized = await client.initialize()
                    assert initialized.serverInfo.name == "mastermind-executive-coo"
                    yield client, http_client


def _payload(result):
    texts = [block.text for block in result.content if block.type == "text"]
    assert len(texts) == 1
    return json.loads(texts[0])


def _events(f):
    return [event.to_dict() for event in f.j["runtime"].events.list_events()]


def test_prepared_t3_guidance_reaches_real_authenticated_current_help(signed_help):
    s = signed_help
    context, source_ref, guidance = _source_handoff(s.f)
    before = _events(s.f)

    async def exercise():
        async with _session(s) as (client, _):
            listed = await client.list_tools()
            tool = next(tool for tool in listed.tools if tool.name == guidance["tool"])
            assert tool.annotations.readOnlyHint is True
            return await client.call_tool(guidance["tool"], guidance["arguments"])

    result = asyncio.run(exercise())
    payload = _payload(result)
    if result.isError:
        pytest.fail(json.dumps({"error": payload.get("error"), "attempts": len(s.attempts),
            "reads": len(s.reads), "failures": [(kind, stack[-5:]) for kind, stack in s.failures]}))
    data = payload["data"]
    assert data["scope"]["root_job_id"] == s.f.root
    assert data["scope"]["source_plan"] == guidance["source_plan"]
    assert wire.context_matches_source_plan(context, data["scope"]["source_plan"], source_ref=source_ref)
    assert data["native_origin_attested"] is False and data["execution_authority"] is False
    assert data["targets"]["state"] == "AVAILABLE" and data["targets"]["items"] == []
    assert data["relationships"]["state"] == data["execution_routes"]["state"] == "UNAVAILABLE"
    mission = data["observation"]["mission"]
    assert {key: mission[key] for key in ("qualification", "mission_read_state", "execution_authorized", "transport")} == {
        "qualification": "CURRENT_DATA_CARD_WITH_UNOBSERVED_DISPATCH",
        "mission_read_state": "PARTIAL", "execution_authorized": False,
        "transport": {"dispatch_state": "UNKNOWN", "reason": "dispatch_evidence_not_supplied",
                      "actionable": False, "historical": True}}
    assert len(mission["root_origin_sha256"]) == 64
    assert type(mission["diagnostics"]) is list
    assert s.token not in repr(result) and s.second not in repr(result)
    assert len(s.reads) == 2 and _events(s.f) == before
    assert s.token not in repr(s.sink.events) and s.second not in repr(s.sink.events)


@pytest.mark.parametrize("fault", ["foreign_work", "caller_root", "missing_workspace", "unenrolled", "revoked_after_read"])
def test_current_api_never_releases_help_under_foreign_or_missing_authority(signed_help, fault):
    s = signed_help
    _, _, guidance = _source_handoff(s.f)
    before = _events(s.f)

    async def exercise():
        async with _session(s) as (client, http_client):
            listed = await client.list_tools()
            assert guidance["tool"] in {tool.name for tool in listed.tools}
            arguments = dict(guidance["arguments"])
            if fault == "foreign_work": arguments["work_ref"] = "WS:FOREIGN-HELP"
            elif fault == "caller_root": arguments["root_job_id"] = s.f.root
            elif fault == "missing_workspace": del http_client.headers["x-mastermind-workspace-authorization"]
            elif fault == "unenrolled": s.f.coo["missions"][0]["enabled"] = False
            elif fault == "revoked_after_read":
                s.after[0] = lambda: s.f.coo["missions"][0].update(enabled=False)
            result = await client.call_tool(guidance["tool"], arguments)
            assert result.isError is True, result
            payload = _payload(result)
            assert payload.get("data") is None and "scope" not in payload

    asyncio.run(exercise())
    assert len(s.reads) == (1 if fault == "revoked_after_read" else 0)
    assert _events(s.f) == before


def test_foreign_source_expectation_cannot_relabel_actual_help(signed_help):
    s = signed_help
    context, foreign_ref, guidance = _source_handoff(s.f, foreign_commit=True)

    async def exercise():
        async with _session(s) as (client, _):
            result = await client.call_tool(guidance["tool"], guidance["arguments"])
            assert result.isError is False
            data = _payload(result)["data"]
            # The caller could not select its foreign commit through the API.
            # The handoff's documented shared source comparison rejects the
            # returned current source as satisfying that foreign expectation.
            assert data["scope"]["source_plan"] == s.f.source_plan != guidance["source_plan"]
            with pytest.raises(ValueError, match="PROJECT_HELP_UNAVAILABLE"):
                wire.context_matches_source_plan(context, data["scope"]["source_plan"], source_ref=foreign_ref)

    asyncio.run(exercise())
    assert len(s.reads) == 2


def test_stale_local_plan_stops_before_tool_read(signed_help):
    s = signed_help
    source = s.f.source_plan["source"]
    path = s.f.j["integrator"] / source["path"]
    path.write_bytes(path.read_bytes() + b"\nUnadopted local change.\n")
    with pytest.raises(ValueError, match="PLAN_REVISION_CHANGED"):
        _source_handoff(s.f)
    assert s.reads == []


def test_legacy_handoff_and_catalogue_do_not_silently_enable_help(signed_help):
    s = signed_help
    brief = team_fixture().root_handoff(request_id="legacy", project_id="fixture-native-project")
    assert "project_help" not in brief.objective

    async def exercise():
        async with _session(s, legacy=True) as (client, _):
            listed = await client.list_tools()
            assert wire.TOOL not in {tool.name for tool in listed.tools}
            result = await client.call_tool(wire.TOOL, {"work_ref": s.f.work})
            assert result.isError is True and _payload(result).get("data") is None

    asyncio.run(exercise())
    assert s.reads == []


def test_owned_capture_keeps_loop_live_and_cancellation_joins_original_read(signed_help, monkeypatch, tmp_path):
    from control_plane import coo_project_help_read as read_owner
    from common.session_bridge_private_contract import SessionBridgeIngressOwner

    s = signed_help
    bridge = build_runtime_session_bridge(s.f.j["runtime"], dialogue_socket_path=tmp_path / "never-opened-cancel.sock")
    actual_capture = read_owner.capture_project_help_authority
    actual_targets = SessionBridgeIngressOwner.handle_frame
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    captures, targets = [], []

    def held_capture(*args, **kwargs):
        captures.append(threading.get_ident())
        entered.set()
        try:
            assert release.wait(3), "The service loop did not release its original bounded read"
            return actual_capture(*args, **kwargs)
        finally:
            finished.set()

    async def counted_targets(owner, frame):
        targets.append(frame["tool"])
        return await actual_targets(owner, frame)

    monkeypatch.setattr(read_owner, "capture_project_help_authority", held_capture)
    monkeypatch.setattr(SessionBridgeIngressOwner, "handle_frame", counted_targets)

    async def exercise():
        loop_thread = threading.get_ident()
        task = asyncio.create_task(s.f.provider.read_project_help(s.f.frame, session_bridge_owner=bridge))
        try:
            async def wait_for_capture():
                while not entered.is_set():
                    await asyncio.sleep(0)
            await asyncio.wait_for(wait_for_capture(), timeout=2)
            marker = asyncio.Event()
            asyncio.get_running_loop().call_soon(marker.set)
            await asyncio.wait_for(marker.wait(), timeout=1)
            assert len(captures) == 1 and captures[0] != loop_thread
            assert not finished.is_set() and not task.done()
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done(), "Cancellation escaped before the original capture was joined"
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert finished.is_set()
        finally:
            release.set()
            if not task.done():
                task.cancel()
            try:
                await task
            except BaseException:
                pass

    asyncio.run(exercise())
    assert len(captures) == 1 and targets == []
