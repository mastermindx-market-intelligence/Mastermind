#!/usr/bin/env python3
"""Finite research examples and package checks; NOT native production tests.

No network, market data, credentials, deployment or application imports.
Run: python3 verify_research.py
Writes CONSISTENCY_RESULTS.json with scope, counts and script digest.
"""
from __future__ import annotations
import hashlib
import io
import json
import re
import sys
import unittest
from datetime import datetime, timezone
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def residual(h0: int, h1: int, s0: int, s1: int) -> F:
    """Toy proportional-scaling arithmetic, not an economic identification model."""
    if s0 <= 0 or s1 < 0:
        raise ValueError("invalid fund units")
    return F(h1) - F(h0 * s1, s0)


def stamp(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    return dt


class FiniteExamples(unittest.TestCase):
    def test_01_pure_proportional_scaling(self):
        self.assertEqual(residual(1000, 1100, 100, 110), 0)

    def test_02_custom_basket_nonidentification(self):
        # Same observations: pro-rata basket + trade OR custom basket + no trade.
        world_a = 1000 + 100 + 50
        world_b = 1000 + 150 + 0
        self.assertEqual(world_a, world_b)
        self.assertEqual(residual(1000, world_a, 100, 110), 50)
        self.assertNotEqual(50, 0)  # The two unobserved market-trade quantities differ.

    def test_03_zero_residual_does_not_prove_no_trading(self):
        self.assertEqual(1000 + 100, 1000 + 100 + 80 - 80)
        self.assertEqual(residual(1000, 1100, 100, 110), 0)

    def test_04_net_issuance_does_not_identify_gross(self):
        self.assertEqual(10 - 0, 110 - 100)
        self.assertNotEqual(10 + 0, 110 + 100)

    def test_05_fund_split_is_not_issuance(self):
        raw_units_change = 200 - 100
        split_adjusted_change = 200 - 2 * 100
        self.assertEqual(raw_units_change, 100)
        self.assertEqual(split_adjusted_change, 0)

    def test_06_issuer_split_is_not_purchase(self):
        self.assertEqual(2000 - 1000, 1000)
        self.assertEqual(2000 - 2 * 1000, 0)

    def test_07_observed_vs_issuer_hhi(self):
        observed = F(40, 50) ** 2 + F(10, 50) ** 2
        partial = F(40, 100) ** 2 + F(10, 100) ** 2
        self.assertEqual(observed, F(68, 100))
        self.assertEqual(partial, F(17, 100))
        self.assertNotEqual(observed, partial)

    def test_08_missing_distribution_prevents_full_hhi(self):
        partial = F(17, 100)
        one_unknown = partial + F(50, 100) ** 2
        fifty_unknown = partial + 50 * F(1, 100) ** 2
        self.assertEqual(one_unknown, F(42, 100))
        self.assertEqual(fifty_unknown, F(175, 1000))
        self.assertNotEqual(one_unknown, fifty_unknown)

    def test_09_overlapping_legal_claims_are_not_additive(self):
        parent = {"lot-a", "lot-b"}
        subsidiary = {"lot-a"}
        self.assertEqual(len(parent) + len(subsidiary), 3)
        self.assertEqual(len(parent | subsidiary), 2)

    def test_10_dilution_changes_pct_without_sale(self):
        quantity = 10
        self.assertEqual(F(quantity, 100), F(1, 10))
        self.assertEqual(F(quantity, 200), F(1, 20))
        self.assertEqual(quantity - quantity, 0)

    def test_11_price_only_weight_change(self):
        q_a = q_b = 10
        w0 = F(q_a * 10, q_a * 10 + q_b * 10)
        w1 = F(q_a * 20, q_a * 20 + q_b * 10)
        self.assertEqual(w0, F(1, 2))
        self.assertEqual(w1, F(2, 3))
        self.assertNotEqual(w0, w1)

    def test_12_value_unit_mismatch(self):
        self.assertEqual(1000 * 1000, 1000000)
        self.assertNotEqual(1000, 1000000)

    def test_13_public_and_system_eligibility_differ(self):
        public = stamp("2026-08-14T21:20:00+00:00")
        recorded = stamp("2026-08-17T13:02:00+00:00")
        emitted = stamp("2026-08-17T13:06:00+00:00")
        cutoff = stamp("2026-08-17T13:04:00+00:00")
        self.assertLessEqual(public, cutoff)
        self.assertLessEqual(recorded, cutoff)
        self.assertGreater(emitted, cutoff)
        self.assertGreater(max(public, recorded, emitted), cutoff)

    def test_14_latest_dependency_controls_eligibility(self):
        filing = stamp("2026-08-14T10:00:00+00:00")
        identity = stamp("2026-08-20T10:00:00+00:00")
        cutoff = stamp("2026-08-17T10:00:00+00:00")
        self.assertGreater(max(filing, identity), cutoff)

    def test_15_later_correction_preserves_old_information(self):
        versions = [(stamp("2026-08-14T10:00:00+00:00"), 100),
                    (stamp("2026-09-01T10:00:00+00:00"), 120)]
        cutoff = stamp("2026-08-20T10:00:00+00:00")
        historical = max((v for v in versions if v[0] <= cutoff), key=lambda v: v[0])[1]
        self.assertEqual(historical, 100)
        self.assertEqual(versions[-1][1], 120)

    def test_16_partial_amendment_preserves_unmentioned_rows(self):
        original = {"row-a": 10, "row-b": 20}
        amendment = {"row-a": 11}
        merged = {**original, **amendment}
        self.assertEqual(merged, {"row-a": 11, "row-b": 20})
        self.assertNotEqual(merged, amendment)

    def test_17_omitted_position_does_not_identify_zero(self):
        # Under the stated illustrative omission thresholds, both worlds omit.
        def appears(q: int, price: int) -> bool:
            return q > 0 and not (q < 10000 and q * price < 200000)
        self.assertFalse(appears(0, 10))
        self.assertFalse(appears(100, 10))
        self.assertNotEqual(0, 100)

    def test_18_date_precision_and_timezone(self):
        low = stamp("2026-08-14T00:00:00-04:00")
        high = stamp("2026-08-15T00:00:00-04:00")
        cutoff = stamp("2026-08-14T09:30:00-04:00")
        self.assertLess(low, cutoff)
        self.assertGreater(high, cutoff)
        with self.assertRaises(ValueError):
            stamp("2026-08-14T09:30:00")


class PackageChecks(unittest.TestCase):
    def test_19_report_has_all_required_sections(self):
        text = (ROOT / "FINAL_REPORT.md").read_text()
        sections = re.findall(r"^## ([A-L])\. ", text, re.M)
        self.assertEqual(sections, list("ABCDEFGHIJKL"))

    def test_20_fixture_specification_has_36_unique_rows(self):
        text = (ROOT / "FINAL_REPORT.md").read_text()
        ids = re.findall(r"^\| (T\d{2}) \|", text, re.M)
        self.assertEqual(ids, [f"T{i:02d}" for i in range(1, 37)])

    def test_21_audit_register_has_36_unique_rows(self):
        text = (ROOT / "AUDIT_LEDGER.md").read_text()
        ids = re.findall(r"^\| (A\d{2}) \|", text, re.M)
        self.assertEqual(ids, [f"A{i:02d}" for i in range(1, 37)])

    def test_22_local_links_and_explicit_source_anchors(self):
        for path in ROOT.glob("*.md"):
            text = path.read_text()
            for target in re.findall(r"\]\(([^)]+)\)", text):
                if target.startswith(("https://", "http://", "mailto:")):
                    continue
                file_part, _, anchor = target.partition("#")
                dest = ROOT / file_part if file_part else path
                self.assertTrue(dest.is_file(), f"missing {path.name}: {target}")
                if anchor:
                    self.assertIn(f'id="{anchor}"', dest.read_text(), target)

    def test_23_no_stale_chat_citation_tokens(self):
        for path in ROOT.glob("*.md"):
            text = path.read_text()
            self.assertNotIn("\ue200", text, path.name)
            self.assertIsNone(re.search(r"turn\d+(file|view|search)\d+", text), path.name)

    def test_24_acquired_sources_are_explicitly_not_behavioral_proof(self):
        data = json.loads((ROOT / "REPOSITORY_SOURCE_INVENTORY.json").read_text())
        self.assertEqual(len(data["files"]), 66)
        for item in data["files"]:
            self.assertEqual(item["status"], "FETCHED")
            self.assertRegex(item["ref"], r"^[0-9a-f]{40}$")
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(item["git_blob_sha"], r"^[0-9a-f]{40}$")
            self.assertIn(item["ref"], item["url"])
        report = (ROOT / "FINAL_REPORT.md").read_text()
        self.assertIn("Acquisition is not semantic inspection", report)
        self.assertIn("not 36 executed production tests", report)


def main() -> int:
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    output = stream.getvalue()
    print(output, end="")
    summary = {
        "schema": "commission10.research_consistency.v1",
        "scope": "18 finite synthetic examples + 6 documentation/package checks; not native tests, backtests or production qualification",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skips": len(result.skipped),
        "passed": result.wasSuccessful(),
        "details": output,
    }
    (ROOT / "CONSISTENCY_RESULTS.json").write_text(json.dumps(summary, indent=2) + "\n")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
