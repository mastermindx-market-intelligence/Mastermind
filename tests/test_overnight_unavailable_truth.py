"""Unavailable overnight observations must never be relabelled as calm."""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types


def _body(resp):
    return json.loads(resp.body)


def test_http_successful_calm_remains_calm(monkeypatch):
    from app import web
    from data_layer import overnight

    monkeypatch.setattr(
        overnight,
        "tape",
        lambda: {"groups": {}, "risk": {"state": "calm", "reasons": []}, "live": True},
    )
    payload = _body(web.api_overnight_tape())
    assert payload["risk"]["state"] == "calm"
    assert payload["live"] is True
    assert "overnight_status" not in payload


def test_http_failure_is_unavailable_not_calm_and_secret_safe(monkeypatch):
    from app import web
    from data_layer import overnight

    monkeypatch.setattr(
        overnight,
        "tape",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/overnight api_key=bad")),
    )
    response = web.api_overnight_tape()
    payload = _body(response)

    assert payload == {
        "overnight_status": "unavailable",
        "groups": None,
        "risk": None,
        "live": False,
        "error": "overnight_tape_unavailable",
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "api_key" not in raw


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


def test_mcp_failure_is_closed_unavailable_not_exception_text(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from data_layer import overnight

    monkeypatch.setattr(
        overnight,
        "tape",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/tape token=bad")),
    )
    out = asyncio.run(bot_mcp.get_overnight_tape.handler({}))
    payload = json.loads(out["content"][0]["text"])

    assert payload == {
        "overnight_status": "unavailable",
        "risk": None,
        "groups": None,
        "live": False,
        "error": "overnight_tape_unavailable",
        "note": "overnight tape unavailable",
    }
    raw = out["content"][0]["text"]
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw
