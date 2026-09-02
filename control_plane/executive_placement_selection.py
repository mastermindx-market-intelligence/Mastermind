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
NEVER performed here: it belongs to the separate Executive claim owner
(:mod:`control_plane.executive_runtime`, which this module never imports,
calls, or simulates). That boundary is a durable property of this module —
selection is inert — not a status held on any particular carrier.

Per-candidate exclusion is a REFINEMENT of the aggregate precedence
(:func:`_first_exclusion_reason` checks its gates in the same top-to-bottom
order :data:`_AGGREGATE_PRECEDENCE` ranks reasons by), and a
``CONTRADICTORY``/``EFFECT_UNKNOWN`` candidate is excluded PER-CANDIDATE
only — a clean sibling in the same call may still be ``SELECTED`` (ruling
m-6). Only a repeated ``worker_id`` is globally fatal to the whole
decision.

Sol addendum (no scope change): (A) **C1 has no tie-breaker authority** —
an exact top tie among eligible candidates ALWAYS abstains
(``TIE_ABSTAINED``); :func:`select_placement` refuses any non-``None``
``accepted_tie_breaker`` outright, and ``tie_breaker_used`` is a RESERVED
field, always ``None``, kept only as a forward-compatible wire slot for a
later wave's typed, source-owned ruling receipt. (B) Every decision also
carries ``evidence`` — one immutable row per candidate actually evaluated,
including short-circuited and duplicate ones — and a constant
``selection_is_commitment: false`` discriminator, so a downstream consumer
can audit exactly what was seen and never has to infer non-commitment from
a field's absence.

Sol correction — MODE WAVE (no scope change): an occupied EXISTING
conversation is not the same fact as an unavailable provider seat. Every
:class:`PlacementCandidateFact` carries a closed :class:`PlacementMode` —
``EXISTING_SESSION_REUSE`` or ``NEW_SESSION_MATERIALIZATION`` — and every
:class:`PlacementDemand` carries a non-empty ``allowed_modes`` set; an
exact-session demand (``allowed_modes={EXISTING_SESSION_REUSE}``) can
NEVER be satisfied by a fresh lane, by construction (``MODE_NOT_ALLOWED``).
A busy existing conversation (``OCCUPIED``) never erases a separately
proven fresh-session lane in the same call, and vice versa — each
candidate is gated on its own facts only (ruling m-6, extended). Choosing
a fresh lane still creates nothing: selection stays fully inert regardless
of mode (``selection_is_commitment`` stays ``false``).

**No Slack-principal field exists in this module, and none may be added.**
Two candidates sharing an ``account_label`` remain fully independent
candidates: there is no collapse, no deduplication, and no ranking by
``account_label`` — three conversation candidates against the same account
yield three separate :class:`CandidateEvidence` rows, exactly like three
candidates against three different accounts would. Slack presence,
communication identity, account numbering, and titles have **no input
channel** into this module; a Slack principal (or any other communication
identity) is a fact about how a HUMAN would be reached, never a fact this
selector reads, ranks, or dedupes by.
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
    Seat,
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


class PlacementMode(_ValueEnum):
    """Mode wave (Sol correction): a busy EXISTING conversation is not the
    same fact as an unavailable provider seat. ``EXISTING_SESSION_REUSE``
    describes a candidate that would REUSE an already-materialized
    conversation/session; ``NEW_SESSION_MATERIALIZATION`` describes a
    candidate that would create a fresh one. An exact-session demand is
    expressed as ``allowed_modes={EXISTING_SESSION_REUSE}`` — a fresh lane
    can never satisfy it, by construction (see the ``MODE_NOT_ALLOWED``
    gate)."""

    EXISTING_SESSION_REUSE = "existing_session_reuse"
    NEW_SESSION_MATERIALIZATION = "new_session_materialization"


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
    #: Mode wave (Sol correction) — see the gate order in
    #: :func:`_first_exclusion_reason` and the fallthrough note on
    #: :data:`_AGGREGATE_PRECEDENCE`.
    MODE_NOT_ALLOWED = "mode_not_allowed"
    CREATION_SURFACE_INACCESSIBLE = "creation_surface_inaccessible"
    SESSION_CREATION_DISALLOWED = "session_creation_disallowed"


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
#: present wins. ``HOST_SOURCE_UNPROVEN``, the three mismatch reasons
#: (``CAPABILITY_MISMATCH``/``QUOTA_CLASS_MISMATCH``/``PROVIDER_MISMATCH``),
#: and — mode wave, Sol correction — ``MODE_NOT_ALLOWED``/
#: ``CREATION_SURFACE_INACCESSIBLE``/``SESSION_CREATION_DISALLOWED`` are
#: DELIBERATELY absent from every bucket below — reviewer-ratified (M-4/
#: n-…): a candidate that is merely the wrong shape for this demand, whose
#: host-source closure was never proven, whose mode this demand does not
#: accept, or whose fresh-lane creation preconditions are not met, is not
#: "the org is waiting on capacity" or "evidence is stale" in the same
#: sense staleness/occupancy/effect-unknown are — it falls through to
#: ``NO_ELIGIBLE_CANDIDATE`` (durable ineligibility), same as zero
#: candidates at all.
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
    ids, ``responsibility_ref``, and every ``*_source`` ``ref``/
    ``observed_at`` — is secret-safe: non-empty, no whitespace, no ``"@"``
    or ``"/"`` (reviewer M-1/M-2), and no backslash or control character
    (exact-head review), so neither an email address, a POSIX path, a
    Windows path, nor an ANSI terminal escape can flow through ANY token
    field. ``scripts/chairman_control_room.py`` prints these fields to a
    terminal, where an escape sequence is not inert.
    """
    if (
        not isinstance(value, str)
        or not value
        or any(ch.isspace() for ch in value)
        or "@" in value
        or "/" in value
        # Exact-head review: `str.isspace()` does not cover NUL, ESC or BEL,
        # and banning "/" alone does not cover a Windows path. These reached
        # the composed Chairman document intact, and `scripts/
        # chairman_control_room.py` prints these fields to a terminal, where
        # an ANSI escape is not inert. `isprintable()` is False for every
        # control character (and for the separators already banned above).
        or "\\" in value
        or any(not ch.isprintable() for ch in value)
    ):
        raise ValueError(
            f"{name} must be a non-empty token with no whitespace, '@', '/', "
            "backslash, or control characters"
        )
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


def _require_mode_set(name: str, value: object):
    """A non-empty ``frozenset`` of :class:`PlacementMode` members. An
    exact-session demand is expressed as ``{EXISTING_SESSION_REUSE}`` —
    never an empty set, which would mean no mode could ever satisfy it."""
    if not isinstance(value, frozenset) or not value:
        raise ValueError(f"{name} must be a non-empty frozenset[PlacementMode]")
    for item in value:
        _require_enum(f"{name} item", item, PlacementMode)
    return value


def _require_mode_shape(
    mode: object,
    creation_surface_accessible: object,
    session_creation_allowed: object,
) -> None:
    """The closed mode-shape rule (mode wave), shared by
    :class:`PlacementCandidateFact` and :class:`CandidateEvidence`: for
    ``EXISTING_SESSION_REUSE`` both creation bools MUST be ``None``; for
    ``NEW_SESSION_MATERIALIZATION`` both MUST be actual ``bool`` values.
    """
    if mode is PlacementMode.EXISTING_SESSION_REUSE:
        if creation_surface_accessible is not None or session_creation_allowed is not None:
            raise ValueError(
                "creation_surface_accessible and session_creation_allowed must "
                "both be None for mode=existing_session_reuse"
            )
    else:
        if type(creation_surface_accessible) is not bool or type(session_creation_allowed) is not bool:
            raise ValueError(
                "creation_surface_accessible and session_creation_allowed must "
                "both be bool for mode=new_session_materialization"
            )


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


#: The ONE definition of which owner may attest each candidate fact. Used
#: by PlacementCandidateFact, CandidateEvidence AND the wire validator, so
#: the typed and serialized forms can never drift apart (review 5084378111
#: BLOCKER 2: they had).
_OCCUPANCY_SOURCE_OWNERS: tuple[SourceOwner, ...] = (SourceOwner.RUNTIME_BINDING,)
_CAPACITY_SOURCE_OWNERS: tuple[SourceOwner, ...] = (SourceOwner.CAPACITY,)
_CLOSURE_SOURCE_OWNERS: tuple[SourceOwner, ...] = (
    SourceOwner.CAPACITY, SourceOwner.EXECUTIVE_OS,
)


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
    """An exact ``WS:<key>`` identity that ALSO obeys the module's token law.

    Exact-head review: this had its own looser check, so a
    ``responsibility_ref`` carrying a filesystem path or an email address
    validated and reached the Chairman wire verbatim — contradicting
    :func:`_require_token`'s stated contract that neither can flow through
    any token field. One shared helper now governs both, and because this
    same function guards BOTH construction
    (:class:`PlacementSelectionDecision`) and wire revalidation, the two
    sides cannot disagree: a ref the wire would refuse can never be emitted.
    """
    if (
        not isinstance(value, str)
        or not value.startswith("WS:")
        or len(value) <= 3
    ):
        raise ValueError("responsibility_ref must be an exact WS:<key> identity")
    _require_token("responsibility_ref", value)
    return value


# ---------------------------------------------------------------------------
# input dataclasses
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True, slots=True)
class PlacementDemand:
    """What a waiting-capacity responsibility needs, closed and secret-free.

    ``allowed_modes`` (mode wave) is REQUIRED and non-empty: it is the
    closed set of :class:`PlacementMode` values a candidate may satisfy
    this demand with. An exact-session demand — "reuse THIS conversation,
    never a fresh one" — is expressed as
    ``allowed_modes={PlacementMode.EXISTING_SESSION_REUSE}``; a candidate
    whose own ``mode`` is not a member is excluded ``MODE_NOT_ALLOWED``
    (see :func:`_first_exclusion_reason`), so a fresh lane can never
    satisfy an exact-session demand by construction.
    """

    required_capabilities: frozenset[str]
    quota_class: str
    provider: str | None
    allowed_modes: frozenset[PlacementMode]

    def __post_init__(self) -> None:
        _require_capability_set("required_capabilities", self.required_capabilities)
        _require_token("quota_class", self.quota_class)
        if self.provider is not None:
            _require_token("provider", self.provider)
        _require_mode_set("allowed_modes", self.allowed_modes)


@dataclasses.dataclass(frozen=True, slots=True)
class PlacementCandidateFact:
    """One point-in-time, source-attributed candidate worker observation.

    Every text field — INCLUDING each ``*_source.ref`` AND each present
    ``*_source.observed_at`` — is a secret-safe token (see
    :func:`_require_token`: no whitespace, empty strings, ``"@"``, ``"/"``,
    backslash or control characters) so an email address, a filesystem path
    or a terminal escape can never flow into a decision or its wire form. Construction ALSO eagerly builds (and discards) the
    Phase-B placement-snapshot shape from this candidate's own
    ``worker_id``/``quota_class``/``provider``/``account_label``/
    ``observed_at_ms`` — enforcing the snapshot's own canonical regexes at
    construction time, on every candidate, so ``select_placement`` can
    never raise late on the winning path. Addendum B: the ``*_source.ref``
    checks close the same gap for ``evidence`` — every source ref here
    flows verbatim into a decision's evidence rows, so it must already
    satisfy that wire's own validator.

    Mode wave: ``mode`` names whether this candidate would REUSE an
    existing conversation/session (``EXISTING_SESSION_REUSE``) or
    materialize a fresh one (``NEW_SESSION_MATERIALIZATION``).
    ``creation_surface_accessible``/``session_creation_allowed`` are
    CLOSED-SHAPE with ``mode``: both ``None`` for a reuse candidate (a
    fresh-lane-only concern does not apply to reusing something that
    already exists), both actual ``bool`` for a fresh-lane candidate. Every
    OTHER field keeps its existing meaning for a fresh lane too:
    ``occupancy`` describes the LANE itself (normally ``FREE``, but a
    bound/contradictory lane still representable), ``capacity_state``/
    ``capacity_source`` prove usable quota/auth realm, and closure/effect
    are unchanged.
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
    mode: PlacementMode
    creation_surface_accessible: bool | None
    session_creation_allowed: bool | None

    def __post_init__(self) -> None:
        _require_token("worker_id", self.worker_id)
        _require_token("provider", self.provider)
        _require_account_label(self.account_label)
        _require_token("quota_class", self.quota_class)
        _require_capability_set("capabilities", self.capabilities)
        _require_int_at_least("observed_at_ms", self.observed_at_ms, 1)
        _require_enum("occupancy", self.occupancy, OccupancyState)
        _require_source_owner(
            self.occupancy_source, _OCCUPANCY_SOURCE_OWNERS, "occupancy_source"
        )
        _require_enum("capacity_state", self.capacity_state, CapacityState)
        _require_source_owner(
            self.capacity_source, _CAPACITY_SOURCE_OWNERS, "capacity_source"
        )
        _require_bool("host_source_closure_proven", self.host_source_closure_proven)
        _require_source_owner(
            self.closure_source, _CLOSURE_SOURCE_OWNERS, "closure_source"
        )
        _require_enum("effect_state", self.effect_state, EffectState)
        _require_enum("mode", self.mode, PlacementMode)
        _require_mode_shape(self.mode, self.creation_surface_accessible, self.session_creation_allowed)
        # Addendum B round-trip closure: every source ref here flows
        # verbatim into a decision's `evidence` (addendum B), whose wire
        # validator re-checks `ref` via this SAME `_require_token` (reuse,
        # per the addendum). executive_steward.SourceRef's OWN validator is
        # weaker (no "@"/"/" ban) — without this eager check here, a
        # candidate could construct cleanly yet produce a decision whose
        # own to_dict() output FAILS validate_placement_selection, breaking
        # the closed round-trip this module promises everywhere else.
        _require_token("occupancy_source.ref", self.occupancy_source.ref)
        _require_token("capacity_source.ref", self.capacity_source.ref)
        _require_token("closure_source.ref", self.closure_source.ref)
        # Exact-head review: the SAME closure was missing for `observed_at`.
        # SourceRef permits "@"/"/" there, but `_validate_source_ref_dict`
        # token-checks it — so a candidate could construct cleanly and then
        # produce a decision whose own to_dict() FAILED this module's
        # validator, and the real Control Room dropped a genuine decision
        # into `degraded`. That is the exact failure the .ref checks above
        # exist to prevent; this completes it. `observed_at` is optional, so
        # only a present value is checked.
        for _name, _source in (
            ("occupancy_source", self.occupancy_source),
            ("capacity_source", self.capacity_source),
            ("closure_source", self.closure_source),
        ):
            if _source.observed_at is not None:
                _require_token(f"{_name}.observed_at", _source.observed_at)
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
class CandidateEvidence:
    """One immutable audit row over exactly what was observed for one
    evaluated candidate — addendum B: a downstream consumer of a decision
    must be able to see EVERY fact that went into it, not just the winner
    and the exclusion reasons, without re-deriving anything from a raw
    candidate list this module never returns. A row exists for every
    candidate handed to :func:`select_placement`, REGARDLESS of whether
    that candidate was eligible, excluded, the eventual winner, or even a
    duplicate ``worker_id`` — evidence is a record of what was looked at,
    never a deduplicated or filtered view.

    Mode wave: ``mode``/``creation_surface_accessible``/
    ``session_creation_allowed`` mirror :class:`PlacementCandidateFact`'s
    own fields verbatim, including the same closed mode-shape rule
    (:func:`_require_mode_shape`).

    Provenance wave: a row is now a COMPLETE
    :class:`PlacementCandidateFact` projection — it carries ``provider``,
    ``account_label``, ``quota_class``, ``capabilities`` and
    ``observed_at_ms`` as well. That upgrade is what makes the claim above
    ("EVERY fact that went into it") literally true, and it is load-bearing
    rather than cosmetic: together with the decision's carried
    :class:`PlacementDemand` and responsibility freshness, these rows are
    exactly the closed input set :func:`validate_placement_selection` needs
    to REBUILD the typed inputs and recompute the decision through
    :func:`select_placement`. Without them the demand-gated fields could
    not be re-derived and the ``selected`` snapshot's own
    ``provider``/``account_label``/``quota_class``/``observed_at_ms`` would
    be bound to nothing on the wire.
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
    mode: PlacementMode
    creation_surface_accessible: bool | None
    session_creation_allowed: bool | None

    def __post_init__(self) -> None:
        _require_token("worker_id", self.worker_id)
        # Provenance wave: an evidence row is the decision's own CANONICAL
        # INPUT PROJECTION for one candidate, so it must carry EVERY field
        # PlacementCandidateFact needs — otherwise validate_placement_
        # selection() cannot rebuild the inputs and recompute the decision,
        # and the demand-gated fields (provider/quota_class/capabilities)
        # plus the snapshot-bearing ones (account_label/observed_at_ms)
        # would be bound to nothing on the wire.
        _require_token("provider", self.provider)
        _require_account_label(self.account_label)
        _require_token("quota_class", self.quota_class)
        _require_capability_set("capabilities", self.capabilities)
        _require_int_at_least("observed_at_ms", self.observed_at_ms, 1)
        _require_enum("occupancy", self.occupancy, OccupancyState)
        # Source AUTHORITY, not merely source shape: an evidence row is a
        # claim about WHO observed a fact, so it must pin the SAME owner
        # sets PlacementCandidateFact does (occupancy=RUNTIME_BINDING,
        # capacity=CAPACITY, closure=CAPACITY|EXECUTIVE_OS). Accepting any
        # SourceRef here would let a row attribute occupancy to Agent OS or
        # Wake, capacity to the Executive Inbox, or closure to Surface
        # Bindings — owners with no authority over those facts.
        _require_source_owner(
            self.occupancy_source, _OCCUPANCY_SOURCE_OWNERS, "occupancy_source"
        )
        _require_enum("capacity_state", self.capacity_state, CapacityState)
        _require_source_owner(
            self.capacity_source, _CAPACITY_SOURCE_OWNERS, "capacity_source"
        )
        _require_bool("host_source_closure_proven", self.host_source_closure_proven)
        _require_source_owner(
            self.closure_source, _CLOSURE_SOURCE_OWNERS, "closure_source"
        )
        _require_enum("effect_state", self.effect_state, EffectState)
        _require_enum("mode", self.mode, PlacementMode)
        _require_mode_shape(self.mode, self.creation_surface_accessible, self.session_creation_allowed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "provider": self.provider,
            "account_label": self.account_label,
            "quota_class": self.quota_class,
            "capabilities": sorted(self.capabilities),
            "observed_at_ms": self.observed_at_ms,
            "mode": self.mode.value,
            "occupancy": self.occupancy.value,
            "occupancy_source": _source_ref_dict(self.occupancy_source),
            "capacity_state": self.capacity_state.value,
            "capacity_source": _source_ref_dict(self.capacity_source),
            "host_source_closure_proven": self.host_source_closure_proven,
            "closure_source": _source_ref_dict(self.closure_source),
            "effect_state": self.effect_state.value,
            "creation_surface_accessible": self.creation_surface_accessible,
            "session_creation_allowed": self.session_creation_allowed,
        }


def _source_ref_dict(source: SourceRef) -> dict[str, Any]:
    """The four-field plain-dict serialization of a ``SourceRef`` — owner,
    ref, observed_at, freshness — and nothing else (no other SourceRef
    attribute exists to leak)."""
    return {
        "owner": source.owner.value,
        "ref": source.ref,
        "observed_at": source.observed_at,
        "freshness": source.freshness.value,
    }


def _demand_dict(demand: PlacementDemand) -> dict[str, Any]:
    """The closed, deterministically ordered serialization of the
    :class:`PlacementDemand` a decision was actually computed against.

    Provenance wave: without the demand on the wire, the capability /
    quota-class / provider / allowed-mode gates cannot be recomputed, so a
    consumer has to take the exclusion set on faith.
    """
    return {
        "required_capabilities": sorted(demand.required_capabilities),
        "quota_class": demand.quota_class,
        "provider": demand.provider,
        "allowed_modes": sorted(mode.value for mode in demand.allowed_modes),
    }


def _evidence_sort_key(row: dict[str, Any]) -> tuple:
    """Canonical, fully deterministic sort key for one evidence wire row.

    Sorting on ``worker_id`` alone is not enough: evidence deliberately
    keeps one row per evaluated candidate even when ``worker_id`` repeats
    (the duplicate-identity short-circuit still reports what was actually
    observed for each duplicate), so two rows can share a ``worker_id``.
    The full row content is folded into the key so ordering never depends
    on the input candidate list's own order — required for
    :func:`select_placement`'s permutation invariance.
    """
    def _source_key(source: dict[str, Any]) -> tuple[str, str, str, str]:
        return (
            source["owner"], source["ref"], source["observed_at"] or "", source["freshness"],
        )

    def _optional_bool_key(value: bool | None) -> tuple[bool, bool]:
        # None sorts before False sorts before True — a plain tuple
        # comparison would TypeError comparing None against bool directly,
        # so both are always mapped into a homogeneous (bool, bool) pair.
        return (value is not None, bool(value))

    return (
        row["worker_id"],
        row["provider"],
        row["account_label"],
        row["quota_class"],
        tuple(row["capabilities"]),
        row["observed_at_ms"],
        row["mode"],
        row["occupancy"],
        _source_key(row["occupancy_source"]),
        row["capacity_state"],
        _source_key(row["capacity_source"]),
        row["host_source_closure_proven"],
        _source_key(row["closure_source"]),
        row["effect_state"],
        _optional_bool_key(row["creation_surface_accessible"]),
        _optional_bool_key(row["session_creation_allowed"]),
    )


@dataclasses.dataclass(frozen=True, slots=True)
class PlacementSelectionDecision:
    """The outcome of one :func:`select_placement` call.

    ``selected`` — when present — is the EXISTING ``mastermind.
    executive_placement_snapshot/v1`` shape
    (:func:`control_plane.executive_orchestration_principal.
    build_placement_snapshot`), i.e. the Phase-B seam: this module hands off
    to the same snapshot contract the Executive runtime already speaks,
    without itself creating any Job/Attempt/Worker/RuntimeBinding or
    provider action.

    ``tie_breaker_used`` is RESERVED (addendum A): C1 has no tie-breaker
    authority, so this field is always ``None`` on every decision this
    module produces, and construction refuses any other value. It is kept
    (rather than removed) as a forward-compatible wire slot for a later
    wave's typed, source-owned ruling receipt.

    ``evidence`` (addendum B) is one immutable :class:`CandidateEvidence`
    row per candidate :func:`select_placement` was actually handed —
    including candidates the algorithm short-circuited past (a stale
    responsibility, or a duplicate ``worker_id``) — so a downstream
    consumer can audit exactly what this decision saw without re-deriving
    anything from a raw candidate list this module never returns.

    ``selected_mode`` (mode wave) is the winning candidate's own ``mode``
    and is present if-and-only-if ``state == "selected"`` — never inferred
    from ``selected`` itself, since the snapshot dict carries no mode field
    of its own.
    """

    responsibility_ref: str
    responsibility_freshness: Freshness
    demand: PlacementDemand
    state: SelectionState
    selected: Mapping[str, Any] | None
    selected_mode: PlacementMode | None
    tie_breaker_used: str | None
    tied_worker_ids: tuple[str, ...]
    exclusions: tuple[CandidateExclusion, ...]
    evaluated_candidates: int
    evidence: tuple[CandidateEvidence, ...]

    def __post_init__(self) -> None:
        _require_responsibility_ref(self.responsibility_ref)
        # Provenance wave: the responsibility gate fact and the demand are
        # INPUTS, carried so the decision can be recomputed from its own
        # wire form. `responsibility_freshness` is the only responsibility
        # attribute select_placement() actually reads besides the ref and
        # the (always "waiting_capacity") state.
        _require_enum("responsibility_freshness", self.responsibility_freshness, Freshness)
        if not isinstance(self.demand, PlacementDemand):
            raise TypeError("demand must be a PlacementDemand")
        _require_enum("state", self.state, SelectionState)
        if self.selected is not None and not isinstance(self.selected, Mapping):
            raise TypeError("selected must be a mapping or None")
        if self.selected_mode is not None:
            _require_enum("selected_mode", self.selected_mode, PlacementMode)
        if (self.selected_mode is not None) != (self.state is SelectionState.SELECTED):
            raise ValueError("selected_mode must be present iff state is 'selected'")
        if self.tie_breaker_used is not None:
            # Addendum A: RESERVED — no tie-breaker authority exists in C1.
            raise ValueError("tie_breaker_used is RESERVED and must be None in C1")
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
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, CandidateEvidence) for item in self.evidence
        ):
            raise TypeError("evidence must be a tuple of CandidateEvidence")
        if len(self.evidence) != self.evaluated_candidates:
            raise ValueError("evidence must carry exactly one row per evaluated candidate")

    def to_dict(self) -> dict[str, Any]:
        """Closed-key, deterministically ordered wire document.

        Nothing beyond these eleven keys is ever emitted — no source-ref
        fields beyond the four ``evidence`` names, no environment, no clock
        read — so ``json.dumps(self.to_dict(), sort_keys=True)`` is
        byte-identical across repeated calls with equivalent inputs
        regardless of candidate list order.
        """
        selected = dict(self.selected) if self.selected is not None else None
        exclusions = sorted(
            (
                {"worker_id": item.worker_id, "reason": item.reason.value}
                for item in self.exclusions
            ),
            key=lambda item: (item["worker_id"], item["reason"]),
        )
        evidence = sorted(
            (item.to_dict() for item in self.evidence),
            key=_evidence_sort_key,
        )
        return {
            "schema_version": SELECTION_SCHEMA,
            "responsibility_ref": self.responsibility_ref,
            "responsibility_freshness": self.responsibility_freshness.value,
            "demand": _demand_dict(self.demand),
            "state": self.state.value,
            "selected": selected,
            "selected_mode": self.selected_mode.value if self.selected_mode is not None else None,
            "tie_breaker_used": self.tie_breaker_used,
            "tied_worker_ids": sorted(self.tied_worker_ids),
            "exclusions": exclusions,
            "evaluated_candidates": self.evaluated_candidates,
            # Addendum B — constant discriminator: selection creates NO
            # capacity reservation, Job, Attempt, Worker, RuntimeBinding, or
            # provider effect of any kind. Always exactly False; a consumer
            # never has to infer non-commitment from a field's absence.
            "selection_is_commitment": False,
            "evidence": evidence,
        }


# ---------------------------------------------------------------------------
# wire-dict revalidation
# ---------------------------------------------------------------------------

_SELECTION_KEYS = frozenset({
    "schema_version", "responsibility_ref", "responsibility_freshness", "demand",
    "state", "selected", "selected_mode",
    "tie_breaker_used", "tied_worker_ids", "exclusions", "evaluated_candidates",
    "selection_is_commitment", "evidence",
})

_EXCLUSION_KEYS = frozenset({"worker_id", "reason"})

#: Fixed stand-ins for the two ResponsibilityFact attributes
#: select_placement() never reads (it uses only `responsibility_ref`,
#: `state`, and `source.freshness`). Constants — never caller data — so the
#: recomputation stays a pure function of the carried inputs.
_RECOMPUTED_RESPONSIBILITY_TITLE = "Recomputed placement selection provenance check."
_RECOMPUTED_RESPONSIBILITY_REF = "recomputed-provenance-check"
#: SourceRef refuses a null `observed_at` for current/stale freshness, so a
#: fixed sentinel stands in. It is never read: select_placement() consults
#: only `source.freshness`, and this ref never reaches any output.
_RECOMPUTED_RESPONSIBILITY_OBSERVED_AT = "1970-01-01T00:00:00Z"

_DEMAND_KEYS = frozenset({
    "required_capabilities", "quota_class", "provider", "allowed_modes",
})

_EVIDENCE_ROW_KEYS = frozenset({
    "worker_id", "provider", "account_label", "quota_class", "capabilities",
    "observed_at_ms",
    "mode", "occupancy", "occupancy_source", "capacity_state",
    "capacity_source", "host_source_closure_proven", "closure_source",
    "effect_state", "creation_surface_accessible", "session_creation_allowed",
})

_SOURCE_REF_KEYS = frozenset({"owner", "ref", "observed_at", "freshness"})


def _validate_source_ref_dict(
    value: Any, *, name: str, allowed: tuple[SourceOwner, ...]
) -> dict[str, Any]:
    """Closed-key revalidation of one ``evidence[*].*_source`` row — the
    plain four-field serialization :func:`_source_ref_dict` produces.
    Field-only error messages throughout — never the caller-supplied value.

    ``allowed`` is REQUIRED (review 5084378111 BLOCKER 2): being a
    *recognized* :class:`SourceOwner` is only a shape check. The wire must
    enforce the SAME authority the typed dataclasses do, or a fabricated
    document can re-attribute a fact to an owner that never had standing to
    observe it.
    """
    if not isinstance(value, Mapping) or set(value) != _SOURCE_REF_KEYS:
        raise ValueError(f"{name} must have exactly {sorted(_SOURCE_REF_KEYS)}")
    try:
        owner = SourceOwner(value["owner"])
    except ValueError as exc:
        raise ValueError(f"{name}.owner is not a recognized SourceOwner value") from exc
    if owner not in allowed:
        # Field-only, and the named owners are this module's OWN constants —
        # never the caller's value.
        raise ValueError(
            f"{name}.owner must be one of: "
            + ", ".join(item.value for item in allowed)
        )
    ref = _require_token(f"{name}.ref", value["ref"])
    observed_at = value["observed_at"]
    if observed_at is not None:
        _require_token(f"{name}.observed_at", observed_at)
    try:
        freshness = Freshness(value["freshness"])
    except ValueError as exc:
        raise ValueError(f"{name}.freshness is not a recognized Freshness value") from exc
    return {
        "owner": owner.value,
        "ref": ref,
        "observed_at": observed_at,
        "freshness": freshness.value,
    }


def _source_ref_from_dict(value: Mapping[str, Any]) -> SourceRef:
    """Rebuild the typed :class:`SourceRef` from an ALREADY-VALIDATED wire
    dict (see :func:`_validate_source_ref_dict`) so the decision can be
    recomputed from its own wire form."""
    return SourceRef(
        owner=SourceOwner(value["owner"]),
        ref=value["ref"],
        observed_at=value["observed_at"],
        freshness=Freshness(value["freshness"]),
    )


def _validate_demand_dict(value: Any) -> tuple[dict[str, Any], PlacementDemand]:
    """Closed-key revalidation of the carried :class:`PlacementDemand`,
    returning BOTH its canonical wire form and the typed object the
    recomputation needs. Field-only error messages."""
    if not isinstance(value, Mapping) or set(value) != _DEMAND_KEYS:
        raise ValueError(f"demand must have exactly {sorted(_DEMAND_KEYS)}")
    raw_capabilities = value["required_capabilities"]
    if not isinstance(raw_capabilities, list):
        raise TypeError("demand.required_capabilities must be a list")
    for item in raw_capabilities:
        _require_token("demand.required_capabilities item", item)
    if raw_capabilities != sorted(raw_capabilities):
        raise ValueError("demand.required_capabilities must be sorted")
    if len(set(raw_capabilities)) != len(raw_capabilities):
        raise ValueError("demand.required_capabilities must not repeat a capability")
    quota_class = _require_token("demand.quota_class", value["quota_class"])
    provider = value["provider"]
    if provider is not None:
        provider = _require_token("demand.provider", provider)
    raw_modes = value["allowed_modes"]
    if not isinstance(raw_modes, list) or not raw_modes:
        raise ValueError("demand.allowed_modes must be a non-empty list")
    modes = []
    for item in raw_modes:
        try:
            modes.append(PlacementMode(item))
        except ValueError as exc:
            raise ValueError("demand.allowed_modes contains an unrecognized PlacementMode") from exc
    if raw_modes != sorted(raw_modes):
        raise ValueError("demand.allowed_modes must be sorted")
    if len(set(raw_modes)) != len(raw_modes):
        raise ValueError("demand.allowed_modes must not repeat a mode")
    demand = PlacementDemand(
        required_capabilities=frozenset(raw_capabilities),
        quota_class=quota_class,
        provider=provider,
        allowed_modes=frozenset(modes),
    )
    return (
        {
            "required_capabilities": list(raw_capabilities),
            "quota_class": quota_class,
            "provider": provider,
            "allowed_modes": list(raw_modes),
        },
        demand,
    )


def _validate_evidence_row(value: Any) -> dict[str, Any]:
    """Closed-key revalidation of one ``evidence`` wire row (addendum B,
    mode wave). Enum-membership + strengthened-token (``_require_token``,
    which rejects ``"@"``/``"/"``) checks on every field; field-only error
    messages.
    """
    if not isinstance(value, Mapping) or set(value) != _EVIDENCE_ROW_KEYS:
        raise ValueError(f"evidence row must have exactly {sorted(_EVIDENCE_ROW_KEYS)}")
    worker_id = _require_token("evidence.worker_id", value["worker_id"])
    provider = _require_token("evidence.provider", value["provider"])
    account_label = _require_token("evidence.account_label", value["account_label"])
    quota_class = _require_token("evidence.quota_class", value["quota_class"])
    raw_capabilities = value["capabilities"]
    if not isinstance(raw_capabilities, list):
        raise TypeError("evidence.capabilities must be a list")
    for item in raw_capabilities:
        _require_token("evidence.capabilities item", item)
    if raw_capabilities != sorted(raw_capabilities):
        raise ValueError("evidence.capabilities must be sorted")
    if len(set(raw_capabilities)) != len(raw_capabilities):
        raise ValueError("evidence.capabilities must not repeat a capability")
    observed_at_ms = _require_int_at_least("evidence.observed_at_ms", value["observed_at_ms"], 1)
    try:
        mode = PlacementMode(value["mode"])
    except ValueError as exc:
        raise ValueError("evidence.mode is not a recognized PlacementMode value") from exc
    try:
        occupancy = OccupancyState(value["occupancy"])
    except ValueError as exc:
        raise ValueError("evidence.occupancy is not a recognized OccupancyState value") from exc
    occupancy_source = _validate_source_ref_dict(
        value["occupancy_source"], name="evidence.occupancy_source", allowed=_OCCUPANCY_SOURCE_OWNERS
    )
    try:
        capacity_state = CapacityState(value["capacity_state"])
    except ValueError as exc:
        raise ValueError("evidence.capacity_state is not a recognized CapacityState value") from exc
    capacity_source = _validate_source_ref_dict(
        value["capacity_source"], name="evidence.capacity_source", allowed=_CAPACITY_SOURCE_OWNERS
    )
    host_source_closure_proven = value["host_source_closure_proven"]
    if type(host_source_closure_proven) is not bool:
        raise TypeError("evidence.host_source_closure_proven must be bool")
    closure_source = _validate_source_ref_dict(
        value["closure_source"], name="evidence.closure_source", allowed=_CLOSURE_SOURCE_OWNERS
    )
    try:
        effect_state = EffectState(value["effect_state"])
    except ValueError as exc:
        raise ValueError("evidence.effect_state is not a recognized EffectState value") from exc
    creation_surface_accessible = value["creation_surface_accessible"]
    session_creation_allowed = value["session_creation_allowed"]
    if creation_surface_accessible is not None and type(creation_surface_accessible) is not bool:
        raise TypeError("evidence.creation_surface_accessible must be bool or null")
    if session_creation_allowed is not None and type(session_creation_allowed) is not bool:
        raise TypeError("evidence.session_creation_allowed must be bool or null")
    _require_mode_shape(mode, creation_surface_accessible, session_creation_allowed)
    return {
        "worker_id": worker_id,
        "provider": provider,
        "account_label": account_label,
        "quota_class": quota_class,
        "capabilities": list(raw_capabilities),
        "observed_at_ms": observed_at_ms,
        "mode": mode.value,
        "occupancy": occupancy.value,
        "occupancy_source": occupancy_source,
        "capacity_state": capacity_state.value,
        "capacity_source": capacity_source,
        "host_source_closure_proven": host_source_closure_proven,
        "closure_source": closure_source,
        "effect_state": effect_state.value,
        "creation_surface_accessible": creation_surface_accessible,
        "session_creation_allowed": session_creation_allowed,
    }


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
    ``state == "selected"``; ``tie_breaker_used`` must be ``null`` — C1 has
    no tie-breaker authority (addendum A), so any non-``null`` value is
    refused outright, regardless of state; ``tied_worker_ids`` is non-empty
    iff ``state == "tie_abstained"``, and then requires at least two ids;
    ``selection_is_commitment`` must be exactly ``false``; and
    ``evaluated_candidates`` equals ``len(evidence)`` exactly and is never
    smaller than ``len(exclusions)``.

    Beyond those, it enforces SOURCE-AUTHORITY BINDING over the decision's
    IDENTITY fields — the parts of a decision must refer to one another: a
    ``selected`` snapshot must correspond to exactly ONE ``evidence`` row
    for the same ``worker_id`` (zero rows means the decision never observed
    that worker; more than one is duplicate identity, which fails closed
    rather than being resolved by picking a row), ``selected_mode`` must
    equal that row's ``mode``, the selected worker may not simultaneously
    appear in ``exclusions``/``tied_worker_ids``, and every exclusion/tied
    id must be represented in ``evidence``.

    Finally — and this is what makes the gate an AUTHORITY gate rather than
    a shape gate — it enforces SELECTOR PROVENANCE. The wire carries the
    decision's own canonical input projection (the responsibility freshness
    actually gated on, the complete :class:`PlacementDemand`, and a
    complete :class:`PlacementCandidateFact` projection in every
    ``evidence`` row). Those inputs are rebuilt into typed facts and run
    through :func:`select_placement` — the ONE existing selector, called
    exactly once, never a second copy of the ranking or exclusion policy —
    and the supplied document must equal the recomputed projection exactly.

    So a document is accepted only if the canonical selector, given the
    inputs that document itself declares, produces precisely it. A forged
    ``state``, exclusion ``reason``, tie set, ineligible winner, or altered
    ``selected`` snapshot field cannot survive, because the recomputation
    never consults the forged half. Note what this does and does not mean:
    it authenticates the decision against its declared INPUTS. It cannot
    attest that those input facts are true of the world — that is the
    source owners' job, which is why owner authority is pinned separately
    above. No caller-supplied digest is trusted anywhere in this path.
    """
    if not isinstance(value, Mapping) or set(value) != _SELECTION_KEYS:
        # Review 5084378111 MAJOR 3: this previously rendered
        # `sorted(value)` (the CALLER's own key names) / `type(value).
        # __name__` into the message, and `compose_control_room()` appends
        # `str(exc)` verbatim to its Chairman-visible `degraded` list — so a
        # malformed document could echo a secret-shaped key straight onto
        # the Control Room. The message now names this module's OWN closed
        # key set and nothing else, matching every other closed-key error
        # here.
        raise ValueError(
            f"placement selection must have exactly {sorted(_SELECTION_KEYS)}"
        )

    if value["schema_version"] != SELECTION_SCHEMA:
        raise ValueError("unsupported placement selection schema")

    responsibility_ref = _require_responsibility_ref(value["responsibility_ref"])

    try:
        responsibility_freshness = Freshness(value["responsibility_freshness"])
    except ValueError as exc:
        raise ValueError("responsibility_freshness is not a recognized Freshness value") from exc

    demand_out, demand = _validate_demand_dict(value["demand"])

    try:
        state = SelectionState(value["state"])
    except ValueError as exc:
        raise ValueError("state is not a recognized SelectionState value") from exc

    selected_raw = value["selected"]
    if selected_raw is None:
        selected = None
    else:
        try:
            selected = validate_placement_snapshot(selected_raw)
        except (ValueError, TypeError) as exc:
            # Sibling of the top-level echo closed above, and the reason
            # fixing only that one was not enough: `selected` is an equally
            # caller-controlled sub-mapping, and
            # executive_orchestration_principal._closed() still renders
            # `sorted(value)` / `type(value).__name__` in ITS message.
            # OrchestrationPrincipalError subclasses ValueError, so
            # compose_control_room()'s `except (ValueError, TypeError)`
            # would append that text — caller key names included — verbatim
            # to its Chairman-visible `degraded` list. This module owns THIS
            # boundary: refuse with a constant, field-only message and never
            # relay the underlying text. (`from exc` keeps the chain for a
            # debugger; only `str()` of THIS error is ever rendered.)
            raise ValueError("selected is not a well-formed placement snapshot") from exc

    selected_mode_raw = value["selected_mode"]
    if selected_mode_raw is not None:
        try:
            selected_mode = PlacementMode(selected_mode_raw)
        except ValueError as exc:
            raise ValueError("selected_mode is not a recognized PlacementMode value") from exc
    else:
        selected_mode = None

    # Addendum A: RESERVED — no tie-breaker authority exists in C1. ANY
    # non-null value is refused, unconditionally, before any state check.
    tie_breaker_used = value["tie_breaker_used"]
    if tie_breaker_used is not None:
        raise ValueError("tie_breaker_used must be null (RESERVED — no tie-breaker authority in C1)")

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

    selection_is_commitment = value["selection_is_commitment"]
    if selection_is_commitment is not False:
        raise ValueError("selection_is_commitment must be exactly false")

    evidence_raw = value["evidence"]
    if not isinstance(evidence_raw, list):
        raise TypeError("evidence must be a list")
    evidence = [_validate_evidence_row(item) for item in evidence_raw]
    if evidence != sorted(evidence, key=_evidence_sort_key):
        raise ValueError("evidence must be sorted canonically (mirrors exclusions)")

    # --- cross-field invariants (reviewer M-3, addendum A/B, mode wave) -----
    if (selected is not None) != (state is SelectionState.SELECTED):
        raise ValueError("selected must be present iff state is 'selected'")
    if (selected_mode is not None) != (state is SelectionState.SELECTED):
        raise ValueError("selected_mode must be present iff state is 'selected'")
    if state is SelectionState.TIE_ABSTAINED:
        if len(tied_raw) < 2:
            raise ValueError("state 'tie_abstained' requires at least two tied_worker_ids")
    elif tied_raw:
        raise ValueError("tied_worker_ids must be empty unless state is 'tie_abstained'")
    if evaluated_candidates < len(exclusions):
        raise ValueError("evaluated_candidates must be >= the number of exclusions")
    if evaluated_candidates < len(tied_raw):
        raise ValueError("evaluated_candidates must be >= the number of tied_worker_ids")
    if evaluated_candidates != len(evidence):
        raise ValueError("evaluated_candidates must equal the number of evidence rows")

    # --- source-authority binding (review 5084378111 BLOCKER 1) -----------
    # Every rule above validates ONE field in isolation. Without the rules
    # below, `selected`, `selected_mode`, `exclusions`, `tied_worker_ids`
    # and `evidence` are five independently-valid islands, and a caller can
    # staple a separately valid snapshot for worker B onto evidence
    # gathered about worker A. `compose_control_room()` treats this
    # function as THE decision gate, so such a document would be displayed
    # as a real selection that `select_placement()` never produced.
    #
    # Each rule below is a property `select_placement()` already
    # guarantees by construction, so no genuine decision is narrowed:
    # duplicates always short-circuit to `reconciliation_required` (never
    # `selected`), the winner is drawn from the eligible set (so it is
    # never excluded), a tie leaves `selected` unset, and every exclusion/
    # tie id names a candidate that necessarily has an evidence row.
    known_worker_ids = frozenset(row["worker_id"] for row in evidence)

    if selected is not None:
        selected_worker_id = selected["worker_id"]
        matching = [
            row for row in evidence if row["worker_id"] == selected_worker_id
        ]
        if len(matching) != 1:
            # Zero rows: the decision never observed this worker at all.
            # More than one: duplicate identity — the exact case
            # select_placement() refuses to select on. Fail CLOSED; never
            # resolve the ambiguity by picking a row.
            raise ValueError(
                "selected must correspond to exactly one evidence row for the "
                "same worker_id"
            )
        # `selected_mode` is necessarily non-None here: the two iff checks
        # above tie BOTH `selected` and `selected_mode` to
        # `state == "selected"`, so the mode binding is unconditional.
        if matching[0]["mode"] != selected_mode.value:
            raise ValueError(
                "selected_mode must equal the selected worker's evidence mode"
            )
        if any(item["worker_id"] == selected_worker_id for item in exclusions):
            raise ValueError("selected worker_id must not also appear in exclusions")
        if selected_worker_id in tied_raw:
            raise ValueError("selected worker_id must not also appear in tied_worker_ids")

    for item in exclusions:
        if item["worker_id"] not in known_worker_ids:
            raise ValueError(
                "every exclusion worker_id must be represented in evidence"
            )
    for worker_id in tied_raw:
        if worker_id not in known_worker_ids:
            raise ValueError(
                "every tied worker_id must be represented in evidence"
            )

    # --- SELECTOR PROVENANCE (the decision-authenticity gate) -------------
    # Everything above is per-field shape and cross-field identity: it can
    # only ever catch symptoms. The authority question is whether THIS
    # document is a projection the ONE canonical selector would actually
    # emit from the inputs the document itself declares. So: rebuild the
    # typed inputs, run them through `select_placement()` — the single
    # existing owner, called exactly once, never a second reimplementation
    # of the ranking or exclusion policy — and require equality with the
    # supplied projection. A forged `state`, exclusion `reason`, tie set,
    # or selected snapshot field cannot survive, because the recomputation
    # does not consult the forged half at all.
    #
    # This is NOT a digest supplied by the same untrusted document: nothing
    # here trusts a caller-provided hash. The inputs are re-derived into
    # typed facts (each re-running its own dataclass validation) and the
    # OUTPUT is recomputed from them.
    normalized = {
        "schema_version": SELECTION_SCHEMA,
        "responsibility_ref": responsibility_ref,
        "responsibility_freshness": responsibility_freshness.value,
        "demand": demand_out,
        "state": state.value,
        "selected": selected,
        "selected_mode": selected_mode.value if selected_mode is not None else None,
        "tie_breaker_used": tie_breaker_used,
        "tied_worker_ids": list(tied_raw),
        "exclusions": exclusions,
        "evaluated_candidates": evaluated_candidates,
        "selection_is_commitment": False,
        "evidence": evidence,
    }

    try:
        candidates = tuple(
            PlacementCandidateFact(
                worker_id=row["worker_id"],
                provider=row["provider"],
                account_label=row["account_label"],
                quota_class=row["quota_class"],
                capabilities=frozenset(row["capabilities"]),
                observed_at_ms=row["observed_at_ms"],
                occupancy=OccupancyState(row["occupancy"]),
                occupancy_source=_source_ref_from_dict(row["occupancy_source"]),
                capacity_state=CapacityState(row["capacity_state"]),
                capacity_source=_source_ref_from_dict(row["capacity_source"]),
                host_source_closure_proven=row["host_source_closure_proven"],
                closure_source=_source_ref_from_dict(row["closure_source"]),
                effect_state=EffectState(row["effect_state"]),
                mode=PlacementMode(row["mode"]),
                creation_surface_accessible=row["creation_surface_accessible"],
                session_creation_allowed=row["session_creation_allowed"],
            )
            for row in evidence
        )
        recomputed = select_placement(
            responsibility=ResponsibilityFact(
                responsibility_ref=responsibility_ref,
                # Neither of these reaches the decision: select_placement()
                # reads only `responsibility_ref`, `state`, and
                # `source.freshness`. They are fixed constants so the
                # recomputation is a pure function of the carried inputs.
                title=_RECOMPUTED_RESPONSIBILITY_TITLE,
                accountable_seat=Seat.COO,
                state="waiting_capacity",
                root_job_id=None,
                source=SourceRef(
                    owner=SourceOwner.AGENT_OS,
                    ref=_RECOMPUTED_RESPONSIBILITY_REF,
                    observed_at=_RECOMPUTED_RESPONSIBILITY_OBSERVED_AT,
                    freshness=responsibility_freshness,
                ),
            ),
            demand=demand,
            candidates=candidates,
        )
    except (ValueError, TypeError) as exc:
        # Field-only: never relay the underlying text, which may quote a
        # caller-supplied value.
        raise ValueError(
            "decision inputs do not form a valid selector invocation"
        ) from exc

    if recomputed.to_dict() != normalized:
        raise ValueError(
            "decision does not match the result of recomputing it from its own "
            "declared inputs"
        )

    return normalized


# ---------------------------------------------------------------------------
# the selector
# ---------------------------------------------------------------------------

def _first_exclusion_reason(
    candidate: PlacementCandidateFact, demand: PlacementDemand
) -> ExclusionReason | None:
    """The first failing gate, or ``None`` if the candidate survives every
    gate (i.e. is eligible).

    Reviewer-ratified order (M-4), extended by the mode wave: this is a
    REFINEMENT of :data:`_AGGREGATE_PRECEDENCE` at the per-candidate level
    — reasons that would win the aggregate (``CONTRADICTORY_BINDING``,
    then ``EFFECT_UNKNOWN``, then the stale/unknown-freshness/capacity-
    unknown family, then ``OCCUPIED``/``BOUND_ELSEWHERE``) are checked
    first, in that same order, and only THEN the reasons the aggregate
    deliberately never elevates on their own (``HOST_SOURCE_UNPROVEN``,
    then the mode-wave fresh-lane gates ``CREATION_SURFACE_INACCESSIBLE``/
    ``SESSION_CREATION_DISALLOWED``, then ``MODE_NOT_ALLOWED``, then the
    three mismatches). A candidate failing multiple gates always reports
    the highest-precedence one — e.g. a candidate that is both ``OCCUPIED``
    and has a stale capacity fact reports ``STALE_CAPACITY_FACT``, never
    ``OCCUPIED``; a candidate whose mode is not allowed AND whose fresh
    lane has no accessible creation surface reports
    ``CREATION_SURFACE_INACCESSIBLE``, never ``MODE_NOT_ALLOWED``.

    Ruling (m-6): a ``CONTRADICTORY`` or ``EFFECT_UNKNOWN`` candidate is
    excluded PER-CANDIDATE only — it never poisons a clean sibling's
    eligibility, and a clean sibling may still be ``SELECTED`` in the same
    call. Only a repeated ``worker_id`` (duplicate identity) is globally
    fatal to the whole decision; see :func:`select_placement` step 3.

    Mode wave: ``CREATION_SURFACE_INACCESSIBLE``/``SESSION_CREATION_
    DISALLOWED`` apply ONLY to a fresh-lane candidate (``mode ==
    NEW_SESSION_MATERIALIZATION``) — a reuse candidate's creation bools are
    always ``None`` by construction and never trigger either gate.
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
    if candidate.mode is PlacementMode.NEW_SESSION_MATERIALIZATION and candidate.creation_surface_accessible is not True:
        return ExclusionReason.CREATION_SURFACE_INACCESSIBLE
    if candidate.mode is PlacementMode.NEW_SESSION_MATERIALIZATION and candidate.session_creation_allowed is not True:
        return ExclusionReason.SESSION_CREATION_DISALLOWED
    if candidate.mode not in demand.allowed_modes:
        return ExclusionReason.MODE_NOT_ALLOWED
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


def _evidence_from_candidates(
    candidates: Sequence[PlacementCandidateFact],
) -> tuple[CandidateEvidence, ...]:
    """One :class:`CandidateEvidence` row per element of ``candidates`` — the
    FULL, un-deduplicated tuple :func:`select_placement` was handed, so a
    duplicate ``worker_id`` still yields one row per occurrence.
    """
    return tuple(
        CandidateEvidence(
            worker_id=c.worker_id,
            provider=c.provider,
            account_label=c.account_label,
            quota_class=c.quota_class,
            capabilities=c.capabilities,
            observed_at_ms=c.observed_at_ms,
            occupancy=c.occupancy,
            occupancy_source=c.occupancy_source,
            capacity_state=c.capacity_state,
            capacity_source=c.capacity_source,
            host_source_closure_proven=c.host_source_closure_proven,
            closure_source=c.closure_source,
            effect_state=c.effect_state,
            mode=c.mode,
            creation_surface_accessible=c.creation_surface_accessible,
            session_creation_allowed=c.session_creation_allowed,
        )
        for c in candidates
    )


def _decision(
    responsibility_ref: str,
    state: SelectionState,
    *,
    responsibility_freshness: Freshness,
    demand: PlacementDemand,
    selected: Mapping[str, Any] | None = None,
    selected_mode: PlacementMode | None = None,
    tied_worker_ids: tuple[str, ...] = (),
    exclusions: tuple[CandidateExclusion, ...] = (),
    evaluated_candidates: int,
    evidence: tuple[CandidateEvidence, ...],
) -> PlacementSelectionDecision:
    return PlacementSelectionDecision(
        responsibility_ref=responsibility_ref,
        responsibility_freshness=responsibility_freshness,
        demand=demand,
        state=state,
        selected=selected,
        selected_mode=selected_mode,
        # Addendum A: RESERVED, always None — no tie-breaker authority
        # exists in C1. select_placement() never sets this to anything else.
        tie_breaker_used=None,
        tied_worker_ids=tied_worker_ids,
        exclusions=exclusions,
        evaluated_candidates=evaluated_candidates,
        evidence=evidence,
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
       ``responsibility.state != "waiting_capacity"``; a
       ``responsibility_ref`` that is legal per
       :mod:`control_plane.executive_steward` but violates THIS module's
       stricter token law (it flows onto the Chairman wire); ``accepted_tie_breaker``
       not ``None`` (addendum A: C1 has NO tie-breaker authority — a later
       wave may add a typed, source-owned ruling receipt binding the exact
       candidate-set digest, but until then this parameter accepts only
       ``None``); any element of ``candidates`` not a
       :class:`PlacementCandidateFact`.
    2. ``responsibility.source.freshness`` not ``CURRENT`` -> ``STALE_EVIDENCE``
       (no selection, no exclusions, ``evaluated_candidates=len(candidates)``,
       ``evidence`` still populated from the full candidate tuple).
    3. Any repeated ``worker_id`` -> ``RECONCILIATION_REQUIRED``; every
       duplicated id gets exactly one ``DUPLICATE_IDENTITY`` exclusion
       (``evidence`` still populated from the full, un-deduplicated tuple —
       one row per occurrence, including duplicates).
    4. Candidates are evaluated in canonical ``worker_id``-sorted order. Per
       candidate, the reason is the first failing gate in a FIXED order
       that REFINES :data:`_AGGREGATE_PRECEDENCE` (see
       :func:`_first_exclusion_reason`): ``CONTRADICTORY`` occupancy, then
       ``EFFECT_UNKNOWN``, then occupancy-source staleness/unknown-freshness,
       then capacity-source staleness/unknown-freshness, then
       ``capacity_state`` ``UNKNOWN``, then ``OCCUPIED``, then
       ``BOUND_ELSEWHERE``, then (ratified: these deliberately fall through
       to ``NO_ELIGIBLE_CANDIDATE`` at the aggregate step rather than
       elevating their own state) unproven host-source closure, then —
       mode wave — a fresh-lane candidate (``mode ==
       NEW_SESSION_MATERIALIZATION``) whose ``creation_surface_accessible``
       is not ``True`` (``CREATION_SURFACE_INACCESSIBLE``), then whose
       ``session_creation_allowed`` is not ``True``
       (``SESSION_CREATION_DISALLOWED``), then any candidate whose ``mode``
       is not in ``demand.allowed_modes`` (``MODE_NOT_ALLOWED``), then a
       capability/quota-class/provider mismatch. A candidate failing no
       gate is eligible; a ``CONTRADICTORY``/``EFFECT_UNKNOWN`` exclusion is
       PER-CANDIDATE only — it never excludes a clean sibling, which may
       still be ``SELECTED`` in the same call (ruling m-6). An occupied
       EXISTING_SESSION_REUSE candidate never erases a separately proven
       NEW_SESSION_MATERIALIZATION lane in the same call, and vice versa —
       each candidate is gated on its OWN facts only.
    5. Eligible non-empty: rank ONLY by ``capacity_state`` (``AVAILABLE``
       before ``DEGRADED``) — ``mode`` NEVER ranks, so a reuse candidate
       and a fresh candidate at the same ``capacity_state`` tie exactly
       like two same-mode candidates would; take the min-rank set. Exactly
       one winner -> ``SELECTED`` (``selected_mode`` set to the winner's
       own ``mode``). More than one -> ``TIE_ABSTAINED`` ALWAYS (addendum
       A: C1 has no tie-breaker authority to resolve an exact top tie —
       every tied id lands in ``tied_worker_ids``, ``selected``/
       ``selected_mode`` stay ``None``, and ``tie_breaker_used`` stays its
       RESERVED ``None``).
    6. Eligible empty: aggregate state by the CLOSED, documented precedence
       over the exclusion reasons actually present — see
       :data:`_AGGREGATE_PRECEDENCE` — falling through to
       ``NO_ELIGIBLE_CANDIDATE`` when only mismatch/``HOST_SOURCE_UNPROVEN``/
       mode-wave (``MODE_NOT_ALLOWED``/``CREATION_SURFACE_INACCESSIBLE``/
       ``SESSION_CREATION_DISALLOWED``) reasons are present (deliberate,
       ratified — see :data:`_AGGREGATE_PRECEDENCE`), or when there were
       zero candidates at all.

    ``evidence`` (addendum B) is populated in EVERY return path — including
    both short-circuits above — from the FULL, un-deduplicated candidate
    tuple exactly as received; :meth:`PlacementSelectionDecision.to_dict`
    also emits the constant ``selection_is_commitment: false``
    discriminator on every decision — choosing a fresh lane creates
    nothing; selection stays inert regardless of mode.

    No clock, no environment, no I/O, no randomness: ranking and every
    aggregate decision are functions of the typed facts alone.
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
    # Exact-head review N-1: this module's `_require_responsibility_ref` is
    # deliberately STRICTER than executive_steward's `_valid_responsibility_ref`
    # (which admits '@', '/', backslash and control characters), because the
    # ref flows onto the Chairman wire. A ResponsibilityFact that is legal per
    # the steward is therefore a legal INPUT here that this module cannot
    # represent — so it must be refused in step 1 alongside the other input
    # refusals, not late from PlacementSelectionDecision.__post_init__ after
    # the whole algorithm has run. That late raise is exactly the defect class
    # the M-1/M-2 ratchet above forbids ("so select_placement can never raise
    # past this point").
    _require_responsibility_ref(responsibility.responsibility_ref)
    if accepted_tie_breaker is not None:
        # Addendum A: no tie-breaker authority exists in C1. See the
        # docstring above for the forward-compatible plan; the error text
        # itself deliberately says only this much.
        raise ValueError("accepted_tie_breaker: no tie-breaker authority exists in C1")

    responsibility_ref = responsibility.responsibility_ref
    evaluated_candidates = len(candidate_tuple)
    # Canonical worker_id-sorted order, computed ONCE up front — this is
    # what makes select_placement's OWN dataclass output (not just its
    # to_dict() wire form) permutation-invariant: evidence is built from
    # THIS order below, not the raw input order, exactly like exclusions
    # already were.
    ordered = sorted(candidate_tuple, key=lambda c: c.worker_id)
    # Addendum B: built ONCE, from the full un-deduplicated candidate set
    # (in canonical order), and reused on every return path below
    # (including both short-circuits) — evidence is a record of what was
    # observed, never a filtered or deduplicated view.
    evidence = _evidence_from_candidates(ordered)

    if responsibility.source.freshness is not Freshness.CURRENT:
        return _decision(
            responsibility_ref, SelectionState.STALE_EVIDENCE,
            responsibility_freshness=responsibility.source.freshness, demand=demand,
            evaluated_candidates=evaluated_candidates, evidence=evidence,
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
            responsibility_freshness=responsibility.source.freshness, demand=demand,
            exclusions=exclusions, evaluated_candidates=evaluated_candidates,
            evidence=evidence,
        )

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
            responsibility_freshness=responsibility.source.freshness, demand=demand,
                selected=selected, selected_mode=winner.mode, exclusions=exclusions,
                evaluated_candidates=evaluated_candidates, evidence=evidence,
            )

        # Addendum A: an exact top tie ALWAYS abstains — C1 has no
        # tie-breaker authority to resolve it, no matter how the caller
        # invoked select_placement (accepted_tie_breaker was already
        # refused above unless None).
        tied_worker_ids = tuple(sorted(c.worker_id for c in winners))
        return _decision(
            responsibility_ref, SelectionState.TIE_ABSTAINED,
            responsibility_freshness=responsibility.source.freshness, demand=demand,
            tied_worker_ids=tied_worker_ids, exclusions=exclusions,
            evaluated_candidates=evaluated_candidates, evidence=evidence,
        )

    reasons_present = frozenset(item.reason for item in exclusions)
    state = _aggregate_state(reasons_present)
    return _decision(
        responsibility_ref, state, exclusions=exclusions,
            responsibility_freshness=responsibility.source.freshness, demand=demand,
        evaluated_candidates=evaluated_candidates, evidence=evidence,
    )
