"""Inert regressions at the actual public owned-process creation boundary.

The default target is the adjacent draft. Set FABRIC_OWNED_START_RUNTIME to
the original source to demonstrate the negative baseline with the same tests.
Only subprocess.Popen is mocked; no child, lease, provider, signal cleanup,
receipt, or native host operation is created by these tests.
"""
from __future__ import annotations

from collections import UserList
from contextlib import contextmanager, ExitStack
import errno
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import traceback
import unittest
from unittest.mock import patch
import uuid


DEFAULT_RUNTIME = Path(__file__).resolve().parents[1] / "candidate/lane_runtime.py"
RUNTIME_PATH = Path(os.environ.get("FABRIC_OWNED_START_RUNTIME", DEFAULT_RUNTIME))
EXECUTABLE = "/synthetic-private-bin/owned-command"
COMMAND = [EXECUTABLE, "synthetic-private-argument"]


@contextmanager
def isolated_runtime():
    """Load the exact file with its own classes, restoring the module registry."""
    name = "_owned_process_boundary_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, RUNTIME_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("runtime fixture could not be imported")
    module = importlib.util.module_from_spec(spec)
    previous_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        with patch.dict(sys.modules, {name: module}):
            spec.loader.exec_module(module)
            yield module
    finally:
        sys.dont_write_bytecode = previous_bytecode


class MissingSubclass(FileNotFoundError):
    pass


class DeniedSubclass(PermissionError):
    pass


class TextSubclass(str):
    pass


class ListSubclass(list):
    pass


class TupleSubclass(tuple):
    pass


def missing(filename=EXECUTABLE, *, filename2=None):
    return FileNotFoundError(errno.ENOENT, "synthetic private failure", filename,
                             None, filename2)


def plain_oserror_with_enoent():
    # OSError(ENOENT, ...) itself specializes to FileNotFoundError in CPython.
    error = OSError("synthetic parent failure")
    error.errno = errno.ENOENT
    error.filename = EXECUTABLE
    return error


# Every row is a distinct public-boundary test, never a predicate-only test.
UNPROVEN_CASES = (
    ("parent_eio", lambda: OSError(errno.EIO, "parent read failure"), COMMAND, False),
    ("parent_eio_matching_filename", lambda: OSError(errno.EIO, "parent close failure", EXECUTABLE), COMMAND, False),
    ("parent_ebadf", lambda: OSError(errno.EBADF, "parent fd failure"), COMMAND, False),
    ("bare_oserror", lambda: OSError("parent failure"), COMMAND, False),
    ("exact_oserror_enoent", plain_oserror_with_enoent, COMMAND, False),
    ("missing_wrong_errno", lambda: FileNotFoundError(errno.EACCES, "failure", EXECUTABLE), COMMAND, False),
    ("denied_wrong_errno", lambda: PermissionError(errno.ENOENT, "failure", EXECUTABLE), COMMAND, False),
    ("permission_eperm", lambda: PermissionError(errno.EPERM, "failure", EXECUTABLE), COMMAND, False),
    ("missing_subclass", lambda: MissingSubclass(errno.ENOENT, "failure", EXECUTABLE), COMMAND, False),
    ("denied_subclass", lambda: DeniedSubclass(errno.EACCES, "failure", EXECUTABLE), COMMAND, False),
    ("filename_missing", lambda: missing(None), COMMAND, False),
    ("filename_empty", lambda: missing(""), COMMAND, False),
    ("filename_different", lambda: missing("/synthetic-private-cwd"), COMMAND, False),
    ("filename_second", lambda: missing(filename2="/synthetic-second-path"), COMMAND, False),
    ("filename_bytes", lambda: missing(EXECUTABLE.encode()), COMMAND, False),
    ("filename_subclass", lambda: missing(TextSubclass(EXECUTABLE)), COMMAND, False),
    ("shell_enabled", missing, COMMAND, True),
    ("shell_zero", missing, COMMAND, 0),
    ("shell_none", missing, COMMAND, None),
    ("command_string", missing, EXECUTABLE, False),
    ("command_bytes", missing, EXECUTABLE.encode(), False),
    ("command_empty_list", missing, [], False),
    ("command_empty_tuple", missing, (), False),
    ("command_list_subclass", missing, ListSubclass(COMMAND), False),
    ("command_tuple_subclass", missing, TupleSubclass(COMMAND), False),
    ("command_other_sequence", missing, UserList(COMMAND), False),
    ("executable_string_subclass", missing, [TextSubclass(EXECUTABLE)], False),
    ("argument_string_subclass", missing, [EXECUTABLE, TextSubclass("argument")], False),
    ("argument_bytes", missing, [EXECUTABLE, b"argument"], False),
    ("argument_pathlike", missing, [EXECUTABLE, Path("argument")], False),
)


class CompletedPopen:
    """An already-completed command or a synthetic completed census process."""
    def __init__(self, args, *, returncode=0, census=False):
        self.args = args
        self.pid = 2_147_483_647
        self.returncode = returncode
        self.stdin = None
        self.stdout = io.BytesIO(b"owned stdout\n")
        self.stderr = io.BytesIO(b"owned stderr\n")
        self.census = census

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def communicate(self, input=None, timeout=None):
        if not self.census:
            raise AssertionError("the owned path must use its real stream collectors")
        # A zombie row is ignored without consulting or signaling any real PID.
        return f"{self.pid} Z\n", ""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stdout.close()
        self.stderr.close()


class OwnedProcessStartBoundaryTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.runtime = stack.enter_context(isolated_runtime())

    def failure(self, error, command=COMMAND, shell=False, **kwargs):
        original_popen = subprocess.Popen
        with patch.object(self.runtime.subprocess, "Popen", side_effect=error) as popen:
            try:
                self.runtime.run_owned_process(command, timeout=1, shell=shell, **kwargs)
            except self.runtime.LaneRuntimeError as observed:
                result = observed
            else:
                self.fail("Popen failure unexpectedly returned a process result")
            popen.assert_called_once()
            self.assertIs(popen.call_args.args[0], command)
            self.assertIs(popen.call_args.kwargs["shell"], shell)
        self.assertIs(subprocess.Popen, original_popen)
        self.assertIsNone(self.runtime._CURRENT_PROCESS)
        self.assertIsNone(result.__cause__)
        self.assertTrue(result.__suppress_context__)
        return result

    def assert_unproven(self, error, command=COMMAND, shell=False, **kwargs):
        result = self.failure(error, command, shell, **kwargs)
        self.assertIs(type(result), self.runtime.LaneRuntimeError)
        self.assertEqual(result.args, ("owned_process_start_unproven",))
        self.assertFalse(hasattr(result, "error_number"))
        return result

    def test_diagnostics_are_bounded_for_qualified_failure(self):
        self.check_diagnostics(qualified=True)

    def test_diagnostics_are_bounded_for_unproven_failure(self):
        self.check_diagnostics(qualified=False)

    def check_diagnostics(self, *, qualified):
        markers = ("PRIVATE_EXECUTABLE_19", "PRIVATE_ARG_29", "PRIVATE_ENV_39",
                   "PRIVATE_CWD_49", "PRIVATE_OSERROR_59", "PRIVATE_SECOND_69")
        command = ["/" + markers[0], markers[1]]
        arguments = {"cwd": "/" + markers[3], "env": {"TEST_TOKEN": markers[2]}}
        if qualified:
            error = FileNotFoundError(errno.ENOENT, markers[4], command[0])
            result = self.failure(error, command, **arguments)
            self.assertIs(type(result), self.runtime.OwnedProcessStartError)
            self.assertEqual(result.args, ("owned_process_exec_not_started",))
            self.assertEqual(result.error_number, errno.ENOENT)
        else:
            error = OSError(errno.EIO, markers[4], command[0], None, markers[5])
            result = self.assert_unproven(error, command, **arguments)
        rendered = str(result) + repr(result) + "".join(traceback.format_exception(result))
        for marker in markers:
            self.assertNotIn(marker, rendered)
        self.assertLess(len(str(result)), 64)

    def check_completed_process(self, returncode):
        # Fail before entering the runtime if this reserved synthetic PID exists.
        with self.assertRaises(ProcessLookupError):
            os.getpgid(2_147_483_647)
        process = CompletedPopen(COMMAND, returncode=returncode)

        def construct(args, **kwargs):
            if args is COMMAND:
                return process
            self.assertEqual(args, ["/bin/ps", "-axo", "pid=,stat="])
            return CompletedPopen(args, census=True)

        with patch.object(self.runtime.subprocess, "Popen", side_effect=construct) as popen:
            result = self.runtime.run_owned_process(COMMAND, timeout=1)
        self.assertEqual(popen.call_count, 2)
        first = popen.call_args_list[0]
        self.assertEqual(first.kwargs, {
            "cwd": None, "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
            "shell": False, "executable": None, "env": None,
            "close_fds": True, "start_new_session": True,
        })
        self.assertIs(type(result), self.runtime.OwnedProcessResult)
        self.assertEqual(result.returncode, returncode)
        self.assertEqual((result.pid, result.pgid), (process.pid, process.pid))
        self.assertEqual((result.stdout, result.stderr), ("owned stdout\n", "owned stderr\n"))
        self.assertEqual((result.stdout_bytes, result.stderr_bytes), (13, 13))
        self.assertFalse(result.timed_out)
        self.assertFalse(result.stdout_truncated or result.stderr_truncated)
        self.assertTrue(result.cleanup_proven)
        self.assertEqual(result.cleanup["status"], "not_needed")
        self.assertEqual(result.cleanup["residual_count"], 0)
        self.assertFalse(result.cleanup["sigterm_sent"] or result.cleanup["sigkill_sent"])
        self.assertTrue(process.stdout.closed and process.stderr.closed)
        self.assertIsNone(self.runtime._CURRENT_PROCESS)

    def test_completed_zero_exit_preserves_success_path(self):
        self.check_completed_process(0)

    def test_completed_nonzero_exit_preserves_success_path(self):
        self.check_completed_process(23)


def unproven_test(error_factory, command, shell):
    def test(self):
        self.assert_unproven(error_factory(), command, shell)
    return test


for case_name, error_factory, command, shell in UNPROVEN_CASES:
    setattr(OwnedProcessStartBoundaryTests, "test_unproven_" + case_name,
            unproven_test(error_factory, command, shell))


def qualified_test(command_type, error_type, error_number):
    def test(self):
        command = command_type(COMMAND)
        observed = self.failure(error_type(error_number, "synthetic exec error", command[0]), command)
        self.assertIs(type(observed), self.runtime.OwnedProcessStartError)
        self.assertEqual(observed.args, ("owned_process_exec_not_started",))
        self.assertEqual(observed.error_number, error_number)
    return test


for command_type in (list, tuple):
    for error_type, error_number in ((FileNotFoundError, errno.ENOENT),
                                     (PermissionError, errno.EACCES)):
        name = "test_qualified_" + command_type.__name__ + "_" + error_type.__name__
        setattr(OwnedProcessStartBoundaryTests, name,
                qualified_test(command_type, error_type, error_number))


class ImportIsolationTests(unittest.TestCase):
    def test_runtime_import_restores_sys_modules_and_bytecode_setting(self):
        before = dict(sys.modules)
        before_bytecode = sys.dont_write_bytecode
        with isolated_runtime() as runtime:
            self.assertIs(sys.modules[runtime.__name__], runtime)
            self.assertIsNone(runtime._CURRENT_PROCESS)
        self.assertEqual(dict(sys.modules), before)
        self.assertIs(sys.dont_write_bytecode, before_bytecode)


if __name__ == "__main__":
    unittest.main(verbosity=2)
