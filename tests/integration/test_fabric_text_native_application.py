"""Mastermind text availability and calls through actual Macro/native owners."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from brain import fabric_inference


_spec = importlib.util.spec_from_file_location("_text_native_fixture_helpers",
    Path(__file__).with_name("test_fabric_chat_buffered_delivery.py"))
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)


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
        import yaml
        _helpers.BufferedNativeChatTests.setUp(self)
        manifest = yaml.safe_load(self.config_paths[1].read_text())
        manifest["capabilities"][0]["allowed_lanes"] = ["mastermind-text"]
        self.config_paths[1].write_text(yaml.safe_dump(manifest))
        self.start(patch.dict(os.environ, {"MM_PROVIDER_WORKLOAD_PROFILE": "site_batch"}))

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
        document["application_fabric_modes"]["shared_fabric"]["enabled"] = False
        self.config_paths[0].write_text(json.dumps(document))
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("credential")):
            self.assertFalse(fabric_inference.available())
            self.assertEqual(fabric_inference.call_model("s", "u"),
                             (None, "fabric_binding_unavailable"))
        self.assertEqual(self.native.posts, [])
        self.assertEqual(self.native.rows("leases"), [])


if __name__ == "__main__":
    unittest.main()
