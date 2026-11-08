"""Fail-closed source contracts for Web-to-VPS accepted-main deployment.

This suite tests the trusted workflow SHAPE, not an actual VPS deploy. The
incumbent archive-and-rollback owner and real production proof remain separate.
"""
from pathlib import Path

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
    assert {"app/**", "portfolio/**", "control_plane/**", "engine/**", "web/**"} <= set(
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
    assert len(steps) == 2
    assert steps[0]["uses"] == "actions/checkout@v4"
    command = steps[1]["run"]
    assert steps[1]["env"] == {"VPS_DEPLOY_KEY": "${{ secrets.VPS_DEPLOY_KEY }}"}
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
