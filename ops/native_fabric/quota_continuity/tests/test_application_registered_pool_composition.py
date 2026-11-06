"""Real B HTTP selected dispatch for go, bailian and one native callback pool.

One handler, one gateway, one broker and one SQLite database serve all three
registered routes. Only the loopback upstream, native compiler/carrier evidence
and accounts document are synthetic; selection, admission, dispatch, recipes,
grants and settlement are the real owners. No provider, credential, CLI or
installed runtime is used and no live route is proven.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
from dataclasses import replace
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import sys
import threading
import unittest
from unittest.mock import patch

from test_go_application_handler_composition import NativeApplicationHTTPFixture, SERVICE_TOKEN
from test_application_turn_admission import NativeApplicationFixture, ROOT
from test_application_registered_pool_selection import _policy_document
from go_lease_gateway import ApplicationNativeSelection, ApplicationSelectionProfile, \
    ApplicationSelectionRefused
import lease_broker
import pick
import pool_ledger

# The H compiler keeps its exact source-owned production identity; the same
# module resolution as the incumbent bailian fixture keeps one shared class.
sys.path.insert(0, str(ROOT.parents[2]))
from application_http_transports import BailianResponsesDriver  # noqa: E402

NATIVE_TOKEN = "fixture-native-service-credential-0123456789"
BAILIAN_TOKEN = "fixture-bailian-service-credential-01234567"
POOL_TOKENS = {"go": SERVICE_TOKEN, "bailian": BAILIAN_TOKEN, "codex-native": NATIVE_TOKEN}
POOL_CREDENTIALS = {"go": "MACRO_APPLICATION_TOKEN", "bailian": "BAILIAN_APPLICATION_TOKEN",
                    "codex-native": "NATIVE_APPLICATION_TOKEN"}
POOL_GRANTS = {"go": "macro-app-go", "bailian": "macro-app-bailian",
               "codex-native": "macro-app-codexnative"}


class RegisteredPoolCompositionFixture(NativeApplicationHTTPFixture, NativeApplicationFixture):
    def setUp(self):
        super().setUp()
        self.compilations, self.dispatches, self.logical_posts, self.credential_reads = [], [], [], []
        self.preflight_transform = self.on_execute = self.observation_transform = None
        self.native_text = "Fixture native answer. 中"
        # Three grants for one principal: each pool keeps its own exact
        # credential reference, models and registered recipe digest.
        self.grant.update(pool="codex-native", credential_ref=POOL_CREDENTIALS["codex-native"],
                          grant_id=POOL_GRANTS["codex-native"], models=["fixture-native"],
                          transport_kind="native_cli_operation_v1",
                          output_limit_mode="hard_maximum", usage_policy="nullable_operation")
        go_grant = dict(self.grant, grant_id=POOL_GRANTS["go"], pool="go",
                        credential_ref=POOL_CREDENTIALS["go"], models=["fixture-model"])
        for key in ("transport_kind", "recipe_digest", "output_limit_mode", "usage_policy"):
            go_grant.pop(key, None)
        self.bailian_grant = dict(self.grant, grant_id=POOL_GRANTS["bailian"], pool="bailian",
                                  credential_ref=POOL_CREDENTIALS["bailian"], models=["qwen3.8-flash"])
        for key in ("transport_kind", "output_limit_mode", "usage_policy"):
            self.bailian_grant.pop(key, None)
        self.bailian_driver = self.make_bailian_driver()
        self.http_binding = self.go.ApplicationHTTPBinding(
            self.bailian_driver, frozenset({"account-a", "account-b"}), "b" * 64, self.bailian_credential)
        self.http_recipes = tuple(self.http_binding.recipe(model)
                                  for model in sorted(self.bailian_driver.identity.allowed_models))
        _, self.http_digest = lease_broker._application_http_recipe(
            self.http_binding.recipe("qwen3.8-flash"), pool="bailian", model="qwen3.8-flash")
        self.bailian_grant["recipe_digest"] = self.http_digest
        self.document["providers"]["bailian"] = copy.deepcopy(self.document["providers"]["go"])
        self.document["application_grants"] = [go_grant, self.bailian_grant, self.grant]
        self.save()
        # NativeApplicationHTTPFixture.setUp runs after the native fixture and
        # retargets self.payload at the Go route; restore the native payload.
        self.payload = {"model": "fixture-native",
                        "messages": [{"role": "system", "content": "Fixture system."},
                                     {"role": "user", "content": "Fixture question."}], "max_tokens": 128}
        self.go_response = self.response
        self.responses = {"go": self.go_response,
                          "bailian": {"id": "fixture-response", "model": "qwen3.8-flash",
                                      "status": "completed",
                                      "output": [{"type": "message", "role": "assistant",
                                                  "content": [{"type": "output_text",
                                                               "text": "Bailian fixture answer."}]}],
                                      "usage": {"input_tokens": 11, "output_tokens": 7}},
                          "codex-native": None}
        self.payloads = {"go": {"model": "fixture-model",
                                "messages": [{"role": "user", "content": "fixture"}], "stream": False},
                         "bailian": {"model": "qwen3.8-flash",
                                     "messages": [{"role": "system", "content": "Fixture system."},
                                                  {"role": "user", "content": "Fixture question."}],
                                     "max_tokens": 128, "stream": False},
                         "codex-native": self.payload}
        self.policy_path = self.directory / "pools.yaml"
        self.policy_path.write_text(json.dumps(_policy_document()))
        self.ledger_path = self.directory / "ledger.jsonl"
        self.ledger_path.write_text("")
        for module, name, value in ((pick, "POOLS_YAML", str(self.policy_path)),
                                    (pool_ledger, "LEDGER_PATH", str(self.ledger_path))):
            guard = patch.object(module, name, value)
            guard.start()
            self.addCleanup(guard.stop)
        self.purposes = {pool: self.purpose_for(pool) for pool in POOL_TOKENS}
        self.profile = ApplicationSelectionProfile(source_generation="a" * 64,
            ingress_digest=hashlib.sha256(Path(self.go.__file__).read_bytes()).hexdigest(),
            account_profile=self.router.accounts_path)
        self.selection = ApplicationNativeSelection(pool="codex-native", model="fixture-native",
            mode="codex-native", source_generation=self.recipe["source_generation"])
        self.gateway = self.new_gateway(application_selection_profile=self.profile,
            application_http_recipes=self.http_recipes,
            application_http_accounts=self.http_binding.accounts,
            application_native_recipes=(self.recipe,),
            application_native_accounts={"codex-native": {"account-a", "account-b"}},
            application_native_selection={("codex-native", "fixture-native"): self.selection})
        self.native_binding = self.go.ApplicationNativeBinding(
            recipe=self.recipe, accounts=frozenset({"account-a", "account-b"}),
            preflight=self.compile_native, execute=self.execute_native, selection=self.selection)
        self.services = self.build_services()
        self.server.shutdown()
        self.server.server_close()
        self.server = self.go.make_server(self.router, lease_gateway=self.gateway,
            application_services=self.services, application_http_binding=self.http_binding,
            application_native_bindings=(self.native_binding,), worker_capabilities_enabled=False)
        self.server.handle_error = lambda *args: None
        self._serve(self.server)

    def make_bailian_driver(self):
        def transport(request):
            self.logical_posts.append(request)
            local = replace(request, url="http://127.0.0.1:" + str(self.upstream.server_port) + "/v1/responses")
            observed = self.router.application_http_transport(local)
            return replace(observed, final_url=request.url)
        return BailianResponsesDriver(transport=transport, clock=lambda: self.clock[0])

    def bailian_credential(self, account):
        self.credential_reads.append((account, len(self.rows("application_requests"))))
        return "fixture-bailian-" + account

    def build_services(self, *, purposes=True):
        return tuple(
            self.go.ApplicationServiceBinding("macro", "vps", "site_interactive",
                                              POOL_CREDENTIALS[pool], POOL_TOKENS[pool], pool=pool,
                                              selection_purpose=self.go.ApplicationSelectionPurpose(
                                                  self.purposes[pool]) if purposes else None)
            for pool in POOL_TOKENS)

    def purpose_for(self, pool):
        return {"purpose_id": "fixture-registered-pool-operation",
            "source_ref": "fixture:qualified-registered-purpose",
            "task": {"task_class": "mechanical", "route_key": "fixture-registered-pool-dispatch",
                     "task_complexity": "C1_ROUTINE_BOUNDED", "needs": [],
                     "escalation_reason": "fixture registered pool economic witness"}}

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

    def restart(self, *, gateway=None, purposes=True, bindings=True):
        self.server.shutdown()
        self.server.server_close()
        self.server = self.go.make_server(self.router, lease_gateway=gateway or self.gateway,
            application_services=self.build_services(purposes=purposes),
            application_http_binding=self.http_binding,
            application_native_bindings=(self.native_binding,) if bindings else (),
            worker_capabilities_enabled=False)
        self.server.handle_error = lambda *args: None
        self._serve(self.server)

    def request(self, pool, *, turn, step="step-1", payload=None, headers=None):
        if self.responses.get(pool) is not None:
            self.response = self.responses[pool]
        body = json.dumps(self.payloads[pool] if payload is None else payload).encode()
        supplied = {"Authorization": "Bearer " + POOL_TOKENS[pool], "Content-Type": "application/json",
                    "Connection": "close", "X-MM-Application-Turn-ID": turn, "Idempotency-Key": step}
        if pool != "go":
            supplied["X-MM-Application-Recipe-Digest"] = (
                self.http_digest if pool == "bailian" else self.recipe_digest)
        supplied.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request("POST", "/v1/chat/completions", body, supplied)
            response = connection.getresponse()
            data = response.read()
            return response.status, json.loads(data), dict(response.getheaders())
        finally:
            connection.close()

    def close(self, turn):
        body = json.dumps({"turn_id": turn}).encode()
        supplied = {"Authorization": "Bearer " + SERVICE_TOKEN, "Content-Type": "application/json",
                    "Connection": "close"}
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request("POST", "/application-turns/close", body, supplied)
            response = connection.getresponse()
            data = response.read()
            return response.status, json.loads(data), dict(response.getheaders())
        finally:
            connection.close()

    def scope(self, pool, turn):
        return {"workload": "site_interactive", "turn_id": turn, "pool": pool,
                "model": self.payloads[pool]["model"]}

    def begin_selected(self, pool, turn, selected):
        return self.gateway.begin_application(self.scope(pool, turn), principal_id="macro", host="vps",
            expected_credential_ref=POOL_CREDENTIALS[pool],
            expected_recipe_digest=self.http_digest if pool == "bailian" else self.recipe_digest,
            expected_selection=selected, selection_purpose=self.purposes[pool],
            selection_payload=self.payloads[pool])

    def usage_rows(self):
        path = Path(self.router.usage_path)
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def assert_no_effect(self):
        self.assertEqual(self.rows("leases"), [])
        self.assertEqual(self.rows("application_turns"), [])
        self.assertEqual(self.rows("application_requests"), [])
        self.assertEqual((self.gets, self.posts, self.usage_rows()), ([], [], []))
        self.assertEqual((self.compilations, self.dispatches), ([], []))
        self.assertEqual((self.logical_posts, self.credential_reads), ([], []))


class RegisteredPoolCompositionTests(RegisteredPoolCompositionFixture):
    def test_selected_first_post_dispatches_each_pool_with_exact_identity(self):
        self.assertEqual(self.request("go", turn="go-turn")[0], 200)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(json.loads(self.posts[0][1])["model"], "fixture-model")
        self.assertEqual(self.posts[0][2], "Bearer fixture-provider-a")
        with patch.object(self.router, "reserve_application_account",
                          side_effect=AssertionError("Go quota on bailian")), \
             patch.object(self.router, "_usage_row", side_effect=AssertionError("Go ledger on bailian")):
            status, body, headers = self.request("bailian", turn="bailian-turn")
        self.assertEqual(status, 200, body)
        self.assertEqual(headers["X-MM-Application-Disposition"], "terminal")
        self.assertEqual(body["choices"][0]["message"]["content"], "Bailian fixture answer.")
        self.assertEqual(len(self.posts), 2)
        self.assertEqual(json.loads(self.posts[1][1])["max_output_tokens"], 128)
        self.assertEqual(self.posts[1][2], "Bearer fixture-bailian-account-a")
        self.assertEqual(len(self.logical_posts), 1)
        with patch.object(self.router, "reserve_application_account",
                          side_effect=AssertionError("Go quota on native")), \
             patch.object(self.router, "application_transport",
                          side_effect=AssertionError("HTTP transport on native")), \
             patch.object(self.router, "_usage_row", side_effect=AssertionError("Go ledger on native")):
            status, body, headers = self.request("codex-native", turn="native-turn")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["model"], "fixture-native")
        self.assertEqual(body["choices"][0]["message"]["content"], self.native_text)
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(len(self.posts), 2)
        turns = {row["pool"]: row for row in self.rows("application_turns")}
        self.assertEqual(set(turns), {"go", "bailian", "codex-native"})
        for pool, row in turns.items():
            record = json.loads(row["selection_json"])
            self.assertEqual(row["model"], self.payloads[pool]["model"])
            self.assertEqual(record["identity"]["pool"], pool)
            self.assertEqual(record["identity"]["model"], self.payloads[pool]["model"])
            self.assertEqual(record["identity"]["observation_source"], "broker-ledger-room")
            self.assertEqual(record["identity"]["grant_ref"]["grant_id"], POOL_GRANTS[pool])
            self.assertEqual(row["selection_digest"],
                             hashlib.sha256(row["selection_json"].encode()).hexdigest())
        leases = {row["pool"]: row for row in self.rows("leases")}
        self.assertEqual(set(leases), {"go", "bailian", "codex-native"})
        self.assertTrue(all(row["host"] == "vps" for row in leases.values()))
        # The native callback ran on the recipe's physical host, never on the
        # authenticated caller host that owns the lease.
        receipt = json.loads(self.rows("application_requests")[-1]["terminal_receipt"])
        self.assertEqual(receipt["process"]["host"], self.recipe["physical_host"])
        self.assertNotEqual(receipt["process"]["host"], "vps")
        self.assertEqual(len(self.usage_rows()), 1)

    def test_native_dispatch_never_touches_router_capacity_or_usage_owner(self):
        with patch.object(self.router, "reserve_application_account",
                          side_effect=AssertionError("Router reserve")), \
             patch.object(self.router, "application_transport",
                          side_effect=AssertionError("HTTP transport")), \
             patch.object(self.router, "_usage_row", side_effect=AssertionError("Router accounting")):
            self.assertEqual(self.request("codex-native", turn="native-turn")[0], 200)
        self.assertEqual(self.rows("application_turns")[0]["account"], "account-a")
        self.assertEqual(self.dispatches[0].invocation["lease_id"],
                         self.rows("application_turns")[0]["lease_id"])
        self.assertEqual((self.gets, self.posts, self.usage_rows()), ([], [], []))

    def test_concurrent_same_pool_posts_reconcile_to_one_turn_and_one_send(self):
        entered, release = threading.Event(), threading.Event()
        def block_first(dispatch):
            entered.set()
            release.wait(3)
        self.on_execute = block_first
        with ThreadPoolExecutor(max_workers=4) as executor:
            first = executor.submit(self.request, "codex-native", turn="nat-race")
            self.assertTrue(entered.wait(3))
            others = [executor.submit(self.request, "codex-native", turn="nat-race")
                      for _ in range(3)]
            dupes = [future.result(5) for future in others]
            release.set()
            self.assertEqual(first.result(5)[0], 200)
        self.assertEqual(sorted(body["application"]["disposition"] for _, body, _ in dupes),
                         ["pending", "pending", "pending"])
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.rows("application_turns")), 1)
        self.assertEqual(len(self.rows("application_requests")), 1)
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(len(self.compilations), 1)
        self.assertEqual((self.gets, self.posts), ([], []))

    def test_grant_replacement_between_selection_and_admission_refuses_without_allocation(self):
        begin = self.gateway.begin_application
        def race(*args, **kwargs):
            self.bailian_grant["enabled"] = False
            self.save()
            return begin(*args, **kwargs)
        with patch.object(self.gateway, "begin_application", race):
            status, body, _ = self.request("bailian", turn="bailian-race")
        self.assertEqual(status, 409, body)
        self.assertEqual(body["application"]["disposition"], "refused")
        self.assert_no_effect()

    def test_stale_native_selection_refuses_before_lease_or_compile(self):
        begin = self.gateway.begin_application
        def race(*args, **kwargs):
            self.clock[0] += 6
            return begin(*args, **kwargs)
        with patch.object(self.gateway, "begin_application", race):
            status, body, _ = self.request("codex-native", turn="nat-stale")
        self.assertEqual(status, 409)
        self.assertEqual(body["application"]["disposition"], "refused")
        self.assert_no_effect()

    def test_last_slot_selection_refusal_recovers_concurrent_original_without_repick(self):
        select = self.gateway.select_application
        def concurrent_admission(*args, **kwargs):
            selected = select(*args, **kwargs)
            self.begin_selected("codex-native", "nat-last", selected)
            raise ApplicationSelectionRefused("synthetic concurrent turn became visible")
        with patch.object(self.gateway, "select_application", concurrent_admission):
            self.assertEqual(self.request("codex-native", turn="nat-last")[0], 200)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.rows("application_turns")), 1)
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual((self.gets, self.posts), ([], []))

    def test_native_begin_ack_loss_recovers_without_second_admission_or_reselection(self):
        begin = self.gateway.begin_application
        def lost(*args, **kwargs):
            begin(*args, **kwargs)
            raise OSError("synthetic lost admission acknowledgement")
        with patch.object(self.gateway, "begin_application", side_effect=lost) as called:
            self.assertEqual(self.request("codex-native", turn="nat-ack")[0], 503)
        self.assertEqual(called.call_count, 1)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual((self.compilations, self.dispatches), ([], []))
        with patch.object(pick, "select_application",
                          side_effect=AssertionError("ack loss reselected")):
            self.assertEqual(self.request("codex-native", turn="nat-ack")[0], 200)
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.dispatches), 1)

    def test_native_prepare_ack_loss_keeps_original_pending_without_recompile(self):
        prepare = self.gateway.prepare_application
        def lost_prepare(*args, **kwargs):
            prepare(*args, **kwargs)
            raise OSError("synthetic lost prepare acknowledgement")
        with patch.object(self.gateway, "prepare_application", side_effect=lost_prepare) as prepared:
            self.assertEqual(self.request("codex-native", turn="nat-pending")[1]["application"]["disposition"],
                             "pending")
            self.assertEqual(self.request("codex-native", turn="nat-pending")[1]["application"]["disposition"],
                             "pending")
        self.assertEqual(prepared.call_count, 1)
        self.assertEqual(self.dispatches, [])
        self.assertEqual(self.rows("application_requests")[0]["state"], "pending")
        self.assertIn(self.rows("leases")[0]["state"], {"held", "rented"})

    def test_native_terminal_ack_loss_recovers_exact_receipt_without_second_writer(self):
        complete = self.gateway.complete_application
        def lost_terminal(*args, **kwargs):
            complete(*args, **kwargs)
            raise OSError("synthetic lost terminal acknowledgement")
        with patch.object(self.gateway, "complete_application", side_effect=lost_terminal) as completed, \
             patch.object(self.gateway, "mark_application_unknown",
                          side_effect=AssertionError("second writer")):
            self.assertEqual(self.request("codex-native", turn="nat-terminal")[0], 200)
        self.assertEqual(completed.call_count, 1)
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(self.rows("application_requests")[0]["state"], "terminal")

    def test_native_provider_error_is_terminal_and_explicitly_closeable(self):
        def known_error(value):
            value["text"] = ""
            value["provider_terminal"]["state"] = "failed"
            value["process"]["returncode"] = 1
        self.observation_transform = known_error
        status, body, _ = self.request("codex-native", turn="nat-error")
        self.assertEqual((status, body["application"]["disposition"]), (502, "terminal"))
        self.assertNotIn("choices", body)
        self.assertEqual(body["application"]["serving_model"], "fixture-native")
        self.assertEqual(self.rows("application_requests")[0]["state"], "terminal")
        recovered = self.request("codex-native", turn="nat-error")[1]["application"]
        self.assertEqual(recovered["disposition"], "terminal_receipt_only")
        self.assertNotIn("usage", recovered)
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(self.close("nat-error")[0], 200)
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_native_partial_and_unknown_usage_stay_nullable_on_the_wire(self):
        self.observation_transform = lambda value: value["usage"].update(
            input_tokens=11, output_tokens=7, scope="provider_final", complete=False)
        status, body, _ = self.request("codex-native", turn="nat-partial")
        self.assertEqual(status, 200)
        self.assertEqual(body["usage"], {"prompt_tokens": None, "completion_tokens": None})
        terminal = json.loads(self.rows("application_requests")[0]["terminal_receipt"])
        self.assertEqual(terminal["usage"], {"input_tokens": 11, "output_tokens": 7,
                                             "scope": "provider_final", "complete": False})
        self.observation_transform = lambda value: value["usage"].update(
            input_tokens=None, output_tokens=None, scope="unknown", complete=False)
        status, body, _ = self.request("codex-native", turn="nat-unknown")
        self.assertEqual(status, 200)
        self.assertEqual(body["usage"], {"prompt_tokens": None, "completion_tokens": None})
        self.assertIsNone(json.loads(
            self.rows("application_requests")[-1]["terminal_receipt"])["usage"]["input_tokens"])

    def test_bailian_provider_error_settles_actual_usage_without_delivery(self):
        self.response_status = 429
        self.responses["bailian"] = {"error": {"message": "synthetic provider detail"},
                                    "model": "qwen3.8-flash",
                                    "usage": {"input_tokens": 4, "output_tokens": 0}}
        status, body, _ = self.request("bailian", turn="bailian-error")
        self.assertEqual(status, 429)
        self.assertEqual(body["application"]["disposition"], "terminal")
        self.assertNotIn("choices", body)
        self.assertNotIn("synthetic provider detail", json.dumps(body))
        self.assertEqual(body["application"]["serving_model"], "qwen3.8-flash")
        self.assertEqual(body["application"]["usage"], {"input_tokens": 4, "output_tokens": 0})
        terminal = json.loads(self.rows("application_requests")[0]["terminal_receipt"])
        self.assertEqual(terminal["status_code"], 429)
        self.assertEqual(terminal["served_model"], "qwen3.8-flash")
        self.assertEqual(terminal["usage"], {"input_tokens": 4, "output_tokens": 0})
        self.assertIsNone(terminal["delivery_digest"])
        self.assertNotIn("synthetic provider detail", json.dumps(terminal))
        status, replay, _ = self.request("bailian", turn="bailian-error")
        self.assertEqual((status, replay["application"]["disposition"]), (409, "terminal_receipt_only"))
        self.assertNotIn("usage", replay["application"])
        self.assertNotIn("choices", replay)
        self.assertEqual((len(self.posts), len(self.logical_posts)), (1, 1))
        self.assertEqual(len(self.rows("application_requests")), 1)
        self.assertEqual(self.usage_rows(), [])  # HTTP receipt owns this observation, not Go's ledger.
        self.assertEqual(self.close("bailian-error")[0], 200)
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_native_tools_or_media_refuse_before_admission_but_go_tools_commit(self):
        tools = [{"type": "function", "function": {"name": "inspect",
            "parameters": {"type": "object", "properties": {}}}}]
        media = [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "https://fixture.invalid/image"}}]}]
        for label, payload in (("tools", dict(self.payloads["codex-native"], tools=tools)),
                               ("media", dict(self.payloads["codex-native"], messages=media))):
            with self.subTest(grammar=label):
                status, body, _ = self.request("codex-native", turn="nat-grammar", payload=payload)
                self.assertEqual(status, 400)
                self.assertEqual(body["application"]["disposition"], "refused")
        self.assert_no_effect()
        status, body, _ = self.request("go", turn="go-tools",
                                       payload=dict(self.payloads["go"], tools=tools))
        self.assertEqual(status, 200)
        record = json.loads(self.rows("application_turns")[0]["selection_json"])
        self.assertEqual(record["identity"]["task"]["needs"], ["tools"])
        self.assertEqual(json.loads(self.posts[0][1])["tools"], tools)

    def test_purpose_removal_holds_selected_turns_without_legacy_reselection(self):
        self.assertEqual(self.request("codex-native", turn="nat-hold")[0], 200)
        before = len(self.dispatches)
        self.restart(purposes=False, bindings=False)
        with patch.object(pick, "select_application",
                          side_effect=AssertionError("replay reselected")):
            replay = self.request("codex-native", turn="nat-hold")[1]["application"]
        self.assertEqual(replay["disposition"], "terminal_receipt_only")
        self.assertNotIn("usage", replay)
        status, body, _ = self.request("codex-native", turn="nat-hold", step="step-2")
        # New execution refuses once the purpose and its selection transport
        # are gone; the original committed turn is never reselected.
        self.assertEqual(status, 503)
        self.assertEqual(body["application"]["disposition"], "refused")
        self.assertEqual(len(self.dispatches), before)
        self.assertEqual(len(self.rows("leases")), 1)

    def test_replay_survives_native_executor_removal_without_selection(self):
        self.assertEqual(self.request("codex-native", turn="nat-gone")[0], 200)
        prepare = self.gateway.prepare_application
        def lost_prepare(*args, **kwargs):
            prepare(*args, **kwargs)
            raise OSError("synthetic lost prepare acknowledgement")
        with patch.object(self.gateway, "prepare_application", side_effect=lost_prepare):
            self.assertEqual(self.request("codex-native", turn="nat-pending-gone")[1]["application"]["disposition"],
                             "pending")
        before = (len(self.compilations), len(self.dispatches))
        turns_before = {row["turn_id"]: row for row in self.rows("application_turns")}
        requests_before = self.rows("application_requests")
        fresh = self.new_gateway(application_selection_profile=self.profile,
            application_http_recipes=self.http_recipes,
            application_http_accounts=self.http_binding.accounts)
        # Enrollment and purpose survive. Only the mutable executor/selection
        # transport disappears, which must not prevent listener startup.
        self.restart(gateway=fresh, purposes=True, bindings=False)
        with patch.object(pick, "select_application",
                          side_effect=AssertionError("recovery or unavailable route reselected")) as selector, \
             patch.object(fresh, "begin_application",
                          side_effect=AssertionError("unavailable route admitted")) as admitted:
            status, body, _ = self.request("codex-native", turn="nat-gone")
            self.assertEqual((status, body["application"]["disposition"]), (409, "terminal_receipt_only"))
            self.assertNotIn("usage", body["application"])
            status, body, _ = self.request("codex-native", turn="nat-pending-gone")
            self.assertEqual((status, body["application"]["disposition"]), (409, "pending"))
            for turn, step in (("nat-new-gone", "step-1"), ("nat-gone", "step-2")):
                status, body, _ = self.request("codex-native", turn=turn, step=step)
                self.assertEqual((status, body["application"]["disposition"]), (503, "refused"))
                self.assertEqual(body["error"]["type"], "application_native_transport_unavailable")
            status, body, _ = self.close("nat-gone")
            self.assertEqual((status, body["application"]["disposition"]), (200, "closed"))
            status, body, _ = self.close("nat-pending-gone")
            self.assertEqual((status, body["application"]["disposition"]), (409, "pending"))
            selector.assert_not_called()
            admitted.assert_not_called()
        self.assertEqual((len(self.compilations), len(self.dispatches)), before)
        self.assertEqual(self.rows("application_requests"), requests_before)
        self.assertEqual({row["turn_id"] for row in self.rows("application_turns")},
                         set(turns_before))
        leases = {row["id"]: row for row in self.rows("leases")}
        self.assertEqual(leases[turns_before["nat-gone"]["lease_id"]]["state"], "released")
        self.assertIn(leases[turns_before["nat-pending-gone"]["lease_id"]]["state"], {"held", "rented"})


if __name__ == "__main__":
    unittest.main()
