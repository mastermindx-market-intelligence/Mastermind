"""Fixed installed metadata child; no caller-selected command or source path."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from control_plane.agentos_project_discovery import read_from_macro_owner


def main():
    # This is the existing bounded subprocess PIPE destination, never a log,
    # terminal or caller-selected output file. It grants no principal rights.
    output = sys.stdout.buffer
    if output.fileno() != sys.stdout.fileno() or not stat.S_ISFIFO(os.fstat(output.fileno()).st_mode):
        raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
    parser = argparse.ArgumentParser()
    parser.add_argument('--macro-root', required=True)
    parser.add_argument('--expected-macro-sha', required=True)
    parser.add_argument('--work-ref', required=True)
    parser.add_argument('--code-root', required=True)
    parser.add_argument('--code-commit', required=True)
    parser.add_argument('--observed-at-ms', required=True, type=int)
    parser.add_argument('--timeout', type=float, default=10.0)
    args = parser.parse_args()

    class ClosedDiagnostics:
        def write(self, value): return len(value)
        def flush(self): pass

    sink = ClosedDiagnostics()
    with redirect_stdout(sink), redirect_stderr(sink):
        value = read_from_macro_owner(macro_root=Path(args.macro_root), expected_macro_sha=args.expected_macro_sha,
            work_ref=args.work_ref, code_root=Path(args.code_root), code_commit=args.code_commit,
            observed_at_ms=args.observed_at_ms, timeout=args.timeout)
    packet = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8') + b'\n'
    if len(packet) > 262144:
        raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
    if output.write(packet) != len(packet):
        raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
    output.flush()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        # No path, traceback, source body or exception text crosses stderr.
        print('PROJECT_DISCOVERY_UNAVAILABLE', file=sys.stderr)
        raise SystemExit(2)
