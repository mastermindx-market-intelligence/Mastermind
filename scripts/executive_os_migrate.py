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
    upgrade_v3_to_v4, upgrade_v4_to_v5, upgrade_v5_to_v6,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one explicitly selected offline Executive schema transition "
            "with barrier, backup, drill, and completion receipts; never chain upgrades."
        )
    )
    parser.add_argument("--transition", choices=("v3-to-v4", "v4-to-v5", "v5-to-v6"),
                        default="v3-to-v4")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--backup-directory", type=Path, required=True)
    parser.add_argument("--release-sha", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    upgrade = {
        "v3-to-v4": upgrade_v3_to_v4,
        "v4-to-v5": upgrade_v4_to_v5,
        "v5-to-v6": upgrade_v5_to_v6,
    }[args.transition]
    receipt = upgrade(
        args.database,
        args.backup_directory,
        release_sha=args.release_sha,
    )
    print(json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
