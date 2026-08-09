"""The US Brain v2 MCP surface — typed evidence in, explicit target decisions out.

This is the sole active US stock-selection portfolio.  Prophet and Macro intelligence are
high-signal discovery/context planes, not automatic buy authority.  A single accountable
manager selects common stocks, validates timing, and calls ``submit_book`` once.  The trusted
boundary rejects ETFs and never treats an omitted holding as an implicit sell.

The tool does NOT execute the trade itself; it RECORDS the decided book to a per-portfolio
file (``_pending_decision.json``). The deterministic builder (``bot/autonomous.py``) reads it
after the session and rebalances the paper account to those targets under the usual
market-hours discipline — so all the trading logic stays in the trusted Python layer, bound
to the autonomous book only.
"""
from __future__ import annotations

import json
from pathlib import Path

import bot  # noqa: F401
from claude_agent_sdk import tool, create_sdk_mcp_server

from brain import bot_mcp

SERVER_NAME = "desk"
PORTFOLIO_ID = "autonomous"

# Marker the builder / any streaming layer can scan a tool result for.
BOOK_MARKER = "__BOOK__"

# Enum-like IDs keep the MCP boundary on the same fixed allowlist as
# portfolio_intelligence.surface_packet; callers can never supply a filesystem path.
SURFACE_IDS = (
    "sector_central", "intelligence_hub", "foresight", "radar", "state_of_themes",
    "etfs", "macro_context", "movers", "intraday_flow", "options",
    "confluence_screener", "stock_seasonality", "prophet", "neural_web",
    "golden_oracle", "technical_lab",
)
SURFACE_PACKET_SCHEMA = {
    "type": "object",
    "properties": {
        "surface_id": {"type": "string", "enum": list(SURFACE_IDS)},
        "limit": {"type": "integer", "minimum": 1, "maximum": 8},
    },
    "required": ["surface_id"],
    "additionalProperties": False,
}
NEURAL_WEB_PACKET_SCHEMA = {
    "type": "object",
    "properties": {
        "tickers": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 24},
            "maxItems": 6,
            "uniqueItems": True,
        },
    },
    "additionalProperties": False,
}


def submission_path(portfolio_id: str = PORTFOLIO_ID) -> Path:
    from portfolio import registry
    return registry.data_dir(portfolio_id) / "_pending_decision.json"


def clear_submission(portfolio_id: str = PORTFOLIO_ID) -> None:
    """Remove a stale decision file before a fresh run so a no-op turn can't replay yesterday."""
    try:
        submission_path(portfolio_id).unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass


def read_submission(portfolio_id: str = PORTFOLIO_ID) -> dict | None:
    p = submission_path(portfolio_id)
    try:
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------

@tool("get_my_book",
      "Your CURRENT autonomous portfolio: cash, NAV, and every holding with its shares, weight, "
      "average cost, live price, unrealized P&L, and the rationale you last gave it. Call this FIRST "
      "to see exactly what you already hold before deciding today's trades.",
      {})
async def get_my_book(args):
    from portfolio import paper_account, registry
    state = paper_account._load_account(PORTFOLIO_ID)
    tickers = list((state.get("positions") or {}).keys())
    prices: dict[str, float] = {}
    for t in tickers + ["SPY"]:
        px = paper_account._current_price(t)
        if px:
            prices[t] = px
    pnl = paper_account.positions_pnl(prices, PORTFOLIO_ID)
    nav = paper_account.nav(prices, PORTFOLIO_ID)
    # prior rationales from the last published book
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
            "ticker": t,
            "shares": rec.get("shares"),
            "avg_cost": rec.get("avg_cost"),
            "current_price": rec.get("current_price"),
            "market_value": mv,
            "weight": round(mv / nav, 4) if (mv and nav) else None,
            "unrealized_pnl": rec.get("unrealized_pnl"),
            "unrealized_pct": rec.get("unrealized_pct"),
            "rationale": rationales.get(t),
        })
    pending = paper_account.load_pending(PORTFOLIO_ID)
    return bot_mcp._json({
        "cash": round(float(state.get("cash") or 0.0), 2),
        "nav": round(nav, 2),
        "starting_nav": state.get("starting_nav"),
        "inception_date": state.get("inception_date"),
        "n_holdings": len(holdings),
        "holdings": holdings,
        "pending_orders": pending,
    })


@tool("submit_book",
      "Submit the FINAL US stock portfolio once. Include every desired holding and an explicit "
      "exit_decisions record for each held name you intend to sell; omission alone NEVER sells. "
      "ETFs are rejected and any legacy ETF is quarantined until an explicit "
      "legacy_instrument_migration exit. For each row choose ADD, HOLD, or TRIM; TRIM requires "
      "evidence and an ordinal intensity. The trusted allocator alone computes weights, so any numeric "
      "weight is optional audit context and never authority. Each holding must state why-now, falsifier, "
      "source provenance, expected horizon and exit plan. Provide a structured decision_memo so the "
      "dashboard can show the candidate funnel, timing, rejected alternatives and lessons without "
      "publishing hidden chain-of-thought.",
      {"type": "object", "properties": {
          "holdings": {"type": "array", "items": {"type": "object", "properties": {
              "ticker": {"type": "string"},
              "weight": {"type": "number", "description": "optional advisory fraction; ignored for sizing"},
              "rationale": {"type": "string", "description": "one paragraph: why you own this, now"},
              "conviction": {"type": "string", "enum": ["high", "medium", "low"]},
              "action": {"type": "string", "enum": ["add", "hold", "trim"]},
              "trim_intensity": {"type": "string", "enum": ["light", "standard", "deep"]},
              "why_now": {"type": "string"}, "falsifier": {"type": "string"},
              "evidence": {"type": "array", "items": {"type": "string"}},
              "source_provenance": {"type": "array", "items": {"type": "string"}},
              "expected_horizon": {"type": "string"}, "exit_plan": {"type": "string"}},
              "required": ["ticker", "rationale", "conviction", "action", "why_now", "falsifier",
                           "evidence", "source_provenance", "expected_horizon", "exit_plan"]}},
          "summary": {"type": "string", "description": "overall thesis / how the book is positioned today"},
          "sold_note": {"type": "string", "description": "optional: what you exited or trimmed and why"},
          "exit_decisions": {"type": "array", "items": {"type": "object", "properties": {
              "ticker": {"type": "string"}, "action": {"type": "string", "enum": ["exit"]},
              "reason": {"type": "string"},
              "reason_code": {"type": "string", "enum": ["hard_falsifier", "technical_break",
                  "material_thesis_change", "risk_limit", "fraud_or_delisting", "stop_breach",
                  "legacy_instrument_migration", "thesis_change"]},
              "evidence": {"type": "array", "items": {"type": "string"}},
              "falsifier": {"type": "string"}, "why_now": {"type": "string"}},
              "required": ["ticker", "action", "reason", "reason_code", "evidence", "why_now"]}},
          "falsifiers": {"type": "array", "items": {"type": "string"},
                         "description": "what would cause you to reverse this book within 5 days"},
          "evidence_planes": {"type": "array", "items": {"type": "string"},
                              "description": "data sources / signal planes you relied on for this decision"},
          "source_provenance": {"type": "array", "items": {"type": "string"}},
          "liquidity_notes": {"type": "string"},
          "risk_posture": {"type": "string", "enum": ["normal", "caution", "crash"]},
          "cash_rationale": {"type": "string"},
          "expected_failure_mode": {"type": "string",
                                    "description": "the most likely way this book loses money"},
          "decision_memo": {"type": "object", "properties": {
              "market_frame": {}, "candidate_funnel": {}, "selected": {}, "rejected": {},
              "changes": {}, "timing": {}, "risk_deliberation": {}, "alternatives": {},
              "lessons_applied": {}, "context_gaps": {}, "delegation_summary": {}}}},
       "required": ["holdings", "summary", "exit_decisions", "falsifiers", "evidence_planes",
                    "source_provenance", "expected_failure_mode", "risk_posture",
                    "cash_rationale", "decision_memo"]})
async def submit_book(args):
    from brain import decision_submission
    try:
        payload, audit = decision_submission.normalize(
            PORTFOLIO_ID, args, stock_only=True, early_exit_hysteresis=True,
            deterministic_sizing=True)
    except decision_submission.DecisionBoundaryFreeze as exc:
        return bot_mcp._ok(
            f"SUBMISSION REJECTED; prior paper book preserved unchanged. Trusted-boundary reason: {exc}"
        )
    cleaned = payload["holdings"]
    gross = float(payload["gross"])
    p = submission_path()
    decision_submission.write_atomic(p, payload)
    cash_pct = max(0.0, 1.0 - gross) * 100
    note = (f"Book submitted: {len(cleaned)} holdings, {gross * 100:.0f}% invested, {cash_pct:.0f}% cash"
            + (" (scaled to remove leverage)" if payload.get("scaled_to_no_leverage") else "")
            + (f". Carried {len(audit['carried'])} omitted/early-exit name(s) pending an explicit valid exit"
               if audit.get("carried") else "")
            + (f". Quarantined {len(audit['quarantined'])} legacy/non-stock holding(s) without trading them"
               if audit.get("quarantined") else "")
            + (". Execution will fail closed until held-position quotes recover"
               if audit.get("quote_fallback_holdings") else "")
            + (f". Rejected {len(audit['rejected'])} ETF/invalid name(s)" if audit.get("rejected") else "")
            + ". The desk will rebalance the paper account to these targets at the next mark.")
    return bot_mcp._ok(f"{BOOK_MARKER} {json.dumps({'n': len(cleaned), 'gross': round(gross, 4)})}\n{note}")


@tool("get_market_packet", "Compact US regime, data-health, Prophet and sector-rotation packet. Call early.", {})
async def get_market_packet(args):
    from brain import portfolio_intelligence
    return bot_mcp._json(portfolio_intelligence.market_packet(PORTFOLIO_ID))


@tool("get_prophet_board", "Prophet's current Enter/Wait candidates plus active Hold/Trail plans. Discovery and geometry, never automatic authority.",
      {"type": "object", "properties": {"limit": {"type": "integer"}}})
async def get_prophet_board(args):
    from brain import portfolio_intelligence
    return bot_mcp._json(portfolio_intelligence.prophet_board(limit=int(args.get("limit") or 24)))


@tool("get_sector_rotation", "Current Sector Central leaders, laggards and rotation state in a bounded packet.",
      {"type": "object", "properties": {"limit": {"type": "integer"}}})
async def get_sector_rotation(args):
    from brain import portfolio_intelligence
    return bot_mcp._json(portfolio_intelligence.sector_rotation(limit=int(args.get("limit") or 12)))


@tool("get_technical_lab", "Golden Oracle, MACD-RSI, Stoch-RSI, multi-timeframe trend, Prophet geometry and entry-discipline packet for one ticker.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_technical_lab(args):
    from brain import portfolio_intelligence
    return bot_mcp._json(portfolio_intelligence.technical_packet(str(args.get("ticker") or "")))


@tool("get_context_catalog", "Catalog of directly wired Macro Dashboard, Terminal, Prophet, Neural Web and technical data planes with freshness and authority.", {})
async def get_context_catalog(args):
    from brain import portfolio_intelligence
    return bot_mcp._json(portfolio_intelligence.context_catalog())


@tool("get_surface_packet", "Read one cataloged Macro/Terminal surface through a fixed artifact allowlist. Returns bounded decision context and freshness; never sizing or execution authority.",
      SURFACE_PACKET_SCHEMA)
async def get_surface_packet(args):
    from brain import portfolio_intelligence
    return bot_mcp._json(portfolio_intelligence.surface_packet(
        str(args.get("surface_id") or ""), limit=args.get("limit", 6)))


@tool("get_neural_web_packet", "Bounded Neural Web context for this US book and up to six requested/held names. Context and provenance only; it cannot originate, size, block, or exit a trade.",
      NEURAL_WEB_PACKET_SCHEMA)
async def get_neural_web_packet(args):
    from brain import portfolio_intelligence
    return bot_mcp._json(portfolio_intelligence.neural_web_packet(
        PORTFOLIO_ID, tickers=args.get("tickers")))


@tool("request_context_upgrade", "Queue a bounded request for a missing decision-relevant context plane. This requests review; it does not change code or authority.",
      {"type": "object", "properties": {"plane": {"type": "string"}, "reason": {"type": "string"},
       "ticker": {"type": "string"}}, "required": ["plane", "reason"]})
async def request_context_upgrade(args):
    from brain import portfolio_learning
    return bot_mcp._json(portfolio_learning.request_context(
        PORTFOLIO_ID, args.get("plane"), args.get("reason"), args.get("ticker")))


_DESK_TOOLS = [get_my_book, get_market_packet, get_prophet_board, get_sector_rotation,
               get_technical_lab, get_context_catalog, get_surface_packet,
               get_neural_web_packet, request_context_upgrade, submit_book]

# Reuse the macro-dashboard READ tools, but drop get_portfolio (that's the FLAGSHIP book — the
# autonomous Brain reads its OWN book via get_my_book to avoid confusion).
_READ_TOOLS = [t for t in bot_mcp._READ if t.name != "get_portfolio"]


def build_servers() -> dict:
    """The mcp_servers map to hand the SDK: the macro READ tools (bot) + this desk."""
    return {
        bot_mcp.SERVER_NAME: create_sdk_mcp_server(name=bot_mcp.SERVER_NAME, version="0.1.0", tools=_READ_TOOLS),
        SERVER_NAME: create_sdk_mcp_server(name=SERVER_NAME, version="0.1.0", tools=_DESK_TOOLS),
    }


def allowed_tools() -> list[str]:
    """Macro READ tools + the desk's own tools + web. NO gated execute_trade / research-paper
    tools — this book is free-form.

    Deliberately NO raw Read/Grep/Glob: with the session cwd at the repo root those reached ANY
    file — including the OTHER books' state (data/portfolio/latest.json) — with no allowlist,
    which was a latent path for the autonomous Brain to peek at Flagship. The Brain researches
    only through the typed mcp__bot__* read tools + the web; it reads its OWN book via the desk.
    The path-controlled mcp__bot__read_signal is still available but now denies portfolio-book
    dirs (see bot_mcp._DENY_ROOTS)."""
    read = [f"mcp__{bot_mcp.SERVER_NAME}__{t.name}" for t in _READ_TOOLS]
    desk = [f"mcp__{SERVER_NAME}__{t.name}" for t in _DESK_TOOLS]
    # Claude fallback uses the built-in Task dispatcher; project subagents are separately
    # restricted to Read/Grep/Glob and cannot see this desk's submit tool. Codex uses its
    # project-local `.codex/agents` definitions instead and ignores this allow-list.
    return read + desk + bot_mcp.WEB_TOOLS + ["Task"]
