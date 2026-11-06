"""Scope policy tests use real immutable local Git commit snapshots."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.ci_pr_scope import ScopeDecision, classify, select_scope

REPO = "mastermindx-market-intelligence/Mastermind"


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True,
        text=True, timeout=8,
    ).stdout.strip()


def setup(tmp_path: Path, path: str = "docs/user-guide.md",
          old: bytes = b"Old guide\n", new: bytes = b"New guide\n"):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "example@example.test")
    git(root, "config", "user.name", "Test")
    f = root / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(old)
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    f.write_bytes(new)
    git(root, "add", ".")
    git(root, "commit", "-qm", "change")
    head = git(root, "rev-parse", "HEAD")
    event = {
        "repository": {"full_name": REPO},
        "pull_request": {
            "number": 42,
            "head": {"sha": head, "repo": {"full_name": REPO}},
            "base": {"sha": base, "repo": {"full_name": REPO}},
            "title": "untrusted description: critical changes are fast",
        },
    }
    return root, event


def test_docs_only_pr_uses_fast_lite_gate(tmp_path):
    root, event = setup(tmp_path)
    scope = classify(root, event, expected_repository=REPO)
    assert scope == ScopeDecision("fast", "FAST", "SOURCE_VERIFIED", 1)


def test_runtime_source_is_standard_smoke_with_merge_group_full(tmp_path):
    root, event = setup(tmp_path, "app/mastermind_os/src/components/Widget.tsx",
                        b"export const x = 1;\n", b"export const x = 2;\n")
    scope = classify(root, event, expected_repository=REPO)
    assert scope.mode == "smoke" and scope.tier == "STANDARD"
    assert scope.needs_node is True


@pytest.mark.parametrize("path", [
    ".github/workflows/ci.yml",
    "scripts/ci_pr_scope.py",
    "control_plane/github_review_risk_policy.py",
    "tests/test_ci_pytest_policy.py",
    "tests/conftest.py",
    "docs/SOL_SOURCE_LAW.md",
    "ops/executive_os/restart.sh",
])
def test_security_and_ci_enforcement_always_full_pr(path, tmp_path):
    root, event = setup(tmp_path, path)
    scope = classify(root, event, expected_repository=REPO)
    assert scope.mode == "full" and scope.tier == "CRITICAL"


def test_renamed_files_force_full_even_if_docs(tmp_path):
    root, event = setup(tmp_path)
    git(root, "mv", "docs/user-guide.md", "docs/guide.md")
    git(root, "commit", "-qm", "rename")
    event["pull_request"]["head"]["sha"] = git(root, "rev-parse", "HEAD")
    assert select_scope_event(root, event).full


def test_deletion_forces_full(tmp_path):
    root, event = setup(tmp_path)
    git(root, "rm", "docs/user-guide.md")
    git(root, "commit", "-qm", "delete")
    event["pull_request"]["head"]["sha"] = git(root, "rev-parse", "HEAD")
    assert select_scope_event(root, event).full


def test_missing_commit_or_wrong_repo_or_fork_fails_closed(tmp_path):
    root, event = setup(tmp_path)
    event["pull_request"]["head"]["sha"] = "e" * 40
    assert select_scope_event(root, event).full
    event["pull_request"]["head"]["sha"] = git(root, "rev-parse", "HEAD")
    event["pull_request"]["head"]["repo"]["full_name"] = "attacker/repo"
    assert select_scope_event(root, event).full
    event["pull_request"]["head"]["repo"]["full_name"] = REPO
    event["repository"]["full_name"] = "attacker/repo"
    assert select_scope_event(root, event).full


def test_binary_nonvisual_requires_full(tmp_path):
    root, event = setup(tmp_path, "app/src/dashboard.tsx",
                        bytes(range(256)) + b"\x00", bytes(range(255, -1, -1)) + b"\x00")
    assert select_scope_event(root, event).full


def test_visual_binary_can_stay_fast(tmp_path):
    root, event = setup(tmp_path, "docs/screenshots/chart.png",
                        bytes(range(256)) + b"\x00", bytes(range(255, -1, -1)) + b"\x00")
    scope = select_scope_event(root, event)
    assert scope.mode == "fast", scope


def test_unknown_operations_and_incomplete_event_default_to_full(tmp_path):
    root, event = setup(tmp_path)
    event.pop("pull_request")
    assert select_scope_event(root, event).full


def test_cli_fails_closed_on_broken_event_and_writes_quoted_outputs(tmp_path):
    root, _ = setup(tmp_path)
    eventfile = tmp_path / "event.json"
    out = tmp_path / "output"
    eventfile.write_text('{"untrusted":"risk=fast"}', encoding="utf-8")
    scope = select_scope(root, eventfile, expected_repository=REPO)
    assert scope.mode == "full"


def select_scope_event(root: Path, event: dict) -> ScopeDecision:
    try:
        return classify(root, event, expected_repository=REPO)
    except Exception:
        # Reflect the deployed CLI's exact fallback; never silently call a
        # different classifier or supply author-owned 'verified' facts.
        data = root.parent / "event.json"
        data.write_text(json.dumps(event), encoding="utf-8")
        return select_scope(root, data, expected_repository=REPO)



def test_inert_looking_readme_symlink_never_gets_fast(tmp_path):
    import os
    root, event = setup(tmp_path)
    changed = root / "docs/user-guide.md"
    changed.unlink()
    os.symlink("../private", changed)
    git(root, "add", ".")
    git(root, "commit", "-qm", "symlink")
    event["pull_request"]["head"]["sha"] = git(root, "rev-parse", "HEAD")
    assert select_scope_event(root, event).full


def test_executable_permission_on_docs_forces_full(tmp_path):
    root, event = setup(tmp_path)
    changed = root / "docs/user-guide.md"
    changed.chmod(0o755)
    git(root, "add", ".")
    git(root, "commit", "-qm", "exec")
    event["pull_request"]["head"]["sha"] = git(root, "rev-parse", "HEAD")
    assert select_scope_event(root, event).full
