"""Host-bound install and real SDK projection tests; no live credentials/Paper."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from paper_direct_test_support import PrivatePython, has_pinned_mcp_sdk

ROOT = Path(__file__).resolve().parents[1] / "integrations/paper_desktop"
HOST = "host-" + "a" * 64


@unittest.skipUnless(has_pinned_mcp_sdk(), "Dedicated mcp==1.30.0 SDK required")
class HostBoundDirectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.python_fixture = PrivatePython()
        cls.python = cls.python_fixture.python

    @classmethod
    def tearDownClass(cls):
        cls.python_fixture.close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve()
        self.binary = self.home / "tunnel-client"
        self.binary.write_text("#!/bin/sh\nexit 0\n")
        self.binary.chmod(0o700)
        spec = importlib.util.spec_from_file_location("bound_direct_fixture", ROOT / "direct_service.py")
        self.svc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.svc)

    def tearDown(self):
        self.tmp.cleanup()

    def stage(self, name="bound", **kwargs):
        options = {"seat_id": "fixture-seat", "host_ref": HOST}
        options.update(kwargs)
        root = self.home / name
        receipt = self.svc.stage(root, python=self.python, tunnel_client=self.binary,
                    source_revision="c" * 40, allow_write=True, allow_prepare=True, **options)
        return root, receipt

    def test_v4_scopes_existing_seat_service_without_new_transport(self):
        root, receipt = self.stage()
        self.assertEqual(receipt["schema"], self.svc.SCHEMA_V4)
        self.assertEqual(self.svc.verify(root), receipt)
        self.assertEqual(self.svc.service_label(receipt), "com.mastermind.paper-direct.business.fixture-seat")
        scope = self.svc.execution_binding(receipt)
        self.assertEqual(scope["host_ref"], HOST)
        self.assertEqual(scope["runtime_revision"], "c" * 40)
        self.assertNotIn(str(root), json.dumps(scope))
        self.assertFalse(receipt["production_acceptance"])
        self.assertFalse(receipt["service_loaded"])
        self.assertEqual(scope, self.svc.execution_binding(self.svc.verify(root)))

    def test_distinct_bundle_and_host_change_scope(self):
        _, first = self.stage()
        _, second = self.stage("other-root")
        self.assertNotEqual(self.svc.execution_binding(first)["service_ref"],
                            self.svc.execution_binding(second)["service_ref"])
        _, third = self.stage("other-host", host_ref="host-" + "e" * 64)
        self.assertNotEqual(self.svc.execution_binding(first)["host_ref"],
                            self.svc.execution_binding(third)["host_ref"])

    def test_host_ref_requires_existing_shape_and_named_seat(self):
        for value in ("m2studio", "https://invalid.example", True, "host-" + "x" * 64):
            with self.subTest(value=value), self.assertRaisesRegex(self.svc.Refusal, "HOST_REFERENCE_REQUIRED"):
                self.stage(host_ref=value)
            self.assertFalse((self.home / "bound").exists())
        with self.assertRaisesRegex(self.svc.Refusal, "HOST_BINDING_REQUIRES_SEAT"):
            self.stage(seat_id=None)
        self.assertFalse((self.home / "bound").exists())

    def test_host_metadata_drift_fails_service_template_verification(self):
        root, receipt = self.stage()
        receipt["host_ref"] = "host-" + "e" * 64
        (root / "INSTALLATION.json").write_bytes(self.svc._json_bytes(receipt))
        with self.assertRaisesRegex(self.svc.Refusal, "SERVICE_TEMPLATE_CHANGED"):
            self.svc.verify(root)

    def test_legacy_seat_stays_unbound_and_rejects_injected_binding(self):
        root, receipt = self.stage(host_ref=None)
        self.assertEqual(receipt["schema"], self.svc.SCHEMA_V3)
        self.assertIsNone(self.svc.execution_binding(receipt))
        receipt["host_ref"] = HOST
        (root / "INSTALLATION.json").write_bytes(self.svc._json_bytes(receipt))
        with self.assertRaisesRegex(self.svc.Refusal, "INVALID_MANIFEST"):
            self.svc.verify(root)

    def test_v4_reuses_existing_tunnel_binding_ceremony(self):
        root, receipt = self.stage()
        bound = self.svc.bind(root, "tunnel_" + "b" * 32)
        self.assertEqual(self.svc.verify_binding(root), bound)
        self.assertIn("--host-ref", (root / "connection/profile.yaml").read_text())
        self.assertEqual(self.svc.execution_binding(self.svc.verify(root))["host_ref"], HOST)

    def test_cli_conflicting_host_binding_refuses_before_stdio_start(self):
        root, _ = self.stage()
        result = subprocess.run([str(self.python), "-I", str(root / "runtime/direct_service.py"),
                  "serve", "--root", str(root), "--host-ref", "host-" + "e" * 64],
                  capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["state"], "HOST_BINDING_MISMATCH")
        self.assertEqual(result.stdout, "")

    def test_real_stdio_keeps_closed_five_tool_input_surface(self):
        root, _ = self.stage()
        with patch.object(sys, "executable", str(self.python)):
            result = asyncio.run(asyncio.wait_for(self.svc.probe(root), timeout=25))
        self.assertEqual(result["state"], "LOCAL_STDIO_PROVEN")
        self.assertFalse(result["paper_called"])
        self.assertFalse(result["production_acceptance"])
        self.assertEqual(len(result["catalog"]["tools"]), 5)
        for tool in result["catalog"]["tools"]:
            properties = tool["inputSchema"].get("properties", {})
            self.assertNotIn("execution_binding", properties)
            self.assertNotIn("host_ref", properties)
            self.assertNotIn("endpoint", properties)
        prepared = next(t for t in result["catalog"]["tools"] if t["name"] == "paper_prepare")
        self.assertIn("without changing active-file focus", prepared["description"])

    def wire(self, value, tool, arguments):
        _, receipt = self.stage()
        scope = self.svc.execution_binding(receipt)
        async def run():
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            code = ("import sys\nsys.path.insert(0, " + repr(str(ROOT)) + ")\n"
                    + "import mcp_server, prepare\n"
                    + "scope = " + repr(scope) + "\n"
                    + "value = " + repr(value) + "\n"
                    + "def execute(*args, **kwargs):\n"
                    + "    assert kwargs.get('execution_binding') == scope\n"
                    + "    return value\n"
                    + "mcp_server.execute = execute\n"
                    + "prepare.prepare_document = execute\n"
                    + "mcp_server.build_server(True, True, execution_binding=scope).run(transport='stdio')\n")
            launcher = self.home / "wire_fixture.py"
            launcher.write_text(code)
            parameters = StdioServerParameters(command=str(self.python), args=["-I", str(launcher)],
                                               env={"PATH": "/usr/bin:/bin"})
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    return await client.call_tool(tool, arguments)
        return asyncio.run(asyncio.wait_for(run(), timeout=25)), scope

    def test_real_wire_observation_carries_configured_host_and_runtime(self):
        value = {"state": "OBSERVED", "result": {"content": [{"type": "text", "text": "ok"}]}}
        result, scope = self.wire(value, "paper_read", {"tool": "get_jsx", "arguments": {}})
        self.assertFalse(result.isError)
        self.assertEqual(json.loads(result.content[0].text)["execution_binding"], scope)
        self.assertNotIn("execution_binding", value)

    def test_real_wire_unknown_edit_keeps_scope_without_retry(self):
        value = {"state": "EFFECT_UNKNOWN", "operation_id": "fixture-unknown-1", "retry_allowed": False}
        result, scope = self.wire(value, "paper_edit", {"tool": "write_html", "arguments": {},
                      "expected_snapshot": "0" * 64, "operation_id": "fixture-unknown-1"})
        actual = json.loads(result.content[0].text)
        self.assertTrue(result.isError)
        self.assertEqual(actual["state"], "EFFECT_UNKNOWN")
        self.assertEqual(actual["execution_binding"], scope)
        self.assertFalse(actual["retry_allowed"])

    def test_real_wire_prepare_carries_same_scope(self):
        value = {"state": "PAPER_READY", "snapshot_sha256": "0" * 64, "open_attempted": False}
        result, scope = self.wire(value, "paper_prepare", {"file_id": "01" + "A" * 24,
                      "expected_snapshot": "0" * 64, "operation_id": "fixture-prepare-1"})
        self.assertFalse(result.isError)
        self.assertEqual(json.loads(result.content[0].text)["execution_binding"], scope)


if __name__ == "__main__":
    unittest.main()
