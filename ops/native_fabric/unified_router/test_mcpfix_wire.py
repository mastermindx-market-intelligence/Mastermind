"""Regression tests for the mcpfix1 wire-translation patch.

Covers: GLM MCP-native blocks (mcp_tool_use / mcp_tool_result) in both user
and assistant roles across both wire translators, and degradation (never a
hard FABRIC_TRANSLATE_* kill) for malformed tool arguments.
"""
import json
import sys

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ops.native_fabric.unified_router import wire  # noqa: E402
from ops.native_fabric.unified_router.wire import (  # noqa: E402
    OpenAIStreamTranslator, ResponsesStreamTranslator, anthropic_to_openai,
    anthropic_to_responses, openai_to_anthropic)

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
    """GLM echoes MCP results inside its own assistant turn (post-mcpfix1
    discovery). Must degrade to text, not FABRIC_TRANSLATE_BLOCK."""
    body = {"model": "glm-5.3", "max_tokens": 16, "messages": [
        {"role": "assistant", "content": [
            {"type": "mcp_tool_use", "id": "m1", "name": "fs", "input": {}},
            {"type": "mcp_tool_result", "tool_use_id": "m1",
             "content": "file list output"}]},
        {"role": "user", "content": "summarize"}]}
    r1 = anthropic_to_openai(body)
    asst = [m for m in r1["messages"] if m["role"] == "assistant"][0]
    assert "file list output" in (asst["content"] or ""), asst
    assert asst["tool_calls"], "tool_calls lost"
    r2 = anthropic_to_responses(body)
    items = r2["input"]
    texts = [i for i in items if isinstance(i.get("content"), list)]
    assert any("file list output" in json.dumps(i["content"]) for i in texts), items
    calls = [i for i in items if i.get("type") == "function_call"]
    assert calls, "function_call lost"
    print("ok assistant-role mcp_tool_result both translators")


@case
def test_tool_name_variants():
    assert wire._tool_name({"name": "a"}) == "a"
    assert wire._tool_name({"tool_name": "b"}) == "b"
    assert wire._tool_name({"server_label": "c"}) == "c"
    assert wire._tool_name({}) == ""
    print("ok tool name variants")


# ── FABRIC_TRANSLATE_TOOL_ARGUMENTS: malformed arguments degrade, not kill ────
@case
def test_malformed_arguments_openai_to_anthropic():
    payload = {"id": "r1", "choices": [{"finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None, "tool_calls": [
            {"id": "t1", "function": {"name": "f",
                                      "arguments": "{\"a\": tr"}}]}}]}
    out = openai_to_anthropic(payload, model="m")
    use = [b for b in out["content"] if b["type"] == "tool_use"][0]
    assert use["input"] == {"_raw_arguments": "{\"a\": tr"}, use
    print("ok malformed args non-stream")


@case
def test_malformed_arguments_stream_finish():
    t = OpenAIStreamTranslator(model="m")
    t.feed({"choices": [{"delta": {"tool_calls": [
        {"index": 0, "id": "t1", "function": {"name": "f",
                                              "arguments": "{\"uncut"}}]}}]})
    events = t.finish()  # previously raised FABRIC_TRANSLATE_TOOL_ARGUMENTS
    blobs = [e for e in events if e[0] == "content_block_delta"]
    assert any(json.loads(e[1])["delta"]["partial_json"].startswith(
        "{\"_raw_arguments\"") for e in blobs), events
    print("ok malformed args stream finish")


@case
def test_malformed_arguments_responses_translator():
    t = ResponsesStreamTranslator(model="m")
    t.feed({"type": "response.output_item.added",
            "item": {"type": "function_call", "call_id": "c1", "name": "f"}})
    t.feed({"type": "response.function_call_arguments.delta",
            "call_id": "c1", "delta": "{\"x\":"})
    t.feed({"type": "response.completed", "response": {"status": "completed"}})
    msg = t.to_message()  # previously raised
    events = t.finish()
    assert any(b["input"] == {"_raw_arguments": "{\"x\":"}
               for b in msg["content"] if b["type"] == "tool_use"), msg
    assert events, "finish produced no events"
    print("ok malformed args responses")


@case
def test_non_dict_json_arguments():
    assert wire._coerce_arguments("[1,2]") == {"_raw_arguments": "[1,2]"}
    assert wire._coerce_arguments("null") == {"_raw_arguments": "null"}
    assert wire._coerce_arguments({"already": "dict"}) == {"already": "dict"}
    assert wire._coerce_arguments('{"ok": 1}') == {"ok": 1}
    assert wire._coerce_arguments("") == {}
    print("ok coercion edge cases")


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
