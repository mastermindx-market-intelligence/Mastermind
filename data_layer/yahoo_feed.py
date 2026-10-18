"""Yahoo (yfinance) live price feed — fresh quotes for US, China, and Hong-Kong books.

Serves any yfinance symbol in ONE batched ``yf.download`` call, token-free:
  * US names (bare tickers + ETFs, e.g. ``SMH``, ``NVDA``) — the US books had NO live leg and
    marked off the CI/EOD-lagging vendored snapshot, so on a fast day (SMH -7%) the NAV was wrong.
    paper_account now routes US marks here too.
  * Hong-Kong names (``0700.HK``) — Tushare's ``hk_daily`` is throttled to ~1 req/hr; Yahoo isn't.
  * Mainland A-shares (``600000.SS`` / ``000001.SZ``) — the dashboard live-preview path now warms
    these too instead of freezing the China book on Terminal's published snapshot.
The quote is in the symbol's native currency (USD / HKD / CNY); ``paper_account`` converts it to
the book's base currency via ``portfolio.fx``.

Liveness: the cache carries an INTRADAY TTL (``YAHOO_FEED_TTL_SEC``, default 120s) so a long-lived
server re-fetches a moving symbol rather than freezing it at the day's first print — a book viewed
mid-selloff shows the live drawdown. ``warm(all_tickers)`` once per mark fetches the whole book in a
single request; per-name ``price_local`` lookups reuse the cache until the TTL lapses.

Downloads supply daily-bar Open/Close fields. Cache TTL controls retrieval frequency; it does not
prove when a market price was observed. A failed refresh can leave a prior Close available to
``price_local``; only an absent quote returns None for the caller's next fallback. The selected
Close's bar label and available retrieval clocks are observational evidence, not fill qualification.
"""
from __future__ import annotations

import logging
import math
import os
import threading
import time
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

_CACHE: dict[str, float] = {}      # SYMBOL -> latest Close quote in its local currency (per process)
_OPEN_CACHE: dict[str, tuple[float, datetime]] = {}  # SYMBOL -> (Open, source daily-bar timestamp)
_TS: dict[str, float] = {}         # SYMBOL -> monotonic ts of its last fetch (drives the intraday TTL)
_ASOF: dict[str, str] = {}         # SYMBOL -> wall-clock UTC fetch start (legacy provenance)
_CLOSE_EVIDENCE: dict[str, dict] = {}  # Bound label/download clocks for the selected Close
_OPEN_EVIDENCE: dict[str, dict] = {}  # Exact Open tuple and its own download clocks
_HISTORY_CACHE: dict[tuple[str, str], object] = {}  # (SYMBOL, period) -> native-currency close Series
_HISTORY_TS: dict[tuple[str, str], float] = {}
_FETCHED_DAY: str | None = None    # the calendar day the cache was populated for (cleared when it rolls)

# Serialise blocking fetches so concurrent callers dedup onto ONE batched download (kills the
# book-switch stampede), and track which symbols a background thread is already fetching so the hot
# request path can refresh the cache off-thread without ever blocking on yfinance.
_LOCK = threading.Lock()
_INFLIGHT: set[str] = set()


def _ttl() -> float:
    """Seconds before a cached quote is re-fetched (intraday liveness). 0 = per-day cache only.
    Tunable via env ``YAHOO_FEED_TTL_SEC`` (default 120)."""
    try:
        return max(0.0, float(os.environ.get("YAHOO_FEED_TTL_SEC", "120")))
    except (TypeError, ValueError):
        return 120.0


def _history_ttl() -> float:
    """Seconds before a benchmark-history series is refreshed (default 30 minutes)."""
    try:
        return max(60.0, float(os.environ.get("YAHOO_HISTORY_TTL_SEC", "1800")))
    except (TypeError, ValueError):
        return 1800.0


def _today() -> str:
    try:
        return date.today().isoformat()
    except Exception:
        return ""


def _reset_if_stale() -> None:
    """Drop the cache when the calendar day rolls so a long-lived server re-fetches each day."""
    global _FETCHED_DAY, _CACHE, _OPEN_CACHE, _TS, _ASOF, _HISTORY_CACHE, _HISTORY_TS, _CLOSE_EVIDENCE, _OPEN_EVIDENCE
    d = _today()
    if _FETCHED_DAY != d:
        _CACHE, _OPEN_CACHE, _TS, _ASOF, _HISTORY_CACHE, _HISTORY_TS = {}, {}, {}, {}, {}, {}
        _CLOSE_EVIDENCE = {}
        _OPEN_EVIDENCE = {}
        _FETCHED_DAY = d


def _fresh(sym: str, now: float, ttl: float) -> bool:
    """A cached symbol is fresh iff present AND (TTL disabled OR fetched within the TTL window)."""
    if sym not in _CACHE:
        return False
    if ttl <= 0:
        return True
    return (now - _TS.get(sym, 0.0)) <= ttl


def warm(tickers, background: bool = False) -> None:
    """Fetch quotes for `tickers` in ONE batched yfinance call and cache the latest per symbol.
    Re-fetches only symbols that are missing or past the intraday TTL — fresh symbols cost nothing.
    Best-effort: a missing yfinance / network / parse failure leaves the cache as-is, and callers
    degrade to the vendored snapshot.

    ``background=True`` (the hot request path — the dashboard) runs the fetch in a daemon thread and
    returns immediately, so a book SWITCH never blocks on a network download: it serves whatever is
    cached now (see ``price_cached``) or the caller's own instant Terminal-snapshot fallback, and the
    fresh quote lands on a subsequent lookup. Concurrent background callers dedup via ``_INFLIGHT`` —
    the three parallel switch endpoints spawn at most ONE fetch, not three (the old stampede).

    ``background=False`` (scheduler pre-warm / NAV marks) blocks under ``_LOCK`` so two concurrent
    callers serialise onto a single batched download instead of both hitting the network."""
    _reset_if_stale()
    now, ttl = time.monotonic(), _ttl()
    want = sorted({(t or "").upper().strip() for t in (tickers or [])} - {""})
    want = [s for s in want if not _fresh(s, now, ttl)]
    if not want:
        return
    if background:
        # NON-BLOCKING: if a fetch already holds the lock (a blocking pre-warm / NAV mark is mid
        # yf.download), do NOT wait — the request serves the cache / Terminal fallback and the fresh
        # quote lands on a later lookup. Only _INFLIGHT is touched under the (try-acquired) lock.
        if not _LOCK.acquire(blocking=False):
            return
        try:
            todo = [s for s in want if s not in _INFLIGHT]
            if not todo:
                return
            _INFLIGHT.update(todo)
        finally:
            _LOCK.release()
        threading.Thread(target=_bg_fetch, args=(todo,), daemon=True).start()
        return
    with _LOCK:
        # re-check freshness under the lock — a caller we queued behind may have just populated these
        todo = [s for s in want if not _fresh(s, time.monotonic(), ttl)]
        if todo:
            _fetch_and_cache(todo)


def _bg_fetch(want) -> None:
    """Daemon-thread wrapper: fetch off the request thread, then clear the in-flight guard."""
    # Hold the same lock as blocking warm() for the duration of yf.download. A live-marks request
    # arriving just after the dashboard's background warm then waits for that one batch and reuses
    # it instead of launching a duplicate download.
    with _LOCK:
        try:
            todo = [s for s in want if not _fresh(s, time.monotonic(), _ttl())]
            if todo:
                _fetch_and_cache(todo)
        finally:
            _INFLIGHT.difference_update(want)


def _remember_close_evidence(sym, series, price, fetched_mono, fetched_at, returned_at) -> None:
    """Retain the selected Close's label and local download-return time."""
    try:
        label = series.index[-1]
        if not isinstance(label, date):
            raise ValueError("daily bar label is not a date")
        label = label.isoformat()
        if not isinstance(label, str) or len(label) > 64:
            raise ValueError("daily bar label is not bounded")
        datetime.fromisoformat(label)  # Reject NaT or an unusable date-subclass label.
    except Exception:
        label = None
    try:
        # Bind every piece to the exact existing cache generation. Readers reject a torn or
        # externally primed cache instead of joining an old label to a new scalar price.
        _CLOSE_EVIDENCE[sym] = {
            "price_local": price,
            "fetched_mono": fetched_mono,
            "fetch_started_at": fetched_at,
            "download_returned_at": returned_at,
            "source_bar_label": label,
        }
    except Exception:
        pass


def _close_evidence_generation(sym):
    """Pin the metadata record before the scalar read; publication replaces whole records."""
    try:
        return _CLOSE_EVIDENCE.get(sym)
    except Exception:
        return None  # Metadata capture must not prevent the original scalar read.


def _close_price_evidence(sym, price, now, fetched_mono, fetched_at, cached) -> dict:
    """Observational metadata only: a daily-bar label is not a trade or availability time."""
    out = {
        "schema": "mastermind.yahoo_daily_bar_evidence.v1",
        "ticker": sym,
        "field": "Close",
        "status": "unavailable",
        "reason": "price_unavailable",
        "price_local": None,
        "source_bar_label": None,
        "source_bar_label_kind": "daily_bar_label",
        "fetch_started_at": None,
        "download_returned_at": None,
        "fetch_age_seconds": None,
        "within_cache_ttl": None,
        "market_observed_at": None,
        "execution_qualification": "not_checked",
    }
    try:
        if price is None:
            return out
        out["reason"] = "price_invalid"
        if (
            isinstance(price, bool) or not isinstance(price, (int, float))
            or not math.isfinite(price) or price <= 0
        ):
            return out
        out["price_local"] = float(price)
        out["reason"] = "cache_binding_unavailable"
        if (
            not isinstance(cached, dict)
            or _CLOSE_EVIDENCE.get(sym) is not cached
            or cached.get("price_local") != price
            or cached.get("fetched_mono") != fetched_mono
            or cached.get("fetch_started_at") != fetched_at
        ):
            return out
        age = now - cached["fetched_mono"]
        out["reason"] = "cache_clock_invalid"
        if not math.isfinite(age) or age < 0:
            return out
        ttl = _ttl()
        out.update({
            "status": "available",
            "reason": None,
            "source_bar_label": cached.get("source_bar_label"),
            "fetch_started_at": cached.get("fetch_started_at"),
            "download_returned_at": cached.get("download_returned_at"),
            "fetch_age_seconds": round(age, 1),
            "within_cache_ttl": ttl <= 0 or age <= ttl,
        })
        if out["source_bar_label"] is None:
            out.update(status="partial", reason="source_bar_label_unavailable")
        elif out["download_returned_at"] is None:
            out.update(status="partial", reason="download_return_time_unavailable")
    except Exception:
        # No source exception strings or arbitrary provider objects enter this envelope.
        out.update(status="unavailable", reason="evidence_read_failed")
    return out



def _remember_open_evidence(sym, quote, fetched_mono, fetched_at, returned_at) -> None:
    """Retain the exact Open tuple and its own download clocks, separately from Close."""
    try:
        label = quote[1]
        if not isinstance(label, date):
            raise ValueError("daily bar label is not a date")
        label = label.isoformat()
        if not isinstance(label, str) or len(label) > 64:
            raise ValueError("daily bar label is not bounded")
        datetime.fromisoformat(label)
    except Exception:
        label = None
    try:
        _OPEN_EVIDENCE[sym] = {
            "quote": quote,
            "fetched_mono": fetched_mono,
            "fetch_started_at": fetched_at,
            "download_returned_at": returned_at,
            "source_bar_label": label,
        }
    except Exception:
        pass


def _open_evidence_generation(sym):
    """Pin the Open metadata before reading the selected tuple."""
    try:
        return _OPEN_EVIDENCE.get(sym)
    except Exception:
        return None


def _open_price_evidence(sym, price, quote, now, cached, selection_reason) -> dict:
    """Observe the Open's generation; shared Close freshness is not an Open clock."""
    out = {
        "schema": "mastermind.yahoo_daily_bar_evidence.v2",
        "ticker": sym,
        "field": "Open",
        "status": "unavailable",
        "reason": selection_reason or "price_unavailable",
        "price_local": None,
        "source_bar_label": None,
        "source_bar_label_kind": "daily_bar_label",
        "fetch_started_at": None,
        "download_returned_at": None,
        "fetch_age_seconds": None,
        "within_cache_ttl": None,
        "cache_refresh_basis": "shared_close_cache",
        "market_observed_at": None,
        "execution_qualification": "not_checked",
    }
    try:
        if price is not None:
            out["reason"] = "price_invalid"
            if (
                isinstance(price, bool) or not isinstance(price, (int, float))
                or not math.isfinite(price) or price <= 0
            ):
                return out
            out["price_local"] = float(price)
        if quote is None:
            return out
        out["reason"] = "cache_binding_unavailable"
        if (
            not isinstance(cached, dict)
            or _OPEN_EVIDENCE.get(sym) is not cached
            or cached.get("quote") is not quote
        ):
            return out
        # The Open may survive a Close-only refresh, or refresh when Close does not.
        # Its own capture record is the only clock used for this observation.
        age = now - cached["fetched_mono"]
        out["reason"] = "cache_clock_invalid"
        if not math.isfinite(age) or age < 0:
            return out
        ttl = _ttl()
        out.update({
            "status": "available" if price is not None else "unavailable",
            "reason": None if price is not None else selection_reason or "price_unavailable",
            "source_bar_label": cached.get("source_bar_label"),
            "fetch_started_at": cached.get("fetch_started_at"),
            "download_returned_at": cached.get("download_returned_at"),
            "fetch_age_seconds": round(age, 1),
            "within_cache_ttl": ttl <= 0 or age <= ttl,
        })
        if price is not None:
            if out["source_bar_label"] is None:
                out.update(status="partial", reason="source_bar_label_unavailable")
            elif out["download_returned_at"] is None:
                out.update(status="partial", reason="download_return_time_unavailable")
    except Exception:
        out.update(status="unavailable", reason="evidence_read_failed")
    return out


def _fetch_and_cache(want) -> None:
    """The actual batched yfinance download + cache populate (Close for marks, Open for settle)."""
    now = time.monotonic()
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        import yfinance as yf
        df = yf.download(want, period="7d", progress=False, auto_adjust=False, threads=False)
    except Exception as e:  # noqa: BLE001
        log.debug("yahoo_feed download failed for %s (%s)", want, e)
        return
    try:
        returned_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    except Exception:
        returned_at = None  # The local download-return clock is optional; legacy prices remain available.
    try:
        close = df["Close"]                       # DataFrame (multi-symbol) or Series (single)
    except Exception as e:  # noqa: BLE001
        log.debug("yahoo_feed: no Close column (%s)", e)
        return
    # Also grab the Open column for settle._open_price_usd — today's session Open is the
    # correct fill price for orders that queued overnight (avoids the ~11am partial-day mark).
    try:
        open_col = df["Open"]
    except Exception:
        open_col = None
    try:
        if hasattr(close, "columns"):             # multi-symbol → column per ticker
            for sym in close.columns:
                s = close[sym].dropna()
                if len(s):
                    k = str(sym).upper().strip()
                    _CACHE[k], _TS[k], _ASOF[k] = float(s.iloc[-1]), now, fetched_at
                    _remember_close_evidence(k, s, _CACHE[k], now, fetched_at, returned_at)
            # Preserve the Open's source-bar timestamp so readers can reject older sessions.
            if open_col is not None and hasattr(open_col, "columns"):
                for sym in open_col.columns:
                    s = open_col[sym].dropna()
                    if len(s):
                        k = str(sym).upper().strip()
                        v = float(s.iloc[-1])
                        if v > 0:
                            quote = (v, s.index[-1])
                            _OPEN_CACHE[k] = quote
                            try:
                                _remember_open_evidence(k, quote, now, fetched_at, returned_at)
                            except Exception:
                                pass  # An observation failure must not skip another symbol.
        else:                                     # single ticker → a bare Series
            s = close.dropna()
            if len(s) and len(want) == 1:
                _CACHE[want[0]], _TS[want[0]], _ASOF[want[0]] = (
                    float(s.iloc[-1]), now, fetched_at)
                _remember_close_evidence(want[0], s, _CACHE[want[0]], now, fetched_at, returned_at)
            if open_col is not None and not hasattr(open_col, "columns"):
                so = open_col.dropna()
                if len(so) and len(want) == 1:
                    v = float(so.iloc[-1])
                    if v > 0:
                        quote = (v, so.index[-1])
                        _OPEN_CACHE[want[0]] = quote
                        try:
                            _remember_open_evidence(want[0], quote, now, fetched_at, returned_at)
                        except Exception:
                            pass
    except Exception as e:  # noqa: BLE001
        log.debug("yahoo_feed parse failed (%s)", e)


def price_local(ticker: str, asof: str | None = None,
                *, _evidence: dict | None = None) -> float | None:
    """The latest cached Yahoo Close in the ticker's local currency, or None.

    Refreshes missing/expired symbols. A failed refresh can retain a prior cached price;
    fetch TTL is not evidence of the bar's age. The compatibility ``asof`` argument does
    not request historical data. An optional private observation sink receives the exact
    selected Close's available source/retrieval clocks without changing the numeric return.
    """
    t = (ticker or "").upper().strip()
    if t:
        warm([t])                                 # no-op when the symbol is still fresh
    cached = _close_evidence_generation(t) if _evidence is not None else None
    price = _CACHE.get(t) if t else None
    if _evidence is not None:
        try:
            _evidence.update(_close_price_evidence(
                t, price, time.monotonic(), _TS.get(t), _ASOF.get(t), cached
            ))
        except Exception:
            pass                                  # observation cannot control price selection
    return price


def price_cached(ticker: str) -> float | None:
    """Cache-ONLY lookup: the last cached quote in its LOCAL currency if still fresh, else None.
    NEVER fetches — for the hot request path (the dashboard). Pair with a prior
    ``warm(..., background=True)`` and a Terminal-snapshot fallback so a book switch never blocks."""
    _reset_if_stale()
    t = (ticker or "").upper().strip()
    if not t:
        return None
    if _fresh(t, time.monotonic(), _ttl()):
        return _CACHE.get(t)
    return None


def history_local(ticker: str, period: str = "2y"):
    """Native-currency daily close history for a Yahoo symbol, cached in-process.

    The vendored Macro parquet does not currently carry the CSI 300 or Hang Seng indexes. This
    narrow fallback gives regional performance charts their real index history without refetching
    it on every portfolio switch. Calls for different books serialize through the same Yahoo lock,
    preventing the cold-start request stampede that previously slowed the dashboard.
    """
    _reset_if_stale()
    symbol = (ticker or "").upper().strip()
    if not symbol:
        return None
    key = (symbol, str(period))
    now = time.monotonic()
    cached = _HISTORY_CACHE.get(key)
    if cached is not None and (now - _HISTORY_TS.get(key, 0.0)) <= _history_ttl():
        return cached.copy()

    with _LOCK:
        cached = _HISTORY_CACHE.get(key)
        if cached is not None and (time.monotonic() - _HISTORY_TS.get(key, 0.0)) <= _history_ttl():
            return cached.copy()
        try:
            import yfinance as yf
            df = yf.download(symbol, period=period, progress=False,
                             auto_adjust=False, threads=False)
            close = df["Close"]
            if hasattr(close, "columns"):
                close = close[symbol] if symbol in close.columns else close.iloc[:, 0]
            series = close.astype(float).dropna()
            if len(series) == 0:
                return None
            _HISTORY_CACHE[key] = series.copy()
            _HISTORY_TS[key] = time.monotonic()
            return series.copy()
        except Exception as exc:  # noqa: BLE001
            log.debug("yahoo_feed history failed for %s (%s)", symbol, exc)
            return cached.copy() if cached is not None else None


def quote_cached(ticker: str) -> dict | None:
    """Cache-only quote plus freshness/provenance metadata; never touches the network."""
    _reset_if_stale()
    t = (ticker or "").upper().strip()
    now = time.monotonic()
    if not t or not _fresh(t, now, _ttl()):
        return None
    cached = _close_evidence_generation(t)
    price = _CACHE.get(t)
    fetched_mono, fetched_at = _TS.get(t, now), _ASOF.get(t)
    return {
        "ticker": t,
        "price_local": price,
        "source": "yahoo_intraday",
        "as_of": fetched_at,
        "time_kind": "feed_retrieval",
        "age_seconds": max(0, round(now - fetched_mono, 1)),
        "fresh": True,
        "daily_bar_evidence": _close_price_evidence(t, price, now, fetched_mono, fetched_at, cached),
    }


def open_price_local(ticker: str, *, _evidence: dict | None = None) -> float | None:
    """Today's exchange-date Open in local currency, or None.

    The existing shared Close cache still determines when warm() downloads. A retained
    Open can therefore have different retrieval clocks from Close. The optional sink
    observes the exact Open tuple and its own clocks without selecting another price.
    Date agreement alone does not establish an individual security's opening event
    or whether an order could have participated in it.
    """
    t = (ticker or "").upper().strip()
    if not t:
        if _evidence is not None:
            try:
                _evidence.update(_open_price_evidence(t, None, None, 0.0, None, "empty_ticker"))
            except Exception:
                pass
        return None
    warm([t])                                     # original shared Close-cache refresh policy
    cached = _open_evidence_generation(t) if _evidence is not None else None
    quote = _OPEN_CACHE.get(t)
    selected = None
    reason = "open_unavailable"
    if quote is not None:
        try:
            zone = ZoneInfo(
                "Asia/Hong_Kong" if t.endswith(".HK") or t == "^HSI"
                else "Asia/Shanghai" if t.endswith((".SS", ".SZ"))
                else "America/New_York"
            )
            value, bar_at = quote
            # Preserve the original exchange-date check and scalar return.
            bar_day = bar_at.astimezone(zone).date() if bar_at.tzinfo else bar_at.date()
            if bar_day == datetime.now(zone).date():
                selected = value
                reason = None
            else:
                reason = "exchange_date_mismatch"
        except Exception:
            reason = "exchange_date_unavailable"
    if _evidence is not None:
        try:
            _evidence.update(_open_price_evidence(
                t, selected, quote, time.monotonic(), cached, reason
            ))
        except Exception:
            pass                                  # observation cannot control numeric selection
    return selected                               # original Close / snapshot fallback remains


_HEALTH_PROBE = "0700.HK"          # Tencent — about as liquid as Hong Kong gets; if Yahoo can't
                                   # price IT, the live feed is genuinely down, not a per-name gap.


def feed_healthy(probe: str | None = None) -> bool | None:
    """Is the live Yahoo feed actually serving quotes? Tri-state, mirroring
    ``tushare_feed.feed_healthy`` so the HK book gates identically to the China book:
      * ``True``  — a canonical liquid name prices through the live path.
      * ``False`` — yfinance is importable but the probe won't price: a live OUTAGE.
      * ``None``  — yfinance isn't importable; the live feed isn't deployed (tests stub it off).
    Yahoo needs no token, so importability stands in for "the live feed is deployed"."""
    try:
        import yfinance  # noqa: F401
    except Exception:
        return None
    return price_local(probe or _HEALTH_PROBE) is not None


def clear_cache() -> None:
    """Drop the per-process price memo (tests / a forced refresh)."""
    global _CACHE, _OPEN_CACHE, _TS, _ASOF, _HISTORY_CACHE, _HISTORY_TS, _FETCHED_DAY, _CLOSE_EVIDENCE, _OPEN_EVIDENCE
    _CACHE, _OPEN_CACHE, _TS, _ASOF, _HISTORY_CACHE, _HISTORY_TS = {}, {}, {}, {}, {}, {}
    _CLOSE_EVIDENCE = {}
    _OPEN_EVIDENCE = {}
    _FETCHED_DAY = None
