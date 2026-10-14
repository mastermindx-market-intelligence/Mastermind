"""Synthetic corruption tests and frozen published-aggregate assertions for V28.

Reads 120 *public V24 summary cells* only; NEVER the old OHLC or
private execution-row archive, and does not rerun the 2025-26 backtest.
"""
from __future__ import annotations
import csv
import copy
import json
import io
import tempfile
from pathlib import Path
from importlib import import_module
import unittest

m = import_module(
    "research.soxx-multitimeframe-cycle-2026-10-11.prospective_validation_v26.stress_surface_v28"
)


def modified(mutator) -> str:
    source = m.FILE.read_text()
    reader = csv.DictReader(io.StringIO(source))
    rows = list(reader)
    mutator(rows)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=reader.fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


class TestV28PublishedStressAudit(unittest.TestCase):
    def test_exact_pinned_summary_and_no_new_market_evidence(self):
        result = m.load_verified_v24()
        self.assertEqual(result["original_parent_episodes"], 91)
        self.assertEqual(result["expected_cells"], 120)
        self.assertFalse(result["market_rows_reloaded"])
        self.assertFalse(result["new_backtest"])
        self.assertFalse(result["trusted_market_fill_source"])
        self.assertFalse(result["production_or_trading_accepted"])
        self.assertEqual(result["V24_csv_sha256"], m.V24_SHA256)

    def test_all_checkpoint_sign_fragility_instead_of_best_arm(self):
        result = m.load_verified_v24()["summary"]
        self.assertEqual(result["all:30m"]["positive_delay_arms"],
                         {0: 3, 10: 3, 25: 3, 50: 2, 100: 0})
        self.assertEqual(result["all:3h"]["positive_delay_arms"],
                         {0: 2, 10: 1, 25: 0, 50: 0, 100: 0})
        self.assertEqual(result["all:30m"]["frozen_arm_means_pp"]["d1"]["bp50"],
                         -0.014226)
        self.assertEqual(result["all:3h"]["frozen_arm_means_pp"]["d4"]["bp25"],
                         -0.046431)

    def test_group_heterogeneity_prevents_pooled_transport_claim(self):
        result = m.load_verified_v24()["summary"]
        self.assertEqual(result["inspected:3h"]["positive_delay_arms"][0], 3)
        self.assertEqual(result["new_semis:3h"]["positive_delay_arms"][0], 0)
        self.assertEqual(result["sector:3h"]["positive_delay_arms"][0], 0)
        self.assertEqual(result["sector:30m"]["positive_delay_arms"][0], 0)
        self.assertEqual(result["new_semis:30m"]["positive_delay_arms"][50], 3)
        self.assertEqual(result["inspected:30m"]["parent_episodes_not_independent_trials"], 34)

    def test_omitted_changing_loser_episode_is_not_ignored(self):
        def corrupt(rows):
            rows.pop()
        with self.assertRaisesRegex(ValueError, "incomplete frozen stress grid"):
            m.audit_surface_text(modified(corrupt))

    def test_duplicate_grid_cell_is_rejected(self):
        def corrupt(rows):
            rows.append(dict(rows[0]))
        with self.assertRaisesRegex(ValueError, "duplicate frozen"):
            m.audit_surface_text(modified(corrupt))

    def test_unregistered_arm_is_rejected(self):
        def corrupt(rows):
            rows[0]["delay_5m_bars"] = "3"
        with self.assertRaisesRegex(ValueError, "unregistered"):
            m.audit_surface_text(modified(corrupt))

    def test_inf_cohort_mean_is_rejected(self):
        def corrupt(rows):
            rows[2]["mean_delta_pp"] = "inf"
        with self.assertRaisesRegex(ValueError, "not finite"):
            m.audit_surface_text(modified(corrupt))

    def test_ownership_cohort_denominator_change_is_rejected(self):
        def corrupt(rows):
            rows[0]["n"] = "90"
        with self.assertRaisesRegex(ValueError, "denominator"):
            m.audit_surface_text(modified(corrupt))

    def test_changing_one_subgroup_mean_breaks_aggregate_reconciliation(self):
        def corrupt(rows):
            target = next(x for x in rows if x["group"] == "new_semis"
                          and x["checkpoint_h"] == "0.5"
                          and x["delay_5m_bars"] == "1"
                          and x["extra_sell_slip_bp"] == "25")
            target["mean_delta_pp"] = "0.99"
        with self.assertRaisesRegex(ValueError, "does not reconcile"):
            m.audit_surface_text(modified(corrupt))

    def test_harmed_winner_count_reconciles_all_subgroups(self):
        def corrupt(rows):
            target = next(x for x in rows if x["group"] == "new_semis"
                          and x["checkpoint_h"] == "0.5"
                          and x["delay_5m_bars"] == "2"
                          and x["extra_sell_slip_bp"] == "25")
            target["harmed_original_winners"] = "9"
        with self.assertRaisesRegex(ValueError, "diagnostics do not partition"):
            m.audit_surface_text(modified(corrupt))

    def test_largest_harm_is_real_subset_extreme_not_a_pooled_invention(self):
        def corrupt(rows):
            target = next(x for x in rows if x["group"] == "all"
                          and x["checkpoint_h"] == "3.0"
                          and x["delay_5m_bars"] == "2"
                          and x["extra_sell_slip_bp"] == "50")
            target["biggest_negative_delta"] = "-88"
        with self.assertRaisesRegex(ValueError, "worst episode diagnostic"):
            m.audit_surface_text(modified(corrupt))

    def test_cost_stress_cannot_appear_to_improve_original_return(self):
        def corrupt(rows):
            target = next(x for x in rows if x["group"] == "all"
                          and x["checkpoint_h"] == "3.0"
                          and x["delay_5m_bars"] == "1"
                          and x["extra_sell_slip_bp"] == "100")
            target["mean_delta_pp"] = "5"
        with self.assertRaisesRegex(ValueError, "reconcile|cost"):
            m.audit_surface_text(modified(corrupt))

    def test_discretionary_sales_stay_fixed_across_adverse_costs(self):
        def corrupt(rows):
            target = next(x for x in rows if x["group"] == "sector"
                          and x["checkpoint_h"] == "3.0"
                          and x["delay_5m_bars"] == "1"
                          and x["extra_sell_slip_bp"] == "100")
            target["discretionary_sales"] = "1"
        with self.assertRaisesRegex(ValueError, "nonpartitioned|changing population"):
            m.audit_surface_text(modified(corrupt))

    def test_published_source_cannot_be_silently_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "mutated.csv"
            p.write_text(modified(lambda rows: rows[0].update(
                {"mean_delta_pp": "0.141369"})))
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                m.load_verified_v24(p)

    def test_cross_artifact_result_and_spec_match_without_market_replay(self):
        out = m.load_verified_v24()
        self.assertEqual(out["V24_results_json_sha256"],
                         "070be15b276b052029c5d6dbb86029899ddab0c4b65138c91bc6f4b759ad5030")
        self.assertEqual(out["V24_spec_sha256"],
                         "b3d6032ff3f3b3a4edc354cfd5afd0de8df4d589c81aa4403be0881fe232d568")
        self.assertEqual(out["original_SOXX_parent_entries"], 11)
        self.assertTrue(out["v24_authentic_boats_history_absent"])

    def test_changed_published_result_artifact_cannot_pass_digest_gate(self):
        source = json.loads(m.RESULT_FILE.read_text())
        source["predeclared_stress"][0]["mean_delta_pp"] += 1.0
        with tempfile.TemporaryDirectory() as folder:
            altered = Path(folder) / "RESULTS_V24.json"
            altered.write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError, "results JSON SHA256 mismatch"):
                m.load_verified_v24(results_path=altered)

    def test_false_quote_replay_proof_does_not_survive_cross_source_check(self):
        original = json.loads(m.RESULT_FILE.read_text())
        mutated = copy.deepcopy(original)
        mutated["NO_AUTHENTIC_BOATS_HISTORY"] = False
        with self.assertRaisesRegex(ValueError, "historical source claim"):
            m.corroborate_v24_result(m.FILE.read_text(), mutated, m.SPEC_FILE.read_bytes())

    def test_one_json_stress_row_cannot_disagree_with_published_csv(self):
        original = json.loads(m.RESULT_FILE.read_text())
        original["predeclared_stress"][4]["mean_delta_pp"] += 0.01
        with self.assertRaisesRegex(ValueError, "CSV/JSON mismatch"):
            m.corroborate_v24_result(m.FILE.read_text(), original, m.SPEC_FILE.read_bytes())

    def test_soxx_original_parent_count_cannot_inflate_in_result_metadata(self):
        original = json.loads(m.RESULT_FILE.read_text())
        soxx = next(x for x in original["input_source_inventory"] if x["symbol"] == "SOXX")
        soxx["count"] = 12
        with self.assertRaisesRegex(ValueError, "SOXX source census|91 original"):
            m.corroborate_v24_result(m.FILE.read_text(), original, m.SPEC_FILE.read_bytes())

    def test_bad_schema_is_rejected(self):
        source = m.FILE.read_text().replace("mean_delta_pp", "nominal_goodness")
        with self.assertRaisesRegex(ValueError, "schema mismatch"):
            m.audit_surface_text(source)


if __name__ == "__main__":
    unittest.main()
