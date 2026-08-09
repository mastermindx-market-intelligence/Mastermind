"""Expose an existing Mastermind in-process MCP surface over stdio.

Codex CLI speaks standard MCP over stdio, while the original Claude Agent SDK
embedded these servers directly in the bot process.  This adapter rebuilds the
same book-scoped surface in a child process; it does not add tools or authority.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server
from mcp.server.stdio import stdio_server

_RETIRED_BOOKS = {"flagship", "heavyweight", "etf"}
_ACTIVE_RESEARCH_BOOKS = {"autonomous", "china", "hk"}
_RESEARCH_SERVER_NAME = "research"
_RESEARCH_TOOLS_BY_BOOK: dict[str, tuple[str, ...]] = {
    "autonomous": (
        "get_regime", "get_overnight_tape", "get_themes", "get_standouts",
        "get_decision_matrix", "get_divergences", "get_altdata", "get_news",
        "get_intelligence", "get_intel_hub", "get_daily_briefing", "get_intake_candidates",
        "get_ticker_package", "get_fundamentals", "get_options", "get_anticipation",
        "get_quote", "evaluate_gate", "read_signal", "get_my_book", "get_market_packet",
        "get_prophet_board", "get_sector_rotation", "get_technical_lab", "get_context_catalog",
        "get_surface_packet", "get_neural_web_packet",
    ),
    "china": (
        "get_my_book", "get_china_regime", "get_china_standouts", "get_china_intake",
        "get_china_brief", "get_quote", "get_context_catalog", "get_surface_packet",
        "get_technical_lab", "get_neural_web_packet",
    ),
    "hk": (
        "get_my_book", "get_china_regime", "get_china_standouts", "get_china_intake",
        "get_china_brief", "get_quote", "get_context_catalog", "get_surface_packet",
        "get_technical_lab", "get_neural_web_packet",
    ),
}
_MCP_SECRET_FILE_ENV = "MASTERMIND_CODEX_MCP_SECRET_FILE"
_MCP_SECRET_KEYS = frozenset({
    # Read-only data-vendor credentials used by bounded quote/macro/news readers. Never provider,
    # database, storage, messaging, OAuth, or portfolio-control credentials.
    "POLYGON_API_KEY", "MASSIVE_API_KEY", "FRED_API_KEY", "FINNHUB_KEY",
    "FINNHUB_API_KEY", "TUSHARE_TOKEN",
})


def _load_secret_env(path: str | None = None) -> set[str]:
    """Load an owner-only, bridge-created bundle into this MCP process only.

    The Codex/model process receives only the bundle path, never the values.  Refuse symlinks,
    group/world-readable files, oversized payloads, and every key outside the fixed read-vendor
    allow-list.  Do not log either keys or values on failure.
    """
    raw_path = path or os.environ.get(_MCP_SECRET_FILE_ENV, "")
    if not raw_path:
        return set()
    bundle = Path(raw_path)
    try:
        if bundle.is_symlink():
            return set()
        meta = bundle.stat()
        if not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o077 or meta.st_size > 65_536:
            return set()
        data = json.loads(bundle.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if not isinstance(data, dict) or any(key not in _MCP_SECRET_KEYS for key in data):
        return set()
    loaded: set[str] = set()
    for key, value in data.items():
        if isinstance(value, str) and value and len(value) <= 8_192:
            os.environ[key] = value
            loaded.add(key)
    return loaded


def _reject_archived(book: str) -> None:
    """Never construct a state-capable MCP server for an archived portfolio."""
    portfolio_id = "flagship" if book == "flagship_judgment" else book
    try:
        from portfolio import registry
        if registry.is_archived(portfolio_id):
            meta = registry.get(portfolio_id)
            raise SystemExit(
                f"MCP disabled: portfolio {portfolio_id!r} is archived and superseded by "
                f"{meta.get('superseded_by') or 'an active successor'!r}"
            )
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - retired books fail closed if registry lookup is unavailable
        if portfolio_id in _RETIRED_BOOKS:
            raise SystemExit(
                f"MCP disabled: could not verify archived portfolio {portfolio_id!r} as active"
            ) from None


def _servers_for(book: str) -> dict:
    _reject_archived(book)
    if book == "autonomous":
        from brain import autonomous_mcp as mod
        return mod.build_servers()
    if book == "etf":
        from brain import etf_mcp as mod
        return mod.build_servers()
    if book == "heavyweight":
        from brain import heavyweight_mcp as mod
        return mod.build_servers()
    if book == "china":
        from brain import china_mcp as mod
        return mod.build_servers()
    if book == "hk":
        from brain import hk_mcp as mod
        return mod.build_servers()
    if book in {"flagship", "flagship_judgment"}:
        from brain import flagship_desk_mcp as mod
        return mod.build_servers()
    from brain import bot_mcp
    return {bot_mcp.SERVER_NAME: bot_mcp.build_server()}


def build_research_server(book: str) -> dict:
    """Build the one child-only, read-only MCP config for an active portfolio."""
    if book not in _ACTIVE_RESEARCH_BOOKS:
        raise SystemExit("research MCP requires an explicit active portfolio book")
    if book == "autonomous":
        from brain import autonomous_mcp as mod
        candidates = list(mod._READ_TOOLS) + list(mod._DESK_TOOLS)
    elif book == "china":
        from brain import china_mcp as mod
        candidates = list(mod._ALL_TOOLS)
    else:
        from brain import hk_mcp as mod
        candidates = list(mod._ALL_TOOLS)
    available = {tool.name: tool for tool in candidates}
    allowed = _RESEARCH_TOOLS_BY_BOOK[book]
    if set(allowed) - set(available):
        raise SystemExit("research MCP read-only policy is unavailable")
    tools = [available[name] for name in allowed]
    return create_sdk_mcp_server(
        name=_RESEARCH_SERVER_NAME,
        version="0.1.0",
        tools=tools,
    )


def research_tool_names(book: str) -> tuple[str, ...]:
    """Return the audited fixed allow-list without constructing a transport."""
    if book not in _ACTIVE_RESEARCH_BOOKS:
        raise SystemExit("research MCP requires an explicit active portfolio book")
    return _RESEARCH_TOOLS_BY_BOOK[book]


def server_instance(book: str, name: str):
    if name == _RESEARCH_SERVER_NAME:
        return build_research_server(book)["instance"]
    servers = _servers_for(book)
    cfg = servers.get(name)
    if not isinstance(cfg, dict) or cfg.get("type") != "sdk" or not cfg.get("instance"):
        raise SystemExit(f"MCP server {name!r} is not authorized for book {book!r}")
    return cfg["instance"]


async def _run(book: str, name: str) -> None:
    server = server_instance(book, name)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
            raise_exceptions=False,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", default=None)
    parser.add_argument("--book-env", default=None)
    parser.add_argument("--server", required=True)
    args = parser.parse_args()
    _load_secret_env()
    book = args.book
    if args.book_env:
        book = os.environ.get(str(args.book_env), "")
    asyncio.run(_run(str(book or "system"), args.server))


if __name__ == "__main__":
    main()
