"""Fail-closed clone/prune evidence checks: never click or delete Paper pages."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "integrations" / "paper_desktop"
spec = importlib.util.spec_from_file_location("clone_prune_guard_test", PAPER / "clone_prune_guard.py")
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

SRC = "01M5HPWFPQ2Z5X79A9H8MJFKK0"
CLONE = "01M5HQ8VMMY87NVDENZAGJNYKM"
PAGES = [
    {"type": "page", "id": "p-1-0", "name": "Page 1", "icon": None},
    {"type": "page", "id": "p-3-0", "name": "Page 2", "icon": "design"},
]


class Copy:
    def __init__(self):
        self.infos = {
            SRC: dict(fileId=SRC, fileName="Young harmony", pages=copy.deepcopy(PAGES),
                      contentHash={"tokens": "c1"}, nodeCount=1),
            CLONE: dict(fileId=CLONE, fileName="Young harmony (copy)",
                        pages=copy.deepcopy(PAGES), contentHash={"tokens": "c1"}, nodeCount=1),
        }
        self.calls = []
        self.page_calls = []
        source_pages = {
            "p-1-0": dict(fileId=SRC, pageId="p-1-0", pageName="Page 1",
                          nodeCount=5, artboardCount=1, fontFamilies=["Inter"],
                          artboards=[dict(id="1-1", name="Migration fidelity specimen",
                                          childCount=3)]),
            "p-3-0": dict(fileId=SRC, pageId="p-3-0", pageName="Page 2",
                          nodeCount=1, artboardCount=0, fontFamilies=[], artboards=[]),
        }
        self.page_infos = {SRC: source_pages, CLONE: copy.deepcopy(source_pages)}
        for page in self.page_infos[CLONE].values():
            page["fileId"] = CLONE

    def read(self, file_id):
        self.calls.append(file_id)
        return copy.deepcopy(self.infos[file_id])

    def read_page(self, file_id, page_id):
        self.page_calls.append((file_id, page_id))
        return copy.deepcopy(self.page_infos[file_id][page_id])

    def plan(self, keep=("p-1-0",)):
        return g.make_plan(SRC, CLONE, list(keep), "scratch-copy-prune-20261022",
                           reader=self.read, page_reader=self.read_page)

    def delete_clone_page_2(self):
        self.infos[CLONE]["pages"] = [copy.deepcopy(PAGES[0])]


class ClonePruneGuardTests(unittest.TestCase):
    def test_bridge_import_reuses_canonical_module_and_does_not_shadow_package(self):
        from integrations.paper_desktop import bridge as canonical_bridge
        self.assertIs(g.bridge, canonical_bridge)
        self.assertEqual(g.bridge.__name__, "integrations.paper_desktop.bridge")
        self.assertIs(sys.modules["integrations.paper_desktop.bridge"], canonical_bridge)
        self.assertNotIn(str(PAPER), sys.path)
        ambient = sys.modules.get("bridge")
        if ambient is not None:
            self.assertNotEqual(Path(getattr(ambient, "__file__", "/")).resolve(),
                                (PAPER / "bridge.py").resolve())

    def test_canonical_bridge_import_passes_protected_identity_scanner(self):
        from tests.test_ceo_submit_armed_composition import (
            _d8_frozen_source_diff, _scan_added_identity_diff,
        )
        path = "integrations/paper_desktop/clone_prune_guard.py"
        source = "from integrations.paper_desktop import bridge\\n".replace("\\n", "\n")
        diff = _d8_frozen_source_diff(path, source)
        self.assertEqual(_scan_added_identity_diff(
            diff, source_postimages={path: source},
        ), [])

    def test_native_page_reads_requested_tool_result_not_active_snapshot(self):
        # A real v14 Paper response carries p-L-0 (Commodities) in its
        # content, but the bridge's document snapshot describes the active
        # p-A-0. Selecting that snapshot can falsely certify a lossy clone.
        from unittest.mock import patch
        import json

        page = {"id": "p-L-0", "name": "Commodities", "type": "page"}
        def observed(actual_page):
            return {
                "state": "OBSERVED",
                "document": {"basic_info": {
                    "fileId": SRC, "pageId": "p-A-0",
                    "pageName": "International", "nodeCount": 1102,
                }},
                "result": {"content": [
                    {"type": "text", "text": json.dumps({
                        "file": {"id": SRC, "name": "Source"},
                        "contentHash": {"tokens": "abc"},
                    })},
                    {"type": "text", "text": "Warning: large file"},
                    {"type": "text", "text": json.dumps({
                        "fileName": "Source", "pageName": "Commodities",
                        "pageId": actual_page, "nodeCount": 6078,
                        "artboardCount": 1,
                        "artboards": [{"id": "L-A", "name": "Futures",
                                       "childCount": 20}],
                        "fontFamilies": ["Inter"], "pages": [page],
                    })},
                ]},
            }

        with patch.object(g.bridge, "execute", return_value=observed("p-L-0")) as execute:
            native = g._read_native_page(SRC, page)
            self.assertEqual(native["page_id"], "p-L-0")
            self.assertEqual(native["node_count"], 6078)
            self.assertEqual(native["artboard_count"], 1)
            execute.assert_called_once_with(
                "read", tool="get_basic_info",
                arguments={"fileId": SRC, "pageId": "p-L-0"},
            )

        with patch.object(g.bridge, "execute", return_value=observed("p-A-0")):
            with self.assertRaisesRegex(g.bridge.Refusal, "NATIVE_PAGE_IDENTITY_MISMATCH"):
                g._read_native_page(SRC, page)

    def test_exact_two_file_scratch_clone_prune_readback(self):
        fixture = Copy()
        plan = fixture.plan()
        self.assertEqual(plan["state"], "CLONE_PRUNE_PLAN_READY")
        self.assertEqual(plan["keep_page_ids"], ["p-1-0"])
        self.assertEqual(plan["remove_pages"][0]["id"], "p-3-0")
        self.assertEqual(fixture.calls, [SRC, CLONE])
        fixture.delete_clone_page_2()
        verified = g.verify_plan(plan, reader=fixture.read, page_reader=fixture.read_page)
        self.assertEqual(verified["state"], "CLONE_PRUNE_METADATA_VERIFIED")
        self.assertEqual(verified["clone_removed_page_ids"], ["p-3-0"])
        self.assertEqual(verified["source_page_list_unchanged_ids"], ["p-1-0", "p-3-0"])
        self.assertFalse(verified["original_deletion_authorized"])
        self.assertFalse(verified["production_migration_accepted"])
        self.assertFalse(verified["image_component_comment_fidelity_verified"])
        self.assertEqual(fixture.calls, [SRC, CLONE, SRC, CLONE])

    def test_source_and_clone_identity_guards(self):
        fixture = Copy()
        with self.assertRaisesRegex(g.bridge.Refusal, "SOURCE_EQUALS_CLONE"):
            g.make_plan(SRC, SRC, ["p-1-0"], "op", reader=fixture.read, page_reader=fixture.read_page)
        self.assertEqual(fixture.calls, [])
        for file_id in ("", "other", "../../fake", SRC.lower()):
            with self.subTest(file_id=file_id), self.assertRaisesRegex(g.bridge.Refusal, "FILE_ID_REQUIRED"):
                g.make_plan(file_id, CLONE, ["p-1-0"], "op", reader=fixture.read, page_reader=fixture.read_page)
        fixture.infos[CLONE]["fileId"] = SRC
        with self.assertRaisesRegex(g.bridge.Refusal, "FILE_ID_MISMATCH"):
            fixture.plan()

    def test_preflight_must_be_intact_clone(self):
        f = Copy()
        f.delete_clone_page_2()
        with self.assertRaisesRegex(g.bridge.Refusal, "CLONE_PAGE_LIST_MISMATCH"):
            f.plan()
        f = Copy()
        f.infos[CLONE]["pages"][0]["name"] = "Different"
        with self.assertRaisesRegex(g.bridge.Refusal, "CLONE_PAGE_LIST_MISMATCH"):
            f.plan()

    def test_reject_unsafe_keep_or_unneeded_prune(self):
        f = Copy()
        for ids, code in [
            ([], "KEEP_PAGE_IDS_REQUIRED"),
            (["p-1-0", "p-1-0"], "DUPLICATE_KEEP_PAGE_IDS"),
            (["p-missing"], "UNKNOWN_KEEP_PAGE"),
            (["p-1-0", "p-3-0"], "NO_PAGES_TO_PRUNE"),
        ]:
            with self.subTest(ids=ids), self.assertRaisesRegex(g.bridge.Refusal, code):
                f.plan(ids)

    def test_duplicate_page_names_make_ui_target_ambiguous(self):
        f = Copy()
        for info in f.infos.values():
            info["pages"][1]["name"] = "Page 1"
        with self.assertRaisesRegex(g.bridge.Refusal, "UI_TARGET_AMBIGUOUS"):
            f.plan()

    def test_dividers_are_explicitly_unsupported(self):
        f = Copy()
        for info in f.infos.values():
            info["pages"].append({"type": "divider", "id": "d-1"})
        with self.assertRaisesRegex(g.bridge.Refusal, "PAGE_LIST_UNSUPPORTED"):
            f.plan()

    def test_token_mismatch_rejected_without_ui(self):
        f = Copy()
        f.infos[CLONE]["contentHash"]["tokens"] = "changed"
        with self.assertRaisesRegex(g.bridge.Refusal, "CLONE_TOKENS_MISMATCH"):
            f.plan()

    def test_target_absence_unverified_no_false_positive(self):
        f = Copy()
        plan = f.plan()
        with self.assertRaisesRegex(g.bridge.Refusal, "CLONE_PRUNE_UNVERIFIED"):
            g.verify_plan(plan, reader=f.read, page_reader=f.read_page)
        self.assertEqual(len(f.infos[CLONE]["pages"]), 2)

    def test_extra_clone_page_blocks_verification(self):
        f = Copy()
        plan = f.plan()
        f.infos[CLONE]["pages"] = [copy.deepcopy(PAGES[0]), {
            "type": "page", "id": "p-extra", "name": "Unplanned", "icon": None,
        }]
        with self.assertRaisesRegex(g.bridge.Refusal, "CLONE_PRUNE_UNVERIFIED"):
            g.verify_plan(plan, reader=f.read, page_reader=f.read_page)

    def test_source_changed_blocks_verification(self):
        f = Copy()
        plan = f.plan()
        f.delete_clone_page_2()
        f.infos[SRC]["pages"][1]["name"] = "Changed"
        with self.assertRaisesRegex(g.bridge.Refusal, "SOURCE_CHANGED"):
            g.verify_plan(plan, reader=f.read, page_reader=f.read_page)

    def test_source_token_drift_blocks_verification(self):
        f = Copy()
        plan = f.plan()
        f.delete_clone_page_2()
        f.infos[SRC]["contentHash"]["tokens"] = "drift"
        with self.assertRaisesRegex(g.bridge.Refusal, "SOURCE_TOKENS_CHANGED"):
            g.verify_plan(plan, reader=f.read, page_reader=f.read_page)

    def test_clone_token_drift_blocks_verification(self):
        f = Copy()
        plan = f.plan()
        f.delete_clone_page_2()
        f.infos[CLONE]["contentHash"]["tokens"] = "drift"
        with self.assertRaisesRegex(g.bridge.Refusal, "CLONE_TOKENS_CHANGED"):
            g.verify_plan(plan, reader=f.read, page_reader=f.read_page)

    def test_tampered_plan_blocks_verification(self):
        for mutate, expected in [
            (lambda p: p.update({"source_page_list_sha256": "0" * 64}), "PLAN_PAGE_HASH_MISMATCH"),
            (lambda p: p.update({"keep_page_ids": ["p-3-0"]}), "PLAN_PAGE_TARGET_MISMATCH"),
            (lambda p: p.update({"remove_pages": []}), "PLAN_PAGE_TARGET_MISMATCH"),
            (lambda p: p.update({"clone_file_id": SRC}), "SOURCE_EQUALS_CLONE"),
            (lambda p: p.update({"state": "claimed_done"}), "INVALID_PRUNE_PLAN"),
        ]:
            with self.subTest(mutate=mutate):
                f = Copy()
                plan = f.plan()
                mutate(plan)
                f.delete_clone_page_2()
                with self.assertRaisesRegex(g.bridge.Refusal, expected):
                    g.verify_plan(plan, reader=f.read, page_reader=f.read_page)

    def test_selected_native_jsx_exact_parity_passes(self):
        f = Copy()
        plan = f.plan()
        f.delete_clone_page_2()
        jsx_reads = []
        def jsx(file_id, node_id):
            jsx_reads.append((file_id, node_id))
            return '(\n  <div id="1-1" style={{ color: "#ffffff" }}>content</div>\n)'
        result = g.verify_plan(plan, reader=f.read, page_reader=f.read_page,
                               evidence_node_ids=["1-1"], jsx_reader=jsx)
        self.assertEqual(result["exact_jsx_node_ids_verified"], ["1-1"])
        self.assertFalse(result["full_page_visual_fidelity_verified"])
        self.assertEqual(jsx_reads, [(SRC, "1-1"), (CLONE, "1-1")])

    def test_selected_jsx_mismatch_fails_closed(self):
        f = Copy()
        plan = f.plan()
        f.delete_clone_page_2()
        with self.assertRaisesRegex(g.bridge.Refusal, "CLONE_JSX_MISMATCH"):
            g.verify_plan(plan, reader=f.read, page_reader=f.read_page, evidence_node_ids=["1-1"],
                          jsx_reader=lambda file_id, node_id: (
                              "(<div>same</div>)" if file_id == SRC else "(<div>wrong</div>)"))

    def test_invalid_jsx_targets_and_non_jsx_reads_refused(self):
        f = Copy()
        plan = f.plan()
        f.delete_clone_page_2()
        for node_ids in ([""], ["1-1", "1-1"], ["x" * 121], list(map(str, range(25)))):
            with self.subTest(node_ids=node_ids), self.assertRaisesRegex(
                    g.bridge.Refusal, "INVALID_JSX_EVIDENCE_TARGETS"):
                g.verify_plan(plan, reader=f.read, page_reader=f.read_page, evidence_node_ids=node_ids)
        with self.assertRaisesRegex(g.bridge.Refusal, "JSX_SCHEMA_UNVERIFIED"):
            g.verify_plan(plan, reader=f.read, page_reader=f.read_page, evidence_node_ids=["1-1"],
                          jsx_reader=lambda *_: "unexpected tool error")

    def test_nested_node_count_mismatch_refuses_retained_page_plan(self):
        f = Copy()
        f.page_infos[CLONE]["p-1-0"]["nodeCount"] += 8
        with self.assertRaisesRegex(g.bridge.Refusal, "RETAINED_PAGE_NATIVE_STRUCTURE_MISMATCH"):
            f.plan()
        self.assertEqual(f.infos[SRC]["pages"], PAGES)
        self.assertEqual(f.infos[CLONE]["pages"], PAGES)

    def test_post_plan_native_source_and_clone_drift_refused(self):
        for file_id, expected in ((SRC, "SOURCE_NATIVE_PAGE_DRIFT"),
                                  (CLONE, "CLONE_NATIVE_PAGE_DRIFT")):
            f = Copy()
            plan = f.plan()
            f.delete_clone_page_2()
            f.page_infos[file_id]["p-1-0"]["nodeCount"] += 8
            with self.subTest(file_id=file_id), self.assertRaisesRegex(
                    g.bridge.Refusal, expected):
                g.verify_plan(plan, reader=f.read, page_reader=f.read_page)

    def test_incomplete_retained_artboard_census_is_never_accepted(self):
        f = Copy()
        f.page_infos[CLONE]["p-1-0"]["artboardCount"] = 2
        with self.assertRaisesRegex(g.bridge.Refusal, "NATIVE_PAGE_CENSUS_INCOMPLETE"):
            f.plan()
        f = Copy()
        plan = f.plan()
        f.delete_clone_page_2()
        plan["retained_native_census"][0]["native_metadata_sha256"] = "0" * 64
        with self.assertRaisesRegex(g.bridge.Refusal, "NATIVE_PAGE_CENSUS_PLAN_INVALID"):
            g.verify_plan(plan, reader=f.read, page_reader=f.read_page)

    def test_pre_prune_artboard_jsx_bound_and_reverified(self):
        f = Copy()
        def native(file_id, node_id):
            self.assertEqual(node_id, "1-1")
            return '(\\n  <div id="1-1">editable native specimen</div>\\n)'
        plan = g.make_plan(SRC, CLONE, ["p-1-0"], "pre-prune-native-1",
                           reader=f.read, page_reader=f.read_page,
                           evidence_node_ids=["1-1"], jsx_reader=native)
        self.assertEqual([x["node_id"] for x in plan["pre_prune_native_jsx"]], ["1-1"])
        f.delete_clone_page_2()
        result = g.verify_plan(plan, reader=f.read, page_reader=f.read_page, jsx_reader=native)
        self.assertEqual(result["pre_prune_native_jsx_verified_ids"], ["1-1"])
        self.assertEqual(result["exact_jsx_node_ids_verified"], ["1-1"])
        self.assertFalse(result["production_migration_accepted"])

    def test_pre_prune_jsx_mismatch_rejected_before_deletion(self):
        f = Copy()
        with self.assertRaisesRegex(g.bridge.Refusal, "CLONE_JSX_MISMATCH"):
            g.make_plan(SRC, CLONE, ["p-1-0"], "pre-prune-native-2",
                        reader=f.read, page_reader=f.read_page,
                        evidence_node_ids=["1-1"], jsx_reader=lambda file_id, node_id: (
                            "(<div>oklab</div>)" if file_id == SRC else "(<div>#5B9BF014</div>)"))
        self.assertEqual(f.infos[CLONE]["pages"], PAGES)

    def test_pre_prune_target_must_be_retained_artboard(self):
        f = Copy()
        for target in ("1-NOT-RETAINED", "p-3-0"):
            with self.subTest(target=target), self.assertRaisesRegex(
                    g.bridge.Refusal, "JSX_TARGET_NOT_RETAINED_ARTBOARD"):
                g.make_plan(SRC, CLONE, ["p-1-0"], "pre-prune-native-3",
                            reader=f.read, page_reader=f.read_page,
                            evidence_node_ids=[target], jsx_reader=lambda *_: "(<div>same</div>)")

    def test_pre_prune_jsx_drift_and_evidence_omission_refused(self):
        f = Copy()
        body = '(\\n  <div id="1-1">original</div>\\n)'
        plan = g.make_plan(SRC, CLONE, ["p-1-0"], "pre-prune-native-4",
                           reader=f.read, page_reader=f.read_page,
                           evidence_node_ids=["1-1"], jsx_reader=lambda *_: body)
        f.delete_clone_page_2()
        with self.assertRaisesRegex(g.bridge.Refusal, "RETAINED_NATIVE_JSX_DRIFT"):
            g.verify_plan(plan, reader=f.read, page_reader=f.read_page,
                          jsx_reader=lambda *_: "(<div>changed text without node count change</div>)")
        with self.assertRaisesRegex(g.bridge.Refusal, "PRE_PRUNE_JSX_TARGET_MISMATCH"):
            g.verify_plan(plan, reader=f.read, page_reader=f.read_page,
                          evidence_node_ids=["another-id"], jsx_reader=lambda *_: body)
        tampered = copy.deepcopy(plan)
        tampered["pre_prune_native_jsx"].clear()
        with self.assertRaisesRegex(g.bridge.Refusal, "PRE_PRUNE_JSX_PLAN_INVALID"):
            g.verify_plan(tampered, reader=f.read, page_reader=f.read_page)

    def test_plan_no_modifying_dispatch(self):
        f = Copy()
        f.plan()
        self.assertEqual(f.calls, [SRC, CLONE])
        self.assertFalse(hasattr(g, "delete_page"))
        self.assertFalse(hasattr(g, "clone_file"))


if __name__ == "__main__":
    unittest.main()
