"""Synthetic fail-closed tests for one-shot first-party Paper UI clone pruning."""
import copy
import json
import unittest

from integrations.paper_desktop import native_page_ui as ui_module
guard = ui_module.guard

SRC = "01M5HPWFPQ2Z5X79A9H8MJFKK0"
CLONE = "01M5HQ8VMMY87NVDENZAGJNYKM"
PAGE1 = {"type": "page", "id": "p-1-0", "name": "Page 1", "icon": None}
PAGE2 = {"type": "page", "id": "p-3-0", "name": "Page 2", "icon": None}


class FakeClient:
    def __init__(self):
        self.active = CLONE
        self.fail_read_after_delete = False
        self.clone_created_at = 1792672000000
        self.source_created_at = 1792671000000
        self.files = {
            SRC: {"fileName": "Young harmony", "pages": [copy.deepcopy(PAGE1), copy.deepcopy(PAGE2)]},
            CLONE: {"fileName": "Young harmony (copy)", "pages": [copy.deepcopy(PAGE1), copy.deepcopy(PAGE2)]},
        }
        self.calls = []

    def call(self, name, arguments):
        self.calls.append((name, copy.deepcopy(arguments)))
        if name == "list_resources":
            return {"content": [{"type": "text", "text": json.dumps({
                "resources": [
                    {"type": "file", "id": SRC, "name": self.files[SRC]["fileName"],
                     "createdAt": self.source_created_at},
                    {"type": "file", "id": CLONE, "name": self.files[CLONE]["fileName"],
                     "createdAt": self.clone_created_at},
                ]
            })}]}
        assert name == "get_basic_info", name
        if self.fail_read_after_delete and len(self.files[CLONE]["pages"]) == 1:
            raise OSError("simulated Paper connection interruption after dispatch")
        fid = arguments.get("fileId") or self.active
        d = self.files[fid]
        pages = copy.deepcopy(d["pages"])
        requested = arguments.get("pageId") or pages[0]["id"]
        page = next(z for z in pages if z["id"] == requested)
        return {"content": [
            {"type": "text", "text": json.dumps({
                "file": {"id": fid, "name": d["fileName"]},
                "contentHash": {"tokens": "c1"},
            })},
            {"type": "text", "text": json.dumps({
                "fileName": d["fileName"], "pageName": page["name"],
                "pageId": page["id"], "nodeCount": 1, "artboardCount": 0,
                "fontFamilies": [], "artboards": [], "pages": pages,
                "tokens": {"items": []},
            })},
        ]}


class FakePeekaboo:
    def __init__(self, client, clipboard, *, link_file=CLONE, link_page="p-3-0"):
        self.client, self.clipboard = client, clipboard
        self.link_file, self.link_page = link_file, link_page
        self.calls = []
        self.fail_delete = False
        self.missing_menu = False
        self.change_file_after_delete = False
        self.no_clipboard_change = False
        self.wrong_title = False

    def menu(self, window_id, private_dir):
        self.calls.append(("menu", window_id))
        assert private_dir.exists()
        elements = [
            {"id": "ocr_3", "label": "Copy link", "confidence": 0.5,
             "bounds": {"x": 620, "y": 210, "width": 60, "height": 12}},
            {"id": "ocr_4", "label": "Delete page", "confidence": 0.5,
             "bounds": {"x": 620, "y": 265, "width": 75, "height": 12}},
        ]
        if self.missing_menu:
            elements = elements[:1]
        return {
            "window_title": "Young harmony" if self.wrong_title else "Young harmony (copy)",
            "is_dialog": False,
            "coordinate_context": {"logical_bounds": [[508, 55], [2165, 1223]],
                                    "window": {"window_id": window_id}},
            "ui_elements": elements,
        }

    def click(self, window_id, x, y, *, right=False):
        self.calls.append(("click", window_id, x, y, right))
        if right:
            return {"success": True}
        if y == 161:  # Copy link OCR: 210+6-55
            if not self.no_clipboard_change:
                self.clipboard["value"] = (
                    "https://app.paper.design/file/" + self.link_file + "/" + self.link_page)
        elif y == 216:  # Delete page OCR: 265+6-55
            if self.fail_delete:
                raise ui_module.bridge.Refusal("CLICK_RESULT_LOST")
            self.client.files[CLONE]["pages"] = [copy.deepcopy(PAGE1)]
            if self.change_file_after_delete:
                self.client.files[SRC]["pages"][0]["name"] = "MUTATED"
        return {"success": True}


def fixture_plan():
    pages = [copy.deepcopy(PAGE1), copy.deepcopy(PAGE2)]
    plan = {
        "schema": guard.SCHEMA, "state": "CLONE_PRUNE_PLAN_READY",
        "source_file_id": SRC, "clone_file_id": CLONE,
        "source_file_name": "Young harmony",
        "clone_file_name": "Young harmony (copy)",
        "original_pages": pages, "keep_page_ids": ["p-1-0"],
        "remove_pages": [copy.deepcopy(PAGE2)],
        "source_page_list_sha256": ui_module.bridge.digest(pages),
        "clone_page_list_sha256": ui_module.bridge.digest(pages),
        "source_token_hash": "c1", "clone_token_hash_before": "c1",
        "retained_native_census": [{"page_id": "p-1-0",
            "native_metadata_sha256": ui_module.bridge.digest({
                "page_id": "p-1-0", "node_count": 1,
                "artboard_count": 0, "artboards": [], "font_families": []
            })}],
        "pre_prune_native_jsx": [],
        "pre_prune_native_jsx_sha256": ui_module.bridge.digest([]),
    }
    plan["retained_native_census_sha256"] = ui_module.bridge.digest(
        plan["retained_native_census"])
    return plan


def scenario():
    client = FakeClient()
    clipboard = {"value": "unrelated"}
    ui = FakePeekaboo(client, clipboard)
    return client, clipboard, ui


def perform(plan=None, *, client=None, clipboard=None, ui=None, page_id="p-3-0"):
    if client is None:
        client, clipboard, ui = scenario()
    result = ui_module.prune_one(
        plan or fixture_plan(), page_id, "paper-scratch-ui-20261022",
        313, 87, 194, client=client, ui=ui,
        clipboard=lambda: clipboard["value"])
    return result, client, clipboard, ui


class NativePageUITests(unittest.TestCase):
    def test_copy_link_anchor_only_with_two_verified_first_party_menu_rows(self):
        from copy import deepcopy
        client, clipboard, ui = scenario()
        snapshot = ui.menu(313, __import__("pathlib").Path("/tmp"))
        # Real M1 OCR omitted Copy link while recognizing Add divider and
        # Delete page. First row may be clicked non-destructively but its
        # clipboard result must still independently match exact IDs.
        snapshot["ui_elements"] = [
            {"id": "ocr_28", "label": "Add divider", "confidence": 0.5,
             "bounds": {"x": 620, "y": 286, "width": 64, "height": 9}},
            {"id": "ocr_31", "label": "Delete page", "confidence": 0.5,
             "bounds": {"x": 621, "y": 347, "width": 67, "height": 12}},
        ]
        x, y = ui_module._menu_target(snapshot, "Young harmony (copy)", "Copy link", 313)
        self.assertTrue(120 <= x <= 180)
        self.assertTrue(150 <= y <= 190)
        for change in ("missing", "duplicate", "faraway", "wrong_title"):
            broken = deepcopy(snapshot)
            if change == "missing":
                broken["ui_elements"] = broken["ui_elements"][:1]
            elif change == "duplicate":
                broken["ui_elements"].append(deepcopy(broken["ui_elements"][1]))
            elif change == "faraway":
                broken["ui_elements"][1]["bounds"]["y"] += 90
            else:
                broken["window_title"] = "MASTERMIND PAGES"
            with self.subTest(case=change), self.assertRaises(ui_module.bridge.Refusal):
                ui_module._menu_target(broken, "Young harmony (copy)", "Copy link", 313)

    def test_every_paper_rpc_is_checked_by_canonical_read_allowlist(self):
        client = FakeClient()
        self.assertIn("list_resources", ui_module.bridge.READ_TOOLS)
        from unittest.mock import patch
        with patch.object(ui_module.bridge, "READ_TOOLS", frozenset({"get_basic_info"})):
            with self.assertRaisesRegex(ui_module.bridge.Refusal, "TOOL_NOT_ALLOWED"):
                ui_module._reviewed_read(client, "list_resources", {"limit": 200})
        self.assertEqual(client.calls, [])


    def test_page_link_exact_match(self):
        url = "https://app.paper.design/file/" + CLONE + "/p-3-0"
        self.assertEqual(ui_module.native_page_identity(url), (CLONE, "p-3-0"))
        for value in [
            "http://app.paper.design/file/" + CLONE + "/p-3-0",
            "https://other.example/file/" + CLONE + "/p-3-0",
            "https://app.paper.design/file/" + CLONE + "/p-3-0?wrong=1",
            "https://app.paper.design/file/" + CLONE + "/p-3-0#frag",
            "https://app.paper.design@evil.example/file/" + CLONE + "/p-3-0",
            "https://app.paper.design/file/" + SRC + "/",
            "garbage",
        ]:
            with self.subTest(value=value), self.assertRaises(ui_module.bridge.Refusal):
                ui_module.native_page_identity(value)

    def test_exact_clone_page_link_before_single_delete(self):
        result, client, clipboard, ui = perform()
        self.assertEqual(result["state"], "CLONE_PAGE_UI_DELETE_VERIFIED")
        self.assertEqual(result["removed_page_id"], "p-3-0")
        self.assertTrue(result["source_unchanged"])
        self.assertFalse(result["original_deletion_authorized"])
        self.assertFalse(result["retry_allowed"])
        self.assertEqual([p["id"] for p in client.files[SRC]["pages"]], ["p-1-0", "p-3-0"])
        self.assertEqual([p["id"] for p in client.files[CLONE]["pages"]], ["p-1-0"])
        self.assertEqual(sum(1 for x in ui.calls if x[0] == "click" and x[3] == 216), 1)

    def test_wrong_file_link_refuses_before_delete(self):
        client, clipboard, ui = scenario()
        ui.link_file = SRC
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "UI_PAGE_ID_MISMATCH")
        self.assertEqual(len(client.files[CLONE]["pages"]), 2)
        self.assertEqual(sum(1 for x in ui.calls if x[0] == "click" and x[3] == 216), 0)

    def test_wrong_page_link_refuses_before_delete(self):
        client, clipboard, ui = scenario()
        ui.link_page = "p-1-0"
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "UI_PAGE_ID_MISMATCH")
        self.assertEqual(len(client.files[CLONE]["pages"]), 2)

    def test_stale_clipboard_refuses_before_delete(self):
        client, clipboard, ui = scenario()
        ui.no_clipboard_change = True
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "STALE_CLIPBOARD")
        self.assertEqual(len(client.files[CLONE]["pages"]), 2)

    def test_foreground_original_blocks_before_ui(self):
        client, clipboard, ui = scenario()
        client.active = SRC
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "CLONE_NOT_FOREGROUND" if isinstance(result, dict) else "")
        self.assertEqual(ui.calls, [])
        self.assertEqual(len(client.files[SRC]["pages"]), 2)

    def test_last_page_cannot_be_deleted(self):
        client, clipboard, ui = scenario()
        client.files[CLONE]["pages"] = [copy.deepcopy(PAGE2)]
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "CLONE_CHANGED")
        self.assertEqual(ui.calls, [])

    def test_delete_click_failure_is_effect_unknown(self):
        client, clipboard, ui = scenario()
        ui.fail_delete = True
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertEqual(len(client.files[CLONE]["pages"]), 2)
        self.assertFalse(result["retry_allowed"])

    def test_original_changes_after_dispatch_is_effect_unknown(self):
        client, clipboard, ui = scenario()
        ui.change_file_after_delete = True
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertNotEqual(client.files[SRC]["pages"][0]["name"], PAGE1["name"])

    def test_io_failure_after_delete_is_effect_unknown(self):
        client, clipboard, ui = scenario()
        client.fail_read_after_delete = True
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertFalse(result["retry_allowed"])
        self.assertEqual(len(client.files[CLONE]["pages"]), 1)

    def test_wrong_menu_window_title_refuses_without_delete(self):
        client, clipboard, ui = scenario()
        ui.wrong_title = True
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "UI_FILE_CONTEXT_CHANGED")
        self.assertEqual(len(client.files[CLONE]["pages"]), 2)

    def test_missing_ocr_menu_item_refuses_without_delete(self):
        client, clipboard, ui = scenario()
        ui.missing_menu = True
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "UI_MENU_ITEM_UNVERIFIED")
        self.assertEqual(len(client.files[CLONE]["pages"]), 2)

    def test_page_not_permitted_refuses_before_ui(self):
        client, clipboard, ui = scenario()
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui, page_id="p-1-0")
        self.assertEqual(result["state"], "PAGE_NOT_APPROVED_FOR_PRUNE")
        self.assertEqual(ui.calls, [])

    def test_duplicate_page_names_refuses(self):
        client, clipboard, ui = scenario()
        client.files[SRC]["pages"][1]["name"] = "Page 1"
        client.files[CLONE]["pages"][1]["name"] = "Page 1"
        plan = fixture_plan()
        plan["original_pages"][1]["name"] = "Page 1"
        plan["remove_pages"][0]["name"] = "Page 1"
        plan["source_page_list_sha256"] = ui_module.bridge.digest(plan["original_pages"])
        plan["clone_page_list_sha256"] = plan["source_page_list_sha256"]
        result, *_ = perform(plan, client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "UI_TARGET_AMBIGUOUS")
        self.assertEqual(ui.calls, [])

    def test_provenance_rejects_original_or_renamed_non_copy(self):
        client, clipboard, ui = scenario()
        client.clone_created_at = client.source_created_at - 1
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "NATIVE_CLONE_PROVENANCE_REQUIRED")
        self.assertEqual(ui.calls, [])
        client, clipboard, ui = scenario()
        client.files[CLONE]["fileName"] = "Renamed original"
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "NATIVE_CLONE_PROVENANCE_REQUIRED")
        self.assertEqual(ui.calls, [])

    def test_canonical_single_bridge_identity(self):
        from integrations.paper_desktop import bridge as canonical
        from integrations.paper_desktop import clone_prune_guard as canonical_guard
        self.assertIs(guard.bridge, canonical)
        self.assertIs(ui_module.guard, canonical_guard)
        self.assertEqual(canonical.__name__, "integrations.paper_desktop.bridge")


if __name__ == "__main__":
    unittest.main()
