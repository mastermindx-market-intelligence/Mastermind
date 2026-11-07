"""Bounded provenance for the FX rate actually consumed by existing scalar owners.

Agreement with a captured conversion is not evidence of market-time eligibility,
pair orientation, proxy suitability or provider authenticity. No price is selected here.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timezone
from numbers import Real

SCHEMA = "mastermind.fx_rate_evidence.v1"
MAX_BYTES = 4096
BINDING_REASONS = frozenset({
    "not_captured", "invalid_fx_fields", "invalid_fx_field", "invalid_fx_context",
    "invalid_fx_source_binding", "invalid_fx_status", "fx_context_too_large",
    "invalid_conversion_value", "fx_operation_or_currency_mismatch", "fx_arithmetic_mismatch",
})
_FIELDS = frozenset({
    "schema", "currency", "rate", "consumed_as", "source", "symbol", "source_path",
    "source_bar_label", "source_bar_label_kind", "source_text_sha256",
    "source_text_digest_basis", "source_read_started_at", "source_read_returned_at",
    "cache_population_day", "cache_day_basis", "cache_state", "cache_observed_at",
    "status", "reason", "source_convention_qualification", "market_observed_at",
    "execution_qualification",
})
_SOURCES = {"yahoo_store", "forex_snapshot", "static_fallback", "identity",
            "unknown_currency_fallback", "unavailable"}
_MISSING = {"source_context_unavailable", "cache_context_unavailable",
            "source_value_mismatch", "source_context_invalid"}
_PATHS = {"data/forex/latest.json", "site/forexdata/latest.json"}
_SYMBOL_CURRENCY = {"CNH=X": "CNY", "CNY=X": "CNY", "HKD=X": "HKD",
                    "USDCNH": "CNY", "USDHKD": "HKD", "HKDUSD": "HKD"}


def positive(value):
    try:
        if isinstance(value, bool) or not isinstance(value, Real):
            return None
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except Exception:
        return None


def clock():
    """A local observation clock, never a market timestamp."""
    try:
        return datetime.now(timezone.utc).isoformat()
    except Exception:
        return None


def label(value):
    try:
        if isinstance(value, date):
            value = value.isoformat()
        if type(value) is not str or not 0 < len(value) <= 64:
            return None
        datetime.fromisoformat(value)
        return value
    except Exception:
        return None


def _instant(value):
    if value is None:
        return None
    if type(value) is not str or not 0 < len(value) <= 64:
        raise ValueError("invalid_clock")
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("naive_clock")
    return stamp.timestamp()


def _state(value):
    if value["source"] == "unavailable":
        reason = value["reason"]
        if reason not in _MISSING:
            raise ValueError("unknown_unavailable_reason")
        return "unavailable", reason
    if value["cache_state"] != "not_used" and value["cache_population_day"] is None:
        return "partial", "cache_day_unavailable"
    observed = _instant(value["cache_observed_at"])
    if observed is None:
        return "partial", "observation_clock_unavailable"
    if value["source"] in ("yahoo_store", "forex_snapshot"):
        start = _instant(value["source_read_started_at"])
        returned = _instant(value["source_read_returned_at"])
        if start is None or returned is None:
            return "partial", "source_read_clock_unavailable"
        if start > returned or returned > observed:
            return "partial", "local_clock_regressed"
        if value["source_bar_label"] is None:
            return "partial", "source_label_unavailable"
        if value["source"] == "forex_snapshot" and value["source_text_sha256"] is None:
            return "partial", "source_text_unavailable"
    return "available", None


def snapshot(value):
    """Validate a flat closed child before serialization or downstream binding."""
    if type(value) is not dict or not value:
        return None, "not_captured"
    try:
        if len(value) != len(_FIELDS) or any(type(k) is not str or k not in _FIELDS for k in value):
            return None, "invalid_fx_fields"
        copied = {}
        for key, item in value.items():
            if item is None or type(item) is bool:
                copied[key] = item
            elif type(item) is str and len(item) <= 128:
                copied[key] = item
            elif type(item) is int and item.bit_length() <= 64:
                copied[key] = item
            elif type(item) is float and math.isfinite(item):
                copied[key] = item
            else:
                return None, "invalid_fx_field"
        if (copied["schema"] != SCHEMA or positive(copied["rate"]) is None
                or type(copied["currency"]) is not str or not 0 < len(copied["currency"]) <= 16
                or copied["consumed_as"] != "foreign_units_per_USD"
                or copied["source_convention_qualification"] != "not_established"
                or copied["market_observed_at"] is not None
                or copied["execution_qualification"] != "not_checked"
                or copied["cache_day_basis"] != "process_local_date"
                or copied["cache_state"] not in ("population", "hit", "not_used")
                or copied["source"] not in _SOURCES):
            return None, "invalid_fx_context"
        for key in ("source_read_started_at", "source_read_returned_at", "cache_observed_at"):
            _instant(copied[key])
        day = copied["cache_population_day"]
        if day is not None and (type(day) is not str or date.fromisoformat(day).isoformat() != day):
            return None, "invalid_fx_context"
        bar = copied["source_bar_label"]
        if bar is not None and label(bar) != bar:
            return None, "invalid_fx_context"
        kind = copied["source_bar_label_kind"]
        if (bar is None) != (kind == "not_provided"):
            return None, "invalid_fx_context"
        source, symbol, path = copied["source"], copied["symbol"], copied["source_path"]
        if source in ("yahoo_store", "forex_snapshot"):
            if _SYMBOL_CURRENCY.get(symbol) != copied["currency"]:
                return None, "invalid_fx_source_binding"
            if source == "yahoo_store":
                if symbol not in ("CNH=X", "CNY=X", "HKD=X") or path is not None:
                    return None, "invalid_fx_source_binding"
                if kind not in ("selected_close_index", "not_provided"):
                    return None, "invalid_fx_context"
            elif path not in _PATHS or symbol not in ("USDCNH", "USDHKD", "HKDUSD"):
                return None, "invalid_fx_source_binding"
            elif kind not in ("pair_asof", "snapshot_asof", "not_provided"):
                return None, "invalid_fx_context"
        elif symbol is not None or path is not None or bar is not None:
            return None, "invalid_fx_source_binding"
        if source == "identity" and (copied["currency"] != "USD" or copied["rate"] != 1.0):
            return None, "invalid_fx_source_binding"
        if source == "static_fallback" and copied["currency"] not in ("CNY", "HKD"):
            return None, "invalid_fx_source_binding"
        if source == "unknown_currency_fallback" and copied["currency"] in ("CNY", "HKD", "USD"):
            return None, "invalid_fx_source_binding"
        digest = copied["source_text_sha256"]
        basis = copied["source_text_digest_basis"]
        if digest is not None and (source != "forex_snapshot" or type(digest) is not str
                or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
                or basis != "decoded_text_utf8"):
            return None, "invalid_fx_context"
        if digest is None and basis is not None:
            return None, "invalid_fx_context"
        if source not in ("yahoo_store", "forex_snapshot") and (
                copied["source_read_started_at"] is not None or copied["source_read_returned_at"] is not None):
            return None, "invalid_fx_context"
        if (copied["status"], copied["reason"]) != _state(copied):
            return None, "invalid_fx_status"
        encoded = json.dumps(copied, allow_nan=False, sort_keys=True, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > MAX_BYTES:
            return None, "fx_context_too_large"
        return json.loads(encoded), None
    except Exception:
        return None, "invalid_fx_context"


def source_context(sink, *, source, symbol, rate, started, returned,
                   bar=None, kind="not_provided", path=None, source_text=None):
    """Capture from the same selected series/text, with no source read of its own."""
    if sink is None:
        return
    try:
        bar = label(bar)
        digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest() if type(source_text) is str else None
        sink.clear()
        sink.update({
            "source": source, "symbol": symbol, "rate": positive(rate), "source_path": path,
            "source_bar_label": bar, "source_bar_label_kind": kind if bar is not None else "not_provided",
            "source_text_sha256": digest, "source_text_digest_basis": "decoded_text_utf8" if digest else None,
            "source_read_started_at": started, "source_read_returned_at": returned,
        })
    except Exception:
        pass


def make_rate(currency, rate, *, source=None, cache_day=None, cache_state="population",
              missing_reason="source_context_unavailable"):
    """Build an observation only; missing metadata cannot request a refreshed rate."""
    try:
        fields = ("source", "symbol", "source_path", "source_bar_label", "source_bar_label_kind",
                  "source_text_sha256", "source_text_digest_basis", "source_read_started_at", "source_read_returned_at")
        observed_rate = positive(source.get("rate")) if type(source) is dict else None
        known = observed_rate is not None and observed_rate == positive(rate)
        if known:
            metadata = {key: source.get(key) for key in fields}
        else:
            metadata = dict.fromkeys(fields)
            metadata.update(source="unavailable", source_bar_label_kind="not_provided")
            if type(source) is dict and source.get("rate") is not None:
                missing_reason = "source_value_mismatch"
        value = dict(metadata, schema=SCHEMA, currency=currency, rate=positive(rate),
                     consumed_as="foreign_units_per_USD", cache_population_day=cache_day or None,
                     cache_day_basis="process_local_date", cache_state=cache_state,
                     cache_observed_at=clock(), status="unavailable", reason=missing_reason,
                     source_convention_qualification="not_established", market_observed_at=None,
                     execution_qualification="not_checked")
        value["status"], value["reason"] = _state(value)
        copied, reason = snapshot(value)
        if copied is not None:
            return copied
        if known:
            return make_rate(currency, rate, cache_day=cache_day, cache_state=cache_state,
                             missing_reason="source_context_invalid")
        return None
    except Exception:
        return None


def cached_rate(value, currency, rate, day):
    """Reuse only validated original metadata; do not revisit its source."""
    copied, reason = snapshot(value)
    if reason or copied["currency"] != currency or copied["rate"] != positive(rate) or copied["cache_population_day"] != (day or None):
        return make_rate(currency, rate, cache_day=day, cache_state="hit",
                         missing_reason="cache_context_unavailable")
    copied.update(cache_state="hit", cache_observed_at=clock())
    try:
        copied["status"], copied["reason"] = _state(copied)
        return snapshot(copied)[0]
    except Exception:
        return None


def emit(sink, value):
    if sink is None:
        return
    try:
        copied, reason = snapshot(value)
        sink.clear()
        sink.update(copied if copied is not None else {"capture_error": reason})
    except Exception:
        pass


def bound_rate(value, input_price, input_currency, output_price, output_currency, operation):
    """Bind the observed rate to the actual single multiplication or division."""
    copied, reason = snapshot(value)
    if reason:
        return None, reason
    before, after = positive(input_price), positive(output_price)
    if before is None or after is None:
        return None, "invalid_conversion_value"
    if operation == "divide" and output_currency == "USD" and copied["currency"] == input_currency:
        expected = before / copied["rate"]
    elif operation == "multiply" and input_currency == "USD" and copied["currency"] == output_currency:
        expected = before * copied["rate"]
    else:
        return None, "fx_operation_or_currency_mismatch"
    if expected != after:
        return None, "fx_arithmetic_mismatch"
    return copied, None
