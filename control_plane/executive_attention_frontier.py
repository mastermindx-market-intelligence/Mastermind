"""Pure Executive Attention Frontier (EAF) v1 engine.

Controlling contract: ``research/MASTERMIND_EXECUTIVE_ATTENTION_ECONOMICS_F0G_
CONSOLIDATED_V1_CONTRACT_2026-08-30.md`` (protected at Mastermind PR #275,
merge ``c544e8378b447bb69515666e539d6a4da24e4d27``).

This module answers one question over demands that some other owner has
*already* admitted as valid:

    Among all valid demands for scarce Chairman/Sol cognition, which must
    interrupt now, which should be the next focus, which can be decided in a
    related batch, which can continue autonomously, and which are intentional
    waits?

It is **pure**.  It has no gather layer, no persistence, no scheduling, no Wake
mutation, no placement, no lifecycle and no target transfer.  Callers supply
immutable source-attributed facts; the engine returns a deterministic
``mastermind.executive_attention_frontier.v1`` result with explanation receipts.

Four concepts stay orthogonal (F0G §3):

* ``authority_requirement`` — who may decide;
* ``attention_class``       — when scarce cognition matters;
* ``serviceability``        — whether the action path is usable now;
* ``projection_relation``   — how the compact view represents it.

A high-pressure demand may be blocked.  A blocked demand stays urgent.  Urgency
never grants authority.  There is no ``priority_score``, no hidden weighting and
no total order: the frontier is a genuine partial order and incomparable demands
stay incomparable.

Identity/freshness vocabulary is reused from the protected Executive Steward
read core rather than re-declared (Charter P7 — no duplicate control planes).
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
from collections.abc import Iterable, Mapping, Sequence

from control_plane.executive_steward import (  # reuse: never fork
    CapacityState,
    EffectState,
    Freshness,
    Seat,
    SourceOwner,
    SourceRef,
)

RESULT_SCHEMA = "mastermind.executive_attention_frontier.v1"

__all__ = [
    "RESULT_SCHEMA",
    "ActionTarget",
    "AdmissionSource",
    "AttentionClass",
    "AttentionDemand",
    "AuthorityFrontier",
    "AuthorityRequirement",
    "AutonomousProgress",
    "BlastRadius",
    "Blocker",
    "Bundle",
    "BurnState",
    "Comparison",
    "ConcurrentDemand",
    "CostOfDelay",
    "Fact",
    "FaninKind",
    "FaninRoot",
    "FrontierItem",
    "FrontierResult",
    "ImpactState",
    "Issue",
    "OmissionReceipt",
    "PressureReason",
    "ProjectionRelation",
    "Reversibility",
    "ServiceFeasibility",
    "Serviceability",
    "ServiceabilityReason",
    "TargetState",
    "WaitContext",
    "WindowPressure",
    "compute_attention_frontier",
]


class _ValueEnum(str, enum.Enum):
    """String enum whose value is the public wire value."""


# --------------------------------------------------------------------------
# 1. Closed vocabularies (F0G §3)
# --------------------------------------------------------------------------


class AuthorityRequirement(_ValueEnum):
    """Which authority class owns the decision/action.  Never inferred upward."""

    CHAIRMAN = "CHAIRMAN"
    SOL = "SOL"
    COO_OR_WORKER = "COO_OR_WORKER"
    EXECUTIVE_PLACEMENT = "EXECUTIVE_PLACEMENT"
    ADMIN_OR_EXTERNAL = "ADMIN_OR_EXTERNAL"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class AttentionClass(_ValueEnum):
    """When scarce cognition matters, independent of serviceability."""

    INTERRUPT_NOW = "INTERRUPT_NOW"
    FOCUS_NOW = "FOCUS_NOW"
    BATCH_NEXT = "BATCH_NEXT"
    AUTONOMOUS_CONTINUE = "AUTONOMOUS_CONTINUE"
    VALID_WAIT = "VALID_WAIT"
    NON_ACTIONABLE = "NON_ACTIONABLE"


class Serviceability(_ValueEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ServiceabilityReason(_ValueEnum):
    AUTHORITY_SOURCE_CONFLICT = "AUTHORITY_SOURCE_CONFLICT"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    STALE_LOAD_BEARING_SOURCE = "STALE_LOAD_BEARING_SOURCE"
    UNKNOWN_LOAD_BEARING_SOURCE = "UNKNOWN_LOAD_BEARING_SOURCE"
    ACTION_TARGET_UNAVAILABLE = "ACTION_TARGET_UNAVAILABLE"
    ACTION_TARGET_CONFLICT = "ACTION_TARGET_CONFLICT"
    ACTION_TARGET_UNKNOWN = "ACTION_TARGET_UNKNOWN"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"
    CAPACITY_DEGRADED = "CAPACITY_DEGRADED"
    EXTERNAL_BLOCKER = "EXTERNAL_BLOCKER"


class ProjectionRelation(_ValueEnum):
    ROOT_VISIBLE = "ROOT_VISIBLE"
    COVERED_BY_BUNDLE = "COVERED_BY_BUNDLE"
    DOMINATED_BY = "DOMINATED_BY"
    DEFERRED_EQUIVALENT_CONTEXT = "DEFERRED_EQUIVALENT_CONTEXT"
    DEFERRED_ORDINARY_SERVICE = "DEFERRED_ORDINARY_SERVICE"


class Comparison(_ValueEnum):
    DOMINATES = "DOMINATES"
    DOMINATED_BY = "DOMINATED_BY"
    EQUIVALENT = "EQUIVALENT"
    INCOMPARABLE_TRADEOFF = "INCOMPARABLE_TRADEOFF"
    INCOMPARABLE_UNKNOWN = "INCOMPARABLE_UNKNOWN"
    INVALID_FOR_COMPARISON = "INVALID_FOR_COMPARISON"


class ConcurrentDemand(_ValueEnum):
    NONE = "NONE"
    SINGLE = "SINGLE"
    MULTIPLE_INDEPENDENT = "MULTIPLE_INDEPENDENT"
    PROVEN_WINDOW_COLLISION = "PROVEN_WINDOW_COLLISION"
    FEASIBILITY_UNKNOWN = "FEASIBILITY_UNKNOWN"


class ServiceFeasibility(_ValueEnum):
    """Can all independent interrupt roots be serviced in their windows?"""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"
    PROVEN_COLLISION = "PROVEN_COLLISION"


class AdmissionSource(_ValueEnum):
    """Only explicit accepted sources admit a demand (F0G §4)."""

    WAKE_OBLIGATION = "WAKE_OBLIGATION"
    EXECUTIVE_INBOX_OBLIGATION = "EXECUTIVE_INBOX_OBLIGATION"
    TURN_OWNER_FACT = "TURN_OWNER_FACT"
    AGENT_OS_DECISION_GATE = "AGENT_OS_DECISION_GATE"
    ACCEPTED_SOURCE_CONTRACT = "ACCEPTED_SOURCE_CONTRACT"


class WindowPressure(_ValueEnum):
    """Source-owned decision/response window class.

    The *caller* classifies the window from owner-relative source facts.  The
    engine never parses prose, never does clock arithmetic and never invents a
    universal TTL (F0G §5.1, §5.8, §19).
    """

    OPEN = "OPEN"
    NEAR = "NEAR"
    BEFORE_NEXT_FOCUS_BOUNDARY = "BEFORE_NEXT_FOCUS_BOUNDARY"
    EXPIRED = "EXPIRED"


class ImpactState(_ValueEnum):
    """Actual *current* harm — never inferred from blast radius (F0G §5.2)."""

    NO_ACTIVE_HARM = "NO_ACTIVE_HARM"
    ACTIVE_HARM = "ACTIVE_HARM"


class BlastRadius(_ValueEnum):
    ISOLATED = "ISOLATED"
    INTERNAL = "INTERNAL"
    USER_FACING = "USER_FACING"


class Reversibility(_ValueEnum):
    REVERSIBLE = "REVERSIBLE"
    COSTLY_REVERSAL = "COSTLY_REVERSAL"
    IRREVERSIBLE = "IRREVERSIBLE"


class AutonomousProgress(_ValueEnum):
    FULL_SAFE_PROGRESS = "FULL_SAFE_PROGRESS"
    PARTIAL_SAFE_PROGRESS = "PARTIAL_SAFE_PROGRESS"
    NO_SAFE_PROGRESS = "NO_SAFE_PROGRESS"


class BurnState(_ValueEnum):
    NONE = "NONE"
    ACTIVE = "ACTIVE"


class TargetState(_ValueEnum):
    RESOLVED = "RESOLVED"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FaninKind(_ValueEnum):
    """Hard canonical relations only.  Semantics/LLM similarity is not here."""

    DECISION_REF = "DECISION_REF"
    BLOCKER_ROOT = "BLOCKER_ROOT"
    WAKE_CORRELATION = "WAKE_CORRELATION"
    ROOT_JOB = "ROOT_JOB"
    DEPENDENCY_ROOT = "DEPENDENCY_ROOT"
    RELEASE_GATE = "RELEASE_GATE"


class PressureReason(_ValueEnum):
    ACTIVE_HARM = "ACTIVE_HARM"
    IMMINENT_IRREVERSIBLE_LOSS = "IMMINENT_IRREVERSIBLE_LOSS"
    DECISION_WINDOW_EXPIRED = "DECISION_WINDOW_EXPIRED"
    DECISION_WINDOW_BEFORE_NEXT_FOCUS = "DECISION_WINDOW_BEFORE_NEXT_FOCUS"
    DECISION_WINDOW_NEAR = "DECISION_WINDOW_NEAR"
    NO_SAFE_AUTONOMOUS_PROGRESS = "NO_SAFE_AUTONOMOUS_PROGRESS"
    EXACT_DEPENDENCY_UNBLOCK = "EXACT_DEPENDENCY_UNBLOCK"
    ACTIVE_RESOURCE_BURN = "ACTIVE_RESOURCE_BURN"
    SAFE_AUTONOMOUS_PROGRESS = "SAFE_AUTONOMOUS_PROGRESS"
    TYPED_WAIT_ACTIVE = "TYPED_WAIT_ACTIVE"
    TERMINAL_STATE = "TERMINAL_STATE"
    NO_GROUNDED_PRESSURE = "NO_GROUNDED_PRESSURE"
    PRESSURE_EVIDENCE_CONFLICTED = "PRESSURE_EVIDENCE_CONFLICTED"


class Issue(_ValueEnum):
    """Truthful coverage gaps.  Unknown is never zero/healthy/harmless."""

    AUTHORITY_UNKNOWN = "AUTHORITY_UNKNOWN"
    AUTHORITY_CONFLICTED = "AUTHORITY_CONFLICTED"
    READY_AGE_UNKNOWN = "READY_AGE_UNKNOWN"
    WAIT_REVIEW_BOUNDARY_UNKNOWN = "WAIT_REVIEW_BOUNDARY_UNKNOWN"
    AUTONOMY_UNKNOWN = "AUTONOMY_UNKNOWN"
    WINDOW_UNKNOWN = "WINDOW_UNKNOWN"
    IMPACT_UNKNOWN = "IMPACT_UNKNOWN"
    STALE_PRESSURE_SOURCE = "STALE_PRESSURE_SOURCE"
    CONFLICTED_PRESSURE_SOURCE = "CONFLICTED_PRESSURE_SOURCE"
    TARGET_EVIDENCE_UNAVAILABLE = "TARGET_EVIDENCE_UNAVAILABLE"


# --------------------------------------------------------------------------
# 2. Source-attributed facts
# --------------------------------------------------------------------------


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        raise ValueError(f"{name} must be a non-empty token")
    return value


def _require_sentence(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_enum(name: str, value: object, expected: type[enum.Enum]) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{name} must be {expected.__name__}")


@dataclasses.dataclass(frozen=True, slots=True)
class Fact:
    """A load-bearing value plus the exact source that can support it.

    ``conflict`` marks a source-owner-reported disagreement.  A conflicted fact
    may not ground a pressure claim (F0G §6.1) but never silently disappears.
    """

    value: object
    source: SourceRef
    conflict: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.source, SourceRef):
            raise TypeError("Fact.source must be SourceRef")
        if not isinstance(self.conflict, bool):
            raise TypeError("Fact.conflict must be bool")

    @property
    def grounded(self) -> bool:
        """True when this fact may ground an authority-grade claim."""
        return not self.conflict and self.source.freshness is Freshness.CURRENT


@dataclasses.dataclass(frozen=True, slots=True)
class WaitContext:
    """An explicit, authored, typed wait.  Never inferred from uncertainty."""

    kind: str
    review_boundary_reached: bool | None  # None == UNKNOWN
    expected_information_event: bool = False
    detail: str | None = None

    def __post_init__(self) -> None:
        _require_text("wait kind", self.kind)
        if self.review_boundary_reached is not None and not isinstance(
            self.review_boundary_reached, bool
        ):
            raise TypeError("review_boundary_reached must be bool or None")


@dataclasses.dataclass(frozen=True, slots=True)
class ActionTarget:
    """Projection of the exact action-target owner.  EAF never transfers it."""

    state: TargetState
    target_ref: str | None = None

    def __post_init__(self) -> None:
        _require_enum("target state", self.state, TargetState)
        if self.state is TargetState.RESOLVED and not self.target_ref:
            raise ValueError("a RESOLVED action target requires an exact target_ref")
        if self.state is not TargetState.RESOLVED and self.target_ref:
            raise ValueError("only a RESOLVED action target may carry a target_ref")


@dataclasses.dataclass(frozen=True, slots=True)
class CostOfDelay:
    """Carried with receipts; V1 never orders by it (F0G §5.11 — no WSJF)."""

    basis: str
    value: str

    def __post_init__(self) -> None:
        _require_sentence("cost-of-delay basis", self.basis)
        _require_sentence("cost-of-delay value", self.value)


@dataclasses.dataclass(frozen=True, slots=True)
class FaninRoot:
    """An exact canonical relation used for fan-in.  Never semantic."""

    kind: FaninKind
    ref: str
    source: SourceRef

    def __post_init__(self) -> None:
        _require_enum("fan-in kind", self.kind, FaninKind)
        _require_text("fan-in ref", self.ref)
        if not isinstance(self.source, SourceRef):
            raise TypeError("FaninRoot.source must be SourceRef")

    @property
    def key(self) -> str:
        return f"{self.kind.value}:{self.ref}"


@dataclasses.dataclass(frozen=True, slots=True)
class Blocker:
    reason: ServiceabilityReason
    source: SourceRef
    detail: str | None = None

    def __post_init__(self) -> None:
        _require_enum("blocker reason", self.reason, ServiceabilityReason)
        if not isinstance(self.source, SourceRef):
            raise TypeError("Blocker.source must be SourceRef")


# --------------------------------------------------------------------------
# 3. Input demand
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class AttentionDemand:
    """One already-valid demand for executive cognition.

    ``title`` is display context only.  Free text has zero admission, authority,
    urgency or ordering power (F0G §4, §11).
    """

    demand_id: str
    admitted_via: AdmissionSource
    admission_source: SourceRef
    title: str
    responsibility_ref: str | None = None

    authority: Fact | None = None                 # -> AuthorityRequirement
    decision_window: Fact | None = None           # -> WindowPressure
    actual_impact: Fact | None = None             # -> ImpactState
    blast_radius: Fact | None = None              # -> BlastRadius (evidence only)
    reversibility: Fact | None = None             # -> Reversibility
    unblocks: Fact | None = None                  # -> tuple[str, ...] exact refs
    resource_burn: Fact | None = None             # -> BurnState
    autonomous_progress: Fact | None = None       # -> AutonomousProgress
    wait: Fact | None = None                      # -> WaitContext
    became_actionable_at: Fact | None = None      # -> str (source-backed instant)
    cost_of_delay: Fact | None = None             # -> CostOfDelay
    effect_state: Fact | None = None              # -> EffectState
    capacity_state: Fact | None = None            # -> CapacityState
    action_target: Fact | None = None             # -> ActionTarget
    terminal: Fact | None = None                  # -> bool

    blockers: tuple[Blocker, ...] = ()
    fanin_roots: tuple[FaninRoot, ...] = ()
    context_key: str | None = None
    display_context: str | None = None

    def __post_init__(self) -> None:
        _require_text("demand_id", self.demand_id)
        _require_enum("admitted_via", self.admitted_via, AdmissionSource)
        if not isinstance(self.admission_source, SourceRef):
            raise TypeError("admission_source must be SourceRef")
        _require_sentence("title", self.title)
        for name in (
            "authority",
            "decision_window",
            "actual_impact",
            "blast_radius",
            "reversibility",
            "unblocks",
            "resource_burn",
            "autonomous_progress",
            "wait",
            "became_actionable_at",
            "cost_of_delay",
            "effect_state",
            "capacity_state",
            "action_target",
            "terminal",
        ):
            fact = getattr(self, name)
            if fact is not None and not isinstance(fact, Fact):
                raise TypeError(f"{name} must be a Fact or None")
        if not isinstance(self.blockers, tuple):
            raise TypeError("blockers must be a tuple")
        if not isinstance(self.fanin_roots, tuple):
            raise TypeError("fanin_roots must be a tuple")


# --------------------------------------------------------------------------
# 4. Output
# --------------------------------------------------------------------------

_UNKNOWN_RANK = None


@dataclasses.dataclass(frozen=True, slots=True)
class OmissionReceipt:
    """Every omitted ordinary demand needs an exact receipt (F0G §3.4)."""

    demand_id: str
    relation: ProjectionRelation
    covered_by: str | None
    reason: str


@dataclasses.dataclass(frozen=True, slots=True)
class Bundle:
    bundle_id: str
    canonical_root_ref: str
    canonical_demand_id: str
    members: tuple[str, ...]
    interrupt_member_count: int
    member_boundaries: tuple[tuple[str, str, str], ...]  # (id, authority, serviceability)


@dataclasses.dataclass(frozen=True, slots=True)
class FrontierItem:
    demand_id: str
    responsibility_ref: str | None
    title: str
    authority_requirement: AuthorityRequirement
    authority_source: SourceRef | None
    attention_class: AttentionClass
    pressure_reasons: tuple[PressureReason, ...]
    serviceability: Serviceability
    serviceability_reasons: tuple[ServiceabilityReason, ...]
    exact_action_target: str | None
    actor_can_act: bool | None
    factor_vector: Mapping[str, object]
    became_actionable_at: str | None
    wait_context: WaitContext | None
    downstream_unblocks: tuple[str, ...]
    active_resource_burn: str | None
    cost_of_delay: CostOfDelay | None
    bundle_id: str | None
    projection_relation: ProjectionRelation
    explanation_reasons: tuple[str, ...]
    source_receipts: tuple[SourceRef, ...]
    issues: tuple[Issue, ...]
    is_fairness_sentinel: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class AuthorityFrontier:
    authority_requirement: AuthorityRequirement
    interrupt_root_count: int
    interrupt_member_count: int
    concurrent_demand: ConcurrentDemand
    service_feasibility: ServiceFeasibility
    feasibility_receipts: tuple[str, ...]
    visible_demand_ids: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class FrontierResult:
    schema: str
    snapshot_identity: str
    authority_frontiers: tuple[AuthorityFrontier, ...]
    bundles: tuple[Bundle, ...]
    items: tuple[FrontierItem, ...]
    fairness_sentinels: tuple[str, ...]
    omissions: tuple[OmissionReceipt, ...]
    comparisons: tuple[tuple[str, str, Comparison], ...]
    coverage_summary: Mapping[str, object]
    source_freshness_summary: Mapping[str, int]

    def visible(self) -> tuple[FrontierItem, ...]:
        return tuple(
            i for i in self.items
            if i.projection_relation is ProjectionRelation.ROOT_VISIBLE
        )


# --------------------------------------------------------------------------
# 5. Authority resolution (F0G §3.1) — resolved before any ordering
# --------------------------------------------------------------------------


def _resolve_authority(
    demand: AttentionDemand,
) -> tuple[AuthorityRequirement, SourceRef | None, list[Issue]]:
    """Authority never defaults upward and is never raised by pressure.

    Free text, urgency, economic consequence, age, fan-out and congestion have
    zero authority power.  A conflicted or absent source yields ``UNKNOWN``.
    """
    fact = demand.authority
    if fact is None:
        return AuthorityRequirement.UNKNOWN, None, [Issue.AUTHORITY_UNKNOWN]
    if not isinstance(fact.value, AuthorityRequirement):
        raise TypeError("authority Fact.value must be AuthorityRequirement")
    if fact.conflict:
        # Never default upward on conflict.
        return AuthorityRequirement.UNKNOWN, fact.source, [Issue.AUTHORITY_CONFLICTED]
    issues: list[Issue] = []
    if fact.source.freshness is not Freshness.CURRENT:
        issues.append(Issue.AUTHORITY_UNKNOWN)
    return fact.value, fact.source, issues


# --------------------------------------------------------------------------
# 6. Pressure vector (F0G §5) — only facts an accepted owner can support
# --------------------------------------------------------------------------


def _grounded(fact: Fact | None, expected: type) -> tuple[object | None, Issue | None]:
    """Return a value only when its own source can ground an authority claim."""
    if fact is None:
        return None, None
    if not isinstance(fact.value, expected):
        raise TypeError(f"expected {expected.__name__} fact value")
    if fact.conflict:
        return None, Issue.CONFLICTED_PRESSURE_SOURCE
    if fact.source.freshness is Freshness.STALE:
        return None, Issue.STALE_PRESSURE_SOURCE
    if fact.source.freshness is Freshness.UNKNOWN:
        return None, Issue.STALE_PRESSURE_SOURCE
    return fact.value, None


def _wait_is_valid(wait: WaitContext | None, reversibility: object | None) -> bool:
    """An explicit typed wait is valid only while its review boundary holds.

    Uncertainty alone never creates a wait (F0G §5.7) and an unknown review
    boundary may not be read as "still waiting" — invented waits must be zero.
    """
    if wait is None:
        return False
    if wait.review_boundary_reached is not False:
        return False  # True == due for review; None == unknown, never invented
    if reversibility is Reversibility.IRREVERSIBLE:
        return False
    return True


def _derive_pressure(
    demand: AttentionDemand,
) -> tuple[AttentionClass, tuple[PressureReason, ...], dict[str, object], list[Issue]]:
    """Classify *when* cognition matters.  Serviceability is not an input here."""
    issues: list[Issue] = []
    reasons: list[PressureReason] = []

    def take(fact: Fact | None, expected: type, unknown: Issue | None):
        value, issue = _grounded(fact, expected)
        if issue is not None:
            issues.append(issue)
        if value is None and unknown is not None:
            issues.append(unknown)
        return value

    terminal = take(demand.terminal, bool, None)
    window = take(demand.decision_window, WindowPressure, Issue.WINDOW_UNKNOWN)
    impact = take(demand.actual_impact, ImpactState, Issue.IMPACT_UNKNOWN)
    reversibility = take(demand.reversibility, Reversibility, None)
    autonomy = take(demand.autonomous_progress, AutonomousProgress, Issue.AUTONOMY_UNKNOWN)
    burn = take(demand.resource_burn, BurnState, None)
    wait = take(demand.wait, WaitContext, None)
    unblocks_raw = take(demand.unblocks, tuple, None)
    unblocks: tuple[str, ...] = tuple(unblocks_raw) if unblocks_raw else ()

    if demand.wait is not None and isinstance(demand.wait.value, WaitContext):
        if demand.wait.value.review_boundary_reached is None:
            issues.append(Issue.WAIT_REVIEW_BOUNDARY_UNKNOWN)

    factor_vector: dict[str, object] = {
        "decision_window": window.value if window else "UNKNOWN",
        "actual_impact": impact.value if impact else "UNKNOWN",
        "blast_radius": (
            demand.blast_radius.value.value
            if demand.blast_radius is not None
            and isinstance(demand.blast_radius.value, BlastRadius)
            else "UNKNOWN"
        ),
        "reversibility": reversibility.value if reversibility else "UNKNOWN",
        "autonomous_progress": autonomy.value if autonomy else "UNKNOWN",
        "active_resource_burn": burn.value if burn else "UNKNOWN",
        "exact_unblock_count": len(unblocks),
    }

    # -- terminal --------------------------------------------------------
    if terminal is True:
        return (
            AttentionClass.NON_ACTIONABLE,
            (PressureReason.TERMINAL_STATE,),
            factor_vector,
            issues,
        )

    # -- interrupt: evaluated BEFORE waits so no wait can hide an emergency
    interrupt = False
    if impact is ImpactState.ACTIVE_HARM:
        reasons.append(PressureReason.ACTIVE_HARM)
        interrupt = True
    if window is WindowPressure.EXPIRED:
        reasons.append(PressureReason.DECISION_WINDOW_EXPIRED)
        interrupt = True
    if window is WindowPressure.BEFORE_NEXT_FOCUS_BOUNDARY:
        reasons.append(PressureReason.DECISION_WINDOW_BEFORE_NEXT_FOCUS)
        interrupt = True
    if reversibility is Reversibility.IRREVERSIBLE and window is WindowPressure.NEAR:
        reasons.append(PressureReason.IMMINENT_IRREVERSIBLE_LOSS)
        interrupt = True
    if interrupt:
        return AttentionClass.INTERRUPT_NOW, tuple(reasons), factor_vector, issues

    # -- intentional wait -------------------------------------------------
    if _wait_is_valid(wait, reversibility):
        return (
            AttentionClass.VALID_WAIT,
            (PressureReason.TYPED_WAIT_ACTIVE,),
            factor_vector,
            issues,
        )

    # -- safe autonomous continuation -------------------------------------
    if (
        autonomy is AutonomousProgress.FULL_SAFE_PROGRESS
        and window in (WindowPressure.OPEN, None)
    ):
        return (
            AttentionClass.AUTONOMOUS_CONTINUE,
            (PressureReason.SAFE_AUTONOMOUS_PROGRESS,),
            factor_vector,
            issues,
        )

    # -- next focus -------------------------------------------------------
    focus = False
    if window is WindowPressure.NEAR:
        reasons.append(PressureReason.DECISION_WINDOW_NEAR)
        focus = True
    if autonomy is AutonomousProgress.NO_SAFE_PROGRESS:
        reasons.append(PressureReason.NO_SAFE_AUTONOMOUS_PROGRESS)
        focus = True
    if unblocks:
        reasons.append(PressureReason.EXACT_DEPENDENCY_UNBLOCK)
        focus = True
    if burn is BurnState.ACTIVE:
        reasons.append(PressureReason.ACTIVE_RESOURCE_BURN)
        focus = True
    if focus:
        return AttentionClass.FOCUS_NOW, tuple(reasons), factor_vector, issues

    if autonomy is AutonomousProgress.PARTIAL_SAFE_PROGRESS:
        return (
            AttentionClass.AUTONOMOUS_CONTINUE,
            (PressureReason.SAFE_AUTONOMOUS_PROGRESS,),
            factor_vector,
            issues,
        )

    # Unknown autonomy is never read as "safe to continue".
    return (
        AttentionClass.BATCH_NEXT,
        (PressureReason.NO_GROUNDED_PRESSURE,),
        factor_vector,
        issues,
    )


# --------------------------------------------------------------------------
# 7. Serviceability (F0G §3.3, §6) — derived independently of pressure
# --------------------------------------------------------------------------


def _derive_serviceability(
    demand: AttentionDemand,
    attention_class: AttentionClass,
    authority: AuthorityRequirement,
    authority_issues: Sequence[Issue],
) -> tuple[Serviceability, tuple[ServiceabilityReason, ...], str | None, list[Issue]]:
    """Whether the action path is usable now.  Never changes urgency."""
    issues: list[Issue] = []
    reasons: list[ServiceabilityReason] = []

    if attention_class is AttentionClass.NON_ACTIONABLE:
        return Serviceability.NOT_APPLICABLE, (), None, issues

    blocked = False
    unknown = False

    for blocker in sorted(demand.blockers, key=lambda b: (b.reason.value, b.source.ref)):
        reasons.append(blocker.reason)
        blocked = True

    if Issue.AUTHORITY_CONFLICTED in authority_issues:
        reasons.append(ServiceabilityReason.AUTHORITY_SOURCE_CONFLICT)
        blocked = True
    elif authority is AuthorityRequirement.UNKNOWN:
        reasons.append(ServiceabilityReason.UNKNOWN_LOAD_BEARING_SOURCE)
        unknown = True

    # Serviceability facts are load-bearing too: a stale or conflicted source
    # may not prove the action path is usable.  Without this the engine would
    # demote urgency for stale evidence while still declaring the actor able to
    # act on it — and would hand out a stale RuntimeBinding as the exact
    # current target (F0G §5.8, §6.2).
    def _service_fact(fact: Fact | None) -> tuple[object | None, bool]:
        """Return (value, degraded) where degraded marks unusable evidence."""
        if fact is None:
            return None, False
        if fact.conflict:
            return None, True
        if fact.source.freshness is not Freshness.CURRENT:
            return None, True
        return fact.value, False

    effect_value, effect_degraded = _service_fact(demand.effect_state)
    if effect_degraded:
        reasons.append(ServiceabilityReason.STALE_LOAD_BEARING_SOURCE)
        issues.append(Issue.STALE_PRESSURE_SOURCE)
        unknown = True
    if effect_value is EffectState.EFFECT_UNKNOWN:
        # Blocks action/retry/failover; never erases time pressure.
        reasons.append(ServiceabilityReason.EFFECT_UNKNOWN)
        blocked = True

    capacity_value, capacity_degraded = _service_fact(demand.capacity_state)
    if capacity_degraded:
        reasons.append(ServiceabilityReason.STALE_LOAD_BEARING_SOURCE)
        unknown = True
    if capacity_value is CapacityState.DEGRADED:
        reasons.append(ServiceabilityReason.CAPACITY_DEGRADED)
        blocked = True
    elif capacity_value is CapacityState.UNKNOWN:
        reasons.append(ServiceabilityReason.UNKNOWN_LOAD_BEARING_SOURCE)
        unknown = True

    target_ref: str | None = None
    if demand.action_target is None:
        # Not declaring a target must never score better than declaring it
        # unknown.  A caller that knows no target is needed says so explicitly
        # with TargetState.NOT_APPLICABLE.
        reasons.append(ServiceabilityReason.ACTION_TARGET_UNKNOWN)
        issues.append(Issue.TARGET_EVIDENCE_UNAVAILABLE)
        unknown = True
    else:
        target = demand.action_target.value
        if not isinstance(target, ActionTarget):
            raise TypeError("action_target Fact.value must be ActionTarget")
        target_value, target_degraded = _service_fact(demand.action_target)
        if target_degraded:
            # A stale binding ref is not the current action target.
            reasons.append(ServiceabilityReason.STALE_LOAD_BEARING_SOURCE)
            issues.append(Issue.TARGET_EVIDENCE_UNAVAILABLE)
            if target.state is TargetState.RESOLVED:
                reasons.append(ServiceabilityReason.ACTION_TARGET_UNKNOWN)
            unknown = True
        elif target.state is TargetState.RESOLVED:
            target_ref = target.target_ref
        if target.state is TargetState.UNAVAILABLE:
            reasons.append(ServiceabilityReason.ACTION_TARGET_UNAVAILABLE)
            blocked = True
        elif target.state is TargetState.CONFLICT:
            reasons.append(ServiceabilityReason.ACTION_TARGET_CONFLICT)
            blocked = True
        elif target.state is TargetState.UNKNOWN:
            reasons.append(ServiceabilityReason.ACTION_TARGET_UNKNOWN)
            issues.append(Issue.TARGET_EVIDENCE_UNAVAILABLE)
            unknown = True

    if blocked:
        state = Serviceability.BLOCKED
    elif unknown:
        state = Serviceability.UNKNOWN
    else:
        state = Serviceability.READY

    ordered = tuple(sorted(set(reasons), key=lambda r: r.value))
    return state, ordered, target_ref, issues


def _actor_can_act(state: Serviceability) -> bool | None:
    if state is Serviceability.READY:
        return True
    if state is Serviceability.BLOCKED:
        return False
    if state is Serviceability.NOT_APPLICABLE:
        return False
    return None  # UNKNOWN stays unknown; never coerced to a boolean


# --------------------------------------------------------------------------
# 8. Exact-root fan-in (F0G §7) — never semantic
# --------------------------------------------------------------------------


def _instant(value: object) -> datetime.datetime | None:
    """Parse a source-backed instant for ordering only.

    This reads no clock and invents no TTL (F0G §19) — it normalises two legal
    spellings of the same moment so fairness ordering compares moments rather
    than strings.  ``2026-09-01T00:00:00+09:00`` is genuinely earlier than
    ``2026-08-31T20:00:00Z``; a lexicographic compare gets that backwards.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _bundle_id(root_key: str, member_ids: Sequence[str]) -> str:
    """Deterministic from canonical root + ordered members.  No mutable ledger."""
    payload = root_key + "|" + "|".join(sorted(member_ids))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"bundle-{digest}"


# --------------------------------------------------------------------------
# 9. Genuine partial order (F0G §8) — no hidden totalization
# --------------------------------------------------------------------------

_WINDOW_RANK = {
    WindowPressure.OPEN: 0,
    WindowPressure.NEAR: 1,
    WindowPressure.BEFORE_NEXT_FOCUS_BOUNDARY: 2,
    WindowPressure.EXPIRED: 3,
}
_IMPACT_RANK = {ImpactState.NO_ACTIVE_HARM: 0, ImpactState.ACTIVE_HARM: 1}
_AUTONOMY_RANK = {
    AutonomousProgress.FULL_SAFE_PROGRESS: 0,
    AutonomousProgress.PARTIAL_SAFE_PROGRESS: 1,
    AutonomousProgress.NO_SAFE_PROGRESS: 2,
}
_BURN_RANK = {BurnState.NONE: 0, BurnState.ACTIVE: 1}

#: Load-bearing comparison dimensions.  Reversibility and blast radius are
#: deliberately absent: they are evidence/optionality, not pressure ordering
#: (F0G §5.2, §5.3).  Cost of delay is absent: V1 has no universal WSJF
#: (F0G §5.11).  Age is absent: it is fairness service, not dominance (§8).
_DIMENSIONS = ("window", "impact", "autonomy", "unblock", "burn")


def _dimension_ranks(demand: AttentionDemand) -> dict[str, int | None]:
    """Rank each load-bearing dimension, or ``None`` when truly unknown."""
    window, _ = _grounded(demand.decision_window, WindowPressure)
    impact, _ = _grounded(demand.actual_impact, ImpactState)
    autonomy, _ = _grounded(demand.autonomous_progress, AutonomousProgress)
    burn, _ = _grounded(demand.resource_burn, BurnState)
    unblocks_raw, _ = _grounded(demand.unblocks, tuple)
    return {
        "window": _WINDOW_RANK[window] if window is not None else _UNKNOWN_RANK,
        "impact": _IMPACT_RANK[impact] if impact is not None else _UNKNOWN_RANK,
        "autonomy": _AUTONOMY_RANK[autonomy] if autonomy is not None else _UNKNOWN_RANK,
        "burn": _BURN_RANK[burn] if burn is not None else _UNKNOWN_RANK,
        "unblock": len(unblocks_raw) if unblocks_raw is not None else _UNKNOWN_RANK,
    }


def _compare(
    left: AttentionDemand,
    right: AttentionDemand,
    left_authority_conflicted: bool,
    right_authority_conflicted: bool,
) -> Comparison:
    """A genuine partial order.  Incomparable demands stay incomparable."""
    if left_authority_conflicted or right_authority_conflicted:
        return Comparison.INVALID_FOR_COMPARISON

    lhs = _dimension_ranks(left)
    rhs = _dimension_ranks(right)

    better = False
    worse = False
    for dim in _DIMENSIONS:
        a, b = lhs[dim], rhs[dim]
        if a is _UNKNOWN_RANK or b is _UNKNOWN_RANK:
            # An unknown dimension can never support a "no worse on every
            # dimension" claim.  Unknown is not zero.
            return Comparison.INCOMPARABLE_UNKNOWN
        if a > b:
            better = True
        elif a < b:
            worse = True

    if better and worse:
        return Comparison.INCOMPARABLE_TRADEOFF
    if better:
        return Comparison.DOMINATES
    if worse:
        return Comparison.DOMINATED_BY
    return Comparison.EQUIVALENT


#: Classes whose members may be omitted by dominance.  INTERRUPT_NOW is absent
#: on purpose: every independent interrupt root stays visible (F0G §3.2, §10).
_DOMINANCE_ELIGIBLE = (AttentionClass.FOCUS_NOW, AttentionClass.BATCH_NEXT)


# --------------------------------------------------------------------------
# 10. Engine
# --------------------------------------------------------------------------


def _freshness_summary(demands: Sequence[AttentionDemand]) -> dict[str, int]:
    counts = {f.value: 0 for f in Freshness}
    for demand in demands:
        seen: list[SourceRef] = [demand.admission_source]
        for name in (
            "authority", "decision_window", "actual_impact", "blast_radius",
            "reversibility", "unblocks", "resource_burn", "autonomous_progress",
            "wait", "became_actionable_at", "cost_of_delay", "effect_state",
            "capacity_state", "action_target", "terminal",
        ):
            fact = getattr(demand, name)
            if fact is not None:
                seen.append(fact.source)
        for ref in seen:
            counts[ref.freshness.value] += 1
    return counts


def compute_attention_frontier(
    demands: Iterable[AttentionDemand],
    *,
    snapshot_identity: str,
    proven_window_collisions: Mapping[str, Sequence[str]] | None = None,
) -> FrontierResult:
    """Derive the deterministic attention frontier from admitted demands.

    Pure: no I/O, no clock, no persistence, no mutation of any input.  The
    result is a function of the demand set alone, and is invariant under input
    permutation.

    ``proven_window_collisions`` maps an authority wire value to the exact
    source refs proving that its independent interrupt roots cannot all be
    serviced in their windows.  Absent evidence yields ``UNKNOWN`` feasibility,
    never an inferred collision (F0G §10).
    """
    _require_text("snapshot_identity", snapshot_identity)
    collisions: dict[str, tuple[str, ...]] = {}
    for key, refs in (proven_window_collisions or {}).items():
        # A mis-keyed authority must not silently discard real collision
        # evidence, and an empty ref is not proof of anything (F0G §10).
        try:
            AuthorityRequirement(key)
        except ValueError:
            raise ValueError(
                f"proven_window_collisions key {key!r} is not an AuthorityRequirement"
            ) from None
        cleaned = tuple(r for r in refs if isinstance(r, str) and r.strip())
        if not cleaned:
            raise ValueError(
                f"proven_window_collisions[{key!r}] must carry at least one source ref"
            )
        collisions[key] = cleaned

    ordered = sorted(demands, key=lambda d: d.demand_id)
    if len({d.demand_id for d in ordered}) != len(ordered):
        raise ValueError("demand_id must be unique within a snapshot")

    by_id = {d.demand_id: d for d in ordered}

    # -- per-demand derivation -------------------------------------------
    authority_of: dict[str, AuthorityRequirement] = {}
    authority_src: dict[str, SourceRef | None] = {}
    authority_conflicted: dict[str, bool] = {}
    class_of: dict[str, AttentionClass] = {}
    pressure_of: dict[str, tuple[PressureReason, ...]] = {}
    factors_of: dict[str, dict[str, object]] = {}
    service_of: dict[str, Serviceability] = {}
    service_reasons_of: dict[str, tuple[ServiceabilityReason, ...]] = {}
    target_of: dict[str, str | None] = {}
    issues_of: dict[str, list[Issue]] = {}

    for demand in ordered:
        did = demand.demand_id
        authority, src, auth_issues = _resolve_authority(demand)
        attention_class, reasons, factors, pressure_issues = _derive_pressure(demand)
        service, service_reasons, target_ref, service_issues = _derive_serviceability(
            demand, attention_class, authority, auth_issues
        )
        authority_of[did] = authority
        authority_src[did] = src
        authority_conflicted[did] = Issue.AUTHORITY_CONFLICTED in auth_issues
        class_of[did] = attention_class
        pressure_of[did] = reasons
        factors_of[did] = factors
        service_of[did] = service
        service_reasons_of[did] = service_reasons
        target_of[did] = target_ref
        merged = list(auth_issues) + list(pressure_issues) + list(service_issues)
        age_fact = demand.became_actionable_at
        if age_fact is None:
            merged.append(Issue.READY_AGE_UNKNOWN)
        elif not age_fact.grounded or _instant(age_fact.value) is None:
            # A stale, conflicted or unparseable ready time is not an age.
            merged.append(Issue.READY_AGE_UNKNOWN)
            if not age_fact.grounded:
                merged.append(Issue.STALE_PRESSURE_SOURCE)
        issues_of[did] = sorted(set(merged), key=lambda i: i.value)

    # -- exact-root fan-in (F0G §7) ---------------------------------------
    # Fan-in is partitioned by AUTHORITY as well as exact root.  Sharing a root
    # cause is context, and context grouping never grants shared permission
    # (F0G §7).  Without the authority key a Chairman emergency could be folded
    # behind a Sol-authority bundle face and render nowhere in its own
    # partition, contradicting §10's guarantee that every independent
    # INTERRUPT_NOW root stays visible.
    root_members: dict[tuple[str, str], list[str]] = {}
    for demand in ordered:
        did = demand.demand_id
        for root in demand.fanin_roots:
            root_members.setdefault(
                (authority_of[did].value, root.key), []
            ).append(did)

    bundles: list[Bundle] = []
    bundle_of: dict[str, str] = {}
    canonical_of_bundle: dict[str, str] = {}
    for key in sorted(root_members):
        authority_value, root_key = key
        # Drop only members already claimed by an earlier exact root, rather
        # than abandoning the whole bundle, so overlapping roots still fan in.
        members = sorted(
            {m for m in root_members[key] if m not in bundle_of}
        )
        if len(members) < 2:
            continue
        bid = _bundle_id(f"{authority_value}|{root_key}", members)
        interrupts = [m for m in members if class_of[m] is AttentionClass.INTERRUPT_NOW]
        # An interrupt member is always the visible face of its bundle so
        # exact-root compaction can never hide an emergency.
        canonical = interrupts[0] if interrupts else members[0]
        for m in members:
            bundle_of[m] = bid
        canonical_of_bundle[bid] = canonical
        bundles.append(
            Bundle(
                bundle_id=bid,
                canonical_root_ref=root_key,
                canonical_demand_id=canonical,
                members=tuple(members),
                interrupt_member_count=len(interrupts),
                member_boundaries=tuple(
                    (m, authority_of[m].value, service_of[m].value) for m in members
                ),
            )
        )

    # -- partial order within (authority, actionable class) ---------------
    comparisons: list[tuple[str, str, Comparison]] = []
    dominated_by: dict[str, str] = {}
    partitions: dict[tuple[str, str], list[str]] = {}
    for demand in ordered:
        did = demand.demand_id
        partitions.setdefault(
            (authority_of[did].value, class_of[did].value), []
        ).append(did)

    # A demand may only be hidden by dominance when it is genuinely
    # non-maximal.  Collecting ALL dominators and omitting exactly the
    # non-maximal elements makes the result transitive and independent of
    # demand-id spelling by construction; the earlier single-dominator record
    # plus a repair pass let lexicographic id order decide visibility, and
    # could promote a strictly weaker demand over a stronger one.
    def _can_dominate(did: str) -> bool:
        """Visible enough to stand in for something it dominates."""
        if class_of[did] not in _DOMINANCE_ELIGIBLE:
            return False
        bid = bundle_of.get(did)
        return bid is None or canonical_of_bundle[bid] == did

    def _can_be_omitted(did: str) -> bool:
        """A bundle's own face is never dominance-omitted (it represents members)."""
        if class_of[did] not in _DOMINANCE_ELIGIBLE:
            return False
        return bundle_of.get(did) is None

    dominators: dict[str, list[str]] = {}
    for key in sorted(partitions):
        _, class_value = key
        members = sorted(partitions[key])
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                relation = _compare(
                    by_id[a], by_id[b], authority_conflicted[a], authority_conflicted[b]
                )
                comparisons.append((a, b, relation))
                if relation is Comparison.DOMINATES:
                    stronger, weaker = a, b
                elif relation is Comparison.DOMINATED_BY:
                    stronger, weaker = b, a
                else:
                    continue
                if _can_dominate(stronger) and _can_be_omitted(weaker):
                    dominators.setdefault(weaker, []).append(stronger)

    # Point each receipt at a MAXIMAL dominator — one nothing else dominates —
    # so a receipt can never resolve to something that is itself omitted.
    for weaker in sorted(dominators):
        maximal = sorted(
            d for d in dominators[weaker] if d not in dominators
        )
        if maximal:
            dominated_by[weaker] = maximal[0]

    # -- projection relations + omission receipts -------------------------
    relation_of: dict[str, ProjectionRelation] = {}
    covered_by: dict[str, str | None] = {}
    omissions: list[OmissionReceipt] = []
    for demand in ordered:
        did = demand.demand_id
        bid = bundle_of.get(did)
        if bid is not None and canonical_of_bundle[bid] != did:
            relation_of[did] = ProjectionRelation.COVERED_BY_BUNDLE
            covered_by[did] = bid
            omissions.append(
                OmissionReceipt(
                    demand_id=did,
                    relation=ProjectionRelation.COVERED_BY_BUNDLE,
                    covered_by=bid,
                    reason=(
                        "exact canonical root "
                        f"{next(b.canonical_root_ref for b in bundles if b.bundle_id == bid)}"
                    ),
                )
            )
        elif did in dominated_by:
            relation_of[did] = ProjectionRelation.DOMINATED_BY
            covered_by[did] = dominated_by[did]
            omissions.append(
                OmissionReceipt(
                    demand_id=did,
                    relation=ProjectionRelation.DOMINATED_BY,
                    covered_by=dominated_by[did],
                    reason=(
                        "no better on any load-bearing dimension and strictly "
                        f"weaker than {dominated_by[did]} in the same authority "
                        "and pressure class"
                    ),
                )
            )
        else:
            relation_of[did] = ProjectionRelation.ROOT_VISIBLE
            covered_by[did] = None

    # -- anti-starvation sentinels (F0G §9) -------------------------------
    sentinels: list[str] = []
    by_authority: dict[str, list[str]] = {}
    for demand in ordered:
        by_authority.setdefault(authority_of[demand.demand_id].value, []).append(
            demand.demand_id
        )
    for authority_value in sorted(by_authority):
        eligible = [
            did
            for did in by_authority[authority_value]
            if class_of[did] in _DOMINANCE_ELIGIBLE
        ]
        if not eligible:
            continue
        if any(relation_of[did] is ProjectionRelation.ROOT_VISIBLE for did in eligible):
            continue
        aged = [
            did
            for did in eligible
            if by_id[did].became_actionable_at is not None
            and by_id[did].became_actionable_at.grounded
            and _instant(by_id[did].became_actionable_at.value) is not None
        ]
        if not aged:
            continue  # unknown ready time is a coverage gap, never age zero
        oldest = min(
            aged,
            key=lambda d: (_instant(by_id[d].became_actionable_at.value), d),
        )
        relation_of[oldest] = ProjectionRelation.ROOT_VISIBLE
        covered_by[oldest] = None
        omissions[:] = [o for o in omissions if o.demand_id != oldest]
        sentinels.append(oldest)

    # -- per-authority concurrency truth (F0G §10) ------------------------
    frontiers: list[AuthorityFrontier] = []
    for authority_value in sorted(by_authority):
        members = sorted(by_authority[authority_value])
        interrupts = [m for m in members if class_of[m] is AttentionClass.INTERRUPT_NOW]
        roots = sorted({bundle_of.get(m, m) for m in interrupts})
        proof = tuple(collisions.get(authority_value, ()))
        if not interrupts:
            concurrent = ConcurrentDemand.NONE
            feasibility = ServiceFeasibility.NOT_APPLICABLE
            receipts: tuple[str, ...] = ()
        elif len(roots) == 1:
            concurrent = ConcurrentDemand.SINGLE
            feasibility = ServiceFeasibility.NOT_APPLICABLE
            receipts = ()
        elif proof:
            concurrent = ConcurrentDemand.PROVEN_WINDOW_COLLISION
            feasibility = ServiceFeasibility.PROVEN_COLLISION
            receipts = proof
        else:
            concurrent = ConcurrentDemand.MULTIPLE_INDEPENDENT
            feasibility = ServiceFeasibility.UNKNOWN
            receipts = (
                "no source-backed executive service-capacity evidence; "
                "feasibility is unknown, not feasible",
            )
        frontiers.append(
            AuthorityFrontier(
                authority_requirement=AuthorityRequirement(authority_value),
                interrupt_root_count=len(roots),
                interrupt_member_count=len(interrupts),
                concurrent_demand=concurrent,
                service_feasibility=feasibility,
                feasibility_receipts=receipts,
                visible_demand_ids=tuple(
                    m
                    for m in members
                    if relation_of[m] is ProjectionRelation.ROOT_VISIBLE
                ),
            )
        )

    # -- emit --------------------------------------------------------------
    items: list[FrontierItem] = []
    for demand in ordered:
        did = demand.demand_id
        receipts = [demand.admission_source]
        for name in (
            "authority", "decision_window", "actual_impact", "reversibility",
            "unblocks", "resource_burn", "autonomous_progress", "wait",
            "became_actionable_at", "effect_state", "capacity_state",
            "action_target", "terminal",
        ):
            fact = getattr(demand, name)
            if fact is not None:
                receipts.append(fact.source)
        unblocks_value, _ = _grounded(demand.unblocks, tuple)
        burn_value, _ = _grounded(demand.resource_burn, BurnState)
        wait_value = (
            demand.wait.value
            if demand.wait is not None and isinstance(demand.wait.value, WaitContext)
            else None
        )
        items.append(
            FrontierItem(
                demand_id=did,
                responsibility_ref=demand.responsibility_ref,
                title=demand.title,
                authority_requirement=authority_of[did],
                authority_source=authority_src[did],
                attention_class=class_of[did],
                pressure_reasons=pressure_of[did],
                serviceability=service_of[did],
                serviceability_reasons=service_reasons_of[did],
                exact_action_target=target_of[did],
                actor_can_act=_actor_can_act(service_of[did]),
                factor_vector=dict(factors_of[did]),
                became_actionable_at=(
                    str(demand.became_actionable_at.value)
                    if demand.became_actionable_at is not None
                    else None
                ),
                wait_context=wait_value,
                downstream_unblocks=tuple(unblocks_value) if unblocks_value else (),
                active_resource_burn=burn_value.value if burn_value else None,
                cost_of_delay=(
                    demand.cost_of_delay.value
                    if demand.cost_of_delay is not None
                    and isinstance(demand.cost_of_delay.value, CostOfDelay)
                    else None
                ),
                bundle_id=bundle_of.get(did),
                projection_relation=relation_of[did],
                explanation_reasons=tuple(
                    [r.value for r in pressure_of[did]]
                    + [r.value for r in service_reasons_of[did]]
                ),
                source_receipts=tuple(receipts),
                issues=tuple(issues_of[did]),
                is_fairness_sentinel=did in sentinels,
            )
        )

    # Starvation debt is reported per authority even when no sentinel can fire,
    # so a suppressed backlog is never invisible (F0G §9 "remains visible as
    # deferred debt").  An unknown ready time is a coverage gap, not age zero.
    fairness_debt: dict[str, dict[str, int]] = {}
    for authority_value in sorted(by_authority):
        eligible = [
            did for did in by_authority[authority_value]
            if class_of[did] in _DOMINANCE_ELIGIBLE
        ]
        hidden = [
            did for did in eligible
            if relation_of[did] is not ProjectionRelation.ROOT_VISIBLE
        ]
        if not hidden:
            continue
        fairness_debt[authority_value] = {
            "deferred_ordinary": len(hidden),
            "ready_age_unknown": sum(
                1 for did in hidden
                if by_id[did].became_actionable_at is None
                or _instant(by_id[did].became_actionable_at.value) is None
            ),
        }

    coverage = {
        "fairness_debt_by_authority": fairness_debt,
        "admitted_demands": len(ordered),
        "visible_roots": sum(
            1 for r in relation_of.values() if r is ProjectionRelation.ROOT_VISIBLE
        ),
        "omitted_with_receipt": len(omissions),
        "authority_unknown": sum(
            1 for a in authority_of.values() if a is AuthorityRequirement.UNKNOWN
        ),
        "ready_age_unknown": sum(
            1 for d in ordered if d.became_actionable_at is None
        ),
        "bundles": len(bundles),
    }

    return FrontierResult(
        schema=RESULT_SCHEMA,
        snapshot_identity=snapshot_identity,
        authority_frontiers=tuple(frontiers),
        bundles=tuple(bundles),
        items=tuple(items),
        fairness_sentinels=tuple(sorted(sentinels)),
        omissions=tuple(sorted(omissions, key=lambda o: o.demand_id)),
        comparisons=tuple(comparisons),
        coverage_summary=coverage,
        source_freshness_summary=_freshness_summary(ordered),
    )
