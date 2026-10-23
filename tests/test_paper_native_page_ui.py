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
        self.source_native_drift = False
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
                "pageId": page["id"],
                "nodeCount": (99 if fid == SRC and self.source_native_drift
                              and requested == "p-1-0" else 1),
                "artboardCount": 0,
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
        self.no_second_copy_change = False
        self.wrong_title = False
        self.right_clicks = 0
        self.drift_second_menu_to_keep = False
        self.drift_final_menu_to_keep = False
        self.tamper_final_menu_clipboard = False
        self.move_final_menu = False
        self.source_native_drift_after_delete = False

    def menu(self, window_id, private_dir, *, row_x, row_y):
        self.calls.append(("menu", window_id, row_x, row_y))
        assert private_dir.exists()
        elements = [
            {"id": "ocr_3", "label": "Copy link", "confidence": 0.5,
             "bounds": {"x": 620, "y": 210, "width": 60, "height": 12}},
            {"id": "ocr_4", "label": "Delete page", "confidence": 0.5,
             "bounds": {"x": 620, "y": 306, "width": 75, "height": 12}},
            {"id": "ocr_5", "label": "Add divider", "confidence": 0.5,
             "bounds": {"x": 620, "y": 245, "width": 75, "height": 12}},
        ]
        if self.missing_menu:
            elements = elements[:1]
        if self.move_final_menu and self.right_clicks >= 3:
            for item in elements:
                item["bounds"]["y"] += 40
        if self.tamper_final_menu_clipboard and self.right_clicks == 3:
            self.clipboard["value"] = (
                "https://app.paper.design/file/" + CLONE + "/p-1-0")
        return {
            "window_title": "Young harmony" if self.wrong_title else "Young harmony (copy)",
            "is_dialog": False,
            "coordinate_context": {"logical_bounds": [[508, 55], [2165, 1223]],
                                    "window": {"window_id": window_id}},
            "ui_elements": elements,
            "_row_visual_sha256": (
                "a" * 64 if self.link_page == "p-3-0" else "b" * 64),
        }

    def click(self, window_id, x, y, *, right=False):
        self.calls.append(("click", window_id, x, y, right))
        if right:
            self.right_clicks += 1
            if self.drift_second_menu_to_keep and self.right_clicks == 2:
                self.link_page = "p-1-0"
            if self.drift_final_menu_to_keep and self.right_clicks == 3:
                self.link_page = "p-1-0"
            return {"success": True}
        if y == 161:  # Copy link OCR: 210+6-55
            if not self.no_clipboard_change and not (
                    self.no_second_copy_change and self.right_clicks == 2):
                self.clipboard["value"] = (
                    "https://app.paper.design/file/" + self.link_file + "/" + self.link_page)
        elif y == 257:  # Delete page OCR: 306+6-55
            if self.fail_delete:
                raise ui_module.bridge.Refusal("CLICK_RESULT_LOST")
            self.client.files[CLONE]["pages"] = (
                [copy.deepcopy(PAGE2)] if self.link_page == "p-1-0"
                else [copy.deepcopy(PAGE1)])
            if self.source_native_drift_after_delete:
                self.client.source_native_drift = True
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
        313, 100, 165, client=client, ui=ui,
        clipboard=lambda: clipboard["value"],
        clipboard_set=lambda value: clipboard.__setitem__("value", value))
    return result, client, clipboard, ui


class NativePageUITests(unittest.TestCase):
    def test_copy_link_anchor_only_with_two_verified_first_party_menu_rows(self):
        from copy import deepcopy
        client, clipboard, ui = scenario()
        snapshot = ui.menu(313, __import__("pathlib").Path("/tmp"),
                           row_x=100, row_y=165)
        # Real M1 OCR omitted Copy link while recognizing Add divider and
        # Delete page. First row may be clicked non-destructively but its
        # clipboard result must still independently match exact IDs.
        snapshot["ui_elements"] = [
            {"id": "ocr_28", "label": "Add divider", "confidence": 0.5,
             "bounds": {"x": 620, "y": 286, "width": 64, "height": 9}},
            {"id": "ocr_31", "label": "Delete page", "confidence": 0.5,
             "bounds": {"x": 621, "y": 347, "width": 67, "height": 12}},
        ]
        x, y = ui_module._menu_target(
            snapshot, "Young harmony (copy)", "Copy link", 313, row_x=100, row_y=165)
        self.assertTrue(120 <= x <= 180)
        self.assertTrue(150 <= y <= 190)
        for change in ("missing", "duplicate", "faraway", "wrong_title",
                       "spoofed_canvas_cluster", "spoofed_below_row",
                       "bool_confidence", "bool_bounds"):
            broken = deepcopy(snapshot)
            if change == "missing":
                broken["ui_elements"] = broken["ui_elements"][:1]
            elif change == "duplicate":
                broken["ui_elements"].append(deepcopy(broken["ui_elements"][1]))
            elif change == "faraway":
                broken["ui_elements"][1]["bounds"]["y"] += 90
            elif change == "spoofed_canvas_cluster":
                for item in broken["ui_elements"]:
                    item["bounds"]["x"] += 400
            elif change == "spoofed_below_row":
                for item in broken["ui_elements"]:
                    item["bounds"]["y"] += 230
            elif change == "bool_confidence":
                broken["ui_elements"][0]["confidence"] = True
            elif change == "bool_bounds":
                broken["ui_elements"][0]["bounds"]["x"] = True
            else:
                broken["window_title"] = "MASTERMIND PAGES"
            with self.subTest(case=change), self.assertRaises(ui_module.bridge.Refusal):
                ui_module._menu_target(
                    broken, "Young harmony (copy)", "Copy link", 313,
                    row_x=100, row_y=165)

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
        self.assertTrue(result["source_page_list_unchanged"])
        self.assertTrue(result["retained_native_structure_reverified"])
        self.assertEqual(result["ui_copy_link_fresh_verification_count"], 2)
        self.assertTrue(result["ui_copy_link_evidence_preserved_before_delete"])
        self.assertTrue(result["ui_visible_page_prefixes_distinct"])
        self.assertNotIn("source_unchanged", result)
        self.assertFalse(result["original_deletion_authorized"])
        self.assertFalse(result["retry_allowed"])
        self.assertEqual([p["id"] for p in client.files[SRC]["pages"]], ["p-1-0", "p-3-0"])
        self.assertEqual([p["id"] for p in client.files[CLONE]["pages"]], ["p-1-0"])
        self.assertEqual(sum(1 for x in ui.calls if x[0] == "click" and x[3] == 257), 1)

    def test_first_copy_link_must_refresh_unique_clipboard_marker(self):
        client, clipboard, ui = scenario()
        ui.no_clipboard_change = True
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "STALE_CLIPBOARD")
        self.assertEqual(clipboard["value"],
                         "paper-native-copy-1:paper-scratch-ui-20261022")
        self.assertEqual(ui.right_clicks, 1)
        self.assertEqual(sum(1 for x in ui.calls
                             if x[0] == "click" and x[3] == 257), 0)

    def test_first_copy_link_missing_marker_refuses_without_delete(self):
        client, clipboard, ui = scenario()
        result = ui_module.prune_one(
            fixture_plan(), "p-3-0", "paper-scratch-ui-20261022",
            313, 100, 165, client=client, ui=ui,
            clipboard=lambda: clipboard["value"],
            clipboard_set=lambda value: None)
        self.assertEqual(result["state"], "UI_CLIPBOARD_MARKER_NOT_SET")
        self.assertEqual(ui.right_clicks, 1)
        self.assertEqual(sum(1 for x in ui.calls
                             if x[0] == "click" and x[3] == 257), 0)

    def test_second_copy_link_must_refresh_unique_clipboard_marker(self):
        client, clipboard, ui = scenario()
        ui.no_second_copy_change = True
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "STALE_CLIPBOARD")
        self.assertEqual(ui.right_clicks, 2)
        self.assertEqual(sum(1 for x in ui.calls if x[0] == "click"
                             and x[3] == 257), 0)
        self.assertEqual(len(client.files[CLONE]["pages"]), 2)

    def test_second_menu_page_drift_refuses_before_destructive_dispatch(self):
        client, clipboard, ui = scenario()
        ui.drift_second_menu_to_keep = True
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "UI_PAGE_ROW_CHANGED")
        self.assertEqual(ui.right_clicks, 2)
        self.assertEqual(sum(1 for x in ui.calls if x[0] == "click"
                             and x[3] == 257), 0)
        self.assertEqual([p["id"] for p in client.files[CLONE]["pages"]],
                         ["p-1-0", "p-3-0"])

    def test_identical_geometry_third_menu_wrong_page_refuses_before_delete(self):
        # Adversarial repro of the actual independent-review P1: the last
        # context menu belongs to a different retained page even though its
        # Copy link / Delete page geometry is unchanged.
        client, clipboard, ui = scenario()
        ui.drift_final_menu_to_keep = True
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "UI_PAGE_ROW_CHANGED")
        self.assertEqual(ui.right_clicks, 3)
        self.assertEqual(
            sum(1 for x in ui.calls if x[0] == "click" and x[3] == 257), 0)
        self.assertEqual([p["id"] for p in client.files[CLONE]["pages"]],
                         ["p-1-0", "p-3-0"])

    def test_third_menu_wrong_page_mutation_kills_visual_guard(self):
        from unittest.mock import patch
        client, clipboard, ui = scenario()
        ui.drift_final_menu_to_keep = True
        # Simulates accidentally removing the new visual identity fence.
        with patch.object(ui_module, "_assert_same_row_visual", return_value=None):
            result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertEqual(
            [p["id"] for p in client.files[CLONE]["pages"]], ["p-3-0"])
        self.assertEqual(
            sum(1 for x in ui.calls if x[0] == "click" and x[3] == 257), 1)

    def test_missing_or_changed_sidebar_visual_refuses(self):
        fake = {"_row_visual_sha256": "a" * 64}
        other = {"_row_visual_sha256": "b" * 64}
        ui_module._assert_same_row_visual(fake, dict(fake))
        for invalid in (other, {}, {"_row_visual_sha256": "not-a-sha"}):
            with self.subTest(invalid=invalid), self.assertRaises(
                    ui_module.bridge.Refusal):
                ui_module._assert_same_row_visual(fake, invalid)

    def test_lone_forged_near_row_delete_ocr_refuses(self):
        client, clip, ui = scenario()
        snapshot = ui.menu(313, __import__("pathlib").Path("/tmp"),
                           row_x=100, row_y=165)
        del snapshot["ui_elements"][2]  # No corroborating Add divider
        with self.assertRaisesRegex(ui_module.bridge.Refusal,
                                    "UI_MENU_STRUCTURE_UNVERIFIED"):
            ui_module._menu_target(
                snapshot, "Young harmony (copy)", "Delete page", 313,
                row_x=100, row_y=165)

    def test_persistent_near_row_misaligned_menu_stack_refuses(self):
        client, clip, ui = scenario()
        snapshot = ui.menu(313, __import__("pathlib").Path("/tmp"),
                           row_x=100, row_y=165)
        snapshot["ui_elements"][2]["bounds"]["x"] += 40
        with self.assertRaisesRegex(ui_module.bridge.Refusal,
                                    "UI_MENU_STRUCTURE_UNVERIFIED"):
            ui_module._menu_target(
                snapshot, "Young harmony (copy)", "Delete page", 313,
                row_x=100, row_y=165)

    def test_final_clipboard_wrong_page_refuses_without_delete(self):
        client, clipboard, ui = scenario()
        ui.tamper_final_menu_clipboard = True
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "UI_COPY_LINK_EVIDENCE_CHANGED")
        self.assertEqual(ui.right_clicks, 3)
        self.assertEqual(sum(1 for x in ui.calls
                             if x[0] == "click" and x[3] == 257), 0)
        self.assertEqual(len(client.files[CLONE]["pages"]), 2)

    def test_visible_prefix_refuses_same_clipped_label_before_any_ui(self):
        client, clipboard, ui = scenario()
        plan = fixture_plan()
        # Different complete names but Paper's narrow screenshot crop
        # would show the same initial six ASCII characters.
        for index, name in enumerate(("Ticker Apple", "Ticker Alphabet")):
            for fid in (SRC, CLONE):
                client.files[fid]["pages"][index]["name"] = name
            plan["original_pages"][index]["name"] = name
        plan["remove_pages"][0]["name"] = "Ticker Alphabet"
        plan["source_page_list_sha256"] = ui_module.bridge.digest(
            plan["original_pages"])
        plan["clone_page_list_sha256"] = plan["source_page_list_sha256"]
        result, *_ = perform(plan, client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "UI_VISIBLE_PAGE_LABEL_AMBIGUOUS")
        self.assertEqual(ui.calls, [])
        self.assertEqual(len(client.files[CLONE]["pages"]), 2)

    def test_visible_prefix_rejects_control_bidi_and_short_names(self):
        for names in [("Hello\n", "Page 2"), ("Abc", "Page 2"),
                      ("E2E \u2067abc", "Page 2")]:
            with self.subTest(names=names), self.assertRaises(
                    ui_module.bridge.Refusal):
                ui_module._require_distinct_visible_prefixes([
                    {"name": x} for x in names])

    def test_final_menu_relocation_refuses_before_destructive_dispatch(self):
        client, clipboard, ui = scenario()
        ui.move_final_menu = True
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "UI_MENU_RELOCATED")
        self.assertEqual(ui.right_clicks, 3)
        self.assertEqual(sum(1 for x in ui.calls if x[0] == "click"
                             and x[3] == 257), 0)
        self.assertEqual(len(client.files[CLONE]["pages"]), 2)

    def test_content_only_source_drift_after_dispatch_cannot_be_verified(self):
        client, clipboard, ui = scenario()
        ui.source_native_drift_after_delete = True
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertEqual(result["reason"],
                         "RETAINED_PAGE_NATIVE_STRUCTURE_MISMATCH")
        self.assertNotIn("source_page_list_unchanged", result)
        self.assertFalse(result["retry_allowed"])
        self.assertEqual(len(client.files[SRC]["pages"]), 2)
        self.assertEqual(len(client.files[CLONE]["pages"]), 1)
        self.assertEqual(sum(1 for x in ui.calls if x[0] == "click"
                             and x[3] == 257), 1)

    def test_wrong_file_link_refuses_before_delete(self):
        client, clipboard, ui = scenario()
        ui.link_file = SRC
        result, *_ = perform(client=client, clipboard=clipboard, ui=ui)
        self.assertEqual(result["state"], "UI_PAGE_ID_MISMATCH")
        self.assertEqual(len(client.files[CLONE]["pages"]), 2)
        self.assertEqual(sum(1 for x in ui.calls if x[0] == "click" and x[3] == 257), 0)

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
