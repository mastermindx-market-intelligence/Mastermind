#!/usr/bin/env python3
"""Fail-closed persistence hardening for the existing Executive MCP/tunnel jobs.

This module does not create services or supervise processes.  It validates an already
installed, canonical launchd job and can atomically change only launchd restart policy.
Service reload/reconciliation remains an explicit operator step.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DESIRED_KEEPALIVE = True
DESIRED_THROTTLE_SECONDS = 10


class NetworkLaunchdContractError(RuntimeError):
    pass


@dataclass(frozen=True)
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


def load_and_validate(path: Path, target: str) -> dict[str, Any]:
    spec = SPECS[target]
    _require(path.is_file(), f"missing plist: {path}")
    raw = path.read_bytes()
    try:
        value = plistlib.loads(raw)
    except Exception as exc:
        raise NetworkLaunchdContractError(f"invalid plist: {path}") from exc
    _require(isinstance(value, dict), "plist root must be a dictionary")
    _require(value.get("Label") == spec.label, "unexpected launchd label")
    _require(value.get("RunAtLoad") is True, "RunAtLoad must already be true")
    _require(value.get("ProcessType") == "Background", "unexpected ProcessType")
    _require(value.get("Umask") == 0o77, "unexpected Umask")
    argv = value.get("ProgramArguments")
    _require(isinstance(argv, list) and all(isinstance(x, str) for x in argv), "invalid ProgramArguments")
    if target == "mcp":
        _require(value.get("UserName") == "_mastermind_executive_mcp", "unexpected MCP user")
        _require(value.get("GroupName") == "_mastermind_executive_mcp", "unexpected MCP group")
        _require(len(argv) == 6 and argv[1:3] == ["-I", "-B"], "unexpected MCP argv shape")
        _require(argv[3].endswith("/ops/executive_os/executive_mcp_entry.py"), "unexpected MCP entrypoint")
        _require(argv[4:] == ["--config", "/Library/Application Support/MastermindExecutive/config/executive-mcp.json"], "unexpected MCP config")
    else:
        _require(len(argv) >= 10 and argv[0:2] == ["/usr/bin/env", "-i"], "unexpected tunnel argv prefix")
        _require(argv[2].startswith("HOME=/"), "tunnel HOME must be explicit and absolute")
        tunnel_home = Path(argv[2].split("=", 1)[1])
        _require(argv[3] == "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "unexpected tunnel PATH")
        _require("tunnel-client" in argv[4], "unexpected tunnel binary")
        _require(argv[5:8] == ["run", "--config", str(tunnel_home / ".config/tunnel-client/mastermind-executive-production.yaml")], "unexpected tunnel config")
        _require(argv[8:] == ["--pid.file", str(tunnel_home / "Library/Application Support/tunnel-client/health/mastermind-executive-production.pid")], "unexpected tunnel pid file")
    return value


def desired_state(value: dict[str, Any]) -> dict[str, Any]:
    updated = dict(value)
    updated["KeepAlive"] = DESIRED_KEEPALIVE
    updated["ThrottleInterval"] = DESIRED_THROTTLE_SECONDS
    return updated


def is_hardened(value: dict[str, Any]) -> bool:
    return value.get("KeepAlive") == DESIRED_KEEPALIVE and value.get("ThrottleInterval") == DESIRED_THROTTLE_SECONDS


def apply(path: Path, target: str, backup_dir: Path) -> tuple[bool, Path | None]:
    current = load_and_validate(path, target)
    if is_hardened(current):
        return False, None
    before = path.stat()
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{path.name}.before-self-heal"
    if not backup.exists():
        shutil.copy2(path, backup)
    payload = plistlib.dumps(desired_state(current), fmt=plistlib.FMT_XML, sort_keys=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, stat.S_IMODE(before.st_mode))
        os.chown(tmp_name, before.st_uid, before.st_gid)
        os.replace(tmp_name, path)
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
