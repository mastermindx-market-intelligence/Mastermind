"""The HK desk's MCP surface — the FREE-FORM all-China book the Opus Brain manages itself.

Sibling of ``brain/autonomous_mcp.py`` but pointed at the macro China desks and the multi-venue
(A-share / HK / ADR) universe. The Brain researches via the China read tools below + the web,
then calls ONE tool — ``submit_book`` — with its complete target portfolio for the day, each
holding carrying a one-paragraph rationale. No gate, no research paper, no sleeves.

The tool RECORDS the decided book to the china portfolio's ``_pending_decision.json``; the
deterministic builder (``bot/china.py``) reads it after the session and rebalances the paper
account (USD-marked) to those targets. All trading logic stays in the trusted Python layer,
bound to the china book only.

Safety (mirrors the autonomous desk): only typed ``mcp__china__*`` read tools + web — NO raw
Read/Grep/Glob, NO flagship get_portfolio, NO gated execute_trade. The Brain reads its OWN book
via get_my_book and cannot reach another book's state.
"""
from __future__ import annotations

import json

import bot  # noqa: F401  -> vendor/macro onto sys.path
from claude_agent_sdk import tool, create_sdk_mcp_server

from brain import autonomous_mcp, bot_mcp, china_intake, decision_submission

SERVER_NAME = "hk"
PORTFOLIO_ID = "hk"

# Registry-driven so the HK desk (brain/hk_mcp.py) reuses this contract: the China book is HKD /
# A-shares-only; the HK book is HKD / HK-only. ALLOWED_VENUES empty = unrestricted.
from portfolio import registry as _registry
BENCHMARK = _registry.benchmark(PORTFOLIO_ID)
CURRENCY = _registry.currency(PORTFOLIO_ID)            # "HKD"
ALLOWED_VENUES = set(_registry.venues(PORTFOLIO_ID))   # {"HK"}

# Marker the builder / streaming layer can scan a tool result for (shared with the autonomous desk).
BOOK_MARKER = autonomous_mcp.BOOK_MARKER

# bot_mcp._json hard-SLICES the serialized payload at 8000 chars, which can cut mid-record and
# yield INVALID JSON. For the list-bearing China tools we instead drop trailing rows until the
# whole payload fits, so the tool ALWAYS returns parseable JSON (no mid-string truncation).
_JSON_CAP = 7600


def _capped_json(payload: dict, shrink_keys: list[str], cap: int = _JSON_CAP):
    while True:
        s = json.dumps(payload, default=str, ensure_ascii=False)
        if len(s) <= cap:
            return bot_mcp._ok(s)
        longest = max((k for k in shrink_keys if isinstance(payload.get(k), list) and payload[k]),
                      key=lambda k: len(payload[k]), default=None)
        if longest is None:
            return bot_mcp._ok(s[:cap])     # nothing left to shrink (defensive; unreachable in practice)
        payload[longest] = payload[longest][:-1]
        payload["truncated"] = True


# ---------------------------------------------------------------------------
# submission helpers — reuse the autonomous desk's per-portfolio file machinery
# ---------------------------------------------------------------------------

def submission_path():
    return autonomous_mcp.submission_path(PORTFOLIO_ID)


def clear_submission():
    autonomous_mcp.clear_submission(PORTFOLIO_ID)


def read_submission():
    return autonomous_mcp.read_submission(PORTFOLIO_ID)


# ---------------------------------------------------------------------------
# book tools
# ---------------------------------------------------------------------------

@tool("get_my_book",
      "Your CURRENT Hong Kong portfolio: cash, NAV (HKD), and every holding with shares, weight, "
      "average cost, live HKD price, unrealized P&L, and the rationale you last gave it. The book "
      "holds Hong Kong names (*.HK) ONLY, marked in HKD. Call this FIRST to see exactly "
      "what you already hold before deciding today.",
      {})
async def get_my_book(args):
    from portfolio import fx, paper_account, registry
    state = paper_account._load_account(PORTFOLIO_ID)
    tickers = list((state.get("positions") or {}).keys())
    try:                                                  # one batched Yahoo request for the HK book
        from data_layer import yahoo_feed
        yahoo_feed.warm([t for t in tickers if (t or "").upper().endswith(".HK")])
    except Exception:
        pass
    prices: dict[str, float] = {}
    for t in tickers + [BENCHMARK]:
        base = fx.usd_to(paper_account._current_price(t), CURRENCY)   # shared store is USD → book ccy
        if base:
            prices[t] = base
    pnl = paper_account.positions_pnl(prices, PORTFOLIO_ID)
    nav = paper_account.nav(prices, PORTFOLIO_ID)
    rationales: dict[str, str] = {}
    latest = registry.data_dir(PORTFOLIO_ID) / "latest.json"
    try:
        if latest.exists():
            for p in (json.loads(latest.read_text()).get("positions") or []):
                rationales[p.get("ticker")] = p.get("rationale") or (p.get("thesis_full") or {}).get("summary")
    except Exception:
        pass
    holdings = []
    for t, rec in pnl.items():
        mv = rec.get("market_value")
        holdings.append({
            "ticker": t, "name": china_intake.display_name(t), "venue": china_intake._venue(t),
            "shares": rec.get("shares"), "avg_cost": rec.get("avg_cost"),
            "current_price": rec.get("current_price"), "market_value": mv,
            "weight": round(mv / nav, 4) if (mv and nav) else None,
            "unrealized_pnl": rec.get("unrealized_pnl"),
            "unrealized_pct": rec.get("unrealized_pct"),
            "rationale": rationales.get(t),
        })
    pending = paper_account.load_pending(PORTFOLIO_ID)
    return bot_mcp._json({
        "cash": round(float(state.get("cash") or 0.0), 2),
        "nav": round(nav, 2), "currency": CURRENCY,
        "benchmark": BENCHMARK,
        "starting_nav": state.get("starting_nav"),
        "inception_date": state.get("inception_date"),
        "n_holdings": len(holdings), "holdings": holdings,
        "pending_orders": pending,
    })


@tool("submit_book",
      "Submit your FINAL decided Hong Kong portfolio for today as a COMPLETE target book — this is how "
      "you express name selection and ordinal intent. For every row choose ADD, HOLD, or TRIM; a TRIM "
      "requires evidence and an ordinal intensity. The trusted incremental allocator computes all final "
      "weights; any numeric weight is optional audit context and never sizing authority. Omission is NOT an exit: any "
      "current holding you omit is carried unchanged unless it also appears in exit_decisions with "
      "decision evidence. Include every name you actively reviewed. The allocator preserves unchanged "
      "holdings and never invents marginal names merely to fill gross. Provide a one-paragraph rationale for EVERY holding (required) "
      "plus an overall summary, and optionally note what you sold and why. There is NO gate. Trade "
      "liquid Hong Kong listings ONLY (ticker like 0700.HK / 9988.HK); mainland A-shares and "
      "US-listed ADRs are REJECTED by this book. Confirm a name is priceable with get_quote "
      "before relying on it (names we cannot price are skipped). Call this ONCE, at the end. "
      "All governance fields added by this schema are REQUIRED: "
      "falsifiers (list of strings — what would cause you to reverse this book within 5 days), "
      "evidence_planes (list of strings — data sources you relied on), "
      "expected_failure_mode (string — the most likely way this book loses money).",
      decision_submission.enhance_schema({"type": "object", "properties": {
          "holdings": {"type": "array", "items": {"type": "object", "properties": {
              "ticker": {"type": "string", "description": "venue-suffixed: *.SS/*.SZ A-share, *.HK Hong Kong, bare = US ADR"},
              "weight": {"type": "number", "description": "fraction of NAV, 0-1"},
              "rationale": {"type": "string", "description": "one paragraph: why you own this, now — name the company alongside its ticker, e.g. Tencent (0700.HK), never a bare code"},
              "conviction": {"type": "string", "enum": ["high", "medium", "low"]}},
              "required": ["ticker", "weight", "rationale"]}},
          "summary": {"type": "string", "description": "overall thesis / how the book is positioned today — refer to each name by company name + ticker, e.g. Tencent (0700.HK)"},
          "sold_note": {"type": "string", "description": "optional: what you exited or trimmed and why"},
          "falsifiers": {"type": "array", "items": {"type": "string"},
                         "description": "what would cause you to reverse this book within 5 days"},
          "evidence_planes": {"type": "array", "items": {"type": "string"},
                              "description": "data sources / signal planes you relied on for this decision"},
          "expected_failure_mode": {"type": "string",
                                    "description": "the most likely way this book loses money"}},
       "required": ["holdings", "summary"]}))
async def submit_book(args):
    try:
        payload, audit = decision_submission.normalize(
            PORTFOLIO_ID, args, venue_of=china_intake._venue,
            allowed_venues=ALLOWED_VENUES, deterministic_sizing=True)
    except decision_submission.DecisionBoundaryFreeze as exc:
        return bot_mcp._ok(
            f"SUBMISSION REJECTED; prior paper book preserved unchanged. Trusted-boundary reason: {exc}"
        )
    cleaned = payload["holdings"]
    gross = float(payload["gross"])
    p = submission_path()
    decision_submission.write_atomic(p, payload)
    cash_pct = max(0.0, 1.0 - gross) * 100
    note = (f"HK book submitted: {len(cleaned)} holdings, {gross * 100:.0f}% invested, "
            f"{cash_pct:.0f}% cash" + (" (scaled to remove leverage)" if payload.get("scaled_to_no_leverage") else "")
            + (f". REJECTED {len(audit['rejected'])} off-venue name(s): " +
               ", ".join(r["ticker"] for r in audit["rejected"]) if audit.get("rejected") else "")
            + (f". Carried {len(audit['carried'])} omitted name(s) pending explicit exits" if audit.get("carried") else "")
            + (". Execution will fail closed until held-position quotes recover"
               if audit.get("quote_fallback_holdings") else "")
            + ". The desk will rebalance the paper account to these targets at the next mark.")
    return bot_mcp._ok(f"{BOOK_MARKER} {json.dumps({'n': len(cleaned), 'gross': round(gross, 4)})}\n{note}")


# ---------------------------------------------------------------------------
# China research read tools
# ---------------------------------------------------------------------------

@tool("get_china_regime",
      "The China macro-regime read: growth/inflation quadrant, scores + confidence, PBoC liquidity "
      "overlay, cycle tag, property read, sector RS, and current alerts. Your top-down frame.", {})
async def get_china_regime(args):
    raw = china_intake._read("china_regime/latest.json") or {}
    keep = ("date", "quad", "quad_name", "growth_score", "inflation_score", "confidence",
            "liquidity_overlay", "cycle_tag", "pending_quad", "sector_rs", "property",
            "fear_euphoria", "conditions", "alerts")
    return bot_mcp._json({k: raw.get(k) for k in keep if k in raw}
                         or {"note": "China regime not built yet."})


def _slim_standout(s: dict) -> dict:
    """Project a buy-board row to the decision-relevant fields — dropping the heavy spark_svg /
    axes / provenance blobs that would blow past the tool's serialization cap and corrupt the JSON."""
    if not isinstance(s, dict):
        return {}
    c = s.get("conviction") if isinstance(s.get("conviction"), dict) else {}
    size = c.get("size") if isinstance(c.get("size"), dict) else {}
    return {
        "ticker": s.get("ticker"), "name": s.get("name"), "sector": s.get("sector"),
        "label": s.get("label"), "urgency": s.get("urgency"), "dir": s.get("dir"),
        "alpha": s.get("alpha"), "alpha_entry": s.get("alpha_entry"),
        "conviction_score": c.get("score"), "band": c.get("band"),
        "entry_bucket": size.get("bucket"), "entry_note": size.get("note"),
        "verdict": c.get("verdict"), "cycle_blocked": c.get("cycle_blocked"),
    }


@tool("get_china_standouts",
      "The ranked China single-name buy boards: the A-share standouts (conviction score + band, "
      "label, urgency, residual alpha, and the ENTRY gate — entry_bucket='avoid' / cycle_blocked "
      "means good company but don't chase the entry) and the Hong-Kong buy board. The desks' best "
      "ideas right now.",
      {"type": "object", "properties": {"limit": {"type": "integer", "description": "max names per board (default 20, max 40)"}}})
async def get_china_standouts(args):
    limit = max(1, min(int(args.get("limit") or 20), 40))
    a = china_intake._read("factordata/china_standouts.json") or {}
    hk = china_intake._read("factordata/hk_standouts.json") or {}
    # Only surface the board(s) for this book's venue — the A-share book never sees the HK board.
    show_a = (not ALLOWED_VENUES) or ("A-share" in ALLOWED_VENUES)
    show_hk = (not ALLOWED_VENUES) or ("HK" in ALLOWED_VENUES)
    out: dict = {"as_of": a.get("as_of") or hk.get("as_of"),
                 "note": "Buy board(s) for this book's venue (slimmed). entry_bucket='avoid'/cycle_blocked "
                         "= wait for a pullback. Call get_china_intake for the corroborated ranking."}
    shrink: list[str] = []
    if show_a:
        out["a_share_buy"] = [_slim_standout(s) for s in (a.get("buy") or [])[:limit]]; shrink.append("a_share_buy")
    if show_hk:
        out["hk_buy"] = [_slim_standout(s) for s in (hk.get("buy") or [])[:limit]]; shrink.append("hk_buy")
    return _capped_json(out, shrink)


@tool("get_china_intake",
      "The UNIFIED China candidate funnel — every per-ticker China desk (A-share buy board, alpha "
      "leaders, reversal watch, HK board) deduped and ranked with provenance: which desks flagged "
      "each name, the directional lean, and the corroboration count. Your shortlist of what to study.",
      {"type": "object", "properties": {"limit": {"type": "integer", "description": "max candidates (default 25, max 60)"}}})
async def get_china_intake(args):
    limit = max(1, min(int(args.get("limit") or 25), 60))
    built = china_intake.build(limit)
    # Project a compact candidate row so the funnel — the Brain's primary shortlist — never exceeds
    # the tool serialization cap and returns truncated/invalid JSON. Restrict to the book's venue.
    slim = [{"ticker": c.get("ticker"), "name": china_intake.display_name(c.get("ticker")),
             "venue": c.get("venue"), "score": c.get("score"),
             "n_sources": c.get("n_sources"), "lean": c.get("lean"),
             "sources": c.get("sources"), "reasons": (c.get("reasons") or [])[:2],
             "falsifier": c.get("falsifier")}
            for c in (built.get("candidates") or [])
            if not ALLOWED_VENUES or c.get("venue") in ALLOWED_VENUES]
    return _capped_json({"as_of": built.get("as_of"), "macro_context": built.get("macro_context"),
                         "n_universe": built.get("n_universe"), "candidates": slim,
                         "note": built.get("note")}, ["candidates"])


@tool("get_china_brief",
      "The macro China desk's narrative brief — a context-only LLM read of the regime, the working "
      "rotation thesis, transmission channels to watch, and watch-items. Qualitative framing, not a "
      "scored signal.", {})
async def get_china_brief(args):
    b = china_intake._read("china_brief.json") or {}
    keep = ("summary", "regime_read", "rotation_check", "transmission", "watch_items",
            "conflicts", "confidence", "state_asof", "disclaimer")
    out = {k: b.get(k) for k in keep if k in b}
    return bot_mcp._json(out or {"note": "China brief not built yet."})


@tool("get_quote",
      "Confirm a Greater-China name is PRICEABLE and see its HKD mark before you rely on it. Returns "
      "the venue (A-share/HK/ADR), quote currency, the local-currency price, and the HKD price the "
      "book will actually transact at (HK names are native HKD; non-HK names are rejected by this book"
      "). priceable=false means the desk will SKIP this name — pick another.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_quote(args):
    from portfolio import fx, paper_account
    t = (args.get("ticker") or "").upper().strip()
    if not t:
        return bot_mcp._json({"error": "no ticker"})
    usd = paper_account._current_price(t)        # shared store returns USD
    base = fx.usd_to(usd, CURRENCY)              # the book's base currency (HKD for china, HKD for hk)
    cur = fx.currency_of(t)                       # native quote currency
    local = round(usd * fx.rate_per_usd(cur), 4) if usd else None   # native-currency price
    return bot_mcp._json({
        "ticker": t, "name": china_intake.display_name(t), "venue": china_intake._venue(t),
        "currency": cur, "price_local": local, "base_currency": CURRENCY,
        "price_base": round(base, 4) if base else None,
        "priceable": bool(base and base > 0),
    })


@tool("get_context_catalog",
      "Catalog of the directly wired Macro Dashboard, Terminal, Prophet, Neural Web and technical "
      "planes. Freshness and authority are explicit; use HK intake/regime for market selection.", {})
async def get_context_catalog(args):
    from brain import portfolio_intelligence
    return bot_mcp._json(portfolio_intelligence.context_catalog())


@tool("get_surface_packet",
      "Read one cataloged Macro/Terminal surface through a fixed artifact allowlist. This is bounded "
      "context only: never transplant a US-market read into the HK regime or grant it trade authority.",
      autonomous_mcp.SURFACE_PACKET_SCHEMA)
async def get_surface_packet(args):
    from brain import portfolio_intelligence
    return bot_mcp._json(portfolio_intelligence.surface_packet(
        str(args.get("surface_id") or ""), limit=args.get("limit", 6)))


@tool("get_technical_lab",
      "Golden Oracle, MACD-RSI, Stoch-RSI, multi-timeframe trend and entry-discipline evidence for "
      "one Hong Kong ticker. Missing fields stay explicit and technicals never override the HK intake.",
      {"type": "object", "properties": {
          "ticker": {"type": "string", "minLength": 1, "maxLength": 24}},
       "required": ["ticker"], "additionalProperties": False})
async def get_technical_lab(args):
    from brain import portfolio_intelligence
    return bot_mcp._json(portfolio_intelligence.technical_packet(str(args.get("ticker") or "")))


@tool("get_neural_web_packet",
      "Bounded Neural Web context for this HK book and up to six requested/held names. Context and "
      "provenance only; it cannot originate, size, block, or exit a trade.",
      autonomous_mcp.NEURAL_WEB_PACKET_SCHEMA)
async def get_neural_web_packet(args):
    from brain import portfolio_intelligence
    return bot_mcp._json(portfolio_intelligence.neural_web_packet(
        PORTFOLIO_ID, tickers=args.get("tickers")))


@tool("request_context_upgrade",
      "Queue a bounded request for missing HK decision context. Review only: it does not change code, "
      "tools, sizing, or execution authority.",
      {"type": "object", "properties": {
          "plane": {"type": "string"}, "reason": {"type": "string"},
          "ticker": {"type": "string"}},
       "required": ["plane", "reason"], "additionalProperties": False})
async def request_context_upgrade(args):
    from brain import portfolio_learning
    return bot_mcp._json(portfolio_learning.request_context(
        PORTFOLIO_ID, args.get("plane"), args.get("reason"), args.get("ticker")))


_DESK_TOOLS = [get_my_book, submit_book]
_READ_TOOLS = [get_china_regime, get_china_standouts, get_china_intake, get_china_brief,
               get_quote, get_context_catalog, get_surface_packet, get_technical_lab,
               get_neural_web_packet, request_context_upgrade]
_ALL_TOOLS = _DESK_TOOLS + _READ_TOOLS


def build_servers() -> dict:
    """The mcp_servers map: a single 'china' server with the desk + China read tools."""
    return {SERVER_NAME: create_sdk_mcp_server(name=SERVER_NAME, version="0.1.0", tools=_ALL_TOOLS)}


def allowed_tools() -> list[str]:
    """The china desk's own tools + web. NO raw Read/Grep/Glob, NO flagship get_portfolio, NO gated
    execute_trade — a free-form book that can only see its OWN state and the China desks."""
    return [f"mcp__{SERVER_NAME}__{t.name}" for t in _ALL_TOOLS] + bot_mcp.WEB_TOOLS + ["Task"]
