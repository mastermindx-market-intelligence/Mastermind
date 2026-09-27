"""Exercise the real pinned SDK transport, optionally a read-only Paper probe.

Run in the dedicated MCP environment. This never calls paper_edit or purchases
anything. Without --paper-inspect it makes no request to the Paper application.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys


async def probe(server_path: Path, write: bool, inspect_paper: bool) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    args = [str(server_path)] + (["--allow-write"] if write else [])
    async with stdio_client(StdioServerParameters(command=sys.executable, args=args)) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            hello = await client.initialize()
            catalog = await client.list_tools()
            expected = {"paper_inspect", "paper_catalog", "paper_read"}
            if write:
                expected.add("paper_edit")
            if {tool.name for tool in catalog.tools} != expected:
                raise RuntimeError("Unexpected exposed tool set")
            for tool in catalog.tools:
                if tool.annotations.readOnlyHint != (tool.name != "paper_edit"):
                    raise RuntimeError("Incorrect tool write annotation")
            data = catalog.model_dump(mode="json")
            result = {"mode": "write" if write else "readonly",
                      "server": hello.serverInfo.model_dump(mode="json"),
                      "tools": data,
                      "capture_sha256": hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
            if inspect_paper and not write:
                result["paper_inspect"] = (await client.call_tool("paper_inspect", {})).model_dump(mode="json")
            return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--server", type=Path, default=Path(__file__).with_name("mcp_server.py"))
    p.add_argument("--paper-inspect", action="store_true")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    async def run():
        return [await probe(a.server.resolve(), False, a.paper_inspect),
                await probe(a.server.resolve(), True, False)]
    result = asyncio.run(run())
    text = json.dumps(result, indent=2) + "\n"
    if a.output:
        with a.output.open("x") as f:
            f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
