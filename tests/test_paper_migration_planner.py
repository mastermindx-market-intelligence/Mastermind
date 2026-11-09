"""Pure offline failure-injection tests: no Paper calls, no modifying operation."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import paper_migration_planner as planner  # noqa: E402

INVENTORY = ROOT / "docs/paper_migrations/MASTERMIND_PAGES_INVENTORY_2026-10-22.json"


class PaperMigrationPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads(INVENTORY.read_text(encoding="utf-8"))

    def test_inventory_totals_and_unique_page_coverage(self):
        plan = planner.make_plan(self.original)
        self.assertEqual(plan["counts"]["source_pages"], 63)
        self.assertEqual(plan["counts"]["source_nodes"], 139812)
        self.assertEqual(plan["counts"]["source_artboards"], 903)
        a = [x["source_page_id"] for x in plan["whole_page_assignments"]]
        h = [x["source_page_id"] for x in plan["pages_requiring_artboard_census"]]
        self.assertEqual(len(a + h), len(set(a + h)))
        self.assertEqual(set(a + h), {p["source_page_id"] for p in self.original["pages"]})
        self.assertFalse(plan["source_deletion_authorized"])
        self.assertEqual(plan["paper_files_created"], 0)
        self.assertEqual(plan["paper_pages_moved"], 0)
        self.assertEqual(plan["unresolved_drift"][0]["source_page_id"], "p-19-0")

    def test_heavy_pages_never_assigned_as_whole_page_volume(self):
        plan = planner.make_plan(self.original)
        flagged = {x["source_page_id"] for x in plan["pages_requiring_artboard_census"]}
        for page in ("p-N-1", "p-Z-0", "p-8-1", "p-1A-0", "p-24-0", "p-L-0"):
            self.assertIn(page, flagged)
        for family in plan["destinations"]:
            for volume in family["volumes"]:
                self.assertLessEqual(volume["planned_nodes"], planner.DEFAULT_NODE_TARGET)
                self.assertLessEqual(volume["planned_artboards"], planner.DEFAULT_ARTBOARD_TARGET)

    def test_reordered_inventory_produces_identical_plan(self):
        scrambled = copy.deepcopy(self.original)
        scrambled["pages"].reverse()
        self.assertEqual(planner.make_plan(scrambled)["destinations"],
                         planner.make_plan(self.original)["destinations"])
        self.assertEqual(planner.make_plan(scrambled)["whole_page_assignments"],
                         planner.make_plan(self.original)["whole_page_assignments"])

    def test_duplicate_pages_are_refused(self):
        modified = copy.deepcopy(self.original)
        modified["pages"].append(copy.deepcopy(modified["pages"][0]))
        with self.assertRaisesRegex(planner.InventoryError, "Duplicate"):
            planner.make_plan(modified)

    def test_spoofed_status_and_wrong_file_link_refused(self):
        for field, bad in (("status", "MIGRATED"), ("source_url", "https://evil.invalid"),
                           ("source_file_id", "wrong")):
            with self.subTest(field=field):
                modified = copy.deepcopy(self.original)
                modified["pages"][0][field] = bad
                with self.assertRaises(planner.InventoryError):
                    planner.make_plan(modified)

    def test_tampered_totals_or_unknown_page_refused(self):
        altered = copy.deepcopy(self.original)
        altered["total_observed_artboards"] -= 1
        with self.assertRaisesRegex(planner.InventoryError, "totals mismatch"):
            planner.make_plan(altered)
        altered = copy.deepcopy(self.original)
        altered["pages"][0]["source_page_id"] = "p-19-0"
        altered["pages"][0]["source_url"] = planner.SOURCE_PREFIX + "p-19-0"
        with self.assertRaisesRegex(planner.InventoryError, "p-19-0"):
            planner.make_plan(altered)

    def test_false_or_negative_counts_refused(self):
        for bad in (True, 0, -1, 1.5):
            with self.subTest(bad=bad):
                altered = copy.deepcopy(self.original)
                altered["pages"][0]["node_count"] = bad
                with self.assertRaises(planner.InventoryError):
                    planner.make_plan(altered)

    def test_cli_generate_then_verify_and_deny_mutation_of_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / "plan.json"
            script = ROOT / "scripts/paper_migration_planner.py"
            base = [sys.executable, str(script), "--inventory", str(INVENTORY)]
            generated = subprocess.run(base + ["--out", str(manifest)],
                                       capture_output=True, text=True)
            self.assertEqual(generated.returncode, 0, generated.stderr)
            check = subprocess.run(base + ["--check-plan", str(manifest)],
                                   capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stderr)
            changed = json.loads(manifest.read_text(encoding="utf-8"))
            changed["source_deletion_authorized"] = True
            manifest.write_text(json.dumps(changed), encoding="utf-8")
            refused = subprocess.run(base + ["--check-plan", str(manifest)],
                                     capture_output=True, text=True)
            self.assertEqual(refused.returncode, 2)
            self.assertIn("MIGRATION_PREFLIGHT_REFUSED", refused.stderr)

    def test_out_cannot_overwrite_original_inventory_or_existing_report(self):
        script = ROOT / "scripts/paper_migration_planner.py"
        base = [sys.executable, str(script), "--inventory", str(INVENTORY)]
        original_bytes = INVENTORY.read_bytes()
        denied = subprocess.run(base + ["--out", str(INVENTORY)],
                                capture_output=True, text=True)
        self.assertEqual(denied.returncode, 2)
        self.assertEqual(INVENTORY.read_bytes(), original_bytes)
        with tempfile.TemporaryDirectory() as folder:
            existing = Path(folder) / "existing.json"
            existing.write_text("preserve", encoding="utf-8")
            denied = subprocess.run(base + ["--out", str(existing)],
                                    capture_output=True, text=True)
            self.assertEqual(denied.returncode, 2)
            self.assertEqual(existing.read_text(encoding="utf-8"), "preserve")

    def _six_terminal_page_delta(self):
        return json.loads((ROOT / "docs/paper_migrations/MASTERMIND_PAGES_DRIFT_2026-10-22.json").read_text(encoding="utf-8"))

    def test_visibility_delta_holds_six_absent_terminal_pages(self):
        missing = self._six_terminal_page_delta()
        plan = planner.make_plan(self.original, visibility_delta=missing)
        self.assertEqual(plan["counts"]["last_observed_visible_pages"], 57)
        self.assertTrue(plan["source_visibility_is_currently_unverified"])
        self.assertEqual(plan["counts"]["whole_page_planning_candidates"], 51)
        self.assertEqual(plan["counts"]["externally_absent_pages"], 6)
        ids = {p["source_page_id"] for p in plan["externally_absent_unproven_pages"]}
        self.assertEqual(ids, {p["source_page_id"] for p in missing["unobserved_baseline_pages"]})
        self.assertFalse(ids.intersection({p["source_page_id"] for p in plan["whole_page_assignments"]}))
        self.assertFalse(plan["source_deletion_authorized"])

    def test_visibility_delta_requires_complete_exact_observation(self):
        for mutate in (
            lambda d: d.pop("observed_visible_page_ids"),
            lambda d: d["observed_visible_page_ids"].pop(),
            lambda d: d["observed_visible_page_ids"].append(d["observed_visible_page_ids"][0]),
            lambda d: d.update(visible_page_list_truncated=True),
            lambda d: d["unobserved_baseline_pages"][0].update(source_url="fake"),
            lambda d: d["unobserved_baseline_pages"][0].update(baseline_nodes=9),
            lambda d: d.update(baseline_nodes_associated_with_unobserved_pages=0),
            lambda d: d["observed_visible_page_ids"].append({"invalid": "unhashable"}),
            lambda d: d["unobserved_baseline_pages"][0].update(source_page_id=["unhashable"]),
        ):
            delta = self._six_terminal_page_delta()
            mutate(delta)
            with self.assertRaises(planner.InventoryError):
                planner.make_plan(self.original, visibility_delta=delta)

    def test_tampered_visibility_delta_fail_closed(self):
        for change in ({"current_visible_page_count": 58}, {"added_visible_page_ids": ["p-NEW-0"]},
                       {"source_file_id": "other"}):
            delta = self._six_terminal_page_delta()
            delta.update(change)
            with self.assertRaises(planner.InventoryError):
                planner.make_plan(self.original, visibility_delta=delta)

    def test_cli_visibility_delta_changes_plan_and_checks_exactly(self):
        script = ROOT / "scripts/paper_migration_planner.py"
        with tempfile.TemporaryDirectory() as folder:
            vis = Path(folder) / "delta.json"
            out = Path(folder) / "plan.json"
            vis.write_text(json.dumps(self._six_terminal_page_delta()), encoding="utf-8")
            args = [sys.executable, str(script), "--inventory", str(INVENTORY),
                    "--visibility-delta", str(vis)]
            created = subprocess.run(args + ["--out", str(out)], capture_output=True, text=True)
            self.assertEqual(created.returncode, 0, created.stderr)
            observed = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(observed["counts"]["externally_absent_pages"], 6)
            confirmed = subprocess.run(args + ["--check-plan", str(out)], capture_output=True, text=True)
            self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
            missing_delta = subprocess.run([sys.executable, str(script), "--inventory", str(INVENTORY),
                                            "--check-plan", str(out)], capture_output=True, text=True)
            self.assertEqual(missing_delta.returncode, 2)

    def test_node_and_board_targets_are_planning_only(self):
        with self.assertRaises(planner.InventoryError):
            planner.make_plan(self.original, node_target=0)
        plan = planner.make_plan(self.original, node_target=1000, artboard_target=4)
        self.assertFalse(plan["source_deletion_authorized"])
        self.assertGreater(plan["counts"]["pages_requiring_artboard_census"], 6)


if __name__ == "__main__":
    unittest.main()
