import copy
import json
from types import SimpleNamespace as N
import unittest

from integrations.hermes_application_fabric.codec import (
    MAX_REQUEST_BYTES, MAX_RESULT_BYTES, to_owner_request, to_hermes_response,
)
from integrations.hermes_application_fabric.errors import HermesFabricError


def request(**extra):
    return {"model": "model-1", "messages": [{"role": "user", "content": "Hello 世界"}], **extra}


def tool(ident="t1", name="read", arguments='{"path":"/tmp/a"}'):
    return {"id": ident, "type": "function", "function": {"name": name, "arguments": arguments}}


def response(*blocks, stop="end_turn", model="model-1", usage=None):
    return N(model=model, content=list(blocks), stop_reason=stop,
             usage=usage if usage is not None else N(input_tokens=11, output_tokens=7))


class ConversationCodecTests(unittest.TestCase):
    def test_real_parallel_tool_history_round_trip_through_owner_codec(self):
        from engine.fabric_inference_client import _request
        history = [
            {"role": "system", "content": "保持原文\n exact\t"},
            {"role": "user", "content": "Read both."},
            {"role": "assistant", "content": None, "tool_calls": [tool(), tool("t2", "read", '{"path":"/tmp/β"}')]},
            {"role": "tool", "tool_call_id": "t2", "content": "second\n"},
            {"role": "tool", "tool_call_id": "t1", "content": "first\t"},
            {"role": "assistant", "content": "I have both."},
            {"role": "user", "content": "Summarize."},
        ]
        original = request(messages=history)
        before = copy.deepcopy(original)
        translated = to_owner_request(original, "model-1")
        _, wire = _request({**translated, "request_id": "req-1"}, "model-1", False)
        observed = json.loads(wire)["messages"]
        for a, b in zip(observed, history):
            if a.get("tool_calls"):
                for x, y in zip(a["tool_calls"], b["tool_calls"]):
                    self.assertEqual(json.loads(x["function"].pop("arguments")),
                                     json.loads(y["function"]["arguments"]))
                    y = copy.deepcopy(y)
                    y["function"].pop("arguments")
                    self.assertEqual(x, y)
            else:
                self.assertEqual(a, b)
        self.assertEqual(len(observed), len(history))
        self.assertEqual(original, before)

    def test_forced_tool_definition_and_choice(self):
        schema = {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}
        out = to_owner_request(request(tools=[{"type": "function", "function": {
            "name": "weather", "description": "Read", "parameters": schema}}],
            tool_choice={"type": "function", "function": {"name": "weather"}}), "model-1")
        self.assertEqual(out["tools"][0]["input_schema"], schema)
        self.assertEqual(out["tool_choice"], {"type": "tool", "name": "weather"})

    def test_text_parts_preserve_text(self):
        out = to_owner_request(request(messages=[{"role": "user", "content": [
            {"type": "text", "text": "α\n"}, {"type": "text", "text": "β"}]}]), "model-1")
        self.assertEqual(out["messages"][0]["content"], "α\nβ")

    def test_unknown_semantics_are_refused(self):
        for extra in [dict(response_format={"type": "json_schema"}), dict(reasoning_effort="high"),
                      dict(parallel_tool_calls=False), dict(extra_body={"reasoning": True}),
                      dict(logprobs=True), dict(seed=3), dict(stream=True)]:
            with self.subTest(extra=extra), self.assertRaises(HermesFabricError):
                to_owner_request(request(**extra), "model-1")

    def test_invalid_limits_and_numbers(self):
        for extra in [dict(max_tokens=True), dict(max_tokens=0), dict(max_tokens=32769),
                      dict(max_tokens=2, max_completion_tokens=3), dict(temperature=float("nan")),
                      dict(temperature=True), dict(stream=1), dict(stop=["a"] * 5),
                      dict(stream_options={"include_usage": "yes"})]:
            with self.subTest(extra=extra), self.assertRaises(HermesFabricError):
                to_owner_request(request(**extra), "model-1")

    def test_output_budget_alias(self):
        self.assertEqual(to_owner_request(request(max_completion_tokens=21), "model-1")["max_tokens"], 21)

    def test_native_relay_trace_header_is_not_an_owner_auth_override(self):
        trace = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
        converted = to_owner_request(request(extra_headers={"traceparent": trace}), "model-1")
        self.assertNotIn("extra_headers", converted)
        for headers in [{"Authorization": "Bearer must-not-pass"}, {"traceparent": "invalid"},
                        {"X-MM-Application-Turn-ID": "another-turn"},
                        {"traceparent": trace, "x-pool": "override"}]:
            with self.subTest(headers=list(headers)), self.assertRaises(HermesFabricError):
                to_owner_request(request(extra_headers=headers), "model-1")

    def test_unknown_roles_and_carriers(self):
        for msg in [dict(role="developer", content="x"), dict(role="user", content="x", name="a"),
                    dict(role="assistant", content="x", reasoning_content="private"),
                    dict(role="user", content=[{"type": "image_url", "image_url": {"url": "a"}}])]:
            with self.subTest(msg=msg), self.assertRaises(HermesFabricError):
                to_owner_request(request(messages=[msg]), "model-1")

    def test_orphan_duplicate_and_missing_tool_results(self):
        assistant = {"role": "assistant", "content": None, "tool_calls": [tool()]}
        result = {"role": "tool", "tool_call_id": "t1", "content": "ok"}
        histories = [[result], [assistant], [assistant, result, result],
                     [assistant, {"role": "user", "content": "skip"}],
                     [assistant, result, assistant, result],
                     [{**assistant, "tool_calls": [tool(), tool()]}]]
        for history in histories:
            with self.subTest(history=history), self.assertRaises(HermesFabricError):
                to_owner_request(request(messages=history), "model-1")

    def test_tool_argument_json_is_strict(self):
        for args in ['{"a":1,"a":2}', '{"x":NaN}', '{"x":1e999}', "[]", "{bad", '"text"']:
            with self.subTest(args=args), self.assertRaises(HermesFabricError):
                to_owner_request(request(messages=[{"role": "assistant", "content": None,
                    "tool_calls": [tool(arguments=args)]},
                    {"role": "tool", "tool_call_id": "t1", "content": "x"}]), "model-1")

    def test_strict_schema_is_not_silently_weakened(self):
        with self.assertRaises(HermesFabricError):
            to_owner_request(request(tools=[{"type": "function", "function": {
                "name": "read", "parameters": {}, "strict": True}}]), "model-1")

    def test_request_size_depth_cycle_and_model_fences(self):
        deep = []
        for _ in range(65):
            deep = [deep]
        cyclic = []
        cyclic.append(cyclic)
        for req in [request(messages=[{"role": "user", "content": "x" * MAX_REQUEST_BYTES}]),
                    request(messages=deep), request(messages=cyclic), request(model="other")]:
            with self.subTest(kind=list(req)), self.assertRaises(HermesFabricError):
                to_owner_request(req, "model-1")


class CompletionCodecTests(unittest.TestCase):
    def test_native_tool_response_and_actual_usage(self):
        result = to_hermes_response(response(N(type="text", text="Reading."),
            N(type="tool_use", id="t1", name="read", input={"path": "β"}), stop="tool_use"),
            request_id="req-1", selected_model="model-1")
        self.assertEqual(result["choices"][0]["finish_reason"], "tool_calls")
        call = result["choices"][0]["message"]["tool_calls"][0]
        self.assertEqual((call["id"], json.loads(call["function"]["arguments"])), ("t1", {"path": "β"}))
        self.assertEqual(result["usage"], {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18})

    def test_text_length_finish(self):
        result = to_hermes_response(response(N(type="text", text="part"), stop="max_tokens"),
                                   request_id="r", selected_model="model-1")
        self.assertEqual(result["choices"][0]["finish_reason"], "length")

    def test_unusable_results_never_emit_tools(self):
        t = N(type="tool_use", id="t1", name="read", input={})
        for resp in [response(t), response(t, stop="max_tokens"), response(t, t, stop="tool_use"),
                     response(N(type="text", text="x"), model="other"),
                     response(N(type="text", text="x"), usage=N(input_tokens=None, output_tokens=1)),
                     response(N(type="thinking", text="x")), response()]:
            with self.subTest(resp=resp), self.assertRaises(HermesFabricError):
                to_hermes_response(resp, request_id="r", selected_model="model-1")

    def test_result_aggregate_bound(self):
        with self.assertRaises(HermesFabricError):
            to_hermes_response(response(*[N(type="text", text="x" * 1024) for _ in range(1025)]),
                               request_id="r", selected_model="model-1")


if __name__ == "__main__":
    unittest.main()
