"""End-to-end truthfulness for the Self-Directed interactive read model.

Unknown market value must stay unknown from the portfolio primitive through the API/UI contract.
Cost basis is execution history, not a market mark.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portfolio import self_directed as SD


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    data = tmp_path / "self_directed"
    monkeypatch.setattr(SD, "_DATA", data)
    monkeypatch.setattr(SD, "_ACCOUNT_PATH", data / "account.json")
    monkeypatch.setattr(SD, "_FILLS_PATH", data / "fills.jsonl")
    monkeypatch.setattr(SD, "_PENDING_PATH", data / "pending.json")
    monkeypatch.setattr(SD, "_THESES_PATH", data / "theses.json")
    monkeypatch.setattr(SD, "_NAV_PATH", data / "nav_history.jsonl")
    monkeypatch.setattr(SD, "_PUBLISHED_PATH", tmp_path / "published" / "latest.json")
    monkeypatch.setattr(SD, "_today", lambda: "2026-06-02")
    monkeypatch.setattr(SD, "_market_status", lambda: {"is_open": False, "session": "closed"})
    monkeypatch.setattr(SD, "_carry_stale_max_days", lambda: 30)
    SD.set_price_resolver(None)
    yield tmp_path
    SD.set_price_resolver(None)


def _state(positions: dict, *, cash: float = 500_000.0) -> dict:
    return {
        "inception_date": "2026-05-01",
        "starting_nav": 1_000_000.0,
        "cash": cash,
        "positions": positions,
    }


def _pos(*, shares=1_000.0, avg_cost=100.0, current=None, current_asof=None) -> dict:
    row = {"shares": shares, "avg_cost": avg_cost}
    if current is not None:
        row["current_price"] = current
    if current_asof is not None:
        row["current_price_asof"] = current_asof
    return row


def test_unpriced_holding_makes_aggregate_valuation_unknown_not_cost_basis(sandbox):
    SD._save_account(_state({"AAPL": _pos(avg_cost=100.0)}))

    book = SD.book(prices={}, read_only=True, resolve_missing_prices=False)

    assert book["valuation_complete"] is False
    assert book["unpriced_tickers"] == ["AAPL"]
    assert book["nav"] is None
    assert book["invested"] is None
    assert book["positions"][0]["current_price"] is None
    assert book["positions"][0]["market_value"] is None
    assert book["positions"][0]["weight"] is None
    alloc = book["allocation"]
    assert alloc["cash_pct"] is None
    assert alloc["invested_pct"] is None
    assert alloc["gross"] is None
    assert alloc["largest_weight"] is None
    assert alloc["total_unrealized_pnl"] is None
    assert alloc["total_return_pct"] is None


def test_bounded_persisted_market_mark_completes_read_model(sandbox):
    SD._save_account(_state({
        "AAPL": _pos(avg_cost=100.0, current=150.0, current_asof="2026-06-01"),
    }))

    book = SD.book(prices={}, read_only=True, resolve_missing_prices=False)

    assert book["valuation_complete"] is True
    assert book["unpriced_tickers"] == []
    assert book["nav"] == pytest.approx(650_000.0)
    assert book["invested"] == pytest.approx(150_000.0)
    row = book["positions"][0]
    assert row["current_price"] == 150.0
    assert row["market_value"] == pytest.approx(150_000.0)
    assert row["weight"] == pytest.approx(150_000.0 / 650_000.0, abs=1e-6)
    assert book["allocation"]["total_unrealized_pnl"] == pytest.approx(50_000.0)


def test_one_unpriced_line_invalidates_total_weights_but_keeps_known_line_detail(sandbox):
    SD._save_account(_state({
        "AAPL": _pos(shares=1_000.0, avg_cost=100.0),
        "MSFT": _pos(shares=500.0, avg_cost=200.0),
    }))

    book = SD.book(
        prices={"MSFT": 220.0}, read_only=True, resolve_missing_prices=False
    )

    by = {row["ticker"]: row for row in book["positions"]}
    assert book["valuation_complete"] is False
    assert book["unpriced_tickers"] == ["AAPL"]
    assert book["nav"] is None and book["invested"] is None
    assert by["MSFT"]["current_price"] == 220.0
    assert by["MSFT"]["market_value"] == pytest.approx(110_000.0)
    assert by["MSFT"]["unrealized_pnl"] == pytest.approx(10_000.0)
    assert by["MSFT"]["weight"] is None
    assert by["AAPL"]["current_price"] is None
    assert book["allocation"]["total_unrealized_pnl"] is None


def test_empty_book_remains_complete_cash_valuation(sandbox):
    SD._save_account(_state({}, cash=1_000_000.0))

    book = SD.book(prices={}, read_only=True, resolve_missing_prices=False)

    assert book["valuation_complete"] is True
    assert book["unpriced_tickers"] == []
    assert book["nav"] == pytest.approx(1_000_000.0)
    assert book["invested"] == pytest.approx(0.0)
    assert book["allocation"]["cash_pct"] == pytest.approx(1.0)


def test_api_failure_never_fabricates_fresh_million_dollar_book(monkeypatch):
    from app import web

    monkeypatch.setattr(SD, "_load_account", lambda: (_ for _ in ()).throw(RuntimeError("secret detail")))

    response = web.api_self_directed()
    payload = json.loads(response.body)

    assert payload["nav"] is None
    assert payload["cash"] is None
    assert payload["invested"] is None
    assert payload["valuation_complete"] is False
    assert payload["error"] == "self_directed_unavailable"
    assert "secret detail" not in response.body.decode("utf-8")


def test_self_directed_ui_has_no_million_dollar_unknown_fallback():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()

    assert "fmtNav(b.nav != null ? b.nav : 1000000)" not in html
    assert "Self-Directed valuation unavailable" in html
    assert "Self-Directed portfolio data unavailable" in html
