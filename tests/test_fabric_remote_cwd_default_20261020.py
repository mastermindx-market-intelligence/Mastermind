"""Fabric CLI default CWD belongs to the receiving host, never M2's vendor cwd.

Hermetic tests: intercept request before routing, leasing, subprocesses, or secrets.
"""
import importlib
import io
import pathlib
import sys
import unittest
from unittest import mock


SOURCE = pathlib.Path(__file__).resolve().parents[1] / "ops/native_fabric/quota_continuity/source"
sys.path.insert(0, str(SOURCE))
fabric_task = importlib.import_module("fabric_task")


class RemoteCwdDefaultTests(unittest.TestCase):
    def call_request(self, *options):
        data = io.TextIOWrapper(io.BytesIO(b"read-only review packet\n"), encoding="utf-8")
        with mock.patch.object(fabric_task, "request", return_value=0) as dispatch:
            with mock.patch.object(sys, "stdin", data):
                with mock.patch.object(fabric_task.os, "getcwd",
                                       return_value="/Users/chriswong/desktop-commander/vendor/dist"):
                    result = fabric_task.main([
                        "request", "--id", "hermetic-cwd-case",
                        "--class", "review", "--stdin", *options
                    ])
        self.assertEqual(result, 0)
        self.assertEqual(dispatch.call_count, 1)
        return dispatch.call_args.kwargs

    def test_implicit_cwd_is_literal_receiving_host_home(self):
        args = self.call_request()
        self.assertEqual(args["cwd"], "~")

    def test_explicit_remote_macro_checkout_is_preserved(self):
        args = self.call_request("--cwd", "~/lanes/repos/macro")
        self.assertEqual(args["cwd"], "~/lanes/repos/macro")

    def test_explicit_absolute_cwd_stays_explicit_for_remote_validation(self):
        args = self.call_request("--cwd", "/Users/chriswong/custom/source")
        self.assertEqual(args["cwd"], "/Users/chriswong/custom/source")


if __name__ == "__main__":
    unittest.main()
