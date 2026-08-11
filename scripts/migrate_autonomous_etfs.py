#!/usr/bin/env python3
"""Plan or apply the paper-only US Brain legacy-ETF migration.

Dry-run (default):
    python scripts/migrate_autonomous_etfs.py

Explicit paper apply:
    python scripts/migrate_autonomous_etfs.py --apply

Apply always queues the complete stock-only target and creates no fills.  The
scheduled open-settlement path alone owns trusted open-price paper fills.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bot  # noqa: E402,F401  # make the vendored Macro package importable
from portfolio import autonomous_migration  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="authorize the paper-only exit queue; omitted means a read-only dry run",
    )
    parser.add_argument("--asof", help="decision date (YYYY-MM-DD); defaults to today")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = autonomous_migration.migrate(asof=args.asof, apply=args.apply)
    print(json.dumps(result, indent=2, default=str, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
