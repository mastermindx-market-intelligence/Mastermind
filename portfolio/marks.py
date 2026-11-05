"""THE marking layer (charter P7 — one marking layer) — W-L / L1.

Before this module there were three ways a Mastermind book got a price:
  * ``paper_account._current_price`` (live Yahoo → vendored snapshot → parquet, USD),
  * ``self_directed._current_price`` (a SEPARATE Polygon/stockdata path that never reads the
    parquet store — so the Self-Directed book showed a *zero* return whenever its held names had
    no live quote and fell back to avg_cost), and
  * the shadow books' own ``_gather_prices`` (yet another accessor).
Three accessors → three answers for the same symbol on the same day = drift, and drift is death
(P7). This module is the SINGLE source of a mark. Every NAV writer routes through it.

Contract — one *logged* source precedence, evaluated per symbol, most-authoritative first.
Every source row carries its full observation basis, not just a label: ``stale_days`` (directional
age for EVERY priced row), ``observed_asof`` (the session date the price belongs to),
``retrieved_at`` (this run's clock for a live/seed row; the stored clock for a carry), ``basis``
(``raw`` / ``split_div_adjusted_at_retrieval`` / ``unknown``), ``time_kind`` (``session_close`` /
``intraday`` / ``carry`` / ``seed``) and ``close_qualified``. A priced row whose age cannot be
bounded — observation date missing, unparseable or in the future — is NOT consumed; it degrades
down the chain (P2: degrade, never fabricate).

  1. ``polygon-eod``    — the RAW (unadjusted) Polygon daily aggregate for the requested as-of
                          date; historical dates use only that session's aggregate, never the
                          live snapshot. For the current ET session date before the close has
                          settled, the live snapshot is labelled ``polygon-intraday`` (or
                          ``polygon-prevday``), is never close-qualified and never refreshes the
                          carry; after the close settles only the official bar is used.
  2. ``yahoo-parquet``  — the vendored dividend-adjusted daily-close parquet (``lib.store``),
                          last row ≤ asof (deterministic, offline, survivorship-clean), labelled
                          ``split_div_adjusted_at_retrieval`` with ``adjusted_through`` (the
                          newest parquet date) so a consumer can see it is a restatement as of
                          retrieval, not as known at asof.
  3. ``last-good-carry`` — the last mark we successfully logged for this symbol, carried forward
                          with a ``stale_days`` count so a book can never silently freeze on a
                          missing feed (P2: missing data degrades to a *carried* mark, it never
                          fabricates a move and it never touches avg_cost). The carry store
                          refreshes only from ``polygon-eod`` / ``yahoo-parquet`` / ``seed`` rows
                          and only monotonically in ``observed_asof`` — a replay with an older
                          observation never moves the store backward.

**NEVER avg_cost.** The old convention marked an unpriceable name at its cost basis, which quietly
zeroes that name's return — the exact bug that made Self-Directed read flat. A name with no source
and no carry is returned *unpriced* (absent from the dict); the NAV writer then holds it at its
prior mark rather than snapping it to cost.

Currency: marks are produced in USD. A non-USD book converts at its own NAV writer (the daily-mark
job already does ``fx.usd_to``), exactly as before — this layer does not change that seam.

Persistence: ``data/marks/last_good.json`` is the carry store ({SYMBOL: {price, asof, source,
basis, retrieved_at}}), and each run logs the per-symbol source attribution to
``data/marks/<asof>.json`` (audit: which feed priced what, on what observation basis, and how many
symbols fell to carry). Best-effort throughout; never raises into a build.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from portfolio import market_calendar

_ROOT = Path(__file__).resolve().parent.parent
_MARKS_DIR = _ROOT / "data" / "marks"
_CARRY_PATH = _MARKS_DIR / "last_good.json"

# source labels — the precedence order is the list order (most authoritative first).
SOURCE_POLYGON = "polygon-eod"
SOURCE_POLYGON_INTRADAY = "polygon-intraday"
SOURCE_POLYGON_PREVDAY = "polygon-prevday"
SOURCE_YAHOO = "yahoo-parquet"
SOURCE_CARRY = "last-good-carry"

_STALE_MAX_DAYS_DEFAULT = 30      # a carry older than this is dropped (a 30d-stale mark is not a mark)
_CLOSE_SETTLE_MINUTES = 20        # minutes after the scheduled close before the daily bar is trusted


def _clock() -> datetime:
    """The marks layer's one clock (UTC; every entry point takes ``now=`` to pin it)."""
    return datetime.now(timezone.utc)


def session_final(today_et: date, now: datetime) -> bool:
    """True iff ``today_et`` is a trading day whose scheduled close has settled
    (scheduled close + ``_CLOSE_SETTLE_MINUTES``), i.e. the official daily bar may exist."""
    try:
        if not market_calendar.is_trading_day(today_et):
            return False
        cutoff = datetime.combine(today_et, market_calendar.session_close(today_et),
                                  market_calendar.ET) + timedelta(minutes=_CLOSE_SETTLE_MINUTES)
        return now.astimezone(market_calendar.ET) >= cutoff
    except Exception:  # noqa: BLE001
        return False


def _stale_max_days() -> int:
    """doctrine.yml marks.carry_stale_max_days (unverified-prior), degrade-safe to the default."""
    try:
        from bot.doctrine_config import load_doctrine
        v = (load_doctrine().get("marks") or {}).get("carry_stale_max_days")
        return int(v) if v is not None else _STALE_MAX_DAYS_DEFAULT
    except Exception:  # noqa: BLE001
        return _STALE_MAX_DAYS_DEFAULT


# ─────────────────────────────────────────────────────────────────────────────
# carry store (the last-good-price memory)
# ─────────────────────────────────────────────────────────────────────────────
def _emit_marks_hard_stop(guard: str, detail: str) -> None:
    """Emit a HARD_STOP GuardrailResult to run_events for marks layer failures. Never raises."""
    try:
        from control_plane.guardrail import GuardrailResult, Severity
        GuardrailResult.failed(
            guard,
            Severity.HARD_STOP,
            detail=detail,
            action_taken="marks layer degraded; fabrication prevented",
        ).log(job="marks_layer", book="")
    except Exception:  # noqa: BLE001
        pass


def _load_carry() -> dict:
    try:
        raw = json.loads(_CARRY_PATH.read_text())
        return raw if isinstance(raw, dict) else {}
    except FileNotFoundError:
        return {}  # normal on first run — no HARD_STOP, just start fresh
    except Exception as _exc:  # noqa: BLE001
        _emit_marks_hard_stop("marks_carry_read", f"carry read failed: {_exc!r}"[:200])
        return {}


def _save_carry(carry: dict) -> None:
    try:
        _MARKS_DIR.mkdir(parents=True, exist_ok=True)
        _CARRY_PATH.write_text(json.dumps(carry, indent=2, default=str, sort_keys=True))
    except Exception as _exc:  # noqa: BLE001
        _emit_marks_hard_stop("marks_carry_write", f"carry write failed: {_exc!r}"[:200])


def _days_between(a: str, b: str) -> Optional[int]:
    """Directional age in calendar days: requested as-of minus observed/carry date.

    Negative means the candidate mark is from the future and therefore cannot be consumed by a
    point-in-time mark. ``None`` means the date identity is not trustworthy enough to bound.
    """
    try:
        return (date.fromisoformat(str(a)[:10]) - date.fromisoformat(str(b)[:10])).days
    except Exception:  # noqa: BLE001
        return None


def _bounded_age(asof: str, observed_asof) -> Optional[int]:
    """Directional age if the observation is consumable at ``asof`` (0 ≤ d ≤ stale max), else None.

    ``None`` (missing/unparseable observation date) fails closed: a live row whose date identity
    cannot be bounded is not admissible — the same rule the carry store already applies.
    """
    d = _days_between(asof, observed_asof)
    if d is None or d < 0 or d > _stale_max_days():
        return None
    return d


# ─────────────────────────────────────────────────────────────────────────────
# the two live sources (both optional / offline-safe / injectable in tests)
# ─────────────────────────────────────────────────────────────────────────────
def _observation(price: float, source: str, observed_asof: str, basis: str,
                 time_kind: str, close_qualified: bool) -> dict:
    """The canonical observation record shared by both live sources (contracts C/D)."""
    return {"price": float(price), "source": source, "observed_asof": observed_asof,
            "basis": basis, "time_kind": time_kind, "close_qualified": bool(close_qualified)}


def _epoch_to_et_date(value, divisor: float) -> Optional[str]:
    """ET session date of an epoch timestamp (``divisor`` scales it to seconds), or None."""
    try:
        ts = datetime.fromtimestamp(float(value) / divisor, tz=timezone.utc)
        return ts.astimezone(market_calendar.ET).date().isoformat()
    except Exception:  # noqa: BLE001
        return None


def _snapshot_live_price(snap: dict, today_et: date):
    """(price, observed_asof) from the first positive live snapshot field, or None.

    ``lastTrade.p`` then ``min.c`` then ``day.c``; the observation date is the field's own
    timestamp when present (``lastTrade.t`` is ns, ``min.t`` is ms since epoch), else today.
    """
    try:
        for grp, fld, div in (("lastTrade", "p", 1e9), ("min", "c", 1e3)):
            block = snap.get(grp) or {}
            v = block.get(fld)
            if v and float(v) > 0:
                return float(v), (_epoch_to_et_date(block.get("t"), div) or today_et.isoformat())
        v = (snap.get("day") or {}).get("c")
        if v and float(v) > 0:
            return float(v), today_et.isoformat()
    except Exception:  # noqa: BLE001
        return None
    return None


def _polygon_observation_detail(symbol: str, asof: str, *, now: Optional[datetime] = None):
    """(observation, close_bar_missing) for the default Polygon path. Degrades, never raises.

    ``close_bar_missing`` is True only for the settled-close current-session case where the
    official aggregate has not been published yet (contract C) — the caller counts it.
    """
    try:
        now = now or _clock()
        day = str(asof)[:10]
        today_et = now.astimezone(market_calendar.ET).date()
        if day > today_et.isoformat():
            return None, False                       # future as-of: no observation, no calls
        from data_layer import polygon
        if day < today_et.isoformat():
            # historical/replay: ONLY that session's aggregate, never the live snapshot
            closes = polygon.daily_closes(symbol, day, day, cache=True, adjusted=False)
            px = (closes or {}).get(day)
            if px and float(px) > 0:
                return _observation(float(px), SOURCE_POLYGON, day, "raw",
                                    "session_close", True), False
            return None, False
        # day == the current ET session date
        if not market_calendar.is_trading_day(today_et):
            return None, False                       # weekend/holiday: no snapshot either
        if session_final(today_et, now):
            closes = polygon.daily_closes(symbol, day, day, cache=False, adjusted=False)
            px = (closes or {}).get(day)
            if px and float(px) > 0:
                return _observation(float(px), SOURCE_POLYGON, day, "raw",
                                    "session_close", True), False
            return None, True                        # official bar not published yet — count it
        snap = polygon._snapshot(symbol) or {}
        live = _snapshot_live_price(snap, today_et)
        if live is not None:
            price, observed = live
            return _observation(price, SOURCE_POLYGON_INTRADAY, observed, "raw",
                                "intraday", False), False
        prev = (snap.get("prevDay") or {}).get("c")
        if prev and float(prev) > 0:
            return _observation(float(prev), SOURCE_POLYGON_PREVDAY,
                                market_calendar.previous_trading_day(today_et).isoformat(),
                                "unknown", "session_close", False), False
        return None, False
    except Exception:  # noqa: BLE001
        return None, False


def _polygon_observation(symbol: str, asof: str, *, now: Optional[datetime] = None) -> Optional[dict]:
    """Polygon observation for ``asof`` (contract C): ``{price, source, observed_asof, basis,
    time_kind, close_qualified}`` or ``None``. Degrades, never raises."""
    obs, _bar_missing = _polygon_observation_detail(symbol, asof, now=now)
    return obs


def _polygon_eod(symbol: str, asof: str, *, now: Optional[datetime] = None) -> Optional[float]:
    """Thin float wrapper over ``_polygon_observation`` (kept for existing callers/tests)."""
    obs = _polygon_observation(symbol, asof, now=now)
    try:
        return float(obs["price"]) if obs else None
    except Exception:  # noqa: BLE001
        return None


def _yahoo_close_series(symbol: str):
    """Positive-float close Series (DatetimeIndex) from the vendored yahoo parquet, or None.

    Reads ``lib.store.read("yahoo", symbol)`` exactly as the old inline reader did; split out so
    tests can inject a series without touching the store.
    """
    try:
        import pandas as pd
        from lib import store
        df = store.read("yahoo", symbol)
        if df is None or "close" not in df.columns or len(df) == 0:
            return None
        s = df["close"].astype(float).dropna()
        s.index = pd.to_datetime(s.index)
        s = s[s > 0]
        return s if len(s) else None
    except Exception:  # noqa: BLE001
        return None


def _yahoo_observation(symbol: str, asof: str) -> Optional[dict]:
    """Last yahoo close ≤ asof with its adjustment basis (contract D). Degrades to ``None``.

    ``close_qualified`` is True only when the selected row IS the newest parquet row — no later
    corporate action can have been restated into it.
    """
    try:
        import pandas as pd
        s = _yahoo_close_series(symbol)
        if s is None or len(s) == 0:
            return None
        adjusted_through = s.index[-1].date().isoformat()
        hist = s[s.index <= pd.Timestamp(str(asof)[:10])]
        if len(hist) == 0:
            return None
        observed_asof = hist.index[-1].date().isoformat()
        price = float(hist.iloc[-1])
        if price <= 0:
            return None
        return {"price": price, "source": SOURCE_YAHOO, "observed_asof": observed_asof,
                "basis": "split_div_adjusted_at_retrieval", "time_kind": "session_close",
                "close_qualified": observed_asof == adjusted_through,
                "adjusted_through": adjusted_through}
    except Exception:  # noqa: BLE001
        return None


def _yahoo_parquet(symbol: str, asof: str) -> Optional[float]:
    """Float wrapper over ``_yahoo_observation`` (kept for existing callers/tests). USD."""
    obs = _yahoo_observation(symbol, asof)
    try:
        return float(obs["price"]) if obs else None
    except Exception:  # noqa: BLE001
        return None


def _coerce_observation(v, default_source: str, asof: str) -> Optional[dict]:
    """Normalise a live-source value into the canonical observation shape (contract E).

    Accepts the legacy float contract (every existing caller/test) or an observation dict from
    ``_polygon_observation`` / ``_yahoo_observation``; ``None``/garbage → ``None``. A dict
    missing ``source`` keeps the slot's label; a dict missing ``basis``/``time_kind`` degrades to
    the legacy labels rather than inventing confidence. Only a yahoo observation may carry
    ``adjusted_through`` through to the row.
    """
    if v is None:
        return None
    if isinstance(v, dict):
        price = v.get("price")
        try:
            price = None if price is None else float(price)
        except (TypeError, ValueError):
            return None
        if price is None or price <= 0:
            return None
        obs = {"price": price,
               "source": v.get("source") or default_source,
               "observed_asof": v.get("observed_asof"),
               "basis": v.get("basis") or "unknown",
               "time_kind": v.get("time_kind") or "session_close",
               "close_qualified": bool(v.get("close_qualified"))}
        if default_source == SOURCE_YAHOO and v.get("adjusted_through") is not None:
            obs["adjusted_through"] = v["adjusted_through"]
        return obs
    try:
        price = float(v)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    # legacy float: assumed observed on the requested date, adjustment basis not established
    return {"price": price, "source": default_source, "observed_asof": asof,
            "basis": "unknown", "time_kind": "session_close", "close_qualified": False}


# ─────────────────────────────────────────────────────────────────────────────
# the public marking API
# ─────────────────────────────────────────────────────────────────────────────
def mark_symbols(symbols: Iterable[str], asof: str, *,
                 seed: dict | None = None,
                 polygon_fn=None, yahoo_fn=None,
                 carry: dict | None = None,
                 persist: bool = True,
                 now: datetime | None = None) -> dict:
    """Mark every symbol through the ONE logged precedence chain, returning:

        {
          "as_of": <asof>,
          "prices": {SYMBOL: usd_price, ...},          # ONLY symbols that got a real mark
          "sources": {SYMBOL: {source, price, stale_days, observed_asof, retrieved_at,
                               basis, time_kind, close_qualified[, adjusted_through]}},
          "counts": {"polygon-eod": .., "polygon-intraday": .., "polygon-prevday": ..,
                     "yahoo-parquet": .., "last-good-carry": .., "seed": .., "unpriced": ..,
                     "polygon_close_bar_missing": ..},
        }

    ``seed`` (SYMBOL→px) is treated as an already-trusted mark (used by tests / a shared fetch) and
    short-circuits the source chain for that symbol (logged source ``seed``). A symbol that resolves
    to no source AND has no fresh-enough carry is *unpriced* — absent from ``prices`` (never marked
    to avg_cost). Official rows (polygon-eod / yahoo-parquet / seed) refresh the carry store
    monotonically in ``observed_asof`` so tomorrow's missing feed can carry.

    ``polygon_fn`` / ``yahoo_fn`` inject the two live sources for offline tests (default: the real
    Polygon observation + the yahoo parquet); each may return a legacy float or an observation
    dict (contract E). ``now`` pins this run's clock (default ``_clock()``). Best-effort; never
    raises."""
    asof = str(asof)[:10]
    if now is None:
        now = _clock()
    elif now.tzinfo is None:            # a naive clock is ambiguous — assume UTC, never machine-local
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")
    seed = {(k or "").upper(): v for k, v in (seed or {}).items() if v and v > 0}
    pfn = polygon_fn
    yfn = yahoo_fn if yahoo_fn is not None else _yahoo_observation
    carry = dict(_load_carry() if carry is None else carry)

    prices: dict = {}
    sources: dict = {}
    counts = {SOURCE_POLYGON: 0, SOURCE_POLYGON_INTRADAY: 0, SOURCE_POLYGON_PREVDAY: 0,
              SOURCE_YAHOO: 0, SOURCE_CARRY: 0, "seed": 0, "unpriced": 0,
              "polygon_close_bar_missing": 0}

    def _accept(obs: Optional[dict]) -> bool:
        """Bind an observation dict to the loop's row fields if it is age-eligible."""
        nonlocal px, src, stale, observed, basis, time_kind, close_qualified, extra
        if obs is None:
            return False
        age = _bounded_age(asof, obs.get("observed_asof"))
        if age is None:
            return False
        px, src, stale = obs["price"], obs["source"], age
        observed = obs.get("observed_asof")
        basis, time_kind, close_qualified = obs["basis"], obs["time_kind"], obs["close_qualified"]
        if obs.get("adjusted_through") is not None:
            extra["adjusted_through"] = obs["adjusted_through"]
        return True

    for raw in symbols or []:
        sym = (raw or "").upper().strip()
        if not sym or sym in prices:
            continue

        px: Optional[float] = None
        src: Optional[str] = None
        stale: Optional[int] = None
        observed: Optional[str] = None
        basis: Optional[str] = None
        time_kind: Optional[str] = None
        close_qualified = False
        retrieved_at: Optional[str] = now_iso
        extra: dict = {}

        if sym in seed:
            px, src, stale = float(seed[sym]), "seed", 0
            observed, basis, time_kind, close_qualified = asof, "unknown", "seed", False
        if px is None:
            try:
                if pfn is not None:
                    v = pfn(sym)
                else:
                    v, bar_missing = _polygon_observation_detail(sym, asof, now=now)
                    if bar_missing:
                        counts["polygon_close_bar_missing"] += 1
            except Exception:  # noqa: BLE001 — a dead feed degrades to the next source (P2)
                v = None
            _accept(_coerce_observation(v, SOURCE_POLYGON, asof))
        if px is None:
            try:
                v = yfn(sym, asof)
            except Exception:  # noqa: BLE001
                v = None
            _accept(_coerce_observation(v, SOURCE_YAHOO, asof))
        if px is None:                                   # carry the last good mark forward (P2)
            c = carry.get(sym)
            if isinstance(c, dict) and c.get("price") and c["price"] > 0:
                d = _days_between(asof, c.get("asof"))
                if d is not None and 0 <= d <= _stale_max_days():
                    px, src, stale = float(c["price"]), SOURCE_CARRY, d
                    observed = str(c.get("asof"))[:10]
                    basis = c.get("basis") or "unknown"
                    time_kind = "carry"
                    close_qualified = False
                    retrieved_at = c.get("retrieved_at") or None

        if px is None or px <= 0:                        # genuinely unpriceable — leave UNPRICED
            counts["unpriced"] += 1
            sources[sym] = {"source": None, "price": None, "stale_days": None,
                            "observed_asof": None, "retrieved_at": now_iso,
                            "basis": None, "time_kind": None, "close_qualified": False}
            continue

        prices[sym] = px
        row = {"source": src, "price": round(px, 6), "stale_days": stale,
               "observed_asof": observed, "retrieved_at": retrieved_at,
               "basis": basis, "time_kind": time_kind, "close_qualified": close_qualified}
        row.update(extra)
        sources[sym] = row
        counts[src] = counts.get(src, 0) + 1
        # refresh the carry ONLY from an official live/seed row, and only monotonically in
        # observed_asof (contract G): never from an intraday/prevday print (not close-grade,
        # and its observation date is not the mark's), never from a carry (that would let a
        # stale mark live forever by resetting its own asof), and a replay whose observation is
        # older than what is stored must not move the store backward.
        if src in (SOURCE_POLYGON, SOURCE_YAHOO, "seed"):
            stored = carry.get(sym)
            stored_d = _days_between(observed, stored.get("asof")) if isinstance(stored, dict) else None
            if not isinstance(stored, dict) or stored_d is None or stored_d >= 0:
                carry[sym] = {"price": round(px, 6), "asof": observed, "source": src,
                              "basis": basis, "retrieved_at": now_iso}

    result = {"as_of": asof, "prices": prices, "sources": sources, "counts": counts}
    if persist:
        _save_carry(carry)
        try:
            _MARKS_DIR.mkdir(parents=True, exist_ok=True)
            (_MARKS_DIR / f"{asof}.json").write_text(
                json.dumps({"as_of": asof, "sources": sources, "counts": counts,
                            "ts": now_iso},
                           indent=2, default=str))
        except Exception:  # noqa: BLE001
            pass
    return result


def mark_one(symbol: str, asof: str, **kw) -> Optional[float]:
    """Single-symbol convenience — the ONE price for `symbol` (or None if unpriceable). Used by the
    injection seam in self_directed so its book finally reads the same mark every other book does."""
    kw.setdefault("persist", False)
    return mark_symbols([symbol], asof, **kw)["prices"].get((symbol or "").upper().strip())


def prices_for(symbols: Iterable[str], asof: str, **kw) -> dict:
    """Just the {SYMBOL: usd_price} union dict — the common shape the NAV writers consume."""
    return mark_symbols(symbols, asof, **kw)["prices"]
