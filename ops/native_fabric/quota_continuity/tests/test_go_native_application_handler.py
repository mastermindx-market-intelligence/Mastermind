"""Native APPLICATION authentication, closed grammar and startup boundaries."""
import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import http.client
import inspect
import json
import unittest
from unittest.mock import patch

from test_go_native_application_composition import NativeFixedHTTPFixture
from go_lease_capability import NATIVE_APPLICATION_POOLS


class NativeApplicationHandlerTests(NativeFixedHTTPFixture):
    def test_all_native_pool_names_are_structural_only_and_do_not_grant_execution(self):
        for pool in NATIVE_APPLICATION_POOLS:
            service = replace(self.service, pool=pool)
            self.restart_native(service=service)
            self.assertEqual(self.request()[0], 503)
        self.assertEqual(self.rows("leases"), [])
        self.assertEqual(self.dispatches, [])

    def test_default_main_and_server_register_no_native_executor(self):
        self.assertEqual(inspect.signature(self.go.main).parameters["application_native_bindings"].default, ())
        self.assertEqual(inspect.signature(self.go.make_server).parameters["application_native_bindings"].default, ())
        self.restart_native()
        self.assertEqual(self.request()[0], 503)
        self.assertEqual(self.rows("leases"), [])

    def test_worker_and_all_application_capabilities_cannot_be_service_credentials(self):
        for prefix in ("v1.", "app1.", "app2.", "app3.", "appd1."):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                replace(self.service, credential=prefix + "x" * 40)
            self.assertEqual(self.request(token=prefix + "x" * 40)[0], 401)
        self.assertNotIn(self.service.credential, repr(self.service))
        self.assertEqual(self.rows("leases"), [])

    def test_fake_or_duplicate_binding_cannot_register(self):
        class Subclass(self.go.ApplicationNativeBinding):
            pass
        for values in ([self.native_binding], ({"recipe": self.recipe},),
                       (Subclass(recipe=self.recipe, accounts=self.native_binding.accounts,
                           preflight=self.compile_native, execute=self.execute_native),),
                       (self.native_binding, self.native_binding)):
            with self.subTest(kind=type(values).__name__), self.assertRaises(ValueError):
                self.go.make_server(self.router, lease_gateway=self.gateway,
                    application_services=(self.service,), application_native_bindings=values)
        self.assertEqual(self.rows("leases"), [])

    def test_recipe_source_or_account_projection_mismatch_refuses_at_startup(self):
        recipe = copy.deepcopy(self.recipe)
        recipe["source_generation"] = "f" * 64
        for binding in (self.make_binding(recipe=recipe), self.make_binding(accounts=frozenset({"account-a"}))):
            with self.assertRaises(ValueError):
                self.go.make_server(self.router, lease_gateway=self.gateway,
                    application_services=(self.service,), application_native_bindings=(binding,))
        self.assertEqual(self.rows("leases"), [])

    def test_startup_recipe_and_compiler_products_are_deeply_immutable(self):
        changed = self.native_binding.recipe
        changed["limits"]["max_steps"] = 64
        self.assertEqual(self.native_binding.recipe["limits"]["max_steps"], 2)
        with self.assertRaises(FrozenInstanceError):
            self.native_binding.recipe_digest = "f" * 64
        product = self.compile_native(recipe=self.recipe, account="account-a", payload=self.payload)
        changed = product.commitment
        changed["physical_host"] = "other-host"
        self.assertEqual(product.commitment["physical_host"], self.recipe["physical_host"])
        with self.assertRaises(FrozenInstanceError):
            product.input_bytes = b"different"

    def test_native_grammar_rejects_tools_history_media_sampling_and_unknown_fields(self):
        alternatives = [
            {**self.payload, "tools": []}, {**self.payload, "reasoning_effort": "none"},
            {**self.payload, "temperature": 0}, {**self.payload, "top_p": 1},
            {**self.payload, "stream": True}, {**self.payload, "stream": 0},
            {**self.payload, "resume": "old"}, {**self.payload, "pool": "go"},
            {**self.payload, "messages": self.payload["messages"] + [{"role": "assistant", "content": "history"}]},
            {**self.payload, "messages": [{"role": "user", "content": [{"type": "text", "text": "media"}]}]},
            {**self.payload, "messages": [{"role": "assistant", "content": "wrong role"}]},
            {**self.payload, "messages": [{"role": "user", "content": "a", "name": "other"}]},
            {**self.payload, "messages": [{"role": "user", "content": "a\x00b"}]},
            {**self.payload, "max_tokens": True}, {**self.payload, "max_tokens": 0},
            {**self.payload, "max_tokens": 1025}, {**self.payload, "preferred_tokens": 128},
        ]
        for payload in alternatives:
            with self.subTest(payload=payload):
                self.assertEqual(self.request(payload=payload)[0], 400)
        missing = copy.deepcopy(self.payload)
        missing.pop("max_tokens")
        self.assertEqual(self.request(payload=missing)[0], 400)
        self.assertEqual((self.rows("leases"), self.compilations, self.dispatches), ([], [], []))

    def test_hard_maximum_is_not_silently_converted_to_preference(self):
        value = copy.deepcopy(self.payload)
        value["preferred_tokens"] = value.pop("max_tokens")
        self.assertEqual(self.request(payload=value)[0], 400)
        self.assertEqual(self.rows("leases"), [])

    def test_explicit_wrong_recipe_is_refused_before_admission(self):
        self.assertEqual(self.request(headers={"X-MM-Application-Recipe-Digest": "f" * 64})[0], 400)
        self.assertEqual((self.rows("leases"), self.compilations, self.dispatches), ([], [], []))

    def test_duplicate_auth_recipe_or_original_identity_headers_refuse(self):
        for duplicate in ("Authorization", "X-MM-Application-Recipe-Digest", "Idempotency-Key", "X-MM-Application-Turn-ID"):
            connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
            body = json.dumps(self.payload).encode()
            connection.putrequest("POST", "/v1/chat/completions")
            headers = {"Authorization": "Bearer " + self.service.credential, "Idempotency-Key": "step-1",
                "X-MM-Application-Turn-ID": "turn-1", "X-MM-Application-Recipe-Digest": self.recipe_digest,
                "Content-Length": str(len(body)), "Connection": "close"}
            for key, value in headers.items():
                connection.putheader(key, value)
                if key == duplicate:
                    connection.putheader(key, value)
            connection.endheaders(body)
            response = connection.getresponse()
            self.assertIn(response.status, (400, 401))
            response.read()
            connection.close()
        self.assertEqual(self.rows("leases"), [])

    def test_service_cannot_select_private_authority_or_use_controller_routes(self):
        for name in ("X-MM-Pool-Account", "X-MM-Host", "X-MM-Principal", "X-MM-Workload", "X-MM-Run-Id"):
            self.assertEqual(self.request(headers={name: "caller-chosen"})[0], 400)
        for path in ("/reenable", "/worker-capabilities", "/v1/responses", "/application-bind"):
            self.assertEqual(self.request(path=path)[0], 400)
        self.assertEqual(self.rows("leases"), [])

    def test_authenticated_credential_and_application_grant_remain_required(self):
        self.grant["credential_ref"] = "ANOTHER_SERVICE_REF"
        self.save()
        self.assertEqual(self.request()[0], 503)
        self.assertEqual((self.rows("leases"), self.compilations, self.dispatches), ([], [], []))

    def test_preflight_account_mismatch_keeps_admitted_lease_and_never_prepares(self):
        self.preflight_transform = lambda value: self.go.ApplicationNativePreflight(
            "not-admitted", value.input_bytes, value.commitment)
        self.assertEqual(self.request()[0], 503)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual((self.rows("application_requests"), self.dispatches), ([], []))
        self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})
        self.assertEqual(self.request(path="/application-turns/close", payload={"turn_id": "turn-1"})[0], 200)

    def test_preflight_source_or_input_change_never_prepares(self):
        def different(value):
            commitment = value.commitment
            commitment["compiler_sha256"] = "e" * 64
            return self.go.ApplicationNativePreflight(value.account, value.input_bytes, commitment)
        self.preflight_transform = different
        self.assertEqual(self.request()[0], 503)
        self.assertEqual((self.rows("application_requests"), self.dispatches), ([], []))
        data = b"changed input"
        commitment = self.native_commitment()
        with self.assertRaises(ValueError):
            self.go.ApplicationNativePreflight("account-a", data, commitment)
        commitment["input_sha256"] = hashlib.sha256(data).hexdigest()
        self.preflight_transform = lambda value: self.go.ApplicationNativePreflight(value.account, data, commitment)
        self.assertEqual(self.request()[0], 503)
        self.assertEqual((self.rows("application_requests"), self.dispatches), ([], []))

    def test_revoked_grant_after_pure_preflight_never_crosses_external_boundary(self):
        def revoke(value):
            self.grant["enabled"] = False
            self.save()
            return value
        self.preflight_transform = revoke
        self.assertEqual(self.request()[0], 503)
        self.assertEqual(self.dispatches, [])
        self.assertEqual(self.rows("application_requests"), [])
        self.assertEqual(len(self.rows("leases")), 1)

    def test_existing_pending_recovery_precedes_current_compiler_readiness(self):
        binding = self.native_begin(turn="turn-1")
        self.native_prepare(binding, request_id="step-1")
        self.restart_native()
        self.assertEqual(self.request()[1]["application"]["disposition"], "pending")
        self.assertEqual((self.compilations, self.dispatches), ([], []))

    def test_close_is_scoped_to_authenticated_service_workload(self):
        self.assertEqual(self.request()[0], 200)
        self.restart_native(service=replace(self.service, workload="different-workload"))
        self.assertEqual(self.request(path="/application-turns/close", payload={"turn_id": "turn-1"})[0], 503)
        self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})


if __name__ == "__main__":
    unittest.main()
