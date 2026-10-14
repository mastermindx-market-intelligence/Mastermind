"""Synthetic-only tests for V27 prospective cohort economic grid.

All prices/returns/entries are invented fixtures; no historical SOXX studies,
vendor credentials or unchanged V26 test suite are rerun.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from importlib import import_module
import unittest

g = import_module(
    "research.soxx-multitimeframe-cycle-2026-10-11.prospective_validation_v26.cohort_v27"
)
u = import_module(
    "research.soxx-multitimeframe-cycle-2026-10-11.prospective_validation_v26.utility"
)
UTC = timezone.utc
REG = datetime(2026, 10, 13, 18, tzinfo=UTC)
ASOF = datetime(2027, 5, 1, tzinfo=UTC)
START = datetime(2026, 10, 14, 14, tzinfo=UTC)


def source(**kw):
    args = dict(
        protocol_committed_at=REG, incumbent_manifest_sha256="a" * 64,
        incumbent_receipt_ref="incumbent-owner:immutable-proof",
        entry_universe_complete=True, warmup_complete=True, source_clock_qualified=True,
        vintage_adjustment_qualified=True, internal_research_rights_qualified=True,
    )
    args.update(kw)
    return g.UpstreamSourceClaims(**args)


def episodes():
    return (
        g.OriginalEpisode("S", "SOXX", START, START + timedelta(days=7),
                          START + timedelta(days=7, minutes=1)),
        g.OriginalEpisode("A", "AMD", START + timedelta(minutes=2),
                          START + timedelta(days=8), START + timedelta(days=8, minutes=1)),
    )


def policies(*, unknown=False, no_action=False):
    S = u.PairedOutcome("S", "FILLED", baseline_pp=2.0, intervention_pp=-3.0,
                        sold_fraction=0.75, sale_to_entry=1.0)
    if unknown:
        A = u.PairedOutcome("A", "UNRESOLVED", baseline_pp=-2.,
                            delta_bounds=(-4., 1.), bounds_cover_slippage_bps=100.)
    elif no_action:
        A = u.PairedOutcome("A", "NO_ACTION", baseline_pp=-2., intervention_pp=-2.,
                            baseline_preserved=True)
    else:
        A = u.PairedOutcome("A", "FILLED", baseline_pp=-2., intervention_pp=1.,
                            sold_fraction=0.75, sale_to_entry=1.0)
    return {key: (S, A) for key in g.ARMS}


def valid_filled_labels(original, arms):
    by_id = {e.episode: e for e in original}
    return {
        key: tuple(
            u.TrainingLabel(
                row.episode,
                by_id[row.episode].entry_at + (
                    timedelta(minutes=30) if key[0] == "30m" else timedelta(hours=3)),
                by_id[row.episode].entry_at + (
                    timedelta(minutes=30) if key[0] == "30m" else timedelta(hours=3)),
                by_id[row.episode].baseline_end_at, by_id[row.episode].baseline_end_at,
                by_id[row.episode].outcome_known_at)
            for row in rows if row.state == "FILLED" and row.episode in by_id
        )
        for key, rows in arms.items()
    }


class TestV27FrozenCohort(unittest.TestCase):
    def run_grid(self, **kw):
        src = kw.get("source", source())
        original = kw.get("episodes", episodes())
        arms = kw.get("arms", policies())
        labels = kw.get("filled_labels", valid_filled_labels(original, arms))
        return g.evaluate_frozen_grid(
            src, original, arms, evaluation_at=kw.get("asof", ASOF),
            filled_labels=labels)

    def test_missing_filled_path_availability_withholds_finite_scores(self):
        out = g.evaluate_frozen_grid(
            source(), episodes(), policies(), evaluation_at=ASOF, filled_labels=None)
        self.assertEqual(out["status"], "WITHHELD_PAIRED_PATH_EVIDENCE")
        self.assertIsNone(out["cells"])

    def test_future_intervention_outcome_cannot_be_claimed_mature(self):
        arms = policies()
        baseline, secondary = episodes()
        by_id = {e.episode:e for e in (baseline, secondary)}
        labels = {
            key: tuple(
                u.TrainingLabel(
                    row.episode, by_id[row.episode].entry_at + timedelta(minutes=30),
                    by_id[row.episode].entry_at + timedelta(minutes=30),
                    by_id[row.episode].baseline_end_at,
                    by_id[row.episode].baseline_end_at,
                    ASOF + timedelta(days=2) if row.episode == "S"
                    else by_id[row.episode].outcome_known_at)
                for row in rows if row.state == "FILLED")
            for key,rows in arms.items()
        }
        with self.assertRaisesRegex(ValueError, "intervention outcome not yet available"):
            g.evaluate_frozen_grid(source(), episodes(), arms, evaluation_at=ASOF,
                                   filled_labels=labels)

    def test_one_missing_filled_path_label_censors_all_cells(self):
        arms = policies()
        labels = valid_filled_labels(episodes(), arms)
        labels[("30m", 1)] = labels[("30m", 1)][:1]
        out = self.run_grid(arms=arms, filled_labels=labels)
        self.assertEqual(out["status"], "WITHHELD_PAIRED_PATH_EVIDENCE")
        self.assertIsNone(out["cells"])

    def test_paired_path_must_use_exact_original_baseline_horizon(self):
        labels = valid_filled_labels(episodes(), policies())
        first, *others = labels[("3h", 2)]
        labels[("3h", 2)] = (
            replace(first, baseline_end_at=first.baseline_end_at + timedelta(minutes=1)),
            *others,
        )
        with self.assertRaisesRegex(ValueError, "baseline end does not match"):
            self.run_grid(filled_labels=labels)

    def test_paired_path_cannot_backdate_known_baseline_availability(self):
        labels = valid_filled_labels(episodes(), policies())
        first, *others = labels[("30m", 2)]
        labels[("30m", 2)] = (
            replace(first, outcome_available_at=first.baseline_end_at), *others
        )
        with self.assertRaisesRegex(ValueError, "backdates original baseline"):
            self.run_grid(filled_labels=labels)

    def test_paired_path_decision_cannot_precede_original_entry(self):
        labels = valid_filled_labels(episodes(), policies())
        first, *others = labels[("30m", 2)]
        early = episodes()[0].entry_at - timedelta(minutes=1)
        labels[("30m", 2)] = (
            replace(first, decision_at=early, feature_available_at=early),
            *others,
        )
        with self.assertRaisesRegex(ValueError, "precedes actual original entry"):
            self.run_grid(filled_labels=labels)

    def test_nonfill_cannot_claim_filled_path_outcome(self):
        arms = policies(no_action=True)
        labels = valid_filled_labels(episodes(), arms)
        other = episodes()[1]
        fake = u.TrainingLabel("A", other.entry_at + timedelta(minutes=30),
                               other.entry_at + timedelta(minutes=30),
                               other.baseline_end_at, other.baseline_end_at,
                               other.outcome_known_at)
        labels[("30m", 1)] += (fake,)
        with self.assertRaisesRegex(ValueError, "unmatched filled-path label"):
            self.run_grid(arms=arms, filled_labels=labels)

    def test_full_grid_has_all_prescribed_cells_with_no_selection(self):
        out = self.run_grid()
        self.assertEqual(out["status"], "STRUCTURAL_ECONOMICS_ONLY")
        self.assertEqual(len(out["cells"]), 60)
        self.assertEqual(out["original_episodes"], 2)
        self.assertEqual(out["SOXX_original_episodes"], 1)
        self.assertTrue(out["matched_denominator_all_arms"])
        self.assertFalse(out["inferential_confidence_claim"])
        self.assertFalse(out["execution_marketability_proven"])
        self.assertFalse(out["source_claims_externally_authenticated"])
        self.assertFalse(out["live_trading_accepted"])

    def test_same_original_denominator_in_each_stress(self):
        for key, value in self.run_grid()["cells"].items():
            self.assertEqual(value["original_episodes"], 1 if key.startswith("SOXX_only:") else 2)
        self.assertEqual(self.run_grid()["cells"]["all_symbols:3h:d4:bp100"]["original_episodes"], 2)

    def test_winner_sacrifice_outweighs_loser_savings(self):
        result = self.run_grid()["cells"]["all_symbols:30m:d1:bp0"]
        self.assertEqual(result["mean_delta_pp"], -1.0)
        self.assertEqual(result["resolved_components"]["baseline_winner_sacrifice_pp"], 5.)
        self.assertEqual(result["resolved_components"]["baseline_loser_improvement_pp"], 3.)

    def test_adverse_selling_makes_fixed_arms_worse(self):
        cells = self.run_grid()["cells"]
        self.assertAlmostEqual(cells["all_symbols:30m:d1:bp0"]["mean_delta_pp"], -1.)
        self.assertAlmostEqual(cells["all_symbols:30m:d1:bp100"]["mean_delta_pp"], -1.75)
        self.assertEqual(cells["all_symbols:30m:d1:bp0"]["discretionary_fills"], 2)

    def test_soxx_is_not_swamped_by_extra_stocks(self):
        cells = self.run_grid()["cells"]
        self.assertEqual(cells["SOXX_only:30m:d1:bp0"]["mean_delta_pp"], -5.)
        self.assertEqual(cells["all_symbols:30m:d1:bp0"]["mean_delta_pp"], -1.)

    def test_early_nonaction_stays_in_all_denominators(self):
        vals = self.run_grid(arms=policies(no_action=True))["cells"]
        self.assertEqual(vals["all_symbols:30m:d1:bp0"]["original_episodes"], 2)
        self.assertEqual(vals["all_symbols:30m:d1:bp0"]["no_action_episodes"], 1)
        self.assertEqual(vals["all_symbols:30m:d1:bp0"]["mean_delta_pp"], -2.5)

    def test_unknown_fill_cannot_disappear_into_mean(self):
        vals = self.run_grid(arms=policies(unknown=True))["cells"]
        data = vals["all_symbols:30m:d1:bp0"]
        self.assertIsNone(data["mean_delta_pp"])
        self.assertEqual(data["unresolved_episodes"], 1)
        self.assertEqual(data["original_episodes"], 2)
        self.assertAlmostEqual(data["mean_delta_lower_pp"], -4.5)
        self.assertAlmostEqual(data["mean_delta_upper_pp"], -2.)

    def test_unknown_fill_stress_not_covered_fails_closed(self):
        arms = policies(unknown=True)
        limited = u.PairedOutcome("A", "UNRESOLVED", baseline_pp=-2.,
                                  delta_bounds=(-4., 1.), bounds_cover_slippage_bps=25.)
        for key in arms:
            arms[key] = (arms[key][0], limited)
        with self.assertRaisesRegex(ValueError, "bounds do not cover"):
            self.run_grid(arms=arms)

    def test_outcome_peeking_before_prespecified_window_close_is_withheld(self):
        out = self.run_grid(asof=datetime(2026, 10, 30, tzinfo=UTC))
        self.assertEqual(out["status"], "WITHHELD_WINDOW_OPEN")
        self.assertIsNone(out["cells"])

    def test_unfinished_last_episode_horizon_cannot_be_scored(self):
        last = g.OriginalEpisode("L", "SOXX",
                                 datetime(2027, 4, 13, 15, tzinfo=UTC),
                                 datetime(2027, 4, 24, tzinfo=UTC), None)
        arms = {key: (u.PairedOutcome("L", "UNRESOLVED"),) for key in g.ARMS}
        out = self.run_grid(episodes=(last,), arms=arms,
                            asof=datetime(2027, 4, 16, tzinfo=UTC))
        self.assertEqual(out["status"], "WITHHELD_UNFINISHED_HORIZON")
        self.assertIsNone(out["cells"])

    def test_incomplete_universe_withholds_all_cells(self):
        out = self.run_grid(source=source(entry_universe_complete=False))
        self.assertEqual(out["status"], "WITHHELD_SOURCE_OR_UNIVERSE")
        self.assertIsNone(out["cells"])
        self.assertEqual(out["missing_gates"], ("entry_universe_complete",))

    def test_unqualified_rights_withholds_all_cells(self):
        out = self.run_grid(source=source(internal_research_rights_qualified=False))
        self.assertIsNone(out["cells"])

    def test_unqualified_clock_withholds_all_cells(self):
        out = self.run_grid(source=source(source_clock_qualified=False))
        self.assertIsNone(out["cells"])

    def test_empty_population_never_implies_zero_perf(self):
        out = self.run_grid(episodes=(), arms={})
        self.assertEqual(out["status"], "NO_OBSERVED_PARENT_EPISODES")
        self.assertIsNone(out["cells"])

    def test_one_of_six_arms_missing_is_not_scored(self):
        arm = policies()
        del arm[("3h", 4)]
        with self.assertRaisesRegex(ValueError, "six frozen"):
            self.run_grid(arms=arm)

    def test_losing_episode_cannot_be_dropped(self):
        arm = policies()
        arm[("30m", 1)] = arm[("30m", 1)][:1]
        with self.assertRaisesRegex(ValueError, "missing, duplicated"):
            self.run_grid(arms=arm)

    def test_episode_id_cannot_be_duplicate_or_invented(self):
        arm = policies()
        arm[("30m", 2)] = (*arm[("30m", 2)], arm[("30m", 2)][0])
        with self.assertRaisesRegex(ValueError, "missing, duplicated"):
            self.run_grid(arms=arm)

    def test_original_episode_inventory_cannot_repeat(self):
        es = (episodes()[0], episodes()[0])
        with self.assertRaisesRegex(ValueError, "repeated original"):
            self.run_grid(episodes=es)

    def test_source_baseline_cannot_change_between_arms(self):
        arm = policies()
        arm[("30m", 1)] = (
            u.PairedOutcome("S", "FILLED", baseline_pp=3., intervention_pp=-3.,
                            sold_fraction=.75, sale_to_entry=1.),
            arm[("30m", 1)][1]
        )
        with self.assertRaisesRegex(ValueError, "different baseline"):
            self.run_grid(arms=arm)

    def test_unresolved_arm_known_baseline_cannot_disagree(self):
        arms = policies(unknown=True)
        prior = arms[("3h", 4)][0]
        arms[("3h", 4)] = (
            prior,
            u.PairedOutcome("A", "UNRESOLVED", baseline_pp=-99.,
                            delta_bounds=(-4., 1.), bounds_cover_slippage_bps=100.)
        )
        with self.assertRaisesRegex(ValueError, "different baseline"):
            self.run_grid(arms=arms)

    def test_unresolved_known_baseline_must_be_mature(self):
        first, second = episodes()
        second = replace(second, outcome_known_at=ASOF + timedelta(days=2))
        with self.assertRaisesRegex(ValueError, "no mature"):
            self.run_grid(episodes=(first, second), arms=policies(unknown=True))

    def test_resolved_future_outcome_not_available_asof(self):
        a, b = episodes()
        late = replace(a, outcome_known_at=ASOF + timedelta(days=1))
        with self.assertRaisesRegex(ValueError, "(no mature|intervention outcome not yet available)"):
            self.run_grid(episodes=(late, b))

    def test_unresolved_outcome_can_stay_unmatured(self):
        e = g.OriginalEpisode("S", "SOXX", START, START + timedelta(days=7), None)
        arm = {key: (u.PairedOutcome("S", "UNRESOLVED", baseline_pp=None),)
               for key in g.ARMS}
        out = self.run_grid(episodes=(e,), arms=arm)
        self.assertIsNone(out["cells"]["all_symbols:30m:d1:bp0"]["mean_delta_pp"])

    def test_future_entry_not_counted_as_observed(self):
        with self.assertRaisesRegex(ValueError, "future original entry"):
            self.run_grid(asof=REG + timedelta(hours=1), arms=policies(unknown=True))

    def test_no_soxx_event_is_not_peer_primary_validation(self):
        a = episodes()[1]
        arm = {key: (policies()[key][1],) for key in g.ARMS}
        out = self.run_grid(episodes=(a,), arms=arm)
        self.assertEqual(out["SOXX_original_episodes"], 0)
        self.assertEqual(out["primary_SOXX_evidence"], "NO_PRIMARY_EPISODES")
        self.assertFalse(any(k.startswith("SOXX_only:") for k in out["cells"]))

    def test_baseline_end_before_entry_rejected(self):
        with self.assertRaisesRegex(ValueError, "baseline horizon"):
            g.OriginalEpisode("S", "SOXX", START, START, None)

    def test_baseline_result_known_before_completion_rejected(self):
        with self.assertRaisesRegex(ValueError, "predates"):
            g.OriginalEpisode("S", "SOXX", START, START + timedelta(days=1), START)

    def test_old_development_year_not_accepted_as_holdout(self):
        with self.assertRaisesRegex(ValueError, "frozen ET window"):
            g.OriginalEpisode("S", "SOXX", datetime(2025, 11, 1, tzinfo=UTC),
                              datetime(2025, 11, 3, tzinfo=UTC), None)

    def test_2027_end_of_window_not_extended_for_good_results(self):
        with self.assertRaisesRegex(ValueError, "frozen ET window"):
            g.OriginalEpisode("S", "SOXX", datetime(2027, 4, 15, tzinfo=UTC),
                              datetime(2027, 4, 25, tzinfo=UTC), None)

    def test_future_prereg_does_not_make_data_prospective(self):
        with self.assertRaisesRegex(ValueError, "not committed before"):
            source(protocol_committed_at=datetime(2026, 10, 15, tzinfo=UTC))

    def test_naive_wall_clocks_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            g.OriginalEpisode("S", "SOXX", datetime(2026, 10, 14, 10),
                              START + timedelta(days=1), None)

    def test_manifest_sha_and_claim_typing_strict(self):
        with self.assertRaisesRegex(ValueError, "canonical SHA256"):
            source(incumbent_manifest_sha256="fake")
        with self.assertRaisesRegex(ValueError, "explicit booleans"):
            source(entry_universe_complete="true")

    def test_report_cannot_predate_publication(self):
        with self.assertRaisesRegex(ValueError, "predate"):
            self.run_grid(asof=REG-timedelta(days=1))

    def test_report_never_calls_derived_results_trade_acceptance(self):
        s = self.run_grid()
        self.assertNotIn("approved_strategy", s)
        self.assertIn("NOT independent source-owner proof", s["note"])
        self.assertFalse(s["live_trading_accepted"])


if __name__ == "__main__":
    unittest.main()
