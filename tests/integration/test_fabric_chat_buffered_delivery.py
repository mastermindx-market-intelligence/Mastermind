"""Actual Mastermind chat -> loaded Macro wrapper -> native B/A, buffered.

The paired CI copy owns synthetic configuration. The incumbent native fixture
owns real HTTP/SQLite/leases with loopback-only synthetic upstream responses.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from brain import advisor, bot_mcp, fabric_chat, fabric_inference, thinking_log


MODEL = "fixture-model"
THESIS = {"subject": "TEST", "lean": "watch", "thesis": "A falsifiable observation."}


def tool(ident="proposal-1", **extra):
    return {"id": ident, "type": "function", "function": {
        "name": "mcp__bot__propose_thesis", "arguments": json.dumps({**THESIS, **extra})}}


def packet(text="Grounded final response.", *, calls=()):
    message = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = list(calls)
    return {"model": MODEL, "choices": [{"index": 0, "message": message,
        "finish_reason": "tool_calls" if calls else "stop"}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7}}


class BufferedNativeChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("MM_REQUIRE_FABRIC_COMPOSITION") != "1":
            raise unittest.SkipTest("required paired Fabric composition step")
        cls.owner, cls.shared, cls.macro_root = fabric_inference._owner()
        import bot
        expected = Path(os.environ["MM_FABRIC_FIXTURE_ROOT"]).resolve()
        if (cls.macro_root != expected or bot._VENDOR.resolve() != expected
                or not (expected / ".fabric-composition-fixture").is_file()):
            raise AssertionError("disposable actual Macro source required")
        cls.config_paths = [expected / "config" / name for name in (
            "provider_production_modes.v1.json", "capability_manifest.yml")]
        cls.originals = {p: p.read_bytes() for p in cls.config_paths}
        root = Path(__file__).resolve().parents[2] / "ops/native_fabric/quota_continuity"
        cls.original_path = list(sys.path)
        sys.path[:0] = [str(root / name) for name in ("tests", "candidate", "source")]
        for name in ("lease_broker", "go_lease_gateway", "go_lease_capability"):
            loaded = sys.modules.get(name)
            if loaded is not None and Path(loaded.__file__).resolve() != root / "candidate" / (name + ".py"):
                raise AssertionError("foreign native fixture module")
        spec = importlib.util.spec_from_file_location("_buffered_native_http_fixture",
            root / "tests/test_go_application_handler_composition.py")
        cls.native_module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.native_module
        spec.loader.exec_module(cls.native_module)

    @classmethod
    def tearDownClass(cls):
        for path, raw in cls.originals.items():
            path.write_bytes(raw)
        sys.path[:] = cls.original_path
        sys.modules.pop("_buffered_native_http_fixture", None)

    def start(self, patcher):
        self.addCleanup(patcher.stop)
        return patcher.start()

    def setUp(self, *, service_mode_id="mastermind_chat_fabric"):
        import yaml
        from engine.fabric_inference_client import NATIVE_PROTOCOL

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.native = self.native_module.NativeApplicationHTTPFixture()
        self.native.setUp()
        self.addCleanup(self.native.doCleanups)
        transport = self.owner._ApplicationFabricTransport(
            f"http://127.0.0.1:{self.native.server.server_port}/v1",
            self.native.service.credential_ref, "go", MODEL, "unknown",
            "fabric:go_mastermind_chat", "fabric_application_go_mastermind_chat",
            qualified=True, application_allowed=True, protocol=NATIVE_PROTOCOL,
            metadata_read=False)
        self.start(patch.dict(self.owner._APPLICATION_FABRIC_TRANSPORTS, {
            "native_go_mastermind_chat_v1": transport}))
        row = {key: getattr(transport, key) for key in self.owner._APPLICATION_IDENTITY_FIELDS}
        row.update(transport_id="native_go_mastermind_chat_v1", enabled=True, application_allowed=True,
                   qualification=self.owner.PROFILE_QUALIFIED_CANARY,
                   qualification_ref="fixture:buffered-source-only", qualified_until=time.time()+3600)
        document = json.loads(self.originals[self.config_paths[0]])
        document["application_fabric_modes"] = {"mastermind_chat_fabric": row}
        self.config_paths[0].write_text(json.dumps(document))
        self.config_paths[1].write_text(yaml.safe_dump({"capabilities": [{
            "capability_id": "fabric_application_go_mastermind_chat",
            "secret_ref": self.native.service.credential_ref,
            "kill_state": "active", "allowed_lanes": ["mastermind-chat"]}]}))
        self.start(patch.dict(os.environ, {
            "BOT_LLM_BACKEND": "fabric", "MM_PROVIDER_APPLICATION_MODE": "shared_fabric",
            "MM_PROVIDER_WORKLOAD_PROFILE": "site_interactive",
            self.native.service.credential_ref: self.native.service.credential,
            "AI_COSTS_STATE_ROOT": str(self.root / "costs"),
            "PROVIDER_HEALTH_PATH": str(self.root / "health.jsonl"),
        }))
        for name, value in (("_ROOT", self.root), ("_HISTORY", self.root / "history"),
                            ("_SESSIONS", self.root / "sessions.json")):
            self.start(patch.object(advisor, name, value))
        for name, value in (("_ROOT", self.root), ("_PROPOSALS", self.root / "proposals.jsonl"),
                            ("_RESEARCH", self.root / "research")):
            self.start(patch.object(bot_mcp, name, value))
        self.start(patch.object(self.shared._FabricMessages, "stream", side_effect=AssertionError("upstream stream")))
        self.start(patch.object(self.shared, "_oauth_pool_candidates", side_effect=AssertionError("legacy pool")))
        self.logs, self.closes = [], []
        self.start(patch.object(thinking_log, "log_turn_async", side_effect=lambda **kw: self.logs.append(kw)))
        real_close = self.shared.close_fabric_provider
        def close(provider):
            self.closes.append(provider)
            return real_close(provider)
        self.start(patch.object(self.shared, "close_fabric_provider", side_effect=close))

    def stream(self, **kwargs):
        return fabric_chat.chat_stream("Explain the observation.", conversation_id="chat-1",
                                       turn_id="turn-1", **kwargs)

    def events(self, **kwargs):
        async def collect():
            return [event async for event in self.stream(**kwargs)]
        return asyncio.run(collect())

    def document(self):
        return json.loads(advisor._hist_path("chat-1").read_text())

    def costs(self):
        return [json.loads(line) for p in (self.root / "costs").rglob("*.jsonl")
                for line in p.read_text().splitlines()]

    def test_tool_only_then_final_uses_one_native_turn_and_releases_original_lease(self):
        plans = [packet(None, calls=[tool()]), packet()]
        self.native.on_upstream = lambda: setattr(self.native, "response", plans.pop(0))
        events = self.events()
        self.assertEqual(events[-1]["type"], "done", events)
        self.assertEqual([e["text"] for e in events if e["type"] == "text"], ["Grounded final response."])
        self.assertEqual(len(self.native.posts), 2)
        self.assertTrue(all(json.loads(post[1])["stream"] is False for post in self.native.posts))
        requests = self.native.rows("application_requests")
        operation = self.document()["turns"][0]["operation_id"]
        self.assertEqual([r["request_id"] for r in requests], [operation+":brain:0", operation+":brain:1"])
        self.assertEqual({r["turn_id"] for r in requests}, {operation})
        self.assertEqual(len(self.native.rows("leases")), 1)
        self.assertEqual(self.native.rows("leases")[0]["state"], "released")
        self.assertEqual(len(self.closes), 1)
        self.assertEqual(len(self.costs()), 2)
        self.assertEqual(events[-1]["usage"]["input_tokens"], 22)

    def test_invalid_second_tool_exposes_no_prose_and_executes_no_first_tool(self):
        self.native.response = packet("Unvalidated narration.", calls=[tool(), tool("bad-2", source="forged")])
        events = self.events()
        self.assertEqual(events[-1]["type"], "error", events)
        self.assertFalse(any(e["type"] in {"text", "tool", "done"} for e in events))
        self.assertFalse(bot_mcp._PROPOSALS.exists())
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.costs()), 1)
        self.assertEqual(len(self.closes), 1)

    def cancel_original(self, *, terminal_error=False):
        self.native.block = threading.Event()
        if terminal_error:
            self.native.response_status = 503
            self.native.response["model"] = "other-model"
        async def exercise():
            loop = asyncio.get_running_loop()
            loop_errors = []
            original_handler = loop.get_exception_handler()
            loop.set_exception_handler(lambda _loop, context: loop_errors.append(context))
            stream = self.stream()
            self.assertEqual((await anext(stream))["type"], "start")
            waiting = asyncio.create_task(anext(stream))
            try:
                self.assertTrue(await asyncio.to_thread(self.native.arrived.wait, 2))
                waiting.cancel()
                await asyncio.sleep(0)
                waiting.cancel()
                await asyncio.sleep(0.02)
                self.assertFalse(waiting.done())
                self.assertFalse(self.closes)
                self.native.block.set()
                with self.assertRaises(asyncio.CancelledError):
                    await waiting
                await asyncio.sleep(0)
                self.assertFalse(loop_errors, loop_errors)
            finally:
                self.native.block.set()
                try:
                    # A failed arrival assertion still owns the outstanding
                    # anext task. Reap it before closing its async generator.
                    if not waiting.done():
                        waiting.cancel()
                    await asyncio.gather(waiting, return_exceptions=True)
                    await stream.aclose()
                finally:
                    loop.set_exception_handler(original_handler)
        asyncio.run(exercise())
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.costs()), 1)
        self.assertEqual(self.costs()[0]["model"], "other-model" if terminal_error else MODEL)
        self.assertEqual(len(self.closes), 1)
        self.assertEqual(self.logs[-1]["input_tokens"], 11)
        self.assertEqual(self.document()["turns"][0]["steps"][0]["state"], "pending")
        self.assertFalse(bot_mcp._PROPOSALS.exists())

    def test_repeated_cancellation_observes_original_provider_before_close(self):
        self.cancel_original()

    def test_original_error_after_cancellation_keeps_usage_and_cancellation(self):
        self.cancel_original(terminal_error=True)

    def test_close_at_final_text_has_durable_receipt_and_close_does_not_block_loop(self):
        started, release = threading.Event(), threading.Event()
        original = self.native.gateway.close_application_turn
        def close(**kwargs):
            started.set()
            if not release.wait(2):
                raise AssertionError("event loop could not release close")
            return original(**kwargs)
        async def exercise():
            stream = self.stream()
            await anext(stream)
            self.assertEqual((await anext(stream))["type"], "text")
            self.assertEqual(self.document()["turns"][0]["state"], "complete")
            closing = asyncio.create_task(stream.aclose())
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                await asyncio.sleep(0)
                self.assertFalse(closing.done())
            finally:
                release.set()
                await closing
        with patch.object(self.native.gateway, "close_application_turn", side_effect=close):
            asyncio.run(exercise())
        self.assertEqual(len(self.closes), 1)
        self.assertEqual(self.native.rows("leases")[0]["state"], "released")

    def test_close_at_tool_event_preserves_pending_action_without_handler(self):
        self.native.response = packet(None, calls=[tool()])
        async def exercise():
            stream = self.stream()
            try:
                async for event in stream:
                    if event["type"] == "tool":
                        break
            finally:
                await stream.aclose()
        asyncio.run(exercise())
        self.assertEqual(self.document()["turns"][0]["tool_effects"][0]["state"], "pending")
        self.assertFalse(bot_mcp._PROPOSALS.exists())
        self.assertEqual(len(self.closes), 1)

    def test_postbinding_persistence_failure_closes_pristine_local_binding(self):
        with patch.object(advisor, "save_fabric_conversation", side_effect=OSError("fixture store failure")):
            events = self.events()
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(len(self.closes), 1)
        self.assertFalse(self.native.posts)
        self.assertFalse(self.native.rows("leases"))

    def test_terminal_save_failure_has_no_visible_text_or_reissue(self):
        original = advisor.save_fabric_conversation
        def save(doc):
            if doc["turns"][0]["state"] == "complete":
                raise advisor.FabricConversationError("fabric_conversation_persistence_failed")
            return original(doc)
        with patch.object(advisor, "save_fabric_conversation", side_effect=save):
            events = self.events()
        self.assertFalse(any(e["type"] in {"text", "done"} for e in events))
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.closes), 1)
        self.assertEqual(self.events()[-1]["error"], "fabric_conversation_unsettled")
        self.assertEqual(len(self.native.posts), 1)
