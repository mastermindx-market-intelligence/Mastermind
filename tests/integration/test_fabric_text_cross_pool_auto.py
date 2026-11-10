"""AUTO application inference through actual Mastermind, C, B and A owners.

Only source qualification, service grants and provider observations are
synthetic. Requests, translation, routing, SQLite admission, settlement, usage,
recovery and close use the incumbent owners and actual loopback HTTP.
"""
from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from brain import client, fabric_inference, thinking_log

_spec = importlib.util.spec_from_file_location("_auto_chat_fixture_helpers",
    Path(__file__).with_name("test_fabric_chat_buffered_delivery.py"))
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)

# Exact H4 GLM APPLICATION carrier d23c662b; historical input pins remain unchanged.
PINS = {
    "candidate/lease_broker.py": "cbb135641aa9d9509714fdb3587f6f0088d5d65b",
    "candidate/go_lease_gateway.py": "9666d2c10c6dd2044a0ea783c534b58b8fe52f34",
    "candidate/go_shim.py": "6a396f8fedc2f3d44604b07e5a09c3c3ba329579",
    "tests/test_application_cross_pool_auto.py": "0d70a47906a23176d5eaed71a4575e925a500341",
}


class AutoTextApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _helpers.BufferedNativeChatTests.setUpClass.__func__(cls)
        root = Path(__file__).resolve().parents[2] / "ops/native_fabric/quota_continuity"
        for name, expected in PINS.items():
            raw = (root / name).read_bytes()
            assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == expected, name
        from test_application_cross_pool_auto import CrossPoolHTTPFixture
        cls.fixture_class = CrossPoolHTTPFixture

    @classmethod
    def tearDownClass(cls):
        _helpers.BufferedNativeChatTests.tearDownClass.__func__(cls)

    def start(self, patcher):
        self.addCleanup(patcher.stop)
        return patcher.start()

    def setUp(self):
        import yaml
        from engine import fabric_inference_client as transport
        self.transport = transport
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.native = self.fixture_class()
        self.native.setUp()
        self.addCleanup(self.native.doCleanups)
        for grant in self.native.document["application_grants"]:
            grant.update(principal_id="mastermind-text", admission_root="service:mastermind-text",
                         workloads=["site_batch"])
        self.native.save()
        self.logs, self.closes = [], []
        self.start(patch.dict(os.environ, {
            "BOT_LLM_BACKEND": "api", "MM_PROVIDER_APPLICATION_MODE": "shared_fabric",
            "MM_PROVIDER_WORKLOAD_PROFILE": "site_interactive",
            "MACRO_APPLICATION_TOKEN": self.native_module.SERVICE_TOKEN,
            "AI_COSTS_STATE_ROOT": str(self.root / "costs"),
            "PROVIDER_HEALTH_PATH": str(self.root / "health.jsonl"),
        }))
        self.start(patch.object(self.shared, "_oauth_pool_candidates",
                                side_effect=AssertionError("legacy pool")))
        self.start(patch.object(thinking_log, "log_turn_async", side_effect=lambda **kw: self.logs.append(kw)))
        real_close = self.shared.close_fabric_provider
        def close(provider):
            self.closes.append(provider)
            return real_close(provider)
        self.start(patch.object(self.shared, "close_fabric_provider", side_effect=close))
        base = self.owner._APPLICATION_FABRIC_TRANSPORTS["native_fabric_mastermind_text_auto_v1"]
        self.auto_transport = replace(base, secret_ref="MACRO_APPLICATION_TOKEN",
            qualified=True, application_allowed=True)
        self.config_paths[1].write_text(yaml.safe_dump({"capabilities": [{
            "capability_id": base.capability_id, "secret_ref": "MACRO_APPLICATION_TOKEN",
            "kill_state": "active", "allowed_lanes": ["mastermind-text"]}]}))
        self.configure(["go"])

    def configure(self, pools, *, client_pools=None):
        native = self.native
        scope = {"schema": "mastermind.application_route_scope.v1", "pools": sorted(pools)}
        service = native.go.ApplicationServiceBinding(
            "mastermind-text", "vps", "site_batch", "MACRO_APPLICATION_TOKEN",
            self.native_module.SERVICE_TOKEN,
            selection_purpose=native.go.ApplicationSelectionPurpose(native.purposes["go"]),
            route_scope=native.go.ApplicationRouteScope(scope))
        native.server.shutdown()
        native.server.server_close()
        native.server = native.go.make_server(native.router, lease_gateway=native.gateway,
            application_services=(service,), application_http_binding=native.http_binding,
            application_native_bindings=(native.native_binding,), worker_capabilities_enabled=False)
        native.server.handle_error = lambda *args: None
        native._serve(native.server)
        selected = replace(self.auto_transport,
            base_url=f"http://127.0.0.1:{native.server.server_port}/v1")
        self.start(patch.dict(self.owner._APPLICATION_FABRIC_TRANSPORTS,
                             {"native_fabric_mastermind_text_auto_v1": selected}))
        row = {key: getattr(selected, key) for key in self.owner._APPLICATION_IDENTITY_FIELDS}
        row.update(transport_id="native_fabric_mastermind_text_auto_v1",
            route_scope=scope if client_pools is None else {
                "schema": "mastermind.application_route_scope.v1", "pools": sorted(client_pools)},
            enabled=True, application_allowed=True,
            qualification=self.owner.PROFILE_QUALIFIED_CANARY,
            qualification_ref="fixture:auto-text-real-owners", qualified_until=time.time()+3600)
        document = json.loads(self.originals[self.config_paths[0]])
        document["application_fabric_modes"] = {"mastermind_text_fabric": row}
        self.config_paths[0].write_text(json.dumps(document))
        if len(pools) == 1 and native.responses[pools[0]] is not None:
            native.response = copy.deepcopy(native.responses[pools[0]])
        self.scope = scope

    def costs(self):
        return [json.loads(line) for path in (self.root / "costs").rglob("*.jsonl")
                for line in path.read_text().splitlines()]

    def factory(self):
        return self.owner.make_application_fabric_factory(
            mode_id="shared_fabric", lane="mastermind-text", root=self.macro_root,
            workload_cfg={"provider_order": ["fabric"], "workload_profile": "site_batch"},
            service_mode_id="mastermind_text_fabric")

    def bind(self, operation):
        return self.shared.build_fabric_provider(self.factory(), request_id=operation,
            workload_cfg={"provider_order": ["fabric"], "workload_profile": "site_batch"})

    def call(self, provider, maximum=128):
        return self.shared.make_call([provider], lambda client, model: (
            (lambda response: (response.content[0].text, None, response))(
                client.messages.create(model=model, max_tokens=maximum,
                    system="Fixture system.", messages=[{"role": "user", "content": "Fixture question."}]))),
            context="mastermind-text")

    def test_real_text_auto_serves_two_pools_and_records_actual_usage_without_price_guess(self):
        from lib import ai_costs
        expected = {"go": "Fixture answer.", "codex-native": self.native.native_text}
        for pool in expected:
            with self.subTest(pool=pool):
                self.configure([pool])
                with patch.object(ai_costs, "estimate_cost_usd", side_effect=AssertionError("unqualified price")):
                    self.assertTrue(client.available())
                    result = client.call_model("Fixture system.", "Fixture question.", max_tokens=128)
                self.assertEqual(result, (expected[pool], None))
                provider = self.closes[-1]
                self.assertIsNone(provider["model"])
                self.assertIsNone(provider["provider"])
                observation = self.shared.fabric_observation(provider)
                document = observation.document
                route = document["routing"]
                model = self.native.payloads[pool]["model"]
                self.assertEqual((route["pool"], route["selected_model"], document["serving_model"]),
                                 (pool, model, model))
                self.assertEqual(route["route_scope"], self.scope)
                self.assertEqual(self.logs[-1]["provider"], pool)
                self.assertEqual(self.logs[-1]["model"], model)
                cost = self.costs()[-1]
                self.assertEqual((cost["provider"], cost["model"], cost["cost_basis"]), (pool, model, "unknown"))
                self.assertIsNone(cost["est_cost_usd"])
                self.assertEqual(cost["fabric_route"]["selection_digest"], route["selection_digest"])
                self.assertEqual(cost["input_tokens"], document["usage"]["input_tokens"])
                self.assertEqual(cost["output_tokens"], document["usage"]["output_tokens"])
                changed = observation.document
                changed["routing"]["pool"] = "forged"
                self.assertEqual(observation.document["routing"]["pool"], pool)
        self.assertEqual((len(self.native.posts), len(self.native.dispatches)), (1, 1))
        self.assertEqual(len(self.closes), 2)
        self.assertEqual(len(self.costs()), 2)
        self.assertTrue(all(row["state"] == "released" for row in self.native.rows("leases")))
        summary = ai_costs.summarize()
        self.assertEqual(summary["totals_30d"]["unpriced_calls"], 2)
        self.assertEqual(summary["by_cost_basis"]["unknown"]["calls"], 2)
        self.assertNotIn("metered", summary["by_cost_basis"])

    def test_inspection_is_credential_free_closed_and_drift_refuses_before_binding(self):
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("credential")):
            identity = self.factory().inspect()
        self.assertEqual(identity["schema"], "mastermind.fabric_application_inspection.v2")
        self.assertIsNone(identity["requested_model"])
        self.assertNotIn("model", identity)
        bound_factory = self.factory().with_inspection(identity)
        identity["route_scope"]["pools"].append("bailian")
        document = json.loads(self.config_paths[0].read_text())
        document["application_fabric_modes"]["mastermind_text_fabric"]["route_scope"]["pools"] = ["bailian", "go"]
        self.config_paths[0].write_text(json.dumps(document))
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("credential")), \
                self.assertRaises(self.shared.FabricProviderError):
            self.shared.build_fabric_provider(bound_factory, request_id="auto-drift")
        self.assertFalse(self.native.rows("leases"))
        self.assertFalse(self.native.posts)

    def test_first_post_scope_mismatch_refuses_without_admission_or_provider(self):
        self.configure(["bailian"], client_pools=["go"])
        result = client.call_model("s", "u", max_tokens=128)
        self.assertIsNone(result[0])
        self.assertFalse(self.native.rows("leases"))
        self.assertFalse(self.native.posts)
        self.assertFalse(self.native.dispatches)
        self.assertEqual(self.costs(), [])
        self.assertEqual(len(self.closes), 1)

    def test_hard_output_and_explicit_null_are_required_before_io(self):
        for maximum in (0, True, 32769, None):
            with self.subTest(maximum=maximum):
                provider = self.bind("auto-max-" + str(maximum))
                with self.assertRaises(self.shared.FabricProviderError):
                    provider["client"].messages.create(model=None, max_tokens=maximum,
                        messages=[{"role": "user", "content": "u"}])
                self.shared.close_fabric_provider(provider)
        provider = self.bind("auto-model")
        with self.assertRaises(self.shared.FabricProviderError):
            provider["client"].messages.create(model="auto", max_tokens=128,
                messages=[{"role": "user", "content": "u"}])
        self.shared.close_fabric_provider(provider)
        self.assertFalse(self.native.rows("leases"))
        self.assertFalse(self.native.posts)

    def test_intentional_second_step_retains_route_with_a_different_hard_maximum(self):
        provider = self.bind("auto-two-steps")
        first = self.call(provider, 128)
        original = self.shared.fabric_observation(provider).document
        second = self.call(provider, 64)
        final = self.shared.fabric_observation(provider).document
        self.shared.close_fabric_provider(provider)
        self.assertIsNone(first[1])
        self.assertIsNone(second[1])
        self.assertEqual(original["routing"]["selection_digest"], final["routing"]["selection_digest"])
        self.assertNotEqual(original["request_id"], final["request_id"])
        self.assertNotEqual(original["routing"]["request_digest"], final["routing"]["request_digest"])
        self.assertEqual(final["routing"]["output_contract"]["max_tokens"], 64)
        self.assertEqual(len(self.native.rows("leases")), 1)
        self.assertEqual(len(self.native.posts), 2)
        self.assertEqual(len(self.costs()), 2)

    def test_unusable_terminal_model_keeps_actual_usage_and_no_answer(self):
        self.native.response["model"] = "actually-other"
        result = client.call_model("Fixture system.", "Fixture question.", max_tokens=128)
        self.assertIsNone(result[0])
        self.assertEqual(len(self.native.posts), 1)
        cost = self.costs()[0]
        self.assertEqual((cost["provider"], cost["model"]), ("go", "actually-other"))
        self.assertEqual((cost["input_tokens"], cost["output_tokens"]), (11, 7))
        self.assertIsNone(cost["est_cost_usd"])
        observation = self.shared.fabric_observation(self.closes[0]).document
        self.assertEqual(observation["serving_model"], "actually-other")
        self.assertEqual(observation["routing"]["selected_model"], "fixture-model")

    def test_malformed_route_preserves_unattributed_usage_without_answer_or_retry(self):
        handler = self.native.server.RequestHandlerClass
        original = handler._application_routed_result
        def corrupt(handler, observed):
            result = original(handler, observed)
            document = json.loads(result.body)
            document["application"]["routing"]["request_digest"] = "0" * 64
            raw = json.dumps(document, separators=(",", ":")).encode()
            return replace(result, body=raw, delivery_digest=hashlib.sha256(raw).hexdigest())
        with patch.object(handler, "_application_routed_result", corrupt):
            result = client.call_model("Fixture system.", "Fixture question.", max_tokens=128)
        self.assertIsNone(result[0])
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.native.rows("leases")), 1)
        cost = self.costs()[0]
        self.assertEqual((cost["provider"], cost["model"], cost["input_tokens"], cost["output_tokens"]),
                         ("unknown", "fixture-model", 11, 7))
        self.assertNotIn("fabric_route", cost)
        self.assertIsNone(self.shared.fabric_observation(self.closes[0]))

    def test_lost_begin_ack_never_dispatches_or_closes_an_unsettled_original(self):
        actual = self.native.gateway.begin_application
        def lost(*args, **kwargs):
            actual(*args, **kwargs)
            raise OSError("fixture original admission ACK lost")
        with patch.object(self.native.gateway, "begin_application", side_effect=lost):
            result = client.call_model("Fixture system.", "Fixture question.", max_tokens=128)
        self.assertIsNone(result[0])
        self.assertFalse(self.native.posts)
        self.assertFalse(self.native.dispatches)
        self.assertEqual(len(self.native.rows("leases")), 1)
        self.assertEqual(self.costs(), [])
        self.assertEqual(len(self.closes), 1)

    def test_same_request_recovery_observes_original_receipt_without_second_invocation_or_usage(self):
        provider = self.bind("auto-original")
        result = self.call(provider)
        self.assertIsNone(result[1])
        recovered = self.shared.build_fabric_provider(self.factory(), request_id="auto-original",
            prior_admission_possible=True,
            workload_cfg={"provider_order": ["fabric"], "workload_profile": "site_batch"})
        with self.assertRaises(self.shared.FabricProviderError):
            self.call(recovered)
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.costs()), 1)
        self.assertEqual(self.shared.fabric_usage(recovered)["usage_state"], "unknown")
        self.shared.close_fabric_provider(recovered)
        self.shared.close_fabric_provider(provider)

    def test_legacy_omitted_billing_basis_still_uses_existing_price_estimator(self):
        from lib import ai_costs
        with patch.object(ai_costs, "estimate_cost_usd", return_value=0.125) as price:
            self.assertTrue(ai_costs.record_usage(lane="legacy", provider="legacy",
                model="fixture-model", input_tokens=11, output_tokens=7))
        price.assert_called_once()
        self.assertEqual(self.costs()[0]["est_cost_usd"], 0.125)
        self.assertEqual(ai_costs._cost_basis_bucketname({"provider": "claude_oauth"}), "subscription")

    def test_batch_workload_uses_qualified_http_with_exact_original_grant(self):
        self.configure(["bailian"])
        result = client.call_model("Fixture system.", "Fixture question.", max_tokens=128)
        self.assertEqual(result, ("Bailian fixture answer.", None))
        self.assertEqual(len(self.native.posts), 1)
        turn = self.native.rows("application_turns")[0]
        self.assertEqual((turn["principal_id"], turn["workload"]), ("mastermind-text", "site_batch"))
        self.assertEqual(self.costs()[0]["model"], "qwen3.8-flash")
        self.assertIsNone(self.costs()[0]["est_cost_usd"])

    def test_batch_workload_cannot_borrow_an_interactive_grant(self):
        self.configure(["bailian"])
        for grant in self.native.document["application_grants"]:
            grant["workloads"] = ["site_interactive"]
        self.native.save()
        result = client.call_model("Fixture system.", "Fixture question.", max_tokens=128)
        self.assertIsNone(result[0])
        self.assertFalse(self.native.posts)
        self.assertFalse(self.native.rows("leases"))
        self.assertEqual(self.costs(), [])

    def test_malformed_route_type_keeps_observed_usage_unknown_and_unattributed(self):
        handler = self.native.server.RequestHandlerClass
        original = handler._application_routed_result
        def corrupt(handler, observed):
            result = original(handler, observed)
            document = json.loads(result.body)
            document["application"]["routing"]["protocol"] = []
            raw = json.dumps(document, separators=(",", ":")).encode()
            return replace(result, body=raw, delivery_digest=hashlib.sha256(raw).hexdigest())
        with patch.object(handler, "_application_routed_result", corrupt):
            result = client.call_model("Fixture system.", "Fixture question.", max_tokens=128)
        self.assertIsNone(result[0])
        self.assertEqual(len(self.native.posts), 1)
        provider = self.closes[0]
        self.assertTrue(provider["_fabric_failure"].effect_unknown)
        self.assertIsNone(self.shared.fabric_observation(provider))
        cost = self.costs()[0]
        self.assertEqual((cost["provider"], cost["model"], cost["input_tokens"], cost["output_tokens"]),
                         ("unknown", "fixture-model", 11, 7))
        self.assertNotIn("fabric_route", cost)

    def test_legacy_terminal_downgrade_cannot_settle_an_auto_request(self):
        handler = self.native.server.RequestHandlerClass
        original = handler._application_reply
        def downgrade(handler, disposition, **kwargs):
            route = getattr(handler, "application_auto_route", None)
            if route is not None:
                del handler.application_auto_route
            try:
                return original(handler, disposition, **kwargs)
            finally:
                if route is not None:
                    handler.application_auto_route = route
        self.native.response["model"] = "actually-other"
        with patch.object(handler, "_application_reply", downgrade):
            result = client.call_model("Fixture system.", "Fixture question.", max_tokens=128)
        self.assertIsNone(result[0])
        self.assertEqual(len(self.native.posts), 1)
        provider = self.closes[0]
        self.assertTrue(provider["_fabric_failure"].effect_unknown)
        self.assertEqual(self.shared.fabric_usage(provider)["usage_state"], "unknown")
        self.assertIsNone(self.shared.fabric_observation(provider))
        cost = self.costs()[0]
        self.assertEqual((cost["provider"], cost["model"], cost["input_tokens"], cost["output_tokens"]),
                         ("unknown", "actually-other", 11, 7))
        self.assertNotIn("fabric_route", cost)
