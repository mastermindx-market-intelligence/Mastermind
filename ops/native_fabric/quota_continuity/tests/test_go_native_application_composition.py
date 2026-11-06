"""Real B HTTP -> A broker/SQLite/signers; synthetic compiler/carrier evidence.

No CLI, provider, installed account or runtime service is invoked. The existing
Go loopback fixture supplies its explicitly synthetic GLM support functions.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
from dataclasses import replace
import hashlib
import http.client
import json
import threading
import unittest
from unittest.mock import patch

from test_application_turn_admission import NativeApplicationFixture
from test_go_application_handler_composition import NativeApplicationHTTPFixture


class NativeFixedHTTPFixture(NativeApplicationHTTPFixture, NativeApplicationFixture):
    def setUp(self):
        # MRO retains the actual A native fixture and the existing real B/Router
        # setup. The initial Go listener receives no request in these tests.
        super().setUp()
        self.payload = {"model": "fixture-native", "messages": [
            {"role": "system", "content": "Fixture system."},
            {"role": "user", "content": "Fixture question."}], "max_tokens": 128}
        self.compilations, self.dispatches = [], []
        self.preflight_transform = self.on_execute = self.observation_transform = None
        self.native_text = "Fixture native answer. 中"
        self.service = self.go.ApplicationServiceBinding("macro", "vps", "site_interactive",
            "MACRO_APPLICATION_TOKEN", "fixture-application-service-credential-0123456789", pool="codex-native")
        self.native_binding = self.make_binding()
        self.restart_native(bindings=(self.native_binding,))

    def make_binding(self, *, accounts=None, recipe=None):
        return self.go.ApplicationNativeBinding(recipe=self.recipe if recipe is None else recipe,
            accounts=frozenset({"account-a", "account-b"}) if accounts is None else accounts,
            preflight=self.compile_native, execute=self.execute_native)

    def compile_native(self, *, recipe, account, payload):
        self.compilations.append((copy.deepcopy(recipe), account, copy.deepcopy(payload)))
        commitment = self.native_commitment(payload)
        messages = payload["messages"]
        raw = json.dumps({"system_text": messages[0]["content"] if len(messages) == 2 else None,
            "user_text": messages[-1]["content"]}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        result = self.go.ApplicationNativePreflight(account, raw, commitment)
        return self.preflight_transform(result) if self.preflight_transform else result

    def execute_native(self, dispatch):
        self.dispatches.append(dispatch)
        self.assertEqual(self.rows("application_requests")[-1]["state"], "pending")
        self.assertEqual(dispatch.input_bytes, dispatch.preflight.input_bytes)
        self.assertEqual(dispatch.invocation["account"], dispatch.preflight.account)
        if self.on_execute:
            self.on_execute(dispatch)
        receipt = self.native_receipt({"native_invocation": dispatch.invocation})
        evidence = {key: receipt[key] for key in ("response_digest", "served_model", "completed_at",
            "process", "provider_terminal", "usage")}
        evidence["usage"] = {"input_tokens": 11, "output_tokens": 7, "scope": "operation", "complete": True}
        document = {"invocation_digest": dispatch.invocation["invocation_digest"], "text": self.native_text, **evidence}
        if self.observation_transform:
            self.observation_transform(document)
        return self.go.ApplicationNativeObservation(**document)

    def restart_native(self, *, bindings=(), gateway=None, service=None):
        self.server = self.go.make_server(self.router, lease_gateway=gateway or self.gateway,
            application_services=(service or self.service,), application_native_bindings=bindings)
        self.server.handle_error = lambda *args: None
        self._serve(self.server)

    def terminal(self):
        return json.loads(self.rows("application_requests")[0]["terminal_receipt"])

    def assert_no_router_effects(self):
        self.assertEqual((self.gets, self.posts, self.usage_rows()), ([], [], []))
        self.assertTrue(all(value == 0 for value in self.router.in_flight.values()))

    def assert_held_once(self):
        status, body, _ = self.request()
        self.assertEqual((status, body["application"]["disposition"]), (503, "effect_unknown"))
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(self.rows("application_requests")[0]["state"], "unknown")
        self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})
        before = len(self.compilations)
        self.assertEqual(self.request()[1]["application"]["disposition"], "effect_unknown")
        self.assertEqual((len(self.dispatches), len(self.compilations)), (1, before))
        self.assert_no_router_effects()


class NativeApplicationCompositionTests(NativeFixedHTTPFixture):
    def test_native_plaintext_completes_through_real_original_owners_and_explicit_close(self):
        with patch.object(self.router, "reserve_application_account", side_effect=AssertionError("Router reserve")), \
             patch.object(self.router, "application_transport", side_effect=AssertionError("HTTP transport")), \
             patch.object(self.router, "_usage_row", side_effect=AssertionError("Router accounting")):
            status, body, headers = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(body["choices"][0]["message"]["content"], self.native_text)
        self.assertEqual(body["model"], "fixture-native")
        self.assertEqual(body["usage"], {"prompt_tokens": 11, "completion_tokens": 7})
        self.assertEqual(headers["X-MM-Application-Disposition"], "terminal")
        receipt, dispatch = self.terminal(), self.dispatches[0]
        self.assertEqual(receipt["invocation_digest"], dispatch.invocation["invocation_digest"])
        self.assertEqual(receipt["output_bytes"], len(self.native_text.encode()))
        self.assertEqual(receipt["delivery_digest"], hashlib.sha256(json.dumps(body,
            sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest())
        self.assertNotEqual(receipt["response_digest"], receipt["delivery_digest"])
        self.assertEqual(receipt["process"]["host"], self.recipe["physical_host"])
        self.assertEqual(receipt["account"], self.compilations[0][1])
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.dispatches), 1)
        public = json.dumps(body)
        for secret in (receipt["account"], receipt["lease_id"], dispatch.capability,
                dispatch.preflight.commitment["command_sha256"], self.recipe["physical_host"]):
            self.assertNotIn(secret, public)
        self.assert_no_router_effects()
        self.assertEqual(self.request(path="/application-turns/close", payload={"turn_id": "turn-1"})[0], 200)
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_preferred_tokens_requires_its_own_exact_recipe_and_grant(self):
        self.recipe["output_contract"]["mode"] = "preferred_tokens"
        self.grant["output_limit_mode"] = "preferred_tokens"
        self.refresh_native()
        self.payload["preferred_tokens"] = self.payload.pop("max_tokens")
        self.native_binding = self.make_binding()
        self.restart_native(bindings=(self.native_binding,))
        self.assertEqual(self.request(headers={"X-MM-Application-Recipe-Digest": self.recipe_digest})[0], 200)
        self.assertEqual(self.dispatches[0].invocation["output_limit"], {"mode": "preferred_tokens", "tokens": 128})
        self.assert_no_router_effects()

    def test_terminal_recovery_survives_expired_grant_removed_executor_and_missing_accounts(self):
        self.assertEqual(self.request()[0], 200)
        before = len(self.compilations)
        self.accounts.unlink()
        self.clock[0] = 3000
        self.restart_native(gateway=self.new_gateway())
        with patch.object(self.router, "application_model_supported", side_effect=AssertionError("mutable readiness")):
            status, body, _ = self.request()
        self.assertEqual((status, body["application"]["disposition"]), (409, "terminal_receipt_only"))
        self.assertNotIn("usage", body["application"])
        self.assertEqual((len(self.dispatches), len(self.compilations)), (1, before))
        self.assertEqual(self.request(path="/application-turns/close", payload={"turn_id": "turn-1"})[0], 200)
        self.assert_no_router_effects()

    def test_intentional_second_step_retains_the_original_account_and_lease(self):
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request(step="step-2")[0], 200)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(self.dispatches[0].invocation["account"], self.dispatches[1].invocation["account"])
        self.assertEqual(self.dispatches[0].invocation["lease_id"], self.dispatches[1].invocation["lease_id"])
        self.assertEqual(len(self.rows("application_requests")), 2)
        self.assert_no_router_effects()

    def test_terminal_recovery_precedes_rotated_service_pool_and_missing_recipe(self):
        self.assertEqual(self.request()[0], 200)
        before = len(self.compilations)
        self.restart_native(gateway=self.new_gateway(), service=replace(self.service, pool="go"))
        with patch.object(self.router, "application_model_supported", side_effect=AssertionError("mutable model read")):
            status, body, _ = self.request()
        self.assertEqual((status, body["application"]["disposition"]), (409, "terminal_receipt_only"))
        self.assertEqual((len(self.compilations), len(self.dispatches)), (before, 1))
        self.assert_no_router_effects()

    def test_preferred_pending_recovery_survives_rotated_pool_without_current_recipe(self):
        self.recipe["output_contract"]["mode"] = "preferred_tokens"
        self.grant["output_limit_mode"] = "preferred_tokens"
        self.refresh_native()
        self.payload["preferred_tokens"] = self.payload.pop("max_tokens")
        admitted = self.native_begin(turn="turn-1")
        self.native_prepare(admitted, request_id="step-1")
        self.restart_native(gateway=self.new_gateway(), service=replace(self.service, pool="go"))
        status, body, _ = self.request()
        self.assertEqual((status, body["application"]["disposition"]), (409, "pending"))
        self.assertEqual((self.compilations, self.dispatches), ([], []))
        self.assert_no_router_effects()

    def test_concurrent_original_request_has_one_dispatch_and_one_canonical_usage(self):
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(lambda _: self.request(), range(6)))
        self.assertEqual(sum(status == 200 for status, _, _ in results), 1)
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.rows("application_requests")), 1)
        self.assertEqual(self.terminal()["usage"]["input_tokens"], 11)
        self.assert_no_router_effects()

    def test_conflicting_original_body_or_recipe_does_not_recompile_or_execute(self):
        self.assertEqual(self.request()[0], 200)
        before = len(self.compilations)
        changed = copy.deepcopy(self.payload)
        changed["messages"][-1]["content"] = "Different intent."
        self.assertEqual(self.request(payload=changed)[0], 503)
        self.assertEqual(self.request(headers={"X-MM-Application-Recipe-Digest": "f" * 64})[0], 503)
        self.assertEqual((len(self.dispatches), len(self.compilations)), (1, before))

    def test_begin_ack_loss_recovers_original_turn_without_second_admission(self):
        begin = self.gateway.begin_application
        def lost(*args, **kwargs):
            begin(*args, **kwargs)
            raise OSError("synthetic lost admission acknowledgement")
        with patch.object(self.gateway, "begin_application", side_effect=lost) as called:
            self.assertEqual(self.request()[0], 503)
        self.assertEqual(called.call_count, 1)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(self.rows("application_requests"), [])
        self.assertEqual((self.compilations, self.dispatches), ([], []))

    def test_prepare_ack_loss_keeps_original_pending_and_never_remints_or_hands_off(self):
        prepare = self.gateway.prepare_application
        def lost(*args, **kwargs):
            prepare(*args, **kwargs)
            raise OSError("synthetic lost prepare acknowledgement")
        with patch.object(self.gateway, "prepare_application", side_effect=lost) as called:
            self.assertEqual(self.request()[1]["application"]["disposition"], "pending")
            self.assertEqual(self.request()[1]["application"]["disposition"], "pending")
        self.assertEqual(called.call_count, 1)
        self.assertEqual(self.dispatches, [])
        self.assertEqual(self.rows("application_requests")[0]["state"], "pending")

    def test_terminal_ack_loss_recovers_exact_receipt_without_another_writer(self):
        complete = self.gateway.complete_application
        def lost(*args, **kwargs):
            complete(*args, **kwargs)
            raise OSError("synthetic lost terminal acknowledgement")
        with patch.object(self.gateway, "complete_application", side_effect=lost) as called, \
             patch.object(self.gateway, "mark_application_unknown", side_effect=AssertionError("second writer")):
            self.assertEqual(self.request()[0], 200)
        self.assertEqual(called.call_count, 1)
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(self.rows("application_requests")[0]["state"], "terminal")

    def test_terminal_ack_and_recovery_loss_do_not_poison_committed_terminal(self):
        complete, recover = self.gateway.complete_application, self.gateway.recover_application
        committed = []
        def lost(*args, **kwargs):
            complete(*args, **kwargs)
            committed.append(True)
            raise OSError("lost ACK")
        def recovery(*args, **kwargs):
            if committed:
                raise OSError("recovery unavailable")
            return recover(*args, **kwargs)
        with patch.object(self.gateway, "complete_application", side_effect=lost), \
             patch.object(self.gateway, "recover_application", side_effect=recovery), \
             patch.object(self.gateway, "mark_application_unknown") as mark:
            self.assertEqual(self.request()[0], 503)
        mark.assert_not_called()
        self.assertEqual(self.rows("application_requests")[0]["state"], "terminal")
        self.assertEqual(len(self.dispatches), 1)

    def test_delivery_disconnect_after_settlement_does_not_poison_original(self):
        with patch.object(self.server.RequestHandlerClass, "send_response", side_effect=BrokenPipeError), \
             patch.object(self.gateway, "mark_application_unknown") as mark:
            with self.assertRaises((http.client.RemoteDisconnected, ConnectionResetError)):
                self.request()
        mark.assert_not_called()
        self.assertEqual(self.rows("application_requests")[0]["state"], "terminal")
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(self.request()[1]["application"]["disposition"], "terminal_receipt_only")

    def test_exception_after_handoff_keeps_unknown_original_and_no_replay(self):
        def failed(dispatch):
            raise RuntimeError("synthetic external boundary failure")
        self.on_execute = failed
        self.assert_held_once()

    def test_base_exception_after_handoff_keeps_unknown_original(self):
        def failed(dispatch):
            raise KeyboardInterrupt("synthetic interruption")
        self.on_execute = failed
        self.assert_held_once()

    def test_failed_unknown_write_keeps_pending_instead_of_freeing_or_replaying(self):
        def failed(dispatch):
            raise OSError("synthetic external failure")
        self.on_execute = failed
        with patch.object(self.gateway, "mark_application_unknown", side_effect=OSError("writer unavailable")) as mark:
            self.assertEqual(self.request()[0], 503)
        self.assertEqual(mark.call_count, 1)
        self.assertEqual(self.rows("application_requests")[0]["state"], "pending")
        self.assertEqual(self.request()[1]["application"]["disposition"], "pending")
        self.assertEqual(len(self.dispatches), 1)

    def test_rc_zero_without_provider_terminal_evidence_is_not_settlement(self):
        self.observation_transform = lambda value: value["provider_terminal"].update(state="unknown")
        self.assert_held_once()

    def test_ambiguous_earlier_send_cannot_be_settled_or_replayed(self):
        self.observation_transform = lambda value: value["provider_terminal"].update(ambiguous_earlier_send=True)
        self.assert_held_once()

    def test_incomplete_cleanup_cannot_be_settled_or_replayed(self):
        self.observation_transform = lambda value: value["process"].update(cleanup_complete=False)
        self.assert_held_once()

    def test_truncated_capture_cannot_be_settled_or_replayed(self):
        self.observation_transform = lambda value: value["process"].update(stdout_truncated=True)
        self.assert_held_once()

    def test_missing_served_model_does_not_substitute_requested_model(self):
        self.observation_transform = lambda value: value.update(served_model=None)
        self.assert_held_once()

    def test_wrong_physical_host_is_not_settlement(self):
        self.observation_transform = lambda value: value["process"].update(host="different-host")
        self.assert_held_once()

    def test_wrong_invocation_observation_is_not_settlement(self):
        self.observation_transform = lambda value: value.update(invocation_digest="f" * 64)
        self.assert_held_once()

    def test_actual_known_provider_error_is_terminal_and_explicitly_closeable(self):
        def known_error(value):
            value["text"] = ""
            value["provider_terminal"]["state"] = "failed"
            value["process"]["returncode"] = 1
        self.observation_transform = known_error
        status, body, _ = self.request()
        self.assertEqual((status, body["application"]["disposition"]), (502, "terminal"))
        self.assertEqual(body["application"]["serving_model"], "fixture-native")
        self.assertEqual(body["application"]["usage"], {"input_tokens": 11, "output_tokens": 7})
        self.assertEqual(self.rows("application_requests")[0]["state"], "terminal")
        self.assertEqual(self.terminal()["provider_terminal"]["state"], "failed")
        recovered = self.request()[1]["application"]
        self.assertEqual(recovered["disposition"], "terminal_receipt_only")
        self.assertNotIn("usage", recovered)
        self.assertEqual(self.request(path="/application-turns/close", payload={"turn_id": "turn-1"})[0], 200)
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_close_while_carrier_is_running_holds_until_original_terminal(self):
        entered, release = threading.Event(), threading.Event()
        def wait_for_close(dispatch):
            entered.set()
            if not release.wait(3):
                raise AssertionError("fixture carrier was not released")
        self.on_execute = wait_for_close
        with ThreadPoolExecutor(max_workers=1) as executor:
            running = executor.submit(self.request)
            try:
                self.assertTrue(entered.wait(3))
                status, body, _ = self.request(path="/application-turns/close", payload={"turn_id": "turn-1"})
                self.assertNotEqual(body["application"]["disposition"], "closed")
                self.assertNotEqual(status, 200)
                self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})
            finally:
                release.set()
            self.assertEqual(running.result(timeout=5)[0], 200)
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(self.rows("application_requests")[0]["state"], "terminal")
        self.assertEqual(self.rows("leases")[0]["state"], "released")
        self.assert_no_router_effects()

    def test_partial_provider_usage_stays_null_on_wire_and_retained_as_partial_in_owner(self):
        self.observation_transform = lambda value: value["usage"].update(
            input_tokens=11, output_tokens=7, scope="provider_final", complete=False)
        status, body, _ = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(body["usage"], {"prompt_tokens": None, "completion_tokens": None})
        self.assertEqual(self.terminal()["usage"], {"input_tokens": 11, "output_tokens": 7,
            "scope": "provider_final", "complete": False})
        self.assert_no_router_effects()

    def test_unknown_usage_is_not_zero_and_does_not_block_nullable_operation_answer(self):
        self.observation_transform = lambda value: value["usage"].update(
            input_tokens=None, output_tokens=None, scope="unknown", complete=False)
        status, body, _ = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(body["usage"], {"prompt_tokens": None, "completion_tokens": None})
        self.assertIsNone(self.terminal()["usage"]["input_tokens"])

    def test_observed_output_over_hard_cap_is_held(self):
        self.observation_transform = lambda value: value["usage"].update(output_tokens=129)
        self.assert_held_once()

    def test_expired_dispatch_capability_is_refused_before_external_execution(self):
        prepare = self.gateway.prepare_application
        def expire(*args, **kwargs):
            result = prepare(*args, **kwargs)
            self.clock[0] += 301
            return result
        with patch.object(self.gateway, "prepare_application", side_effect=expire):
            self.assertEqual(self.request()[0], 503)
        self.assertEqual(self.dispatches, [])
        self.assertEqual(self.rows("application_requests")[0]["state"], "unknown")

    def test_tampered_dispatch_capability_is_refused_before_external_execution(self):
        prepare = self.gateway.prepare_application
        def tamper(*args, **kwargs):
            result = prepare(*args, **kwargs)
            result["native_dispatch_capability"] += "x"
            return result
        with patch.object(self.gateway, "prepare_application", side_effect=tamper):
            self.assertEqual(self.request()[0], 503)
        self.assertEqual(self.dispatches, [])
        self.assertEqual(self.rows("application_requests")[0]["state"], "unknown")

    def test_post_prepare_invocation_change_is_refused_before_external_execution(self):
        prepare = self.gateway.prepare_application
        def tamper(*args, **kwargs):
            result = prepare(*args, **kwargs)
            result["native_invocation"]["commitment"]["command_sha256"] = "e" * 64
            return result
        with patch.object(self.gateway, "prepare_application", side_effect=tamper):
            self.assertEqual(self.request()[0], 503)
        self.assertEqual(self.dispatches, [])
        self.assertEqual(self.rows("application_requests")[0]["state"], "unknown")


if __name__ == "__main__":
    unittest.main()
