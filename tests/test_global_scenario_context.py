"""MA-4 pure shadow comparisons: no account, fee, FX or forecast authority."""
from __future__ import annotations

import copy
import math
import unittest

from portfolio.global_scenario_context import AUTHORITY, ContractError, compare

AT = "2026-11-05T20:00:00Z"
BEFORE = "2026-11-05T19:59:00Z"
AFTER = "2026-11-05T20:30:00Z"


def book():
    return {
        "book_id": "hypothetical", "book_revision": "rev-1", "base_currency": "USD",
        "known_at": BEFORE, "valid_until": AFTER,
        "universe": [
            {"instrument_id": "SPY", "currency": "USD", "eligibility": "QUALIFIED",
             "policy_ref": "synthetic-policy-ref", "risk_keys": ["US_equities"]},
            {"instrument_id": "EEM", "currency": "USD", "eligibility": "QUALIFIED",
             "policy_ref": "synthetic-policy-ref", "risk_keys": ["EM_equities"]},
            {"instrument_id": "HK", "currency": "HKD", "eligibility": "QUALIFIED",
             "policy_ref": "synthetic-policy-ref", "risk_keys": ["EM_equities", "China"]},
        ],
        "positions": {"SPY": 0.6}, "cash_weight": 0.4,
        "constraints": {"max_instrument_weight": 0.8, "max_risk_key_weight": 0.8,
                        "max_turnover_fraction": 1.0, "min_cash_fraction": 0.1},
    }


def alternative(name="hold", positions=None, cash=0.4, fee=1, spread=2, impact=3):
    return {"alternative_id": name,
            "positions": {"SPY": 0.6} if positions is None else positions,
            "cash_weight": cash,
            "costs_bps": {"fee": fee, "spread_crossing": spread, "impact": impact}}


def scenario(name="stress", *, spy=-.1, em=-.03, hk=.02, cash=.001, fx=True):
    def ret(value, currency="USD"):
        out = {"base_total_return": value, "return_currency": currency,
               "known_at": BEFORE, "valid_until": AFTER}
        if currency == "USD":
            return out
        return out
    return {"scenario_id": name, "known_at": BEFORE, "valid_until": AFTER,
            "source_ref": "hypothetical-assumptions-v1",
            "cash_return": cash,
            "returns": {
                "SPY": ret(spy), "EEM": ret(em),
                "HK": {**ret(hk), "fx_qualified": fx, "fx_source_ref": "test-fx-v1"},
            }}


class ScenarioComparisonTests(unittest.TestCase):
    def run_one(self, b=None, alternatives=None, scenarios=None, *, at=AT):
        return compare(book() if b is None else b,
                       [alternative()] if alternatives is None else alternatives,
                       [scenario()] if scenarios is None else scenarios, as_of=at)

    def test_hold_net_return_is_weighted_sum(self):
        row = self.run_one()["alternatives"][0]
        self.assertEqual(row["status"], "AVAILABLE")
        p = row["scenario_results"][0]
        self.assertAlmostEqual(p["gross_return"], -.6*.1 + .4*.001)
        self.assertEqual(p["one_time_cost"], 0)
        self.assertEqual(p["net_return"], p["gross_return"])

    def test_rotation_charges_each_traded_leg_once(self):
        a = alternative("rotate", {"SPY": .3, "EEM": .3})
        row = self.run_one(alternatives=[a])["alternatives"][0]
        self.assertAlmostEqual(row["traded_notional_fraction"], .6)
        self.assertAlmostEqual(row["one_time_cost_fraction"], .6*6/10000)
        self.assertAlmostEqual(row["scenario_results"][0]["gross_return"], -.3*.1-.3*.03+.4*.001)
        self.assertAlmostEqual(row["scenario_results"][0]["net_return"],
                               -.3*.1-.3*.03+.4*.001-.6*6/10000)

    def test_cash_is_competing_funded_destination(self):
        a = alternative("cash", {}, cash=1)
        row = self.run_one(alternatives=[a])["alternatives"][0]
        self.assertEqual(row["status"], "AVAILABLE")
        self.assertAlmostEqual(row["one_time_cost_fraction"], .6*6/10000)
        self.assertAlmostEqual(row["scenario_results"][0]["gross_return"], .001)

    def test_sell_to_cash_is_not_charged_cash_leg(self):
        row = self.run_one(alternatives=[alternative("cash", {}, cash=1)])["alternatives"][0]
        self.assertAlmostEqual(row["traded_notional_fraction"], .6)

    def test_partial_sell_only_charges_reduced_position(self):
        row = self.run_one(alternatives=[alternative("partial", {"SPY": .4}, cash=.6)])["alternatives"][0]
        self.assertAlmostEqual(row["traded_notional_fraction"], .2)

    def test_zero_cost_still_explicit(self):
        row = self.run_one(alternatives=[alternative(fee=0,spread=0,impact=0)])["alternatives"][0]
        self.assertEqual(row["one_time_cost_fraction"], 0)

    def test_worst_hypothetical_return_not_forecast(self):
        ss = [scenario("up", spy=.1), scenario("down", spy=-.2)]
        row = self.run_one(scenarios=ss)["alternatives"][0]
        self.assertAlmostEqual(row["worst_hypothetical_net_return"], -.2*.6+.001*.4)
        self.assertTrue(self.run_one()["no_predictive_claim"])

    def test_authority_always_all_false(self):
        value = self.run_one()
        self.assertTrue(value["no_predictive_claim"])
        self.assertTrue(value["hypothetical_only"])
        self.assertTrue(value["display_only"])
        self.assertTrue(all(x is False for x in value["authority"].values()))
        self.assertEqual(value["authority"], AUTHORITY)

    def test_does_not_rank_alternatives_by_return(self):
        value = self.run_one(alternatives=[alternative("z_cash",{},1),
                                           alternative("a_hold")])
        self.assertEqual([a["alternative_id"] for a in value["alternatives"]],
                         ["a_hold", "z_cash"])
        self.assertNotIn("recommendation", value)

    def test_normalized_offset_clock(self):
        value = self.run_one(at="2026-11-05T12:00:00-08:00")
        self.assertEqual(value["as_of"], AT)
        self.assertEqual(value["status"], "AVAILABLE")

    def test_naive_or_date_only_as_of_rejected(self):
        for at in ("2026-11-05", "2026-11-05T20:00", "today", ""):
            with self.subTest(at=at), self.assertRaises(ContractError):
                self.run_one(at=at)

    def test_missing_book_identity_abstains(self):
        b=book();b.pop("book_revision")
        self.assertEqual(self.run_one(b=b)["reasons"], ["book_identity_missing"])

    def test_currency_invalid_abstains(self):
        b=book();b["base_currency"]="usd"
        self.assertEqual(self.run_one(b=b)["reasons"], ["book_currency_invalid"])

    def test_book_clock_ahead_abstains(self):
        b=book();b["known_at"]="2026-11-05T20:01:00Z"
        self.assertEqual(self.run_one(b=b)["reasons"], ["book_clock_unqualified"])

    def test_book_stale_on_valid_until_boundary(self):
        b=book();b["valid_until"]=AT
        self.assertEqual(self.run_one(b=b)["status"], "UNAVAILABLE")

    def test_duplicate_universe_instruments_refused(self):
        b=book(); b["universe"].append(dict(b["universe"][0]))
        self.assertIn("ambiguous", self.run_one(b=b)["reasons"][0])

    def test_bad_or_missing_eligibility_is_not_tradable(self):
        b=book();b["universe"][1]["eligibility"]="UNKNOWN"
        self.assertEqual(self.run_one(b=b)["reasons"],["instrument_eligibility_unqualified"])
        b=book();b["universe"][1].pop("policy_ref")
        self.assertEqual(self.run_one(b=b)["status"],"UNAVAILABLE")

    def test_risk_exposure_keys_required(self):
        b=book();b["universe"][0].pop("risk_keys")
        self.assertEqual(self.run_one(b=b)["reasons"],["risk_exposure_missing"])

    def test_missing_constraints_abstain(self):
        b=book();b.pop("constraints")
        self.assertEqual(self.run_one(b=b)["reasons"], ["constraints_missing"])

    def test_missing_bound_abstain(self):
        b=book();b["constraints"].pop("max_turnover_fraction")
        self.assertEqual(self.run_one(b=b)["reasons"], ["constraints_unqualified"])

    def test_book_cash_sum_needs_one(self):
        b=book();b["cash_weight"]=.2
        self.assertEqual(self.run_one(b=b)["reasons"], ["book_not_fully_funded"])

    def test_negative_position_refused(self):
        b=book();b["positions"]={"SPY":-0.1}
        self.assertEqual(self.run_one(b=b)["status"], "UNAVAILABLE")

    def test_boolean_weight_refused(self):
        b=book();b["positions"]={"SPY":True}; b["cash_weight"]=0
        self.assertEqual(self.run_one(b=b)["status"], "UNAVAILABLE")

    def test_alternative_missing_cash_abstains(self):
        row=self.run_one(alternatives=[alternative("bad",{"SPY":.6},cash=.2)])["alternatives"][0]
        self.assertIn("alternative_not_fully_funded",row["reasons"])

    def test_unknown_new_instrument_cannot_be_assumed_eligible(self):
        row=self.run_one(alternatives=[alternative("buy",{"SPY":.4,"QQQ":.2})])["alternatives"][0]
        self.assertEqual(row["status"],"UNAVAILABLE")

    def test_missing_cost_breakdown_refuses_implicit_free_trading(self):
        a=alternative("rot",{"SPY":.3,"EEM":.3});a.pop("costs_bps")
        self.assertIn("cost_components_missing_or_ambiguous",
                      self.run_one(alternatives=[a])["alternatives"][0]["reasons"])

    def test_all_in_cost_cannot_double_charge(self):
        a=alternative();a["costs_bps"]["all_in"]=8
        self.assertIn("cost_components_missing_or_ambiguous",
                      self.run_one(alternatives=[a])["alternatives"][0]["reasons"])

    def test_invalid_cost_number_fails(self):
        a=alternative();a["costs_bps"]["impact"]=math.nan
        self.assertEqual(self.run_one(alternatives=[a])["status"],"UNAVAILABLE")

    def test_cash_return_is_explicit_not_assumed_zero(self):
        s=scenario();s.pop("cash_return")
        self.assertEqual(self.run_one(scenarios=[s])["reasons"], ["cash_assumption_missing"])

    def test_scenario_future_known_abstains(self):
        s=scenario();s["known_at"]="2026-11-05T20:05:00Z"
        self.assertEqual(self.run_one(scenarios=[s])["reasons"],["scenario_clock_unqualified"])

    def test_missing_scenario_instrument_return_is_unavailable(self):
        a=alternative("rot", {"SPY":.3,"EEM":.3})
        s=scenario();s["returns"].pop("EEM")
        r=self.run_one(alternatives=[a],scenarios=[s])["alternatives"][0]
        self.assertEqual(r["status"],"UNAVAILABLE")
        self.assertEqual(r["scenario_results"][0]["reasons"],["instrument_return_missing"])

    def test_missing_one_scenario_is_partial(self):
        s=scenario("bad");s["returns"].pop("SPY")
        r=self.run_one(scenarios=[scenario("good"),s])["alternatives"][0]
        self.assertEqual(r["status"],"PARTIAL")
        self.assertEqual(len([x for x in r["scenario_results"] if x["status"]=="HYPOTHETICAL"]),1)

    def test_non_base_currency_requires_fx_lineage(self):
        a=alternative("hk",{"HK":.2,"SPY":.4})
        r=self.run_one(alternatives=[a],scenarios=[scenario(fx=False)])["alternatives"][0]
        self.assertIn("fx_ancestry_unqualified",r["scenario_results"][0]["reasons"])

    def test_non_base_currency_with_declared_fx_ancestry(self):
        a=alternative("hk",{"HK":.2,"SPY":.4})
        r=self.run_one(alternatives=[a],scenarios=[scenario(fx=True)])["alternatives"][0]
        self.assertEqual(r["status"],"AVAILABLE")
        self.assertAlmostEqual(r["scenario_results"][0]["gross_return"],.2*.02-.4*.1+.4*.001)

    def test_missing_fx_ref_is_unknown_not_zero(self):
        a=alternative("hk",{"HK":.2,"SPY":.4})
        s=scenario();s["returns"]["HK"].pop("fx_source_ref")
        self.assertEqual(self.run_one(alternatives=[a],scenarios=[s])["alternatives"][0]["status"],"UNAVAILABLE")

    def test_bases_cannot_be_inferred_from_fx_symbol(self):
        a=alternative("hk",{"HK":.2,"SPY":.4})
        s=scenario();s["returns"]["HK"]["return_currency"]="HKD"
        self.assertIn("base_return_unqualified",
                      self.run_one(alternatives=[a],scenarios=[s])["alternatives"][0]["scenario_results"][0]["reasons"])

    def test_return_future_clock_refused(self):
        s=scenario();s["returns"]["SPY"]["known_at"]="2026-11-05T20:01:00Z"
        self.assertIn("return_assumption_clock_unqualified",
                      self.run_one(scenarios=[s])["alternatives"][0]["scenario_results"][0]["reasons"])

    def test_per_instrument_ceiling_is_reported_not_traded(self):
        b=book();b["constraints"]["max_instrument_weight"]=.5
        r=self.run_one(b=b)["alternatives"][0]
        self.assertEqual(r["status"],"INELIGIBLE")
        self.assertIn("instrument_weight_ceiling",r["constraints_breached"])
        self.assertTrue(r["scenario_results"])

    def test_risk_key_ceiling_is_reported(self):
        b=book();b["constraints"]["max_risk_key_weight"]=.2
        r=self.run_one(b=b)["alternatives"][0]
        self.assertIn("risk_key_weight_ceiling",r["constraints_breached"])

    def test_turnover_ceiling_is_reported(self):
        b=book();b["constraints"]["max_turnover_fraction"]=.3
        a=alternative("rot",{"SPY":.3,"EEM":.3})
        r=self.run_one(b=b,alternatives=[a])["alternatives"][0]
        self.assertIn("turnover_ceiling",r["constraints_breached"])

    def test_cash_floor_is_reported(self):
        b=book();b["constraints"]["min_cash_fraction"]=.5
        self.assertIn("cash_floor",self.run_one(b=b)["alternatives"][0]["constraints_breached"])

    def test_risk_groups_nonadditive(self):
        a=alternative("hk",{"HK":.2,"SPY":.4})
        r=self.run_one(alternatives=[a])["alternatives"][0]
        self.assertAlmostEqual(r["risk_key_exposures_nonadditive"]["China"],.2)
        self.assertAlmostEqual(r["risk_key_exposures_nonadditive"]["EM_equities"],.2)

    def test_duplicate_scenario_refused(self):
        self.assertIn("duplicate",self.run_one(scenarios=[scenario(),scenario()])["reasons"][0])

    def test_duplicate_alternative_refused(self):
        self.assertIn("duplicate",self.run_one(alternatives=[alternative(),alternative()])["reasons"][0])

    def test_reordering_outer_rows_preserves_digest(self):
        b=book();ss=[scenario("one"),scenario("two")];aa=[alternative("a"),alternative("b")]
        v1=self.run_one(b=b,alternatives=aa,scenarios=ss)
        b["universe"].reverse()
        v2=self.run_one(b=b,alternatives=list(reversed(aa)),scenarios=list(reversed(ss)))
        self.assertEqual(v1["input_digest"],v2["input_digest"])

    def test_correction_revision_changes_digest(self):
        b=book();a=self.run_one(b=b)
        b["book_revision"]="rev-2"
        self.assertNotEqual(a["input_digest"],self.run_one(b=b)["input_digest"])

    def test_no_input_mutation(self):
        b=book();aa=[alternative()];ss=[scenario()]
        before=copy.deepcopy((b,aa,ss))
        self.run_one(b=b,alternatives=aa,scenarios=ss)
        self.assertEqual((b,aa,ss),before)

    def test_no_optimization_probabilities_or_actions(self):
        out=self.run_one()
        for forbidden in ("target_weights", "order", "expected_return","forecast_probability",
                          "execute", "recommendation", "best_alternative"):
            self.assertNotIn(forbidden,out)
        self.assertTrue(all(v is False for v in out["authority"].values()))


if __name__=="__main__":
    unittest.main()
