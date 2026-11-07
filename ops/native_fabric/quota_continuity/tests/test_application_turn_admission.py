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
from threading import Barrier
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

    def test_distinct_models_share_one_canonical_account_slot_concurrently(self):
        self.document["providers"]["go"]["accounts"] = [{"name": "account-a", "per_account_cap": 1}]
        self.grant["accounts"] = ["account-a"]
        self.save()
        barrier = Barrier(2)

        def admit(model):
            gateway = self.new_gateway(self.new_broker())
            barrier.wait(timeout=5)
            return gateway.begin_application({"workload": "site_interactive",
                "turn_id": model, "pool": "go", "model": model}, principal_id="macro", host="vps")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(admit, ["fixture-model", "other-model"]))
        self.assertEqual(sum(result["ok"] for result in results), 1)
        leases = self.rows("leases")
        self.assertEqual(len(leases), 1)
        self.assertEqual((leases[0]["pool"], leases[0]["account"]), ("go", "account-a"))
        self.assertEqual(len(self.rows("application_turns")), 1)
        self.assertEqual(self.rows("application_requests"), [])

    def test_model_caps_cannot_expand_the_shared_account_cap(self):
        self.document["providers"]["go"]["accounts"] = [{"name": "account-a", "per_account_cap": 2,
            "per_model_caps": {"fixture-model": 10, "other-model": 10}}]
        self.grant["accounts"] = ["account-a"]
        self.save()
        barrier = Barrier(2)

        def admit(model):
            gateway = self.new_gateway(self.new_broker())
            barrier.wait(timeout=5)
            return gateway.begin_application({"workload": "site_interactive",
                "turn_id": model, "pool": "go", "model": model}, principal_id="macro", host="vps")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(admit, ["fixture-model", "other-model"]))
        self.assertTrue(all(result["ok"] for result in results))
        self.assertEqual({result["model"] for result in results}, {"fixture-model", "other-model"})
        self.assertEqual({result["account"] for result in results}, {"account-a"})
        self.assertEqual(len({result["lease_id"] for result in results}), 2)
        self.assertFalse(self.begin("third-operation")["ok"])
        self.assertEqual(len(self.rows("leases")), 2)
        self.assertEqual(len(self.rows("application_turns")), 2)
        self.assertEqual(self.rows("application_requests"), [])

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


class NativeApplicationFixture(ApplicationFixture):
    """Only qualification/compiler/provider evidence is synthetic, never A."""
    def setUp(self):
        super().setUp()
        self.recipe = {"schema": "mastermind.application_native_recipe.v1",
            "transport_kind": "native_cli_operation_v1", "pool": "codex-native", "model": "fixture-native",
            "driver_id": "fixture-native-driver", "profile": "plaintext_single_turn_v1",
            "physical_host": "fixture-ubuntu1", "source_generation": "1" * 64,
            "support_generation": "2" * 64, "binary_sha256": "3" * 64, "compiler_sha256": "4" * 64,
            "profile_sha256": "5" * 64, "policy_sha256": "6" * 64, "result_parser_sha256": "7" * 64,
            "argv_semantics_sha256": "8" * 64,
            "output_contract": {"mode": "hard_maximum", "token_bound": 1024},
            "usage_policy": "nullable_operation", "limits": {"max_input_bytes": 65536,
                "max_capture_bytes": 131072, "max_output_bytes": 65536, "max_turn_seconds": 300, "max_steps": 2}}
        self.document["providers"]["codex-native"] = copy.deepcopy(self.document["providers"]["go"])
        self.grant.update(pool="codex-native", models=["fixture-native"],
            transport_kind="native_cli_operation_v1", output_limit_mode="hard_maximum", usage_policy="nullable_operation")
        self.payload = {"model": "fixture-native", "messages": [{"role": "system", "content": "Fixture system."},
            {"role": "user", "content": "Fixture question."}], "max_tokens": 128}
        self.refresh_native()

    def refresh_native(self):
        _, self.recipe_digest = lease_broker._application_native_recipe(self.recipe,
            pool=self.recipe["pool"], model=self.recipe["model"])
        self.grant["recipe_digest"] = self.recipe_digest
        self.save()
        self.gateway = self.native_gateway()

    def native_gateway(self, *, recipe=None, broker=None):
        value = self.recipe if recipe is None else recipe
        return self.new_gateway(broker,
            application_native_recipes=(value,),
            application_native_accounts={value["pool"]: {"account-a", "account-b"}})

    def native_begin(self, turn="native-turn", gateway=None, **kwargs):
        return (gateway or self.gateway).begin_application(
            {"workload": "site_interactive", "turn_id": turn, "pool": self.recipe["pool"], "model": "fixture-native"},
            principal_id="macro", host="vps", expected_credential_ref="MACRO_APPLICATION_TOKEN",
            expected_recipe_digest=kwargs.pop("expected_recipe_digest", self.recipe_digest), **kwargs)

    def native_commitment(self, payload=None):
        value = self.payload if payload is None else payload
        messages = value["messages"]
        raw = json.dumps({"system_text": messages[0]["content"] if len(messages) == 2 else None,
                          "user_text": messages[-1]["content"]}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        logical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        return {**{key: self.recipe[key] for key in ("physical_host", "source_generation", "support_generation",
                "binary_sha256", "compiler_sha256", "profile_sha256", "policy_sha256", "result_parser_sha256", "argv_semantics_sha256")},
            "recipe_digest": self.recipe_digest, "logical_payload_digest": hashlib.sha256(logical).hexdigest(),
            "input_sha256": hashlib.sha256(raw).hexdigest(),
            "command_sha256": hashlib.sha256(b"synthetic-qualified-compiler-command").hexdigest()}

    def native_prepare(self, binding, request_id="native-step", *, gateway=None, payload=None, commitment=None):
        value = self.payload if payload is None else payload
        return (gateway or self.gateway).prepare_application(binding["token"], principal_id="macro", host="vps",
            turn_id=binding["turn_id"], request_id=request_id, path="/v1/chat/completions", payload=value,
            expected_pool=self.recipe["pool"], transport_commitment=self.native_commitment(value) if commitment is None else commitment)

    def native_receipt(self, prepared):
        invocation = prepared["native_invocation"]
        return {"terminal_kind": "native_cli_operation_v1",
            **{key: invocation[key] for key in ("principal_id", "caller_host", "workload", "admission_root",
                "turn_id", "request_id", "dispatch_id", "lease_id", "pool", "account", "model", "request_digest",
                "recipe_digest", "logical_payload_digest", "invocation_digest")},
            **{key: invocation["commitment"][key] for key in ("physical_host", "source_generation", "support_generation")},
            "response_digest": hashlib.sha256(b"fixture native answer").hexdigest(), "delivery_digest": None,
            "served_model": "fixture-native", "completed_at": self.clock[0], "output_bytes": 21,
            "provider_terminal": {"state": "completed", "evidence_sha256": "a" * 64,
                "parser_sha256": self.recipe["result_parser_sha256"], "attempts_complete": True, "ambiguous_earlier_send": False},
            "process": {"receipt_sha256": "b" * 64, "host": self.recipe["physical_host"], "pid": 12345,
                "returncode": 0, "started": True, "exited": True, "cleanup_complete": True, "timed_out": False,
                "stdout_bytes": 128, "stderr_bytes": 0, "stdout_truncated": False, "stderr_truncated": False,
                "stdout_sha256": "c" * 64, "stderr_sha256": hashlib.sha256(b"").hexdigest()},
            "usage": {"input_tokens": None, "output_tokens": None, "scope": "unknown", "complete": False}}

    def authorize_native(self, prepared, *, invocation=None, token=None, gateway=None):
        return (gateway or self.gateway).authorize_native_dispatch(
            token or prepared["native_dispatch_capability"], principal_id="macro", caller_host="vps",
            turn_id="native-turn", request_id="native-step",
            invocation=prepared["native_invocation"] if invocation is None else invocation)


class NativeAdmissionTests(NativeApplicationFixture):
    def test_native_application_and_worker_contend_for_the_same_last_account_slot(self):
        self.document["providers"]["codex-native"]["accounts"] = [{"name": "account-a", "per_account_cap": 1}]
        self.grant["accounts"] = ["account-a"]
        self.save()
        def application(): return self.native_begin()["ok"]
        def worker(): return self.broker.acquire("worker-root", "codex-native", host="vps", pid=os.getpid(),
            model="fixture-native", wait=0).ok
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda call: call(), (application, worker)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(len([row for row in self.rows("leases") if row["state"] in {"held", "rented"}]), 1)

    def test_real_native_permit_binds_original_rows_without_worker_identity(self):
        binding = self.native_begin()
        self.assertTrue(binding["token"].startswith("app3."))
        prepared = self.native_prepare(binding)
        self.assertTrue(prepared["dispatch_permitted"])
        self.assertTrue(prepared["native_dispatch_capability"].startswith("appd1."))
        claims = self.authorize_native(prepared)
        self.assertEqual(claims["physical_host"], "fixture-ubuntu1")
        lease, request = self.rows("leases")[0], self.rows("application_requests")[0]
        self.assertEqual((lease["purpose"], lease["pid"], lease["host"]), ("APPLICATION", 0, "vps"))
        self.assertIsNone(request["wire_body_digest"])
        self.assertEqual(hashlib.sha256(request["invocation_json"].encode()).hexdigest(), request["invocation_digest"])
        frozen = json.loads(request["invocation_json"])
        self.assertNotIn("invocation_digest", frozen)
        self.assertNotIn("native_dispatch_capability", frozen)
        self.assertEqual(frozen["expires_at"], binding["expires_at"])
        self.assertEqual(hashlib.sha256(prepared["native_input_bytes"]).hexdigest(), frozen["commitment"]["input_sha256"])
        self.assertEqual(self.gateway._models, frozenset({"fixture-model", "other-model"}))
        self.assertNotIn("fixture-native", self.gateway._models)

    def test_soft_preference_requires_exact_trusted_recipe_and_grant_opt_in(self):
        hard = self.native_begin()
        soft_payload = {key: value for key, value in self.payload.items() if key != "max_tokens"}
        soft_payload["preferred_tokens"] = 128
        with self.assertRaises(LeaseGatewayError):
            self.native_prepare(hard, payload=soft_payload)
        self.assertEqual(self.rows("application_requests"), [])
        self.recipe["output_contract"]["mode"] = "preferred_tokens"
        self.refresh_native()
        with self.assertRaises(LeaseGatewayError):
            self.native_begin("not-opted-in")
        self.grant["output_limit_mode"] = "preferred_tokens"
        self.save()
        self.payload = soft_payload
        binding = self.native_begin("soft-turn")
        prepared = self.native_prepare(binding)
        self.assertEqual(prepared["native_invocation"]["output_limit"], {"mode": "preferred_tokens", "tokens": 128})
        with self.assertRaises(LeaseGatewayError):
            self.native_prepare(binding, "conflicting-limit", payload={**soft_payload, "max_tokens": 128})

    def test_plaintext_profile_rejects_history_tools_media_sampling_and_unbounded_limits(self):
        binding = self.native_begin()
        variants = [dict(self.payload, tools=[]), dict(self.payload, temperature=0),
            dict(self.payload, stream=True), dict(self.payload, preferred_tokens=128),
            dict(self.payload, max_tokens=True), dict(self.payload, max_tokens=0),
            dict(self.payload, max_tokens=1025), dict(self.payload, messages=self.payload["messages"] * 2),
            dict(self.payload, messages=[{"role": "user", "content": [{"type": "text", "text": "x"}]}]),
            dict(self.payload, messages=[{"role": "assistant", "content": "x"}]),
            dict(self.payload, messages=[{"role": "user", "content": "x" * 70000}]),
            {key: value for key, value in self.payload.items() if key != "max_tokens"}]
        for payload in variants:
            with self.subTest(payload_keys=sorted(payload)), self.assertRaises(LeaseGatewayError):
                self.native_prepare(binding, payload=payload, commitment=self.native_commitment())
        self.assertEqual(self.rows("application_requests"), [])

    def test_closed_native_recipe_and_grant_are_real_admission_conditions(self):
        for key, value in (("extra", True), ("profile", "worker-agent"), ("binary_sha256", "unknown"),
                           ("physical_host", "bad host"), ("limits", {}), ("usage_policy", "assume_zero")):
            with self.subTest(key=key), self.assertRaises(LeaseGatewayError):
                self.native_gateway(recipe={**self.recipe, key: value})
        for field, value in (("transport_kind", "http"), ("output_limit_mode", "guess"),
                             ("recipe_digest", "f" * 64), ("application_permission_ref", "")):
            saved = self.grant[field]
            self.grant[field] = value
            self.save()
            with self.subTest(field=field), self.assertRaises(LeaseGatewayError):
                self.native_begin()
            self.grant[field] = saved
        self.save()
        self.assertEqual(self.rows("leases"), [])

    def test_current_enabled_and_transport_account_intersection_cannot_be_bypassed(self):
        self.document["providers"]["codex-native"]["accounts"][0]["enabled"] = False
        self.grant["accounts"] = ["account-a"]
        self.save()
        self.assertFalse(self.native_begin()["ok"])
        self.assertEqual(self.rows("leases"), [])
        self.document["providers"]["codex-native"]["enabled"] = "auto"
        self.save()
        with self.assertRaises(LeaseGatewayError):
            self.native_begin()

    def test_native_subclasses_and_dicts_are_not_the_privileged_gateway_context(self):
        class ForgedGateway(GoLeaseGateway):
            pass
        with self.assertRaises(LeaseGatewayError):
            ForgedGateway(str(self.directory / "leases.sqlite"), [], [], application_broker=self.broker,
                application_native_recipes=(self.recipe,), application_native_accounts={"codex-native": ["account-a"]})
        with self.assertRaises(LeaseGatewayError):
            GoLeaseGateway(str(self.directory / "leases.sqlite"), [], [],
                application_native_recipes=(self.recipe,), application_native_accounts={"codex-native": ["account-a"]},
                application_broker={"verified": True})

    def test_native_turn_and_dispatch_domains_cannot_cross_use_http_or_worker_capabilities(self):
        binding = self.native_begin()
        prepared = self.native_prepare(binding)
        for token in (binding["token"], binding["token"].replace("app3.", "app1.", 1),
                      binding["token"].replace("app3.", "app2.", 1),
                      prepared["native_dispatch_capability"].replace("appd1.", "app3.", 1)):
            with self.subTest(prefix=token.split('.')[0]), self.assertRaises(LeaseGatewayError):
                self.gateway.authorize(token, model="fixture-native", run_id="worker", host="vps")
        for token in (binding["token"], prepared["native_dispatch_capability"].replace("appd1.", "app3.", 1)):
            with self.assertRaises(LeaseGatewayError):
                self.authorize_native(prepared, token=token)
        with self.assertRaises(LeaseGatewayError):
            self.gateway.prepare_application(binding["token"], principal_id="macro", host="vps",
                turn_id="native-turn", request_id="native-step", path="/v1/chat/completions", payload=self.payload)
        import hmac
        parts = binding["token"].split('.')
        raw = codec._base64url_decode(parts[1].encode())
        wrong_mac = hmac.new(b"k" * 32, codec._APPLICATION_DOMAIN + raw, hashlib.sha256).digest()
        wrong_domain = "app3." + parts[1] + "." + codec._base64url_encode(wrong_mac).decode()
        with self.assertRaises(LeaseGatewayError):
            self.native_prepare({**binding, "token": wrong_domain})

    def test_changed_invocation_correlation_and_expired_token_refuse(self):
        prepared = self.native_prepare(self.native_begin())
        for key, value in (("dispatch_id", "other"), ("account", "account-b"), ("pool", "glm"),
                ("model", "other-model"), ("lease_id", "other"), ("principal_id", "other"),
                ("request_digest", "f" * 64), ("expires_at", 9999), ("invocation_digest", "e" * 64)):
            with self.subTest(key=key), self.assertRaises(LeaseGatewayError):
                self.authorize_native(prepared, invocation={**prepared["native_invocation"], key: value})
        for key in ("physical_host", "source_generation", "support_generation", "binary_sha256", "command_sha256"):
            changed = copy.deepcopy(prepared["native_invocation"])
            changed["commitment"][key] = "other-host" if key == "physical_host" else "e" * 64
            with self.subTest(key=key), self.assertRaises(LeaseGatewayError):
                self.authorize_native(prepared, invocation=changed)
        self.clock[0] = prepared["expires_at"]
        with self.assertRaises(LeaseGatewayError):
            self.authorize_native(prepared)


# Frozen pre-native APPLICATION schema/trigger owner, copied exactly from
# public e5/3b broker blob9b22048111a2bb3112c65b0abfb57f0870126ed6.
# This fixture is distinct from source/lease_broker.py, which predates APPLICATION.
class HistoricalApplicationSchema(lease_broker.Broker):
    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        import quota_circuit
        quota_circuit.init_schema(conn)
        lcols = {r[1] for r in conn.execute("PRAGMA table_info(leases)")}
        if "renewable" not in lcols:
            conn.execute(
                "ALTER TABLE leases ADD COLUMN renewable INTEGER NOT NULL DEFAULT 1"
            )
        if "model" not in lcols:
            conn.execute(
                "ALTER TABLE leases ADD COLUMN model TEXT NOT NULL DEFAULT ''"
            )
        if "purpose" not in lcols:
            conn.execute("ALTER TABLE leases ADD COLUMN purpose TEXT NOT NULL DEFAULT 'WORKER'")
        conn.execute("""CREATE TABLE IF NOT EXISTS application_turns (
            principal_id TEXT NOT NULL, turn_id TEXT NOT NULL,
            grant_id TEXT NOT NULL, grant_digest TEXT NOT NULL,
            caller_host TEXT NOT NULL, workload TEXT NOT NULL,
            admission_root TEXT NOT NULL, pool TEXT NOT NULL, account TEXT NOT NULL,
            model TEXT NOT NULL, lease_id TEXT NOT NULL UNIQUE,
            created_at REAL NOT NULL, expires_at REAL NOT NULL,
            max_steps INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'open',
            PRIMARY KEY (principal_id, turn_id))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS application_requests (
            principal_id TEXT NOT NULL, turn_id TEXT NOT NULL, request_id TEXT NOT NULL,
            request_digest TEXT NOT NULL, dispatch_id TEXT NOT NULL UNIQUE,
            state TEXT NOT NULL CHECK (state IN ('pending','unknown','terminal')), created_at REAL NOT NULL,
            terminal_receipt TEXT, unknown_reason TEXT,
            CHECK ((state='terminal' AND terminal_receipt IS NOT NULL)
                   OR (state IN ('pending','unknown') AND terminal_receipt IS NULL)),
            PRIMARY KEY (principal_id, turn_id, request_id))""")
        # Add commitments to the existing owner rows in this same migration
        # transaction. Historical Go rows stay NULL and retain their v1 proof.
        for table, additions in (
                ("application_turns", ("recipe_json", "recipe_digest", "selection_json", "selection_digest")),
                ("application_requests", ("recipe_digest", "logical_payload_digest", "wire_body_digest"))):
            columns = {row[1] for row in conn.execute("PRAGMA table_info(" + table + ")")}
            for column in additions:
                if column not in columns:
                    conn.execute("ALTER TABLE " + table + " ADD COLUMN " + column + " TEXT")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_selection_binding_v1
            BEFORE UPDATE ON application_turns WHEN
                NEW.selection_json IS NOT OLD.selection_json
                OR NEW.selection_digest IS NOT OLD.selection_digest
                OR (OLD.selection_digest IS NOT NULL AND (
                    NEW.principal_id IS NOT OLD.principal_id OR NEW.turn_id IS NOT OLD.turn_id
                    OR NEW.grant_id IS NOT OLD.grant_id OR NEW.grant_digest IS NOT OLD.grant_digest
                    OR NEW.caller_host IS NOT OLD.caller_host OR NEW.workload IS NOT OLD.workload
                    OR NEW.admission_root IS NOT OLD.admission_root OR NEW.pool IS NOT OLD.pool
                    OR NEW.account IS NOT OLD.account OR NEW.model IS NOT OLD.model
                    OR NEW.lease_id IS NOT OLD.lease_id OR NEW.created_at IS NOT OLD.created_at
                    OR NEW.expires_at IS NOT OLD.expires_at OR NEW.max_steps IS NOT OLD.max_steps))
            BEGIN SELECT RAISE(IGNORE); END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_selection_delete_v1
            BEFORE DELETE ON application_turns WHEN OLD.selection_digest IS NOT NULL
            BEGIN SELECT RAISE(IGNORE); END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_http_turn_binding_v1
            BEFORE UPDATE ON application_turns WHEN OLD.pool='bailian' AND (
                NEW.principal_id IS NOT OLD.principal_id OR NEW.turn_id IS NOT OLD.turn_id
                OR NEW.grant_id IS NOT OLD.grant_id OR NEW.grant_digest IS NOT OLD.grant_digest
                OR NEW.caller_host IS NOT OLD.caller_host OR NEW.workload IS NOT OLD.workload
                OR NEW.admission_root IS NOT OLD.admission_root OR NEW.pool IS NOT OLD.pool
                OR NEW.account IS NOT OLD.account OR NEW.model IS NOT OLD.model
                OR NEW.lease_id IS NOT OLD.lease_id OR NEW.created_at IS NOT OLD.created_at
                OR NEW.expires_at IS NOT OLD.expires_at OR NEW.max_steps IS NOT OLD.max_steps
                OR NEW.recipe_json IS NOT OLD.recipe_json OR NEW.recipe_digest IS NOT OLD.recipe_digest)
            BEGIN SELECT RAISE(IGNORE); END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_http_request_binding_v1
            BEFORE UPDATE ON application_requests WHEN OLD.recipe_digest IS NOT NULL AND (
                NEW.principal_id IS NOT OLD.principal_id OR NEW.turn_id IS NOT OLD.turn_id
                OR NEW.request_id IS NOT OLD.request_id OR NEW.request_digest IS NOT OLD.request_digest
                OR NEW.dispatch_id IS NOT OLD.dispatch_id OR NEW.created_at IS NOT OLD.created_at
                OR NEW.recipe_digest IS NOT OLD.recipe_digest
                OR NEW.logical_payload_digest IS NOT OLD.logical_payload_digest
                OR NEW.wire_body_digest IS NOT OLD.wire_body_digest)
            BEGIN SELECT RAISE(IGNORE); END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_http_turn_delete_v1
            BEFORE DELETE ON application_turns WHEN OLD.pool='bailian'
            BEGIN SELECT RAISE(IGNORE); END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_http_request_delete_v1
            BEFORE DELETE ON application_requests WHEN OLD.recipe_digest IS NOT NULL
            BEGIN SELECT RAISE(IGNORE); END""")
        # Older immutable worker releases also run GC against this same DB.
        # Keep application custody in the canonical schema, where an old PID,
        # TTL or generic release path cannot erase it. IGNORE affects only the
        # incompatible row; ordinary worker updates continue in the same batch.
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_lease_binding_v1
            BEFORE UPDATE ON leases WHEN OLD.purpose='APPLICATION' AND (
                NEW.purpose IS NOT OLD.purpose OR NEW.id IS NOT OLD.id
                OR NEW.orchestrator_id IS NOT OLD.orchestrator_id OR NEW.pool IS NOT OLD.pool
                OR NEW.account IS NOT OLD.account OR NEW.model IS NOT OLD.model
                OR NEW.host IS NOT OLD.host OR NEW.pid IS NOT OLD.pid
                OR NEW.granted_at IS NOT OLD.granted_at OR NEW.ttl IS NOT OLD.ttl
                OR NEW.last_heartbeat IS NOT OLD.last_heartbeat
                OR NEW.renewable > OLD.renewable)
            BEGIN SELECT RAISE(IGNORE); END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_lease_delete_v1
            BEFORE DELETE ON leases WHEN OLD.purpose='APPLICATION'
            BEGIN SELECT RAISE(IGNORE); END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_lease_release_v1
            BEFORE UPDATE OF state ON leases WHEN OLD.purpose='APPLICATION'
            AND OLD.state IN ('held','rented') AND NEW.state NOT IN ('held','rented')
            AND NOT EXISTS (
                SELECT 1 FROM application_turns t WHERE t.lease_id=OLD.id AND t.state='closed'
                AND NOT EXISTS (
                    SELECT 1 FROM application_requests r
                    WHERE r.principal_id=t.principal_id AND r.turn_id=t.turn_id
                    AND CASE WHEN r.state='terminal' AND json_valid(r.terminal_receipt)=1 THEN
                        CASE WHEN json_type(r.terminal_receipt)='object'
                            AND json_extract(r.terminal_receipt,'$.dispatch_id')=r.dispatch_id
                            AND json_extract(r.terminal_receipt,'$.request_digest')=r.request_digest
                            AND json_extract(r.terminal_receipt,'$.lease_id')=t.lease_id
                            AND json_extract(r.terminal_receipt,'$.account')=t.account
                            AND json_extract(r.terminal_receipt,'$.model')=t.model
                            AND json_type(r.terminal_receipt,'$.response_digest')='text'
                            AND length(json_extract(r.terminal_receipt,'$.response_digest'))=64
                            AND json_extract(r.terminal_receipt,'$.response_digest') NOT GLOB '*[^0-9a-f]*'
                            AND json_type(r.terminal_receipt,'$.status_code')='integer'
                            AND json_extract(r.terminal_receipt,'$.status_code') BETWEEN 200 AND 599
                            AND json_type(r.terminal_receipt,'$.completed_at') IN ('integer','real')
                            AND json_extract(r.terminal_receipt,'$.completed_at')>=r.created_at
                            AND json_type(r.terminal_receipt,'$.usage')='object'
                            AND (json_type(r.terminal_receipt,'$.usage.input_tokens')='null'
                                 OR (json_type(r.terminal_receipt,'$.usage.input_tokens')='integer'
                                     AND json_extract(r.terminal_receipt,'$.usage.input_tokens') BETWEEN 0 AND 1000000000000))
                            AND (json_type(r.terminal_receipt,'$.usage.output_tokens')='null'
                                 OR (json_type(r.terminal_receipt,'$.usage.output_tokens')='integer'
                                     AND json_extract(r.terminal_receipt,'$.usage.output_tokens') BETWEEN 0 AND 1000000000000))
                        THEN 0 ELSE 1 END ELSE 1 END=1))
            BEGIN SELECT RAISE(IGNORE); END""")
        # The HTTP extension retains every v1 terminal condition and adds its
        # original recipe/wire binding. An old broker's release/GC cannot turn
        # a downgraded Go-shaped receipt into proof for a Bailian operation.
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_http_lease_release_v2
            BEFORE UPDATE OF state ON leases WHEN OLD.purpose='APPLICATION'
            AND OLD.pool='bailian' AND OLD.state IN ('held','rented')
            AND NEW.state NOT IN ('held','rented')
            AND NOT EXISTS (
                SELECT 1 FROM application_turns t WHERE t.lease_id=OLD.id
                AND t.pool=OLD.pool AND t.account=OLD.account AND t.model=OLD.model
                AND t.state='closed' AND json_valid(t.recipe_json)=1
                AND length(t.recipe_digest)=64
                AND t.recipe_digest NOT GLOB '*[^0-9a-f]*'
                AND NOT EXISTS (
                    SELECT 1 FROM application_requests r
                    WHERE r.principal_id=t.principal_id AND r.turn_id=t.turn_id
                    AND CASE WHEN r.state='terminal' AND json_valid(r.terminal_receipt)=1 THEN
                        CASE WHEN json_extract(r.terminal_receipt,'$.terminal_kind')='http_responses_v1'
                            AND (SELECT count(*) FROM json_each(r.terminal_receipt))=15
                            AND NOT EXISTS (SELECT 1 FROM json_each(r.terminal_receipt) j
                                WHERE j.key NOT IN ('dispatch_id','request_digest','lease_id','account','model',
                                    'response_digest','status_code','completed_at','usage','terminal_kind',
                                    'recipe_digest','logical_payload_digest','wire_body_digest','delivery_digest','served_model'))
                            AND (SELECT count(*) FROM json_each(r.terminal_receipt,'$.usage'))=2
                            AND NOT EXISTS (SELECT 1 FROM json_each(r.terminal_receipt,'$.usage') j
                                WHERE j.key NOT IN ('input_tokens','output_tokens'))
                            AND r.recipe_digest=t.recipe_digest
                            AND json_extract(r.terminal_receipt,'$.recipe_digest')=r.recipe_digest
                            AND length(r.logical_payload_digest)=64
                            AND r.logical_payload_digest NOT GLOB '*[^0-9a-f]*'
                            AND json_extract(r.terminal_receipt,'$.logical_payload_digest')=r.logical_payload_digest
                            AND length(r.wire_body_digest)=64
                            AND r.wire_body_digest NOT GLOB '*[^0-9a-f]*'
                            AND json_extract(r.terminal_receipt,'$.wire_body_digest')=r.wire_body_digest
                            AND (json_type(r.terminal_receipt,'$.delivery_digest')='null'
                                 OR (json_type(r.terminal_receipt,'$.delivery_digest')='text'
                                     AND length(json_extract(r.terminal_receipt,'$.delivery_digest'))=64
                                     AND json_extract(r.terminal_receipt,'$.delivery_digest') NOT GLOB '*[^0-9a-f]*'))
                            AND (json_type(r.terminal_receipt,'$.served_model')='null'
                                 OR (json_type(r.terminal_receipt,'$.served_model')='text'
                                     AND length(json_extract(r.terminal_receipt,'$.served_model')) BETWEEN 1 AND 256
                                     AND instr(json_extract(r.terminal_receipt,'$.served_model'),char(0))=0))
                        THEN 0 ELSE 1 END ELSE 1 END=1))
            BEGIN SELECT RAISE(IGNORE); END""")
        wcols = {r[1] for r in conn.execute("PRAGMA table_info(waiters)")}
        if "last_heartbeat" not in wcols:
            conn.execute("ALTER TABLE waiters ADD COLUMN last_heartbeat REAL")
            conn.execute(
                "UPDATE waiters SET last_heartbeat = enqueued_at "
                "WHERE last_heartbeat IS NULL"
            )



def historical_application_database(case):
    case.directory = case.directory / "pre-native"
    case.directory.mkdir()
    return HistoricalApplicationSchema(db_path=str(case.directory / "leases.sqlite"),
        lock_path=str(case.directory / "leases.lock"), accounts_path=str(case.accounts),
        now_fn=lambda: case.clock[0], check_pid=False, external_gates=False,
        this_host="vps", status_json=str(case.directory / "status.json"))


if __name__ == "__main__":
    unittest.main()
