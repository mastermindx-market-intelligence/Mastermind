"""Fixed installed child for canonical Agent OS plan reads; no network or writes."""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
import sys

_CODE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_CODE_ROOT))
from control_plane.agentos_project_plan import read_from_macro_owner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--macro-root", required=True)
    parser.add_argument("--expected-macro-sha", required=True)
    parser.add_argument("--work-ref", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--continuity", action="store_true")
    args = parser.parse_args()
    class ClosedDiagnostics:
        # The owner may print a missing-dependency diagnostic before refusing.
        # This fixed public child emits only its closed JSON contract; no raw
        # source/error/payload text is retained in an auxiliary output buffer.
        def write(self, value):
            return len(value)
        def flush(self):
            pass
    sink = ClosedDiagnostics()
    with redirect_stdout(sink), redirect_stderr(sink):
        value = read_from_macro_owner(macro_root=Path(args.macro_root),
            expected_macro_sha=args.expected_macro_sha, work_ref=args.work_ref,
            timeout=args.timeout, include_continuity=args.continuity)
    print(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
