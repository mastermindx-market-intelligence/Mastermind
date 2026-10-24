"""Routing validation measurements are evidence, not executable identity defaults.

Uses the existing D8 classifiers unchanged. No scanner exemption, native source
change or provider operation is involved; the original native proof stays held.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.test_ceo_submit_armed_composition import (
    _identity_guard_evidence_json_path,
    _identity_guard_source_path,
    _scan_evidence_identity_literals,
    _scan_identity_source_lines,
    _semantic_words,
    _SOURCE_IDENTITY_WORDS,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "ops/native_fabric/routing_audit_20261013/account_balance/manifest.json"
EVIDENCE = "research/evidence/fabric_routing_validation_20261015.json"


def test_source_manifest_does_not_encode_measurements_as_identity_defaults():
    source = (ROOT / MANIFEST).read_text(encoding="utf-8")
    assert _identity_guard_source_path(MANIFEST)
    assert _scan_identity_source_lines(
        source.splitlines(),
        path_identity=bool(_semantic_words(MANIFEST) & _SOURCE_IDENTITY_WORDS),
    ) == []


def test_validation_evidence_is_hash_bound_and_preserves_measured_counts():
    manifest = json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))
    reference = manifest["verification"]["measurement_evidence"]
    assert reference["path"] == EVIDENCE
    content = (ROOT / EVIDENCE).read_bytes()
    assert hashlib.sha256(content).hexdigest() == reference["sha256"]
    assert _identity_guard_evidence_json_path(EVIDENCE)
    assert not _identity_guard_source_path(EVIDENCE)
    assert _scan_evidence_identity_literals(content.decode("utf-8")) == []
    evidence = json.loads(content)
    assert evidence["source_head"] == "d47c54a46e7e20baa42d18c0a12f8eef09c2a0db"
    measured = evidence["measurements"]
    assert measured["capacity_matrix"]["cases"] == 400
    assert measured["capacity_matrix"]["unit"] == "synthetic eligible-capacity combinations"
    assert measured["capacity_matrix"]["included_in_suite_count"] is True
    assert measured["combined_source_suite"]["passed"] == 89
    assert sum(measured["combined_source_suite"]["breakdown"].values()) == 89
    assert measured["combined_source_suite"]["failed"] == 0
    assert measured["capacity_selection_suite"] == {
        "before": {"failed": 15, "passed": 15},
        "after": {"passed": 30, "failed": 0},
    }
    assert evidence["scope"]["full_native_regression"] is False
    assert evidence["scope"]["independent_review"] is False
    assert evidence["scope"]["production_proof"] is False
    assert evidence["scope"]["original_native_suite"] == {"passed": 49, "failed": 1}


@pytest.mark.parametrize("key", ["uid", "worker_uid", "allowedPeerUIDs", "account", "owner"])
def test_measurement_path_does_not_exempt_identity_values(key):
    assert _scan_evidence_identity_literals(json.dumps({key: 400})) == ["400"]


def test_original_source_literal_still_trips_guard():
    assert _scan_identity_source_lines(
        ['"account_capacity_cases_inside_suite": 400,'], path_identity=True,
    ) == ["400"]


@pytest.mark.parametrize("document", [
    '{"metrics": 1, "metrics": 2}', '{"metrics": NaN}', '[]',
])
def test_invalid_measurement_evidence_is_not_accepted(document):
    with pytest.raises(AssertionError):
        _scan_evidence_identity_literals(document)


@pytest.mark.parametrize("path", [
    "ops/native_fabric/evidence.json", "research/evidence/../config.json",
    "/research/evidence/proof.json", "research/evidence/proof.py",
])
def test_evidence_route_remains_path_and_format_scoped(path):
    assert not _identity_guard_evidence_json_path(path)
    assert _identity_guard_source_path(path)
