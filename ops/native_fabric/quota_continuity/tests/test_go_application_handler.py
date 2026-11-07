"""Authentication, framing and incumbent-route boundaries on the real handler."""
from dataclasses import replace
import http.client
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_go_application_handler_composition as fixtures


class ApplicationBoundaryTests(fixtures.NativeApplicationHTTPFixture):
    def test_controller_worker_and_execution_tokens_are_not_service_credentials(self):
        for token in (fixtures.CONTROLLER_TOKEN, "v1.not-an-application-credential", "app1.not-a-service-credential", "unknown-token"):
            with self.subTest(token_type=token.split(".")[0]):
                self.assertEqual(self.request(token=token)[0], 401)
        self.assertEqual(self.rows("leases"), [])
        self.assertEqual((self.gets, self.posts), ([], []))

    def test_invalid_stream_body_scope_or_identity_refuses_before_any_admission(self):
        for payload in ({**self.payload, "stream": True}, {**self.payload, "stream": 0},
                        {**self.payload, "pool": "go"}, {**self.payload, "account": "account-a"},
                        {**self.payload, "principal_id": "macro"}, {**self.payload, "workload": "site_interactive"},
                        {**self.payload, "temperature": float("nan")}, {**self.payload, "messages": []}):
            with self.subTest(keys=list(payload)):
                self.assertEqual(self.request(payload=payload)[0], 400)
        self.assertEqual(self.request(step="original/id-must-not-be-rewritten")[0], 400)
        self.assertEqual(self.request(headers={"X-MM-Pool-Account": "account-a"})[0], 400)
        self.assertEqual(self.request(raw=b'{"model":"fixture-model","model":"other-model","messages":[]}')[0], 400)
        self.assertEqual(self.request(raw=b'{"model":"fixture-model","temperature":1e309,"messages":[{}]}')[0], 400)
        self.assertEqual(self.request(path="/v1/chat/completions?route=other")[0], 400)
        self.assertEqual(self.rows("leases"), [])
        self.assertEqual((self.gets, self.posts), ([], []))

    def test_duplicate_authorization_and_identity_headers_refuse(self):
        for duplicate in ("Authorization", "Idempotency-Key", "X-MM-Application-Turn-ID"):
            with self.subTest(header=duplicate):
                conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
                body = json.dumps(self.payload).encode()
                conn.putrequest("POST", "/v1/chat/completions")
                headers = {"Authorization": "Bearer " + fixtures.SERVICE_TOKEN, "Idempotency-Key": "step-1", "X-MM-Application-Turn-ID": "turn-1", "Content-Length": str(len(body)), "Connection": "close"}
                for key, value in headers.items():
                    conn.putheader(key, value)
                    if key == duplicate:
                        conn.putheader(key, value)
                conn.endheaders(body)
                response = conn.getresponse()
                self.assertIn(response.status, (400, 401))
                response.read()
                conn.close()
        self.assertEqual(self.rows("leases"), [])
        self.assertEqual(self.posts, [])

    def test_stable_service_cannot_mutate_controller_or_worker_routes(self):
        self.router.auth_failed["account-a"] = True
        for path, body in (("/reenable", {"account": "account-a"}), ("/worker-capabilities", {}),
                           ("/v1/responses", self.payload), ("/v1/messages", self.payload)):
            self.assertEqual(self.request(path=path, payload=body)[0], 400)
        self.assertTrue(self.router.auth_failed["account-a"])
        self.assertEqual(self.rows("leases"), [])
        self.assertEqual(self.posts, [])

    def test_disabled_default_does_not_enroll_an_application_service(self):
        server = self.go.make_server(self.router, lease_gateway=self.gateway)
        self._serve(server)
        old = self.server
        self.server = server
        try:
            self.assertEqual(self.request()[0], 401)
        finally:
            self.server = old
        self.assertEqual(self.rows("leases"), [])

    def test_ambiguous_or_malformed_service_binding_refuses_at_construction(self):
        with self.assertRaises(ValueError):
            self.go.make_server(self.router, lease_gateway=self.gateway, application_services=(self.service, self.service))
        with self.assertRaises(ValueError):
            self.go.make_server(self.router, lease_gateway=self.gateway, application_services=(replace(self.service, credential=fixtures.CONTROLLER_TOKEN),))
        with self.assertRaises(ValueError):
            replace(self.service, credential="v1." + "a" * 40)
        self.assertNotIn(fixtures.SERVICE_TOKEN, repr(self.service))
        self.assertEqual(self.rows("leases"), [])

    def test_authenticated_reference_is_compared_in_original_atomic_grant_owner(self):
        self.grant["credential_ref"] = "DIFFERENT_AUTHENTICATED_SERVICE"
        self.save()
        with patch.object(self.broker, "_try_acquire_in_transaction", side_effect=AssertionError("credential mismatch admitted")):
            status, _, _ = self.request()
        self.assertEqual(status, 503)
        self.assertEqual(self.rows("leases"), [])
        self.assertEqual((self.gets, self.posts), ([], []))

    def test_live_grant_change_between_begin_and_prepare_cannot_send(self):
        reserve = self.router.reserve_application_account
        def revoke_after_admission(*args):
            result = reserve(*args)
            self.grant["credential_ref"] = "REVOKED_AFTER_BIND"
            self.save()
            return result
        with patch.object(self.router, "reserve_application_account", side_effect=revoke_after_admission):
            self.assertEqual(self.request()[0], 503)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(self.rows("application_requests"), [])
        self.assertEqual(self.posts, [])

    def test_original_close_is_scoped_to_authenticated_workload_and_exact_body(self):
        self.assertEqual(self.request()[0], 200)
        with self.assertRaises(Exception):
            self.gateway.close_application_turn(principal_id="macro", turn_id="turn-1",
                expected_host="vps", expected_workload="another-workload")
        self.assertIn(self.rows("leases")[0]["state"], ("held", "rented"))
        self.assertEqual(self.request(path="/application-turns/close", payload={"turn_id": "turn-1", "release": True})[0], 400)
        self.assertEqual(len(self.posts), 1)

    def test_worker_health_still_accepts_only_the_original_worker_codec(self):
        lease = self.broker.acquire("worker-root", "go", host="vps", pid=os.getpid(), model="fixture-model", wait=0)
        token = self.gateway.issue({"lease_id": lease.lease_id, "root": "worker-root", "model": "fixture-model", "run_id": "worker-run", "host": "vps", "ttl": 30})["token"]
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        conn.request("GET", "/worker-health", headers={"Authorization": "Bearer " + token,
            "X-MM-Run-Id": "worker-run", "X-MM-Host": "vps", "X-MM-Worker-Model": "fixture-model"})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read())["worker_capabilities"], "lease-v1")
        conn.close()
        self.assertEqual(self.rows("application_turns"), [])
        self.assertEqual((self.gets, self.posts), ([], []))

    def test_trusted_main_hook_keeps_one_original_lifecycle_and_worker_flag(self):
        events = []
        broker_dir = self.directory / "ext/broker"
        broker_dir.mkdir()
        (broker_dir / "leases.sqlite").symlink_to(self.directory / "leases.sqlite")
        original_make_server = self.go.make_server
        actual = []
        def make_server(router, port, **kwargs):
            self.assertIs(router, self.router)
            self.assertFalse(kwargs["worker_capabilities_enabled"])
            self.assertEqual(kwargs["application_services"], (self.service,))
            self.assertIs(kwargs["lease_gateway"]._application_owner(), self.broker)
            server = original_make_server(router, 0, **kwargs)
            server.serve_forever = lambda: events.append("serve")
            actual.append(server)
            return server
        with patch.object(self.go, "Router", return_value=self.router), patch.object(self.go, "make_server", side_effect=make_server), patch.object(self.go, "acquire_singleton_lock", side_effect=lambda p: events.append(("lock", p))), patch.object(self.go, "write_pid", side_effect=lambda p: events.append(("pid", p))), patch.dict(os.environ, {"GO_WORKER_CAPABILITIES": "0", "GO_STATE_DIR": self.router.state_dir, "GO_SHIM_PORT": "0"}), patch.object(sys, "argv", [self.go.__file__]):
            try:
                self.assertEqual(self.go.main(application_broker=self.broker, application_services=(self.service,)), 0)
            finally:
                for server in actual:
                    server.server_close()
        self.assertEqual([e if isinstance(e, str) else e[0] for e in events], ["lock", "pid", "serve"])
        self.assertEqual(events[0][1], os.path.join(self.router.state_dir, "shim.lock"))
        self.assertEqual(self.rows("application_turns"), [])
        self.assertEqual((self.gets, self.posts), ([], []))

    def test_application_gateway_does_not_implicitly_enable_worker_routes(self):
        server = self.go.make_server(self.router, lease_gateway=self.gateway,
            application_services=(self.service,), worker_capabilities_enabled=False)
        self._serve(server)
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        conn.request("GET", "/health", headers={"Connection": "close"})
        response = conn.getresponse()
        self.assertIsNone(json.loads(response.read())["worker_capabilities"])
        conn.close()
        old = self.server
        self.server = server
        try:
            self.assertEqual(self.request()[0], 200)
            controller = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            controller.request("POST", "/worker-capabilities", "{}", headers={
                "Authorization": "Bearer " + fixtures.CONTROLLER_TOKEN,
                "Content-Type": "application/json", "Connection": "close"})
            response = controller.getresponse()
            self.assertEqual(response.status, 404)
            self.assertEqual(json.loads(response.read())["error"]["type"], "worker_capabilities_disabled")
            controller.close()
        finally:
            self.server = old

    def test_real_generation_keeps_original_state_and_rejects_binding_drift(self):
        # Use the real unchanged generation publisher, not hand-crafted release
        # metadata. This does not select or install any fixture generation.
        sys.path.insert(0, str(fixtures.ROOT / "rollout"))
        import test_native_generation as generation_fixtures
        fixture = generation_fixtures.NativeGenerationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tearDown)
        source = fixture.make_source("GO")
        for name in ("go_shim.py", "native_runtime_bindings.py"):
            (source / "ext" / name).write_bytes((fixtures.ROOT / "candidate" / name).read_bytes())
        release = fixture.publish("GO")
        here = release / "ext"
        with patch.dict(sys.modules):
            sys.modules.pop("native_runtime_bindings", None)
            name = "fixture_generated_go"
            spec = importlib.util.spec_from_file_location(name, here / "go_shim.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            self.assertEqual(module.__file__, str(here / "go_shim.py"))
            self.assertEqual(module._EXT_DIR, str(here))
            self.assertEqual(module.HERE, str(fixture.ext / "go_shim"))
            self.assertEqual(module._HELPER_OWNER, str(fixture.ext / "glm_shim"))
            self.assertEqual(module._BROKER_DB, str(fixture.ext / "broker/leases.sqlite"))
            self.assertEqual(module.DEFAULTS["GO_WEIGHTS_PATH"], str(fixture.ext / "state/go_weights.jsonl"))
            self.assertEqual(module.DEFAULTS["GO_WIRE_COMPAT_PATH"], str(fixture.ext / "state/go_wire_compat.json"))
            self.assertEqual(module.DEFAULTS["GO_MODEL_TIERS_PATH"], str(fixture.ext / "go_shim/model_tiers.json"))
            here.chmod(0o755)
            (here / "go_shim").unlink()
            (here / "go_shim").symlink_to(fixture.ext / "different-state")
            here.chmod(0o555)
            with self.assertRaisesRegex(ValueError, "visible alias changed"):
                module._go_source_paths(here / "go_shim.py")
            sys.modules["native_runtime_bindings"] = self.go
            with self.assertRaisesRegex(ValueError, "module conflict"):
                module._go_source_paths(here / "go_shim.py")
        self.assertEqual(self.rows("application_turns"), [])
        self.assertEqual((self.gets, self.posts), ([], []))


if __name__ == "__main__":
    unittest.main()
