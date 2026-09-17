"""The Brain regime tool must preserve core and optional-context availability truth."""
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


def _write_regime(vendor, payload=None):
    path = vendor / "data" / "regime" / "latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = payload or {
        "date": "2026-09-17",
        "quad": "Q1",
        "quad_name": "Goldilocks",
        "growth_score": 1.2,
        "inflation_score": -0.4,
        "liquidity_overlay": "supportive",
        "cycle_tag": "mid",
        "sector_rs": [{"ticker": "XLK"}],
    }
    path.write_text(json.dumps(payload))
    return path


def _wire_optional_context(monkeypatch, *, market_fail=False, decision_fail=False):
    from brain import decision_context, pm_conviction

    if market_fail:
        def fail_market():
            raise RuntimeError("secret /Users/private/market_view token=do-not-return")
        monkeypatch.setattr(pm_conviction, "_read_market_view", fail_market)
    else:
        monkeypatch.setattr(pm_conviction, "_read_market_view", lambda: None)
        monkeypatch.setattr(pm_conviction, "_market_view_enrichment", lambda _mv: {})

    if decision_fail:
        def fail_decision():
            raise RuntimeError("secret /Users/private/decision_context api_key=do-not-return")
        monkeypatch.setattr(decision_context, "prompt_summary", fail_decision)
    else:
        monkeypatch.setattr(decision_context, "prompt_summary", lambda: {})


def test_valid_core_with_absent_optional_context_keeps_success_shape(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_regime(vendor)
    _wire_optional_context(monkeypatch)

    payload = json.loads(_text(asyncio.run(bot_mcp.get_regime.handler({}))))
    assert payload["quad"] == "Q1"
    assert payload["sector_rs_top"] == [{"ticker": "XLK"}]
    assert "read_status" not in payload
    assert "failed_sources" not in payload


def test_missing_core_is_explicit_absent_not_false_empty(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")
    _wire_optional_context(monkeypatch)

    payload = json.loads(_text(asyncio.run(bot_mcp.get_regime.handler({}))))
    assert payload["read_status"] == "unavailable"
    assert payload["regime_status"] == "absent"
    assert payload["error"] == "regime_core_absent"
    assert payload["quad"] is None
    assert payload["sector_rs_top"] is None


def test_corrupt_core_is_closed_unavailable_not_exception(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    path = vendor / "data" / "regime" / "latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ broken")
    _wire_optional_context(monkeypatch)

    raw = _text(asyncio.run(bot_mcp.get_regime.handler({})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["regime_status"] == "unavailable"
    assert payload["error"] == "regime_core_unavailable"
    assert payload["failed_sources"] == ["regime"]
    assert payload["sector_rs_top"] is None
    assert "broken" not in raw


def test_market_view_failure_is_partial_and_secret_safe(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_regime(vendor)
    _wire_optional_context(monkeypatch, market_fail=True)

    raw = _text(asyncio.run(bot_mcp.get_regime.handler({})))
    payload = json.loads(raw)
    assert payload["quad"] == "Q1"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["market_view"]
    assert "secret" not in raw and "/Users/private" not in raw and "do-not-return" not in raw


def test_decision_context_failure_is_partial_and_secret_safe(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_regime(vendor)
    _wire_optional_context(monkeypatch, decision_fail=True)

    raw = _text(asyncio.run(bot_mcp.get_regime.handler({})))
    payload = json.loads(raw)
    assert payload["quad"] == "Q1"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["decision_context"]
    assert "secret" not in raw and "api_key" not in raw


def test_both_optional_context_failures_are_named_without_losing_core(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_regime(vendor)
    _wire_optional_context(monkeypatch, market_fail=True, decision_fail=True)

    payload = json.loads(_text(asyncio.run(bot_mcp.get_regime.handler({}))))
    assert payload["quad"] == "Q1"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["market_view", "decision_context"]
