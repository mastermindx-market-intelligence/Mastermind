#!/usr/bin/env python3
"""Launch the bounded Executive OS MCP gateway.

    python3 scripts/executive_mcp.py --mode readonly
    python3 scripts/executive_mcp.py --mode fixture --config /tmp/fixture.json
    python3 scripts/executive_mcp.py --mode readonly --describe

There are exactly two modes (commission R8).  ``readonly`` exposes the four read
tools and refuses ``submit_ceo_intent`` with ``production_write_disabled``.
``fixture`` additionally submits to a TEMPORARY Executive control service named
explicitly in a JSON config; the installed production socket, config, runtime
root, and system root are refused as fixture targets.

There is no production write mode and no flag that creates one.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from integrations.executive_mcp.adapter import (  # noqa: E402
    ExecutiveMcpGateway,
    load_gateway_config,
)
from integrations.executive_mcp.schemas import (  # noqa: E402
    SCHEMA_SNAPSHOT_SHA256,
    GatewayError,
    ServerMode,
    canonical_json,
    schema_snapshot,
    schema_snapshot_sha256,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--mode",
        choices=[item.value for item in ServerMode],
        default=ServerMode.READONLY.value,
        help="readonly (default) or fixture; there is no production write mode",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="JSON host config; required for fixture mode",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Mastermind checkout to project state from (default: this repository)",
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help="print the frozen tool surface and its snapshot hash, then exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_gateway_config(args.mode, args.config, repo_root=args.repo_root)
    except GatewayError as exc:
        print(f"executive-mcp: {exc.code}: {exc.message}", file=sys.stderr, flush=True)
        return 2

    if args.describe:
        payload = schema_snapshot()
        payload["snapshot_sha256"] = schema_snapshot_sha256()
        payload["pinned_snapshot_sha256"] = SCHEMA_SNAPSHOT_SHA256
        payload["mode"] = config.mode.value
        print(canonical_json(payload).decode("utf-8"), flush=True)
        return 0

    # Imported here, not at module scope: `--describe` and every config refusal
    # must work on a host that has no MCP SDK installed (R5).
    from integrations.executive_mcp.server import run_stdio

    gateway = ExecutiveMcpGateway(config)
    try:
        asyncio.run(run_stdio(gateway))
    except KeyboardInterrupt:  # graceful shutdown (R12)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
