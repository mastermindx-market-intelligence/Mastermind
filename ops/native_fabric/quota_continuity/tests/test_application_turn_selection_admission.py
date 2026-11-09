"""Actual ingress -> pure picker -> conditional A -> original Go transport.

Only the fixture upstream is synthetic. B, picker, gateway, A/SQLite, payload
and terminal ownership are real. No provider or production credential is used.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import unittest
from unittest.mock import patch

from test_go_application_handler_composition import NativeApplicationHTTPFixture, SERVICE_TOKEN
from test_application_turn_pick_go_composition import _policy_document
from go_lease_gateway import ApplicationSelectionProfile, ApplicationSelectionRefused
import lease_broker
import pick
import pool_ledger


class SelectedIngressFixture(NativeApplicationHTTPFixture):
    def setUp(self):
        super().setUp()
        self.policy_path = self.directory / "pools.yaml"
        self.policy_document = _policy_document()
        self.policy_document["pools"]["go"]["capabilities"] = {"tools": True, "vision": False}
        self.policy_path.write_text(json.dumps(self.policy_document))
        self.ledger_path = self.directory / "ledger.jsonl"
        pool_ledger.create_ledger_file(self.ledger_path)
        for module, name, value in ((pick, "POOLS_YAML", str(self.policy_path)),
                                    (pool_ledger, "LEDGER_PATH", str(self.ledger_path))):
            guard = patch.object(module, name, value)
            guard.start()
            self.addCleanup(guard.stop)
        self.purpose_document = {"purpose_id": "fixture-text-operation",
            "source_ref": "fixture:qualified-text-purpose",
            "task": {"task_class": "mechanical", "route_key": "fixture-text-operation",
                     "task_complexity": "C1_ROUTINE_BOUNDED", "needs": []}}
        self.profile = ApplicationSelectionProfile(source_generation="a" * 64,
            ingress_digest=hashlib.sha256(Path(self.go.__file__).read_bytes()).hexdigest(),
            account_profile=self.router.accounts_path)
        self.gateway._application_selection_profile = self.profile
        self.restart_service(self.purpose_document)

    def restart_service(self, purpose):
        self.server.shutdown()
        self.server.server_close()
        binding = self.go.ApplicationSelectionPurpose(purpose) if purpose is not None else None
        self.service = self.go.ApplicationServiceBinding("macro", "vps", "site_interactive",
            "MACRO_APPLICATION_TOKEN", SERVICE_TOKEN, selection_purpose=binding)
        self.server = self.go.make_server(self.router, lease_gateway=self.gateway, application_services=(self.service,))
        self.server.handle_error = lambda *args: None
        self._serve(self.server)

    def original_scope(self):
        return {"workload": "site_interactive", "turn_id": "turn-1", "pool": "go", "model": "fixture-model"}

    def select(self):
        return self.gateway.select_application(self.original_scope(), principal_id="macro", host="vps",
            credential_ref="MACRO_APPLICATION_TOKEN", purpose=self.purpose_document, payload=self.payload)

    def assert_no_effect(self):
        self.assertEqual(self.rows("leases"), [])
        self.assertEqual(self.rows("application_turns"), [])
        self.assertEqual(self.rows("application_requests"), [])
        self.assertEqual((self.gets, self.posts, self.usage_rows()), ([], [], []))


class SelectedIngressTests(SelectedIngressFixture):
    def test_real_first_ingress_selects_and_stores_before_one_upstream_send(self):
        with patch.object(pick, "select_application", wraps=pick.select_application) as selector:
            status, body, headers = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(selector.call_count, 1)
        self.assertEqual(headers["X-MM-Application-Disposition"], "terminal")
        turn = self.rows("application_turns")[0]
        record = json.loads(turn["selection_json"])
        self.assertEqual(turn["selection_digest"], hashlib.sha256(turn["selection_json"].encode()).hexdigest())
        self.assertEqual(record["purpose"], self.purpose_document)
        self.assertEqual(record["identity"]["model"], "fixture-model")
        self.assertEqual(record["identity"]["grant_ref"]["grant_id"], self.grant["grant_id"])
        self.assertEqual(record["identity"]["observation_source"], "broker-ledger-room")
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.pending_at_send[0][0]["state"], "pending")
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.usage_rows()), 1)
        self.assertEqual(body["model"], turn["model"])

    def test_new_step_keeps_original_selection_when_observations_unavailable(self):
        self.assertEqual(self.request()[0], 200)
        original = self.rows("application_turns")[0]
        self.ledger_path.unlink()
        self.clock[0] += 10
        with patch.object(pick, "select_application", side_effect=AssertionError("new-step reselection")), \
             patch.object(self.broker, "application_selection_facts", side_effect=AssertionError("new observation")):
            self.assertEqual(self.request(step="step-2")[0], 200)
        current = self.rows("application_turns")[0]
        self.assertEqual(current, original)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.posts), 2)
        self.assertEqual(self.posts[0][2], self.posts[1][2])

    def test_recovery_three_way_uses_one_canonical_turn(self):
        kwargs = dict(principal_id="macro", host="vps", request_id="step-1",
            path="/v1/chat/completions", payload=self.payload, include_turn=True)
        self.assertEqual(self.gateway.recover_application(self.original_scope(), **kwargs), {"kind": "turn_absent"})
        self.assertEqual(self.request()[0], 200)
        context = self.gateway.recover_application(self.original_scope(), **kwargs)
        self.assertEqual(context["kind"], "request_present")
        self.assertEqual(context["request"]["disposition"], "terminal")
        context = self.gateway.recover_application(self.original_scope(), **dict(kwargs, request_id="step-2"))
        self.assertEqual(context["kind"], "turn_present_new_step")
        self.assertEqual(context["turn"]["selection_digest"], self.rows("application_turns")[0]["selection_digest"])

    def test_terminal_replay_precedes_revoked_policy_quality_and_provider_state(self):
        self.assertEqual(self.request()[0], 200)
        before = (len(self.gets), len(self.posts), len(self.usage_rows()))
        self.accounts.unlink()
        self.policy_path.unlink()
        self.ledger_path.unlink()
        self.router.prices["models"].clear()
        with patch.object(pick, "select_application", side_effect=AssertionError("replay selected")), \
             patch.object(self.router, "reserve_application_account", side_effect=AssertionError("replay quota")):
            status, body, _ = self.request()
        self.assertEqual(status, 409)
        self.assertEqual(body["application"]["disposition"], "terminal_receipt_only")
        self.assertEqual((len(self.gets), len(self.posts), len(self.usage_rows())), before)

    def test_unknown_new_step_holds_original_without_selection_or_quota(self):
        self.reset = True
        self.assertEqual(self.request()[0], 503)
        before = (len(self.gets), len(self.posts), len(self.usage_rows()))
        self.policy_path.unlink()
        self.ledger_path.unlink()
        with patch.object(pick, "select_application", side_effect=AssertionError("unknown reselected")), \
             patch.object(self.router, "reserve_application_account", side_effect=AssertionError("unknown quota")):
            status, body, _ = self.request(step="step-2")
        self.assertEqual(status, 409)
        self.assertEqual(body["application"]["disposition"], "effect_unknown")
        self.assertEqual((len(self.gets), len(self.posts), len(self.usage_rows())), before)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(self.rows("leases")[0]["state"], "held")

    def test_grant_replacement_between_selection_and_admission_refuses_without_allocation(self):
        begin = self.gateway.begin_application
        def race(*args, **kwargs):
            self.grant["grant_id"] = "replacement-grant"
            self.grant["max_steps"] = 3
            self.save()
            return begin(*args, **kwargs)
        with patch.object(self.gateway, "begin_application", race):
            status, body, _ = self.request()
        self.assertEqual(status, 409)
        self.assertEqual(body["application"]["disposition"], "refused")
        self.assert_no_effect()

    def test_policy_change_between_selection_and_admission_refuses(self):
        begin = self.gateway.begin_application
        def race(*args, **kwargs):
            self.policy_document["routing"]["acceptance_floor"] = "0.8 over last 20"
            self.policy_path.write_text(json.dumps(self.policy_document))
            return begin(*args, **kwargs)
        with patch.object(self.gateway, "begin_application", race):
            self.assertEqual(self.request()[0], 409)
        self.assert_no_effect()

    def test_source_profile_change_between_selection_and_admission_refuses(self):
        begin = self.gateway.begin_application
        def race(*args, **kwargs):
            self.gateway._application_selection_profile = ApplicationSelectionProfile(
                source_generation="b" * 64, ingress_digest=self.profile.document["ingress_digest"],
                account_profile=self.router.accounts_path)
            return begin(*args, **kwargs)
        with patch.object(self.gateway, "begin_application", race):
            self.assertEqual(self.request()[0], 409)
        self.assert_no_effect()

    def test_stale_first_selection_refuses_but_new_steps_do_not_expire_observation(self):
        begin = self.gateway.begin_application
        def race(*args, **kwargs):
            self.clock[0] += 6
            return begin(*args, **kwargs)
        with patch.object(self.gateway, "begin_application", race):
            self.assertEqual(self.request()[0], 409)
        self.assert_no_effect()

    def test_cold_quota_refresh_happens_only_after_real_admission(self):
        self.assertTrue(all(value is None for value in self.router.snapshots.values()))
        reserve = self.router.reserve_application_account
        def checked(account, model):
            self.assertEqual(self.gets, [])
            self.assertEqual(len(self.rows("application_turns")), 1)
            self.assertIsNotNone(self.rows("application_turns")[0]["selection_json"])
            return reserve(account, model)
        with patch.object(self.router, "reserve_application_account", checked):
            self.assertEqual(self.request()[0], 200)
        self.assertTrue(self.gets)

    def test_selector_inputs_use_readonly_cooldown_connection_without_new_broker(self):
        with patch.object(self.broker, "_conn", side_effect=AssertionError("write connection")), \
             patch.object(self.broker, "_lock", side_effect=AssertionError("admission lock")), \
             patch.object(self.broker, "_gc_locked", side_effect=AssertionError("GC")):
            selected = self.select()
        self.assertEqual(selected["identity"]["model"], "fixture-model")
        self.assert_no_effect()

    def test_recovery_snapshot_does_not_open_an_admission_lock_or_writer(self):
        with patch.object(self.broker, "_conn", side_effect=AssertionError("recovery writer")), \
             patch.object(self.broker, "_lock", side_effect=AssertionError("recovery admission lock")):
            context = self.gateway.recover_application(self.original_scope(), principal_id="macro", host="vps",
                request_id="step-1", path="/v1/chat/completions", payload=self.payload, include_turn=True)
        self.assertEqual(context, {"kind": "turn_absent"})
        self.assert_no_effect()

    def test_purpose_and_profile_getters_own_deep_values(self):
        purpose = self.go.ApplicationSelectionPurpose(self.purpose_document)
        original, digest = purpose.document, purpose.digest
        self.purpose_document["task"]["needs"].append("vision")
        view = purpose.document
        view["task"]["needs"].append("tools")
        self.assertEqual(purpose.document, original)
        self.assertEqual(purpose.digest, digest)
        profile = self.profile.document
        profile["capabilities"]["vision"] = True
        self.assertFalse(self.profile.document["capabilities"]["vision"])
        with self.assertRaises(AttributeError):
            purpose.digest = "0" * 64

    def test_quality_empty_is_valid_but_missing_malformed_incomplete_and_duplicate_refuse(self):
        for raw in (None, "{bad}\n", '{"pool":"go"}', '{"pool":"go","pool":"go"}\n', '{"score":NaN}\n'):
            with self.subTest(raw=raw):
                if raw is None:
                    self.ledger_path.unlink(missing_ok=True)
                else:
                    pool_ledger.create_ledger_file(self.ledger_path)
                    self.ledger_path.write_text(raw)
                self.assertEqual(self.request()[0], 409)
                self.assert_no_effect()
        pool_ledger.create_ledger_file(self.ledger_path)
        self.assertEqual(self.request()[0], 200)

    def test_purpose_removal_cannot_convert_selected_turn_to_legacy(self):
        self.assertEqual(self.request()[0], 200)
        self.restart_service(None)
        before = len(self.posts)
        self.assertEqual(self.request()[1]["application"]["disposition"], "terminal_receipt_only")
        status, body, _ = self.request(step="step-2")
        self.assertEqual(status, 409)
        self.assertEqual(body["application"]["disposition"], "refused")
        self.assertEqual(len(self.posts), before)

    def test_purpose_change_refuses_new_step_but_preserves_original_recovery(self):
        self.assertEqual(self.request()[0], 200)
        changed = copy.deepcopy(self.purpose_document)
        changed["purpose_id"] = "different-purpose"
        self.restart_service(changed)
        self.assertEqual(self.request()[1]["application"]["disposition"], "terminal_receipt_only")
        self.assertEqual(self.request(step="step-2")[0], 409)
        self.assertEqual(len(self.posts), 1)

    def test_selected_identity_and_model_are_immutable_inside_original_turn(self):
        self.assertEqual(self.request()[0], 200)
        before = self.rows("application_turns")
        with sqlite3.connect(self.directory / "leases.sqlite") as conn:
            conn.execute("UPDATE application_turns SET selection_json=NULL,selection_digest=NULL")
            conn.execute("UPDATE application_turns SET model='other-model'")
            conn.execute("DELETE FROM application_turns")
        self.assertEqual(self.rows("application_turns"), before)
        self.assertEqual(self.request(step="step-2", payload=dict(self.payload, model="other-model"))[0], 503)
        self.assertEqual(len(self.posts), 1)

    def test_concurrent_first_requests_reconcile_to_one_turn_and_one_post(self):
        barrier = threading.Barrier(2)
        recover = self.gateway.recover_application
        def synchronized(*args, **kwargs):
            result = recover(*args, **kwargs)
            if kwargs.get("include_turn") and result["kind"] == "turn_absent":
                barrier.wait(3)
            return result
        self.block = threading.Event()
        try:
            with patch.object(self.gateway, "recover_application", synchronized), ThreadPoolExecutor(max_workers=2) as threads:
                first, second = threads.submit(self.request), threads.submit(self.request)
                self.assertTrue(self.arrived.wait(3))
                self.block.set()
                results = [first.result(5), second.result(5)]
            self.assertEqual(sorted(r[0] for r in results), [200, 409])
        finally:
            self.block.set()
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.rows("application_turns")), 1)
        self.assertEqual(len(self.rows("application_requests")), 1)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(len(self.usage_rows()), 1)

    def test_selection_ack_loss_keeps_original_committed_turn_without_another_choice(self):
        begin = self.gateway.begin_application
        def lose(*args, **kwargs):
            begin(*args, **kwargs)
            raise RuntimeError("synthetic lost admission acknowledgement")
        with patch.object(self.gateway, "begin_application", lose):
            self.assertEqual(self.request()[0], 503)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(self.posts, [])
        with patch.object(pick, "select_application", side_effect=AssertionError("ack loss reselected")):
            self.assertEqual(self.request()[0], 200)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.posts), 1)

    def test_last_slot_selection_refusal_recovers_concurrent_original_pending(self):
        self.document["providers"]["go"]["accounts"] = [{"name": "account-a", "per_account_cap": 1}]
        self.grant["accounts"] = ["account-a"]
        self.save()
        absent_barrier = threading.Barrier(2)
        recover, select = self.gateway.recover_application, self.gateway.select_application
        lock, observed = threading.Lock(), [0]
        def recovered(*args, **kwargs):
            result = recover(*args, **kwargs)
            if kwargs.get("include_turn") and result["kind"] == "turn_absent":
                absent_barrier.wait(3)
            return result
        def delayed(*args, **kwargs):
            with lock:
                observed[0] += 1
                second = observed[0] == 2
            if second:
                self.assertTrue(self.arrived.wait(3))
            return select(*args, **kwargs)
        self.block = threading.Event()
        try:
            with patch.object(self.gateway, "recover_application", recovered), \
                 patch.object(self.gateway, "select_application", delayed), ThreadPoolExecutor(max_workers=2) as threads:
                requests = {threads.submit(self.request), threads.submit(self.request)}
                self.assertTrue(self.arrived.wait(3))
                done, running = wait(requests, timeout=3, return_when=FIRST_COMPLETED)
                try:
                    self.assertEqual(len(done), 1)
                    reply = next(iter(done)).result()
                    self.assertEqual(reply[0], 409)
                    self.assertEqual(reply[1]["application"]["disposition"], "pending")
                finally:
                    self.block.set()
                self.assertEqual(next(iter(running)).result(5)[0], 200)
        finally:
            self.block.set()
        self.assertEqual(observed[0], 2)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(len(self.usage_rows()), 1)

    def test_failed_selection_recovers_admitted_turn_before_any_request_intent(self):
        select = self.gateway.select_application
        def concurrent_admission(*args, **kwargs):
            selected = select(*args, **kwargs)
            self.gateway.begin_application(self.original_scope(), principal_id="macro", host="vps",
                expected_credential_ref="MACRO_APPLICATION_TOKEN", expected_selection=selected,
                selection_purpose=self.purpose_document, selection_payload=self.payload)
            raise ApplicationSelectionRefused("synthetic concurrent turn became visible")
        with patch.object(self.gateway, "select_application", concurrent_admission) as selector:
            self.assertEqual(self.request()[0], 200)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.posts), 1)

    def test_new_step_may_narrow_but_not_add_committed_capability_needs(self):
        tools = [{"type": "function", "function": {"name": "inspect", "parameters": {"type": "object"}}}]
        self.assertEqual(self.request(turn="with-tools", payload=dict(self.payload, tools=tools))[0], 200)
        with patch.object(pick, "select_application", side_effect=AssertionError("narrow step selected")):
            self.assertEqual(self.request(turn="with-tools", step="step-2")[0], 200)
        self.assertEqual(self.request(turn="plain")[0], 200)
        before = len(self.posts)
        self.assertEqual(self.request(turn="plain", step="step-2", payload=dict(self.payload, tools=tools))[0], 409)
        self.assertEqual(len(self.posts), before)

    def test_tools_are_committed_and_carried_through_real_chat_transport(self):
        tools = [{"type": "function", "function": {"name": "inspect", "description": "fixture",
            "parameters": {"type": "object", "properties": {}}}}]
        first = dict(self.payload, tools=tools)
        self.assertEqual(self.request(payload=first)[0], 200)
        record = json.loads(self.rows("application_turns")[0]["selection_json"])
        self.assertEqual(record["identity"]["task"]["needs"], ["tools"])
        second = dict(first, messages=[*first["messages"],
            {"role": "assistant", "content": None, "tool_calls": [{"id": "call-1", "type": "function",
                "function": {"name": "inspect", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "call-1", "content": "fixture result"}])
        with patch.object(pick, "select_application", side_effect=AssertionError("tool step selected")):
            self.assertEqual(self.request(step="step-2", payload=second)[0], 200)
        self.assertEqual(json.loads(self.posts[1][1]), second)
        self.assertEqual(len(self.rows("leases")), 1)

    def test_media_cannot_use_unqualified_text_profile(self):
        payload = dict(self.payload, messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "https://fixture.invalid/image"}}]}])
        self.assertEqual(self.request(payload=payload)[0], 409)
        self.assert_no_effect()


if __name__ == "__main__":
    unittest.main()
