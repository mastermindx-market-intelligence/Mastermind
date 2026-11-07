"""Bounded history tests; no real database, gateway, model or credentials."""
import asyncio
import copy
import importlib.util
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

BRIDGE = Path(__file__).parents[1] / "app/mastermind_os/src-tauri/src/hermes_native/bridge.py"
SID, TIP, REQUEST = "local-original", "physical-tip", "b" * 32


def load():
    spec = importlib.util.spec_from_file_location("native_history_bridge", BRIDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Source:
    def __init__(self, **values):
        self.values = values

    def to_dict(self):
        return dict(self.values)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.b = load()
        self.directory = tempfile.TemporaryDirectory(prefix="native-history-fixture-")
        self.addCleanup(self.directory.cleanup)
        self.runtime = object.__new__(self.b.NativeRuntime)
        self.runtime.home = Path(self.directory.name)
        self.runtime.require_history_source = Mock()
        self.runtime.require_recovery_source = Mock()
        self.path = self.runtime.home / "state.db"
        self.path.write_bytes(b"inert fixture only")
        self.path.chmod(0o600)
        self.principal = f"uid:{os.getuid()}"
        self.origin = {"platform": "local", "chat_id": SID, "user_id": self.principal, "chat_type": "dm"}
        self.route = "agent:main:local:dm:" + SID
        self.receipt = {"profile_id": str(self.runtime.home), "principal_id": self.principal,
            "request_id": REQUEST, "session_id": SID, "route": self.route,
            "entry": {"session_id": TIP, "session_key": self.route, "origin": self.origin},
            "lineage": [SID, TIP]}
        self.rows = {
            SID: {"id": SID, "runtime_generation": 7},
            TIP: {"id": TIP, "session_key": self.route, "chat_id": SID, "user_id": self.principal,
                  "origin_json": json.dumps(self.origin), "runtime_generation": 1,
                  "title": "Original OS conversation", "model": "configured-only", "source": "tool"},
        }
        self.messages = [{"role": "system", "content": "private system"},
                         {"role": "user", "content": "  Original\n 中文\t"},
                         {"role": "assistant", "content": "Original answer"},
                         {"role": "tool", "content": "private trace"}]
        self.pending = []
        self.candidates = [{"id": TIP}]
        self.db = SimpleNamespace(_read_ctx=self.read_context, get_session=lambda sid: self.rows.get(sid),
            get_messages=Mock(side_effect=self.message_page),
            get_resume_message_count=Mock(side_effect=lambda sid: len(self.messages)),
            list_sessions_rich=Mock(side_effect=lambda **kw: self.candidates[kw["offset"]:kw["offset"] + kw["limit"]]),
            close=Mock())
        self.session_db = Mock(return_value=self.db)
        self.receipt_reader = Mock(side_effect=self.read_receipt)
        self.lineage = Mock(return_value=TIP)
        modules = {
            "gateway.config": SimpleNamespace(Platform=SimpleNamespace(LOCAL="local")),
            "gateway.owner_identity": SimpleNamespace(same_owner=lambda left, right: left == right),
            "gateway.session": SimpleNamespace(SessionSource=Source, build_session_key=lambda src: "agent:main:local:dm:" + src.values["chat_id"]),
            "hermes_state": SimpleNamespace(SessionDB=self.session_db),
            "hermes_state_keys": SimpleNamespace(local_identity=lambda home, principal, request: SID if request == REQUEST else "other"),
            "hermes_state_local": SimpleNamespace(local_lineage_owner=lambda conn, sid: SID if sid in {SID, TIP} else sid,
                                                  local_receipt=self.receipt_reader),
            "hermes_state_local_lineage": SimpleNamespace(validate_local_lineage=self.lineage),
            "hermes_state_runtime": SimpleNamespace(RuntimeStoreError=LookupError,
                list_session_admissions=Mock(side_effect=lambda db, session_id: self.pending)),
        }
        self.patch = patch.dict("sys.modules", modules)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    @contextmanager
    def read_context(self):
        yield object()

    def read_receipt(self, db, sid):
        if sid != SID or self.receipt is None:
            raise LookupError("missing receipt")
        return copy.deepcopy(self.receipt)

    def message_page(self, sid, **options):
        end = len(self.messages) - options["offset"]
        start = max(0, end - options["limit"])
        return self.messages[start:max(0, end)]

    def test_tool_source_history_uses_readonly_owner_and_filters_foreign_rows(self):
        self.candidates.insert(0, {"id": "foreign-private-title"})
        result = self.runtime.list_history()
        self.assertEqual(result, {"sessions": [{"id": SID, "title": "Original OS conversation",
                                                "running": None, "messageCount": 4}]})
        self.assertNotIn("foreign", str(result))
        self.session_db.assert_called_once_with(self.path, read_only=True)
        options = self.db.list_sessions_rich.call_args.kwargs
        self.assertIn("tool", options["sources"])
        self.assertEqual(options["limit"], 200)
        self.assertNotIn("include_hidden", options)
        self.db.close.assert_called_once_with()

    def test_history_preserves_original_answer_and_declares_unobserved_live_state(self):
        self.pending = [{"admission_id": "original-admission", "status": "unknown"}]
        result = self.runtime.read_history(TIP)["session"]
        self.assertEqual(result["messages"], [
            {"role": "user", "text": "  Original\n 中文\t"},
            {"role": "assistant", "text": "Original answer"}])
        self.assertEqual((result["id"], result["storedId"], result["executionGeneration"]), (SID, TIP, 7))
        self.assertTrue(result["sendCheckRequired"])
        self.assertFalse(result["canSend"])
        self.assertEqual(result["toolAccess"], "UNQUALIFIED")
        self.assertIsNone(result["running"])
        self.assertIsNone(result["promptsPending"])
        self.assertEqual(result["pending"], [{"id": "original-admission", "status": "unknown"}])
        self.assertNotIn("private", str(result))
        self.db.get_messages.assert_called_once_with(TIP, include_compacted=True, include_ancestors=True,
                                                     limit=1000, offset=0, latest=True)
        self.assertFalse(result["historyTruncated"])
        self.assertGreaterEqual(self.lineage.call_count, 2)

    def test_foreign_or_damaged_receipt_and_target_never_expose_messages(self):
        baseline = copy.deepcopy(self.receipt)
        target = copy.deepcopy(self.rows[TIP])
        changes = [
            lambda: self.receipt.update(profile_id="/another-profile"),
            lambda: self.receipt.update(principal_id="uid:another"),
            lambda: self.receipt.update(session_id="another"),
            lambda: self.receipt.update(route="another-route"),
            lambda: self.receipt["entry"].update(session_key="another-route"),
            lambda: self.receipt["entry"]["origin"].update(chat_id="another"),
            lambda: self.rows[TIP].update(user_id="uid:another"),
            lambda: self.rows[TIP].update(origin_json='{"platform":"foreign"}'),
        ]
        for change in changes:
            self.receipt = copy.deepcopy(baseline)
            self.rows[TIP] = copy.deepcopy(target)
            self.db.get_messages.reset_mock()
            change()
            with self.assertRaisesRegex(self.b.BridgeRefusal, "NATIVE_HISTORY_UNAVAILABLE"):
                self.runtime.read_history(TIP)
            self.db.get_messages.assert_not_called()

    def test_recover_create_requires_committed_exact_original_receipt(self):
        self.assertEqual(self.runtime.create_identity(REQUEST), {"session_id": SID})
        self.assertEqual(self.runtime.resolve_original("recover_create", {"request_id": REQUEST}), {"session_id": SID})
        self.receipt = None
        # Expected identity remains usable for a NEW creation. It is not success.
        self.assertEqual(self.runtime.create_identity(REQUEST), {"session_id": SID})
        with self.assertRaisesRegex(self.b.BridgeRefusal, "NATIVE_HISTORY_UNAVAILABLE"):
            self.runtime.resolve_original("recover_create", {"request_id": REQUEST})
        self.db.get_messages.assert_not_called()

    def test_bounded_visible_history_retains_latest_text_and_reports_truncation(self):
        self.messages = [item for i in range(240) for item in (
            {"role": "assistant", "content": f"answer-{i}"}, {"role": "tool", "content": "private"})]
        result = self.runtime.read_history(SID)["session"]
        self.assertEqual(len(result["messages"]), 100)
        self.assertEqual(result["messages"][0]["text"], "answer-140")
        self.assertEqual(result["messages"][-1]["text"], "answer-239")
        self.assertTrue(result["historyTruncated"])
        self.assertEqual(self.db.get_messages.call_count, 1)
        self.assertNotIn("private", str(result))
        self.messages = [{"role": "tool", "content": "private"}] * 2000
        self.db.get_messages.reset_mock()
        result = self.runtime.read_history(SID)["session"]
        self.assertEqual(result["messages"], [])
        self.assertTrue(result["historyTruncated"])
        self.assertEqual(self.db.get_messages.call_count, 1)

    def test_concurrent_append_does_not_overlap_visible_history(self):
        self.messages = [item for i in range(120) for item in (
            {"role": "assistant", "content": f"answer-{i}"},
            *({"role": "tool", "content": "private trace"} for _ in range(4)))]
        expected = [{"role": "assistant", "text": f"answer-{i}"} for i in range(20, 120)]

        def append_after_snapshot(sid, **options):
            page = self.message_page(sid, **options)
            self.messages.extend({"role": "assistant", "content": "later append"} for _ in range(35))
            return page

        self.db.get_messages.side_effect = append_after_snapshot
        result = self.runtime.read_history(SID)["session"]
        self.assertEqual(result["messages"], expected)
        self.assertTrue(result["historyTruncated"])
        self.assertNotIn("later append", str(result["messages"]))

    def test_storage_identity_and_mode_fail_before_exposing_history(self):
        self.path.chmod(0o622)
        with self.assertRaisesRegex(self.b.BridgeRefusal, "NATIVE_RECOVERY_UNAVAILABLE"):
            self.runtime.read_history(SID)
        self.session_db.assert_not_called()

    def test_read_and_create_recovery_never_connect_or_attach(self):
        async def identify():
            return {"ok": True, "protocol": 1, "result": {"kind": "hermes-gateway", "runtime_protocol": 1,
                "state": "ready", "hermes_home": str(self.runtime.home), "instance_id": "original-owner",
                "authority_epoch": 2, "api_origin": "http://127.0.0.1:45678", "code_sha": "a" * 40,
                "code_version": "0.23.0", "capabilities": ["session-authority-v1", "durable-admission-v1", "event-replay-v1"]}}
        self.runtime.identify = identify
        self.runtime.connect = Mock(side_effect=AssertionError("No lifecycle connection during history"))
        self.runtime.readonly_capacity_qualified = lambda: False
        for request in ({"operation": "list"}, {"operation": "read", "sessionId": SID},
                        {"operation": "recover_create", "requestId": REQUEST}):
            result = asyncio.run(self.b.execute_request(request, self.runtime))
            self.assertEqual(result["state"], "OPENED" if request["operation"] == "recover_create" else "READY")
        self.runtime.connect.assert_not_called()
        self.receipt = None
        result = asyncio.run(self.b.execute_request({"operation": "recover_create", "requestId": REQUEST}, self.runtime))
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertFalse(result["retryAllowed"])
        self.runtime.connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
