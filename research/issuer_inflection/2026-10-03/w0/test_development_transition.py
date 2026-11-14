#!/usr/bin/env python3
"""Semantic/shape tests for development-only I3 candidate transitions."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from baseline_replay import canonical
from development_transition import REFUSAL, build_transitions

ROOT = Path(__file__).resolve().parent
SCHEMA = json.loads((ROOT / "issuer_state_transition.candidate.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def projection_hash(value: dict) -> str:
    projected = deepcopy(value)
    projected.pop("transition_id")
    projected["reproducibility"]["semantic_projection_sha256"] = "0" * 64
    return hashlib.sha256(canonical(projected)).hexdigest()


class DevelopmentTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.values = build_transitions()

    def test_exact_three_cases_and_all_validate_candidate_shape(self) -> None:
        self.assertEqual(set(self.values), {
            "first_availability_revenue",
            "unchanged_revenue",
            "assets_cross_filing_refusal",
        })
        for name, value in self.values.items():
            with self.subTest(name=name):
                VALIDATOR.validate(value)

    def test_every_case_is_development_rights_fail_closed_and_powerless(self) -> None:
        for name, value in self.values.items():
            with self.subTest(name=name):
                self.assertEqual(value["meaning"]["evidence_maturity"], "development_golden")
                self.assertEqual(value["clocks"]["reconstruction_mode"], "development_reconstruction")
                self.assertIsNone(value["clocks"]["emitted_at"])
                self.assertEqual(value["rights"], {"state":"not_admitted","decision_refs":[],"consumer_purpose_refs":[]})
                self.assertEqual(value["materiality"], [])
                self.assertEqual(value["mechanism"], [])
                self.assertTrue(all(flag is False for key, flag in value["authority"].items() if key != "class"))
                self.assertEqual(value["comparison"]["state"], "not_evaluable")
                self.assertIsNone(value["comparison"]["admission_ref"])

    def test_first_availability_is_not_labeled_growth(self) -> None:
        value = self.values["first_availability_revenue"]
        variable = value["baseline"]["variables"][0]
        self.assertEqual(variable["state"], "missing")
        self.assertIsNone(variable["value_ref"])
        self.assertIsNone(value["comparison"]["before_value"])
        self.assertEqual(value["comparison"]["after_value"], "416161000000")
        self.assertIsNone(value["comparison"]["absolute_change"])
        self.assertIn("availability", value["comparison"]["refusal_reason"])

    def test_unchanged_owner_value_is_retained_without_semantic_admission(self) -> None:
        value = self.values["unchanged_revenue"]
        variable = value["baseline"]["variables"][0]
        self.assertEqual(variable["state"], "unchanged")
        self.assertIsNotNone(variable["value_ref"])
        self.assertEqual(value["comparison"]["before_value"], "416161000000")
        self.assertEqual(value["comparison"]["after_value"], "416161000000")
        self.assertIsNone(value["comparison"]["absolute_change"])
        self.assertIn("unadmitted", value["comparison"]["refusal_reason"])

    def test_cross_filing_assets_preserve_exact_refusal_and_baseline(self) -> None:
        value = self.values["assets_cross_filing_refusal"]
        variable = value["baseline"]["variables"][0]
        self.assertEqual(variable["state"], "available")
        self.assertIsNotNone(variable["value_ref"])
        self.assertEqual(value["comparison"]["before_value"], "359241000000")
        self.assertIsNone(value["comparison"]["after_value"])
        self.assertEqual(value["comparison"]["refusal_reason"], REFUSAL)
        self.assertEqual(value["correction"]["source_correction_refs"], [])
        self.assertTrue(any(item["role"] == "missing" and item["limitation"] == REFUSAL for item in value["evidence"]))

    def test_same_source_occurrence_is_one_dependence_group_not_two_confirmations(self) -> None:
        value = self.values["unchanged_revenue"]
        groups = [item["dependence_group_ref"] for item in value["evidence"]]
        self.assertEqual(groups[0], groups[1])
        self.assertEqual(groups[0]["owner_ref"], "FIF_RAW_LEDGER")

    def test_transition_identity_and_semantic_projection_are_deterministic(self) -> None:
        again = build_transitions()
        self.assertEqual(self.values, again)
        for name, value in self.values.items():
            digest = projection_hash(value)
            self.assertEqual(value["reproducibility"]["semantic_projection_sha256"], digest)
            self.assertEqual(value["transition_id"], f"i3devtransition_{name}_{digest[:24]}")

    def test_owner_response_refs_are_hash_bound_not_naked_ids(self) -> None:
        for value in self.values.values():
            refs = [value["issuer_ref"], value["definition_ref"], value["baseline"]["cutoff_ref"], *value["reproducibility"]["source_refs"]]
            for ref in refs:
                self.assertRegex(ref["content_sha256"], r"^[0-9a-f]{64}$")
                self.assertTrue(ref["revision_id"])
                self.assertTrue(ref["owner_ref"])

    def test_no_lineage_receipt_is_smuggled_into_cross_filing_refusal(self) -> None:
        raw = canonical(self.values["assets_cross_filing_refusal"])
        self.assertNotIn(b"lineage_receipt_", raw)
        self.assertNotIn(b"parent_document_id", raw)

    def test_output_mutation_does_not_change_later_composition(self) -> None:
        original = build_transitions()
        mutated = build_transitions()
        mutated["unchanged_revenue"]["authority"]["may_rank"] = True
        mutated["assets_cross_filing_refusal"]["comparison"]["refusal_reason"] = "CORRUPTED"
        self.assertEqual(build_transitions(), original)


if __name__ == "__main__":
    unittest.main()
