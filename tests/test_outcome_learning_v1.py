"""Contract + evaluator tests for the Outcome Learning V1 (OL-V1) vertical.

Happy-path builders for every artifact, plus the twelve OL-V1 kill tests (eleven
live here; kill test #11 — the CLI single-shot journal refusal — lives in
``tests/test_outcome_learning_v1_cli.py`` since it exercises the CLI, not the
contracts module directly). Every kill test constructs the BAD document literally
(never by disabling a guard) and asserts :class:`OutcomeLearningContractError`.
"""
from __future__ import annotations

import copy
import hashlib

import pytest

from control_plane.outcome_learning_contracts import (
    CANARY_TOKEN,
    OutcomeLearningContractError,
    build_canary_request,
    build_expectation,
    build_outcome,
    canonical_digest,
    scan_public_safe_text,
    seal_document,
    validate_agentos_projection,
    validate_canary_request,
    validate_evaluation,
    validate_expectation,
    validate_outcome,
    validate_preflight,
    validate_self_model,
    verify_sealed,
)
from control_plane.outcome_learning_evaluator import (
    build_agentos_projection,
    build_self_model,
    evaluate_episode,
)

RECORDED_AT = "2026-09-02T12:00:00Z"
SHA40_A = "a" * 40
SHA40_B = "b" * 40
#: Sol REQUEST_REPAIR (BLOCKER F): every Blocker B/C revalidation actually performed.
FULLY_VERIFIED_EFFECT_EDGE = {
    "parent_proven": True,
    "request_reacquired_from_sealed_commit": True,
    "request_digest_matched": True,
    "selector_repeated_single_pr": True,
    "bindings_verified": True,
}


def _digest64() -> str:
    return "sha256:" + "c" * 64


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_expectation(**overrides):
    kwargs = dict(
        decision_ref={
            "owner": "chairman_cognition",
            "type": "a1_decision_packet",
            "id": _digest64(),
        },
        operation_key="mastermind-outcome-learning-v1-complete-vertical-20260902-sol-001",
        decision_kind="organizational_learning_episode",
        recorded_at=RECORDED_AT,
        context={
            "source_refs": ["CHAIRMAN_DIRECTIVE:completion-drive-2026-09-02"],
            "task_kind": "organizational_learning_episode",
            "risk": "routine",
            "ambiguity": "low",
            "program": "organizational-learning",
            "repository": "mastermindx-market-intelligence/Mastermind",
            "source_cutoff": RECORDED_AT,
            "applicability_cohort": (
                "supervised reversible GitHub metadata canary, repository-owner PR, "
                "single episode"
            ),
        },
        alternatives=[
            {"action_id": "OPT-OLV1-PR-TITLE-CANARY", "eligible": True, "exclusion_reason": None},
            {"action_id": "OPT-OLV1-PORTFOLIO-HOLD", "eligible": True, "exclusion_reason": None},
        ],
        chosen_action="OPT-OLV1-PR-TITLE-CANARY",
        assignment={
            "method": "DETERMINISTIC",
            "probability": None,
            "probability_null_reason": "DETERMINISTIC_NO_COUNTERFACTUAL_SUPPORT",
            "policy_version": "olv1-v1",
            "randomization_unit": "N/A",
        },
        expectations=[
            {"metric_id": "effect_applied_and_restored", "horizon": "terminal", "estimate": 0.90, "lower": 0.70, "upper": 0.97, "kind": "probability"},
            {"metric_id": "head_unchanged_through_effect", "horizon": "terminal", "estimate": 0.97, "lower": 0.85, "upper": 0.995, "kind": "probability"},
            {"metric_id": "byte_identical_restoration", "horizon": "terminal", "estimate": 0.95, "lower": 0.80, "upper": 0.99, "kind": "probability"},
            {"metric_id": "effect_calls_exactly_two", "horizon": "terminal", "estimate": 0.90, "lower": 0.75, "upper": 0.98, "kind": "probability"},
            {"metric_id": "ci_green_at_final_head", "horizon": "delayed", "estimate": 0.80, "lower": 0.55, "upper": 0.95, "kind": "probability"},
        ],
        guardrails=[
            {"guardrail_id": "G1", "statement": "Two-call max."},
            {"guardrail_id": "G2", "statement": "No retry."},
        ],
        causal_question="Does one supervised PR-title canary apply and restore cleanly?",
        known_confounders=["concurrent PR editor", "GitHub API instability"],
        assumptions=[
            {"assumption_id": "OLV1-A1", "role": "LOAD_BEARING", "statement": "single open PR + head match", "evidence_refs": [], "ex_ante_confidence": 0.9, "confidence_null_reason": None, "falsifier": "preflight head mismatch"},
            {"assumption_id": "OLV1-A2", "role": "LOAD_BEARING", "statement": "apply observable, head stable", "evidence_refs": [], "ex_ante_confidence": 0.9, "confidence_null_reason": None, "falsifier": "readback mismatch"},
            {"assumption_id": "OLV1-A3", "role": "LOAD_BEARING", "statement": "byte-identical restore", "evidence_refs": [], "ex_ante_confidence": 0.9, "confidence_null_reason": None, "falsifier": "restore byte mismatch"},
            {"assumption_id": "OLV1-A4", "role": "CONTEXTUAL", "statement": "no concurrent mutator", "evidence_refs": [], "ex_ante_confidence": 0.8, "confidence_null_reason": None, "falsifier": "unexpected title bytes"},
            {"assumption_id": "OLV1-A5", "role": "CONTEXTUAL", "statement": "read-after-write adequacy", "evidence_refs": [], "ex_ante_confidence": None, "confidence_null_reason": "NOT_ASSESSABLE_IN_V1", "falsifier": "reconciliation required"},
            {"assumption_id": "OLV1-A6", "role": "CONTEXTUAL", "statement": "source states stable through window", "evidence_refs": [], "ex_ante_confidence": None, "confidence_null_reason": "NO_POST_EPISODE_RECOMPOSITION_IN_V1", "falsifier": "N/A"},
        ],
        memory_exposure={
            "pre_memory_option_set_digest": _digest64(),
            "final_option_set_digest": _digest64(),
            "final_decision_digest": _digest64(),
            "consulted": [
                {"record_ref": "DEC:OUTCOME-LEARNING-POLICY-CALIBRATION-ARCHITECTURE", "influence": "MATERIALLY_CHANGED", "why": "architecture"},
                {"record_ref": "DEC:OUTCOME-LEARNING-TWO-DECISION-CANARY-GATE", "influence": "CONSULTED_NO_CHANGE", "why": "scope"},
                {"record_ref": "DSC:HISTORICAL-ROUTING-COUNTERFACTUALS-NOT-IDENTIFIED", "influence": "CONSULTED_NO_CHANGE", "why": "no counterfactuals"},
            ],
            "source_packet_digests": [_digest64(), _digest64(), _digest64(), _digest64()],
        },
    )
    kwargs.update(overrides)
    return build_expectation(**kwargs)


def make_request(expectation, **overrides):
    kwargs = dict(
        operation_key=expectation["operation_key"],
        expectation_sealed_hash=expectation["sealed_hash"],
        repository="mastermindx-market-intelligence/Mastermind",
        branch="sol/outcome-learning-v1-complete-vertical-20260902",
        expected_parent_head=SHA40_A,
        recorded_at=RECORDED_AT,
    )
    kwargs.update(overrides)
    return build_canary_request(**kwargs)


def make_clean_outcome(expectation, request, *, head_sha=SHA40_B, original_title="Some PR title"):
    original_sha = _sha256_hex(original_title)
    applied_title = original_title + " " + CANARY_TOKEN
    applied_sha = _sha256_hex(applied_title)
    preflight = {
        "observed_at": RECORDED_AT,
        "repository": "mastermindx-market-intelligence/Mastermind",
        "pr_number": 1,
        "pr_url": "https://github.com/mastermindx-market-intelligence/Mastermind/pull/1",
        "head_sha": head_sha,
        "base_ref": "master",
        "original_title_sha256": original_sha,
        "original_title_length": len(original_title),
        "sealed_commit_sha": head_sha,
        "expectation_blob_sha": SHA40_A,
        "request_blob_sha": SHA40_A,
        "expectation_content_sha256": canonical_digest(expectation).removeprefix("sha256:"),
        "request_content_sha256": canonical_digest(request).removeprefix("sha256:"),
        "head_equals_sealed_commit": True,
        "seal_provenance": "COMMITTED_BLOBS_VERIFIED",
    }
    validate_preflight(preflight)
    effect_calls = [
        {
            "seq": 1,
            "kind": "TITLE_APPLY",
            "requested_at": RECORDED_AT,
            "method": "PATCH",
            "endpoint": "repos/mastermindx-market-intelligence/Mastermind/pulls/1",
            "payload_title_sha256": applied_sha,
            "response_status": 200,
            "readback": {
                "observed_at": RECORDED_AT,
                "title_sha256": applied_sha,
                "title_length": len(applied_title),
                "head_sha": head_sha,
            },
        },
        {
            "seq": 2,
            "kind": "TITLE_RESTORE",
            "requested_at": RECORDED_AT,
            "method": "PATCH",
            "endpoint": "repos/mastermindx-market-intelligence/Mastermind/pulls/1",
            "payload_title_sha256": original_sha,
            "response_status": 200,
            "readback": {
                "observed_at": RECORDED_AT,
                "title_sha256": original_sha,
                "title_length": len(original_title),
                "head_sha": head_sha,
            },
        },
    ]
    restoration = {
        "byte_identical": True,
        "prestate_title_sha256": original_sha,
        "poststate_title_sha256": original_sha,
        "head_unchanged": True,
    }
    return build_outcome(
        operation_key=expectation["operation_key"],
        expectation_sealed_hash=expectation["sealed_hash"],
        request=request,
        preflight=preflight,
        effect_calls=effect_calls,
        pre_effect_observation=None,
        effect_edge=FULLY_VERIFIED_EFFECT_EDGE,
        effect_state="APPLIED_AND_RESTORED",
        restoration=restoration,
        recorded_at=RECORDED_AT,
    )


def make_episode():
    expectation = make_expectation()
    request = make_request(expectation)
    outcome = make_clean_outcome(expectation, request)
    return expectation, request, outcome


# --------------------------------------------------------------------------- happy path


def test_build_expectation_seals_and_validates():
    expectation = make_expectation()
    assert expectation["schema"] == "mastermind.decision_expectation_receipt.v2"
    assert expectation["sealed_hash"].startswith("sha256:")
    verify_sealed(expectation, field="sealed_hash")
    validate_expectation(expectation)


def test_build_canary_request_is_frozen_and_valid():
    expectation = make_expectation()
    request = make_request(expectation)
    assert request["canary_token"] == CANARY_TOKEN
    assert request["max_effect_calls"] == 2
    assert request["execution_authority_granted"] is False
    validate_canary_request(request)


def test_build_outcome_cross_validates_against_expectation_and_request():
    expectation, request, outcome = make_episode()
    validate_outcome(outcome, expectation, request)
    assert outcome["effect_state"] == "APPLIED_AND_RESTORED"
    assert outcome["restoration"]["byte_identical"] is True


def test_evaluate_episode_is_descriptive_only_and_deterministic():
    expectation, request, outcome = make_episode()
    evaluation = evaluate_episode(expectation, outcome, request, recorded_at=RECORDED_AT)
    assert evaluation["causal_grade"] == "DESCRIPTIVE_ONLY"
    assert evaluation["promotion"] == "NONE"
    again = evaluate_episode(expectation, outcome, request, recorded_at=RECORDED_AT)
    assert evaluation == again

    by_id = {item["assumption_id"]: item["resolution"] for item in evaluation["assumption_resolutions"]}
    assert by_id["OLV1-A1"] == "HELD"
    assert by_id["OLV1-A2"] == "HELD"
    assert by_id["OLV1-A3"] == "HELD"
    assert by_id["OLV1-A6"] == "NOT_TESTED"

    delayed = next(f for f in evaluation["forecast"] if f["metric_id"] == "ci_green_at_final_head")
    assert delayed["realized"] is None
    assert delayed["within_interval"] is None


def test_build_self_model_is_n1_and_non_promoting():
    expectation, request, outcome = make_episode()
    evaluation = evaluate_episode(expectation, outcome, request, recorded_at=RECORDED_AT)
    self_model = build_self_model(evaluation, expectation, recorded_at=RECORDED_AT)
    assert self_model["sample_size"] == 1
    assert self_model["sample_state"] == "INSUFFICIENT_SAMPLE"
    assert self_model["promotion"] == "NONE"
    assert self_model["authority"] == "NONE"
    assert self_model["universal_score"] is None
    assert all(self_model["memory_law"].values())


def test_build_agentos_projection_is_candidate_only():
    expectation, request, outcome = make_episode()
    evaluation = evaluate_episode(expectation, outcome, request, recorded_at=RECORDED_AT)
    projection = build_agentos_projection(
        evaluation, expectation, outcome, recorded_at=RECORDED_AT, key_hint="OLV1-EPISODE-2026-09-02"
    )
    assert projection["automatic_writes"] is False
    assert projection["grants_authority"] is False
    kinds = {c["kind"] for c in projection["candidates"]}
    assert "DSC_CANDIDATE" in kinds
    assert "WS_UPDATE_CANDIDATE" in kinds
    assert all(c["status"] == "CANDIDATE_ONLY" for c in projection["candidates"])
    validate_agentos_projection(projection, evaluation)


def test_scan_public_safe_text_accepts_clean_document():
    expectation = make_expectation()
    scan_public_safe_text(expectation)  # must not raise


# --------------------------------------------------------------------------- kill tests


def test_kill_1_outcome_referencing_wrong_expectation_digest():
    expectation, request, outcome = make_episode()
    other_expectation = make_expectation(operation_key="a-different-operation-key")
    bad_outcome = dict(outcome)
    bad_outcome["expectation_sealed_hash"] = other_expectation["sealed_hash"]
    with pytest.raises(OutcomeLearningContractError, match="expectation_sealed_hash"):
        validate_outcome(bad_outcome, expectation, request)


def test_kill_2_sealed_receipt_field_mutated_after_seal():
    expectation = make_expectation()
    mutated = dict(expectation)
    mutated["decision_kind"] = "some_other_kind"
    with pytest.raises(OutcomeLearningContractError, match="sealed_hash"):
        validate_expectation(mutated)
    with pytest.raises(OutcomeLearningContractError):
        verify_sealed(mutated, field="sealed_hash")


def test_kill_3_duplicate_assumption_id():
    expectation = make_expectation()
    bad = copy.deepcopy(dict(expectation))
    unsealed = {k: v for k, v in bad.items() if k != "sealed_hash"}
    unsealed["assumptions"] = list(unsealed["assumptions"]) + [dict(unsealed["assumptions"][0])]
    resealed = seal_document(unsealed, field="sealed_hash")
    with pytest.raises(OutcomeLearningContractError, match="duplicate assumptions"):
        validate_expectation(resealed)


def test_kill_4_resolution_value_outside_the_five():
    expectation, request, outcome = make_episode()
    evaluation = evaluate_episode(expectation, outcome, request, recorded_at=RECORDED_AT)
    bad = dict(evaluation)
    bad_resolutions = [dict(item) for item in bad["assumption_resolutions"]]
    bad_resolutions[0]["resolution"] = "PARTIALLY_HELD"
    bad["assumption_resolutions"] = bad_resolutions
    with pytest.raises(OutcomeLearningContractError, match="closed vocabulary"):
        validate_evaluation(bad, expectation, outcome)


def test_kill_5_secret_shape_string_anywhere_fails_public_safe_scan():
    with pytest.raises(OutcomeLearningContractError, match="PUBLIC_SAFE"):
        make_expectation(
            causal_question="leaked token ghp_1234567890abcdef1234567890abcdef1234 in prose"
        )


def test_kill_6_hidden_mutation_of_assumptions_after_sealing():
    expectation = make_expectation()
    mutated = dict(expectation)
    mutated_assumptions = [dict(item) for item in mutated["assumptions"]]
    mutated_assumptions[0] = dict(mutated_assumptions[0])
    mutated_assumptions[0]["statement"] = "a silently rewritten assumption"
    mutated["assumptions"] = mutated_assumptions
    with pytest.raises(OutcomeLearningContractError, match="sealed_hash"):
        validate_expectation(mutated)


def test_kill_7_bad_parent_head_and_head_mismatch_refuse_effect():
    expectation = make_expectation()
    with pytest.raises(OutcomeLearningContractError, match="expected_parent_head"):
        make_request(expectation, expected_parent_head="not-40-hex")

    request = make_request(expectation)
    outcome = make_clean_outcome(expectation, request)
    bad_outcome = copy.deepcopy(dict(outcome))
    bad_preflight = dict(bad_outcome["preflight"])
    bad_preflight["head_equals_sealed_commit"] = False
    bad_outcome["preflight"] = bad_preflight
    with pytest.raises(OutcomeLearningContractError, match="head_equals_sealed_commit"):
        validate_outcome(bad_outcome, expectation, request)


def test_kill_8_canary_before_sealed_commit_refused():
    expectation, request, outcome = make_episode()
    bad_outcome = copy.deepcopy(dict(outcome))
    bad_preflight = dict(bad_outcome["preflight"])
    bad_preflight["head_sha"] = "d" * 40
    bad_preflight["head_equals_sealed_commit"] = False
    bad_outcome["preflight"] = bad_preflight
    with pytest.raises(OutcomeLearningContractError, match="head_equals_sealed_commit"):
        validate_outcome(bad_outcome, expectation, request)


def test_kill_9_three_effect_calls_and_duplicate_seq_rejected():
    expectation, request, outcome = make_episode()
    three_calls = copy.deepcopy(dict(outcome))
    calls = list(three_calls["effect_calls"])
    extra = dict(calls[1])
    three_calls["effect_calls"] = calls + [extra]
    with pytest.raises(OutcomeLearningContractError, match="never exceed 2"):
        validate_outcome(three_calls, expectation, request)

    duplicate_seq = copy.deepcopy(dict(outcome))
    calls2 = [dict(c) for c in duplicate_seq["effect_calls"]]
    calls2[1] = dict(calls2[1])
    calls2[1]["seq"] = 1
    duplicate_seq["effect_calls"] = calls2
    with pytest.raises(OutcomeLearningContractError):
        validate_outcome(duplicate_seq, expectation, request)


def test_kill_10_restore_readback_mismatch_with_applied_and_restored_rejected():
    expectation, request, outcome = make_episode()
    bad = copy.deepcopy(dict(outcome))
    calls = [dict(c) for c in bad["effect_calls"]]
    calls[1] = dict(calls[1])
    calls[1]["readback"] = dict(calls[1]["readback"])
    calls[1]["readback"]["title_sha256"] = "0" * 64
    bad["effect_calls"] = calls
    with pytest.raises(OutcomeLearningContractError, match="call2 readback"):
        validate_outcome(bad, expectation, request)


def test_kill_12_self_model_promotion_score_and_sample_size_rejected():
    expectation, request, outcome = make_episode()
    evaluation = evaluate_episode(expectation, outcome, request, recorded_at=RECORDED_AT)
    self_model = build_self_model(evaluation, expectation, recorded_at=RECORDED_AT)

    bad_promotion = dict(self_model)
    bad_promotion["promotion"] = "GRANTED"
    with pytest.raises(OutcomeLearningContractError, match="promotion"):
        validate_self_model(bad_promotion, evaluation)

    bad_score = dict(self_model)
    bad_score["universal_score"] = 0.9
    with pytest.raises(OutcomeLearningContractError, match="universal_score"):
        validate_self_model(bad_score, evaluation)

    bad_sample = dict(self_model)
    bad_sample["sample_size"] = 2
    with pytest.raises(OutcomeLearningContractError, match="sample_size"):
        validate_self_model(bad_sample, evaluation)


# --------------------------------------------------------------------------- coverage
# (principal-review "previously-uncovered guards" pass, 2026-09-02) — each test
# constructs the bad document literally and pins the exact guard message, so a guard
# removal makes the test fail, never pass silently.


def _mutate_call(outcome, index, **readback_overrides):
    bad = copy.deepcopy(dict(outcome))
    calls = [dict(c) for c in bad["effect_calls"]]
    calls[index] = dict(calls[index])
    calls[index]["readback"] = {**calls[index]["readback"], **readback_overrides}
    bad["effect_calls"] = calls
    return bad


def test_coverage_preflight_head_sha_must_equal_sealed_commit_sha():
    expectation, request, outcome = make_episode()
    bad = copy.deepcopy(dict(outcome))
    bad_preflight = dict(bad["preflight"])
    # head_equals_sealed_commit still True but head_sha itself has drifted from
    # sealed_commit_sha — an internally inconsistent preflight the structural check
    # must catch independently of the boolean flag.
    bad_preflight["head_sha"] = "9" * 40
    bad["preflight"] = bad_preflight
    with pytest.raises(
        OutcomeLearningContractError, match="preflight.head_sha == sealed_commit_sha"
    ):
        validate_outcome(bad, expectation, request)


def test_coverage_poststate_must_equal_original_for_applied_and_restored():
    expectation, request, outcome = make_episode()
    bad = _mutate_call(outcome, 1, title_sha256="8" * 64)
    with pytest.raises(OutcomeLearningContractError, match="call2 readback"):
        validate_outcome(bad, expectation, request)


def test_coverage_prestate_must_equal_original_for_applied_and_restored():
    expectation, request, outcome = make_episode()
    bad = copy.deepcopy(dict(outcome))
    # poststate stays correct (== original) so the poststate-specific check passes;
    # prestate is wrong, and byte_identical is set to the value the general
    # byte_identical==(prestate==poststate) derivation actually requires (False, since
    # prestate != poststate here) — this isolates the APPLIED_AND_RESTORED-specific
    # "prestate must equal the ORIGINAL title" check from every earlier one.
    bad["restoration"] = {
        **bad["restoration"],
        "prestate_title_sha256": "7" * 64,
        "byte_identical": False,
    }
    with pytest.raises(
        OutcomeLearningContractError, match="prestate_title_sha256 must equal the original"
    ):
        validate_outcome(bad, expectation, request)


def test_coverage_every_readback_head_must_equal_sealed_commit_sha():
    expectation, request, outcome = make_episode()
    bad = _mutate_call(outcome, 0, head_sha="6" * 40)
    with pytest.raises(
        OutcomeLearningContractError, match="every head_sha to equal sealed_commit_sha"
    ):
        validate_outcome(bad, expectation, request)


def test_coverage_kind_ordering_must_be_apply_then_restore():
    expectation, request, outcome = make_episode()
    bad = copy.deepcopy(dict(outcome))
    calls = [dict(c) for c in bad["effect_calls"]]
    calls[0] = dict(calls[0])
    calls[0]["kind"] = "TITLE_RESTORE"  # wrong kind at position 0
    bad["effect_calls"] = calls
    with pytest.raises(OutcomeLearningContractError, match="kind must be TITLE_APPLY"):
        validate_outcome(bad, expectation, request)


def test_coverage_seq_must_equal_its_1_based_position():
    expectation, request, outcome = make_episode()
    bad = copy.deepcopy(dict(outcome))
    calls = [dict(c) for c in bad["effect_calls"]]
    calls[0] = dict(calls[0])
    calls[0]["seq"] = 2  # wrong seq at position 0 (should be 1)
    bad["effect_calls"] = calls
    with pytest.raises(
        OutcomeLearningContractError, match="seq must equal its 1-based position"
    ):
        validate_outcome(bad, expectation, request)


# --------------------------------------------------------------------------- BLOCKER 1 / MAJOR 4/10 coverage


def test_coverage_restoration_poststate_unobserved_permits_none_byte_identical():
    expectation, request, outcome = make_episode()
    bad = copy.deepcopy(dict(outcome))
    bad["effect_state"] = "EFFECT_UNKNOWN"
    bad["restoration"] = {
        "byte_identical": None,
        "prestate_title_sha256": bad["restoration"]["prestate_title_sha256"],
        "poststate_title_sha256": "UNOBSERVED",
        "head_unchanged": False,
    }
    # 2 calls present is still a legal EFFECT_UNKNOWN shape structurally.
    validate_outcome(bad, expectation, request)  # must not raise


def test_coverage_byte_identical_must_be_derived_not_free_when_observed():
    expectation, request, outcome = make_episode()
    bad = copy.deepcopy(dict(outcome))
    bad_restoration = dict(bad["restoration"])
    bad_restoration["byte_identical"] = False  # prestate == poststate here, so this is a lie
    bad["restoration"] = bad_restoration
    with pytest.raises(
        OutcomeLearningContractError, match="byte_identical must equal \\(prestate == poststate\\)"
    ):
        validate_outcome(bad, expectation, request)


def test_coverage_forecast_probability_kind_forbids_within_interval():
    expectation, request, outcome = make_episode()
    evaluation = evaluate_episode(expectation, outcome, request, recorded_at=RECORDED_AT)
    bad = dict(evaluation)
    forecast = [dict(f) for f in bad["forecast"]]
    forecast[0] = dict(forecast[0])
    forecast[0]["within_interval"] = True  # forbidden for probability-kind
    bad["forecast"] = forecast
    with pytest.raises(
        OutcomeLearningContractError, match="within_interval must be None for a"
    ):
        validate_evaluation(bad, expectation, outcome)


def test_coverage_forecast_brier_score_must_match_formula():
    expectation, request, outcome = make_episode()
    evaluation = evaluate_episode(expectation, outcome, request, recorded_at=RECORDED_AT)
    bad = dict(evaluation)
    forecast = [dict(f) for f in bad["forecast"]]
    forecast[0] = dict(forecast[0])
    forecast[0]["brier_score"] = 0.5  # wrong value
    bad["forecast"] = forecast
    with pytest.raises(
        OutcomeLearningContractError, match="brier_score must equal"
    ):
        validate_evaluation(bad, expectation, outcome)


def test_coverage_forecast_must_bind_verbatim_to_expectation_metric():
    expectation, request, outcome = make_episode()
    evaluation = evaluate_episode(expectation, outcome, request, recorded_at=RECORDED_AT)
    bad = dict(evaluation)
    forecast = [dict(f) for f in bad["forecast"]]
    forecast[0] = dict(forecast[0])
    # Still within [lower, upper] (so the bounds-consistency check alone can't catch
    # it) but no longer equal to the sealed expectation metric's own estimate —
    # isolates the verbatim-binding check from the ordering check.
    forecast[0]["estimate"] = 0.85
    bad["forecast"] = forecast
    with pytest.raises(
        OutcomeLearningContractError, match="does not match the sealed expectation"
    ):
        validate_evaluation(bad, expectation, outcome)
