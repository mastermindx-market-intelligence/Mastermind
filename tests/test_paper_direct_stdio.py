"""Real MCP stdio proof without contacting Paper or OpenAI.

Run with the dedicated mcp==1.30.0 environment. Tests use temporary bundles and
non-networking fixture tunnel binaries; none consumes real credentials.
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "integrations/paper_desktop/direct_service.py"


@unittest.skipUnless(importlib.util.find_spec("mcp"), "Dedicated MCP SDK required")
class DirectStdioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve()
        self.binary = self.home / "tunnel-client"
        self.binary.write_text("#!/bin/sh\nexit 0\n")
        self.binary.chmod(0o700)
        spec = importlib.util.spec_from_file_location("paper_direct_stdio_test", SOURCE)
        self.svc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.svc)

    def tearDown(self):
        self.tmp.cleanup()

    def stage(self, write):
        root = self.home / ("write" if write else "read")
        self.svc.stage(root, python=Path(sys.executable).absolute(), tunnel_client=self.binary,
                       source_revision="0" * 40, allow_write=write)
        return root

    def test_real_stdio_readonly_surface(self):
        result = asyncio.run(asyncio.wait_for(self.svc.probe(self.stage(False)), timeout=20))
        self.assertEqual(result["state"], "LOCAL_STDIO_PROVEN")
        self.assertEqual(result["tools"], ["paper_catalog", "paper_inspect", "paper_read"])
        self.assertFalse(result["paper_called"])
        self.assertFalse(result["chatgpt_enrolled"])

    def test_real_stdio_write_surface_preserves_consequential_annotations(self):
        result = asyncio.run(asyncio.wait_for(self.svc.probe(self.stage(True)), timeout=20))
        tools = {t["name"]: t for t in result["catalog"]["tools"]}
        self.assertEqual(set(tools), {"paper_catalog", "paper_inspect", "paper_read", "paper_edit"})
        edit = tools["paper_edit"]
        self.assertEqual(set(edit["inputSchema"]["required"]),
                         {"tool", "arguments", "expected_snapshot", "operation_id"})
        self.assertFalse(edit["annotations"]["readOnlyHint"])
        self.assertTrue(edit["annotations"]["destructiveHint"])
        self.assertFalse(edit["annotations"]["idempotentHint"])
        self.assertTrue(edit["annotations"]["openWorldHint"])
        self.assertFalse(result["production_acceptance"])

    def test_unbound_cli_cannot_start_a_tunnel(self):
        root = self.stage(True)
        result = subprocess.run([sys.executable, "-I", str(root / "runtime/direct_service.py"),
                                 "run", "--root", str(root)], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["state"], "BINDING_REQUIRED")

    def test_bound_cli_still_requires_final_runtime_key(self):
        root = self.stage(True)
        self.svc.bind(root, "tunnel_" + "b" * 32, "workspace-business-test")
        result = subprocess.run([sys.executable, "-I", str(root / "runtime/direct_service.py"),
                                 "run", "--root", str(root)], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["state"], "RUNTIME_KEY_MISSING")


if __name__ == "__main__":
    unittest.main()
