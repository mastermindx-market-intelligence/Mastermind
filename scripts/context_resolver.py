#!/usr/bin/env python3
"""Render one bounded Mastermind context pack from an existing Session Truth receipt."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import TextIO

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.context_resolver import (  # noqa: E402
    ContextResolverError,
    build_context_pack,
    render_context_pack,
)
from control_plane.session_truth_contract import canonical_json  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a read-only task-scoped context pack from Session Truth."
    )
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--prior-pack")
    parser.add_argument("--max-items", type=int, default=64)
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser


def _load(path: str) -> object:
    raw = Path(path).read_bytes()
    if len(raw) > 2 * 1024 * 1024:
        raise ContextResolverError("input file exceeds byte bound")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContextResolverError("input file is not valid UTF-8 JSON") from exc


def _error(stream: TextIO, message: str) -> int:
    safe = " ".join(message.replace("\r", " ").replace("\n", " ").split())
    stream.write(f"context-resolver error: {safe[:220] or 'invalid input'}\n")
    return 2


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args = _parser().parse_args(argv)
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    try:
        receipt = _load(args.receipt)
        prior = _load(args.prior_pack) if args.prior_pack else None
        pack = build_context_pack(
            receipt,
            task=args.task,
            prior_pack=prior,
            max_items=args.max_items,
        )
        rendered = (
            canonical_json(pack) + "\n" if args.emit_json else render_context_pack(pack)
        )
    except (OSError, ContextResolverError) as exc:
        return _error(err, str(exc))
    out.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
