"""Causal forward-return panels and hierarchical response-curve estimates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Mapping, Protocol, Sequence

import numpy as np
import pandas as pd

from brain.liquidity_lab.contracts import (
    HORIZONS_BDAYS,
    TARGET_BY_ID,
    ContractError,
    ShockRecord,
)


@dataclass(frozen=True, slots=True)
class ForwardReturnObservation:
    shock_id: str
    first_detected: datetime
    target_id: str
    asset_class: str
    hierarchy_parent: str
    shock_family: str
    shock_type: str
    horizon_bdays: int
    anchor_session: date
    exit_session: date
    forward_return: float
    conditions: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ResponseCurveCell:
    target_id: str
    shock_family: str
    condition_bucket: str
    horizon_bdays: int
    sample_n: int
    effective_n: int
    raw_mean: float | None
    shrunk_mean: float | None
    interval_low: float | None
    interval_high: float | None
    prior_mean: float | None
    prior_effective_n: int
    evidence_state: str


class ResponseCurveEstimator(Protocol):
    """Interface for an attributable full-curve estimator."""

    model_version: str

    def fit(
        self,
        observations: Sequence[ForwardReturnObservation],
        *,
        condition_keys: Sequence[str] = (),
    ) -> list[ResponseCurveCell]: ...


def _clean_business_series(raw: pd.Series, *, as_of: date) -> pd.Series:
    """Normalize a pre-sampled business-session close series without filling."""

    if not isinstance(raw, pd.Series):
        raise ContractError("each target price input must be a pandas Series")
    series = raw.copy()
    try:
        index = pd.to_datetime(series.index, utc=True).tz_convert(None).normalize()
    except Exception as exc:  # noqa: BLE001
        raise ContractError("price index must be timestamp-like") from exc
    if index.isna().any():
        raise ContractError("price index contains an invalid timestamp")
    if index.duplicated().any():
        raise ContractError("price input must contain one close per business session")
    series.index = index
    converted = pd.to_numeric(series, errors="coerce")
    if (series.notna() & converted.isna()).any():
        raise ContractError("price input contains a non-numeric close")
    if (converted.dropna() <= 0).any():
        raise ContractError("price closes must be positive")
    series = converted.sort_index()
    cutoff = pd.Timestamp(as_of)
    series = series[(series.index <= cutoff) & series.notna() & (series > 0)]
    return series.astype(float)


def build_forward_return_panel(
    shocks: Iterable[ShockRecord],
    prices: Mapping[str, pd.Series],
    *,
    as_of: date,
    horizons: Sequence[int] = HORIZONS_BDAYS,
) -> list[ForwardReturnObservation]:
    """Build resolved outcomes using only closes available by ``as_of``.

    The anchor is the first supplied business-session close *strictly after* the
    first-detection calendar date.  This conservative rule avoids using a same-day
    close that may not have existed when an intraday/after-close shock was known.
    The caller must supply business-session sampled prices; this function never
    forward-fills different calendars or reaches beyond ``as_of``.
    """

    unknown_horizons = sorted(set(horizons) - set(HORIZONS_BDAYS))
    if unknown_horizons:
        raise ContractError(f"unregistered horizons: {unknown_horizons}")
    clean: dict[str, pd.Series] = {}
    for target_id, series in prices.items():
        if target_id not in TARGET_BY_ID:
            raise ContractError(f"unregistered target price series: {target_id}")
        clean[target_id] = _clean_business_series(series, as_of=as_of)

    output: list[ForwardReturnObservation] = []
    for shock in sorted(shocks, key=lambda item: (item.first_detected, item.shock_id)):
        if shock.first_detected.date() > as_of:
            continue
        detection_day = pd.Timestamp(shock.first_detected.date())
        for target_id, series in clean.items():
            post = series[series.index > detection_day]
            if post.empty:
                continue
            target = TARGET_BY_ID[target_id]
            anchor_price = float(post.iloc[0])
            for horizon in sorted(set(int(value) for value in horizons)):
                if len(post) <= horizon:
                    continue
                exit_price = float(post.iloc[horizon])
                output.append(
                    ForwardReturnObservation(
                        shock_id=shock.shock_id,
                        first_detected=shock.first_detected,
                        target_id=target_id,
                        asset_class=target.asset_class,
                        hierarchy_parent=target.hierarchy_parent,
                        shock_family=shock.shock_family,
                        shock_type=shock.shock_type,
                        horizon_bdays=horizon,
                        anchor_session=post.index[0].date(),
                        exit_session=post.index[horizon].date(),
                        forward_return=exit_price / anchor_price - 1.0,
                        conditions=shock.conditions,
                    )
                )
    return output


def condition_bucket(row: ForwardReturnObservation, keys: Sequence[str]) -> str:
    if not keys:
        return "all"
    values = []
    for key in keys:
        value = row.conditions.get(key, "unknown")
        values.append(f"{key}={value}")
    return "|".join(values)


def _sample_values(rows: Sequence[ForwardReturnObservation]) -> tuple[np.ndarray, int]:
    by_shock: dict[str, list[ForwardReturnObservation]] = {}
    for row in sorted(rows, key=lambda item: (item.first_detected, item.shock_id)):
        by_shock.setdefault(row.shock_id, []).append(row)
    # A broad hierarchical prior may include multiple peer targets for one
    # shock.  Average peers within the episode before counting honest N; never
    # let cross-sectional breadth manufacture independent shock observations.
    unique = [
        (
            min(row.anchor_session for row in group),
            max(row.exit_session for row in group),
            float(np.mean([row.forward_return for row in group])),
        )
        for group in by_shock.values()
    ]
    values: list[float] = []
    last_exit: date | None = None
    for anchor_session, exit_session, event_return in sorted(unique):
        # Adjacent intervals may share the boundary price but no return increment;
        # that is non-overlap.  Cross-target peer priors use the widest interval
        # in an episode, so breadth cannot increase effective N.
        if last_exit is None or anchor_session >= last_exit:
            values.append(event_return)
            last_exit = exit_session
    return np.asarray(values, dtype=float), len(values)


class HierarchicalMeanCurveEstimator:
    """Shrunk event-response means with full horizons and honest thin cells.

    Narrow targets borrow from *other targets* in the same asset class and shock
    family.  No cell is labeled beyond ``discovered`` and cells below
    ``min_effective_n`` expose no estimate.  The estimator is descriptive research
    machinery, not a promotion rule.
    """

    def __init__(
        self,
        *,
        model_version: str,
        prior_strength: int,
        min_effective_n: int,
    ) -> None:
        if not model_version:
            raise ContractError("model_version is required")
        if prior_strength < 0:
            raise ContractError("prior_strength may not be negative")
        if min_effective_n < 2:
            raise ContractError("min_effective_n must be at least 2")
        self.model_version = model_version
        self.prior_strength = int(prior_strength)
        self.min_effective_n = int(min_effective_n)

    def fit(
        self,
        observations: Sequence[ForwardReturnObservation],
        *,
        condition_keys: Sequence[str] = (),
    ) -> list[ResponseCurveCell]:
        groups: dict[tuple[str, str, str, int], list[ForwardReturnObservation]] = {}
        curve_axes: set[tuple[str, str, str]] = set()
        for row in observations:
            if row.target_id not in TARGET_BY_ID:
                raise ContractError(f"unregistered target observation: {row.target_id}")
            if row.horizon_bdays not in HORIZONS_BDAYS:
                raise ContractError("observation horizon is not precommitted")
            key = (
                row.target_id,
                row.shock_family,
                condition_bucket(row, condition_keys),
                row.horizon_bdays,
            )
            groups.setdefault(key, []).append(row)
            curve_axes.add(key[:3])

        cells: list[ResponseCurveCell] = []
        full_keys = [
            (target_id, shock_family, condition_bucket, horizon)
            for target_id, shock_family, condition_bucket in sorted(curve_axes)
            for horizon in HORIZONS_BDAYS
        ]
        for key in full_keys:
            target_id, shock_family, bucket_name, horizon = key
            target = TARGET_BY_ID[target_id]
            rows = groups.get(key, [])
            values, effective_n = _sample_values(rows)

            peer_rows = [
                row
                for row in observations
                if row.target_id != target_id
                and row.asset_class == target.asset_class
                and row.shock_family == shock_family
                and row.horizon_bdays == horizon
                and condition_bucket(row, condition_keys) == bucket_name
            ]
            peer_values, peer_effective_n = _sample_values(peer_rows)
            prior_n = min(self.prior_strength, peer_effective_n)
            prior_mean = float(peer_values.mean()) if len(peer_values) else None

            if effective_n < self.min_effective_n:
                cells.append(
                    ResponseCurveCell(
                        target_id=target_id,
                        shock_family=shock_family,
                        condition_bucket=bucket_name,
                        horizon_bdays=horizon,
                        sample_n=len(rows),
                        effective_n=effective_n,
                        raw_mean=None,
                        shrunk_mean=None,
                        interval_low=None,
                        interval_high=None,
                        prior_mean=prior_mean,
                        prior_effective_n=prior_n,
                        evidence_state="insufficient",
                    )
                )
                continue

            raw_mean = float(values.mean())
            if prior_mean is not None and prior_n:
                estimate = (effective_n * raw_mean + prior_n * prior_mean) / (
                    effective_n + prior_n
                )
            else:
                estimate = raw_mean

            combined = values
            if prior_mean is not None and prior_n:
                combined = np.concatenate((values, peer_values[:prior_n]))
            if len(combined) >= 2:
                se = float(combined.std(ddof=1) / math.sqrt(len(combined)))
                low, high = estimate - 1.96 * se, estimate + 1.96 * se
            else:
                low = high = None
            cells.append(
                ResponseCurveCell(
                    target_id=target_id,
                    shock_family=shock_family,
                    condition_bucket=bucket_name,
                    horizon_bdays=horizon,
                    sample_n=len(rows),
                    effective_n=effective_n,
                    raw_mean=raw_mean,
                    shrunk_mean=float(estimate),
                    interval_low=low,
                    interval_high=high,
                    prior_mean=prior_mean,
                    prior_effective_n=prior_n,
                    evidence_state="discovered",
                )
            )
        return cells


def cells_for_target(
    cells: Iterable[ResponseCurveCell], target_id: str
) -> dict[int, ResponseCurveCell]:
    """Return the full available curve indexed by precommitted horizon."""

    if target_id not in TARGET_BY_ID:
        raise ContractError(f"target_id is not precommitted: {target_id}")
    selected = {cell.horizon_bdays: cell for cell in cells if cell.target_id == target_id}
    return {horizon: selected[horizon] for horizon in HORIZONS_BDAYS if horizon in selected}
