"""Point-in-time regressions for the canonical portfolio marking layer.

These cases prevent a historical/replay mark from consuming data whose observation date is after the
requested as-of date. They are deliberately offline: Polygon and Yahoo are injected or monkeypatched.
"""
from __future__ import annotations

import pytest

from portfolio import marks as M


def _none_polygon(_symbol: str):
    return None


def _none_yahoo(_symbol: str, _asof: str):
    return None


def test_future_dated_carry_is_not_consumed():
    result = M.mark_symbols(
        ["AAPL"],
        "2026-06-01",
        polygon_fn=_none_polygon,
        yahoo_fn=_none_yahoo,
        carry={"AAPL": {"price": 123.45, "asof": "2026-06-02", "source": "seed"}},
        persist=False,
    )
    assert "AAPL" not in result["prices"]
    assert result["counts"]["unpriced"] == 1
    assert result["sources"]["AAPL"]["source"] is None


@pytest.mark.parametrize("carry_asof", [None, "", "not-a-date"])
def test_carry_without_valid_observation_date_fails_closed(carry_asof):
    result = M.mark_symbols(
        ["AAPL"],
        "2026-06-01",
        polygon_fn=_none_polygon,
        yahoo_fn=_none_yahoo,
        carry={"AAPL": {"price": 123.45, "asof": carry_asof, "source": "seed"}},
        persist=False,
    )
    assert "AAPL" not in result["prices"]
    assert result["counts"]["unpriced"] == 1


def test_prior_carry_remains_usable_with_directional_staleness():
    result = M.mark_symbols(
        ["AAPL"],
        "2026-06-05",
        polygon_fn=_none_polygon,
        yahoo_fn=_none_yahoo,
        carry={"AAPL": {"price": 123.45, "asof": "2026-06-01", "source": "seed"}},
        persist=False,
    )
    assert result["prices"]["AAPL"] == pytest.approx(123.45)
    assert result["sources"]["AAPL"] == {
        "source": M.SOURCE_CARRY,
        "price": 123.45,
        "stale_days": 4,
    }


def test_historical_polygon_uses_exact_asof_aggregate_not_live_snapshot(monkeypatch):
    from data_layer import polygon

    observed = {}

    def fake_daily(symbol, start, end, cache=True):
        observed.update(symbol=symbol, start=start, end=end, cache=cache)
        return {"2026-06-01": 101.25}

    def forbidden_snapshot(_symbol):
        pytest.fail("historical mark must not consume the current Polygon snapshot")

    monkeypatch.setattr(polygon, "daily_closes", fake_daily)
    monkeypatch.setattr(polygon, "snapshot_price", forbidden_snapshot)

    assert M._polygon_eod("AAPL", "2026-06-01") == pytest.approx(101.25)
    assert observed == {
        "symbol": "AAPL",
        "start": "2026-06-01",
        "end": "2026-06-01",
        "cache": True,
    }


def test_historical_polygon_miss_does_not_fall_through_to_current_snapshot(monkeypatch):
    from data_layer import polygon

    monkeypatch.setattr(polygon, "daily_closes", lambda *args, **kwargs: {})
    monkeypatch.setattr(polygon, "snapshot_price", lambda _symbol: 999.0)

    assert M._polygon_eod("AAPL", "2026-06-01") is None


def test_current_day_polygon_can_still_use_snapshot_fallback(monkeypatch):
    from data_layer import polygon

    today = M.date.today().isoformat()
    monkeypatch.setattr(polygon, "daily_closes", lambda *args, **kwargs: {})
    monkeypatch.setattr(polygon, "snapshot_price", lambda _symbol: 111.5)

    assert M._polygon_eod("AAPL", today) == pytest.approx(111.5)
