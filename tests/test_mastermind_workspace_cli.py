from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.name", "Workspace CLI Test")
    _git(source, "config", "user.email", "workspace-cli@example.invalid")
    (source / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(source, "add", "README.md")
    _git(source, "commit", "-qm", "fixture")
    return source, _git(source, "rev-parse", "HEAD")


def _run_cli(source: Path, root: Path, *args: str) -> tuple[int, dict[str, object]]:
    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["MASTERMIND_SOURCE_REPO"] = str(source)
    env["MASTERMIND_AGENT_WORKSPACE_ROOT"] = str(root)
    completed = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "mastermind_workspace.py"), *args],
        cwd=repo_root,
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    payload = json.loads(completed.stdout or completed.stderr)
    return completed.returncode, payload


def test_cli_acquires_reuses_and_releases_without_model_selected_path(tmp_path: Path):
    source, base_sha = _repository(tmp_path)
    root = tmp_path / "workspaces"

    code, acquired = _run_cli(
        source, root, "acquire", "--operation-id", "cli-op-001", "--base-sha", base_sha,
    )
    assert code == 0
    assert acquired["effect"] == "APPLIED"
    receipt = acquired["receipt"]
    assert receipt["workspace_path"] == str(root / "web" / "cli-op-001")
    assert receipt["branch"] == "sol/web-cli-op-001"
    assert receipt["reused"] is False

    code, reused = _run_cli(
        source, root, "acquire", "--operation-id", "cli-op-001", "--base-sha", base_sha,
    )
    assert code == 0
    assert reused["effect"] == "NOT_APPLIED"
    assert reused["receipt"]["reused"] is True

    code, released = _run_cli(source, root, "release", "--operation-id", "cli-op-001")
    assert code == 0
    assert released["effect"] == "APPLIED"
    assert released["receipt"]["state"] == "REMOVED"
    assert not (root / "web" / "cli-op-001").exists()


def test_cli_release_preserves_dirty_workspace(tmp_path: Path):
    source, base_sha = _repository(tmp_path)
    root = tmp_path / "workspaces"
    code, acquired = _run_cli(
        source, root, "acquire", "--operation-id", "cli-op-002", "--base-sha", base_sha,
    )
    assert code == 0
    workspace = Path(acquired["receipt"]["workspace_path"])
    (workspace / "local.txt").write_text("dirty\n", encoding="utf-8")

    code, released = _run_cli(source, root, "release", "--operation-id", "cli-op-002")
    assert code == 0
    assert released["effect"] == "NOT_APPLIED"
    assert released["receipt"]["state"] == "PRESERVED_DIRTY"
    assert workspace.exists()


def test_cli_census_reports_source_and_managed_workspace(tmp_path: Path):
    source, base_sha = _repository(tmp_path)
    root = tmp_path / "workspaces"
    code, _ = _run_cli(
        source, root, "acquire", "--operation-id", "cli-op-003", "--base-sha", base_sha,
    )
    assert code == 0

    code, census = _run_cli(source, root, "census")
    assert code == 0
    assert census["effect"] == "NOT_APPLIED"
    states = {entry["path"]: entry["state"] for entry in census["receipt"]["worktrees"]}
    assert states[str(source.resolve())] == "SOURCE_CHECKOUT"
    assert states[str((root / "web" / "cli-op-003").resolve())] == "MANAGED_ACTIVE"
