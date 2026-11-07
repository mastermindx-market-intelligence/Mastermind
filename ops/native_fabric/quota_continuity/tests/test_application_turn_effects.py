"""Durable application dispatch and settlement, using the real native owner."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import importlib.util
import os
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

from test_application_turn_admission import ApplicationFixture, NativeApplicationFixture, offline_acquire, offline_release
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

    def test_unknown_on_one_model_holds_account_capacity_for_another_model(self):
        self.document["providers"]["go"]["accounts"] = [{"name": "account-a", "per_account_cap": 1}]
        self.grant["accounts"] = ["account-a"]
        self.save()
        binding = self.begin()
        prepared = self.prepare(binding)
        self.gateway.mark_application_unknown(prepared["dispatch_id"], reason="transport_interrupted")
        self.clock[0] = binding["expires_at"] + 1
        closed = self.gateway.close_application_turn(principal_id="macro", turn_id="turn-1")
        self.assertEqual(closed["disposition"], "effect_unknown")
        restarted = self.new_gateway(self.new_broker())
        other = {"workload": "site_interactive", "turn_id": "other-model-turn",
                 "pool": "go", "model": "other-model"}
        self.assertFalse(restarted.begin_application(other, principal_id="macro", host="vps")["ok"])
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.rows("application_requests")), 1)
        self.assertEqual(self.rows("application_requests")[0]["dispatch_id"], prepared["dispatch_id"])
        self.assertIn(self.rows("leases")[0]["state"], ("held", "rented"))

        terminal = self.gateway.complete_application(prepared["dispatch_id"],
            terminal_receipt=self.receipt(prepared))
        self.assertEqual(terminal["disposition"], "terminal")
        self.assertEqual(self.rows("leases")[0]["state"], "released")
        admitted = restarted.begin_application(other, principal_id="macro", host="vps")
        self.assertTrue(admitted["ok"])
        self.assertEqual((admitted["account"], admitted["model"]), ("account-a", "other-model"))
        self.assertNotEqual(admitted["lease_id"], binding["lease_id"])
        self.assertEqual(len(self.rows("application_requests")), 1)

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


class NativeEffectTests(NativeApplicationFixture):
    def test_native_unknown_survives_process_restarts_with_distinct_hash_seeds(self):
        binding = self.native_begin()
        prepared = self.native_prepare(binding)
        self.gateway.mark_application_unknown(prepared["dispatch_id"], reason="transport_interrupted")
        original = self.rows("leases")[0]
        from _offline_boundary import guarded_python_child
        code = guarded_python_child('''import json,sqlite3,sys
from lease_broker import Broker
p=sys.argv[1]
b=Broker(db_path=p+'/leases.sqlite',lock_path=p+'/leases.lock',
    accounts_path=p+'/accounts.json',now_fn=lambda:3000,check_pid=False,
    external_gates=False,this_host='vps',status_json=p+'/child-status.json')
recovered=b.recover_application_request(principal_id='macro',turn_id='native-turn',
    request_id='native-step',request_digest=sys.argv[2])
released=b.release(sys.argv[3],'service:macro')
b.gc()
print(json.dumps({'recovered':recovered,'released':released}))
''')
        for seed in ("1", "23"):
            with self.subTest(hash_seed=seed):
                child = subprocess.run([sys.executable, "-c", code, str(self.directory),
                    prepared["request_digest"], binding["lease_id"]],
                    env=dict(os.environ, PYTHONHASHSEED=seed),
                    text=True, capture_output=True, timeout=10, check=True)
                result = json.loads(child.stdout)
                self.assertFalse(result["released"])
                self.assertFalse(result["recovered"]["dispatch_permitted"])
                self.assertEqual(result["recovered"]["disposition"], "effect_unknown")
                self.assertEqual(result["recovered"]["dispatch_id"], prepared["dispatch_id"])
                self.assertEqual(self.rows("leases")[0], original)
                self.assertEqual(len(self.rows("application_requests")), 1)

    def test_unmodified_historical_worker_owner_cannot_release_unknown_native_custody(self):
        binding = self.native_begin()
        prepared = self.native_prepare(binding)
        self.gateway.mark_application_unknown(prepared["dispatch_id"], reason="transport_interrupted")
        name = "native_application_fixture_old_worker_broker"
        spec = importlib.util.spec_from_file_location(name, ROOT / "source/lease_broker.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        self.addCleanup(sys.modules.pop, name, None)
        spec.loader.exec_module(module)
        old = module.Broker(db_path=str(self.directory / "leases.sqlite"),
            lock_path=str(self.directory / "leases.lock"), accounts_path=str(self.accounts),
            now_fn=lambda: self.clock[0], check_pid=True, external_gates=False,
            this_host="vps", status_json=str(self.directory / "old-status.json"))
        original = self.rows("leases")[0]
        self.clock[0] = binding["expires_at"] + 10
        old.heartbeat(binding["lease_id"])
        old.release(binding["lease_id"], "service:macro")
        old.gc()
        current = self.rows("leases")[0]
        self.assertEqual(current, original)
        self.gateway.close_application_turn(principal_id="macro", turn_id="native-turn")
        self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=self.native_receipt(prepared))
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_ignored_terminal_update_does_not_report_a_committed_completion(self):
        prepared = self.native_prepare(self.native_begin())
        with sqlite3.connect(self.directory / "leases.sqlite") as conn:
            conn.execute("CREATE TRIGGER fixture_terminal_hold BEFORE UPDATE OF state ON application_requests BEGIN SELECT RAISE(IGNORE); END")
        with self.assertRaisesRegex(lease_broker.ApplicationAdmissionError, "terminal_not_committed"):
            self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=self.native_receipt(prepared))
        self.assertEqual(self.rows("application_requests")[0]["state"], "pending")
        self.assertEqual(self.rows("leases")[0]["state"], "held")

    def test_real_native_settlement_and_close_release_actual_capacity(self):
        prepared = self.native_prepare(self.native_begin())
        closing = self.gateway.close_application_turn(principal_id="macro", turn_id="native-turn")
        self.assertEqual(closing["disposition"], "pending")
        self.assertEqual(self.rows("leases")[0]["state"], "held")
        receipt = self.native_receipt(prepared)
        terminal = self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=receipt)
        self.assertEqual(terminal["terminal_receipt"]["usage"],
            {"input_tokens": None, "output_tokens": None, "scope": "unknown", "complete": False})
        self.assertNotIn("status_code", terminal["terminal_receipt"])
        self.assertEqual(self.rows("leases")[0]["state"], "released")
        self.assertEqual(self.rows("application_turns")[0]["state"], "closed")
        with self.assertRaises(LeaseGatewayError):
            self.authorize_native(prepared)

    def test_one_concurrent_native_prepare_commits_one_immutable_permit(self):
        binding = self.native_begin()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.native_prepare(binding), range(4)))
        self.assertEqual(sum(row["dispatch_permitted"] for row in results), 1)
        self.assertEqual(len({row["dispatch_id"] for row in results}), 1)
        self.assertEqual(sum("native_dispatch_capability" in row for row in results), 1)
        self.assertEqual(len(self.rows("application_requests")), 1)
        for key in ("command_sha256", "input_sha256", "logical_payload_digest", "source_generation", "physical_host"):
            changed = self.native_commitment()
            changed[key] = "other-host" if key == "physical_host" else "f" * 64
            with self.subTest(key=key), self.assertRaises(LeaseGatewayError):
                self.native_prepare(binding, commitment=changed)
        self.assertEqual(len(self.rows("leases")), 1)

    def test_native_lost_commit_ack_recovers_without_remint_or_launch_material(self):
        binding = self.native_begin()
        original = self.broker._conn
        class LostAcknowledgement:
            def __init__(self, conn): self.conn = conn
            def __getattr__(self, name): return getattr(self.conn, name)
            def commit(self):
                written = self.conn.execute("SELECT count(*) FROM application_requests").fetchone()[0]
                self.conn.commit()
                if written: raise sqlite3.OperationalError("fixture committed before lost acknowledgement")
        with patch.object(self.broker, "_conn", side_effect=lambda: LostAcknowledgement(original())):
            with self.assertRaises(LeaseGatewayError):
                self.native_prepare(binding)
        recovered = self.native_prepare(binding)
        self.assertEqual(recovered["disposition"], "pending")
        self.assertFalse(recovered["dispatch_permitted"])
        self.assertNotIn("native_dispatch_capability", recovered)
        self.assertNotIn("native_input_bytes", recovered)
        self.assertEqual(len(self.rows("application_requests")), 1)

    def test_native_recovery_precedes_rotation_revocation_and_expiry(self):
        binding = self.native_begin()
        prepared = self.native_prepare(binding)
        self.gateway.mark_application_unknown(prepared["dispatch_id"], reason="transport_lost")
        self.clock[0] = 3000
        self.accounts.unlink()
        restarted = self.new_gateway(self.new_broker())  # no native projection at all
        request = {"workload": "site_interactive", "turn_id": "native-turn", "pool": "go", "model": "fixture-native"}
        recovered = restarted.recover_application(request, principal_id="macro", host="vps", request_id="native-step",
            path="/v1/chat/completions", payload=self.payload, expected_recipe_digest=self.recipe_digest, include_turn=True)
        self.assertEqual(recovered["kind"], "request_present")
        self.assertEqual(recovered["turn"]["pool"], "codex-native")
        self.assertEqual(recovered["request"]["disposition"], "effect_unknown")
        self.assertFalse(recovered["request"]["dispatch_permitted"])
        self.assertEqual(self.native_prepare(binding)["dispatch_id"], prepared["dispatch_id"])
        with self.assertRaises(LeaseGatewayError):
            self.native_prepare(binding, "another-step")
        with self.assertRaises(LeaseGatewayError):
            self.authorize_native(prepared)
        restarted.close_application_turn(principal_id="macro", turn_id="native-turn")
        restarted.complete_application(prepared["dispatch_id"], terminal_receipt=self.native_receipt(prepared))
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_native_context_distinguishes_absent_and_admitted_without_request(self):
        request = {"workload": "site_interactive", "turn_id": "native-turn", "pool": "codex-native", "model": "fixture-native"}
        arguments = dict(principal_id="macro", host="vps", request_id="native-step", path="/v1/chat/completions",
            payload=self.payload, expected_recipe_digest=self.recipe_digest, include_turn=True)
        self.assertEqual(self.gateway.recover_application(request, **arguments), {"kind": "turn_absent"})
        with patch.object(self.gateway, "_connection", side_effect=sqlite3.OperationalError("fixture unavailable read")):
            with self.assertRaises(LeaseGatewayError):
                self.gateway.recover_application(request, **arguments)
        binding = self.native_begin()
        self.assertEqual(self.gateway.recover_application(request, **arguments)["kind"], "turn_present_new_step")
        self.accounts.unlink()
        self.assertEqual(self.gateway.recover_application(request, **arguments)["kind"], "turn_present_new_step")
        with self.assertRaises(LeaseGatewayError):
            self.native_prepare(binding)
        self.assertEqual(self.gateway.close_application_turn(principal_id="macro", turn_id="native-turn")["disposition"], "closed")
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_native_intentional_steps_keep_original_account_and_finite_expiry(self):
        binding = self.native_begin()
        first = self.native_prepare(binding)
        self.gateway.complete_application(first["dispatch_id"], terminal_receipt=self.native_receipt(first))
        self.clock[0] += 10
        second = self.native_prepare(binding, "next-step")
        self.assertNotEqual(first["dispatch_id"], second["dispatch_id"])
        for key in ("account", "pool", "model", "lease_id", "expires_at"):
            self.assertEqual(first[key], second[key])
        self.gateway.complete_application(second["dispatch_id"], terminal_receipt=self.native_receipt(second))
        with self.assertRaises(LeaseGatewayError):
            self.native_prepare(binding, "over-budget")
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.rows("application_requests")), 2)

    def test_native_incomplete_or_conflicting_evidence_never_settles(self):
        prepared = self.native_prepare(self.native_begin())
        changes = [("served_model", None), ("served_model", "other-model"), ("pool", "glm"),
            ("request_id", "other"), ("caller_host", "other"), ("workload", "other"),
            ("recipe_digest", "f" * 64), ("invocation_digest", "f" * 64), ("source_generation", "f" * 64),
            ("support_generation", "f" * 64), ("physical_host", "other"), ("output_bytes", 65537),
            ("process.cleanup_complete", False), ("process.exited", False), ("process.started", False),
            ("process.stdout_truncated", True), ("process.stderr_truncated", True), ("process.timed_out", True),
            ("process.returncode", 1), ("process.host", "other"), ("process.stdout_bytes", 131073),
            ("provider_terminal.state", "unknown"), ("provider_terminal.attempts_complete", False),
            ("provider_terminal.ambiguous_earlier_send", True), ("provider_terminal.parser_sha256", "f" * 64),
            ("usage.complete", True)]
        for key, value in changes:
            receipt = self.native_receipt(prepared)
            parts = key.split('.')
            if len(parts) == 2: receipt[parts[0]][parts[1]] = value
            else: receipt[key] = value
            with self.subTest(key=key), self.assertRaises(lease_broker.ApplicationAdmissionError):
                self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=receipt)
            self.assertEqual(self.rows("application_requests")[0]["state"], "pending")
        self.gateway.close_application_turn(principal_id="macro", turn_id="native-turn")
        self.assertEqual(self.rows("leases")[0]["state"], "held")

    def test_native_complete_usage_policy_and_hard_limit_are_not_assumed(self):
        self.recipe["usage_policy"] = self.grant["usage_policy"] = "complete_operation"
        self.refresh_native()
        prepared = self.native_prepare(self.native_begin())
        receipt = self.native_receipt(prepared)
        with self.assertRaises(lease_broker.ApplicationAdmissionError):
            self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=receipt)
        receipt["usage"] = {"input_tokens": 20, "output_tokens": 129, "scope": "operation", "complete": True}
        with self.assertRaises(lease_broker.ApplicationAdmissionError):
            self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=receipt)
        receipt["usage"]["output_tokens"] = 128
        self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=receipt)
        self.assertEqual(self.rows("application_requests")[0]["state"], "terminal")

    def test_qualified_provider_failure_can_settle_without_answer_delivery(self):
        prepared = self.native_prepare(self.native_begin())
        receipt = self.native_receipt(prepared)
        receipt["provider_terminal"]["state"] = "failed"
        receipt["process"]["returncode"] = 1
        receipt["output_bytes"] = 0
        self.gateway.close_application_turn(principal_id="macro", turn_id="native-turn")
        self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=receipt)
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_native_terminal_is_idempotent_and_sql_cannot_downgrade_or_rebind_it(self):
        binding = self.native_begin()
        prepared = self.native_prepare(binding)
        receipt = self.native_receipt(prepared)
        first = self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=receipt)
        self.assertEqual(first, self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=receipt))
        self.assertEqual(self.gateway.mark_application_unknown(prepared["dispatch_id"], reason="late_disconnect")["disposition"], "terminal")
        with self.assertRaises(lease_broker.ApplicationAdmissionError):
            self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt={**receipt, "response_digest": "f" * 64})
        original_turn, original_request = self.rows("application_turns")[0], self.rows("application_requests")[0]
        with sqlite3.connect(self.directory / "leases.sqlite") as conn:
            for column in ("transport_kind", "recipe_json", "recipe_digest", "caller_host", "pool", "model", "lease_id"):
                conn.execute("UPDATE application_turns SET " + column + "=NULL")
            for column in ("invocation_json", "invocation_digest", "recipe_digest", "logical_payload_digest", "wire_body_digest"):
                conn.execute("UPDATE application_requests SET " + column + "='changed'")
            conn.execute("UPDATE application_requests SET state='unknown',terminal_receipt=NULL,unknown_reason='late'")
            conn.execute("DELETE FROM application_requests")
            conn.execute("DELETE FROM application_turns")
        self.assertEqual(self.rows("application_turns")[0], original_turn)
        self.assertEqual(self.rows("application_requests")[0], original_request)
        self.assertEqual(self.native_prepare(binding)["terminal_receipt"], receipt)

    def test_native_sql_release_guard_rejects_corrupt_and_unfamiliar_receipts(self):
        prepared = self.native_prepare(self.native_begin())
        original = self.native_receipt(prepared)
        variants = ["not-json", "{}", json.dumps({**original, "status_code": 200}),
            json.dumps({**original, "served_model": None}),
            json.dumps({**original, "process": "not-an-object"}),
            json.dumps({**original, "provider_terminal": {**original["provider_terminal"], "attempts_complete": False}}),
            json.dumps({**original, "usage": {"input_tokens": 0, "output_tokens": 0, "scope": "unknown", "complete": True}}),
            json.dumps({**original, "process": {**original["process"], "stdout_truncated": True}})]
        with sqlite3.connect(self.directory / "leases.sqlite") as conn:
            conn.execute("UPDATE application_turns SET state='closed'")
            for value in variants:
                with self.subTest(receipt=value[:80]):
                    conn.execute("SAVEPOINT invalid_receipt")
                    conn.execute("UPDATE application_requests SET state='terminal', terminal_receipt=?", (value,))
                    conn.execute("UPDATE leases SET state='released'")
                    self.assertEqual(conn.execute("SELECT state FROM leases").fetchone()[0], "held")
                    conn.execute("ROLLBACK TO invalid_receipt")
                    conn.execute("RELEASE invalid_receipt")
        self.gateway.complete_application(prepared["dispatch_id"], terminal_receipt=original)
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_ignored_release_update_is_not_positive_release_proof(self):
        self.native_begin()
        with sqlite3.connect(self.directory / "leases.sqlite") as conn:
            conn.execute("CREATE TRIGGER fixture_hold BEFORE UPDATE OF state ON leases BEGIN SELECT RAISE(IGNORE); END")
        result = self.gateway.close_application_turn(principal_id="macro", turn_id="native-turn")
        self.assertEqual(result["disposition"], "effect_unknown")
        self.assertEqual(self.rows("leases")[0]["state"], "held")
        with self.broker._application_transaction() as conn:
            turn = self.broker._application_turn(conn, "macro", "native-turn")
            self.assertFalse(self.broker._application_release_if_finished(conn, turn))


if __name__ == "__main__":
    unittest.main()
