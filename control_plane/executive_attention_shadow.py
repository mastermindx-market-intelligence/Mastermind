"""Report-only adaptor: protected Executive Steward truth -> EAF v1 demands.

This is EAF wave A2.  It is the *only* place that knows how the real company's
already-gathered executive facts become
:class:`~control_plane.executive_attention_frontier.AttentionDemand` values.
The engine itself stays pure and source-agnostic.

Three laws shape every line here:

1. **Admission is explicit and source-owned** (F0G §4).  A demand exists only
   because an accepted source owner said so — an Executive Inbox / Wake
   attention obligation, or a structured Agent OS ``needs_ceo`` decision gate.
   Workstream prose (``next_action``, ``Decide ...``, ``urgent`` in a title) is
   carried as display context and never manufactures a demand, an authority, a
   deadline, an impact, a wait or an urgency.

2. **Never fork the Steward** (F0G §17).  Every fact is read through the
   protected query API so its identity and conflict resolution applies.  A
   ``REFUSED`` or ``DEGRADED`` answer becomes typed serviceability trouble, not
   a silent empty.

3. **Report-only.**  No notification, no Wake mutation, no lifecycle
   transition, no target transfer, no placement, no persistence, and no
   suppression of the raw forensic view.

Freshness is owner-relative and always arrives already asserted on the source
fact.  This module contains no clock and invents no TTL.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.executive_attention_frontier import (
    ActionTarget,
    AdmissionSource,
    AttentionClass,
    AttentionDemand,
    AuthorityRequirement,
    AutonomousProgress,
    Blocker,
    Fact,
    FaninKind,
    FaninRoot,
    FrontierResult,
    ProjectionRelation,
    Serviceability,
    ServiceabilityReason,
    TargetState,
    compute_attention_frontier,
)
from control_plane.executive_steward import (
    AttentionFact,
    CapacityState,
    EffectState,
    ExecutiveStewardSnapshot,
    Freshness,
    QueryStatus,
    Seat,
    SourceOwner,
    SourceRef,
)

SCHEMA = "mastermind.executive_attention_shadow.v1"

#: Closed set of top-level projection keys.
OUTPUT_KEYS = frozenset(
    {
        "schema",
        "generated_at",
        "frontier",
        "coverage",
        "admission",
        "degraded",
    }
)

__all__ = [
    "SCHEMA",
    "OUTPUT_KEYS",
    "build_attention_demands",
    "project_attention_shadow",
    "seat_to_authority",
]


def seat_to_authority(seat: Seat | None) -> AuthorityRequirement:
    """Map an accepted source seat to an authority class.

    ``Seat.CEO`` becomes ``SOL`` — CEO consideration is never Chairman
    authority (F0G §3.1 rule 3).  An unknown seat stays ``UNKNOWN`` and never
    defaults upward.
    """
    if seat is Seat.CHAIRMAN:
        return AuthorityRequirement.CHAIRMAN
    if seat is Seat.CEO:
        return AuthorityRequirement.SOL
    if seat in (Seat.COO, Seat.WORKER):
        return AuthorityRequirement.COO_OR_WORKER
    return AuthorityRequirement.UNKNOWN


def _responsibility_source(snapshot: ExecutiveStewardSnapshot, ref: str) -> SourceRef | None:
    result = snapshot.get_responsibility(ref)
    fact = result.data
    if fact is None:
        return None
    return fact.source


def _runtime_facts(
    snapshot: ExecutiveStewardSnapshot, ref: str, seat: Seat
) -> tuple[Any | None, QueryStatus, tuple[str, ...]]:
    """Read runtime evidence through the protected query surface.

    ``get_current_runtime`` refuses on ``EFFECT_UNKNOWN``, root mismatch and
    ambiguity.  Each refusal is preserved as a typed reason rather than being
    flattened into "no runtime".
    """
    result = snapshot.get_current_runtime(ref, seat)
    codes = tuple(issue.code for issue in result.issues)
    return result.data, result.status, codes


def _serviceability_blockers(
    snapshot: ExecutiveStewardSnapshot,
    ref: str,
    seat: Seat,
    runtime: Any | None,
    status: QueryStatus,
    codes: Sequence[str],
) -> tuple[tuple[Blocker, ...], Fact | None, Fact | None, Fact | None]:
    """Derive typed serviceability inputs without inventing a healthy default."""
    blockers: list[Blocker] = []
    effect_fact: Fact | None = None
    capacity_fact: Fact | None = None
    target_fact: Fact | None = None

    runtime_ref = f"executive_steward.get_current_runtime:{ref}:{seat.value}"
    unknown_source = SourceRef(
        owner=SourceOwner.EXECUTIVE_OS,
        ref=runtime_ref,
        observed_at=None,
        freshness=Freshness.UNKNOWN,
    )

    if runtime is not None:
        effect_fact = Fact(runtime.effect_state, runtime.executive_source)
        capacity_fact = Fact(runtime.capacity_state, runtime.executive_source)
        # The Steward carries binding identity as flat strings.  A resolved
        # exact action target requires the binding owner's own evidence; this
        # module never promotes a sister alias or a workstream owner into one.
        if runtime.runtime_binding_id and runtime.session_alias:
            target_fact = Fact(
                ActionTarget(
                    TargetState.RESOLVED,
                    target_ref=f"{runtime.session_alias}#{runtime.runtime_binding_id}",
                ),
                runtime.binding_source,
            )
        else:
            target_fact = Fact(ActionTarget(TargetState.UNKNOWN), runtime.binding_source)
    else:
        if status is QueryStatus.REFUSED:
            if "reconciliation_required" in codes:
                effect_fact = Fact(EffectState.EFFECT_UNKNOWN, unknown_source)
            if any(c.startswith("ambiguous_") for c in codes) or "runtime_root_mismatch" in codes:
                blockers.append(
                    Blocker(
                        reason=ServiceabilityReason.IDENTITY_CONFLICT,
                        source=unknown_source,
                        detail=",".join(sorted(codes)),
                    )
                )
        # No runtime evidence is unknown, never ready.
        target_fact = Fact(ActionTarget(TargetState.UNKNOWN), unknown_source)

    blocker_result = snapshot.explain_blocker(ref)
    blocker_fact = blocker_result.data
    if blocker_fact is not None:
        blockers.append(
            Blocker(
                reason=(
                    ServiceabilityReason.EFFECT_UNKNOWN
                    if blocker_fact.effect_state is EffectState.EFFECT_UNKNOWN
                    else ServiceabilityReason.EXTERNAL_BLOCKER
                ),
                source=blocker_fact.source,
                detail=blocker_fact.code,
            )
        )

    return tuple(blockers), effect_fact, capacity_fact, target_fact


def _autonomy_fact(runtime: Any | None) -> Fact | None:
    """Autonomous progress from accepted runtime state only.

    Unknown autonomy is left absent so the engine reports it as a coverage gap
    rather than reading it as "safe to continue".
    """
    if runtime is None:
        return None
    status = (runtime.status or "").strip().lower()
    if runtime.effect_state is EffectState.EFFECT_UNKNOWN:
        return Fact(AutonomousProgress.NO_SAFE_PROGRESS, runtime.executive_source)
    if runtime.capacity_state is CapacityState.DEGRADED:
        return Fact(AutonomousProgress.NO_SAFE_PROGRESS, runtime.executive_source)
    if status in ("running", "active", "in_progress"):
        return Fact(AutonomousProgress.FULL_SAFE_PROGRESS, runtime.executive_source)
    if status in ("blocked", "failed", "cancelled", "refused"):
        return Fact(AutonomousProgress.NO_SAFE_PROGRESS, runtime.executive_source)
    return None


def build_attention_demands(
    snapshot: ExecutiveStewardSnapshot,
    *,
    declared_blockers: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[tuple[AttentionDemand, ...], dict[str, Any]]:
    """Map protected Steward truth onto explicit EAF demands.

    Returns the demands plus an admission ledger recording exactly how many
    obligations each accepted source contributed and how many were declined,
    so missing coverage stays visible instead of looking like a light load.
    """
    admission: dict[str, Any] = {
        "attention_obligations_seen": 0,
        "attention_obligations_admitted": 0,
        "needs_ceo_gates_admitted": 0,
        "declined": [],
        "steward_issue_codes": [],
    }
    demands: list[AttentionDemand] = []
    seen_ids: set[str] = set()

    # Admission reads the caller-supplied obligation facts themselves; the
    # resolver's verdict is consumed alongside them, never instead of them.
    #
    # ``get_attention()`` correctly REFUSES to guess and drops any obligation
    # whose responsibility does not join exactly, reporting a typed issue.  For
    # the Steward that is right.  For EAF it is fatal: an obligation that the
    # Inbox/Wake owner genuinely raised is real executive demand, and taking
    # only ``.data`` would make a live ``ceo_decision_pending`` disappear from
    # the frontier entirely — the hidden-independent-interrupt failure this
    # whole program exists to prevent.  An unjoinable obligation is therefore
    # admitted and marked BLOCKED with a typed identity reason, never deleted.
    attention_result = snapshot.get_attention()
    admission["steward_issue_codes"] = sorted(
        {issue.code for issue in attention_result.issues}
    )
    resolved_ids = {f.attention_id for f in (attention_result.data or ())}

    by_attention_id: dict[str, list[AttentionFact]] = {}
    for fact in snapshot.attention:
        by_attention_id.setdefault(fact.attention_id, []).append(fact)
    admission["attention_obligations_seen"] = len(by_attention_id)
    admission["attention_obligations_unresolved"] = sorted(
        set(by_attention_id) - resolved_ids
    )

    for attention_id in sorted(by_attention_id):
        candidates = by_attention_id[attention_id]
        fact = candidates[0]
        identity_conflict = len(candidates) > 1
        unjoined = attention_id not in resolved_ids

        seat = fact.target_seat
        # A conflicted obligation identity cannot ground a seat claim, and
        # authority never defaults upward on conflict.
        authority = (
            AuthorityRequirement.UNKNOWN
            if identity_conflict
            else seat_to_authority(seat)
        )
        ref = fact.responsibility_ref
        runtime, status, codes = _runtime_facts(snapshot, ref, seat)
        blockers, effect_fact, capacity_fact, target_fact = _serviceability_blockers(
            snapshot, ref, seat, runtime, status, codes
        )
        # Missing responsibility identity degrades serviceability; it never
        # removes the obligation from the frontier.
        if _responsibility_source(snapshot, ref) is None or unjoined or identity_conflict:
            blockers = blockers + (
                Blocker(
                    reason=ServiceabilityReason.IDENTITY_CONFLICT
                    if identity_conflict
                    else ServiceabilityReason.UNKNOWN_LOAD_BEARING_SOURCE,
                    source=fact.source,
                    detail=(
                        f"attention {attention_id} has {len(candidates)} candidate "
                        "identities"
                        if identity_conflict
                        else f"no exact Agent OS responsibility joins {ref}"
                    ),
                ),
            )

        roots: list[FaninRoot] = []
        if runtime is not None and runtime.root_job_id:
            roots.append(
                FaninRoot(
                    kind=FaninKind.ROOT_JOB,
                    ref=runtime.root_job_id,
                    source=runtime.executive_source,
                )
            )
        declared = (declared_blockers or {}).get(ref)
        if declared:
            blocked_by = declared.get("blocked_by")
            if isinstance(blocked_by, (list, tuple)):
                for token in sorted(str(b) for b in blocked_by if isinstance(b, str)):
                    roots.append(
                        FaninRoot(
                            kind=FaninKind.BLOCKER_ROOT,
                            ref=token,
                            source=SourceRef(
                                owner=SourceOwner.AGENT_OS,
                                ref=f"agent_os_state.workstreams:{ref}.blocked_by",
                                observed_at=None,
                                freshness=Freshness.UNKNOWN,
                            ),
                        )
                    )

        demand_id = f"att:{attention_id}"
        if demand_id in seen_ids:
            continue
        seen_ids.add(demand_id)
        demands.append(
            AttentionDemand(
                demand_id=demand_id,
                admitted_via=(
                    AdmissionSource.WAKE_OBLIGATION
                    if fact.source.owner is SourceOwner.WAKE
                    else AdmissionSource.EXECUTIVE_INBOX_OBLIGATION
                ),
                admission_source=fact.source,
                title=fact.reason,
                responsibility_ref=ref,
                authority=Fact(authority, fact.source, conflict=identity_conflict),
                autonomous_progress=_autonomy_fact(runtime),
                effect_state=effect_fact,
                capacity_state=capacity_fact,
                action_target=target_fact,
                blockers=blockers,
                fanin_roots=tuple(roots),
                context_key=ref,
                display_context=fact.kind,
            )
        )
        admission["attention_obligations_admitted"] += 1

    # Structured Agent OS decision gates.  ``needs_ceo`` admits a question to
    # CEO consideration; it never sets urgency, impact or Chairman authority.
    for ref in sorted(declared_blockers or {}):
        declared = (declared_blockers or {})[ref]
        if declared.get("target_seat") != "ceo":
            continue
        demand_id = f"gate:{ref}"
        if demand_id in seen_ids:
            continue
        responsibility_source = _responsibility_source(snapshot, ref)
        if responsibility_source is None:
            admission["declined"].append(
                {"responsibility_ref": ref, "reason": "needs_ceo gate has no canonical identity"}
            )
            continue
        gate_source = SourceRef(
            owner=SourceOwner.AGENT_OS,
            ref=f"agent_os_state.workstreams:{ref}.needs_ceo",
            observed_at=None,
            freshness=Freshness.UNKNOWN,
        )
        runtime, status, codes = _runtime_facts(snapshot, ref, Seat.CEO)
        blockers, effect_fact, capacity_fact, target_fact = _serviceability_blockers(
            snapshot, ref, Seat.CEO, runtime, status, codes
        )
        roots = []
        blocked_by = declared.get("blocked_by")
        if isinstance(blocked_by, (list, tuple)):
            for token in sorted(str(b) for b in blocked_by if isinstance(b, str)):
                roots.append(
                    FaninRoot(kind=FaninKind.BLOCKER_ROOT, ref=token, source=gate_source)
                )
        seen_ids.add(demand_id)
        demands.append(
            AttentionDemand(
                demand_id=demand_id,
                admitted_via=AdmissionSource.AGENT_OS_DECISION_GATE,
                admission_source=gate_source,
                title=f"CEO consideration gate on {ref}",
                responsibility_ref=ref,
                authority=Fact(AuthorityRequirement.SOL, gate_source),
                autonomous_progress=_autonomy_fact(runtime),
                effect_state=effect_fact,
                capacity_state=capacity_fact,
                action_target=target_fact,
                blockers=blockers,
                fanin_roots=tuple(roots),
                context_key=ref,
            )
        )
        admission["needs_ceo_gates_admitted"] += 1

    return tuple(demands), admission


def _frontier_to_wire(result: FrontierResult) -> dict[str, Any]:
    def item(i: Any) -> dict[str, Any]:
        return {
            "demand_id": i.demand_id,
            "responsibility_ref": i.responsibility_ref,
            "title": i.title,
            "authority_requirement": i.authority_requirement.value,
            "attention_class": i.attention_class.value,
            "pressure_reasons": [r.value for r in i.pressure_reasons],
            "serviceability": i.serviceability.value,
            "serviceability_reasons": [r.value for r in i.serviceability_reasons],
            "exact_action_target": i.exact_action_target,
            "actor_can_act": i.actor_can_act if i.actor_can_act is not None else "unknown",
            "factor_vector": dict(i.factor_vector),
            "became_actionable_at": i.became_actionable_at,
            "downstream_unblocks": list(i.downstream_unblocks),
            "bundle_id": i.bundle_id,
            "projection_relation": i.projection_relation.value,
            "explanation_reasons": list(i.explanation_reasons),
            "issues": [x.value for x in i.issues],
            "is_fairness_sentinel": i.is_fairness_sentinel,
            "source_receipts": [
                {
                    "owner": r.owner.value,
                    "ref": r.ref,
                    "observed_at": r.observed_at,
                    "freshness": r.freshness.value,
                }
                for r in i.source_receipts
            ],
        }

    return {
        "schema": result.schema,
        "snapshot_identity": result.snapshot_identity,
        "authority_frontiers": [
            {
                "authority_requirement": f.authority_requirement.value,
                "interrupt_root_count": f.interrupt_root_count,
                "interrupt_member_count": f.interrupt_member_count,
                "concurrent_demand": f.concurrent_demand.value,
                "service_feasibility": f.service_feasibility.value,
                "feasibility_receipts": list(f.feasibility_receipts),
                "visible_demand_ids": list(f.visible_demand_ids),
            }
            for f in result.authority_frontiers
        ],
        "bundles": [
            {
                "bundle_id": b.bundle_id,
                "canonical_root_ref": b.canonical_root_ref,
                "canonical_demand_id": b.canonical_demand_id,
                "members": list(b.members),
                "interrupt_member_count": b.interrupt_member_count,
                "member_boundaries": [list(m) for m in b.member_boundaries],
            }
            for b in result.bundles
        ],
        "items": [item(i) for i in result.items],
        "fairness_sentinels": list(result.fairness_sentinels),
        "omissions": [
            {
                "demand_id": o.demand_id,
                "relation": o.relation.value,
                "covered_by": o.covered_by,
                "reason": o.reason,
            }
            for o in result.omissions
        ],
        "source_freshness_summary": dict(result.source_freshness_summary),
    }


def project_attention_shadow(
    snapshot: ExecutiveStewardSnapshot,
    *,
    generated_at: str,
    declared_blockers: Mapping[str, Mapping[str, Any]] | None = None,
    source_degraded: Sequence[str] = (),
) -> dict[str, Any]:
    """Report-only Attention Frontier projection over real Steward truth.

    ``source_degraded`` carries the composing caller's own source-availability
    reasons.  It is load-bearing: an empty frontier means *nothing was
    admitted*, which is only good news when the admission sources actually
    answered.  An unanswered source plane must never be rendered as a calm
    empty desk (F0G §11 — unknown is not zero, healthy or harmless).
    """
    degraded: list[str] = []
    demands, admission = build_attention_demands(
        snapshot, declared_blockers=declared_blockers
    )
    result = compute_attention_frontier(demands, snapshot_identity=generated_at)

    # Admission confidence is reported explicitly so a dark source plane can
    # never be mistaken for a light executive load.
    seen = admission["attention_obligations_seen"]
    gates = admission["needs_ceo_gates_admitted"]
    if seen == 0 and gates == 0:
        admission_confidence = "NO_SOURCE"
        degraded.append(
            "attention_frontier: NO attention-obligation source answered — admitted "
            "demand is 0 because the Executive Inbox/Wake plane and the Agent OS "
            "decision-gate plane are dark, NOT because executive load is zero"
        )
    elif seen == 0:
        admission_confidence = "GATES_ONLY"
        degraded.append(
            "attention_frontier: no Executive Inbox/Wake obligation answered; "
            "coverage is Agent OS decision gates only"
        )
    else:
        admission_confidence = "SOURCED"
    for reason in source_degraded:
        degraded.append(f"attention_frontier: upstream source degraded — {reason}")

    declined = len(admission["declined"])
    if declined:
        degraded.append(f"attention_frontier: {declined} obligation(s) declined for missing identity")
    if admission["steward_issue_codes"]:
        degraded.append(
            "attention_frontier: steward reported "
            f"{len(admission['steward_issue_codes'])} issue code(s)"
        )

    visible = [
        i for i in result.items if i.projection_relation is ProjectionRelation.ROOT_VISIBLE
    ]
    coverage = {
        "admission_confidence": admission_confidence,
        "admitted_demands": len(demands),
        "visible_roots": len(visible),
        "omitted_with_receipt": len(result.omissions),
        "interrupts": sum(
            1 for i in result.items if i.attention_class is AttentionClass.INTERRUPT_NOW
        ),
        "valid_waits": sum(
            1 for i in result.items if i.attention_class is AttentionClass.VALID_WAIT
        ),
        "autonomous_continue": sum(
            1
            for i in result.items
            if i.attention_class is AttentionClass.AUTONOMOUS_CONTINUE
        ),
        "blocked": sum(
            1 for i in result.items if i.serviceability is Serviceability.BLOCKED
        ),
        "serviceability_unknown": sum(
            1 for i in result.items if i.serviceability is Serviceability.UNKNOWN
        ),
        "authority_unknown": result.coverage_summary["authority_unknown"],
        "ready_age_unknown": result.coverage_summary["ready_age_unknown"],
        "scan_reduction": {
            "raw_obligations": admission["attention_obligations_seen"],
            "admitted": len(demands),
            "compact_visible": len(visible),
        },
    }

    doc = {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "frontier": _frontier_to_wire(result),
        "coverage": coverage,
        "admission": admission,
        "degraded": degraded,
    }
    if set(doc.keys()) != OUTPUT_KEYS:
        raise RuntimeError("attention shadow document key set is not the closed contract")
    return doc
