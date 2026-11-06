"""Durable application dispatch and settlement, using the real native owner."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import importlib.util
import os
import sqlite3
import sys
import unittest
from unittest.mock import patch

from test_application_turn_admission import ApplicationFixture, offline_acquire, offline_release
from test_application_turn_admission import ROOT
import lease_broker
from go_lease_gateway import LeaseGatewayError


def setUpModule():
    offline_acquire()


def tearDownModule():
    offline_release()


class EffectTests(ApplicationFixture):
    def test_concurrent_duplicate_dispatch_permission_and_frozen_payload(self):
        binding = self.begin()
        payload = {"model": "fixture-model", "messages": [{"role": "user", "content": "original"}]}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.prepare(binding, payload=payload), range(2)))
        self.assertEqual(sum(row["dispatch_permitted"] for row in results), 1)
        winner = next(row for row in results if row["dispatch_permitted"])
        payload["messages"][0]["content"] = "mutated"
        self.assertIn(b"original", winner["payload_bytes"])
        self.assertNotIn(b"mutated", winner["payload_bytes"])
        self.assertEqual(len(self.rows("application_requests")), 1)
        with self.assertRaises(LeaseGatewayError):
            self.prepare(binding, payload=payload)

    def test_restart_after_intent_never_reissues_dispatch(self):
        binding = self.begin()
        first = self.prepare(binding)
        broker = self.new_broker()
        gateway = self.new_gateway(broker)
        recovered = self.begin(gateway=gateway)
        self.assertEqual(recovered["disposition"], "pending")
        self.assertNotIn("token", recovered)
        result = broker.prepare_application_request(principal_id="macro", turn_id="turn-1",
            request_id="step-1", request_digest=first["request_digest"])
        self.assertFalse(result["dispatch_permitted"])
        self.assertEqual(result["dispatch_id"], first["dispatch_id"])
        blocked = broker.prepare_application_request(principal_id="macro", turn_id="turn-1",
            request_id="new-step", request_digest="a" * 64)
        self.assertFalse(blocked["dispatch_permitted"])
        self.assertEqual(len(self.rows("leases")), 1)

    def test_unknown_survives_expiry_pid_death_gc_generic_release_and_close(self):
        binding = self.begin()
        prepared = self.prepare(binding)
        self.gateway.mark_application_unknown(prepared["dispatch_id"], reason="transport_interrupted")
        self.clock[0] = 3000
        self.broker.check_pid = True
        with patch.object(lease_broker, "_pid_alive", return_value=False):
            self.assertEqual(self.broker.gc(), 0)
        self.assertFalse(self.broker.release(binding["lease_id"], "service:macro"))
        self.assertFalse(self.broker.heartbeat(binding["lease_id"]))
        result = self.gateway.close_application_turn(principal_id="macro", turn_id="turn-1")
        self.assertEqual(result["disposition"], "effect_unknown")
        self.assertIn(self.rows("leases")[0]["state"], ("held", "rented"))
        # Original handler can settle after grant expiry and downstream loss.
        result = self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=self.receipt(prepared))
        self.assertEqual(result["disposition"], "terminal")
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_two_intentional_steps_keep_one_lease_and_third_is_refused(self):
        binding = self.begin()
        first = self.prepare(binding)
        self.gateway.complete_application(first["dispatch_id"], terminal_receipt=self.receipt(first))
        second = self.prepare(binding, "step-2")
        self.assertNotEqual(first["dispatch_id"], second["dispatch_id"])
        for key in ("account", "model", "lease_id"):
            self.assertEqual(first[key], second[key])
        self.gateway.complete_application(second["dispatch_id"], terminal_receipt=self.receipt(second))
        with self.assertRaises(LeaseGatewayError):
            self.prepare(binding, "step-3")
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.rows("application_requests")), 2)
        self.gateway.close_application_turn(principal_id="macro", turn_id="turn-1")
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_identical_completion_is_idempotent_conflict_and_late_unknown_cannot_overwrite(self):
        binding = self.begin()
        prepared = self.prepare(binding)
        receipt = self.receipt(prepared)
        original = self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=receipt)
        self.assertEqual(original, self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=receipt))
        changed = {**receipt, "response_digest": "b" * 64}
        with self.assertRaises(lease_broker.ApplicationAdmissionError):
            self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=changed)
        self.assertEqual(self.gateway.mark_application_unknown(prepared["dispatch_id"], reason="downstream_closed")["disposition"], "terminal")
        replay = self.prepare(binding)
        self.assertFalse(replay["dispatch_permitted"])
        self.assertEqual(replay["terminal_receipt"], receipt)

    def test_rejected_terminal_receipt_never_settles_pending(self):
        binding = self.begin()
        prepared = self.prepare(binding)
        for key, value in [("account", "other-account"), ("model", "other-model"),
                           ("lease_id", "other-lease"), ("request_digest", "a" * 64),
                           ("status_code", 100), ("usage", {"input_tokens": False, "output_tokens": 1})]:
            with self.subTest(key=key), self.assertRaises(lease_broker.ApplicationAdmissionError):
                self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt={**self.receipt(prepared), key: value})
        self.assertEqual(self.rows("application_requests")[0]["state"], "pending")

    def test_revocation_same_mtime_blocks_new_step_without_erasing_old_effect(self):
        binding = self.begin()
        prepared = self.prepare(binding)
        before = self.accounts.stat()
        self.grant["enabled"] = False
        self.save()
        os.utime(self.accounts, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(LeaseGatewayError):
            self.prepare(binding, "new-step")
        self.assertEqual(self.prepare(binding)["disposition"], "pending")
        self.assertEqual(self.rows("application_requests")[0]["state"], "pending")
        self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=self.receipt(prepared))
        self.gateway.close_application_turn(principal_id="macro", turn_id="turn-1")
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_original_scope_recovers_after_expiry_revocation_close_and_restart(self):
        binding = self.begin()
        prepared = self.prepare(binding)
        self.gateway.mark_application_unknown(prepared["dispatch_id"], reason="transport_interrupted")
        self.clock[0] = 3000
        self.accounts.unlink()
        self.assertEqual(self.prepare(binding)["disposition"], "effect_unknown")
        self.assertEqual(self.begin()["disposition"], "effect_unknown")
        self.gateway.close_application_turn(principal_id="macro", turn_id="turn-1")
        receipt = self.receipt(prepared)
        self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=receipt)
        restarted = self.new_gateway(self.new_broker())
        recovered = self.prepare(binding, gateway=restarted)
        self.assertFalse(recovered["dispatch_permitted"])
        self.assertEqual(recovered["terminal_receipt"], receipt)
        self.assertNotIn("payload_bytes", recovered)
        with self.assertRaises(LeaseGatewayError):
            self.prepare(binding, "new-step", gateway=restarted)
        with self.assertRaises(LeaseGatewayError):
            restarted.prepare_application(binding["token"], principal_id="attacker", host="vps",
                turn_id="turn-1", request_id="step-1", path="/v1/chat/completions",
                payload={"model": "fixture-model", "messages": [{"role": "user", "content": "fixture"}]})
        self.assertEqual(len(self.rows("application_requests")), 1)

    def test_commit_succeeded_but_ack_failed_recovers_one_original_intent(self):
        binding = self.begin()
        original_conn = self.broker._conn
        class AmbiguousCommit:
            def __init__(self, conn):
                self.conn = conn
            def __getattr__(self, name):
                return getattr(self.conn, name)
            def commit(self):
                exists = self.conn.execute("SELECT COUNT(*) FROM application_requests").fetchone()[0]
                self.conn.commit()
                if exists:
                    raise sqlite3.OperationalError("fixture: commit acknowledgement lost")
        with patch.object(self.broker, "_conn", side_effect=lambda: AmbiguousCommit(original_conn())):
            with self.assertRaises(LeaseGatewayError):
                self.prepare(binding)
        recovered = self.prepare(binding)
        self.assertFalse(recovered["dispatch_permitted"])
        self.assertEqual(recovered["disposition"], "pending")
        self.assertEqual(len(self.rows("application_requests")), 1)

    def test_authenticated_service_recovery_needs_no_old_signing_key_or_live_grant(self):
        binding = self.begin()
        prepared = self.prepare(binding)
        self.clock[0] = 3000
        self.accounts.unlink()
        scope = {"workload": "site_interactive", "turn_id": "turn-1", "pool": "go", "model": "fixture-model"}
        kwargs = dict(principal_id="macro", host="vps", request_id="step-1", path="/v1/chat/completions",
                      payload={"model": "fixture-model", "messages": [{"role": "user", "content": "fixture"}]})
        restarted = self.new_gateway(self.new_broker())
        restarted._signing_key = b"new-process-signing-key-32-bytes!!"
        recovered = restarted.recover_application(scope, **kwargs)
        self.assertEqual(recovered["disposition"], "pending")
        self.assertFalse(recovered["dispatch_permitted"])
        self.assertEqual(recovered["dispatch_id"], prepared["dispatch_id"])
        self.assertIsNone(restarted.recover_application(scope, **{**kwargs, "request_id": "never-sent"}))
        self.assertIsNone(restarted.recover_application({**scope, "turn_id": "absent"}, **kwargs))
        for changed_scope, changed_kwargs in [({**scope, "workload": "other"}, kwargs),
                (scope, {**kwargs, "host": "other-host"}),
                (scope, {**kwargs, "payload": {"model": "fixture-model", "messages": []}})]:
            with self.subTest(scope=changed_scope), self.assertRaises(LeaseGatewayError):
                restarted.recover_application(changed_scope, **changed_kwargs)
        self.assertEqual(len(self.rows("application_requests")), 1)

    def test_corrupt_persisted_state_or_terminal_receipt_never_releases_capacity(self):
        binding = self.begin()
        prepared = self.prepare(binding)
        invalid_receipt = {**self.receipt(prepared), "account": "wrong-account"}
        mutations = [("unrecognized", None), ("terminal", None), ("terminal", "{}"),
                     ("terminal", json.dumps(invalid_receipt, sort_keys=True, separators=(",", ":")))]
        self.clock[0] = 3000
        for state, receipt in mutations:
            with self.subTest(state=state, receipt=receipt):
                with sqlite3.connect(self.directory / "leases.sqlite") as conn:
                    conn.execute("PRAGMA ignore_check_constraints=ON")
                    conn.execute("UPDATE application_requests SET state=?,terminal_receipt=?", (state, receipt))
                self.assertEqual(self.broker.gc(), 0)
                self.assertEqual(self.gateway.close_application_turn(principal_id="macro", turn_id="turn-1")["disposition"], "effect_unknown")
                self.assertEqual(self.prepare(binding)["disposition"], "effect_unknown")
                self.assertIn(self.rows("leases")[0]["state"], ("held", "rented"))

    def test_close_blocks_future_steps_but_retains_unsettled_capacity(self):
        binding = self.begin()
        prepared = self.prepare(binding)
        self.gateway.close_application_turn(principal_id="macro", turn_id="turn-1")
        with self.assertRaises(LeaseGatewayError):
            self.prepare(binding, "step-2")
        self.assertEqual(self.rows("leases")[0]["state"], "held")
        self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=self.receipt(prepared))
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_application_deadline_is_never_extended_by_heartbeat_or_pool_promotion(self):
        self.grant["max_turn_seconds"] = 90
        self.save()
        binding = self.begin()
        original = self.rows("leases")[0]
        self.clock[0] += 40
        self.assertFalse(self.broker.heartbeat(binding["lease_id"]))
        self.broker.acquire("worker-root", "go", host="vps", pid=os.getpid(), model="fixture-model", wait=0)
        current = next(row for row in self.rows("leases") if row["id"] == original["id"])
        self.assertEqual(current["last_heartbeat"], original["last_heartbeat"])
        self.assertEqual(current["ttl"], original["ttl"])
        self.clock[0] = binding["expires_at"] + 1
        self.broker.gc()
        self.assertEqual(next(row for row in self.rows("leases") if row["id"] == original["id"])["state"], "expired")

    def test_unmodified_old_broker_cannot_release_unknown_application_or_repurpose_it(self):
        self.document["providers"]["go"]["accounts"] = [{"name": "account-a", "per_account_cap": 1}]
        self.grant["accounts"] = ["account-a"]
        self.save()
        binding = self.begin()
        prepared = self.prepare(binding)
        self.gateway.mark_application_unknown(prepared["dispatch_id"], reason="transport_interrupted")
        name = "application_fixture_old_broker"
        spec = importlib.util.spec_from_file_location(name, ROOT / "source/lease_broker.py")
        old_module = importlib.util.module_from_spec(spec)
        sys.modules[name] = old_module
        self.addCleanup(sys.modules.pop, name, None)
        spec.loader.exec_module(old_module)
        old = old_module.Broker(db_path=str(self.directory / "leases.sqlite"),
            lock_path=str(self.directory / "leases.lock"), accounts_path=str(self.accounts),
            now_fn=lambda: self.clock[0], check_pid=True, external_gates=False,
            this_host="vps", status_json=str(self.directory / "old-status.json"))
        original = self.rows("leases")[0]
        self.clock[0] = binding["expires_at"] + 10
        # Legacy return booleans/counts are not proof; assert the canonical rows.
        old.heartbeat(binding["lease_id"])
        old.release(binding["lease_id"], "service:macro")
        old.gc()
        old.plan("mechanical", 1, "old-worker")
        old.snapshot()
        result = old.acquire("old-worker", "go", host="vps", pid=os.getpid(), model="fixture-model", wait=0)
        self.assertFalse(result.ok)
        current = self.rows("leases")[0]
        for key in ("id", "purpose", "account", "model", "last_heartbeat", "ttl", "granted_at"):
            self.assertEqual(current[key], original[key])
        self.assertIn(current["state"], ("held", "rented"))
        with sqlite3.connect(self.directory / "leases.sqlite") as conn:
            conn.execute("UPDATE leases SET purpose='WORKER', state='released' WHERE id=?", (binding["lease_id"],))
            conn.execute("DELETE FROM leases WHERE id=?", (binding["lease_id"],))
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(self.rows("leases")[0]["purpose"], "APPLICATION")
        self.gateway.close_application_turn(principal_id="macro", turn_id="turn-1")
        self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=self.receipt(prepared))
        self.assertEqual(self.rows("leases")[0]["state"], "released")
        worker = old.acquire("old-worker", "go", host="vps", pid=os.getpid(), model="fixture-model", wait=0)
        self.assertTrue(worker.ok)
        self.clock[0] += 1
        self.assertTrue(old.heartbeat(worker.lease_id))
        self.assertTrue(old.release(worker.lease_id, "old-worker"))
        self.assertEqual(next(row for row in self.rows("leases") if row["id"] == worker.lease_id)["state"], "released")


if __name__ == "__main__":
    unittest.main()
