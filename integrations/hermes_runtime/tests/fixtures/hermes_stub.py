#!/usr/bin/env python3
"""Stand-in for the pinned Hermes CLI. It never opens a public socket."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "-p":
        if len(args) < 3:
            return 2
        args = args[2:]
    if args[:4] == ["tools", "list", "--platform", "cli"]:
        stderr = os.environ.get("HERMES_STUB_STDERR", "")
        if stderr:
            sys.stderr.write(stderr)
        fixture = os.environ.get("HERMES_STUB_TOOLS")
        if not fixture:
            sys.stderr.write("FIXTURE_TOOLS_NOT_SET")
            return 2
        sys.stdout.write(Path(fixture).read_text(encoding="utf-8"))
        return 0
    if args and args[0] == "serve":
        host = _flag(args, "--host")
        if host != "127.0.0.1":
            sys.stderr.write("NON_LOOPBACK\n")
            return 2
        if os.environ.get("HERMES_STUB_MODE") == "exit":
            _count()
            return 1
        ready = os.environ.get("HERMES_STUB_READY")
        if ready:
            payload = {"pid": os.getpid(), "argv": args, "env_keys": sorted(os.environ)}
            tmp = ready + ".tmp"
            Path(tmp).write_text(json.dumps(payload), encoding="utf-8")
            os.replace(tmp, ready)
        _count()
        while True:
            time.sleep(0.2)
    sys.stderr.write("STUB_USAGE\n")
    return 2


def _flag(args: list[str], name: str) -> str:
    if name not in args:
        return ""
    index = args.index(name)
    if index + 1 >= len(args):
        return ""
    return args[index + 1]


def _count() -> None:
    path = os.environ.get("HERMES_STUB_COUNT")
    if not path:
        return
    file = Path(path)
    current = int(file.read_text(encoding="utf-8") or "0") if file.exists() else 0
    file.write_text(str(current + 1), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
