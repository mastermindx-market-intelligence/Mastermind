"""Strict US operation persistence and shared-ledger recovery, without provider I/O."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from brain import cost_guard, fabric_portfolio as F, runlog


class PortfolioReceiptTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.day = "2026-11-06"
        self.ident = "us-owner-test"
        for module, name, value in (
            (runlog, "_RUNS_DIR", self.root / "data/brain/runs"),
            (runlog, "_INDEX", self.root / "data/brain/runs/index.jsonl"),
            (runlog, "_PROTOCOL_LOCK_ROOT", self.root),
            (cost_guard, "_ROOT", self.root),
            (cost_guard, "_DIR", self.root / "data/brain/cost"),
        ):
            p = patch.object(module, name, value)
            p.start()
            self.addCleanup(p.stop)

    def claim(self):
        return runlog.portfolio_claim({
            "schema": F.SCHEMA, "run_id": self.ident, "book": "autonomous",
            "request": {"asof": self.day, "force": False, "armed": True, "directive": None},
            "asof": self.day, "phase": "claimed", "steps": [], "tools": []})

    def observations(self):
        return [{"request_id": self.ident + ":brain:0", "model": "actual-model", "pool": "go",
                 "input_tokens": 11, "output_tokens": None}]

    def test_original_claim_has_durable_anchor_and_revision_cas(self):
        doc = self.claim()
        stale = copy.deepcopy(doc)
        doc["state"]["error"] = "original-holder"
        runlog.portfolio_save(doc)
        self.assertEqual(doc["revision"], 1)
        stale["state"]["error"] = "stale-writer"
        with self.assertRaises(runlog.PortfolioRunError):
            runlog.portfolio_save(stale)
        self.assertEqual(runlog.portfolio_lookup()["state"]["error"], "original-holder")
        with self.assertRaises(runlog.PortfolioRunError):
            self.claim()

    def test_new_id_cannot_bypass_original_or_consult_current_selector(self):
        self.claim()
        with patch.object(F, "selected", side_effect=AssertionError("mutable selector")), \
             patch.object(F, "_factory", side_effect=AssertionError("new binding")):
            handled, result = F.route(asof="2026-11-07", force=True, armed=True, directive="changed",
                                     run_id="different-operation", runner=lambda *a, **k: self.fail("runner"))
        self.assertTrue(handled)
        self.assertEqual(result["run_id"], self.ident)
        self.assertTrue(result["fabric_held"])

    def test_partial_private_row_is_not_absence_and_legacy_end_cannot_erase_anchor(self):
        self.claim()
        path = runlog._run_path(self.ident)
        path.write_bytes(path.read_bytes()[:-4])
        before = runlog._INDEX.read_bytes()
        legacy = runlog.start_run("legacy")
        runlog.end_run(legacy, "done")
        rows = runlog.strict_rows(runlog._INDEX)
        self.assertEqual([row for row in rows if "_fabric_portfolio" in row],
                         [json.loads(line) for line in before.splitlines()])
        self.assertTrue(any(row.get("run_id") == legacy for row in rows))
        with self.assertRaises(runlog.PortfolioRunError):
            runlog.portfolio_lookup()

    def test_torn_index_is_preserved_by_legacy_end(self):
        self.claim()
        runlog._INDEX.write_bytes(runlog._INDEX.read_bytes()[:-5])
        before = runlog._INDEX.read_bytes()
        legacy = runlog.start_run("legacy")
        runlog.end_run(legacy, "done")
        self.assertEqual(runlog._INDEX.read_bytes(), before)
        with self.assertRaises(runlog.PortfolioRunError):
            runlog.portfolio_lookup()

    def test_legacy_end_preserves_and_durably_rewrites_valid_anchor(self):
        self.claim()
        legacy = runlog.start_run("legacy")
        real = runlog.durable_replace
        writes = []
        def replace(path, raw, *, expected):
            writes.append(path)
            return real(path, raw, expected=expected)
        with patch.object(runlog, "durable_replace", side_effect=replace):
            runlog.end_run(legacy, "legacy completed")
        self.assertIn(runlog._INDEX, writes)
        self.assertEqual(runlog.portfolio_lookup()["state"]["run_id"], self.ident)

    def test_anchor_visible_but_missing_run_remains_held_after_claim_lost_ack(self):
        real = runlog.durable_replace
        def replace(path, raw, *, expected):
            if path.name == self.ident + ".jsonl":
                raise OSError("fixture before run file")
            return real(path, raw, expected=expected)
        with patch.object(runlog, "durable_replace", side_effect=replace), self.assertRaises(OSError):
            self.claim()
        with self.assertRaises(runlog.PortfolioRunError):
            runlog.portfolio_lookup()
        runlog.log_step(self.ident, "legacy", "late native writer", "must not create")
        self.assertFalse(runlog._run_path(self.ident).exists())

    def test_semantically_invalid_complete_cannot_release_original_custody(self):
        self.claim()
        path = runlog._run_path(self.ident)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        envelope = rows[1]["_fabric_portfolio"]
        envelope["state"]["phase"] = "complete"
        envelope["digest"] = runlog.digest(envelope["state"])
        path.write_bytes(b"".join(runlog.canonical(row)+b"\n" for row in rows))
        with self.assertRaises(runlog.PortfolioRunError):
            runlog.portfolio_lookup()

    def test_private_protocol_does_not_enter_public_projection(self):
        self.claim()
        for value in (runlog.list_runs(), runlog.read_run(self.ident)):
            raw = json.dumps(value)
            self.assertNotIn("_fabric_portfolio", raw)
            self.assertNotIn("directive", raw)
            self.assertNotIn("request_digest", raw)

    def test_closed_ids_duplicate_keys_nonfinite_and_symlinks_refuse(self):
        for ident in ("", "error", "../escape", "a" * 97, "line\nbreak"):
            with self.subTest(ident=ident), self.assertRaises(runlog.PortfolioRunError):
                runlog.portfolio_id(ident)
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '{"a":[-1e999]}'):
            with self.subTest(raw=raw), self.assertRaises(runlog.PortfolioRunError):
                runlog.strict_json(raw)
        original = self.root / "original"
        original.write_text("{}")
        link = self.root / "redirected"
        link.symlink_to(original)
        with self.assertRaises(runlog.PortfolioRunError):
            runlog.strict_read(link)
        directory = self.root / "directory"
        directory.mkdir()
        (directory / "receipt").write_text("{}")
        redirected = self.root / "redirected-directory"
        redirected.symlink_to(directory, target_is_directory=True)
        with self.assertRaises(runlog.PortfolioRunError):
            runlog.strict_read(redirected / "receipt")
        with self.assertRaises(runlog.PortfolioRunError):
            runlog.strict_read(redirected / "missing", absent=True)

    def test_known_subtotal_unknown_cost_and_usage_are_retained_once(self):
        observations = self.observations()
        receipt = cost_guard.record_fabric("autonomous", self.ident, self.day, observations)
        self.assertIsNone(receipt["cost_usd"])
        self.assertIsNone(receipt["observations"][0]["output_tokens"])
        self.assertEqual(cost_guard.record_fabric("autonomous", self.ident, self.day, observations), receipt)
        row = cost_guard._strict_cost(self.day)[1]["autonomous"]
        self.assertEqual(row["input_tokens"], 11)
        self.assertEqual(row["calls"], 1)
        self.assertEqual(row["unknown_usage_calls"], 1)
        self.assertEqual(row["unpriced_provider_calls"], 1)
        changed = copy.deepcopy(observations)
        changed[0]["input_tokens"] = 12
        with self.assertRaises(runlog.PortfolioRunError):
            cost_guard.record_fabric("autonomous", self.ident, self.day, changed)

    def test_lost_cost_write_ack_recovers_exact_receipt_without_counting_twice(self):
        real = runlog.durable_replace
        def replace(path, raw, *, expected):
            real(path, raw, expected=expected)
            raise OSError("fixture lost final acknowledgement")
        with patch.object(runlog, "durable_replace", side_effect=replace), self.assertRaises(OSError):
            cost_guard.record_fabric("autonomous", self.ident, self.day, self.observations())
        before = cost_guard._path(self.day).read_bytes()
        sync = runlog.durable_existing
        seen = []
        def reconcile(path, raw):
            seen.append(path)
            return sync(path, raw)
        with patch.object(runlog, "durable_existing", side_effect=reconcile):
            cost_guard.record_fabric("autonomous", self.ident, self.day, self.observations())
        self.assertEqual(cost_guard._path(self.day).read_bytes(), before)
        self.assertEqual(seen, [cost_guard._path(self.day)])

    def test_legacy_cost_update_uses_strict_original_snapshot_and_preserves_receipt(self):
        cost_guard.record_fabric("autonomous", self.ident, self.day, self.observations())
        with patch.object(cost_guard, "_load", side_effect=AssertionError("permissive reload")):
            cost_guard.record("autonomous", 2.5, self.day, input_tokens=3, output_tokens=4, seat="native")
        row = cost_guard._strict_cost(self.day)[1]["autonomous"]
        self.assertIn(self.ident, row["fabric_operations"])
        self.assertEqual(row["input_tokens"], 14)
        self.assertEqual(row["output_tokens"], 4)
        self.assertEqual(row["calls"], 2)
        self.assertEqual(row["usd"], 2.5)

    def test_partial_cost_ledger_never_means_zero_or_gets_overwritten(self):
        path = cost_guard._path(self.day)
        path.parent.mkdir(parents=True)
        path.write_bytes(b'{"autonomous":{"fabric_operations":')
        before = path.read_bytes()
        with self.assertRaises(runlog.PortfolioRunError):
            cost_guard.fabric_over_budget("autonomous", self.day)
        cost_guard.record("autonomous", 3.0, self.day)
        self.assertEqual(path.read_bytes(), before)

    def test_tool_schema_types_unknown_fields_duplicate_ids_and_nonfinite_are_closed(self):
        roster, _ = F.catalog()
        valid = {"type": "tool_use", "id": "read-1", "name": "mcp__desk__get_prophet_board", "input": {"limit": 2}}
        self.assertEqual(F._calls([valid], roster, set()), [valid])
        invalid = [
            {**valid, "input": {"limit": True}},
            {**valid, "input": {"limit": 2.0}},
            {**valid, "input": {"limit": 2, "book": "flagship"}},
            {**valid, "name": "WebSearch"},
            {**valid, "input": {"limit": float("inf")}},
            {"type": "image", "source": {"type": "base64", "data": "fixture"}},
        ]
        for index, candidate in enumerate(invalid):
            candidate = copy.deepcopy(candidate)
            if candidate.get("type") == "tool_use":
                candidate["id"] = f"bad-{index}"
            with self.subTest(candidate=candidate), self.assertRaises(runlog.PortfolioRunError):
                F._calls([valid, candidate], roster, set())
        with self.assertRaises(runlog.PortfolioRunError):
            F._calls([valid], roster, {"read-1"})

    def test_public_projection_uses_run_revision_instead_of_stale_index_counts(self):
        doc = self.claim()
        doc["state"]["error"] = "PRIVATE_SENTINEL_ERROR"
        runlog.portfolio_save(doc)
        rows = runlog.strict_rows(runlog._INDEX)
        rows[0].update(n_steps=999, summary="PRIVATE_SENTINEL_INDEX")
        runlog._INDEX.write_bytes(b"".join(runlog.canonical(row)+b"\n" for row in rows))
        index, detail = runlog.list_runs()[0], runlog.read_run(self.ident)
        self.assertEqual(index["n_steps"], 0)
        self.assertEqual(index["projection_revision"], doc["revision"])
        self.assertEqual(detail["projection_revision"], doc["revision"])
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps([index, detail]))
        path = runlog._run_path(self.ident)
        path.write_bytes(path.read_bytes()[:-1])
        unavailable = runlog.list_runs()[0]
        self.assertIsNone(unavailable["n_steps"])
        self.assertEqual(unavailable["status"], "unavailable")



if __name__ == "__main__":
    unittest.main()
