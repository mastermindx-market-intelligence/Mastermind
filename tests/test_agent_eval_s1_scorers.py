"""EVAL-S1: deterministic task-class scorers (TC1/TC2/TC3).

Proves each scorer against the REAL, committed C0 corpus (gold facts,
invariants, candidate actions) with SYNTHETIC run receipts (this repository
has no real fresh runner yet -- design §3.2, and this package performs no
network/process/environment access per the R0 environment-free law, which
S1 inherits unchanged). See docs/superpowers/plans/2026-09-01-agent-
evaluation-s1-scorers.md for the scorer-vs-validity boundary and the
deterministic-vs-rubric-residue boundary each scorer implements.
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
    assert statuses["correctness"] == "PASS"
    assert statuses["rubric_residue"] == "UNKNOWN"
    residue_result = next(r for r in scorer_pass["dimension_results"] if r["dimension"] == "rubric_residue")
    assert residue_result["evidence_refs"] == [scenario["expected_contract"]]


@pytest.mark.parametrize("case", TC1_CASES)
def test_tc1_wrong_but_plausible_answer_scores_fail_not_unscored(case: str, synthetic_valid_run: dict) -> None:
    _scenario, _input_fixture, expected_contract = _load_corpus_case("current_source_comprehension", case)
    submission = {"answer": "This is a wrong-but-plausible-sounding answer that shares no gold fact clause."}

    results = tc1_source_comprehension.score_submission(expected_contract, submission)
    statuses = {r["dimension"]: r["status"] for r in results}
    assert statuses["correctness"] == "FAIL"
    assert statuses["correctness"] != "UNSCORED"  # UNSCORED is an evidence-ref-level rollup, never a dimension status


def test_tc1_partial_credit_when_only_one_of_two_gold_clauses_present() -> None:
    _scenario, _input_fixture, expected_contract = _load_corpus_case(
        "current_source_comprehension", "canonical_artifact_size_bound"
    )
    clauses = tc1_source_comprehension.gold_fact_clauses(expected_contract)
    assert len(clauses) == 2  # sanity: this real case has two semicolon-delimited fact clauses
    submission = {"answer": expected_contract["answer"].split(";")[0]}  # only the first clause

    results = tc1_source_comprehension.score_submission(expected_contract, submission)
    statuses = {r["dimension"]: r["status"] for r in results}
    assert statuses["correctness"] == "PARTIAL"


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
    assert statuses["literal_invariants"] == "PASS"
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
    assert statuses["literal_invariants"] == "FAIL"
    assert statuses["literal_invariants"] != "UNSCORED"


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
    assert statuses["literal_invariants"] == "PASS"


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
    literal_result = next(r for r in results if r["dimension"] == "literal_invariants")
    # PASS on the extractable literals, but the non-extractable "no key
    # removed" invariant is still NAMED, never silently assumed satisfied.
    assert literal_result["status"] == "PASS"
    assert "NON_DETERMINISTIC_INVARIANT_NOT_SCORED" in literal_result["reason_codes"]


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
