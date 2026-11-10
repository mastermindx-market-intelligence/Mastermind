"""Guarded Paper resource and page tools: synthetic tests, not live acceptance."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("paper_file_mgmt_bridge", ROOT / "integrations/paper_desktop/bridge.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
FILE_ID = "01M2WGNCX9475G79JRKJTCM08P"


class Fake:
    def __init__(self):
        self.server = {"name": "paper-desktop", "version": "0.5.14"}
        self.catalog_data = json.loads((ROOT / "tests/fixtures/paper_desktop/1b9aff_full_catalog.json").read_text())
        self.calls = []
        self.name = "Source"
        self.error = False

    def initialize(self):
        pass

    def catalog(self):
        return self.catalog_data

    def call(self, name, args):
        self.calls.append((name, dict(args)))
        if name == "get_basic_info":
            return {"structuredContent": {"file": {"id": FILE_ID, "name": self.name}},
                    "content": [{"type": "text", "text": json.dumps(
                        {"fileName": self.name, "pageName": "Page 1", "pageId": "p-1-0",
                         "pages": [{"type": "page", "id": "p-1-0", "name": "Page 1"}],
                         "artboards": [], "nodeCount": 0})}]}
        if self.error:
            raise TimeoutError("upstream response lost")
        if name == "rename_resource":
            self.name = args["name"].strip()
        return {"content": [{"type": "text", "text": json.dumps(
            {"fileId": "NEWFILEID" if name == "create_file" else FILE_ID})}]}


class FileManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = Fake()

    def tearDown(self):
        self.tmp.cleanup()

    def run_action(self, tool, args, action="file_manage", **extras):
        kw = dict(tool=tool, arguments=args,
                  expected_snapshot=b.snapshot(self.client, FILE_ID)["snapshot_sha256"],
                  operation_id="paper-file-mgmt-proof", allow_write=True,
                  client=self.client, lock_root=Path(self.tmp.name))
        kw.update(extras)
        return b.execute(action, **kw)

    def test_catalog_preserves_exact_pin_and_management_classification(self):
        result = b.execute("catalog", client=self.client, lock_root=Path(self.tmp.name))
        self.assertTrue(result["write_schema"]["accepted_for_write"])
        indexed = {x["name"]: x["bridge_access"] for x in result["tools"]}
        for name in ("list_resources",):
            self.assertEqual(indexed[name], "read")
        for name in ("create_file", "rename_resource"):
            self.assertEqual(indexed[name], "edit")
        for name in ("arrange_pages", "update_pages"):
            self.assertEqual(indexed[name], "edit")
        for name in ("delete_nodes", "export", "open_file"):
            self.assertIn(name, result["blocked_tools"])

    def test_create_blank_file_with_guarded_existing_file_context(self):
        result = self.run_action("create_file", {"sourceFileId": FILE_ID, "name": "Crypto"})
        self.assertEqual(result["state"], "RESPONSE_OBSERVED_REQUIRES_TARGET_VERIFICATION")
        self.assertIn(("create_file", {"name": "Crypto"}), self.client.calls)
        self.assertEqual(result["before"]["identity"]["id"], FILE_ID)

    def test_existing_paper_edit_action_handles_file_admin_for_published_clients(self):
        result = self.run_action("create_file", {"cloneFileId": FILE_ID, "name": "Ready"}, action="edit")
        self.assertEqual(result["state"], "RESPONSE_OBSERVED_REQUIRES_TARGET_VERIFICATION")
        self.assertIn(("create_file", {"cloneFileId": FILE_ID, "name": "Ready"}), self.client.calls)
        renamed = self.run_action("rename_resource", {"resourceId": FILE_ID, "name": "Renamed"}, action="edit")
        self.assertEqual(renamed["state"], "APPLIED_RESPONSE_OBSERVED")
        self.assertIn(("rename_resource", {"resourceId": FILE_ID, "name": "Renamed"}), self.client.calls)

    def test_blank_names_are_rejected_without_file_creation(self):
        for invalid in ("", "  ", "x" * 501, 6):
            with self.subTest(name=invalid), self.assertRaisesRegex(b.Refusal, "FILE_NAME_REQUIRED"):
                self.run_action("create_file", {"sourceFileId": FILE_ID, "name": invalid}, action="edit")
        self.assertFalse(any(name == "create_file" for name, _ in self.client.calls))

    def test_clone_full_file_retains_original(self):
        result = self.run_action("create_file", {"cloneFileId": FILE_ID, "name": "Crypto Archive"})
        self.assertEqual(result["state"], "RESPONSE_OBSERVED_REQUIRES_TARGET_VERIFICATION")
        self.assertIn(("create_file", {"cloneFileId": FILE_ID, "name": "Crypto Archive"}), self.client.calls)

    def test_exact_file_rename_requires_postread(self):
        result = self.run_action("rename_resource", {"resourceId": FILE_ID, "name": "New name"})
        self.assertEqual(result["state"], "APPLIED_RESPONSE_OBSERVED")
        self.assertEqual(result["after"]["basic_info"]["fileName"], "New name")

    def test_wrong_resource_type_or_folder_id_refused_before_dispatch(self):
        for args in ({"resourceId": "folder-A", "name": "oops"},
                     {"name": "Unbound"},
                     {"cloneFileId": FILE_ID, "sourceFileId": FILE_ID, "name": "ambiguous"}):
            with self.subTest(args=args), self.assertRaises(b.Refusal):
                self.run_action("create_file" if "resourceId" not in args else "rename_resource", args)
        self.assertFalse(any(x[0] in b.FILE_MANAGE_TOOLS for x in self.client.calls))

    def test_delete_and_raw_file_transition_remain_blocked(self):
        for name in ("delete_nodes", "open_file", "rename_pages"):
            with self.subTest(tool=name), self.assertRaisesRegex(b.Refusal, "TOOL_NOT_ALLOWED"):
                self.run_action(name, {"fileId": FILE_ID})

    def test_upstream_error_is_effect_unknown_never_retry(self):
        self.client.error = True
        result = self.run_action("create_file", {"sourceFileId": FILE_ID, "name": "Maybe"})
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertFalse(result["retry_allowed"])

    def test_page_management_requires_write_and_exact_guard(self):
        for name, args in (
            ("arrange_pages", {"fileId": FILE_ID, "order": ["p-1-0"]}),
            ("update_pages", {"fileId": FILE_ID, "updates": [{"pageId": "p-1-0", "name": "New"}]}),
        ):
            with self.subTest(tool=name):
                self.assertEqual(self.run_action(name, args, action="edit")["state"],
                                 "APPLIED_RESPONSE_OBSERVED")
                with self.assertRaisesRegex(b.Refusal, "DOCUMENT_CHANGED"):
                    self.run_action(name, args, action="edit", expected_snapshot="0"*64)


if __name__ == "__main__":
    unittest.main()
