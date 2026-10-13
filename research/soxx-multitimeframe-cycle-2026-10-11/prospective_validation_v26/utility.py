"""Pure prospective SOXX accounting and causal-clock checks.

No network, prices, broker, collector, scheduler, model fitting, or trade sizing.
Inputs are qualified upstream facts or explicitly labelled hypothetical bounds.
This module checks consistency; it cannot authenticate a receipt or grant rights.
All return quantities are percentage points per ORIGINAL position, not per sale.
The frozen v2-v24 implementations/results are intentionally not imported/changed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from numbers import Real
from typing import Iterable, Optional, Sequence


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite real number, not a boolean')
    return float(value)


def _clock(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f'{name} must be timezone-aware')
    return value


def _key(value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError('episode must be a nonempty canonical upstream identifier')


@dataclass(frozen=True)
class TrainingLabel:
    """One decision label, with BOTH paired outcome paths and receipt availability.

    outcome_available_at is when the complete label was available to the model,
    not a backdated market timestamp. Unknown availability never enters training.
    Build each checkpoint's training population separately with its frozen rules.
    """
    episode: str
    decision_at: datetime
    feature_available_at: datetime
    baseline_end_at: datetime
    intervention_end_at: datetime
    outcome_available_at: Optional[datetime]

    def __post_init__(self) -> None:
        _key(self.episode)
        for name in ('decision_at', 'feature_available_at', 'baseline_end_at', 'intervention_end_at'):
            _clock(getattr(self, name), name)
        if self.feature_available_at > self.decision_at:
            raise ValueError('feature unavailable at the claimed decision')
        if min(self.baseline_end_at, self.intervention_end_at) < self.decision_at:
            raise ValueError('decision label includes a path closed before the decision')
        if self.outcome_available_at is not None:
            _clock(self.outcome_available_at, 'outcome_available_at')
            if self.outcome_available_at < max(self.baseline_end_at, self.intervention_end_at):
                raise ValueError('outcome availability precedes paired-path completion')


def mature_training_labels(labels: Iterable[TrainingLabel], fit_at: datetime) -> list[TrainingLabel]:
    """Strictly prior available labels; entry week is not a maturity test."""
    _clock(fit_at, 'fit_at')
    selected: list[TrainingLabel] = []
    seen: set[str] = set()
    for row in labels:
        if not isinstance(row, TrainingLabel):
            raise ValueError('labels must be TrainingLabel records')
        if row.episode in seen:
            raise ValueError('duplicate training decision')
        seen.add(row.episode)
        if row.outcome_available_at is not None and row.outcome_available_at < fit_at:
            selected.append(row)
    return selected


def check_decision_clocks(completed_bar_at: datetime, feature_available_at: datetime,
                          decision_recorded_at: datetime, submitted_at: datetime,
                          first_allowed_fill_at: datetime) -> None:
    """Reject retroactive information/fills, without claiming order marketability."""
    clocks = (completed_bar_at, feature_available_at, decision_recorded_at,
              submitted_at, first_allowed_fill_at)
    for i, value in enumerate(clocks):
        _clock(value, f'clock[{i}]')
    if not completed_bar_at <= feature_available_at <= decision_recorded_at <= submitted_at:
        raise ValueError('decision clocks are not causally ordered')
    if first_allowed_fill_at <= submitted_at:
        raise ValueError('fill must follow submission; simultaneous OHLC open is not proof')


@dataclass(frozen=True)
class PairedOutcome:
    """One original episode, including genuine non-actions and unresolved cases.

    Net returns already include baseline fees. Extra sell slippage applies only
    to the remaining original-position fraction actually sold. For UNRESOLVED,
    bounds must include that stress and are assumptions, not observed fills.
    baseline_preserved means the SAME baseline controls/path were retained; a
    rejected order alone does not establish this fact. The caller must verify it.
    """
    episode: str
    state: str
    baseline_pp: Optional[float] = None
    intervention_pp: Optional[float] = None
    baseline_preserved: bool = False
    sold_fraction: float = 0.
    sale_to_entry: Optional[float] = None
    delta_bounds: Optional[tuple[float, float]] = None
    bounds_cover_slippage_bps: float = 0.

    def __post_init__(self) -> None:
        _key(self.episode)
        if self.state not in {'FILLED', 'NO_ACTION', 'VERIFIED_NO_FILL', 'UNRESOLVED'}:
            raise ValueError('unknown outcome state')
        if type(self.baseline_preserved) is not bool:
            raise ValueError('baseline_preserved must be boolean')
        for name in ('baseline_pp', 'intervention_pp'):
            value = getattr(self, name)
            if value is not None:
                _finite(value, name)
        q = _finite(self.sold_fraction, 'sold_fraction')
        if not 0 <= q <= 1:
            raise ValueError('sold fraction must lie within the original position')
        covered = _finite(self.bounds_cover_slippage_bps, 'bounds_cover_slippage_bps')
        if not 0 <= covered <= 10000:
            raise ValueError('invalid bound stress coverage')
        if self.state == 'FILLED':
            if self.baseline_pp is None or self.intervention_pp is None or q <= 0:
                raise ValueError('filled outcome needs paired returns and positive sold fraction')
            if _finite(self.sale_to_entry, 'sale_to_entry') <= 0:
                raise ValueError('sale/entry ratio must be positive')
            if self.delta_bounds is not None or self.baseline_preserved:
                raise ValueError('filled outcome cannot masquerade as a bound or non-action')
        elif self.state in {'NO_ACTION', 'VERIFIED_NO_FILL'}:
            if not self.baseline_preserved or q != 0 or self.sale_to_entry is not None:
                raise ValueError('zero delta requires verified unchanged baseline controls')
            if self.delta_bounds is not None:
                raise ValueError('non-action cannot have an alternative delta bound')
            if (self.baseline_pp is None) != (self.intervention_pp is None):
                raise ValueError('provide both equal returns or neither')
            if self.baseline_pp is not None and not math.isclose(
                    self.baseline_pp, self.intervention_pp, rel_tol=0, abs_tol=1e-12):
                raise ValueError('non-action has unequal paired returns')
        else:
            if q != 0 or self.sale_to_entry is not None or self.intervention_pp is not None:
                raise ValueError('unknown execution cannot assert a fill or point outcome')
            if self.baseline_preserved:
                raise ValueError('uncertain outcome cannot assert baseline equivalence')
            if self.delta_bounds is not None:
                if len(self.delta_bounds) != 2:
                    raise ValueError('bounds need lower and upper')
                lo, hi = (_finite(v, 'delta bound') for v in self.delta_bounds)
                if lo > hi:
                    raise ValueError('reversed outcome bounds')
                object.__setattr__(self, 'delta_bounds', (lo, hi))


def summarize(cohort_ids: Sequence[str], rows: Iterable[PairedOutcome], *,
              extra_sell_slippage_bps: float = 0.) -> dict:
    """Full-cohort paired economics. Unknowns are neither zeroed nor discarded.

    A lower/upper envelope is NOT a statistical confidence interval. Component
    sums concern resolved rows only; unknown contributions remain unassigned.
    The economic bridge splits zero crossings: avoiding a loss is not the same
    as creating an additional profit, and sacrificing profit is not a new loss.
    positive_under_supplied_bounds is descriptive, never strategy acceptance.
    """
    cost = _finite(extra_sell_slippage_bps, 'extra_sell_slippage_bps')
    if not 0 <= cost <= 10000:
        raise ValueError('additional adverse sell slippage must be between zero and 10000 bps')
    ids = list(cohort_ids)
    for key in ids:
        _key(key)
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('nonempty unique original cohort required')
    values = list(rows)
    if any(not isinstance(r, PairedOutcome) for r in values):
        raise ValueError('rows must be PairedOutcome records')
    keys = [r.episode for r in values]
    if len(keys) != len(set(keys)) or set(keys) != set(ids):
        raise ValueError('every original episode must occur exactly once, with no extras')
    components = dict(baseline_loser_improvement_pp=0., baseline_winner_improvement_pp=0.,
                      baseline_winner_sacrifice_pp=0., baseline_loser_deterioration_pp=0.,
                      zero_baseline_benefit_pp=0., zero_baseline_harm_pp=0.)
    bridge = dict(loss_reduction_pp=0., profit_increase_pp=0.,
                  profit_surrender_pp=0., loss_increase_pp=0.)
    point: list[float] = []
    lower: list[Optional[float]] = []
    upper: list[Optional[float]] = []
    states = {name: 0 for name in ('FILLED', 'NO_ACTION', 'VERIFIED_NO_FILL', 'UNRESOLVED')}
    total_cost = 0.
    for row in values:
        states[row.state] += 1
        if row.state == 'UNRESOLVED':
            if row.delta_bounds is None:
                lower.append(None); upper.append(None)
            else:
                if row.bounds_cover_slippage_bps < cost:
                    raise ValueError('unknown-outcome bounds do not cover the requested cost stress')
                lower.append(float(row.delta_bounds[0])); upper.append(float(row.delta_bounds[1]))
            continue
        delta = 0.
        if row.state == 'FILLED':
            extra = row.sold_fraction * row.sale_to_entry * cost / 100.
            total_cost += extra
            delta = row.intervention_pp - row.baseline_pp - extra
            baseline = row.baseline_pp
            stressed = row.intervention_pp - extra
            loss_change = max(-baseline, 0.) - max(-stressed, 0.)
            profit_change = max(stressed, 0.) - max(baseline, 0.)
            bridge['loss_reduction_pp'] += max(loss_change, 0.)
            bridge['loss_increase_pp'] += max(-loss_change, 0.)
            bridge['profit_increase_pp'] += max(profit_change, 0.)
            bridge['profit_surrender_pp'] += max(-profit_change, 0.)
            if delta > 0:
                label = ('baseline_loser_improvement_pp' if baseline < 0 else 'baseline_winner_improvement_pp'
                         if baseline > 0 else 'zero_baseline_benefit_pp')
                components[label] += delta
            elif delta < 0:
                label = ('baseline_winner_sacrifice_pp' if baseline > 0 else 'baseline_loser_deterioration_pp'
                         if baseline < 0 else 'zero_baseline_harm_pp')
                components[label] -= delta
        _finite(delta, 'net delta')
        point.append(delta); lower.append(delta); upper.append(delta)
    n = len(ids)
    lo = math.fsum(lower)/n if all(v is not None for v in lower) else None
    hi = math.fsum(upper)/n if all(v is not None for v in upper) else None
    exact = math.fsum(point)/n if len(point) == n else None
    return dict(original_episodes=n, resolved_episodes=len(point),
                unresolved_episodes=states['UNRESOLVED'], discretionary_fills=states['FILLED'],
                no_action_episodes=states['NO_ACTION'], verified_no_fill_episodes=states['VERIFIED_NO_FILL'],
                mean_delta_pp=exact, mean_delta_lower_pp=lo, mean_delta_upper_pp=hi,
                resolved_components=components, resolved_economic_bridge=bridge,
                extra_sell_cost_sum_pp=total_cost,
                worst_resolved_delta_pp=min(point) if point else None,
                positive_under_supplied_bounds=lo is not None and lo > 0,
                envelope_is_confidence_interval=False,
                evidence_claim='ACCOUNTING_ONLY_NOT_STRATEGY_ACCEPTANCE')


def break_even_share(mean_benefit_pp: float, mean_harm_pp: float, *,
                     decision_cost_pp: float = 0.) -> float:
    """Conditional payoff identity p*benefit-(1-p)*harm-cost=0.

    Applies to the contemplated action mix, NOT an arbitrary strategy's precision.
    No assumption of acting on all opportunities. A result >=1 is not attainable
    with positive strict utility. Do not add a cost already included in payoffs.
    """
    benefit = _finite(mean_benefit_pp, 'mean_benefit_pp')
    harm = _finite(mean_harm_pp, 'mean_harm_pp')
    cost = _finite(decision_cost_pp, 'decision_cost_pp')
    if benefit <= 0 or harm < 0 or cost < 0:
        raise ValueError('positive benefit and nonnegative harm/cost required')
    return (harm + cost) / (benefit + harm)


def overlap_components(intervals: Iterable[tuple[str, datetime, datetime]]) -> list[list[str]]:
    """Connected overlapping exposure intervals across ALL symbols, [start,end).

    This diagnoses overlap dependence, not independence or a bootstrap guarantee.
    Long chains can yield one component; never count its symbols as new trials.
    Exchange sessions/calendars and horizon clocks remain upstream-owned.
    """
    values = list(intervals)
    seen: set[str] = set()
    for key, start, end in values:
        _key(key); _clock(start, 'start'); _clock(end, 'end')
        if key in seen or end <= start:
            raise ValueError('duplicate episode or invalid exposure interval')
        seen.add(key)
    groups: list[list[str]] = []
    end_at: Optional[datetime] = None
    for key, start, end in sorted(values, key=lambda x: (x[1], x[2], x[0])):
        if end_at is None or start >= end_at:
            groups.append([key]); end_at = end
        else:
            groups[-1].append(key); end_at = max(end_at, end)
    return groups
