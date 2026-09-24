#!/usr/bin/env python3
"""Read one bounded owner snapshot and print advice. No persistence or dispatch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from brain import improvement_discovery as discovery  # noqa: E402

MAX_INPUT_BYTES = 2_000_000


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--now", required=True, help="Explicit timezone-aware observation clock")
    parser.add_argument("--format", choices=("json", "markdown", "public-summary"), default="json")
    args = parser.parse_args(argv)
    try:
        with args.input.open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("input_too_large")
        report = discovery.evaluate(json.loads(raw), now=args.now)
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        print("improvement_discovery: invalid or unavailable input", file=sys.stderr)
        return 2
    if args.format == "markdown":
        print(discovery.render_markdown(report))
    else:
        value = discovery.agenda_projection(report) if args.format == "public-summary" else report
        print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
