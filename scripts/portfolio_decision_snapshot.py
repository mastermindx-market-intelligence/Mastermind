#!/usr/bin/env python3
"""scripts.portfolio_decision_snapshot — explicit operator CLI for the V3 Decision Snapshot.

Three subcommands only:

- ``compose`` is the sole S0 writer. It requires explicit UTC ``--decision-cutoff`` and
  ``--recorded-at`` (never defaulted) and prints only a bounded compose receipt — never
  the full snapshot body.
- ``status`` and ``show`` are read-only: they never call ``decision_snapshot.create_snapshot``
  and print a compact verified manifest, or a typed ``NO_SNAPSHOT`` object when nothing has
  been composed yet.

Every success or error output is exactly one JSON object, written with the existing
canonical serializer (``control_plane.wake_events.canonical_json_bytes`` — no second
serializer is defined here). Errors distinguish ``invalid_request``, ``not_found``,
``corrupt_snapshot``, and ``internal_error``; none of them ever echo a filesystem path,
raw exception text, or snapshot payload bytes. Argument-parsing failures also return one
closed JSON object on stderr with exit code 2 — argparse's default usage prose and
``SystemExit`` are intercepted before they can escape.

The CLI exposes no path, root, url, or output override: the storage root is the fixed,
displayed-only string ``data/shadow/decision_snapshots/autonomous``, and the only accepted
``--book`` value is the lowercase literal ``autonomous``.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

if __name__ == "__main__":  # pragma: no cover - direct-execution import shim
    _ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.wake_events import canonical_json_bytes
from portfolio import decision_snapshot
from portfolio import decision_snapshot_contracts as contracts

_BOOK_CHOICES = ("autonomous",)
_WRITE_ROOT = "data/shadow/decision_snapshots/autonomous"

_COMPOSE_RECEIPT_SCHEMA = "mastermind.portfolio_decision_snapshot.compose_receipt.v1"
_STATUS_SCHEMA = "mastermind.portfolio_decision_snapshot.cli_status.v1"
_SHOW_SCHEMA = "mastermind.portfolio_decision_snapshot.cli_show.v1"
_ERROR_SCHEMA = "mastermind.portfolio_decision_snapshot.cli_error.v1"

_STATUS_INVALID_REQUEST = "invalid_request"
_STATUS_NOT_FOUND = "not_found"
_STATUS_CORRUPT = "corrupt_snapshot"
_STATUS_INTERNAL = "internal_error"

_GENERIC_ERROR_MESSAGES = {
    _STATUS_NOT_FOUND: "no matching snapshot was found",
    _STATUS_CORRUPT: "a persisted snapshot failed verification",
    _STATUS_INTERNAL: "an internal failure occurred",
}

_MANIFEST_FIELDS = (
    "book",
    "snapshot_id",
    "decision_cutoff",
    "recorded_at",
    "state",
    "coverage_state",
    "summary",
    "correction",
    "authority",
)

_DEFAULT_OFFSET = 0
_DEFAULT_LIMIT = 50


class _CLIArgumentError(Exception):
    """Raised in place of argparse's default prose-and-``SystemExit`` error path."""


class _JSONErrorArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise _CLIArgumentError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _JSONErrorArgumentParser(
        prog="portfolio_decision_snapshot.py",
        description="Operator CLI for V3 Decision Snapshot evidence (read-mostly; compose is the sole writer).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    compose = sub.add_parser(
        "compose", help="Compose and persist one immutable decision snapshot."
    )
    compose.add_argument("--book", required=True, choices=_BOOK_CHOICES)
    compose.add_argument("--decision-cutoff", required=True)
    compose.add_argument("--recorded-at", required=True)

    status = sub.add_parser(
        "status", help="Print the latest verified snapshot manifest, read-only."
    )
    status.add_argument("--book", required=True, choices=_BOOK_CHOICES)

    show = sub.add_parser(
        "show", help="Print a verified snapshot manifest or bounded section page, read-only."
    )
    show.add_argument("--book", required=True, choices=_BOOK_CHOICES)
    show.add_argument("--snapshot-id")
    show.add_argument("--section")
    show.add_argument("--offset", type=int, default=_DEFAULT_OFFSET)
    show.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)

    return parser


def _write_json(stream, obj: Mapping[str, Any]) -> None:
    stream.write(canonical_json_bytes(obj).decode("ascii"))
    stream.write("\n")


def _write_error(stream, status: str, message: str) -> None:
    _write_json(stream, {"schema": _ERROR_SCHEMA, "status": status, "error": message})


def _compact_manifest(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {field: snapshot[field] for field in _MANIFEST_FIELDS}


def _run_compose(args: argparse.Namespace) -> int:
    result = decision_snapshot.create_snapshot(
        args.book,
        decision_cutoff=args.decision_cutoff,
        recorded_at=args.recorded_at,
    )
    receipt = {
        "schema": _COMPOSE_RECEIPT_SCHEMA,
        "book": args.book,
        "snapshot_id": result["snapshot_id"],
        "state": result["state"],
        "coverage_state": result["coverage_state"],
        "write_root": _WRITE_ROOT,
        "write_permitted_outside_shadow": False,
        "execution_authority": False,
    }
    _write_json(sys.stdout, receipt)
    return 0


def _run_status(args: argparse.Namespace) -> int:
    snapshot = decision_snapshot.latest_snapshot(args.book)
    if snapshot is None:
        _write_json(
            sys.stdout,
            {"schema": _STATUS_SCHEMA, "book": args.book, "status": "NO_SNAPSHOT"},
        )
        return 0
    _write_json(
        sys.stdout,
        {
            "schema": _STATUS_SCHEMA,
            "book": args.book,
            "status": "OK",
            "manifest": _compact_manifest(snapshot),
        },
    )
    return 0


def _run_show(args: argparse.Namespace) -> int:
    if args.snapshot_id is not None:
        snapshot = decision_snapshot.load_snapshot(args.book, args.snapshot_id)
    else:
        snapshot = decision_snapshot.latest_snapshot(args.book)
        if snapshot is None:
            _write_json(
                sys.stdout,
                {"schema": _SHOW_SCHEMA, "book": args.book, "status": "NO_SNAPSHOT"},
            )
            return 0

    if args.section is None:
        _write_json(
            sys.stdout,
            {
                "schema": _SHOW_SCHEMA,
                "book": args.book,
                "status": "OK",
                "manifest": _compact_manifest(snapshot),
            },
        )
        return 0

    page = decision_snapshot.section_page(
        snapshot, args.section, offset=args.offset, limit=args.limit
    )
    _write_json(
        sys.stdout,
        {
            "schema": _SHOW_SCHEMA,
            "book": args.book,
            "status": "OK",
            "snapshot_id": snapshot["snapshot_id"],
            "decision_cutoff": snapshot["decision_cutoff"],
            "recorded_at": snapshot["recorded_at"],
            "state": snapshot["state"],
            "coverage_state": snapshot["coverage_state"],
            "correction": dict(snapshot["correction"]),
            "section": page,
        },
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except _CLIArgumentError as exc:
        _write_error(sys.stderr, _STATUS_INVALID_REQUEST, str(exc))
        return 2

    try:
        if args.command == "compose":
            return _run_compose(args)
        if args.command == "status":
            return _run_status(args)
        if args.command == "show":
            return _run_show(args)
        raise AssertionError(f"unhandled command {args.command!r}")  # pragma: no cover
    except decision_snapshot.SnapshotNotFound:
        _write_error(sys.stderr, _STATUS_NOT_FOUND, _GENERIC_ERROR_MESSAGES[_STATUS_NOT_FOUND])
        return 1
    except decision_snapshot.SnapshotCorrupt:
        _write_error(sys.stderr, _STATUS_CORRUPT, _GENERIC_ERROR_MESSAGES[_STATUS_CORRUPT])
        return 1
    except (decision_snapshot.SnapshotInvalidRequest, contracts.DecisionSnapshotContractError):
        _write_error(sys.stderr, _STATUS_INVALID_REQUEST, "the request was invalid")
        return 1
    except Exception:
        _write_error(sys.stderr, _STATUS_INTERNAL, _GENERIC_ERROR_MESSAGES[_STATUS_INTERNAL])
        return 1


if __name__ == "__main__":
    sys.exit(main())
