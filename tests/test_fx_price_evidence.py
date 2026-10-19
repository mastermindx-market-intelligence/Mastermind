"""FX evidence must follow the actual selected rate without changing scalar behavior."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from datetime import date
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from test_selected_price_evidence import (
    isolated_evidence_books, _seed_evidence_book, _selected_numeric_bytes,
)


@pytest.fixture
def fx_inputs(tmp_path, monkeypatch):
    from portfolio import fx, price_evidence as pe

    state = {"day": date(2026, 10, 18), "clock": "2026-10-18T23:00:00+00:00",
             "rows": {}, "calls": [], "store_calls": [], "root": tmp_path / "macro"}

    class LocalDate(date):
        @classmethod
        def today(cls):
            return state["day"]

    def store_read(provider, symbol):
        assert provider == "yahoo"
        state["store_calls"].append(symbol)
        value = state["rows"].get(symbol)
        if isinstance(value, Exception):
            raise value
        return value

    lib = ModuleType("lib")
    lib.store = SimpleNamespace(read=store_read)
    monkeypatch.setitem(sys.modules, "lib", lib)
    monkeypatch.setattr(fx, "date", LocalDate)
    monkeypatch.setattr(fx, "_V", state["root"])
    monkeypatch.setattr(fx, "_RATE_CACHE", {})
    if hasattr(fx, "_RATE_CONTEXT"):
        monkeypatch.setattr(fx, "_RATE_CONTEXT", {})
    if hasattr(fx, "_fx_evidence"):
        monkeypatch.setattr(fx._fx_evidence, "clock", lambda: state["clock"])

    for name, kind in (("_from_yahoo_store", "yahoo"), ("_from_forex_snapshot", "snapshot")):
        original = getattr(fx, name)

        def wrapper(key, *, _evidence=None, _reader=original, _kind=kind):
            state["calls"].append([_kind, key])
            return pe.call_with_evidence(_reader, key, evidence=_evidence)

        monkeypatch.setattr(fx, name, wrapper)
    return state


def close_rows(value, *, trailing_null=False):
    values = [value, float("nan")] if trailing_null else [value]
    return pd.DataFrame({"close": values}, index=pd.to_datetime(
        ["2026-10-12", "2026-10-15"] if trailing_null else ["2026-10-12"],
    ))


def put_snapshot(state, pairs, *, second=False):
    rel = "site/forexdata/latest.json" if second else "data/forex/latest.json"
    path = state["root"] / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"asof": "2026-10-12T16:00:00+00:00", "pairs": pairs}, indent=2) + "\n"
    path.write_text(text)
    return path, text


SELECTIONS = [
    ("cnh", "CNY", 7.1, "yahoo_store", "CNH=X"),
    ("cny", "CNY", 7.2, "yahoo_store", "CNY=X"),
    ("cny_snapshot", "CNY", 7.3, "forex_snapshot", "USDCNH"),
    ("cny_second_snapshot", "CNY", 7.4, "forex_snapshot", "USDCNH"),
    ("hkd", "HKD", 7.8, "yahoo_store", "HKD=X"),
    ("hkd_snapshot", "HKD", 7.81, "forex_snapshot", "USDHKD"),
    ("hkd_alias", "HKD", 0.128, "forex_snapshot", "HKDUSD"),
    ("cny_static", "CNY", 7.2, "static_fallback", None),
    ("hkd_static", "HKD", 7.8, "static_fallback", None),
    ("unknown", "EUR", 1.0, "unknown_currency_fallback", None),
    ("identity", "USD", 1.0, "identity", None),
]


def configure_selection(state, case, value):
    if case in ("cnh", "cny", "hkd"):
        symbol = {"cnh": "CNH=X", "cny": "CNY=X", "hkd": "HKD=X"}[case]
        state["rows"][symbol] = close_rows(value)
    elif case in ("cny_snapshot", "cny_second_snapshot", "hkd_snapshot", "hkd_alias"):
        symbol = {"cny_snapshot": "USDCNH", "cny_second_snapshot": "USDCNH",
                  "hkd_snapshot": "USDHKD", "hkd_alias": "HKDUSD"}[case]
        put_snapshot(state, {symbol: {"quote": value}}, second=case == "cny_second_snapshot")


@pytest.mark.parametrize("case,currency,expected,source,symbol", SELECTIONS, ids=[x[0] for x in SELECTIONS])
def test_real_selection_retains_provenance_without_scalar_or_call_change(
    fx_inputs, case, currency, expected, source, symbol,
):
    from portfolio import fx, price_evidence as pe

    configure_selection(fx_inputs, case, expected)
    values, calls, caches = [], [], []
    for capture in (False, True):
        fx.clear_cache()
        fx_inputs["calls"].clear()
        if capture:
            value, context = pe.read_with_evidence(fx.rate_per_usd, currency)
        else:
            value = fx.rate_per_usd(currency)
        values.append(value)
        calls.append(copy.deepcopy(fx_inputs["calls"]))
        caches.append(copy.deepcopy(fx._RATE_CACHE))
    assert values == [expected, expected]
    assert calls[0] == calls[1]
    assert caches[0] == caches[1]
    assert context["schema"] == "mastermind.fx_rate_evidence.v1"
    assert context["source"] == source
    assert context["symbol"] == symbol
    assert context["rate"] == expected
    assert context["currency"] == currency
    assert context["consumed_as"] == "foreign_units_per_USD"
    assert context["source_convention_qualification"] == "not_established"
    assert context["market_observed_at"] is None
    assert context["execution_qualification"] == "not_checked"
    if source == "forex_snapshot":
        path = fx_inputs["root"] / context["source_path"]
        assert context["source_text_sha256"] == hashlib.sha256(path.read_text().encode("utf-8")).hexdigest()
        assert context["source_text_digest_basis"] == "decoded_text_utf8"
    if currency == "USD":
        assert context["cache_state"] == "not_used" and caches == [{}, {}]


def test_last_nonnull_close_keeps_its_own_index(fx_inputs):
    from portfolio import fx, price_evidence as pe

    fx_inputs["rows"]["CNH=X"] = close_rows(7.1, trailing_null=True)
    value, context = pe.read_with_evidence(fx.rate_per_usd, "CNY")
    assert value == 7.1
    assert context["source_bar_label"] == "2026-10-12T00:00:00"
    assert context["source_bar_label_kind"] == "selected_close_index"
    assert fx_inputs["store_calls"] == ["CNH=X"]


@pytest.mark.parametrize("source", ["yahoo", "snapshot"])
def test_cache_keeps_original_selection_after_source_and_returned_context_change(fx_inputs, source):
    from portfolio import fx, price_evidence as pe

    if source == "yahoo":
        fx_inputs["rows"]["CNH=X"] = close_rows(7.1)
    else:
        put_snapshot(fx_inputs, {"USDCNH": {"quote": 7.1}})
    first, context = pe.read_with_evidence(fx.rate_per_usd, "CNY")
    original = copy.deepcopy(context)
    count = len(fx_inputs["calls"])
    context["source_bar_label"] = "2026-10-18"
    context["source"] = "caller_mutation"
    fx_inputs["rows"]["CNH=X"] = close_rows(8.0)
    put_snapshot(fx_inputs, {"USDCNH": {"quote": 9.0}})
    fx_inputs["clock"] = "2026-10-18T23:10:00+00:00"
    second, retained = pe.read_with_evidence(fx.rate_per_usd, "CNY")
    assert first == second == 7.1 and len(fx_inputs["calls"]) == count
    expected = dict(original, cache_state="hit", cache_observed_at=fx_inputs["clock"])
    assert retained == expected


@pytest.mark.parametrize("missing", ["legacy_seed", "replaced_tuple", "missing_sidecar", "malformed_sidecar"])
def test_unbound_cache_context_never_requests_a_rate_refresh(fx_inputs, missing):
    from portfolio import fx, price_evidence as pe

    fx_inputs["rows"]["CNH=X"] = close_rows(7.1)
    if missing == "legacy_seed":
        fx._RATE_CACHE["CNY"] = (7.1, "2026-10-18")
    else:
        pe.read_with_evidence(fx.rate_per_usd, "CNY")
        assert hasattr(fx, "_RATE_CONTEXT")
        if missing == "replaced_tuple":
            fx._RATE_CACHE["CNY"] = tuple(list(fx._RATE_CACHE["CNY"]))
        elif missing == "missing_sidecar":
            fx._RATE_CONTEXT.clear()
        else:
            entry, record = fx._RATE_CONTEXT["CNY"]
            fx._RATE_CONTEXT["CNY"] = (entry, dict(record, rate=9.0))
    before = copy.deepcopy(fx_inputs["calls"])
    fx_inputs["rows"]["CNH=X"] = close_rows(9.0)
    value, context = pe.read_with_evidence(fx.rate_per_usd, "CNY")
    assert value == 7.1 and fx_inputs["calls"] == before
    assert context["source"] == "unavailable"
    assert context["status"] == "unavailable"
    assert context["reason"] == "cache_context_unavailable"
    assert context["rate"] == 7.1


def test_day_rollover_refreshes_using_the_existing_order(fx_inputs):
    from portfolio import fx, price_evidence as pe

    fx_inputs["rows"]["CNH=X"] = close_rows(7.1)
    first, _ = pe.read_with_evidence(fx.rate_per_usd, "CNY")
    fx_inputs["day"] = date(2026, 10, 19)
    fx_inputs["clock"] = "2026-10-19T01:00:00+00:00"
    fx_inputs["rows"]["CNH=X"] = None
    fx_inputs["rows"]["CNY=X"] = close_rows(7.2)
    value, context = pe.read_with_evidence(fx.rate_per_usd, "CNY")
    assert first == 7.1 and value == 7.2
    assert fx_inputs["calls"] == [["yahoo", "CNH=X"], ["yahoo", "CNH=X"], ["yahoo", "CNY=X"]]
    assert context["symbol"] == "CNY=X" and context["cache_population_day"] == "2026-10-19"


@pytest.mark.parametrize("helper", ["clock", "source_context", "make_rate", "emit"])
def test_observation_fault_does_not_advance_source_or_discard_cache(fx_inputs, monkeypatch, helper):
    from portfolio import fx, fx_evidence as fe, price_evidence as pe

    fx_inputs["rows"]["CNH=X"] = close_rows(7.1)
    def broken(*args, **kwargs):
        raise RuntimeError("synthetic observation fault")
    monkeypatch.setattr(fe, helper, broken)
    value, _ = pe.read_with_evidence(fx.rate_per_usd, "CNY")
    assert value == 7.1
    assert fx._RATE_CACHE["CNY"] == (7.1, "2026-10-18")
    assert fx_inputs["calls"] == [["yahoo", "CNH=X"]]


def test_failed_sink_does_not_replace_numeric_selection(fx_inputs):
    from portfolio import fx

    class BrokenSink(dict):
        def clear(self):
            raise RuntimeError("synthetic sink failure")
    fx_inputs["rows"]["CNH=X"] = close_rows(7.1)
    assert fx.rate_per_usd("CNY", _evidence=BrokenSink()) == 7.1
    assert fx._RATE_CACHE["CNY"] == (7.1, "2026-10-18")
    assert fx_inputs["calls"] == [["yahoo", "CNH=X"]]


@pytest.mark.parametrize("operation", ["to_usd", "usd_to"])
@pytest.mark.parametrize("value", [None, 0, -1, "invalid", 1, True, float("nan"), float("inf")])
def test_conversion_capture_preserves_scalar_edge_cases(fx_inputs, operation, value):
    from portfolio import fx, price_evidence as pe

    fx_inputs["rows"]["CNH=X"] = close_rows(7.1)
    arg = "600519.SS" if operation == "to_usd" else "CNY"
    reader = getattr(fx, operation)
    off = reader(value, arg)
    calls = copy.deepcopy(fx_inputs["calls"])
    fx.clear_cache()
    fx_inputs["calls"].clear()
    on, _ = pe.read_with_evidence(reader, value, arg)
    assert (math.isnan(off) and math.isnan(on)) if isinstance(off, float) and math.isnan(off) else off == on
    assert calls == fx_inputs["calls"]


@pytest.mark.parametrize("kind", ["legacy", "kwargs_only", "uninspectable"])
def test_legacy_rate_adapter_is_called_once_without_speculative_keyword(fx_inputs, monkeypatch, kind):
    from portfolio import fx, price_evidence as pe

    calls = []
    def legacy(currency):
        calls.append((currency, {}))
        return 7.1
    def kwargs_only(currency, **kwargs):
        calls.append((currency, kwargs))
        return 7.1
    if kind == "uninspectable":
        legacy.__signature__ = "not a signature"
    monkeypatch.setattr(fx, "rate_per_usd", kwargs_only if kind == "kwargs_only" else legacy)
    value, context = pe.read_with_evidence(fx.to_usd, 71.0, "600519.SS")
    assert value == 10.0 and calls == [("CNY", {})] and context == {}


def test_rate_exception_after_entry_is_not_retried(fx_inputs, monkeypatch):
    from portfolio import fx, price_evidence as pe

    calls = []
    def failed(currency, *, _evidence=None):
        calls.append(currency)
        raise TypeError("after rate entry")
    monkeypatch.setattr(fx, "rate_per_usd", failed)
    with pytest.raises(TypeError, match="after rate entry"):
        pe.read_with_evidence(fx.to_usd, 71.0, "600519.SS")
    assert calls == ["CNY"]


def captured_rate(state, currency="CNY", rate=7.1):
    from portfolio import fx, price_evidence as pe
    state["rows"]["CNH=X" if currency == "CNY" else "HKD=X"] = close_rows(rate)
    return pe.read_with_evidence(fx.rate_per_usd, currency)[1]


def converted_context(rate, *, ticker="600519.SS", input_price=71.0, output=10.0,
                      input_currency="CNY", currency="USD", operation="divide", upstream=None):
    from portfolio import price_evidence as pe
    return pe.make_read(
        ticker, output, currency, "captured_fx", stage="paper_live",
        input_price=input_price, input_currency=input_currency, upstream=upstream,
        fx_context=rate, fx_operation=operation,
    )


def test_conversion_v2_preserves_v1_constant_and_binds_each_currency(fx_inputs):
    from portfolio import price_evidence as pe

    context = converted_context(captured_rate(fx_inputs))
    assert pe.READ_SCHEMA == "mastermind.price_read.v1"
    assert context["schema"] == "mastermind.price_read.v2"
    assert context["fx_observation"] == "matched"
    copied, reason = pe.bound_context(context, "600519.SS", 10.0, "USD")
    assert reason is None and copied == context
    assert pe.bound_context(context, "600519.SS", 10.0, "HKD") == (None, "currency_mismatch")
    context["fx_rate"]["rate"] = 9.0
    assert copied["fx_rate"]["rate"] == 7.1


@pytest.mark.parametrize("field,value", [
    ("rate", 9.0), ("currency", "HKD"), ("rate", True), ("rate", float("inf")),
    ("symbol", "HKD=X"), ("market_observed_at", "2026-10-18T00:00:00+00:00"),
    ("execution_qualification", "passed"), ("source_convention_qualification", "verified"),
    ("extra", {"secret": "not traversed"}), ("source_bar_label", "x" * 10000),
])
def test_bad_rate_context_is_unavailable_without_changing_conversion_values(fx_inputs, field, value):
    from portfolio import price_evidence as pe

    rate = captured_rate(fx_inputs)
    rate[field] = value
    record = converted_context(rate)
    assert record["price"] == 10.0 and record["input_price"] == 71.0
    assert record["fx_observation"] == "unavailable" and record["fx_rate"] is None
    assert pe.bound_context(record, "600519.SS", 10.0, "USD")[0] == record


@pytest.mark.parametrize("field,value", [
    ("fx_operation", "multiply"), ("input_currency", "HKD"), ("price", 11.0),
    ("fx_observation", "unavailable"), ("fx_binding_reason", "invented"),
])
def test_retained_v2_tampering_cannot_rebind_a_rate(fx_inputs, field, value):
    from portfolio import price_evidence as pe

    record = converted_context(captured_rate(fx_inputs))
    record[field] = value
    copied, reason = pe.bound_context(record, "600519.SS", record["price"], "USD")
    assert copied is None and reason == "invalid_fx_binding"


def test_unobserved_population_preserves_actual_source_for_later_receipt(fx_inputs):
    from portfolio import fx, price_evidence as pe

    fx_inputs["rows"]["CNH=X"] = close_rows(7.1)
    assert fx.rate_per_usd("CNY") == 7.1
    fx_inputs["rows"]["CNH=X"] = close_rows(9.0)
    before = copy.deepcopy(fx_inputs["calls"])
    value, context = pe.read_with_evidence(fx.rate_per_usd, "CNY")
    assert value == 7.1 and fx_inputs["calls"] == before
    assert context["source"] == "yahoo_store"
    assert context["symbol"] == "CNH=X"
    assert context["source_bar_label"] == "2026-10-12T00:00:00"
    assert context["cache_state"] == "hit"


def test_literal_legacy_conversion_and_receipt_reconstruct_unchanged():
    from portfolio import price_evidence as pe

    legacy = {
        "schema": "mastermind.price_read.v1", "ticker": "600519.SS",
        "stage": "paper_live", "source": "captured_fx", "price": 10.0, "currency": "USD",
        "read_status": "returned", "upstream": None, "upstream_status": "unavailable",
        "upstream_reason": "not_captured", "source_bar_label": None,
        "source_bar_label_kind": None, "source_text_sha256": None, "attempts": [],
        "market_observed_at": None, "execution_qualification": "not_checked",
        "input_price": 71.0, "input_currency": "CNY", "fx_observation": "not_captured",
    }
    assert pe.bound_context(legacy, "600519.SS", 10.0, "USD") == (legacy, None)
    assert pe.make_read("600519.SS", 10.0, "USD", "captured_fx", stage="paper_live",
                        input_price=71.0, input_currency="CNY") == legacy
    prices, sources = {"600519.SS": 10.0}, {"600519.SS": "captured_fx"}
    captured = {
        "schema": "mastermind.settlement_price_evidence.v1", "currency": "USD",
        "quotes": {"600519.SS": {"price": 10.0, "source": "captured_fx",
                   "binding_status": "matched", "reason": None, "observation": legacy}},
        "omitted_quote_count": 0, "market_observed_at": None,
        "execution_qualification": "not_checked",
    }
    assert pe.validated_settlement_snapshot(prices, sources, "USD", captured) == captured


def test_mixed_conversion_nodes_retain_both_actual_rate_legs(fx_inputs):
    from portfolio import price_evidence as pe

    rate = captured_rate(fx_inputs)
    native = pe.make_read("600519.SS", 71.0, "CNY", "native_quote", stage="quote")
    usd = converted_context(rate, upstream=native)
    mark = pe.make_read("600519.SS", 10.0, "USD", "live_price", stage="paper_current", upstream=usd)
    book = converted_context(rate, input_price=10.0, output=71.0, input_currency="USD",
                             currency="CNY", operation="multiply", upstream=mark)
    copied, reason = pe.bound_context(book, "600519.SS", 71.0, "CNY")
    assert reason is None and copied == book
    assert copied["fx_operation"] == "multiply"
    assert copied["upstream"]["upstream"]["fx_operation"] == "divide"
    copied["upstream"]["upstream"]["fx_rate"]["currency"] = "HKD"
    assert pe.bound_context(copied, "600519.SS", 71.0, "CNY") == (None, "invalid_upstream")


def test_complete_tree_byte_limit_counts_the_fx_child(fx_inputs, monkeypatch):
    from portfolio import price_evidence as pe

    record = converted_context(captured_rate(fx_inputs))
    size = len(json.dumps(record, allow_nan=False, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    assert pe.MAX_CONTEXT_BYTES == 16384 and size < pe.MAX_CONTEXT_BYTES
    monkeypatch.setattr(pe, "MAX_CONTEXT_BYTES", size)
    assert pe.bound_context(record, "600519.SS", 10.0, "USD") == (record, None)
    monkeypatch.setattr(pe, "MAX_CONTEXT_BYTES", size - 1)
    assert pe.bound_context(record, "600519.SS", 10.0, "USD") == (None, "context_too_large")


def test_fx_capture_keeps_existing_128_quote_limit_and_explicit_omission(fx_inputs):
    from portfolio import price_evidence as pe

    rate = captured_rate(fx_inputs)
    prices = {f"T{i:03d}": 10.0 for i in range(129)}
    sources = {ticker: "captured_fx" for ticker in prices}
    contexts = {ticker: converted_context(rate, ticker=ticker) for ticker in prices}
    record = pe.settlement_snapshot(prices, sources, "USD", contexts)
    assert len(record["quotes"]) == 128 and record["omitted_quote_count"] == 1
    assert "T128" not in record["quotes"]
    assert all(q["observation"]["fx_rate"]["rate"] == 7.1 for q in record["quotes"].values())
    assert pe.validated_settlement_snapshot(prices, sources, "USD", record) == record


@pytest.fixture
def real_fx_books(fx_inputs, monkeypatch, tmp_path):
    from data_layer import tushare_feed, yahoo_feed
    from portfolio import fx, paper_account, registry
    from test_selected_price_evidence import yahoo_context

    assert fx.rate_per_usd.__name__ == "rate_per_usd"
    monkeypatch.setattr(registry, "_ROOT", tmp_path / "accounts")
    monkeypatch.setattr(paper_account, "_ROOT", tmp_path / "accounts")
    monkeypatch.setattr(paper_account, "_fetch_price_series", lambda ticker: None)
    fx_inputs["day"] = date(2026, 8, 13)
    fx_inputs["clock"] = "2026-08-13T14:00:00+00:00"
    for symbol, rate in (("CNH=X", 7.0), ("HKD=X", 7.8)):
        fx_inputs["rows"][symbol] = pd.DataFrame(
            {"close": [rate]}, index=pd.to_datetime(["2026-08-11"]),
        )
    state = {"quotes": {}, "quote_calls": [], "fx": fx_inputs}
    def quote(ticker, *, _evidence=None):
        state["quote_calls"].append(ticker)
        value = state["quotes"].get(ticker)
        if value is not None and _evidence is not None:
            _evidence.update(yahoo_context(ticker, value))
        return value
    monkeypatch.setattr(yahoo_feed, "price_local", quote)
    monkeypatch.setattr(tushare_feed, "price_local", lambda ticker: None)
    return state


def selected_book_inputs(state, book, *, weight=0.20):
    from bot import settle
    from portfolio import price_evidence as pe
    from test_selected_price_evidence import EVIDENCE_BOOKS

    _, native, _ = _seed_evidence_book(book, weight=weight)
    state["quotes"].update(native)
    (prices, sources), contexts = pe.read_with_evidence(settle._price_and_sources, book, list(native))
    assert prices == native
    ticker = EVIDENCE_BOOKS[book][0]
    root = contexts[ticker]
    assert root["schema"] == "mastermind.price_read.v2"
    assert root["fx_operation"] == "multiply"
    inner = root["upstream"]["upstream"]
    assert inner["schema"] == "mastermind.price_read.v2" and inner["fx_operation"] == "divide"
    assert root["fx_rate"]["symbol"] == inner["fx_rate"]["symbol"]
    assert root["fx_rate"]["cache_state"] == "hit"
    assert inner["fx_rate"]["source_bar_label"] == "2026-08-11T00:00:00"
    return prices, sources, contexts


@pytest.mark.parametrize("book", ["china", "hk"])
@pytest.mark.parametrize("weight", [0.20, 1e-9], ids=["filled", "zero_fill"])
@pytest.mark.parametrize("stage", ["before_account_replace", "after_account_replace"])
def test_real_fx_producer_wal_recovery_reuses_original_observation_and_ids(
    real_fx_books, monkeypatch, book, weight, stage,
):
    from portfolio import fx, paper_account, price_evidence as pe

    prices, sources, contexts = selected_book_inputs(real_fx_books, book, weight=weight)
    real_save = paper_account._save_account
    def fail_save(state, portfolio_id=None):
        if stage == "after_account_replace":
            real_save(state, portfolio_id)
        raise OSError(stage)
    with monkeypatch.context() as patch:
        patch.setattr(paper_account, "_save_account", fail_save)
        with pytest.raises(OSError, match=stage):
            paper_account.settle_target(prices, "2026-08-13", portfolio_id=book,
                                        _price_sources=sources, _evidence=contexts)
    wal = json.loads(paper_account._transaction_path(book).read_bytes())
    recorded = copy.deepcopy(wal["followup"]["settlement_price_evidence"])
    real_fx_books["fx"]["rows"]["CNH=X"] = close_rows(9.0)
    real_fx_books["fx"]["rows"]["HKD=X"] = close_rows(9.0)
    fx.clear_cache()
    def forbidden(*args, **kwargs):
        raise AssertionError("FX or price reconstruction during original-receipt recovery")
    for name in ("to_usd", "usd_to", "rate_per_usd", "_from_yahoo_store", "_from_forex_snapshot"):
        monkeypatch.setattr(fx, name, forbidden)
    monkeypatch.setattr(paper_account, "_current_price", forbidden)
    monkeypatch.setattr(pe, "settlement_snapshot", forbidden)
    recovered = paper_account.recover_paper_transaction(book)
    receipt, = paper_account.pending_settlement_receipts(book)
    assert recovered["transaction_id"] == wal["transaction_id"] == receipt["transaction_id"]
    assert receipt["transaction_identity"]["followup"]["settlement_price_evidence"] == recorded
    fills = paper_account.validated_settlement_receipt_fills(receipt)
    assert len(fills) == (1 if weight == 0.20 else 0)
    before = _selected_numeric_bytes(book)
    assert paper_account.recover_paper_transaction(book) is None
    assert _selected_numeric_bytes(book) == before


def test_malformed_boolean_source_rate_cannot_decorate_real_scalar(fx_inputs, monkeypatch):
    from portfolio import fx, fx_evidence as fe, price_evidence as pe

    fx_inputs["rows"]["CNH=X"] = close_rows(1.0)
    original = fe.source_context
    def malformed(sink, **kwargs):
        original(sink, **kwargs)
        sink["rate"] = True
    monkeypatch.setattr(fe, "source_context", malformed)
    value, context = pe.read_with_evidence(fx.rate_per_usd, "CNY")
    assert value == 1.0 and fx_inputs["calls"] == [["yahoo", "CNH=X"]]
    assert context["source"] == "unavailable"
    assert context["reason"] == "source_value_mismatch"


@pytest.mark.parametrize("book", ["china", "hk"])
@pytest.mark.parametrize("weight", [0.20, 1e-9], ids=["filled", "zero_fill"])
def test_real_fx_queued_ack_retry_preserves_original_receipt_without_new_rates(
    real_fx_books, monkeypatch, book, weight,
):
    from bot import settle
    from portfolio import fx, paper_account, price_evidence as pe, registry
    from test_selected_price_evidence import EVIDENCE_BOOKS

    _, prices, _ = _seed_evidence_book(book, weight=weight)
    real_fx_books["quotes"].update(prices)
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(settle, "_republish", lambda *a, **k: {"ok": True})
    actual_ack = paper_account.acknowledge_settlement_receipt
    retained = []

    def failed_ack(transaction_id, portfolio_id=None):
        retained.append(paper_account._settlement_receipt_path(
            transaction_id, portfolio_id,
        ).read_bytes())
        raise OSError("synthetic FX acknowledgement fault")

    with monkeypatch.context() as patch:
        patch.setattr(paper_account, "acknowledge_settlement_receipt", failed_ack)
        first = settle.settle_open(book, "2026-08-13")
    assert first["skipped"] == "settlement_receipt_ack_pending"
    assert len(retained) == 1
    receipt, = paper_account.pending_settlement_receipts(book)
    capture = receipt["transaction_identity"]["followup"]["settlement_price_evidence"]
    assert {t: q["price"] for t, q in capture["quotes"].items()} == prices
    ticker = EVIDENCE_BOOKS[book][0]
    outer = capture["quotes"][ticker]["observation"]
    inner = outer["upstream"]["upstream"]
    assert outer["schema"] == inner["schema"] == "mastermind.price_read.v2"
    assert outer["fx_operation"] == "multiply" and inner["fx_operation"] == "divide"
    assert outer["fx_rate"]["symbol"] == inner["fx_rate"]["symbol"]
    assert inner["fx_rate"]["source_bar_label"] == "2026-08-11T00:00:00"
    assert len(paper_account.validated_settlement_receipt_fills(receipt)) == (
        1 if weight == 0.20 else 0
    )
    before = _selected_numeric_bytes(book)
    journal = registry.data_dir(book) / "decisions.jsonl"
    before_journal = journal.read_bytes()
    before_calls = copy.deepcopy(real_fx_books["fx"]["calls"])
    before_quotes = list(real_fx_books["quote_calls"])

    real_fx_books["fx"]["rows"]["CNH=X"] = close_rows(9.0)
    real_fx_books["fx"]["rows"]["HKD=X"] = close_rows(9.0)
    fx.clear_cache()

    def forbidden(*args, **kwargs):
        raise AssertionError("FX acknowledgement retry must reuse the original receipt")

    def checked_ack(transaction_id, portfolio_id=None):
        path = paper_account._settlement_receipt_path(transaction_id, portfolio_id)
        assert path.read_bytes() == retained[0]
        return actual_ack(transaction_id, portfolio_id)

    for name in ("rate_per_usd", "to_usd", "usd_to", "_from_yahoo_store", "_from_forex_snapshot"):
        monkeypatch.setattr(fx, name, forbidden)
    monkeypatch.setattr(settle, "_price_and_sources", forbidden)
    monkeypatch.setattr(settle, "_open_price_usd", forbidden)
    monkeypatch.setattr(paper_account, "_current_price", forbidden)
    monkeypatch.setattr(pe, "settlement_snapshot", forbidden)
    monkeypatch.setattr(paper_account, "acknowledge_settlement_receipt", checked_ack)
    retried = settle.settle_open(book, "2026-08-14", _open_price_fn=forbidden)
    assert retried["ok"] is True
    assert retried["transaction_id"] == first["transaction_id"]
    assert retried["executed"] == first["executed"]
    assert _selected_numeric_bytes(book) == before
    assert journal.read_bytes() == before_journal
    assert real_fx_books["fx"]["calls"] == before_calls
    assert real_fx_books["quote_calls"] == before_quotes
