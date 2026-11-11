"""Public US runner -> real portfolio AUTO factory/client -> A/B -> real tools/settlement.

Only provider responses and market/time inputs are synthetic. Operation persistence,
tool normalization, paper queue/receipts, global and book accounting remain real.
"""
from __future__ import annotations

import asyncio
import copy
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch

from brain import autonomous_mcp, cost_guard, decision_submission, fabric_portfolio as F
from brain import portfolio_learning, runlog
from bot import autonomous, settle
from portfolio import paper_account, registry

_spec = importlib.util.spec_from_file_location("_us_portfolio_fixture",
    Path(__file__).with_name("test_technician_fabric_composition.py"))
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)
_auto = _fixture._auto


def call(name, args, ident):
    return {"id": ident, "type": "function", "function": {
        "name": name, "arguments": json.dumps(args, allow_nan=False)}}


def packet(text="The dated dashboard evidence supports this paper target.", calls=()):
    message = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = list(calls)
    return {"model": "fixture-model", "choices": [{"index": 0, "message": message,
        "finish_reason": "tool_calls" if calls else "stop"}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7}}


def submission(holdings=None):
    return {"holdings": [] if holdings is None else holdings,
            "summary": "Maintain the explicit paper target using dated evidence.",
            "exit_decisions": [], "falsifiers": ["A verified change in the dated evidence."],
            "evidence_planes": ["macro"], "source_provenance": ["fixture:dated-market-packet"],
            "expected_failure_mode": "The dated evidence can become stale.",
            "risk_posture": "normal", "cash_rationale": "Preserve paper capital until evidence qualifies.",
            "decision_memo": {"market_frame": "Dated source fixture", "lessons_applied": []}}


class USPortfolioApplicationTests(unittest.TestCase):
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
        self.book_root = (self.root / "mastermind").resolve()
        self.day = "2026-11-06"
        self.run_id = "us-typed-original-1"
        self.start(patch.object(registry, "_ROOT", self.book_root))
        registry.data_dir("autonomous").mkdir(parents=True, exist_ok=True)
        self.start(patch.object(runlog, "_RUNS_DIR", self.book_root / "data/brain/runs"))
        self.start(patch.object(runlog, "_INDEX", runlog._RUNS_DIR / "index.jsonl"))
        self.start(patch.object(runlog, "_PROTOCOL_LOCK_ROOT", self.book_root))
        self.start(patch.object(cost_guard, "_ROOT", self.book_root))
        self.start(patch.object(cost_guard, "_DIR", self.book_root / "data/brain/cost"))
        self.start(patch.object(portfolio_learning, "_ROOT", self.book_root))
        self.start(patch.object(portfolio_learning, "_DIR", self.book_root / "data/portfolio_learning"))
        self.start(patch.dict(portfolio_learning._ACTIVE_PRESENTATIONS, {}, clear=True))
        self.start(patch.object(autonomous, "_ROOT", self.book_root))
        self.start(patch.object(paper_account, "_current_price",
                               side_effect=lambda ticker: {"SPY": 740.0, "NVDA": 210.0}.get(ticker)))
        self.start(patch.object(settle, "is_open", return_value=False))
        self.start(patch.dict(os.environ, {
            "MASTERMIND_PACKET_GATE": "shadow", "MASTERMIND_NIGHTLY_USD_CAP": "0",
            "MM_PROVIDER_APPLICATION_MODE": "shared_fabric",
            "MM_PROVIDER_WORKLOAD_PROFILE": "portfolio_analysis",
            "MACRO_PORTFOLIO_FABRIC_APPLICATION_TOKEN": self.native_module.SERVICE_TOKEN,
        }))
        from brain import cli_bridge
        self.legacy = self.start(patch.object(cli_bridge, "reason", side_effect=AssertionError("native fallback")))
        for grant in self.native.document["application_grants"]:
            grant.update(principal_id="macro_portfolio_fabric",
                         admission_root="service:macro_portfolio_fabric", workloads=["portfolio_analysis"],
                         credential_ref="MACRO_PORTFOLIO_FABRIC_APPLICATION_TOKEN")
            if grant["pool"] in {"go", "bailian"}:
                grant["max_steps"] = F.MAX_STEPS
        self.native.save()
        policy = json.loads(self.native.policy_path.read_text())
        policy["pools"]["bailian"]["model_capabilities"] = {
            "qwen3.8-flash": {"tools": True, "vision": False}}
        self.native.policy_path.write_text(json.dumps(policy))
        self.portfolio_base = replace(
            self.owner._APPLICATION_FABRIC_TRANSPORTS["native_fabric_macro_portfolio_auto_v1"],
            qualified=True, application_allowed=True)
        self.configure_portfolio(["go"])
        self.plans = []
        self.refusals = []
        self.persistence_errors = []
        original_save = runlog.portfolio_save
        def save(doc):
            try:
                return original_save(doc)
            except BaseException as exc:
                self.persistence_errors.append((type(exc).__name__, str(exc)))
                raise
        self.start(patch.object(runlog, "portfolio_save", side_effect=save))
        original_refuse = self.transport._refuse
        def refuse(*args, **kwargs):
            self.refusals.append((args[0] if args else "default", kwargs.get("unknown", False)))
            return original_refuse(*args, **kwargs)
        self.start(patch.object(self.transport, "_refuse", side_effect=refuse))
        original_failure = self.shared.fabric_failure
        def failure(provider, exc):
            self.refusals.append(("underlying", type(exc).__name__, getattr(exc, "code", None),
                                  getattr(exc, "status_code", None)))
            return original_failure(provider, exc)
        self.start(patch.object(self.shared, "fabric_failure", side_effect=failure))
        self.native.on_upstream = self.upstream
        self.native.response = packet()

    def upstream(self):
        if self.plans:
            self.native.response = self.plans.pop(0)

    def configure_portfolio(self, pools):
        import yaml
        native = self.native
        scope = {"schema": "mastermind.application_route_scope.v1", "pools": sorted(pools)}
        service = native.go.ApplicationServiceBinding(
            "macro_portfolio_fabric", "vps", "portfolio_analysis",
            "MACRO_PORTFOLIO_FABRIC_APPLICATION_TOKEN", self.native_module.SERVICE_TOKEN,
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
            qualification_ref="fixture:us-typed-portfolio-actual-owners", qualified_until=time.time()+3600)
        document = json.loads(self.originals[self.config_paths[0]])
        startup = self.owner._APPLICATION_FABRIC_TRANSPORTS["native_fabric_application_auto_v1"]
        startup_row = {key: getattr(startup, key) for key in self.owner._APPLICATION_IDENTITY_FIELDS}
        startup_row.update(transport_id="native_fabric_application_auto_v1", route_scope=scope,
            enabled=True, application_allowed=True, qualification=self.owner.PROFILE_QUALIFIED_CANARY,
            qualification_ref="fixture:us-typed-host-selection", qualified_until=time.time()+3600)
        document["application_fabric_modes"] = {"shared_fabric": startup_row, "macro_portfolio_fabric": row}
        self.config_paths[0].write_text(json.dumps(document))
        self.config_paths[1].write_text(yaml.safe_dump({"capabilities": [{
            "capability_id": selected.capability_id, "secret_ref": selected.secret_ref,
            "kill_state": "active", "allowed_lanes": [F.lane(book) for book in
                getattr(self, "books", ("autonomous",))]}]}))

    def run_book(self, **kwargs):
        return autonomous.run_autonomous(self.day, run_id=self.run_id, **kwargs)

    def original(self):
        return runlog.portfolio_lookup(self.run_id)

    def counts(self):
        return (len(self.native.posts), len(self.native.dispatches),
                len(self.native.rows("application_requests")), len(self.costs()), len(self.closes))

    def arrange_submission(self, payload=None, *, read=True):
        self.plans = ([packet(None, [call("mcp__desk__get_my_book", {}, "read-1")])] if read else []) + [
            packet(None, [call("mcp__desk__submit_book", payload or submission(), "submit-1")]),
            packet()]

    def test_public_runner_reads_submits_normalizes_and_queues_one_original(self):
        self.arrange_submission()
        result = self.run_book()
        self.assertEqual(result.get("target_status"), "queued", {"out": result, "refusals": self.refusals, "persistence": self.persistence_errors})
        self.assertTrue(result["decided"])
        self.assertTrue(result["decision_effective"])
        self.assertEqual(result["brain"]["run_id"], self.run_id)
        doc = self.original()["state"]
        self.assertEqual(doc["phase"], "complete", {
            "phase": doc["phase"], "brain_error": doc.get("brain", {}).get("error"),
            "states": [x["state"] for x in doc["steps"]], "counts": self.counts(),
            "refusals": self.refusals, "persistence": self.persistence_errors})
        self.assertEqual(doc["close"], F._CLOSED)
        normalized = doc["tools"][1]["submission"]["payload"]
        self.assertEqual(normalized["schema"], "mastermind.target_book.v2")
        self.assertEqual(normalized["_fabric_submission"]["run_id"], self.run_id)
        self.assertEqual(self.counts(), (3, 0, 3, 3, 1))
        self.assertEqual(len(self.native.rows("leases")), 1)
        turn = self.native.rows("application_turns")[0]
        self.assertEqual((turn["principal_id"], turn["workload"]), (F.SERVICE, F.WORKLOAD))
        self.assertEqual(doc["brain"]["usage"]["input_tokens"], 33)
        costs = cost_guard._strict_cost(self.day)[1]["autonomous"]
        self.assertEqual(costs["input_tokens"], 33)
        self.assertIsNone(costs["fabric_operations"][self.run_id]["cost_usd"])
        self.assertEqual(len(costs["fabric_operations"]), 1)
        raw = runlog.canonical(doc)
        self.assertNotIn(b"MACRO_PORTFOLIO_FABRIC_APPLICATION_TOKEN", raw)
        self.assertNotIn(b"account-a", raw)
        self.assertNotIn("_fabric_portfolio", json.dumps(runlog.read_run(self.run_id)))
        self.assertNotIn("_fabric_portfolio", json.dumps(runlog.list_runs()))
        public = runlog.read_run(self.run_id)
        self.assertEqual(public["n_steps"], 5)
        self.assertEqual(public["projection_revision"], self.original()["revision"])
        self.assertEqual(public["decision_status"], "queued")
        self.assertEqual(runlog.list_runs()[0]["n_steps"], 5)
        self.assertNotIn("Dated source fixture", json.dumps(public))
        self.assertNotIn("APPLICATION CONTRACT", json.dumps(public))
        self.legacy.assert_not_called()

    def test_completed_replay_precedes_selector_credentials_and_new_prices(self):
        self.arrange_submission()
        first = self.run_book()
        self.assertEqual(first.get("target_status"), "queued", {"out": first, "refusals": self.refusals, "persistence": self.persistence_errors})
        before = self.counts()
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("credential replay")), \
             patch.object(autonomous, "_run_brain", side_effect=AssertionError("new brain")), \
             patch.object(paper_account, "_current_price", side_effect=AssertionError("new prices")):
            self.assertEqual(self.run_book(), first)
        self.assertEqual(self.counts(), before)

    def test_green_text_without_submission_does_not_settle(self):
        result = self.run_book()
        self.assertFalse(result["decided"], result)
        self.assertFalse(result["decision_effective"])
        self.assertEqual(result["target_status"], "rejected_no_submission")
        self.assertFalse(paper_account.pending_target_file_exists("autonomous"))
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1), self.refusals)

    def test_invalid_later_call_executes_no_earlier_handler(self):
        self.plans = [packet(None, [
            call("mcp__desk__submit_book", submission(), "submit-1"),
            call("mcp__desk__get_my_book", {"book": "flagship"}, "bad-2")])]
        result = self.run_book()
        self.assertFalse(result["decided"], result)
        self.assertFalse(autonomous_mcp.submission_path().exists())
        self.assertEqual(self.original()["state"]["tools"], [])
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))

    def test_native_plaintext_only_policy_refuses_before_credentials_or_dispatch(self):
        self.configure_portfolio(["codex-native"])
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("credential")):
            self.assertFalse(F.available())
            result = self.run_book()
        self.assertTrue(result["fabric_held"])
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))
        self.assertFalse(runlog._INDEX.exists())

    def test_actual_context_handler_returns_one_correlated_request(self):
        self.plans = [packet(None, [call("mcp__desk__request_context_upgrade",
            {"plane": "fresh_insider_context", "reason": "A dated insider context would resolve this decision gap."},
            "context-1")]), packet()]
        result = self.run_book()
        self.assertFalse(result["decided"])
        doc = self.original()["state"]
        receipt = portfolio_learning.reconcile_context_request(
            {"run_id": self.run_id, "tool_id": "context-1"})
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["request"]["book"], "autonomous")
        self.assertEqual(len(portfolio_learning.context_requests(limit=None)), 1)
        before = (self.counts(), (portfolio_learning._DIR / "context_requests.jsonl").read_bytes())
        self.run_book()
        self.assertEqual((self.counts(), (portfolio_learning._DIR / "context_requests.jsonl").read_bytes()), before)


    def grant_steps(self, maximum):
        for grant in self.native.document["application_grants"]:
            if grant["pool"] in {"go", "bailian"}:
                grant["max_steps"] = maximum
        self.native.save()

    def stock_submission(self):
        from portfolio import instrument_policy
        self.start(patch.object(instrument_policy, "_read_macro_json", side_effect=lambda path: {
            "ticker": "NVDA", "name": "NVIDIA Corporation", "sector": "Technology",
            "security_type": "common_stock"} if path == "stockdata/NVDA.json" else None))
        return submission([{
            "ticker": "NVDA", "action": "add", "conviction": "high",
            "rationale": "Dated fixture evidence supports the paper thesis.",
            "why_now": "The dated evidence cleared the review.",
            "falsifier": "The declared thesis evidence fails.",
            "evidence": ["fixture:dated-market-packet"], "source_provenance": ["fixture:stockdata"],
            "expected_horizon": "one month", "exit_plan": "Exit on the declared falsifier."}])

    def test_accepted_submission_survives_later_real_native_step_limit(self):
        from bridge import build_portfolio
        self.grant_steps(2)
        self.arrange_submission()
        first = self.run_book()
        self.assertEqual(first["target_status"], "queued")
        self.assertTrue(first["fabric_held"])
        self.assertFalse(first["brain"]["ok"])
        before = self.counts()
        with patch.object(F, "_factory", side_effect=AssertionError("rebind")), \
             patch.object(settle, "execute_or_queue", side_effect=AssertionError("new settlement")), \
             patch.object(build_portfolio, "write", side_effect=AssertionError("repeat publication")):
            second = self.run_book()
        self.assertTrue(second["decision_effective"])
        self.assertTrue(second["fabric_held"])
        self.assertEqual(second["paths"], first["paths"])
        self.assertEqual(self.counts(), before)

    def test_late_veto_is_once_per_step_and_keeps_accepted_submission(self):
        from brain import cli_bridge
        self.arrange_submission(read=False)
        vetoes = []
        def veto():
            vetoes.append(1)
            if len(vetoes) == 2:
                raise cli_bridge.ProviderStartRefused("fixture_late_veto")
        result = self.run_book(before_provider_start=veto)
        self.assertEqual(result["target_status"], "queued", result)
        self.assertFalse(result["brain"]["ok"])
        self.assertNotIn("fabric_held", result)
        self.assertEqual(len(vetoes), 2)
        doc = self.original()["state"]
        self.assertEqual([row["state"] for row in doc["steps"]], ["complete", "refused"])
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))
        self.assertEqual(cost_guard._strict_cost(self.day)[1]["autonomous"]["calls"], 1)

    def test_real_stock_normalizer_direct_settlement_and_ack(self):
        self.arrange_submission(self.stock_submission(), read=False)
        with patch.object(settle, "is_open", return_value=True):
            result = self.run_book()
        self.assertEqual(result["target_status"], "executed", result)
        self.assertTrue(result.get("settlement_receipt_acknowledged"), result)
        self.assertTrue(result["decision_effective"])
        self.assertEqual(self.original()["state"]["phase"], "complete")
        self.assertEqual({row["ticker"] for row in result["executed"]}, {"NVDA"})
        self.assertTrue(all(row["shares"] > 0 for row in result["executed"]))
        self.assertEqual(paper_account.pending_settlement_receipts("autonomous"), [])
        archives = list((paper_account._settlement_receipt_dir("autonomous") / "acknowledged").glob("*.json"))
        self.assertEqual(len(archives), 1)
        receipt = runlog.strict_json(runlog.strict_read(archives[0]))
        receipt_fills = paper_account.validated_settlement_receipt_fills(receipt)
        rows = runlog.strict_rows(registry.data_dir("autonomous") / "decisions.jsonl")
        self.assertEqual(rows[0]["settlement_fill_ids"], [row["fill_id"] for row in receipt_fills])
        self.assertTrue(paper_account.settlement_receipt_fills_are_durable(receipt, "autonomous"))
        self.assertEqual([(row["ticker"], row["side"]) for row in result["executed"]],
                         [(row["ticker"], row["side"]) for row in receipt_fills])
        self.assertEqual(self.counts(), (2, 0, 2, 2, 1))

    def test_lost_submit_ack_reconciles_normalized_original_without_new_inference(self):
        self.arrange_submission(read=False)
        real = decision_submission.write_atomic
        def lost_ack(*args, **kwargs):
            real(*args, **kwargs)
            raise OSError("fixture lost submission acknowledgement")
        with patch.object(decision_submission, "write_atomic", side_effect=lost_ack):
            first = self.run_book()
        self.assertTrue(first["fabric_held"])
        self.assertFalse(first["decision_effective"])
        self.assertNotIn("publication", self.original()["state"])
        before = self.counts()
        with patch.object(decision_submission, "normalize", side_effect=AssertionError("renormalize")), \
             patch.object(F, "_factory", side_effect=AssertionError("new provider")):
            recovered = self.run_book()
        self.assertEqual(recovered["target_status"], "queued", recovered)
        self.assertTrue(recovered["decision_effective"])
        self.assertEqual(self.counts(), before)
        self.assertEqual(len(self.original()["state"]["tools"]), 1)
        self.assertEqual(self.original()["state"]["tools"][0]["state"], "complete")

    def test_lost_context_ack_reconciles_one_original_request(self):
        self.plans = [packet(None, [call("mcp__desk__request_context_upgrade",
            {"plane": "fresh_insider_context", "reason": "A dated insider context would resolve this decision gap."},
            "context-lost")])]
        real = portfolio_learning.request_context
        def lost_ack(*args, **kwargs):
            real(*args, **kwargs)
            raise OSError("fixture lost context acknowledgement")
        with patch.object(portfolio_learning, "request_context", side_effect=lost_ack):
            first = self.run_book()
        self.assertTrue(first["fabric_held"])
        before = (self.counts(), (portfolio_learning._DIR / "context_requests.jsonl").read_bytes())
        with patch.object(portfolio_learning, "request_context", side_effect=AssertionError("duplicate request")), \
             patch.object(F, "_factory", side_effect=AssertionError("new provider")):
            recovered = self.run_book()
        self.assertFalse(recovered["decision_effective"])
        self.assertNotIn("fabric_held", recovered)
        self.assertEqual(self.original()["state"]["phase"], "complete")
        self.assertEqual((self.counts(), (portfolio_learning._DIR / "context_requests.jsonl").read_bytes()), before)

    def test_interrupted_queue_callback_repairs_original_partner_once(self):
        self.arrange_submission(read=False)
        with patch.object(autonomous, "_append_decision_log", side_effect=KeyboardInterrupt("fixture callback interruption")):
            with self.assertRaises(KeyboardInterrupt):
                self.run_book()
        self.assertTrue(paper_account.pending_target_file_exists("autonomous"))
        self.assertEqual(self.original()["state"]["phase"], "settlement_intent")
        before = self.counts()
        with patch.object(settle, "execute_or_queue", side_effect=AssertionError("repeat execution")), \
             patch.object(F, "_factory", side_effect=AssertionError("repeat inference")):
            recovered = self.run_book()
        self.assertEqual(recovered["target_status"], "queued", recovered)
        self.assertEqual(self.counts(), before)
        rows = runlog.strict_rows(registry.data_dir("autonomous") / "decisions.jsonl")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["decision_effective"])

    def test_partial_publication_repairs_only_missing_original_component(self):
        from bridge import build_portfolio
        self.arrange_submission(read=False)
        real = build_portfolio._atomic_write_bytes
        def partial(path, encoded):
            if path.name == "portfolio.json":
                raise OSError("fixture before second publication target")
            return real(path, encoded)
        with patch.object(build_portfolio, "_atomic_write_bytes", side_effect=partial):
            first = self.run_book()
        self.assertTrue(first["fabric_held"])
        plan = self.original()["state"]["publication"]
        self.assertEqual(plan["state"], "pending")
        hub_before = Path(plan["paths"]["hub"]).read_bytes()
        before = self.counts()
        repaired = []
        def record(path, encoded):
            repaired.append(path.name)
            return real(path, encoded)
        with patch.object(build_portfolio, "_atomic_write_bytes", side_effect=record), \
             patch.object(build_portfolio, "write", side_effect=AssertionError("new publication")), \
             patch.object(settle, "execute_or_queue", side_effect=AssertionError("new settlement")), \
             patch.object(paper_account, "_current_price", side_effect=AssertionError("new price")):
            recovered = self.run_book()
        self.assertEqual(repaired, ["portfolio.json"])
        self.assertEqual(Path(plan["paths"]["hub"]).read_bytes(), hub_before)
        self.assertEqual(Path(plan["paths"]["site"]).read_bytes(), hub_before)
        self.assertNotIn("fabric_held", recovered)
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.run_book(), recovered)

    def test_publication_lost_ack_uses_exact_readback_without_rewrite(self):
        from bridge import build_portfolio
        self.arrange_submission(read=False)
        real = build_portfolio.write
        def lost_ack(*args, **kwargs):
            real(*args, **kwargs)
            raise OSError("fixture lost publication acknowledgement")
        with patch.object(build_portfolio, "write", side_effect=lost_ack):
            first = self.run_book()
        self.assertTrue(first["fabric_held"])
        before = self.counts()
        with patch.object(build_portfolio, "_atomic_write_bytes", side_effect=AssertionError("rewrite")), \
             patch.object(F, "_factory", side_effect=AssertionError("new provider")):
            recovered = self.run_book()
        self.assertNotIn("fabric_held", recovered)
        self.assertEqual(self.original()["state"]["publication"]["state"], "complete")
        self.assertEqual(self.counts(), before)

    def test_publication_foreign_component_is_held_without_overwriting_either(self):
        from bridge import build_portfolio
        self.arrange_submission(read=False)
        real = build_portfolio._atomic_write_bytes
        def partial(path, encoded):
            if path.name == "portfolio.json":
                raise OSError("fixture interrupted second target")
            return real(path, encoded)
        with patch.object(build_portfolio, "_atomic_write_bytes", side_effect=partial):
            self.run_book()
        paths = self.original()["state"]["publication"]["paths"]
        Path(paths["site"]).write_bytes(b'{"foreign":"publication"}')
        before = {key: Path(path).read_bytes() for key, path in paths.items()}
        with patch.object(build_portfolio, "_atomic_write_bytes", side_effect=AssertionError("overwrite foreign")):
            recovered = self.run_book()
        self.assertTrue(recovered["fabric_held"])
        self.assertEqual({key: Path(path).read_bytes() for key, path in paths.items()}, before)

    def test_cost_lost_ack_is_reconciled_once_at_both_owners(self):
        self.arrange_submission(read=False)
        real = cost_guard.record_fabric
        def lost_ack(*args, **kwargs):
            real(*args, **kwargs)
            raise OSError("fixture lost book-cost acknowledgement")
        with patch.object(cost_guard, "record_fabric", side_effect=lost_ack):
            first = self.run_book()
        self.assertTrue(first["fabric_held"])
        before = self.counts()
        raw = cost_guard._path(self.day).read_bytes()
        recovered = self.run_book()
        self.assertNotIn("fabric_held", recovered)
        self.assertEqual(cost_guard._path(self.day).read_bytes(), raw)
        self.assertEqual(self.counts(), before)

    def test_archive_only_recovery_uses_original_fills_after_lost_final_run_ack(self):
        self.arrange_submission(self.stock_submission(), read=False)
        with patch.object(settle, "is_open", return_value=True), \
             patch.object(F.Session, "finish", side_effect=RuntimeError("fixture lost final run acknowledgement")):
            self.run_book()
        doc = self.original()["state"]
        self.assertEqual(doc["phase"], "settlement_observed")
        self.assertIn("settlement_receipt_id", doc["business"]["result"])
        self.assertEqual(paper_account.pending_settlement_receipts("autonomous"), [])
        before = self.counts()
        with patch.object(settle, "execute_or_queue", side_effect=AssertionError("new execution")), \
             patch.object(settle, "finalize_direct_settlement_receipt", side_effect=AssertionError("archive refinalization")), \
             patch.object(paper_account, "_current_price", side_effect=AssertionError("fresh price")), \
             patch.object(F, "_factory", side_effect=AssertionError("new provider")):
            recovered = self.run_book()
        self.assertEqual(recovered["target_status"], "executed", recovered)
        self.assertTrue(recovered["settlement_receipt_acknowledged"])
        self.assertTrue(recovered["settlement_receipt_finalization"]["archived_original"])
        self.assertEqual(self.counts(), before)

    def test_archive_status_hash_fill_identity_and_known_receipt_must_match(self):
        self.arrange_submission(self.stock_submission(), read=False)
        with patch.object(settle, "is_open", return_value=True), \
             patch.object(F.Session, "finish", side_effect=RuntimeError("fixture lost final run acknowledgement")):
            self.run_book()
        path = registry.data_dir("autonomous") / "decisions.jsonl"
        original = path.read_bytes()
        rows = runlog.strict_rows(path)
        before = self.counts()
        for key, value in (("target_status", "rejected"), ("decision_effective", False),
                           ("target_sha256", "0"*64), ("settlement_receipt_sha256", "0"*64),
                           ("settlement_fill_ids", [])):
            with self.subTest(field=key):
                changed = copy.deepcopy(rows)
                changed[0][key] = value
                path.write_bytes(b"".join(runlog.canonical(row)+b"\n" for row in changed))
                recovered = self.run_book()
                self.assertTrue(recovered["fabric_held"])
                self.assertFalse(recovered["decision_effective"])
        path.write_bytes(original)
        session = F.Session(self.original())
        known = session.state["business"]["result"]["settlement_receipt_id"]
        session.state["business"]["result"]["settlement_receipt_id"] = "0"*64
        session.save()
        self.assertTrue(self.run_book()["fabric_held"])
        session = F.Session(self.original())
        session.state["business"]["result"]["settlement_receipt_id"] = known
        session.save()
        self.assertEqual(self.run_book()["target_status"], "executed")
        self.assertEqual(self.counts(), before)

    def test_rewritten_queue_keeps_original_root_and_required_partner(self):
        self.grant_steps(2)
        self.arrange_submission(self.stock_submission())
        first = self.run_book()
        self.assertTrue(first["fabric_held"])
        self.assertEqual(first["target_status"], "queued", first)
        path = paper_account._pending_target_path("autonomous")
        old = runlog.strict_json(runlog.strict_read(path))
        paper_account.save_pending_target({"NVDA": 0.05}, self.day, portfolio_id="autonomous",
                                          decision_snapshot=old["decision_snapshot"])
        rewritten = path.read_bytes()
        before = self.counts()
        with patch.object(settle, "execute_or_queue", side_effect=AssertionError("new execution")):
            self.assertEqual(self.run_book()["target_status"], "queued")
        queue = json.loads(rewritten)
        for key, value in (("accepted_target_sha256", "0"*64), ("decision_log_required", False),
                           ("target_lineage", [])):
            with self.subTest(field=key):
                altered = copy.deepcopy(queue)
                altered["decision_snapshot"][key] = value
                path.write_bytes(runlog.canonical(altered))
                recovered = self.run_book()
                self.assertTrue(recovered["fabric_held"])
                self.assertIn("conflict" if key != "target_lineage" else "lineage", recovered["skipped"])
        path.write_bytes(rewritten)
        self.assertEqual(self.counts(), before)

    def test_manual_wait_cancellation_keeps_original_thread_and_book_lock(self):
        from types import SimpleNamespace
        from app.main import app
        from control_plane import locks, run_ledger
        entered, release = threading.Event(), threading.Event()
        held, receipts = [], []
        class Lock:
            def __enter__(self):
                held.append(True)
                return self
            def __exit__(self, *_):
                held.pop()
        self.start(patch.object(locks, "acquire_or_log", return_value=Lock()))
        self.start(patch.object(run_ledger, "start_run", return_value=SimpleNamespace(run_id=self.run_id)))
        self.start(patch.object(run_ledger, "end_run", side_effect=lambda *a, **k: receipts.append((a, k))))
        def wait_original():
            entered.set()
            if not release.wait(5):
                raise AssertionError("fixture original was not released")
            self.upstream()
        self.native.on_upstream = wait_original
        endpoint = next(route.endpoint for route in app.routes
                        if getattr(route, "path", None) == "/api/autonomous/run")
        async def exercise():
            task = asyncio.create_task(endpoint(force=False, wait=True))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                task.cancel()
                await asyncio.sleep(0.05)
                self.assertFalse(task.done())
                self.assertEqual(held, [True])
            finally:
                release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        asyncio.run(exercise())
        self.assertEqual(held, [])
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0][0][1], "error")
        self.assertEqual(self.original()["state"]["run_id"], self.run_id)
        self.assertEqual(self.original()["state"]["phase"], "complete")
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))

    def test_health_policy_is_pure_and_preserves_scheduler_failure(self):
        from app.main import app
        from app import auth
        from brain import client, codex_bridge
        endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/health")
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("health credential")), \
             patch.object(client, "available", side_effect=AssertionError("native readiness")), \
             patch.object(codex_bridge, "available", side_effect=AssertionError("Codex readiness")), \
             patch.object(auth, "serve_only", return_value=False), \
             patch.object(app.state, "scheduler", None, create=True):
            result = endpoint()
        self.assertEqual(result["reasoning_backend"], "fabric")
        self.assertEqual(result["reasoning_policy_scope"], "typed_portfolio_policy_only")
        self.assertEqual(set(result["scheduled_portfolio_reasoning_by_book"]), {"autonomous", "china", "hk"})
        self.assertTrue(result["scheduled_portfolio_reasoning_by_book"]["autonomous"]["eligible"])
        self.assertFalse(result["scheduled_portfolio_reasoning_by_book"]["china"]["eligible"])
        self.assertFalse(result["scheduled_portfolio_reasoning_available"])
        self.assertTrue(result["reasoning_policy_evidence"]["eligible"])
        self.assertFalse(result["reasoning_policy_evidence"]["live_provider_verified"])
        self.assertFalse(result["scheduled_runtime_ok"])
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))

    def test_cron_forwards_original_job_id_and_suppresses_whole_book_retry(self):
        from types import SimpleNamespace
        from app import scheduler
        from control_plane import locks
        class Lock:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
        receipts = []
        with patch.object(locks, "acquire_or_log", return_value=Lock()), \
             patch.object(scheduler, "_ledger_start", return_value=SimpleNamespace(run_id=self.run_id)), \
             patch.object(scheduler, "_ledger_end", side_effect=lambda *a, **k: receipts.append((a, k))), \
             patch.object(scheduler, "_post_mark_forward_evaluation") as post:
            scheduler._autonomous_job()
        self.assertEqual(len(receipts), 1)
        self.assertEqual(self.original()["state"]["run_id"], self.run_id)
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))
        self.assertEqual(post.call_count, 1)


    def test_bailian_responses_tools_use_the_same_portfolio_owner(self):
        self.configure_portfolio(["bailian"])
        prepare = self.native.bailian_driver.prepare_request
        def inspect_prepare(logical):
            try:
                return prepare(logical)
            except Exception as exc:
                self.refusals.append(("bailian_compile", type(exc).__name__, str(exc)[:160]))
                raise
        self.start(patch.object(self.native.bailian_driver, "prepare_request", side_effect=inspect_prepare))
        roster, _ = F.catalog()
        diagnostic = F._normalized_request({"system": "", "messages": [{"role": "user", "content": "fixture"}],
                                           "tools": roster, "max_tokens": F.MAX_TOKENS}, "fixture-preflight")
        prepare(dict(diagnostic, model="qwen3.8-flash"))  # Pure compiler: no provider or admission.
        def response(outputs):
            return {"id": "fixture-bailian", "model": "qwen3.8-flash", "status": "completed",
                    "output": outputs, "usage": {"input_tokens": 11, "output_tokens": 7}}
        self.plans = [
            response([{"type": "function_call", "call_id": "submit-bailian",
                       "name": "mcp__desk__submit_book", "arguments": json.dumps(submission())}]),
            response([{"type": "message", "role": "assistant",
                       "content": [{"type": "output_text", "text": "The explicit paper submission is complete."}]}])]
        result = self.run_book()
        self.assertEqual(result["target_status"], "queued", {
            "target_status": result["target_status"], "brain": result["brain"],
            "counts": self.counts(), "refusals": self.refusals, "persistence": self.persistence_errors})
        self.assertNotIn("fabric_held", result)
        doc = self.original()["state"]
        self.assertEqual(doc["brain"]["model"], "qwen3.8-flash")
        self.assertEqual(doc["brain"]["provider"], "bailian")
        self.assertTrue(all(step["observation"]["routing"]["pool"] == "bailian" for step in doc["steps"]))
        self.assertEqual(self.counts(), (2, 0, 2, 2, 1))

    def test_mixed_native_and_go_scope_excludes_plaintext_for_real_tools(self):
        self.configure_portfolio(["codex-native", "go"])
        self.arrange_submission(read=False)
        result = self.run_book()
        self.assertEqual(result["target_status"], "queued", result)
        self.assertNotIn("fabric_held", result)
        self.assertEqual(self.native.compilations, [])
        self.assertTrue(all(step["observation"]["routing"]["pool"] == "go"
                            for step in self.original()["state"]["steps"]))
        self.assertEqual(self.counts(), (2, 0, 2, 2, 1))

    def test_truncated_provider_answer_cannot_execute_saved_tools(self):
        self.plans = [packet(None, [call("mcp__desk__submit_book", submission(), "truncated-submit")])]
        self.plans[0]["choices"][0]["finish_reason"] = "length"
        result = self.run_book()
        self.assertFalse(result["decision_effective"])
        self.assertFalse(autonomous_mcp.submission_path().exists())
        self.assertEqual(self.original()["state"]["tools"], [])
        before = self.counts()
        self.run_book()
        self.assertEqual(self.counts(), before)

    def test_last_turn_tool_request_is_refused_before_any_handler(self):
        self.arrange_submission(read=False)
        with patch.object(autonomous, "_MAX_TURNS", 1):
            result = self.run_book()
        self.assertFalse(result["decision_effective"])
        self.assertFalse(autonomous_mcp.submission_path().exists())
        self.assertEqual(self.original()["state"]["steps"][0]["state"], "rejected")
        self.assertEqual(self.original()["state"]["tools"], [])
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))

    def test_unresolved_settlement_owner_does_not_release_original_identity(self):
        self.arrange_submission(read=False)
        real = paper_account.recover_paper_transaction
        def unavailable(*args, **kwargs):
            raise OSError("fixture unreadable existing transaction")
        # Scope the fault at the actual execute_or_queue owner boundary; input
        # preparation still uses the existing normalizer and account readers.
        real_execute = settle.execute_or_queue
        def execute(*args, **kwargs):
            with patch.object(paper_account, "recover_paper_transaction", side_effect=unavailable):
                return real_execute(*args, **kwargs)
        with patch.object(settle, "execute_or_queue", side_effect=execute):
            result = self.run_book()
        self.assertTrue(result["fabric_held"])
        self.assertFalse(result["decision_effective"])
        self.assertEqual(self.original()["state"]["business"]["result"]["skipped"],
                         "settlement_recovery_failed")
        before = self.counts()
        with patch.object(F, "_factory", side_effect=AssertionError("new provider")):
            different = autonomous.run_autonomous("2026-11-07", force=True, run_id="new-id")
        self.assertEqual(different["run_id"], self.run_id)
        self.assertTrue(different["fabric_held"])
        self.assertEqual(self.counts(), before)

    def test_callback_and_rollback_error_remains_held_then_reconciles_original_queue(self):
        self.arrange_submission(read=False)
        original_unlink = Path.unlink
        def fail_unlink(path, *args, **kwargs):
            if path == paper_account._pending_target_path("autonomous"):
                raise OSError("fixture queue rollback failed")
            return original_unlink(path, *args, **kwargs)
        with patch.object(autonomous, "_append_decision_log", side_effect=OSError("fixture callback failed")), \
             patch.object(Path, "unlink", fail_unlink):
            result = self.run_book()
        self.assertTrue(result["fabric_held"])
        self.assertFalse(result["decision_effective"])
        self.assertTrue(paper_account.pending_target_file_exists("autonomous"))
        before = self.counts()
        with patch.object(settle, "execute_or_queue", side_effect=AssertionError("repeat execution")):
            recovered = self.run_book()
        self.assertEqual(recovered["target_status"], "queued", recovered)
        self.assertEqual(self.counts(), before)


    def test_receipt_ack_supersedes_pending_queue_publication_without_replaying_it(self):
        from bridge import build_portfolio
        self.grant_steps(2)
        self.arrange_submission(self.stock_submission())
        real = build_portfolio._atomic_write_bytes
        def partial(path, encoded):
            if path.name == "portfolio.json":
                raise OSError("fixture queued publication interrupted")
            return real(path, encoded)
        with patch.object(build_portfolio, "_atomic_write_bytes", side_effect=partial):
            first = self.run_book()
        self.assertTrue(first["fabric_held"])
        self.assertEqual(self.original()["state"]["publication"]["state"], "pending")
        with patch.object(settle, "is_open", return_value=True):
            settled = settle.settle_open("autonomous", self.day,
                _open_price_fn=lambda ticker: ({"NVDA": 210.0, "SPY": 740.0}.get(ticker), "fixture_open"))
        self.assertTrue(settled.get("receipt_acknowledged"), settled)
        paths = self.original()["state"]["publication"]["paths"]
        before_bytes = {key: Path(path).read_bytes() for key, path in paths.items()}
        before = self.counts()
        with patch.object(build_portfolio, "_atomic_write_bytes", side_effect=AssertionError("old publication replay")), \
             patch.object(settle, "execute_or_queue", side_effect=AssertionError("new settlement")):
            recovered = self.run_book()
        self.assertEqual(recovered["target_status"], "executed", recovered)
        self.assertTrue(recovered["fabric_held"])  # The original later inference remains unknown.
        plan = self.original()["state"]["publication"]
        self.assertEqual(plan["state"], "superseded")
        self.assertEqual(plan["superseded_by_receipt"], settled["transaction_id"])
        self.assertEqual({key: Path(path).read_bytes() for key, path in paths.items()}, before_bytes)
        self.assertEqual(self.counts(), before)

    def test_each_deliberate_submission_keeps_its_receipt_and_latest_accepted_target(self):
        latest = self.stock_submission()
        self.plans = [packet(None, [call("mcp__desk__submit_book", submission(), "submit-first")]),
                      packet(None, [call("mcp__desk__submit_book", latest, "submit-latest")]), packet()]
        result = self.run_book()
        self.assertEqual(result["target_status"], "queued", result)
        doc = self.original()["state"]
        self.assertEqual(len(doc["tools"]), 2)
        self.assertEqual(doc["tools"][0]["submission"]["payload"]["holdings"], [])
        self.assertEqual(doc["tools"][1]["submission"]["payload"]["holdings"][0]["ticker"], "NVDA")
        self.assertEqual(doc["business"]["target"], {"NVDA": 0.15})
        for tool in doc["tools"]:
            self.assertEqual(tool["submission_receipt"]["tool_id"], tool["id"])
        self.assertEqual(doc["tools"][1]["submission"]["before_sha256"],
                         doc["tools"][0]["submission_receipt"]["written_sha256"])
        self.assertEqual(self.counts(), (3, 0, 3, 3, 1))

    def test_recovery_rejects_weaker_response_history_usage_or_order_semantics(self):
        self.arrange_submission()
        self.run_book()
        original = self.original()
        def truncated(doc):
            doc["state"]["steps"][0]["response"]["stop_reason"] = "max_tokens"
        def too_many(doc):
            frozen = doc["state"]["frozen"]
            frozen["max_turns"] = 1
            frozen["digest"] = runlog.digest({key: value for key, value in frozen.items() if key != "digest"})
        def changed_request(doc):
            step = doc["state"]["steps"][1]
            step["request"]["messages"][0]["content"] += "changed"
            step["request_digest"] = self.transport._auto_request_digest(step["request"])
        def wrong_usage(doc):
            doc["state"]["steps"][0]["observed_usage"]["input_tokens"] += 1
        def reordered(doc):
            doc["state"]["tools"].reverse()
        def pending_complete(doc):
            doc["state"]["tools"][-1]["state"] = "pending"
        before = self.counts()
        for mutate in (truncated, too_many, changed_request, wrong_usage, reordered, pending_complete):
            with self.subTest(case=mutate.__name__):
                changed = copy.deepcopy(original)
                mutate(changed)
                with self.assertRaises(runlog.PortfolioRunError):
                    F._validate(changed)
        self.assertEqual(self.counts(), before)

    def test_unqualified_selected_policy_refuses_without_credentials_or_new_original(self):
        selected = self.owner._APPLICATION_FABRIC_TRANSPORTS["native_fabric_macro_portfolio_auto_v1"]
        with patch.dict(self.owner._APPLICATION_FABRIC_TRANSPORTS,
                        {"native_fabric_macro_portfolio_auto_v1": replace(selected, qualified=False)}), \
             patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("credential")):
            self.assertFalse(F.readiness()["eligible"])
            result = self.run_book()
        self.assertTrue(result["fabric_held"])
        self.assertFalse(runlog._INDEX.exists())
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))



if __name__ == "__main__":
    unittest.main()
