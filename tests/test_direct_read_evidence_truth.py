"""Direct/live Brain reads must be closed, secret-safe, and non-speculative on failure."""
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


def test_quote_transport_failure_is_closed_and_secret_safe(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from data_layer import polygon

    def explode(_tickers):
        raise RuntimeError("secret /Users/private/polygon api_key=do-not-return")

    monkeypatch.setattr(polygon, "quotes", explode)
    raw = _text(asyncio.run(bot_mcp.get_quote.handler({"tickers": ["AAPL"]})))
    payload = json.loads(raw)
    assert payload == {
        "read_status": "unavailable",
        "error": "live_quotes_unavailable",
        "failed_sources": ["quotes"],
        "quotes": None,
    }
    assert "secret" not in raw and "/Users/private" not in raw and "api_key" not in raw


def test_quote_wrong_shape_is_unavailable(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from data_layer import polygon
    monkeypatch.setattr(polygon, "quotes", lambda _tickers: [250.0])

    payload = json.loads(_text(asyncio.run(bot_mcp.get_quote.handler({"tickers": ["AAPL"]}))))
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "live_quotes_unavailable"
    assert payload["quotes"] is None


def test_all_null_quotes_do_not_claim_provider_outage(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from data_layer import polygon
    monkeypatch.setattr(polygon, "quotes", lambda _tickers: {"AAPL": None})

    text = _text(asyncio.run(bot_mcp.get_quote.handler({"tickers": ["AAPL"]})))
    assert text == "no live quotes returned for the requested tickers."
    assert "offline" not in text.lower() and "api key" not in text.lower()


def test_healthy_quotes_keep_existing_payload(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from data_layer import polygon
    monkeypatch.setattr(polygon, "quotes", lambda _tickers: {"AAPL": 250.0, "MSFT": None})

    payload = json.loads(_text(asyncio.run(bot_mcp.get_quote.handler({"tickers": ["AAPL", "MSFT"]}))))
    assert payload["quotes"] == {"AAPL": 250.0, "MSFT": None}
    assert "read_status" not in payload


def test_read_signal_missing_does_not_disclose_absolute_allowed_path(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    allowed = tmp_path / "vendor" / "macro" / "site"
    allowed.mkdir(parents=True)
    monkeypatch.setattr(bot_mcp, "_ROOT", tmp_path)
    monkeypatch.setattr(bot_mcp, "_READ_ROOTS", [allowed])
    monkeypatch.setattr(bot_mcp, "_DENY_ROOTS", [])

    target = allowed / "signals" / "missing.json"
    text = _text(asyncio.run(bot_mcp.read_signal.handler({"path": str(target)})))
    assert text == "not found: requested signal path"
    assert str(tmp_path) not in text


def test_read_signal_corrupt_json_is_closed_and_secret_safe(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    allowed = tmp_path / "vendor" / "macro" / "site"
    target = allowed / "signals" / "bad.json"
    target.parent.mkdir(parents=True)
    target.write_text("{ broken secret token=do-not-return")
    monkeypatch.setattr(bot_mcp, "_ROOT", tmp_path)
    monkeypatch.setattr(bot_mcp, "_READ_ROOTS", [allowed])
    monkeypatch.setattr(bot_mcp, "_DENY_ROOTS", [])

    raw = _text(asyncio.run(bot_mcp.read_signal.handler({"path": str(target)})))
    payload = json.loads(raw)
    assert payload == {
        "read_status": "unavailable",
        "error": "signal_read_unavailable",
        "failed_sources": ["signal"],
    }
    assert "secret" not in raw and "do-not-return" not in raw and str(tmp_path) not in raw


def test_read_signal_valid_json_is_unchanged(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    allowed = tmp_path / "vendor" / "macro" / "site"
    target = allowed / "signals" / "ok.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"schema": "signal.v1", "value": 7}))
    monkeypatch.setattr(bot_mcp, "_ROOT", tmp_path)
    monkeypatch.setattr(bot_mcp, "_READ_ROOTS", [allowed])
    monkeypatch.setattr(bot_mcp, "_DENY_ROOTS", [])

    payload = json.loads(_text(asyncio.run(bot_mcp.read_signal.handler({"path": str(target)}))))
    assert payload == {"schema": "signal.v1", "value": 7}
