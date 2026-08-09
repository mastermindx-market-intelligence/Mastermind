"""Bounded intelligence plane for the three Mastermind Portfolio Brains.

This module turns Macro Dashboard's published JSON contracts into small, typed,
read-only packets suitable for MCP tools.  It deliberately does *not* expose a
generic path reader: every artifact is named below and ticker-derived paths are
accepted only after strict symbol validation.  Prophet, Oracle, flow, and
technical artifacts remain evidence/context; none of them acquires trade or
sizing authority here.

All public functions are synchronous and fail soft.  Missing, malformed, or
stale data is reported explicitly rather than being silently promoted to a
current signal.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_V = _ROOT / "vendor" / "macro"
_URL_BASE = "https://www.mastermind-x.com"
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,11}$")

_DAILY_MAX_AGE = 4
_WEEKLY_MAX_AGE = 9
_INTRADAY_MAX_AGE = 1
_MAX_LIMIT = 20


def _clamp_limit(value: int | None, default: int = 8) -> int:
    try:
        return max(1, min(int(value if value is not None else default), _MAX_LIMIT))
    except (TypeError, ValueError):
        return default


def _ticker(value: str | None) -> str | None:
    symbol = str(value or "").upper().strip()
    return symbol if _TICKER_RE.fullmatch(symbol) else None


def _asof_value(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("as_of", "asof", "date", "generated_utc", "generated_at", "produced_at", "built"):
        value = payload.get(key)
        if value is not None and not isinstance(value, (dict, list, bool)):
            return str(value)
    return None


def _age_days(value: str | None) -> int | None:
    if not value:
        return None
    try:
        stamp = str(value).replace("Z", "+00:00")
        if "T" in stamp or " " in stamp:
            parsed = datetime.fromisoformat(stamp.replace(" ", "T"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return (datetime.now(UTC).date() - parsed.date()).days
        day = stamp[:10]
        if len(day) == 7:  # monthly contracts (for example factor seasonality)
            day += "-01"
        return (datetime.now(UTC).date() - date.fromisoformat(day)).days
    except (TypeError, ValueError):
        return None


def _health(
    path: Path,
    artifact: str,
    *,
    payload: Any = None,
    parse_ok: bool | None = None,
    max_age_days: int = _DAILY_MAX_AGE,
    cadence: str = "nightly",
    authority: str = "context",
) -> dict:
    exists = path.is_file()
    if parse_ok is None:
        parse_ok = exists and payload is not None
    as_of = _asof_value(payload) if parse_ok else None
    age = _age_days(as_of)
    stale = bool(age is not None and age > max_age_days)
    if not exists:
        status = "missing"
    elif not parse_ok:
        status = "malformed"
    elif age is None:
        status = "undated"
    elif stale:
        status = "stale"
    else:
        status = "fresh"
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat() if exists else None
    except OSError:
        mtime = None
    return {
        "artifact": artifact,
        "available": bool(exists and parse_ok),
        "status": status,
        "as_of": as_of,
        "age_days": age,
        "max_age_days": max_age_days,
        "stale": stale,
        "cadence": cadence,
        "authority": authority,
        "execution_authority": False,
        "file_mtime_utc": mtime,
    }


def _read_path(
    path: Path,
    artifact: str,
    *,
    max_age_days: int = _DAILY_MAX_AGE,
    cadence: str = "nightly",
    authority: str = "context",
) -> tuple[Any, dict]:
    if not path.is_file():
        return None, _health(
            path,
            artifact,
            parse_ok=False,
            max_age_days=max_age_days,
            cadence=cadence,
            authority=authority,
        )
    try:
        payload = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, _health(
            path,
            artifact,
            parse_ok=False,
            max_age_days=max_age_days,
            cadence=cadence,
            authority=authority,
        )
    return payload, _health(
        path,
        artifact,
        payload=payload,
        parse_ok=True,
        max_age_days=max_age_days,
        cadence=cadence,
        authority=authority,
    )


def _read_vendor(
    rel: str,
    *,
    max_age_days: int = _DAILY_MAX_AGE,
    cadence: str = "nightly",
    authority: str = "context",
) -> tuple[Any, dict]:
    # ``rel`` is supplied only by constants or by the validated ticker branches below.
    return _read_path(
        _V / rel,
        rel,
        max_age_days=max_age_days,
        cadence=cadence,
        authority=authority,
    )


def _source_ref(health: dict) -> dict:
    """Token-light provenance/freshness projection for nested packets."""
    return {key: health.get(key) for key in (
        "artifact", "available", "status", "as_of", "age_days", "authority",
        "execution_authority",
    )}


def _technical_source_ref(health: dict) -> dict:
    return {key: health.get(key) for key in (
        "artifact", "status", "as_of", "authority",
    )}


# User-visible surfaces and their fixed local contracts.  Several surfaces have
# more than one supporting contract; availability is intentionally reported per
# artifact rather than hidden behind a single optimistic boolean.
_SURFACES: tuple[dict, ...] = (
    {"id": "sector_central", "title": "Sector Central", "page": "sector_central.html#",
     "artifacts": (("site/sectordata/sector_central.json", _DAILY_MAX_AGE, "nightly", "context"),)},
    {"id": "intelligence_hub", "title": "Intelligence Hub", "page": "intelligence_hub.html",
     "artifacts": (("site/intelligence/briefing.json", _DAILY_MAX_AGE, "nightly", "context"),)},
    {"id": "foresight", "title": "Foresight", "page": "foresight.html",
     "artifacts": (("site/basketdata/foresight_cascade.json", _DAILY_MAX_AGE, "nightly", "context"),)},
    {"id": "radar", "title": "Radar", "page": "radar.html",
     "artifacts": (("site/basketdata/radar_enriched.json", _DAILY_MAX_AGE, "nightly", "context"),)},
    {"id": "state_of_themes", "title": "State of Themes", "page": "state_of_themes.html",
     "artifacts": (("site/basketdata/baskets.json", _DAILY_MAX_AGE, "nightly", "context"),
                    ("site/marketdata/themes_heatmap.json", _DAILY_MAX_AGE, "nightly", "display"))},
    {"id": "etfs", "title": "ETF and Fund Flows", "page": "etfs.html",
     "artifacts": (("site/basketdata/etf_pulse.json", _DAILY_MAX_AGE, "nightly", "context"),)},
    {"id": "macro_context", "title": "Macro Context", "page": "macro_context.html",
     "artifacts": (("data/regime/latest.json", _DAILY_MAX_AGE, "nightly", "context"),)},
    {"id": "movers", "title": "Movers", "page": "movers.html",
     "artifacts": (("site/marketdata/sp500_heatmap.json", _INTRADAY_MAX_AGE, "intraday", "display"),)},
    {"id": "intraday_flow", "title": "Intraday Flow", "page": "intraday_flow.html",
     "artifacts": (("site/basketdata/flow.json", _INTRADAY_MAX_AGE, "intraday", "display"),
                    ("site/basketdata/trade_flows.json", _INTRADAY_MAX_AGE, "intraday", "display"))},
    {"id": "options", "title": "Options", "page": "options.html",
     "artifacts": (("site/options_ivspread/latest.json", _INTRADAY_MAX_AGE, "intraday", "display"),
                    ("site/options_skew/latest.json", _INTRADAY_MAX_AGE, "intraday", "display"),
                    ("site/basketdata/options_witness.json", _DAILY_MAX_AGE, "nightly", "display"))},
    {"id": "confluence_screener", "title": "Confluence Screener", "page": "confluence_screener.html",
     "artifacts": (("site/premiumdata/confluence_screener.json", _DAILY_MAX_AGE, "nightly", "context"),
                    ("site/factordata/tech_confluence.json", _DAILY_MAX_AGE, "nightly", "context"))},
    {"id": "stock_seasonality", "title": "Stock Seasonality", "page": "stock_seasonality.html",
     "artifacts": (("site/factordata/factor_seasonality.json", _WEEKLY_MAX_AGE, "weekly", "context"),)},
    {"id": "prophet", "title": "US Prophet", "page": "prophet/index.html",
     "artifacts": (("site/prophet/index.json", _DAILY_MAX_AGE, "nightly", "display"),)},
    {"id": "neural_web", "title": "Neural Web Portfolio Context", "page": "neural_web.html",
     "artifacts": (("site/neuralwebdata/mastermind_context.json", _DAILY_MAX_AGE, "nightly", "context"),)},
    {"id": "golden_oracle", "title": "Golden Oracle", "page": "technical_lab.html",
     "artifacts": (("site/factordata/contracts/golden_signals.json", _WEEKLY_MAX_AGE, "contract", "reference"),
                    ("site/basketdata/oracle_state.json", _DAILY_MAX_AGE, "nightly", "display"),
                    ("site/basketdata/oracle_reversion_state.json", _DAILY_MAX_AGE, "nightly", "display"))},
    {"id": "technical_lab", "title": "Technical Lab and Terminal", "page": "technical_lab.html",
     "artifacts": (("site/factordata/tech_lab.json", _DAILY_MAX_AGE, "nightly", "context"),
                    ("site/factordata/signal_gate.json", _DAILY_MAX_AGE, "nightly", "context"))},
)


def context_catalog() -> dict:
    """Return the allowlisted Macro surface catalog with per-contract health.

    The result is intentionally metadata-only.  Callers use the other typed
    functions for content and cannot turn catalog paths into arbitrary reads.
    """
    surfaces: list[dict] = []
    for spec in _SURFACES:
        artifacts = []
        for rel, max_age, cadence, authority in spec["artifacts"]:
            _, health = _read_vendor(
                rel,
                max_age_days=max_age,
                cadence=cadence,
                authority=authority,
            )
            artifacts.append(_source_ref(health))
        available = [a for a in artifacts if a["available"]]
        if any(a["status"] == "fresh" for a in available):
            status = "fresh"
        elif any(a["status"] == "undated" for a in available):
            status = "undated"
        elif available:
            status = "stale"
        elif any(a["status"] == "malformed" for a in artifacts):
            status = "malformed"
        else:
            status = "missing"
        surfaces.append({
            "id": spec["id"],
            "title": spec["title"],
            "url": f"{_URL_BASE}/{spec['page']}",
            "status": status,
            "available": bool(available),
            "artifacts": artifacts,
        })
    return {
        "schema": "mastermind.portfolio_intelligence.catalog/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "policy": {
            "read_only": True,
            "bounded_allowlist": True,
            "arbitrary_filesystem_access": False,
            "signals_are_context_not_orders": True,
        },
        "surfaces": surfaces,
    }


def _bounded_value(
    value: Any,
    *,
    list_limit: int = 6,
    dict_limit: int = 14,
    str_limit: int = 220,
    max_depth: int = 4,
    depth: int = 0,
) -> Any:
    """Recursively project a published contract without leaking unbounded bulk."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _short(value, str_limit)
    if depth >= max_depth:
        if isinstance(value, dict):
            return {"_nested_keys_omitted": len(value)}
        if isinstance(value, (list, tuple)):
            return [f"<{len(value)} nested rows omitted>"]
        return _short(str(value), str_limit)
    if isinstance(value, dict):
        items = list(value.items())
        out = {
            str(key): _bounded_value(
                child,
                list_limit=list_limit,
                dict_limit=dict_limit,
                str_limit=str_limit,
                max_depth=max_depth,
                depth=depth + 1,
            )
            for key, child in items[:dict_limit]
        }
        if len(items) > dict_limit:
            out["_keys_omitted"] = len(items) - dict_limit
        return out
    if isinstance(value, (list, tuple)):
        return [
            _bounded_value(
                child,
                list_limit=list_limit,
                dict_limit=dict_limit,
                str_limit=str_limit,
                max_depth=max_depth,
                depth=depth + 1,
            )
            for child in list(value)[:list_limit]
        ]
    return _short(str(value), str_limit)


def _packet_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def _fit_packet(packet: dict, *, budget: int = 7_900) -> dict:
    """Hard transport bound while preserving a valid structural packet."""
    complete = {**packet, "packet_truncated": False}
    if _packet_size(complete) <= budget:
        return complete
    for list_limit, dict_limit, str_limit, max_depth in (
        (6, 14, 180, 4),
        (4, 12, 150, 4),
        (3, 10, 120, 3),
        (2, 8, 90, 3),
        (1, 6, 72, 2),
    ):
        compact = _bounded_value(
            packet,
            list_limit=list_limit,
            dict_limit=dict_limit,
            str_limit=str_limit,
            max_depth=max_depth,
        )
        if isinstance(compact, dict):
            compact["packet_truncated"] = True
            if _packet_size(compact) <= budget:
                return compact
    return {
        "schema": packet.get("schema"),
        "status": "packet_budget_exceeded",
        "context_only": True,
        "execution_authority": False,
        "packet_truncated": True,
    }


def _fit_content(value: Any, *, budget: int) -> Any:
    """Bound one nested content block before it is wrapped in provenance metadata."""
    if _packet_size(value) <= budget:
        return value
    for list_limit, dict_limit, str_limit, max_depth in (
        (6, 16, 180, 4),
        (4, 14, 150, 4),
        (3, 12, 120, 3),
        (2, 10, 90, 3),
        (1, 8, 72, 2),
    ):
        compact = _bounded_value(
            value,
            list_limit=list_limit,
            dict_limit=dict_limit,
            str_limit=str_limit,
            max_depth=max_depth,
        )
        if isinstance(compact, dict):
            compact["_content_truncated"] = True
        if _packet_size(compact) <= budget:
            return compact
    return {"status": "content_budget_exceeded", "_content_truncated": True}


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _short(value: Any, limit: int = 240) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[: max(0, limit - 1)] + "…"
    return value


def _plan_row(plan: dict, *, held: bool) -> dict:
    entry = _num(plan.get("entry"))
    invalidation = _num(plan.get("invalidation"))
    t1 = _num(plan.get("t1"))
    risk_r = entry - invalidation if entry is not None and invalidation is not None else None
    reward_r = ((t1 - entry) / risk_r
                if t1 is not None and entry is not None and risk_r is not None and risk_r > 0 else None)
    return {
        "ticker": plan.get("ticker"),
        "book_state": "held" if held else "candidate",
        "plan_id": plan.get("plan_id"),
        "recommended_action": plan.get("recommended_action"),
        "phase": plan.get("phase"),
        "conviction": _num(plan.get("conviction")),
        "signal_date": plan.get("signal_date"),
        "age_days": plan.get("age_days"),
        "geometry": {
            "entry": entry,
            "trigger": _num(plan.get("trigger")),
            "invalidation": invalidation,
            "t1": t1,
            "t2": _num(plan.get("t2")),
            "risk_r": round(risk_r, 4) if risk_r is not None else None,
            "reward_to_t1_r": round(reward_r, 2) if reward_r is not None else None,
        },
        "provenance": {
            "artifact": "site/prophet/index.json",
            "authority": "display",
            "context_only": True,
        },
    }


def prophet_board(limit: int = 10, held: list[str] | tuple[str, ...] | set[str] | None = None) -> dict:
    """Return fresh Prophet discovery candidates and active management plans.

    Enter/Wait plans source the discovery list.  Hold/Trail/Trim plans and any
    plan matching ``held`` source the management list.  The underlying reader's
    staleness gate remains binding; stale plans are never resurrected here.
    """
    cap = _clamp_limit(limit, 10)
    held_set = {t for raw in (held or []) if (t := _ticker(str(raw)))}
    _, health = _read_vendor(
        "site/prophet/index.json", authority="display", cadence="nightly"
    )
    try:
        from portfolio import prophet_feed

        index = prophet_feed.index() or {}
        plans = prophet_feed.plans() or []
    except Exception:  # noqa: BLE001 - an optional evidence source must fail soft
        index, plans = {}, []

    active_by_ticker: dict[str, dict] = {}
    for plan in plans:
        if not isinstance(plan, dict) or not _ticker(plan.get("ticker")):
            continue
        ticker = plan["ticker"]
        prior = active_by_ticker.get(ticker)
        rank = (
            -(plan.get("conviction") if isinstance(plan.get("conviction"), (int, float)) else -1),
            plan.get("age_days") if isinstance(plan.get("age_days"), int) else 10**6,
        )
        prior_rank = (
            -(prior.get("conviction") if prior and isinstance(prior.get("conviction"), (int, float)) else -1),
            prior.get("age_days") if prior and isinstance(prior.get("age_days"), int) else 10**6,
        )
        if prior is None or rank < prior_rank:
            active_by_ticker[ticker] = plan

    discovery: list[dict] = []
    management: list[dict] = []
    for ticker, plan in active_by_ticker.items():
        action = str(plan.get("recommended_action") or "").lower()
        is_held = ticker in held_set
        if is_held or action in {"hold", "trail", "trim"}:
            management.append(_plan_row(plan, held=is_held))
        elif action in {"enter", "wait"}:
            discovery.append(_plan_row(plan, held=False))

    def key(row: dict) -> tuple:
        conviction = row.get("conviction")
        age = row.get("age_days")
        return (
            -(conviction if isinstance(conviction, (int, float)) else -1),
            age if isinstance(age, int) else 10**6,
            row.get("ticker") or "",
        )
    discovery.sort(key=key)
    management.sort(key=lambda row: (0 if row["book_state"] == "held" else 1, *key(row)))
    planned = set(active_by_ticker)
    return {
        "schema": "mastermind.portfolio_intelligence.prophet/v1",
        "as_of": index.get("asof"),
        "feed_active": bool(index),
        "authority_tier": index.get("authority_tier") or "display",
        "gate_go": index.get("gate_go"),
        "context_only": True,
        "health": health,
        "discovery": discovery[:cap],
        "management": management[:cap],
        "held_without_active_plan": sorted(held_set - planned)[:cap],
        "counts": {
            "active_plans": len(plans),
            "discovery_returned": min(len(discovery), cap),
            "management_returned": min(len(management), cap),
        },
    }


def _rotation_row(row: dict) -> dict:
    conviction = row.get("conviction") if isinstance(row.get("conviction"), dict) else {}
    cycle = row.get("cycle") if isinstance(row.get("cycle"), dict) else {}
    projection = cycle.get("proj") if isinstance(cycle.get("proj"), dict) else {}
    momentum = row.get("momentum") if isinstance(row.get("momentum"), dict) else {}
    rotation = row.get("rotation") if isinstance(row.get("rotation"), dict) else {}
    heat = row.get("heat") if isinstance(row.get("heat"), dict) else {}
    return {
        "ticker": row.get("ticker"),
        "name": row.get("name"),
        "group": row.get("group"),
        "conviction": {k: conviction.get(k) for k in ("score", "label_en", "dir", "early")},
        "cycle": {
            "phase": cycle.get("phase"),
            "position": cycle.get("pos"),
            "tilt": projection.get("tilt"),
            "next_turn": projection.get("nextTurn"),
        },
        "momentum": {k: momentum.get(k) for k in (
            "rs_rank", "rs_21d_rank", "rs_21d", "above_200d", "lead", "fading"
        )},
        "rotation": {k: rotation.get(k) for k in (
            "rank", "score", "state", "state_plain_en", "stale"
        )},
        "heat": {k: heat.get(k) for k in ("heat_1D", "breadth_pct")},
        "split_view": bool(row.get("split_view")),
    }


def sector_rotation(limit: int = 6) -> dict:
    """Return a slim, ranked Sector Central packet (up to six sectors and baskets)."""
    cap = min(_clamp_limit(limit, 6), 6)
    data, health = _read_vendor("site/sectordata/sector_central.json")
    if not isinstance(data, dict):
        data = {}

    def ranked(rows: Any) -> list[dict]:
        usable = [row for row in (rows or []) if isinstance(row, dict)]
        usable.sort(key=lambda row: (
            (row.get("rotation") or {}).get("rank")
            if isinstance((row.get("rotation") or {}).get("rank"), (int, float)) else 10**6,
            -(_num((row.get("conviction") or {}).get("score")) or 0),
            str(row.get("ticker") or row.get("id") or ""),
        ))
        return [_rotation_row(row) for row in usable[:cap]]

    market = data.get("market") if isinstance(data.get("market"), dict) else {}
    return {
        "schema": "mastermind.portfolio_intelligence.sector_rotation/v1",
        "as_of": data.get("as_of"),
        "context_only": True,
        "health": health,
        "market": {k: market.get(k) for k in (
            "risk_on", "state_en", "gate_state_en", "tactical_label", "risk_state_state",
            "headline_en", "quad", "quad_name", "liquidity", "growth_score", "inflation_score",
            "n_above_trend", "n_sectors",
        )},
        "sectors": ranked(data.get("sectors")),
        "baskets": ranked(data.get("baskets")),
    }


def _project_mtf(value: Any) -> dict:
    out: dict[str, dict] = {}
    if not isinstance(value, dict):
        return out
    keys = (
        "macd_pos", "macd_cross_up", "macd_cross_dn", "macd_curl_up", "macd_curl_dn",
        "stoch_cross_up", "stoch_cross_dn", "rsi14", "stoch",
    )
    for timeframe in ("D", "3D", "W", "M"):
        row = value.get(timeframe)
        if isinstance(row, dict):
            out[timeframe] = {key: row.get(key) for key in keys}
    return out


def _golden_oracle_packet(ticker: str) -> tuple[dict, list[dict], list[str]]:
    golden, gh = _read_vendor(
        "site/factordata/contracts/golden_signals.json",
        max_age_days=_WEEKLY_MAX_AGE,
        cadence="contract",
        authority="reference",
    )
    oracle, oh = _read_vendor("site/basketdata/oracle_state.json", authority="display")
    reversion, rh = _read_vendor("site/basketdata/oracle_reversion_state.json", authority="display")
    match = None
    if isinstance(golden, dict):
        match = next((row for row in (golden.get("symbols") or [])
                      if isinstance(row, dict) and row.get("symbol") == ticker), None)
    packet = {
        "golden_contract": {
            "schema": golden.get("schema") if isinstance(golden, dict) else None,
            "as_of": golden.get("as_of") if isinstance(golden, dict) else None,
            "oracle": golden.get("oracle") if isinstance(golden, dict) else None,
            "math": ({k: (golden.get("math") or {}).get(k) for k in (
                "macd_fast", "macd_slow", "macd_signal", "stoch_len",
                "smooth_k", "smooth_d", "resample",
            )} if isinstance(golden, dict) and isinstance(golden.get("math"), dict) else None),
            "ticker_vector": ({k: match.get(k) for k in (
                "symbol", "region", "label", "inputs_hash", "n_signals"
            )} if match else None),
            "role": "conformance reference, not a live signal",
        },
        "oracle_state": {
            "schema": oracle.get("schema") if isinstance(oracle, dict) else None,
            "as_of": oracle.get("asof") if isinstance(oracle, dict) else None,
            "regime": oracle.get("regime") if isinstance(oracle, dict) else None,
            "complexes": [
                {k: row.get(k) for k in ("id", "name", "state", "tier", "direction")}
                for row in ((oracle.get("complexes") or []) if isinstance(oracle, dict) else [])[:8]
                if isinstance(row, dict)
            ][:2],
        },
        "reversion_state": {
            "schema": reversion.get("schema") if isinstance(reversion, dict) else None,
            "as_of": reversion.get("asof") if isinstance(reversion, dict) else None,
            "tier": reversion.get("tier") if isinstance(reversion, dict) else None,
            "fired": [
                {k: row.get(k) for k in ("id", "name", "cluster", "authority_level", "fired_today")}
                for row in ((reversion.get("signals") or []) if isinstance(reversion, dict) else [])
                if isinstance(row, dict) and row.get("fired_today")
            ][:3],
        },
    }
    missing = []
    if not gh["available"]:
        missing.append("golden_contract")
    elif match is None:
        missing.append("golden_ticker_vector")
    if not oh["available"]:
        missing.append("oracle_state")
    if not rh["available"]:
        missing.append("oracle_reversion_state")
    return packet, [gh, oh, rh], missing


def technical_packet(ticker: str) -> dict:
    """Return one bounded, multi-timeframe technical packet for a validated ticker."""
    symbol = _ticker(ticker)
    if not symbol:
        return {
            "schema": "mastermind.portfolio_intelligence.technical/v1",
            "ticker": None,
            "status": "invalid_ticker",
            "error": "ticker must be 1-12 uppercase alphanumeric characters with optional . or -",
            "context_only": True,
        }

    stock, sh = _read_vendor(f"site/stockdata/{symbol}.json")
    signals, sigh = _read_vendor(f"site/signals/{symbol}.json")
    gex, gexh = _read_vendor(
        f"site/options_structure/gex_state/{symbol}.json",
        max_age_days=_INTRADAY_MAX_AGE,
        cadence="intraday",
        authority="display",
    )
    flow, flowh = _read_vendor(
        f"site/flow/{symbol}.json",
        max_age_days=_INTRADAY_MAX_AGE,
        cadence="intraday",
        authority="display",
    )
    prophet, proph_h = _read_vendor("site/prophet/index.json", authority="display")
    del prophet  # health is useful here; normalized plan comes from the gated reader below.
    try:
        from portfolio import entry_engine, prophet_feed

        entry = entry_engine.assess(symbol)
        plan = prophet_feed.plan_for(symbol)
    except Exception:  # noqa: BLE001
        entry, plan = {"ticker": symbol, "verdict": "unknown", "sources": []}, None

    stock = stock if isinstance(stock, dict) else {}
    signals = signals if isinstance(signals, dict) else {}
    tech = stock.get("tech") if isinstance(stock.get("tech"), dict) else {}
    stock_signal = stock.get("signal") if isinstance(stock.get("signal"), dict) else {}
    entry_signal = stock.get("entry_signal") if isinstance(stock.get("entry_signal"), dict) else {}
    ladder = stock.get("ladder") if isinstance(stock.get("ladder"), dict) else {}
    golden_oracle, oracle_sources, missing = _golden_oracle_packet(symbol)

    if not sh["available"]:
        missing.append("stockdata")
    if not sigh["available"]:
        missing.append("chart_signals")
    if not gexh["available"]:
        missing.append("options_gex")
    if not flowh["available"]:
        missing.append("options_flow")
    if plan is None:
        missing.append("prophet_plan")
    if not entry.get("sources"):
        missing.append("entry_engine_inputs")

    tech_keys = (
        "price", "above50", "above200", "pct_vs_20dma", "pct_vs_50dma", "pct_vs_200dma",
        "off_52w_high_pct", "rsi14", "rsi2", "macd_pos", "golden", "sma50_slope_up",
        "ret_1m", "ret_3m", "ret_6m", "ret_12m", "rs_1m", "rs_3m", "rs_6m",
        "atr14", "atr_pct", "adx14", "di_plus", "di_minus", "adx_trend", "bbwp",
        "squeeze_on", "donchian_pos", "rel_volume", "obv_slope_up", "cmf20",
    )
    gex = gex if isinstance(gex, dict) else {}
    flow = flow if isinstance(flow, dict) else {}
    positioning = flow.get("positioning") if isinstance(flow.get("positioning"), dict) else {}
    signing = flow.get("signing") if isinstance(flow.get("signing"), dict) else {}
    timing = entry_signal.get("timing") if isinstance(entry_signal.get("timing"), dict) else {}
    ladder_entry = ladder.get("entry") if isinstance(ladder.get("entry"), dict) else {}
    gex_reliability = gex.get("reliability") if isinstance(gex.get("reliability"), dict) else {}
    flow_verdict = flow.get("verdict") if isinstance(flow.get("verdict"), dict) else {}
    return {
        "schema": "mastermind.portfolio_intelligence.technical/v1",
        "ticker": symbol,
        "status": "ok" if sh["available"] or sigh["available"] else "degraded",
        "context_only": True,
        "identity": {k: stock.get(k) for k in ("ticker", "name", "sector", "asof")},
        "entry_assessment": entry,
        "spot_technicals": {key: tech.get(key) for key in tech_keys},
        "multi_timeframe": _project_mtf(stock.get("mtf")),
        "terminal_signal": {
            "state": signals.get("state"),
            "timeframe": signals.get("tf"),
            "above200": signals.get("above200"),
            "weekly_bull": signals.get("weekly_bull"),
            "trail_stop": signals.get("trail_stop"),
            "trail_breach": signals.get("trail_breach"),
            "early_now": signals.get("early_now"),
            "recent_markers": [m for m in (signals.get("markers") or [])[-3:] if isinstance(m, dict)],
            "recent_risk_flags": list((signals.get("risk_flags") or [])[-3:]),
        },
        "entry_timing": {
            "signal_gate": {k: stock_signal.get(k) for k in (
                "eligible", "tier_cascade", "tier_sub", "ticks", "bars_to_cross", "provisional"
            )},
            "entry_signal": {k: entry_signal.get(k) for k in (
                "status", "urgency", "headline", "entry_z", "entry_grade", "confidence",
                "buy_zone", "chase_above", "stop", "spot",
            )} | {
                "timing": {
                    "opens_in_days_lo": timing.get("opens_in_days_lo"),
                    "opens_in_days_hi": timing.get("opens_in_days_hi"),
                    "next_trigger": _short(timing.get("next_trigger"), 100),
                },
            },
            "ladder": {k: ladder.get(k) for k in (
                "state", "label", "action", "dir", "score", "weekly_ok", "regime", "regime_label",
            )} | {
                "why": _short(ladder.get("why"), 100),
                "next": _short(ladder.get("next"), 100),
                "entry": {k: ladder_entry.get(k) for k in ("tag", "urgency")},
            },
        },
        "prophet_plan": _plan_row(plan, held=False) if isinstance(plan, dict) else None,
        "options_structure": {
            "gex": {k: gex.get(k) for k in (
                "asof", "spot", "net_gex_bn", "gamma_regime", "stability_pct", "gamma_flip",
                "call_wall", "put_wall", "magnet", "max_pain", "pin_probability",
                "gravity_direction", "cascade_trigger", "upside_trigger", "authority_tier",
            )} | {
                "reliability": {k: _short(gex_reliability.get(k), 120) for k in (
                    "levels", "regime",
                )},
            },
            "flow": {
                **{k: flow.get(k) for k in (
                    "available", "asof", "spot", "volume", "premium_mn", "pc_ratio", "zerodte_share",
                )},
                "positioning": {k: positioning.get(k) for k in (
                    "available", "reliable", "asof", "n_new_contracts", "net_doi", "doi_pc",
                    "net_delta_doi_mn", "opening", "tone", "lean_en",
                )},
                "signing": {k: signing.get(k) for k in (
                    "method", "direction_reliable", "magnitude_reliable", "per_trade_agreement",
                    "net_sign_recovery",
                )},
                "verdict": {k: _short(flow_verdict.get(k), 200) for k in (
                    "tone", "en", "direction_reliable", "positioning_reliable",
                )},
            },
        },
        "golden_oracle": golden_oracle,
        "sources": [_technical_source_ref(source) for source in (
            sh, sigh, proph_h, gexh, flowh, *oracle_sources
        )],
        "missing_fields": sorted(set(missing)),
    }


def _book_snapshot(book: str) -> dict:
    allowed = {"autonomous", "china", "hk"}
    if book not in allowed:
        return {"book": book, "status": "unsupported_book", "allowed": sorted(allowed)}
    base = _ROOT / "data" / "portfolios" / book
    latest, latest_h = _read_path(
        base / "latest.json", f"data/portfolios/{book}/latest.json", cadence="portfolio-run"
    )
    account, account_h = _read_path(
        base / "account.json", f"data/portfolios/{book}/account.json", cadence="portfolio-run"
    )
    latest = latest if isinstance(latest, dict) else {}
    account = account if isinstance(account, dict) else {}
    rows = []
    all_positions = latest.get("positions") or []
    for row in all_positions[:12]:
        if isinstance(row, dict):
            projected = {k: row.get(k) for k in (
                "ticker", "weight", "held_days", "unrealized_pct",
            )}
            rows.append(projected)
    if not rows and isinstance(account.get("positions"), dict):
        rows = [{"ticker": ticker} for ticker in sorted(account["positions"])[:12]]
    return {
        "book": book,
        "status": "ok" if latest else "degraded",
        "as_of": latest.get("as_of"),
        "nav": latest.get("nav"),
        "gross": latest.get("gross"),
        "cash_weight": latest.get("cash"),
        "cash_amount": latest.get("cash_usd") or account.get("cash"),
        "summary": _short(latest.get("summary"), 320),
        "n_positions": len(rows),
        "positions_truncated": len(all_positions) > len(rows),
        "positions": rows,
        "sources": [_source_ref(latest_h), _source_ref(account_h)],
    }


def _nw_candidate_projection(ticker: str, row: Any, *, origin: str) -> dict:
    if not isinstance(row, dict):
        return {"ticker": ticker, "origin": origin, "available": False}

    def section(name: str, keys: tuple[str, ...]) -> dict | None:
        value = row.get(name)
        if not isinstance(value, dict):
            return None
        return {key: _short(value.get(key), 140) for key in keys if key in value}

    projected = {
        "ticker": ticker,
        "origin": origin,
        "available": True,
        "allowed_behavior": row.get("allowed_behavior"),
        "kernel": section("kernel", ("fdr_cleared",)),
        "bottom": section("bottom", (
            "as_of", "bottom_state", "coiled", "coiled_fire", "dist_21d_low_pct",
            "dist_126d_high_pct",
        )),
        "valuation": section("valuation", ("ev_sales", "ev_ebit", "p_fcf", "pe")),
        "leverage": section("leverage", ("net_debt_to_ebitda", "net_debt_to_op_income")),
        "structural": section("structural", (
            "decline_geometry", "underwater_state", "decline_herf", "sponsorship_state",
        )),
        "earnings": section("earnings_ctx", ("days_to_earnings", "is_blackout")),
        "options": section("options", (
            "as_of", "ivspread_rel", "skew", "gamma_regime", "gex_confirm_verdict",
            "evidence_quality", "wall_up_dist_pct", "wall_down_dist_pct",
        )),
        "dilution": _bounded_value(row.get("dilution"), list_limit=2, dict_limit=8, max_depth=2),
        "visibility": _bounded_value(row.get("visibility"), list_limit=2, dict_limit=8, max_depth=2),
    }
    return {key: value for key, value in projected.items() if value is not None}


def neural_web_packet(
    book: str = "autonomous",
    tickers: list[str] | tuple[str, ...] | set[str] | str | None = None,
) -> dict:
    """Return bounded Neural Web context for one active Portfolio Brain.

    Explicit tickers are considered first, then the book's held names.  The
    artifact remains annotate-only/display-tier: its own authority declaration
    is shown, while the effective authority fence is always false for candidate
    origination, sizing, blocking, and exits.
    """
    book_id = str(book or "autonomous").lower().strip()
    if book_id not in {"autonomous", "china", "hk"}:
        return _fit_packet({
            "schema": "mastermind.portfolio_intelligence.neural_web/v1",
            "status": "unsupported_book",
            "book": book_id,
            "allowed_books": ["autonomous", "china", "hk"],
            "context_only": True,
            "execution_authority": False,
        })
    if tickers is None:
        supplied: list[Any] = []
    elif isinstance(tickers, str):
        supplied = [tickers]
    elif isinstance(tickers, (list, tuple, set)):
        supplied = list(tickers)
    else:
        return _fit_packet({
            "schema": "mastermind.portfolio_intelligence.neural_web/v1",
            "status": "invalid_tickers_type",
            "book": book_id,
            "context_only": True,
            "execution_authority": False,
        })

    explicit: list[str] = []
    rejected: list[str] = []
    for raw in supplied:
        normalized = _ticker(str(raw))
        if normalized and normalized not in explicit:
            explicit.append(normalized)
        elif not normalized:
            rejected.append(_short(str(raw), 80))

    current = _book_snapshot(book_id)
    held = []
    for position in current.get("positions", []):
        normalized = _ticker(position.get("ticker"))
        if normalized and normalized not in held:
            held.append(normalized)
    requested = explicit + [ticker for ticker in held if ticker not in explicit]
    ticker_limit = 6
    selected = requested[:ticker_limit]
    omitted = requested[ticker_limit:]

    data, health = _read_vendor(
        "site/neuralwebdata/mastermind_context.json",
        authority="context",
    )
    data = data if isinstance(data, dict) else {}
    candidates = data.get("candidate_context") if isinstance(data.get("candidate_context"), dict) else {}
    lobes = data.get("lobes") if isinstance(data.get("lobes"), dict) else {}
    market = lobes.get("market") if isinstance(lobes.get("market"), dict) else {}
    book_context = data.get("book_context") if isinstance(data.get("book_context"), dict) else {}

    market_context = {
        "verdict": _bounded_value(market.get("verdict"), list_limit=2, dict_limit=10, max_depth=2),
        "radar": _bounded_value(market.get("radar"), list_limit=2, dict_limit=8, max_depth=2),
        "volatility": {key: (market.get("vol") or {}).get(key) for key in (
            "asof", "regime", "risk_score", "vix", "vrp_state", "vvix_state",
            "vol_target_scalar", "fragility_confluence",
        )} if isinstance(market.get("vol"), dict) else None,
        "breadth": {key: (market.get("breadth") or {}).get(key) for key in (
            "date", "pct_above_50", "pct_above_200", "nh", "nl", "adv", "dec", "breadth_div",
        )} if isinstance(market.get("breadth"), dict) else None,
        "rotation": _bounded_value(
            (market.get("rotation") or {}).get("regime") if isinstance(market.get("rotation"), dict) else None,
            list_limit=2,
            dict_limit=8,
            str_limit=140,
            max_depth=3,
        ),
    }
    selected_lobes = {}
    for name in (
        "reliability", "contradictions", "macro_weather", "claim_reliability",
        "risk_radar_reliability", "contagion", "fx_dollar", "market_structure", "rates_command",
    ):
        if name in lobes:
            selected_lobes[name] = _bounded_value(
                lobes[name], list_limit=2, dict_limit=7, str_limit=120, max_depth=2
            )

    origins = {
        ticker: "requested+held" if ticker in explicit and ticker in held
        else "requested" if ticker in explicit else "held"
        for ticker in selected
    }
    manifest = [
        {key: row.get(key) for key in (
            "artifact_id", "asof", "stale", "tier", "horizon_role", "has_rich_summary",
        )}
        for row in (data.get("lobe_manifest") or [])[:10]
        if isinstance(row, dict)
    ]
    authority = data.get("authority") if isinstance(data.get("authority"), dict) else {}
    global_projected = _fit_content({
        "market": market_context,
        "lobes": selected_lobes,
        "manifest": manifest,
    }, budget=1_700)
    book_projected = _fit_content({
        "top_macro_contradictions": _bounded_value(
            book_context.get("top_macro_contradictions"),
            list_limit=2,
            dict_limit=8,
            str_limit=140,
            max_depth=3,
        ),
        "decaying_families": [_short(item, 180) for item in (
            book_context.get("decaying_families") or []
        )[:4]],
        "bottom_summary_counts": _bounded_value(
            book_context.get("bottom_summary_counts"), dict_limit=10, max_depth=3
        ),
    }, budget=900)
    candidate_rows = [
        _fit_content(
            _nw_candidate_projection(ticker, candidates.get(ticker), origin=origins[ticker]),
            budget=950 if index < 2 else 620,
        )
        for index, ticker in enumerate(selected)
    ]
    return _fit_packet({
        "schema": "mastermind.portfolio_intelligence.neural_web/v1",
        "status": "ok" if data else "unavailable",
        "book": book_id,
        "as_of": data.get("as_of"),
        "freshest_market_asof": data.get("freshest_market_asof"),
        "context_only": True,
        "authority": {
            "artifact_declaration": _bounded_value(authority, dict_limit=8, max_depth=2),
            "effective": {
                "can_add_candidates": False,
                "can_raise_size": False,
                "can_lower_size": False,
                "can_block_entry": False,
                "can_force_exit": False,
                "execution_authority": False,
            },
        },
        "provenance": _source_ref(health),
        "freshness_by_lobe": _fit_content(
            _bounded_value(data.get("freshness"), list_limit=2, dict_limit=12, max_depth=2),
            budget=650,
        ),
        "global_context": global_projected,
        "book_context": book_projected,
        "candidates": candidate_rows,
        "candidate_coverage": {
            "artifact_candidates": len(candidates),
            "requested": len(explicit),
            "held": len(held),
            "returned": len(selected),
            "limit": ticker_limit,
            "omitted_tickers": omitted,
            "rejected_tickers": rejected,
        },
        "gap_notes": [_short(item, 180) for item in (data.get("gap_notes") or [])[:4]],
    })


def market_packet(book: str = "autonomous") -> dict:
    """Return one compact start-of-session packet for a Portfolio Brain.

    This is the cheap first call: current book, regime, top rotation, Prophet
    discovery/management, and health.  Rich per-name context stays on demand via
    :func:`technical_packet`, keeping daily prompts token-efficient.
    """
    book_id = str(book or "autonomous").lower().strip()
    current = _book_snapshot(book_id)
    held = [row.get("ticker") for row in current.get("positions", []) if row.get("ticker")]
    regime, regime_h = _read_vendor("data/regime/latest.json")
    regime = regime if isinstance(regime, dict) else {}
    sectors = sector_rotation(limit=2)
    prophet = prophet_board(limit=4, held=held)
    catalog = context_catalog()
    status_rows = [
        {"id": row["id"], "status": row["status"], "available": row["available"]}
        for row in catalog["surfaces"]
    ]
    status_counts = {
        key: sum(1 for row in status_rows if row["status"] == key)
        for key in ("fresh", "stale", "undated", "missing", "malformed")
    }

    def compact_rotation(row: dict) -> dict:
        conviction = row.get("conviction") or {}
        cycle = row.get("cycle") or {}
        momentum = row.get("momentum") or {}
        rotation = row.get("rotation") or {}
        return {
            "ticker": row.get("ticker"),
            "name": row.get("name"),
            "conviction": {k: conviction.get(k) for k in ("score", "dir", "early")},
            "cycle": {k: cycle.get(k) for k in ("phase", "tilt")},
            "momentum": {k: momentum.get(k) for k in (
                "rs_21d_rank", "above_200d", "lead",
            )},
            "rotation": {k: rotation.get(k) for k in ("rank", "state", "stale")},
        }

    def compact_plan(row: dict) -> dict:
        geometry = row.get("geometry") or {}
        return {
            **{key: row.get(key) for key in (
                "ticker", "book_state", "recommended_action", "phase", "conviction", "age_days",
            )},
            "geometry": {key: geometry.get(key) for key in (
                "entry", "invalidation", "t1", "reward_to_t1_r",
            )},
        }

    prophet_compact = {key: prophet.get(key) for key in (
        "as_of", "feed_active", "authority_tier", "gate_go", "context_only",
        "held_without_active_plan", "counts",
    )} | {
        "health": _source_ref(prophet.get("health") or {}),
        "discovery": [compact_plan(row) for row in prophet.get("discovery", [])],
        "management": [compact_plan(row) for row in prophet.get("management", [])],
    }
    return {
        "schema": "mastermind.portfolio_intelligence.market_packet/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "book": current,
        "regime": {
            "health": _source_ref(regime_h),
            **{key: regime.get(key) for key in (
                "asof", "date", "quad", "quad_name", "growth_score", "inflation_score",
                "confidence", "liquidity_overlay", "cycle_tag", "transition_state",
            )},
            "confirming": [_short(item, 120) for item in (regime.get("confirming") or [])[:4]],
            "contradicting": [_short(item, 120) for item in (regime.get("contradicting") or [])[:4]],
            "alerts": [
                {key: _short(row.get(key), 160) for key in ("rule", "severity", "message")}
                for row in (regime.get("alerts") or [])[:3] if isinstance(row, dict)
            ],
            "sector_rs_top": [
                {key: row.get(key) for key in ("ticker", "rs", "mom_20d_pct", "rank")}
                for row in (regime.get("sector_rs") or [])[:6] if isinstance(row, dict)
            ],
        },
        "sector_rotation": {
            "as_of": sectors.get("as_of"),
            "health": _source_ref(sectors.get("health") or {}),
            "market": sectors.get("market"),
            "sectors": [compact_rotation(row) for row in sectors.get("sectors", [])],
            "baskets": [compact_rotation(row) for row in sectors.get("baskets", [])],
        },
        "prophet": prophet_compact,
        "data_health": {
            "counts": status_counts,
            "critical": [
                row for row in status_rows
                if row["id"] in {"macro_context", "sector_central", "prophet", "technical_lab", "neural_web"}
            ],
        },
        "usage": {
            "next_call": "technical_packet(ticker) only for held names under review and finalists",
            "signals_are_context_not_orders": True,
        },
    }


_SURFACE_DECISION_KEYS: dict[str, tuple[str, ...]] = {
    "intelligence_hub": (
        "schema", "is_context_only", "as_of", "macro_context", "n_priority", "n_actionable",
        "n_divergences", "priority_queue", "divergences", "how_to_use",
    ),
    "foresight": (
        "asof", "n_themes", "dislocation", "demand_pool", "sizing", "health", "themes", "note",
    ),
    "radar": (
        "schema", "is_context_only", "as_of", "coverage", "changes", "regime", "edge_ranked",
        "flags", "hypotheses", "caveats",
    ),
    "state_of_themes": (
        "as_of", "asof", "story", "theme_intel", "baskets", "source", "delay_min", "default_tf",
        "tiles", "n_tiles", "n_members",
    ),
    "etfs": ("as_of", "horizons", "style", "risk", "sector", "disclaimer_en"),
    "movers": (
        "asof", "generated_utc", "source", "delay_min", "default_tf", "tiles", "n_tiles",
    ),
    "intraday_flow": (
        "schema", "as_of", "generated_at", "verdict", "calibrated", "regime", "cluster",
        "emerging", "cooling", "sectors", "baskets", "authority", "coverage_stats", "themes",
        "ai_handoff", "honesty_header",
    ),
    "options": (
        "schema", "is_context_only", "as_of", "generated_utc", "gate_status", "n", "ranked",
        "authority", "coverage_stats", "themes", "honesty_header", "disclaimer",
    ),
    "confluence_screener": (
        "schema", "page", "gated", "required_tier", "built", "generated_utc", "universe_n",
        "n_evaluated", "n_reported", "top_selection", "base", "combos", "pairs", "now",
        "universe_caveat", "search_caveat",
    ),
    "stock_seasonality": (
        "schema", "as_of", "source", "trailing_years", "now", "factors", "disclosure_en",
    ),
    "technical_lab": (
        "generated_utc", "as_of", "universe_n", "universe_caveat", "_meta", "signals", "verdicts",
    ),
}


def _surface_content(surface_id: str, rel: str, payload: Any, limit: int) -> Any:
    if not isinstance(payload, dict):
        return _bounded_value(payload, list_limit=limit, dict_limit=12, max_depth=3)
    if surface_id == "sector_central":
        return sector_rotation(limit=limit)
    if surface_id == "prophet":
        return prophet_board(limit=limit)
    if surface_id == "macro_context":
        return {
            **{key: payload.get(key) for key in (
                "asof", "date", "quad", "quad_name", "growth_score", "inflation_score",
                "confidence", "liquidity_overlay", "cycle_tag", "transition_state", "flip_condition",
                "liquidity_quality", "conditions", "market_drivers", "fed_path", "yield_curve",
            )},
            "confirming": [_short(item, 140) for item in (payload.get("confirming") or [])[:limit]],
            "contradicting": [_short(item, 140) for item in (payload.get("contradicting") or [])[:limit]],
            "sector_rs": [
                {key: row.get(key) for key in (
                    "ticker", "rs", "mom_20d_pct", "mom_60d_pct", "above_200d_trend", "rank",
                )}
                for row in (payload.get("sector_rs") or [])[:limit] if isinstance(row, dict)
            ],
            "alerts": _bounded_value(payload.get("alerts"), list_limit=limit, dict_limit=8, max_depth=3),
        }
    if surface_id == "neural_web":
        lobes = payload.get("lobes") if isinstance(payload.get("lobes"), dict) else {}
        return _bounded_value({
            "schema": payload.get("schema"),
            "as_of": payload.get("as_of"),
            "freshest_market_asof": payload.get("freshest_market_asof"),
            "authority": payload.get("authority"),
            "freshness": payload.get("freshness"),
            "market": lobes.get("market"),
            "macro_weather": lobes.get("macro_weather"),
            "reliability": lobes.get("reliability"),
            "contradictions": lobes.get("contradictions"),
            "book_context": payload.get("book_context"),
            "gap_notes": payload.get("gap_notes"),
        }, list_limit=limit, dict_limit=12, str_limit=160, max_depth=3)
    if surface_id == "golden_oracle":
        keys = (
            ("schema", "as_of", "oracle", "math", "symbols", "note")
            if "golden_signals" in rel
            else ("schema", "asof", "regime", "complexes", "active_episodes", "onset_watchlist",
                  "tier", "n_signals", "signals", "disclaimers")
        )
        selected = {key: payload.get(key) for key in keys if key in payload}
        return _bounded_value(
            selected, list_limit=limit, dict_limit=14, str_limit=160, max_depth=4
        )

    keys = _SURFACE_DECISION_KEYS.get(surface_id, tuple(payload)[:14])
    selected: dict[str, Any] = {}
    map_keys = {"signals", "verdicts", "themes", "now"}
    for key in keys:
        if key not in payload:
            continue
        value = payload[key]
        if key in map_keys and isinstance(value, dict):
            value = dict(list(value.items())[:limit])
        if surface_id == "movers" and key == "tiles" and isinstance(value, list):
            def move_size(tile: Any) -> float:
                if not isinstance(tile, dict):
                    return -1.0
                perf = tile.get("perf")
                if isinstance(perf, dict):
                    nums = [_num(item) for item in perf.values()]
                    return max((abs(item) for item in nums if item is not None), default=-1.0)
                number = _num(perf)
                return abs(number) if number is not None else -1.0

            value = sorted(value, key=move_size, reverse=True)
        if surface_id == "state_of_themes" and key == "theme_intel" and isinstance(value, dict):
            value = {name: value.get(name) for name in (
                "as_of", "macro_context", "rotation_5d", "impulse_scorecard", "market_concentration",
                "breadth_leaders", "breadth_laggards", "entries", "rollover", "act_now",
                "recommendations",
            ) if name in value}
        selected[key] = value
    return _bounded_value(
        selected,
        list_limit=limit,
        dict_limit=16,
        str_limit=180,
        max_depth=4,
    )


def surface_packet(surface_id: str, limit: int = 6) -> dict:
    """Read one catalog surface through its fixed artifact allowlist.

    ``surface_id`` is an enum-like catalog key, never a path.  Each response is
    structurally projected and hard-limited below the MCP transport budget.
    """
    requested = str(surface_id or "").lower().strip()
    spec = next((row for row in _SURFACES if row["id"] == requested), None)
    if spec is None:
        return _fit_packet({
            "schema": "mastermind.portfolio_intelligence.surface/v1",
            "status": "invalid_surface_id",
            "surface_id": requested,
            "valid_surface_ids": [row["id"] for row in _SURFACES],
            "context_only": True,
            "execution_authority": False,
        })

    cap = min(_clamp_limit(limit, 6), 8)
    artifact_count = max(1, len(spec["artifacts"]))
    per_artifact_limit = max(1, min(cap, 6 // artifact_count))
    per_artifact_budget = max(1_500, 6_300 // artifact_count)
    artifacts = []
    for rel, max_age, cadence, authority in spec["artifacts"]:
        payload, health = _read_vendor(
            rel,
            max_age_days=max_age,
            cadence=cadence,
            authority=authority,
        )
        content = (
            _surface_content(requested, rel, payload, per_artifact_limit)
            if health["available"] else None
        )
        artifacts.append({
            "source": _source_ref(health),
            "content": _fit_content(content, budget=per_artifact_budget)
            if content is not None else None,
        })
    return _fit_packet({
        "schema": "mastermind.portfolio_intelligence.surface/v1",
        "status": "ok" if any(row["source"]["available"] for row in artifacts) else "unavailable",
        "surface_id": requested,
        "title": spec["title"],
        "url": f"{_URL_BASE}/{spec['page']}",
        "requested_limit": cap,
        "per_artifact_limit": per_artifact_limit,
        "context_only": True,
        "execution_authority": False,
        "artifacts": artifacts,
    })
