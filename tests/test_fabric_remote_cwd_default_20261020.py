"""The default cwd belongs to the receiving host, never the controller.

Load only the candidate adapter with isolated import doubles. Intercept request
before provider selection, routing, leases, subprocesses or installed state.
"""
import importlib.util
import io
import pathlib
import sys
import types
import unittest
from unittest import mock


CANDIDATE = (pathlib.Path(__file__).resolve().parents[1]
             / "ops/native_fabric/quota_continuity/candidate/fabric_task.py")


def load_candidate():
    dependencies = (
        "pick", "pool_ledger", "a04_terminal_reconcile",
        "native_completion_reconcile", "native_prestart_reconcile",
        "native_preexec_reconcile", "native_host_review_controller_reconcile",
    )
    spec = importlib.util.spec_from_file_location(
        "fabric_remote_cwd_default_candidate", CANDIDATE
    )
    module = importlib.util.module_from_spec(spec)
    doubles = {name: types.ModuleType(name) for name in dependencies}
    with mock.patch.dict(sys.modules, doubles):
        spec.loader.exec_module(module)
    return module


class RemoteCwdDefaultTests(unittest.TestCase):
    def call_request(self, *options):
        fabric_task = load_candidate()
        with io.TextIOWrapper(io.BytesIO(b"read-only review packet\n"),
                              encoding="utf-8") as data, \
                mock.patch.object(fabric_task, "request", return_value=0) as dispatch, \
                mock.patch.object(sys, "stdin", data), \
                mock.patch.object(fabric_task.os, "getcwd",
                                  return_value="/controller/vendor/dist"), \
                mock.patch.object(fabric_task.subprocess, "run",
                                  side_effect=AssertionError("unexpected subprocess")), \
                mock.patch.object(fabric_task.subprocess, "Popen",
                                  side_effect=AssertionError("unexpected process")):
            result = fabric_task.main([
                "request", "--id", "hermetic-cwd-case",
                "--class", "review", "--stdin", *options
            ])
        self.assertEqual(result, 0)
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(dispatch.call_args.kwargs["stdin_bytes"],
                         b"read-only review packet\n")
        return dispatch.call_args.kwargs

    def test_implicit_cwd_is_literal_receiving_host_home(self):
        self.assertEqual(self.call_request()["cwd"], "~")

    def test_explicit_remote_macro_checkout_is_preserved(self):
        args = self.call_request("--cwd", "~/lanes/repos/macro")
        self.assertEqual(args["cwd"], "~/lanes/repos/macro")

    def test_explicit_absolute_cwd_stays_explicit_for_remote_validation(self):
        args = self.call_request("--cwd", "/receiver/custom/source")
        self.assertEqual(args["cwd"], "/receiver/custom/source")


if __name__ == "__main__":
    unittest.main()
