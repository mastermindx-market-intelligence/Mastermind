#!/usr/bin/env python3
"""Run the loopback Workspace Agent candidate-return MCP service."""
from __future__ import annotations

import argparse

from integrations.workspace_agent_return_service import run_configured_service


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the owner-managed Workspace return service config.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return run_configured_service(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
