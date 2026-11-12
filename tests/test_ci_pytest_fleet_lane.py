"""The optional ephemeral pytest-shard lane is variable-gated and default OFF.

The shard job's `runs-on` is either the literal hosted image or one exact
expression. These tests evaluate that expression with a small, faithful model
of the GitHub Actions expression subset it uses (contains, format, fromJSON,
==, !=, &&, ||, parentheses, context properties), so the routing truth table is
proven rather than inferred from string shape.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from scripts import ci_parallel_shard as fan
from scripts import ci_pytest as cip

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW = _ROOT / ".github" / "workflows" / "ci.yml"
_LANE = ["self-hosted", "linux", "x64", "mastermind-pytest"]
_HOSTED = "ubuntu-24.04"


# --- minimal GitHub Actions expression evaluator ------------------------------

_TOKEN = re.compile(
    r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<num>\d+)|(?P<op>==|!=|&&|\|\||[(),!])"
    r"|(?P<ident>[A-Za-z_][A-Za-z0-9_\-]*(?:\.[A-Za-z_][A-Za-z0-9_\-]*)*))"
)


def _tokens(text: str):
    position, out = 0, []
    text = text.strip()
    while position < len(text):
        match = _TOKEN.match(text, position)
        assert match and match.end() > position, text[position:]
        position = match.end()
        kind = match.lastgroup
        out.append((kind, match.group(kind)))
    return out


def _truthy(value) -> bool:
    return value not in (None, False, 0, "") and not (isinstance(value, float) and value != value)


def _to_number(value):
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value) if value.strip() else 0
    except ValueError:
        return float("nan")


def _equal(left, right) -> bool:
    if isinstance(left, str) and isinstance(right, str):
        return left.casefold() == right.casefold()
    if type(left) is type(right):
        return left == right
    return _to_number(left) == _to_number(right)


def _string(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class _Expr:
    def __init__(self, text: str, context: dict) -> None:
        self.tokens = _tokens(text)
        self.index = 0
        self.context = context

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else (None, None)

    def take(self, value=None):
        token = self.peek()
        assert value is None or token[1] == value, (token, value)
        self.index += 1
        return token

    def evaluate(self):
        value = self.disjunction()
        assert self.index == len(self.tokens)
        return value

    def disjunction(self):
        value = self.conjunction()
        while self.peek()[1] == "||":
            self.take()
            right = self.conjunction()
            value = value if _truthy(value) else right
        return value

    def conjunction(self):
        value = self.comparison()
        while self.peek()[1] == "&&":
            self.take()
            right = self.comparison()
            value = right if _truthy(value) else value
        return value

    def comparison(self):
        value = self.unary()
        while self.peek()[1] in ("==", "!="):
            operator = self.take()[1]
            right = self.unary()
            value = _equal(value, right) if operator == "==" else not _equal(value, right)
        return value

    def unary(self):
        if self.peek()[1] == "!":
            self.take()
            return not _truthy(self.unary())
        return self.primary()

    def primary(self):
        kind, text = self.take()
        if text == "(":
            value = self.disjunction()
            self.take(")")
            return value
        if kind == "str":
            return text[1:-1].replace("''", "'")
        if kind == "num":
            return int(text)
        assert kind == "ident", text
        if self.peek()[1] == "(":
            self.take("(")
            args = []
            while self.peek()[1] != ")":
                args.append(self.disjunction())
                if self.peek()[1] == ",":
                    self.take(",")
            self.take(")")
            return self.call(text, args)
        value = self.context
        for part in text.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        return value

    @staticmethod
    def call(name, args):
        if name == "contains":
            return _string(args[1]).casefold() in _string(args[0]).casefold()
        if name == "format":
            template = args[0]
            return re.sub(r"\{(\d+)\}", lambda m: _string(args[1 + int(m.group(1))]), template)
        if name == "fromJSON":
            return json.loads(args[0])
        raise AssertionError(name)


def _evaluate(runs_on: str, *, shards=None, merge_group=None, event="push",
              index=3, fork=False):
    assert runs_on.startswith("${{") and runs_on.endswith("}}")
    variables = {}
    if shards is not None:
        variables["MM_PYTEST_FLEET_SHARDS"] = shards
    if merge_group is not None:
        variables["MM_PYTEST_FLEET_MERGE_GROUP"] = merge_group
    repository = "owner/Mastermind"
    context = {
        # An unset repository variable evaluates to the empty string.
        "vars": variables,
        "matrix": {"index": index},
        "github": {
            "event_name": event,
            "repository": repository,
            "event": {"pull_request": {"head": {"repo": {
                "full_name": "someone/fork" if fork else repository}}}},
        },
    }
    return _Expr(runs_on[3:-2], context).evaluate()


# --- source contract -------------------------------------------------------------


def _workflow():
    return yaml.load(_WORKFLOW.read_text(encoding="utf-8"), Loader=cip._WorkflowYAMLLoader)


def test_live_shard_runs_on_is_an_accepted_value_and_validates() -> None:
    workflow = _workflow()
    assert workflow["jobs"]["pytest_shards"]["runs-on"] in fan.PYTEST_SHARDS_RUNNERS
    fan.validate_parallel_workflow(_WORKFLOW.read_text(encoding="utf-8"))


def test_lane_expression_never_names_the_shared_label_and_falls_back_to_literal() -> None:
    expression = fan.PYTEST_SHARDS_LANE_RUNS_ON
    assert "ubuntu-latest" not in expression
    assert expression.endswith("|| 'ubuntu-24.04' }}")
    labels = json.loads(re.search(r"fromJSON\('(.*?)'\)", expression).group(1))
    assert labels == list(fan.PYTEST_FLEET_LABELS) == _LANE
    assert fan.PYTEST_SHARDS_RUNNERS == (_HOSTED, expression)


@pytest.mark.parametrize("event", ["push", "pull_request", "merge_group", "workflow_dispatch"])
@pytest.mark.parametrize("index", range(6))
def test_unset_variables_select_the_hosted_image_for_every_shard_and_event(event, index) -> None:
    assert _evaluate(fan.PYTEST_SHARDS_LANE_RUNS_ON, event=event, index=index) == _HOSTED
    assert _evaluate(fan.PYTEST_SHARDS_LANE_RUNS_ON, shards="", merge_group="",
                     event=event, index=index) == _HOSTED


@pytest.mark.parametrize("value,selected", [
    ("3", {3}), ("1,3,4,5", {1, 3, 4, 5}), ("0,1,2,3,4,5", {1, 3, 4, 5}),
    ("13", set()), ("3 ", set()), (" 3", set()), ("1, 3", {1}), ("all", set()),
    ("true", set()), ("-1", set()), ("03", set()), ("6", set()),
])
def test_variable_selects_only_exact_listed_non_container_shards(value, selected) -> None:
    for index in range(6):
        runner = _evaluate(fan.PYTEST_SHARDS_LANE_RUNS_ON, shards=value, event="push", index=index)
        assert runner == (_LANE if index in selected else _HOSTED), (value, index, runner)


@pytest.mark.parametrize("index", fan.PYTEST_FLEET_EXCLUDED_SHARDS)
def test_docker_and_sudo_shards_never_leave_the_hosted_image(index) -> None:
    for event in ("push", "pull_request", "merge_group", "workflow_dispatch"):
        assert _evaluate(fan.PYTEST_SHARDS_LANE_RUNS_ON, shards="0,1,2,3,4,5",
                         merge_group="true", event=event, index=index) == _HOSTED


@pytest.mark.parametrize("flag,expected", [
    (None, _HOSTED), ("", _HOSTED), ("false", _HOSTED), ("1", _HOSTED),
    ("yes", _HOSTED), ("true", _LANE),
])
def test_merge_groups_need_their_own_explicit_opt_in(flag, expected) -> None:
    assert _evaluate(fan.PYTEST_SHARDS_LANE_RUNS_ON, shards="3", merge_group=flag,
                     event="merge_group", index=3) == expected
    # The merge-group flag alone never moves any other event.
    assert _evaluate(fan.PYTEST_SHARDS_LANE_RUNS_ON, merge_group=flag,
                     event="push", index=3) == _HOSTED


def test_fork_pull_requests_stay_hosted_and_same_repository_ones_may_move() -> None:
    assert _evaluate(fan.PYTEST_SHARDS_LANE_RUNS_ON, shards="3", merge_group="true",
                     event="pull_request", index=3, fork=True) == _HOSTED
    assert _evaluate(fan.PYTEST_SHARDS_LANE_RUNS_ON, shards="3",
                     event="pull_request", index=3) == _LANE
    for event in ("push", "workflow_dispatch"):
        assert _evaluate(fan.PYTEST_SHARDS_LANE_RUNS_ON, shards="3", event=event, index=3) == _LANE


@pytest.mark.parametrize("runner", [
    "ubuntu-latest",
    ["self-hosted", "linux", "x64", "mastermind-pytest"],
    "${{ vars.TEST_RUNNER }}",
    "${{ vars.MM_PYTEST_FLEET_SHARDS && 'ubuntu-latest' || 'ubuntu-24.04' }}",
    fan.PYTEST_SHARDS_LANE_RUNS_ON.replace("'ubuntu-24.04'", "'ubuntu-latest'"),
    fan.PYTEST_SHARDS_LANE_RUNS_ON.replace(" && matrix.index != 2", ""),
    fan.PYTEST_SHARDS_LANE_RUNS_ON.replace("mastermind-pytest", "ubuntu-latest"),
    fan.PYTEST_SHARDS_LANE_RUNS_ON.replace(" == 'true'", ""),
    fan.PYTEST_SHARDS_LANE_RUNS_ON + " ",
    "",
    None,
])
def test_validator_refuses_any_other_shard_runner(runner) -> None:
    workflow = _workflow()
    if runner is None:
        del workflow["jobs"]["pytest_shards"]["runs-on"]
    else:
        workflow["jobs"]["pytest_shards"]["runs-on"] = runner
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))


@pytest.mark.parametrize("runner", [_HOSTED, fan.PYTEST_SHARDS_LANE_RUNS_ON])
def test_validator_accepts_both_shard_runner_forms(runner) -> None:
    workflow = _workflow()
    workflow["jobs"]["pytest_shards"]["runs-on"] = runner
    fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))


@pytest.mark.parametrize("job", ["pr_fast", "qualification"])
def test_lane_expression_is_refused_outside_the_shard_job(job) -> None:
    workflow = _workflow()
    assert workflow["jobs"][job]["runs-on"] == _HOSTED
    workflow["jobs"][job]["runs-on"] = fan.PYTEST_SHARDS_LANE_RUNS_ON
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))


def test_evaluator_matches_documented_github_semantics() -> None:
    """Guard the model itself on the operators the expression relies on."""
    def run(text, **context):
        return _Expr(text, context).evaluate()
    assert run("format(',{0},', vars.X)", vars={}) == ",,"
    assert run("contains(',1,3,', ',3,')") is True
    assert run("contains(',13,', ',3,')") is False
    assert run("matrix.index != 0", matrix={"index": 0}) is False
    assert run("'' && 'a' || 'b'") == "b"
    assert run("'x' && 'a' || 'b'") == "a"
    assert run("'TRUE' == 'true'") is True
