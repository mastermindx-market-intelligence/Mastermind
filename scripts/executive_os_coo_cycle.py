#!/usr/bin/env python3
"""Explicit, bounded, production-unarmed Phase 1F-C COO cycle CLI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_runtime import Runtime, RuntimeProofError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Perform at most one deterministic COO bookkeeping mutation for one "
            "explicit strict-v2 Executive root. No polling or parent selection."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=_REPOSITORY_ROOT,
        help=(
            "existing schema-v4 Executive runtime root; defaults to this repository "
            "and is never created or migrated"
        ),
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    run_once = subcommands.add_parser("run-once")
    run_once.add_argument("--parent", required=True, help="exact aggregation root Job ID")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        runtime = Runtime.at(args.root, create=False, existing_writable=True)
        outcome = CooCycle(runtime).run_once(args.parent)
    except RuntimeProofError as exc:
        print(
            json.dumps(
                {
                    "schema_version": "mastermind.executive_coo_cycle_error/v1",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(outcome.to_dict(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
