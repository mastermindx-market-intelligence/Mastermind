"""AUTO translation through the actual incumbent client and loopback endpoint."""
import unittest

from engine.fabric_inference_client import FabricInferenceClient, NATIVE_PROTOCOL, validate_auto_route_scope
from integrations.hermes_application_fabric import HermesFabricError, NativeCall
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
