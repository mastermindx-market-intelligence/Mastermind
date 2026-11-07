"""Fixed signed HTTP→Unix socket→Workspace→sealed Git owner; inert sources only."""
import asyncio
import copy

import httpx
import pytest

from common import workspace_project_direction_contract as wire
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app, _project_direction_envelope_response
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA, principal_frame, workspace_authorizers
from integrations.executive_mcp.installed import InstalledBootPacketCollector
from integrations.executive_mcp.server import AuditedWorkspaceApp, build_executive_mcp_app, _mounted_lifespan
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.mastermind_executive_app.app import AppSettings
from integrations.mastermind_executive_app.gateway import AppPolicies
from tests.test_installed_project_direction_context import bound
from tests.test_workspace_read_service import cache_fixture
from tests.test_workspace_project_direction_read import request
from tests.test_agentos_project_direction_source import direction_git, read, WORK
from tests.test_workspace_read_app import rsa_key, _authenticator, _workspace_token, NOW, _make_app, _FakeWorkspaceClient
from tests.test_workspace_result_socket import control, short_socket_root
from tests.test_mastermind_executive_app_asgi import _read_policy, _submit_policy, _FakeJwksCache

ROUTE = "/workspace/project-direction/current"


@pytest.mark.parametrize("case", ["available", "revoke_source", "revoke_socket", "catalogue_sha"])
def test_actual_signed_mounted_route_joins_sealed_owner_without_runtime_reads(tmp_path, monkeypatch, rsa_key, short_socket_root, case):
    async def run():
        auth = _authenticator(rsa_key); token = _workspace_token(rsa_key)
        principal = await auth.verify_authorization_header("Bearer " + token, now=NOW)
        slots = {"schema": BINDINGS_SCHEMA, "profiles": {
            "web": {"enabled": True, "binding": dict(principal_frame(principal), permission_digest="a" * 64)},
            "mac": {"enabled": False, "binding": None}}}
        app_auth, control_auth = workspace_authorizers(policy=auth.policy, load_bindings=lambda: slots)
        def revoke(): slots["profiles"]["web"]["enabled"] = False
        (tmp_path / "source").mkdir()
        (tmp_path / "catalogue").mkdir()
        collector, seen = bound(tmp_path / "source", monkeypatch)
        original = InstalledBootPacketCollector.read_project_direction
        if case == "revoke_source":
            def acquire(owner, **kwargs):
                value = original(owner, **kwargs); revoke(); return value
            monkeypatch.setattr(InstalledBootPacketCollector, "read_project_direction", acquire)
        reader = collector.project_direction_reader(macro_root=seen["macro"])
        owners, clock, cache = cache_fixture(tmp_path / "catalogue")
        doc = owners[0].state_cache["doc"]
        doc["sources"] = {"macro_sha": "f" * 40 if case == "catalogue_sha" else seen["sha"]}
        doc["work"][0]["work_ref"] = WORK
        doc["autonomy"]["responsibilities"][0]["responsibility_ref"] = WORK
        from scripts import chairman_control_room as ccr
        with owners[0].state_lock:
            ccr._publish_source_validity(owners[0], doc, tuple(clock), tuple(clock))
        class NoRuntime:
            def __getattr__(self, name): pytest.fail("Direction read acquired Runtime")
        provider = WorkspaceReadService(cache=cache, runtime=NoRuntime(), authorize=control_auth,
            armed={}, runtime_identity={}, project_direction_reader=reader)
        svc = control(tmp_path / "service", short_socket_root, lambda _: provider)
        await svc.start()
        peer = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
        class Client:
            async def request(self, value):
                result = await peer.request(value)
                if case == "revoke_socket": revoke()
                return result
        app = create_workspace_app(WorkspaceAppConfig(authenticator=auth, now=lambda: NOW,
            authorize_principal=app_auth, client=Client()))
        class Sink:
            def emit(self, _): pass
        sink = Sink()
        verifier = MastermindTokenVerifier(authenticator=auth, policy=auth.policy, now=lambda: NOW, audit_sink=sink)
        mounted = build_executive_mcp_app(AppSettings(policies=AppPolicies(read=_read_policy(), submit=_submit_policy()),
            mastermind_root=tmp_path, macro_root_flag=None, environ={}, ceo_ingress_socket_path=svc.ceo_ingress_socket_path,
            read_from_ceo_ingress=True, jwks_cache=_FakeJwksCache(rsa_key), clock=lambda: NOW),
            audit_sink=sink, workspace_app=AuditedWorkspaceApp(app, verifier))
        try:
            async with _mounted_lifespan(mounted):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mounted), base_url="https://mcp.mastermind-x.com") as client:
                    response = await client.get(ROUTE, params={"work_ref": WORK}, headers={"Authorization": "Bearer " + token})
                    assert seen["calls"]
                    if case.startswith("revoke"):
                        assert response.status_code == 403, response.text
                        assert "Complete the original journey" not in response.text
                    elif case == "catalogue_sha":
                        assert response.status_code == 503, response.text
                        assert response.json()["direction"] is None
                    else:
                        assert response.status_code == 200, response.text
                        assert response.json()["direction"]["current"]["decision_ref"] == "DEC:CURRENT"
                        assert response.json()["source"]["commit"] == seen["sha"]
                        assert response.headers["cache-control"] == "no-store"
                    assert owners[0].state_compose_seq == 0
        finally:
            await svc.close()
    asyncio.run(run())


@pytest.mark.parametrize("query", ["", "?work_ref=WS:ONE&root_job_id=JOB-1", "?work_ref=WS:ONE&work_ref=WS:OTHER",
    "?work_ref=../private", "?work_ref=WS:ONE&commit=" + "a" * 40, "?path=agentos/decisions/DEC-ONE.md"])
def test_unknown_or_duplicate_selectors_do_not_reach_source(rsa_key, query):
    app, client = _make_app(rsa_key)
    response = app.get(ROUTE + query, headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 400
    assert client.calls == []


@pytest.mark.parametrize("method,path", [("POST", ROUTE), ("HEAD", ROUTE), ("GET", "/workspace/project-%64irection/current")])
def test_raw_path_and_method_fences_run_before_auth_or_source(rsa_key, method, path):
    app, client = _make_app(rsa_key)
    response = app.request(method, path, params={"work_ref": WORK})
    assert response.status_code in (400, 404, 405)
    assert client.calls == []


def test_unsigned_read_and_malformed_socket_frame_never_acquire_source(rsa_key, monkeypatch):
    app, client = _make_app(rsa_key)
    assert app.get(ROUTE, params={"work_ref": WORK}).status_code == 401
    assert client.calls == []
    async def forbidden(*a, **kw): pytest.fail("Malformed frame opened socket")
    monkeypatch.setattr(asyncio, "open_unix_connection", forbidden)
    value = request(); value["selection"]["history_revision"] = "private"
    with pytest.raises(ValueError):
        asyncio.run(CeoIngressWorkspaceClient("/not-opened.sock").request(value))


@pytest.mark.parametrize("change", ["private", "oversize", "grant"])
def test_http_body_projects_no_raw_extra_fields_or_new_authority(direction_git, change):
    body = copy.deepcopy(read(direction_git))
    if change == "private": body["direction"]["private"] = "PRIVATE_SECRET"
    if change == "oversize": body["direction"]["current"]["answer"] = "PRIVATE_SECRET" * 10000
    if change == "grant": body["direction"]["current"]["can_place_work"] = True
    response = _project_direction_envelope_response({"ok": True, "result": body})
    assert response.status_code == 503
    assert b"PRIVATE_SECRET" not in response.body


def test_existing_project_session_head_is_refused_before_auth_or_backend(rsa_key, monkeypatch):
    from integrations.mastermind_workspace_app import app as workspace_app
    auth_calls = []
    async def forbidden_auth(*args, **kwargs):
        auth_calls.append(True)
        pytest.fail("HEAD reached authentication")
    monkeypatch.setattr(workspace_app, "_authenticate", forbidden_auth)
    app, client = _make_app(rsa_key)
    response = app.head("/workspace/project-session/current",
        params={"work_ref": WORK, "root_job_id": "JOB-1"})
    assert response.status_code == 405
    assert response.headers["allow"] == "GET"
    assert response.headers["cache-control"] == "no-store"
    assert auth_calls == []
    assert client.calls == []
