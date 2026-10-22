"""Purged walk-forward, episode effective-N, FDR, and inert lifecycle tools."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from brain.liquidity_lab.contracts import ContractError, ShockRecord
from brain.liquidity_lab.estimator import (
    ForwardReturnObservation,
    ResponseCurveEstimator,
    condition_bucket,
)


def effective_episode_dates(
    dates: Iterable[date], *, horizon_bdays: int
) -> tuple[date, ...]:
    """Greedily retain non-overlapping event dates for a forward horizon.

    This is the honest-N for shock-response cells: multiple targets attached to
    the same shock remain one episode, and shock windows that overlap at the
    measured horizon do not manufacture independent observations.
    """

    if horizon_bdays < 1:
        raise ContractError("horizon_bdays must be positive")
    kept: list[date] = []
    for current in sorted(set(dates)):
        if not kept:
            kept.append(current)
            continue
        gap = int(np.busday_count(kept[-1].isoformat(), current.isoformat()))
        if gap >= horizon_bdays:
            kept.append(current)
    return tuple(kept)


@dataclass(frozen=True, slots=True)
class WalkForwardSpec:
    holdout_start: date
    min_train_episodes: int
    validation_episodes: int
    step_episodes: int

    def __post_init__(self) -> None:
        if self.min_train_episodes < 2:
            raise ContractError("min_train_episodes must be at least 2")
        if self.validation_episodes < 1 or self.step_episodes < 1:
            raise ContractError("validation_episodes and step_episodes must be positive")


@dataclass(frozen=True, slots=True)
class WalkForwardSplit:
    train_shock_ids: tuple[str, ...]
    validation_shock_ids: tuple[str, ...]
    train_end: date
    validation_start: date
    validation_end: date
    horizon_bdays: int


@dataclass(frozen=True, slots=True)
class WalkForwardPlan:
    splits: tuple[WalkForwardSplit, ...]
    untouched_holdout_shock_ids: tuple[str, ...]
    holdout_start: date
    horizon_bdays: int


@dataclass(frozen=True, slots=True)
class WalkForwardPrediction:
    split_index: int
    relation_id: str
    model_version: str
    shock_id: str
    target_id: str
    horizon_bdays: int
    anchor_session: date
    exit_session: date
    predicted_return: float
    realized_return: float
    effective_n_at_fit: int


def build_walk_forward_plan(
    shocks: Sequence[ShockRecord],
    *,
    horizon_bdays: int,
    spec: WalkForwardSpec,
) -> WalkForwardPlan:
    """Build expanding, horizon-purged folds without reading the holdout."""

    if horizon_bdays < 1:
        raise ContractError("horizon_bdays must be positive")
    ordered = sorted(shocks, key=lambda shock: (shock.first_detected, shock.shock_id))
    development = [shock for shock in ordered if shock.first_detected.date() < spec.holdout_start]
    holdout = tuple(
        shock.shock_id for shock in ordered if shock.first_detected.date() >= spec.holdout_start
    )
    splits: list[WalkForwardSplit] = []
    start = spec.min_train_episodes
    while start < len(development):
        validation = development[start : start + spec.validation_episodes]
        if not validation:
            break
        validation_start = validation[0].first_detected.date()
        purged_train = []
        for shock in development[:start]:
            gap = int(
                np.busday_count(shock.first_detected.date().isoformat(), validation_start.isoformat())
            )
            if gap > horizon_bdays:
                purged_train.append(shock)
        if len(purged_train) >= spec.min_train_episodes:
            splits.append(
                WalkForwardSplit(
                    train_shock_ids=tuple(shock.shock_id for shock in purged_train),
                    validation_shock_ids=tuple(shock.shock_id for shock in validation),
                    train_end=purged_train[-1].first_detected.date(),
                    validation_start=validation_start,
                    validation_end=validation[-1].first_detected.date(),
                    horizon_bdays=horizon_bdays,
                )
            )
        start += spec.step_episodes
    return WalkForwardPlan(
        splits=tuple(splits),
        untouched_holdout_shock_ids=holdout,
        holdout_start=spec.holdout_start,
        horizon_bdays=horizon_bdays,
    )


def run_walk_forward_curves(
    observations: Sequence[ForwardReturnObservation],
    *,
    plan: WalkForwardPlan,
    estimator: ResponseCurveEstimator,
    relation_id: str,
    condition_keys: Sequence[str] = (),
) -> list[WalkForwardPrediction]:
    """Fit on each purged train slice and predict only its validation slice.

    Holdout IDs never appear in ``plan.splits`` and are refused explicitly if a
    malformed plan tries to include one.  The runner returns prediction rows; it
    does not decide whether the relation passed, survived FDR, or earned authority.
    """

    holdout = set(plan.untouched_holdout_shock_ids)
    rows_by_shock: dict[str, list[ForwardReturnObservation]] = {}
    for row in observations:
        rows_by_shock.setdefault(row.shock_id, []).append(row)
    predictions: list[WalkForwardPrediction] = []
    for split_index, split in enumerate(plan.splits):
        train_ids = set(split.train_shock_ids)
        validation_ids = set(split.validation_shock_ids)
        if (train_ids | validation_ids) & holdout:
            raise ContractError("walk-forward split contains an untouched holdout shock")
        train_rows = [
            row
            for shock_id in train_ids
            for row in rows_by_shock.get(shock_id, [])
            if row.horizon_bdays == plan.horizon_bdays
        ]
        validation_rows = [
            row
            for shock_id in validation_ids
            for row in rows_by_shock.get(shock_id, [])
            if row.horizon_bdays == plan.horizon_bdays
        ]
        cells = estimator.fit(train_rows, condition_keys=condition_keys)
        index = {
            (
                cell.target_id,
                cell.shock_family,
                cell.condition_bucket,
                cell.horizon_bdays,
            ): cell
            for cell in cells
        }
        for row in validation_rows:
            key = (
                row.target_id,
                row.shock_family,
                condition_bucket(row, condition_keys),
                row.horizon_bdays,
            )
            cell = index.get(key)
            if cell is None or cell.shrunk_mean is None:
                continue
            predictions.append(
                WalkForwardPrediction(
                    split_index=split_index,
                    relation_id=relation_id,
                    model_version=estimator.model_version,
                    shock_id=row.shock_id,
                    target_id=row.target_id,
                    horizon_bdays=row.horizon_bdays,
                    anchor_session=row.anchor_session,
                    exit_session=row.exit_session,
                    predicted_return=cell.shrunk_mean,
                    realized_return=row.forward_return,
                    effective_n_at_fit=cell.effective_n,
                )
            )
    return predictions


def score_incremental_predictions(
    candidate: Sequence[WalkForwardPrediction],
    baseline: Sequence[WalkForwardPrediction],
    *,
    mean_test_fn: Callable[..., Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Score paired OOS squared-error improvement over one named baseline.

    Improvements are averaged within a shock, then greedily thinned using the
    actual widest anchor/exit interval.  The p-value comes from the existing Macro
    HAC judge by default; tests may inject that exact callable shape.  This result
    is input to FDR, never a promotion verdict by itself.
    """

    def key(row: WalkForwardPrediction) -> tuple[str, str, int]:
        return row.shock_id, row.target_id, row.horizon_bdays

    baseline_by_key = {key(row): row for row in baseline}
    paired: list[tuple[WalkForwardPrediction, WalkForwardPrediction, float]] = []
    for row in candidate:
        base = baseline_by_key.get(key(row))
        if base is None:
            continue
        if not math.isclose(row.realized_return, base.realized_return, rel_tol=0, abs_tol=1e-12):
            raise ContractError("candidate and baseline disagree on realized return")
        candidate_error = (row.realized_return - row.predicted_return) ** 2
        baseline_error = (base.realized_return - base.predicted_return) ** 2
        paired.append((row, base, baseline_error - candidate_error))
    if not paired:
        return {
            "status": "insufficient",
            "effective_n": 0,
            "mean_squared_error_improvement": None,
            "p_value": None,
            "max_episode_share": None,
        }

    by_shock: dict[str, list[tuple[WalkForwardPrediction, float]]] = {}
    for row, _, improvement in paired:
        by_shock.setdefault(row.shock_id, []).append((row, improvement))
    episodes = []
    for shock_id, group in by_shock.items():
        episodes.append(
            (
                min(row.anchor_session for row, _ in group),
                max(row.exit_session for row, _ in group),
                float(np.mean([improvement for _, improvement in group])),
                shock_id,
            )
        )
    thinned: list[tuple[date, date, float, str]] = []
    last_exit: date | None = None
    for episode in sorted(episodes):
        if last_exit is None or episode[0] >= last_exit:
            thinned.append(episode)
            last_exit = episode[1]
    improvements = pd.Series([episode[2] for episode in thinned], dtype=float)

    if mean_test_fn is None:
        try:
            from engine.validation import newey_west_tstat as mean_test_fn  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            raise StatisticalDependencyUnavailable(
                "engine.validation.newey_west_tstat is required for incremental scoring"
            ) from exc
    test = dict(mean_test_fn(improvements)) if len(improvements) >= 2 else {}
    absolute_total = float(improvements.abs().sum())
    max_share = (
        float(improvements.abs().max() / absolute_total) if absolute_total > 0 else None
    )
    return {
        "status": "scoring" if len(improvements) >= 2 else "insufficient",
        "effective_n": len(improvements),
        "n_paired_rows": len(paired),
        "mean_squared_error_improvement": float(improvements.mean()),
        "p_value": float(test["p"]) if test.get("p") is not None else None,
        "max_episode_share": max_share,
        "episode_shock_ids": [episode[3] for episode in thinned],
    }


class StatisticalDependencyUnavailable(RuntimeError):
    """The canonical Macro validation implementation is not installed."""


def apply_bh_fdr(
    p_values: Mapping[str, float],
    *,
    alpha: float,
    fdr_fn: Callable[..., Mapping[str, Mapping[str, object]]] | None = None,
) -> dict[str, dict[str, object]]:
    """Apply the existing Macro BH-FDR judge, with dependency injection for tests.

    W-LIQ.3 does not create a second multiple-testing implementation.  Production
    calls reuse ``engine.validation.benjamini_hochberg``; hermetic tests inject a
    compatible frozen judge because the local sparse Macro checkout may be absent.
    """

    if not 0 < alpha < 1:
        raise ContractError("alpha must be in (0, 1)")
    clean: dict[str, float] = {}
    for relation_id, value in p_values.items():
        p_value = float(value)
        if not np.isfinite(p_value) or not 0 <= p_value <= 1:
            raise ContractError(f"invalid p-value for {relation_id}")
        clean[str(relation_id)] = p_value
    if fdr_fn is None:
        try:
            from engine.validation import benjamini_hochberg as fdr_fn  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            raise StatisticalDependencyUnavailable(
                "engine.validation.benjamini_hochberg is required for W-LIQ.3 FDR"
            ) from exc
    result = fdr_fn(clean, alpha=alpha)
    return {str(key): dict(value) for key, value in result.items()}


class RelationState(StrEnum):
    DISCOVERED = "discovered"
    SHADOW = "shadow"
    ADVISORY = "advisory"
    VALIDATED = "validated"
    DEMOTED = "demoted"
    DEAD = "dead"


@dataclass(frozen=True, slots=True)
class RelationEvidence:
    effective_n: int
    fdr_reject: bool
    incremental_metric: float
    sign_stability: float
    max_episode_share: float
    forward_windows: int
    forward_predictions_started: bool


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    """Sol-owned thresholds; no module-level production defaults exist."""

    min_effective_n_advisory: int
    min_effective_n_validated: int
    min_incremental_metric: float
    min_sign_stability: float
    max_episode_share: float
    min_forward_windows_validated: int
    demote_sign_stability: float

    def __post_init__(self) -> None:
        if self.min_effective_n_advisory < 1:
            raise ContractError("min_effective_n_advisory must be positive")
        if self.min_effective_n_validated < self.min_effective_n_advisory:
            raise ContractError("validated effective-n cannot be below advisory")
        if not 0 <= self.min_sign_stability <= 1:
            raise ContractError("min_sign_stability must be in [0, 1]")
        if not 0 <= self.max_episode_share <= 1:
            raise ContractError("max_episode_share must be in [0, 1]")
        if not 0 <= self.demote_sign_stability <= self.min_sign_stability:
            raise ContractError("demote_sign_stability must not exceed promotion stability")


def lifecycle_step(
    current: RelationState,
    evidence: RelationEvidence,
    *,
    policy: PromotionPolicy | None,
) -> RelationState:
    """Return one deterministic lifecycle step; never self-author a policy."""

    if current in {RelationState.DEAD, RelationState.DEMOTED}:
        return current
    if policy is None:
        # The current W-LIQ.3 PR has no Sol-ratified numeric acceptance policy.
        return current
    if current in {RelationState.ADVISORY, RelationState.VALIDATED} and (
        evidence.sign_stability < policy.demote_sign_stability
    ):
        return RelationState.DEMOTED
    if current == RelationState.DISCOVERED:
        return RelationState.SHADOW if evidence.forward_predictions_started else current
    common_pass = (
        evidence.fdr_reject
        and evidence.incremental_metric >= policy.min_incremental_metric
        and evidence.sign_stability >= policy.min_sign_stability
        and evidence.max_episode_share <= policy.max_episode_share
    )
    if current == RelationState.SHADOW and common_pass and (
        evidence.effective_n >= policy.min_effective_n_advisory
    ):
        return RelationState.ADVISORY
    if current == RelationState.ADVISORY and common_pass and (
        evidence.effective_n >= policy.min_effective_n_validated
        and evidence.forward_windows >= policy.min_forward_windows_validated
    ):
        return RelationState.VALIDATED
    return current
