"""Registered-route APPLICATION selection and admission for all nine pools.

Real pure picker, real policy/strict ledger, real B gateway projection, real A
broker/SQLite with fresh grants. Only accounts, grants and inventory are
synthetic; no provider, credential, CLI or network is used and selection
performs no effect.
"""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

from test_application_turn_admission import NativeApplicationFixture
import lease_broker
import pick
import pool_ledger
from go_lease_gateway import ApplicationNativeSelection, ApplicationSelectionProfile, \
    ApplicationSelectionRefused, LeaseGatewayError

NATIVE_POOLS = ("codex-native", "claude-native", "glm", "minimax", "grok", "cursor", "ocfree")
# pool -> (payload model, task class, picker mode). Default fixtures use
# distinct names; the fixed-pool collision case registers the same name twice.
POOL_MODELS = {
    "go": ("fixture-model", "mechanical", "go"),
    "bailian": ("qwen3.8-flash", "mechanical", "bailian"),
    "glm": ("glm-5.3-flash", "mechanical", "glm"),
    "minimax": ("MiniMax-M3", "mechanical", "minimax"),
    "grok": ("grok-4.7", "mechanical", "grok"),
    "cursor": ("cursor-composer", "high_level", "cursor"),
    "codex-native": ("fixture-codex", "mechanical", "codex-native"),
    "claude-native": ("fixture-claude", "mechanical", "claude-native"),
    "ocfree": ("mimo-v2.5-free", "mechanical", "oc-free"),
}


def _policy_document():
    return {
        "routing": {
            "execute_order": ["minimax", "glm-flash", "bailian", "grok", "cursor"],
            "judgment_order": ["glm-5.3", "grok", "cursor", "fable"],
            "acceptance_floor": "0.6 over last 20",
        },
        "pools": {
            "go": {"enabled": True, "task_classes": ["mechanical", "review", "build"],
                   "worker_models": ["fixture-model"], "default_model": "fixture-model",
                   "capabilities": {"tools": True, "vision": False}},
            "glm": {"enabled": True, "models": {"executor": "glm-5.3-flash"}},
            "grok": {"enabled": True, "windows": {"weekly": {}}},
            "minimax": {"enabled": True},
            "bailian": {"enabled": True},
            "cursor": {"enabled": True},
            "codex-native": {"enabled": True},
            "claude-native": {"enabled": True},
            "ocfree": {"enabled": True},
        },
    }


class RegisteredPoolFixture(NativeApplicationFixture):
    def setUp(self):
        super().setUp()
        self.document["providers"] = {pool: {"enabled": True, "accounts": [
            {"name": "account-a", "per_account_cap": 2}, {"name": "account-b", "per_account_cap": 2}]}
            for pool in POOL_MODELS}
        self.template = self.recipe
        self.native_recipes, self.digests = {}, {}
        for pool in NATIVE_POOLS:
            recipe = copy.deepcopy(self.template)
            recipe.update(pool=pool, model=POOL_MODELS[pool][0],
                          driver_id="fixture-" + pool + "-driver")
            encoded, digest = lease_broker._application_native_recipe(recipe, pool=pool, model=recipe["model"])
            recipe["__digest__"] = digest
            self.native_recipes[pool] = recipe
            self.digests[(pool, recipe["model"])] = digest
        self.http_recipe = {"schema": "mastermind.application_http_recipe.v1", "pool": "bailian",
            "model": POOL_MODELS["bailian"][0], "driver_id": "alibaba-token-plan-sg.responses",
            "realm_id": "alibaba-token-plan-sg", "provider": "bailian", "protocol": "responses",
            "endpoint": "https://bailian.fixture.invalid/api/v2/responses",
            "source_projection_sha256": "b" * 64, "credential_owner": "bailian_keys._codex_key_value"}
        _, self.http_digest = lease_broker._application_http_recipe(
            self.http_recipe, pool="bailian", model=self.http_recipe["model"])
        self.document["application_grants"] = [
            self.grant_for(pool, POOL_MODELS[pool][0]) for pool in POOL_MODELS]
        self.save()
        self.policy_path = self.directory / "pools.yaml"
        self.policy_path.write_text(json.dumps(_policy_document()))
        self.ledger_path = self.directory / "ledger.jsonl"
        pool_ledger.create_ledger_file(self.ledger_path)
        for module, name, value in ((pick, "POOLS_YAML", str(self.policy_path)),
                                    (pool_ledger, "LEDGER_PATH", str(self.ledger_path))):
            guard = patch.object(module, name, value)
            guard.start()
            self.addCleanup(guard.stop)
        self.purpose_document = self.purpose_for("go")
        self.profile = ApplicationSelectionProfile(source_generation="a" * 64,
            ingress_digest=hashlib.sha256(Path(lease_broker.__file__).with_name("go_shim.py")
                                          .read_bytes()).hexdigest(),
            account_profile=self.accounts)
        self.rebuild_gateway()

    def grant_for(self, pool, model, *, grant_id=None):
        grant = dict(grant_id=grant_id or "macro-app-" + pool.replace("-", ""),
            purpose="APPLICATION", enabled=True, principal_id="macro",
            credential_ref="MACRO_APPLICATION_TOKEN", admission_root="service:macro",
            caller_hosts=["vps"], workloads=["site_interactive"], pool=pool,
            accounts=["account-a", "account-b"], models=[model],
            route="/v1/chat/completions", stream=False, expires_at=2000,
            max_turn_seconds=300, max_steps=2,
            qualification_ref="fixture:controlled-qualification",
            application_permission_ref="fixture:ordinary-inference")
        if pool == "bailian":
            grant["recipe_digest"] = self.http_digest
        elif pool in NATIVE_POOLS:
            grant.update(transport_kind="native_cli_operation_v1",
                recipe_digest=self.native_recipes[pool]["__digest__"],
                output_limit_mode="hard_maximum", usage_policy="nullable_operation")
        return grant

    def projections(self):
        return {(pool, recipe["model"]): ApplicationNativeSelection(
                    pool=pool, model=recipe["model"],
                    mode=POOL_MODELS[pool][2],
                    source_generation=recipe["source_generation"])
                for pool, recipe in self.native_recipes.items()}

    def rebuild_gateway(self, **kwargs):
        options = dict(application_selection_profile=self.profile,
            application_http_recipes=(self.http_recipe,),
            application_http_accounts=frozenset({"account-a", "account-b"}),
            application_native_recipes=tuple(
                {key: value for key, value in recipe.items() if key != "__digest__"}
                for recipe in self.native_recipes.values()),
            application_native_accounts={pool: {"account-a", "account-b"} for pool in NATIVE_POOLS},
            application_native_selection=self.projections())
        options.update(kwargs)
        self.gateway = self.new_gateway(**options)

    def purpose_for(self, pool):
        # Incumbent role policy: cursor never carries labor classes (R30), so
        # its registered route is exercised with the operator class instead.
        mechanical = pool != "cursor"
        task = {"task_class": "mechanical" if mechanical else "high_level",
                "route_key": "fixture-registered-pool-selection", "needs": [],
                "escalation_reason": "fixture registered pool economic witness"}
        if mechanical:
            task["task_complexity"] = "C1_ROUTINE_BOUNDED"
        return {"purpose_id": "fixture-registered-pool-operation",
            "source_ref": "fixture:qualified-registered-purpose", "task": task}

    def payload_for(self, pool, **changes):
        payload = {"model": POOL_MODELS[pool][0],
            "messages": [{"role": "system", "content": "Fixture system."},
                         {"role": "user", "content": "Fixture question."}], "max_tokens": 128}
        if pool == "bailian":
            payload["stream"] = False
        payload.update(changes)
        return payload

    def select(self, pool, *, payload=None, purpose=None, turn="turn-1", scope_pool=None):
        payload = self.payload_for(pool) if payload is None else payload
        return self.gateway.select_application(
            {"workload": "site_interactive", "turn_id": turn,
             "pool": scope_pool or pool, "model": payload["model"]},
            principal_id="macro", host="vps", credential_ref="MACRO_APPLICATION_TOKEN",
            purpose=purpose or self.purpose_for(pool), payload=payload)

    def begin_selected(self, pool, *, payload=None, turn="turn-1"):
        payload = self.payload_for(pool) if payload is None else payload
        purpose = self.purpose_for(pool)
        selected = self.select(pool, payload=payload, purpose=purpose, turn=turn)
        digest = (self.digests.get((pool, payload["model"])) if pool in NATIVE_POOLS
                  else self.http_digest if pool == "bailian" else None)
        binding = self.gateway.begin_application(
            {"workload": "site_interactive", "turn_id": turn, "pool": pool, "model": payload["model"]},
            principal_id="macro", host="vps", expected_credential_ref="MACRO_APPLICATION_TOKEN",
            expected_recipe_digest=digest, expected_selection=selected,
            selection_purpose=purpose, selection_payload=payload)
        return selected, binding

    def rows(self, table):
        with sqlite3.connect(self.directory / "leases.sqlite") as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute("SELECT * FROM " + table)]

    def assert_no_effect(self):
        self.assertEqual(self.rows("leases"), [])
        self.assertEqual(self.rows("application_turns"), [])
        self.assertEqual(self.rows("application_requests"), [])


class RegisteredPoolSelectionTests(RegisteredPoolFixture):
    def test_each_registered_pool_selects_and_admits_its_exact_route(self):
        for pool, (model, _, mode) in POOL_MODELS.items():
            with self.subTest(pool=pool):
                selected, binding = self.begin_selected(pool, turn="turn-" + pool)
                self.assertTrue(binding["ok"])
                self.assertEqual(binding["disposition"], "admitted")
                identity = selected["identity"]
                self.assertEqual((identity["pool"], identity["model"]), (pool, model))
                self.assertEqual(identity["mode"], mode)
                self.assertEqual(identity["host"], "vps")
                self.assertEqual(identity["observation_source"], "broker-ledger-room")
                self.assertEqual(identity["task"]["requested_model"], model)
                self.assertEqual(selected["profile"]["pool"], pool)
                self.assertEqual(selected["profile"]["streaming"], False)
                self.assertEqual(identity["grant_ref"]["grant_id"], "macro-app-" + pool.replace("-", ""))
                self.assertEqual(selected["schema"], "mastermind.application_turn_selection.v1")
                self.assertEqual(sorted(selected),
                                 sorted({"schema", "purpose", "purpose_digest", "profile", "profile_digest",
                                         "identity", "commitments", "quality_records_sha256", "fresh_s"}))
                self.assertIn("now_epoch", selected["commitments"])
                self.assertIn("policy_critical_sha256", selected["commitments"])
                turn = [row for row in self.rows("application_turns") if row["turn_id"] == "turn-" + pool][0]
                self.assertEqual((turn["pool"], turn["model"]), (pool, model))
                self.assertEqual(turn["grant_id"], identity["grant_ref"]["grant_id"])
                self.assertIsNotNone(turn["selection_json"])
                self.assertEqual(turn["selection_digest"],
                                 hashlib.sha256(turn["selection_json"].encode()).hexdigest())
                self.assertIn(binding["token"].split(".", 1)[0],
                              ("app1", "app2", "app3"))
                lease = [row for row in self.rows("leases") if row["id"] == turn["lease_id"]][0]
                self.assertEqual((lease["purpose"], lease["pool"], lease["host"]),
                                 ("APPLICATION", pool, "vps"))
                self.gateway.close_application_turn(principal_id="macro", turn_id="turn-" + pool)
                self.assertEqual([row for row in self.rows("leases")
                                  if row["id"] == turn["lease_id"]][0]["state"], "released")

    def test_catalogue_offers_only_the_exact_requested_route_and_never_hijacks(self):
        # Routes are (pool, model) keyed by this request's exact payload model:
        # one registered route, the full canonical pool order, no substitutes.
        with patch.object(pick, "select_application", wraps=pick.select_application) as selector:
            selected = self.select("minimax")
            self.assertEqual(selected["identity"]["pool"], "minimax")
            catalogue = selector.call_args.kwargs["catalogue"]
            self.assertEqual(catalogue["pool_order"], list(pick._APPLICATION_POOL_ORDER))
            self.assertEqual(sorted(catalogue["pools"]), ["minimax"])
            recipe = catalogue["pools"]["minimax"]["recipes"][0]
            self.assertEqual((recipe["model"], recipe["mode"]),
                             (POOL_MODELS["minimax"][0], "minimax"))
            self.assertEqual(sorted(selector.call_args.kwargs["observations"]), ["minimax"])
        for pool in ("go", "glm", "bailian", "grok", "cursor", "codex-native",
                     "claude-native", "ocfree"):
            self.assertEqual(self.select(pool)["identity"]["pool"], pool)

        # Two eligible native pools deliberately expose the identical model
        # under this principal and credential reference. The bound Claude pool
        # must remain usable even when the unbound Codex pool ranks before it.
        shared_model = POOL_MODELS["codex-native"][0]
        recipe = self.native_recipes["claude-native"]
        recipe["model"] = shared_model
        encoded, digest = lease_broker._application_native_recipe(
            {key: value for key, value in recipe.items() if key != "__digest__"},
            pool="claude-native", model=shared_model)
        recipe["__digest__"] = digest
        self.digests[("claude-native", shared_model)] = digest
        self.document["application_grants"] = [
            grant for grant in self.document["application_grants"]
            if grant["pool"] != "claude-native"]
        bound_grant = self.grant_for("claude-native", shared_model)
        self.document["application_grants"].append(bound_grant)
        self.save()
        self.rebuild_gateway()
        payload = self.payload_for("claude-native", model=shared_model)
        with patch.object(pick, "select_application", wraps=pick.select_application) as selector:
            selected = self.select("claude-native", payload=payload)
            self.assertEqual((selected["identity"]["pool"], selected["identity"]["model"]),
                             ("claude-native", shared_model))
            self.assertEqual(list(selector.call_args.kwargs["catalogue"]["pools"]),
                             ["claude-native"])
            self.assertEqual(list(selector.call_args.kwargs["observations"]), ["claude-native"])
            self.assertEqual(selector.call_count, 1)
        bound_grant["enabled"] = False
        self.save()
        with patch.object(pick, "select_application", wraps=pick.select_application) as selector:
            with self.assertRaises(ApplicationSelectionRefused):
                self.select("claude-native", payload=payload)
            self.assertEqual(selector.call_args.kwargs["catalogue"]["pools"], {})
            self.assertEqual(selector.call_count, 1)
        self.assertEqual(self.select("codex-native")["identity"]["pool"], "codex-native")
        self.assert_no_effect()

    def test_selection_uses_one_readonly_snapshot_one_accounts_reading_and_no_effects(self):
        reads = []
        original = lease_broker._read_application_accounts
        def counting(path):
            reads.append(path)
            return original(path)
        with patch.object(lease_broker, "_read_application_accounts", counting), \
             patch.object(self.broker, "_conn", side_effect=AssertionError("write connection")), \
             patch.object(self.broker, "_lock", side_effect=AssertionError("admission lock")), \
             patch.object(self.broker, "_gc_locked", side_effect=AssertionError("GC")):
            self.select("glm")
            self.select("bailian")
        self.assertEqual(len(reads), 2)
        self.assertEqual(Path(reads[0]), self.accounts)
        self.assert_no_effect()

    def test_missing_native_projection_excludes_selection_but_keeps_fixed_route(self):
        self.rebuild_gateway(application_native_selection=None)
        with self.assertRaises(ApplicationSelectionRefused):
            self.select("codex-native")
        self.assert_no_effect()
        # The fixed native route itself is unchanged: admission without any
        # selection still admits on the same registered recipe and grant.
        payload = self.payload_for("codex-native")
        binding = self.gateway.begin_application(
            {"workload": "site_interactive", "turn_id": "turn-fixed", "pool": "codex-native",
             "model": payload["model"]},
            principal_id="macro", host="vps", expected_credential_ref="MACRO_APPLICATION_TOKEN",
            expected_recipe_digest=self.native_recipes["codex-native"]["__digest__"])
        self.assertTrue(binding["ok"])
        view = self.gateway.application_pool_view(principal_id="macro", host="vps",
            workload="site_interactive", credential_ref="MACRO_APPLICATION_TOKEN",
            bound_pool="go", go_models=frozenset({"fixture-model"}),
            source={"source_generation": "a" * 64, "ingress_sha256": "c" * 64,
                    "gateway_sha256": "d" * 64})
        rows = {row["pool"]: row for row in view["pools"]}
        self.assertEqual(rows["codex-native"]["models"][0]["application_state"], "unqualified")
        self.assertEqual(rows["codex-native"]["models"][0]["transport_state"], "unqualified")
        # The bound go route keeps its own configured state: the missing native
        # projection never breaks fixed or recovery admission.
        self.assertEqual(rows["go"]["models"][0]["application_state"], "configured")

    def test_unknown_room_refuses_without_reporting_zero_or_positive(self):
        # An unobserved canonical inventory is unknown: the owner facts API
        # omits the model from model_room instead of reporting 0 or a positive.
        import sqlite3 as sqlite3_module
        document = copy.deepcopy(self.document)
        del document["providers"]["grok"]
        connection = self.gateway._connection()
        try:
            connection.row_factory = sqlite3_module.Row
            connection.execute("BEGIN")
            _, _, observation = self.broker.application_selection_facts(connection,
                principal_id="macro", caller_host="vps", workload="site_interactive",
                pool="grok", model=POOL_MODELS["grok"][0], credential_ref="MACRO_APPLICATION_TOKEN",
                transport_accounts=frozenset({"account-a", "account-b"}),
                mode="grok", expected_recipe_digest=self.digests[("grok", POOL_MODELS["grok"][0])],
                document=document)
        finally:
            connection.close()
        self.assertEqual(observation["model_room"], {})
        self.assertEqual(observation["source"], "broker-ledger-room")
        self.assertEqual(observation["host"], "vps")
        self.assertEqual(observation["mode"], "grok")
        # The closed account owner itself refuses a grant whose pool has no
        # configured inventory, so the seam can never admit on an unknown room.
        del self.document["providers"]["grok"]
        self.save()
        with self.assertRaises(ApplicationSelectionRefused):
            self.select("grok")
        self.assert_no_effect()

    def test_inventory_or_grant_alone_is_never_offered_without_a_registered_route(self):
        # claude-native has a fresh grant and configured inventory but this
        # startup registered no route for it.
        pools = {pool: recipe for pool, recipe in self.native_recipes.items() if pool != "claude-native"}
        self.rebuild_gateway(application_native_recipes=tuple(
            {key: value for key, value in recipe.items() if key != "__digest__"}
            for recipe in pools.values()),
            application_native_accounts={pool: {"account-a", "account-b"} for pool in pools},
            application_native_selection={key: value for key, value in self.projections().items()
                                          if key[0] != "claude-native"})
        with self.assertRaises(ApplicationSelectionRefused):
            self.select("claude-native")
        self.assert_no_effect()

    def test_disabled_stale_ambiguous_or_mismatched_grants_refuse_before_lease(self):
        cases = {
            "disabled": ("bailian", {"enabled": False}),
            "stale": ("grok", {"expires_at": 900}),
            "ambiguous": ("minimax", {"__duplicate__": True}),
            "recipe_mismatch": ("glm", {"recipe_digest": "f" * 64}),
            "unavailable_model": ("codex-native", {"models": ["other-native"]}),
            "wrong_credential": ("ocfree", {"credential_ref": "OTHER_APPLICATION_TOKEN"}),
            "unknown_account": ("cursor", {"accounts": ["account-ghost"]}),
        }
        for label, (pool, changes) in cases.items():
            with self.subTest(case=label):
                duplicate = changes.pop("__duplicate__", False)
                for grant in self.document["application_grants"]:
                    if grant["pool"] == pool:
                        grant.update(changes)
                if duplicate:
                    clone = dict(self.grant_for(pool, POOL_MODELS[pool][0], grant_id="macro-app-clone"))
                    clone.update({key: value for key, value in changes.items() if key != "__duplicate__"})
                    self.document["application_grants"].append(clone)
                self.save()
                with self.assertRaises(ApplicationSelectionRefused):
                    self.select(pool)
                self.assert_no_effect()

    def test_projection_vocabulary_and_recipe_binding_refuse_wrong_source(self):
        from go_lease_gateway import ApplicationNativeSelection as Projection
        with self.assertRaises(LeaseGatewayError):
            Projection(pool="codex-native", model="fixture-codex", mode="glm-codex",
                       source_generation="1" * 64)
        with self.assertRaises(LeaseGatewayError):
            Projection(pool="go", model="fixture-model", mode="go", source_generation="1" * 64)
        # The projection vocabulary is closed per pool; an unpooled name refuses.
        with self.assertRaises(LeaseGatewayError):
            Projection(pool="claude", model="fixture-claude", mode="claude-native",
                       source_generation="1" * 64)
        # A source generation outside this recipe cannot bind at startup.
        with self.assertRaises(LeaseGatewayError):
            self.rebuild_gateway(application_native_selection={
                **self.projections(),
                ("codex-native", "fixture-codex"): Projection(
                    pool="codex-native", model="fixture-codex", mode="codex-native",
                    source_generation="2" * 64)})
        # A recipe with an unsupported transport kind is refused at startup.
        broken = copy.deepcopy(self.native_recipes["glm"])
        broken["transport_kind"] = "other_operation_v1"
        broken.pop("__digest__")
        with self.assertRaises(LeaseGatewayError):
            self.new_gateway(application_native_recipes=(broken,),
                             application_native_accounts={"glm": {"account-a"}},
                             application_native_selection={
                                 ("glm", broken["model"]): Projection(
                                     pool="glm", model=broken["model"], mode="glm",
                                     source_generation=broken["source_generation"])})

    def test_exact_service_pool_and_model_condition_is_preserved(self):
        with self.assertRaises(ApplicationSelectionRefused):
            self.select("go", payload=self.payload_for("bailian"))
        with self.assertRaises(ApplicationSelectionRefused):
            self.select("bailian", payload=self.payload_for("go"))
        self.assert_no_effect()

    def test_media_and_unoffered_capability_needs_refuse(self):
        media = [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "https://fixture.invalid/image"}}]}]
        for pool in ("go", "bailian", "codex-native"):
            with self.subTest(pool=pool):
                with self.assertRaises(ApplicationSelectionRefused):
                    self.select(pool, payload=self.payload_for(pool, messages=media))
        tools = [{"type": "function", "function": {"name": "inspect",
            "parameters": {"type": "object", "properties": {}}}}]
        with self.assertRaises(ApplicationSelectionRefused):
            self.select("codex-native", payload=self.payload_for("codex-native", tools=tools))
        self.assert_no_effect()

    def test_exhausted_room_refuses_and_shared_last_slot_stays_fair(self):
        self.document["providers"]["bailian"]["accounts"] = [
            {"name": "account-a", "per_account_cap": 0}, {"name": "account-b", "per_account_cap": 0}]
        self.save()
        with self.assertRaises(ApplicationSelectionRefused):
            self.select("bailian")
        self.assert_no_effect()
        self.document["providers"]["glm"]["accounts"] = [{"name": "account-a", "per_account_cap": 1}]
        self.document["application_grants"] = [
            grant for grant in self.document["application_grants"] if grant["pool"] != "glm"]
        self.document["application_grants"].append(self.grant_for("glm", "glm-5.3-flash", grant_id="macro-app-glm"))
        for grant in self.document["application_grants"]:
            if grant["pool"] == "glm":
                grant["accounts"] = ["account-a"]
        self.save()
        selected, binding = self.begin_selected("glm", turn="turn-glm")
        self.assertTrue(binding["ok"])
        self.assertEqual(binding["account"], "account-a")
        worker = self.broker.acquire("worker-root", "glm", host="vps", pid=0,
                                     model="glm-5.3-flash", wait=0)
        self.assertFalse(worker.ok)
        self.assertEqual(len([row for row in self.rows("leases")
                              if row["state"] in ("held", "rented")]), 1)

    def test_admin_view_lists_native_rows_with_ledger_room_and_redaction(self):
        view = self.gateway.application_pool_view(principal_id="macro", host="vps",
            workload="site_interactive", credential_ref="MACRO_APPLICATION_TOKEN",
            bound_pool="go", go_models=frozenset({"fixture-model"}),
            source={"source_generation": "a" * 64, "ingress_sha256": "c" * 64,
                    "gateway_sha256": "d" * 64})
        self.assertEqual(view["schema"], "mastermind.fabric_admin_pool_view.v1")
        self.assertEqual([row["pool"] for row in view["pools"]], list(pick._APPLICATION_POOL_ORDER))
        self.assertIs(view["execution_authorized"], False)
        self.assertIs(view["requires_fresh_admission"], True)
        self.assertEqual(view["stale_after"], view["observed_at"] + 5.0)
        rows = {row["pool"]: row for row in view["pools"]}
        for pool in NATIVE_POOLS:
            model_rows = rows[pool]["models"]
            self.assertEqual(len(model_rows), 1)
            row = model_rows[0]
            self.assertEqual(row["transport_state"], "qualified")
            self.assertEqual(row["protocol"], "harness")
            self.assertEqual(row["capabilities"],
                             {"text": True, "tools": False, "vision": False,
                              "upstream_streaming": False})
            # Native pools are not the bound service pool here: held away from
            # this service's execution with no inferred capacity observation.
            self.assertEqual(row["application_state"], "held")
            self.assertIn("service_pool_mismatch", row["blockers"])
            self.assertIsNone(row["ledger_room"])
            self.assertEqual(row["capacity_state"], "unobserved")
            self.assertNotIn("recipe_digest", json.dumps(row))
        bailian_row = rows["bailian"]["models"][0]
        self.assertEqual((bailian_row["transport_state"], bailian_row["protocol"]),
                         ("qualified", "responses"))
        self.assertIsNone(bailian_row["ledger_room"])
        bailian_route = self.gateway._application_route("bailian", POOL_MODELS["bailian"][0])[2]
        self.assertEqual(bailian_row["capabilities"],
                         {**bailian_route["capabilities"],
                          "upstream_streaming": bailian_route["streaming"]})
        self.assertIs(bailian_row["capabilities"]["tools"], True)
        self.assertIs(bailian_row["capabilities"]["vision"], False)
        self.assertIs(bailian_row["capabilities"]["upstream_streaming"], False)
        self.assertEqual(bailian_row["application_state"], "held")
        self.assertIn("service_pool_mismatch", bailian_row["blockers"])
        go_row = rows["go"]["models"][0]
        self.assertEqual(go_row["transport_state"], "qualified")
        # Only the bound service pool's own route reports its ledger room.
        self.assertIsInstance(go_row["ledger_room"], int)
        self.assertEqual(go_row["capacity_state"], "broker_ledger_only")
        rendered = json.dumps(view)
        self.assertNotIn("MACRO_APPLICATION_TOKEN", rendered)
        self.assertNotIn("account-a", rendered)
        self.assertNotIn(str(self.accounts), rendered)
        self.assertNotIn("recipe_digest", rendered)
        self.assert_no_effect()

    def test_admin_view_holds_unobserved_and_disabled_pools_without_inventing_room(self):
        self.document["providers"]["ocfree"]["enabled"] = False
        # The closed loader refuses a grant whose pool has no inventory entry,
        # so the unobserved case retires the grok grant with its inventory.
        del self.document["providers"]["grok"]
        self.document["application_grants"] = [
            grant for grant in self.document["application_grants"] if grant["pool"] != "grok"]
        self.save()
        view = self.gateway.application_pool_view(principal_id="macro", host="vps",
            workload="site_interactive", credential_ref="MACRO_APPLICATION_TOKEN",
            bound_pool="go", go_models=frozenset({"fixture-model"}),
            source={"source_generation": "a" * 64, "ingress_sha256": "c" * 64,
                    "gateway_sha256": "d" * 64})
        rows = {row["pool"]: row for row in view["pools"]}
        self.assertEqual(rows["ocfree"]["models"][0]["application_state"], "held")
        self.assertIn("pool_disabled", rows["ocfree"]["blockers"])
        self.assertIsNone(rows["grok"]["models"][0]["ledger_room"])
        self.assertEqual(rows["grok"]["models"][0]["capacity_state"], "unobserved")
        self.assertIn("account_inventory_unobserved", rows["grok"]["blockers"])
        self.assertIsNone(rows["grok"]["models"][0]["ledger_room"])

    def test_purpose_digest_and_profile_digest_bind_the_record(self):
        expected = self.purpose_for("cursor")
        selected = self.select("cursor")
        self.assertEqual(selected["purpose"], expected)
        self.assertEqual(selected["purpose_digest"],
                         lease_broker._application_selection_purpose(expected)[1])
        self.assertEqual(selected["profile_digest"],
                         hashlib.sha256(lease_broker._application_json(selected["profile"]).encode()).hexdigest())
        self.assertEqual(selected["fresh_s"], 5.0)
        self.assert_no_effect()

    def test_selection_quality_is_read_strict_from_the_owner_ledger(self):
        # A truncated ledger row is not an empty quality sample: the strict
        # reader refuses, and the whole selection refuses before any lease.
        pool_ledger.create_ledger_file(self.ledger_path)
        self.ledger_path.write_text('{"pool":"go"}')
        with self.assertRaises(ApplicationSelectionRefused):
            self.select("cursor")
        pool_ledger.create_ledger_file(self.ledger_path)
        self.assertEqual(self.select("cursor")["identity"]["pool"], "cursor")
        self.assert_no_effect()


if __name__ == "__main__":
    unittest.main()
