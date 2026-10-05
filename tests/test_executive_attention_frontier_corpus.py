"""S0 deterministic adversarial corpus for the Executive Attention Frontier.

Controlling contract: ``research/MASTERMIND_EXECUTIVE_ATTENTION_ECONOMICS_F0G_
CONSOLIDATED_V1_CONTRACT_2026-08-30.md`` §15 ("S0 — deterministic adversarial
corpus").  Engine under test: ``control_plane.executive_attention_frontier``.

Every test here is hostile: it tries to make the engine break one of the hard
zero-violation laws (§11) rather than to demonstrate that it works.  Nothing in
this file is random, clock-dependent or I/O dependent — the single shuffle uses
a fixed seed.

Law tags used in assertion messages map to F0G sections.
"""

from __future__ import annotations

import dataclasses
import random

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
    PressureReason,
    ProjectionRelation,
    RESULT_SCHEMA,
    Reversibility,
    ServiceFeasibility,
    Serviceability,
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

# --------------------------------------------------------------------------
# Module-level builders
# --------------------------------------------------------------------------

OBSERVED = "2026-09-20T09:00:00Z"
LATER = "2026-09-20T23:59:59Z"
SNAPSHOT = "eaf-s0-corpus"

_OMIT = object()

#: Most demands here want executive *cognition*, not a runtime action target.
#: Saying so explicitly is the engine's contract: an undeclared target is
#: unknown evidence, and unknown may never score better than a declared
#: "no target is needed" (F0G §11).
NO_TARGET_NEEDED = ActionTarget(state=TargetState.NOT_APPLICABLE)


def src(
    ref: str,
    *,
    owner: SourceOwner = SourceOwner.AGENT_OS,
    observed_at: str | None = OBSERVED,
    freshness: Freshness = Freshness.CURRENT,
) -> SourceRef:
    """An exact source reference.  Freshness is the *owner's* verdict (§5.8)."""
    return SourceRef(owner=owner, ref=ref, observed_at=observed_at, freshness=freshness)


def _f(value: object, source: SourceRef, conflict: bool = False) -> Fact | None:
    if value is _OMIT:
        return None
    return Fact(value=value, source=source, conflict=conflict)


def demand(
    demand_id: str,
    *,
    title: str | None = None,
    authority: object = AuthorityRequirement.SOL,
    authority_source: SourceRef | None = None,
    authority_conflict: bool = False,
    window: object = WindowPressure.OPEN,
    window_source: SourceRef | None = None,
    window_conflict: bool = False,
    impact: object = ImpactState.NO_ACTIVE_HARM,
    autonomy: object = AutonomousProgress.PARTIAL_SAFE_PROGRESS,
    burn: object = BurnState.NONE,
    unblocks: object = (),
    reversibility: object = _OMIT,
    blast: object = _OMIT,
    wait: object = _OMIT,
    wait_conflict: bool = False,
    ready_at: object = _OMIT,
    cost: object = _OMIT,
    effect: object = _OMIT,
    capacity: object = _OMIT,
    target: object = NO_TARGET_NEEDED,
    target_conflict: bool = False,
    terminal: object = _OMIT,
    blockers: tuple = (),
    roots: tuple = (),
    responsibility_ref: str | None = None,
    context_key: str | None = None,
    display_context: str | None = None,
    admitted_via: AdmissionSource = AdmissionSource.EXECUTIVE_INBOX_OBLIGATION,
    observed_at: str = OBSERVED,
    owner: SourceOwner = SourceOwner.AGENT_OS,
) -> AttentionDemand:
    """Build one admitted demand.

    The five load-bearing comparison dimensions (window/impact/autonomy/
    unblock/burn) default to *grounded* values so that a test that does not
    care about them still yields comparable demands; pass ``_OMIT`` to make a
    dimension genuinely unknown.
    """
    base = src(f"src:{demand_id}", owner=owner, observed_at=observed_at)
    return AttentionDemand(
        demand_id=demand_id,
        admitted_via=admitted_via,
        admission_source=base,
        title=title or f"demand {demand_id}",
        responsibility_ref=responsibility_ref,
        authority=_f(authority, authority_source or base, authority_conflict),
        decision_window=_f(window, window_source or base, window_conflict),
        actual_impact=_f(impact, base),
        blast_radius=_f(blast, base),
        reversibility=_f(reversibility, base),
        unblocks=_f(unblocks, base),
        resource_burn=_f(burn, base),
        autonomous_progress=_f(autonomy, base),
        wait=_f(wait, base, wait_conflict),
        became_actionable_at=_f(ready_at, base),
        cost_of_delay=_f(cost, base),
        effect_state=_f(effect, base),
        capacity_state=_f(capacity, base),
        action_target=_f(target, base, target_conflict),
        terminal=_f(terminal, base),
        blockers=tuple(Blocker(reason=r, source=base, detail=d) for r, d in blockers),
        fanin_roots=tuple(FaninRoot(kind=k, ref=r, source=base) for k, r in roots),
        context_key=context_key,
        display_context=display_context,
    )


def item_of(result: FrontierResult, demand_id: str) -> FrontierItem:
    for item in result.items:
        if item.demand_id == demand_id:
            return item
    raise AssertionError(f"{demand_id} missing from the frontier result")


def frontier_of(result: FrontierResult, authority: AuthorityRequirement):
    for frontier in result.authority_frontiers:
        if frontier.authority_requirement is authority:
            return frontier
    return None


def relation(result: FrontierResult, demand_id: str) -> ProjectionRelation:
    return item_of(result, demand_id).projection_relation


def comparison(result: FrontierResult, left: str, right: str) -> Comparison | None:
    for a, b, rel in result.comparisons:
        if (a, b) == (left, right):
            return rel
        if (a, b) == (right, left):
            return rel
    return None


def receipt_of(result: FrontierResult, demand_id: str):
    matches = [o for o in result.omissions if o.demand_id == demand_id]
    assert len(matches) <= 1, f"{demand_id} has {len(matches)} omission receipts"
    return matches[0] if matches else None


def decision_fingerprint(result: FrontierResult) -> tuple:
    """Everything the frontier decides, excluding raw source observation time."""
    return (
        result.schema,
        result.snapshot_identity,
        tuple(
            (
                i.demand_id,
                i.authority_requirement,
                i.attention_class,
                i.pressure_reasons,
                i.serviceability,
                i.serviceability_reasons,
                i.exact_action_target,
                i.actor_can_act,
                tuple(sorted(i.factor_vector.items(), key=lambda kv: kv[0])),
                i.became_actionable_at,
                i.downstream_unblocks,
                i.active_resource_burn,
                i.bundle_id,
                i.projection_relation,
                i.explanation_reasons,
                i.issues,
                i.is_fairness_sentinel,
            )
            for i in result.items
        ),
        result.fairness_sentinels,
        tuple((o.demand_id, o.relation, o.covered_by, o.reason) for o in result.omissions),
        result.comparisons,
        tuple(
            (
                f.authority_requirement,
                f.interrupt_root_count,
                f.interrupt_member_count,
                f.concurrent_demand,
                f.service_feasibility,
                f.feasibility_receipts,
                f.visible_demand_ids,
            )
            for f in result.authority_frontiers
        ),
        tuple((b.bundle_id, b.canonical_root_ref, b.canonical_demand_id, b.members,
               b.interrupt_member_count, b.member_boundaries) for b in result.bundles),
        tuple(sorted(result.coverage_summary.items(), key=lambda kv: kv[0])),
        tuple(sorted(result.source_freshness_summary.items(), key=lambda kv: kv[0])),
    )


# --------------------------------------------------------------------------
# The shared 10-demand mixed corpus (tests 8, 16, 17)
# --------------------------------------------------------------------------


def mixed_corpus(*, refreshed: frozenset[str] = frozenset()) -> list[AttentionDemand]:
    """Ten demands covering interrupts, bundles, dominance, fairness, unknowns.

    ``refreshed`` re-observes the named demands at a *later* observation time
    with byte-identical values — the timestamp refresh attack of §5.9/§11.
    """

    def at(demand_id: str) -> str:
        return LATER if demand_id in refreshed else OBSERVED

    return [
        # Chairman emergency — its own authority partition.
        demand(
            "d01-chair-emergency",
            authority=AuthorityRequirement.CHAIRMAN,
            window=WindowPressure.NEAR,
            impact=ImpactState.ACTIVE_HARM,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            unblocks=("DEC-CHAIR-1",),
            burn=BurnState.NONE,
            ready_at="2026-02-01T00:00:00Z",
            observed_at=at("d01-chair-emergency"),
        ),
        # Sol symptom-storm face (interrupt) + one batchable sibling on the
        # same exact blocker root.
        demand(
            "d02-sol-storm-face",
            window=WindowPressure.EXPIRED,
            impact=ImpactState.ACTIVE_HARM,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            unblocks=("WS-A", "WS-B", "WS-C", "WS-D"),
            burn=BurnState.ACTIVE,
            roots=((FaninKind.BLOCKER_ROOT, "BLK-77"),),
            ready_at="2026-03-01T00:00:00Z",
            observed_at=at("d02-sol-storm-face"),
        ),
        demand(
            "d03-sol-storm-batch",
            autonomy=_OMIT,
            roots=((FaninKind.BLOCKER_ROOT, "BLK-77"),),
            ready_at="2024-05-05T00:00:00Z",
            observed_at=at("d03-sol-storm-batch"),
        ),
        # A second independent Sol interrupt root.
        demand(
            "d04-sol-window-edge",
            window=WindowPressure.BEFORE_NEXT_FOCUS_BOUNDARY,
            autonomy=AutonomousProgress.FULL_SAFE_PROGRESS,
            ready_at="2026-01-09T00:00:00Z",
            observed_at=at("d04-sol-window-edge"),
        ),
        # Sol FOCUS_NOW pair where one strictly dominates the other.
        demand(
            "d05-sol-unblock-edge",
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            unblocks=("WS-E", "WS-F", "WS-G"),
            ready_at="2026-01-10T00:00:00Z",
            observed_at=at("d05-sol-unblock-edge"),
        ),
        demand(
            "d06-sol-weak-focus",
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            unblocks=("WS-E",),
            ready_at="2026-01-11T00:00:00Z",
            observed_at=at("d06-sol-weak-focus"),
        ),
        # COO partition: one interrupt root swallowing both ordinary members,
        # forcing the anti-starvation sentinel.
        demand(
            "d07-coo-interrupt",
            authority=AuthorityRequirement.COO_OR_WORKER,
            window=WindowPressure.EXPIRED,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            roots=((FaninKind.DEPENDENCY_ROOT, "DEP-9"),),
            ready_at="2026-04-04T00:00:00Z",
            observed_at=at("d07-coo-interrupt"),
        ),
        demand(
            "d08-coo-old-batch",
            authority=AuthorityRequirement.COO_OR_WORKER,
            autonomy=_OMIT,
            roots=((FaninKind.DEPENDENCY_ROOT, "DEP-9"),),
            ready_at="2023-11-11T00:00:00Z",
            observed_at=at("d08-coo-old-batch"),
        ),
        demand(
            "d09-coo-new-batch",
            authority=AuthorityRequirement.COO_OR_WORKER,
            autonomy=_OMIT,
            roots=((FaninKind.DEPENDENCY_ROOT, "DEP-9"),),
            ready_at="2026-07-07T00:00:00Z",
            observed_at=at("d09-coo-new-batch"),
        ),
        # Conflicted authority — must land in the UNKNOWN partition.
        demand(
            "d10-conflicted-authority",
            authority=AuthorityRequirement.CHAIRMAN,
            authority_conflict=True,
            autonomy=_OMIT,
            ready_at=_OMIT,
            observed_at=at("d10-conflicted-authority"),
        ),
    ]


MIXED_COLLISIONS = {"SOL": ("capacity:exec-service-window-1", "wake:window-proof-2")}


# ==========================================================================
# 1. Chairman-only emergency vs a more urgent Sol item
# ==========================================================================


def test_01_chairman_emergency_is_not_demoted_by_a_more_urgent_sol_item() -> None:
    """§3.1/§13: authority is resolved before ordering and a stronger Sol
    pressure vector may never demote, absorb or out-rank a Chairman item.
    """
    chairman = demand(
        "d-chairman-only-emergency",
        title="ratify the irreversible capital-allocation change",
        authority=AuthorityRequirement.CHAIRMAN,
        window=WindowPressure.NEAR,
        impact=ImpactState.NO_ACTIVE_HARM,
        reversibility=Reversibility.IRREVERSIBLE,
        autonomy=AutonomousProgress.FULL_SAFE_PROGRESS,
        unblocks=(),
        burn=BurnState.NONE,
        ready_at="2026-09-01T00:00:00Z",
    )
    # Strictly stronger on every single load-bearing dimension.
    sol = demand(
        "d-sol-more-urgent-everything",
        title="URGENT CRITICAL production incident blocking the whole company",
        authority=AuthorityRequirement.SOL,
        window=WindowPressure.EXPIRED,
        impact=ImpactState.ACTIVE_HARM,
        autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
        unblocks=tuple(f"WS-{n}" for n in range(12)),
        burn=BurnState.ACTIVE,
        ready_at="2026-09-19T00:00:00Z",
    )
    result = compute_attention_frontier([chairman, sol], snapshot_identity=SNAPSHOT)

    chair_item = item_of(result, "d-chairman-only-emergency")
    sol_item = item_of(result, "d-sol-more-urgent-everything")

    assert chair_item.authority_requirement is AuthorityRequirement.CHAIRMAN
    assert sol_item.authority_requirement is AuthorityRequirement.SOL
    assert chair_item.attention_class is AttentionClass.INTERRUPT_NOW
    assert PressureReason.IMMINENT_IRREVERSIBLE_LOSS in chair_item.pressure_reasons

    # Not demoted, not absorbed, not omitted.
    assert chair_item.projection_relation is ProjectionRelation.ROOT_VISIBLE
    assert chair_item.bundle_id is None
    assert receipt_of(result, "d-chairman-only-emergency") is None
    assert sol_item.projection_relation is ProjectionRelation.ROOT_VISIBLE

    # Cross-authority comparison may not even be attempted (§8 compares only
    # "within the same authority and actionable pressure class").
    assert comparison(
        result, "d-chairman-only-emergency", "d-sol-more-urgent-everything"
    ) is None

    chair_frontier = frontier_of(result, AuthorityRequirement.CHAIRMAN)
    assert chair_frontier is not None
    assert chair_frontier.interrupt_root_count == 1
    assert chair_frontier.visible_demand_ids == ("d-chairman-only-emergency",)
    assert chair_frontier.concurrent_demand is ConcurrentDemand.SINGLE


# ==========================================================================
# 2. Exact-root symptom storm vs merely similar titles
# ==========================================================================


def test_02a_exact_blocker_root_symptom_storm_bundles_under_one_root() -> None:
    """§7: an exact canonical blocker root is a lawful fan-in relation, the
    bundle id is derived from root + ordered members, and the visible face of a
    bundle containing an interrupt is that interrupt.
    """
    root = (FaninKind.BLOCKER_ROOT, "BLK-ROOT-77")
    storm = [
        demand(
            "d-storm-0-interrupt",
            window=WindowPressure.EXPIRED,
            impact=ImpactState.ACTIVE_HARM,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            roots=(root,),
            ready_at=_OMIT,
        )
    ] + [
        demand(
            f"d-storm-{n}-symptom",
            autonomy=_OMIT,
            target=(
                ActionTarget(state=TargetState.UNAVAILABLE) if n == 4 else NO_TARGET_NEEDED
            ),
            roots=(root,),
            ready_at=_OMIT,
        )
        for n in range(1, 6)
    ]
    # Same exact root, different authority: context, never shared permission.
    other_authority = demand(
        "d-storm-9-other-authority",
        authority=AuthorityRequirement.COO_OR_WORKER,
        autonomy=_OMIT,
        roots=(root,),
        ready_at=_OMIT,
    )
    result = compute_attention_frontier(storm + [other_authority], snapshot_identity=SNAPSHOT)

    sol_ids = tuple(sorted(d.demand_id for d in storm))
    bundle = next(b for b in result.bundles if "d-storm-0-interrupt" in b.members)
    assert bundle.canonical_root_ref == "BLOCKER_ROOT:BLK-ROOT-77"
    assert bundle.members == sol_ids
    assert len(bundle.members) == 6
    assert bundle.interrupt_member_count == 1
    # The emergency is the face of its own bundle — compaction never hides it.
    assert bundle.canonical_demand_id == "d-storm-0-interrupt"
    assert relation(result, "d-storm-0-interrupt") is ProjectionRelation.ROOT_VISIBLE

    covered = [d.demand_id for d in storm if d.demand_id != "d-storm-0-interrupt"]
    for did in covered:
        assert relation(result, did) is ProjectionRelation.COVERED_BY_BUNDLE
        receipt = receipt_of(result, did)
        assert receipt is not None
        assert receipt.relation is ProjectionRelation.COVERED_BY_BUNDLE
        assert receipt.covered_by == bundle.bundle_id
        assert "BLOCKER_ROOT:BLK-ROOT-77" in receipt.reason
        assert item_of(result, did).bundle_id == bundle.bundle_id

    # §7: grouping preserves per-member serviceability boundaries and never
    # grants shared permission — a blocked member stays blocked inside the card.
    boundaries = dict(
        (member, (authority, service)) for member, authority, service in bundle.member_boundaries
    )
    assert boundaries["d-storm-4-symptom"] == ("SOL", "BLOCKED")
    assert boundaries["d-storm-0-interrupt"] == ("SOL", "READY")
    assert item_of(result, "d-storm-4-symptom").actor_can_act is False

    # §7/§13: a demand of another authority is never represented by a face that
    # does not share its authority.
    for item in result.items:
        if item.projection_relation is not ProjectionRelation.COVERED_BY_BUNDLE:
            continue
        face = next(b for b in result.bundles if b.bundle_id == item.bundle_id)
        assert item_of(result, face.canonical_demand_id).authority_requirement is (
            item.authority_requirement
        )
    assert relation(result, "d-storm-9-other-authority") is ProjectionRelation.ROOT_VISIBLE

    # Deterministic bundle identity: no mutable ledger.
    again = compute_attention_frontier(
        list(reversed(storm + [other_authority])), snapshot_identity=SNAPSHOT
    )
    assert next(
        b for b in again.bundles if "d-storm-0-interrupt" in b.members
    ).bundle_id == bundle.bundle_id
    assert result.fairness_sentinels == ()


def test_02b_near_identical_titles_without_a_shared_exact_root_never_bundle() -> None:
    """§7/§11: semantic similarity may not suppress, and free text ("urgent",
    "critical", "CEO") has zero admission/ordering power.
    """
    titles = [
        "URGENT: CEO must decide the CI gate fix for the frontier rollout",
        "URGENT: CEO must decide the CI gate fix for the frontier rollout!",
        "Urgent - CEO must decide the CI gate fix for the frontier rollout",
        "CRITICAL: CEO must decide the CI gate fix for the frontier rollout",
        "urgent: ceo must decide the ci gate fix for the frontier rollout",
    ]
    twins = [
        demand(
            f"d-twin-{n}",
            title=title,
            autonomy=_OMIT,
            # §4 canary: a user-facing blast radius is neither executive
            # authority nor proof of current harm.
            blast=BlastRadius.USER_FACING,
            # Distinct exact refs: same *kind*, different canonical identity.
            roots=((FaninKind.DECISION_REF, f"DEC-TWIN-{n}"),),
            display_context="same program, same words, different exact roots",
            context_key="ctx-frontier-rollout",
            ready_at=f"2026-0{n + 1}-01T00:00:00Z",
        )
        for n, title in enumerate(titles)
    ]
    result = compute_attention_frontier(twins, snapshot_identity=SNAPSHOT)

    assert result.bundles == ()
    assert result.omissions == ()
    for n in range(5):
        item = item_of(result, f"d-twin-{n}")
        assert item.bundle_id is None
        assert item.projection_relation is ProjectionRelation.ROOT_VISIBLE
        # Free text never lifts the pressure class.
        assert item.attention_class is AttentionClass.BATCH_NEXT
        assert item.pressure_reasons == (PressureReason.NO_GROUNDED_PRESSURE,)
        assert item.authority_requirement is AuthorityRequirement.SOL
        # §5.2: blast radius is carried as evidence and never read as harm.
        assert item.factor_vector["blast_radius"] == "USER_FACING"
        assert item.factor_vector["actual_impact"] == "NO_ACTIVE_HARM"
        assert PressureReason.ACTIVE_HARM not in item.pressure_reasons


# ==========================================================================
# 3. Stale / conflicted / absent authority
# ==========================================================================


def test_03a_conflicted_authority_resolves_unknown_and_blocks_service() -> None:
    """§3.1.4: unknown/conflicted authority never defaults upward; §6.1: a
    conflicted authority source blocks the action path.
    """
    conflicted_high = demand(
        "d-auth-conflicted-chairman",
        authority=AuthorityRequirement.CHAIRMAN,
        authority_conflict=True,
        impact=ImpactState.ACTIVE_HARM,
    )
    conflicted_low = demand(
        "d-auth-conflicted-worker",
        authority=AuthorityRequirement.COO_OR_WORKER,
        authority_conflict=True,
    )
    result = compute_attention_frontier(
        [conflicted_high, conflicted_low], snapshot_identity=SNAPSHOT
    )

    for did in ("d-auth-conflicted-chairman", "d-auth-conflicted-worker"):
        item = item_of(result, did)
        assert item.authority_requirement is AuthorityRequirement.UNKNOWN
        assert Issue.AUTHORITY_CONFLICTED in item.issues
        assert item.serviceability is Serviceability.BLOCKED
        assert ServiceabilityReason.AUTHORITY_SOURCE_CONFLICT in item.serviceability_reasons
        assert item.actor_can_act is False
        # The conflicted source is still disclosed, never dropped.
        assert item.authority_source is not None

    # Pressure survives the conflict; it is simply not actionable.
    assert item_of(
        result, "d-auth-conflicted-chairman"
    ).attention_class is AttentionClass.INTERRUPT_NOW

    assert frontier_of(result, AuthorityRequirement.CHAIRMAN) is None
    assert frontier_of(result, AuthorityRequirement.UNKNOWN) is not None
    assert result.coverage_summary["authority_unknown"] == 2
    # A conflicted demand is invalid for comparison, never silently ordered.
    assert comparison(
        result, "d-auth-conflicted-chairman", "d-auth-conflicted-worker"
    ) in (None, Comparison.INVALID_FOR_COMPARISON)


def test_03b_absent_authority_resolves_unknown_and_never_defaults_upward() -> None:
    """§3.1.4 + §11: missing authority evidence is UNKNOWN, not CHAIRMAN, not
    SOL and not "harmless"."""
    result = compute_attention_frontier(
        [demand("d-auth-absent", authority=_OMIT, impact=ImpactState.ACTIVE_HARM)],
        snapshot_identity=SNAPSHOT,
    )
    item = item_of(result, "d-auth-absent")
    assert item.authority_requirement is AuthorityRequirement.UNKNOWN
    assert item.authority_source is None
    assert Issue.AUTHORITY_UNKNOWN in item.issues
    assert item.serviceability is Serviceability.UNKNOWN
    assert ServiceabilityReason.UNKNOWN_LOAD_BEARING_SOURCE in item.serviceability_reasons
    assert item.actor_can_act is None  # never coerced to a boolean
    assert item.attention_class is AttentionClass.INTERRUPT_NOW


def test_03c_stale_authority_source_resolves_unknown_not_the_stale_claim() -> None:
    """§5.8 + §11: freshness is load-bearing and unknown is never healthy.

    A stale authority source cannot ground an authority-grade claim — the
    engine's own ``Fact.grounded`` defines that standard as
    ``not conflict and freshness is CURRENT`` — so a stale CHAIRMAN claim must
    resolve UNKNOWN and must not report a usable action path.
    """
    stale = demand(
        "d-auth-stale-chairman",
        authority=AuthorityRequirement.CHAIRMAN,
        authority_source=src(
            "agentos:decision-gate-authority",
            observed_at="2026-07-01T00:00:00Z",
            freshness=Freshness.STALE,
        ),
    )
    result = compute_attention_frontier([stale], snapshot_identity=SNAPSHOT)
    item = item_of(result, "d-auth-stale-chairman")

    assert Issue.AUTHORITY_UNKNOWN in item.issues
    assert item.authority_requirement is AuthorityRequirement.UNKNOWN, (
        "a stale source may not ground the authority class it claims"
    )
    assert frontier_of(result, AuthorityRequirement.CHAIRMAN) is None, (
        "a stale claim must not populate the canonical Chairman partition (§13)"
    )
    assert item.serviceability is not Serviceability.READY, (
        "false confidence on stale truth (§15 interrupt-safety metric family)"
    )
    assert item.actor_can_act is not True
    assert ServiceabilityReason.UNKNOWN_LOAD_BEARING_SOURCE in item.serviceability_reasons
    assert result.coverage_summary["authority_unknown"] == 1


def test_03d_unknown_freshness_authority_source_resolves_unknown() -> None:
    """§11: "Unknown is not zero, healthy, unlimited or harmless." An authority
    source whose own owner reports UNKNOWN freshness may not ground SOL.
    """
    unknown_fresh = demand(
        "d-auth-unknown-freshness",
        authority=AuthorityRequirement.SOL,
        authority_source=src(
            "wake:authority-hint",
            owner=SourceOwner.WAKE,
            observed_at=None,
            freshness=Freshness.UNKNOWN,
        ),
    )
    result = compute_attention_frontier([unknown_fresh], snapshot_identity=SNAPSHOT)
    item = item_of(result, "d-auth-unknown-freshness")

    assert Issue.AUTHORITY_UNKNOWN in item.issues
    assert item.authority_requirement is AuthorityRequirement.UNKNOWN, (
        "an UNKNOWN-freshness source may not ground an authority class"
    )
    assert item.serviceability is not Serviceability.READY
    assert item.actor_can_act is not True


# ==========================================================================
# 4. EFFECT_UNKNOWN + time-critical
# ==========================================================================


def test_04_effect_unknown_time_critical_is_interrupt_now_and_blocked() -> None:
    """§6.3: EFFECT_UNKNOWN blocks action/retry/failover but does not erase
    time pressure — the pressure class is preserved and serviceability blocks.
    """
    unknown_effect = demand(
        "d-effect-unknown",
        window=WindowPressure.BEFORE_NEXT_FOCUS_BOUNDARY,
        autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
        effect=EffectState.EFFECT_UNKNOWN,
        target=ActionTarget(state=TargetState.RESOLVED, target_ref="job-ROOT-7#ceo-sol-a"),
    )
    applied_twin = demand(
        "d-effect-applied",
        window=WindowPressure.BEFORE_NEXT_FOCUS_BOUNDARY,
        autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
        effect=EffectState.APPLIED,
        target=ActionTarget(state=TargetState.RESOLVED, target_ref="job-ROOT-8#ceo-sol-a"),
    )
    external = demand(
        "d-effect-external-blocker",
        window=WindowPressure.BEFORE_NEXT_FOCUS_BOUNDARY,
        autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
        effect=EffectState.EFFECT_UNKNOWN,
        blockers=(
            (ServiceabilityReason.EXTERNAL_BLOCKER, "upstream vendor incident"),
        ),
    )
    result = compute_attention_frontier(
        [unknown_effect, applied_twin, external], snapshot_identity=SNAPSHOT
    )
    blocked = item_of(result, "d-effect-unknown")
    ready = item_of(result, "d-effect-applied")

    assert blocked.attention_class is AttentionClass.INTERRUPT_NOW
    assert PressureReason.DECISION_WINDOW_BEFORE_NEXT_FOCUS in blocked.pressure_reasons
    assert blocked.serviceability is Serviceability.BLOCKED
    assert blocked.serviceability_reasons == (ServiceabilityReason.EFFECT_UNKNOWN,)
    assert blocked.actor_can_act is False
    assert blocked.projection_relation is ProjectionRelation.ROOT_VISIBLE
    assert PressureReason.DECISION_WINDOW_BEFORE_NEXT_FOCUS.value in blocked.explanation_reasons
    assert ServiceabilityReason.EFFECT_UNKNOWN.value in blocked.explanation_reasons

    # Blocked never means less urgent: identical pressure to the serviceable twin.
    assert blocked.attention_class is ready.attention_class
    assert blocked.pressure_reasons == ready.pressure_reasons
    assert ready.serviceability is Serviceability.READY
    assert ready.actor_can_act is True

    # An accepted source-owner blocker stacks with EFFECT_UNKNOWN; reasons are
    # deduplicated and deterministically ordered, and urgency still stands.
    stacked = item_of(result, "d-effect-external-blocker")
    assert stacked.attention_class is AttentionClass.INTERRUPT_NOW
    assert stacked.serviceability is Serviceability.BLOCKED
    assert stacked.serviceability_reasons == (
        ServiceabilityReason.EFFECT_UNKNOWN,
        ServiceabilityReason.EXTERNAL_BLOCKER,
    )
    assert stacked.actor_can_act is False

    # Every independent interrupt root stays visible under SOL.
    sol = frontier_of(result, AuthorityRequirement.SOL)
    assert sol is not None
    assert sol.interrupt_member_count == 3
    assert set(sol.visible_demand_ids) == {
        "d-effect-unknown", "d-effect-applied", "d-effect-external-blocker"
    }


def test_04b_a_conflicted_effect_or_capacity_source_is_not_reported_as_stale() -> None:
    """§3.3 + §5.8: ``Fact.conflict`` and ``SourceRef.freshness`` are
    independent attributes with independent codes, and the engine's own
    ``_grounded`` already separates ``CONFLICTED_PRESSURE_SOURCE`` from
    ``STALE_PRESSURE_SOURCE``. A CURRENT source whose owners disagree is a
    conflict; calling it stale reports a false cause and makes an owner
    disagreement look like a refresh problem.
    """
    conflicted_effect = demand(
        "d-conflict-effect",
        window=WindowPressure.BEFORE_NEXT_FOCUS_BOUNDARY,
        autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
        ready_at="2026-09-01T00:00:00Z",
    )
    conflicted_effect = dataclasses.replace(
        conflicted_effect,
        effect_state=Fact(
            value=EffectState.APPLIED,
            source=src("executive_os:effect-ledger", owner=SourceOwner.EXECUTIVE_OS),
            conflict=True,
        ),
    )
    conflicted_capacity = demand(
        "d-conflict-capacity",
        window=WindowPressure.BEFORE_NEXT_FOCUS_BOUNDARY,
        autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
        ready_at="2026-09-02T00:00:00Z",
    )
    conflicted_capacity = dataclasses.replace(
        conflicted_capacity,
        capacity_state=Fact(
            value=CapacityState.AVAILABLE,
            source=src("capacity:executive-service", owner=SourceOwner.CAPACITY),
            conflict=True,
        ),
    )
    result = compute_attention_frontier(
        [conflicted_effect, conflicted_capacity], snapshot_identity=SNAPSHOT
    )

    for did in ("d-conflict-effect", "d-conflict-capacity"):
        item = item_of(result, did)
        # Undisputed: contested evidence never proves the path is usable, and
        # never erases the time pressure.
        assert item.serviceability is not Serviceability.READY, did
        assert item.actor_can_act is not True, did
        assert item.attention_class is AttentionClass.INTERRUPT_NOW, did
        # The source itself is CURRENT — every source ref on this demand says so.
        assert all(
            ref.freshness is Freshness.CURRENT for ref in item.source_receipts
        ), did
        assert ServiceabilityReason.STALE_LOAD_BEARING_SOURCE not in (
            item.serviceability_reasons
        ), f"{did}: a current-but-contested source is not a stale source"
        assert Issue.STALE_PRESSURE_SOURCE not in item.issues, (
            f"{did}: conflict has its own code (CONFLICTED_PRESSURE_SOURCE)"
        )


# ==========================================================================
# 5. Old valid wait vs overdue wait — no invented waits
# ==========================================================================


def test_05_typed_waits_are_honoured_and_never_invented() -> None:
    """§5.7/§3.2: an explicit typed wait is valid only while its review
    boundary holds; uncertainty alone never creates a wait; age never converts
    a valid wait into false urgency (§9).
    """
    demands = [
        # A very old, still-valid wait.
        demand(
            "d-wait-valid-old",
            wait=WaitContext(
                kind="external_calendar_event",
                review_boundary_reached=False,
                expected_information_event=True,
                detail="FOMC statement on the scheduled date",
            ),
            reversibility=Reversibility.REVERSIBLE,
            ready_at="2023-01-01T00:00:00Z",
        ),
        # Overdue: the review boundary has arrived.
        demand(
            "d-wait-overdue",
            wait=WaitContext(
                kind="external_calendar_event", review_boundary_reached=True
            ),
            ready_at="2026-09-01T00:00:00Z",
        ),
        # Unknown boundary: must never be read as "still waiting".
        demand(
            "d-wait-boundary-unknown",
            wait=WaitContext(
                kind="external_calendar_event", review_boundary_reached=None
            ),
            ready_at="2026-09-02T00:00:00Z",
        ),
        # Conflicted wait evidence: uncertainty is not option value.
        demand(
            "d-wait-conflicted",
            wait=WaitContext(
                kind="external_calendar_event", review_boundary_reached=False
            ),
            wait_conflict=True,
            ready_at="2026-09-03T00:00:00Z",
        ),
        # Irreversible action may not hide behind a wait.
        demand(
            "d-wait-irreversible",
            wait=WaitContext(
                kind="external_calendar_event", review_boundary_reached=False
            ),
            reversibility=Reversibility.IRREVERSIBLE,
            ready_at="2026-09-04T00:00:00Z",
        ),
        # An emergency may never be hidden by a valid wait.
        demand(
            "d-wait-with-active-harm",
            wait=WaitContext(
                kind="external_calendar_event", review_boundary_reached=False
            ),
            impact=ImpactState.ACTIVE_HARM,
            reversibility=Reversibility.REVERSIBLE,
            ready_at="2026-09-05T00:00:00Z",
        ),
        # No wait fact at all.
        demand("d-wait-absent", autonomy=_OMIT, ready_at="2026-09-06T00:00:00Z"),
    ]
    result = compute_attention_frontier(demands, snapshot_identity=SNAPSHOT)

    valid = item_of(result, "d-wait-valid-old")
    assert valid.attention_class is AttentionClass.VALID_WAIT
    assert valid.pressure_reasons == (PressureReason.TYPED_WAIT_ACTIVE,)
    assert valid.wait_context is not None
    assert valid.wait_context.kind == "external_calendar_event"
    assert valid.is_fairness_sentinel is False  # age never makes a wait overdue

    for did in (
        "d-wait-overdue",
        "d-wait-boundary-unknown",
        "d-wait-conflicted",
        "d-wait-irreversible",
        "d-wait-absent",
    ):
        item = item_of(result, did)
        assert item.attention_class is not AttentionClass.VALID_WAIT, did
        assert PressureReason.TYPED_WAIT_ACTIVE not in item.pressure_reasons, did

    assert Issue.WAIT_REVIEW_BOUNDARY_UNKNOWN in item_of(
        result, "d-wait-boundary-unknown"
    ).issues
    assert Issue.WAIT_REVIEW_BOUNDARY_UNKNOWN not in item_of(result, "d-wait-absent").issues
    assert item_of(result, "d-wait-absent").wait_context is None

    emergency = item_of(result, "d-wait-with-active-harm")
    assert emergency.attention_class is AttentionClass.INTERRUPT_NOW
    assert PressureReason.ACTIVE_HARM in emergency.pressure_reasons

    # Invented waits must be exactly zero.
    waiting = [i.demand_id for i in result.items
               if i.attention_class is AttentionClass.VALID_WAIT]
    assert waiting == ["d-wait-valid-old"]


# ==========================================================================
# 6. Safe autonomous progress vs NO_SAFE_PROGRESS + exact unblock set
# ==========================================================================


def test_06_safe_progress_batches_while_no_safe_progress_takes_focus() -> None:
    """§5.6/§5.4: work that can safely continue should not interrupt, while
    no-safe-progress plus an exact dependency unblock set earns focus and
    exposes the exact blocked member refs.
    """
    exact_unblocks = ("WS-ALPHA", "WS-BETA", "WS-GAMMA")
    demands = [
        demand("d-progress-full", autonomy=AutonomousProgress.FULL_SAFE_PROGRESS),
        demand(
            "d-progress-none",
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            unblocks=exact_unblocks,
        ),
        demand("d-progress-unknown", autonomy=_OMIT),
    ]
    result = compute_attention_frontier(demands, snapshot_identity=SNAPSHOT)

    full = item_of(result, "d-progress-full")
    assert full.attention_class is AttentionClass.AUTONOMOUS_CONTINUE
    assert full.pressure_reasons == (PressureReason.SAFE_AUTONOMOUS_PROGRESS,)
    assert full.downstream_unblocks == ()
    assert full.factor_vector["autonomous_progress"] == "FULL_SAFE_PROGRESS"

    blocked = item_of(result, "d-progress-none")
    assert blocked.attention_class is AttentionClass.FOCUS_NOW
    assert PressureReason.NO_SAFE_AUTONOMOUS_PROGRESS in blocked.pressure_reasons
    assert PressureReason.EXACT_DEPENDENCY_UNBLOCK in blocked.pressure_reasons
    assert blocked.downstream_unblocks == exact_unblocks
    assert blocked.factor_vector["exact_unblock_count"] == 3

    # Unknown autonomy is never read as "safe to continue".
    unknown = item_of(result, "d-progress-unknown")
    assert unknown.attention_class is not AttentionClass.AUTONOMOUS_CONTINUE
    assert unknown.attention_class is AttentionClass.BATCH_NEXT
    assert Issue.AUTONOMY_UNKNOWN in unknown.issues
    assert unknown.factor_vector["autonomous_progress"] == "UNKNOWN"

    # Fan-out size is exposed as an exact ref set, never as a "critical path".
    assert "critical_path" not in blocked.factor_vector
    assert all(ref in blocked.downstream_unblocks for ref in exact_unblocks)


# ==========================================================================
# 7. Active resource burn raises pressure, never authority
# ==========================================================================


def test_07_active_resource_burn_raises_pressure_without_touching_authority() -> None:
    """§5.5 + §3.1.2: current burn may raise pressure; it may never change the
    authority class nor authorize retry/target transfer/failover.
    """
    target = ActionTarget(state=TargetState.RESOLVED, target_ref="job-ROOT-3#worker-7")
    idle = demand(
        "d-burn-idle",
        authority=AuthorityRequirement.COO_OR_WORKER,
        burn=BurnState.NONE,
        capacity=CapacityState.AVAILABLE,
        target=target,
    )
    burning = demand(
        "d-burn-active",
        authority=AuthorityRequirement.COO_OR_WORKER,
        burn=BurnState.ACTIVE,
        capacity=CapacityState.AVAILABLE,
        target=target,
    )
    result = compute_attention_frontier([idle, burning], snapshot_identity=SNAPSHOT)

    quiet = item_of(result, "d-burn-idle")
    hot = item_of(result, "d-burn-active")

    # Pressure rose...
    assert quiet.attention_class is AttentionClass.AUTONOMOUS_CONTINUE
    assert hot.attention_class is AttentionClass.FOCUS_NOW
    assert PressureReason.ACTIVE_RESOURCE_BURN in hot.pressure_reasons
    assert hot.active_resource_burn == "ACTIVE"
    assert quiet.active_resource_burn == "NONE"

    # ...authority did not.
    assert hot.authority_requirement is AuthorityRequirement.COO_OR_WORKER
    assert hot.authority_requirement is quiet.authority_requirement
    assert frontier_of(result, AuthorityRequirement.SOL) is None
    assert frontier_of(result, AuthorityRequirement.CHAIRMAN) is None
    coo = frontier_of(result, AuthorityRequirement.COO_OR_WORKER)
    assert coo is not None
    assert set(coo.visible_demand_ids) == {"d-burn-idle", "d-burn-active"}

    # Burn grants no target transfer or failover.
    assert hot.exact_action_target == quiet.exact_action_target == "job-ROOT-3#worker-7"


# ==========================================================================
# 8. Timestamp refresh attack
# ==========================================================================


def test_08_re_observation_never_resets_actionable_age_or_fairness_order() -> None:
    """§5.9 + §11: repeated Wake delivery, file modification, summary
    regeneration or observation refresh never resets actionable age.
    """
    baseline = compute_attention_frontier(
        mixed_corpus(), snapshot_identity=SNAPSHOT,
        proven_window_collisions=MIXED_COLLISIONS,
    )
    # The attack: re-observe *only* the oldest fairness-protected demand at a
    # much later observation time, byte-identical values otherwise.
    attacked = compute_attention_frontier(
        mixed_corpus(refreshed=frozenset({"d08-coo-old-batch"})),
        snapshot_identity=SNAPSHOT,
        proven_window_collisions=MIXED_COLLISIONS,
    )
    # And the blunt variant: re-observe everything.
    everything = compute_attention_frontier(
        mixed_corpus(refreshed=frozenset(d.demand_id for d in mixed_corpus())),
        snapshot_identity=SNAPSHOT,
        proven_window_collisions=MIXED_COLLISIONS,
    )

    assert baseline.fairness_sentinels == ("d08-coo-old-batch",)
    for other in (attacked, everything):
        assert decision_fingerprint(other) == decision_fingerprint(baseline)
        assert other.fairness_sentinels == baseline.fairness_sentinels
        for item in baseline.items:
            twin = item_of(other, item.demand_id)
            assert twin.became_actionable_at == item.became_actionable_at
            assert twin.projection_relation is item.projection_relation
            assert twin.attention_class is item.attention_class

    # The refreshed observation time *is* still disclosed on the receipts —
    # truthfully carried, just powerless.
    refreshed_item = item_of(attacked, "d08-coo-old-batch")
    assert any(ref.observed_at == LATER for ref in refreshed_item.source_receipts)
    assert refreshed_item.became_actionable_at == "2023-11-11T00:00:00Z"


# ==========================================================================
# 9. Context batching and fairness
# ==========================================================================


def test_09a_oldest_ready_fairness_sentinel_surfaces_without_changing_class() -> None:
    """§9: when every eligible ordinary demand in an authority partition is
    omitted, the oldest-ready one is exposed as a sentinel — visibility
    protection only, never a priority score and never a stronger class.
    """
    root = (FaninKind.ROOT_JOB, "job-ROOT-42")
    demands = [
        demand(
            "d-fair-0-interrupt",
            window=WindowPressure.EXPIRED,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            roots=(root,),
            ready_at="2026-05-05T00:00:00Z",
        ),
        demand("d-fair-1-old", autonomy=_OMIT, roots=(root,),
               ready_at="2024-02-02T00:00:00Z"),
        demand("d-fair-2-new", autonomy=_OMIT, roots=(root,),
               ready_at="2026-06-06T00:00:00Z"),
        # Far older, but an intentional wait: never eligible for the sentinel.
        demand(
            "d-fair-3-wait",
            wait=WaitContext(kind="accepted_external_condition",
                             review_boundary_reached=False),
            reversibility=Reversibility.REVERSIBLE,
            ready_at="2019-01-01T00:00:00Z",
        ),
    ]
    result = compute_attention_frontier(demands, snapshot_identity=SNAPSHOT)

    assert result.fairness_sentinels == ("d-fair-1-old",)
    sentinel = item_of(result, "d-fair-1-old")
    assert sentinel.is_fairness_sentinel is True
    assert sentinel.projection_relation is ProjectionRelation.ROOT_VISIBLE
    assert receipt_of(result, "d-fair-1-old") is None
    # Fairness service does not rewrite the pressure class.
    assert sentinel.attention_class is AttentionClass.BATCH_NEXT
    assert sentinel.pressure_reasons == (PressureReason.NO_GROUNDED_PRESSURE,)
    # The newer sibling stays lawfully covered, with its receipt.
    assert relation(result, "d-fair-2-new") is ProjectionRelation.COVERED_BY_BUNDLE
    assert receipt_of(result, "d-fair-2-new") is not None
    # The sentinel never suppressed the interrupt.
    assert relation(result, "d-fair-0-interrupt") is ProjectionRelation.ROOT_VISIBLE
    # The valid wait was not made overdue early.
    wait_item = item_of(result, "d-fair-3-wait")
    assert wait_item.attention_class is AttentionClass.VALID_WAIT
    assert wait_item.is_fairness_sentinel is False


def test_09b_unknown_ready_time_is_a_coverage_gap_not_age_zero() -> None:
    """§9 + §11: unknown ready time appears as a coverage gap, and no
    allocator-local age state may be invented to replace it.
    """
    root = (FaninKind.ROOT_JOB, "job-ROOT-43")
    demands = [
        demand(
            "d-gap-0-interrupt",
            window=WindowPressure.EXPIRED,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            roots=(root,),
            ready_at=_OMIT,
        ),
        demand("d-gap-1", autonomy=_OMIT, roots=(root,), ready_at=_OMIT),
        demand("d-gap-2", autonomy=_OMIT, roots=(root,), ready_at=_OMIT),
    ]
    result = compute_attention_frontier(demands, snapshot_identity=SNAPSHOT)

    assert result.fairness_sentinels == ()
    assert result.coverage_summary["ready_age_unknown"] == 3
    for did in ("d-gap-0-interrupt", "d-gap-1", "d-gap-2"):
        item = item_of(result, did)
        assert item.became_actionable_at is None
        assert Issue.READY_AGE_UNKNOWN in item.issues
        assert item.is_fairness_sentinel is False


def test_09c_context_affinity_never_hides_an_interrupt_or_moves_authority() -> None:
    """§5.10: context affinity may group equivalent ordinary work; it may never
    hide/demote an interrupt or change authority.
    """
    shared = "ctx-breathing-platform"
    demands = [
        demand(
            "d-ctx-interrupt",
            authority=AuthorityRequirement.CHAIRMAN,
            window=WindowPressure.EXPIRED,
            impact=ImpactState.ACTIVE_HARM,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            context_key=shared,
            display_context="Breathing Platform",
            responsibility_ref="WS-BREATHING-PLATFORM",
        )
    ] + [
        demand(
            f"d-ctx-batch-{n}",
            autonomy=_OMIT,
            context_key=shared,
            display_context="Breathing Platform",
            responsibility_ref="WS-BREATHING-PLATFORM",
            ready_at=f"2026-0{n + 1}-01T00:00:00Z",
        )
        for n in range(3)
    ]
    result = compute_attention_frontier(demands, snapshot_identity=SNAPSHOT)

    interrupt = item_of(result, "d-ctx-interrupt")
    assert interrupt.projection_relation is ProjectionRelation.ROOT_VISIBLE
    assert interrupt.authority_requirement is AuthorityRequirement.CHAIRMAN
    assert interrupt.bundle_id is None
    # Shared free-text context is not a canonical root and cannot bundle.
    assert result.bundles == ()
    for n in range(3):
        item = item_of(result, f"d-ctx-batch-{n}")
        assert item.authority_requirement is AuthorityRequirement.SOL
        assert item.projection_relation is ProjectionRelation.ROOT_VISIBLE
    assert all(
        o.relation is not ProjectionRelation.DEFERRED_EQUIVALENT_CONTEXT
        or o.demand_id != "d-ctx-interrupt"
        for o in result.omissions
    )
    assert result.omissions == ()


# ==========================================================================
# 10. Multiple independent emergencies; unknown vs proven feasibility
# ==========================================================================


def test_10_multiple_independent_emergencies_report_honest_feasibility() -> None:
    """§10: after exact fan-in every independent INTERRUPT_NOW root stays
    visible; multiple interrupts prove congestion, not overload; missing
    capacity evidence is UNKNOWN feasibility, never inferred collision.
    """
    root = (FaninKind.WAKE_CORRELATION, "wake-corr-5")
    demands = [
        demand(
            "d-emg-sol-a",
            window=WindowPressure.EXPIRED,
            impact=ImpactState.ACTIVE_HARM,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            roots=(root,),
            ready_at="2026-09-01T00:00:00Z",
        ),
        demand(
            "d-emg-sol-b",
            window=WindowPressure.EXPIRED,
            impact=ImpactState.ACTIVE_HARM,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            roots=(root,),
            ready_at="2026-09-02T00:00:00Z",
        ),
        demand(
            "d-emg-sol-c",
            window=WindowPressure.BEFORE_NEXT_FOCUS_BOUNDARY,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            target=ActionTarget(state=TargetState.UNAVAILABLE),
            ready_at="2026-09-03T00:00:00Z",
        ),
        demand(
            "d-emg-chair",
            authority=AuthorityRequirement.CHAIRMAN,
            impact=ImpactState.ACTIVE_HARM,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            ready_at="2026-09-04T00:00:00Z",
        ),
        demand(
            "d-emg-worker-quiet",
            authority=AuthorityRequirement.COO_OR_WORKER,
            autonomy=_OMIT,
            ready_at="2026-09-05T00:00:00Z",
        ),
    ]

    unknown = compute_attention_frontier(demands, snapshot_identity=SNAPSHOT)
    sol = frontier_of(unknown, AuthorityRequirement.SOL)
    assert sol is not None
    assert sol.interrupt_member_count == 3
    assert sol.interrupt_root_count == 2  # a+b share one exact root
    assert sol.concurrent_demand is ConcurrentDemand.MULTIPLE_INDEPENDENT
    assert sol.service_feasibility is ServiceFeasibility.UNKNOWN
    assert sol.feasibility_receipts
    assert "unknown" in sol.feasibility_receipts[0]

    # Both independent interrupt roots remain visible.
    assert relation(unknown, "d-emg-sol-a") is ProjectionRelation.ROOT_VISIBLE
    assert relation(unknown, "d-emg-sol-c") is ProjectionRelation.ROOT_VISIBLE
    assert {"d-emg-sol-a", "d-emg-sol-c"} <= set(sol.visible_demand_ids)

    chair = frontier_of(unknown, AuthorityRequirement.CHAIRMAN)
    assert chair is not None
    assert chair.concurrent_demand is ConcurrentDemand.SINGLE
    assert chair.service_feasibility is ServiceFeasibility.NOT_APPLICABLE
    assert chair.feasibility_receipts == ()

    coo = frontier_of(unknown, AuthorityRequirement.COO_OR_WORKER)
    assert coo is not None
    assert coo.concurrent_demand is ConcurrentDemand.NONE
    assert coo.service_feasibility is ServiceFeasibility.NOT_APPLICABLE

    # With source-backed proof the collision becomes assertable — and only then.
    proof = ("capacity:exec-service-2026-09-20", "wake:window-proof-7")
    proven = compute_attention_frontier(
        demands, snapshot_identity=SNAPSHOT, proven_window_collisions={"SOL": proof}
    )
    sol_proven = frontier_of(proven, AuthorityRequirement.SOL)
    assert sol_proven is not None
    assert sol_proven.concurrent_demand is ConcurrentDemand.PROVEN_WINDOW_COLLISION
    assert sol_proven.service_feasibility is ServiceFeasibility.PROVEN_COLLISION
    assert sol_proven.feasibility_receipts == proof

    # Congestion grants no authority escalation and touches no other partition.
    for did in (d.demand_id for d in demands):
        assert item_of(proven, did).authority_requirement is item_of(
            unknown, did
        ).authority_requirement
    assert frontier_of(proven, AuthorityRequirement.CHAIRMAN) == chair


# ==========================================================================
# 11. Genuine incomparable tradeoff
# ==========================================================================


def test_11_genuine_tradeoff_keeps_both_demands_visible_and_incomparable() -> None:
    """§8: a real tradeoff (critical window vs larger exact unblock and no safe
    progress) may not be secretly totalized — both stay on the frontier.
    """
    window_side = demand(
        "d-trade-window",
        window=WindowPressure.NEAR,
        autonomy=AutonomousProgress.FULL_SAFE_PROGRESS,
        unblocks=(),
        ready_at="2026-09-01T00:00:00Z",
    )
    unblock_side = demand(
        "d-trade-unblock",
        window=WindowPressure.OPEN,
        autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
        unblocks=("WS-1", "WS-2", "WS-3"),
        ready_at="2026-09-02T00:00:00Z",
    )
    # A demand with one genuinely unknown dimension is incomparable, not weaker.
    unknown_side = demand(
        "d-trade-unknown-burn",
        window=WindowPressure.NEAR,
        autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
        unblocks=("WS-4",),
        burn=_OMIT,
        ready_at="2026-09-03T00:00:00Z",
    )
    forward = compute_attention_frontier(
        [window_side, unblock_side, unknown_side], snapshot_identity=SNAPSHOT
    )
    reversed_order = compute_attention_frontier(
        [unknown_side, unblock_side, window_side], snapshot_identity=SNAPSHOT
    )

    for result in (forward, reversed_order):
        for did in ("d-trade-window", "d-trade-unblock", "d-trade-unknown-burn"):
            assert item_of(result, did).attention_class is AttentionClass.FOCUS_NOW
            assert relation(result, did) is ProjectionRelation.ROOT_VISIBLE
        assert result.omissions == ()
        assert (
            comparison(result, "d-trade-window", "d-trade-unblock")
            is Comparison.INCOMPARABLE_TRADEOFF
        )
        assert (
            comparison(result, "d-trade-window", "d-trade-unknown-burn")
            is Comparison.INCOMPARABLE_UNKNOWN
        )
        sol = frontier_of(result, AuthorityRequirement.SOL)
        assert sol is not None
        assert set(sol.visible_demand_ids) == {
            "d-trade-window", "d-trade-unblock", "d-trade-unknown-burn"
        }

    # Input order has no effect whatsoever on the decision.
    assert decision_fingerprint(forward) == decision_fingerprint(reversed_order)


# ==========================================================================
# 12. Owner-relative freshness
# ==========================================================================


def test_12_freshness_is_owner_relative_and_never_re_derived_from_a_clock() -> None:
    """§5.8: freshness is the source owner's verdict. Two owners may classify
    the *same* observation instant differently and the engine must honour each
    verdict rather than invent a universal TTL.
    """
    same_instant = "2026-09-20T08:00:00Z"
    fresh_owner = demand(
        "d-fresh-agentos",
        window=WindowPressure.NEAR,
        window_source=src(
            "agentos:decision-gate-window",
            owner=SourceOwner.AGENT_OS,
            observed_at=same_instant,
            freshness=Freshness.CURRENT,
        ),
    )
    stale_owner = demand(
        "d-fresh-wake",
        window=WindowPressure.NEAR,
        window_source=src(
            "wake:response-window",
            owner=SourceOwner.WAKE,
            observed_at=same_instant,
            freshness=Freshness.STALE,
        ),
    )
    third_owner = demand(
        "d-fresh-capacity",
        window=WindowPressure.NEAR,
        window_source=src(
            "capacity:service-window",
            owner=SourceOwner.CAPACITY,
            observed_at=same_instant,
            freshness=Freshness.CURRENT,
        ),
    )
    result = compute_attention_frontier(
        [fresh_owner, stale_owner, third_owner], snapshot_identity=SNAPSHOT
    )

    for did in ("d-fresh-agentos", "d-fresh-capacity"):
        item = item_of(result, did)
        assert item.factor_vector["decision_window"] == "NEAR"
        assert PressureReason.DECISION_WINDOW_NEAR in item.pressure_reasons
        assert item.attention_class is AttentionClass.FOCUS_NOW
        assert Issue.STALE_PRESSURE_SOURCE not in item.issues

    stale = item_of(result, "d-fresh-wake")
    assert stale.factor_vector["decision_window"] == "UNKNOWN"
    assert PressureReason.DECISION_WINDOW_NEAR not in stale.pressure_reasons
    assert Issue.STALE_PRESSURE_SOURCE in stale.issues
    assert Issue.WINDOW_UNKNOWN in stale.issues
    assert stale.attention_class is not AttentionClass.FOCUS_NOW

    # Identical observation instants, opposite verdicts: no universal TTL.
    observed = {
        ref.observed_at
        for item in result.items
        for ref in item.source_receipts
        if ref.ref.endswith("window")
    }
    assert observed == {same_instant}

    totals = result.source_freshness_summary
    assert totals[Freshness.STALE.value] == 1
    assert totals[Freshness.UNKNOWN.value] == 0
    assert totals[Freshness.CURRENT.value] == sum(totals.values()) - 1

    # The stale-sourced demand is incomparable, never treated as window-OPEN.
    assert (
        comparison(result, "d-fresh-agentos", "d-fresh-wake")
        in (None, Comparison.INCOMPARABLE_UNKNOWN)
    )


# ==========================================================================
# 13. WSJF / cost-of-delay category error
# ==========================================================================


def test_13_huge_cost_of_delay_reorders_nothing() -> None:
    """§5.11: V1 has no universal WSJF. A source-backed cost of delay is
    carried with receipts but may not order, dominate or rescue anything.
    """
    huge = CostOfDelay(
        basis="source-owned incident revenue model", value="USD 40,000,000 per hour"
    )
    tiny = CostOfDelay(basis="source-owned incident revenue model", value="USD 3 per year")
    twin_a = demand("d-cod-cheap", autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
                    unblocks=("WS-1",), cost=tiny, ready_at="2026-09-01T00:00:00Z")
    twin_b = demand(
        "d-cod-expensive",
        title="40 story points, 3-week PR, USD 40m/hour of delay cost, CEO CRITICAL",
        autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
        unblocks=("WS-1",),
        cost=huge,
        display_context="implementation size: 3 weeks",
        ready_at="2026-09-02T00:00:00Z",
    )
    # Strictly weaker pressure vector but an enormous delay cost: still dominated.
    weak_but_costly = demand(
        "d-cod-weak-but-costly",
        autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
        unblocks=(),
        cost=huge,
        ready_at="2026-09-03T00:00:00Z",
    )
    result = compute_attention_frontier(
        [twin_a, twin_b, weak_but_costly], snapshot_identity=SNAPSHOT
    )

    cheap = item_of(result, "d-cod-cheap")
    expensive = item_of(result, "d-cod-expensive")

    assert comparison(result, "d-cod-cheap", "d-cod-expensive") is Comparison.EQUIVALENT
    assert cheap.projection_relation is ProjectionRelation.ROOT_VISIBLE
    assert expensive.projection_relation is ProjectionRelation.ROOT_VISIBLE
    assert cheap.factor_vector == expensive.factor_vector

    # Carried with receipts, but outside the factor vector.
    assert expensive.cost_of_delay == huge
    assert "cost_of_delay" not in expensive.factor_vector
    assert set(expensive.factor_vector) == {
        "decision_window",
        "actual_impact",
        "blast_radius",
        "reversibility",
        "autonomous_progress",
        "active_resource_burn",
        "exact_unblock_count",
    }

    # A huge delay cost cannot rescue a strictly weaker demand.
    assert relation(result, "d-cod-weak-but-costly") is ProjectionRelation.DOMINATED_BY
    receipt = receipt_of(result, "d-cod-weak-but-costly")
    assert receipt is not None
    assert receipt.covered_by in {"d-cod-cheap", "d-cod-expensive"}

    # No score/rank/priority surface exists to be gamed (§12).
    names = {f.name for f in dataclasses.fields(FrontierItem)}
    assert not any(
        token in name for name in names for token in ("score", "rank", "priority")
    )
    assert result.schema == RESULT_SCHEMA


# ==========================================================================
# 14. Exact Sol action target: unavailable / conflict / unknown
# ==========================================================================


def test_14_exact_sol_target_states_block_service_without_touching_urgency() -> None:
    """§6.2/§3.3: the exact action target is consumed as a projection. Every
    non-resolved state blocks or unknowns the action path while the emergency
    stays an emergency.
    """
    def emergency(demand_id: str, **kwargs) -> AttentionDemand:
        return demand(
            demand_id,
            impact=ImpactState.ACTIVE_HARM,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            ready_at="2026-09-01T00:00:00Z",
            **kwargs,
        )

    demands = [
        emergency("d-target-1-unavailable",
                  target=ActionTarget(state=TargetState.UNAVAILABLE)),
        emergency("d-target-2-conflict", target=ActionTarget(state=TargetState.CONFLICT)),
        emergency("d-target-3-unknown", target=ActionTarget(state=TargetState.UNKNOWN)),
        emergency(
            "d-target-4-resolved-but-conflicted",
            target=ActionTarget(state=TargetState.RESOLVED,
                                target_ref="job-ROOT-7#ceo-sol-alias-a"),
            target_conflict=True,
        ),
        emergency(
            "d-target-5-resolved",
            target=ActionTarget(state=TargetState.RESOLVED,
                                target_ref="job-ROOT-9#ceo-sol-alias-b"),
        ),
        emergency("d-target-6-not-applicable",
                  target=ActionTarget(state=TargetState.NOT_APPLICABLE)),
    ]
    result = compute_attention_frontier(demands, snapshot_identity=SNAPSHOT)

    expected = {
        "d-target-1-unavailable": (
            Serviceability.BLOCKED, ServiceabilityReason.ACTION_TARGET_UNAVAILABLE, False
        ),
        "d-target-2-conflict": (
            Serviceability.BLOCKED, ServiceabilityReason.ACTION_TARGET_CONFLICT, False
        ),
        "d-target-3-unknown": (
            Serviceability.UNKNOWN, ServiceabilityReason.ACTION_TARGET_UNKNOWN, None
        ),
    }
    for did, (state, reason, can_act) in expected.items():
        item = item_of(result, did)
        assert item.serviceability is state, did
        assert reason in item.serviceability_reasons, did
        assert item.actor_can_act is can_act, did
        assert item.exact_action_target is None, did
        # Urgency is untouched by serviceability.
        assert item.attention_class is AttentionClass.INTERRUPT_NOW, did
        assert PressureReason.ACTIVE_HARM in item.pressure_reasons, did
        assert item.projection_relation is ProjectionRelation.ROOT_VISIBLE, did

    # A contested exact target is never handed out and never claims usability,
    # whichever non-usable state the engine reports.
    contested = item_of(result, "d-target-4-resolved-but-conflicted")
    assert contested.exact_action_target is None
    assert contested.serviceability is not Serviceability.READY
    assert contested.actor_can_act is not True
    assert contested.attention_class is AttentionClass.INTERRUPT_NOW
    assert contested.projection_relation is ProjectionRelation.ROOT_VISIBLE

    assert Issue.TARGET_EVIDENCE_UNAVAILABLE in item_of(result, "d-target-3-unknown").issues

    resolved = item_of(result, "d-target-5-resolved")
    assert resolved.serviceability is Serviceability.READY
    assert resolved.exact_action_target == "job-ROOT-9#ceo-sol-alias-b"
    assert resolved.actor_can_act is True

    not_applicable = item_of(result, "d-target-6-not-applicable")
    assert not_applicable.exact_action_target is None
    assert not_applicable.attention_class is AttentionClass.INTERRUPT_NOW

    sol = frontier_of(result, AuthorityRequirement.SOL)
    assert sol is not None
    assert sol.interrupt_root_count == 6
    assert len(sol.visible_demand_ids) == 6


def test_14b_a_conflicted_source_is_reported_as_a_conflict_not_as_staleness() -> None:
    """§3.3: typed ``serviceability_reasons`` must preserve the *source-specific*
    cause. Conflict and freshness are independent attributes of a ``Fact``
    (``Fact.conflict`` vs ``SourceRef.freshness``), the closed vocabulary has a
    separate code for each, and the engine's own ``_grounded`` already tells
    them apart. Reporting a current-but-contested source as stale is a false
    cause and hides an identity/authority disagreement behind a refresh
    problem.
    """
    contested_target = demand(
        "d-conflict-target",
        impact=ImpactState.ACTIVE_HARM,
        autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
        target=ActionTarget(state=TargetState.RESOLVED,
                            target_ref="job-ROOT-7#ceo-sol-alias-a"),
        target_conflict=True,
        ready_at="2026-09-01T00:00:00Z",
    )
    result = compute_attention_frontier([contested_target], snapshot_identity=SNAPSHOT)
    item = item_of(result, "d-conflict-target")

    # The undisputed part of the law first.
    assert item.exact_action_target is None
    assert item.actor_can_act is not True
    assert item.attention_class is AttentionClass.INTERRUPT_NOW

    assert ServiceabilityReason.ACTION_TARGET_CONFLICT in item.serviceability_reasons, (
        "a contested exact target is a target conflict, not a stale source"
    )
    assert ServiceabilityReason.STALE_LOAD_BEARING_SOURCE not in (
        item.serviceability_reasons
    ), "the source is CURRENT; only the owners disagree"


# ==========================================================================
# 15. Owner-fallback attack
# ==========================================================================


def test_15_missing_exact_target_never_falls_back_to_owner_or_sister_sol() -> None:
    """§6.2: no fallback to a workstream/seat default, no sister-Sol promotion.
    §7: bundling preserves per-member boundaries and grants no shared
    permission.
    """
    root = (FaninKind.ROOT_JOB, "job-ROOT-7")
    missing = demand(
        "d-sol-target-missing",
        authority=AuthorityRequirement.SOL,
        responsibility_ref="WS-BREATHING-PLATFORM",
        display_context="owner: ceo-sol",
        impact=ImpactState.ACTIVE_HARM,
        autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
        target=ActionTarget(state=TargetState.UNAVAILABLE),
        roots=(root,),
        ready_at="2026-09-01T00:00:00Z",
    )
    sister = demand(
        "d-sol-sister-resolved",
        authority=AuthorityRequirement.SOL,
        responsibility_ref="WS-BREATHING-PLATFORM",
        impact=ImpactState.ACTIVE_HARM,
        autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
        target=ActionTarget(state=TargetState.RESOLVED,
                            target_ref="job-ROOT-7#ceo-sol-alias-sister"),
        roots=(root,),
        ready_at="2026-09-02T00:00:00Z",
    )
    worker_owner = demand(
        "d-worker-same-workstream",
        authority=AuthorityRequirement.COO_OR_WORKER,
        responsibility_ref="WS-BREATHING-PLATFORM",
        autonomy=_OMIT,
        target=ActionTarget(state=TargetState.RESOLVED,
                            target_ref="job-ROOT-7#worker-placement-3"),
        ready_at="2026-09-03T00:00:00Z",
    )
    result = compute_attention_frontier(
        [missing, sister, worker_owner], snapshot_identity=SNAPSHOT
    )

    orphan = item_of(result, "d-sol-target-missing")
    assert orphan.exact_action_target is None, "no owner/seat fallback is permitted"
    assert orphan.serviceability is Serviceability.BLOCKED
    assert ServiceabilityReason.ACTION_TARGET_UNAVAILABLE in orphan.serviceability_reasons
    assert orphan.actor_can_act is False
    assert orphan.attention_class is AttentionClass.INTERRUPT_NOW

    # Never the workstream owner, never the sister's alias, never the worker's.
    forbidden = {
        "WS-BREATHING-PLATFORM",
        "ceo-sol",
        "job-ROOT-7#ceo-sol-alias-sister",
        "job-ROOT-7#worker-placement-3",
    }
    assert orphan.exact_action_target not in forbidden
    assert orphan.responsibility_ref == "WS-BREATHING-PLATFORM"  # disclosed, not used

    # Sharing an exact root Job groups them but grants no shared permission.
    assert len(result.bundles) == 1
    bundle = result.bundles[0]
    assert bundle.canonical_root_ref == "ROOT_JOB:job-ROOT-7"
    assert set(bundle.members) == {"d-sol-target-missing", "d-sol-sister-resolved"}
    boundaries = {m: (a, s) for m, a, s in bundle.member_boundaries}
    assert boundaries["d-sol-target-missing"] == ("SOL", "BLOCKED")
    assert boundaries["d-sol-sister-resolved"] == ("SOL", "READY")
    assert item_of(result, "d-sol-sister-resolved").exact_action_target == (
        "job-ROOT-7#ceo-sol-alias-sister"
    )
    assert orphan.exact_action_target is None


# ==========================================================================
# 16. Permutation stability
# ==========================================================================


def test_16_result_is_byte_identical_under_fifty_input_permutations() -> None:
    """§8 + the engine's purity contract: the result is a function of the
    demand set alone and is invariant under input permutation.
    """
    baseline = compute_attention_frontier(
        mixed_corpus(), snapshot_identity=SNAPSHOT,
        proven_window_collisions=MIXED_COLLISIONS,
    )
    baseline_repr = repr(baseline)
    rng = random.Random(20260920)
    for _ in range(50):
        shuffled = mixed_corpus()
        rng.shuffle(shuffled)
        result = compute_attention_frontier(
            shuffled, snapshot_identity=SNAPSHOT,
            proven_window_collisions=MIXED_COLLISIONS,
        )
        assert repr(result) == baseline_repr
        assert result == baseline

    # The corpus really does exercise every projection relation and both
    # concurrency verdicts, so the stability claim is not vacuous.
    relations = {i.projection_relation for i in baseline.items}
    assert relations == {
        ProjectionRelation.ROOT_VISIBLE,
        ProjectionRelation.COVERED_BY_BUNDLE,
        ProjectionRelation.DOMINATED_BY,
    }
    assert len(baseline.items) == 10
    assert len(baseline.bundles) == 2
    assert baseline.fairness_sentinels == ("d08-coo-old-batch",)
    sol = frontier_of(baseline, AuthorityRequirement.SOL)
    assert sol is not None
    assert sol.concurrent_demand is ConcurrentDemand.PROVEN_WINDOW_COLLISION


# ==========================================================================
# 17. Receipt accounting
# ==========================================================================


def test_17a_every_omitted_demand_has_exactly_one_matching_receipt() -> None:
    """§3.4: every omitted ordinary raw demand requires an exact receipt, and
    the coverage summary must reconcile exactly.
    """
    result = compute_attention_frontier(
        mixed_corpus(), snapshot_identity=SNAPSHOT,
        proven_window_collisions=MIXED_COLLISIONS,
    )

    visible = {i.demand_id for i in result.items
               if i.projection_relation is ProjectionRelation.ROOT_VISIBLE}
    omitted = {i.demand_id for i in result.items
               if i.projection_relation is not ProjectionRelation.ROOT_VISIBLE}
    receipt_ids = [o.demand_id for o in result.omissions]

    assert set(receipt_ids) == omitted
    assert len(receipt_ids) == len(omitted)  # no duplicate receipts
    assert visible & omitted == set()
    assert visible | omitted == {i.demand_id for i in result.items}

    for omission in result.omissions:
        item = item_of(result, omission.demand_id)
        assert omission.relation is item.projection_relation
        assert omission.covered_by is not None
        assert omission.reason
        if omission.relation is ProjectionRelation.COVERED_BY_BUNDLE:
            bundle = next(b for b in result.bundles if b.bundle_id == omission.covered_by)
            assert omission.demand_id in bundle.members
            assert bundle.canonical_root_ref in omission.reason
            assert item.bundle_id == bundle.bundle_id
        else:
            assert omission.relation is ProjectionRelation.DOMINATED_BY
            assert omission.covered_by != omission.demand_id
            assert omission.covered_by in {i.demand_id for i in result.items}

    summary = result.coverage_summary
    assert summary["admitted_demands"] == len(result.items) == 10
    assert summary["visible_roots"] == len(visible)
    assert summary["omitted_with_receipt"] == len(result.omissions)
    assert summary["visible_roots"] + summary["omitted_with_receipt"] == (
        summary["admitted_demands"]
    )
    assert summary["bundles"] == len(result.bundles)
    assert summary["authority_unknown"] == sum(
        1 for i in result.items
        if i.authority_requirement is AuthorityRequirement.UNKNOWN
    )
    assert summary["ready_age_unknown"] == sum(
        1 for i in result.items if i.became_actionable_at is None
    )

    # A visible root never carries an omission receipt, and every sentinel is
    # visible by construction.
    for did in visible:
        assert receipt_of(result, did) is None
    for did in result.fairness_sentinels:
        assert did in visible
        assert item_of(result, did).is_fairness_sentinel is True

    # Every INTERRUPT_NOW demand is either visible or represented by the
    # visible canonical face of its own bundle (§3.4, §10).
    for item in result.items:
        if item.attention_class is not AttentionClass.INTERRUPT_NOW:
            continue
        if item.projection_relation is ProjectionRelation.ROOT_VISIBLE:
            continue
        bundle = next(b for b in result.bundles if b.bundle_id == item.bundle_id)
        assert relation(result, bundle.canonical_demand_id) is (
            ProjectionRelation.ROOT_VISIBLE
        )


def test_17b_an_omission_receipt_never_points_at_an_omitted_dominator() -> None:
    """Engine invariant (``executive_attention_frontier.py``: "A dominator that
    is itself omitted may not hide its subordinate") and §3.4/§13: an exact
    receipt must resolve to something on the frontier, or the raw demand is not
    reachable from the compact view.
    """
    root = (FaninKind.BLOCKER_ROOT, "BLK-X")
    demands = [
        demand(
            "x-a-canonical-interrupt",
            window=WindowPressure.EXPIRED,
            impact=ImpactState.ACTIVE_HARM,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            roots=(root,),
            ready_at=_OMIT,
        ),
        demand(
            "x-b-dominator",
            window=WindowPressure.NEAR,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            unblocks=("WS-1", "WS-2", "WS-3", "WS-4"),
            roots=(root,),
            ready_at=_OMIT,
        ),
        demand(
            "x-c-subordinate",
            window=WindowPressure.OPEN,
            autonomy=AutonomousProgress.NO_SAFE_PROGRESS,
            unblocks=("WS-1",),
            ready_at=_OMIT,
        ),
    ]
    result = compute_attention_frontier(demands, snapshot_identity=SNAPSHOT)

    # Preconditions: the dominator really is bundle-covered and really does
    # dominate the subordinate.
    assert relation(result, "x-b-dominator") is ProjectionRelation.COVERED_BY_BUNDLE
    assert comparison(result, "x-b-dominator", "x-c-subordinate") is Comparison.DOMINATES
    assert result.fairness_sentinels == ()

    receipt = receipt_of(result, "x-c-subordinate")
    if receipt is not None:
        # If it was hidden at all, it must be hidden behind a visible face.
        assert receipt.relation is ProjectionRelation.DOMINATED_BY
        assert relation(result, receipt.covered_by) is ProjectionRelation.ROOT_VISIBLE, (
            "a demand may not be hidden behind a dominator that is itself omitted"
        )

    # The same invariant over the full mixed corpus: every receipt resolves to
    # something actually on the frontier.
    mixed = compute_attention_frontier(
        mixed_corpus(), snapshot_identity=SNAPSHOT,
        proven_window_collisions=MIXED_COLLISIONS,
    )
    assert mixed.omissions
    for omission in mixed.omissions:
        if omission.relation is ProjectionRelation.DOMINATED_BY:
            assert relation(mixed, omission.covered_by) is (
                ProjectionRelation.ROOT_VISIBLE
            ), omission.demand_id
        else:
            face = next(
                b for b in mixed.bundles if b.bundle_id == omission.covered_by
            )
            assert relation(mixed, face.canonical_demand_id) is (
                ProjectionRelation.ROOT_VISIBLE
            ), omission.demand_id
