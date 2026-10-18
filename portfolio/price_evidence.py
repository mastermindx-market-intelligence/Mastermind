"""Bounded observations for the existing numeric price and settlement owners.

This module does not select prices, qualify execution or change portfolio policy.
A matched observation proves agreement with captured inputs, not provider authenticity
or point-in-time tradability. All execution qualification remains explicitly unchecked.
"""
from __future__ import annotations

import inspect
import json
import math
from datetime import date, datetime
from numbers import Real

READ_SCHEMA = "mastermind.price_read.v1"
SETTLEMENT_SCHEMA = "mastermind.settlement_price_evidence.v1"
YAHOO_SCHEMA = "mastermind.yahoo_daily_bar_evidence.v1"
MAX_CONTEXT_BYTES = 16_384
MAX_QUOTES = 128


def positive_number(value):
    """A finite positive observation value; never coerce arbitrary provider objects."""
    try:
        if isinstance(value, bool) or not isinstance(value, Real):
            return None
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except Exception:
        return None


def _text(value, limit=64):
    return value if isinstance(value, str) and 0 < len(value) <= limit else None


def bar_label(value):
    """Keep an ISO date/bar label without inventing an exchange observation instant."""
    try:
        if isinstance(value, date):
            value = value.isoformat()
        if not _text(value):
            return None
        datetime.fromisoformat(value)
        return value
    except Exception:
        return None


def call_with_evidence(reader, *args, evidence=None, **kwargs):
    """Use a declared optional observation parameter, with exactly one reader call."""
    try:
        parameter = inspect.signature(reader).parameters.get("_evidence")
        if parameter is not None and parameter.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            kwargs = {**kwargs, "_evidence": evidence}
    except Exception:
        pass
    return reader(*args, **kwargs)


def read_with_evidence(reader, *args, **kwargs):
    """Read once and collect context, retaining compatibility with scalar-only readers.

    Signature failure means context is unavailable; no speculative call or retry
    is made. Reader exceptions retain their existing caller-owned fallback behavior.
    """
    observation = {}
    return call_with_evidence(reader, *args, evidence=observation, **kwargs), observation


_READ_FIELDS = frozenset({
    "schema", "ticker", "stage", "source", "price", "currency", "read_status",
    "upstream", "upstream_status", "upstream_reason", "source_bar_label",
    "source_bar_label_kind", "source_text_sha256", "attempts",
    "market_observed_at", "execution_qualification",
})
_CONVERSION_FIELDS = frozenset({"input_price", "input_currency", "fx_observation"})
_YAHOO_FIELDS = frozenset({
    "schema", "ticker", "field", "status", "reason", "price_local",
    "source_bar_label", "source_bar_label_kind", "fetch_started_at",
    "download_returned_at", "fetch_age_seconds", "within_cache_ttl",
    "market_observed_at", "execution_qualification",
})


def _binding_reason(copied, ticker, price, currency):
    if copied.get("ticker") != ticker:
        return "ticker_mismatch"
    expected = positive_number(price)
    field = "price_local" if copied["schema"] == YAHOO_SCHEMA else "price"
    if expected is None or positive_number(copied.get(field)) != expected:
        return "price_mismatch"
    if copied["schema"] == READ_SCHEMA and copied.get("currency") != currency:
        return "currency_mismatch"
    return None


def _snapshot(value, *, depth=0):
    """Copy only bounded v1 fields, rebinding every retained nested observation.

    Validation precedes serialization: bounded fields, one upstream edge and at most
    eight two-field attempts per level prevent arbitrary payload traversal. Hashing
    the resulting data establishes consistency, not source authenticity.
    """
    if type(value) is not dict or not value:
        return None, "not_captured"
    if depth > 6:
        return None, "context_too_deep"
    try:
        schema = value.get("schema")
        if type(schema) is not str or schema not in (READ_SCHEMA, YAHOO_SCHEMA):
            return None, "unsupported_schema"
        required = _READ_FIELDS if schema == READ_SCHEMA else _YAHOO_FIELDS
        allowed = required | (_CONVERSION_FIELDS if schema == READ_SCHEMA else frozenset())
        if len(value) > len(allowed) or any(type(k) is not str or k not in allowed for k in value):
            return None, "unknown_fields"
        if not required.issubset(value):
            return None, "missing_fields"
        if (
            value.get("execution_qualification") != "not_checked"
            or value.get("market_observed_at") is not None
        ):
            return None, "qualification_not_supported"
        copied = {}
        for key, item in value.items():
            if key in ("upstream", "attempts"):
                continue
            if item is None or type(item) is bool:
                copied[key] = item
            elif type(item) is str and len(item) <= 128:
                copied[key] = item
            elif type(item) is int and item.bit_length() <= 64:
                copied[key] = item
            elif type(item) is float and math.isfinite(item):
                copied[key] = item
            else:
                return None, "invalid_or_oversized_field"
        if not _text(copied.get("ticker")):
            return None, "invalid_context"
        price_field = "price" if schema == READ_SCHEMA else "price_local"
        if copied[price_field] is not None and positive_number(copied[price_field]) is None:
            return None, "invalid_context"
        label = copied.get("source_bar_label")
        if label is not None and bar_label(label) != label:
            return None, "invalid_context"
        if schema == YAHOO_SCHEMA:
            if copied["field"] != "Close" or copied["status"] not in ("available", "partial", "unavailable"):
                return None, "invalid_context"
            if copied["source_bar_label_kind"] != "daily_bar_label":
                return None, "invalid_context"
            for key in ("fetch_started_at", "download_returned_at"):
                if copied[key] is not None and bar_label(copied[key]) != copied[key]:
                    return None, "invalid_context"
            age = copied["fetch_age_seconds"]
            if age is not None and (type(age) not in (int, float) or age < 0):
                return None, "invalid_context"
            if copied["within_cache_ttl"] is not None and type(copied["within_cache_ttl"]) is not bool:
                return None, "invalid_context"
        else:
            if copied["read_status"] not in ("returned", "missing", "invalid_value"):
                return None, "invalid_context"
            if (copied["price"] is not None) != (copied["read_status"] == "returned"):
                return None, "invalid_context"
            for key in ("stage", "currency"):
                if not _text(copied[key]):
                    return None, "invalid_context"
            if (copied["source"] is not None or copied["price"] is not None) and not _text(copied["source"]):
                return None, "invalid_context"
            conversion = _CONVERSION_FIELDS.intersection(value)
            if conversion and conversion != _CONVERSION_FIELDS:
                return None, "invalid_conversion"
            if conversion:
                if not _text(copied["input_currency"]):
                    return None, "invalid_conversion"
                if copied["input_price"] is not None and positive_number(copied["input_price"]) is None:
                    return None, "invalid_conversion"
                expected_fx = "not_captured" if copied["input_currency"] != copied["currency"] else "not_required"
                if copied["fx_observation"] != expected_fx:
                    return None, "invalid_conversion"
            attempts = value["attempts"]
            if type(attempts) is not list or len(attempts) > 8:
                return None, "invalid_attempts"
            copied["attempts"] = []
            for attempt in attempts:
                if type(attempt) is not dict or len(attempt) != 2 or set(attempt) != {"source", "outcome"}:
                    return None, "invalid_attempts"
                if not all(_text(attempt[k]) for k in ("source", "outcome")):
                    return None, "invalid_attempts"
                copied["attempts"].append(dict(attempt))
            copied["upstream"] = None
            if value["upstream"] is not None:
                child, reason = _snapshot(value["upstream"], depth=depth + 1)
                if reason or _binding_reason(
                    child, copied["ticker"],
                    copied["input_price"] if conversion else copied["price"],
                    copied["input_currency"] if conversion else copied["currency"],
                ):
                    return None, "invalid_upstream"
                if copied["upstream_status"] != "matched" or copied["upstream_reason"] is not None:
                    return None, "invalid_upstream"
                copied["upstream"] = child
            elif copied["upstream_status"] != "unavailable" or not _text(copied["upstream_reason"]):
                return None, "invalid_upstream"
        encoded = json.dumps(copied, allow_nan=False, ensure_ascii=False, sort_keys=True)
        if len(encoded.encode("utf-8")) > MAX_CONTEXT_BYTES:
            return None, "context_too_large"
        return json.loads(encoded), None
    except Exception:
        return None, "invalid_context"


def bound_context(value, ticker, price, currency):
    """Bind context to the actual selected scalar before retaining source clocks."""
    copied, reason = _snapshot(value)
    if reason:
        return None, reason
    reason = _binding_reason(copied, ticker, price, currency)
    return (None, reason) if reason else (copied, None)


def make_read(
    ticker, price, currency, source, *, stage,
    upstream=None, input_price=None, input_currency=None,
    source_bar_label=None, source_bar_label_kind=None, source_text_sha256=None,
    attempts=(),
):
    """Describe one real read/conversion without making its incomplete clocks authoritative."""
    value = positive_number(price)
    input_value = positive_number(input_price)
    has_input = input_currency is not None
    child, child_reason = bound_context(
        upstream, ticker,
        input_price if has_input else price,
        input_currency if has_input else currency,
    )
    label = bar_label(source_bar_label)
    safe_attempts = []
    for attempt in list(attempts)[:8]:
        if isinstance(attempt, dict):
            name, outcome = _text(attempt.get("source")), _text(attempt.get("outcome"))
            if name and outcome:
                safe_attempts.append({"source": name, "outcome": outcome})
    record = {
        "schema": READ_SCHEMA,
        "ticker": _text(ticker),
        "stage": _text(stage),
        "source": _text(source),
        "price": value,
        "currency": _text(currency),
        "read_status": "returned" if value is not None else (
            "missing" if price is None else "invalid_value"
        ),
        "upstream": child,
        "upstream_status": "matched" if child is not None else "unavailable",
        "upstream_reason": child_reason,
        "source_bar_label": label,
        "source_bar_label_kind": _text(source_bar_label_kind) if label else None,
        "source_text_sha256": _text(source_text_sha256),
        "attempts": safe_attempts,
        "market_observed_at": None,
        "execution_qualification": "not_checked",
    }
    if has_input:
        record.update(
            input_price=input_value,
            input_currency=_text(input_currency),
            fx_observation="not_captured" if input_currency != currency else "not_required",
        )
    return record


def emit(sink, record):
    """Observation failure must never discard or replace a numerical price."""
    if sink is None:
        return
    try:
        copied, reason = _snapshot(record)
        sink.clear()
        if copied is None:
            sink.update({"capture_error": reason})
        else:
            sink.update(copied)
    except Exception:
        pass


def settlement_snapshot(prices, sources, currency, observations):
    """Bind optional per-ticker reads to the already selected settlement price map.

    This snapshot is additional material in the existing transaction identity. New
    captures can therefore change future transaction/fill IDs. Missing legacy input
    remains absent at the caller; this function never reconstructs old observations.
    """
    quotes = {}
    tickers = sorted(prices)
    source_map = sources if isinstance(sources, dict) else {}
    context_map = observations if isinstance(observations, dict) else {}
    for ticker in tickers[:MAX_QUOTES]:
        selected = positive_number(prices[ticker])
        context, reason = bound_context(context_map.get(ticker), ticker, selected, currency)
        source = _text(source_map.get(ticker))
        if context is not None and context.get("source") != source:
            context, reason = None, "source_mismatch"
        quotes[ticker] = {
            "price": selected,
            "source": source,
            "binding_status": "matched" if context is not None else "unavailable",
            "reason": reason,
            "observation": context,
        }
    return {
        "schema": SETTLEMENT_SCHEMA,
        "currency": currency,
        "quotes": quotes,
        "omitted_quote_count": max(0, len(tickers) - MAX_QUOTES),
        "market_observed_at": None,
        "execution_qualification": "not_checked",
    }
