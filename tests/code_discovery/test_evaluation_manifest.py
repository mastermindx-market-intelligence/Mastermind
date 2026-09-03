"""Strict preregistration tests for the Z0 paired-evaluation manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from experiments.code_discovery.evaluation_manifest import (
    EvaluationManifestError,
    load_evaluation_manifest,
    parse_evaluation_manifest,
)


_FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "code_discovery"
    / "evaluation-manifest.v1.json"
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
