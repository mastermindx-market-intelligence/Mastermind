"""Authenticated project plan read over real Macro parser/Workspace owners; inert source I/O."""
import asyncio
import json

import pytest

from common import executive_workspace_contract as workspace
from common import workspace_project_plan_contract as wire
from control_plane.agentos_project_plan import AgentOsProjectPlanReader
from control_plane.workspace_read_service import WorkspaceReadService
from tests.test_agentos_project_plan_source import source_git, read, SHA
from tests.test_workspace_read_service import cache_fixture, frame
from tests.test_workspace_read_app import rsa_key, _make_app, _workspace_token, _FakeWorkspaceClient

ROUTE = "/workspace/project-plan/current"


def request():
    value = frame()
    value.update(schema=wire.FRAME_SCHEMA, operation=wire.OPERATION,
                 selection={"work_ref": "WS:ONE"})
    return value


def provider(tmp_path, monkeypatch, source_git, authorize=lambda principal: True, after=None):
    from pathlib import Path
    runner, calls = source_git
    owners, clock, cache = cache_fixture(tmp_path)
    owners[0].state_cache["doc"]["sources"] = {"macro_sha": SHA}
    reader = AgentOsProjectPlanReader(macro_root=Path("/qualified/macro"))
    def acquire(self, *, work_ref):
        assert work_ref == "WS:ONE"
        value = read(runner)
        if after: after(owners)
        return value
    monkeypatch.setattr(AgentOsProjectPlanReader, "read", acquire)
    class RuntimeForbidden:
        def __getattr__(self, name):
            pytest.fail("Project plan must not read Runtime or require a Job")
    service = WorkspaceReadService(cache=cache, runtime=RuntimeForbidden(), authorize=authorize,
        armed={}, runtime_identity={}, project_plan_reader=reader)
    return service, owners, calls


def test_actual_canonical_plan_reads_without_job_selector_or_runtime(tmp_path, monkeypatch, source_git):
    service, owners, calls = provider(tmp_path, monkeypatch, source_git)
    value = asyncio.run(service.handle_frame(request()))
    assert value["ok"] is True and value["result"]["availability"] == "AVAILABLE"
    assert value["result"]["selection"] == {"work_ref": "WS:ONE"}
    assert value["result"]["plan"]["objective"] == "Deliver the real owner content."
    assert value["result"]["plan"]["adoption"] == {"state": "UNAVAILABLE", "reason": "NOT_DECLARED"}
    assert calls and owners[0].state_compose_seq == 0


def test_permission_refused_before_source_acquisition(tmp_path, monkeypatch, source_git):
    service, owners, calls = provider(tmp_path, monkeypatch, source_git, authorize=lambda p: False)
    assert asyncio.run(service.handle_frame(request())) == workspace.error("access_denied", 403)
    assert calls == []


def test_revocation_during_actual_source_read_discards_content(tmp_path, monkeypatch, source_git):
    allowed = [True]
    service, _, calls = provider(tmp_path, monkeypatch, source_git,
        authorize=lambda p: allowed[0], after=lambda owners: allowed.__setitem__(0, False))
    value = asyncio.run(service.handle_frame(request()))
    assert value == workspace.error("access_denied", 403)
    assert calls and "Deliver the real" not in json.dumps(value)


@pytest.mark.parametrize("change", ["publication", "source", "document"])
def test_catalogue_drift_after_acquisition_discards_plan(tmp_path, monkeypatch, source_git, change):
    def mutate(owners):
        if change == "publication": owners[0].state_published_seq += 1
        if change == "source": owners[0].state_cache["doc"]["sources"]["macro_sha"] = "b" * 40
        if change == "document": owners[0].state_cache["doc"]["work"][0]["agent_os"]["title"] = "Changed"
    service, _, _ = provider(tmp_path, monkeypatch, source_git, after=mutate)
    value = asyncio.run(service.handle_frame(request()))
    assert value["ok"] is True and value["result"]["availability"] == "UNAVAILABLE"
    assert value["result"]["reason_codes"] in (["SOURCE_CHANGED"], ["SOURCE_UNAVAILABLE"])
    assert value["result"]["plan"] is None


def test_unknown_catalogue_work_ref_never_reaches_source(tmp_path, monkeypatch, source_git):
    service, _, calls = provider(tmp_path, monkeypatch, source_git)
    value = request(); value["selection"] = {"work_ref": "WS:OTHER"}
    assert asyncio.run(service.handle_frame(value)) == workspace.error("selection_not_found", 404)
    assert calls == []


def test_signed_http_get_uses_same_workspace_read_authority(rsa_key, source_git):
    body = read(source_git[0])
    client, fake = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope={"ok": True, "result": body}))
    response = client.get(ROUTE, params={"work_ref": "WS:ONE"},
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 200, response.text
    assert response.json() == body
    assert fake.calls[0]["schema"] == wire.FRAME_SCHEMA
    assert fake.calls[0]["selection"] == {"work_ref": "WS:ONE"}
    assert "no-store" in response.headers["cache-control"]


@pytest.mark.parametrize("query", ["", "?work_ref=WS:ONE&root_job_id=JOB-1", "?work_ref=WS:ONE&work_ref=WS:OTHER", "?work_ref=../private", "?path=agentos/workstreams/WS-ONE.md", "?work_ref=WS:ONE&commit=" + "a" * 40])
def test_extra_or_malformed_http_selector_refused_before_owner(rsa_key, query):
    client, fake = _make_app(rsa_key)
    response = client.get(ROUTE + query, headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 400
    assert fake.calls == []


def test_anonymous_http_never_reads_source(rsa_key):
    client, fake = _make_app(rsa_key)
    response = client.get(ROUTE, params={"work_ref": "WS:ONE"})
    assert response.status_code == 401
    assert fake.calls == []


def test_real_macro_producer_to_signed_http_route_without_runtime(tmp_path, monkeypatch, source_git, rsa_key):
    service, _, calls = provider(tmp_path, monkeypatch, source_git)
    class JoinedClient:
        async def request(self, frame):
            return await service.handle_frame(dict(frame))
    client, _ = _make_app(rsa_key, client=JoinedClient())
    response = client.get(ROUTE, params={"work_ref": "WS:ONE"},
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["plan"]["objective"] == "Deliver the real owner content."
    assert value["plan"]["waves"][1]["depends_on"] == ["first"]
    assert value["plan"]["version_history"]["revisions"][0]["commit"] == "c" * 40
    assert value["source"]["commit"] == SHA
    assert calls and "Private body" not in response.text


def test_http_revocation_after_source_discards_joined_response(tmp_path, monkeypatch, source_git, rsa_key):
    allowed = [True]
    service, _, calls = provider(tmp_path, monkeypatch, source_git,
        after=lambda _: allowed.__setitem__(0, False))
    class JoinedClient:
        async def request(self, frame):
            return await service.handle_frame(dict(frame))
    client, _ = _make_app(rsa_key, client=JoinedClient(), authorize=lambda _: allowed[0])
    response = client.get(ROUTE, params={"work_ref": "WS:ONE"},
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 403, response.text
    assert calls and "Deliver the real" not in response.text


@pytest.mark.parametrize("claims", [dict(scope="openid"), dict(aud="https://wrong.invalid/read"), dict(exp=1)])
def test_wrong_scope_audience_or_expired_identity_never_reads_owner(rsa_key, claims):
    client, fake = _make_app(rsa_key)
    response = client.get(ROUTE, params={"work_ref": "WS:ONE"},
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key, **claims)})
    assert response.status_code in (401, 403)
    assert fake.calls == []


@pytest.mark.parametrize("unmapped", [False, True])
def test_catalogued_plan_does_not_require_a_runtime_root_or_mapped_seat(tmp_path, monkeypatch, source_git, unmapped):
    service, owners, calls = provider(tmp_path, monkeypatch, source_git)
    owner = owners[0]
    doc = owner.state_cache["doc"]
    if unmapped:
        doc["autonomy"]["responsibilities"] = []
        doc["autonomy"]["unmapped_responsibilities"] = [
            {"responsibility_ref": "WS:ONE", "reason": "owner_not_a_recognized_seat"}]
        doc["autonomy"]["counts"] = {"total": 0, "empty": False}
    else:
        row = doc["autonomy"]["responsibilities"][0]
        row.update(root_job_id=None, root_job_candidates=[], runtime_root_state="UNRESOLVED", is_actionable=False)
    from scripts import chairman_control_room as ccr
    sample = owner.validity_sample_fn()
    with owner.state_lock: ccr._publish_source_validity(owner, doc, sample, sample)
    result = asyncio.run(service.handle_frame(request()))
    assert result["ok"] is True and result["result"]["availability"] == "AVAILABLE", result
    assert calls
