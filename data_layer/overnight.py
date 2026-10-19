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

import json
import math
import re
import time
from datetime import datetime, timezone

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
        try:
            parsed = float(value)
        except (OverflowError, ValueError):
            return None
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


_LIVE_QUALITY_KEYS = frozenset({
    "classification", "source_vendor", "source_receipt_id",
    "source_observed_at_utc", "dataos_identity_admitted",
    "source_rights_admitted", "realtime_venue_admitted", "risk_qualified",
})
_QUALIFIED_RISK_GROUPS = ("us_futures", "international", "vol")


def _host_live_source_admitted(_observation: dict) -> bool:
    """Default deny until the EXISTING Data OS authority binds the true source.

    The verifier MUST bind the COMPLETE observation (venue symbols, returns,
    risk values, source time and receipt), not only claimed quality metadata.
    A JSON risk_qualified or live flag is not an attested grant. Production
    has no enrolled intraday source or rights owner for this consumer yet.
    Do not replace this with an environment toggle, model-provided metadata,
    unchecked local files, or a duplicate data-licensing authority.
    """
    return False


def qualifies_live_risk(t: dict | None) -> bool:
    """One fail-closed admission decision shared by Brain watch and materiality.

    Unlike the pure risk classifier, this concerns data provenance and permitted
    use. A future installed upstream must furnish a separately verified,
    admitted source receipt; until then all real provider packets refuse. Even
    under a synthetic test-owned host verdict, clock and exact risk/venue
    content must satisfy this contract.
    """
    if not isinstance(t, dict) or t.get("live") is not True:
        return False
    quality = t.get("source_quality")
    if not isinstance(quality, dict) or frozenset(quality) != _LIVE_QUALITY_KEYS:
        return False
    if quality.get("classification") != "LIVE_QUALIFIED":
        return False
    for key in ("dataos_identity_admitted", "source_rights_admitted",
                "realtime_venue_admitted", "risk_qualified"):
        if quality.get(key) is not True:
            return False
    vendor = quality.get("source_vendor")
    receipt = quality.get("source_receipt_id")
    if (not isinstance(vendor, str)
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]{3,79}", vendor) is None
            or not isinstance(receipt, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{15,127}", receipt) is None):
        return False
    observed = quality.get("source_observed_at_utc")
    if not isinstance(observed, str) or len(observed) > 40:
        return False
    try:
        source_clock = datetime.fromisoformat(observed.replace("Z", "+00:00"))
        if source_clock.tzinfo is None or source_clock.utcoffset() is None:
            return False
        age_s = (datetime.now(timezone.utc)
                 - source_clock.astimezone(timezone.utc)).total_seconds()
        if not -30 <= age_s <= _TTL:
            return False
    except (TypeError, ValueError, OverflowError):
        return False

    groups = t.get("groups")
    if not isinstance(groups, dict) or not set(groups) <= set(GROUPS):
        return False
    observed_risk_rows = 0
    for group, rows in groups.items():
        if not isinstance(rows, list):
            return False
        permitted = {symbol for symbol, _label in GROUPS[group]}
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                return False
            ticker = row.get("ticker")
            if not isinstance(ticker, str) or ticker not in permitted or ticker in seen:
                return False
            seen.add(ticker)
            change = row.get("change_pct")
            if change is None and group not in _QUALIFIED_RISK_GROUPS:
                # Supplemental display-only observations can be absent; the
                # formatter must then omit them rather than claiming a move.
                continue
            if type(change) not in (int, float):
                return False
            try:
                percentage = float(change)
            except (OverflowError, ValueError):
                return False
            # The same input may be presented in the Brain prompt (FX,
            # commodities and crypto included). Never format NaN/Inf or a
            # physically impossible return as a verified real-time move.
            if not math.isfinite(percentage) or not -100 <= percentage <= 1000:
                return False
            if group in _QUALIFIED_RISK_GROUPS:
                if group == "vol" and ticker != "^VIX":
                    return False
                observed_risk_rows += 1
    if not observed_risk_rows:
        return False
    expected = risk_read(groups)
    if (expected["state"] == "unknown" or
            any(type(value) in (int, float) and not math.isfinite(value)
                for value in (expected["futures_avg_pct"],
                              expected["intl_avg_pct"],
                              expected["vix_change_pct"])) or
            t.get("risk") != expected):
        return False

    # Existing, currently unimplemented host owner must authenticate the
    # COMPLETE observed body against its independently retained source/usage
    # receipt. Checking metadata alone would permit substituted prices with
    # the same receipt. Synthetic tests can inject this host verdict only.
    try:
        return _host_live_source_admitted(t) is True
    except Exception:
        return False


_MAX_VERIFIED_OBSERVATION_BYTES = 32768


def _bounded_observation_json(observation: dict | None) -> str | None:
    """Bound traversal BEFORE JSON expansion, then stream one closed-size blob.

    Fail closed on cycles, shared mutable container aliases, pathological
    nesting, huge strings/numbers, untyped scalars or oversized output. A
    32 KiB *post-hoc* check of json.dumps alone permits exponential expansion
    of shared graphs before authentication and is not a resource bound.
    """
    if type(observation) is not dict:
        return None
    seen: set[int] = set()
    count = 0

    def preflight(value: object, depth: int) -> bool:
        nonlocal count
        count += 1
        if count > 512 or depth > 12:
            return False
        kind = type(value)
        if kind in (dict, list):
            if id(value) in seen or len(value) > 64:
                return False
            seen.add(id(value))
            if kind is dict:
                return all(
                    type(key) is str and len(key) <= 128
                    and preflight(item, depth + 1)
                    for key, item in value.items()
                )
            return all(preflight(item, depth + 1) for item in value)
        if kind is str:
            return len(value) <= 8192
        if kind is int:
            return value.bit_length() <= 8192
        if kind is float:
            return math.isfinite(value)
        return kind is bool or value is None

    if not preflight(observation, 0):
        return None
    try:
        encoder = json.JSONEncoder(
            sort_keys=True, ensure_ascii=True, allow_nan=False,
            separators=(",", ":"),
        )
        chunks = []
        size = 0
        for chunk in encoder.iterencode(observation):
            size += len(chunk)  # ensure_ascii ensures one byte per character
            if size > _MAX_VERIFIED_OBSERVATION_BYTES:
                return None
            chunks.append(chunk)
        return "".join(chunks)
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError):
        return None


def qualified_live_snapshot(observation: dict | None) -> dict | None:
    """Return a private, detached source-authenticated JSON observation.

    The incumbent Data OS host owns full-body and rights verification. It
    receives its own temporary decode, NEVER the reference returned to trading
    or output consumers. Detect mutations made during the verifier call, and
    account for slow verification against a monotonic elapsed-time window.
    No new credential, lease or second authorization plane is introduced.
    """
    tick_start = time.monotonic()
    wall_start = datetime.now(timezone.utc)
    encoded = _bounded_observation_json(observation)
    if encoded is None:
        return None
    try:
        verifier_body = json.loads(encoded)
        if not qualifies_live_risk(verifier_body):
            return None
        if _bounded_observation_json(verifier_body) != encoded:
            # A verifier cannot amend the approved body, even after returning
            # a positive verdict. A retained verifier reference is not reused.
            return None
        source_clock = datetime.fromisoformat(
            verifier_body["source_quality"]["source_observed_at_utc"].replace(
                "Z", "+00:00"
            )
        ).astimezone(timezone.utc)
        elapsed = time.monotonic() - tick_start
        age = (wall_start - source_clock).total_seconds() + max(0.0, elapsed)
        if not math.isfinite(age) or not -30 <= age <= _TTL:
            return None
        return json.loads(encoded)  # new object with no verifier-side aliases
    except (TypeError, ValueError, OverflowError, RecursionError, KeyError):
        return None


def _monotonic_clock() -> float:
    """Elapsed-time clock for an ephemeral observation, never a market clock."""
    return time.monotonic()


def _initial_source_deadline(
    qualified: dict | None, first_wall_utc: datetime,
    first_monotonic: float,
) -> float | None:
    """Freeze expiry from FIRST observation admission, not a later recheck.

    A monotonic deadline cannot grow if the wall clock is adjusted backwards
    while a model prompt is prepared. This is a short-lived, in-memory usage
    fence, NOT a source identity or a second rights authority.
    """
    if not isinstance(qualified, dict):
        return None
    try:
        if (first_wall_utc.tzinfo is None
                or first_wall_utc.utcoffset() is None
                or not math.isfinite(float(first_monotonic))):
            return None
        observed = qualified["source_quality"]["source_observed_at_utc"]
        source_time = datetime.fromisoformat(
            observed.replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        age = (first_wall_utc.astimezone(timezone.utc) - source_time).total_seconds()
        if not math.isfinite(age) or not -30 <= age <= _TTL:
            return None
        return float(first_monotonic) + _TTL - age
    except (AttributeError, TypeError, KeyError, ValueError, OverflowError):
        return None


def is_material(t: dict | None = None) -> bool:
    """Deterministic tripwire (free — no LLM): is the overnight tape moving enough to warrant a Brain
    reconsideration? True when the distilled risk read is 'elevated' or 'stressed'."""
    t = t if t is not None else tape()
    # Compare materiality on the SAME verified private data object. If the
    # source callback mutates its original dict during or after admission,
    # it cannot substitute a risk state after this decision is verified.
    qualified = qualified_live_snapshot(t)
    return (qualified is not None
            and qualified["risk"]["state"] in ("elevated", "stressed"))


def brief(t: dict | None = None) -> str:
    """A one-line human/Brain summary of a source-verified, detached tape."""
    t = t if t is not None else tape()
    qualified = qualified_live_snapshot(t)
    if qualified is None:
        return "Overnight tape unavailable (historical closes or unqualified evidence are not live risk)."
    risk = qualified["risk"]
    return f"Overnight tape: risk {risk.get('state')} — " + "; ".join(risk.get("reasons") or [])


def clear_cache() -> None:
    """Drop the memo (tests / a forced refresh)."""
    global _cache, _cache_ts
    _cache, _cache_ts = None, 0.0


def public_tape(observation: dict | None) -> dict:
    """Bound model/dashboard output to the SAME admission used by decisions.

    A future replacement feed cannot label its own data live merely by
    supplying matching quality flags. Original Yahoo daily orientation may
    remain visible as historical-only, with its risk forced to UNKNOWN.
    A rejected claimed-live packet exposes no unqualified prices or receipts.
    """
    qualified = qualified_live_snapshot(observation)
    if qualified is not None:
        # The host verified the COMPLETE detached body (including its receipt
        # and rights) before we make a separate, tightly CLOSED public view.
        # Never export the raw source packet, receipt identifier, provider
        # diagnostics, arbitrary row metadata or source-controlled labels to
        # the dashboard or model tool. The true source verifier, not claimed
        # booleans, must separately establish permitted downstream use.
        groups: dict[str, list[dict]] = {}
        for group, catalog in GROUPS.items():
            labels = dict(catalog)
            displayed: list[dict] = []
            for row in qualified["groups"].get(group, []):
                ticker = row["ticker"]
                price = row.get("price")
                try:
                    price = (float(price)
                             if type(price) in (int, float) else None)
                    if (price is not None
                            and (not math.isfinite(price)
                                 or not 0 <= price <= 1e9)):
                        price = None
                except (OverflowError, ValueError, TypeError):
                    price = None
                change = row.get("change_pct")
                displayed.append({
                    "ticker": ticker, "name": labels[ticker],
                    "price": price,
                    "change_pct": float(change) if change is not None else None,
                })
            groups[group] = displayed
        source = qualified["source_quality"]
        observed_at = source["source_observed_at_utc"]
        return {
            "as_of": observed_at,
            "as_of_kind": "source_observed_at",
            "groups": groups,
            "risk": risk_read(groups),
            "n_symbols": sum(len(rows) for rows in groups.values()),
            "live": True,
            "source_quality": {
                "classification": "LIVE_QUALIFIED",
                "source_vendor": source["source_vendor"],
                "source_observed_at_utc": observed_at,
                "risk_qualified": True,
            },
        }

    risk = risk_read({})
    quality = (observation or {}).get("source_quality") if isinstance(observation, dict) else None
    daily = (
        isinstance(observation, dict)
        and observation.get("live") is False
        and observation.get("as_of_kind") == "retrieved_at_not_source_observed_at"
        and quality == {
            "classification": "EOD_NOT_LIVE",
            "source": "yahoo_daily_history",
            "interval": "1d",
            "risk_qualified": False,
        }
    )
    if daily:
        groups = {}
        for group, rows in (observation.get("groups") or {}).items():
            if group not in GROUPS or not isinstance(rows, list):
                continue
            names = dict(GROUPS[group])
            sanitized = []
            seen = set()
            for row in rows:
                if not isinstance(row, dict):
                    continue
                ticker = row.get("ticker")
                if not isinstance(ticker, str) or ticker not in names or ticker in seen:
                    continue
                seen.add(ticker)
                change = row.get("change_pct")
                if change is not None:
                    if type(change) not in (int, float):
                        continue
                    try:
                        value = float(change)
                    except (OverflowError, ValueError):
                        continue
                    if not math.isfinite(value) or not -100 <= value <= 1000:
                        continue
                price = row.get("price")
                if type(price) not in (int, float):
                    price = None
                else:
                    try:
                        price = float(price)
                    except (OverflowError, ValueError):
                        price = None
                    if price is not None and not math.isfinite(price):
                        price = None
                sanitized.append({
                    "ticker": ticker, "name": names[ticker],
                    "price": price, "change_pct": change,
                })
            groups[group] = sanitized
        as_of = observation.get("as_of")
        return {
            "as_of": as_of if isinstance(as_of, str) and len(as_of) <= 48 else None,
            "as_of_kind": "retrieved_at_not_source_observed_at",
            "groups": groups,
            "risk": risk,
            "n_symbols": sum(len(rows) for rows in groups.values()),
            "live": False,
            "source_quality": {
                "classification": "EOD_NOT_LIVE",
                "source": "yahoo_daily_history",
                "interval": "1d",
                "risk_qualified": False,
            },
        }
    return {
        "as_of": None,
        "as_of_kind": "unqualified_no_observation",
        "groups": {}, "risk": risk, "n_symbols": 0, "live": False,
        "source_quality": {
            "classification": "UNQUALIFIED_FOR_RISK",
            "risk_qualified": False,
        },
    }
