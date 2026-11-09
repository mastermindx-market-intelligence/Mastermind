"""Fail-closed clone/prune evidence checks: never click or delete Paper pages."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

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

WARNING = "Warning: Your file is too large. Further changes will result in data loss. Please start a new file."


def jsx_result(file_id=SRC, node_id="1-1", warnings=(), text="content"):
    return {"state": "OBSERVED", "result": {"content": [
        {"type": "text", "text": json.dumps({"file": {"id": file_id, "name": "Source"},
                                             "contentHash": {"tokens": "c1"}})},
        *[{"type": "text", "text": w} for w in warnings],
        {"type": "text", "text": f'(\n  <div id="{node_id}" style={{{{ color: "#ffffff" }}}}>{text}</div>\n)'},
    ]}}


class NativeJsxObservationTests(unittest.TestCase):
    def test_warning_is_retained_but_never_the_compared_body(self):
        raw = jsx_result(warnings=[WARNING])
        with patch.object(g.bridge, "execute", return_value=raw) as execute:
            observed = g._read_jsx_observation(SRC, "1-1")
        self.assertEqual(observed["warnings"], [WARNING])
        self.assertEqual(observed["body"], raw["result"]["content"][-1]["text"])
        self.assertEqual(observed["file_id"], SRC)
        self.assertEqual(observed["node_id"], "1-1")
        self.assertEqual(execute.call_args.args, ("read",))

    def test_two_block_body_remains_byte_exact(self):
        raw = jsx_result()
        with patch.object(g.bridge, "execute", return_value=raw):
            self.assertEqual(g._read_jsx(SRC, "1-1"), raw["result"]["content"][1]["text"])

    def test_warning_does_not_upgrade_prune_readiness(self):
        with patch.object(g.bridge, "execute", return_value=jsx_result(warnings=[WARNING])):
            with self.assertRaisesRegex(g.bridge.Refusal, "JSX_WARNING_REQUIRES_REVIEW"):
                g._read_jsx(SRC, "1-1")

    def test_wrong_file_and_wrong_root_are_rejected(self):
        for raw, reason in ((jsx_result(CLONE), "JSX_FILE_ID_MISMATCH"),
                            (jsx_result(node_id="other", text='<div id="1-1">nested</div>'),
                             "JSX_ROOT_ID_MISMATCH")):
            with self.subTest(reason=reason), patch.object(g.bridge, "execute", return_value=raw):
                with self.assertRaisesRegex(g.bridge.Refusal, reason):
                    g._read_jsx(SRC, "1-1")

    def test_conflicting_identity_aliases_and_duplicate_json_keys(self):
        for header in (
            {"file": {"id": SRC, "name": "Source"}, "fileId": CLONE},
            {"file": {"id": SRC, "name": "Source"}, "documentId": CLONE},
        ):
            raw = jsx_result()
            raw["result"]["content"][0]["text"] = json.dumps(header)
            with self.subTest(header=header), patch.object(g.bridge, "execute", return_value=raw):
                with self.assertRaisesRegex(g.bridge.Refusal, "JSX_FILE_ID_MISMATCH"):
                    g._read_jsx(SRC, "1-1")
        raw = jsx_result()
        raw["result"]["content"][0]["text"] = '{"file":{"id":"' + SRC + '","id":"' + CLONE + '","name":"Source"}}'
        with patch.object(g.bridge, "execute", return_value=raw):
            with self.assertRaisesRegex(g.bridge.Refusal, "DUPLICATE_JSON_KEY"):
                g._read_jsx(SRC, "1-1")

    def test_malformed_or_ambiguous_transport_is_rejected(self):
        cases = []
        raw = jsx_result(); raw["state"] = "EFFECT_UNKNOWN"; cases.append(raw)
        raw = jsx_result(); raw["result"]["isError"] = True; cases.append(raw)
        raw = jsx_result(); raw["result"]["content"].pop(0); cases.append(raw)
        raw = jsx_result(); raw["result"]["content"].append(copy.deepcopy(raw["result"]["content"][-1])); cases.append(raw)
        raw = jsx_result(); raw["result"]["content"].insert(1, {"type": "text", "text": "Unknown operation error"}); cases.append(raw)
        raw = jsx_result(); raw["result"]["content"].append({"type": "text", "text": WARNING}); cases.append(raw)
        raw = jsx_result(); raw["result"]["structuredContent"] = {"fileId": CLONE}; cases.append(raw)
        raw = jsx_result(); raw["result"]["content"][-1]["text"] = '(<div id="1-1">unfinished'; cases.append(raw)
        raw = jsx_result(); raw["result"]["content"][0]["text"] = '{"file":{"id":"' + SRC + '","name":"Source"},"contentHash":{"tokens":NaN}}'; cases.append(raw)
        raw = jsx_result(); raw["result"]["content"].insert(1, {"type": "image", "data": "invalid"}); cases.append(raw)
        raw = jsx_result(); raw["result"]["truncated"] = True; cases.append(raw)
        raw = jsx_result(); raw["result"]["isError"] = 0; cases.append(raw)
        raw = jsx_result(); raw["result"]["content"][-1]["text"] = '(<div id="1-1" id="other">bad</div>)'; cases.append(raw)
        cases.extend([{}, {"state": "OBSERVED", "result": []}])
        for i, raw in enumerate(cases):
            with self.subTest(case=i), patch.object(g.bridge, "execute", return_value=raw):
                with self.assertRaises(g.bridge.Refusal):
                    g._read_jsx_observation(SRC, "1-1")


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


class NativePairCompareTests(unittest.TestCase):
    def compare(self, fixture, **kwargs):
        return g.compare_file_pair(SRC, CLONE, reader=fixture.read,
                                   page_reader=fixture.read_page, **kwargs)

    def test_intact_unpruned_pair_has_a_real_scoped_success_path(self):
        f = Copy()
        result = self.compare(f)
        self.assertEqual(result["state"], "OBSERVED_SCOPE_PARITY")
        self.assertTrue(result["complete_file_native_census_observed"])
        self.assertFalse(result["all_artboards_jsx_compared"])
        self.assertFalse(result["native_restore_verified"])
        self.assertFalse(result["resource_actions_authorized"])
        self.assertFalse(result["atomic_native_revision_bound"])
        self.assertEqual(result["paper_mutations"], 0)
        self.assertEqual(f.calls, [SRC, CLONE, SRC, CLONE])
        self.assertEqual(f.infos[CLONE]["pages"], PAGES)

    def test_missing_page_is_observed_divergence_not_pruning(self):
        f = Copy()
        f.delete_clone_page_2()
        result = self.compare(f)
        self.assertEqual(result["state"], "OBSERVED_SCOPE_DIVERGENCE")
        self.assertEqual(result["missing_source_page_ids"], ["p-3-0"])
        self.assertFalse(result["complete_file_native_census_observed"])
        self.assertEqual(f.infos[SRC]["pages"], PAGES)

    def test_native_counts_detect_content_changes_despite_token_parity(self):
        f = Copy()
        f.page_infos[CLONE]["p-1-0"]["nodeCount"] += 8
        result = self.compare(f)
        self.assertTrue(result["token_hash_equal"])
        self.assertEqual(result["state"], "OBSERVED_SCOPE_DIVERGENCE")

    def test_selected_page_is_never_whole_file_census(self):
        result = self.compare(Copy(), page_ids=["p-1-0"])
        self.assertEqual(result["native_page_scope_ids"], ["p-1-0"])
        self.assertFalse(result["complete_file_native_census_observed"])

    def test_equal_warning_text_does_not_hide_jsx_divergence(self):
        def native(action, *, tool, arguments):
            self.assertEqual((action, tool), ("read", "get_jsx"))
            file_id = arguments["fileId"]
            return jsx_result(file_id, warnings=[WARNING], text="source" if file_id == SRC else "changed")
        with patch.object(g.bridge, "execute", side_effect=native) as execute:
            result = self.compare(Copy(), evidence_node_ids=["1-1"])
        self.assertEqual(result["state"], "OBSERVED_SCOPE_DIVERGENCE")
        self.assertEqual([w["text"] for w in result["warnings"]], [WARNING, WARNING])
        self.assertEqual(execute.call_count, 2)
        self.assertFalse(result["selected_artboard_jsx_comparisons"][0]["exact_jsx_equal"])
        self.assertFalse(result["native_restore_verified"])

    def test_selected_jsx_parity_is_not_restore(self):
        with patch.object(g.bridge, "execute", side_effect=lambda action, *, tool, arguments:
                          jsx_result(arguments["fileId"])):
            result = self.compare(Copy(), evidence_node_ids=["1-1"])
        self.assertTrue(result["all_artboards_jsx_compared"])
        self.assertTrue(result["selected_artboard_jsx_comparisons"][0]["exact_jsx_equal"])
        self.assertFalse(result["native_restore_verified"])
        self.assertFalse(result["resource_actions_authorized"])

    def test_capped_or_duplicate_page_census_refused(self):
        for change in (dict(artboardCount=2), dict(truncated=True)):
            f = Copy(); f.page_infos[CLONE]["p-1-0"].update(change)
            with self.subTest(change=change), self.assertRaisesRegex(g.bridge.Refusal, "NATIVE_PAGE_CENSUS_INCOMPLETE"):
                self.compare(f)
        for change in (dict(pageCount=3), dict(truncated=True)):
            f = Copy(); f.infos[CLONE].update(change)
            with self.subTest(change=change), self.assertRaisesRegex(g.bridge.Refusal, "PAGE_LIST_INCOMPLETE"):
                self.compare(f)

    def test_invalid_scopes_are_refused_before_jsx_reads(self):
        for kwargs in (dict(page_ids=[]), dict(page_ids=["unknown"]),
                       dict(page_ids=["p-1-0", "p-1-0"]),
                       dict(page_ids=["p-3-0"], evidence_node_ids=["1-1"])):
            with self.subTest(kwargs=kwargs), patch.object(g.bridge, "execute") as execute:
                with self.assertRaises(g.bridge.Refusal):
                    self.compare(Copy(), **kwargs)
                execute.assert_not_called()

    def test_metadata_drift_during_read_window_is_refused(self):
        f = Copy()
        def read(file_id):
            result = f.read(file_id)
            if len(f.calls) > 2:
                result["fileName"] = "renamed meanwhile"
            return result
        with self.assertRaisesRegex(g.bridge.Refusal, "FILE_METADATA_DRIFT_DURING_COMPARE"):
            g.compare_file_pair(SRC, CLONE, reader=read, page_reader=f.read_page)

    def test_missing_tokens_are_unknown_not_equal(self):
        f = Copy()
        for info in f.infos.values():
            info.pop("contentHash")
        result = self.compare(f)
        self.assertIsNone(result["token_hash_equal"])
        self.assertEqual(result["state"], "OBSERVED_SCOPE_INCOMPLETE")
        self.assertFalse(result["native_restore_verified"])

    def test_compare_cli_preserves_distinct_exit_states(self):
        args = ["clone_prune_guard", "compare", "--source-file-id", SRC,
                "--clone-file-id", CLONE, "--page-id", "p-1-0", "--verify-node-id", "1-1"]
        for state, code in (("OBSERVED_SCOPE_PARITY", 0),
                            ("OBSERVED_SCOPE_DIVERGENCE", 3),
                            ("OBSERVED_SCOPE_INCOMPLETE", 4)):
            with self.subTest(state=state), patch.object(sys, "argv", args), \
                 patch.object(g, "compare_file_pair", return_value={"state": state}) as compare, \
                 patch.object(sys, "stdout", new_callable=io.StringIO):
                self.assertEqual(g.main(), code)
                compare.assert_called_once_with(SRC, CLONE, page_ids=["p-1-0"],
                                                evidence_node_ids=["1-1"])

    def test_empty_token_digest_does_not_become_parity(self):
        f = Copy()
        for info in f.infos.values():
            info["contentHash"]["tokens"] = ""
        self.assertEqual(self.compare(f)["state"], "OBSERVED_SCOPE_INCOMPLETE")

    def test_basic_read_uses_actual_requested_result_and_preserves_warning(self):
        raw = {"state": "OBSERVED", "document": {"basic_info": {"fileId": CLONE}},
               "result": {"content": [
                   {"type": "text", "text": json.dumps({"file": {"id": SRC, "name": "Source"}})},
                   {"type": "text", "text": WARNING},
                   {"type": "text", "text": json.dumps({"fileName": "Source", "pageName": "Page 1",
                       "pageId": "p-1-0", "artboards": [], "pages": PAGES})},
               ]}}
        warnings = []
        with patch.object(g.bridge, "execute", return_value=raw):
            observed = g._read(SRC, warnings=warnings)
        self.assertEqual(observed["fileId"], SRC)
        self.assertEqual(warnings, [{"file_id": SRC, "page_id": None, "text": WARNING}])
        with patch.object(g.bridge, "execute", return_value=raw):
            with self.assertRaisesRegex(g.bridge.Refusal, "NATIVE_READ_WARNING_REQUIRES_REVIEW"):
                g.make_plan(SRC, CLONE, ["p-1-0"], "no-prune-when-warned")


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


class BasicInfoEnvelopeTruncationTests(unittest.TestCase):
    """An explicitly truncated outer envelope must be refused before normalization.

    The vendor may mark a get_basic_info response, or its result envelope, as
    truncated. The guard normalizes the result into a file/page census, so an
    envelope flag that is dropped before normalization lets a partial
    observation become a file census, a scoped parity or a prune readiness.
    Absent and literal False stay valid; only literal True is refused.
    """

    FILE_NAMES = {SRC: "Young harmony", CLONE: "Young harmony (copy)"}

    def _file_payload(self, file_id):
        return {"fileId": file_id, "fileName": self.FILE_NAMES[file_id],
                "pages": copy.deepcopy(PAGES), "contentHash": {"tokens": "c1"}}

    def _page_payload(self, file_id, page):
        boards = ([{"id": "1-1", "name": "Migration fidelity specimen", "childCount": 3}]
                  if page["id"] == "p-1-0" else [])
        return {"fileId": file_id, "fileName": self.FILE_NAMES[file_id],
                "pageId": page["id"], "pageName": page["name"],
                "nodeCount": 5 if boards else 1, "artboardCount": len(boards),
                "artboards": boards, "fontFamilies": ["Inter"] if boards else []}

    def _response(self, payload, *, outer=None, result=None, warning=False):
        content = [{"type": "text", "text": json.dumps(payload)}]
        if warning:
            content.append({"type": "text", "text": WARNING})
        envelope = {"content": content}
        if result is not None:
            envelope["truncated"] = result
        response = {"state": "OBSERVED", "result": envelope}
        if outer is not None:
            response["truncated"] = outer
        return response

    def _vendor(self, *, outer=None, result=None, warning=False):
        def native(action, *, tool, arguments):
            self.assertEqual((action, tool), ("read", "get_basic_info"))
            file_id = arguments["fileId"]
            page_id = arguments.get("pageId")
            if page_id is None:
                return self._response(self._file_payload(file_id), outer=outer,
                                      result=result, warning=warning)
            page = next(item for item in PAGES if item["id"] == page_id)
            return self._response(self._page_payload(file_id, page), outer=outer,
                                  result=result, warning=warning)
        return native

    def _expect_refusal(self, thunk, describe):
        try:
            outcome = thunk()
        except g.bridge.Refusal as exc:
            self.assertEqual(exc.code, "DOCUMENT_SCHEMA_UNVERIFIED",
                             "wrong refusal code %r" % (exc.code,))
            return
        self.fail("no refusal; accepted outcome: %s" % (describe(outcome),))

    def test_reject_read_refuses_outer_response_truncated(self):
        raw = self._response(self._file_payload(SRC), outer=True)
        with patch.object(g.bridge, "execute", return_value=raw):
            self._expect_refusal(
                lambda: g._read(SRC),
                lambda info: "file info fileId=%r pages=%r"
                % (info.get("fileId"), info.get("pages")))

    def test_reject_read_refuses_result_envelope_truncated(self):
        raw = self._response(self._file_payload(SRC), result=True)
        with patch.object(g.bridge, "execute", return_value=raw):
            self._expect_refusal(
                lambda: g._read(SRC),
                lambda info: "file info fileId=%r pages=%r"
                % (info.get("fileId"), info.get("pages")))

    def test_reject_native_page_refuses_outer_response_truncated(self):
        raw = self._response(self._page_payload(SRC, PAGES[0]), outer=True)
        with patch.object(g.bridge, "execute", return_value=raw):
            self._expect_refusal(
                lambda: g._read_native_page(SRC, PAGES[0]),
                lambda page: "page %r nodes=%r"
                % (page.get("page_id"), page.get("node_count")))

    def test_reject_native_page_refuses_result_envelope_truncated(self):
        raw = self._response(self._page_payload(SRC, PAGES[0]), result=True)
        with patch.object(g.bridge, "execute", return_value=raw):
            self._expect_refusal(
                lambda: g._read_native_page(SRC, PAGES[0]),
                lambda page: "page %r nodes=%r"
                % (page.get("page_id"), page.get("node_count")))

    def test_reject_compare_refuses_outer_response_truncated(self):
        with patch.object(g.bridge, "execute", side_effect=self._vendor(outer=True)):
            self._expect_refusal(
                lambda: g.compare_file_pair(SRC, CLONE),
                lambda out: "state=%r complete_file_native_census_observed=%r"
                % (out.get("state"), out.get("complete_file_native_census_observed")))

    def test_reject_compare_refuses_result_envelope_truncated(self):
        with patch.object(g.bridge, "execute", side_effect=self._vendor(result=True)):
            self._expect_refusal(
                lambda: g.compare_file_pair(SRC, CLONE),
                lambda out: "state=%r complete_file_native_census_observed=%r"
                % (out.get("state"), out.get("complete_file_native_census_observed")))

    def test_control_read_accepts_absent_and_false_truncated_flags(self):
        for label, outer, result in (("absent", None, None),
                                     ("outer-false", False, None),
                                     ("result-false", None, False),
                                     ("both-false", False, False)):
            with self.subTest(flags=label):
                raw = self._response(self._file_payload(SRC), outer=outer,
                                     result=result, warning=True)
                warnings = []
                with patch.object(g.bridge, "execute", return_value=raw):
                    info = g._read(SRC, warnings=warnings)
                self.assertEqual(info["fileId"], SRC)
                self.assertEqual(info["fileName"], self.FILE_NAMES[SRC])
                self.assertEqual(info["pages"], PAGES)
                self.assertEqual([w["text"] for w in warnings], [WARNING])

    def test_control_native_page_accepts_absent_and_false_truncated_flags(self):
        for label, outer, result in (("absent", None, None),
                                     ("outer-false", False, None),
                                     ("result-false", None, False),
                                     ("both-false", False, False)):
            with self.subTest(flags=label):
                raw = self._response(self._page_payload(SRC, PAGES[0]), outer=outer,
                                     result=result, warning=True)
                warnings = []
                with patch.object(g.bridge, "execute", return_value=raw):
                    page = g._read_native_page(SRC, PAGES[0], warnings=warnings)
                self.assertEqual(page["page_id"], "p-1-0")
                self.assertEqual(page["node_count"], 5)
                self.assertEqual(page["artboard_count"], 1)
                self.assertEqual(page["artboards"],
                                 [{"id": "1-1", "name": "Migration fidelity specimen",
                                   "childCount": 3}])
                self.assertEqual(page["font_families"], ["Inter"])
                self.assertEqual([w["text"] for w in warnings], [WARNING])

    def test_control_compare_reaches_scoped_parity_with_absent_and_false_flags(self):
        for label, outer, result in (("absent", None, None),
                                     ("outer-false", False, None),
                                     ("result-false", None, False),
                                     ("both-false", False, False)):
            with self.subTest(flags=label):
                with patch.object(g.bridge, "execute",
                                  side_effect=self._vendor(outer=outer, result=result)):
                    out = g.compare_file_pair(SRC, CLONE)
                self.assertEqual(out["state"], "OBSERVED_SCOPE_PARITY")
                self.assertTrue(out["complete_file_native_census_observed"])
                self.assertTrue(out["token_hash_equal"])
                self.assertFalse(out["native_restore_verified"])
                self.assertFalse(out["resource_actions_authorized"])
                self.assertFalse(out["atomic_native_revision_bound"])
                self.assertEqual(out["paper_mutations"], 0)
                self.assertEqual(out["native_page_scope_ids"], ["p-1-0", "p-3-0"])

    def test_control_warning_text_is_retained_under_valid_envelope_flags(self):
        with patch.object(g.bridge, "execute",
                          side_effect=self._vendor(outer=False, result=False, warning=True)):
            out = g.compare_file_pair(SRC, CLONE)
        texts = [w["text"] for w in out["warnings"]]
        self.assertTrue(texts)
        self.assertEqual(set(texts), {WARNING})
        self.assertEqual({w["file_id"] for w in out["warnings"]}, {SRC, CLONE})
        self.assertFalse(out["native_restore_verified"])
        self.assertFalse(out["resource_actions_authorized"])


if __name__ == "__main__":
    unittest.main()
