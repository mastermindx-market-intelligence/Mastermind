"""CLI and native-action preparation never execute an agent or mutate T3."""
import json
from pathlib import Path
import shlex
import subprocess
import sys
import zipfile
from io import BytesIO

import pytest

from integrations.session_bridge.t3_project_team_cli import main, project_actions
from scripts.build_t3_project_team import archive_bytes
from tests.test_t3_project_team import binding, snapshot, team_fixture


@pytest.fixture
def definition(tmp_path):
    path = tmp_path / "team.json"
    path.write_text(json.dumps(team_fixture().document()))
    return path


def test_check_brief_and_portable_graph_are_read_only(definition, capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("A preparation command attempted to launch a subprocess")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert main(["check", str(definition)]) == 0
    check = json.loads(capsys.readouterr().out)
    assert check["valid"] and check["roles"] == 6
    assert not check["execution_authorized"]
    assert main(["brief", str(definition), "--project-id", "native-project", "--request-id", "prepare-one"]) == 0
    assert "whole original DONE_WHEN" in capsys.readouterr().out
    assert main(["graph", str(definition)]) == 0
    graph = json.loads(capsys.readouterr().out)
    assert len(graph["nodes"]) == 6 and len(graph["edges"]) == 6
    assert all(node["native_state"] == "unbound" for node in graph["nodes"])
    assert not graph["all_native_results_available"]


def test_launch_request_preserves_scope_and_native_namespace_without_dispatch(definition, capsys):
    args = ["launch-request", str(definition), "--project-id", "native-project", "--request-id", "prepare-one",
            "--environment-id", "native-environment"]
    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["tool"] == "t3_thread_launch"
    assert first["effect_state"] == "NOT_DISPATCHED"
    payload = first["arguments"]
    assert payload["workspaceStrategy"]["type"] == "worktree"
    assert payload["projectId"] == "native-project"
    assert payload["environmentId"] == "native-environment"
    assert "modelSelection" not in payload and "runtimeMode" not in payload
    assert "fresh CLI/OAuth client" in first["recovery"]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out) == first


def test_delegate_command_uses_existing_owner_snapshot_and_retains_native_parent(definition, tmp_path, capsys):
    team = team_fixture()
    root = binding(team, "coo")
    path = tmp_path / "existing-owner-export.json"
    path.write_text(json.dumps({"bindings": [root.document()], "observations": {"coo": snapshot(root)},
                                "dependency_evidence": [], "uncertain_role_ids": []}))
    assert main(["delegate", str(definition), "--snapshot", str(path),
                 "--parent-role", "coo", "--child-role", "product"]) == 0
    request = json.loads(capsys.readouterr().out)
    assert request["tool"] == "delegate_task" and request["effect_state"] == "NOT_DISPATCHED"
    assert request["offer"]["parent_thread_id"] == root.receipt.thread_id
    assert request["offer"]["parent_run_id"] == root.receipt.run_id


def test_native_project_actions_quote_paths_and_never_autorun_or_dispatch(definition, capsys):
    launcher = "/qualified path/team;not-shell"
    malicious_path = "project ' $(touch should-not-exist).json"
    actions = project_actions(definition=malicious_path, launcher=launcher,
                              project_id="p", request_id="r", environment_id="e")
    assert len(actions["scripts"]) == 3
    for action in actions["scripts"]:
        argv = shlex.split(action["command"])
        assert argv[0] == launcher and argv[2] == malicious_path
        assert not action["runOnWorktreeCreate"] and not action["runOnSettle"]
        assert argv[1] in {"check", "graph", "launch-request"}
    assert main(["actions", str(definition), "--launcher", launcher, "--project-id", "p",
                 "--request-id", "r", "--environment-id", "e"]) == 0
    assert json.loads(capsys.readouterr().out)["scripts"][-1]["name"] == "Prepare COO launch request"


@pytest.mark.parametrize("raw", ["{", '{"schema":1,"schema":2}', '{"x":NaN}', "secret should not leak"])
def test_invalid_input_is_bounded_and_non_sensitive(tmp_path, capsys, raw):
    path = tmp_path / "bad.json"
    path.write_text(raw)
    assert main(["check", str(path)]) == 2
    output = capsys.readouterr().out
    assert "secret should not leak" not in output
    assert json.loads(output)["effect_state"] == "NOT_DISPATCHED"


def test_non_regular_input_and_symlink_are_refused(tmp_path, definition, capsys):
    link = tmp_path / "link.json"
    link.symlink_to(definition)
    assert main(["check", str(link)]) == 2
    assert main(["check", str(tmp_path)]) == 2
    capsys.readouterr()


def test_packaged_fresh_process_runs_without_source_checkout_or_dependencies(definition, tmp_path):
    root = Path(__file__).resolve().parents[1]
    payload, manifest = archive_bytes(root)
    assert manifest["source_status"] == "qualification_only" and manifest["source_revision"] is None
    assert archive_bytes(root)[0] == payload
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        assert len(archive.namelist()) == 8
        assert all(not name.startswith("/") and ".." not in name for name in archive.namelist())
    app = tmp_path / "team.pyz"
    app.write_bytes(payload)
    # Isolated cwd and Python mode ensure this is the packaged consumer, not repo imports.
    result = subprocess.run([sys.executable, "-I", str(app), "check", str(definition)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=20, check=True)
    assert json.loads(result.stdout)["team_sha256"] == team_fixture().fingerprint
