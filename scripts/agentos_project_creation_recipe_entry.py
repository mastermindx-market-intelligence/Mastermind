#!/usr/bin/env python3
"""Fixed private input/read-only canonical compiler child. Emits closed JSON only."""
from __future__ import annotations
import argparse
import contextlib
import json
import os
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--macro-root", required=True)
    parser.add_argument("--expected-macro-sha", required=True)
    parser.add_argument("--timeout", required=True, type=float)
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(32769)
        if len(raw) > 32768: raise ValueError()
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value: raise ValueError()
                value[key] = item
            return value
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
        if (type(body) is not dict or set(body) != {"schema", "code_commit", "request"}
                or body["schema"] != "mastermind.project_creation_recipe_capture_request.v1"):
            raise ValueError()
        from control_plane.agentos_project_creation_recipe import capture_creation_recipe
        with open(os.devnull, "w") as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
            result = capture_creation_recipe(macro_root=args.macro_root,
                expected_macro_sha=args.expected_macro_sha, code_commit=body["code_commit"],
                request=body["request"], timeout=args.timeout)
    except (Exception, SystemExit):
        print('{"schema":"mastermind.project_creation_recipe_unavailable.v1"}')
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
