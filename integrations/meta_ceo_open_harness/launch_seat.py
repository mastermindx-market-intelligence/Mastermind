#!/usr/bin/env python3
"""Run a private, provider-credential-free DSH interaction seat from pinned source.

This is a developer interaction launcher, not an Executive/Agent OS principal,
provider router, scheduler, secret manager, container sandbox, or approval grant.
Providers and keys are configured through the upstream DSH Models UI separately
inside each profile's private DSH_HOME. The child receives no ambient API keys.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Mapping

DONOR_SHA = "687f282e8625c6b8d11ff58211a90524be2e4317"
DEFAULT_PORTS = {"meta-ceo": 3080, "secretary": 3081}
ALLOWED_ENV = frozenset({"HOME", "PATH", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TERM"})


class SeatLaunchError(RuntimeError):
    """A bounded local developer preflight failed before process launch."""


@dataclass(frozen=True)
class Seat:
    role: str
    source: Path
    root: Path
    port: int
    node: Path

    @property
    def home(self) -> Path:
        return self.root / self.role / "harness-home"

    @property
    def workspace(self) -> Path:
        return self.root / self.role / "workspace"

    @property
    def web_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def _checked_private_dir(path: Path, *, create: bool) -> None:
    if create:
        # This root is explicitly selected by the local operator; the actual
        # credential-bearing seat subtree must be private and never symlinked.
        try:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise SeatLaunchError("private_directory_create_failed") from exc
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise SeatLaunchError("private_directory_absent") from exc
    if not stat.S_ISDIR(info.st_mode) or path.is_symlink():
        raise SeatLaunchError("private_directory_not_real_directory")
    if info.st_uid != os.getuid():
        raise SeatLaunchError("private_directory_wrong_owner")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise SeatLaunchError("private_directory_excess_permissions")


def _source_preflight(source: Path, node: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise SeatLaunchError("donor_source_absent_or_symlink")
    if not (source / ".git").exists():
        raise SeatLaunchError("donor_git_checkout_missing")
    if not node.is_absolute() or not node.is_file() or not os.access(node, os.X_OK):
        raise SeatLaunchError("node_binary_unavailable")
    for relative in ("apps/cli/lib/bin.js", "node_modules"):
        if not (source / relative).exists():
            raise SeatLaunchError("donor_build_or_dependencies_missing")
    # No shell and no network calls. Ignore untracked build artifacts but refuse
    # tracked dirty source that cannot honestly be described by the donor pin.
    commands = (["git", "-C", str(source), "rev-parse", "HEAD"],
                ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"])
    values = []
    safe_env = {key: value for key, value in os.environ.items() if key in ALLOWED_ENV}
    for cmd in commands:
        try:
            result = subprocess.run(cmd, text=True, capture_output=True,
                                    timeout=10, check=False, env=safe_env)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SeatLaunchError("donor_source_git_probe_failed") from exc
        if result.returncode != 0:
            raise SeatLaunchError("donor_source_git_probe_failed")
        values.append(result.stdout.strip())
    if values[0] != DONOR_SHA:
        raise SeatLaunchError("donor_immutable_pin_mismatch")
    if values[1]:
        raise SeatLaunchError("donor_tracked_source_dirty")


def prepare(seat: Seat, *, create: bool) -> None:
    _source_preflight(seat.source, seat.node)
    if not 1024 <= seat.port <= 65535:
        raise SeatLaunchError("invalid_port")
    if seat.role not in DEFAULT_PORTS:
        raise SeatLaunchError("invalid_role")
    if create:
        for path in (seat.root, seat.root / seat.role, seat.home, seat.workspace):
            _checked_private_dir(path, create=True)
    else:
        # No persistent effect during --check. Existing directories, when
        # present, must still satisfy the same ownership and permission guard.
        for path in (seat.root, seat.root / seat.role, seat.home, seat.workspace):
            if path.exists() or path.is_symlink():
                _checked_private_dir(path, create=False)


def build_command(seat: Seat) -> list[str]:
    return [str(seat.node), str(seat.source / "apps/cli/lib/bin.js"),
            "web", "--no-open", "--host", "127.0.0.1", "--port", str(seat.port)]


def child_environment(seat: Seat, parent: Mapping[str, str]) -> dict[str, str]:
    env = {key: value for key, value in parent.items() if key in ALLOWED_ENV}
    env["DSH_HOME"] = str(seat.home)
    # This is a configuration hint, not a guarantee that all donor telemetry
    # paths have been audited or disabled. No model credentials are injected.
    env["DSH_TELEMETRY_DISABLED"] = "1"
    return env


def run(seat: Seat, *, check: bool = False,
        execute: Callable[[str, list[str], dict[str, str]], object] = os.execve,
        change_directory: Callable[[str], object] = os.chdir) -> None:
    prepare(seat, create=not check)
    if check:
        print(json.dumps({"state": "PREFLIGHT_ONLY_NO_MODEL_OR_TOOL_PROOF",
                          "role": seat.role, "source_sha": DONOR_SHA,
                          "url": seat.web_url, "home": str(seat.home),
                          "credentials": "SET_IN_NATIVE_DSH_MODELS_UI"}, sort_keys=True))
        return
    # Not a persistent supervisor: replace this process with the pinned DSH
    # binary. No independent queue, process registry, retries, or provider calls.
    change_directory(str(seat.workspace))
    execute(str(seat.node), build_command(seat), child_environment(seat, os.environ))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a private Meta-CEO or Secretary DSH developer seat")
    parser.add_argument("--seat", choices=sorted(DEFAULT_PORTS), required=True)
    parser.add_argument("--source", type=Path, required=True,
                        help="Exact pinned, built DeepSeek Harness donor checkout")
    parser.add_argument("--data-root", type=Path,
                        default=Path.home() / ".mastermind" / "dsh-open-harness")
    parser.add_argument("--port", type=int, help="Loopback port (defaults to dedicated seat port)")
    parser.add_argument("--check", action="store_true", help="Read-only preflight; no install or launch")
    args = parser.parse_args(argv)
    node = shutil.which("node")
    if node is None:
        print("seat-launch: node_binary_unavailable", file=sys.stderr)
        return 2
    seat = Seat(args.seat, args.source.expanduser().absolute(),
                args.data_root.expanduser().absolute(),
                args.port if args.port is not None else DEFAULT_PORTS[args.seat], Path(node).absolute())
    try:
        run(seat, check=args.check)
    except SeatLaunchError as exc:
        print(f"seat-launch: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
