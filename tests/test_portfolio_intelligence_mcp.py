"""Focused contract tests for the three active Portfolio Brain intelligence surfaces."""
from __future__ import annotations

import asyncio
import importlib
import json

import pytest

pytest.importorskip("claude_agent_sdk")


def _payload(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


@pytest.mark.parametrize(
    ("module_name", "server", "is_us"),
    [
        ("brain.autonomous_mcp", "desk", True),
        ("brain.china_mcp", "china", False),
        ("brain.hk_mcp", "hk", False),
    ],
)
def test_intelligence_tools_are_registered_and_schema_bounded(module_name, server, is_us):
    from brain import portfolio_intelligence

    module = importlib.import_module(module_name)
    tools = module._DESK_TOOLS if is_us else module._ALL_TOOLS
    by_name = {item.name: item for item in tools}
    expected = {
        "get_context_catalog", "get_surface_packet", "get_technical_lab",
        "get_neural_web_packet", "request_context_upgrade",
    }
    assert expected <= set(by_name)
    assert {f"mcp__{server}__{name}" for name in expected} <= set(module.allowed_tools())

    surface_schema = by_name["get_surface_packet"].input_schema
    surface = surface_schema["properties"]["surface_id"]
    surface_ids = module.SURFACE_IDS if is_us else module.autonomous_mcp.SURFACE_IDS
    assert set(surface["enum"]) == set(surface_ids)
    assert set(surface["enum"]) == {
        item["id"] for item in portfolio_intelligence.context_catalog()["surfaces"]
    }
    assert surface_schema["properties"]["limit"] == {
        "type": "integer", "minimum": 1, "maximum": 8,
    }
    assert surface_schema["additionalProperties"] is False

    neural_schema = by_name["get_neural_web_packet"].input_schema
    tickers = neural_schema["properties"]["tickers"]
    assert tickers["type"] == "array"
    assert tickers["items"]["type"] == "string"
    assert tickers["maxItems"] == 6
    assert tickers["uniqueItems"] is True
    assert neural_schema["additionalProperties"] is False

    if not is_us:
        # CN/HK retain their own regime and intake. US auto-packets are deliberately absent.
        assert not {"get_market_packet", "get_prophet_board", "get_sector_rotation"} & set(by_name)


@pytest.mark.parametrize(
    ("module_name", "book", "ticker"),
    [
        ("brain.autonomous_mcp", "autonomous", "NVDA"),
        ("brain.china_mcp", "china", "600519.SS"),
        ("brain.hk_mcp", "hk", "0700.HK"),
    ],
)
def test_neural_web_tool_is_book_bound(monkeypatch, module_name, book, ticker):
    from brain import portfolio_intelligence

    module = importlib.import_module(module_name)
    seen = {}

    def fake_packet(bound_book, tickers=None):
        seen.update(book=bound_book, tickers=tickers)
        return {"book": bound_book, "tickers": tickers, "execution_authority": False}

    monkeypatch.setattr(portfolio_intelligence, "neural_web_packet", fake_packet)
    out = _payload(asyncio.run(module.get_neural_web_packet.handler({"tickers": [ticker]})))
    assert seen == {"book": book, "tickers": [ticker]}
    assert out == {"book": book, "tickers": [ticker], "execution_authority": False}


@pytest.mark.parametrize(
    "module_name",
    ["brain.autonomous_mcp", "brain.china_mcp", "brain.hk_mcp"],
)
def test_surface_tool_rejects_paths_even_when_handler_called_directly(module_name):
    module = importlib.import_module(module_name)
    out = _payload(asyncio.run(module.get_surface_packet.handler({
        "surface_id": "../../etc/passwd", "limit": 8,
    })))
    assert out["status"] == "invalid_surface_id"
    assert out["execution_authority"] is False
    assert "../../etc/passwd" not in out["valid_surface_ids"]
    assert len(json.dumps(out)) < 8000


@pytest.mark.parametrize(
    ("module_name", "book"),
    [
        ("brain.autonomous_mcp", "autonomous"),
        ("brain.china_mcp", "china"),
        ("brain.hk_mcp", "hk"),
    ],
)
def test_context_upgrade_tool_is_book_bound(monkeypatch, module_name, book):
    from brain import portfolio_learning

    module = importlib.import_module(module_name)
    seen = {}

    def fake_request(bound_book, plane, reason, ticker=None):
        seen.update(book=bound_book, plane=plane, reason=reason, ticker=ticker)
        return {"ok": True, "book": bound_book, "authority": "request_only"}

    monkeypatch.setattr(portfolio_learning, "request_context", fake_request)
    args = {
        "plane": "technical_gap",
        "reason": "Need a fresher multi-timeframe confirmation before deciding.",
        "ticker": "0700.HK" if book == "hk" else None,
    }
    out = _payload(asyncio.run(module.request_context_upgrade.handler(args)))
    assert seen == {"book": book, **args}
    assert out == {"ok": True, "book": book, "authority": "request_only"}
