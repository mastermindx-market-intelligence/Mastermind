"""Mutation tests for receipt-bound Z0 empirical evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from experiments.code_discovery.baseline_search import (
    AnswerKey,
    SourceCensus,
    census_sealed_sources,
)
from experiments.code_discovery.evaluation_manifest import (
    load_evaluation_manifest,
    parse_evaluation_manifest,
)
from experiments.code_discovery.index_manifest import (
    IndexManifest,
    load_index_manifest,
    source_tree_digest,
)
from experiments.code_discovery.z0_empirical import (
    UNKNOWN_RESOURCE,
    CandidateTransport,
    CapturedCandidateAdapter,
    CapturedEvaluation,
    ComparativeEvidence,
    DecisionEvidence,
    EvaluationBundleIdentity,
    EvaluationLedger,
    EvidenceError,
    FailureExecutionReceipt,
    FailureInjectionReceipt,
    GenerationReceipt,
    GenerationExecutionReceipt,
    QueryPlan,
    QueryReceiptError,
    ResourceObservation,
    build_query_plan,
    build_decision_from_evidence,
    parse_normalized_query_receipt,
    run_empirical_evaluation,
    run_paired_trials,
)


_MANIFEST = (
    Path(__file__).parent.parent / "fixtures" / "code_discovery" / "evaluation-manifest.v1.json"
)
_LEDGER_SCHEMA = (
    Path(__file__).parent.parent.parent
    / "research"
    / "code_intelligence_fabric"
    / "Z0_EVALUATION_LEDGER.schema.json"
)
_RESULT_SCHEMA = (
    Path(__file__).parent.parent.parent
    / "research"
    / "code_intelligence_fabric"
    / "z0-result.schema.json"
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _ledger(*, run_kind: str = "real") -> EvaluationLedger:
    return EvaluationLedger(
        load_evaluation_manifest(_MANIFEST),
        run_kind=run_kind,
        source_census_digest="a" * 64,
    )


def _answer_keys(ledger: EvaluationLedger) -> dict[str, AnswerKey]:
    """Make source-like canonical keys for each unique query/repetition row."""

    result: dict[str, AnswerKey] = {}
    for query in ledger.manifest.queries:
        document = _canonical(
            {
                "case_id": query.case_id,
                "census_digest": "a" * 64,
                "path_policy_digest": ledger.manifest.path_policy_rules[
                    "policy_document_digest"
                ],
                "query": {
                    "query": f"synthetic-{query.case_id}-{query.warm_or_cold}",
                    "regex": False,
                    "case_sensitive": False,
                    "repository_ids": list(query.logical_repo_ids),
                    "refs": list(query.refs),
                    "path_prefixes": list(query.path_prefixes),
                    "languages": list(query.languages),
                    "limit": query.max_results,
                    "context_lines": query.max_context_lines,
                    "timeout_ms": query.timeout_ms,
                },
                "expected": [],
                "forbidden": [],
            }
        )
        answer_key = AnswerKey(
            case_id=query.case_id,
            expected_identities=(),
            forbidden_identities=(),
            canonical_bytes=document,
            digest=hashlib.sha256(document).hexdigest(),
            path_policy_digest=ledger.manifest.path_policy_rules["policy_document_digest"],
        )
        assert answer_key.digest == query.answer_key_digest
        result[query.identity] = answer_key
    return result


def _plans(ledger: EvaluationLedger) -> dict[str, QueryPlan]:
    answer_keys = _answer_keys(ledger)
    return {
        query.identity: build_query_plan(ledger.manifest, query, answer_keys[query.identity])
        for query in ledger.manifest.queries
    }


def _publish_generation(ledger: EvaluationLedger, generation_id: str = "g0") -> None:
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
                execution=GenerationExecutionReceipt(
                    evaluation_manifest_digest=ledger.manifest.digest,
                    source_blob_census_digest=corpus["blob_census_digest"],
                    source_path_policy_digest=corpus["include_exclude_policy_digest"],
                    zoekt_source_commit="c" * 40,
                    zoekt_binary_digest="d" * 64,
                    go_toolchain_digest="e" * 64,
                    module_graph_digest="f" * 64,
                    ctags_disposition_digest="0" * 64,
                    configuration_digest="1" * 64,
                    sandbox_digest="2" * 64,
                    selected_file_count=1,
                    selected_byte_count=1,
                    shard_count=1,
                    build_ms=1,
                    refresh_ms=1,
                    query_ms=1,
                    cpu_ms=1,
                    rss_bytes=1,
                    disk_bytes=1,
                    disk_io_bytes=1,
                    process_count=1,
                    open_file_peak=1,
                    network_attempt_count=0,
                    credential_access_count=0,
                    source_write_count=0,
                    output_digest="3" * 64,
                    published_generation_id=generation_id,
                    prior_generation_id=None,
                    effect="PUBLISHED",
                    cleanup_state="SUCCEEDED",
                    cleanup_receipt_digest="4" * 64,
                    correction_of=None,
                ),
            )
        )
    assert ledger.publish_generation(generation_id).state == "PUBLISHED"


def _query_payload(
    ledger: EvaluationLedger,
    plan: QueryPlan,
    candidate: str,
    *,
    status: str = "ZERO_RESULTS",
    query_completeness: str = "COMPLETE",
    zero_result_authority: str = "AUTHORITATIVE_NOT_FOUND_ON_HEALTHY_COVERED_EXACT_REF",
) -> dict[str, object]:
    corpus = {str(row["logical_repo_id"]): row for row in ledger.manifest.corpus}
    return {
        "schema_version": "mastermind.codeintel_discovery_query.v1",
        "trial_id": plan.trial_id(candidate),
        "query_identity": plan.query_identity,
        "query_index": plan.query_index,
        "candidate": candidate,
        "query_plan_digest": plan.digest,
        "query_digest": plan.query_digest,
        "normalized_arguments_digest": plan.normalized_arguments_digest,
        "evaluation_manifest_digest": ledger.manifest.digest,
        "source_statuses": [
            {
                "logical_repository": logical_id,
                "canonical_repository_digest": hashlib.sha256(
                    str(corpus[logical_id]["canonical_repository"]).encode("utf-8")
                ).hexdigest(),
                "requested_ref": corpus[logical_id]["ref"],
                "requested_commit": corpus[logical_id]["commit"],
                "requested_tree": corpus[logical_id]["tree"],
                "indexed_commit": corpus[logical_id]["commit"],
                "indexed_tree": corpus[logical_id]["tree"],
                "generation_id": "g0",
                "coverage": "FULLY_COVERED",
                "health": "HEALTHY",
                "freshness": "EXACT_SHA_CURRENT",
            }
            for logical_id in plan.logical_repo_ids
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
        "query_completeness": query_completeness,
        "matches": [],
        "limits": {
            "requested_limit": plan.max_results,
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
        "cleanup_observation": {"state": "SUCCEEDED", "receipt_digest": "2" * 64},
        "raw_response_digest": "3" * 64,
        "normalized_response_digest": "4" * 64,
        "correction_of": None,
    }


def _source_statuses(
    ledger: EvaluationLedger,
    plan: QueryPlan,
    *,
    coverage: str = "FULLY_COVERED",
    health: str = "HEALTHY",
    freshness: str = "EXACT_SHA_CURRENT",
) -> list[dict[str, object]]:
    """Build one keyed execution status for every source in the frozen plan."""

    corpus = {str(row["logical_repo_id"]): row for row in ledger.manifest.corpus}
    return [
        {
            "logical_repository": logical_id,
            "canonical_repository_digest": hashlib.sha256(
                str(corpus[logical_id]["canonical_repository"]).encode("utf-8")
            ).hexdigest(),
            "requested_ref": corpus[logical_id]["ref"],
            "requested_commit": corpus[logical_id]["commit"],
            "requested_tree": corpus[logical_id]["tree"],
            "indexed_commit": corpus[logical_id]["commit"],
            "indexed_tree": corpus[logical_id]["tree"],
            "generation_id": "g0",
            "coverage": coverage,
            "health": health,
            "freshness": freshness,
        }
        for logical_id in plan.logical_repo_ids
    ]


def test_manifest_requires_counterbalanced_cold_warm_query_identities() -> None:
    """The fixture proves each required case has two distinct paired queries."""

    manifest = load_evaluation_manifest(_MANIFEST)
    for case_id in ("E1", "X3", "R3", "A1"):
        rows = tuple(query for query in manifest.queries if query.case_id == case_id)
        assert {query.warm_or_cold for query in rows} == {"cold", "warm"}
        assert {query.candidate_order[0] for query in rows} == {"baseline", "zoekt"}
        assert len({query.identity for query in rows}) == len(rows)
        assert all(
            sum(query.identity in trial_id for trial_id in manifest.trial_order) == 2
            for query in rows
        )
    assert len(manifest.trial_order) == len(manifest.queries) * 2


def test_query_plan_binds_answer_key_manifest_and_normalized_arguments() -> None:
    """Changing any query/filter/answer field prevents either candidate from running."""

    ledger = _ledger()
    answer_keys = _answer_keys(ledger)
    query = ledger.manifest.queries[0]
    plan = build_query_plan(ledger.manifest, query, answer_keys[query.identity])

    assert plan.query_identity == query.identity
    assert plan.normalized_arguments_digest != plan.digest
    assert plan.trial_id("baseline").endswith(":baseline")
    with pytest.raises(EvidenceError, match="answer key digest"):
        build_query_plan(
            ledger.manifest,
            query,
            AnswerKey(
                case_id=plan.case_id,
                expected_identities=(),
                forbidden_identities=(),
                canonical_bytes=answer_keys[plan.query_identity].canonical_bytes,
                digest="f" * 64,
                path_policy_digest=answer_keys[plan.query_identity].path_policy_digest,
            ),
        )


def test_paired_harness_gives_both_candidates_the_same_queryplan_and_derives_trial_truth() -> None:
    """Executors can contribute transport bytes, not a second semantic result."""

    ledger = _ledger()
    _publish_generation(ledger)
    answer_keys = _answer_keys(ledger)
    seen: dict[str, list[tuple[str, int]]] = {"baseline": [], "zoekt": []}

    def executor(candidate: str):
        def run(plan: QueryPlan) -> CandidateTransport:
            seen[candidate].append((plan.query_identity, id(plan)))
            return CandidateTransport(receipt_document={"trial": plan.trial_id(candidate)})

        return run

    def receipt_factory(plan: QueryPlan, identity: object, transport: CandidateTransport):
        del transport
        candidate = getattr(identity, "candidate")
        return parse_normalized_query_receipt(
            _query_payload(ledger, plan, candidate), query_plan=plan
        )

    receipts = run_paired_trials(
        ledger,
        baseline_executor=executor("baseline"),
        zoekt_executor=executor("zoekt"),
        answer_keys=answer_keys,
        query_receipt_factory=receipt_factory,
    )

    assert tuple(receipt.trial_id for receipt in receipts) == ledger.manifest.trial_order
    assert len(receipts) == len(ledger.manifest.queries) * 2
    for query in ledger.manifest.queries:
        baseline = next(item for item in seen["baseline"] if item[0] == query.identity)
        zoekt = next(item for item in seen["zoekt"] if item[0] == query.identity)
        assert baseline[1] == zoekt[1]
    assert all(receipt.recall == 1.0 for receipt in receipts)
    assert all(receipt.false_positive_count == 0 for receipt in receipts)
    assert all(receipt.query_receipt_digest for receipt in receipts)


def _complete_real_ledger() -> tuple[EvaluationLedger, dict[str, AnswerKey]]:
    ledger = _ledger()
    _publish_generation(ledger)
    answer_keys = _answer_keys(ledger)

    def executor(plan: QueryPlan) -> CandidateTransport:
        return CandidateTransport(receipt_document=plan.query_identity.encode("utf-8"))

    def receipt_factory(plan: QueryPlan, identity: object, transport: CandidateTransport):
        del transport
        return parse_normalized_query_receipt(
            _query_payload(ledger, plan, getattr(identity, "candidate")),
            query_plan=plan,
        )

    run_paired_trials(
        ledger,
        baseline_executor=executor,
        zoekt_executor=executor,
        answer_keys=answer_keys,
        query_receipt_factory=receipt_factory,
    )
    for injection_id in ledger.manifest.failure_injections:
        digest = hashlib.sha256(injection_id.encode("utf-8")).hexdigest()
        ledger.record_failure_injection(
            FailureInjectionReceipt(
                failure_code=injection_id,
                outcome="REJECTED",
                cleanup_state="SUCCEEDED",
                correction_of=None,
                evidence_digest=digest,
                execution=FailureExecutionReceipt(
                    injection_id=injection_id,
                    expected_failure_code="PROCESS_CRASH",
                    observed_failure_code="PROCESS_CRASH",
                    expected_effect="PUBLISH_REFUSED",
                    observed_effect="PUBLISH_REFUSED",
                    cleanup_state="SUCCEEDED",
                    execution_receipt_digest=digest,
                ),
            )
        )
    return ledger, answer_keys


def _decision_evidence(ledger: EvaluationLedger, *, topology_id: str = "T0") -> DecisionEvidence:
    return DecisionEvidence(
        manifest_digest=ledger.manifest.digest,
        path_policy_id="P1",
        path_policy_measurements_digest="1" * 64,
        p0_non_recall_justification=None,
        topology_id=topology_id,
        topology_measurements_digest="2" * 64,
        freshness_receipt_digest="3" * 64,
        reproducibility_receipt_digest="4" * 64,
        comparative=ComparativeEvidence(
            metrics={
                "critical_path_recall": {"baseline": 1.0, "zoekt": 1.0},
                "time_to_first_useful_ms": {"baseline": 100.0, "zoekt": 100.0},
            },
            measurement_digest="5" * 64,
        ),
        safety_complete=True,
        correctness_complete=True,
        freshness_complete=True,
        reproducibility_complete=True,
        path_policy_complete=True,
        topology_complete=True,
        constitutional_failure=False,
    )


def test_final_decision_requires_complete_real_evidence_and_never_uses_caller_safe_boolean() -> None:
    """Tie evidence chooses baseline; only complete actual no-safe evidence can emit no-safe."""

    ledger, answer_keys = _complete_real_ledger()
    assert build_decision_from_evidence(
        ledger.freeze(), ledger=ledger, evaluation_manifest=ledger.manifest, answer_keys=answer_keys
    ) is None

    ledger.record_decision_evidence(_decision_evidence(ledger))
    evidence = ledger.freeze()
    assert evidence.state == "ELIGIBLE_REAL_EMPIRICAL_EVIDENCE"
    assert evidence.decision is None
    assert build_decision_from_evidence(
        evidence, ledger=ledger, evaluation_manifest=ledger.manifest, answer_keys=answer_keys
    ) == "ZOEKT_REQUIRES_ARCHITECTURE_REVISION"

    no_safe, no_safe_keys = _complete_real_ledger()
    no_safe.record_decision_evidence(_decision_evidence(no_safe, topology_id="NO_SAFE_TOPOLOGY"))
    assert build_decision_from_evidence(
        no_safe.freeze(),
        ledger=no_safe,
        evaluation_manifest=no_safe.manifest,
        answer_keys=no_safe_keys,
    ) == "NO_SAFE_GLOBAL_INDEX"


@pytest.mark.parametrize("mutation", ["subset", "query_index", "normalized_arguments"])
def test_receipt_drift_is_refused_before_grading(mutation: str) -> None:
    """A valid-looking receipt cannot describe a different query or source subset."""

    ledger = _ledger()
    _publish_generation(ledger)
    plans = _plans(ledger)
    ledger.bind_query_plans(plans)
    plan = plans[ledger.manifest.queries[2].identity]
    payload = _query_payload(ledger, plan, "baseline")
    if mutation == "subset":
        statuses = payload["source_statuses"]
        assert isinstance(statuses, list)
        payload["source_statuses"] = statuses[:1]
    elif mutation == "query_index":
        payload["query_index"] = plan.query_index + 1
    else:
        payload["normalized_arguments_digest"] = "f" * 64

    with pytest.raises(QueryReceiptError, match="source_statuses|QueryPlan"):
        parse_normalized_query_receipt(payload, query_plan=plan)


def test_receipt_parser_rejects_mismatched_identity_and_non_authoritative_absence() -> None:
    """Schema-valid JSON cannot pick a mismatched trial identity or bless stale absence."""

    ledger = _ledger()
    plan = _plans(ledger)[ledger.manifest.queries[0].identity]
    wrong = _query_payload(ledger, plan, "baseline")
    wrong["query_identity"] = ledger.manifest.queries[1].identity
    with pytest.raises(QueryReceiptError, match="trial_id|QueryPlan"):
        parse_normalized_query_receipt(wrong, query_plan=plan)

    stale = _query_payload(ledger, plan, "baseline")
    statuses = stale["source_statuses"]
    assert isinstance(statuses, list) and isinstance(statuses[0], dict)
    statuses[0]["coverage"] = "PARTIALLY_COVERED"
    stale["zero_result_authority"] = "NONAUTHORITATIVE_COVERAGE_GAP"
    with pytest.raises(QueryReceiptError, match="zero_result_authority"):
        stale["zero_result_authority"] = "AUTHORITATIVE_NOT_FOUND_ON_HEALTHY_COVERED_EXACT_REF"
        parse_normalized_query_receipt(stale, query_plan=plan)


def test_keyed_source_statuses_close_zero_result_authority_one_to_one() -> None:
    """Only every exact requested source can make a three-repository zero authoritative."""

    ledger = _ledger()
    _publish_generation(ledger)
    plans = _plans(ledger)
    ledger.bind_query_plans(plans)
    plan = next(plan for plan in plans.values() if len(plan.logical_repo_ids) == 3)
    payload = _query_payload(ledger, plan, "baseline")
    payload["source_statuses"] = _source_statuses(ledger, plan)

    complete = parse_normalized_query_receipt(payload, query_plan=plan)
    assert complete.zero_result_authority == (
        "AUTHORITATIVE_NOT_FOUND_ON_HEALTHY_COVERED_EXACT_REF"
    )
    ledger.record_query_receipt(complete)

    missing = deepcopy(payload)
    missing["source_statuses"] = _source_statuses(ledger, plan)[:1]
    missing["zero_result_authority"] = "NONAUTHORITATIVE_SOURCE_SET_MISMATCH"
    with pytest.raises(QueryReceiptError, match="source_statuses"):
        parse_normalized_query_receipt(missing, query_plan=plan)

    stale = deepcopy(payload)
    statuses = stale["source_statuses"]
    assert isinstance(statuses, list) and isinstance(statuses[2], dict)
    statuses[2]["freshness"] = "SOURCE_MOVED_BEYOND_TARGET"
    stale["zero_result_authority"] = "NONAUTHORITATIVE_STALE_OR_MOVED"
    assert parse_normalized_query_receipt(stale, query_plan=plan).zero_result_authority == (
        "NONAUTHORITATIVE_STALE_OR_MOVED"
    )

    failed = deepcopy(payload)
    statuses = failed["source_statuses"]
    assert isinstance(statuses, list) and isinstance(statuses[2], dict)
    statuses[2]["health"] = "FAILED"
    failed["zero_result_authority"] = "NONAUTHORITATIVE_UNHEALTHY"
    assert parse_normalized_query_receipt(failed, query_plan=plan).zero_result_authority == (
        "NONAUTHORITATIVE_UNHEALTHY"
    )

    omitted = deepcopy(payload)
    statuses = omitted["source_statuses"]
    assert isinstance(statuses, list) and isinstance(statuses[2], dict)
    statuses[2]["coverage"] = "REPOSITORY_ABSENT"
    omitted["zero_result_authority"] = "NONAUTHORITATIVE_COVERAGE_GAP"
    assert parse_normalized_query_receipt(omitted, query_plan=plan).zero_result_authority == (
        "NONAUTHORITATIVE_COVERAGE_GAP"
    )

    duplicate = deepcopy(payload)
    statuses = duplicate["source_statuses"]
    assert isinstance(statuses, list)
    statuses[2] = deepcopy(statuses[1])
    with pytest.raises(QueryReceiptError, match="duplicate"):
        parse_normalized_query_receipt(duplicate, query_plan=plan)

    wrong_order = deepcopy(payload)
    statuses = wrong_order["source_statuses"]
    assert isinstance(statuses, list)
    statuses[1], statuses[2] = statuses[2], statuses[1]
    wrong_order["zero_result_authority"] = "NONAUTHORITATIVE_SOURCE_SET_MISMATCH"
    with pytest.raises(QueryReceiptError, match="source_statuses"):
        parse_normalized_query_receipt(wrong_order, query_plan=plan)

    mixed_generation = deepcopy(payload)
    statuses = mixed_generation["source_statuses"]
    assert isinstance(statuses, list) and isinstance(statuses[2], dict)
    statuses[2]["generation_id"] = "g1"
    with pytest.raises(QueryReceiptError, match="generation"):
        parse_normalized_query_receipt(mixed_generation, query_plan=plan)


@pytest.mark.parametrize(
    "field, replacement",
    [
        ("logical_repository", "unregistered-mirror"),
        ("requested_ref", "other-ref"),
        ("requested_commit", "f" * 40),
        ("requested_tree", "e" * 40),
        ("indexed_commit", "d" * 40),
        ("indexed_tree", "c" * 40),
        ("canonical_repository_digest", "b" * 64),
    ],
)
def test_source_statuses_must_bind_the_exact_query_plan_and_corpus(
    field: str, replacement: str
) -> None:
    """A keyed source row cannot substitute another ref, SHA, tree, or repository."""

    ledger = _ledger()
    _publish_generation(ledger)
    plans = _plans(ledger)
    ledger.bind_query_plans(plans)
    plan = next(plan for plan in plans.values() if len(plan.logical_repo_ids) == 3)
    payload = _query_payload(ledger, plan, "baseline")
    payload["source_statuses"] = _source_statuses(ledger, plan)
    statuses = payload["source_statuses"]
    assert isinstance(statuses, list) and isinstance(statuses[2], dict)
    statuses[2][field] = replacement

    if field in {"requested_commit", "requested_tree", "indexed_commit", "indexed_tree"}:
        payload["zero_result_authority"] = "NONAUTHORITATIVE_IDENTITY_UNKNOWN"

    if field in {"logical_repository", "requested_ref"}:
        with pytest.raises(QueryReceiptError, match="source_statuses"):
            parse_normalized_query_receipt(payload, query_plan=plan)
    else:
        receipt = parse_normalized_query_receipt(payload, query_plan=plan)
        with pytest.raises(EvidenceError, match="source status|source identity"):
            ledger.record_query_receipt(receipt)


def test_synthetic_and_missing_receipts_remain_nondecision_evidence() -> None:
    """Unknown resource, a missing receipt, or synthetic work cannot become a final result."""

    synthetic = _ledger(run_kind="synthetic")
    _publish_generation(synthetic)
    assert synthetic.freeze().state.startswith("NON_DECISION")
    assert "MISSING_OR_UNEXPECTED_TRIALS" in synthetic.freeze().reasons

    resource = ResourceObservation(
        cpu_ms=UNKNOWN_RESOURCE,
        rss_bytes=UNKNOWN_RESOURCE,
        disk_bytes=UNKNOWN_RESOURCE,
    )
    assert resource.is_known is False


def test_failure_injection_receipts_remain_append_only_and_reject_free_labels() -> None:
    """Free-form injection labels cannot count as required failure evidence."""

    ledger = _ledger()
    with pytest.raises(EvidenceError, match="not preregistered"):
        ledger.record_failure_injection(
            FailureInjectionReceipt(
                failure_code="FABRICATED_LABEL",
                outcome="REJECTED",
                cleanup_state="SUCCEEDED",
                correction_of=None,
                evidence_digest="a" * 64,
            )
        )


def test_ledger_and_result_schemas_bind_repetition_level_receipts_and_nullable_nondecisions() -> None:
    """Schemas reject the retired case-only contract and incomplete final claims."""

    jsonschema = pytest.importorskip("jsonschema")
    ledger, _answer_keys_for_ledger = _complete_real_ledger()
    ledger.record_decision_evidence(_decision_evidence(ledger))
    ledger_schema = json.loads(_LEDGER_SCHEMA.read_text(encoding="utf-8"))
    result_schema = json.loads(_RESULT_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(ledger_schema)
    jsonschema.Draft202012Validator.check_schema(result_schema)
    ledger_validator = jsonschema.Draft202012Validator(ledger_schema)
    ledger_payload = ledger.to_payload()
    ledger_validator.validate(ledger_payload)

    keyed_query = next(
        item
        for item in ledger_payload["query_receipts"]
        if len(item["source_statuses"]) == 3
    )
    assert len(keyed_query["source_statuses"]) == 3
    paired_trial = next(
        item
        for item in ledger_payload["trial_receipts"]
        if item["trial_id"] == keyed_query["trial_id"]
    )
    assert paired_trial["query_receipt_digest"] == hashlib.sha256(
        _canonical(keyed_query)
    ).hexdigest()

    retired_unkeyed = json.loads(json.dumps(ledger_payload))
    queries = retired_unkeyed["query_receipts"]
    assert isinstance(queries, list) and isinstance(queries[0], dict)
    queries[0].pop("source_statuses")
    queries[0].update(
        {
            "requested_sources": [],
            "coverage": ["FULLY_COVERED"],
            "health": ["HEALTHY"],
            "freshness": ["EXACT_SHA_CURRENT"],
        }
    )
    with pytest.raises(jsonschema.ValidationError):
        ledger_validator.validate(retired_unkeyed)

    case_only_trial = json.loads(json.dumps(ledger_payload))
    trials = case_only_trial["trial_receipts"]
    assert isinstance(trials, list) and isinstance(trials[0], dict)
    trials[0]["trial_id"] = "E1:baseline"
    with pytest.raises(jsonschema.ValidationError):
        ledger_validator.validate(case_only_trial)

    evidence = ledger.freeze().to_result_payload()
    result = {
        "schema_version": "mastermind.codeintel_z0_result.v1",
        "decision": "ZOEKT_REQUIRES_ARCHITECTURE_REVISION",
        "generated_at": "2026-09-03T00:00:00+00:00",
        "manifest_digest": ledger.manifest.digest,
        "source_census_digest": "a" * 64,
        "path_policy_digest": ledger.manifest.path_policy_rules[
            "policy_document_digest"
        ],
        "tool_schema_digest": "b" * 64,
        "zoekt_source_commit": "c" * 40,
        "binary_digests": {
            "zoekt_git_index": "d" * 64,
            "zoekt_webserver": "e" * 64,
            "go_toolchain": "f" * 64,
            "module_graph": "0" * 64,
            "ctags_disposition": "1" * 64,
            "configuration": "2" * 64,
            "sandbox": "3" * 64,
        },
        "source_bundle": {
            "protected_source": dict(ledger.manifest.protected_source),
            "authority_blobs": dict(ledger.manifest.authority_blobs),
            "real_preregistration_digest": ledger.manifest.real_preregistration_digest,
            "corpus": [dict(row) for row in ledger.manifest.corpus],
            "active_generation_id": ledger.active_generation_id,
        },
        "repository_statuses": [
            {
                "logical_repo_id": receipt.logical_repo_id,
                "canonical_repository": next(
                    row["canonical_repository"]
                    for row in ledger.manifest.corpus
                    if row["logical_repo_id"] == receipt.logical_repo_id
                ),
                "ref": next(
                    row["ref"]
                    for row in ledger.manifest.corpus
                    if row["logical_repo_id"] == receipt.logical_repo_id
                ),
                "source_commit": receipt.source_commit,
                "source_tree": receipt.source_tree,
                "indexed_commit_sha": receipt.indexed_commit_sha,
                "shard_digest": receipt.shard_digest,
                "generation_id": receipt.generation_id,
                "status": receipt.status,
            }
            for receipt in ledger.generation_receipts
        ],
        "resource_observations": {
            "generation_receipts_digest": "4" * 64,
            "query_receipts_digest": "5" * 64,
            "failure_injection_receipts_digest": "6" * 64,
        },
        "evaluation_evidence": evidence,
    }
    result_validator = jsonschema.Draft202012Validator(result_schema)
    result_validator.validate(result)

    incomplete = json.loads(json.dumps(result))
    incomplete["decision"] = None
    incomplete_evidence = incomplete["evaluation_evidence"]
    assert isinstance(incomplete_evidence, dict)
    incomplete_evidence.update(
        {
            "state": "NON_DECISION",
            "run_kind": "synthetic",
            "active_generation_id": None,
            "required_trial_count": 0,
            "recorded_trial_count": 0,
            "failed_trial_count": 0,
            "required_failure_injection_count": 0,
            "recorded_failure_injection_count": 0,
            "all_resources_known": False,
            "all_identity_bound": False,
            "decision": None,
            "decision_evidence": None,
            "reasons": ["SYNTHETIC_EVIDENCE"],
        }
    )
    result_validator.validate(incomplete)

    missing_topology = json.loads(json.dumps(result))
    final_evidence = missing_topology["evaluation_evidence"]
    assert isinstance(final_evidence, dict)
    decision_evidence = final_evidence["decision_evidence"]
    assert isinstance(decision_evidence, dict)
    del decision_evidence["topology_measurements_digest"]
    with pytest.raises(jsonschema.ValidationError):
        result_validator.validate(missing_topology)


def _sealed_runtime_inputs(
    tmp_path: Path,
) -> tuple[object, dict[str, AnswerKey], IndexManifest, SourceCensus]:
    """Build a type-correct sealed input set whose answer keys bind its census."""

    fixture_payload = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    fixture_corpus = fixture_payload["corpus"]
    assert isinstance(fixture_corpus, list)
    index_rows: list[dict[str, object]] = []
    observed_sources: dict[str, tuple[str, str]] = {}
    for row in fixture_corpus:
        assert isinstance(row, dict)
        logical_repo_id = str(row["logical_repo_id"])
        root = tmp_path / logical_repo_id
        root.mkdir()
        for args in (
            ("init", "-q", "-b", "main"),
            ("config", "user.name", "CodeIntel test"),
            ("config", "user.email", "codeintel@example.invalid"),
            (
                "remote",
                "add",
                "origin",
                f"git@github.com:{row['canonical_repository']}.git",
            ),
        ):
            subprocess.run(["git", "-C", str(root), *args], check=True)
        engine = root / "engine"
        engine.mkdir()
        (engine / "sealed.py").write_text(
            f"SEALED_{logical_repo_id.replace('-', '_').upper()} = 1\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-qm", "sealed source"], check=True
        )
        commit = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
        tree = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], text=True
        ).strip()
        observed_sources[logical_repo_id] = (commit, tree)
        index_rows.append(
            {
                "repository_id": logical_repo_id,
                "repository_name": row["canonical_repository"],
                "source_snapshot_root": str(root),
                "ref_label": row["ref"],
                "commit_sha": commit,
                "included_prefixes": ["engine/**"],
                "excluded_globs": [],
                "source_tree_digest": source_tree_digest(root, ("engine/**",), ()),
            }
        )
    index_path = tmp_path / "index-manifest.json"
    index_path.write_text(
        json.dumps(
            {
                "schema_version": "mastermind.codeintel_index_manifest.v1",
                "repositories": index_rows,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    index_manifest = load_index_manifest(index_path)
    census = census_sealed_sources(index_manifest)
    source_census_digest = census.digest
    source_ledger = _ledger()
    base_keys = _answer_keys(source_ledger)
    payload = fixture_payload
    corpus = payload["corpus"]
    assert isinstance(corpus, list)
    for index, row in enumerate(corpus):
        assert isinstance(row, dict)
        commit, tree = observed_sources[str(row["logical_repo_id"])]
        row.update(
            {
                "commit": commit,
                "tree": tree,
                "blob_census_digest": hashlib.sha256(
                    f"{source_census_digest}:{row['logical_repo_id']}".encode("utf-8")
                ).hexdigest(),
                "include_exclude_policy_digest": hashlib.sha256(
                    f"include:{index}".encode("utf-8")
                ).hexdigest(),
                "submodule_lfs_generated_vendor_oversize_disposition_digest": hashlib.sha256(
                    f"disposition:{index}".encode("utf-8")
                ).hexdigest(),
            }
        )
    answer_keys: dict[str, AnswerKey] = {}
    queries = payload["queries"]
    assert isinstance(queries, list)
    for query in queries:
        assert isinstance(query, dict)
        identity = ":".join(
            (
                str(query["case_id"]),
                str(query["family"]),
                str(query["repetition_index"]),
                str(query["warm_or_cold"]),
                str(query["query_index"]),
            )
        )
        original = json.loads(base_keys[identity].canonical_bytes)
        original["census_digest"] = source_census_digest
        canonical = _canonical(original)
        answer_key = AnswerKey(
            case_id=str(query["case_id"]),
            expected_identities=(),
            forbidden_identities=(),
            canonical_bytes=canonical,
            digest=hashlib.sha256(canonical).hexdigest(),
            path_policy_digest=str(original["path_policy_digest"]),
        )
        answer_keys[identity] = answer_key
        query["answer_key_digest"] = answer_key.digest
    manifest = parse_evaluation_manifest(_canonical(payload))
    return manifest, answer_keys, index_manifest, census


def _captured_evaluation(
    tmp_path: Path,
) -> tuple[object, dict[str, AnswerKey], IndexManifest, SourceCensus, CapturedEvaluation, EvaluationBundleIdentity]:
    """Construct pure captured receipts; no adapter runs a process or touches disk."""

    manifest, answer_keys, index_manifest, census = _sealed_runtime_inputs(tmp_path)
    assert hasattr(manifest, "queries")
    ledger = EvaluationLedger(
        manifest,  # type: ignore[arg-type]
        run_kind="real",
        source_census_digest=census.digest,
    )
    _publish_generation(ledger)
    plans = {
        query.identity: build_query_plan(manifest, query, answer_keys[query.identity])  # type: ignore[arg-type]
        for query in manifest.queries  # type: ignore[union-attr]
    }
    adapters: dict[str, CapturedCandidateAdapter] = {}
    for candidate in ("baseline", "zoekt"):
        transports: dict[str, CandidateTransport] = {}
        for plan in plans.values():
            payload = _query_payload(ledger, plan, candidate)
            identity = payload["index_identity"]
            assert isinstance(identity, dict)
            identity.update(
                {
                    "source_epoch_digest": census.digest,
                    "zoekt_source_commit": "c" * 40,
                    "zoekt_binary_digest": "d" * 64,
                    "go_toolchain_digest": "e" * 64,
                    "module_graph_digest": "f" * 64,
                    "ctags_disposition_digest": "0" * 64,
                    "configuration_digest": "1" * 64,
                    "sandbox_digest": "2" * 64,
                }
            )
            transports[plan.query_identity] = CandidateTransport(payload)
        adapters[candidate] = CapturedCandidateAdapter(candidate, transports)
    failures = tuple(
        FailureInjectionReceipt(
            failure_code=injection_id,
            outcome="REJECTED",
            cleanup_state="SUCCEEDED",
            correction_of=None,
            evidence_digest=hashlib.sha256(injection_id.encode("utf-8")).hexdigest(),
            execution=FailureExecutionReceipt(
                injection_id=injection_id,
                expected_failure_code="PROCESS_CRASH",
                observed_failure_code="PROCESS_CRASH",
                expected_effect="PUBLISH_REFUSED",
                observed_effect="PUBLISH_REFUSED",
                cleanup_state="SUCCEEDED",
                execution_receipt_digest=hashlib.sha256(
                    injection_id.encode("utf-8")
                ).hexdigest(),
            ),
        )
        for injection_id in manifest.failure_injections  # type: ignore[union-attr]
    )
    capture = CapturedEvaluation(
        generation_id="g0",
        generation_receipts=ledger.generation_receipts,
        baseline=adapters["baseline"],
        zoekt=adapters["zoekt"],
        failure_injection_receipts=failures,
        decision_evidence=_decision_evidence(ledger),
    )
    bundle = EvaluationBundleIdentity(
        zoekt_source_commit="c" * 40,
        zoekt_git_index_digest="d" * 64,
        zoekt_webserver_digest="d" * 64,
        go_toolchain_digest="e" * 64,
        module_graph_digest="f" * 64,
        ctags_disposition_digest="0" * 64,
        configuration_digest="1" * 64,
        sandbox_digest="2" * 64,
        tool_schema_digest="3" * 64,
    )
    return manifest, answer_keys, index_manifest, census, capture, bundle


def test_real_orchestrator_emits_immutable_captured_evidence_without_host_effects(
    tmp_path: Path,
) -> None:
    """The public real-run path accepts only sealed inputs and captured adapter receipts."""

    manifest, answer_keys, index_manifest, census, capture, bundle = _captured_evaluation(
        tmp_path
    )
    entries_before_run = sorted(path.name for path in tmp_path.iterdir())
    artifacts = run_empirical_evaluation(
        manifest,  # type: ignore[arg-type]
        index_manifest=index_manifest,
        source_census=census,
        answer_keys=answer_keys,
        bundle=bundle,
        capture=capture,
        generated_at="2026-09-03T00:00:00+00:00",
    )

    ledger_payload = json.loads(artifacts.ledger_bytes)
    result_payload = json.loads(artifacts.result_bytes)
    assert artifacts.decision == "ZOEKT_REQUIRES_ARCHITECTURE_REVISION"
    assert artifacts.ledger_digest == hashlib.sha256(artifacts.ledger_bytes).hexdigest()
    assert artifacts.result_digest == hashlib.sha256(artifacts.result_bytes).hexdigest()
    assert ledger_payload["run_kind"] == "real"
    assert len(ledger_payload["trial_receipts"]) == len(manifest.trial_order)  # type: ignore[union-attr]
    assert result_payload["source_bundle"]["active_generation_id"] == "g0"
    assert result_payload["binary_digests"]["zoekt_webserver"] == "d" * 64
    assert result_payload["resource_observations"]["query_receipts_digest"] == hashlib.sha256(
        _canonical(ledger_payload["query_receipts"])
    ).hexdigest()
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft202012Validator(
        json.loads(_LEDGER_SCHEMA.read_text(encoding="utf-8"))
    ).validate(ledger_payload)
    jsonschema.Draft202012Validator(
        json.loads(_RESULT_SCHEMA.read_text(encoding="utf-8"))
    ).validate(result_payload)
    assert sorted(path.name for path in tmp_path.iterdir()) == entries_before_run


def test_real_orchestrator_preserves_a_bundle_mismatch_as_nondecision_evidence(
    tmp_path: Path,
) -> None:
    """A captured receipt cannot be relabeled with a different Zoekt binary identity."""

    manifest, answer_keys, index_manifest, census, capture, bundle = _captured_evaluation(
        tmp_path
    )
    artifacts = run_empirical_evaluation(
        manifest,  # type: ignore[arg-type]
        index_manifest=index_manifest,
        source_census=census,
        answer_keys=answer_keys,
        bundle=replace(bundle, zoekt_webserver_digest="f" * 64),
        capture=capture,
        generated_at="2026-09-03T00:00:00+00:00",
    )

    assert artifacts.decision is None
    assert artifacts.evidence.state == "NON_DECISION"
    assert "QUERY_RECEIPT_NORMALIZATION_FAILURE" in artifacts.evidence.reasons


def test_real_orchestrator_rechecks_the_parent_sealed_source_before_accepting_capture(
    tmp_path: Path,
) -> None:
    """A stale caller census cannot hide a source mutation after the host capture."""

    manifest, answer_keys, index_manifest, census, capture, bundle = _captured_evaluation(
        tmp_path
    )
    moved_source = index_manifest.repositories[0].source_snapshot_root / "engine" / "sealed.py"
    moved_source.write_text("SEALED_MUTATED = 2\n", encoding="utf-8")

    with pytest.raises(EvidenceError, match="source seal"):
        run_empirical_evaluation(
            manifest,  # type: ignore[arg-type]
            index_manifest=index_manifest,
            source_census=census,
            answer_keys=answer_keys,
            bundle=bundle,
            capture=capture,
            generated_at="2026-09-03T00:00:00+00:00",
        )
