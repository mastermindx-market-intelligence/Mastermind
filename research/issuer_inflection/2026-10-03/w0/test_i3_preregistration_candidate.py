#!/usr/bin/env python3
"""Validate the unregistered I3 W0 preregistration candidate.

This checks frozen research-law content only. It opens no filing body/outcome,
mutates no registry, and cannot promote the candidate into a registered trial.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "PREREGISTRATION_CANDIDATE.md"
WITNESS = ROOT / "evidence/CORPUS_BETA_PIT_MEMBERSHIP_WITNESS.json"
BEGIN = "<!-- I3_PREREG_JSON_BEGIN -->"
END = "<!-- I3_PREREG_JSON_END -->"


def candidate() -> dict:
    text = DOC.read_text(encoding="utf-8")
    block = text.split(BEGIN, 1)[1].split(END, 1)[0].strip()
    if not block.startswith("```json\n") or not block.endswith("```"):
        raise AssertionError("machine block is not a fenced JSON object")
    return json.loads(block[len("```json\n"):-len("```")].strip())


class PreregistrationCandidateTests(unittest.TestCase):
    def test_candidate_is_explicitly_unregistered_and_non_authorizing(self) -> None:
        value = candidate()
        self.assertEqual(value["candidate_state"], "NOT_REGISTERED")
        for key in (
            "trial_registered",
            "body_inspection_authorized",
            "outcome_inspection_authorized",
            "production_emission_authorized",
        ):
            self.assertIs(value[key], False)
        self.assertTrue(all(v is False for k, v in value["authority"].items() if k != "class"))

    def test_beta_selection_identity_matches_prebody_witness(self) -> None:
        value = candidate()
        raw = WITNESS.read_bytes()
        witness = json.loads(raw)
        self.assertEqual(
            value["immutable_inputs"]["beta_event_selection_sha256"],
            witness["selection_sha256"],
        )
        self.assertEqual(
            value["immutable_inputs"]["beta_pit_witness_file_sha256"],
            hashlib.sha256(raw).hexdigest(),
        )
        self.assertEqual(len(witness["rows"]), 12)
        self.assertTrue(all(row["body_read"] is False for row in witness["rows"]))
        self.assertTrue(all(row["event_assigned"] is False for row in witness["rows"]))

    def test_split_and_holdout_laws_remain_leakage_safe(self) -> None:
        corpus = candidate()["corpus"]
        self.assertEqual(corpus["split_unit"], "issuer_time_source_revision_family")
        self.assertIs(corpus["random_row_split_forbidden"], True)
        self.assertEqual(corpus["prospective_temporal_holdout_candidates"]["event_identity_state"], "FUTURE_UNASSIGNED")
        self.assertEqual(corpus["sealed_external_holdout"]["e3_eight_revision_corpus"], "EXCLUDED_DO_NOT_OPEN")
        self.assertIs(corpus["beta_prebody_candidates"]["historical_business_family_qualified"], False)
        self.assertIs(corpus["beta_prebody_candidates"]["current_proxy_is_discovery_only"], True)

    def test_reconstruction_and_classification_targets_are_frozen(self) -> None:
        tracks = candidate()["tracks"]
        self.assertEqual(tracks["R"]["coverage_floor"], 0.80)
        self.assertEqual(tracks["C"]["precision_min"], 0.95)
        self.assertEqual(tracks["C"]["recall_min"], 0.80)
        self.assertEqual(tracks["C"]["precision_lower_95_bound_min"], 0.85)
        self.assertEqual(tracks["C"]["predicted_positive_independent_units_min"], 100)
        self.assertEqual(tracks["C"]["adjudicated_positive_independent_units_min"], 100)
        self.assertIs(tracks["C"]["underpowered_is_not_pass"], True)

    def test_utility_trial_cannot_start_without_separate_power_freeze(self) -> None:
        utility = candidate()["tracks"]["U"]
        self.assertEqual(utility["state"], "CHILD_PREREG_REQUIRED_BEFORE_UTILITY_OUTCOMES")
        self.assertEqual(utility["minimum_decision_useful_effect_absolute"], 0.10)
        self.assertEqual(utility["secondary_median_time_reduction_min"], 0.20)
        self.assertIs(utility["pilot_required_for_power_and_sample_size"], True)
        self.assertIs(utility["pilot_reuse_in_confirmatory_trial"], False)
        self.assertIs(utility["current_confirmatory_sample_size_frozen"], False)

    def test_prediction_has_no_universal_alpha_or_live_influence(self) -> None:
        prediction = candidate()["tracks"]["P"]
        self.assertEqual(prediction["state"], "NO_PREDICTIVE_TRIAL_REGISTERED_IN_W0")
        self.assertIsNone(prediction["universal_alpha_threshold"])
        self.assertIs(prediction["decision_path_influence"], False)
        self.assertIs(prediction["feature_specific_economic_target_required"], True)
        self.assertIs(prediction["feature_specific_power_sensitivity_required"], True)

    def test_multiplicity_and_stopping_cannot_reward_peeking(self) -> None:
        value = candidate()
        self.assertEqual(value["multiplicity"]["formal_confirmatory_secondary_family_control"], "Holm")
        self.assertIs(value["multiplicity"]["no_aggregate_success_score"], True)
        self.assertIs(value["stopping"]["adaptive_stop_for_favorable_result"], False)
        self.assertEqual(value["stopping"]["insufficient_power_disposition"], "UNDERPOWERED")
        self.assertEqual(value["stopping"]["validation_case_used_for_method_repair_becomes"], "DEVELOPMENT_EVIDENCE")

    def test_rights_and_exposure_remain_fail_closed(self) -> None:
        value = candidate()
        self.assertTrue(all(state != "ADMITTED" for state in value["rights_purposes"].values() if isinstance(state, str)))
        self.assertIs(value["rights_purposes"]["unknown_or_revoked_blocks_use"], True)
        self.assertIs(value["exposure_capture"]["runtime_exposure_writer_admitted"], False)
        for key in ("ui_display_event", "machine_model_receipt", "alert_emission_event"):
            self.assertTrue(value["exposure_capture"][key].startswith("SEPARATE_REQUIRED"))

    def test_amendment_cannot_rewrite_spent_validation_cases(self) -> None:
        amendment = candidate()["amendment"]
        self.assertIs(amendment["new_version_required"], True)
        self.assertIs(amendment["prior_result_visibility_required"], True)
        self.assertIs(amendment["silent_replacement_forbidden"], True)
        self.assertIs(amendment["repaired_validation_case_becomes_development"], True)
        self.assertIs(amendment["fresh_holdout_required_after_holdout_contamination"], True)

    def test_open_gates_are_named_not_tbd(self) -> None:
        gates = candidate()["open_registration_gates"]
        self.assertGreaterEqual(len(gates), 4)
        self.assertTrue(all("TBD" not in gate.upper() for gate in gates))
        self.assertIn("canonical_registry_serialized_writer_and_post_write_readback", gates)
        self.assertIn("independent_architecture_source_owner_acceptance", gates)


if __name__ == "__main__":
    unittest.main()
