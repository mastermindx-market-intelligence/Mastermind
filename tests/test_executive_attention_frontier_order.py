"""Matrix suite for the Executive Attention Frontier order / fairness laws.

Controlling contract: ``control_plane/executive_attention_frontier.py`` and the
F0G consolidated contract it cites.  This file proves four families of law over
``compute_attention_frontier``:

A. **Partial order algebra** — ``DOMINATES`` really is a strict partial order
   (irreflexive, antisymmetric, transitive), ``INCOMPARABLE_TRADEOFF`` is
   symmetric, any unknown load-bearing dimension collapses to
   ``INCOMPARABLE_UNKNOWN``, and no hidden totalization sneaks in through input
   order or demand-id collation.
B. **Fairness / anti-starvation** — a fully-hidden ordinary partition still
   exposes exactly one oldest-ready sentinel, unknown ready age is a reported
   coverage gap rather than age zero, and fairness never launders an interrupt
   or upgrades a class.
C. **Concurrent demand** — independent interrupt roots, exact-root fan-in,
   proven window collisions, and the honest ``UNKNOWN`` feasibility floor.
D. **Bundle determinism** — stable ``bundle_id``, interrupt-canonical faces, and
   per-member authority/serviceability boundaries that survive compaction.

Everything here is pure: no clock, no I/O (bar one deliberate subprocess that
proves cross-process determinism), and every random corpus is seeded.

Tests that fail are *not* to be weakened: each failing test names the exact law
the engine breaks.  See the ``ENGINE DEFECTS FOUND`` note in the task report.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import os
import random
import subprocess
import sys
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path

import pytest

from control_plane.executive_attention_frontier import (
    ActionTarget,
    AdmissionSource,
    AttentionClass,
    AttentionDemand,
    AuthorityRequirement,
    AutonomousProgress,
    BlastRadius,
    Blocker,
    BurnState,
    Comparison,
    ConcurrentDemand,
    CostOfDelay,
    Fact,
    FaninKind,
    FaninRoot,
    FrontierItem,
    FrontierResult,
    ImpactState,
    Issue,
    ProjectionRelation,
    Reversibility,
    ServiceFeasibility,
    ServiceabilityReason,
    TargetState,
    WaitContext,
    WindowPressure,
    compute_attention_frontier,
)
from control_plane.executive_steward import (
    CapacityState,
    EffectState,
    Freshness,
    SourceOwner,
    SourceRef,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_FILE = Path(__file__).resolve()

SNAP = "snap-eaf-order-2026-09-20"
OBSERVED_AT = "2026-09-20T00:00:00Z"

#: The five load-bearing comparison dimensions, mapped to the demand field that
#: carries them.  Reversibility / blast radius / cost-of-delay / age are
#: deliberately *not* here — they are evidence or fairness service, never
#: dominance (F0G §5.2, §5.3, §5.11, §8).
DIMENSIONS = ("window", "impact", "autonomy", "burn", "unblocks")

#: Ways a load-bearing dimension can fail to be knowable.
DEGRADE_MODES = ("absent", "stale", "source_unknown", "conflict")


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def src(
    ref: str,
    owner: SourceOwner = SourceOwner.EXECUTIVE_OS,
    freshness: Freshness = Freshness.CURRENT,
) -> SourceRef:
    """An exact source ref.  ``UNKNOWN`` freshness carries no observed_at."""
    return SourceRef(
        owner=owner,
        ref=ref,
        observed_at=None if freshness is Freshness.UNKNOWN else OBSERVED_AT,
        freshness=freshness,
    )


def demand(
    did: str,
    *,
    authority: AuthorityRequirement | None = AuthorityRequirement.SOL,
    authority_conflict: bool = False,
    authority_freshness: Freshness = Freshness.CURRENT,
    window: WindowPressure | None = WindowPressure.OPEN,
    impact: ImpactState | None = ImpactState.NO_ACTIVE_HARM,
    autonomy: AutonomousProgress | None = AutonomousProgress.PARTIAL_SAFE_PROGRESS,
    burn: BurnState | None = BurnState.NONE,
    unblocks: tuple[str, ...] | None = (),
    reversibility: Reversibility | None = Reversibility.REVERSIBLE,
    blast_radius: BlastRadius | None = None,
    wait: WaitContext | None = None,
    terminal: bool | None = None,
    became_actionable_at: str | None = None,
    ready_freshness: Freshness = Freshness.CURRENT,
    ready_conflict: bool = False,
    cost_of_delay: CostOfDelay | None = None,
    effect_state: EffectState | None = None,
    capacity_state: CapacityState | None = None,
    action_target: ActionTarget | None = None,
    blockers: tuple[Blocker, ...] = (),
    fanin_roots: tuple[FaninRoot, ...] = (),
    title: str | None = None,
    responsibility_ref: str | None = None,
    degraded: Sequence[str] = (),
    degrade_mode: str = "stale",
) -> AttentionDemand:
    """One admitted demand.

    ``None`` for a dimension means *the fact is absent*.  ``degraded`` names the
    dimensions whose **source** is degraded per ``degrade_mode`` — the value is
    still supplied, but its provenance can no longer ground a claim.
    """

    def fact(value, name: str, *, owner=SourceOwner.EXECUTIVE_OS):
        if value is None:
            return None
        freshness, conflict = Freshness.CURRENT, False
        if name in degraded:
            if degrade_mode == "stale":
                freshness = Freshness.STALE
            elif degrade_mode == "source_unknown":
                freshness = Freshness.UNKNOWN
            elif degrade_mode == "conflict":
                conflict = True
            else:  # pragma: no cover - guards a typo in a parametrisation
                raise AssertionError(f"unknown degrade mode {degrade_mode!r}")
        return Fact(
            value=value,
            source=src(f"{name}:{did}", owner=owner, freshness=freshness),
            conflict=conflict,
        )

    authority_fact = None
    if authority is not None:
        authority_fact = Fact(
            value=authority,
            source=src(f"authority:{did}", freshness=authority_freshness),
            conflict=authority_conflict,
        )

    ready_fact = None
    if became_actionable_at is not None:
        ready_fact = Fact(
            value=became_actionable_at,
            source=src(
                f"ready:{did}",
                owner=SourceOwner.EXECUTIVE_INBOX,
                freshness=ready_freshness,
            ),
            conflict=ready_conflict,
        )

    return AttentionDemand(
        demand_id=did,
        admitted_via=AdmissionSource.EXECUTIVE_INBOX_OBLIGATION,
        admission_source=src(f"inbox:{did}", owner=SourceOwner.EXECUTIVE_INBOX),
        title=title if title is not None else f"order fixture {did}",
        responsibility_ref=responsibility_ref,
        authority=authority_fact,
        decision_window=fact(window, "window"),
        actual_impact=fact(impact, "impact", owner=SourceOwner.RUNTIME_BINDING),
        blast_radius=fact(blast_radius, "blast"),
        reversibility=fact(reversibility, "reversibility", owner=SourceOwner.AGENT_OS),
        unblocks=fact(unblocks, "unblocks", owner=SourceOwner.AGENT_OS),
        resource_burn=fact(burn, "burn", owner=SourceOwner.CAPACITY),
        autonomous_progress=fact(autonomy, "autonomy", owner=SourceOwner.RUNTIME_BINDING),
        wait=fact(wait, "wait", owner=SourceOwner.AGENT_OS),
        became_actionable_at=ready_fact,
        cost_of_delay=fact(cost_of_delay, "cost", owner=SourceOwner.AGENT_OS),
        effect_state=fact(effect_state, "effect", owner=SourceOwner.RUNTIME_BINDING),
        capacity_state=fact(capacity_state, "capacity", owner=SourceOwner.CAPACITY),
        action_target=fact(action_target, "target", owner=SourceOwner.SURFACE_BINDINGS),
        terminal=fact(terminal, "terminal", owner=SourceOwner.AGENT_OS),
        blockers=blockers,
        fanin_roots=fanin_roots,
    )


def fanin(ref: str, kind: FaninKind = FaninKind.BLOCKER_ROOT) -> FaninRoot:
    return FaninRoot(
        kind=kind,
        ref=ref,
        source=src(f"{kind.value}:{ref}", owner=SourceOwner.AGENT_OS),
    )


def blocker(reason: ServiceabilityReason) -> Blocker:
    return Blocker(reason=reason, source=src(f"blocker:{reason.value}"))


# ---------------------------------------------------------------------------
# Shared dimension vectors
# ---------------------------------------------------------------------------

#: Everything a FOCUS_NOW demand needs so that dropping any ONE dimension still
#: leaves at least one grounded focus trigger — the partition stays stable while
#: the comparison degrades.  Only ``unblocks`` separates STRONG from WEAK.
STRONG = dict(
    window=WindowPressure.NEAR,
    impact=ImpactState.NO_ACTIVE_HARM,
    autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
    burn=BurnState.ACTIVE,
    unblocks=("JOB-A", "JOB-B"),
)
MIDDLE = dict(STRONG, unblocks=("JOB-A",))
WEAK = dict(STRONG, unblocks=())


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------

_INVERSE = {
    Comparison.DOMINATES: Comparison.DOMINATED_BY,
    Comparison.DOMINATED_BY: Comparison.DOMINATES,
    Comparison.EQUIVALENT: Comparison.EQUIVALENT,
    Comparison.INCOMPARABLE_TRADEOFF: Comparison.INCOMPARABLE_TRADEOFF,
    Comparison.INCOMPARABLE_UNKNOWN: Comparison.INCOMPARABLE_UNKNOWN,
    Comparison.INVALID_FOR_COMPARISON: Comparison.INVALID_FOR_COMPARISON,
}


def rel(result: FrontierResult, left: str, right: str) -> Comparison | None:
    """The reported relation of ``left`` to ``right``, or None if uncompared."""
    for a, b, relation in result.comparisons:
        if (a, b) == (left, right):
            return relation
        if (a, b) == (right, left):
            return _INVERSE[relation]
    return None


def item(result: FrontierResult, did: str) -> FrontierItem:
    for entry in result.items:
        if entry.demand_id == did:
            return entry
    raise AssertionError(f"{did} not in result: {[i.demand_id for i in result.items]}")


def visible_ids(result: FrontierResult) -> tuple[str, ...]:
    return tuple(sorted(i.demand_id for i in result.visible()))


def frontier_for(result: FrontierResult, authority: AuthorityRequirement):
    for entry in result.authority_frontiers:
        if entry.authority_requirement is authority:
            return entry
    raise AssertionError(
        f"no frontier for {authority}: "
        f"{[f.authority_requirement.value for f in result.authority_frontiers]}"
    )


def omission_for(result: FrontierResult, did: str):
    for entry in result.omissions:
        if entry.demand_id == did:
            return entry
    return None


def _plain(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _plain(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Mapping):
        return {str(k): _plain(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def serialise(result: FrontierResult) -> str:
    return json.dumps(_plain(result), sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Seeded corpus for the algebra laws
# ---------------------------------------------------------------------------

_WINDOWS = list(WindowPressure)
_IMPACTS = list(ImpactState)
_AUTOS = list(AutonomousProgress)
_BURNS = list(BurnState)
_UNBLOCK_COUNTS = (0, 1, 2, 3)


def _vector(rng: random.Random) -> dict:
    return dict(
        window=rng.choice(_WINDOWS),
        impact=rng.choice(_IMPACTS),
        autonomy=rng.choice(_AUTOS),
        burn=rng.choice(_BURNS),
        unblocks=tuple(f"JOB-{i}" for i in range(rng.choice(_UNBLOCK_COUNTS))),
    )


@lru_cache(maxsize=1)
def corpus() -> tuple[FrontierResult, ...]:
    """30 seeded snapshots of 9 demands built by perturbing a base vector.

    Perturbation (rather than independent draws) is what makes comparable pairs
    common, so the DOMINATES antecedent actually fires hundreds of times instead
    of leaving transitivity vacuously true.
    """
    rng = random.Random(20260920)
    results = []
    for snapshot in range(30):
        base = _vector(rng)
        demands = []
        for index in range(9):
            values = dict(base)
            for dim in rng.sample(sorted(base), rng.randint(0, 2)):
                values[dim] = _vector(rng)[dim]
            demands.append(
                demand(
                    f"d.g{snapshot:02d}{index}",
                    reversibility=rng.choice(list(Reversibility)),
                    became_actionable_at=f"2026-09-{rng.randint(1, 28):02d}T00:00:00Z",
                    **values,
                )
            )
        results.append(
            compute_attention_frontier(demands, snapshot_identity=f"{SNAP}-{snapshot}")
        )
    return tuple(results)


def partitions(result: FrontierResult) -> dict[tuple[str, str], list[str]]:
    """Group visible + omitted items by the engine's own (authority, class) key."""
    grouped: dict[tuple[str, str], list[str]] = {}
    for entry in result.items:
        key = (entry.authority_requirement.value, entry.attention_class.value)
        grouped.setdefault(key, []).append(entry.demand_id)
    return {k: sorted(v) for k, v in grouped.items()}


# ---------------------------------------------------------------------------
# Cross-process determinism probe (imported by the subprocess in test D1)
# ---------------------------------------------------------------------------


def bundle_probe() -> dict:
    """A bundle-bearing snapshot reduced to comparable primitives."""
    root = fanin("JOB-PROBE")
    demands = [
        demand("d.probe.a", fanin_roots=(root,), became_actionable_at="2026-09-01T00:00:00Z", **WEAK),
        demand("d.probe.b", fanin_roots=(root,), became_actionable_at="2026-09-02T00:00:00Z", **MIDDLE),
        demand("d.probe.c", fanin_roots=(root,), became_actionable_at="2026-09-03T00:00:00Z", **STRONG),
    ]
    result = compute_attention_frontier(demands, snapshot_identity=SNAP)
    return {
        "bundle_ids": [b.bundle_id for b in result.bundles],
        "canonical": [b.canonical_demand_id for b in result.bundles],
        "serialised": serialise(result),
    }


_SUBPROCESS_SCRIPT = (
    "import importlib.util, json, sys\n"
    "spec = importlib.util.spec_from_file_location('eaf_order_probe', sys.argv[1])\n"
    "mod = importlib.util.module_from_spec(spec)\n"
    "sys.modules['eaf_order_probe'] = mod\n"
    "spec.loader.exec_module(mod)\n"
    "sys.stdout.write('@@' + json.dumps(mod.bundle_probe()))\n"
)


# ===========================================================================
# A. PARTIAL ORDER ALGEBRA
# ===========================================================================


def test_a1_relation_is_irreflexive_and_clones_are_equivalent():
    """Irreflexivity: nothing dominates itself, and identical demands tie.

    The engine never emits a self pair, never issues a self-referential
    omission receipt, and two demands with identical load-bearing vectors are
    EQUIVALENT — never a dominance that would silently rank one above the other.
    """
    for result in corpus():
        for a, b, _ in result.comparisons:
            assert a != b, f"self comparison emitted for {a}"
        for omission in result.omissions:
            assert omission.covered_by != omission.demand_id, (
                f"{omission.demand_id} is its own dominator"
            )

    clones = [
        demand("d.clone.1", became_actionable_at="2026-09-01T00:00:00Z", **STRONG),
        demand("d.clone.2", became_actionable_at="2026-09-02T00:00:00Z", **STRONG),
    ]
    result = compute_attention_frontier(clones, snapshot_identity=SNAP)
    assert rel(result, "d.clone.1", "d.clone.2") is Comparison.EQUIVALENT
    assert visible_ids(result) == ("d.clone.1", "d.clone.2")
    assert result.omissions == ()


def test_a2_dominance_is_antisymmetric_under_identity_swap():
    """Antisymmetry, proved by re-running with the two identities exchanged.

    Reading the inverse out of one result would be tautological, so each pair is
    recomputed with the fact vectors assigned to the opposite demand_ids.  The
    reported relation must be the exact inverse — identity may never tip a
    dominance claim.
    """
    rng = random.Random(4242)
    compared = 0
    dominances = 0
    for _ in range(90):
        left, right = _vector(rng), _vector(rng)
        forward = compute_attention_frontier(
            [demand("d.left", **left), demand("d.right", **right)],
            snapshot_identity=SNAP,
        )
        swapped = compute_attention_frontier(
            [demand("d.left", **right), demand("d.right", **left)],
            snapshot_identity=SNAP,
        )
        a = rel(forward, "d.left", "d.right")
        b = rel(swapped, "d.left", "d.right")
        if a is None:
            assert b is None, "partition membership must not depend on identity"
            continue
        compared += 1
        if a is Comparison.DOMINATES:
            dominances += 1
        assert b is _INVERSE[a], (
            f"antisymmetry broken: {a} forward but {b} with identities swapped"
        )
    assert compared >= 40, f"only {compared} comparable pairs — corpus too weak"
    assert dominances >= 5, f"only {dominances} dominances — antisymmetry vacuous"


def test_a3_dominance_is_transitive_over_generated_triples():
    """Transitivity of DOMINATES over >=200 seeded triples (F0G §8)."""
    triples = 0
    chains = 0
    violations = []
    for result in corpus():
        for members in partitions(result).values():
            for combo in itertools.combinations(members, 3):
                triples += 1
                for a, b, c in itertools.permutations(combo):
                    if (
                        rel(result, a, b) is Comparison.DOMINATES
                        and rel(result, b, c) is Comparison.DOMINATES
                    ):
                        chains += 1
                        if rel(result, a, c) is not Comparison.DOMINATES:
                            violations.append((a, b, c, rel(result, a, c)))
    assert triples >= 200, f"only {triples} generated triples"
    assert chains >= 50, f"only {chains} dominance chains — transitivity vacuous"
    assert not violations, f"transitivity broken on {violations[:5]}"


def test_a4_equivalence_composes_with_dominance():
    """a == b and b > c implies a > c — ties may not absorb a dominance."""
    chains = 0
    violations = []
    for result in corpus():
        for members in partitions(result).values():
            for a, b, c in itertools.permutations(members, 3):
                if (
                    rel(result, a, b) is Comparison.EQUIVALENT
                    and rel(result, b, c) is Comparison.DOMINATES
                ):
                    chains += 1
                    if rel(result, a, c) is not Comparison.DOMINATES:
                        violations.append((a, b, c, rel(result, a, c)))
    assert chains >= 50, f"only {chains} equivalence chains — law vacuous"
    assert not violations, f"equivalence/dominance composition broken on {violations[:5]}"


def test_a5_incomparable_tradeoff_is_symmetric():
    """A genuine tradeoff reads the same from either side, hand-built and seeded."""
    left = demand(
        "d.trade.left",
        window=WindowPressure.NEAR,
        autonomy=AutonomousProgress.PARTIAL_SAFE_PROGRESS,
        became_actionable_at="2026-09-01T00:00:00Z",
    )
    right = demand(
        "d.trade.right",
        window=WindowPressure.OPEN,
        autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
        became_actionable_at="2026-09-02T00:00:00Z",
    )
    forward = compute_attention_frontier([left, right], snapshot_identity=SNAP)
    assert rel(forward, "d.trade.left", "d.trade.right") is Comparison.INCOMPARABLE_TRADEOFF
    assert rel(forward, "d.trade.right", "d.trade.left") is Comparison.INCOMPARABLE_TRADEOFF

    swapped = compute_attention_frontier(
        [
            demand(
                "d.trade.left",
                window=WindowPressure.OPEN,
                autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
                became_actionable_at="2026-09-02T00:00:00Z",
            ),
            demand(
                "d.trade.right",
                window=WindowPressure.NEAR,
                autonomy=AutonomousProgress.PARTIAL_SAFE_PROGRESS,
                became_actionable_at="2026-09-01T00:00:00Z",
            ),
        ],
        snapshot_identity=SNAP,
    )
    assert rel(swapped, "d.trade.left", "d.trade.right") is Comparison.INCOMPARABLE_TRADEOFF

    seen = 0
    for result in corpus():
        for members in partitions(result).values():
            for a, b in itertools.combinations(members, 2):
                if rel(result, a, b) is Comparison.INCOMPARABLE_TRADEOFF:
                    seen += 1
                    assert rel(result, b, a) is Comparison.INCOMPARABLE_TRADEOFF
    assert seen >= 20, f"only {seen} tradeoff pairs in the corpus"


def test_a6_base_pair_dominates_before_any_dimension_is_degraded():
    """Control for the unknown-dimension matrix: fully-known facts do dominate."""
    result = compute_attention_frontier(
        [demand("d.s", **STRONG), demand("d.w", **WEAK)], snapshot_identity=SNAP
    )
    assert item(result, "d.s").attention_class is AttentionClass.FOCUS_NOW
    assert item(result, "d.w").attention_class is AttentionClass.FOCUS_NOW
    assert rel(result, "d.s", "d.w") is Comparison.DOMINATES
    assert item(result, "d.w").projection_relation is ProjectionRelation.DOMINATED_BY
    assert visible_ids(result) == ("d.s",)


@pytest.mark.parametrize("dim", DIMENSIONS)
@pytest.mark.parametrize("mode", DEGRADE_MODES)
@pytest.mark.parametrize("side", ("d.s", "d.w"))
def test_a7_unknown_dimension_forces_incomparable_unknown(dim: str, mode: str, side: str):
    """Unknown is not zero: one unprovable dimension kills the dominance claim.

    The same STRONG/WEAK pair that DOMINATES in the control above must become
    INCOMPARABLE_UNKNOWN as soon as either side loses one load-bearing
    dimension — whether the fact is absent, stale, of unknown provenance, or
    source-owner-conflicted.  Both demands stay on the frontier: an unprovable
    comparison may never be settled by omission.
    """
    strong, weak = dict(STRONG), dict(WEAK)
    degraded_strong: tuple[str, ...] = ()
    degraded_weak: tuple[str, ...] = ()
    if mode == "absent":
        (strong if side == "d.s" else weak)[dim] = None
    elif side == "d.s":
        degraded_strong = (dim,)
    else:
        degraded_weak = (dim,)

    result = compute_attention_frontier(
        [
            demand("d.s", degraded=degraded_strong, degrade_mode=mode, **strong),
            demand("d.w", degraded=degraded_weak, degrade_mode=mode, **weak),
        ],
        snapshot_identity=SNAP,
    )

    # Partition stability: the law under test is the comparison, not the class.
    assert item(result, "d.s").attention_class is AttentionClass.FOCUS_NOW
    assert item(result, "d.w").attention_class is AttentionClass.FOCUS_NOW

    relation = rel(result, "d.s", "d.w")
    assert relation is Comparison.INCOMPARABLE_UNKNOWN, (
        f"{dim} degraded via {mode} on {side} yielded {relation}"
    )
    assert relation is not Comparison.DOMINATES
    assert visible_ids(result) == ("d.s", "d.w")
    assert result.omissions == ()


def test_a8_no_total_order_incomparable_peers_both_stay_visible():
    """There is no total order: same authority, same class, both roots visible.

    Two genuine tradeoffs plus an exact tie stay three separate roots.  No
    tie-break, age, id or insertion order is allowed to collapse them.
    """
    demands = [
        demand(
            "d.peer.near",
            window=WindowPressure.NEAR,
            autonomy=AutonomousProgress.PARTIAL_SAFE_PROGRESS,
            became_actionable_at="2026-09-01T00:00:00Z",
        ),
        demand(
            "d.peer.stuck",
            window=WindowPressure.OPEN,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            became_actionable_at="2026-09-02T00:00:00Z",
        ),
        demand(
            "d.peer.twin",
            window=WindowPressure.NEAR,
            autonomy=AutonomousProgress.PARTIAL_SAFE_PROGRESS,
            became_actionable_at="2026-09-03T00:00:00Z",
        ),
    ]
    result = compute_attention_frontier(demands, snapshot_identity=SNAP)

    classes = {i.demand_id: i.attention_class for i in result.items}
    assert set(classes.values()) == {AttentionClass.FOCUS_NOW}
    authorities = {i.authority_requirement for i in result.items}
    assert authorities == {AuthorityRequirement.SOL}

    assert rel(result, "d.peer.near", "d.peer.stuck") is Comparison.INCOMPARABLE_TRADEOFF
    assert rel(result, "d.peer.near", "d.peer.twin") is Comparison.EQUIVALENT
    assert rel(result, "d.peer.stuck", "d.peer.twin") is Comparison.INCOMPARABLE_TRADEOFF

    assert visible_ids(result) == ("d.peer.near", "d.peer.stuck", "d.peer.twin")
    assert result.omissions == ()
    assert result.fairness_sentinels == ()
    assert frontier_for(result, AuthorityRequirement.SOL).visible_demand_ids == (
        "d.peer.near",
        "d.peer.stuck",
        "d.peer.twin",
    )


def _totalization_snapshot() -> list[AttentionDemand]:
    """A snapshot exercising bundles, dominance, interrupts, waits and sentinels."""
    shared = fanin("JOB-SHARED")
    return [
        demand(
            "d.mix.int",
            impact=ImpactState.ACTIVE_HARM,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            fanin_roots=(shared,),
            became_actionable_at="2026-09-01T00:00:00Z",
        ),
        demand(
            "d.mix.dom",
            fanin_roots=(shared,),
            became_actionable_at="2026-09-18T00:00:00Z",
            **STRONG,
        ),
        demand("d.mix.sub1", became_actionable_at="2026-09-02T00:00:00Z", **WEAK),
        demand("d.mix.sub2", became_actionable_at="2026-09-03T00:00:00Z", **WEAK),
        demand(
            "d.mix.chair",
            authority=AuthorityRequirement.CHAIRMAN,
            window=WindowPressure.BEFORE_NEXT_FOCUS_BOUNDARY,
            became_actionable_at="2026-09-04T00:00:00Z",
        ),
        demand(
            "d.mix.wait",
            wait=WaitContext(kind="awaiting_ci", review_boundary_reached=False),
            became_actionable_at="2026-09-05T00:00:00Z",
        ),
        demand(
            "d.mix.terminal",
            terminal=True,
            became_actionable_at="2026-09-06T00:00:00Z",
        ),
        demand(
            "d.mix.blocked",
            authority=AuthorityRequirement.COO_OR_WORKER,
            blockers=(blocker(ServiceabilityReason.EXTERNAL_BLOCKER),),
            window=WindowPressure.NEAR,
            became_actionable_at="2026-09-07T00:00:00Z",
        ),
        demand("d.mix.unknown", authority=None, became_actionable_at="2026-09-08T00:00:00Z"),
    ]


def test_a9_result_is_invariant_under_input_permutation():
    """No hidden totalization via insertion order: the result is a set function."""
    demands = _totalization_snapshot()
    canonical = serialise(compute_attention_frontier(demands, snapshot_identity=SNAP))

    reversed_result = compute_attention_frontier(
        list(reversed(demands)), snapshot_identity=SNAP
    )
    assert serialise(reversed_result) == canonical, "reversing input changed the frontier"

    rng = random.Random(99)
    for _ in range(12):
        shuffled = list(demands)
        rng.shuffle(shuffled)
        assert (
            serialise(compute_attention_frontier(shuffled, snapshot_identity=SNAP))
            == canonical
        ), "shuffling input changed the frontier"

    # A generator (single-pass iterable) must be treated identically to a list.
    assert (
        serialise(
            compute_attention_frontier((d for d in demands), snapshot_identity=SNAP)
        )
        == canonical
    )


def test_a10_visibility_is_invariant_under_demand_id_renaming():
    """No hidden totalization via demand_id collation (F0G §8).

    Three demands form a strict chain X > Y > Z on the single ``unblocks``
    dimension; every other dimension is identical, so the partial order is
    completely determined by the facts.  Renaming the demands — a pure bijection
    on identity that changes nothing about the evidence — must not change which
    demands the Chairman/Sol is shown.  Identity is a label, never a rank.
    """
    vectors = {"X": STRONG, "Y": MIDDLE, "Z": WEAK}
    ready = {
        "X": "2026-09-01T00:00:00Z",
        "Y": "2026-09-02T00:00:00Z",
        "Z": "2026-09-03T00:00:00Z",
    }
    # Two namings of the same three demands; the second reverses the collation.
    naming_a = {"X": "d.p1", "Y": "d.p2", "Z": "d.p3"}
    naming_b = {"X": "d.p3", "Y": "d.p2", "Z": "d.p1"}

    outcome = {}
    for label, naming in (("a", naming_a), ("b", naming_b)):
        result = compute_attention_frontier(
            [
                demand(naming[k], became_actionable_at=ready[k], **vectors[k])
                for k in ("X", "Y", "Z")
            ],
            snapshot_identity=SNAP,
        )
        back = {v: k for k, v in naming.items()}
        # Sanity: the partial order itself is identical under both namings.
        assert rel(result, naming["X"], naming["Y"]) is Comparison.DOMINATES
        assert rel(result, naming["Y"], naming["Z"]) is Comparison.DOMINATES
        assert rel(result, naming["X"], naming["Z"]) is Comparison.DOMINATES
        assert result.fairness_sentinels == ()
        outcome[label] = tuple(sorted(back[i.demand_id] for i in result.visible()))

    assert outcome["a"] == outcome["b"], (
        "renaming the demands changed the frontier: "
        f"naming A shows {outcome['a']}, naming B shows {outcome['b']} — "
        "demand_id collation is acting as a hidden total order"
    )
    assert outcome["a"] == ("X",), (
        "only the maximum of a strict chain may be root-visible; "
        f"got {outcome['a']}"
    )


# ===========================================================================
# B. FAIRNESS / ANTI-STARVATION
# ===========================================================================


def _starved_partition(
    *,
    ready: Mapping[str, str | None],
    ready_freshness: Freshness = Freshness.CURRENT,
    ready_conflict: bool = False,
    extra: Sequence[AttentionDemand] = (),
) -> FrontierResult:
    """A SOL partition whose every ordinary demand is compacted out of view.

    Exact-root compaction is the only projection that can empty an ordinary
    partition: the engine refuses to dominance-omit a bundle member, and a
    dominator must itself be root-visible before it may stand in for anything,
    so a dominance chain always leaves its maximum on the frontier.  Here the
    bundle's visible face is the INTERRUPT_NOW member, which is not ordinary
    work — without the anti-starvation sentinel the whole ordinary partition
    would vanish.
    """
    root = fanin("JOB-STORM")
    demands = [
        demand(
            "d.int",
            impact=ImpactState.ACTIVE_HARM,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            fanin_roots=(root,),
            became_actionable_at="2026-09-01T00:00:00Z",
        ),
        demand(
            "d.sub1",
            fanin_roots=(root,),
            became_actionable_at=ready["d.sub1"],
            ready_freshness=ready_freshness,
            ready_conflict=ready_conflict,
            **WEAK,
        ),
        demand(
            "d.sub2",
            fanin_roots=(root,),
            became_actionable_at=ready["d.sub2"],
            ready_freshness=ready_freshness,
            ready_conflict=ready_conflict,
            **WEAK,
        ),
    ]
    demands.extend(extra)
    return compute_attention_frontier(demands, snapshot_identity=SNAP)


def test_b1_fully_hidden_partition_exposes_exactly_one_oldest_sentinel():
    """Anti-starvation (F0G §9): a fully-compacted ordinary partition keeps one seat."""
    result = _starved_partition(
        ready={"d.sub1": "2026-09-02T00:00:00Z", "d.sub2": "2026-09-03T00:00:00Z"}
    )

    # Premise: the bundle's face is the interrupt, so no ordinary member would
    # render on its own.
    bundle = result.bundles[0]
    assert bundle.canonical_demand_id == "d.int"
    assert bundle.members == ("d.int", "d.sub1", "d.sub2")
    assert item(result, "d.sub2").projection_relation is ProjectionRelation.COVERED_BY_BUNDLE

    assert result.fairness_sentinels == ("d.sub1",), "exactly one oldest-ready sentinel"
    assert sum(1 for i in result.items if i.is_fairness_sentinel) == 1
    sentinel = item(result, "d.sub1")
    assert sentinel.is_fairness_sentinel is True
    assert sentinel.projection_relation is ProjectionRelation.ROOT_VISIBLE
    assert omission_for(result, "d.sub1") is None, "a visible sentinel keeps no receipt"

    # The rest of the backlog is still reported as exact deferred debt.
    assert omission_for(result, "d.sub2").relation is ProjectionRelation.COVERED_BY_BUNDLE
    assert omission_for(result, "d.sub2").covered_by == bundle.bundle_id
    assert result.coverage_summary["omitted_with_receipt"] == 1
    assert frontier_for(result, AuthorityRequirement.SOL).visible_demand_ids == (
        "d.int",
        "d.sub1",
    )


def test_b2_dominance_alone_never_empties_an_ordinary_partition():
    """The maximum of a dominance chain is always on the frontier.

    A receipt may only name a dominator that the reader can actually see, so
    dominance can hide the middle and the bottom of a chain but never its top.
    Proved on a hand-built chain and over every generated partition.
    """
    chain = compute_attention_frontier(
        [
            demand("d.chain.top", became_actionable_at="2026-09-01T00:00:00Z", **STRONG),
            demand("d.chain.mid", became_actionable_at="2026-09-02T00:00:00Z", **MIDDLE),
            demand("d.chain.low", became_actionable_at="2026-09-03T00:00:00Z", **WEAK),
        ],
        snapshot_identity=SNAP,
    )
    assert visible_ids(chain) == ("d.chain.top",)
    assert chain.fairness_sentinels == (), "no sentinel is owed while a root is visible"
    for did in ("d.chain.mid", "d.chain.low"):
        assert omission_for(chain, did).covered_by == "d.chain.top"

    checked = 0
    starved = []
    for result in list(corpus()) + [
        _starved_partition(
            ready={"d.sub1": "2026-09-02T00:00:00Z", "d.sub2": "2026-09-03T00:00:00Z"}
        )
    ]:
        ordinary: dict[str, list[FrontierItem]] = {}
        for entry in result.items:
            if entry.attention_class in (AttentionClass.FOCUS_NOW, AttentionClass.BATCH_NEXT):
                ordinary.setdefault(entry.authority_requirement.value, []).append(entry)
        for authority, members in ordinary.items():
            checked += 1
            if not any(
                m.projection_relation is ProjectionRelation.ROOT_VISIBLE for m in members
            ):
                starved.append((authority, [m.demand_id for m in members]))
    assert checked >= 10, f"only {checked} ordinary partitions checked"
    assert not starved, f"ordinary partitions with no visible root: {starved[:3]}"


def test_b3_sentinel_is_oldest_ready_with_deterministic_id_tiebreak():
    """The scarce fairness seat goes to the oldest ready demand; ties break by id."""
    tied = _starved_partition(
        ready={"d.sub1": "2026-09-02T00:00:00Z", "d.sub2": "2026-09-02T00:00:00Z"}
    )
    assert tied.fairness_sentinels == ("d.sub1",), "tie must break on demand_id"

    older_second = _starved_partition(
        ready={"d.sub1": "2026-09-05T00:00:00Z", "d.sub2": "2026-09-01T00:00:00Z"}
    )
    assert older_second.fairness_sentinels == ("d.sub2",), (
        "age must beat demand_id order — the id tiebreak is a tiebreak, not a rank"
    )

    # Oldest means the oldest *instant*, not the smallest string.  d.sub1's
    # +09:00 stamp is 2026-08-31T15:00Z, five hours older than d.sub2 — yet it
    # sorts LAST lexicographically.
    offset = _starved_partition(
        ready={
            "d.sub1": "2026-09-01T00:00:00+09:00",
            "d.sub2": "2026-08-31T20:00:00Z",
        }
    )
    assert "2026-08-31T20:00:00Z" < "2026-09-01T00:00:00+09:00", "fixture sanity"
    assert offset.fairness_sentinels == ("d.sub1",), (
        "fairness ordering compared timestamp strings instead of instants"
    )


def test_b4_absent_ready_age_yields_no_sentinel_but_reports_the_gap():
    """Unknown ready age is a coverage gap, never age zero (F0G §9).

    With no ready-age evidence the engine must refuse to invent an "oldest" —
    and must say so, in the per-item issues and in the coverage summary.
    """
    result = _starved_partition(ready={"d.sub1": None, "d.sub2": None})

    assert result.fairness_sentinels == (), "no ready-age evidence, so no sentinel"
    assert not any(i.is_fairness_sentinel for i in result.items)

    for did in ("d.sub1", "d.sub2"):
        assert Issue.READY_AGE_UNKNOWN in item(result, did).issues, did
        assert item(result, did).became_actionable_at is None
    assert result.coverage_summary["ready_age_unknown"] == 2

    # The partition really is starved — the gap is reported, not papered over.
    assert visible_ids(result) == ("d.int",)
    assert result.coverage_summary["omitted_with_receipt"] == 2
    debt = result.coverage_summary.get("fairness_debt_by_authority")
    if debt is not None:
        assert debt["SOL"]["deferred_ordinary"] == 2
        assert debt["SOL"]["ready_age_unknown"] == 2


@pytest.mark.parametrize(
    "freshness,conflict",
    [
        (Freshness.STALE, False),
        (Freshness.UNKNOWN, False),
        (Freshness.CURRENT, True),
    ],
)
def test_b5_unprovable_ready_age_is_counted_as_unknown(
    freshness: Freshness, conflict: bool
):
    """A ready age the source cannot prove is unknown everywhere, not just per item.

    The engine already refuses to seat a sentinel on an ungrounded timestamp and
    already flags the item with READY_AGE_UNKNOWN.  The coverage summary is the
    same claim aggregated, so it must agree with the items it summarises —
    otherwise the frontier reports a gap and simultaneously reports zero gaps,
    and "unknown is never zero/healthy/harmless" holds only at one of the two
    altitudes a reader might look at.
    """
    result = _starved_partition(
        ready={"d.sub1": "2026-09-02T00:00:00Z", "d.sub2": "2026-09-03T00:00:00Z"},
        ready_freshness=freshness,
        ready_conflict=conflict,
    )

    flagged = [i.demand_id for i in result.items if Issue.READY_AGE_UNKNOWN in i.issues]
    assert sorted(flagged) == ["d.sub1", "d.sub2"], (
        "an ungrounded ready age must be flagged on the item"
    )
    assert result.fairness_sentinels == (), (
        "an unprovable timestamp won the scarce fairness seat"
    )
    assert result.coverage_summary["ready_age_unknown"] == len(flagged), (
        "coverage_summary['ready_age_unknown'] counts only ABSENT ready-age facts "
        f"({result.coverage_summary['ready_age_unknown']}) while the items report "
        f"{len(flagged)} unknown ready ages — the summary contradicts its own items"
    )
    debt = result.coverage_summary.get("fairness_debt_by_authority")
    if debt is not None:
        assert debt["SOL"]["ready_age_unknown"] == len(flagged)


def test_b6_sentinel_never_suppresses_an_interrupt_or_upgrades_its_class():
    """Fairness is a visibility service, not a promotion (F0G §9)."""
    result = _starved_partition(
        ready={"d.sub1": "2026-09-02T00:00:00Z", "d.sub2": "2026-09-03T00:00:00Z"}
    )

    interrupt = item(result, "d.int")
    assert interrupt.attention_class is AttentionClass.INTERRUPT_NOW
    assert interrupt.projection_relation is ProjectionRelation.ROOT_VISIBLE
    assert interrupt.is_fairness_sentinel is False
    sol = frontier_for(result, AuthorityRequirement.SOL)
    assert sol.interrupt_member_count == 1
    assert sol.concurrent_demand is ConcurrentDemand.SINGLE
    assert "d.int" in sol.visible_demand_ids

    # The sentinel itself is unchanged against a control run in which it is an
    # ordinary visible root.
    control = compute_attention_frontier(
        [demand("d.sub1", became_actionable_at="2026-09-02T00:00:00Z", **WEAK)],
        snapshot_identity=SNAP,
    )
    control_item = item(control, "d.sub1")
    sentinel = item(result, "d.sub1")
    assert control_item.is_fairness_sentinel is False
    assert sentinel.attention_class is control_item.attention_class
    assert sentinel.pressure_reasons == control_item.pressure_reasons
    assert sentinel.authority_requirement is control_item.authority_requirement
    assert sentinel.serviceability is control_item.serviceability
    assert sentinel.attention_class is AttentionClass.FOCUS_NOW
    assert sentinel.attention_class is not AttentionClass.INTERRUPT_NOW


def test_b7_three_interrupts_do_not_erase_the_ordinary_fairness_debt():
    """Congestion is not an excuse to starve ordinary work."""
    result = _starved_partition(
        ready={"d.sub1": "2026-09-02T00:00:00Z", "d.sub2": "2026-09-03T00:00:00Z"},
        extra=[
            demand(
                f"d.int{n}",
                impact=ImpactState.ACTIVE_HARM,
                autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
                became_actionable_at=f"2026-09-0{n}T00:00:00Z",
            )
            for n in (2, 3)
        ],
    )

    sol = frontier_for(result, AuthorityRequirement.SOL)
    assert sol.interrupt_member_count == 3
    assert sol.interrupt_root_count == 3
    assert sol.concurrent_demand is ConcurrentDemand.MULTIPLE_INDEPENDENT
    for did in ("d.int", "d.int2", "d.int3"):
        assert item(result, did).projection_relation is ProjectionRelation.ROOT_VISIBLE

    assert result.fairness_sentinels == ("d.sub1",)
    assert item(result, "d.sub1").is_fairness_sentinel is True
    assert {o.demand_id for o in result.omissions} == {"d.sub2"}
    assert result.coverage_summary["omitted_with_receipt"] == 1


def test_b8_an_omitted_dominator_may_not_hide_its_subordinate():
    """A DOMINATED_BY receipt must name something the reader can actually see.

    Otherwise the compact view says "covered by X" where X is not on the
    frontier at all — an omission receipt that cannot be followed is not a
    receipt, and the subordinate is starved behind a ghost.
    """
    scenarios = list(corpus()) + [
        _starved_partition(
            ready={"d.sub1": "2026-09-02T00:00:00Z", "d.sub2": "2026-09-03T00:00:00Z"}
        ),
        compute_attention_frontier(
            [
                demand("d.chain.top", became_actionable_at="2026-09-01T00:00:00Z", **STRONG),
                demand("d.chain.mid", became_actionable_at="2026-09-02T00:00:00Z", **MIDDLE),
                demand("d.chain.low", became_actionable_at="2026-09-03T00:00:00Z", **WEAK),
            ],
            snapshot_identity=SNAP,
        ),
    ]
    checked = 0
    for result in scenarios:
        visible = set(visible_ids(result))
        for omission in result.omissions:
            if omission.relation is ProjectionRelation.DOMINATED_BY:
                checked += 1
                assert omission.covered_by in visible, (
                    f"{omission.demand_id} is hidden behind {omission.covered_by}, "
                    "which is itself omitted "
                    f"({item(result, omission.covered_by).projection_relation.value})"
                )
    assert checked >= 5, f"only {checked} dominance receipts checked"


# ===========================================================================
# C. CONCURRENT DEMAND
# ===========================================================================


def _interrupt_snapshot(count: int, **kwargs) -> FrontierResult:
    """``count`` independent SOL interrupts plus one ordinary BATCH_NEXT filler."""
    demands = [
        demand(
            "d.filler",
            autonomy=None,
            became_actionable_at="2026-09-01T00:00:00Z",
        )
    ]
    demands += [
        demand(
            f"d.i{n}",
            impact=ImpactState.ACTIVE_HARM,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            became_actionable_at=f"2026-09-{n + 1:02d}T00:00:00Z",
        )
        for n in range(count)
    ]
    return compute_attention_frontier(demands, snapshot_identity=SNAP, **kwargs)


@pytest.mark.parametrize(
    "count,concurrent,feasibility",
    [
        (0, ConcurrentDemand.NONE, ServiceFeasibility.NOT_APPLICABLE),
        (1, ConcurrentDemand.SINGLE, ServiceFeasibility.NOT_APPLICABLE),
        (2, ConcurrentDemand.MULTIPLE_INDEPENDENT, ServiceFeasibility.UNKNOWN),
        (5, ConcurrentDemand.MULTIPLE_INDEPENDENT, ServiceFeasibility.UNKNOWN),
    ],
)
def test_c1_independent_interrupt_roots_map_to_concurrent_demand(
    count: int, concurrent: ConcurrentDemand, feasibility: ServiceFeasibility
):
    """0/1/2/5 independent interrupt roots -> NONE/SINGLE/MULTIPLE_INDEPENDENT."""
    result = _interrupt_snapshot(count)
    sol = frontier_for(result, AuthorityRequirement.SOL)
    assert sol.interrupt_root_count == count
    assert sol.interrupt_member_count == count
    assert sol.concurrent_demand is concurrent
    assert sol.service_feasibility is feasibility
    if feasibility is ServiceFeasibility.NOT_APPLICABLE:
        assert sol.feasibility_receipts == ()
    else:
        assert len(sol.feasibility_receipts) == 1
        assert "unknown, not feasible" in sol.feasibility_receipts[0]
    # Every independent interrupt root stays visible — none is compacted away.
    for n in range(count):
        assert item(result, f"d.i{n}").projection_relation is ProjectionRelation.ROOT_VISIBLE


def test_c2_two_interrupts_on_one_exact_root_count_as_one_root():
    """Exact-root fan-in (F0G §7): shared root == one demand on attention."""
    root = fanin("JOB-ONE-ROOT")
    result = compute_attention_frontier(
        [
            demand(
                "d.i1",
                impact=ImpactState.ACTIVE_HARM,
                autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
                fanin_roots=(root,),
                became_actionable_at="2026-09-01T00:00:00Z",
            ),
            demand(
                "d.i2",
                impact=ImpactState.ACTIVE_HARM,
                autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
                fanin_roots=(root,),
                became_actionable_at="2026-09-02T00:00:00Z",
            ),
        ],
        snapshot_identity=SNAP,
    )
    sol = frontier_for(result, AuthorityRequirement.SOL)
    assert sol.interrupt_member_count == 2, "both interrupts are still counted"
    assert sol.interrupt_root_count == 1, "one exact root is one root"
    assert sol.concurrent_demand is ConcurrentDemand.SINGLE
    assert sol.service_feasibility is ServiceFeasibility.NOT_APPLICABLE
    assert len(result.bundles) == 1
    assert result.bundles[0].members == ("d.i1", "d.i2")

    # Contrast: the same two interrupts on distinct roots are two roots.
    split = compute_attention_frontier(
        [
            demand(
                "d.i1",
                impact=ImpactState.ACTIVE_HARM,
                autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
                fanin_roots=(fanin("JOB-ROOT-1"),),
                became_actionable_at="2026-09-01T00:00:00Z",
            ),
            demand(
                "d.i2",
                impact=ImpactState.ACTIVE_HARM,
                autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
                fanin_roots=(fanin("JOB-ROOT-2"),),
                became_actionable_at="2026-09-02T00:00:00Z",
            ),
        ],
        snapshot_identity=SNAP,
    )
    split_sol = frontier_for(split, AuthorityRequirement.SOL)
    assert split_sol.interrupt_root_count == 2
    assert split_sol.concurrent_demand is ConcurrentDemand.MULTIPLE_INDEPENDENT


def test_c3_proven_window_collision_carries_exactly_the_supplied_receipts():
    """A collision is claimed only on supplied proof, and only where proved."""
    proof = ("executive_os:window-proof-1", "capacity:window-proof-2")
    demands = [
        demand(
            f"d.{authority.value.lower()}{n}",
            authority=authority,
            impact=ImpactState.ACTIVE_HARM,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            became_actionable_at=f"2026-09-0{n + 1}T00:00:00Z",
        )
        for authority in (AuthorityRequirement.SOL, AuthorityRequirement.CHAIRMAN)
        for n in range(2)
    ]
    result = compute_attention_frontier(
        demands,
        snapshot_identity=SNAP,
        proven_window_collisions={AuthorityRequirement.SOL.value: proof},
    )

    sol = frontier_for(result, AuthorityRequirement.SOL)
    assert sol.concurrent_demand is ConcurrentDemand.PROVEN_WINDOW_COLLISION
    assert sol.service_feasibility is ServiceFeasibility.PROVEN_COLLISION
    assert sol.feasibility_receipts == proof, "receipts must be exactly the supplied refs"

    # The proof is authority-scoped; CHAIRMAN never inherits it.
    chairman = frontier_for(result, AuthorityRequirement.CHAIRMAN)
    assert chairman.concurrent_demand is ConcurrentDemand.MULTIPLE_INDEPENDENT
    assert chairman.service_feasibility is ServiceFeasibility.UNKNOWN
    assert chairman.feasibility_receipts != proof

    # A single root is never a collision even when proof is offered.
    single = compute_attention_frontier(
        [
            demand(
                "d.solo",
                impact=ImpactState.ACTIVE_HARM,
                autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
                became_actionable_at="2026-09-01T00:00:00Z",
            )
        ],
        snapshot_identity=SNAP,
        proven_window_collisions={AuthorityRequirement.SOL.value: proof},
    )
    assert frontier_for(single, AuthorityRequirement.SOL).concurrent_demand is (
        ConcurrentDemand.SINGLE
    )
    assert frontier_for(single, AuthorityRequirement.SOL).feasibility_receipts == ()


def test_c4_absent_collision_evidence_is_unknown_never_feasible():
    """No capacity evidence means UNKNOWN.  The vocabulary cannot even say FEASIBLE."""
    result = _interrupt_snapshot(3)
    sol = frontier_for(result, AuthorityRequirement.SOL)
    assert sol.service_feasibility is ServiceFeasibility.UNKNOWN
    assert sol.concurrent_demand is not ConcurrentDemand.PROVEN_WINDOW_COLLISION
    assert len(sol.feasibility_receipts) == 1
    assert "no source-backed executive service-capacity evidence" in sol.feasibility_receipts[0]
    assert "unknown, not feasible" in sol.feasibility_receipts[0]

    # Closed vocabulary: there is no way to assert feasibility at all.
    assert {member.name for member in ServiceFeasibility} == {
        "NOT_APPLICABLE",
        "UNKNOWN",
        "PROVEN_COLLISION",
    }

    # An empty proof mapping is simply no evidence.
    empty = _interrupt_snapshot(3, proven_window_collisions={})
    assert frontier_for(empty, AuthorityRequirement.SOL).service_feasibility is (
        ServiceFeasibility.UNKNOWN
    )


@pytest.mark.parametrize(
    "collisions",
    [
        {AuthorityRequirement.SOL.value: ()},
        {AuthorityRequirement.SOL.value: ("", "   ")},
        {"sol": ("executive_os:proof",)},
        {"CEO": ("executive_os:proof",)},
    ],
    ids=["no-refs", "blank-refs", "wrong-case-key", "unknown-authority-key"],
)
def test_c5_unusable_collision_evidence_is_refused_not_silently_dropped(collisions):
    """Empty or mis-keyed proof is refused loudly (F0G §10).

    Silently discarding it would turn a real proven collision into an
    ``UNKNOWN`` that reads like ordinary congestion, and an empty ref tuple is
    not proof of anything.
    """
    with pytest.raises(ValueError):
        _interrupt_snapshot(3, proven_window_collisions=collisions)


def test_c6_congestion_never_changes_authority_requirement():
    """Congestion is not authority (F0G §3.1): queue depth may not re-seat anyone."""
    watched = [
        demand(
            "d.watch.chair",
            authority=AuthorityRequirement.CHAIRMAN,
            window=WindowPressure.NEAR,
            became_actionable_at="2026-09-01T00:00:00Z",
        ),
        demand(
            "d.watch.sol",
            authority=AuthorityRequirement.SOL,
            window=WindowPressure.NEAR,
            became_actionable_at="2026-09-02T00:00:00Z",
        ),
        demand(
            "d.watch.worker",
            authority=AuthorityRequirement.COO_OR_WORKER,
            window=WindowPressure.NEAR,
            became_actionable_at="2026-09-03T00:00:00Z",
        ),
    ]

    baseline = None
    for count in (0, 1, 2, 5, 12):
        congestion = [
            demand(
                f"d.noise{n}",
                impact=ImpactState.ACTIVE_HARM,
                autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
                became_actionable_at=f"2026-08-{n + 1:02d}T00:00:00Z",
            )
            for n in range(count)
        ]
        result = compute_attention_frontier(
            watched + congestion, snapshot_identity=SNAP
        )
        observed = {
            entry.demand_id: (
                entry.authority_requirement,
                entry.authority_source,
                entry.attention_class,
                entry.serviceability,
            )
            for entry in result.items
            if entry.demand_id.startswith("d.watch.")
        }
        if baseline is None:
            baseline = observed
            assert observed["d.watch.chair"][0] is AuthorityRequirement.CHAIRMAN
            assert observed["d.watch.sol"][0] is AuthorityRequirement.SOL
            assert observed["d.watch.worker"][0] is AuthorityRequirement.COO_OR_WORKER
        assert observed == baseline, (
            f"{count} concurrent interrupts changed a watched demand's boundaries"
        )
        for n in range(count):
            assert item(result, f"d.noise{n}").authority_requirement is (
                AuthorityRequirement.SOL
            )


# ===========================================================================
# D. BUNDLE DETERMINISM
# ===========================================================================


def test_d1_bundle_id_is_stable_across_runs_member_order_and_processes():
    """bundle_id is a pure function of the exact root plus its member set."""
    first = bundle_probe()
    assert len(first["bundle_ids"]) == 1
    assert first == bundle_probe(), "bundle_id changed between runs in one process"

    root = fanin("JOB-PROBE")
    members = [
        demand("d.probe.a", fanin_roots=(root,), became_actionable_at="2026-09-01T00:00:00Z", **WEAK),
        demand("d.probe.b", fanin_roots=(root,), became_actionable_at="2026-09-02T00:00:00Z", **MIDDLE),
        demand("d.probe.c", fanin_roots=(root,), became_actionable_at="2026-09-03T00:00:00Z", **STRONG),
    ]
    rng = random.Random(7)
    for _ in range(8):
        shuffled = list(members)
        rng.shuffle(shuffled)
        result = compute_attention_frontier(shuffled, snapshot_identity=SNAP)
        assert [b.bundle_id for b in result.bundles] == first["bundle_ids"], (
            "member input order changed the bundle_id"
        )
        assert serialise(result) == first["serialised"]

    # Cross-process, with a different hash seed: no dict/set iteration order and
    # no per-process salt may leak into the identity.
    env = {**os.environ, "PYTHONHASHSEED": "12345", "PYTHONPATH": str(REPO_ROOT)}
    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_SCRIPT, str(TEST_FILE)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, f"probe subprocess failed:\n{proc.stderr}"
    payload = json.loads(proc.stdout.rsplit("@@", 1)[-1])
    assert payload["bundle_ids"] == first["bundle_ids"], "bundle_id is process-dependent"
    assert payload["canonical"] == first["canonical"]
    assert payload["serialised"] == first["serialised"], "frontier is process-dependent"


def test_d2_bundle_id_changes_when_the_member_set_changes():
    """Adding, removing or re-rooting a member must mint a new identity."""
    root = fanin("JOB-SET")
    base_members = {
        "d.set.a": WEAK,
        "d.set.b": MIDDLE,
        "d.set.c": STRONG,
    }

    def build(members: Mapping[str, dict], root_ref: str = "JOB-SET") -> str:
        node = fanin(root_ref)
        result = compute_attention_frontier(
            [
                demand(
                    did,
                    fanin_roots=(node,),
                    became_actionable_at="2026-09-01T00:00:00Z",
                    **vector,
                )
                for did, vector in members.items()
            ],
            snapshot_identity=SNAP,
        )
        assert len(result.bundles) == 1
        return result.bundles[0].bundle_id

    three = build(base_members)
    two = build({k: v for k, v in base_members.items() if k != "d.set.c"})
    four = build({**base_members, "d.set.d": WEAK})
    renamed_member = build(
        {"d.set.a": WEAK, "d.set.b": MIDDLE, "d.set.zzz": STRONG}
    )
    other_root = build(base_members, root_ref="JOB-OTHER")

    assert len({three, two, four, renamed_member, other_root}) == 5, (
        "distinct member sets / roots collided onto one bundle_id: "
        f"{[three, two, four, renamed_member, other_root]}"
    )
    assert build(base_members) == three, "rebuilding the same set changed the id"
    assert all(bid.startswith("bundle-") for bid in (three, two, four, other_root))
    assert root.key == "BLOCKER_ROOT:JOB-SET"


def test_d3_an_interrupt_member_is_the_canonical_visible_face():
    """Exact-root compaction may never hide an emergency (F0G §3.2, §7)."""
    root = fanin("JOB-FACE")
    result = compute_attention_frontier(
        [
            # d.a sorts first, so members[0] would be the default canonical.
            demand("d.a", fanin_roots=(root,), became_actionable_at="2026-09-01T00:00:00Z", **WEAK),
            demand("d.b", fanin_roots=(root,), became_actionable_at="2026-09-02T00:00:00Z", **WEAK),
            demand(
                "d.z",
                impact=ImpactState.ACTIVE_HARM,
                autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
                fanin_roots=(root,),
                became_actionable_at="2026-09-03T00:00:00Z",
            ),
            # Keeps the ordinary partition from starving, so the fairness
            # sentinel does not confound the bundle projection under test.
            demand(
                "d.free",
                became_actionable_at="2026-09-04T00:00:00Z",
                window=WindowPressure.NEAR,
                autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
                burn=BurnState.ACTIVE,
                unblocks=("JOB-A", "JOB-B", "JOB-C"),
            ),
        ],
        snapshot_identity=SNAP,
    )

    assert len(result.bundles) == 1
    bundle = result.bundles[0]
    assert bundle.members == ("d.a", "d.b", "d.z")
    assert bundle.canonical_demand_id == "d.z", "the interrupt owns the bundle face"
    assert bundle.canonical_demand_id != bundle.members[0]
    assert bundle.interrupt_member_count == 1
    assert bundle.canonical_root_ref == "BLOCKER_ROOT:JOB-FACE"

    assert item(result, "d.z").projection_relation is ProjectionRelation.ROOT_VISIBLE
    assert item(result, "d.z").attention_class is AttentionClass.INTERRUPT_NOW
    assert result.fairness_sentinels == ()
    for did in ("d.a", "d.b"):
        assert item(result, did).projection_relation is ProjectionRelation.COVERED_BY_BUNDLE
        assert item(result, did).bundle_id == bundle.bundle_id
        assert omission_for(result, did).covered_by == bundle.bundle_id
    assert frontier_for(result, AuthorityRequirement.SOL).interrupt_member_count == 1


def test_d4_member_boundaries_keep_each_members_own_serviceability():
    """Compaction is a view, not a merge: per-member boundaries survive (F0G §7)."""
    root = fanin("JOB-BOUNDARY")
    result = compute_attention_frontier(
        [
            demand(
                "d.m1blocked",
                blockers=(blocker(ServiceabilityReason.EXTERNAL_BLOCKER),),
                action_target=ActionTarget(state=TargetState.NOT_APPLICABLE),
                fanin_roots=(root,),
                became_actionable_at="2026-09-01T00:00:00Z",
                **WEAK,
            ),
            demand(
                "d.m2ready",
                action_target=ActionTarget(
                    state=TargetState.RESOLVED, target_ref="runtime_binding:rb-1"
                ),
                fanin_roots=(root,),
                became_actionable_at="2026-09-02T00:00:00Z",
                **WEAK,
            ),
            demand(
                "d.m3unknown",
                fanin_roots=(root,),
                became_actionable_at="2026-09-03T00:00:00Z",
                **WEAK,
            ),
        ],
        snapshot_identity=SNAP,
    )

    assert len(result.bundles) == 1
    bundle = result.bundles[0]
    assert bundle.members == ("d.m1blocked", "d.m2ready", "d.m3unknown")
    assert bundle.member_boundaries == (
        ("d.m1blocked", "SOL", "BLOCKED"),
        ("d.m2ready", "SOL", "READY"),
        ("d.m3unknown", "SOL", "UNKNOWN"),
    )

    # Every boundary matches that member's own item — nothing inherits the
    # canonical member's serviceability, and compaction never implies the
    # members are jointly actionable.
    for did, authority, serviceability in bundle.member_boundaries:
        entry = item(result, did)
        assert entry.authority_requirement.value == authority
        assert entry.serviceability.value == serviceability
        assert entry.bundle_id == bundle.bundle_id
    assert len({s for _, _, s in bundle.member_boundaries}) == 3
    assert item(result, "d.m1blocked").actor_can_act is False
    assert item(result, "d.m2ready").actor_can_act is True
    assert item(result, "d.m2ready").exact_action_target == "runtime_binding:rb-1"
    assert item(result, "d.m3unknown").actor_can_act is None
    assert Issue.TARGET_EVIDENCE_UNAVAILABLE in item(result, "d.m3unknown").issues


def test_d5_an_exact_root_never_bundles_across_authorities():
    """Shared cause is context; context grouping never grants shared permission.

    A Chairman demand and two Sol demands on the SAME exact canonical root must
    not be folded behind one face — otherwise the Chairman item would render
    nowhere in its own authority partition.
    """
    root = fanin("JOB-BOUNDARY")
    common = dict(
        fanin_roots=(root,),
        action_target=ActionTarget(state=TargetState.NOT_APPLICABLE),
        **WEAK,
    )
    result = compute_attention_frontier(
        [
            demand(
                "d.chair",
                authority=AuthorityRequirement.CHAIRMAN,
                became_actionable_at="2026-09-01T00:00:00Z",
                **common,
            ),
            demand("d.sol1", became_actionable_at="2026-09-02T00:00:00Z", **common),
            demand("d.sol2", became_actionable_at="2026-09-03T00:00:00Z", **common),
        ],
        snapshot_identity=SNAP,
    )

    assert len(result.bundles) == 1, "only the same-authority members may fan in"
    bundle = result.bundles[0]
    assert bundle.members == ("d.sol1", "d.sol2")
    assert {a for _, a, _ in bundle.member_boundaries} == {"SOL"}

    chair = item(result, "d.chair")
    assert chair.bundle_id is None, "a Chairman demand was folded into a Sol bundle"
    assert chair.projection_relation is ProjectionRelation.ROOT_VISIBLE
    assert chair.authority_requirement is AuthorityRequirement.CHAIRMAN
    assert frontier_for(result, AuthorityRequirement.CHAIRMAN).visible_demand_ids == (
        "d.chair",
    )
    assert omission_for(result, "d.chair") is None
