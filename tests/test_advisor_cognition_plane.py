"""Advisor chat cognition plane: broad typed reads without portfolio mutation authority."""
from __future__ import annotations

import asyncio
import json

import pytest

from brain import advisor, cli_bridge, cognition_mcp, portfolio_intelligence


def _text(result: dict) -> str:
    return result["content"][0]["text"]


def _drain(agen):
    async def run():
        return [event async for event in agen]

    return asyncio.run(run())


def test_cognition_server_is_read_only_and_reuses_existing_intelligence_tools():
    names = {tool.name for tool in cognition_mcp._READ_TOOLS}
    assert names == {
        "get_market_packet",
        "get_prophet_board",
        "get_sector_rotation",
        "get_technical_lab",
        "get_context_catalog",
        "get_surface_packet",
        "get_neural_web_packet",
    }

    allowed = set(cognition_mcp.allowed_tools())
    assert allowed == {f"mcp__cognition__{name}" for name in names}
    assert not any(
        forbidden in tool_name
        for tool_name in allowed
        for forbidden in ("submit_book", "request_context_upgrade", "get_my_book")
    )
    assert cognition_mcp.build_server() is not None
    from brain import autonomous_mcp
    assert all(getattr(cognition_mcp, name) is getattr(autonomous_mcp, name) for name in names)


def test_cognition_handlers_read_the_incumbent_portfolio_intelligence_owner(monkeypatch):
    expected = {
        "schema": "mastermind.portfolio_intelligence.catalog/v1",
        "surfaces": [{"id": "radar", "status": "fresh"}],
    }
    monkeypatch.setattr(portfolio_intelligence, "context_catalog", lambda: expected)

    result = json.loads(_text(asyncio.run(cognition_mcp.get_context_catalog.handler({}))))

    assert result == expected


class _Result:
    def __init__(self):
        self.result = "Connected evidence."
        self.session_id = "session-cognition"
        self.total_cost_usd = 0.0


def test_chat_stream_arms_bot_and_read_only_cognition_servers(monkeypatch):
    async def fake_query(*, prompt, options):
        assert set(options.mcp_servers) == {"bot", "cognition"}
        assert options.permission_mode == cli_bridge._HEADLESS_PERMISSION_MODE == "dontAsk"
        allowed = set(options.allowed_tools)
        assert "mcp__bot__get_regime" in allowed
        assert "mcp__cognition__get_context_catalog" in allowed
        assert "mcp__cognition__get_surface_packet" in allowed
        assert "mcp__cognition__get_technical_lab" in allowed
        assert "mcp__cognition__get_neural_web_packet" in allowed
        assert not any(
            name in allowed
            for name in (
                "mcp__cognition__submit_book",
                "mcp__cognition__request_context_upgrade",
                "mcp__cognition__get_my_book",
            )
        )
        yield _Result()

    monkeypatch.setattr(cli_bridge, "_SDK", True)
    monkeypatch.setattr(cli_bridge, "_sdk_query", fake_query)
    monkeypatch.setattr(cli_bridge, "cli_path", lambda: "/usr/bin/claude")

    events = _drain(cli_bridge.chat_stream("connect the market evidence"))

    assert [event["text"] for event in events if event["type"] == "text"] == [
        "Connected evidence."
    ]
    assert events[-1]["type"] == "done"


def test_advisor_prompt_requires_freshness_contradiction_and_independence_checks():
    prompt = advisor.SYSTEM.lower()
    for tool_name in (
        "get_context_catalog",
        "get_surface_packet",
        "get_market_packet",
        "get_intel_hub",
        "get_technical_lab",
        "get_neural_web_packet",
    ):
        assert tool_name in prompt
    assert "independent evidence families" in prompt
    assert "stale or missing" in prompt
    assert "contradictions" in prompt
    assert "observed facts" in prompt
    assert "inference" in prompt
    assert "unknown" in prompt


def test_advisor_prompt_keeps_preliminary_gate_first_and_rejects_legacy_sizing():
    prompt = advisor.SYSTEM.lower()
    assert "evaluate_gate remains the first tool call" in prompt
    assert "legacy suggested-size" in prompt
    assert "must not influence" in prompt


def test_chat_stream_redacts_backend_exception_text(monkeypatch):
    secret = "sk-live-should-never-reach-browser"

    async def boom(*, prompt, options):
        if False:
            yield {}
        raise RuntimeError(f"provider failed with {secret} at /private/runtime/path")

    monkeypatch.setattr(cli_bridge, "_SDK", True)
    monkeypatch.setattr(cli_bridge, "_sdk_query", boom)
    monkeypatch.setattr(cli_bridge, "cli_path", lambda: "/usr/bin/claude")

    events = _drain(cli_bridge.chat_stream("hi"))
    error = next(event for event in events if event["type"] == "error")

    assert error == {
        "type": "error",
        "code": "advisor_chat_unavailable",
        "error": "Mastermind AI is temporarily unavailable. Please retry.",
    }
    assert secret not in json.dumps(events)
    assert "/private/runtime/path" not in json.dumps(events)


def test_chat_route_does_not_stream_raw_exception_repr():
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "app" / "main.py").read_text()
    chat_route = source[source.index('@app.post("/chat")'):source.index('@app.get("/chat/history")')]
    assert "repr(exc)" not in chat_route
    assert "cli_bridge.public_chat_error_event()" in chat_route


def test_shared_inference_prompt_keeps_cognition_guidance_conditional():
    from brain import bot_mcp

    tools = {row["name"] for row in bot_mcp.inference_tool_catalog()}
    assert not any(name.startswith("mcp__cognition__") for name in tools)
    prompt = advisor.inference_system()
    assert "ONLY WHEN get_context_catalog" in prompt
    assert "Never call an unlisted tool" in prompt
    assert "If cognition tools are not listed" in prompt
    assert "State which\nconnected evidence is unavailable" in prompt
    assert "evaluate_gate remains first in every backend" in prompt
    assert "External web search, arbitrary file access and web fetch are unavailable" in prompt
    assert "INDEPENDENT EVIDENCE FAMILIES" in prompt


@pytest.mark.parametrize("partial_text", [False, True])
def test_actual_chat_generator_uses_public_error_and_preserves_bookkeeping(
    monkeypatch, partial_text
):
    import ast
    from pathlib import Path
    from types import SimpleNamespace

    tree = ast.parse((Path(__file__).resolve().parent.parent / "app" / "main.py").read_text())
    chat = next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "chat")
    generator = next(node for node in chat.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "gen")
    encoder = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_sse")
    assert generator.decorator_list == encoder.decorator_list == []
    namespace = {
        "json": json, "cli_bridge": cli_bridge, "advisor": advisor,
        "req": SimpleNamespace(message="fixture question"), "conv_id": "fixture-chat",
        "resume": "prior-session",
    }
    # Execute the exact parsed generator and SSE encoder, with an inert upstream
    # stream and bookkeeping spies. This does not start an HTTP server or model.
    exec(compile(ast.Module(body=[encoder, generator], type_ignores=[]), "<actual-chat-generator>", "exec"), namespace)
    secret = "opaque-route-failure-secret"
    calls = []

    async def broken_stream(*_args, **_kwargs):
        if partial_text:
            yield {"type": "text", "text": "Earlier grounded text."}
        raise RuntimeError(secret + " /private/provider/path")

    monkeypatch.setattr(cli_bridge, "_selected_backend", lambda: "cli")
    monkeypatch.setattr(cli_bridge, "chat_stream", broken_stream)
    monkeypatch.setattr(advisor, "append_turn", lambda *args: calls.append(("append", args)))
    monkeypatch.setattr(advisor, "set_session", lambda *args: calls.append(("session", args)))
    frames = _drain(namespace["gen"]())
    events = [json.loads(frame.split("data: ", 1)[1].strip()) for frame in frames]
    assert events[0] == {"type": "start", "conversation_id": "fixture-chat", "backend": "cli"}
    assert events[-1] == {
        "type": "error", "code": "advisor_chat_unavailable",
        "error": "Mastermind AI is temporarily unavailable. Please retry.",
    }
    assert [event["text"] for event in events if event["type"] == "text"] == (["Earlier grounded text."] if partial_text else [])
    assert secret not in "".join(frames)
    assert "/private/provider/path" not in "".join(frames)
    assert calls == [
        ("append", ("fixture-chat", "user", "fixture question")),
        ("session", ("fixture-chat", "prior-session")),
        ("append", ("fixture-chat", "brain", "Earlier grounded text." if partial_text else "", [], [])),
    ]
