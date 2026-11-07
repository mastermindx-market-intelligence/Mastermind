"""Hermetic tests for mandatory TCP sandbox ordering and refusal behavior."""
import ctypes
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import stat
import socket
import tempfile
import unittest
from unittest import mock

from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime import tcp_sandbox as sandbox
from integrations.hermes_runtime.errors import RuntimeRefusal


class TcpSandboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hermes-tcp-policy-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def profile(self, role="mmsecretary"):
        return compose_profile(role, state_dir=self.root / role,
                               secrets_file=self.root / (role + ".env"))

    def test_exact_ports_for_both_roles(self):
        self.assertEqual(sandbox.role_tcp_ports(self.profile()),
                         (frozenset({8765, 8766}), frozenset({8765, 8766, 18651})))
        self.assertEqual(sandbox.role_tcp_ports(self.profile("mmmeta")),
                         (frozenset({8865, 8866}), frozenset({8865, 8866, 18652})))

    def test_ephemeral_boolean_privileged_and_colliding_ports_refused(self):
        for port in (0, True, 80, 65536, 8766, 18651):
            with self.subTest(port=port), self.assertRaisesRegex(RuntimeRefusal, "ROLE_TCP_FIXED_PORTS_REQUIRED"):
                sandbox.role_tcp_ports(replace(self.profile(), gateway_port=port))

    def test_invalid_policy_does_not_touch_kernel(self):
        for ports in (set(), frozenset(), frozenset({0}), frozenset({True}), frozenset({80})):
            with mock.patch.object(sandbox, "_libc") as libc, self.assertRaises(RuntimeRefusal):
                sandbox.apply_tcp_port_policy(ports, frozenset({18651}))
            libc.assert_not_called()

    def fake(self, *, abi=4, fail=None):
        calls, rules = [], []
        def syscall(number, *args):
            n = number.value
            calls.append(n)
            if n == sandbox._CREATE:
                if args[2].value == sandbox._VERSION:
                    return abi
                return -1 if fail == "create" else 99
            if n == sandbox._ADD:
                obj = ctypes.cast(args[2], ctypes.POINTER(sandbox._PortRule)).contents
                rules.append((obj.port, obj.allowed_access))
                return -1 if fail == "rule" else 0
            if n == sandbox._RESTRICT:
                return -1 if fail == "attach" else 0
            raise AssertionError(n)
        return SimpleNamespace(syscall=syscall, prctl=mock.Mock(return_value=-1 if fail == "prctl" else 0)), calls, rules

    def apply(self, lib):
        with mock.patch.object(sandbox, "_libc", return_value=lib), \
                mock.patch.object(sandbox, "_single_thread_without_sockets"), \
                mock.patch.object(sandbox.os, "close") as close:
            sandbox.apply_tcp_port_policy(frozenset({8765, 8766}), frozenset({8765, 8766, 18651}))
        return close

    def test_kernel_rules_and_attachment_have_exact_rights(self):
        lib, calls, rules = self.fake()
        close = self.apply(lib)
        self.assertEqual(rules, [(8765, 3), (8766, 3), (18651, 2)])
        self.assertEqual(calls, [444, 444, 445, 445, 445, 446])
        close.assert_called_once_with(99)
        lib.prctl.assert_called_once()

    def test_unsupported_abi_never_degrades_to_unrestricted(self):
        for abi in (-1, 0, 1, 2, 3):
            lib, calls, rules = self.fake(abi=abi)
            with self.subTest(abi=abi), self.assertRaisesRegex(RuntimeRefusal, "ROLE_TCP_LANDLOCK_ABI_UNAVAILABLE"):
                self.apply(lib)
            self.assertEqual(calls, [444])
            self.assertEqual(rules, [])
            lib.prctl.assert_not_called()

    def test_every_failed_enforcement_stage_refuses(self):
        for stage, code in (("create", "CREATE_FAILED"), ("rule", "RULE_FAILED"),
                            ("prctl", "NO_NEW_PRIVS_FAILED"), ("attach", "ATTACH_FAILED")):
            lib, calls, _ = self.fake(fail=stage)
            with self.subTest(stage=stage), self.assertRaisesRegex(RuntimeRefusal, code):
                self.apply(lib)
            if stage != "attach":
                self.assertNotIn(sandbox._RESTRICT, calls)

    def test_preexisting_threads_refused(self):
        with mock.patch.object(sandbox.os, "listdir", return_value=["1", "2"]), \
                self.assertRaisesRegex(RuntimeRefusal, "ROLE_TCP_LATE_SANDBOX_REFUSED"):
            sandbox._single_thread_without_sockets()

    def test_preexisting_socket_refused(self):
        item = SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600)
        with mock.patch.object(sandbox.os, "listdir", side_effect=[["1"], ["5"]]), \
                mock.patch.object(sandbox.os, "fstat", return_value=item), \
                mock.patch.object(sandbox, "_is_unix_socket", return_value=False), \
                self.assertRaisesRegex(RuntimeRefusal, "ROLE_TCP_INHERITED_SOCKET_REFUSED"):
            sandbox._single_thread_without_sockets()

    def test_systemd_journal_unix_socket_remains_usable(self):
        left, right = socket.socketpair()
        with left as journal, right:
            self.assertTrue(sandbox._is_unix_socket(journal.fileno()))
            with mock.patch.object(sandbox.os, "listdir", side_effect=[["1"], [str(journal.fileno())]]):
                sandbox._single_thread_without_sockets()

    def test_closed_enumeration_descriptor_is_not_a_socket(self):
        with mock.patch.object(sandbox.os, "listdir", side_effect=[["1"], ["9"]]), \
                mock.patch.object(sandbox.os, "fstat", side_effect=OSError):
            sandbox._single_thread_without_sockets()


if __name__ == "__main__":
    unittest.main()
