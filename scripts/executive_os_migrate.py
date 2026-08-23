#!/usr/bin/env python3
"""Explicit inert CLI for the offline Executive schema v3→v4 upgrade."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from control_plane.executive_backup import upgrade_v3_to_v4


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Upgrade one stopped, quiesced exact-v3 Executive SQLite database "
            "to exact v4 with barrier, backup, drill, and completion receipts."
        )
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--backup-directory", type=Path, required=True)
    parser.add_argument("--release-sha", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    receipt = upgrade_v3_to_v4(
        args.database,
        args.backup_directory,
        release_sha=args.release_sha,
    )
    print(json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
