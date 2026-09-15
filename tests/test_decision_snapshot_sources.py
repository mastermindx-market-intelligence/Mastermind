import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from portfolio import decision_snapshot_contracts as c
from portfolio import decision_snapshot_sources as sources


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _by_id(receipts) -> dict:
    return {r["source_id"]: r for r in receipts}


@pytest.fixture
def repo_roots(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    macro = tmp_path / "macro"
    repo.mkdir()
    macro.mkdir()
    monkeypatch.setattr(sources, "_ROOT", repo)
    monkeypatch.setattr(sources, "_V", macro)
    return repo, macro


def test_capture_reads_fixed_sources_without_account_recovery(
    monkeypatch, repo_roots
):
    repo, macro = repo_roots
    _write_json(repo / "data/portfolios/autonomous/account.json", {
        "starting_nav": 1_000_000.0,
        "cash": 800_000.0,
        "positions": {"AAPL": {"shares": 100.0, "avg_cost": 180.0}},
    })
    _write_json(repo / "data/portfolios/autonomous/latest.json", {
        "as_of": "2026-09-15",
        "positions": [{
            "ticker": "AAPL",
            "weight": 0.2,
            "identity_status": "verified_common_stock",
            "holding_mark_source": "live_quote",
        }],
    })
    _write_json(macro / "site/riskdata/risk_envelope.json", {
        "schema": "mastermind.risk_envelope/v1",
        "definition_id": "grey-deer-v1-2026-08-19",
        "generated_at": "2026-09-15T19:55:00Z",
        "as_of": "2026-09-15",
        "data_state": "FRESH",
        "capital_policy": {"posture": "SELECTIVE"},
    })

    from portfolio import paper_account
    monkeypatch.setattr(
        paper_account,
        "_load_account",
        lambda *a, **k: pytest.fail("transaction recovery is forbidden"),
    )

    result = sources.capture_all(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )

    assert result["sections"]["book_truth"]["rows"][0]["cash"] == 800_000.0
    assert result["sections"]["risk_truth"]["rows"][0]["capital_policy"] == {
        "posture": "SELECTIVE"
    }
    assert not any(gap["code"] == "ACCOUNT_RECOVERY_CALLED" for gap in result["gaps"])


def test_internal_state_uses_only_stable_first_party_file_clock(repo_roots):
    repo, _ = repo_roots
    path = repo / "data/portfolios/autonomous/account.json"
    _write_json(path, {"cash": 1_000_000.0, "positions": {}})
    os.utime(path, ns=(1_789_400_000_000_000_000, 1_789_400_000_000_000_000))
    result = sources.capture_book_state(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["book.account"]
    assert receipt["clock_basis"] == "FILE_MTIME_FIRST_PARTY_STATE"
    assert receipt["known_at"] == receipt["filesystem_observed_at"]


def test_internal_source_change_during_read_returns_no_rows(monkeypatch, repo_roots):
    repo, _ = repo_roots
    path = repo / "data/portfolios/autonomous/account.json"
    _write_json(path, {"cash": 1_000_000.0, "positions": {}})
    real_fstat = sources.os.fstat
    calls = {"n": 0}

    def changed(fd):
        row = real_fstat(fd)
        calls["n"] += 1
        if calls["n"] == 2:
            return SimpleNamespace(
                st_dev=row.st_dev,
                st_ino=row.st_ino,
                st_size=row.st_size + 1,
                st_mtime_ns=row.st_mtime_ns + 1,
            )
        return row

    monkeypatch.setattr(sources.os, "fstat", changed)
    result = sources.capture_book_state(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["book.account"]
    assert receipt["status"] == "INVALID"
    assert receipt["error_code"] == "SOURCE_CHANGED_DURING_READ"
    assert result["sections"]["book_truth"]["rows"] == []


def test_external_known_after_cutoff_is_excluded_not_read_as_current(repo_roots):
    _, macro = repo_roots
    _write_json(macro / "site/riskdata/risk_envelope.json", {
        "schema": "mastermind.risk_envelope/v1",
        "generated_at": "2026-09-15T20:05:00Z",
        "as_of": "2026-09-15",
        "capital_policy": {"posture": "NORMAL"},
    })
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:06:00Z",
    )
    receipt = _by_id(result["sources"])["macro.risk_envelope"]
    assert receipt["status"] == "FUTURE_AT_CUTOFF"
    assert receipt["coverage_state"] == "BLOCKED"
    assert result["sections"]["risk_truth"]["rows"] == []


def test_missing_risk_is_unknown_protective_not_calm(repo_roots):
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    risk = result["sections"]["risk_truth"]
    assert risk["coverage_state"] == "PARTIAL"
    assert risk["rows"] == [{
        "market_risk_state": "UNKNOWN_PROTECTIVE",
        "reason": "macro.risk_envelope:MISSING",
    }]


def test_rotation_is_receipt_only_until_pr548_contract_is_available(
    repo_roots,
):
    _, macro = repo_roots
    _write_json(macro / "site/sectordata/sector_central.json", {
        "as_of": "2026-09-15",
        "sectors": [{"id": "technology", "ticker": "XLK"}],
        "baskets": [{"id": "memory-hbm", "ticker": "SMH"}],
    })
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.sector_rotation"]
    assert receipt["status"] == "DEPENDENCY_PARTIAL"
    section = result["sections"]["market_structure"]
    assert section["coverage_state"] == "PARTIAL"
    assert not any("sectors" in row or "baskets" in row for row in section["rows"])
    assert any(gap["owner"] == "Mastermind PR #548" for gap in section["gaps"])


def test_external_mtime_is_never_promoted_to_market_known_at(repo_roots):
    _, macro = repo_roots
    path = macro / "site/factor_betas.json"
    _write_json(path, {"schema": "factor_betas.v1", "betas": {}})
    os.utime(path, (1_789_400_000, 1_789_400_000))
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.factor_betas"]
    assert receipt["known_at"] is None
    assert receipt["filesystem_observed_at"] is not None
    assert receipt["clock_basis"] == "UNQUALIFIED_EXTERNAL_CLOCK"
    assert receipt["status"] == "UNQUALIFIED_CLOCK"


def test_no_public_function_accepts_a_path_or_root_argument():
    for fn in (
        sources.capture_all,
        sources.capture_book_state,
        sources.capture_external_sources,
    ):
        assert not {"path", "root", "url", "filename"} & set(
            inspect.signature(fn).parameters
        )


def test_oversize_source_is_partial_without_parsing(repo_roots):
    _, macro = repo_roots
    path = macro / "site/factor_betas.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"{" + b"x" * (c.MAX_SOURCE_BYTES + 1))
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.factor_betas"]
    assert receipt["status"] == "OVERSIZE"
    assert receipt["coverage_state"] == "PARTIAL"
