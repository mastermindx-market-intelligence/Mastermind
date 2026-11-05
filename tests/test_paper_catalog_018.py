"""Paper 0.5.18 exact full-catalog review; no live design modification."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("paper_catalog_018_bridge", ROOT / "integrations/paper_desktop/bridge.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
P = ROOT / "tests/fixtures/paper_desktop"
PREVIOUS = json.loads((P / "1b9aff_full_catalog.json").read_text())
CURRENT = json.loads((P / "16e6b_full_catalog.json").read_text())
ADDED_BLOCKED = {"archive_resources", "create_folder", "move_resources", "unarchive_resources"}
CHANGED = {"create_file", "export", "export_combined_pdf", "get_comment_thread",
           "get_jsx", "get_node_info", "list_resources", "set_text_content",
           "update_styles", "write_html"}


class Client:
    def __init__(self):
        self.server = {"name": "paper-desktop", "version": "0.5.18"}
        self.calls = []
        self.counter = 0

    def initialize(self):
        return {}

    def catalog(self):
        return copy.deepcopy(CURRENT)

    def call(self, name, arguments):
        self.calls.append((name, copy.deepcopy(arguments)))
        if name == "get_basic_info":
            return {"structuredContent": {
                "fileId": "paper-scratch-fixture", "fileName": "Scratch",
                "pageName": "Page", "pageId": "page-fixture",
                "nodeCount": 1, "artboards": [
                    {"id": "board-fixture", "name": "Board", "width": 800, "height": 600}],
                "contentHash": {"tokens": "stable"}
            }}
        return {"content": [{"type": "text", "text": "ok"}]}


class PaperCatalog018Tests(unittest.TestCase):
    def test_exact_catalog_and_full_delta(self):
        self.assertEqual(len(PREVIOUS), 37)
        self.assertEqual(len(CURRENT), 41)
        self.assertEqual(b.digest(PREVIOUS), b.SUPPORTED_CATALOG_SHA256)
        self.assertEqual(b.digest(CURRENT), b.PAPER_RICH_TEXT_CATALOG_SHA256)
        self.assertEqual(set(PREVIOUS) - set(CURRENT), set())
        self.assertEqual(set(CURRENT) - set(PREVIOUS), ADDED_BLOCKED)
        self.assertEqual({name for name in PREVIOUS if PREVIOUS[name] != CURRENT[name]}, CHANGED)
        self.assertEqual(CURRENT["get_jsx"]["inputSchema"]["properties"]["format"]["enum"],
                         ["inline-styles", "tailwind"])

    def test_rich_html_is_required_and_file_management_not_broadened(self):
        item = CURRENT["set_text_content"]["inputSchema"]["properties"]["updates"]["items"]
        self.assertEqual(item["required"], ["nodeId", "html"])
        self.assertNotIn("textContent", item["properties"])
        self.assertFalse(item["additionalProperties"])
        self.assertEqual(CURRENT["set_text_content"]["inputSchema"]["required"], ["updates", "fileId"])
        self.assertIn("parentId", CURRENT["create_file"]["inputSchema"]["properties"])
        self.assertIn("includeArchived", CURRENT["list_resources"]["inputSchema"]["properties"])
        self.assertTrue(ADDED_BLOCKED.isdisjoint(b.READ_TOOLS | b.EDIT_TOOLS | b.FILE_MANAGE_TOOLS))

    def test_strict_receipt_refuses_name_schema_and_identity_drift(self):
        c = Client()
        self.assertTrue(b.schema_receipt(c, CURRENT)["accepted_for_write"])
        changed = copy.deepcopy(CURRENT)
        changed["set_text_content"]["inputSchema"]["properties"]["updates"]["items"]["properties"]["html"]["type"] = "number"
        receipt = b.schema_receipt(c, changed)
        self.assertTrue(receipt["accepted_for_write"])
        self.assertNotIn("set_text_content", receipt["compatible_write_tools"])
        changed = copy.deepcopy(CURRENT)
        changed["archive_resources"]["description"] += " drift"
        self.assertTrue(b.schema_receipt(c, changed)["accepted_for_write"])
        self.assertFalse(b.schema_receipt(c, CURRENT, catalog_pin="0"*64)["accepted_for_write"])
        c.server["name"] = "other-server"
        self.assertFalse(b.schema_receipt(c, CURRENT)["accepted_for_write"])

    def test_blocked_resource_commands_never_dispatch(self):
        with tempfile.TemporaryDirectory() as p:
            c = Client()
            for name in sorted(ADDED_BLOCKED):
                with self.subTest(name=name):
                    with self.assertRaisesRegex(b.Refusal, "TOOL_NOT_ALLOWED"):
                        b.execute("read", tool=name, client=c, lock_root=Path(p))
                    with self.assertRaisesRegex(b.Refusal, "TOOL_NOT_ALLOWED"):
                        b.execute("edit", tool=name, arguments={"fileId": "paper-scratch-fixture"},
                                  expected_snapshot="a"*64, operation_id="blocked-resource-test",
                                  allow_write=True, client=c, lock_root=Path(p))
            self.assertEqual(c.calls, [])

    def test_legacy_text_content_refused_before_upstream_call(self):
        with tempfile.TemporaryDirectory() as p:
            c = Client()
            with self.assertRaisesRegex(b.Refusal, "PAPER_RICH_TEXT_SCHEMA_REQUIRED"):
                b.execute("edit", tool="set_text_content",
                          arguments={"fileId": "paper-scratch-fixture",
                                     "updates": [{"nodeId": "node-1", "textContent": "legacy"}]},
                          expected_snapshot="a"*64, operation_id="reject-old-payload",
                          allow_write=True, client=c, lock_root=Path(p))
            self.assertEqual(c.calls, [])

    def test_new_html_payload_preserves_target_snapshot_and_dispatches_once(self):
        with tempfile.TemporaryDirectory() as p:
            c = Client()
            before = b.snapshot(c, "paper-scratch-fixture")
            result = b.execute("edit", tool="set_text_content",
                       arguments={"fileId": "paper-scratch-fixture",
                                  "updates": [{"nodeId": "node-1", "html": "safe <b>copy</b>"}]},
                       expected_snapshot=before["snapshot_sha256"],
                       operation_id="supported-rich-html-payload",
                       allow_write=True, client=c, lock_root=Path(p))
            self.assertEqual(result["state"], "APPLIED_RESPONSE_OBSERVED")
            self.assertEqual([name for name,_ in c.calls].count("set_text_content"), 1)
            self.assertEqual(c.calls[-2][1]["updates"][0]["html"], "safe <b>copy</b>")


if __name__ == "__main__":
    unittest.main()
