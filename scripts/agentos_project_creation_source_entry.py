"""Fixed installed source-only child; emits one closed JSON observation."""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from control_plane.agentos_project_creation_source import read_from_macro_owner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--macro-root", required=True)
    parser.add_argument("--expected-macro-sha", required=True)
    parser.add_argument("--record-commit", required=True)
    parser.add_argument("--work-ref", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    source = None
    reason = None
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        try:
            source = read_from_macro_owner(macro_root=Path(args.macro_root),
                expected_macro_sha=args.expected_macro_sha, record_commit=args.record_commit, work_ref=args.work_ref,
                timeout=args.timeout)
        except (Exception, SystemExit) as exc:
            reason = {"source_changed": "SOURCE_CHANGED", "source_mismatch": "SOURCE_MISMATCH"}.get(
                str(exc) if type(exc) is ValueError else "", "SOURCE_UNAVAILABLE")
    result = {"schema": "mastermind.agentos_project_creation_source.v1", "work_ref": args.work_ref,
        "availability": "AVAILABLE" if source is not None else "UNAVAILABLE", "source": source, "reason": reason}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
