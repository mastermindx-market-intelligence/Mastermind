"""Fixed installed child for bounded canonical archive reads; no writes."""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
import sys

_CODE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_CODE_ROOT))
from control_plane.agentos_project_archive import read_from_macro_owner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--macro-root", required=True)
    parser.add_argument("--expected-macro-sha", required=True)
    parser.add_argument("--work-refs-json", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    with open("/dev/null", "w") as discard, redirect_stdout(discard), redirect_stderr(discard):
        value = read_from_macro_owner(macro_root=Path(args.macro_root), expected_macro_sha=args.expected_macro_sha,
                                      work_refs=json.loads(args.work_refs_json), timeout=args.timeout)
    print(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
