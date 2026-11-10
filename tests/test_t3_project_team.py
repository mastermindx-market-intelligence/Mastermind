"""Pure graph and real incumbent-client composition; no model/network calls."""
import asyncio
import copy
import json
from dataclasses import replace

import pytest

from integrations.session_bridge.t3_mission_brief import MissionBrief, Phase
from integrations.session_bridge.t3_project_team import (
    DependencyEvidence, ProjectTeam, ProjectTeamClient, RoleBinding, TeamError,
    TeamRole, bind_delegation, parse_team, prepare_delegation, project_graph,
    team_from_document, validate_bindings, validate_dependency_evidence,
)
from integrations.session_bridge.t3_web_client import (
    CliResult, NativeEffectUnknown, T3CliClient, ThreadReceipt,
)

BASE = "a" * 40
SOURCE = f"https://github.com/example/project/blob/{BASE}/docs/project.md"


def team_fixture():
    mission = MissionBrief(
        "project-team", "Deliver the original product and its verified consumer journey.", SOURCE, BASE,
        (Phase("build", "Build the application", ("Actual feature works",)),
         Phase("verify", "Verify the consumer", ("Real consumer proof, not merely green tests",))),
        ("The complete original journey works", "Every returned child is reviewed"),
        ("app", "tests"), ("No new scheduler or provider selection",),
        ("Stop on actual permission denial or unknown effects",), "agentos:WS:PROJECT",
        "runtime:existing-root-envelope",
    )
    roles = (
        TeamRole("coo", "coo", None, "Own the whole outcome", ("build", "verify"), ("app", "tests")),
        TeamRole("product", "director", "coo", "Deliver application", ("build",), ("app",)),
        TeamRole("ui", "worker", "product", "Build the interface", ("build",), ("app/ui",)),
        TeamRole("api", "worker", "product", "Build the API", ("build",), ("app/api",)),
        TeamRole("quality", "director", "coo", "Verify original journey", ("verify",), ("tests",), ("product",)),
        TeamRole("check", "worker", "quality", "Exercise the real consumer", ("verify",), ("tests",), native_role="test"),
    )
    return ProjectTeam(mission, roles)


def binding(team, role_id):
    role = team.by_id[role_id]
    return RoleBinding(role_id, "test-environment", "thread-coo",
                       "thread-" + role.parent_id if role.parent_id else None,
                       "task-" + role_id if role.parent_id else None,
                       ThreadReceipt("request-" + role_id, "test-project", "thread-" + role_id,
                                     "run-" + role_id, "b" * 64), team.fingerprint)


def snapshot(item, status="running", *, run=None, pending=0):
    current = run or item.receipt.run_id
    return {"thread": {"threadId": item.receipt.thread_id,
                        "projectId": item.receipt.project_id,
                        "parentThreadId": item.parent_thread_id,
                        "relationshipToParent": "subagent" if item.parent_thread_id else None,
                        "latestRunId": current,
                        "activeRunId": current if status == "running" else None,
                        "pendingRequestCount": pending, "status": status},
            "messages": [{"role": "assistant", "runId": current, "text": "Original result"}]}


def changed_role(team, role_id, **updates):
    return replace(team, roles=tuple(replace(role, **updates) if role.role_id == role_id else role
                                     for role in team.roles))


def offer_fixture():
    team = team_fixture()
    root = binding(team, "coo")
    offer = prepare_delegation(team, parent_role_id="coo", child_role_id="product", bindings=(root,),
                               observations={"coo": snapshot(root)})
    return team, root, offer


def test_roundtrip_preserves_full_graph_scope_and_fingerprint():
    team = team_fixture()
    actual = parse_team(json.dumps(team.document()).encode())
    assert actual == team
    assert actual.fingerprint == team.fingerprint
    brief = team.root_handoff(request_id="project-launch", project_id="test-project")
    for role in team.roles:
        assert role.objective in brief.objective
        for path in role.allowed_write_paths:
            assert path in brief.objective
    assert all(check in brief.objective for phase in team.mission.phases for check in phase.checks)
    assert brief.worktree_base == BASE
    assert brief.acceptance_checks == team.mission.done_when


@pytest.mark.parametrize("mutation,error", [
    (lambda t: replace(t, roles=t.roles + (t.roles[0],)), "TEAM_DUPLICATE_ROLE"),
    (lambda t: changed_role(t, "product", parent_id="missing"), "TEAM_PARENT_INVALID"),
    (lambda t: changed_role(t, "product", parent_id="ui"), "TEAM_WORKER_CANNOT_DELEGATE"),
    (lambda t: changed_role(t, "coo", phase_ids=("build",)), "TEAM_COO_SCOPE_INCOMPLETE"),
    (lambda t: changed_role(t, "ui", phase_ids=("verify",)), "TEAM_PHASE_SCOPE_ESCALATION"),
    (lambda t: changed_role(t, "ui", allowed_write_paths=("tests",)), "TEAM_PATH_SCOPE_ESCALATION"),
    (lambda t: changed_role(t, "ui", allowed_write_paths=("application",)), "TEAM_PATH_SCOPE_ESCALATION"),
    (lambda t: changed_role(t, "api", allowed_write_paths=("app/ui/deep",)), "TEAM_SHARED_CHECKOUT_COLLISION"),
    (lambda t: changed_role(t, "ui", depends_on=("product",)), "TEAM_COMPLETION_DEPENDENCY_CYCLE"),
    (lambda t: changed_role(t, "product", depends_on=("check",)), "TEAM_COMPLETION_DEPENDENCY_CYCLE"),
    (lambda t: replace(t, requested_max_depth=2), "TEAM_DEPTH_EXCEEDED"),
    (lambda t: replace(t, requested_max_live_agents=True), "TEAM_AGENT_CEILING_INVALID"),
])
def test_rejects_invalid_hierarchy_scope_deadlocks_and_parallel_writers(mutation, error):
    with pytest.raises(TeamError, match=error):
        mutation(team_fixture())


def test_same_checkout_serialized_writers_are_allowed_without_scope_expansion():
    team = team_fixture()
    serialized = changed_role(team, "api", allowed_write_paths=("app/ui",), depends_on=("ui",))
    assert serialized.launch_dependencies("api") == {"ui"}


def test_each_director_retains_its_own_phase_coverage():
    team = team_fixture()
    roles = tuple(replace(role, phase_ids=("build", "verify"), allowed_write_paths=("app", "tests"))
                  if role.role_id == "product" else role for role in team.roles)
    with pytest.raises(TeamError, match="TEAM_DIRECTOR_COVERAGE_INCOMPLETE"):
        replace(team, roles=roles)


@pytest.mark.parametrize("raw", [b"{}", b"[]", b'{"schema":1,"schema":2}', b'{"a":NaN}',
                                  b'\xff', b'x' * 131073, b'{"a":[[['])
def test_parser_rejects_malformed_oversized_and_duplicate_documents(raw):
    with pytest.raises(TeamError):
        parse_team(raw)


@pytest.mark.parametrize("field,value", [("kind", []), ("phase_ids", [{}]), ("native_role", {}),
                                         ("allowed_write_paths", ["../escape"]),
                                         ("objective", "Bearer " + "x" * 40)])
def test_parser_fails_closed_on_untrusted_role_shapes(field, value):
    doc = team_fixture().document()
    doc["roles"][0][field] = value
    with pytest.raises(TeamError):
        parse_team(json.dumps(doc).encode())


def test_delegation_uses_native_tool_contract_and_original_root_without_provider_overrides():
    team, root, offer = offer_fixture()
    args = offer.native_arguments()
    assert set(args) == {"task", "title", "role", "mode", "clientRequestId", "isolation"}
    assert args["role"] == "general" and args["mode"] == "async"
    assert offer.root_thread_id == root.receipt.thread_id
    assert offer.parent_run_id == root.receipt.run_id
    for text in (*team.mission.done_when, *team.mission.stop_conditions, *team.mission.non_goals):
        assert text in args["task"]
    for child in team.children("product"):
        assert child.objective in args["task"]
    assert "not an admission" in args["task"]
    assert prepare_delegation(team, parent_role_id="coo", child_role_id="product", bindings=(root,),
                              observations={"coo": snapshot(root)}).fingerprint == offer.fingerprint


@pytest.mark.parametrize("change,error", [
    (lambda t, r: {"uncertain_role_ids": ("coo",)}, "TEAM_ORIGINAL_EFFECT_UNCERTAIN"),
    (lambda t, r: {"uncertain_role_ids": ("product",)}, "TEAM_ORIGINAL_EFFECT_UNCERTAIN"),
    (lambda t, r: {"observations": {}}, "TEAM_EXACT_ACTIVE_PARENT_REQUIRED"),
    (lambda t, r: {"observations": {"coo": snapshot(r, "completed")}}, "TEAM_EXACT_ACTIVE_PARENT_REQUIRED"),
    (lambda t, r: {"observations": {"coo": snapshot(r, pending=1)}}, "TEAM_EXACT_ACTIVE_PARENT_REQUIRED"),
    (lambda t, r: {"observations": {"coo": snapshot(r, run="other-run")}}, "TEAM_EXACT_ACTIVE_PARENT_REQUIRED"),
    (lambda t, r: {"child_role_id": "ui"}, "TEAM_IMMEDIATE_PARENT_REQUIRED"),
    (lambda t, r: {"child_role_id": "quality"}, "TEAM_DEPENDENCY_EVIDENCE_REQUIRED"),
    (lambda t, r: {"bindings": (r, binding(t, "product"))}, "TEAM_CHILD_ALREADY_BOUND"),
])
def test_delegation_never_replays_or_bypasses_parent_or_dependency_gate(change, error):
    team, root, _ = offer_fixture()
    kwargs = dict(parent_role_id="coo", child_role_id="product", bindings=(root,),
                  observations={"coo": snapshot(root)})
    kwargs.update(change(team, root))
    with pytest.raises(TeamError, match=error):
        prepare_delegation(team, **kwargs)


def test_capacity_unknown_and_requested_ceiling_hold_offer_without_creating_reservation():
    team = replace(team_fixture(), requested_max_live_agents=1)
    root = binding(team, "coo")
    with pytest.raises(TeamError, match="TEAM_REQUESTED_AGENT_CEILING_REACHED"):
        prepare_delegation(team, parent_role_id="coo", child_role_id="product", bindings=(root,),
                           observations={"coo": snapshot(root)})
    team = team_fixture()
    root, prod = binding(team, "coo"), binding(team, "product")
    with pytest.raises(TeamError, match="TEAM_NATIVE_CAPACITY_UNKNOWN"):
        prepare_delegation(team, parent_role_id="product", child_role_id="ui", bindings=(root, prod),
                           observations={"product": snapshot(prod)})


def test_dependency_evidence_requires_parent_review_matching_revision_and_complete_subtree():
    team = team_fixture()
    evidence = tuple(DependencyEvidence(key, team.by_id[key].parent_id, team.fingerprint, SOURCE)
                     for key in ("ui", "api", "product"))
    assert validate_dependency_evidence(team, evidence) == {"ui", "api", "product"}
    with pytest.raises(TeamError, match="TEAM_EVIDENCE_DEPENDENCIES_INCOMPLETE"):
        validate_dependency_evidence(team, evidence[-1:])
    with pytest.raises(TeamError, match="TEAM_PARENT_REVIEW_REQUIRED"):
        validate_dependency_evidence(team, (replace(evidence[0], accepted_by_role_id="ui"),))
    with pytest.raises(TeamError, match="TEAM_EVIDENCE_STALE_REVISION"):
        validate_dependency_evidence(team, (replace(evidence[0], team_sha256="c" * 64),))
    root = binding(team, "coo")
    offer = prepare_delegation(team, parent_role_id="coo", child_role_id="quality", bindings=(root,),
                               observations={"coo": snapshot(root)}, evidence=evidence)
    assert offer.role_id == "quality"


def test_native_delegation_return_retains_ids_and_refuses_duplicate_thread_or_task():
    team, root, offer = offer_fixture()
    result = {"taskId": "task-product", "childThreadId": "thread-product", "childRunId": "run-product",
              "childNodeId": "node-product", "status": "running"}
    child = bind_delegation(team, offer, result, (root,))
    assert child.parent_thread_id == root.receipt.thread_id
    assert child.root_thread_id == root.receipt.thread_id
    assert child.task_id == result["taskId"] and child.receipt.run_id == result["childRunId"]
    with pytest.raises(TeamError, match="TEAM_NATIVE_THREAD_REUSED"):
        bind_delegation(team, offer, {**result, "childThreadId": root.receipt.thread_id}, (root,))
    with pytest.raises(TeamError, match="TEAM_OFFER_ALREADY_BOUND"):
        bind_delegation(team, offer, result, (root, child))
    with pytest.raises(TeamError, match="TEAM_NATIVE_TASK_REUSED"):
        validate_bindings(team, (root, child, replace(binding(team, "ui"), task_id=child.task_id)))


@pytest.mark.parametrize("changes,error", [
    ({"team_sha256": "d" * 64}, "TEAM_BINDING_STALE_REVISION"),
    ({"environment_id": "other"}, "TEAM_BINDING_ROOT_DIFFERS"),
    ({"root_thread_id": "other-root"}, "TEAM_BINDING_ROOT_DIFFERS"),
    ({"parent_thread_id": "wrong-parent"}, "TEAM_BINDING_PARENT_DIFFERS"),
])
def test_bindings_preserve_exact_revision_environment_root_and_immediate_parent(changes, error):
    team = team_fixture()
    with pytest.raises(TeamError, match=error):
        validate_bindings(team, (binding(team, "coo"), replace(binding(team, "product"), **changes)))


def test_root_completion_never_hides_missing_running_or_unknown_children_or_claims_acceptance():
    team = team_fixture()
    bindings = tuple(binding(team, role.role_id) for role in team.roles)
    observations = {item.role_id: snapshot(item, "completed") for item in bindings}
    graph = project_graph(team, bindings=bindings, observations=observations)
    assert graph["all_native_results_available"] is True
    assert graph["acceptance"] == "not_evaluated" and graph["execution_authorized"] is False
    assert all(node["acceptance"] == "not_evaluated" for node in graph["nodes"])
    for bad in (None, snapshot(bindings[2], "running"), snapshot(bindings[2], "completed", pending=1),
                snapshot(bindings[2], "completed", run="newer-run")):
        observations["ui"] = bad
        assert project_graph(team, bindings=bindings, observations=observations)["all_native_results_available"] is False
    observations["ui"] = snapshot(bindings[2], "completed")
    assert not project_graph(team, bindings=bindings, observations=observations,
                             uncertain_role_ids=("ui",))["all_native_results_available"]
    assert not project_graph(team, bindings=(bindings[0],),
                             observations={"coo": observations["coo"]})["all_native_results_available"]


def test_wrong_native_lineage_is_unavailable_not_a_successful_result():
    team = team_fixture()
    root = binding(team, "coo")
    observed = snapshot(root, "completed")
    observed["thread"]["parentThreadId"] = "different-parent"
    node = project_graph(team, bindings=(root,), observations={"coo": observed})["nodes"][0]
    assert node["native_state"] == "observation_unavailable"
    assert not node["original_result_available"]


def test_incumbent_client_launches_once_with_full_scope_native_worktree_and_no_new_router():
    team = team_fixture()
    invocations = []

    def runner(invocation):
        invocations.append(invocation)
        return CliResult(0, json.dumps({"projectId": "test-project", "threadId": "thread-coo", "runId": "run-coo"}))

    client = ProjectTeamClient(T3CliClient("/authorized/t3", runner), environment_id="test-environment")
    root = asyncio.run(client.launch(team, project_id="test-project", request_id="launch-once"))
    assert len(invocations) == 1
    argv = invocations[0].argv
    assert argv[:3] == ("/authorized/t3", "thread", "start")
    assert argv[argv.index("--worktree") + 1] == BASE
    assert "--provider" not in argv and "--model" not in argv
    assert root.root_thread_id == root.receipt.thread_id
    assert root.team_sha256 == team.fingerprint
    assert all(text in invocations[0].stdin for text in team.mission.done_when)
    assert all(role.objective in invocations[0].stdin for role in team.roles)


@pytest.mark.parametrize("response", [CliResult(1, "", "secret diagnostic"), CliResult(0, "not-json"),
                                      CliResult(0, '{"projectId":"wrong"}')])
def test_uncertain_native_launch_is_never_retried_or_rehomed(response):
    calls = []

    def runner(invocation):
        calls.append(invocation)
        return response

    client = ProjectTeamClient(T3CliClient("/authorized/t3", runner), environment_id="test-environment")
    with pytest.raises(NativeEffectUnknown) as error:
        asyncio.run(client.launch(team_fixture(), project_id="test-project", request_id="one-effect"))
    assert len(calls) == 1 and "secret" not in str(error.value)


def test_native_read_failure_stays_unavailable_and_observation_never_mutates():
    team = team_fixture()
    bindings = (binding(team, "coo"), binding(team, "product"))
    calls = []

    def runner(invocation):
        calls.append(invocation)
        return (CliResult(0, json.dumps(snapshot(bindings[0], "completed")))
                if invocation.argv[3] == "thread-coo" else CliResult(1, ""))

    client = ProjectTeamClient(T3CliClient("/authorized/t3", runner), environment_id="test-environment")
    graph = asyncio.run(client.observe(team, bindings))
    assert all(call.argv[2] == "show" and call.stdin is None for call in calls)
    assert graph["nodes"][1]["native_state"] == "observation_unavailable"
    assert not graph["all_native_results_available"]


def isolated_team():
    team = team_fixture()
    roles = tuple(replace(role, isolation="worktree") if role.kind == "director" else role
                  for role in team.roles)
    return replace(team, roles=roles)


def test_native_worktree_partition_allows_separate_branch_writers_but_not_shared_leaf_collisions():
    team = isolated_team()
    assert team.workspace_group("coo") == "coo"
    assert team.workspace_group("ui") == "product"
    assert team.workspace_group("check") == "quality"
    roles = tuple(replace(role, allowed_write_paths=("app",), depends_on=())
                  if role.role_id == "quality" else
                  replace(role, allowed_write_paths=("app/ui",)) if role.role_id == "check" else role
                  for role in team.roles)
    parallel = replace(team, roles=roles)
    assert parallel.by_id["quality"].isolation == "worktree"
    with pytest.raises(TeamError, match="TEAM_SHARED_CHECKOUT_COLLISION"):
        changed_role(parallel, "api", allowed_write_paths=("app/ui",))


def test_native_worktree_offer_and_followup_require_observed_workspace_partition():
    team = isolated_team()
    root, director = binding(team, "coo"), binding(team, "product")
    observations = {"coo": snapshot(root), "product": snapshot(director)}
    observations["coo"]["thread"]["worktreePath"] = "/native/root"
    offer = prepare_delegation(team, parent_role_id="coo", child_role_id="product", bindings=(root,),
                               observations={"coo": observations["coo"]})
    assert offer.native_arguments()["isolation"] == "worktree"
    for path in (None, "/native/root"):
        observations["product"]["thread"]["worktreePath"] = path
        with pytest.raises(TeamError, match="TEAM_NATIVE_WORKSPACE_UNQUALIFIED"):
            prepare_delegation(team, parent_role_id="product", child_role_id="ui", bindings=(root, director),
                               observations=observations)
    observations["product"]["thread"]["worktreePath"] = "/native/product"
    leaf = prepare_delegation(team, parent_role_id="product", child_role_id="ui", bindings=(root, director),
                              observations=observations)
    assert leaf.native_arguments()["isolation"] == "shared"


def test_claimed_worktree_isolation_is_not_accepted_as_actual_workspace_evidence():
    team = isolated_team()
    bindings = tuple(binding(team, role.role_id) for role in team.roles)
    observations = {item.role_id: snapshot(item, "completed") for item in bindings}
    graph = project_graph(team, bindings=bindings, observations=observations)
    assert not graph["all_native_results_available"]
    for item in bindings:
        observations[item.role_id]["thread"]["worktreePath"] = "/native/" + team.workspace_group(item.role_id)
    graph = project_graph(team, bindings=bindings, observations=observations)
    assert graph["all_native_results_available"]
    assert graph["nodes"][1]["workspace_evidence"]["state"] == "distinct_path_observed"
    observations["quality"]["thread"]["worktreePath"] = "/native/product"
    graph = project_graph(team, bindings=bindings, observations=observations)
    assert not graph["all_native_results_available"]
    assert graph["nodes"][4]["workspace_evidence"]["state"] == "contradicted"


def test_large_team_uses_immutable_progressive_disclosure_without_silent_scope_truncation():
    small = team_fixture()
    roles = (small.root,) + tuple(
        TeamRole(f"worker-{index}", "worker", "coo", f"Slice {index}: " + "Detailed scope. " * 30,
                 ("build", "verify"), (f"app/slice-{index}",)) for index in range(40))
    team = replace(small, roles=roles)
    with pytest.raises(TeamError, match="TEAM_ROOT_BRIEF_TOO_LARGE_USE_DEFINITION_REF"):
        team.root_handoff(project_id="project", request_id="large-team")
    reference = f"https://github.com/example/project/blob/{BASE}/docs/team.json"
    brief = team.root_handoff(project_id="project", request_id="large-team", definition_ref=reference)
    assert brief.source_ref == reference
    assert team.fingerprint in brief.objective and '"role_count":41' in brief.objective
    assert all(role.role_id in brief.objective for role in roles[1:])
    assert brief.acceptance_checks == small.mission.done_when
    assert "verify its complete team fingerprint" in brief.objective
    assert len(brief.objective.encode()) <= 8192
    assert len(project_graph(team)["nodes"]) == 41
    with pytest.raises(ValueError):
        team.root_handoff(project_id="project", request_id="large-team",
                          definition_ref="https://github.com/example/project/blob/main/docs/team.json")
