"""Synthetic native-account -> valuation -> scenario integration; no account I/O."""
from __future__ import annotations

import copy
import hashlib
import json
from unittest.mock import Mock

import pytest

from portfolio import global_scenario_account as adapter
from portfolio import instrument_policy, paper_account

AT = "2026-11-05T22:00:00Z"
BEFORE = "2026-11-05T21:30:00Z"
AFTER = "2026-11-05T22:30:00Z"
END = "2026-11-12T22:00:00Z"
NATIVE_IDENTITY = instrument_policy.classify_instrument


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def inputs():
    account = {"cash": 400.0, "starting_nav": 1000.0,
               "positions": {"AAPL": {"shares": 6.0, "avg_cost": 80.0}}}
    prices = {"AAPL": 100.0}
    evidence = {"AAPL": {"price": 100.0, "source": "synthetic-close", "source_revision": "price-r1",
                         "currency": "USD", "observed_asof": "2026-11-05", "stale_days": 0,
                         "close_qualified": True, "price_basis": "unadjusted_close",
                         "known_at": BEFORE, "valid_until": AFTER}}
    snapshot = {"book_id": "autonomous", "account_sha256": digest(account),
                "source_revision": "account-r1", "valuation_session": "2026-11-05",
                "known_at": BEFORE, "valid_until": AFTER}
    mandate = {"book_id": "autonomous", "revision": "synthetic-mandate-r1", "currency": "USD",
               "known_at": BEFORE, "valid_until": AFTER,
               "constraints": {"max_instrument_weight": .8, "max_risk_key_weight": .8,
                               "max_turnover_fraction": 1., "min_cash_fraction": .1}}
    universe = [{"instrument_id": key, "currency": "USD", "risk_keys": ["US_equity"],
                 "risk_source_ref": "synthetic-risk-groups-r1"} for key in ("AAPL", "MSFT")]
    costs = {"fee": 1., "spread_crossing": 2., "impact": 3.}
    alternatives = [{"alternative_id": "hold", "positions": {"AAPL": .6}, "cash_weight": .4, "costs_bps": costs},
                    {"alternative_id": "cash", "positions": {}, "cash_weight": 1., "costs_bps": costs},
                    {"alternative_id": "rotation", "positions": {"AAPL": .3, "MSFT": .3},
                     "cash_weight": .4, "costs_bps": costs}]
    scenario = {"scenario_id": "hypothetical-stress", "known_at": BEFORE, "valid_until": AFTER,
                "period_start": AT, "period_end": END, "source_ref": "synthetic-assumptions-r1", "cash_return": .001,
                "returns": {key: {"base_total_return": ret, "return_currency": "USD", "known_at": BEFORE,
                                   "valid_until": AFTER} for key, ret in (("AAPL", -.1), ("MSFT", .02))}}
    return dict(portfolio_id="autonomous", account=account, prices=prices, price_evidence=evidence,
                snapshot=snapshot, mandate=mandate, universe=universe, alternatives=alternatives,
                scenarios=[scenario], as_of=AT)


@pytest.fixture(autouse=True)
def isolate_native_owner(monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("what-if must not load, create, save or mark an account")
    for name in ("_load_account", "_save_account", "mark", "rebalance"):
        monkeypatch.setattr(paper_account, name, forbidden)
    monkeypatch.setattr(instrument_policy, "classify_instrument",
                        lambda pid, key: {"ticker": key, "kind": "common_stock", "verified": True,
                                          "status": "synthetic-positive-identity", "market": pid})


def result(values=None):
    return adapter.compare_account(**(values or inputs()))


def row(output, name):
    return next(r for r in output["comparison"]["alternatives"] if r["alternative_id"] == name)


def test_actual_native_valuation_and_comparison_not_target_snapshot(monkeypatch):
    native = paper_account.valuation
    spy = Mock(wraps=native)
    monkeypatch.setattr(paper_account, "valuation", spy)
    values = inputs(); out = result(values)
    assert out["status"] == "AVAILABLE" and out["valuation_status"] == "QUALIFIED"
    assert out["comparison"]["book"]["current_cash_fraction"] == .4
    assert out["held_positions"] == 1 and out["base_currency"] == "USD"
    assert spy.call_count == 1 and spy.call_args.kwargs["state"] == values["account"]
    assert spy.call_args.kwargs["state"] is not values["account"]
    assert row(out, "hold")["scenario_results"][0]["net_return"] == pytest.approx(-.06 + .0004)
    assert row(out, "cash")["scenario_results"][0]["net_return"] == pytest.approx(.001 - .6 * .0006)
    assert row(out, "rotation")["one_time_cost_fraction"] == pytest.approx(.6 * .0006)
    assert out["hypothetical_only"] and out["display_only"] and out["no_predictive_claim"]
    assert all(v is False for v in out["authority"].values())


def test_inputs_unchanged_and_original_shares_never_exposed():
    x = inputs(); before = copy.deepcopy(x); out = result(x)
    assert x == before
    assert "account" not in out and "prices" not in out
    assert "shares" not in json.dumps(out)


def test_native_policy_refuses_etf_despite_declared_metadata(monkeypatch):
    x = inputs(); x["universe"][1]["instrument_id"] = "EEM"
    monkeypatch.setattr(instrument_policy, "classify_instrument",
                        lambda pid, key: NATIVE_IDENTITY(pid, key) if key == "EEM"
                        else {"ticker": key, "kind": "common_stock", "verified": True})
    assert result(x)["reasons"] == ["native_instrument_policy_unqualified"]


@pytest.mark.parametrize("pid", ["not-a-book", "../../account", None, "flagship", "self_directed"])
def test_unknown_archived_or_unsupported_book_never_reads_default(pid):
    x = inputs(); x["portfolio_id"] = pid
    assert result(x)["status"] == "UNAVAILABLE"


def test_wrong_book_receipt_never_borrows_holdings():
    x = inputs(); x["snapshot"]["book_id"] = "hk"
    assert result(x)["reasons"] == ["book_receipt_mismatch"]


def test_account_correction_without_matching_revision_rejected():
    x = inputs(); x["account"]["cash"] = 500
    assert result(x)["reasons"] == ["account_revision_mismatch"]


def test_price_revision_changes_semantic_identity():
    x = inputs(); first = result(x)
    x["price_evidence"]["AAPL"]["source_revision"] = "price-r2"
    assert result(x)["comparison"]["input_digest"] != first["comparison"]["input_digest"]


@pytest.mark.parametrize("owner", ["snapshot", "mandate"])
@pytest.mark.parametrize("field,value", [("known_at", "2026-11-05T22:01:00Z"),
                                         ("valid_until", AT), ("known_at", "2026-11-05")])
def test_receipt_future_naive_and_expired(owner, field, value):
    x = inputs(); x[owner][field] = value
    assert result(x)["reasons"] == ["book_or_mandate_clock_unqualified"]


@pytest.mark.parametrize("change", ["missing", "boolean", "nan", "zero"])
def test_bad_prices_never_fall_back_to_cost_basis(change):
    x = inputs()
    if change == "missing": x["prices"] = {}
    else: x["prices"]["AAPL"] = {"boolean": True, "nan": float("nan"), "zero": 0}[change]
    assert result(x)["reasons"] == ["held_price_evidence_missing"]


@pytest.mark.parametrize("field,value", [("price", 99), ("currency", "HKD"),
    ("observed_asof", "2026-11-04"), ("close_qualified", False),
    ("price_basis", "adjusted_close"), ("source_revision", "")])
def test_unqualified_price_basis(field, value):
    x = inputs(); x["price_evidence"]["AAPL"][field] = value
    assert result(x)["reasons"] == ["held_price_basis_unqualified"]


def test_price_expiry_equality_abstains():
    x = inputs(); x["price_evidence"]["AAPL"]["valid_until"] = AT
    assert result(x)["reasons"] == ["held_price_clock_unqualified"]


def test_native_carried_price_cannot_qualify_scenario_weights():
    x = inputs(); x["price_evidence"]["AAPL"]["stale_days"] = 1
    assert result(x)["reasons"] == ["native_valuation_not_qualified"]


def test_negative_cash_or_short_positions_are_not_silently_normalized():
    for field in ("cash", "shares"):
        x = inputs()
        if field == "cash": x["account"]["cash"] = -1
        else: x["account"]["positions"]["AAPL"]["shares"] = -1
        x["snapshot"]["account_sha256"] = digest(x["account"])
        assert result(x)["reasons"] == ["fully_funded_long_only_required"]


def test_duplicate_instrument_refused():
    x = inputs(); x["universe"].append(copy.deepcopy(x["universe"][0]))
    assert result(x)["reasons"] == ["instrument_identity_ambiguous"]


def test_missing_current_holding_metadata_is_not_dropped():
    x = inputs(); x["universe"] = [x["universe"][1]]
    assert result(x)["reasons"] == ["held_instrument_metadata_missing"]


def test_missing_constraints_are_not_defaulted():
    x = inputs(); del x["mandate"]["constraints"]["min_cash_fraction"]
    assert result(x)["reasons"] == ["explicit_mandate_limits_required"]


def test_existing_constraint_breach_is_visible_not_overridden():
    x = inputs(); x["mandate"]["constraints"]["max_instrument_weight"] = .5
    out = result(x)
    assert row(out, "hold")["status"] == "INELIGIBLE"
    assert "instrument_weight_ceiling" in row(out, "hold")["constraints_breached"]


def test_no_static_fx_used_for_different_currency_instrument():
    x = inputs(); x["universe"][1]["currency"] = "HKD"
    assert result(x)["reasons"] == ["cross_currency_mark_not_supported"]


def test_risk_group_missingness_abstains():
    x = inputs(); x["universe"][0]["risk_keys"] = []
    assert result(x)["reasons"] == ["risk_group_evidence_missing"]


def test_explicit_same_horizon_required():
    x = inputs(); del x["scenarios"][0]["period_end"]
    assert result(x)["reasons"] == ["explicit_scenario_horizon_required"]
    x = inputs(); other = copy.deepcopy(x["scenarios"][0]); other["scenario_id"] = "other"
    other["period_end"] = "2026-11-13T22:00:00Z"; x["scenarios"].append(other)
    assert result(x)["reasons"] == ["scenario_horizon_mismatch"]


def test_cash_only_account_is_not_missing_holdings_or_forced_into_an_etf():
    x = inputs(); x["account"]["positions"] = {}; x["prices"] = {}; x["price_evidence"] = {}
    x["snapshot"]["account_sha256"] = digest(x["account"]); x["universe"] = []
    x["alternatives"] = [x["alternatives"][1]]; x["scenarios"][0]["returns"] = {}
    out = result(x)
    assert out["status"] == "AVAILABLE"
    assert out["held_positions"] == 0
    assert out["comparison"]["book"]["current_cash_fraction"] == 1.
    assert row(out, "cash")["one_time_cost_fraction"] == 0
    assert row(out, "cash")["scenario_results"][0]["net_return"] == .001


def test_identity_order_does_not_change_result():
    x = inputs(); out = result(x); x["universe"].reverse()
    assert result(x) == out


def test_declared_metadata_cannot_force_native_identity_approval(monkeypatch):
    x = inputs(); monkeypatch.setattr(instrument_policy, "classify_instrument",
                                     lambda pid, key: {"ticker": key, "kind": "unknown", "verified": False})
    assert result(x)["reasons"] == ["native_instrument_policy_unqualified"]


@pytest.mark.parametrize("pid,currency,symbols", [
    ("china", "CNY", {"AAPL": "600000.SS", "MSFT": "600519.SS"}),
    ("hk", "HKD", {"AAPL": "0700.HK", "MSFT": "9988.HK"}),
])
def test_native_regional_books_keep_their_own_currency_without_fx(pid, currency, symbols):
    x = inputs(); x["portfolio_id"] = pid
    x["snapshot"]["book_id"] = x["mandate"]["book_id"] = pid
    x["mandate"]["currency"] = currency
    x["account"]["positions"] = {symbols[k]: v for k, v in x["account"]["positions"].items()}
    x["snapshot"]["account_sha256"] = digest(x["account"])
    x["prices"] = {symbols[k]: v for k, v in x["prices"].items()}
    x["price_evidence"] = {symbols[k]: {**v, "currency": currency} for k, v in x["price_evidence"].items()}
    for u in x["universe"]:
        u["instrument_id"] = symbols[u["instrument_id"]]; u["currency"] = currency
    for a in x["alternatives"]:
        a["positions"] = {symbols[k]: v for k, v in a["positions"].items()}
    for s in x["scenarios"]:
        s["returns"] = {symbols[k]: {**v, "return_currency": currency} for k, v in s["returns"].items()}
    out = result(x)
    assert out["status"] == "AVAILABLE" and out["base_currency"] == currency
    assert out["comparison"]["book"]["base_currency"] == currency
    assert row(out, "hold")["scenario_results"][0]["net_return"] == pytest.approx(-.0596)


def test_cash_return_is_not_inferred_from_a_missing_assumption():
    x = inputs(); del x["scenarios"][0]["cash_return"]
    assert result(x)["comparison"]["reasons"] == ["cash_assumption_missing"]


def test_malformed_and_missing_account_are_not_empty_cash_books():
    for bad in (None, {}, {"cash": 400, "starting_nav": 1000}):
        x = inputs(); x["account"] = bad
        assert result(x)["status"] == "UNAVAILABLE"


def test_empty_universe_cannot_hide_actual_nonzero_holdings():
    x = inputs(); x["universe"] = []
    assert result(x)["reasons"] == ["held_instrument_metadata_missing"]
