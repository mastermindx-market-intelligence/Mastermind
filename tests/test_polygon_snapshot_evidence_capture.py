"""Polygon source observations use the existing bounded receipt context owner."""
from __future__ import annotations

import copy
import json

import pytest

from portfolio import price_evidence
from test_polygon_open_price_evidence import source, read  # noqa: F401


def selected_context(source):
    value, context = read()
    assert value == 199.0
    return context


def capture(context):
    selected = price_evidence.make_read(
        "AAPL", 199.0, "USD", "polygon_open", stage="us_open_selection", upstream=context,
    )
    return price_evidence.settlement_snapshot(
        {"AAPL": 199.0}, {"AAPL": "polygon_open"}, "USD", {"AAPL": selected},
    )


def test_actual_polygon_source_roundtrips_through_existing_receipt_decoder(source):
    context = selected_context(source)
    captured = capture(context)
    assert captured["quotes"]["AAPL"]["observation"]["upstream"] == context
    restored = price_evidence.validated_settlement_snapshot(
        {"AAPL": 199.0}, {"AAPL": "polygon_open"}, "USD", captured,
    )
    assert restored == captured and restored is not captured
    assert '"1791896400123456789"' in json.dumps(restored)
    restored["quotes"]["AAPL"]["observation"]["upstream"]["source_updated_raw"] = "1"
    assert captured["quotes"]["AAPL"]["observation"]["upstream"]["source_updated_raw"] == "1791896400123456789"


@pytest.mark.parametrize("field,value,reason", [
    ("field", "day.c", "invalid_context"),
    ("cache_clock_basis", "response_return", "invalid_context"),
    ("source_updated_unit", "nanoseconds", "invalid_context"),
    ("source_updated_raw", 1791896400123456789, "invalid_context"),
    ("source_updated_raw", "01", "invalid_context"),
    ("source_updated_raw", str(2**64), "invalid_context"),
    ("source_bar_label", "2026-10-13", "invalid_context"),
    ("source_bar_label_kind", "opening_auction", "invalid_context"),
    ("request_started_at", "2026-10-13", "invalid_context"),
    ("response_returned_at", "2026-10-13T13:00:00", "invalid_context"),
    ("cache_age_seconds", True, "invalid_context"),
    ("cache_age_seconds", -1.0, "invalid_context"),
    ("cache_age_seconds", 99.0, "invalid_context"),
    ("within_cache_ttl", "true", "invalid_context"),
    ("payload_ticker_status", "qualified", "invalid_context"),
    ("payload_ticker_status", "mismatch", "invalid_context"),
    ("payload_ticker", "MSFT", "invalid_context"),
    ("status", "fresh", "invalid_context"),
    ("reason", "guessed_failure_cause", "invalid_context"),
    ("currency", "HKD", "invalid_context"),
    ("price", True, "invalid_context"),
    ("market_observed_at", "2026-10-13T13:30:00+00:00", "qualification_not_supported"),
    ("execution_qualification", "qualified", "qualification_not_supported"),
])
def test_snapshot_contract_rejects_relabeling_coercion_or_overclaims(source, field, value, reason):
    context = selected_context(source)
    context[field] = value
    assert price_evidence.bound_context(context, "AAPL", 199.0, "USD") == (None, reason)


@pytest.mark.parametrize("change,reason", [("extra", "unknown_fields"), ("missing", "missing_fields")])
def test_snapshot_contract_remains_closed_and_bounded(source, change, reason):
    context = selected_context(source)
    if change == "extra":
        context["raw_response"] = {"unbounded": "not retained"}
    else:
        del context["cache_anchor_at"]
    assert price_evidence.bound_context(context, "AAPL", 199.0, "USD") == (None, reason)


def test_recorded_payload_mismatch_remains_visible_but_does_not_veto_numeric_selection(source):
    source["payload"]["ticker"] = "MSFT"
    context = selected_context(source)
    captured = capture(context)
    child = captured["quotes"]["AAPL"]["observation"]["upstream"]
    assert child["status"] == "partial" and child["payload_ticker"] == "MSFT"
    assert child["payload_ticker_status"] == "mismatch"
    assert price_evidence.validated_settlement_snapshot(
        {"AAPL": 199.0}, {"AAPL": "polygon_open"}, "USD", captured,
    ) == captured


def test_shared_snapshot_mutation_retains_unavailable_context_with_the_real_selected_price(source):
    from data_layer import polygon
    polygon._snapshot("AAPL")
    polygon._snapshot_cache["AAPL"][1]["updated"] += 1
    context = selected_context(source)
    captured = capture(context)
    child = captured["quotes"]["AAPL"]["observation"]["upstream"]
    assert child["status"] == "unavailable"
    assert child["reason"] == "snapshot_fields_changed"
    assert captured["quotes"]["AAPL"]["price"] == 199.0


def test_actual_selector_uses_polygon_once_without_fetching_a_fallback(source):
    from bot.settle import _open_price_usd
    def forbidden(ticker):
        raise AssertionError("unselected fallback must not run")
    selected, context = price_evidence.read_with_evidence(
        _open_price_usd, "AAPL", _yahoo=forbidden, _paper=forbidden,
    )
    assert selected == (199.0, "polygon_open")
    assert context["upstream_status"] == "matched"
    assert context["upstream"]["schema"] == "mastermind.polygon_snapshot_evidence.v1"
    assert len(source["calls"]) == 1


def test_tampered_retained_polygon_child_is_rejected_after_rebinding(source):
    captured = capture(selected_context(source))
    changed = copy.deepcopy(captured)
    changed["quotes"]["AAPL"]["observation"]["upstream"]["price"] = 200.0
    with pytest.raises(ValueError, match="settlement_price_capture"):
        price_evidence.validated_settlement_snapshot(
            {"AAPL": 199.0}, {"AAPL": "polygon_open"}, "USD", changed,
        )


def test_future_schema_remains_unavailable_without_changing_selected_price(source):
    context = selected_context(source)
    context["schema"] = "mastermind.polygon_snapshot_evidence.v2"
    captured = capture(context)
    row = captured["quotes"]["AAPL"]
    assert row["price"] == 199.0
    assert row["observation"]["upstream_status"] == "unavailable"
    assert row["observation"]["upstream_reason"] == "unsupported_schema"
