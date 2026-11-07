"""Bailian uses the same actual admission/SQLite owner; no provider effects."""
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import sqlite3
import unittest

from test_application_turn_admission import ApplicationFixture, offline_acquire, offline_release
import lease_broker
import go_lease_capability as codec
from go_lease_gateway import GoLeaseGateway, LeaseGatewayError


def setUpModule():
    offline_acquire()


def tearDownModule():
    offline_release()


class HTTPAdmissionFixture(ApplicationFixture):
    def setUp(self):
        super().setUp()
        self.recipe = {"schema": "mastermind.application_http_recipe.v1", "pool": "bailian",
            "model": "qwen3.8-flash", "driver_id": "alibaba-token-plan-sg.responses",
            "realm_id": "alibaba-token-plan-sg", "provider": "bailian", "protocol": "responses",
            "endpoint": "https://coding-intl.dashscope.aliyuncs.com/v1/responses",
            "source_projection_sha256": "a" * 64, "credential_owner": "bailian_keys._codex_key_value"}
        _, self.recipe_digest = lease_broker._application_http_recipe(self.recipe,
            pool="bailian", model="qwen3.8-flash")
        self.document["providers"]["bailian"] = copy.deepcopy(self.document["providers"]["go"])
        self.grant.update(pool="bailian", models=["qwen3.8-flash"], recipe_digest=self.recipe_digest)
        self.save()
        self.gateway = self.http_gateway()
        self.scope = {"workload": "site_interactive", "turn_id": "turn-1", "pool": "bailian", "model": "qwen3.8-flash"}
        self.payload = {"model": "qwen3.8-flash", "messages": [{"role": "user", "content": "fixture"}]}
        self.commitment = {"recipe_digest": self.recipe_digest,
            "logical_payload_digest": hashlib.sha256(b"fixture-logical").hexdigest(),
            "wire_body_digest": hashlib.sha256(b"fixture-wire").hexdigest()}

    def http_gateway(self, recipe=None):
        return GoLeaseGateway(str(self.directory / "leases.sqlite"), {"account-a", "account-b"},
            {"fixture-model", "other-model"}, clock=lambda: self.clock[0], signing_key=b"k" * 32,
            application_broker=self.broker, application_http_recipes=(recipe or self.recipe,),
            application_http_accounts={"account-a", "account-b"})

    def http_begin(self, **kwargs):
        return self.gateway.begin_application(self.scope, principal_id="macro", host="vps",
            expected_credential_ref=kwargs.pop("expected_credential_ref", "MACRO_APPLICATION_TOKEN"),
            expected_recipe_digest=kwargs.pop("expected_recipe_digest", self.recipe_digest), **kwargs)

    def http_prepare(self, binding, request_id="step-1", **kwargs):
        return self.gateway.prepare_application(binding["token"], principal_id="macro", host="vps",
            turn_id="turn-1", request_id=request_id, path="/v1/chat/completions", payload=self.payload,
            expected_pool="bailian", transport_commitment=kwargs.pop("transport_commitment", self.commitment), **kwargs)

    def http_receipt(self, permit):
        return {**self.receipt(permit), **self.commitment, "terminal_kind": "http_responses_v1",
            "delivery_digest": hashlib.sha256(b"fixture-chat-delivery").hexdigest(), "served_model": "qwen3.8-flash"}


class HTTPAdmissionTests(HTTPAdmissionFixture):
    def test_same_owner_atomic_identity_and_terminal_release(self):
        binding = self.http_begin()
        self.assertTrue(binding["token"].startswith("app2."))
        permit = self.http_prepare(binding)
        self.assertTrue(permit["dispatch_permitted"])
        row = self.rows("application_requests")[0]
        self.assertEqual({key: row[key] for key in self.commitment}, self.commitment)
        self.assertEqual(self.rows("application_turns")[0]["recipe_json"],
            json.dumps(self.recipe, sort_keys=True, separators=(",", ":")))
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(self.gateway.close_application_turn(principal_id="macro", turn_id="turn-1")["disposition"], "pending")
        receipt = self.http_receipt(permit)
        self.gateway.complete_application(permit["dispatch_id"], terminal_receipt=receipt)
        self.assertEqual(self.rows("leases")[0]["state"], "released")
        self.assertEqual(self.http_prepare(binding)["terminal_receipt"], receipt)

    def test_credential_recipe_and_commitment_are_atomic_narrowing_conditions(self):
        for field, value in (("expected_credential_ref", None), ("expected_credential_ref", "wrong"),
                             ("expected_recipe_digest", None), ("expected_recipe_digest", "b" * 64)):
            with self.subTest(field=field, value=value), self.assertRaises(LeaseGatewayError):
                self.http_begin(**{field: value})
            self.assertEqual(self.rows("leases"), [])
        binding = self.http_begin()
        for commitment in (None, {}, {**self.commitment, "recipe_digest": "b" * 64},
                           {**self.commitment, "wire_body_digest": True}):
            with self.subTest(commitment=commitment), self.assertRaises(LeaseGatewayError):
                self.http_prepare(binding, transport_commitment=commitment)
            self.assertEqual(self.rows("application_requests"), [])

    def test_recipe_and_intent_roll_back_with_original_owner_failure(self):
        with sqlite3.connect(self.directory / "leases.sqlite") as conn:
            conn.execute("CREATE TRIGGER fail_http_turn BEFORE INSERT ON application_turns BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(LeaseGatewayError):
            self.http_begin()
        self.assertEqual(self.rows("leases"), [])
        with sqlite3.connect(self.directory / "leases.sqlite") as conn:
            conn.execute("DROP TRIGGER fail_http_turn")
            conn.execute("CREATE TRIGGER fail_http_request BEFORE INSERT ON application_requests BEGIN SELECT RAISE(ABORT,'fixture'); END")
        binding = self.http_begin()
        with self.assertRaises(LeaseGatewayError):
            self.http_prepare(binding)
        self.assertEqual(self.rows("application_requests"), [])
        self.assertEqual(len(self.rows("leases")), 1)

    def test_concurrent_same_request_grants_exactly_one_dispatch(self):
        binding = self.http_begin()
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: self.http_prepare(binding), range(4)))
        self.assertEqual(sum(bool(result["dispatch_permitted"]) for result in results), 1)
        self.assertEqual(len(self.rows("application_requests")), 1)
        self.assertEqual(len({result["dispatch_id"] for result in results}), 1)

    def test_recovery_uses_original_recipe_before_revocation_expiry_or_rotation(self):
        binding = self.http_begin()
        permit = self.http_prepare(binding)
        self.grant["enabled"] = False
        self.save()
        self.clock[0] = 3000.0
        changed = {**self.recipe, "source_projection_sha256": "c" * 64}
        rotated = self.http_gateway(changed)
        result = rotated.recover_application({**self.scope, "pool": "go"}, principal_id="macro", host="vps",
            request_id="step-1", path="/v1/chat/completions", payload=self.payload,
            expected_recipe_digest=self.recipe_digest)
        self.assertEqual(result["disposition"], "pending")
        self.assertFalse(result["dispatch_permitted"])
        self.assertEqual(result["dispatch_id"], permit["dispatch_id"])
        self.assertEqual(self.http_prepare(binding)["dispatch_id"], permit["dispatch_id"])
        with self.assertRaises(LeaseGatewayError):
            rotated.recover_application(self.scope, principal_id="macro", host="vps",
                request_id="step-1", path="/v1/chat/completions", payload=self.payload,
                expected_recipe_digest="b" * 64)

    def test_sql_identity_and_delete_guards_preserve_original_commitments(self):
        binding = self.http_begin()
        permit = self.http_prepare(binding)
        original_turn = self.rows("application_turns")[0]
        original_request = self.rows("application_requests")[0]
        with sqlite3.connect(self.directory / "leases.sqlite") as conn:
            for key in ("recipe_json", "recipe_digest", "pool", "model", "principal_id", "lease_id"):
                conn.execute("UPDATE application_turns SET " + key + "='changed'")
            for key in ("recipe_digest", "logical_payload_digest", "wire_body_digest", "dispatch_id", "request_digest"):
                conn.execute("UPDATE application_requests SET " + key + "='changed'")
            conn.execute("DELETE FROM application_requests")
            conn.execute("DELETE FROM application_turns")
            conn.execute("UPDATE leases SET state='released'")
        self.assertEqual(self.rows("application_turns")[0], original_turn)
        self.assertEqual(self.rows("application_requests")[0], original_request)
        self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})
        self.assertEqual(self.http_prepare(binding)["dispatch_id"], permit["dispatch_id"])

    def test_http_terminal_cannot_downgrade_to_go_or_change_wire(self):
        permit = self.http_prepare(self.http_begin())
        terminal = self.http_receipt(permit)
        for bad in (self.receipt(permit), {**terminal, "wire_body_digest": "f" * 64},
                    {**terminal, "extra": True}, {**terminal, "usage": {"input_tokens": 1, "output_tokens": 2, "extra": 0}}):
            with self.subTest(bad=bad), self.assertRaises(lease_broker.ApplicationAdmissionError):
                self.gateway.complete_application(permit["dispatch_id"], terminal_receipt=bad)
            with sqlite3.connect(self.directory / "leases.sqlite") as conn:
                conn.execute("UPDATE application_requests SET state='terminal',terminal_receipt=?", (json.dumps(bad),))
                conn.execute("UPDATE application_turns SET state='closed'")
                conn.execute("UPDATE leases SET state='released'")
            self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})
        self.assertEqual(self.gateway.close_application_turn(principal_id="macro", turn_id="turn-1")["disposition"], "effect_unknown")

    def test_bailian_capability_has_separate_pool_domain_and_cannot_authorize_worker(self):
        binding = self.http_begin()
        lease, turn = self.rows("leases")[0], self.rows("application_turns")[0]
        lookup = lambda _: lease
        turn_lookup = lambda *_: turn
        kwargs = dict(principal_id="macro", host="vps", turn_id="turn-1", model="qwen3.8-flash", now=self.clock[0])
        claims = codec.authorize_application(binding["token"], b"k" * 32, lookup, turn_lookup,
            expected_pool="bailian", **kwargs)
        self.assertEqual(claims["recipe_digest"], self.recipe_digest)
        for token in (binding["token"], binding["token"].replace("app2.", "app1.", 1)):
            with self.assertRaises(codec.CapabilityError):
                codec.authorize_application(token, b"k" * 32, lookup, turn_lookup, **kwargs)
            with self.assertRaises(LeaseGatewayError):
                self.gateway.authorize(token, model="qwen3.8-flash", run_id="fixture", host="vps")
        self.assertEqual(self.gateway._models, frozenset({"fixture-model", "other-model"}))
        self.assertNotIn("qwen3.8-flash", self.gateway._models)


if __name__ == "__main__":
    unittest.main()
