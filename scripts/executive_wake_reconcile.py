"""One-shot Executive Wake reconciliation.

Reads canonical sources, plans missing ``WAKE_REQUESTED`` / healthy
``SOURCE_RESOLVED`` rows, applies them onto the existing Executive OS events
table, prints a deterministic report, and exits.

``--observe-only`` uses the existing read-only Runtime and only plans rows.
SQLite may create sidecars/update shared-memory reader bookkeeping; no Runtime
rows, lifecycle state, schema or authoritative WAL frames are written. It is a
point observation, not a closed campaign census or acceptance verdict.
Its additive capacity observation reports conditional recorded Wake intervals
and snapshot attention coverage; unavailable costs/occupancy stay unavailable.
An optional exclusive observation receipt retains actual acquisition times and
the exact result. Offline receipt summaries never qualify installed coverage.

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
from control_plane.capacity_campaign_observation import observe_capacity_campaign  # noqa: E402
from control_plane.capacity_runtime_observation import observe_runtime_workload  # noqa: E402
from control_plane.capacity_observation_evidence import (  # noqa: E402
    ObservationEvidenceError, capture_observation, summarize_observations,
)
from control_plane.executive_runtime import PersistenceError, Runtime  # noqa: E402
from control_plane.fs_security import FilesystemSecurityError  # noqa: E402
from control_plane.wake_ledger import SourceReadHealth  # noqa: E402
from control_plane.wake_reconcile import (  # noqa: E402
    WakeReconcileResult, collect_source_snapshot, collect_ledger_snapshot,
    plan_wake_reconciliation, reconcile_wakes,
)


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
    parser.add_argument(
        "--observe-only", action="store_true",
        help="Read sources and report the plan without creating or resolving Wake rows.",
    )
    parser.add_argument(
        "--observation-receipt", type=Path,
        help="With --observe-only, retain one exclusive receipt in an existing private directory.",
    )
    parser.add_argument(
        "--installed-release-sha",
        help="With --observe-only and --observation-receipt, require the real installed root owner; no root or saved input override.",
    )
    parser.add_argument(
        "--summarize-observations", type=Path, nargs="+", metavar="RECEIPT",
        help="Offline JSON close/report over exactly these receipts; no Runtime read or campaign qualification.",
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


def _run(args) -> int:
    root = Path(args.root).resolve() if args.root else _ROOT
    packet = None
    if args.boot_packet_file:
        packet, error = load_boot_packet_file(args.boot_packet_file)
        if error is not None:
            print(error, file=sys.stderr)
            return 2
    try:
        runtime = Runtime.at(root, create=False, existing_writable=not args.observe_only)
    except PersistenceError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.observe_only:
        try:
            snapshot = collect_source_snapshot(
                runtime, boot_packet=packet,
                include_boot_packet=not args.no_boot_packet and packet is None,
            )
            ledger = collect_ledger_snapshot(runtime)
            plan = plan_wake_reconciliation(snapshot, ledger)
            measurements = observe_capacity_campaign(snapshot, ledger)
            workload = observe_runtime_workload(runtime)
            measurements["runtime_workload"] = workload
            if workload["degraded"]:
                measurements["degraded"].append("RUNTIME_WORKLOAD_PARTIAL")
                if measurements["point_status"] == "OBSERVED":
                    measurements["point_status"] = "PARTIAL"
        except Exception as exc:
            print(f"observation unavailable: {type(exc).__name__}", file=sys.stderr)
            return 2
        result = WakeReconcileResult(snapshot, plan, requested=(), resolved=())
    else:
        result = reconcile_wakes(
            runtime,
            boot_packet=packet,
            include_boot_packet=not args.no_boot_packet and packet is None,
        )
    payload = _report(result)
    if args.observe_only:
        payload.update(
            mode="observe_only", writes_applied=False,
            planned_request=[o.obligation_id for o in result.plan.to_request],
            planned_resolve=[o.obligation_id for o in result.plan.to_resolve],
            capacity_observation=measurements,
        )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if args.observe_only:
            print("mode observe_only; writes_applied false")
            print(f"planned_request {len(result.plan.to_request)} planned_resolve {len(result.plan.to_resolve)}")
            print(f"capacity_observation {measurements['point_status']}; campaign_qualified false")
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
    if result.plan.contradictions or args.observe_only and measurements["contradictions"]:
        return 3
    if args.observe_only and (
        result.plan.degraded or result.plan.unsupported_attention or measurements["degraded"]
        or any(health != SourceReadHealth.HEALTHY for health in (
            result.snapshot.runtime_health, result.snapshot.inbox_runtime_health,
            result.snapshot.agentos_health,
        ))
    ):
        return 2  # retained partial diagnostics are not a healthy observation
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.summarize_observations:
        if (args.root or args.observe_only or args.observation_receipt or args.no_boot_packet
                or args.boot_packet_file or args.installed_release_sha is not None):
            parser.error("--summarize-observations accepts only receipt paths and --json")
        try:
            result = summarize_observations(args.summarize_observations)
        except (ObservationEvidenceError, OSError, FilesystemSecurityError) as exc:
            print(f"observation evidence unavailable: {type(exc).__name__}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2 if result["failures"] or result["observer_failure_count"] else 0
    if args.installed_release_sha is not None:
        if (not args.observe_only or not args.observation_receipt
                or args.root is not None or args.boot_packet_file is not None):
            parser.error("--installed-release-sha requires --observe-only and --observation-receipt without --root or --boot-packet-file")
    if args.observation_receipt:
        if not args.observe_only:
            parser.error("--observation-receipt requires --observe-only")
        # Retain the existing JSON owner report; there is no action-changing path.
        args.json = True
        origin = "saved_file" if args.boot_packet_file else "not_collected" if args.no_boot_packet else "owner_collected"
        def observe(runtime_root=None):
            if runtime_root is not None:
                # Only the installed source/config owner can supply this path.
                args.root = str(runtime_root)
            return _run(args)
        try:
            code, out, err = capture_observation(
                args.observation_receipt, observe,
                runtime_root=None if args.installed_release_sha is not None else Path(args.root).resolve() if args.root else _ROOT,
                boot_packet_origin=origin,
                source_files=() if args.installed_release_sha is not None else (
                              Path(__file__), Path(observe_capacity_campaign.__code__.co_filename),
                              Path(observe_runtime_workload.__code__.co_filename)),
                installed_release_sha=args.installed_release_sha,
            )
        except (ObservationEvidenceError, OSError, FilesystemSecurityError) as exc:
            print(f"observation evidence unavailable: {type(exc).__name__}", file=sys.stderr)
            return 2
        sys.stdout.write(out)
        sys.stderr.write(err)
        return code
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
