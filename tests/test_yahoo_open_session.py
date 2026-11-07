"""Offline public-feed regressions: an old daily bar is not today's open."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from data_layer import yahoo_feed


@pytest.fixture
def feed(monkeypatch):
    clock = {"now": datetime(2026, 10, 13, 15, tzinfo=timezone.utc), "mono": 1000.0}
    download = {"frame": None, "calls": 0}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = clock["now"]
            return value.astimezone(tz) if tz is not None else value.replace(tzinfo=None)

    def fetch(tickers, **kwargs):
        download["calls"] += 1
        assert kwargs == {
            "period": "7d", "progress": False, "auto_adjust": False, "threads": False,
        }
        return download["frame"].copy()

    monkeypatch.setattr(yahoo_feed, "datetime", Clock)
    monkeypatch.setattr(yahoo_feed, "_today", lambda: clock["now"].date().isoformat())
    monkeypatch.setattr(yahoo_feed.time, "monotonic", lambda: clock["mono"])
    monkeypatch.setenv("YAHOO_FEED_TTL_SEC", "120")
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=fetch))
    yahoo_feed.clear_cache()
    yield clock, download
    yahoo_feed.clear_cache()


def _bars(shape, dates, opens, closes, ticker="AAPL"):
    index = pd.DatetimeIndex(dates)
    if shape == "series":
        return pd.DataFrame({"Open": opens, "Close": closes}, index=index)
    return pd.concat({
        "Open": pd.DataFrame({ticker: opens}, index=index),
        "Close": pd.DataFrame({ticker: closes}, index=index),
    }, axis=1)


@pytest.mark.parametrize("shape", ["series", "multi"])
@pytest.mark.parametrize("dates,opens,closes", [
    (["2026-10-12"], [180.0], [190.0]),
    (["2026-10-12", "2026-10-13"], [180.0, float("nan")], [190.0, 202.0]),
    (["2026-10-14"], [205.0], [210.0]),
])
def test_unavailable_today_open_does_not_reuse_another_session(feed, shape, dates, opens, closes):
    _, download = feed
    download["frame"] = _bars(shape, dates, opens, closes)

    assert yahoo_feed.open_price_local("AAPL") is None
    # Daily close availability/freshness remains independent of Open's session date.
    assert yahoo_feed.price_cached("AAPL") == closes[-1]
    assert yahoo_feed.quote_cached("AAPL")["fresh"] is True


@pytest.mark.parametrize("shape", ["series", "multi"])
def test_current_open_and_latest_close_keep_separate_values(feed, shape):
    _, download = feed
    download["frame"] = _bars(shape, ["2026-10-12", "2026-10-13"], [180.0, 200.0], [190.0, 202.0])

    assert yahoo_feed.open_price_local(" aapl ") == 200.0
    assert yahoo_feed.price_cached("AAPL") == 202.0
    assert yahoo_feed.open_price_local("AAPL") == 200.0
    assert download["calls"] == 1


@pytest.mark.parametrize("ticker,now,bar_date", [
    ("AAPL", "2026-10-14T00:30:00+00:00", "2026-10-13"),
    ("0700.HK", "2026-10-13T01:35:00+00:00", "2026-10-13"),
    ("600519.SS", "2026-10-13T01:35:00+00:00", "2026-10-13"),
    ("000001.SZ", "2026-10-13T01:35:00+00:00", "2026-10-13"),
    ("^HSI", "2026-10-13T01:35:00+00:00", "2026-10-13"),
])
def test_open_date_is_exchange_local_not_utc(feed, ticker, now, bar_date):
    clock, download = feed
    clock["now"] = datetime.fromisoformat(now)
    download["frame"] = _bars("multi", [bar_date], [200.0], [202.0], ticker)

    assert yahoo_feed.open_price_local(ticker) == 200.0


@pytest.mark.parametrize("ticker,now,stamp", [
    ("AAPL", "2026-10-14T00:30:00+00:00", "2026-10-13T00:00:00-04:00"),
    ("0700.HK", "2026-10-13T01:35:00+00:00", "2026-10-12T16:00:00+00:00"),
    ("600519.SS", "2026-10-13T01:35:00+00:00", "2026-10-13T00:00:00+08:00"),
])
def test_aware_bar_timestamps_are_compared_in_exchange_timezone(feed, ticker, now, stamp):
    clock, download = feed
    clock["now"] = datetime.fromisoformat(now)
    download["frame"] = _bars("multi", [stamp], [200.0], [202.0], ticker)

    assert yahoo_feed.open_price_local(ticker) == 200.0


@pytest.mark.parametrize("ticker,before,after,bar_date", [
    ("AAPL", "2026-10-14T03:59:30+00:00", "2026-10-14T04:00:30+00:00", "2026-10-13"),
    ("0700.HK", "2026-10-13T15:59:30+00:00", "2026-10-13T16:00:30+00:00", "2026-10-13"),
    ("600519.SS", "2026-10-13T15:59:30+00:00", "2026-10-13T16:00:30+00:00", "2026-10-13"),
])
def test_cached_open_expires_at_exchange_midnight_even_inside_ttl(feed, ticker, before, after, bar_date):
    clock, download = feed
    clock["now"] = datetime.fromisoformat(before)
    download["frame"] = _bars("multi", [bar_date], [200.0], [202.0], ticker)
    assert yahoo_feed.open_price_local(ticker) == 200.0

    clock["now"] = datetime.fromisoformat(after)
    clock["mono"] += 60
    assert yahoo_feed.open_price_local(ticker) is None
    assert yahoo_feed.price_cached(ticker) == 202.0
    assert download["calls"] == 1


def test_old_yahoo_bar_uses_existing_last_price_fallback_label(feed):
    from bot.settle import _open_price_usd

    _, download = feed
    download["frame"] = _bars("multi", ["2026-10-12"], [180.0], [190.0])
    # Exercise the real feed and production consumer; only unavailable Polygon and
    # the unrelated final quote source use the consumer's existing injection seams.
    result = _open_price_usd("AAPL", _polygon=lambda _: None, _paper=lambda _: 202.0)

    assert result == (202.0, "last_price")


def test_current_yahoo_open_keeps_existing_source_precedence(feed):
    from bot.settle import _open_price_usd

    _, download = feed
    download["frame"] = _bars("multi", ["2026-10-13"], [200.0], [202.0])
    assert _open_price_usd("AAPL", _polygon=lambda _: None, _paper=lambda _: 202.0) == (200.0, "yahoo_open")
    assert _open_price_usd("AAPL", _polygon=lambda _: 199.0, _paper=lambda _: 202.0) == (199.0, "polygon_open")


def test_missing_open_column_and_empty_symbol_remain_unavailable(feed):
    _, download = feed
    download["frame"] = pd.DataFrame({"Close": [202.0]}, index=pd.DatetimeIndex(["2026-10-13"]))
    assert yahoo_feed.open_price_local("AAPL") is None
    assert yahoo_feed.open_price_local("") is None
    assert yahoo_feed.price_cached("AAPL") == 202.0
