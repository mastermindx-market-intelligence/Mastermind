"""Focused, inert regression coverage for slot canonical-source diagnostics."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / "ops/native_fabric/quota_continuity/source"
_ORIGINAL_SYS_PATH = list(sys.path)
try:
    if str(SOURCE) not in sys.path:
        sys.path.insert(0, str(SOURCE))
    SPEC = importlib.util.spec_from_file_location("slot_source_diagnostic_test", SOURCE / "slot.py")
    slot = importlib.util.module_from_spec(SPEC)
    sys.modules[SPEC.name] = slot
    SPEC.loader.exec_module(slot)
finally:
    sys.path[:] = _ORIGINAL_SYS_PATH


class CanonicalSourceDiagnostics(unittest.TestCase):
    def setUp(self):
        slot._reset_canonical_source_subreason()

    def assert_subreason(self, expected):
        self.assertEqual(slot._canonical_source_subreason, expected)

    def test_closed_subreason_vocabulary_is_exact(self):
        self.assertEqual({item.value for item in slot.CanonicalSourceSubreason}, {
            "unsupported_pool_binding", "legacy_checkout_absent", "legacy_checkout_git_failure",
            "legacy_checkout_wrong_pin", "legacy_source_unreadable", "object_root_invalid",
            "object_root_missing", "object_root_config_or_promisor", "object_root_read_failure",
            "pinned_commit_unavailable", "blob_missing", "blob_too_large", "blob_invalid_utf8",
            "binding_json_malformed", "binding_document_malformed",
            "binding_activation_gates_invalid", "binding_id_inconsistent",
        })

    def test_legacy_checkout_observations_are_closed_and_reset(self):
        with mock.patch.object(slot.os.path, "exists", return_value=False):
            self.assertFalse(slot._minimax_commit_matches())
        self.assert_subreason(slot.CanonicalSourceSubreason.LEGACY_CHECKOUT_ABSENT)

        slot._record_canonical_source_subreason(slot.CanonicalSourceSubreason.BLOB_MISSING)
        with mock.patch.object(slot, "_minimax_commit_matches", return_value=False):
            self.assertEqual(slot._pool_refusal_reason("minimax"), "canonical_source_unreadable")
        # The public evaluation reset removes a prior invocation's detail.
        self.assertIsNone(slot._canonical_source_subreason)

    def test_every_declared_subreason_has_a_reachable_observation_case(self):
        # Remaining one-step cases complement the detailed path tests below.
        with mock.patch.object(slot, "_minimax_file", return_value=None), \
             mock.patch.dict(slot.os.environ, {}, clear=True):
            self.assertIsNone(slot._minimax_canonical_source(slot.MINIMAX_BINDING_PATH))
        self.assert_subreason(slot.CanonicalSourceSubreason.LEGACY_SOURCE_UNREADABLE)

        slot._reset_canonical_source_subreason()
        with mock.patch.object(slot.subprocess, "run", side_effect=OSError("fixture")), \
             mock.patch.dict(slot.os.environ, {"MINIMAX_GIT_OBJECT_ROOT": "/fixture"}, clear=False), \
             mock.patch.object(slot.os.path, "isdir", return_value=True):
            self.assertIsNone(slot._minimax_canonical_source(slot.MINIMAX_BINDING_PATH))
        self.assert_subreason(slot.CanonicalSourceSubreason.OBJECT_ROOT_READ_FAILURE)

        slot._reset_canonical_source_subreason()
        self.assertEqual(slot._pool_refusal_reason("minimax-unknown"), "canonical_source_unreadable")
        self.assert_subreason(slot.CanonicalSourceSubreason.UNSUPPORTED_POOL_BINDING)

    def test_legacy_wrong_pin_and_git_failure_are_distinct(self):
        with mock.patch.object(slot.os.path, "exists", return_value=True), \
             mock.patch.object(slot.subprocess, "run", return_value=type("P", (), {
                 "returncode": 0, "stdout": "not-the-pin\n"})()):
            self.assertFalse(slot._minimax_commit_matches())
        self.assert_subreason(slot.CanonicalSourceSubreason.LEGACY_CHECKOUT_WRONG_PIN)

        slot._reset_canonical_source_subreason()
        with mock.patch.object(slot.os.path, "exists", return_value=True), \
             mock.patch.object(slot.subprocess, "run", side_effect=OSError("fixture")):
            self.assertFalse(slot._minimax_commit_matches())
        self.assert_subreason(slot.CanonicalSourceSubreason.LEGACY_CHECKOUT_GIT_FAILURE)

    def test_object_source_failures_use_only_the_existing_git_calls(self):
        result = lambda rc=0, out=b"": type("P", (), {"returncode": rc, "stdout": out})()
        # config, commit kind, then the existing blob read: no diagnostic probe.
        calls = [result(), result(0, b"commit\n"), result(1)]
        with mock.patch.dict(slot.os.environ, {"MINIMAX_GIT_OBJECT_ROOT": "/fixture"}, clear=False), \
             mock.patch.object(slot.os.path, "isdir", return_value=True), \
             mock.patch.object(slot.subprocess, "run", side_effect=calls) as run:
            self.assertIsNone(slot._minimax_canonical_source(slot.MINIMAX_BINDING_PATH))
        self.assertEqual(run.call_count, 3)
        self.assert_subreason(slot.CanonicalSourceSubreason.BLOB_MISSING)

    def test_canonical_source_has_exact_existing_operation_traces(self):
        result = lambda rc=0, out=b"": type("P", (), {"returncode": rc, "stdout": out})()
        for responses, expected_ops in (
            ([result(), result(0, b"commit\n"), result(0, b"text")], ("config", "cat-file", "cat-file")),
            ([result(), result(0, b"commit\n"), result(1)], ("config", "cat-file", "cat-file")),
            ([result(), result(0, b"tree\n")], ("config", "cat-file")),
        ):
            with self.subTest(responses=len(responses)), \
                 mock.patch.dict(slot.os.environ, {"MINIMAX_GIT_OBJECT_ROOT": "/fixture"}, clear=False), \
                 mock.patch.object(slot.os.path, "isdir", return_value=True), \
                 mock.patch.object(slot.subprocess, "run", side_effect=responses) as run:
                slot._reset_canonical_source_subreason()
                slot._minimax_canonical_source(slot.MINIMAX_BINDING_PATH)
            self.assertEqual(run.call_count, len(expected_ops))
            self.assertEqual(tuple(call.args[0][4] for call in run.call_args_list), expected_ops)

    def test_object_root_and_blob_subtypes_are_closed(self):
        with mock.patch.dict(slot.os.environ, {"MINIMAX_GIT_OBJECT_ROOT": "relative"}, clear=False):
            self.assertIsNone(slot._minimax_canonical_source(slot.MINIMAX_BINDING_PATH))
        self.assert_subreason(slot.CanonicalSourceSubreason.OBJECT_ROOT_INVALID)

        slot._reset_canonical_source_subreason()
        result = lambda rc=0, out=b"": type("P", (), {"returncode": rc, "stdout": out})()
        with mock.patch.dict(slot.os.environ, {"MINIMAX_GIT_OBJECT_ROOT": "/fixture"}, clear=False), \
             mock.patch.object(slot.os.path, "isdir", return_value=True), \
             mock.patch.object(slot.subprocess, "run", side_effect=[result(), result(0, b"commit\n"), result(0, b"x" * (4 * 1024 * 1024 + 1))]):
            self.assertIsNone(slot._minimax_canonical_source(slot.MINIMAX_BINDING_PATH))
        self.assert_subreason(slot.CanonicalSourceSubreason.BLOB_TOO_LARGE)

    def test_remaining_object_root_commit_and_utf8_subtypes(self):
        with mock.patch.dict(slot.os.environ, {"MINIMAX_GIT_OBJECT_ROOT": "/missing"}, clear=False), \
             mock.patch.object(slot.os.path, "isdir", return_value=False):
            self.assertIsNone(slot._minimax_canonical_source(slot.MINIMAX_BINDING_PATH))
        self.assert_subreason(slot.CanonicalSourceSubreason.OBJECT_ROOT_MISSING)

        slot._reset_canonical_source_subreason()
        result = lambda rc=0, out=b"": type("P", (), {"returncode": rc, "stdout": out})()
        with mock.patch.dict(slot.os.environ, {"MINIMAX_GIT_OBJECT_ROOT": "/fixture"}, clear=False), \
             mock.patch.object(slot.os.path, "isdir", return_value=True), \
             mock.patch.object(slot.subprocess, "run", side_effect=[result(0, b"promisor\n")]):
            self.assertIsNone(slot._minimax_canonical_source(slot.MINIMAX_BINDING_PATH))
        self.assert_subreason(slot.CanonicalSourceSubreason.OBJECT_ROOT_CONFIG_OR_PROMISOR)

        slot._reset_canonical_source_subreason()
        with mock.patch.dict(slot.os.environ, {"MINIMAX_GIT_OBJECT_ROOT": "/fixture"}, clear=False), \
             mock.patch.object(slot.os.path, "isdir", return_value=True), \
             mock.patch.object(slot.subprocess, "run", side_effect=[result(), result(0, b"tree\n")]):
            self.assertIsNone(slot._minimax_canonical_source(slot.MINIMAX_BINDING_PATH))
        self.assert_subreason(slot.CanonicalSourceSubreason.PINNED_COMMIT_UNAVAILABLE)

        slot._reset_canonical_source_subreason()
        with mock.patch.dict(slot.os.environ, {"MINIMAX_GIT_OBJECT_ROOT": "/fixture"}, clear=False), \
             mock.patch.object(slot.os.path, "isdir", return_value=True), \
             mock.patch.object(slot.subprocess, "run", side_effect=[result(), result(0, b"commit\n"), result(0, b"\xff")]):
            self.assertIsNone(slot._minimax_canonical_source(slot.MINIMAX_BINDING_PATH))
        self.assert_subreason(slot.CanonicalSourceSubreason.BLOB_INVALID_UTF8)

    def test_binding_parse_gate_and_id_inconsistency_are_observational(self):
        with mock.patch.object(slot, "_minimax_canonical_source", return_value="{"):
            self.assertIsNone(slot._canonical_minimax_binding("minimax"))
        self.assert_subreason(slot.CanonicalSourceSubreason.BINDING_JSON_MALFORMED)

        slot._reset_canonical_source_subreason()
        with mock.patch.object(slot, "_minimax_canonical_source", return_value="[]"):
            self.assertIsNone(slot._canonical_minimax_binding("minimax"))
        self.assert_subreason(slot.CanonicalSourceSubreason.BINDING_DOCUMENT_MALFORMED)

        slot._reset_canonical_source_subreason()
        bad_gates = '{"bindings":{"minimax-token-plan.claude-code-anthropic":{"activation_gates":[]}}}'
        with mock.patch.object(slot, "_minimax_canonical_source", return_value=bad_gates):
            self.assertIsNone(slot._canonical_minimax_binding("minimax"))
        self.assert_subreason(slot.CanonicalSourceSubreason.BINDING_ACTIVATION_GATES_INVALID)

        with mock.patch.object(slot, "_minimax_commit_matches", return_value=True), \
             mock.patch.object(slot, "_minimax_canonical_source", return_value="source"), \
             mock.patch.object(slot, "_reviewed_minimax_realm", return_value=True), \
             mock.patch.object(slot, "_canonical_minimax_binding", return_value=("wrong.id", {})):
            self.assertEqual(slot._pool_refusal_reason("minimax"), "canonical_source_unreadable")
        self.assert_subreason(slot.CanonicalSourceSubreason.BINDING_ID_INCONSISTENT)

    def test_generic_line_and_rc_are_preserved_with_additive_safe_detail(self):
        stderr = io.StringIO()
        with mock.patch.object(slot, "_child_runtime_limit"), \
             mock.patch.object(slot, "_local_host_admission_refusal", return_value=None), \
             mock.patch.object(slot, "_pool_cap", return_value=0), \
             mock.patch.object(slot, "_pool_refusal_reason", return_value="canonical_source_unreadable"), \
             mock.patch.object(slot, "_pool_ledger_refusal"), \
             mock.patch.object(slot, "_canonical_source_subreason", slot.CanonicalSourceSubreason.BLOB_MISSING), \
             mock.patch.dict(slot.os.environ, {"LANE_LEASED": "1"}, clear=False), \
             contextlib.redirect_stderr(stderr):
            self.assertEqual(slot.main(["minimax", "--", "true"]), 78)
        lines = stderr.getvalue().splitlines()
        self.assertEqual(lines[0], "slot.py: pool=minimax admission_denied reason=canonical_source_unreadable")
        self.assertEqual(lines[1], "slot.py: pool=minimax canonical_source_subreason=blob_missing")

        stderr = io.StringIO()
        with mock.patch.object(slot, "_child_runtime_limit"), \
             mock.patch.object(slot, "_local_host_admission_refusal", return_value=None), \
             mock.patch.object(slot, "_pool_cap", return_value=0), \
             mock.patch.object(slot, "_pool_refusal_reason", return_value="realm_unreviewed"), \
             mock.patch.object(slot, "_pool_ledger_refusal"), \
             mock.patch.object(slot, "_canonical_source_subreason", slot.CanonicalSourceSubreason.BLOB_MISSING), \
             mock.patch.dict(slot.os.environ, {"LANE_LEASED": "1"}, clear=False), \
             contextlib.redirect_stderr(stderr):
            self.assertEqual(slot.main(["minimax", "--", "true"]), 78)
        self.assertEqual(stderr.getvalue().splitlines(), [
            "slot.py: pool=minimax admission_denied reason=realm_unreviewed"
        ])

    def test_valid_source_stops_before_activation(self):
        binding = {
            "bindings": {"minimax-token-plan.claude-code-anthropic": {
                "activation_gates": list(slot.MINIMAX_ACTIVATION_GATES),
                "harness_id": "claude-code", "implementation_state": "BUILT_NOT_PROVEN",
            }}
        }
        def source(path):
            return '{\nREVIEWED_CODEX_PROVIDER_REALMS = {"minimax-token-plan": True}\n}\n' if path == slot.REVIEWED_REALM_PATH else __import__("json").dumps(binding)
        class Stop(Exception):
            pass
        with mock.patch.object(slot, "_minimax_commit_matches", return_value=True), \
             mock.patch.object(slot, "_minimax_canonical_source", side_effect=source), \
             mock.patch.object(slot, "_minimax_activation_fact", side_effect=Stop):
            with self.assertRaises(Stop):
                slot._pool_refusal_reason("minimax")


if __name__ == "__main__":
    unittest.main()
