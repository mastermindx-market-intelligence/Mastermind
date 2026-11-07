"""Regional public runners through the real shared AUTO, HTTP and paper owners.

Provider responses, market/FX inputs and feed snapshots are synthetic. The native
router, leases, tools, normalizer, runlog, costs, queue and publication stay real.
"""
from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from brain import (autonomous_mcp, china_mcp, hk_mcp, cost_guard, decision_submission,
                   fabric_portfolio as F, portfolio_learning, runlog)
from bot import autonomous, china, hk, overnight, settle
from portfolio import fx, instrument_policy, paper_account, registry

_spec = importlib.util.spec_from_file_location("_regional_us_fixture",
    Path(__file__).with_name("test_fabric_portfolio_composition.py"))
_us = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_us)
call, packet, submission = _us.call, _us.packet, _us.submission


class RegionalCases:
    books = ("autonomous", "china", "hk")
    start, configure, costs = _us.USPortfolioApplicationTests.start, _us.USPortfolioApplicationTests.configure, _us.USPortfolioApplicationTests.costs
    configure_portfolio, upstream, counts = _us.USPortfolioApplicationTests.configure_portfolio, _us.USPortfolioApplicationTests.upstream, _us.USPortfolioApplicationTests.counts

    @classmethod
    def setUpClass(cls):
        _us.USPortfolioApplicationTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        _us.USPortfolioApplicationTests.tearDownClass.__func__(cls)

    def setUp(self):
        _us.USPortfolioApplicationTests.setUp(self)
        from data_layer import feed_health, yahoo_feed
        from brain import translate
        self.run_id = self.book + "-typed-original-1"
        self.bot = {"china": china, "hk": hk}[self.book]
        self.mcp = {"china": china_mcp, "hk": hk_mcp}[self.book]
        self.ticker = {"china": "600519.SS", "hk": "0700.HK"}[self.book]
        self.other = "hk" if self.book == "china" else "china"
        self.currency = {"china": "CNY", "hk": "HKD"}[self.book]
        self.benchmark = {"china": "000300.SS", "hk": "^HSI"}[self.book]
        for book, owner in (("china", china), ("hk", hk)):
            registry.data_dir(book).mkdir(parents=True, exist_ok=True)
            self.start(patch.object(owner, "_ROOT", self.book_root))
        self.start(patch.object(translate, "_ROOT", self.book_root))
        self.start(patch.object(translate, "_CACHE_PATH", self.book_root / "data/brain/translations.json"))
        self.start(patch.object(translate, "_cache_mem", None))
        self.start(patch.object(translate, "_cache_mtime", None))
        self.feed = self.start(patch.object(feed_health, "status", return_value={
            "status": "ok", "asof": self.day, "source": "fixture:regional-feed"}))
        self.start(patch.object(yahoo_feed, "warm", return_value=None))
        self.start(patch.object(fx, "rate_per_usd", side_effect=lambda currency, **kwargs:
                               {"USD": 1.0, "CNY": 7.2, "HKD": 7.8}[currency]))
        self.start(patch.object(paper_account, "_current_price", side_effect=lambda ticker: {
            "600519.SS": 200.0, "0700.HK": 50.0, "000300.SS": 600.0, "^HSI": 3000.0,
            "NVDA": 210.0, "SPY": 740.0}.get(ticker)))
        def market_artifact(path):
            for book, ticker, directory in (("china", "600519.SS", "chinastockdata"),
                                            ("hk", "0700.HK", "hkstockdata")):
                if path == "marketdata/" + book + "_heatmap.json":
                    return {"market": book, "map_type": "stocks", "stockdata_dir": directory,
                            "n_tiles": 1, "tiles": [{"t": ticker, "name": "Fixture Company",
                                                   "security_type": "common_stock"}]}
            return None
        self.start(patch.object(instrument_policy, "_read_macro_json", side_effect=market_artifact))

    def run_book(self, **kwargs):
        return getattr(self.bot, "run_" + self.book)(self.day, run_id=self.run_id, **kwargs)

    def original(self):
        return runlog.portfolio_lookup(self.run_id, book=self.book)

    def arrange_submission(self, payload=None, *, read=True):
        prefix = "mcp__" + self.book + "__"
        self.plans = ([packet(None, [call(prefix+"get_my_book", {}, "read-1")])] if read else []) + [
            packet(None, [call(prefix+"submit_book", payload or submission(), "submit-1")]), packet()]

    def stock_submission(self, ticker=None):
        return submission([{
            "ticker": ticker or self.ticker, "action": "add", "conviction": "high", "weight": 0.99,
            "rationale": "Dated regional fixture supports this paper thesis.",
            "why_now": "The dated regional source cleared review.",
            "falsifier": "The declared regional evidence fails.",
            "evidence": ["fixture:regional-source"], "source_provenance": ["fixture:stock-heatmap"],
            "expected_horizon": "one month", "exit_plan": "Exit on the declared falsifier."}])

    def test_exact_catalog_and_real_go_read_submit_queue_preserve_book(self):
        declarations, handlers = F.catalog(self.book)
        self.assertEqual(len(declarations), 13 if self.book == "china" else 12)
        self.assertEqual({row["name"] for row in declarations}, set(handlers))
        self.assertTrue(all(name.startswith("mcp__"+self.book+"__") for name in handlers))
        self.assertFalse({"WebSearch", "WebFetch", "Task"} & set(handlers))
        self.arrange_submission(self.stock_submission())
        out = self.run_book()
        self.assertEqual(out.get("target_status"), "queued", {
            "out": out, "refusals": self.refusals, "persistence": self.persistence_errors})
        self.assertTrue(out["decision_effective"])
        state = self.original()["state"]
        self.assertEqual((state["book"], state["phase"]), (self.book, "complete"))
        payload = state["tools"][1]["submission"]["payload"]
        self.assertEqual(payload["_fabric_submission"]["book"], self.book)
        self.assertAlmostEqual(payload["holdings"][0]["weight"], 0.18)
        self.assertIn("regional", json.dumps(payload))
        queued = paper_account.load_pending_target(self.book)
        self.assertEqual(queued["portfolio_id"], self.book)
        self.assertEqual(set(queued["target"]), {self.ticker})
        self.assertAlmostEqual(queued["target"][self.ticker], 0.18)
        published = json.loads(Path(state["publication"]["paths"]["site"]).read_text())
        self.assertEqual((published["portfolio_id"], published["currency"], published["benchmark"]),
                         (self.book, self.currency, self.benchmark))
        self.assertEqual(out["nav"], 1000000.0)
        self.assertFalse(paper_account.pending_target_file_exists(self.other))
        self.assertEqual(self.counts(), (3, 0, 3, 3, 1))
        self.assertEqual(len(self.native.rows("leases")), 1)
        cost = cost_guard._strict_cost(self.day)[1][self.book]
        self.assertEqual(cost["input_tokens"], 33)
        self.assertEqual(list(cost["fabric_operations"]), [self.run_id])
        self.assertEqual(runlog.read_run(self.run_id)["kind"], self.book)
        self.legacy.assert_not_called()

    def test_real_bailian_tools_use_same_regional_owners(self):
        self.configure_portfolio(["bailian"])
        def response(outputs):
            return {"id": "fixture-bailian", "model": "qwen3.8-flash", "status": "completed",
                    "output": outputs, "usage": {"input_tokens": 11, "output_tokens": 7}}
        self.plans = [
            response([{"type": "function_call", "call_id": "submit-bailian",
                       "name": F.tool_name(self.book, "submit_book"),
                       "arguments": json.dumps(submission())}]),
            response([{"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": "The regional paper submission is complete."}]}])]
        out = self.run_book()
        self.assertEqual(out.get("target_status"), "queued", {"out": out, "refusals": self.refusals})
        self.assertFalse(out.get("fabric_held"))
        state = self.original()["state"]
        self.assertEqual(state["brain"]["provider"], "bailian")
        self.assertTrue(all(step["observation"]["routing"]["pool"] == "bailian" for step in state["steps"]))
        self.assertEqual(self.counts(), (2, 0, 2, 2, 1))

    def test_direct_settlement_has_regional_currency_and_original_ack(self):
        self.arrange_submission(self.stock_submission(), read=False)
        with patch.object(settle, "is_open", return_value=True):
            out = self.run_book()
        self.assertEqual(out.get("target_status"), "executed", out)
        self.assertTrue(out.get("settlement_receipt_acknowledged"), out)
        self.assertTrue(out["decision_effective"])
        self.assertEqual({row["ticker"] for row in out["executed"]}, {self.ticker})
        native_price = {"china": 1440.0, "hk": 390.0}[self.book]
        self.assertTrue(all(row["price"] == native_price for row in out["executed"]))
        archives = list((paper_account._settlement_receipt_dir(self.book) / "acknowledged").glob("*.json"))
        self.assertEqual(len(archives), 1)
        receipt = runlog.strict_json(runlog.strict_read(archives[0]))
        self.assertTrue(paper_account.settlement_receipt_fills_are_durable(receipt, self.book))
        self.assertEqual(paper_account.pending_settlement_receipts(self.book), [])
        self.assertEqual(self.counts(), (2, 0, 2, 2, 1))

    def test_archived_settlement_recovers_without_other_book_or_fresh_price(self):
        self.arrange_submission(self.stock_submission(), read=False)
        with patch.object(settle, "is_open", return_value=True), \
             patch.object(F.Session, "finish", side_effect=RuntimeError("fixture final run ACK lost")):
            self.run_book()
        self.assertEqual(self.original()["state"]["phase"], "settlement_observed")
        self.assertEqual(paper_account.pending_settlement_receipts(self.book), [])
        before = self.counts()
        with patch.object(settle, "execute_or_queue", side_effect=AssertionError("repeat execution")), \
             patch.object(settle, "finalize_direct_settlement_receipt", side_effect=AssertionError("archive refinalization")), \
             patch.object(paper_account, "_current_price", side_effect=AssertionError("fresh price")), \
             patch.object(F, "_factory", side_effect=AssertionError("new provider")):
            recovered = self.run_book()
        self.assertEqual(recovered.get("target_status"), "executed", recovered)
        self.assertTrue(recovered["settlement_receipt_acknowledged"])
        self.assertTrue(recovered["settlement_receipt_finalization"]["archived_original"])
        self.assertEqual(recovered["portfolio_id"], self.book)
        self.assertEqual(self.counts(), before)

    def test_saved_state_cannot_detach_entry_or_relabel_completed_output(self):
        self.arrange_submission(read=False)
        self.assertEqual(self.run_book()["target_status"], "queued")
        doc = self.original()
        for fault in ("missing_entry", "entry_business", "inaugural", "out_book", "out_date"):
            altered = copy.deepcopy(doc)
            state = altered["state"]
            if fault == "missing_entry":
                state.pop("entry_context")
            elif fault == "entry_business":
                state["business"]["out"]["feed_health"] = {"status": "forged"}
                state["business"]["digest"] = runlog.digest({
                    k: v for k, v in state["business"].items() if k not in {"digest", "result"}})
            elif fault == "inaugural":
                state["frozen"]["inaugural"] = not state["entry_context"]["inaugural"]
                state["frozen"]["digest"] = runlog.digest({
                    k: v for k, v in state["frozen"].items() if k != "digest"})
            elif fault == "out_book":
                state["out"]["portfolio_id"] = self.other
            else:
                state["out"]["asof"] = "2026-11-07"
            with self.subTest(fault=fault), self.assertRaises(runlog.PortfolioRunError):
                F._validate(altered)
        self.assertEqual(self.original(), doc)

    def test_mixed_invalid_foreign_tool_batch_executes_nothing(self):
        self.plans = [packet(None, [
            call(F.tool_name(self.book, "submit_book"), submission(), "valid"),
            call(F.tool_name(self.other, "submit_book"), submission(), "foreign")])]
        out = self.run_book()
        self.assertFalse(out["decision_effective"])
        self.assertFalse(self.mcp.submission_path().exists())
        self.assertEqual(self.original()["state"]["tools"], [])
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))

    def test_real_normalizer_rejects_off_venue_stock_without_latent_buy(self):
        self.arrange_submission(self.stock_submission("NVDA"), read=False)
        out = self.run_book()
        self.assertEqual(out.get("target_status"), "queued", out)
        payload = self.original()["state"]["tools"][0]["submission"]["payload"]
        self.assertEqual(payload["holdings"], [])
        self.assertIn("off_venue", json.dumps(payload["submission_audit"]))
        self.assertEqual(paper_account.load_pending_target(self.book)["target"], {})
        self.assertFalse(paper_account.pending_target_file_exists("autonomous"))

    def test_text_without_submission_is_distinct_from_explicit_cash(self):
        out = self.run_book()
        self.assertEqual(out.get("target_status"), "rejected_no_submission", out)
        self.assertFalse(out["decision_effective"])
        self.assertFalse(paper_account.pending_target_file_exists(self.book))
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))

    def test_lost_submission_ack_recovers_frozen_feed_and_payload_once(self):
        self.arrange_submission(self.stock_submission(), read=False)
        real = decision_submission.write_atomic
        def lost_ack(*args, **kwargs):
            real(*args, **kwargs)
            raise OSError("fixture submission ACK lost")
        with patch.object(decision_submission, "write_atomic", side_effect=lost_ack):
            first = self.run_book()
        self.assertTrue(first["fabric_held"], first)
        saved = copy.deepcopy(self.original()["state"]["entry_context"])
        before = self.counts()
        with patch.object(decision_submission, "normalize", side_effect=AssertionError("renormalize")), \
             patch.object(F, "_factory", side_effect=AssertionError("new provider")), \
             patch.object(self.feed, "side_effect", AssertionError("refresh feed")):
            out = self.run_book()
        self.assertEqual(out.get("target_status"), "queued", out)
        self.assertEqual(out["feed_health"], saved["feed_health"])
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.original()["state"]["tools"][0]["state"], "complete")
        self.assertEqual(self.original()["state"]["entry_context"], saved)

    def test_original_context_request_receipt_rejects_foreign_book(self):
        self.plans = [packet(None, [call(F.tool_name(self.book, "request_context_upgrade"), {
            "plane": "fresh_insider_context",
            "reason": "Dated regional context would resolve this decision gap."}, "context-lost")])]
        real = portfolio_learning.request_context
        def lost_ack(*args, **kwargs):
            real(*args, **kwargs)
            raise OSError("fixture context ACK lost")
        with patch.object(portfolio_learning, "request_context", side_effect=lost_ack):
            first = self.run_book()
        self.assertTrue(first["fabric_held"], first)
        correlation = {"run_id": self.run_id, "tool_id": "context-lost"}
        self.assertEqual(portfolio_learning.reconcile_context_request(
            correlation, book=self.book)["request"]["book"], self.book)
        with self.assertRaises(runlog.PortfolioRunError):
            portfolio_learning.reconcile_context_request(correlation, book=self.other)
        before = (self.counts(), (portfolio_learning._DIR / "context_requests.jsonl").read_bytes())
        with patch.object(portfolio_learning, "request_context", side_effect=AssertionError("duplicate context")), \
             patch.object(F, "_factory", side_effect=AssertionError("new provider")):
            recovered = self.run_book()
        self.assertFalse(recovered.get("fabric_held"), recovered)
        self.assertEqual((self.counts(), (portfolio_learning._DIR / "context_requests.jsonl").read_bytes()), before)

    def test_interrupted_queue_callback_repairs_same_regional_owner(self):
        self.arrange_submission(self.stock_submission(), read=False)
        with patch.object(self.bot, "_append_decision_log", side_effect=KeyboardInterrupt("fixture callback")):
            with self.assertRaises(KeyboardInterrupt):
                self.run_book()
        self.assertTrue(paper_account.pending_target_file_exists(self.book))
        self.assertFalse(paper_account.pending_target_file_exists(self.other))
        before = self.counts()
        with patch.object(F, "_factory", side_effect=AssertionError("repeat provider")), \
             patch.object(settle, "execute_or_queue", side_effect=AssertionError("repeat settle")):
            recovered = self.run_book()
        self.assertEqual(recovered.get("target_status"), "queued", recovered)
        self.assertEqual(self.counts(), before)
        rows = runlog.strict_rows(registry.data_dir(self.book) / "decisions.jsonl")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["decision_effective"])
        self.assertEqual(rows[0]["feed_health"], self.original()["state"]["entry_context"]["feed_health"])

    def test_partial_publication_repairs_only_same_book_original_bytes(self):
        from bridge import build_portfolio
        self.arrange_submission(read=False)
        real = build_portfolio._atomic_write_bytes
        def partial(path, encoded):
            if path.name == "portfolio.json":
                raise OSError("fixture before site write")
            return real(path, encoded)
        with patch.object(build_portfolio, "_atomic_write_bytes", side_effect=partial):
            first = self.run_book()
        self.assertTrue(first["fabric_held"], first)
        plan = self.original()["state"]["publication"]
        hub = Path(plan["paths"]["hub"]).read_bytes()
        before = self.counts()
        with patch.object(F, "_factory", side_effect=AssertionError("repeat provider")), \
             patch.object(settle, "execute_or_queue", side_effect=AssertionError("repeat settle")), \
             patch.object(build_portfolio, "write", side_effect=AssertionError("new publication")):
            recovered = self.run_book()
        self.assertFalse(recovered.get("fabric_held"), recovered)
        self.assertEqual(Path(plan["paths"]["site"]).read_bytes(), hub)
        self.assertEqual(json.loads(hub)["portfolio_id"], self.book)
        self.assertEqual(self.counts(), before)

    def test_manual_cancellation_keeps_book_lock_until_original_observed(self):
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
        def waiting():
            entered.set()
            if not release.wait(5):
                raise AssertionError("fixture original never released")
            self.upstream()
        self.native.on_upstream = waiting
        endpoint = next(route.endpoint for route in app.routes
                        if getattr(route, "path", None) == "/api/"+self.book+"/run")
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
        self.assertEqual(receipts[0][0][1], "error")
        self.assertEqual(self.original()["state"]["phase"], "complete")
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))

    def test_daily_and_first_run_use_job_id_and_no_legacy_availability(self):
        from app import scheduler
        from brain import cli_bridge
        from control_plane import locks
        class Lock:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
        # Keep the actual Thread class: native HTTP deadlines construct Timer,
        # whose initializer calls threading.Thread.__init__ directly.
        original_start = threading.Thread.start
        first_run_started = []
        def first_run_start(thread):
            if thread.name == self.book+"-first-run":
                first_run_started.append(thread.name)
                return thread.run()
            return original_start(thread)
        receipts = []
        with patch.object(locks, "acquire_or_log", return_value=Lock()), \
             patch.object(scheduler, "_ledger_start", return_value=SimpleNamespace(run_id=self.run_id)), \
             patch.object(scheduler, "_ledger_end", side_effect=lambda *a, **k: receipts.append((a, k))), \
             patch.object(scheduler, "_post_mark_forward_evaluation"), \
             patch.object(cli_bridge, "available", side_effect=AssertionError("legacy readiness")), \
             patch.object(threading.Thread, "start", first_run_start):
            self.assertTrue(getattr(scheduler, "maybe_first_"+self.book+"_run")())
        state = self.original()["state"]
        self.assertEqual(state["run_id"], self.run_id)
        self.assertEqual(state["phase"], "complete", state)
        self.assertEqual(first_run_started, [self.book+"-first-run"])
        self.assertEqual(len(receipts), 1)
        before = self.counts()
        with patch.object(locks, "acquire_or_log", return_value=Lock()), \
             patch.object(scheduler, "_ledger_start", return_value=SimpleNamespace(run_id=self.run_id)), \
             patch.object(scheduler, "_ledger_end"), \
             patch.object(scheduler, "_post_mark_forward_evaluation"), \
             patch.object(scheduler, "_read_pool_exhausted_since", side_effect=AssertionError("legacy retry")), \
             patch.object(F, "_factory", side_effect=AssertionError("repeat provider")):
            getattr(scheduler, "_"+self.book+"_job")()
        self.assertEqual(self.counts(), before)

    def test_late_provider_veto_preserves_accepted_regional_target(self):
        from brain import cli_bridge
        self.arrange_submission(read=False)
        calls = []
        def veto():
            calls.append(1)
            if len(calls) == 2:
                raise cli_bridge.ProviderStartRefused("fixture_late_veto")
        out = self.run_book(before_provider_start=veto)
        self.assertEqual(out.get("target_status"), "queued", out)
        self.assertFalse(out["brain"]["ok"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))
        self.assertEqual([item["state"] for item in self.original()["state"]["steps"]],
                         ["complete", "refused"])

    def test_pre_provider_failure_closes_locally_without_rebinding(self):
        with patch.object(self.bot, "_build_prompt", side_effect=ValueError("fixture prompt input")):
            out = self.run_book()
        self.assertFalse(out.get("fabric_held"), out)
        self.assertFalse(out["decision_effective"])
        self.assertEqual(self.original()["state"]["phase"], "complete")
        self.assertTrue(self.original()["state"]["local_failure"])
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))
        with patch.object(F, "_factory", side_effect=AssertionError("rebind")):
            self.assertEqual(self.run_book(), out)

    def test_feed_gate_finishes_locally_and_replays_without_new_read(self):
        self.feed.return_value = {"status": "down", "asof": self.day}
        out = self.run_book()
        self.assertTrue(out.get("feed_aborted"), out)
        self.assertFalse(out.get("fabric_held"), out)
        state = self.original()["state"]
        self.assertEqual((state["phase"], state["local_gate"], state["close"]),
                         ("complete", "feed_down", F._LOCAL))
        self.assertFalse(out["decision_effective"])
        self.assertNotIn("frozen", state)
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))
        self.assertFalse(paper_account.pending_target_file_exists(self.book))
        with patch.object(F, "_factory", side_effect=AssertionError("new provider")), \
             patch.object(self.feed, "side_effect", AssertionError("new feed")):
            self.assertEqual(self.run_book(), out)

    def test_budget_gate_partial_publication_recovers_local_original(self):
        from bridge import build_portfolio
        real = build_portfolio._atomic_write_bytes
        def partial(path, encoded):
            if path.name == "portfolio.json":
                raise OSError("fixture local publication")
            return real(path, encoded)
        with patch.object(cost_guard, "fabric_over_budget", return_value=True), \
             patch.object(build_portfolio, "_atomic_write_bytes", side_effect=partial):
            first = self.run_book()
        self.assertTrue(first.get("fabric_held"), first)
        self.assertEqual(self.original()["state"]["local_gate"], "cost_capped")
        with patch.object(cost_guard, "fabric_over_budget", side_effect=AssertionError("changed gate")), \
             patch.object(self.feed, "side_effect", AssertionError("new feed")), \
             patch.object(F, "_factory", side_effect=AssertionError("new provider")):
            out = self.run_book()
        self.assertFalse(out.get("fabric_held"), out)
        self.assertTrue(out["cost_capped"])
        self.assertFalse(out["decision_effective"])
        self.assertEqual(self.original()["state"]["phase"], "complete")
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))

    def test_overnight_recovers_original_before_tripwire_and_derisk(self):
        from data_layer import overnight as tape
        self.arrange_submission(read=False)
        real = decision_submission.write_atomic
        def lost_ack(*args, **kwargs):
            real(*args, **kwargs)
            raise OSError("fixture original")
        with patch.object(decision_submission, "write_atomic", side_effect=lost_ack):
            self.assertTrue(self.run_book()["fabric_held"])
        before = self.counts()
        with patch.object(tape, "tape", side_effect=AssertionError("new tape")), \
             patch.object(F, "_factory", side_effect=AssertionError("new provider")):
            out = overnight.watch(self.book, self.day, run_id="new-watch:"+self.book)
        self.assertEqual(out["refined"]["run_id"], self.run_id)
        self.assertEqual(out["refined"]["target_status"], "queued", out)
        self.assertEqual(self.counts(), before)


class ChinaPortfolioApplicationTests(RegionalCases, unittest.TestCase):
    book = "china"


class HKPortfolioApplicationTests(RegionalCases, unittest.TestCase):
    book = "hk"


class RegionalIdentityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        for module, name, value in (
            (runlog, "_RUNS_DIR", self.root / "data/brain/runs"),
            (runlog, "_INDEX", self.root / "data/brain/runs/index.jsonl"),
            (runlog, "_PROTOCOL_LOCK_ROOT", self.root),
            (cost_guard, "_ROOT", self.root),
            (cost_guard, "_DIR", self.root / "data/brain/cost"),
        ):
            item = patch.object(module, name, value)
            item.start()
            self.addCleanup(item.stop)

    def claim(self, book, run_id=None):
        return runlog.portfolio_claim({
            "schema": F.SCHEMA, "run_id": run_id or "pending-"+book, "book": book,
            "request": {"asof": "2026-11-06", "force": False, "armed": True, "directive": None},
            "asof": "2026-11-06", "phase": "claimed", "steps": [], "tools": []})

    def test_each_book_retains_original_but_run_ids_are_globally_unique(self):
        for book in ("autonomous", "china", "hk"):
            self.claim(book)
        for book in ("autonomous", "china", "hk"):
            self.assertEqual(runlog.portfolio_lookup(book=book)["state"]["run_id"], "pending-"+book)
            self.assertEqual(runlog.portfolio_lookup("new-"+book, book=book)["state"]["book"], book)
        with self.assertRaises(runlog.PortfolioRunError):
            runlog.portfolio_lookup("pending-china", book="hk")
        with self.assertRaises(runlog.PortfolioRunError):
            self.claim("hk", "pending-china")
        for book in ("china", "hk"):
            with patch.object(F, "_factory", side_effect=AssertionError("new factory")):
                handled, out = F.route(book=book, run_id="later-"+book, runner=lambda *a, **k: self.fail("runner"))
            self.assertTrue(handled)
            self.assertTrue(out["fabric_held"])
            self.assertEqual((out["portfolio_id"], out["run_id"]), (book, "pending-"+book))

    def test_book_and_entry_context_cannot_change_after_claim(self):
        doc = self.claim("china")
        bad = copy.deepcopy(doc)
        bad["state"]["book"] = "hk"
        with self.assertRaises(runlog.PortfolioRunError):
            runlog.portfolio_save(bad)
        doc["state"]["entry_context"] = {
            "portfolio_id": "china", "asof": "2026-11-06", "ran_at": "2026-11-06T00:00:00+00:00",
            "trading_day": True, "inaugural": True, "feed_health": {"status": "ok"}}
        runlog.portfolio_save(doc)
        bad = copy.deepcopy(doc)
        bad["state"]["entry_context"]["feed_health"]["status"] = "down"
        with self.assertRaises(runlog.PortfolioRunError):
            runlog.portfolio_save(bad)
        self.assertEqual(runlog.portfolio_lookup(book="china")["state"]["entry_context"], doc["state"]["entry_context"])

    def test_cost_receipt_id_cannot_be_reused_by_another_book(self):
        observations = [{"request_id": "cost-original:brain:0", "model": "model", "pool": "go",
                         "input_tokens": 11, "output_tokens": None}]
        first = cost_guard.record_fabric("china", "cost-original", "2026-11-06", observations)
        self.assertEqual(cost_guard.record_fabric("china", "cost-original", "2026-11-06", observations), first)
        with self.assertRaises(Exception):
            cost_guard.record_fabric("hk", "cost-original", "2026-11-06", observations)
        self.assertNotIn("hk", cost_guard._strict_cost("2026-11-06")[1])

    def test_watch_ids_and_health_preserve_each_held_result(self):
        from app import scheduler
        with patch.object(F, "selected", return_value=True), \
             patch.object(overnight, "watch", side_effect=lambda pid, asof, **kwargs: {
                 "refined": {"target_status": "queued", "decision_effective": True,
                             "fabric_held": pid == "hk", **kwargs}}):
            result = overnight.watch_asia(handle=SimpleNamespace(run_id="watch-job"))
        self.assertEqual(result["china"]["refined"]["run_id"], "watch-job:china")
        self.assertEqual(result["hk"]["refined"]["run_id"], "watch-job:hk")
        status, severity, detail = scheduler._watch_job_outcome(result)
        self.assertEqual((status, severity), ("error", "FREEZE"))
        self.assertEqual(detail["books"]["china"]["status"], "ok")
        self.assertEqual(detail["books"]["hk"]["reason"], "fabric_effect_unsettled")
        self.assertEqual(scheduler._watch_job_outcome({"hk": {"skipped": "tape_calm"}})[0], "skip")


if __name__ == "__main__":
    unittest.main()
