"""Saved-paper re-digest through real portfolio Fabric, artifact and filing owners."""
from __future__ import annotations
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import threading
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from brain import research_paper as R

_spec = importlib.util.spec_from_file_location("_redigest_fixture",
    Path(__file__).with_name("test_technician_fabric_composition.py"))
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)


class SavedPaperApplicationTests(unittest.TestCase):
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
        value = yaml.safe_load(self.config_paths[1].read_text())
        value["capabilities"][0]["allowed_lanes"] = [R._REDI_LANE]
        self.config_paths[1].write_text(yaml.safe_dump(value))

    def setUp(self):
        _fixture.TechnicianApplicationTests.setUp(self)
        self.start(patch.object(R, "_ROOT", self.root))
        self.start(patch.object(R, "_PAPERS", self.root / "data/research/papers"))
        self.start(patch.object(R, "_INDEX", R._PAPERS / "index.jsonl"))
        self.start(patch.object(R, "_NOTES", self.root / "data/research/notes"))
        self.start(patch.dict(os.environ, {"MASTERMIND_RESEARCH_LLM": "1"}))
        self.research = self.start(patch.object(R.cli_bridge, "research_sync",
            side_effect=AssertionError("fresh armed research")))
        from brain import neural_web_context
        self.weather = self.start(patch.object(neural_web_context, "seat_prompt_block",
            side_effect=AssertionError("fresh weather")))
        self.paper_id = "2026-06-01-NVDA"
        self.operation_id = "saved-redigest:fixture-1"
        report = ("## Thesis\n\nThis is the already-filed research report. "
                  "The business case relies on dated evidence, with valuation and execution risks.\n\n"
                  "## Pros\n\n- Durable demand was observed in the saved quarter.\n"
                  "- Existing margins support the saved operating case.\n\n"
                  "## Cons\n\n- The valuation leaves limited room for execution errors.\n"
                  "- Concentration remains a material risk.\n\n"
                  "## Valuation\n\nThe saved price was used in this analysis.\n\n"
                  "## Re-digest — viability at this price\n\nThe original grade was fair.")
        self.paper = {
            "schema": R.SCHEMA, "id": self.paper_id, "ticker": "NVDA", "asof": "2026-06-01",
            "generated_at": "2026-06-01T12:34:56+00:00", "mode": "llm", "model": "original-report-model",
            "tools_used": ["saved_report_tool"], "cost_usd": None, "price_at_review": 100.0,
            "confluence": 0.6, "research_score": 70, "viability": "fair", "recommend": True,
            "confidence": "medium", "fair_value": 110.0, "price_assessment": "The saved price was fair.",
            "summary": "Original saved thesis.", "sections": R._split_sections(report),
            "key_risks": ["Valuation", "Execution"], "entry_agreement": None, "entry_note": "",
            "report_md": report, "verdict_parsed": True,
            "entry_report": {"verdict": "buyable", "buyable": True, "notes": ["Saved entry read."]},
            "context_report": {"verdict": "mixed", "score": 0.5, "reasons": ["Saved weather."]},
        }
        R._attach_gate(self.paper, self.paper["confluence"])
        self.path = R.save_paper(copy.deepcopy(self.paper))
        self.note = R.write_feed_note(copy.deepcopy(self.paper))
        self.index_before = R._INDEX.read_bytes()
        self.verdict = {"research_score": 78, "viability": "compelling", "recommend": True,
            "confidence": "medium", "fair_value": 115.0,
            "price_assessment": "At the saved price, the filed evidence supports a measured entry.",
            "key_risks": ["The saved growth case may weaken.", "Valuation remains sensitive to execution."],
            "entry_agreement": "caution", "entry_note": "Respect the saved entry constraints.",
            "summary": "The saved report supports a measured position at its historical review price."}
        self.native.response = _fixture._auto._helpers.packet(json.dumps(self.verdict))

    def redigest(self, operation_id=None):
        return R.redigest_saved_paper(self.paper_id, operation_id=operation_id or self.operation_id)

    def document(self):
        return json.loads(self.path.read_text())

    def operation(self):
        return self.document()[R._REDI_KEY]["operations"][-1]

    def counts(self):
        return (len(self.native.posts), len(self.native.dispatches),
                len(self.native.rows("application_requests")), len(self.costs()), len(self.closes))

    def test_positive_saved_paper_preserves_source_and_reuses_original_index_and_note(self):
        def upstream():
            operation = self.operation()
            self.assertEqual(operation["phase"], "pending")
            self.assertEqual(operation["input"]["paper"], self.paper)
            self.assertFalse(self.document()["recommend"])
            self.assertFalse(R.latest_for("NVDA")["confirmed"])
            self.assertFalse(R.latest_for("NVDA", strict=True)["confirmed"])
            self.assertEqual(operation["filing"]["note"]["name"], self.note.name)
        self.native.on_upstream = upstream
        result = self.redigest()
        self.assertTrue(result["ok"], result)
        paper = result["paper"]
        for key in ("id", "asof", "generated_at", "model", "tools_used", "cost_usd", "mode", "price_at_review"):
            self.assertEqual(paper[key], self.paper[key])
        self.assertEqual(paper["research_score"], 78)
        self.assertEqual((paper["redigest"]["provider"], paper["redigest"]["model"]), ("go", "fixture-model"))
        self.assertEqual(paper["redigest"]["source_report_sha256"], R._paper_bytes_hash(self.paper["report_md"].encode()))
        self.assertEqual(paper["combined"], R.score_breakdown(0.6, paper)["combined"])
        self.assertEqual(R._INDEX.read_bytes(), self.index_before)
        self.assertEqual([path.resolve() for path in R._NOTES.glob("*.md")], [self.note.resolve()])
        self.assertEqual(self.note.read_text(), R._paper_note_body(paper))
        self.assertEqual(R.latest_for("NVDA"), paper)
        self.assertEqual(R.latest_for("NVDA", strict=True), paper)
        self.assertNotIn(R._REDI_KEY, paper)
        turn = self.native.rows("application_turns")[0]
        self.assertEqual((turn["principal_id"], turn["workload"]), ("macro_portfolio_fabric", "portfolio_analysis"))
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))
        before = (self.path.read_bytes(), self.note.read_bytes(), R._INDEX.read_bytes())
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        os.environ["MASTERMIND_RESEARCH_LLM"] = "0"
        self.native.document["application_grants"] = []
        self.native.save()
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("repeat credential")):
            self.assertEqual(self.redigest(), result)
        self.assertEqual((self.path.read_bytes(), self.note.read_bytes(), R._INDEX.read_bytes()), before)
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))
        self.weather.assert_not_called()
        self.research.assert_not_called()
        self.reason.assert_not_called()

    def test_prepared_lost_ack_recovers_original_before_any_provider_effect(self):
        actual = R._paper_write
        def save(path, document):
            actual(path, document)
            if document.get(R._REDI_KEY, {}).get("operations", [{}])[-1].get("phase") == "prepared":
                raise OSError("synthetic prepared acknowledgement lost")
        with patch.object(R, "_paper_write", side_effect=save):
            self.assertFalse(self.redigest()["ok"])
        original = self.operation()
        self.assertEqual(original["phase"], "prepared")
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))
        result = self.redigest()
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.operation()["input_digest"], original["input_digest"])
        self.assertEqual(self.operation()["filing"], original["filing"])
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))

    def test_pending_lost_ack_never_binds_again_or_rekeys(self):
        actual = R._paper_write
        def save(path, document):
            actual(path, document)
            if document.get(R._REDI_KEY, {}).get("operations", [{}])[-1].get("phase") == "pending":
                raise OSError("synthetic pending acknowledgement lost")
        with patch.object(R, "_paper_write", side_effect=save):
            self.assertFalse(self.redigest()["ok"])
        original = self.operation()
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        self.assertFalse(self.redigest()["ok"])
        self.assertFalse(self.redigest("another-original")["ok"])
        self.assertEqual(self.operation(), original)
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))

    def test_concurrent_calls_do_not_repeat_original_or_erase_owner(self):
        from concurrent.futures import ThreadPoolExecutor
        self.native.block = threading.Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.redigest)
            try:
                self.assertTrue(self.native.arrived.wait(3))
                self.assertFalse(self.redigest()["ok"])
                self.assertFalse(self.redigest("another-original")["ok"])
                with self.assertRaises(ValueError):
                    R.save_paper(copy.deepcopy(self.paper))
                with self.assertRaises(ValueError):
                    R.write_feed_note(copy.deepcopy(self.paper))
            finally:
                self.native.block.set()
            self.assertTrue(future.result(timeout=20)["ok"])
        self.assertEqual(self.counts(), (1, 0, 1, 1, 1))

    def test_refused_close_keeps_original_paper_conservative(self):
        with patch.object(self.native.gateway, "close_application_turn", return_value={"disposition": "refused"}):
            result = self.redigest()
        self.assertFalse(result["ok"])
        self.assertEqual(self.operation()["phase"], "held")
        self.assertFalse(R.latest_for("NVDA")["recommend"])
        self.assertFalse(R.latest_for("NVDA")["confirmed"])
        counts = self.counts()
        self.assertFalse(self.redigest()["ok"])
        self.assertFalse(self.redigest("another-original")["ok"])
        self.assertEqual(self.counts(), counts)
        self.assertEqual(R._INDEX.read_bytes(), self.index_before)
        self.assertEqual(self.note.read_text(), R._paper_note_body(self.paper))

    def test_final_paper_lost_ack_replays_without_new_note_or_model(self):
        actual = R._paper_write
        def save(path, document):
            actual(path, document)
            if document.get(R._REDI_KEY, {}).get("operations", [{}])[-1].get("phase") == "complete":
                raise OSError("synthetic final acknowledgement lost")
        with patch.object(R, "_paper_write", side_effect=save):
            self.assertFalse(self.redigest()["ok"])
        self.assertEqual(self.operation()["phase"], "complete")
        before = self.counts()
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        self.assertTrue(self.redigest()["ok"])
        self.assertEqual(self.counts(), before)
        self.assertEqual(R._INDEX.read_bytes(), self.index_before)
        self.assertEqual(len(list(R._NOTES.glob("*.md"))), 1)

    def test_note_write_then_error_reconciles_same_original_path(self):
        actual = R._paper_sync
        def sync(path):
            if Path(path).resolve() == R._NOTES.resolve() and "Saved-report re-digest" in self.note.read_text():
                raise OSError("synthetic note directory acknowledgement lost")
            return actual(path)
        with patch.object(R, "_paper_sync", side_effect=sync):
            self.assertFalse(self.redigest()["ok"])
        self.assertEqual(self.operation()["phase"], "ready")
        counts = self.counts()
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        self.assertTrue(self.redigest()["ok"])
        self.assertEqual(self.counts(), counts)
        self.assertEqual(len(list(R._NOTES.glob("*.md"))), 1)

    def test_index_write_then_error_reconciles_without_duplicate_row(self):
        R._INDEX.write_bytes(b"")
        actual = R._paper_index_append
        def append(row):
            actual(row)
            raise OSError("synthetic index acknowledgement lost")
        with patch.object(R, "_paper_index_append", side_effect=append):
            self.assertFalse(self.redigest()["ok"])
        self.assertEqual(self.operation()["phase"], "ready")
        self.assertEqual(len(R._INDEX.read_text().splitlines()), 1)
        counts = self.counts()
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        self.assertTrue(self.redigest()["ok"])
        self.assertEqual(len(R._INDEX.read_text().splitlines()), 1)
        self.assertEqual(self.counts(), counts)

    def test_index_rotation_or_note_conflict_blocks_original_publication(self):
        def upstream():
            original = R._INDEX
            rotated = original.with_name("replacement.jsonl")
            rotated.write_bytes(original.read_bytes())
            os.replace(rotated, original)
        self.native.on_upstream = upstream
        self.assertFalse(self.redigest()["ok"])
        self.assertEqual(self.operation()["phase"], "ready")
        self.assertFalse(R.latest_for("NVDA")["confirmed"])
        before = self.counts()
        self.assertFalse(self.redigest()["ok"])
        self.assertEqual(self.counts(), before)

    def test_late_unselected_writer_cannot_overwrite_completed_original(self):
        result = self.redigest()
        self.assertTrue(result["ok"], result)
        original = self.path.read_bytes()
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        with self.assertRaises(ValueError):
            R.save_paper(copy.deepcopy(self.paper))
        with self.assertRaises(ValueError):
            R.write_feed_note(copy.deepcopy(self.paper))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(R.save_paper(result["paper"]), self.path)
        self.assertEqual(R.write_feed_note(result["paper"]), self.note)
        self.assertEqual(len(R._INDEX.read_text().splitlines()), 1)

    def test_new_explicit_operation_does_not_rewind_or_duplicate_filing(self):
        self.assertTrue(self.redigest()["ok"])
        second = self.redigest("saved-redigest:fixture-2")
        self.assertTrue(second["ok"], second)
        self.assertFalse(self.redigest()["ok"])
        self.assertEqual(self.counts(), (2, 0, 2, 2, 2))
        self.assertEqual(len(R._INDEX.read_text().splitlines()), 1)
        self.assertEqual(len(list(R._NOTES.glob("*.md"))), 1)
        self.assertEqual(second["paper"]["generated_at"], self.paper["generated_at"])

    def test_saved_report_input_bound_and_no_fresh_evidence(self):
        paper = copy.deepcopy(self.paper)
        paper["report_md"] += "\n" + "source content " * 1000 + "\nOUTSIDE-REPORT-BOUND"
        R.save_paper(paper)
        result = self.redigest()
        self.assertTrue(result["ok"], result)
        request = self.operation()["request"]
        self.assertNotIn("OUTSIDE-REPORT-BOUND", request["user"])
        self.assertIn("2026-06-01", request["user"])
        self.assertIn("Saved entry read.", request["user"])
        self.weather.assert_not_called()
        self.research.assert_not_called()

    def test_cancellation_keeps_pending_and_closes_original_once(self):
        with patch.object(self.shared, "make_call", side_effect=KeyboardInterrupt("synthetic cancellation")):
            with self.assertRaises(KeyboardInterrupt):
                self.redigest()
        self.assertEqual(self.operation()["phase"], "pending")
        counts = self.counts()
        self.assertFalse(self.redigest()["ok"])
        self.assertEqual(self.counts(), counts)
        self.assertEqual(len(self.closes), 1)

    def test_missing_saved_confluence_and_disabled_flags_never_bind(self):
        for key, expected in (("confluence", "saved_confluence_missing"), ("price_at_review", "saved_price_invalid")):
            with self.subTest(missing=key):
                paper = copy.deepcopy(self.paper)
                paper.pop(key)
                R.save_paper(paper)
                before = self.path.read_bytes()
                result = self.redigest()
                self.assertFalse(result["ok"])
                self.assertEqual(result["reason"], expected)
                self.assertEqual(self.path.read_bytes(), before)
        R.save_paper(self.paper)
        os.environ["MASTERMIND_RESEARCH_LLM"] = "0"
        self.assertFalse(self.redigest()["ok"])
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))

    def test_strict_verdict_rejects_ambiguous_unbounded_or_coerced_values(self):
        invalid = []
        for key, value in (("research_score", True), ("research_score", 101), ("recommend", "yes"),
                           ("fair_value", float("nan")), ("viability", "BUY"), ("key_risks", [])):
            obj = copy.deepcopy(self.verdict)
            obj[key] = value
            invalid.append(json.dumps(obj))
        valid = json.dumps(self.verdict)
        invalid.extend([valid + " trailing prose", valid[:-1], valid.replace('"research_score": 78',
                         '"research_score": 78, "research_score": 12')])
        for text in invalid:
            with self.subTest(response=text[:80]):
                self.assertIsNone(R._redigest_verdict(text))
        self.native.response = _fixture._auto._helpers.packet(invalid[0])
        result = self.redigest()
        self.assertFalse(result["ok"])
        self.assertEqual(self.operation()["phase"], "rejected")
        self.assertFalse(R.latest_for("NVDA")["recommend"])

    def test_cli_uses_explicit_operation_and_returns_public_result(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = R._main(["redigest", "--paper-id", self.paper_id, "--operation-id", self.operation_id])
        self.assertEqual(code, 0, output.getvalue())
        result = json.loads(output.getvalue())
        self.assertTrue(result["ok"])
        self.assertNotIn(R._REDI_KEY, result["paper"])


    def _assert_filing_fsync_recovery(self, kind):
        import stat
        if kind == "index":
            R._INDEX.write_bytes(b"")
        else:
            self.note.unlink()
        actual = os.fsync
        failed = []
        def fsync(descriptor):
            info = os.fstat(descriptor)
            if stat.S_ISREG(info.st_mode):
                is_index = (info.st_dev, info.st_ino) == (R._INDEX.stat().st_dev, R._INDEX.stat().st_ino)
                try:
                    is_note = os.pread(descriptor, 2, 0) == b"# "
                except OSError:
                    # The first write descriptor is write-only; its target inode
                    # is already visible for the new-note publication branch.
                    is_note = any((p.stat().st_dev, p.stat().st_ino) == (info.st_dev, info.st_ino)
                                  for p in R._NOTES.glob("*.md"))
                if ((kind == "index" and is_index and info.st_size > 0)
                        or kind == "note" and is_note):
                    failed.append(kind)
                    raise OSError("synthetic file content fsync failure")
            return actual(descriptor)
        with patch.object(os, "fsync", side_effect=fsync):
            self.assertFalse(self.redigest()["ok"])
            self.assertEqual(self.operation()["phase"], "ready")
            before = self.counts()
            self.assertFalse(self.redigest()["ok"])
            self.assertEqual(self.operation()["phase"], "ready")
            self.assertEqual(self.counts(), before)
        self.assertGreaterEqual(len(failed), 2)
        self.assertTrue(self.redigest()["ok"])
        self.assertEqual(self.counts(), before)
        self.assertEqual(len(R._INDEX.read_text().splitlines()), 1)
        self.assertEqual(len(list(R._NOTES.glob("*.md"))), 1)

    def test_visible_index_requires_file_fsync_before_completion(self):
        self._assert_filing_fsync_recovery("index")

    def test_visible_note_requires_file_fsync_before_completion(self):
        self._assert_filing_fsync_recovery("note")

    def test_batch_operation_id_cannot_collide_across_saved_dates(self):
        self.note.unlink()
        with patch.object(R.time, "time", return_value=int(R.time.time())), \
                patch.object(self.cache, "_fabric_cached_document",
                             side_effect=KeyboardInterrupt("synthetic before bind")):
            with self.assertRaises(KeyboardInterrupt):
                self.redigest()
            first = self.operation()["filing"]["note"]["name"]
            another = copy.deepcopy(self.paper)
            another.update(id="2026-06-02-NVDA", asof="2026-06-02", generated_at="2026-06-02T12:34:56+00:00")
            path = R.save_paper(another)
            with self.assertRaises(KeyboardInterrupt):
                R.redigest_saved_paper(another["id"], operation_id=self.operation_id)
            second = json.loads(path.read_text())[R._REDI_KEY]["operations"][-1]["filing"]["note"]["name"]
        self.assertNotEqual(first, second)
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0))

    def test_saved_blocked_entry_cannot_be_upgraded_by_an_agree_verdict(self):
        paper = copy.deepcopy(self.paper)
        paper["entry_report"] = {"verdict": "extended", "buyable": False, "notes": ["Saved hard entry block."]}
        R.save_paper(paper)
        self.verdict["entry_agreement"] = "agree"
        self.native.response = _fixture._auto._helpers.packet(json.dumps(self.verdict))
        result = self.redigest()
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["paper"]["redigest"]["entry_gate"]["buyable"])
        self.assertEqual(result["paper"]["redigest"]["entry_gate"]["verdict"], "extended")

    def test_no_saved_entry_is_an_explicit_absence_not_a_fresh_query(self):
        paper = copy.deepcopy(self.paper)
        paper.pop("entry_report")
        paper.pop("context_report")
        R.save_paper(paper)
        result = self.redigest()
        self.assertTrue(result["ok"], result)
        self.assertIsNone(result["paper"]["entry_agreement"])
        self.assertIsNone(result["paper"]["redigest"]["entry_gate"]["buyable"])
        self.assertIn("no entry/context evidence available", self.operation()["request"]["user"])
        self.weather.assert_not_called()

    def test_native_pool_regrades_saved_report_with_actual_model_and_single_usage(self):
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
        native.native_text = json.dumps(self.verdict)
        result = self.redigest()
        self.assertTrue(result["ok"], result)
        self.assertEqual((result["paper"]["redigest"]["provider"], result["paper"]["redigest"]["model"]),
                         ("codex-native", "fixture-native"))
        self.assertEqual(result["paper"]["model"], self.paper["model"])
        self.assertEqual(self.counts(), (0, 1, 1, 1, 1))
        self.assertEqual(self.costs()[0]["cost_basis"], "unknown")
        self.assertIsNone(self.costs()[0]["est_cost_usd"])
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE")
        self.assertEqual(self.redigest(), result)
        self.assertEqual(self.counts(), (0, 1, 1, 1, 1))
