"""Tests for the redacted PBR decision-case fixtures (schema pbr.decision_case_fixture.v1).

Stdlib only. The fixtures are redacted, provenance-pinned extracts of
production decision rows (capture 2026-10-22T073549Z, manifest sha256
4c55f3f8...); the builder ``_build_decision_cases.py`` must regenerate every
fixture byte-for-byte from the original capture extracts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
FIXTURE_DIR = TESTS_DIR / "fixtures" / "pbr" / "decision_cases"
BUILDER = FIXTURE_DIR / "_build_decision_cases.py"

SCHEMA = "pbr.decision_case_fixture.v1"
MANIFEST_SHA256 = "4c55f3f8df454ecfcb2742b0b7bec5043ac35d4919a66026888541fa4bf976aa"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
DECISION_ID = re.compile(r"^decision\.v1\.[0-9a-f]{24}$")

EXPECTED = {
    "mu_2026-10-02_entry": ("regression", "A14", "MU"),
    "mu_2026-10-05_amendment": ("regression", "A15", "MU"),
    "mu_2026-10-22_planless_summary": ("regression", "A15", "MU"),
    "cn_688062_2026-08-12_sizing": ("regression", "A16", "688062.SS"),
    "xom_2026-08-12_positive_control": ("positive_control", "none", "XOM"),
}

# Byte-regeneration needs the original (non-redacted) capture extracts, which are
# evidence, not repository content. Point PBR_DECISION_CASE_INPUT_DIR at a directory
# holding case_rows.jsonl, case_fills.jsonl and the capture MANIFEST.json to run it.
INPUT_DIR = Path(os.environ.get("PBR_DECISION_CASE_INPUT_DIR", "/nonexistent/pbr-decision-case-inputs"))
INPUTS = (INPUT_DIR / "case_rows.jsonl", INPUT_DIR / "case_fills.jsonl", INPUT_DIR / "MANIFEST.json")


def load(case_id: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{case_id}.json").read_text(encoding="utf-8"))


def all_fixtures() -> dict:
    return {case_id: load(case_id) for case_id in EXPECTED}


def record_by_line(fixture: dict, line_index: int) -> dict:
    for record in fixture["records"]:
        if record["line_index_0based"] == line_index:
            return record
    raise AssertionError(f"line {line_index} not among records")


class DecisionCaseFixtureTests(unittest.TestCase):
    def test_all_five_fixtures_load_with_schema_case_id_and_role(self):
        for case_id, (role, defect_ref, ticker) in EXPECTED.items():
            with self.subTest(case_id=case_id):
                fixture = load(case_id)
                self.assertEqual(fixture["schema"], SCHEMA)
                self.assertEqual(fixture["case_id"], case_id)
                self.assertEqual(fixture["case_role"], role)
                self.assertEqual(fixture["defect_ref"], defect_ref)
                self.assertEqual(fixture["ticker"], ticker)
                self.assertEqual(fixture["capture"]["manifest_sha256"], MANIFEST_SHA256)
                for key in (
                    "capture",
                    "provenance",
                    "redaction",
                    "records",
                    "fills",
                    "linkage_note",
                    "external_facts",
                    "derived",
                    "records_sha256",
                ):
                    self.assertIn(key, fixture)

    def test_provenance_hashes_are_hex64_and_decision_ids_match(self):
        for case_id, fixture in all_fixtures().items():
            with self.subTest(case_id=case_id):
                self.assertTrue(fixture["provenance"])
                for prov in fixture["provenance"]:
                    self.assertRegex(prov["line_sha256"], HEX64)
                    self.assertRegex(prov["source_file_sha256"], HEX64)
                    self.assertRegex(prov["decision_id"], DECISION_ID)
                for fill in fixture["fills"]:
                    self.assertRegex(fill["line_sha256"], HEX64)

    def test_records_sha256_recomputes(self):
        for case_id, fixture in all_fixtures().items():
            with self.subTest(case_id=case_id):
                payload = json.dumps(
                    fixture["records"], sort_keys=True, ensure_ascii=False, separators=(",", ":")
                )
                self.assertEqual(hashlib.sha256(payload.encode("utf-8")).hexdigest(), fixture["records_sha256"])

    def test_redaction_dropped_perception_input_and_filtered_holdings(self):
        for case_id, fixture in all_fixtures().items():
            with self.subTest(case_id=case_id):
                for record in fixture["records"]:
                    self.assertNotIn("perception_input", record["row"])
                    # Filtered to the case ticker; legitimately empty when the
                    # case ticker was exited out of that record's holdings.
                    self.assertTrue(
                        all(h["ticker"] == fixture["ticker"] for h in record["row"]["holdings"])
                    )
                    self.assertTrue(
                        all(h["ticker"] == fixture["ticker"] for h in record["row"]["effective_holdings"])
                    )

    def test_mu_entry_falsifier_names_2026_10_22_and_external_fact_predates_asof(self):
        fixture = load("mu_2026-10-02_entry")
        record = record_by_line(fixture, 75)
        self.assertIn("2026-10-22", record["case_holding"]["falsifier"])
        asof = date.fromisoformat(record["row"]["asof"])
        dated = [f for f in fixture["external_facts"] if "event_date" in f]
        self.assertTrue(dated)
        self.assertTrue(
            any(date.fromisoformat(f["event_date"]) < asof for f in dated),
            "expected an external fact with event_date before the record asof",
        )
        for fact in fixture["external_facts"]:
            self.assertEqual(fact["verification_status"], "cited_by_audit_not_refetched")

    def test_mu_entry_fills_are_exactly_the_settlement_linked_ones(self):
        fixture = load("mu_2026-10-02_entry")
        record = record_by_line(fixture, 75)
        linked_ids = set(record["row"]["settlement_fill_ids"])
        fill_ids = {f["row"]["fill_id"] for f in fixture["fills"]}
        self.assertTrue(fill_ids)
        self.assertEqual(fill_ids, fill_ids & linked_ids)
        for fill in fixture["fills"]:
            self.assertEqual(fill["linked_decision_ids"], [record["decision_id"]])

    def test_mu_amendment_records_falsifier_and_exit_plan_changes(self):
        fixture = load("mu_2026-10-05_amendment")
        changes = fixture["derived"]["case_holding_changes"]
        self.assertIn("falsifier", changes)
        self.assertIn("exit_plan", changes)
        self.assertNotEqual(changes["falsifier"]["old"], changes["falsifier"]["new"])
        self.assertNotEqual(changes["exit_plan"]["old"], changes["exit_plan"]["new"])
        falsifier_changes = fixture["derived"]["case_row_falsifier_changes"]
        self.assertNotEqual(falsifier_changes["old"], falsifier_changes["new"])
        self.assertEqual(fixture["fills"], [])

    def test_planless_summary_mu_absent_and_planless_sentence_present(self):
        fixture = load("mu_2026-10-22_planless_summary")
        record_89 = record_by_line(fixture, 89)
        self.assertIsNone(record_89["case_holding"])
        self.assertIsNone(record_89["case_effective_holding"])
        self.assertFalse(fixture["derived"]["ticker_in_holdings"]["89"])
        sentences = fixture["derived"]["summary_and_memo_sentences"]
        self.assertTrue(
            any(
                "held_without_active_plan" in s["sentence"] or "no live thesis" in s["sentence"]
                for s in sentences
            )
        )
        self.assertTrue(fixture["derived"]["mu_exit_decisions"])
        self.assertTrue(fixture["derived"]["mu_requested_exit_decisions"])

    def test_cn_688062_weight_is_medium_cap_and_rationale_says_starter(self):
        fixture = load("cn_688062_2026-08-12_sizing")
        record_35 = record_by_line(fixture, 35)
        self.assertEqual(record_35["case_holding"]["weight"], 0.12)
        self.assertIn("starter", record_35["case_holding"]["rationale"])
        cap_reference = fixture["derived"]["cap_reference"]
        self.assertEqual(cap_reference["file"], "brain/decision_submission.py")
        self.assertEqual(cap_reference["line"], 450)
        self.assertEqual(cap_reference["caps"], {"high": 0.18, "medium": 0.12, "low": 0.06})
        self.assertIn('"conviction_caps"', cap_reference["quote"])

    def test_xom_positive_control_has_fills(self):
        fixture = load("xom_2026-08-12_positive_control")
        self.assertGreaterEqual(len(fixture["fills"]), 1)
        self.assertTrue(all(f["row"]["ticker"] == "XOM" for f in fixture["fills"]))

    def test_regeneration_reproduces_identical_bytes(self):
        if not all(path.exists() for path in INPUTS):
            self.skipTest(
                f"capture inputs not present at {INPUT_DIR} (set PBR_DECISION_CASE_INPUT_DIR); "
                "byte-regeneration check skipped"
            )
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "decision_cases"
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(BUILDER),
                    str(INPUTS[0]),
                    str(INPUTS[1]),
                    str(INPUTS[2]),
                    str(out_dir),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            for case_id in EXPECTED:
                regenerated = (out_dir / f"{case_id}.json").read_bytes()
                committed = (FIXTURE_DIR / f"{case_id}.json").read_bytes()
                self.assertEqual(
                    regenerated, committed, f"{case_id}.json does not regenerate byte-for-byte"
                )


if __name__ == "__main__":
    unittest.main()
