#!/usr/bin/env python3
"""Read-only proof client for route B: MCP over one ssh command.

  probe.py --out <new 0700 dir> --file <fileId> [--node <nodeId>] -- ssh <ssh args...>

Runs initialize, tools/list, paper_read(get_basic_info) and, with --node,
paper_read(get_screenshot). It writes the PNG and a JSON receipt with sha256 values
into --out. It needs the `mcp` package (any runtime built by build_runtime.py has it).
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import sys
from pathlib import Path


async def run(cmd: list[str], file_id: str, node: str | None, out: Path) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=cmd[0], args=cmd[1:])
    receipt: dict = {}
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            receipt["server"] = init.serverInfo.name
            receipt["tools"] = sorted(t.name for t in (await s.list_tools()).tools)
            info = await s.call_tool("paper_read", {"tool": "get_basic_info", "arguments": {"fileId": file_id}})
            body = json.loads(info.content[0].text)
            receipt["basic_info_state"] = body.get("state")
            receipt["basic_info_is_error"] = info.isError
            if node:
                shot = await s.call_tool("paper_read", {"tool": "get_screenshot",
                                                        "arguments": {"fileId": file_id, "nodeId": node, "scale": 1}})
                receipt["screenshot_state"] = json.loads(shot.content[0].text).get("state")
                for block in shot.content[1:]:
                    if getattr(block, "type", "") == "image":
                        data = base64.b64decode(block.data)
                        path = out / f"{node}.png"
                        path.write_bytes(data)
                        receipt["screenshot"] = {"path": str(path), "bytes": len(data),
                                                 "sha256": hashlib.sha256(data).hexdigest()}
    return receipt


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" not in argv:
        print("usage: probe.py --out DIR --file ID [--node ID] -- ssh ...", file=sys.stderr)
        return 2
    i = argv.index("--")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--node")
    a = ap.parse_args(argv[:i])
    out = Path(a.out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = asyncio.run(run(argv[i + 1:], a.file, a.node, out))
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1))
    print(json.dumps(receipt))
    return 0 if receipt.get("basic_info_state") == "OBSERVED" else 1


if __name__ == "__main__":
    sys.exit(main())
