from pathlib import Path

import pytest

from portfolio import decision_snapshot_contracts as c


def _receipt() -> dict:
    return {
        "schema": c.SOURCE_RECEIPT_SCHEMA,
        "source_id": "book.account",
        "domains": ["book_truth"],
        "producer": "mastermind_portfolio",
        "owner": "portfolio_desk",
        "artifact": "data/portfolios/autonomous/account.json",
        "source_schema": None,
        "schema_version": None,
        "definition_id": None,
        "artifact_digest": "sha256:" + "a" * 64,
        "observed_at": None,
        "known_at": "2026-09-15T20:00:00Z",
        "as_of": "2026-09-15",
        "generated_at": None,
        "filesystem_observed_at": "2026-09-15T20:00:00Z",
        "correction_generation": "sha256:" + "a" * 64,
        "freshness_state": "FRESH",
        "coverage_state": "COMPLETE",
        "rights_class": "FIRST_PARTY_INTERNAL",
        "authority_class": "BOOK_STATE",
        "status": "AVAILABLE",
        "required": True,
        "bytes": 120,
        "rows_total": 1,
        "rows_returned": 1,
        "omitted_rows": 0,
        "clock_basis": "FILE_MTIME_FIRST_PARTY_STATE",
        "error_code": None,
    }


def _section() -> dict:
    return {
        "schema": c.SECTION_SCHEMA,
        "section_id": "book_truth",
        "coverage_state": "COMPLETE",
        "source_ids": ["book.account"],
        "rows_total": 1,
        "rows_returned": 1,
        "omitted_rows": 0,
        "rows": [{"kind": "account", "cash": 1000000.0, "positions": []}],
        "gaps": [],
    }


def _unsealed() -> dict:
    return {
        "schema": c.SNAPSHOT_SCHEMA,
        "book": "autonomous",
        "decision_cutoff": "2026-09-15T20:00:00Z",
        "recorded_at": "2026-09-15T20:01:00Z",
        "state": "COMPLETE",
        "coverage_state": "COMPLETE",
        "summary": {
            "sources_total": 1,
            "sources_available": 1,
            "domains_complete": 1,
            "domains_partial": 0,
            "domains_blocked": 0,
        },
        "source_generation_set": [
            {"source_id": "book.account", "correction_generation": "sha256:" + "a" * 64}
        ],
        "sources": [_receipt()],
        "sections": {"book_truth": _section()},
        "gaps": [],
        "correction": {
            "status": "ORIGINAL",
            "same_cutoff_prior_snapshot_ids": [],
        },
        "authority": {
            "write_permitted": False,
            "execution_authority": False,
            "numeric_target_authority": False,
        },
    }


def test_seal_is_key_order_invariant_and_self_verifying():
    left = _unsealed()
    right = dict(reversed(list(left.items())))
    sealed_left = c.seal_snapshot(left)
    sealed_right = c.seal_snapshot(right)
    assert sealed_left["snapshot_id"] == sealed_right["snapshot_id"]
    assert sealed_left["snapshot_id"].startswith("sha256:")
    c.verify_snapshot(sealed_left)


def test_closed_root_rejects_unknown_and_missing_fields():
    extra = {**_unsealed(), "surprise": True}
    with pytest.raises(c.DecisionSnapshotContractError, match="unknown"):
        c.validate_unsealed_snapshot(extra)
    missing = _unsealed()
    missing.pop("decision_cutoff")
    with pytest.raises(c.DecisionSnapshotContractError, match="missing"):
        c.validate_unsealed_snapshot(missing)


def test_contract_requires_timezone_aware_utc_clocks():
    for bad in ("2026-09-15", "2026-09-15T20:00:00", "not-a-time"):
        with pytest.raises(c.DecisionSnapshotContractError):
            c.parse_utc_timestamp(bad, field="decision_cutoff")
    assert c.parse_utc_timestamp(
        "2026-09-15T16:00:00-04:00", field="decision_cutoff"
    ) == "2026-09-15T20:00:00Z"


def test_source_receipt_refuses_unqualified_digest_and_authority_escalation():
    bad_digest = {**_receipt(), "artifact_digest": "abc"}
    with pytest.raises(c.DecisionSnapshotContractError):
        c.validate_source_receipt(bad_digest)
    bad_authority = {**_receipt(), "authority_class": "EXECUTION"}
    with pytest.raises(c.DecisionSnapshotContractError):
        c.validate_source_receipt(bad_authority)


def test_verify_snapshot_rejects_tampering_and_mismatched_id():
    sealed = c.seal_snapshot(_unsealed())

    tampered = dict(sealed)
    tampered["book"] = "not-autonomous"
    with pytest.raises(c.DecisionSnapshotContractError):
        c.verify_snapshot(tampered)

    mismatched_id = dict(sealed)
    mismatched_id["snapshot_id"] = "sha256:" + "b" * 64
    with pytest.raises(c.DecisionSnapshotContractError):
        c.verify_snapshot(mismatched_id)


def test_clock_bases_include_external_declared_and_unqualified():
    assert "DECLARED_SOURCE_FIELD" in c.CLOCK_BASES
    assert "UNQUALIFIED_EXTERNAL_CLOCK" in c.CLOCK_BASES
    # Each basis is paired with a status it can lawfully carry: an unqualified external
    # clock is precisely the state that cannot be AVAILABLE, so it is exercised on the
    # UNQUALIFIED_CLOCK receipt it actually describes.
    c.validate_source_receipt({**_receipt(), "clock_basis": "DECLARED_SOURCE_FIELD"})
    c.validate_source_receipt({
        **_receipt(),
        "clock_basis": "UNQUALIFIED_EXTERNAL_CLOCK",
        "status": "UNQUALIFIED_CLOCK",
        "known_at": None,
        "coverage_state": "PARTIAL",
    })


def test_authority_classes_accept_new_context_only_classes_but_reject_execution():
    for authority in ("MARKET_RISK_CONTEXT", "CONTEXT_ONLY", "MEASUREMENT_ONLY", "DISPLAY_ONLY"):
        assert authority in c.AUTHORITY_CLASSES
        c.validate_source_receipt({**_receipt(), "authority_class": authority})
    assert "EXECUTION" not in c.AUTHORITY_CLASSES
    with pytest.raises(c.DecisionSnapshotContractError):
        c.validate_source_receipt({**_receipt(), "authority_class": "EXECUTION"})


def test_source_receipt_rejects_boolean_as_integer():
    bad_bytes = {**_receipt(), "bytes": True}
    with pytest.raises(c.DecisionSnapshotContractError):
        c.validate_source_receipt(bad_bytes)


def test_snapshot_and_receipt_require_already_canonical_utc_timestamps():
    noncanonical = "2026-09-15T16:00:00-04:00"
    canonical = "2026-09-15T20:00:00Z"
    # parse_utc_timestamp itself still normalizes a non-canonical aware offset.
    assert c.parse_utc_timestamp(noncanonical, field="decision_cutoff") == canonical

    unsealed = _unsealed()
    unsealed["decision_cutoff"] = noncanonical
    with pytest.raises(c.DecisionSnapshotContractError):
        c.validate_unsealed_snapshot(unsealed)

    unsealed_recorded = _unsealed()
    unsealed_recorded["recorded_at"] = noncanonical
    with pytest.raises(c.DecisionSnapshotContractError):
        c.validate_unsealed_snapshot(unsealed_recorded)

    for field in ("known_at", "observed_at", "generated_at", "filesystem_observed_at"):
        bad_receipt = {**_receipt(), field: noncanonical}
        with pytest.raises(c.DecisionSnapshotContractError):
            c.validate_source_receipt(bad_receipt)

    # as_of is source-owned and must not be run through timestamp parsing.
    date_only_receipt = {**_receipt(), "as_of": "2026-09-15"}
    c.validate_source_receipt(date_only_receipt)

    # observed_at must actually be checked now, not merely type-checked.
    unparseable_receipt = {**_receipt(), "observed_at": "banana"}
    with pytest.raises(c.DecisionSnapshotContractError):
        c.validate_source_receipt(unparseable_receipt)


def test_contract_reuses_canonical_json_owner_and_has_no_hidden_io():
    source = Path(c.__file__).read_text(encoding="utf-8")
    assert "from control_plane.wake_events import canonical_json_bytes" in source
    assert "def canonical_json_bytes" not in source
    forbidden = (
        "datetime.now",
        "date.today",
        "time.time",
        "open(",
        "Path(",
        "requests",
        "subprocess",
        "paper_account",
        "portfolio_intelligence",
    )
    assert not [token for token in forbidden if token in source]


# ---------------------------------------------------------------------------
# Task 8 repair R5 — AVAILABLE is a clock-qualified state, closed at the contract
# ---------------------------------------------------------------------------

def test_available_receipt_requires_a_non_null_known_at():
    """``status=AVAILABLE`` asserts point-in-time knowledge; a null ``known_at`` means the
    snapshot cannot say *when* the evidence was true, so it may never claim AVAILABLE."""
    receipt = {**_receipt(), "known_at": None}
    with pytest.raises(c.DecisionSnapshotContractError):
        c.validate_source_receipt(receipt)


@pytest.mark.parametrize("clock_basis", ["UNKNOWN", "UNQUALIFIED_EXTERNAL_CLOCK"])
def test_available_receipt_cannot_rest_on_an_unqualified_clock(clock_basis):
    receipt = {**_receipt(), "clock_basis": clock_basis}
    with pytest.raises(c.DecisionSnapshotContractError):
        c.validate_source_receipt(receipt)


@pytest.mark.parametrize(
    "status,known_at,clock_basis",
    [
        ("ABSENT_OPTIONAL", None, "UNKNOWN"),
        ("MISSING", None, "UNKNOWN"),
        ("OVERSIZE", None, "UNKNOWN"),
        ("MALFORMED", None, "UNKNOWN"),
        ("INVALID", None, "UNKNOWN"),
        ("UNQUALIFIED_CLOCK", None, "UNQUALIFIED_EXTERNAL_CLOCK"),
        ("DEPENDENCY_PARTIAL", None, "UNQUALIFIED_EXTERNAL_CLOCK"),
        ("FUTURE_AT_CUTOFF", "2026-09-15T21:00:00Z", "FILE_MTIME_FIRST_PARTY_STATE"),
    ],
)
def test_non_available_states_keep_their_lawful_unqualified_clocks(status, known_at, clock_basis):
    """The AVAILABLE invariant must not collaterally outlaw the degraded states the
    source law depends on — every one of these stays valid."""
    receipt = {
        **_receipt(),
        "status": status,
        "known_at": known_at,
        "clock_basis": clock_basis,
        "coverage_state": "PARTIAL",
    }
    c.validate_source_receipt(receipt)
