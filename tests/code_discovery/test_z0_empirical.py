"""Mutation-focused tests for Z0's immutable empirical evidence ledger."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from experiments.code_discovery.baseline_search import AnswerKey
from experiments.code_discovery.evaluation_manifest import load_evaluation_manifest
from experiments.code_discovery.z0_empirical import (
    UNKNOWN_RESOURCE,
    EvaluationEvidence,
    EvaluationLedger,
    EvidenceError,
    GenerationReceipt,
    ResourceObservation,
    TrialReceipt,
    CandidateTrialObservation,
    TrialGrade,
    grade_candidate_result,
    run_paired_trials,
)


_MANIFEST = (
    Path(__file__).parent.parent
    / "fixtures"
    / "code_discovery"
    / "evaluation-manifest.v1.json"
)


def _ledger(*, run_kind: str = "real") -> EvaluationLedger:
    return EvaluationLedger(
        load_evaluation_manifest(_MANIFEST),
        run_kind=run_kind,
        source_census_digest="a" * 64,
    )


def _publish_healthy_generation(ledger: EvaluationLedger, generation_id: str = "g0") -> None:
    for corpus in ledger.manifest.corpus:
        ledger.record_generation(
            GenerationReceipt(
                generation_id=generation_id,
                logical_repo_id=corpus["logical_repo_id"],
                source_commit=corpus["commit"],
                source_tree=corpus["tree"],
                status="succeeded",
                indexed_commit_sha=corpus["commit"],
                shard_digest="b" * 64,
                failure_code=None,
            )
        )
    publication = ledger.publish_generation(generation_id)
    assert publication.state == "PUBLISHED"


def _trial(
    ledger: EvaluationLedger,
    trial_id: str,
    *,
    outcome: str = "completed",
    resource: ResourceObservation | None = None,
    answer_key_digest: str | None = None,
    recall: float = 1.0,
    false_positive_count: int = 0,
) -> TrialReceipt:
    case_id, _candidate = trial_id.split(":", 1)
    query = next(item for item in ledger.manifest.queries if item.case_id == case_id)
    return TrialReceipt(
        trial_id=trial_id,
        attempt_index=1,
        outcome=outcome,
        answer_key_digest=answer_key_digest or query.answer_key_digest,
        source_census_digest="a" * 64,
        generation_id="g0",
        query_completed=outcome == "completed",
        truncated=False,
        returned_identities=(),
        recall=recall if outcome == "completed" else 0.0,
        false_positive_count=false_positive_count,
        resource=resource or ResourceObservation(cpu_ms=1, rss_bytes=2, disk_bytes=3),
        failure_code=None if outcome == "completed" else "TIMEOUT",
    )


def _answer_keys(ledger: EvaluationLedger) -> dict[str, AnswerKey]:
    return {
        query.case_id: AnswerKey(
            case_id=query.case_id,
            expected_identities=(),
            forbidden_identities=(),
            canonical_bytes=b"",
            digest=query.answer_key_digest,
        )
        for query in ledger.manifest.queries
    }


def test_real_complete_ledger_is_eligible_only_with_exact_generations_and_trials() -> None:
    """A receipt-complete real run can become evidence, but never by omission."""

    ledger = _ledger()
    _publish_healthy_generation(ledger)
    for trial_id in ledger.manifest.trial_order:
        ledger.record_trial(_trial(ledger, trial_id))

    evidence = ledger.freeze()

    assert isinstance(evidence, EvaluationEvidence)
    assert evidence.state == "ELIGIBLE_REAL_EMPIRICAL_EVIDENCE"
    assert evidence.required_trial_count == len(ledger.manifest.trial_order)
    assert evidence.recorded_trial_count == len(ledger.manifest.trial_order)
    assert evidence.all_resources_known is True
    assert evidence.ledger_digest == ledger.freeze().ledger_digest


def test_failed_or_partial_generation_is_recorded_and_never_published_over_a_healthy_one() -> None:
    """A partial build cannot replace the current healthy generation invisibly."""

    ledger = _ledger()
    _publish_healthy_generation(ledger, "g0")
    first = ledger.manifest.corpus[0]
    ledger.record_generation(
        GenerationReceipt(
            generation_id="g1",
            logical_repo_id=first["logical_repo_id"],
            source_commit=first["commit"],
            source_tree=first["tree"],
            status="failed",
            indexed_commit_sha=None,
            shard_digest=None,
            failure_code="PROCESS_CRASH",
        )
    )

    refused = ledger.publish_generation("g1")

    assert refused.state == "PUBLISH_REFUSED"
    assert refused.active_generation_id == "g0"
    assert ledger.generation_receipts[-1].failure_code == "PROCESS_CRASH"
    assert ledger.freeze().state == "NON_DECISION_INCOMPLETE_EVIDENCE"


def test_omitted_index_sha_duplicate_repository_and_moved_source_fail_closed() -> None:
    """Identity mutations cannot collapse corpus coverage or bless stale source bytes."""

    ledger = _ledger()
    first = ledger.manifest.corpus[0]
    missing_sha = GenerationReceipt(
        generation_id="g0",
        logical_repo_id=first["logical_repo_id"],
        source_commit=first["commit"],
        source_tree=first["tree"],
        status="succeeded",
        indexed_commit_sha=None,
        shard_digest="b" * 64,
        failure_code=None,
    )
    with pytest.raises(EvidenceError, match="indexed_commit_sha"):
        ledger.record_generation(missing_sha)

    moved_source = GenerationReceipt(
        generation_id="g0",
        logical_repo_id=first["logical_repo_id"],
        source_commit="f" * 40,
        source_tree=first["tree"],
        status="succeeded",
        indexed_commit_sha="f" * 40,
        shard_digest="b" * 64,
        failure_code=None,
    )
    with pytest.raises(EvidenceError, match="source_commit"):
        ledger.record_generation(moved_source)

    valid = GenerationReceipt(
        generation_id="g0",
        logical_repo_id=first["logical_repo_id"],
        source_commit=first["commit"],
        source_tree=first["tree"],
        status="succeeded",
        indexed_commit_sha=first["commit"],
        shard_digest="b" * 64,
        failure_code=None,
    )
    ledger.record_generation(valid)
    with pytest.raises(EvidenceError, match="duplicate repository"):
        ledger.record_generation(valid)


def test_answer_key_change_unknown_resource_and_dropped_timeout_are_not_decision_evidence() -> None:
    """Three common flattering mutations all leave the ledger non-decision eligible."""

    ledger = _ledger()
    _publish_healthy_generation(ledger)
    first_trial = ledger.manifest.trial_order[0]
    with pytest.raises(EvidenceError, match="answer_key_digest"):
        ledger.record_trial(_trial(ledger, first_trial, answer_key_digest="c" * 64))

    timeout = _trial(
        ledger,
        first_trial,
        outcome="timeout",
        resource=ResourceObservation(
            cpu_ms=UNKNOWN_RESOURCE,
            rss_bytes=UNKNOWN_RESOURCE,
            disk_bytes=UNKNOWN_RESOURCE,
        ),
    )
    ledger.record_trial(timeout)
    with pytest.raises(EvidenceError, match="retry"):
        ledger.record_trial(
            TrialReceipt(
                **{**timeout.__dict__, "attempt_index": 2}
            )
        )

    evidence = ledger.freeze()
    assert evidence.all_resources_known is False
    assert evidence.failed_trial_count == 1
    assert evidence.state == "NON_DECISION_INCOMPLETE_EVIDENCE"
    assert ledger.trial_receipts == (timeout,)


def test_synthetic_only_winner_is_a_typed_nondecision_state() -> None:
    """Synthetic tests are valuable mutation proof, never a real-run acceptance substitute."""

    ledger = _ledger(run_kind="synthetic")
    _publish_healthy_generation(ledger)
    for trial_id in ledger.manifest.trial_order:
        ledger.record_trial(_trial(ledger, trial_id))

    assert ledger.freeze().state == "NON_DECISION_SYNTHETIC_ONLY"


def test_paired_harness_uses_the_frozen_alternating_order_and_retains_callback_timeout() -> None:
    """Both candidates receive the same query declaration; a timeout is a receipt, not a retry."""

    ledger = _ledger()
    _publish_healthy_generation(ledger)
    seen: list[tuple[str, str]] = []

    def baseline(query: object) -> CandidateTrialObservation:
        seen.append(("baseline", getattr(query, "case_id")))
        return CandidateTrialObservation(
            outcome="completed",
            query_completed=True,
            truncated=False,
            returned_identities=(),
            resource=ResourceObservation(cpu_ms=1, rss_bytes=2, disk_bytes=3),
            failure_code=None,
        )

    def zoekt(query: object) -> CandidateTrialObservation:
        seen.append(("zoekt", getattr(query, "case_id")))
        if getattr(query, "case_id") == "X3":
            raise TimeoutError("bounded synthetic timeout")
        return CandidateTrialObservation(
            outcome="completed",
            query_completed=True,
            truncated=False,
            returned_identities=(),
            resource=ResourceObservation(cpu_ms=1, rss_bytes=2, disk_bytes=3),
            failure_code=None,
        )

    receipts = run_paired_trials(
        ledger,
        baseline_executor=baseline,
        zoekt_executor=zoekt,
        answer_keys=_answer_keys(ledger),
    )

    assert tuple(item.trial_id for item in receipts) == ledger.manifest.trial_order
    assert tuple(f"{case}:{candidate}" for candidate, case in seen) == ledger.manifest.trial_order
    timeout = next(item for item in receipts if item.trial_id == "X3:zoekt")
    assert timeout.outcome == "timeout"
    assert timeout.failure_code == "TIMEOUT"
    assert timeout.resource.cpu_ms == UNKNOWN_RESOURCE
    assert ledger.freeze().state == "NON_DECISION_INCOMPLETE_EVIDENCE"


def test_independent_grader_derives_recall_and_false_positives_from_answer_keys() -> None:
    """A candidate's own score is ignored in favor of source-derived identities."""

    expected = ("alpha", "synthetic-org/alpha", "main", "engine/core.py", 1, 1)
    forbidden = ("beta", "synthetic-org/beta", "main", "engine/core.py", 1, 1)
    answer = AnswerKey(
        case_id="E1",
        expected_identities=(expected,),
        forbidden_identities=(forbidden,),
        canonical_bytes=b"source-derived-answer-key",
        digest="a" * 64,
    )

    grade = grade_candidate_result(answer, (expected, forbidden))

    assert isinstance(grade, TrialGrade)
    assert grade.recall == 1.0
    assert grade.false_positive_count == 1


def test_clean_transport_with_low_recall_or_false_positives_is_not_complete_evidence() -> None:
    """A candidate cannot graduate merely because its request returned normally."""

    ledger = _ledger()
    _publish_healthy_generation(ledger)
    for trial_id in ledger.manifest.trial_order:
        ledger.record_trial(
            _trial(
                ledger,
                trial_id,
                recall=0.0 if trial_id == "E1:zoekt" else 1.0,
                false_positive_count=1 if trial_id == "A1:baseline" else 0,
            )
        )

    evidence = ledger.freeze()

    assert evidence.state == "NON_DECISION_INCOMPLETE_EVIDENCE"
    assert evidence.failed_trial_count == 2
    assert "TRIAL_GRADE_FAILURE" in evidence.reasons


def test_result_schema_allows_acceptance_only_with_complete_real_empirical_evidence() -> None:
    """The machine-readable gate rejects a synthetic stand-in before CI3 acceptance."""

    ledger = _ledger()
    _publish_healthy_generation(ledger)
    for trial_id in ledger.manifest.trial_order:
        ledger.record_trial(_trial(ledger, trial_id))
    real = ledger.freeze().to_result_payload()
    schema_path = (
        Path(__file__).parent.parent.parent
        / "research"
        / "code_intelligence_fabric"
        / "z0-result.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    payload = {
        "schema_version": "mastermind.codeintel_z0_result.v1",
        "decision": "ZOEKT_FACADE_ACCEPTED_FOR_CI3",
        "generated_at": "2026-09-03T00:00:00+00:00",
        "manifest_digest": "a" * 64,
        "path_policy_digest": "b" * 64,
        "tool_schema_digest": "c" * 64,
        "zoekt_source_commit": "d" * 40,
        "binary_digests": {
            "zoekt_git_index": "e" * 64,
            "zoekt_webserver": "f" * 64,
        },
        "repository_statuses": [],
        "resource_observations": {},
        "evaluation_evidence": real,
    }
    assert list(validator.iter_errors(payload)) == []

    synthetic = dict(real)
    synthetic["state"] = "NON_DECISION_SYNTHETIC_ONLY"
    synthetic["run_kind"] = "synthetic"
    payload["evaluation_evidence"] = synthetic
    assert list(validator.iter_errors(payload))
