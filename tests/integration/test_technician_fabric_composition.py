"""Technician's existing artifact through actual portfolio AUTO C/B/A.

The public/provider network is synthetic; source owners, native service identity,
HTTP, SQLite, accounting, closure, locking, and artifact persistence stay real.
"""
from __future__ import annotations
import copy
from dataclasses import replace
from datetime import date
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch

from brain import technician as T

_spec = importlib.util.spec_from_file_location("_technician_auto_fixture",
    Path(__file__).with_name("test_fabric_text_cross_pool_auto.py"))
_auto = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_auto)


class TechnicianApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _auto.AutoTextApplicationTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        _auto.AutoTextApplicationTests.tearDownClass.__func__(cls)

    start = _auto.AutoTextApplicationTests.start
    configure = _auto.AutoTextApplicationTests.configure
    costs = _auto.AutoTextApplicationTests.costs

    def setUp(self):
        _auto.AutoTextApplicationTests.setUp(self)
        from engine import catalyst_tone
        self.cache = catalyst_tone
        self.start(patch.object(T, "_ARTIFACTS", self.root / "committee"))
        self.available = self.start(patch.object(T.cli_bridge, "available",
                            side_effect=AssertionError("legacy readiness")))
        self.reason = self.start(patch.object(T.cli_bridge, "reason_sync",
                            side_effect=AssertionError("legacy subprocess")))
        for grant in self.native.document["application_grants"]:
            grant.update(principal_id="macro_portfolio_fabric",
                         admission_root="service:macro_portfolio_fabric", workloads=["portfolio_analysis"])
        self.native.save()
        self.portfolio_base = replace(
            self.owner._APPLICATION_FABRIC_TRANSPORTS["native_fabric_macro_portfolio_auto_v1"],
            secret_ref="MACRO_APPLICATION_TOKEN", qualified=True, application_allowed=True)
        self.configure_portfolio(["go"])
        self.native.response = _auto._helpers.packet(json.dumps(
            {"verdict": "now", "confidence": 0.8, "rationale": "A clean, defined chart setup."}))
        self.input = T.technician_input("NVDA", entry_signal={"stop": 100.0},
                                       tech={"rsi14": 55.0, "pct_vs_50dma": 2.0})
        self.day = "2026-11-06"

    def configure_portfolio(self, pools):
        import yaml
        native = self.native
        scope = {"schema": "mastermind.application_route_scope.v1", "pools": sorted(pools)}
        service = native.go.ApplicationServiceBinding(
            "macro_portfolio_fabric", "vps", "portfolio_analysis", "MACRO_APPLICATION_TOKEN",
            self.native_module.SERVICE_TOKEN,
            selection_purpose=native.go.ApplicationSelectionPurpose(native.purposes["go"]),
            route_scope=native.go.ApplicationRouteScope(scope))
        native.server.shutdown()
        native.server.server_close()
        native.server = native.go.make_server(native.router, lease_gateway=native.gateway,
            application_services=(service,), application_http_binding=native.http_binding,
            application_native_bindings=(native.native_binding,), worker_capabilities_enabled=False)
        native.server.handle_error = lambda *args: None
        native._serve(native.server)
        selected = replace(self.portfolio_base, base_url=f"http://127.0.0.1:{native.server.server_port}/v1")
        self.start(patch.dict(self.owner._APPLICATION_FABRIC_TRANSPORTS,
            {"native_fabric_macro_portfolio_auto_v1": selected}))
        row = {key: getattr(selected, key) for key in self.owner._APPLICATION_IDENTITY_FIELDS}
        row.update(transport_id="native_fabric_macro_portfolio_auto_v1", route_scope=scope,
            enabled=True, application_allowed=True, qualification=self.owner.PROFILE_QUALIFIED_CANARY,
            qualification_ref="fixture:technician-portfolio-real-owners", qualified_until=time.time()+3600)
        document = json.loads(self.originals[self.config_paths[0]])
        startup = self.owner._APPLICATION_FABRIC_TRANSPORTS["native_fabric_application_auto_v1"]
        startup_row = {key: getattr(startup, key) for key in self.owner._APPLICATION_IDENTITY_FIELDS}
        startup_row.update(transport_id="native_fabric_application_auto_v1", route_scope=scope,
            enabled=True, application_allowed=True, qualification=self.owner.PROFILE_QUALIFIED_CANARY,
            qualification_ref="fixture:technician-host-auto-selection", qualified_until=time.time()+3600)
        document["application_fabric_modes"] = {
            "shared_fabric": startup_row, "macro_portfolio_fabric": row}
        self.config_paths[0].write_text(json.dumps(document))
        self.config_paths[1].write_text(yaml.safe_dump({"capabilities": [{
            "capability_id": selected.capability_id, "secret_ref": selected.secret_ref,
            "kill_state": "active", "allowed_lanes": [T._FABRIC_LANE]}]}))

    def path(self):
        return T._ARTIFACTS / self.day / "NVDA/technician.json"

    def document(self):
        return json.loads(self.path().read_text())

    def assess(self, inp=None):
        return T.technician_assess(copy.deepcopy(self.input if inp is None else inp), asof=self.day)

    def counts(self):
        return (len(self.native.posts), len(self.native.dispatches),
                len(self.native.rows("application_requests")), len(self.costs()), len(self.closes))

    def test_positive_portfolio_original_and_zero_spend_direct_run_replay(self):
        def upstream():
            doc = self.document()
            row = doc[T._FABRIC_KEY]["cache"]["entries"][0]
            self.assertEqual(row["state"], "pending")
            self.assertEqual(doc["verdict"]["verdict"], "wait")
            self.assertEqual(set(doc[T._FABRIC_KEY]["requests"]), {row["operation_id"]})
        self.native.on_upstream = upstream
        result = self.assess()
        self.assertEqual(result["verdict"], "now", result)
        self.assertEqual((result["model"], result["served_by"]), ("fixture-model", "go"))
        doc = self.document()
        row = doc[T._FABRIC_KEY]["cache"]["entries"][0]
        self.assertEqual(doc["verdict"], result)
        self.assertTrue(row["receipt"]["close"]["closed"])
        turn = self.native.rows("application_turns")[0]
        self.assertEqual((turn["principal_id"], turn["workload"]),
                         ("macro_portfolio_fabric", "portfolio_analysis"))
        before = self.path().read_bytes()
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("repeat credential")):
            repeated = T.run("NVDA", entry_signal={"stop": 100.0},
                             tech={"rsi14": 55.0, "pct_vs_50dma": 2.0}, asof=self.day)
            self.assertEqual(repeated, result)
        self.assertEqual(self.path().read_bytes(), before)
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))
        self.available.assert_not_called()
        self.reason.assert_not_called()
        self.assertEqual(self.costs()[0]["cost_basis"], "unknown")

    def test_direct_assess_filters_nested_forbidden_fields_before_freezing(self):
        inp = copy.deepcopy(self.input)
        inp["bull_thesis"] = "DO-NOT-SEND"
        inp["tech"]["conviction_score"] = 99
        inp["options"]["nested"] = {"fair_value": 200.0, "gamma_flip": 111.0}
        result = self.assess(inp)
        self.assertEqual(result["verdict"], "now", result)
        doc = self.document()
        frozen = json.dumps(doc["input"])
        self.assertNotIn("DO-NOT-SEND", frozen)
        self.assertNotIn("conviction", frozen)
        self.assertNotIn("fair_value", frozen)
        request = next(iter(doc[T._FABRIC_KEY]["requests"].values()))
        self.assertEqual(json.loads(request["user"]), doc["input"])

    def test_refused_close_retains_now_as_evidence_but_exposes_wait(self):
        with patch.object(self.native.gateway, "close_application_turn",
                          return_value={"disposition": "refused"}):
            result = self.assess()
        self.assertEqual(result["verdict"], "wait")
        doc = self.document()
        row = doc[T._FABRIC_KEY]["cache"]["entries"][0]
        self.assertEqual(row["state"], "held")
        self.assertEqual(row["result"]["verdict"], "now")
        self.assertEqual(doc["verdict"]["verdict"], "wait")
        before = self.counts()
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        changed = copy.deepcopy(self.input)
        changed["tech"]["rsi14"] = 80.0
        self.assertEqual(self.assess(changed)["verdict"], "wait")
        self.assertEqual(self.counts(), before)
        self.available.assert_not_called()

    def test_lost_close_ack_never_resends_original(self):
        original = self.native.gateway.close_application_turn
        def close(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError("synthetic lost close acknowledgement")
        with patch.object(self.native.gateway, "close_application_turn", side_effect=close):
            self.assertEqual(self.assess()["verdict"], "wait")
        before = self.counts()
        self.assertEqual(self.assess()["verdict"], "wait")
        self.assertEqual(self.counts(), before)

    def test_concurrent_assess_has_one_original(self):
        from concurrent.futures import ThreadPoolExecutor
        self.native.block = threading.Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.assess)
            try:
                self.assertTrue(self.native.arrived.wait(3))
                self.assertEqual(self.assess()["verdict"], "wait")
                self.assertEqual(len(self.native.posts), 1)
            finally:
                self.native.block.set()
            self.assertEqual(future.result(timeout=20)["verdict"], "now")
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))

    def test_claim_readback_failure_prevents_binding(self):
        original = self.cache._cache_save
        def save(path, value):
            original(path, value)
            raise OSError("synthetic lost claim readback")
        with patch.object(self.cache, "_cache_save", side_effect=save):
            self.assertEqual(self.assess()["verdict"], "wait")
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))
        self.assertEqual(self.assess()["verdict"], "wait")
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))

    def test_final_save_failure_keeps_pending_and_returns_wait(self):
        original = self.cache._cache_save
        def save(path, value):
            rows = value[T._FABRIC_KEY]["cache"]["entries"]
            if rows[-1]["state"] == "terminal":
                raise OSError("synthetic final write failure")
            return original(path, value)
        with patch.object(self.cache, "_cache_save", side_effect=save):
            self.assertEqual(self.assess()["verdict"], "wait")
        self.assertEqual(self.document()["verdict"]["verdict"], "wait")
        before = self.counts()
        self.assertEqual(self.assess()["verdict"], "wait")
        self.assertEqual(self.counts(), before)

    def test_lost_final_ack_recovers_already_published_original(self):
        original = self.cache._cache_save
        def save(path, value):
            original(path, value)
            if value[T._FABRIC_KEY]["cache"]["entries"][-1]["state"] == "terminal":
                raise OSError("synthetic final acknowledgement lost")
        with patch.object(self.cache, "_cache_save", side_effect=save):
            self.assertEqual(self.assess()["verdict"], "wait")
        before = self.counts()
        self.assertEqual(self.assess()["verdict"], "now")
        self.assertEqual(self.counts(), before)

    def test_changed_input_uses_new_original_after_positive_close(self):
        first = self.assess()
        before = self.document()
        changed = copy.deepcopy(self.input)
        changed["tech"]["rsi14"] = 80.0
        self.native.response = _auto._helpers.packet(json.dumps({"verdict": "wait", "confidence": 0.9}))
        second = self.assess(changed)
        self.assertEqual((first["verdict"], second["verdict"]), ("now", "wait"))
        doc = self.document()
        self.assertEqual(doc["input"], changed)
        self.assertEqual(doc[T._FABRIC_KEY]["cache"]["entries"][0],
                         before[T._FABRIC_KEY]["cache"]["entries"][0])
        self.assertEqual(self.counts(), (2, 0, 2, 2, 2))

    def test_legacy_writer_cannot_erase_selected_result(self):
        result = self.assess()
        before = self.path().read_bytes()
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        self.assertIsNone(T._write_artifact(self.day, "NVDA", self.input, T._wait("stale legacy result")))
        self.assertEqual(self.path().read_bytes(), before)
        self.assertEqual(self.assess(), result)
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))

    def test_corrupt_saved_result_or_attribution_refuses_without_provider(self):
        self.assess()
        original = self.document()
        for kind in ("input", "output", "model", "request", "close", "projection"):
            with self.subTest(kind=kind):
                doc = copy.deepcopy(original)
                owned = doc[T._FABRIC_KEY]
                row = owned["cache"]["entries"][0]
                if kind == "input":
                    owned["requests"][row["operation_id"]]["input"]["tech"]["rsi14"] = 99
                elif kind == "output":
                    row["result"]["confidence"] = 1.0
                    row["result_digest"] = self.cache._cache_hash(row["result"])
                elif kind == "model":
                    row["receipt"]["served_model"] = "unobserved"
                elif kind == "request":
                    row["request"]["digest"] = "a" * 64
                elif kind == "close":
                    row["receipt"]["close"] = {"disposition": "refused", "closed": False,
                                                "effect_unknown": False, "attempted": True}
                else:
                    doc["verdict"]["confidence"] = 1.0
                self.path().write_text(json.dumps(doc))
                before = self.counts()
                self.assertEqual(self.assess()["verdict"], "wait")
                self.assertEqual(self.counts(), before)

    def test_conflicting_ticker_and_path_components_refuse_before_binding(self):
        for ticker, day in (("AAPL", self.day), ("../escape", self.day), ("NVDA", "invalid")):
            with self.subTest(ticker=ticker, day=day):
                result = T.technician_assess(self.input, ticker=ticker, asof=day)
                self.assertEqual(result["verdict"], "wait")
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))

    def test_one_day_is_resolved_across_midnight(self):
        calls = []
        class Clock(date):
            @classmethod
            def today(cls):
                calls.append(True)
                return date(2026, 11, 6 if len(calls) == 1 else 7)
        with patch.object(T, "date", Clock):
            result = T.run("NVDA", entry_signal={"stop": 100.0},
                           tech={"rsi14": 55.0, "pct_vs_50dma": 2.0})
        self.assertEqual(result["verdict"], "now", result)
        self.assertEqual(len(calls), 1)
        self.assertTrue(self.path().exists())
        self.assertFalse((T._ARTIFACTS / "2026-11-07").exists())

    def test_bot_only_and_invalid_application_selectors_are_exclusive(self):
        with patch.dict(os.environ, {"BOT_LLM_BACKEND": "fabric"}):
            os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
            self.assertEqual(self.assess()["verdict"], "wait")
        for value in ("", "not-a-known-mode"):
            with patch.dict(os.environ, {"MM_PROVIDER_APPLICATION_MODE": value}):
                self.assertEqual(self.assess()["verdict"], "wait")
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))
        self.available.assert_not_called()
        self.reason.assert_not_called()

    def test_missing_capability_refuses_before_credentials(self):
        import yaml
        self.config_paths[1].write_text(yaml.safe_dump({"capabilities": []}))
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("credential")):
            self.assertEqual(self.assess()["verdict"], "wait")
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))
        self.assertFalse(self.path().exists())

    def test_nonfinite_and_unknown_verdicts_remain_conservative(self):
        for n, text in enumerate(('{"verdict":"now","confidence":NaN}',
                                  '{"verdict":"now","confidence":true}',
                                  '{"verdict":"STRONG_BUY","confidence":1.0}', '[]', 'not JSON')):
            with self.subTest(text=text):
                self.native.response = _auto._helpers.packet(text)
                inp = copy.deepcopy(self.input)
                inp["tech"]["rsi14"] = 50 + n
                self.assertEqual(self.assess(inp)["verdict"], "wait")
        self.assertEqual(len(self.native.posts), 5)

    def test_partial_usage_stays_unknown_without_price_fiction(self):
        self.native.response["usage"] = {"prompt_tokens": 11}
        self.assertEqual(self.assess()["verdict"], "now")
        row = self.document()[T._FABRIC_KEY]["cache"]["entries"][0]
        self.assertEqual(row["receipt"]["usage"]["usage_state"], "unknown")
        self.assertIsNone(row["receipt"]["observed_usage"]["output_tokens"])
        self.assertEqual(self.costs(), [])

    def test_cancellation_propagates_and_retains_pending_original(self):
        stop = KeyboardInterrupt("synthetic cancellation")
        with patch.object(self.shared, "make_call", side_effect=stop):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.assess()
        self.assertIs(caught.exception, stop)
        before = self.counts()
        self.assertEqual(self.assess()["verdict"], "wait")
        self.assertEqual(self.counts(), before)


    def test_historical_result_cannot_escape_current_artifact_after_selector_removal(self):
        self.assertEqual(self.assess()["verdict"], "now")
        changed = copy.deepcopy(self.input)
        changed["tech"]["rsi14"] = 80.0
        self.native.response = _auto._helpers.packet(json.dumps({"verdict": "wait", "confidence": 0.9}))
        self.assertEqual(self.assess(changed)["verdict"], "wait")
        before, counts = self.path().read_bytes(), self.counts()
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        result = T.run("NVDA", entry_signal={"stop": 100.0},
                       tech={"rsi14": 55.0, "pct_vs_50dma": 2.0}, asof=self.day)
        self.assertEqual(result["verdict"], "wait")
        self.assertEqual(self.path().read_bytes(), before)
        self.assertEqual(self.counts(), counts)
        self.available.assert_not_called()

    def test_writer_failure_with_selector_removed_keeps_original_custody(self):
        def writer(*args, **kwargs):
            os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
            raise OSError("synthetic publication acknowledgement lost")
        with patch.object(T, "_write_artifact", side_effect=writer):
            result = T.run("NVDA", entry_signal={"stop": 100.0},
                           tech={"rsi14": 55.0, "pct_vs_50dma": 2.0}, asof=self.day)
        self.assertEqual(result["verdict"], "wait")
        counts = self.counts()
        recovered = T.run("NVDA", entry_signal={"stop": 100.0},
                          tech={"rsi14": 55.0, "pct_vs_50dma": 2.0}, asof=self.day)
        self.assertEqual(recovered["verdict"], "now")
        self.assertEqual(self.counts(), counts)


    def test_direct_assess_cannot_rewind_newer_original_projection(self):
        self.assertEqual(self.assess()["verdict"], "now")
        changed = copy.deepcopy(self.input)
        changed["tech"]["rsi14"] = 80.0
        self.native.response = _auto._helpers.packet(json.dumps({"verdict": "wait", "confidence": 0.9}))
        self.assertEqual(self.assess(changed)["verdict"], "wait")
        before, counts = self.path().read_bytes(), self.counts()
        self.assertEqual(self.assess()["verdict"], "wait")
        self.assertEqual(self.path().read_bytes(), before)
        self.assertEqual(self.counts(), counts)

    def test_missing_owner_cannot_overwrite_existing_selected_artifact(self):
        self.assertEqual(self.assess()["verdict"], "now")
        before, counts = self.path().read_bytes(), self.counts()
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        with patch.object(T, "_fabric_owner", side_effect=ImportError("synthetic optional owner absent")):
            result = T.run("NVDA", entry_signal={"stop": 100.0},
                           tech={"rsi14": 55.0, "pct_vs_50dma": 2.0}, asof=self.day)
        self.assertEqual(result["verdict"], "wait")
        self.assertEqual(self.path().read_bytes(), before)
        self.assertEqual(self.counts(), counts)


    def test_native_pool_uses_same_portfolio_owner_and_retains_actual_serving_model(self):
        # The incumbent generic native fixture qualifies only 1024 output tokens.
        # This consumer requires 1500; qualify its synthetic recipe at 2048
        # through the real recipe/grant/gateway owners before creating the service.
        import lease_broker
        native = self.native
        native.recipe["output_contract"]["token_bound"] = 2048
        _, native.recipe_digest = lease_broker._application_native_recipe(
            native.recipe, pool="codex-native", model="fixture-native")
        for grant in native.document["application_grants"]:
            if grant["pool"] == "codex-native":
                grant["recipe_digest"] = native.recipe_digest
        native.save()
        native.gateway = native.new_gateway(application_selection_profile=native.profile,
            application_http_recipes=native.http_recipes,
            application_http_accounts=native.http_binding.accounts,
            application_native_recipes=(native.recipe,),
            application_native_accounts={"codex-native": {"account-a", "account-b"}},
            application_native_selection={("codex-native", "fixture-native"): native.selection})
        native.native_binding = native.go.ApplicationNativeBinding(
            recipe=native.recipe, accounts=frozenset({"account-a", "account-b"}),
            preflight=native.compile_native, execute=native.execute_native, selection=native.selection)
        self.configure_portfolio(["codex-native"])
        self.native.native_text = json.dumps({"verdict": "staged_starter", "confidence": 0.7,
                                              "rationale": "The chart supports a starter only."})
        result = self.assess()
        self.assertEqual(result["verdict"], "staged_starter", result)
        self.assertEqual((result["model"], result["served_by"]), ("fixture-native", "codex-native"))
        row = self.document()[T._FABRIC_KEY]["cache"]["entries"][0]
        self.assertEqual(row["receipt"]["application_observation"]["routing"]["pool"], "codex-native")
        self.assertEqual(row["receipt"]["usage"]["usage_state"], "known")
        self.assertTrue(row["receipt"]["close"]["closed"])
        self.assertEqual(self.counts(), (0, 1, 1, 1, 1))
        cost = self.costs()[0]
        self.assertEqual((cost["provider"], cost["model"], cost["cost_basis"]),
                         ("codex-native", "fixture-native", "unknown"))
        self.assertIsNone(cost["est_cost_usd"])
        self.native.document["application_grants"] = []
        self.native.save()
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("repeat credential")):
            self.assertEqual(self.assess(), result)
        self.assertEqual(self.counts(), (0, 1, 1, 1, 1))
