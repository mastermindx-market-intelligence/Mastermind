"""Closed-market EOD valuation contract for every active portfolio.

These tests keep the display carry outside execution: published/persisted marks may value the
dashboard while the exchange is shut, but only explicit trusted prices can ever reach rebalance.
"""
from __future__ import annotations

import json

import pytest


def _closed_session(market: str = "SSE/SZSE") -> dict:
    return {
        "venue": "CN", "market": market, "timezone": "Asia/Shanghai",
        "is_open": False, "state": "pre_open", "trading_day": True,
        "holiday": False, "as_of": "2026-08-12T05:00:00+08:00",
        "next_open": "2026-08-12T09:30:00+08:00", "poll_after_seconds": 16_200,
    }


@pytest.mark.parametrize(
    ("portfolio_id", "ticker", "price"),
    [
        ("china", "600519.SS", 1_512.25),
        ("hk", "0700.HK", 581.50),
        ("autonomous", "AAPL", 228.75),
    ],
)
def test_all_brain_books_read_last_closed_eod_in_base_currency(
    tmp_path, monkeypatch, portfolio_id, ticker, price,
):
    from app import web

    base = tmp_path / portfolio_id
    base.mkdir()
    (base / "account.json").write_text(json.dumps({
        "cash": 500_000.0, "starting_nav": 1_000_000.0,
        "positions": {ticker: {"shares": 10.0, "avg_cost": price - 5.0}},
    }))
    closed_at = {
        "china": "2026-08-11T16:01:00+08:00",
        "hk": "2026-08-11T17:01:00+08:00",
        "autonomous": "2026-08-11T19:01:00-04:00",
    }[portfolio_id]
    (base / "latest.json").write_text(json.dumps({
        "as_of": "2026-08-11",
        "market_status": {
            "open": False, "trading_day": True, "asof": closed_at,
        },
        "positions": [{"ticker": ticker, "current_price": price}],
    }))
    monkeypatch.setattr(web, "_portfolio_dir", lambda pid=None: base)

    quote = web._persisted_book_quotes(
        portfolio_id, [ticker], asof="2026-08-12T05:00:00+08:00"
    )[ticker]
    assert quote["price_local"] == price
    assert quote["source"] == "portfolio_eod"
    assert quote["as_of"] == "2026-08-11"
    assert quote["stale_days"] == 1
    assert quote["fresh"] is False


def test_persisted_mark_rejects_future_and_over_30_day_staleness(tmp_path, monkeypatch):
    from app import web

    base = tmp_path / "china"
    base.mkdir()
    monkeypatch.setattr(web, "_portfolio_dir", lambda pid=None: base)

    def write(as_of: str) -> None:
        (base / "latest.json").write_text(json.dumps({
            "as_of": as_of,
            "market_status": {"open": False, "trading_day": True},
            "positions": [{"ticker": "600519.SS", "current_price": 1_500.0}],
        }))

    write("2026-08-13")
    assert web._persisted_book_quotes(
        "china", ["600519.SS"], asof="2026-08-12"
    ) == {}

    write("2026-07-12")  # 31 days before the requested point in time
    assert web._persisted_book_quotes(
        "china", ["600519.SS"], asof="2026-08-12"
    ) == {}


def test_china_closed_endpoint_prices_every_row_and_nav_from_eod(
    tmp_path, monkeypatch,
):
    from app import web
    from data_layer import yahoo_feed
    from portfolio import market_sessions, paper_account

    ticker = "600519.SS"
    state = {
        "cash": 500.0, "starting_nav": 1_000.0, "inception_date": "2026-08-01",
        "positions": {ticker: {"shares": 10.0, "avg_cost": 40.0, "current_price": 50.0}},
    }
    base = tmp_path / "china"
    base.mkdir()
    (base / "account.json").write_text(json.dumps(state))
    (base / "latest.json").write_text(json.dumps({
        "as_of": "2026-08-11",
        "market_status": {
            "open": False, "trading_day": True,
            "asof": "2026-08-11T16:01:00+08:00",
        },
        "positions": [{"ticker": ticker, "current_price": 50.0}],
    }))
    monkeypatch.setattr(web, "_portfolio_dir", lambda pid=None: base)
    monkeypatch.setattr(web, "_dash_mark_usd", lambda ticker: None)
    monkeypatch.setattr(web, "_quote_provenance", lambda tickers: {})
    monkeypatch.setattr(market_sessions, "status_for_portfolio", lambda pid: _closed_session())
    monkeypatch.setattr(yahoo_feed, "warm", lambda tickers: pytest.fail("closed market fetched live"))
    monkeypatch.setattr(paper_account, "_load_account", lambda pid=None: state)

    seen: dict = {}

    def performance(portfolio_id=None, prices=None):
        seen["prices"] = dict(prices or {})
        current_nav = paper_account.nav(prices or {}, portfolio_id=portfolio_id)
        return {
            "inception_date": "2026-08-01", "starting_nav": 1_000.0,
            "current_nav": current_nav, "cash": 500.0,
            "invested": current_nav - 500.0, "total_return_pct": 0.0,
        }

    monkeypatch.setattr(paper_account, "performance", performance)

    payload = json.loads(web.api_live_marks("china").body)
    assert seen["prices"] == {ticker: 50.0}
    assert payload["pricing"] == {
        "priced_positions": 1, "total_positions": 1, "complete": True,
    }
    assert payload["performance"]["current_nav"] == 1_000.0
    row = payload["positions"][0]
    assert row["current_price"] == 50.0
    assert row["market_value"] == 500.0
    assert row["unrealized_pnl"] == 100.0
    assert row["quote_source"] == "portfolio_eod"
    assert row["quote_as_of"] == "2026-08-11"
    assert row["quote_is_live"] is False


def test_hot_quote_wins_over_persisted_eod(tmp_path, monkeypatch):
    from app import web
    from data_layer import yahoo_feed
    from portfolio import market_sessions

    base = tmp_path / "autonomous"
    base.mkdir()
    (base / "account.json").write_text(json.dumps({
        "cash": 500.0, "starting_nav": 1_000.0,
        "positions": {"AAPL": {"shares": 2.0, "avg_cost": 40.0}},
    }))
    (base / "latest.json").write_text(json.dumps({
        "as_of": "2026-08-11",
        "market_status": {"open": False, "trading_day": True},
        "positions": [{"ticker": "AAPL", "current_price": 50.0}],
    }))
    monkeypatch.setattr(web, "_portfolio_dir", lambda pid=None: base)
    monkeypatch.setattr(web, "_account_tickers", lambda pid=None: ["AAPL"])
    monkeypatch.setattr(web, "_dash_mark_usd", lambda ticker: 60.0)
    monkeypatch.setattr(web, "_quote_provenance", lambda tickers: {
        "AAPL": {
            "source": "yahoo_intraday", "as_of": "2026-08-12T14:00:00Z",
            "time_kind": "feed_retrieval", "price_local": 60.0,
        }
    })
    monkeypatch.setattr(
        market_sessions,
        "status_for_portfolio",
        lambda pid: {**_closed_session("NYSE"), "is_open": True, "state": "open"},
    )
    monkeypatch.setattr(yahoo_feed, "warm", lambda tickers, background=False: None)

    assert web._book_marks("autonomous", refresh=False) == {"AAPL": 60.0}


def test_newer_persisted_eod_beats_older_terminal_snapshot(tmp_path, monkeypatch):
    from app import web
    from portfolio import market_sessions

    base = tmp_path / "autonomous"
    base.mkdir()
    (base / "account.json").write_text(json.dumps({
        "cash": 500.0, "starting_nav": 1_000.0,
        "positions": {"AAPL": {"shares": 2.0, "avg_cost": 40.0}},
    }))
    (base / "latest.json").write_text(json.dumps({
        "as_of": "2026-08-11",
        "market_status": {
            "open": False, "trading_day": True,
            "asof_et": "2026-08-11T19:00:00-04:00",
        },
        "positions": [{"ticker": "AAPL", "current_price": 50.0}],
    }))
    monkeypatch.setattr(web, "_portfolio_dir", lambda pid=None: base)
    monkeypatch.setattr(web, "_account_tickers", lambda pid=None: ["AAPL"])
    monkeypatch.setattr(web, "_dash_mark_usd", lambda ticker: 40.0)
    monkeypatch.setattr(web, "_quote_provenance", lambda tickers: {
        "AAPL": {
            "source": "terminal_snapshot", "as_of": "2026-08-09",
            "time_kind": "snapshot_market_date", "price_local": 40.0,
        }
    })
    monkeypatch.setattr(
        market_sessions, "status_for_portfolio",
        lambda pid: {
            **_closed_session("NYSE"), "timezone": "America/New_York",
            "as_of": "2026-08-12T05:00:00-04:00",
        },
    )

    assert web._book_marks("autonomous", refresh=False) == {"AAPL": 50.0}
    provenance = web._book_quote_provenance("autonomous", ["AAPL"])["AAPL"]
    assert provenance["source"] == "portfolio_eod"
    assert provenance["as_of"] == "2026-08-11"


def test_terminal_provenance_uses_market_asof_not_fresh_file_mtime(tmp_path, monkeypatch):
    from data_layer import terminal_prices

    stockdata = tmp_path / "vendor" / "macro" / "site" / "stockdata"
    stockdata.mkdir(parents=True)
    (stockdata / "AAPL.json").write_text(json.dumps({
        "ticker": "AAPL", "asof": "2026-08-09", "tech": {"price": 40.0},
    }))
    monkeypatch.setattr(terminal_prices, "_ROOT", tmp_path)

    quote = terminal_prices.quote_local("AAPL")
    assert quote["as_of"] == "2026-08-09"
    assert quote["time_kind"] == "snapshot_market_date"


def test_dashboard_carry_is_not_an_execution_price(tmp_path, monkeypatch):
    from app import web
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(
        web,
        "_persisted_book_quotes",
        lambda *args, **kwargs: {"AAPL": {"price_local": 999.0}},
    )

    paper_account.rebalance(
        {"AAPL": 0.5}, {"AAPL": 100.0}, "2026-08-11", portfolio_id="autonomous"
    )
    fills = paper_account._load_jsonl(paper_account._paths("autonomous")["fills"])
    assert fills and fills[-1]["price"] == 100.0
    assert paper_account._load_account("autonomous")["positions"]["AAPL"]["avg_cost"] == 100.0


def test_missing_daily_quote_retains_last_observed_mark_not_cost(tmp_path, monkeypatch):
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path, raising=False)
    paper_account.rebalance(
        {"AAPL": 0.5}, {"AAPL": 100.0}, "2026-08-10", portfolio_id="autonomous"
    )
    paper_account.mark(
        {"AAPL": 110.0, "SPY": 500.0}, "2026-08-10", portfolio_id="autonomous"
    )
    paper_account.mark(
        {"SPY": 501.0}, "2026-08-11", portfolio_id="autonomous"
    )

    lot = paper_account._load_account("autonomous")["positions"]["AAPL"]
    assert lot["current_price"] == 110.0
    assert lot["current_price_asof"] == "2026-08-10"
    assert lot["current_price_source"] == "paper_account_mark"
    assert lot["current_price"] != lot["avg_cost"]


def test_dashboard_labels_persisted_marks_as_prior_not_live():
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text()
    assert "last closed EOD" in html
    assert "quote_source === 'portfolio_eod'" in html
    assert "hasSnapshot && !hasPersisted" in html
