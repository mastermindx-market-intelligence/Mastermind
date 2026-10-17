"""Synthetic replays of decision failure, later settlement, and strict read failures.

No live book, model, provider, scheduler, settlement, or account recovery is used.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, decision_availability as projection, response_cache, web
from portfolio import instrument_policy, paper_account, registry

OBSERVED = "2026-10-17T10:00:00+00:00"
SYMBOLS = {"autonomous": "AAPL", "china": "600519.SS", "hk": "0700.HK"}


def accepted(book="autonomous", *, cash_only=False, settled=False):
    ticker = SYMBOLS[book]
    target = {} if cash_only else {ticker: 0.2}
    result = {
        "asof": "2026-10-09", "ts": "2026-10-09T20:00:00+00:00",
        "decision_id": "decision.v1." + "a" * 24, "run_id": "synthetic-oct09",
        "target_status": "executed" if settled else "queued", "decision_effective": True,
        "summary": "Synthetic original investment memo.",
        "holdings": [{"ticker": key, "weight": value} for key, value in target.items()],
        "effective_holdings": [{"ticker": key, "weight": value} for key, value in target.items()],
        "submission_sha256": "b" * 64, "target_sha256": paper_account._target_sha256(target),
    }
    if settled:
        result.update(accepted_asof="2026-10-09", settled_asof="2026-10-12",
                      settlement_transaction_id="c" * 64, settlement_receipt_sha256="d" * 64,
                      settlement_fill_ids=[], executed=[])
    return result


def failed():
    return {
        "asof": "2026-10-15", "ts": "2026-10-15T20:00:00+00:00",
        "run_id": "synthetic-oct15", "target_status": "rejected_no_submission",
        "decision_effective": False, "holdings": [], "summary": None,
        "error": "CANARY_PRIVATE_PROVIDER_DETAIL /private/canary",
        "brain_text": "CANARY_PRIVATE_BRAIN_TRACE",
    }


def account(book="autonomous", *, priced=True):
    lot = {"shares": 10.0, "avg_cost": 99.0}
    if priced:
        lot.update(current_price=120.0, current_price_asof="2026-10-15",
                   current_price_source="paper_account_mark",
                   current_price_time_kind="portfolio_mark_date")
    return {"cash": 8000.0, "starting_nav": 10000.0, "positions": {SYMBOLS[book]: lot}}


def write(base, name, value):
    base.mkdir(parents=True, exist_ok=True)
    raw = "\n".join(json.dumps(row) for row in value) if name.endswith(".jsonl") else json.dumps(value)
    (base / name).write_text(raw)


def read(base, book="autonomous", observed=OBSERVED):
    return projection.read_decision_availability(
        book, base_dir=base, observed_at=observed,
        verify_receipt=web._decision_execution_receipt_verified,
        validate_pending=paper_account.pending_target_contract_error,
    )


def queue(book, row):
    target = {holding["ticker"]: holding["weight"] for holding in row["effective_holdings"]}
    return {
        "schema_version": paper_account.PENDING_TARGET_SCHEMA_V2,
        "engine_version": paper_account.US_BRAIN_ENGINE_V2,
        "portfolio_id": book, "asset_policy": instrument_policy.POLICY_NAME,
        "instrument_policy_version": instrument_policy.POLICY_VERSION,
        "asof": row["asof"], "queued_at": row["ts"], "target": target,
        "decision_snapshot": {
            "schema_version": paper_account.PENDING_DECISION_SCHEMA_V1,
            "portfolio_id": book, "decision_id": row["decision_id"],
            "submission": {"holdings": row["holdings"]}, "target_sha256": row["target_sha256"],
        },
    }


@pytest.mark.parametrize("book", SYMBOLS)
def test_failure_does_not_erase_origin_or_later_account_and_mark(tmp_path, book):
    row = accepted(book, settled=True)
    write(tmp_path, "decisions.jsonl", [row, failed()])
    write(tmp_path, "account.json", account(book))
    write(tmp_path, "nav_history.jsonl", [
        {"date": "2026-10-15", "nav": 9150, "cash": 7950, "invested": 1200},
    ])
    result = read(tmp_path, book)
    assert result["last_valid_decision"]["asof"] == "2026-10-09"
    assert result["latest_attempt"]["asof"] == "2026-10-15"
    assert result["latest_attempt_kind"] == "failed"
    assert result["accepted_target"]["settled_asof"] == "2026-10-12"
    assert result["accepted_target"]["execution_evidence"] == "receipt_identity_verified"
    assert result["accepted_target"]["execution_verification_scope"] == "decision_row_identity_only"
    assert result["accepted_target"]["durable_ledger_status"] == "not_checked"
    assert result["account"]["cash"] == 8000
    assert result["account"]["positions"][0]["shares"] == 10
    assert result["account"]["valuation"]["nav"] == 9200
    assert result["account"]["valuation"]["price_date_from"] == "2026-10-15"
    assert result["account"]["valuation"]["status"] == "provisional"
    assert result["account"]["last_recorded_nav"]["nav"] == 9150
    assert result["account"]["last_recorded_nav"]["account_binding"] == "unavailable"
    assert result["expected_opportunity"]["status"] == "unknown"
    assert result["attempt_coverage"] == "partial"
    assert "CANARY_PRIVATE" not in json.dumps(result)


def test_missing_account_is_not_fresh_or_empty_and_does_not_require_latest_snapshot(tmp_path):
    write(tmp_path, "decisions.jsonl", [accepted(cash_only=True)])
    result = read(tmp_path)
    assert result["last_valid_decision"]["submitted_holding_count"] == 0
    assert result["account"]["status"] == "missing"
    assert result["account"]["cash"] is None
    assert result["account"]["position_count"] is None
    assert result["account"]["valuation"]["nav"] is None
    assert not (tmp_path / "account.json").exists()
    assert not (tmp_path / "latest.json").exists()


def test_verified_empty_account_and_zero_nav_are_distinct_from_missing(tmp_path):
    write(tmp_path, "account.json", {"cash": 0, "positions": {}})
    result = read(tmp_path)["account"]
    assert result["status"] == "available"
    assert result["cash"] == 0
    assert result["position_count"] == 0
    assert result["valuation"]["status"] == "cash_only"
    assert result["valuation"]["nav"] == 0
    assert result["valuation"]["gross_exposure"] is None


@pytest.mark.parametrize("raw", ['{"cash":NaN,"positions":{}}', '{"cash":1,"cash":2,"positions":{}}',
                                '{"cash":2', '[]', 'null'])
def test_corrupt_account_is_invalid_without_repair_or_fallback(tmp_path, raw):
    (tmp_path / "account.json").write_text(raw)
    result = read(tmp_path)
    assert result["account"]["status"] == "invalid"
    assert result["account"]["cash"] is None
    assert result["consistency"]["status"] == "observed_stable"
    assert (tmp_path / "account.json").read_text() == raw


@pytest.mark.parametrize("cash,shares", [(True, 10), (8000, False), (8000, -1), ("8000", 10)])
def test_numeric_lookalikes_and_invalid_quantities_cannot_create_nav(tmp_path, cash, shares):
    raw = account()
    raw["cash"] = cash
    raw["positions"]["AAPL"]["shares"] = shares
    write(tmp_path, "account.json", raw)
    result = read(tmp_path)["account"]
    assert result["status"] == "partial"
    assert result["valuation"]["nav"] is None


@pytest.mark.parametrize("mutation", [
    {"current_price": None}, {"current_price_asof": "2099-10-01"},
    {"current_price_source": None}, {"current_price_time_kind": "unknown"},
    {"current_price": True},
])
def test_cost_basis_and_unqualified_marks_never_fill_a_price_gap(tmp_path, mutation):
    raw = account()
    raw["positions"]["AAPL"].update(mutation)
    write(tmp_path, "account.json", raw)
    result = read(tmp_path)["account"]
    assert result["cash"] == 8000
    assert result["positions"][0]["shares"] == 10
    assert result["valuation"]["nav"] is None
    assert result["valuation"]["missing_tickers"] == ["AAPL"]


def test_malformed_journal_tail_remains_partial_and_preserves_prior_valid_record(tmp_path):
    (tmp_path / "decisions.jsonl").write_text(json.dumps(accepted()) + '\n{"asof":')
    result = read(tmp_path)
    assert result["history_status"] == "partial"
    assert result["last_valid_decision"]["asof"] == "2026-10-09"
    assert result["sources"]["decisions"]["status"] == "partial"


def test_empty_journal_is_distinct_from_missing(tmp_path):
    missing = read(tmp_path)
    (tmp_path / "decisions.jsonl").write_text("")
    empty = read(tmp_path)
    assert missing["sources"]["decisions"]["status"] == "missing"
    assert empty["sources"]["decisions"]["status"] == "available"
    assert missing["last_valid_decision"] is empty["last_valid_decision"] is None


@pytest.mark.parametrize("book", SYMBOLS)
def test_canonical_pending_validation_and_identity_are_retained(tmp_path, book):
    row = accepted(book)
    write(tmp_path, "decisions.jsonl", [row])
    write(tmp_path, "pending_target.json", queue(book, row))
    pending = read(tmp_path, book)["accepted_target"]["pending"]
    assert pending["status"] == "queued"
    assert pending["lineage_status"] == "matched"
    assert pending["target"] == {SYMBOLS[book]: 0.2}


def test_mismatched_pending_identity_is_not_merged_into_the_original_decision(tmp_path):
    row = accepted()
    pending = queue("autonomous", row)
    pending["decision_snapshot"]["decision_id"] = "decision.v1." + "e" * 24
    write(tmp_path, "decisions.jsonl", [row])
    write(tmp_path, "pending_target.json", pending)
    result = read(tmp_path)
    assert result["accepted_target"]["pending"]["lineage_status"] == "conflict"
    assert result["last_valid_decision"]["decision_id"] == row["decision_id"]


def test_bare_empty_executions_do_not_prove_settled_no_trade(tmp_path):
    row = accepted(settled=True)
    row.pop("settlement_receipt_sha256")
    write(tmp_path, "decisions.jsonl", [row])
    result = read(tmp_path)["accepted_target"]
    assert result["target_status"] == "executed"
    assert result["execution_evidence"] == "unverified"
    assert result["fill_count"] is None


def test_accepted_with_adapter_error_keeps_target_and_redacts_error(tmp_path):
    row = accepted(cash_only=True)
    row["error"] = "CANARY_PRIVATE_ERROR"
    write(tmp_path, "decisions.jsonl", [row])
    result = read(tmp_path)
    assert result["latest_attempt_kind"] == "accepted_with_error"
    assert result["accepted_target"]["target_status"] == "queued"
    assert "CANARY_PRIVATE_ERROR" not in json.dumps(result)


def test_new_observation_cannot_refresh_decision_or_price_dates(tmp_path):
    write(tmp_path, "decisions.jsonl", [accepted(), failed()])
    write(tmp_path, "account.json", account())
    a, b = read(tmp_path), read(tmp_path, observed="2026-10-18T10:00:00+00:00")
    assert a["observed_at"] != b["observed_at"]
    for key in ("last_valid_decision", "latest_attempt", "account", "accepted_target"):
        assert a[key] == b[key]


def test_future_and_conflicting_nav_rows_remain_unavailable(tmp_path):
    write(tmp_path, "nav_history.jsonl", [
        {"date": "2026-10-15", "nav": 9000}, {"date": "2026-10-15", "nav": 9100},
        {"date": "2099-10-15", "nav": 15000},
    ])
    result = read(tmp_path)["account"]["last_recorded_nav"]
    assert result["date"] is None
    assert result["nav"] is None
    assert result["status"] == "partial"


def test_read_during_source_change_is_provisional(tmp_path, monkeypatch):
    write(tmp_path, "account.json", account())
    original = projection._signature
    calls = 0

    def signature(path):
        nonlocal calls
        result = original(path)
        if path.name == "account.json":
            calls += 1
            if calls == 2:
                return (*result[:3], result[3] + 1)
        return result

    monkeypatch.setattr(projection, "_signature", signature)
    result = read(tmp_path)
    assert result["consistency"]["status"] == "changed_during_read"
    assert result["account"]["status"] == "provisional"


@pytest.mark.parametrize("book", SYMBOLS)
def test_mounted_route_cannot_recover_quarantine_quote_or_write(tmp_path, monkeypatch, book):
    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    base = registry.data_dir(book)
    write(base, "account.json", account(book))
    write(base, "decisions.jsonl", [accepted(book), failed()])
    write(base, "paper_transaction.json", {"state": "prepared", "private": "CANARY_PRIVATE_WAL"})
    write(base, "pending_target.json", {"target": {SYMBOLS[book]: True}})
    write(base, "fills.jsonl", [{"synthetic": "untouched"}])

    def forbidden(*args, **kwargs):
        raise AssertionError("side_effect_or_quote_called")

    for name in ("_load_account", "_load_account_file", "_fresh_account", "mark", "nav",
                 "positions_pnl", "settle_target", "rebalance", "preflight_pending_target",
                 "quarantine_pending_target", "accrue_cash_yield", "_recover_paper_transaction_unlocked"):
        monkeypatch.setattr(paper_account, name, forbidden)
    for name in ("_book_marks", "_book_quote_provenance", "_portfolio_dir"):
        monkeypatch.setattr(web, name, forbidden)

    def files():
        return {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in base.rglob("*") if p.is_file()}

    before = files()
    app = FastAPI()
    app.include_router(web.router)
    response_cache.install(app)
    auth.install(app)
    monkeypatch.setenv("MASTERMIND_RESP_CACHE_TTL", "30")
    response_cache.clear()
    client = TestClient(app)  # no lifespan, scheduler, or live account setup
    for _ in range(2):
        response = client.get("/api/portfolio", params={"portfolio": book, "view": "decision_availability"})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert "x-mm-cache" not in response.headers
        result = response.json()
        assert result["consistency"]["transaction"] == "present"
        assert result["account"]["status"] == "provisional"
        assert result["accepted_target"]["pending"]["status"] == "invalid"
        assert "CANARY_PRIVATE" not in response.text
    assert files() == before
    assert not response_cache._CACHE


@pytest.mark.parametrize("book", ["flagship", "heavyweight", "etf", "self_directed"])
def test_archived_and_manual_books_are_explicitly_out_of_scope_without_reads(tmp_path, book):
    result = read(tmp_path / "does-not-exist", book)
    assert result["status"] == "not_applicable"
    assert not tmp_path.joinpath("does-not-exist").exists()


def test_unknown_portfolio_and_view_fail_closed_without_fallback():
    app = FastAPI()
    app.include_router(web.router)
    client = TestClient(app)
    assert client.get("/api/portfolio?portfolio=typo&view=decision_availability").status_code == 404
    assert client.get("/api/portfolio?portfolio=autonomous&view=typo").status_code == 400


def test_response_does_not_alias_retained_inputs(tmp_path):
    row = accepted()
    write(tmp_path, "decisions.jsonl", [row])
    before = copy.deepcopy(row)
    result = read(tmp_path)
    result["last_valid_decision"]["summary"] = "changed"
    assert read(tmp_path)["last_valid_decision"]["summary"] == before["summary"]


@pytest.mark.parametrize("status", [{}, [], ["queued"]])
def test_mounted_corrupt_decision_field_is_a_qualified_response(tmp_path, monkeypatch, status):
    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    base = registry.data_dir("autonomous")
    row = accepted()
    row["target_status"] = status
    write(base, "decisions.jsonl", [row])
    app = FastAPI()
    app.include_router(web.router)
    response = TestClient(app).get("/api/portfolio?portfolio=autonomous&view=decision_availability")
    assert response.status_code == 200
    result = response.json()
    assert result["last_valid_decision"] is None
    assert result["history_status"] == "partial"


def test_explicit_wrong_book_account_nav_and_queue_do_not_cross_bind(tmp_path):
    write(tmp_path, "account.json", {**account(), "portfolio_id": "hk"})
    write(tmp_path, "nav_history.jsonl", [{"date": "2026-10-15", "nav": 9999, "book": "hk"}])
    row = accepted()
    pending = queue("autonomous", row)
    pending["book"] = "hk"
    write(tmp_path, "pending_target.json", pending)
    result = read(tmp_path)
    assert result["account"]["cash"] is None
    assert result["account"]["status"] == "invalid"
    assert result["account"]["last_recorded_nav"]["nav"] is None
    assert result["accepted_target"]["pending"]["status"] == "invalid"


def test_pit_read_bounds_and_summary_truncation_are_explicit(tmp_path, monkeypatch):
    row = accepted()
    row["summary"] = "memo " * 3000
    write(tmp_path, "decisions.jsonl", [row])
    result = read(tmp_path)
    assert result["last_valid_decision"]["summary_truncated"] is True
    monkeypatch.setattr(projection, "_MAX_BYTES", 100)
    bounded = read(tmp_path)
    assert bounded["sources"]["decisions"]["status"] == "invalid"
    assert bounded["sources"]["decisions"]["issues"] == ["source_too_large"]
    assert bounded["last_valid_decision"] is None


@pytest.mark.parametrize("queued_at", ["2099-01-01T00:00:00+00:00", "2026-10-09T20:00:00", None, "bad"])
def test_pending_clock_errors_are_visible_without_rewriting_queue(tmp_path, queued_at):
    row = accepted()
    pending = queue("autonomous", row)
    pending["queued_at"] = queued_at
    write(tmp_path, "pending_target.json", pending)
    before = (tmp_path / "pending_target.json").read_bytes()
    result = read(tmp_path)
    assert result["accepted_target"]["pending"]["status"] == "queued"
    assert result["accepted_target"]["pending"]["clock_status"] == "invalid"
    assert "pending_target_clock_invalid" in result["issues"]
    assert (tmp_path / "pending_target.json").read_bytes() == before


def test_validator_failure_is_unavailable_not_artifact_invalid(tmp_path):
    write(tmp_path, "pending_target.json", queue("autonomous", accepted()))
    def unavailable(*args):
        raise OSError("CANARY_PRIVATE_PROVIDER")
    result = projection.read_decision_availability(
        "autonomous", base_dir=tmp_path, observed_at=OBSERVED,
        verify_receipt=web._decision_execution_receipt_verified, validate_pending=unavailable,
    )
    assert result["accepted_target"]["pending"]["status"] == "unavailable"
    assert "CANARY_PRIVATE" not in json.dumps(result)
