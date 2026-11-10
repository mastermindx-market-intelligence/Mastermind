"""Actual authenticated App consumes existing Paperclip and Capacity owners.

Runtime/DATA/plan and both JWT authorizers are real disposable fixtures. The
Paperclip transport's lowest network edge supplies source records; its client,
binding, service, sanitizers and explicit work mapping execute unchanged. The
private Workspace ingress edge calls its real handler/ExistingCapacity source
in process. No installed account, Unix service or task placement is claimed.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from urllib.parse import urlsplit

import pytest

from common import coo_project_help_contract as wire
from common import workspace_capacity_fabric_contract as capacity_wire
from control_plane.workspace_capacity_fabric import ExistingCapacityFabricSource
from integrations.executive_mcp import server
from integrations.mastermind_workspace_app.app import create_workspace_app
from integrations.paperclip_control.client import PaperclipHttpClient
from integrations.paperclip_control.contract import CONFIG_SCHEMA, DONOR_REVISION
from integrations.paperclip_control.installed import build_installed_binding
from tests import test_t3_project_help_api as api
from tests.test_coo_project_help_authority import (
    qualified_help, full_joined, owner, env, isolated_git_env, identity,
)
from tests.test_paperclip_connections import snapshot, uid
from tests.test_workspace_capacity_fabric import fixture_inputs, fixture_binding

rsa_key = api.rsa_key
signed_help = api.signed_help


@pytest.fixture
def avenues(signed_help, monkeypatch, tmp_path):
    s = signed_help
    old = s.workspace_app
    config = old._fresh_workspace_config
    who = s.f.j["workspace"]
    raw = {"schema": CONFIG_SCHEMA, "origin": "http://127.0.0.1:3100",
        "company_id": uid(90), "source_revision": DONOR_REVISION, "work_owner": "legacy",
        "wake_owner": "legacy", "create_backlog_enabled": False,
        "access": [{"subject_digest": who.subject_digest, "client_ref": who.client_ref,
            "credential_env": None, "local_operator": True, "create_backlog": False}],
        "hermes_bindings": [{"agent_id": uid(2), "profile_ref": "hermes:engineering",
            "supervisor_session_ref": "native:original", "gateway_ref": "gateway:original"}],
        "project_bindings": [{"project_id": uid(10), "work_ref": s.f.work}]}
    bound = build_installed_binding(raw, policy=config.authenticator.policy, load_current=lambda: raw)
    records, calls = snapshot(), []
    def network(self, method, path, token, payload):
        assert self is bound.client and method == "GET" and token is payload is None
        calls.append((method, path))
        route = urlsplit(path).path.rsplit("/", 1)[-1]
        if route == "health": return {"commit": DONOR_REVISION}
        if route == uid(90): return deepcopy(records["company"])
        kind = {"agents": "people", "issues": "work"}.get(route, route)
        if kind == "routines": return []
        return [{**deepcopy(item), "companyId": uid(90)} for item in records["collections"][kind]["items"]]
    monkeypatch.setattr(PaperclipHttpClient, "_once", network)

    preview, views = fixture_inputs(now=s.clock[0])
    binding = fixture_binding(preview, views)
    path = tmp_path / "existing-capacity-preview.json"
    path.write_text(json.dumps(preview))
    revisions = [binding]
    source = ExistingCapacityFabricSource(path, account_views=lambda refs: views,
        current_revision=lambda: revisions[0], now=lambda: s.clock[0])
    s.f.workspace._capacity_fabric_source = source
    private_calls = []
    async def private(frame):
        assert frame["schema"] == capacity_wire.FRAME_SCHEMA
        private_calls.append(deepcopy(frame))
        return await s.f.workspace.handle_frame(frame)
    # Retain the actual nominal existing client; only its private transport
    # boundary is controlled. No socket custody is simulated or asserted.
    monkeypatch.setattr(config.client, "request", private)
    config = replace(config, paperclip=bound)
    s.workspace_app = server.AuditedWorkspaceApp(create_workspace_app(config), old._verifier,
        authenticator=config.authenticator, authorize_principal=config.authorize_principal,
        fresh_workspace_config=config)
    s.company_configuration, s.company_records, s.company_calls = raw, records, calls
    s.capacity_source, s.capacity_preview, s.capacity_path = source, preview, path
    s.capacity_revisions, s.capacity_calls = revisions, private_calls
    return s


def _read(s):
    async def run():
        async with api._session(s) as (client, _):
            return await client.call_tool(wire.TOOL, {"work_ref": s.f.work})
    result = asyncio.run(run())
    return result, api._payload(result)


def test_current_project_receives_real_relationships_and_observed_capacity(avenues):
    s = avenues
    before = api._events(s.f)
    result, payload = _read(s)
    assert result.isError is False, payload
    data = payload["data"]
    company, routes = data["relationships"], data["execution_routes"]
    assert company["state"] == "AVAILABLE", company
    assert company["workRef"] == s.f.work and company["project"]["id"] == uid(10)
    assert company["projectMapping"] == "CONFIGURED_VISIBLE_REFERENCE"
    assert company["scope"] == "VISIBLE_COMPANY_NOT_PROJECT_MEMBERSHIP"
    assert company["people"][1]["reportsTo"] == uid(1)
    assert company["newWorkAuthorized"] is False and company["executionLineage"] == "NOT_PROJECTED"
    assert {row["kind"]: row["state"] for row in company["helpAvenues"]}["delegate"] == "NOT_BOUND_IN_THIS_SURFACE"
    assert routes["state"] == "AVAILABLE", routes
    assert routes["scope"] == "ESTATE_CAPACITY_NOT_TASK_PLACEMENT"
    assert routes["task_placement"] == "NOT_EVALUATED" and routes["new_execution_authorized"] is False
    capacity = routes["capacity"]
    assert capacity["admission_authorized"] is False
    assert capacity["resources"][1]["windows"][2]["remaining_pct"] == 0
    assert all(row["runtime_state"] == "NOT_OBSERVED" for row in capacity["consumers"])
    assert next(row for row in capacity["consumers"] if row["consumer"] == "t3_code")["source_state"] == "SPEC_ONLY"
    assert data["targets"]["state"] == "AVAILABLE" and data["targets"]["items"] == []
    assert data["scope"]["root_job_id"] == s.f.root
    assert len(s.reads) == 2 and len(s.capacity_calls) == 1
    assert {urlsplit(path).path.rsplit("/", 1)[-1] for _, path in s.company_calls} == {
        uid(90), "health", "agents", "projects", "goals", "issues", "routines"}
    assert api._events(s.f) == before
    assert "native:original" not in json.dumps(data) and "gateway:original" not in json.dumps(data)


def test_company_roster_does_not_invent_missing_project_membership(avenues):
    s = avenues
    s.company_records["collections"]["projects"]["items"] = []
    result, payload = _read(s)
    assert result.isError is False, payload
    company = payload["data"]["relationships"]
    assert company["state"] == "AVAILABLE" and company["people"]
    assert company["projectMapping"] == "NOT_OBSERVED_IN_VISIBLE_WINDOW"
    assert company["project"] is None and company["work"] == []
    assert payload["data"]["scope"]["root_job_id"] == s.f.root


def test_original_company_grant_rotation_during_outer_bracket_withholds_result(avenues):
    s = avenues
    def revoke():
        if len(s.reads) == 2:
            s.company_configuration["access"].clear()
    s.after[0] = revoke
    result, payload = _read(s)
    assert result.isError is True and payload.get("data") is None
    assert len(s.capacity_calls) == 1 and len(s.reads) == 2


def test_current_capacity_source_rotation_stays_unavailable_without_invented_placement(avenues, monkeypatch):
    s = avenues
    original = s.capacity_source.account_views
    def changed(refs):
        result = original(refs)
        s.capacity_revisions[0] = dict(s.capacity_revisions[0], registry_revision="rotated")
        return result
    # Frozen adapter's callback object is selected at construction, not changed
    # on a live source. Recompose the disposable source through its real owner.
    source = ExistingCapacityFabricSource(s.capacity_path, account_views=changed,
        current_revision=lambda: s.capacity_revisions[0], now=lambda: s.clock[0])
    s.f.workspace._capacity_fabric_source = source
    result, payload = _read(s)
    assert result.isError is False, payload
    routes = payload["data"]["execution_routes"]
    assert routes["state"] == "UNAVAILABLE" and routes["capacity"] is None
    assert routes["task_placement"] == "NOT_EVALUATED" and routes["new_execution_authorized"] is False
    assert payload["data"]["relationships"]["state"] == "AVAILABLE"
