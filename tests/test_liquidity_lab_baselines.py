"""GLT T15: same-information baselines, paired population, train-only transforms, LTIFO.

Named acceptance cases:
* C27 -- ``test_c27_paired_population_refuses_one_key_asymmetry``
* C17 -- ``test_c17_transform_fit_with_one_dev_row_raises_leaked_fit``
* C26 -- ``test_c26_dollar_target_candidate_matches_direct_funding_and_ltifo_mask``
"""

from __future__ import annotations

import ast
import json
import math
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from pathlib import Path

import numpy as np
import pytest

from brain.liquidity_lab.baselines import (
    BASELINE_LADDER,
    DEFAULT_LTIFO_PATH,
    DIRECT_INPUT_KEYS,
    PRICE_CONTEXT_KEYS,
    AnnouncedOnlyBaseline,
    ComponentBaseline,
    DirectFundingBaseline,
    LeakedFitError,
    NoGapBaseline,
    PairedPopulation,
    PersistenceBaseline,
    PopulationMismatch,
    PooledMeanBaseline,
    PriceMomentumBaseline,
    QuantileBucketTransform,
    load_ltifo_definition,
    ltifo_definition_hash,
    ltifo_family_mask,
    mean_squared_error,
    novelty_disposition,
    restrict_to_common,
    run_baseline,
    run_direction_partitioned,
    run_fold_transformed,
    score_paired,
)
from brain.liquidity_lab.contracts import HORIZONS_BDAYS, TARGET_BY_ID, ContractError
from brain.liquidity_lab.estimator import ForwardReturnObservation, HierarchicalMeanCurveEstimator
from brain.liquidity_lab.preregistration import card_hash, load_card
from brain.liquidity_lab.validation import (
    WalkForwardSpec,
    build_walk_forward_plan,
    score_incremental_predictions,
)

REPO = Path(__file__).resolve().parents[1]
CARD_HASH = "da060bf47e8eafc7e94d0cadbb4135c9207a069aad9eef3539ea9d62911d6aee"
LTIFO_HASH = "d4746b2ba92f23f16c51e9abae37e78a23a4a76f7342def3d42157171ba49c62"
RELATION = "glt_rel_monetary_impulse_to_broad_targets.v1"
FAMILY = "glt_composite"
H = 20
#: The card's reveal.walk_forward_spec (holdout = reserved_start).
SPEC = WalkForwardSpec(
    holdout_start=date(2022, 1, 3), min_train_episodes=20, validation_episodes=5, step_episodes=5
)
NEW_MODULES = ("baselines.py", "window_guard.py")


@dataclass(frozen=True)
class _Shock:
    shock_id: str
    first_detected: datetime


def _bday(day: date, n: int) -> date:
    return np.busday_offset(day.isoformat(), n, roll="forward").astype(date)


def _t_test(values):
    """Deterministic stand-in with the HAC judge's call shape (tests only)."""

    arr = np.asarray(values, dtype=float)
    se = arr.std(ddof=1) / math.sqrt(len(arr))
    t = float(arr.mean() / se) if se > 0 else 0.0
    return {"t": t, "p": math.erfc(abs(t) / math.sqrt(2.0))}


def _panel(
    *,
    target: str = "spy",
    n: int = 80,
    seed: int = 20261019,
    response=None,
    horizons=(5, 20, 60),
):
    """Synthetic train-window panel: one row per (shock, horizon); 30-session spacing."""

    rng = np.random.default_rng(seed)
    spec = TARGET_BY_ID.get(target)
    asset_class = spec.asset_class if spec else "fx"
    parent = spec.hierarchy_parent if spec else "fx"
    shocks, rows, directions, dollar = [], [], {}, {}
    start = date(2008, 1, 7)
    for i in range(n):
        detected = _bday(start, 30 * i)
        dollar_sign = int(rng.choice([-1, 1]))
        conditions = {
            "dtwexbgs.d4w_sign": dollar_sign,
            "dfii10.d4w_sign": int(rng.choice([-1, 1])),
            "fed_total_assets.d4w_sign": int(rng.choice([-1, 1])),
            "ecb_total_assets.d4w_sign": int(rng.choice([-1, 1])),
            "boj_total_assets.d4w_sign": int(rng.choice([-1, 1])),
            "target.ret20_sign": int(rng.choice([-1, 1])),
            "target.vol60": float(rng.uniform(0.05, 0.40)),
            "target.above_ma200": int(rng.choice([0, 1])),
        }
        # The composite contains the dollar leg inverted (falling dollar = easing).
        direction = -dollar_sign
        shock_id = f"liq_{detected.isoformat()}_{FAMILY}_{'pos' if direction > 0 else 'neg'}_{i:012d}"
        first = datetime.combine(detected, time(21, 0))
        shocks.append(_Shock(shock_id, first))
        directions[shock_id] = direction
        dollar[shock_id] = dollar_sign
        anchor = _bday(detected, 1)
        for h in horizons:
            if response is None:
                value = 0.004 * direction * math.sqrt(h / 20) + float(rng.normal(0, 0.01))
            else:
                value = response(h, conditions, direction, rng)
            rows.append(
                ForwardReturnObservation(
                    shock_id=shock_id,
                    first_detected=first,
                    target_id=target,
                    asset_class=asset_class,
                    hierarchy_parent=parent,
                    shock_family=FAMILY,
                    shock_type="composite_z",
                    horizon_bdays=h,
                    anchor_session=anchor,
                    exit_session=_bday(anchor, h),
                    forward_return=value,
                    conditions=conditions,
                )
            )
    plan = build_walk_forward_plan(shocks, horizon_bdays=H, spec=SPEC)
    return rows, plan, directions, dollar


def _ladder(min_n: int = 3):
    return [
        PooledMeanBaseline(card_hash=CARD_HASH, min_effective_n=min_n),
        PersistenceBaseline(card_hash=CARD_HASH),
        AnnouncedOnlyBaseline(card_hash=CARD_HASH),
        ComponentBaseline(card_hash=CARD_HASH, min_effective_n=min_n),
        DirectFundingBaseline(card_hash=CARD_HASH, min_effective_n=min_n),
        PriceMomentumBaseline(card_hash=CARD_HASH, min_effective_n=min_n),
        NoGapBaseline(card_hash=CARD_HASH),
    ]


# ------------------------------------------------------------------ rung shape
def test_every_rung_fits_on_the_same_axes_and_carries_the_card_hash():
    rows, plan, _, _ = _panel()
    train = [r for r in rows if r.shock_id in set(plan.splits[0].train_shock_ids)]
    axes = None
    for baseline in _ladder():
        rows_in = train
        for factory in baseline.transform_factories:
            transform = factory(plan.splits[0]).fit([r for r in train if r.horizon_bdays == H])
            rows_in = [transform.apply(r) for r in rows_in]
        cells = baseline.fit(rows_in, condition_keys=baseline.condition_keys)
        assert baseline.model_version.startswith("glt_t15_")
        assert baseline.model_version.endswith("@" + CARD_HASH[:8])
        got = {(c.target_id, c.shock_family) for c in cells}
        horizons = {c.horizon_bdays for c in cells}
        assert horizons == set(HORIZONS_BDAYS), baseline.slug
        axes = got if axes is None else axes
        assert got == axes == {("spy", FAMILY)}, baseline.slug


def test_rungs_refuse_undeclared_information():
    rows, plan, _, _ = _panel()
    with pytest.raises(ContractError, match="undeclared information"):
        PooledMeanBaseline(card_hash=CARD_HASH).fit(rows, condition_keys=("dtwexbgs.d4w_sign",))
    with pytest.raises(ContractError, match="undeclared information"):
        DirectFundingBaseline(card_hash=CARD_HASH).fit(rows, condition_keys=())


def test_persistence_nogap_and_pooled_cell_values():
    rows, plan, _, _ = _panel()
    train = [r for r in rows if r.horizon_bdays == H][:10]
    pooled = {c.horizon_bdays: c for c in PooledMeanBaseline(card_hash=CARD_HASH).fit(train)}[H]
    assert pooled.shrunk_mean == pytest.approx(np.mean([r.forward_return for r in train]))
    assert pooled.prior_mean is None and pooled.prior_effective_n == 0
    persistence = {c.horizon_bdays: c for c in PersistenceBaseline(card_hash=CARD_HASH).fit(train)}[H]
    assert persistence.shrunk_mean == pytest.approx(train[-1].forward_return)
    assert persistence.effective_n == 1 and persistence.evidence_state == "comparator"
    nogap = {c.horizon_bdays: c for c in NoGapBaseline(card_hash=CARD_HASH).fit(train)}
    assert nogap[H].shrunk_mean == 0.0
    assert nogap[5].shrunk_mean is None  # no training cell at h5 -> no forecast


def test_pooled_mean_below_floor_is_insufficient_without_a_mean():
    rows, _, _, _ = _panel()
    cells = PooledMeanBaseline(card_hash=CARD_HASH, min_effective_n=10).fit(
        [r for r in rows if r.horizon_bdays == H][:4]
    )
    cell = {c.horizon_bdays: c for c in cells}[H]
    assert cell.evidence_state == "insufficient"
    assert cell.raw_mean is None and cell.shrunk_mean is None and cell.effective_n == 4


def test_announced_only_abstains_when_card_registers_no_announced_series():
    card = load_card(REPO / "research/liquidity_transmission/glt_preregistration_card.v1.json")
    baseline = AnnouncedOnlyBaseline.from_card(card)
    rows, _, _, _ = _panel()
    cells = baseline.fit(rows)
    assert cells and {c.evidence_state for c in cells} == {"unavailable"}
    assert all(c.shrunk_mean is None and c.raw_mean is None for c in cells)
    assert "no announced-path series is registered" in baseline.abstention_reason
    rows_, plan, _, _ = _panel()
    assert run_baseline(rows_, plan=plan, baseline=baseline, relation_id=RELATION) == []
    with pytest.raises(ContractError, match="never a stand-in"):
        AnnouncedOnlyBaseline(card_hash=CARD_HASH, announced_source_ids=("fomc_dots",))


def test_direct_input_rungs_follow_the_card_b4_information_set_and_rights():
    card = load_card(REPO / "research/liquidity_transmission/glt_preregistration_card.v1.json")
    component = ComponentBaseline.from_card(card)
    funding = DirectFundingBaseline.from_card(card)
    assert component.sources == (
        "fed_total_assets",
        "ecb_total_assets",
        "boj_total_assets",
        "dtwexbgs",
        "dfii10",
    )
    assert funding.sources == ("dtwexbgs", "dfii10")
    assert funding.condition_keys == ("dtwexbgs.d4w_sign", "dfii10.d4w_sign")
    assert component.min_effective_n == funding.min_effective_n == 10
    assert "hy_oas" not in DIRECT_INPUT_KEYS  # UNPROVEN and outside B4: never a v1 comparator
    assert {row["class"] for row in BASELINE_LADDER} == {
        "PooledMeanBaseline",
        "PriceMomentumBaseline",
        "ComponentBaseline",
        "DirectFundingBaseline",
        "PersistenceBaseline",
        "AnnouncedOnlyBaseline",
        "NoGapBaseline",
    }


def test_card_hash_mismatch_is_refused():
    card = load_card(REPO / "research/liquidity_transmission/glt_preregistration_card.v1.json")
    tampered = card.payload
    tampered["windows"]["train_end"] = "2018-06-29"
    with pytest.raises(ContractError, match="card_hash does not recompute"):
        DirectFundingBaseline.from_card(tampered)


# ------------------------------------------------------------ C27 paired population
def test_c27_paired_population_refuses_one_key_asymmetry():
    rows, plan, directions, _ = _panel()
    candidate = run_direction_partitioned(
        rows,
        directions=directions,
        plan=plan,
        estimator=PooledMeanBaseline(card_hash=CARD_HASH, min_effective_n=3),
        relation_id=RELATION,
    )
    comparator = run_baseline(
        rows, plan=plan, baseline=PooledMeanBaseline(card_hash=CARD_HASH, min_effective_n=3), relation_id=RELATION
    )
    population = PairedPopulation.require({"candidate": candidate, "pooled_mean": comparator})
    assert len(population.keys) == len(candidate) == len(comparator) == 60
    assert population.per_fold == {i: 5 for i in range(12)}

    dropped = comparator[:-1]
    with pytest.raises(PopulationMismatch) as excinfo:
        PairedPopulation.require({"candidate": candidate, "pooled_mean": dropped})
    missing_key = (comparator[-1].shock_id, comparator[-1].target_id, comparator[-1].horizon_bdays)
    assert excinfo.value.asymmetric["pooled_mean"]["missing_vs_candidate"] == (missing_key,)
    assert excinfo.value.asymmetric["pooled_mean"]["extra_vs_candidate"] == ()
    with pytest.raises(PopulationMismatch):
        score_paired(candidate, dropped, mean_test_fn=_t_test)
    # The incumbent scorer would have silently narrowed the population; the guard is the point.
    silent = score_incremental_predictions(candidate, dropped, mean_test_fn=_t_test)
    assert silent["n_paired_rows"] == 59


def test_paired_population_refuses_realized_disagreement_and_duplicates():
    rows, plan, directions, _ = _panel()
    candidate = run_baseline(
        rows, plan=plan, baseline=PooledMeanBaseline(card_hash=CARD_HASH, min_effective_n=3), relation_id=RELATION
    )
    shifted = [replace(candidate[0], realized_return=candidate[0].realized_return + 1.0), *candidate[1:]]
    with pytest.raises(ContractError, match="realized return"):
        PairedPopulation.require({"candidate": candidate, "other": shifted})
    with pytest.raises(ContractError, match="duplicate"):
        PairedPopulation.require({"candidate": candidate, "other": [*candidate, candidate[0]]})


def test_restrict_to_common_reports_what_each_member_lost():
    rows, plan, directions, _ = _panel()
    members = {
        baseline.slug: run_baseline(rows, plan=plan, baseline=baseline, relation_id=RELATION)
        for baseline in _ladder()
        if not isinstance(baseline, AnnouncedOnlyBaseline)
    }
    with pytest.raises(PopulationMismatch):
        PairedPopulation.require(members)  # the 5-key component rung leaves cells empty
    restricted, dropped = restrict_to_common(members)
    population = PairedPopulation.require(restricted)
    assert dropped["pooled_mean"] == 60 - len(population.keys)
    assert dropped["component"] == len(members["component"]) - len(population.keys)
    assert 0 < len(population.keys) < 60


# ------------------------------------------------------------- C17 train-only fit
def test_c17_transform_fit_with_one_dev_row_raises_leaked_fit():
    rows, plan, _, _ = _panel()
    split = plan.splits[0]
    train_ids = set(split.train_shock_ids)
    train = [r for r in rows if r.shock_id in train_ids and r.horizon_bdays == H]
    dev_row = next(r for r in rows if r.shock_id == split.validation_shock_ids[0] and r.horizon_bdays == H)
    QuantileBucketTransform(split).fit(train)  # train only: admitted
    with pytest.raises(LeakedFitError, match="non-training shock"):
        QuantileBucketTransform(split).fit([*train, dev_row])
    later = replace(train[0], first_detected=datetime.combine(_bday(split.train_end, 1), time(21, 0)))
    with pytest.raises(LeakedFitError):
        QuantileBucketTransform(split).fit([*train, later])


def test_fold_transforms_are_fitted_per_fold_on_train_rows_only():
    rows, plan, _, _ = _panel()
    fitted = []

    def factory(split):
        transform = QuantileBucketTransform(split)
        fitted.append(transform)
        return transform

    predictions = run_fold_transformed(
        rows,
        plan=plan,
        estimator=PriceMomentumBaseline(card_hash=CARD_HASH, min_effective_n=2),
        relation_id=RELATION,
        condition_keys=PRICE_CONTEXT_KEYS,
        transform_factories=(factory,),
    )
    assert len(fitted) == len(plan.splits) == 12
    for transform, split in zip(fitted, plan.splits):
        assert set(transform.fitted_on) == set(split.train_shock_ids)
        assert not set(transform.fitted_on) & set(split.validation_shock_ids)
    assert len({t.cut_points for t in fitted}) > 1  # expanding window -> refitted cut points
    assert predictions and {p.split_index for p in predictions} <= set(range(12))


# ------------------------------------------------- C26 mechanical overlap control
def _dollar_response(h, conditions, direction, rng):
    # The dollar's own 4-week momentum carries into its forward return.
    return 0.01 * conditions["dtwexbgs.d4w_sign"] * math.sqrt(h / 20) + float(rng.normal(0, 0.005))


def test_c26_dollar_target_candidate_matches_direct_funding_and_ltifo_mask(monkeypatch, capsys):
    card = load_card(REPO / "research/liquidity_transmission/glt_preregistration_card.v1.json")
    ltifo = load_ltifo_definition(REPO / DEFAULT_LTIFO_PATH)
    rows, plan, directions, _ = _panel(target="dtwexbgs", response=_dollar_response)
    # Composite candidate: direction-split pooled mean (= M1 prior 0 for a one-target panel).
    candidate = run_direction_partitioned(
        rows,
        directions=directions,
        plan=plan,
        estimator=PooledMeanBaseline(card_hash=CARD_HASH, min_effective_n=3),
        relation_id=RELATION,
    )
    funding = DirectFundingBaseline.from_card(card, min_effective_n=3)
    masked = DirectFundingBaseline.from_card(card, ltifo_def=ltifo, target_id="dtwexbgs", min_effective_n=3)
    assert masked.sources == ("dfii10",)
    assert masked.excluded_sources == ("dtwexbgs",)
    assert "+ltifo-dtwexbgs" in masked.model_version
    members = {
        "candidate": candidate,
        "direct_funding": run_baseline(rows, plan=plan, baseline=funding, relation_id=RELATION),
        "direct_funding_ltifo": run_baseline(rows, plan=plan, baseline=masked, relation_id=RELATION),
    }
    # The card's paired population: origins where every member predicts, restricted
    # explicitly and with the loss quoted -- never the scorer's silent narrowing.
    restricted, dropped = restrict_to_common(members)
    population = PairedPopulation.require(restricted)
    candidate = restricted["candidate"]
    funding_preds = restricted["direct_funding"]
    masked_preds = restricted["direct_funding_ltifo"]
    assert sum(population.per_fold.values()) == len(population.keys) >= 55
    assert max(dropped.values()) <= 5

    disposition = novelty_disposition(candidate, funding_preds, alpha=0.1, mean_test_fn=_t_test)
    masked_disposition = novelty_disposition(candidate, masked_preds, alpha=0.1, mean_test_fn=_t_test)
    candidate_mse = mean_squared_error(candidate)
    funding_mse = mean_squared_error(funding_preds)
    masked_mse = mean_squared_error(masked_preds)
    print(
        "C26 scores:",
        json.dumps(
            {
                "paired_keys": len(population.keys),
                "per_fold": population.per_fold,
                "dropped": dropped,
                "candidate_mse": candidate_mse,
                "direct_funding_mse": funding_mse,
                "direct_funding_ltifo_mse": masked_mse,
                "vs_direct_funding": {k: disposition[k] for k in ("status", "mean_squared_error_improvement", "p_value")},
                "vs_direct_funding_ltifo": {
                    k: masked_disposition[k] for k in ("status", "mean_squared_error_improvement", "p_value")
                },
            },
            sort_keys=True,
        ),
    )
    # Candidate ~= direct_funding: the composite's dollar call is the dollar input itself.
    assert abs(candidate_mse - funding_mse) / funding_mse < 0.25
    assert disposition["status"] == "novelty_withheld"
    # Removing the dollar family strips that information: the masked comparator is far worse,
    # which is exactly why the masked score is a sensitivity and never the v1 result.
    assert masked_mse > 2.5 * funding_mse
    assert masked_disposition["status"] == "novelty_admissible_for_review"

    # Without the canonical HAC judge the disposition abstains with the exact text.
    monkeypatch.setitem(sys.modules, "engine.validation", None)
    abstained = novelty_disposition(candidate, funding_preds, alpha=0.1)
    assert abstained["status"] == "novelty_withheld"
    assert abstained["p_value"] is None
    assert abstained["reason"] == (
        "StatisticalDependencyUnavailable: engine.validation.newey_west_tstat is required "
        "for incremental scoring"
    )


def test_c26_incumbent_on_dollar_sensitive_target_needs_the_direct_funding_control():
    """Same overlap through the shipped incumbent on a registered target (efa -> broad_dollar)."""

    card = load_card(REPO / "research/liquidity_transmission/glt_preregistration_card.v1.json")
    ltifo = load_ltifo_definition(REPO / DEFAULT_LTIFO_PATH)

    def response(h, conditions, direction, rng):
        return -0.01 * conditions["dtwexbgs.d4w_sign"] * math.sqrt(h / 20) + float(rng.normal(0, 0.005))

    rows, plan, directions, _ = _panel(target="efa", response=response)
    incumbent = HierarchicalMeanCurveEstimator(model_version="glt_t14_m1.v1", prior_strength=0, min_effective_n=3)
    candidate = run_direction_partitioned(
        rows, directions=directions, plan=plan, estimator=incumbent, relation_id=RELATION
    )
    funding = run_baseline(
        rows, plan=plan, baseline=DirectFundingBaseline.from_card(card, min_effective_n=3), relation_id=RELATION
    )
    assert ltifo_family_mask(card, ltifo, "efa") == frozenset({"dtwexbgs", "fx_eurusd", "fx_usdjpy"})
    restricted, _ = restrict_to_common({"candidate": candidate, "direct_funding": funding})
    disposition = novelty_disposition(
        restricted["candidate"], restricted["direct_funding"], alpha=0.1, mean_test_fn=_t_test
    )
    assert disposition["paired_keys"] >= 55
    assert disposition["status"] == "novelty_withheld"


# ------------------------------------------------------------------------ LTIFO
def test_ltifo_definition_loads_and_its_hash_recomputes():
    raw = json.loads((REPO / DEFAULT_LTIFO_PATH).read_text(encoding="utf-8"))
    assert raw["definition_hash"] == LTIFO_HASH == ltifo_definition_hash(raw)
    definition = load_ltifo_definition(REPO / DEFAULT_LTIFO_PATH)
    assert definition["card_ref"]["card_hash"] == CARD_HASH
    assert definition["rule"] == (
        "drop the family containing the target from direct-input comparators; report as "
        "sensitivity, never as the v1 result"
    )
    assert definition["v1_card_untouched"] is True
    card = load_card(REPO / "research/liquidity_transmission/glt_preregistration_card.v1.json")
    assert card_hash(card) == card.payload["card_hash"] == CARD_HASH


def test_ltifo_mask_per_target():
    card = load_card(REPO / "research/liquidity_transmission/glt_preregistration_card.v1.json")
    ltifo = load_ltifo_definition(REPO / DEFAULT_LTIFO_PATH)
    assert ltifo_family_mask(card, ltifo, "spy") == frozenset()
    assert ltifo_family_mask(card, ltifo, "tlt") == frozenset({"dfii10"})
    assert ltifo_family_mask(card, ltifo, "lqd") == frozenset({"dfii10", "hy_oas"})
    assert ltifo_family_mask(card, ltifo, "dtwexbgs") == frozenset({"dtwexbgs", "fx_eurusd", "fx_usdjpy"})
    with pytest.raises(ContractError, match="not covered"):
        ltifo_family_mask(card, ltifo, "not_a_target")
    unmasked = DirectFundingBaseline.from_card(card, ltifo_def=ltifo, target_id="spy")
    assert unmasked.sources == ("dtwexbgs", "dfii10") and unmasked.excluded_sources == ()


def test_ltifo_refuses_tampering_and_a_foreign_card():
    card = load_card(REPO / "research/liquidity_transmission/glt_preregistration_card.v1.json")
    ltifo = load_ltifo_definition(REPO / DEFAULT_LTIFO_PATH)
    tampered = json.loads(json.dumps(ltifo))
    tampered["target_family_map"]["spy"] = ["broad_dollar"]
    with pytest.raises(ContractError, match="definition_hash"):
        ltifo_family_mask(card, tampered, "spy")
    foreign = json.loads(json.dumps(ltifo))
    foreign["card_ref"]["card_hash"] = "0" * 64
    foreign["definition_hash"] = ltifo_definition_hash(foreign)
    with pytest.raises(ContractError, match="different card"):
        ltifo_family_mask(card, foreign, "spy")


# ------------------------------------------------------------------ import hygiene
_FORBIDDEN_ROOTS = ("requests", "yfinance", "urllib", "macro", "engine", "httpx", "aiohttp")
_PRICE_READERS = ("build_forward_return_panel", "brain.liquidity_lab.adapter", "brain.liquidity_transmission")


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names.append(module)
            names.extend(f"{module}.{alias.name}" for alias in node.names)
            names.extend(alias.name for alias in node.names)
    return names


@pytest.mark.parametrize("module", NEW_MODULES)
def test_t15_modules_import_no_network_macro_engine_or_ledger(module):
    names = _imports(REPO / "brain" / "liquidity_lab" / module)
    for name in names:
        root = name.split(".")[0]
        assert root not in _FORBIDDEN_ROOTS, (module, name)
        assert "ledger" not in name.split("."), (module, name)


def test_baselines_import_no_price_reader():
    names = _imports(REPO / "brain" / "liquidity_lab" / "baselines.py")
    for reader in _PRICE_READERS:
        assert not any(name == reader or name.startswith(reader + ".") or name.endswith("." + reader) for name in names), reader
