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
from unittest.mock import patch
from paper_direct_test_support import PrivatePython, has_pinned_mcp_sdk

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "integrations/paper_desktop/direct_service.py"


@unittest.skipUnless(has_pinned_mcp_sdk(), "Dedicated mcp==1.30.0 SDK required")
class DirectStdioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._python_fixture = PrivatePython()
        cls.private_python = cls._python_fixture.python

    @classmethod
    def tearDownClass(cls):
        cls._python_fixture.close()
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

    def stage(self, write, prepare=False):
        root = self.home / ("write" if write else "read")
        options = {}
        if prepare:
            import inspect
            self.assertIn("allow_prepare", inspect.signature(self.svc.stage).parameters)
            options["allow_prepare"] = True
        self.svc.stage(root, python=self.private_python, tunnel_client=self.binary,
                       source_revision="0" * 40, allow_write=write, **options)
        return root

    def probe_bundle(self, root):
        # probe() validates that the invoking process is the staged runtime.
        # This in-process test models that identity; the server subprocess still
        # executes through the actual private staged interpreter.
        with patch.object(sys, "executable", str(self.private_python)):
            return asyncio.run(asyncio.wait_for(self.svc.probe(root), timeout=20))

    def test_real_stdio_readonly_surface(self):
        result = self.probe_bundle(self.stage(False))
        self.assertEqual(result["state"], "LOCAL_STDIO_PROVEN")
        self.assertEqual(result["tools"], ["paper_catalog", "paper_inspect", "paper_read"])
        instructions = result["catalog"].get("instructions") or ""
        self.assertIn("Multiple admitted designers may modify the same file/page across hosts", instructions)
        self.assertIn("board/artboard/node", instructions)
        self.assertNotIn("Only one design operator may own a desktop document", instructions)
        self.assertFalse(result["paper_called"])
        self.assertFalse(result["chatgpt_enrolled"])

    def test_real_stdio_write_surface_preserves_consequential_annotations(self):
        result = self.probe_bundle(self.stage(True))
        tools = {t["name"]: t for t in result["catalog"]["tools"]}
        self.assertEqual(set(tools), {"paper_catalog", "paper_inspect", "paper_read", "paper_edit"})
        edit = tools["paper_edit"]
        self.assertEqual(set(edit["inputSchema"]["required"]),
                         {"tool", "arguments", "expected_snapshot", "operation_id"})
        self.assertFalse(edit["annotations"]["readOnlyHint"])
        self.assertTrue(edit["annotations"]["destructiveHint"])
        self.assertFalse(edit["annotations"]["idempotentHint"])
        self.assertTrue(edit["annotations"]["openWorldHint"])
        self.assertIn("same Paper file or page", edit["description"])
        self.assertIn("not a file-wide or page-wide lease", edit["description"])
        self.assertFalse(result["production_acceptance"])

    def test_real_stdio_prepare_is_a_closed_non_destructive_write(self):
        result = self.probe_bundle(self.stage(True, prepare=True))
        tools = {t["name"]: t for t in result["catalog"]["tools"]}
        self.assertEqual(set(tools), {"paper_catalog", "paper_inspect", "paper_read", "paper_edit", "paper_prepare"})
        tool = tools["paper_prepare"]
        self.assertEqual(set(tool["inputSchema"]["required"]),
                         {"file_id", "expected_snapshot", "operation_id"})
        self.assertFalse(tool["annotations"]["readOnlyHint"])
        self.assertFalse(tool["annotations"]["destructiveHint"])
        self.assertTrue(tool["annotations"]["idempotentHint"])
        self.assertFalse(tool["annotations"]["openWorldHint"])
        self.assertFalse(result["paper_called"])

    def test_real_stdio_prepare_rejects_vendor_url_before_dispatch(self):
        root = self.stage(True, prepare=True)
        async def run():
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            command = [str(self.private_python), "-I", str(root / "runtime/direct_service.py"), "serve", "--root", str(root)]
            async with stdio_client(StdioServerParameters(command=command[0], args=command[1:],
                                                         env=self.svc.clean_env(dict(os.environ)))) as (reader, writer):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    return await client.call_tool("paper_prepare", {
                        "file_id": "https://paper.design/file/" + "0" * 26,
                        "expected_snapshot": "0" * 64, "operation_id": "sdk-invalid-url-no-effect"})
        result = asyncio.run(asyncio.wait_for(run(), timeout=20))
        self.assertTrue(result.isError)
        self.assertEqual(json.loads(result.content[0].text)["state"], "FILE_ID_REQUIRED")

    def test_unbound_cli_cannot_start_a_tunnel(self):
        root = self.stage(True)
        result = subprocess.run([str(self.private_python), "-I", str(root / "runtime/direct_service.py"),
                                 "run", "--root", str(root)], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["state"], "BINDING_REQUIRED")

    def test_bound_cli_still_requires_final_runtime_key(self):
        root = self.stage(True)
        self.svc.bind(root, "tunnel_" + "b" * 32, "workspace-business-test")
        result = subprocess.run([str(self.private_python), "-I", str(root / "runtime/direct_service.py"),
                                 "run", "--root", str(root)], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["state"], "RUNTIME_KEY_MISSING")


if __name__ == "__main__":
    unittest.main()
