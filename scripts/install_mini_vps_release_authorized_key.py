#!/usr/bin/env python3
"""Install one restricted mini release public key into the attended M2 operator account."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import socket
import stat
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.render_mini_vps_release_authorized_key import RenderError, render


AUTHORIZED_KEYS = Path("/Users/chriswong/.ssh/authorized_keys")
M2_HOST = "m2studio"
M2_HOME = Path("/Users/chriswong")
MAX_AUTHORIZED_KEYS_BYTES = 128 * 1024


class InstallError(RuntimeError):
    pass


def _assert_m2_operator() -> None:
    host = socket.gethostname().split(".", 1)[0].lower()
    if host != M2_HOST or Path.home().resolve() != M2_HOME:
        raise InstallError("restricted key installer must run as the attended M2 operator")
def _read_authorized_keys(path: Path) -> tuple[bytes, os.stat_result]:
    try:
        info = path.lstat()
    except OSError as exc:
        raise InstallError("M2 authorized_keys is unavailable") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_uid != os.getuid()
        or info.st_nlink != 1
        or info.st_size > MAX_AUTHORIZED_KEYS_BYTES
    ):
        raise InstallError("M2 authorized_keys has unsafe metadata")
    raw = path.read_bytes()
    if len(raw) > MAX_AUTHORIZED_KEYS_BYTES or b"\x00" in raw:
        raise InstallError("M2 authorized_keys is outside the bounded format")
    return raw, info


def _atomic_replace(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.release-key.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temporary, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short authorized_keys write")
            view = view[written:]
        os.fchmod(fd, 0o600)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(temporary, path)
        parent_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def install(public_key: Path, label: str, *, path: Path = AUTHORIZED_KEYS) -> dict[str, object]:
    _assert_m2_operator()
    try:
        rendered = render(public_key, label)
    except RenderError as exc:
        raise InstallError(str(exc)) from exc

    lock_path = path.with_name(".mastermind-vps-release-authorized-keys.lock")
    lock_flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    lock_fd = os.open(lock_path, lock_flags, 0o600)
    try:
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        raw, _ = _read_authorized_keys(path)
        text = raw.decode("utf-8", errors="strict")
        marker = f"mastermind-release-{label}"
        matches = [line for line in text.splitlines() if line.rstrip().endswith(marker)]
        if matches:
            if matches == [rendered]:
                changed = False
            else:
                raise InstallError("a different release key already owns this mini label")
        else:
            prefix = text
            if prefix and not prefix.endswith("\n"):
                prefix += "\n"
            payload = (prefix + rendered + "\n").encode("utf-8")
            if len(payload) > MAX_AUTHORIZED_KEYS_BYTES:
                raise InstallError("authorized_keys would exceed the bounded size")
            _atomic_replace(path, payload)
            changed = True
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
    line_sha256 = hashlib.sha256((rendered + "\n").encode("utf-8")).hexdigest()
    return {
        "label": label,
        "authorized_keys": str(path),
        "line_sha256": line_sha256,
        "changed": changed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-key-file", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = install(args.public_key_file.expanduser().resolve(), args.label)
    except (InstallError, OSError, UnicodeError) as exc:
        print(f"release authorized-key install refused: {exc}", file=sys.stderr)
        return 2
    print(
        f"label={receipt['label']} changed={str(receipt['changed']).lower()} "
        f"line_sha256={receipt['line_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
