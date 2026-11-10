"""Qualified native continuation returns preserve original receipts and fail closed."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from integrations.session_bridge.t3_project_team import ProjectTeamClient, TeamError, project_graph
from integrations.session_bridge.t3_project_team_cli import main
from integrations.session_bridge.t3_project_team_inventory import InventoryThread
from integrations.session_bridge.t3_project_team_results import (
    NativeSettledResult, qualify_settled_result, read_native_settled_result,
    settled_result_from_document,
)
from integrations.session_bridge.t3_web_client import CliResult, NativeUnavailable, T3CliClient
from tests.test_t3_project_team import binding, inventory_fixture, snapshot, team_fixture


def context(team, item):
    return dict(environment_id=item.environment_id, project_id=item.receipt.project_id,
                thread_id=item.receipt.thread_id, requested_run_id=item.receipt.run_id,
                team_sha256=team.fingerprint)


def native_result(item, result_run="continued-run"):
    return {"threadId": item.receipt.thread_id, "runId": item.receipt.run_id,
            "status": "completed", "timedOut": False,
            "resultRun": {"runId": result_run, "status": "completed"}}


def continued_fixture():
    team = team_fixture()
    bindings = tuple(binding(team, role.role_id) for role in team.roles)
    observations = {item.role_id: snapshot(item, "completed") for item in bindings}
    results = {}
    for item in bindings:
        if team.children(item.role_id):
            current = "continued-" + item.role_id
            observations[item.role_id] = snapshot(item, "completed", run=current)
            results[item.role_id] = qualify_settled_result(native_result(item, current), **context(team, item))
    return team, bindings, observations, results


def test_reads_existing_native_join_once_without_forwarding_or_launching():
    team = team_fixture()
    root = binding(team, "coo")
    calls = []

    async def native(tool, arguments):
        calls.append((tool, arguments))
        return native_result(root)

    result = asyncio.run(read_native_settled_result(native, **context(team, root)))
    assert calls == [("t3_thread_wait", {"threadId": root.receipt.thread_id,
                                       "runId": root.receipt.run_id,
                                       "timeoutMs": 1, "untilDelegatedWorkSettled": True})]
    assert result.requested_run_id == root.receipt.run_id
    assert result.result_run_id == "continued-run" and result.is_fresh()
    assert settled_result_from_document(result.document()) == result
    assert len(result.native_wait_sha256) == 64


@pytest.mark.parametrize("mutation", [
    lambda v: {**v, "threadId": "different-thread"},
    lambda v: {**v, "runId": "unreconciled-restart-run"},
    lambda v: {**v, "status": "failed"},
    lambda v: {**v, "status": "cancelled"},
    lambda v: {**v, "timedOut": 0},
    lambda v: {**v, "timedOut": True},
    lambda v: {**v, "resultRun": None},
    lambda v: {**v, "resultRun": {"runId": "other", "status": "failed"}},
    lambda v: {**v, "resultRun": {"runId": "other", "status": "running"}},
    lambda v: {**v, "resultRun": {"status": "completed"}},
    lambda v: {**v, "next": "Still waiting"},
    lambda v: {key: value for key, value in v.items() if key != "resultRun"},
])
def test_inconsistent_or_unsuccessful_native_returns_never_resolve_a_new_run(mutation):
    team = team_fixture()
    root = binding(team, "coo")
    with pytest.raises((NativeUnavailable, ValueError)):
        qualify_settled_result(mutation(native_result(root)), **context(team, root))


def test_native_pending_is_not_success_and_has_no_retry_or_dispatch():
    team = team_fixture()
    root = binding(team, "coo")
    calls = []

    def native(tool, arguments):
        calls.append(arguments)
        return {"threadId": root.receipt.thread_id, "runId": root.receipt.run_id,
                "status": "completed", "timedOut": True}

    assert asyncio.run(read_native_settled_result(native, **context(team, root))) is None
    assert len(calls) == 1


def test_native_failure_is_sanitized_and_never_retried():
    team = team_fixture()
    root = binding(team, "coo")
    calls = []

    def native(tool, arguments):
        calls.append(tool)
        raise RuntimeError("Bearer DO_NOT_EXPOSE_TRANSPORT_DIAGNOSTICS")

    with pytest.raises(NativeUnavailable) as error:
        asyncio.run(read_native_settled_result(native, **context(team, root)))
    assert len(calls) == 1 and "Bearer" not in str(error.value)


@pytest.mark.parametrize("timeout", [True, 0, -1, 30001, "1"])
def test_invalid_wait_bounds_fail_before_native_call(timeout):
    team = team_fixture()
    root = binding(team, "coo")

    def forbidden(*args):
        pytest.fail("Invalid input reached native tooling")

    with pytest.raises(NativeUnavailable):
        asyncio.run(read_native_settled_result(forbidden, **context(team, root), timeout_ms=timeout))


def test_completed_parent_continuations_roll_up_without_overwriting_original_run():
    team, bindings, observations, results = continued_fixture()
    inventory = inventory_fixture(team, bindings, observations)
    without = project_graph(team, bindings=bindings, observations=observations, native_inventory=inventory)
    assert not without["all_defined_results_available"]
    before = tuple(item.document() for item in bindings)
    graph = project_graph(team, bindings=bindings, observations=observations,
                          native_inventory=inventory, settled_results=results)
    assert graph["all_defined_results_available"] and graph["all_native_results_available"]
    assert graph["acceptance"] == "not_evaluated" and graph["execution_authorized"] is False
    assert tuple(item.document() for item in bindings) == before
    for node in graph["nodes"]:
        assert node["result_available"]
        if node["role_id"] in results:
            assert node["result_provenance"] == "native_settled_return"
            assert node["original_result_available"] is False
            assert node["binding"]["receipt"]["run_id"] == "run-" + node["role_id"]
            assert node["result_run_id"] == "continued-" + node["role_id"]
        else:
            assert node["result_provenance"] == "original_run"
            assert node["original_result_available"]


@pytest.mark.parametrize("updates,state", [
    ({"environment_id": "another-environment"}, "binding_mismatch"),
    ({"project_id": "another-project"}, "binding_mismatch"),
    ({"thread_id": "another-thread"}, "binding_mismatch"),
    ({"requested_run_id": "another-origin"}, "binding_mismatch"),
    ({"team_sha256": "d" * 64}, "binding_mismatch"),
    ({"result_run_id": "later-unrelated-run"}, "result_run_not_current"),
])
def test_qualified_join_cannot_cross_original_binding_or_revision(updates, state):
    team, bindings, observations, results = continued_fixture()
    results["coo"] = replace(results["coo"], **updates)
    graph = project_graph(team, bindings=bindings, observations=observations,
                          native_inventory=inventory_fixture(team, bindings, observations), settled_results=results)
    assert not graph["all_native_results_available"]
    assert graph["nodes"][0]["settled_result_evidence"]["state"] == state


@pytest.mark.parametrize("delta", [-121, 30])
def test_stale_and_future_join_receipts_never_qualify_current_results(delta):
    team, bindings, observations, results = continued_fixture()
    results["coo"] = replace(results["coo"], observed_at=(datetime.now(timezone.utc) + timedelta(seconds=delta)).isoformat())
    graph = project_graph(team, bindings=bindings, observations=observations, settled_results=results)
    assert not graph["all_defined_results_available"]
    assert graph["nodes"][0]["settled_result_evidence"]["state"] == "stale_settled_return"


@pytest.mark.parametrize("update", [
    {"activeRunId": "continued-coo"}, {"pendingRequestCount": 1},
    {"pendingRequestCount": False}, {"status": "running"},
    {"parentThreadId": "different-lineage"},
])
def test_native_settled_return_does_not_override_current_thread_or_lineage(update):
    team, bindings, observations, results = continued_fixture()
    observations["coo"]["thread"].update(update)
    graph = project_graph(team, bindings=bindings, observations=observations, settled_results=results)
    assert not graph["all_defined_results_available"]


def test_settled_return_cannot_hide_missing_results_unknown_effects_or_extra_children():
    team, bindings, observations, results = continued_fixture()
    inventory = inventory_fixture(team, bindings, observations)
    for change in ("no-text", "unknown", "hidden-child"):
        observed = dict(observations)
        uncertain = ()
        inv = inventory
        if change == "no-text":
            observed["coo"] = {**observed["coo"], "messages": []}
        elif change == "unknown":
            uncertain = ("ui",)
        else:
            inv = replace(inv, threads=inv.threads + (
                InventoryThread("hidden-child", "thread-coo", "subagent", "running", "hidden-run"),))
        graph = project_graph(team, bindings=bindings, observations=observed, settled_results=results,
                              native_inventory=inv, uncertain_role_ids=uncertain)
        assert not graph["all_native_results_available"]
    with pytest.raises(TeamError, match="TEAM_SETTLED_RESULTS_INVALID"):
        project_graph(team, bindings=bindings, settled_results={"nonexistent": results["coo"]})


def test_existing_client_observes_continuations_without_sending_or_replacing_receipts():
    team, bindings, observations, results = continued_fixture()
    by_thread = {item.receipt.thread_id: observations[item.role_id] for item in bindings}
    calls = []

    def runner(invocation):
        calls.append(invocation)
        return CliResult(0, json.dumps(by_thread[invocation.argv[3]]))

    client = ProjectTeamClient(T3CliClient("/authorized/t3", runner), environment_id=bindings[0].environment_id)
    graph = asyncio.run(client.observe(team, bindings, native_inventory=inventory_fixture(team, bindings, observations),
                                       settled_results=results))
    assert graph["all_native_results_available"]
    assert len(calls) == len(bindings) and all(call.argv[2] == "show" and call.stdin is None for call in calls)


def test_read_only_cli_accepts_new_and_old_snapshot_shapes(tmp_path, capsys):
    team, bindings, observations, results = continued_fixture()
    definition = tmp_path / "team.json"
    definition.write_text(json.dumps(team.document()))
    path = tmp_path / "owner-export.json"
    doc = {"bindings": [item.document() for item in bindings], "observations": observations,
           "dependency_evidence": [], "uncertain_role_ids": [],
           "native_inventory": inventory_fixture(team, bindings, observations).document()}
    path.write_text(json.dumps(doc))
    assert main(["graph", str(definition), "--snapshot", str(path)]) == 0
    assert not json.loads(capsys.readouterr().out)["all_defined_results_available"]
    doc["settled_results"] = {key: value.document() for key, value in results.items()}
    path.write_text(json.dumps(doc))
    assert main(["graph", str(definition), "--snapshot", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["all_native_results_available"]
    doc["settled_results"]["coo"]["wait_scope"] = "guess_latest_run"
    path.write_text(json.dumps(doc))
    assert main(["graph", str(definition), "--snapshot", str(path)]) == 2
    assert json.loads(capsys.readouterr().out)["effect_state"] == "NOT_DISPATCHED"


def test_team_briefs_follow_native_child_wakes_not_background_command_waits():
    team = team_fixture()
    brief = team.root_handoff(project_id="project", request_id="native-wake")
    assert "Follow delegate_task's native next directive" in brief.objective
    assert "Do not pass delegated task IDs to t3_background_wait" in brief.objective
    assert "Use native parentThreadId for ancestry" in brief.objective
