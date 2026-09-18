#!/usr/bin/env python3
"""Emit one bounded Web-Sol continuation packet from canonical Agent OS reads."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.session_truth_acquire import collect_agentos  # noqa: E402
from control_plane.web_sol_continuation import (  # noqa: E402
    WebSolContinuationError,
    build_continuation,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read Agent OS through its existing read-only CLI and emit one strict "
            "continuation packet for a fresh Web Sol conversation."
        )
    )
    parser.add_argument("--workstream", required=True, help="exact WS:<KEY> identity")
    parser.add_argument("--macro-root", help="Macro checkout containing canonical Agent OS")
    parser.add_argument("--now", help="freeze Agent OS observation time (ISO-8601)")
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        agentos = collect_agentos(
            args.macro_root,
            [args.workstream],
            environ=os.environ,
            now=args.now,
            timeout=args.timeout,
        )
        packet = build_continuation(agentos, args.workstream)
    except (WebSolContinuationError, RuntimeError, ValueError) as exc:
        sys.stderr.write(f"web-sol-continuation refused: {exc}\n")
        return 2
    sys.stdout.write(json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
