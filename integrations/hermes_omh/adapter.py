"""Pure OMH graph analysis and Executive-v4 proposals; no runtime authority.

Only the vendored topology algorithms are reused. Policy and identity inputs
are caller-supplied proposal data, not grants, admission or currentness proof.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, NoReturn

from control_plane.executive_orchestration_result import (
    PLAN_SCHEMA_V4, OrchestrationResultError, _validate_plan,
    canonical_bytes, canonical_digest,
)
from .vendor import dag_core

MAX_BYTES = 131072
MAX_DEPTH = 12
MAX_ITEMS = 4096
SCHEMA = "mastermind.hermes_omh.proposal/v1"
DONOR_COMMIT = "5ead1032360edadd4b3a749f234f3830324de3b2"
_NODE_FIELDS = {"id", "label", "category", "prompt", "depends_on", "write_scope", "role"}
_POLICY_FIELDS = {"business_impact", "review_required", "requested_authorities",
                  "allowed_write_paths", "validation_ids", "attempt_limit", "cost_class"}
_NODE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_RESERVED_PATHS = {"CON", "PRN", "AUX", "NUL"} | {f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)}
_REASONS = frozenset({"INVALID_INPUT", "INPUT_OVER_BUDGET", "INVALID_GRAPH", "INVALID_POLICY",
                      "INVALID_SCOPE", "SCOPE_OUTSIDE_POLICY", "OVERLAPPING_WRITES",
                      "INVALID_IDENTITY", "INVALID_JSON", "INPUT_UNAVAILABLE", "OUTPUT_OVER_BUDGET"})


class ProposalError(ValueError):
    """A value-free closed refusal: no caller text or partial plan is exposed."""
    def __init__(self, reason: str):
        if reason not in _REASONS:
            raise ValueError("unknown proposal refusal")
        self.reason = reason
        super().__init__(reason)


def _refuse(reason: str) -> NoReturn:
    raise ProposalError(reason)


def bounded_plain(value: Any) -> None:
    """Bound exact builtins before serialization or recursive copying.

    The iterative depth/item budget also terminates cyclic in-memory input.
    No custom Mapping, iterator, numeric or string subclass is invoked.
    """
    stack = [(value, 0)]
    count = size = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if count > MAX_ITEMS or depth > MAX_DEPTH:
            _refuse("INPUT_OVER_BUDGET")
        kind = type(item)
        if kind is str:
            if len(item) > 8192:
                _refuse("INPUT_OVER_BUDGET")
            try:
                size += len(item.encode("utf-8"))
            except UnicodeEncodeError:
                _refuse("INVALID_INPUT")
        elif kind is dict:
            if len(item) > MAX_ITEMS or any(type(key) is not str for key in item):
                _refuse("INVALID_INPUT")
            if count + len(stack) + 2 * len(item) > MAX_ITEMS:
                _refuse("INPUT_OVER_BUDGET")
            for key, val in item.items():
                stack.append((key, depth + 1)); stack.append((val, depth + 1))
        elif kind is list:
            if count + len(stack) + len(item) > MAX_ITEMS:
                _refuse("INPUT_OVER_BUDGET")
            stack.extend((val, depth + 1) for val in item)
        elif item is None or kind is bool:
            size += 5
        elif kind is int:
            if item.bit_length() > 63:
                _refuse("INVALID_INPUT")
            size += 20
        else:
            _refuse("INVALID_INPUT")
        if size > MAX_BYTES:
            _refuse("INPUT_OVER_BUDGET")
    if len(canonical_bytes(value)) > MAX_BYTES:
        _refuse("INPUT_OVER_BUDGET")


def _text(value: Any, limit: int) -> str:
    if (type(value) is not str or not value or value != value.strip() or len(value) > limit
            or any(ord(c) < 32 and c not in "\n\r\t" for c in value) or "\x7f" in value):
        _refuse("INVALID_INPUT")
    return value


def _scope(value: Any, limit: int) -> list[str]:
    if type(value) is not list or len(value) > limit:
        _refuse("INVALID_SCOPE")
    out = []
    for path in value:
        if (type(path) is not str or not 1 <= len(path) <= 200
                or any(c in path for c in "\\*?[]{}:~")
                or any(unicodedata.category(c).startswith("C") for c in path)):
            _refuse("INVALID_SCOPE")
        parts = path.split("/")
        if any(p in {"", ".", ".."} or p != p.strip() or p.endswith(".")
               or unicodedata.normalize("NFKC", p.split(".")[0]).upper() in _RESERVED_PATHS
               for p in parts) or path in out:
            _refuse("INVALID_SCOPE")
        out.append(path)
    return out


def _within(path: str, parent: str) -> bool:
    # Exact lexical containment: case/Unicode folding must NEVER widen policy.
    return path == parent or path.startswith(parent + "/")


def _overlap(left: str, right: str) -> bool:
    # Conservatively detect aliases; actual filesystem custody stays host-owned.
    a = unicodedata.normalize("NFC", left).casefold()
    b = unicodedata.normalize("NFC", right).casefold()
    return _within(a, b) or _within(b, a)


def prepare_execution_plan(nodes: Any, *, policies: Any,
                           root_job_id: Any, plan_attempt_id: Any) -> dict[str, Any]:
    """Return a detached, deterministic proposal accepted by the existing parser.

    This does not authenticate supplied identities, inspect a worktree, reserve
    capacity, admit a plan, create a Job/Attempt, invoke Hermes, or dispatch work.
    OMH categories and roles select neither providers nor review/authority policy.
    """
    bounded_plain(dict(nodes=nodes, policies=policies,
                       root_job_id=root_job_id, plan_attempt_id=plan_attempt_id))
    if (type(root_job_id) is not str or _ID.fullmatch(root_job_id) is None
            or type(plan_attempt_id) is not str or _ID.fullmatch(plan_attempt_id) is None):
        _refuse("INVALID_IDENTITY")
    if type(nodes) is not list or not 1 <= len(nodes) <= 8:
        _refuse("INVALID_GRAPH")
    ids: list[str] = []
    by_id: dict[str, dict] = {}
    parents: dict[str, list[str]] = {}
    scopes: dict[str, list[str]] = {}
    for raw in nodes:
        if type(raw) is not dict or set(raw) != _NODE_FIELDS:
            _refuse("INVALID_INPUT")
        ident = raw["id"]
        if type(ident) is not str or _NODE_ID.fullmatch(ident) is None or ident in by_id:
            _refuse("INVALID_GRAPH")
        _text(raw["label"], 80); _text(raw["category"], 64); _text(raw["prompt"], 3000)
        if raw["role"] not in ("build", "baseline", "verify", "review"):
            _refuse("INVALID_INPUT")
        deps = raw["depends_on"]
        if (type(deps) is not list or len(deps) > 7
                or any(type(p) is not str or _NODE_ID.fullmatch(p) is None for p in deps)
                or len(deps) != len(set(deps))):
            _refuse("INVALID_GRAPH")
        ids.append(ident); by_id[ident] = raw; parents[ident] = list(deps)
        scopes[ident] = _scope(raw["write_scope"], 16)
    for ident in ids:
        if dag_core.edge_problem(ident, parents[ident], by_id) is not None:
            _refuse("INVALID_GRAPH")
    placed, stuck = dag_core.layer_of(ids, parents, strict=True)
    if stuck:
        _refuse("INVALID_GRAPH")
    ordered = sorted(ids, key=placed.__getitem__)
    if type(policies) is not dict or set(policies) != set(ids):
        _refuse("INVALID_POLICY")
    ancestors: dict[str, set[str]] = {}
    steps = []
    for ordinal, ident in enumerate(ordered):
        ancestors[ident] = set(parents[ident])
        for parent in parents[ident]:
            ancestors[ident].update(ancestors[parent])
        rule = policies[ident]
        if type(rule) is not dict or set(rule) != _POLICY_FIELDS:
            _refuse("INVALID_POLICY")
        allowed = _scope(rule["allowed_write_paths"], 32)
        if any(not any(_within(path, base) for base in allowed) for path in scopes[ident]):
            _refuse("SCOPE_OUTSIDE_POLICY")
        steps.append(dict(rule, ordinal=ordinal, step_id=ident, objective=by_id[ident]["prompt"],
                          allowed_write_paths=scopes[ident], prerequisite_step_ids=parents[ident]))
    for i, first in enumerate(ordered):
        for second in ordered[i+1:]:
            if first in ancestors[second] or second in ancestors[first]:
                continue
            if any(_overlap(a, b) for a in scopes[first] for b in scopes[second]):
                _refuse("OVERLAPPING_WRITES")
    proposed = dict(schema_version=PLAN_SCHEMA_V4, root_job_id=root_job_id,
                    plan_attempt_id=plan_attempt_id, steps=steps)
    try:
        # This is the original consumer, not a shadow schema or admission engine.
        plan = _validate_plan(proposed, outer=dict(run_id=plan_attempt_id, expected_root_job_id=root_job_id))
    except OrchestrationResultError:
        _refuse("INVALID_POLICY")
    layers = [[ident for ident in ordered if placed[ident] == n] for n in range(max(placed.values())+1)]
    result = dict(schema=SCHEMA, state="PREPARED_NOT_ADMITTED", admitted=False, dispatched=False,
                  plan=plan, plan_sha256=canonical_digest(plan),
                  topology=dict(layers=layers, critical_path=dag_core.critical_path(ids, parents),
                                critical_path_measure="node_count",
                                bottlenecks=[dict(step_id=i, dependent_count=n)
                                             for i, n in dag_core.bottlenecks(ids, parents)]),
                  donor=dict(repository="rlaope/oh-my-hermes", commit=DONOR_COMMIT,
                             path="src/plugin_bundle/omh/dag_core.py",
                             git_blob="e4bdf90bb03206b0eed806396196762cb5daa091"))
    if len(canonical_bytes(result)) > MAX_BYTES:
        _refuse("OUTPUT_OVER_BUDGET")
    return result
