"""The parallel qualification lane owns the six non-pytest gates exactly.

CI Lightning F3 moved the once-per-checkout qualification gates out of shard
zero so they stop serializing ahead of its pytest mass. The gates must stay
byte-identical to their released commands, run exactly when the shards run
(including reuse pushes), and never linger inside a shard. These checks fail
closed on any drift.

The sixth gate is the web application typecheck. The PR fast lane owns it
for fast/smoke candidates and is skipped in full mode, so this job is the
only place a full merge group, a protected push or a manual run typechecks
``app/mastermind_os``. It must be present, unconditional and run once.
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
    "Typecheck web application",
)
_TYPECHECK = _GATE_NAMES[-1]
_TYPECHECK_RUN = (
    "npm ci --prefix app/mastermind_os --ignore-scripts --no-audit --no-fund\n"
    "npm --prefix app/mastermind_os run typecheck\n"
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


def _typecheck_step(workflow: dict) -> dict:
    steps = workflow["jobs"]["qualification"]["steps"]
    found = [step for step in steps if step.get("name") == _TYPECHECK]
    assert len(found) == 1
    return found[0]


def test_full_mode_typechecks_the_web_application_unconditionally() -> None:
    workflow = _workflow()
    jobs = workflow["jobs"]
    step = _typecheck_step(workflow)
    # Unconditional: pr_scope does not run on push/dispatch and every
    # fail-closed HOLD decision reports needs_node=false, so neither a step
    # condition nor needs_node may decide whether full mode typechecks.
    assert set(step) == {"name", "run"}
    assert step["run"] == _TYPECHECK_RUN
    assert "needs_node" not in str(jobs["qualification"])
    # Same commands and the same Node release the PR fast lane typechecks with.
    fast_steps = jobs["pr_fast"]["steps"]
    fast_typecheck = next(
        s for s in fast_steps if s.get("name") == "Typecheck affected web application"
    )
    assert fast_typecheck["run"] == step["run"]
    fast_node = next(s for s in fast_steps if s.get("uses") == "actions/setup-node@v4")
    qual_node = next(
        s for s in jobs["qualification"]["steps"]
        if s.get("uses") == "actions/setup-node@v4"
    )
    assert qual_node["with"]["node-version"] == fast_node["with"]["node-version"]
    assert qual_node["with"]["cache-dependency-path"].splitlines() == [
        "integrations/studio_direct_mcp/package-lock.json",
        "app/mastermind_os/package-lock.json",
    ]
    for lockfile in qual_node["with"]["cache-dependency-path"].splitlines():
        assert (ROOT / lockfile).is_file()


def test_typecheck_runs_once_per_event_never_in_both_lanes() -> None:
    jobs = _workflow()["jobs"]
    # The two job conditions are pinned by the validator and exclude each
    # other: pr_fast needs a PR/merge-group scope that is not full, the
    # qualification job needs full mode or an event with no scope at all.
    fast_if, qual_if = jobs["pr_fast"]["if"], jobs["qualification"]["if"]
    assert fast_if == fan._REQUIRED_PR_FAST_IF
    assert qual_if == fan._REQUIRED_QUALIFICATION_IF
    assert "needs.pr_scope.outputs.mode != 'full'" in fast_if
    assert "needs.pr_scope.outputs.mode == 'full'" in qual_if

    def lanes(event: str, mode: str) -> tuple[bool, bool]:
        scoped = event in {"pull_request", "merge_group"}
        fast = scoped and mode != "full"
        qualification = event in {"push", "workflow_dispatch"} or (
            scoped and mode == "full"
        )
        return fast, qualification

    for event, modes in {
        "pull_request": ("fast", "smoke", "full"),
        "merge_group": ("fast", "full"),
        "push": ("",),
        "workflow_dispatch": ("",),
    }.items():
        for mode in modes:
            fast, qualification = lanes(event, mode)
            assert fast != qualification, (event, mode)
            if mode in {"full", ""}:
                assert qualification, (event, mode)
    # No other job typechecks, so one event runs the command at most once.
    owners = [
        name for name, job in jobs.items()
        if any("run typecheck" in str(s.get("run", "")) for s in job.get("steps", []))
    ]
    assert sorted(owners) == ["pr_fast", "qualification"]


@pytest.mark.parametrize("mutation", [
    "removed", "renamed", "conditional-needs-node", "conditional-always",
    "continue-on-error", "command-cut", "command-echoed", "command-or-true",
    "duplicated", "moved-into-shard", "moved-into-pin-guards",
    "lockfile-cache-dropped", "node-version",
])
def test_validator_requires_the_qualification_typecheck(mutation: str) -> None:
    import copy

    import yaml

    workflow = _workflow()
    jobs = workflow["jobs"]
    steps = jobs["qualification"]["steps"]
    step = _typecheck_step(workflow)
    specific = "must typecheck the web application unconditionally"
    if mutation == "removed":
        steps.remove(step)
    elif mutation == "renamed":
        step["name"] = "Typecheck"
    elif mutation == "conditional-needs-node":
        step["if"] = "${{ needs.pr_scope.outputs.needs_node == 'true' }}"
    elif mutation == "conditional-always":
        step["if"] = "${{ always() }}"
    elif mutation == "continue-on-error":
        step["continue-on-error"] = True
    elif mutation == "command-cut":
        step["run"] = step["run"].splitlines()[0] + "\n"
    elif mutation == "command-echoed":
        step["run"] = step["run"].replace("npm --prefix", "echo npm --prefix")
    elif mutation == "command-or-true":
        step["run"] = step["run"].rstrip("\n") + " || true\n"
    elif mutation == "duplicated":
        steps.append(copy.deepcopy(step))
    elif mutation == "moved-into-shard":
        steps.remove(step)
        jobs["pytest_shards"]["steps"].append(step)
    elif mutation == "moved-into-pin-guards":
        steps.remove(step)
        jobs["pin_guards"]["steps"].append(step)
    elif mutation == "lockfile-cache-dropped":
        specific = "qualification lane source or commands drifted"
        node = next(s for s in steps if s.get("uses") == "actions/setup-node@v4")
        node["with"]["cache-dependency-path"] = (
            "integrations/studio_direct_mcp/package-lock.json"
        )
    elif mutation == "node-version":
        specific = "qualification lane source or commands drifted"
        node = next(s for s in steps if s.get("uses") == "actions/setup-node@v4")
        node["with"]["node-version"] = "20"
    with pytest.raises(cip.PolicyError) as raised:
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))
    if not mutation.startswith("moved-into-"):
        assert specific in str(raised.value)


@pytest.mark.parametrize("index", range(len(_GATE_NAMES)))
def test_any_single_shard_side_gate_copy_is_rejected(index: int) -> None:
    import copy

    import yaml

    workflow = _workflow()
    gate = copy.deepcopy(workflow["jobs"]["qualification"]["steps"][4 + index])
    assert gate["name"] == _GATE_NAMES[index]
    workflow["jobs"]["pytest_shards"]["steps"].append(gate)
    with pytest.raises(cip.PolicyError, match="only in the qualification job"):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))
