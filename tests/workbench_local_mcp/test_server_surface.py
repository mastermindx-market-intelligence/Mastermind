from __future__ import annotations

import unittest

from integrations.workbench_local_mcp.schemas import TOOL_SPECS


class ServerSurfaceTests(unittest.TestCase):
    def test_sdk_surface_matches_closed_specs(self) -> None:
        try:
            from integrations.workbench_local_mcp.server import build_tools
        except ImportError as exc:
            self.skipTest(f"optional MCP SDK unavailable: {exc}")
        tools = build_tools()
        self.assertEqual([tool.name for tool in tools], [spec.name for spec in TOOL_SPECS])
        for tool in tools:
            annotations = tool.annotations
            self.assertTrue(annotations.readOnlyHint)
            self.assertFalse(annotations.destructiveHint)
            self.assertTrue(annotations.idempotentHint)
            self.assertFalse(annotations.openWorldHint)


if __name__ == "__main__":
    unittest.main()
