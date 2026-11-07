"""AUTO translation through the actual incumbent client and loopback endpoint."""
import unittest

from engine.fabric_inference_client import FabricInferenceClient, NATIVE_PROTOCOL, validate_auto_route_scope
from integrations.hermes_application_fabric import (
    HermesFabricError, NativeCall, HermesApplicationClient, call_scope,
)
import test_owner_integration as original


class AutoOwnerTests(unittest.TestCase):
    def setUp(self):
        original.OwnerLoopbackTests.setUp(self)
        scope, digest = validate_auto_route_scope({"schema": "mastermind.application_route_scope.v1", "pools": ["go"]})
        self.auto_inspection = dict(schema="mastermind.fabric_application_inspection.v2", requested_model=None,
            route_scope=scope, route_scope_digest=digest, output_limit_mode="hard_maximum",
            cap_id="fabric:fixture", capability_id="fabric_fixture", workload_policy={"fixture": True},
            transport_identity="b" * 64)
        self.owner = FabricInferenceClient(base_url=f"http://127.0.0.1:{self.server.server_port}/v1",
            proxy_token="t" * 40, model=None, protocol=NATIVE_PROTOCOL, operation_id="owner-turn-1",
            auto_inspection=self.auto_inspection)
        self.binding._owner = self.owner
        self.binding.automatic = True
        self.binding.model = None

    tearDown = original.OwnerLoopbackTests.tearDown
    invoke = original.OwnerLoopbackTests.invoke

    def test_null_wire_model_and_actual_served_observation(self):
        response = self.invoke(max_tokens=128)
        self.assertIsNone(self.calls[0]["payload"]["model"])
        self.assertEqual(response.model, "model-1")
        observation = response.application_observation.model_dump()
        self.assertEqual(observation, self.owner.application_observation.document)
        self.assertEqual(observation["routing"]["output_contract"], {"mode": "hard_maximum", "max_tokens": 128})
        self.assertEqual(self.binding.requested_model, "host-selection")
        self.assertEqual(self.binding.model, None)

    def test_new_facade_cannot_replay_original_auto_request(self):
        self.invoke()
        with self.assertRaises(HermesFabricError):
            self.invoke()
        self.assertEqual(len(self.calls), 1)

    def test_provider_route_change_is_held_without_adapter_failover(self):
        self.invoke()
        self.serving_model = "model-2"
        with self.assertRaises(HermesFabricError):
            self.invoke(NativeCall("session-1", "task-1", "turn-1", "api-2"))
        self.assertTrue(self.owner._uncertain)
        with self.assertRaises(HermesFabricError):
            self.invoke(NativeCall("session-1", "task-1", "turn-1", "api-3"))
        self.assertEqual(len(self.calls), 2)

    def test_auto_request_overrides_cannot_expand_output_ceiling(self):
        self.binding._max_output_tokens = 128
        with self.assertRaises(HermesFabricError):
            self.invoke(max_completion_tokens=129)
        self.assertEqual(self.calls, [])


class ExactOwnerTests(unittest.TestCase):
    def setUp(self):
        original.OwnerLoopbackTests.setUp(self)
        scope, digest = validate_auto_route_scope({"schema": "mastermind.application_route_scope.v1", "pools": ["go"]})
        self.auto_inspection = dict(schema="mastermind.fabric_application_inspection.v3", requested_model="model-1",
            route_scope=scope, route_scope_digest=digest, output_limit_mode="hard_maximum",
            cap_id="fabric:fixture", capability_id="fabric_fixture", workload_policy={"fixture": True},
            transport_identity="b" * 64)
        self.owner = FabricInferenceClient(base_url=f"http://127.0.0.1:{self.server.server_port}/v1",
            proxy_token="t" * 40, model="model-1", protocol=NATIVE_PROTOCOL, operation_id="owner-turn-1",
            auto_inspection=self.auto_inspection)
        self.binding._owner = self.owner
        self.binding.automatic = True
        self.binding.model = self.binding.requested_model = "model-1"

    tearDown = original.OwnerLoopbackTests.tearDown

    def invoke(self, call=None, **extra):
        with call_scope(self.binding, call or self.call):
            return HermesApplicationClient().create(model="model-1",
                messages=[{"role": "user", "content": "Read"}], **extra)

    def refuse_route(self, changes):
        self.route_overrides = changes
        with self.assertRaises(HermesFabricError):
            self.invoke()
        with self.assertRaises(HermesFabricError):
            self.invoke(NativeCall("session-1", "task-1", "turn-1", "api-2"))
        self.assertEqual(len(self.calls), 1)

    def test_concrete_original_model_and_no_substituted_digest(self):
        result = self.invoke(max_tokens=128)
        route = result.application_observation.model_dump()["routing"]
        self.assertEqual(self.calls[0]["payload"]["model"], "model-1")
        self.assertEqual((result.model, route["requested_model"], route["selected_model"]), ("model-1",) * 3)
        self.assertEqual(route["schema"], "mastermind.fabric_application_route.v2")
        self.assertIsNone(route["routed_request_digest"])

    def test_exact_route_cannot_downgrade_to_auto_schema(self):
        self.refuse_route({"schema": "mastermind.fabric_application_route.v1"})

    def test_exact_route_cannot_change_requested_model(self):
        self.refuse_route({"requested_model": "model-2"})

    def test_exact_route_cannot_invent_a_routed_digest(self):
        self.refuse_route({"routed_request_digest": "c" * 64})

    def test_exact_route_cannot_escape_qualified_pool(self):
        self.refuse_route({"pool": "bailian"})

    def test_actual_serving_model_must_match_exact_selection(self):
        self.serving_model = "model-2"
        self.refuse_route({})

    def test_native_selection_and_output_overrides_refuse_before_send(self):
        self.binding._max_output_tokens = 128
        with call_scope(self.binding, self.call), self.assertRaises(HermesFabricError):
            HermesApplicationClient().create(model="model-2", messages=[])
        with self.assertRaises(HermesFabricError):
            self.invoke(max_tokens=129)
        self.assertEqual(self.calls, [])

    def test_post_tool_429_cannot_replay_or_reuse_previous_observation(self):
        self.mode = "tools"
        result = self.invoke(tools=[{"type": "function", "function": {"name": "read", "parameters": {}}}])
        self.assertEqual(result.choices[0].message.tool_calls[0].id, "tool-original")
        first = result.application_observation.model_dump()
        self.mode = "429-refused"
        with self.assertRaises(HermesFabricError):
            self.invoke(NativeCall("session-1", "task-1", "turn-1", "api-2"))
        with self.assertRaises(HermesFabricError):
            self.invoke(NativeCall("session-1", "task-1", "turn-1", "api-3"))
        self.assertEqual(len(self.calls), 2)
        self.assertNotEqual(first["request_id"], self.calls[1]["request_id"])
