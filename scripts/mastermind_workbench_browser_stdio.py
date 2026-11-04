#!/usr/bin/env python3
"""Describe or launch one fixed-channel Workbench Browser stdio child."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _run(path: str) -> int:
    source_root = str(Path(__file__).resolve().parents[1])
    if not sys.path or sys.path[0] != source_root:
        sys.path.insert(0, source_root)
    from integrations.workbench_browser_mcp.tunnel import (
        run_configured_browser_stdio,
    )

    return run_configured_browser_stdio(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        allow_abbrev=False,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--describe", action="store_true")
    mode.add_argument("--config")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if args.describe:
        print(
            json.dumps(
                {
                    "capability": "BUILT_NOT_PROVEN",
                    "mode": "fixed-channel-stdio",
                    "authority_kind": "secure_mcp_tunnel_channel",
                    "surface": "workbench-browser",
                    "config_schema": "mastermind.workbench_browser_tunnel.v1",
                    "browser_engine": "@playwright/mcp@0.0.79",
                    "persistent_profiles": False,
                    "installed": False,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.config is None:
        print("BROWSER_TUNNEL_CONFIGURATION_REQUIRED", file=sys.stderr)
        return 2
    return _run(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
