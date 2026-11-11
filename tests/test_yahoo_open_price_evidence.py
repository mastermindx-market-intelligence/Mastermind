"""Open evidence uses the selected tuple's own retrieval generation.

Synthetic daily bars and clocks only. Existing source priority and refresh policy remain.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from data_layer import yahoo_feed

SCHEMA = "mastermind.yahoo_daily_bar_evidence.v2"


@pytest.fixture
def feed(monkeypatch):
    clock = {"now": datetime(2026, 10, 13, 15, tzinfo=timezone.utc), "mono": 1000.0}
    download = {"frame": None, "calls": [], "fail": False, "duration": 3.0}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = clock["now"]
            return value.astimezone(tz) if tz is not None else value.replace(tzinfo=None)

    def fetch(tickers, **kwargs):
        download["calls"].append((list(tickers), kwargs))
        assert kwargs == {
            "period": "7d", "progress": False, "auto_adjust": False, "threads": False,
        }
        clock["now"] += timedelta(seconds=download["duration"])
        clock["mono"] += download["duration"]
        if download["fail"]:
            raise RuntimeError("synthetic unavailable response")
        return download["frame"].copy()

    monkeypatch.setattr(yahoo_feed, "datetime", Clock)
    monkeypatch.setattr(yahoo_feed, "_today", lambda: clock["now"].date().isoformat())
    monkeypatch.setattr(yahoo_feed.time, "monotonic", lambda: clock["mono"])
    monkeypatch.setenv("YAHOO_FEED_TTL_SEC", "120")
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=fetch))
    yahoo_feed.clear_cache()
    yield clock, download
    yahoo_feed.clear_cache()


def bars(shape="multi", labels=("2026-10-13",), opens=(200.0,), closes=(202.0,), ticker="AAPL"):
    index = pd.DatetimeIndex(labels)
    data = {"Close": closes}
    if opens is not None:
        data["Open"] = opens
    if shape == "series":
        return pd.DataFrame(data, index=index)
    return pd.concat({
        field: pd.DataFrame({ticker: values}, index=index)
        for field, values in data.items()
    }, axis=1)


def advance(clock, seconds=130):
    clock["now"] += timedelta(seconds=seconds)
    clock["mono"] += seconds


def read(ticker="AAPL"):
    evidence = {}
    price = yahoo_feed.open_price_local(ticker, _evidence=evidence)
    assert evidence["schema"] == SCHEMA
    assert evidence["ticker"] == ticker.upper().strip()
    assert evidence["field"] == "Open"
    assert evidence["cache_refresh_basis"] == "shared_close_cache"
    assert evidence["market_observed_at"] is None
    assert evidence["execution_qualification"] == "not_checked"
    json.dumps(evidence, allow_nan=False)
    return price, evidence


@pytest.mark.parametrize("shape", ["series", "multi"])
@pytest.mark.parametrize("ticker", ["AAPL", "0700.HK", "600519.SS"])
def test_selected_open_has_its_own_download_clocks(feed, shape, ticker):
    _, download = feed
    download["frame"] = bars(shape, ticker=ticker)
    price, evidence = read(ticker)
    assert price == evidence["price_local"] == 200.0
    assert evidence["status"] == "available"
    assert evidence["reason"] is None
    assert evidence["source_bar_label"] == "2026-10-13T00:00:00"
    assert evidence["source_bar_label_kind"] == "daily_bar_label"
    assert evidence["fetch_started_at"] == "2026-10-13T15:00:00+00:00"
    assert evidence["download_returned_at"] == "2026-10-13T15:00:03+00:00"
    assert evidence["fetch_age_seconds"] == 3.0
    assert evidence["within_cache_ttl"] is True
    assert len(download["calls"]) == 1


@pytest.mark.parametrize("shape", ["series", "multi"])
def test_fresh_close_does_not_lend_clocks_to_retained_open(feed, shape):
    clock, download = feed
    download["frame"] = bars(shape)
    _, before = read()
    advance(clock)
    download["frame"] = bars(shape, opens=None, closes=(203.0,))
    assert yahoo_feed.price_local("AAPL") == 203.0
    price, evidence = read()
    assert price == 200.0
    for key in ("source_bar_label", "fetch_started_at", "download_returned_at"):
        assert evidence[key] == before[key]
    assert evidence["download_returned_at"] != yahoo_feed._CLOSE_EVIDENCE["AAPL"]["download_returned_at"]
    assert evidence["fetch_age_seconds"] == 136.0
    assert evidence["within_cache_ttl"] is False
    assert len(download["calls"]) == 2


@pytest.mark.parametrize("shape", ["series", "multi"])
def test_fresh_open_does_not_inherit_retained_close_age(feed, shape):
    clock, download = feed
    download["frame"] = bars(shape)
    read()
    old_close = yahoo_feed._CLOSE_EVIDENCE["AAPL"]
    advance(clock)
    download["frame"] = bars(shape, opens=(201.0,), closes=(float("nan"),))
    price, evidence = read()
    assert price == 201.0
    assert evidence["fetch_age_seconds"] == 3.0
    assert evidence["within_cache_ttl"] is True
    assert evidence["fetch_started_at"] != old_close["fetch_started_at"]
    assert yahoo_feed._CLOSE_EVIDENCE["AAPL"] is old_close
    assert len(download["calls"]) == 2


@pytest.mark.parametrize("shape", ["series", "multi"])
@pytest.mark.parametrize("label", ["2026-10-12", "2026-10-14"])
def test_rejected_session_keeps_source_label_but_no_selected_price(feed, shape, label):
    _, download = feed
    download["frame"] = bars(shape, labels=(label,))
    price, evidence = read()
    assert price is None and evidence["price_local"] is None
    assert evidence["status"] == "unavailable"
    assert evidence["reason"] == "exchange_date_mismatch"
    assert evidence["source_bar_label"] == label + "T00:00:00"
    assert len(download["calls"]) == 1


@pytest.mark.parametrize("ticker,label", [
    ("AAPL", "2026-10-13T00:00:00-04:00"),
    ("0700.HK", "2026-10-12T16:00:00+00:00"),
    ("600519.SS", "2026-10-13T00:00:00+08:00"),
])
def test_aware_source_label_is_preserved_literally(feed, ticker, label):
    _, download = feed
    download["frame"] = bars(labels=(label,), ticker=ticker)
    price, evidence = read(ticker)
    assert price == 200.0
    assert evidence["source_bar_label"] == label


def test_same_value_same_bar_refresh_changes_the_capture_generation(feed):
    clock, download = feed
    download["frame"] = bars()
    _, before = read()
    before_tuple = yahoo_feed._OPEN_CACHE["AAPL"]
    advance(clock)
    _, after = read()
    assert yahoo_feed._OPEN_CACHE["AAPL"] == before_tuple
    assert yahoo_feed._OPEN_CACHE["AAPL"] is not before_tuple
    assert after["price_local"] == before["price_local"]
    assert after["source_bar_label"] == before["source_bar_label"]
    assert after["download_returned_at"] != before["download_returned_at"]
    assert len(download["calls"]) == 2


def test_equal_value_generation_swap_during_scalar_read_withholds_metadata(feed, monkeypatch):
    clock, download = feed
    download["frame"] = bars()
    read()
    old_tuple = yahoo_feed._OPEN_CACHE["AAPL"]

    class ReplacingOpen(dict):
        def get(self, key, default=None):
            old = super().get(key, default)
            if key == "AAPL":
                new = (old[0], old[1])
                self[key] = new
                yahoo_feed._remember_open_evidence(
                    key, new, clock["mono"] + 1, "2026-10-13T15:00:04+00:00",
                    "2026-10-13T15:00:05+00:00",
                )
            return old

    monkeypatch.setattr(yahoo_feed, "_OPEN_CACHE", ReplacingOpen(yahoo_feed._OPEN_CACHE))
    price, evidence = read()
    assert price == old_tuple[0]
    assert evidence["status"] == "unavailable"
    assert evidence["reason"] == "cache_binding_unavailable"
    assert evidence["download_returned_at"] is None
    assert len(download["calls"]) == 1


def test_refresh_during_projection_cannot_replace_captured_clocks(feed, monkeypatch):
    clock, download = feed
    download["frame"] = bars()
    _, original = read()
    advance(clock)
    download["fail"] = True
    # Preserve the original expired-Open numeric read, then publish a new metadata
    # generation during its TTL observation. It cannot lend its clock to the old tuple.
    original_ttl = yahoo_feed._ttl
    calls = {"n": 0}
    def ttl():
        calls["n"] += 1
        if calls["n"] == 2:
            q = yahoo_feed._OPEN_CACHE["AAPL"]
            new = (q[0], q[1])
            yahoo_feed._OPEN_CACHE["AAPL"] = new
            yahoo_feed._remember_open_evidence("AAPL", new, clock["mono"],
                                               "2026-10-13T15:02:16+00:00",
                                               "2026-10-13T15:02:16+00:00")
        return original_ttl()
    monkeypatch.setattr(yahoo_feed, "_ttl", ttl)
    price, evidence = read()
    assert price == 200.0
    assert evidence["download_returned_at"] == original["download_returned_at"]
    assert evidence["within_cache_ttl"] is False
    assert evidence["fetch_age_seconds"] == 136.0


def test_failed_refresh_preserves_original_open_context(feed):
    clock, download = feed
    download["frame"] = bars()
    price, original = read()
    advance(clock)
    download["fail"] = True
    again, evidence = read()
    assert again == price == 200.0
    for key in ("source_bar_label", "fetch_started_at", "download_returned_at"):
        assert evidence[key] == original[key]
    assert evidence["within_cache_ttl"] is False
    assert len(download["calls"]) == 2


def test_disabled_ttl_preserves_per_day_policy_and_reports_own_age(feed, monkeypatch):
    clock, download = feed
    download["frame"] = bars()
    read()
    advance(clock, 600)
    monkeypatch.setenv("YAHOO_FEED_TTL_SEC", "0")
    price, evidence = read()
    assert price == 200.0
    assert evidence["fetch_age_seconds"] == 603.0
    assert evidence["within_cache_ttl"] is True
    assert len(download["calls"]) == 1


def test_capture_does_not_alias_the_internal_record(feed):
    _, download = feed
    download["frame"] = bars()
    _, evidence = read()
    evidence["source_bar_label"] = "forged"
    evidence["fetch_started_at"] = "forged"
    _, current = read()
    assert current["source_bar_label"] == "2026-10-13T00:00:00"
    assert current["fetch_started_at"] == "2026-10-13T15:00:00+00:00"
    assert len(download["calls"]) == 1


def test_legacy_primed_open_has_no_invented_metadata(feed):
    clock, _ = feed
    yahoo_feed._FETCHED_DAY = clock["now"].date().isoformat()
    yahoo_feed._CACHE["AAPL"] = 202.0
    yahoo_feed._TS["AAPL"] = clock["mono"]
    yahoo_feed._OPEN_CACHE["AAPL"] = (200.0, pd.Timestamp("2026-10-13"))
    price, evidence = read()
    assert price == 200.0
    assert evidence["status"] == "unavailable"
    assert evidence["reason"] == "cache_binding_unavailable"


def test_metadata_sink_failure_does_not_change_scalar(feed):
    _, download = feed
    download["frame"] = bars()
    class Broken(dict):
        def update(self, *args, **kwargs):
            raise RuntimeError("synthetic sink failure")
    assert yahoo_feed.open_price_local("AAPL", _evidence=Broken()) == 200.0
    assert len(download["calls"]) == 1


@pytest.mark.parametrize("failure", ["storage", "helper"])
def test_metadata_capture_failure_cannot_skip_sibling_open(feed, monkeypatch, failure):
    _, download = feed
    index = pd.DatetimeIndex(["2026-10-13"])
    download["frame"] = pd.concat({
        "Close": pd.DataFrame({"AAPL": [202.0], "MSFT": [402.0]}, index=index),
        "Open": pd.DataFrame({"AAPL": [200.0], "MSFT": [400.0]}, index=index),
    }, axis=1)
    # The day-reset path must run before installing the broken store, otherwise
    # it would replace the injected failure with a healthy empty dict.
    yahoo_feed._reset_if_stale()
    attempts = []
    if failure == "storage":
        class Broken(dict):
            def __setitem__(self, key, value):
                attempts.append(key)
                raise RuntimeError("synthetic storage failure")
        monkeypatch.setattr(yahoo_feed, "_OPEN_EVIDENCE", Broken())
    else:
        def broken(ticker, *args, **kwargs):
            attempts.append(ticker)
            raise RuntimeError("synthetic helper failure")
        monkeypatch.setattr(yahoo_feed, "_remember_open_evidence", broken)
    yahoo_feed.warm(["AAPL", "MSFT"])
    a, ea = read("AAPL")
    m, em = read("MSFT")
    assert (a, m) == (200.0, 400.0)
    assert ea["status"] == em["status"] == "unavailable"
    assert attempts == ["AAPL", "MSFT"]
    assert len(download["calls"]) == 1


def test_metadata_read_failure_cannot_block_scalar(feed, monkeypatch):
    _, download = feed
    download["frame"] = bars()
    read()
    class Broken(dict):
        def get(self, key, default=None):
            raise RuntimeError("synthetic metadata read failure")
    monkeypatch.setattr(yahoo_feed, "_OPEN_EVIDENCE", Broken(yahoo_feed._OPEN_EVIDENCE))
    price, evidence = read()
    assert price == 200.0
    assert evidence["status"] == "unavailable"
    assert len(download["calls"]) == 1


def test_projection_failure_cannot_block_scalar(feed, monkeypatch):
    _, download = feed
    download["frame"] = bars()
    def broken(*args):
        raise RuntimeError("synthetic projection failure")
    monkeypatch.setattr(yahoo_feed, "_open_price_evidence", broken)
    evidence = {}
    assert yahoo_feed.open_price_local("AAPL", _evidence=evidence) == 200.0
    assert evidence == {}
    assert len(download["calls"]) == 1


def test_missing_download_return_clock_keeps_numeric_open(feed, monkeypatch):
    _, download = feed
    download["frame"] = bars()
    original_clock = yahoo_feed.datetime
    class Clock(original_clock):
        calls = 0
        @classmethod
        def now(cls, tz=None):
            if tz == timezone.utc:
                cls.calls += 1
                if cls.calls == 2:
                    raise RuntimeError("synthetic return-clock failure")
            return original_clock.now(tz)
    monkeypatch.setattr(yahoo_feed, "datetime", Clock)
    price, evidence = read()
    assert price == 200.0
    assert evidence["status"] == "partial"
    assert evidence["reason"] == "download_return_time_unavailable"
    assert evidence["download_returned_at"] is None


@pytest.mark.parametrize("value", [float("inf"), float("nan"), -1.0, True])
def test_invalid_observation_cannot_sanitize_legacy_scalar(feed, value):
    clock, _ = feed
    yahoo_feed._FETCHED_DAY = clock["now"].date().isoformat()
    yahoo_feed._CACHE["AAPL"] = 202.0
    yahoo_feed._TS["AAPL"] = clock["mono"]
    quote = (value, pd.Timestamp("2026-10-13"))
    yahoo_feed._OPEN_CACHE["AAPL"] = quote
    yahoo_feed._remember_open_evidence("AAPL", quote, clock["mono"],
                                      "2026-10-13T15:00:00+00:00", "2026-10-13T15:00:00+00:00")
    price, evidence = read()
    assert price is value
    assert evidence["price_local"] is None
    assert evidence["status"] == "unavailable"
    assert evidence["reason"] == "price_invalid"


def test_invalid_capture_age_is_withheld(feed):
    clock, download = feed
    download["frame"] = bars()
    read()
    yahoo_feed._OPEN_EVIDENCE["AAPL"]["fetched_mono"] = clock["mono"] + 1
    price, evidence = read()
    assert price == 200.0
    assert evidence["reason"] == "cache_clock_invalid"
    assert evidence["download_returned_at"] is None


def test_cache_reset_drops_open_capture(feed):
    clock, download = feed
    download["frame"] = bars()
    read()
    assert yahoo_feed._OPEN_EVIDENCE
    yahoo_feed.clear_cache()
    assert yahoo_feed._OPEN_EVIDENCE == {}
    read()
    clock["now"] += timedelta(days=1)
    yahoo_feed._reset_if_stale()
    assert yahoo_feed._OPEN_EVIDENCE == {}
    assert yahoo_feed._OPEN_CACHE == {}


def test_empty_or_missing_open_stays_unavailable(feed):
    _, download = feed
    price, evidence = read("")
    assert price is None and evidence["reason"] == "empty_ticker"
    assert download["calls"] == []
    download["frame"] = bars(opens=None)
    price, evidence = read()
    assert price is None and evidence["reason"] == "open_unavailable"
    assert len(download["calls"]) == 1
