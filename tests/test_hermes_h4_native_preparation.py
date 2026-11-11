"""Recorded owner refusal -> MCP contract; no provider, reservation or dispatch."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_source(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bridge = load_source("h4_capacity_bridge", "integrations/hermes_omh/capacity_bridge.py")
preflight = load_source("h4_preflight",
    "integrations/hermes_application_fabric/qualification/qualify_live_preimages.py")
CANONICAL = ("NONE reason=no eligible remote mode on requested host blockers="
             "m1:cpu+disk+lane-ceiling+load+reachable+tools,"
             "ubuntu4:automatic-qualification\n")


class RefusalContractTests(unittest.TestCase):
    def call(self, diagnostic, returncode=75, stdout=""):
        calls = []

        def owner(argv, **kwargs):
            calls.append((argv, kwargs))
            if isinstance(diagnostic, bytes):
                kwargs["stderr"].buffer.write(diagnostic)
            else:
                kwargs["stderr"].write(diagnostic)
            kwargs["stderr"].flush()
            return SimpleNamespace(returncode=returncode, stdout=stdout)

        output = io.StringIO()
        with patch.object(bridge, "catalog", return_value={"pools": [{"pool": "minimax"}]}), \
             patch.object(bridge, "FABRIC", Path(__file__)), \
             patch.object(bridge.subprocess, "run", side_effect=owner), \
             contextlib.redirect_stdout(output):
            bridge.handle({"jsonrpc": "2.0", "id": 19, "method": "tools/call",
                           "params": {"name": "fabric_route_preview",
                                      "arguments": {"task_class": "census"}}})
        return json.loads(output.getvalue()), calls

    def test_recorded_owner_reason_survives_real_mcp_response(self):
        response, calls = self.call(CANONICAL)
        self.assertEqual(response["id"], 19)
        self.assertEqual(response["result"], {
            "isError": True,
            "content": [{"type": "text", "text":
                         "FABRIC_PREVIEW_NO_ELIGIBLE_REMOTE_HOST"}],
        })
        self.assertEqual(len(calls), 1)
        argv, options = calls[0]
        self.assertEqual(argv[2], "preview")
        self.assertNotIn("request", argv)
        self.assertEqual(options["stdin"], subprocess.DEVNULL)
        self.assertEqual(options["timeout"], 15)
        self.assertNotIn("m1", json.dumps(response))
        self.assertNotIn("ubuntu4", json.dumps(response))

    def test_unknown_untrusted_and_truncated_diagnostics_stay_closed(self):
        samples = (
            "", "SECRET_SENTINEL", b"\xffSECRET_SENTINEL",
            "NONE reason=unknown SECRET_SENTINEL",
            CANONICAL + "SECRET_SENTINEL",
            CANONICAL.replace("cpu", "SECRET_SENTINEL"),
            CANONICAL.replace("ubuntu4", "/private/SECRET_SENTINEL"),
            CANONICAL.replace("cpu+disk", "cpu+cpu"),
            CANONICAL.replace("m1:", "m1:SECRET_SENTINEL+"),
            "x" * 8193, CANONICAL + "x" * 8193,
        )
        for raw in samples:
            with self.subTest(diagnostic_length=len(raw)):
                response, calls = self.call(raw)
                encoded = json.dumps(response)
                self.assertEqual(response["result"]["content"][0]["text"],
                                 "FABRIC_PREVIEW_REFUSED")
                self.assertNotIn("SECRET_SENTINEL", encoded)
                self.assertEqual(len(calls), 1)

    def test_reason_is_not_inferred_from_another_exit_status(self):
        response, calls = self.call(CANONICAL, returncode=1)
        self.assertEqual(response["result"]["content"][0]["text"],
                         "FABRIC_PREVIEW_REFUSED")
        self.assertEqual(len(calls), 1)

    def test_successful_preview_contract_is_preserved(self):
        selected = {"pool": "minimax", "model": "qualified-model",
                    "state": "PREVIEW", "reserved": False}
        response, calls = self.call("SECRET_SENTINEL", 0, json.dumps(selected))
        self.assertFalse(response["result"]["isError"])
        result = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(result, {**selected,
            "proof": "PREVIEW_ONLY_NO_RESERVATION_OR_DISPATCH"})
        self.assertNotIn("SECRET_SENTINEL", json.dumps(response))
        self.assertEqual(len(calls), 1)

    def test_owner_timeout_is_not_retried_or_exposed(self):
        output = io.StringIO()
        with patch.object(bridge, "catalog", return_value={"pools": []}), \
             patch.object(bridge, "FABRIC", Path(__file__)), \
             patch.object(bridge.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired("SECRET_SENTINEL", 15)) as owner, \
             contextlib.redirect_stdout(output):
            bridge.handle({"id": 20, "method": "tools/call",
                           "params": {"name": "fabric_route_preview",
                                      "arguments": {"task_class": "census"}}})
        response = json.loads(output.getvalue())
        self.assertEqual(response["result"]["content"][0]["text"],
                         "FABRIC_PREVIEW_UNAVAILABLE")
        self.assertEqual(owner.call_count, 1)
        self.assertNotIn("SECRET_SENTINEL", output.getvalue())


class NativePreflightSafetyTests(unittest.TestCase):
    def test_live_output_is_refused_before_qualification(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            native = root / "native"
            native.mkdir()
            target = native / "receipt.json"
            args = ["qualify", "--native-root", str(native),
                    "--source-repo", str(root), "--candidate", "a" * 40,
                    "--output", str(target)]
            with patch.object(preflight, "qualify") as qualify, \
                 patch("sys.argv", args), \
                 self.assertRaisesRegex(RuntimeError,
                     "RECEIPT_MUST_BE_OUTSIDE_LIVE_NATIVE_ROOT"):
                preflight.main()
            qualify.assert_not_called()
            self.assertFalse(target.exists())

    def test_native_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            native = root / "native"
            native.mkdir()
            secret = root / "outside"
            secret.write_text("SECRET_SENTINEL")
            (native / "source.py").symlink_to(secret)
            with self.assertRaisesRegex(RuntimeError, "NATIVE_SYMLINK_REFUSED"):
                preflight.read_native(native, "source.py")
            self.assertEqual(secret.read_text(), "SECRET_SENTINEL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
