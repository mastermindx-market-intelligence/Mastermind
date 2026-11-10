"""Relationship semantics and the real service's scoped read composition.

All principals, source records and transport responses here are synthetic.
The tests do not install bindings, contact Paperclip or admit runtime work.
"""
import asyncio
from copy import deepcopy
from urllib.parse import urlsplit

import pytest

from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.paperclip_control.connections import project_connections
from integrations.paperclip_control.contract import DONOR_REVISION, PaperclipError, project_record
from integrations.paperclip_control.installed import Access, HermesBinding, PaperclipWorkspaceBinding
from integrations.paperclip_control.service import PaperclipWorkspace


def uid(number):
    return f"00000000-0000-4000-8000-{number:012d}"


def collection(items=(), **extra):
    return {"state": "CURRENT", "items": list(items), "coverage": "BOUNDED_RESPONSE",
            "hasMore": False, "restrictedCount": 0, "nextOffset": None, "nextCursor": None, **extra}


def snapshot():
    return {"schema": "mastermind.paperclip_workspace.v1", "state": "CURRENT", "view": "overview",
        "company": {"id": uid(90), "name": "Synthetic company"}, "bindingRevision": "a" * 64,
        "scopeKey": "b" * 64, "observedAt": "2026-11-10T07:00:00Z",
        "sourceRevision": DONOR_REVISION, "qualifiedRevision": DONOR_REVISION,
        "capabilities": [], "item": None,
        "ownership": {"work": "legacy", "wake": "legacy", "runtime": "hermes", "admission": "executive", "routing": "capacity"},
        "collections": {
            "people": collection([{"id": uid(1), "name": "Director", "status": "idle"},
                                  {"id": uid(2), "name": "Engineer", "reportsTo": uid(1), "status": "idle"}]),
            "projects": collection([{"id": uid(10), "name": "Delivery", "goalId": uid(20), "leadAgentId": uid(1)}]),
            "goals": collection([{"id": uid(20), "title": "Useful outcome", "ownerAgentId": uid(1)}]),
            "work": collection([{"id": uid(30), "title": "Original parent", "projectId": uid(10), "goalId": uid(20)},
                                {"id": uid(31), "title": "Child work", "parentId": uid(30), "assigneeAgentId": uid(2)}]),
        },
        "runtimeBindings": [HermesBinding(uid(2), "hermes:engineering", "native:original", "gateway:original").public()],
        "projectBindings": [{"projectId": uid(10), "workRef": "WS:ORIGINAL-PROJECT"}],
    }


def test_three_graphs_remain_distinct_and_help_is_not_admission():
    result = project_connections(snapshot())
    assert result["state"] == "CURRENT"
    assert {edge["relation"] for edge in result["relationships"]} == {
        "reports_to", "project_goal", "project_lead", "goal_owner", "issue_project",
        "issue_goal", "issue_parent", "issue_assignee", "runs_as", "tracks_work"}
    assert result["dependencies"] == result["executionLineage"] == "NOT_PROJECTED"
    assert result["parentConsumption"] == "NOT_OBSERVED"
    assert result["consistency"] == "SEPARATE_READS_NOT_ATOMIC"
    routes = {entry["kind"]: entry["state"] for entry in result["helpAvenues"]}
    assert routes["browse_team"] == routes["inspect_runtime"] == "READ_ROUTE"
    assert all(routes[key] == "NOT_BOUND_IN_THIS_SURFACE" for key in ("consult", "delegate", "resume", "create_backlog"))
    assert all(edge["state"] == "CONFIGURED_NOT_LIVE_VERIFIED" for edge in result["relationships"] if edge["relation"] in {"runs_as", "tracks_work"})


@pytest.mark.parametrize("collection_name,field,relation", [("people", "reportsTo", "reports_to"), ("goals", "parentId", "goal_parent"), ("work", "parentId", "issue_parent")])
def test_visible_parent_cycles_are_withheld(collection_name, field, relation):
    source = snapshot()
    source["collections"][collection_name] = collection([{"id": uid(1), field: uid(2)}, {"id": uid(2), field: uid(1)}])
    result = project_connections(source)
    assert result["state"] == "WITHHELD" and result["relationships"] == []
    assert any(row["code"] == "VISIBLE_CYCLE" and row["relation"] == relation for row in result["findings"])


@pytest.mark.parametrize("source_change", ["hasMore", "restricted", "unavailable", "not_requested"])
def test_missing_target_is_only_outside_this_window(source_change):
    source = snapshot()
    source["collections"]["people"]["items"] = [{"id": uid(2), "reportsTo": uid(99)}]
    if source_change == "hasMore": source["collections"]["people"]["hasMore"] = True
    if source_change == "restricted": source["collections"]["people"]["restrictedCount"] = 1
    if source_change == "unavailable": source["collections"]["goals"] = collection(state="UNAVAILABLE")
    if source_change == "not_requested": del source["collections"]["goals"]
    result = project_connections(source)
    assert result["state"] == "PARTIAL" and result["findings"] == []
    assert next(edge for edge in result["relationships"] if edge["relation"] == "reports_to")["state"] == "OUTSIDE_VISIBLE_WINDOW"


@pytest.mark.parametrize("mutation,code", [("duplicate", "DUPLICATE_ID"), ("self", "SELF_REFERENCE"), ("malformed", "MALFORMED_REFERENCE"), ("binding", "AMBIGUOUS_BINDING")])
def test_invalid_or_ambiguous_source_does_not_form_an_authoritative_graph(mutation, code):
    source = snapshot()
    if mutation == "duplicate": source["collections"]["people"]["items"].append(deepcopy(source["collections"]["people"]["items"][0]))
    if mutation == "self": source["collections"]["people"]["items"][0]["reportsTo"] = uid(1)
    if mutation == "malformed": source["collections"]["people"]["items"][0]["reportsTo"] = "secret-not-a-native-reference"
    if mutation == "binding": source["projectBindings"].append({"projectId": uid(10), "workRef": "WS:DIFFERENT"})
    result = project_connections(source)
    assert result["state"] == "WITHHELD" and result["relationships"] == []
    assert code in {row["code"] for row in result["findings"]}
    assert "secret-not-a-native-reference" not in str(result)


def test_hidden_configured_references_are_not_disclosed():
    source = snapshot()
    source["runtimeBindings"].append(HermesBinding(uid(98), "private:hidden-profile", None, "private:gateway").public())
    source["projectBindings"].append({"projectId": uid(99), "workRef": "WS:PRIVATE-HIDDEN"})
    result = project_connections(source)
    assert "private:" not in str(result) and "PRIVATE-HIDDEN" not in str(result)


def test_native_id_namespaces_are_not_collapsed():
    source = snapshot()
    source["collections"]["projects"]["items"][0]["id"] = uid(1)
    source["projectBindings"] = []
    result = project_connections(source)
    assert not any(row["code"] == "DUPLICATE_ID" for row in result["findings"])


def test_backlog_is_only_bound_by_existing_capability():
    source = snapshot()
    source["capabilities"] = ["create_backlog"]
    routes = {entry["kind"]: entry["state"] for entry in project_connections(source)["helpAvenues"]}
    assert routes["create_backlog"] == "COMMAND_BOUND" and routes["delegate"] == "NOT_BOUND_IN_THIS_SURFACE"


@pytest.mark.parametrize("kind,field", [("people", "reportsTo"), ("projects", "goalId"), ("projects", "leadAgentId"),
    ("goals", "parentId"), ("goals", "ownerAgentId"), ("work", "parentId"), ("work", "projectId"),
    ("work", "goalId"), ("work", "assigneeAgentId")])
@pytest.mark.parametrize("invalid", [["malformed"], 7, True, "not-a-native-reference"])
def test_actual_source_projection_does_not_erase_corrupt_relationship(kind, field, invalid):
    with pytest.raises(PaperclipError, match="^SOURCE_RECORD_INVALID$"):
        project_record(kind, {"id": uid(1), field: invalid}, uid(90))


def test_absent_and_null_parent_are_legitimate_source_values():
    assert project_record("people", {"id": uid(1)}, uid(90)) == {"id": uid(1)}
    assert project_record("people", {"id": uid(1), "reportsTo": None}, uid(90)) == {"id": uid(1)}


def service_fixture(*, revoke=False, wrong_company=False, unavailable_goals=False):
    source, live, calls = snapshot(), [True], []
    principal = VerifiedPrincipal("synthetic-policy", "https://issuer.invalid", "c" * 64,
        "https://workspace.invalid", "d" * 64, "synthetic-client", (), 1, 999999, None)
    class FakeClient:
        async def request(self, method, path, **_):
            calls.append((method, path))
            assert method == "GET"
            route = urlsplit(path).path.rsplit("/", 1)[-1]
            if route == "health": return {"commit": DONOR_REVISION}
            if route == uid(90): return source["company"]
            name = {"agents": "people", "issues": "work"}.get(route, route)
            if name == "goals":
                if revoke: live[0] = False
                if unavailable_goals: raise PaperclipError("SOURCE_UNAVAILABLE")
            result = deepcopy(source["collections"].get(name, collection())["items"])
            if wrong_company and name == "people": result[0]["companyId"] = uid(999)
            return result
    binding = PaperclipWorkspaceBinding(FakeClient(), uid(90), DONOR_REVISION, "a" * 64,
        "legacy", "legacy", False, (Access("d" * 64, "synthetic-client", local_operator=True),),
        (HermesBinding(uid(2), "hermes:engineering", "native:original", "gateway:original"),
         HermesBinding(uid(98), "private:hidden-profile", None, "private:gateway")),
        ((uid(10), "WS:ORIGINAL-PROJECT"), (uid(99), "WS:PRIVATE-HIDDEN")),
        "synthetic-policy", lambda: live[0])
    return PaperclipWorkspace(binding, principal, authorize=lambda _: True, now=lambda: 100), calls


def test_existing_service_emits_projection_after_visible_joins_with_no_commands():
    service, calls = service_fixture()
    result = asyncio.run(service.read({"view": "overview"}))
    assert result["connections"]["state"] == "CURRENT"
    assert len(calls) == 7 and all(method == "GET" for method, _ in calls)
    assert "private:" not in str(result) and "PRIVATE-HIDDEN" not in str(result)
    assert set(result["collections"]) == {"people", "projects", "goals", "work", "routines"}


@pytest.mark.parametrize("kwargs", [{"revoke": True}, {"wrong_company": True}])
def test_revoked_or_foreign_source_discards_the_entire_read(kwargs):
    service, _ = service_fixture(**kwargs)
    with pytest.raises(PaperclipError): asyncio.run(service.read({"view": "overview"}))


def test_one_unavailable_collection_preserves_other_scoped_records():
    service, _ = service_fixture(unavailable_goals=True)
    result = asyncio.run(service.read({"view": "overview"}))
    assert result["state"] == result["connections"]["state"] == "PARTIAL"
    assert len(result["collections"]["people"]["items"]) == 2
    assert result["collections"]["goals"]["state"] == "UNAVAILABLE"
