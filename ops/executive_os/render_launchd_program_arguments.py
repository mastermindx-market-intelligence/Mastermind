"""Atomically replace a launchd plist ProgramArguments array."""
from __future__ import annotations

import os
import plistlib
import stat
import sys
import tempfile
from pathlib import Path
from typing import Sequence


class LaunchdPlistRenderError(RuntimeError):
    pass


def render_program_arguments(path: Path, arguments: Sequence[str]) -> None:
    lexical = Path(path)
    if not lexical.is_absolute():
        raise LaunchdPlistRenderError("launchd plist path must be absolute")
    info = lexical.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise LaunchdPlistRenderError("launchd plist must be a direct single-link file")
    if not arguments or any(not value or "\x00" in value for value in arguments):
        raise LaunchdPlistRenderError("launchd ProgramArguments are invalid")

    with lexical.open("rb") as handle:
        payload = plistlib.load(handle)
    existing = payload.get("ProgramArguments") if isinstance(payload, dict) else None
    if not isinstance(existing, list) or not all(isinstance(value, str) for value in existing):
        raise LaunchdPlistRenderError("launchd plist has no string ProgramArguments array")
    payload["ProgramArguments"] = list(arguments)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{lexical.name}.", dir=lexical.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            plistlib.dump(payload, handle, fmt=plistlib.FMT_XML, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_info = os.fstat(handle.fileno())
            if (temporary_info.st_uid, temporary_info.st_gid) != (
                info.st_uid,
                info.st_gid,
            ):
                os.fchown(handle.fileno(), info.st_uid, info.st_gid)
            os.fchmod(handle.fileno(), stat.S_IMODE(info.st_mode))
        os.replace(temporary, lexical)
        directory = os.open(lexical.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if len(raw) < 3 or raw[1] != "--":
        raise LaunchdPlistRenderError(
            "usage: render_launchd_program_arguments.py /absolute/plist -- ARG [ARG ...]"
        )
    render_program_arguments(Path(raw[0]), raw[2:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
