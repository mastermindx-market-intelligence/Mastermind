"""News/alt-data/unified Brain reads must distinguish absence from unreadable evidence."""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types


def _load_bot_mcp_with_fake_sdk(monkeypatch):
    fake = types.ModuleType("claude_agent_sdk")

    class ToolWrap:
        def __init__(self, name, handler):
            self.name = name
            self.handler = handler

    def tool(name, _description, _schema):
        def deco(fn):
            return ToolWrap(name, fn)
        return deco

    fake.tool = tool
    fake.create_sdk_mcp_server = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    sys.modules.pop("brain.bot_mcp", None)
    return importlib.import_module("brain.bot_mcp")


def _text(result: dict) -> str:
    return result["content"][0]["text"]


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def _break(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ broken json")


def test_genuine_absence_keeps_existing_no_signal_messages(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")

    assert _text(asyncio.run(bot_mcp.get_news.handler({"ticker": "ZZZZ"}))) == (
        "no news-flow signal for ZZZZ — not covered by the macro news surface."
    )
    assert _text(asyncio.run(bot_mcp.get_altdata.handler({"ticker": "ZZZZ"}))) == (
        "no alt-data signal for ZZZZ — not flagged by any political/insider/contract channel."
    )
    assert _text(asyncio.run(bot_mcp.get_intelligence.handler({"ticker": "ZZZZ"}))) == (
        "no news or alt-data intelligence for ZZZZ."
    )


def test_news_corrupt_source_is_unavailable_not_no_coverage(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "news" / "by_ticker.json")

    raw = _text(asyncio.run(bot_mcp.get_news.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "ticker_news_unavailable"
    assert payload["failed_sources"] == ["news"]
    assert payload["news"] is None
    assert "not covered" not in raw and "broken json" not in raw


def test_news_bad_primary_uses_healthy_fallback_but_stays_partial(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "news" / "by_ticker.json")
    _write_json(
        vendor / "data" / "news" / "by_ticker.json",
        {"tickers": {"AAPL": {"headline_count": 4, "sentiment": "positive"}}},
    )

    payload = json.loads(_text(asyncio.run(bot_mcp.get_news.handler({"ticker": "AAPL"}))))
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["news"]
    assert payload["news"]["headline_count"] == 4


def test_altdata_flow_failure_preserves_healthy_graph_as_partial(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "altdata" / "by_ticker.json")
    _write_json(
        vendor / "site" / "altdata" / "latent.json",
        {"watch": [{"ticker": "AAPL", "themes": [{"en": "AI power"}], "note": "graph"}], "mismatches": []},
    )

    payload = json.loads(_text(asyncio.run(bot_mcp.get_altdata.handler({"ticker": "AAPL"}))))
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["altdata_flow"]
    assert payload["flow"] is None
    assert payload["latent_graph"]["themes"] == ["AI power"]


def test_altdata_graph_failure_preserves_healthy_flow_as_partial(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(
        vendor / "site" / "altdata" / "by_ticker.json",
        {"tickers": {"AAPL": {"signal_score": 77}}},
    )
    _break(vendor / "site" / "altdata" / "latent.json")

    payload = json.loads(_text(asyncio.run(bot_mcp.get_altdata.handler({"ticker": "AAPL"}))))
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["altdata_graph"]
    assert payload["flow"]["signal_score"] == 77
    assert payload["latent_graph"] is None


def test_altdata_all_source_failures_are_unavailable(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "altdata" / "by_ticker.json")
    _break(vendor / "site" / "altdata" / "latent.json")

    raw = _text(asyncio.run(bot_mcp.get_altdata.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "ticker_altdata_unavailable"
    assert payload["failed_sources"] == ["altdata_flow", "altdata_graph"]
    assert "broken json" not in raw


def test_unified_intelligence_failure_can_fall_back_to_news_as_partial(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "intelligence" / "by_ticker.json")
    _write_json(
        vendor / "site" / "news" / "by_ticker.json",
        {"tickers": {"AAPL": {"headline_count": 2}}},
    )

    payload = json.loads(_text(asyncio.run(bot_mcp.get_intelligence.handler({"ticker": "AAPL"}))))
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["unified_intelligence"]
    assert payload["news"]["headline_count"] == 2
    assert payload["alt"] is None


def test_news_fallback_failure_cannot_become_no_intelligence(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "news" / "by_ticker.json")

    raw = _text(asyncio.run(bot_mcp.get_intelligence.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["news"]
    assert "no news or alt-data intelligence" not in raw


def test_all_unified_intelligence_sources_failed_is_unavailable(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "intelligence" / "by_ticker.json")
    _break(vendor / "site" / "news" / "by_ticker.json")
    _break(vendor / "site" / "altdata" / "mastermind.json")

    raw = _text(asyncio.run(bot_mcp.get_intelligence.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "ticker_intelligence_unavailable"
    assert payload["failed_sources"] == ["unified_intelligence", "news", "altdata"]
    assert "broken json" not in raw
