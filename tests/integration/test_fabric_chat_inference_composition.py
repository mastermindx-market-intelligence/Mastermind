"""Actual advisor/tool/HTTP paths through the paired Macro owner and gateway.

Only provider responses, logging destinations, and business data paths are
synthetic. No production account, credentials, portfolio, or conversation is used.
"""
from __future__ import annotations

import asyncio
from contextlib import aclosing
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from brain import advisor, bot_mcp, fabric_chat

_spec = importlib.util.spec_from_file_location(
    "_paired_text_fixture", Path(__file__).with_name("test_fabric_inference_composition.py"))
_text_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_text_fixture)
MODEL = _text_fixture.MODEL
THESIS = {"subject": "TEST", "lean": "watch", "thesis": "A falsifiable observation."}


def tool_call(ident="proposal-1", name="propose_thesis", args=None):
    return {"id": ident, "type": "function", "function": {
        "name": "mcp__bot__" + name, "arguments": json.dumps(THESIS if args is None else args)}}


# The seven read objects the cognition owner already publishes, under the
# cognition owner's own namespace. The Fabric inference view joins them to the
# incumbent bot roster; it does not create a second authority.
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


def packet(text="Grounded response.", *, calls=(), usage=True):
    message = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = list(calls)
    return {"model": MODEL, "choices": [{"index": 0, "message": message,
        "finish_reason": "tool_calls" if calls else "stop"}],
        "usage": {"prompt_tokens": 19, "completion_tokens": 7} if usage else None}


class ToolBoundaryTests(unittest.TestCase):
    def test_catalog_is_exact_incumbent_roster_and_system_is_honest(self):
        catalog = bot_mcp.inference_tool_catalog()
        # The exact intended roster: the 25 incumbent bot tools plus the seven
        # cognition reads, in the derived view's order.
        self.assertEqual({row["name"] for row in catalog},
                         set(bot_mcp.TOOL_NAMES) | set(COGNITION_NAMES))
        self.assertEqual(len(catalog), 32)
        self.assertEqual(len(bot_mcp.TOOL_NAMES), 25)
        self.assertEqual(len(bot_mcp._ALL), 25)
        for name in ("recommend_action", "WebSearch", "WebFetch", "Read", "Grep", "Glob"):
            self.assertNotIn(name, {row["name"] for row in catalog})
            self.assertNotIn("mcp__bot__" + name, {row["name"] for row in catalog})
        self.assertNotIn("WebSearch", advisor.inference_system())
        self.assertNotIn("WebFetch", advisor.inference_system())

    def test_cognition_namespace_adds_no_authority_and_cannot_file_a_paper(self):
        names = {row["name"] for row in bot_mcp.inference_tool_catalog()}
        self.assertEqual(len(names), 32)
        for forbidden in ("mcp__cognition__submit_book",
                          "mcp__cognition__request_context_upgrade",
                          "mcp__cognition__get_my_book",
                          "mcp__bot__get_market_packet",
                          "mcp__bot__get_context_catalog"):
            self.assertNotIn(forbidden, names)
        # The incumbent filing handler stays the sole paper-event owner.
        marker = {"content": [{"type": "text",
                               "text": bot_mcp.PAPER_MARKER + ' {"paper_id":"x"}'}]}
        for name in COGNITION_NAMES:
            self.assertEqual(bot_mcp.tool_result_event(marker, tool_name=name),
                             {"type": "tool_result"})

    def test_cognition_calls_keep_the_published_argument_contract(self):
        def block(args, ident="valid-1", name="mcp__cognition__get_technical_lab"):
            return SimpleNamespace(id=ident, name=name, input=args)
        for args in ({}, {"ticker": "AAPL", "source": "trusted"},
                     {"ticker": "AAPL", "limit": 1.0}, {"ticker": 7}):
            with self.subTest(args=args), self.assertRaises(bot_mcp.InferenceToolError):
                bot_mcp.validate_inference_calls([block(args)])
        calls = bot_mcp.validate_inference_calls([block({"ticker": "AAPL"})])
        self.assertEqual(calls[0]["name"], "mcp__cognition__get_technical_lab")
        self.assertEqual(calls[0]["input"], {"ticker": "AAPL"})
        # An integer argument stays integer-exact for the cognition reads too.
        with self.assertRaises(bot_mcp.InferenceToolError):
            bot_mcp.validate_inference_calls([SimpleNamespace(
                id="valid-2", name="mcp__cognition__get_prophet_board",
                input={"limit": 1.0})])
        # A non-finite argument and an unsupported cognition name are refused.
        with self.assertRaises(bot_mcp.InferenceToolError):
            bot_mcp.validate_inference_calls([SimpleNamespace(
                id="valid-3", name="mcp__cognition__get_sector_rotation",
                input={"limit": float("inf")})])
        for unsupported in ("mcp__cognition__submit_book",
                            "mcp__cognition__request_context_upgrade",
                            "mcp__cognition__get_my_book",
                            "mcp__cognition__unknown_read"):
            with self.subTest(name=unsupported), self.assertRaises(bot_mcp.InferenceToolError):
                bot_mcp.validate_inference_calls([SimpleNamespace(
                    id="valid-4", name=unsupported, input={})])
        # One id ledger spans both namespaces: a repeated id is refused.
        with self.assertRaises(bot_mcp.InferenceToolError):
            bot_mcp.validate_inference_calls([
                block({"ticker": "AAPL"}, ident="shared-id"),
                SimpleNamespace(id="shared-id", name="mcp__cognition__get_context_catalog",
                                input={})])

    def test_strict_full_argument_schema_and_ids(self):
        def block(args, ident="valid-1", name="mcp__bot__propose_thesis"):
            return SimpleNamespace(id=ident, name=name, input=args)
        invalid = [{**THESIS, "source": "trusted"}, {**THESIS, "horizon_d": True},
                   {**THESIS, "horizon_d": 1.0}, {**THESIS, "evidence": [2]},
                   {**THESIS, "prob_correct": float("nan")}, {"subject": "TEST"}]
        for args in invalid:
            with self.subTest(args=args), self.assertRaises(bot_mcp.InferenceToolError):
                bot_mcp.validate_inference_calls([block(args)])
        for blocks in ([block(THESIS), block(THESIS)], [block(THESIS, ident="bad id")],
                       [block(THESIS, name="mcp__bot__recommend_action")]):
            with self.assertRaises(bot_mcp.InferenceToolError):
                bot_mcp.validate_inference_calls(blocks)
        with self.assertRaises(bot_mcp.InferenceToolError):
            bot_mcp.validate_inference_calls([block(THESIS)], used_ids={"valid-1"})

    def test_another_tool_cannot_spoof_a_paper_card(self):
        result = {"content": [{"type": "text", "text": bot_mcp.PAPER_MARKER + ' {"paper_id":"x"}'}]}
        self.assertEqual(bot_mcp.tool_result_event(result, tool_name="mcp__bot__get_news"),
                         {"type": "tool_result"})


class ChatCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _text_fixture.FabricCompositionTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        _text_fixture.FabricCompositionTests.tearDownClass.__func__(cls)

    start = _text_fixture.FabricCompositionTests.start
    save = _text_fixture.FabricCompositionTests.save
    costs = _text_fixture.FabricCompositionTests.costs

    def setUp(self):
        _text_fixture.FabricCompositionTests.setUp(self)
        self.text_mode = dict(self.mode)
        self.text_capability = dict(self.manifest["capabilities"][0])
        text_transport = self.owner._APPLICATION_FABRIC_TRANSPORTS[self.transport_id]
        transport = self.owner._ApplicationFabricTransport(
            text_transport.base_url, "TEST_FABRIC_CHAT_TOKEN",
            "actual-fixture-provider", MODEL, "unknown",
            "fabric:chat-fixture", "chat_fixture",
            qualified=True, application_allowed=True,
        )
        self.transport_id = self.owner._SERVICE_FABRIC_RELATIONS["mastermind_chat_fabric"].transport_id
        self.start(patch.dict(self.owner._APPLICATION_FABRIC_TRANSPORTS, {self.transport_id: transport}))
        self.mode = {key: getattr(transport, key) for key in self.owner._APPLICATION_IDENTITY_FIELDS}
        self.mode.update(transport_id=self.transport_id, enabled=True, application_allowed=True,
                         qualification=self.owner.PROFILE_QUALIFIED_CANARY,
                         qualification_ref="fixture:source-only",
                         qualified_until=self.text_mode["qualified_until"])
        self.document["application_fabric_modes"] = {"mastermind_chat_fabric": self.mode}
        self.manifest = {"capabilities": [{
            "capability_id": "chat_fixture", "secret_ref": "TEST_FABRIC_CHAT_TOKEN",
            "kill_state": "active", "allowed_lanes": ["mastermind-chat"],
        }]}
        self.save()
        os.environ["TEST_FABRIC_CHAT_TOKEN"] = _text_fixture.PROXY_TOKEN
        os.environ["MM_PROVIDER_WORKLOAD_PROFILE"] = "site_interactive"
        self.start(patch.object(advisor, "_ROOT", self.root))
        self.start(patch.object(advisor, "_HISTORY", self.root / "history"))
        self.start(patch.object(advisor, "_SESSIONS", self.root / "sdk_sessions.json"))
        self.start(patch.object(bot_mcp, "_ROOT", self.root))
        self.start(patch.object(bot_mcp, "_PROPOSALS", self.root / "proposals.jsonl"))
        self.start(patch.object(bot_mcp, "_RESEARCH", self.root / "research"))
        self.start(patch.object(advisor, "append_turn", side_effect=AssertionError("legacy transcript writer")))
        self.start(patch.object(advisor, "set_session", side_effect=AssertionError("SDK resume writer")))
        self.response = packet()

    def events(self, prompt="Explain the observation.", *, conv="chat-1", turn="turn-1", **kwargs):
        async def collect():
            return [event async for event in fabric_chat.chat_stream(
                prompt, conversation_id=conv, turn_id=turn, **kwargs)]
        return asyncio.run(collect())

    def conversation_document(self, conv="chat-1"):
        return json.loads(advisor._hist_path(conv).read_text())

    def test_text_service_grant_cannot_substitute_for_chat_identity(self):
        self.document["application_fabric_modes"] = {"mastermind_text_fabric": self.text_mode}
        text_capability = dict(self.text_capability, allowed_lanes=["mastermind-text", "mastermind-chat"])
        self.manifest = {"capabilities": [text_capability]}
        self.save()
        events = self.events()
        self.assertEqual(events[-1]["error"], "fabric_chat_unavailable", events)
        self.assertEqual(self.dispatches, [])
        self.assertFalse(advisor._hist_path("chat-1").exists())

    def test_tool_only_round_and_final_response_use_real_owner_and_handler_once(self):
        plans = [packet(None, calls=[tool_call()]), packet("Proposal queued; no trade was executed.")]
        self.response = lambda: plans.pop(0)
        events = self.events()
        self.assertEqual(events[-1]["type"], "done", events)
        self.assertEqual(len(self.dispatches), 2)
        first, second = [row["body"] for row in self.dispatches]
        self.assertEqual(first["model"], MODEL)
        self.assertEqual(len(first["tools"]), 32)
        self.assertFalse(first["stream"])
        self.assertEqual(second["messages"][-1]["role"], "tool")
        self.assertEqual(second["messages"][-1]["tool_call_id"], "proposal-1")
        doc = self.conversation_document()
        self.assertEqual(len(doc["turns"]), 1)
        self.assertEqual([step["request_id"].rsplit(":", 1)[-1] for step in doc["turns"][0]["steps"]], ["0", "1"])
        self.assertEqual(doc["turns"][0]["tool_effects"][0]["state"], "complete")
        proposal = json.loads(bot_mcp._PROPOSALS.read_text())
        self.assertEqual((proposal["source"], proposal["provider"], proposal["model"], proposal["turn_id"]),
                         ("fabric_application", "actual-fixture-provider", MODEL, "turn-1"))
        self.assertEqual(proposal["status"], "proposed")
        self.assertEqual(len(self.costs()), 2)
        self.assertEqual(len(advisor.load_history("chat-1")), 2)
        self.assertEqual(set(advisor.load_history("chat-1")[0]), {"role", "content", "tools", "papers", "ts"})
        self.assertEqual(self.rows[-1]["provider"], "actual-fixture-provider")

    def test_recovery_only_can_never_start_an_absent_turn(self):
        with patch.object(fabric_chat, "_bind", side_effect=AssertionError("new admission")):
            events = self.events(recover_only=True)
        self.assertEqual(events[-1]["error"], "fabric_turn_receipt_missing")
        self.assertTrue(events[-1]["unsettled"])
        self.assertFalse(advisor._hist_path("chat-1").exists())
        self.assertFalse(self.dispatches)

    def test_completed_identity_replays_receipt_without_inference_tools_or_duplicate_history(self):
        original = self.events()
        with patch.object(fabric_chat, "_bind", side_effect=AssertionError("new admission")):
            replay = self.events(recover_only=True)
            conflict = self.events("A different prompt.")
        self.assertTrue(replay[-1]["replayed"])
        self.assertEqual(replay[-1]["text"], original[-1]["text"])
        self.assertEqual(conflict[-1]["error"], "fabric_turn_identity_conflict")
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(len(advisor.load_history("chat-1")), 2)

    def test_second_turn_reuses_durable_protocol_and_has_a_new_operation(self):
        self.events()
        events = self.events("What would falsify it?", turn="turn-2")
        self.assertEqual(events[-1]["type"], "done", events)
        messages = self.dispatches[1]["body"]["messages"]
        self.assertEqual([row["role"] for row in messages], ["system", "user", "assistant", "user"])
        turns = self.conversation_document()["turns"]
        self.assertNotEqual(turns[0]["operation_id"], turns[1]["operation_id"])
        self.assertEqual(len(advisor.load_history("chat-1")), 4)

    def test_invalid_second_tool_prevents_first_business_handler(self):
        self.response = packet(None, calls=[tool_call(), tool_call("bad-2", args={**THESIS, "source": "forged"})])
        events = self.events()
        self.assertEqual(events[-1]["type"], "error", events)
        self.assertFalse(bot_mcp._PROPOSALS.exists())
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(self.conversation_document()["turns"][0]["tool_effects"], [])

    def test_cognition_read_round_uses_the_real_cognition_owner_and_frozen_route(self):
        from brain import portfolio_intelligence

        catalog = {"schema": "mastermind.portfolio_intelligence.catalog/v1",
                   "surfaces": [{"id": "radar", "status": "fresh"}]}
        plans = [packet(None, calls=[cognition_call()]),
                 packet("Catalog read; it carries no trade authority.")]
        self.response = lambda: plans.pop(0)
        with patch.object(portfolio_intelligence, "context_catalog", lambda: catalog):
            events = self.events()
        self.assertEqual(events[-1]["type"], "done", events)
        self.assertEqual(len(self.dispatches), 2)
        first, second = [row["body"] for row in self.dispatches]
        self.assertEqual(first["model"], MODEL)
        self.assertEqual(len(first["tools"]), 32)
        self.assertIn("mcp__cognition__get_context_catalog",
                      {row["function"]["name"] for row in first["tools"]})
        self.assertEqual(second["messages"][-1]["role"], "tool")
        self.assertEqual(second["messages"][-1]["tool_call_id"], "cognition-1")
        # The cognition owner's own decorated handler produced the result.
        returned = json.loads(
            json.loads(second["messages"][-1]["content"])["content"][0]["text"])
        self.assertEqual(returned, catalog)
        self.assertEqual([event["name"] for event in events if event["type"] == "tool"],
                         ["mcp__cognition__get_context_catalog"])
        self.assertEqual([event for event in events if event["type"] == "paper"], [])
        doc = self.conversation_document()
        self.assertEqual(doc["turns"][0]["tool_effects"][0]["state"], "complete")
        self.assertEqual(doc["turns"][0]["tool_effects"][0]["name"],
                         "mcp__cognition__get_context_catalog")
        self.assertEqual(len(self.costs()), 2)
        self.assertEqual(self.rows[-1]["provider"], "actual-fixture-provider")

    def test_late_invalid_cognition_call_prevents_the_earlier_business_handler(self):
        from brain import portfolio_intelligence

        self.response = packet(None, calls=[
            tool_call(),
            cognition_call("bad-2", args={"source": "forged"}),
        ])
        with patch.object(portfolio_intelligence, "context_catalog",
                          lambda: {"surfaces": []}):
            events = self.events()
        self.assertEqual(events[-1]["type"], "error", events)
        self.assertEqual(events[-1]["error"], "fabric_tool_arguments_invalid")
        # The whole completed batch is refused before any handler side effect.
        self.assertFalse(bot_mcp._PROPOSALS.exists())
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(self.conversation_document()["turns"][0]["tool_effects"], [])

    def test_completed_cognition_replay_adds_no_model_or_handler_execution(self):
        from brain import portfolio_intelligence

        plans = [packet(None, calls=[cognition_call()]), packet("Catalog read.")]
        self.response = lambda: plans.pop(0)
        with patch.object(portfolio_intelligence, "context_catalog",
                          lambda: {"surfaces": []}):
            original = self.events()
        self.assertEqual(original[-1]["type"], "done", original)
        with patch.object(fabric_chat, "_bind", side_effect=AssertionError("new admission")), \
                patch.object(bot_mcp, "invoke_inference_tool",
                             side_effect=AssertionError("replayed handler")):
            replay = self.events(recover_only=True)
        self.assertTrue(replay[-1]["replayed"])
        self.assertEqual(replay[-1]["text"], original[-1]["text"])
        # The completed receipt replays: no additional model or handler run.
        self.assertEqual(len(self.dispatches), 2)
        self.assertEqual(len(self.conversation_document()["turns"][0]["tool_effects"]), 1)

    def test_provider_tool_ids_may_repeat_in_a_distinct_completed_turn(self):
        plans = [packet(None, calls=[tool_call()]), packet("First proposal queued."),
                 packet(None, calls=[tool_call()]), packet("Second proposal queued.")]
        self.response = lambda: plans.pop(0)
        self.assertEqual(self.events()[-1]["type"], "done")
        self.assertEqual(self.events("A separate deliberate proposal.", turn="turn-2")[-1]["type"], "done")
        self.assertEqual(len(bot_mcp._PROPOSALS.read_text().splitlines()), 2)
        self.assertEqual(len(self.dispatches), 4)

    def test_tool_id_replay_within_one_operation_is_refused_before_second_effect(self):
        plans = [packet(None, calls=[tool_call()]), packet(None, calls=[tool_call()])]
        self.response = lambda: plans.pop(0)
        events = self.events()
        self.assertEqual(events[-1]["error"], "fabric_tool_request_invalid")
        self.assertEqual(len(bot_mcp._PROPOSALS.read_text().splitlines()), 1)
        self.assertEqual(len(self.dispatches), 2)

    def test_write_then_raise_preserves_pending_action_and_never_replays_on_restart(self):
        self.response = packet(None, calls=[tool_call()])
        real = bot_mcp.propose_thesis.handler
        async def write_then_raise(args):
            await real(args)
            raise RuntimeError("handler failed after write")
        with patch.object(bot_mcp.propose_thesis, "handler", side_effect=write_then_raise):
            events = self.events()
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(self.conversation_document()["turns"][0]["tool_effects"][0]["state"], "pending")
        for turn in ("turn-1", "new-turn"):
            retry = self.events(turn=turn)
            self.assertEqual(retry[-1]["error"], "fabric_conversation_unsettled")
            self.assertTrue(retry[-1]["unsettled"])
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(len(bot_mcp._PROPOSALS.read_text().splitlines()), 1)

    def test_limit_refuses_tool_before_effect_and_unknown_tokens_remain_unknown(self):
        self.response = packet(None, calls=[tool_call()], usage=False)
        events = self.events(max_turns=1)
        self.assertEqual(events[-1]["error"], "fabric_tool_budget_exhausted")
        self.assertFalse(bot_mcp._PROPOSALS.exists())
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(self.costs(), [])  # Unknown usage is not fabricated as zero.
        self.assertIsNone(self.rows[-1]["input_tokens"])

    def test_disconnect_at_tool_event_cannot_execute_a_later_handler(self):
        self.response = packet("Inspecting the observation.", calls=[tool_call()])
        async def disconnect():
            async with aclosing(fabric_chat.chat_stream("Explain the observation.",
                    conversation_id="chat-1", turn_id="turn-1")) as stream:
                async for event in stream:
                    if event["type"] == "tool":
                        return
        asyncio.run(disconnect())
        self.assertFalse(bot_mcp._PROPOSALS.exists())
        self.assertEqual(self.conversation_document()["turns"][0]["tool_effects"][0]["state"], "pending")
        self.assertEqual(self.events()[-1]["error"], "fabric_conversation_unsettled")
        self.assertEqual(len(self.dispatches), 1)

    def test_persistence_failure_after_provider_response_has_no_done_or_reissue(self):
        real = advisor.save_fabric_conversation
        def fail_terminal(doc):
            if doc["turns"][0]["steps"] and doc["turns"][0]["steps"][-1]["state"] == "complete":
                raise advisor.FabricConversationError("fabric_conversation_persistence_failed")
            real(doc)
        with patch.object(advisor, "save_fabric_conversation", side_effect=fail_terminal):
            events = self.events()
        self.assertEqual(events[-1]["error"], "fabric_conversation_persistence_failed")
        self.assertNotIn("done", [event["type"] for event in events])
        self.assertNotIn("text", [event["type"] for event in events])
        self.assertEqual(self.events()[-1]["error"], "fabric_conversation_unsettled")
        self.assertEqual(len(self.dispatches), 1)

    def test_existing_sdk_or_legacy_transcript_is_not_reused_as_fabric_protocol(self):
        advisor._SESSIONS.write_text(json.dumps({"chat-1": "sdk-secret"}))
        self.assertEqual(self.events()[-1]["error"], "fabric_conversation_backend_mismatch")
        advisor._SESSIONS.unlink()
        advisor._HISTORY.mkdir()
        advisor._hist_path("chat-1").write_text('[{"role":"user","content":"legacy"}]')
        self.assertEqual(self.events()[-1]["error"], "fabric_conversation_backend_mismatch")
        self.assertFalse(self.dispatches)

    def test_cross_process_lock_and_path_identity_are_enforced_before_inference(self):
        with advisor.fabric_conversation("chat-1", scope="portfolio_advisor"):
            self.assertEqual(self.events()[-1]["error"], "fabric_conversation_busy")
        for conv in ("../chat-1", "chat 1", "chat.1", "x" * 65):
            self.assertEqual(self.events(conv=conv)[-1]["error"], "fabric_conversation_id_invalid")
        self.assertFalse(self.dispatches)

    def test_actual_http_routes_use_one_history_writer_and_same_research_driver(self):
        from app.main import app
        from app import auth
        from fastapi.testclient import TestClient
        auth.reset_rate_buckets()
        with patch.dict(os.environ, {"MASTERMIND_AUTH_TOKEN": "synthetic-operator"}):
            # No lifespan: scheduled business jobs are outside this request proof.
            http = TestClient(app)
            denied = http.post("/chat", json={"message": "Explain the observation."})
            self.assertIn(denied.status_code, {401, 403})
            headers = {"Authorization": "Bearer synthetic-operator"}
            for path, body in (("/chat", {"message": "Question", "turn_id": "orphan"}),
                               ("/research", {"prompt": "Question", "turn_id": "orphan"})):
                auth.reset_rate_buckets()
                refused = http.post(path, headers=headers, json=body)
                self.assertEqual(refused.status_code, 400, refused.text)
            auth.reset_rate_buckets()
            response = http.post("/chat", headers=headers, json={"message": "Explain the observation.",
                "conversation_id": "chat-1", "turn_id": "turn-1"})
            self.assertEqual(response.status_code, 200, response.text)
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            self.assertEqual(events[-1]["type"], "done", events)
            history = http.get("/chat/history", params={"conversation_id": "chat-1"}).json()
            self.assertEqual(len(history["turns"]), 2)
            self.assertNotIn("steps", json.dumps(history))
            auth.reset_rate_buckets()  # Independent route case; preserve the actual auth middleware.
            result = http.post("/research", headers=headers, json={"prompt": "Explain the observation.",
                "conversation_id": "research-1", "turn_id": "turn-r1"}).json()
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["backend"], "fabric")
            self.assertIsNone(result["session_id"])
            auth.reset_rate_buckets()
            recovered = http.post("/research", headers=headers, json={"prompt": "Explain the observation.",
                "conversation_id": "research-1", "turn_id": "turn-r1", "recover_only": True}).json()
            self.assertTrue(recovered["replayed"], recovered)
            auth.reset_rate_buckets()
            mismatch = http.post("/research", headers=headers, json={"prompt": "Another question.",
                "conversation_id": "chat-1", "turn_id": "turn-r2"}).json()
            self.assertEqual(mismatch["error"], "fabric_conversation_backend_mismatch")
            auth.reset_rate_buckets()
            resume = http.post("/research", headers=headers, json={"prompt": "Question", "resume": "sdk-token"}).json()
            self.assertEqual(resume["error"], "fabric_sdk_resume_unsupported")
            self.assertEqual(len(self.dispatches), 2)
            auth.reset_rate_buckets()
            with patch.dict(os.environ, {"BOT_LLM_BACKEND": "claude"}):
                os.environ.pop("MM_PROVIDER_APPLICATION_MODE", None)
                refused = http.post("/chat", headers=headers, json={"message": "Explain the observation.",
                    "conversation_id": "chat-1", "turn_id": "turn-1", "recover_only": True})
                self.assertEqual(refused.status_code, 409, refused.text)
                self.assertEqual(refused.json()["detail"], "fabric_recovery_unavailable")
            self.assertEqual(len(self.dispatches), 2)


if __name__ == "__main__":
    unittest.main()
