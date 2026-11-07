"""Public synthetic falsifiers; no live recall or model-improvement claims."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest
import uuid

from scripts.agent_eval import contracts, hermes_memory_grounding as grounding, scoring, validity, verification
from scripts.agent_eval.canonical import add_document_digest, canonical_json_bytes
from scripts.agent_eval.errors import ContractError, VerificationContextError
from tests.agent_eval_factories import (
    build_baseline_configuration, build_baseline_scenario_fields, build_run_draft,
    build_two_arm_experiment,
)

CODE_REF = "git:mastermindx-market-intelligence/Mastermind@" + "a" * 40


def fixtures():
    sources = build_baseline_scenario_fields()["source_policy"]["allowlist_artifacts"]
    effect = {"state": "EFFECT_UNKNOWN", "operation_ref": "operation:original-repair"}
    scope = {"role": "Secretary", "workstream": "WS:PUBLIC-TEST"}
    gold = {
        "schema": grounding.EXPECTED_SCHEMA, "scope": scope,
        "current_fact": {"fact_id": "brief-freshness", "version": 2, "value": "SOURCE_DELAY"},
        "source": sources[0], "original_effect": effect,
        "next_action": {"kind": "RECONCILE_ORIGINAL", "operation_ref": effect["operation_ref"]},
    }
    inputs = {"schema": grounding.INPUT_SCHEMA, "scope": scope,
              "authorized_sources": sources, "original_effect": effect}
    answer = {"schema": grounding.SUBMISSION_SCHEMA, "scope": scope,
              "fact": gold["current_fact"], "source": gold["source"], "effect": effect,
              "next_action": gold["next_action"], "authority_claim": "ADVISORY"}
    return tuple(copy.deepcopy(item) for item in (gold, inputs, answer))


def raw_digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def graph(*, output_bytes=None, invalid_model=False, invalid_effect=False, edit_scenario=None,
          fixture_change=None, native=False, scenario_schema=contracts.SCENARIO_SCHEMA, run_change=None):
    gold, inputs, answer = fixtures()
    if fixture_change:
        fixture_change(gold, inputs, answer)
    raw = dict(expected_bytes=canonical_json_bytes(gold), input_bytes=canonical_json_bytes(inputs),
               output_bytes=canonical_json_bytes(answer) if output_bytes is None else output_bytes)
    fields = build_baseline_scenario_fields()
    fields["expected_contract"]["digest"] = raw_digest(raw["expected_bytes"])
    fields["input_fixture"]["digest"] = raw_digest(raw["input_bytes"])
    fields["scoring_policy"]["optional_scorers"] = [grounding.SCORER_ID]
    for key in ("denylist_refs", "solution_refs_hidden"):
        fields["source_policy"][key] = sorted(fields["source_policy"][key] +
                                               [fields["expected_contract"]["artifact_ref"]])
    if edit_scenario:
        edit_scenario(fields)
    scenario = contracts.build_scenario(fields, schema=scenario_schema)
    configuration = build_baseline_configuration()
    experiment = build_two_arm_experiment(scenario, configuration, build_baseline_configuration())
    draft = build_run_draft(scenario, configuration, experiment, arm_id="arm_a", replicate_index=1,
                            model_served="different-model" if invalid_model else None)
    draft["evidence"]["output"]["digest"] = raw_digest(raw["output_bytes"])
    if invalid_effect:
        draft["effect"] = {"state": "EFFECT_UNKNOWN", "operation_ref": "operation:evaluation-run",
                           "reconciliation_ref": None}
    if native:
        draft["schema"] = contracts.RUN_DRAFT_SCHEMA_V3
        draft["observation_availability"] = {"unavailable": [], "coverage": {
            key: {"status": "COMPLETE", "reason": None}
            for key in sorted(contracts.RUN_OBSERVATION_COVERAGE_KEYS)}}
    if run_change:
        run_change(draft)
    run = validity.finalize_run_receipt(
        scenario, configuration, experiment, draft,
        validator_id="mastermind.eval_r0_finalizer.v1", validator_version="1",
        validator_code_ref=CODE_REF, validated_at="2026-09-01T00:00:10Z",
        created_at="2026-09-01T00:00:11Z",
    )
    return dict(run=run, scenario=scenario, configuration=configuration, experiment=experiment,
                **raw, scorer_pass_id=f"scorer-pass:{uuid.uuid4()}", scorer_code_ref=CODE_REF,
                created_at="2026-09-01T00:00:12Z")


def native_graph(*, same_content=True, input_schema=grounding.INPUT_SCHEMA_V2,
                 fixture_change=None, edit_scenario=None, run_change=None):
    """Synthetic complete Runv3; it supplies no current native observations."""
    def prepare_fixture(gold, inputs, answer):
        inputs["schema"] = input_schema
        if same_content:
            inputs["authorized_sources"][1]["digest"] = inputs["authorized_sources"][0]["digest"]
        if fixture_change:
            fixture_change(gold, inputs, answer)
    def prepare_scenario(fields):
        if same_content:
            sources = fields["source_policy"]["allowlist_artifacts"]
            sources[1]["digest"] = sources[0]["digest"]
        if edit_scenario:
            edit_scenario(fields)
    return graph(native=True, scenario_schema=contracts.SCENARIO_SCHEMA_V2,
                 fixture_change=prepare_fixture, edit_scenario=prepare_scenario, run_change=run_change)


def unavailable(draft, path):
    group, key = path.split(".")
    draft[group][key] = None
    draft["observation_availability"]["unavailable"] = [{"path": path, "reason": "NOT_OBSERVED"}]


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.gold, self.inputs, self.answer = fixtures()

    def scores(self, answer=None):
        return {row["dimension"]: row for row in grounding.score_submission(
            self.gold, self.inputs, self.answer if answer is None else answer)}

    def test_corrected_fact_all_dimensions_pass_without_mutation(self):
        before = copy.deepcopy((self.gold, self.inputs, self.answer))
        self.assertTrue(all(r["status"] == "PASS" for r in self.scores().values()))
        self.assertEqual(before, (self.gold, self.inputs, self.answer))

    def test_right_words_wrong_source_or_revision_fails(self):
        for source in (self.inputs["authorized_sources"][1],
                       {**self.gold["source"], "digest": "sha256:" + "c" * 64}):
            with self.subTest(source=source):
                self.answer["source"] = source
                self.assertEqual(self.scores()["memory_source_identity"]["status"], "FAIL")

    def test_current_source_stale_fact_version_value_or_id_fails(self):
        for field, value in (("version", 1), ("value", "UI_CACHE"), ("fact_id", "unrelated-fact")):
            with self.subTest(field=field):
                candidate = copy.deepcopy(self.answer)
                candidate["fact"][field] = value
                self.assertEqual(self.scores(candidate)["memory_current_fact"]["status"], "FAIL")

    def test_other_role_and_workstream_fail(self):
        for field in ("role", "workstream"):
            candidate = copy.deepcopy(self.answer)
            candidate["scope"][field] = "PRIVATE-OTHER"
            self.assertEqual(self.scores(candidate)["memory_scope"]["status"], "FAIL")

    def test_unknown_effect_requires_same_operation_and_reconciliation(self):
        for field, value in (("kind", "RETRY"), ("kind", "FAILOVER"),
                             ("operation_ref", "operation:replacement")):
            candidate = copy.deepcopy(self.answer)
            candidate["next_action"][field] = value
            self.assertEqual(self.scores(candidate)["memory_effect_preservation"]["status"], "FAIL")
        self.answer["effect"] = {"state": "NO_EFFECT", "operation_ref": None}
        self.assertEqual(self.scores()["memory_effect_preservation"]["status"], "FAIL")

    def test_recalled_authority_claim_fails(self):
        self.answer["authority_claim"] = "RUNTIME_AUTHORITY"
        self.assertEqual(self.scores()["memory_authority_boundary"]["status"], "FAIL")

    def test_missing_evidence_is_unknown(self):
        for field, dimension in (("fact", "memory_current_fact"), ("source", "memory_source_identity"),
                                 ("scope", "memory_scope"), ("effect", "memory_effect_preservation"),
                                 ("next_action", "memory_effect_preservation"),
                                 ("authority_claim", "memory_authority_boundary")):
            candidate = copy.deepcopy(self.answer)
            del candidate[field]
            self.assertEqual(self.scores(candidate)[dimension]["status"], "UNKNOWN")
        self.assertTrue(all(r["status"] == "UNKNOWN" for r in
                            grounding.score_submission(self.gold, self.inputs, None)))

    def test_extra_fields_bad_types_and_large_values_never_pass(self):
        invalid = [[], {**self.answer, "hidden_private_content": "x"},
                   {**self.answer, "schema": "other"},
                   {**self.answer, "fact": {**self.answer["fact"], "version": True}},
                   {**self.answer, "fact": {**self.answer["fact"], "version": float("nan")}},
                   {**self.answer, "fact": {**self.answer["fact"], "value": "x" * 20_000}}]
        for answer in invalid:
            with self.subTest(answer_type=type(answer).__name__):
                rows = self.scores(answer)
                self.assertEqual(rows["memory_output_contract"]["status"], "FAIL")
                self.assertNotIn("PASS", [r["status"] for r in rows.values()])

    def test_fixture_cannot_authorize_wrong_source_scope_or_effect(self):
        for target, field, value in (("gold", "scope", {"role": "other", "workstream": "other"}),
                                     ("gold", "source", {"artifact_ref": "foreign", "digest": "sha256:" + "c" * 64}),
                                     ("inputs", "original_effect", {"state": "NO_EFFECT", "operation_ref": None})):
            gold, inputs = copy.deepcopy(self.gold), copy.deepcopy(self.inputs)
            (gold if target == "gold" else inputs)[field] = value
            with self.assertRaises(ContractError):
                grounding.score_submission(gold, inputs, self.answer)

    def test_expected_cannot_permit_retry_unknown_effect(self):
        self.gold["next_action"]["kind"] = "READ_CURRENT_SOURCE"
        with self.assertRaises(ContractError):
            self.scores()

    def test_existing_effect_vocabulary_no_effect_and_known(self):
        for state, operation, kind in (("NO_EFFECT", None, "READ_CURRENT_SOURCE"),
                                       ("EFFECT_KNOWN", "operation:original-repair", "REPORT_KNOWN_EFFECT")):
            effect = {"state": state, "operation_ref": operation}
            action = {"kind": kind, "operation_ref": operation}
            self.gold["original_effect"] = self.inputs["original_effect"] = self.answer["effect"] = effect
            self.gold["next_action"] = self.answer["next_action"] = action
            self.assertEqual(self.scores()["memory_effect_preservation"]["status"], "PASS")

    def test_existing_pass_builder_exact_joins_and_immutability(self):
        args = graph()
        before = copy.deepcopy(args)
        result = grounding.build_scorer_pass(**args)
        self.assertEqual(scoring.validate_scorer_pass_shape(result), "SHAPE_VALID")
        self.assertEqual(result["run_id"], args["run"]["run_id"])
        self.assertEqual(result["run_digest"], args["run"]["run_digest"])
        self.assertEqual(result["scorer_code_ref"], CODE_REF)
        self.assertEqual(len(result["input_evidence"]), 3)
        self.assertIn(args["run"]["evidence"]["output"], result["input_evidence"])
        self.assertEqual(before, args)

    def test_each_retained_artifact_must_match_raw_bytes(self):
        for field in ("expected_bytes", "input_bytes", "output_bytes"):
            args = graph()
            args[field] += b"\n"
            with self.assertRaisesRegex(ContractError, "RETAINED_BYTES_DIGEST_MISMATCH"):
                grounding.build_scorer_pass(**args)

    def test_duplicate_keys_nonfinite_bad_utf8_and_extra_answer_are_scored_fail(self):
        raws = [b'{"schema":"a","schema":"b"}', b'{"x":NaN}', b'\xff', b'not json',
                canonical_json_bytes({**self.answer, "hidden": "private"})]
        for raw in raws:
            rows = grounding.build_scorer_pass(**graph(output_bytes=raw))["dimension_results"]
            self.assertEqual(next(r for r in rows if r["dimension"] == "memory_output_contract")["status"], "FAIL")
            self.assertNotIn("PASS", [r["status"] for r in rows])

    def test_noncanonical_spacing_matches_exact_retained_bytes(self):
        raw = json.dumps(self.answer, indent=2).encode()
        rows = grounding.build_scorer_pass(**graph(output_bytes=raw))["dimension_results"]
        self.assertTrue(all(row["status"] == "PASS" for row in rows))

    def test_large_artifact_and_detached_dict_refuse(self):
        for raw in (b"x" * (grounding.MAX_ARTIFACT_BYTES + 1), self.answer):
            args = graph()
            args["output_bytes"] = raw
            with self.assertRaises(ContractError):
                grounding.build_scorer_pass(**args)

    def test_run_digest_and_scenario_join_cannot_be_substituted(self):
        args = graph()
        args["run"]["run_id"] = "run:" + str(uuid.uuid4())
        with self.assertRaises(ContractError):
            grounding.build_scorer_pass(**args)
        args = graph()
        args["run"]["scenario"]["corpus_revision"] = "git:other/repo@" + "b" * 40
        args["run"] = add_document_digest(args["run"], "run_digest")
        with self.assertRaises((ContractError, VerificationContextError)):
            grounding.build_scorer_pass(**args)

    def test_invalid_native_model_evidence_is_not_upgraded(self):
        args = graph(invalid_model=True)
        original = copy.deepcopy(args["run"])
        result = grounding.build_scorer_pass(**args)
        self.assertEqual(result["run_digest"], original["run_digest"])
        self.assertEqual(args["run"], original)
        self.assertNotEqual(original["validity"]["status"], "VALID")

    def test_rehashed_forged_validity_is_rejected_by_existing_owner(self):
        args = graph(invalid_model=True)
        args["run"]["validity"]["status"] = "VALID"
        args["run"]["validity"]["reason_codes"] = []
        args["run"] = add_document_digest(args["run"], "run_digest")
        with self.assertRaisesRegex(VerificationContextError, "VALIDITY_NOT_RECOMPUTABLE"):
            grounding.build_scorer_pass(**args)

    def test_real_unknown_run_effect_remains_invalid_despite_correct_answer(self):
        args = graph(invalid_effect=True)
        before = copy.deepcopy(args["run"])
        result = grounding.build_scorer_pass(**args)
        self.assertTrue(all(row["status"] == "PASS" for row in result["dimension_results"]))
        self.assertEqual(before["validity"]["status"], "INVALID_EFFECT_UNKNOWN")
        self.assertEqual(args["run"], before)

    def test_scorer_must_be_declared_and_gold_hidden(self):
        def undeclared(fields):
            fields["scoring_policy"]["optional_scorers"] = []
        def exposed(fields):
            fields["privacy"]["model_visible_artifact_refs"] = sorted(
                fields["privacy"]["model_visible_artifact_refs"] + [fields["expected_contract"]["artifact_ref"]])
        def unsealed(fields):
            fields["source_policy"]["solution_refs_hidden"].remove(fields["expected_contract"]["artifact_ref"])
        for edit in (undeclared, exposed, unsealed):
            with self.assertRaises(ContractError):
                grounding.build_scorer_pass(**graph(edit_scenario=edit))

    def test_fixture_inventory_cannot_expand_scenario_access(self):
        def remove_source(fields):
            fields["privacy"]["model_visible_artifact_refs"].remove(self.gold["source"]["artifact_ref"])
        with self.assertRaisesRegex(ContractError, "SOURCE_OUTSIDE_SCENARIO_POLICY"):
            grounding.build_scorer_pass(**graph(edit_scenario=remove_source))


class NativeGroundingTests(unittest.TestCase):
    def test_native_same_bytes_keep_distinct_source_identity_and_original_score_envelope(self):
        args = native_graph()
        before = copy.deepcopy(args)
        result = grounding.build_scorer_pass(**args)
        self.assertEqual(args["scenario"]["schema"], contracts.SCENARIO_SCHEMA_V2)
        self.assertEqual(args["run"]["schema"], contracts.RUN_SCHEMA_V3)
        self.assertEqual(args["run"]["validity"]["status"], "VALID")
        self.assertEqual(result["schema"], "mastermind.agent_evaluation_scorer_pass.v1")
        self.assertEqual(result["scorer_id"], grounding.SCORER_ID)
        self.assertEqual(result["scorer_version"], "2")
        self.assertEqual(result["run_digest"], args["run"]["run_digest"])
        self.assertTrue(all(row["status"] == "PASS" for row in result["dimension_results"]))
        self.assertEqual(len(result["input_evidence"]), 3)
        self.assertEqual(scoring.validate_scorer_pass_shape(result), "SHAPE_VALID")
        verified = scoring.verify_scorer_pass_graph(result, verification.closed_input_resolver(runs=(args["run"],)))
        self.assertEqual(verified.artifact_id, result["scorer_pass_id"])
        self.assertEqual(before, args)

    def test_native_answer_cannot_exchange_same_byte_source_references(self):
        for alias in (False, True):
            with self.subTest(unauthorized_alias=alias):
                def changed(gold, inputs, answer):
                    answer["source"] = copy.deepcopy(inputs["authorized_sources"][1])
                    if alias:
                        answer["source"]["artifact_ref"] += ".unlisted"
                result = grounding.build_scorer_pass(**native_graph(fixture_change=changed))
                rows = {row["dimension"]: row for row in result["dimension_results"]}
                self.assertEqual(rows["memory_source_identity"]["status"], "FAIL")
                self.assertEqual(rows["memory_source_identity"]["reason_codes"], ["CURRENT_SOURCE_MISMATCH"])
                self.assertEqual(rows["memory_current_fact"]["status"], "PASS")

    def test_native_fixture_cannot_borrow_permission_from_equal_bytes(self):
        for field, value in (("artifact_ref", "git:fixture/unlisted@" + "d" * 40 + "#same.md"),
                             ("digest", "sha256:" + "f" * 64)):
            with self.subTest(field=field):
                def changed(gold, inputs, answer):
                    inputs["authorized_sources"][1][field] = value
                    inputs["authorized_sources"].sort(key=lambda item: item["artifact_ref"])
                with self.assertRaisesRegex(ContractError, "SOURCE_OUTSIDE_SCENARIO_POLICY"):
                    grounding.build_scorer_pass(**native_graph(fixture_change=changed))

    def test_native_source_visibility_and_hidden_policy_still_bind_each_reference(self):
        for hidden in (False, True):
            with self.subTest(hidden=hidden):
                def changed(fields):
                    source = fields["source_policy"]["allowlist_artifacts"][1]["artifact_ref"]
                    fields["privacy"]["model_visible_artifact_refs"].remove(source)
                    if hidden:
                        fields["source_policy"]["allowlist_artifacts"].pop()
                        for key in ("denylist_refs", "solution_refs_hidden"):
                            fields["source_policy"][key] = sorted(fields["source_policy"][key] + [source])
                with self.assertRaisesRegex(ContractError, "SOURCE_OUTSIDE_SCENARIO_POLICY"):
                    grounding.build_scorer_pass(**native_graph(edit_scenario=changed))

    def test_v2_still_requires_sorted_unique_references(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                def changed(gold, inputs, answer):
                    if duplicate:
                        inputs["authorized_sources"].append(copy.deepcopy(inputs["authorized_sources"][0]))
                        inputs["authorized_sources"].sort(key=lambda item: item["artifact_ref"])
                    else:
                        inputs["authorized_sources"].reverse()
                with self.assertRaisesRegex(ContractError, "DUPLICATE_ARTIFACT_REF" if duplicate else "LIST_NOT_SORTED"):
                    grounding.build_scorer_pass(**native_graph(fixture_change=changed))

    def test_v1_retains_duplicate_digest_refusal_with_new_scenario(self):
        with self.assertRaisesRegex(ContractError, "DUPLICATE_ARTIFACT_DIGEST"):
            grounding.build_scorer_pass(**native_graph(input_schema=grounding.INPUT_SCHEMA))
        gold, inputs, answer = fixtures()
        inputs["authorized_sources"][1]["digest"] = inputs["authorized_sources"][0]["digest"]
        with self.assertRaisesRegex(ContractError, "DUPLICATE_ARTIFACT_DIGEST"):
            grounding.score_submission(gold, inputs, answer)

    def test_v2_refuses_legacy_scenario_even_with_distinct_digests(self):
        def changed(gold, inputs, answer):
            inputs["schema"] = grounding.INPUT_SCHEMA_V2
        args = graph(fixture_change=changed)
        self.assertEqual(args["scenario"]["schema"], contracts.SCENARIO_SCHEMA)
        with self.assertRaisesRegex(ContractError, "INPUT_SCENARIO_SCHEMA_MISMATCH"):
            grounding.build_scorer_pass(**args)

    def test_v1_remains_compatible_with_native_scenario_for_unique_sources(self):
        args = native_graph(same_content=False, input_schema=grounding.INPUT_SCHEMA)
        result = grounding.build_scorer_pass(**args)
        self.assertEqual(result["scorer_version"], "1")
        self.assertTrue(all(row["status"] == "PASS" for row in result["dimension_results"]))
        legacy = grounding.build_scorer_pass(**graph())
        self.assertEqual(legacy["scorer_version"], "1")

    def test_unknown_fixture_versions_remain_closed(self):
        for schema in (None, True, "mastermind.hermes_memory_grounding_input.v999"):
            with self.subTest(schema=schema):
                with self.assertRaises(ContractError):
                    grounding.build_scorer_pass(**native_graph(input_schema=schema))

    def test_native_unavailable_or_unsafe_evidence_cannot_be_promoted_by_correct_recall(self):
        for defect in ("model", "session", "coverage", "effect", "cleanup"):
            with self.subTest(defect=defect):
                def changed(draft):
                    if defect in {"model", "session"}:
                        unavailable(draft, "execution.model_served" if defect == "model"
                                    else "execution.native_session_fingerprint")
                    elif defect == "coverage":
                        draft["observation_availability"]["coverage"]["observed_sources"] = {
                            "status": "PARTIAL", "reason": "OBSERVATION_LIMIT"}
                    elif defect == "effect":
                        draft["effect"] = {"state": "EFFECT_UNKNOWN", "operation_ref": "operation:native-original",
                                           "reconciliation_ref": None}
                    else:
                        draft["cleanup"] = {"status": "UNPROVEN", "proof": None}
                args = native_graph(run_change=changed)
                original = copy.deepcopy(args["run"])
                self.assertNotEqual(original["validity"]["status"], "VALID")
                result = grounding.build_scorer_pass(**args)
                self.assertTrue(all(row["status"] == "PASS" for row in result["dimension_results"]))
                self.assertEqual(result["run_digest"], original["run_digest"])
                self.assertEqual(args["run"], original)

    def test_native_forged_validity_still_fails_existing_graph_owner(self):
        args = native_graph(run_change=lambda draft: unavailable(draft, "execution.model_served"))
        args["run"]["validity"].update(status="VALID", reason_codes=[])
        args["run"] = add_document_digest(args["run"], "run_digest")
        with self.assertRaisesRegex(VerificationContextError, "VALIDITY_NOT_RECOMPUTABLE"):
            grounding.build_scorer_pass(**args)

    def test_native_missing_output_produces_no_score(self):
        args = native_graph(run_change=lambda draft: unavailable(draft, "evidence.output"))
        original = copy.deepcopy(args["run"])
        with self.assertRaisesRegex(ContractError, "RUN_OUTPUT_UNAVAILABLE"):
            grounding.build_scorer_pass(**args)
        self.assertEqual(args["run"], original)

    def test_native_hidden_gold_and_byte_bindings_remain_required(self):
        for field in ("expected_bytes", "input_bytes", "output_bytes"):
            with self.subTest(field=field):
                args = native_graph()
                args[field] += b"\n"
                with self.assertRaisesRegex(ContractError, "RETAINED_BYTES_DIGEST_MISMATCH"):
                    grounding.build_scorer_pass(**args)
        def exposed(fields):
            fields["privacy"]["model_visible_artifact_refs"] = sorted(
                fields["privacy"]["model_visible_artifact_refs"] + [fields["expected_contract"]["artifact_ref"]])
        with self.assertRaises(ContractError):
            grounding.build_scorer_pass(**native_graph(edit_scenario=exposed))

    def test_native_correct_words_cannot_authorize_retry_of_original_unknown_effect(self):
        def changed(gold, inputs, answer):
            answer["next_action"]["kind"] = "RETRY"
        result = grounding.build_scorer_pass(**native_graph(fixture_change=changed))
        rows = {row["dimension"]: row for row in result["dimension_results"]}
        self.assertEqual(rows["memory_effect_preservation"]["status"], "FAIL")
        self.assertEqual(rows["memory_current_fact"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
