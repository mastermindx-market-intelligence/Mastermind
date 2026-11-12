"""The early pin-guard lane and the shard exclusions must stay identical.

The guard modules run in the standalone ``Pin and identity guards`` job and
are excluded from the six canonical shards. If either list drifts, a module
would either run twice or silently lose coverage; these checks fail closed.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from scripts import ci_parallel_shard as fan
from scripts import ci_pin_guards as guards
from scripts import ci_pytest as cip

ROOT = Path(__file__).resolve().parents[1]
_PIN_GUARDS_GATE_MARKER = "scripts/ci_pin_guards.py"


def _excluded_for_pin_guards(root: Path) -> set[str]:
    rows = cip.load_exclusions(root)
    excluded = cip.validate_exclusions(root, rows, cip.discover_test_modules(root))
    by_gate: set[str] = set()
    for row in rows:
        if _PIN_GUARDS_GATE_MARKER in str(row.get("replacement_gate", "")):
            by_gate.add(str(row["path"]))
    assert by_gate <= set(excluded), "replacement gate must name an excluded module"
    return by_gate


def test_excluded_manifest_and_shard_exclusions_are_exactly_the_same_set() -> None:
    assert _excluded_for_pin_guards(ROOT) == set(guards.EXCLUDED_GUARD_MODULES)


def test_shard_resident_guards_stay_protected_and_in_the_shards() -> None:
    # The executive-prefix protection forbids excluding these modules; the
    # early job runs them additionally, never instead.
    assert all(cip.is_protected(path) for path in guards.SHARD_RESIDENT_GUARD_MODULES)
    gate = cip.resolve_gate(ROOT)
    assert set(guards.SHARD_RESIDENT_GUARD_MODULES) <= set(gate["included"])


def test_guard_modules_are_real_discovered_modules() -> None:
    gate = cip.resolve_gate(ROOT)
    discovered = set(gate["discovered"])
    assert set(guards.GUARD_MODULES) <= discovered
    # The excludable family must never run twice.
    assert set(guards.EXCLUDED_GUARD_MODULES).isdisjoint(set(gate["included"]))


def test_manifest_rejects_missing_modules_fail_closed(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    with pytest.raises(cip.PolicyError, match="missing"):
        guards.resolve_modules(tmp_path)


def test_plan_only_resolves_without_running_pytest(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(guards.subprocess, "run", lambda *a, **k: pytest.fail("plan-only must not run pytest"))
    assert guards.main(["--plan-only", "--root", str(ROOT)]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"pin_guards modules={len(guards.GUARD_MODULES)} ")
    for module in guards.GUARD_MODULES:
        assert module in out


def test_manifest_is_partitioned_without_overlap() -> None:
    assert set(guards.EXCLUDED_GUARD_MODULES).isdisjoint(guards.SHARD_RESIDENT_GUARD_MODULES)
    assert set(guards.GUARD_MODULES) == (
        set(guards.EXCLUDED_GUARD_MODULES) | set(guards.SHARD_RESIDENT_GUARD_MODULES)
    )


def test_workflow_pin_guards_lane_is_pinned_by_the_validator() -> None:
    import yaml

    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    fan.validate_parallel_workflow(text)
    workflow = yaml.load(text, Loader=cip._WorkflowYAMLLoader)
    job = workflow["jobs"]["pin_guards"]
    assert job["name"] == "Pin and identity guards"
    assert job["if"] == "${{ !cancelled() }}"
    assert job["steps"][3]["name"] == fan._PIN_GUARDS_RUN_STEP
    assert guards.GUARD_MODULES  # the manifest itself is non-empty


@pytest.mark.parametrize("mutation", [
    "wrong-if", "pr-and-merge-group-only", "needs-scope", "timeout",
    "continue-on-error", "missing-step",
    "wrong-command", "conditional-step", "permissions", "extra-step",
    "job-env", "job-defaults", "container", "strategy",
])
def test_validator_rejects_pin_guards_lane_drift(mutation: str) -> None:
    import copy

    import yaml

    workflow = yaml.load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"),
        Loader=cip._WorkflowYAMLLoader,
    )
    job = workflow["jobs"]["pin_guards"]
    if mutation == "wrong-if":
        job["if"] = "${{ github.event_name == 'pull_request' }}"
    elif mutation == "pr-and-merge-group-only":
        job["if"] = "${{ github.event_name == 'pull_request' || github.event_name == 'merge_group' }}"
    elif mutation == "needs-scope":
        job["needs"] = ["pr_scope"]
    elif mutation == "timeout":
        job["timeout-minutes"] = 45
    elif mutation == "continue-on-error":
        job["continue-on-error"] = True
    elif mutation == "missing-step":
        job["steps"].pop()
    elif mutation == "wrong-command":
        job["steps"][3]["run"] = "echo bypass"
    elif mutation == "conditional-step":
        job["steps"][3]["if"] = "${{ always() }}"
    elif mutation == "permissions":
        job["permissions"] = {"contents": "write"}
    elif mutation == "job-env":
        job["env"] = {"PYTHONPATH": "/tmp/shadow"}
    elif mutation == "job-defaults":
        job["defaults"] = {"run": {"working-directory": "scripts"}}
    elif mutation == "container":
        job["container"] = "ubuntu:24.04"
    elif mutation == "strategy":
        job["strategy"] = {"matrix": {"index": [0, 1]}}
    else:
        job["steps"].append({"run": "echo extra"})
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))
