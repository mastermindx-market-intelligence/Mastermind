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
