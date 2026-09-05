"""Tests for the bot's MCP tool surface — the read + write-back armament for Claude.

These exercise the tools DIRECTLY (no Claude auth needed), proving the armament works:
Claude's reads return real dashboard data and its actions write to the app's review queue.
"""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import bot  # noqa: F401
import pytest
from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk._internal.query import Query

from brain import bot_mcp, cli_bridge

_ROOT = Path(__file__).resolve().parent.parent


def _text(result: dict) -> str:
    return result["content"][0]["text"]


def _strict_json(text: str):
    return json.loads(
        text,
        parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
    )


def _utf8_bytes(text: str) -> int:
    return len(text.encode("utf-8"))


async def _sdk_wire_tool_call(config: dict, tool_name: str, arguments: dict) -> dict:
    """Drive the actual SDK in-memory server over its JSON-RPC request seam."""
    transport = AsyncMock()
    transport.is_ready = Mock(return_value=True)
    query = Query(
        transport=transport,
        is_streaming_mode=True,
        sdk_mcp_servers={"bot": config["instance"]},
    )
    try:
        initialized = await query._handle_sdk_mcp_request(
            "bot",
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "0"},
                },
            },
        )
        assert initialized and "result" in initialized
        assert await query._handle_sdk_mcp_request(
            "bot",
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
        ) is None
        response = await query._handle_sdk_mcp_request(
            "bot",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
        )
        assert response and "error" not in response
        return response["result"]
    finally:
        await query.close()
        query.close_receive_stream()


def test_read_tools_return_real_data():
    reg = json.loads(_text(asyncio.run(bot_mcp.get_regime.handler({}))))
    if reg.get("quad") is None:
        pytest.skip("live vendor/macro regime data is unavailable in this worktree")
    assert reg["quad"] in {"Q1", "Q2", "Q3", "Q4"}          # live regime
    themes = json.loads(_text(asyncio.run(bot_mcp.get_themes.handler({"region": "us"}))))
    assert isinstance(themes["themes"], list) and themes["themes"]


def test_read_signal_is_allowlisted():
    denied = _text(asyncio.run(bot_mcp.read_signal.handler({"path": "/etc/passwd"})))
    assert "DENIED" in denied


def test_action_tools_write_to_review_queue(tmp_path, monkeypatch):
    # isolate writes to a temp dir — the action handlers persist real files, and
    # without this the suite would spam stub notes/proposals into the live data feed.
    monkeypatch.setattr(bot_mcp, "_ROOT", tmp_path)
    monkeypatch.setattr(bot_mcp, "_RESEARCH", tmp_path / "data" / "research")
    monkeypatch.setattr(bot_mcp, "_PROPOSALS", tmp_path / "data" / "brain" / "proposals.jsonl")

    note = _text(asyncio.run(bot_mcp.save_research_note.handler(
        {"title": "AI power bottleneck", "body": "Compute is migrating to electricity.",
         "tickers": ["NVDA", "VST"]})))
    assert "research note" in note and (tmp_path / "data" / "research" / "notes").exists()

    prop = _text(asyncio.run(bot_mcp.propose_thesis.handler(
        {"subject": "VST", "lean": "add", "conviction": "medium",
         "thesis": "Power demand from AI data centers", "horizon_d": 60})))
    assert "review queue" in prop and "NOT executed" in prop
    rows = (tmp_path / "data" / "brain" / "proposals.jsonl").read_text().strip().splitlines()
    assert json.loads(rows[-1])["subject"] == "VST"


def test_server_and_allowlist_build():
    srv = bot_mcp.build_server()
    assert srv is not None
    allowed = bot_mcp.armed_allowed_tools()
    assert "mcp__bot__get_regime" in allowed and "WebSearch" in allowed
    assert "mcp__bot__propose_thesis" in allowed


def test_json_transport_compaction_remains_valid_json():
    result = bot_mcp._json(
        {
            "rows": [
                {"rank": rank, "detail": "x" * 1_000}
                for rank in range(100)
            ],
            "status": "ok",
        }
    )
    text = _text(result)
    parsed = json.loads(text)

    assert len(text) <= 8_000
    assert parsed["status"] == "ok"
    assert parsed["_transport_truncated"] is True
    assert parsed["rows"]


def test_json_transport_preserves_ordinary_json_and_counts_utf8_bytes():
    result = bot_mcp._json(
        {"status": "ok", "none": None, "zero": 0, "flag": False, "rows": ["電", "🚀"]}
    )
    text = _text(result)

    assert _strict_json(text) == {
        "status": "ok", "none": None, "zero": 0, "flag": False, "rows": ["電", "🚀"]
    }
    assert _utf8_bytes(text) <= 8_000
    assert result.get("is_error") is not True


def test_json_transport_accepts_exactly_8000_bytes_and_compacts_8001():
    exact = bot_mcp._json({"v": "x" * 7_991})
    overflow = bot_mcp._json({"v": "x" * 7_992})

    assert _utf8_bytes(_text(exact)) == 8_000
    assert _strict_json(_text(exact)) == {"v": "x" * 7_991}
    assert _utf8_bytes(_text(overflow)) <= 8_000
    assert _strict_json(_text(overflow))["_transport_truncated"] is True


@pytest.mark.parametrize(
    "payload",
    (
        {"v": "x" * 7_991},       # exactly 8,000 serialized UTF-8 bytes
        {"v": "x" * 7_992},       # 8,001 bytes must compact instead of overflow
        {"v": "電" * 2_700},       # character count is under 8k; UTF-8 bytes are not
        {"v": "🚀" * 4_000},
        {f"key-{index}": 1 for index in range(1_500)},
        {f"key-{index}": "x" * 200 for index in range(150)},
    ),
)
def test_json_transport_never_exceeds_utf8_budget_for_valid_payloads(payload):
    result = bot_mcp._json(payload)
    text = _text(result)

    assert _utf8_bytes(text) <= 8_000
    _strict_json(text)
    assert result.get("is_error") is not True


def test_json_transport_returns_fixed_error_for_wide_scalar_fallback():
    result = bot_mcp._json({"k" * 9_000: 1})
    text = _text(result)

    assert _strict_json(text) == {"error": "MCP_RESPONSE_TOO_LARGE"}
    assert result["is_error"] is True
    assert _utf8_bytes(text) <= 8_000


@pytest.mark.parametrize("value", (float("nan"), float("inf"), float("-inf"), "\ud800"))
def test_json_transport_returns_fixed_error_for_non_strict_or_unencodable_values(value):
    result = bot_mcp._json({"value": value})
    text = _text(result)

    assert _strict_json(text) == {"error": "MCP_RESPONSE_NOT_JSON"}
    assert result["is_error"] is True
    assert _utf8_bytes(text) <= 8_000


def test_json_transport_catches_base_exception_from_default_serialization():
    class ExplosiveStringification:
        def __str__(self):
            raise BaseException("do not leak this")

    result = bot_mcp._json({"value": ExplosiveStringification()})

    assert _strict_json(_text(result)) == {"error": "MCP_RESPONSE_NOT_JSON"}
    assert result["is_error"] is True


def test_real_decorated_handler_sets_sdk_wire_error_once(monkeypatch):
    producer_calls = 0
    handler_calls = 0
    original_handler = bot_mcp.get_regime.handler

    def invalid_regime(_path):
        nonlocal producer_calls
        producer_calls += 1
        return {"quad": "Q1", "sector_rs": [float("nan")]}

    async def counted_handler(args):
        nonlocal handler_calls
        handler_calls += 1
        return await original_handler(args)

    monkeypatch.setattr(bot_mcp, "_read_json", invalid_regime)
    monkeypatch.setattr(bot_mcp.get_regime, "handler", counted_handler)

    wire = asyncio.run(_sdk_wire_tool_call(bot_mcp.build_server(), "get_regime", {}))

    assert handler_calls == 1
    assert producer_calls == 1
    assert wire["isError"] is True
    assert _strict_json(wire["content"][0]["text"]) == {"error": "MCP_RESPONSE_NOT_JSON"}


def test_sdk_does_not_treat_camel_case_handler_error_as_an_error():
    @tool("camel_only", "Negative handler-key control.", {})
    async def camel_only(_args):
        return {
            "content": [{"type": "text", "text": '{"error":"MCP_RESPONSE_NOT_JSON"}'}],
            "isError": True,
        }

    config = create_sdk_mcp_server(name="camel-only", version="0", tools=[camel_only])
    wire = asyncio.run(_sdk_wire_tool_call(config, "camel_only", {}))

    assert wire.get("isError", False) is False


def test_subscription_env_strips_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    env = cli_bridge._subscription_env()
    assert "ANTHROPIC_API_KEY" not in env                   # subscription, not metered API


def test_intake_tools_registered_and_callable():
    # the Phase-6 intake / transmission tools must be armed
    allowed = bot_mcp.armed_allowed_tools()
    for name in ("get_daily_briefing", "get_intake_candidates", "get_ticker_package"):
        assert f"mcp__bot__{name}" in allowed

    # get_daily_briefing — macro frame + ranked queue (composes live from the intake funnel
    # when briefing.json isn't vendored yet; must never error)
    brief = json.loads(_text(asyncio.run(bot_mcp.get_daily_briefing.handler({"top": 5}))))
    assert "macro_context" in brief
    assert "priority_queue" in brief and isinstance(brief["priority_queue"], list)

    # get_intake_candidates — unified queue with provenance; tiers split on request
    cand = json.loads(_text(asyncio.run(bot_mcp.get_intake_candidates.handler({"limit": 8, "tiers": True}))))
    assert "candidates" in cand and isinstance(cand["candidates"], list)
    assert "salience" in cand and {"act", "watch", "divergent"} <= set(cand["salience"])
    for c in cand["candidates"]:
        assert "ticker" in c and "score" in c and "sources" in c    # provenance present


def test_ticker_package_degrades_cleanly():
    # a name with no dashboard coverage degrades to a plain message, never raises
    out = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "ZZZZ"})))
    assert "ZZZZ" in out


def test_intel_hub_tool(tmp_path, monkeypatch):
    # armed + degrades cleanly when hub.json absent
    assert "mcp__bot__get_intel_hub" in bot_mcp.armed_allowed_tools()
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "novendor")
    assert "not built yet" in _text(asyncio.run(bot_mcp.get_intel_hub.handler({})))

    # with a hub.json present: command pull (no ticker) + single-dossier pull (ticker)
    hub = {"as_of": "2026-06-21", "macro_context": {"regime": "Goldilocks"},
           "desks": {"policy": {"live": True}}, "counts": {"theme_wide": 3},
           "n_actionable": 2, "divergence_alerts": {"early_edge": [], "crowded_top": []},
           "sector_heat": [{"etf": "XLK", "mean_conviction": 31.6}],
           "how_to_use": "read macro first",
           "command": [{"ticker": "NVDA", "name": "Nvidia", "composite_conviction": 100,
                        "lean": 1, "n_confirm": 5, "flags": ["confirmed_trend", "theme_wide"],
                        "read": "5 desks agree", "peers": ["DELL", "MSFT"], "falsifier": None}]}
    site = tmp_path / "novendor" / "site" / "intel_hub"
    site.mkdir(parents=True)
    (site / "hub.json").write_text(json.dumps(hub))

    full = json.loads(_text(asyncio.run(bot_mcp.get_intel_hub.handler({"top": 5}))))
    assert full["macro_context"]["regime"] == "Goldilocks"
    assert full["command"][0]["ticker"] == "NVDA" and "theme_wide" in full["command"][0]["flags"]
    assert "sector_heat" in full and "counts" in full

    one = json.loads(_text(asyncio.run(bot_mcp.get_intel_hub.handler({"ticker": "nvda"}))))
    assert one["ticker"] == "NVDA" and one["composite_conviction"] == 100
    assert "ZZZZ not in" in _text(asyncio.run(bot_mcp.get_intel_hub.handler({"ticker": "ZZZZ"})))
