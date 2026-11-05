"""Actual Polygon Open reads retain bounded context without changing price admission."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone

import pytest

from data_layer import polygon
from portfolio import price_evidence

SCHEMA = "mastermind.polygon_snapshot_evidence.v1"


@pytest.fixture
def source(monkeypatch):
    import requests
    state = {
        "now": 1791896400.0, "delay": 4.0, "calls": [], "time_reads": 0,
        "payload": {"ticker": "AAPL", "updated": 1791896400123456789, "day": {"o": 199.0}},
        "failure": None, "same_object": False,
    }
    def now():
        state["time_reads"] += 1
        return state["now"]
    def clock():
        return datetime.fromtimestamp(state["now"], timezone.utc)
    def request(url, *, params, timeout):
        state["calls"].append({"url": url, "params": dict(params), "timeout": timeout})
        state["now"] += state["delay"]
        if state["failure"] == "transport":
            raise RuntimeError("synthetic provider failure")
        class Response:
            ok = state["failure"] != "http"
            def json(self):
                if state["failure"] == "decode":
                    raise ValueError("synthetic decode failure")
                return {"ticker": state["payload"] if state["same_object"] else copy.deepcopy(state["payload"])}
        return Response()
    monkeypatch.setenv("POLYGON_API_KEY", "synthetic-fixture-key")
    monkeypatch.setattr(polygon.time, "time", now)
    monkeypatch.setattr(polygon, "_snapshot_clock", clock, raising=False)
    monkeypatch.setattr(polygon, "_snapshot_cache", {})
    monkeypatch.setattr(polygon, "_snapshot_observations", {}, raising=False)
    monkeypatch.setattr(polygon, "_TTL", 60.0)
    monkeypatch.setattr(requests, "get", request)
    return state


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def read(ticker="AAPL", sink=None):
    sink = {} if sink is None else sink
    value = polygon.day_open(ticker, _evidence=sink)
    return value, sink


def test_real_request_retains_own_clocks_and_exact_raw_timestamp(source):
    start = source["now"]
    price, context = read(" aapl ")
    assert price == 199.0
    assert context == {
        "schema": SCHEMA, "ticker": "AAPL", "field": "day.o", "price": 199.0,
        "currency": "USD", "status": "available", "reason": None,
        "payload_ticker": "AAPL", "payload_ticker_status": "matched",
        "source_updated_raw": "1791896400123456789", "source_updated_unit": "not_established",
        "source_bar_label": None, "source_bar_label_kind": "not_provided",
        "cache_anchor_at": iso(start), "request_started_at": iso(start),
        "response_returned_at": iso(start + 4), "cache_age_observed_at": iso(start + 4),
        "cache_age_seconds": 4.0, "within_cache_ttl": True,
        "cache_clock_basis": "lookup_before_request",
        "market_observed_at": None, "execution_qualification": "not_checked",
    }
    assert len(source["calls"]) == 1 and source["time_reads"] == 1
    assert source["calls"][0]["url"].endswith("/AAPL")
    assert source["calls"][0]["timeout"] == 6
    assert source["calls"][0]["params"] == {"apiKey": "synthetic-fixture-key"}
    encoded = json.dumps(context)
    assert '"1791896400123456789"' in encoded
    assert "synthetic-fixture-key" not in encoded


def test_cache_hit_keeps_original_request_and_return_clocks(source):
    first_price, first = read()
    source["now"] += 30
    price, context = read()
    assert first_price == price == 199.0
    assert context["request_started_at"] == first["request_started_at"]
    assert context["response_returned_at"] == first["response_returned_at"]
    assert context["cache_age_seconds"] == 34.0
    assert context["cache_age_observed_at"] == iso(source["now"])
    assert context["within_cache_ttl"] is True
    assert len(source["calls"]) == 1 and source["time_reads"] == 2


def test_legacy_snapshot_and_open_reads_populate_context_without_copying_snapshot(source):
    original = polygon._snapshot("AAPL")
    assert polygon._snapshot("AAPL") is original
    assert polygon.day_open("AAPL") == 199.0
    price, context = read()
    assert price == 199.0 and context["status"] == "available"
    assert context["response_returned_at"] == iso(source["now"])
    assert len(source["calls"]) == 1


def test_slow_request_can_already_exceed_original_lookup_based_ttl(source):
    source["delay"] = 75
    price, context = read()
    assert price == 199.0
    assert context["cache_age_seconds"] == 75.0
    assert context["within_cache_ttl"] is False
    assert len(source["calls"]) == 1
    read()
    assert len(source["calls"]) == 2


def test_equal_price_and_timestamp_refresh_retains_distinct_retrieval(source):
    _, first = read()
    source["now"] += 61
    _, second = read()
    assert second["price"] == first["price"]
    assert second["source_updated_raw"] == first["source_updated_raw"]
    assert second["request_started_at"] != first["request_started_at"]
    assert second["response_returned_at"] != first["response_returned_at"]
    assert len(source["calls"]) == 2


@pytest.mark.parametrize("failure", ["transport", "http", "decode"])
def test_failed_refresh_keeps_existing_negative_cache_behavior_without_old_clocks(source, failure):
    read()
    source["now"] += 61
    source["failure"] = failure
    price, context = read()
    assert price is None
    assert context["status"] == "unavailable"
    assert context["reason"] == "no_selected_open"
    assert context["response_returned_at"] is None
    read()
    assert len(source["calls"]) == 2


@pytest.mark.parametrize("payload,expected_status,reason", [
    ("MSFT", "mismatch", "payload_ticker_mismatch"),
    (None, "unavailable", "payload_ticker_unavailable"),
    ("x" * 65, "unavailable", "payload_ticker_unavailable"),
    ("<script>bad</script>", "unavailable", "payload_ticker_unavailable"),
])
def test_payload_symbol_disagreement_is_retained_without_rejecting_price(source, payload, expected_status, reason):
    source["payload"]["ticker"] = payload
    price, context = read()
    assert price == 199.0
    assert context["payload_ticker_status"] == expected_status
    assert context["status"] == "partial" and context["reason"] == reason
    assert context["payload_ticker"] == ("MSFT" if payload == "MSFT" else None)


@pytest.mark.parametrize("value", [None, True, 1.5, "1791896400123456789", -1, 2**65])
def test_unqualified_updated_value_is_not_guessed_or_coerced(source, value):
    source["payload"]["updated"] = value
    price, context = read()
    assert price == 199.0
    assert context["source_updated_raw"] is None
    assert context["source_updated_unit"] == "not_established"
    assert context["status"] == "partial"
    assert context["reason"] == "snapshot_updated_unavailable"


def test_old_updated_value_does_not_become_a_bar_date_or_new_admission_rule(source):
    source["payload"]["updated"] = 1
    price, context = read()
    assert price == 199.0
    assert context["source_updated_raw"] == "1"
    assert context["source_bar_label"] is None
    assert context["market_observed_at"] is None
    assert context["execution_qualification"] == "not_checked"


@pytest.mark.parametrize("mutation", ["open", "day_object", "symbol", "updated"])
def test_shared_snapshot_mutation_cannot_reuse_original_retrieval_context(source, mutation):
    polygon._snapshot("AAPL")
    snap = polygon._snapshot_cache["AAPL"][1]
    if mutation == "open":
        snap["day"]["o"] = 200.0
    elif mutation == "day_object":
        snap["day"] = {"o": 199.0}
    elif mutation == "symbol":
        snap["ticker"] = "MSFT"
    else:
        snap["updated"] += 1
    price, context = read()
    assert price == (200.0 if mutation == "open" else 199.0)
    assert context["status"] == "unavailable"
    assert context["reason"] == "snapshot_fields_changed"
    assert context["request_started_at"] is None and context["response_returned_at"] is None
    assert len(source["calls"]) == 1


def test_same_object_refetch_during_reader_does_not_lend_newer_retrieval_clock(source, monkeypatch):
    source["same_object"] = True
    original_read = price_evidence.read_with_evidence
    held = {}
    def intervening(reader, *args, **kwargs):
        result = original_read(reader, *args, **kwargs)
        held["old_return"] = iso(source["now"])
        source["now"] += 61
        polygon._snapshot("AAPL")
        return result
    monkeypatch.setattr(price_evidence, "read_with_evidence", intervening)
    price, context = read()
    assert price == 199.0
    assert context["response_returned_at"] == held["old_return"]
    assert context["response_returned_at"] != iso(source["now"])
    assert len(source["calls"]) == 2


def test_unmatched_cache_entry_cannot_borrow_metadata(source):
    read()
    original = polygon._snapshot_cache["AAPL"]
    polygon._snapshot_cache["AAPL"] = (original[0], copy.deepcopy(original[1]))
    price, context = read()
    assert price == 199.0
    assert context["status"] == "unavailable"
    assert context["reason"] == "snapshot_context_unavailable"
    assert context["response_returned_at"] is None


def test_missing_observation_store_does_not_veto_the_selected_open(source, monkeypatch):
    class BrokenStore(dict):
        failures = 0
        def __setitem__(self, key, value):
            self.failures += 1
            raise RuntimeError("synthetic observation-store failure")
        def get(self, key, default=None):
            self.failures += 1
            raise RuntimeError("synthetic observation-store failure")
    broken = BrokenStore()
    monkeypatch.setattr(polygon, "_snapshot_observations", broken)
    price, first = read()
    second_price, second = read()
    assert price == second_price == 199.0
    assert first["status"] == "available"
    assert second["status"] == "unavailable"
    assert broken.failures >= 2 and len(source["calls"]) == 1


@pytest.mark.parametrize("when", ["before", "after", "both"])
def test_clock_capture_failures_do_not_skip_request_or_price(source, monkeypatch, when):
    calls = []
    def broken_clock():
        calls.append(len(calls))
        if when == "both" or (when == "before" and len(calls) == 1) or (when == "after" and len(calls) == 2):
            raise RuntimeError("synthetic clock failure")
        return datetime.fromtimestamp(source["now"], timezone.utc)
    monkeypatch.setattr(polygon, "_snapshot_clock", broken_clock)
    price, context = read()
    assert price == 199.0 and len(source["calls"]) == 1
    assert len(calls) == 2
    assert context["status"] == "partial"
    assert context["reason"] == "retrieval_clock_unavailable"


def test_wall_clock_regression_is_unavailable_not_zero_age(source, monkeypatch):
    clocks = iter([source["now"], source["now"] - 10])
    monkeypatch.setattr(polygon, "_snapshot_clock", lambda: datetime.fromtimestamp(next(clocks), timezone.utc))
    price, context = read()
    assert price == 199.0
    assert context["status"] == "partial" and context["reason"] == "local_clock_regressed"
    assert context["cache_age_seconds"] is None and context["within_cache_ttl"] is None


def test_legacy_snapshot_seam_is_called_once_without_speculative_retry(source, monkeypatch):
    calls = []
    def legacy(ticker):
        calls.append(ticker)
        return {"ticker": "AAPL", "day": {"o": 201.0}}
    monkeypatch.setattr(polygon, "_snapshot", legacy)
    price, context = read()
    assert price == 201.0 and calls == ["AAPL"]
    assert context["status"] == "unavailable" and context["reason"] == "snapshot_context_unavailable"


def test_capture_sink_failure_never_changes_the_return_or_request_count(source):
    class BadSink(dict):
        def clear(self):
            raise RuntimeError("synthetic sink failure")
    price, _ = read(sink=BadSink())
    assert price == 199.0 and len(source["calls"]) == 1


@pytest.mark.parametrize("value,expected", [(0, None), (-1, None), ("199.5", 199.5), (True, 1.0)])
def test_legacy_numeric_admission_is_preserved_for_nonstandard_open_values(source, value, expected):
    source["payload"]["day"]["o"] = value
    price, context = read()
    assert price == expected
    assert context["status"] == "unavailable"


def test_arbitrary_numeric_object_is_not_coerced_again_by_capture(source):
    class Value:
        calls = 0
        def __float__(self):
            self.calls += 1
            return 199.0
    value = Value()
    source["payload"]["day"]["o"] = value
    source["same_object"] = True
    price, context = read()
    assert price == 199.0 and value.calls == 2
    assert context["status"] == "unavailable"


@pytest.mark.parametrize("payload", [[], "wrong-shape", {"day": "wrong-shape"}])
def test_corrupt_snapshot_legacy_exception_contract_is_not_retried(source, payload):
    source["payload"] = payload
    if payload == []:
        price, context = read()
        assert price is None and context["status"] == "unavailable"
    else:
        with pytest.raises(AttributeError):
            read()
    assert len(source["calls"]) == 1


def test_cache_publication_cannot_relabel_a_mutated_value_with_provider_retrieval_clocks(source, monkeypatch):
    class MutatingCache(dict):
        def __setitem__(self, key, entry):
            super().__setitem__(key, entry)
            # A holder of the shared snapshot changes it as soon as published.
            entry[1]["day"]["o"] = 200.0
    monkeypatch.setattr(polygon, "_snapshot_cache", MutatingCache())
    price, context = read()
    assert price == 200.0
    assert context["status"] == "unavailable"
    assert context["reason"] == "snapshot_fields_changed"
    assert context["response_returned_at"] is None
    assert len(source["calls"]) == 1


def test_observation_construction_failure_cannot_skip_cache_publication(source, monkeypatch):
    failures = []
    def fail(*args):
        failures.append(True)
        raise RuntimeError("synthetic record construction failure")
    monkeypatch.setattr(polygon, "_remember_snapshot_observation", fail)
    price, context = read()
    assert price == 199.0 and context["status"] == "unavailable"
    assert polygon._snapshot_cache["AAPL"][1]["day"]["o"] == 199.0
    second, _ = read()
    assert second == 199.0 and failures == [True] and len(source["calls"]) == 1
