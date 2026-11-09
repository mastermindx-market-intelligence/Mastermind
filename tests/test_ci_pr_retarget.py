"""Exercise retarget routing without inventing a required-test result.

The expressions come from the actual workflow. The small evaluator implements
only the logical/context subset used there; it does not emulate a hosted run.
Hosted checkout and completion remain separate evidence.
"""

from __future__ import annotations

import ast
import copy
import re
from pathlib import Path

import pytest
import yaml

from scripts import ci_parallel_shard as fan
from scripts import ci_pytest as cip

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"


def _workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=cip._WorkflowYAMLLoader)


def _expression(source, github, needs=None, cancelled=False):
    source = source.strip()
    if source.startswith("$" + "{{"):
        source = source[3:-2].strip()
    values = {"always": lambda: True, "cancelled": lambda: cancelled}

    def bind(match):
        path = match[0].split(".")
        value = {"github": github, "needs": needs or {}}
        for part in path:
            value = value.get(part) if isinstance(value, dict) else None
        key = f"context_{len(values)}"
        values[key] = value
        return key

    source = re.sub(r"\b(?:github|needs)\.[a-zA-Z0-9_.]+", bind, source)
    source = source.replace("&&", " and ").replace("||", " or ")
    source = re.sub(r"!(?!=)", " not ", source)
    source = re.sub(r"\bnull\b", "None", source)
    parsed = ast.parse(source.strip(), mode="eval")
    allowed = (ast.Expression, ast.BoolOp, ast.UnaryOp, ast.Compare, ast.Name,
               ast.Load, ast.Constant, ast.And, ast.Or, ast.Not, ast.Eq,
               ast.NotEq, ast.Call)
    assert all(isinstance(node, allowed) for node in ast.walk(parsed))
    for node in ast.walk(parsed):
        if isinstance(node, ast.Call):
            assert isinstance(node.func, ast.Name)
            assert node.func.id in {"always", "cancelled"}
            assert not node.args and not node.keywords
    return eval(compile(parsed, "<actual-workflow-condition>", "eval"),
                {"__builtins__": {}}, values)


def _render(source, github):
    return re.sub(r"\$\{\{(.*?)\}\}",
                  lambda m: str(_expression(m[1], github)), source)


BASE_CHANGE = {"base": {"ref": {"from": "feature/old"},
                        "sha": {"from": "1" * 40}}}
CASES = [
    ("pull_request", "opened", None, False),
    ("pull_request", "synchronize", None, False),
    ("pull_request", "reopened", None, False),
    ("pull_request", "edited", BASE_CHANGE, False),
    ("pull_request", "edited", {**BASE_CHANGE, "body": {"from": "old"}}, False),
    ("pull_request", "edited", {"base": {}}, False),
    ("pull_request", "edited", {"base": {"sha": {"from": "1" * 40}}}, False),
    ("pull_request", "edited", {"title": {"from": "old"}}, True),
    ("pull_request", "edited", {"body": {"from": ""}}, True),
    ("pull_request", "edited", {"title": {"from": "old"}, "body": {"from": ""}}, True),
    ("pull_request", "edited", None, False),
    ("pull_request", "edited", {}, False),
    ("pull_request", "edited", {"future": {"from": "old"}}, False),
    ("merge_group", "checks_requested", None, False),
    ("push", "", None, False),
    ("workflow_dispatch", "", None, False),
    ("push", "edited", {"body": {"from": "old"}}, False),
    ("merge_group", "edited", {"body": {"from": "old"}}, False),
    ("workflow_dispatch", "edited", {"title": {"from": "old"}}, False),
]


@pytest.mark.parametrize("event,action,changes,metadata", CASES)
@pytest.mark.parametrize("cancelled", [False, True])
def test_actual_event_conditions_preserve_source_checks_and_isolate_metadata(
    event, action, changes, metadata, cancelled,
):
    workflow = _workflow()
    github = {"event_name": event, "workflow": "CI",
              "ref": "refs/pull/751/merge",
              "event": {"action": action, "changes": changes}}
    if event == "pull_request":
        trigger = workflow["on"]["pull_request"]
        types = trigger.get("types") if isinstance(trigger, dict) else [
            "opened", "synchronize", "reopened",
        ]
        assert action in types, "a base edit must create a new qualification"
    scope_event = event in {"pull_request", "merge_group"}
    jobs = workflow["jobs"]
    # A skipped job reports success on GitHub. Its name must therefore differ
    # from the branch-protected context even when the body changed after red CI.
    assert _render(jobs["test"]["name"], github) == (
        "PR metadata edit" if metadata else "test"
    )
    assert bool(_expression(jobs["test"]["if"], github, cancelled=cancelled)) is not metadata
    assert bool(_expression(jobs["pr_scope"]["if"], github)) == (
        scope_event and not metadata
    )
    assert _render(workflow["concurrency"]["group"], github) == (
        "ci-CI-refs/pull/751/merge" + ("-metadata" if metadata else "")
    )
    assert workflow["concurrency"]["cancel-in-progress"] is True

    for mode in ("full", "fast", "smoke"):
        needs = {"pr_scope": {
            "result": "success" if scope_event and not metadata else "skipped",
            "outputs": {"mode": mode},
        }}
        fast = bool(_expression(jobs["pr_fast"]["if"], github, needs, cancelled))
        shards = bool(_expression(jobs["pytest_shards"]["if"], github, needs, cancelled))
        assert fast == (scope_event and not metadata and mode != "full" and not cancelled)
        assert shards == (not metadata and not cancelled and (
            event in {"push", "workflow_dispatch"} or (scope_event and mode == "full")
        ))


@pytest.mark.parametrize("mutation", [
    "omit-retarget", "omit-opened", "omit-synchronize", "omit-reopened",
    "extra-trigger", "trigger-path-filter", "metadata-required-name",
    "metadata-cancels-source", "cancel-disabled", "metadata-runs-gate",
    "real-gate-disappears-on-cancellation", "metadata-runs-scope", "base-ref-only",
])
def test_retarget_contract_refuses_unsafe_workflow_mutations(mutation):
    workflow = copy.deepcopy(_workflow())
    jobs = workflow["jobs"]
    if mutation.startswith("omit-"):
        action = {"retarget": "edited"}.get(mutation[5:], mutation[5:])
        workflow["on"]["pull_request"]["types"].remove(action)
    elif mutation == "extra-trigger":
        workflow["on"]["pull_request"]["types"].append("labeled")
    elif mutation == "trigger-path-filter":
        workflow["on"]["pull_request"]["paths"] = ["app/**"]
    elif mutation == "metadata-required-name":
        jobs["test"]["name"] = "test"
    elif mutation == "metadata-cancels-source":
        workflow["concurrency"]["group"] = "ci-$" + "{{ github.workflow }}-$" + "{{ github.ref }}"
    elif mutation == "cancel-disabled":
        workflow["concurrency"]["cancel-in-progress"] = False
    elif mutation == "metadata-runs-gate":
        jobs["test"]["if"] = "$" + "{{ always() }}"
    elif mutation == "real-gate-disappears-on-cancellation":
        jobs["test"]["if"] = jobs["test"]["if"].replace("always()", "!cancelled()")
    elif mutation == "metadata-runs-scope":
        jobs["pr_scope"]["if"] = "$" + "{{ github.event_name == 'pull_request' || github.event_name == 'merge_group' }}"
    elif mutation == "base-ref-only":
        for job in ("test", "pr_scope"):
            jobs[job]["if"] = jobs[job]["if"].replace(
                "github.event.changes.base == null",
                "github.event.changes.base.ref.from == null",
            )
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))


def test_retarget_keeps_event_checkout_and_actual_base_selection():
    workflow = _workflow()
    fan.validate_parallel_workflow(WORKFLOW.read_text(encoding="utf-8"))
    scope = workflow["jobs"]["pr_scope"]["steps"]
    assert scope[0]["uses"] == "actions/checkout@v4"
    assert "ref" not in scope[0]["with"]
    assert scope[0]["with"]["persist-credentials"] is False
    classifier = next(step for step in scope if step.get("id") == "scope")
    assert classifier["env"] == {"PR_BASE_SHA": "$" + "{{ github.event.pull_request.base.sha }}"}
    steps = workflow["jobs"]["pytest_shards"]["steps"]
    checkout = next(s for s in steps if s.get("name") == "Checkout event source")
    assert checkout["uses"] == "actions/checkout@v4"
    assert "ref" not in checkout["with"]
    verification = next(s for s in steps if s.get("name") == "Verify event source and immutable fixture anchor")
    assert 'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"' in verification["run"]
