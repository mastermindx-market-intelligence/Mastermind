#!/usr/bin/env python3
"""Read-only Cursor MCP surface census. Does not authenticate or dispatch Fabric.

Tool exposure is NOT provider admission, worker START, root/parent identity,
native-child model selection, paid subscription capacity, or result acceptance.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess


REQUIRED = frozenset({
    "fabric_capabilities", "fabric_request", "fabric_status", "fabric_wait",
    "fabric_result", "fabric_accept", "fabric_controller_output",
})
NAME = re.compile(r"^-[ ]+([A-Za-z][A-Za-z0-9_]*)[ ]*\(")
SERVER_NAMES = frozenset({"mastermindStudio", "mastermindFabric"})


def classify(output: str, exit_code: int, server: str) -> dict[str, object]:
    if server not in SERVER_NAMES:
        raise ValueError("unknown MCP binding; refusing broad inventory")
    tools = sorted({
        m.group(1) for line in output.splitlines() if (m := NAME.match(line))
    })
    found = set(tools) & REQUIRED
    has_request = "fabric_request" in found
    all_required = REQUIRED <= set(tools)
    if exit_code != 0:
        state = "MCP_CATALOG_UNAVAILABLE"
    elif all_required:
        state = "FABRIC_CATALOG_EXPOSED_NOT_ADMITTED"
    elif has_request:
        state = "PARTIAL_FABRIC_CATALOG_REFUSED"
    elif tools:
        state = "READ_ONLY_OR_UNRELATED_MCP"
    else:
        state = "NO_OBSERVED_TOOLS"
    return {
        "schema": "mastermind.cursor_fabric_readiness.v1",
        "server": server,
        "state": state,
        "mcp_exit_code": exit_code,
        "tool_names": tools,
        "fabric_tool_names": sorted(found),
        "required_fabric_tool_count": len(REQUIRED),
        "fabric_dispatch_authorized": False,
        "worker_started": False,
        "provider_admission_proven": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", choices=sorted(SERVER_NAMES), default="mastermindStudio")
    parser.add_argument("--agent-binary", default="agent")
    args = parser.parse_args()
    # Bounded, read-only CLI discovery. No shell, credentials, login or MCP call.
    try:
        result = subprocess.run(
            [args.agent_binary, "mcp", "list-tools", args.server],
            capture_output=True, text=True, timeout=15, check=False,
        )
        receipt = classify(result.stdout, result.returncode, args.server)
    except (OSError, subprocess.TimeoutExpired):
        receipt = classify("", 1, args.server)
    print(json.dumps(receipt, sort_keys=True))
    # Non-zero when not fully exposed; the parent must not treat this as authorization.
    return 0 if receipt["state"] == "FABRIC_CATALOG_EXPOSED_NOT_ADMITTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
