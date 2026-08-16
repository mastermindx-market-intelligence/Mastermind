"""Fail-closed policy for discovery-first hosted CI.

A new ``tests/**/test_*.py`` module runs automatically. Exact reviewed exclusions
are the only way to omit a module, and they cannot remove constitutional tests
or resurrect a positive workflow filename allowlist.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _load_runner():
    path = _ROOT / "scripts" / "ci_pytest.py"
    spec = importlib.util.spec_from_file_location("ci_pytest_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cip = _load_runner()


def _write_manifest(root: Path, rows: list[dict] | None = None) -> None:
    lines = ["version = 1", ""]
    for row in rows or []:
        lines.append("[[exclude]]")
        lines.append(f'path = "{row["path"]}"')
        if "reason" in row:
            lines.append(f'reason = "{row["reason"]}"')
        if "replacement_gate" in row:
            lines.append(f'replacement_gate = "{row["replacement_gate"]}"')
        lines.append("")
    (root / "ci").mkdir(parents=True, exist_ok=True)
    (root / "ci" / "pytest_exclusions.toml").write_text("\n".join(lines), encoding="utf-8")


def _write_test(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("def test_ok():\n    assert True\n", encoding="utf-8")


def _fake_repo(tmp_path: Path, modules: list[str], rows: list[dict] | None = None) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'ci-policy-fixture'\n", encoding="utf-8")
    for relative in modules:
        _write_test(tmp_path, relative)
    _write_manifest(tmp_path, rows)
    return tmp_path


def _plan(root: Path):
    discovered = cip.discover_test_modules(root)
    excluded = cip.validate_exclusions(root, cip.load_exclusions(root), discovered)
    included = cip.included_modules(discovered, excluded)
    return discovered, excluded, included


def test_new_test_is_included_automatically(tmp_path):
    root = _fake_repo(
        tmp_path,
        ["tests/test_existing.py", "tests/test_brand_new_future_test.py"],
    )
    discovered, excluded, included = _plan(root)
    assert excluded == ()
    assert "tests/test_existing.py" in included
    assert "tests/test_brand_new_future_test.py" in included
    assert set(included) == set(discovered)


def test_exact_exclusion_omits_only_that_path(tmp_path):
    root = _fake_repo(
        tmp_path,
        ["tests/test_keep.py", "tests/test_host_only.py"],
        [
            {
                "path": "tests/test_host_only.py",
                "reason": "Requires root, launchd and dedicated macOS service UIDs.",
                "replacement_gate": "Phase 1C-A real-host acceptance",
            }
        ],
    )
    discovered, excluded, included = _plan(root)
    assert excluded == ("tests/test_host_only.py",)
    assert "tests/test_host_only.py" not in included
    assert "tests/test_keep.py" in included
    assert set(included) | set(excluded) == set(discovered)
    assert set(included) & set(excluded) == set()


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_executive_*.py",
        "tests/**",
        "tests/",
        "tests",
    ],
)
def test_wildcard_and_directory_exclusions_are_rejected(tmp_path, path):
    root = _fake_repo(tmp_path, ["tests/test_keep.py"])
    rows = [
        {
            "path": path,
            "reason": "should not be accepted",
            "replacement_gate": "none",
        }
    ]
    with pytest.raises(cip.PolicyError, match="forbidden|must be under tests"):
        cip.validate_exclusions(root, rows, cip.discover_test_modules(root))


def test_stale_exclusion_is_rejected(tmp_path):
    root = _fake_repo(tmp_path, ["tests/test_keep.py"])
    rows = [
        {
            "path": "tests/test_missing.py",
            "reason": "file was deleted",
            "replacement_gate": "none",
        }
    ]
    with pytest.raises(cip.PolicyError, match="stale exclusion"):
        cip.validate_exclusions(root, rows, cip.discover_test_modules(root))


@pytest.mark.parametrize(
    "path",
    [
        "../something.py",
        "/vendor/macro/tests/test_x.py",
        "vendor/macro/tests/test_x.py",
    ],
)
def test_path_escape_is_rejected(tmp_path, path):
    root = _fake_repo(tmp_path, ["tests/test_keep.py"])
    rows = [
        {
            "path": path,
            "reason": "escape attempt",
            "replacement_gate": "none",
        }
    ]
    with pytest.raises(cip.PolicyError, match="forbidden|must be under tests"):
        cip.validate_exclusions(root, rows, cip.discover_test_modules(root))


def test_duplicate_exclusion_is_rejected(tmp_path):
    root = _fake_repo(tmp_path, ["tests/test_host_only.py"])
    row = {
        "path": "tests/test_host_only.py",
        "reason": "Requires root, launchd and dedicated macOS service UIDs.",
        "replacement_gate": "Phase 1C-A real-host acceptance",
    }
    with pytest.raises(cip.PolicyError, match="duplicate exclusion"):
        cip.validate_exclusions(root, [row, dict(row)], cip.discover_test_modules(root))


def test_empty_reason_is_rejected(tmp_path):
    root = _fake_repo(tmp_path, ["tests/test_host_only.py"])
    rows = [
        {
            "path": "tests/test_host_only.py",
            "reason": "",
            "replacement_gate": "Phase 1C-A real-host acceptance",
        }
    ]
    with pytest.raises(cip.PolicyError, match="reason cannot be empty"):
        cip.validate_exclusions(root, rows, cip.discover_test_modules(root))


def test_protected_executive_test_cannot_be_excluded(tmp_path):
    root = _fake_repo(tmp_path, ["tests/test_executive_os_runtime.py"])
    rows = [
        {
            "path": "tests/test_executive_os_runtime.py",
            "reason": "should not be accepted",
            "replacement_gate": "none",
        }
    ]
    with pytest.raises(cip.PolicyError, match="protected test cannot be excluded"):
        cip.validate_exclusions(root, rows, cip.discover_test_modules(root))


def test_self_exclusion_of_ci_policy_is_rejected(tmp_path):
    root = _fake_repo(tmp_path, ["tests/test_ci_pytest_policy.py"])
    rows = [
        {
            "path": "tests/test_ci_pytest_policy.py",
            "reason": "should not be accepted",
            "replacement_gate": "none",
        }
    ]
    with pytest.raises(cip.PolicyError, match="protected test cannot be excluded"):
        cip.validate_exclusions(root, rows, cip.discover_test_modules(root))


def test_workflow_must_call_discovery_runner_and_reject_allowlists():
    cip.validate_workflow((_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    with pytest.raises(cip.PolicyError, match="must invoke"):
        cip.validate_workflow("name: CI\njobs:\n  test:\n    steps: []\n")
    allowlist = """
name: CI
jobs:
  test:
    steps:
      - name: Run repository test gate
        run: |
          python scripts/ci_pytest.py
          tests/test_foo.py
          tests/test_bar.py
          tests/test_baz.py
"""
    with pytest.raises(cip.PolicyError, match="positive tests/test_"):
        cip.validate_workflow(allowlist)
    comments_only = """
name: CI
jobs:
  test:
    steps:
      - name: Run repository test gate
        run: python scripts/ci_pytest.py
# Historical note only:
# tests/test_foo.py
# tests/test_bar.py
# tests/test_baz.py
"""
    cip.validate_workflow(comments_only)


def test_all_discovered_tests_are_accounted_for():
    gate = cip.resolve_gate(_ROOT)
    discovered = set(gate["discovered"])
    excluded = set(gate["excluded"])
    included = set(gate["included"])
    independent = {
        path.relative_to(_ROOT).as_posix()
        for path in (_ROOT / "tests").rglob("test_*.py")
        if path.is_file()
    }
    assert discovered == independent
    assert included | excluded == discovered
    assert included & excluded == set()
    assert discovered
    assert included
    argv = cip.pytest_argv(gate["included"])
    assert argv[:4] == [cip.sys.executable, "-m", "pytest", "-q"]
    assert argv[4:] == list(gate["included"])
