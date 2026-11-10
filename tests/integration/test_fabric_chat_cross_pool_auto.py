"""Real AUTO advisor composition and existing conversation recovery.

Actual shared C, native B and SQLite A are exercised over loopback HTTP.
Only service qualification/grants and the upstream model response are fixtures.
"""
from __future__ import annotations

import asyncio
import copy
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from brain import advisor, bot_mcp, fabric_chat

_spec = importlib.util.spec_from_file_location("_advisor_auto_text_helpers",
    Path(__file__).with_name("test_fabric_text_cross_pool_auto.py"))
_text_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_text_helpers)
_fixed = _text_helpers._helpers

# The seven read objects the cognition owner already publishes, under the
# cognition owner's own namespace. The AUTO route joins them to the incumbent
# bot roster; it does not create a second authority.
COGNITION_NAMES = [
    "mcp__cognition__get_market_packet",
    "mcp__cognition__get_prophet_board",
    "mcp__cognition__get_sector_rotation",
    "mcp__cognition__get_technical_lab",
    "mcp__cognition__get_context_catalog",
    "mcp__cognition__get_surface_packet",
    "mcp__cognition__get_neural_web_packet",
]


def cognition_call(ident="cognition-1", name="get_context_catalog", args=None):
    return {"id": ident, "type": "function", "function": {
        "name": "mcp__cognition__" + name,
        "arguments": json.dumps({} if args is None else args)}}


class AutoAdvisorApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _text_helpers.AutoTextApplicationTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        _text_helpers.AutoTextApplicationTests.tearDownClass.__func__(cls)

    start = _text_helpers.AutoTextApplicationTests.start
    costs = _text_helpers.AutoTextApplicationTests.costs
    configure = _text_helpers.AutoTextApplicationTests.configure
    stream = _fixed.BufferedNativeChatTests.stream
    events = _fixed.BufferedNativeChatTests.events
    document = _fixed.BufferedNativeChatTests.document

    def setUp(self):
        import yaml
        _text_helpers.AutoTextApplicationTests.setUp(self)
        for name, value in (("_ROOT", self.root), ("_HISTORY", self.root / "history"),
                            ("_SESSIONS", self.root / "sessions.json")):
            self.start(patch.object(advisor, name, value))
        for name, value in (("_ROOT", self.root), ("_PROPOSALS", self.root / "proposals.jsonl"),
                            ("_RESEARCH", self.root / "research")):
            self.start(patch.object(bot_mcp, name, value))
        self.start(patch.object(self.shared._FabricMessages, "stream",
                                side_effect=AssertionError("upstream stream")))
        for grant in self.native.document["application_grants"]:
            grant.update(principal_id="mastermind-chat", admission_root="service:mastermind-chat",
                         workloads=["site_interactive"])
        self.native.save()
        base = self.owner._APPLICATION_FABRIC_TRANSPORTS["native_fabric_mastermind_chat_auto_v1"]
        self.chat_transport = replace(base, secret_ref="MACRO_APPLICATION_TOKEN",
                                      qualified=True, application_allowed=True)
        self.config_paths[1].write_text(yaml.safe_dump({"capabilities": [{
            "capability_id": base.capability_id, "secret_ref": "MACRO_APPLICATION_TOKEN",
            "kill_state": "active", "allowed_lanes": ["mastermind-chat"]}]}))
        self.configure_chat(["go"])
        self.native.response = _fixed.packet()

    def configure_chat(self, pools):
        native = self.native
        scope = {"schema": "mastermind.application_route_scope.v1", "pools": sorted(pools)}
        service = native.go.ApplicationServiceBinding("mastermind-chat", "vps", "site_interactive",
            "MACRO_APPLICATION_TOKEN", self.native_module.SERVICE_TOKEN,
            selection_purpose=native.go.ApplicationSelectionPurpose(native.purposes["go"]),
            route_scope=native.go.ApplicationRouteScope(scope))
        native.server.shutdown()
        native.server.server_close()
        native.server = native.go.make_server(native.router, lease_gateway=native.gateway,
            application_services=(service,), application_http_binding=native.http_binding,
            application_native_bindings=(native.native_binding,), worker_capabilities_enabled=False)
        native.server.handle_error = lambda *args: None
        native._serve(native.server)
        selected = replace(self.chat_transport,
            base_url=f"http://127.0.0.1:{native.server.server_port}/v1")
        self.start(patch.dict(self.owner._APPLICATION_FABRIC_TRANSPORTS,
                             {"native_fabric_mastermind_chat_auto_v1": selected}))
        row = {key: getattr(selected, key) for key in self.owner._APPLICATION_IDENTITY_FIELDS}
        row.update(transport_id="native_fabric_mastermind_chat_auto_v1", route_scope=scope,
            enabled=True, application_allowed=True, qualification=self.owner.PROFILE_QUALIFIED_CANARY,
            qualification_ref="fixture:auto-advisor-real-owners", qualified_until=time.time()+3600)
        document = json.loads(self.originals[self.config_paths[0]])
        document["application_fabric_modes"] = {"mastermind_chat_fabric": row}
        self.config_paths[0].write_text(json.dumps(document))
        self.scope = scope

    def test_rich_tool_turn_freezes_actual_route_and_closes_before_public_answer(self):
        self.configure_chat(["codex-native", "go"])
        plans = [_fixed.packet("Researching.", calls=[_fixed.tool()]), _fixed.packet("Final evidence.")]
        self.native.on_upstream = lambda: setattr(self.native, "response", plans.pop(0))
        observed = []
        original_tool = bot_mcp.invoke_inference_tool
        async def invoke(call, *, provenance):
            observed.append(copy.deepcopy(provenance))
            return await original_tool(call, provenance=provenance)
        with patch.object(bot_mcp, "invoke_inference_tool", side_effect=invoke):
            events = self.events()
        self.assertEqual(events[-1]["type"], "done", events)
        self.assertEqual([e["text"] for e in events if e["type"] == "text"],
                         ["Researching.Final evidence."])
        done = events[-1]
        self.assertEqual((done["provider"], done["model"]), ("go", _fixed.MODEL))
        turn = self.document()["turns"][0]
        self.assertEqual(turn["schema"], "mastermind.advisor.fabric_turn.v2")
        self.assertIsNone(turn["model"])
        self.assertIsNone(turn["provider"])
        self.assertEqual(turn["close"], {"disposition": "closed", "closed": True,
                                        "effect_unknown": False, "attempted": True})
        self.assertEqual(len(self.native.posts), 2)
        self.assertEqual(self.native.dispatches, [])
        self.assertEqual(len(self.native.rows("leases")), 1)
        first, second = turn["steps"]
        self.assertNotEqual(first["normalized_request_digest"], second["normalized_request_digest"])
        self.assertEqual(first["observation"]["routing"]["selection_digest"],
                         second["observation"]["routing"]["selection_digest"])
        self.assertEqual(observed, [{"provider": "go", "model": _fixed.MODEL, "turn_id": "turn-1"}])
        sent = [json.loads(post[1]) for post in self.native.posts]
        self.assertEqual(sent[1]["messages"][-1]["role"], "tool")
        self.assertTrue(sent[1]["tools"])
        self.assertEqual(len(self.closes), 1)
        self.assertEqual(len(self.costs()), 2)
        self.assertTrue(all(row["est_cost_usd"] is None for row in self.costs()))
        public = json.dumps(advisor.load_history("chat-1"))
        for private in ("inspection", "route_scope", "selection_digest", "normalized_request_digest"):
            self.assertNotIn(private, public)

    def test_completed_original_replays_before_configuration_or_accounting(self):
        first = self.events()
        self.assertEqual(first[-1]["type"], "done", first)
        self.config_paths[0].write_text("{}")
        with patch.object(fabric_chat, "_bind", side_effect=AssertionError("rebind")), \
                patch.object(self.shared, "_capture_usage", side_effect=AssertionError("duplicate ledger")):
            replay = self.events(recover_only=True)
        self.assertTrue(replay[-1]["replayed"])
        self.assertEqual((replay[-1]["provider"], replay[-1]["model"]), ("go", _fixed.MODEL))
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.costs()), 1)

    def test_cognition_read_round_freezes_the_actual_auto_route_and_closes_before_publication(self):
        from brain import portfolio_intelligence

        catalog = {"schema": "mastermind.portfolio_intelligence.catalog/v1",
                   "surfaces": [{"id": "radar", "status": "fresh"}]}
        plans = [_fixed.packet("Reading the catalog.", calls=[cognition_call()]),
                 _fixed.packet("Catalog read; it carries no trade authority.")]
        self.native.on_upstream = lambda: setattr(self.native, "response", plans.pop(0))
        observed = []
        original_tool = bot_mcp.invoke_inference_tool
        async def invoke(call, *, provenance):
            observed.append(copy.deepcopy(provenance))
            return await original_tool(call, provenance=provenance)
        with patch.object(bot_mcp, "invoke_inference_tool", side_effect=invoke), \
                patch.object(portfolio_intelligence, "context_catalog", lambda: catalog):
            events = self.events()
        self.assertEqual(events[-1]["type"], "done", events)
        self.assertEqual([e["text"] for e in events if e["type"] == "text"],
                         ["Reading the catalog.Catalog read; it carries no trade authority."])
        done = events[-1]
        self.assertEqual((done["provider"], done["model"]), ("go", _fixed.MODEL))
        turn = self.document()["turns"][0]
        self.assertEqual(turn["schema"], "mastermind.advisor.fabric_turn.v2")
        self.assertEqual(turn["close"], {"disposition": "closed", "closed": True,
                                         "effect_unknown": False, "attempted": True})
        # The cognition read ran once, under the same frozen original route.
        self.assertEqual(observed, [{"provider": "go", "model": _fixed.MODEL, "turn_id": "turn-1"}])
        self.assertEqual(turn["tool_effects"][0]["name"], "mcp__cognition__get_context_catalog")
        self.assertEqual(turn["tool_effects"][0]["state"], "complete")
        self.assertEqual(len(self.native.posts), 2)
        self.assertEqual(self.native.dispatches, [])
        self.assertEqual(len(self.native.rows("leases")), 1)
        sent = [json.loads(post[1]) for post in self.native.posts]
        self.assertEqual(sent[1]["messages"][-1]["role"], "tool")
        self.assertEqual(len(sent[0]["tools"]), 32)
        sent_names = set()
        for tool in sent[0]["tools"]:
            sent_names.add(tool.get("name") or tool.get("function", {}).get("name"))
        self.assertIn("mcp__cognition__get_context_catalog", sent_names)
        self.assertEqual(len(self.closes), 1)
        self.assertEqual(len(self.costs()), 2)
        self.assertEqual([event["type"] for event in events if event["type"] == "paper"], [])

    def test_late_invalid_cognition_call_prevents_the_earlier_business_handler(self):
        from brain import portfolio_intelligence

        self.native.response = _fixed.packet("Reading the catalog.", calls=[
            _fixed.tool(),
            cognition_call("bad-2", args={"source": "forged"}),
        ])
        with patch.object(portfolio_intelligence, "context_catalog",
                          lambda: {"surfaces": []}):
            events = self.events()
        self.assertEqual(events[-1]["type"], "error", events)
        self.assertEqual(events[-1]["error"], "fabric_tool_arguments_invalid")
        # The whole completed batch is refused before any handler side effect.
        self.assertFalse(bot_mcp._PROPOSALS.exists())
        self.assertEqual(self.document()["turns"][0]["tool_effects"], [])
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.costs()), 1)
        self.assertEqual(len(self.closes), 1)

    def test_rich_chat_cannot_be_flattened_into_plaintext_native_harness(self):
        self.configure_chat(["codex-native"])
        events = self.events()
        self.assertEqual(events[-1]["type"], "error", events)
        self.assertFalse(self.native.posts)
        self.assertFalse(self.native.dispatches)
        self.assertFalse(self.native.rows("leases"))
        self.assertFalse(any(e["type"] in {"text", "tool", "done"} for e in events))

    def test_terminal_unusable_answer_keeps_actual_usage_and_remains_held(self):
        self.native.response["model"] = "observed-other"
        events = self.events()
        self.assertEqual(events[-1]["type"], "error", events)
        self.assertFalse(any(e["type"] in {"text", "done"} for e in events))
        turn = self.document()["turns"][0]
        step = turn["steps"][0]
        self.assertEqual(turn["state"], "held")
        self.assertEqual(step["state"], "pending")
        self.assertEqual(step["observation"]["serving_model"], "observed-other")
        self.assertEqual(step["observed_usage"]["input_tokens"], 11)
        self.assertEqual(self.costs()[0]["model"], "observed-other")
        self.assertEqual(self.events(recover_only=True)[-1]["error"], "fabric_conversation_unsettled")
        self.assertEqual(len(self.native.posts), 1)

    def test_unknown_usage_does_not_fabricate_counts_or_prevent_valid_answer(self):
        self.native.response["usage"] = {"prompt_tokens": 11}
        events = self.events()
        self.assertEqual(events[-1]["type"], "done", events)
        self.assertEqual(events[-1]["usage"]["usage_state"], "unknown")
        self.assertIsNone(events[-1]["usage"]["output_tokens"])
        self.assertEqual(self.costs(), [])
        self.assertEqual((self.logs[-1]["provider"], self.logs[-1]["model"]), ("go", _fixed.MODEL))
        self.assertEqual(self.document()["turns"][0]["state"], "complete")

    def test_stale_prior_observation_is_not_attached_to_new_failed_step(self):
        self.native.response = _fixed.packet(None, calls=[_fixed.tool()])
        original = self.transport.FabricInferenceClient._exchange
        calls = []
        def exchange(client, path, body, headers, **kwargs):
            if path == "/v1/chat/completions":
                calls.append(path)
                if len(calls) == 2:
                    raise OSError("fixture second request transport unavailable")
            return original(client, path, body, headers, **kwargs)
        with patch.object(self.transport.FabricInferenceClient, "_exchange", exchange):
            events = self.events()
        self.assertEqual(events[-1]["type"], "error", events)
        steps = self.document()["turns"][0]["steps"]
        self.assertEqual(len(steps), 2)
        self.assertIn("observation", steps[0])
        self.assertNotIn("observation", steps[1])
        self.assertNotIn("observed_usage", steps[1])
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.costs()), 1)

    def test_malformed_route_preserves_unattributed_counts_in_original_step(self):
        handler = self.native.server.RequestHandlerClass
        original = handler._application_routed_result
        def corrupt(handler, outcome):
            result = original(handler, outcome)
            value = json.loads(result.body)
            value["application"]["routing"]["protocol"] = []
            raw = json.dumps(value, separators=(",", ":")).encode()
            return replace(result, body=raw, delivery_digest=hashlib.sha256(raw).hexdigest())
        with patch.object(handler, "_application_routed_result", corrupt):
            events = self.events()
        self.assertEqual(events[-1]["type"], "error", events)
        step = self.document()["turns"][0]["steps"][0]
        self.assertNotIn("observation", step)
        self.assertEqual(step["observed_usage"]["input_tokens"], 11)
        self.assertEqual(self.costs()[0]["provider"], "unknown")
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.closes), 1)

    def test_original_close_lost_ack_holds_answer_without_publication_or_replay(self):
        original = self.native.gateway.close_application_turn
        def close(**kwargs):
            original(**kwargs)
            raise OSError("fixture original close ACK lost")
        with patch.object(self.native.gateway, "close_application_turn", side_effect=close):
            events = self.events()
        self.assertEqual(events[-1]["type"], "error", events)
        self.assertFalse(any(e["type"] in {"text", "done"} for e in events))
        turn = self.document()["turns"][0]
        self.assertEqual(turn["state"], "held")
        self.assertIn("held_result", turn)
        self.assertFalse(turn["close"]["closed"])
        self.assertTrue(turn["close"]["effect_unknown"])
        self.assertEqual(self.events(recover_only=True)[-1]["error"], "fabric_conversation_unsettled")
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.closes), 1)

    def test_cancellation_observes_and_saves_original_response_before_unlock(self):
        self.native.block = threading.Event()
        async def exercise():
            stream = self.stream()
            await anext(stream)
            pending = asyncio.create_task(anext(stream))
            try:
                self.assertTrue(await asyncio.to_thread(self.native.arrived.wait, 2))
                pending.cancel()
                await asyncio.sleep(0)
                self.assertFalse(pending.done())
                self.native.block.set()
                with self.assertRaises(asyncio.CancelledError):
                    await pending
            finally:
                self.native.block.set()
                await stream.aclose()
        asyncio.run(exercise())
        turn = self.document()["turns"][0]
        self.assertEqual(turn["state"], "held")
        self.assertEqual(turn["steps"][0]["state"], "pending")
        self.assertEqual(turn["steps"][0]["observation"]["usage"]["input_tokens"], 11)
        self.assertTrue(turn["close"]["closed"])
        self.assertEqual(len(self.costs()), 1)
        self.assertEqual(len(self.closes), 1)

    def test_cancellation_during_close_keeps_held_answer_and_original_close(self):
        arrived, release = threading.Event(), threading.Event()
        original = self.native.gateway.close_application_turn
        def close(**kwargs):
            arrived.set()
            if not release.wait(2):
                raise AssertionError("close not released")
            return original(**kwargs)
        async def exercise():
            stream = self.stream()
            await anext(stream)
            pending = asyncio.create_task(anext(stream))
            try:
                self.assertTrue(await asyncio.to_thread(arrived.wait, 2))
                pending.cancel()
                await asyncio.sleep(0)
                self.assertFalse(pending.done())
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await pending
            finally:
                release.set()
                await stream.aclose()
        with patch.object(self.native.gateway, "close_application_turn", side_effect=close):
            asyncio.run(exercise())
        turn = self.document()["turns"][0]
        self.assertEqual(turn["state"], "held")
        self.assertTrue(turn["close"]["closed"])
        self.assertIn("held_result", turn)
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.closes), 1)

    def test_durable_receipt_corruption_refuses_before_mutable_binding(self):
        events = self.events()
        self.assertEqual(events[-1]["type"], "done", events)
        original = self.document()
        mutations = (
            lambda t: t.pop("schema"),
            lambda t: t.update(schema="mastermind.advisor.fabric_turn.v99"),
            lambda t: t["steps"][0].update(request_id="foreign"),
            lambda t: t["steps"][0].update(observation_hash="0"*64),
            lambda t: t["inspection"]["route_scope"].update(pools=["codex-native"]),
            lambda t: t["close"].update(closed=False),
            lambda t: t["result"].update(model="foreign"),
            lambda t: t.update(result=None),
            lambda t: t.update(steps=[], tool_effects=[]),
            lambda t: t["result"]["usage"].update(input_tokens=0),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                doc = copy.deepcopy(original)
                mutate(doc["turns"][0])
                advisor._hist_path("chat-1").write_text(json.dumps(doc))
                with patch.object(fabric_chat, "_bind", side_effect=AssertionError("rebind")):
                    result = self.events(recover_only=True)
                self.assertEqual(result[-1]["error"], "fabric_conversation_invalid", result)
        self.assertEqual(len(self.native.posts), 1)

    def test_persistence_failure_does_not_retry_or_publish_held_answer(self):
        original = advisor.save_fabric_conversation
        attempts = []
        def save(doc):
            if doc["turns"][0].get("close") is not None:
                attempts.append("close")
                raise advisor.FabricConversationError("fabric_conversation_persistence_failed")
            return original(doc)
        with patch.object(advisor, "save_fabric_conversation", side_effect=save):
            events = self.events()
        self.assertEqual(events[-1]["type"], "error", events)
        self.assertFalse(any(e["type"] in {"text", "done"} for e in events))
        self.assertEqual(attempts, ["close"])
        self.assertEqual(len(self.closes), 1)
        self.assertEqual(len(self.native.posts), 1)

    def test_second_cancellation_during_cleanup_preserves_first_cancellation(self):
        self.native.block = threading.Event()
        close_started, close_release = threading.Event(), threading.Event()
        original = self.native.gateway.close_application_turn
        def close(**kwargs):
            close_started.set()
            if not close_release.wait(3):
                raise AssertionError("close not released")
            return original(**kwargs)
        async def exercise():
            stream = self.stream()
            await anext(stream)
            pending = asyncio.create_task(anext(stream))
            try:
                self.assertTrue(await asyncio.to_thread(self.native.arrived.wait, 2))
                pending.cancel("first-request-cancellation")
                await asyncio.sleep(0)
                self.native.block.set()
                self.assertTrue(await asyncio.to_thread(close_started.wait, 2))
                pending.cancel("second-close-cancellation")
                await asyncio.sleep(0)
                close_release.set()
                with self.assertRaises(asyncio.CancelledError) as caught:
                    await pending
                self.assertEqual(caught.exception.args, ("first-request-cancellation",))
            finally:
                self.native.block.set()
                close_release.set()
                await stream.aclose()
        with patch.object(self.native.gateway, "close_application_turn", side_effect=close):
            asyncio.run(exercise())
        turn = self.document()["turns"][0]
        self.assertEqual(turn["state"], "held")
        self.assertTrue(turn["close"]["closed"])
        self.assertEqual(len(self.closes), 1)
        self.assertEqual(len(self.native.posts), 1)

    def test_partial_usage_mismatch_does_not_relabel_prior_known_tokens(self):
        final = _fixed.packet()
        final["model"] = "observed-other"
        final["usage"] = {"prompt_tokens": 13}
        plans = [_fixed.packet(None, calls=[_fixed.tool()]), final]
        self.native.on_upstream = lambda: setattr(self.native, "response", plans.pop(0))
        events = self.events()
        self.assertEqual(events[-1]["type"], "error", events)
        step = self.document()["turns"][0]["steps"][-1]
        self.assertEqual(step["observation"]["serving_model"], "observed-other")
        self.assertIsNone(step["observation"]["usage"]["output_tokens"])
        self.assertEqual((self.logs[-1]["provider"], self.logs[-1]["model"]), ("unknown", None))
        self.assertEqual(len(self.costs()), 1)
        self.assertEqual(self.costs()[0]["model"], _fixed.MODEL)
        self.assertEqual(len(self.native.posts), 2)

