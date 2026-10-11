"""Optional native-client MCP projection using the official, pinned Python SDK.

Transport is stdio only. Approved local clients may launch this process directly.
An explicitly enrolled private Business Mastermind Paper app may reach this same
stdio server through OpenAI Secure MCP Tunnel, without Studio Direct in its normal
Paper path. direct_service.py stages that route without enrolling or starting it.
Legacy seats may retain Studio Direct as another client of the same guarded bridge.
This module creates no HTTP/auth infrastructure and arms no Executive grants.
"""

import argparse
import asyncio
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bridge import execute, Refusal, READ_TOOLS, EDIT_TOOLS, validate_execution_binding


def build_server(allow_write=False, allow_prepare=False, *, execution_binding=None):
    execution_binding = validate_execution_binding(execution_binding)
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations, CallToolResult, TextContent, ImageContent

    server = FastMCP("mastermind-paper", instructions=(
        "Inspect the exact Paper target first. Read the catalog for exact upstream schemas. "
        "A snapshot is a drift guard, not permission, a document revision, or a collaboration lock. "
        "Multiple admitted designers may modify the same file/page across hosts; coordinate by "
        "board/artboard/node target and re-read/re-plan known overlap. "
        "Default active-file context and exact-file serviceability are separate facts. If paper_inspect "
        "returns DOCUMENT_UNAVAILABLE but an exact fileId is known, do not declare Paper blocked: call "
        "paper_read(get_basic_info, {fileId}) once to bootstrap that target snapshot. "
        "Each logical mutation remains on one carrier until reconciled. Never retry EFFECT_UNKNOWN; "
        "reconcile the original operation with the same carrier."
    ))

    def run(action, **kwargs):
        if execution_binding is not None:
            kwargs["execution_binding"] = execution_binding
        try:
            if action == "prepare":
                from prepare import prepare_document
                value = prepare_document(**kwargs)
            else:
                value = execute(action, **kwargs)
            if action == "status" and isinstance(value, dict):
                value = dict(value,
                             concurrency_rule="MULTI_WRITER_PER_FILE_TARGET_SCOPED",
                             same_file_multi_writer_allowed=True,
                             same_page_multi_writer_allowed=True,
                             coordination_scope="BOARD_ARTBOARD_NODE")
        except Refusal as exc:
            value = {"state": exc.code, "detail": exc.detail, "retry_allowed": False}
            if action == "status" and exc.code == "DOCUMENT_UNAVAILABLE":
                # Default active-file lookup failure is narrower than exact-file
                # serviceability. Keep the refusal typed/error-visible while
                # making the lawful one-shot bootstrap machine-readable even
                # when a ChatGPT app is still using an older frozen tool description.
                value.update({
                    "context_scope": "DEFAULT_ACTIVE_FILE",
                    "whole_paper_outage_proven": False,
                    "exact_target_status": "UNKNOWN",
                    "next_action_if_file_id_known": "paper_read:get_basic_info(fileId)",
                    "retry_paper_inspect": False,
                })
        if execution_binding is not None:
            value = dict(value, execution_binding=dict(execution_binding))
        bad = value.get("state") not in {None, "CONNECTED", "OBSERVED", "APPLIED_RESPONSE_OBSERVED", "PAPER_READY", "PAPER_READY_READ_ONLY"}
        # Formatting is downstream of effect observation. A missing reply or
        # malformed image must not erase the operation's canonical receipt.
        value = copy.deepcopy(value)
        images, presentation_errors = [], []
        result = value.get("result")
        blocks = result.get("content", []) if isinstance(result, dict) else []
        if result is not None and not isinstance(result, dict):
            presentation_errors.append("RESULT_BLOCK_INVALID")
        if not isinstance(blocks, list):
            presentation_errors.append("CONTENT_BLOCK_INVALID")
            blocks = []
        for block in blocks:
            if not isinstance(block, dict):
                presentation_errors.append("CONTENT_BLOCK_INVALID")
                continue
            if block.get("type") == "image":
                try:
                    image = ImageContent.model_validate(block)
                except ValueError:
                    # Do not include the validation exception: it can embed the
                    # complete image payload. Preserve the effect state instead.
                    presentation_errors.append("IMAGE_BLOCK_INVALID")
                    block.pop("data", None)
                    block["rendered_as_mcp_image"] = False
                else:
                    images.append(image)
                    block.pop("data", None)
                    block["rendered_as_mcp_image"] = True
        if presentation_errors:
            value["presentation_errors"] = presentation_errors
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(value)), *images],
                              isError=bad or bool(presentation_errors))

    read_annotations = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                      idempotentHint=True, openWorldHint=False)

    @server.tool(annotations=read_annotations)
    async def paper_inspect() -> CallToolResult:
        """Inspect Paper availability and default active-file context.\n\n        DOCUMENT_UNAVAILABLE means the default active context could not be resolved; it does\n        not prove Paper or an exact target file is unavailable. If the intended fileId is\n        already known, call paper_read with tool="get_basic_info" and that fileId once. A\n        successful explicit read returns the target guard needed for prepare/edit.\n        """
        return await asyncio.to_thread(run, "status")

    @server.tool(annotations=read_annotations)
    async def paper_catalog() -> CallToolResult:
        """Return actual current Paper tool input schemas. Unknown/destructive tools are blocked."""
        return await asyncio.to_thread(run, "catalog")

    @server.tool(annotations=read_annotations)
    async def paper_read(tool: str, arguments: dict, expected_snapshot: str | None = None) -> CallToolResult:
        """Call an allowed read-only Paper tool, never a document mutation.

        For a known exact target, get_basic_info with fileId returns that file's
        guarded document snapshot for prepare/edit even when another file is
        user-active or default active-file context is unavailable.
        """
        if tool not in READ_TOOLS:
            return CallToolResult(content=[TextContent(type="text", text="TOOL_NOT_ALLOWED")], isError=True)
        return await asyncio.to_thread(run, "read", tool=tool, arguments=arguments,
                                       expected_snapshot=expected_snapshot)

    if allow_prepare:
        @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                                idempotentHint=True, openWorldHint=False))
        async def paper_prepare(file_id: str, expected_snapshot: str, operation_id: str) -> CallToolResult:
            """Bind one existing Paper file by bare ID, never a URL or path.

            Paper must already be running. First call paper_read with
            tool="get_basic_info" and arguments={"fileId": file_id}; pass the
            returned document snapshot. The user's active file is not a prerequisite
            and may change concurrently. Validates only the exact target without changing active-file focus
            or design content. Use the returned target
            snapshot on this same installed host and service.
            """
            return await asyncio.to_thread(run, "prepare", file_id=file_id,
                                           expected_snapshot=expected_snapshot,
                                           operation_id=operation_id, allow_prepare=True)

    if allow_write:
        # HTML/style operations can reference external assets. A fixed loopback
        # transport alone does not establish a closed-world rendering boundary.
        # Keep this consequential, non-idempotent tool truthfully annotated.
        @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                                idempotentHint=False, openWorldHint=True))
        async def paper_edit(tool: str, arguments: dict, expected_snapshot: str, operation_id: str) -> CallToolResult:
            """Mutate an explicitly approved Paper target by exact fileId. Never auto-retry this action.

            The target need not be the user's active Paper file. Caller must have
            current write permission for this logical mutation/target.
            Other admitted sessions may modify disjoint targets in the same Paper file or page.
            Known same-board overlap should use disjoint node targets plus fresh re-read/re-plan;
            this operation/carrier fence is not a file-wide or page-wide lease.
            File creation/open transitions, native exports, node deletion and token deletion are intentionally not permitted.
            """
            return await asyncio.to_thread(run, "edit", tool=tool, arguments=arguments,
                                           expected_snapshot=expected_snapshot,
                                           operation_id=operation_id, allow_write=True)
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--allow-prepare", action="store_true")
    args = parser.parse_args()
    try:
        build_server(args.allow_write, args.allow_prepare).run(transport="stdio")
    except ImportError:
        print("MCP_SDK_REQUIRED: install requirements-mcp.txt in a dedicated Python 3.10+ environment.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
