"""Local proposal CLI. Never loads a Hermes profile or performs dispatch."""
from __future__ import annotations

import argparse
import os
import stat
import sys

from control_plane.executive_orchestration_result import canonical_bytes
from .adapter import MAX_BYTES, ProposalError
from .json_input import prepare_json


def _read_file(path: str) -> bytes:
    # O_NOFOLLOW closes final-component symlink races; nonblocking open and
    # fstat refuse FIFOs/devices/directories without reading or waiting on them.
    if not hasattr(os, "O_NOFOLLOW"):
        raise ProposalError("INPUT_UNAVAILABLE")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ProposalError("INPUT_UNAVAILABLE")
        if info.st_size > MAX_BYTES:
            raise ProposalError("INPUT_OVER_BUDGET")
        with os.fdopen(fd, "rb", closefd=False) as source:
            raw = source.read(MAX_BYTES + 1)
        after = os.fstat(fd)
        if (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ProposalError("INPUT_UNAVAILABLE")
        return raw
    finally:
        os.close(fd)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ProposalError("INVALID_INPUT")


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(allow_abbrev=False, description="Prepare an OMH graph proposal for the existing Executive v4 parser; never admit or dispatch.")
    parser.add_argument("--input", metavar="REGULAR_FILE", help="Read an explicit regular file instead of bounded UTF-8 stdin.")
    try:
        args = parser.parse_args(argv)
        raw = _read_file(args.input) if args.input else sys.stdin.buffer.read(MAX_BYTES + 1)
        result = prepare_json(raw)
    except ProposalError as exc:
        result = dict(state="REFUSED", reason=exc.reason)
    except (OSError, ValueError):
        result = dict(state="REFUSED", reason="INPUT_UNAVAILABLE")
    sys.stdout.buffer.write(canonical_bytes(result) + b"\n")
    return 2 if result["state"] == "REFUSED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
