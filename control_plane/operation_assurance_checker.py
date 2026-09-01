"""control_plane.operation_assurance_checker — OLS-A1 deterministic checker (OLS-F0).

Deterministic explicit-state exploration of one closed
``mastermind.operation_assurance_model.v1``: reachability, authored safety,
workflow soundness, all reachable cyclic SCCs, a weak-fairness augmented
product for liveness/starvation, and final verdict/disposition/recommendation
composition into one immutable
``mastermind.operation_assurance_report.v1``.

Controlling sources (exact precedence):

1. docs/superpowers/specs/2026-08-31-operation-assurance-a1-wire-release-finalization.md
2. docs/superpowers/specs/2026-08-30-operation-assurance-immutable-report-projection-clarification.md
3. docs/superpowers/specs/2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md
4. docs/superpowers/specs/2026-08-30-operation-assurance-a1-trusted-input-total-proof-clarification.md
5. docs/superpowers/specs/2026-08-30-operation-assurance-a1-controlling-execution-overlay.md
6. docs/superpowers/plans/2026-08-30-operation-assurance-core.md

Purity boundary: zero network, socket, subprocess, telemetry,
filesystem-write, SQLite, or runtime I/O. Standard library only.

Trust ceiling: this module treats every authored positive evidence label as
descriptive-only. ``source_applicability_at_generation`` is normalized from
``model.source_snapshot`` using the deterministic weakening order in the
core plan (Section 9.3); it can never exceed ``AUTHOR_DECLARED_ONLY``.
Every checker-discovered witness starts at ``DECLARED_MODEL_ONLY`` (or
``POTENTIALLY_SPURIOUS`` for a relevant-gap/non-exact-fidelity candidate);
nothing in the authored model can promote it further.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Iterable

from control_plane.operation_assurance_model import (
    Gate,
    Guard,
    ModelGap,
    OperationAssuranceModel,
    Outcome,
    Transition,
)
from control_plane.operation_assurance_report import (
    AnalysisProduct,
    Assumptions,
    Change,
    Counterexample,
    Coverage,
    DisabledTransition,
    ExplorationReceipt,
    GuardFailure,
    OperationAssuranceReport,
    PropertyResult,
    RepairCandidate,
    StateDeltaStep,
    TransitionReasonSnapshot,
    build_report,
    compute_counterexample_id,
)
from control_plane.operation_assurance_model import canonical_json, sha256_hex

CHECKER_VERSION = "ols-a1-0.1.0"

_GENERIC_MANDATORY_ORDER = (
    "OPTION_TO_COMPLETE",
    "PROPER_COMPLETION",
    "NO_DEAD_REQUIRED_TRANSITION",
    "NO_POST_TERMINAL_TRANSITION",
    "GATE_OR_WAIT_RETURN_PATH_VALID",
    "UNIVERSAL_PROGRESS",
    "RECURRING_PROGRESS_VALID",
    "NO_STARVATION_UNDER_DECLARED_FAIRNESS",
    "FAIRNESS_REALIZABLE",
)
_NOT_APPLICABLE_ELIGIBLE = frozenset(
    {"RECURRING_PROGRESS_VALID", "NO_STARVATION_UNDER_DECLARED_FAIRNESS", "FAIRNESS_REALIZABLE"}
)


class CheckerInternalError(RuntimeError):
    """An unexpected internal checker failure. Never becomes proof."""


State = tuple  # tuple[str, ...] in lexical variable order


# ---------------------------------------------------------------------------
# Guard / effect evaluation
# ---------------------------------------------------------------------------


def _guard_holds(state_dict: dict[str, str], g: Guard) -> bool:
    actual = state_dict[g.variable]
    if g.op == "EQ":
        return actual == g.value
    if g.op == "NEQ":
        return actual != g.value
    if g.op == "IN":
        return actual in g.value
    if g.op == "NOT_IN":
        return actual not in g.value
    raise CheckerInternalError(f"unknown guard op {g.op!r}")


def _guard_failure(state_dict: dict[str, str], g: Guard) -> GuardFailure:
    expected = g.value if isinstance(g.value, str) else "[" + ",".join(g.value) + "]"
    return GuardFailure(variable=g.variable, op=g.op, expected=str(expected), actual=state_dict[g.variable])


def _all_guards_eval(state_dict: dict[str, str], guards: Iterable[Guard]) -> tuple[bool, tuple[GuardFailure, ...]]:
    failures = []
    ok = True
    for g in guards:
        if not _guard_holds(state_dict, g):
            ok = False
            failures.append(_guard_failure(state_dict, g))
    return ok, tuple(failures)


def _apply_effects(state_dict: dict[str, str], effects, var_order: tuple[str, ...]) -> State:
    new = dict(state_dict)
    for e in effects:
        new[e.variable] = e.value
    return tuple(new[v] for v in var_order)


def _state_dict(state: State, var_order: tuple[str, ...]) -> dict[str, str]:
    return dict(zip(var_order, state))


def _state_fingerprint(state_dict: dict[str, str]) -> str:
    return sha256_hex(canonical_json(state_dict))


# ---------------------------------------------------------------------------
# Reachability graph
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Graph:
    var_order: tuple[str, ...]
    initial: State
    discovered: dict[State, int]  # state -> depth
    prefix_of: dict[State, tuple[str, ...]]
    all_edges: list[tuple[State, str, State]]
    enabled_at: dict[State, tuple[str, ...]]
    disabled_at: dict[State, dict[str, tuple[tuple[str, ...], tuple[GuardFailure, ...]]]]
    succ_of: dict[State, list[tuple[str, State]]]
    incomplete_at: set[State]
    base_graph_complete: bool
    state_limit_reached: bool
    depth_limit_reached: bool
    transitions_considered: int
    peak_frontier: int


def _disabled_reason_codes(transition: Transition, guard_failures: tuple[GuardFailure, ...]) -> tuple[str, ...]:
    if not guard_failures:
        return ()
    return tuple(sorted({"GUARD_NOT_SATISFIED"}))


def explore(model: OperationAssuranceModel) -> Graph:
    var_order = tuple(sorted(v for v, _ in model.state_domains))
    initial_dict = model.initial_state_dict()
    initial = tuple(initial_dict[v] for v in var_order)
    max_states = model.exploration_limits.max_states
    max_depth = model.exploration_limits.max_depth
    transitions = model.transitions  # already sorted by transition_id

    discovered: dict[State, int] = {initial: 0}
    prefix_of: dict[State, tuple[str, ...]] = {initial: ()}
    frontier: list[State] = [initial]
    current_depth = 0
    all_edges: list[tuple[State, str, State]] = []
    enabled_at: dict[State, tuple[str, ...]] = {}
    disabled_at: dict[State, dict[str, tuple[tuple[str, ...], tuple[GuardFailure, ...]]]] = {}
    incomplete_at: set[State] = set()
    base_graph_complete = True
    state_limit_reached = False
    depth_limit_reached = False
    transitions_considered = 0
    peak_frontier = 1

    while frontier:
        peak_frontier = max(peak_frontier, len(frontier))
        round_candidates: dict[State, list[tuple[tuple[str, ...], State, str]]] = {}
        for s in sorted(frontier, key=lambda x: prefix_of[x]):
            sd = _state_dict(s, var_order)
            en: list[str] = []
            dis: dict[str, tuple[tuple[str, ...], tuple[GuardFailure, ...]]] = {}
            for t in transitions:
                transitions_considered += 1
                ok, failures = _all_guards_eval(sd, t.guards)
                if ok:
                    en.append(t.transition_id)
                    succ = _apply_effects(sd, t.effects, var_order)
                    if succ in discovered:
                        all_edges.append((s, t.transition_id, succ))
                    else:
                        if current_depth >= max_depth:
                            base_graph_complete = False
                            depth_limit_reached = True
                            incomplete_at.add(s)
                        else:
                            round_candidates.setdefault(succ, []).append((prefix_of[s] + (t.transition_id,), s, t.transition_id))
                else:
                    dis[t.transition_id] = (_disabled_reason_codes(t, failures), failures)
            enabled_at[s] = tuple(en)
            disabled_at[s] = dis

        next_frontier: list[State] = []
        ordered_succ = sorted(round_candidates.keys(), key=lambda x: min(c[0] for c in round_candidates[x]))
        for succ in ordered_succ:
            candidates = round_candidates[succ]
            if len(discovered) >= max_states:
                base_graph_complete = False
                state_limit_reached = True
                for (_p, from_c, _t) in candidates:
                    incomplete_at.add(from_c)
                continue
            candidates_sorted = sorted(candidates, key=lambda c: c[0])
            best_prefix = candidates_sorted[0][0]
            discovered[succ] = current_depth + 1
            prefix_of[succ] = best_prefix
            for (_p, from_c, tid_c) in candidates_sorted:
                all_edges.append((from_c, tid_c, succ))
            next_frontier.append(succ)
        frontier = next_frontier
        current_depth += 1

    succ_of: dict[State, list[tuple[str, State]]] = {}
    for (s, tid, s2) in all_edges:
        succ_of.setdefault(s, []).append((tid, s2))
    for s in succ_of:
        succ_of[s].sort(key=lambda x: (x[0], x[1]))

    return Graph(
        var_order=var_order,
        initial=initial,
        discovered=discovered,
        prefix_of=prefix_of,
        all_edges=all_edges,
        enabled_at=enabled_at,
        disabled_at=disabled_at,
        succ_of=succ_of,
        incomplete_at=incomplete_at,
        base_graph_complete=base_graph_complete,
        state_limit_reached=state_limit_reached,
        depth_limit_reached=depth_limit_reached,
        transitions_considered=transitions_considered,
        peak_frontier=peak_frontier,
    )


# ---------------------------------------------------------------------------
# Outcome / gate matching
# ---------------------------------------------------------------------------


def _outcome_matches(sd: dict[str, str], o: Outcome) -> bool:
    return all(_guard_holds(sd, g) for g in o.guards)


def _matching_outcomes(sd: dict[str, str], outcomes: tuple[Outcome, ...]) -> tuple[Outcome, ...]:
    return tuple(o for o in outcomes if _outcome_matches(sd, o))


def _gate_state_matches(sd: dict[str, str], g: Gate) -> bool:
    return all(_guard_holds(sd, sg) for sg in g.state_guards)


def _gate_return_valid_at(sd: dict[str, str], g: Gate, graph: Graph, model: OperationAssuranceModel, terminal_outcomes) -> bool:
    """True iff at least one release transition of ``g`` is enabled at this
    exact state and its materialized successor either leaves the gate or
    matches a named terminal outcome (overlay Section 3.3 / plan 14.7)."""
    state = tuple(sd[v] for v in graph.var_order)
    en = graph.enabled_at.get(state, ())
    for tid, succ in graph.succ_of.get(state, []):
        if tid not in g.release_transition_ids:
            continue
        succ_sd = _state_dict(succ, graph.var_order)
        if not _gate_state_matches(succ_sd, g):
            return True
        if _matching_outcomes(succ_sd, terminal_outcomes):
            return True
    return False


# ---------------------------------------------------------------------------
# Reach-a-boundary helper (existence needs no completeness; absence does)
# ---------------------------------------------------------------------------


def _forward_reach(start: State, predicate, graph: Graph) -> str:
    """PASS if ``predicate`` holds somewhere in the forward closure of
    ``start`` (existence — always decidable). FAIL if the *entire* forward
    closure was fully materialized and predicate never held. UNKNOWN if the
    closure touched an incompletely-expanded state before deciding."""
    visited = {start}
    queue = [start]
    hit_incomplete = False
    while queue:
        s = queue.pop(0)
        if predicate(s):
            return "PASS"
        if s in graph.incomplete_at:
            hit_incomplete = True
        for _tid, s2 in graph.succ_of.get(s, []):
            if s2 not in visited:
                visited.add(s2)
                queue.append(s2)
    return "UNKNOWN" if hit_incomplete else "FAIL"


# ---------------------------------------------------------------------------
# Witness construction
# ---------------------------------------------------------------------------


def _state_delta(graph: Graph, from_state: State, tid: str, to_state: State, segment: str, step_index: int) -> StateDeltaStep:
    from_sd = _state_dict(from_state, graph.var_order)
    to_sd = _state_dict(to_state, graph.var_order)
    changes = tuple(
        Change(v, from_sd[v], to_sd[v]) for v in graph.var_order if from_sd[v] != to_sd[v]
    )
    return StateDeltaStep(
        segment=segment,
        step_index=step_index,
        from_state_fingerprint=_state_fingerprint(from_sd),
        transition_id=tid,
        to_state_fingerprint=_state_fingerprint(to_sd),
        changes=changes,
    )


def _transition_reason_snapshot(graph: Graph, state: State, segment: str, step_index: int) -> TransitionReasonSnapshot:
    en = graph.enabled_at.get(state, ())
    dis = graph.disabled_at.get(state, {})
    disabled = tuple(
        DisabledTransition(tid, reason_codes, guard_failures)
        for tid, (reason_codes, guard_failures) in sorted(dis.items())
    )
    return TransitionReasonSnapshot(
        segment=segment,
        step_index=step_index,
        state_fingerprint=_state_fingerprint(_state_dict(state, graph.var_order)),
        enabled_transition_ids=en,
        disabled_transitions=disabled,
    )


def _path_from_prefix(graph: Graph, target: State) -> list[tuple[State, str, State]]:
    """Reconstruct the canonical (state, transition_id, state) path from the
    initial state to ``target`` using the recorded canonical prefix."""
    prefix = graph.prefix_of[target]
    steps = []
    cur = graph.initial
    for tid in prefix:
        nxt = None
        for t2, s2 in graph.succ_of.get(cur, []):
            if t2 == tid:
                nxt = s2
                break
        if nxt is None:
            raise CheckerInternalError("prefix reconstruction failed")
        steps.append((cur, tid, nxt))
        cur = nxt
    return steps


def _build_witness(
    graph: Graph,
    model: OperationAssuranceModel,
    *,
    property_id: str,
    witness_kind: str,
    prefix_path: list[tuple[State, str, State]],
    cycle_path: list[tuple[State, str, State]],
    realizability: str,
    invalidating_gap_ids: tuple[str, ...],
    limitations: tuple[str, ...],
    repair_candidates: tuple[RepairCandidate, ...],
) -> Counterexample:
    initial_sd = _state_dict(graph.initial, graph.var_order)
    prefix_ids = tuple(tid for (_f, tid, _t) in prefix_path)
    cycle_ids = tuple(tid for (_f, tid, _t) in cycle_path)
    deltas = []
    for i, (f, tid, t) in enumerate(prefix_path):
        deltas.append(_state_delta(graph, f, tid, t, "PREFIX", i))
    for i, (f, tid, t) in enumerate(cycle_path):
        deltas.append(_state_delta(graph, f, tid, t, "CYCLE", i))
    reasons = []
    for i, (f, _tid, _t) in enumerate(prefix_path):
        reasons.append(_transition_reason_snapshot(graph, f, "PREFIX", i))
    for i, (f, _tid, _t) in enumerate(cycle_path):
        reasons.append(_transition_reason_snapshot(graph, f, "CYCLE", i))
    final_state = cycle_path[-1][2] if cycle_path else (prefix_path[-1][2] if prefix_path else graph.initial)
    reasons.append(_transition_reason_snapshot(graph, final_state, "FINAL", 0))

    body_without_id = dict(
        witness_kind=witness_kind,
        property_id=property_id,
        realizability=realizability,
        validation_refs=(),
        invalidating_gap_ids=invalidating_gap_ids,
        initial_state=tuple(sorted(initial_sd.items())),
        shortest_prefix=prefix_ids,
        cycle=cycle_ids,
        state_delta_per_step=tuple(deltas),
        enabled_and_disabled_transition_reasons=tuple(reasons),
        source_refs=(),
        repair_candidates=repair_candidates,
        limitations=limitations,
    )
    placeholder = Counterexample(counterexample_id="ocx_placeholder", **body_without_id)
    serialized = {k: v for k, v in placeholder.to_dict().items() if k != "counterexample_id"}
    cid = compute_counterexample_id(model.model_hash, serialized)
    return Counterexample(counterexample_id=cid, **body_without_id)


# ---------------------------------------------------------------------------
# Boundary predicate (terminal / valid gate-wait / valid recurring)
# ---------------------------------------------------------------------------


class Boundaries:
    def __init__(self, graph: Graph, model: OperationAssuranceModel):
        self.graph = graph
        self.model = model
        self._cache: dict[State, bool] = {}
        self._gate_valid_cache: dict[tuple[State, str], bool] = {}

    def gate_valid_at(self, state: State, gate: Gate) -> bool:
        key = (state, gate.gate_id)
        if key not in self._gate_valid_cache:
            sd = _state_dict(state, self.graph.var_order)
            self._gate_valid_cache[key] = _gate_return_valid_at(sd, gate, self.graph, self.model, self.model.terminal_outcomes)
        return self._gate_valid_cache[key]

    def matching_valid_gates(self, state: State) -> tuple[Gate, ...]:
        sd = _state_dict(state, self.graph.var_order)
        out = []
        for g in self.model.external_gates:
            if _gate_state_matches(sd, g) and self.gate_valid_at(state, g):
                out.append(g)
        return tuple(out)

    def matching_incomplete_gates(self, state: State) -> tuple[Gate, ...]:
        sd = _state_dict(state, self.graph.var_order)
        return tuple(
            g for g in self.model.external_gates if _gate_state_matches(sd, g) and not self.gate_valid_at(state, g)
        )

    def is_recurring_valid(self, state: State) -> bool:
        sd = _state_dict(state, self.graph.var_order)
        matches = _matching_outcomes(sd, self.model.recurring_progress_outcomes)
        if not matches:
            return False
        en = self.graph.enabled_at.get(state, ())
        return len(en) > 0

    def is_boundary(self, state: State) -> bool:
        if state in self._cache:
            return self._cache[state]
        sd = _state_dict(state, self.graph.var_order)
        result = bool(_matching_outcomes(sd, self.model.terminal_outcomes)) or bool(
            self.matching_valid_gates(state)
        ) or self.is_recurring_valid(state)
        self._cache[state] = result
        return result


# ---------------------------------------------------------------------------
# Fairness-augmented closed-walk search (Section 14.9)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class LassoResult:
    found: bool
    prefix_path: list[tuple[State, str, State]] = dataclasses.field(default_factory=list)
    cycle_path: list[tuple[State, str, State]] = dataclasses.field(default_factory=list)
    used_fairness: bool = False
    product_complete: bool = True


def _fair_transitions_for(model: OperationAssuranceModel, realizable_fairness_ids: frozenset[str]) -> frozenset[str]:
    return frozenset(
        t.transition_id for t in model.transitions if t.fairness_ref is not None and t.fairness_ref in realizable_fairness_ids
    )


def _search_fair_lasso(
    graph: Graph,
    boundaries: Boundaries,
    entry_candidates: list[State],
    region_predicate,
    fair_transition_ids: frozenset[str],
) -> LassoResult:
    """For each candidate entry state, BFS the augmented product
    (state, seen_or_disabled_mask) restricted to ``region_predicate`` states,
    searching for the shortest closed walk back to the entry with every
    fair transition seen-or-disabled. Returns the globally shortest result
    across all entries (prefix length via graph.prefix_of + cycle length),
    tie-broken by canonical transition sequence then state fingerprint."""
    fair_list = sorted(fair_transition_ids)
    bit_of = {tid: i for i, tid in enumerate(fair_list)}
    full_mask = (1 << len(fair_list)) - 1 if fair_list else 0

    best: tuple | None = None  # (total_len, prefix_ids, cycle_ids, entry, cycle_path)

    for entry in sorted(set(entry_candidates)):
        if not region_predicate(entry):
            continue

        def local_mask(state: State) -> int:
            m = 0
            en = graph.enabled_at.get(state, ())
            for tid, bit in bit_of.items():
                if tid not in en:
                    m |= 1 << bit
            return m

        start_mask = local_mask(entry)
        # augmented BFS. ``closing`` is captured independently of the
        # ``parent`` dedup dict: when fair_list is empty, full_mask == 0 ==
        # start_mask, so a direct self-loop back to (entry, start_mask)
        # would otherwise collide with the entry's own placeholder node and
        # silently reconstruct an empty path. Keeping the closing edge out
        # of ``parent`` sidesteps that collision entirely.
        parent: dict[tuple[State, int], tuple[State, int, str] | None] = {(entry, start_mask): None}
        queue: list[tuple[State, int]] = [(entry, start_mask)]
        qi = 0
        closing: tuple[State, int, str] | None = None
        while qi < len(queue) and closing is None:
            state, mask = queue[qi]
            qi += 1
            for tid, succ in graph.succ_of.get(state, []):
                if not region_predicate(succ):
                    continue
                new_mask = mask
                if tid in bit_of:
                    new_mask |= 1 << bit_of[tid]
                new_mask |= local_mask(succ)
                if succ == entry and new_mask == full_mask:
                    closing = (state, mask, tid)
                    break
                key = (succ, new_mask)
                if key not in parent:
                    parent[key] = (state, mask, tid)
                    queue.append(key)

        if closing is None:
            continue

        from_state, from_mask, closing_tid = closing
        chain: list[tuple[State, str, State]] = []
        cur = (from_state, from_mask)
        while parent[cur] is not None:
            p_state, p_mask, p_tid = parent[cur]
            chain.append((p_state, p_tid, cur[0]))
            cur = (p_state, p_mask)
        chain.reverse()
        cycle_path = chain + [(from_state, closing_tid, entry)]
        cycle_ids = tuple(tid for (_f, tid, _t) in cycle_path)

        prefix_path = _path_from_prefix(graph, entry)
        prefix_ids = tuple(tid for (_f, tid, _t) in prefix_path)
        total_len = len(prefix_ids) + len(cycle_ids)
        candidate = (total_len, prefix_ids, cycle_ids, entry, cycle_path)
        if best is None or candidate[:3] < best[:3]:
            best = candidate

    if best is None:
        return LassoResult(found=False)
    _total, _pfx, _cyc, entry, cycle_path = best
    prefix_path = _path_from_prefix(graph, entry)
    return LassoResult(found=True, prefix_path=prefix_path, cycle_path=cycle_path, used_fairness=bool(fair_list))


# ---------------------------------------------------------------------------
# Property evaluation
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Evaluated:
    property_id: str
    property_kind: str
    status: str
    analysis_complete: bool
    reason_codes: tuple[str, ...]
    counterexample: Counterexample | None
    used_fairness: bool = False


def _mk_pass(pid: str, kind: str, complete: bool = True, reason_codes: tuple[str, ...] = ()) -> Evaluated:
    return Evaluated(pid, kind, "PASS", complete, reason_codes, None)


def _mk_na(pid: str, kind: str, reason_codes: tuple[str, ...]) -> Evaluated:
    return Evaluated(pid, kind, "NOT_APPLICABLE", True, reason_codes, None)


def _mk_unknown(pid: str, kind: str, reason_codes: tuple[str, ...]) -> Evaluated:
    return Evaluated(pid, kind, "UNKNOWN", False, reason_codes, None)


def _mk_fail(pid: str, kind: str, cx: Counterexample, complete: bool = True) -> Evaluated:
    return Evaluated(pid, kind, "FAIL", complete, (), cx)


def _eval_state_forbidden(model, graph: Graph) -> list[Evaluated]:
    out = []
    for p in model.safety_properties:
        if p.kind != "STATE_FORBIDDEN":
            continue
        violating = [s for s in graph.discovered if all(_guard_holds(_state_dict(s, graph.var_order), g) for g in p.violation_when)]
        if violating:
            violating.sort(key=lambda s: (len(graph.prefix_of[s]), graph.prefix_of[s]))
            target = violating[0]
            prefix_path = _path_from_prefix(graph, target)
            cx = _build_witness(
                graph,
                model,
                property_id=p.property_id,
                witness_kind="TRACE",
                prefix_path=prefix_path,
                cycle_path=[],
                realizability="DECLARED_MODEL_ONLY",
                invalidating_gap_ids=(),
                limitations=(),
                repair_candidates=(
                    RepairCandidate(f"rep_{p.property_id}_state", "ADD_OR_CORRECT_TRANSITION", (p.property_id,), "revise the model/source to avoid this state", ()),
                ),
            )
            out.append(_mk_fail(p.property_id, "AUTHORED_STATE_SAFETY", cx))
        else:
            complete = graph.base_graph_complete
            out.append(
                _mk_pass(p.property_id, "AUTHORED_STATE_SAFETY", complete)
                if complete
                else _mk_unknown(p.property_id, "AUTHORED_STATE_SAFETY", ("BOUNDED_EXPLORATION",))
            )
    return out


def _eval_transition_forbidden(model, graph: Graph) -> list[Evaluated]:
    out = []
    transitions_by_id = {t.transition_id: t for t in model.transitions}
    for p in model.safety_properties:
        if p.kind != "TRANSITION_FORBIDDEN":
            continue
        violating_edges = []
        for (s, tid, s2) in graph.all_edges:
            t = transitions_by_id[tid]
            if t.kind not in p.forbidden_transition_kinds:
                continue
            sd = _state_dict(s, graph.var_order)
            if all(_guard_holds(sd, g) for g in p.when):
                violating_edges.append((s, tid, s2))
        if violating_edges:
            violating_edges.sort(key=lambda e: (len(graph.prefix_of[e[0]]) + 1, graph.prefix_of[e[0]] + (e[1],)))
            s, tid, s2 = violating_edges[0]
            prefix_path = _path_from_prefix(graph, s) + [(s, tid, s2)]
            cx = _build_witness(
                graph,
                model,
                property_id=p.property_id,
                witness_kind="TRACE",
                prefix_path=prefix_path,
                cycle_path=[],
                realizability="DECLARED_MODEL_ONLY",
                invalidating_gap_ids=(),
                limitations=(),
                repair_candidates=(
                    RepairCandidate(f"rep_{p.property_id}_transition", "RECONCILE_EFFECT", (tid,), "forbid or gate this transition under the stated condition", ()),
                ),
            )
            out.append(_mk_fail(p.property_id, "AUTHORED_TRANSITION_SAFETY", cx))
        else:
            complete = graph.base_graph_complete
            out.append(
                _mk_pass(p.property_id, "AUTHORED_TRANSITION_SAFETY", complete)
                if complete
                else _mk_unknown(p.property_id, "AUTHORED_TRANSITION_SAFETY", ("BOUNDED_EXPLORATION",))
            )
    return out


def _eval_option_to_complete(model, graph: Graph, boundaries: Boundaries) -> Evaluated:
    failing = []
    any_unknown = False
    for s in graph.discovered:
        status = _forward_reach(s, boundaries.is_boundary, graph)
        if status == "FAIL":
            failing.append(s)
        elif status == "UNKNOWN":
            any_unknown = True
    if failing:
        failing.sort(key=lambda s: (len(graph.prefix_of[s]), graph.prefix_of[s]))
        target = failing[0]
        prefix_path = _path_from_prefix(graph, target)
        cx = _build_witness(
            graph,
            model,
            property_id="OPTION_TO_COMPLETE",
            witness_kind="TRACE",
            prefix_path=prefix_path,
            cycle_path=[],
            realizability="DECLARED_MODEL_ONLY",
            invalidating_gap_ids=(),
            limitations=(),
            repair_candidates=(
                RepairCandidate("rep_option_to_complete", "ADD_OR_CORRECT_TERMINAL_OUTCOME", (), "add a reachable terminal, gate, wait, or recurring boundary from this state", ()),
            ),
        )
        return _mk_fail("OPTION_TO_COMPLETE", "OPTION_TO_COMPLETE", cx)
    if any_unknown or not graph.base_graph_complete:
        return _mk_unknown("OPTION_TO_COMPLETE", "OPTION_TO_COMPLETE", ("BOUNDED_EXPLORATION",))
    return _mk_pass("OPTION_TO_COMPLETE", "OPTION_TO_COMPLETE")


def _residue_violation(sd: dict[str, str], model, matching: tuple[Outcome, ...]) -> str | None:
    owned_obl = set()
    owned_res = set()
    for o in matching:
        owned_obl |= set(o.owned_persistent_obligation_ids)
        owned_res |= set(o.owned_persistent_resource_ids)
    for ob in model.obligations:
        pending = sd[ob.state_variable] in ob.pending_values
        if not pending:
            continue
        if not ob.persistent:
            return f"NON_PERSISTENT_OBLIGATION_PENDING:{ob.obligation_id}"
        if ob.obligation_id not in owned_obl:
            return f"UNOWNED_PERSISTENT_OBLIGATION:{ob.obligation_id}"
    for r in model.resources:
        held = sd[r.holder_variable] not in r.released_values
        if not held:
            continue
        if not r.persistent:
            return f"NON_PERSISTENT_RESOURCE_HELD:{r.resource_id}"
        if r.resource_id not in owned_res:
            return f"UNOWNED_PERSISTENT_RESOURCE:{r.resource_id}"
    return None


def _eval_proper_completion(model, graph: Graph) -> Evaluated:
    failing = []
    for s in graph.discovered:
        sd = _state_dict(s, graph.var_order)
        matching = _matching_outcomes(sd, model.terminal_outcomes)
        if not matching:
            continue
        if len(matching) > 1 and len({o.kind for o in matching}) > 1:
            failing.append((s, "AMBIGUOUS_TERMINAL_CLASSIFICATION"))
            continue
        if graph.enabled_at.get(s, ()):
            failing.append((s, "TERMINAL_STATE_NOT_ABSORBING"))
            continue
        reason = _residue_violation(sd, model, matching)
        if reason:
            failing.append((s, reason))
    if failing:
        failing.sort(key=lambda item: (len(graph.prefix_of[item[0]]), graph.prefix_of[item[0]]))
        target, reason = failing[0]
        prefix_path = _path_from_prefix(graph, target)
        cx = _build_witness(
            graph,
            model,
            property_id="PROPER_COMPLETION",
            witness_kind="TRACE",
            prefix_path=prefix_path,
            cycle_path=[],
            realizability="DECLARED_MODEL_ONLY",
            invalidating_gap_ids=(),
            limitations=(reason,),
            repair_candidates=(
                RepairCandidate("rep_proper_completion", "DISCHARGE_OBLIGATION", (), "discharge pending non-persistent residue or explicitly own it as persistent before terminal completion", ()),
            ),
        )
        return _mk_fail("PROPER_COMPLETION", "PROPER_COMPLETION", cx)
    if not graph.base_graph_complete:
        return _mk_unknown("PROPER_COMPLETION", "PROPER_COMPLETION", ("BOUNDED_EXPLORATION",))
    return _mk_pass("PROPER_COMPLETION", "PROPER_COMPLETION")


def _eval_no_dead_required_transition(model, graph: Graph) -> Evaluated:
    required = [t.transition_id for t in model.transitions if t.required_reachable]
    if not required:
        return _mk_pass("NO_DEAD_REQUIRED_TRANSITION", "NO_DEAD_REQUIRED_TRANSITION")
    used = {tid for (_s, tid, _s2) in graph.all_edges}
    missing = sorted(t for t in required if t not in used)
    if not missing:
        return _mk_pass("NO_DEAD_REQUIRED_TRANSITION", "NO_DEAD_REQUIRED_TRANSITION")
    if not graph.base_graph_complete:
        return _mk_unknown("NO_DEAD_REQUIRED_TRANSITION", "NO_DEAD_REQUIRED_TRANSITION", ("BOUNDED_EXPLORATION",))
    cx = _build_witness(
        graph,
        model,
        property_id="NO_DEAD_REQUIRED_TRANSITION",
        witness_kind="GLOBAL_CERTIFICATE",
        prefix_path=[],
        cycle_path=[],
        realizability="DECLARED_MODEL_ONLY",
        invalidating_gap_ids=(),
        limitations=(f"MISSING_TRANSITION:{missing[0]}",),
        repair_candidates=(
            RepairCandidate("rep_dead_transition", "ADD_OR_CORRECT_TRANSITION", (missing[0],), "make this required transition reachable or remove required_reachable", ()),
        ),
    )
    return _mk_fail("NO_DEAD_REQUIRED_TRANSITION", "NO_DEAD_REQUIRED_TRANSITION", cx)


def _eval_no_post_terminal_transition(model, graph: Graph) -> Evaluated:
    failing = []
    for s in graph.discovered:
        sd = _state_dict(s, graph.var_order)
        if not _matching_outcomes(sd, model.terminal_outcomes):
            continue
        if graph.enabled_at.get(s, ()):
            failing.append(s)
    if failing:
        failing.sort(key=lambda s: (len(graph.prefix_of[s]), graph.prefix_of[s]))
        target = failing[0]
        prefix_path = _path_from_prefix(graph, target)
        enabled_tid = graph.enabled_at[target][0]
        succ = dict(graph.succ_of.get(target, [])).get(enabled_tid)
        extra = [(target, enabled_tid, succ)] if succ is not None else []
        cx = _build_witness(
            graph,
            model,
            property_id="NO_POST_TERMINAL_TRANSITION",
            witness_kind="TRACE",
            prefix_path=prefix_path + extra,
            cycle_path=[],
            realizability="DECLARED_MODEL_ONLY",
            invalidating_gap_ids=(),
            limitations=(),
            repair_candidates=(
                RepairCandidate("rep_terminal_absorption", "ADD_OR_CORRECT_TERMINAL_OUTCOME", (enabled_tid,), "remove or guard this transition so terminal states are absorbing", ()),
            ),
        )
        return _mk_fail("NO_POST_TERMINAL_TRANSITION", "NO_POST_TERMINAL_TRANSITION", cx)
    if not graph.base_graph_complete:
        return _mk_unknown("NO_POST_TERMINAL_TRANSITION", "NO_POST_TERMINAL_TRANSITION", ("BOUNDED_EXPLORATION",))
    return _mk_pass("NO_POST_TERMINAL_TRANSITION", "NO_POST_TERMINAL_TRANSITION")


def _eval_gate_or_wait_return_path_valid(model, graph: Graph, boundaries: Boundaries) -> Evaluated:
    failing = []
    for s in graph.discovered:
        incomplete_gates = boundaries.matching_incomplete_gates(s)
        for g in incomplete_gates:
            failing.append((s, g))
    if failing:
        failing.sort(key=lambda item: (len(graph.prefix_of[item[0]]), graph.prefix_of[item[0]]))
        target, gate = failing[0]
        prefix_path = _path_from_prefix(graph, target)
        cx = _build_witness(
            graph,
            model,
            property_id="GATE_OR_WAIT_RETURN_PATH_VALID",
            witness_kind="TRACE",
            prefix_path=prefix_path,
            cycle_path=[],
            realizability="DECLARED_MODEL_ONLY",
            invalidating_gap_ids=(),
            limitations=(f"EXTERNAL_GATE_INCOMPLETE:{gate.gate_id}",),
            repair_candidates=(
                RepairCandidate("rep_gate_return", "ADD_OR_CORRECT_GATE_RETURN", (gate.gate_id,), "ensure a release transition is enabled and valid at every state matching this gate", ()),
            ),
        )
        return _mk_fail("GATE_OR_WAIT_RETURN_PATH_VALID", "GATE_OR_WAIT_RETURN_PATH_VALID", cx)
    if not graph.base_graph_complete:
        return _mk_unknown("GATE_OR_WAIT_RETURN_PATH_VALID", "GATE_OR_WAIT_RETURN_PATH_VALID", ("BOUNDED_EXPLORATION",))
    return _mk_pass("GATE_OR_WAIT_RETURN_PATH_VALID", "GATE_OR_WAIT_RETURN_PATH_VALID")


def _eval_fairness_realizable(model, graph: Graph) -> tuple[Evaluated, frozenset[str]]:
    if not model.fairness_assumptions:
        return _mk_na("FAIRNESS_REALIZABLE", "FAIRNESS_REALIZABLE", ("NO_FAIRNESS_DECLARED",)), frozenset()
    used_tids = {tid for (_s, tid, _s2) in graph.all_edges}
    realizable_ids = set()
    unrealizable_ids = []
    unknown_any = False
    for f in model.fairness_assumptions:
        if any(tid in used_tids for tid in f.transition_ids):
            realizable_ids.add(f.fairness_id)
        elif not graph.base_graph_complete:
            unknown_any = True
        else:
            unrealizable_ids.append(f.fairness_id)
    if unrealizable_ids:
        cx = _build_witness(
            graph,
            model,
            property_id="FAIRNESS_REALIZABLE",
            witness_kind="GLOBAL_CERTIFICATE",
            prefix_path=[],
            cycle_path=[],
            realizability="DECLARED_MODEL_ONLY",
            invalidating_gap_ids=(),
            limitations=(f"UNREALIZABLE_FAIRNESS:{unrealizable_ids[0]}",),
            repair_candidates=(
                RepairCandidate("rep_fairness", "REVISE_FAIRNESS_ASSUMPTION", tuple(unrealizable_ids), "the declared fairness assumption never becomes enabled anywhere reachable", ()),
            ),
        )
        return _mk_fail("FAIRNESS_REALIZABLE", "FAIRNESS_REALIZABLE", cx), frozenset(realizable_ids)
    if unknown_any or not graph.base_graph_complete:
        return _mk_unknown("FAIRNESS_REALIZABLE", "FAIRNESS_REALIZABLE", ("BOUNDED_EXPLORATION",)), frozenset(realizable_ids)
    return _mk_pass("FAIRNESS_REALIZABLE", "FAIRNESS_REALIZABLE"), frozenset(realizable_ids)


def _eval_universal_progress(model, graph: Graph, boundaries: Boundaries, fair_transition_ids: frozenset[str]) -> Evaluated:
    def region(s: State) -> bool:
        return not boundaries.is_boundary(s)

    entries = [s for s in graph.discovered if region(s)]
    result = _search_fair_lasso(graph, boundaries, entries, region, fair_transition_ids)
    if result.found:
        cx = _build_witness(
            graph,
            model,
            property_id="UNIVERSAL_PROGRESS",
            witness_kind="LASSO",
            prefix_path=result.prefix_path,
            cycle_path=result.cycle_path,
            realizability="DECLARED_MODEL_ONLY",
            invalidating_gap_ids=(),
            limitations=(),
            repair_candidates=(
                RepairCandidate("rep_universal_progress", "ADD_OR_CORRECT_TERMINAL_OUTCOME", (), "this closed walk never reaches a terminal, valid gate/wait, or recurring boundary", ()),
            ),
        )
        return _mk_fail("UNIVERSAL_PROGRESS", "UNIVERSAL_PROGRESS", cx)
    if not graph.base_graph_complete:
        return _mk_unknown("UNIVERSAL_PROGRESS", "UNIVERSAL_PROGRESS", ("BOUNDED_EXPLORATION",))
    ev = _mk_pass("UNIVERSAL_PROGRESS", "UNIVERSAL_PROGRESS")
    ev.used_fairness = bool(fair_transition_ids)
    return ev


def _eval_no_starvation(model, graph: Graph, boundaries: Boundaries, fair_transition_ids: frozenset[str]) -> Evaluated:
    persistent_obligations = [o for o in model.obligations if o.persistent]
    if not persistent_obligations:
        return _mk_na("NO_STARVATION_UNDER_DECLARED_FAIRNESS", "NO_STARVATION_UNDER_DECLARED_FAIRNESS", ("NO_PERSISTENT_OBLIGATION",))

    best: LassoResult | None = None
    best_ob = None
    any_incomplete = False
    for ob in persistent_obligations:
        def region(s: State, ob=ob) -> bool:
            sd = _state_dict(s, graph.var_order)
            pending = sd[ob.state_variable] in ob.pending_values
            return pending and not boundaries.is_boundary(s)

        entries = [s for s in graph.discovered if region(s)]
        result = _search_fair_lasso(graph, boundaries, entries, region, fair_transition_ids)
        if result.found:
            total = len(result.prefix_path) + len(result.cycle_path)
            if best is None or total < (len(best.prefix_path) + len(best.cycle_path)):
                best = result
                best_ob = ob

    if best is not None:
        cx = _build_witness(
            graph,
            model,
            property_id="NO_STARVATION_UNDER_DECLARED_FAIRNESS",
            witness_kind="LASSO",
            prefix_path=best.prefix_path,
            cycle_path=best.cycle_path,
            realizability="DECLARED_MODEL_ONLY",
            invalidating_gap_ids=(),
            limitations=(f"PENDING_OBLIGATION:{best_ob.obligation_id}",),
            repair_candidates=(
                RepairCandidate("rep_starvation", "DISCHARGE_OBLIGATION", (best_ob.obligation_id,), "this fairness-valid closed walk keeps a persistent obligation pending forever", ()),
            ),
        )
        return _mk_fail("NO_STARVATION_UNDER_DECLARED_FAIRNESS", "NO_STARVATION_UNDER_DECLARED_FAIRNESS", cx)
    if not graph.base_graph_complete:
        return _mk_unknown("NO_STARVATION_UNDER_DECLARED_FAIRNESS", "NO_STARVATION_UNDER_DECLARED_FAIRNESS", ("BOUNDED_EXPLORATION",))
    ev = _mk_pass("NO_STARVATION_UNDER_DECLARED_FAIRNESS", "NO_STARVATION_UNDER_DECLARED_FAIRNESS")
    ev.used_fairness = bool(fair_transition_ids)
    return ev


def _eval_recurring_progress_valid(model, graph: Graph) -> Evaluated:
    if not model.recurring_progress_outcomes:
        return _mk_na("RECURRING_PROGRESS_VALID", "RECURRING_PROGRESS_VALID", ("NO_RECURRING_OUTCOME_DECLARED",))
    failing = []
    for s in graph.discovered:
        sd = _state_dict(s, graph.var_order)
        matching = _matching_outcomes(sd, model.recurring_progress_outcomes)
        if not matching:
            continue
        if not graph.enabled_at.get(s, ()):
            failing.append((s, "RECURRING_STATE_HAS_NO_CONTINUATION"))
            continue
        reason = _residue_violation(sd, model, matching)
        if reason:
            failing.append((s, reason))
    if failing:
        failing.sort(key=lambda item: (len(graph.prefix_of[item[0]]), graph.prefix_of[item[0]]))
        target, reason = failing[0]
        prefix_path = _path_from_prefix(graph, target)
        cx = _build_witness(
            graph,
            model,
            property_id="RECURRING_PROGRESS_VALID",
            witness_kind="TRACE",
            prefix_path=prefix_path,
            cycle_path=[],
            realizability="DECLARED_MODEL_ONLY",
            invalidating_gap_ids=(),
            limitations=(reason,),
            repair_candidates=(
                RepairCandidate("rep_recurring", "ADD_OR_CORRECT_RECURRING_OUTCOME", (), "this recurring outcome cannot recur or continue, or owns undeclared residue", ()),
            ),
        )
        return _mk_fail("RECURRING_PROGRESS_VALID", "RECURRING_PROGRESS_VALID", cx)
    if not graph.base_graph_complete:
        return _mk_unknown("RECURRING_PROGRESS_VALID", "RECURRING_PROGRESS_VALID", ("BOUNDED_EXPLORATION",))
    return _mk_pass("RECURRING_PROGRESS_VALID", "RECURRING_PROGRESS_VALID")


# ---------------------------------------------------------------------------
# Verdict / disposition / recommendation composition
# ---------------------------------------------------------------------------


def _fidelity_proof_eligible(model: OperationAssuranceModel) -> bool:
    return model.abstraction_contract.kind == "DECLARED_EXACT"


def _compose_source_applicability(model: OperationAssuranceModel) -> str:
    sources = model.source_snapshot.sources
    if any(s.conflict == "CONFLICT" for s in sources):
        return "CONFLICTED"
    if any(s.freshness == "STALE" for s in sources):
        return "STALE"
    if any(s.coverage == "PARTIAL" or s.truncated or s.continuation is not None for s in sources):
        return "INCOMPLETE"
    if any(s.freshness == "UNKNOWN" or s.conflict == "UNKNOWN" or s.coverage == "UNKNOWN" for s in sources):
        return "UNKNOWN"
    return "AUTHOR_DECLARED_ONLY"


def _compose_progress_disposition(evaluated: dict[str, Evaluated]) -> str:
    option = evaluated["OPTION_TO_COMPLETE"]
    universal = evaluated["UNIVERSAL_PROGRESS"]
    starvation = evaluated["NO_STARVATION_UNDER_DECLARED_FAIRNESS"]
    recurring = evaluated["RECURRING_PROGRESS_VALID"]

    if option.status == "FAIL" or universal.status == "FAIL" or starvation.status == "FAIL":
        return "NO_PROGRESS"
    if evaluated.get("_reached_external_gate"):
        return "EXTERNALLY_GATED"
    if evaluated.get("_reached_intentional_wait"):
        return "INTENTIONAL_WAIT"
    if recurring.status == "PASS" and evaluated.get("_reached_recurring"):
        return "RECURRING_SERVICE"
    if universal.status == "PASS" and universal.used_fairness:
        return "FAIRNESS_CONDITIONAL"
    if all(evaluated[k].status in ("PASS", "NOT_APPLICABLE") for k in ("OPTION_TO_COMPLETE", "UNIVERSAL_PROGRESS", "NO_STARVATION_UNDER_DECLARED_FAIRNESS")):
        return "AUTONOMOUSLY_LIVE"
    return "UNKNOWN"


def _compose_admission_recommendation(
    model_analysis_verdict: str,
    source_applicability: str,
    progress_disposition: str,
    any_fail: bool,
) -> str:
    if source_applicability in ("CONFLICTED", "STALE"):
        return "REPORT_ONLY_RECONCILE"
    if model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE":
        return "REPORT_ONLY_REPAIR"
    if (
        not any_fail
        and progress_disposition in ("EXTERNALLY_GATED", "INTENTIONAL_WAIT")
        and model_analysis_verdict in ("PROVEN_WITHIN_FINITE_MODEL", "BOUNDED_NO_COUNTEREXAMPLE")
    ):
        return "REPORT_ONLY_AWAIT_GATE"
    return "REPORT_ONLY_NO_RECOMMENDATION"


def run_checker(
    model: OperationAssuranceModel,
    *,
    generated_at: str,
    supersedes_report_id: str | None = None,
) -> OperationAssuranceReport:
    try:
        return _run_checker_inner(model, generated_at=generated_at, supersedes_report_id=supersedes_report_id)
    except CheckerInternalError:
        raise
    except Exception as exc:  # pragma: no cover - defense in depth
        raise CheckerInternalError(str(exc)) from exc


def _run_checker_inner(
    model: OperationAssuranceModel,
    *,
    generated_at: str,
    supersedes_report_id: str | None,
) -> OperationAssuranceReport:
    graph = explore(model)
    boundaries = Boundaries(graph, model)

    fairness_realizable_eval, realizable_fairness_ids = _eval_fairness_realizable(model, graph)
    fair_transition_ids = _fair_transitions_for(model, realizable_fairness_ids)

    evaluated: dict[str, Evaluated] = {}
    for e in _eval_state_forbidden(model, graph):
        evaluated[e.property_id] = e
    for e in _eval_transition_forbidden(model, graph):
        evaluated[e.property_id] = e

    evaluated["OPTION_TO_COMPLETE"] = _eval_option_to_complete(model, graph, boundaries)
    evaluated["PROPER_COMPLETION"] = _eval_proper_completion(model, graph)
    evaluated["NO_DEAD_REQUIRED_TRANSITION"] = _eval_no_dead_required_transition(model, graph)
    evaluated["NO_POST_TERMINAL_TRANSITION"] = _eval_no_post_terminal_transition(model, graph)
    evaluated["GATE_OR_WAIT_RETURN_PATH_VALID"] = _eval_gate_or_wait_return_path_valid(model, graph, boundaries)
    evaluated["UNIVERSAL_PROGRESS"] = _eval_universal_progress(model, graph, boundaries, fair_transition_ids)
    evaluated["RECURRING_PROGRESS_VALID"] = _eval_recurring_progress_valid(model, graph)
    evaluated["NO_STARVATION_UNDER_DECLARED_FAIRNESS"] = _eval_no_starvation(model, graph, boundaries, fair_transition_ids)
    evaluated["FAIRNESS_REALIZABLE"] = fairness_realizable_eval

    reached_external_gate = False
    reached_intentional_wait = False
    reached_recurring = False
    for s in graph.discovered:
        for g in boundaries.matching_valid_gates(s):
            if g.disposition == "EXTERNAL_GATE":
                reached_external_gate = True
            else:
                reached_intentional_wait = True
        if boundaries.is_recurring_valid(s):
            reached_recurring = True
    evaluated["_reached_external_gate"] = reached_external_gate
    evaluated["_reached_intentional_wait"] = reached_intentional_wait
    evaluated["_reached_recurring"] = reached_recurring

    property_results = []
    counterexamples: list[Counterexample] = []
    for pid, e in evaluated.items():
        if pid.startswith("_"):
            continue
        cx_id = None
        if e.counterexample is not None:
            counterexamples.append(e.counterexample)
            cx_id = e.counterexample.counterexample_id
        property_results.append(
            PropertyResult(
                property_id=e.property_id,
                property_kind=e.property_kind,
                status=e.status,
                analysis_complete=e.analysis_complete,
                counterexample_id=cx_id,
                reason_codes=e.reason_codes,
                source_refs=(),
            )
        )
    property_results.sort(key=lambda r: r.property_id)
    counterexamples.sort(key=lambda c: (c.property_id, c.counterexample_id))

    any_fail = any(r.status == "FAIL" for r in property_results)
    any_unknown = any(r.status == "UNKNOWN" for r in property_results)
    any_load_bearing_gap = any(g.load_bearing for g in model.known_model_gaps)
    fidelity_ok = _fidelity_proof_eligible(model)

    if any_fail and fidelity_ok and not any_load_bearing_gap:
        model_analysis_verdict = "UNSAFE_COUNTEREXAMPLE"
        counterexamples = [dataclasses.replace(c, realizability="DECLARED_MODEL_ONLY") for c in counterexamples]
    elif any_fail and (not fidelity_ok or any_load_bearing_gap):
        model_analysis_verdict = "INCONCLUSIVE_MODEL_GAP"
        counterexamples = [dataclasses.replace(c, realizability="POTENTIALLY_SPURIOUS") for c in counterexamples]
    elif (
        not any_fail
        and not any_unknown
        and graph.base_graph_complete
        and fidelity_ok
        and not any_load_bearing_gap
    ):
        model_analysis_verdict = "PROVEN_WITHIN_FINITE_MODEL"
    elif not any_fail and (not graph.base_graph_complete or any_unknown) and not any_load_bearing_gap and fidelity_ok:
        model_analysis_verdict = "BOUNDED_NO_COUNTEREXAMPLE"
    else:
        model_analysis_verdict = "INCONCLUSIVE_MODEL_GAP"

    # recompute counterexample ids after realizability rewrite (identity depends on body)
    fixed_cx = []
    id_remap = {}
    for c in counterexamples:
        body = {k: v for k, v in c.to_dict().items() if k != "counterexample_id"}
        new_id = compute_counterexample_id(model.model_hash, body)
        id_remap[c.counterexample_id] = new_id if c.counterexample_id != new_id else c.counterexample_id
        fixed_cx.append(dataclasses.replace(c, counterexample_id=id_remap.get(c.counterexample_id, c.counterexample_id)))
    counterexamples = fixed_cx
    property_results = [
        dataclasses.replace(r, counterexample_id=id_remap.get(r.counterexample_id, r.counterexample_id))
        if r.counterexample_id is not None
        else r
        for r in property_results
    ]

    source_applicability = _compose_source_applicability(model)
    progress_disposition = _compose_progress_disposition(evaluated)
    admission_recommendation = _compose_admission_recommendation(
        model_analysis_verdict, source_applicability, progress_disposition, any_fail
    )

    mandatory_ids = set(_GENERIC_MANDATORY_ORDER)
    authored_ids = {p.property_id for p in model.safety_properties}
    evaluated_ids = {r.property_id for r in property_results}
    complete_ids = {r.property_id for r in property_results if r.analysis_complete}
    incomplete_ids = evaluated_ids - complete_ids
    na_ids = {r.property_id for r in property_results if r.status == "NOT_APPLICABLE"}
    complete_ids -= na_ids

    coverage = Coverage(
        mandatory_property_ids=tuple(sorted(mandatory_ids)),
        authored_property_ids=tuple(sorted(authored_ids)),
        evaluated_property_ids=tuple(sorted(evaluated_ids)),
        complete_property_ids=tuple(sorted(complete_ids)),
        incomplete_property_ids=tuple(sorted(incomplete_ids)),
        not_applicable_property_ids=tuple(sorted(na_ids)),
    )

    # A fairness assumption is reported as "used to exclude candidates" only
    # when it is both realizable and actually load-bearing for a passing
    # fairness-dependent property (UNIVERSAL_PROGRESS or
    # NO_STARVATION_UNDER_DECLARED_FAIRNESS) in this report — never merely
    # because it was declared.
    _fairness_load_bearing = evaluated["UNIVERSAL_PROGRESS"].used_fairness or evaluated[
        "NO_STARVATION_UNDER_DECLARED_FAIRNESS"
    ].used_fairness
    fairness_used_ids = (
        tuple(sorted(f.fairness_id for f in model.fairness_assumptions if f.fairness_id in realizable_fairness_ids))
        if fair_transition_ids and _fairness_load_bearing
        else ()
    )
    assumptions = Assumptions(
        declared_fairness_assumption_ids=tuple(sorted(f.fairness_id for f in model.fairness_assumptions)),
        fairness_assumption_ids_used_to_exclude_candidates=fairness_used_ids,
        declared_environment_assumption_ids=tuple(sorted(a.assumption_id for a in model.environment_assumptions)),
        environment_assumption_ids_required_by_results=(),
    )

    analysis_products = tuple(
        AnalysisProduct(
            analysis_id=pid,
            complete=(pid in complete_ids or pid in na_ids),
            states_examined=len(graph.discovered),
            transitions_considered=graph.transitions_considered,
            limit_reason=(
                "STATE_LIMIT_REACHED"
                if graph.state_limit_reached and pid not in complete_ids and pid not in na_ids
                else ("DEPTH_LIMIT_REACHED" if graph.depth_limit_reached and pid not in complete_ids and pid not in na_ids else None)
            ),
        )
        for pid in sorted(evaluated_ids)
    )

    exploration_receipt = ExplorationReceipt(
        checker_terminated_normally=True,
        base_graph_complete=graph.base_graph_complete,
        declared_limits={"max_states": model.exploration_limits.max_states, "max_depth": model.exploration_limits.max_depth},
        states_discovered=len(graph.discovered),
        edges_materialized=len(graph.all_edges),
        transitions_considered=graph.transitions_considered,
        maximum_depth_reached=max(graph.discovered.values()) if graph.discovered else 0,
        peak_frontier=graph.peak_frontier,
        state_limit_reached=graph.state_limit_reached,
        depth_limit_reached=graph.depth_limit_reached,
        analysis_products=analysis_products,
    )

    return build_report(
        model_id=model.model_id,
        model_hash=model.model_hash,
        source_snapshot_hash=model.source_snapshot.snapshot_hash,
        checker_version=CHECKER_VERSION,
        property_set_version=model.property_set,
        model_analysis_verdict=model_analysis_verdict,
        source_applicability_at_generation=source_applicability,
        abstraction_contract=model.abstraction_contract,
        progress_disposition=progress_disposition,
        admission_recommendation=admission_recommendation,
        property_results=tuple(property_results),
        counterexamples=tuple(counterexamples),
        coverage=coverage,
        assumptions=assumptions,
        known_model_gaps=model.known_model_gaps,
        exploration_receipt=exploration_receipt,
        generated_at=generated_at,
        supersedes_report_id=supersedes_report_id,
    )
