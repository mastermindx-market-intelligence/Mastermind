#!/usr/bin/env python3
"""Inert/local-child tests for the opt-in owned private file capture.

No provider processes, no /proc identity scraping and no real process census:
identity observation and the process-group/session census are mocked on the
patched lane_runtime. Trivial local Python children exercise the real pipes,
collector threads, exclusive files, sealing and result publication.

The pytest fixture materializes the exact pinned base and source patch.
The canonical supported-Claude parser is used unchanged.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import io
import json
import os
import queue
import shutil
import stat
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from test_fabric_owned_process_phases import lr
lane_runtime = None

@pytest.fixture(autouse=True)
def canonical_lane(lr):
    global lane_runtime
    lane_runtime = lr

SCHEMA_JSON = json.dumps({
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["summary"],
    "properties": {
        "summary": {"type": "string", "minLength": 1},
        "count": {"type": "integer", "minimum": 0},
    },
    "additionalProperties": False,
})

CHILD_OK = [sys.executable, "-c",
            "import json,sys\n"
            "sys.stderr.write('warn line\\n')\n"
            "print(json.dumps({'structured_output': {'summary': 'ok', 'count': 1},"
            " 'session_id': 'sess-abc',"
            " 'usage': {'input_tokens': 3, 'output_tokens': 5}}), end='')\n"]

CHILD_BAD_PARSE = [sys.executable, "-c",
                   "import json\n"
                   "print(json.dumps({'structured_output': {'summary': 123}}), end='')\n"]

CHILD_NONZERO = [sys.executable, "-c",
                 "import json,sys\n"
                 "print(json.dumps({'structured_output': {'summary': 'ok'}}), end='')\n"
                 "sys.exit(3)\n"]

CHILD_SLOW_STREAM = [sys.executable, "-c",
                     "import sys, time\n"
                     "for i in range(20):\n"
                     "    sys.stdout.write('x' * 1000 + '\\n')\n"
                     "    sys.stdout.flush()\n"
                     "    time.sleep(0.03)\n"]

CHILD_SLEEP = [sys.executable, "-c", "import time; time.sleep(30)\n"]

CHILD_BIG = [sys.executable, "-c",
             "import sys\n"
             "sys.stdout.write('y' * 200 + '\\n')\n"
             "sys.stderr.write('e' * 40 + '\\n')\n"]


def canonical(payload) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False).encode("utf-8")
            + b"\n")


class OwnedCaptureCase(unittest.TestCase):
    """Common mocked kernel/identity/census environment."""

    def setUp(self):
        self._patchers = []
        self._patch(lane_runtime, "_group_pids", lambda pgid: (pgid,))
        self._patch(lane_runtime, "_session_pids", lambda sid: ())
        self._patch(lane_runtime, "process_exists", lambda pid: True)
        self._identities: dict[int, dict] = {}
        self._patch(lane_runtime, "_observe_owned_launch_identity",
                    self._fake_identity)
        self.run_dir = self._make_run_dir()
        self.receipt_path = Path(self.run_dir + ".receipt.jsonl")

    def tearDown(self):
        # Runs whose capture stayed unproven intentionally keep the global
        # exclusion; reset it so tests stay independent.
        lane_runtime._EXECUTION_OWNER = None
        lane_runtime._CURRENT_PROCESS = None

    # -- helpers ---------------------------------------------------------------
    def _patch(self, target, name, value):
        patcher = mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fake_identity(self, pid: int) -> dict:
        if pid not in self._identities:
            self._identities[pid] = {
                "pid": pid, "pgid": pid, "session_id": pid,
                "boot_id": "00000000-test-boot-id",
                "process_start_identity": "linux:123456",
                "effective_uid": os.geteuid(), "effective_gid": os.getegid(),
                "real_uid": os.geteuid(), "real_gid": os.getegid(),
            }
        return dict(self._identities[pid])

    def _make_run_dir(self) -> str:
        path = tempfile.mkdtemp(prefix="owned-capture-run-")
        os.chmod(path, 0o700)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return str(Path(path).resolve())

    def _receipt(self) -> dict:
        rows = self.receipt_path.read_text(encoding="utf-8").splitlines()
        return json.loads(rows[-1])

    def _capture_block(self, receipt: dict) -> dict:
        self.assertIn("owned_capture", receipt)
        return receipt["owned_capture"]

    def run_capture(self, command, *, run_dir=None, schema=SCHEMA_JSON,
                    limit=None, timeout=20.0, **kw):
        kwargs = dict(timeout=timeout, label="test-run",
                      receipt_path=self.receipt_path)
        if run_dir is not None:
            kwargs["owned_capture_run_dir"] = run_dir
            kwargs["owned_capture_result_schema_json"] = schema
        if limit is not None:
            kwargs["capture_limit_bytes"] = limit
        kwargs.update(kw)
        return lane_runtime.run_owned_process(command, **kwargs)


class DefaultBehaviorTests(OwnedCaptureCase):

    def test_legacy_path_unchanged_without_option(self):
        result = self.run_capture(CHILD_OK)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertIsNone(result.owned_capture)
        self.assertIsNone(result.structured_result)
        self.assertIn("ok", result.stdout)
        self.assertTrue(lane_runtime.cleanup_receipt_is_proven(result.cleanup))
        receipt = self._receipt()
        self.assertNotIn("owned_capture", receipt)
        self.assertNotIn("stdout_file_capture_complete", receipt["cleanup"])
        self.assertNotIn("stderr_file_capture_complete", receipt["cleanup"])
        self.assertEqual(receipt["cleanup"]["stdout_capture_complete"], True)
        self.assertFalse((Path(self.run_dir) / "logs").exists())
        self.assertFalse((Path(self.run_dir) / "output").exists())


class HappyPathTests(OwnedCaptureCase):

    def test_capture_publishes_qualified_result(self):
        result = self.run_capture(CHILD_OK, run_dir=self.run_dir)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.structured_result, {"summary": "ok", "count": 1})
        run_dir = Path(self.run_dir)
        stdout_file = run_dir / "logs" / "stdout.json"
        stderr_file = run_dir / "logs" / "stderr.log"
        result_file = run_dir / "output" / "result.json"
        raw_stdout = result.stdout.encode("utf-8")
        self.assertEqual(stdout_file.read_bytes(), raw_stdout)
        self.assertEqual(stderr_file.read_bytes(), b"warn line\n")
        self.assertEqual(result_file.read_bytes(), canonical(result.structured_result))
        expected = {"stdout_path": self.run_dir + "/logs/stdout.json",
                    "stderr_path": self.run_dir + "/logs/stderr.log",
                    "result_path": self.run_dir + "/output/result.json"}
        self.assertEqual(result.owned_capture["files"]["stdout"]["path"],
                         expected["stdout_path"])
        block = self._capture_block(self._receipt())
        self.assertEqual(block["schema"], "mastermind.local_owned_capture_files.v1")
        self.assertTrue(block["stdout_file_complete"])
        self.assertTrue(block["stderr_file_complete"])
        self.assertEqual(block["stdout"]["file_sha256"],
                         hashlib.sha256(raw_stdout).hexdigest())
        self.assertEqual(block["stdout"]["stream_sha256"],
                         block["stdout"]["file_sha256"])
        self.assertEqual(block["stdout"]["stream_bytes"], len(raw_stdout))
        self.assertEqual(block["result"]["state"], "published")
        self.assertIsNone(block["result"]["reason"])
        self.assertEqual(block["result"]["sha256"],
                         hashlib.sha256(canonical(result.structured_result)).hexdigest())
        self.assertEqual(block["provider_observations"]["session_id"], "sess-abc")
        self.assertIs(block["provider_observations"]["authority"], False)
        self.assertEqual(block["result_schema_sha256"],
                         hashlib.sha256(SCHEMA_JSON.encode()).hexdigest())
        # private modes, exact ownership, and cleanup stays proven
        for path in (stdout_file, stderr_file, result_file):
            info = os.stat(path)
            self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
            self.assertEqual(info.st_uid, os.geteuid())
        for path in (run_dir / "logs", run_dir / "output"):
            info = os.stat(path)
            self.assertEqual(stat.S_IMODE(info.st_mode), 0o700)
            self.assertEqual(info.st_uid, os.geteuid())
        self.assertTrue(lane_runtime.cleanup_receipt_is_proven(result.cleanup))
        self.assertEqual(result.cleanup["stdout_file_capture_complete"], True)
        self.assertEqual(result.cleanup["stderr_file_capture_complete"], True)


class RefusalTests(OwnedCaptureCase):

    def test_existing_stdout_file_refuses_without_replay(self):
        logs = Path(self.run_dir) / "logs"
        logs.mkdir(mode=0o700)
        sentinel = logs / "stdout.json"
        sentinel.write_bytes(b"KEEP ME")
        with self.assertRaises(lane_runtime.LaneRuntimeError) as ctx:
            self.run_capture(CHILD_OK, run_dir=self.run_dir)
        self.assertEqual(str(ctx.exception), "owned_capture_file_exists")
        self.assertEqual(sentinel.read_bytes(), b"KEEP ME")
        self.assertIsNone(lane_runtime._EXECUTION_OWNER)
        self.assertFalse((Path(self.run_dir) / "output").exists())

    def test_missing_run_dir_refuses(self):
        missing = os.path.join(self.run_dir, "does-not-exist")
        with self.assertRaises(lane_runtime.LaneRuntimeError) as ctx:
            self.run_capture(CHILD_OK, run_dir=missing)
        self.assertEqual(str(ctx.exception), "owned_capture_run_dir_unavailable")

    def test_shared_run_dir_refuses(self):
        os.chmod(self.run_dir, 0o755)
        with self.assertRaises(lane_runtime.LaneRuntimeError) as ctx:
            self.run_capture(CHILD_OK, run_dir=self.run_dir)
        self.assertEqual(str(ctx.exception), "owned_capture_run_dir_unsafe")
        os.chmod(self.run_dir, 0o700)

    def test_symlinked_run_dir_refuses(self):
        real = tempfile.mkdtemp(prefix="owned-capture-real-")
        self.addCleanup(shutil.rmtree, real, ignore_errors=True)
        link = self.run_dir + ".link"
        os.symlink(real, link)
        self.addCleanup(os.unlink, link)
        with self.assertRaises(lane_runtime.LaneRuntimeError) as ctx:
            self.run_capture(CHILD_OK, run_dir=link)
        self.assertEqual(str(ctx.exception), "owned_capture_run_dir_unavailable")
        self.assertEqual(os.listdir(real), [])

    def test_symlinked_layout_names_refuse(self):
        run_dir = Path(self.run_dir)
        outside = tempfile.mkdtemp(prefix="owned-capture-outside-")
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (run_dir / "logs").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(lane_runtime.LaneRuntimeError) as ctx:
            self.run_capture(CHILD_OK, run_dir=self.run_dir)
        self.assertEqual(str(ctx.exception), "owned_capture_directory_unavailable")
        self.assertEqual(os.listdir(outside), [])

    def test_symlinked_result_file_refuses(self):
        run_dir = Path(self.run_dir)
        (run_dir / "logs").mkdir(mode=0o700)
        (run_dir / "output").mkdir(mode=0o700)
        target = run_dir / "smuggled.json"
        target.write_bytes(b"old")
        (run_dir / "output" / "result.json").symlink_to(target)
        with self.assertRaises(lane_runtime.LaneRuntimeError) as ctx:
            self.run_capture(CHILD_OK, run_dir=self.run_dir)
        self.assertEqual(str(ctx.exception), "owned_capture_file_exists")
        self.assertEqual(target.read_bytes(), b"old")

    def test_option_pairing_and_schema_validation_refuse_before_spawn(self):
        with self.assertRaises(lane_runtime.LaneRuntimeConfigError) as ctx:
            self.run_capture(CHILD_OK, run_dir=self.run_dir, schema=None)
        self.assertEqual(str(ctx.exception), "owned_capture_options_incomplete")
        for bad, code in (
            ("{not json", "owned_capture_result_schema_invalid"),
            ("[1,2]", "owned_capture_result_schema_invalid"),
            (json.dumps({"type": "object"}) * 20000,
             "owned_capture_result_schema_too_large"),
        ):
            with self.assertRaises(lane_runtime.LaneRuntimeConfigError) as ctx:
                self.run_capture(CHILD_OK, run_dir=self.run_dir, schema=bad)
            self.assertEqual(str(ctx.exception), code)
        self.assertFalse((Path(self.run_dir) / "logs").exists())
        self.assertIsNone(lane_runtime._EXECUTION_OWNER)

    def test_pre_collection_failure_keeps_empty_files_and_closes_fds(self):
        owner = None
        with mock.patch.object(lane_runtime, "_set_current",
                               side_effect=lane_runtime.LaneRuntimeError("busy")):
            with self.assertRaises(lane_runtime.LaneRuntimeError):
                lane_runtime.begin_owned_process(
                    CHILD_SLEEP, timeout=10, label="test-run",
                    receipt_path=self.receipt_path,
                    owned_capture_run_dir=self.run_dir,
                    owned_capture_result_schema_json=SCHEMA_JSON)
        run_dir = Path(self.run_dir)
        # The run happened: exclusive empty files stay bound to this run_dir.
        for rel in ("logs/stdout.json", "logs/stderr.log", "output/result.json"):
            path = run_dir / rel
            self.assertTrue(path.is_file(), rel)
            self.assertEqual(path.read_bytes(), b"")
        owner = lane_runtime._EXECUTION_OWNER
        self.assertIsNotNone(owner)
        reservation = getattr(owner, "_capture_reservation", None)
        self.assertIsNotNone(reservation)
        self.assertTrue(reservation._closed)
        with self.assertRaises(lane_runtime.LaneRuntimeError) as ctx:
            lane_runtime.validate_owned_capture_live(owner)
        self.assertEqual(str(ctx.exception), "busy")  # stored original failure

    def test_start_error_rolls_back_created_names(self):
        fresh = self._make_run_dir()
        with self.assertRaises(lane_runtime.OwnedProcessStartError) as ctx:
            self.run_capture(["/nonexistent/no-such-binary-xyz"], run_dir=fresh)
        self.assertEqual(ctx.exception.error_number, 2)
        self.assertFalse((Path(fresh) / "logs").exists())
        self.assertFalse((Path(fresh) / "output").exists())
        self.assertIsNone(lane_runtime._EXECUTION_OWNER)


class UnqualifiedCaptureTests(OwnedCaptureCase):

    def test_overcap_bounds_file_and_keeps_full_stream_hash(self):
        result = self.run_capture(CHILD_BIG, run_dir=self.run_dir, limit=64)
        self.assertEqual(result.returncode, 0)
        expected_full = b"y" * 200 + b"\n"
        block = self._capture_block(self._receipt())
        self.assertTrue(block["stdout"]["overcap"])
        self.assertFalse(block["stdout_file_complete"])
        self.assertTrue(result.stdout_truncated)
        self.assertLessEqual(len(result.stdout), 64 + len(result.stdout))
        self.assertEqual(block["stdout"]["file_bytes"], 64)
        # full-stream hash vs bounded file distinction is preserved
        self.assertEqual(block["stdout"]["stream_bytes"], 201)
        self.assertEqual(block["stdout"]["stream_sha256"],
                         hashlib.sha256(expected_full).hexdigest())
        self.assertNotEqual(block["stdout"]["file_sha256"],
                            block["stdout"]["stream_sha256"])
        self.assertEqual(block["result"]["state"], "not_published")
        self.assertEqual(block["result"]["reason"], "capture_unqualified")
        self.assertEqual(
            (Path(self.run_dir) / "output" / "result.json").read_bytes(), b"")
        self.assertEqual(result.structured_result, None)
        self.assertFalse(lane_runtime.cleanup_receipt_is_proven(result.cleanup))
        self.assertEqual(result.cleanup["status"], "output_capture_unproven")
        self.assertIsNone(lane_runtime._EXECUTION_OWNER)

    def test_write_failure_keeps_draining_without_deadlock(self):
        owner = lane_runtime.begin_owned_process(
            CHILD_SLOW_STREAM, timeout=20, label="test-run",
            receipt_path=self.receipt_path,
            owned_capture_run_dir=self.run_dir,
            owned_capture_result_schema_json=SCHEMA_JSON)
        captured_fd = owner._capture_reservation.files["stdout"].fd

        real_write_all = lane_runtime._write_all

        def failing_write_all(fd, payload):
            if fd == captured_fd:
                raise OSError(28, "No space left on device")
            return real_write_all(fd, payload)

        with mock.patch.object(lane_runtime, "_write_all", failing_write_all):
            result = lane_runtime.finish_owned_process(owner)
        self.assertEqual(result.returncode, 0)
        # the pipe stayed drained for the full stream
        self.assertEqual(len(result.stdout), 20 * 1001)
        block = self._capture_block(self._receipt())
        self.assertEqual(block["stdout"]["error_code"], "owned_capture_write_failed")
        self.assertFalse(block["stdout_file_complete"])
        self.assertEqual(block["result"]["reason"], "capture_unqualified")
        self.assertEqual(
            (Path(self.run_dir) / "output" / "result.json").read_bytes(), b"")
        self.assertFalse(lane_runtime.cleanup_receipt_is_proven(result.cleanup))

    def test_replaced_inode_during_run_unqualifies(self):
        stderr_path = Path(self.run_dir) / "logs" / "stderr.log"
        originals = {}

        def replace_mid_run():
            # fires while the child is still streaming
            for _ in range(200):
                if stderr_path.exists():
                    break
                time.sleep(0.01)
            info = os.stat(stderr_path)
            originals["identity"] = (info.st_dev, info.st_ino)
            stderr_path.unlink()
            fd = os.open(stderr_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.write(fd, b"smuggled\n")
            os.close(fd)
            kept = os.stat(stderr_path)
            self.assertNotEqual((kept.st_dev, kept.st_ino), originals["identity"])

        timer = threading.Timer(0.15, replace_mid_run)
        timer.start()
        self.addCleanup(timer.join, 10)
        result = self.run_capture(CHILD_SLOW_STREAM, run_dir=self.run_dir)
        self.assertEqual(result.returncode, 0)
        block = self._capture_block(self._receipt())
        self.assertIn(block["stderr"]["error_code"],
                      ("owned_capture_path_replaced", "owned_capture_identity_changed"))
        self.assertFalse(block["stderr_file_complete"])
        self.assertEqual(block["result"]["reason"], "capture_unqualified")
        self.assertFalse(lane_runtime.cleanup_receipt_is_proven(result.cleanup))
        self.assertEqual(
            (Path(self.run_dir) / "output" / "result.json").read_bytes(), b"")

    def test_fsync_failure_at_seal_unqualifies(self):
        owner = lane_runtime.begin_owned_process(
            CHILD_OK, timeout=20, label="test-run",
            receipt_path=self.receipt_path,
            owned_capture_run_dir=self.run_dir,
            owned_capture_result_schema_json=SCHEMA_JSON)
        captured_fd = owner._capture_reservation.files["stdout"].fd
        real_fsync = os.fsync

        def failing_fsync(fd):
            if fd == captured_fd:
                raise OSError(5, "Input/output error")
            return real_fsync(fd)

        with mock.patch.object(os, "fsync", failing_fsync):
            result = lane_runtime.finish_owned_process(owner)
        self.assertEqual(result.returncode, 0)
        block = self._capture_block(self._receipt())
        self.assertEqual(block["stdout"]["error_code"], "owned_capture_fsync_failed")
        self.assertFalse(block["stdout_file_complete"])
        self.assertEqual(block["result"]["reason"], "capture_unqualified")
        self.assertFalse(lane_runtime.cleanup_receipt_is_proven(result.cleanup))

    def test_missing_eof_on_uncertain_collector_retains_resources(self):
        reservation = lane_runtime._OwnedCaptureReservation.create(
            self.run_dir, result_schema_json=SCHEMA_JSON, limit_bytes=1_048_576)
        self.addCleanup(reservation.close_fds_only)

        class BlockingStream:
            def __init__(self):
                self.chunks = queue.Queue()
                self.closed = False

            def read(self, _limit):
                item = self.chunks.get()
                if item is None:
                    return b""
                return item

            def close(self):
                self.closed = True

        stdout_stream = BlockingStream()
        stdout_collector = lane_runtime._BoundedStreamCollector(
            stdout_stream, 1_048_576, "stdout",
            capture_file=reservation.files["stdout"])
        stdout_collector.capture_file.note_streaming()
        stdout_collector.start()
        stdout_stream.chunks.put(b"hello")
        time.sleep(0.1)

        stderr_collector = lane_runtime._BoundedStreamCollector(
            io.BytesIO(b""), 1_048_576, "stderr",
            capture_file=reservation.files["stderr"])
        stderr_collector.capture_file.note_streaming()

        cleanup = {"status": "terminated", "identity_verified": True,
                   "census_proven": True, "residual_count": 0}
        block, structured = reservation.finalize(
            stdout_collector, stderr_collector,
            cleanup=cleanup, returncode=0, timed_out=False)
        self.assertIsNone(structured)
        self.assertEqual(block["stdout"]["error_code"], "owned_capture_collector_live")
        self.assertFalse(block["stdout_file_complete"])
        self.assertFalse(block["stderr_file_complete"])
        self.assertEqual(block["result"]["reason"], "capture_unqualified")
        # retained resources: fds of the live collector's file stay open
        self.assertIsNotNone(reservation.files["stdout"].fd)
        os.fstat(reservation.files["stdout"].fd)
        self.assertFalse(reservation._closed)
        # stderr sealed but never saw EOF, so it cannot qualify either
        self.assertEqual(block["stderr"]["error_code"], None)
        self.assertFalse(block["stderr"]["complete"])
        stdout_stream.chunks.put(None)
        stdout_collector._thread.join(5)
        self.assertTrue(stdout_collector._thread.is_alive() is False)

    def test_file_flags_flip_existing_cleanup_marking(self):
        cleanup = {"status": "not_needed", "identity_verified": True,
                   "census_proven": True, "residual_count": 0}
        flipped = lane_runtime._mark_stream_state_unproven(
            cleanup, stdout_complete=True, stderr_complete=True,
            stdin_complete=True, stdout_error=None, stderr_error=None,
            stdin_error=None, stdout_file_complete=False,
            stderr_file_complete=True)
        self.assertEqual(flipped["status"], "output_capture_unproven")
        self.assertFalse(lane_runtime.cleanup_receipt_is_proven(flipped))
        self.assertIs(flipped["stdout_file_capture_complete"], False)
        neutral = lane_runtime._mark_stream_state_unproven(
            cleanup, stdout_complete=True, stderr_complete=True,
            stdin_complete=True, stdout_error=None, stderr_error=None,
            stdin_error=None)
        self.assertNotIn("stdout_file_capture_complete", neutral)
        self.assertTrue(lane_runtime.cleanup_receipt_is_proven(neutral))


class ResultPublicationTests(OwnedCaptureCase):

    def test_parse_bad_result_leaves_file_empty_but_cleanup_proven(self):
        result = self.run_capture(CHILD_BAD_PARSE, run_dir=self.run_dir)
        self.assertEqual(result.returncode, 0)
        self.assertIsNone(result.structured_result)
        block = self._capture_block(self._receipt())
        self.assertTrue(block["stdout_file_complete"])
        self.assertEqual(block["result"]["state"], "not_published")
        self.assertTrue(block["result"]["reason"].startswith("parse_refused:"))
        self.assertEqual(
            (Path(self.run_dir) / "output" / "result.json").read_bytes(), b"")
        self.assertTrue(lane_runtime.cleanup_receipt_is_proven(result.cleanup))

    def test_nonzero_exit_and_timeout_stay_failures(self):
        result = self.run_capture(CHILD_NONZERO, run_dir=self.run_dir)
        self.assertEqual(result.returncode, 3)
        block = self._capture_block(self._receipt())
        self.assertEqual(block["result"]["reason"], "nonzero_exit")
        self.assertEqual(
            (Path(self.run_dir) / "output" / "result.json").read_bytes(), b"")

        fresh = self._make_run_dir()
        result = self.run_capture(CHILD_SLEEP, run_dir=fresh, timeout=0.5)
        self.assertTrue(result.timed_out)
        block = self._capture_block(self._receipt())
        self.assertEqual(block["result"]["reason"], "timed_out")
        self.assertEqual(
            (Path(self.run_dir) / "output" / "result.json").read_bytes(), b"")
        self.assertIsNone(result.structured_result)

    def test_cancel_keeps_empty_result_and_proven_files(self):
        owner = lane_runtime.begin_owned_process(
            CHILD_SLEEP, timeout=30, label="test-run",
            receipt_path=self.receipt_path,
            owned_capture_run_dir=self.run_dir,
            owned_capture_result_schema_json=SCHEMA_JSON)

        async def drive():
            finisher = lane_runtime.start_owned_process_finisher(owner)
            await asyncio.sleep(0.2)
            receipt = lane_runtime.cancel_exact_owned_process(
                owner, label=owner.label,
                process_identity=owner.process_identity, reason="test-cancel")
            result = await finisher
            return result, receipt

        result, cancel_receipt = asyncio.run(drive())
        self.assertEqual(cancel_receipt["status"], "terminated")
        self.assertTrue(result.cleanup["census_proven"])
        self.assertNotEqual(result.returncode, 0)
        block = self._capture_block(self._receipt())
        self.assertEqual(block["result"]["state"], "not_published")
        self.assertEqual(block["result"]["reason"], "cancelled")
        self.assertEqual(
            (Path(self.run_dir) / "output" / "result.json").read_bytes(), b"")
        self.assertTrue(lane_runtime.cleanup_receipt_is_proven(result.cleanup))

    def test_result_identity_guard_preserves_unknown_file(self):
        reservation = lane_runtime._OwnedCaptureReservation.create(
            self.run_dir, result_schema_json=SCHEMA_JSON, limit_bytes=1_048_576)
        self.addCleanup(reservation.close_fds_only)
        result_file = Path(self.run_dir) / "output" / "result.json"
        fd = reservation.files["result"].fd
        os.close(fd)
        # simulate a replaced, non-empty result inode after the run began
        result_file.unlink()
        result_file.write_bytes(b"not ours")
        reservation.files["result"].fd = os.open(
            str(result_file), os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)

        # real captured stdout bytes so publication is actually reached
        stdout_payload = b'{"structured_output": {"summary": "ok"}}'
        stdout_file = Path(self.run_dir) / "logs" / "stdout.json"
        with open(stdout_file, "wb") as handle:
            handle.write(stdout_payload)
        stdout_collector = lane_runtime._BoundedStreamCollector(
            io.BytesIO(stdout_payload), 1_048_576, "stdout",
            capture_file=reservation.files["stdout"])
        stdout_collector.eof = True
        stdout_collector.total_bytes = len(stdout_payload)
        stdout_collector.capture_hash = hashlib.sha256(stdout_payload)
        stderr_collector = lane_runtime._BoundedStreamCollector(
            io.BytesIO(b""), 1_048_576, "stderr",
            capture_file=reservation.files["stderr"])
        stderr_collector.eof = True
        stderr_collector.total_bytes = 0
        stderr_collector.capture_hash = hashlib.sha256()
        cleanup = {"status": "not_needed", "identity_verified": True,
                   "census_proven": True, "residual_count": 0}
        block, structured = reservation.finalize(
            stdout_collector, stderr_collector,
            cleanup=cleanup, returncode=0, timed_out=False)
        self.assertIsNone(structured)
        self.assertEqual(block["result"]["reason"], "result_identity_changed")
        self.assertEqual(result_file.read_bytes(), b"not ours")

    def test_result_readback_mismatch_preserves_failed_original_bytes(self):
        owner = lane_runtime.begin_owned_process(
            CHILD_OK, timeout=20, label="test-run",
            receipt_path=self.receipt_path,
            owned_capture_run_dir=self.run_dir,
            owned_capture_result_schema_json=SCHEMA_JSON)
        result_fd = owner._capture_reservation.files["result"].fd
        real_write_all = lane_runtime._write_all

        def short_write_all(fd, payload):
            if fd == result_fd:
                return real_write_all(fd, payload[:-1])
            return real_write_all(fd, payload)

        with mock.patch.object(lane_runtime, "_write_all", short_write_all):
            result = lane_runtime.finish_owned_process(owner)
        self.assertEqual(result.returncode, 0)
        block = self._capture_block(self._receipt())
        self.assertEqual(block["result"]["reason"], "result_write_failed")
        self.assertIsNone(result.structured_result)
        self.assertTrue((Path(self.run_dir) / "output" / "result.json").read_bytes())
        self.assertFalse(result.cleanup_proven)


class PinnedStartTests(OwnedCaptureCase):

    def begin_sleeping(self):
        owner = lane_runtime.begin_owned_process(
            CHILD_SLEEP, timeout=30, label="test-run",
            receipt_path=self.receipt_path,
            owned_capture_run_dir=self.run_dir,
            owned_capture_result_schema_json=SCHEMA_JSON)
        self.addCleanup(self._terminate_owner, owner)
        return owner

    def _terminate_owner(self, owner):
        try:
            if owner.result is None and owner.failure is None:
                lane_runtime.abort_owned_process(owner, RuntimeError("test-end"))
        except (lane_runtime.LaneRuntimeError, RuntimeError):
            pass

    def test_fixed_paths_and_live_validator(self):
        owner = self.begin_sleeping()
        paths = lane_runtime.owned_capture_paths(owner)
        self.assertEqual(paths, {
            "stdout_path": self.run_dir + "/logs/stdout.json",
            "stderr_path": self.run_dir + "/logs/stderr.log",
            "result_path": self.run_dir + "/output/result.json",
        })
        live = lane_runtime.validate_owned_capture_live(owner)
        self.assertEqual(live["schema"], "mastermind.local_owned_capture_files.v1")
        described = owner.owned_capture["files"]
        for key, path_key in (("stdout", "stdout_path"),
                              ("stderr", "stderr_path"),
                              ("result", "result_path")):
            entry = live["files"][path_key]
            self.assertEqual(entry["path"], paths[path_key])
            self.assertEqual(entry["device"], described[key]["device"])
            self.assertEqual(entry["inode"], described[key]["inode"])
            self.assertEqual(entry["size"], 0)
            info = os.stat(entry["path"])
            self.assertEqual((info.st_dev, info.st_ino),
                             (entry["device"], entry["inode"]))

    def test_validator_ignores_path_strings_and_requires_actual_files(self):
        owner = self.begin_sleeping()
        # strings alone never satisfy the validator: corrupt them, still live
        owner._original_capture_paths = {"stdout_path": "/bogus/x"}
        live = lane_runtime.validate_owned_capture_live(owner)
        self.assertEqual(live["files"]["stdout_path"]["path"],
                         self.run_dir + "/logs/stdout.json")
        # a replaced inode at a pinned path is refused
        stdout_file = Path(self.run_dir) / "logs" / "stdout.json"
        stdout_file.unlink()
        stdout_file.write_bytes(b"replaced")
        with self.assertRaises(lane_runtime.LaneRuntimeError) as ctx:
            lane_runtime.validate_owned_capture_live(owner)
        self.assertEqual(str(ctx.exception), "owned_capture_identity_changed")

    def test_validator_requires_private_mode_and_owner(self):
        owner = self.begin_sleeping()
        stderr_file = Path(self.run_dir) / "logs" / "stderr.log"
        os.chmod(stderr_file, 0o644)
        with self.assertRaises(lane_runtime.LaneRuntimeError) as ctx:
            lane_runtime.validate_owned_capture_live(owner)
        self.assertEqual(str(ctx.exception), "owned_capture_identity_changed")
        os.chmod(stderr_file, 0o600)
        lane_runtime.validate_owned_capture_live(owner)

    def test_abort_after_begin_seals_files_and_keeps_result_empty(self):
        owner = self.begin_sleeping()
        with self.assertRaises(RuntimeError):
            lane_runtime.abort_owned_process(owner, RuntimeError("planned-stop"))
        self.assertIsNotNone(owner.failure)
        self.assertIsNone(owner.result)
        block = self._capture_block(self._receipt())
        self.assertTrue(block["stdout_file_complete"])
        self.assertEqual(block["result"]["reason"], "nonzero_exit")
        self.assertEqual(
            (Path(self.run_dir) / "output" / "result.json").read_bytes(), b"")

    def test_start_path_shape_mirror(self):
        """Mirror of the START assembler's capture-path shape requirements."""
        owner = self.begin_sleeping()
        paths = lane_runtime.owned_capture_paths(owner)
        run_dir = self.run_dir
        self.assertEqual(set(paths),
                         {"stdout_path", "stderr_path", "result_path"})
        for key, value in paths.items():
            self.assertTrue(value.startswith("/"))
            self.assertNotIn("..", value.split("/"))
            self.assertNotEqual(value, run_dir)
            self.assertTrue(value.startswith(run_dir + "/"),
                            f"{key} not strictly under run_dir")
        self.assertEqual(
            (Path(run_dir) / "output" / "result.json").stat().st_size, 0)
        lane_runtime.validate_owned_capture_live(owner)


class SchemaBoundReceiptTests(OwnedCaptureCase):

    def test_schema_digest_is_bound_to_the_invocation_receipt(self):
        schema = json.dumps({"type": "object",
                             "required": ["summary"],
                             "properties": {"summary": {"type": "string"}}})
        result = self.run_capture(CHILD_OK, run_dir=self.run_dir, schema=schema)
        block = self._capture_block(self._receipt())
        self.assertEqual(block["result_schema_sha256"],
                         hashlib.sha256(schema.encode()).hexdigest())
        self.assertEqual(result.structured_result,
                         {"summary": "ok", "count": 1})
        # provider usage stays an observation, never result content
        self.assertEqual(
            (Path(self.run_dir) / "output" / "result.json").read_bytes(),
            canonical({"summary": "ok", "count": 1}))
        self.assertNotIn("usage", result.structured_result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
