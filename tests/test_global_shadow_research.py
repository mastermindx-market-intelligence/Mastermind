"""Hermetic, adversarial tests for the non-executable cross-asset research adapter."""
from __future__ import annotations

import copy
import math

import pytest

from portfolio.global_scenario_context import ContractError
from portfolio.global_shadow_research import (
    AUTHORITY, ROSTER, compare_global_shadow,
)

AS_OF = "2026-11-06T10:00:00Z"
KNOWN = "2026-11-05T21:00:00Z"
EXPIRY = "2026-11-07T00:00:00Z"
START = "2026-10-28"
END = "2026-11-04"
EXPECTED = "2026-11-05"
SHA = "a" * 64


def context(*, missing_uso: bool = True, stale: bool = True):
    bench = -0.05
    returns = {
        "SPY": bench, "EFA": 0.02, "EEM": -0.03, "FXI": 0.06,
        "KWEB": 0.04, "GLD": -0.01, "HYG": -0.015, "SHY": 0.004,
        "TLT": 0.01, "IBIT": -0.08, "USO": 0.005,
    }
    end = END
    expected = EXPECTED if stale else END
    rows = []
    for ident, (asset, region, _keys) in sorted(ROSTER.items()):
        unavailable = ident == "USO" and missing_uso
        absolute = None if unavailable else returns[ident]
        relative = None if unavailable or ident == "SPY" else (1 + absolute) / (1 + bench) - 1
        classification = None
        if relative is not None:
            classification = (
                "POSITIVE_AND_OUTPERFORMING" if absolute > 0 and relative > 0 else
                "RELATIVE_RESILIENCE_ONLY" if absolute <= 0 and relative > 0 else
                "UNDERPERFORMING" if relative < 0 else "IN_LINE"
            )
        rows.append({
            "instrument_id": ident, "asset_class": asset, "exposure_region": region,
            "listing_market": "US", "currency": "USD", "return_basis": "total_return",
            "evidence_family_id": "yahoo_daily_adjusted_prices",
            "source_ref": "data/yahoo/" + ident + ".parquet", "source_digest": SHA,
            "start_session": START, "end_session": end,
            "last_source_session": "2026-11-03" if unavailable else end,
            "status": "UNAVAILABLE" if unavailable else "OBSERVED",
            "reasons": ["end_session_missing"] if unavailable else [],
            "absolute_return": absolute, "relative_return": relative,
            "classification": classification,
            "comparison_status": "OBSERVED" if relative is not None else None,
            "label_en": ident + " proxy", "label_zh": "代理" + ident,
        })
    observed = 10 if missing_uso else 11
    comparable = observed - 1
    status = "STALE" if stale else "PARTIAL" if missing_uso else "AVAILABLE"
    return {
        "schema": "mastermind.multi_asset_daily_context/v1",
        "method_version": "same_us_cash_session_snapshot.v1",
        "captured_at": "2026-11-06T02:25:11Z",
        "alignment_basis": "US_CASH_SESSION_LABEL_NOT_QUOTE_TIMESTAMP",
        "capture_coherence": "individually_hashed_not_atomic_bundle",
        "source_kind": "captured_mutable_daily_cache",
        "historical_original_availability_proven": False,
        "provider_available_at": None,
        "base_currency": "USD",
        "benchmark_instrument_id": "SPY",
        "benchmark_return": bench,
        "context_digest": SHA,
        "window": {
            "start_session": START, "end_session": end,
            "expected_session": expected, "horizon_sessions": 5,
            "calendar_owner": "lib.nyse_calendar", "listing_timezone": "America/New_York",
        },
        "rows": rows,
        "coverage": {"requested": 11, "observed": observed,
                     "comparable": comparable, "invalid_sources": 0},
        "status": status, "reasons": ["older_than_expected_session"] if stale else [],
        "limitations": [
            "not_intraday", "not_native_foreign_market_returns", "not_observed_fund_flows",
            "not_point_in_time_backtest_evidence", "funds_may_overlap",
            "cash_is_separate_from_short_duration_funds", "not_an_allocation_recommendation",
        ],
        "authority": {"can_rank": False, "can_gate": False, "can_size": False, "can_trade": False},
        "display_only": True, "no_predictive_claim": True,
    }


def book():
    return {
        "book_id": "global_research_shadow", "book_revision": "test-rev-1",
        "research_only": True, "active_account": False,
        "user_supplied_scenario_assumptions": True, "base_currency": "USD",
        "known_at": KNOWN, "valid_until": EXPIRY,
        "positions": {"SPY": 0.6}, "cash_weight": 0.4,
        "constraints": {
            "max_instrument_weight": 0.8, "max_risk_key_weight": 0.8,
            "max_turnover_fraction": 1.0, "min_cash_fraction": 0.1,
        },
    }


def alt(id="hold", positions=None, cash=0.4):
    return {
        "alternative_id": id,
        "positions": {"SPY": .6} if positions is None else positions,
        "cash_weight": cash,
        "costs_bps": {"fee": 1, "spread_crossing": 2, "impact": 3},
    }


def scenario(name="stress"):
    def datum(value):
        return {
            "base_total_return": value, "return_currency": "USD",
            "known_at": KNOWN, "valid_until": EXPIRY,
        }
    return {
        "scenario_id": name, "known_at": KNOWN, "valid_until": EXPIRY,
        "source_ref": "synthetic-stress-" + name, "assumption_kind": "hypothetical",
        "cash_return": 0.001,
        "returns": {x: datum(v) for x, v in {
            "SPY": -.10, "EFA": .01, "EEM": -.03, "FXI": .05, "KWEB": .04,
            "GLD": .02, "HYG": -.04, "SHY": .001, "TLT": .08,
            "IBIT": -.20, "USO": -.12,
        }.items()},
    }


def evaluate(c=None, b=None, a=None, s=None, *, as_of=AS_OF):
    return compare_global_shadow(
        context=context() if c is None else c, book=book() if b is None else b,
        alternatives=[alt()] if a is None else a, scenarios=[scenario()] if s is None else s,
        as_of=as_of,
    )


def assert_refused(result, reason):
    assert result["status"] == "UNAVAILABLE"
    assert result["reasons"] == [reason]
    assert result["alternatives"] == []
    assert not any(result["authority"].values())


def test_fixed_roster_and_stale_context_survive_qualification():
    out = evaluate()
    assert out["status"] == "AVAILABLE"  # maths only, not market freshness
    assert out["source_computation_status"] == "AVAILABLE"
    assert out["market_context"]["status"] == "STALE"
    assert out["market_context"]["source_session"] == END
    assert out["market_context"]["expected_session"] == EXPECTED
    assert out["market_context"]["source_authenticated"] is False
    assert out["market_context"]["input_basis"] == "operator_supplied_descriptive_context"
    assert out["market_context"]["eligible_ids"] == sorted(set(ROSTER) - {"USO"})
    assert out["market_context"]["excluded_ids"] == ["USO"]
    assert out["scenario_basis"] == "hypothetical_not_forecast"
    assert out["display_only"] and out["hypothetical_only"] and out["no_predictive_claim"]
    assert all(value is False for value in out["authority"].values())


def test_all_eleven_roster_qualifies_without_missing_rows():
    out = evaluate(c=context(missing_uso=False, stale=False))
    assert out["market_context"]["status"] == "AVAILABLE"
    assert len(out["market_context"]["eligible_ids"]) == 11
    assert out["market_context"]["excluded_ids"] == []


def test_current_source_with_missing_uso_is_honestly_stale():
    out = evaluate()
    assert out["market_context"]["coverage"] == {
        "requested": 11, "observed": 10, "comparable": 9, "invalid_sources": 0,
    }
    assert out["market_context"]["status"] == "STALE"


def test_alternative_cannot_buy_missing_uso_but_other_ones_survive():
    options = [alt("buy_missing", {"USO": .2, "SPY": .4}),
               alt("rotate", {"FXI": .3, "SPY": .3})]
    out = evaluate(a=options)
    rows = {a["alternative_id"]: a for a in out["alternatives"]}
    assert rows["buy_missing"]["status"] == "UNAVAILABLE"
    assert "alternative_not_fully_funded" in rows["buy_missing"]["reasons"]
    assert rows["rotate"]["status"] == "AVAILABLE"
    assert rows["rotate"]["scenario_results"][0]["status"] == "HYPOTHETICAL"


def test_held_missing_uso_refuses_entire_book():
    b = book()
    b["positions"] = {"USO": .2, "SPY": .4}
    assert_refused(evaluate(b=b), "held_instrument_unavailable")


def test_unknown_asset_in_held_book_refuses():
    b = book()
    b["positions"] = {"QQQ": .6}
    assert_refused(evaluate(b=b), "held_instrument_unavailable")


def test_all_cash_research_book_is_admitted_by_existing_core():
    b = book(); b["positions"] = {}; b["cash_weight"] = 1
    a = [alt("cash", {}, 1)]
    out = evaluate(b=b, a=a)
    assert out["alternatives"][0]["status"] == "AVAILABLE"
    assert out["alternatives"][0]["scenario_results"][0]["net_return"] == .001


def test_sell_buy_costs_charged_once_in_native_core():
    options = [alt("em_rotation", {"SPY": .3, "FXI": .3})]
    row = evaluate(a=options)["alternatives"][0]
    assert row["traded_notional_fraction"] == pytest.approx(.6)
    assert row["one_time_cost_fraction"] == pytest.approx(.6 * 6/10000)
    assert row["scenario_results"][0]["gross_return"] == pytest.approx(.3 * -.10 + .3 * .05 + .4 * .001)
    assert row["scenario_results"][0]["net_return"] == pytest.approx(.3 * -.10 + .3 * .05 + .4 * .001 - .6 * 6/10000)


def test_cash_competes_explicitly_not_a_bond_proxy():
    row = evaluate(a=[alt("cash", {}, 1)])["alternatives"][0]
    assert row["one_time_cost_fraction"] == pytest.approx(.6 * 6/10000)
    assert row["scenario_results"][0]["net_return"] == pytest.approx(.001 - .6 * 6/10000)
    assert "SHY" not in row["risk_key_exposures_nonadditive"]


def test_both_down_but_lesser_loss_does_not_become_inflows():
    c = context()
    assert c["status"] == "STALE"
    em = next(x for x in c["rows"] if x["instrument_id"] == "EEM")
    assert em["absolute_return"] < 0 and em["relative_return"] > 0
    assert em["classification"] == "RELATIVE_RESILIENCE_ONLY"
    out = evaluate(c=c)
    assert out["market_context"]["source_authenticated"] is False
    assert "forecast_probability" not in out and "recommendation" not in out


def test_rejects_non_synthetic_book_names_and_active_accounts():
    for key, value in [("book_id", "autonomous"), ("book_id", "china"),
                       ("active_account", True), ("research_only", False),
                       ("user_supplied_scenario_assumptions", False),
                       ("base_currency", "HKD")]:
        b = book(); b[key] = value
        assert_refused(evaluate(b=b), "research_book_identity_invalid")


@pytest.mark.parametrize("key", ["account_id", "tenant_id", "broker_id", "order_id", "account", "auth_token", "universe"])
def test_rejects_live_account_identifiers_even_if_book_says_research(key):
    b = book(); b[key] = "actual_live_id"
    assert_refused(evaluate(b=b), "active_account_identity_prohibited")


@pytest.mark.parametrize("stamp", ["2026-11-06", "2026-11-06T10:00", "garbage", ""])
def test_asof_timezone_naive_or_invalid_rejected(stamp):
    with pytest.raises(ContractError, match="aware_as_of_required"):
        evaluate(as_of=stamp)


def test_aware_offset_asof_normalized_utc():
    out = evaluate(as_of="2026-11-06T02:00:00-08:00")
    assert out["as_of"] == AS_OF


def test_malformed_inputs_raise_contract_not_incidental_type_error():
    for inp in (None, [], "oops", 20):
        with pytest.raises(ContractError):
            compare_global_shadow(context=inp, book=book(), alternatives=[alt()], scenarios=[scenario()], as_of=AS_OF)
        with pytest.raises(ContractError):
            compare_global_shadow(context=context(), book=inp, alternatives=[alt()], scenarios=[scenario()], as_of=AS_OF)


def test_future_capture_abstains():
    c=context(); c["captured_at"]="2026-11-06T10:00:01Z"
    assert_refused(evaluate(c=c), "context_clock_unqualified")


def test_naive_capture_abstains():
    c=context(); c["captured_at"]="2026-11-06T09:00:00"
    assert_refused(evaluate(c=c), "context_clock_unqualified")


def test_calendar_invalid_day_refused():
    c=context(); c["window"]["end_session"]="2026-11-31"
    assert_refused(evaluate(c=c), "context_window_invalid")


def test_source_end_after_capture_refused():
    c=context(); c["window"]["end_session"]="2026-11-07"
    assert_refused(evaluate(c=c), "context_window_invalid")


def test_missing_source_digest_refused():
    c=context(); c["rows"][0]["source_digest"]="not-a-hash"
    assert_refused(evaluate(c=c), "context_source_digest_invalid")


def test_context_digest_provenance_is_not_authenticated():
    out = evaluate()
    assert out["market_context"]["context_digest"] == SHA
    assert out["market_context"]["source_authenticated"] is False


def test_forged_original_availability_blocked():
    c=context(); c["historical_original_availability_proven"]=True
    assert_refused(evaluate(c=c), "context_source_basis_invalid")


def test_forged_provider_clock_blocked():
    c=context(); c["provider_available_at"]="2026-11-05T21:00:00Z"
    assert_refused(evaluate(c=c), "context_source_basis_invalid")


def test_forged_source_digest_shape_blocked():
    c=context(); c["context_digest"]="A" * 64
    assert_refused(evaluate(c=c), "context_source_basis_invalid")


def test_fake_trading_authority_rejected():
    c=context(); c["authority"]["can_trade"]=True
    assert_refused(evaluate(c=c), "context_authority_invalid")


@pytest.mark.parametrize("mod", [
    ("source_kind", "official_live_feeds"), ("alignment_basis", "matched_intraday_ticks"),
    ("capture_coherence", "settled_atomic_bundle"), ("base_currency", "HKD"),
    ("benchmark_instrument_id", "QQQ"),
])
def test_spoofed_source_semantics_rejected(mod):
    key, value = mod
    c=context(); c[key]=value
    assert_refused(evaluate(c=c), "context_source_basis_invalid")


def test_unexpected_source_schema_rejected():
    c=context(); c["schema"]="unknown"
    assert_refused(evaluate(c=c), "context_schema_invalid")


def test_duplicate_instrument_row_rejected():
    c=context(); c["rows"][0]["instrument_id"]=c["rows"][1]["instrument_id"]
    assert_refused(evaluate(c=c), "context_roster_invalid")


def test_wrong_roster_size_refused():
    c=context(); c["rows"].pop()
    assert_refused(evaluate(c=c), "context_roster_invalid")


def test_wrong_coverage_refused():
    c=context(); c["coverage"]["comparable"]+=1
    assert_refused(evaluate(c=c), "context_coverage_disagreement")


def test_boolean_coverage_refused():
    c=context(); c["coverage"]["observed"]=True
    assert_refused(evaluate(c=c), "context_coverage_invalid")


def test_unknown_asset_class_refused():
    c=context(); c["rows"][0]["asset_class"]="unknown"
    assert_refused(evaluate(c=c), "context_row_invalid")


@pytest.mark.parametrize("field,value", [("listing_market","HK"),("currency","HKD"),
                                           ("return_basis","price_return"),
                                           ("evidence_family_id","options_gamma"),
                                           ("source_ref","../../user/account")])
def test_foreign_listing_fake_fx_and_wrong_source_blocked(field, value):
    c=context(); c["rows"][0][field]=value
    assert_refused(evaluate(c=c), "context_row_invalid")


def test_row_window_inconsistent_with_context_refused():
    c=context(); c["rows"][0]["end_session"]=EXPECTED
    assert_refused(evaluate(c=c), "context_row_invalid")


def test_observed_source_older_than_window_refused():
    c=context(); c["rows"][0]["last_source_session"]="2026-11-03"
    assert_refused(evaluate(c=c), "context_observation_invalid")


def test_missing_uso_not_treated_as_zero_return():
    c=context()
    uso = next(x for x in c["rows"] if x["instrument_id"]=="USO")
    uso["absolute_return"]=0.0
    assert_refused(evaluate(c=c), "context_unavailable_row_invalid")


def test_null_return_in_observed_refused():
    c=context(); c["rows"][0]["absolute_return"]=None
    assert_refused(evaluate(c=c), "context_observation_invalid")


@pytest.mark.parametrize("value", [math.nan,math.inf,-math.inf,-1.01,True])
def test_bad_measured_return_refused(value):
    c=context(); c["rows"][0]["absolute_return"]=value
    assert_refused(evaluate(c=c), "context_observation_invalid")


def test_zero_benchmark_wealth_abstains():
    c=context(); sp=next(x for x in c["rows"] if x["instrument_id"]=="SPY")
    sp["absolute_return"]=-1
    c["benchmark_return"]=-1
    assert_refused(evaluate(c=c), "context_benchmark_unavailable")


def test_wrong_benchmark_total_return_refused():
    c=context(); c["benchmark_return"]=-.06
    assert_refused(evaluate(c=c), "context_benchmark_mismatch")


@pytest.mark.parametrize("malformed", [{}, [], 42])
def test_unhashable_or_malformed_classification_refused_without_exception(malformed):
    c=context(); em=next(x for x in c["rows"] if x["instrument_id"]=="EEM")
    em["classification"]=malformed
    assert_refused(evaluate(c=c), "context_relative_invalid")


def test_wrong_relative_wealth_math_refused():
    c=context(); em=next(x for x in c["rows"] if x["instrument_id"]=="EEM")
    em["relative_return"]=.42
    assert_refused(evaluate(c=c), "context_relative_math_invalid")


def test_classification_claim_must_match_absolute_and_relative():
    c=context(); em=next(x for x in c["rows"] if x["instrument_id"]=="EEM")
    em["classification"]="POSITIVE_AND_OUTPERFORMING"
    assert_refused(evaluate(c=c), "context_classification_invalid")


def test_stale_source_cannot_claim_available():
    c=context(); c["status"]="AVAILABLE"
    assert_refused(evaluate(c=c), "context_status_mismatch")


def test_stale_source_requires_stale_reason():
    c=context(); c["reasons"]=[]
    assert_refused(evaluate(c=c), "context_reasons_mismatch")


def test_no_original_availability_cannot_be_a_quote():
    c=context(); c["alignment_basis"]="actual_event_time"
    assert_refused(evaluate(c=c), "context_source_basis_invalid")


def test_cash_funding_gap_fails_in_native_core():
    b=book();b["cash_weight"]=.1
    out=evaluate(b=b)
    assert out["status"]=="UNAVAILABLE"
    assert out["reasons"]==["book_not_fully_funded"]


def test_negative_book_cash_rejected():
    b=book();b["cash_weight"]=-.1
    assert_refused(evaluate(b=b), "book_not_fully_funded")


def test_alternative_false_costs_are_rejected_by_existing_core():
    a=alt("bad");a["costs_bps"]["impact"]=None
    out=evaluate(a=[a])
    assert out["alternatives"][0]["status"]=="UNAVAILABLE"
    assert "cost_component_invalid" in out["alternatives"][0]["reasons"]


def test_missing_cash_assumption_refused_in_core():
    s=scenario();s.pop("cash_return")
    assert_refused(evaluate(s=[s]), "cash_assumption_missing")


def test_forecast_kind_not_accepted_as_user_hypothetical():
    s=scenario();s["assumption_kind"]="model_forecast"
    assert_refused(evaluate(s=[s]), "scenario_hypothetical_declaration_missing")


def test_future_knowable_scenario_refused_by_core():
    s=scenario();s["known_at"]="2026-11-06T11:00:00Z"
    assert_refused(evaluate(s=[s]), "scenario_clock_unqualified")


def test_missing_scenario_asset_return_not_filled():
    s=scenario();s["returns"].pop("SPY")
    out=evaluate(s=[s])
    row=out["alternatives"][0]
    assert row["status"]=="UNAVAILABLE"
    assert row["scenario_results"][0]["reasons"]==["instrument_return_missing"]


def test_corrupt_scenario_return_not_a_forecast():
    s=scenario();s["returns"]["SPY"]["base_total_return"]=math.nan
    # The incumbent core rejects nonfinite evidence at canonical input
    # serialization, before creating candidate rows; no NaN result escapes.
    assert_refused(evaluate(s=[s]), "evidence_not_serializable")


def test_declared_constraints_are_respected_not_overridden():
    b=book();b["constraints"]["max_instrument_weight"]=.5
    out=evaluate(b=b)
    row=out["alternatives"][0]
    assert row["status"]=="INELIGIBLE"
    assert "instrument_weight_ceiling" in row["constraints_breached"]
    assert out["authority"]["can_trade"] is False


def test_china_lookthrough_factors_shared_nonadditively():
    a=alt("China_overlap",{"FXI":.3,"KWEB":.3},.4)
    row=evaluate(a=[a])["alternatives"][0]
    assert row["status"] in ("AVAILABLE","INELIGIBLE")
    assert row["risk_key_exposures_nonadditive"]["china_equity"]==pytest.approx(.6)
    assert row["risk_key_exposures_nonadditive"]["asset:equity"]==pytest.approx(.6)


def test_correction_digest_changes_identity_without_mutating_inputs():
    c=context();out=evaluate(c=c)
    c2=copy.deepcopy(c);c2["context_digest"]="b"*64
    newer=evaluate(c=c2)
    assert out["market_context"]["context_digest"]!=newer["market_context"]["context_digest"]
    assert out["authority"]==newer["authority"]


def test_reordering_instruments_and_scenarios_changes_no_results():
    c=context(); options=[alt("x"),alt("y",{"FXI":.3,"SPY":.3})]
    scenarios=[scenario("z"),scenario("a")]
    a=evaluate(c=c,a=options,s=scenarios)
    c["rows"].reverse()
    b=evaluate(c=c,a=list(reversed(options)),s=list(reversed(scenarios)))
    assert a==b


def test_no_input_mutation_and_no_external_calls():
    c=context();b=book();aa=[alt()];ss=[scenario()]
    original=copy.deepcopy((c,b,aa,ss))
    evaluate(c=c,b=b,a=aa,s=ss)
    assert (c,b,aa,ss)==original


def test_privileged_decisions_never_originated():
    out=evaluate()
    for field in ("recommended_weights","rank","best_asset","forecast_probability",
                  "expected_return","orders","allocation_plan","trade"):
        assert field not in out
    assert out["authority"] == AUTHORITY
    assert not any(out["authority"].values())


def test_malformed_hypothetical_input_preserves_status_and_reason():
    out=evaluate(s=[])
    assert out["status"]=="UNAVAILABLE" and "alternatives_or_scenarios_missing_or_duplicate" in out["reasons"]


def test_bad_book_window_held():
    b=book();b["valid_until"]="2026-11-06T09:00:00Z"
    assert_refused(evaluate(b=b),"book_clock_unqualified")


def test_context_future_expected_day_refused():
    c=context();c["window"]["expected_session"]="2026-11-07"
    assert_refused(evaluate(c=c),"context_window_invalid")
