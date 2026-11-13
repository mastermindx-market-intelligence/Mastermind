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


def _count_vendored_read(tmp_path, monkeypatch, relative_path, payload):
    """Count the selected file read through the unchanged checked producer."""
    _write_vendored(tmp_path, relative_path, payload)
    selected = tmp_path / relative_path
    original_read = Path.read_text
    reads = {"count": 0}

    def counted_read(path, *args, **kwargs):
        if path == selected:
            reads["count"] += 1
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    monkeypatch.setattr(Path, "read_text", counted_read)
    return reads


def _isolate_regime_enrichment(monkeypatch):
    from brain import decision_context, pm_conviction

    monkeypatch.setattr(pm_conviction, "_read_market_view", lambda: None)
    monkeypatch.setattr(pm_conviction, "_market_view_enrichment", lambda _view: None)
    monkeypatch.setattr(decision_context, "prompt_summary", lambda **_kwargs: None)


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


def test_json_transport_measures_final_unicode_payload_after_metadata():
    result = bot_mcp._json({"rows": ["電" * 240 for _ in range(20)]})
    text = _text(result)

    assert _utf8_bytes(text) == 7_280
    assert _strict_json(text)["_transport_truncated"] is True


def test_json_transport_rechecks_final_metadata_at_the_utf8_boundary():
    payload = {"k" * 6_792: "電" * 2_700}
    first_compact = bot_mcp._compact_json_value(payload, list_limit=20, str_limit=400)
    first_text = json.dumps(first_compact, ensure_ascii=False, allow_nan=False)
    first_compact["_transport_truncated"] = True
    marked_text = json.dumps(first_compact, ensure_ascii=False, allow_nan=False)
    result = bot_mcp._json(payload)
    text = _text(result)

    assert _utf8_bytes(first_text) == 8_000
    assert _utf8_bytes(marked_text) == 8_030
    assert _utf8_bytes(text) == 7_550
    assert _strict_json(text)["_transport_truncated"] is True


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


def test_json_transport_catches_ordinary_serialization_exceptions():
    class ExplosiveStringification:
        def __str__(self):
            raise RuntimeError("do not leak this")

    result = bot_mcp._json({"value": ExplosiveStringification()})

    assert _strict_json(_text(result)) == {"error": "MCP_RESPONSE_NOT_JSON"}
    assert result["is_error"] is True


@pytest.mark.parametrize("signal", (KeyboardInterrupt, SystemExit, GeneratorExit, asyncio.CancelledError))
def test_json_transport_propagates_base_exception_subclasses(signal):
    class TerminatingStringification:
        def __str__(self):
            raise signal()

    with pytest.raises(signal):
        bot_mcp._json({"value": TerminatingStringification()})


def test_json_transport_propagates_termination_from_compaction_path():
    class ChangesDuringSerialization:
        calls = 0

        def __str__(self):
            type(self).calls += 1
            if type(self).calls == 1:
                return "x" * 9_000
            raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        bot_mcp._json({"value": ChangesDuringSerialization()})


@pytest.mark.parametrize("root", (["x" * 1_000] * 50, tuple(["x" * 1_000] * 50), "x" * 9_000))
def test_json_transport_refuses_oversized_non_object_roots(root):
    result = bot_mcp._json(root)

    assert _strict_json(_text(result)) == {"error": "MCP_RESPONSE_TOO_LARGE"}
    assert result["is_error"] is True


def test_real_decorated_handler_sets_sdk_wire_error_once(tmp_path, monkeypatch):
    handler_calls = 0
    original_handler = bot_mcp.get_regime.handler
    reads = _count_vendored_read(tmp_path, monkeypatch, "data/regime/latest.json", {
        "quad": "Q1", "sector_rs": [float("nan")],
    })
    _isolate_regime_enrichment(monkeypatch)

    async def counted_handler(args):
        nonlocal handler_calls
        handler_calls += 1
        return await original_handler(args)

    monkeypatch.setattr(bot_mcp.get_regime, "handler", counted_handler)
    wire = asyncio.run(_sdk_wire_tool_call(bot_mcp.build_server(), "get_regime", {}))

    assert handler_calls == reads["count"] == 1
    assert wire["isError"] is True
    assert _strict_json(wire["content"][0]["text"]) == {"error": "MCP_RESPONSE_NOT_JSON"}

def test_real_decorated_handler_preserves_multilingual_success_through_sdk(tmp_path, monkeypatch):
    handler_calls = 0
    original_handler = bot_mcp.get_regime.handler
    reads = _count_vendored_read(tmp_path, monkeypatch, "data/regime/latest.json", {
        "quad": "Q1", "cycle_tag": "電力", "growth_score": 0, "liquidity_overlay": False,
        "sector_rs": ["🚀"], "data_quality": None,
    })
    _isolate_regime_enrichment(monkeypatch)

    async def counted_handler(args):
        nonlocal handler_calls
        handler_calls += 1
        return await original_handler(args)

    monkeypatch.setattr(bot_mcp.get_regime, "handler", counted_handler)
    wire = asyncio.run(_sdk_wire_tool_call(bot_mcp.build_server(), "get_regime", {}))
    parsed = _strict_json(wire["content"][0]["text"])

    assert handler_calls == reads["count"] == 1
    assert wire.get("isError", False) is False
    assert _utf8_bytes(wire["content"][0]["text"]) <= 8_000
    assert parsed["cycle_tag"] == "電力" and parsed["growth_score"] == 0
    assert parsed["liquidity_overlay"] is False

def test_real_intel_hub_handler_compacts_multilingual_fixture_through_sdk(tmp_path, monkeypatch):
    handler_calls = 0
    original_handler = bot_mcp.get_intel_hub.handler
    reads = _count_vendored_read(tmp_path, monkeypatch, "site/intel_hub/hub.json", {
        "as_of": "2026-09-06",
        "macro_context": {"label": "電力", "confidence": 0, "risk_off": False, "note": None},
        "desks": {"research": {"active": True}},
        "counts": {"actionable": 0, "complete": False, "pending": None},
        "n_actionable": 0,
        "command": [
            {
                "ticker": f"T{index:02d}", "name": "電" * 160,
                "composite_conviction": 0, "lean": False, "n_confirm": 0,
                "flags": ["電力", "🚀"], "read": "多語研究",
                "peers": ["PWR"], "sectors": ["utilities"], "falsifier": None,
            }
            for index in range(24)
        ],
        "divergence_alerts": {"early_edge": []}, "sector_heat": [], "how_to_use": "研究用",
    })

    async def counted_handler(args):
        nonlocal handler_calls
        handler_calls += 1
        return await original_handler(args)

    monkeypatch.setattr(bot_mcp.get_intel_hub, "handler", counted_handler)
    wire = asyncio.run(_sdk_wire_tool_call(bot_mcp.build_server(), "get_intel_hub", {"top": 24}))
    text = wire["content"][0]["text"]
    parsed = _strict_json(text)

    assert handler_calls == reads["count"] == 1
    assert wire.get("isError", False) is False
    assert _utf8_bytes(text) <= 8_000
    assert parsed["_transport_truncated"] is True
    assert parsed["command"] and parsed["command"][0]["ticker"] == "T00"
    assert parsed["command"][0]["composite_conviction"] == 0
    assert parsed["command"][0]["lean"] is False
    assert parsed["command"][0]["falsifier"] is None
    assert "電" in parsed["command"][0]["name"] and "🚀" in parsed["command"][0]["flags"]


@pytest.mark.parametrize("invalid", (float("nan"), "\ud800"))
def test_real_handler_rejects_invalid_data_before_compaction_can_omit_it(tmp_path, monkeypatch, invalid):
    handler_calls = 0
    original_handler = bot_mcp.get_themes.handler
    retained_control = {"id": "late-control", "name": None, "category": False, "n_members": 0}
    baskets = [
        {"id": f"basket-{index}", "name": "電" * 400, "category": "research", "n_members": index}
        for index in range(24)
    ] + [retained_control, {"id": "invalid-late", "perf": {"20d": {"rel": invalid}}}]
    # _write_vendored escapes a lone surrogate so the fixture file is valid UTF-8;
    # rejection must occur in the actual handler's transport serialization.
    reads = _count_vendored_read(tmp_path, monkeypatch, "site/basketdata/baskets.json", {
        "as_of": "2026-09-05", "baskets": baskets,
    })

    async def counted_handler(args):
        nonlocal handler_calls
        handler_calls += 1
        return await original_handler(args)

    monkeypatch.setattr(bot_mcp.get_themes, "handler", counted_handler)
    wire = asyncio.run(_sdk_wire_tool_call(bot_mcp.build_server(), "get_themes", {}))

    assert handler_calls == reads["count"] == 1
    assert wire["isError"] is True
    assert _strict_json(wire["content"][0]["text"]) == {"error": "MCP_RESPONSE_NOT_JSON"}
    assert retained_control == {"id": "late-control", "name": None, "category": False, "n_members": 0}

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


# --- D2 boundary freshness (news estate 2026-10-31) -------------------------------------------
def _write_vendored(root, rel, payload):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload))


_NEWS_REC = {"n_recent": 3, "sentiment_lean": "pos", "n_pos": 2, "n_neg": 0,
             "baskets": ["ai"], "sectors": ["tech"], "is_mag7": True,
             "top": [{"title": "t", "source": "Reuters", "url": "u", "summary": "s",
                      "sentiment": "pos", "date": "2026-10-30",
                      "item_id": "massive:reuters.com:abc123",
                      "published_utc": "2026-10-30T14:05:00+00:00"}]}


def test_get_news_carries_freshness_and_evidence_grade(tmp_path, monkeypatch):
    """T5: a found ticker carries the vendored file's clocks; existing keys stay unchanged."""
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_vendored(tmp_path, "site/news/by_ticker.json", {
        "schema": "news_flow.v1", "is_context_only": True, "asof": "2026-10-31",
        "source_asof": "2026-10-30T22:00:00+00:00", "source_asof_basis": "financial_news.fetched_at",
        "retained_from_previous_build": True, "retained_reason": "candidate_darker_than_existing",
        "tickers": {"NVDA": _NEWS_REC}})
    out = json.loads(_text(asyncio.run(bot_mcp.get_news.handler({"ticker": "nvda"}))))
    assert {"ticker", "news", "note"} <= set(out)
    assert out["ticker"] == "NVDA" and out["news"]["n_recent"] == 3
    assert out["evidence_grade"] == "vendored_snapshot"
    assert out["freshness"] == {
        "asof": "2026-10-31", "source_asof": "2026-10-30T22:00:00+00:00",
        "retained_from_previous_build": True, "generated_utc": None,
        "basis": "vendored_macro_file", "source_file": "site/news/by_ticker.json"}
    assert "missing_reason" not in out and "fallback" not in out
    # a pre-D2 producer file (no source clock) reports null, never an invented clock
    _write_vendored(tmp_path, "site/news/by_ticker.json", {
        "schema": "news_flow.v1", "asof": "2026-10-29", "tickers": {"NVDA": _NEWS_REC}})
    old = json.loads(_text(asyncio.run(bot_mcp.get_news.handler({"ticker": "NVDA"}))))
    assert old["freshness"]["asof"] == "2026-10-29"
    assert old["freshness"]["source_asof"] is None
    assert old["freshness"]["retained_from_previous_build"] is None
    # an absent ticker keeps the existing plain-text contract
    assert "no news-flow signal for ZZZZ" in _text(
        asyncio.run(bot_mcp.get_news.handler({"ticker": "ZZZZ"})))


def test_get_intelligence_labels_primary_and_legacy_fallback(tmp_path, monkeypatch):
    """T6: the unified read is graded vendored_snapshot; the standalone-feed composition is
    labelled legacy_fallback with its reason and the news file's clocks."""
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_vendored(tmp_path, "site/intelligence/by_ticker.json", {
        "schema": "intelligence.v1", "is_context_only": True, "as_of": "2026-10-31",
        "generated_utc": "2026-10-31T06:10:00+00:00",
        "tickers": {"NVDA": {"ticker": "NVDA", "news": _NEWS_REC, "alt": None,
                             "has_news": True, "has_alt": False}}})
    _write_vendored(tmp_path, "site/news/by_ticker.json", {
        "schema": "news_flow.v1", "asof": "2026-10-31",
        "source_asof": "2026-10-31T05:00:00+00:00", "retained_from_previous_build": False,
        "tickers": {"AMD": _NEWS_REC}})
    _write_vendored(tmp_path, "site/altdata/mastermind.json", {
        "as_of": "2026-10-30", "signals": [{"ticker": "AMD", "signal_score": 61}]})

    primary = json.loads(_text(asyncio.run(bot_mcp.get_intelligence.handler({"ticker": "NVDA"}))))
    assert primary["has_news"] is True and "note" in primary
    assert primary["evidence_grade"] == "vendored_snapshot"
    assert primary["freshness"]["asof"] == "2026-10-31"
    assert primary["freshness"]["generated_utc"] == "2026-10-31T06:10:00+00:00"
    assert primary["freshness"]["source_file"] == "site/intelligence/by_ticker.json"
    assert primary["freshness"]["basis"] == "vendored_macro_file"
    assert "missing_reason" not in primary and "fallback" not in primary

    legacy = json.loads(_text(asyncio.run(bot_mcp.get_intelligence.handler({"ticker": "AMD"}))))
    assert legacy["has_news"] is True and legacy["has_alt"] is True
    assert legacy["missing_reason"] == "ticker_absent_in_vendored_file"
    assert legacy["fallback"] == "standalone_news_and_altdata_feeds"
    assert legacy["evidence_grade"] == "legacy_fallback"
    assert legacy["freshness"]["source_file"] == "site/news/by_ticker.json"
    assert legacy["freshness"]["source_asof"] == "2026-10-31T05:00:00+00:00"
    assert legacy["freshness"]["retained_from_previous_build"] is False
    assert legacy["alt_freshness"]["asof"] == "2026-10-30"


def test_freshness_survives_transport_compaction(tmp_path, monkeypatch):
    """T6b: the 8k transport budget never drops the freshness block or the grade."""
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    wide = dict(_NEWS_REC, top=[dict(_NEWS_REC["top"][0], summary="x" * 3000) for _ in range(40)])
    _write_vendored(tmp_path, "site/news/by_ticker.json", {
        "asof": "2026-10-31", "source_asof": "2026-10-31T05:00:00+00:00",
        "tickers": {"NVDA": wide}})
    out = json.loads(_text(asyncio.run(bot_mcp.get_news.handler({"ticker": "NVDA"}))))
    assert out["_transport_truncated"] is True
    assert out["freshness"]["source_asof"] == "2026-10-31T05:00:00+00:00"
    assert out["evidence_grade"] == "vendored_snapshot"
    tiny = json.loads(_text(bot_mcp._json({"freshness": {"asof": "2026-10-31"}, "evidence_grade": "g",
                                            **{f"k{i}": {"v": "y" * 200} for i in range(400)}})))
    assert tiny["freshness"] == {"asof": "2026-10-31"} and tiny["evidence_grade"] == "g"


_NEWS_ORIGIN = {
    "source_asof": "2026-10-29T21:00:00+00:00",
    "source_asof_basis": "financial_news.fetched_at",
    "retained_from_previous_build": True,
    "retained_reason": "candidate_darker_than_existing",
}


def test_unified_intelligence_keeps_news_origin_separate(tmp_path, monkeypatch):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_vendored(tmp_path, "site/intelligence/by_ticker.json", {
        "as_of": "2026-11-08", "generated_utc": "2026-11-08T05:00:00+00:00",
        "news_freshness": _NEWS_ORIGIN,
        "tickers": {"NVDA": {"news": _NEWS_REC, "has_news": True, "alt": None}}})
    _write_vendored(tmp_path, "site/news/by_ticker.json", {
        "source_asof": "2026-11-08T06:00:00+00:00", "retained_from_previous_build": False,
        "tickers": {"NVDA": dict(_NEWS_REC, n_recent=99)}})
    out = json.loads(_text(asyncio.run(bot_mcp.get_intelligence.handler({"ticker": "NVDA"}))))
    assert out["news_freshness"] == _NEWS_ORIGIN
    assert out["freshness"]["asof"] == "2026-11-08"
    assert out["freshness"]["source_asof"] is None
    assert out["freshness"]["source_file"] == "site/intelligence/by_ticker.json"
    assert out["news"] == _NEWS_REC
    assert out["evidence_grade"] == "vendored_snapshot"


@pytest.mark.parametrize("metadata", [None, [], "bad", {}, {
    "source_asof": 12, "source_asof_basis": [], "retained_from_previous_build": "false",
    "retained_reason": {"reason": "old"}}, {
    "source_asof": " ", "source_asof_basis": "", "retained_from_previous_build": 0}])
def test_unified_news_unknown_metadata_never_borrows_newer_standalone(tmp_path, monkeypatch, metadata):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_vendored(tmp_path, "site/intelligence/by_ticker.json", {
        "as_of": "2026-11-08", "news_freshness": metadata,
        "tickers": {"NVDA": {"news": _NEWS_REC, "has_news": True}}})
    _write_vendored(tmp_path, "site/news/by_ticker.json", {
        **_NEWS_ORIGIN, "retained_from_previous_build": False, "tickers": {"NVDA": _NEWS_REC}})
    out = json.loads(_text(asyncio.run(bot_mcp.get_intelligence.handler({"ticker": "NVDA"}))))
    assert out["news_freshness"] == {
        "source_asof": None, "source_asof_basis": None,
        "retained_from_previous_build": None, "retained_reason": None}
    assert out["news"] == _NEWS_REC


@pytest.mark.parametrize("mode", ["compact", "scalar_fallback"])
def test_unified_news_origin_survives_actual_tool_transport(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    news = dict(_NEWS_REC, top=[{"title": "x" * 3000} for _ in range(40)])
    if mode == "scalar_fallback":
        news.update({f"wide_{i}": {"nested": "x" * 500} for i in range(250)})
    _write_vendored(tmp_path, "site/intelligence/by_ticker.json", {
        "as_of": "2026-11-08", "news_freshness": _NEWS_ORIGIN,
        "tickers": {"NVDA": {"news": news, "has_news": True}}})
    text = _text(asyncio.run(bot_mcp.get_intelligence.handler({"ticker": "NVDA"})))
    out = json.loads(text)
    assert out["_transport_truncated"] is True
    assert len(text) <= 8000
    assert out["news_freshness"] == _NEWS_ORIGIN
    assert out["freshness"]["asof"] == "2026-11-08"
    assert out["evidence_grade"] == "vendored_snapshot"
    if mode == "scalar_fallback":
        assert "news" not in out


@pytest.mark.parametrize("shape", ["structured", "nested_fallback", "scalar_prefix"])
def test_json_transport_preserves_late_source_qualification(shape):
    qualification = {
        "freshness": {"asof": "2026-11-08", "source_asof": None, "basis": "vendored_macro_file"},
        "alt_freshness": {"asof": "2026-11-07", "source_asof": "2026-11-06T05:00:00Z"},
        "news_freshness": dict(_NEWS_ORIGIN),
        "evidence_grade": "legacy_fallback",
        "missing_reason": "unified_artifact_absent",
        "fallback": "standalone_news_and_altdata_feeds",
        "read_status": "partial",
        "failed_sources": [f"source_{i}" for i in range(30)],
        "degraded_sources": ["lenses", "intake"],
        "note": "Evidence remains incomplete. " * 25 + "Missing fields are unknown.",
        "live": False,
        "status": "available_with_gaps",
        "portfolio_id": "fixture",
        "active": False,
        "lifecycle": None,
    }
    if shape == "structured":
        bulk = {"rows": [{"detail": "電" * 1000} for _ in range(100)]}
    elif shape == "nested_fallback":
        bulk = {f"key_{i}": {"value": "x" * 500} for i in range(400)}
    else:
        bulk = {f"key_{i}": i for i in range(1500)}
    original = {**bulk, **qualification}
    before = json.dumps(original, ensure_ascii=False)
    result = bot_mcp._json(original)
    text = _text(result)
    out = _strict_json(text)

    assert result.get("is_error") is not True
    assert out["_transport_truncated"] is True
    assert _utf8_bytes(text) <= 8000
    assert {key: out[key] for key in qualification} == qualification
    assert json.dumps(original, ensure_ascii=False) == before
    assert bot_mcp._json(original) == result
    if shape == "scalar_prefix":
        assert out["key_0"] == 0


def test_json_transport_retains_nested_lens_restrictions_with_its_values():
    lenses = {
        "confluence": 0,
        "data_degraded": True,
        "stockdata_present": False,
        "n_scored": 0,
        "thin_evidence": True,
        "size_authority": "blocked",
        "vetoes": [f"veto_{i}" for i in range(30)],
        "note": "Evidence is thin. " * 30 + "Do not derive size from this result.",
    }
    result = bot_mcp._json({
        "rows": [{"detail": "x" * 1000} for _ in range(100)],
        "lenses": lenses,
    })
    out = _strict_json(_text(result))

    assert out["_transport_truncated"] is True
    assert out["lenses"] == lenses
    assert _utf8_bytes(_text(result)) <= 8000


@pytest.mark.parametrize("outcome_key", ["proposal_queued", "paper_saved"])
def test_json_transport_keeps_unknown_write_outcome_and_retry_fence(outcome_key):
    fence = {
        "write_status": "unknown",
        outcome_key: None,
        "error": "fixture_outcome_unknown",
        "note": "Canonical outcome is unknown. " * 20 + "Reconcile it before considering retry.",
    }
    result = bot_mcp._json({**{f"k{i}": i for i in range(1500)}, **fence})
    out = _strict_json(_text(result))

    assert result.get("is_error") is not True
    assert out["_transport_truncated"] is True
    assert {key: out[key] for key in fence} == fence
    assert _utf8_bytes(_text(result)) <= 8000


def test_json_transport_preserves_gate_unknowns_after_wide_scalar_fallback():
    gate = {
        "read_status": "unavailable",
        "gate_status": "unavailable",
        "failed_sources": ["decision_matrix"],
        "error": "advisor_gate_unavailable",
        "passed": None,
        "size_authority": None,
        "vetoes": None,
        "reason": "Preliminary gate unavailable; engine evidence did not complete.",
    }
    result = bot_mcp._json({**{f"k{i}": i for i in range(1500)}, **gate})
    out = _strict_json(_text(result))

    assert {key: out[key] for key in gate} == gate
    assert out["_transport_truncated"] is True
    assert _utf8_bytes(_text(result)) <= 8000


@pytest.mark.parametrize("qualification", [
    {"freshness": {"source_file": "源" * 3000}},
    {"news_freshness": {"source_asof": None, "retained_reason": "x" * 9000}},
    {"read_status": "partial", "failed_sources": ["source_" + "x" * 500] * 30},
    {"write_status": "unknown", "paper_saved": None, "note": "x" * 9000},
])
def test_json_transport_errors_if_complete_qualification_cannot_fit(qualification):
    result = bot_mcp._json({"value": 0, **qualification})

    assert result["is_error"] is True
    assert _strict_json(_text(result)) == {"error": "MCP_RESPONSE_TOO_LARGE"}
    assert _utf8_bytes(_text(result)) <= 8000


def test_json_transport_does_not_replace_only_unfit_entry_with_metadata():
    result = bot_mcp._json({"k" * 9000: {"nested": "x" * 500}})

    assert result["is_error"] is True
    assert _strict_json(_text(result)) == {"error": "MCP_RESPONSE_TOO_LARGE"}


# Canonical producer -> real SDK transport: the fixture is the observation from
# Macro's 2026-11-13 source audit, not an invented market data scenario.
def _fragility_fixture():
    return json.loads((_ROOT / "tests/fixtures/market_fragility_observation.json").read_text())


def _freeze_fragility_read(monkeypatch):
    from datetime import datetime, timezone
    from brain import market_fragility_context
    original = market_fragility_context.project_market_fragility
    frozen = datetime(2026, 11, 13, 17, tzinfo=timezone.utc)
    monkeypatch.setattr(market_fragility_context, "project_market_fragility",
                        lambda value: original(value, now=frozen))


def test_fragility_producer_observation_reaches_real_sdk_wire(tmp_path, monkeypatch):
    reads = _count_vendored_read(tmp_path, monkeypatch, "data/regime/latest.json", {
        "date": "2026-11-12", "quad": "Q2", "sector_rs": [],
        "market_fragility": _fragility_fixture(),
    })
    _isolate_regime_enrichment(monkeypatch)
    _freeze_fragility_read(monkeypatch)
    wire = asyncio.run(_sdk_wire_tool_call(bot_mcp.build_server(), "get_regime", {}))
    result = _strict_json(wire["content"][0]["text"])
    assert wire.get("isError", False) is False
    assert reads["count"] == 1
    assert result["quad"] == "Q2"
    fragility = result["market_fragility"]
    assert fragility["state"] == "amplifying"
    assert fragility["history"]["observed_sessions"] == 15
    assert fragility["history"]["unknown_sessions"] == 5
    assert fragility["authority"]["position_sizing"] is False
    assert fragility["predictive_validation"] == "not_established"
    assert _utf8_bytes(wire["content"][0]["text"]) <= 8_000


def test_bad_fragility_does_not_hide_healthy_core_regime(tmp_path, monkeypatch):
    bad = _fragility_fixture()
    bad["authority"]["trade_execution"] = True
    _count_vendored_read(tmp_path, monkeypatch, "data/regime/latest.json", {
        "quad": "Q2", "sector_rs": [], "market_fragility": bad,
    })
    _isolate_regime_enrichment(monkeypatch)
    _freeze_fragility_read(monkeypatch)
    wire = asyncio.run(_sdk_wire_tool_call(bot_mcp.build_server(), "get_regime", {}))
    result = _strict_json(wire["content"][0]["text"])
    assert result["quad"] == "Q2"
    assert result["market_fragility"]["state"] == "unknown"
    assert result["market_fragility"]["reason"] == "unexpected_authority"


def test_transport_compaction_keeps_fragility_qualifiers_whole():
    from datetime import datetime, timezone
    from brain.market_fragility_context import project_market_fragility
    fragility = project_market_fragility(_fragility_fixture(), now=datetime(2026, 11, 13, 17, tzinfo=timezone.utc))
    result = bot_mcp._json({"market_fragility": fragility, "other_rows": ["x" * 200] * 100})
    parsed = _strict_json(_text(result))
    assert not result.get("is_error")
    assert parsed["market_fragility"] == fragility
