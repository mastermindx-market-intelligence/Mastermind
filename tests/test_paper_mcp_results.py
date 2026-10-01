"""Exercise MCP result projection without calling Paper, a tunnel, or real keys."""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from paper_direct_test_support import has_pinned_mcp_sdk

ROOT = Path(__file__).resolve().parents[1] / "integrations/paper_desktop"


@unittest.skipUnless(has_pinned_mcp_sdk(), "Dedicated mcp==1.30.0 SDK required")
class McpResultTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # The repository also has a top-level `bridge` package. mcp_server.py is
        # normally a fresh isolated stdio process, so reproduce that module
        # identity explicitly instead of inheriting pytest's module cache.
        self._prior_modules = {name: sys.modules.get(name) for name in ("bridge", "prepare")}

        def load_exact(name, path):
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            return module

        load_exact("bridge", ROOT / "bridge.py")
        self.prepare = load_exact("prepare", ROOT / "prepare.py")
        spec = importlib.util.spec_from_file_location("paper_result_test_server", ROOT / "mcp_server.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.server = self.module.build_server(allow_write=True, allow_prepare=True)

    def tearDown(self):
        for name, previous in self._prior_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    async def invoke(self, name, args):
        # The real SDK's registered callable returns the exact CallToolResult
        # subsequently serialized by FastMCP. No external transport is touched.
        tool = self.server._tool_manager.get_tool(name)
        return await tool.fn(**args)

    def payload(self, result):
        return json.loads(result.content[0].text)

    async def test_prepare_lost_reply_preserves_unknown_effect_and_operation(self):
        value = {"state": "EFFECT_UNKNOWN", "operation_id": "lost-focus-1", "file_id": "0" * 26,
                 "result": None, "retry_allowed": False, "response_observed": False,
                 "after": {"identity": {"kind": "file-id", "id": "0" * 26}}}
        with patch.object(self.prepare, "prepare_document", return_value=value) as invoke:
            try:
                result = await self.invoke("paper_prepare", {
                    "file_id": "0" * 26, "expected_snapshot": "0" * 64, "operation_id": "lost-focus-1"})
            except Exception as exc:
                self.fail(f"Uncertain effect receipt was lost in projection: {type(exc).__name__}")
        self.assertTrue(result.isError)
        self.assertEqual(self.payload(result), value)
        invoke.assert_called_once()

    async def test_projecting_native_image_does_not_mutate_evidence(self):
        image = {"type": "image", "data": "aGVsbG8=", "mimeType": "image/png"}
        value = {"state": "OBSERVED", "result": {"content": [image]}}
        original = copy.deepcopy(value)
        with patch.object(self.module, "execute", return_value=value):
            result = await self.invoke("paper_read", {"tool": "get_screenshot", "arguments": {}})
        self.assertEqual(value, original, "Image projection rewrote the original evidence receipt")
        self.assertEqual(result.content[1].data, "aGVsbG8=")
        text_image = self.payload(result)["result"]["content"][0]
        self.assertNotIn("data", text_image)
        self.assertTrue(text_image["rendered_as_mcp_image"])

    async def test_bad_image_does_not_erase_observed_content_edit(self):
        value = {"state": "APPLIED_RESPONSE_OBSERVED", "operation_id": "edit-observed-1",
                 "retry_allowed": False, "result": {"content": [{"type": "image", "data": "aGVsbG8="}]},
                 "after": {"identity": {"kind": "file-id", "id": "0" * 26}},
                 "production_acceptance": False}
        with patch.object(self.module, "execute", return_value=value) as execute:
            try:
                result = await self.invoke("paper_edit", {"tool": "write_html", "arguments": {},
                    "expected_snapshot": "0" * 64, "operation_id": "edit-observed-1"})
            except Exception as exc:
                self.fail(f"Observed edit receipt was lost to image formatting: {type(exc).__name__}")
        actual = self.payload(result)
        self.assertEqual(actual["state"], "APPLIED_RESPONSE_OBSERVED")
        self.assertEqual(actual["operation_id"], "edit-observed-1")
        self.assertFalse(actual["retry_allowed"])
        self.assertEqual(actual["presentation_errors"], ["IMAGE_BLOCK_INVALID"])
        self.assertTrue(result.isError)
        execute.assert_called_once()

    async def wire_call(self, value, tool_name, arguments):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        # Only the protocol projection is real. Vendor execution is replaced
        # before the server starts; this fixture cannot reach the Paper app.
        code = ("import sys\n"
                + "sys.path.insert(0, " + repr(str(ROOT)) + ")\n"
                + "import mcp_server, prepare\n"
                + "value = " + repr(value) + "\n"
                + "mcp_server.execute = lambda *a, **k: value\n"
                + "prepare.prepare_document = lambda **k: value\n"
                + "mcp_server.build_server(True, True).run(transport='stdio')\n")
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / "fixture.py"
            launcher.write_text(code)
            parameters = StdioServerParameters(command=sys.executable, args=["-I", str(launcher)],
                                               env={"PATH": "/usr/bin:/bin"})
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    return await client.call_tool(tool_name, arguments)

    async def test_real_stdio_preserves_lost_focus_receipt(self):
        value = {"state": "EFFECT_UNKNOWN", "operation_id": "wire-lost-focus-1",
                 "result": None, "retry_allowed": False, "response_observed": False,
                 "after": {"identity": {"kind": "file-id", "id": "0" * 26}}}
        result = await asyncio.wait_for(self.wire_call(value, "paper_prepare", {
            "file_id": "0" * 26, "expected_snapshot": "0" * 64,
            "operation_id": "wire-lost-focus-1"}), timeout=20)
        self.assertTrue(result.isError)
        self.assertEqual(self.payload(result), value)

    async def test_real_stdio_preserves_edit_receipt_despite_image_failure(self):
        value = {"state": "APPLIED_RESPONSE_OBSERVED", "operation_id": "wire-edit-1",
                 "retry_allowed": False, "result": {"content": [{"type": "image", "data": "aGVsbG8="}]},
                 "production_acceptance": False}
        result = await asyncio.wait_for(self.wire_call(value, "paper_edit", {
            "tool": "write_html", "arguments": {}, "expected_snapshot": "0" * 64,
            "operation_id": "wire-edit-1"}), timeout=20)
        self.assertTrue(result.isError)
        actual = self.payload(result)
        self.assertEqual(actual["state"], "APPLIED_RESPONSE_OBSERVED")
        self.assertEqual(actual["operation_id"], "wire-edit-1")
        self.assertFalse(actual["retry_allowed"])
        self.assertEqual(actual["presentation_errors"], ["IMAGE_BLOCK_INVALID"])

    async def test_read_only_refusal_still_returns_typed_receipt(self):
        with patch.object(self.module, "execute", side_effect=self.module.Refusal("UPSTREAM_FORBIDDEN")):
            result = await self.invoke("paper_inspect", {})
        self.assertTrue(result.isError)
        self.assertEqual(self.payload(result)["state"], "UPSTREAM_FORBIDDEN")
        self.assertFalse(self.payload(result)["retry_allowed"])


if __name__ == "__main__":
    unittest.main()
