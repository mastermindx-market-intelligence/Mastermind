"""Existing Workspace permission/catalogue bracket + actual captured Direction owner."""
import asyncio
from pathlib import Path

import pytest

from common import workspace_project_direction_contract as wire
from common.executive_workspace_contract import error
from control_plane.agentos_project_direction import AgentOsProjectDirectionReader
from control_plane.workspace_project_direction_read import ProjectDirectionReadAdapter
from control_plane.workspace_read_service import WorkspaceReadService
from tests.test_agentos_project_direction_source import direction_git, read, WORK
from tests.test_workspace_read_service import cache_fixture, frame


def request():
    result = frame()
    result.update(schema=wire.FRAME_SCHEMA, operation=wire.OPERATION, selection={"work_ref": WORK})
    return result


def service(tmp_path, monkeypatch, direction_git, *, after=None):
    owners, clock, cache = cache_fixture(tmp_path)
    owners[0].state_cache["doc"]["sources"] = {"macro_sha": direction_git[0]}
    owners[0].state_cache["doc"]["work"][0]["work_ref"] = WORK
    owners[0].state_cache["doc"]["autonomy"]["responsibilities"][0]["responsibility_ref"] = WORK
    from scripts import chairman_control_room as ccr
    with owners[0].state_lock:
        ccr._publish_source_validity(owners[0], owners[0].state_cache["doc"], tuple(clock), tuple(clock))
    allowed, binding = [True], ["a" * 64]
    def authorize(principal):
        return allowed[0]
    authorize.binding_digest = lambda principal: binding[0]
    class NoRuntime:
        def __getattr__(self, name):
            pytest.fail("Direction must not acquire Runtime or require a Job")
    workspace = WorkspaceReadService(cache=cache, runtime=NoRuntime(), authorize=authorize, armed={}, runtime_identity={})
    reader = AgentOsProjectDirectionReader(macro_root=Path("/qualified/macro"))
    def acquire(self, *, work_ref):
        assert work_ref == WORK
        result = read(direction_git)
        if after:
            after(owners, allowed, binding, workspace)
        return result
    monkeypatch.setattr(AgentOsProjectDirectionReader, "read", acquire)
    return ProjectDirectionReadAdapter(workspace=workspace, reader=reader), owners, allowed, binding


def test_owner_join_is_rootless_and_observational(tmp_path, monkeypatch, direction_git):
    adapter, owners, _, _ = service(tmp_path, monkeypatch, direction_git)
    result = asyncio.run(adapter.handle_frame(request()))
    assert result["ok"] and result["result"]["availability"] == "AVAILABLE", result
    assert result["result"]["direction"]["current"]["decision_ref"] == "DEC:CURRENT"
    assert owners[0].state_compose_seq == 0


def test_denial_prevents_any_source_read(tmp_path, monkeypatch, direction_git):
    adapter, _, allowed, _ = service(tmp_path, monkeypatch, direction_git)
    allowed[0] = False
    assert asyncio.run(adapter.handle_frame(request())) == error("access_denied", 403)
    assert direction_git[2] == []


@pytest.mark.parametrize("kind", ["revoked", "permission_binding", "authorizer_replaced"])
def test_post_read_auth_changes_discard_accepted_content(tmp_path, monkeypatch, direction_git, kind):
    def after(owners, allowed, binding, workspace):
        if kind == "revoked": allowed[0] = False
        if kind == "permission_binding": binding[0] = "b" * 64
        if kind == "authorizer_replaced": workspace.authorize = lambda principal: True
    adapter, _, _, _ = service(tmp_path, monkeypatch, direction_git, after=after)
    assert asyncio.run(adapter.handle_frame(request())) == error("access_denied", 403)
    assert direction_git[2]


@pytest.mark.parametrize("kind", ["publication", "source", "document"])
def test_post_read_catalogue_changes_discard_direction(tmp_path, monkeypatch, direction_git, kind):
    def after(owners, allowed, binding, workspace):
        if kind == "publication": owners[0].state_published_seq += 1
        if kind == "source": owners[0].state_cache["doc"]["sources"]["macro_sha"] = "b" * 40
        if kind == "document": owners[0].state_cache["doc"]["work"][0]["agent_os"]["title"] = "Changed"
    adapter, _, _, _ = service(tmp_path, monkeypatch, direction_git, after=after)
    result = asyncio.run(adapter.handle_frame(request()))
    assert result["ok"] and result["result"]["availability"] == "UNAVAILABLE"
    assert result["result"]["direction"] is None


def test_unknown_work_and_caller_revision_never_reach_source(tmp_path, monkeypatch, direction_git):
    adapter, _, _, _ = service(tmp_path, monkeypatch, direction_git)
    unknown = request(); unknown["selection"] = {"work_ref": "WS:OTHER"}
    assert asyncio.run(adapter.handle_frame(unknown)) == error("selection_not_found", 404)
    invalid = request(); invalid["selection"]["commit"] = "b" * 40
    assert asyncio.run(adapter.handle_frame(invalid)) == error("invalid_input", 400)
    assert direction_git[2] == []


def test_missing_permission_receipt_does_not_fall_back_to_bare_true(tmp_path, monkeypatch, direction_git):
    adapter, _, _, _ = service(tmp_path, monkeypatch, direction_git)
    adapter._workspace.authorize = lambda principal: True
    assert asyncio.run(adapter.handle_frame(request())) == error("access_denied", 403)
    assert direction_git[2] == []
