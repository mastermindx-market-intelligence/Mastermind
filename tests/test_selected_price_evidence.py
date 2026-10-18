"""Selected-source observations must preserve numeric policy and never invent clocks."""
from __future__ import annotations

import copy
import hashlib
import json

import pandas as pd
import pytest

BOOKS = [
    ("AAPL", 100.0, "USD"),
    ("600519.SS", 700.0, "CNY"),
    ("0700.HK", 780.0, "HKD"),
]


def yahoo_context(ticker, price):
    return {
        "schema": "mastermind.yahoo_daily_bar_evidence.v1",
        "ticker": ticker, "field": "Close", "status": "available", "reason": None,
        "price_local": price, "source_bar_label": "2026-08-12T00:00:00",
        "source_bar_label_kind": "daily_bar_label",
        "fetch_started_at": "2026-08-13T14:00:00+00:00",
        "download_returned_at": "2026-08-13T14:00:03+00:00",
        "fetch_age_seconds": 3.0, "within_cache_ttl": True,
        "market_observed_at": None, "execution_qualification": "not_checked",
    }


@pytest.fixture
def price_paths(tmp_path, monkeypatch):
    from data_layer import tushare_feed, yahoo_feed
    from portfolio import fx, paper_account

    monkeypatch.setattr(paper_account, "_ROOT", tmp_path)
    monkeypatch.setattr(paper_account, "_fetch_price_series", lambda ticker: None)
    monkeypatch.setattr(yahoo_feed, "price_local", lambda ticker: None)
    monkeypatch.setattr(tushare_feed, "price_local", lambda ticker: None)
    monkeypatch.setattr(fx, "rate_per_usd", lambda currency: {
        "USD": 1.0, "CNY": 7.0, "HKD": 7.8,
    }[currency])
    return tmp_path


@pytest.mark.parametrize("ticker,native,currency", BOOKS)
@pytest.mark.parametrize("entry", ["_live_price", "_current_price"])
def test_actual_paper_selector_carries_selected_yahoo_native_and_usd_facts(
    price_paths, monkeypatch, ticker, native, currency, entry
):
    from data_layer import yahoo_feed
    from portfolio import paper_account, price_evidence

    calls = []
    supplied = yahoo_context(ticker, native)

    def quote(symbol, *, _evidence=None):
        calls.append((symbol, _evidence is not None))
        if _evidence is not None:
            _evidence.update(copy.deepcopy(supplied))
        return native

    monkeypatch.setattr(yahoo_feed, "price_local", quote)
    result, context = price_evidence.read_with_evidence(getattr(paper_account, entry), ticker)

    assert result == 100.0
    assert context["schema"] == price_evidence.READ_SCHEMA
    assert context["price"] == result
    assert context["currency"] == "USD"
    live = context if entry == "_live_price" else context["upstream"]
    assert live["source"] == "yahoo_close"
    assert live["input_price"] == native
    assert live["input_currency"] == currency
    assert live["fx_observation"] == ("not_required" if currency == "USD" else "not_captured")
    assert live["upstream"] == supplied
    assert live["market_observed_at"] is None
    assert live["execution_qualification"] == "not_checked"
    assert calls == [(ticker, True)]
    context["upstream"]["source_bar_label"] = "changed by caller"
    assert supplied["source_bar_label"] == "2026-08-12T00:00:00"
    json.dumps(context, allow_nan=False)


def test_scalar_only_quote_is_called_once_and_missing_context_is_explicit(price_paths, monkeypatch):
    from data_layer import yahoo_feed
    from portfolio import paper_account, price_evidence

    calls = []

    def legacy_quote(ticker):
        calls.append(ticker)
        return 100.0

    monkeypatch.setattr(yahoo_feed, "price_local", legacy_quote)
    price, context = price_evidence.read_with_evidence(paper_account._current_price, "AAPL")

    assert price == 100.0
    live = context["upstream"]
    assert live["source"] == "yahoo_close"
    assert live["upstream"] is None
    assert live["upstream_status"] == "unavailable"
    assert live["upstream_reason"] == "not_captured"
    assert calls == ["AAPL"]


@pytest.mark.parametrize("yahoo_outcome", ["missing", "error"])
def test_china_fallback_keeps_tushare_selection_and_records_yahoo_failure(
    price_paths, monkeypatch, yahoo_outcome
):
    from data_layer import tushare_feed, yahoo_feed
    from portfolio import paper_account, price_evidence

    calls = []

    def yahoo(ticker):
        calls.append("yahoo")
        if yahoo_outcome == "error":
            raise OSError("synthetic read failure")
        return None

    def tushare(ticker):
        calls.append("tushare")
        return 700.0

    monkeypatch.setattr(yahoo_feed, "price_local", yahoo)
    monkeypatch.setattr(tushare_feed, "price_local", tushare)
    value, context = price_evidence.read_with_evidence(paper_account._live_price, "600519.SS")

    assert value == 100.0
    assert context["source"] == "tushare_close"
    assert context["upstream_status"] == "unavailable"
    assert context["attempts"] == [
        {"source": "yahoo_close", "outcome": yahoo_outcome},
        {"source": "tushare_close", "outcome": "returned"},
    ]
    assert calls == ["yahoo", "tushare"]


@pytest.mark.parametrize("ticker,native,currency", BOOKS)
def test_snapshot_label_and_text_fingerprint_come_from_the_same_read(
    price_paths, ticker, native, currency
):
    from portfolio import paper_account, price_evidence

    folder = {"USD": "stockdata", "CNY": "chinastockdata", "HKD": "hkstockdata"}[currency]
    path = price_paths / "vendor" / "macro" / "site" / folder / (ticker + ".json")
    path.parent.mkdir(parents=True)
    text = json.dumps({"asof": "2026-08-12", "tech": {"price": native}}, indent=2)
    path.write_text(text)
    value, context = price_evidence.read_with_evidence(paper_account._live_price, ticker)

    assert value == 100.0
    assert context["source"] == "macro_snapshot"
    assert context["source_bar_label"] == "2026-08-12"
    assert context["source_bar_label_kind"] == "snapshot_asof"
    assert context["source_text_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert context["input_currency"] == currency
    assert context["market_observed_at"] is None


@pytest.mark.parametrize("ticker,native,currency", BOOKS)
def test_engine_fallback_retains_selected_index_and_conversion_inputs(
    price_paths, monkeypatch, ticker, native, currency
):
    from portfolio import paper_account, price_evidence

    series = pd.Series([native - 1.0, native], index=pd.to_datetime(["2026-08-11", "2026-08-12"]))
    monkeypatch.setattr(paper_account, "_live_price", lambda symbol: None)
    monkeypatch.setattr(paper_account, "_fetch_price_series", lambda symbol: series)
    value, context = price_evidence.read_with_evidence(paper_account._current_price, ticker)

    assert value == 100.0
    assert context["source"] == "engine_series"
    assert context["source_bar_label"] == "2026-08-12T00:00:00"
    assert context["source_bar_label_kind"] == "series_index"
    assert context["input_price"] == native
    assert context["input_currency"] == currency
    assert context["execution_qualification"] == "not_checked"


def test_invalid_live_value_still_uses_existing_engine_fallback(price_paths, monkeypatch):
    from data_layer import yahoo_feed
    from portfolio import paper_account, price_evidence

    monkeypatch.setattr(yahoo_feed, "price_local", lambda ticker: 0.0)
    monkeypatch.setattr(
        paper_account, "_fetch_price_series",
        lambda ticker: pd.Series([123.0], index=pd.to_datetime(["2026-08-12"])),
    )
    value, context = price_evidence.read_with_evidence(paper_account._current_price, "AAPL")

    assert value == 123.0
    assert context["source"] == "engine_series"
    assert context["attempts"] == [{"source": "live_price", "outcome": "invalid_value"}]


def test_observation_emission_failure_does_not_change_the_selected_scalar(price_paths, monkeypatch):
    from data_layer import yahoo_feed
    from portfolio import paper_account, price_evidence

    monkeypatch.setattr(yahoo_feed, "price_local", lambda ticker: 100.0)

    def broken(*args, **kwargs):
        raise RuntimeError("synthetic observation failure")

    monkeypatch.setattr(price_evidence, "emit", broken)
    assert paper_account._live_price("AAPL", _evidence={}) == 100.0
    assert paper_account._current_price("AAPL", _evidence={}) == 100.0


@pytest.mark.parametrize("reader_kind", ["legacy", "kwargs_only", "signature_unavailable"])
def test_reader_capability_detection_does_not_probe_or_retry(monkeypatch, reader_kind):
    from portfolio import price_evidence

    calls = []

    def legacy(ticker):
        calls.append((ticker, {}))
        return 123.0

    def kwargs_only(ticker, **kwargs):
        calls.append((ticker, kwargs))
        return 123.0

    if reader_kind == "signature_unavailable":
        def unavailable(reader):
            raise ValueError("signature unavailable")
        monkeypatch.setattr(price_evidence.inspect, "signature", unavailable)
    reader = kwargs_only if reader_kind == "kwargs_only" else legacy
    value, context = price_evidence.read_with_evidence(reader, "AAPL")

    assert value == 123.0
    assert context == {}
    assert calls == [("AAPL", {})]


def test_reader_typeerror_after_start_is_not_retried_as_a_legacy_call():
    from portfolio import price_evidence

    calls = []

    def reader(ticker, *, _evidence=None):
        calls.append(ticker)
        raise TypeError("inside reader")

    with pytest.raises(TypeError, match="inside reader"):
        price_evidence.read_with_evidence(reader, "AAPL")
    assert calls == ["AAPL"]


@pytest.mark.parametrize("field,value,reason", [
    ("ticker", "MSFT", "ticker_mismatch"),
    ("price_local", 101.0, "price_mismatch"),
    ("execution_qualification", "qualified", "qualification_not_supported"),
    ("market_observed_at", "2026-08-13T14:00:00+00:00", "qualification_not_supported"),
])
def test_mismatched_or_overclaimed_upstream_cannot_lend_its_clocks(
    price_paths, monkeypatch, field, value, reason
):
    from data_layer import yahoo_feed
    from portfolio import paper_account, price_evidence

    def quote(ticker, *, _evidence=None):
        if _evidence is not None:
            payload = yahoo_context(ticker, 100.0)
            payload[field] = value
            _evidence.update(payload)
        return 100.0

    monkeypatch.setattr(yahoo_feed, "price_local", quote)
    selected, context = price_evidence.read_with_evidence(paper_account._live_price, "AAPL")

    assert selected == 100.0
    assert context["upstream"] is None
    assert context["upstream_status"] == "unavailable"
    assert context["upstream_reason"] == reason


@pytest.mark.parametrize("helper", ["positive_number", "make_read"])
@pytest.mark.parametrize("entry", ["_live_price", "_current_price"])
def test_metadata_helper_failure_cannot_discard_a_successful_quote(
    price_paths, monkeypatch, helper, entry
):
    from data_layer import yahoo_feed
    from portfolio import paper_account, price_evidence

    calls = []

    def quote(ticker):
        calls.append(ticker)
        return 100.0

    def broken(*args, **kwargs):
        raise RuntimeError("synthetic diagnostic helper failure")

    monkeypatch.setattr(yahoo_feed, "price_local", quote)
    monkeypatch.setattr(price_evidence, helper, broken)

    assert getattr(paper_account, entry)("AAPL", _evidence={}) == 100.0
    assert calls == ["AAPL"]


@pytest.mark.parametrize("field,value", [
    ("ticker", "MSFT"), ("price", 101.0), ("currency", "HKD"),
])
def test_nested_tampering_cannot_lend_clocks_to_a_matching_settlement_root(field, value):
    from portfolio import price_evidence as pe

    child = pe.make_read(
        "AAPL", 100.0, "USD", "yahoo_close", stage="paper_live",
        upstream=yahoo_context("AAPL", 100.0),
    )
    root = pe.make_read("AAPL", 100.0, "USD", "last_price", stage="settlement_input", upstream=child)
    root["upstream"][field] = value
    snapshot = pe.settlement_snapshot({"AAPL": 100.0}, {"AAPL": "last_price"}, "USD", {"AAPL": root})

    quote = snapshot["quotes"]["AAPL"]
    assert quote["price"] == 100.0
    assert quote["binding_status"] == "unavailable"
    assert quote["observation"] is None
    assert quote["reason"]
    assert snapshot["execution_qualification"] == "not_checked"


@pytest.mark.parametrize("schema_kind", ["yahoo", "read"])
def test_unrecognized_fields_are_not_copied_into_persisted_price_context(schema_kind):
    from portfolio import price_evidence as pe

    context = yahoo_context("AAPL", 100.0) if schema_kind == "yahoo" else pe.make_read(
        "AAPL", 100.0, "USD", "last_price", stage="settlement_input",
    )
    context["undisclosed_provider_payload"] = {"private_field": "must not persist"}
    copied, reason = pe.bound_context(context, "AAPL", 100.0, "USD")

    assert copied is None
    assert reason


def test_oversized_context_is_rejected_before_json_serialization(monkeypatch):
    from portfolio import price_evidence as pe

    context = yahoo_context("AAPL", 100.0)
    context["source_bar_label"] = "x" * (pe.MAX_CONTEXT_BYTES + 1)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("oversized input reached serializer")

    monkeypatch.setattr(pe.json, "dumps", forbidden)
    copied, reason = pe.bound_context(context, "AAPL", 100.0, "USD")

    assert copied is None
    assert reason
    assert calls == []


EVIDENCE_BOOKS = {
    "autonomous": ("AAPL", "SPY", "USD", 100.0, "bot.autonomous"),
    "china": ("600519.SS", "000300.SS", "CNY", 700.0, "bot.china"),
    "hk": ("0700.HK", "^HSI", "HKD", 780.0, "bot.hk"),
}


def _source_path(monkeypatch, book):
    from data_layer import polygon, yahoo_feed

    ticker, benchmark, currency, native, _ = EVIDENCE_BOOKS[book]
    prices = {ticker: native, benchmark: native * 5}
    calls = []

    def close(symbol, *, _evidence=None):
        calls.append(("close", symbol))
        if _evidence is not None:
            _evidence.update(yahoo_context(symbol, prices[symbol]))
        return prices[symbol]

    monkeypatch.setattr(polygon, "day_open", lambda symbol: None)
    monkeypatch.setattr(yahoo_feed, "open_price_local", lambda symbol: None)
    monkeypatch.setattr(yahoo_feed, "price_local", close)
    return prices, calls


@pytest.mark.parametrize("book", EVIDENCE_BOOKS)
def test_actual_settlement_selector_carries_native_usd_and_book_values(price_paths, monkeypatch, book):
    from bot import settle
    from portfolio import price_evidence as pe

    expected, calls = _source_path(monkeypatch, book)
    ticker, _, currency, native, _ = EVIDENCE_BOOKS[book]
    (prices, sources), observations = pe.read_with_evidence(settle._price_and_sources, book, list(expected))
    snapshot = pe.settlement_snapshot(prices, sources, currency, observations)

    assert prices == expected
    assert sources == {symbol: "last_price" for symbol in expected}
    assert calls == [("close", symbol) for symbol in expected]
    root = snapshot["quotes"][ticker]
    assert root["binding_status"] == "matched"
    node = root["observation"]
    assert node["price"] == native
    if currency != "USD":
        assert node["input_price"] == 100.0
        assert node["input_currency"] == "USD"
        assert node["fx_observation"] == "not_captured"
    while node["schema"] == pe.READ_SCHEMA:
        assert node["market_observed_at"] is None
        assert node["execution_qualification"] == "not_checked"
        node = node["upstream"]
    assert node == yahoo_context(ticker, native)


@pytest.mark.parametrize("selected", ["polygon_open", "yahoo_open", "last_price"])
def test_open_selection_keeps_source_priority_and_calls_each_attempt_once(selected):
    from bot import settle
    from portfolio import price_evidence as pe

    calls = []
    names = ["polygon_open", "yahoo_open", "last_price"]

    def quote(name):
        def reader(ticker):
            calls.append(name)
            return 123.0 if name == selected else None
        return reader

    (price, source), context = pe.read_with_evidence(
        settle._open_price_usd, "AAPL",
        _polygon=quote(names[0]), _yahoo=quote(names[1]), _paper=quote(names[2]),
    )
    assert (price, source) == (123.0, selected)
    assert calls == names[:names.index(selected) + 1]
    assert context["upstream"] is None
    assert context["upstream_reason"] == "not_captured"
    assert context["attempts"][-1] == {"source": selected, "outcome": "selected"}


@pytest.mark.parametrize("book", [*EVIDENCE_BOOKS, "etf"])
def test_settlement_metadata_failure_preserves_real_scalar_selection(price_paths, monkeypatch, book):
    from bot import settle
    from portfolio import etf_universe, price_evidence as pe

    if book == "etf":
        expected, calls = {"SPY": 123.0}, []
        monkeypatch.setattr(etf_universe, "warm", lambda symbols: None)

        def etf_quote(symbol):
            calls.append(("close", symbol))
            return expected[symbol]

        monkeypatch.setattr(etf_universe, "price", etf_quote)
    else:
        expected, calls = _source_path(monkeypatch, book)

    def broken(*args, **kwargs):
        raise RuntimeError("synthetic context factory failure")

    monkeypatch.setattr(pe, "make_read", broken)
    (prices, sources), context = pe.read_with_evidence(settle._price_and_sources, book, list(expected))
    assert prices == expected
    assert calls == [("close", symbol) for symbol in expected]
    assert context == {}
    assert sources == {symbol: "etf_universe" if book == "etf" else "last_price" for symbol in expected}


@pytest.fixture
def isolated_evidence_books(price_paths, monkeypatch):
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", price_paths)
    return price_paths


def _seed_evidence_book(book, *, queued=True, weight=0.20):
    import importlib
    from portfolio import paper_account

    ticker, benchmark, _, native, module_name = EVIDENCE_BOOKS[book]
    prices = {ticker: native, benchmark: native * 5}
    target = {ticker: weight}
    paper_account._save_account({
        "inception_date": "2026-08-01", "starting_nav": 1_000_000.0,
        "cash": 1_000_000.0, "positions": {},
        "spy_shares": None, "spy_inception_price": None,
    }, book)
    submission = {
        "schema": "mastermind.target_book.v2",
        "holdings": [{
            "ticker": ticker, "weight": weight, "action": "add",
            "action_effective": "add", "rationale": "original context-bound thesis",
        }],
        "summary": "original selected price context",
    }
    if queued:
        importlib.import_module(module_name)._append_decision_log(
            "2026-08-12", submission, [], [], {},
            target_status="queued", effective_target=target,
        )
        paper_account.save_pending_target(
            target, "2026-08-12", portfolio_id=book, decision_snapshot=submission,
        )
    return target, prices, submission


def _selected_numeric_bytes(book):
    from portfolio import paper_account

    return {
        kind: path.read_bytes() if path.exists() else None
        for kind, path in paper_account._paths(book).items()
        if kind in ("account", "fills", "nav")
    }


def _captured_context(book, prices):
    from portfolio import price_evidence as pe

    currency = EVIDENCE_BOOKS[book][2]
    return {
        ticker: pe.make_read(
            ticker, value, currency, "captured_input", stage="settlement_input",
            source_bar_label="2026-08-12", source_bar_label_kind="snapshot_asof",
        )
        for ticker, value in prices.items()
    }


@pytest.mark.parametrize("book", EVIDENCE_BOOKS)
@pytest.mark.parametrize("weight", [0.20, 1e-9], ids=["filled", "zero_fill"])
def test_real_queued_finalization_retry_reuses_original_context_without_quotes(
    isolated_evidence_books, monkeypatch, book, weight
):
    from bot import settle
    from portfolio import paper_account, registry

    _seed_evidence_book(book, weight=weight)
    expected_prices, calls = _source_path(monkeypatch, book)
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(settle, "_republish", lambda *a, **k: {"ok": True})
    real_ack = paper_account.acknowledge_settlement_receipt
    retained = []

    def failed_ack(transaction_id, portfolio_id=None):
        path = paper_account._settlement_receipt_path(transaction_id, portfolio_id)
        retained.append(path.read_bytes())
        raise OSError("synthetic acknowledgement fault")

    with monkeypatch.context() as patch:
        patch.setattr(paper_account, "acknowledge_settlement_receipt", failed_ack)
        first = settle.settle_open(book, "2026-08-13")

    assert first["skipped"] == "settlement_receipt_ack_pending"
    assert len(calls) == len(expected_prices)
    receipt, = paper_account.pending_settlement_receipts(book)
    context = receipt["transaction_identity"]["followup"]["settlement_price_evidence"]
    assert {t: q["price"] for t, q in context["quotes"].items()} == expected_prices
    assert all(q["binding_status"] == "matched" for q in context["quotes"].values())
    assert all(q["observation"]["source"] == "last_price" for q in context["quotes"].values())
    before = _selected_numeric_bytes(book)
    journal = registry.data_dir(book) / "decisions.jsonl"
    decisions_before = journal.read_bytes()
    original_fills = paper_account.validated_settlement_receipt_fills(receipt)
    assert len(original_fills) == (1 if weight == 0.20 else 0)

    def forbidden(*args, **kwargs):
        raise AssertionError("recovery must not fetch new prices")

    def checked_ack(transaction_id, portfolio_id=None):
        path = paper_account._settlement_receipt_path(transaction_id, portfolio_id)
        assert path.read_bytes() == retained[0]
        return real_ack(transaction_id, portfolio_id)

    monkeypatch.setattr(settle, "_price_and_sources", forbidden)
    monkeypatch.setattr(settle, "_open_price_usd", forbidden)
    monkeypatch.setattr(paper_account, "_current_price", forbidden)
    monkeypatch.setattr(paper_account, "acknowledge_settlement_receipt", checked_ack)
    retried = settle.settle_open(book, "2026-08-14", _open_price_fn=forbidden)

    assert retried["ok"] is True
    assert retried["transaction_id"] == first["transaction_id"]
    assert retried["executed"] == first["executed"]
    assert _selected_numeric_bytes(book) == before
    assert journal.read_bytes() == decisions_before
    assert len(calls) == len(expected_prices)


@pytest.mark.parametrize("book", EVIDENCE_BOOKS)
def test_direct_settlement_records_existing_marks_without_quote_reconstruction(
    isolated_evidence_books, monkeypatch, book
):
    from bot import settle
    from portfolio import paper_account

    target, prices, submission = _seed_evidence_book(book, queued=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("direct decision marks must not be decorated by a new quote")

    monkeypatch.setattr(settle, "_price_and_sources", forbidden)
    monkeypatch.setattr(paper_account, "_current_price", forbidden)
    result = settle.execute_or_queue(
        book, target, prices, "2026-08-13", market_open=True, decision_snapshot=submission,
    )
    assert not result.get("skipped")
    receipt, = paper_account.pending_settlement_receipts(book)
    context = receipt["transaction_identity"]["followup"]["settlement_price_evidence"]
    assert context["currency"] == EVIDENCE_BOOKS[book][2]
    for ticker, quote in context["quotes"].items():
        assert quote["price"] == prices[ticker]
        assert quote["source"] == "decision_mark"
        assert quote["binding_status"] == "matched"
        assert quote["observation"]["upstream"] is None
        assert quote["observation"]["upstream_reason"] == "not_captured"
        assert quote["observation"]["source_bar_label"] is None


@pytest.mark.parametrize("book", EVIDENCE_BOOKS)
@pytest.mark.parametrize("stage", ["before_account_replace", "after_account_replace"])
def test_real_wal_recovery_keeps_exact_context_and_future_identity(
    isolated_evidence_books, monkeypatch, book, stage
):
    from portfolio import paper_account

    _, prices, _ = _seed_evidence_book(book)
    contexts = _captured_context(book, prices)
    sources = {ticker: "captured_input" for ticker in prices}
    real_save = paper_account._save_account

    def fail_save(state, portfolio_id=None):
        if stage == "after_account_replace":
            real_save(state, portfolio_id)
        raise OSError(stage)

    with monkeypatch.context() as patch:
        patch.setattr(paper_account, "_save_account", fail_save)
        with pytest.raises(OSError, match=stage):
            paper_account.settle_target(
                prices, "2026-08-13", portfolio_id=book,
                _price_sources=sources, _evidence=contexts,
            )
    wal = json.loads(paper_account._transaction_path(book).read_bytes())
    captured = copy.deepcopy(wal["followup"]["settlement_price_evidence"])
    for value in contexts.values():
        value["price"] = 9999.0
        value["source_bar_label"] = "2026-08-14"

    def forbidden(*args, **kwargs):
        raise AssertionError("committed context must not be rebuilt during recovery")

    monkeypatch.setattr(paper_account, "_current_price", forbidden)
    from portfolio import price_evidence as pe
    monkeypatch.setattr(pe, "settlement_snapshot", forbidden)
    recovered = paper_account.recover_paper_transaction(book)
    receipt, = paper_account.pending_settlement_receipts(book)

    assert recovered["transaction_id"] == wal["transaction_id"] == receipt["transaction_id"]
    assert receipt["transaction_identity"]["followup"]["settlement_price_evidence"] == captured
    rows = paper_account.validated_settlement_receipt_fills(receipt)
    assert len(rows) == 1
    before = _selected_numeric_bytes(book)
    assert paper_account.recover_paper_transaction(book) is None
    assert _selected_numeric_bytes(book) == before


@pytest.mark.parametrize("book", EVIDENCE_BOOKS)
def test_snapshot_failure_is_recorded_without_vetoing_numeric_settlement(
    isolated_evidence_books, monkeypatch, book
):
    from portfolio import paper_account, price_evidence as pe

    _, prices, _ = _seed_evidence_book(book)

    def broken(*args, **kwargs):
        raise RuntimeError("synthetic capture fault")

    monkeypatch.setattr(pe, "settlement_snapshot", broken)
    paper_account.settle_target(
        prices, "2026-08-13", portfolio_id=book, _evidence={},
        _price_sources={ticker: "captured_input" for ticker in prices},
    )
    receipt, = paper_account.pending_settlement_receipts(book)
    context = receipt["transaction_identity"]["followup"]["settlement_price_evidence"]
    assert context["capture_error"] == "snapshot_failed"
    assert context["quotes"] == {}
    assert context["omitted_quote_count"] == len(prices)
    assert len(paper_account.validated_settlement_receipt_fills(receipt)) == 1


@pytest.mark.parametrize("book", EVIDENCE_BOOKS)
@pytest.mark.parametrize("weight", [0.20, 1e-9], ids=["filled", "zero_fill"])
def test_changing_only_captured_context_changes_future_identity_not_numeric_effect(
    isolated_evidence_books, monkeypatch, book, weight
):
    from datetime import datetime, timezone
    from portfolio import paper_account, registry

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 8, 13, 14, 0, 0, tzinfo=timezone.utc)
            return value.astimezone(tz) if tz is not None else value.replace(tzinfo=None)

    monkeypatch.setattr(paper_account, "datetime", FrozenDatetime)
    receipts = []
    for index, label in enumerate(["2026-08-11", "2026-08-12"]):
        monkeypatch.setattr(registry, "_ROOT", isolated_evidence_books / str(index))
        target, prices, _ = _seed_evidence_book(book, queued=False, weight=weight)
        paper_account.save_pending_target(target, "2026-08-12", portfolio_id=book)
        contexts = _captured_context(book, prices)
        for context in contexts.values():
            context["source_bar_label"] = label
        paper_account.settle_target(
            prices, "2026-08-13", portfolio_id=book,
            _price_sources={ticker: "captured_input" for ticker in prices}, _evidence=contexts,
        )
        receipt, = paper_account.pending_settlement_receipts(book)
        paper_account.validated_settlement_receipt_fills(receipt)
        receipts.append(receipt)

    first, second = receipts
    assert first["transaction_id"] != second["transaction_id"]
    identities = [copy.deepcopy(r["transaction_identity"]) for r in receipts]
    context_a = identities[0]["followup"].pop("settlement_price_evidence")
    context_b = identities[1]["followup"].pop("settlement_price_evidence")
    assert context_a != context_b
    assert identities[0] == identities[1]
    if weight == 0.20:
        assert [row["fill_id"] for row in first["fills"]] != [
            row["fill_id"] for row in second["fills"]
        ]
    else:
        assert first["fills"] == second["fills"] == []


def test_quote_capture_limit_preserves_explicit_omission_count():
    from portfolio import price_evidence as pe

    prices = {f"T{index:03d}": 100.0 for index in range(pe.MAX_QUOTES + 1)}
    snapshot = pe.settlement_snapshot(
        prices, {ticker: "decision_mark" for ticker in prices}, "USD", {},
    )
    assert len(snapshot["quotes"]) == pe.MAX_QUOTES
    assert snapshot["omitted_quote_count"] == 1
    assert list(snapshot["quotes"]) == sorted(prices)[:pe.MAX_QUOTES]
    assert len(prices) == pe.MAX_QUOTES + 1
    assert all(q["binding_status"] == "unavailable" for q in snapshot["quotes"].values())


@pytest.mark.parametrize("ticker,native,currency", BOOKS)
@pytest.mark.parametrize("entry", ["_live_price", "_current_price"])
def test_missing_price_retains_a_normal_missing_observation_not_a_capture_error(
    price_paths, ticker, native, currency, entry
):
    from portfolio import paper_account, price_evidence as pe

    price, context = pe.read_with_evidence(getattr(paper_account, entry), ticker)
    assert price is None
    assert context["schema"] == pe.READ_SCHEMA
    assert context["read_status"] == "missing"
    assert context["source"] is None
    assert context["upstream"] is None
    assert context["attempts"]
    assert "capture_error" not in context
