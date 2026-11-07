#!/usr/bin/env python3
"""Launch the fixed provider-free ACP workspace read MCP over stdio."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from integrations.acp_worker.workspace_read_mcp import WorkspaceReadGateway
from integrations.acp_worker.workspace_read_server import run_stdio


def main() -> int:
    try:
        gateway = WorkspaceReadGateway.from_environment(os.environ)
        asyncio.run(run_stdio(gateway))
    except (OSError, RuntimeError, ValueError):
        print("ACP_WORKSPACE_READ_REFUSED", file=sys.stderr, flush=True)
        return 65
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
