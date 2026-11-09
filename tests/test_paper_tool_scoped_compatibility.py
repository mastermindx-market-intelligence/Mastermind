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
# This is one observed descriptor, not a reconstructed full f200 catalog.
NATIVE_STYLE = json.loads(
    (FIXTURES / "f200eaf_update_styles_descriptor.json").read_text())["tool"]
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

    @staticmethod
    def _native_style_catalog():
        """Synthetic catalog: historical M2 plus the exact observed style tool."""
        cat = copy.deepcopy(M2)
        cat["update_styles"] = copy.deepcopy(NATIVE_STYLE)
        return cat

    def _assert_style_descriptor_held(self, cat):
        self.assertIsNone(
            b.compatible_tool_contract("update_styles", cat["update_styles"]))
        receipt = b.schema_receipt(Client(cat), cat)
        self.assertNotIn("update_styles", receipt["compatible_write_tools"])
        self.assertIn("write_html", receipt["compatible_write_tools"])
        with tempfile.TemporaryDirectory() as tmp:
            c = Client(cat)
            with self.assertRaisesRegex(b.Refusal, "TOOL_SCHEMA_CHANGED"):
                b.execute("edit", tool="update_styles",
                          arguments={"fileId": FILE_ID, "updates": [{
                              "nodeIds": ["node-1"], "styles": {"opacity": 1}}]},
                          expected_snapshot="a" * 64,
                          operation_id="unreviewed-style-descriptor",
                          allow_write=True, client=c, lock_root=Path(tmp))
            self.assertEqual(c.calls, [])

    def test_observed_style_primitive_union_dispatches_once(self):
        cat = self._native_style_catalog()
        receipt = b.schema_receipt(Client(cat), cat)
        self.assertIn("update_styles", receipt["compatible_write_tools"])
        self.assertFalse(receipt["full_catalog_known"])
        self.assertNotIn(b.digest(cat), b.REVIEWED_CATALOG_SHA256_ALTERNATES)
        args = {"fileId": FILE_ID, "updates": [{
            "nodeIds": ["node-1", "node-2"],
            "styles": {"boxShadow": "none", "zIndex": 110,
                       "backgroundColor": "var(--mx-dark-panel)", "opacity": 0}}]}
        with tempfile.TemporaryDirectory() as tmp:
            c = Client(cat)
            guard = b.snapshot(c, FILE_ID)["snapshot_sha256"]
            c.calls.clear()
            result = b.execute("edit", tool="update_styles", arguments=args,
                               expected_snapshot=guard,
                               operation_id="observed-style-union",
                               allow_write=True, client=c, lock_root=Path(tmp))
            self.assertEqual(result["state"], "APPLIED_RESPONSE_OBSERVED")
            self.assertEqual([call for call in c.calls
                              if call[0] == "update_styles"],
                             [("update_styles", args)])

    def test_observed_style_union_type_and_value_constraints_stay_held(self):
        variants = [
            {"type": ["string", "number", "null"]},
            {"type": ["string", "number", "boolean"]},
            {"type": ["string", "integer"]},
            {"type": ["string"]},
            {"type": ["number"]},
            {"type": ["number", "string"]},  # No general union normalization.
            {"type": ["string", "number"], "minimum": 0},
            {"type": ["string", "number"], "maxLength": 4},
            {"type": ["string", "number"], "default": 0},
        ]
        for values in variants:
            with self.subTest(values=values):
                cat = self._native_style_catalog()
                styles = cat["update_styles"]["inputSchema"]["properties"][
                    "updates"]["items"]["properties"]["styles"]
                styles["additionalProperties"] = values
                self._assert_style_descriptor_held(cat)

    def test_observed_style_nested_shape_and_dialect_stay_held(self):
        for change in ("node_type", "file_type", "missing_styles",
                       "relaxed_item", "relaxed_top", "nested_optional",
                       "property_names", "schema_dialect"):
            with self.subTest(change=change):
                cat = self._native_style_catalog()
                schema = cat["update_styles"]["inputSchema"]
                item = schema["properties"]["updates"]["items"]
                if change == "node_type":
                    item["properties"]["nodeIds"]["items"]["type"] = "number"
                elif change == "file_type":
                    schema["properties"]["fileId"]["type"] = "number"
                elif change == "missing_styles":
                    item["required"] = ["nodeIds"]
                elif change == "relaxed_item":
                    item["additionalProperties"] = True
                elif change == "relaxed_top":
                    schema["additionalProperties"] = True
                elif change == "nested_optional":
                    item["properties"]["futureFlag"] = {"type": "boolean"}
                elif change == "property_names":
                    item["properties"]["styles"]["propertyNames"]["minLength"] = 1
                else:
                    schema["$schema"] = "https://json-schema.org/draft-07/schema"
                self._assert_style_descriptor_held(cat)

    def test_observed_style_safety_annotation_types_stay_exact(self):
        for annotations in ({}, {"destructiveHint": False},
                            {"destructiveHint": 1},
                            {"destructiveHint": True, "readOnlyHint": False}):
            with self.subTest(annotations=annotations):
                cat = self._native_style_catalog()
                cat["update_styles"]["annotations"] = annotations
                self._assert_style_descriptor_held(cat)

    def test_observed_style_descriptor_drift_after_guard_refuses(self):
        class ChangedAfterGuard(Client):
            armed = False

            def call(self, name, arguments):
                response = super().call(name, arguments)
                if self.armed and name == "get_basic_info":
                    self.value["update_styles"]["inputSchema"]["properties"][
                        "updates"]["items"]["properties"]["styles"][
                            "additionalProperties"]["type"].append("boolean")
                return response

        c = ChangedAfterGuard(self._native_style_catalog())
        guard = b.snapshot(c, FILE_ID)["snapshot_sha256"]
        c.calls.clear()
        c.armed = True
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(b.Refusal, "TOOL_SCHEMA_CHANGED"):
                b.execute("edit", tool="update_styles",
                          arguments={"fileId": FILE_ID, "updates": [{
                              "nodeIds": ["node-1"], "styles": {"zIndex": 110}}]},
                          expected_snapshot=guard, operation_id="style-guard-drift",
                          allow_write=True, client=c, lock_root=Path(tmp))
        self.assertEqual([name for name, _ in c.calls], ["get_basic_info"])

    def test_requested_tool_drift_during_guard_refuses_before_dispatch(self):
        cases = [
            ("edit", "write_html", {"fileId": FILE_ID, "targetNodeId": "artboard-1",
                                     "mode": "insert-children", "html": "<div>QA</div>"}),
            ("edit", "create_file", {"sourceFileId": FILE_ID, "name": "QA fixture"}),
            ("read", "get_jsx", {"fileId": FILE_ID, "nodeId": "artboard-1"}),
        ]
        for action, tool, arguments in cases:
            with self.subTest(tool=tool):
                class ChangedAfterGuard(Client):
                    armed = False

                    def call(self, name, args):
                        response = super().call(name, args)
                        if self.armed and name == "get_basic_info":
                            key = "readOnlyHint" if action == "read" else "destructiveHint"
                            self.value[tool]["annotations"][key] = False
                        return response

                c = ChangedAfterGuard()
                guard = b.snapshot(c, FILE_ID)["snapshot_sha256"]
                c.calls.clear()
                c.armed = True
                with tempfile.TemporaryDirectory() as tmp:
                    with self.assertRaisesRegex(b.Refusal, "TOOL_SCHEMA_CHANGED"):
                        b.execute(action, tool=tool, arguments=arguments,
                                  expected_snapshot=guard, operation_id="guard-tool-drift",
                                  allow_write=True, client=c, lock_root=Path(tmp))
                self.assertEqual([name for name, _ in c.calls], ["get_basic_info"])

    def test_material_schema_drift_during_guard_refuses_before_dispatch(self):
        class ChangedAfterGuard(Client):
            armed = False

            def call(self, name, arguments):
                response = super().call(name, arguments)
                if self.armed and name == "get_basic_info":
                    self.value["write_html"]["inputSchema"]["properties"]["mode"]["enum"] = ["new-mode"]
                return response

        c = ChangedAfterGuard()
        guard = b.snapshot(c, FILE_ID)["snapshot_sha256"]
        c.calls.clear()
        c.armed = True
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(b.Refusal, "TOOL_SCHEMA_CHANGED"):
                b.execute("edit", tool="write_html", arguments={"fileId": FILE_ID,
                          "targetNodeId": "artboard-1", "mode": "insert-children",
                          "html": "<div>QA</div>"}, expected_snapshot=guard,
                          operation_id="guard-schema-drift", allow_write=True,
                          client=c, lock_root=Path(tmp))
        self.assertEqual([name for name, _ in c.calls], ["get_basic_info"])

    def test_reviewed_text_profile_switch_revalidates_payload_after_guard(self):
        for before_catalog, after_catalog, field, refusal in [
            (M2, CATALOGS[0], "html", "PAPER_LEGACY_TEXT_SCHEMA_REQUIRED"),
            (CATALOGS[0], M2, "textContent", "PAPER_RICH_TEXT_SCHEMA_REQUIRED"),
        ]:
            with self.subTest(field=field):
                class ChangedAfterGuard(Client):
                    armed = False

                    def call(self, name, arguments):
                        response = super().call(name, arguments)
                        if self.armed and name == "get_basic_info":
                            self.value["set_text_content"] = copy.deepcopy(after_catalog["set_text_content"])
                        return response

                c = ChangedAfterGuard(before_catalog)
                guard = b.snapshot(c, FILE_ID)["snapshot_sha256"]
                c.calls.clear()
                c.armed = True
                with tempfile.TemporaryDirectory() as tmp:
                    with self.assertRaisesRegex(b.Refusal, refusal):
                        b.execute("edit", tool="set_text_content", allow_write=True,
                                  arguments={"fileId": FILE_ID,
                                             "updates": [{"nodeId": "text-1", field: "QA"}]},
                                  expected_snapshot=guard, operation_id="guard-text-switch",
                                  client=c, lock_root=Path(tmp))
                self.assertEqual([name for name, _ in c.calls], ["get_basic_info"])

    def test_getter_or_identity_drift_during_guard_blocks_requested_call(self):
        for change in ("getter", "identity"):
            with self.subTest(change=change):
                class ChangedAfterGuard(Client):
                    armed = False

                    def call(self, name, arguments):
                        response = super().call(name, arguments)
                        if self.armed and name == "get_basic_info":
                            if change == "getter":
                                self.value[name]["annotations"]["readOnlyHint"] = False
                            else:
                                self.server["name"] = "different-server"
                        return response

                c = ChangedAfterGuard()
                guard = b.snapshot(c, FILE_ID)["snapshot_sha256"]
                c.calls.clear()
                c.armed = True
                with tempfile.TemporaryDirectory() as tmp:
                    with self.assertRaisesRegex(b.Refusal, "UPSTREAM_SCHEMA_UNREVIEWED"):
                        b.execute("edit", tool="write_html", arguments={"fileId": FILE_ID},
                                  expected_snapshot=guard, operation_id="guard-critical-drift",
                                  allow_write=True, client=c, lock_root=Path(tmp))
                self.assertEqual([name for name, _ in c.calls], ["get_basic_info"])

    def test_benign_guard_drift_keeps_file_creation_single_and_strips_source_id(self):
        class ChangedAfterGuard(Client):
            def call(self, name, arguments):
                response = super().call(name, arguments)
                if name == "get_basic_info":
                    self.value["create_file"]["description"] += " Vendor explanation."
                    self.value["archive_resources"]["description"] += " Unrelated change."
                return response

        c = ChangedAfterGuard()
        guard = b.snapshot(c, FILE_ID)["snapshot_sha256"]
        c.calls.clear()
        with tempfile.TemporaryDirectory() as tmp:
            result = b.execute("edit", tool="create_file",
                               arguments={"sourceFileId": FILE_ID, "name": "QA fixture"},
                               expected_snapshot=guard, operation_id="benign-guard-drift",
                               allow_write=True, client=c, lock_root=Path(tmp))
        self.assertEqual(result["state"], "RESPONSE_OBSERVED_REQUIRES_TARGET_VERIFICATION")
        self.assertEqual([args for name, args in c.calls if name == "create_file"],
                         [{"name": "QA fixture"}])

    def test_catalog_failure_after_guard_refuses_before_mutation(self):
        class CatalogFailsAfterGuard(Client):
            armed = False
            catalog_unavailable = False

            def catalog(self):
                if self.catalog_unavailable:
                    raise b.Refusal("UPSTREAM_UNAVAILABLE")
                return super().catalog()

            def call(self, name, arguments):
                response = super().call(name, arguments)
                if self.armed and name == "get_basic_info":
                    self.catalog_unavailable = True
                return response

        c = CatalogFailsAfterGuard()
        guard = b.snapshot(c, FILE_ID)["snapshot_sha256"]
        c.calls.clear()
        c.armed = True
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(b.Refusal, "UPSTREAM_UNAVAILABLE"):
                b.execute("edit", tool="write_html", arguments={"fileId": FILE_ID},
                          expected_snapshot=guard, operation_id="guard-catalog-failure",
                          allow_write=True, client=c, lock_root=Path(tmp))
        self.assertEqual([name for name, _ in c.calls], ["get_basic_info"])

    def test_post_edit_getter_drift_returns_effect_unknown_before_unsafe_verification(self):
        class ChangedAfterEdit(Client):
            def call(self, name, arguments):
                response = super().call(name, arguments)
                if name == "set_text_content":
                    # This models catalog drift after the real mutation, not
                    # a simulated response failure before dispatch.
                    self.value["get_basic_info"]["annotations"]["readOnlyHint"] = False
                    self.value["get_basic_info"]["annotations"]["destructiveHint"] = True
                return response

        c = ChangedAfterEdit()
        guard = b.snapshot(c, FILE_ID)["snapshot_sha256"]
        c.calls.clear()
        with tempfile.TemporaryDirectory() as tmp:
            result = b.execute(
                "edit", tool="set_text_content", allow_write=True,
                arguments={"fileId": FILE_ID,
                           "updates": [{"nodeId": "fixture-node", "html": "safe"}]},
                expected_snapshot=guard, operation_id="post-edit-drift",
                client=c, lock_root=Path(tmp))
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertFalse(result["retry_allowed"])
        self.assertFalse(result["production_acceptance"])
        self.assertEqual([name for name, _ in c.calls],
                         ["get_basic_info", "set_text_content"])

    def test_read_getter_drift_blocks_second_implicit_snapshot_dispatch(self):
        class ChangedAfterRead(Client):
            def call(self, name, arguments):
                result = super().call(name, arguments)
                if name == "get_basic_info":
                    self.value["get_basic_info"]["annotations"]["readOnlyHint"] = False
                    self.value["get_basic_info"]["annotations"]["destructiveHint"] = True
                return result

        c = ChangedAfterRead()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(b.Refusal, "UPSTREAM_SCHEMA_UNREVIEWED"):
                b.execute("read", tool="get_basic_info",
                          arguments={"fileId": FILE_ID},
                          client=c, lock_root=Path(tmp))
        self.assertEqual([name for name, _ in c.calls], ["get_basic_info"])
        self.assertIsNone(b.compatible_tool_contract(
            "get_basic_info", c.catalog()["get_basic_info"]))

    def test_read_getter_stable_still_returns_file_only_guard(self):
        c = Client()
        with tempfile.TemporaryDirectory() as tmp:
            result = b.execute("read", tool="get_basic_info",
                               arguments={"fileId": FILE_ID},
                               client=c, lock_root=Path(tmp))
        self.assertEqual(result["state"], "OBSERVED")
        self.assertEqual(result["document"]["identity"]["id"], FILE_ID)
        self.assertEqual(result["document"]["snapshot_sha256"],
                         b.snapshot(Client(), FILE_ID)["snapshot_sha256"])
        self.assertEqual([name for name, _ in c.calls],
                         ["get_basic_info", "get_basic_info"])

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

    def test_schema_dialect_change_is_not_treated_as_presentation_only(self):
        cat = copy.deepcopy(M2)
        original = cat["write_html"]["inputSchema"]["$schema"]
        cat["write_html"]["inputSchema"]["$schema"] = (
            "https://json-schema.org/draft/2019-09/schema"
            if "2019-09" not in original else
            "https://json-schema.org/draft/2020-12/schema")
        r = b.schema_receipt(Client(cat), cat)
        self.assertNotIn("write_html", r["compatible_write_tools"])
        self.assertIn("create_artboard", r["compatible_write_tools"])
        self.assertTrue(r["accepted_for_write"])

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


    def test_read_annotations_drift_refuses_before_vendor_dispatch(self):
        cat = copy.deepcopy(M2)
        cat["get_node_info"]["annotations"] = {
            "readOnlyHint": False, "destructiveHint": True}
        self.assertIsNone(b.compatible_tool_contract("get_node_info", cat["get_node_info"]))
        with tempfile.TemporaryDirectory() as tmp:
            c = Client(cat)
            listing = b.execute("catalog", client=c, lock_root=Path(tmp))
            unsafe = [x for x in listing["tools"] if x["name"] == "get_node_info"]
            self.assertEqual(unsafe[0]["bridge_access"], "read_held_schema")
            self.assertEqual(c.calls, [], "catalog must not dispatch a tool")
            args = {"fileId": FILE_ID, "nodeId": "text-1"}
            with self.assertRaisesRegex(b.Refusal, "TOOL_SCHEMA_CHANGED"):
                b.execute("read", tool="get_node_info", arguments=args,
                          client=c, lock_root=Path(tmp))
            self.assertEqual(c.calls, [], "unsafe read descriptor was dispatched")
            good = Client()
            observed = b.execute("read", tool="get_node_info", arguments=args,
                                 client=good, lock_root=Path(tmp))
            self.assertEqual(observed["state"], "OBSERVED")
            self.assertEqual(good.calls, [("get_node_info", args)])

    def test_read_optional_future_input_is_ignored_not_forwarded(self):
        cat = copy.deepcopy(M2)
        cat["get_node_info"]["inputSchema"]["properties"]["futureFlag"] = {
            "type": "boolean"}
        profile = b.compatible_tool_contract("get_node_info", cat["get_node_info"])
        self.assertIsNotNone(profile)
        self.assertEqual(profile["optional_new_inputs"], ["futureFlag"])
        self.assertIn("get_node_info",
                      b.schema_receipt(Client(cat), cat)["optional_vendor_inputs_ignored"])
        with tempfile.TemporaryDirectory() as tmp:
            c = Client(cat)
            with self.assertRaisesRegex(b.Refusal, "UNREVIEWED_TOOL_ARGUMENTS"):
                b.execute("read", tool="get_node_info",
                          arguments={"fileId": FILE_ID, "nodeId": "text-1",
                                     "futureFlag": True},
                          client=c, lock_root=Path(tmp))
            self.assertEqual(c.calls, [], "unreviewed optional input was forwarded")
            args = {"fileId": FILE_ID, "nodeId": "text-1"}
            self.assertEqual(b.execute("read", tool="get_node_info", arguments=args,
                                       client=c, lock_root=Path(tmp))["state"], "OBSERVED")
            self.assertEqual(c.calls, [("get_node_info", args)])

    def test_json_boolean_is_never_equivalent_to_number_in_safety_annotations(self):
        for name, hint in (("get_basic_info", "readOnlyHint"),
                           ("set_text_content", "destructiveHint")):
            with self.subTest(tool=name):
                cat = copy.deepcopy(M2)
                self.assertIs(cat[name]["annotations"][hint], True)
                cat[name]["annotations"][hint] = 1
                self.assertIsNone(b.compatible_tool_contract(name, cat[name]))
                r = b.schema_receipt(Client(cat), cat)
                if name == "get_basic_info":
                    self.assertFalse(r["snapshot_tool_compatible"])
                    self.assertFalse(r["accepted_for_write"])
                    with tempfile.TemporaryDirectory() as tmp:
                        c = Client(cat)
                        with self.assertRaisesRegex(b.Refusal, "UPSTREAM_SCHEMA_UNREVIEWED"):
                            b.execute("status", client=c, lock_root=Path(tmp))
                        with self.assertRaisesRegex(b.Refusal, "TOOL_SCHEMA_CHANGED"):
                            b.execute("read", tool="get_basic_info",
                                      arguments={"fileId": FILE_ID},
                                      client=c, lock_root=Path(tmp))
                        with self.assertRaisesRegex(b.Refusal, "UPSTREAM_SCHEMA_UNREVIEWED"):
                            b.execute("read", tool="get_node_info",
                                      arguments={"fileId": FILE_ID, "nodeId": "text-1"},
                                      expected_snapshot="a" * 64,
                                      client=c, lock_root=Path(tmp))
                        with self.assertRaisesRegex(b.Refusal, "UPSTREAM_SCHEMA_UNREVIEWED"):
                            b.execute("edit", tool="set_text_content",
                                      arguments={"fileId": FILE_ID,
                                                 "updates": [{"nodeId": "text-1",
                                                              "html": "<b>safe</b>"}]},
                                      expected_snapshot="a" * 64,
                                      operation_id="bad-implicit-guard",
                                      allow_write=True, client=c, lock_root=Path(tmp))
                        self.assertEqual(c.calls, [])
                else:
                    self.assertNotIn("set_text_content", r["compatible_write_tools"])
                    self.assertIn("create_artboard", r["compatible_write_tools"])
                    with tempfile.TemporaryDirectory() as tmp:
                        c = Client(cat)
                        with self.assertRaisesRegex(b.Refusal, "TOOL_SCHEMA_CHANGED"):
                            b.execute("edit", tool=name,
                                      arguments={"fileId": FILE_ID,
                                                 "updates": [{"nodeId": "text-1",
                                                              "html": "<b>safe</b>"}]},
                                      expected_snapshot="a" * 64,
                                      operation_id="bad-typed-write",
                                      allow_write=True, client=c, lock_root=Path(tmp))
                        self.assertEqual(c.calls, [])

    def test_prepare_blocks_unsafe_implicit_snapshot_without_paper_calls(self):
        import sys
        from unittest.mock import patch
        cat = copy.deepcopy(M2)
        cat["get_basic_info"]["annotations"]["readOnlyHint"] = 1
        path = ROOT / "integrations/paper_desktop/prepare.py"
        with patch.dict(sys.modules, {"bridge": b}):
            prep_spec = importlib.util.spec_from_file_location(
                "paper_selfheal_prepare_check", path)
            prep = importlib.util.module_from_spec(prep_spec)
            prep_spec.loader.exec_module(prep)
        with tempfile.TemporaryDirectory() as tmp:
            c = Client(cat)
            with self.assertRaisesRegex(b.Refusal, "UPSTREAM_SCHEMA_UNREVIEWED"):
                prep.prepare_document(FILE_ID, "a" * 64, "guarded-prepare",
                                      allow_prepare=True, client=c,
                                      lock_root=Path(tmp))
            self.assertEqual(c.calls, [])
            # Genuine reviewed descriptor remains usable; the new guard is
            # selective rather than a Paper-wide read/write outage.
            good = Client()
            guard = b.snapshot(good, FILE_ID)["snapshot_sha256"]
            good.calls.clear()
            prepared = prep.prepare_document(
                FILE_ID, guard, "qualified-prepare", allow_prepare=True,
                client=good, lock_root=Path(tmp))
            self.assertEqual(prepared["state"], "PAPER_READY")
            self.assertEqual(good.calls, [("get_basic_info", {"fileId": FILE_ID})])


if __name__ == "__main__":
    unittest.main()

