"""Synthetic host-affinity/target-read regressions; no live Paper or fleet calls."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "integrations/paper_desktop"
A = "01" + "A" * 24
B = "01" + "B" * 24


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExecutionBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.b = load("binding_bridge_fixture", ROOT / "bridge.py")
        with patch.dict(sys.modules, {"bridge": self.b}):
            self.p = load("binding_prepare_fixture", ROOT / "prepare.py")
        self.scope = {"schema": "mastermind.paper_execution_binding.v1",
                      "host_ref": "host-" + "a" * 64,
                      "service_ref": "b" * 64, "runtime_revision": "c" * 40,
                      "bridge_sha256": "d" * 64}
        self.docs = {A: {"fileId": A, "fileName": "Active", "artboards": []},
                     B: {"fileId": B, "fileName": "Target", "artboards": []}}
        self.calls = []
        owner = self

        class Client:
            server = {"name": "fixture", "version": "1"}
            error = False
            def initialize(self):
                return {}
            def catalog(self):
                return {n: {"name": n, "inputSchema": {"type": "object"}}
                        for n in owner.b.READ_TOOLS | owner.b.EDIT_TOOLS}
            def call(self, name, arguments):
                owner.calls.append((name, copy.deepcopy(arguments)))
                if name == "get_basic_info":
                    return {"structuredContent": copy.deepcopy(owner.docs[arguments.get("fileId", A)])}
                if name in owner.b.EDIT_TOOLS and self.error:
                    raise TimeoutError()
                return {"content": [{"type": "text", "text": "ok"}]}
        self.client = Client()

    def tearDown(self):
        self.tmp.cleanup()

    def execute(self, action, **kwargs):
        return self.b.execute(action, client=self.client, lock_root=self.root,
                              _server_pin=None, _catalog_pin=None, **kwargs)

    def snapshot(self, scope, file_id=B):
        return self.b.snapshot(self.client, file_id, execution_binding=scope)

    def edit(self, guard, scope):
        return self.execute("edit", tool="set_text_content", arguments={"fileId": B},
                            expected_snapshot=guard, operation_id="bound-edit-1",
                            allow_write=True, execution_binding=scope)

    def test_background_read_uses_explicit_target_not_active_file(self):
        result = self.execute("read", tool="get_jsx", arguments={"fileId": B},
                              expected_snapshot=self.b.digest(self.docs[B]))
        self.assertEqual(result["state"], "OBSERVED")
        self.assertEqual(self.calls, [("get_basic_info", {"fileId": B}),
                                     ("get_jsx", {"fileId": B})])

    def test_active_snapshot_cannot_authorize_background_read(self):
        with self.assertRaisesRegex(self.b.Refusal, "DOCUMENT_CHANGED"):
            self.execute("read", tool="get_jsx", arguments={"fileId": B},
                         expected_snapshot=self.b.digest(self.docs[A]))
        self.assertFalse(any(name == "get_jsx" for name, _ in self.calls))

    def test_legacy_snapshot_hash_is_unchanged(self):
        self.assertEqual(self.b.snapshot(self.client, B)["snapshot_sha256"],
                         self.b.digest(self.docs[B]))

    def test_bound_snapshot_remains_hex64_and_has_provenance(self):
        result = self.snapshot(self.scope)
        self.assertRegex(result["snapshot_sha256"], "^[0-9a-f]{64}$")
        self.assertNotEqual(result["snapshot_sha256"], self.b.digest(self.docs[B]))
        self.assertEqual(result["execution_binding"], self.scope)

    def test_other_host_same_document_snapshot_refused_before_edit(self):
        guard = self.snapshot(self.scope)["snapshot_sha256"]
        other = dict(self.scope, host_ref="host-" + "e" * 64)
        with self.assertRaisesRegex(self.b.Refusal, "DOCUMENT_CHANGED"):
            self.edit(guard, other)
        self.assertFalse(any(name == "set_text_content" for name, _ in self.calls))

    def test_changed_service_or_runtime_refused_before_edit(self):
        guard = self.snapshot(self.scope)["snapshot_sha256"]
        for key, value in (("service_ref", "e" * 64), ("runtime_revision", "e" * 40),
                           ("bridge_sha256", "e" * 64)):
            with self.subTest(key=key), self.assertRaisesRegex(self.b.Refusal, "DOCUMENT_CHANGED"):
                self.edit(guard, dict(self.scope, **{key: value}))
        self.assertFalse(any(name == "set_text_content" for name, _ in self.calls))

    def test_legacy_guard_is_not_accepted_by_bound_runtime(self):
        with self.assertRaisesRegex(self.b.Refusal, "DOCUMENT_CHANGED"):
            self.edit(self.b.digest(self.docs[B]), self.scope)
        self.assertFalse(any(name == "set_text_content" for name, _ in self.calls))

    def test_bound_guard_is_not_accepted_by_legacy_runtime(self):
        guard = self.snapshot(self.scope)["snapshot_sha256"]
        with self.assertRaisesRegex(self.b.Refusal, "DOCUMENT_CHANGED"):
            self.edit(guard, None)
        self.assertFalse(any(name == "set_text_content" for name, _ in self.calls))

    def test_same_binding_edit_preserves_exact_target_and_scope(self):
        guard = self.snapshot(self.scope)["snapshot_sha256"]
        result = self.edit(guard, self.scope)
        self.assertEqual(result["state"], "APPLIED_RESPONSE_OBSERVED")
        self.assertEqual(result["before"]["identity"]["id"], B)
        self.assertEqual(result["after"]["execution_binding"], self.scope)
        self.assertEqual(sum(name == "set_text_content" for name, _ in self.calls), 1)

    def test_unknown_effect_keeps_original_scope_and_is_not_replayed(self):
        guard = self.snapshot(self.scope)["snapshot_sha256"]
        self.client.error = True
        result = self.edit(guard, self.scope)
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertEqual(result["before"]["execution_binding"], self.scope)
        self.assertFalse(result["retry_allowed"])
        self.assertEqual(sum(name == "set_text_content" for name, _ in self.calls), 1)

    def test_invalid_scope_refused_before_paper_calls(self):
        bad = [True, {}, dict(self.scope, host_ref="m2studio"),
               dict(self.scope, arbitrary_url="https://invalid.example"),
               dict(self.scope, service_ref="invalid")]
        for scope in bad:
            with self.subTest(scope=scope), self.assertRaisesRegex(self.b.Refusal, "EXECUTION_BINDING_INVALID"):
                self.execute("status", execution_binding=scope)
        self.assertEqual(self.calls, [])

    def test_prepare_then_background_read_and_edit_share_binding(self):
        guard = self.snapshot(self.scope, B)["snapshot_sha256"]
        prepared = self.p.prepare_document(B, guard, "bound-prepare-1", allow_prepare=True,
                     client=self.client, lock_root=self.root, _server_pin=None,
                     _catalog_pin=None, execution_binding=self.scope)
        self.assertFalse(prepared["open_attempted"])
        self.assertIsNone(prepared["target_active"])
        self.assertFalse(prepared["active_context_required"])
        target_guard = prepared["snapshot_sha256"]
        read = self.execute("read", tool="get_jsx", arguments={"fileId": B},
                            expected_snapshot=target_guard, execution_binding=self.scope)
        self.assertEqual(read["state"], "OBSERVED")
        self.assertEqual(self.edit(target_guard, self.scope)["state"], "APPLIED_RESPONSE_OBSERVED")
        self.assertFalse(any(name == "open_file" for name, _ in self.calls))


if __name__ == "__main__":
    unittest.main()
