"""Actual installed gateway construction; owner/service authorization is fixture-only."""
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

import test_owner_integration as fixtures
from integrations.hermes_application_fabric.attended_host import AttendedHost
from integrations.hermes_application_fabric.client import ApplicationBinding, HermesApplicationClient
from integrations.hermes_application_fabric.errors import HermesFabricError
from integrations.hermes_application_fabric.native import PROVIDER


class AttendedNativeTests(unittest.TestCase):
    def setUp(self):
        fixtures.OwnerLoopbackTests.setUp(self)
        from integrations.hermes_application_fabric.native import register_native_provider
        register_native_provider()  # Explicit native startup precedes construction.
        from hermes_cli.plugins import PluginContext, PluginManifest, _delivery_manager
        self.context = PluginContext(PluginManifest(name="mmx-attended-fixture"), _delivery_manager())
        self.host = AttendedHost(self.context)
        self.bind_calls = []

    def tearDown(self):
        self.host.dispose()
        fixtures.OwnerLoopbackTests.tearDown(self)

    def bind_fixture(self, factory, **kwargs):
        self.bind_calls.append(kwargs)
        self.binding.turn_id = kwargs["turn_id"]
        self.binding._authorized = kwargs["authorized"]
        return self.binding

    def turn(self):
        return self.host.admitted_turn(factory=object(), operation_id="owner-turn-1",
            session_id="session-1", task_id="task-native-host", requested_model="host-selection",
            strict_model="model-1", authorized=lambda _: self.allow, prior_admission_possible=False)

    def build_gateway_agent(self, turn, tools=None):
        from gateway.turn_context import TurnContext
        from gateway.session_execution import GatewaySessionAgentMixin
        from run_agent import AIAgent
        source = N(**{key: None for key in
            ("user_id", "user_id_alt", "user_name", "chat_id", "chat_name", "chat_type", "thread_id")})
        ctx = TurnContext(AIAgent=AIAgent, session_id="session-1", session_key="fixture-key",
            source=source, user_config={}, enabled_toolsets=tools or [], disabled_toolsets=None)
        turn.attach_gateway_context(ctx)
        holder = GatewaySessionAgentMixin()
        holder._ctx = ctx
        holder._runner = N(_service_tier=None, _session_db=None, _prefill_messages=None,
                           _refresh_fallback_model=lambda: None)
        policy = N(verbose=False, ignore_rules=True, pass_session_id=False, run_budget_seconds=None)
        route = {"model": "host-selection", "runtime": {"provider": PROVIDER,
            "requested_provider": PROVIDER, "api_mode": "chat_completions",
            "api_key": None, "base_url": None}}
        with patch("gateway.session_policy.policy_for_source", return_value=policy), \
             patch("gateway.session_authorities.active_authority", return_value=None), \
             patch("gateway.session_worker_construct.session_prefill", return_value=None):
            native = holder._build_fresh_agent(route, "local", None, 3, {}, {}, True)
        return native, ctx, AIAgent

    def test_actual_gateway_constructor_and_native_turn_use_one_original_binding(self):
        turn = self.turn()
        with patch.object(ApplicationBinding, "from_factory", side_effect=self.bind_fixture):
            with self.host.activate(turn):
                native, ctx, original = self.build_gateway_agent(turn)
                self.assertIs(type(native.client), HermesApplicationClient)
                result = native.run_conversation("Reply with the fixture result.", task_id="task-native-host")
                self.assertEqual(result.get("final_response"), "Result 世界")
                self.assertEqual(len(self.bind_calls), 1)
                self.assertEqual(self.bind_calls[0]["profile_id"], "attended")
                self.assertTrue(self.calls[0]["authenticated"])
            self.assertIs(ctx.AIAgent, original)
        self.assertEqual((len(self.calls), self.closed), (1, 1))
        self.assertIs(turn.close_result, turn.close())

    def test_actual_gateway_tool_result_keeps_binding_and_native_tool_identity(self):
        from tools.registry import registry
        self.mode = "native-conversation"
        self.tool_name = "tool_call"
        self.tool_arguments = {"calls": [{"name": "mmx_attended_fixture_read", "arguments": {"value": "original"}}]}
        executed = []
        def read(args, **_):
            executed.append(args)
            return args["value"]
        registry.register(name="mmx_attended_fixture_read", toolset="mmx_attended_fixture",
            schema={"name": "mmx_attended_fixture_read", "description": "Read fixture",
                "parameters": {"type": "object", "properties": {"value": {"type": "string"}},
                               "required": ["value"]}}, handler=read)
        turn = self.turn()
        with patch.object(ApplicationBinding, "from_factory", side_effect=self.bind_fixture):
            with self.host.activate(turn):
                native, _, _ = self.build_gateway_agent(turn, ["mmx_attended_fixture"])
                result = native.run_conversation("Read the fixture once, then report.", task_id="task-native-host")
                self.assertEqual(result.get("final_response"), "Result 世界")
        self.assertEqual(executed, [{"value": "original"}])
        self.assertEqual((len(self.bind_calls), len(self.calls), self.closed), (1, 2, 1))
        self.assertNotEqual(self.calls[0]["request_id"], self.calls[1]["request_id"])
        self.assertEqual(self.calls[1]["payload"]["messages"][-1]["tool_call_id"], "tool-original")

    def test_gateway_context_collision_is_not_overwritten(self):
        from gateway.turn_context import TurnContext
        incumbent = lambda **_: None
        ctx = TurnContext(session_id="session-1", AIAgent=incumbent)
        turn = self.turn()
        with self.assertRaises(HermesFabricError):
            turn.attach_gateway_context(ctx)
        self.assertIs(ctx.AIAgent, incumbent)

    def test_missing_owner_relation_refuses_before_provider_and_never_rebinds(self):
        turn = self.turn()
        with patch.object(ApplicationBinding, "from_factory",
                side_effect=HermesFabricError("hermes_fabric_role_unqualified")) as bind:
            with self.host.activate(turn):
                native, _, _ = self.build_gateway_agent(turn)
                result = native.run_conversation("Refuse.", task_id="task-native-host")
                self.assertNotEqual(result.get("final_response"), "Result 世界")
                self.assertEqual(turn.refusal, ("hermes_fabric_role_unqualified", False))
            self.assertEqual(bind.call_count, 1)
        self.assertEqual((len(self.calls), self.closed), (0, 0))


if __name__ == "__main__":
    unittest.main()
