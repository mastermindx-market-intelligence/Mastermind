"""Optional native-client MCP projection using the official, pinned Python SDK.

Transport is stdio only. Approved local clients may launch this process directly.
ChatGPT Web uses the existing Studio Direct private tunnel and its gateway-owned
paper_* tools, which invoke the same guarded bridge; do not enroll a second Paper
web gateway from this module. This module does not create HTTP/auth infrastructure
or arm Executive grants.
"""

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bridge import execute, Refusal, READ_TOOLS, EDIT_TOOLS


def build_server(allow_write=False):
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations, CallToolResult, TextContent, ImageContent

    server = FastMCP("mastermind-paper", instructions=(
        "Inspect the active Paper document first. Read the catalog for exact upstream schemas. "
        "A snapshot is a drift guard, not permission or a document revision. "
        "Only one design operator may own a desktop document at a time. "
        "Never retry EFFECT_UNKNOWN; reconcile the original operation with the same carrier."
    ))

    def run(action, **kwargs):
        try:
            value = execute(action, **kwargs)
        except Refusal as exc:
            value = {"state": exc.code, "detail": exc.detail, "retry_allowed": False}
        bad = value.get("state") not in {None, "CONNECTED", "OBSERVED", "APPLIED_RESPONSE_OBSERVED"}
        images = []
        for block in value.get("result", {}).get("content", []):
            if block.get("type") == "image":
                images.append(ImageContent.model_validate(block))
                block.pop("data", None)
                block["rendered_as_mcp_image"] = True
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(value)), *images], isError=bad)

    read_annotations = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                      idempotentHint=True, openWorldHint=False)

    @server.tool(annotations=read_annotations)
    async def paper_inspect() -> CallToolResult:
        """Inspect Paper availability and the active file; obtain a fresh snapshot guard."""
        return await asyncio.to_thread(run, "status")

    @server.tool(annotations=read_annotations)
    async def paper_catalog() -> CallToolResult:
        """Return actual current Paper tool input schemas. Unknown/destructive tools are blocked."""
        return await asyncio.to_thread(run, "catalog")

    @server.tool(annotations=read_annotations)
    async def paper_read(tool: str, arguments: dict, expected_snapshot: str | None = None) -> CallToolResult:
        """Call an allowed Paper inspection/screenshot/JSX tool, never a document mutation."""
        if tool not in READ_TOOLS:
            return CallToolResult(content=[TextContent(type="text", text="TOOL_NOT_ALLOWED")], isError=True)
        return await asyncio.to_thread(run, "read", tool=tool, arguments=arguments,
                                       expected_snapshot=expected_snapshot)

    if allow_write:
        @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                                idempotentHint=False, openWorldHint=True))
        async def paper_edit(tool: str, arguments: dict, expected_snapshot: str, operation_id: str) -> CallToolResult:
            """Mutate the explicitly approved active Paper design. Never auto-retry this action.

            Caller must have current write permission and exclusive design-task ownership.
            File creation/open transitions, native exports, node deletion and token deletion are intentionally not permitted.
            """
            return await asyncio.to_thread(run, "edit", tool=tool, arguments=arguments,
                                           expected_snapshot=expected_snapshot,
                                           operation_id=operation_id, allow_write=True)
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-write", action="store_true")
    args = parser.parse_args()
    try:
        build_server(args.allow_write).run(transport="stdio")
    except ImportError:
        print("MCP_SDK_REQUIRED: install requirements-mcp.txt in a dedicated Python 3.10+ environment.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
