"""Installed Hermes implementation tests; the APPLICATION endpoint is a fixture."""
import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

import test_owner_integration as fixtures
from integrations.hermes_application_fabric.client import HermesApplicationClient, NativeCall, call_scope
from integrations.hermes_application_fabric.errors import HermesFabricError
from integrations.hermes_application_fabric.native import (
    AUTH_TYPE, PROVIDER, create_primary_agent, execution_middleware, register_native_provider,
)


class InstalledNativeTests(unittest.TestCase):
    def setUp(self):
        fixtures.OwnerLoopbackTests.setUp(self)
        register_native_provider()
        from hermes_cli.plugins import _delivery_manager
        self.manager = _delivery_manager()
        self.native_calls = []

        def resolve(call):
            if not self.native_calls:
                self.binding.turn_id = call.turn_id
            self.native_calls.append(call)
            return self.binding

        self.middleware = execution_middleware(resolve)
        self.manager._middleware.setdefault("llm_execution", []).append(self.middleware)

    def tearDown(self):
        self.manager._middleware["llm_execution"].remove(self.middleware)
        fixtures.OwnerLoopbackTests.tearDown(self)

    def agent(self, **extra):
        return create_primary_agent(model="host-selection", session_id="session-1",
            quiet_mode=True, skip_memory=True, skip_background_review=True,
            skip_context_files=True, load_soul_identity=False, save_trajectories=False,
            max_iterations=3, max_tokens=256, **extra)

    def test_discovered_profile_and_keyless_actual_primary_construction(self):
        from providers import get_provider_profile
        from agent.auxiliary_client import resolve_provider_client
        profile = get_provider_profile(PROVIDER)
        self.assertEqual(profile.auth_type, AUTH_TYPE)
        self.assertEqual(profile.env_vars, ())
        self.assertIs(profile.supports_streaming, False)
        client, selected = resolve_provider_client(PROVIDER, model="host-selection", raw_codex=True)
        self.assertIs(type(client), HermesApplicationClient)
        self.assertEqual(selected, "host-selection")
        self.assertIsNone(client.api_key)
        self.assertEqual(client.base_url, "")
        native = self.agent(enabled_toolsets=[])
        self.assertIs(type(native.client), HermesApplicationClient)
        self.assertIn(native.api_key, (None, ""))
        self.assertEqual(self.calls, [])

    def test_unbound_profile_client_does_not_fall_back_to_http(self):
        from agent.agent_runtime_helpers import create_openai_client
        native = N(provider=PROVIDER, model="host-selection", _client_log_context=lambda: "fixture")
        client = create_openai_client(native, {"api_key": None, "base_url": ""}, reason="fixture", shared=True)
        self.assertIs(type(client), HermesApplicationClient)
        with self.assertRaises(HermesFabricError):
            client.chat.completions.create(model="host-selection", messages=[])
        self.assertEqual(self.calls, [])

    def test_real_transport_tool_history_and_normalization(self):
        from providers import get_provider_profile
        from agent.transports.chat_completions import ChatCompletionsTransport
        transport = ChatCompletionsTransport()
        profile = get_provider_profile(PROVIDER)
        self.mode = "tools"
        kwargs = transport.build_kwargs("host-selection", [{"role": "user", "content": "Read"}],
            tools=[{"type": "function", "function": {"name": "read", "parameters": {}}}],
            provider_profile=profile, max_tokens=256)
        with call_scope(self.binding, self.call):
            result = HermesApplicationClient().create(**kwargs)
        normalized = transport.normalize_response(result)
        self.assertEqual(normalized.tool_calls[0].id, "tool-original")
        self.assertEqual(normalized.tool_calls[0].name, "read")
        self.assertEqual(normalized.finish_reason, "tool_calls")

    def test_real_native_primary_turn_uses_the_original_owner(self):
        native = self.agent(enabled_toolsets=[])
        result = native.run_conversation("Reply with the fixture result.", task_id="task-fixture")
        self.assertEqual(result.get("final_response"), "Result 世界",
            {"native_calls": len(self.native_calls), "owner_calls": len(self.calls)})
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.calls[0]["authenticated"])
        self.assertEqual(self.native_calls[0].session_id, "session-1")
        self.assertEqual(self.calls[0]["request_id"], self.binding.request_id(self.native_calls[0]))

    def _use_auto_owner(self):
        from engine.fabric_inference_client import FabricInferenceClient, NATIVE_PROTOCOL, validate_auto_route_scope
        scope, digest = validate_auto_route_scope({"schema": "mastermind.application_route_scope.v1", "pools": ["go"]})
        self.auto_inspection = dict(schema="mastermind.fabric_application_inspection.v2", requested_model=None,
            route_scope=scope, route_scope_digest=digest, output_limit_mode="hard_maximum",
            cap_id="fabric:fixture", capability_id="fabric_fixture", workload_policy={"fixture": True},
            transport_identity="b" * 64)
        # The fixed fixture client has made no request or admission. Replace
        # that unstarted test fixture only; production never replaces an owner.
        self.assertEqual(self.calls, [])
        self.owner = FabricInferenceClient(base_url=f"http://127.0.0.1:{self.server.server_port}/v1",
            proxy_token="t" * 40, model=None, protocol=NATIVE_PROTOCOL, operation_id="owner-turn-1",
            auto_inspection=self.auto_inspection)
        self.binding._owner, self.binding.automatic, self.binding.model = self.owner, True, None

    def _assert_native_auto_observation(self, observation, index):
        from engine.fabric_inference_client import _auto_request_digest, validate_auto_observation
        native_call, wire = self.native_calls[index], self.calls[index]
        self.assertIs(self.binding._owner, self.owner)
        self.assertEqual(wire["turn_id"], self.binding.operation_id)
        self.assertIsNone(wire["payload"]["model"])
        self.assertTrue(wire["authenticated"])
        self.assertEqual(wire["request_id"], self.binding.request_id(native_call))
        verified = validate_auto_observation(observation, self.auto_inspection,
            operation_id=self.binding.operation_id, request_id=self.binding.request_id(native_call),
            request_digest=_auto_request_digest(wire["payload"]),
            routed_request_digest=_auto_request_digest(dict(wire["payload"], model="model-1")),
            max_tokens=wire["payload"]["max_tokens"], require_success=True)
        self.assertEqual(verified["serving_model"], "model-1")
        self.assertEqual(verified["routing"]["pool"], "go")
        self.assertEqual(verified["usage"], {"input_tokens": 11, "output_tokens": 7})

    def test_real_native_auto_turn_correlates_original_owner_selection(self):
        self._use_auto_owner()
        native = self.agent(enabled_toolsets=[])
        result = native.run_conversation("Reply with the fixture result.", task_id="task-auto")
        self.assertEqual(result.get("final_response"), "Result 世界")
        self.assertEqual(len(self.calls), 1)
        self._assert_native_auto_observation(self.owner.application_observation.document, 0)
        # The native model remains the host route label. The immutable owner
        # observation is the serving receipt, not that configuration label.
        self.assertEqual(native.model, "host-selection")

    def test_real_native_auto_tools_preserve_both_original_request_observations(self):
        self._use_auto_owner()
        observations = []
        original_result = self.owner._auto_result

        def observe(*args, **kwargs):
            result = original_result(*args, **kwargs)
            observations.append(result.application_observation.document)
            return result

        with patch.object(self.owner, "_auto_result", side_effect=observe):
            _, result, executed = self._tool_turn("native-conversation")
        self.assertEqual(result.get("final_response"), "Result 世界")
        self.assertEqual(executed, [{"value": "native fixture"}])
        self.assertEqual((len(self.calls), len(observations)), (2, 2))
        for index, observation in enumerate(observations):
            self._assert_native_auto_observation(observation, index)
        self.assertEqual(self.calls[1]["payload"]["messages"][-1]["tool_call_id"], "tool-original")

    def test_real_native_auto_disconnect_does_not_replay_or_misattribute_last_observation(self):
        self._use_auto_owner()
        _, result, executed = self._tool_turn("native-effect-disconnect")
        self.assertNotEqual(result.get("final_response"), "Result 世界")
        self.assertEqual(executed, [{"value": "native fixture"}])
        self.assertEqual((len(self.calls), len(self.native_calls), self.closed), (2, 2, 1))
        retained = self.owner.application_observation.document
        self._assert_native_auto_observation(retained, 0)
        self.assertNotEqual(retained["request_id"], self.binding.request_id(self.native_calls[-1]))
        from engine.fabric_inference_client import FabricInferenceError
        with self.assertRaises(FabricInferenceError):
            self._assert_native_auto_observation(retained, 1)
        self.assertTrue(self.owner._closed)

    def test_actual_error_classifier_disables_all_recovery_flags(self):
        from agent.error_classifier import classify_api_error
        for error in (HermesFabricError("hermes_fabric_owner_refused", effect_unknown=True),
                      TimeoutError("watchdog"), ValueError("shape"), TypeError("shape")):
            with self.subTest(kind=type(error).__name__):
                verdict = classify_api_error(error, provider=PROVIDER, model="host-selection")
                for flag in ("retryable", "should_compress", "should_rotate_credential", "should_fallback"):
                    self.assertFalse(getattr(verdict, flag))

    def test_native_middleware_detaches_errors_and_closes_original_owner(self):
        from hermes_cli.middleware import run_llm_execution_middleware
        seen = []

        def terminal(request):
            seen.append(request)
            HermesApplicationClient().create(**request)
            raise TimeoutError("private watchdog body that must not reach recovery")

        request = {"model": "host-selection", "messages": [{"role": "user", "content": "hello"}]}
        with self.assertRaises(HermesFabricError) as caught:
            run_llm_execution_middleware(request, terminal, provider=PROVIDER,
                session_id="session-1", task_id="task-1", turn_id="turn-1", api_request_id="api-1")
        self.assertTrue(caught.exception.effect_unknown)
        self.assertIsNone(caught.exception.__context__)
        self.assertIsNone(caught.exception.__cause__)
        self.assertEqual((len(seen), len(self.calls), self.closed), (1, 1, 1))
        with call_scope(self.binding, NativeCall("session-1", "task-1", "turn-1", "new-api-id")), self.assertRaises(HermesFabricError):
            HermesApplicationClient().create(**request)
        self.assertEqual(len(self.calls), 1)

    def test_async_native_resolution_is_an_awaitable_refusal(self):
        from agent.auxiliary_client import resolve_provider_client
        client, _ = resolve_provider_client(PROVIDER, model="host-selection", async_mode=True)
        with self.assertRaises(HermesFabricError):
            asyncio.run(client.chat.completions.create(model="host-selection", messages=[]))
        self.assertEqual(self.calls, [])

    def test_colliding_custom_provider_is_not_overwritten(self):
        with patch("hermes_cli.runtime_provider_custom.has_named_custom_provider", return_value=True), self.assertRaises(HermesFabricError):
            register_native_provider()

    def test_existing_auth_arm_is_not_overwritten(self):
        from agent.auxiliary_client_registry import REGISTRY_AUTHTYPE_ARMS
        incumbent = lambda _: None
        with patch.dict(REGISTRY_AUTHTYPE_ARMS, {AUTH_TYPE: incumbent}), self.assertRaises(HermesFabricError):
            register_native_provider()

    def _tool_turn(self, mode):
        from tools.registry import registry
        self.mode = mode
        fixture_tool = "mmx_fixture_read"
        # Hermes v0.23 exposes deferred tools through its real tool_call wrapper.
        # The fixture models the exact offered schema, not an unoffered function.
        self.tool_name = "tool_call"
        self.tool_arguments = {"calls": [{"name": fixture_tool, "arguments": {"value": "native fixture"}}]}
        executed = []

        def handler(arguments, **_):
            executed.append(arguments)
            return json.dumps({"value": arguments["value"]})

        registry.register(name=fixture_tool, toolset="mmx_fixture_tools", schema={"name": fixture_tool,
            "description": "Read an immutable in-memory fixture.", "parameters": {"type": "object",
                "properties": {"value": {"type": "string"}}, "required": ["value"]}}, handler=handler)
        native = self.agent(enabled_toolsets=["mmx_fixture_tools"])
        result = native.run_conversation("Read the fixture once, then report.", task_id="task-native-tools")
        return native, result, executed

    def test_native_tool_execution_and_original_result_continuation(self):
        _, result, executed = self._tool_turn("native-conversation")
        self.assertEqual(result.get("final_response"), "Result 世界",
            {"native_calls": len(self.native_calls), "owner_calls": len(self.calls)})
        self.assertEqual(executed, [{"value": "native fixture"}])
        self.assertEqual(len(self.calls), 2)
        self.assertNotEqual(self.calls[0]["request_id"], self.calls[1]["request_id"])
        self.assertEqual(self.calls[1]["payload"]["messages"][-1]["role"], "tool")
        self.assertEqual(self.calls[1]["payload"]["messages"][-1]["tool_call_id"], "tool-original")

    def test_connection_loss_after_native_tool_does_not_execute_it_again(self):
        native, result, executed = self._tool_turn("native-effect-disconnect")
        self.assertNotEqual(result.get("final_response"), "Result 世界")
        self.assertEqual(executed, [{"value": "native fixture"}])
        self.assertEqual((len(self.calls), len(self.native_calls), self.closed), (2, 2, 1))
        self.assertTrue(self.owner._closed)
        rebuilt = native._create_openai_client(native._client_kwargs, reason="fixture-recovery", shared=False)
        original = self.native_calls[-1]
        replacement = NativeCall(original.session_id, original.task_id, original.turn_id, "replacement-api-id")
        with call_scope(self.binding, replacement), self.assertRaises(HermesFabricError):
            rebuilt.chat.completions.create(model="host-selection", messages=[{"role": "user", "content": "retry"}])
        self.assertEqual((len(self.calls), len(executed)), (2, 1))

    def test_real_native_watchdog_fences_late_result_and_new_request_identity(self):
        from agent import chat_completion_helpers as helpers
        self.mode = "native-stall"
        native = self.agent(enabled_toolsets=[])
        original = helpers._resolve_nonstream_watchdogs

        def short_watchdog(agent, kwargs):
            return replace(original(agent, kwargs), stale_timeout=.05)

        with patch.object(helpers, "_resolve_nonstream_watchdogs", side_effect=short_watchdog):
            result = native.run_conversation("Wait for the bounded fixture.", task_id="task-watchdog")
        self.assertNotEqual(result.get("final_response"), "Result 世界")
        self.assertEqual((len(self.calls), len(self.native_calls), self.closed), (1, 1, 1))
        self.assertTrue(self.owner._closed)
        self.response_release.set()
        self.assertTrue(self.response_finished.wait(timeout=2))
        first = self.native_calls[0]
        with call_scope(self.binding, NativeCall(first.session_id, first.task_id, first.turn_id, "after-watchdog")), self.assertRaises(HermesFabricError):
            HermesApplicationClient().create(model="host-selection", messages=[{"role": "user", "content": "retry"}])
        self.assertEqual(len(self.calls), 1)
