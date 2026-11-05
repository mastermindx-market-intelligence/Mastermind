"""Versioned Open observations pass through the existing bounded capture owner."""
from __future__ import annotations

import copy
import json

import pytest

from portfolio import price_evidence


def open_context(price=200.0):
    return {
        "schema": "mastermind.yahoo_daily_bar_evidence.v2",
        "ticker": "AAPL", "field": "Open", "status": "available", "reason": None,
        "price_local": price, "source_bar_label": "2026-10-13T00:00:00",
        "source_bar_label_kind": "daily_bar_label",
        "fetch_started_at": "2026-10-13T15:00:00+00:00",
        "download_returned_at": "2026-10-13T15:00:03+00:00",
        "fetch_age_seconds": 3.0, "within_cache_ttl": True,
        "cache_refresh_basis": "shared_close_cache",
        "market_observed_at": None, "execution_qualification": "not_checked",
    }


def capture(context):
    read = price_evidence.make_read(
        "AAPL", 200.0, "USD", "yahoo_open", stage="us_open_selection", upstream=context,
    )
    return price_evidence.settlement_snapshot(
        {"AAPL": 200.0}, {"AAPL": "yahoo_open"}, "USD", {"AAPL": read},
    )


def test_versioned_open_context_roundtrips_through_existing_retained_capture():
    source = open_context()
    result = capture(source)
    quote = result["quotes"]["AAPL"]
    assert quote["binding_status"] == "matched"
    assert quote["observation"]["upstream"] == source
    restored = price_evidence.validated_settlement_snapshot(
        {"AAPL": 200.0}, {"AAPL": "yahoo_open"}, "USD", result,
    )
    assert restored == result
    assert restored is not result
    restored["quotes"]["AAPL"]["observation"]["upstream"]["source_bar_label"] = "changed"
    assert result["quotes"]["AAPL"]["observation"]["upstream"] == source
    assert source["source_bar_label"] == "2026-10-13T00:00:00"


@pytest.mark.parametrize("field,value,reason", [
    ("field", "Close", "invalid_context"),
    ("cache_refresh_basis", "independent_open_cache", "invalid_context"),
    ("cache_refresh_basis", True, "invalid_context"),
    ("market_observed_at", "2026-10-13T13:30:00+00:00", "qualification_not_supported"),
    ("execution_qualification", "qualified", "qualification_not_supported"),
    ("fetch_age_seconds", True, "invalid_context"),
    ("fetch_age_seconds", -1.0, "invalid_context"),
    ("within_cache_ttl", "true", "invalid_context"),
    ("source_bar_label_kind", "opening_auction", "invalid_context"),
    ("source_bar_label", "not-a-date", "invalid_context"),
])
def test_open_contract_rejects_relabeling_or_overclaimed_metadata(field, value, reason):
    source = open_context()
    source[field] = value
    assert price_evidence.bound_context(source, "AAPL", 200.0, "USD") == (None, reason)


@pytest.mark.parametrize("mutation", ["missing", "unknown"])
def test_open_contract_keeps_strict_field_bounds(mutation):
    source = open_context()
    if mutation == "missing":
        del source["cache_refresh_basis"]
        reason = "missing_fields"
    else:
        source["raw_provider_response"] = {"unbounded": "not retained"}
        reason = "unknown_fields"
    assert price_evidence.bound_context(source, "AAPL", 200.0, "USD") == (None, reason)


@pytest.mark.parametrize("state,reason", [
    ("partial", "download_return_time_unavailable"),
    ("unavailable", "cache_binding_unavailable"),
])
def test_recorded_open_context_limits_remain_visible(state, reason):
    source = open_context()
    source.update(status=state, reason=reason, download_returned_at=None)
    if state == "unavailable":
        source.update(source_bar_label=None, fetch_started_at=None, fetch_age_seconds=None, within_cache_ttl=None)
    result = capture(source)
    child = result["quotes"]["AAPL"]["observation"]["upstream"]
    assert child["status"] == state and child["reason"] == reason
    assert price_evidence.validated_settlement_snapshot(
        {"AAPL": 200.0}, {"AAPL": "yahoo_open"}, "USD", result,
    ) == result


@pytest.mark.parametrize("field,value,reason", [
    ("ticker", "MSFT", "ticker_mismatch"),
    ("price_local", 201.0, "price_mismatch"),
    ("price_local", True, "invalid_context"),
])
def test_open_metadata_still_binds_the_actual_selected_ticker_and_price(field, value, reason):
    source = open_context()
    source[field] = value
    assert price_evidence.bound_context(source, "AAPL", 200.0, "USD") == (None, reason)


def test_expired_open_clock_remains_separate_from_close_refresh_policy():
    source = open_context()
    source.update(fetch_age_seconds=136.0, within_cache_ttl=False)
    result = capture(source)
    child = result["quotes"]["AAPL"]["observation"]["upstream"]
    assert child["fetch_age_seconds"] == 136.0
    assert child["within_cache_ttl"] is False
    assert child["cache_refresh_basis"] == "shared_close_cache"
    assert child["market_observed_at"] is None
    assert child["execution_qualification"] == "not_checked"


def test_close_v1_remains_close_only_and_does_not_gain_open_fields():
    source = open_context()
    source.update(schema="mastermind.yahoo_daily_bar_evidence.v1", field="Close")
    del source["cache_refresh_basis"]
    before = json.dumps(source, sort_keys=True, ensure_ascii=False)
    copied, reason = price_evidence.bound_context(source, "AAPL", 200.0, "USD")
    assert reason is None
    assert json.dumps(copied, sort_keys=True, ensure_ascii=False) == before
    source["field"] = "Open"
    assert price_evidence.bound_context(source, "AAPL", 200.0, "USD") == (None, "invalid_context")


def test_actual_open_selector_uses_one_declared_observation_read():
    from bot.settle import _open_price_usd
    calls = []
    def yahoo(ticker, *, _evidence=None):
        calls.append((ticker, _evidence is not None))
        _evidence.update(open_context())
        return 200.0
    def forbidden(ticker):
        raise AssertionError("A nonselected fallback was called")
    selected, context = price_evidence.read_with_evidence(
        _open_price_usd, "AAPL", _polygon=lambda _: None, _yahoo=yahoo, _paper=forbidden,
    )
    assert selected == (200.0, "yahoo_open")
    assert context["upstream_status"] == "matched"
    assert context["upstream"] == open_context()
    assert calls == [("AAPL", True)]


def test_unsupported_future_version_stays_unavailable_without_changing_numeric_selection():
    from bot.settle import _open_price_usd
    calls = []
    def yahoo(ticker, *, _evidence=None):
        calls.append(ticker)
        _evidence.update({**open_context(), "schema": "mastermind.yahoo_daily_bar_evidence.v3"})
        return 200.0
    selected, context = price_evidence.read_with_evidence(
        _open_price_usd, "AAPL", _polygon=lambda _: None, _yahoo=yahoo, _paper=lambda _: 202.0,
    )
    assert selected == (200.0, "yahoo_open")
    assert context["upstream_status"] == "unavailable"
    assert context["upstream_reason"] == "unsupported_schema"
    assert calls == ["AAPL"]


def test_capture_rejects_changed_nested_open_after_rebinding():
    result = capture(open_context())
    changed = copy.deepcopy(result)
    changed["quotes"]["AAPL"]["observation"]["upstream"]["price_local"] = 201.0
    with pytest.raises(ValueError, match="settlement_price_capture"):
        price_evidence.validated_settlement_snapshot(
            {"AAPL": 200.0}, {"AAPL": "yahoo_open"}, "USD", changed,
        )
