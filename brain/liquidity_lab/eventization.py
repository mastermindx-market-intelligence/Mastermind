"""Causal eventization over externally computed W-LIQ.1 state points."""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping

import numpy as np

from brain.liquidity_lab.contracts import ContractError, ShockRecord, SourceStateRef, build_shock_record, canonical_hash

EVENTIZATION_DEFINITION_VERSION = "glt_eventization.v1"
BUSINESS_DAY_CALENDAR = "numpy_busday_mon_fri_no_holidays"
TRUSTED_FRESHNESS = frozenset({"fresh"})

SHOCK_CLASSES = (
    "observed_state_change",
    "forecast_innovation",
    "policy_announcement_surprise",
    "identified_intervention",
)
EVENTIZE_SHOCK_CLASS = "observed_state_change"
NOT_IDENTIFIED = "NOT_IDENTIFIED"
IDENTIFIED = "IDENTIFIED"


def _business_days(start: date, end: date) -> int:
    if end < start:
        raise ContractError("state points must be time ordered")
    return int(np.busday_count(start.isoformat(), end.isoformat()))


@dataclass(frozen=True, slots=True)
class EventizationPolicy:
    """Pre-registered episode policy supplied by the quant program.

    There is intentionally no production default.  Sol must ratify thresholds
    after W-LIQ.1 freezes its field semantics; a test or research run must pass a
    policy explicitly and record it with the model version.
    """

    material_abs_z: float
    reset_abs_z: float
    min_coverage: float
    min_confidence: float
    max_observation_gap_bdays: int
    refractory_bdays: int

    def __post_init__(self) -> None:
        if self.material_abs_z <= 0:
            raise ContractError("material_abs_z must be positive")
        if not 0 <= self.reset_abs_z < self.material_abs_z:
            raise ContractError("reset_abs_z must be in [0, material_abs_z)")
        if not 0 <= self.min_coverage <= 1:
            raise ContractError("min_coverage must be in [0, 1]")
        if not 0 <= self.min_confidence <= 1:
            raise ContractError("min_confidence must be in [0, 1]")
        if self.max_observation_gap_bdays < 1:
            raise ContractError("max_observation_gap_bdays must be positive")
        if self.refractory_bdays < 0:
            raise ContractError("refractory_bdays may not be negative")


_RATIO_FIELDS = ("material_abs_z", "reset_abs_z", "min_coverage", "min_confidence")
_BDAY_FIELDS = ("max_observation_gap_bdays", "refractory_bdays")


def event_definition(policy: EventizationPolicy) -> dict[str, Any]:
    """Return the frozen, outcome-free definition that ``eventize`` applies.

    Every threshold plus the definition version, business-day calendar and
    trusted-freshness set.  A change to any of them is a new registered research
    choice with a new ``event_definition_id``; nothing here reads data.
    """

    for name in _RATIO_FIELDS:
        value = getattr(policy, name)
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise ContractError(f"{name} must be a real number, not {type(value).__name__}")
    for name in _BDAY_FIELDS:
        value = getattr(policy, name)
        # int() would truncate 2.5 to 2 while eventize compares the raw value, so two
        # behaviourally different policies would share one id; bool would hash as 0/1.
        if isinstance(value, bool) or not isinstance(value, numbers.Integral):
            raise ContractError(f"{name} must be an integer business-day count, not {type(value).__name__}")
    numeric = {name: float(getattr(policy, name)) for name in _RATIO_FIELDS}
    if not all(math.isfinite(value) for value in numeric.values()):
        raise ContractError("event definition thresholds must be finite")
    return {
        "definition_version": EVENTIZATION_DEFINITION_VERSION,
        "business_day_calendar": BUSINESS_DAY_CALENDAR,
        "trusted_freshness": sorted(TRUSTED_FRESHNESS),
        **numeric,
        "max_observation_gap_bdays": int(policy.max_observation_gap_bdays),
        "refractory_bdays": int(policy.refractory_bdays),
    }


def event_definition_id(policy: EventizationPolicy) -> str:
    """Canonical id of the event definition; independent of any outcome data."""

    return "evdef_" + canonical_hash(event_definition(policy))


def _observable(point: SourceStateRef, policy: EventizationPolicy) -> bool:
    """Only trustworthy observations can open, reset, or bridge an episode."""

    return (
        point.freshness in TRUSTED_FRESHNESS
        and point.coverage >= policy.min_coverage
        and point.confidence >= policy.min_confidence
    )


def eventize(
    points: Iterable[SourceStateRef], policy: EventizationPolicy
) -> list[ShockRecord]:
    """Return immutable first-detection episodes from causal state observations.

    A material point opens one episode per state family.  Continued material
    points remain part of that episode and cannot rewrite its first-detection
    record.  A sign flip, an explicit reset, or a long observation gap closes the
    episode.  The refractory window suppresses rapid same-direction remints.

    The function reads only values already computed by W-LIQ.1.  It performs no
    transforms, z-scoring, orthogonalisation, source classification, or filling.
    """

    ordered = sorted(points, key=lambda point: (point.known_at, point.state_family))
    # A repeated observation is replay, not a choice of whichever row arrived
    # first. Validate before admission so even a degraded conflicting copy
    # cannot silently select the trusted row. Corrections belong to amendments.
    unique: list[SourceStateRef] = []
    for point in ordered:
        if unique and (point.known_at, point.state_family) == (
            unique[-1].known_at, unique[-1].state_family
        ):
            if point.to_dict() != unique[-1].to_dict():
                raise ContractError("conflicting same-clock observation; use the amendment path")
            continue
        unique.append(point)
    active: dict[str, SourceStateRef] = {}
    last_seen: dict[str, SourceStateRef] = {}
    last_emitted: dict[tuple[str, int], SourceStateRef] = {}
    emitted: list[ShockRecord] = []

    for point in unique:
        if not _observable(point, policy):
            # Missing/stale/low-quality evidence proves neither a reset nor a
            # continuous observation history. Leave both clocks untouched.
            continue
        family = point.state_family
        previous = last_seen.get(family)
        if previous is not None:
            gap = _business_days(previous.known_at.date(), point.known_at.date())
            if gap > policy.max_observation_gap_bdays:
                active.pop(family, None)
        last_seen[family] = point

        current = active.get(family)
        if abs(point.magnitude_z) <= policy.reset_abs_z:
            active.pop(family, None)
            continue
        if abs(point.magnitude_z) < policy.material_abs_z:
            continue
        if current is not None and current.direction == point.direction:
            continue

        active.pop(family, None)
        prior_same_direction = last_emitted.get((family, point.direction))
        if prior_same_direction is not None:
            separation = _business_days(
                prior_same_direction.known_at.date(), point.known_at.date()
            )
            if separation < policy.refractory_bdays:
                active[family] = point
                continue

        emitted.append(build_shock_record(point))
        active[family] = point
        last_emitted[(family, point.direction)] = point

    return emitted


@dataclass(frozen=True, slots=True)
class ShockLabel:
    """Shock-class label carried separately from the immutable shock record.

    The label is never written into ``ShockRecord`` or a registry payload.  An
    eventized threshold crossing is an observed state change; it is not an
    exogenous shock and carries no identification.
    """

    shock_id: str
    shock_class: str
    identification_status: str
    identification_receipt: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "shock_id": self.shock_id,
            "shock_class": self.shock_class,
            "identification_status": self.identification_status,
            "identification_receipt": None
            if self.identification_receipt is None
            else dict(self.identification_receipt),
        }


def label_shock(
    shock: ShockRecord,
    *,
    shock_class: str = EVENTIZE_SHOCK_CLASS,
    identification_receipt: Mapping[str, Any] | None = None,
) -> ShockLabel:
    """Attach a §5 shock-class label; identification needs an explicit receipt.

    Defaults to ``observed_state_change`` / ``NOT_IDENTIFIED``.  Only
    ``identified_intervention`` may carry a receipt, and only a receipt naming a
    ``receipt_id`` and ``method`` with ``weak_instrument`` explicitly ``False``
    yields ``IDENTIFIED``.  A weak instrument is not identified.
    """

    if shock_class not in SHOCK_CLASSES:
        raise ContractError(f"unknown shock_class: {shock_class!r}")
    if shock_class != "identified_intervention":
        if identification_receipt is not None:
            raise ContractError("only identified_intervention may carry an identification receipt")
        return ShockLabel(shock.shock_id, shock_class, NOT_IDENTIFIED, None)
    if identification_receipt is None:
        raise ContractError("identified_intervention requires an explicit identification receipt")
    receipt = dict(identification_receipt)
    if not str(receipt.get("receipt_id") or "").strip() or not str(receipt.get("method") or "").strip():
        raise ContractError("identification receipt must name receipt_id and method")
    if receipt.get("weak_instrument") is not False:
        raise ContractError("weak or undeclared instrument strength is NOT_IDENTIFIED")
    return ShockLabel(shock.shock_id, shock_class, IDENTIFIED, receipt)
