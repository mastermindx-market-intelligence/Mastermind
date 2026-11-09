"""GLM through the actual nested HTTP handler, one Broker and bounded loopback sender."""
from concurrent.futures import ThreadPoolExecutor
import copy
from dataclasses import replace
import hashlib
import json
import sys
import threading
from unittest.mock import patch

from test_go_application_handler_composition import NativeApplicationHTTPFixture, SERVICE_TOKEN
from test_glm_application_transports import glm_adapter, projection_bytes, completed, CALL, REASONING
from go_lease_gateway import GoLeaseGateway
import lease_broker


class GlmHTTPFixture(NativeApplicationHTTPFixture):
    def setUp(self):
        super().setUp()
        adapter_patch = patch.dict(sys.modules, {"glm_application_adapter": glm_adapter})
        adapter_patch.start()
        self.addCleanup(adapter_patch.stop)
        self.credential_reads, self.logical_posts = [], []
        self.credential_failure = None
        self.response = completed()

        def credential(account):
            self.credential_reads.append((account, len(self.rows("application_requests"))))
            if self.credential_failure == "preflight" or (
                    self.credential_failure == "after_intent" and self.rows("application_requests")):
                raise ValueError("synthetic credential unavailable")
            return "fixture-glm-" + account

        def transport(request):
            self.logical_posts.append(request)
            self.assertFalse(request.allow_redirects)
            self.assertFalse(request.use_environment_proxy)
            self.assertEqual(request.url, self.driver.identity.endpoint)
            local = replace(request, url="http://127.0.0.1:" + str(self.upstream.server_port) + "/v1/chat/completions")
            observed = self.router.application_http_transport(local)
            return replace(observed, final_url=request.url)

        raw_projection = projection_bytes()
        digest = hashlib.sha256(raw_projection).hexdigest()
        self.driver = glm_adapter.GlmChatCompletionsDriver(
            transport=transport, clock=lambda: self.clock[0],
            realm_projection=raw_projection, projection_sha256=digest)
        self.http_binding = self.go.ApplicationHTTPBinding(
            self.driver, frozenset({"account-a", "account-b"}), digest, credential)
        recipes = tuple(self.http_binding.recipe(model) for model in sorted(self.driver.identity.allowed_models))
        _, self.recipe_digest = lease_broker._application_http_recipe(
            self.http_binding.recipe("glm-5.3"), pool="glm", model="glm-5.3")
        self.document["providers"]["glm"] = copy.deepcopy(self.document["providers"]["go"])
        self.document["providers"]["glm"]["enabled"] = "auto"
        self.grant.update(pool="glm", models=["glm-5.3"], recipe_digest=self.recipe_digest)
        self.save()
        self.gateway = GoLeaseGateway(
            str(self.directory / "leases.sqlite"), self.router.accounts, set(self.router.prices["models"]),
            clock=lambda: self.clock[0], signing_key=b"k" * 32,
            application_broker=self.broker, application_http_recipes=recipes,
            application_http_accounts={"glm": self.http_binding.accounts})
        self.service = self.go.ApplicationServiceBinding(
            "macro", "vps", "site_interactive", "MACRO_APPLICATION_TOKEN", SERVICE_TOKEN, pool="glm")
        self.server = self.go.make_server(
            self.router, lease_gateway=self.gateway, application_services=(self.service,),
            application_http_binding={"glm": self.http_binding}, worker_capabilities_enabled=False)
        self.server.handle_error = lambda *args: None
        self._serve(self.server)
        self.payload = {"model": "glm-5.3", "messages": [
            {"role": "system", "content": "Fixture system."},
            {"role": "user", "content": "Read the fixture."}], "max_tokens": 128, "stream": False}

    def request(self, **kwargs):
        headers = {"X-MM-Application-Recipe-Digest": self.recipe_digest, **kwargs.pop("headers", {})}
        return super().request(headers=headers, **kwargs)


class GlmApplicationCompositionTests(GlmHTTPFixture):
    def test_actual_handler_commits_one_glm_lease_before_exact_chat_send(self):
        with patch.object(self.router, "reserve_application_account", side_effect=AssertionError("Go quota used")), \
                patch.object(self.router, "_usage_row", side_effect=AssertionError("Go ledger used")):
            status, body, headers = self.request()
        self.assertEqual(status, 200, body)
        self.assertEqual(body["model"], "glm-5.3")
        self.assertEqual(body["choices"][0]["message"]["reasoning_content"], REASONING)
        self.assertEqual(body["usage"], {"prompt_tokens": 11, "completion_tokens": 7})
        self.assertEqual(headers["X-MM-Application-Disposition"], "terminal")
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.gets, [])
        self.assertEqual(self.usage_rows(), [])
        self.assertEqual(self.credential_reads, [("account-a", 0), ("account-a", 1)])
        self.assertEqual(self.posts[0][2], "Bearer fixture-glm-account-a")
        expected = self.driver.prepare_request(self.payload)
        self.assertEqual(self.posts[0][1], expected.wire_body)
        pending = self.pending_at_send[0][0]
        self.assertEqual(pending["state"], "pending")
        self.assertEqual(pending["wire_body_digest"], hashlib.sha256(self.posts[0][1]).hexdigest())
        receipt = json.loads(self.rows("application_requests")[0]["terminal_receipt"])
        self.assertEqual(receipt["terminal_kind"], "http_chat_v1")
        self.assertEqual(receipt["recipe_digest"], self.recipe_digest)
        self.assertEqual(receipt["served_model"], "glm-5.3")
        self.assertEqual(receipt["response_digest"], hashlib.sha256(json.dumps(self.response).encode()).hexdigest())
        self.assertNotEqual(receipt["response_digest"], receipt["delivery_digest"])
        self.assertEqual(len(self.rows("leases")), 1)

    def test_real_tool_return_replays_exact_reasoning_on_same_original_turn(self):
        self.response = completed(tools=True)
        self.payload["tools"] = [{"type": "function", "function": {
            "name": "read_fixture", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}}}}]
        status, first, _ = self.request()
        self.assertEqual(status, 200, first)
        message = first["choices"][0]["message"]
        self.assertEqual(first["choices"][0]["finish_reason"], "tool_calls")
        self.assertEqual(message["tool_calls"], [CALL])
        self.assertEqual(message["reasoning_content"], REASONING)
        self.payload["messages"] += [message, {"role": "tool", "tool_call_id": CALL["id"], "content": "fixture value"}]
        self.response = completed()
        status, second, _ = self.request(step="step-2")
        self.assertEqual(status, 200, second)
        sent_history = json.loads(self.posts[1][1])["messages"]
        self.assertEqual(sent_history[-2]["reasoning_content"], REASONING)
        self.assertEqual(sent_history[-2]["tool_calls"][0]["function"]["arguments"], CALL["function"]["arguments"])
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual({row["account"] for row in self.rows("leases")}, {"account-a"})
        status, closed, _ = self.request(path="/application-turns/close", payload={"turn_id": "turn-1"})
        self.assertEqual(status, 200, closed)
        self.assertEqual(self.rows("leases")[0]["state"], "released")
        self.assertEqual(len(self.rows("application_requests")), 2)
        self.assertEqual(self.usage_rows(), [])

    def test_original_recovery_survives_revocation_without_recompile_key_or_send(self):
        self.assertEqual(self.request()[0], 200)
        self.accounts.unlink()
        self.clock[0] = 3000.0
        with patch.object(self.driver, "prepare_request", side_effect=AssertionError("recompiled original")), \
                patch.object(self.driver, "preflight_credential", side_effect=AssertionError("loaded key on recovery")):
            status, body, _ = self.request()
        self.assertEqual(status, 409, body)
        self.assertEqual(body["application"]["disposition"], "terminal_receipt_only")
        self.assertEqual(len(self.posts), 1)

    def test_concurrent_duplicate_stays_one_dispatch(self):
        self.block = threading.Event()
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(self.request)
            self.assertTrue(self.arrived.wait(2))
            duplicate = executor.submit(self.request)
            second = duplicate.result(timeout=3)
            self.block.set()
            original = first.result(timeout=3)
        self.assertEqual(original[0], 200, original[1])
        self.assertIn(second[0], (409, 202), second[1])
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.rows("application_requests")), 1)

    def test_unframed_transport_retains_original_unknown_without_replay(self):
        self.partial = True
        status, body, _ = self.request()
        self.assertEqual(status, 503, body)
        self.assertEqual(body["application"]["disposition"], "effect_unknown")
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.rows("application_requests")[0]["state"], "unknown")
        self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})
        self.request()
        self.assertEqual(len(self.posts), 1)

    def test_key_and_unsupported_tool_control_refuse_before_admission(self):
        self.credential_failure = "preflight"
        status, _, _ = self.request()
        self.assertNotEqual(status, 200)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.rows("application_requests"), [])
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(self.request(path="/application-turns/close", payload={"turn_id": "turn-1"})[0], 200)
        self.assertEqual(self.rows("leases")[0]["state"], "released")
        self.credential_failure = None
        self.payload["tool_choice"] = "required"
        status, _, _ = self.request(turn="unsupported-control")
        self.assertNotEqual(status, 200)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.rows("application_requests"), [])
