"""In-process MCP server — the bot's data + action surface for Claude.

This is how the web app ARMS Claude and lets Claude COMMUNICATE BACK. The tools run
in THIS Python process (via the Agent SDK's in-process MCP), so Claude never touches
the filesystem directly — it calls typed tools we control.

READ tools  → give Claude the live dashboard + bot state to reason over.
ACTION tools → let Claude write conclusions back to the app's RESEARCH/PROPOSAL surface
               (research notes, proposed theses, emerging-theme flags, recommendations).

Accountability spine: action tools write to a REVIEW QUEUE (jsonl/markdown the web app
renders), never to the execution path. The engine still derives sizing + the falsifier;
nothing here auto-executes a trade. Paper-only.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

import bot  # noqa: F401
from claude_agent_sdk import tool, create_sdk_mcp_server

_ROOT = Path(__file__).resolve().parent.parent
_V = _ROOT / "vendor" / "macro"
_RESEARCH = _ROOT / "data" / "research"
_PROPOSALS = _ROOT / "data" / "brain" / "proposals.jsonl"
_READ_ROOTS = [_V / "site", _V / "data", _ROOT / "data"]
# Portfolio BOOK state is not "published signal" data — block cross-book reads through this
# generic path reader. A Brain reads its OWN book via a dedicated tool (get_portfolio / the
# desk's get_my_book); reading ANOTHER book's positions / ledger / research via read_signal was
# the latent autonomous→flagship peek path (data/portfolio/* lives under the _ROOT/data root).
_DENY_ROOTS = [(_ROOT / "data" / "portfolio").resolve(), (_ROOT / "data" / "portfolios").resolve()]
_LEAK_AUDIT = _ROOT / "data" / "brain" / "read_signal_denied.jsonl"


def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _compact_json_value(
    value,
    *,
    list_limit: int,
    str_limit: int,
    depth: int = 0,
):
    """Recursively bound a tool payload while preserving valid JSON and top-level shape."""
    if depth >= 7:
        return "<nested context omitted>"
    if isinstance(value, dict):
        return {
            str(k): _compact_json_value(
                v,
                list_limit=list_limit,
                str_limit=str_limit,
                depth=depth + 1,
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [
            _compact_json_value(
                v,
                list_limit=list_limit,
                str_limit=str_limit,
                depth=depth + 1,
            )
            for v in value[:list_limit]
        ]
    if isinstance(value, tuple):
        return _compact_json_value(
            list(value),
            list_limit=list_limit,
            str_limit=str_limit,
            depth=depth,
        )
    if isinstance(value, str) and len(value) > str_limit:
        return value[: max(0, str_limit - 1)] + "…"
    return value


def _json(obj) -> dict:
    """Return a valid JSON tool result under the 8k transport budget.

    The old implementation sliced serialized bytes, which emitted malformed JSON.  Progressive
    structural compaction keeps top-level keys and the highest-ranked list rows instead.
    """
    payload = json.dumps(obj, default=str, ensure_ascii=False)
    if len(payload) <= 8000:
        return _ok(payload)
    for list_limit, str_limit in ((20, 400), (10, 240), (5, 160), (3, 100), (1, 72)):
        compact = _compact_json_value(
            obj,
            list_limit=list_limit,
            str_limit=str_limit,
        )
        if isinstance(compact, dict):
            compact["_transport_truncated"] = True
        payload = json.dumps(compact, default=str, ensure_ascii=False)
        if len(payload) <= 8000:
            return _ok(payload)
    # Extremely wide objects still return valid JSON with their top-level scalar contract.
    fallback = {
        str(k): v
        for k, v in (obj.items() if isinstance(obj, dict) else [])
        if v is None or isinstance(v, (bool, int, float, str))
    }
    fallback["_transport_truncated"] = True
    fallback["_note"] = "Nested payload exceeded the MCP transport budget."
    return _ok(json.dumps(fallback, default=str, ensure_ascii=False))


def _read_json(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def _read_first_mapping_checked(paths):
    """Read the first available JSON source while preserving unreadable-source truth.

    Returns ``(mapping, had_failure)``. Missing paths are legitimate absence; malformed,
    unreadable, or wrong-shaped paths set ``had_failure`` but do not prevent a lower-priority
    mirror from being consumed. This is intentionally narrow and used only by the ticker deep-dive.
    """
    had_failure = False
    for path in paths:
        try:
            value = _read_json(path)
        except Exception:  # noqa: BLE001 - caller projects a closed source status
            had_failure = True
            continue
        if value is None:
            continue
        if not isinstance(value, dict):
            had_failure = True
            continue
        return value, had_failure
    return None, had_failure


def _ticker_record_checked(mapping, ticker):
    """Return one ticker record plus whether the mapping shape was invalid."""
    if mapping is None:
        return None, False
    tickers = mapping.get("tickers")
    if tickers is None:
        return None, False
    if not isinstance(tickers, dict):
        return None, True
    record = tickers.get(ticker)
    if record is not None and not isinstance(record, dict):
        return None, True
    return record, False


def _list_field_checked(mapping, key):
    """Return one optional list field plus whether its persisted shape was invalid."""
    if mapping is None:
        return [], False
    value = mapping.get(key)
    if value is None:
        return [], False
    if not isinstance(value, list):
        return [], True
    return value, False


def _pick(d, keys):
    """Shallow projection — {k: d[k]} for the keys present (drops noise/bulk)."""
    d = d or {}
    return {k: d.get(k) for k in keys if k in d}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append(p: Path, row: dict):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps({**row, "logged_at": _now()}, default=str) + "\n")


# Marker the streaming layer scans tool results for, to surface a research paper as a
# clickable button in the chat (followed by a JSON blob with the paper meta).
PAPER_MARKER = "__PAPER__"


def _today() -> str:
    d = _read_json(_V / "data" / "regime" / "latest.json") or {}
    return d.get("date") or datetime.now(timezone.utc).date().isoformat()


def _stock_price(t: str):
    d = _read_json(_V / "site" / "stockdata" / f"{t.upper()}.json") or {}
    return (d.get("tech") or {}).get("price")


# ---------------- READ tools ----------------
@tool("get_regime", "Current US macro regime read (quad, growth/inflation scores, liquidity).", {})
async def get_regime(args):
    keys = ["date", "quad", "quad_name", "growth_score", "inflation_score", "liquidity_overlay", "cycle_tag"]
    d, core_failed = _read_first_mapping_checked((
        _V / "data" / "regime" / "latest.json",
    ))
    if d is None:
        out = {k: None for k in keys} | {
            "sector_rs_top": None,
            "read_status": "unavailable",
            "regime_status": "unavailable" if core_failed else "absent",
            "error": "regime_core_unavailable" if core_failed else "regime_core_absent",
        }
        if core_failed:
            out["failed_sources"] = ["regime"]
        return _json(out)

    sector_rs = d.get("sector_rs")
    if sector_rs is not None and not isinstance(sector_rs, list):
        return _json({
            **{k: None for k in keys},
            "sector_rs_top": None,
            "read_status": "unavailable",
            "regime_status": "unavailable",
            "error": "regime_core_unavailable",
            "failed_sources": ["regime"],
        })

    out = {k: d.get(k) for k in keys} | {"sector_rs_top": (sector_rs or [])[:6]}
    failed_sources = []
    # E1.1 — append the market_view brief + label_vs_planes line (ADDITIVE; absent view → keys absent).
    # This replaces the ad-hoc 7-key slice so the autonomous Brain reads the same perception layer as
    # the judgment seats — the incident's root cause was the Brain seeing ONLY the label.
    try:
        from brain.pm_conviction import _read_market_view, _market_view_enrichment
        mv = _read_market_view()
        enrichment = _market_view_enrichment(mv)
        if enrichment:
            compact_mv = dict(enrichment)
            compact_mv["plane_summaries"] = [
                {
                    "name": row.get("name"),
                    "direction": row.get("direction"),
                    "status": row.get("status"),
                    "stale": (row.get("freshness") or {}).get("stale"),
                    "age_sessions": (row.get("freshness") or {}).get("age_sessions"),
                }
                for row in (enrichment.get("plane_summaries") or [])
            ]
            out["market_view"] = compact_mv
    except Exception:  # noqa: BLE001 — preserve the healthy regime core
        failed_sources.append("market_view")
    try:
        from brain import decision_context as _dc

        dc = _dc.prompt_summary()
        if dc:
            liquidity = dc.get("liquidity") or {}
            quality = liquidity.get("quality") or {}
            driver = dc.get("market_driver") or {}
            # Keep this tool's JSON safely below its transport cap. Rich fresh-lobe context remains
            # available to the strategist/PM; get_regime carries the precise regime core.
            out["decision_context"] = {
                "schema_version": dc.get("schema_version"),
                "market_asof": dc.get("market_asof"),
                "hard_label": dc.get("hard_label"),
                "probabilistic_state": dc.get("probabilistic_state"),
                "trajectory": dc.get("trajectory"),
                "axes": dc.get("axes"),
                "liquidity": {
                    "quantity_overlay": liquidity.get("quantity_overlay"),
                    "quality_label": quality.get("label"),
                    "quality_asof": quality.get("asof"),
                },
                "risk": dc.get("risk"),
                "market_driver": {
                    "label": driver.get("label"),
                    "direction": driver.get("direction"),
                    "confidence": driver.get("confidence"),
                    "strength": driver.get("strength"),
                    "evidence": driver.get("evidence"),
                    "invalidation": driver.get("invalidation"),
                },
                "governor": dc.get("governor"),
                "data_quality": dc.get("data_quality"),
                "neural_web_health": dc.get("neural_web_health"),
            }
    except Exception:  # noqa: BLE001 — preserve the healthy regime core
        failed_sources.append("decision_context")

    if failed_sources:
        out["read_status"] = "partial"
        out["failed_sources"] = failed_sources
        out["note"] = "Regime core is available; named context sources did not complete."
    return _json(out)


@tool("get_overnight_tape",
      "The LIVE overnight cross-asset tape — what's moving RIGHT NOW while the US cash market is shut, "
      "which the EOD macro dashboard CANNOT see. US index futures (ES/NQ/YM/RTY), international indices "
      "(Nikkei, Hang Seng, Shanghai, KOSPI, Euro Stoxx, DAX, FTSE), USD/JPY/DXY, the 10Y yield, VIX, oil, "
      "gold and BTC — each with its overnight % change — plus a distilled risk read (calm / elevated / "
      "stressed). Use this to position for the open the way a human trader watches the overnight tape; do "
      "NOT rely on the stale dashboard for the current risk.", {})
async def get_overnight_tape(args):
    try:
        from data_layer import overnight
        return _json(overnight.tape())
    except Exception:  # noqa: BLE001
        return _json({
            "overnight_status": "unavailable",
            "risk": None,
            "groups": None,
            "live": False,
            "error": "overnight_tape_unavailable",
            "note": "overnight tape unavailable",
        })


@tool("get_themes", "Narrative baskets with recent relative performance (the theme universe).",
      {"type": "object", "properties": {"region": {"type": "string"}}})
async def get_themes(args):
    d = _read_json(_V / "site" / "basketdata" / "baskets.json") or {}
    out = [{"id": b["id"], "name": b.get("name"), "category": b.get("category"),
            "perf_20d_rel": ((b.get("perf") or {}).get("20d") or {}).get("rel"),
            "n_members": b.get("n_members")} for b in (d.get("baskets") or [])]
    return _json({"as_of": d.get("as_of"), "themes": out})


@tool("get_standouts", "The ranked single-name buy board (top picks with suggested size).", {})
async def get_standouts(args):
    d = _read_json(_V / "site" / "factordata" / "us_standouts.json")
    if not d:
        return _ok("us_standouts.json not built locally (ships in the Pages artifact).")
    buys = (d.get("buy") or d.get("standouts") or [])[:20]
    return _json({"gate_go": d.get("gate_go"), "rank_by": d.get("rank_by"), "buy": buys})


@tool("get_portfolio", "The bot's current paper book + track record.", {})
async def get_portfolio(args):
    # This is the private Portfolio Advisor's own-book reader. ``flagship`` remains the
    # storage compatibility default, but it is archived and must never silently supply the
    # active US advisor context.
    from portfolio import registry

    portfolio_id = registry.DASHBOARD_DEFAULT_ID
    try:
        book_dir = registry.data_dir(portfolio_id)
    except Exception:  # noqa: BLE001
        return _json({
            "portfolio_id": portfolio_id,
            "read_status": "unavailable",
            "error": "portfolio_registry_unavailable",
            "failed_sources": ["portfolio_registry"],
        })

    latest, book_failed = _read_first_mapping_checked((book_dir / "latest.json",))
    if latest is None:
        if book_failed:
            return _json({
                "portfolio_id": portfolio_id,
                "read_status": "unavailable",
                "error": "portfolio_book_unavailable",
                "failed_sources": ["portfolio_book"],
            })
        return _json({"status": "no book yet", "portfolio_id": portfolio_id})
    if not latest:
        return _json({"status": "no book yet", "portfolio_id": portfolio_id})

    try:
        meta = registry.get(portfolio_id)
        if not isinstance(meta, dict):
            raise TypeError("portfolio registry metadata is not a mapping")
    except Exception:  # noqa: BLE001
        return _json({
            **latest,
            "portfolio_id": portfolio_id,
            "active": None,
            "lifecycle": None,
            "read_status": "partial",
            "failed_sources": ["portfolio_registry"],
            "note": "Book state is available; portfolio registry metadata did not complete.",
        })

    try:
        active = registry.is_active(portfolio_id)
    except Exception:  # noqa: BLE001
        return _json({
            **latest,
            "portfolio_id": portfolio_id,
            "active": None,
            "lifecycle": meta.get("status", "active"),
            "read_status": "partial",
            "failed_sources": ["portfolio_registry"],
            "note": "Book state is available; portfolio active-status read did not complete.",
        })

    return _json({
        **latest,
        "portfolio_id": portfolio_id,
        "active": active,
        "lifecycle": meta.get("status", "active"),
    })


@tool("get_decision_matrix", "The MULTI-SIDED decision matrix for a name or theme — every lens (valuation, quality, growth, narrative, leadership, asymmetry, risk, policy/admin tilt, Fed, institutional flows, options, rate sensitivity, cross-asset, conviction) with its read + honest status, plus the confluence/divergence synthesis. ALWAYS call this before any verdict.",
      {"type": "object", "properties": {"subject": {"type": "string"}, "kind": {"type": "string", "enum": ["name", "theme"]}}, "required": ["subject"]})
async def get_decision_matrix(args):
    from portfolio import lenses
    return _json(lenses.full(args["subject"], args.get("kind", "name")))


@tool("get_divergences", "Just the divergence patterns for a subject — where the lenses DISAGREE (the edge or the trap): distribution, early_edge, high_confluence_buy, crowded_top, policy_early.",
      {"type": "object", "properties": {"subject": {"type": "string"}, "kind": {"type": "string", "enum": ["name", "theme"]}}, "required": ["subject"]})
async def get_divergences(args):
    from portfolio import lenses
    s = lenses.synthesize(lenses.decision_matrix(args["subject"], args.get("kind", "name")))
    return _json({"divergences": s["divergences"], "confluence": s["confluence"], "vetoes": s["vetoes"]})


@tool("get_altdata", "Alternative-data flow + Trump-family/administration linkage for a NAME — cross-signal convergence across congress/insider/government-contract/lobbying/Trump-trade channels, plus whether the name sits in the latent-stake entity graph (e.g. American Bitcoin -> Hut 8, branded crypto but the value accrues to an AI-power-infra parent). A QUALITATIVE research signal: politically-linked smart-money flow. Public-record + CONTEXT-ONLY (never a scored axis) — informs narrative/conviction, never sizes alone.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_altdata(args):
    t = (args.get("ticker") or "").upper()
    flow_store, flow_read_failed = _read_first_mapping_checked((
        _V / "site" / "altdata" / "by_ticker.json",
        _V / "data" / "altdata" / "by_ticker.json",
    ))
    rec, flow_shape_failed = _ticker_record_checked(flow_store, t)
    flow_failed = flow_read_failed or flow_shape_failed
    flow_available = flow_store is not None and not flow_shape_failed

    latent, graph_read_failed = _read_first_mapping_checked((
        _V / "site" / "altdata" / "latent.json",
    ))
    watch, watch_shape_failed = _list_field_checked(latent, "watch")
    mismatches, mismatch_shape_failed = _list_field_checked(latent, "mismatches")
    graph_failed = graph_read_failed or watch_shape_failed or mismatch_shape_failed
    graph_available = latent is not None and not (watch_shape_failed or mismatch_shape_failed)

    graph = None
    for row in watch:
        if not isinstance(row, dict):
            graph_failed = True
            continue
        if (row.get("ticker") or "").upper() != t:
            continue
        themes = row.get("themes") or []
        if not isinstance(themes, list) or any(not isinstance(theme, dict) for theme in themes):
            graph_failed = True
            themes = []
        top_holder = row.get("top_holder") or {}
        if not isinstance(top_holder, dict):
            graph_failed = True
            top_holder = {}
        graph = {
            "in_graph": True,
            "themes": [theme.get("en") for theme in themes],
            "trump_people": row.get("trump_people"),
            "top_holder": top_holder.get("owner"),
            "alt_corroborated": row.get("alt_corroborated"),
            "note": row.get("note"),
        }
        break

    mismatch = None
    for row in mismatches:
        if not isinstance(row, dict):
            graph_failed = True
            continue
        tickers = {(row.get("repointed_ticker") or "").upper(), (row.get("entity_ticker") or "").upper()}
        if t in tickers:
            mismatch = row
            break

    failed_sources = []
    if flow_failed:
        failed_sources.append("altdata_flow")
    if graph_failed:
        failed_sources.append("altdata_graph")
    payload = {
        "ticker": t,
        "flow": rec,
        "latent_graph": graph,
        "label_mismatch": mismatch,
        "note": "Public-record alt-data (congress/insider/govt-contract/SEC EDGAR — macro engine Signal Intelligence Desk). Context-only — informs narrative, never sizes alone.",
    }
    if failed_sources:
        payload["read_status"] = (
            "unavailable"
            if flow_failed and graph_failed and not flow_available and not graph_available
            else "partial"
        )
        payload["failed_sources"] = failed_sources
        if payload["read_status"] == "unavailable":
            payload["error"] = "ticker_altdata_unavailable"
        return _json(payload)
    if rec is None and graph is None and mismatch is None:
        return _ok(f"no alt-data signal for {t} — not flagged by any political/insider/contract channel.")
    return _json(payload)


@tool("get_news",
      "Recent financial-news flow for a NAME — count of recent reputable headlines, a context-only "
      "sentiment lean aggregated from per-article tags, the baskets/sectors it touches, and the top "
      "headlines (title/source/url/summary). A QUALITATIVE research signal: what the tape is SAYING "
      "about this name. CONTEXT-ONLY (never a scored axis) — informs narrative/conviction, never sizes alone.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_news(args):
    t = (args.get("ticker") or "").upper()
    store, read_failed = _read_first_mapping_checked((
        _V / "site" / "news" / "by_ticker.json",
        _V / "data" / "news" / "by_ticker.json",
    ))
    rec, shape_failed = _ticker_record_checked(store, t)
    failed = read_failed or shape_failed
    healthy_store = store is not None and not shape_failed
    if failed:
        payload = {
            "ticker": t,
            "news": rec,
            "read_status": "partial" if healthy_store else "unavailable",
            "failed_sources": ["news"],
            "note": "News evidence did not fully load; missing fields are unknown, not negative evidence.",
        }
        if payload["read_status"] == "unavailable":
            payload["error"] = "ticker_news_unavailable"
        return _json(payload)
    if rec is None:
        return _ok(f"no news-flow signal for {t} — not covered by the macro news surface.")
    return _json({"ticker": t, "news": rec,
                  "note": "Public-record financial news flow. Context-only — informs narrative, never sizes alone."})


@tool("get_intelligence",
      "The UNIFIED News & Intelligence read for a NAME — both sides of the tape in ONE call: "
      "(1) news_flow (demand-side: what the market is SAYING — recent headline count, sentiment lean, "
      "top headlines) and (2) the alt-data signal (supply-side: what political/insider/contract/"
      "affiliation money is DOING — signal_score 0-100, action, conviction, channels, affiliations). "
      "Shown SIDE BY SIDE, never blended — the divergence between them is the edge (early = flow into a "
      "QUIET tape; crowded/late = flow into a LOUD tape). CONTEXT-ONLY — informs conviction, never sizes alone.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_intelligence(args):
    t = (args.get("ticker") or "").upper()
    unified_store, unified_read_failed = _read_first_mapping_checked((
        _V / "site" / "intelligence" / "by_ticker.json",
        _V / "data" / "intelligence" / "by_ticker.json",
    ))
    rec, unified_shape_failed = _ticker_record_checked(unified_store, t)
    unified_failed = unified_read_failed or unified_shape_failed
    unified_available = unified_store is not None and not unified_shape_failed

    if rec is not None:
        payload = {"ticker": t, **rec,
                   "note": "News flow (what the tape says) + alt-data signal (what smart money does), side by side. Context-only — the divergence between them is the read; never sizes alone."}
        if unified_failed:
            payload["read_status"] = "partial"
            payload["failed_sources"] = ["unified_intelligence"]
        return _json(payload)

    news_store, news_read_failed = _read_first_mapping_checked((
        _V / "site" / "news" / "by_ticker.json",
        _V / "data" / "news" / "by_ticker.json",
    ))
    news, news_shape_failed = _ticker_record_checked(news_store, t)
    news_failed = news_read_failed or news_shape_failed
    news_available = news_store is not None and not news_shape_failed

    alt_store, alt_read_failed = _read_first_mapping_checked((
        _V / "site" / "altdata" / "mastermind.json",
    ))
    signals, signals_shape_failed = _list_field_checked(alt_store, "signals")
    alt_failed = alt_read_failed or signals_shape_failed
    alt_available = alt_store is not None and not signals_shape_failed
    alt = None
    for row in signals:
        if not isinstance(row, dict):
            alt_failed = True
            continue
        if (row.get("ticker") or "").upper() == t:
            alt = row
            break

    failed_sources = []
    if unified_failed:
        failed_sources.append("unified_intelligence")
    if news_failed:
        failed_sources.append("news")
    if alt_failed:
        failed_sources.append("altdata")

    composed = {"ticker": t, "news": news, "alt": alt, "has_news": bool(news), "has_alt": bool(alt)}
    if failed_sources:
        payload = {
            **composed,
            "read_status": (
                "unavailable"
                if unified_failed and news_failed and alt_failed
                and not unified_available and not news_available and not alt_available
                else "partial"
            ),
            "failed_sources": failed_sources,
            "note": "Intelligence evidence did not fully load; missing fields are unknown, not negative evidence.",
        }
        if payload["read_status"] == "unavailable":
            payload["error"] = "ticker_intelligence_unavailable"
        return _json(payload)

    if news is None and alt is None:
        return _ok(f"no news or alt-data intelligence for {t}.")
    return _json({
        **composed,
        "note": "News flow (what the tape says) + alt-data signal (what smart money does), side by side. Context-only — the divergence between them is the read; never sizes alone.",
    })


@tool("get_quote",
      "Live (15-min delayed) market price(s) via Polygon for one or more tickers — the Brain's "
      "real-time price read: mark held positions, sanity-check an entry level, or confirm a move "
      "is real before forming a thesis. Returns {TICKER: price}. Prices are delayed and for "
      "reference/marks only — never a trade trigger on their own.",
      {"type": "object", "properties": {"tickers": {"type": "array", "items": {"type": "string"}}},
       "required": ["tickers"]})
async def get_quote(args):
    from data_layer import polygon
    tks = [str(t) for t in (args.get("tickers") or []) if t]
    px = polygon.quotes(tks)
    if not any(v is not None for v in px.values()):
        return _ok("no live quotes available — Polygon layer offline or unkeyed (set POLYGON_API_KEY).")
    return _json({"quotes": px,
                  "note": "Live 15-min delayed prices (Polygon). For marks/entry checks — not a signal."})


@tool("get_daily_briefing",
      "START HERE each session. The dashboard's RANKED daily briefing for the brain — the triaged "
      "worklist so you don't scan every name cold. Returns: macro_context (regime/quad, cycle, "
      "liquidity, Fed stance, plain-English posture, next catalysts) to frame the day; priority_queue "
      "(top names by transmission priority = facet-agreement × signal-strength, each with the "
      "FACTS-derived situation, lean, evidence, source mix, and falsifier); and divergences (the subset "
      "where the tape and smart-money DISAGREE — spend your depth budget here). Context-only — a triage, "
      "never a position size.",
      {"type": "object", "properties": {"top": {"type": "integer"}}})
async def get_daily_briefing(args):
    top = int(args.get("top") or 20)
    b = (_read_json(_V / "site" / "intelligence" / "briefing.json")
         or _read_json(_V / "data" / "intelligence" / "briefing.json"))
    if b:
        return _json({"as_of": b.get("as_of"), "macro_context": b.get("macro_context"),
                      "n_actionable": b.get("n_actionable"), "n_divergences": b.get("n_divergences"),
                      "priority_queue": (b.get("priority_queue") or [])[:top],
                      "divergences": b.get("divergences"), "how_to_use": b.get("how_to_use")})
    # not published yet — compose a live briefing from the per-engine intake funnel
    from brain import intake
    q = intake.build(limit=top)
    return _json({"as_of": q.get("as_of"), "macro_context": q.get("macro_context"),
                  "priority_queue": q.get("candidates"),
                  "note": "Composed live from the dashboard signal engines (briefing.json not built yet)."})


@tool("get_intel_hub",
      "The INTELLIGENCE HUB central command — the dashboard's deepest read, fusing ALL FIVE desks "
      "(news flow · alt-data smart-money · divergence radar · factor buy-board · POLICY intent) into "
      "one reasoned dossier per name. Each carries a composite CONVICTION (0-100, rewards independent "
      "cross-desk agreement, docked by an unanswered falsifier), the 5-desk direction matrix, and the "
      "2nd/3rd-order FLAGS that name the setup: stealth_accumulation / early_edge (smart money before "
      "the crowd) / crowded_top (distribution risk) / confirmed_trend / fading / policy_aligned / "
      "policy_conflict / THEME_WIDE (the whole basket is moving — durable) / ISOLATED (name-specific). "
      "Pass a ticker for that name's full dossier; omit it for the ranked command + divergence alerts + "
      "sector heat. The richest single pull; context-only, never sizes.",
      {"type": "object", "properties": {"ticker": {"type": "string"}, "top": {"type": "integer"}}})
async def get_intel_hub(args):
    h = (_read_json(_V / "site" / "intel_hub" / "hub.json")
         or _read_json(_V / "data" / "intel_hub" / "hub.json"))
    if not h:
        return _ok("intel hub not built yet (site/intel_hub/hub.json absent — ships in the daily build).")
    t = (args.get("ticker") or "").upper()
    if t:
        d = next((x for x in (h.get("command") or []) if (x.get("ticker") or "").upper() == t), None)
        if not d:
            return _ok(f"{t} not in the intel-hub command (no cross-desk signal today).")
        return _json({"ticker": t, **d, "macro_context": h.get("macro_context"),
                      "note": "Full 5-desk dossier. The flags name the setup; track the falsifier."})
    top = int(args.get("top") or 15)

    def _slim(d):
        return {k: d.get(k) for k in ("ticker", "name", "composite_conviction", "lean", "n_confirm",
                "n_dissent", "flags", "read", "peers", "sectors", "falsifier") if k in d}
    return _json({"as_of": h.get("as_of"), "macro_context": h.get("macro_context"),
                  "desks": h.get("desks"), "counts": h.get("counts"),
                  "n_actionable": h.get("n_actionable"),
                  "command": [_slim(d) for d in (h.get("command") or [])[:top]],
                  "divergence_alerts": h.get("divergence_alerts"),
                  "sector_heat": (h.get("sector_heat") or [])[:8],
                  "how_to_use": h.get("how_to_use")})


@tool("get_intake_candidates",
      "The unified CANDIDATE QUEUE — every name the dashboard's signal engines flagged today, deduped "
      "and ranked with full PROVENANCE: for each ticker, which engines fired (briefing / divergence / "
      "buy-board / radar / alt-data / news-surge / open-thesis), why, the net lean, confidence, and "
      "falsifier. Corroboration across INDEPENDENT engines lifts a name. This is the intake funnel that "
      "replaces the old static shortlist — use it to choose what to research. Optional salience tiers "
      "split it into ACT (high-score, corroborated) / WATCH / DIVERGENT. Context-only — never sizes.",
      {"type": "object", "properties": {"limit": {"type": "integer"}, "tiers": {"type": "boolean"}}})
async def get_intake_candidates(args):
    from brain import intake
    limit = int(args.get("limit") or 30)
    out = intake.build(limit=limit)
    if args.get("tiers"):
        out["salience"] = intake.salience_tiers(limit)
    return _json(out)


@tool("get_ticker_package",
      "ONE-CALL DEEP DIVE for a name — bundles every per-ticker read so you don't chain five tools: the "
      "unified intelligence (news flow + alt-data signal + radar divergence + factor buy-board, side by "
      "side, with the brain summary), the decision-matrix divergences/confluence/vetoes (where the lenses "
      "agree or disagree), and the intake provenance (which engines flagged it). Call this once you've "
      "picked a name off the briefing/intake queue and want the full picture before a verdict. "
      "Context-only — informs conviction, never sizes alone.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_ticker_package(args):
    t = (args.get("ticker") or "").upper()
    uni, intelligence_failed = _read_first_mapping_checked((
        _V / "site" / "intelligence" / "by_ticker.json",
        _V / "data" / "intelligence" / "by_ticker.json",
    ))
    uni = uni or {}
    intel = (uni.get("tickers") or {}).get(t)
    pkg = {"ticker": t, "intelligence": intel}
    failed_sources = []
    if intelligence_failed:
        failed_sources.append("intelligence")
    try:
        from portfolio import lenses
        synthesis = lenses.synthesize(lenses.decision_matrix(t, "name"))
        pkg["lenses"] = {
            "divergences": synthesis.get("divergences"),
            "confluence": synthesis.get("confluence"),
            "vetoes": synthesis.get("vetoes"),
        }
    except Exception:  # noqa: BLE001
        failed_sources.append("lenses")
        pkg["lenses"] = {
            "read_status": "unavailable",
            "error": "ticker_package_lenses_unavailable",
        }
    try:
        from brain import intake
        prov = next((c for c in intake.queue(60) if c["ticker"] == t), None)
        pkg["intake"] = prov
    except Exception:  # noqa: BLE001
        failed_sources.append("intake")
        pkg["intake"] = None

    if failed_sources:
        pkg["failed_sources"] = failed_sources
        pkg["read_status"] = "unavailable" if len(failed_sources) == 3 else "partial"
        if pkg["read_status"] == "unavailable":
            pkg["error"] = "ticker_package_unavailable"
        pkg["note"] = (
            "Ticker-package evidence is incomplete; missing fields are unknown, not negative evidence."
        )
        return _json(pkg)

    if intel is None and pkg.get("intake") is None:
        return _ok(f"no per-ticker intelligence for {t} — not flagged by any dashboard engine.")
    pkg["note"] = ("Full per-name picture: intelligence facets + lens divergences + intake provenance. "
                   "The divergence between demand-tape and supply-smart-money is the read; never sizes alone.")
    return _json(pkg)


@tool("get_fundamentals",
      "Valuation + financials + earnings + accounting-quality + the engine's conviction read for a NAME "
      "(from the per-ticker stock file). Use this for a fundamental picture before an add/cut verdict — "
      "P/E + forward tier, margins/growth/ROE/accruals, next earnings + SUE, analyst rating/target, the "
      "Piotroski/accounting verdict, and the composite conviction score/band/size with its cautions.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_fundamentals(args):
    t = (args.get("ticker") or "").upper()
    d = _read_json(_V / "site" / "stockdata" / f"{t}.json")
    if not d:
        return _ok(f"no stock file for {t} (covered: S&P 1500 + crypto; ships in the Pages artifact).")
    return _json({
        "ticker": t, "name": d.get("name"), "sector": d.get("sector"), "asof": d.get("asof"),
        "valuation": _pick(d.get("valuation"), ["trailing_pe", "forward_pe", "forward_tier", "price_to_book",
                           "price_to_sales", "earnings_yield", "shareholder_yield", "value_z"]),
        "financials": _pick(d.get("financials"), ["gross_margin", "net_margin", "fcf_margin", "rev_growth",
                            "ni_growth", "roe", "roa", "debt_to_assets", "accruals"]),
        "earnings": _pick(d.get("earnings"), ["next_date", "eps_forecast", "sue_z", "summary"]),
        "analyst": _pick(d.get("analyst"), ["rating", "target", "forward_pe", "div_yield"]),
        "accounting_quality": _pick(d.get("accounting_quality"), ["verdict", "headline", "piotroski", "n_caution"]),
        "factors": _pick(d.get("factors"), ["composite", "fundamental_score"]),
        "tech": _pick(d.get("tech"), ["price", "pct_vs_50dma", "pct_vs_200dma", "rsi14", "off_52w_high_pct"]),
        "conviction": _pick(d.get("conviction"), ["score", "band", "verdict", "size", "risk",
                            "cycle_blocked", "cautions"]),
    })


@tool("get_options",
      "Dealer-positioning / options read for a liquid NAME (gamma exposure): the GEX regime (long/short) + "
      "gamma-flip level + distance, magnets, IV30, put/call OI, max pain, call/put walls, the expected daily/"
      "weekly move, and the volatility-hole state (compression -> where price can vacuum to). Use for entry "
      "timing + risk bands, not stock selection.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_options(args):
    t = (args.get("ticker") or "").upper()
    d = _read_json(_V / "site" / "gex" / f"{t}.json")
    if not d:
        return _ok(f"no options/GEX file for {t} (only the ~liquid options universe is covered).")
    return _json({
        "ticker": t, "asof": (d.get("meta") or {}).get("asof"),
        "summary": _pick(d.get("summary"), ["spot", "regime", "tier", "net_gex_bn", "gamma_flip",
                         "dist_to_flip_pct", "magnet_up", "magnet_down", "iv30", "put_call_oi_ratio",
                         "max_pain", "call_wall", "put_wall"]),
        "expected_move": _pick(d.get("expected_move"), ["daily_pct", "weekly_pct", "front"]),
        "vol_hole": _pick(d.get("vol_hole"), ["state", "bias", "upper", "lower", "to_upper_pct",
                          "to_lower_pct", "compression"]),
    })


@tool("get_anticipation",
      "The forward-looking anticipation index for a watchlist NAME — a directional conviction read with "
      "multi-leg confluence: the index (-1..+1) + band, how many drivers align, how much to TRUST the "
      "direction, the realized-vol cone, and per-horizon (short/medium/long) expected moves + the drivers/"
      "guards/caveats. Context for a timing lean; honest about trust.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_anticipation(args):
    t = (args.get("ticker") or "").upper()
    d = _read_json(_V / "site" / "anticipationdata" / f"{t}.json")
    if not d:
        return _ok(f"no anticipation file for {t} (only the curated forward-signal watchlist is covered).")
    return _json({
        "ticker": t, "name": d.get("name"), "group": d.get("group"), "as_of": d.get("as_of"),
        **_pick(d, ["anticipation_index", "index_band", "confluence_value", "n_go_legs",
                    "direction_trust", "trust", "vol_cone_ann", "horizons", "drivers", "guards", "caveats"]),
    })


@tool("read_signal", "Read a published signal/data JSON by path (allowlisted to the dashboard + bot data roots).",
      {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]})
async def read_signal(args):
    p = (Path(args["path"]) if Path(args["path"]).is_absolute() else _ROOT / args["path"]).resolve()
    roots = [r.resolve() for r in _READ_ROOTS]
    if not any(p == root or root in p.parents for root in roots):
        return _ok("DENIED: path outside the allowed data roots.")
    if any(p == r or r in p.parents for r in _DENY_ROOTS):
        _audit_denied_book_read(p)
        return _ok("DENIED: portfolio book state (positions/ledger/research) is not readable "
                   "via read_signal — read your OWN book through your desk tool.")
    d = _read_json(p)
    return _json(d) if d is not None else _ok(f"not found: {p}")


def _audit_denied_book_read(p: Path) -> None:
    """Best-effort: record any attempt to read a portfolio book through read_signal, so a
    cross-book peek attempt is visible after the fact even though it was blocked."""
    try:
        _LEAK_AUDIT.parent.mkdir(parents=True, exist_ok=True)
        with _LEAK_AUDIT.open("a") as fh:
            fh.write(json.dumps({"ts": _now(), "denied_path": str(p)}) + "\n")
    except Exception:
        pass


# ------------ proposal/write-back tools (never mutate a portfolio or paper account) ------------
@tool("save_research_note", "Persist a research note for the web app to render (Claude's conclusions/analysis).",
      {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"},
       "tickers": {"type": "array", "items": {"type": "string"}}}, "required": ["title", "body"]})
async def save_research_note(args):
    slug = re.sub(r"[^a-z0-9]+", "-", args["title"].lower())[:48].strip("-")
    p = _RESEARCH / "notes" / f"{int(time.time())}_{slug}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# {args['title']}\n\n*tickers: {', '.join(args.get('tickers') or [])} · {_now()}*\n\n{args['body']}\n")
    return _ok(f"saved research note → {p.relative_to(_ROOT)}")


@tool("propose_thesis", "Propose a FALSIFIABLE investment thesis to the review queue (engine derives the falsifier + size; never auto-executed).",
      {"type": "object", "properties": {
          "subject": {"type": "string"}, "lean": {"type": "string", "enum": ["add", "overweight", "avoid", "underweight", "watch"]},
          "conviction": {"type": "string", "enum": ["low", "medium", "high"]}, "horizon_d": {"type": "integer"},
          "thesis": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}},
          "prob_correct": {"type": "number"}},
       "required": ["subject", "lean", "thesis"]})
async def propose_thesis(args):
    _append(_PROPOSALS, {"source": "claude_cli", "status": "proposed", **args})
    return _ok(f"thesis proposed for {args['subject']} ({args['lean']}) → review queue. NOT executed.")


@tool("flag_emerging_theme", "Flag a newly-detected emerging narrative/theme for the web app.",
      {"type": "object", "properties": {"name": {"type": "string"}, "stage": {"type": "string"},
       "tickers": {"type": "array", "items": {"type": "string"}}, "rationale": {"type": "string"}},
       "required": ["name", "rationale"]})
async def flag_emerging_theme(args):
    _append(_RESEARCH / "emerging.jsonl", {"source": "claude_cli", **args})
    return _ok(f"flagged emerging theme '{args['name']}' → web app.")


# Legacy compatibility handler for non-Portfolio callers.  It is deliberately NOT registered in
# ``_ACTION`` below: the private Portfolio Advisor must use the validated proposal lifecycle, and
# legacy ``status=paper`` rows must not contaminate that homogeneous queue.
@tool("recommend_action", "LEGACY: log a paper recommendation outside the Portfolio Advisor queue.",
      {"type": "object", "properties": {"ticker": {"type": "string"},
       "action": {"type": "string", "enum": ["buy", "add", "trim", "exit", "watch"]},
       "rationale": {"type": "string"}}, "required": ["ticker", "action", "rationale"]})
async def recommend_action(args):
    _append(_RESEARCH / "legacy_recommendations.jsonl",
            {"source": "claude_cli", "status": "paper", **args})
    return _ok(f"legacy recommendation logged: {args['action']} {args['ticker']} "
               "(paper, outside the Portfolio Advisor queue).")


# -------- evaluate -> research paper -> non-executing proposal (user-pushed-name flow) --------
@tool("evaluate_gate",
      "PRELIMINARY GATE for a name the user wants you to consider adding. Runs the multi-sided "
      "decision matrix and returns whether it passes the engine's size gate (size_authority 'up' "
      "AND no hard veto), the confluence, the hard vetoes, and the bearish/bullish lenses. Call "
      "this FIRST when the user pushes a ticker: if it does NOT pass, explain why and stop; if it "
      "passes, tell the user it cleared preliminary inspection and that you're now writing the "
      "research paper before deciding.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def evaluate_gate(args):
    from portfolio import lenses
    t = (args.get("ticker") or "").upper()
    m = lenses.full(t, "name")
    syn = m.get("synthesis") or {}
    rows = m.get("rows") or []
    vetoes = syn.get("vetoes") or []
    conf = float(syn.get("confluence", 0.0) or 0.0)
    authority = syn.get("size_authority")
    passed = authority == "up" and not vetoes
    if vetoes:
        reason = "hard veto — " + ", ".join(vetoes)
    elif authority == "blocked":
        reason = "blocked (size_authority=blocked)"
    elif conf <= -0.3:
        reason = f"negative confluence ({conf:+.2f})"
    elif authority != "up":
        reason = f"insufficient confluence ({conf:+.2f}; need > 0.30 with leadership + trend confirmation)"
    else:
        reason = f"cleared — confluence {conf:+.2f}, no hard veto"
    bears = [(r.get("lens", "").replace("_", " ") + (f": {r['note']}" if r.get("note") else ""))
             for r in rows if r.get("direction") == "bear"][:5]
    bulls = [r.get("lens", "").replace("_", " ") for r in rows if r.get("direction") == "bull"][:6]
    return _json({"ticker": t, "passed": passed, "confluence": round(conf, 3),
                  "size_authority": authority, "vetoes": vetoes, "reason": reason,
                  "bear_lenses": bears, "bull_lenses": bulls,
                  "divergences": syn.get("divergences")})


@tool("file_research_paper",
      "File the holistic research paper YOU wrote for a name and get the combined Conviction-Index "
      "gate result. Call this AFTER evaluate_gate passes and you've done the deep research (tools + "
      "web) and written the full report in markdown. The tool combines the engine buy-score with "
      "your research score (combined = round(0.5*engine + 0.5*research); CONFIRMED if combined >= 60 "
      "and viability != avoid). It STORES the paper in the Research dashboard and returns paper_id + "
      "confirmed so the chat shows the user a button to open it. Use EXACTLY these report headings: "
      "## Thesis, ## Pros, ## Cons, ## Valuation, ## Fundamentals, ## Revenue streams, ## Competitive "
      "landscape & moat, ## Confirmed catalysts, ## Pending catalysts, ## Potential catalysts, "
      "## Forward earnings (recalculated), ## Bull / base / bear scenarios, ## Second- and third-order "
      "effects, ## Variant perception — what the market is missing, ## What to watch, ## Other factors.",
      {"type": "object", "properties": {
          "ticker": {"type": "string"},
          "report_md": {"type": "string"},
          "research_score": {"type": "integer"},
          "viability": {"type": "string", "enum": ["compelling", "fair", "rich", "avoid"]},
          "recommend": {"type": "boolean"},
          "summary": {"type": "string"},
          "key_risks": {"type": "array", "items": {"type": "string"}},
          "fair_value": {"type": "number"},
          "price_assessment": {"type": "string"},
          "confidence": {"type": "string", "enum": ["low", "medium", "high"]}},
       "required": ["ticker", "report_md", "research_score", "viability", "recommend", "summary"]})
async def file_research_paper(args):
    from portfolio import lenses
    from brain import research_paper as rp
    t = (args.get("ticker") or "").upper()
    syn = (lenses.full(t, "name") or {}).get("synthesis") or {}
    confluence = float(syn.get("confluence", 0.0) or 0.0)
    asof = _today()
    price = None
    try:
        from data_layer import polygon
        price = (polygon.quotes([t]) or {}).get(t)
    except Exception:
        price = None
    price = price if price else _stock_price(t)

    report_md = rp._strip_leading_narration(args["report_md"])
    paper = {
        "schema": rp.SCHEMA, "id": f"{asof}-{t}", "ticker": t, "asof": asof,
        "generated_at": rp._now(), "mode": "portfolio_research_advisor",
        "model": "portfolio-research-advisor",
        "price_at_review": price, "research_score": int(args["research_score"]),
        "viability": args["viability"], "recommend": bool(args["recommend"]),
        "confidence": args.get("confidence") or "medium", "fair_value": args.get("fair_value"),
        "price_assessment": args.get("price_assessment") or "", "summary": args["summary"],
        "sections": rp._split_sections(report_md), "key_risks": args.get("key_risks") or [],
        "report_md": report_md,
    }
    rp._attach_gate(paper, confluence)          # -> engine_score, combined, confirmed, gate_reason
    rp.save_paper(paper)
    try:
        rp.write_feed_note(paper)
    except Exception:
        pass
    meta = {"paper_id": paper["id"], "ticker": t, "title": f"{t} — Research Report",
            "combined": paper["combined"], "confirmed": paper["confirmed"],
            "research_score": paper["research_score"], "engine_score": paper["engine_score"],
            "viability": paper["viability"]}
    verdict = ("CONFIRMED (combined >= 60) — eligible for a non-executing ADD proposal."
               if paper["confirmed"] else f"NOT confirmed ({paper['gate_reason']}) — do not add it.")
    return _ok(f"{PAPER_MARKER} {json.dumps(meta)}\n"
               f"Filed research paper {paper['id']} → Research dashboard. Conviction Index "
               f"{paper['combined']}/100 (engine {paper['engine_score']} + research "
               f"{paper['research_score']}). {verdict}")


@tool("propose_portfolio_action",
      "Queue a NON-EXECUTING ADD / TRIM / EXIT proposal from the private Mastermind Portfolio "
      "Research Advisor. This tool accepts no size, shares, notional, price, or fill instruction; "
      "scheduled deterministic portfolio engines remain the sole sizing and paper-execution "
      "authority. An ADD proposal requires a CONFIRMED research paper. Urgency describes review "
      "priority only and never authorizes execution.",
      {"type": "object", "properties": {
          "ticker": {"type": "string"},
          "action": {"type": "string", "enum": ["add", "trim", "exit"]},
          "thesis": {"type": "string"},
          "evidence": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                       "maxItems": 12},
          "urgency": {"type": "string",
                      "enum": ["routine", "next_cycle", "urgent_review"]}},
       "required": ["ticker", "action", "thesis", "evidence", "urgency"]})
async def propose_portfolio_action(args):
    from brain import research_paper as rp
    from portfolio import advisor_trade

    # Defense in depth for direct handler callers that bypass JSON-schema validation. A
    # proposal carrying an order unit must be refused, not silently stripped and queued.
    forbidden = sorted({"weight", "size", "shares", "notional", "price", "fill"} & set(args or {}))
    if forbidden:
        return _ok(
            "REFUSED: Portfolio Advisor proposals cannot carry sizing or fill fields "
            f"({', '.join(forbidden)}). No proposal queued and no paper account changed."
        )

    t = (args.get("ticker") or "").upper()
    action = (args.get("action") or "").lower()
    if action == "add":
        paper = rp.latest_for(t)
        if not paper or not paper.get("confirmed"):
            return _ok(
                f"REFUSED: no CONFIRMED research paper on file for {t}. Run the flow first — "
                "evaluate_gate -> write + file_research_paper -> if confirmed, propose ADD. "
                "No proposal queued and no paper account changed."
            )
    res = advisor_trade.propose_action(
        t,
        action,
        thesis=args.get("thesis") or "",
        evidence=args.get("evidence") or [],
        urgency=args.get("urgency") or "",
        source="advisor_chat",
    )
    if not res.get("ok"):
        return _ok(
            f"proposal NOT queued for {t}: {res.get('error', 'unknown')}. "
            "No paper account changed."
        )
    proposal = res["proposal"]
    return _ok(
        f"PROPOSAL_QUEUED {json.dumps(proposal, ensure_ascii=False)}\n{res['note']}"
    )


_READ = [get_regime, get_overnight_tape, get_themes, get_standouts, get_portfolio, get_decision_matrix, get_divergences,
         get_altdata, get_news, get_intelligence, get_intel_hub, get_daily_briefing, get_intake_candidates,
         get_ticker_package, get_fundamentals, get_options, get_anticipation, get_quote,
         evaluate_gate, read_signal]
_ACTION = [save_research_note, propose_thesis, flag_emerging_theme,
           file_research_paper, propose_portfolio_action]
_ALL = _READ + _ACTION
SERVER_NAME = "bot"

# tool names as Claude sees them: mcp__<server>__<tool>
TOOL_NAMES = [f"mcp__{SERVER_NAME}__{t.name}" for t in _ALL]
WEB_TOOLS = ["WebSearch", "WebFetch"]


def build_server():
    """Return the in-process MCP server config to hand the SDK via mcp_servers={SERVER_NAME: cfg}."""
    return create_sdk_mcp_server(name=SERVER_NAME, version="0.1.0", tools=_ALL)


def armed_allowed_tools() -> list[str]:
    """The tool allow-list for an armed research session: bot tools + web + read-only files."""
    return TOOL_NAMES + WEB_TOOLS + ["Read", "Grep", "Glob"]
