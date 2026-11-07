"""Real selected-price producers survive ACK interruption and mounted pure reads.

Composition contract: #1420 Yahoo clocks, #1614 capture/decoder, #1608 retention,
and the landed decision-availability reader. Only market I/O, clocks, the market
open guard, and external publication are synthetic; no decoder is substituted.
"""
from __future__ import annotations

import importlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest


BOOKS = {
    "autonomous": ("AAPL", "SPY", "USD", 100.0, "bot.autonomous"),
    "china": ("600519.SS", "000300.SS", "CNY", 70.0, "bot.china"),
    "hk": ("0700.HK", "^HSI", "HKD", 78.0, "bot.hk"),
}
POLYGON_UPDATED = 1791896400123456789  # Opaque provider integer, not an Open clock.


def _file_bytes(base):
    return {str(p.relative_to(base)): p.read_bytes()
            for p in base.rglob("*") if p.is_file()}


def _source_inputs(monkeypatch, tmp_path, prices):
    import requests
    from data_layer import polygon, tushare_feed, yahoo_feed
    from lib import store
    from portfolio import fx, paper_account as paper

    state = {
        "now": datetime(2026, 10, 12, 20, tzinfo=timezone.utc), "mono": 1000.0,
        "prices": dict(prices), "rates": {"CNH=X": 7.0, "HKD=X": 7.8},
        "yahoo": {}, "polygon": {}, "fx": {}, "calls": [],
        "forbidden": [], "sealed": False,
    }

    def forbidden(label):
        def stop(*args, **kwargs):
            state["forbidden"].append(label)
            raise AssertionError(label)
        return stop

    def transport(label):
        if state["sealed"]:
            forbidden("post-commit " + label)()
        state["calls"].append(label)

    def advance(seconds):
        state["now"] += timedelta(seconds=seconds)
        state["mono"] += seconds

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return (state["now"].astimezone(tz) if tz is not None
                    else state["now"].replace(tzinfo=None))

    class LocalDate(date):
        @classmethod
        def today(cls):
            return state["now"].date()

    def download(symbols, **kwargs):
        transport("yahoo:" + ",".join(symbols))
        assert kwargs == {"period": "7d", "progress": False,
                          "auto_adjust": False, "threads": False}
        assert symbols and set(symbols) <= set(state["prices"])
        started = state["now"].isoformat()
        advance(3)
        for symbol in symbols:
            state["yahoo"][symbol] = (started, state["now"].isoformat())
        index = pd.DatetimeIndex(["2026-10-12", "2026-10-13"])
        # The US benchmark selects today's Open. Regional books must select the
        # prior non-null Close, not today's different Open or retrieval date.
        closes = {s: [state["prices"][s], float("nan")] for s in symbols}
        opens = {s: [state["prices"][s] - 2.0,
                     state["prices"][s] if s == "SPY" else state["prices"][s] + 2.0]
                 for s in symbols}
        return pd.concat({"Close": pd.DataFrame(closes, index=index),
                          "Open": pd.DataFrame(opens, index=index)}, axis=1)

    def request(url, *, params, timeout):
        symbol = url.rsplit("/", 1)[-1]
        transport("polygon:" + symbol)
        assert url == "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/" + symbol
        assert symbol in {"AAPL", "SPY"}
        assert params == {"apiKey": "synthetic-fixture-key"} and timeout == 6
        started = state["now"].isoformat()
        advance(4)
        state["polygon"][symbol] = (started, state["now"].isoformat())
        payload = {"ticker": symbol, "updated": POLYGON_UPDATED,
                   "day": {"o": state["prices"][symbol] if symbol == "AAPL" else None}}
        return SimpleNamespace(ok=True, json=lambda: {"ticker": payload})

    def store_read(provider, symbol):
        transport("fx:" + symbol)
        assert provider == "yahoo" and symbol in state["rates"]
        started = state["now"].isoformat()
        advance(1)
        state["fx"][symbol] = (started, state["now"].isoformat())
        return pd.DataFrame({"close": [state["rates"][symbol], float("nan")]},
                            index=pd.DatetimeIndex(["2026-10-09", "2026-10-12"]))

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=download))
    monkeypatch.setattr(requests, "get", request)
    monkeypatch.setattr(store, "read", store_read)
    monkeypatch.setenv("POLYGON_API_KEY", "synthetic-fixture-key")
    monkeypatch.setenv("YAHOO_FEED_TTL_SEC", "120")
    # Replace module bindings, not the shared time module used by the API loop.
    monkeypatch.setattr(yahoo_feed, "time", SimpleNamespace(monotonic=lambda: state["mono"]))
    monkeypatch.setattr(yahoo_feed, "datetime", Clock)
    monkeypatch.setattr(yahoo_feed, "_today", lambda: state["now"].date().isoformat())
    for name in ("_CACHE", "_OPEN_CACHE", "_TS", "_ASOF", "_CLOSE_EVIDENCE",
                 "_OPEN_EVIDENCE", "_HISTORY_CACHE", "_HISTORY_TS"):
        monkeypatch.setattr(yahoo_feed, name, {})
    monkeypatch.setattr(yahoo_feed, "_FETCHED_DAY", None)
    monkeypatch.setattr(yahoo_feed, "_INFLIGHT", set())
    monkeypatch.setattr(polygon, "time", SimpleNamespace(time=lambda: state["now"].timestamp()))
    monkeypatch.setattr(polygon, "_snapshot_clock", lambda: state["now"])
    monkeypatch.setattr(polygon, "_snapshot_cache", {})
    monkeypatch.setattr(polygon, "_snapshot_observations", {})
    monkeypatch.setattr(polygon, "_TTL", 60)
    monkeypatch.setattr(fx, "date", LocalDate)
    monkeypatch.setattr(fx, "_V", tmp_path / "empty_macro")
    monkeypatch.setattr(fx, "_RATE_CACHE", {})
    monkeypatch.setattr(fx, "_RATE_CONTEXT", {})
    monkeypatch.setattr(fx._fx_evidence, "clock", lambda: state["now"].isoformat())
    monkeypatch.setattr(paper, "datetime", Clock)
    monkeypatch.setattr(paper, "_ROOT", tmp_path / "empty_source")
    monkeypatch.setattr(paper, "_fetch_price_series", forbidden("unexpected engine price fallback"))
    monkeypatch.setattr(tushare_feed, "price_local", forbidden("unexpected Tushare fallback"))
    state["Clock"], state["stop"] = Clock, forbidden
    return state


def _assert_producer_context(captured, state, book, prices):
    ticker, benchmark, currency, _, _ = BOOKS[book]
    assert captured["schema"] == "mastermind.settlement_price_evidence.v1"
    assert captured["currency"] == currency and captured["omitted_quote_count"] == 0
    assert captured["market_observed_at"] is None
    assert captured["execution_qualification"] == "not_checked"
    assert {s: q["price"] for s, q in captured["quotes"].items()} == prices
    for symbol, quote in captured["quotes"].items():
        assert quote["binding_status"] == "matched" and quote["reason"] is None
        root = quote["observation"]
        assert root["stage"] == "settlement_selection"
        assert root["price"] == prices[symbol] and root["currency"] == currency
        assert root["market_observed_at"] is None
        assert root["execution_qualification"] == "not_checked"
        if book == "autonomous":
            source = "polygon_open" if symbol == ticker else "yahoo_open"
            assert quote["source"] == root["source"] == source
            selected = root["upstream"]
            assert selected["stage"] == "us_open_selection" and selected["source"] == source
            upstream = selected["upstream"]
            if symbol == ticker:
                started, returned = state["polygon"][symbol]
                assert upstream["schema"] == "mastermind.polygon_snapshot_evidence.v1"
                assert upstream["status"] == "available" and upstream["field"] == "day.o"
                assert upstream["payload_ticker_status"] == "matched"
                assert upstream["source_updated_raw"] == str(POLYGON_UPDATED)
                assert upstream["source_updated_unit"] == "not_established"
                assert upstream["source_bar_label"] is None
                assert upstream["request_started_at"] == upstream["cache_anchor_at"] == started
                assert upstream["response_returned_at"] == upstream["cache_age_observed_at"] == returned
                assert upstream["cache_age_seconds"] == 4.0
                assert upstream["within_cache_ttl"] is True
                assert upstream["market_observed_at"] is None
                assert upstream["execution_qualification"] == "not_checked"
                continue
            assert symbol == benchmark
            assert upstream["schema"] == "mastermind.yahoo_daily_bar_evidence.v2"
            assert upstream["field"] == "Open"
            assert upstream["source_bar_label"] == "2026-10-13T00:00:00"
            assert upstream["cache_refresh_basis"] == "shared_close_cache"
        else:
            assert quote["source"] == root["source"] == "last_price"
            current = root["upstream"]
            assert current["stage"] == "paper_current" and current["source"] == "live_price"
            native = current["upstream"]
            assert native["stage"] == "paper_live" and native["source"] == "yahoo_close"
            assert root["fx_operation"] == "multiply" and native["fx_operation"] == "divide"
            assert root["fx_observation"] == native["fx_observation"] == "matched"
            fx_symbol = "CNH=X" if currency == "CNY" else "HKD=X"
            rate = 7.0 if currency == "CNY" else 7.8
            assert native["input_price"] == prices[symbol]
            assert native["price"] == current["price"] == prices[symbol] / rate
            assert root["input_price"] == native["price"]
            for conversion in (native, root):
                observation = conversion["fx_rate"]
                assert observation["source"] == "yahoo_store" and observation["symbol"] == fx_symbol
                assert observation["rate"] == rate and observation["currency"] == currency
                assert observation["source_bar_label"] == "2026-10-09T00:00:00"
                assert observation["source_bar_label_kind"] == "selected_close_index"
                assert observation["cache_population_day"] == "2026-10-13"
                assert observation["source_read_started_at"] == state["fx"][fx_symbol][0]
                assert observation["source_read_returned_at"] == state["fx"][fx_symbol][1]
                assert observation["consumed_as"] == "foreign_units_per_USD"
                assert observation["source_convention_qualification"] == "not_established"
                assert observation["market_observed_at"] is None
                assert observation["execution_qualification"] == "not_checked"
            assert root["fx_rate"]["cache_state"] == "hit"
            upstream = native["upstream"]
            assert upstream["schema"] == "mastermind.yahoo_daily_bar_evidence.v1"
            assert upstream["field"] == "Close"
            assert upstream["source_bar_label"] == "2026-10-12T00:00:00"
        assert upstream["status"] == "available"
        assert upstream["price_local"] == prices[symbol]
        assert upstream["source_bar_label_kind"] == "daily_bar_label"
        assert upstream["fetch_started_at"] == state["yahoo"][symbol][0]
        assert upstream["download_returned_at"] == state["yahoo"][symbol][1]
        assert upstream["fetch_age_seconds"] == 3.0 and upstream["within_cache_ttl"] is True
        assert upstream["market_observed_at"] is None
        assert upstream["execution_qualification"] == "not_checked"


def _assert_mounted_reads(monkeypatch, state, book, base, row, receipt, captured, *, active):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import auth, response_cache, web
    from portfolio import paper_account as paper

    validated = []
    real_validate = paper.validated_settlement_receipt_prices

    def validate(value):
        validated.append(value["transaction_id"])
        return real_validate(value)

    app = FastAPI()
    app.include_router(web.router)
    response_cache.install(app)
    auth.install(app)
    response_cache.clear()
    monkeypatch.setenv("MASTERMIND_RESP_CACHE_TTL", "30")
    before = _file_bytes(base)
    with monkeypatch.context() as read_patch:
        # Delegate the canonical validator; the default decoder is completely real.
        read_patch.setattr(paper, "validated_settlement_receipt_prices", validate)
        for name in ("_load_account", "_load_account_file", "_save_account", "_fresh_account",
                     "mark", "nav", "positions_pnl", "recover_paper_transaction",
                     "_recover_paper_transaction_unlocked", "preflight_pending_target",
                     "quarantine_pending_target", "accrue_cash_yield",
                     "settlement_receipt_fills_are_durable", "acknowledge_settlement_receipt"):
            read_patch.setattr(paper, name, state["stop"]("mounted read: " + name))
        for name in ("_book_marks", "_book_quote_provenance", "_portfolio_dir"):
            read_patch.setattr(web, name, state["stop"]("mounted read: " + name))
        with TestClient(app) as client:
            for _ in range(2):
                response = client.get("/api/portfolio", params={
                    "portfolio": book, "view": "decision_availability",
                })
                assert response.status_code == 200, response.text
                assert response.headers["cache-control"] == "no-store"
                assert "x-mm-cache" not in response.headers
                inspection = response.json()["settlement_price_inspection"]
                assert inspection["decision_id"] == row["decision_id"]
                assert inspection["transaction_id"] == receipt["transaction_id"]
                assert inspection["receipt_sha256"] == row["settlement_receipt_sha256"]
                assert inspection["receipt_linkage"] == "matched"
                assert inspection["status"] == ("provisional" if active else "available")
                assert inspection["reason"] == ("active_receipt_still_present" if active else None)
                assert inspection["receipt_location"] == ("both" if active else "acknowledged")
                assert inspection["consistency"] == "observed_stable"
                assert inspection["settlement_asof"] == "2026-10-13"
                assert inspection["fill_count"] == len(row["executed"])
                assert inspection["selected_price_count"] == 2
                assert inspection["context_status"] == "available"
                assert inspection["context_validation_scope"] == "selected_prices_sources_and_bounded_capture_contract"
                assert inspection["price_context"] == captured
                assert inspection["execution_qualification"] == "not_checked"
                assert inspection["durable_ledger_status"] == "not_checked"
    assert validated == [receipt["transaction_id"], receipt["transaction_id"]]
    assert _file_bytes(base) == before
    assert not response_cache._CACHE and not state["forbidden"]


@pytest.mark.parametrize("book", BOOKS)
@pytest.mark.parametrize("weight", [0.20, 1e-9], ids=["filled", "zero_fill"])
def test_real_producer_receipt_retry_and_default_mounted_decoder(monkeypatch, tmp_path, book, weight):
    from bot import decision_rows, settle
    from brain import provider_waterfall
    from data_layer import polygon, yahoo_feed
    from portfolio import fx, paper_account as paper, registry

    ticker, benchmark, _, native, module_name = BOOKS[book]
    prices = {ticker: native, benchmark: native * 5.0}
    monkeypatch.setattr(registry, "_ROOT", tmp_path / "books")
    state = _source_inputs(monkeypatch, tmp_path, prices)
    module = importlib.import_module(module_name)
    monkeypatch.setattr(module, "datetime", state["Clock"])
    monkeypatch.setattr(module, "_run_brain", state["stop"]("unexpected PM invocation"))
    monkeypatch.setattr(provider_waterfall, "reason", state["stop"]("unexpected provider invocation"))
    monkeypatch.setattr(settle, "is_open", lambda _book: True)
    monkeypatch.setattr(settle, "_republish", lambda *a, **k: {"ok": True})
    paper._save_account({
        "inception_date": "2026-10-01", "starting_nav": 1_000_000.0,
        "cash": 1_000_000.0, "positions": {}, "spy_shares": None, "spy_inception_price": None,
    }, book)
    target = {ticker: weight}
    submission = {
        "schema": "mastermind.target_book.v2",
        "holdings": [{"ticker": ticker, "weight": weight, "action": "add",
                      "action_effective": "add", "rationale": "original retained-price thesis"}],
        "summary": "原始决策 — exact receipt-bound provenance",
    }
    module._append_decision_log("2026-10-12", submission, [], [], {},
                                target_status="queued", effective_target=target)
    paper.save_pending_target(target, "2026-10-12", portfolio_id=book, decision_snapshot=submission)
    pending = json.loads(paper._pending_target_path(book).read_bytes())
    state["now"] = datetime(2026, 10, 13, 15, tzinfo=timezone.utc)
    atomic_write = paper._atomic_write_bytes
    unlink = paper._durable_unlink
    committed, interrupted = [], []

    def observe_receipt_commit(path, payload):
        result = atomic_write(path, payload)
        path = Path(path)
        if path.parent.name == "settlement_receipts" and path.suffix == ".json":
            # Observe the completed storage boundary, then forbid pricing even
            # during the first real finalizer, before the interrupted ACK.
            committed.append(path)
            state["sealed"] = True
            state["source_calls_at_commit"] = list(state["calls"])
            for owner, names in (
                (settle, ("_price_and_sources", "_open_price_usd")),
                (paper, ("_current_price", "_live_price", "_pending_clear_transition", "settle_target", "rebalance")),
                (yahoo_feed, ("warm", "price_local", "open_price_local")),
                (polygon, ("day_open",)),
                (fx, ("rate_per_usd", "to_usd", "usd_to")),
            ):
                for name in names:
                    monkeypatch.setattr(owner, name, state["stop"]("post-commit " + name))
        return result

    def fail_active_unlink(path):
        path = Path(path)
        if path.parent.name == "settlement_receipts" and path.suffix == ".json":
            archive = path.parent / "acknowledged" / path.name
            # The actual retention owner has already written the exact preimage.
            assert archive.read_bytes() == path.read_bytes()
            interrupted.append(path)
            raise OSError("synthetic active receipt unlink interruption")
        return unlink(path)

    with monkeypatch.context() as fault:
        fault.setattr(paper, "_atomic_write_bytes", observe_receipt_commit)
        fault.setattr(paper, "_durable_unlink", fail_active_unlink)
        first = settle.settle_open(book, "2026-10-13")
    assert first["ok"] is False and first["skipped"] == "settlement_receipt_ack_pending", first
    assert first["receipt_retained"] is True and len(interrupted) == 1
    receipt, = paper.pending_settlement_receipts(book)
    transaction_id = receipt["transaction_id"]
    active = paper._settlement_receipt_path(transaction_id, book)
    archive = active.parent / "acknowledged" / active.name
    raw = active.read_bytes()
    assert committed == interrupted == [active] and archive.read_bytes() == raw
    assert first["transaction_id"] == transaction_id
    assert transaction_id == paper._content_sha256(receipt["transaction_identity"])
    followup = receipt["transaction_identity"]["followup"]
    assert followup["pending_payload"] == pending
    assert receipt["decision_snapshot"] == pending["decision_snapshot"]
    assert paper.validated_settlement_receipt_prices(receipt) == prices
    fills = paper.validated_settlement_receipt_fills(receipt)
    assert len(fills) == (1 if weight == 0.20 else 0)
    captured = followup["settlement_price_evidence"]
    _assert_producer_context(captured, state, book, prices)
    assert len(state["calls"]) == 3
    assert set(state["yahoo"]) == ({benchmark} if book == "autonomous" else set(prices))
    assert set(state["polygon"]) == (set(prices) if book == "autonomous" else set())
    assert set(state["fx"]) == ({"CNH=X"} if book == "china" else {"HKD=X"} if book == "hk" else set())
    base = registry.data_dir(book)
    journal = base / "decisions.jsonl"
    rows = [json.loads(line) for line in journal.read_text().splitlines() if line]
    row, = [r for r in rows if r.get("settlement_transaction_id") == transaction_id]
    assert row["target_status"] == "executed"
    assert row["settlement_receipt_sha256"] == decision_rows._canonical_sha256(receipt)
    assert row["settlement_fill_ids"] == [f["fill_id"] for f in fills]
    assert len(row["executed"]) == len(fills)
    numeric = {key: path.read_bytes() if path.exists() else None
               for key, path in paper._paths(book).items() if key in {"account", "fills", "nav"}}
    decision_bytes = journal.read_bytes()
    source_calls = state["source_calls_at_commit"]

    state["now"] += timedelta(days=1)
    state["mono"] += 86400
    state["prices"] = {symbol: value + 900.0 for symbol, value in prices.items()}
    state["rates"] = {"CNH=X": 14.0, "HKD=X": 15.6}
    # The pure settlement_snapshot constructor stays real: the default decoder
    # uses it to validate retained context without fetching or recapturing prices.
    _assert_mounted_reads(monkeypatch, state, book, base, row, receipt, captured, active=True)
    retried = settle.settle_open(book, "2026-10-14")
    assert retried["ok"] is True and retried["receipt_acknowledged"] is True, retried
    assert retried["settlement_recovered"] is True
    assert retried["transaction_id"] == transaction_id and retried["executed"] == first["executed"]
    assert not active.exists() and archive.read_bytes() == raw
    assert paper.pending_settlement_receipts(book) == []
    assert paper.validated_settlement_receipt_fills(json.loads(archive.read_bytes())) == fills
    assert journal.read_bytes() == decision_bytes
    assert {key: path.read_bytes() if path.exists() else None
            for key, path in paper._paths(book).items() if key in numeric} == numeric
    _assert_mounted_reads(monkeypatch, state, book, base, row, receipt, captured, active=False)
    assert state["calls"] == source_calls and not state["forbidden"]
