#!/usr/bin/env python3
"""scripts/fabric_job_view.py — operator CLI for the truthful fabric view.

Read-only.  It prints one ``mastermind.fabric_job_view.v1`` document for a
single Executive Runtime root, or enumerates the runtime's self-rooted Job ids
(seat ruling R2) so an operator can find a root id to render.  It writes
nothing: no state file, no cache, no log, no daemon, no socket, and no MCP
server (``integrations.executive_mcp`` is another lane's custody).

  fabric_job_view.py --runtime-root <abs> --root-job-id <id> [--control-config <abs>] [--json]
  fabric_job_view.py --list-roots --runtime-root <abs> [--limit N] [--json]
  fabric_job_view.py --describe [--json]

Human mode mirrors the Control Room's existing print shape
(``scripts/chairman_control_room.py:1435-1490``): schema, generated_at,
counts, the ``degraded`` list (or ``degraded: none``), then
``capability: <state>``.  ``--describe`` prints the A16 capability object with
``installed: false`` and opens no runtime at all.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if os.fspath(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_REPO_ROOT))

from control_plane import fabric_job_view  # noqa: E402  (after sys.path bootstrap)


def _print_degraded(entries) -> None:
    if entries:
        print("degraded:")
        for entry in entries:
            print(f"  - {entry}")
    else:
        print("degraded: none")


def _print_view(document) -> None:
    print(f"schema: {document['schema']}")
    print(f"generated_at: {document['generated_at']}")
    print(f"runtime.root: {document['runtime']['root']}")
    print(f"runtime.db_present: {document['runtime']['db_present']}")
    root = document["root"]
    print(f"root: {root['job_id'] if root is not None else 'none'}")
    print(f"children: {len(document['children'])}")
    print(f"unjoined_job_count: {document['unjoined_job_count']}")
    print(f"missingness: {len(document['missingness'])}")
    _print_degraded(document["degraded"])
    print(f"capability: {document['capability']['state']}")


def _print_roots(document) -> None:
    print(f"schema: {document['schema']}")
    print(f"generated_at: {document['generated_at']}")
    print(f"runtime.root: {document['runtime']['root']}")
    print(f"roots: {document['count']} of {document['total']}")
    for row in document["roots"]:
        print(f"  - {row['job_id']} status={row['status']} depth={row['depth']}")
    _print_degraded(document["degraded"])


def _print_capability(capability) -> None:
    print(f"capability: {capability['state']}")
    print(f"installed: {capability['installed']}")
    print(f"version: {capability['version']}")
    print(f"detail: {capability['detail']}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render one truthful fabric root from the Executive Runtime "
            "(read-only; renders explicit unknowns instead of guessing)."
        )
    )
    parser.add_argument("--runtime-root", default=None)
    parser.add_argument("--root-job-id", default=None)
    parser.add_argument("--control-config", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--list-roots", action="store_true", dest="list_roots")
    parser.add_argument("--limit", type=int, default=fabric_job_view.LIST_ROOTS_LIMIT)
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)

    if args.describe:
        capability = fabric_job_view.describe_capability()
        if args.json:
            print(json.dumps(capability, indent=2, sort_keys=True))
        else:
            _print_capability(capability)
        return 0

    if not args.runtime_root:
        print("--runtime-root is required", file=sys.stderr)
        return 2

    if args.list_roots:
        document = fabric_job_view.list_roots(
            args.runtime_root,
            limit=args.limit,
            control_config_path=args.control_config,
        )
        if args.json:
            print(json.dumps(document, indent=2, sort_keys=True))
        else:
            _print_roots(document)
        return 0

    if not args.root_job_id:
        print("--root-job-id is required (or use --list-roots)", file=sys.stderr)
        return 2

    document = fabric_job_view.read_fabric_view(
        args.runtime_root,
        args.root_job_id,
        control_config_path=args.control_config,
    )
    if args.json:
        print(json.dumps(document, indent=2, sort_keys=True))
    else:
        _print_view(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
