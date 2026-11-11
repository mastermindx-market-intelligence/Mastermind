"""Real B/A/H composition with explicit numeric-loopback upstream substitution.

The H compiler keeps its exact source-owned production identity. Only the
outbound fixture transport substitutes its URL with the local synthetic server
and reports the corresponding logical URL back. Real bounded HTTP I/O, handler,
broker, SQLite, capability, compile, normalization and settlement all execute.
No provider or real account/credential is used, and this proves no live route.
"""
from dataclasses import replace
import copy
import hashlib
import json
import sys
import unittest
from unittest.mock import patch

from test_go_application_handler_composition import NativeApplicationHTTPFixture, SERVICE_TOKEN
from test_application_turn_admission import ROOT
from go_lease_gateway import GoLeaseGateway
import lease_broker

sys.path.insert(0, str(ROOT.parents[2]))
from application_http_transports import BailianResponsesDriver


class BailianHTTPFixture(NativeApplicationHTTPFixture):
    def setUp(self):
        super().setUp()
        self.credential_reads, self.logical_posts = [], []
        self.credential_failure = None
        self.response = {"id": "fixture-response", "model": "qwen3.8-flash", "status": "completed",
            "output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": "Bailian fixture answer."}]}],
            "usage": {"input_tokens": 11, "output_tokens": 7}}
        def credential(account):
            self.credential_reads.append((account, len(self.rows("application_requests"))))
            if self.credential_failure == "preflight" or self.credential_failure == "after_intent" and self.rows("application_requests"):
                raise ValueError("synthetic credential unavailable")
            return "fixture-bailian-" + account
        def transport(request):
            self.logical_posts.append(request)
            self.assertFalse(request.allow_redirects)
            self.assertFalse(request.use_environment_proxy)
            self.assertEqual(request.url, self.driver.identity.endpoint)
            local = replace(request, url="http://127.0.0.1:" + str(self.upstream.server_port) + "/v1/responses")
            observed = self.router.application_http_transport(local)
            return replace(observed, final_url=request.url)
        self.driver = BailianResponsesDriver(transport=transport, clock=lambda: self.clock[0])
        self.http_binding = self.go.ApplicationHTTPBinding(self.driver, frozenset({"account-a", "account-b"}),
            "a" * 64, credential)
        recipes = tuple(self.http_binding.recipe(model) for model in sorted(self.driver.identity.allowed_models))
        _, self.recipe_digest = lease_broker._application_http_recipe(self.http_binding.recipe("qwen3.8-flash"),
            pool="bailian", model="qwen3.8-flash")
        self.document["providers"]["bailian"] = copy.deepcopy(self.document["providers"]["go"])
        self.grant.update(pool="bailian", models=["qwen3.8-flash"], recipe_digest=self.recipe_digest)
        self.save()
        self.gateway = GoLeaseGateway(str(self.directory / "leases.sqlite"), self.router.accounts,
            set(self.router.prices["models"]), clock=lambda: self.clock[0], signing_key=b"k" * 32,
            application_broker=self.broker, application_http_recipes=recipes,
            application_http_accounts=self.http_binding.accounts)
        self.service = self.go.ApplicationServiceBinding("macro", "vps", "site_interactive",
            "MACRO_APPLICATION_TOKEN", SERVICE_TOKEN, pool="bailian")
        self.server = self.go.make_server(self.router, lease_gateway=self.gateway, application_services=(self.service,),
            application_http_binding=self.http_binding, worker_capabilities_enabled=False)
        self.server.handle_error = lambda *args: None
        self._serve(self.server)
        self.payload = {"model": "qwen3.8-flash", "messages": [{"role": "system", "content": "Fixture system."},
            {"role": "user", "content": "Fixture question."}], "max_tokens": 128, "stream": False}

    def request(self, **kwargs):
        headers = {"X-MM-Application-Recipe-Digest": self.recipe_digest, **kwargs.pop("headers", {})}
        return super().request(headers=headers, **kwargs)


class BailianApplicationCompositionTests(BailianHTTPFixture):
    def test_real_handler_uses_same_lease_exact_wire_and_truthful_distinct_receipts(self):
        with patch.object(self.router, "reserve_application_account", side_effect=AssertionError("Go quota used")), \
                patch.object(self.router, "_usage_row", side_effect=AssertionError("Go ledger used")):
            status, body, headers = self.request()
        self.assertEqual(status, 200, body)
        self.assertEqual(body["model"], "qwen3.8-flash")
        self.assertEqual(body["choices"][0]["message"]["content"], "Bailian fixture answer.")
        self.assertEqual(body["usage"], {"prompt_tokens": 11, "completion_tokens": 7})
        self.assertEqual(headers["X-MM-Application-Disposition"], "terminal")
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.gets, [])
        self.assertEqual(self.usage_rows(), [])
        self.assertEqual(self.credential_reads, [("account-a", 0), ("account-a", 1)])
        wire = json.loads(self.posts[0][1])
        self.assertEqual(wire["max_output_tokens"], 128)
        self.assertEqual([item["role"] for item in wire["input"]], ["system", "user"])
        self.assertEqual(self.posts[0][2], "Bearer fixture-bailian-account-a")
        pending = self.pending_at_send[0][0]
        self.assertEqual(pending["state"], "pending")
        self.assertEqual(pending["wire_body_digest"], hashlib.sha256(self.posts[0][1]).hexdigest())
        terminal = json.loads(self.rows("application_requests")[0]["terminal_receipt"])
        self.assertEqual(terminal["recipe_digest"], self.recipe_digest)
        self.assertEqual(terminal["response_digest"], hashlib.sha256(json.dumps(self.response).encode()).hexdigest())
        delivery = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        self.assertEqual(terminal["delivery_digest"], hashlib.sha256(delivery).hexdigest())
        self.assertNotEqual(terminal["response_digest"], terminal["delivery_digest"])
        self.assertEqual(terminal["served_model"], "qwen3.8-flash")
        self.assertEqual(len(self.rows("leases")), 1)

    def test_two_tool_steps_use_one_turn_account_and_actual_close(self):
        self.response["output"] = [{"type": "function_call", "call_id": "call-fixture", "name": "lookup", "arguments": "{}"}]
        self.payload["tools"] = [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object", "properties": {}}}}]
        status, first, _ = self.request()
        self.assertEqual(status, 200, first)
        message = first["choices"][0]["message"]
        self.assertEqual(first["choices"][0]["finish_reason"], "tool_calls")
        self.payload["messages"] += [message, {"role": "tool", "tool_call_id": "call-fixture", "content": "fixture result"}]
        self.response["output"] = [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Done."}]}]
        status, second, _ = self.request(step="step-2")
        self.assertEqual(status, 200, second)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len({row["account"] for row in self.rows("leases")}), 1)
        status, closed, _ = self.request(path="/application-turns/close", payload={"turn_id": "turn-1"})
        self.assertEqual(status, 200, closed)
        self.assertEqual(closed["application"]["disposition"], "closed")
        self.assertEqual(self.rows("leases")[0]["state"], "released")
        self.assertEqual(self.usage_rows(), [])

    def test_original_recovery_precedes_recipe_compiler_and_credential_after_revoke(self):
        self.assertEqual(self.request()[0], 200)
        self.accounts.unlink()
        self.clock[0] = 3000.0
        with patch.object(self.driver, "prepare_request", side_effect=AssertionError("recompiled original")), \
                patch.object(self.driver, "preflight_credential", side_effect=AssertionError("loaded on recovery")):
            status, body, _ = self.request()
        self.assertEqual(status, 409)
        self.assertEqual(body["application"]["disposition"], "terminal_receipt_only")
        self.assertNotIn("usage", body["application"])
        self.assertEqual(len(self.posts), 1)

    def test_preflight_refusal_has_no_intent_or_upstream_effect(self):
        self.credential_failure = "preflight"
        status, body, _ = self.request()
        self.assertEqual(status, 503)
        self.assertEqual(body["application"]["disposition"], "refused")
        self.assertEqual(self.rows("application_requests"), [])
        self.assertEqual(self.posts, [])
        self.assertEqual(self.request(path="/application-turns/close", payload={"turn_id": "turn-1"})[0], 200)
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_post_intent_credential_loss_remains_original_unknown_without_replay(self):
        self.credential_failure = "after_intent"
        self.assertEqual(self.request()[1]["application"]["disposition"], "effect_unknown")
        self.assertEqual(self.request()[1]["application"]["disposition"], "effect_unknown")
        self.assertEqual(self.request(path="/application-turns/close", payload={"turn_id": "turn-1"})[0], 409)
        self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})
        self.assertEqual(self.posts, [])
        self.assertEqual(len(self.rows("application_requests")), 1)

    def test_bad_recipe_or_unsupported_control_refuses_before_admission(self):
        for kwargs in ({"headers": {"X-MM-Application-Recipe-Digest": "b" * 64}},
                       {"payload": {**self.payload, "temperature": 0.2}}):
            with self.subTest(kwargs=kwargs):
                status, body, _ = self.request(**kwargs)
                self.assertEqual(status, 400)
                self.assertEqual(body["application"]["disposition"], "refused")
        self.assertEqual(self.rows("leases"), [])
        self.assertEqual(self.credential_reads, [])
        self.assertEqual(self.posts, [])

    def test_complete_errors_and_bad_answers_settle_actual_usage_without_delivery(self):
        cases = [(429, {"error": {"message": "synthetic provider detail"}, "model": "qwen3.8-flash", "usage": {"input_tokens": 4}}),
                 (200, {**self.response, "status": "incomplete"}),
                 (200, {**self.response, "output": []}),
                 (200, {**self.response, "model": "different-model"}),
                 (200, {**self.response, "model": "\x00"}),
                 (200, b"not valid JSON")]
        for index, (status, response) in enumerate(cases):
            with self.subTest(index=index):
                self.response_status, self.response = status, response
                code, body, _ = self.request(turn="turn-" + str(index))
                self.assertEqual(code, status if status >= 300 else 502)
                self.assertEqual(body["application"]["disposition"], "terminal")
                self.assertNotIn("choices", body)
                self.assertNotIn("synthetic provider detail", json.dumps(body))
                self.assertEqual(self.request(path="/application-turns/close", payload={"turn_id": "turn-" + str(index)})[0], 200)
                terminal = json.loads(self.rows("application_requests")[-1]["terminal_receipt"])
                self.assertEqual(terminal["status_code"], status)
                self.assertIsNone(terminal["delivery_digest"])
        self.assertEqual(len(self.posts), len(cases))
        self.assertTrue(all(row["state"] == "released" for row in self.rows("leases")))
        self.assertEqual(self.usage_rows(), [])

    def test_incomplete_http_response_keeps_capacity_and_never_sends_again(self):
        self.partial = True
        self.assertEqual(self.request()[1]["application"]["disposition"], "effect_unknown")
        self.assertEqual(self.request()[1]["application"]["disposition"], "effect_unknown")
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.request(path="/application-turns/close", payload={"turn_id": "turn-1"})[0], 409)
        self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})


if __name__ == "__main__":
    unittest.main()
