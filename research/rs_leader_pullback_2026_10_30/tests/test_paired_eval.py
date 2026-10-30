"""Synthetic-only falsification suite for paired RS-leader research, not market evidence."""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paired_eval import PairedProtocol, evaluate_paired

SHA = "f" * 64


def inputs(n=2, candidate="pivot"):
    opportunities, outcomes = [], []
    for i in range(n):
        day = date(2026, 10, 5) + timedelta(days=i)
        session = day.isoformat()
        decision = pd.Timestamp(session + "T15:00:00Z")
        prior = day - timedelta(days=1)
        identifier = f"op-{i:03}"
        opportunities.append({
            "opportunity_id": identifier, "symbol": f"A{i % 3}", "episode_id": f"episode-{i}",
            "session_date": session, "decision_utc": decision.isoformat(),
            "bar_known_at_utc": (decision - pd.Timedelta(seconds=1)).isoformat(),
            "leader_known_at_utc": (decision - pd.Timedelta(days=1)).isoformat(),
            "leader_asof_session": prior.isoformat(),
            "regime_known_at_utc": (decision - pd.Timedelta(hours=1)).isoformat(),
            "input_sha256": SHA, "eligible": True, "signal": i % 2 == 0,
            "split": "DEVELOPMENT",
        })
        for policy in (candidate, "leader_reference"):
            is_signal = i % 2 == 0
            status = "RESOLVED" if policy == "leader_reference" or is_signal else "NO_ENTRY"
            outcomes.append({"opportunity_id": identifier, "policy": policy,
                             "status": status,
                             "net_r": 1.0 + i if policy == candidate and is_signal else
                                      0.2 if policy == "leader_reference" else None,
                             "outcome_end_utc": (decision + pd.Timedelta(hours=1)).isoformat()
                             if status == "RESOLVED" else None,
                             "outcome_known_at_utc": (decision + pd.Timedelta(hours=1, minutes=1)).isoformat()
                             if status == "RESOLVED" else None,
                             "common_policy_clock_utc": decision.isoformat(),
                             "common_episode_end_utc": (decision + pd.Timedelta(hours=2)).isoformat(),
                             "common_risk_unit_sha256": "a" * 64,
                             "common_cost_model_sha256": "b" * 64})
    return pd.DataFrame(opportunities), pd.DataFrame(outcomes)


class PairedTests(unittest.TestCase):
    def run_pair(self, p=None, o=None, **kwargs):
        if p is None or o is None:
            p, o = inputs()
        return evaluate_paired(p, o, PairedProtocol(candidate="pivot", **kwargs))

    def test_all_predeclared_opportunities_preserved(self):
        a = self.run_pair()
        self.assertEqual(a["denominator"]["all_predeclared"], 2)
        self.assertEqual(a["splits"]["DEVELOPMENT"]["paired_supported"], 2)
        self.assertEqual(a["splits"]["DEVELOPMENT"]["candidate_nonentries"], 1)
        # +0.8 signal trade vs baseline; -0.2 missed baseline when no signal.
        self.assertAlmostEqual(a["splits"]["DEVELOPMENT"]["paired_mean_incremental_r"], .3)
        self.assertEqual(a["empirical_strategy_edge_verdict"], "NOT_ESTABLISHED")

    def test_explicit_nonentry_is_zero_within_denominator(self):
        a = self.run_pair()
        nonentry = a["paired_opportunities"][1]
        self.assertEqual(nonentry["candidate_status"], "NO_ENTRY")
        self.assertEqual(nonentry["candidate_r"], 0.0)
        self.assertAlmostEqual(nonentry["delta_r"], -.2)

    def test_censored_pair_excluded_but_counted(self):
        p, o = inputs()
        mask = (o.policy == "pivot") & (o.opportunity_id == "op-000")
        o.loc[mask, ["status", "net_r", "outcome_end_utc", "outcome_known_at_utc"]] = [
            "CENSORED", None, "2026-10-05T17:00:00Z", None]
        a = self.run_pair(p, o)
        v = a["splits"]["DEVELOPMENT"]
        self.assertEqual(v["eligible"], 2)
        self.assertEqual(v["paired_supported"], 1)
        self.assertEqual(v["candidate_censored"], 1)
        self.assertIsNone(a["paired_opportunities"][0]["delta_r"])
        self.assertIsNone(a["paired_opportunities"][0]["candidate_r"])

    def test_unavailable_pair_not_replaced_by_zero(self):
        p, o = inputs()
        mask = (o.policy == "leader_reference") & (o.opportunity_id == "op-000")
        o.loc[mask, ["status", "net_r", "outcome_end_utc", "outcome_known_at_utc"]] = [
            "UNAVAILABLE", None, None, None]
        a = self.run_pair(p, o)
        self.assertEqual(a["splits"]["DEVELOPMENT"]["unpaired_or_censored"], 1)

    def test_common_risk_basis_falsification_refused(self):
        p, o = inputs()
        o.loc[0, "common_risk_unit_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "risk must match"):
            self.run_pair(p, o)

    def test_common_cost_model_falsification_refused(self):
        p, o = inputs()
        o.loc[1, "common_cost_model_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "cost and risk must match"):
            self.run_pair(p, o)

    def test_asymmetric_outcome_horizon_refused(self):
        p, o = inputs()
        o.loc[0, "common_episode_end_utc"] = "2026-10-05T20:00:00Z"
        with self.assertRaisesRegex(ValueError, "horizon, cost and risk must match"):
            self.run_pair(p, o)

    def test_outcome_after_common_horizon_refused(self):
        p, o = inputs()
        o.loc[0, "outcome_end_utc"] = "2026-10-05T18:00:01Z"
        o.loc[0, "outcome_known_at_utc"] = "2026-10-05T18:00:02Z"
        with self.assertRaisesRegex(ValueError, "beyond the common episode horizon"):
            self.run_pair(p, o)

    def test_different_calendar_splits_same_day_refused(self):
        p, o = inputs()
        p.loc[1, "session_date"] = p.loc[0, "session_date"]
        p.loc[1, "decision_utc"] = p.loc[0, "decision_utc"]
        p.loc[1, "bar_known_at_utc"] = p.loc[0, "bar_known_at_utc"]
        p.loc[1, "leader_asof_session"] = p.loc[0, "leader_asof_session"]
        p.loc[1, "leader_known_at_utc"] = p.loc[0, "leader_known_at_utc"]
        p.loc[1, "regime_known_at_utc"] = p.loc[0, "regime_known_at_utc"]
        p.loc[1, "split"] = "HOLDOUT"
        with self.assertRaisesRegex(ValueError, "same calendar session"):
            self.run_pair(p, o)

    def test_absent_control_row_is_error(self):
        p, o = inputs()
        with self.assertRaisesRegex(ValueError, "identical opportunity"):
            self.run_pair(p, o.iloc[:-1])

    def test_duplicate_outcome_is_error(self):
        p, o = inputs()
        with self.assertRaises(ValueError):
            self.run_pair(p, pd.concat([o, o.iloc[[0]]]))

    def test_duplicate_opportunity_id_is_error(self):
        p, o = inputs()
        p.loc[1, "opportunity_id"] = p.loc[0, "opportunity_id"]
        with self.assertRaisesRegex(ValueError, "duplicate opportunity"):
            self.run_pair(p, o)

    def test_duplicate_symbol_episode_is_error(self):
        p, o = inputs()
        p.loc[1, ["symbol", "episode_id"]] = p.loc[0, ["symbol", "episode_id"]]
        with self.assertRaisesRegex(ValueError, "single episode"):
            self.run_pair(p, o)

    def test_future_bar_or_regime_is_refused(self):
        p, o = inputs()
        for field in ("bar_known_at_utc", "regime_known_at_utc", "leader_known_at_utc"):
            q = p.copy()
            q.loc[0, field] = "2026-10-05T16:00:00Z"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "future feature"):
                self.run_pair(q, o)

    def test_intraday_daily_leader_from_current_session_refused(self):
        p, o = inputs()
        p.loc[0, "leader_asof_session"] = p.loc[0, "session_date"]
        with self.assertRaisesRegex(ValueError, "prior session"):
            self.run_pair(p, o)

    def test_naive_and_local_display_timestamp_refused(self):
        p, o = inputs()
        p.loc[0, "decision_utc"] = "2026-10-05T15:00:00"
        with self.assertRaisesRegex(ValueError, "timezone-qualified"):
            self.run_pair(p, o)

    def test_session_et_day_does_not_equal_utc_day_if_after_midnight(self):
        p, o = inputs()
        p.loc[0, "decision_utc"] = "2026-10-06T01:00:00Z"
        p.loc[0, "bar_known_at_utc"] = "2026-10-06T00:59:59Z"
        with self.assertRaises(ValueError):
            self.run_pair(p, o)

    def test_boolean_from_string_refused(self):
        p, o = inputs()
        p["signal"] = p["signal"].astype(object)
        p.loc[0, "signal"] = "true"
        with self.assertRaisesRegex(ValueError, "genuine bool"):
            self.run_pair(p, o)

    def test_nonentry_return_zero_as_claim_is_refused(self):
        p, o = inputs()
        mask = (o.policy == "pivot") & (o.opportunity_id == "op-001")
        o.loc[mask, "net_r"] = 0.0
        with self.assertRaisesRegex(ValueError, "null, not zero"):
            self.run_pair(p, o)

    def test_censored_return_nan_is_null(self):
        p, o = inputs()
        mask = (o.policy == "pivot") & (o.opportunity_id == "op-000")
        o.loc[mask, ["status", "net_r", "outcome_end_utc", "outcome_known_at_utc"]] = [
            "CENSORED", float("nan"), "2026-10-05T17:00:00Z", None]
        self.assertEqual(self.run_pair(p, o)["splits"]["DEVELOPMENT"]["candidate_censored"], 1)

    def test_resolved_zero_return_is_valid(self):
        p, o = inputs()
        mask = (o.policy == "leader_reference") & (o.opportunity_id == "op-000")
        o.loc[mask, "net_r"] = 0.0
        self.assertAlmostEqual(self.run_pair(p, o)["splits"]["DEVELOPMENT"]["paired_mean_incremental_r"], .4)

    def test_no_signal_cannot_resolve_trade(self):
        p, o = inputs()
        mask = (o.policy == "pivot") & (o.opportunity_id == "op-001")
        o.loc[mask, ["status", "net_r", "outcome_end_utc", "outcome_known_at_utc"]] = [
            "RESOLVED", 5., "2026-10-06T17:00:00Z", "2026-10-06T17:01:00Z"]
        with self.assertRaisesRegex(ValueError, "no as-of signal"):
            self.run_pair(p, o)

    def test_ineligible_cannot_have_filled_trade(self):
        p, o = inputs()
        p.loc[0, "eligible"] = False
        with self.assertRaisesRegex(ValueError, "ineligible episode"):
            self.run_pair(p, o)

    def test_outcome_known_before_its_end_rejected(self):
        p, o = inputs()
        o.loc[0, "outcome_known_at_utc"] = "2026-10-05T15:59:00Z"
        with self.assertRaisesRegex(ValueError, "outcome clock"):
            self.run_pair(p, o)

    def test_unknown_status_refused(self):
        p, o = inputs()
        o.loc[0, "status"] = "WIN"
        with self.assertRaisesRegex(ValueError, "unrecognized outcome"):
            self.run_pair(p, o)

    def test_invalid_source_digest_refused(self):
        p, o = inputs()
        p.loc[0, "input_sha256"] = "not-a-sha"
        with self.assertRaisesRegex(ValueError, "64-char"):
            self.run_pair(p, o)

    def test_interleaved_splits_refused(self):
        p, o = inputs(3)
        p.loc[0, "split"] = "HOLDOUT"
        with self.assertRaisesRegex(ValueError, "interleaved"):
            self.run_pair(p, o)

    def test_embargo_refuses_label_crossing_holdout(self):
        p, o = inputs(2)
        p.loc[1, "split"] = "HOLDOUT"
        with self.assertRaisesRegex(ValueError, "overlaps holdout embargo"):
            self.run_pair(p, o, embargo_calendar_days=9)

    def test_late_holdout_registration_refused(self):
        p, o = inputs(2)
        p.loc[1, "split"] = "HOLDOUT"
        with self.assertRaisesRegex(ValueError, "registration postdates"):
            self.run_pair(p, o, embargo_calendar_days=0, registered_at_utc="2026-10-06T15:00:00Z")

    def test_holdout_is_not_independently_attested(self):
        p, o = inputs(2)
        p.loc[1, "split"] = "HOLDOUT"
        a = self.run_pair(p, o, embargo_calendar_days=0, registered_at_utc="2026-10-04T13:00:00Z")
        self.assertEqual(a["holdout_status"], "REGISTRATION_DECLARED_NOT_INDEPENDENTLY_ATTESTED")
        self.assertEqual(a["empirical_strategy_edge_verdict"], "NOT_ESTABLISHED")

    def test_analysis_asof_refuses_unobserved_future_label(self):
        p, o = inputs()
        with self.assertRaisesRegex(ValueError, "unobserved outcome"):
            self.run_pair(p, o, analysis_asof_utc="2026-10-06T15:01:00Z")

    def test_analysis_asof_refuses_future_decision(self):
        p, o = inputs()
        with self.assertRaisesRegex(ValueError, "future decision"):
            self.run_pair(p, o, analysis_asof_utc="2026-10-05T23:00:00Z")

    def test_analysis_asof_after_labels_accepts_without_proving_source(self):
        p, o = inputs()
        x = self.run_pair(p, o, analysis_asof_utc="2026-10-08T00:00:00Z")
        self.assertEqual(x["source_admission"], "NOT_ATTESTED_BY_THIS_EVALUATOR")
        self.assertIsInstance(x["paired_opportunities"][0]["session_date"], str)

    def test_bootstrap_underpowered_by_calendar_clusters(self):
        a = self.run_pair()
        self.assertEqual(a["splits"]["DEVELOPMENT"]["date_block_bootstrap"]["reason"],
                         "INSUFFICIENT_DATE_CLUSTERS")

    def test_date_cluster_bootstrap_deterministic(self):
        p, o = inputs(45)
        v1 = self.run_pair(p, o, block_sessions=5, bootstrap_draws=30)
        v2 = self.run_pair(p, o, block_sessions=5, bootstrap_draws=30)
        b = v1["splits"]["DEVELOPMENT"]["date_block_bootstrap"]
        self.assertIsNone(b["reason"])
        self.assertEqual(b, v2["splits"]["DEVELOPMENT"]["date_block_bootstrap"])
        self.assertLessEqual(b["lower"], b["upper"])


if __name__ == "__main__":
    unittest.main()
