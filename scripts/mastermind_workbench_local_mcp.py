#!/usr/bin/env python3
"""Launch the Personal-Pro-safe local Mastermind Workbench MCP over stdio."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from integrations.workbench_local_mcp.schemas import (  # noqa: E402
    LocalProfileError,
    load_config,
    schema_snapshot,
    schema_snapshot_sha256,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    parser.add_argument("--config", help="absolute owner-controlled local profile JSON")
    parser.add_argument("--describe", action="store_true", help="print the frozen read/prepare surface")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.describe:
        payload = schema_snapshot()
        payload["snapshot_sha256"] = schema_snapshot_sha256()
        payload["capability_state"] = "BUILT_NOT_PROVEN"
        payload["transport"] = "stdio-via-secure-mcp-tunnel"
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")), flush=True)
        return 0
    if args.config is None:
        print("WORKBENCH_LOCAL_CONFIGURATION_REQUIRED", file=sys.stderr, flush=True)
        return 2
    try:
        selected = Path(args.config)
        if not selected.is_absolute():
            raise LocalProfileError("CONFIGURATION_REFUSED")
        config = load_config(str(selected))
        from integrations.workbench_local_mcp.adapter import LocalWorkbenchGateway
        from integrations.workbench_local_mcp.server import run_stdio

        gateway = LocalWorkbenchGateway.open(config)
        asyncio.run(run_stdio(gateway))
    except LocalProfileError as error:
        print(f"WORKBENCH_LOCAL_{error.code}", file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
