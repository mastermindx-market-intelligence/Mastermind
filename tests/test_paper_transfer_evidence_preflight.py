"""Fail-closed transfer mapping checks; all evidence is synthetic."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import paper_transfer_evidence_preflight as preflight
from paper_migration_planner import inventory_fingerprint, InventoryError

FIX = ROOT / "docs/paper_migrations"
INVENTORY = json.loads((FIX / "MASTERMIND_PAGES_INVENTORY_2026-10-22.json").read_text())
DELTA = json.loads((FIX / "MASTERMIND_PAGES_DRIFT_2026-10-22.json").read_text())
HEAVY = {"schema": "mastermind.paper-oversize-artboard-index.v1", "source_file_id": INVENTORY["source_file_id"],
         "pages": [{"source_page_id": "p-N-1", "artboard_count": 2,
                    "artboards": [{"source_artboard_id": x} for x in ["1AMJ-1", "6NKK-0"]]}]}
DEST_FILE = "01M3P1TW5Y3XWQC37ADDS8K5AG"


def base_claim(page="p-N-1", board="6NKK-0"):
    return {"schema": preflight.SCHEMA, "source_file_id": INVENTORY["source_file_id"],
            "source_inventory_sha256": inventory_fingerprint(INVENTORY),
            "source_visibility_delta_sha256": inventory_fingerprint(DELTA),
            "units": [{"source_page_id": page, "source_artboard_id": board,
                       "destination_file_id": DEST_FILE, "destination_page_id": "p-1-0",
                       "destination_artboard_id": "6ABC-0", "operation_id": "native-test-0001",
                       "transfer_mechanism": "REVIEWED_NATIVE_EDITABLE_COPY",
                       "effect_state": "RESPONSE_OBSERVED_REQUIRES_TARGET_VERIFICATION",
                       "evidence_refs": {"source_read": "fixture/source-read.json", "target_read": "fixture/target-read.json"}}]}


class TransferEvidenceTests(unittest.TestCase):
    def check(self, claim):
        return preflight.validate_evidence_manifest(INVENTORY, DELTA, HEAVY, claim)

    def test_pass_does_not_accept_fidelity_or_source_deletion(self):
        report = self.check(base_claim())
        self.assertEqual(report["units_checked"], 1)
        self.assertTrue(report["units"][0]["source_index_qualified"])
        self.assertEqual(report["units_needing_fidelity_evidence"], 1)
        self.assertFalse(report["source_deletion_authorized"])
        self.assertTrue(report["unresolved_source_drift"])

    def test_unknown_or_absent_source_page_rejected(self):
        for pid in ("p-21-0", "p-X999-0"):
            item = base_claim()
            item["units"][0]["source_page_id"] = pid
            with self.assertRaises(InventoryError):
                self.check(item)

    def test_capped_101st_forex_board_index_is_supported(self):
        self.assertEqual(self.check(base_claim())["units"][0]["source_artboard_id"], "6NKK-0")
        wrong = base_claim(board="6XXX-0")
        with self.assertRaises(InventoryError):
            self.check(wrong)

    def test_wrong_target_or_fake_transfer_mechanism_rejected(self):
        for field, value in (("destination_file_id", INVENTORY["source_file_id"]),
                             ("destination_file_id", "not-a-file"),
                             ("destination_page_id", "bad"),
                             ("transfer_mechanism", "FLATTENED_JSX")):
            claim = base_claim()
            claim["units"][0][field] = value
            with self.assertRaises(InventoryError):
                self.check(claim)

    def test_stale_digest_and_wrong_index_refused(self):
        claim = base_claim()
        claim["source_visibility_delta_sha256"] = "0" * 64
        with self.assertRaises(InventoryError):
            self.check(claim)
        bad = copy.deepcopy(HEAVY)
        bad["pages"][0]["artboards"].pop()
        with self.assertRaises(InventoryError):
            preflight.validate_evidence_manifest(INVENTORY, DELTA, bad, base_claim())

    def test_duplicate_source_or_target_or_operation_refused(self):
        for alter in ("destination_artboard_id", "source_artboard_id", "operation_id"):
            claim = base_claim()
            second = copy.deepcopy(claim["units"][0])
            if alter == "destination_artboard_id":
                second["source_artboard_id"] = "1AMJ-1"
                second["operation_id"] = "native-test-0002"
            elif alter == "source_artboard_id":
                second["destination_artboard_id"] = "6ABD-0"
                second["operation_id"] = "native-test-0002"
            elif alter == "operation_id":
                second["source_artboard_id"] = "1AMJ-1"
                second["destination_artboard_id"] = "6ABD-0"
            claim["units"].append(second)
            with self.assertRaises(InventoryError):
                self.check(claim)

    def test_effect_unknown_and_missing_readback_refused(self):
        claim = base_claim()
        claim["units"][0]["effect_state"] = "EFFECT_UNKNOWN"
        with self.assertRaises(InventoryError):
            self.check(claim)
        claim = base_claim()
        claim["units"][0]["evidence_refs"] = {"source_read": "fixture/a"}
        with self.assertRaises(InventoryError):
            self.check(claim)

    def test_unknown_small_page_requires_board_census(self):
        claim = base_claim(page="p-16-0", board="1234-0")
        report = self.check(claim)
        self.assertEqual(report["units_needing_source_artboard_census"], 1)
        self.assertFalse(report["source_deletion_authorized"])


if __name__ == "__main__":
    unittest.main()
