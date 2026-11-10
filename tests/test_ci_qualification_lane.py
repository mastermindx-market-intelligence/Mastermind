"""The parallel qualification lane owns the five non-pytest gates exactly.

CI Lightning F3 moved the once-per-checkout qualification gates out of shard
zero so they stop serializing ahead of its pytest mass. The gates must stay
byte-identical to their released commands, run exactly when the shards run
(including reuse pushes), and never linger inside a shard. These checks fail
closed on any drift.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from scripts import ci_parallel_shard as fan
from scripts import ci_pytest as cip

ROOT = Path(__file__).resolve().parents[1]
_GATE_NAMES = (
    "Verify Paper direct pinned MCP SDK",
    "Verify Paper Studio prepare guard",
    "Verify private Fabric HTTP compatibility and incumbent backend lifetime",
    "Compile source",
    "Validate shell scripts",
)


def _workflow() -> dict:
    import yaml

    return yaml.load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"),
        Loader=cip._WorkflowYAMLLoader,
    )


def test_qualification_lane_is_pinned_by_the_validator() -> None:
    fan.validate_parallel_workflow(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    workflow = _workflow()
    qual = workflow["jobs"]["qualification"]
    assert qual["name"] == "Non-pytest qualification gates"
    assert qual["needs"] == ["pr_scope"]
    # Hosted-only: the shared self-hosted hosts also answer "ubuntu-latest"
    # and their checkouts fail the Fabric gate's source-directory check.
    assert qual["runs-on"] == "ubuntu-24.04"
    # The lane runs exactly when the pytest shards run: same gate expression.
    assert qual["if"] == workflow["jobs"]["pytest_shards"]["if"]
    assert [step.get("name") for step in qual["steps"]][4:] == list(_GATE_NAMES)


def test_gate_bodies_are_the_released_shard_zero_commands() -> None:
    # Byte-identical commands: only placement changed, never the checks.
    expected = fan._EXPECTED_QUALIFICATION_STEPS
    workflow = _workflow()
    qual_steps = workflow["jobs"]["qualification"]["steps"]
    assert qual_steps == expected
    fabric = next(s for s in qual_steps if s.get("name") == _GATE_NAMES[2])
    assert fabric["working-directory"] == "integrations/studio_direct_mcp"
    commands = [line for line in fabric["run"].splitlines() if line.strip()]
    assert commands[0] == "npm ci --ignore-scripts --no-audit --no-fund"
    assert "private-tunnel-auth.test.mjs" in commands[1]
    assert commands[-1] == "python -m unittest discover -s . -p 'control_bundle*test.py'"
    paper_sdk = next(s for s in qual_steps if s.get("name") == _GATE_NAMES[0])
    assert "PAPER_DIRECT_PINNED_SDK_TESTS=1" in paper_sdk["run"]
    compile_step = next(s for s in qual_steps if s.get("name") == "Compile source")
    assert compile_step["run"].startswith("python -m compileall -q app bot brain")
    shell_step = next(s for s in qual_steps if s.get("name") == "Validate shell scripts")
    assert "bash -n" in shell_step["run"]


def test_shards_no_longer_carry_any_qualification_gate() -> None:
    workflow = _workflow()
    shard_steps = workflow["jobs"]["pytest_shards"]["steps"]
    for name in _GATE_NAMES:
        assert not [step for step in shard_steps if step.get("name") == name]


def test_proof_schema_requires_the_qualification_job_and_its_steps() -> None:
    from scripts import ci_postmerge_proof as proof

    assert proof._JOB_CONCLUSIONS["Non-pytest qualification gates"] == "success"
    assert len(proof._JOB_NAMES) == 11


@pytest.mark.parametrize("mutation", [
    "wrong-if", "needs-scope", "timeout-low", "timeout-high", "continue-on-error",
    "missing-gate", "gate-conditional", "gate-continue-on-error", "wrong-directory",
    "cut-command", "extra-step", "permissions", "moved-into-shard",
    "shard-copy", "runner-latest", "runner-self-hosted", "runner-expression",
    "job-env", "job-defaults", "container", "strategy", "services",
])
def test_validator_rejects_qualification_lane_drift(mutation: str) -> None:
    import copy

    import yaml

    workflow = _workflow()
    qual = workflow["jobs"]["qualification"]
    shards = workflow["jobs"]["pytest_shards"]
    if mutation == "wrong-if":
        qual["if"] = "${{ github.event_name == 'push' }}"
    elif mutation == "needs-scope":
        qual["needs"] = ["pr_scope", "pytest_shards"]
    elif mutation == "timeout-low":
        qual["timeout-minutes"] = 4
    elif mutation == "timeout-high":
        qual["timeout-minutes"] = 45
    elif mutation == "continue-on-error":
        qual["continue-on-error"] = True
    elif mutation == "missing-gate":
        qual["steps"].pop(5)
    elif mutation == "gate-conditional":
        qual["steps"][5]["if"] = "${{ always() }}"
    elif mutation == "gate-continue-on-error":
        qual["steps"][5]["continue-on-error"] = True
    elif mutation == "wrong-directory":
        next(s for s in qual["steps"] if s.get("name") == _GATE_NAMES[2])[
            "working-directory"] = "."
    elif mutation == "cut-command":
        fabric = next(s for s in qual["steps"] if s.get("name") == _GATE_NAMES[2])
        fabric["run"] = "\n".join(
            line for line in fabric["run"].splitlines()
            if "private-cli" not in line
        ) + "\n"
    elif mutation == "extra-step":
        qual["steps"].append({"run": "echo extra"})
    elif mutation == "permissions":
        qual["permissions"] = {"contents": "write"}
    elif mutation == "moved-into-shard":
        gate = copy.deepcopy(qual["steps"][5])
        gate["if"] = "matrix.index == 0"
        qual["steps"].pop(5)
        shards["steps"].append(gate)
    elif mutation == "shard-copy":
        # Lane left intact: only the shard-side "no copy" rule can fire.
        gate = copy.deepcopy(qual["steps"][5])
        gate["if"] = "matrix.index == 0"
        shards["steps"].append(gate)
    elif mutation == "runner-latest":
        qual["runs-on"] = "ubuntu-latest"
    elif mutation == "runner-self-hosted":
        qual["runs-on"] = ["self-hosted", "linux"]
    elif mutation == "runner-expression":
        qual["runs-on"] = "${{ vars.HOSTED_TEST_RUNNER || 'ubuntu-latest' }}"
    elif mutation == "job-env":
        qual["env"] = {"PYTHONPATH": "/tmp/shadow"}
    elif mutation == "job-defaults":
        qual["defaults"] = {"run": {"working-directory": "integrations"}}
    elif mutation == "container":
        qual["container"] = "ubuntu:24.04"
    elif mutation == "strategy":
        qual["strategy"] = {"matrix": {"index": [0, 1]}}
    elif mutation == "services":
        qual["services"] = {"cache": {"image": "redis"}}
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))


@pytest.mark.parametrize("index", range(5))
def test_any_single_shard_side_gate_copy_is_rejected(index: int) -> None:
    import copy

    import yaml

    workflow = _workflow()
    gate = copy.deepcopy(workflow["jobs"]["qualification"]["steps"][4 + index])
    assert gate["name"] == _GATE_NAMES[index]
    workflow["jobs"]["pytest_shards"]["steps"].append(gate)
    with pytest.raises(cip.PolicyError, match="only in the qualification job"):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))
