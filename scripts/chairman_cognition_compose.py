#!/usr/bin/env python3
"""Compose and evaluate one Chairman-cognition source bundle without mutation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from control_plane.chairman_cognition import ChairmanCognitionError  # noqa: E402
from control_plane.chairman_cognition_sources import (  # noqa: E402
    ERROR_SCHEMA,
    ChairmanCognitionSourceError,
    evaluate_bundle,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="source bundle JSON path or '-' for stdin")
    parser.add_argument("--pretty", action="store_true", help="pretty-print output")
    return parser


def _reject_duplicate_object_pairs(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ChairmanCognitionSourceError("duplicate JSON object key")
        document[key] = value
    return document


def _loads(text: str) -> object:
    return json.loads(text, object_pairs_hook=_reject_duplicate_object_pairs)


def _read(path: str) -> object:
    if path == "-":
        return _loads(sys.stdin.read())
    return _loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        raw = _read(args.input)
        if not isinstance(raw, dict):
            raise ChairmanCognitionSourceError("top-level JSON must be an object")
        result = evaluate_bundle(raw)
    except (
        ChairmanCognitionError,
        ChairmanCognitionSourceError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ):
        print(
            json.dumps(
                {"schema": ERROR_SCHEMA, "error": "INVALID_SOURCE_BUNDLE"},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            result,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
