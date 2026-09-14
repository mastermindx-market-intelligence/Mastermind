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


def test_installer_pins_host_root_and_refuses_missing_mount(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    fixture = tmp_path / "installer-repo"
    (fixture / "scripts").mkdir(parents=True)
    (fixture / "control_plane").mkdir()
    for relative in (
        "scripts/install_mastermind_workspace_cli.sh",
        "scripts/mastermind_workspace.py",
        "control_plane/executive_workspace.py",
        "control_plane/__init__.py",
    ):
        source = repo_root / relative
        target_file = fixture / relative
        target_file.write_bytes(source.read_bytes())
        target_file.chmod(source.stat().st_mode & 0o777)
    _git(fixture, "init", "-q")
    _git(fixture, "config", "user.name", "Workspace Installer Test")
    _git(fixture, "config", "user.email", "workspace-installer@example.invalid")
    _git(fixture, "add", ".")
    _git(fixture, "commit", "-qm", "fixture")

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    launcher = tmp_path / "bin" / "mmx-workspace"
    payload = tmp_path / "payload"
    env = dict(os.environ)
    env.update(
        {
            "HOME": str(fake_home),
            "MASTERMIND_WORKSPACE_CLI_INSTALL": str(launcher),
            "MASTERMIND_WORKSPACE_CLI_PAYLOAD_ROOT": str(payload),
        }
    )
    subprocess.run(
        ["/bin/sh", str(fixture / "scripts" / "install_mastermind_workspace_cli.sh")],
        cwd=fixture,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    wrapper = launcher.read_text(encoding="utf-8")
    assert f"export MASTERMIND_SOURCE_REPO='{fixture.resolve()}'" in wrapper

    observed_external = ""
    if Path("/Volumes/Mastermind").is_dir():
        probe = subprocess.run(
            ["/bin/df", "-P", "/Volumes/Mastermind"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            observed_external = probe.stdout.strip().splitlines()[-1].split()[-1]
    expected_root = (
        "/Volumes/Mastermind/agent-workspaces"
        if observed_external == "/Volumes/Mastermind"
        else str(fake_home / ".mastermind" / "agent-workspaces")
    )
    assert f"export MASTERMIND_AGENT_WORKSPACE_ROOT='{expected_root}'" in wrapper

    payload_script = payload / "scripts" / "mastermind_workspace.py"
    payload_script.write_text(
        "import json, os\n"
        "print(json.dumps({\"source\": os.environ.get(\"MASTERMIND_SOURCE_REPO\"), "
        "\"root\": os.environ.get(\"MASTERMIND_AGENT_WORKSPACE_ROOT\")}))\n",
        encoding="utf-8",
    )
    hostile_env = dict(env)
    hostile_env["MASTERMIND_PYTHON"] = sys.executable
    hostile_env["MASTERMIND_SOURCE_REPO"] = str(tmp_path / "hostile-source")
    hostile_env["MASTERMIND_AGENT_WORKSPACE_ROOT"] = str(tmp_path / "hostile-root")
    completed = subprocess.run(
        [str(launcher)],
        env=hostile_env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    observed = json.loads(completed.stdout)
    assert observed == {"source": str(fixture.resolve()), "root": expected_root}

    original_mount_line = next(
        line for line in wrapper.splitlines() if line.startswith("workspace_mount=")
    )
    guarded = wrapper.replace(
        original_mount_line,
        f"workspace_mount='{tmp_path}'",
        1,
    )
    launcher.write_text(guarded, encoding="utf-8")
    launcher.chmod(0o755)
    refused = subprocess.run(
        [str(launcher)],
        env=hostile_env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert refused.returncode == 66
    assert "refusing fallback" in refused.stderr
