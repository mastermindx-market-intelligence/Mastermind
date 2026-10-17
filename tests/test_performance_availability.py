"""Adverse integration cases for persisted performance, using synthetic books only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from portfolio.performance_read import read_performance_sources


def paths(root):
    return {"data": root, "account": root / "account.json", "nav": root / "nav_history.jsonl"}


def state(**updates):
    return {"inception_date": "2026-10-01", "starting_nav": 10000.0,
            "cash": 4000.0, "positions": {"EXAMPLE": {"shares": 60, "avg_cost": 100}},
            **updates}


def write_account(root, value=None):
    root.mkdir(parents=True, exist_ok=True)
    (root / "account.json").write_text(json.dumps(state() if value is None else value))


def history(root):
    rows = [
        {"date": "2026-10-01", "nav": 10000, "cash": 4000, "invested": 6000},
        {"date": "2026-10-09", "nav": 10400, "cash": 4200, "invested": 6200},
    ]
    (root / "nav_history.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))


def fingerprint(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def forbidden(*_args, **_kwargs):
    raise AssertionError("forbidden performance-read effect")


@pytest.fixture
def book(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from portfolio import paper_account, registry
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 17, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(paper_account, "datetime", FixedDatetime)
    root = tmp_path / "china"
    write_account(root)
    history(root)
    monkeypatch.setattr(registry, "data_dir", lambda portfolio_id=None: tmp_path / (portfolio_id or "flagship"))
    monkeypatch.setattr(paper_account, "_DATA", tmp_path / "flagship")
    monkeypatch.setattr(paper_account, "_ACCOUNT_PATH", tmp_path / "flagship" / "account.json")
    monkeypatch.setattr(paper_account, "_NAV_PATH", tmp_path / "flagship" / "nav_history.jsonl")
    monkeypatch.setattr(paper_account, "_load_spy_history",
                        lambda *_a, **_k: [("2026-10-01", 4000), ("2026-10-09", 4200)])
    return root


def test_reader_missing_account_is_not_a_fresh_account(tmp_path):
    before = {str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*")}
    result = read_performance_sources(paths(tmp_path), "china")
    assert result["state"] is None
    assert result["account_status"] == "missing"
    assert result["history_status"] == "missing"
    assert {str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*")} == before


@pytest.mark.parametrize("raw", [
    '{"cash":4000,"cash":9000,"positions":{}}',
    '{"cash":NaN,"positions":{}}',
    "[]", "{BROKEN", '{"portfolio_id":"hk","cash":4000,"positions":{}}',
])
def test_invalid_account_bytes_are_qualified(tmp_path, raw):
    (tmp_path / "account.json").write_text(raw)
    result = read_performance_sources(paths(tmp_path), "china")
    assert result["state"] is None
    assert result["account_status"] == "invalid"
    assert "BROKEN" not in json.dumps(result)


def test_bad_tail_and_foreign_row_remain_partial(tmp_path):
    write_account(tmp_path)
    history(tmp_path)
    with (tmp_path / "nav_history.jsonl").open("a") as stream:
        stream.write('{BROKEN\n{"portfolio_id":"hk","date":"2026-10-16","nav":90000}\n')
    result = read_performance_sources(paths(tmp_path), "china")
    assert result["history_status"] == "partial"
    assert len(result["rows"]) == 2


def test_changed_sources_do_not_claim_a_consistent_account(tmp_path, monkeypatch):
    from portfolio import performance_read
    write_account(tmp_path)
    original = performance_read._signature
    count = 0
    def changed(path):
        nonlocal count
        count += 1
        result = original(path)
        return result + ("changed",) if count == 4 else result
    monkeypatch.setattr(performance_read, "_signature", changed)
    result = read_performance_sources(paths(tmp_path), "china")
    assert result["consistency"] == "changed"
    assert result["transaction_pending"] is True


def test_valid_recorded_snapshot_uses_same_row_cash_and_common_benchmark_dates(book):
    from portfolio import paper_account
    result = paper_account.performance("china")
    assert result["current_nav"] == 10400
    assert result["cash"] == 4200  # not current account cash=4000
    assert result["invested"] == 6200
    assert result["total_return_pct"] == pytest.approx(4)
    assert result["vs_benchmark_pct"] == pytest.approx(-1)
    assert result["availability"]["as_of"] == "2026-10-09"
    assert result["benchmark"] == "000300.SS"
    assert result["benchmark_name"] == "CSI 300"


def test_unknown_or_missing_book_never_borrows_default(book):
    from portfolio import paper_account
    write_account(book.parent / "flagship", state(cash=999999, positions={}))
    unknown = paper_account.performance("not-a-book")
    assert unknown["portfolio_id"] is None
    assert unknown["benchmark"] is None
    missing = paper_account.performance("hk")
    assert missing["portfolio_id"] == "hk"
    assert missing["current_nav"] is None
    assert missing["starting_nav"] is None
    assert missing["benchmark"] == "^HSI"


@pytest.mark.parametrize("cash,positions", [(True, {}), (float("inf"), {}), (100, {"EXAMPLE": {}})])
def test_numeric_poison_cannot_generate_a_complete_valuation(book, cash, positions):
    from portfolio import paper_account
    write_account(book, state(cash=cash, positions=positions))
    result = paper_account.performance("china", prices={"EXAMPLE": 100})
    assert result["current_nav"] is None
    assert result["availability"]["account_status"] == "invalid"
    json.dumps(result, allow_nan=False)


def test_legitimate_zero_account_is_not_unavailable(book):
    from portfolio import paper_account
    write_account(book, state(cash=0, positions={}))
    (book / "nav_history.jsonl").unlink()
    result = paper_account.performance("china")
    assert result["current_nav"] == 0
    assert result["cash"] == 0
    assert result["total_return_pct"] == -100
    assert result["day_change_pct"] is None
    assert result["max_drawdown_pct"] is None


@pytest.mark.parametrize("pending", [False, True])
def test_pending_transaction_and_mounted_get_have_no_book_or_provider_effect(book, monkeypatch, pending):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import web, response_cache
    from portfolio import paper_account
    from data_layer import yahoo_feed

    from unittest.mock import Mock
    denied = Mock(side_effect=forbidden)
    if pending:
        (book / "paper_transaction.json").write_text('{"secret":"WAL_CANARY"}')
    before = fingerprint(book)
    for name in ("_load_account", "_load_account_file", "_fresh_account",
                 "_recover_paper_transaction_unlocked", "_save_account", "nav", "mark", "rebalance"):
        monkeypatch.setattr(paper_account, name, denied)
    monkeypatch.setattr(web, "_book_marks", denied)
    monkeypatch.setattr(yahoo_feed, "warm", denied)
    monkeypatch.setattr(response_cache, "_ttl", lambda: 60)
    app = FastAPI()
    app.include_router(web.router)
    response_cache.install(app)
    client = TestClient(app)
    for _ in range(2):
        response = client.get("/api/performance?portfolio=china")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers.get("x-mm-cache") is None
        result = response.json()
        if pending:
            assert result["current_nav"] is None
            assert result["total_return_pct"] is None
            assert result["availability"]["status"] == "unavailable"
        else:
            assert result["current_nav"] == 10400
            assert result["total_return_pct"] == pytest.approx(4)
            assert result["availability"]["valuation_basis"] == "last_recorded_nav"
        assert "WAL_CANARY" not in response.text
    denied.assert_not_called()
    assert fingerprint(book) == before


def test_route_exception_is_null_and_does_not_leak_error(book, monkeypatch):
    from app import web
    from portfolio import paper_account
    def fail(**_kwargs):
        raise RuntimeError("PROVIDER_SECRET_CANARY")
    monkeypatch.setattr(paper_account, "performance", fail)
    response = web.api_performance("china")
    result = json.loads(response.body)
    assert result["current_nav"] is None
    assert result["cash"] is None
    assert result["vs_spy_pct"] is None
    assert result["inception_date"] is None
    assert result["benchmark"] == "000300.SS"
    assert "PROVIDER_SECRET_CANARY" not in response.body.decode()


def test_regional_benchmark_cache_read_never_fetches_or_advances_cache_clock(monkeypatch):
    import pandas as pd
    from data_layer import yahoo_feed
    from portfolio import paper_account
    import sys
    from types import SimpleNamespace
    store = SimpleNamespace(read=lambda *_a, **_k: None)
    monkeypatch.setitem(sys.modules, "lib", SimpleNamespace(store=store))
    series = pd.Series([4000, 4200], index=pd.to_datetime(["2026-10-01", "2026-10-09"]))
    monkeypatch.setattr(yahoo_feed, "_HISTORY_CACHE", {("000300.SS", "2y"): series})
    monkeypatch.setattr(yahoo_feed, "_HISTORY_TS", {("000300.SS", "2y"): 12.0})
    monkeypatch.setattr(yahoo_feed, "history_local", forbidden)
    monkeypatch.setattr(yahoo_feed, "_reset_if_stale", forbidden)
    monkeypatch.setattr(store, "read", lambda *_a, **_k: None)
    result = paper_account._load_spy_history(504, "000300.SS")
    assert result == [("2026-10-01", 4000.0), ("2026-10-09", 4200.0)]
    assert yahoo_feed._HISTORY_TS == {("000300.SS", "2y"): 12.0}
    returned = yahoo_feed.history_cached("000300.SS")
    returned.iloc[0] = 1
    assert series.iloc[0] == 4000


def test_old_account_episode_cannot_become_current_baseline_performance(book):
    from portfolio import paper_account
    write_account(book, state(inception_date="2026-10-12", starting_nav=2_000_000))
    result = paper_account.performance("china")
    assert result["current_nav"] is None
    assert result["total_return_pct"] is None
    assert result["vs_benchmark_pct"] is None
    assert result["day_change_pct"] is None
    assert result["max_drawdown_pct"] is None
    assert result["realized_since"] is None


def test_sparse_observations_publish_their_actual_metric_windows(book):
    from portfolio import paper_account
    result = paper_account.performance("china")
    assert result["day_change_pct"] == pytest.approx(4)
    assert result["day_change_window"] == {"from": "2026-10-01", "to": "2026-10-09"}
    assert result["drawdown_window"] == {"from": "2026-10-01", "to": "2026-10-09"}
    assert result["return_measure"] == "nav_change_from_starting_capital"
    assert result["external_flow_adjustment"] == "not_applied"
    assert result["benchmark_return_basis"] == "cached_close_series"
    assert result["benchmark_total_return_status"] == "unverified"
    assert result["availability"]["account_history_binding"] == "book_path_only"


@pytest.mark.parametrize("key,account_value,row_value", [
    ("starting_nav", 10000, 20000),
    ("inception_date", "2026-10-01", "2026-10-02"),
    ("episode_id", "current", "other"),
    ("account_id", "current", "other"),
])
def test_explicit_account_history_metadata_conflict_cannot_make_a_return(
        book, key, account_value, row_value):
    from portfolio import paper_account
    write_account(book, state(**{key: account_value}))
    row = {"date": "2026-10-09", "nav": 10400, "cash": 4200, "invested": 6200,
           key: row_value}
    (book / "nav_history.jsonl").write_text(json.dumps(row) + "\n")
    result = paper_account.performance("china")
    assert result["current_nav"] is None
    assert result["total_return_pct"] is None
    assert result["vs_benchmark_pct"] is None
    assert "history_account_metadata_conflict" in result["availability"]["issues"]


@pytest.mark.parametrize("source", ["account", "history"])
def test_explicit_foreign_currency_is_not_labeled_as_native_book_performance(book, source):
    from portfolio import paper_account
    if source == "account":
        write_account(book, state(currency="USD"))
    else:
        row = {"date": "2026-10-09", "nav": 10400, "cash": 4200,
               "invested": 6200, "currency": "USD"}
        (book / "nav_history.jsonl").write_text(json.dumps(row) + "\n")
    result = paper_account.performance("china")
    assert result["current_nav"] is None
    assert result["total_return_pct"] is None
    assert result["currency"] == "CNY"
