"""GLM HTTP APPLICATION conformance against the original temporary Broker."""
import copy
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from test_application_turn_admission import ApplicationFixture, offline_acquire, offline_release

import lease_broker
import go_lease_capability as codec
from go_lease_gateway import GoLeaseGateway, LeaseGatewayError


def setUpModule():
    offline_acquire()


def tearDownModule():
    offline_release()


class GlmApplicationFixture(ApplicationFixture):
    def setUp(self):
        super().setUp()
        self.recipe = {
            "schema": "mastermind.application_http_recipe.v1", "pool": "glm",
            "model": "glm-5.3", "driver_id": "zai-coding-plan.chat-completions",
            "realm_id": "zai-coding-plan", "provider": "glm",
            "protocol": "openai-chat",
            "endpoint": "https://api.z.ai/api/coding/paas/v4/chat/completions",
            "source_projection_sha256": "a" * 64,
            "credential_owner": "glm_keys.selected_account_key",
        }
        _, self.recipe_digest = lease_broker._application_http_recipe(
            self.recipe, pool="glm", model="glm-5.3")
        self.document["providers"]["glm"] = copy.deepcopy(self.document["providers"]["go"])
        self.document["providers"]["glm"]["enabled"] = "auto"
        self.grant.update(pool="glm", models=["glm-5.3"], recipe_digest=self.recipe_digest)
        self.save()
        self.gateway = self.http_gateway()
        self.scope = {"workload": "site_interactive", "turn_id": "turn-1",
                      "pool": "glm", "model": "glm-5.3"}
        self.payload = {"model": "glm-5.3", "messages": [{"role": "user", "content": "fixture"}]}
        self.commitment = {
            "recipe_digest": self.recipe_digest,
            "logical_payload_digest": hashlib.sha256(b"fixture-logical").hexdigest(),
            "wire_body_digest": hashlib.sha256(b"fixture-wire").hexdigest(),
        }

    def http_gateway(self, recipe=None, accounts=None):
        return GoLeaseGateway(
            str(self.directory / "leases.sqlite"), {"account-a", "account-b"},
            {"fixture-model", "other-model"}, clock=lambda: self.clock[0],
            signing_key=b"k" * 32, application_broker=self.broker,
            application_http_recipes=(recipe or self.recipe,),
            application_http_accounts=accounts if accounts is not None else
                {"glm": {"account-a", "account-b"}})

    def http_begin(self, **kwargs):
        return self.gateway.begin_application(
            self.scope, principal_id="macro", host="vps",
            expected_credential_ref="MACRO_APPLICATION_TOKEN",
            expected_recipe_digest=self.recipe_digest, **kwargs)

    def http_prepare(self, binding, request_id="step-1", **kwargs):
        return self.gateway.prepare_application(
            binding["token"], principal_id="macro", host="vps", turn_id="turn-1",
            request_id=request_id, path="/v1/chat/completions", payload=self.payload,
            expected_pool="glm", transport_commitment=self.commitment, **kwargs)

    def http_receipt(self, permit):
        return {**self.receipt(permit), **self.commitment,
                "terminal_kind": "http_chat_v1",
                "delivery_digest": hashlib.sha256(b"fixture-chat-delivery").hexdigest(),
                "served_model": "glm-5.3"}


class GlmApplicationAdmissionTests(GlmApplicationFixture):
    def test_original_owner_identity_terminal_release_and_replay(self):
        binding = self.http_begin()
        self.assertTrue(binding["token"].startswith("app4."))
        permit = self.http_prepare(binding)
        self.assertTrue(permit["dispatch_permitted"])
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(self.rows("leases")[0]["pid"], 0)
        self.assertIsNone(self.rows("application_turns")[0]["transport_kind"])
        self.assertEqual({key: self.rows("application_requests")[0][key]
                          for key in self.commitment}, self.commitment)
        self.assertEqual(self.gateway.close_application_turn(
            principal_id="macro", turn_id="turn-1")["disposition"], "pending")
        receipt = self.http_receipt(permit)
        self.gateway.complete_application(permit["dispatch_id"], terminal_receipt=receipt)
        self.assertEqual(self.rows("leases")[0]["state"], "released")
        self.assertEqual(self.http_prepare(binding)["terminal_receipt"], receipt)

    def test_concurrent_duplicate_request_has_one_dispatch(self):
        binding = self.http_begin()
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(lambda _: self.http_prepare(binding), range(4)))
        self.assertEqual(sum(result["dispatch_permitted"] for result in results), 1)
        self.assertEqual(len({result["dispatch_id"] for result in results}), 1)
        self.assertEqual(len(self.rows("application_requests")), 1)

    def test_recovery_precedes_revocation_expiry_and_recipe_rotation(self):
        binding = self.http_begin()
        permit = self.http_prepare(binding)
        self.grant["enabled"] = False
        self.save()
        self.clock[0] = 3000.0
        rotated = self.http_gateway({**self.recipe, "source_projection_sha256": "c" * 64})
        result = rotated.recover_application(
            {**self.scope, "pool": "go"}, principal_id="macro", host="vps",
            request_id="step-1", path="/v1/chat/completions", payload=self.payload,
            expected_recipe_digest=self.recipe_digest)
        self.assertEqual(result["disposition"], "pending")
        self.assertFalse(result["dispatch_permitted"])
        self.assertEqual(result["dispatch_id"], permit["dispatch_id"])
        self.assertEqual(self.http_prepare(binding)["dispatch_id"], permit["dispatch_id"])
        with self.assertRaises(LeaseGatewayError):
            rotated.recover_application(
                self.scope, principal_id="macro", host="vps", request_id="step-1",
                path="/v1/chat/completions", payload=self.payload,
                expected_recipe_digest="b" * 64)

    def test_glm_http_capability_cannot_authorize_native_worker_or_other_pool(self):
        binding = self.http_begin()
        lease, turn = self.rows("leases")[0], self.rows("application_turns")[0]
        lookup, turn_lookup = lambda _: lease, lambda *_: turn
        kwargs = dict(principal_id="macro", host="vps", turn_id="turn-1",
                      model="glm-5.3", now=self.clock[0])
        claims = codec.authorize_application(
            binding["token"], b"k" * 32, lookup, turn_lookup, expected_pool="glm", **kwargs)
        self.assertEqual(claims["v"], 4)
        self.assertEqual(claims["recipe_digest"], self.recipe_digest)
        for prefix in ("app1.", "app2.", "app3."):
            with self.subTest(prefix=prefix), self.assertRaises(codec.CapabilityError):
                codec.authorize_application(binding["token"].replace("app4.", prefix, 1),
                    b"k" * 32, lookup, turn_lookup, expected_pool="glm", **kwargs)
        for pool in ("go", "bailian", "codex-native"):
            with self.subTest(pool=pool), self.assertRaises(codec.CapabilityError):
                codec.authorize_application(binding["token"], b"k" * 32, lookup,
                                            turn_lookup, expected_pool=pool, **kwargs)
        with self.assertRaises(LeaseGatewayError):
            self.gateway.authorize(binding["token"], model="glm-5.3",
                                   run_id="fixture", host="vps")
        self.assertNotIn("glm-5.3", self.gateway._models)

    def test_glm_cannot_settle_with_responses_or_native_receipt(self):
        permit = self.http_prepare(self.http_begin())
        terminal = self.http_receipt(permit)
        invalid = (
            self.receipt(permit),
            {**terminal, "terminal_kind": "http_responses_v1"},
            {**terminal, "terminal_kind": "native_cli_operation_v1"},
            {**terminal, "wire_body_digest": "f" * 64},
            {**terminal, "extra": True},
        )
        for bad in invalid:
            with self.subTest(kind=bad.get("terminal_kind")):
                with self.assertRaises(lease_broker.ApplicationAdmissionError):
                    self.gateway.complete_application(permit["dispatch_id"], terminal_receipt=bad)
                with sqlite3.connect(self.directory / "leases.sqlite") as conn:
                    conn.execute("UPDATE application_requests SET state='terminal',terminal_receipt=?",
                                 (json.dumps(bad),))
                    conn.execute("UPDATE application_turns SET state='closed'")
                    conn.execute("UPDATE leases SET state='released'")
                self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})
        self.assertEqual(self.gateway.close_application_turn(
            principal_id="macro", turn_id="turn-1")["disposition"], "effect_unknown")

    def test_glm_auto_is_exact_provider_schema_and_grant_enabled_stays_boolean(self):
        self.grant["enabled"] = "auto"
        self.save()
        with self.assertRaises(LeaseGatewayError):
            self.http_begin()
        self.assertEqual(self.rows("leases"), [])
        self.grant["enabled"] = True
        self.document["providers"]["glm"]["enabled"] = "AUTO"
        self.save()
        with self.assertRaises(LeaseGatewayError):
            self.http_begin()
        self.assertEqual(self.rows("leases"), [])

    def test_glm_http_grant_refuses_mixed_native_fields(self):
        self.grant["transport_kind"] = "native_cli_operation_v1"
        self.save()
        with self.assertRaises(LeaseGatewayError):
            self.http_begin()
        self.assertEqual(self.rows("leases"), [])

    def test_glm_requires_explicit_pool_account_namespace(self):
        for accounts in ({"account-a", "account-b"},
                         {"bailian": {"account-a", "account-b"}},
                         {"glm": {"account-a"}, "bailian": {"account-b"}}):
            with self.subTest(accounts=accounts), self.assertRaises(LeaseGatewayError):
                self.http_gateway(accounts=accounts)

    def test_glm_recipe_cannot_change_endpoint_credential_owner_or_model(self):
        for change in (
            {"endpoint": "https://api.z.ai/api/paas/v4/chat/completions"},
            {"credential_owner": "bailian_keys._codex_key_value"},
            {"protocol": "responses"},
            {"model": "unqualified-model"},
            {"source_projection_sha256": True},
        ):
            with self.subTest(change=change), self.assertRaises(lease_broker.ApplicationAdmissionError):
                lease_broker._application_http_recipe(
                    {**self.recipe, **change}, pool="glm", model="glm-5.3")


class GlmApplicationFacadeTests(GlmApplicationFixture):
    """The original GLM module surface shares the existing v4/Broker owner."""
    def setUp(self):
        super().setUp()
        import importlib.util
        from pathlib import Path
        import sys
        root = Path(__file__).resolve().parents[2] / "paid_canonical_glm/candidate"
        saved = {name: sys.modules.get(name) for name in
                 ("glm_lease_capability", "_fixture_glm_application_codec",
                  "_fixture_glm_application_gateway")}
        def restore():
            for name, value in saved.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value
        self.addCleanup(restore)
        def load(name, filename):
            spec = importlib.util.spec_from_file_location(name, root / filename)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            return module
        self.glm_codec = load("_fixture_glm_application_codec", "glm_lease_capability.py")
        sys.modules["glm_lease_capability"] = self.glm_codec
        self.glm_gateway = load("_fixture_glm_application_gateway", "glm_lease_gateway.py")
        self.original_gateway = self.gateway
        self.facade = self.glm_gateway.GlmApplicationGateway(self.gateway)

    def test_real_v4_codec_roundtrip_is_separate_from_every_prior_domain(self):
        import base64
        import hmac
        self.http_begin()
        lease, turn = self.rows("leases")[0], self.rows("application_turns")[0]
        token = self.glm_codec.mint_application(b"k" * 32, lease, turn, now=self.clock[0])
        kwargs = dict(principal_id="macro", host="vps", turn_id="turn-1",
                      model="glm-5.3", now=self.clock[0])
        claims = self.glm_codec.authorize_application(
            token, b"k" * 32, lambda _: lease, lambda *_: turn, **kwargs)
        self.assertEqual(claims["v"], 4)
        self.assertEqual(claims["recipe_digest"], self.recipe_digest)
        self.assertEqual(claims, codec.authorize_application(
            token, b"k" * 32, lambda _: lease, lambda *_: turn,
            expected_pool="glm", **kwargs))
        prefix, encoded, _ = token.split(".")
        raw = codec._base64url_decode(encoded.encode("ascii"))
        for domain in (codec._APPLICATION_DOMAIN, codec._APPLICATION_HTTP_DOMAIN,
                       codec._APPLICATION_NATIVE_DOMAIN):
            signature = base64.urlsafe_b64encode(
                hmac.new(b"k" * 32, domain + raw, hashlib.sha256).digest()).rstrip(b"=").decode()
            foreign = prefix + "." + encoded + "." + signature
            with self.subTest(domain=domain), self.assertRaises(self.glm_codec.CapabilityError):
                self.glm_codec.authorize_application(
                    foreign, b"k" * 32, lambda _: lease, lambda *_: turn, **kwargs)
        for authorize in (self.glm_codec.authorize, self.glm_codec.authorize_canonical):
            with self.subTest(authorize=authorize.__name__), self.assertRaises(self.glm_codec.CapabilityError):
                authorize(token, b"k" * 32, lambda _: lease, model="glm-5.3",
                          run_id="fixture", host="vps", now=self.clock[0])

    def test_foreign_owner_pool_and_native_kind_refuse_without_new_rows(self):
        with self.assertRaises(self.glm_gateway.LeaseGatewayError):
            self.glm_gateway.GlmApplicationGateway(object())
        with self.assertRaises(self.glm_gateway.LeaseGatewayError):
            self.facade.begin_application({**self.scope, "pool": "go"},
                principal_id="macro", host="vps",
                expected_credential_ref="MACRO_APPLICATION_TOKEN")
        self.assertEqual(self.rows("leases"), [])
        binding = self.http_begin()
        lease, turn = self.rows("leases")[0], self.rows("application_turns")[0]
        before = (self.rows("leases"), self.rows("application_turns"), self.rows("application_requests"))
        for bad in ({**turn, "pool": "go"}, {**turn, "transport_kind": "native_cli_operation_v1"}):
            with self.subTest(change=bad["pool"]), self.assertRaises(
                    (codec.CapabilityError, self.glm_codec.CapabilityError)):
                self.glm_codec.mint_application(b"k" * 32, lease, bad, now=self.clock[0])
        for prefix in ("app1.", "app2.", "app3."):
            with self.subTest(prefix=prefix), self.assertRaises(self.glm_gateway.LeaseGatewayError):
                self.facade.prepare_application(
                    binding["token"].replace("app4.", prefix, 1),
                    principal_id="macro", host="vps", turn_id="turn-1",
                    request_id="foreign", path="/v1/chat/completions", payload=self.payload,
                    expected_pool="glm", transport_commitment=self.commitment)
        self.assertEqual(before, (self.rows("leases"), self.rows("application_turns"),
                                  self.rows("application_requests")))

    def test_facade_completion_and_revoked_recovery_keep_original_dispatch(self):
        self.gateway = self.facade
        binding = self.http_begin()
        permit = self.http_prepare(binding)
        terminal = self.http_receipt(permit)
        pending = self.original_gateway.recover_application(
            self.scope, principal_id="macro", host="vps", request_id="step-1",
            path="/v1/chat/completions", payload=self.payload,
            expected_recipe_digest=self.recipe_digest)
        self.assertEqual(pending["dispatch_id"], permit["dispatch_id"])
        self.assertEqual(self.facade.close_application_turn(
            principal_id="macro", turn_id="turn-1")["disposition"], "pending")
        self.facade.complete_application(permit["dispatch_id"], terminal_receipt=terminal)
        self.grant["enabled"] = False
        self.save()
        self.clock[0] = 3000
        recovered = self.facade.recover_application(
            {**self.scope, "pool": "go"}, principal_id="macro", host="vps",
            request_id="step-1", path="/v1/chat/completions", payload=self.payload,
            expected_recipe_digest=self.recipe_digest)
        self.assertFalse(recovered["dispatch_permitted"])
        self.assertEqual(recovered["dispatch_id"], permit["dispatch_id"])
        self.assertEqual(recovered["terminal_receipt"], terminal)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.rows("application_requests")), 1)
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_facade_unknown_keeps_the_original_lease_and_recovery_identity(self):
        self.gateway = self.facade
        binding = self.http_begin()
        permit = self.http_prepare(binding)
        self.facade.mark_application_unknown(permit["dispatch_id"], reason="fixture_disconnect")
        recovered = self.facade.recover_application(
            self.scope, principal_id="macro", host="vps", request_id="step-1",
            path="/v1/chat/completions", payload=self.payload,
            expected_recipe_digest=self.recipe_digest)
        self.assertFalse(recovered["dispatch_permitted"])
        self.assertEqual(recovered["dispatch_id"], permit["dispatch_id"])
        self.assertEqual(self.facade.close_application_turn(
            principal_id="macro", turn_id="turn-1")["disposition"], "effect_unknown")
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})
