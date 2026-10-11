"""Bounded explicit-file preparation safety tests. No real Paper document is mutated."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "integrations/paper_desktop"
CURRENT = "01" + "A" * 24
TARGET = "01" + "B" * 24


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.b = load("paper_prepare_guard_fixture", ROOT / "bridge.py")
        with patch.dict(sys.modules, {"bridge": self.b}):
            self.p = load("paper_prepare_fixture", ROOT / "prepare.py")
        self.active_info = {
            "fileId": CURRENT, "fileName": "Active", "pageName": "Page 1", "artboards": []
        }
        self.target_info = {
            "fileId": TARGET, "fileName": "Target", "pageName": "Page 1", "artboards": []
        }
        self.calls = []
        owner = self

        class Client:
            server = {"name": "fixture", "version": "1"}
            fail_initial = None
            fail_target = None
            wrong_target = False
            missing_open_tool = False

            def initialize(self):
                if self.fail_initial:
                    raise owner.b.Refusal(self.fail_initial)

            def catalog(self):
                tools = {
                    "get_basic_info": {
                        "name": "get_basic_info",
                        "inputSchema": {"type": "object"},
                    }
                }
                if not self.missing_open_tool:
                    tools["open_file"] = {
                        "name": "open_file",
                        "inputSchema": {"type": "object"},
                    }
                return tools

            def call(self, name, arguments):
                owner.calls.append((name, copy.deepcopy(arguments)))
                if name != "get_basic_info":
                    raise AssertionError("prepare must not dispatch vendor open_file")
                if arguments.get("fileId") == TARGET:
                    if self.fail_target:
                        raise owner.b.Refusal(self.fail_target)
                    value = owner.active_info if self.wrong_target else owner.target_info
                    return {"structuredContent": copy.deepcopy(value)}
                if arguments:
                    raise AssertionError("unexpected target")
                return {"structuredContent": copy.deepcopy(owner.active_info)}

        self.client = Client()
        self.expected = self.b.digest(self.target_info)

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self, **kwargs):
        parameters = dict(
            file_id=TARGET,
            expected_snapshot=self.expected,
            operation_id="prepare-test-1",
            allow_prepare=True,
            client=self.client,
            lock_root=self.root,
            _server_pin=None,
            _catalog_pin=None,
            _sleep=lambda _: None,
        )
        parameters.update(kwargs)
        return self.p.prepare_document(**parameters)

    def opens(self):
        return [(n, a) for n, a in self.calls if n == "open_file"]

    def test_requires_explicit_prepare_opt_in(self):
        with self.assertRaisesRegex(self.b.Refusal, "PREPARE_DISABLED"):
            self.prepare(allow_prepare=False)
        self.assertEqual(self.calls, [])

    def test_rejects_urls_routes_paths_and_non_ulid_ids(self):
        for value in (
            "https://paper.design/file/" + TARGET,
            "/file/" + TARGET,
            "paper://file/" + TARGET,
            "/tmp/test",
            TARGET.lower(),
            "x",
            "A" * 500,
        ):
            with self.subTest(value=value), self.assertRaisesRegex(self.b.Refusal, "FILE_ID"):
                self.prepare(file_id=value)
        self.assertEqual(self.calls, [])

    def test_rejects_invalid_operation_id(self):
        with self.assertRaisesRegex(self.b.Refusal, "OPERATION_ID"):
            self.prepare(operation_id="invalid op")
        self.assertEqual(self.calls, [])

    def test_requires_snapshot(self):
        with self.assertRaisesRegex(self.b.Refusal, "SNAPSHOT"):
            self.prepare(expected_snapshot="invalid")
        self.assertEqual(self.calls, [])

    def test_foreground_drift_does_not_block_exact_target_binding(self):
        self.active_info["pageName"] = "Human changed this"
        result = self.prepare()
        self.assertEqual(result["state"], "PAPER_READY")
        self.assertEqual(result["after"]["identity"]["id"], TARGET)
        self.assertEqual(
            self.calls, [("get_basic_info", {"fileId": TARGET})],
            "prepare must bind only the explicit target, not unrelated foreground context",
        )

    def test_reuses_bridge_desktop_mutex(self):
        with self.b.desktop_lock(self.root), patch.object(self.b, "DESKTOP_LOCK_WAIT_SECONDS", 0):
            with self.assertRaisesRegex(self.b.Refusal, "DESKTOP_BUSY"):
                self.prepare()
        self.assertEqual(self.calls, [])

    def test_initial_denial_never_reads_target(self):
        self.client.fail_initial = "UPSTREAM_FORBIDDEN"
        with self.assertRaisesRegex(self.b.Refusal, "UPSTREAM_FORBIDDEN"):
            self.prepare()
        self.assertEqual(self.calls, [])

    def test_background_target_schema_drift_is_readonly_ready(self):
        result = self.prepare(_catalog_pin="0" * 64)
        self.assertEqual(result["state"], "PAPER_READY_READ_ONLY")
        self.assertFalse(result["write_qualified"])
        self.assertTrue(result["target_addressable"])
        self.assertIsNone(result["target_active"])
        self.assertEqual(result["after"]["identity"]["id"], TARGET)
        self.assertEqual(self.opens(), [])

    def test_vendor_open_tool_is_not_required(self):
        self.client.missing_open_tool = True
        result = self.prepare()
        self.assertEqual(result["state"], "PAPER_READY")
        self.assertEqual(result["prepare_mode"], "EXPLICIT_FILE_BINDING")
        self.assertEqual(self.opens(), [])

    def test_active_file_state_is_not_required_for_target_binding(self):
        self.active_info = copy.deepcopy(self.target_info)
        result = self.prepare()
        self.assertEqual(result["state"], "PAPER_READY")
        self.assertIsNone(result["already_active"])
        self.assertIsNone(result["target_active"])
        self.assertFalse(result["active_context_required"])
        self.assertTrue(result["target_addressable"])
        self.assertFalse(result["open_attempted"])
        self.assertEqual(
            self.calls, [("get_basic_info", {"fileId": TARGET})],
        )
        self.assertEqual(self.opens(), [])

    def test_target_schema_drift_is_readonly_ready_even_if_target_is_active(self):
        self.active_info = copy.deepcopy(self.target_info)
        result = self.prepare(_catalog_pin="0" * 64)
        self.assertEqual(result["state"], "PAPER_READY_READ_ONLY")
        self.assertFalse(result["write_qualified"])
        self.assertIsNone(result["target_active"])
        self.assertEqual(self.opens(), [])

    def test_background_target_is_bound_without_vendor_open(self):
        result = self.prepare()
        self.assertEqual(result["state"], "PAPER_READY")
        self.assertIsNone(result["already_active"])
        self.assertFalse(result["open_attempted"])
        self.assertTrue(result["target_observed"])
        self.assertIsNone(result["target_active"])
        self.assertTrue(result["target_addressable"])
        self.assertEqual(result["after"]["identity"]["id"], TARGET)
        self.assertEqual(result["snapshot_sha256"], self.b.digest(self.target_info))
        self.assertEqual(result["operation_id"], "prepare-test-1")
        self.assertEqual(result["concurrency_rule"], "MULTI_WRITER_PER_FILE_TARGET_SCOPED")
        self.assertTrue(result["same_file_multi_writer_allowed"])
        self.assertTrue(result["same_page_multi_writer_allowed"])
        self.assertEqual(result["coordination_scope"], "BOARD_ARTBOARD_NODE")
        self.assertFalse(result["retry_allowed"])
        self.assertFalse(result["production_acceptance"])
        self.assertEqual(self.opens(), [])
        self.assertEqual(
            self.calls,
            [("get_basic_info", {"fileId": TARGET})],
        )

    def test_target_mismatch_refuses_without_effect(self):
        self.client.wrong_target = True
        with self.assertRaisesRegex(self.b.Refusal, "FILE_ID_MISMATCH"):
            self.prepare()
        self.assertEqual(self.opens(), [])
        self.assertEqual(
            self.calls,
            [("get_basic_info", {"fileId": TARGET})],
        )

    def test_target_read_denial_refuses_without_effect(self):
        self.client.fail_target = "UPSTREAM_FORBIDDEN"
        with self.assertRaisesRegex(self.b.Refusal, "UPSTREAM_FORBIDDEN"):
            self.prepare()
        self.assertEqual(self.opens(), [])
        self.assertEqual(
            self.calls,
            [("get_basic_info", {"fileId": TARGET})],
        )

    def test_raw_open_remains_blocked_in_original_guard(self):
        self.assertNotIn("open_file", self.b.READ_TOOLS)
        self.assertNotIn("open_file", self.b.EDIT_TOOLS)


if __name__ == "__main__":
    unittest.main()
