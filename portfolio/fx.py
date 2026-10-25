"""Currency conversion for the multi-currency China book — everything marked in USD.

The all-China book holds three venues that quote in three currencies:
  * mainland A-shares (``*.SS`` / ``*.SZ``) quote in **CNY**
  * Hong Kong (``*.HK``) quotes in **HKD**
  * US-listed China ADRs (no suffix) quote in **USD**

The paper account keeps ONE NAV, so every local price is converted to USD before it ever
touches cash/positions. This module owns that conversion: it resolves a ticker's currency
from its suffix and the live USD rate from (1) the vendored macro yahoo FX store, (2) the
macro forex snapshot, then (3) a static peg/recent fallback so marking never fails offline.

Rates are quoted the market way (USD-per-1-USD in the foreign unit, i.e. CNY-per-USD ≈ 7),
and ``to_usd`` divides by them. Pure-ish + degrade-never-raise; results are memoised per
process (FX moves slowly relative to a once-daily mark)."""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from . import fx_evidence as _fx_evidence
from .price_evidence import call_with_evidence as _call_with_evidence

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_V = _ROOT / "vendor" / "macro"

# Static fallbacks — foreign units PER 1 USD. Used only when no live rate is available.
# CNH offshore yuan and the HKD peg (band 7.75–7.85) are both stable enough that a constant
# is accurate to ~1% for a paper mark; live values override.
_FALLBACK = {"CNY": 7.2, "HKD": 7.80, "USD": 1.0}

# Per-process memo, keyed by currency → (rate, day-it-was-fetched). DATE-keyed so a long-lived
# server (the china_daily cron runs in one persistent process) picks up the nightly FX refresh
# instead of freezing the first rate forever, while a single build still reads a stable rate.
_RATE_CACHE: dict[str, tuple[float, str]] = {}
# Optional provenance is bound to the exact tuple object, never the numeric rate alone.
_RATE_CONTEXT: dict[str, tuple[tuple[float, str], dict | None]] = {}


def _fx_clock():
    try:
        return _fx_evidence.clock()
    except Exception:
        return None


def _observed_call(reader, *args, _evidence=None):
    if _evidence is None:
        return reader(*args)
    return _call_with_evidence(reader, *args, evidence=_evidence)



def currency_of(ticker: str) -> str:
    """The quote currency implied by a ticker's venue suffix."""
    t = (ticker or "").upper().strip()
    if t == "^HSI":
        return "HKD"
    if t.endswith(".SS") or t.endswith(".SZ"):
        return "CNY"
    if t.endswith(".HK"):
        return "HKD"
    return "USD"


def market_of(ticker: str) -> str:
    """'A' (mainland A-share), 'HK', or 'US' (incl. ADRs) — by suffix."""
    cur = currency_of(ticker)
    return {"CNY": "A", "HKD": "HK"}.get(cur, "US")


def _from_yahoo_store(symbol: str, *, _evidence=None) -> float | None:
    try:
        from lib import store  # vendored macro lib
        started = _fx_clock() if _evidence is not None else None
        df = store.read("yahoo", symbol)
        returned = _fx_clock() if _evidence is not None else None
        if df is not None and "close" in df.columns and len(df) > 0:
            closes = df["close"].astype(float).dropna()
            v = float(closes.iloc[-1])
            if v > 0:
                try:
                    if _evidence is not None:
                        _fx_evidence.source_context(
                            _evidence, source="yahoo_store", symbol=symbol, rate=v,
                            started=started, returned=returned,
                            bar=closes.index[-1], kind="selected_close_index",
                        )
                except Exception:
                    pass
                return v
            return None
    except Exception as e:  # noqa: BLE001
        log.debug("fx: yahoo %s failed (%s)", symbol, e)
    return None


def _from_forex_snapshot(key: str, *, _evidence=None) -> float | None:
    """Read pairs[KEY].quote from the macro forex snapshot (e.g. 'USDCNH')."""
    for rel in ("data/forex/latest.json", "site/forexdata/latest.json"):
        p = _V / rel
        try:
            if p.exists():
                started = _fx_clock() if _evidence is not None else None
                text = p.read_text()
                returned = _fx_clock() if _evidence is not None else None
                decoded = json.loads(text) or {}
                pairs = decoded.get("pairs") or {}
                rec = pairs.get(key)
                if isinstance(rec, dict):
                    q = rec.get("quote")
                    if q and float(q) > 0:
                        value = float(q)
                        try:
                            if _evidence is not None:
                                pair_label = rec.get("asof")
                                bar = pair_label if pair_label is not None else decoded.get("asof")
                                _fx_evidence.source_context(
                                    _evidence, source="forex_snapshot", symbol=key, rate=value,
                                    started=started, returned=returned, path=rel, source_text=text,
                                    bar=bar, kind="pair_asof" if pair_label is not None else "snapshot_asof",
                                )
                        except Exception:
                            pass
                        return value
        except Exception as e:  # noqa: BLE001
            log.debug("fx: forex snapshot %s/%s failed (%s)", rel, key, e)
    return None


def rate_per_usd(currency: str, *, _evidence=None) -> float:
    """Foreign units per 1 USD for `currency` (CNY≈7.2, HKD≈7.8, USD=1.0). Degrade-safe."""
    cur = (currency or "USD").upper()
    if cur == "USD":
        try:
            if _evidence is not None:
                source = {"source": "identity", "rate": 1.0, "source_bar_label_kind": "not_provided"}
                _fx_evidence.emit(_evidence, _fx_evidence.make_rate(
                    cur, 1.0, source=source, cache_state="not_used",
                ))
        except Exception:
            pass
        return 1.0
    try:
        today = date.today().isoformat()
    except Exception:
        today = ""
    cached = _RATE_CACHE.get(cur)
    if cached is not None and cached[1] == today:
        value = cached[0]
        try:
            if _evidence is not None:
                binding = _RATE_CONTEXT.get(cur)
                context = binding[1] if type(binding) is tuple and len(binding) == 2 and binding[0] is cached else None
                _fx_evidence.emit(_evidence, _fx_evidence.cached_rate(context, cur, value, today))
        except Exception:
            pass
        return value
    selected = None

    def source_read(reader, key):
        nonlocal selected
        # Ordinary marks can populate the cache before a receipt requests context.
        # Capture at that original read; observing a later hit must never reread it.
        observed = {}
        value = _observed_call(reader, key, _evidence=observed)
        selected = observed
        return value

    val: float | None = None
    if cur == "CNY":
        # Existing offshore-yuan proxy policy is unchanged; observation does not qualify it.
        val = source_read(_from_yahoo_store, "CNH=X") or source_read(_from_yahoo_store, "CNY=X") or source_read(_from_forex_snapshot, "USDCNH")
    elif cur == "HKD":
        val = (source_read(_from_yahoo_store, "HKD=X") or source_read(_from_forex_snapshot, "USDHKD")
               or source_read(_from_forex_snapshot, "HKDUSD"))
    if not val or val <= 0:
        val = _FALLBACK.get(cur, 1.0)
        selected = {
            "source": "static_fallback" if cur in _FALLBACK else "unknown_currency_fallback",
            "rate": val, "source_bar_label_kind": "not_provided",
        }
    context = None
    try:
        context = _fx_evidence.make_rate(cur, val, source=selected, cache_day=today)
    except Exception:
        pass
    entry = (val, today)
    _RATE_CACHE[cur] = entry
    try:
        _RATE_CONTEXT[cur] = (entry, context)
        _fx_evidence.emit(_evidence, context)
    except Exception:
        pass
    return val


def to_usd(price_local: float | None, ticker: str, *, _evidence=None) -> float | None:
    """Convert a LOCAL-currency price for `ticker` into USD. None passes through."""
    if price_local is None:
        return None
    try:
        px = float(price_local)
    except (TypeError, ValueError):
        return None
    if px <= 0:
        return None
    cur = currency_of(ticker)
    if cur == "USD":
        return px
    rate = _observed_call(rate_per_usd, cur, _evidence=_evidence)
    return px / rate if rate and rate > 0 else None


def to_cny(price_local: float | None, ticker: str) -> float | None:
    """Convert a LOCAL-currency price for `ticker` into CNY — the China book's base currency.
    A-shares are already CNY; HK (HKD) and US-listed ADRs (USD) convert at the prevailing rate
    (CNY per 1 unit of the local currency = CNY-per-USD ÷ local-per-USD). None passes through."""
    if price_local is None:
        return None
    try:
        px = float(price_local)
    except (TypeError, ValueError):
        return None
    if px <= 0:
        return None
    cur = currency_of(ticker)
    if cur == "CNY":
        return px
    cur_per_usd = rate_per_usd(cur)
    return px * rate_per_usd("CNY") / cur_per_usd if cur_per_usd and cur_per_usd > 0 else None


def usd_to_cny(usd_value: float | None) -> float | None:
    """Convert a USD amount into CNY at the prevailing USD/CNY (offshore CNH) rate. Used to mark the
    China book — whose shared price store returns USD — in its CNY base currency. None passes through."""
    if usd_value is None:
        return None
    try:
        v = float(usd_value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return v * rate_per_usd("CNY")


def usd_to(usd_value: float | None, currency: str, *, _evidence=None) -> float | None:
    """Convert a USD amount into `currency` (CNY / HKD / USD) at the prevailing rate. Generic form of
    usd_to_cny — used to mark a single-currency book (e.g. the HKD HK book or the CNY A-share book)
    whose shared price store returns USD. None / non-positive passes through as None."""
    if usd_value is None:
        return None
    try:
        v = float(usd_value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return v * _observed_call(rate_per_usd, (currency or "USD").upper(), _evidence=_evidence)


def usd_to_hkd(usd_value: float | None) -> float | None:
    """Convert a USD amount into HKD — used to mark the HK book (HKD base) from the USD price store."""
    return usd_to(usd_value, "HKD")


def cny_to_local(cny_value: float | None, ticker: str) -> float | None:
    """Inverse of to_cny: a CNY amount back into the ticker's LOCAL quote currency (for display)."""
    if cny_value is None:
        return None
    try:
        v = float(cny_value)
    except (TypeError, ValueError):
        return None
    cur = currency_of(ticker)
    if cur == "CNY":
        return v
    return v * rate_per_usd(cur) / rate_per_usd("CNY")


def clear_cache() -> None:
    """Drop the per-process rate memo (tests / a fresh FX read)."""
    _RATE_CACHE.clear()
    _RATE_CONTEXT.clear()
