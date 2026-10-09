"""Alpaca overnight equity quote READ adapter for the self-directed PAPER book.

Only two authenticated GET families are used: stock quotes and asset eligibility.
Never submit a broker order or treat indicative/delayed/EOD data as a paper fill.
BOATS real-time entitlement and paper-fill rollout are explicit operator attestations;
unknown entitlement is non-executable. No secrets or upstream error bodies in output.
"""
from __future__ import annotations

import math
import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")
_MAX_QUOTE_AGE = 30
_MAX_SPREAD_PCT = 0.05


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _credentials() -> dict[str, str] | None:
    key = os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("ALPACA_API_SECRET_KEY") or os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        return None
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}


def _read(url: str, headers: dict[str, str], params: dict | None = None) -> dict | None:
    """Fixed Alpaca domains/paths, no user-controlled URL except validated symbol."""
    try:
        response = requests.get(url, headers=headers, params=params, timeout=4)
        if response.status_code != 200:
            return None
        body = response.json()
        return body if isinstance(body, dict) else None
    except Exception:
        # Never surface exception text: URL/headers may contain provider secrets.
        return None


def _number(value: Any) -> float | None:
    try:
        n = float(value)
        return n if math.isfinite(n) and n > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return t if t.tzinfo is not None else None
    except ValueError:
        return None


def _eligible(asset: dict | None) -> bool:
    if not isinstance(asset, dict) or asset.get("status") != "active":
        return False
    attrs = asset.get("attributes")
    attrs = attrs if isinstance(attrs, list) else []
    overnight = asset.get("overnight_tradable") is True or "overnight_tradable" in attrs
    halted = asset.get("overnight_halted") is True or "overnight_halted" in attrs
    return (
        overnight and not halted
        and asset.get("tradable") is True
        and asset.get("class") == "us_equity"
    )


def latest(ticker: str, *, now: datetime | None = None, include_eligibility: bool = False) -> dict:
    """Return a provenance-rich quote. `executable` means *eligible for paper simulation* only.

    Price data is NEVER a real broker execution promise. In particular the free
    `overnight` feed is indicative; `boats` without explicitly attested
    REAL-TIME access is not used as a paper execution feed.
    """
    symbol = (ticker or "").upper().strip()
    confirmed = _enabled("MASTERMIND_ALPACA_BOATS_REALTIME_CONFIRMED")
    feed = "boats" if confirmed else "overnight"
    base = {
        "ticker": symbol, "provider": "alpaca", "feed": feed,
        "status": "unavailable", "bid": None, "ask": None, "mid": None,
        "bid_size": None, "ask_size": None, "quoted_at": None,
        "age_seconds": None, "fresh": False, "eligible": None,
        "executable": False, "indicative": not confirmed, "paper_only": True,
    }
    if not _SYMBOL.fullmatch(symbol):
        return {**base, "status": "invalid_symbol"}
    auth = _credentials()
    if not auth:
        return {**base, "status": "not_configured"}
    raw = _read(f"https://data.alpaca.markets/v2/stocks/{symbol}/quotes/latest",
                auth, {"feed": feed})
    quote = (raw or {}).get("quote")
    if not isinstance(quote, dict):
        return {**base, "status": "feed_unavailable"}
    bid, ask = _number(quote.get("bp")), _number(quote.get("ap"))
    bid_size, ask_size = _number(quote.get("bs")), _number(quote.get("as"))
    stamp = _timestamp(quote.get("t"))
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    age = (clock - stamp).total_seconds() if stamp else None
    structurally_valid = (bid is not None and ask is not None and bid <= ask
                          and (ask - bid) / ask <= _MAX_SPREAD_PCT)
    fresh = bool(structurally_valid and age is not None and -5 <= age <= _MAX_QUOTE_AGE)
    base.update({
        "bid": bid, "ask": ask,
        "mid": round((bid + ask) / 2, 4) if structurally_valid else None,
        "bid_size": bid_size, "ask_size": ask_size,
        "quoted_at": stamp.isoformat() if stamp else None,
        "age_seconds": round(age, 1) if age is not None else None,
        "fresh": fresh,
        "status": "stale" if structurally_valid else "invalid_quote",
    })
    if not fresh:
        return base
    base["status"] = "indicative" if not confirmed else "realtime_boats"
    if include_eligibility and confirmed:
        asset = _read(f"https://paper-api.alpaca.markets/v2/assets/{symbol}", auth)
        base["eligible"] = _eligible(asset)
        if not base["eligible"]:
            base["status"] = "ineligible_or_halted"
    if include_eligibility and not confirmed:
        base["eligible"] = None
    base["executable"] = bool(
        fresh and confirmed and include_eligibility and base["eligible"] is True
        and _enabled("MASTERMIND_OVERNIGHT_PAPER_FILLS_ENABLED")
        and bid_size is not None and ask_size is not None
    )
    return base
