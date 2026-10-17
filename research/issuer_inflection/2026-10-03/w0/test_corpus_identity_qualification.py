#!/usr/bin/env python3
"""Hermetic checks for metadata-only I3 corpus identity qualification.

These checks validate source-controlled evidence only. They do not contact SEC,
assign event/revision IDs, inspect filing bodies, grant rights, register a
trial, or establish validation/prediction performance.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
RECORD = ROOT / "evidence/CORPUS_IDENTITY_QUALIFICATION.json"
CANDIDATE = ROOT / "CORPUS_PRESELECTION_CANDIDATE.md"
ROLES = {
    "beta_validation_candidate": 12,
    "prospective_temporal_holdout_candidate": 12,
    "broad_reserve_candidate": 6,
}
CIK = re.compile(r"^[0-9]{10}$")


def _candidate_rows() -> list[tuple]:
    rows = []
    for line in CANDIDATE.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| "):
            continue
        parts = [item.strip() for item in line.strip("|").split("|")]
        if len(parts) != 6 or parts[0] not in ROLES:
            continue
        role, proxy, pos, ticker, issuer, security = parts
        rows.append(
            (role, proxy, int(pos), ticker, issuer[1:-1], security[1:-1])
        )
    return rows


def _record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


class CorpusIdentityQualificationTests(unittest.TestCase):
    def test_exact_frozen_candidate_set_is_preserved(self) -> None:
        record = _record()
        actual = [
            (
                row["role"],
                row["proxy"],
                row["position"],
                row["ticker"],
                row["issuer_id"],
                row["security_id"],
            )
            for row in record["rows"]
        ]
        self.assertEqual(actual, _candidate_rows())

    def test_thirty_unique_canonical_identities(self) -> None:
        rows = _record()["rows"]
        self.assertEqual(len(rows), 30)
        self.assertEqual(len({row["issuer_id"] for row in rows}), 30)
        self.assertEqual(len({row["security_id"] for row in rows}), 30)
        self.assertEqual(len({row["issuer_cik"] for row in rows}), 30)

    def test_role_counts_are_frozen(self) -> None:
        rows = _record()["rows"]
        self.assertEqual(
            {role: sum(row["role"] == role for row in rows) for role in ROLES},
            ROLES,
        )

    def test_every_identity_is_resolved_and_active(self) -> None:
        for row in _record()["rows"]:
            with self.subTest(ticker=row["ticker"]):
                self.assertIs(row["identity_qualified"], True)
                self.assertEqual(row["issuer_status"], "active")
                self.assertEqual(row["security_issuer_state"], "RESOLVED")
                self.assertEqual(row["security_country"], "US")
                self.assertIn(row["security_mic"], {"XNAS", "XNYS"})
                self.assertRegex(row["issuer_cik"], CIK)
                self.assertEqual(row["issuer_evidence_source"], "sec_company_tickers")
                self.assertEqual(row["issuer_evidence_snapshot"], "2026-08-18")

    def test_no_event_or_body_was_admitted(self) -> None:
        for row in _record()["rows"]:
            with self.subTest(ticker=row["ticker"]):
                self.assertIsNone(row["event_id"])
                self.assertIsNone(row["source_revision_id"])
                self.assertIs(row["body_read"], False)
                self.assertEqual(row["source_support_status"], "UNASSIGNED_PRE_BODY")
                self.assertIs(row["trial_registered"], False)

    def test_public_financial_rights_remain_unadmitted(self) -> None:
        record = _record()
        self.assertIs(record["rights_registry_has_sec_edgar"], False)
        for row in record["rows"]:
            self.assertEqual(
                row["public_financial_rights_status"],
                "NOT_ADMITTED_ON_PROTECTED_MAIN",
            )

    def test_development_exposed_names_are_not_in_candidate(self) -> None:
        tickers = {row["ticker"] for row in _record()["rows"]}
        self.assertNotIn("AAPL", tickers)
        self.assertNotIn("PG", tickers)

    def test_prospective_holdout_still_has_no_event_identity(self) -> None:
        rows = [
            row
            for row in _record()["rows"]
            if row["role"] == "prospective_temporal_holdout_candidate"
        ]
        self.assertEqual(len(rows), 12)
        self.assertTrue(
            all(row["event_id"] is None and not row["body_read"] for row in rows)
        )

    def test_current_proxy_is_not_historical_eligibility(self) -> None:
        record = _record()
        self.assertIs(record["preselection_reproducible"], True)
        self.assertIs(record["current_proxy_historical_eligibility"], False)
        self.assertEqual(
            record["selection_protocol_sha256"],
            "14e73eee775cfdba6085997ac01e033d0aea0e54abc00dd32e4147f2f447d0ef",
        )
        self.assertEqual(
            record["historical_eligibility_pit_blob"],
            "ec7085bc7460aca4a07661fa5983c424e1559be8",
        )

    def test_maturity_flags_remain_non_promotional(self) -> None:
        maturity = _record()["maturity"]
        self.assertEqual(maturity["identity_qualification"], "PASS")
        for key in (
            "source_event_qualification",
            "rights_admission",
            "holdout_event_assignment",
            "trial_registered",
            "classification_validated",
            "prediction_validated",
        ):
            self.assertIs(maturity[key], False)


if __name__ == "__main__":
    unittest.main()
