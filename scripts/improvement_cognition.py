#!/usr/bin/env python3
"""Generate one private advisory improvement proposal draft; no persistence or dispatch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brain import improvement_cognition  # noqa: E402

MAX_INPUT_BYTES = 2_000_000


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Private grounded discovery report JSON")
    parser.add_argument(
        "--evaluation-packet",
        action="store_true",
        help="Emit only the public-safe independent-evaluation metadata packet.",
    )
    args = parser.parse_args(argv)

    try:
        with args.report.open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("input_too_large")
        report = json.loads(raw)
        draft = improvement_cognition.draft_proposals(report)
        value = (
            improvement_cognition.evaluation_packet(draft)
            if args.evaluation_packet
            else draft
        )
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        print("improvement_cognition: proposal draft unavailable", file=sys.stderr)
        return 2

    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
