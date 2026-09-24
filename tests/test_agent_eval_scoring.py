"""EVAL-R0 Task 5: append-only scorer and evidence reference."""
from __future__ import annotations

import copy
import uuid

import pytest

from scripts.agent_eval import contracts, scoring, validity
from scripts.agent_eval.canonical import add_document_digest
from scripts.agent_eval.errors import ContractError, VerificationContextError
from tests.agent_eval_factories import (
    MemoryArtifactResolver,
    build_alternate_configuration,
    build_baseline_configuration,
    build_baseline_scenario,
    build_run_draft,
    build_two_arm_experiment,
    fresh_run_id,
)

VALIDATOR_KW = dict(
    validator_id="mastermind.eval_r0_finalizer.v1",
    validator_version="1",
    validator_code_ref="git:mastermindx-market-intelligence/Mastermind@" + "a" * 40,
    validated_at="2026-08-25T00:00:10Z",
    created_at="2026-08-25T00:00:11Z",
)
SCORER_CODE_REF = "git:mastermindx-market-intelligence/Mastermind@" + "a" * 40


def _fresh_scorer_pass_id() -> str:
    return f"scorer-pass:{uuid.uuid4()}"


def _fresh_evidence_ref_id() -> str:
    return f"evidence-ref:{uuid.uuid4()}"


def _graph_with_two_runs():
    scenario = build_baseline_scenario()
    config_a = build_baseline_configuration()
    config_b = build_alternate_configuration()
    experiment = build_two_arm_experiment(scenario, config_a, config_b)

    draft_valid = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    run_valid = validity.finalize_run_receipt(scenario, config_a, experiment, draft_valid, **VALIDATOR_KW)

    draft_invalid = build_run_draft(
        scenario, config_a, experiment, arm_id="arm_a", replicate_index=1, model_served="claude-opus-9", run_id=fresh_run_id()
    )
    run_invalid = validity.finalize_run_receipt(scenario, config_a, experiment, draft_invalid, **VALIDATOR_KW)

    return scenario, config_a, config_b, experiment, run_valid, run_invalid


def _score(run: dict, **overrides) -> dict:
    kwargs = dict(scorer_pass_id=_fresh_scorer_pass_id(), scorer_code_ref=SCORER_CODE_REF, created_at="2026-08-25T00:00:12Z")
    kwargs.update(overrides)
    return scoring.build_technical_integrity_scorer_pass(run, **kwargs)


# ---------------------------------------------------------------------------
# Scorer pass shape
# ---------------------------------------------------------------------------


def test_technical_integrity_scorer_pass_is_shape_valid() -> None:
    *_rest, run_valid, _run_invalid = _graph_with_two_runs()
    scorer_pass = _score(run_valid)
    assert scoring.validate_scorer_pass_shape(scorer_pass) == "SHAPE_VALID"


def test_scorer_pass_binds_exact_run_id_and_digest() -> None:
    *_rest, run_valid, _run_invalid = _graph_with_two_runs()
    scorer_pass = _score(run_valid)
    assert scorer_pass["run_id"] == run_valid["run_id"]
    assert scorer_pass["run_digest"] == run_valid["run_digest"]


def test_scorer_pass_dimension_results_are_sorted() -> None:
    *_rest, run_valid, _run_invalid = _graph_with_two_runs()
    scorer_pass = _score(run_valid)
    dims = [d["dimension"] for d in scorer_pass["dimension_results"]]
    assert dims == sorted(dims)
    assert dims == list(scoring.DIMENSIONS[:]) or sorted(dims) == dims  # sanity


def test_scorer_pass_rejects_duplicate_dimension() -> None:
    *_rest, run_valid, _run_invalid = _graph_with_two_runs()
    scorer_pass = _score(run_valid)
    tampered = copy.deepcopy(scorer_pass)
    tampered["dimension_results"].append(dict(tampered["dimension_results"][0]))
    tampered["dimension_results"].sort(key=lambda item: item["dimension"])
    tampered = add_document_digest(
        {k: v for k, v in tampered.items() if k != "scorer_pass_digest"}, "scorer_pass_digest"
    )
    with pytest.raises(ContractError) as excinfo:
        scoring.validate_scorer_pass_shape(tampered)
    assert any(d.code == "LIST_HAS_DUPLICATES" for d in excinfo.value.defects)


def test_deterministic_method_forbids_grader_identity() -> None:
    *_rest, run_valid, _run_invalid = _graph_with_two_runs()
    scorer_pass = _score(run_valid)
    tampered = dict(scorer_pass)
    tampered["grader_identity"] = "person:auditor"
    tampered = add_document_digest({k: v for k, v in tampered.items() if k != "scorer_pass_digest"}, "scorer_pass_digest")
    with pytest.raises(ContractError) as excinfo:
        scoring.validate_scorer_pass_shape(tampered)
    assert any(d.code == "GRADER_IDENTITY_NOT_ALLOWED" for d in excinfo.value.defects)


def test_human_method_requires_grader_identity() -> None:
    *_rest, run_valid, _run_invalid = _graph_with_two_runs()
    scorer_pass = _score(run_valid)
    tampered = dict(scorer_pass)
    tampered["method"] = "HUMAN"
    tampered = add_document_digest({k: v for k, v in tampered.items() if k != "scorer_pass_digest"}, "scorer_pass_digest")
    with pytest.raises(ContractError) as excinfo:
        scoring.validate_scorer_pass_shape(tampered)
    assert any(d.code == "GRADER_IDENTITY_REQUIRED" for d in excinfo.value.defects)


def test_scorer_pass_must_not_supersede_itself() -> None:
    *_rest, run_valid, _run_invalid = _graph_with_two_runs()
    scorer_pass = _score(run_valid)
    tampered = dict(scorer_pass)
    tampered["supersedes"] = tampered["scorer_pass_id"]
    tampered = add_document_digest({k: v for k, v in tampered.items() if k != "scorer_pass_digest"}, "scorer_pass_digest")
    with pytest.raises(ContractError) as excinfo:
        scoring.validate_scorer_pass_shape(tampered)
    assert any(d.code == "SUPERSEDES_SELF" for d in excinfo.value.defects)


def test_scorer_pass_rejects_unknown_field() -> None:
    *_rest, run_valid, _run_invalid = _graph_with_two_runs()
    scorer_pass = _score(run_valid)
    tampered = dict(scorer_pass)
    tampered["aggregate_score"] = 0.9
    with pytest.raises(ContractError) as excinfo:
        scoring.validate_scorer_pass_shape(tampered)
    assert any(d.code == "UNKNOWN_FIELD" for d in excinfo.value.defects)


# ---------------------------------------------------------------------------
# build_technical_integrity_scorer_pass uses validity/reasons only
# ---------------------------------------------------------------------------


def test_clean_valid_run_scores_all_dimensions_pass() -> None:
    *_rest, run_valid, _run_invalid = _graph_with_two_runs()
    scorer_pass = _score(run_valid)
    statuses = {d["dimension"]: d["status"] for d in scorer_pass["dimension_results"]}
    assert set(statuses.values()) == {"PASS"}


def test_model_served_mismatch_fails_configuration_integrity_only() -> None:
    *_rest, run_valid, run_invalid = _graph_with_two_runs()
    scorer_pass = _score(run_invalid)
    statuses = {d["dimension"]: d["status"] for d in scorer_pass["dimension_results"]}
    assert statuses["configuration_integrity"] == "FAIL"
    assert statuses["effect_integrity"] == "PASS"
    assert statuses["cleanup_integrity"] == "PASS"
    assert statuses["source_integrity"] == "PASS"
    config_dim = next(d for d in scorer_pass["dimension_results"] if d["dimension"] == "configuration_integrity")
    assert "MODEL_SERVED_MISMATCH" in config_dim["reason_codes"]


def test_source_leakage_fails_source_integrity_only() -> None:
    scenario, config_a, config_b, experiment, run_valid, _run_invalid = _graph_with_two_runs()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1, run_id=fresh_run_id())
    draft["observations"]["observed_sources"][0]["digest"] = "sha256:" + "9" * 64
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    scorer_pass = _score(run)
    statuses = {d["dimension"]: d["status"] for d in scorer_pass["dimension_results"]}
    assert statuses["source_integrity"] == "FAIL"
    assert statuses["configuration_integrity"] == "PASS"


def test_scorer_never_claims_broad_task_correctness_or_usefulness() -> None:
    *_rest, run_valid, _run_invalid = _graph_with_two_runs()
    scorer_pass = _score(run_valid)
    dimensions = {d["dimension"] for d in scorer_pass["dimension_results"]}
    assert dimensions == {"cleanup_integrity", "configuration_integrity", "effect_integrity", "source_integrity"}
    assert "task_correctness" not in dimensions
    assert "product_usefulness" not in dimensions


# ---------------------------------------------------------------------------
# Append-only: scoring never mutates the run
# ---------------------------------------------------------------------------


def test_scoring_a_run_does_not_mutate_the_run_document() -> None:
    *_rest, run_valid, _run_invalid = _graph_with_two_runs()
    before = copy.deepcopy(run_valid)
    _score(run_valid)
    _score(run_valid)  # score twice
    assert run_valid == before


def test_supersession_appends_a_new_record_never_rewrites() -> None:
    *_rest, run_valid, _run_invalid = _graph_with_two_runs()
    first = _score(run_valid)
    second = _score(run_valid, supersedes=first["scorer_pass_id"], scorer_pass_id=_fresh_scorer_pass_id())
    assert second["supersedes"] == first["scorer_pass_id"]
    assert first["scorer_pass_id"] != second["scorer_pass_id"]
    # both records remain independently shape-valid and distinct
    assert scoring.validate_scorer_pass_shape(first) == "SHAPE_VALID"
    assert scoring.validate_scorer_pass_shape(second) == "SHAPE_VALID"


# ---------------------------------------------------------------------------
# verify_scorer_pass_graph
# ---------------------------------------------------------------------------


def test_verify_scorer_pass_graph_succeeds_for_a_consistent_pass() -> None:
    scenario, config_a, config_b, experiment, run_valid, _run_invalid = _graph_with_two_runs()
    scorer_pass = _score(run_valid)
    resolver = MemoryArtifactResolver.build(runs=(run_valid,))
    result = scoring.verify_scorer_pass_graph(scorer_pass, resolver)
    assert result.scope == "EVALUATION_GRAPH_VERIFIED"


def test_verify_scorer_pass_graph_fails_when_run_missing() -> None:
    *_rest, run_valid, _run_invalid = _graph_with_two_runs()
    scorer_pass = _score(run_valid)
    resolver = MemoryArtifactResolver.build()
    with pytest.raises(VerificationContextError) as excinfo:
        scoring.verify_scorer_pass_graph(scorer_pass, resolver)
    assert any(d.code == "RUN_NOT_RESOLVED" for d in excinfo.value.defects)


def test_verify_scorer_pass_graph_fails_on_forged_dimension_result() -> None:
    *_rest, run_valid, run_invalid = _graph_with_two_runs()
    scorer_pass = _score(run_invalid)  # real: configuration_integrity FAIL
    forged = copy.deepcopy(scorer_pass)
    for dim in forged["dimension_results"]:
        if dim["dimension"] == "configuration_integrity":
            dim["status"] = "PASS"
            dim["reason_codes"] = []
    forged = add_document_digest({k: v for k, v in forged.items() if k != "scorer_pass_digest"}, "scorer_pass_digest")
    resolver = MemoryArtifactResolver.build(runs=(run_invalid,))
    with pytest.raises(VerificationContextError) as excinfo:
        scoring.verify_scorer_pass_graph(forged, resolver)
    assert any(d.code == "SCORER_RESULT_NOT_RECOMPUTABLE" for d in excinfo.value.defects)


def test_verify_scorer_pass_graph_fails_on_run_digest_mismatch() -> None:
    *_rest, run_valid, _run_invalid = _graph_with_two_runs()
    scorer_pass = _score(run_valid)
    tampered = dict(scorer_pass)
    tampered["run_digest"] = "sha256:" + "5" * 64
    tampered = add_document_digest({k: v for k, v in tampered.items() if k != "scorer_pass_digest"}, "scorer_pass_digest")
    resolver = MemoryArtifactResolver.build(runs=(run_valid,))
    with pytest.raises(VerificationContextError) as excinfo:
        scoring.verify_scorer_pass_graph(tampered, resolver)
    assert any(d.code == "RUN_DIGEST_MISMATCH" for d in excinfo.value.defects)


# ---------------------------------------------------------------------------
# Evidence reference shape
# ---------------------------------------------------------------------------


def _evidence(scenario, experiment, runs, scorer_passes):
    return scoring.summarize_experiment(
        experiment,
        scenario,
        runs,
        scorer_passes,
        evidence_ref_id=_fresh_evidence_ref_id(),
        intended_owner="person:sol",
        review_at="2026-08-26T00:00:00Z",
        created_at="2026-08-25T00:00:13Z",
        analysis_version="mastermind.agent_evaluation_r0_analysis.v1",
    )


def test_evidence_ref_is_shape_valid() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    sp_invalid = _score(run_invalid)
    evidence = _evidence(scenario, experiment, (run_valid, run_invalid), (sp_valid, sp_invalid))
    assert scoring.validate_evidence_ref_shape(evidence) == "SHAPE_VALID"


def test_evidence_ref_grade_is_always_insufficient_evidence() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    sp_invalid = _score(run_invalid)
    evidence = _evidence(scenario, experiment, (run_valid, run_invalid), (sp_valid, sp_invalid))
    assert evidence["evidence_grade"] == "INSUFFICIENT_EVIDENCE"


def test_evidence_ref_verification_scopes_never_include_content_verified() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    sp_invalid = _score(run_invalid)
    evidence = _evidence(scenario, experiment, (run_valid, run_invalid), (sp_valid, sp_invalid))
    assert "EVIDENCE_CONTENT_VERIFIED" not in evidence["verification_scopes"]
    assert set(evidence["verification_scopes"]) == {"SHAPE_VALID", "EVALUATION_GRAPH_VERIFIED"}


def test_evidence_ref_shape_rejects_content_verified_scope() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    sp_invalid = _score(run_invalid)
    evidence = _evidence(scenario, experiment, (run_valid, run_invalid), (sp_valid, sp_invalid))
    tampered = dict(evidence)
    tampered["verification_scopes"] = ["EVALUATION_GRAPH_VERIFIED", "EVIDENCE_CONTENT_VERIFIED", "SHAPE_VALID"]
    tampered = add_document_digest({k: v for k, v in tampered.items() if k != "evidence_ref_digest"}, "evidence_ref_digest")
    with pytest.raises(ContractError) as excinfo:
        scoring.validate_evidence_ref_shape(tampered)
    assert any(d.code == "CONTENT_VERIFICATION_OVERCLAIMED" for d in excinfo.value.defects)


def test_evidence_ref_non_authority_statement_is_exact() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    sp_invalid = _score(run_invalid)
    evidence = _evidence(scenario, experiment, (run_valid, run_invalid), (sp_valid, sp_invalid))
    assert evidence["non_authority_statement"] == scoring.REQUIRED_NON_AUTHORITY_STATEMENT
    tampered = dict(evidence)
    tampered["non_authority_statement"] = "This evidence is fully authoritative."
    tampered = add_document_digest({k: v for k, v in tampered.items() if k != "evidence_ref_digest"}, "evidence_ref_digest")
    with pytest.raises(ContractError):
        scoring.validate_evidence_ref_shape(tampered)


@pytest.mark.parametrize(
    "forbidden_field",
    ["aggregate_score", "winner", "route", "policy", "approved", "accepted", "promoted", "release", "score"],
)
def test_evidence_ref_rejects_authority_or_aggregate_fields(forbidden_field: str) -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    sp_invalid = _score(run_invalid)
    evidence = _evidence(scenario, experiment, (run_valid, run_invalid), (sp_valid, sp_invalid))
    tampered = dict(evidence)
    tampered[forbidden_field] = "anything"
    with pytest.raises(ContractError) as excinfo:
        scoring.validate_evidence_ref_shape(tampered)
    assert any(d.code == "UNKNOWN_FIELD" for d in excinfo.value.defects)


def test_evidence_ref_rejects_count_mismatch() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    sp_invalid = _score(run_invalid)
    evidence = _evidence(scenario, experiment, (run_valid, run_invalid), (sp_valid, sp_invalid))
    tampered = copy.deepcopy(evidence)
    tampered["counts"]["valid_count"] = 99
    tampered = add_document_digest({k: v for k, v in tampered.items() if k != "evidence_ref_digest"}, "evidence_ref_digest")
    with pytest.raises(ContractError) as excinfo:
        scoring.validate_evidence_ref_shape(tampered)
    assert any(d.code == "COUNT_MISMATCH" for d in excinfo.value.defects)


def test_evidence_ref_rejects_sample_size_mismatch() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    sp_invalid = _score(run_invalid)
    evidence = _evidence(scenario, experiment, (run_valid, run_invalid), (sp_valid, sp_invalid))
    tampered = copy.deepcopy(evidence)
    tampered["sample_size"] = 99
    tampered = add_document_digest({k: v for k, v in tampered.items() if k != "evidence_ref_digest"}, "evidence_ref_digest")
    with pytest.raises(ContractError) as excinfo:
        scoring.validate_evidence_ref_shape(tampered)
    assert any(d.code == "SAMPLE_SIZE_MISMATCH" for d in excinfo.value.defects)


def test_evidence_ref_rejects_unsorted_run_entries() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    sp_invalid = _score(run_invalid)
    evidence = _evidence(scenario, experiment, (run_valid, run_invalid), (sp_valid, sp_invalid))
    tampered = copy.deepcopy(evidence)
    tampered["run_entries"] = list(reversed(tampered["run_entries"]))
    tampered = add_document_digest({k: v for k, v in tampered.items() if k != "evidence_ref_digest"}, "evidence_ref_digest")
    with pytest.raises(ContractError) as excinfo:
        scoring.validate_evidence_ref_shape(tampered)
    assert any(d.code == "LIST_NOT_SORTED" for d in excinfo.value.defects)


# ---------------------------------------------------------------------------
# summarize_experiment: complete-enumeration law (plan §5.6)
# ---------------------------------------------------------------------------


def test_summarize_experiment_retains_invalid_run_never_filters_it() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    sp_invalid = _score(run_invalid)
    evidence = _evidence(scenario, experiment, (run_valid, run_invalid), (sp_valid, sp_invalid))
    run_ids_in_evidence = {entry["run_id"] for entry in evidence["run_entries"]}
    assert run_valid["run_id"] in run_ids_in_evidence
    assert run_invalid["run_id"] in run_ids_in_evidence  # invalid run retained, not filtered
    invalid_entry = next(e for e in evidence["run_entries"] if e["run_id"] == run_invalid["run_id"])
    assert invalid_entry["technical_validity"] == "INVALID_CONFIGURATION"
    assert invalid_entry["scored_projection"] == "INVALID_CONFIGURATION"  # passthrough, never disappears


def test_summarize_experiment_ignores_runs_outside_the_target_experiment() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    other_experiment = build_two_arm_experiment(scenario, config_a, config_b)
    other_draft = build_run_draft(scenario, config_a, other_experiment, arm_id="arm_a", replicate_index=1, run_id=fresh_run_id())
    other_run = validity.finalize_run_receipt(scenario, config_a, other_experiment, other_draft, **VALIDATOR_KW)
    sp_valid = _score(run_valid)
    sp_other = _score(other_run)
    evidence = _evidence(scenario, experiment, (run_valid, other_run), (sp_valid, sp_other))
    run_ids = {e["run_id"] for e in evidence["run_entries"]}
    assert run_valid["run_id"] in run_ids
    assert other_run["run_id"] not in run_ids


def test_valid_run_with_all_required_dimensions_passing_is_valid_pass() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    evidence = _evidence(scenario, experiment, (run_valid,), (sp_valid,))
    entry = next(e for e in evidence["run_entries"] if e["run_id"] == run_valid["run_id"])
    assert entry["scored_projection"] == "VALID_PASS"


def test_valid_run_missing_scorer_pass_is_unscored() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    evidence = _evidence(scenario, experiment, (run_valid,), ())  # no scorer pass at all
    entry = next(e for e in evidence["run_entries"] if e["run_id"] == run_valid["run_id"])
    assert entry["scored_projection"] == "UNSCORED"


def test_evidence_ref_preserves_configuration_arm_pair_replicate_identity() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    evidence = _evidence(scenario, experiment, (run_valid,), (sp_valid,))
    entry = next(e for e in evidence["run_entries"] if e["run_id"] == run_valid["run_id"])
    assert entry["arm_id"] == "arm_a"
    assert entry["replicate_index"] == 1
    assert entry["pair_key"] == f"pair:{scenario['scenario_id']}:v{scenario['scenario_version']}:r1"
    config_ref = next(c for c in evidence["configuration_refs"] if c["arm_id"] == "arm_a")
    assert config_ref["configuration_id"] == config_a["configuration_id"]


# ---------------------------------------------------------------------------
# verify_evidence_ref_graph
# ---------------------------------------------------------------------------


def test_verify_evidence_ref_graph_succeeds_for_a_consistent_reference() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    sp_invalid = _score(run_invalid)
    evidence = _evidence(scenario, experiment, (run_valid, run_invalid), (sp_valid, sp_invalid))
    resolver = MemoryArtifactResolver.build(
        scenarios=(scenario,),
        configurations=(config_a, config_b),
        experiments=(experiment,),
        runs=(run_valid, run_invalid),
        scorer_passes=(sp_valid, sp_invalid),
    )
    result = scoring.verify_evidence_ref_graph(evidence, resolver)
    assert result.scope == "EVALUATION_GRAPH_VERIFIED"
    assert result.artifact_id == evidence["evidence_ref_id"]


def test_verify_evidence_ref_graph_never_claims_content_verified() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    sp_invalid = _score(run_invalid)
    evidence = _evidence(scenario, experiment, (run_valid, run_invalid), (sp_valid, sp_invalid))
    resolver = MemoryArtifactResolver.build(
        scenarios=(scenario,),
        configurations=(config_a, config_b),
        experiments=(experiment,),
        runs=(run_valid, run_invalid),
        scorer_passes=(sp_valid, sp_invalid),
    )
    result = scoring.verify_evidence_ref_graph(evidence, resolver)
    assert result.scope != "EVIDENCE_CONTENT_VERIFIED"


def test_verify_evidence_ref_graph_fails_when_run_cannot_be_resolved() -> None:
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    sp_invalid = _score(run_invalid)
    evidence = _evidence(scenario, experiment, (run_valid, run_invalid), (sp_valid, sp_invalid))
    resolver = MemoryArtifactResolver.build(
        scenarios=(scenario,),
        configurations=(config_a, config_b),
        experiments=(experiment,),
        runs=(run_valid,),  # run_invalid missing
        scorer_passes=(sp_valid, sp_invalid),
    )
    with pytest.raises(VerificationContextError) as excinfo:
        scoring.verify_evidence_ref_graph(evidence, resolver)
    assert any(d.code == "RUN_NOT_RESOLVED" for d in excinfo.value.defects)


def test_verify_evidence_ref_graph_fails_on_stale_counts() -> None:
    # verify_evidence_ref_graph resolves exactly the runs the evidence
    # reference itself CLAIMS (the ArtifactResolver protocol is direct-ID
    # only, §5.6 -- it has no enumeration method), then recomputes
    # counts/projections FROM those resolved runs' true stored validity and
    # compares against the document's claim. Forge the claimed
    # scored_projection for the invalid run (with counts hand-adjusted to
    # stay internally shape-consistent) -- graph verification must still
    # catch that the TRUE resolved run recomputes a different projection.
    scenario, config_a, config_b, experiment, run_valid, run_invalid = _graph_with_two_runs()
    sp_valid = _score(run_valid)
    sp_invalid = _score(run_invalid)
    evidence = _evidence(scenario, experiment, (run_valid, run_invalid), (sp_valid, sp_invalid))
    forged = copy.deepcopy(evidence)
    for entry in forged["run_entries"]:
        if entry["run_id"] == run_invalid["run_id"]:
            assert entry["technical_validity"] == "INVALID_CONFIGURATION"
            entry["technical_validity"] = "VALID"
            entry["scored_projection"] = "VALID_PASS"
    forged["counts"] = {"valid_count": 2, "invalid_count": 0, "degraded_count": 0, "unscored_count": 0, "total_count": 2}
    forged["sample_size"] = 2
    forged = add_document_digest({k: v for k, v in forged.items() if k != "evidence_ref_digest"}, "evidence_ref_digest")
    # confirm the forgery is shape-valid on its own -- the defect this test
    # proves is specifically about graph-level recomputation, not a shape bug
    assert scoring.validate_evidence_ref_shape(forged) == "SHAPE_VALID"
    resolver = MemoryArtifactResolver.build(
        scenarios=(scenario,),
        configurations=(config_a, config_b),
        experiments=(experiment,),
        runs=(run_valid, run_invalid),
        scorer_passes=(sp_valid, sp_invalid),
    )
    with pytest.raises(VerificationContextError) as excinfo:
        scoring.verify_evidence_ref_graph(forged, resolver)
    assert any(d.code == "EVIDENCE_NOT_RECOMPUTABLE" for d in excinfo.value.defects)
