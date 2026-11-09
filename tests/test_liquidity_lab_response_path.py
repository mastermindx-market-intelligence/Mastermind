"""GLT T16 response path: ONE plan, ONE budget, card-only spec, functional, delay cost.

Named cases:
* budget -- ``test_search_budget_guard_refuses_trial_n_plus_one_of_the_card_budget``
* functional -- ``test_functional_is_unavailable_when_the_card_declares_none``,
  ``test_functional_is_unavailable_on_a_flat_path``,
  ``test_two_tied_horizons_give_a_region_never_a_single_session``
* delay -- ``test_delay_cost_sensitivity_is_monotone_on_the_fixture``
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from brain.liquidity_lab.baselines import PairedPopulation, restrict_to_common
from brain.liquidity_lab.contracts import TARGET_BY_ID, ContractError
from brain.liquidity_lab.estimator import ForwardReturnObservation
from brain.liquidity_lab.path_inference import PathBand
from brain.liquidity_lab.preregistration import load_card
from brain.liquidity_lab.response_path import (
    DELAY_COST_NOTE,
    NO_FUNCTIONAL_REASON,
    LocalProjectionChallenger,
    PooledChallenger,
    ResponsePathSpec,
    ResponseTimeFunctional,
    SearchBudgetExceeded,
    StateConditionedChallenger,
    delay_cost_sensitivity,
    fit_response_path,
    response_time_functional,
    search_budget_guard,
)
from brain.liquidity_lab.validation import WalkForwardSpec, build_walk_forward_plan
from brain.liquidity_lab.window_guard import ReservedWindowTouched

REPO = Path(__file__).resolve().parents[1]
CARD_PATH = REPO / "research/liquidity_transmission/glt_preregistration_card.v1.json"
CARD_HASH = "da060bf47e8eafc7e94d0cadbb4135c9207a069aad9eef3539ea9d62911d6aee"
RELATION = "glt_rel_monetary_impulse_to_broad_targets.v1"
FAMILY = "glt_composite"
GRID = (5, 20, 60)
SPEC_WF = WalkForwardSpec(
    holdout_start=date(2022, 1, 3), min_train_episodes=20, validation_episodes=5, step_episodes=5
)


@dataclass(frozen=True)
class _Shock:
    shock_id: str
    first_detected: datetime


def _bday(day: date, n: int) -> date:
    return np.busday_offset(day.isoformat(), n, roll="forward").astype(date)


def _panel(*, targets=("spy", "qqq"), n: int = 80, seed: int = 20261019, horizons=GRID, plan_h: int = 60):
    rng = np.random.default_rng(seed)
    shocks, rows, directions = [], [], {}
    start = date(2008, 1, 7)
    for i in range(n):
        detected = _bday(start, 30 * i)
        direction = int(rng.choice([-1, 1]))
        size = float(rng.uniform(0.5, 3.0))
        shock_id = f"liq_{detected.isoformat()}_{FAMILY}_{i:04d}"
        first = datetime.combine(detected, time(21, 0))
        shocks.append(_Shock(shock_id, first))
        directions[shock_id] = direction
        anchor = _bday(detected, 1)
        for target in targets:
            spec = TARGET_BY_ID[target]
            for h in horizons:
                value = 0.002 * direction * size * math.sqrt(h / 20) + float(rng.normal(0, 0.004))
                rows.append(
                    ForwardReturnObservation(
                        shock_id=shock_id,
                        first_detected=first,
                        target_id=target,
                        asset_class=spec.asset_class,
                        hierarchy_parent=spec.hierarchy_parent,
                        shock_family=FAMILY,
                        shock_type="composite_z",
                        horizon_bdays=h,
                        anchor_session=anchor,
                        exit_session=_bday(anchor, h),
                        forward_return=value,
                        conditions={"shock_size_z": size},
                    )
                )
    plan = build_walk_forward_plan(shocks, horizon_bdays=plan_h, spec=SPEC_WF)
    return rows, plan, directions


@pytest.fixture(scope="module")
def spec():
    return ResponsePathSpec.from_card(load_card(CARD_PATH))


def _band(kind, lower, upper, horizons=GRID):
    return PathBand(
        kind=kind,
        horizons=tuple(horizons),
        lower=tuple(lower),
        upper=tuple(upper),
        level=0.9,
        n_blocks=12,
        n_episodes_effective=12,
        n_rows=36,
        n_draws=1000,
        method="fixture",
        critical_values=(2.0,) * len(horizons),
    )


def _path(points, horizons=GRID):
    return SimpleNamespace(horizons=tuple(horizons), points=tuple(points))


# ------------------------------------------------------------------------ spec
def test_spec_is_read_only_from_the_frozen_card(spec):
    assert spec.card_hash == CARD_HASH
    assert spec.relation_id == RELATION
    assert spec.horizon_grid == GRID and spec.primary_horizon == 20
    assert spec.sensitivity_horizons == (5, 60)
    assert spec.functional_kind is None
    assert spec.n_trials_total == 54 and spec.tuning_budget == 3
    assert spec.prior_strength_grid == (0, 5, 20) and spec.min_effective_n == 10
    assert spec.condition_keys == ()
    assert spec.purge_sessions == 60 and spec.reserved_start == date(2022, 1, 3)
    assert spec.identification_status == "association_only"
    assert spec.treatment_identification_status == "NOT_IDENTIFIED"
    configs = spec.incumbent_configs()
    assert [c.prior_strength for c in configs] == [0, 5, 20]
    assert all(CARD_HASH[:8] in c.model_version for c in configs)


def test_tampered_card_is_refused():
    payload = load_card(CARD_PATH).payload
    payload["family"]["n_trials_total"] = 999
    with pytest.raises(ContractError):
        ResponsePathSpec.from_card(payload)


# ---------------------------------------------------------------------- budget
def test_search_budget_guard_refuses_trial_n_plus_one_of_the_card_budget(spec):
    budget = search_budget_guard(spec)
    assert budget.n_trials_total == 54
    for i in range(54):
        budget.register("family", f"hyper={i // 3}", GRID[i % 3])
    assert budget.remaining == 0
    assert budget.register("family", "hyper=0", 5) == 54  # a repeat consumes nothing
    with pytest.raises(SearchBudgetExceeded, match=r"trial 55 .* card family\.n_trials_total=54 is spent"):
        budget.register("family", "hyper=18", 5)


def test_fit_response_path_refuses_when_the_budget_cannot_cover_the_grid(spec):
    rows, plan, _ = _panel(n=60)
    budget = search_budget_guard(spec)
    for i in range(52):
        budget.register("other", f"h{i}", 5)
    with pytest.raises(SearchBudgetExceeded, match="trial 55"):
        fit_response_path(rows, spec=spec, plan=plan, estimators=spec.incumbent_configs()[:1], budget=budget)


# ------------------------------------------------------------- one plan, paths
@pytest.fixture(scope="module")
def fitted(spec):
    rows, plan, directions = _panel()
    estimators = [
        *spec.incumbent_configs(),
        PooledChallenger(card_hash=spec.card_hash, min_effective_n=spec.min_effective_n),
        StateConditionedChallenger(spec, prior_strength=5),
        LocalProjectionChallenger(card_hash=spec.card_hash, min_effective_n=spec.min_effective_n),
    ]
    result = fit_response_path(rows, spec=spec, plan=plan, estimators=estimators, directions=directions)
    return result, estimators, plan


def test_every_challenger_runs_on_one_plan_under_one_budget(fitted, spec):
    result, estimators, plan = fitted
    assert result.plan_purge_horizon == 60
    assert len(result.trials) == len(estimators) * len(GRID) == 18
    assert result.trials_remaining == spec.n_trials_total - 18
    families = {t[0] for t in result.trials}
    assert families == {
        "direction_split_hierarchical_mean_curve",
        "pooled_no_shrinkage",
        "state_conditioned_hierarchical",
        "binned_local_projection",
    }
    for estimator in estimators:
        assert set(result.predictions[estimator.model_version]) == set(GRID)
        assert result.predictions[estimator.model_version][20], estimator.model_version
    # One plan: every member scores the same folds; the paired population is explicit.
    at20 = {mv: list(per_h[20]) for mv, per_h in result.predictions.items()}
    restricted, dropped = restrict_to_common(at20)
    population = PairedPopulation.require(restricted)
    assert len(population.keys) > 0
    assert set(population.per_fold) <= set(range(len(plan.splits)))
    assert set(dropped) == set(at20)  # every member's loss is quoted, never silent


def test_paths_are_direction_partitioned_and_keep_support_visible(fitted, spec):
    result, estimators, _ = fitted
    m1 = estimators[1]  # prior 5
    up = result.path(m1.model_version, target_id="spy", partition="direction=+1")
    down = result.path(m1.model_version, target_id="spy", partition="direction=-1")
    assert up.horizons == GRID
    assert all(p is not None for p in up.points)
    assert up.points[1] > 0 > down.points[1]
    assert all(n >= spec.min_effective_n for n in up.effective_n)
    assert all(n > 0 for n in up.prior_effective_n)  # qqq peer support, reported separately


def test_pooled_challenger_coincides_with_m1_prior0_on_the_v1_card(fitted):
    result, estimators, _ = fitted
    m1_prior0, pooled = estimators[0], estimators[3]
    for h in GRID:
        assert result.oos_mse(pooled.model_version, h) == pytest.approx(result.oos_mse(m1_prior0.model_version, h))


def test_local_projection_uses_declared_size_and_supplies_no_exogeneity(fitted, spec):
    result, estimators, _ = fitted
    lp = estimators[-1]
    assert "S31" in lp.identification
    paths = [
        result.path(lp.model_version, target_id="spy", partition="direction=+1", bucket=f"shock_size_tercile=q{q}")
        for q in (1, 3)
    ]
    small, large = (p.points[1] for p in paths)
    assert small is not None and large is not None and large > small
    assert all(p.prior_effective_n[1] > 0 for p in paths)


def test_challengers_refuse_undeclared_information(spec):
    rows, _, _ = _panel(n=30)
    with pytest.raises(ContractError, match="no conditioning"):
        PooledChallenger(card_hash=spec.card_hash, min_effective_n=10).fit(rows, condition_keys=("x",))
    with pytest.raises(ContractError, match="exactly the card"):
        StateConditionedChallenger(spec, prior_strength=0).fit(rows, condition_keys=("x",))
    with pytest.raises(ContractError, match="not on the card grid"):
        StateConditionedChallenger(spec, prior_strength=7)
    lp = LocalProjectionChallenger(card_hash=spec.card_hash, min_effective_n=10)
    with pytest.raises(ContractError, match="undeclared information"):
        lp.fit(rows, condition_keys=())
    bare = [replace(r, conditions={"shock_size_tercile": "q1"}) for r in rows]
    with pytest.raises(ContractError, match="declared shock size"):
        lp.fit(bare, condition_keys=lp.condition_keys)


def test_reserved_rows_and_a_short_purge_are_refused(spec):
    rows, plan, _ = _panel(n=40)
    late = replace(rows[0], exit_session=date(2022, 1, 3))
    with pytest.raises(ReservedWindowTouched, match="reserved_start 2022-01-03"):
        fit_response_path([*rows, late], spec=spec, plan=plan, estimators=spec.incumbent_configs()[:1])
    _, plan20, _ = _panel(n=40, plan_h=20)
    with pytest.raises(ContractError, match="needs purge >= 60"):
        fit_response_path(rows, spec=spec, plan=plan20, estimators=spec.incumbent_configs()[:1])


# ------------------------------------------------------------------ functional
def test_functional_is_unavailable_when_the_card_declares_none(spec):
    out = response_time_functional(_path((0.01, 0.03, 0.04)), spec.functional_kind)
    assert out.status == "unavailable" and out.reason == NO_FUNCTIONAL_REASON
    assert out.lower_session_exclusive is None and out.upper_session_inclusive is None


def test_functional_is_unavailable_on_a_flat_path():
    band = _band("simultaneous", (-0.01, -0.02, -0.03), (0.01, 0.02, 0.03))
    out = response_time_functional(_path((0.0, 0.001, -0.001)), "peak", band=band)
    assert out.status == "unavailable" and "flat path" in out.reason


def test_a_pointwise_band_cannot_certify_a_functional():
    band = _band("pointwise", (0.005, 0.025, 0.035), (0.015, 0.035, 0.045))
    out = response_time_functional(_path((0.01, 0.03, 0.04)), "peak", band=band)
    assert out.status == "unavailable" and "C29" in out.reason


def test_two_tied_horizons_give_a_region_never_a_single_session():
    band = _band("simultaneous", (0.005, 0.025, 0.026), (0.015, 0.035, 0.036))
    out = response_time_functional(_path((0.01, 0.03, 0.031)), "peak", band=band)
    assert out.status == "supported_region"
    assert out.candidate_horizons == (20, 60)
    assert out.lower_session_exclusive == 5 and out.upper_session_inclusive is None


def test_a_unique_peak_is_an_interval_between_grid_neighbours():
    band = _band("simultaneous", (0.005, 0.040, 0.010), (0.015, 0.050, 0.020))
    out = response_time_functional(_path((0.01, 0.045, 0.015)), "peak", band=band)
    assert (out.status, out.lower_session_exclusive, out.upper_session_inclusive) == ("interval", 5, 60)
    assert out.upper_session_inclusive - out.lower_session_exclusive > 1


def test_time_to_fraction_and_threshold_are_intervals_or_censored_regions():
    band = _band("simultaneous", (0.005, 0.028, 0.035), (0.015, 0.032, 0.045))
    half = response_time_functional(_path((0.01, 0.03, 0.04)), "time_to_fraction", band=band, fraction=0.5)
    assert (half.status, half.lower_session_exclusive, half.upper_session_inclusive) == ("interval", 5, 20)
    never = response_time_functional(_path((0.01, 0.03, 0.04)), "threshold_crossing", band=band, threshold=0.044)
    assert never.status == "supported_region" and never.upper_session_inclusive is None
    beyond = response_time_functional(_path((0.01, 0.03, 0.04)), "threshold_crossing", band=band, threshold=0.5)
    assert beyond.status == "unavailable"


def test_functional_object_refuses_a_single_session():
    with pytest.raises(ContractError, match="single session"):
        ResponseTimeFunctional("peak", "interval", 19, 20, (20,), "simultaneous", "x")


# ------------------------------------------------------------------ delay cost
def test_delay_cost_sensitivity_is_monotone_on_the_fixture(fitted):
    result, estimators, _ = fitted
    path = result.path(estimators[1].model_version, target_id="spy", partition="direction=+1")
    table = delay_cost_sensitivity(path, (0, 1, 5, 10, 20, 40))
    assert table.note == DELAY_COST_NOTE and "not a recommendation" in table.note
    for horizon in GRID:
        remaining = [r["response_remaining"] for r in table.rows if r["horizon"] == horizon]
        delays = [r["delay_sessions"] for r in table.rows if r["horizon"] == horizon]
        assert delays == sorted(d for d in (0, 1, 5, 10, 20, 40) if d < horizon)
        assert all(a >= b for a, b in zip(remaining, remaining[1:])), (horizon, remaining)
    zero = [r for r in table.rows if r["delay_sessions"] == 0]
    assert all(r["response_remaining"] == pytest.approx(r["response_at_horizon"]) for r in zero)


def test_delay_cost_refuses_an_inadequate_path():
    with pytest.raises(ContractError, match="every grid horizon"):
        delay_cost_sensitivity(_path((0.01, None, 0.02)), (0, 5))
