#!/usr/bin/env python3
"""scripts.operation_assurance — OLS-A1 bounded report-only CLI (OLS-F0).

Usage
-----
    operation-assurance MODEL.json [--pretty]
    operation-assurance -           [--pretty]      (model JSON on stdin)

The CLI performs no write other than stdout/stderr, has no trusted-source or
trusted-replay flag, and is not an implicit admission gate: a valid unsafe
model still produces a normal report and exit 0.

Exit contract
-------------
0   a valid report, including UNSAFE_COUNTEREXAMPLE / BOUNDED_NO_COUNTEREXAMPLE
    / INCONCLUSIVE_MODEL_GAP results;
2   malformed JSON or a refused closed model (parser refusal);
3   internal checker/report refusal (never a partially trusted report).

Controlling sources (exact precedence): see control_plane.operation_assurance_model
module docstring.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

if __name__ == "__main__":  # pragma: no cover - direct-execution import shim
    _ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.operation_assurance_checker import CheckerInternalError, run_checker
from control_plane.operation_assurance_model import MAX_INPUT_BYTES, ModelParseError, parse_model_bytes
from control_plane.operation_assurance_report import ReportValidationError

USAGE = "usage: operation-assurance MODEL.json|- [--pretty]"


def _generated_at_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_source(source: str) -> bytes:
    if source == "-":
        return sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    with open(source, "rb") as f:  # noqa: PTH123 - explicit caller-supplied read path only
        return f.read(MAX_INPUT_BYTES + 1)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    pretty = "--pretty" in argv
    positional = [a for a in argv if a != "--pretty"]
    if len(positional) != 1:
        print(USAGE, file=sys.stderr)
        return 2

    source = positional[0]
    try:
        raw = _read_source(source)
    except OSError:
        print("INPUT_READ_ERROR: could not read the supplied model input", file=sys.stderr)
        return 2

    try:
        model = parse_model_bytes(raw)
    except ModelParseError as exc:
        print(f"{exc.reason_code}: model refused", file=sys.stderr)
        return 2
    except Exception:  # pragma: no cover - defense in depth, never a healthy default
        print("PARSER_INTERNAL_ERROR: model refused", file=sys.stderr)
        return 2

    try:
        report = run_checker(model, generated_at=_generated_at_now())
    except (CheckerInternalError, ReportValidationError) as exc:
        reason = getattr(exc, "reason_code", "CHECKER_INTERNAL_ERROR")
        print(f"{reason}: checker refused to emit a report", file=sys.stderr)
        return 3
    except Exception:  # pragma: no cover - defense in depth, never a healthy default
        print("CHECKER_INTERNAL_ERROR: checker refused to emit a report", file=sys.stderr)
        return 3

    if pretty:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(report.to_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
