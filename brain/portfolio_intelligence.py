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
import math
import os
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
_PACKET_MAX_BYTES = 7_900

_CHINA_COMPANY_EVIDENCE_ARTIFACT = "site/china_intel/command.json"
_CHINA_COMMAND_SCHEMA = "china_intel.command.v1"
_CHINA_COMPANY_EVIDENCE_SOURCE_SCHEMA = "china_intel.company_evidence.v1"
_CHINA_COMPANY_EVIDENCE_PACKET_SCHEMA = "mastermind.china_company_evidence.v1"
_CHINA_A_SHARE_RE = re.compile(r"^\d{6}\.(?:SS|SZ)$")


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
    if health.get("source_mode") == "selected_generation":
        return {
            **_psl_health(health), "artifact": _PSL_NATIVE_MEMBER,
            "available": health.get("available") is True, "age_days": None,
            "authority": "context", "execution_authority": False,
        }
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
    sector_health = sector_rotation()["health"]
    packet = _context_catalog_with_sector_health(sector_health)
    if sector_health.get("source_mode") != "selected_generation":
        return packet
    packet["packet_truncated"] = False
    if _packet_size(packet) <= _PACKET_MAX_BYTES:
        return packet
    refused = _native_packet_refusal(
        packet["schema"], sector_health, "native_catalog_transport_budget_exceeded")
    # Fixed catalog identities remain discoverable; none of this oversized
    # packet's observed health is presented as admitted source evidence.
    refused.update(
        generated_at=packet["generated_at"], policy=packet["policy"],
        surfaces=[{
            "id": spec["id"], "title": spec["title"],
            "url": f"{_URL_BASE}/{spec['page']}", "status": "unknown",
            "available": False, "artifacts": [],
        } for spec in _SURFACES],
    )
    return refused


def _context_catalog_with_sector_health(sector_health: dict) -> dict:
    """Build catalog observations without recapturing the selected Sector source."""
    surfaces: list[dict] = []
    for spec in _SURFACES:
        artifacts = []
        for rel, max_age, cadence, authority in spec["artifacts"]:
            if spec["id"] == "sector_central":
                health = sector_health
            else:
                _, health = _read_vendor(
                    rel,
                    max_age_days=max_age,
                    cadence=cadence,
                    authority=authority,
                )
            artifacts.append(_source_ref(health))
        available = [a for a in artifacts if a["available"]]
        if spec["id"] == "sector_central":
            # A degraded native receipt is unknown, not a temporal stale claim.
            status = artifacts[0]["status"]
        elif any(a["status"] == "fresh" for a in available):
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


def _fit_packet(packet: dict, *, budget: int = _PACKET_MAX_BYTES) -> dict:
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


def _fit_china_company_evidence(packet: dict) -> dict:
    """Fit CIE-15 without dropping its authority or negative-context envelope."""
    budget = 6_500
    complete = {**packet, "packet_truncated": False}
    if _packet_size(complete) <= budget:
        return complete

    row_priority = (
        "basis", "detail_en", "detail_zh", "kind", "title", "source",
        "source_id", "source_url", "source_published_at",
        "system_recorded_at", "visitor_identity_state",
    )
    exact_provenance = (
        "source", "source_id", "source_url", "source_published_at",
        "system_recorded_at", "visitor_identity_state",
    )

    def project_rows(rows: list, limit: int, text_limit: int) -> list:
        projected = []
        for row in rows[:limit]:
            if not isinstance(row, dict):
                projected.append(_bounded_value(row, str_limit=text_limit))
                continue
            ordered = {key: row[key] for key in row_priority if key in row}
            ordered.update({key: value for key, value in row.items() if key not in ordered})
            item = _bounded_value(
                ordered, list_limit=limit, dict_limit=14,
                str_limit=text_limit, max_depth=4,
            )
            # A shortened URL, source ID or clock is not usable provenance.
            for key in exact_provenance:
                if key in row:
                    item[key] = row[key]
            projected.append(item)
        return projected

    # Never pass this top-level packet through an insertion-order dict limiter.
    # Source, clocks, market context and both authority boundaries remain exact.
    for limit, text_limit in ((6, 180), (4, 120), (2, 90), (1, 60)):
        compact = {
            **packet,
            "name": _bounded_value(packet.get("name"), str_limit=140),
            "evidence": project_rows(packet["evidence"], limit, text_limit),
            "packet_truncated": True,
            "compaction": {
                "evidence_rows_omitted": max(0, len(packet["evidence"]) - limit),
                "contradiction_rows_omitted": 0,
                "unknown_rows_omitted": 0,
            },
        }
        if _packet_size(compact) <= budget:
            return compact

    # Bulk positive evidence has reached one row before negative text/row
    # compaction begins. Keep at least that row's exact citation when present.
    for limit, text_limit in ((6, 180), (4, 120), (2, 90), (1, 60), (1, 40)):
        compact = {
            **packet,
            "name": _bounded_value(packet.get("name"), str_limit=140),
            "evidence": project_rows(packet["evidence"], 1, 60),
            "contradictions": project_rows(packet["contradictions"], limit, text_limit),
            "falsifier": {
                key: _bounded_value(value, str_limit=text_limit)
                for key, value in packet["falsifier"].items()
            },
            "unknowns": _bounded_value(
                packet["unknowns"], list_limit=limit, str_limit=text_limit,
            ),
            "packet_truncated": True,
            "compaction": {
                "evidence_rows_omitted": max(0, len(packet["evidence"]) - 1),
                "contradiction_rows_omitted": max(0, len(packet["contradictions"]) - limit),
                "unknown_rows_omitted": max(0, len(packet["unknowns"]) - limit),
            },
        }
        if _packet_size(compact) <= budget:
            return compact

    # Unrepresentable mandatory context is unavailable, never a smaller
    # positive packet that silently lost its clocks, warnings or boundaries.
    return {
        "schema": packet["schema"],
        "status": "packet_budget_exceeded",
        "ticker": packet["ticker"],
        "name": None,
        "context_only": True,
        "execution_authority": False,
        "authority": packet["authority"],
        "source": {
            "artifact": _CHINA_COMPANY_EVIDENCE_ARTIFACT,
            "url": f"{_URL_BASE}/china_intel.html",
            "available": False,
            "status": "packet_budget_exceeded",
        },
        "contradictions": [],
        "falsifier": {"en": None, "zh": None},
        "unknowns": ["mandatory_context_exceeds_packet_budget"],
        "evidence_context": {"status": "unavailable", "clocks": None},
        "evidence": [],
        "recognition": packet["recognition"],
        "prophet_timing": packet["prophet_timing"],
        "packet_truncated": True,
    }


def china_company_evidence(ticker: str) -> dict:
    """Return one bounded, read-only China company-evidence packet.

    The reader consumes only the fixed vendored Macro publication at
    site/china_intel/command.json. It never fetches source documents, never
    reads an arbitrary path, and never grants ranking, Prophet, sizing, exit or
    trade authority. CIE-14 recognition fields attach only after their separate
    acceptance; this slice is grounded in the already PROVEN_LIVE CIE-06
    company-evidence contract.
    """
    symbol = _ticker(ticker)
    authority = {
        "context_only": True,
        "may_rank": False,
        "may_feed_prophet": False,
        "may_size": False,
        "may_change_eligibility": False,
        "may_change_entry": False,
        "may_change_exit": False,
        "may_trade": False,
        "may_execute_source_text": False,
    }

    def _base(status: str, *, source: dict | None = None) -> dict:
        return {
            "schema": _CHINA_COMPANY_EVIDENCE_PACKET_SCHEMA,
            "status": status,
            "ticker": symbol,
            "context_only": True,
            "execution_authority": False,
            "authority": authority,
            "source": source,
        }

    if symbol is None or not _CHINA_A_SHARE_RE.fullmatch(symbol):
        return _fit_packet(_base("invalid_or_off_venue_ticker"), budget=6_500)

    payload, health = _read_vendor(
        _CHINA_COMPANY_EVIDENCE_ARTIFACT,
        max_age_days=_DAILY_MAX_AGE,
        cadence="settled-close",
        authority="context",
    )
    source = {
        **_source_ref(health),
        "url": f"{_URL_BASE}/china_intel.html",
    }
    if not health.get("available"):
        return _fit_packet(_base("unavailable", source=source), budget=6_500)

    if (
        not isinstance(payload, dict)
        or payload.get("schema") != _CHINA_COMMAND_SCHEMA
        or payload.get("is_context_only") is not True
        or not isinstance(payload.get("command"), list)
    ):
        return _fit_packet(
            {
                **_base("unsupported_contract", source=source),
                "observed_contract": {
                    "schema": payload.get("schema") if isinstance(payload, dict) else None,
                    "is_context_only": (
                        payload.get("is_context_only") if isinstance(payload, dict) else None
                    ),
                },
            },
            budget=6_500,
        )

    rows = [
        row for row in payload["command"]
        if isinstance(row, dict)
        and str(row.get("ticker") or "").upper().strip() == symbol
    ]
    if not rows:
        return _fit_packet(
            {
                **_base("not_in_published_cohort", source=source),
                "publication": {
                    "schema": payload.get("schema"),
                    "as_of": payload.get("as_of"),
                    "generated_utc": payload.get("generated_utc"),
                    "n_universe": payload.get("n_universe"),
                    "command_count": len(payload["command"]),
                },
            },
            budget=6_500,
        )
    if len(rows) != 1:
        return _fit_packet(
            {
                **_base("ambiguous_published_identity", source=source),
                "matching_rows": len(rows),
            },
            budget=6_500,
        )

    row = rows[0]
    evidence = row.get("company_evidence")
    if (
        not isinstance(evidence, dict)
        or evidence.get("schema") != _CHINA_COMPANY_EVIDENCE_SOURCE_SCHEMA
        or evidence.get("is_context_only") is not True
    ):
        return _fit_packet(
            {
                **_base("unsupported_company_evidence_contract", source=source),
                "observed_contract": {
                    "schema": evidence.get("schema") if isinstance(evidence, dict) else None,
                    "is_context_only": (
                        evidence.get("is_context_only") if isinstance(evidence, dict) else None
                    ),
                },
            },
            budget=6_500,
        )

    upstream_authority = evidence.get("authority")
    if (
        not isinstance(upstream_authority, dict)
        or upstream_authority.get("ranking") != "none"
        or upstream_authority.get("prophet") != "none"
        or upstream_authority.get("trade") != "none"
    ):
        return _fit_packet(
            {
                **_base("authority_contract_refused", source=source),
                "observed_authority": _bounded_value(
                    upstream_authority,
                    list_limit=2,
                    dict_limit=8,
                    str_limit=100,
                    max_depth=2,
                ),
            },
            budget=6_500,
        )

    contradictions = (
        evidence.get("contradictions")
        if isinstance(evidence.get("contradictions"), list)
        else []
    )
    unknowns = (
        evidence.get("unknowns")
        if isinstance(evidence.get("unknowns"), list)
        else []
    )
    source_rows = (
        evidence.get("evidence")
        if isinstance(evidence.get("evidence"), list)
        else []
    )

    packet = {
        "schema": _CHINA_COMPANY_EVIDENCE_PACKET_SCHEMA,
        "status": "stale" if health.get("status") == "stale" else "ok",
        "ticker": symbol,
        "name": row.get("name"),
        "context_only": True,
        "execution_authority": False,
        "authority": authority,
        "source": {
            **source,
            "root_schema": payload.get("schema"),
            "root_as_of": payload.get("as_of"),
            "root_generated_utc": payload.get("generated_utc"),
            "company_schema": evidence.get("schema"),
        },
        "contradictions": contradictions[:6],
        "falsifier": {
            "en": row.get("falsifier"),
            "zh": row.get("falsifier_zh"),
        },
        "unknowns": unknowns[:12],
        "evidence_context": {
            "source_state": evidence.get("source_state"),
            "coverage_start": evidence.get("coverage_start"),
            "clocks": evidence.get("clocks"),
            "change": evidence.get("change"),
            "market_context": evidence.get("market_context"),
        },
        "evidence": source_rows[:6],
        "recognition": {
            "status": "not_attached_until_accepted_cie14",
            "may_multiply_conviction": False,
        },
        "prophet_timing": {
            "included": False,
            "reason": "separate_authority",
        },
    }
    return _fit_china_company_evidence(packet)


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


# Closed native wire identities; this reader does not own sector membership.
_PSL_GROUP_IDS = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")
_PSL_NATIVE_SCHEMA = "leadership_rotation_context.sector_dossiers/v1"
_PSL_PACKET_SCHEMA = "mastermind.portfolio_intelligence.sector_dossiers/v1"
_PSL_ARTIFACT = "site/sectordata/sector_central.json"
_PSL_FIELDS = ("rs_21d", "rs_63d")
_PSL_MAX_BYTES = 7200  # Below the existing serializer's 8,000-character/byte boundary.

# Exact-session companion: the same artifact and cohort, one explicitly selected sector.
PSL_SECTOR_IDS = _PSL_GROUP_IDS
_PSL_WINDOW_NATIVE_SCHEMA = "leadership_rotation_context.sector_window_measurements/v1"
_PSL_WINDOW_PACKET_SCHEMA = "mastermind.portfolio_intelligence.sector_window_measurements/v1"
_PSL_WINDOW_KEYS = ("5", "20", "63")
_PSL_WINDOW_SESSIONS = (5, 20, 63)
_PSL_WINDOW_EXPECTED = {"5": 6, "20": 21, "63": 64}
_PSL_WINDOW_MAX_INPUT_BYTES = 131072  # Native ceiling for one detached companion document.
_PSL_MEASUREMENT_REASONS = (
    "missing_input", "non_finite_input", "invalid_price", "benchmark_missing",
    "benchmark_invalid", "insufficient_reference_history", "empty_panel", "future_tail",
    "source_session_mismatch", "ambiguous_duplicate_price_index", "ambiguous_duplicate_column",
    "cohort_identity_mismatch", "benchmark_identity_mismatch", "return_basis_not_qualified",
)
_PSL_BLOCK_REASONS = _PSL_MEASUREMENT_REASONS[6:]
_PSL_BINDING_KEYS = (
    "benchmark", "clocks", "cohort_id", "price_basis", "receipt", "source_roots", "source_session",
)
# The native endpoint definition is a fixed literal of the pinned producer contract.
_PSL_WINDOW_ENDPOINT = (
    "Endpoint return: P(T)/P(S_N) - 1, where T is the explicit end session and S_N is the "
    "canonical US session exactly N positions before T, so a 5-session return spans 6 session "
    "endpoints. Relative wealth is (1+R_group)/(1+R_benchmark) - 1 -- a wealth ratio, never a "
    "return difference. Interior gaps never move an endpoint; they are disclosed as observed "
    "coverage. Prices are strictly positive, finite, total-return adjusted closes read at the two "
    "endpoints only."
)
# Separates an absent selector from an explicit null so neither can fall back to legacy.
_PSL_SECTOR_UNSET = object()


def _psl_schema() -> dict:
    """Validate the closed producer v1, including fields omitted by this projection."""
    def obj(**properties):
        return {"type": "object", "properties": properties,
                "required": list(properties), "additionalProperties": False}

    def literal(value):
        result = {"const": value}
        if isinstance(value, bool):
            result["type"] = "boolean"
        return result

    def nullable(value):
        return {"anyOf": [value, {"type": "null"}]}

    def count(maximum):
        return {"type": "integer", "minimum": 0, "maximum": maximum}

    def unavailable(reason, **extra):
        return obj(status=literal("unavailable"), reason=literal(reason), **extra)

    def windows(value):
        return obj(rs_21d=value, rs_63d=value)

    text = {"type": "string", "minLength": 1, "maxLength": 120,
            "pattern": r"^[^\x00-\x1f]+\Z"}
    reasons = {"type": "array", "items": text, "maxItems": 32, "uniqueItems": True}
    ids = {"type": "array", "items": {"enum": list(_PSL_GROUP_IDS)},
           "maxItems": 11, "uniqueItems": True}
    breadth = obj(expected_n=literal(11), measured_n=count(11),
                  positive_n=nullable(count(11)))
    return obj(
        schema=literal(_PSL_NATIVE_SCHEMA),
        status={"enum": ["partial", "unavailable"]},
        measurement_status={"enum": ["available", "partial", "unavailable"]},
        cohort_id=literal("us_sectors_11"), population=literal("eleven_sector_etf_proxies"),
        as_of=nullable({"type": "string", "format": "date", "pattern": r"^\d{4}-\d{2}-\d{2}\Z"}),
        benchmark=nullable({"type": "string", "pattern": r"^[A-Z][A-Z0-9.^-]{0,15}\Z",
                            "not": {"enum": ["UNKNOWN", "NONE", "NULL"]}}),
        price_basis={"enum": ["total_return", None]}, units=literal("pct"),
        windows_sessions=literal([21, 63]),
        unavailable_windows=obj(sessions=literal([5, 20]), reason=literal("not_supplied_by_owner")),
        absolute_returns=unavailable("not_supplied_by_owner"),
        compatibility_key=nullable({**text, "maxLength": 160}),
        source_generation=unavailable("immutable_generation_not_supplied", id=literal(None)),
        availability=obj(
            mode={"enum": ["dated_snapshot", "as_known"]},
            decision_cutoff=nullable({**text, "format": "date-time", "maxLength": 64}),
            original_available_at=literal(None), historically_admissible=literal(False),
            reason={"enum": ["original_availability_not_supplied", "invalid_decision_cutoff",
                             "source_session_after_decision_cutoff", "availability_time_missing"]}),
        history=obj(mode=literal("reconstructed_price_history"), naturally_observed=literal(False)),
        freshness=obj(status=literal("unverified"),
                      reason=literal("owner_freshness_receipt_not_supplied")),
        corrections=unavailable("native_revision_selection_not_supplied"),
        authority=obj(**{key: literal(False) for key in
                         ("may_rank", "may_gate", "may_size", "may_trade", "may_escalate")}),
        forecasts=obj(status=literal("not_qualified"), expected_return=literal(None),
                      persistence_estimate=literal(None), allocation_weight=literal(None)),
        mechanism=unavailable("no_qualified_evidence", owner=literal("engine.theme_graph")),
        risk=unavailable("no_qualified_risk_context", owner=literal("engine.risk_envelope"),
                         scope=literal(None)),
        constituent_breadth=unavailable("native_membership_not_supplied"),
        constituent_concentration=unavailable("native_weights_not_supplied"),
        cross_sector_breadth_counts=obj(**{"21": breadth, "63": breadth}),
        dependency_audit=obj(
            source_roots={"type": "array", "items": literal("engine.sector_cycles"),
                          "maxItems": 1, "uniqueItems": True},
            source_family_count=count(1), independence=literal("not_established"),
            shared_rolling_windows=literal(True), constituent_overlap=literal("unknown")),
        diagnostics=obj(
            qualification_reasons=reasons, duplicate_groups=ids,
            outside_cohort={"type": "array", "items": {
                "type": "string", "pattern": r"^[A-Z][A-Z0-9]{0,7}\Z"},
                "maxItems": 11, "uniqueItems": True},
            malformed_source_rows=count(128), malformed_measured_rows=count(128)),
        groups={"type": "array", "minItems": 11, "maxItems": 11, "items": obj(
            group_id={"enum": list(_PSL_GROUP_IDS)}, name_en=nullable(text),
            name_zh=nullable(text), status={"enum": ["available", "partial", "unavailable"]},
            relative_wealth_pct=windows(nullable({"type": "number", "minimum": -100})),
            null_reasons=windows(nullable(text)), qualification_reasons=reasons)},
    )


def _psl_consistent(dossier: dict, measured: dict) -> bool:
    generation = measured.get("generation")
    if not isinstance(generation, dict) or generation.get("cohort_id") != "us_sectors_11":
        return False
    for native, parent in (("as_of", "session_end"), ("benchmark", "benchmark"),
                           ("price_basis", "price_basis"), ("compatibility_key", "id")):
        if dossier[native] is not None and dossier[native] != generation.get(parent):
            return False
    parents = measured.get("groups")
    if not isinstance(parents, list) or len(parents) != 11:
        return False
    by_id = {}
    for row in parents:
        if (not isinstance(row, dict) or row.get("group_id") not in _PSL_GROUP_IDS
                or row.get("group_kind") != "sector" or row["group_id"] in by_id):
            return False
        by_id[row["group_id"]] = row
    seen, available, any_values = set(), 0, False
    for row in dossier["groups"]:
        gid = row["group_id"]
        if gid in seen:
            return False
        seen.add(gid)
        current = by_id[gid].get("current")
        if (not isinstance(current, dict) or current.get("metric") != "relative_wealth_pct"
                or current.get("units") != "pct"):
            return False
        n = 0
        for key in _PSL_FIELDS:
            value, reason = row["relative_wealth_pct"][key], row["null_reasons"][key]
            if value is None:
                if reason is None:
                    return False
            else:
                if (reason is not None or row["qualification_reasons"]
                        or type(current.get(key)) not in (int, float) or current[key] != value):
                    return False
                n += 1
        if row["status"] != ("available" if n == 2 else "partial" if n else "unavailable"):
            return False
        available += n == 2
        any_values |= n > 0
    if (dossier["measurement_status"] !=
            ("available" if available == 11 else "partial" if any_values else "unavailable")
            or dossier["status"] != ("partial" if any_values else "unavailable")):
        return False
    diagnostics = dossier["diagnostics"]
    if diagnostics["qualification_reasons"] and any_values:
        return False
    if set(diagnostics["outside_cohort"]) & set(_PSL_GROUP_IDS):
        return False
    rows = {row["group_id"]: row for row in dossier["groups"]}
    if any(rows[gid]["status"] != "unavailable" for gid in diagnostics["duplicate_groups"]):
        return False
    for window, field in zip(("21", "63"), _PSL_FIELDS):
        values = [row["relative_wealth_pct"][field] for row in dossier["groups"]
                  if row["relative_wealth_pct"][field] is not None]
        counts = dossier["cross_sector_breadth_counts"][window]
        if (counts["measured_n"] != len(values)
                or counts["positive_n"] != (sum(value > 0 for value in values) if values else None)):
            return False
    dependency = dossier["dependency_audit"]
    if dependency["source_family_count"] != len(dependency["source_roots"]):
        return False
    if any_values and (dossier["as_of"] is None or dossier["benchmark"] is None
                       or dossier["price_basis"] != "total_return"
                       or dependency["source_family_count"] != 1):
        return False
    availability = dossier["availability"]
    if availability["mode"] == "dated_snapshot":
        if (availability["decision_cutoff"] is not None
                or availability["reason"] != "original_availability_not_supplied"):
            return False
    elif (any_values or availability["reason"] == "original_availability_not_supplied"
          or (availability["reason"] == "invalid_decision_cutoff") !=
             (availability["decision_cutoff"] is None)):
        return False
    return True


_PSL_NATIVE_MEMBER = "sectordata/sector_central.json"
_PSL_NATIVE_REASONS = frozenset((
    "native_generation_not_configured", "native_generation_configuration_invalid",
    "native_generation_reader_unavailable", "native_generation_not_selected",
    "native_generation_unavailable", "native_generation_contract_invalid",
    "native_generation_too_large",
))
_PSL_CONSUMER_REASONS = frozenset((
    "invalid_legacy_rotation_input", "native_legacy_transport_budget_exceeded",
    "native_surface_content_budget_exceeded", "native_surface_transport_budget_exceeded",
    "native_catalog_transport_budget_exceeded", "native_market_transport_budget_exceeded",
))
_PSL_RECEIPT_LIMITS = {
    "schema": 32, "source": 32, "generation_id": 128, "source_session": 10,
    "published_at": 32, "qualification": 8, "input_version": 128,
    "baseline_session": 10, "content_sha256": 64,
}


def _read_sector_central() -> tuple[dict | None, dict]:
    """Read one existing selected snapshot; never initialize, select or fall back.

    Deployment supplies the same private root used by Macro. Its incumbent
    facade owns pointer/manifest/member verification; its projection owns source
    semantics and the public receipt. Existing Portfolio parsers still consume
    the original captured Central, whose legacy fields exceed preview core.
    """
    health = {
        "artifact": _PSL_NATIVE_MEMBER, "source_mode": "selected_generation",
        "available": False, "status": "missing", "as_of": None, "stale": None,
        "authority": "context", "execution_authority": False,
    }

    def unavailable(reason: str, status: str = "missing") -> tuple[None, dict]:
        return None, {**health, "status": status, "source_reason": reason}

    configured = os.environ.get("MACRO_SECTOR_GENERATIONS_ROOT")
    if configured is None:
        return unavailable("native_generation_not_configured")
    if (not configured or configured != configured.strip()
            or len(configured) > 4096 or "\x00" in configured):
        return unavailable("native_generation_configuration_invalid", "malformed")
    root = Path(configured)
    if not root.is_absolute() or root == Path("/") or ".." in root.parts:
        return unavailable("native_generation_configuration_invalid", "malformed")
    # Do not resolve symlinks away: the native facade must inspect the original
    # deployment root and ancestors. No caller path or generation selector exists.
    try:
        from lib.sector_generation_contract import (
            SECTOR_GENERATION_DOMAIN, SECTOR_GENERATION_MEMBERS,
            SectorGenerationContractError, _decode_member, project_sector_bundle,
        )
        from lib.sector_generation_wire import SectorGenerationTooLarge, encode_sector_generation
        from engine.sector_native_view import SectorViewUnavailable
        from scripts.vps_live_orchestrator import (
            SelectedGenerationAbsent, SelectedGenerationUnavailable, read_selected_generation,
        )
    except ImportError:
        return unavailable("native_generation_reader_unavailable")
    try:
        snapshot = read_selected_generation(
            generations_root=root, domain=SECTOR_GENERATION_DOMAIN,
            members=SECTOR_GENERATION_MEMBERS,
        )
    except SelectedGenerationAbsent:
        return unavailable("native_generation_not_selected")
    except (SelectedGenerationUnavailable, OSError):
        return unavailable("native_generation_unavailable")
    try:
        # Observe after the one capture; never consult the selected pointer again.
        now = datetime.now(UTC)
        projection = project_sector_bundle(
            member_bytes=snapshot.members,
            input_identity=snapshot.manifest.get("input_identity"),
            generation_id=snapshot.generation_id, published_at=snapshot.published_at,
            now=now, audience="preview", preview_rows=3,
        )
        receipt = projection["receipt"]
        encode_sector_generation(
            audience="preview", source_session=receipt["source_session"],
            published_at=receipt["published_at"], qualification=receipt["qualification"],
            projection=projection,
        )
        central = _decode_member(snapshot.members[_PSL_NATIVE_MEMBER])
    except SectorGenerationTooLarge:
        return unavailable("native_generation_too_large", "malformed")
    except (SectorGenerationContractError, SectorViewUnavailable, ValueError, TypeError,
            KeyError, OverflowError, RecursionError):
        return unavailable("native_generation_contract_invalid", "malformed")
    qualification = receipt["qualification"]
    return central, {
        **health, "available": True,
        "status": {"accepted": "fresh", "stale": "stale"}.get(qualification, "unknown"),
        "as_of": receipt["source_session"],
        "stale": {"accepted": False, "stale": True}.get(qualification),
        # This is the owner's authorized-representation hash, not a hash of a
        # Portfolio packet, raw Central, or a second snapshot.
        "native_receipt": dict(receipt),
    }


def _psl_health(health: Any) -> dict:
    """Bound the existing artifact-health disclosure without upgrading native clocks."""
    health = health if isinstance(health, dict) else {}
    status = health.get("status")
    stamp = health.get("as_of")
    result = {
        "status": status if status in ("missing", "malformed", "undated", "stale", "fresh") else "unknown",
        "as_of": stamp if isinstance(stamp, str) and 0 < len(stamp) <= 64
        and not any(ord(char) < 32 for char in stamp) else None,
        "stale": health.get("stale") if isinstance(health.get("stale"), bool) else None,
        "execution_authority": False,
    }
    if health.get("source_mode") == "selected_generation":
        result.update(source_mode="selected_generation", source_member=_PSL_NATIVE_MEMBER)
        reason = health.get("source_reason")
        if isinstance(reason, str) and reason in (_PSL_NATIVE_REASONS | _PSL_CONSUMER_REASONS):
            result["source_reason"] = reason
        receipt = health.get("native_receipt")
        # Bound an additive disclosure, not a second source-admission scheme.
        # Only the existing native owner above constructs the source receipt.
        if (isinstance(receipt, dict) and set(receipt) == set(_PSL_RECEIPT_LIMITS)
                and receipt.get("schema") == "sector_native_view.receipt.v1"
                and receipt.get("source") == "macro.sector"
                and receipt.get("qualification") in ("accepted", "stale", "degraded")
                and all((key == "baseline_session" and value is None)
                        or (isinstance(value, str) and 0 < len(value) <= _PSL_RECEIPT_LIMITS[key]
                            and not any(ord(char) < 32 for char in value))
                        for key, value in receipt.items())):
            result["native_receipt"] = dict(receipt)
    return result


def _native_consumer_refusal(health: dict, reason: str) -> dict:
    """Preserve the captured receipt while refusing this consumer representation."""
    return {**_psl_health(health), "available": False, "status": "unknown",
            "source_reason": reason}


def _native_packet_refusal(schema: str, health: dict, reason: str) -> dict:
    """Whole-packet refusal before generic compaction can remove native evidence."""
    return {
        "schema": schema, "status": "unavailable", "consumer_reason": reason,
        "context_only": True, "execution_authority": False, "packet_truncated": False,
        "source": _source_ref(_native_consumer_refusal(health, reason)),
    }


def _psl_unavailable(reason: str, health: Any = None) -> dict:
    """Consumer refusal: expected identities are explicit, never represented as source facts."""
    return {
        "schema": _PSL_PACKET_SCHEMA, "source_schema": None, "source_artifact": _PSL_ARTIFACT,
        "context_only": True, "status": "unavailable", "measurement_status": "unavailable",
        "consumer_reason": reason, "cohort_id": "us_sectors_11",
        "population": "eleven_sector_etf_proxies", "cohort_status": "expected_not_admitted",
        "as_of": None, "benchmark": None, "price_basis": None, "units": "pct",
        "windows_sessions": [21, 63], "compatibility_key": None,
        "source_generation": {"status": "unavailable", "id": None, "reason": reason},
        "availability": {"mode": "unavailable", "decision_cutoff": None,
                         "original_available_at": None, "historically_admissible": False,
                         "reason": reason},
        "history": {"mode": "unavailable", "naturally_observed": False},
        "freshness": {"status": "unverified", "reason": reason},
        "corrections": {"status": "unavailable", "reason": reason},
        "authority": {key: False for key in
                      ("may_rank", "may_gate", "may_size", "may_trade", "may_escalate")},
        "forecasts": {"status": "not_qualified", "expected_return": None,
                      "persistence_estimate": None, "allocation_weight": None},
        "mechanism": {"status": "unavailable", "reason": reason},
        "risk": {"status": "unavailable", "reason": reason},
        "artifact_health": _psl_health(health),
        "cross_sector_breadth_counts": {
            window: {"expected_n": 11, "measured_n": 0, "positive_n": None}
            for window in ("21", "63")},
        "row_encoding": {"values": "windows_sessions order", "reasons": "reason_table indexes"},
        "reason_table": [reason],
        "groups": [{"group_id": gid, "status": "unavailable",
                    "relative_wealth_pct": [None, None], "null_reason_refs": [0, 0],
                    "qualification_reason_refs": [0]} for gid in _PSL_GROUP_IDS],
    }


def _sector_dossier_projection(data: Any, health: Any) -> dict:
    """Project one validated native dossier within the unchanged MCP transport budget."""
    if not isinstance(data, dict) or "measured_read" not in data:
        return _psl_unavailable("dossier_not_supplied", health)
    measured = data["measured_read"]
    if not isinstance(measured, dict):
        return _psl_unavailable("invalid_dossier_contract", health)
    if "sector_dossiers" not in measured:
        return _psl_unavailable("dossier_not_supplied", health)
    if (measured.get("schema") != "leadership_rotation_context.measured_group_read/v1"
            or measured.get("status") not in ("available", "partial", "unavailable")):
        return _psl_unavailable("invalid_dossier_contract", health)
    try:
        # JSON detachment rejects nonfinite/non-JSON input and bounds the native addendum.
        encoded = json.dumps(measured["sector_dossiers"], ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > 32768:
            return _psl_unavailable("dossier_input_budget_exceeded", health)
        dossier = json.loads(encoded)
        from jsonschema import Draft202012Validator, FormatChecker

        if (not Draft202012Validator(_psl_schema(), format_checker=FormatChecker()).is_valid(dossier)
                or not _psl_consistent(dossier, measured)):
            return _psl_unavailable("invalid_dossier_contract", health)
    except (TypeError, ValueError, RecursionError, OverflowError):
        return _psl_unavailable("invalid_dossier_contract", health)

    reasons = sorted({reason for row in dossier["groups"]
                      for reason in [*row["null_reasons"].values(), *row["qualification_reasons"]]
                      if reason is not None})
    reason_ids = {reason: index for index, reason in enumerate(reasons)}
    packet = {key: value for key, value in dossier.items() if key != "groups"}
    packet.update({
        "schema": _PSL_PACKET_SCHEMA, "source_schema": _PSL_NATIVE_SCHEMA,
        "source_artifact": _PSL_ARTIFACT, "context_only": True, "consumer_reason": None,
        "cohort_status": "native_contract_admitted", "artifact_health": _psl_health(health),
        "row_encoding": {"values": "windows_sessions order", "reasons": "reason_table indexes"},
        "reason_table": reasons,
        "groups": [{
            "group_id": row["group_id"], "status": row["status"],
            "relative_wealth_pct": [row["relative_wealth_pct"][field] for field in _PSL_FIELDS],
            "null_reason_refs": [reason_ids.get(row["null_reasons"][field]) for field in _PSL_FIELDS],
            "qualification_reason_refs": [reason_ids[reason] for reason in row["qualification_reasons"]],
        } for row in dossier["groups"]],
    })
    # Both the current character budget and the held stricter byte-budget proposal are met.
    # If exact reasons cannot fit, refuse the whole projection; never silently drop a sector.
    if len(json.dumps(packet, ensure_ascii=False, allow_nan=False).encode("utf-8")) > _PSL_MAX_BYTES:
        return _psl_unavailable("dossier_transport_budget_exceeded", health)
    return packet


def _psl_window_schema() -> dict:
    """Validate the closed exact-session companion, including fields this projection omits."""
    def obj(**properties):
        return {"type": "object", "properties": properties,
                "required": list(properties), "additionalProperties": False}

    def literal(value):
        result = {"const": value}
        if isinstance(value, bool):
            result["type"] = "boolean"
        return result

    def nullable(value):
        return {"anyOf": [value, {"type": "null"}]}

    def count(maximum):
        return {"type": "integer", "minimum": 0, "maximum": maximum}

    text = {"type": "string", "minLength": 1, "maxLength": 120,
            "pattern": r"^[^\x00-\x1f]+\Z"}
    reason = {"enum": list(_PSL_MEASUREMENT_REASONS)}
    block = {"enum": list(_PSL_BLOCK_REASONS)}
    iso_date = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}\Z"}
    clock = {"type": "string", "minLength": 1, "maxLength": 64,
             "pattern": r"^[^\x00-\x1f]+\Z"}

    def coverage():
        return obj(observed_n=count(64), expected_n=count(64),
                   ratio={"type": "number", "minimum": 0, "maximum": 1})

    def clock_limitation(owner_reason):
        return {"anyOf": [
            obj(status=literal("unknown"), reason=literal(owner_reason)),
            obj(status=literal("supplied"), clock=clock),
        ]}

    cell = obj(
        status={"enum": ["available", "partial", "unavailable"]},
        absolute_return_pct=nullable({"type": "number", "minimum": -100}),
        relative_wealth_pct=nullable({"type": "number", "minimum": -100}),
        null_reasons=obj(absolute_return_pct=nullable(reason),
                         relative_wealth_pct=nullable(reason)),
        coverage=coverage(),
    )
    window = obj(
        window_sessions=count(63),
        status={"enum": ["available", "partial", "unavailable"]},
        start_session=nullable(iso_date),
        end_session=iso_date,
        benchmark_return_pct=nullable({"type": "number", "minimum": -100}),
        benchmark_null_reason=nullable(reason),
        benchmark_coverage=coverage(),
        null_reason=nullable(reason),
    )
    group = obj(
        group_id={"enum": list(_PSL_GROUP_IDS)},
        name_en=nullable(text),
        name_zh=nullable(text),
        windows=obj(**{key: cell for key in _PSL_WINDOW_KEYS}),
    )
    return obj(
        schema=literal(_PSL_WINDOW_NATIVE_SCHEMA),
        status={"enum": ["available", "partial", "unavailable"]},
        reason=nullable(reason),
        units=literal("pct"),
        price_basis=literal("total_return"),
        benchmark={"type": "string", "pattern": r"^[A-Z][A-Z0-9.^-]{0,15}\Z",
                   "not": {"enum": ["UNKNOWN", "NONE", "NULL"]}},
        cohort_id=literal("us_sectors_11"),
        population=literal("eleven_sector_etf_proxies"),
        source_session=iso_date,
        end_session=iso_date,
        windows_sessions=literal([5, 20, 63]),
        endpoint_definition=literal(_PSL_WINDOW_ENDPOINT),
        clocks=obj(publication=nullable(clock), availability=nullable(clock),
                   correction=nullable(clock), history=nullable(clock)),
        source_roots={"type": "array", "maxItems": 32, "items": {
            "type": "string", "minLength": 1, "maxLength": 256,
            "pattern": r"^[^\x00-\x1f]+\Z"}},
        receipt=nullable({"type": "object"}),
        limitations=obj(
            availability=clock_limitation("owner_availability_clock_not_supplied"),
            publication=clock_limitation("owner_publication_clock_not_supplied"),
            history=clock_limitation("owner_history_clock_not_supplied"),
            corrections=obj(status=literal("unavailable"),
                            reason=literal("native_revision_selection_not_supplied")),
            freshness=obj(status=literal("unverified"),
                          reason=literal("owner_freshness_receipt_not_supplied")),
            point_in_time=obj(status=literal("not_qualified"),
                              reason=literal("point_in_time_admission_not_supplied")),
        ),
        windows=obj(**{key: window for key in _PSL_WINDOW_KEYS}),
        groups={"type": "array", "minItems": 11, "maxItems": 11, "items": group},
        diagnostics=obj(
            panel_rows=count(20000),
            malformed_rows=count(9007199254740991),
            duplicate_sessions={"type": "array", "maxItems": 16, "items": {
                "type": "string", "minLength": 1, "maxLength": 64}},
            ambiguous_columns={"type": "array", "maxItems": 16, "items": {
                "type": "string", "minLength": 1, "maxLength": 64}},
            columns={"type": "array", "maxItems": 64, "items": {
                "type": "string", "minLength": 1, "maxLength": 64}},
            binding_keys={"type": "array", "maxItems": 7, "uniqueItems": True,
                          "items": {"enum": list(_PSL_BINDING_KEYS)}},
            receipt_withheld={"type": "boolean"},
            future_tail_sessions={"type": "array", "maxItems": 16, "items": iso_date},
            expected_columns=literal(12),
            qualification_reasons={"type": "array", "maxItems": 8, "uniqueItems": True,
                                   "items": block},
            measured_cells=count(33),
            complete_cells=count(33),
            total_cells=literal(33),
            coverage_note={"type": "string", "minLength": 1, "maxLength": 256},
        ),
        authority=obj(**{key: literal(False) for key in
                         ("may_rank", "may_gate", "may_size", "may_trade", "may_escalate")}),
    )


def _psl_real_date(value: Any) -> date | None:
    """Accept only a strict, real YYYY-MM-DD calendar date."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _psl_aware_clock(value: Any) -> bool:
    """Accept the producer's timezone-aware ISO text; never restamp or infer a clock."""
    if value is None:
        return True
    if not isinstance(value, str) or not 0 < len(value) <= 64:
        return False
    if any(ord(char) < 32 for char in value):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _psl_coverage_ok(observed: Any, expected: Any, ratio: Any) -> bool:
    """A published ratio must agree with its own counts within the six-decimal rounding."""
    if not isinstance(observed, int) or isinstance(observed, bool):
        return False
    if not isinstance(expected, int) or isinstance(expected, bool):
        return False
    if expected <= 0 or not 0 <= observed <= expected:
        return False
    if not isinstance(ratio, (int, float)) or isinstance(ratio, bool):
        return False
    return abs(ratio - round(observed / expected, 6)) <= 1e-6


def _psl_json_preflight(value: Any, *, byte_limit: int,
                        depth_limit: int, node_limit: int) -> None:
    """Bound exact builtin JSON before copying or serializing a container.

    Match the producer's default ASCII encoding and separator spaces. The
    length limit applies to each container; keys count bytes, values count
    nodes, and receipt depth starts at zero. No custom conversion hook runs.
    """
    nodes, encoded = 0, 0
    active: set[int] = set()

    def invalid():
        raise ValueError("invalid_window_contract")

    def add(size):
        nonlocal encoded
        encoded += size
        if encoded > byte_limit:
            raise ValueError("window_input_budget_exceeded")

    def string_size(text):
        if type(text) is not str:
            invalid()
        if len(text) > byte_limit:
            raise ValueError("window_input_budget_exceeded")
        add(2)
        for char in text:
            point = ord(char)
            add(2 if char in '"\\\b\f\n\r\t' else
                6 if point < 32 or 127 <= point <= 65535 else
                12 if point > 65535 else 1)

    def walk(node, depth):
        nonlocal nodes
        nodes += 1
        if nodes > node_limit or depth > depth_limit:
            invalid()
        kind = type(node)
        if node is None:
            add(4)
        elif kind is bool:
            add(4 if node else 5)
        elif kind is str:
            string_size(node)
        elif kind in (int, float):
            if kind is int and node.bit_length() > byte_limit * 4:
                raise ValueError("window_input_budget_exceeded")
            if kind is float and not math.isfinite(node):
                invalid()
            # Only an already bounded primitive is serialized here.
            add(len(json.dumps(node, allow_nan=False)))
        elif kind in (dict, list):
            if len(node) > 256 or id(node) in active:
                invalid()
            active.add(id(node))
            add(2 + max(0, len(node) - 1) * 2)
            try:
                if kind is dict:
                    for key, child in node.items():
                        string_size(key)
                        add(2)
                        walk(child, depth + 1)
                else:
                    for child in node:
                        walk(child, depth + 1)
            finally:
                active.remove(id(node))
        else:
            invalid()

    walk(value, 0)


def _psl_receipt_ok(receipt: Any) -> bool:
    """Qualify the opaque owner receipt before detachment; never infer authority."""
    if receipt is None:
        return True
    if type(receipt) is not dict or len(receipt) > 32:
        return False
    try:
        _psl_json_preflight(receipt, byte_limit=16384, depth_limit=8, node_limit=2048)
    except (TypeError, ValueError, RecursionError, OverflowError):
        return False
    return True


def _psl_window_consistent(companion: dict, measured: dict) -> bool:
    """Admit one companion only against the exact parent binding and the closed native contract."""
    if (measured.get("schema") != "leadership_rotation_context.measured_group_read/v1"
            or measured.get("status") not in ("available", "partial", "unavailable")):
        return False
    generation = measured.get("generation")
    if not isinstance(generation, dict):
        return False
    if generation.get("cohort_id") != companion["cohort_id"]:
        return False
    if generation.get("price_basis") != companion["price_basis"]:
        return False
    end = _psl_real_date(companion["end_session"])
    source = _psl_real_date(companion["source_session"])
    if end is None or source is None or end != source:
        return False
    if generation.get("session_end") != companion["end_session"]:
        return False
    parent_benchmark = generation.get("benchmark")
    if not isinstance(parent_benchmark, str):
        return False
    if parent_benchmark.strip().upper() != companion["benchmark"]:
        return False

    clocks = companion["clocks"]
    for name, owner_reason in (("availability", "owner_availability_clock_not_supplied"),
                                ("publication", "owner_publication_clock_not_supplied"),
                                ("history", "owner_history_clock_not_supplied")):
        clock = clocks[name]
        if not _psl_aware_clock(clock):
            return False
        limitation = companion["limitations"][name]
        if clock is None:
            if limitation != {"status": "unknown", "reason": owner_reason}:
                return False
        elif limitation != {"status": "supplied", "clock": clock}:
            return False
    if not _psl_aware_clock(clocks["correction"]):
        return False
    if not _psl_receipt_ok(companion["receipt"]):
        return False

    groups = companion["groups"]
    if [row["group_id"] for row in groups] != list(_PSL_GROUP_IDS):
        return False
    measured_cells = 0
    complete_cells = 0
    per_window_measured = {key: 0 for key in _PSL_WINDOW_KEYS}
    per_window_complete = {key: 0 for key in _PSL_WINDOW_KEYS}
    for row in groups:
        for key in _PSL_WINDOW_KEYS:
            cell = row["windows"][key]
            absolute = cell["absolute_return_pct"]
            relative = cell["relative_wealth_pct"]
            reasons = cell["null_reasons"]
            if (absolute is None) == (reasons["absolute_return_pct"] is None):
                return False
            if (relative is None) == (reasons["relative_wealth_pct"] is None):
                return False
            present = (absolute is not None) + (relative is not None)
            status = ("available" if present == 2 else "partial" if present == 1 else "unavailable")
            if cell["status"] != status:
                return False
            coverage = cell["coverage"]
            if coverage["expected_n"] != _PSL_WINDOW_EXPECTED[key]:
                return False
            if not _psl_coverage_ok(coverage["observed_n"], coverage["expected_n"],
                                    coverage["ratio"]):
                return False
            measured_cells += present > 0
            complete_cells += present == 2
            per_window_measured[key] += present > 0
            per_window_complete[key] += present == 2

    block_reason = companion["reason"]
    diagnostics = companion["diagnostics"]
    if companion["receipt"] is not None and diagnostics["receipt_withheld"]:
        return False
    count_fields = ("panel_rows", "malformed_rows", "expected_columns",
                    "measured_cells", "complete_cells", "total_cells")
    if any(type(diagnostics[name]) is not int for name in count_fields):
        return False
    if any(type(value) is not int for value in companion["windows_sessions"]):
        return False
    for name in ("duplicate_sessions", "future_tail_sessions"):
        for value in diagnostics[name]:
            parsed = _psl_real_date(value)
            if parsed is None or (name == "future_tail_sessions" and parsed <= end):
                return False
    window_only_reasons = set(_PSL_BLOCK_REASONS) | {"insufficient_reference_history"}
    if block_reason is not None:
        if block_reason not in _PSL_BLOCK_REASONS or companion["status"] != "unavailable":
            return False
        if (not diagnostics["qualification_reasons"]
                or diagnostics["qualification_reasons"][0] != block_reason):
            return False
        if measured_cells or complete_cells:
            return False
    else:
        if diagnostics["qualification_reasons"]:
            return False
        expected_status = ("available" if complete_cells == 33
                           else "partial" if measured_cells else "unavailable")
        if companion["status"] != expected_status:
            return False

    for key in _PSL_WINDOW_KEYS:
        window = companion["windows"][key]
        if type(window["window_sessions"]) is not int or window["window_sessions"] != int(key):
            return False
        if window["end_session"] != companion["end_session"]:
            return False
        start = window["start_session"]
        insufficient = start is None
        if not insufficient:
            parsed = _psl_real_date(start)
            if parsed is None or parsed >= end:
                return False
        if (window["benchmark_return_pct"] is None) == (window["benchmark_null_reason"] is None):
            return False
        benchmark_coverage = window["benchmark_coverage"]
        if benchmark_coverage["expected_n"] != _PSL_WINDOW_EXPECTED[key]:
            return False
        if not _psl_coverage_ok(benchmark_coverage["observed_n"],
                                benchmark_coverage["expected_n"],
                                benchmark_coverage["ratio"]):
            return False
        if (window["benchmark_return_pct"] is not None
                and benchmark_coverage["observed_n"] < 2):
            return False
        complete = per_window_complete[key]
        present = per_window_measured[key]
        status = ("available" if complete == 11 else "partial" if present else "unavailable")
        if window["status"] != status:
            return False
        if insufficient:
            # Insufficient reference history takes precedence for this window.
            if (window["null_reason"] != "insufficient_reference_history"
                    or window["benchmark_return_pct"] is not None
                    or window["benchmark_null_reason"] != "insufficient_reference_history"):
                return False
            if (benchmark_coverage["observed_n"] != 0
                    or abs(benchmark_coverage["ratio"]) > 1e-9):
                return False
        else:
            if block_reason is not None:
                if (window["null_reason"] != block_reason
                        or window["benchmark_return_pct"] is not None
                        or window["benchmark_null_reason"] != block_reason):
                    return False
            elif (window["null_reason"] is not None
                  or window["benchmark_null_reason"] in window_only_reasons):
                return False
        for row in groups:
            cell = row["windows"][key]
            coverage = cell["coverage"]
            absolute, relative = cell["absolute_return_pct"], cell["relative_wealth_pct"]
            reasons = cell["null_reasons"]
            if (absolute is not None or relative is not None) and coverage["observed_n"] < 2:
                return False
            if relative is not None and window["benchmark_return_pct"] is None:
                return False
            # A finite relative wealth needs valid endpoints. Absolute publication can
            # still overflow when converting the independently finite factor to percent.
            if (relative is not None and absolute is None
                    and reasons["absolute_return_pct"] != "non_finite_input"):
                return False
            if (not insufficient and block_reason is None
                    and any(reason in window_only_reasons for reason in reasons.values())):
                return False
            if insufficient:
                if (cell["absolute_return_pct"] is not None
                        or cell["relative_wealth_pct"] is not None):
                    return False
                if (cell["null_reasons"]["absolute_return_pct"]
                        != "insufficient_reference_history"
                        or cell["null_reasons"]["relative_wealth_pct"]
                        != "insufficient_reference_history"):
                    return False
                if coverage["observed_n"] != 0 or abs(coverage["ratio"]) > 1e-9:
                    return False
            elif block_reason is not None:
                if (cell["absolute_return_pct"] is not None
                        or cell["relative_wealth_pct"] is not None):
                    return False
                if (cell["null_reasons"]["absolute_return_pct"] != block_reason
                        or cell["null_reasons"]["relative_wealth_pct"] != block_reason):
                    return False

    windows = companion["windows"]
    # These nested windows retain counts from one panel with one end session.
    for short, long, extra in (("5", "20", 15), ("20", "63", 43)):
        if windows[short]["start_session"] is None or windows[long]["start_session"] is None:
            continue
        pairs = [(windows[short]["benchmark_coverage"]["observed_n"],
                  windows[long]["benchmark_coverage"]["observed_n"])]
        pairs.extend((row["windows"][short]["coverage"]["observed_n"],
                      row["windows"][long]["coverage"]["observed_n"]) for row in groups)
        if any(b < a or b - a > extra for a, b in pairs):
            return False

    if (diagnostics["measured_cells"] != measured_cells
            or diagnostics["complete_cells"] != complete_cells
            or diagnostics["total_cells"] != 33):
        return False
    if diagnostics["columns"] != sorted(diagnostics["columns"]):
        return False
    if diagnostics["qualification_reasons"] != sorted(diagnostics["qualification_reasons"]):
        return False
    for key in ("duplicate_sessions", "ambiguous_columns", "future_tail_sessions"):
        if diagnostics[key] != sorted(diagnostics[key]):
            return False
    if diagnostics["binding_keys"] != sorted(diagnostics["binding_keys"]):
        return False
    return True


def _psl_window_unavailable(reason: str, health: Any = None, sector: Any = None) -> dict:
    """Consumer refusal: expected identities stay explicit and no source fact is invented."""
    return {
        "schema": _PSL_WINDOW_PACKET_SCHEMA, "source_schema": None,
        "source_artifact": _PSL_ARTIFACT, "context_only": True, "consumer_reason": reason,
        "cohort_id": "us_sectors_11", "population": "eleven_sector_etf_proxies",
        "cohort_status": "expected_not_admitted",
        "selected_group_id": sector if isinstance(sector, str) and sector in _PSL_GROUP_IDS else None,
        "status": "unavailable", "reason": None,
        "source_session": None, "end_session": None, "benchmark": None, "price_basis": None,
        "units": "pct", "windows_sessions": list(_PSL_WINDOW_SESSIONS),
        "endpoint_definition": None,
        "clocks": {"publication": None, "availability": None, "correction": None, "history": None},
        "limitations": {
            "availability": {"status": "unknown",
                             "reason": "owner_availability_clock_not_supplied"},
            "publication": {"status": "unknown",
                            "reason": "owner_publication_clock_not_supplied"},
            "history": {"status": "unknown", "reason": "owner_history_clock_not_supplied"},
            "corrections": {"status": "unavailable",
                            "reason": "native_revision_selection_not_supplied"},
            "freshness": {"status": "unverified",
                          "reason": "owner_freshness_receipt_not_supplied"},
            "point_in_time": {"status": "not_qualified",
                              "reason": "point_in_time_admission_not_supplied"},
        },
        "authority": {key: False for key in
                      ("may_rank", "may_gate", "may_size", "may_trade", "may_escalate")},
        "artifact_health": _psl_health(health),
        "metadata_projection": {"receipt": "not_projected", "source_roots": "not_projected"},
        "row_encoding": {"windows": "keys 5,20,63", "values": "windows_sessions order",
                         "reasons": "reason_table indexes"},
        "reason_table": [reason],
        "groups": [{"group_id": gid, "scope": "expected_not_admitted"} for gid in _PSL_GROUP_IDS],
        "selected": None,
        "windows": {},
        "diagnostics": {"measured_cells": 0, "complete_cells": 0, "total_cells": 33,
                        "block_reason_ref": 0, "qualification_reason_refs": []},
    }


def _sector_window_projection(data: Any, health: Any, sector: str) -> dict:
    """Project one validated exact-session companion for one explicitly selected sector."""
    if not isinstance(data, dict) or "measured_read" not in data:
        return _psl_window_unavailable("window_companion_not_supplied", health, sector)
    measured = data["measured_read"]
    if not isinstance(measured, dict):
        return _psl_window_unavailable("invalid_window_contract", health, sector)
    if "sector_window_measurements" not in measured:
        return _psl_window_unavailable("window_companion_not_supplied", health, sector)
    try:
        raw = measured["sector_window_measurements"]
        if type(raw) is not dict or not _psl_receipt_ok(raw.get("receipt")):
            return _psl_window_unavailable("invalid_window_contract", health, sector)
        try:
            _psl_json_preflight(raw, byte_limit=_PSL_WINDOW_MAX_INPUT_BYTES,
                                depth_limit=16, node_limit=8192)
        except ValueError as exc:
            reason = ("window_input_budget_exceeded"
                      if str(exc) == "window_input_budget_exceeded"
                      else "invalid_window_contract")
            return _psl_window_unavailable(reason, health, sector)
        # Detachment occurs only after bounded, finite, exact-builtin admission.
        companion = json.loads(json.dumps(raw, allow_nan=False))
        from jsonschema import Draft202012Validator

        if (not Draft202012Validator(_psl_window_schema()).is_valid(companion)
                or not _psl_window_consistent(companion, measured)):
            return _psl_window_unavailable("invalid_window_contract", health, sector)
    except (TypeError, ValueError, RecursionError, OverflowError):
        return _psl_window_unavailable("invalid_window_contract", health, sector)

    groups = companion["groups"]
    selected = next(row for row in groups if row["group_id"] == sector)
    used = set()
    if companion["reason"] is not None:
        used.add(companion["reason"])
    used.update(companion["diagnostics"]["qualification_reasons"])
    for key in _PSL_WINDOW_KEYS:
        window = companion["windows"][key]
        for value in (window["null_reason"], window["benchmark_null_reason"]):
            if value is not None:
                used.add(value)
    for key in _PSL_WINDOW_KEYS:
        for value in selected["windows"][key]["null_reasons"].values():
            if value is not None:
                used.add(value)
    reason_table = sorted(used)
    reason_ids = {reason: index for index, reason in enumerate(reason_table)}

    packet = {
        "schema": _PSL_WINDOW_PACKET_SCHEMA, "source_schema": _PSL_WINDOW_NATIVE_SCHEMA,
        "source_artifact": _PSL_ARTIFACT, "context_only": True, "consumer_reason": None,
        "cohort_id": companion["cohort_id"], "population": companion["population"],
        "cohort_status": "native_contract_admitted", "selected_group_id": sector,
        "status": companion["status"], "reason": companion["reason"],
        "source_session": companion["source_session"], "end_session": companion["end_session"],
        "benchmark": companion["benchmark"], "price_basis": companion["price_basis"],
        "units": companion["units"], "windows_sessions": list(_PSL_WINDOW_SESSIONS),
        "endpoint_definition": companion["endpoint_definition"],
        "clocks": companion["clocks"], "limitations": companion["limitations"],
        "authority": {key: False for key in
                      ("may_rank", "may_gate", "may_size", "may_trade", "may_escalate")},
        "artifact_health": _psl_health(health),
        "metadata_projection": {"receipt": "not_projected", "source_roots": "not_projected"},
        "row_encoding": {"windows": "keys 5,20,63", "values": "windows_sessions order",
                         "reasons": "reason_table indexes"},
        "reason_table": reason_table,
        "groups": [{
            "group_id": row["group_id"],
            "scope": "selected" if row["group_id"] == sector else "status_only",
            "window_status": [row["windows"][key]["status"] for key in _PSL_WINDOW_KEYS],
        } for row in groups],
        "selected": {
            "group_id": selected["group_id"],
            "name_en": selected["name_en"], "name_zh": selected["name_zh"],
            "absolute_return_pct": [selected["windows"][key]["absolute_return_pct"]
                                    for key in _PSL_WINDOW_KEYS],
            "relative_wealth_pct": [selected["windows"][key]["relative_wealth_pct"]
                                    for key in _PSL_WINDOW_KEYS],
            "observed_n": [selected["windows"][key]["coverage"]["observed_n"]
                           for key in _PSL_WINDOW_KEYS],
            "coverage_ratio": [selected["windows"][key]["coverage"]["ratio"]
                               for key in _PSL_WINDOW_KEYS],
            "absolute_reason_refs": [
                reason_ids.get(selected["windows"][key]["null_reasons"]["absolute_return_pct"])
                for key in _PSL_WINDOW_KEYS],
            "relative_reason_refs": [
                reason_ids.get(selected["windows"][key]["null_reasons"]["relative_wealth_pct"])
                for key in _PSL_WINDOW_KEYS],
        },
        "windows": {key: {
            "window_sessions": companion["windows"][key]["window_sessions"],
            "expected_observations": companion["windows"][key]["benchmark_coverage"]["expected_n"],
            "start_session": companion["windows"][key]["start_session"],
            "end_session": companion["windows"][key]["end_session"],
            "status": companion["windows"][key]["status"],
            "benchmark_return_pct": companion["windows"][key]["benchmark_return_pct"],
            "benchmark_observed_n": companion["windows"][key]["benchmark_coverage"]["observed_n"],
            "benchmark_coverage_ratio": companion["windows"][key]["benchmark_coverage"]["ratio"],
            "benchmark_reason_ref": reason_ids.get(
                companion["windows"][key]["benchmark_null_reason"]),
            "window_reason_ref": reason_ids.get(companion["windows"][key]["null_reason"]),
        } for key in _PSL_WINDOW_KEYS},
        "diagnostics": {
            "measured_cells": companion["diagnostics"]["measured_cells"],
            "complete_cells": companion["diagnostics"]["complete_cells"],
            "total_cells": companion["diagnostics"]["total_cells"],
            "block_reason_ref": reason_ids.get(companion["reason"]),
            "qualification_reason_refs": [reason_ids[reason] for reason
                                          in companion["diagnostics"]["qualification_reasons"]],
        },
    }
    # Both the character budget and the byte budget are measured on the exact serializer text.
    # If the whole packet cannot fit, refuse it; never drop a member, window or reason.
    payload = json.dumps(packet, default=str, ensure_ascii=False)
    if len(payload) > _PSL_MAX_BYTES or len(payload.encode("utf-8")) > _PSL_MAX_BYTES:
        return _psl_window_unavailable("window_transport_budget_exceeded", health, sector)
    return packet


def sector_rotation(limit: int = 6, *, projection: str = "legacy",
                     sector: Any = _PSL_SECTOR_UNSET) -> dict:
    """Return legacy leaders, an all-eleven dossier, or one selected exact-session sector view."""
    if projection == "sector_windows":
        if sector is _PSL_SECTOR_UNSET:
            return _psl_window_unavailable("sector_selection_required")
        if not isinstance(sector, str) or sector not in _PSL_GROUP_IDS:
            return _psl_window_unavailable("invalid_sector_selection")
        data, health = _read_sector_central()
        return _sector_window_projection(data, health, sector)
    if sector is not _PSL_SECTOR_UNSET:
        return _psl_window_unavailable("incompatible_selector_combination")
    if projection not in ("legacy", "sector_dossiers"):
        return _psl_unavailable("unsupported_projection")
    if projection == "sector_dossiers":
        data, health = _read_sector_central()
        return _sector_dossier_projection(data, health)
    cap = min(_clamp_limit(limit, 6), 6)
    data, health = _read_sector_central()
    invalid_legacy_input = data is not None and not isinstance(data, dict)
    if not isinstance(data, dict):
        data = {}

    # Native admission qualifies preview core; these original legacy fields are
    # consumed separately. Validate every row before ranking or applying the cap.
    for collection in ("sectors", "baskets"):
        rows = data.get(collection)
        if rows is None:
            continue
        if not isinstance(rows, list) or any(
            not isinstance(row, dict)
            or any(row.get(field) is not None and not isinstance(row[field], dict)
                   for field in ("rotation", "conviction"))
            for row in rows
        ):
            invalid_legacy_input = True
            break
    if invalid_legacy_input:
        data = {}
        health = {**_psl_health(health), "available": False, "status": "malformed",
                  "source_reason": "invalid_legacy_rotation_input"}

    def ranked(rows: Any) -> list[dict]:
        usable = [row for row in (rows or []) if isinstance(row, dict)]
        usable.sort(key=lambda row: (
            (row.get("rotation") or {}).get("rank")
            if isinstance((row.get("rotation") or {}).get("rank"), (int, float)) else 10**6,
            -(_num((row.get("conviction") or {}).get("score")) or 0),
            str(row.get("ticker") or row.get("id") or ""),
        ))
        return [_rotation_row(row) for row in usable[:cap]]

    try:
        ranked_sectors = ranked(data.get("sectors"))
        ranked_baskets = ranked(data.get("baskets"))
    except OverflowError:
        # A JSON integer can exceed float conversion even in a well-shaped row.
        # Refuse the whole captured legacy view, including any already-ranked side.
        data = {}
        health = {**_psl_health(health), "available": False, "status": "malformed",
                  "source_reason": "invalid_legacy_rotation_input"}
        ranked_sectors, ranked_baskets = [], []

    market = data.get("market") if isinstance(data.get("market"), dict) else {}
    packet = {
        "schema": "mastermind.portfolio_intelligence.sector_rotation/v1",
        "as_of": data.get("as_of"),
        "context_only": True,
        "health": health,
        "market": {k: market.get(k) for k in (
            "risk_on", "state_en", "gate_state_en", "tactical_label", "risk_state_state",
            "headline_en", "quad", "quad_name", "liquidity", "growth_score", "inflation_score",
            "n_above_trend", "n_sectors",
        )},
        "sectors": ranked_sectors,
        "baskets": ranked_baskets,
    }
    if health.get("source_mode") == "selected_generation":
        # The new native receipt must fit with the original legacy fields. Never
        # let the generic serializer silently truncate this newly admitted path.
        payload = json.dumps(packet, default=str, ensure_ascii=False)
        if len(payload) > _PSL_MAX_BYTES or len(payload.encode("utf-8")) > _PSL_MAX_BYTES:
            packet.update(as_of=None, sectors=[], baskets=[],
                          market={key: None for key in packet["market"]},
                          health={**_psl_health(health), "available": False,
                                  "status": "unknown", "source_reason":
                                  "native_legacy_transport_budget_exceeded"})
    return packet


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
    catalog = _context_catalog_with_sector_health(sectors["health"])
    status_rows = [
        {"id": row["id"], "status": row["status"], "available": row["available"]}
        for row in catalog["surfaces"]
    ]
    status_counts = {
        key: sum(1 for row in status_rows if row["status"] == key)
        for key in ("fresh", "stale", "undated", "missing", "malformed", "unknown")
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
    packet = {
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
    if sectors["health"].get("source_mode") == "selected_generation":
        packet["packet_truncated"] = False
        if _packet_size(packet) > _PACKET_MAX_BYTES:
            return _native_packet_refusal(
                packet["schema"], sectors["health"], "native_market_transport_budget_exceeded")
    return packet


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
    native_sector = False
    for rel, max_age, cadence, authority in spec["artifacts"]:
        if requested == "sector_central":
            captured_sector = sector_rotation(limit=per_artifact_limit)
            health = captured_sector["health"]
            native_sector = health.get("source_mode") == "selected_generation"
            content = captured_sector if health.get("available") is True else None
            if native_sector and content is not None and _packet_size(content) > per_artifact_budget:
                health = _native_consumer_refusal(health, "native_surface_content_budget_exceeded")
                content = None
        else:
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
            "content": content if native_sector else (
                _fit_content(content, budget=per_artifact_budget) if content is not None else None),
        })
    packet = {
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
    }
    if native_sector:
        packet["packet_truncated"] = False
        if _packet_size(packet) > _PACKET_MAX_BYTES:
            health = _native_consumer_refusal(health, "native_surface_transport_budget_exceeded")
            packet.update(status="unavailable", artifacts=[{
                "source": _source_ref(health), "content": None,
            }])
        return packet
    return _fit_packet(packet)
