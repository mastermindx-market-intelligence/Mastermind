"""GLT T19 regional transfer challenge (C34, protocol section 9, C22 exclusions).

The tests use synthetic fixtures only:

* the frozen transfer cards in ``research/liquidity_transmission``;
* one synthetic measured china_hk card, re-hashed from the frozen china card;
* hand-built cells and holdout rows, all anchored before the preregistration
  ``reserved_start``.

Nothing here reads ``data/``.
"""

from __future__ import annotations

import dataclasses
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from brain.liquidity_lab import regional_transfer
from brain.liquidity_lab.baselines import PopulationMismatch
from brain.liquidity_lab.contracts import ContractError, canonical_hash
from brain.liquidity_lab.estimator import ResponseCurveCell
from brain.liquidity_lab.preregistration import load_card
from brain.liquidity_lab.regional_transfer import (
    COPIED_US_REASON,
    CalendarMismatchError,
    ExcludedRoleError,
    FutureFixingError,
    FxFixing,
    FxFixingSeries,
    HoldoutResult,
    HoldoutScores,
    LocalCells,
    LocalPriceSeries,
    RegionalTransferError,
    TransferCard,
    TransferHoldouts,
    TransferResult,
    decompose_returns,
    load_transfer_cards,
    qualify_transfer,
)
from brain.liquidity_lab.target_card import BROAD_TARGET_CARD_V1
from brain.liquidity_lab.validation import WalkForwardPrediction
from brain.liquidity_lab.window_guard import WindowGuard

REPO = Path(__file__).resolve().parents[1]
CARD_PATH = REPO / "research/liquidity_transmission/glt_preregistration_card.v1.json"
CARDS_PATH = REPO / "research/liquidity_transmission/glt_transfer_cards.v1.json"
RULES_PATH = REPO / "research/liquidity_transmission/glt_repricing_rules.v1.json"
CARDS_HASH = "032b8bbd21e7361e8ddb2d0ddfc811fd714f803fc1d12cb7e45068fa84fe465a"
CARD_HASH = "da060bf47e8eafc7e94d0cadbb4135c9207a069aad9eef3539ea9d62911d6aee"
UTC = timezone.utc
H = 20
HK_MEMBERS = ("fxi", "mchi", "kweb")
US_MEMBERS = ("spy", "qqq", "smh", "igv", "iwm", "tlt", "hyg", "lqd")
HK_CALENDAR = "hkex_sessions (synthetic fixture calendar)"
US_CALENDAR = "portfolio.market_calendar.is_trading_day (us_equity_sessions)"
LCO_ANCHORS = (date(2009, 3, 2), date(2011, 6, 1), date(2015, 9, 1), date(2018, 2, 1))
LEO_ANCHORS = (
    date(2009, 5, 4),
    date(2010, 8, 2),
    date(2012, 3, 1),
    date(2013, 6, 3),
    date(2014, 4, 1),
    date(2016, 7, 1),
    date(2017, 10, 2),
    date(2019, 2, 1),
    date(2020, 3, 2),
    date(2020, 9, 1),
    date(2021, 4, 1),
    date(2021, 10, 1),
)


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def cards():
    return load_transfer_cards(CARDS_PATH)


@pytest.fixture()
def guard():
    return WindowGuard.from_card(load_card(CARD_PATH))


def _rehash(payload: dict) -> dict:
    body = {k: v for k, v in payload.items() if k != "card_hash"}
    body["card_hash"] = canonical_hash({k: v for k, v in body.items() if k != "card_hash"})
    return body


def _measured_hk(cards, **overrides) -> TransferCard:
    payload = cards["china"].to_dict()
    payload.update(
        region_id="china_hk_synthetic",
        measurement_status="measured",
        local_currency="HKD",
        local_calendar_ref=HK_CALENDAR,
        local_return_series="synthetic HKD total-return fixture",
        missing_owners=[],
    )
    payload.update(overrides)
    return TransferCard.from_dict(_rehash(payload), preregistration_card_hash=CARD_HASH)


def _cell(target, *, h=H, eff=14, mean=0.01, prior_eff=25, family="usd_funding", bucket="all", shrunk=True):
    return ResponseCurveCell(
        target_id=target,
        shock_family=family,
        condition_bucket=bucket,
        horizon_bdays=h,
        sample_n=eff,
        effective_n=eff,
        raw_mean=mean,
        shrunk_mean=mean if shrunk else None,
        interval_low=mean - 0.01 if shrunk else None,
        interval_high=mean + 0.01 if shrunk else None,
        prior_mean=0.0,
        prior_effective_n=prior_eff,
        evidence_state="discovered" if shrunk else "insufficient",
    )


def _local(region_id, targets, *, currency="HKD", calendar=HK_CALENDAR, effs=None):
    effs = effs or [14] * len(targets)
    return LocalCells(
        region_id=region_id,
        currency=currency,
        calendar_ref=calendar,
        cells=tuple(_cell(t, eff=e, mean=0.012) for t, e in zip(targets, effs)),
    )


def _pooled(targets, *, prior_eff=25, shrunk=True):
    return tuple(_cell(t, eff=40, mean=0.008, prior_eff=prior_eff, shrunk=shrunk) for t in targets)


def _row(shock_id, target, anchor, predicted, realized, *, model, h=H):
    return WalkForwardPrediction(
        split_index=anchor.year - 2008,
        relation_id="glt_t19_transfer",
        model_version=model,
        shock_id=shock_id,
        target_id=target,
        horizon_bdays=h,
        anchor_session=anchor,
        exit_session=anchor + timedelta(days=28),
        predicted_return=float(predicted),
        realized_return=float(realized),
        effective_n_at_fit=30,
    )


def _scores(keys, *, local_err, pooled_err):
    pooled, local = [], []
    for i, (shock_id, target, anchor) in enumerate(keys):
        realized = 0.01 * math.sin(i + 1)
        sign = 1 if i % 2 else -1
        local.append(_row(shock_id, target, anchor, realized + sign * local_err, realized, model="local.v1"))
        pooled.append(_row(shock_id, target, anchor, realized + sign * pooled_err, realized, model="pooled.v1"))
    return HoldoutScores(pooled=tuple(pooled), local=tuple(local))


def _lco_keys(members):
    return [(f"lco_{a.isoformat()}", t, a) for a in LCO_ANCHORS for t in members][:12]


def _leo_keys(members):
    return [(f"leo_{a.isoformat()}", members[i % len(members)], a) for i, a in enumerate(LEO_ANCHORS)]


def _holdouts(card, *, lco=(0.001, 0.01), leo=(0.001, 0.01), drop=()):
    members = card.hierarchy_members
    kinds = {}
    if "leave_country_out" not in drop:
        kinds["leave_country_out"] = _scores(_lco_keys(members), local_err=lco[0], pooled_err=lco[1])
    if "leave_era_out" not in drop:
        kinds["leave_era_out"] = _scores(_leo_keys(members), local_err=leo[0], pooled_err=leo[1])
    return TransferHoldouts(plan_hash=card.holdout_plan.plan_hash, **kinds)


def _qualify(card, guard, *, local=None, pooled=None, holdouts="default"):
    local = _local(card.region_id, card.hierarchy_members) if local is None else local
    pooled = _pooled(card.hierarchy_members) if pooled is None else pooled
    holdouts = _holdouts(card) if holdouts == "default" else holdouts
    return qualify_transfer(card, pooled, local, holdouts=holdouts, guard=guard)


def _known(day: date, hour: int = 16) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=UTC)


SESSIONS = (date(2019, 3, 1), date(2019, 3, 4), date(2019, 3, 5), date(2019, 3, 6))


def _hkd_series(calendar=HK_CALENDAR):
    return LocalPriceSeries(
        series_id="synthetic_hkd_fixture",
        currency="HKD",
        calendar_ref=calendar,
        sessions=SESSIONS,
        prices=(100.0, 101.0, 99.5, 102.0),
    )


def _fixings(*, calendar=HK_CALENDAR, dates=SESSIONS, late_known_at=None):
    rates = (0.1274, 0.1275, 0.1273, 0.1276)
    rows = []
    for i, (day, rate) in enumerate(zip(dates, rates)):
        known = _known(day)
        if late_known_at is not None and i == len(dates) - 1:
            known = late_known_at
        rows.append(FxFixing(fixing_date=day, usd_per_local=rate, known_at=known))
    return FxFixingSeries(pair="USDHKD fixture", currency="HKD", calendar_ref=calendar, fixings=tuple(rows))


# ---------------------------------------------------------- frozen cards
def test_transfer_cards_are_frozen_with_their_definition_hash(cards):
    assert cards.definition_hash == CARDS_HASH
    assert cards.preregistration_card_hash == CARD_HASH
    assert cards.region_ids() == ("us", "euro_area", "japan", "china", "hong_kong")
    statuses = {r: cards[r].measurement_status for r in cards.region_ids()}
    assert statuses == {
        "us": "measured",
        "euro_area": "measured",
        "japan": "measured",
        "china": "assumption_only_context",
        "hong_kong": "missing_input",
    }
    for region_id in cards.region_ids():
        card = cards[region_id]
        assert card.fx_fixing_policy == "known_at_only"
        assert card.card_hash == canonical_hash(card.to_dict(include_hash=False))
        plan = card.holdout_plan
        assert (plan.eval_horizon_bdays, plan.local_floor_effective_n, plan.margin) == (20, 10, 0.98)
        assert [e.era_id for e in plan.leave_era_out] == ["e1_2008_2013", "e2_2014_2019", "e3_2020_2021"]
        assert plan.leave_era_out[-1].end < date(2022, 1, 3)
    with pytest.raises(ContractError, match="no transfer card"):
        cards["dm_ex_us"]


def test_a_tampered_card_document_or_card_is_refused(tmp_path):
    document = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    document["cards"][0]["holdout_plan"]["margin"] = 0.9
    tampered = tmp_path / "cards.json"
    tampered.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ContractError, match="definition_hash mismatch"):
        load_transfer_cards(tampered)
    body = {k: v for k, v in document.items() if k != "definition_hash"}
    document["definition_hash"] = canonical_hash(body)
    tampered.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ContractError, match="card_hash mismatch"):
        load_transfer_cards(tampered)


def test_hierarchy_members_come_from_the_registry(cards):
    registry_us = tuple(
        t for t in BROAD_TARGET_CARD_V1.target_ids() if BROAD_TARGET_CARD_V1.entry(t).region == "us"
    )
    assert set(cards["us"].hierarchy_members) == set(registry_us)
    assert set(cards["china"].hierarchy_members) == set(HK_MEMBERS)
    assert cards["euro_area"].hierarchy_members == ()
    with pytest.raises(ContractError, match="must equal the registry targets"):
        _measured_hk(cards, hierarchy_members=["fxi", "mchi"], holdout_plan={
            **cards["china"].holdout_plan.to_dict(), "leave_country_out": ["fxi", "mchi"]
        })


def test_c22_btc_and_baba_raise_excluded_role_error_from_the_registry(cards, guard):
    for target_id in ("btc", "baba"):
        with pytest.raises(ExcludedRoleError, match="is excluded from") as excinfo:
            regional_transfer._registry_entry(target_id)
        assert isinstance(excinfo.value.__cause__, ContractError)
    with pytest.raises(ExcludedRoleError, match="unknown id, or a role other than"):
        regional_transfer._registry_entry("aapl")
    with pytest.raises(ExcludedRoleError):
        _measured_hk(cards, hierarchy_members=["fxi", "mchi", "baba"])
    card = _measured_hk(cards)
    with pytest.raises(ExcludedRoleError):
        _qualify(card, guard, pooled=_pooled(HK_MEMBERS) + _pooled(("btc",)))
    with pytest.raises(ExcludedRoleError):
        _qualify(card, guard, local=_local(card.region_id, ("fxi", "baba")))


# ------------------------------------------------------- local / FX legs
def test_decomposition_splits_local_and_fx_legs():
    cutoff = _known(SESSIONS[-1], 20)
    result = decompose_returns(_hkd_series(), _fixings(), known_at=cutoff)
    assert result.local_ccy_return == pytest.approx(math.log(102.0 / 100.0))
    assert result.fx_return == pytest.approx(math.log(0.1276 / 0.1274))
    assert result.usd_return == pytest.approx(result.local_ccy_return + result.fx_return, abs=1e-15)
    assert result.fixing_known_at == _known(SESSIONS[-1])
    usd = LocalPriceSeries("spy_fixture", "USD", US_CALENDAR, SESSIONS, (100.0, 100.5, 101.0, 99.0))
    plain = decompose_returns(usd, None, known_at=cutoff)
    assert (plain.fx_return, plain.fixing_known_at) == (0.0, None)
    with pytest.raises(ContractError, match="no USD fallback"):
        decompose_returns(_hkd_series(), None, known_at=cutoff)
    with pytest.raises(RegionalTransferError, match="after known_at"):
        decompose_returns(_hkd_series(), _fixings(), known_at=_known(SESSIONS[-2], 20))


def test_c34_a_future_fx_fixing_raises_future_fixing_error():
    cutoff = _known(SESSIONS[-1], 20)
    late = _fixings(late_known_at=cutoff + timedelta(hours=2))
    with pytest.raises(FutureFixingError, match="is after known_at"):
        decompose_returns(_hkd_series(), late, known_at=cutoff)
    ahead = _fixings(dates=SESSIONS[:-1] + (date(2019, 3, 7),))
    with pytest.raises(FutureFixingError):
        decompose_returns(_hkd_series(), ahead, known_at=cutoff)


def test_c34_a_mixed_calendar_join_raises_calendar_mismatch_error(cards, guard):
    cutoff = _known(SESSIONS[-1], 20)
    with pytest.raises(CalendarMismatchError, match="fixing calendar"):
        decompose_returns(_hkd_series(), _fixings(calendar="ldn_fx_sessions (synthetic)"), known_at=cutoff)
    gapped = _fixings(dates=(SESSIONS[0], date(2019, 3, 2), SESSIONS[2], SESSIONS[3]))
    with pytest.raises(CalendarMismatchError, match="no forward-fill"):
        decompose_returns(_hkd_series(), gapped, known_at=cutoff)
    card = _measured_hk(cards)
    us_calendar_cells = _local(card.region_id, HK_MEMBERS, calendar="us_equity_sessions")
    with pytest.raises(CalendarMismatchError):
        _qualify(card, guard, local=us_calendar_cells)


# ------------------------------------------------- section 9: missing input
@pytest.mark.parametrize("region_id", ["euro_area", "japan", "china", "hong_kong"])
def test_missing_input_region_carries_no_cell_mean_or_probability(cards, guard, region_id):
    card = cards[region_id]
    result = qualify_transfer(
        card,
        _pooled(US_MEMBERS + HK_MEMBERS),
        _local(region_id, HK_MEMBERS if card.hierarchy_members else ()),
        holdouts=None,
        guard=guard,
    )
    assert result.status == "missing_input"
    for name in (
        "pooled_vs_local",
        "leave_country_out",
        "leave_era_out",
        "coverage",
        "local_effective_n",
        "borrowed_prior_effective_n",
    ):
        assert getattr(result, name) is None
    owners = [r for r in result.reasons if r.startswith("missing_owner:")]
    assert owners and len(owners) == len(card.missing_owners)
    if card.measurement_status != "measured":
        assert f"t10_status:{card.measurement_status}" in result.reasons
    payload = json.dumps(result.to_payload())
    assert "probability" not in payload and "mean" not in payload
    assert guard.refused_count == 0 and guard.admitted_count == 0


@pytest.mark.parametrize("region_id", ["euro_area", "japan", "china", "hong_kong"])
def test_a_us_cell_passed_as_local_is_refused_as_copied_us_probability(cards, guard, region_id):
    spy_as_local = LocalCells(
        region_id=region_id, currency="USD", calendar_ref="us_equity_sessions", cells=(_cell("spy"),)
    )
    result = qualify_transfer(
        cards[region_id], _pooled(US_MEMBERS), spy_as_local, holdouts=None, guard=guard
    )
    assert result.status == "missing_input"
    assert COPIED_US_REASON in result.reasons
    assert result.local_effective_n is None and result.pooled_vs_local is None
    assert "spy" not in json.dumps(result.to_payload())


def test_a_us_cell_in_a_measured_region_abstains_and_is_named(cards, guard):
    card = _measured_hk(cards)
    result = _qualify(card, guard, local=_local(card.region_id, ("fxi", "spy")))
    assert result.status == "abstain"
    assert result.reasons == ("outside_hierarchy:spy", COPIED_US_REASON)
    usd_cells = _local(card.region_id, HK_MEMBERS, currency="USD")
    result = _qualify(card, guard, local=usd_cells)
    assert result.status == "abstain"
    assert result.reasons == ("local_currency_mismatch:USD!=HKD", COPIED_US_REASON)


# ------------------------------------------------------- hierarchy / floor
def test_a_region_outside_the_registered_hierarchy_abstains(cards, guard):
    card = _measured_hk(cards)
    result = _qualify(card, guard, local=_local(card.region_id, ("fxi", "efa")))
    assert (result.status, result.reasons) == ("abstain", ("outside_hierarchy:efa",))
    assert result.local_effective_n is None
    no_registry = _measured_hk(
        cards,
        region_id="euro_area_synthetic",
        local_currency="EUR",
        registry_region=None,
        hierarchy_members=[],
        holdout_plan={**cards["euro_area"].holdout_plan.to_dict()},
    )
    result = _qualify(no_registry, guard, local=_local(no_registry.region_id, (), currency="EUR"), holdouts=None)
    assert (result.status, result.reasons) == ("abstain", ("no_registered_hierarchy",))


def test_local_effective_n_below_the_floor_abstains(cards, guard):
    card = _measured_hk(cards)
    result = _qualify(card, guard, local=_local(card.region_id, HK_MEMBERS, effs=[6, 4, 3]))
    assert result.status == "abstain"
    assert result.reasons == ("local_effective_n_below_floor:6<10",)
    assert (result.local_effective_n, result.borrowed_prior_effective_n) == (6, 25)
    assert result.leave_country_out is None and guard.admitted_count == 0


# ------------------------------------------------ C34: the frozen holdouts
def test_c34_missing_either_holdout_abstains_with_a_reason(cards, guard):
    card = _measured_hk(cards)
    for drop, reasons in (
        (("leave_era_out",), ("missing_holdout:leave_era_out",)),
        (("leave_country_out",), ("missing_holdout:leave_country_out",)),
    ):
        result = _qualify(card, guard, holdouts=_holdouts(card, drop=drop))
        assert (result.status, result.reasons) == ("abstain", reasons)
    result = _qualify(card, guard, holdouts=None)
    assert result.reasons == ("missing_holdout:leave_country_out", "missing_holdout:leave_era_out")
    assert guard.admitted_count == 0 and guard.refused_count == 0


def test_a_holdout_scored_under_another_plan_abstains(cards, guard):
    card = _measured_hk(cards)
    stale = dataclasses.replace(_holdouts(card), plan_hash="0" * 64)
    result = _qualify(card, guard, holdouts=stale)
    assert (result.status, result.reasons) == ("abstain", ("holdout_plan_hash_mismatch",))


def test_supported_local_only_when_local_wins_both_holdouts(cards, guard):
    card = _measured_hk(cards)
    result = _qualify(card, guard)
    assert result.status == "supported_local" and result.reasons == ()
    assert result.leave_country_out.local_beats_pooled and result.leave_era_out.local_beats_pooled
    assert result.leave_country_out.n_paired_keys == 12 and result.leave_era_out.n_paired_keys == 12
    assert dict(result.leave_era_out.per_group) == {"e1_2008_2013": 4, "e2_2014_2019": 4, "e3_2020_2021": 4}
    assert result.uncertainty_kind == "pointwise"
    split = _qualify(card, guard, holdouts=_holdouts(card, leo=(0.01, 0.001)))
    assert split.status == "pooled_only_borrowed"
    assert split.reasons == ("local_did_not_beat_pooled:leave_era_out",)
    assert split.leave_country_out.local_beats_pooled and not split.leave_era_out.local_beats_pooled


def test_pooled_only_borrowed_keeps_borrowed_support_separate(cards, guard):
    card = _measured_hk(cards)
    local = _local(card.region_id, HK_MEMBERS, effs=[14, 12, 11])
    result = _qualify(card, guard, local=local, holdouts=_holdouts(card, lco=(0.01, 0.001), leo=(0.01, 0.001)))
    assert result.status == "pooled_only_borrowed"
    assert result.local_effective_n == 14
    assert result.borrowed_prior_effective_n == 25
    assert result.local_effective_n not in (14 + 25, 14 + 12 + 11)
    assert {r.target_id for r in result.pooled_vs_local.rows} == set(HK_MEMBERS)
    payload = result.to_payload()
    assert (payload["local_effective_n"], payload["borrowed_prior_effective_n"]) == (14, 25)
    no_pool = _qualify(
        card, guard, local=local, pooled=_pooled(HK_MEMBERS, shrunk=False),
        holdouts=_holdouts(card, lco=(0.01, 0.001)),
    )
    assert no_pool.status == "abstain"
    assert no_pool.reasons == ("local_did_not_beat_pooled:leave_country_out", "no_pooled_cell")


def test_too_few_paired_keys_never_wins_a_holdout(cards, guard):
    card = _measured_hk(cards)
    holdouts = _holdouts(card)
    short = HoldoutScores(pooled=holdouts.leave_era_out.pooled[:6], local=holdouts.leave_era_out.local[:6])
    result = _qualify(card, guard, holdouts=dataclasses.replace(holdouts, leave_era_out=short))
    assert result.status == "pooled_only_borrowed"
    assert result.reasons == ("too_few_paired_keys:leave_era_out:6<10",)


def test_window_guard_refusals_are_counted_and_never_scored(cards, guard):
    card = _measured_hk(cards)
    holdouts = _holdouts(card)
    early = _scores([("pre_window", "fxi", date(2006, 6, 1))], local_err=0.5, pooled_err=0.0)
    lco = HoldoutScores(
        pooled=holdouts.leave_country_out.pooled + early.pooled,
        local=holdouts.leave_country_out.local + early.local,
    )
    result = _qualify(card, guard, holdouts=dataclasses.replace(holdouts, leave_country_out=lco))
    assert result.leave_country_out.refused_by_guard == 2
    assert result.leave_country_out.n_paired_keys == 12
    assert result.status == "supported_local"
    assert guard.refused_count == 2
    assert {r.reason for r in guard.refusals} == {"before_train_start"}


def test_a_guard_from_another_card_is_refused(cards, guard):
    card = _measured_hk(cards)
    with pytest.raises(ContractError, match="another preregistration card"):
        _qualify(card, dataclasses.replace(guard, card_hash="f" * 64))


def test_holdout_rows_must_match_the_frozen_plan(cards, guard):
    card = _measured_hk(cards)
    holdouts = _holdouts(card)
    wrong_h = _scores([("h40", "fxi", date(2010, 3, 1))], local_err=0.0, pooled_err=0.0)
    wrong_h = HoldoutScores(
        pooled=tuple(dataclasses.replace(r, horizon_bdays=40) for r in wrong_h.pooled),
        local=tuple(dataclasses.replace(r, horizon_bdays=40) for r in wrong_h.local),
    )
    with pytest.raises(ContractError, match="eval horizon"):
        _qualify(card, guard, holdouts=dataclasses.replace(holdouts, leave_country_out=wrong_h))
    not_member = _scores([("nm", "spy", date(2010, 3, 1))], local_err=0.0, pooled_err=0.0)
    with pytest.raises(ContractError, match="not a held-out member"):
        _qualify(card, guard, holdouts=dataclasses.replace(holdouts, leave_country_out=not_member))
    gap_day = _scores([("gap", "fxi", date(2014, 1, 1))], local_err=0.0, pooled_err=0.0)
    with pytest.raises(ContractError, match="outside every frozen era"):
        _qualify(card, guard, holdouts=dataclasses.replace(holdouts, leave_era_out=gap_day))


def test_asymmetric_holdout_keys_are_refused(cards, guard):
    card = _measured_hk(cards)
    holdouts = _holdouts(card)
    lopsided = HoldoutScores(
        pooled=holdouts.leave_country_out.pooled, local=holdouts.leave_country_out.local[:-1]
    )
    with pytest.raises(PopulationMismatch):
        _qualify(card, guard, holdouts=dataclasses.replace(holdouts, leave_country_out=lopsided))


def test_changing_one_regions_inputs_cannot_change_another_regions_result(cards, guard):
    hk = _measured_hk(cards)
    us = cards["us"]
    us_local = _local("us", US_MEMBERS, currency="USD", calendar=US_CALENDAR)
    first = _qualify(hk, guard).to_payload()
    us_before = _qualify(us, guard, local=us_local).to_payload()
    _qualify(
        us,
        guard,
        local=_local("us", US_MEMBERS, currency="USD", calendar=US_CALENDAR, effs=[3] * 8),
        pooled=_pooled(US_MEMBERS, prior_eff=99),
        holdouts=_holdouts(us, lco=(0.05, 0.0), leo=(0.05, 0.0)),
    )
    again = qualify_transfer(
        hk,
        _pooled(HK_MEMBERS) + _pooled(US_MEMBERS, prior_eff=99),
        _local(hk.region_id, HK_MEMBERS),
        holdouts=_holdouts(hk),
        guard=guard,
    ).to_payload()
    assert again == first
    assert _qualify(us, guard, local=us_local).to_payload() == us_before
    assert us_before["status"] == "supported_local" and COPIED_US_REASON not in us_before["reasons"]


# ------------------------------------------------------------ contracts
def test_local_cells_of_another_region_are_refused(cards, guard):
    card = _measured_hk(cards)
    with pytest.raises(ContractError, match="cannot qualify"):
        _qualify(card, guard, local=_local("japan", HK_MEMBERS))


def test_result_contract_refuses_inconsistent_states(cards, guard):
    card = _measured_hk(cards)
    base = _qualify(card, guard)
    with pytest.raises(ContractError, match="carries no number"):
        dataclasses.replace(base, status="missing_input", reasons=("t10_status:missing_input",))
    lost = dataclasses.replace(
        base.leave_era_out, local_beats_pooled=False, reason="local_did_not_beat_pooled:leave_era_out"
    )
    with pytest.raises(ContractError, match="BOTH frozen holdouts"):
        dataclasses.replace(base, leave_era_out=lost)
    with pytest.raises(ContractError, match="pointwise"):
        dataclasses.replace(base, uncertainty_kind="hac")
    with pytest.raises(ContractError, match="names its reasons"):
        TransferResult(
            region_id="x", status="abstain", card_hash="h", plan_hash="p", pooled_vs_local=None,
            leave_country_out=None, leave_era_out=None, coverage=None, local_effective_n=None,
            borrowed_prior_effective_n=None,
        )
    with pytest.raises(ContractError, match="contradicts"):
        dataclasses.replace(base.leave_country_out, local_mse=1.0, pooled_mse=0.5)
    assert isinstance(base.leave_country_out, HoldoutResult)


def test_module_language_avoids_the_forbidden_terms():
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    source = Path(regional_transfer.__file__).read_text(encoding="utf-8").lower()
    for term in rules["language"]["forbidden_terms"]:
        assert term not in source
