"""Rootless archive acquisition through the real signed HTTP/socket/read join."""
import asyncio
import copy

import httpx
import pytest

from common import workspace_project_archive_contract as wire
from control_plane.workspace_read_service import WorkspaceReadService
from control_plane.workspace_project_archive_read import ProjectArchiveReadAdapter
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA, principal_frame, workspace_authorizers
from integrations.executive_mcp.installed import InstalledBootPacketCollector
from tests.test_agentos_project_archive_source import bound, WORK
from tests.test_workspace_read_service import cache_fixture
from tests.test_workspace_read_app import rsa_key, _authenticator, _workspace_token, NOW, _make_app
from tests.test_workspace_result_socket import control, short_socket_root

ROUTE = "/workspace/projects/archive/current"


def catalogue(tmp_path, macro_sha):
    owners, clock, cache = cache_fixture(tmp_path)
    doc = owners[0].state_cache["doc"]
    doc["sources"] = {"macro_sha": macro_sha}
    doc["work"][0]["work_ref"] = WORK
    doc["autonomy"]["responsibilities"][0]["responsibility_ref"] = WORK
    from scripts import chairman_control_room as ccr
    with owners[0].state_lock:
        ccr._publish_source_validity(owners[0], doc, tuple(clock), tuple(clock))
    return owners, cache


@pytest.mark.parametrize("case", ["available", "empty_sample", "revoke_source", "revoke_socket", "catalogue_sha", "publication", "catalogue_document"])
def test_signed_fixed_read_is_bound_to_original_permission_and_catalogue(tmp_path, monkeypatch, rsa_key, short_socket_root, case):
    async def run():
        auth = _authenticator(rsa_key); token = _workspace_token(rsa_key)
        principal = await auth.verify_authorization_header("Bearer " + token, now=NOW)
        slots = {"schema": BINDINGS_SCHEMA, "profiles": {
            "web": {"enabled": True, "binding": dict(principal_frame(principal), permission_digest="a" * 64)},
            "mac": {"enabled": False, "binding": None}}}
        app_auth, control_auth = workspace_authorizers(policy=auth.policy, load_bindings=lambda: slots)
        def revoke(): slots["profiles"]["web"]["enabled"] = False
        (tmp_path / "source").mkdir(); (tmp_path / "catalogue").mkdir()
        collector, seen = bound(tmp_path / "source", monkeypatch, archived=case != "empty_sample")
        owners, cache = catalogue(tmp_path / "catalogue", "f" * 40 if case == "catalogue_sha" else seen["sha"])
        original = InstalledBootPacketCollector.read_project_archive
        def acquire(owner, **kwargs):
            result = original(owner, **kwargs)
            if case == "revoke_source": revoke()
            if case == "publication": owners[0].state_published_seq += 1
            if case == "catalogue_document": owners[0].state_cache["doc"]["work"][0]["agent_os"]["title"] = "Changed"
            return result
        monkeypatch.setattr(InstalledBootPacketCollector, "read_project_archive", acquire)
        reader = collector.project_archive_reader(macro_root=seen["macro"])
        class NoRuntime:
            def __getattr__(self, key): pytest.fail("Archive read acquired Runtime")
        provider = WorkspaceReadService(cache=cache, runtime=NoRuntime(), authorize=control_auth,
            armed={}, runtime_identity={}, project_archive_reader=reader)
        svc = control(tmp_path / "service", short_socket_root, lambda _: provider)
        await svc.start()
        peer = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
        class Client:
            async def request(self, frame):
                value = await peer.request(frame)
                if case == "revoke_socket": revoke()
                return value
        app = create_workspace_app(WorkspaceAppConfig(authenticator=auth, now=lambda: NOW,
            authorize_principal=app_auth, client=Client()))
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://mcp.mastermind-x.com") as client:
                response = await client.get(ROUTE, headers={"Authorization": "Bearer " + token})
            if case.startswith("revoke"):
                assert response.status_code == 403 and "archived_by" not in response.text
            elif case in ("catalogue_sha", "publication", "catalogue_document"):
                assert response.status_code == 503
                assert response.json()["sample"] is None and response.json()["catalogue"] is None
            else:
                assert response.status_code == 200, response.text
                body = wire.validate_body(response.json())
                assert body["catalogue"]["work_refs"] == [WORK]
                assert body["sample"]["coverage"]["company_total"] is None
                assert len(body["sample"]["items"]) == (0 if case == "empty_sample" else 1)
                assert body["sample"]["can_restore"] is False
            assert response.headers["cache-control"] == "no-store"
        finally: await svc.close()
    asyncio.run(run())


@pytest.mark.parametrize("query", ["?work_ref=WS:FOREIGN", "?work_refs=WS:FOREIGN", "?macro_sha=" + "a" * 40,
                                   "?path=/private", "?page=2", "?restore=true"])
def test_caller_selectors_are_not_archive_membership_authority(rsa_key, query):
    app, client = _make_app(rsa_key)
    result = app.get(ROUTE + query, headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert result.status_code == 400 and client.calls == []


@pytest.mark.parametrize("method", ["HEAD", "POST"])
def test_method_fence_is_before_authentication_and_backend(rsa_key, monkeypatch, method):
    from integrations.mastermind_workspace_app import app as module
    calls = []
    async def forbidden(*args, **kwargs): calls.append(True); pytest.fail("method reached auth")
    monkeypatch.setattr(module, "_authenticate", forbidden)
    app, client = _make_app(rsa_key)
    response = app.request(method, ROUTE)
    assert response.status_code == 405 and response.headers["allow"] == "GET"
    assert calls == [] and client.calls == []


def test_unsigned_archive_request_does_not_reach_backend(rsa_key):
    app, client = _make_app(rsa_key)
    assert app.get(ROUTE).status_code == 401 and client.calls == []


def test_missing_permission_receipt_cannot_acquire_archive(tmp_path, monkeypatch):
    collector, seen = bound(tmp_path, monkeypatch)
    _, cache = catalogue(tmp_path, seen["sha"])
    owner = WorkspaceReadService(cache=cache, runtime=object(), authorize=lambda principal: True, armed={}, runtime_identity={})
    adapter = ProjectArchiveReadAdapter(workspace=owner, reader=collector.project_archive_reader(macro_root=seen["macro"]))
    from tests.test_workspace_project_direction_read import request
    frame = {"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION, "principal": request()["principal"]}
    result = asyncio.run(adapter.handle_frame(frame))
    assert result["status"] == 403 and seen["calls"] == []


def test_unavailable_has_no_retained_rows_or_catalogue():
    body = wire.unavailable()
    assert wire.validate_body(body) == body
    with pytest.raises(ValueError): wire.validate_body(dict(body, catalogue={"work_refs": [WORK]}))
