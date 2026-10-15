"""Cross-asset session-change overlay — NOT a qualified live overnight feed.

The incumbent Yahoo downloader requests daily history (interval=1d). Its
close-to-close changes can be displayed as indicative historical information,
but neither fetching it at night nor caching it every five minutes creates an
overnight quote timestamp or a real-time risk observation. Therefore the
operational tape currently reports live=False and risk UNKNOWN, even when daily
bars are present. An independently admitted intraday source with exact venue
clock and data rights is required before the automatic overnight Brain tripwire
may be armed; the downloader does not invent that authority.

No data or invalid data is similarly UNKNOWN, never implicitly CALM. These
helpers avoid provider-network work in pure risk classification and keep the
unchanged five-minute read cache for historical indicative prices."""

from __future__ import annotations

import math
import time

# The overnight universe, grouped (Yahoo symbols + display names).
GROUPS: dict[str, list[tuple[str, str]]] = {
    "us_futures":   [("ES=F", "S&P 500 fut"), ("NQ=F", "Nasdaq-100 fut"),
                     ("YM=F", "Dow fut"), ("RTY=F", "Russell 2000 fut")],
    "international": [("^N225", "Nikkei 225"), ("^HSI", "Hang Seng"), ("000001.SS", "Shanghai"),
                     ("^KS11", "KOSPI"), ("^STOXX50E", "Euro Stoxx 50"), ("^GDAXI", "DAX"), ("^FTSE", "FTSE 100")],
    "fx_rates":     [("DX-Y.NYB", "US Dollar"), ("JPY=X", "USD/JPY"), ("^TNX", "10Y yield")],
    "vol":          [("^VIX", "VIX")],
    "commodities":  [("CL=F", "WTI crude"), ("GC=F", "Gold")],
    "crypto":       [("BTC-USD", "Bitcoin")],
}
ALL_SYMBOLS = [s for g in GROUPS.values() for s, _ in g]

_TTL = 300.0           # seconds — cache the tape for ~5 min
_cache: dict | None = None
_cache_ts: float = 0.0


def _fetch_changes(symbols: list[str]) -> dict[str, dict]:
    """{symbol: {price, prev, change_pct}} from ONE batched yf.download (last ~5 daily closes →
    last vs prior session). Best-effort; a missing yfinance / network leaves an empty dict."""
    out: dict[str, dict] = {}
    try:
        import yfinance as yf
        # Explicit daily interval: these are historical session bars, NOT
        # timestamp-qualified overnight quotes. Never infer live risk from them.
        df = yf.download(symbols, period="5d", interval="1d",
                         progress=False, auto_adjust=False, threads=False)
        close = df["Close"]
    except Exception:
        return out
    multi = hasattr(close, "columns")
    cols = list(close.columns) if multi else [symbols[0]]
    for sym in cols:
        try:
            s = (close[sym] if multi else close).dropna()
            if len(s) >= 2:
                last, prev = float(s.iloc[-1]), float(s.iloc[-2])
                out[str(sym)] = {"price": round(last, 4), "prev": round(prev, 4),
                                 "change_pct": round((last / prev - 1) * 100, 2) if prev else None}
            elif len(s) == 1:
                out[str(sym)] = {"price": round(float(s.iloc[-1]), 4), "prev": None, "change_pct": None}
        except Exception:
            continue
    return out


def risk_read(groups: dict) -> dict:
    """Distil available overnight risk signals without treating absence as calm.

    The dashboard and overnight watcher consume this SAME risk assessment.
    Only finite observed changes count as risk evidence. Missing/nonfinite
    futures, international and VIX signals yield UNKNOWN, not an implicit
    risk-on vote. A qualified zero change is still a valid calm observation.
    """
    def finite_change(value):
        if type(value) not in (int, float):
            return None
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None

    def observed(group):
        rows = groups.get(group) or ()
        if not isinstance(rows, (list, tuple)):
            return []
        return [
            change for row in rows if isinstance(row, dict)
            for change in (finite_change(row.get("change_pct")),)
            if change is not None
        ]

    fut = observed("us_futures")
    intl = observed("international")
    vol_rows = groups.get("vol") or ()
    if not isinstance(vol_rows, (list, tuple)):
        vol_rows = ()
    vix_chg = next(
        (finite_change(row.get("change_pct"))
         for row in vol_rows if isinstance(row, dict) and row.get("ticker") == "^VIX"),
        None,
    )
    fut_avg = round(sum(fut) / len(fut), 2) if fut else None
    intl_avg = round(sum(intl) / len(intl), 2) if intl else None
    intl_down = sum(1 for x in intl if x < 0)

    has_risk_evidence = bool(fut or intl or vix_chg is not None)
    state = "unknown" if not has_risk_evidence else "calm"
    if ((fut_avg is not None and fut_avg <= -1.5)
            or (intl and intl_avg is not None and intl_avg <= -1.5 and intl_down >= max(1, int(0.6 * len(intl))))
            or (vix_chg is not None and vix_chg >= 12)):
        state = "stressed"
    elif ((fut_avg is not None and fut_avg <= -0.6)
          or (intl and intl_down >= max(1, int(0.6 * len(intl))))
          or (vix_chg is not None and vix_chg >= 6)):
        state = "elevated"

    reasons = []
    if fut_avg is not None:
        reasons.append(f"US futures avg {fut_avg:+.2f}%")
    if intl_avg is not None:
        reasons.append(f"{intl_down}/{len(intl)} intl mkts down (avg {intl_avg:+.2f}%)")
    if vix_chg is not None:
        reasons.append(f"VIX {vix_chg:+.1f}%")
    return {"state": state, "futures_avg_pct": fut_avg, "intl_avg_pct": intl_avg,
            "intl_down": intl_down, "intl_n": len(intl), "vix_change_pct": vix_chg,
            "reasons": reasons or ["no qualified overnight risk signals"]}


def tape(force: bool = False) -> dict:
    """Indicate Yahoo daily session changes; refuse to call them live overnight.

    The unchanged grouping is useful for historical orientation, but daily
    bars have no independently qualified intraday timestamp or source rights.
    The overnight Brain tripwire consumes only the conservative risk field.
    """
    global _cache, _cache_ts
    now = time.monotonic()
    if not force and _cache is not None and (now - _cache_ts) < _TTL:
        return _cache
    changes = _fetch_changes(ALL_SYMBOLS)
    groups: dict[str, list[dict]] = {}
    for g, syms in GROUPS.items():
        rows = []
        for sym, name in syms:
            c = changes.get(sym)
            if c:
                rows.append({"ticker": sym, "name": name,
                             "price": c.get("price"), "change_pct": c.get("change_pct")})
        groups[g] = rows
    from datetime import datetime, timezone
    # as_of remains the retrieval clock for older dashboards, NOT the
    # source-observation timestamp. Do not qualify a historical close as live.
    out = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "as_of_kind": "retrieved_at_not_source_observed_at",
        "groups": groups,
        "risk": risk_read({}),
        "n_symbols": len(changes),
        "live": False,
        "source_quality": {
            "classification": "EOD_NOT_LIVE",
            "source": "yahoo_daily_history",
            "interval": "1d",
            "risk_qualified": False,
        },
    }
    _cache, _cache_ts = out, now
    return out


def is_material(t: dict | None = None) -> bool:
    """Deterministic tripwire (free — no LLM): is the overnight tape moving enough to warrant a Brain
    reconsideration? True when the distilled risk read is 'elevated' or 'stressed'."""
    t = t if t is not None else tape()
    # A confirmed non-live source may carry indicative historical changes.
    # Those changes must never become an actionable overnight tripwire.
    return (t.get("live") is not False
            and (t.get("risk") or {}).get("state") in ("elevated", "stressed"))


def brief(t: dict | None = None) -> str:
    """A one-line human/Brain summary of the overnight tape (for prompts + logs)."""
    t = t if t is not None else tape()
    if not t.get("live"):
        return "Overnight tape unavailable (historical closes are not qualified live risk)."
    risk = t.get("risk") or {}
    return f"Overnight tape: risk {risk.get('state')} — " + "; ".join(risk.get("reasons") or [])


def clear_cache() -> None:
    """Drop the memo (tests / a forced refresh)."""
    global _cache, _cache_ts
    _cache, _cache_ts = None, 0.0
