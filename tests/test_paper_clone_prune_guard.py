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

    def read(self, file_id):
        self.calls.append(file_id)
        return copy.deepcopy(self.infos[file_id])

    def plan(self, keep=("p-1-0",)):
        return g.make_plan(SRC, CLONE, list(keep), "scratch-copy-prune-20261022", reader=self.read)

    def delete_clone_page_2(self):
        self.infos[CLONE]["pages"] = [copy.deepcopy(PAGES[0])]


class ClonePruneGuardTests(unittest.TestCase):
    def test_bridge_import_is_private_and_does_not_shadow_package(self):
        self.assertEqual(g.bridge.__name__, "_mastermind_paper_clone_prune_bridge")
        self.assertNotIn(str(PAPER), sys.path)
        ambient = sys.modules.get("bridge")
        if ambient is not None:
            self.assertNotEqual(Path(getattr(ambient, "__file__", "/")).resolve(),
                                (PAPER / "bridge.py").resolve())

    def test_exact_two_file_scratch_clone_prune_readback(self):
        fixture = Copy()
        plan = fixture.plan()
        self.assertEqual(plan["state"], "CLONE_PRUNE_PLAN_READY")
        self.assertEqual(plan["keep_page_ids"], ["p-1-0"])
        self.assertEqual(plan["remove_pages"][0]["id"], "p-3-0")
        self.assertEqual(fixture.calls, [SRC, CLONE])
        fixture.delete_clone_page_2()
        verified = g.verify_plan(plan, reader=fixture.read)
        self.assertEqual(verified["state"], "CLONE_PRUNE_METADATA_VERIFIED")
        self.assertEqual(verified["clone_removed_page_ids"], ["p-3-0"])
        self.assertEqual(verified["source_unchanged_page_ids"], ["p-1-0", "p-3-0"])
        self.assertFalse(verified["original_deletion_authorized"])
        self.assertFalse(verified["production_migration_accepted"])
        self.assertFalse(verified["image_component_comment_fidelity_verified"])
        self.assertEqual(fixture.calls, [SRC, CLONE, SRC, CLONE])

    def test_source_and_clone_identity_guards(self):
        fixture = Copy()
        with self.assertRaisesRegex(g.bridge.Refusal, "SOURCE_EQUALS_CLONE"):
            g.make_plan(SRC, SRC, ["p-1-0"], "op", reader=fixture.read)
        self.assertEqual(fixture.calls, [])
        for file_id in ("", "other", "../../fake", SRC.lower()):
            with self.subTest(file_id=file_id), self.assertRaisesRegex(g.bridge.Refusal, "FILE_ID_REQUIRED"):
                g.make_plan(file_id, CLONE, ["p-1-0"], "op", reader=fixture.read)
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
            g.verify_plan(plan, reader=f.read)
        self.assertEqual(len(f.infos[CLONE]["pages"]), 2)

    def test_extra_clone_page_blocks_verification(self):
        f = Copy()
        plan = f.plan()
        f.infos[CLONE]["pages"] = [copy.deepcopy(PAGES[0]), {
            "type": "page", "id": "p-extra", "name": "Unplanned", "icon": None,
        }]
        with self.assertRaisesRegex(g.bridge.Refusal, "CLONE_PRUNE_UNVERIFIED"):
            g.verify_plan(plan, reader=f.read)

    def test_source_changed_blocks_verification(self):
        f = Copy()
        plan = f.plan()
        f.delete_clone_page_2()
        f.infos[SRC]["pages"][1]["name"] = "Changed"
        with self.assertRaisesRegex(g.bridge.Refusal, "SOURCE_CHANGED"):
            g.verify_plan(plan, reader=f.read)

    def test_source_token_drift_blocks_verification(self):
        f = Copy()
        plan = f.plan()
        f.delete_clone_page_2()
        f.infos[SRC]["contentHash"]["tokens"] = "drift"
        with self.assertRaisesRegex(g.bridge.Refusal, "SOURCE_TOKENS_CHANGED"):
            g.verify_plan(plan, reader=f.read)

    def test_clone_token_drift_blocks_verification(self):
        f = Copy()
        plan = f.plan()
        f.delete_clone_page_2()
        f.infos[CLONE]["contentHash"]["tokens"] = "drift"
        with self.assertRaisesRegex(g.bridge.Refusal, "CLONE_TOKENS_CHANGED"):
            g.verify_plan(plan, reader=f.read)

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
                    g.verify_plan(plan, reader=f.read)

    def test_selected_native_jsx_exact_parity_passes(self):
        f = Copy()
        plan = f.plan()
        f.delete_clone_page_2()
        jsx_reads = []
        def jsx(file_id, node_id):
            jsx_reads.append((file_id, node_id))
            return '(\n  <div id="1-1" style={{ color: "#ffffff" }}>content</div>\n)'
        result = g.verify_plan(plan, reader=f.read,
                               evidence_node_ids=["1-1"], jsx_reader=jsx)
        self.assertEqual(result["exact_jsx_node_ids_verified"], ["1-1"])
        self.assertFalse(result["full_page_visual_fidelity_verified"])
        self.assertEqual(jsx_reads, [(SRC, "1-1"), (CLONE, "1-1")])

    def test_selected_jsx_mismatch_fails_closed(self):
        f = Copy()
        plan = f.plan()
        f.delete_clone_page_2()
        with self.assertRaisesRegex(g.bridge.Refusal, "CLONE_JSX_MISMATCH"):
            g.verify_plan(plan, reader=f.read, evidence_node_ids=["1-1"],
                          jsx_reader=lambda file_id, node_id: (
                              "(<div>same</div>)" if file_id == SRC else "(<div>wrong</div>)"))

    def test_invalid_jsx_targets_and_non_jsx_reads_refused(self):
        f = Copy()
        plan = f.plan()
        f.delete_clone_page_2()
        for node_ids in ([""], ["1-1", "1-1"], ["x" * 121], list(map(str, range(25)))):
            with self.subTest(node_ids=node_ids), self.assertRaisesRegex(
                    g.bridge.Refusal, "INVALID_JSX_EVIDENCE_TARGETS"):
                g.verify_plan(plan, reader=f.read, evidence_node_ids=node_ids)
        with self.assertRaisesRegex(g.bridge.Refusal, "JSX_SCHEMA_UNVERIFIED"):
            g.verify_plan(plan, reader=f.read, evidence_node_ids=["1-1"],
                          jsx_reader=lambda *_: "unexpected tool error")

    def test_plan_no_modifying_dispatch(self):
        f = Copy()
        f.plan()
        self.assertEqual(f.calls, [SRC, CLONE])
        self.assertFalse(hasattr(g, "delete_page"))
        self.assertFalse(hasattr(g, "clone_file"))


if __name__ == "__main__":
    unittest.main()
