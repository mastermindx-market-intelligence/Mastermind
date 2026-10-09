from __future__ import annotations

import pandas as pd
import pytest

from research import market_experience_f0_sec_anchor_audit as audit


def legacy_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "cik": 1,
                "filing_date": "2015-01-02",
                "acceptance_datetime": "2015-01-02T13:00:00Z",
                "items": "2.02,9.01",
            },
            {
                "ticker": "AAA",
                "cik": 1,
                "filing_date": "2025-01-03",
                "acceptance_datetime": "2025-01-03T13:00:00Z",
                "items": "2.02",
            },
            {
                "ticker": "BBB",
                "cik": 2,
                "filing_date": "2025-02-01",
                "acceptance_datetime": "2025-02-01T14:00:00Z",
                "items": "2.02",
            },
        ],
        columns=audit.LEGACY_COLUMNS,
    )


def current_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "cik": 1,
                "accession": "0000000001-25-000001",
                "form": "8-K",
                "filing_date": "2025-01-03",
                "acceptance_datetime": "2025-01-03T13:00:00Z",
                "report_date": "2024-12-31",
                "items": "2.02,9.01",
            },
            {
                "ticker": "AAA",
                "cik": 1,
                "accession": "0000000001-25-000002",
                "form": "8-K/A",
                "filing_date": "2025-01-03",
                "acceptance_datetime": "2025-01-03T15:00:00Z",
                "report_date": "2024-12-31",
                "items": "2.02,9.01",
            },
        ],
        columns=audit.CURRENT_COLUMNS,
    )


def test_legacy_store_reports_exact_identity_gap():
    result = audit.analyze_store(legacy_frame())
    assert result["schema_state"] == "LEGACY_DATE_KEY_MISSING_CANONICAL_IDENTITY"
    assert result["missing_identity_columns"] == ["accession", "report_date"]
    assert result["missing_revision_columns"] == ["accession", "form", "report_date"]
    assert result["rows"] == 3
    assert result["ciks"] == 2
    assert result["exact_item_202_rows"] == 3


def test_current_store_preserves_same_day_amendment():
    result = audit.analyze_store(current_frame())
    assert result["schema_state"] == "CURRENT_CANONICAL_FILING_KEY"
    assert result["missing_identity_columns"] == []
    assert result["canonical_key_duplicates"] == 0
    assert result["accession_present"] == 2
    assert result["report_date_present"] == 2
    assert result["form_present"] == 2


def test_duplicate_current_filing_key_is_measured_not_hidden():
    frame = pd.concat([current_frame(), current_frame().iloc[[0]]], ignore_index=True)
    result = audit.analyze_store(frame)
    assert result["canonical_key_duplicates"] == 1


def test_non_item_202_row_refused():
    frame = legacy_frame()
    frame.loc[0, "items"] = "9.01"
    with pytest.raises(audit.SecAnchorAuditError, match="non-Item-2.02"):
        audit.analyze_store(frame)


def test_invalid_clock_refused():
    frame = legacy_frame()
    frame.loc[0, "acceptance_datetime"] = "not-a-time"
    with pytest.raises(audit.SecAnchorAuditError, match="acceptance_datetime"):
        audit.analyze_store(frame)


def test_unknown_schema_refused():
    frame = legacy_frame().assign(extra="x")
    with pytest.raises(audit.SecAnchorAuditError, match="unexpected store columns"):
        audit.analyze_store(frame)


def test_manifest_counts_and_missing_shards():
    value = {
        "1": {
            "status": "ok",
            "n_filings": 2,
            "n_shards_missing": 0,
            "ts": "2026-01-01T00:00:00+00:00",
        },
        "2": {
            "status": "error",
            "n_filings": 0,
            "n_shards_missing": 1,
            "ts": "2026-01-02T00:00:00+00:00",
        },
    }
    result = audit.analyze_manifest(value)
    assert result["entries"] == 2
    assert result["status_counts"] == {"ok": 1, "error": 1}
    assert result["sum_manifest_filings"] == 2
    assert result["sum_missing_shards"] == 1
    assert result["malformed_entries"] == 0


@pytest.mark.parametrize("value", [{}, [], None])
def test_empty_or_nonobject_manifest_refused(value):
    with pytest.raises(audit.SecAnchorAuditError):
        audit.analyze_manifest(value)


def test_git_blob_sha_matches_git_format():
    body = b"hello\n"
    assert audit.git_blob_sha1(body) == "ce013625030ba8dba906f756967f9e9ca394464a"
