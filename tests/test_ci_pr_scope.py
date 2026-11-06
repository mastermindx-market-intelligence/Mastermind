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


def merge_event(root: Path, pr: dict, *, protected: str | None = None) -> tuple[dict, str]:
    base = pr["pull_request"]["base"]["sha"]
    head = pr["pull_request"]["head"]["sha"]
    git(root, "update-ref", "refs/remotes/origin/master", protected or base)
    return {
        "repository": {"full_name": REPO},
        "merge_group": {
            "base_sha": base,
            "head_sha": head,
            "base_ref": "refs/heads/master",
            "head_ref": "refs/heads/gh-readonly-queue/master/pr-42-verified",
        },
    }, protected or base


def test_merge_group_inert_docs_uses_fast_on_exact_integrated_head(tmp_path):
    root, pr = setup(tmp_path)
    event, protected = merge_event(root, pr)
    from scripts.ci_pr_scope import classify_merge_group
    result = classify_merge_group(root, event, expected_repository=REPO,
                                  protected_base_sha=protected)
    assert result.mode == "fast" and result.tier == "FAST"
    assert result.source_base == protected
    assert result.source_head == pr["pull_request"]["head"]["sha"]


def test_merge_group_ordinary_code_requires_source_proximate_smoke(tmp_path):
    root, pr = setup(tmp_path, "app/mastermind_os/src/components/Widget.tsx",
                     b"export const x = 1;\n", b"export const x = 2;\n")
    event, protected = merge_event(root, pr)
    from scripts.ci_pr_scope import classify_merge_group
    result = classify_merge_group(root, event, expected_repository=REPO,
                                  protected_base_sha=protected)
    assert result.mode == "smoke" and result.needs_node is True


@pytest.mark.parametrize("path", [
    ".github/workflows/ci.yml", "scripts/ci_pr_scope.py",
    "control_plane/github_review_risk_policy.py", "AGENTS.md",
    "integrations/studio_direct_mcp/git-publish.mjs",
    "trading/live_execution.py", "tests/test_ci_pytest_policy.py",
])
def test_merge_group_privileged_changes_remain_full(tmp_path, path):
    root, pr = setup(tmp_path, path)
    event, protected = merge_event(root, pr)
    from scripts.ci_pr_scope import classify_merge_group
    result = classify_merge_group(root, event, expected_repository=REPO,
                                  protected_base_sha=protected)
    assert result.mode == "full" and result.tier == "CRITICAL"


def test_merge_group_scans_entire_aggregate_not_only_last_inert_commit(tmp_path):
    root, pr = setup(tmp_path, "docs/user-guide.md")
    critical = root / "scripts" / "ci_pr_scope.py"
    critical.parent.mkdir(exist_ok=True)
    critical.write_text("x = True\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "critical earlier queue entry")
    (root / "docs/user-guide.md").write_text("latest doc only\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "last benign queue entry")
    pr["pull_request"]["head"]["sha"] = git(root, "rev-parse", "HEAD")
    event, protected = merge_event(root, pr)
    from scripts.ci_pr_scope import classify_merge_group
    decision = classify_merge_group(root, event, expected_repository=REPO,
                                    protected_base_sha=protected)
    assert decision.mode == "full"


@pytest.mark.parametrize("mutation", [
    "repository", "base_ref", "head_ref", "head", "protected", "event_base",
    "missing", "untrusted_group_source",
])
def test_merge_group_unverifiable_identity_fails_to_full(tmp_path, mutation):
    root, pr = setup(tmp_path)
    event, protected = merge_event(root, pr)
    if mutation == "repository":
        event["repository"]["full_name"] = "other/attacker"
    elif mutation == "base_ref":
        event["merge_group"]["base_ref"] = "refs/heads/feature"
    elif mutation == "head_ref":
        event["merge_group"]["head_ref"] = "refs/heads/attacker"
    elif mutation == "head":
        event["merge_group"]["head_sha"] = "e" * 40
    elif mutation == "protected":
        protected = "e" * 40
    elif mutation == "event_base":
        event["merge_group"]["base_sha"] = "e" * 40
    elif mutation == "missing":
        del event["merge_group"]["head_sha"]
    elif mutation == "untrusted_group_source":
        git(root, "update-ref", "refs/remotes/origin/master",
            pr["pull_request"]["head"]["sha"])
    payload = tmp_path / "merge-event.json"
    payload.write_text(json.dumps(event))
    scope = select_scope(root, payload, expected_repository=REPO,
                         event_type="merge_group", protected_base_sha=protected)
    assert scope.mode == "full" and scope.tier == "HOLD"


def test_merge_group_without_trusted_protected_base_cannot_choose_fast(tmp_path):
    root, pr = setup(tmp_path)
    event, _ = merge_event(root, pr)
    file = tmp_path / "merge-group.json"
    file.write_text(json.dumps(event))
    result = select_scope(root, file, expected_repository=REPO,
                          event_type="merge_group")
    assert result.mode == "full" and result.tier == "HOLD"
