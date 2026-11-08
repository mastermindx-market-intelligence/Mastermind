"""Actual incumbent client over loopback; no production keys or provider calls.

Run with the exact Macro APPLICATION source on PYTHONPATH. No copied owner code
is shipped in this package, and a simulated endpoint is never live acceptance.
"""
from contextvars import copy_context
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
from types import SimpleNamespace as N
import unittest

from engine.fabric_inference_client import FabricInferenceClient, NATIVE_PROTOCOL, NATIVE_SCHEMA
from integrations.hermes_application_fabric import (
    ApplicationBinding, HermesApplicationClient, NativeCall, HermesFabricError, call_scope,
)
from integrations.hermes_application_fabric.native import execution_middleware, classify_error, PROVIDER


class OwnerLoopbackTests(unittest.TestCase):
    def setUp(self):
        self.calls, self.mode, self.closed, self.allow = [], "text", 0, True
        self.structured_value = {"answer": 42}
        self.tool_name, self.tool_arguments = "read", {"path": "/tmp/x"}
        self.auto_inspection = None
        self.route_overrides = {}
        self.serving_model = "model-1"
        self.response_release, self.response_finished = threading.Event(), threading.Event()
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/application-turns/close":
                    parent.closed += 1
                    self.reply(200, {"application": {"schema": NATIVE_SCHEMA,
                        "disposition": "closed", "turn_id": payload["turn_id"], "request_id": None,
                        "dispatch_permitted": False, "effect_unknown": False}}, "closed", payload["turn_id"], None)
                    return
                parent.calls.append({"payload": payload, "request_id": self.headers["Idempotency-Key"],
                    "turn_id": self.headers["X-MM-Application-Turn-ID"],
                    "authenticated": self.headers["Authorization"] == "Bearer " + "t" * 40})
                if parent.mode == "native-stall":
                    parent.response_release.wait(timeout=8)
                if parent.mode == "disconnect" or parent.mode == "native-effect-disconnect" and len(parent.calls) > 1:
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                req, turn = self.headers["Idempotency-Key"], self.headers["X-MM-Application-Turn-ID"]
                if parent.mode in {"429-refused", "pending"}:
                    state = "refused" if parent.mode == "429-refused" else "pending"
                    self.reply(429 if state == "refused" else 409, {"application": {
                        "schema": NATIVE_SCHEMA, "disposition": state, "turn_id": turn,
                        "request_id": req, "dispatch_permitted": False, "effect_unknown": state == "pending"}}, state, turn, req)
                    return
                if parent.mode == "revoked":
                    parent.allow = False
                msg = {"role": "assistant", "content": "Result 世界"}
                finish = "stop"
                if parent.mode == "tools" or parent.mode in {"native-conversation", "native-effect-disconnect"} and len(parent.calls) == 1:
                    msg.update(content=None, tool_calls=[{"id": "tool-original", "type": "function",
                        "function": {"name": parent.tool_name, "arguments": json.dumps(parent.tool_arguments)}}])
                    finish = "tool_calls"
                if parent.mode.startswith("structured"):
                    msg.update(content="preamble" if parent.mode == "structured-preamble" else None,
                        tool_calls=[{"id": "structured-original", "type": "function", "function": {
                            "name": "mmx_hermes_structured_result", "arguments": json.dumps(parent.structured_value)}}])
                    if parent.mode == "structured-many":
                        msg["tool_calls"].append({"id": "structured-second", "type": "function", "function": {
                            "name": "mmx_hermes_structured_result", "arguments": json.dumps(parent.structured_value)}})
                    finish = "tool_calls"
                self.reply(200, {"id": "provider-result", "model": parent.serving_model,
                    "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 7}}, "terminal", turn, req)
                parent.response_finished.set()

            def reply(self, status, payload, state, turn, req):
                if parent.auto_inspection is not None and req is not None and status == 200:
                    from engine.fabric_inference_client import _auto_request_digest, AUTO_SCHEMA
                    original = parent.calls[-1]["payload"]
                    scope = parent.auto_inspection
                    exact = scope["schema"] == "mastermind.fabric_application_inspection.v3"
                    routing = dict(schema="mastermind.fabric_application_route.v2" if exact else "mastermind.fabric_application_route.v1",
                        requested_model=scope["requested_model"],
                        route_scope=scope["route_scope"], route_scope_digest=scope["route_scope_digest"],
                        selection_digest="a" * 64, request_digest=_auto_request_digest(original),
                        routed_request_digest=None if exact else _auto_request_digest(dict(original, model=parent.serving_model)),
                        pool="go", selected_model=scope["requested_model"] if exact else parent.serving_model,
                        mode="fixture-mode", protocol="chat",
                        driver="fixture-driver", profile="fixture-profile", source="fixture-source", recipe_digest=None,
                        output_contract={"mode": "hard_maximum", "max_tokens": original["max_tokens"]})
                    routing.update(parent.route_overrides)
                    payload["application"] = dict(schema=AUTO_SCHEMA, disposition=state, turn_id=turn,
                        request_id=req, dispatch_permitted=False, effect_unknown=False, routing=routing,
                        serving_model=parent.serving_model, usage={"input_tokens": 11, "output_tokens": 7})
                def _header(value):
                    # Defense in depth: fixture-derived header values must
                    # never carry CR/LF into a response header.
                    return str(value).replace("\r", "").replace("\n", "")

                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-MM-Application-Disposition", _header(state))
                if turn is not None:
                    self.send_header("X-MM-Application-Turn-ID", _header(turn))
                if req is not None:
                    self.send_header("X-MM-Application-Request-ID", _header(req))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.owner = FabricInferenceClient(base_url=f"http://127.0.0.1:{self.server.server_port}/v1",
            proxy_token="t" * 40, model="model-1", protocol=NATIVE_PROTOCOL, operation_id="owner-turn-1")
        # Fixture injection only. The production constructor requires an enrolled
        # APPLICATION factory; no fixture identity is presented as qualification.
        self.binding = object.__new__(ApplicationBinding)
        self.binding._owner = self.owner
        self.binding.operation_id, self.binding.session_id, self.binding.turn_id = "owner-turn-1", "session-1", "turn-1"
        self.binding.model, self.binding.requested_model = "model-1", "host-selection"
        self.binding._authorized = lambda _: self.allow
        self.binding._max_output_tokens = 4096
        self.binding.automatic = False
        self.call = NativeCall("session-1", "task-1", "turn-1", "api-1")

    def tearDown(self):
        self.response_release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def invoke(self, call=None, **extra):
        with call_scope(self.binding, call or self.call):
            return HermesApplicationClient().chat.completions.create(model="host-selection",
                messages=[{"role": "user", "content": "Read"}], **extra)

    def test_authenticated_original_request_and_served_usage(self):
        result = self.invoke()
        self.assertEqual(result.model, "model-1")
        self.assertEqual(result.usage.total_tokens, 18)
        self.assertTrue(self.calls[0]["authenticated"])
        self.assertEqual(self.calls[0]["turn_id"], "owner-turn-1")
        self.assertEqual(self.calls[0]["request_id"], self.binding.request_id(self.call))

    def test_final_native_request_cannot_expand_host_output_ceiling(self):
        self.binding._max_output_tokens = 128
        for extra in ({"max_tokens": 129}, {"max_completion_tokens": 129}, {}):
            with self.subTest(extra=extra), self.assertRaises(HermesFabricError):
                self.invoke(**extra)
        self.assertEqual(self.calls, [])
        self.invoke(max_completion_tokens=128)
        self.assertEqual(self.calls[0]["payload"]["max_tokens"], 128)

    def test_rebuilt_facade_cannot_replay_completed_request(self):
        self.invoke()
        with self.assertRaises(HermesFabricError):
            self.invoke()
        self.assertEqual(len(self.calls), 1)

    def test_disconnect_does_not_replay_on_rebuilt_client(self):
        self.mode = "disconnect"
        for _ in range(2):
            with self.assertRaises(HermesFabricError) as raised:
                self.invoke()
            self.assertTrue(raised.exception.effect_unknown)
        self.assertEqual(len(self.calls), 1)

    def test_owner_proven_429_is_not_adapter_failover(self):
        self.mode = "429-refused"
        for _ in range(2):
            with self.assertRaises(HermesFabricError) as raised:
                self.invoke()
            self.assertFalse(raised.exception.effect_unknown)
            self.assertIsNone(raised.exception.__context__)
            self.assertIsNone(raised.exception.__cause__)
        self.assertEqual(len(self.calls), 1)

    def test_pending_owner_receipt_retains_uncertainty(self):
        self.mode = "pending"
        with self.assertRaises(HermesFabricError) as raised:
            self.invoke()
        self.assertTrue(raised.exception.effect_unknown)

    def test_native_tool_followup_history_and_distinct_identity(self):
        self.mode = "tools"
        result = self.invoke(tools=[{"type": "function", "function": {"name": "read", "parameters": {}}}])
        self.assertEqual(result.choices[0].message.tool_calls[0].id, "tool-original")
        self.mode = "text"
        with call_scope(self.binding, NativeCall("session-1", "task-1", "turn-1", "api-2")):
            final = HermesApplicationClient().create(model="host-selection", messages=[
                {"role": "user", "content": "Read"}, result.choices[0].message.model_dump(),
                {"role": "tool", "tool_call_id": "tool-original", "content": "original file value"}])
        self.assertEqual(final.choices[0].message.content, "Result 世界")
        self.assertNotEqual(self.calls[0]["request_id"], self.calls[1]["request_id"])
        self.assertEqual(self.calls[1]["payload"]["messages"][-1]["content"], "original file value")

    def test_unoffered_or_forbidden_tool_is_not_delivered(self):
        self.mode = "tools"
        with self.assertRaises(HermesFabricError):
            self.invoke()
        self.assertEqual(len(self.calls), 1)

    def test_native_sdk_deadline_cannot_be_tighter_than_bound_owner(self):
        with self.assertRaises(HermesFabricError):
            self.invoke(timeout=1)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.invoke(timeout=900).model, "model-1")
        self.assertNotIn("timeout", self.calls[0]["payload"])

    def test_forced_tool_choice_cannot_be_answered_with_text(self):
        with self.assertRaises(HermesFabricError):
            self.invoke(tools=[{"type": "function", "function": {"name": "read", "parameters": {}}}],
                        tool_choice="required")
        self.assertEqual(len(self.calls), 1)

    def test_unbound_revoked_wrong_session_and_selection_before_dispatch(self):
        with self.assertRaises(HermesFabricError):
            HermesApplicationClient().create(model="model-1", messages=[])
        self.allow = False
        with self.assertRaises(HermesFabricError):
            self.invoke()
        self.allow = True
        with self.assertRaises(HermesFabricError):
            self.invoke(NativeCall("other-session", "task-1", "turn-1", "api-1"))
        with call_scope(self.binding, self.call), self.assertRaises(HermesFabricError):
            HermesApplicationClient().create(model="unauthorized-model", messages=[])
        self.assertEqual(self.calls, [])

    def test_late_revocation_prevents_tool_delivery(self):
        self.mode = "revoked"
        with self.assertRaises(HermesFabricError):
            self.invoke()
        self.assertEqual(len(self.calls), 1)

    def test_facade_close_is_not_turn_cancellation(self):
        facade = HermesApplicationClient()
        facade.close()
        self.assertEqual(self.closed, 0)
        with call_scope(self.binding, self.call), self.assertRaises(HermesFabricError):
            facade.create(model="host-selection", messages=[])
        self.invoke()
        receipt = self.binding.close()
        self.assertTrue(receipt["closed"])
        self.assertEqual(self.binding.close(), receipt)
        self.assertEqual(self.closed, 1)

    def test_context_propagation_and_failed_middleware_deny(self):
        mw = execution_middleware(lambda _: self.binding)
        args = dict(session_id="session-1", task_id="task-1", turn_id="turn-1", api_request_id="api-1", provider=PROVIDER)
        req = {"model": "host-selection", "messages": [{"role": "user", "content": "x"}]}
        got = []
        def next_call(request):
            ctx = copy_context()
            t = threading.Thread(target=lambda: got.append(ctx.run(HermesApplicationClient().create, **request)))
            t.start()
            t.join(2)
            return got[0]
        self.assertEqual(mw(request=req, next_call=next_call, **args).model, "model-1")
        def broken(_):
            raise RuntimeError("private owner error")
        with self.assertRaises(HermesFabricError):
            execution_middleware(broken)(request=req, next_call=lambda p: HermesApplicationClient().create(**p), **args)
        self.assertEqual(len(self.calls), 1)

    def test_unsupported_requests_never_touch_provider(self):
        for extra in [dict(stream=True), dict(response_format={"type": "json_schema"}), dict(max_tokens=999999)]:
            with self.subTest(extra=extra), self.assertRaises(HermesFabricError):
                self.invoke(**extra)
        self.assertEqual(self.calls, [])

    def test_binding_rejects_generic_provider_and_unknown_restore(self):
        with self.assertRaises(HermesFabricError):
            ApplicationBinding(N(), operation_id="op", session_id="s", turn_id="t", model="m",
                requested_model="m", authorized=lambda _: True)
        with self.assertRaises(HermesFabricError):
            ApplicationBinding.from_factory(None, profile_id="mmmeta", operation_id="op", session_id="s",
                turn_id="t", requested_model="m", authorized=lambda _: True, prior_admission_possible=True)

    def test_native_error_classification_is_terminal(self):
        result = classify_error(HermesFabricError("hermes_fabric_owner_refused", effect_unknown=True))
        self.assertFalse(result["retryable"])
        self.assertFalse(result["should_fallback"])
        self.assertFalse(classify_error(TimeoutError("watchdog"))["retryable"])
        self.assertFalse(classify_error(ValueError("local protocol"))["should_fallback"])


if __name__ == "__main__":
    unittest.main()
