"""Superseded CI may stop heavy work without skipping the fail-closed gate."""
from pathlib import Path

import pytest

from scripts.ci_parallel_shard import validate_parallel_workflow
from scripts.ci_pytest import PolicyError, _WorkflowYAMLLoader

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci.yml"


def test_heavy_jobs_cancel_and_final_gate_keeps_aggregating():
    import yaml

    source = WORKFLOW.read_text(encoding="utf-8")
    validate_parallel_workflow(source)
    jobs = yaml.load(source, Loader=_WorkflowYAMLLoader)["jobs"]
    from scripts import ci_parallel_shard as fan
    assert jobs["pr_fast"]["if"] == fan._REQUIRED_PR_FAST_IF
    assert jobs["pytest_shards"]["if"] == fan._REQUIRED_SHARDS_IF
    assert jobs["test"]["if"] == "${{ always() }}"
    assert jobs["test"]["needs"] == ["pr_scope", "pr_fast", "pin_guards", "pytest_shards"]


@pytest.mark.parametrize("job", ["pr_fast", "pytest_shards"])
@pytest.mark.parametrize("replacement", ["always()", "success()", "true"])
def test_validator_rejects_uncancellable_or_incomplete_heavy_job_selector(job, replacement):
    source = WORKFLOW.read_text(encoding="utf-8")
    start = source.index("  " + job + ":\n")
    position = source.index("!cancelled()", start)
    mutated = source[:position] + source[position:].replace("!cancelled()", replacement, 1)
    with pytest.raises(PolicyError):
        validate_parallel_workflow(mutated)


def test_final_gate_cannot_disappear_on_cancelled_dependencies():
    source = WORKFLOW.read_text(encoding="utf-8")
    mutated = source.replace("if: ${{ always() }}", "if: ${{ !cancelled() }}", 1)
    with pytest.raises(PolicyError):
        validate_parallel_workflow(mutated)
