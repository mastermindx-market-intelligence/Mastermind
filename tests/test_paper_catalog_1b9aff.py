"""Exact observed catalog qualification; synthetic calls, never a live Paper write."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "paper_catalog_1b9aff_bridge", ROOT / "integrations/paper_desktop/bridge.py",
)
b = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = b
SPEC.loader.exec_module(b)

PREVIOUS_PIN = "48b2587455d839a57b4b78f5cfdb2e75df8d530ad8059a3ad6af303c0d37224f"
CURRENT_PIN = "1b9afff4c9bcf6f11f5ca2db301bf25ccdc442025344e2ec402459cedcd6a2db"
FIXTURES = ROOT / "tests/fixtures/paper_desktop"
PREVIOUS = b.load_json((FIXTURES / "48b258_full_catalog.json").read_bytes())
CURRENT = b.load_json((FIXTURES / "1b9aff_full_catalog.json").read_bytes())
BLOCKED = {
    "arrange_pages", "create_file", "delete_nodes", "export",
    "export_combined_pdf", "list_resources", "open_file", "rename_resource",
    "update_pages",
}
INFO = {
    "fileId": "file-qualified", "fileName": "Catalog proof", "pageName": "Page 1",
    "pageId": "p-1", "nodeCount": 1,
    "artboards": [{"id": "board-1", "name": "Anchor", "width": 390, "height": 844}],
    "pages": [
        {"id": "p-1", "type": "page", "name": "Page 1", "isActive": True},
        {"id": "divider-1", "type": "divider"},
        {"id": "p-2", "type": "page", "name": "Page 2", "isActive": False},
    ],
}
BINDING = {
    "schema": "mastermind.paper_execution_binding.v1",
    "host_ref": "host-" + "a" * 64, "service_ref": "b" * 64,
    "runtime_revision": "c" * 40, "bridge_sha256": "d" * 64,
}


class CatalogClient:
    def __init__(self, catalog=None):
        self.value = copy.deepcopy(CURRENT if catalog is None else catalog)
        self.server = {"name": "paper-desktop", "version": "0.5.14"}
        self.info = copy.deepcopy(INFO)
        self.calls = []
        self.initializations = 0
        self.failure = None
        self.after_wrong_file = False

    def initialize(self):
        self.initializations += 1

    def catalog(self):
        return copy.deepcopy(self.value)

    def call(self, name, arguments):
        self.calls.append((name, copy.deepcopy(arguments)))
        if name == "get_basic_info":
            return {"structuredContent": copy.deepcopy(self.info)}
        if name in b.EDIT_TOOLS:
            self.info["nodeCount"] += 1
            if self.after_wrong_file:
                self.info["fileId"] = "different-file"
            if self.failure == "timeout":
                raise TimeoutError("synthetic response loss")
            if self.failure == "tool_error":
                return {"isError": True, "content": [{"type": "text", "text": "synthetic partial error"}]}
        return {"content": [{"type": "text", "text": "synthetic observed response"}]}


class ExactCatalogQualificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, client, **overrides):
        args = {
            "tool": "create_artboard", "arguments": {"fileId": "file-qualified", "pageId": "p-1"},
            "expected_snapshot": b.digest(client.info), "operation_id": "paper-catalog-v13-proof",
            "allow_write": True, "client": client, "lock_root": self.root,
        }
        args.update(overrides)
        # Intentionally use the real default catalog/server pins. No test bypass.
        return b.execute("edit", **args)

    def assert_no_edit(self, client):
        self.assertFalse(any(name in b.EDIT_TOOLS for name, _ in client.calls))

    def test_complete_fixture_digests_and_exact_catalog_delta(self):
        self.assertEqual(b.digest(PREVIOUS), PREVIOUS_PIN)
        self.assertEqual(b.digest(CURRENT), CURRENT_PIN)
        self.assertEqual(b.SUPPORTED_CATALOG_SHA256, CURRENT_PIN)
        self.assertEqual(len(PREVIOUS), 36)
        self.assertEqual(len(CURRENT), 37)
        self.assertEqual(set(CURRENT) - set(PREVIOUS), {"arrange_pages", "update_pages"})
        self.assertEqual(set(PREVIOUS) - set(CURRENT), {"rename_pages"})
        changed = {name for name in set(PREVIOUS) & set(CURRENT) if PREVIOUS[name] != CURRENT[name]}
        self.assertEqual(changed, {"create_page", "get_basic_info", "get_jsx"})
        self.assertEqual(len(set(PREVIOUS) & set(CURRENT) - changed), 32)

        expected = copy.deepcopy(PREVIOUS)
        del expected["rename_pages"]
        for name in ["arrange_pages", "update_pages"]:
            expected[name] = CURRENT[name]
        expected["create_page"]["description"] = CURRENT["create_page"]["description"]
        expected["create_page"]["inputSchema"]["properties"]["icon"] = CURRENT["create_page"]["inputSchema"]["properties"]["icon"]
        expected["get_basic_info"]["description"] = CURRENT["get_basic_info"]["description"]
        for key in ["includeNodeIds", "includeRootPositioning"]:
            expected["get_jsx"]["inputSchema"]["properties"][key] = CURRENT["get_jsx"]["inputSchema"]["properties"][key]
        self.assertEqual(expected, CURRENT)

    def test_new_optional_fields_leave_exact_target_requirements_unchanged(self):
        for tool in ["create_page", "get_jsx"]:
            with self.subTest(tool=tool):
                self.assertEqual(CURRENT[tool]["inputSchema"]["required"], PREVIOUS[tool]["inputSchema"]["required"])
                self.assertFalse(CURRENT[tool]["inputSchema"]["additionalProperties"])
                self.assertIn("fileId", CURRENT[tool]["inputSchema"]["required"])
        icon = CURRENT["create_page"]["inputSchema"]["properties"]["icon"]
        self.assertEqual(icon["type"], "string")
        self.assertEqual(icon["enum"], ["arrow", "padlock", "check", "cross", "info", "question", "design", "vector", "images", "table", "presentation", "blueprint", "swatches", "bar-chart", "line-chart", "pie-chart", "paper"])
        for field in ["includeNodeIds", "includeRootPositioning"]:
            self.assertEqual(CURRENT["get_jsx"]["inputSchema"]["properties"][field]["type"], "boolean")
            self.assertNotIn(field, CURRENT["get_jsx"]["inputSchema"]["required"])

    def test_exact_catalog_accepts_guarded_write_with_production_defaults(self):
        client = CatalogClient()
        receipt = b.schema_receipt(client, client.catalog())
        self.assertTrue(receipt["accepted_for_write"])
        self.assertEqual(receipt["expected_catalog_sha256"], CURRENT_PIN)
        result = self.edit(client)
        self.assertEqual(result["state"], "APPLIED_RESPONSE_OBSERVED")
        self.assertFalse(result["production_acceptance"])
        self.assertFalse(result["retry_allowed"])
        self.assertEqual([name for name, _ in client.calls], ["get_basic_info", "create_artboard", "get_basic_info"])

    def test_catalog_projection_preserves_semantic_blocked_set(self):
        client = CatalogClient()
        result = b.execute("catalog", client=client, lock_root=self.root)
        self.assertEqual(set(result["blocked_tools"]), BLOCKED)
        self.assertEqual({tool["name"] for tool in result["tools"]}, b.READ_TOOLS | b.EDIT_TOOLS)
        self.assertEqual(len(result["tools"]), 28)
        for name in BLOCKED | {"rename_pages", "list_files", "launch_shell"}:
            self.assertNotIn(name, b.READ_TOOLS | b.EDIT_TOOLS)

    def test_page_mutators_and_unknown_tools_are_refused_before_initialization(self):
        for name in BLOCKED | {"rename_pages", "list_files", "launch_shell"}:
            with self.subTest(tool=name):
                client = CatalogClient()
                with self.assertRaisesRegex(b.Refusal, "TOOL_NOT_ALLOWED"):
                    self.edit(client, tool=name)
                self.assertEqual(client.initializations, 0)
                self.assertEqual(client.calls, [])

    def test_any_further_descriptor_schema_or_name_drift_refuses_before_dispatch(self):
        mutations = []
        for name in ["create_page", "get_basic_info", "get_jsx", "arrange_pages", "update_pages", "write_html", "get_font_family_info"]:
            changed = copy.deepcopy(CURRENT)
            changed[name]["description"] += " unreviewed change"
            mutations.append((name + ":description", changed))
        changed = copy.deepcopy(CURRENT)
        changed["create_page"]["inputSchema"]["properties"]["icon"]["enum"].append("unreviewed")
        mutations.append(("icon_enum", changed))
        changed = copy.deepcopy(CURRENT)
        changed["create_page"]["inputSchema"]["required"].append("icon")
        mutations.append(("icon_required", changed))
        changed = copy.deepcopy(CURRENT)
        changed["create_page"]["inputSchema"]["additionalProperties"] = True
        mutations.append(("additional_properties", changed))
        changed = copy.deepcopy(CURRENT)
        changed["get_jsx"]["inputSchema"]["properties"]["includeNodeIds"]["type"] = "string"
        mutations.append(("jsx_flag_type", changed))
        changed = copy.deepcopy(CURRENT)
        changed["get_font_family_info"]["inputSchema"]["required"].remove("fileId")
        mutations.append(("font_target_removed", changed))
        changed = copy.deepcopy(CURRENT)
        changed["arrange_pages"]["annotations"] = {"readOnlyHint": True}
        mutations.append(("page_mutator_annotation", changed))
        changed = copy.deepcopy(CURRENT)
        changed["unreviewed_page_editor"] = {"name": "unreviewed_page_editor", "inputSchema": {"type": "object"}}
        mutations.append(("tool_added", changed))
        changed = copy.deepcopy(CURRENT)
        del changed["update_pages"]
        mutations.append(("tool_removed", changed))
        for label, catalog in mutations:
            with self.subTest(change=label):
                client = CatalogClient(catalog)
                with self.assertRaisesRegex(b.Refusal, "UPSTREAM_SCHEMA_UNREVIEWED"):
                    self.edit(client)
                self.assertEqual(client.calls, [])

    def test_old_catalog_is_not_silently_added_to_new_default_pin(self):
        client = CatalogClient(PREVIOUS)
        with self.assertRaisesRegex(b.Refusal, "UPSTREAM_SCHEMA_UNREVIEWED"):
            self.edit(client)
        self.assertEqual(client.calls, [])

    def test_server_identity_remains_a_separate_gate(self):
        client = CatalogClient()
        client.server["name"] = "different-server"
        with self.assertRaisesRegex(b.Refusal, "UPSTREAM_SCHEMA_UNREVIEWED"):
            self.edit(client)
        self.assertEqual(client.calls, [])

    def test_write_opt_in_operation_snapshot_file_and_token_guards_remain(self):
        cases = [
            ({"allow_write": False}, "WRITE_DISABLED"),
            ({"operation_id": None}, "OPERATION_ID_REQUIRED"),
            ({"expected_snapshot": None}, "SNAPSHOT_REQUIRED"),
            ({"expected_snapshot": "0" * 64}, "DOCUMENT_CHANGED"),
            ({"arguments": {}}, "FILE_ID_REQUIRED"),
            ({"arguments": {"fileId": "different-file"}}, "FILE_ID_MISMATCH"),
            ({"tool": "set_tokens", "arguments": {"fileId": "file-qualified", "tokens": [{"name": "--test", "delete": True}]}}, "TOKEN_DELETE_NOT_ALLOWED"),
        ]
        for overrides, code in cases:
            with self.subTest(code=code):
                client = CatalogClient()
                with self.assertRaisesRegex(b.Refusal, code):
                    self.edit(client, **overrides)
                self.assert_no_edit(client)

    def test_execution_binding_is_still_part_of_the_guard(self):
        client = CatalogClient()
        expected = b.digest({"document": client.info, "execution_binding": BINDING})
        other = dict(BINDING, bridge_sha256="e" * 64)
        with self.assertRaisesRegex(b.Refusal, "DOCUMENT_CHANGED"):
            self.edit(client, expected_snapshot=expected, execution_binding=other)
        self.assert_no_edit(client)
        result = self.edit(client, expected_snapshot=expected, execution_binding=BINDING)
        self.assertEqual(result["state"], "APPLIED_RESPONSE_OBSERVED")

    def test_divider_records_are_preserved_and_bound_without_becoming_identity(self):
        client = CatalogClient()
        snapshot = b.snapshot(client, "file-qualified")
        self.assertEqual(snapshot["identity"], {"kind": "file-id", "id": "file-qualified"})
        self.assertEqual(snapshot["basic_info"]["pages"], INFO["pages"])
        self.assertEqual(snapshot["basic_info"]["pageId"], "p-1")
        client.info["pages"].reverse()
        with self.assertRaisesRegex(b.Refusal, "DOCUMENT_CHANGED"):
            self.edit(client, expected_snapshot=snapshot["snapshot_sha256"])
        self.assert_no_edit(client)

    def test_new_jsx_options_remain_read_only_and_are_forwarded_explicitly(self):
        client = CatalogClient()
        args = {"fileId": "file-qualified", "nodeId": "board-1", "format": "inline-styles", "includeNodeIds": False, "includeRootPositioning": False}
        result = b.execute("read", tool="get_jsx", arguments=args, client=client, lock_root=self.root)
        self.assertEqual(result["state"], "OBSERVED")
        self.assertEqual(client.calls, [("get_jsx", args)])
        self.assert_no_edit(client)

    def test_edit_errors_remain_unknown_with_one_dispatch_and_no_retry(self):
        for failure in ["timeout", "tool_error", "after_wrong_file"]:
            with self.subTest(failure=failure):
                client = CatalogClient()
                client.failure = failure
                client.after_wrong_file = failure == "after_wrong_file"
                result = self.edit(client)
                self.assertEqual(result["state"], "EFFECT_UNKNOWN")
                self.assertEqual(result["operation_id"], "paper-catalog-v13-proof")
                self.assertFalse(result["retry_allowed"])
                self.assertEqual(sum(name == "create_artboard" for name, _ in client.calls), 1)


if __name__ == "__main__":
    unittest.main()
