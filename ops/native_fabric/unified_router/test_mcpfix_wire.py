"""Regression tests for the mcpfix1 wire-translation patch.

Covers completed MCP-native history across wires without losing identity,
and explicit refusal of malformed tool inputs without raw logging.
"""
import json
import sys
import pytest

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ops.native_fabric.unified_router import wire  # noqa: E402
from ops.native_fabric.unified_router.wire import (  # noqa: E402
    OpenAIStreamTranslator, ResponsesStreamTranslator, anthropic_to_openai,
    anthropic_to_responses, openai_to_anthropic, WireTranslationError)

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# ── FABRIC_TRANSLATE_BLOCK: GLM MCP-native assistant blocks ──────────────────
@case
def test_mcp_tool_use_assistant_chat():
    body = {"model": "glm-5.3", "max_tokens": 64, "messages": [
        {"role": "user", "content": "run the tool"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "calling"},
            {"type": "mcp_tool_use", "id": "mcp_1", "name": "search",
             "input": {"q": "hi"}}]},
        {"role": "user", "content": [
            {"type": "mcp_tool_result", "tool_use_id": "mcp_1",
             "content": "result text"}]},
    ]}
    req = anthropic_to_openai(body)
    asst = [m for m in req["messages"] if m["role"] == "assistant"][0]
    assert asst["tool_calls"][0]["function"]["name"] == "search", asst
    assert json.loads(asst["tool_calls"][0]["function"]["arguments"]) == {"q": "hi"}
    tool_msgs = [m for m in req["messages"] if m["role"] == "tool"]
    assert tool_msgs and tool_msgs[0]["tool_call_id"] == "mcp_1"
    assert tool_msgs[0]["content"] == "result text"
    print("ok mcp chat translation")


@case
def test_mcp_tool_use_assistant_responses():
    body = {"model": "glm-5.3", "max_tokens": 64, "messages": [
        {"role": "assistant", "content": [
            {"type": "mcp_tool_use", "id": "mcp_2", "tool_name": "lookup",
             "input": {"k": 1}}]},
        {"role": "user", "content": [
            {"type": "mcp_tool_result", "tool_use_id": "mcp_2",
             "content": [{"type": "text", "text": "found"}]}]},
    ]}
    req = anthropic_to_responses(body)
    calls = [i for i in req["input"] if i.get("type") == "function_call"]
    assert calls and calls[0]["name"] == "lookup" and calls[0]["call_id"] == "mcp_2"
    outs = [i for i in req["input"] if i.get("type") == "function_call_output"]
    assert outs and outs[0]["output"] == "found"
    print("ok mcp responses translation")


@case
def test_mcp_tool_result_assistant_role():
    """Assistant-contained results keep their call identity on both wires."""
    body = {"model": "glm-5.3", "max_tokens": 16, "messages": [
        {"role": "assistant", "content": [
            {"type": "mcp_tool_use", "id": "m1", "name": "fs", "input": {}},
            {"type": "mcp_tool_result", "tool_use_id": "m1",
             "content": "file list output"}]},
        {"role": "user", "content": "summarize"}]}
    r1 = anthropic_to_openai(body)
    asst = [m for m in r1["messages"] if m["role"] == "assistant"][0]
    assert asst["tool_calls"], "tool_calls lost"
    result = [m for m in r1["messages"] if m["role"] == "tool"][0]
    assert result["tool_call_id"] == "m1" and result["content"] == "file list output"
    r2 = anthropic_to_responses(body)
    items = r2["input"]
    outputs = [i for i in items if i.get("type") == "function_call_output"]
    assert outputs[0]["call_id"] == "m1" and outputs[0]["output"] == "file list output"
    calls = [i for i in items if i.get("type") == "function_call"]
    assert calls, "function_call lost"
    print("ok assistant-role mcp_tool_result both translators")


@case
def test_tool_name_variants():
    for field in ("name", "tool_name"):
        body = {"messages": [{"role": "assistant", "content": [
            {"type": "mcp_tool_use", "id": "a", field: "f", "input": {}},
            {"type": "mcp_tool_result", "tool_use_id": "a", "content": "ok"}]}]}
        assert anthropic_to_openai(body)["messages"][0]["tool_calls"][0]["function"]["name"] == "f"
    body["messages"][0]["content"][0] = {"type": "mcp_tool_use", "id": "a", "server_label": "server", "input": {}}
    with pytest.raises(WireTranslationError, match="FABRIC_TRANSLATE_TOOL_CALL"):
        anthropic_to_openai(body)


# Malformed arguments must never become a different executable argument object.
@case
def test_malformed_arguments_openai_to_anthropic():
    payload = {"id": "r1", "choices": [{"finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None, "tool_calls": [
            {"id": "t1", "function": {"name": "f",
                                      "arguments": "{\"a\": tr"}}]}}]}
    with pytest.raises(WireTranslationError, match="FABRIC_TRANSLATE_TOOL_ARGUMENTS"):
        openai_to_anthropic(payload, model="m")


@case
def test_malformed_arguments_stream_finish():
    t = OpenAIStreamTranslator(model="m")
    t.feed({"choices": [{"delta": {"tool_calls": [
        {"index": 0, "id": "t1", "function": {"name": "f",
                                              "arguments": "{\"uncut"}}]}}]})
    with pytest.raises(WireTranslationError, match="FABRIC_STREAM_INCOMPLETE"):
        t.finish()
    t.feed({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]})
    with pytest.raises(WireTranslationError, match="FABRIC_TRANSLATE_TOOL_ARGUMENTS"):
        t.finish()


@case
def test_malformed_arguments_responses_translator():
    t = ResponsesStreamTranslator(model="m")
    t.feed({"type": "response.output_item.added",
            "item": {"type": "function_call", "call_id": "c1", "name": "f"}})
    t.feed({"type": "response.function_call_arguments.delta",
            "call_id": "c1", "delta": "{\"x\":"})
    t.feed({"type": "response.completed", "response": {"status": "completed"}})
    for finish in (t.to_message, t.finish):
        with pytest.raises(WireTranslationError, match="FABRIC_TRANSLATE_TOOL_ARGUMENTS"):
            finish()


@case
def test_non_dict_json_arguments():
    for invalid in ("[1,2]", "null", "true", "5"):
        with pytest.raises(WireTranslationError, match="FABRIC_TRANSLATE_TOOL_ARGUMENTS"):
            wire._arguments(invalid)
    assert wire._arguments({"already": "dict"}) == {"already": "dict"}
    assert wire._arguments('{"ok": 1}') == {"ok": 1}
    assert wire._arguments("") == {}


def main():
    failed = 0
    for fn in CASES:
        try:
            fn()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
