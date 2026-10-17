"""Closed, non-authoritative, point-in-time Portfolio V3 snapshot contracts."""
from copy import deepcopy
from importlib import import_module, util
from pathlib import Path
import pytest


def contract():
    name = "portfolio.decision_snapshot_contracts"
    assert util.find_spec(name) is not None, "missing Portfolio V3 snapshot contract"
    return import_module(name)


def receipt():
    c = contract()
    return {
        "schema": c.SOURCE_RECEIPT_SCHEMA, "source_id": "book.account",
        "domains": ["book_truth"], "producer": "mastermind_portfolio",
        "owner": "portfolio_desk", "artifact": "data/portfolios/autonomous/account.json",
        "source_schema": None, "schema_version": None, "definition_id": None,
        "artifact_digest": "sha256:" + "a" * 64, "observed_at": None,
        "known_at": "2026-09-15T20:00:00Z", "as_of": "2026-09-15",
        "generated_at": None, "filesystem_observed_at": "2026-09-15T20:00:00Z",
        "correction_generation": "sha256:" + "a" * 64, "freshness_state": "FRESH",
        "coverage_state": "COMPLETE", "rights_class": "FIRST_PARTY_INTERNAL",
        "authority_class": "BOOK_STATE", "status": "AVAILABLE", "required": True,
        "bytes": 120, "rows_total": 1, "rows_returned": 1, "omitted_rows": 0,
        "clock_basis": "FILE_MTIME_FIRST_PARTY_STATE", "error_code": None,
    }


def section():
    c = contract()
    return {
        "schema": c.SECTION_SCHEMA, "section_id": "book_truth",
        "coverage_state": "COMPLETE", "source_ids": ["book.account"],
        "rows_total": 1, "rows_returned": 1, "omitted_rows": 0,
        "rows": [{"kind": "account", "cash": 1000000.0, "positions": []}], "gaps": [],
    }


def unsealed():
    c = contract()
    return {
        "schema": c.SNAPSHOT_SCHEMA, "book": "autonomous",
        "decision_cutoff": "2026-09-15T20:00:00Z", "recorded_at": "2026-09-15T20:01:00Z",
        "state": "COMPLETE", "coverage_state": "COMPLETE",
        "summary": {"sources_total": 1, "sources_available": 1, "domains_complete": 1,
                    "domains_partial": 0, "domains_blocked": 0},
        "source_generation_set": [{"source_id": "book.account", "correction_generation": "sha256:" + "a" * 64}],
        "sources": [receipt()], "sections": {"book_truth": section()}, "gaps": [],
        "correction": {"status": "ORIGINAL", "same_cutoff_prior_snapshot_ids": []},
        "authority": {"write_permitted": False, "execution_authority": False, "numeric_target_authority": False},
    }


def test_seal_is_key_order_invariant_and_self_verifying():
    c = contract(); left = unsealed(); right = dict(reversed(list(left.items())))
    a = c.seal_snapshot(left); b = c.seal_snapshot(right)
    assert a == b and a["snapshot_id"].startswith("sha256:")
    c.verify_snapshot(a)
    assert "snapshot_id" not in left
    left["sections"]["book_truth"]["rows"][0]["cash"] = 0
    assert a["sections"]["book_truth"]["rows"][0]["cash"] == 1000000.0


@pytest.mark.parametrize("value", ["2026-09-15", "2026-09-15T20:00:00", "not-a-time", True, None])
def test_naive_or_invalid_clock_is_rejected(value):
    c = contract()
    with pytest.raises(c.DecisionSnapshotContractError):
        c.parse_utc_timestamp(value, field="decision_cutoff")


def test_aware_clock_is_normalized_to_utc():
    assert contract().parse_utc_timestamp("2026-09-15T16:00:00-04:00", field="cutoff") == "2026-09-15T20:00:00Z"


@pytest.mark.parametrize("target", ["root", "source", "section", "authority", "summary", "correction"])
@pytest.mark.parametrize("mode", ["extra", "missing"])
def test_closed_containers(target, mode):
    c = contract(); p = unsealed()
    obj = {"root": p, "source": p["sources"][0], "section": p["sections"]["book_truth"],
           "authority": p["authority"], "summary": p["summary"], "correction": p["correction"]}[target]
    if mode == "extra": obj["surprise"] = True
    else: obj.pop(next(iter(obj)))
    with pytest.raises(c.DecisionSnapshotContractError, match=mode if mode == "missing" else "unknown"):
        c.validate_unsealed_snapshot(p)


@pytest.mark.parametrize("value", [True, -1, 1.0, "1", None])
def test_counts_are_nonnegative_integers_not_booleans(value):
    c = contract(); r = receipt(); r["rows_returned"] = value
    with pytest.raises(c.DecisionSnapshotContractError): c.validate_source_receipt(r)


@pytest.mark.parametrize("field,value", [
    ("artifact_digest", "abc"), ("authority_class", "EXECUTION"),
    ("rights_class", "UNVERIFIED"), ("required", 1), ("status", "OK"),
    ("domains", ["book_truth", "book_truth"]), ("domains", ["unknown_domain"]),
    ("known_at", None), ("clock_basis", "UNKNOWN"), ("freshness_state", "STALE"),
])
def test_available_receipt_cannot_smuggle_invalid_or_unqualified_fields(field, value):
    c = contract(); r = receipt(); r[field] = value
    with pytest.raises(c.DecisionSnapshotContractError): c.validate_source_receipt(r)


@pytest.mark.parametrize("field,value", [("write_permitted", True), ("execution_authority", 0), ("numeric_target_authority", None)])
def test_snapshot_never_grants_any_authority(field, value):
    c = contract(); p = unsealed(); p["authority"][field] = value
    with pytest.raises(c.DecisionSnapshotContractError): c.seal_snapshot(p)


def test_available_future_source_is_not_admitted():
    c = contract(); p = unsealed(); p["sources"][0]["known_at"] = "2026-09-15T20:00:01Z"
    with pytest.raises(c.DecisionSnapshotContractError): c.seal_snapshot(p)


def test_recording_before_cutoff_is_rejected():
    c = contract(); p = unsealed(); p["recorded_at"] = "2026-09-15T19:59:00Z"
    with pytest.raises(c.DecisionSnapshotContractError): c.seal_snapshot(p)


@pytest.mark.parametrize("case", ["source_duplicate", "generation_duplicate", "generation_mismatch", "unknown_source", "wrong_domain", "summary", "wrong_book", "section_identity", "count_mismatch"])
def test_cross_reference_integrity(case):
    c = contract(); p = unsealed()
    if case == "source_duplicate": p["sources"].append(deepcopy(p["sources"][0]))
    elif case == "generation_duplicate": p["source_generation_set"] *= 2
    elif case == "generation_mismatch": p["source_generation_set"][0]["correction_generation"] = "sha256:" + "b" * 64
    elif case == "unknown_source": p["sections"]["book_truth"]["source_ids"] = ["not.registered"]
    elif case == "wrong_domain": p["sources"][0]["domains"] = ["risk_truth"]
    elif case == "summary": p["summary"]["sources_total"] = 2
    elif case == "wrong_book": p["book"] = "../self_directed"
    elif case == "section_identity": p["sections"]["book_truth"]["section_id"] = "risk_truth"
    elif case == "count_mismatch": p["sections"]["book_truth"]["rows_total"] = 2
    with pytest.raises(c.DecisionSnapshotContractError): c.seal_snapshot(p)


def test_complete_cannot_hide_missing_source():
    c = contract(); p = unsealed(); p["sources"][0]["status"] = "MISSING"
    with pytest.raises(c.DecisionSnapshotContractError): c.seal_snapshot(p)


def test_tampered_nested_payload_fails_digest_verification():
    c = contract(); p = c.seal_snapshot(unsealed()); p["sections"]["book_truth"]["rows"][0]["cash"] = 1
    with pytest.raises(c.DecisionSnapshotContractError, match="digest"): c.verify_snapshot(p)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), {1, 2}, {1: "non-string key"}])
def test_noncanonical_json_is_rejected(bad):
    c = contract(); p = unsealed(); p["sections"]["book_truth"]["rows"][0]["bad"] = bad
    with pytest.raises(c.DecisionSnapshotContractError): c.seal_snapshot(p)


def test_section_rows_and_serialized_size_are_bounded():
    c = contract(); s = section(); s["rows"] *= 101; s["rows_total"] = s["rows_returned"] = 101
    with pytest.raises(c.DecisionSnapshotContractError): c.validate_section(s)
    s = section(); s["rows"][0]["oversize"] = "x" * c.MAX_SECTION_RESPONSE_BYTES
    with pytest.raises(c.DecisionSnapshotContractError): c.validate_section(s)


def test_correction_is_explicit_and_does_not_mutate_predecessor():
    c = contract(); first = c.seal_snapshot(unsealed()); original = deepcopy(first); p = unsealed()
    p["state"] = "CORRECTED_GENERATION_AVAILABLE"
    p["correction"] = {"status": "CORRECTED_GENERATION_AVAILABLE", "same_cutoff_prior_snapshot_ids": [first["snapshot_id"]]}
    p["sources"][0]["correction_generation"] = "sha256:" + "b" * 64
    p["source_generation_set"][0]["correction_generation"] = "sha256:" + "b" * 64
    second = c.seal_snapshot(p)
    assert first == original and first["snapshot_id"] != second["snapshot_id"]


def test_contract_reuses_canonical_json_owner_and_has_no_hidden_io():
    c = contract(); source = Path(c.__file__).read_text()
    assert "from control_plane.wake_events import canonical_json_bytes" in source
    assert "def canonical_json_bytes" not in source
    assert not [t for t in ("datetime.now", "date.today", "time.time", "open(", "Path(", "requests", "subprocess", "paper_account", "portfolio_intelligence") if t in source]


@pytest.mark.parametrize("authority", ["MEASUREMENT_ONLY", "DISPLAY_ONLY"])
def test_recovered_s0_context_authority_classes_are_nonexecuting(authority):
    c = contract(); r = receipt(); r["authority_class"] = authority
    r["clock_basis"] = "DECLARED_SOURCE_FIELD"
    c.validate_source_receipt(r)


def test_unqualified_external_clock_is_recordable_but_not_complete():
    c = contract(); r = receipt()
    r.update(status="UNQUALIFIED_CLOCK", known_at=None, clock_basis="UNQUALIFIED_EXTERNAL_CLOCK",
             coverage_state="PARTIAL", freshness_state="UNKNOWN", error_code="NO_QUALIFIED_KNOWN_AT")
    c.validate_source_receipt(r)


def test_nonzero_subsecond_clock_is_not_silently_rounded_into_cutoff():
    c = contract()
    with pytest.raises(c.DecisionSnapshotContractError):
        c.parse_utc_timestamp("2026-09-15T20:00:00.900Z", field="known_at")


def test_available_source_cannot_use_unqualified_external_clock_basis():
    c = contract(); r = receipt(); r["clock_basis"] = "UNQUALIFIED_EXTERNAL_CLOCK"
    with pytest.raises(c.DecisionSnapshotContractError): c.validate_source_receipt(r)


def test_aggregate_json_size_is_checked_before_serialization(monkeypatch):
    c = contract()
    monkeypatch.setattr(c, "canonical_json_bytes", lambda _: pytest.fail("oversized aggregate reached serializer"))
    with pytest.raises(c.DecisionSnapshotContractError): c.content_digest(["x" * 131072] * 3)
