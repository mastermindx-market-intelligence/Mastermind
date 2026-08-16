"""Inert stdio MCP server exposing ``ohf_probe_echo``.

No GitHub, no browser, no production services, no filesystem writes.
"""
from __future__ import annotations

import json
import sys

from scripts.ohf.fixtures import OHF_PROBE_MCP_TOOL

PROTOCOL_VERSION = "2024-11-05"


def _read() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return _read()
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
    return payload if isinstance(payload, dict) else None


def _write(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _result(request_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> int:
    while True:
        message = _read()
        if message is None:
            return 0
        method = message.get("method")
        request_id = message.get("id")
        if method == "initialize":
            _write(
                _result(
                    request_id,
                    {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "ohf_probe", "version": "p0"},
                    },
                )
            )
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            _write(
                _result(
                    request_id,
                    {
                        "tools": [
                            {
                                "name": OHF_PROBE_MCP_TOOL,
                                "description": "Echo a bounded laboratory payload.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"text": {"type": "string"}},
                                    "required": ["text"],
                                },
                            }
                        ]
                    },
                )
            )
        elif method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            text = str(arguments.get("text") or "")
            if name != OHF_PROBE_MCP_TOOL:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": f"unknown tool {name!r}"},
                    }
                )
                continue
            _write(
                _result(
                    request_id,
                    {
                        "content": [{"type": "text", "text": f"echo:{text}"}],
                        "isError": False,
                    },
                )
            )
        elif request_id is not None:
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"unknown method {method!r}"},
                }
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
