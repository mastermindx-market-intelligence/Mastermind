"""Cross-pool AUTO through the real B/A owners; only provider evidence is synthetic."""
from concurrent.futures import ThreadPoolExecutor
import copy
from dataclasses import replace
import hashlib
import http.client
import json
import unittest
from unittest.mock import patch

from test_application_registered_pool_composition import RegisteredPoolCompositionFixture, SERVICE_TOKEN
from test_application_registered_pool_selection import RegisteredPoolFixture, POOL_MODELS
from test_application_auto_request import digest
import lease_broker
import pick
from go_lease_gateway import ApplicationSelectionRefused


def route_scope(pools):
    return {"schema": "mastermind.application_route_scope.v1", "pools": sorted(pools)}


class CrossPoolOwnerTests(RegisteredPoolFixture):
    def test_all_nine_registered_pools_use_closed_v2_scope_and_actual_picker(self):
        for pool, (model, _, _) in POOL_MODELS.items():
            with self.subTest(pool=pool):
                payload = self.payload_for(pool, model=None)
                scope = route_scope([pool])
                selected = self.gateway.select_application(
                    {"workload": "site_interactive", "turn_id": "auto-" + pool,
                     "pool": "go", "model": None},
                    principal_id="macro", host="vps", credential_ref="MACRO_APPLICATION_TOKEN",
                    purpose=self.purpose_for(pool), payload=payload,
                    route_scope=scope, transport_candidates=frozenset({(pool, model)}))
                self.assertEqual(selected["schema"], "mastermind.application_turn_selection.v2")
                self.assertEqual(selected["identity"]["pool"], pool)
                self.assertEqual(selected["identity"]["model"], model)
                self.assertEqual(selected["route_scope"], scope)
                self.assertEqual(selected["route_scope_digest"], lease_broker._application_route_scope(scope)[1])
        self.assertEqual(self.rows("leases"), [])

    def test_route_scope_is_a_restriction_and_never_creates_a_grant_or_route(self):
        self.document["application_grants"] = []
        self.save()
        with self.assertRaises(ApplicationSelectionRefused):
            self.gateway.select_application(
                {"workload": "site_interactive", "turn_id": "absent", "pool": "go", "model": None},
                principal_id="macro", host="vps", credential_ref="MACRO_APPLICATION_TOKEN",
                purpose=self.purpose_for("go"), payload=self.payload_for("go", model=None),
                route_scope=route_scope(["go"]), transport_candidates=frozenset({("go", "invented")}))
        self.assertEqual(self.rows("leases"), [])

    def test_scope_and_transport_mask_are_closed_and_explicit(self):
        invalid = [{}, {"schema": "mastermind.application_route_scope.v1", "pools": []},
            route_scope(["native"]), route_scope(["go", "go"]),
            {"schema": "mastermind.application_route_scope.v1", "pools": ["go", "bailian"]},
            dict(route_scope(["go"]), account="account-a")]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(lease_broker.ApplicationSelectionError):
                lease_broker._application_route_scope(value)
        for mask in (None, [("go", "fixture-model")], frozenset({"go"})):
            with self.subTest(mask=mask), self.assertRaises(ApplicationSelectionRefused):
                self.gateway.select_application(
                    {"workload": "site_interactive", "turn_id": "invalid", "pool": "go", "model": None},
                    principal_id="macro", host="vps", credential_ref="MACRO_APPLICATION_TOKEN",
                    purpose=self.purpose_for("go"), payload=self.payload_for("go", model=None),
                    route_scope=route_scope(["go"]), transport_candidates=mask)
        self.assertEqual(self.rows("leases"), [])


class CrossPoolHTTPFixture(RegisteredPoolCompositionFixture):
    def setUp(self):
        super().setUp()
        for grant in self.document["application_grants"]:
            grant["credential_ref"] = "MACRO_APPLICATION_TOKEN"
        self.save()
        self.auto_payload = {"model": None, "messages": [
            {"role": "system", "content": "Fixture system."},
            {"role": "user", "content": "Fixture question."}],
            "stream": False, "max_tokens": 128}
        self.configure(["go", "bailian", "codex-native"])

    def configure(self, pools, *, purpose=True, bindings=True, service_pool="go"):
        service = self.go.ApplicationServiceBinding("macro", "vps", "site_interactive",
            "MACRO_APPLICATION_TOKEN", SERVICE_TOKEN, pool=service_pool,
            selection_purpose=self.go.ApplicationSelectionPurpose(self.purposes["go"]) if purpose else None,
            route_scope=self.go.ApplicationRouteScope(route_scope(pools)) if pools is not None else None)
        self.server.shutdown()
        self.server.server_close()
        self.server = self.go.make_server(self.router, lease_gateway=self.gateway,
            application_services=(service,), application_http_binding=self.http_binding,
            application_native_bindings=(self.native_binding,) if bindings else (),
            worker_capabilities_enabled=False)
        self.server.handle_error = lambda *args: None
        self._serve(self.server)
        self.expected_scope_digest = service.route_scope.digest if service.route_scope else None
        return service

    def auto_request(self, turn="auto", *, step="step-1", payload=None, scope_digest="current"):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        supplied = {"Authorization": "Bearer " + SERVICE_TOKEN, "Content-Type": "application/json",
            "Connection": "close", "X-MM-Application-Turn-ID": turn, "Idempotency-Key": step}
        expected = self.expected_scope_digest if scope_digest == "current" else scope_digest
        value = self.auto_payload if payload is None else payload
        if expected is not None and value.get("model") is None:
            supplied["X-MM-Application-Route-Scope-Digest"] = expected
        try:
            connection.request("POST", "/v1/chat/completions",
                json.dumps(self.auto_payload if payload is None else payload).encode(), supplied)
            response = connection.getresponse()
            raw = response.read()
            result_headers = dict(response.getheaders())
            result_headers["Fixture-Body-SHA256"] = hashlib.sha256(raw).hexdigest()
            return response.status, json.loads(raw), result_headers
        finally:
            connection.close()


class CrossPoolHTTPTests(CrossPoolHTTPFixture):
    def test_same_service_token_dispatches_three_pools_with_frozen_original_and_actual_result(self):
        for pool in ("go", "bailian", "codex-native"):
            with self.subTest(pool=pool):
                self.configure([pool])
                if self.responses[pool] is not None:
                    self.response = self.responses[pool]
                status, body, headers = self.auto_request("auto-" + pool)
                self.assertEqual(status, 200, body)
                state = body["application"]
                self.assertEqual(state["schema"], "mastermind.fabric_application.v2")
                route = state["routing"]
                model = self.payloads[pool]["model"]
                self.assertEqual((route["pool"], route["selected_model"], body["model"]), (pool, model, model))
                self.assertIsNone(route["requested_model"])
                self.assertEqual(route["request_digest"], digest(self.auto_payload))
                self.assertEqual(route["routed_request_digest"], digest(dict(self.auto_payload, model=model)))
                self.assertEqual(route["output_contract"], {"mode": "hard_maximum", "max_tokens": 128})
                row = next(r for r in self.rows("application_requests") if r["turn_id"] == "auto-" + pool)
                self.assertEqual(row["routed_request_digest"], route["routed_request_digest"])
                terminal = json.loads(row["terminal_receipt"])
                if pool != "go":
                    self.assertEqual(terminal["delivery_digest"], headers["Fixture-Body-SHA256"])
                turn = next(r for r in self.rows("application_turns") if r["turn_id"] == row["turn_id"])
                self.assertEqual(turn["selection_digest"], route["selection_digest"])
                self.assertEqual(state["serving_model"], model)
                self.assertNotIn("account", route)
                self.assertNotIn("grant_id", route)
                self.assertEqual(self.close("auto-" + pool)[0], 200)
        self.assertEqual((len(self.posts), len(self.dispatches)), (2, 1))
        self.assertIsNone(self.auto_payload["model"])
        self.assertTrue(all(json.loads(post[1])["model"] is not None for post in self.posts))

    def test_request_recovery_precedes_removed_scope_purpose_grants_and_native_executor(self):
        self.configure(["codex-native"])
        self.assertEqual(self.auto_request()[0], 200)
        self.document["application_grants"] = []
        self.save()
        self.configure(None, purpose=False, bindings=False)
        with patch.object(self.gateway, "select_application", side_effect=AssertionError("repick")), \
             patch.object(self.gateway, "application_registered_routes", side_effect=AssertionError("current routes")):
            status, body, _ = self.auto_request()
            self.assertEqual(status, 409, body)
            self.assertEqual(body["application"]["disposition"], "terminal_receipt_only")
            self.assertNotIn("usage", body["application"])
            self.assertEqual(self.auto_request(step="step-2")[0], 409)
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(self.close("auto")[0], 200)

    def test_changed_scope_cannot_move_existing_turn_but_original_remains_recoverable(self):
        self.configure(["go"])
        self.assertEqual(self.auto_request()[0], 200)
        self.configure(["go", "codex-native"])
        status, body, _ = self.auto_request(step="step-2")
        self.assertEqual(status, 503, body)
        self.assertEqual(body["application"]["disposition"], "effect_unknown")
        self.assertEqual(self.auto_request()[1]["application"]["disposition"], "terminal_receipt_only")
        self.assertEqual((len(self.posts), len(self.dispatches)), (1, 0))
        self.assertEqual(len(self.rows("leases")), 1)

    def test_missing_scope_and_nonhard_contract_refuse_before_admission(self):
        self.configure(None)
        self.assertEqual(self.auto_request()[0], 409)
        self.configure(["go", "codex-native"])
        values = [dict(self.auto_payload, max_tokens=None), dict(self.auto_payload, max_tokens=True),
            dict(self.auto_payload, max_tokens=32769), dict(self.auto_payload, preferred_tokens=50)]
        absent = dict(self.auto_payload)
        absent.pop("model")
        values += [absent, dict(self.auto_payload, model=""), dict(self.auto_payload, model="auto")]
        for value in values:
            with self.subTest(value=value):
                self.assertGreaterEqual(self.auto_request(payload=value)[0], 400)
        self.assert_no_effect()

    def test_native_grammar_and_missing_callback_are_excluded_before_picker(self):
        self.configure(["go", "codex-native"])
        payload = dict(self.auto_payload, tools=[{"type": "function", "function": {
            "name": "fixture", "parameters": {"type": "object"}}}], tool_choice="auto")
        original = pick.select_application
        catalogues = []
        def select(*args, **kwargs):
            catalogues.append(copy.deepcopy(kwargs["catalogue"]))
            return original(*args, **kwargs)
        with patch.object(pick, "select_application", side_effect=select):
            status, body, _ = self.auto_request("tools", payload=payload)
        self.assertEqual(status, 200, body)
        self.assertEqual(body["application"]["routing"]["pool"], "go")
        self.assertNotIn("codex-native", catalogues[0]["pools"])
        self.assertEqual(self.compilations, [])
        self.configure(["go", "codex-native"], bindings=False)
        with patch.object(pick, "select_application", side_effect=select):
            self.assertEqual(self.auto_request("missing")[0], 200)
        self.assertNotIn("codex-native", catalogues[-1]["pools"])

    def test_lost_native_begin_ack_recovers_logical_null_and_admits_only_once(self):
        self.configure(["codex-native"])
        actual = self.gateway.begin_application
        def lost(*args, **kwargs):
            actual(*args, **kwargs)
            raise OSError("lost ACK")
        with patch.object(self.gateway, "begin_application", side_effect=lost):
            status, body, _ = self.auto_request()
        self.assertEqual((status, body["application"]["disposition"]), (503, "effect_unknown"))
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(self.dispatches, [])
        with patch.object(self.gateway, "select_application", side_effect=AssertionError("repick")):
            self.assertEqual(self.auto_request()[0], 200)
        self.assertEqual((len(self.rows("leases")), len(self.dispatches)), (1, 1))

    def test_lost_prepare_ack_never_regenerates_native_permit(self):
        self.configure(["codex-native"])
        actual = self.gateway.prepare_application
        def lost(*args, **kwargs):
            actual(*args, **kwargs)
            raise OSError("lost ACK")
        with patch.object(self.gateway, "prepare_application", side_effect=lost):
            status, body, _ = self.auto_request()
        self.assertEqual(body["application"]["disposition"], "pending")
        with patch.object(self.gateway, "select_application", side_effect=AssertionError("repick")):
            self.assertEqual(self.auto_request()[1]["application"]["disposition"], "pending")
        self.assertEqual((len(self.rows("application_requests")), len(self.compilations), len(self.dispatches)), (1, 1, 0))

    def test_lost_terminal_ack_uses_exact_original_receipt(self):
        self.configure(["codex-native"])
        actual = self.gateway.complete_application
        writes = []
        def lost(*args, **kwargs):
            writes.append(args[0])
            actual(*args, **kwargs)
            raise OSError("lost ACK")
        with patch.object(self.gateway, "complete_application", side_effect=lost):
            status, body, _ = self.auto_request()
        self.assertEqual(status, 200, body)
        self.assertEqual((len(writes), len(self.dispatches)), (1, 1))
        self.assertEqual(self.auto_request()[1]["application"]["disposition"], "terminal_receipt_only")

    def test_same_request_concurrency_has_one_native_invocation(self):
        self.configure(["codex-native"])
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(lambda _: self.auto_request(), range(3)))
        self.assertEqual(sum(status == 200 for status, _, _ in results), 1, results)
        self.assertEqual((len(self.rows("leases")), len(self.rows("application_requests")), len(self.dispatches)), (1, 1, 1))

    def test_selected_http_model_mismatch_keeps_actual_usage_and_both_identities(self):
        self.configure(["go"])
        self.response = dict(self.go_response, model="actually-served-other")
        status, body, _ = self.auto_request()
        self.assertEqual(status, 502, body)
        state = body["application"]
        self.assertEqual(state["routing"]["selected_model"], "fixture-model")
        self.assertEqual(state["serving_model"], "actually-served-other")
        self.assertEqual(state["usage"]["input_tokens"], self.go_response["usage"]["prompt_tokens"])
        self.assertEqual(self.rows("application_requests")[0]["state"], "terminal")
        self.assertNotIn("choices", body)

    def test_selection_race_adopts_original_different_pool_without_repicking(self):
        scope = route_scope(["go", "codex-native"])
        self.configure(scope["pools"])
        actual = self.gateway.select_application
        selections = []
        def race(request, **kwargs):
            selections.append(request)
            winner = actual(request, **dict(kwargs,
                transport_candidates=frozenset({("codex-native", "fixture-native")})))
            self.gateway.begin_application(dict(request, pool="codex-native", model="fixture-native"),
                principal_id="macro", host="vps", expected_credential_ref="MACRO_APPLICATION_TOKEN",
                expected_recipe_digest=self.recipe_digest, expected_selection=winner,
                selection_purpose=self.purposes["go"], selection_payload=self.auto_payload,
                selection_route_scope=scope)
            raise ApplicationSelectionRefused("concurrent last-slot observation")
        with patch.object(self.gateway, "select_application", side_effect=race):
            status, body, _ = self.auto_request()
        self.assertEqual(status, 200, body)
        self.assertEqual(body["application"]["routing"]["pool"], "codex-native")
        self.assertEqual((len(selections), len(self.rows("leases")), len(self.dispatches), len(self.posts)),
                         (1, 1, 1, 0))

    def test_failed_begin_reconciles_different_pool_original_before_known_refusal(self):
        scope = route_scope(["go", "codex-native"])
        self.configure(scope["pools"])
        request = {"workload": "site_interactive", "turn_id": "auto", "pool": "go", "model": None}
        winner = self.gateway.select_application(request, principal_id="macro", host="vps",
            credential_ref="MACRO_APPLICATION_TOKEN", purpose=self.purposes["go"],
            payload=self.auto_payload, route_scope=scope,
            transport_candidates=frozenset({("codex-native", "fixture-native")}))
        actual_select, actual_begin = self.gateway.select_application, self.gateway.begin_application
        def choose_go(request, **kwargs):
            return actual_select(request, **dict(kwargs,
                transport_candidates=frozenset({("go", "fixture-model")})))
        attempts = []
        def racing_begin(request, **kwargs):
            attempts.append(request)
            actual_begin(dict(request, pool="codex-native", model="fixture-native"),
                **dict(kwargs, expected_recipe_digest=self.recipe_digest, expected_selection=winner))
            raise ApplicationSelectionRefused("losing candidate")
        with patch.object(self.gateway, "select_application", side_effect=choose_go), \
             patch.object(self.gateway, "begin_application", side_effect=racing_begin):
            status, body, _ = self.auto_request()
        self.assertEqual((status, body["application"]["disposition"]), (503, "effect_unknown"))
        self.assertEqual((len(attempts), len(self.rows("leases")), len(self.posts), len(self.dispatches)),
                         (1, 1, 0, 0))
        with patch.object(self.gateway, "select_application", side_effect=AssertionError("repick")):
            status, body, _ = self.auto_request()
        self.assertEqual(status, 200, body)
        self.assertEqual(body["application"]["routing"]["pool"], "codex-native")
        self.assertEqual((len(self.rows("leases")), len(self.dispatches)), (1, 1))

    def test_reserved_upstream_application_field_is_terminal_error_with_usage(self):
        self.configure(["go"])
        self.response = dict(self.go_response, application={"untrusted": "reserved"})
        status, body, _ = self.auto_request()
        self.assertEqual(status, 502, body)
        self.assertEqual(body["application"]["disposition"], "terminal")
        self.assertEqual(body["application"]["routing"]["selected_model"], "fixture-model")
        self.assertEqual(body["application"]["usage"]["input_tokens"],
                         self.go_response["usage"]["prompt_tokens"])
        self.assertEqual(self.rows("application_requests")[0]["state"], "terminal")
        self.assertNotIn("choices", body)
        self.assertEqual(self.auto_request()[1]["application"]["disposition"], "terminal_receipt_only")
        self.assertEqual(len(self.posts), 1)

    def test_scope_commitment_refuses_before_selection_but_cannot_erase_original(self):
        self.configure(["go"])
        with patch.object(self.gateway, "select_application", side_effect=AssertionError("scope not checked")):
            self.assertEqual(self.auto_request(scope_digest="0" * 64)[0], 409)
            self.assertEqual(self.auto_request(scope_digest=None)[0], 409)
        self.assert_no_effect()
        self.assertEqual(self.auto_request()[0], 200)
        with patch.object(self.gateway, "select_application", side_effect=AssertionError("recovery repick")):
            self.assertEqual(self.auto_request(scope_digest="0" * 64)[1]["application"]["disposition"],
                             "terminal_receipt_only")

    def test_scope_object_is_frozen_and_fixed_requests_keep_existing_wire(self):
        service = self.configure(["go"])
        with self.assertRaises(AttributeError):
            service.route_scope.digest = "changed"
        copied = service.route_scope.document
        copied["pools"].append("codex-native")
        self.assertEqual(service.route_scope.document["pools"], ["go"])
        status, body, _ = self.auto_request(payload=dict(self.auto_payload, model="fixture-model"))
        self.assertEqual(status, 200, body)
        self.assertNotIn("application", body)
        self.assertIsNone(self.rows("application_requests")[0]["routed_request_digest"])
