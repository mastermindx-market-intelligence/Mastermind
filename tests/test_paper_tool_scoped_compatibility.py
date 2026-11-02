"""Paper upgrade resilience: unrelated schema drift cannot disable working writes.

Tests use original observed upstream catalogs and injected clients only.
They do not contact Paper, modify a design, or enroll a tunnel.
"""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "paper_tool_scoped_contract", ROOT / "integrations/paper_desktop/bridge.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

FIXTURES = ROOT / "tests/fixtures/paper_desktop"
FILES = ["1b9aff_full_catalog.json", "f3483_full_catalog.json",
         "955e92_full_catalog.json", "16e6b_full_catalog.json"]
CATALOGS = [json.loads((FIXTURES / name).read_text()) for name in FILES]
M2 = CATALOGS[-1]
READ_ONLY_4 = {"archive_resources", "create_folder", "move_resources",
               "unarchive_resources"}
FILE_ID = "01M2VWK62FA5S4VVF6G7SBPE5J"


class Client:
    def __init__(self, catalog=None, version="0.5.19"):
        self.server = {"name": "paper-desktop", "version": version}
        self.value = copy.deepcopy(M2 if catalog is None else catalog)
        self.calls = []
    def initialize(self):
        return {}
    def catalog(self):
        return copy.deepcopy(self.value)
    def call(self, name, arguments):
        self.calls.append((name, copy.deepcopy(arguments)))
        if name == "get_basic_info":
            return {"structuredContent": {
                "fileId": FILE_ID, "fileName": "Scratch",
                "pageId": "p-1-0", "pageName": "Page 1",
                "nodeCount": 1, "artboards": [{
                    "id": "artboard-1", "name": "QA",
                    "width": 1000, "height": 700}],
                "contentHash": {"tokens": "qa-only"}}}
        return {"content": [{"type": "text", "text": "success"}]}


class ContractResilienceTests(unittest.TestCase):
    def test_reviewed_policy_comes_from_original_known_fixtures(self):
        for cat in CATALOGS:
            with self.subTest(sha=b.digest(cat)):
                receipt = b.schema_receipt(Client(cat), cat)
                self.assertTrue(receipt["accepted_for_write"])
                self.assertTrue(receipt["full_catalog_known"])
                self.assertEqual(receipt["catalog_policy"], "TOOL_SCOPED_CONTRACT_V1")
                self.assertEqual(set(receipt["compatible_write_tools"]),
                                 (b.EDIT_TOOLS | b.FILE_MANAGE_TOOLS) & set(cat))
                for name in b.READ_TOOLS | b.EDIT_TOOLS | b.FILE_MANAGE_TOOLS:
                    if name in cat:
                        self.assertIsNotNone(b.compatible_tool_contract(name, cat[name]),
                                             name)

    def test_new_blocked_tools_and_description_drift_leave_existing_edits_live(self):
        cat = copy.deepcopy(M2)
        cat["brand_new_unapproved_tool"] = {
            "name": "brand_new_unapproved_tool", "description": "destructive",
            "annotations": {"destructiveHint": True},
            "inputSchema": {"type": "object", "properties": {}}}
        cat["archive_resources"]["description"] = "vendor changed explanatory prose"
        cat["write_html"]["description"] = "new instructional text"
        cat["set_text_content"]["inputSchema"]["properties"]["updates"]["description"] = "more docs"
        receipt = b.schema_receipt(Client(cat, "0.7.123"), cat)
        self.assertFalse(receipt["full_catalog_known"])
        self.assertTrue(receipt["accepted_for_write"])
        self.assertEqual(receipt["server_version_policy"], "OBSERVED_NOT_PINNED")
        self.assertIn("write_html", receipt["compatible_write_tools"])
        self.assertIn("set_text_content", receipt["compatible_write_tools"])
        self.assertNotIn("brand_new_unapproved_tool", receipt["compatible_write_tools"])
        with tempfile.TemporaryDirectory() as tmp:
            c = Client(cat)
            result = b.execute("catalog", client=c, lock_root=Path(tmp))
            blocked = result["blocked_tools"]
            self.assertIn("brand_new_unapproved_tool", blocked)
            self.assertTrue(READ_ONLY_4.issubset(set(blocked)))
            with self.assertRaisesRegex(b.Refusal, "TOOL_NOT_ALLOWED"):
                b.execute("edit", tool="brand_new_unapproved_tool",
                          arguments={"fileId": FILE_ID}, expected_snapshot="a"*64,
                          operation_id="blocked-new-tool", allow_write=True,
                          client=c, lock_root=Path(tmp))

    def test_harmless_schema_reordering_does_not_break_tool(self):
        cat = copy.deepcopy(M2)
        cat["set_text_content"]["inputSchema"]["required"].reverse()
        cat["get_jsx"]["inputSchema"]["properties"]["format"]["enum"].reverse()
        r = b.schema_receipt(Client(cat), cat)
        self.assertTrue(r["accepted_for_write"])
        self.assertIn("set_text_content", r["compatible_write_tools"])

    def test_new_optional_top_level_field_is_ignored_and_cannot_be_forwarded(self):
        cat = copy.deepcopy(M2)
        cat["write_html"]["inputSchema"]["properties"]["brandNewOptional"] = {
            "type": "boolean", "description": "extra future option"}
        r = b.schema_receipt(Client(cat), cat)
        self.assertTrue(r["accepted_for_write"])
        self.assertIn("write_html", r["compatible_write_tools"])
        self.assertIn("write_html", r["optional_vendor_inputs_ignored"])
        with tempfile.TemporaryDirectory() as tmp:
            c = Client(cat)
            guard = b.snapshot(c, FILE_ID)["snapshot_sha256"]
            with self.assertRaisesRegex(b.Refusal, "UNREVIEWED_TOOL_ARGUMENTS"):
                b.execute("edit", tool="write_html",
                          arguments={"fileId": FILE_ID, "brandNewOptional": True},
                          expected_snapshot=guard, operation_id="blocked-new-input",
                          allow_write=True, client=c, lock_root=Path(tmp))
            self.assertEqual([name for name, _ in c.calls].count("write_html"), 0)
            observed = b.execute("edit", tool="write_html",
                          arguments={"fileId": FILE_ID},
                          expected_snapshot=guard, operation_id="qualified-old-input",
                          allow_write=True, client=c, lock_root=Path(tmp))
            self.assertEqual(observed["state"], "APPLIED_RESPONSE_OBSERVED")
            self.assertEqual([name for name, _ in c.calls].count("write_html"), 1)

    def test_required_new_input_or_default_restricts_only_changed_tool(self):
        for variant in ("required", "default", "enum", "annotation"):
            with self.subTest(variant=variant):
                cat = copy.deepcopy(M2)
                w = cat["write_html"]
                if variant == "required":
                    w["inputSchema"]["properties"]["newRequired"] = {"type": "string"}
                    w["inputSchema"]["required"].append("newRequired")
                elif variant == "default":
                    w["inputSchema"]["properties"]["newOptional"] = {
                        "type": "boolean", "default": True}
                elif variant == "enum":
                    w["inputSchema"]["properties"]["mode"]["enum"] = ["new-unreviewed-mode"]
                else:
                    w["annotations"]["destructiveHint"] = False
                r = b.schema_receipt(Client(cat), cat)
                self.assertTrue(r["accepted_for_write"])
                self.assertNotIn("write_html", r["compatible_write_tools"])
                self.assertIn("create_artboard", r["compatible_write_tools"])
                with tempfile.TemporaryDirectory() as tmp:
                    c = Client(cat)
                    with self.assertRaisesRegex(b.Refusal, "TOOL_SCHEMA_CHANGED"):
                        b.execute("edit", tool="write_html",
                                  arguments={"fileId": FILE_ID},
                                  expected_snapshot="a"*64, operation_id="changed-tool",
                                  allow_write=True, client=c, lock_root=Path(tmp))
                    self.assertEqual(c.calls, [])

    def test_real_input_named_description_is_not_stripped_as_schema_prose(self):
        # Paper create_tokens includes a *user input* named description inside
        # tokens[].properties. That property is not documentation metadata.
        for name in ("create_tokens", "set_tokens"):
            with self.subTest(name=name):
                inputs = b.REVIEWED_TOOL_CONTRACTS[name][0]["inputSchema"]
                nested = inputs["properties"]["tokens"]["items"]["properties"]
                self.assertIn("description", nested)
                self.assertEqual(nested["description"]["type"], "string")
                mutated = copy.deepcopy(M2)
                props = mutated[name]["inputSchema"]["properties"]["tokens"]["items"]["properties"]
                props["description"]["type"] = "number"
                receipt = b.schema_receipt(Client(mutated), mutated)
                self.assertTrue(receipt["accepted_for_write"])
                self.assertNotIn(name, receipt["compatible_write_tools"])
                self.assertIn("create_artboard", receipt["compatible_write_tools"])

    def test_nested_rich_text_schema_change_blocks_only_rich_text(self):
        cat = copy.deepcopy(M2)
        fields = cat["set_text_content"]["inputSchema"]["properties"]["updates"]["items"]["properties"]
        fields["html"]["type"] = "number"
        r = b.schema_receipt(Client(cat), cat)
        self.assertIn("create_artboard", r["compatible_write_tools"])
        self.assertNotIn("set_text_content", r["compatible_write_tools"])
        with tempfile.TemporaryDirectory() as tmp:
            c = Client(cat)
            with self.assertRaisesRegex(b.Refusal, "TOOL_SCHEMA_CHANGED"):
                b.execute("edit", tool="set_text_content",
                          arguments={"fileId": FILE_ID, "updates": [{"nodeId": "text-1", "html": "ok"}]},
                          expected_snapshot="a"*64, operation_id="changed-richtext",
                          allow_write=True, client=c, lock_root=Path(tmp))
            self.assertEqual(c.calls, [])

    def test_legacy_text_payload_fails_before_dispatch_on_future_version(self):
        cat = copy.deepcopy(M2)
        cat["brand_new_vendor_tool"] = {
            "name": "brand_new_vendor_tool", "inputSchema": {
                "type": "object", "properties": {}}}
        with tempfile.TemporaryDirectory() as tmp:
            c = Client(cat, "9.4.3")
            with self.assertRaisesRegex(b.Refusal, "PAPER_RICH_TEXT_SCHEMA_REQUIRED"):
                b.execute("edit", tool="set_text_content",
                          arguments={"fileId": FILE_ID,
                                     "updates": [{"nodeId": "txt", "textContent": "old"}]},
                          expected_snapshot="a"*64, operation_id="legacy-rejected",
                          allow_write=True, client=c, lock_root=Path(tmp))
            self.assertEqual(c.calls, [])

    def test_critical_snapshot_contract_or_server_identity_blocks_all_writes(self):
        for change in ("snapshot_type", "identity"):
            with self.subTest(change=change):
                cat = copy.deepcopy(M2)
                c = Client(cat)
                if change == "snapshot_type":
                    c.value["get_basic_info"]["inputSchema"]["properties"]["fileId"]["type"] = "number"
                else:
                    c.server["name"] = "not-paper-desktop"
                r = b.schema_receipt(c, c.catalog())
                self.assertFalse(r["accepted_for_write"])
                with tempfile.TemporaryDirectory() as tmp:
                    with self.assertRaisesRegex(b.Refusal, "UPSTREAM_SCHEMA_UNREVIEWED"):
                        b.execute("edit", tool="create_artboard",
                                  arguments={"fileId": FILE_ID},
                                  expected_snapshot="a"*64, operation_id="critical-drift",
                                  allow_write=True, client=c, lock_root=Path(tmp))
                self.assertEqual(c.calls, [])

    def test_missing_edit_tool_isolated_and_missing_snapshot_tool_blocks(self):
        cat = copy.deepcopy(M2)
        cat.pop("write_html")
        r = b.schema_receipt(Client(cat), cat)
        self.assertTrue(r["accepted_for_write"])
        self.assertNotIn("write_html", r["compatible_write_tools"])
        self.assertIn("create_artboard", r["compatible_write_tools"])
        cat.pop("get_basic_info")
        self.assertFalse(b.schema_receipt(Client(cat), cat)["accepted_for_write"])

    def test_custom_pin_and_existing_snapshot_fence_do_not_regress(self):
        cat = copy.deepcopy(M2)
        cat["create_file"]["description"] += "new docs"
        r = b.schema_receipt(Client(cat), cat, catalog_pin="0"*64)
        self.assertFalse(r["accepted_for_write"])
        with tempfile.TemporaryDirectory() as tmp:
            c = Client(cat)
            with self.assertRaisesRegex(b.Refusal, "DOCUMENT_CHANGED"):
                b.execute("edit", tool="create_artboard",
                          arguments={"fileId": FILE_ID},
                          expected_snapshot="a"*64, operation_id="stale-snapshot",
                          allow_write=True, client=c, lock_root=Path(tmp))
            self.assertEqual([name for name, _ in c.calls].count("create_artboard"), 0)


if __name__ == "__main__":
    unittest.main()
