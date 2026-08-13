"""Print the read-only CEO boot packet assembled from Agent OS.

The stable entrypoint for :mod:`control_plane.ceo_boot_packet` — the Phase 1D-A
bridge that lets the AI CEO seat reconstruct organizational state from canonical
stores instead of conversational memory.  Executive OS READS Agent OS: this command
never writes into the Macro checkout, never dispatches, never schedules, and never
arms anything.

It ALWAYS exits 0 once the arguments parse.  A missing or stale Macro checkout is an
orientation gap, not a control-plane fault, so it degrades with explicit warnings
rather than failing — see the fail-open design law in the module docstring.

    python3 scripts/ceo_boot_packet.py
    python3 scripts/ceo_boot_packet.py --json
    python3 scripts/ceo_boot_packet.py --macro-root ~/Documents/Cluade/"Macro Dashboard"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.ceo_boot_packet import (  # noqa: E402  (after sys.path bootstrap)
    DEFAULT_TIMEOUT,
    ENV_MACRO_ROOT,
    build_packet,
    render_packet,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only CEO boot packet assembled from the Agent OS store.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit the mastermind.ceo_boot_packet.v1 document instead of text",
    )
    parser.add_argument(
        "--macro-root",
        help=f"Macro checkout to read Agent OS from (overrides ${ENV_MACRO_ROOT})",
    )
    parser.add_argument(
        "--since", help="brief window: 1h | 24h | 7d | overnight | YYYY-MM-DD",
    )
    parser.add_argument(
        "--now", help="freeze the clock (ISO-8601) — reproducibility",
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT,
        help=f"seconds allowed for the Agent OS brief (default {DEFAULT_TIMEOUT})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    packet = build_packet(
        macro_root_flag=args.macro_root,
        since=args.since,
        now=args.now,
        timeout=args.timeout,
    )

    if args.json:
        sys.stdout.write(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render_packet(packet))

    # Fail open by contract: a degraded packet is still a delivered packet.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
