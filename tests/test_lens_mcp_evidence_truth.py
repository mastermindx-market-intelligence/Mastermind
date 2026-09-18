"""Lens MCP wrappers must fail closed without hiding the engine's legitimate degraded states."""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types


def _load_bot_mcp_with_fake_sdk(monkeypatch):
    fake = types.ModuleType("claude_agent_sdk")
    class ToolWrap:
        def __init__(self, name, handler): self.name=name; self.handler=handler
    def tool(name, _description, _schema):
        def deco(fn): return ToolWrap(name, fn)
        return deco
    fake.tool=tool
    fake.create_sdk_mcp_server=lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules,"claude_agent_sdk",fake)
    sys.modules.pop("brain.bot_mcp",None)
    return importlib.import_module("brain.bot_mcp")


def _payload(result):
    return json.loads(result["content"][0]["text"])


def test_decision_matrix_exception_is_closed_unavailable(monkeypatch):
    bot_mcp=_load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses
    def explode(*_args, **_kwargs):
        raise RuntimeError("secret /Users/private/lens token=do-not-return")
    monkeypatch.setattr(lenses,"full",explode)
    payload=_payload(asyncio.run(bot_mcp.get_decision_matrix.handler({"subject":"AAPL","kind":"name"})))
    assert payload == {
        "subject":"AAPL","read_status":"unavailable","error":"decision_matrix_unavailable",
        "failed_sources":["decision_matrix"]
    }


def test_decision_matrix_wrong_shape_is_unavailable(monkeypatch):
    bot_mcp=_load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses
    monkeypatch.setattr(lenses,"full",lambda *_args,**_kwargs: ["wrong"])
    payload=_payload(asyncio.run(bot_mcp.get_decision_matrix.handler({"subject":"AAPL"})))
    assert payload["error"] == "decision_matrix_unavailable"
    assert payload["read_status"] == "unavailable"


def test_decision_matrix_empty_mapping_is_unavailable(monkeypatch):
    bot_mcp=_load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses
    monkeypatch.setattr(lenses,"full",lambda *_args,**_kwargs: {})
    payload=_payload(asyncio.run(bot_mcp.get_decision_matrix.handler({"subject":"AAPL"})))
    assert payload["error"] == "decision_matrix_unavailable"
    assert payload["failed_sources"] == ["decision_matrix"]


def test_legitimate_degraded_matrix_passes_through(monkeypatch):
    bot_mcp=_load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses
    expected={"subject":"AAPL","data_degraded":True,"synthesis":{"size_authority":"insufficient_data"},"rows":[]}
    monkeypatch.setattr(lenses,"full",lambda *_args,**_kwargs: expected)
    payload=_payload(asyncio.run(bot_mcp.get_decision_matrix.handler({"subject":"AAPL"})))
    assert payload == expected


def test_divergence_matrix_exception_is_closed_unavailable(monkeypatch):
    bot_mcp=_load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses
    def explode(*_args, **_kwargs):
        raise RuntimeError("secret /Users/private/matrix api_key=do-not-return")
    monkeypatch.setattr(lenses,"decision_matrix",explode)
    payload=_payload(asyncio.run(bot_mcp.get_divergences.handler({"subject":"AAPL"})))
    assert payload["error"] == "divergence_synthesis_unavailable"
    assert payload["failed_sources"] == ["decision_matrix"]


def test_divergence_malformed_matrix_is_matrix_failure(monkeypatch):
    bot_mcp=_load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses
    monkeypatch.setattr(lenses,"decision_matrix",lambda *_args,**_kwargs:{})
    payload=_payload(asyncio.run(bot_mcp.get_divergences.handler({"subject":"AAPL"})))
    assert payload["error"] == "divergence_synthesis_unavailable"
    assert payload["failed_sources"] == ["decision_matrix"]


def test_divergence_synthesis_exception_is_closed_unavailable(monkeypatch):
    bot_mcp=_load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses
    monkeypatch.setattr(lenses,"decision_matrix",lambda *_args,**_kwargs:{"rows":[]})
    def explode(_matrix):
        raise RuntimeError("secret synthesis token=do-not-return")
    monkeypatch.setattr(lenses,"synthesize",explode)
    payload=_payload(asyncio.run(bot_mcp.get_divergences.handler({"subject":"AAPL"})))
    assert payload["error"] == "divergence_synthesis_unavailable"
    assert payload["failed_sources"] == ["divergence_synthesis"]


def test_divergence_wrong_shape_is_unavailable(monkeypatch):
    bot_mcp=_load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses
    monkeypatch.setattr(lenses,"decision_matrix",lambda *_args,**_kwargs:{"rows":[]})
    monkeypatch.setattr(lenses,"synthesize",lambda _matrix:{"divergences":[]})
    payload=_payload(asyncio.run(bot_mcp.get_divergences.handler({"subject":"AAPL"})))
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "divergence_synthesis_unavailable"


def test_healthy_divergence_shape_is_unchanged(monkeypatch):
    bot_mcp=_load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses
    monkeypatch.setattr(lenses,"decision_matrix",lambda *_args,**_kwargs:{"rows":[]})
    monkeypatch.setattr(lenses,"synthesize",lambda _matrix:{"divergences":[{"pattern":"early_edge"}],"confluence":0.4,"vetoes":[]})
    payload=_payload(asyncio.run(bot_mcp.get_divergences.handler({"subject":"AAPL"})))
    assert payload == {"divergences":[{"pattern":"early_edge"}],"confluence":0.4,"vetoes":[]}
