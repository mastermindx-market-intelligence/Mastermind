"""Fail-closed source contracts for Web-to-VPS accepted-main deployment.

This suite tests the trusted workflow SHAPE, not an actual VPS deploy. The
incumbent archive-and-rollback owner and real production proof remain separate.
"""
from pathlib import Path
import os
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/vps-main-deploy.yml"
PIN = ROOT / "ops/vps_origin_known_hosts"
EXPECTED_PIN = (
    "146.190.142.17 ssh-ed25519 "
    "AAAAC3NzaC1lZDI1NTE5AAAAIEc8ibhWOj35RC4FXjydG27GMxKfjiVXOw0s7hiCySkk\n"
)


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_release_wake_is_protected_main_only_and_read_only() -> None:
    wf = _workflow()
    events = wf.get("on", wf.get(True))
    assert set(events) == {"push", "workflow_dispatch"}
    assert events["workflow_dispatch"] == {}
    assert events["push"]["branches"] == ["master"]
    assert {"app/**", "brain/**", "portfolio/**", "control_plane/**", "engine/**", "web/**",
            ".github/workflows/vps-main-deploy.yml"} <= set(
        events["push"]["paths"]
    )
    assert "pull_request_target" not in events and "pull_request" not in events
    assert wf["permissions"] == {"contents": "read"}
    assert wf["concurrency"]["cancel-in-progress"] is False
    assert list(wf["jobs"]) == ["deploy"]
    job = wf["jobs"]["deploy"]
    assert "github.repository == 'mastermindx-market-intelligence/Mastermind'" in job["if"]
    assert "github.ref == 'refs/heads/master'" in job["if"]


def test_release_wake_uses_existing_exact_sha_and_rollback_owner() -> None:
    assert PIN.read_text(encoding="utf-8") == EXPECTED_PIN
    steps = _workflow()["jobs"]["deploy"]["steps"]
    assert len(steps) == 3
    assert steps[0]["uses"] == "actions/checkout@v4"
    command = steps[2]["run"]
    assert steps[2]["env"] == {"VPS_DEPLOY_KEY": "${{ secrets.VPS_DEPLOY_KEY }}"}
    assert '[[ "$GITHUB_SHA" =~ ^[0-9a-f]{40}$ ]]' in command
    assert "./scripts/deploy_from_git.sh \"$GITHUB_SHA\"" in command
    assert 'MASTERMIND_VPS_KEY="$KEYFILE"' in command
    assert "root@146.190.142.17" in command
    assert "StrictHostKeyChecking yes" in command
    assert "ssh-keyscan" not in "\n".join(
        line for line in command.splitlines() if not line.lstrip().startswith("#")
    )
    assert "mktemp" in command and "trap 'rm -f" in command
    executable = "\n".join(
        line for line in command.splitlines() if not line.lstrip().startswith("#")
    )
    for forbidden in ("rsync ", "git push", "gh pr merge", "systemctl restart", "--admin"):
        assert forbidden not in executable


def test_deploy_command_shell_parses_without_running() -> None:
    command = _workflow()["jobs"]["deploy"]["steps"][-1]["run"]
    parsed = subprocess.run(["bash", "-n"], input=command, text=True,
                            capture_output=True, check=False)
    assert parsed.returncode == 0, parsed.stderr


def test_checkout_materialization_precedes_the_secret_bearing_deploy() -> None:
    job = _workflow()["jobs"]["deploy"]
    assert job["runs-on"] == "ubuntu-24.04"
    materialize = job["steps"][1]
    assert set(materialize) == {"name", "shell", "run"}
    assert materialize["name"] == "Materialise the full checkout tree"
    assert materialize["shell"] == "bash"
    assert "VPS_DEPLOY_KEY" not in materialize["run"]
    parsed = subprocess.run(["bash", "-n"], input=materialize["run"], text=True,
                            capture_output=True, check=False)
    assert parsed.returncode == 0, parsed.stderr


def _fixture_environment() -> dict:
    # No inherited Git directory, global hooks, identity or signing configuration.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0")
    return env


def _sparse_fixture(root: Path, *, include_pin: bool) -> dict:
    env = _fixture_environment()
    def git(*args: str):
        return subprocess.run(["git", "-c", "user.name=Fixture", "-c",
            "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
            "-c", "core.hooksPath=" + os.devnull, *args], cwd=root, env=env,
            text=True, capture_output=True, check=True)
    (root / "scripts").mkdir()
    (root / "scripts/ci_profile_capture.py").write_text("# inert fixture\n")
    if include_pin:
        (root / "ops").mkdir()
        (root / "ops/vps_origin_known_hosts").write_text(EXPECTED_PIN)
    git("init", "-q")
    git("add", ".")
    git("commit", "-qm", "Disposable checkout fixture")
    git("sparse-checkout", "set", "--no-cone", "/scripts/ci_profile_capture.py")
    assert not (root / "ops/vps_origin_known_hosts").exists()
    return env


def test_materialization_restores_a_real_sparse_checkout(tmp_path: Path) -> None:
    env = _sparse_fixture(tmp_path, include_pin=True)
    result = subprocess.run(["bash", "-c", _workflow()["jobs"]["deploy"]["steps"][1]["run"]],
                            cwd=tmp_path, env=env, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "ops/vps_origin_known_hosts").read_text() == EXPECTED_PIN
    sparse = subprocess.run(["git", "sparse-checkout", "list"], cwd=tmp_path,
                            env=env, text=True, capture_output=True, check=False)
    assert sparse.returncode != 0


def test_materialization_refuses_a_missing_pin(tmp_path: Path) -> None:
    env = _sparse_fixture(tmp_path, include_pin=False)
    result = subprocess.run(["bash", "-c", _workflow()["jobs"]["deploy"]["steps"][1]["run"]],
                            cwd=tmp_path, env=env, text=True, capture_output=True, check=False)
    assert result.returncode != 0
    assert "VPS host pin missing after full-tree refresh" in result.stdout
    assert not (tmp_path / "ops/vps_origin_known_hosts").exists()
