"""The actual Yahoo Close selection must retain its source and retrieval clocks.

All data and clocks are synthetic. No provider/network or portfolio writer is used.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from data_layer import yahoo_feed

SCHEMA = "mastermind.yahoo_daily_bar_evidence.v1"


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


def bars(shape, labels, closes, opens=None, ticker="AAPL"):
    index = pd.Index(labels) if any(not isinstance(x, str) for x in labels) else pd.DatetimeIndex(labels)
    data = {"Close": closes}
    if opens is not None:
        data["Open"] = opens
    if shape == "series":
        return pd.DataFrame(data, index=index)
    return pd.concat({
        field: pd.DataFrame({ticker: values}, index=index)
        for field, values in data.items()
    }, axis=1)


def read_price(ticker="AAPL", asof=None):
    evidence = {}
    price = yahoo_feed.price_local(ticker, asof, _evidence=evidence)
    assert evidence["schema"] == SCHEMA
    assert evidence["ticker"] == ticker.upper().strip()
    assert evidence["field"] == "Close"
    assert evidence["market_observed_at"] is None
    assert evidence["execution_qualification"] == "not_checked"
    json.dumps(evidence, allow_nan=False)
    return price, evidence


@pytest.mark.parametrize("shape", ["series", "multi"])
@pytest.mark.parametrize("ticker", ["AAPL", "0700.HK", "600519.SS"])
def test_fresh_fetch_retains_old_bar_label_without_claiming_current_tape(feed, shape, ticker):
    _, download = feed
    download["frame"] = bars(shape, ["2026-10-12"], [190.0], [180.0], ticker)
    price, evidence = read_price(ticker)

    assert price == 190.0
    assert evidence["price_local"] == price
    assert evidence["status"] == "available"
    assert evidence["source_bar_label"] == "2026-10-12T00:00:00"
    assert evidence["source_bar_label_kind"] == "daily_bar_label"
    assert evidence["fetch_started_at"] == "2026-10-13T15:00:00+00:00"
    assert evidence["download_returned_at"] == "2026-10-13T15:00:03+00:00"
    assert evidence["fetch_age_seconds"] == 3.0
    assert evidence["within_cache_ttl"] is True
    assert yahoo_feed.open_price_local(ticker) is None
    assert len(download["calls"]) == 1


@pytest.mark.parametrize("shape", ["series", "multi"])
def test_close_clock_follows_selected_nonnull_close_and_not_open_or_last_index(feed, shape):
    _, download = feed
    download["frame"] = bars(
        shape, ["2026-10-12", "2026-10-13"],
        [190.0, float("nan")], [180.0, 200.0],
    )
    price, evidence = read_price()
    assert price == 190.0
    assert evidence["source_bar_label"].startswith("2026-10-12")
    assert yahoo_feed.open_price_local("AAPL") == 200.0
    assert len(download["calls"]) == 1


@pytest.mark.parametrize("label", [
    "2026-10-13T00:00:00-04:00",
    "2026-10-12T16:00:00+00:00",
    "2026-10-13T00:00:00+08:00",
])
def test_aware_label_retains_source_offset_and_is_not_a_trade_timestamp(feed, label):
    _, download = feed
    download["frame"] = bars("multi", [label], [202.0])
    price, evidence = read_price()
    assert price == 202.0
    assert evidence["source_bar_label"] == label
    assert evidence["source_bar_label_kind"] == "daily_bar_label"


def test_one_batch_binds_each_symbols_own_last_nonnull_close(feed):
    _, download = feed
    ix = pd.DatetimeIndex(["2026-10-12", "2026-10-13"])
    download["frame"] = pd.concat({
        "Close": pd.DataFrame({"AAPL": [190.0, 202.0], "MSFT": [400.0, float("nan")]}, index=ix),
    }, axis=1)
    yahoo_feed.warm(["AAPL", "MSFT"])
    a, ea = read_price("AAPL")
    m, em = read_price("MSFT")
    assert (a, ea["source_bar_label"]) == (202.0, "2026-10-13T00:00:00")
    assert (m, em["source_bar_label"]) == (400.0, "2026-10-12T00:00:00")
    assert len(download["calls"]) == 1


def test_failed_refresh_retains_old_price_and_original_clocks_with_expired_ttl(feed):
    clock, download = feed
    download["frame"] = bars("multi", ["2026-10-12"], [190.0])
    original_price, original = read_price()
    clock["now"] += timedelta(seconds=130)
    clock["mono"] += 130
    download["fail"] = True

    price, evidence = read_price()
    assert price == original_price == 190.0
    for key in ["source_bar_label", "fetch_started_at", "download_returned_at"]:
        assert evidence[key] == original[key]
    assert evidence["within_cache_ttl"] is False
    assert evidence["fetch_age_seconds"] == 136.0
    assert yahoo_feed.quote_cached("AAPL") is None
    assert len(download["calls"]) == 2


def test_same_price_new_response_replaces_its_bar_and_retrieval_identity(feed):
    clock, download = feed
    download["frame"] = bars("series", ["2026-10-12"], [202.0])
    _, before = read_price()
    clock["now"] += timedelta(seconds=130)
    clock["mono"] += 130
    download["frame"] = bars("series", ["2026-10-13"], [202.0])
    _, after = read_price()
    assert before["price_local"] == after["price_local"]
    assert before["source_bar_label"] != after["source_bar_label"]
    assert before["download_returned_at"] != after["download_returned_at"]
    assert len(download["calls"]) == 2


def test_quote_cached_exposes_same_bound_evidence_without_network_or_aliasing(feed):
    _, download = feed
    download["frame"] = bars("multi", ["2026-10-13"], [202.0])
    price, evidence = read_price()
    quote = yahoo_feed.quote_cached("AAPL")
    assert quote["price_local"] == price
    assert quote["daily_bar_evidence"] == evidence
    assert quote["as_of"] == evidence["fetch_started_at"]
    assert quote["time_kind"] == "feed_retrieval"
    assert quote["fresh"] is True
    quote["daily_bar_evidence"]["source_bar_label"] = "forged"
    assert yahoo_feed.quote_cached("AAPL")["daily_bar_evidence"] == evidence
    assert len(download["calls"]) == 1


@pytest.mark.parametrize("field,new_value", [
    ("_CACHE", 203.0), ("_TS", 1001.0), ("_ASOF", "2026-10-13T15:00:01+00:00"),
])
def test_mismatched_cache_components_never_borrow_a_prior_price_clock(feed, field, new_value):
    _, download = feed
    download["frame"] = bars("multi", ["2026-10-13"], [202.0])
    read_price()
    getattr(yahoo_feed, field)["AAPL"] = new_value
    quote = yahoo_feed.quote_cached("AAPL")
    assert quote["daily_bar_evidence"]["status"] == "unavailable"
    assert quote["daily_bar_evidence"]["reason"] == "cache_binding_unavailable"
    assert quote["daily_bar_evidence"]["source_bar_label"] is None
    assert quote["daily_bar_evidence"]["download_returned_at"] is None


@pytest.mark.parametrize("label", [17, "not-a-date", pd.NaT])
def test_unusable_bar_label_preserves_original_close_and_exposes_partial_evidence(feed, label):
    _, download = feed
    download["frame"] = pd.DataFrame({"Close": [202.0]}, index=pd.Index([label]))
    price, evidence = read_price()
    assert price == yahoo_feed.price_local("AAPL") == 202.0
    assert evidence["status"] == "partial"
    assert evidence["reason"] == "source_bar_label_unavailable"
    assert evidence["source_bar_label"] is None
    assert evidence["download_returned_at"] == "2026-10-13T15:00:03+00:00"


@pytest.mark.parametrize("action", ["clear", "roll"])
def test_cache_reset_does_not_reuse_previous_price_provenance(feed, action):
    clock, download = feed
    download["frame"] = bars("series", ["2026-10-13"], [202.0])
    read_price()
    if action == "clear":
        yahoo_feed.clear_cache()
    else:
        clock["now"] += timedelta(days=1)
        clock["mono"] += 86400
    download["fail"] = True
    price, evidence = read_price()
    assert price is None
    assert evidence["status"] == "unavailable"
    assert evidence["reason"] == "price_unavailable"
    assert evidence["source_bar_label"] is None
    assert evidence["download_returned_at"] is None


def test_asof_compatibility_argument_does_not_relabel_current_data_as_historical(feed):
    _, download = feed
    download["frame"] = bars("multi", ["2026-10-13"], [202.0])
    price, evidence = read_price(asof="2025-01-01")
    assert price == 202.0
    assert evidence["source_bar_label"].startswith("2026-10-13")
    assert evidence["fetch_started_at"].startswith("2026-10-13")


def test_empty_ticker_and_absent_price_keep_explicit_unavailability_without_fetch(feed):
    _, download = feed
    price, evidence = read_price("")
    assert price is None
    assert evidence["status"] == "unavailable"
    assert evidence["reason"] == "price_unavailable"
    assert download["calls"] == []


def test_evidence_sink_failure_cannot_change_numeric_price_or_source_selection(feed):
    _, download = feed
    download["frame"] = bars("multi", ["2026-10-13"], [202.0], [200.0])

    class BrokenDict(dict):
        def update(self, *args, **kwargs):
            raise RuntimeError("synthetic observation failure")

    assert yahoo_feed.price_local("AAPL", _evidence=BrokenDict()) == 202.0
    from bot.settle import _open_price_usd
    assert _open_price_usd("AAPL", _polygon=lambda _: None, _paper=lambda _: 250.0) == (200.0, "yahoo_open")
    assert len(download["calls"]) == 1

def test_metadata_write_failure_does_not_skip_other_numeric_prices(feed, monkeypatch):
    _, download = feed
    yahoo_feed._reset_if_stale()

    class RefusingCache(dict):
        def __setitem__(self, key, value):
            raise RuntimeError("synthetic metadata storage failure")

    monkeypatch.setattr(yahoo_feed, "_CLOSE_EVIDENCE", RefusingCache())
    ix = pd.DatetimeIndex(["2026-10-13"])
    download["frame"] = pd.concat({
        "Close": pd.DataFrame({"AAPL": [202.0], "MSFT": [400.0]}, index=ix),
    }, axis=1)
    yahoo_feed.warm(["AAPL", "MSFT"])
    assert yahoo_feed.price_local("AAPL") == 202.0
    assert yahoo_feed.price_local("MSFT") == 400.0
    assert yahoo_feed.quote_cached("AAPL")["daily_bar_evidence"]["status"] == "unavailable"
    assert len(download["calls"]) == 1


def test_missing_receipt_clock_does_not_discard_prices_or_invent_a_timestamp(feed, monkeypatch):
    _, download = feed
    download["frame"] = bars("multi", ["2026-10-13"], [202.0])
    actual_clock = yahoo_feed.datetime
    calls = {"count": 0}

    class MissingReceiptClock(actual_clock):
        @classmethod
        def now(cls, tz=None):
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("synthetic clock failure after response")
            return actual_clock.now(tz)

    monkeypatch.setattr(yahoo_feed, "datetime", MissingReceiptClock)
    price, evidence = read_price()
    assert price == 202.0
    assert evidence["status"] == "partial"
    assert evidence["reason"] == "download_return_time_unavailable"
    assert evidence["source_bar_label"].startswith("2026-10-13")
    assert evidence["download_returned_at"] is None


def test_clock_reversal_is_unknown_age_without_changing_legacy_price(feed):
    clock, download = feed
    download["frame"] = bars("multi", ["2026-10-13"], [202.0])
    read_price()
    clock["mono"] = 999.0
    price, evidence = read_price()
    assert price == 202.0
    assert evidence["status"] == "unavailable"
    assert evidence["reason"] == "cache_clock_invalid"
    assert evidence["fetch_age_seconds"] is None
    assert evidence["within_cache_ttl"] is None


@pytest.mark.parametrize("price", [float("inf"), float("-inf"), float("nan"), -1.0, 0.0])
def test_nonfinite_or_nonpositive_cache_value_cannot_be_serialized_as_price_evidence(feed, price):
    _, download = feed
    download["frame"] = bars("multi", ["2026-10-13"], [202.0])
    read_price()
    yahoo_feed._CACHE["AAPL"] = price
    evidence = yahoo_feed.quote_cached("AAPL")["daily_bar_evidence"]
    assert evidence["status"] == "unavailable"
    assert evidence["reason"] == "price_invalid"
    assert evidence["price_local"] is None
    json.dumps(evidence, allow_nan=False)

def test_concurrent_price_refresh_cannot_attach_another_prices_evidence_to_quote(feed, monkeypatch):
    _, download = feed
    download["frame"] = bars("multi", ["2026-10-13"], [202.0])
    read_price()

    class RefreshAfterRead(dict):
        def get(self, key, default=None):
            value = super().get(key, default)
            if key == "AAPL" and value == 202.0:
                self[key] = 203.0
                yahoo_feed._CLOSE_EVIDENCE[key] = {
                    **yahoo_feed._CLOSE_EVIDENCE[key],
                    "price_local": 203.0,
                }
            return value

    monkeypatch.setattr(yahoo_feed, "_CACHE", RefreshAfterRead(yahoo_feed._CACHE))
    quote = yahoo_feed.quote_cached("AAPL")
    evidence = quote["daily_bar_evidence"]
    assert quote["price_local"] == 202.0
    assert evidence["status"] == "unavailable"
    assert evidence["reason"] == "cache_binding_unavailable"
    assert evidence["source_bar_label"] is None


@pytest.mark.parametrize("reader", ["price_local", "quote_cached"])
def test_same_value_refresh_during_selection_cannot_replace_selected_bar_identity(
    feed, monkeypatch, reader
):
    _, download = feed
    download["frame"] = bars("multi", ["2026-10-12"], [202.0])
    read_price()
    original_record = yahoo_feed._CLOSE_EVIDENCE["AAPL"]
    refreshes = []

    class RefreshAfterRead(dict):
        def get(self, key, default=None):
            selected = super().get(key, default)
            if key == "AAPL" and not refreshes:
                # A background request started before this read and publishes a
                # newer bar now. Its equal scalar does not identify the old read.
                refreshes.append(key)
                yahoo_feed._TS[key] = 1001.0
                yahoo_feed._ASOF[key] = "2026-10-13T15:00:01+00:00"
                yahoo_feed._CLOSE_EVIDENCE[key] = {
                    **original_record,
                    "source_bar_label": "2026-10-13T00:00:00",
                    "fetched_mono": 1001.0,
                    "fetch_started_at": "2026-10-13T15:00:01+00:00",
                    "download_returned_at": "2026-10-13T15:00:04+00:00",
                }
            return selected

    monkeypatch.setattr(yahoo_feed, "_CACHE", RefreshAfterRead(yahoo_feed._CACHE))
    if reader == "price_local":
        price, evidence = read_price()
    else:
        quote = yahoo_feed.quote_cached("AAPL")
        price, evidence = quote["price_local"], quote["daily_bar_evidence"]

    assert price == 202.0
    assert evidence["status"] == "unavailable"
    assert evidence["reason"] == "cache_binding_unavailable"
    assert evidence["source_bar_label"] is None
    assert refreshes == ["AAPL"]
    assert len(download["calls"]) == 1


def test_retained_bar_ttl_uses_its_own_age_if_refresh_finishes_during_projection(
    feed, monkeypatch
):
    clock, download = feed
    download["frame"] = bars("multi", ["2026-10-12"], [202.0])
    read_price()
    original_record = dict(yahoo_feed._CLOSE_EVIDENCE["AAPL"])
    clock["now"] += timedelta(seconds=130)
    clock["mono"] += 130
    download["fail"] = True
    refreshes = []

    class RefreshDuringProjection(dict):
        def get(self, key, default=None):
            selected = super().get(key, default)
            if key == "download_returned_at" and not refreshes:
                refreshes.append(key)
                fetched_mono = clock["mono"] - 1.0
                fetched_at = (clock["now"] - timedelta(seconds=1)).isoformat()
                yahoo_feed._TS["AAPL"] = fetched_mono
                yahoo_feed._ASOF["AAPL"] = fetched_at
                yahoo_feed._CLOSE_EVIDENCE["AAPL"] = {
                    **original_record,
                    "fetched_mono": fetched_mono,
                    "fetch_started_at": fetched_at,
                    "source_bar_label": "2026-10-13T00:00:00",
                    "download_returned_at": clock["now"].isoformat(),
                }
            return selected

    monkeypatch.setitem(
        yahoo_feed._CLOSE_EVIDENCE, "AAPL", RefreshDuringProjection(original_record)
    )
    price, evidence = read_price()

    assert price == 202.0
    assert evidence["status"] == "available"
    assert evidence["source_bar_label"] == original_record["source_bar_label"]
    assert evidence["fetch_age_seconds"] == 136.0
    assert evidence["within_cache_ttl"] is False
    assert refreshes == ["download_returned_at"]
    assert len(download["calls"]) == 2


def test_disabled_ttl_still_describes_the_bound_older_record_as_within_cache_policy(
    feed, monkeypatch
):
    clock, download = feed
    download["frame"] = bars("multi", ["2026-10-12"], [202.0])
    read_price()
    monkeypatch.setenv("YAHOO_FEED_TTL_SEC", "0")
    clock["now"] += timedelta(seconds=130)
    clock["mono"] += 130

    price, evidence = read_price()

    assert price == 202.0
    assert evidence["source_bar_label"] == "2026-10-12T00:00:00"
    assert evidence["fetch_age_seconds"] == 133.0
    assert evidence["within_cache_ttl"] is True
    assert len(download["calls"]) == 1


def test_metadata_generation_read_failure_does_not_prevent_scalar_selection(feed, monkeypatch):
    _, download = feed
    download["frame"] = bars("multi", ["2026-10-13"], [202.0])
    read_price()

    class BrokenMetadata(dict):
        def get(self, *args, **kwargs):
            raise RuntimeError("synthetic metadata read failure")

    monkeypatch.setattr(yahoo_feed, "_CLOSE_EVIDENCE", BrokenMetadata())
    price, evidence = read_price()

    assert price == 202.0
    assert evidence["status"] == "unavailable"
    assert evidence["source_bar_label"] is None
    assert len(download["calls"]) == 1
