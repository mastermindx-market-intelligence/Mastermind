"""Causal eventization over externally computed W-LIQ.1 state points."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import numpy as np

from brain.liquidity_lab.contracts import ContractError, ShockRecord, SourceStateRef, build_shock_record


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


def _eligible(point: SourceStateRef, policy: EventizationPolicy) -> bool:
    """Stale/unknown or low-coverage input cannot mint a supportive episode."""

    return (
        point.freshness == "fresh"
        and point.coverage >= policy.min_coverage
        and point.confidence >= policy.min_confidence
        and abs(point.magnitude_z) >= policy.material_abs_z
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
    active: dict[str, SourceStateRef] = {}
    last_seen: dict[str, SourceStateRef] = {}
    last_emitted: dict[tuple[str, int], SourceStateRef] = {}
    emitted: list[ShockRecord] = []

    for point in ordered:
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
        if not _eligible(point, policy):
            # Missing/stale evidence neither creates a shock nor proves a reset.
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
