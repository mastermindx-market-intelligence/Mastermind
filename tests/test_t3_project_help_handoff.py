"""Reached T3 source-plan guidance; authentication remains with the COO reader."""
import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from common import coo_project_help_contract as help_wire
from integrations.session_bridge.project_task_context import load_context
from integrations.session_bridge.t3_project_team import ProjectTeamClient, TeamError
from integrations.session_bridge.t3_project_team_cli import ProjectPlanInput, launch_request, main
from integrations.session_bridge.t3_web_client import CliResult, NativeEffectUnknown, T3CliClient
from scripts.build_t3_project_team import archive_bytes
from tests.test_t3_project_team import team_fixture


def plan_fixture(tmp_path):
    value = {
        "schema": "mastermind.project_task_tree.v1", "workstream": "WS:T3-HELP",
        "objective": "Deliver the original project with qualified help",
        "requirements": [{"id": "R1", "text": "Use the current owner and exact plan"}],
        "allowed_paths": ["app", "tests"], "non_goals": ["No new authority"],
        "tasks": [{"id": "P1.T1", "title": "Prove the consumer", "requirement_ids": ["R1"],
                   "depends_on": [], "state": "pending", "evidence": [],
                   "acceptance": [{"id": "A1", "text": "Actual authenticated read matches this plan"}]}],
    }
    raw = ("# T3 project plan\n\n```mastermind-plan\n" + json.dumps(value) + "\n```\n").encode()
    path = "docs/plans/t3-help.md"
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    context = load_context(workspace_root=tmp_path, relative_path=path,
                           workstream="WS:T3-HELP", expected_sha256=digest)
    source_ref = "https://github.com/mastermindx-market-intelligence/Mastermind/blob/" + "a" * 40 + "/" + path
    return context, source_ref


def bound_team(source_ref):
    team = team_fixture()
    return replace(team, mission=replace(team.mission, source_ref=source_ref))


def guidance_from_message(message):
    document = json.JSONDecoder().raw_decode(message.split("\n", 1)[1])[0]
    return json.loads(document["objective"].rsplit("\n", 1)[1])["project_help"]


def plan_input(tmp_path, context, source_ref):
    return ProjectPlanInput(str(tmp_path), context["source_path"], context["workstream"],
                            source_ref, context["source_sha256"])


def cli_input(tmp_path):
    context, source_ref = plan_fixture(tmp_path)
    definition = tmp_path / "team.json"
    definition.write_text(json.dumps(bound_team(source_ref).document()))
    args = ["launch-request", str(definition), "--project-id", "native-project",
            "--request-id", "project-help", "--environment-id", "native-environment",
            *plan_input(tmp_path, context, source_ref).arguments()]
    return context, source_ref, definition, args


def test_actual_root_handoff_carries_only_exact_read_selector(tmp_path):
    context, source_ref = plan_fixture(tmp_path)
    brief = bound_team(source_ref).root_handoff(
        request_id="project-help", project_id="actual-t3-project",
        project_context=context, project_source_ref=source_ref)
    guidance = json.loads(brief.objective.rsplit("\n", 1)[1])["project_help"]
    assert guidance["tool"] == help_wire.TOOL
    assert guidance["catalogue"] == help_wire.CATALOGUE
    assert guidance["arguments"] == {"work_ref": "WS:T3-HELP"}
    assert guidance["read_state"] == "NOT_READ"
    assert guidance["execution_authority"] is False
    assert guidance["native_origin_attested"] is False
    assert "root_job_id" not in guidance
    assert help_wire.context_matches_source_plan(context, guidance["source_plan"], source_ref=source_ref)
    assert "existing authenticated COO MCP connection" in brief.objective
    assert "unavailable" in brief.objective


def test_legacy_omission_keeps_original_bytes():
    team = team_fixture()
    brief = team.root_handoff(request_id="project-help", project_id="actual-t3-project")
    explicit = team.root_handoff(request_id="project-help", project_id="actual-t3-project",
                                 project_context=None, project_source_ref=None)
    assert brief.render() == explicit.render()
    assert "project_help" not in brief.objective
    # Golden is derived from exact incumbent blob4789456033fe6a5c5452a5b6dc08d5fce946075c.
    assert hashlib.sha256(brief.render().encode()).hexdigest() == "321e07c9914139ec591d6d0130a5ccd82684381d8a0c18ce3ef730da93494385"


def test_different_team_source_cannot_receive_foreign_plan_guidance(tmp_path):
    context, source_ref = plan_fixture(tmp_path)
    with pytest.raises(TeamError, match="TEAM_PROJECT_HELP_MISSION_SOURCE_DIFFERS"):
        team_fixture().root_handoff(request_id="project-help", project_id="p",
                                   project_context=context, project_source_ref=source_ref)


@pytest.mark.parametrize("field,value", [
    ("schema", "forged"), ("execution_authority", True), ("workstream", "caller-root"),
    ("source_path", "docs/foreign.md"), ("source_sha256", "invalid"),
    ("contract_sha256", "invalid"),
])
def test_invalid_parser_or_plan_binding_is_refused(tmp_path, field, value):
    context, source_ref = plan_fixture(tmp_path)
    context[field] = value
    with pytest.raises(TeamError, match="TEAM_PROJECT_HELP_SOURCE_INVALID"):
        bound_team(source_ref).root_handoff(request_id="project-help", project_id="p",
                                            project_context=context, project_source_ref=source_ref)


def test_source_reference_is_not_accepted_from_its_path_alone(tmp_path):
    context, source_ref = plan_fixture(tmp_path)
    foreign = source_ref.replace("mastermindx-market-intelligence/Mastermind", "example/project")
    with pytest.raises(TeamError, match="TEAM_PROJECT_HELP_SOURCE_INVALID"):
        bound_team(foreign).root_handoff(request_id="project-help", project_id="p",
                                         project_context=context, project_source_ref=foreign)


def test_actual_client_launch_keeps_original_receipt_and_one_dispatch(tmp_path):
    context, source_ref = plan_fixture(tmp_path)
    team = bound_team(source_ref)
    calls = []

    async def runner(invocation):
        calls.append(invocation)
        return CliResult(0, json.dumps({"projectId": "native-project", "threadId": "original-thread",
                                       "runId": "original-run"}))

    client = ProjectTeamClient(T3CliClient("/authorized/t3", runner), environment_id="native-environment")
    bound = asyncio.run(client.launch(team, project_id="native-project", request_id="project-help",
                                    project_context=context, project_source_ref=source_ref))
    assert len(calls) == 1
    guidance = guidance_from_message(calls[0].stdin)
    assert guidance["read_state"] == "NOT_READ"
    assert guidance["arguments"] == {"work_ref": context["workstream"]}
    assert bound.receipt.thread_id == "original-thread" and bound.receipt.run_id == "original-run"
    assert bound.receipt.brief_sha256 == team.root_handoff(
        project_id="native-project", request_id="project-help",
        project_context=context, project_source_ref=source_ref).fingerprint


def test_bound_guidance_does_not_retry_uncertain_original_launch(tmp_path):
    context, source_ref = plan_fixture(tmp_path)
    calls = []

    async def runner(invocation):
        calls.append(invocation)
        return CliResult(1, "", "private transport failure")

    client = ProjectTeamClient(T3CliClient("/authorized/t3", runner), environment_id="e")
    with pytest.raises(NativeEffectUnknown):
        asyncio.run(client.launch(bound_team(source_ref), project_id="p", request_id="project-help",
                                  project_context=context, project_source_ref=source_ref))
    assert len(calls) == 1


def test_cli_reads_actual_plan_and_prepares_same_immutable_request(tmp_path, capsys, monkeypatch):
    context, source_ref, _, args = cli_input(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("The source compiler must not call a network or native process")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["effect_state"] == "NOT_DISPATCHED"
    guidance = guidance_from_message(first["arguments"]["message"])
    assert help_wire.context_matches_source_plan(context, guidance["source_plan"], source_ref=source_ref)
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out) == first
    direct = launch_request(bound_team(source_ref), project_id="native-project", request_id="project-help",
                            environment_id="native-environment", project_context=context,
                            project_source_ref=source_ref)
    assert first == direct


def test_cli_refuses_partial_source_selection(tmp_path, capsys):
    _, _, definition, _ = cli_input(tmp_path)
    assert main(["check", str(definition), "--project-plan", "docs/plans/t3-help.md"]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "error": "TEAM_PROJECT_HELP_PLAN_SELECTION_INCOMPLETE", "effect_state": "NOT_DISPATCHED"}


def test_cli_stale_source_is_unavailable_before_native_preparation(tmp_path, capsys):
    context, _, _, args = cli_input(tmp_path)
    with (tmp_path / context["source_path"]).open("ab") as stream:
        stream.write(b"\nChanged after source selection.\n")
    assert main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["error"] == "TEAM_PROJECT_HELP_SOURCE_UNAVAILABLE"
    assert result["effect_state"] == "NOT_DISPATCHED"
    assert "Changed after source selection" not in json.dumps(result)


def test_cli_refuses_source_symlink(tmp_path, capsys):
    context, _, _, args = cli_input(tmp_path)
    source = tmp_path / context["source_path"]
    saved = source.with_suffix(".saved")
    source.rename(saved)
    source.symlink_to(saved)
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["effect_state"] == "NOT_DISPATCHED"


def test_native_action_retains_plan_selection_on_manual_prepare_only(tmp_path, capsys):
    context, source_ref, definition, _ = cli_input(tmp_path)
    assert main(["actions", str(definition), "--launcher", "/qualified/team.pyz",
                 "--project-id", "p", "--request-id", "help", "--environment-id", "e",
                 *plan_input(tmp_path, context, source_ref).arguments()]) == 0
    actions = json.loads(capsys.readouterr().out)["scripts"]
    assert all(not item["runOnWorktreeCreate"] and not item["runOnSettle"] for item in actions)
    check, graph, launch = [shlex.split(item["command"]) for item in actions]
    assert "--project-plan" in check and "--project-plan" in launch
    assert "--project-plan" not in graph
    assert launch[launch.index("--plan-source-ref") + 1] == source_ref


def test_packaged_isolated_consumer_includes_pure_help_dependency_closure(tmp_path):
    context, source_ref, _, args = cli_input(tmp_path)
    payload, _ = archive_bytes(Path(__file__).resolve().parents[1])
    app = tmp_path / "team.pyz"
    app.write_bytes(payload)
    completed = subprocess.run([sys.executable, "-I", str(app), *args],
                               cwd=tmp_path, capture_output=True, text=True, timeout=20, check=True)
    emitted = json.loads(completed.stdout)
    guidance = guidance_from_message(emitted["arguments"]["message"])
    assert help_wire.context_matches_source_plan(context, guidance["source_plan"], source_ref=source_ref)
    assert guidance["read_state"] == "NOT_READ"
