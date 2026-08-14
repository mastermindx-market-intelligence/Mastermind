"""Print the read-only Executive Inbox — what needs an executive, and whose it is.

The stable entrypoint for :mod:`control_plane.executive_inbox` — the Phase 1F-A
projection that compresses hundreds of durable Job/Attempt/Worker/Event rows into
the small set of items an executive seat must actually look at.

It READS.  It never dispatches, claims, requeues, cancels, schedules, or arms
anything; it creates no database, no table, and no file; and it never writes into
the Executive OS runtime or the Agent OS store.  The runtime remains the only
lifecycle authority and the Improvement Agenda remains the priority queue.

It ALWAYS exits 0 once the arguments parse.  A missing runtime database, an
unreadable registry, or an uncollectable boot packet is an orientation gap, not a
control-plane fault, so it degrades with explicit warnings rather than failing —
see the fail-open design law in the module docstring.

    python3 scripts/executive_inbox.py
    python3 scripts/executive_inbox.py --json
    python3 scripts/executive_inbox.py --no-boot-packet
    python3 scripts/executive_inbox.py --boot-packet-file /tmp/packet.json
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

from control_plane.executive_inbox import (  # noqa: E402  (after sys.path bootstrap)
    DEFAULT_TIMEOUT,
    build_inbox,
    parse_now,
    render_inbox,
)


def _iso_stamp(value: str) -> str:
    """argparse type for --now: reject an unparseable clock at PARSE time.

    A bad --now is a usage error, not a degraded read, so it must be refused
    before the always-exit-0 contract begins — otherwise a typo'd freeze would
    silently become the wall clock and the document would date itself one way
    while comparing leases another.
    """
    try:
        parse_now(value)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(f"--now must be ISO-8601: {exc}") from exc
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Executive Inbox projected from the durable runtime.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit the mastermind.executive_inbox.v1 document instead of text",
    )
    parser.add_argument(
        "--root",
        help="repository root to project (default: this checkout; mainly tests)",
    )
    parser.add_argument(
        "--macro-root",
        help="Macro checkout the boot packet reads Agent OS from",
    )
    parser.add_argument(
        "--now", type=_iso_stamp,
        help="freeze the clock (ISO-8601) — reproducibility",
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT,
        help=f"seconds allowed for the boot packet (default {DEFAULT_TIMEOUT})",
    )
    packet = parser.add_mutually_exclusive_group()
    packet.add_argument(
        "--no-boot-packet", action="store_true",
        help="skip boot-packet collection; CEO/Agent OS attention is not projected",
    )
    packet.add_argument(
        "--boot-packet-file",
        help="read a saved mastermind.ceo_boot_packet.v1 document instead of collecting",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    inbox = build_inbox(
        repo_root=Path(args.root) if args.root else None,
        include_boot_packet=not args.no_boot_packet,
        boot_packet_file=args.boot_packet_file,
        macro_root_flag=args.macro_root,
        now=args.now,
        timeout=args.timeout,
    )

    if args.json:
        sys.stdout.write(json.dumps(inbox, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render_inbox(inbox))

    # Fail open by contract: a degraded inbox is still a delivered inbox.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
