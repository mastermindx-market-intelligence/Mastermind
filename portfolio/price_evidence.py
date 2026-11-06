"""Bounded observations for the existing numeric price and settlement owners.

This module does not select prices, qualify execution or change portfolio policy.
A matched observation proves agreement with captured inputs, not provider authenticity
or point-in-time tradability. All execution qualification remains explicitly unchecked.
"""
from __future__ import annotations

import inspect
import json
import math
import re
from datetime import date, datetime
from numbers import Real

from . import fx_evidence

READ_SCHEMA = "mastermind.price_read.v1"
CONVERSION_SCHEMA = "mastermind.price_read.v2"
_READ_SCHEMAS = (READ_SCHEMA, CONVERSION_SCHEMA)
SETTLEMENT_SCHEMA = "mastermind.settlement_price_evidence.v1"
YAHOO_SCHEMA = "mastermind.yahoo_daily_bar_evidence.v1"
YAHOO_OPEN_SCHEMA = "mastermind.yahoo_daily_bar_evidence.v2"
POLYGON_SCHEMA = "mastermind.polygon_snapshot_evidence.v1"
_YAHOO_SCHEMAS = (YAHOO_SCHEMA, YAHOO_OPEN_SCHEMA)
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
_CONVERSION_V2_FIELDS = _CONVERSION_FIELDS | frozenset({"fx_operation", "fx_rate", "fx_binding_reason"})
_YAHOO_FIELDS = frozenset({
    "schema", "ticker", "field", "status", "reason", "price_local",
    "source_bar_label", "source_bar_label_kind", "fetch_started_at",
    "download_returned_at", "fetch_age_seconds", "within_cache_ttl",
    "market_observed_at", "execution_qualification",
})

_YAHOO_OPEN_FIELDS = _YAHOO_FIELDS | frozenset({"cache_refresh_basis"})

_POLYGON_FIELDS = frozenset({
    "schema", "ticker", "field", "price", "currency", "status", "reason",
    "payload_ticker", "payload_ticker_status", "source_updated_raw", "source_updated_unit",
    "source_bar_label", "source_bar_label_kind", "cache_anchor_at", "request_started_at",
    "response_returned_at", "cache_age_observed_at", "cache_age_seconds", "within_cache_ttl",
    "cache_clock_basis", "market_observed_at", "execution_qualification",
})


def _valid_polygon_context(value):
    """Check recorded observation consistency; never qualify the selected Open."""
    if (
        value["field"] != "day.o" or value["currency"] != "USD"
        or value["cache_clock_basis"] != "lookup_before_request"
        or value["source_updated_unit"] != "not_established"
        or value["source_bar_label"] is not None
        or value["source_bar_label_kind"] != "not_provided"
        or value["status"] not in ("available", "partial", "unavailable")
    ):
        return False
    status, reason = value["status"], value["reason"]
    reasons = {
        "available": {None},
        "partial": {
            "local_clock_regressed", "retrieval_clock_unavailable",
            "payload_ticker_mismatch", "payload_ticker_unavailable", "snapshot_updated_unavailable",
        },
        "unavailable": {
            "snapshot_context_unavailable", "no_selected_open",
            "unsupported_selected_value", "snapshot_fields_changed",
        },
    }
    if reason not in reasons[status]:
        return False
    symbol = value["payload_ticker"]
    if symbol is not None and (
        type(symbol) is not str or not re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", symbol)
    ):
        return False
    symbol_status = "unavailable" if symbol is None else (
        "matched" if symbol == value["ticker"] else "mismatch"
    )
    if value["payload_ticker_status"] != symbol_status:
        return False
    updated = value["source_updated_raw"]
    if updated is not None and (
        type(updated) is not str or not re.fullmatch(r"[0-9]{1,20}", updated)
        or not 0 <= int(updated) < 2**64 or str(int(updated)) != updated
    ):
        return False
    clock_keys = ("cache_anchor_at", "request_started_at", "response_returned_at", "cache_age_observed_at")
    clocks = []
    for key in clock_keys:
        item = value[key]
        if item is None:
            clocks.append(None)
        elif type(item) is str:
            stamp = datetime.fromisoformat(item)
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                return False
            clocks.append(stamp.timestamp())
        else:
            return False
    age, within = value["cache_age_seconds"], value["within_cache_ttl"]
    if age is not None and (type(age) not in (int, float) or age < 0):
        return False
    if within is not None and type(within) is not bool:
        return False
    if (age is None) != (within is None):
        return False
    known = [clock for clock in clocks if clock is not None]
    regressed = any(a > b for a, b in zip(known, known[1:]))
    if age is not None and (
        clocks[0] is None or clocks[-1] is None or regressed
        or not math.isclose(age, clocks[-1] - clocks[0], rel_tol=0, abs_tol=0.000001)
    ):
        return False
    if status == "available":
        return (
            symbol_status == "matched" and updated is not None
            and all(clock is not None for clock in clocks) and age is not None
            and positive_number(value["price"]) is not None
        )
    if status == "unavailable":
        return (
            symbol is None and updated is None and all(clock is None for clock in clocks)
            and age is None and (value["price"] is None) == (reason == "no_selected_open")
        )
    if positive_number(value["price"]) is None:
        return False
    return {
        "local_clock_regressed": regressed and age is None,
        "retrieval_clock_unavailable": any(clock is None for clock in clocks),
        "payload_ticker_mismatch": symbol_status == "mismatch",
        "payload_ticker_unavailable": symbol_status == "unavailable",
        "snapshot_updated_unavailable": updated is None,
    }[reason]



def _binding_reason(copied, ticker, price, currency):
    if copied.get("ticker") != ticker:
        return "ticker_mismatch"
    expected = positive_number(price)
    field = "price_local" if copied["schema"] in _YAHOO_SCHEMAS else "price"
    if expected is None or positive_number(copied.get(field)) != expected:
        return "price_mismatch"
    if copied["schema"] in (*_READ_SCHEMAS, POLYGON_SCHEMA) and copied.get("currency") != currency:
        return "currency_mismatch"
    return None


def _snapshot(value, *, depth=0):
    """Copy only bounded supported fields, rebinding every retained nested observation.

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
        if type(schema) is not str or schema not in (*_READ_SCHEMAS, *_YAHOO_SCHEMAS, POLYGON_SCHEMA):
            return None, "unsupported_schema"
        required = (
            _READ_FIELDS | _CONVERSION_V2_FIELDS if schema == CONVERSION_SCHEMA
            else _READ_FIELDS if schema == READ_SCHEMA
            else _POLYGON_FIELDS if schema == POLYGON_SCHEMA
            else _YAHOO_OPEN_FIELDS if schema == YAHOO_OPEN_SCHEMA
            else _YAHOO_FIELDS
        )
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
            if key in ("upstream", "attempts", "fx_rate"):
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
        price_field = "price_local" if schema in _YAHOO_SCHEMAS else "price"
        if copied[price_field] is not None and positive_number(copied[price_field]) is None:
            return None, "invalid_context"
        label = copied.get("source_bar_label")
        if label is not None and bar_label(label) != label:
            return None, "invalid_context"
        if schema in _YAHOO_SCHEMAS:
            expected_field = "Open" if schema == YAHOO_OPEN_SCHEMA else "Close"
            if copied["field"] != expected_field or copied["status"] not in ("available", "partial", "unavailable"):
                return None, "invalid_context"
            if schema == YAHOO_OPEN_SCHEMA and copied["cache_refresh_basis"] != "shared_close_cache":
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
        elif schema == POLYGON_SCHEMA:
            if not _valid_polygon_context(copied):
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
                if schema == READ_SCHEMA:
                    expected_fx = "not_captured" if copied["input_currency"] != copied["currency"] else "not_required"
                    if copied["fx_observation"] != expected_fx:
                        return None, "invalid_conversion"
                else:
                    if copied["fx_operation"] not in ("multiply", "divide"):
                        return None, "invalid_conversion"
                    copied["fx_rate"] = None
                    if value["fx_rate"] is not None:
                        rate, reason = fx_evidence.bound_rate(
                            value["fx_rate"], copied["input_price"], copied["input_currency"],
                            copied["price"], copied["currency"], copied["fx_operation"],
                        )
                        if reason or copied["fx_observation"] != "matched" or copied["fx_binding_reason"] is not None:
                            return None, "invalid_fx_binding"
                        copied["fx_rate"] = rate
                    elif copied["fx_observation"] != "unavailable" or copied["fx_binding_reason"] not in fx_evidence.BINDING_REASONS:
                        return None, "invalid_fx_binding"
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
    attempts=(), fx_context=None, fx_operation=None,
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
        # Empty legacy adapters retain their exact v1 result. New context uses an
        # explicit child/schema; old decoders are not forward-compatible with it.
        if fx_context is not None and (type(fx_context) is not dict or fx_context):
            rate, reason = fx_evidence.bound_rate(
                fx_context, input_price, input_currency, price, currency, fx_operation,
            )
            record.update(
                schema=CONVERSION_SCHEMA, fx_operation=fx_operation, fx_rate=rate,
                fx_observation="matched" if rate is not None else "unavailable",
                fx_binding_reason=reason,
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


def validated_settlement_snapshot(prices, sources, currency, captured):
    """Validate retained v1 context against selected prices without inventing lost data.

    Matched observations are checked by the same bounded constructor as capture.
    Rejected observations were discarded at capture; their bounded recorded reason
    is retained, not independently reproduced or authenticated from that lost input.
    No quote, account, transaction, identifier or policy is created or changed.
    """
    fields = {
        "schema", "currency", "quotes", "omitted_quote_count",
        "market_observed_at", "execution_qualification",
    }
    quote_fields = {"price", "source", "binding_status", "reason", "observation"}
    if (
        type(captured) is not dict or len(captured) != len(fields)
        or any(type(key) is not str or key not in fields for key in captured)
        or captured["schema"] != SETTLEMENT_SCHEMA
        or type(captured["currency"]) is not str
        or captured["currency"] != currency
        or type(captured["quotes"]) is not dict or len(captured["quotes"]) > MAX_QUOTES
        or type(captured["omitted_quote_count"]) is not int or captured["omitted_quote_count"] < 0
        or captured["market_observed_at"] is not None
        or captured["execution_qualification"] != "not_checked"
    ):
        raise ValueError("invalid_settlement_price_capture")
    observations = {}
    for ticker, quote in captured["quotes"].items():
        if (
            type(ticker) is not str or type(quote) is not dict or len(quote) != len(quote_fields)
            or any(type(key) is not str or key not in quote_fields for key in quote)
            or (quote["price"] is not None and positive_number(quote["price"]) is None)
            or type(quote["binding_status"]) is not str
            or quote["binding_status"] not in ("matched", "unavailable")
            or (quote["binding_status"] == "matched"
                and (quote["reason"] is not None or type(quote["observation"]) is not dict))
            or (quote["binding_status"] == "unavailable"
                and (quote["observation"] is not None or _text(quote["reason"]) is None))
        ):
            raise ValueError("invalid_settlement_price_quote")
        observations[ticker] = quote["observation"]
    expected = settlement_snapshot(prices, sources, currency, observations)
    for ticker, quote in captured["quotes"].items():
        reconstructed = expected["quotes"].get(ticker)
        if reconstructed is None or reconstructed["binding_status"] != quote["binding_status"]:
            raise ValueError("settlement_price_capture_binding_mismatch")
        if quote["binding_status"] == "unavailable":
            reconstructed["reason"] = quote["reason"]
    if expected != captured:
        raise ValueError("settlement_price_capture_mismatch")
    return expected
