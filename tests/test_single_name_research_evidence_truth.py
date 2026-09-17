"""Single-name Brain research reads must distinguish coverage absence from failed evidence."""
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
    path.write_text("{ broken secret token=do-not-return")


def test_genuine_coverage_absence_keeps_existing_messages(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")

    assert _text(asyncio.run(bot_mcp.get_fundamentals.handler({"ticker": "ZZZZ"}))) == (
        "no stock file for ZZZZ (covered: S&P 1500 + crypto; ships in the Pages artifact)."
    )
    assert _text(asyncio.run(bot_mcp.get_options.handler({"ticker": "ZZZZ"}))) == (
        "no options/GEX file for ZZZZ (only the ~liquid options universe is covered)."
    )
    assert _text(asyncio.run(bot_mcp.get_anticipation.handler({"ticker": "ZZZZ"}))) == (
        "no anticipation file for ZZZZ (only the curated forward-signal watchlist is covered)."
    )


def test_corrupt_fundamentals_are_unavailable_and_secret_safe(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "stockdata" / "AAPL.json")

    raw = _text(asyncio.run(bot_mcp.get_fundamentals.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload == {
        "ticker": "AAPL",
        "read_status": "unavailable",
        "error": "ticker_fundamentals_unavailable",
        "failed_sources": ["fundamentals"],
    }
    assert "secret" not in raw and "do-not-return" not in raw


def test_wrong_fundamental_section_is_partial_and_keeps_healthy_sections(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "stockdata" / "AAPL.json", {
        "name": "Apple",
        "sector": "Technology",
        "asof": "2026-09-17",
        "valuation": ["wrong-shape"],
        "financials": {"roe": 0.31, "net_margin": 0.25},
        "conviction": {"score": 81, "band": "high"},
    })

    payload = json.loads(_text(asyncio.run(bot_mcp.get_fundamentals.handler({"ticker": "AAPL"}))))
    assert payload["name"] == "Apple"
    assert payload["valuation"] is None
    assert payload["financials"]["roe"] == 0.31
    assert payload["conviction"]["score"] == 81
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["fundamentals"]


def test_corrupt_options_are_unavailable_not_uncovered(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "gex" / "AAPL.json")

    raw = _text(asyncio.run(bot_mcp.get_options.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "ticker_options_unavailable"
    assert payload["failed_sources"] == ["options"]
    assert "liquid options universe" not in raw


def test_wrong_options_meta_is_partial_and_keeps_healthy_summary(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "gex" / "AAPL.json", {
        "meta": "wrong-shape",
        "summary": {"spot": 250.0, "regime": "long"},
        "expected_move": {"daily_pct": 1.3},
        "vol_hole": {"state": "compressed"},
    })

    payload = json.loads(_text(asyncio.run(bot_mcp.get_options.handler({"ticker": "AAPL"}))))
    assert payload["asof"] is None
    assert payload["summary"]["spot"] == 250.0
    assert payload["expected_move"]["daily_pct"] == 1.3
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["options"]


def test_corrupt_anticipation_is_unavailable_not_uncovered(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "anticipationdata" / "AAPL.json")

    raw = _text(asyncio.run(bot_mcp.get_anticipation.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "ticker_anticipation_unavailable"
    assert payload["failed_sources"] == ["anticipation"]
    assert "curated forward-signal watchlist" not in raw


def test_empty_existing_anticipation_is_failed_evidence(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "anticipationdata" / "AAPL.json", {})

    payload = json.loads(_text(asyncio.run(bot_mcp.get_anticipation.handler({"ticker": "AAPL"}))))
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "ticker_anticipation_unavailable"


def test_healthy_single_name_research_keeps_existing_shapes(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "stockdata" / "AAPL.json", {
        "name": "Apple", "sector": "Technology", "asof": "2026-09-17",
        "valuation": {"forward_pe": 30.0}, "financials": {"roe": 0.31},
    })
    _write_json(vendor / "site" / "gex" / "AAPL.json", {
        "meta": {"asof": "2026-09-17"}, "summary": {"spot": 250.0},
        "expected_move": {"daily_pct": 1.2}, "vol_hole": {"state": "normal"},
    })
    _write_json(vendor / "site" / "anticipationdata" / "AAPL.json", {
        "name": "Apple", "group": "mega-cap", "as_of": "2026-09-17",
        "anticipation_index": 0.6, "direction_trust": "high",
    })

    fundamentals = json.loads(_text(asyncio.run(bot_mcp.get_fundamentals.handler({"ticker": "AAPL"}))))
    options = json.loads(_text(asyncio.run(bot_mcp.get_options.handler({"ticker": "AAPL"}))))
    anticipation = json.loads(_text(asyncio.run(bot_mcp.get_anticipation.handler({"ticker": "AAPL"}))))
    assert fundamentals["valuation"]["forward_pe"] == 30.0 and "read_status" not in fundamentals
    assert options["summary"]["spot"] == 250.0 and "read_status" not in options
    assert anticipation["anticipation_index"] == 0.6 and "read_status" not in anticipation
