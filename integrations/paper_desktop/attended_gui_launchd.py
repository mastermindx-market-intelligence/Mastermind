#!/usr/bin/env python3
"""Install and verify the single attended Paper Desktop GUI launchd supervisor.

This supervises only the existing Paper.app GUI. The existing private Paper MCP
tunnels, guarded bridge, credentials and document effects remain independent.
No polling worker, port proxy, scheduler or additional Paper daemon is created.
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import stat
import subprocess
import sys
from pathlib import Path

LABEL = "com.mastermind.paper-desktop.attended"
APP_REL = Path("Applications/Paper.app")
PLIST_REL = Path("Library/LaunchAgents") / f"{LABEL}.plist"
LAUNCHCTL = "/bin/launchctl"
OPEN = "/usr/bin/open"


class SupervisorRefused(RuntimeError):
    """Refuse an unsafe or unknown installed state without replacing it."""


def _regular_owned(path: Path, uid: int, *, executable: bool = False) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != uid:
        raise SupervisorRefused(f"UNSAFE_FILE: {path}")
    if executable and not (info.st_mode & 0o111):
        raise SupervisorRefused(f"NOT_EXECUTABLE: {path}")


def _dir_owned(path: Path, uid: int) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid:
        raise SupervisorRefused(f"UNSAFE_DIRECTORY: {path}")


def expected_plist(home: Path) -> dict:
    return {
        "Label": LABEL,
        "ProgramArguments": [OPEN, "-W", "-a", str(home / APP_REL)],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "LimitLoadToSessionType": "Aqua",
        "ProcessType": "Interactive",
    }


def preflight(home: Path, uid: int) -> None:
    _dir_owned(home, uid)
    _dir_owned(home / "Applications", uid)
    _dir_owned(home / APP_REL, uid)
    _dir_owned(home / APP_REL / "Contents", uid)
    _dir_owned(home / APP_REL / "Contents/MacOS", uid)
    _dir_owned(home / "Library", uid)
    _dir_owned(home / "Library/LaunchAgents", uid)
    _regular_owned(home / APP_REL / "Contents/MacOS/Paper", uid, executable=True)


def verify_plist(home: Path, uid: int) -> bool:
    path = home / PLIST_REL
    try:
        _regular_owned(path, uid)
    except FileNotFoundError:
        return False
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise SupervisorRefused("PLIST_MODE_MISMATCH")
    with path.open("rb") as source:
        installed = plistlib.load(source)
    if installed != expected_plist(home):
        raise SupervisorRefused("PLIST_CONTENT_MISMATCH")
    return True


def install_plist(home: Path, uid: int) -> str:
    preflight(home, uid)
    if verify_plist(home, uid):
        return "EXISTING_IDENTICAL"
    path = home / PLIST_REL
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            plistlib.dump(expected_plist(home), output, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        # Do not delete an uncertain partial installation; reconcile this path.
        raise
    if not verify_plist(home, uid):
        raise SupervisorRefused("PLIST_POSTREAD_FAILED")
    return "CREATED"


def _job_target(uid: int) -> str:
    return f"gui/{uid}/{LABEL}"


def job_observation(uid: int, *, run=subprocess.run) -> str:
    result = run([LAUNCHCTL, "print", _job_target(uid)], capture_output=True, text=True, timeout=10, check=False)
    if result.returncode == 0:
        return "LOADED"
    output = (result.stdout + result.stderr).lower()
    if "could not find service" in output or "service not found" in output:
        return "ABSENT"
    return "UNKNOWN"


def bootstrap(home: Path, uid: int, *, run=subprocess.run) -> str:
    if not verify_plist(home, uid):
        raise SupervisorRefused("PLIST_NOT_VERIFIED")
    previous = job_observation(uid, run=run)
    if previous == "LOADED":
        return "ALREADY_LOADED"
    if previous != "ABSENT":
        raise SupervisorRefused("JOB_STATE_UNKNOWN")
    result = run([LAUNCHCTL, "bootstrap", f"gui/{uid}", str(home / PLIST_REL)],
                 capture_output=True, text=True, timeout=15, check=False)
    # A lost/failed bootstrap response is never proof of no effect; inspect the
    # original launchd label rather than blindly submitting a second bootstrap.
    after = job_observation(uid, run=run)
    if after == "LOADED":
        return "LOADED_AFTER_BOOTSTRAP"
    if result.returncode != 0 or after == "UNKNOWN":
        raise SupervisorRefused("BOOTSTRAP_OUTCOME_UNVERIFIED")
    raise SupervisorRefused("BOOTSTRAP_NOT_LOADED")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["verify", "install"])
    args = parser.parse_args()
    home = Path.home()
    uid = os.getuid()
    try:
        preflight(home, uid)
        if args.action == "install":
            file_state = install_plist(home, uid)
            job_state = bootstrap(home, uid)
        else:
            file_state = "VERIFIED" if verify_plist(home, uid) else "ABSENT"
            job_state = job_observation(uid)
        print(json.dumps({"label": LABEL, "file_state": file_state, "job_state": job_state,
                          "gui_session_only": True, "paper_health_proven": False},
                         sort_keys=True))
        return 0 if file_state != "ABSENT" and job_state in {"LOADED", "ALREADY_LOADED", "LOADED_AFTER_BOOTSTRAP"} else 1
    except (SupervisorRefused, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        print(json.dumps({"label": LABEL, "state": "REFUSED",
                          "reason": str(exc), "effect": "NOT_CLAIMED"}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
