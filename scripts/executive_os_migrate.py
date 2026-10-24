#!/usr/bin/env python3
"""Explicit inert CLI for the closed offline Executive schema upgrades."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from control_plane.executive_backup import (
    upgrade_v3_to_v4, upgrade_v4_to_v5, upgrade_v5_to_v6, upgrade_v6_to_v7,
    inspect_v5_to_v6_pre_census_barrier,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one explicitly selected offline Executive schema transition "
            "with barrier, backup, drill, and completion receipts; never chain upgrades."
        )
    )
    transition = parser.add_mutually_exclusive_group()
    transition.add_argument("--transition",
                            choices=("v3-to-v4", "v4-to-v5", "v5-to-v6", "v6-to-v7"),
                            default="v3-to-v4")
    transition.add_argument("--from-version", type=int, choices=(3, 4, 5, 6),
                            help="Compatibility alias selecting one closed transition.")
    transition.add_argument("--inspect-v5-to-v6-pre-census-barrier", action="store_true",
                            help="Read only the fixed original barrier metadata; no database access.")
    transition.add_argument("--resume-v5-to-v6-pre-census", action="store_true",
                            help="Consume the fixed one-use qualification for the SAME operation.")
    parser.add_argument("--expected-operation-id")
    parser.add_argument("--expected-barrier-sha256")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--backup-directory", type=Path)
    parser.add_argument("--release-sha")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.inspect_v5_to_v6_pre_census_barrier:
        if any(value is not None for value in (args.database, args.backup_directory,
                args.release_sha, args.expected_operation_id, args.expected_barrier_sha256)):
            parser.error("fixed-leaf inspection accepts no path, release or recovery selectors")
        print(json.dumps(inspect_v5_to_v6_pre_census_barrier(), sort_keys=True, separators=(",", ":")))
        return 0
    if any(value is None for value in (args.database, args.backup_directory, args.release_sha)):
        parser.error("a transition requires --database, --backup-directory and --release-sha")
    if args.resume_v5_to_v6_pre_census:
        if args.expected_operation_id is None or args.expected_barrier_sha256 is None:
            parser.error("continuation requires exact original operation and barrier CAS selectors")
        from control_plane.executive_backup import resume_v5_to_v6_pre_census
        receipt = resume_v5_to_v6_pre_census(args.database, args.backup_directory,
            release_sha=args.release_sha, expected_operation_id=args.expected_operation_id,
            expected_barrier_sha256=args.expected_barrier_sha256)
        print(json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":")))
        return 0
    if args.expected_operation_id is not None or args.expected_barrier_sha256 is not None:
        parser.error("recovery CAS selectors are exclusive to the continuation action")
    selected = (f"v{args.from_version}-to-v{args.from_version + 1}"
                if args.from_version is not None else args.transition)
    upgrade = {
        "v3-to-v4": upgrade_v3_to_v4,
        "v4-to-v5": upgrade_v4_to_v5,
        "v5-to-v6": upgrade_v5_to_v6,
        "v6-to-v7": upgrade_v6_to_v7,
    }[selected]
    receipt = upgrade(
        args.database,
        args.backup_directory,
        release_sha=args.release_sha,
    )
    print(json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
