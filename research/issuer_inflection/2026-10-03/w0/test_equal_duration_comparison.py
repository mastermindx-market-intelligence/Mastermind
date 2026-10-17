#!/usr/bin/env python3
"""Adversarial tests for the development-only equal-duration comparator.

These tests use the already-captured AAPL owner response. They do not establish
source-owner admission, annual/YoY semantics, publication rights, an I3 runtime
schema, product integration, trial registration, or production evidence.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from equal_duration_comparison import (
    ComparisonRefusal,
    compare_owner_cells,
    load_verified_comparison,
)

ROOT = Path(__file__).resolve().parent
RESPONSE = ROOT / "evidence/aapl_same_filing_annual_revenue.response.json"
EXPECTED_RESPONSE_SHA = "a752302d0d11457920be1425cb9ebb6d1f29560b7f1e8f41a5de98075083c6af"
OWNER_ENTITY_ID = "0000320193"


def _root_cells() -> list[dict]:
    response = json.loads(RESPONSE.read_text())
    roots = set(response["receipt"]["root_cell_ids"])
    cells = [deepcopy(node) for node in response["receipt"]["nodes"] if node["cell_id"] in roots]
    return sorted(cells, key=lambda cell: cell["period"]["start"])


class EqualDurationComparatorTests(unittest.TestCase):
    def test_verified_aapl_result_is_descriptive_not_annual(self) -> None:
        result = load_verified_comparison()
        self.assertEqual(result["schema"], "issuer_inflection.equal_duration_comparison.dev/v1")
        self.assertEqual(result["relationship_state"], "descriptive_equal_duration_source_intervals")
        self.assertEqual(result["metric_id"], "revenue")
        self.assertEqual(result["unit"], "USD")
        self.assertEqual(result["prior_value"], "391035000000")
        self.assertEqual(result["current_value"], "416161000000")
        self.assertEqual(result["absolute_change"], "25126000000")
        self.assertEqual(
            result["relative_change_exact"],
            {"numerator": "502520", "denominator": "78207"},
        )
        self.assertEqual(result["relative_change_percent_display"], "6.43")
        self.assertEqual(result["interval_days"], 364)
        self.assertEqual(result["inferred_week_count"], 52)
        self.assertIs(result["owner_typed_annual"], False)
        self.assertIs(result["annual_or_yoy_claim_permitted"], False)
        self.assertIs(result["economic_interpretation"], None)
        self.assertIs(result["comparison_admitted"], False)
        self.assertIs(result["product_publication_admitted"], False)
        self.assertIs(result["trial_registered"], False)
        self.assertIs(result["emitted_at"], None)

    def test_display_labels_do_not_create_fiscal_semantics(self) -> None:
        prior, current = _root_cells()
        expected = compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)
        prior["period"]["label"] = "NOT_A_FISCAL_TYPE"
        current["period"]["label"] = "ALSO_NOT_A_FISCAL_TYPE"
        actual = compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)
        self.assertEqual(actual["comparison_id"], expected["comparison_id"])
        self.assertEqual(actual["semantic_period_basis"], expected["semantic_period_basis"])
        self.assertEqual(actual["source_labels"], ["NOT_A_FISCAL_TYPE", "ALSO_NOT_A_FISCAL_TYPE"])
        self.assertIs(actual["owner_typed_annual"], False)

    def test_generic_duration_is_required(self) -> None:
        prior, current = _root_cells()
        current["period"]["kind"] = "annual"
        with self.assertRaisesRegex(ComparisonRefusal, "period_kind"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_equal_interval_length_is_required(self) -> None:
        prior, current = _root_cells()
        current["period"]["start"] = "2024-09-30"
        current["provenance"]["selected_raw_fact"]["context"]["start"] = "2024-09-30"
        with self.assertRaisesRegex(ComparisonRefusal, "equal_duration"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_adjacent_nonoverlapping_intervals_are_required(self) -> None:
        prior, current = _root_cells()
        current["period"]["start"] = "2024-09-28"
        current["period"]["end"] = "2025-09-26"
        current["provenance"]["selected_raw_fact"]["context"]["start"] = "2024-09-28"
        current["provenance"]["selected_raw_fact"]["context"]["end"] = "2025-09-26"
        with self.assertRaisesRegex(ComparisonRefusal, "contiguous_duration"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_same_filing_revision_is_required(self) -> None:
        prior, current = _root_cells()
        current["provenance"]["selected_raw_fact"]["source"]["accession"] = "0000320193-26-000020"
        with self.assertRaisesRegex(ComparisonRefusal, "source_revision"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_same_metric_definition_and_mapping_are_required(self) -> None:
        prior, current = _root_cells()
        current["provenance"]["mapping_digest"] = "a" * 64
        with self.assertRaisesRegex(ComparisonRefusal, "definition_basis"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_same_metric_is_required(self) -> None:
        prior, current = _root_cells()
        current["metric_id"] = "total_assets"
        with self.assertRaisesRegex(ComparisonRefusal, "metric"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_same_unit_is_required(self) -> None:
        prior, current = _root_cells()
        current["unit"] = "shares"
        with self.assertRaisesRegex(ComparisonRefusal, "unit"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_same_concept_is_required(self) -> None:
        prior, current = _root_cells()
        current["provenance"]["selected_raw_fact"]["concept_qname"] = "us-gaap:SalesRevenueNet"
        with self.assertRaisesRegex(ComparisonRefusal, "concept"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_consolidated_dimensionless_scope_is_required(self) -> None:
        prior, current = _root_cells()
        current["provenance"]["selected_raw_fact"]["context"]["explicit_dimensions"] = {
            "us-gaap:StatementBusinessSegmentsAxis": "aapl:ExampleMember"
        }
        with self.assertRaisesRegex(ComparisonRefusal, "dimensions"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_matching_reported_decimals_are_required(self) -> None:
        prior, current = _root_cells()
        current["provenance"]["selected_raw_fact"]["decimals"] = "-3"
        with self.assertRaisesRegex(ComparisonRefusal, "reported_precision"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_non_value_cell_is_never_forced_into_comparison(self) -> None:
        prior, current = _root_cells()
        current["state"] = "not_evaluable"
        current["value"] = None
        current["reason"] = "unlinked source vintages require an explicit typed revision lineage"
        current["provenance"]["selected_raw_fact"] = None
        with self.assertRaisesRegex(ComparisonRefusal, "owner_value"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_nonpositive_baseline_has_no_percentage_comparison(self) -> None:
        prior, current = _root_cells()
        prior["value"] = "0"
        prior["provenance"]["selected_raw_fact"]["parsed_value"] = "0"
        with self.assertRaisesRegex(ComparisonRefusal, "positive_baseline"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_cell_issuer_identity_is_bound(self) -> None:
        prior, current = _root_cells()
        current["entity_id"] = "0000789019"
        with self.assertRaisesRegex(ComparisonRefusal, "owner_entity"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_selected_context_issuer_identity_is_bound(self) -> None:
        prior, current = _root_cells()
        current["provenance"]["selected_raw_fact"]["context"]["entity_identifier"] = "0000789019"
        with self.assertRaisesRegex(ComparisonRefusal, "owner_entity"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_selected_source_issuer_identity_is_bound(self) -> None:
        prior, current = _root_cells()
        current["provenance"]["selected_raw_fact"]["source"]["entity_id"] = "0000789019"
        with self.assertRaisesRegex(ComparisonRefusal, "owner_entity"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_provenance_issuer_identity_is_bound(self) -> None:
        prior, current = _root_cells()
        current["provenance"]["source_entity_id"] = "0000789019"
        with self.assertRaisesRegex(ComparisonRefusal, "owner_entity"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_value_status_state_must_agree(self) -> None:
        prior, current = _root_cells()
        current["status"] = "not_evaluable"
        with self.assertRaisesRegex(ComparisonRefusal, "owner_value"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_value_cannot_carry_refusal_reason(self) -> None:
        prior, current = _root_cells()
        current["reason"] = "TEST_ONLY refusal"
        current["provenance"]["reason"] = current["reason"]
        with self.assertRaisesRegex(ComparisonRefusal, "owner_value_reason"):
            compare_owner_cells(prior, current, owner_entity_id=OWNER_ENTITY_ID)

    def test_response_digest_is_a_fixed_trust_anchor(self) -> None:
        with self.assertRaisesRegex(ComparisonRefusal, "response_identity"):
            load_verified_comparison(expected_response_sha256="0" * 64)

    def test_source_labels_are_preserved_only_as_display_context(self) -> None:
        result = load_verified_comparison()
        self.assertEqual(result["source_labels"], ["FY2024", "FY2025"])
        self.assertNotIn("fiscal_year", result["semantic_period_basis"])
        self.assertEqual(result["semantic_period_basis"]["kind"], "duration")
        self.assertEqual(result["semantic_period_basis"]["calendar_kind"], "unknown")


if __name__ == "__main__":
    unittest.main()
