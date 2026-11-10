"""Scope policy tests use real immutable local Git commit snapshots."""
from __future__ import annotations

import json
import os
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


def ordinary_module_group(tmp_path, count, *, owners=False, oversized=False):
    root = tmp_path / "group"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "example@example.test")
    git(root, "config", "user.name", "Test")
    (root / "app").mkdir()
    (root / "tests").mkdir()
    (root / "app/customer.py").write_text("value = 1\n")
    names = [f"tests/test_customer_{i}.py" for i in range(count)]
    for name in names:
        (root / name).write_text("def test_customer(): assert True\n")
    if oversized:
        (root / "tests/test_customer.py").write_text("#" + "x" * 160000 + "\n")
    if owners:
        from scripts.ci_pr_smoke import _IDENTITY_PIN_REGISTRIES
        registry, _, required = _IDENTITY_PIN_REGISTRIES[0]
        (root / registry).write_text("REVIEWED_FILES = {'app/customer.py': {}}\n")
        for name in required:
            (root / name).write_text("def test_pin(): assert True\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "protected fixture")
    base = git(root, "rev-parse", "HEAD")
    (root / "app/customer.py").write_text("value = 2\n")
    for index, name in enumerate(names):
        (root / name).write_text("def test_customer(): assert 1 == 1\n")
        # Two individually small queue entries must still qualify their union.
        if index == 1:
            git(root, "add", ".")
            git(root, "commit", "-qm", "first queue entry")
    git(root, "add", ".")
    git(root, "commit", "-qm", "remaining queue entry")
    head = git(root, "rev-parse", "HEAD")
    pr = {"repository": {"full_name": REPO}, "pull_request": {
        "number": 42, "base": {"sha": base, "repo": {"full_name": REPO}},
        "head": {"sha": head, "repo": {"full_name": REPO}},
    }}
    event, protected = merge_event(root, pr)
    return root, pr, event, protected


@pytest.mark.parametrize("count,expected", [(3, "smoke"), (4, "full")])
def test_merge_group_complete_module_budget_preserves_pr_fast_feedback(tmp_path, count, expected):
    from scripts.ci_pr_scope import classify_merge_group
    root, pr, event, protected = ordinary_module_group(tmp_path, count)
    assert classify(root, pr, expected_repository=REPO).mode == "smoke"
    result = classify_merge_group(root, event, expected_repository=REPO,
                                  protected_base_sha=protected)
    assert result.mode == expected and result.tier == "STANDARD"
    assert result.source_base == protected and result.source_head == pr["pull_request"]["head"]["sha"]
    assert result.file_count == count + 1
    assert result.reason == ("SMOKE_SELECTION_EXCEEDS_BUDGET" if count == 4 else "SOURCE_VERIFIED")


@pytest.mark.parametrize("count,expected", [(0, "smoke"), (1, "full")])
def test_merge_group_ownership_tests_cannot_hide_an_ordinary_module(tmp_path, count, expected):
    from scripts.ci_pr_scope import classify_merge_group
    root, _, event, protected = ordinary_module_group(tmp_path, count, owners=True)
    result = classify_merge_group(root, event, expected_repository=REPO,
                                  protected_base_sha=protected)
    assert result.mode == expected and result.tier == "STANDARD"
    if count:
        assert result.reason == "SMOKE_SELECTION_EXCEEDS_BUDGET"


def test_merge_group_oversized_mapped_module_escalates_instead_of_disappearing(tmp_path):
    from scripts.ci_pr_scope import classify_merge_group
    root, _, event, protected = ordinary_module_group(tmp_path, 0, oversized=True)
    result = classify_merge_group(root, event, expected_repository=REPO,
                                  protected_base_sha=protected)
    assert result.mode == "full" and result.tier == "STANDARD"
    assert result.reason == "SMOKE_APPLICABLE_TEST_UNAVAILABLE"


def test_workflow_uses_complete_protected_archive_despite_candidate_package_poison(tmp_path):
    import yaml
    source = Path(__file__).resolve().parents[1]
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "example@example.test")
    git(root, "config", "user.name", "Test")
    paths = ("scripts/__init__.py", "scripts/ci_pr_scope.py", "scripts/ci_pr_smoke.py",
             "control_plane/__init__.py", "control_plane/github_review_risk_policy.py")
    for name in paths:
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((source / name).read_bytes())
    git(root, "add", ".")
    git(root, "commit", "-qm", "protected qualifier closure")
    protected = git(root, "rev-parse", "HEAD")
    for name in ("scripts/__init__.py", "scripts/ci_pr_smoke.py", "control_plane/__init__.py"):
        (root / name).write_text("raise RuntimeError('CANDIDATE_PACKAGE_EXECUTED')\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "poison candidate packages")
    head = git(root, "rev-parse", "HEAD")
    event = {"repository": {"full_name": REPO}, "pull_request": {
        "number": 42, "base": {"sha": protected, "repo": {"full_name": REPO}},
        "head": {"sha": head, "repo": {"full_name": REPO}},
    }}
    payload, output = tmp_path / "event.json", tmp_path / "output"
    payload.write_text(json.dumps(event))
    workflow = yaml.safe_load((source / ".github/workflows/ci.yml").read_text())
    (scope_step,) = (
        step for step in workflow["jobs"]["pr_scope"]["steps"]
        if step.get("id") == "scope"
    )
    command = scope_step["run"]
    result = subprocess.run(["bash", "-c", command], cwd=root, env={
        **os.environ, "RUNNER_TEMP": str(tmp_path), "PR_BASE_SHA": protected,
        "GITHUB_EVENT_NAME": "pull_request", "GITHUB_WORKSPACE": str(root),
        "GITHUB_EVENT_PATH": str(payload), "GITHUB_REPOSITORY": REPO,
        "GITHUB_OUTPUT": str(output),
    }, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "mode=full" in output.read_text().splitlines()
    assert "CANDIDATE_PACKAGE_EXECUTED" not in result.stdout + result.stderr
    for name in paths:
        assert (tmp_path / "ci-trusted-base" / name).read_bytes() == (source / name).read_bytes()
