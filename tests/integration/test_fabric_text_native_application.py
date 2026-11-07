"""Mastermind text availability and calls through actual Macro/native owners."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from brain import cli_bridge, client, fabric_inference


_spec = importlib.util.spec_from_file_location("_text_native_fixture_helpers",
    Path(__file__).with_name("test_fabric_chat_buffered_delivery.py"))
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)


class ApplicationSelectorTests(unittest.TestCase):
    """Pure selection tests run without the disposable Macro/native fixture."""

    def selector(self, value="shared_fabric", backend="api"):
        env = {} if value is None else {"MM_PROVIDER_APPLICATION_MODE": value}
        if backend is not None:
            env["BOT_LLM_BACKEND"] = backend
        return self.start(patch.dict(os.environ, env, clear=True))

    def start(self, patcher):
        self.addCleanup(patcher.stop)
        return patcher.start()

    def forbidden(self):
        for target, name in (
            (cli_bridge, "_cfg"), (cli_bridge, "cli_path"),
            (cli_bridge, "_subscription_env"), (cli_bridge, "_Options"),
            (client.codex_bridge, "available"),
        ):
            self.start(patch.object(target, name, side_effect=AssertionError(name)))

    def refusal(self, result):
        self.assertEqual(result, {"ok": False, "text": None, "backend": "fabric",
                                  "error": "fabric_tools_unavailable"})
        self.assertNotIn("cost_usd", result)
        self.assertNotIn("session_id", result)

    def test_selector_contract_is_presence_only_not_a_mode_label(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(cli_bridge._application_fabric_selected())
        for value in ("shared_fabric", "", "legacy", "unknown", " ", "{"):
            with self.subTest(value=value), patch.dict(os.environ,
                    {"MM_PROVIDER_APPLICATION_MODE": value}, clear=True):
                self.assertTrue(cli_bridge._application_fabric_selected())

    def test_selector_alone_fences_all_bot_modes_and_private_overrides(self):
        for bot_mode in (None, "legacy", "unknown", "", "api", "waterfall", "cli"):
            for mode in ("", "unknown", " ", "{"):
                with self.subTest(bot=bot_mode, mode=mode):
                    self.selector(mode, bot_mode)
                    self.forbidden()
                    self.start(patch.object(fabric_inference, "available", return_value=False))
                    self.assertEqual(client.backend(), "fabric")
                    self.assertFalse(client.available())
                    self.assertFalse(client.api_available())
                    self.assertFalse(cli_bridge.available())
                    for override in ("cli", "waterfall", "codex", "fabric", ""):
                        self.refusal(asyncio.run(cli_bridge._reason(
                            "u", _backend_override=override, _subscription_slots=[])))

    def test_unselected_routing_preserves_bot_config_and_explicit_overrides(self):
        with patch.dict(os.environ, {"BOT_LLM_BACKEND": "api"}, clear=True), \
                patch.object(fabric_inference, "_owner", side_effect=AssertionError("owner")):
            self.assertEqual(client.backend(), "api")
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(cli_bridge, "_cfg", return_value={"backend": "codex"}):
            self.assertEqual(client.backend(), "codex")
            self.assertEqual(cli_bridge._selected_backend("cli"), "cli")

    def test_explicit_bot_fabric_without_host_selection_remains_exclusive(self):
        self.selector(None, "fabric")
        with patch.object(fabric_inference, "call_model", return_value=(None, "held")), \
                patch.object(client, "api_available", side_effect=AssertionError("legacy")):
            self.assertEqual(client.call_model("s", "u"), (None, "held"))
            for override in ("cli", "codex", "waterfall"):
                self.refusal(asyncio.run(cli_bridge._reason(
                    "u", _backend_override=override, _subscription_slots=[])))
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(cli_bridge, "_cfg", return_value={"backend": "fabric"}), \
                patch.object(fabric_inference, "call_model", return_value=(None, "held")):
            self.assertEqual(client.call_model("s", "u"), (None, "held"))
            for override in ("cli", "codex"):
                self.refusal(asyncio.run(cli_bridge._reason(
                    "u", _backend_override=override, _subscription_slots=[])))

    def test_invalid_selected_cli_surfaces_are_effect_free(self):
        self.selector("unknown", "waterfall")
        self.forbidden()
        self.start(patch.object(cli_bridge, "_require_provider_start",
                                side_effect=AssertionError("callback")))
        self.refusal(cli_bridge.reason_sync("u", allowed_tools=["x"], mcp_servers={"custom": {}}))
        self.refusal(cli_bridge.research_sync("u", resume="old-session"))
        self.refusal(asyncio.run(cli_bridge.reason(
            "u", cwd="/private", add_dirs=["private"], allowed_tools=["Write"],
            mcp_servers={"custom": {"handler": lambda: self.fail("tool")}},
            before_provider_start=lambda: self.fail("veto"), log_run=False)))
        self.refusal(asyncio.run(cli_bridge.research("u", book="autonomous")))
        async def events():
            return [event async for event in cli_bridge.chat_stream(
                "u", resume="old", append_system="private")]
        self.assertEqual(asyncio.run(events()),
                         [{"type": "error", "error": "fabric_tools_unavailable"}])

    def test_app_reason_selected_failure_is_an_honest_refusal(self):
        self.selector("", None)
        from app.main import ReasonReq, reason
        with patch.object(cli_bridge, "_cfg", side_effect=AssertionError("config")):
            result = asyncio.run(reason(ReasonReq(prompt="u")))
        self.refusal(result)

    def test_selector_changes_after_availability_re_resolve(self):
        with patch.dict(os.environ, {"BOT_LLM_BACKEND": "waterfall"}, clear=True), \
                patch.object(cli_bridge, "available", return_value=True), \
                patch.object(fabric_inference, "available", return_value=True), \
                patch.object(fabric_inference, "call_model", return_value=("held", None)):
            self.assertTrue(client.available())
            os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
            self.assertEqual(client.call_model("s", "u"), ("held", None))
        with patch.dict(os.environ, {"MM_PROVIDER_APPLICATION_MODE": "shared_fabric",
                                     "BOT_LLM_BACKEND": "fabric"}, clear=True), \
                patch.object(fabric_inference, "available", return_value=True), \
                patch.object(cli_bridge, "reason_sync", return_value={"ok": True, "text": "legacy"}), \
                patch.object(cli_bridge, "available", return_value=True):
            self.assertTrue(client.available())
            os.environ["BOT_LLM_BACKEND"] = "waterfall"
            del os.environ["MM_PROVIDER_APPLICATION_MODE"]
            self.assertEqual(client.call_model("s", "u"), ("legacy", None))

    def test_late_option_and_guard_selection_changes_block_sdk_once(self):
        with patch.dict(os.environ, {}, clear=True):
            guards = []
            def guard():
                guards.append(1)
                os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
            opts = type("Options", (), {"__init__": lambda self, **kw: None})
            with patch.object(cli_bridge, "_Options", opts), \
                    patch.object(cli_bridge, "_subscription_env", lambda _name: {}), \
                    patch.object(cli_bridge, "_sdk_query", side_effect=AssertionError("send")):
                with self.assertRaisesRegex(cli_bridge.ProviderStartRefused, "fabric_tools_unavailable"):
                    asyncio.run(cli_bridge._via_sdk(
                        "p", "m", "pm", None, None, [], [], 1, ".", "dontAsk",
                        None, None, False, before_provider_start=guard))
            self.assertEqual(len(guards), 1)

    def test_selection_during_option_preparation_calls_no_guard_or_sdk(self):
        with patch.dict(os.environ, {}, clear=True):
            def options(**kwargs):
                os.environ["MM_PROVIDER_APPLICATION_MODE"] = ""
            with patch.object(cli_bridge, "_Options", side_effect=options) as prepared, \
                    patch.object(cli_bridge, "_subscription_env", lambda _name: {}), \
                    patch.object(cli_bridge, "_require_provider_start", side_effect=AssertionError("guard")), \
                    patch.object(cli_bridge, "_sdk_query", side_effect=AssertionError("send")):
                with self.assertRaisesRegex(cli_bridge.ProviderStartRefused, "fabric_tools_unavailable"):
                    asyncio.run(cli_bridge._via_sdk(
                        "p", "m", "pm", None, None, [], [], 1, ".", "dontAsk",
                        None, None, False))
            prepared.assert_called_once()
            self.assertIn("MM_PROVIDER_APPLICATION_MODE", os.environ)

    def test_selection_during_option_preparation_blocks_subprocess(self):
        for guard in (None, unittest.mock.Mock()):
            with self.subTest(callback=guard is not None), patch.dict(os.environ, {}, clear=True):
                def environment(_name):
                    os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
                    return {}
                with patch.object(cli_bridge, "_subscription_env", side_effect=environment) as prepared, \
                        patch.object(cli_bridge.asyncio, "create_subprocess_exec",
                                     side_effect=AssertionError("subprocess must not run")):
                    with self.assertRaisesRegex(cli_bridge.ProviderStartRefused, "fabric_tools_unavailable"):
                        asyncio.run(cli_bridge._via_subprocess(
                            "p", "m", "pm", None, None, [], [], 1, ".", "dontAsk", {},
                            before_provider_start=guard))
                if guard is not None:
                    guard.assert_not_called()
                prepared.assert_called_once()


    def test_later_rung_and_waterfall_reentry_remain_fenced(self):
        self.selector("", "waterfall")
        self.refusal(asyncio.run(cli_bridge._reason(
            "u", _backend_override="waterfall", log_run=False)))
        with patch.dict(os.environ, {}, clear=True):
            def candidates():
                os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
                return [None]
            from brain import key_rotor
            # Ordinary unselected preparation must reach the late selector.
            # This pure boundary fixture has no production agents.yml.
            with patch.object(cli_bridge, "_cfg", return_value={"backend": "cli", "reasoning": {}}), \
                    patch.object(cli_bridge, "cli_path", lambda: "/claude"), \
                    patch.object(key_rotor, "candidates", side_effect=candidates) as selected, \
                    patch.object(cli_bridge, "_via_subprocess", side_effect=AssertionError("send")), \
                    patch.object(cli_bridge, "_SDK", False):
                with self.assertRaisesRegex(cli_bridge.ProviderStartRefused, "fabric_tools_unavailable"):
                    asyncio.run(cli_bridge._reason(
                        "u", _backend_override="cli", log_run=False))
                selected.assert_called_once()

    def test_waterfall_selected_late_refusal_does_not_fabricate_attempt(self):
        from brain import provider_waterfall
        effects = []
        original = cli_bridge._reason
        async def exercise():
            async def later(*args, **kwargs):
                os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
                effects.append("later-rung-refused")
                return cli_bridge._fabric_tools_unavailable()
            async def rungs(*args, **kwargs):
                return await original(*args, _backend_override="codex", **kwargs)
            with patch.dict(os.environ, {"BOT_LLM_BACKEND": "waterfall"}, clear=True), \
                    patch.object(provider_waterfall, "reason", rungs), \
                    patch.object(cli_bridge, "_reason", later), \
                    patch("brain.codex_bridge.reason", side_effect=AssertionError("legacy")):
                self.refusal(await cli_bridge.reason("u", log_run=False))
            self.assertEqual(effects, ["later-rung-refused"])
        asyncio.run(exercise())

    def test_original_success_and_usage_survive_selection_after_run(self):
        from brain import provider_waterfall
        original = {"ok": True, "text": "already observed", "backend": "sdk",
                    "cost_usd": 0.125, "usage": {"input_tokens": 7, "output_tokens": 3}}
        async def rungs(*args, **kwargs):
            os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
            return dict(original)
        async def exercise():
            with patch.dict(os.environ, {"BOT_LLM_BACKEND": "waterfall"}, clear=True), \
                    patch.object(provider_waterfall, "reason", rungs):
                result = await cli_bridge._reason("u", _backend_override="waterfall", log_run=False)
                self.assertEqual(result, original)
        asyncio.run(exercise())

    def test_api_selected_after_readiness_does_not_construct_legacy_client(self):
        import sys
        import types
        anthropic = types.SimpleNamespace(Anthropic=lambda: self.fail("legacy client"))
        with patch.dict(os.environ, {"BOT_LLM_BACKEND": "api"}, clear=True), \
                patch.dict(sys.modules, {"anthropic": anthropic}), \
                patch.object(fabric_inference, "call_model", return_value=(None, "held")):
            def available():
                os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
                return True
            with patch.object(client, "api_available", available):
                self.assertEqual(client.call_model("s", "u"), (None, "held"))

    def test_before_provider_start_original_refusal_remains_one_call(self):
        self.selector("shared_fabric", "cli")
        guard = unittest.mock.Mock(return_value=False)
        self.refusal(asyncio.run(cli_bridge._reason(
            "u", _backend_override="cli", log_run=False, before_provider_start=guard)))
        guard.assert_not_called()  # Initial presence refuses before any legacy effect.
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        with patch.object(cli_bridge, "_Options", lambda **kwargs: object()), \
                patch.object(cli_bridge, "_subscription_env", lambda _name: {}), \
                patch.object(cli_bridge, "_sdk_query", side_effect=AssertionError("send")):
            with self.assertRaisesRegex(cli_bridge.ProviderStartRefused, "admission revoked"):
                asyncio.run(cli_bridge._via_sdk(
                    "p", "m", "pm", None, None, [], [], 1, ".", "dontAsk",
                    None, None, False, before_provider_start=guard))
        guard.assert_called_once_with()

    def test_later_rung_refusal_localizes_selected_unavailable(self):
        from brain import provider_waterfall
        original = cli_bridge._reason
        async def rungs(prompt, **kwargs):
            os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
            return await original(prompt, **kwargs, _backend_override="cli")
        async def exercise():
            with patch.dict(os.environ, {"BOT_LLM_BACKEND": "waterfall"}, clear=True), \
                    patch.object(provider_waterfall, "reason", rungs), \
                    patch.object(cli_bridge, "cli_path", side_effect=AssertionError("discovery")):
                result = await cli_bridge.reason("u", log_run=False)
                self.refusal(result)
                self.assertNotIn("provider_attempts", result)
        asyncio.run(exercise())

    def test_chat_selection_changes_after_creation_before_iteration(self):
        with patch.dict(os.environ, {"BOT_LLM_BACKEND": "cli"}, clear=True):
            stream = cli_bridge.chat_stream("u")
            os.environ["MM_PROVIDER_APPLICATION_MODE"] = "unknown"
            self.assertEqual(asyncio.run(anext(stream)),
                             {"type": "error", "error": "fabric_tools_unavailable"})

    def test_unselected_veto_contract_still_one_call(self):
        async def query(**kwargs):
            self.fail("veto must precede SDK")
        guard = unittest.mock.Mock(return_value=False)
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(cli_bridge, "_Options", lambda **kwargs: object()), \
                patch.object(cli_bridge, "_subscription_env", lambda _name: {}), \
                patch.object(cli_bridge, "_sdk_query", query):
            with self.assertRaisesRegex(cli_bridge.ProviderStartRefused, "admission revoked"):
                asyncio.run(cli_bridge._via_sdk(
                    "p", "m", "pm", None, None, [], [], 1, ".", "dontAsk",
                    None, None, False, before_provider_start=guard))
        guard.assert_called_once_with()


    def test_backend_resolution_activation_precedes_any_legacy_discovery(self):
        from brain import explabs_pool, production_inference
        targets = ((cli_bridge, "available"), (client.codex_bridge, "available"),
                   (client, "api_available"), (explabs_pool, "available"),
                   (production_inference, "available"))
        from contextlib import ExitStack
        for mode in ("waterfall", "codex", "cli", "api", "explabs", "production_mode"):
            for action in ("available", "call"):
                with self.subTest(mode=mode, action=action), ExitStack() as stack:
                    stack.enter_context(patch.dict(os.environ, {"BOT_LLM_BACKEND": mode}, clear=True))
                    def resolve():
                        os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
                        return mode
                    stack.enter_context(patch.object(client, "backend", resolve))
                    for target, name in targets:
                        stack.enter_context(patch.object(target, name, side_effect=AssertionError("legacy discovery")))
                    stack.enter_context(patch.object(fabric_inference, "available", return_value=True))
                    call = stack.enter_context(patch.object(fabric_inference, "call_model", return_value=("fabric", None)))
                    if action == "available":
                        self.assertTrue(client.available())
                        call.assert_not_called()
                    else:
                        self.assertEqual(client.call_model("s", "u"), ("fabric", None))
                        call.assert_called_once()

    def test_cli_backend_resolution_activation_blocks_discovery(self):
        from brain import provider_waterfall, codex_bridge
        for mode, module in (("waterfall", provider_waterfall), ("codex", codex_bridge)):
            with self.subTest(mode=mode), patch.dict(os.environ, {"BOT_LLM_BACKEND": mode}, clear=True):
                def resolve():
                    os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
                    return mode
                with patch.object(cli_bridge, "_selected_backend", resolve), \
                        patch.object(module, "available", side_effect=AssertionError("legacy discovery")):
                    self.assertFalse(cli_bridge.available())

    def test_late_codex_and_explabs_readiness_cannot_send(self):
        from brain import explabs_pool
        for mode, target, sender in (("codex", client.codex_bridge, "reason_sync"),
                                     ("explabs", explabs_pool, "complete")):
            with self.subTest(mode=mode), patch.dict(os.environ, {"BOT_LLM_BACKEND": mode}, clear=True):
                def ready():
                    os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
                    return True
                with patch.object(target, "available", ready), \
                        patch.object(target, sender, side_effect=AssertionError("legacy send")), \
                        patch.object(fabric_inference, "call_model", return_value=(None, "held")) as call:
                    self.assertEqual(client.call_model("s", "u"), (None, "held"))
                    call.assert_called_once()

    def test_subprocess_preparation_precedes_original_veto_once(self):
        order = []
        def environment(_name):
            order.append("environment")
            return {}
        def guard():
            order.append("guard")
            self.assertEqual(order, ["environment", "guard"])
            raise ValueError("deadline elapsed during preparation")
        with patch.dict(os.environ, {"BOT_LLM_BACKEND": "cli"}, clear=True), \
                patch.object(cli_bridge, "_subscription_env", environment), \
                patch.object(cli_bridge.asyncio, "create_subprocess_exec", side_effect=AssertionError("late send")):
            with self.assertRaisesRegex(cli_bridge.ProviderStartRefused, "admission revoked"):
                asyncio.run(cli_bridge._via_subprocess(
                    "p", "m", "pm", None, None, [], [], 1, ".", "dontAsk", {},
                    before_provider_start=guard))
        self.assertEqual(order, ["environment", "guard"])

    def test_chat_activation_at_each_preparation_seam_is_error_only(self):
        from brain import bot_mcp, key_rotor, thinking_log
        from contextlib import ExitStack
        from types import SimpleNamespace
        import time
        for phase in ("backend", "config", "candidate", "environment", "options", "clock"):
            with self.subTest(phase=phase), ExitStack() as stack:
                stack.enter_context(patch.dict(os.environ, {"BOT_LLM_BACKEND": "cli"}, clear=True))
                def activate(name, value):
                    if name == phase:
                        os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
                    return value
                stack.enter_context(patch.object(cli_bridge, "_selected_backend",
                    lambda: activate("backend", "cli")))
                stack.enter_context(patch.object(cli_bridge, "_SDK", True))
                stack.enter_context(patch.object(cli_bridge, "cli_path", return_value="/fixture-claude"))
                stack.enter_context(patch.object(cli_bridge, "_cfg",
                    lambda: activate("config", {"reasoning": {}})))
                stack.enter_context(patch.object(cli_bridge, "resolve_model", return_value="fixture-model"))
                stack.enter_context(patch.object(key_rotor, "candidates", lambda: activate("candidate", [])))
                environment = stack.enter_context(patch.object(cli_bridge, "_subscription_env",
                    lambda name: activate("environment", {})))
                stack.enter_context(patch.object(cli_bridge, "_Options",
                    lambda **kwargs: activate("options", SimpleNamespace())))
                stack.enter_context(patch.object(cli_bridge, "time",
                    SimpleNamespace(monotonic=lambda: activate("clock", time.monotonic()))))
                stack.enter_context(patch.object(bot_mcp, "build_server", return_value={}))
                stack.enter_context(patch.object(bot_mcp, "armed_allowed_tools", return_value=[]))
                send = stack.enter_context(patch.object(cli_bridge, "_sdk_query",
                    side_effect=AssertionError("late chat send")))
                log = stack.enter_context(patch.object(thinking_log, "log_turn_async",
                    side_effect=AssertionError("refused chat has no provider turn")))
                cool = stack.enter_context(patch.object(key_rotor, "mark_cooling",
                    side_effect=AssertionError("selection is not provider failure")))
                async def collect():
                    return [event async for event in cli_bridge.chat_stream("p")]
                self.assertEqual(asyncio.run(collect()),
                    [{"type": "error", "error": "fabric_tools_unavailable"}])
                send.assert_not_called()
                log.assert_not_called()
                cool.assert_not_called()

    def test_successful_subprocess_fallback_retains_original_key_accounting(self):
        from brain import key_rotor
        async def failed(*args, **kwargs):
            raise RuntimeError("fixture non-key SDK failure")
        async def fallback(*args, **kwargs):
            return {"ok": True, "text": "observed fallback", "backend": "cli", "session_id": "original-session",
                    "cost_usd": 0.125, "usage": {"input_tokens": 7, "output_tokens": 3}}
        with patch.dict(os.environ, {"BOT_LLM_BACKEND": "cli"}, clear=True), \
                patch.object(cli_bridge, "_SDK", True), \
                patch.object(cli_bridge, "_cfg", return_value={"reasoning": {}}), \
                patch.object(cli_bridge, "cli_path", return_value="/fixture-claude"), \
                patch.object(cli_bridge, "_via_sdk", failed), \
                patch.object(cli_bridge, "_via_subprocess", fallback), \
                patch.object(cli_bridge, "_new_sdk_diagnostic", return_value=None), \
                patch.object(cli_bridge, "_record_sdk_diagnostic"), \
                patch.object(key_rotor, "classify_failure", return_value=None), \
                patch.object(key_rotor, "record_session") as session, \
                patch.object(cli_bridge, "_record_cli_cost") as cost:
            result = asyncio.run(cli_bridge._reason("u", allowed_tools=[], log_run=False,
                _subscription_slots=[{"key_id": "original-key", "env_name": "FIXTURE_TOKEN"}]))
        self.assertEqual(result["key_id"], "original-key")
        self.assertEqual(result["session_id"], "original-session")
        session.assert_called_once_with("original-key", est_tokens=10, cycle_id="", stage="pm", outcome="ok")
        self.assertEqual(cost.call_count, 1)
        self.assertEqual(cost.call_args.kwargs["key_id"], "original-key")

    def test_late_veto_preserves_observed_failure_usage_tools_and_key(self):
        from brain import key_rotor
        from control_plane import run_events
        from contextlib import ExitStack
        for provider_kind in ("sdk", "cli", "fallback"):
            for count in (1, 2):
                with self.subTest(provider=provider_kind, candidates=count), ExitStack() as stack:
                    calls = []
                    observed = {"ok": False, "text": "fixture key failure", "error": "fixture quota",
                        "backend": "sdk" if provider_kind == "sdk" else "cli",
                        "cost_usd": 0.25, "usage": {"input_tokens": 9, "output_tokens": 2},
                        "tools_used": ["Read"], "session_id": "original-session"}
                    async def first(*args, **kwargs):
                        calls.append(kwargs["env_name"])
                        return dict(observed)
                    async def failed_sdk(*args, **kwargs):
                        raise RuntimeError("fixture non-key SDK exception")
                    def classify(text, *args, **kwargs):
                        return None if "non-key SDK exception" in str(text) else ("quota", "fixture")
                    def cooled(*args, **kwargs):
                        os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
                    stack.enter_context(patch.dict(os.environ, {"BOT_LLM_BACKEND": "cli"}, clear=True))
                    stack.enter_context(patch.object(cli_bridge, "_SDK", provider_kind != "cli"))
                    stack.enter_context(patch.object(cli_bridge, "_cfg", return_value={"reasoning": {}}))
                    stack.enter_context(patch.object(cli_bridge, "cli_path", return_value="/fixture-claude"))
                    stack.enter_context(patch.object(cli_bridge, "_via_sdk",
                        failed_sdk if provider_kind == "fallback" else first))
                    stack.enter_context(patch.object(cli_bridge, "_via_subprocess",
                        first if provider_kind != "sdk" else unittest.mock.Mock(side_effect=AssertionError("refused send"))))
                    stack.enter_context(patch.object(cli_bridge, "_new_sdk_diagnostic", return_value=None))
                    stack.enter_context(patch.object(cli_bridge, "_record_sdk_diagnostic"))
                    stack.enter_context(patch.object(key_rotor, "classify_failure", classify))
                    stack.enter_context(patch.object(key_rotor, "mark_cooling", cooled))
                    exhausted = stack.enter_context(patch.object(run_events, "append"))
                    exhaustion_read = stack.enter_context(patch.object(key_rotor, "all_cooling_info"))
                    cost = stack.enter_context(patch.object(cli_bridge, "_record_cli_cost"))
                    slots = [{"key_id": "original-key", "env_name": "FIRST_TOKEN"},
                             {"key_id": "refused-key", "env_name": "SECOND_TOKEN"}][:count]
                    result = asyncio.run(cli_bridge._reason("u", allowed_tools=[], log_run=False,
                        _subscription_slots=slots))
                    self.assertEqual(calls, ["FIRST_TOKEN"])
                    self.assertEqual(result, dict(observed, key_id="original-key"))
                    self.assertEqual(cost.call_count, 1)
                    self.assertEqual(cost.call_args.kwargs["key_id"], "original-key")
                    exhausted.assert_not_called()
                    exhaustion_read.assert_not_called()



class NativeTextApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _helpers.BufferedNativeChatTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        _helpers.BufferedNativeChatTests.tearDownClass.__func__(cls)

    def start(self, patcher):
        self.addCleanup(patcher.stop)
        return patcher.start()

    def setUp(self):
        import time
        import yaml
        from engine.fabric_inference_client import NATIVE_PROTOCOL
        _helpers.BufferedNativeChatTests.setUp(self)
        native = self.native
        native.server.shutdown()
        native.server.server_close()
        token = "fixture-mastermind-text-credential-0123456789"
        secret_ref = "MASTERMIND_FABRIC_APPLICATION_TOKEN"
        native.service = native.go.ApplicationServiceBinding(
            "mastermind-text", "vps", "site_batch", secret_ref, token)
        native.document["application_grants"] = [{
            **native.grant, "grant_id": "fixture-mastermind-text",
            "principal_id": "mastermind-text", "credential_ref": secret_ref,
            "admission_root": "service:mastermind-text", "workloads": ["site_batch"]}]
        native.save()
        native.server = native.go.make_server(native.router, lease_gateway=native.gateway,
                                             application_services=(native.service,))
        native.server.handle_error = lambda *args: None
        native._serve(native.server)
        transport = self.owner._ApplicationFabricTransport(
            f"http://127.0.0.1:{native.server.server_port}/v1", secret_ref, "go", _helpers.MODEL, "unknown",
            "fabric:go_mastermind_text", "fabric_application_go_mastermind_text",
            qualified=True, application_allowed=True, protocol=NATIVE_PROTOCOL, metadata_read=False)
        self.start(patch.dict(self.owner._APPLICATION_FABRIC_TRANSPORTS, {
            "native_go_mastermind_text_v1": transport}))
        row = {key: getattr(transport, key) for key in self.owner._APPLICATION_IDENTITY_FIELDS}
        row.update(transport_id="native_go_mastermind_text_v1", enabled=True, application_allowed=True,
            qualification=self.owner.PROFILE_QUALIFIED_CANARY, qualification_ref="fixture:text-source-only",
            qualified_until=time.time() + 3600)
        document = json.loads(self.originals[self.config_paths[0]])
        document["application_fabric_modes"] = {"mastermind_text_fabric": row}
        self.config_paths[0].write_text(json.dumps(document))
        self.config_paths[1].write_text(yaml.safe_dump({"capabilities": [{
            "capability_id": "fabric_application_go_mastermind_text", "secret_ref": secret_ref,
            "kill_state": "active", "allowed_lanes": ["mastermind-text"]}]}))
        self.start(patch.dict(os.environ, {"MM_PROVIDER_WORKLOAD_PROFILE": "site_batch", secret_ref: token}))


    def costs(self):
        return _helpers.BufferedNativeChatTests.costs(self)

    def test_availability_never_reads_credentials_constructs_client_or_admits(self):
        from engine.fabric_inference_client import FabricInferenceClient
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("credential")) as secret, \
                patch.object(FabricInferenceClient, "__init__", side_effect=AssertionError("client")) as client:
            self.assertTrue(fabric_inference.available())
            secret.assert_not_called()
            client.assert_not_called()
        self.assertEqual(self.native.posts, [])
        self.assertEqual(self.native.rows("leases"), [])
        self.assertEqual(self.closes, [])

    def test_native_text_call_keeps_original_operation_and_closes_once(self):
        result = fabric_inference.call_model("Use supplied evidence.", "Explain the state.")
        self.assertEqual(result, ("Fixture answer.", None))
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.closes), 1)
        requests = self.native.rows("application_requests")
        self.assertTrue(requests[0]["turn_id"].startswith("mastermind-text-"))
        self.assertEqual(requests[0]["request_id"], requests[0]["turn_id"] + ":brain:0")
        self.assertEqual(self.native.rows("leases")[0]["state"], "released")
        self.assertEqual(len(self.costs()), 1)
        self.assertEqual(self.costs()[0]["input_tokens"], 11)

    def test_known_native_error_keeps_observed_model_without_replay(self):
        self.native.response["model"] = "other-model"
        result = fabric_inference.call_model("Use supplied evidence.", "Explain the state.")
        self.assertEqual(result, (None, "fabric_unavailable"))
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.closes), 1)
        self.assertEqual(self.costs()[0]["model"], "other-model")
        self.assertEqual(self.costs()[0]["input_tokens"], 11)
        self.assertEqual(self.native.rows("leases")[0]["state"], "released")

    def test_unknown_settlement_closes_locally_without_releasing_original_hold(self):
        with patch.object(self.native.gateway, "complete_application", side_effect=OSError("before commit")):
            result = fabric_inference.call_model("Use supplied evidence.", "Explain the state.")
        self.assertEqual(result, (None, "fabric_effect_unknown"))
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.closes), 1)
        self.assertEqual(self.costs()[0]["input_tokens"], 11)
        self.assertIn("turn_total_unknown", self.costs()[0]["note"])
        self.assertEqual(self.native.rows("application_requests")[0]["state"], "unknown")
        self.assertIn(self.native.rows("leases")[0]["state"], {"held", "rented"})

    def test_readiness_does_not_freeze_a_revoked_binding(self):
        self.assertTrue(fabric_inference.available())
        document = json.loads(self.config_paths[0].read_text())
        document["application_fabric_modes"]["mastermind_text_fabric"]["enabled"] = False
        self.config_paths[0].write_text(json.dumps(document))
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("credential")):
            self.assertFalse(fabric_inference.available())
            self.assertEqual(fabric_inference.call_model("s", "u"),
                             (None, "fabric_binding_unavailable"))
        self.assertEqual(self.native.posts, [])
        self.assertEqual(self.native.rows("leases"), [])

    def test_actual_client_selected_positive_with_api_waterfall_and_absent_bot(self):
        for mode in ("api", "waterfall", None):
            with self.subTest(bot=mode), patch.dict(os.environ, clear=False) as env:
                if mode is None:
                    env.pop("BOT_LLM_BACKEND", None)
                else:
                    env["BOT_LLM_BACKEND"] = mode
                with patch.object(cli_bridge, "reason_sync", side_effect=AssertionError("legacy")), \
                        patch.object(cli_bridge, "available", side_effect=AssertionError("legacy")):
                    self.assertEqual(client.backend(), "fabric")
                    self.assertTrue(client.available())
                    self.assertEqual(client.call_model("s", "u"), ("Fixture answer.", None))
                self.assertEqual(len(self.native.posts), 1)
                self.assertEqual(self.native.posts[0][1].count(b'"model"'), 1)
                self.assertEqual(len(self.closes), 1)
                self.assertEqual(len(self.costs()), 1)
                self.native.posts.clear()
                self.closes.clear()
                for path in (self.root / "costs").rglob("*.jsonl"):
                    path.unlink()

    def test_selected_owner_failure_factory_none_and_zero_readiness_effects(self):
        from engine.fabric_inference_client import FabricInferenceClient
        for mode in ("", "unknown", " ", "{"):
            with self.subTest(mode=mode), patch.dict(os.environ,
                    {"MM_PROVIDER_APPLICATION_MODE": mode}), \
                    patch.object(cli_bridge, "_cfg", side_effect=AssertionError("config")), \
                    patch.object(cli_bridge, "cli_path", side_effect=AssertionError("discovery")), \
                    patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("credential")), \
                    patch.object(FabricInferenceClient, "__init__", side_effect=AssertionError("client")):
                self.assertFalse(client.available())
                self.assertEqual(client.call_model("s", "u"), (None, "fabric_binding_unavailable"))
                self.assertEqual(cli_bridge.reason_sync("u"), {
                    "ok": False, "text": None, "backend": "fabric",
                    "error": "fabric_tools_unavailable"})
        with patch.object(fabric_inference, "_owner", side_effect=ImportError("owner")):
            self.assertFalse(client.available())
            self.assertEqual(client.call_model("s", "u"), (None, "fabric_owner_unavailable"))
        self.assertEqual(self.native.posts, [])
        self.assertEqual(self.native.rows("leases"), [])
        original = self.owner.configured_application_fabric
        def no_factory(*args, **kwargs):
            return True, None
        with patch.object(self.owner, "configured_application_fabric", no_factory):
            self.assertFalse(client.available())
            self.assertEqual(client.call_model("s", "u"), (None, "fabric_binding_unavailable"))
        self.assertEqual(self.native.posts, [])
        self.assertTrue(callable(original))


if __name__ == "__main__":
    unittest.main()
