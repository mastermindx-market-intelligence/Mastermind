from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from common.bounded_sync_executor import BoundedSyncExecutor
from integrations.acp_worker.workspace_read_mcp import WorkspaceReadGateway

MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None


def _fixture(root_parent: Path):
    root = root_parent / "workspace"
    root.mkdir(mode=0o700)
    (root / "memo.txt").write_text(
        "alpha\nneedle-one\nbeta\nneedle-two\n", encoding="utf-8"
    )
    env = {
        "MMX_ACP_WORKSPACE_PATH": str(root),
        "MMX_ACP_WORKSPACE_BASE_SHA": "a" * 40,
        "MMX_ACP_RUN_ID": "RUN-1",
        "MMX_ACP_JOB_ID": "JOB-1",
        "MMX_ACP_WORKER_ID": "acp-worker-01",
        "MMX_ACP_DEADLINE_MS": str(int(time.time() * 1000) + 60_000),
    }
    return root, env


@unittest.skipUnless(MCP_AVAILABLE, "optional MCP SDK absent; ACP read server not qualified")
class AcpWorkspaceReadServerTests(unittest.TestCase):
    @staticmethod
    def _request(name: str, arguments: dict | None = None):
        import mcp.types as mcp_types
        return mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name=name, arguments={} if arguments is None else arguments
            ),
        )

    def _dispatch(self, name: str, arguments: dict | None = None):
        import mcp.types as mcp_types
        from integrations.acp_worker.workspace_read_server import build_server

        async def scenario():
            with tempfile.TemporaryDirectory(prefix="mmx-acp-read-server-") as td:
                _root, env = _fixture(Path(td))
                gateway = WorkspaceReadGateway.from_environment(env)
                executor = BoundedSyncExecutor(max_concurrency=2)
                try:
                    server = build_server(gateway, executor)
                    handler = server.request_handlers[mcp_types.CallToolRequest]
                    value = await handler(self._request(name, arguments))
                    self.assertIsInstance(value, mcp_types.ServerResult)
                    return value.root
                finally:
                    await executor.aclose(timeout=1.0)
                    gateway.close()

        return asyncio.run(scenario())

    @staticmethod
    def _payload(result):
        return json.loads(result.content[0].text)

    def test_sdk_surface_is_exactly_two_readonly_tools(self):
        from integrations.acp_worker.workspace_read_server import build_tools

        tools = build_tools()
        self.assertEqual([tool.name for tool in tools], ["read_file", "search_text"])
        for tool in tools:
            self.assertTrue(tool.annotations.readOnlyHint)
            self.assertFalse(tool.annotations.destructiveHint)
            self.assertTrue(tool.annotations.idempotentHint)
            self.assertFalse(tool.annotations.openWorldHint)

    def test_sdk_dispatch_reads_and_searches_through_gateway(self):
        read = self._dispatch("read_file", {"relative_path": "memo.txt"})
        self.assertFalse(read.isError)
        self.assertTrue(self._payload(read)["data"]["content"].startswith("alpha\n"))

        search = self._dispatch(
            "search_text",
            {"relative_path": "memo.txt", "query": "needle", "max_matches": 4},
        )
        self.assertFalse(search.isError)
        self.assertEqual(
            [row["line"] for row in self._payload(search)["data"]["matches"]],
            [1, 3],
        )

    def test_unknown_tool_is_sanitized_before_sdk_warning(self):
        private_name = "PRIVATE-SENTINEL-" + "x" * 4096
        result = self._dispatch(private_name)
        payload = self._payload(result)
        self.assertTrue(result.isError)
        self.assertEqual(payload["tool"], "unknown")
        self.assertEqual(payload["error"]["code"], "TOOL_NOT_AVAILABLE")
        self.assertNotIn(private_name, result.content[0].text)
        self.assertNotIn("PRIVATE-SENTINEL", result.content[0].text)

    def test_invalid_request_never_echoes_private_input(self):
        private = "PRIVATE-REJECTED-SENTINEL"
        result = self._dispatch(
            "read_file",
            {"relative_path": "../" + private, "unknown": private},
        )
        self.assertTrue(result.isError)
        text = result.content[0].text
        self.assertEqual(self._payload(result)["error"]["code"], "INVALID_REQUEST")
        self.assertNotIn(private, text)
        self.assertNotIn("additionalProperties", text)

    def test_real_stdio_sdk_round_trip_uses_fixed_launcher_and_cleans_up(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with tempfile.TemporaryDirectory(prefix="mmx-acp-read-stdio-") as td:
            root, env = _fixture(Path(td))
            launcher = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "acp_workspace_read_mcp.py"
            )

            async def scenario():
                params = StdioServerParameters(
                    command=sys.executable,
                    args=["-B", str(launcher)],
                    cwd=str(root),
                    env={**env, "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                )
                async with stdio_client(params) as (reader, writer):
                    async with ClientSession(reader, writer) as client:
                        await client.initialize()
                        tools = await client.list_tools()
                        self.assertEqual(
                            [tool.name for tool in tools.tools],
                            ["read_file", "search_text"],
                        )
                        read = await client.call_tool(
                            "read_file",
                            {"relative_path": "memo.txt", "max_lines": 2},
                        )
                        self.assertFalse(read.isError)
                        payload = json.loads(read.content[0].text)
                        self.assertEqual(
                            payload["data"]["content"],
                            "alpha\nneedle-one\n",
                        )
                        search = await client.call_tool(
                            "search_text",
                            {
                                "relative_path": "memo.txt",
                                "query": "needle",
                                "max_matches": 2,
                            },
                        )
                        self.assertFalse(search.isError)
                        self.assertEqual(
                            [
                                row["line"]
                                for row in json.loads(
                                    search.content[0].text
                                )["data"]["matches"]
                            ],
                            [1, 3],
                        )

            asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
