"""Exact 0.5.15 Paper catalog successor. Synthetic proof, not a live M1 write."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("paper_catalog_015_bridge", ROOT / "integrations/paper_desktop/bridge.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
CATALOG_ROOT = ROOT / "tests/fixtures/paper_desktop"
PREVIOUS = json.loads((CATALOG_ROOT / "1b9aff_full_catalog.json").read_text())
CURRENT = json.loads((CATALOG_ROOT / "f3483_full_catalog.json").read_text())


class CatalogTests(unittest.TestCase):
    def test_exact_catalogs_are_only_approved_known_digests(self):
        self.assertEqual(len(PREVIOUS), 37)
        self.assertEqual(len(CURRENT), 37)
        self.assertEqual(b.digest(PREVIOUS), b.SUPPORTED_CATALOG_SHA256)
        self.assertEqual(b.digest(CURRENT), "f3483e001d4f07f5a49144ca52a4f9e14ba046e35546dda05d6cd37c9d2b4728")
        self.assertIn(b.digest(CURRENT), b.REVIEWED_CATALOG_SHA256_ALTERNATES)
        modified = {k for k in CURRENT if CURRENT[k] != PREVIOUS[k]}
        self.assertEqual(modified, {"get_jsx"})
        self.assertEqual(CURRENT["get_jsx"]["inputSchema"]["properties"]["format"]["enum"],
                         ["inline-styles", "tailwind"])
        for catalog in (PREVIOUS, CURRENT):
            self.assertEqual(set(catalog), set(PREVIOUS))
            self.assertEqual(set(catalog["create_file"]), set(PREVIOUS["create_file"]))
            self.assertEqual(catalog["create_file"], PREVIOUS["create_file"])
            self.assertEqual(catalog["arrange_pages"], PREVIOUS["arrange_pages"])
            self.assertEqual(catalog["update_pages"], PREVIOUS["update_pages"])

    def test_exact_receipt_accepts_both_without_loosening_rejection(self):
        class Client:
            server = {"name": "paper-desktop", "version": "0.5.15"}
        for catalog in (PREVIOUS, CURRENT):
            v = b.schema_receipt(Client(), catalog)
            self.assertTrue(v["accepted_for_write"])
            self.assertTrue(v["catalog_compatible"])
        for name in ("get_jsx", "create_file", "delete_nodes"):
            mutated = copy.deepcopy(CURRENT)
            mutated[name]["description"] += " drift"
            self.assertFalse(b.schema_receipt(Client(), mutated)["accepted_for_write"])

    def test_explicit_custom_pin_does_not_inherit_unrelated_compatibility(self):
        class Client:
            server = {"name": "paper-desktop", "version": "0.5.15"}
        other = "0" * 64
        self.assertFalse(b.schema_receipt(Client(), CURRENT, catalog_pin=other)["accepted_for_write"])
        self.assertFalse(b.schema_receipt(Client(), CURRENT, server_pin=("other-desktop", None))["accepted_for_write"])


if __name__ == "__main__":
    unittest.main()
