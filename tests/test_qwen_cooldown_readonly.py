"""Regression for non-mutating, fail-closed local Token Plan cooldown observation.

The candidate's real function is loaded, not a reimplementation. Fixture paths
are private and no real credential, slot, provider or broker is touched.
"""
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import time
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "ops/native_fabric/quota_continuity/candidate/bailian_keys.py"


def load_candidate():
    spec = importlib.util.spec_from_file_location("bailian_keys_test_readonly", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QwenCooldownReadOnly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "slots"
        self.root.mkdir(mode=0o700)
        self.keys = load_candidate()
        self.root_patch = patch.object(self.keys, "SLOTS_ROOT", str(self.root))
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.path = self.root / "Ryan.cooldown"

    def write(self, content, *, mode=0o600):
        self.path.write_text(content)
        self.path.chmod(mode)

    def rank(self):
        # Selection must never delete/replace files or create state.
        with patch.object(self.keys.os, "unlink", side_effect=AssertionError("mutation!")):
            return self.keys.cooldown_rank_readonly("Ryan")

    def test_missing_file_is_healthy_with_verified_directory(self):
        self.assertEqual(self.rank(), 0)
        self.assertEqual(list(self.root.glob("*.cooldown")), [])

    def test_missing_cooldown_directory_is_unknown(self):
        self.root.rmdir()
        self.assertEqual(self.rank(), 1)

    def test_fresh_429_is_soft_rank_two(self):
        self.write(f"{int(time.time())+120} http_429\n")
        old = self.path.read_bytes()
        self.assertEqual(self.rank(), 2)
        self.assertEqual(self.path.read_bytes(), old)

    def test_known_hard_denials_get_rank_three(self):
        for reason in ("access_denied", "invalid_api_key", "quota_or_insufficient"):
            with self.subTest(reason=reason):
                self.write(f"{int(time.time())+120} {reason}\n")
                self.assertEqual(self.rank(), 3)

    def test_expired_record_does_not_get_unlinked(self):
        self.write("1 http_429\n")
        orig = os.stat(self.path)
        self.assertEqual(self.rank(), 0)
        self.assertTrue(self.path.is_file())
        self.assertEqual(os.stat(self.path).st_ino, orig.st_ino)

    def test_malformed_and_empty_records_are_unknown(self):
        for value in ("", " ", "notatime http_429\n", "NaN http_429\n",
                      "Infinity http_429\n", f"{int(time.time())+120}\n",
                      "1e999 http_429\n", " " * 300):
            with self.subTest(value=value[:20]):
                self.write(value)
                self.assertEqual(self.rank(), 1)

    def test_symlink_to_valid_cooldown_is_unknown(self):
        other = self.root / "other"
        other.write_text(f"{int(time.time())+120} http_429\n")
        self.path.symlink_to(other)
        self.assertEqual(self.rank(), 1)

    def test_group_writable_cooldown_unknown(self):
        self.write(f"{int(time.time())+120} http_429\n", mode=0o660)
        self.assertEqual(self.rank(), 1)

    def test_group_writable_directory_unknown(self):
        self.root.chmod(0o770)
        self.assertEqual(self.rank(), 1)

    def test_oversized_cooldown_unknown(self):
        self.write((f"{int(time.time())+120} " + "Z" * 300))
        self.assertEqual(self.rank(), 1)

    def test_os_open_permission_failure_unknown_not_healthy(self):
        original = self.keys.os.open
        def refused(path, flags, *args, **kwargs):
            if str(path) == self.path.name and kwargs.get("dir_fd") is not None:
                raise PermissionError("fixture denied")
            return original(path, flags, *args, **kwargs)
        self.write(f"{int(time.time())+120} http_429\n")
        with patch.object(self.keys.os, "open", side_effect=refused):
            self.assertEqual(self.rank(), 1)

    def test_unrelated_oserror_unknown_not_healthy(self):
        self.write(f"{int(time.time())+120} http_429\n")
        with patch.object(self.keys.os, "read", side_effect=OSError("fixture raced")):
            self.assertEqual(self.rank(), 1)


    def broker_pick(self, preferred=None):
        """Exercise actual candidate Broker method with the real read-only accessor."""
        import sqlite3
        import sys
        import types

        broker_tests = SOURCE.parent.parent / "tests/test_qwen_429_account_priority.py"
        spec = importlib.util.spec_from_file_location("qwen_broker_selection_fixture", broker_tests)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        quota = types.ModuleType("quota_circuit")
        quota.admission_room = lambda *args: True
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("CREATE TABLE leases (pool TEXT, account TEXT, granted_at REAL)")
            conn.executemany("INSERT INTO leases VALUES (?,?,?)", [
                ("bailian", "Ryan", 1), ("bailian", "Chris", 2), ("bailian", "Kris", 3),
            ])
            with patch.dict(sys.modules, {
                    "bailian_keys": self.keys, "quota_circuit": quota}):
                return helper.selected_method()(helper.BrokerStub(), conn, "bailian", preferred)
        finally:
            conn.close()

    def test_broker_real_accessor_never_prioritizes_corrupt_cooldown(self):
        self.write("corrupt not_a_reason\n")
        self.assertEqual(self.broker_pick(), "Chris")

    def test_broker_real_accessor_excludes_hard_denial(self):
        self.write(f"{int(time.time())+120} access_denied\n")
        self.assertEqual(self.broker_pick(), "Chris")
        self.assertIsNone(self.broker_pick(preferred="Ryan"))

    def test_broker_real_accessor_falls_back_to_soft_429(self):
        for name in ("Ryan", "Chris", "Kris"):
            (self.root / (name + ".cooldown")).write_text(
                f"{int(time.time())+120} http_429\n")
        self.assertEqual(self.broker_pick(), "Ryan")

    def test_broker_real_accessor_does_not_delete_expired_evidence(self):
        self.write("1 http_429\n")
        (self.root / "Chris.cooldown").write_text(
            f"{int(time.time())+120} http_429\n")
        self.assertEqual(self.broker_pick(), "Ryan")
        self.assertTrue(self.path.is_file())


    def broker_cap(self):
        """Execute the actual Broker._bailian_effective_cap, not a copied formula."""
        import ast
        import sys
        import types
        from typing import Optional
        broker_source = SOURCE.parent / "lease_broker.py"
        tree = ast.parse(broker_source.read_text(), filename=str(broker_source))
        cls = next(x for x in tree.body if isinstance(x, ast.ClassDef)
                   and x.name == "Broker")
        fn = next(x for x in cls.body if isinstance(x, ast.FunctionDef)
                  and x.name == "_bailian_effective_cap")
        scope = {"Optional": Optional, "HERE": str(SOURCE.parent), "sys": sys}
        exec(compile(ast.fix_missing_locations(
            ast.Module(body=[fn], type_ignores=[])), str(broker_source), "exec"), scope)
        with (
            patch.dict(sys.modules, {"bailian_keys": self.keys}),
            patch.object(sys, "path", [str(SOURCE.parent), *sys.path]),
            patch.object(self.keys, "current_per_key_cap", return_value=7),
            patch.object(self.keys, "load_policy", return_value={"soft_cap_on_429": True}),
            patch.object(self.keys, "_read_soft_cap", return_value=5),
            patch.object(self.keys.os, "unlink") as deletion,
        ):
            cap = scope["_bailian_effective_cap"](
                types.SimpleNamespace(external_gates=True), "Ryan", 7
            )
            deletion.assert_not_called()
            return cap

    def test_broker_actual_capacity_path_does_not_unlink_expired(self):
        self.write("1 http_429\n")
        self.assertEqual(self.broker_cap(), 7)
        self.assertTrue(self.path.is_file())

    def test_broker_actual_capacity_soft_429_remains_reduced(self):
        self.write(f"{int(time.time())+120} http_429\n")
        self.assertEqual(self.broker_cap(), 4)

    def test_broker_actual_capacity_hard_denial_not_grantable(self):
        self.write(f"{int(time.time())+120} access_denied\n")
        self.assertIsNone(self.broker_cap())

    def test_trusted_intermediate_state_link_matches_installed_layout(self):
        self.write(f"{int(time.time())+120} http_429\n")
        parent = Path(self.tmp.name) / "native" / "ext"
        parent.mkdir(parents=True)
        (parent / "slots").symlink_to(Path(self.tmp.name), target_is_directory=True)
        # ext/slots is an authorized intermediate release state link, while
        # the *final* bailian directory must remain an owned physical folder.
        with patch.object(self.keys, "SLOTS_ROOT", str(parent / "slots" / "slots")):
            self.assertEqual(self.rank(), 2)

    def test_symlinked_cooldown_root_refused(self):
        self.write(f"{int(time.time())+120} access_denied\n")
        other = self.root.with_name("real_slots")
        self.root.rename(other)
        self.root.symlink_to(other, target_is_directory=True)
        self.assertEqual(self.rank(), 1)

    def test_directory_replacement_during_read_refused(self):
        self.write(f"{int(time.time())+120} http_429\n")
        original_read = self.keys.os.read
        moved = {"done": False}
        def replace_while_reading(fd, length):
            if not moved["done"]:
                moved["done"] = True
                self.root.rename(self.root.with_name("old_slots"))
                self.root.mkdir(mode=0o700)
            return original_read(fd, length)
        with patch.object(self.keys.os, "read", side_effect=replace_while_reading):
            self.assertEqual(self.rank(), 1)
        self.assertTrue(moved["done"])

    def test_account_name_path_escape_refused(self):
        self.assertEqual(self.keys.cooldown_rank_readonly("../other"), 1)


if __name__ == "__main__":
    unittest.main()
