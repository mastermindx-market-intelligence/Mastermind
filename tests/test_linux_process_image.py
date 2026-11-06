"""Inert tests for ``inspect_linux_process_image``.

Same discipline as ``tests/test_linux_process_identity.py``: every OS seam is
replaced with synthetic fixtures and a guard fails the test immediately if
the module attempts a real ``os.open``/``os.read``/``os.fstat``/``os.stat``/
``os.readlink``/``os.close``/``os.sysconf`` against the host.  The only real
bytes are a few harmless synthetic executable bytes hashed in memory.  No
proc filesystem is touched, nothing here qualifies a real process, and no
secret-bearing proc file is ever requested.
"""

from __future__ import annotations

import hashlib
import inspect as inspect_module
import unittest
from collections import deque
from unittest import mock

from control_plane import linux_process_identity as lpi

LinuxProcessIdentityError = lpi.LinuxProcessIdentityError

# Sentinel descriptors; every close/open/read is patched, so none are real.
_PROC_ROOT_FD = 8101
_PID_DIR_FD = 8202
_IMAGE_FD = 8303

_PID = 4242
_BOOT_ID = "3f0b7d1a-9c2e-4d8f-b1a6-7e5c0d9f2a44"

# Harmless synthetic image bytes; nothing executable is ever produced here.
EXECUTABLE_BYTES = b"\x7fELF-synthetic-harmless-image-bytes\n" * 4
EXECUTABLE_SHA256 = hashlib.sha256(EXECUTABLE_BYTES).hexdigest()

_META_BASE = dict(
    device=458129,
    inode=987654,
    mode=0o100755,
    uid=1000,
    gid=1000,
    mtime_ns=1_700_000_000_000_000_000,
    ctime_ns=1_700_000_000_000_000_001,
)


def image_meta(**overrides):
    """Synthetic fstat snapshot of the executed image."""
    meta = dict(_META_BASE)
    meta["size"] = len(EXECUTABLE_BYTES)
    meta.update(overrides)
    return meta


def make_stat(
    pid=_PID,
    comm=b"mm-broker",
    state=b"S",
    ppid=1,
    pgrp=_PID,
    session=_PID,
    start_ticks=123456789,
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
        1000,
        0,
        0,
        0,
        40,
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


def make_status(pid=_PID, ppid=1, uid=(1000, 1001, 1002, 1003), gid=(2000, 2001, 2002, 2003)):
    """Synthetic /proc/<pid>/status payload with the documented layout."""
    return (
        b"Name:\tmm-broker\n"
        b"State:\tS (sleeping)\n"
        b"Tgid:\t%d\n"
        b"Pid:\t%d\n"
        b"PPid:\t%d\n"
        b"Uid:\t%d\t%d\t%d\t%d\n"
        b"Gid:\t%d\t%d\t%d\t%d\n"
        b"Threads:\t4\n"
    ) % (pid, pid, ppid, uid[0], uid[1], uid[2], uid[3], gid[0], gid[1], gid[2], gid[3])


_RESULT_KEYS = {
    "start_identity",
    "pgid",
    "session_id",
    "effective_uid",
    "effective_gid",
    "real_uid",
    "real_gid",
    "parent_pid",
    "boot_id",
    "sha256",
    "size",
    "device",
    "inode",
    "mode",
    "uid",
    "gid",
    "mtime_ns",
    "ctime_ns",
}


class ImageSeamTestCase(unittest.TestCase):
    """Patches every OS seam and forbids any real host I/O."""

    def setUp(self):
        super().setUp()
        self.forbidden_io = mock.Mock(
            side_effect=AssertionError("module attempted real host I/O")
        )
        for name in ("open", "close", "fstat", "readlink", "stat", "lstat", "sysconf"):
            patcher = mock.patch.object(lpi.os, name, self.forbidden_io)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.exe_opens = []
        self.closed = []
        self.fstat_calls = []
        self.proc_reads = []

        def fake_open_exe(pid_dir_fd):
            self.assertEqual(
                pid_dir_fd,
                _PID_DIR_FD,
                "exe must be opened relative to the pinned pid directory",
            )
            self.exe_opens.append(pid_dir_fd)
            return _IMAGE_FD

        def fake_close(fd):
            self.closed.append(fd)

        def fake_fstat(image_fd):
            self.fstat_calls.append(image_fd)
            self.assertEqual(image_fd, _IMAGE_FD)
            if not self.fstat_meta:
                raise AssertionError("unexpected extra _fstat_image call")
            return self.fstat_meta.pop(0)

        def fake_read_proc_file(dir_fd, name, limit, label):
            self.assertEqual(dir_fd, _PID_DIR_FD)
            self.assertNotIn(
                name,
                ("environ", "cmdline", "maps", "mem"),
                "secret-bearing or content-bearing proc files are never read",
            )
            self.proc_reads.append(name)
            queues = {"stat": self.stat_payloads, "status": self.status_payloads}
            queue = queues.get(name)
            if queue is None:
                raise AssertionError(f"unexpected proc file read: {name!r}")
            if not queue:
                raise AssertionError(f"unexpected extra {name!r} read")
            return queue.pop(0)

        self.image_chunks = deque()

        def fake_read(fd, size):
            self.assertEqual(fd, _IMAGE_FD, "raw reads must target the image fd only")
            if not self.image_chunks:
                return b""
            return self.image_chunks.popleft()

        for target, replacement in (
            ("_open_proc_root", lambda: _PROC_ROOT_FD),
            ("_open_proc_pid_dir", lambda fd, pid: _PID_DIR_FD),
            ("_close_fd", fake_close),
            ("_open_proc_exe_image", fake_open_exe),
            ("_fstat_image", fake_fstat),
            ("_read_proc_file", fake_read_proc_file),
        ):
            patcher = mock.patch.object(lpi, target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(lpi, "read_linux_boot_id", return_value=_BOOT_ID)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Real os.read is replaced by the image-bytes feeder; everything else
        # on os stays forbidden.
        patcher = mock.patch.object(lpi.os, "read", fake_read)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.stat_payloads = []
        self.status_payloads = []
        self.fstat_meta = []

    def set_proc(self, stat=(), status=()):
        self.stat_payloads = list(stat)
        self.status_payloads = list(status)

    def set_image(self, chunks=(), meta=()):
        self.image_chunks = deque(chunks)
        self.fstat_meta = list(meta)

    def set_happy(self):
        self.set_proc(
            stat=[make_stat(), make_stat()],
            status=[make_status(), make_status()],
        )
        self.set_image(chunks=[EXECUTABLE_BYTES], meta=[image_meta()] * 3)


class ClosingBracketTests(ImageSeamTestCase):
    def test_confirmation_is_inside_the_closing_principal_bracket(self):
        self.set_happy()
        confirm = lpi._confirm_image_unswitched
        def changes_principal(*args):
            confirm(*args)
            self.status_payloads[:] = [make_status(uid=(1000, 2001, 1002, 1003))]
        with mock.patch.object(lpi, "_confirm_image_unswitched", changes_principal):
            with self.assertRaisesRegex(LinuxProcessIdentityError, "principal effective_uid changed"):
                lpi.inspect_linux_process_image(_PID)


class ImageMetadataFailureTests(unittest.TestCase):
    def test_fstat_error_has_closed_typed_diagnostic(self):
        with mock.patch.object(lpi.os, "fstat", side_effect=OSError(5, "private fixture payload")):
            with self.assertRaisesRegex(LinuxProcessIdentityError, "cannot stat executed image.*errno 5") as caught:
                lpi._fstat_image(123)
        self.assertNotIn("private fixture payload", str(caught.exception))


class HappyPathTests(ImageSeamTestCase):
    def test_image_observation_returns_identity_plus_image_fields(self):
        self.set_happy()
        result = lpi.inspect_linux_process_image(_PID)
        self.assertEqual(set(result), _RESULT_KEYS)
        self.assertEqual(result["start_identity"], "123456789")
        self.assertIsInstance(result["start_identity"], str)
        self.assertEqual(result["pgid"], _PID)
        self.assertEqual(result["session_id"], _PID)
        self.assertEqual(result["effective_uid"], 1001)
        self.assertEqual(result["effective_gid"], 2001)
        self.assertEqual(result["real_uid"], 1000)
        self.assertEqual(result["real_gid"], 2000)
        self.assertEqual(result["parent_pid"], 1)
        self.assertEqual(result["boot_id"], _BOOT_ID)
        self.assertEqual(result["sha256"], EXECUTABLE_SHA256)
        self.assertEqual(result["size"], len(EXECUTABLE_BYTES))
        for key in ("device", "inode", "mode", "uid", "gid", "mtime_ns", "ctime_ns"):
            self.assertEqual(result[key], _META_BASE[key])
        self.assertIsInstance(result["sha256"], str)
        self.assertEqual(len(result["sha256"]), 64)
        for key in ("size", "device", "inode", "mode", "uid", "gid", "mtime_ns", "ctime_ns"):
            self.assertIsInstance(result[key], int)
        self.forbidden_io.assert_not_called()

    def test_identity_fields_match_the_legacy_result_for_the_same_proc(self):
        self.set_happy()
        image_result = lpi.inspect_linux_process_image(_PID)
        self.set_proc(
            stat=[make_stat(), make_stat()],
            status=[make_status(), make_status()],
        )
        legacy = lpi.inspect_linux_process(_PID)
        for key, value in legacy.items():
            self.assertEqual(image_result[key], value)
        self.assertNotIn("sha256", legacy)
        self.assertEqual(set(legacy), _RESULT_KEYS - {
            "boot_id", "sha256", "size", "device", "inode",
            "mode", "uid", "gid", "mtime_ns", "ctime_ns",
        })

    def test_hash_covers_the_streamed_chunks(self):
        first, second = EXECUTABLE_BYTES[:10], EXECUTABLE_BYTES[10:]
        self.set_proc(
            stat=[make_stat(), make_stat()],
            status=[make_status(), make_status()],
        )
        self.set_image(
            chunks=[first, second],
            meta=[image_meta(size=len(first) + len(second))] * 3,
        )
        result = lpi.inspect_linux_process_image(_PID)
        self.assertEqual(result["sha256"], EXECUTABLE_SHA256)
        self.assertEqual(result["size"], len(EXECUTABLE_BYTES))

    def test_exe_is_opened_twice_relative_to_the_same_pinned_directory(self):
        self.set_happy()
        lpi.inspect_linux_process_image(_PID)
        self.assertEqual(self.exe_opens, [_PID_DIR_FD, _PID_DIR_FD])
        self.assertEqual(self.fstat_calls, [_IMAGE_FD, _IMAGE_FD, _IMAGE_FD])
        self.assertEqual(
            self.proc_reads, ["stat", "status", "status", "stat"]
        )
        self.forbidden_io.assert_not_called()

    def test_every_descriptor_is_closed_exactly_once_on_success(self):
        self.set_happy()
        lpi.inspect_linux_process_image(_PID)
        self.assertEqual(
            self.closed,
            # image fd (after hash), image fd (after confirmation reopen),
            # pid directory, proc root.
            [_IMAGE_FD, _IMAGE_FD, _PID_DIR_FD, _PROC_ROOT_FD],
        )

    def test_boot_scope_comes_from_the_fixed_boot_reader(self):
        self.set_happy()
        result = lpi.inspect_linux_process_image(_PID)
        self.assertEqual(result["boot_id"], _BOOT_ID)

    def test_boot_id_failure_is_fail_closed_before_any_proc_access(self):
        self.set_happy()
        root = mock.Mock(side_effect=AssertionError("proc root must not be opened"))
        with mock.patch.object(lpi, "_open_proc_root", root), \
             mock.patch.object(
                 lpi, "read_linux_boot_id", side_effect=LinuxProcessIdentityError()
             ):
            with self.assertRaises(LinuxProcessIdentityError):
                lpi.inspect_linux_process_image(_PID)
        root.assert_not_called()
        self.assertEqual(self.exe_opens, [])
        self.forbidden_io.assert_not_called()


class ImageFailureTests(ImageSeamTestCase):
    def test_zombie_is_rejected_before_the_image_is_touched(self):
        zombie = make_stat(state=b"Z")
        self.set_proc(stat=[zombie, zombie], status=[make_status(), make_status()])
        self.set_image(chunks=[EXECUTABLE_BYTES], meta=[image_meta()] * 3)
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process_image(_PID)
        self.assertIn("is a zombie", str(ctx.exception))
        self.assertEqual(self.exe_opens, [])
        self.assertEqual(self.proc_reads, ["stat"])
        self.assertEqual(self.closed, [_PID_DIR_FD, _PROC_ROOT_FD])
        self.forbidden_io.assert_not_called()

    def test_missing_exe_fails_closed(self):
        self.set_happy()
        with mock.patch.object(
            lpi,
            "_open_proc_exe_image",
            side_effect=FileNotFoundError(2, "No such file or directory"),
        ):
            with self.assertRaises(LinuxProcessIdentityError) as ctx:
                lpi.inspect_linux_process_image(_PID)
        self.assertIn("cannot open /proc/4242/exe", str(ctx.exception))
        self.assertIn("errno 2", str(ctx.exception))
        self.assertEqual(self.closed, [_PID_DIR_FD, _PROC_ROOT_FD])

    def test_denied_exe_fails_closed(self):
        self.set_happy()
        with mock.patch.object(
            lpi,
            "_open_proc_exe_image",
            side_effect=PermissionError(13, "Permission denied"),
        ):
            with self.assertRaises(LinuxProcessIdentityError) as ctx:
                lpi.inspect_linux_process_image(_PID)
        self.assertIn("permission denied opening /proc/4242/exe", str(ctx.exception))
        self.assertIn("errno 13", str(ctx.exception))
        self.assertEqual(self.closed, [_PID_DIR_FD, _PROC_ROOT_FD])

    def test_metadata_mutation_while_hashing_is_rejected(self):
        self.set_happy()
        mutated = image_meta(ctime_ns=1_700_000_000_999_999_999)
        self.set_image(chunks=[EXECUTABLE_BYTES], meta=[image_meta(), mutated, mutated])
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process_image(_PID)
        self.assertIn("metadata mutated while it was being read", str(ctx.exception))
        self.assertIn("ctime_ns differs", str(ctx.exception))
        self.assertEqual(self.closed, [_IMAGE_FD, _PID_DIR_FD, _PROC_ROOT_FD])

    def test_hash_size_drift_is_rejected(self):
        self.set_happy()
        # Metadata snapshots agree, but the bytes do not add up to st_size.
        self.set_image(
            chunks=[EXECUTABLE_BYTES, b"extra"],
            meta=[image_meta()] * 3,
        )
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process_image(_PID)
        self.assertIn("reported a size of", str(ctx.exception))
        self.assertIn("bytes were hashed", str(ctx.exception))
        self.assertEqual(self.closed, [_IMAGE_FD, _PID_DIR_FD, _PROC_ROOT_FD])

    def test_exe_switch_between_hash_and_reopen_is_rejected(self):
        for field, value in (
            ("device", 458130),
            ("inode", 987655),
            ("mode", 0o100644),
            ("uid", 0),
            ("gid", 0),
            ("size", len(EXECUTABLE_BYTES) + 1),
            ("mtime_ns", 1_799_999_999_999_999_999),
            ("ctime_ns", 1_799_999_999_999_999_999),
        ):
            with self.subTest(field=field):
                self.setUp()
                self.set_happy()
                switched = image_meta(**{field: value})
                self.set_image(
                    chunks=[EXECUTABLE_BYTES],
                    meta=[image_meta(), image_meta(), switched],
                )
                with self.assertRaises(LinuxProcessIdentityError) as ctx:
                    lpi.inspect_linux_process_image(_PID)
                self.assertIn(
                    "switched between the hash and the confirmation reopen",
                    str(ctx.exception),
                )
                self.assertIn(f"{field} differs", str(ctx.exception))
                self.assertEqual(len(self.exe_opens), 2)

    def test_read_failure_while_hashing_closes_the_image_descriptor(self):
        self.set_happy()
        with mock.patch.object(
            lpi.os, "read", side_effect=OSError(5, "Input/output error")
        ):
            with self.assertRaises(LinuxProcessIdentityError) as ctx:
                lpi.inspect_linux_process_image(_PID)
        self.assertIn("cannot read /proc/4242/exe", str(ctx.exception))
        self.assertIn("errno 5", str(ctx.exception))
        self.assertEqual(self.closed, [_IMAGE_FD, _PID_DIR_FD, _PROC_ROOT_FD])

    def test_oversized_stream_is_refused(self):
        self.set_happy()
        with mock.patch.object(lpi, "_IMAGE_MAX_BYTES", 16):
            self.set_image(
                chunks=[b"\xff" * 12, b"\xff" * 12],
                meta=[image_meta(size=24)] * 3,
            )
            with self.assertRaises(LinuxProcessIdentityError) as ctx:
                lpi.inspect_linux_process_image(_PID)
        self.assertIn(
            "exceeds the maximum supported image size of 16 bytes",
            str(ctx.exception),
        )
        self.assertEqual(self.closed, [_IMAGE_FD, _PID_DIR_FD, _PROC_ROOT_FD])

    def test_default_hash_bound_is_128mib(self):
        self.assertEqual(lpi._IMAGE_MAX_BYTES, 128 * 1024 * 1024)

    def test_oversized_image_is_refused_without_hashing(self):
        self.set_happy()
        self.set_image(
            chunks=[EXECUTABLE_BYTES],
            meta=[image_meta(size=lpi._IMAGE_MAX_BYTES + 1)] * 3,
        )
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process_image(_PID)
        self.assertIn(
            f"exceeds the maximum supported image size of {lpi._IMAGE_MAX_BYTES} bytes",
            str(ctx.exception),
        )
        self.assertEqual(self.image_chunks, deque([EXECUTABLE_BYTES]))

    def test_empty_image_is_refused(self):
        self.set_happy()
        self.set_image(chunks=[b""], meta=[image_meta(size=0)] * 3)
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process_image(_PID)
        self.assertIn("is empty; refusing to hash it", str(ctx.exception))

    def test_non_regular_image_is_refused(self):
        self.set_happy()
        self.set_image(chunks=[b""], meta=[image_meta(mode=0o40755)] * 3)
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process_image(_PID)
        self.assertIn("is not a regular file; refusing to hash it", str(ctx.exception))

    def test_identity_change_during_the_image_bracket_is_rejected(self):
        self.set_happy()
        self.set_proc(
            stat=[make_stat(), make_stat(start_ticks=987654321)],
            status=[make_status(), make_status()],
        )
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process_image(_PID)
        self.assertIn("changed between bracketing stat reads", str(ctx.exception))
        self.assertIn("reused", str(ctx.exception))

    def test_principal_change_during_the_image_bracket_is_rejected(self):
        self.set_happy()
        self.set_proc(
            stat=[make_stat(), make_stat()],
            status=[make_status(), make_status(uid=(1000, 0, 1002, 1003))],
        )
        with self.assertRaises(LinuxProcessIdentityError) as ctx:
            lpi.inspect_linux_process_image(_PID)
        self.assertIn("principal effective_uid changed", str(ctx.exception))

    def test_dead_process_directory_fails_closed(self):
        self.set_happy()
        with mock.patch.object(
            lpi,
            "_open_proc_pid_dir",
            side_effect=FileNotFoundError(2, "No such file or directory"),
        ):
            with self.assertRaises(LinuxProcessIdentityError) as ctx:
                lpi.inspect_linux_process_image(_PID)
        self.assertIn("absent or cannot be addressed", str(ctx.exception))
        self.assertEqual(self.closed, [_PROC_ROOT_FD])

    def test_denied_process_directory_fails_closed(self):
        self.set_happy()
        with mock.patch.object(
            lpi,
            "_open_proc_pid_dir",
            side_effect=PermissionError(13, "Permission denied"),
        ):
            with self.assertRaises(LinuxProcessIdentityError) as ctx:
                lpi.inspect_linux_process_image(_PID)
        self.assertIn("permission denied addressing /proc/4242", str(ctx.exception))

    def test_diagnostics_do_not_leak_image_bytes(self):
        self.set_happy()
        with mock.patch.object(
            lpi.os, "read", side_effect=OSError(5, "Input/output error")
        ):
            with self.assertRaises(LinuxProcessIdentityError) as ctx:
                lpi.inspect_linux_process_image(_PID)
        message = str(ctx.exception)
        self.assertNotIn("ELF", message)
        self.assertNotIn(EXECUTABLE_SHA256[:16], message)


class ImageApiSurfaceTests(ImageSeamTestCase):
    def test_pid_validation_precedes_every_read(self):
        for bad in (True, False, 3.0, "42", None, 0, -7):
            with self.subTest(bad=bad):
                with self.assertRaises(LinuxProcessIdentityError):
                    lpi.inspect_linux_process_image(bad)
        self.forbidden_io.assert_not_called()
        self.assertEqual(self.exe_opens, [])
        self.assertEqual(self.proc_reads, [])

    def test_signature_takes_only_the_pid(self):
        signature = inspect_module.signature(lpi.inspect_linux_process_image)
        self.assertEqual(list(signature.parameters), ["pid"])
        self.assertNotIn(
            inspect_module.Parameter.VAR_KEYWORD,
            signature.parameters.values(),
            "no keyword catch-all: no caller proc root, path or proof input",
        )
        self.assertNotIn(
            inspect_module.Parameter.VAR_POSITIONAL,
            signature.parameters.values(),
        )

    def test_only_stat_and_status_are_ever_requested(self):
        self.set_happy()
        lpi.inspect_linux_process_image(_PID)
        self.assertEqual(set(self.proc_reads), {"stat", "status"})
        self.forbidden_io.assert_not_called()

    def test_result_is_a_plain_snapshot_of_scalars(self):
        self.set_happy()
        result = lpi.inspect_linux_process_image(_PID)
        self.assertEqual(set(result), _RESULT_KEYS)
        for value in result.values():
            self.assertIsInstance(value, (str, int))
        self.assertNotIn(b"ELF".decode(), str(result.values()))

    def test_legacy_read_order_is_unchanged_by_the_refactor(self):
        self.set_proc(
            stat=[make_stat(), make_stat()],
            status=[make_status(), make_status()],
        )
        result = lpi.inspect_linux_process(_PID)
        self.assertEqual(self.proc_reads, ["stat", "status", "status", "stat"])
        self.assertEqual(result["start_identity"], "123456789")
        self.assertEqual(self.exe_opens, [])


if __name__ == "__main__":
    unittest.main()
