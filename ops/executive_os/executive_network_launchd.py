#!/usr/bin/env python3
"""Fail-closed restart-policy hardening for existing Executive MCP/tunnel jobs.

This module owns no service lifecycle. It validates one already-installed
canonical launchd plist and can atomically change only the restart-policy fields
already proven in production: RunAtLoad=true, KeepAlive=true and
ThrottleInterval=10. Bootout/bootstrap/restart and endpoint reconciliation stay
with their existing owners.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DESIRED_KEEPALIVE = True
DESIRED_THROTTLE_SECONDS = 10


class NetworkLaunchdContractError(RuntimeError):
    """Installed launchd state is outside the reviewed fixed contract."""


@dataclass(frozen=True, slots=True)
class TargetSpec:
    label: str
    kind: str


SPECS = {
    "mcp": TargetSpec("com.mastermind.executive.mcp", "system-daemon"),
    "tunnel": TargetSpec("com.mastermind.executive.tunnel", "user-agent"),
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NetworkLaunchdContractError(message)


def _safe_regular(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise NetworkLaunchdContractError(f"missing plist: {path}") from exc
    _require(not stat.S_ISLNK(info.st_mode), "plist must not be a symlink")
    _require(stat.S_ISREG(info.st_mode), "plist must be a regular file")
    _require(info.st_nlink == 1, "plist must have exactly one hard link")
    _require(
        stat.S_IMODE(info.st_mode) & 0o022 == 0,
        "plist must not be group/other writable",
    )
    return info


def _canonical_path(target: str) -> Path:
    if target == "mcp":
        return Path("/Library/LaunchDaemons/com.mastermind.executive.mcp.plist")
    return Path.home() / "Library/LaunchAgents/com.mastermind.executive.tunnel.plist"


def _require_installed_path(path: Path, target: str) -> None:
    expected = _canonical_path(target)
    _require(path == expected, f"plist must be the canonical installed {target} path")
    info = _safe_regular(path)
    mode = stat.S_IMODE(info.st_mode)
    if target == "mcp":
        _require(info.st_uid == 0 and info.st_gid == 0, "MCP plist owner must be root:wheel")
        _require(mode == 0o644, "MCP plist mode must be 0644")
    else:
        _require(
            info.st_uid == os.geteuid() and info.st_gid == os.getegid(),
            "tunnel plist owner must match the invoking user",
        )
        _require(mode == 0o600, "tunnel plist mode must be 0600")


def load_and_validate(path: Path, target: str) -> dict[str, Any]:
    spec = SPECS[target]
    _safe_regular(path)
    try:
        value = plistlib.loads(path.read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException) as exc:
        raise NetworkLaunchdContractError(f"invalid plist: {path}") from exc
    _require(isinstance(value, dict), "plist root must be a dictionary")
    _require(value.get("Label") == spec.label, "unexpected launchd label")
    _require(value.get("RunAtLoad") is True, "RunAtLoad must already be true")
    _require(value.get("ProcessType") == "Background", "unexpected ProcessType")
    _require(value.get("Umask") == 0o77, "unexpected Umask")
    argv = value.get("ProgramArguments")
    _require(
        isinstance(argv, list) and all(isinstance(item, str) for item in argv),
        "invalid ProgramArguments",
    )
    if target == "mcp":
        _require(
            value.get("UserName") == "_mastermind_executive_mcp",
            "unexpected MCP user",
        )
        _require(
            value.get("GroupName") == "_mastermind_executive_mcp",
            "unexpected MCP group",
        )
        _require(
            len(argv) == 6 and argv[1:3] == ["-I", "-B"],
            "unexpected MCP argv shape",
        )
        _require(
            argv[0].startswith(
                "/Library/Application Support/MastermindExecutive/network-runtimes/"
            )
            and argv[0].endswith("/bin/python"),
            "unexpected MCP runtime",
        )
        _require(
            argv[3].startswith(
                "/Library/Application Support/MastermindExecutive/releases/"
            )
            and argv[3].endswith("/ops/executive_os/executive_mcp_entry.py"),
            "unexpected MCP entrypoint",
        )
        _require(
            argv[4:]
            == [
                "--config",
                "/Library/Application Support/MastermindExecutive/config/executive-mcp.json",
            ],
            "unexpected MCP config",
        )
    else:
        _require(
            len(argv) == 10 and argv[0:2] == ["/usr/bin/env", "-i"],
            "unexpected tunnel argv prefix",
        )
        _require(
            argv[2].startswith("HOME=/") and len(argv[2]) > len("HOME=/"),
            "tunnel HOME must be explicit and absolute",
        )
        tunnel_home = Path(argv[2].split("=", 1)[1])
        _require(tunnel_home.is_absolute(), "tunnel HOME must be absolute")
        _require(
            argv[3] == "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
            "unexpected tunnel PATH",
        )
        _require(
            argv[4].startswith("/opt/homebrew/")
            and argv[4].endswith("/bin/tunnel-client"),
            "unexpected tunnel binary",
        )
        _require(
            argv[5:8]
            == [
                "run",
                "--config",
                str(
                    tunnel_home
                    / ".config/tunnel-client/mastermind-executive-production.yaml"
                ),
            ],
            "unexpected tunnel config",
        )
        _require(
            argv[8:]
            == [
                "--pid.file",
                str(
                    tunnel_home
                    / "Library/Application Support/tunnel-client/health/mastermind-executive-production.pid"
                ),
            ],
            "unexpected tunnel pid file",
        )
    return value


def desired_state(value: dict[str, Any]) -> dict[str, Any]:
    updated = dict(value)
    updated["KeepAlive"] = DESIRED_KEEPALIVE
    updated["ThrottleInterval"] = DESIRED_THROTTLE_SECONDS
    return updated


def is_hardened(value: dict[str, Any]) -> bool:
    return (
        value.get("RunAtLoad") is True
        and value.get("KeepAlive") is DESIRED_KEEPALIVE
        and value.get("ThrottleInterval") == DESIRED_THROTTLE_SECONDS
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_preimage(path: Path, backup: Path, *, mode: int) -> None:
    current = path.read_bytes()
    if backup.exists() or backup.is_symlink():
        _safe_regular(backup)
        _require(backup.read_bytes() == current, "existing rollback preimage differs")
        return
    backup.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        backup,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )
    try:
        view = memoryview(current)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise NetworkLaunchdContractError("short rollback preimage write")
            view = view[written:]
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(backup.parent)


def apply(path: Path, target: str, backup_dir: Path) -> tuple[bool, Path | None]:
    current = load_and_validate(path, target)
    if is_hardened(current):
        return False, None
    before = _safe_regular(path)
    backup = backup_dir / f"{path.name}.before-self-heal"
    _write_preimage(path, backup, mode=stat.S_IMODE(before.st_mode))
    payload = plistlib.dumps(
        desired_state(current), fmt=plistlib.FMT_XML, sort_keys=True
    )
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, stat.S_IMODE(before.st_mode))
        os.chown(tmp_name, before.st_uid, before.st_gid)
        os.replace(tmp_name, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    verified = load_and_validate(path, target)
    _require(is_hardened(verified), "post-write persistence verification failed")
    return True, backup


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=sorted(SPECS), required=True)
    parser.add_argument("--plist", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    _require_installed_path(args.plist, args.target)
    value = load_and_validate(args.plist, args.target)
    if not args.apply:
        print("HARDENED" if is_hardened(value) else "DRIFT")
        return 0 if is_hardened(value) else 2
    if args.backup_dir is None:
        raise SystemExit("--backup-dir is required with --apply")
    changed, backup = apply(args.plist, args.target, args.backup_dir)
    print("CHANGED" if changed else "UNCHANGED", str(backup) if backup else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
