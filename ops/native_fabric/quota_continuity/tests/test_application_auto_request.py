"""Explicit-null application intent through the real picker, A and SQLite.

This is the preparatory fixed-pool AUTO owner contract. Public B enrollment
remains fixed until its separately qualified trusted route-scope join.
All grants, provider receipts and native qualification evidence are synthetic.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import sqlite3
import unittest
from unittest.mock import patch

from test_application_registered_pool_selection import (
    RegisteredPoolFixture, POOL_MODELS, NATIVE_POOLS, _policy_document)
from test_application_turn_admission import offline_acquire, offline_release
import lease_broker
import pick
from go_lease_gateway import ApplicationSelectionRefused, LeaseGatewayError


def setUpModule():
    offline_acquire()


def tearDownModule():
    offline_release()


def digest(payload):
    raw = json.dumps({"path": "/v1/chat/completions", "payload": payload},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


class AutoFixture(RegisteredPoolFixture):
    def auto_payload(self, pool="go", **changes):
        return self.payload_for(pool, model=None, **changes)

    def begin_auto(self, pool="go", *, turn="auto-turn", payload=None, selected=None):
        payload = self.auto_payload(pool) if payload is None else payload
        purpose = self.purpose_for(pool)
        if selected is None:
            selected = self.select(pool, payload=payload, purpose=purpose, turn=turn)
        model = selected["identity"]["model"]
        recipe_digest = None if pool == "go" else self.gateway.application_recipe(pool, model)[1]
        binding = self.gateway.begin_application(
            {"workload": "site_interactive", "turn_id": turn, "pool": pool, "model": model},
            principal_id="macro", host="vps", expected_credential_ref="MACRO_APPLICATION_TOKEN",
            expected_recipe_digest=recipe_digest, expected_selection=selected,
            selection_purpose=purpose, selection_payload=payload)
        return selected, binding

    def commitment(self, binding, payload):
        pool = binding["pool"]
        concrete = copy.deepcopy(payload)
        concrete["model"] = binding["model"]
        if pool in NATIVE_POOLS:
            recipe, recipe_digest = self.gateway.application_recipe(pool, binding["model"])
            raw, logical, _ = lease_broker._application_native_payload(recipe, concrete)
            fields = ("physical_host", "source_generation", "support_generation",
                "binary_sha256", "compiler_sha256", "profile_sha256", "policy_sha256",
                "result_parser_sha256", "argv_semantics_sha256")
            return {**{key: recipe[key] for key in fields},
                "recipe_digest": recipe_digest, "logical_payload_digest": logical,
                "input_sha256": hashlib.sha256(raw).hexdigest(),
                "command_sha256": hashlib.sha256(b"synthetic-qualified-command").hexdigest()}
        if pool == "bailian":
            return {"recipe_digest": self.gateway.application_recipe(pool, binding["model"])[1],
                "logical_payload_digest": hashlib.sha256(lease_broker._application_json(concrete).encode()).hexdigest(),
                "wire_body_digest": hashlib.sha256(b"synthetic-H-wire").hexdigest()}
        return None

    def prepare_auto(self, binding, *, payload=None, request_id="auto-step", commitment=None):
        payload = self.auto_payload(binding["pool"]) if payload is None else payload
        if commitment is None:
            commitment = self.commitment(binding, payload)
        return self.gateway.prepare_application(binding["token"], principal_id="macro", host="vps",
            turn_id=binding["turn_id"], request_id=request_id, path="/v1/chat/completions",
            payload=payload, expected_pool=binding["pool"], transport_commitment=commitment)

    def complete_auto(self, prepared):
        if prepared["pool"] in NATIVE_POOLS:
            receipt = self.native_receipt(prepared)
            receipt["served_model"] = prepared["model"]
        else:
            receipt = self.receipt(prepared)
            if prepared["pool"] == "bailian":
                receipt.update(terminal_kind="http_responses_v1", served_model=prepared["model"],
                    delivery_digest=None, **{key: prepared[key] for key in
                        ("recipe_digest", "logical_payload_digest", "wire_body_digest")})
        return self.broker.complete_application_request(
            dispatch_id=prepared["dispatch_id"], terminal_receipt=receipt)

    def recover_auto(self, pool="go", *, turn="auto-turn", request_id="auto-step", payload=None,
                     expected_recipe_digest=None):
        payload = self.auto_payload(pool) if payload is None else payload
        return self.gateway.recover_application(
            {"workload": "site_interactive", "turn_id": turn, "pool": pool, "model": payload["model"]},
            principal_id="macro", host="vps", request_id=request_id,
            path="/v1/chat/completions", payload=payload,
            expected_recipe_digest=expected_recipe_digest, include_turn=True)

    def add_go_models(self, models=("fixture-model", "other-model"), default="other-model"):
        grant = next(g for g in self.document["application_grants"] if g["pool"] == "go")
        grant["models"] = list(models)
        self.save()
        policy = _policy_document()
        policy["pools"]["go"]["worker_models"] = list(models)
        if default is None:
            policy["pools"]["go"].pop("default_model", None)
        else:
            policy["pools"]["go"]["default_model"] = default
        self.policy_path.write_text(json.dumps(policy))

    def sql(self, statement, parameters=()):
        with sqlite3.connect(self.directory / "leases.sqlite") as conn:
            return conn.execute(statement, parameters).fetchall()


class AutoSelectionTests(AutoFixture):
    def test_each_registered_pool_keeps_concrete_admission_and_original_null_intent(self):
        for pool in POOL_MODELS:
            with self.subTest(pool=pool):
                payload = self.auto_payload(pool)
                original = copy.deepcopy(payload)
                selected, binding = self.begin_auto(pool, turn="auto-" + pool, payload=payload)
                self.assertIsNone(selected["identity"]["task"]["requested_model"])
                self.assertEqual((binding["pool"], binding["model"]), (pool, POOL_MODELS[pool][0]))
                turn = next(t for t in self.rows("application_turns") if t["turn_id"] == "auto-" + pool)
                self.assertIsNone(lease_broker._application_requested_model(turn))
                prepared = self.prepare_auto(binding, payload=payload)
                self.assertTrue(prepared["dispatch_permitted"])
                concrete = {**payload, "model": binding["model"]}
                self.assertEqual(prepared["request_digest"], digest(payload))
                self.assertEqual(prepared["routed_request_digest"], digest(concrete))
                self.assertNotEqual(prepared["request_digest"], prepared["routed_request_digest"])
                self.assertEqual(json.loads(prepared["payload_bytes"]), concrete)
                self.assertEqual(payload, original)
                row = next(r for r in self.rows("application_requests") if r["turn_id"] == binding["turn_id"])
                self.assertEqual(row["routed_request_digest"], digest(concrete))
                self.complete_auto(prepared)
                closed = self.broker.close_application_turn(principal_id="macro", turn_id=binding["turn_id"])
                self.assertEqual(closed["disposition"], "closed")
                self.assertEqual(next(r for r in self.rows("leases") if r["id"] == binding["lease_id"])["state"], "released")

    def test_multiple_models_use_incumbent_default_and_keep_separate_shared_room(self):
        self.add_go_models()
        observed = {}
        choose = pick.select_application
        def capture(task, **kwargs):
            observed.update(kwargs)
            return choose(task, **kwargs)
        with patch.object(pick, "select_application", side_effect=capture) as picker:
            selected, binding = self.begin_auto()
        self.assertEqual(picker.call_count, 1)
        self.assertEqual(binding["model"], "other-model")
        self.assertEqual(observed["expected_identity"], {"pool": "go"})
        room = observed["observations"]["go"]["model_room"]
        self.assertEqual(set(room), {"fixture-model", "other-model"})
        self.assertEqual(room["fixture-model"], room["other-model"])
        recipes = observed["catalogue"]["pools"]["go"]["recipes"]
        self.assertEqual({r["order_rank"] for r in recipes}, {0})
        self.assertEqual(selected["profile"], self.gateway._application_route("go", "other-model")[2])
        self.assertEqual(len(self.rows("leases")), 1)

    def test_unordered_alternatives_refuse_and_one_eligible_model_does_not_need_a_fake_rank(self):
        self.add_go_models(default=None)
        with self.assertRaises(ApplicationSelectionRefused):
            self.select("go", payload=self.auto_payload())
        self.assert_no_effect()
        self.add_go_models(models=("other-model",), default=None)
        selected, binding = self.begin_auto()
        self.assertEqual(binding["model"], "other-model")
        self.assertIsNone(selected["identity"]["task"]["requested_model"])

    def test_unobserved_model_room_is_not_converted_to_zero_or_added_to_other_room(self):
        self.add_go_models(default="fixture-model")
        facts = self.broker.application_selection_facts
        choose = pick.select_application
        captured = {}
        def unknown(*args, **kwargs):
            grant, grant_digest, observation = facts(*args, **kwargs)
            if kwargs["model"] == "other-model":
                observation["model_room"] = {}
            return grant, grant_digest, observation
        def capture(task, **kwargs):
            captured.update(kwargs)
            return choose(task, **kwargs)
        with patch.object(self.broker, "application_selection_facts", side_effect=unknown), \
                patch.object(pick, "select_application", side_effect=capture):
            self.begin_auto()
        self.assertEqual(set(captured["observations"]["go"]["model_room"]), {"fixture-model"})

    def test_missing_empty_and_alias_models_do_not_acquire_auto_meaning(self):
        for value in ("", "auto", 0, False, []):
            with self.subTest(value=value):
                with self.assertRaises(ApplicationSelectionRefused):
                    self.select("go", payload=self.payload_for("go", model=value))
                self.assert_no_effect()
        missing = self.auto_payload()
        del missing["model"]
        with self.assertRaises(ApplicationSelectionRefused):
            self.gateway.select_application(
                {"workload": "site_interactive", "turn_id": "auto-turn", "pool": "go", "model": None},
                principal_id="macro", host="vps", credential_ref="MACRO_APPLICATION_TOKEN",
                purpose=self.purpose_for("go"), payload=missing)
        self.assert_no_effect()

    def test_null_does_not_widen_the_fixed_pool_or_native_request_grammar(self):
        for payload in (self.auto_payload("codex-native", temperature=0.5),
                self.auto_payload("codex-native", messages=[{"role": "user", "content": "one"},
                    {"role": "assistant", "content": "two"}, {"role": "user", "content": "three"}])):
            with self.assertRaises(ApplicationSelectionRefused):
                self.select("codex-native", payload=payload)
            self.assert_no_effect()
        self.document["application_grants"] = [g for g in self.document["application_grants"] if g["pool"] != "go"]
        self.save()
        with self.assertRaises(ApplicationSelectionRefused):
            self.select("go", payload=self.auto_payload())
        self.assert_no_effect()

    def test_selected_grant_change_refuses_before_allocating_an_auto_turn(self):
        payload = self.auto_payload()
        selected = self.select("go", payload=payload)
        next(g for g in self.document["application_grants"] if g["pool"] == "go")["enabled"] = False
        self.save()
        with self.assertRaises(ApplicationSelectionRefused):
            self.begin_auto(payload=payload, selected=selected)
        self.assert_no_effect()


class AutoRequestCustodyTests(AutoFixture):
    def test_pending_and_terminal_recovery_use_original_bytes_without_current_routes(self):
        payload = self.auto_payload("codex-native")
        _, binding = self.begin_auto("codex-native")
        prepared = self.prepare_auto(binding)
        for phase in ("pending", "terminal"):
            if phase == "terminal":
                self.complete_auto(prepared)
            with patch.object(self.gateway, "_application_route", side_effect=AssertionError("no catalogue")), \
                    patch.object(self.gateway, "select_application", side_effect=AssertionError("no picker")), \
                    patch.object(self.broker, "_application_grant", side_effect=AssertionError("no fresh grant")):
                recovered = self.recover_auto("codex-native", payload=payload)
            self.assertEqual(recovered["kind"], "request_present")
            self.assertEqual(recovered["request"]["disposition"], phase)
            self.assertFalse(recovered["request"]["dispatch_permitted"])
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.rows("application_requests")), 1)

    def test_native_invocation_and_dispatch_claims_stay_concrete(self):
        _, binding = self.begin_auto("codex-native")
        prepared = self.prepare_auto(binding)
        invocation = prepared["native_invocation"]
        self.assertEqual(invocation["model"], binding["model"])
        self.assertEqual(invocation["request_digest"], digest(self.auto_payload("codex-native")))
        self.assertEqual(invocation["logical_payload_digest"], prepared["logical_payload_digest"])
        claims = self.gateway.authorize_native_dispatch(prepared["native_dispatch_capability"],
            principal_id="macro", caller_host="vps", turn_id="auto-turn", request_id="auto-step",
            invocation=invocation)
        self.assertEqual(claims["model"], binding["model"])
        self.assertTrue(binding["token"].startswith("app3."))
        self.assertTrue(prepared["native_dispatch_capability"].startswith("appd1."))

    def test_native_non_model_input_change_refuses_before_request_intent(self):
        payload = self.auto_payload("codex-native")
        _, binding = self.begin_auto("codex-native")
        concrete = {**payload, "model": binding["model"]}
        changed = copy.deepcopy(concrete)
        changed["messages"][-1]["content"] += " changed"
        with self.assertRaises(lease_broker.ApplicationAdmissionError):
            self.broker.prepare_application_request(principal_id="macro", turn_id="auto-turn",
                request_id="auto-step", request_digest=digest(payload),
                original_payload=payload, native_payload=changed,
                transport_commitment=self.commitment(binding, changed))
        self.assertEqual(self.rows("application_requests"), [])

    def test_same_request_replay_cannot_obtain_a_second_permit(self):
        _, binding = self.begin_auto()
        first = self.prepare_auto(binding)
        again = self.prepare_auto(binding)
        self.assertTrue(first["dispatch_permitted"])
        self.assertFalse(again["dispatch_permitted"])
        self.assertEqual(first["dispatch_id"], again["dispatch_id"])
        changed = self.auto_payload(messages=[{"role": "user", "content": "different original"}])
        with self.assertRaises(LeaseGatewayError):
            self.prepare_auto(binding, payload=changed)
        self.assertEqual(len(self.rows("application_requests")), 1)

    def test_fixed_and_auto_request_modes_cannot_be_substituted(self):
        _, fixed = self.begin_selected("go", turn="fixed-turn")
        with self.assertRaises(LeaseGatewayError):
            self.gateway.recover_application(
                {"workload": "site_interactive", "turn_id": "fixed-turn", "pool": "go", "model": None},
                principal_id="macro", host="vps", request_id="auto-step",
                path="/v1/chat/completions", payload=self.auto_payload(), include_turn=True)
        _, automatic = self.begin_auto()
        with self.assertRaises(LeaseGatewayError):
            self.prepare_auto(automatic, payload=self.payload_for("go"))
        with self.assertRaises(LeaseGatewayError):
            self.recover_auto(payload=self.payload_for("go"))
        self.assertEqual(self.rows("application_requests"), [])
        prepared = self.prepare(fixed)
        self.assertNotIn("routed_request_digest", prepared)
        self.assertIsNone(self.rows("application_requests")[0]["routed_request_digest"])

    def test_turn_without_request_and_new_step_keep_the_frozen_model(self):
        payload = self.auto_payload()
        selected, binding = self.begin_auto()
        first = self.recover_auto()
        self.assertEqual(first["kind"], "turn_present_new_step")
        prepared = self.prepare_auto(binding)
        self.complete_auto(prepared)
        self.add_go_models(default="other-model")
        with patch.object(self.gateway, "select_application", side_effect=AssertionError("must not reselect")):
            recovered = self.recover_auto(request_id="step-2")
            self.assertEqual(recovered["kind"], "turn_present_new_step")
            self.assertEqual(recovered["turn"]["model"], "fixture-model")
            with self.assertRaises(ApplicationSelectionRefused):
                self.begin_auto(payload=payload, selected=selected)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.rows("application_requests")), 1)

    def test_lost_admission_ack_recovers_original_and_resumes_without_another_pick(self):
        selected = self.select("go", payload=self.auto_payload())
        admit = self.broker.begin_application_turn
        def lost(**kwargs):
            admit(**kwargs)
            raise OSError("synthetic lost begin acknowledgment")
        with patch.object(self.broker, "begin_application_turn", side_effect=lost):
            with self.assertRaises(LeaseGatewayError):
                self.begin_auto(selected=selected)
        with patch.object(self.gateway, "select_application", side_effect=AssertionError("no second selection")):
            recovered = self.recover_auto()
            self.assertEqual(recovered["kind"], "turn_present_new_step")
            _, resumed = self.begin_auto(selected=json.loads(recovered["turn"]["selection_json"]))
            self.assertTrue(self.prepare_auto(resumed)["dispatch_permitted"])
        self.assertEqual(len(self.rows("leases")), 1)

    def test_concurrent_same_turn_attempts_share_one_lease_and_one_request(self):
        selected = self.select("go", payload=self.auto_payload())
        def attempt():
            _, binding = self.begin_auto(selected=selected)
            if "token" not in binding:
                return False
            return self.prepare_auto(binding)["dispatch_permitted"]
        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes = list(workers.map(lambda _: attempt(), range(2)))
        self.assertEqual(sum(outcomes), 1)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.rows("application_requests")), 1)

    def test_insert_suppression_never_returns_an_unretained_dispatch_permit(self):
        _, binding = self.begin_auto()
        self.sql("CREATE TRIGGER synthetic_ignore BEFORE INSERT ON application_requests BEGIN SELECT RAISE(IGNORE); END")
        with self.assertRaises(LeaseGatewayError):
            self.prepare_auto(binding)
        self.assertEqual(self.rows("application_requests"), [])

    def test_sql_update_delete_replace_and_terminal_rewrite_preserve_auto_custody(self):
        _, binding = self.begin_auto()
        prepared = self.prepare_auto(binding)
        before = self.rows("application_requests")
        self.sql("UPDATE application_requests SET routed_request_digest=?", ("f" * 64,))
        self.sql("UPDATE application_requests SET request_digest=?", ("e" * 64,))
        self.sql("DELETE FROM application_requests")
        self.assertEqual(self.rows("application_requests"), before)
        for table in ("application_requests", "application_turns", "leases"):
            with self.subTest(table=table):
                row = self.rows(table)[0]
                columns = list(row)
                statement = "INSERT OR REPLACE INTO " + table + " (" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")"
                with sqlite3.connect(self.directory / "leases.sqlite") as conn:
                    conn.execute("PRAGMA recursive_triggers=OFF")
                    with self.assertRaises(sqlite3.IntegrityError):
                        conn.execute(statement, [row[key] for key in columns])
        self.complete_auto(prepared)
        terminal = self.rows("application_requests")
        self.sql("UPDATE application_requests SET state='pending',terminal_receipt=NULL")
        self.assertEqual(self.rows("application_requests"), terminal)
        self.assertEqual(self.broker.close_application_turn(principal_id="macro", turn_id="auto-turn")["disposition"], "closed")

    def test_old_style_insert_without_route_commitment_and_bad_request_binding_refuse(self):
        _, binding = self.begin_auto()
        payload = self.auto_payload()
        with self.assertRaises(sqlite3.IntegrityError):
            self.sql("INSERT INTO application_requests (principal_id,turn_id,request_id,request_digest,dispatch_id,state,created_at) VALUES (?,?,?,?,?,'pending',?)",
                ("macro", "auto-turn", "auto-step", digest(payload), "old-dispatch", self.clock[0]))
        self.assertEqual(self.rows("application_requests"), [])
        with self.assertRaises(lease_broker.ApplicationAdmissionError):
            self.broker.prepare_application_request(principal_id="macro", turn_id="auto-turn",
                request_id="auto-step", request_digest="a" * 64, original_payload=payload)
        self.assertEqual(self.rows("application_requests"), [])

    def test_old_close_without_actual_release_is_not_reported_closed_for_auto_go(self):
        self.begin_auto()
        self.sql("UPDATE application_turns SET state='closed'")
        recovered = self.recover_auto()
        self.assertEqual(recovered["turn"]["disposition"], "effect_unknown")
        self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})

    def test_damaged_frozen_selection_and_missing_routed_commitment_are_not_terminal_proof(self):
        _, binding = self.begin_auto()
        prepared = self.prepare_auto(binding)
        self.complete_auto(prepared)
        row, turn = self.rows("application_requests")[0], self.rows("application_turns")[0]
        self.assertIsNotNone(lease_broker._application_stored_terminal(row, turn))
        for value in (None, "", "bad", row["request_digest"]):
            with self.subTest(value=value):
                self.assertIsNone(lease_broker._application_stored_terminal(
                    {**row, "routed_request_digest": value}, turn))
        broken = json.loads(turn["selection_json"])
        del broken["identity"]["task"]["requested_model"]
        raw = lease_broker._application_json(broken)
        forged = {**turn, "selection_json": raw, "selection_digest": hashlib.sha256(raw.encode()).hexdigest()}
        with self.assertRaises(lease_broker.ApplicationAdmissionError):
            lease_broker._application_requested_model(forged)
        self.assertIsNone(lease_broker._application_stored_terminal(row, forged))

    def test_auto_token_cannot_widen_tools_history_or_media_before_first_request(self):
        _, binding = self.begin_auto()
        declaration = [{"type": "function", "function": {"name": "read",
            "parameters": {"type": "object"}}}]
        payloads = [
            self.auto_payload(tools=declaration),
            self.auto_payload(messages=[{"role": "user", "content": "one"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "read-1", "type": "function", "function": {"name": "read", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "read-1", "content": "result"}]),
            self.auto_payload(messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "https://fixture.invalid/image"}}]}]),
        ]
        for i, payload in enumerate(payloads):
            with self.subTest(kind=i):
                with self.assertRaises(LeaseGatewayError):
                    self.prepare_auto(binding, payload=payload, request_id="wide-" + str(i))
                self.assertEqual(self.rows("application_requests"), [])
        self.assertTrue(self.prepare_auto(binding)["dispatch_permitted"])

    def test_auto_new_step_cannot_widen_the_frozen_turn_needs(self):
        _, binding = self.begin_auto()
        prepared = self.prepare_auto(binding)
        self.complete_auto(prepared)
        before = self.rows("application_requests")
        with self.assertRaises(LeaseGatewayError):
            self.prepare_auto(binding, request_id="step-2", payload=self.auto_payload(tools=[
                {"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}]))
        self.assertEqual(self.rows("application_requests"), before)

    def test_auto_request_can_narrow_original_tool_needs_without_reading_current_policy(self):
        payload = self.auto_payload(tools=[
            {"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}])
        _, binding = self.begin_auto(payload=payload)
        with patch.object(pick, "read_application_policy", side_effect=AssertionError("no current selection")):
            self.assertTrue(self.prepare_auto(binding)["dispatch_permitted"])

    def test_repeated_terminal_completion_requires_retained_routed_proof(self):
        _, binding = self.begin_auto()
        prepared = self.prepare_auto(binding)
        self.complete_auto(prepared)
        receipt = self.receipt(prepared)
        # Deliberately damaged retained fixture state: prove repeated completion
        # uses the same original proof as recovery, without weakening live guards.
        self.sql("DROP TRIGGER application_auto_request_binding_v1")
        self.sql("UPDATE application_requests SET routed_request_digest=NULL")
        before = self.rows("application_requests")
        with self.assertRaises(lease_broker.ApplicationAdmissionError):
            self.broker.complete_application_request(dispatch_id=prepared["dispatch_id"], terminal_receipt=receipt)
        self.assertEqual(self.rows("application_requests"), before)
        self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})

    def test_routed_size_is_bounded_after_the_concrete_model_substitution(self):
        _, binding = self.begin_auto()
        turn = self.rows("application_turns")[0]
        empty = {"model": None, "messages": [{"role": "user", "content": ""}]}
        overhead = len(lease_broker._application_json({"path": "/v1/chat/completions", "payload": empty}).encode())
        payload = copy.deepcopy(empty)
        payload["messages"][0]["content"] = "x" * (1024 * 1024 - overhead)
        with self.assertRaises(LeaseGatewayError):
            self.prepare_auto(binding, payload=payload)
        self.assertEqual(self.rows("application_requests"), [])


class AutoSchemaCompatibilityTests(AutoFixture):
    def predecessor_schema(self):
        # Remove precisely the additive AUTO/exact objects. All incumbent native,
        # selection, HTTP and worker schema/trigger definitions stay untouched.
        with sqlite3.connect(self.directory / "leases.sqlite") as conn:
            names = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND "
                "(name LIKE 'application_auto_%' OR name LIKE 'application_exact_%')")]
            self.assertEqual(len(names), 12)
            for name in names:
                conn.execute("DROP TRIGGER " + name)
            conn.execute("ALTER TABLE application_requests DROP COLUMN routed_request_digest")
        return names

    def test_current_registered_predecessor_migrates_without_rewriting_release_or_fixed_rows(self):
        _, binding = self.begin_selected("go")
        prepared = self.prepare(binding)
        self.broker.complete_application_request(dispatch_id=prepared["dispatch_id"],
            terminal_receipt=self.receipt(prepared))
        before_turns, before_leases = self.rows("application_turns"), self.rows("leases")
        before_requests = self.rows("application_requests")
        release = self.sql("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='application_lease_release_v1'")
        self.predecessor_schema()
        migrated = self.new_broker()
        self.assertEqual(self.sql("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='application_lease_release_v1'"), release)
        self.assertEqual(self.rows("application_turns"), before_turns)
        self.assertEqual(self.rows("leases"), before_leases)
        self.assertEqual(self.rows("application_requests"), before_requests)
        recovered = migrated.recover_application_request(principal_id="macro", turn_id=binding["turn_id"],
            request_id="step-1", request_digest=prepared["request_digest"])
        self.assertEqual(recovered["disposition"], "terminal")

    def test_unrecognized_release_trigger_rolls_back_new_column_and_auto_guards(self):
        self.predecessor_schema()
        self.sql("DROP TRIGGER application_lease_release_v1")
        self.sql("CREATE TRIGGER application_lease_release_v1 BEFORE UPDATE ON leases BEGIN SELECT RAISE(IGNORE); END")
        with self.assertRaises(lease_broker.ApplicationAdmissionError):
            self.new_broker()
        columns = {r[1] for r in self.sql("PRAGMA table_info(application_requests)")}
        self.assertNotIn("routed_request_digest", columns)
        self.assertEqual(self.sql("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'application_auto_%'"), [])



class ExactScopedFixture(AutoFixture):
    def begin_exact(self, pool="go", *, turn="exact-turn", payload=None, pools=None):
        payload = self.payload_for(pool) if payload is None else payload
        scope = {"schema": "mastermind.application_route_scope.v1", "pools": sorted(pools or [pool])}
        selected = self.gateway.select_application(
            {"workload": "site_interactive", "turn_id": turn, "pool": "go", "model": payload["model"]},
            principal_id="macro", host="vps", credential_ref="MACRO_APPLICATION_TOKEN",
            purpose=self.purpose_for(pool), payload=payload, route_scope=scope,
            transport_candidates=self.gateway.application_registered_routes())
        target = selected["identity"]
        recipe = None if target["pool"] == "go" else self.gateway.application_recipe(target["pool"], target["model"])[1]
        binding = self.gateway.begin_application(
            {"workload": "site_interactive", "turn_id": turn, "pool": target["pool"], "model": target["model"]},
            principal_id="macro", host="vps", expected_credential_ref="MACRO_APPLICATION_TOKEN",
            expected_recipe_digest=recipe, expected_selection=selected,
            selection_purpose=self.purpose_for(pool), selection_payload=payload, selection_route_scope=scope)
        return selected, binding


class ExactScopedCustodyTests(ExactScopedFixture):
    def test_every_registered_pool_keeps_concrete_original_and_null_routed_digest(self):
        for pool, (model, _, _) in POOL_MODELS.items():
            with self.subTest(pool=pool):
                payload = self.payload_for(pool)
                selected, binding = self.begin_exact(pool, turn="exact-" + pool)
                self.assertEqual(selected["schema"], "mastermind.application_turn_selection.v3")
                self.assertEqual(selected["identity"]["task"]["requested_model"], model)
                prepared = self.prepare_auto(binding, payload=payload)
                self.assertEqual(json.loads(prepared["payload_bytes"]), payload)
                self.assertEqual(prepared["request_digest"], digest(payload))
                self.assertIsNone(prepared.get("routed_request_digest"))
                self.assertIsNone(self.rows("application_requests")[-1]["routed_request_digest"])
                self.complete_auto(prepared)
                self.assertEqual(self.broker.close_application_turn(
                    principal_id="macro", turn_id=binding["turn_id"])["disposition"], "closed")

    def test_one_picker_can_choose_exact_model_in_either_permitted_registered_pool(self):
        shared = POOL_MODELS["codex-native"][0]
        recipe = self.native_recipes["claude-native"]
        recipe["model"] = shared
        _, digest_value = lease_broker._application_native_recipe(
            {key: value for key, value in recipe.items() if key != "__digest__"},
            pool="claude-native", model=shared)
        recipe["__digest__"] = digest_value
        self.document["application_grants"] = [
            grant for grant in self.document["application_grants"] if grant["pool"] != "claude-native"]
        self.document["application_grants"].append(self.grant_for("claude-native", shared))
        self.save()
        self.rebuild_gateway()
        payload = self.payload_for("codex-native")
        with patch.object(pick, "select_application", wraps=pick.select_application) as selector:
            selected, binding = self.begin_exact("codex-native", payload=payload,
                pools=["codex-native", "claude-native"])
        self.assertEqual(selector.call_count, 1)
        self.assertEqual(set(selector.call_args.kwargs["catalogue"]["pools"]), {"codex-native", "claude-native"})
        self.assertEqual(selector.call_args.kwargs["expected_identity"], {"model": shared})
        self.assertEqual(binding["model"], shared)
        self.assertNotEqual(binding["pool"], "go")
        self.assertEqual(len(self.rows("leases")), 1)

    def test_no_matching_model_or_grant_does_not_allocate_or_substitute(self):
        for model in ("AUTO", "auto", "unknown-model", "Qwen3.8-flash"):
            with self.subTest(model=model), self.assertRaises(ApplicationSelectionRefused):
                self.begin_exact("bailian", payload=self.payload_for("bailian", model=model),
                    pools=["go", "bailian", "codex-native"])
        self.document["application_grants"] = []
        self.save()
        with self.assertRaises(ApplicationSelectionRefused):
            self.begin_exact("bailian", pools=["go", "bailian"])
        self.assertEqual(self.rows("leases"), [])

    def test_closed_v3_cannot_be_null_mismatched_or_relabelled_v2(self):
        selected, _ = self.begin_exact()
        for requested in (None, "", False, "other-model"):
            altered = copy.deepcopy(selected)
            altered["identity"]["task"]["requested_model"] = requested
            with self.subTest(requested=requested), self.assertRaises(lease_broker.ApplicationSelectionError):
                lease_broker._application_record_scope(altered)
        altered = dict(selected, schema="mastermind.application_turn_selection.v2")
        with self.assertRaises(lease_broker.ApplicationSelectionError):
            lease_broker._application_record_scope(altered)

    def test_original_recovery_ignores_removed_routes_but_checks_exact_body_and_recipe(self):
        payload = self.payload_for("bailian")
        _, binding = self.begin_exact("bailian", payload=payload, pools=["go", "bailian"])
        prepared = self.prepare_auto(binding, payload=payload)
        self.complete_auto(prepared)
        self.document["application_grants"] = []
        self.save()
        self.rebuild_gateway(application_http_recipes=(), application_http_accounts=())
        original = self.recover_auto(payload=payload, turn=binding["turn_id"])
        self.assertEqual(original["request"]["disposition"], "terminal")
        for changed in (dict(payload, model=None), dict(payload, max_tokens=127)):
            with self.subTest(changed=changed), self.assertRaises(LeaseGatewayError):
                self.recover_auto(payload=changed, turn=binding["turn_id"])
        with self.assertRaises(LeaseGatewayError):
            self.recover_auto(payload=payload, turn=binding["turn_id"], expected_recipe_digest="a" * 64)
        self.assertEqual(len(self.rows("application_requests")), 1)

    def test_direct_token_cannot_skip_original_body_or_widen_frozen_needs(self):
        _, binding = self.begin_exact()
        payload = self.payload_for("go")
        with self.assertRaises(lease_broker.ApplicationAdmissionError):
            self.broker.prepare_application_request(principal_id="macro", turn_id="exact-turn",
                request_id="missing-original", request_digest=digest(payload))
        for changes in (
            {"tools": [{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}]},
            {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "fixture"}}]}]},
        ):
            with self.assertRaises(LeaseGatewayError):
                self.prepare_auto(binding, payload=dict(payload, **changes))
        self.assertEqual(self.rows("application_requests"), [])
        prepared = self.prepare_auto(binding, payload=payload)
        self.complete_auto(prepared)
        with self.assertRaises(LeaseGatewayError):
            self.prepare_auto(binding, request_id="wide-step", payload=dict(payload, **changes))
        self.assertEqual(len(self.rows("application_requests")), 1)

    def test_sql_custody_guards_cover_null_digest_exact_go_and_terminal_rewrite(self):
        _, binding = self.begin_exact()
        prepared = self.prepare_auto(binding, payload=self.payload_for("go"))
        before = self.rows("application_requests")
        for statement in ("UPDATE application_requests SET request_digest='" + "e" * 64 + "'",
                          "UPDATE application_requests SET principal_id='other'",
                          "UPDATE application_requests SET logical_payload_digest='" + "f" * 64 + "'",
                          "UPDATE application_requests SET routed_request_digest='" + "f" * 64 + "'",
                          "DELETE FROM application_requests"):
            self.sql(statement)
            self.assertEqual(self.rows("application_requests"), before)
        for table in ("application_requests", "application_turns", "leases"):
            row = self.rows(table)[0]
            columns = list(row)
            statement = "INSERT OR REPLACE INTO " + table + " (" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")"
            with sqlite3.connect(self.directory / "leases.sqlite") as conn:
                conn.execute("PRAGMA recursive_triggers=OFF")
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(statement, [row[key] for key in columns])
        self.sql("UPDATE leases SET state='released'")
        self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})
        self.complete_auto(prepared)
        terminal = self.rows("application_requests")
        self.sql("UPDATE application_requests SET state='pending',terminal_receipt=NULL")
        self.assertEqual(self.rows("application_requests"), terminal)
        self.assertEqual(self.broker.close_application_turn(principal_id="macro", turn_id="exact-turn")["disposition"], "closed")

    def test_old_closed_row_without_actual_release_is_unknown(self):
        self.begin_exact()
        self.sql("UPDATE application_turns SET state='closed'")
        recovered = self.recover_auto(payload=self.payload_for("go"), turn="exact-turn")
        self.assertEqual(recovered["turn"]["disposition"], "effect_unknown")
        self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})

    def test_zero_step_close_works_and_damaged_requested_model_cannot_release(self):
        self.begin_exact(turn="empty")
        self.assertEqual(self.broker.close_application_turn(principal_id="macro", turn_id="empty")["disposition"], "closed")
        self.begin_exact()
        turn = next(row for row in self.rows("application_turns") if row["turn_id"] == "exact-turn")
        broken = json.loads(turn["selection_json"])
        del broken["identity"]["task"]["requested_model"]
        raw = lease_broker._application_json(broken)
        self.sql("DROP TRIGGER application_selection_binding_v1")
        self.sql("UPDATE application_turns SET selection_json=?,selection_digest=?,state='closed' WHERE turn_id='exact-turn'",
            (raw, hashlib.sha256(raw.encode()).hexdigest()))
        self.sql("UPDATE leases SET state='released' WHERE id=?", (turn["lease_id"],))
        retained = next(row for row in self.rows("leases") if row["id"] == turn["lease_id"])
        self.assertIn(retained["state"], {"held", "rented"})

    def test_changed_guard_definition_refuses_initialization_without_rewriting_history(self):
        self.begin_exact()
        before = self.rows("application_turns")
        self.sql("DROP TRIGGER application_exact_request_delete_v3")
        self.sql("CREATE TRIGGER application_exact_request_delete_v3 BEFORE DELETE ON application_requests BEGIN SELECT RAISE(IGNORE); END")
        with self.assertRaises(lease_broker.ApplicationAdmissionError):
            self.new_broker()
        self.assertEqual(self.rows("application_turns"), before)


if __name__ == "__main__":
    unittest.main()
