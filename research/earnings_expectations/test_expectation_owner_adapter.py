"""Fail-closed read-only integration contract with current Macro K3E/EXP-1 source."""
from copy import deepcopy
import json

import pytest

from expectation_owner_adapter import (
    OBS_PATH, ATT_PATH, OWNER_SCHEMA, OwnerContractError,
    _canonical_digest, project_owner_inspection,
)


def owner_document():
    query = {
        "provider": "yfinance",
        "ticker_compat": "GOOGL",
        "metric": "EPS",
        "horizon_label_raw": "0q",
        "as_of": "2026-10-02T12:00:00Z",
    }
    source = {
        "source_revision": "a" * 40,
        "inputs": {
            OBS_PATH: {"sha256": "b" * 64, "git_blob_id": "c" * 40},
            ATT_PATH: {"sha256": "d" * 64, "git_blob_id": "e" * 40},
        },
    }
    payload = {
        "schema": OWNER_SCHEMA,
        "query": query,
        "source": source,
        "query_identity": _canonical_digest(
            {"schema": OWNER_SCHEMA, "query": query, "source": source}
        ),
        "historical_public_availability_verified": False,
        "historical_repository_visibility_verified": False,
        "identity_gate": {
            "contract": "k3e.identity_gate.v1",
            "status": "NOT_CHECKED",
        },
        "normalized_baseline": {
            "value": None,
            "status": "UNESTIMABLE",
            "reasons": [
                "NORMALIZED_CONSUMER_ADMISSION_NOT_GRANTED",
                "SOURCE_USE_RIGHTS_UNKNOWN",
                "CANONICAL_BASIS_UNAVAILABLE",
            ],
            "rights_state": "UNKNOWN",
            "candidate_observation_id": "raw-observation-not-normalized",
        },
        "period_continuity": "SAME_NATIVE_PERIOD",
        "denominators": {
            "capture_clock_bounded_relevant_records": 2,
            "structurally_supported_estimate_records": 1,
        },
    }
    return {
        "semantic_payload": payload,
        "semantic_digest": _canonical_digest(payload),
        "composition_time": "2026-10-03T12:00:00Z",
        "input_provenance": {"historical_population": False},
    }


def recalc(doc):
    p = doc["semantic_payload"]
    doc["semantic_digest"] = _canonical_digest(p)
    return doc


def test_current_source_envelope_remains_unadmitted_without_copying_raw_value():
    witness = owner_document()
    projected = project_owner_inspection(witness, expected_asof="2026-10-02T12:00:00+00:00")
    assert projected["baseline_status"] == "UNESTIMABLE"
    assert projected["baseline_value"] is None
    assert projected["baseline_use"] == "NOT_ADMITTED"
    assert projected["rights_state"] == "UNKNOWN"
    assert projected["issuer_binding"] == "NOT_ESTABLISHED_BY_TICKER_COMPAT_ALONE"
    assert projected["capture_clock_bounded_relevant_records"] == 2
    assert "NORMALIZED_CONSUMER_ADMISSION_NOT_GRANTED" in projected["reason_codes"]
    assert "raw-observation-not-normalized" not in json.dumps(projected)
    assert projected["source_query_identity"] == witness["semantic_payload"]["query_identity"]
    assert projected["historical_public_availability_verified"] is False


@pytest.mark.parametrize(("status", "rights"), [
    ("UNAVAILABLE", "UNKNOWN"),
    ("RIGHTS_BLOCKED", "RIGHTS_BLOCKED"),
    ("STALE_UNAVAILABLE", "UNKNOWN"),
    ("WITHDRAWN_UNAVAILABLE", "UNKNOWN"),
])
def test_current_owner_unavailable_variants_are_preserved(status, rights):
    doc = owner_document()
    doc["semantic_payload"]["normalized_baseline"].update(status=status, rights_state=rights)
    out = project_owner_inspection(recalc(doc))
    assert out["baseline_status"] == status
    assert out["baseline_value"] is None


def test_digest_rejects_tampered_source_without_recomputed_receipt():
    doc = owner_document()
    doc["semantic_payload"]["normalized_baseline"]["status"] = "UNAVAILABLE"
    with pytest.raises(OwnerContractError, match="SOURCE_OWNER_DIGEST_MISMATCH"):
        project_owner_inspection(doc)


@pytest.mark.parametrize(("field", "value", "expected"), [
    ("normalized_baseline.value", 3.42, "NORMALIZED_BASELINE_PROMOTION_REQUIRES_NEW_CONTRACT"),
    ("normalized_baseline.status", "AVAILABLE", "SOURCE_BASELINE_NONADMISSION_INVALID"),
    ("normalized_baseline.reasons", [], "SOURCE_BASELINE_NONADMISSION_INVALID"),
    ("normalized_baseline.rights_state", "MODEL_TRAINING_LICENSED", "RIGHTS_GRANT_NOT_ESTABLISHED"),
    ("schema", "k3e.other_version", "SOURCE_OWNER_SCHEMA_UNSUPPORTED"),
    ("query.metric", "GOOGL", "SOURCE_METRIC_UNSUPPORTED"),
    ("query.as_of", "2026-10-02T12:00:00", "SOURCE_ASOF_UTC_REQUIRED"),
    ("source.source_revision", "master", "IMMUTABLE_SOURCE_REVISION_REQUIRED"),
    ("historical_public_availability_verified", True, "UNSUPPORTED_HISTORICAL_AVAILABILITY_CLAIM"),
    ("period_continuity", "REVISION_PROVEN", "SOURCE_PERIOD_CONTINUITY_UNSUPPORTED"),
    ("identity_gate.contract", "other", "SOURCE_IDENTITY_GATE_REQUIRED"),
    ("denominators.capture_clock_bounded_relevant_records", -1, "SOURCE_DENOMINATORS_INVALID"),
])
def test_unsafe_native_admission_refuses_even_with_fresh_digest(field, value, expected):
    doc = owner_document()
    part = doc["semantic_payload"]
    keys = field.split(".")
    for key in keys[:-1]:
        part = part[key]
    part[keys[-1]] = value
    if field.startswith("query."):
        p = doc["semantic_payload"]
        p["query_identity"] = _canonical_digest(
            {"schema": OWNER_SCHEMA, "query": p["query"], "source": p["source"]}
        )
    if field.startswith("source."):
        p = doc["semantic_payload"]
        p["query_identity"] = _canonical_digest(
            {"schema": OWNER_SCHEMA, "query": p["query"], "source": p["source"]}
        )
    with pytest.raises(OwnerContractError, match=expected):
        project_owner_inspection(recalc(doc))


def test_asof_mismatch_stops_cross_event_join():
    with pytest.raises(OwnerContractError, match="SOURCE_QUERY_ASOF_MISMATCH"):
        project_owner_inspection(owner_document(), expected_asof="2026-10-03T12:00:00Z")


def test_source_query_identity_must_match_underlying_native_query():
    doc = owner_document()
    doc["semantic_payload"]["query"]["ticker_compat"] = "MSFT"
    with pytest.raises(OwnerContractError, match="SOURCE_OWNER_QUERY_IDENTITY_MISMATCH"):
        project_owner_inspection(recalc(doc))


def test_raw_fiscal_anchor_not_upgraded_to_normalized_baseline():
    doc = owner_document()
    doc["semantic_payload"]["latest_captured_snapshot"] = {
        "snapshot": {"selected_observation": {
            "period_end": "2026-12-31", "value": 9999.0
        }}
    }
    out = project_owner_inspection(recalc(doc))
    assert out["baseline_value"] is None
    assert "9999" not in json.dumps(out)
