"""Strict preregistration tests for the Z0 paired-evaluation manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from experiments.code_discovery.baseline_search import AnswerKey
from experiments.code_discovery.evaluation_manifest import (
    EvaluationManifestError,
    load_evaluation_manifest,
    load_real_evaluation_preregistration,
    materialize_real_evaluation_manifest,
    parse_evaluation_manifest,
    parse_real_evaluation_preregistration,
)


_FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "code_discovery"
    / "evaluation-manifest.v1.json"
)
_EPOCH1_PREREGISTRATION = (
    Path(__file__).parent.parent.parent
    / "research"
    / "code_intelligence_fabric"
    / "Z0_REAL_EVALUATION_EPOCH1_PREREGISTRATION.json"
)


def _payload() -> dict[str, object]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _document(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


def test_manifest_canonicalizes_frozen_identity_and_experiment_inputs() -> None:
    """Changing canonical bytes must change the immutable evidence identity."""

    manifest = load_evaluation_manifest(_FIXTURE)
    expected = _document(_payload())

    assert manifest.canonical_bytes == expected
    assert manifest.digest == hashlib.sha256(expected).hexdigest()
    assert manifest.operation_key == "mastermind-codeintel-z0-empirical-evidence-source-20260903-sol-001"
    assert {query.case_id for query in manifest.queries} == {"E1", "X3", "R3", "A1"}
    assert manifest.path_policy_candidates == ("P0", "P1", "P2")


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (
            b'{"schema_version":"mastermind.codeintel_evaluation_manifest.v1",'
            b'"schema_version":"mastermind.codeintel_evaluation_manifest.v1"}',
            "duplicate JSON key",
        ),
        (b'{"schema_version":NaN}', "non-finite JSON constant"),
    ],
)
def test_manifest_rejects_ambiguous_or_nonfinite_json(
    document: bytes, message: str
) -> None:
    """A parser that silently accepts either condition can bless altered evidence."""

    with pytest.raises(EvaluationManifestError, match=message):
        parse_evaluation_manifest(document)


def test_manifest_rejects_missing_frozen_fields_and_out_of_budget_trials() -> None:
    """Dropping a gate or widening a trial budget must invalidate preregistration."""

    missing = _payload()
    del missing["hard_failure_rules_digest"]
    with pytest.raises(EvaluationManifestError, match="missing fields"):
        parse_evaluation_manifest(_document(missing))

    widened = _payload()
    queries = widened["queries"]
    assert isinstance(queries, list)
    assert isinstance(queries[0], dict)
    queries[0]["max_results"] = 101
    with pytest.raises(EvaluationManifestError, match="max_results"):
        parse_evaluation_manifest(_document(widened))


def test_manifest_freezes_and_validates_nested_resource_envelopes() -> None:
    """A mutable or negative nested budget could rewrite the experiment after review."""

    manifest = load_evaluation_manifest(_FIXTURE)
    with pytest.raises(TypeError):
        manifest.resource_envelopes["T0"]["max_cpu_ms"] = 0  # type: ignore[index]

    malformed = _payload()
    envelopes = malformed["resource_envelopes"]
    assert isinstance(envelopes, dict)
    assert isinstance(envelopes["T0"], dict)
    envelopes["T0"]["max_cpu_ms"] = -1
    with pytest.raises(EvaluationManifestError, match="resource_envelopes"):
        parse_evaluation_manifest(_document(malformed))


def test_epoch1_preregistration_is_exact_canonical_and_non_decisive_input() -> None:
    """A changed or reformatted Epoch 1 record must not seed a later real run."""

    raw = _EPOCH1_PREREGISTRATION.read_bytes()
    preregistration = load_real_evaluation_preregistration(_EPOCH1_PREREGISTRATION)

    assert len(raw) == 21_052
    assert preregistration.canonical_bytes == raw
    assert preregistration.digest == (
        "ba88036fe2a8e7ae9dcd1feaa30e5e88aa7b381ca2a01c4f26000799f02a7eeb"
    )
    assert preregistration.source_epoch["mastermind"]["commit"] == (
        "762f993e2f1af467d95e54aaa99796f20c24c2e0"
    )
    assert preregistration.source_epoch["macro"]["commit"] == (
        "0795a15b0249110a7eb35439123cd1af755e8397"
    )
    assert preregistration.source_epoch["terminal"]["commit"] == (
        "fadd8b82f03ecaabe8a86d693da89f27be096d9f"
    )
    assert len(preregistration.queries) == 20
    assert preregistration.required_trial_count == 40
    assert preregistration.required_failure_injection_count == 21
    assert preregistration.incomplete_state == "NON_DECISION"
    assert preregistration.incomplete_decision is None

    mutated = bytearray(raw)
    mutated[-1] ^= 1
    with pytest.raises(EvaluationManifestError):
        parse_real_evaluation_preregistration(bytes(mutated))


def test_epoch1_materializer_binds_answer_keys_and_policy_to_the_frozen_payload() -> None:
    """The generic harness can construct, but not execute, the exact Epoch 1 study."""

    preregistration = load_real_evaluation_preregistration(_EPOCH1_PREREGISTRATION)
    source_census_digest = "a" * 64
    policy_digest = "b" * 64
    corpus = [
        {
            "logical_repo_id": logical_id,
            "canonical_repository": source["repository"],
            "ref": source["ref"],
            "commit": source["commit"],
            "tree": source["tree"],
            "blob_census_digest": f"{index + 1:x}" * 64,
            "include_exclude_policy_digest": f"{index + 4:x}" * 64,
            "submodule_lfs_generated_vendor_oversize_disposition_digest": f"{index + 7:x}" * 64,
        }
        for index, (logical_id, source) in enumerate(sorted(preregistration.source_epoch.items()))
    ]
    answer_keys: dict[str, AnswerKey] = {}
    for raw_query in preregistration.queries:
        case_id = raw_query["case_id"]
        family = raw_query["family"]
        warm = str(raw_query["warm_or_cold"]).lower()
        query_index = raw_query["query_index"]
        repetition = raw_query["repetition_index"]
        assert isinstance(case_id, str) and isinstance(family, str)
        assert type(query_index) is int and type(repetition) is int
        identity = f"{case_id}:{family}:{repetition}:{warm}:{query_index}"
        logical_repo_ids = list(raw_query["logical_repo_ids"])
        refs = raw_query["refs"]
        assert isinstance(refs, dict) or hasattr(refs, "items")
        canonical = _document(
            {
                "case_id": case_id,
                "census_digest": source_census_digest,
                "path_policy_digest": policy_digest,
                "query": {
                    "query": raw_query["query"],
                    "regex": raw_query["regex"],
                    "case_sensitive": raw_query["case_sensitive"],
                    "repository_ids": logical_repo_ids,
                    "refs": [refs[logical_id] for logical_id in logical_repo_ids],  # type: ignore[index]
                    "path_prefixes": list(raw_query["path_prefixes"]),
                    "languages": list(raw_query["languages"]),
                    "limit": raw_query["max_results"],
                    "context_lines": raw_query["max_context_lines"],
                    "timeout_ms": raw_query["timeout_ms"],
                },
                "expected": [],
                "forbidden": [],
            }
        )
        answer_keys[identity] = AnswerKey(
            case_id=case_id,
            expected_identities=(),
            forbidden_identities=(),
            canonical_bytes=canonical,
            digest=hashlib.sha256(canonical).hexdigest(),
            path_policy_digest=policy_digest,
        )
    protected_source = {
        "repository": preregistration.source_epoch["mastermind"]["repository"],
        "commit": preregistration.source_epoch["mastermind"]["commit"],
        "tree": preregistration.source_epoch["mastermind"]["tree"],
        "skillpack_index_blob": preregistration.authority["skillpack_index_blob"],
    }
    authority_blobs = {
        "f0": preregistration.authority["f0_blob"],
        "language_amendment": preregistration.authority["language_deployment_blob"],
        "z0_plan": preregistration.authority["z0_plan_blob"],
    }
    path_policy_rules = {
        "policy_document_digest": policy_digest,
        "p0_allowed_non_recall_justifications": [
            "cross_repo_trace_required_by_preregistered_case"
        ],
    }

    manifest = materialize_real_evaluation_manifest(
        preregistration,
        protected_source=protected_source,
        authority_blobs=authority_blobs,
        corpus=corpus,
        source_census_digest=source_census_digest,
        answer_keys=answer_keys,
        path_policy_rules=path_policy_rules,
    )

    assert manifest.real_preregistration_digest == preregistration.digest
    assert len(manifest.queries) == 20
    assert len(manifest.trial_order) == 40
    assert manifest.failure_injections == preregistration.failure_injections
    assert {query.case_id for query in manifest.queries} == {"E1", "X3", "R3", "A1", "T1"}

    with pytest.raises(EvaluationManifestError, match="path policy"):
        materialize_real_evaluation_manifest(
            preregistration,
            protected_source=protected_source,
            authority_blobs=authority_blobs,
            corpus=corpus,
            source_census_digest=source_census_digest,
            answer_keys=answer_keys,
            path_policy_rules={
                **path_policy_rules,
                "policy_document_digest": "c" * 64,
            },
        )
