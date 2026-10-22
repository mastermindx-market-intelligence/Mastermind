"""Live (15-min delayed) equity quotes — for the Brain and the dashboard.

Thin wrapper over the vendored macro Polygon client
(`collectors.polygon_options.PolygonOptions`), which hits api.polygon.io (or a
Polygon-compatible clone) for the stock snapshot. The key resolves from
POLYGON_API_KEY, falling back to MASSIVE_API_KEY (the macro repo's existing
Polygon-compatible secret). Degrades to None per-symbol when offline / unkeyed —
never raises.

Quotes are cached in-process for `_TTL` seconds so one page load (Positions +
Trade History both want the held names) doesn't re-hit the API per panel.

Delayed data is fine here: this is a paper book, marks are EOD-grade.

SECRET-HANDLING CONSTRAINT — read before adding logging to this module.
Every request below passes the key as an ``apiKey`` QUERY PARAMETER, and
``requests`` embeds the full request URL in its exception messages.  A
``requests`` exception raised anywhere in this file therefore carries
POLYGON_API_KEY / MASSIVE_API_KEY in plaintext.  That is safe today only because
every ``except Exception`` block here swallows the exception without logging it
— the degradation contract ("never raises", returns None per symbol) is also
what keeps the key out of the logs.

If you add logging, the exception text is externally-produced text reaching a
log and MUST go through it first::

    from common.redaction import sanitize_external_text
    log.warning("polygon %s failed: %s", ticker, sanitize_external_text(exc))

Both key names are auto-collected by ``common.redaction.environment_secrets``,
so the sanitizer removes them by identity, not merely by shape.  Pinned by
``tests/test_secret_redaction.py::test_requests_style_url_exception_is_redacted``.
The structural fix — moving the key to an ``Authorization: Bearer`` header so it
never enters a URL — is a live-API change and is deliberately not made here.
"""
from __future__ import annotations

import time
from typing import Iterable, Optional

import bot  # noqa: F401  -> puts vendor/macro on sys.path

_TTL = 60.0  # seconds; a minute of staleness on a delayed feed is immaterial
_cache: dict[str, tuple[float, Optional[float]]] = {}
_client = None
_client_tried = False


def _get_client():
    """Lazy singleton macro Polygon client, or None if unavailable/unkeyed."""
    global _client, _client_tried
    if _client_tried:
        return _client
    _client_tried = True
    try:
        from collectors.polygon_options import PolygonOptions
        c = PolygonOptions()
        _client = c if c.enabled() else None
    except Exception:
        _client = None
    return _client


def available() -> bool:
    """True if a keyed Polygon client is reachable."""
    return _get_client() is not None


def daily_closes(ticker: str, start: str, end: str, cache: bool = True) -> dict:
    """Adjusted daily closes for [start, end] (ISO dates) as {YYYY-MM-DD: close}. Best-effort
    (returns {} on any failure). Non-positive closes (data errors / halted-trading artifacts) are
    dropped so they can't fabricate a stop barrier or a -100% return. `cache=True` reads/writes a
    disk cache under data/cache/aggs — ONLY safe for immutable, fully-elapsed windows; callers pass
    cache=False for still-live windows so a partial snapshot is never frozen."""
    import json
    import os
    from datetime import datetime, timezone
    from pathlib import Path

    t = (ticker or "").upper().strip()
    if not t or not start or not end:
        return {}
    cdir = Path(__file__).resolve().parent.parent / "data" / "cache" / "aggs"
    cf = cdir / f"{t}_{start}_{end}.json"
    if cache:
        try:
            if cf.exists():
                return json.loads(cf.read_text())
        except Exception:  # noqa: BLE001
            pass
    out: dict = {}
    try:
        import requests
        key = (os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY") or "").strip()
        if key:
            url = f"https://api.polygon.io/v2/aggs/ticker/{t}/range/1/day/{start}/{end}"
            r = requests.get(url, params={"adjusted": "true", "sort": "asc", "limit": 50000,
                                          "apiKey": key}, timeout=12)
            if r.ok:
                for row in (r.json() or {}).get("results") or []:
                    ts, c = row.get("t"), row.get("c")
                    if ts is None or c is None:
                        continue
                    try:
                        cv = float(c)
                    except (TypeError, ValueError):
                        continue
                    if cv <= 0:                 # drop zero/negative closes (data artifacts)
                        continue
                    d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                    out[d] = cv
    except Exception:  # noqa: BLE001 — labeling degrades to 'unresolved' on failure, never fatal
        out = {}
    if out and cache:
        try:
            cdir.mkdir(parents=True, exist_ok=True)
            cf.write_text(json.dumps(out))
        except Exception:  # noqa: BLE001
            pass
    return out


_details_cache: dict = {}


def ticker_details(ticker: str) -> Optional[dict]:
    """Best-effort company reference (name, description, market_cap, sector) from Polygon's
    /v3/reference/tickers/{ticker}. Returns None on ANY failure (unkeyed, paywalled, network,
    timeout) — callers must degrade gracefully. Cached for the process (incl. None results)."""
    import os
    t = (ticker or "").upper().strip()
    if not t:
        return None
    if t in _details_cache:
        return _details_cache[t]
    out = None
    try:
        import requests
        key = (os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY") or "").strip()
        if key:
            r = requests.get(f"https://api.polygon.io/v3/reference/tickers/{t}",
                             params={"apiKey": key}, timeout=5)
            if r.ok:
                res = (r.json() or {}).get("results") or {}
                sic = (res.get("sic_description") or "").strip()
                out = {
                    "name": res.get("name") or None,
                    "description": (res.get("description") or "").strip() or None,
                    "market_cap": res.get("market_cap"),
                    "sector": sic.title() if sic else None,
                }
    except Exception:  # noqa: BLE001 — reference lookup is optional context, never fatal
        out = None
    _details_cache[t] = out
    return out


_search_cache: dict[str, tuple[float, list]] = {}


def search_tickers(query: str, limit: int = 12) -> list[dict]:
    """Live US-stock search via Polygon /v3/reference/tickers (`search` matches ticker OR
    name). Returns [{ticker, name, type, exchange}], active common stocks/ETFs first.
    Best-effort: [] when unkeyed / offline. Cached `_TTL` seconds per (query, limit)."""
    import os
    q = (query or "").strip()
    if not q:
        return []
    ckey = f"{q.lower()}|{limit}"
    now = time.time()
    hit = _search_cache.get(ckey)
    if hit and (now - hit[0]) < _TTL:
        return hit[1]
    out: list[dict] = []
    try:
        import requests
        key = (os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY") or "").strip()
        if key:
            r = requests.get(
                "https://api.polygon.io/v3/reference/tickers",
                params={"search": q, "market": "stocks", "active": "true",
                        "limit": max(1, min(int(limit), 50)), "apiKey": key},
                timeout=6)
            if r.ok:
                for res in (r.json() or {}).get("results") or []:
                    tk = (res.get("ticker") or "").upper()
                    if not tk:
                        continue
                    out.append({
                        "ticker": tk,
                        "name": res.get("name") or "",
                        "type": res.get("type") or "",
                        "exchange": res.get("primary_exchange") or "",
                    })
    except Exception:  # noqa: BLE001 — search is best-effort, never fatal
        out = []
    _search_cache[ckey] = (now, out)
    return out


_snapshot_cache: dict[str, tuple[float, Optional[dict]]] = {}

# Observation records belong to the existing cache entry, not another price owner.
# The snapshot dict remains shared exactly as before. Changed selected fields lose
# their retrieval context; recording never repairs or admits a numerical value.
_snapshot_observations: dict = {}


def _snapshot_clock():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _snapshot_payload_fields(snap):
    import math
    import re
    if type(snap) is not dict:
        return None, None, None, None
    day = snap.get("day")
    day = day if type(day) is dict else None
    value = day.get("o") if day is not None else None
    if type(value) not in (int, float) or not math.isfinite(value):
        value = None
    symbol = snap.get("ticker")
    if type(symbol) is not str or not re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", symbol):
        symbol = None
    updated = snap.get("updated")
    # Keep the provider integer exact through JSON/JavaScript. Its unit is not
    # established here and it is never relabelled as the Open event or bar date.
    updated = str(updated) if type(updated) is int and 0 <= updated < 2**64 else None
    return day, value, symbol, updated


def _remember_snapshot_observation(ticker, entry, started, returned):
    day, value, symbol, updated = _snapshot_payload_fields(entry[1])
    record = (entry, day, value, symbol, updated, started, returned)
    try:
        _snapshot_observations[ticker] = record
    except Exception:
        pass
    return record


def _emit_snapshot_observation(sink, entry, record, observed):
    if sink is not None:
        try:
            sink.clear()
            sink.update(entry=entry, record=record, observed=observed)
        except Exception:
            pass


def _emit_open_observation(sink, ticker, snap, raw_open, price, captured):
    """Project only the selected source fields and its captured retrieval clocks."""
    if sink is None:
        return
    try:
        import math
        from datetime import datetime, timezone

        def epoch(value):
            if isinstance(value, datetime):
                return value.timestamp() if value.tzinfo is not None else None
            return value if type(value) in (int, float) and math.isfinite(value) else None

        def timestamp(value):
            value = epoch(value)
            return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None

        selected = price if type(price) in (int, float) and math.isfinite(price) and price > 0 else None
        result = {
            "schema": "mastermind.polygon_snapshot_evidence.v1",
            "ticker": (ticker or "").upper().strip(), "field": "day.o",
            "price": selected, "currency": "USD", "status": "unavailable",
            "reason": "snapshot_context_unavailable",
            "payload_ticker": None, "payload_ticker_status": "unavailable",
            "source_updated_raw": None, "source_updated_unit": "not_established",
            "source_bar_label": None, "source_bar_label_kind": "not_provided",
            "cache_anchor_at": None, "request_started_at": None,
            "response_returned_at": None, "cache_age_observed_at": None,
            "cache_age_seconds": None, "within_cache_ttl": None,
            "cache_clock_basis": "lookup_before_request",
            "market_observed_at": None, "execution_qualification": "not_checked",
        }
        entry = captured.get("entry") if type(captured) is dict else None
        record = captured.get("record") if type(captured) is dict else None
        bound = (
            type(entry) is tuple and len(entry) == 2 and entry[1] is snap
            and type(record) is tuple and len(record) == 7 and record[0] is entry
        )
        if selected is None:
            result["reason"] = "no_selected_open"
        elif type(raw_open) not in (int, float) or not math.isfinite(raw_open):
            result["reason"] = "unsupported_selected_value"
        elif bound:
            day, value, symbol, updated = _snapshot_payload_fields(snap)
            if (
                day is not record[1] or type(raw_open) is not type(record[2])
                or raw_open != record[2] or value != record[2]
                or symbol != record[3] or updated != record[4]
            ):
                result["reason"] = "snapshot_fields_changed"
            else:
                anchor, started, returned, observed = (
                    epoch(entry[0]), epoch(record[5]), epoch(record[6]),
                    epoch(captured.get("observed")),
                )
                payload_status = "unavailable" if symbol is None else (
                    "matched" if symbol == result["ticker"] else "mismatch"
                )
                result.update(
                    status="available", reason=None, payload_ticker=symbol,
                    payload_ticker_status=payload_status, source_updated_raw=updated,
                    cache_anchor_at=timestamp(anchor), request_started_at=timestamp(started),
                    response_returned_at=timestamp(returned), cache_age_observed_at=timestamp(observed),
                )
                known = [x for x in (anchor, started, returned, observed) if x is not None]
                regressed = any(a > b for a, b in zip(known, known[1:]))
                if regressed:
                    result.update(status="partial", reason="local_clock_regressed")
                else:
                    if anchor is not None and observed is not None:
                        age = observed - anchor
                        result.update(cache_age_seconds=age, within_cache_ttl=age < _TTL)
                    if any(x is None for x in (anchor, started, returned, observed)):
                        result.update(status="partial", reason="retrieval_clock_unavailable")
                if payload_status != "matched":
                    result.update(status="partial", reason=(
                        "payload_ticker_mismatch" if payload_status == "mismatch"
                        else "payload_ticker_unavailable"
                    ))
                elif updated is None and result["status"] == "available":
                    result.update(status="partial", reason="snapshot_updated_unavailable")
        sink.clear()
        sink.update(result)
    except Exception:
        pass



def _snapshot(ticker: str, *, _evidence=None) -> Optional[dict]:
    """Raw Polygon snapshot `ticker` object for one symbol (cached `_TTL` s).
    None when unkeyed / offline / paywalled."""
    import os
    t = (ticker or "").upper().strip()
    if not t:
        return None
    now = time.time()
    hit = _snapshot_cache.get(t)
    if hit and (now - hit[0]) < _TTL:
        try:
            record = _snapshot_observations.get(t)
            _emit_snapshot_observation(_evidence, hit, record, now)
        except Exception:
            pass
        return hit[1]
    out = None
    started = returned = None
    try:
        import requests
        key = (os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY") or "").strip()
        if key:
            try:
                started = _snapshot_clock()
            except Exception:
                pass
            r = requests.get(
                f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{t}",
                params={"apiKey": key}, timeout=6)
            try:
                returned = _snapshot_clock()
            except Exception:
                pass
            if r.ok:
                out = (r.json() or {}).get("ticker") or None
    except Exception:  # noqa: BLE001
        out = None
    entry = (now, out)
    record = None
    try:
        # Capture the selected fields before exposing the shared mutable dict.
        record = _remember_snapshot_observation(t, entry, started, returned)
    except Exception:
        pass
    _snapshot_cache[t] = entry
    try:
        _emit_snapshot_observation(_evidence, entry, record, returned)
    except Exception:
        pass
    return out


def day_open(ticker: str, *, _evidence=None) -> Optional[float]:
    """Positive `snapshot.day.o` using the existing numerical admission contract.

    The source field alone does not establish a bar date, opening event, matching
    payload symbol or order eligibility. Optional observations do not change that
    admission, the shared mutable snapshot, cache refresh or fallback behavior.
    """
    captured = {}
    if _evidence is None:
        snap = _snapshot(ticker) or {}
    else:
        try:
            from portfolio.price_evidence import read_with_evidence
        except Exception:
            snap = _snapshot(ticker) or {}
        else:
            snap, captured = read_with_evidence(_snapshot, ticker)
            snap = snap or {}
    o = (snap.get("day") or {}).get("o")
    price = float(o) if (o and float(o) > 0) else None
    try:
        _emit_open_observation(_evidence, ticker, snap, o, price, captured)
    except Exception:
        pass
    return price


def snapshot_price(ticker: str) -> Optional[float]:
    """Best available price from the Polygon snapshot, robust on DELAYED / EOD-tier keys
    (where `lastTrade` and the intraday `day` block are empty outside market hours): tries
    last trade → last-minute close → today's close → prior-day close. Paper marks are
    EOD-grade, so prior-day close is an honest fallback when nothing live is published."""
    snap = _snapshot(ticker)
    if not snap:
        return None
    for grp, fld in (("lastTrade", "p"), ("min", "c"), ("day", "c"), ("prevDay", "c")):
        v = (snap.get(grp) or {}).get(fld)
        if v and float(v) > 0:
            return float(v)
    return None


def quote(ticker: str) -> Optional[float]:
    """Live (delayed) last/close for one ticker, or None. Cached `_TTL` seconds."""
    t = (ticker or "").upper().strip()
    if not t:
        return None
    now = time.time()
    hit = _cache.get(t)
    if hit and (now - hit[0]) < _TTL:
        return hit[1]
    c = _get_client()
    px: Optional[float] = None
    if c is not None:
        try:
            px = c.spot(t)
        except Exception:
            px = None
    _cache[t] = (now, px)
    return px


def quotes(tickers: Iterable[str]) -> dict[str, Optional[float]]:
    """Batch quotes -> {TICKER: price|None}. De-dupes; uses the per-symbol cache."""
    out: dict[str, Optional[float]] = {}
    for t in tickers or []:
        tk = (t or "").upper().strip()
        if tk and tk not in out:
            out[tk] = quote(tk)
    return out
