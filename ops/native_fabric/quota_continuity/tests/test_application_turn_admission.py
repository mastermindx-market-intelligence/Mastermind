"""Application admission in the existing candidate broker; no live effects."""
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "candidate"), str(ROOT / "source"), str(ROOT / "tests")]
from _offline_boundary import acquire as offline_acquire, release as offline_release
import lease_broker
import go_lease_capability as codec
from go_lease_gateway import GoLeaseGateway, LeaseGatewayError


def setUpModule():
    offline_acquire()


def tearDownModule():
    offline_release()


class ApplicationFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.clock = [1000.0]
        self.grant = dict(grant_id="macro-app", purpose="APPLICATION", enabled=True,
            principal_id="macro", credential_ref="MACRO_APPLICATION_TOKEN", admission_root="service:macro",
            caller_hosts=["vps"], workloads=["site_interactive"], pool="go", accounts=["account-a", "account-b"],
            models=["fixture-model", "other-model"], route="/v1/chat/completions", stream=False,
            expires_at=2000, max_turn_seconds=300, max_steps=2,
            qualification_ref="fixture:controlled-qualification", application_permission_ref="fixture:ordinary-inference")
        self.document = {"schema": "mastermind.provider_accounts.v1", "providers": {"go": {
            "enabled": True, "accounts": [{"name": "account-a", "per_account_cap": 2},
                                            {"name": "account-b", "per_account_cap": 2}]}},
            "application_grants": [self.grant]}
        self.accounts = self.directory / "accounts.json"
        self.save()
        self.broker = self.new_broker()
        self.gateway = self.new_gateway()
        self.assertEqual(Path(lease_broker.__file__).resolve(), ROOT / "candidate/lease_broker.py")
        self.assertEqual(Path(codec.__file__).resolve(), ROOT / "candidate/go_lease_capability.py")

    def save(self):
        self.accounts.write_text(json.dumps(self.document))

    def new_broker(self):
        return lease_broker.Broker(db_path=str(self.directory / "leases.sqlite"),
            lock_path=str(self.directory / "leases.lock"), accounts_path=str(self.accounts),
            now_fn=lambda: self.clock[0], check_pid=False, external_gates=False,
            this_host="vps", status_json=str(self.directory / "status.json"))

    def new_gateway(self, broker=None, **kwargs):
        return GoLeaseGateway(str(self.directory / "leases.sqlite"), {"account-a", "account-b"},
            {"fixture-model", "other-model"}, clock=lambda: self.clock[0], signing_key=b"k" * 32,
            application_broker=broker or self.broker, **kwargs)

    def begin(self, turn="turn-1", gateway=None):
        return (gateway or self.gateway).begin_application(
            {"workload": "site_interactive", "turn_id": turn, "pool": "go", "model": "fixture-model"},
            principal_id="macro", host="vps")

    def prepare(self, binding, request_id="step-1", gateway=None, payload=None):
        return (gateway or self.gateway).prepare_application(binding["token"], principal_id="macro", host="vps",
            turn_id=binding["turn_id"], request_id=request_id, path="/v1/chat/completions",
            payload=payload or {"model": "fixture-model", "messages": [{"role": "user", "content": "fixture"}]})

    def receipt(self, prepared):
        return {"dispatch_id": prepared["dispatch_id"], "request_digest": prepared["request_digest"],
                "lease_id": prepared["lease_id"], "account": prepared["account"], "model": prepared["model"],
                "response_digest": hashlib.sha256(b"fixture-response").hexdigest(), "status_code": 200,
                "completed_at": self.clock[0], "usage": {"input_tokens": 11, "output_tokens": 7}}

    def rows(self, table):
        with sqlite3.connect(self.directory / "leases.sqlite") as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute("SELECT * FROM " + table)]


class AdmissionTests(ApplicationFixture):
    def test_atomic_turn_and_lease_rollback_on_turn_insert_failure(self):
        with sqlite3.connect(self.directory / "leases.sqlite") as conn:
            conn.execute("CREATE TRIGGER fail_turn BEFORE INSERT ON application_turns BEGIN SELECT RAISE(ABORT, 'fixture'); END")
        with self.assertRaises(LeaseGatewayError):
            self.begin()
        self.assertEqual(self.rows("leases"), [])
        self.assertEqual(self.rows("application_turns"), [])

    def test_closed_grants_and_fresh_same_mtime_read(self):
        self.broker.load_accounts_doc()
        before = self.accounts.stat()
        self.grant["enabled"] = False
        self.save()
        os.utime(self.accounts, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(LeaseGatewayError):
            self.begin()
        self.assertEqual(self.rows("leases"), [])
        self.accounts.unlink()
        with self.assertRaises(LeaseGatewayError):
            self.begin()
        self.assertEqual(self.rows("leases"), [])

    def test_grant_shape_types_bounds_references_and_ambiguity(self):
        original = copy.deepcopy(self.grant)
        changes = [("extra", True), ("enabled", 1), ("expires_at", True), ("max_steps", 0),
                   ("max_turn_seconds", 901), ("stream", True), ("pool", "minimax"),
                   ("models", ["fixture-model", "fixture-model"]), ("accounts", ["absent"]),
                   ("qualification_ref", ""), ("workloads", [])]
        for key, value in changes:
            with self.subTest(key=key):
                self.document["application_grants"] = [{**original, key: value}]
                self.save()
                with self.assertRaises(LeaseGatewayError):
                    self.begin()
                self.assertEqual(self.rows("leases"), [])
        self.document["application_grants"] = [original, {**original, "grant_id": "ambiguous"}]
        self.save()
        with self.assertRaises(LeaseGatewayError):
            self.begin()
        self.assertEqual(self.rows("leases"), [])

    def test_duplicate_json_keys_are_not_an_authorization_override(self):
        self.accounts.write_text(json.dumps(self.document).replace('"enabled": true', '"enabled": false, "enabled": true', 1))
        with self.assertRaises(LeaseGatewayError):
            self.begin()
        self.assertEqual(self.rows("leases"), [])

    def test_shared_worker_application_last_slot_and_stable_service_root(self):
        self.document["providers"]["go"]["accounts"] = [{"name": "account-a", "per_account_cap": 1}]
        self.grant["accounts"] = ["account-a"]
        self.save()
        def application():
            return self.begin()["ok"]
        def worker():
            return self.broker.acquire("worker-root", "go", host="vps", pid=os.getpid(),
                                       model="fixture-model", wait=0).ok
        with ThreadPoolExecutor(max_workers=2) as pool:
            winners = list(pool.map(lambda function: function(), [application, worker]))
        self.assertEqual(sum(winners), 1)
        self.assertEqual(len([row for row in self.rows("leases") if row["state"] in ("held", "rented")]), 1)
        for row in self.rows("application_turns"):
            self.assertEqual(row["admission_root"], "service:macro")

    def test_gateway_account_envelope_is_intersected_before_admission(self):
        gateway = GoLeaseGateway(str(self.directory / "leases.sqlite"), {"unavailable-account"},
            {"fixture-model"}, clock=lambda: self.clock[0], application_broker=self.broker)
        self.assertFalse(self.begin(gateway=gateway)["ok"])
        self.assertEqual(self.rows("leases"), [])

    def test_duplicate_turn_preserves_binding_deadline_and_changed_input_refuses(self):
        first = self.begin()
        self.clock[0] += 15
        second = self.begin()
        for key in ("lease_id", "account", "model", "expires_at", "created_at"):
            self.assertEqual(first[key], second[key])
        self.assertEqual(len(self.rows("leases")), 1)
        with self.assertRaises(lease_broker.ApplicationAdmissionError):
            self.broker.begin_application_turn(principal_id="macro", caller_host="vps", workload="site_interactive",
                turn_id="turn-1", pool="go", model="other-model")

    def test_gateway_requires_same_canonical_database_and_actual_owner(self):
        other = self.directory / "other.sqlite"
        sqlite3.connect(other).close()
        with self.assertRaises(LeaseGatewayError):
            GoLeaseGateway(str(other), {"account-a"}, {"fixture-model"}, application_broker=self.broker)
        with self.assertRaises(LeaseGatewayError):
            GoLeaseGateway(str(self.directory / "leases.sqlite"), [], [], application_broker=object())
        unconfigured = GoLeaseGateway(str(self.directory / "leases.sqlite"), [], [])
        with self.assertRaises(LeaseGatewayError):
            self.begin(gateway=unconfigured)
        hardlink = self.directory / "hardlink.sqlite"
        os.link(self.directory / "leases.sqlite", hardlink)
        with self.assertRaises(LeaseGatewayError):
            GoLeaseGateway(str(hardlink), [], [], application_broker=self.broker)
        symlink = self.directory / "symlink.sqlite"
        symlink.symlink_to(self.directory / "leases.sqlite")
        gateway = GoLeaseGateway(str(symlink), {"account-a", "account-b"}, {"fixture-model"},
                                clock=lambda: self.clock[0], application_broker=self.broker)
        self.assertTrue(self.begin(gateway=gateway)["ok"])
        replacement = self.directory / "replacement.sqlite"
        sqlite3.connect(replacement).close()
        os.replace(replacement, self.directory / "leases.sqlite")
        with self.assertRaises(LeaseGatewayError):
            self.begin("after-replacement", gateway=gateway)

    def test_expiry_during_final_eligibility_check_never_creates_dispatch_intent(self):
        binding = self.begin()
        grantable = self.broker.grantable_accounts
        def expires_during_check(pool):
            accounts = grantable(pool)
            self.clock[0] = binding["expires_at"]
            return accounts
        with patch.object(self.broker, "grantable_accounts", side_effect=expires_during_check):
            with self.assertRaises(LeaseGatewayError):
                self.prepare(binding)
        self.assertEqual(self.rows("application_requests"), [])

    def test_closed_request_state_and_receipt_constraints(self):
        binding = self.begin()
        self.prepare(binding)
        with sqlite3.connect(self.directory / "leases.sqlite") as conn:
            for mutation in ["state='unrecognized'", "state='terminal',terminal_receipt=NULL",
                             "state='pending',terminal_receipt='{}'"]:
                with self.subTest(mutation=mutation), self.assertRaises(sqlite3.IntegrityError):
                    conn.execute("UPDATE application_requests SET " + mutation)

    def test_application_codec_is_not_a_worker_capability_and_binds_actual_model(self):
        binding = self.begin()
        self.assertTrue(binding["token"].startswith("app1."))
        lease = self.rows("leases")[0]
        self.assertEqual(lease["pid"], 0)
        self.assertEqual(lease["purpose"], "APPLICATION")
        with self.assertRaises(codec.CapabilityError):
            codec.authorize(binding["token"], b"k" * 32, lambda _: lease,
                            model="fixture-model", run_id="fake-worker", host="vps", now=self.clock[0])
        with self.assertRaises(codec.CapabilityError):
            codec.mint(b"k" * 32, lease, root="service:macro", model="fixture-model",
                       run_id="fake-worker", host="vps", now=self.clock[0])
        turn = self.rows("application_turns")[0]
        changed = {**turn, "model": "other-model"}
        with self.assertRaises(codec.CapabilityError):
            codec.mint_application(b"k" * 32, lease, changed, now=self.clock[0])
        for identity in [("attacker", "vps", "turn-1", "fixture-model"),
                         ("macro", "other-host", "turn-1", "fixture-model"),
                         ("macro", "vps", "other-turn", "fixture-model"),
                         ("macro", "vps", "turn-1", "other-model")]:
            with self.subTest(identity=identity), self.assertRaises(codec.CapabilityError):
                codec.authorize_application(binding["token"], b"k" * 32, lambda _: lease,
                    lambda *_: turn, principal_id=identity[0], host=identity[1], turn_id=identity[2],
                    model=identity[3], now=self.clock[0])

    def test_worker_codec_compatibility_and_application_rejects_worker_token(self):
        result = self.broker.acquire("worker-root", "go", host="vps", pid=os.getpid(),
                                     model="fixture-model", ttl=300, wait=0)
        lease = next(row for row in self.rows("leases") if row["id"] == result.lease_id)
        token = codec.mint(b"k" * 32, lease, root="worker-root", model="fixture-model",
                           run_id="worker-run", host="vps", now=self.clock[0])
        claims = codec.authorize(token, b"k" * 32, lambda _: lease,
                                  model="fixture-model", run_id="worker-run", host="vps", now=self.clock[0])
        self.assertEqual(claims["account"], result.account)
        with self.assertRaises(codec.CapabilityError):
            codec.authorize_application(token, b"k" * 32, lambda _: lease, lambda *_: {},
                principal_id="macro", host="vps", turn_id="turn-1", model="fixture-model", now=self.clock[0])

    def test_route_stream_and_nonfinite_payload_refuse_before_intent(self):
        binding = self.begin()
        for path, payload in [("/v1/responses", {"model": "fixture-model"}),
                              ("/v1/chat/completions", {"model": "fixture-model", "stream": True}),
                              ("/v1/chat/completions", {"model": "fixture-model", "temperature": float("nan")})]:
            with self.subTest(path=path, payload=payload), self.assertRaises(LeaseGatewayError):
                self.gateway.prepare_application(binding["token"], principal_id="macro", host="vps",
                    turn_id="turn-1", request_id="step-1", path=path, payload=payload)
        self.assertEqual(self.rows("application_requests"), [])


if __name__ == "__main__":
    unittest.main()
