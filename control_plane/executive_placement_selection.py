"""Pure, deterministic Phase-1 placement-selection vertical (CAP-C1).

This module is a **pure, closed, deterministic** selection capability over
point-in-time, secret-safe candidate facts.  It performs no file I/O, no
clock read, no environment read, no subprocess, and no randomness — calling
:func:`select_placement` twice with the same arguments (in any candidate
list order) always produces byte-identical
``json.dumps(decision.to_dict(), sort_keys=True)`` output.

Titles, timestamps, account numbering, prose, Slack presence, and
"remembered" quota have **no input channel** into this module and **never**
influence ranking or selection — the only signals a candidate is judged on
are the closed set of typed facts :class:`PlacementCandidateFact` declares
(capabilities, quota class, provider, occupancy, capacity state, source
freshness, host-source closure, and effect state). Nothing here is scored
by observation recency, account-label lexical order, or any other
heuristic a caller might be tempted to smuggle in through a "soft" field —
:func:`select_placement` ranks eligible candidates by ``capacity_state``
alone.

Selection here creates **no** Job, Attempt, Worker, RuntimeBinding, or
provider action of any kind — it returns an inert
:class:`PlacementSelectionDecision` describing what a fully evaluated,
point-in-time selection over already-gathered facts *would* choose. Phase-B
runtime commitment (actually creating/binding a Job/Attempt/Worker) is
explicitly held on PR #255 (:mod:`control_plane.executive_runtime`, which
this module never imports, calls, or simulates).

Per-candidate exclusion is a REFINEMENT of the aggregate precedence
(:func:`_first_exclusion_reason` checks its gates in the same top-to-bottom
order :data:`_AGGREGATE_PRECEDENCE` ranks reasons by), and a
``CONTRADICTORY``/``EFFECT_UNKNOWN`` candidate is excluded PER-CANDIDATE
only — a clean sibling in the same call may still be ``SELECTED`` (ruling
m-6). Only a repeated ``worker_id`` is globally fatal to the whole
decision.
"""
from __future__ import annotations

import dataclasses
import enum
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.executive_orchestration_principal import (
    OrchestrationPrincipalError,
    build_placement_snapshot,
    validate_placement_snapshot,
)
from control_plane.executive_steward import (
    CapacityState,
    EffectState,
    Freshness,
    ResponsibilityFact,
    SourceOwner,
    SourceRef,
)

#: Schema version of the wire document :meth:`PlacementSelectionDecision.to_dict`
#: emits and :func:`validate_placement_selection` accepts.
SELECTION_SCHEMA = "mastermind.executive_placement_selection.v1"


class _ValueEnum(str, enum.Enum):
    """String enum whose value is the public wire value (steward idiom)."""


class OccupancyState(_ValueEnum):
    FREE = "free"
    OCCUPIED = "occupied"
    BOUND_ELSEWHERE = "bound_elsewhere"
    CONTRADICTORY = "contradictory"


class SelectionState(_ValueEnum):
    SELECTED = "selected"
    WAITING_CAPACITY = "waiting_capacity"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    NO_ELIGIBLE_CANDIDATE = "no_eligible_candidate"
    STALE_EVIDENCE = "stale_evidence"
    EFFECT_UNKNOWN = "effect_unknown"
    TIE_ABSTAINED = "tie_abstained"


class ExclusionReason(_ValueEnum):
    CAPABILITY_MISMATCH = "capability_mismatch"
    QUOTA_CLASS_MISMATCH = "quota_class_mismatch"
    PROVIDER_MISMATCH = "provider_mismatch"
    OCCUPIED = "occupied"
    BOUND_ELSEWHERE = "bound_elsewhere"
    CONTRADICTORY_BINDING = "contradictory_binding"
    STALE_OCCUPANCY_FACT = "stale_occupancy_fact"
    STALE_CAPACITY_FACT = "stale_capacity_fact"
    UNKNOWN_FRESHNESS = "unknown_freshness"
    HOST_SOURCE_UNPROVEN = "host_source_unproven"
    EFFECT_UNKNOWN = "effect_unknown"
    CAPACITY_UNKNOWN = "capacity_unknown"
    DUPLICATE_IDENTITY = "duplicate_identity"


#: The only tie-breaker token :func:`select_placement` will honor. Any other
#: non-``None`` value is a refused input, never a silently-ignored one.
_RECOGNIZED_TIE_BREAKERS = frozenset({"worker_id_lexicographic"})

#: Ranking order for eligible candidates — capacity state ONLY. Nothing
#: else (observation recency, account-label text, title) ever breaks a tie.
_CAPACITY_RANK: dict[CapacityState, int] = {
    CapacityState.AVAILABLE: 0,
    CapacityState.DEGRADED: 1,
}

# Reviewer n-11: an eligible candidate's capacity_state is looked up in
# _CAPACITY_RANK unconditionally (candidates whose capacity_state is
# UNKNOWN are excluded earlier, at the CAPACITY_UNKNOWN gate, so they never
# reach this lookup) — but a FUTURE CapacityState member added to
# executive_steward without a matching _CAPACITY_RANK entry would otherwise
# only surface as a bare KeyError deep on the winning path. Fail loudly at
# IMPORT time instead: every CapacityState member must either be ranked
# here or be exactly CapacityState.UNKNOWN (the one member deliberately
# excluded from ranking because it never survives to be ranked).
assert all(
    member in _CAPACITY_RANK or member is CapacityState.UNKNOWN
    for member in CapacityState
), "every CapacityState member must be ranked in _CAPACITY_RANK or be CapacityState.UNKNOWN"

#: Aggregate precedence, evaluated top-to-bottom, when eligible candidates
#: is empty. Each entry is (state, set-of-exclusion-reasons-that-trigger-it);
#: the first entry whose reason set intersects the exclusions actually
#: present wins. ``HOST_SOURCE_UNPROVEN`` and the three mismatch reasons
#: (``CAPABILITY_MISMATCH``/``QUOTA_CLASS_MISMATCH``/``PROVIDER_MISMATCH``)
#: are DELIBERATELY absent from every bucket below — reviewer-ratified
#: (M-4/n-…): a candidate that is merely the wrong shape for this demand,
#: or whose host-source closure was never proven, is not "the org is
#: waiting on capacity" or "evidence is stale" in the same sense staleness/
#: occupancy/effect-unknown are — it falls through to
#: ``NO_ELIGIBLE_CANDIDATE``, same as zero candidates at all.
#: :func:`_first_exclusion_reason` is a REFINEMENT of this same precedence
#: at the per-candidate level: its fixed gate order checks the trigger sets
#: below in this exact top-to-bottom order (splitting each bucket into its
#: own stable sub-order), so the per-candidate reason a caller sees is
#: never surprising relative to what the aggregate would pick if it were
#: the only reason present.
_AGGREGATE_PRECEDENCE: tuple[tuple[SelectionState, frozenset[ExclusionReason]], ...] = (
    (SelectionState.RECONCILIATION_REQUIRED, frozenset({ExclusionReason.CONTRADICTORY_BINDING})),
    (SelectionState.EFFECT_UNKNOWN, frozenset({ExclusionReason.EFFECT_UNKNOWN})),
    (
        SelectionState.STALE_EVIDENCE,
        frozenset({
            ExclusionReason.STALE_OCCUPANCY_FACT,
            ExclusionReason.STALE_CAPACITY_FACT,
            ExclusionReason.UNKNOWN_FRESHNESS,
            ExclusionReason.CAPACITY_UNKNOWN,
        }),
    ),
    (
        SelectionState.WAITING_CAPACITY,
        frozenset({ExclusionReason.OCCUPIED, ExclusionReason.BOUND_ELSEWHERE}),
    ),
)


# ---------------------------------------------------------------------------
# secret-safe token validators
# ---------------------------------------------------------------------------

def _require_token(name: str, value: object) -> str:
    """Every text token in this module's wire — worker_id, provider,
    quota_class, capabilities, tie-breaker strings, exclusion/tied worker
    ids — is secret-safe: non-empty, no whitespace, and (reviewer M-1/M-2)
    no ``"@"`` or ``"/"`` either, so an email address or a filesystem path
    can never flow through ANY token field, not just ``account_label``.
    """
    if (
        not isinstance(value, str)
        or not value
        or any(ch.isspace() for ch in value)
        or "@" in value
        or "/" in value
    ):
        raise ValueError(f"{name} must be a non-empty token with no whitespace, '@', or '/'")
    return value


def _require_account_label(value: object) -> str:
    # _require_token already rejects '@'/'/' for every token (see above);
    # this wrapper is kept, unchanged in name and call sites, as the
    # explicit account-label-specific gate the FROZEN SPEC names.
    return _require_token("account_label", value)


def _require_capability_set(name: str, value: object) -> frozenset[str]:
    if not isinstance(value, frozenset):
        raise TypeError(f"{name} must be a frozenset[str]")
    for item in value:
        _require_token(f"{name} item", item)
    return value


def _require_enum(name: str, value: object, expected: type[enum.Enum]) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{name} must be {expected.__name__}")


def _require_int_at_least(name: str, value: object, floor: int) -> int:
    if type(value) is not int or value < floor:
        raise ValueError(f"{name} must be an integer >= {floor}")
    return value


def _require_bool(name: str, value: object) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{name} must be bool")
    return value


def _require_source_owner(
    source: object, allowed: tuple[SourceOwner, ...], fact_name: str
) -> SourceRef:
    if not isinstance(source, SourceRef):
        raise TypeError(f"{fact_name} must be SourceRef")
    if source.owner not in allowed:
        if len(allowed) == 1:
            raise ValueError(f"{fact_name} owner must be {allowed[0].value}")
        values = ", ".join(owner.value for owner in allowed)
        raise ValueError(f"{fact_name} owner must be one of: {values}")
    return source


def _require_responsibility_ref(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("WS:")
        or len(value) <= 3
        or any(ch.isspace() for ch in value)
    ):
        raise ValueError("responsibility_ref must be an exact WS:<key> identity")
    return value


# ---------------------------------------------------------------------------
# input dataclasses
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True, slots=True)
class PlacementDemand:
    """What a waiting-capacity responsibility needs, closed and secret-free."""

    required_capabilities: frozenset[str]
    quota_class: str
    provider: str | None

    def __post_init__(self) -> None:
        _require_capability_set("required_capabilities", self.required_capabilities)
        _require_token("quota_class", self.quota_class)
        if self.provider is not None:
            _require_token("provider", self.provider)


@dataclasses.dataclass(frozen=True, slots=True)
class PlacementCandidateFact:
    """One point-in-time, source-attributed candidate worker observation.

    Every text field is a secret-safe token (no whitespace, no empty
    strings, no ``"@"``, no ``"/"``) so an email address or a filesystem
    path can never flow into a decision or its wire form. Construction ALSO
    eagerly builds (and discards) the Phase-B placement-snapshot shape from
    this candidate's own ``worker_id``/``quota_class``/``provider``/
    ``account_label``/``observed_at_ms`` — enforcing the snapshot's own
    canonical regexes at construction time, on every candidate, so
    ``select_placement`` can never raise late on the winning path.
    """

    worker_id: str
    provider: str
    account_label: str
    quota_class: str
    capabilities: frozenset[str]
    observed_at_ms: int
    occupancy: OccupancyState
    occupancy_source: SourceRef
    capacity_state: CapacityState
    capacity_source: SourceRef
    host_source_closure_proven: bool
    closure_source: SourceRef
    effect_state: EffectState

    def __post_init__(self) -> None:
        _require_token("worker_id", self.worker_id)
        _require_token("provider", self.provider)
        _require_account_label(self.account_label)
        _require_token("quota_class", self.quota_class)
        _require_capability_set("capabilities", self.capabilities)
        _require_int_at_least("observed_at_ms", self.observed_at_ms, 1)
        _require_enum("occupancy", self.occupancy, OccupancyState)
        _require_source_owner(
            self.occupancy_source, (SourceOwner.RUNTIME_BINDING,), "occupancy_source"
        )
        _require_enum("capacity_state", self.capacity_state, CapacityState)
        _require_source_owner(
            self.capacity_source, (SourceOwner.CAPACITY,), "capacity_source"
        )
        _require_bool("host_source_closure_proven", self.host_source_closure_proven)
        _require_source_owner(
            self.closure_source,
            (SourceOwner.CAPACITY, SourceOwner.EXECUTIVE_OS),
            "closure_source",
        )
        _require_enum("effect_state", self.effect_state, EffectState)
        # Reviewer M-1/M-2: eagerly enforce the Phase-B snapshot contract's
        # own canonical regexes (executive_orchestration_principal._ID_RE /
        # _PROVIDER_RE / _ACCOUNT_RE) at CONSTRUCTION time, on every
        # candidate — not only the eventual winner. Without this, a
        # candidate whose worker_id/quota_class/provider/account_label
        # passes this module's own looser token check but fails the
        # snapshot's stricter regex would only be discovered when
        # select_placement() tries to build its snapshot on the winning
        # path — a late, mid-algorithm raise on an input that had already
        # been accepted as a typed fact. Constructing the fact now refuses
        # it up front, so select_placement can never raise past this point.
        try:
            build_placement_snapshot(
                worker_id=self.worker_id,
                quota_class=self.quota_class,
                provider=self.provider,
                account_label=self.account_label,
                observed_at_ms=self.observed_at_ms,
            )
        except OrchestrationPrincipalError as exc:
            # OrchestrationPrincipalError's own messages already name only
            # the failing field (see executive_orchestration_principal._text
            # / _integer) and never interpolate the caller-supplied value —
            # safe to relay verbatim.
            raise ValueError(
                f"candidate fields fail the Phase-B placement snapshot contract: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# output dataclasses
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True, slots=True)
class CandidateExclusion:
    worker_id: str
    reason: ExclusionReason

    def __post_init__(self) -> None:
        _require_token("worker_id", self.worker_id)
        _require_enum("reason", self.reason, ExclusionReason)


@dataclasses.dataclass(frozen=True, slots=True)
class PlacementSelectionDecision:
    """The outcome of one :func:`select_placement` call.

    ``selected`` — when present — is the EXISTING ``mastermind.
    executive_placement_snapshot/v1`` shape
    (:func:`control_plane.executive_orchestration_principal.
    build_placement_snapshot`), i.e. the Phase-B seam: this module hands off
    to the same snapshot contract PR #255's runtime already speaks, without
    itself creating any Job/Attempt/Worker/RuntimeBinding or provider
    action.
    """

    responsibility_ref: str
    state: SelectionState
    selected: Mapping[str, Any] | None
    tie_breaker_used: str | None
    tied_worker_ids: tuple[str, ...]
    exclusions: tuple[CandidateExclusion, ...]
    evaluated_candidates: int

    def __post_init__(self) -> None:
        _require_responsibility_ref(self.responsibility_ref)
        _require_enum("state", self.state, SelectionState)
        if self.selected is not None and not isinstance(self.selected, Mapping):
            raise TypeError("selected must be a mapping or None")
        if self.tie_breaker_used is not None:
            _require_token("tie_breaker_used", self.tie_breaker_used)
        if not isinstance(self.tied_worker_ids, tuple) or not all(
            isinstance(w, str) for w in self.tied_worker_ids
        ):
            raise TypeError("tied_worker_ids must be a tuple of str")
        for worker_id in self.tied_worker_ids:
            _require_token("tied_worker_ids item", worker_id)
        if not isinstance(self.exclusions, tuple) or not all(
            isinstance(item, CandidateExclusion) for item in self.exclusions
        ):
            raise TypeError("exclusions must be a tuple of CandidateExclusion")
        if type(self.evaluated_candidates) is not int or self.evaluated_candidates < 0:
            raise ValueError("evaluated_candidates must be an integer >= 0")

    def to_dict(self) -> dict[str, Any]:
        """Closed-key, deterministically ordered wire document.

        Nothing beyond these eight keys is ever emitted — no source-ref
        fields, no environment, no clock read — so ``json.dumps(self.
        to_dict(), sort_keys=True)`` is byte-identical across repeated calls
        with equivalent inputs regardless of candidate list order.
        """
        selected = dict(self.selected) if self.selected is not None else None
        exclusions = sorted(
            (
                {"worker_id": item.worker_id, "reason": item.reason.value}
                for item in self.exclusions
            ),
            key=lambda item: (item["worker_id"], item["reason"]),
        )
        return {
            "schema_version": SELECTION_SCHEMA,
            "responsibility_ref": self.responsibility_ref,
            "state": self.state.value,
            "selected": selected,
            "tie_breaker_used": self.tie_breaker_used,
            "tied_worker_ids": sorted(self.tied_worker_ids),
            "exclusions": exclusions,
            "evaluated_candidates": self.evaluated_candidates,
        }


# ---------------------------------------------------------------------------
# wire-dict revalidation
# ---------------------------------------------------------------------------

_SELECTION_KEYS = frozenset({
    "schema_version", "responsibility_ref", "state", "selected",
    "tie_breaker_used", "tied_worker_ids", "exclusions", "evaluated_candidates",
})

_EXCLUSION_KEYS = frozenset({"worker_id", "reason"})


def validate_placement_selection(value: Any) -> dict[str, Any]:
    """Closed-key revalidation of a ``mastermind.executive_placement_selection.v1``
    wire dict. Raises ``ValueError``/``TypeError`` on any violation; never
    performs I/O.

    Every error message names the offending FIELD only — never the
    caller-supplied VALUE (reviewer M-3) — since this function's whole
    point is to revalidate a wire dict from a potentially untrusted or
    malformed source; interpolating the value back into the exception text
    would defeat that.

    Beyond per-field shape, this also enforces the CROSS-FIELD invariants a
    well-formed decision always satisfies: ``selected`` is present iff
    ``state == "selected"``; a set ``tie_breaker_used`` implies
    ``state == "selected"`` and at least two ``tied_worker_ids``;
    ``state == "tie_abstained"`` implies at least two ``tied_worker_ids``;
    every other state implies an EMPTY ``tied_worker_ids``; and
    ``evaluated_candidates`` is never smaller than either ``exclusions`` or
    ``tied_worker_ids``.
    """
    if not isinstance(value, Mapping) or set(value) != _SELECTION_KEYS:
        actual = sorted(value) if isinstance(value, Mapping) else type(value).__name__
        raise ValueError(
            f"placement selection must have exactly {sorted(_SELECTION_KEYS)}; got {actual}"
        )

    if value["schema_version"] != SELECTION_SCHEMA:
        raise ValueError("unsupported placement selection schema")

    responsibility_ref = _require_responsibility_ref(value["responsibility_ref"])

    try:
        state = SelectionState(value["state"])
    except ValueError as exc:
        raise ValueError("state is not a recognized SelectionState value") from exc

    selected_raw = value["selected"]
    selected = validate_placement_snapshot(selected_raw) if selected_raw is not None else None

    tie_breaker_used = value["tie_breaker_used"]
    if tie_breaker_used is not None:
        if not isinstance(tie_breaker_used, str):
            raise TypeError("tie_breaker_used must be a string or null")
        if tie_breaker_used not in _RECOGNIZED_TIE_BREAKERS:
            raise ValueError("tie_breaker_used is not a recognized tie-breaker token")

    tied_raw = value["tied_worker_ids"]
    if not isinstance(tied_raw, list) or not all(isinstance(w, str) for w in tied_raw):
        raise TypeError("tied_worker_ids must be a list of strings")
    for worker_id in tied_raw:
        _require_token("tied_worker_ids item", worker_id)
    if tied_raw != sorted(tied_raw):
        raise ValueError("tied_worker_ids must be sorted")

    exclusions_raw = value["exclusions"]
    if not isinstance(exclusions_raw, list):
        raise TypeError("exclusions must be a list")
    exclusions: list[dict[str, str]] = []
    for item in exclusions_raw:
        if not isinstance(item, Mapping) or set(item) != _EXCLUSION_KEYS:
            raise ValueError("each exclusion must have exactly {'worker_id', 'reason'}")
        worker_id = _require_token("exclusion worker_id", item["worker_id"])
        try:
            reason = ExclusionReason(item["reason"])
        except ValueError as exc:
            raise ValueError("exclusion reason is not a recognized ExclusionReason value") from exc
        exclusions.append({"worker_id": worker_id, "reason": reason.value})
    if exclusions != sorted(exclusions, key=lambda item: (item["worker_id"], item["reason"])):
        raise ValueError("exclusions must be sorted by worker_id then reason")

    evaluated_candidates = value["evaluated_candidates"]
    if type(evaluated_candidates) is not int or evaluated_candidates < 0:
        raise ValueError("evaluated_candidates must be an integer >= 0")

    # --- cross-field invariants (reviewer M-3) ------------------------------
    if (selected is not None) != (state is SelectionState.SELECTED):
        raise ValueError("selected must be present iff state is 'selected'")
    if tie_breaker_used is not None:
        if state is not SelectionState.SELECTED:
            raise ValueError("tie_breaker_used may only be set when state is 'selected'")
        if len(tied_raw) < 2:
            raise ValueError("tie_breaker_used requires at least two tied_worker_ids")
    if state is SelectionState.TIE_ABSTAINED and len(tied_raw) < 2:
        raise ValueError("state 'tie_abstained' requires at least two tied_worker_ids")
    if state not in (SelectionState.SELECTED, SelectionState.TIE_ABSTAINED) and tied_raw:
        raise ValueError(
            "tied_worker_ids must be empty unless state is 'selected' or 'tie_abstained'"
        )
    if evaluated_candidates < len(exclusions):
        raise ValueError("evaluated_candidates must be >= the number of exclusions")
    if evaluated_candidates < len(tied_raw):
        raise ValueError("evaluated_candidates must be >= the number of tied_worker_ids")

    return {
        "schema_version": SELECTION_SCHEMA,
        "responsibility_ref": responsibility_ref,
        "state": state.value,
        "selected": selected,
        "tie_breaker_used": tie_breaker_used,
        "tied_worker_ids": list(tied_raw),
        "exclusions": exclusions,
        "evaluated_candidates": evaluated_candidates,
    }


# ---------------------------------------------------------------------------
# the selector
# ---------------------------------------------------------------------------

def _first_exclusion_reason(
    candidate: PlacementCandidateFact, demand: PlacementDemand
) -> ExclusionReason | None:
    """The first failing gate, or ``None`` if the candidate survives every
    gate (i.e. is eligible).

    Reviewer-ratified order (M-4): this is a REFINEMENT of
    :data:`_AGGREGATE_PRECEDENCE` at the per-candidate level — reasons that
    would win the aggregate (``CONTRADICTORY_BINDING``, then
    ``EFFECT_UNKNOWN``, then the stale/unknown-freshness/capacity-unknown
    family, then ``OCCUPIED``/``BOUND_ELSEWHERE``) are checked first, in
    that same order, and only THEN the reasons the aggregate deliberately
    never elevates on their own (``HOST_SOURCE_UNPROVEN``, then the three
    mismatches). A candidate failing multiple gates always reports the
    highest-precedence one — e.g. a candidate that is both ``OCCUPIED`` and
    has a stale capacity fact reports ``STALE_CAPACITY_FACT``, never
    ``OCCUPIED``.

    Ruling (m-6): a ``CONTRADICTORY`` or ``EFFECT_UNKNOWN`` candidate is
    excluded PER-CANDIDATE only — it never poisons a clean sibling's
    eligibility, and a clean sibling may still be ``SELECTED`` in the same
    call. Only a repeated ``worker_id`` (duplicate identity) is globally
    fatal to the whole decision; see :func:`select_placement` step 3.
    """
    if candidate.occupancy is OccupancyState.CONTRADICTORY:
        return ExclusionReason.CONTRADICTORY_BINDING
    if candidate.effect_state is EffectState.EFFECT_UNKNOWN:
        return ExclusionReason.EFFECT_UNKNOWN
    if candidate.occupancy_source.freshness is Freshness.STALE:
        return ExclusionReason.STALE_OCCUPANCY_FACT
    if candidate.occupancy_source.freshness is Freshness.UNKNOWN:
        return ExclusionReason.UNKNOWN_FRESHNESS
    if candidate.capacity_source.freshness is Freshness.STALE:
        return ExclusionReason.STALE_CAPACITY_FACT
    if candidate.capacity_source.freshness is Freshness.UNKNOWN:
        return ExclusionReason.UNKNOWN_FRESHNESS
    if candidate.capacity_state is CapacityState.UNKNOWN:
        return ExclusionReason.CAPACITY_UNKNOWN
    if candidate.occupancy is OccupancyState.OCCUPIED:
        return ExclusionReason.OCCUPIED
    if candidate.occupancy is OccupancyState.BOUND_ELSEWHERE:
        return ExclusionReason.BOUND_ELSEWHERE
    if not candidate.host_source_closure_proven:
        return ExclusionReason.HOST_SOURCE_UNPROVEN
    if not demand.required_capabilities.issubset(candidate.capabilities):
        return ExclusionReason.CAPABILITY_MISMATCH
    if candidate.quota_class != demand.quota_class:
        return ExclusionReason.QUOTA_CLASS_MISMATCH
    if demand.provider is not None and demand.provider != candidate.provider:
        return ExclusionReason.PROVIDER_MISMATCH
    return None


def _aggregate_state(reasons_present: frozenset[ExclusionReason]) -> SelectionState:
    for state, triggers in _AGGREGATE_PRECEDENCE:
        if reasons_present & triggers:
            return state
    return SelectionState.NO_ELIGIBLE_CANDIDATE


def _decision(
    responsibility_ref: str,
    state: SelectionState,
    *,
    selected: Mapping[str, Any] | None = None,
    tie_breaker_used: str | None = None,
    tied_worker_ids: tuple[str, ...] = (),
    exclusions: tuple[CandidateExclusion, ...] = (),
    evaluated_candidates: int,
) -> PlacementSelectionDecision:
    return PlacementSelectionDecision(
        responsibility_ref=responsibility_ref,
        state=state,
        selected=selected,
        tie_breaker_used=tie_breaker_used,
        tied_worker_ids=tied_worker_ids,
        exclusions=exclusions,
        evaluated_candidates=evaluated_candidates,
    )


def select_placement(
    *,
    responsibility: ResponsibilityFact,
    demand: PlacementDemand,
    candidates: Sequence[PlacementCandidateFact],
    accepted_tie_breaker: str | None = None,
) -> PlacementSelectionDecision:
    """Pure, deterministic, fail-closed placement selection.

    Documented algorithm
    ---------------------
    1. Input refusal (typed ``ValueError``, no decision produced):
       ``responsibility.state != "waiting_capacity"``; ``accepted_tie_breaker``
       not in the closed recognized set ``{"worker_id_lexicographic"}`` when
       not ``None``; any element of ``candidates`` not a
       :class:`PlacementCandidateFact`.
    2. ``responsibility.source.freshness`` not ``CURRENT`` -> ``STALE_EVIDENCE``
       (no selection, no exclusions, ``evaluated_candidates=len(candidates)``).
    3. Any repeated ``worker_id`` -> ``RECONCILIATION_REQUIRED``; every
       duplicated id gets exactly one ``DUPLICATE_IDENTITY`` exclusion.
    4. Candidates are evaluated in canonical ``worker_id``-sorted order. Per
       candidate, the reason is the first failing gate in a FIXED order
       that REFINES :data:`_AGGREGATE_PRECEDENCE` (see
       :func:`_first_exclusion_reason`): ``CONTRADICTORY`` occupancy, then
       ``EFFECT_UNKNOWN``, then occupancy-source staleness/unknown-freshness,
       then capacity-source staleness/unknown-freshness, then
       ``capacity_state`` ``UNKNOWN``, then ``OCCUPIED``, then
       ``BOUND_ELSEWHERE``, then (ratified: these deliberately fall through
       to ``NO_ELIGIBLE_CANDIDATE`` at the aggregate step rather than
       elevating their own state) unproven host-source closure, then a
       capability/quota-class/provider mismatch. A candidate failing no
       gate is eligible; a ``CONTRADICTORY``/``EFFECT_UNKNOWN`` exclusion is
       PER-CANDIDATE only — it never excludes a clean sibling, which may
       still be ``SELECTED`` in the same call (ruling m-6).
    5. Eligible non-empty: rank ONLY by ``capacity_state`` (``AVAILABLE``
       before ``DEGRADED``); take the min-rank set. Exactly one winner ->
       ``SELECTED``. More than one: ``accepted_tie_breaker ==
       "worker_id_lexicographic"`` picks the lexicographic minimum
       (``SELECTED``, ``tie_breaker_used`` set); otherwise ``TIE_ABSTAINED``
       with every tied id in ``tied_worker_ids``.
    6. Eligible empty: aggregate state by the CLOSED, documented precedence
       over the exclusion reasons actually present — see
       :data:`_AGGREGATE_PRECEDENCE` — falling through to
       ``NO_ELIGIBLE_CANDIDATE`` when only mismatch/``HOST_SOURCE_UNPROVEN``
       reasons are present (deliberate, ratified — see
       :data:`_AGGREGATE_PRECEDENCE`), or when there were zero candidates at
       all.

    No clock, no environment, no I/O, no randomness: ranking, tie-breaking,
    and every aggregate decision are functions of the typed facts alone.
    """
    if not isinstance(responsibility, ResponsibilityFact):
        raise TypeError("responsibility must be a ResponsibilityFact")
    if not isinstance(demand, PlacementDemand):
        raise TypeError("demand must be a PlacementDemand")
    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
        raise TypeError("candidates must be a sequence of PlacementCandidateFact")
    candidate_tuple = tuple(candidates)
    if not all(isinstance(item, PlacementCandidateFact) for item in candidate_tuple):
        raise ValueError("every candidate must be a PlacementCandidateFact")
    if responsibility.state != "waiting_capacity":
        raise ValueError(
            "responsibility.state must be 'waiting_capacity' before placement "
            "selection may run"
        )
    if accepted_tie_breaker is not None and accepted_tie_breaker not in _RECOGNIZED_TIE_BREAKERS:
        raise ValueError("accepted_tie_breaker is not a recognized tie-breaker token")

    responsibility_ref = responsibility.responsibility_ref
    evaluated_candidates = len(candidate_tuple)

    if responsibility.source.freshness is not Freshness.CURRENT:
        return _decision(
            responsibility_ref, SelectionState.STALE_EVIDENCE,
            evaluated_candidates=evaluated_candidates,
        )

    seen_counts: dict[str, int] = {}
    for candidate in candidate_tuple:
        seen_counts[candidate.worker_id] = seen_counts.get(candidate.worker_id, 0) + 1
    duplicated = sorted(
        worker_id for worker_id, count in seen_counts.items() if count > 1
    )
    if duplicated:
        exclusions = tuple(
            CandidateExclusion(worker_id=worker_id, reason=ExclusionReason.DUPLICATE_IDENTITY)
            for worker_id in duplicated
        )
        return _decision(
            responsibility_ref, SelectionState.RECONCILIATION_REQUIRED,
            exclusions=exclusions, evaluated_candidates=evaluated_candidates,
        )

    ordered = sorted(candidate_tuple, key=lambda c: c.worker_id)

    exclusions_list: list[CandidateExclusion] = []
    eligible: list[PlacementCandidateFact] = []
    for candidate in ordered:
        reason = _first_exclusion_reason(candidate, demand)
        if reason is None:
            eligible.append(candidate)
        else:
            exclusions_list.append(CandidateExclusion(worker_id=candidate.worker_id, reason=reason))
    exclusions = tuple(exclusions_list)

    if eligible:
        min_rank = min(_CAPACITY_RANK[c.capacity_state] for c in eligible)
        winners = [c for c in eligible if _CAPACITY_RANK[c.capacity_state] == min_rank]

        if len(winners) == 1:
            winner = winners[0]
            selected = build_placement_snapshot(
                worker_id=winner.worker_id,
                quota_class=winner.quota_class,
                provider=winner.provider,
                account_label=winner.account_label,
                observed_at_ms=winner.observed_at_ms,
            )
            return _decision(
                responsibility_ref, SelectionState.SELECTED,
                selected=selected, exclusions=exclusions,
                evaluated_candidates=evaluated_candidates,
            )

        tied_worker_ids = tuple(sorted(c.worker_id for c in winners))
        if accepted_tie_breaker == "worker_id_lexicographic":
            winner = min(winners, key=lambda c: c.worker_id)
            selected = build_placement_snapshot(
                worker_id=winner.worker_id,
                quota_class=winner.quota_class,
                provider=winner.provider,
                account_label=winner.account_label,
                observed_at_ms=winner.observed_at_ms,
            )
            return _decision(
                responsibility_ref, SelectionState.SELECTED,
                selected=selected, tie_breaker_used="worker_id_lexicographic",
                tied_worker_ids=tied_worker_ids, exclusions=exclusions,
                evaluated_candidates=evaluated_candidates,
            )

        return _decision(
            responsibility_ref, SelectionState.TIE_ABSTAINED,
            tied_worker_ids=tied_worker_ids, exclusions=exclusions,
            evaluated_candidates=evaluated_candidates,
        )

    reasons_present = frozenset(item.reason for item in exclusions)
    state = _aggregate_state(reasons_present)
    return _decision(
        responsibility_ref, state, exclusions=exclusions,
        evaluated_candidates=evaluated_candidates,
    )
