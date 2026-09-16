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
        (settlement_dir / f"receipt_{i:03d}.json").write_text("{}", encoding="utf-8")

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
    assert receipt["correction_generation"].startswith("sha256:")
    assert receipt["rows_total"] == 0
    assert receipt["rows_returned"] == 0
    assert receipt["omitted_rows"] == 0
    assert any(
        gap["code"] == "FUTURE_AT_CUTOFF" and gap["source_id"] == "book.account"
        and gap["section_id"] == "book_truth"
        for gap in result["gaps"]
    )
