"""One-shot Executive Wake reconciliation.

Reads canonical sources, plans missing ``WAKE_REQUESTED`` / healthy
``SOURCE_RESOLVED`` rows, applies them onto the existing Executive OS events
table, prints a deterministic report, and exits.

Not a daemon.  No timer, scheduler, transport, or MCP acknowledgement.
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

from control_plane.executive_inbox import load_boot_packet_file  # noqa: E402
from control_plane.executive_runtime import Runtime  # noqa: E402
from control_plane.wake_reconcile import reconcile_wakes  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="One-shot Wake ledger reconciliation against Executive OS.",
    )
    parser.add_argument(
        "--root",
        help="repository root that owns data/control_plane/executive.sqlite3",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the deterministic report as JSON",
    )
    parser.add_argument(
        "--no-boot-packet",
        action="store_true",
        help="do not collect Agent OS / CEO boot packet",
    )
    parser.add_argument(
        "--boot-packet-file",
        help="inject a saved mastermind.ceo_boot_packet.v1 document",
    )
    return parser


def _report(result) -> dict[str, object]:
    return {
        "digest": result.snapshot.digest,
        "observed": [item.obligation_id for item in result.snapshot.observed],
        "requested": list(result.requested),
        "resolved": list(result.resolved),
        "already_requested": list(result.plan.already_requested),
        "already_closed": list(result.plan.already_closed),
        "unsupported_attention": list(result.plan.unsupported_attention),
        "degraded": list(result.plan.degraded),
        "contradictions": list(result.plan.contradictions),
        "runtime_health": result.snapshot.runtime_health.value,
        "inbox_runtime_health": result.snapshot.inbox_runtime_health.value,
        "agentos_health": result.snapshot.agentos_health.value,
        "transport_invocations": result.transport_invocations,
        "delivery_attempts": result.delivery_attempts,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.root).resolve() if args.root else _ROOT
    packet = None
    if args.boot_packet_file:
        packet, error = load_boot_packet_file(args.boot_packet_file)
        if error is not None:
            print(error, file=sys.stderr)
            return 2
    runtime = Runtime.at(root, create=True)
    result = reconcile_wakes(
        runtime,
        boot_packet=packet,
        include_boot_packet=not args.no_boot_packet and packet is None,
    )
    payload = _report(result)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"digest {payload['digest']}")
        print(f"requested {len(result.requested)} resolved {len(result.resolved)}")
        print(f"transport_invocations {result.transport_invocations}")
        print(f"delivery_attempts {result.delivery_attempts}")
        if result.plan.degraded:
            print("degraded:")
            for entry in result.plan.degraded:
                print(f"  - {entry}")
        if result.plan.contradictions:
            print("contradictions:")
            for entry in result.plan.contradictions:
                print(f"  - {entry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
