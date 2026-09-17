"""Session-entry Brain intelligence must distinguish absent artifacts from failed evidence."""
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


def _wire_intake(monkeypatch, *, fail=False):
    from brain import intake

    if fail:
        def explode(*_args, **_kwargs):
            raise RuntimeError("secret /Users/private/intake api_key=do-not-return")
        monkeypatch.setattr(intake, "build", explode)
    else:
        monkeypatch.setattr(intake, "build", lambda limit=20: {
            "as_of": "2026-09-17",
            "macro_context": {"quad": "Q1"},
            "candidates": [{"ticker": "AAPL", "score": 9}],
        })


def _briefing_payload():
    return {
        "as_of": "2026-09-17",
        "macro_context": {"quad": "Q1"},
        "n_actionable": 1,
        "n_divergences": 0,
        "priority_queue": [{"ticker": "AAPL", "score": 9}],
        "divergences": [],
        "how_to_use": "start here",
    }


def _hub_payload():
    return {
        "as_of": "2026-09-17",
        "macro_context": {"quad": "Q1"},
        "desks": {"news": {"live": True}},
        "counts": {"command": 1},
        "n_actionable": 1,
        "command": [{"ticker": "AAPL", "name": "Apple", "composite_conviction": 80, "flags": []}],
        "divergence_alerts": {"early_edge": [], "crowded_top": []},
        "sector_heat": [{"etf": "XLK"}],
        "how_to_use": "rank then inspect",
    }


def test_missing_briefing_composes_live_without_degradation(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")
    _wire_intake(monkeypatch)

    payload = json.loads(_text(asyncio.run(bot_mcp.get_daily_briefing.handler({"top": 5}))))
    assert payload["priority_queue"] == [{"ticker": "AAPL", "score": 9}]
    assert "Composed live" in payload["note"]
    assert "read_status" not in payload


def test_corrupt_briefing_can_use_healthy_mirror_but_stays_partial(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "intelligence" / "briefing.json")
    _write_json(vendor / "data" / "intelligence" / "briefing.json", _briefing_payload())

    raw = _text(asyncio.run(bot_mcp.get_daily_briefing.handler({"top": 5})))
    payload = json.loads(raw)
    assert payload["priority_queue"][0]["ticker"] == "AAPL"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["briefing"]
    assert "secret" not in raw and "do-not-return" not in raw


def test_empty_briefing_artifact_falls_back_live_as_partial(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "intelligence" / "briefing.json", {})
    _wire_intake(monkeypatch)

    payload = json.loads(_text(asyncio.run(bot_mcp.get_daily_briefing.handler({}))))
    assert payload["priority_queue"][0]["ticker"] == "AAPL"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["briefing"]


def test_briefing_wrong_queue_shape_preserves_other_fields_as_partial(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    payload = _briefing_payload()
    payload["priority_queue"] = {"AAPL": 9}
    _write_json(vendor / "site" / "intelligence" / "briefing.json", payload)

    out = json.loads(_text(asyncio.run(bot_mcp.get_daily_briefing.handler({}))))
    assert out["as_of"] == "2026-09-17"
    assert out["priority_queue"] is None
    assert out["read_status"] == "partial"
    assert out["failed_sources"] == ["briefing"]


def test_missing_briefing_plus_failed_live_composition_is_unavailable(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")
    _wire_intake(monkeypatch, fail=True)

    raw = _text(asyncio.run(bot_mcp.get_daily_briefing.handler({})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "daily_briefing_unavailable"
    assert payload["failed_sources"] == ["intake"]
    assert payload["priority_queue"] is None
    assert "secret" not in raw and "api_key" not in raw


def test_missing_hub_keeps_existing_not_built_message(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")

    text = _text(asyncio.run(bot_mcp.get_intel_hub.handler({})))
    assert text == "intel hub not built yet (site/intel_hub/hub.json absent — ships in the daily build)."


def test_corrupt_hub_is_unavailable_not_not_built(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "intel_hub" / "hub.json")

    raw = _text(asyncio.run(bot_mcp.get_intel_hub.handler({})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "intel_hub_unavailable"
    assert payload["failed_sources"] == ["intel_hub"]
    assert payload["command"] is None
    assert "not built yet" not in raw and "secret" not in raw


def test_corrupt_hub_primary_uses_fallback_but_stays_partial(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "intel_hub" / "hub.json")
    _write_json(vendor / "data" / "intel_hub" / "hub.json", _hub_payload())

    payload = json.loads(_text(asyncio.run(bot_mcp.get_intel_hub.handler({}))))
    assert payload["command"][0]["ticker"] == "AAPL"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intel_hub"]


def test_hub_wrong_command_shape_cannot_claim_ticker_has_no_signal(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    payload = _hub_payload()
    payload["command"] = {"AAPL": {"score": 80}}
    _write_json(vendor / "site" / "intel_hub" / "hub.json", payload)

    raw = _text(asyncio.run(bot_mcp.get_intel_hub.handler({"ticker": "MSFT"})))
    out = json.loads(raw)
    assert out["ticker"] == "MSFT"
    assert out["dossier"] is None
    assert out["read_status"] == "partial"
    assert out["failed_sources"] == ["intel_hub"]
    assert "no cross-desk signal today" not in raw


def test_hub_healthy_command_absence_keeps_existing_no_signal_message(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "intel_hub" / "hub.json", _hub_payload())

    text = _text(asyncio.run(bot_mcp.get_intel_hub.handler({"ticker": "MSFT"})))
    assert text == "MSFT not in the intel-hub command (no cross-desk signal today)."
