"""Ticker deep-dive evidence must distinguish absence from unreadable sources."""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types
from pathlib import Path


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


def _wire_lenses(monkeypatch, *, fail: bool = False):
    from portfolio import lenses

    if fail:
        def explode(*_args, **_kwargs):
            raise RuntimeError("secret /Users/private/lenses token=do-not-return")
        monkeypatch.setattr(lenses, "decision_matrix", explode)
    else:
        monkeypatch.setattr(lenses, "decision_matrix", lambda *_args, **_kwargs: {})
        monkeypatch.setattr(
            lenses,
            "synthesize",
            lambda _matrix: {"divergences": [], "confluence": [], "vetoes": []},
        )


def _wire_intake(monkeypatch, rows=None, *, fail: bool = False):
    from brain import intake

    if fail:
        def explode(*_args, **_kwargs):
            raise RuntimeError("secret /Users/private/intake api_key=do-not-return")
        monkeypatch.setattr(intake, "queue", explode)
    else:
        monkeypatch.setattr(intake, "queue", lambda _limit=60: list(rows or []))


def _write_intel(root: Path, ticker: str = "AAPL") -> None:
    path = root / "site" / "intelligence" / "by_ticker.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tickers": {ticker: {"ticker": ticker, "brain_summary": "healthy"}}}))


def test_genuine_absence_keeps_existing_not_flagged_message(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")
    _wire_lenses(monkeypatch)
    _wire_intake(monkeypatch)

    text = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "ZZZZ"})))
    assert text == "no per-ticker intelligence for ZZZZ — not flagged by any dashboard engine."


def test_lens_failure_is_partial_secret_safe_and_keeps_healthy_evidence(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_intel(vendor)
    _wire_lenses(monkeypatch, fail=True)
    _wire_intake(monkeypatch, [{"ticker": "AAPL", "score": 8, "sources": ["briefing"]}])

    raw = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["lenses"]
    assert payload["intelligence"]["brain_summary"] == "healthy"
    assert payload["intake"]["ticker"] == "AAPL"
    assert payload["lenses"] == {
        "read_status": "unavailable",
        "error": "ticker_package_lenses_unavailable",
    }
    assert "secret" not in raw and "/Users/private" not in raw and "do-not-return" not in raw


def test_intake_failure_cannot_be_reported_as_not_flagged(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")
    _wire_lenses(monkeypatch)
    _wire_intake(monkeypatch, fail=True)

    raw = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "ZZZZ"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intake"]
    assert payload["intake"] is None
    assert "not flagged by any dashboard engine" not in raw
    assert "secret" not in raw and "api_key" not in raw


def test_corrupt_intelligence_store_is_partial_not_no_coverage(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    path = vendor / "site" / "intelligence" / "by_ticker.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ definitely not json")
    _wire_lenses(monkeypatch)
    _wire_intake(monkeypatch)

    raw = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intelligence"]
    assert payload["intelligence"] is None
    assert "not flagged by any dashboard engine" not in raw


def test_all_ticker_package_sources_failed_is_unavailable(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    path = vendor / "site" / "intelligence" / "by_ticker.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ definitely not json")
    _wire_lenses(monkeypatch, fail=True)
    _wire_intake(monkeypatch, fail=True)

    raw = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "ticker_package_unavailable"
    assert payload["failed_sources"] == ["intelligence", "lenses", "intake"]
    assert payload["intelligence"] is None and payload["intake"] is None
    assert "secret" not in raw and "/Users/private" not in raw and "do-not-return" not in raw


def test_wrong_shape_intelligence_store_is_partial_not_exception(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    path = vendor / "site" / "intelligence" / "by_ticker.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]")
    _wire_lenses(monkeypatch)
    _wire_intake(monkeypatch)

    raw = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intelligence"]
    assert payload["intelligence"] is None


def test_corrupt_primary_can_use_healthy_fallback_but_stays_partial(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    primary = vendor / "site" / "intelligence" / "by_ticker.json"
    primary.parent.mkdir(parents=True, exist_ok=True)
    primary.write_text("{ broken")
    fallback = vendor / "data" / "intelligence" / "by_ticker.json"
    fallback.parent.mkdir(parents=True, exist_ok=True)
    fallback.write_text(json.dumps({"tickers": {"AAPL": {"brain_summary": "fallback-ok"}}}))
    _wire_lenses(monkeypatch)
    _wire_intake(monkeypatch)

    raw = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intelligence"]
    assert payload["intelligence"]["brain_summary"] == "fallback-ok"
