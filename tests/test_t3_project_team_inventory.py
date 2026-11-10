"""Actual native inventory semantics, hidden-child coverage and path alias checks."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from integrations.session_bridge.t3_project_team import (
    TeamError, inventory_coverage, prepare_delegation, project_graph,
)
from integrations.session_bridge.t3_project_team_inventory import (
    InventoryThread, NativeInventory, inventory_from_document, read_native_inventory,
)
from integrations.session_bridge.t3_web_client import NativeUnavailable
from tests.test_t3_project_team import (
    binding, changed_role, inventory_fixture, snapshot, team_fixture,
)


def native_row(thread="root", parent=None, status="running", project="p", relationship=None):
    return {"threadId": thread, "projectId": project, "parentThreadId": parent,
            "relationshipToParent": relationship or ("subagent" if parent else None),
            "status": status, "latestRunId": "run-" + thread}


def page(rows, next_cursor=None, total=None):
    return {"projectId": "p", "currentThreadId": None, "threads": rows,
            "nextCursor": next_cursor, "total": len(rows) if total is None else total}


def test_real_native_shape_is_paged_once_with_children_and_no_environment_forwarding():
    calls = []
    values = [page([native_row()], 1, 2), page([native_row("child", "root")], None, 2)]

    async def native(tool, arguments):
        calls.append((tool, arguments))
        return values[len(calls) - 1]

    result = asyncio.run(read_native_inventory(native, environment_id="local-env", project_id="p"))
    assert len(calls) == 2
    assert [args["cursor"] for _, args in calls] == [0, 1]
    assert all(tool == "t3_thread_list" and args["includeSubagents"] is True
               and args["projectId"] == "p" and args["limit"] == 100
               and "environmentId" not in args for tool, args in calls)
    assert result.descendants("root") == {"root", "child"}
    assert result.is_fresh()
    assert inventory_from_document(result.document()) == result
    assert result.document()["atomic_snapshot"] is False


@pytest.mark.parametrize("bad", [
    {}, page([native_row(project="wrong")]), page([native_row()], 0, 2),
    page([], 1, 1), page([native_row()], None, 2), page([native_row(), native_row()]),
    page([native_row("a", "b"), native_row("b", "a")]),
    page([native_row(status="magically_finished")]),
    page([native_row()], True, 2), page([native_row()], None, True),
    page([native_row()], None, 1001),
])
def test_malformed_partial_cyclic_and_duplicate_native_inventory_never_becomes_success(bad):
    calls = []

    def native(tool, arguments):
        calls.append(arguments)
        return bad

    with pytest.raises(NativeUnavailable):
        asyncio.run(read_native_inventory(native, environment_id="e", project_id="p"))
    assert len(calls) == 1


def test_inventory_total_drift_and_cursor_loops_do_not_retry():
    for second in (page([native_row("child", "root")], None, 3),
                   page([native_row("child", "root")], 1, 2)):
        calls = []

        def native(tool, arguments):
            calls.append(arguments)
            return page([native_row()], 1, 2) if len(calls) == 1 else second

        with pytest.raises(NativeUnavailable):
            asyncio.run(read_native_inventory(native, environment_id="e", project_id="p"))
        assert len(calls) == 2


def test_native_transport_failure_is_sanitized_and_not_retried():
    calls = []

    def native(tool, arguments):
        calls.append(arguments)
        raise RuntimeError("Bearer DO_NOT_LEAK_THIS_PRIVATE_DIAGNOSTIC")

    with pytest.raises(NativeUnavailable) as error:
        asyncio.run(read_native_inventory(native, environment_id="e", project_id="p"))
    assert "Bearer" not in str(error.value) and len(calls) == 1


def test_unrelated_projects_and_forks_are_not_mistaken_for_team_descendants():
    result = asyncio.run(read_native_inventory(
        lambda tool, args: page([native_row(), native_row("child", "root"),
                                 native_row("fork", "root", relationship="fork"),
                                 native_row("other"), native_row("other-child", "other")]),
        environment_id="e", project_id="p"))
    assert result.descendants("root") == {"root", "child"}
    with pytest.raises(NativeUnavailable):
        result.descendants("not-observed")


def test_inventory_age_is_bounded_and_future_timestamps_are_not_fresh():
    team = team_fixture()
    root = binding(team, "coo")
    inventory = inventory_fixture(team, (root,))
    now = datetime.now(timezone.utc)
    for delta in (-121, 1):
        changed = replace(inventory, observed_at=(now + timedelta(seconds=delta)).isoformat())
        assert not changed.is_fresh(now=now)
    with pytest.raises(NativeUnavailable):
        replace(inventory, observed_at="2026-11-09T12:00:00")
    doc = inventory.document()
    doc["includes_subagents"] = False
    with pytest.raises(NativeUnavailable):
        inventory_from_document(doc)


def test_missing_or_hidden_native_children_block_new_delegation_and_full_completion_claims():
    team = team_fixture()
    bindings = tuple(binding(team, role.role_id) for role in team.roles)
    observations = {item.role_id: snapshot(item, "completed") for item in bindings}
    good = inventory_fixture(team, bindings, observations)
    graph = project_graph(team, bindings=bindings, observations=observations)
    assert graph["all_defined_results_available"]
    assert not graph["all_native_results_available"]
    assert graph["native_inventory_coverage"]["state"] == "not_observed"
    hidden = replace(good, threads=good.threads + (
        InventoryThread("unmapped-child", "thread-product", "subagent", "running", "hidden-run"),))
    graph = project_graph(team, bindings=bindings, observations=observations, native_inventory=hidden)
    assert graph["all_defined_results_available"] and not graph["all_native_results_available"]
    assert graph["native_inventory_coverage"]["unknown_native_thread_ids"] == ["unmapped-child"]
    missing = replace(good, threads=tuple(row for row in good.threads if row.thread_id != "thread-ui"))
    coverage = inventory_coverage(team, {item.role_id: item for item in bindings}, observations, missing)
    assert coverage["missing_native_thread_ids"] == ["thread-ui"]
    root = binding(team, "coo")
    with pytest.raises(TeamError, match="TEAM_NATIVE_CHILD_INVENTORY_REQUIRED"):
        prepare_delegation(team, parent_role_id="coo", child_role_id="product", bindings=(root,),
                           observations={"coo": snapshot(root)})
    one = inventory_fixture(team, (root,))
    one_hidden = replace(one, threads=one.threads + (
        InventoryThread("unmapped-child", "thread-coo", "subagent", "running", "hidden-run"),))
    with pytest.raises(TeamError, match="TEAM_NATIVE_CHILD_INVENTORY_UNQUALIFIED"):
        prepare_delegation(team, parent_role_id="coo", child_role_id="product", bindings=(root,),
                           observations={"coo": snapshot(root)}, native_inventory=one_hidden)


@pytest.mark.parametrize("mutation,reason", [
    (lambda inv: replace(inv, project_id="other"), "scope_mismatch"),
    (lambda inv: replace(inv, environment_id="other"), "scope_mismatch"),
    (lambda inv: replace(inv, observed_at=(datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()), "stale_inventory"),
    (lambda inv: replace(inv, threads=()), "root_missing"),
    (lambda inv: replace(inv, threads=(replace(inv.threads[0], latest_run_id="new-run"),)), "inventory_observation_drift"),
    (lambda inv: replace(inv, threads=(replace(inv.threads[0], status="waiting"),)), "inventory_observation_drift"),
])
def test_coverage_requires_current_scope_and_consistent_original_run(mutation, reason):
    team = team_fixture()
    root = binding(team, "coo")
    result = inventory_coverage(team, {"coo": root}, {"coo": snapshot(root)},
                                mutation(inventory_fixture(team, (root,))))
    assert not result["qualified"] and result["state"] == reason


@pytest.mark.parametrize("left,right", [("app/UI", "app/ui"),
                                         ("app/caf\u00e9", "app/cafe\u0301/deep")])
def test_shared_mac_checkout_case_and_unicode_aliases_cannot_evade_collision_checks(left, right):
    team = changed_role(team_fixture(), "ui", allowed_write_paths=(left,))
    with pytest.raises(TeamError, match="TEAM_SHARED_CHECKOUT_COLLISION"):
        changed_role(team, "api", allowed_write_paths=(right,))


def test_path_collision_normalization_never_widens_child_authority():
    with pytest.raises(TeamError, match="TEAM_PATH_SCOPE_ESCALATION"):
        changed_role(team_fixture(), "ui", allowed_write_paths=("APP/ui",))


def test_unbound_uncertain_original_effect_conserves_planning_headroom():
    team = replace(team_fixture(), requested_max_live_agents=3)
    root, director = binding(team, "coo"), binding(team, "product")
    bindings = (root, director)
    observations = {item.role_id: snapshot(item) for item in bindings}
    with pytest.raises(TeamError, match="TEAM_REQUESTED_AGENT_CEILING_REACHED"):
        prepare_delegation(team, parent_role_id="product", child_role_id="api",
                           bindings=bindings, observations=observations,
                           native_inventory=inventory_fixture(team, bindings, observations),
                           uncertain_role_ids=("quality",))
