"""Observed Paper 0.5.18 (f200) create_artboard / create_tokens / set_tokens descriptors.

The native catalog spells string|number as a JSON type array. These tests admit
exactly the observed descriptors and keep every nearby variant held.
"""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "paper_f200_artboard_tokens_bridge", ROOT / "integrations/paper_desktop/bridge.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
FIXTURES = ROOT / "tests/fixtures/paper_desktop"
M2 = json.loads((FIXTURES / "16e6b_full_catalog.json").read_text())
OBSERVED = json.loads((FIXTURES / "f200eaf_artboard_token_descriptors.json").read_text())["tools"]
FILE_ID = "01M2VWK62FA5S4VVF6G7SBPE5J"
NAMES = ("create_artboard", "create_tokens", "set_tokens")
ARGS = {
    "create_artboard": {"fileId": FILE_ID, "name": "QA", "styles": {"width": "480px", "height": "200px"}},
    "create_tokens": {"fileId": FILE_ID, "tokens": [{"name": "--qa", "type": "color", "value": "#101418"}]},
    "set_tokens": {"fileId": FILE_ID, "tokens": [{"name": "--qa", "value": 4}]},
}


class Client:
    def __init__(self, catalog):
        self.server = {"name": "paper-desktop", "version": "0.5.18"}
        self.value = copy.deepcopy(catalog)
        self.calls = []

    def initialize(self):
        return {}

    def catalog(self):
        return copy.deepcopy(self.value)

    def call(self, name, arguments):
        self.calls.append((name, copy.deepcopy(arguments)))
        if name == "get_basic_info":
            return {"structuredContent": {
                "fileId": FILE_ID, "fileName": "Scratch", "pageId": "p-1-0", "pageName": "Page 1",
                "nodeCount": 1, "artboards": [], "contentHash": {"tokens": "qa-only"}}}
        return {"content": [{"type": "text", "text": "success"}]}


def observed_catalog():
    cat = copy.deepcopy(M2)
    cat.update(copy.deepcopy(OBSERVED))
    return cat


class F200ArtboardTokenTests(unittest.TestCase):
    def test_fixture_is_exact_observation(self):
        self.assertEqual(set(OBSERVED), set(NAMES))
        for name in NAMES:
            self.assertNotEqual(OBSERVED[name]["inputSchema"], M2[name]["inputSchema"])
            self.assertIsNotNone(b.compatible_tool_contract(name, OBSERVED[name]))
            self.assertIsNotNone(b.compatible_tool_contract(name, M2[name]))

    def test_observed_descriptors_dispatch_once(self):
        cat = observed_catalog()
        receipt = b.schema_receipt(Client(cat), cat)
        for name in NAMES:
            self.assertIn(name, receipt["compatible_write_tools"])
        for name in NAMES:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                c = Client(cat)
                guard = b.snapshot(c, FILE_ID)["snapshot_sha256"]
                c.calls.clear()
                result = b.execute("edit", tool=name, arguments=ARGS[name], expected_snapshot=guard,
                                   operation_id=f"f200-{name}", allow_write=True, client=c,
                                   lock_root=Path(tmp))
                self.assertEqual(result["state"], "APPLIED_RESPONSE_OBSERVED")
                self.assertEqual([x for x in c.calls if x[0] == name], [(name, ARGS[name])])

    def test_token_delete_still_refused_on_observed_descriptor(self):
        cat = observed_catalog()
        with tempfile.TemporaryDirectory() as tmp:
            c = Client(cat)
            guard = b.snapshot(c, FILE_ID)["snapshot_sha256"]
            c.calls.clear()
            with self.assertRaisesRegex(b.Refusal, "TOKEN_DELETE_NOT_ALLOWED"):
                b.execute("edit", tool="set_tokens",
                          arguments={"fileId": FILE_ID, "tokens": [{"name": "--qa", "delete": True}]},
                          expected_snapshot=guard, operation_id="f200-delete", allow_write=True,
                          client=c, lock_root=Path(tmp))
            self.assertEqual([x for x in c.calls if x[0] == "set_tokens"], [])

    def _held(self, cat, name):
        self.assertIsNone(b.compatible_tool_contract(name, cat[name]))
        receipt = b.schema_receipt(Client(cat), cat)
        self.assertNotIn(name, receipt["compatible_write_tools"])
        with tempfile.TemporaryDirectory() as tmp:
            c = Client(cat)
            with self.assertRaisesRegex(b.Refusal, "TOOL_SCHEMA_CHANGED"):
                b.execute("edit", tool=name, arguments=ARGS[name], expected_snapshot="a" * 64,
                          operation_id=f"held-{name}", allow_write=True, client=c, lock_root=Path(tmp))
            self.assertEqual(c.calls, [])

    def _union_slot(self, schema, name):
        if name == "create_artboard":
            return schema["properties"]["styles"]["additionalProperties"]
        return schema["properties"]["tokens"]["items"]["properties"]["value"]

    def test_union_variants_stay_held(self):
        variants = [["string", "number", "null"], ["string", "number", "boolean"],
                    ["string", "integer"], ["string"], ["number", "string"]]
        for name in NAMES:
            for types in variants:
                with self.subTest(name=name, types=types):
                    cat = observed_catalog()
                    self._union_slot(cat[name]["inputSchema"], name)["type"] = types
                    self._held(cat, name)

    def test_shape_and_annotation_changes_stay_held(self):
        for name in NAMES:
            for change in ("relaxed_top", "schema_dialect", "annotation", "required"):
                with self.subTest(name=name, change=change):
                    cat = observed_catalog()
                    schema = cat[name]["inputSchema"]
                    if change == "relaxed_top":
                        schema["additionalProperties"] = True
                    elif change == "schema_dialect":
                        schema["$schema"] = "https://json-schema.org/draft-07/schema"
                    elif change == "annotation":
                        cat[name]["annotations"] = {"destructiveHint": False}
                    else:
                        schema["required"] = [r for r in schema["required"] if r != "fileId"]
                    self._held(cat, name)

    def test_extra_optional_root_property_is_never_forwarded(self):
        # The contract may admit a new optional root property, but no call that uses it is dispatched.
        for name in NAMES:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                cat = observed_catalog()
                cat[name]["inputSchema"]["properties"]["vendorExtra"] = {"type": "string"}
                c = Client(cat)
                guard = b.snapshot(c, FILE_ID)["snapshot_sha256"]
                c.calls.clear()
                with self.assertRaisesRegex(b.Refusal, "UNREVIEWED_TOOL_ARGUMENTS"):
                    b.execute("edit", tool=name, arguments={**ARGS[name], "vendorExtra": "x"},
                              expected_snapshot=guard, operation_id=f"extra-{name}", allow_write=True,
                              client=c, lock_root=Path(tmp))
                self.assertEqual([x for x in c.calls if x[0] == name], [])


if __name__ == "__main__":
    unittest.main()
