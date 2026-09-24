#!/usr/bin/env python3
"""Evaluate one Chairman-cognition JSON document without side effects."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from control_plane.chairman_cognition import (  # noqa: E402
    ERROR_SCHEMA,
    ChairmanCognitionError,
    evaluate_document,
)


class _DuplicateKeyError(ValueError):
    """A JSON object repeated a key before A1 closed-map validation."""


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError("duplicate JSON object key")
        result[key] = value
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON input path or '-' for stdin")
    parser.add_argument("--pretty", action="store_true", help="pretty-print output")
    return parser


def _read(path: str) -> object:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(text, object_pairs_hook=_strict_object)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        raw = _read(args.input)
        if not isinstance(raw, dict):
            raise ChairmanCognitionError("top-level JSON must be an object")
        packet = evaluate_document(raw)
    except (
        ChairmanCognitionError,
        _DuplicateKeyError,
        OSError,
        json.JSONDecodeError,
        UnicodeError,
    ):
        print(
            json.dumps(
                {"schema": ERROR_SCHEMA, "error": "INVALID_INPUT"},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            packet,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
