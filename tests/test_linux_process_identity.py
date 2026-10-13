"""Inert tests for the Linux process identity helper.

Every OS-level seam (``_open_proc_root``, ``_open_proc_pid_dir``,
``_open_boot_id_file``, ``_read_proc_file``, ``_read_boot_id_raw``,
``_close_fd``) is replaced with synthetic fixtures, and a per-test guard
fails immediately if the module under test attempts a real ``os.open``,
``os.read`` or ``os.sysconf`` against the host.  Synthetic bytes are never
presented as real qualification: these tests assert parser behaviour and the
fail-closed contract only, and they never touch the real proc filesystem.
"""

from __future__ import annotations

import ast
import importlib
import inspect as inspect_module
import os
import sys
import unittest
from unittest import mock

from control_plane import linux_process_identity as lpi

LinuxProcessIdentityError = lpi.LinuxProcessIdentityError
# Captured before any patching: lets individual tests exercise the real seam.
_REAL_READ_PROC_FILE = lpi._read_proc_file

# Sentinel descriptors; every close/read is patched, so these are never real.
_PROC_ROOT_FD = 7301
_PID_DIR_FD = 7402
_BOOT_ID_FD = 7503

_BOOT_ID = "3f0b7d1a-9c2e-4d8f-b1a6-7e5c0d9f2a44"
_ALT_BOOT_ID = "9f2a44c1-0d9f-4b1a-8e5c-7d1a3f0b6c2e"


def make_stat(
    pid=4242,
    comm=b"mm-broker",
    state=b"S",
    ppid=1,
    pgrp=4242,
    session=4242,
    start_ticks=123456789,
    utime=40,
    minflt=1000,
):
    """Synthetic /proc/<pid>/stat payload; rest[i] is stat field 3 + i."""
    rest = [
        state,
        ppid,
        pgrp,
        session,
        3489,
        3489,
        4202624,
        minflt,
        0,
        0,
        0,
        utime,
        3,
        0,
        0,
        20,
        0,
        4,
        0,
        start_ticks,
        219136,
        512,
    ]
    rest_bytes = b" ".join(
        field if isinstance(field, bytes) else str(field).encode("ascii")
        for field in rest
    )
    return str(pid).encode("ascii") + b" (" + comm + b") " + rest_bytes


def make_status(
    pid=4242,
    ppid=1,
    uid=(1000, 1000, 1000, 1000),
    gid=(1000, 1000, 1000, 1000),
):
    """Synthetic /proc/<pid>/status payload with the documented layout."""
    return (
        b"Name:\tmm-broker\n"
        b"Umask:\t0022\n"
        b"State:\tS (sleeping)\n"
        b"Tgid:\t%d\n"
        b"Ngid:\t0\n"
        b"Pid:\t%d\n"
        b"PPid:\t%d\n"
        b"TracerPid:\t0\n"
        b"Uid:\t%d\t%d\t%d\t%d\n"
        b"Gid:\t%d\t%d\t%d\t%d\n"
        b"FDSize:\t64\n"
        b"VmRSS:\t1024 kB\n"
        b"Threads:\t4\n"
        b"voluntary_ctxt_switches:\t12\n"
    ) % (pid, pid, ppid, uid[0], uid[1], uid[2], uid[3], gid[0], gid[1], gid[2], gid[3])


class SeamTestCase(unittest.TestCase):
    """Patches every OS seam and forbids any real host I/O."""

    def setUp(self):
        super().setUp()
        self.forbidden_io = mock.Mock(
            side_effect=AssertionError("module attempted real host I/O")
        )
        for name in ("open", "read", "sysconf"):
            patcher = mock.patch.object(lpi.os, name, self.forbidden_io)
            patcher.start()
            self.addCleanup(patcher.stop)
        seams = (
            ("_open_proc_root", lambda: _PROC_ROOT_FD),
            ("_open_proc_pid_dir", lambda fd, pid: _PID_DIR_FD),
            ("_close_fd", lambda fd: None),
        )
        for name, replacement in seams:
            patcher = mock.patch.object(lpi, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.stat_payloads = []
        self.status_payloads = []

        def fake_read_proc_file(dir_fd, name, limit, label):
            self.assertEqual(dir_fd, _PID_DIR_FD)
            self.assertNotIn(
                name,
                ("environ", "cmdline"),
                "secret-bearing proc files are never read",
            )
            queues = {"stat": self.stat_payloads, "status": self.status_payloads}
            queue = queues.get(name)
            if queue is None:
                raise AssertionError(f"unexpected proc file read: {name!r}")
            if not queue:
                raise AssertionError(f"unexpected extra {name!r} read")
            return queue.pop(0)

        patcher = mock.patch.object(
            lpi, "_read_proc_file", side_effect=fake_read_proc_file
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def set_proc(self, stat=(), status=()):
        self.stat_payloads = list(stat)
        self.status_payloads = list(status)


class BootIdTests(SeamTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(lpi, "_open_boot_id_file", lambda: _BOOT_ID_FD)
        patcher.start()
        self.addCleanup(patcher.stop)

    def set_boot_raw(self, raw):
        patcher = mock.patch.object(
            lpi, "_read_boot_id_raw", return_value=raw
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_canonical_boot_id_is_returned(self):
        self.set_boot_raw((_BOOT_ID + "\n").encode("ascii"))
        self.assertEqual(lpi.read_linux_boot_id(), _BOOT_ID)

    def test_boot_id_is_stable_across_reads(self):
        raw = (_BOOT_ID + "\n").encode("ascii")
        self.set_boot_raw(raw)
        self.assertEqual(lpi.read_linux_boot_id(), lpi.read_linux_boot_id(), _BOOT_ID)

    def test_boot_id_without_trailing_newline_is_accepted(self):
        self.set_boot_raw(_BOOT_ID.encode("ascii"))
        self.assertEqual(lpi.read_linux_boot_id(), _BOOT_ID)

    def test_malformed_boot_ids_fail_closed(self):
        bad_payloads = [
            b"",
            b"\n",
            b"not-a-uuid\n",
            _BOOT_ID.upper().encode("ascii") + b"\n",
            (_BOOT_ID[:-1]).encode("ascii") + b"\n",
            (_BOOT_ID + "0").encode("ascii") + b"\n",
            (_BOOT_ID + " extra\n").encode("ascii"),
            _BOOT_ID.replace("-", "_").encode("ascii") + b"\n",
            (_BOOT_ID[:18] + "\n" + _BOOT_ID[18:] + "\n").encode("ascii"),
            b"\xff\xfe" + _BOOT_ID.encode("ascii") + b"\n",
        ]
        for raw in bad_payloads:
            with self.subTest(raw=raw):
                self.set_boot_raw(raw)
                with self.assertRaises(LinuxProcessIdentityError):
                    lpi.read_linux_boot_id()

    def test_malformed_boot_id_never_degrades_to_adapter_scope(self):
        self.set_boot_raw(b"garbage\n")
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.read_linux_boot_id()
        self.assertNotIn("adapter-", str(ctx.exception))

    def test_boot_id_open_denied_fails_closed(self):
        patcher = mock.patch.object(
            lpi,
            "_open_boot_id_file",
            side_effect=PermissionError(13, "Permission denied"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.read_linux_boot_id()
        self.assertIn("errno 13", str(ctx.exception))

    def test_boot_id_open_missing_fails_closed(self):
        patcher = mock.patch.object(
            lpi,
            "_open_boot_id_file",
            side_effect=FileNotFoundError(2, "No such file or directory"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.read_linux_boot_id()
        self.assertIn("errno 2", str(ctx.exception))

    def test_oversized_boot_id_fails_closed(self):
        patcher = mock.patch.object(
            lpi.os, "read", side_effect=[b"\xff" * 200, b""]
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi._read_boot_id_raw()
        self.assertIn("exceeds the maximum supported size of 128 bytes", str(ctx.exception))

    def test_boot_id_path_is_fixed(self):
        self.assertEqual(
            lpi._BOOT_ID_PROC_PATH, "/proc/sys/kernel/random/boot_id"
        )
        signature = inspect_module.signature(lpi.read_linux_boot_id)
        self.assertEqual(list(signature.parameters), [])


class StatParserTests(SeamTestCase):
    def test_stat_fields_are_reported(self):
        parsed = lpi._parse_stat(make_stat(start_ticks=123456789), 4242)
        self.assertEqual(parsed["pid"], 4242)
        self.assertEqual(parsed["ppid"], 1)
        self.assertEqual(parsed["pgrp"], 4242)
        self.assertEqual(parsed["session"], 4242)
        self.assertEqual(parsed["start_ticks"], 123456789)

    def test_comm_with_spaces_parens_and_newline(self):
        comm = b"bro kers (v2)\nrun)ner"
        parsed = lpi._parse_stat(make_stat(comm=comm), 4242)
        self.assertEqual(parsed["comm"], comm)
        self.assertEqual(parsed["start_ticks"], 123456789)

    def test_start_ticks_are_not_rounded(self):
        first = lpi._parse_stat(make_stat(start_ticks=123456780), 4242)
        second = lpi._parse_stat(make_stat(start_ticks=123456781), 4242)
        self.assertNotEqual(first["start_ticks"], second["start_ticks"])
        self.assertEqual(first["start_ticks"], 123456780)
        self.assertNotEqual(str(first["start_ticks"]), "1234567.8")

    def test_stat_reporting_another_pid_is_rejected(self):
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi._parse_stat(make_stat(pid=4999), 4242)
        self.assertIn("reported another pid", str(ctx.exception))

    def test_truncated_stat_is_rejected(self):
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi._parse_stat(b"4242 (mm-broker) S 1 4242 4242", 4242)
        self.assertIn("cannot parse /proc/4242/stat", str(ctx.exception))

    def test_non_numeric_start_ticks_are_rejected(self):
        payload = (
            b"4242 (mm-broker) R 1 4242 4242 "
            + b"0 " * 15
            + b"abc 0 0"
        )
        with self.assertRaises(LinuxProcessIdentityError):
            lpi._parse_stat(payload, 4242)

    def test_negative_ppid_is_rejected(self):
        payload = (
            b"4242 (mm-broker) S -1 4242 4242 "
            + b"0 " * 15
            + b"123456789 0 0"
        )
        with self.assertRaises(LinuxProcessIdentityError):
            lpi._parse_stat(payload, 4242)

    def test_multi_character_state_is_rejected(self):
        with self.assertRaises(LinuxProcessIdentityError):
            lpi._parse_stat(make_stat(state=b"RS"), 4242)

    def test_zero_group_or_session_is_rejected(self):
        for kwargs in ({"pgrp": 0}, {"session": 0}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(LinuxProcessIdentityError):
                    lpi._parse_stat(make_stat(**kwargs), 4242)

    def test_stat_diagnostics_do_not_leak_contents(self):
        payload = make_stat(comm=b"SEcReT-payload", pid=4999)
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi._parse_stat(payload, 4242)
        self.assertNotIn("SEcReT-payload", str(ctx.exception))


class StatusParserTests(SeamTestCase):
    def test_distinct_real_and_effective_credentials(self):
        parsed = lpi._parse_status(
            make_status(uid=(1000, 1001, 1002, 1003), gid=(2000, 2001, 2002, 2003)),
            4242,
        )
        self.assertEqual(parsed["real_uid"], 1000)
        self.assertEqual(parsed["effective_uid"], 1001)
        self.assertEqual(parsed["saved_uid"], 1002)
        self.assertEqual(parsed["filesystem_uid"], 1003)
        self.assertEqual(parsed["real_gid"], 2000)
        self.assertEqual(parsed["effective_gid"], 2001)
        self.assertEqual(parsed["saved_gid"], 2002)
        self.assertEqual(parsed["filesystem_gid"], 2003)
        self.assertEqual(parsed["ppid"], 1)

    def test_uid_and_gid_require_exactly_four_entries(self):
        for field, count in (("Uid", 3), ("Uid", 5), ("Gid", 3), ("Gid", 5)):
            with self.subTest(field=field, count=count):
                entries = b"\t".join(b"1000" for _ in range(count))
                payload = make_status().replace(
                    field.encode("ascii") + b":\t1000\t1000\t1000\t1000",
                    field.encode("ascii") + b":\t" + entries,
                )
                self.assertNotEqual(payload, make_status())
                with self.assertRaises(LinuxProcessIdentityError) as ctx:
                    lpi._parse_status(payload, 4242)
                self.assertIn("exactly 4 entries", str(ctx.exception))

    def test_missing_required_fields_are_rejected(self):
        for field in ("Uid:", "Gid:", "Pid:", "PPid:"):
            with self.subTest(field=field):
                payload = b"\n".join(
                    line
                    for line in make_status().split(b"\n")
                    if not line.startswith(field.encode("ascii"))
                )
                with self.assertRaises(LinuxProcessIdentityError) as ctx:
                    lpi._parse_status(payload, 4242)
                self.assertIn("missing required", str(ctx.exception))

    def test_duplicate_fields_are_rejected(self):
        base = make_status()
        for field, dup in (
            (b"Uid:", b"Uid:\t1\t1\t1\t1\n"),
            (b"Gid:", b"Gid:\t1\t1\t1\t1\n"),
            (b"Pid:", b"Pid:\t4242\n"),
        ):
            with self.subTest(field=field):
                lines = base.split(b"\n")
                index = next(
                    i for i, line in enumerate(lines) if line.startswith(field)
                )
                lines.insert(index, dup)
                with self.assertRaises(LinuxProcessIdentityError) as ctx:
                    lpi._parse_status(b"\n".join(lines), 4242)
                self.assertIn("duplicate", str(ctx.exception))

    def test_status_reporting_another_pid_is_rejected(self):
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi._parse_status(make_status(pid=4999), 4242)
        self.assertIn("reported another pid", str(ctx.exception))

    def test_non_numeric_principal_entry_is_rejected(self):
        payload = make_status().replace(
            b"Uid:\t1000\t1000\t1000\t1000",
            b"Uid:\troot\t1000\t1000\t1000",
        )
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi._parse_status(payload, 4242)
        self.assertIn("non-numeric entry in Uid field", str(ctx.exception))

    def test_status_diagnostics_do_not_leak_contents(self):
        payload = make_status(pid=4999).replace(
            b"Name:\tmm-broker", b"Name:\tSEcReT-broker"
        )
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi._parse_status(payload, 4242)
        self.assertNotIn("SEcReT-broker", str(ctx.exception))


class InspectTests(SeamTestCase):
    PID = 4242

    def setUp(self):
        super().setUp()
        self.stat = make_stat()
        self.status = make_status(
            uid=(1000, 1001, 1002, 1003), gid=(2000, 2001, 2002, 2003)
        )

    def test_inspect_returns_the_identity_dict(self):
        self.set_proc(stat=[self.stat, self.stat], status=[self.status, self.status])
        result = lpi.inspect_linux_process(self.PID)
        self.assertEqual(
            set(result),
            {
                "start_identity",
                "pgid",
                "session_id",
                "effective_uid",
                "effective_gid",
                "real_uid",
                "real_gid",
                "parent_pid",
            },
        )
        self.assertEqual(result["start_identity"], "123456789")
        self.assertIsInstance(result["start_identity"], str)
        self.assertEqual(result["pgid"], 4242)
        self.assertEqual(result["session_id"], 4242)
        self.assertEqual(result["effective_uid"], 1001)
        self.assertEqual(result["effective_gid"], 2001)
        self.assertEqual(result["real_uid"], 1000)
        self.assertEqual(result["real_gid"], 2000)
        self.assertEqual(result["parent_pid"], 1)
        for key in ("pgid", "session_id", "effective_uid", "effective_gid", "real_uid", "real_gid", "parent_pid"):
            self.assertIsInstance(result[key], int)

    def test_dynamic_counter_drift_is_tolerated(self):
        drifting = make_stat(utime=41, minflt=1001, state=b"R")
        self.set_proc(
            stat=[self.stat, drifting], status=[self.status, self.status]
        )
        result = lpi.inspect_linux_process(self.PID)
        self.assertEqual(result["start_identity"], "123456789")

    def test_stat_identity_change_is_rejected(self):
        changed = make_stat(pgrp=4243)
        self.set_proc(stat=[self.stat, changed], status=[self.status, self.status])
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process(self.PID)
        self.assertIn("changed between bracketing stat reads", str(ctx.exception))

    def test_pid_reuse_between_reads_is_rejected(self):
        reused = make_stat(start_ticks=987654321)
        self.set_proc(stat=[self.stat, reused], status=[self.status, self.status])
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process(self.PID)
        self.assertIn("reused", str(ctx.exception))

    def test_principal_change_is_rejected(self):
        changed = make_status(uid=(1000, 0, 1002, 1003))
        self.set_proc(stat=[self.stat, self.stat], status=[self.status, changed])
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process(self.PID)
        self.assertIn("principal effective_uid changed", str(ctx.exception))

    def test_status_pid_mismatch_is_rejected(self):
        other = make_status(pid=4999)
        self.set_proc(stat=[self.stat, self.stat], status=[other, other])
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process(self.PID)
        self.assertIn("reported another pid", str(ctx.exception))

    def test_parent_disagreement_between_sources_is_rejected(self):
        self.set_proc(
            stat=[self.stat, self.stat],
            status=[make_status(ppid=2), make_status(ppid=2)],
        )
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process(self.PID)
        self.assertIn("disagrees between stat and status", str(ctx.exception))

    def test_absent_process_fails_closed(self):
        patcher = mock.patch.object(
            lpi,
            "_open_proc_pid_dir",
            side_effect=FileNotFoundError(2, "No such file or directory"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process(self.PID)
        self.assertIn("absent", str(ctx.exception))

    def test_denied_process_directory_fails_closed(self):
        patcher = mock.patch.object(
            lpi,
            "_open_proc_pid_dir",
            side_effect=PermissionError(13, "Permission denied"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process(self.PID)
        self.assertIn("permission denied addressing /proc/4242", str(ctx.exception))

    def test_denied_read_fails_closed(self):
        # Restore the real _read_proc_file seam and make its inner os.open
        # fail, so the production OSError wrapping is what gets exercised.
        patcher = mock.patch.object(lpi, "_read_proc_file", _REAL_READ_PROC_FILE)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(
            lpi.os, "open", side_effect=PermissionError(13, "Permission denied")
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process(self.PID)
        self.assertIn(
            "cannot open /proc/4242/stat (errno 13)", str(ctx.exception)
        )

    def test_missing_read_fails_closed(self):
        patcher = mock.patch.object(lpi, "_read_proc_file", _REAL_READ_PROC_FILE)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(
            lpi.os,
            "open",
            side_effect=FileNotFoundError(2, "No such file or directory"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process(self.PID)
        self.assertIn("cannot open /proc/4242/stat", str(ctx.exception))

    def test_inspect_uses_only_synthetic_reads(self):
        self.set_proc(stat=[self.stat, self.stat], status=[self.status, self.status])
        lpi.inspect_linux_process(self.PID)
        self.forbidden_io.assert_not_called()


class BoundedReadTests(SeamTestCase):
    def test_within_limit_is_returned(self):
        patcher = mock.patch.object(lpi.os, "read", side_effect=[b"a" * 100, b""])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertEqual(lpi._read_bounded(_BOOT_ID_FD, 128, "boot id"), b"a" * 100)

    def test_oversized_read_is_rejected(self):
        patcher = mock.patch.object(
            lpi.os, "read", side_effect=[b"x" * 100, b"y" * 29, b""]
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi._read_bounded(_BOOT_ID_FD, 128, "boot id")
        self.assertIn("exceeds the maximum supported size of 128 bytes", str(ctx.exception))

    def test_chunks_are_reassembled(self):
        patcher = mock.patch.object(
            lpi.os, "read", side_effect=[b"z" * 8192, b"z" * 8192, b"z" * 8192, b""]
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertEqual(
            lpi._read_bounded(_BOOT_ID_FD, 65536, "stat"), b"z" * 24576
        )


class ApiSurfaceTests(SeamTestCase):
    def test_process_inspector_uses_boot_and_exact_credentials_without_fallback(self):
        from control_plane import codex_worker
        inspector = codex_worker.ProcessInspector()
        values = dict(start_identity="123456781", pgid=4242, session_id=4242,
                      effective_uid=1001, effective_gid=2001, real_uid=1000, real_gid=2000,
                      parent_pid=1)
        with mock.patch.object(codex_worker.platform, "system", return_value="Linux"), \
             mock.patch.object(codex_worker, "_run_checked", side_effect=AssertionError("fallback invoked")), \
             mock.patch.object(lpi, "read_linux_boot_id", return_value=_BOOT_ID), \
             mock.patch.object(lpi, "inspect_linux_process", return_value=values):
            self.assertEqual(inspector.boot_session_id(), _BOOT_ID)
            self.assertEqual(inspector.inspect(4242), codex_worker.ProcessIdentity(**values))
            with mock.patch.object(lpi, "read_linux_boot_id", side_effect=LinuxProcessIdentityError()):
                with self.assertRaises(codex_worker.ProcessIdentityError):
                    inspector.boot_session_id()
            with mock.patch.object(lpi, "inspect_linux_process", side_effect=LinuxProcessIdentityError()):
                with self.assertRaises(codex_worker.ProcessIdentityError):
                    inspector.inspect(4242)

    def test_root_open_failure_has_the_closed_public_error(self):
        with mock.patch.object(lpi, "_open_proc_root", side_effect=PermissionError(13, "private path")):
            with self.assertRaises(LinuxProcessIdentityError) as ctx:
                lpi.inspect_linux_process(4242)
        self.assertNotIn("private path", str(ctx.exception))

    def test_saved_or_filesystem_principal_change_is_rejected(self):
        for position in (2, 3):
            with self.subTest(position=position):
                changed = [1000, 1000, 1000, 1000]
                changed[position] = 1001
                self.set_proc(stat=[make_stat(), make_stat()],
                              status=[make_status(), make_status(uid=tuple(changed))])
                with self.assertRaises(LinuxProcessIdentityError):
                    lpi.inspect_linux_process(4242)

    def test_pid_must_be_a_strict_positive_int(self):
        for bad in (True, False, 3.0, "42", None, 0, -7):
            with self.subTest(bad=bad):
                with self.assertRaises(LinuxProcessIdentityError):
                    lpi.inspect_linux_process(bad)
        self.forbidden_io.assert_not_called()

    def test_inspect_takes_only_the_pid(self):
        signature = inspect_module.signature(lpi.inspect_linux_process)
        self.assertEqual(list(signature.parameters), ["pid"])
        self.assertNotIn(
            inspect_module.Parameter.VAR_KEYWORD,
            signature.parameters.values(),
            "no keyword catch-all: no arbitrary proc root or identity input",
        )

    def test_error_type_is_a_value_error(self):
        self.assertTrue(issubclass(LinuxProcessIdentityError, ValueError))

    def test_module_imports_the_standard_library_only(self):
        source = inspect_module.getsource(lpi)
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertLessEqual(imported, {"hashlib", "os", "re", "typing", "__future__"})

    def test_public_api_surface(self):
        self.assertEqual(
            set(lpi.__all__),
            {
                "LinuxProcessIdentityError",
                "inspect_linux_process",
                "inspect_linux_process_image",
                "read_linux_boot_id",
            },
        )


if __name__ == "__main__":
    unittest.main()
