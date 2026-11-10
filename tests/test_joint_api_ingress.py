"""One exact API enrollment across help and original requester returns.

Actual installed catalogue/target factories, signed resource authentication,
SDK ClientSession, canonical current-C Mission/adoption and Runtime owners run.
The no-socket test names its in-process private READ edge. The separate Unix
journey uses the original Control service and is qualified on the authorized
socket host. Physical provider/receiver and root-ownership seams are the
incumbent disposable fixtures; no native-origin or installed capability claim.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import jwt
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from common import coo_project_help_contract as help_wire
from common import coo_requester_return_contract as return_wire
from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.coo_principal_host import CooHostProvider, build_selected_child_publication
from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.executive_mcp import coo, server
from integrations.mastermind_executive_app.app import AppSettings
from integrations.mastermind_executive_app.coo_binding import principal_frame
from integrations.mastermind_executive_app.coo_installed import CooFactsClient
from integrations.mastermind_executive_app.gateway import APP_POLICY_ENVELOPE_SCHEMA
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import principal_frame as workspace_frame, workspace_authorizers
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from integrations.session_bridge.installed import build_runtime_session_bridge, principal_frame as session_frame
from ops.executive_os import executive_mcp_entry as entry
from ops.executive_os.coo_principal_host import CooInstalledSource, CLAUDE_PRINCIPAL_POLICY
from tests import test_executive_coo_app as app_tests
from tests import test_executive_coo_install_binding as install_tests
from tests.test_coo_project_help_authority import _frame, full_joined, owner, env, isolated_git_env, identity
from tests.test_hermes_selected_child_dispatch import _settle
from tests.test_hermes_selected_child_ingress import _SealingSupervisor
from tests.test_hermes_selected_child_target import unsealed, _unsealed_installation
from tests.test_joint_api_project_owner import current_joint_project
from tests.test_executive_service import _capture_projection

rsa_key = app_tests.rsa_key


@pytest.fixture
def joint_signed(current_joint_project, unsealed, rsa_key, tmp_path):
    f = current_joint_project
    frame = _frame(f)
    captured = f.provider.capture_selected_child_target(principal=frame["principal"],
        context=PrincipalAdmissionContext(**frame["principal_context"]), work_ref=f.work,
        root_job_id=f.root, child_job_ids=[f.work_child.job_id])
    publication = build_selected_child_publication(work_ref=f.work, root_job_id=f.root,
        children=captured["children"], source=captured["source"])
    document = install_tests.base_document()
    document.update(executive_mcp_profile="web_ceo_v3", release_sha=f.service_config.proof_base_sha,
        coo=copy.deepcopy(f.coo), selected_child_target=publication,
        policies={"schema": APP_POLICY_ENVELOPE_SCHEMA,
            "read": dataclasses.asdict(f.j["factory"].policies.read),
            "submit": dataclasses.asdict(f.j["factory"].policies.submit)})
    document = json.loads(json.dumps(document))
    source, config = _unsealed_installation(document, unsealed)
    policy_path = source / CLAUDE_PRINCIPAL_POLICY
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_bytes(f.policy_path.read_bytes())
    installed = CooInstalledSource.from_path(config, source, expected_uid=os.geteuid())
    f.provider = CooHostProvider(installed, f.workspace)
    f.frame = _frame(f)
    target = installed.selected_child_target()
    assert target is not None and target.material_digest() == publication["material_digest"]
    clock = [f.j["workspace"].issued_at + 5]
    cache = app_tests.fixture._FakeJwksCache(rsa_key)
    policy = dataclasses.replace(f.j["factory"].policies.read,
        policy_id="project-help-coo", required_scopes=tuple(f.principal.scopes))

    def bearer(selected, *, client="inert-client"):
        return jwt.encode(dict(iss=selected.issuer, sub="inert-chairman", aud=selected.resource,
            client_id=client, scope=" ".join(selected.required_scopes),
            iat=f.j["workspace"].issued_at, nbf=f.j["workspace"].issued_at,
            exp=f.j["workspace"].expires_at), rsa_key, algorithm="RS256",
            headers={"kid": app_tests.fixture.KID, "typ": "at+jwt"})

    token, second = bearer(policy), bearer(f.j["factory"].workspace_policy)
    principal = asyncio.run(JwtAuthenticator(policy=policy, jwks_cache=cache).verify_token(token, now=clock[0]))
    wauth = JwtAuthenticator(policy=f.j["factory"].workspace_policy, jwks_cache=cache)
    workspace = asyncio.run(wauth.verify_token(second, now=clock[0]))
    assert principal_frame(principal) == principal_frame(f.principal)
    assert workspace_frame(workspace) == workspace_frame(f.j["workspace"])
    authorize, _ = workspace_authorizers(policy=f.j["factory"].workspace_policy,
        load_bindings=lambda: legacy_workspace_document(f.j["document"], f.j["factory"].workspace_policy))
    sink = app_tests.Sink()
    workspace_config = WorkspaceAppConfig(authenticator=wauth, now=lambda: clock[0],
        authorize_principal=authorize, client=CeoIngressWorkspaceClient(tmp_path / "unopened-workspace.sock"))
    verifier = MastermindTokenVerifier(authenticator=wauth, policy=f.j["factory"].workspace_policy,
        now=workspace_config.now, audit_sink=sink)
    workspace_app = server.AuditedWorkspaceApp(create_workspace_app(workspace_config), verifier,
        authenticator=wauth, authorize_principal=authorize, fresh_workspace_config=workspace_config)
    base = AppSettings(policies=f.j["factory"].policies, mastermind_root=source,
        macro_root_flag=None, environ={}, ceo_ingress_socket_path=tmp_path / "unopened-control.sock",
        read_from_ceo_ingress=True, jwks_cache=cache, clock=lambda: clock[0])
    installed_settings = entry.build_installed_coo_settings(document, source, config, base,
        expected_uid=os.geteuid())
    # The incumbent factory's binding loader retains the production 458
    # identity even when its target/catalogue use the fixture's expected_uid.
    # Supply that same explicit fixture identity to the unchanged canonical
    # loader; do not patch os.geteuid or weaken any content/generation check.
    installed_settings = dataclasses.replace(installed_settings,
        load_binding=entry.current_projection_loader(config, source, document,
            "coo", "binding", expected_uid=os.geteuid()))
    assert type(installed_settings.project_help_provider.__self__) is CooFactsClient
    assert installed_settings.catalogue_provider(principal, f.work) == help_wire.API_REQUESTER_CATALOGUE
    assert installed_settings.selected_child_target.material_digest() == target.material_digest()
    bridge = build_runtime_session_bridge(f.j["runtime"], dialogue_socket_path=tmp_path / "unused-dialogue.sock")
    reads = []

    async def project_help(who, workspace_who, context, digest):
        frame = {"schema": help_wire.FRAME_SCHEMA, "principal": principal_frame(who),
            "session_principal": session_frame(who), "workspace_principal": workspace_frame(workspace_who),
            "principal_context": dataclasses.asdict(context), "capability_profile_digest": digest}
        result = await f.provider.read_project_help(frame, session_bridge_owner=bridge)
        reads.append(copy.deepcopy(frame))
        return result

    settings = dataclasses.replace(installed_settings,
        authority_provider=lambda who, work: f.provider.source.for_principal(principal_frame(who), work)[2],
        mission_provider=lambda who, work: f.workspace.read_mission_for_work_ref(work),
        project_help_provider=project_help)
    return SimpleNamespace(f=f, settings=settings, installed_settings=installed_settings,
        workspace_app=workspace_app, token=token, second=second, principal=principal,
        sink=sink, reads=reads, target=target, document=document, source=source, config=config,
        bearer=bearer, clock=clock, bridge=bridge)


@asynccontextmanager
async def session(s, *, companion=False, token=None):
    app = server._build_coo_mcp_app(s.settings, audit_sink=s.sink, workspace_app=s.workspace_app)
    headers = {"authorization": "Bearer " + (token or s.token)}
    if companion:
        headers["x-mastermind-workspace-authorization"] = "Bearer " + s.second
    async with app._app.router.lifespan_context(app._app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1", headers=headers) as http_client:
            async with streamable_http_client("http://127.0.0.1/mcp/coo", http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    yield client, http_client


def payload(result):
    blocks = [item.text for item in result.content if item.type == "text"]
    assert len(blocks) == 1
    return json.loads(blocks[0])


def assert_original_auth_401(error):
    """Exact original MCP transport refusal, including nested SDK groups."""
    leaves = []
    def collect(value):
        if isinstance(value, BaseExceptionGroup):
            for child in value.exceptions:
                collect(child)
        else:
            leaves.append(value)
    collect(error)
    assert len(leaves) == 1, leaves
    refused = leaves[0]
    assert isinstance(refused, httpx.HTTPStatusError), type(refused)
    assert refused.response.status_code == 401
    assert refused.request.method == "POST"
    assert str(refused.request.url) == "http://127.0.0.1/mcp/coo"


def receipts(runtime):
    with runtime.store.read() as connection:
        return list(connection.execute("SELECT * FROM events WHERE event_type=?", (return_wire.CONSUMPTION_EVENT,)))


async def delegate(client, arguments):
    result = await client.call_tool("mmx_delegate", arguments)
    body = payload(result)
    assert result.isError is False, body
    assert body["schema"] == "mastermind.hermes_delegate.selected_child/v1", body
    return body


@pytest.mark.parametrize("current_joint_project", ["t3", "paperclip"], indirect=True)
def test_same_signed_api_principal_discovers_joint_tools_and_qualifies_help(joint_signed):
    s = joint_signed
    before = [event.to_dict() for event in s.f.j["runtime"].events.list_events()]

    async def run():
        async with session(s) as (client, http_client):
            listed = await client.list_tools()
            observed = {"tools": {tool.name: {"name": tool.name, "inputSchema": tool.inputSchema,
                "annotations": tool.annotations.model_dump(exclude_none=True) if tool.annotations else {}}
                for tool in listed.tools}}
            assert observed_mcp_tool_schema_digest(observed) == coo.coo_project_help_requester_tool_schema_digest()
            missing = await client.call_tool(help_wire.TOOL, {"work_ref": s.f.work})
            assert missing.isError is True and s.reads == []
            assert s.settings.catalogue_provider(s.principal, s.f.work) == help_wire.API_REQUESTER_CATALOGUE
            http_client.headers["x-mastermind-workspace-authorization"] = "Bearer " + s.second
            result = await client.call_tool(help_wire.TOOL, {"work_ref": s.f.work})
            body = payload(result)
            assert result.isError is False, body
            data = body["data"]
            assert data["scope"] == s.f.scope
            assert data["observation"]["mission"]["qualification"] == "CURRENT_MISSION"
            assert data["native_origin_attested"] is False and data["execution_authority"] is False
            assert s.token not in repr(body) and s.second not in repr(body)
            return data

    data = asyncio.run(run())
    assert len(s.reads) == 2 and s.target.children[0].selection.root_job_id == data["scope"]["root_job_id"]
    assert [event.to_dict() for event in s.f.j["runtime"].events.list_events()] == before


@asynccontextmanager
async def unix_control(s, tmp_path):
    """Original service, kernel peer and namespace custody; no private hop mock."""
    f, runtime = s.f, s.f.j["runtime"]
    with tempfile.TemporaryDirectory(prefix="mmx-joint-api-", dir="/tmp") as directory:
        sockets = Path(directory)
        finish_gate = asyncio.Event()
        config = dataclasses.replace(f.service_config, socket_path=sockets / "control.sock",
            runtime_root=runtime.store.root, coo_tick_interval_seconds=3600.0)
        binding = CeoIngressAppBinding(peer_uid=os.geteuid(), armed=True,
            grounding_provider=SimpleNamespace(observe=lambda: {}), principal_admission_armed=True,
            principal_admission_guard=f.service._autonomy_guard,
            principal_facts_factory=lambda actual: f.provider if actual is runtime else None,
            session_bridge_provider_factory=lambda actual: s.bridge if actual is runtime else None,
            selected_child_target=s.target)
        service = ExecutiveControlService(config, runtime_factory=lambda root: runtime,
            supervisor_factory=lambda actual: _SealingSupervisor(actual, finish_gate=finish_gate),
            autonomy_guard=f.service._autonomy_guard,
            terminal_return_projector=lambda candidate: _capture_projection([], candidate),
            ceo_ingress_socket_path=sockets / "coo.sock", ceo_ingress_peer_uid=os.geteuid() + 1,
            ceo_ingress_grounding_provider=binding.grounding_provider, ceo_ingress_app_binding=binding)
        await service.start()
        previous = f.workspace._bounded_runtime
        try:
            assert service.runtime is runtime and service._service_state == "READY"
            f.workspace._bounded_runtime = service._namespace_custody.bound_runtime
            client = CooFactsClient(sockets / "coo.sock")
            s.settings = dataclasses.replace(s.installed_settings,
                executive=dataclasses.replace(s.installed_settings.executive,
                    ceo_ingress_socket_path=sockets / "coo.sock"),
                authority_provider=client.authority, mission_provider=client.mission,
                project_help_context_provider=client.project_help_context,
                project_help_provider=client.project_help)
            yield SimpleNamespace(service=service, finish_gate=finish_gate)
        finally:
            f.workspace._bounded_runtime = previous
            finish_gate.set()
            await service.close()


@pytest.mark.parametrize("current_joint_project,boundary", [
    ("t3", "normal"), ("paperclip", "normal"), ("t3", "changed_digest"),
    ("t3", "revoked"), ("t3", "foreign_root"), ("t3", "source_generation"),
    ("paperclip", "foreign_principal"), ("paperclip", "lost_response"), ("t3", "concurrent_ack"),
], indirect=["current_joint_project"])
def test_joint_same_enrollment_help_then_original_unix_requester_lifecycle(
        joint_signed, tmp_path, monkeypatch, boundary):
    s, f = joint_signed, joint_signed.f
    original_refusal = []

    def record_immutable_installation_change():
        original_refusal.append([event.to_dict() for event in f.j["runtime"].events.list_events()])

    async def run():
        async with unix_control(s, tmp_path) as host:
            async with session(s, companion=True) as (client, http_client):
                help_result = await client.call_tool(help_wire.TOOL, {"work_ref": f.work})
                assert help_result.isError is False, payload(help_result)
                assert payload(help_result)["data"]["scope"]["root_job_id"] == f.root
                del http_client.headers["x-mastermind-workspace-authorization"]
                missing = await client.call_tool(help_wire.TOOL, {"work_ref": f.work})
                assert missing.isError is True
                command = s.target.children[0].command_id
                if boundary in {"foreign_root", "source_generation"}:
                    row = s.document["coo"]["missions"][0]
                    if boundary == "foreign_root":
                        row["project_help"]["root_job_id"] = next(job.job_id for job in
                            f.j["runtime"].jobs.list_jobs() if job.depth == 0 and job.job_id != f.root)
                    else:
                        row["project_help"]["source_plan"]["source"]["commit"] = "f" * 40
                    s.config.write_text(json.dumps(s.document, sort_keys=True) + "\n")
                    # The installed projection loader forbids changing this
                    # immutable source/root scope. Its original BoundVerifier
                    # rejects before the selected-child handler is reached.
                    record_immutable_installation_change()
                    await delegate(client, {"action": "selected_child_submit", "command": command})
                    raise AssertionError("changed installed scope must receive the original HTTP 401")
                submitted = await delegate(client, {"action": "selected_child_submit", "command": command})
                assert submitted["state"] in {"ACTIVE", "COMPLETED"}, submitted
                event = f.j["runtime"].store.get_event_by_command_id(command)
                claim = return_wire.validate_claim(event.payload["selected_child_requester"])
                assert claim["family"] == "coo_api_principal"
                assert claim["selection"]["root_job_id"] == f.root
                assert claim["capability_profile_digest"] == f.profile.profile_digest
                host.finish_gate.set()
                await _settle(host.service)
                observed = await delegate(client, {"action": "selected_child_status", "command": command})
                assert observed["state"] == "COMPLETED", observed
                descriptor = return_wire.validate_descriptor(observed["requester_return"], observation=observed)
                assert descriptor["consumption"] is None and receipts(f.j["runtime"]) == []
                assert descriptor["root_job_id"] == f.root and descriptor["job_id"] == f.work_child.job_id
                request = {"action": return_wire.ACK_ACTION, "command": command, "result": descriptor}
                if boundary == "changed_digest":
                    wrong = copy.deepcopy(request)
                    wrong["result"]["result_envelope_digest"] = "f" * 64
                    refused = await delegate(client, wrong)
                    assert refused["state"] == "REFUSED" and receipts(f.j["runtime"]) == []
                elif boundary == "revoked":
                    s.document["coo"]["missions"][0]["principal_actions"].remove(return_wire.ACTION)
                    s.config.write_text(json.dumps(s.document, sort_keys=True) + "\n")
                    record_immutable_installation_change()
                    await delegate(client, request)
                    raise AssertionError("revoked installed action must receive the original HTTP 401")
                elif boundary == "foreign_principal":
                    before_foreign = [event.to_dict() for event in f.j["runtime"].events.list_events()]
                    with pytest.raises(BaseExceptionGroup) as refused:
                        async with session(s, token=s.bearer(s.settings.policy, client="foreign-client")) as (other, _):
                            await delegate(other, request)
                    assert_original_auth_401(refused.value)
                    assert receipts(f.j["runtime"]) == []
                    assert [event.to_dict() for event in f.j["runtime"].events.list_events()] == before_foreign
                elif boundary == "lost_response":
                    original = host.service.acknowledge_selected_child_result
                    async def lose(*args, **options):
                        await original(*args, **options)
                        raise OSError("original acknowledgment response lost after commit")
                    monkeypatch.setattr(host.service, "acknowledge_selected_child_result", lose)
                replies = (await asyncio.gather(delegate(client, request), delegate(client, request))
                    if boundary == "concurrent_ack" else [await delegate(client, request)])
                for reply in replies:
                    assert reply["state"] == ("EFFECT_UNKNOWN" if boundary == "lost_response" else "COMPLETED"), reply
                assert len(receipts(f.j["runtime"])) == 1
                final = await delegate(client, {"action": "selected_child_status", "command": command})
                assert final["state"] == "COMPLETED"
                assert final["requester_return"]["consumption"] is not None
                assert f.j["runtime"].jobs.get_job(f.work_child.job_id).attempt_count == 1
                assert "x-mastermind-workspace-authorization" not in http_client.headers

    if boundary in {"revoked", "foreign_root", "source_generation"}:
        with pytest.raises(BaseExceptionGroup) as refused:
            asyncio.run(run())
        assert_original_auth_401(refused.value)
        assert len(original_refusal) == 1
        assert [event.to_dict() for event in f.j["runtime"].events.list_events()] == original_refusal[0]
        assert receipts(f.j["runtime"]) == []
        expected_attempts = 1 if boundary == "revoked" else 0
        assert f.j["runtime"].jobs.get_job(f.work_child.job_id).attempt_count == expected_attempts
    else:
        asyncio.run(run())
