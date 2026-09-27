"""Bounded file-focus safety tests. No real Paper document is opened."""
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
        self.assertTrue((ROOT / "prepare.py").exists(), "Bounded API file preparation is not implemented")
        self.b = load("paper_prepare_guard_fixture", ROOT / "bridge.py")
        with patch.dict(sys.modules, {"bridge": self.b}):
            self.p = load("paper_prepare_fixture", ROOT / "prepare.py")
        self.info = {"fileId": CURRENT, "fileName": "Fixture", "pageName": "Page 1", "artboards": []}
        self.calls = []
        owner = self

        class Client:
            server = {"name": "fixture", "version": "1"}
            fail_initial = None
            fail_after = False
            lost_reply = False
            tool_error = False
            wrong_file = False
            missing_open_tool = False

            def initialize(self):
                if self.fail_initial:
                    raise owner.b.Refusal(self.fail_initial)

            def catalog(self):
                tools = {"get_basic_info": {"name": "get_basic_info", "inputSchema": {"type": "object"}}}
                if not self.missing_open_tool:
                    tools["open_file"] = {"name": "open_file", "inputSchema": {"type": "object"}}
                return tools

            def call(self, name, arguments):
                owner.calls.append((name, copy.deepcopy(arguments)))
                if name == "get_basic_info":
                    if self.fail_after and any(n == "open_file" for n, _ in owner.calls):
                        raise owner.b.Refusal("UPSTREAM_FORBIDDEN")
                    return {"structuredContent": copy.deepcopy(owner.info)}
                if name == "open_file":
                    if not self.wrong_file:
                        owner.info["fileId"] = arguments["fileId"]
                    if self.lost_reply:
                        raise TimeoutError()
                    return {"isError": self.tool_error, "structuredContent": copy.deepcopy(owner.info)}
                raise AssertionError("Unexpected vendor call")

        self.client = Client()
        self.expected = self.b.digest(self.info)

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self, **kwargs):
        parameters = dict(file_id=TARGET, expected_snapshot=self.expected,
                          operation_id="prepare-test-1", allow_prepare=True,
                          client=self.client, lock_root=self.root,
                          _server_pin=None, _catalog_pin=None, _sleep=lambda _: None)
        parameters.update(kwargs)
        return self.p.prepare_document(**parameters)

    def opens(self):
        return [(n, a) for n, a in self.calls if n == "open_file"]

    def test_requires_explicit_prepare_opt_in(self):
        with self.assertRaisesRegex(self.b.Refusal, "PREPARE_DISABLED"):
            self.prepare(allow_prepare=False)
        self.assertEqual(self.calls, [])

    def test_rejects_urls_routes_paths_and_non_ulid_ids(self):
        for value in ("https://paper.design/file/" + TARGET, "/file/" + TARGET,
                      "paper://file/" + TARGET, "/tmp/test", TARGET.lower(), "x", "A" * 500):
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

    def test_fresh_snapshot_precedes_focus(self):
        self.info["pageName"] = "Human changed this"
        with self.assertRaisesRegex(self.b.Refusal, "DOCUMENT_CHANGED"):
            self.prepare()
        self.assertEqual(self.opens(), [])

    def test_reuses_bridge_desktop_mutex(self):
        with self.b.desktop_lock(self.root):
            with self.assertRaisesRegex(self.b.Refusal, "DESKTOP_BUSY"):
                self.prepare()
        self.assertEqual(self.opens(), [])

    def test_initial_denial_never_opens_file(self):
        self.client.fail_initial = "UPSTREAM_FORBIDDEN"
        with self.assertRaisesRegex(self.b.Refusal, "UPSTREAM_FORBIDDEN"):
            self.prepare()
        self.assertEqual(self.calls, [])

    def test_schema_drift_refuses_focus(self):
        with self.assertRaisesRegex(self.b.Refusal, "UPSTREAM_SCHEMA_UNREVIEWED"):
            self.prepare(_catalog_pin="0" * 64)
        self.assertEqual(self.opens(), [])

    def test_missing_open_tool_refuses_focus(self):
        self.client.missing_open_tool = True
        with self.assertRaisesRegex(self.b.Refusal, "TOOL_NOT_AVAILABLE"):
            self.prepare()
        self.assertEqual(self.opens(), [])

    def test_already_active_file_is_verified_without_open(self):
        result = self.prepare(file_id=CURRENT)
        self.assertEqual(result["state"], "PAPER_READY")
        self.assertTrue(result["already_active"])
        self.assertFalse(result["open_attempted"])
        self.assertEqual(self.opens(), [])

    def test_already_active_schema_drift_is_readonly_ready(self):
        result = self.prepare(file_id=CURRENT, _catalog_pin="0" * 64)
        self.assertEqual(result["state"], "PAPER_READY_READ_ONLY")
        self.assertFalse(result["write_qualified"])
        self.assertEqual(self.opens(), [])

    def test_exact_bare_id_only_is_forwarded_once(self):
        result = self.prepare()
        self.assertEqual(self.opens(), [("open_file", {"fileId": TARGET})])
        self.assertEqual(result["state"], "PAPER_READY")
        self.assertEqual(result["file_id"], TARGET)
        self.assertEqual(result["after"]["identity"]["id"], TARGET)
        self.assertEqual(result["snapshot_sha256"], self.b.digest(self.info))
        self.assertEqual(result["operation_id"], "prepare-test-1")
        self.assertFalse(result["retry_allowed"])
        self.assertFalse(result["production_acceptance"])

    def test_post_read_is_untargeted_active_file_observation(self):
        self.prepare()
        self.assertTrue(all(a == {} for n, a in self.calls if n == "get_basic_info"))
        self.assertGreaterEqual(sum(n == "get_basic_info" for n, _ in self.calls), 2)

    def test_wrong_file_is_unknown_never_retried(self):
        self.client.wrong_file = True
        result = self.prepare()
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertFalse(result["retry_allowed"])
        self.assertEqual(len(self.opens()), 1)
        self.assertLessEqual(len(self.calls), 8)

    def test_lost_reply_stays_unknown_with_post_read_evidence(self):
        self.client.lost_reply = True
        result = self.prepare()
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertEqual(result["after"]["identity"]["id"], TARGET)
        self.assertFalse(result["response_observed"])
        self.assertFalse(result["retry_allowed"])
        self.assertEqual(len(self.opens()), 1)

    def test_upstream_error_does_not_masquerade_as_success(self):
        self.client.tool_error = True
        result = self.prepare()
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertFalse(result["retry_allowed"])
        self.assertEqual(len(self.opens()), 1)

    def test_post_read_denial_stops_observation_loop(self):
        self.client.fail_after = True
        result = self.prepare()
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertEqual(len(self.opens()), 1)
        self.assertEqual(sum(n == "get_basic_info" for n, _ in self.calls), 2)

    def test_raw_open_remains_blocked_in_original_guard(self):
        self.assertNotIn("open_file", self.b.READ_TOOLS)
        self.assertNotIn("open_file", self.b.EDIT_TOOLS)


if __name__ == "__main__":
    unittest.main()
