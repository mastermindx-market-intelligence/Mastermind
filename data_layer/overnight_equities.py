"""Tiingo BOATS venue-native overnight equity quotes for the existing PAPER desk.

Only authenticated, read-only Tiingo REST GETs are performed. BOATS requires its
own account entitlement; a Tiingo Commercial subscription alone does not grant
that feed or redistribution/non-display licensing. Three independent gates:

* MASTERMIND_TIINGO_BOATS_DISPLAY_AUTHORIZED: customer-facing quote display.
* MASTERMIND_TIINGO_BOATS_NONDISPLAY_AUTHORIZED: paper simulation rights.
* MASTERMIND_OVERNIGHT_PAPER_FILLS_ENABLED: operational rollout.

All default OFF. No broker order submission, token in URLs, or upstream error
content in outward-facing API responses.
"""
from __future__ import annotations

import math
import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")
_MAX_QUOTE_AGE = 30.0
_MAX_SPREAD_PCT = 0.05
_URL = "https://api.tiingo.com/boats"


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _token() -> str | None:
    """Use only an existing server-side Tiingo credential."""
    value = (os.environ.get("TIINGO_API_KEY") or os.environ.get("TIINGO_API_TOKEN")
             or os.environ.get("TIINGO_TOKEN") or "").strip()
    return value or None


def _number(value: Any) -> float | None:
    try:
        n = float(value)
        return n if math.isfinite(n) and n > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _read_snapshot(symbol: str, token: str) -> tuple[dict | None, str]:
    """Return only a typed status, never external error text or secrets."""
    # Tiingo normalizes class-share symbols with hyphens (BRK-B), while
    # the existing portfolio may hold their US dot aliases (BRK.B).
    vendor_symbol = symbol.replace(".", "-")
    try:
        response = requests.get(
            f"{_URL}/{vendor_symbol.lower()}",
            headers={"Authorization": f"Token {token}", "Accept": "application/json"},
            timeout=4,
        )
        status = response.status_code
        if status in (401, 402, 403):
            return None, "entitlement_required"
        if status == 404:
            return None, "symbol_not_quoted"
        if status == 429:
            return None, "rate_limited"
        if status != 200:
            return None, "provider_unavailable"
        payload = response.json()
        if isinstance(payload, list):
            if len(payload) != 1 or not isinstance(payload[0], dict):
                return None, "no_overnight_snapshot"
            payload = payload[0]
        if not isinstance(payload, dict):
            return None, "invalid_provider_payload"
        if str(payload.get("ticker") or "").upper() != vendor_symbol:
            return None, "ticker_mismatch"
        return payload, "ok"
    except Exception:
        # Never expose requests exceptions: they may include request headers.
        return None, "provider_unavailable"


def latest(ticker: str, *, now: datetime | None = None,
           include_eligibility: bool = False, purpose: str = "display") -> dict:
    """Fetch a BOATS snapshot for either customer display or internal PAPER simulation.

    purpose='display' requires separate redistribution authorization.
    purpose='execution' requires the approved non-display use and paper rollout.
    A BOATS quote is a venue observation, not a real broker fill guarantee.
    """
    symbol = (ticker or "").upper().strip()
    base = {
        "ticker": symbol, "provider": "tiingo", "venue": "BOATS", "feed": "boats",
        "status": "unavailable", "bid": None, "ask": None, "mid": None,
        "bid_size": None, "ask_size": None, "last": None, "last_size": None,
        "volume": None, "quoted_at": None, "last_trade_at": None,
        "age_seconds": None, "fresh": False, "eligible": None,
        "executable": False, "indicative": False, "paper_only": True,
    }
    if not _SYMBOL.fullmatch(symbol):
        return {**base, "status": "invalid_symbol"}
    if purpose == "display":
        if not _enabled("MASTERMIND_TIINGO_BOATS_DISPLAY_AUTHORIZED"):
            return {**base, "status": "display_license_unverified"}
    elif purpose == "execution":
        if not _enabled("MASTERMIND_TIINGO_BOATS_NONDISPLAY_AUTHORIZED"):
            return {**base, "status": "non_display_license_unverified"}
        # The customer-facing manual paper ledger reveals fill prices/history.
        # Its source quote therefore also needs approved display rights.
        if not _enabled("MASTERMIND_TIINGO_BOATS_DISPLAY_AUTHORIZED"):
            return {**base, "status": "display_license_unverified"}
        if not _enabled("MASTERMIND_OVERNIGHT_PAPER_FILLS_ENABLED"):
            return {**base, "status": "paper_fills_disabled"}
    else:
        return {**base, "status": "invalid_purpose"}
    token = _token()
    if not token:
        return {**base, "status": "not_configured"}
    quote, state = _read_snapshot(symbol, token)
    if quote is None:
        return {**base, "status": state}

    # Only venue quoteTimestamp qualifies a bid/ask for paper execution.
    # Response refresh timestamps and last-sale times can be more recent.
    stamp = _timestamp(quote.get("quoteTimestamp"))
    last_stamp = _timestamp(quote.get("lastSaleTimestamp"))
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    age = (clock - stamp).total_seconds() if stamp else None
    bid, ask = _number(quote.get("bidPrice")), _number(quote.get("askPrice"))
    bid_size, ask_size = _number(quote.get("bidSize")), _number(quote.get("askSize"))
    structure_ok = bool(bid and ask and bid < ask
                        and (ask - bid) / ask <= _MAX_SPREAD_PCT)
    fresh = bool(structure_ok and bid_size and ask_size and age is not None
                 and -5 <= age <= _MAX_QUOTE_AGE)
    # A fresh two-sided quote witnesses a quoted symbol, not broker tradability.
    base.update({
        "bid": bid, "ask": ask,
        "mid": round((bid + ask) / 2, 4) if structure_ok else None,
        "bid_size": bid_size, "ask_size": ask_size,
        "last": _number(quote.get("last")),
        "last_size": _number(quote.get("lastSize")),
        "volume": _number(quote.get("volume")),
        "quoted_at": stamp.isoformat() if stamp else None,
        "last_trade_at": last_stamp.isoformat() if last_stamp else None,
        "age_seconds": round(age, 1) if age is not None else None,
        "fresh": fresh,
        "eligible": bool(fresh) if include_eligibility else None,
        "status": "realtime_boats" if fresh else ("stale" if structure_ok else "invalid_quote"),
        # UI may enable the limit ticket only when *all* release/license
        # switches are armed; POST still re-fetches the venue BBO and rechecks.
        "executable": bool(
            fresh and include_eligibility
            and _enabled("MASTERMIND_TIINGO_BOATS_DISPLAY_AUTHORIZED")
            and _enabled("MASTERMIND_TIINGO_BOATS_NONDISPLAY_AUTHORIZED")
            and _enabled("MASTERMIND_OVERNIGHT_PAPER_FILLS_ENABLED")
        ),
    })
    return base
