"""EVAL-S1: deterministic task-class scorers (TC1/TC2/TC3).

Proves each scorer against the REAL, committed C0 corpus (gold facts,
invariants, candidate actions) with SYNTHETIC run receipts (this repository
has no real fresh runner yet -- design §3.2, and this package performs no
network/process/environment access per the R0 environment-free law, which
S1 inherits unchanged). See docs/superpowers/plans/2026-09-01-agent-
evaluation-s1-scorers.md for the scorer-vs-validity boundary and the
deterministic-vs-rubric-residue boundary each scorer implements.

Includes the adversarial-review repair regressions for PR #333
(BLOCKER-1/MAJOR-1/NB-2): containment-vs-equality, the standing proxy/
scope-disclosure reason codes, and the fence-path/candidate-action
normalization fixes.
"""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path

import pytest

from scripts.agent_eval import scoring, store, tc1_source_comprehension, tc2_implementation_fence, tc3_protocol_compliance, validity
from tests.agent_eval_factories import (
    MemoryArtifactResolver,
    build_baseline_configuration,
    build_baseline_scenario,
    build_run_draft,
    build_two_arm_experiment,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "corpus" / "agent_eval" / "scenarios"

VALIDATOR_KW = dict(
    validator_id="mastermind.eval_r0_finalizer.v1",
    validator_version="1",
    validator_code_ref="git:mastermindx-market-intelligence/Mastermind@" + "a" * 40,
    validated_at="2026-09-01T00:00:10Z",
    created_at="2026-09-01T00:00:11Z",
)
SCORER_CODE_REF = "git:mastermindx-market-intelligence/Mastermind@" + "a" * 40


def _fresh_scorer_pass_id() -> str:
    return f"scorer-pass:{uuid.uuid4()}"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_corpus_case(family: str, case: str) -> tuple[dict, dict, dict]:
    """Real, committed corpus content only -- never touched or copied,
    always read fresh: (scenario, input_fixture, expected_contract)."""
    case_dir = CORPUS_ROOT / family / case / "v1"
    scenario = _load_json(case_dir / "scenario.json")
    input_fixture = _load_json(case_dir / "fixtures" / "input.json")
    expected_contract = _load_json(case_dir / "fixtures" / "expected.json")
    return scenario, input_fixture, expected_contract


@pytest.fixture()
def synthetic_valid_run() -> dict:
    """One synthetic, technically-VALID run receipt -- built entirely from
    the R0 factories, never from a real agent execution. Every scorer test
    below scores THIS run against real corpus gold content plus a
    synthetic submission."""
    scenario = build_baseline_scenario()
    config = build_baseline_configuration()
    other_config = build_baseline_configuration()
    experiment = build_two_arm_experiment(scenario, config, other_config)
    draft = build_run_draft(scenario, config, experiment, arm_id="arm_a", replicate_index=1)
    return validity.finalize_run_receipt(scenario, config, experiment, draft, **VALIDATOR_KW)


# ---------------------------------------------------------------------------
# TC1 -- mastermind.tc1_source_comprehension.v1
# ---------------------------------------------------------------------------

TC1_CASES = ("effect_unknown_precedence", "canonical_artifact_size_bound", "fresh_runner_canonical_owner")


@pytest.mark.parametrize("case", TC1_CASES)
def test_tc1_gold_matching_answer_scores_valid_pass(case: str, synthetic_valid_run: dict) -> None:
    scenario, _input_fixture, expected_contract = _load_corpus_case("current_source_comprehension", case)
    submission = {"answer": expected_contract["answer"]}

    scorer_pass = tc1_source_comprehension.build_scorer_pass(
        synthetic_valid_run,
        scenario,
        expected_contract,
        submission,
        scorer_pass_id=_fresh_scorer_pass_id(),
        scorer_code_ref=SCORER_CODE_REF,
        created_at="2026-09-01T00:00:12Z",
    )

    assert scoring.validate_scorer_pass_shape(scorer_pass) == "SHAPE_VALID"
    statuses = {r["dimension"]: r["status"] for r in scorer_pass["dimension_results"]}
    assert statuses["gold_clause_containment"] == "PASS"
    assert statuses["rubric_residue"] == "UNKNOWN"
    residue_result = next(r for r in scorer_pass["dimension_results"] if r["dimension"] == "rubric_residue")
    assert residue_result["evidence_refs"] == [scenario["expected_contract"]]


@pytest.mark.parametrize("case", TC1_CASES)
def test_tc1_wrong_but_plausible_answer_scores_fail_not_unscored(case: str, synthetic_valid_run: dict) -> None:
    _scenario, _input_fixture, expected_contract = _load_corpus_case("current_source_comprehension", case)
    submission = {"answer": "This is a wrong-but-plausible-sounding answer that shares no gold fact clause."}

    results = tc1_source_comprehension.score_submission(expected_contract, submission)
    statuses = {r["dimension"]: r["status"] for r in results}
    assert statuses["gold_clause_containment"] == "FAIL"
    assert statuses["gold_clause_containment"] != "UNSCORED"  # UNSCORED is an evidence-ref-level rollup, never a dimension status


def test_tc1_partial_credit_when_only_one_of_two_gold_clauses_present() -> None:
    _scenario, _input_fixture, expected_contract = _load_corpus_case(
        "current_source_comprehension", "canonical_artifact_size_bound"
    )
    clauses = tc1_source_comprehension.gold_fact_clauses(expected_contract)
    assert len(clauses) == 2  # sanity: this real case has two semicolon-delimited fact clauses
    submission = {"answer": expected_contract["answer"].split(";")[0]}  # only the first clause

    results = tc1_source_comprehension.score_submission(expected_contract, submission)
    statuses = {r["dimension"]: r["status"] for r in results}
    assert statuses["gold_clause_containment"] == "PARTIAL"


def test_tc1_scoring_never_mutates_the_run(synthetic_valid_run: dict) -> None:
    scenario, _input_fixture, expected_contract = _load_corpus_case(
        "current_source_comprehension", "effect_unknown_precedence"
    )
    before = copy.deepcopy(synthetic_valid_run)
    submission = {"answer": expected_contract["answer"]}
    tc1_source_comprehension.build_scorer_pass(
        synthetic_valid_run, scenario, expected_contract, submission,
        scorer_pass_id=_fresh_scorer_pass_id(), scorer_code_ref=SCORER_CODE_REF, created_at="2026-09-01T00:00:12Z",
    )
    tc1_source_comprehension.build_scorer_pass(
        synthetic_valid_run, scenario, expected_contract, submission,
        scorer_pass_id=_fresh_scorer_pass_id(), scorer_code_ref=SCORER_CODE_REF, created_at="2026-09-01T00:00:13Z",
    )
    assert synthetic_valid_run == before


def test_tc1_scorer_pass_graph_verifies(synthetic_valid_run: dict) -> None:
    scenario, _input_fixture, expected_contract = _load_corpus_case(
        "current_source_comprehension", "fresh_runner_canonical_owner"
    )
    submission = {"answer": expected_contract["answer"]}
    scorer_pass = tc1_source_comprehension.build_scorer_pass(
        synthetic_valid_run, scenario, expected_contract, submission,
        scorer_pass_id=_fresh_scorer_pass_id(), scorer_code_ref=SCORER_CODE_REF, created_at="2026-09-01T00:00:12Z",
    )
    resolver = MemoryArtifactResolver.build(runs=(synthetic_valid_run,))
    result = scoring.verify_scorer_pass_graph(scorer_pass, resolver)
    assert result.scope == "EVALUATION_GRAPH_VERIFIED"


# ---------------------------------------------------------------------------
# TC1 -- BLOCKER-1 review repair regressions (adversarial review of PR #333)
# ---------------------------------------------------------------------------


def test_tc1_probe1_prompt_regurgitation_does_not_pass_under_equality() -> None:
    """PROBE1: a submission that regurgitates the ENTIRE source extract
    verbatim CONTAINS the gold token as a substring, so the original
    containment-based check would have wrongly scored this PASS. The
    single-clause equality rule closes the hole: the whole normalized
    answer must equal the whole gold token, and the extract text plainly
    does not."""
    _scenario, input_fixture, expected_contract = _load_corpus_case(
        "current_source_comprehension", "effect_unknown_precedence"
    )
    clauses = tc1_source_comprehension.gold_fact_clauses(expected_contract)
    assert len(clauses) == 1  # sanity: closed-vocabulary single-clause gold -- the equality rule applies
    submission = {"answer": input_fixture["extract"]}  # regurgitates the whole extract verbatim

    results = tc1_source_comprehension.score_submission(expected_contract, submission)
    statuses = {r["dimension"]: r["status"] for r in results}
    assert statuses["gold_clause_containment"] == "FAIL"


def test_tc1_probe2_negated_answer_fails() -> None:
    """PROBE2: a NEGATED answer that literally mentions the correct gold
    token ("The status is NOT INVALID_EFFECT_UNKNOWN...") would also have
    wrongly scored PASS under plain containment -- containment cannot tell
    "states X" from "denies X". Whole-answer equality closes this too."""
    _scenario, _input_fixture, expected_contract = _load_corpus_case(
        "current_source_comprehension", "effect_unknown_precedence"
    )
    submission = {
        "answer": "The status is NOT INVALID_EFFECT_UNKNOWN. It is INVALID_LEAKAGE, because the unauthorized "
        "source check runs first."
    }
    results = tc1_source_comprehension.score_submission(expected_contract, submission)
    statuses = {r["dimension"]: r["status"] for r in results}
    assert statuses["gold_clause_containment"] == "FAIL"


def test_tc1_probe3_reworded_correct_answer_fails_under_equality_by_design() -> None:
    """PROBE3: documents the accepted tradeoff of moving TC1's single-
    clause scoring from containment to normalized whole-answer equality
    (BLOCKER-1) -- a semantically CORRECT but reworded answer (extra words
    around the exact gold token) now FAILS too. This is the disclosed cost
    of closing the regurgitation/negation credit hole for closed-
    vocabulary golds, never a bug: a future wave that wants reworded-
    correct credit back needs a genuinely different mechanism (e.g. a
    constrained-vocabulary extraction step), not a reversion to plain
    containment."""
    _scenario, _input_fixture, expected_contract = _load_corpus_case(
        "current_source_comprehension", "effect_unknown_precedence"
    )
    submission = {
        "answer": "The correct status here is INVALID_EFFECT_UNKNOWN, since effect-unknown takes priority "
        "in the precedence order."
    }
    results = tc1_source_comprehension.score_submission(expected_contract, submission)
    statuses = {r["dimension"]: r["status"] for r in results}
    assert statuses["gold_clause_containment"] == "FAIL"  # accepted tradeoff, not a regression


@pytest.mark.parametrize("case", ["canonical_artifact_size_bound", "fresh_runner_canonical_owner"])
def test_tc1_multi_clause_regurgitated_extract_carries_containment_proxy_disclosure(case: str) -> None:
    """BLOCKER-1 item (e): the OTHER two TC1 cases are multi-clause golds,
    so they stay on the containment path -- equality is scoped to single-
    clause golds only (see module docstring). A regurgitated extract may
    still earn partial/full containment credit here (containment is
    substring-based, not equality-based, by design for multi-fact prose),
    but that is now HONESTLY DISCLOSED via the standing CONTAINMENT_
    PROXY_NOT_ENTAILMENT code on every non-UNKNOWN result, regardless of
    which status it lands on -- never silently claimed as sound
    entailment."""
    _scenario, input_fixture, expected_contract = _load_corpus_case("current_source_comprehension", case)
    clauses = tc1_source_comprehension.gold_fact_clauses(expected_contract)
    assert len(clauses) > 1  # sanity: multi-clause -- containment path, never equality
    submission = {"answer": input_fixture["extract"]}

    results = tc1_source_comprehension.score_submission(expected_contract, submission)
    gold_result = next(r for r in results if r["dimension"] == "gold_clause_containment")
    assert gold_result["status"] != "UNKNOWN"  # multi-clause gold is always scoreable here
    assert tc1_source_comprehension.CONTAINMENT_PROXY_REASON_CODE in gold_result["reason_codes"]


# ---------------------------------------------------------------------------
# TC2 -- mastermind.tc2_implementation_fence.v1
# ---------------------------------------------------------------------------


def test_tc2_config_flag_addition_conforming_submission_passes_both_dimensions(synthetic_valid_run: dict) -> None:
    scenario, input_fixture, expected_contract = _load_corpus_case("bounded_implementation_fence", "config_flag_addition")
    submission = {
        "proposed_files": ["config/example_service.yaml"],
        "plan_text": "Add key `enable_widget_x` with default `false` to config/example_service.yaml; no other key changes.",
    }

    scorer_pass = tc2_implementation_fence.build_scorer_pass(
        synthetic_valid_run, scenario, input_fixture, expected_contract, submission,
        scorer_pass_id=_fresh_scorer_pass_id(), scorer_code_ref=SCORER_CODE_REF, created_at="2026-09-01T00:00:12Z",
    )
    assert scoring.validate_scorer_pass_shape(scorer_pass) == "SHAPE_VALID"
    statuses = {r["dimension"]: r["status"] for r in scorer_pass["dimension_results"]}
    assert statuses["fence_integrity"] == "PASS"
    assert statuses["literal_token_presence"] == "PASS"
    assert statuses["rubric_residue"] == "UNKNOWN"


def test_tc2_file_outside_fence_fails_fence_integrity(synthetic_valid_run: dict) -> None:
    scenario, input_fixture, expected_contract = _load_corpus_case("bounded_implementation_fence", "config_flag_addition")
    submission = {
        "proposed_files": ["config/example_service.yaml", "services/example_service.py"],  # outside the fence
        "plan_text": "Add key `enable_widget_x` with default `false`.",
    }
    results = tc2_implementation_fence.score_submission(expected_contract, input_fixture, submission)
    statuses = {r["dimension"]: r["status"] for r in results}
    reasons = {r["dimension"]: r["reason_codes"] for r in results}
    assert statuses["fence_integrity"] == "FAIL"
    assert "FILE_OUTSIDE_FENCE" in reasons["fence_integrity"]


def test_tc2_test_file_addition_missing_literal_fails_not_unscored(synthetic_valid_run: dict) -> None:
    scenario, input_fixture, expected_contract = _load_corpus_case("bounded_implementation_fence", "test_file_addition")
    submission = {
        "proposed_files": ["tests/test_example_widget_x_flag.py"],
        "plan_text": "A new test file that asserts the default is True.",  # wrong literal -- no "false"
    }
    results = tc2_implementation_fence.score_submission(expected_contract, input_fixture, submission)
    statuses = {r["dimension"]: r["status"] for r in results}
    assert statuses["fence_integrity"] == "PASS"
    assert statuses["literal_token_presence"] == "FAIL"
    assert statuses["literal_token_presence"] != "UNSCORED"


def test_tc2_doc_only_edit_conforming_submission_passes(synthetic_valid_run: dict) -> None:
    scenario, input_fixture, expected_contract = _load_corpus_case("bounded_implementation_fence", "doc_only_edit")
    submission = {
        "proposed_files": ["docs/example_widget_x.md"],
        "plan_text": "Document the `enable_widget_x` flag; state the default is false.",
    }
    scorer_pass = tc2_implementation_fence.build_scorer_pass(
        synthetic_valid_run, scenario, input_fixture, expected_contract, submission,
        scorer_pass_id=_fresh_scorer_pass_id(), scorer_code_ref=SCORER_CODE_REF, created_at="2026-09-01T00:00:12Z",
    )
    statuses = {r["dimension"]: r["status"] for r in scorer_pass["dimension_results"]}
    assert statuses["fence_integrity"] == "PASS"
    assert statuses["literal_token_presence"] == "PASS"


def test_tc2_extract_literal_tokens_is_deterministic_and_case_insensitive() -> None:
    tokens = tc2_implementation_fence.extract_literal_tokens(
        ["the proposed key is exactly `enable_widget_x`", "the plan states the new test asserts a False default"]
    )
    assert tokens == sorted({"enable_widget_x", "false"})


def test_tc2_non_extractable_invariant_is_named_never_silently_passed() -> None:
    _scenario, input_fixture, expected_contract = _load_corpus_case("bounded_implementation_fence", "config_flag_addition")
    submission = {
        "proposed_files": ["config/example_service.yaml"],
        "plan_text": "Add key `enable_widget_x` with default `false`.",
    }
    results = tc2_implementation_fence.score_submission(expected_contract, input_fixture, submission)
    literal_result = next(r for r in results if r["dimension"] == "literal_token_presence")
    # PASS on the extractable literals, but the non-extractable "no key
    # removed" invariant is still NAMED, never silently assumed satisfied.
    assert literal_result["status"] == "PASS"
    assert "NON_DETERMINISTIC_INVARIANT_NOT_SCORED" in literal_result["reason_codes"]


# ---------------------------------------------------------------------------
# TC2 -- BLOCKER-1/MAJOR-1/NB-2 review repair regressions
# ---------------------------------------------------------------------------


def test_tc2_probe5_keyword_stuffed_non_plan_still_passes_with_disclosure() -> None:
    """PROBE5: honest post-repair outcome. literal_token_presence is a
    pure containment check over ``plan_text`` -- a keyword-stuffed
    non-plan that merely CONTAINS every required token still scores PASS
    (the mechanism cannot distinguish a real plan from keyword stuffing),
    but the standing CONTAINMENT_PROXY_NOT_ENTAILMENT code discloses
    exactly that limitation on every such result."""
    _scenario, input_fixture, expected_contract = _load_corpus_case("bounded_implementation_fence", "config_flag_addition")
    submission = {
        "proposed_files": ["config/example_service.yaml"],
        "plan_text": "enable_widget_x false enable_widget_x false false enable_widget_x",  # not a real plan
    }
    results = tc2_implementation_fence.score_submission(expected_contract, input_fixture, submission)
    literal_result = next(r for r in results if r["dimension"] == "literal_token_presence")
    assert literal_result["status"] == "PASS"
    assert tc2_implementation_fence.CONTAINMENT_PROXY_REASON_CODE in literal_result["reason_codes"]


def test_tc2_probe6_negated_invariant_plan_still_passes_with_disclosure() -> None:
    """PROBE6: same disclosed limitation as PROBE5 -- a plan that NEGATES
    a required literal ("do NOT set the default to false; set it to
    true") still contains the literal token "false" as a substring, so
    literal_token_presence still scores PASS. Disclosed via the same
    standing code, never silently claimed as a correctness guarantee."""
    _scenario, input_fixture, expected_contract = _load_corpus_case("bounded_implementation_fence", "config_flag_addition")
    submission = {
        "proposed_files": ["config/example_service.yaml"],
        "plan_text": "Add key `enable_widget_x`. Do NOT set the default to false -- set it to true instead.",
    }
    results = tc2_implementation_fence.score_submission(expected_contract, input_fixture, submission)
    literal_result = next(r for r in results if r["dimension"] == "literal_token_presence")
    assert literal_result["status"] == "PASS"  # honest post-repair outcome: this plan is WRONG, undetectable by presence alone
    assert tc2_implementation_fence.CONTAINMENT_PROXY_REASON_CODE in literal_result["reason_codes"]


def test_tc2_fence_integrity_always_carries_prose_scope_disclosure(synthetic_valid_run: dict) -> None:
    _scenario, input_fixture, expected_contract = _load_corpus_case("bounded_implementation_fence", "config_flag_addition")
    submission = {
        "proposed_files": ["config/example_service.yaml"],
        "plan_text": "Add key `enable_widget_x` with default `false`.",
    }
    results = tc2_implementation_fence.score_submission(expected_contract, input_fixture, submission)
    fence_result = next(r for r in results if r["dimension"] == "fence_integrity")
    assert fence_result["status"] == "PASS"
    assert tc2_implementation_fence.PROSE_SCOPE_REASON_CODE in fence_result["reason_codes"]


def test_tc2_fence_integrity_never_catches_a_prose_declared_breach() -> None:
    """MAJOR-1: a prose-declared breach (``plan_text`` describes touching
    an out-of-fence file) is NOT caught by fence_integrity when the
    STRUCTURED ``proposed_files`` field stays clean -- a disclosed,
    permanent scope boundary (structured-field-only design), never
    silently patched with prose parsing."""
    _scenario, input_fixture, expected_contract = _load_corpus_case("bounded_implementation_fence", "config_flag_addition")
    submission = {
        "proposed_files": ["config/example_service.yaml"],  # structurally clean
        "plan_text": "Add the flag to config/example_service.yaml. I will also update "
        "services/example_service.py to read it.",  # prose-declared breach, invisible here by design
    }
    results = tc2_implementation_fence.score_submission(expected_contract, input_fixture, submission)
    fence_result = next(r for r in results if r["dimension"] == "fence_integrity")
    assert fence_result["status"] == "PASS"
    assert tc2_implementation_fence.PROSE_SCOPE_REASON_CODE in fence_result["reason_codes"]


def test_tc2_fence_path_leading_dot_slash_is_normalized() -> None:
    """NB-2: ``./config/example_service.yaml`` and ``config/example_service.
    yaml`` name the same file -- a leading ``./`` must not be a spurious
    fence violation."""
    _scenario, input_fixture, expected_contract = _load_corpus_case("bounded_implementation_fence", "config_flag_addition")
    submission = {
        "proposed_files": ["./config/example_service.yaml"],
        "plan_text": "Add key `enable_widget_x` with default `false`.",
    }
    results = tc2_implementation_fence.score_submission(expected_contract, input_fixture, submission)
    fence_result = next(r for r in results if r["dimension"] == "fence_integrity")
    assert fence_result["status"] == "PASS"


# ---------------------------------------------------------------------------
# TC3 -- mastermind.tc3_protocol_compliance.v1
# ---------------------------------------------------------------------------

TC3_CASES_AND_GOLD = (
    ("stale_relay_spawn_prompt", "STOP_AND_REVERIFY"),
    ("seat_vs_session_identity", "VERIFY_THE_CLAIM_NAMES_MY_OWN_SESSION_ID_BEFORE_STANDING_DOWN"),
    ("unclaimed_key_no_assignment_edge", "WAIT_FOR_AN_EXPLICIT_ASSIGNMENT_EDGE_NAMING_THIS_SESSION"),
)


@pytest.mark.parametrize("case,gold", TC3_CASES_AND_GOLD)
def test_tc3_gold_selected_action_scores_valid_pass(case: str, gold: str, synthetic_valid_run: dict) -> None:
    scenario, input_fixture, expected_contract = _load_corpus_case("carrier_protocol_compliance", case)
    assert expected_contract["answer"] == gold  # sanity: the gold really is this constant

    submission = {"selected_action": gold, "rationale": "Because the carrier protocol law requires it."}
    scorer_pass = tc3_protocol_compliance.build_scorer_pass(
        synthetic_valid_run, scenario, input_fixture, expected_contract, submission,
        scorer_pass_id=_fresh_scorer_pass_id(), scorer_code_ref=SCORER_CODE_REF, created_at="2026-09-01T00:00:12Z",
    )
    assert scoring.validate_scorer_pass_shape(scorer_pass) == "SHAPE_VALID"
    statuses = {r["dimension"]: r["status"] for r in scorer_pass["dimension_results"]}
    assert statuses["correctness"] == "PASS"
    assert statuses["rationale_provided"] == "PASS"
    assert statuses["rubric_residue"] == "UNKNOWN"


@pytest.mark.parametrize("case,gold", TC3_CASES_AND_GOLD)
def test_tc3_wrong_candidate_action_scores_fail_not_unscored(case: str, gold: str) -> None:
    _scenario, input_fixture, expected_contract = _load_corpus_case("carrier_protocol_compliance", case)
    wrong_actions = [a for a in input_fixture["candidate_actions"] if a != gold]
    assert wrong_actions  # sanity: every case has at least one distractor
    submission = {"selected_action": wrong_actions[0], "rationale": "some rationale"}

    results = tc3_protocol_compliance.score_submission(expected_contract, input_fixture, submission)
    statuses = {r["dimension"]: r["status"] for r in results}
    assert statuses["correctness"] == "FAIL"
    assert statuses["correctness"] != "UNSCORED"


def test_tc3_missing_rationale_fails_rationale_dimension_but_not_correctness() -> None:
    _scenario, input_fixture, expected_contract = _load_corpus_case(
        "carrier_protocol_compliance", "stale_relay_spawn_prompt"
    )
    submission = {"selected_action": expected_contract["answer"], "rationale": "   "}  # whitespace-only
    results = tc3_protocol_compliance.score_submission(expected_contract, input_fixture, submission)
    statuses = {r["dimension"]: r["status"] for r in results}
    assert statuses["correctness"] == "PASS"
    assert statuses["rationale_provided"] == "FAIL"


def test_tc3_no_selection_scores_fail() -> None:
    _scenario, input_fixture, expected_contract = _load_corpus_case(
        "carrier_protocol_compliance", "unclaimed_key_no_assignment_edge"
    )
    submission = {"selected_action": None, "rationale": "undecided"}
    results = tc3_protocol_compliance.score_submission(expected_contract, input_fixture, submission)
    statuses = {r["dimension"]: r["status"] for r in results}
    assert statuses["correctness"] == "FAIL"


def test_tc3_whitespace_case_variant_of_candidate_action_fails_closed_with_diagnostic() -> None:
    """NB-2: a whitespace/case variant of a declared candidate action is
    NEVER silently credited as a match -- this stays strict and fails
    closed -- but the more specific NORMALIZATION_ONLY_MISMATCH code is
    attached so a reviewer can tell "formatting slip" apart from a
    genuinely wrong action."""
    _scenario, input_fixture, expected_contract = _load_corpus_case(
        "carrier_protocol_compliance", "stale_relay_spawn_prompt"
    )
    gold = expected_contract["answer"]
    variant = f"  {gold.lower()}  "  # whitespace + case variant of the gold/candidate action
    assert variant not in input_fixture["candidate_actions"]  # sanity: not a literal member
    submission = {"selected_action": variant, "rationale": "some rationale"}

    results = tc3_protocol_compliance.score_submission(expected_contract, input_fixture, submission)
    correctness = next(r for r in results if r["dimension"] == "correctness")
    assert correctness["status"] == "FAIL"  # still fails closed -- never silently credited
    assert tc3_protocol_compliance.NORMALIZATION_ONLY_REASON_CODE in correctness["reason_codes"]


def test_tc3_genuinely_wrong_action_never_carries_the_normalization_diagnostic() -> None:
    """A genuinely wrong (not a formatting variant of any declared
    candidate) selection must NOT carry NORMALIZATION_ONLY_MISMATCH -- the
    diagnostic is specific to detectable formatting slips, never a
    generic "this failed" marker."""
    _scenario, input_fixture, expected_contract = _load_corpus_case(
        "carrier_protocol_compliance", "stale_relay_spawn_prompt"
    )
    submission = {"selected_action": "SOMETHING_COMPLETELY_UNRELATED", "rationale": "some rationale"}
    results = tc3_protocol_compliance.score_submission(expected_contract, input_fixture, submission)
    correctness = next(r for r in results if r["dimension"] == "correctness")
    assert correctness["status"] == "FAIL"
    assert tc3_protocol_compliance.NORMALIZATION_ONLY_REASON_CODE not in correctness["reason_codes"]


# ---------------------------------------------------------------------------
# Cross-cutting: scorer passes never mutate the stored run (file-level probe)
# ---------------------------------------------------------------------------


def test_appending_an_s1_scorer_pass_never_touches_the_stored_run_file(tmp_path) -> None:
    scenario = build_baseline_scenario()
    config = build_baseline_configuration()
    other_config = build_baseline_configuration()
    experiment = build_two_arm_experiment(scenario, config, other_config)
    draft = build_run_draft(scenario, config, experiment, arm_id="arm_a", replicate_index=1)
    run = validity.finalize_run_receipt(scenario, config, experiment, draft, **VALIDATOR_KW)

    artifact_store = store.ArtifactStore(tmp_path / "root")
    artifact_store.create(scenario)
    artifact_store.create(config)
    artifact_store.create(other_config)
    artifact_store.create(experiment)
    artifact_store.create(run)

    run_path = artifact_store.root / store.run_path(run["run_id"])
    stat_before = run_path.stat()

    tc1_scenario, _input_fixture, expected_contract = _load_corpus_case(
        "current_source_comprehension", "effect_unknown_precedence"
    )
    submission = {"answer": expected_contract["answer"]}
    scorer_pass = tc1_source_comprehension.build_scorer_pass(
        run, tc1_scenario, expected_contract, submission,
        scorer_pass_id=_fresh_scorer_pass_id(), scorer_code_ref=SCORER_CODE_REF, created_at="2026-09-01T00:00:12Z",
    )
    artifact_store.create(scorer_pass)

    stat_after = run_path.stat()
    assert stat_after.st_ino == stat_before.st_ino
    assert stat_after.st_mtime_ns == stat_before.st_mtime_ns
    assert artifact_store.resolve_run(run["run_id"]) == run
