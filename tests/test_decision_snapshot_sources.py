import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from portfolio import decision_snapshot_contracts as c
from portfolio import decision_snapshot_sources as sources


# Fixed, pre-cutoff epoch for ordinary fixture writes (2026-09-15T19:00:00Z) — every test in
# this file that does not care about clock behavior uses "2026-09-15T20:00:00Z" as
# decision_cutoff, so fixture mtimes must not depend on the host wall clock landing before it.
_PRE_CUTOFF_EPOCH = 1_789_498_800


def _set_pre_cutoff_mtime(path: Path) -> None:
    os.utime(path, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    _set_pre_cutoff_mtime(path)


def _write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    _set_pre_cutoff_mtime(path)


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


# ---------------------------------------------------------------------------
# Pre-review interface closure — receipts must validate against Task 1's
# closed contract, and declared correction generations must be digest-shaped.
# ---------------------------------------------------------------------------

def _full_capture_fixture(repo, macro) -> None:
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
    _write_json(macro / "site/sectordata/sector_central.json", {
        "as_of": "2026-09-15",
        "sectors": [{"id": "technology", "ticker": "XLK"}],
    })
    _write_json(macro / "site/factor_betas.json", {
        "schema": "factor_betas.v1",
        "generated_at": "2026-09-15T19:00:00Z",
        "as_of": "2026-09-15",
        "revision": "42",
        "betas": {"AAPL": {"MKT": 1.0}},
    })


def test_every_emitted_receipt_validates_against_the_closed_contract(repo_roots):
    repo, macro = repo_roots
    _full_capture_fixture(repo, macro)
    result = sources.capture_all(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert len(result["sources"]) > 1
    for receipt in result["sources"]:
        c.validate_source_receipt(receipt)


def test_source_generation_set_from_receipts_satisfies_generation_rule(repo_roots):
    repo, macro = repo_roots
    _full_capture_fixture(repo, macro)
    result = sources.capture_all(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    generation_set = [
        {"source_id": r["source_id"], "correction_generation": r["correction_generation"]}
        for r in result["sources"]
    ]
    c._validate_source_generation_set(generation_set)


def test_declared_correction_generation_is_digest_shaped_and_stable(repo_roots):
    _, macro = repo_roots
    _write_json(macro / "site/factor_betas.json", {
        "schema": "factor_betas.v1",
        "generated_at": "2026-09-15T19:00:00Z",
        "as_of": "2026-09-15",
        "revision": "42",
        "betas": {},
    })
    first = sources.capture_external_sources(
        held_tickers=[], decision_cutoff="2026-09-15T20:00:00Z", recorded_at="2026-09-15T20:01:00Z",
    )
    receipt_1 = _by_id(first["sources"])["macro.factor_betas"]
    c.validate_source_receipt(receipt_1)
    assert receipt_1["correction_generation"] != "42"
    assert receipt_1["correction_generation"].startswith("sha256:")

    second = sources.capture_external_sources(
        held_tickers=[], decision_cutoff="2026-09-15T20:00:00Z", recorded_at="2026-09-15T20:05:00Z",
    )
    receipt_2 = _by_id(second["sources"])["macro.factor_betas"]
    assert receipt_2["correction_generation"] == receipt_1["correction_generation"]


def test_declared_correction_generation_changes_when_content_changes_under_same_revision(repo_roots):
    _, macro = repo_roots
    path = macro / "site/factor_betas.json"
    _write_json(path, {
        "schema": "factor_betas.v1",
        "generated_at": "2026-09-15T19:00:00Z",
        "as_of": "2026-09-15",
        "revision": "42",
        "betas": {"AAPL": {"MKT": 1.0}},
    })
    first = sources.capture_external_sources(
        held_tickers=["AAPL"], decision_cutoff="2026-09-15T20:00:00Z", recorded_at="2026-09-15T20:01:00Z",
    )
    receipt_1 = _by_id(first["sources"])["macro.factor_betas"]

    _write_json(path, {
        "schema": "factor_betas.v1",
        "generated_at": "2026-09-15T19:00:00Z",
        "as_of": "2026-09-15",
        "revision": "42",
        "betas": {"AAPL": {"MKT": 1.5}},
    })
    second = sources.capture_external_sources(
        held_tickers=["AAPL"], decision_cutoff="2026-09-15T20:00:00Z", recorded_at="2026-09-15T20:02:00Z",
    )
    receipt_2 = _by_id(second["sources"])["macro.factor_betas"]

    assert receipt_1["artifact_digest"] != receipt_2["artifact_digest"]
    assert receipt_1["correction_generation"] != receipt_2["correction_generation"]


@pytest.mark.parametrize("bad_revision", ["", "\x00bad", float("nan"), float("inf"), True, {}, []])
def test_unusable_declared_generation_falls_back_to_artifact_digest(repo_roots, bad_revision):
    _, macro = repo_roots
    _write_json(macro / "site/factor_betas.json", {
        "schema": "factor_betas.v1",
        "generated_at": "2026-09-15T19:00:00Z",
        "as_of": "2026-09-15",
        "revision": bad_revision,
        "betas": {},
    })
    result = sources.capture_external_sources(
        held_tickers=[], decision_cutoff="2026-09-15T20:00:00Z", recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.factor_betas"]
    assert receipt["correction_generation"] == receipt["artifact_digest"]


# ---------------------------------------------------------------------------
# Fix round 1 — independent review repairs: JSONL stable read + exact counts.
# ---------------------------------------------------------------------------

def test_jsonl_source_changed_during_read_returns_invalid_receipt_with_no_rows(monkeypatch, repo_roots):
    repo, _ = repo_roots
    path = repo / "data/portfolios/autonomous/decisions.jsonl"
    _write_jsonl(path, [{"id": 1}, {"id": 2}])
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
    receipt = _by_id(result["sources"])["book.decisions"]
    assert receipt["status"] == "INVALID"
    assert receipt["error_code"] == "SOURCE_CHANGED_DURING_READ"
    assert receipt["known_at"] is None
    assert receipt["clock_basis"] == "UNKNOWN"
    assert receipt["artifact_digest"] == sources._EMPTY_DIGEST
    assert receipt["rows_returned"] == 0
    assert result["sections"]["historical_memory"]["rows"] == []


def test_jsonl_tail_counts_and_digest_from_single_stable_read(repo_roots):
    repo, _ = repo_roots
    path = repo / "data/portfolios/autonomous/decisions.jsonl"
    lines = [json.dumps({"id": i}) for i in range(105)]
    lines.append("{not valid json")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    path.write_bytes(raw)
    _set_pre_cutoff_mtime(path)

    result = sources.capture_book_state(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["book.decisions"]
    assert receipt["status"] == "AVAILABLE"
    assert receipt["rows_returned"] == 100
    assert receipt["omitted_rows"] == 6  # 5 excess valid rows beyond the tail + 1 invalid line
    assert receipt["rows_total"] == receipt["rows_returned"] + receipt["omitted_rows"]
    assert receipt["artifact_digest"] == sources._digest(raw)
    assert receipt["clock_basis"] == "FILE_MTIME_FIRST_PARTY_STATE"
    assert [row["id"] for row in result["sections"]["historical_memory"]["rows"]] == list(range(5, 105))


def test_historical_memory_overflow_counts_all_cap_drops_exactly_once(repo_roots):
    repo, _ = repo_roots
    _write_jsonl(
        repo / "data/portfolios/autonomous/decisions.jsonl",
        [{"id": f"d{i}"} for i in range(100)],
    )
    _write_jsonl(
        repo / "data/portfolios/autonomous/fills.jsonl",
        [{"id": f"f{i}"} for i in range(100)],
    )
    settlement_dir = repo / "data/portfolios/autonomous/settlement_receipts"
    settlement_dir.mkdir(parents=True, exist_ok=True)
    for i in range(10):
        receipt_path = settlement_dir / f"receipt_{i:03d}.json"
        receipt_path.write_text("{}", encoding="utf-8")
        _set_pre_cutoff_mtime(receipt_path)
    # The directory's own mtime is part of the manifest clock — creating entries bumps it to
    # the host wall clock, which is after this test's cutoff — so it is pinned last, exactly
    # as every file fixture in this module pins its own mtime.
    _set_pre_cutoff_mtime(settlement_dir)

    result = sources.capture_book_state(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    section = result["sections"]["historical_memory"]
    assert section["rows_returned"] == len(section["rows"]) == 100
    assert section["rows_total"] == section["rows_returned"] + section["omitted_rows"]
    assert section["omitted_rows"] == 110  # 200 decisions/fills + 10 settlement rows - 100 kept


def test_prophet_selection_preserves_producer_order_and_counts_malformed_as_omitted(repo_roots):
    _, macro = repo_roots
    _write_json(macro / "site/prophet/index.json", {
        "schema": "prophet.v1",
        "generated_at": "2026-09-15T19:00:00Z",
        "as_of": "2026-09-15",
        "plans": [
            {"ticker": "MSFT", "plan": "non-held-1"},
            {"ticker": "AAPL", "plan": "held-1"},
            "not-a-plan",
            {"ticker": "GOOG", "plan": "non-held-2"},
            {"ticker": "AAPL", "plan": "held-2"},
        ],
    })
    result = sources.capture_external_sources(
        held_tickers=["AAPL"],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.prophet"]
    assert receipt["status"] == "AVAILABLE"
    section = result["sections"]["candidate_geometry"]
    held_selected = [row["plan"] for row in section["rows"] if row.get("ticker") == "AAPL"]
    non_held_selected = [row["plan"] for row in section["rows"] if row.get("ticker") != "AAPL"]
    assert held_selected == ["held-1", "held-2"]
    assert non_held_selected == ["non-held-1", "non-held-2"]
    assert receipt["omitted_rows"] == 1  # the malformed "not-a-plan" entry
    assert receipt["rows_returned"] == 4
    assert receipt["rows_total"] == 5


def test_held_ticker_bundle_input_over_cap_counts_preslice_omissions(repo_roots):
    _, macro = repo_roots
    tickers = {f"T{i:03d}": {"score": i} for i in range(105)}
    _write_json(macro / "site/altdata/by_ticker.json", {
        "schema": "altdata.v1",
        "generated_at": "2026-09-15T19:00:00Z",
        "as_of": "2026-09-15",
        "tickers": tickers,
    })
    held = list(tickers.keys())
    result = sources.capture_external_sources(
        held_tickers=held,
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.altdata"]
    assert receipt["status"] == "AVAILABLE"
    assert receipt["rows_returned"] == 100
    assert receipt["omitted_rows"] == 5
    assert receipt["rows_total"] == 105
    section = result["sections"]["positioning"]
    assert section["rows_returned"] == len(section["rows"]) == 100
    assert section["rows_total"] == section["rows_returned"] + section["omitted_rows"]


def test_portfolio_context_per_domain_cap_counts_preslice_omissions(repo_roots):
    _, macro = repo_roots
    held = [f"T{i:03d}" for i in range(105)]
    _write_json(macro / "site/data/portfolio_ctx.json", {
        "schema": "portfolio_context.v1",
        "generated_at": "2026-09-15T19:00:00Z",
        "as_of": "2026-09-15",
        "fundamental_state": [{"ticker": t} for t in held],
        "positioning": [{"ticker": t} for t in held[:3]],
        "event_state": [],
        "priceability": [{"ticker": t} for t in held],
    })
    result = sources.capture_external_sources(
        held_tickers=held,
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.portfolio_context"]
    assert receipt["status"] == "AVAILABLE"
    assert receipt["rows_returned"] == 100 + 3 + 0 + 100
    assert receipt["omitted_rows"] == 5 + 0 + 0 + 5
    assert receipt["rows_total"] == receipt["rows_returned"] + receipt["omitted_rows"]

    fundamental = result["sections"]["fundamental_state"]
    assert fundamental["rows_returned"] == len(fundamental["rows"]) == 100
    assert fundamental["omitted_rows"] == 5
    assert fundamental["rows_total"] == fundamental["rows_returned"] + fundamental["omitted_rows"]

    positioning = result["sections"]["positioning"]
    assert positioning["rows_returned"] == len(positioning["rows"]) == 3
    assert positioning["omitted_rows"] == 0


def test_missing_risk_placeholder_counts_as_one_row_not_a_free_row(repo_roots):
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    section = result["sections"]["risk_truth"]
    assert section["rows_returned"] == 1
    assert section["rows_total"] == 1
    assert section["omitted_rows"] == 0
    assert len(section["rows"]) == 1


# ---------------------------------------------------------------------------
# W1 — first-party mtime must be compared against decision_cutoff too.
# ---------------------------------------------------------------------------

_FUTURE_EPOCH = 1_789_502_700  # 2026-09-15T20:05:00Z — strictly after the fixture cutoff
_EQUAL_EPOCH = 1_789_502_400  # 2026-09-15T20:00:00Z — exactly the fixture cutoff


def test_required_account_after_cutoff_is_future_and_blocks_book_truth(repo_roots):
    repo, _ = repo_roots
    path = repo / "data/portfolios/autonomous/account.json"
    _write_json(path, {"cash": 1_000_000.0, "positions": {}})
    os.utime(path, (_FUTURE_EPOCH, _FUTURE_EPOCH))

    result = sources.capture_book_state(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:06:00Z",
    )
    receipt = _by_id(result["sources"])["book.account"]
    assert receipt["status"] == "FUTURE_AT_CUTOFF"
    assert receipt["coverage_state"] == "BLOCKED"
    assert receipt["rows_returned"] == 0
    assert result["sections"]["book_truth"]["rows"] == []
    assert result["sections"]["book_truth"]["coverage_state"] == "BLOCKED"
    assert any(
        gap["code"] == "FUTURE_AT_CUTOFF" and gap["source_id"] == "book.account"
        for gap in result["gaps"]
    )
    assert any(
        gap["code"] == "FUTURE_AT_CUTOFF" and gap["source_id"] == "book.account"
        for gap in result["sections"]["book_truth"]["gaps"]
    )


def test_optional_latest_after_cutoff_cannot_contribute_rows(repo_roots):
    repo, _ = repo_roots
    account_path = repo / "data/portfolios/autonomous/account.json"
    _write_json(account_path, {"cash": 1_000_000.0, "positions": {}})
    latest_path = repo / "data/portfolios/autonomous/latest.json"
    _write_json(latest_path, {"as_of": "2026-09-15", "positions": []})
    os.utime(latest_path, (_FUTURE_EPOCH, _FUTURE_EPOCH))

    result = sources.capture_book_state(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:06:00Z",
    )
    receipt = _by_id(result["sources"])["book.latest"]
    assert receipt["status"] == "FUTURE_AT_CUTOFF"
    assert receipt["coverage_state"] == "BLOCKED"
    assert receipt["rows_returned"] == 0
    assert not any("as_of" in row for row in result["sections"]["book_truth"]["rows"])


def test_decisions_jsonl_after_cutoff_contributes_no_row_and_blocks_section(repo_roots):
    repo, _ = repo_roots
    path = repo / "data/portfolios/autonomous/decisions.jsonl"
    _write_jsonl(path, [{"id": 1}, {"id": 2}])
    os.utime(path, (_FUTURE_EPOCH, _FUTURE_EPOCH))

    result = sources.capture_book_state(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:06:00Z",
    )
    receipt = _by_id(result["sources"])["book.decisions"]
    assert receipt["status"] == "FUTURE_AT_CUTOFF"
    assert receipt["coverage_state"] == "BLOCKED"
    assert receipt["rows_returned"] == 0
    assert result["sections"]["historical_memory"]["rows"] == []
    assert result["sections"]["historical_memory"]["coverage_state"] == "BLOCKED"


def test_malformed_future_bytes_are_future_at_cutoff_not_malformed(repo_roots):
    repo, _ = repo_roots
    path = repo / "data/portfolios/autonomous/account.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")
    os.utime(path, (_FUTURE_EPOCH, _FUTURE_EPOCH))

    result = sources.capture_book_state(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:06:00Z",
    )
    receipt = _by_id(result["sources"])["book.account"]
    assert receipt["status"] == "FUTURE_AT_CUTOFF"
    assert receipt["error_code"] is None


def test_mtime_exactly_at_cutoff_remains_eligible(repo_roots):
    repo, _ = repo_roots
    path = repo / "data/portfolios/autonomous/account.json"
    _write_json(path, {"cash": 1_000_000.0, "positions": {}})
    os.utime(path, (_EQUAL_EPOCH, _EQUAL_EPOCH))

    result = sources.capture_book_state(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:06:00Z",
    )
    receipt = _by_id(result["sources"])["book.account"]
    assert receipt["status"] == "AVAILABLE"
    assert receipt["known_at"] == "2026-09-15T20:00:00Z"
    assert result["sections"]["book_truth"]["rows"] != []


def test_future_at_cutoff_receipt_retains_first_party_clock_digest_and_generation(repo_roots):
    repo, _ = repo_roots
    path = repo / "data/portfolios/autonomous/account.json"
    _write_json(path, {"cash": 1_000_000.0, "positions": {}})
    os.utime(path, (_FUTURE_EPOCH, _FUTURE_EPOCH))
    raw = path.read_bytes()

    result = sources.capture_book_state(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:06:00Z",
    )
    receipt = _by_id(result["sources"])["book.account"]
    c.validate_source_receipt(receipt)
    assert receipt["clock_basis"] == "FILE_MTIME_FIRST_PARTY_STATE"
    assert receipt["known_at"] == "2026-09-15T20:05:00Z"
    assert receipt["known_at"] == receipt["filesystem_observed_at"]
    assert receipt["artifact_digest"] == sources._digest(raw)
    assert (
        receipt["correction_generation"]
        == receipt["artifact_digest"]
        == sources._digest(raw)
        != sources._EMPTY_DIGEST
    )
    assert receipt["rows_total"] == 0
    assert receipt["rows_returned"] == 0
    assert receipt["omitted_rows"] == 0
    assert any(
        gap["code"] == "FUTURE_AT_CUTOFF" and gap["source_id"] == "book.account"
        and gap["section_id"] == "book_truth"
        for gap in result["gaps"]
    )
    assert any(
        gap["code"] == "FUTURE_AT_CUTOFF" and gap["source_id"] == "book.account"
        for gap in result["sections"]["book_truth"]["gaps"]
    )


def test_mtime_one_ns_below_next_second_stays_in_prior_second_and_eligible(repo_roots):
    """Regression for float-precision loss in nanosecond-to-second conversion.

    A file written 1 ns before the second *after* the cutoff second is still, in whole
    seconds, exactly at the cutoff — eligible, not future. ``st_mtime_ns / 1e9`` as a
    float can round that fractional nanosecond count up across the second boundary
    before truncation, wrongly reporting the next second and excluding an eligible file.
    """
    repo, _ = repo_roots
    path = repo / "data/portfolios/autonomous/account.json"
    _write_json(path, {"cash": 1_000_000.0, "positions": {}})
    one_ns_below_next_second = (_EQUAL_EPOCH + 1) * 1_000_000_000 - 1
    os.utime(path, ns=(one_ns_below_next_second, one_ns_below_next_second))

    result = sources.capture_book_state(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:06:00Z",
    )
    receipt = _by_id(result["sources"])["book.account"]
    assert receipt["status"] == "AVAILABLE"
    assert receipt["known_at"] == "2026-09-15T20:00:00Z"
    assert result["sections"]["book_truth"]["rows"] != []


# ---------------------------------------------------------------------------
# Task 8 repair R1 — every source state carries a discriminating generation
# ---------------------------------------------------------------------------

def _generations(result) -> dict:
    return {r["source_id"]: r["correction_generation"] for r in result["sources"]}


def test_no_source_state_keeps_the_empty_placeholder_generation(repo_roots):
    """``_EMPTY_DIGEST`` is a scaffold value, never evidence. If any receipt keeps it, two
    materially different source states collapse onto one generation and a same-cutoff retry
    silently reuses a stale snapshot."""
    repo, macro = repo_roots
    # A deliberately heterogeneous world: available, absent, malformed, oversize, jsonl.
    _write_json(repo / "data/portfolios/autonomous/account.json", {"cash": 1.0, "positions": {}})
    _write_jsonl(repo / "data/portfolios/autonomous/decisions.jsonl", [{"id": "d1"}])
    malformed = repo / "data/portfolios/autonomous/pending_orders.json"
    malformed.parent.mkdir(parents=True, exist_ok=True)
    malformed.write_bytes(b"{not json")
    _set_pre_cutoff_mtime(malformed)
    oversize = repo / "data/portfolios/autonomous/pending_target.json"
    oversize.write_bytes(b"x" * (c.MAX_SOURCE_BYTES + 1))
    _set_pre_cutoff_mtime(oversize)
    _write_json(macro / "site/factor_betas.json", {"betas": {}})

    result = sources.capture_all(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    placeholder = [
        r["source_id"] for r in result["sources"]
        if r["correction_generation"] == sources._EMPTY_DIGEST
    ]
    assert placeholder == []


def test_two_different_malformed_bodies_do_not_share_one_generation(repo_roots):
    _, macro = repo_roots
    path = macro / "site/factor_betas.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    def capture_with(body: bytes) -> dict:
        path.write_bytes(body)
        _set_pre_cutoff_mtime(path)
        return _by_id(sources.capture_external_sources(
            held_tickers=[],
            decision_cutoff="2026-09-15T20:00:00Z",
            recorded_at="2026-09-15T20:01:00Z",
        )["sources"])["macro.factor_betas"]

    first = capture_with(b"{broken-one")
    second = capture_with(b"{broken-two")
    assert first["status"] == second["status"] == "MALFORMED"
    assert first["artifact_digest"] != second["artifact_digest"]
    assert first["correction_generation"] == first["artifact_digest"]
    assert second["correction_generation"] == second["artifact_digest"]
    assert first["correction_generation"] != second["correction_generation"]

    # Idempotence: the exact same malformed bytes must re-derive the same generation.
    again = capture_with(b"{broken-two")
    assert again["correction_generation"] == second["correction_generation"]


def test_absent_optional_and_oversize_are_not_the_same_generation(repo_roots):
    """The sharpest same-cutoff reuse hazard: an optional source that goes from absent to
    present-but-unreadable must not present the same generation as when it was absent."""
    repo, _ = repo_roots
    book_dir = repo / "data/portfolios/autonomous"
    book_dir.mkdir(parents=True, exist_ok=True)
    _write_json(book_dir / "account.json", {"cash": 1.0, "positions": {}})

    absent = _by_id(sources.capture_book_state(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )["sources"])["book.pending_target"]
    assert absent["status"] == "ABSENT_OPTIONAL"

    oversize_path = book_dir / "pending_target.json"
    oversize_path.write_bytes(b"x" * (c.MAX_SOURCE_BYTES + 1))
    _set_pre_cutoff_mtime(oversize_path)
    oversize = _by_id(sources.capture_book_state(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )["sources"])["book.pending_target"]
    assert oversize["status"] == "OVERSIZE"
    assert oversize["correction_generation"] != absent["correction_generation"]


def test_unavailable_generation_is_stable_across_identical_retries(repo_roots):
    repo, _ = repo_roots
    _write_json(repo / "data/portfolios/autonomous/account.json", {"cash": 1.0, "positions": {}})
    first = _generations(sources.capture_book_state(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    ))
    second = _generations(sources.capture_book_state(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:09:00Z",
    ))
    assert first == second


def test_jsonl_available_generation_tracks_its_own_bytes(repo_roots):
    repo, _ = repo_roots
    path = repo / "data/portfolios/autonomous/decisions.jsonl"
    _write_jsonl(path, [{"id": "d1"}])
    first = _by_id(sources.capture_book_state(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )["sources"])["book.decisions"]
    _write_jsonl(path, [{"id": "d1"}, {"id": "d2"}])
    second = _by_id(sources.capture_book_state(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )["sources"])["book.decisions"]
    assert first["correction_generation"] == first["artifact_digest"]
    assert second["correction_generation"] == second["artifact_digest"]
    assert first["correction_generation"] != second["correction_generation"]


def test_contract_unavailable_generation_is_status_bearing(repo_roots, monkeypatch):
    from control_plane import contracts as contracts_module
    monkeypatch.setattr(contracts_module, "contract", lambda key: None)
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.risk_envelope"]
    assert receipt["status"] == "INVALID"
    assert receipt["correction_generation"] != sources._EMPTY_DIGEST


# ---------------------------------------------------------------------------
# Task 8 repair R2 — non-finite JSON numbers degrade, they never hard-fail
# ---------------------------------------------------------------------------

def test_external_non_finite_constant_is_malformed_not_a_crash(repo_roots):
    _, macro = repo_roots
    path = macro / "site/factor_betas.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"schema":"factor_betas.v1","generated_at":"2026-09-15T19:00:00Z","betas":{"AAPL":NaN}}',
        encoding="utf-8",
    )
    _set_pre_cutoff_mtime(path)
    result = sources.capture_external_sources(
        held_tickers=["AAPL"],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.factor_betas"]
    assert receipt["status"] == "MALFORMED"
    assert receipt["error_code"] == "MALFORMED"
    assert result["sections"]["factor_risk"]["coverage_state"] == "PARTIAL"
    assert result["sections"]["factor_risk"]["rows"] == []


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e400", "-1e400"])
def test_every_non_finite_number_form_is_rejected_at_ingestion(repo_roots, literal):
    """Bare ``NaN``/``Infinity`` constants and finite-looking overflow literals both produce
    a non-finite float that canonical serialization refuses; both must die at the parser."""
    repo, _ = repo_roots
    path = repo / "data/portfolios/autonomous/account.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"cash": %s, "positions": {}}' % literal, encoding="utf-8")
    _set_pre_cutoff_mtime(path)
    result = sources.capture_book_state(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["book.account"]
    assert receipt["status"] == "MALFORMED"
    assert result["sections"]["book_truth"]["coverage_state"] == "BLOCKED"
    assert result["sections"]["book_truth"]["rows"] == []


def test_jsonl_row_with_non_finite_number_is_counted_as_omitted_not_emitted(repo_roots):
    repo, _ = repo_roots
    path = repo / "data/portfolios/autonomous/decisions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"id": "d1"}\n{"id": "d2", "score": NaN}\n{"id": "d3"}\n',
        encoding="utf-8",
    )
    _set_pre_cutoff_mtime(path)
    result = sources.capture_book_state(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["book.decisions"]
    assert receipt["status"] == "AVAILABLE"
    assert receipt["rows_returned"] == 2
    assert receipt["omitted_rows"] == 1
    assert receipt["rows_total"] == 3
    ids = [row["id"] for row in result["sections"]["historical_memory"]["rows"]]
    assert ids == ["d1", "d3"]


# ---------------------------------------------------------------------------
# Task 8 repair R3 — a contentless artifact is not a complete one
# ---------------------------------------------------------------------------

def _gap_codes(result, *, source_id=None, section_id=None) -> list:
    return sorted(
        g["code"] for g in result["gaps"]
        if (source_id is None or g["source_id"] == source_id)
        and (section_id is None or g["section_id"] == section_id)
    )


def test_clock_only_risk_envelope_is_not_a_complete_risk_domain(repo_roots):
    """``available_at`` qualifies the clock but carries no risk content: the required
    risk_truth domain must not read COMPLETE off an artifact with zero projected rows."""
    _, macro = repo_roots
    _write_json(macro / "site/riskdata/risk_envelope.json", {
        "available_at": "2026-09-15T19:55:00Z",
    })
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.risk_envelope"]
    assert receipt["status"] == "AVAILABLE"
    assert receipt["known_at"] == "2026-09-15T19:55:00Z"
    assert receipt["coverage_state"] == "PARTIAL"
    assert result["sections"]["risk_truth"]["coverage_state"] != "COMPLETE"
    assert result["sections"]["risk_truth"]["rows"] == []
    assert "EMPTY_PROJECTION" in _gap_codes(result, source_id="macro.risk_envelope")


def test_present_but_empty_risk_content_stays_complete(repo_roots):
    _, macro = repo_roots
    _write_json(macro / "site/riskdata/risk_envelope.json", {
        "known_at": "2026-09-15T19:55:00Z",
        "hazard_summary": {},
    })
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.risk_envelope"]
    assert receipt["coverage_state"] == "COMPLETE"
    assert result["sections"]["risk_truth"]["coverage_state"] == "COMPLETE"
    assert "EMPTY_PROJECTION" not in _gap_codes(result, source_id="macro.risk_envelope")


def test_portfolio_context_reports_only_the_domain_whose_key_is_absent(repo_roots):
    _, macro = repo_roots
    _write_json(macro / "site/data/portfolio_ctx.json", {
        "known_at": "2026-09-15T19:00:00Z",
        "fundamental_state": [],
        "positioning": [],
        "event_state": [],
    })
    result = sources.capture_external_sources(
        held_tickers=["AAPL"],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    ctx_gaps = [
        g for g in result["gaps"]
        if g["code"] == "EMPTY_PROJECTION" and g["source_id"] == "macro.portfolio_context"
    ]
    assert [g["section_id"] for g in ctx_gaps] == ["priceability"]
    receipt = _by_id(result["sources"])["macro.portfolio_context"]
    assert receipt["coverage_state"] == "PARTIAL"


def test_held_ticker_bundle_distinguishes_absent_tickers_from_empty_tickers(repo_roots):
    _, macro = repo_roots
    path = macro / "site/intelligence/by_ticker.json"

    _write_json(path, {"known_at": "2026-09-15T19:00:00Z"})
    absent = sources.capture_external_sources(
        held_tickers=["AAPL"],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert "EMPTY_PROJECTION" in _gap_codes(absent, source_id="macro.intelligence")
    assert _by_id(absent["sources"])["macro.intelligence"]["coverage_state"] == "PARTIAL"

    _write_json(path, {"known_at": "2026-09-15T19:00:00Z", "tickers": {}})
    empty = sources.capture_external_sources(
        held_tickers=["AAPL"],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert "EMPTY_PROJECTION" not in _gap_codes(empty, source_id="macro.intelligence")
    assert _by_id(empty["sources"])["macro.intelligence"]["coverage_state"] == "COMPLETE"


def test_prophet_with_present_empty_plans_remains_complete(repo_roots):
    _, macro = repo_roots
    path = macro / "site/prophet/index.json"

    _write_json(path, {"known_at": "2026-09-15T19:00:00Z", "plans": []})
    empty = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert "EMPTY_PROJECTION" not in _gap_codes(empty, source_id="macro.prophet")
    assert _by_id(empty["sources"])["macro.prophet"]["coverage_state"] == "COMPLETE"

    _write_json(path, {"known_at": "2026-09-15T19:00:00Z"})
    absent = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert "EMPTY_PROJECTION" in _gap_codes(absent, source_id="macro.prophet")


# ---------------------------------------------------------------------------
# Task 8 repair R4 — a dropped position is a visible gap, never silence
# ---------------------------------------------------------------------------

def test_malformed_account_position_entry_is_visible_and_never_a_narrower_book(repo_roots):
    repo, macro = repo_roots
    path = repo / "data/portfolios/autonomous/account.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "cash": 800_000.0,
        "positions": {"AAPL": {"shares": 100.0, "avg_cost": 180.0}, "MSFT": None},
    }), encoding="utf-8")
    _set_pre_cutoff_mtime(path)
    _write_json(macro / "site/factor_betas.json", {
        "known_at": "2026-09-15T19:00:00Z",
        "betas": {"AAPL": {"MKT": 1.0}, "MSFT": {"MKT": 0.9}},
    })

    result = sources.capture_all(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    positions = result["sections"]["book_truth"]["rows"][0]["positions"]
    assert "AAPL" in positions
    assert "MSFT" not in positions
    assert result["sections"]["book_truth"]["coverage_state"] == "PARTIAL"
    assert "MALFORMED_POSITION_ENTRY" in _gap_codes(result, source_id="book.account")
    assert _by_id(result["sources"])["book.account"]["coverage_state"] == "PARTIAL"
    # A dropped position silently narrows every held-ticker-filtered external projection;
    # the factor row must not be presented as a complete factor picture of the book.
    assert result["sections"]["factor_risk"]["coverage_state"] != "COMPLETE"

    # The gap is a bounded count, not a leak of arbitrary payload text.
    gap = next(g for g in result["gaps"] if g["code"] == "MALFORMED_POSITION_ENTRY")
    assert "MSFT" not in json.dumps(gap)
    assert _by_id(result["sources"])["book.account"]["omitted_rows"] == 0


def test_malformed_latest_position_entries_are_visible(repo_roots):
    repo, _ = repo_roots
    _write_json(repo / "data/portfolios/autonomous/account.json", {"cash": 1.0, "positions": {}})
    path = repo / "data/portfolios/autonomous/latest.json"
    path.write_text(json.dumps({
        "as_of": "2026-09-15",
        "positions": [
            {"ticker": "AAPL", "weight": 0.2},
            None,
            {"weight": 0.1},
            {"ticker": "", "weight": 0.1},
        ],
    }), encoding="utf-8")
    _set_pre_cutoff_mtime(path)
    result = sources.capture_book_state(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert "MALFORMED_POSITION_ENTRY" in _gap_codes(result, source_id="book.latest")
    assert result["sections"]["book_truth"]["coverage_state"] == "PARTIAL"
    latest_row = next(
        row for row in result["sections"]["book_truth"]["rows"] if "as_of" in row
    )
    assert [p["ticker"] for p in latest_row["positions"]] == ["AAPL"]


# ---------------------------------------------------------------------------
# Task 8 repair R5 — the settlement manifest is point-in-time, no-follow, bounded
# ---------------------------------------------------------------------------

_CUTOFF = "2026-09-15T20:00:00Z"
_AT_CUTOFF_EPOCH = 1_789_502_400  # 2026-09-15T20:00:00Z
_POST_CUTOFF_EPOCH = _AT_CUTOFF_EPOCH + 300  # 2026-09-15T20:05:00Z


def _settlement_dir(repo: Path) -> Path:
    return repo / "data/portfolios/autonomous/settlement_receipts"


def _seed_settlement(repo: Path, names, *, entry_epoch=_PRE_CUTOFF_EPOCH,
                     dir_epoch=_PRE_CUTOFF_EPOCH, entry_overrides=None) -> Path:
    """Seed a settlement-receipt directory with fully controlled metadata clocks.

    Directory mtime is set last, because creating entries bumps it.
    """
    directory = _settlement_dir(repo)
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        entry = directory / name
        entry.write_text("{}", encoding="utf-8")
        epoch = (entry_overrides or {}).get(name, entry_epoch)
        os.utime(entry, (epoch, epoch))
    os.utime(directory, (dir_epoch, dir_epoch))
    return directory


def _settlement_receipt(repo, *, cutoff=_CUTOFF) -> tuple:
    result = sources.capture_book_state(
        "autonomous", decision_cutoff=cutoff, recorded_at="2026-09-15T20:10:00Z",
    )
    return _by_id(result["sources"])[sources._SETTLEMENT_RECEIPTS_SOURCE_ID], result


def test_settlement_manifest_binds_a_qualified_first_party_metadata_clock(repo_roots):
    repo, _ = repo_roots
    _seed_settlement(repo, ["r001.json", "r002.json"])
    receipt, result = _settlement_receipt(repo)
    assert receipt["status"] == "AVAILABLE"
    assert receipt["coverage_state"] == "COMPLETE"
    assert receipt["known_at"] == "2026-09-15T19:00:00Z"
    assert receipt["filesystem_observed_at"] == receipt["known_at"]
    assert receipt["clock_basis"] == "FILE_MTIME_FIRST_PARTY_STATE"
    assert receipt["rows_total"] == receipt["rows_returned"] == 2
    files = [
        row["file"] for row in result["sections"]["historical_memory"]["rows"]
        if isinstance(row, dict) and "file" in row
    ]
    assert files == ["r001.json", "r002.json"]


def test_settlement_manifest_exactly_at_cutoff_remains_eligible(repo_roots):
    repo, _ = repo_roots
    _seed_settlement(repo, ["r001.json"], entry_epoch=_AT_CUTOFF_EPOCH,
                     dir_epoch=_AT_CUTOFF_EPOCH)
    receipt, _ = _settlement_receipt(repo)
    assert receipt["status"] == "AVAILABLE"
    assert receipt["known_at"] == _CUTOFF


def test_settlement_receipt_written_after_cutoff_never_enters_historical_memory(repo_roots):
    """Sol's exact reproduced failure: a receipt file whose mtime is five minutes after the
    decision cutoff was emitted AVAILABLE/COMPLETE with ``known_at=null`` and leaked into
    historical memory."""
    repo, _ = repo_roots
    _seed_settlement(
        repo,
        ["r001.json", "settlement-future.json"],
        entry_overrides={"settlement-future.json": _POST_CUTOFF_EPOCH},
    )
    receipt, result = _settlement_receipt(repo)
    assert receipt["status"] == "FUTURE_AT_CUTOFF"
    assert receipt["known_at"] == "2026-09-15T20:05:00Z"
    assert receipt["clock_basis"] == "FILE_MTIME_FIRST_PARTY_STATE"
    assert receipt["rows_returned"] == 0
    assert result["sections"]["historical_memory"]["coverage_state"] == "BLOCKED"
    rendered = json.dumps(result["sections"]["historical_memory"])
    assert "settlement-future.json" not in rendered
    assert "r001.json" not in rendered


def test_settlement_directory_mtime_after_cutoff_is_future(repo_roots):
    repo, _ = repo_roots
    _seed_settlement(repo, ["r001.json"], dir_epoch=_POST_CUTOFF_EPOCH)
    receipt, _ = _settlement_receipt(repo)
    assert receipt["status"] == "FUTURE_AT_CUTOFF"


def test_settlement_source_that_is_a_symlinked_directory_fails_closed(repo_roots):
    repo, _ = repo_roots
    real = repo / "elsewhere"
    real.mkdir(parents=True, exist_ok=True)
    (real / "r001.json").write_text("{}", encoding="utf-8")
    link = _settlement_dir(repo)
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(real, target_is_directory=True)
    receipt, result = _settlement_receipt(repo)
    assert receipt["status"] == "INVALID"
    assert receipt["rows_returned"] == 0
    assert result["sections"]["historical_memory"]["coverage_state"] == "BLOCKED"
    assert "r001.json" not in json.dumps(result["sections"]["historical_memory"])


def test_settlement_source_that_is_a_regular_file_fails_closed(repo_roots):
    repo, _ = repo_roots
    path = _settlement_dir(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    receipt, _ = _settlement_receipt(repo)
    assert receipt["status"] == "INVALID"


def test_settlement_symlinked_json_entry_fails_closed(repo_roots):
    repo, _ = repo_roots
    directory = _seed_settlement(repo, ["r001.json"])
    (directory / "r002.json").symlink_to(directory / "r001.json")
    os.utime(directory, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))
    receipt, result = _settlement_receipt(repo)
    assert receipt["status"] == "INVALID"
    assert receipt["rows_returned"] == 0
    assert "r001.json" not in json.dumps(result["sections"]["historical_memory"])


def test_settlement_nonregular_json_entry_fails_closed(repo_roots):
    repo, _ = repo_roots
    directory = _seed_settlement(repo, ["r001.json"])
    (directory / "nested.json").mkdir()
    os.utime(directory, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))
    receipt, _ = _settlement_receipt(repo)
    assert receipt["status"] == "INVALID"


def test_settlement_directory_changed_during_enumeration_fails_closed(repo_roots, monkeypatch):
    import stat as _stat
    repo, _ = repo_roots
    _seed_settlement(repo, ["r001.json", "r002.json"])

    real_fstat = sources.os.fstat
    dir_calls = {"n": 0}

    def unstable_fstat(fd):
        st = real_fstat(fd)
        if _stat.S_ISDIR(st.st_mode):
            dir_calls["n"] += 1
            if dir_calls["n"] == 2:
                return SimpleNamespace(
                    st_dev=st.st_dev, st_ino=st.st_ino, st_mode=st.st_mode,
                    st_mtime_ns=st.st_mtime_ns + 1,
                )
        return st

    monkeypatch.setattr(sources.os, "fstat", unstable_fstat)
    receipt, result = _settlement_receipt(repo)
    assert receipt["status"] == "INVALID"
    assert receipt["error_code"] == "SOURCE_CHANGED_DURING_READ"
    assert receipt["rows_returned"] == 0
    assert result["sections"]["historical_memory"]["coverage_state"] == "BLOCKED"


def test_settlement_digest_covers_omitted_names_not_only_displayed_rows(repo_roots):
    repo, _ = repo_roots
    names = [f"receipt_{i:03d}.json" for i in range(105)]
    directory = _seed_settlement(repo, names)
    before, before_result = _settlement_receipt(repo)
    assert before["rows_returned"] == c.MAX_SECTION_ROWS
    assert before["omitted_rows"] == 5

    # Rename the sorted-first (never displayed) name so only the omitted head changes.
    (directory / "receipt_000.json").rename(directory / "receipt_0000.json")
    os.utime(directory / "receipt_0000.json", (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))
    os.utime(directory, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))
    after, after_result = _settlement_receipt(repo)

    def files(result):
        return [
            row["file"] for row in result["sections"]["historical_memory"]["rows"]
            if isinstance(row, dict) and "file" in row
        ]

    assert files(after_result) == files(before_result)
    assert after["artifact_digest"] != before["artifact_digest"]
    assert after["correction_generation"] != before["correction_generation"]


def test_settlement_metadata_budget_overflow_fails_closed(repo_roots, monkeypatch):
    repo, _ = repo_roots
    _seed_settlement(repo, [f"receipt_{i:03d}.json" for i in range(6)])
    monkeypatch.setattr(sources, "MAX_MANIFEST_METADATA_BYTES", 40)
    receipt, result = _settlement_receipt(repo)
    assert receipt["status"] == "OVERSIZE"
    assert receipt["rows_returned"] == 0
    assert result["sections"]["historical_memory"]["coverage_state"] == "BLOCKED"
    assert "receipt_000.json" not in json.dumps(result["sections"]["historical_memory"])


def test_settlement_absent_directory_remains_a_complete_optional_absence(repo_roots):
    repo, _ = repo_roots
    _write_json(repo / "data/portfolios/autonomous/account.json", {"cash": 1.0, "positions": {}})
    receipt, result = _settlement_receipt(repo)
    assert receipt["status"] == "ABSENT_OPTIONAL"
    assert receipt["coverage_state"] == "COMPLETE"
    assert result["sections"]["historical_memory"]["coverage_state"] == "COMPLETE"


def test_no_emitted_receipt_claims_available_without_a_qualified_clock(repo_roots):
    """The composition-wide form of the contract invariant: whatever the world looks like,
    an AVAILABLE receipt always carries point-in-time knowledge."""
    repo, macro = repo_roots
    _full_capture_fixture(repo, macro)
    _seed_settlement(repo, ["r001.json"])
    result = sources.capture_all(
        "autonomous", decision_cutoff=_CUTOFF, recorded_at="2026-09-15T20:10:00Z",
    )
    available = [r for r in result["sources"] if r["status"] == "AVAILABLE"]
    assert available
    for receipt in available:
        assert receipt["known_at"] is not None
        assert receipt["clock_basis"] not in ("UNKNOWN", "UNQUALIFIED_EXTERNAL_CLOCK")


# ---------------------------------------------------------------------------
# Task 8 repair R7 — exact-head hardening on the external path
# ---------------------------------------------------------------------------

def test_external_filesystem_clock_floors_in_integer_nanosecond_space(repo_roots):
    """``st_mtime`` is a float64 and rounds up across a second boundary for large epochs;
    a permanently sealed evidentiary timestamp must never be one second late."""
    _, macro = repo_roots
    path = macro / "site/factor_betas.json"
    _write_json(path, {"betas": {}})
    ns = (_PRE_CUTOFF_EPOCH + 1) * 1_000_000_000 - 1
    os.utime(path, ns=(ns, ns))
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff=_CUTOFF,
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.factor_betas"]
    assert receipt["filesystem_observed_at"] == "2026-09-15T19:00:00Z"


@pytest.mark.parametrize("escape", ["../../etc/passwd", "/etc/passwd", "site/../../escape.json"])
def test_external_contract_path_outside_the_vendored_root_is_refused_unread(
    repo_roots, monkeypatch, escape,
):
    from control_plane import contracts as contracts_module
    monkeypatch.setattr(contracts_module, "contract", lambda key: {"path": escape})
    monkeypatch.setattr(
        sources, "_read_json_bytes",
        lambda path: pytest.fail(f"escaping contract path was read: {path}"),
    )
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff=_CUTOFF,
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.risk_envelope"]
    assert receipt["status"] == "INVALID"
    assert receipt["error_code"] == "CONTRACT_PATH_ESCAPE"


def test_external_contract_path_through_an_escaping_symlink_is_refused_unread(
    repo_roots, monkeypatch, tmp_path,
):
    _, macro = repo_roots
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"known_at": "2026-09-15T19:00:00Z"}), encoding="utf-8")
    link = macro / "site" / "escape.json"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)

    from control_plane import contracts as contracts_module
    monkeypatch.setattr(contracts_module, "contract", lambda key: {"path": "site/escape.json"})
    monkeypatch.setattr(
        sources, "_read_json_bytes",
        lambda path: pytest.fail(f"escaping contract path was read: {path}"),
    )
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff=_CUTOFF,
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.risk_envelope"]
    assert receipt["status"] == "INVALID"
    assert receipt["error_code"] == "CONTRACT_PATH_ESCAPE"


# ---------------------------------------------------------------------------
# Task 8 repair R1 — the unavailable-generation rule is closed over its metadata
# ---------------------------------------------------------------------------

_BASE_UNAVAILABLE = {
    "source_id": "book.pending_target",
    "status": "OVERSIZE",
    "error_code": "OVERSIZE",
    "size": 9_000_000,
}


@pytest.mark.parametrize("field,value", [
    ("source_id", "book.pending_orders"),
    ("status", "MISSING"),
    ("error_code", "SOURCE_CHANGED_DURING_READ"),
    ("size", 9_000_001),
])
def test_every_unavailable_metadata_field_changes_the_generation(field, value):
    """Each trustworthy metadata field is load-bearing on its own. If any one of them
    stopped discriminating, two materially different unavailable states could present one
    generation and a same-cutoff retry would reuse a snapshot describing the other."""
    stat_result = SimpleNamespace(st_mtime_ns=1_789_498_800_000_000_000, st_dev=1, st_ino=2)
    base = sources._unavailable_generation(**_BASE_UNAVAILABLE, stat_result=stat_result)
    variant = sources._unavailable_generation(
        **{**_BASE_UNAVAILABLE, field: value}, stat_result=stat_result
    )
    assert base != variant
    assert base == sources._unavailable_generation(**_BASE_UNAVAILABLE, stat_result=stat_result)


@pytest.mark.parametrize("attribute,value", [
    ("st_mtime_ns", 1_789_498_800_000_000_001),
    ("st_dev", 99),
    ("st_ino", 99),
])
def test_every_unavailable_identity_field_changes_the_generation(attribute, value):
    base_stat = {"st_mtime_ns": 1_789_498_800_000_000_000, "st_dev": 1, "st_ino": 2}
    base = sources._unavailable_generation(
        **_BASE_UNAVAILABLE, stat_result=SimpleNamespace(**base_stat)
    )
    variant = sources._unavailable_generation(
        **_BASE_UNAVAILABLE, stat_result=SimpleNamespace(**{**base_stat, attribute: value})
    )
    assert base != variant


def test_unavailable_generation_without_a_stat_is_distinct_from_one_with(repo_roots):
    with_stat = sources._unavailable_generation(
        **_BASE_UNAVAILABLE,
        stat_result=SimpleNamespace(st_mtime_ns=1, st_dev=1, st_ino=1),
    )
    assert with_stat != sources._unavailable_generation(**_BASE_UNAVAILABLE)


def test_oversize_source_rewritten_at_the_same_mtime_is_a_new_generation(repo_roots):
    """End-to-end proof that the filesystem metadata really reaches the generation: only the
    byte count differs here — same path, same inode, mtime pinned identical."""
    repo, _ = repo_roots
    book_dir = repo / "data/portfolios/autonomous"
    book_dir.mkdir(parents=True, exist_ok=True)
    path = book_dir / "pending_target.json"

    def capture_with(size: int) -> dict:
        path.write_bytes(b"x" * size)
        _set_pre_cutoff_mtime(path)
        return _by_id(sources.capture_book_state(
            "autonomous", decision_cutoff=_CUTOFF, recorded_at="2026-09-15T20:01:00Z",
        )["sources"])["book.pending_target"]

    first = capture_with(c.MAX_SOURCE_BYTES + 1)
    second = capture_with(c.MAX_SOURCE_BYTES + 2)
    assert first["status"] == second["status"] == "OVERSIZE"
    assert first["correction_generation"] != second["correction_generation"]


def test_oversize_source_touched_to_a_new_mtime_is_a_new_generation(repo_roots):
    repo, _ = repo_roots
    book_dir = repo / "data/portfolios/autonomous"
    book_dir.mkdir(parents=True, exist_ok=True)
    path = book_dir / "pending_target.json"
    path.write_bytes(b"x" * (c.MAX_SOURCE_BYTES + 1))
    _set_pre_cutoff_mtime(path)

    def generation() -> str:
        return _by_id(sources.capture_book_state(
            "autonomous", decision_cutoff=_CUTOFF, recorded_at="2026-09-15T20:01:00Z",
        )["sources"])["book.pending_target"]["correction_generation"]

    first = generation()
    os.utime(path, (_PRE_CUTOFF_EPOCH - 60, _PRE_CUTOFF_EPOCH - 60))
    assert generation() != first
