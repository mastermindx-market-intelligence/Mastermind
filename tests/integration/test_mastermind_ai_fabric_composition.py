"""Portfolio prose through the actual Fabric portfolio workload and existing journals.

Only upstream responses, qualification/account fixtures, and business input facts
are synthetic. Source owners, C/B/A HTTP, SQLite, accounting, custody and public
projection are real. All files are isolated beneath the fixture root.
"""
from __future__ import annotations
import copy
import importlib.util
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from brain import mastermind_ai as M

_spec = importlib.util.spec_from_file_location("_portfolio_fixture",
    Path(__file__).with_name("test_technician_fabric_composition.py"))
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)


class PortfolioApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _fixture.TechnicianApplicationTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        _fixture.TechnicianApplicationTests.tearDownClass.__func__(cls)

    start = _fixture.TechnicianApplicationTests.start
    configure = _fixture.TechnicianApplicationTests.configure
    costs = _fixture.TechnicianApplicationTests.costs

    def configure_portfolio(self, pools):
        import yaml
        _fixture.TechnicianApplicationTests.configure_portfolio(self, pools)
        document = yaml.safe_load(self.config_paths[1].read_text())
        document["capabilities"][0]["allowed_lanes"] = [M._PORTFOLIO_LANE]
        self.config_paths[1].write_text(yaml.safe_dump(document))

    def setUp(self):
        _fixture.TechnicianApplicationTests.setUp(self)
        from brain import journal, nw_reflection, portfolio_learning, outcome_ledger
        directory = self.root / "data/mastermind_ai"
        for name, value in (
            ("_ROOT", self.root), ("_DIR", directory), ("_SETTINGS", directory / "settings.json"),
            ("_LOOP_LOG", directory / "loop_log.jsonl"), ("_REVIEWS", directory / "reviews.jsonl"),
            ("_DIRECTIVES", directory / "directives.jsonl"), ("_LAST_ACK", directory / "last_ack.json")):
            self.start(patch.object(M, name, value))
        self.start(patch.object(M, "_doctrine_block", return_value={}))
        self.start(patch.dict(os.environ, {"MASTERMIND_AI_LOOP": "1", "MASTERMIND_AI_REVIEW_LLM": "1"}))
        self.assertTrue(M.update_settings({"review_every_n_loops": 2, "llm_review": True})["ok"])
        self.business = []
        self.start(patch.object(journal, "draft_all",
            side_effect=lambda: (self.business.append("journal") or {"analyst": 1})))
        self.start(patch.object(journal, "recompute_pins", return_value=[]))
        self.start(patch.object(nw_reflection, "persist", return_value={
            "contract_drift": [], "nudges": [], "coverage": {"coverage_rate": 0.5},
            "context_quality": {"seen_rate": 0.75}}))
        self.start(patch.object(nw_reflection, "_read_jsonl", return_value=[]))
        self.start(patch.object(nw_reflection, "latest", return_value={}))
        self.start(patch.object(M, "reconcile_ack", return_value={"state": "absent", "directives_acknowledged": 0}))
        self.start(patch.object(M, "expire_stale_published", return_value={"expired_n": 0}))
        self.start(patch.object(M, "draft_directives_from_context_requests",
                              return_value={"ok": True, "queued": [], "skipped": []}))
        self.start(patch.object(portfolio_learning, "refresh_all", return_value={"books": {}}))
        self.start(patch.object(portfolio_learning, "status", return_value={"books": {}, "context_requests": []}))
        self.start(patch.object(outcome_ledger, "summary", return_value={"n": 0, "hit_rate": None, "brier": None}))
        self.start(patch.object(M, "_journal_counts",
                              return_value={"lessons": 4, "pins_active": 2, "pins_unpinned": 0, "pending": 1}))
        self.start(patch.object(M, "_self_tune_state", return_value={"armed": False, "families_n": 0, "locked": []}))
        self.start(patch.object(M, "_agenda_top", return_value=[]))
        self.answer = "Steady progress; evidence is still limited. No alpha claims."
        self.native.response = _fixture._auto._helpers.packet(self.answer)

    def build(self, number=2):
        return M._build_review(number, M.settings())

    def raw_reviews(self):
        return [json.loads(line) for line in M._REVIEWS.read_text().splitlines() if line.strip()]

    def counts(self):
        return (len(self.native.posts), len(self.native.dispatches),
                len(self.native.rows("application_requests")), len(self.costs()), len(self.closes))

    def assert_public_files(self):
        raw = "\n".join(path.read_text() for path in (M._LOOP_LOG, M._REVIEWS) if path.exists())
        for private in ("http://", "https://", "MACRO_APPLICATION_TOKEN", "account-a",
                        "credential_ref", "lease_id", "transport_identity", "workload_policy",
                        str(self.macro_root), str(self.root), "You are the Mastermind Portfolio"):
            self.assertNotIn(private, raw)
        return raw

    def test_positive_review_uses_portfolio_authority_and_zero_spend_replay(self):
        def upstream():
            state = M._portfolio_state()
            row = state["review_map"][2][1]
            self.assertEqual(row[M._PORTFOLIO_REVIEW]["phase"], "pending")
            self.assertEqual(state["open_ref"], M._portfolio_ref(row))
            self.assertNotIn("llm_assessment", M.reviews()[0])
        self.native.on_upstream = upstream
        result = self.build()
        self.assertEqual(result.get("llm_assessment"), self.answer, result)
        self.assertEqual(result["llm_review"]["state"], "complete")
        self.assertEqual((result["llm_review"]["provider"], result["llm_review"]["model"]),
                         ("go", "fixture-model"))
        turn = self.native.rows("application_turns")[0]
        self.assertEqual((turn["principal_id"], turn["workload"]), ("macro_portfolio_fabric", "portfolio_analysis"))
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))
        self.assertEqual(M.reviews(), [result])
        self.assertEqual(M.status()["last_review"], result)
        before = (M._REVIEWS.read_bytes(), M._LOOP_LOG.read_bytes())
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        os.environ["MASTERMIND_AI_REVIEW_LLM"] = "0"
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("repeat credential")):
            self.assertEqual(self.build(), result)
        self.assertEqual((M._REVIEWS.read_bytes(), M._LOOP_LOG.read_bytes()), before)
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))
        self.reason.assert_not_called()
        self.assert_public_files()

    def test_two_cycles_preserve_cadence_completed_window_and_public_shapes(self):
        first = M.run_cycle(self.day, trigger="test")
        self.assertTrue(first["ok"], first)
        self.assertEqual(first["loop_n"], 1)
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))
        second = M.run_cycle(self.day, trigger="test")
        self.assertTrue(second["ok"], second)
        self.assertEqual(second["loop_n"], 2)
        self.assertNotIn("review_state", second)
        self.assertEqual([r["loop_n"] for r in M.loop_log()], [1, 2])
        self.assertEqual(M.reviews()[0]["completed"]["journal_drafts_added"], 1)
        self.assertEqual(M.reviews()[0]["llm_assessment"], self.answer)
        self.assertEqual(M.status()["loop_n"], 2)
        self.assertEqual(len(self.business), 2)
        self.assertEqual(len(M._LOOP_LOG.read_text().splitlines()), 2)
        self.assert_public_files()

    def test_concurrent_cycle_returns_original_without_repeating_business_or_model(self):
        from concurrent.futures import ThreadPoolExecutor
        self.assertTrue(M.run_cycle(self.day)["ok"])
        self.native.block = threading.Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(M.run_cycle, self.day)
            try:
                self.assertTrue(self.native.arrived.wait(3))
                waiting = M.run_cycle("2026-11-07")
                self.assertEqual(waiting["loop_n"], 2)
                self.assertEqual(waiting["review_state"], "held")
                self.assertEqual(len(self.business), 2)
                self.assertEqual(len(self.native.posts), 1)
            finally:
                self.native.block.set()
            self.assertTrue(future.result(timeout=20)["ok"])
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))

    def test_business_crash_keeps_original_claim_before_any_repeat(self):
        with patch.object(M, "_cycle_snapshot", side_effect=KeyboardInterrupt("synthetic crash")):
            with self.assertRaises(KeyboardInterrupt):
                M.run_cycle(self.day)
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        os.environ["MASTERMIND_AI_LOOP"] = "0"
        result = M.run_cycle("2026-11-07")
        self.assertEqual(result, {"ok": False, "held": "original_incomplete", "asof": self.day, "loop_n": 1})
        self.assertEqual(self.business, [])
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))

    def test_frozen_cycle_recovers_same_review_without_rerunning_business(self):
        self.assertTrue(M.run_cycle(self.day)["ok"])
        with patch.object(M, "_portfolio_finish_cycle", side_effect=KeyboardInterrupt("synthetic interruption")):
            with self.assertRaises(KeyboardInterrupt):
                M.run_cycle(self.day)
        state = M._portfolio_state()
        original = state["unfinished"][1]
        operation = original[M._PORTFOLIO_CYCLE]["review_operation_id"]
        self.assertEqual(len(self.business), 2)
        result = M.run_cycle("2026-11-07")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["asof"], self.day)
        self.assertEqual(result["loop_n"], 2)
        self.assertEqual(len(self.business), 2)
        self.assertEqual(self.native.rows("application_turns")[0]["turn_id"], operation)
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))

    def test_lost_claim_readback_never_binds_or_rekeys(self):
        original = M._portfolio_store
        def store(path, **kwargs):
            original(path, **kwargs)
            if kwargs["row"].get(M._PORTFOLIO_REVIEW, {}).get("phase") == "pending":
                raise OSError("synthetic claim acknowledgement lost")
        with patch.object(M, "_portfolio_store", side_effect=store):
            self.assertNotIn("llm_assessment", self.build())
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        self.assertNotIn("llm_assessment", self.build())
        self.assertIn("held", M.run_cycle(self.day))
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))

    def test_lost_anchor_ack_prevents_provider_and_preserves_pending_review(self):
        original = M._portfolio_store
        def store(path, **kwargs):
            original(path, **kwargs)
            if path == M._LOOP_LOG:
                raise OSError("synthetic anchor acknowledgement lost")
        with patch.object(M, "_portfolio_store", side_effect=store):
            self.assertNotIn("llm_assessment", self.build())
        self.assertEqual(self.raw_reviews()[0][M._PORTFOLIO_REVIEW]["phase"], "pending")
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))
        self.assertNotIn("llm_assessment", self.build())
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))

    def test_observation_precedes_close_and_unknown_close_keeps_safe_text_held(self):
        def close(*args, **kwargs):
            row = self.raw_reviews()[0]
            self.assertEqual(row[M._PORTFOLIO_REVIEW]["phase"], "observed")
            self.assertEqual(row[M._PORTFOLIO_REVIEW]["approved_text"], self.answer)
            self.assertNotIn("llm_assessment", M.reviews()[0])
            return {"disposition": "refused"}
        with patch.object(self.native.gateway, "close_application_turn", side_effect=close):
            result = self.build()
        self.assertNotIn("llm_assessment", result)
        owned = self.raw_reviews()[0][M._PORTFOLIO_REVIEW]
        self.assertEqual((owned["phase"], owned["approved_text"]), ("held", self.answer))
        counts = self.counts()
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        self.assertNotIn("llm_assessment", self.build(4))
        self.assertIn("held", M.run_cycle(self.day))
        self.assertEqual(self.counts(), counts)
        self.assert_public_files()

    def test_failed_observation_write_still_closes_original_once(self):
        original = M._portfolio_store
        def store(path, **kwargs):
            if kwargs["row"].get(M._PORTFOLIO_REVIEW, {}).get("phase") == "observed":
                raise OSError("synthetic observation persistence failure")
            return original(path, **kwargs)
        with patch.object(M, "_portfolio_store", side_effect=store):
            self.assertNotIn("llm_assessment", self.build())
        self.assertEqual(self.raw_reviews()[0][M._PORTFOLIO_REVIEW]["phase"], "pending")
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))
        self.assertNotIn("llm_assessment", self.build())
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))

    def test_lost_final_ack_reconciles_saved_result_and_anchor_locally(self):
        original = M._portfolio_store
        def store(path, **kwargs):
            original(path, **kwargs)
            if kwargs["row"].get(M._PORTFOLIO_REVIEW, {}).get("phase") == "terminal":
                raise OSError("synthetic final acknowledgement lost")
        with patch.object(M, "_portfolio_store", side_effect=store):
            self.assertNotIn("llm_assessment", self.build())
        self.assertIsNotNone(M._portfolio_state()["open_ref"])
        counts = self.counts()
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        self.assertEqual(self.build()["llm_assessment"], self.answer)
        self.assertIsNone(M._portfolio_state()["open_ref"])
        self.assertEqual(self.counts(), counts)

    def test_cancellation_retains_original_and_closes_once(self):
        with patch.object(self.shared, "make_call", side_effect=KeyboardInterrupt("synthetic cancellation")):
            with self.assertRaises(KeyboardInterrupt):
                self.build()
        self.assertEqual(self.raw_reviews()[0][M._PORTFOLIO_REVIEW]["phase"], "pending")
        self.assertEqual(self.counts(), (0, 0, 0, 0, 1))
        self.assertNotIn("llm_assessment", self.build())
        self.assertEqual(self.counts(), (0, 0, 0, 0, 1))

    def test_all_deny_categories_are_swept_before_truncation_and_never_saved(self):
        rejected = ("MASTERMIND_PRIVATE", "$123", "A" * 48, "token=private-value",
                    "https://private.example", "/Users/private/secret")
        for number, text in enumerate(rejected, 2):
            with self.subTest(category=number):
                self.native.response = _fixture._auto._helpers.packet("ordinary prose. " * 160 + text)
                result = self.build(number)
                self.assertNotIn("llm_assessment", result)
                self.assertEqual(result["llm_review"]["reason"], "prose_rejected")
                self.assertNotIn(text, self.assert_public_files())
        self.assertEqual(self.counts(), (6, 0, 6, 6, 6))

    def test_saved_receipt_corruption_blocks_without_new_provider(self):
        self.assertEqual(self.build()["llm_assessment"], self.answer)
        raw = M._REVIEWS.read_bytes()
        original = self.raw_reviews()[0]
        for kind in ("model", "request", "usage", "protocol", "text", "commitment"):
            with self.subTest(kind=kind):
                row = copy.deepcopy(original)
                owned = row[M._PORTFOLIO_REVIEW]
                if kind == "model":
                    owned["receipt"]["serving_model"] = "unobserved"
                elif kind == "request":
                    owned["request"]["digest"] = "0" * 64
                elif kind == "usage":
                    owned["receipt"]["input_tokens"] = -1
                elif kind == "protocol":
                    owned["receipt"]["protocol"] = "harness"
                elif kind == "text":
                    owned["approved_text"] = "MASTERMIND_PRIVATE"
                    owned["text_digest"] = M._portfolio_hash(owned["approved_text"])
                else:
                    owned["original_digest"] = "0" * 64
                M._REVIEWS.write_text(json.dumps(row) + "\n")
                self.assertNotIn("llm_assessment", self.build())
                self.assertEqual(self.counts(), (1, 0, 1, 1, 1))
        M._REVIEWS.write_bytes(raw)

    def test_duplicate_json_and_partial_tail_never_disappear_into_fresh_state(self):
        self.assertEqual(self.build()["llm_assessment"], self.answer)
        raw = M._REVIEWS.read_bytes()
        for malformed in (raw.replace(b'"loop_n":2', b'"loop_n":2,"loop_n":2', 1), raw[:-1]):
            with self.subTest(kind=len(malformed)):
                M._REVIEWS.write_bytes(malformed)
                self.assertNotIn("llm_assessment", self.build(4))
                self.assertEqual(M.status()["review_runtime"]["state"], "held")
                self.assertEqual(self.counts(), (1, 0, 1, 1, 1))
        M._REVIEWS.write_bytes(raw)

    def test_prefix_rotation_keeps_counter_and_pruned_review_cannot_rekey(self):
        self.assertTrue(M.run_cycle(self.day)["ok"])
        self.assertTrue(M.run_cycle(self.day)["ok"])
        M._LOOP_LOG.write_bytes(M._LOOP_LOG.read_bytes().splitlines(keepends=True)[-1])
        result = M.run_cycle("2026-11-07")
        self.assertEqual(result["loop_n"], 3)
        self.assertEqual([r["loop_n"] for r in M.loop_log()], [2, 3])
        M._REVIEWS.write_bytes(b"")
        self.assertNotIn("llm_assessment", self.build(2))
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))

    def test_missing_review_with_open_anchor_is_held_before_business(self):
        with patch.object(self.native.gateway, "close_application_turn", return_value={"disposition": "refused"}):
            self.build()
        M._REVIEWS.write_bytes(b"")
        result = M.run_cycle(self.day)
        self.assertEqual(result["held"], "journal_unavailable")
        self.assertEqual(self.business, [])
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))

    def test_opt_in_gates_never_bind_and_preserve_deterministic_review(self):
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("credential")):
            os.environ["MASTERMIND_AI_REVIEW_LLM"] = "0"
            result = self.build()
            self.assertTrue(result["assessment"])
            self.assertNotIn("llm_assessment", result)
            os.environ["MASTERMIND_AI_REVIEW_LLM"] = "1"
            M.update_settings({"llm_review": False})
            self.assertNotIn("llm_assessment", self.build())
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))
        self.reason.assert_not_called()

    def test_wrong_workload_or_lane_refuses_before_credentials(self):
        import yaml
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("credential")):
            with patch.object(M, "_PORTFOLIO_WORKLOAD", "site_batch"):
                self.assertNotIn("llm_assessment", self.build())
            self.config_paths[1].write_text(yaml.safe_dump({"capabilities": []}))
            self.assertNotIn("llm_assessment", self.build())
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))
        self.reason.assert_not_called()


    def test_refused_close_cannot_be_promoted_to_terminal_by_saved_phase(self):
        with patch.object(self.native.gateway, "close_application_turn", return_value={"disposition": "refused"}):
            self.build()
        original = self.raw_reviews()[0]
        owned = original[M._PORTFOLIO_REVIEW]
        owned.update(approved_text=None, text_digest=None, phase="terminal", revision=2,
                     reason="response_unusable")
        owned["receipt"]["effect_unknown"] = False
        owned["receipt"]["close"] = {"disposition": "refused", "closed": False,
                                    "effect_unknown": False, "attempted": True}
        M._REVIEWS.write_text(json.dumps(original) + "\n")
        before = self.counts()
        self.assertNotIn("llm_assessment", self.build())
        self.assertEqual(M.status()["review_runtime"]["state"], "held")
        self.assertEqual(self.counts(), before)
        self.assertEqual(json.loads(M._LOOP_LOG.read_text())[M._PORTFOLIO_ANCHOR]["open_review"]["loop_n"], 2)

    def test_repository_ancestor_sync_precedes_business_and_binding(self):
        root = M._ROOT.resolve()
        actual = M._portfolio_sync
        calls = []
        def sync(path):
            calls.append(Path(path).resolve())
            if Path(path).resolve() == root:
                raise OSError("synthetic repository ancestor fsync failure")
            return actual(path)
        with patch.object(M, "_portfolio_sync", side_effect=sync):
            self.assertIn("held", M.run_cycle(self.day))
            self.assertNotIn("llm_assessment", self.build())
        self.assertIn(root, calls)
        self.assertEqual(self.business, [])
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))

    def test_frozen_cycle_rejects_another_cycle_receipt_before_anchor_reconciliation(self):
        self.assertTrue(M.run_cycle(self.day)["ok"])
        actual = M._portfolio_store
        def save(path, **kwargs):
            row = kwargs["row"]
            if row.get(M._PORTFOLIO_CYCLE, {}).get("phase") == "complete" and row.get("loop_n") == 2:
                raise OSError("synthetic cycle final write failure")
            return actual(path, **kwargs)
        with patch.object(M, "_portfolio_store", side_effect=save):
            self.assertIn("held", M.run_cycle(self.day))
        row = self.raw_reviews()[0]
        owned = row[M._PORTFOLIO_REVIEW]
        owned["cycle_id"] = "portfolio-cycle:foreign-original"
        owned["original_digest"] = M._portfolio_hash({key: owned[key] for key in (
            "schema", "operation_id", "cycle_id", "input_digest", "prompt_version", "authority", "request")})
        M._REVIEWS.write_text(json.dumps(row) + "\n")
        before = self.counts()
        self.assertIn("held", M.run_cycle("2026-11-07"))
        self.assertEqual(self.counts(), before)
        self.assertEqual(len(self.business), 2)

    def test_concurrent_native_recovery_cannot_complete_the_active_original(self):
        from concurrent.futures import ThreadPoolExecutor
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        self.assertTrue(M.run_cycle(self.day)["ok"])
        with patch.object(M, "_portfolio_finish_cycle", side_effect=KeyboardInterrupt("synthetic freeze boundary")):
            with self.assertRaises(KeyboardInterrupt):
                M.run_cycle(self.day)
        frozen = copy.deepcopy(M._portfolio_state()["unfinished"][1])
        reached = [threading.Event(), threading.Event()]
        proceed = [threading.Event(), threading.Event()]
        entered, release = threading.Event(), threading.Event()
        actual_build = M._build_review
        native_calls, builds = [], []
        def build(*args, **kwargs):
            number = len(builds)
            builds.append(number)
            reached[number].set()
            if not proceed[number].wait(5):
                raise TimeoutError("fixture build release missing")
            return actual_build(*args, **kwargs)
        def native(prompt, **kwargs):
            native_calls.append(kwargs)
            entered.set()
            if not release.wait(5):
                raise TimeoutError("fixture release missing")
            return {"ok": True, "text": "Steady native progress; no alpha claims."}
        with patch.object(M, "_build_review", side_effect=build), \
                patch.object(_fixture.T.cli_bridge, "reason_sync", side_effect=native), \
                ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(M._portfolio_finish_cycle, copy.deepcopy(frozen))
            try:
                self.assertTrue(reached[0].wait(3))
                second = executor.submit(M._portfolio_finish_cycle, copy.deepcopy(frozen))
                self.assertTrue(reached[1].wait(3))
                proceed[0].set()
                self.assertTrue(entered.wait(3))
                proceed[1].set()
                self.assertEqual(second.result(timeout=3)["review_state"], "held")
                self.assertFalse(M._REVIEWS.exists())
                self.assertEqual(M._portfolio_state()["unfinished"][1][M._PORTFOLIO_CYCLE]["phase"], "frozen")
                self.assertEqual(M.loop_log()[-1]["loop_n"], 1)
            finally:
                for event in proceed:
                    event.set()
                release.set()
            self.assertTrue(first.result(timeout=10)["ok"])
        self.assertEqual(len(native_calls), 1)
        self.assertEqual(M.reviews()[0]["llm_assessment"], "Steady native progress; no alpha claims.")
        self.assertIsNone(M._portfolio_state()["unfinished"])
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))
        self.assertEqual(len(self.business), 2)

    def test_untrusted_serving_model_label_is_not_copied_to_public_receipt(self):
        private = "A" * 48
        self.native.response["model"] = private
        self.assertNotIn("llm_assessment", self.build())
        self.assertNotIn(private, self.assert_public_files())
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.costs()), 1)


    def test_effect_unknown_disposition_cannot_claim_terminal_settlement(self):
        self.assertEqual(self.build()["llm_assessment"], self.answer)
        row = self.raw_reviews()[0]
        owned = row[M._PORTFOLIO_REVIEW]
        owned.update(approved_text=None, text_digest=None, reason="response_unusable")
        owned["receipt"].update(disposition="effect_unknown", effect_unknown=False)
        M._REVIEWS.write_text(json.dumps(row) + "\n")
        before = self.counts()
        self.assertNotIn("llm_assessment", self.build())
        self.assertEqual(M.status()["review_runtime"]["state"], "held")
        self.assertEqual(self.counts(), before)

    def test_native_exception_retains_started_cycle_without_repeat_or_finalization(self):
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        self.assertTrue(M.run_cycle(self.day)["ok"])
        with patch.object(_fixture.T.cli_bridge, "reason_sync",
                          side_effect=OSError("synthetic original outcome unknown")) as call:
            result = M.run_cycle(self.day)
            self.assertEqual(result["review_state"], "held")
            self.assertEqual(M.run_cycle("2026-11-07")["review_state"], "held")
            self.assertEqual(call.call_count, 1)
        self.assertFalse(M._REVIEWS.exists())
        self.assertEqual(M._portfolio_state()["unfinished"][1][M._PORTFOLIO_CYCLE]["phase"], "frozen")
        self.assertEqual([row["loop_n"] for row in M.loop_log()], [1])
        self.assertEqual(len(self.business), 2)
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))

    def test_late_selected_recovery_cannot_bind_after_native_start(self):
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        self.assertTrue(M.run_cycle(self.day)["ok"])
        observed = []
        def native(prompt, **kwargs):
            os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
            cycle = M._portfolio_state()["unfinished"][1]
            owned = cycle[M._PORTFOLIO_CYCLE]
            observed.append(M._build_review(cycle["loop_n"], M.settings(),
                _snapshot=owned["review"], _cycle_id=owned["cycle_id"],
                _operation_id=owned["review_operation_id"],
                _fabric_selected=False, _llm_requested=True))
            self.assertEqual(self.counts(), (0, 0, 0, 0, 0))
            return {"ok": True, "text": "Known completed native response."}
        with patch.object(_fixture.T.cli_bridge, "reason_sync", side_effect=native) as call:
            result = M.run_cycle(self.day)
        self.assertTrue(result["ok"])
        self.assertEqual(call.call_count, 1)
        self.assertEqual(observed[0]["llm_review"]["state"], "held")
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))
        self.assertNotIn("llm_assessment", M.reviews()[0])

    def test_partial_usage_remains_nullable_and_unpriced(self):
        self.native.response["usage"] = {"prompt_tokens": 11}
        result = self.build()
        self.assertEqual(result["llm_assessment"], self.answer, result)
        self.assertEqual(result["llm_review"]["input_tokens"], 11)
        self.assertIsNone(result["llm_review"]["output_tokens"])
        receipt = self.raw_reviews()[0][M._PORTFOLIO_REVIEW]["receipt"]
        self.assertEqual(receipt["usage"]["usage_state"], "unknown")
        self.assertIsNone(receipt["usage"]["output_tokens"])
        self.assertEqual(self.costs(), [])
        self.assertEqual(self.counts(), (1, 0, 1, 0, 1))

    def test_empty_response_never_becomes_accepted_prose(self):
        self.native.response["choices"][0]["message"]["content"] = ""
        result = self.build()
        self.assertNotIn("llm_assessment", result)
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.closes), 1)
        self.assert_public_files()

    def test_truncated_response_never_becomes_accepted_prose(self):
        self.native.response["choices"][0]["finish_reason"] = "length"
        result = self.build()
        self.assertNotIn("llm_assessment", result)
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.closes), 1)
        self.assertNotIn(self.answer, self.assert_public_files())

    def test_unsolicited_tool_response_is_not_executed_or_published(self):
        packet = self.native.response
        packet["choices"][0]["message"]["tool_calls"] = [{
            "id": "unsolicited-tool", "type": "function",
            "function": {"name": "write_private", "arguments": "{}"}}]
        packet["choices"][0]["finish_reason"] = "tool_calls"
        result = self.build()
        self.assertNotIn("llm_assessment", result)
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.closes), 1)
        self.assertNotIn("write_private", self.assert_public_files())

    def test_lost_close_ack_holds_original_after_server_side_close(self):
        actual = self.native.gateway.close_application_turn
        def close(*args, **kwargs):
            actual(*args, **kwargs)
            raise OSError("synthetic close acknowledgement lost")
        with patch.object(self.native.gateway, "close_application_turn", side_effect=close):
            result = self.build()
        self.assertNotIn("llm_assessment", result)
        self.assertEqual(self.raw_reviews()[0][M._PORTFOLIO_REVIEW]["phase"], "held")
        counts = self.counts()
        self.assertEqual(counts, (1, 0, 1, 1, 1))
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        self.assertNotIn("llm_assessment", self.build())
        self.assertEqual(self.counts(), counts)

    def test_native_pool_uses_portfolio_authority_and_replays_without_live_grants(self):
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
        native.native_text = "Native progress is steady; evidence remains limited."
        result = self.build()
        self.assertEqual(result["llm_assessment"], native.native_text, result)
        self.assertEqual((result["llm_review"]["model"], result["llm_review"]["provider"]),
                         ("fixture-native", "codex-native"))
        receipt = self.raw_reviews()[0][M._PORTFOLIO_REVIEW]["receipt"]
        self.assertEqual(receipt["protocol"], "harness")
        self.assertTrue(receipt["close"]["closed"])
        self.assertEqual(self.counts(), (0, 1, 1, 1, 1))
        cost = self.costs()[0]
        self.assertEqual((cost["provider"], cost["model"], cost["cost_basis"]),
                         ("codex-native", "fixture-native", "unknown"))
        self.assertIsNone(cost["est_cost_usd"])
        native.document["application_grants"] = []
        native.save()
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("repeat credential")):
            self.assertEqual(self.build(), result)
        self.assertEqual(self.counts(), (0, 1, 1, 1, 1))
        self.assert_public_files()
