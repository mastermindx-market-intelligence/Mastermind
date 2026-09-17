"""Truthful degradation for the active-book performance API and dashboard."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_api_performance_failure_is_unknown_not_fabricated(monkeypatch) -> None:
    from app import web
    from portfolio import paper_account

    monkeypatch.setattr(web, "_book_marks", lambda _portfolio: {})
    monkeypatch.setattr(
        paper_account,
        "performance",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("secret backend detail")),
    )

    response = web.api_performance("autonomous")
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["error"] == "performance_unavailable"
    for key in (
        "inception_date", "starting_nav", "current_nav", "cash", "invested",
        "total_return_pct", "vs_benchmark_pct", "vs_spy_pct", "day_change_pct",
        "max_drawdown_pct", "realized_since",
    ):
        assert payload[key] is None, key
    assert payload["series"] == []
    assert "secret backend detail" not in response.body.decode("utf-8")


def test_api_performance_success_is_unchanged_passthrough(monkeypatch) -> None:
    from app import web
    from portfolio import paper_account

    expected = {
        "starting_nav": 1_000_000.0,
        "current_nav": 1_125_000.0,
        "cash": 125_000.0,
        "invested": 1_000_000.0,
        "total_return_pct": 12.5,
        "benchmark": "SPY",
        "series": [{"date": "2026-09-16", "nav": 1_125_000.0}],
    }
    monkeypatch.setattr(web, "_book_marks", lambda _portfolio: {"AAPL": 123.0})
    monkeypatch.setattr(paper_account, "performance", lambda **kwargs: dict(expected))

    response = web.api_performance("autonomous")
    assert json.loads(response.body) == expected


def test_performance_ui_clears_stale_values_and_names_unavailable_state() -> None:
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()

    assert "Performance unavailable" in html
    assert "performance unavailable" in html.lower()
    assert "p.error === 'performance_unavailable'" in html
    assert "cashLbl.textContent = t('perf.cash_lbl') + ' ' + fmtNav(p.cash);" in html
    assert "rangeEl.textContent = series.length ?" in html
