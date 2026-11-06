"""Real-core held-baseline comparisons; no accounts, feeds, forecasts or actions."""
from __future__ import annotations

import copy
from unittest.mock import patch

import pytest

from portfolio import global_scenario_context as core
from portfolio.global_scenario_summary import compare_with_hold_baseline as compare
from tests.test_global_scenario_context import AT, alternative, book, scenario


def run(b=None, aa=None, ss=None):
    return compare(book() if b is None else b, [alternative()] if aa is None else aa,
                   [scenario()] if ss is None else ss, as_of=AT)


def delta(result, index=0, scen=0):
    return result["alternatives"][index]["relative_to_hold"]["scenarios"][scen]


def test_actual_held_baseline_is_not_caller_named_hold():
    x = run(aa=[alternative("hold", {}, cash=1)])
    assert x["hold_baseline"]["source"] == "unchanged_supplied_book"
    assert x["hold_baseline"]["scenario_results"][0]["net_return"] == pytest.approx(-.0596)
    assert delta(x)["hold_net_return"] == pytest.approx(-.0596)
    assert delta(x)["candidate_net_return"] == pytest.approx(.00064)


def test_baseline_does_not_trade_or_charge_candidate_costs():
    x = run(aa=[alternative(fee=20, spread=30, impact=40)])
    assert x["hold_baseline"]["one_time_cost_fraction"] == 0
    assert delta(x)["net_return_delta"] == 0
    assert delta(x)["candidate_one_time_cost"] == 0


def test_buy_and_sell_costs_once_in_net_relative_to_hold():
    x = run(aa=[alternative("rotation", {"SPY": .3, "EEM": .3})])
    d = delta(x)
    assert d["candidate_net_return"] == pytest.approx(-.039 + .0004 - .00036)
    assert d["net_return_delta"] == pytest.approx(.021 - .00036)
    assert d["candidate_one_time_cost"] == pytest.approx(.00036)


def test_cash_alternative_competes_with_hold():
    x = run(aa=[alternative("cash", {}, cash=1)])
    assert delta(x)["net_return_delta"] == pytest.approx(.06024)
    assert x["alternatives"][0]["status"] == "AVAILABLE"


def test_entirely_cash_book_needs_no_fake_security():
    b = book(); b.update(universe=[], positions={}, cash_weight=1)
    x = run(b, [alternative("cash", {}, cash=1)], [scenario()])
    assert x["status"] == "AVAILABLE"
    assert delta(x)["net_return_delta"] == 0
    assert x["hold_baseline"]["one_time_cost_fraction"] == 0


def test_missing_held_return_cannot_be_silently_imputed():
    s = scenario(); s["returns"].pop("SPY")
    x = run(aa=[alternative("cash", {}, cash=1)], ss=[s])
    assert x["alternatives"][0]["status"] == "AVAILABLE"
    assert x["hold_baseline"]["status"] == "UNAVAILABLE"
    assert delta(x) == {"scenario_id": "stress", "status": "UNAVAILABLE",
                        "reason": "candidate_or_hold_scenario_unavailable"}
    assert x["alternatives"][0]["relative_to_hold"]["paired_scenarios"] == 0


def test_missing_candidate_return_preserves_other_paired_scenario():
    bad = scenario("bad"); bad["returns"].pop("EEM")
    x = run(aa=[alternative("rot", {"SPY": .3, "EEM": .3})], ss=[bad, scenario("good")])
    pairs = x["alternatives"][0]["relative_to_hold"]
    assert pairs["status"] == "PARTIAL"
    assert (pairs["paired_scenarios"], pairs["requested_scenarios"]) == (1, 2)
    assert pairs["scenarios"][0]["status"] == "UNAVAILABLE"
    assert pairs["scenarios"][1]["status"] == "HYPOTHETICAL"


def test_less_negative_is_not_reported_as_an_absolute_gain():
    x = run(aa=[alternative("rot", {"SPY": .3, "EEM": .3})])
    d = delta(x)
    assert d["candidate_net_return"] < 0 and d["hold_net_return"] < 0
    assert d["net_return_delta"] > 0
    assert "forecast_probability" not in d and "recommendation" not in x


def test_ineligible_candidate_remains_ineligible_despite_a_positive_delta():
    b = book(); b["constraints"]["max_turnover_fraction"] = .1
    x = run(b, [alternative("cash", {}, cash=1)])
    assert x["alternatives"][0]["status"] == "INELIGIBLE"
    assert "turnover_ceiling" in x["alternatives"][0]["constraints_breached"]
    assert delta(x)["status"] == "HYPOTHETICAL"
    assert x["status"] == "PARTIAL"


def test_inherited_hold_concentration_breach_remains_visible():
    b = book(); b["constraints"]["max_instrument_weight"] = .2
    x = run(b, [alternative("cash", {}, cash=1)])
    assert x["hold_baseline"]["status"] == "INELIGIBLE"
    assert "instrument_weight_ceiling" in x["hold_baseline"]["constraints_breached"]
    assert delta(x)["status"] == "HYPOTHETICAL"


def test_unqualified_book_returns_no_fabricated_deltas():
    b = book(); b.pop("book_revision")
    x = run(b)
    assert x["status"] == "UNAVAILABLE" and x["alternatives"] == []
    assert x["hold_baseline"]["reasons"] == ["qualified_book_unavailable"]


def test_bad_invocation_preserves_native_contract_error():
    with pytest.raises(core.ContractError): compare({}, [], [], as_of="not-time")
    with pytest.raises(core.ContractError): compare([], [], [], as_of=AT)


def test_duplicate_scenarios_remain_native_refusal():
    x = run(ss=[scenario(), scenario()])
    assert x["status"] == "UNAVAILABLE" and not x["alternatives"]


def test_duplicate_alternatives_remain_native_refusal():
    x = run(aa=[alternative(), alternative()])
    assert x["status"] == "UNAVAILABLE" and not x["alternatives"]


def test_no_mutation_of_caller_objects():
    b, a, s = book(), [alternative("r", {"SPY": .3, "EEM": .3})], [scenario()]
    before = copy.deepcopy((b, a, s))
    run(b, a, s)
    assert (b, a, s) == before


def test_stable_identity_order_and_native_digest():
    b = book(); aa = [alternative("z"), alternative("a", {}, cash=1)]
    ss = [scenario("z"), scenario("a", spy=.1)]
    x = run(b, aa, ss); y = run(b, list(reversed(aa)), list(reversed(ss)))
    assert x == y
    assert x["input_digest"] == core.compare(b, aa, ss, as_of=AT)["input_digest"]
    assert [a["alternative_id"] for a in x["alternatives"]] == ["a", "z"]


def test_caller_reserved_looking_name_cannot_replace_baseline():
    x = run(aa=[alternative("__held_book_baseline__", {}, cash=1)])
    assert delta(x)["hold_net_return"] < 0 < delta(x)["candidate_net_return"]


def test_authority_stays_false_through_partial_and_unavailable_states():
    for x in (run(), run(b={}), run(aa=[alternative("bad", {"SPY": .8}, cash=.1)])):
        assert all(value is False for value in x["authority"].values())
        assert x["display_only"] and x["hypothetical_only"] and x["no_predictive_claim"]


def test_nonfinite_native_assumptions_never_become_a_delta():
    s = scenario(); s["returns"]["SPY"]["base_total_return"] = float("inf")
    x = run(ss=[s])
    assert x["status"] == "UNAVAILABLE"
    assert x["alternatives"] == []


def test_native_result_is_not_mutated():
    base = core.compare(book(), [alternative()], [scenario()], as_of=AT)
    original = copy.deepcopy(base)
    with patch.object(core, "compare", return_value=base):
        run()
    assert base == original


def test_overflow_of_pair_subtraction_withholds_instead_of_emitting_infinity():
    # Defensive join fixture: actual fully-funded native returns cannot reach
    # this opposite-sign extreme. Exercise the consumer's arithmetic fence.
    first = core.compare(book(), [alternative()], [scenario()], as_of=AT)
    second = copy.deepcopy(first)
    first["alternatives"][0]["scenario_results"][0]["net_return"] = 1e308
    second["alternatives"][0]["scenario_results"][0]["net_return"] = -1e308
    with patch.object(core, "compare", side_effect=[first, second]):
        x = run()
    assert delta(x)["status"] == "UNAVAILABLE"
    assert delta(x)["reason"] == "comparison_arithmetic_invalid"
