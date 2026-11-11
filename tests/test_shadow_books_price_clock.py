"""Point-in-time regressions for shadow-book price gathering.

The canonical marks layer owns dated prices. The legacy paper-account accessor is undated/current,
so it may only fill a miss when the requested shadow mark is for today.
"""
from __future__ import annotations

import pytest

import bot  # noqa: F401 — bootstrap vendored macro for portfolio imports used by the fallback
from portfolio import marks
from portfolio import paper_account
from portfolio import shadow_books as S


def test_historical_shadow_gather_never_calls_undated_current_price(monkeypatch):
    observed = {}

    def fake_marks(want, asof, **kwargs):
        observed["asof"] = asof
        observed["want"] = set(want)
        return {}

    def forbidden_current(_ticker):
        pytest.fail("historical replay must not consume paper_account._current_price")

    monkeypatch.setattr(marks, "prices_for", fake_marks)
    monkeypatch.setattr(paper_account, "_current_price", forbidden_current)

    result = S._gather_prices({"AAA"}, seed=None, asof="2026-06-01")

    assert observed["asof"] == "2026-06-01"
    assert "AAA" in observed["want"]
    assert "AAA" not in result


def test_same_day_shadow_gather_can_use_current_price_as_emergency_fallback(monkeypatch):
    today = S.date.today().isoformat()
    monkeypatch.setattr(marks, "prices_for", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        paper_account,
        "_current_price",
        lambda ticker: {"AAA": 123.0, "SPY": 500.0}.get(ticker),
    )

    result = S._gather_prices({"AAA"}, seed=None, asof=today)

    assert result["AAA"] == pytest.approx(123.0)
    assert result["SPY"] == pytest.approx(500.0)


def test_explicit_seed_remains_authoritative_on_historical_replay(monkeypatch):
    monkeypatch.setattr(marks, "prices_for", lambda want, asof, **kwargs: dict(kwargs.get("seed") or {}))
    monkeypatch.setattr(
        paper_account,
        "_current_price",
        lambda _ticker: pytest.fail("historical seeded replay must not call current price"),
    )

    result = S._gather_prices({"AAA"}, seed={"AAA": 88.0}, asof="2026-06-01")

    assert result["AAA"] == pytest.approx(88.0)
