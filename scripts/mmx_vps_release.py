#!/usr/bin/env python3
"""Mini-host client for the fixed M2 Executive production-release relay."""
from __future__ import annotations

import argparse
import os
import re
import socket
import stat
import subprocess
import sys
from pathlib import Path
from typing import Sequence


_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
_MINI_LABEL = re.compile(r"^mini[1-9][0-9]*$")
_TARGET = "m2studio"
_USER = "chriswong"
_KEY = Path.home() / ".ssh" / "m2_release"
_SSH = Path("/usr/bin/ssh")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "deploy", "status"))
    parser.add_argument("--commit-sha")
    parser.add_argument("--request-id")
    return parser


def _key_path() -> Path:
    path = _KEY
    try:
        info = path.lstat()
    except OSError as exc:
        raise RuntimeError("dedicated M2 release key is unavailable") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
        or info.st_uid != os.getuid()
    ):
        raise RuntimeError("dedicated M2 release key has unsafe metadata")
    return path


def _local_label() -> str:
    label = socket.gethostname().split(".", 1)[0].lower()
    if _MINI_LABEL.fullmatch(label) is None:
        raise RuntimeError("local host is not a recognized mini fleet identity")
    return label


def _remote_command(args: argparse.Namespace, *, label: str) -> tuple[str, int]:
    if _MINI_LABEL.fullmatch(label) is None:
        raise ValueError("invalid mini fleet identity")
    if args.action == "preflight":
        if args.commit_sha is not None or args.request_id is not None:
            raise ValueError("preflight accepts no effect arguments")
        return "preflight", 30
    if args.request_id is None or _REQUEST_ID.fullmatch(args.request_id) is None:
        raise ValueError("deploy/status require a bounded --request-id")
    if not args.request_id.startswith(f"{label}-"):
        raise ValueError("request id must be bound to this mini identity")
    if args.action == "status":
        if args.commit_sha is not None:
            raise ValueError("status does not accept --commit-sha")
        return f"status {args.request_id}", 30
    if args.commit_sha is None or _SHA40.fullmatch(args.commit_sha) is None:
        raise ValueError("deploy requires an exact lowercase 40-hex --commit-sha")
    return f"deploy {args.commit_sha} {args.request_id}", 720


def _ssh_argv(command: str, key: Path) -> list[str]:
    return [
        str(_SSH),
        "-F",
        "/dev/null",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "RequestTTY=no",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=yes",
        "-l",
        _USER,
        "-i",
        str(key),
        _TARGET,
        command,
    ]


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(list(sys.argv[1:] if argv is None else argv))
        label = _local_label()
        command, timeout = _remote_command(args, label=label)
        key = _key_path()
    except (ValueError, RuntimeError) as exc:
        sys.stderr.write(f"mmx-vps-release refused: {exc}\n")
        return 64
    if not _SSH.is_file():
        sys.stderr.write("mmx-vps-release refused: /usr/bin/ssh unavailable\n")
        return 69
    if args.request_id:
        sys.stderr.write(f"mmx-vps-release request_id={args.request_id}\n")
        sys.stderr.flush()
    try:
        completed = subprocess.run(
            _ssh_argv(command, key),
            stdin=subprocess.DEVNULL,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        if args.request_id:
            sys.stderr.write(
                "mmx-vps-release transport timeout; reconcile the same request id with status\n"
            )
            return 75
        return 69
    except OSError as exc:
        sys.stderr.write(f"mmx-vps-release transport failure: {exc}\n")
        return 69
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
