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
    parser.add_argument("--input-kind", choices=("observations", "nw-reflection"), default="observations")
    parser.add_argument("--source-revision", help="Exact observer contract revision for an owner snapshot")
    parser.add_argument("--contract-sha256", help="SHA-256 of that exact NW reflection contract file")
    args = parser.parse_args(argv)
    try:
        with args.input.open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("input_too_large")
        if args.input_kind == "nw-reflection":
            from brain import improvement_discovery_nw
            report = improvement_discovery_nw.evaluate_owner_snapshot(json.loads(raw),
                source_revision=args.source_revision, contract_sha256=args.contract_sha256,
                observed_at=args.now)
        else:
            if args.source_revision is not None or args.contract_sha256 is not None:
                raise ValueError("owner_identity_requires_owner_input")
            report = discovery.evaluate(json.loads(raw), now=args.now)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        print("improvement_discovery: invalid or unavailable input", file=sys.stderr)
        return 2
    if args.format == "markdown":
        if args.input_kind == "nw-reflection":
            print(improvement_discovery_nw.render_owner_brief(report))
        else:
            print(discovery.render_markdown(report))
    else:
        value = discovery.agenda_projection(report) if args.format == "public-summary" else report
        print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
