"""Mutation-focused tests for Z0's immutable empirical evidence ledger."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
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
    FailureInjectionReceipt,
    GenerationReceipt,
    REQUIRED_FAILURE_INJECTIONS,
    ResourceObservation,
    TrialReceipt,
    CandidateTrialObservation,
    TrialGrade,
    QueryReceiptError,
    grade_candidate_result,
    parse_normalized_query_receipt,
    build_decision_from_evidence,
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


def _query_payload(
    ledger: EvaluationLedger,
    trial_id: str,
    *,
    query_index: int,
    coverage: str = "FULLY_COVERED",
    status: str = "ZERO_RESULTS",
    query_completeness: str = "COMPLETE",
    zero_result_authority: str = "AUTHORITATIVE_NOT_FOUND_ON_HEALTHY_COVERED_EXACT_REF",
) -> dict[str, object]:
    case_id, candidate = trial_id.split(":", 1)
    query = next(item for item in ledger.manifest.queries if item.case_id == case_id)
    return {
        "schema_version": "mastermind.codeintel_discovery_query.v1",
        "trial_id": trial_id,
        "query_index": query_index,
        "candidate": candidate,
        "query_digest": query.query_digest,
        "normalized_arguments_digest": "a" * 64,
        "evaluation_manifest_digest": ledger.manifest.digest,
        "requested_sources": [
            {
                "logical_repository": row["logical_repo_id"],
                "canonical_repository_digest": hashlib.sha256(
                    row["canonical_repository"].encode("utf-8")
                ).hexdigest(),
                "requested_ref": row["ref"],
                "requested_commit": row["commit"],
                "requested_tree": row["tree"],
            }
            for row in ledger.manifest.corpus
        ],
        "index_identity": {
            "generation_id": "g0",
            "generation_manifest_digest": ledger.manifest.digest,
            "source_epoch_digest": "a" * 64,
            "zoekt_source_commit": "b" * 40,
            "zoekt_binary_digest": "c" * 64,
            "go_toolchain_digest": "d" * 64,
            "module_graph_digest": "e" * 64,
            "ctags_disposition_digest": "f" * 64,
            "configuration_digest": "0" * 64,
            "sandbox_digest": "1" * 64,
        },
        "started_at": "2026-09-03T00:00:00+00:00",
        "ended_at": "2026-09-03T00:00:01+00:00",
        "monotonic_duration_ms": 1000,
        "status": status,
        "coverage": [coverage],
        "health": ["HEALTHY"],
        "freshness": ["EXACT_SHA_CURRENT"],
        "query_completeness": query_completeness,
        "matches": [],
        "limits": {
            "requested_limit": query.max_results,
            "returned_count": 0,
            "total_known": 0,
            "truncated": False,
        },
        "zero_result_authority": zero_result_authority,
        "canonical_verification_required": True,
        "resource_observation": {
            "tool_calls": 1,
            "peak_rss": 2,
            "cpu_ms": 3,
            "disk_io": 4,
            "process_count": 1,
            "open_file_peak": 2,
        },
        "security_observation": {
            "network_attempt_count": 0,
            "credential_access_count": 0,
            "source_write_count": 0,
        },
        "cleanup_observation": {
            "state": "SUCCEEDED",
            "receipt_digest": "2" * 64,
        },
        "raw_response_digest": "3" * 64,
        "normalized_response_digest": "4" * 64,
        "correction_of": None,
    }


def _record_query_receipts(ledger: EvaluationLedger) -> None:
    for query_index, trial_id in enumerate(ledger.manifest.trial_order):
        ledger.record_query_receipt(
            parse_normalized_query_receipt(
                _query_payload(ledger, trial_id, query_index=query_index)
            )
        )


def _record_failure_injections(ledger: EvaluationLedger) -> None:
    for index, failure_code in enumerate(REQUIRED_FAILURE_INJECTIONS):
        ledger.record_failure_injection(
            FailureInjectionReceipt(
                failure_code=failure_code,
                outcome="REJECTED",
                cleanup_state="SUCCEEDED",
                correction_of=None,
                evidence_digest=f"{index:064x}",
            )
        )


def test_real_complete_ledger_is_eligible_only_with_exact_generations_and_trials() -> None:
    """A receipt-complete real run can become evidence, but never by omission."""

    ledger = _ledger()
    _publish_healthy_generation(ledger)
    _record_query_receipts(ledger)
    _record_failure_injections(ledger)
    for trial_id in ledger.manifest.trial_order:
        ledger.record_trial(_trial(ledger, trial_id))

    evidence = ledger.freeze()

    assert isinstance(evidence, EvaluationEvidence)
    assert evidence.state == "ELIGIBLE_REAL_EMPIRICAL_EVIDENCE"
    assert evidence.required_trial_count == len(ledger.manifest.trial_order)
    assert evidence.recorded_trial_count == len(ledger.manifest.trial_order)
    assert evidence.all_resources_known is True
    assert evidence.ledger_digest == ledger.freeze().ledger_digest
    rendered_ledger = ledger.to_payload()
    assert rendered_ledger["generation_receipts"][0]["schema_version"] == (
        "mastermind.codeintel_generation.v1"
    )
    assert rendered_ledger["generation_receipts"][0]["index_build_receipt"][
        "schema_version"
    ] == "mastermind.codeintel_index_build.v1"
    assert rendered_ledger["trial_receipts"][0]["schema_version"] == (
        "mastermind.codeintel_query_trial.v1"
    )
    assert rendered_ledger["trial_receipts"][0]["grader_receipt"]["schema_version"] == (
        "mastermind.codeintel_grader.v1"
    )
    ledger_schema = json.loads(
        (
            Path(__file__).parent.parent.parent
            / "research"
            / "code_intelligence_fabric"
            / "Z0_EVALUATION_LEDGER.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert list(jsonschema.Draft202012Validator(ledger_schema).iter_errors(ledger.to_payload())) == []


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


def test_real_evidence_requires_every_preregistered_failure_injection() -> None:
    """Failure handling is a ledger gate, not a prose claim or a detached unit test."""

    ledger = _ledger()
    _publish_healthy_generation(ledger)
    _record_query_receipts(ledger)
    for trial_id in ledger.manifest.trial_order:
        ledger.record_trial(_trial(ledger, trial_id))

    assert ledger.freeze().state == "NON_DECISION_INCOMPLETE_EVIDENCE"
    assert "MISSING_FAILURE_INJECTIONS" in ledger.freeze().reasons

    _record_failure_injections(ledger)
    assert ledger.freeze().state == "ELIGIBLE_REAL_EMPIRICAL_EVIDENCE"


def test_deterministic_decision_builder_never_accepts_incomplete_or_unsafe_evidence() -> None:
    """The result enum is derived from safety plus complete real evidence, not a boolean flag."""

    ledger = _ledger()
    _publish_healthy_generation(ledger)
    _record_query_receipts(ledger)
    _record_failure_injections(ledger)
    for trial_id in ledger.manifest.trial_order:
        ledger.record_trial(_trial(ledger, trial_id))
    complete = ledger.freeze()
    answer_keys = _answer_keys(ledger)

    assert build_decision_from_evidence(
        complete,
        repositories_safe=True,
        ledger=ledger,
        evaluation_manifest=ledger.manifest,
        answer_keys=answer_keys,
    ) == (
        "ZOEKT_FACADE_ACCEPTED_FOR_CI3"
    )
    assert build_decision_from_evidence(
        complete,
        repositories_safe=False,
        ledger=ledger,
        evaluation_manifest=ledger.manifest,
        answer_keys=answer_keys,
    ) == (
        "NO_SAFE_GLOBAL_INDEX"
    )

    synthetic = _ledger(run_kind="synthetic")
    _publish_healthy_generation(synthetic)
    assert build_decision_from_evidence(
        synthetic.freeze(),
        repositories_safe=True,
        ledger=synthetic,
        evaluation_manifest=synthetic.manifest,
        answer_keys=_answer_keys(synthetic),
    ) == (
        "ZOEKT_REQUIRES_ARCHITECTURE_REVISION"
    )


def test_decision_builder_revalidates_every_public_completion_predicate() -> None:
    """A forged summary cannot promote an incomplete ledger to CI3 eligibility."""

    ledger = _ledger()
    _publish_healthy_generation(ledger)
    _record_query_receipts(ledger)
    _record_failure_injections(ledger)
    for trial_id in ledger.manifest.trial_order:
        ledger.record_trial(_trial(ledger, trial_id))
    complete = ledger.freeze()
    answer_keys = _answer_keys(ledger)

    forged_evidence = (
        replace(complete, run_kind="synthetic"),
        replace(complete, active_generation_id=None),
        replace(complete, recorded_trial_count=complete.recorded_trial_count - 1),
        replace(complete, failed_trial_count=1),
        replace(
            complete,
            recorded_failure_injection_count=(
                complete.recorded_failure_injection_count - 1
            ),
        ),
        replace(complete, all_resources_known=False),
        replace(complete, all_identity_bound=False),
        replace(complete, reasons=("FORGED_COMPLETION",)),
        replace(complete, canonical_bytes=b"{}"),
    )

    for forged in forged_evidence:
        assert build_decision_from_evidence(
            forged,
            repositories_safe=True,
            ledger=ledger,
            evaluation_manifest=ledger.manifest,
            answer_keys=answer_keys,
        ) == (
            "ZOEKT_REQUIRES_ARCHITECTURE_REVISION"
        )
        assert build_decision_from_evidence(
            forged,
            repositories_safe=False,
            ledger=ledger,
            evaluation_manifest=ledger.manifest,
            answer_keys=answer_keys,
        ) == (
            "NO_SAFE_GLOBAL_INDEX"
        )

    self_hashed_payload = json.loads(complete.canonical_bytes)
    query_sources = self_hashed_payload["query_receipts"][0]["requested_sources"]
    assert isinstance(query_sources, list)
    assert isinstance(query_sources[0], dict)
    query_sources[0]["requested_tree"] = "f" * 40
    self_hashed_canonical = json.dumps(
        self_hashed_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    self_hashed_forgery = replace(
        complete,
        canonical_bytes=self_hashed_canonical,
        ledger_digest=hashlib.sha256(self_hashed_canonical).hexdigest(),
    )
    assert build_decision_from_evidence(
        self_hashed_forgery,
        repositories_safe=True,
        ledger=ledger,
        evaluation_manifest=ledger.manifest,
        answer_keys=answer_keys,
    ) == "ZOEKT_REQUIRES_ARCHITECTURE_REVISION"

    unbound_answer_keys = dict(answer_keys)
    unbound_answer_keys["E1"] = AnswerKey(
        case_id="E1",
        expected_identities=(
            ("alpha", "synthetic-org/alpha", "main", "engine/core.py", 1, 1),
        ),
        forbidden_identities=(),
        canonical_bytes=b"unbound-answer-key",
        digest=ledger.manifest.queries[0].answer_key_digest,
    )
    assert build_decision_from_evidence(
        complete,
        repositories_safe=True,
        ledger=ledger,
        evaluation_manifest=ledger.manifest,
        answer_keys=unbound_answer_keys,
    ) == "ZOEKT_REQUIRES_ARCHITECTURE_REVISION"


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

    def receipt_factory(
        query: object,
        trial_id: str,
        query_index: int,
        observation: CandidateTrialObservation,
    ) -> object:
        if observation.outcome == "timeout":
            return parse_normalized_query_receipt(
                _query_payload(
                    ledger,
                    trial_id,
                    query_index=query_index,
                    status="TIMEOUT",
                    query_completeness="TIMED_OUT",
                    zero_result_authority="NONAUTHORITATIVE_TRUNCATED_OR_INCOMPLETE",
                )
            )
        return parse_normalized_query_receipt(
            _query_payload(ledger, trial_id, query_index=query_index)
        )

    receipts = run_paired_trials(
        ledger,
        baseline_executor=baseline,
        zoekt_executor=zoekt,
        answer_keys=_answer_keys(ledger),
        query_receipt_factory=receipt_factory,
    )

    assert tuple(item.trial_id for item in receipts) == ledger.manifest.trial_order
    assert tuple(f"{case}:{candidate}" for candidate, case in seen) == ledger.manifest.trial_order
    timeout = next(item for item in receipts if item.trial_id == "X3:zoekt")
    assert timeout.outcome == "timeout"
    assert timeout.failure_code == "TIMEOUT"
    assert timeout.resource.cpu_ms == UNKNOWN_RESOURCE
    assert tuple(item.trial_id for item in ledger.query_receipts) == ledger.manifest.trial_order
    assert ledger.freeze().state == "NON_DECISION_INCOMPLETE_EVIDENCE"


def test_paired_runner_records_query_receipt_failures_and_continues() -> None:
    """Factory, shape, and ledger-validation faults remain visible trial evidence."""

    ledger = _ledger()
    _publish_healthy_generation(ledger)
    seen: list[str] = []

    def executor(query: object) -> CandidateTrialObservation:
        seen.append(getattr(query, "case_id"))
        return CandidateTrialObservation(
            outcome="completed",
            query_completed=True,
            truncated=False,
            returned_identities=(),
            resource=ResourceObservation(cpu_ms=1, rss_bytes=2, disk_bytes=3),
            failure_code=None,
        )

    def receipt_factory(
        query: object,
        trial_id: str,
        query_index: int,
        observation: CandidateTrialObservation,
    ) -> object:
        del query, observation
        if trial_id == "X3:zoekt":
            raise RuntimeError("synthetic receipt factory failure")
        if trial_id == "R3:baseline":
            return object()
        payload = _query_payload(ledger, trial_id, query_index=query_index)
        if trial_id == "A1:zoekt":
            sources = payload["requested_sources"]
            assert isinstance(sources, list)
            assert isinstance(sources[0], dict)
            sources[0]["requested_tree"] = "f" * 40
        return parse_normalized_query_receipt(payload)

    receipts = run_paired_trials(
        ledger,
        baseline_executor=executor,
        zoekt_executor=executor,
        answer_keys=_answer_keys(ledger),
        query_receipt_factory=receipt_factory,
    )

    assert tuple(item.trial_id for item in receipts) == ledger.manifest.trial_order
    assert len(seen) == len(ledger.manifest.trial_order)
    failures = ledger.query_receipt_failure_receipts
    assert tuple(item.trial_id for item in failures) == (
        "X3:zoekt",
        "R3:baseline",
        "A1:zoekt",
    )
    assert failures[0].stage == "FACTORY"
    assert all(item.failure_code == "RESULT_SCHEMA_INVALID" for item in failures)
    failed_trials = tuple(item for item in receipts if item.failure_code is not None)
    assert tuple(item.trial_id for item in failed_trials) == tuple(
        item.trial_id for item in failures
    )
    assert all(item.outcome == "error" for item in failed_trials)
    assert all(item.resource.cpu_ms == UNKNOWN_RESOURCE for item in failed_trials)
    frozen = ledger.freeze()
    assert frozen.state == "NON_DECISION_INCOMPLETE_EVIDENCE"
    assert "QUERY_RECEIPT_NORMALIZATION_FAILURE" in frozen.reasons
    ledger_schema_path = (
        Path(__file__).parent.parent.parent
        / "research"
        / "code_intelligence_fabric"
        / "Z0_EVALUATION_LEDGER.schema.json"
    )
    ledger_schema = json.loads(ledger_schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(ledger_schema)
    assert list(validator.iter_errors(ledger.to_payload())) == []


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


def test_normalized_query_receipt_derives_zero_authority_from_closed_state() -> None:
    """Neither the caller nor raw engine output gets to pronounce an absence authoritative."""

    ledger = _ledger()
    payload = _query_payload(ledger, "A1:baseline", query_index=0)
    receipt = parse_normalized_query_receipt(payload)

    assert receipt.zero_result_authority == (
        "AUTHORITATIVE_NOT_FOUND_ON_HEALTHY_COVERED_EXACT_REF"
    )
    assert receipt.status == "ZERO_RESULTS"

    stale_claim = _query_payload(
        ledger,
        "A1:baseline",
        query_index=0,
        coverage="PARTIALLY_COVERED",
    )
    with pytest.raises(QueryReceiptError, match="zero_result_authority"):
        parse_normalized_query_receipt(stale_claim)

    unbound_response = _query_payload(ledger, "A1:baseline", query_index=0)
    unbound_response["raw_response_digest"] = UNKNOWN_RESOURCE
    with pytest.raises(QueryReceiptError, match="zero_result_authority"):
        parse_normalized_query_receipt(unbound_response)


def test_query_receipt_cannot_substitute_a_different_ref_commit_or_tree() -> None:
    """Syntactically valid source identities still need the exact frozen corpus binding."""

    ledger = _ledger()
    _publish_healthy_generation(ledger)
    mutated = _query_payload(ledger, "E1:baseline", query_index=0)
    sources = mutated["requested_sources"]
    assert isinstance(sources, list)
    assert isinstance(sources[0], dict)
    sources[0]["requested_tree"] = "f" * 40

    with pytest.raises(EvidenceError, match="requested source identity"):
        ledger.record_query_receipt(parse_normalized_query_receipt(mutated))


def test_clean_transport_with_low_recall_or_false_positives_is_not_complete_evidence() -> None:
    """A candidate cannot graduate merely because its request returned normally."""

    ledger = _ledger()
    _publish_healthy_generation(ledger)
    _record_query_receipts(ledger)
    _record_failure_injections(ledger)
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
    _record_query_receipts(ledger)
    _record_failure_injections(ledger)
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

    incomplete = dict(real)
    incomplete["recorded_trial_count"] = real["recorded_trial_count"] - 1
    incomplete["recorded_failure_injection_count"] = (
        real["recorded_failure_injection_count"] - 1
    )
    payload["evaluation_evidence"] = incomplete
    assert list(validator.iter_errors(payload))
