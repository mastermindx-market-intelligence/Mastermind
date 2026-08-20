"""Attested macOS platform ambient processes for the dedicated worker UID.

The UID sweep's residual set is every same-UID process except the broker and
processes that carry a cryptographically and structurally attested launchd
identity.  A process name, argv string, or caller-supplied PID class is never
authority.

The only reviewed ambient identity is Apple's per-user distributed
notification agent:

* launchd domain ``user/<uid>``
* launchd label ``com.apple.distnoted.xpc.agent``
* plist ``/System/Library/LaunchAgents/com.apple.distnoted.xpc.agent.plist``
* program ``/usr/sbin/distnoted``
* codesign identifier ``com.apple.distnoted`` with ``codesign --verify --strict``

A process executing the same binary, or a process merely named ``distnoted``,
that does not own that exact launchd job PID is a worker residual.
"""
from __future__ import annotations

import ctypes
import dataclasses
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

AMBIENT_LAUNCHD_LABEL = "com.apple.distnoted.xpc.agent"
AMBIENT_PLIST_PATH = "/System/Library/LaunchAgents/com.apple.distnoted.xpc.agent.plist"
AMBIENT_PROGRAM_PATH = "/usr/sbin/distnoted"
AMBIENT_CODESIGN_IDENTIFIER = "com.apple.distnoted"
AMBIENT_ATTRIBUTIONS = frozenset({"attested", "absent", "failed_closed"})

_LAUNCHCTL = "/bin/launchctl"
_CODESIGN = "/usr/bin/codesign"
_TOP_LEVEL_ASSIGNMENT = re.compile(r"^\t([A-Za-z][A-Za-z0-9_ ]*) = (.+)$")


@dataclasses.dataclass(frozen=True)
class AmbientProcessIdentity:
    """Secret-free, host-attested identity for one platform ambient process."""

    pid: int
    uid: int
    launchd_domain: str
    launchd_label: str
    launchd_reported_pid: int
    plist_path: str
    program_path: str
    executable_path: str
    executable_device: int
    executable_inode: int
    codesign_identifier: str
    codesign_verified: bool

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class AmbientClassification:
    """Result of one ambient-attribution attempt.  Empty identities fail closed."""

    status: str
    identities: tuple[AmbientProcessIdentity, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in AMBIENT_ATTRIBUTIONS:
            raise ValueError(f"ambient attribution {self.status!r} is not reviewed")
        if self.status != "attested" and self.identities:
            raise ValueError("non-attested ambient classification cannot carry identities")
        if self.status == "attested" and not self.identities:
            raise ValueError("attested ambient classification requires identities")


class AmbientProcessClassifier(Protocol):
    def classify(self, *, worker_uid: int) -> AmbientClassification:
        """Return attested ambient identities, or fail closed with none."""


class NullAmbientClassifier:
    """No ambient processes.  Used by tests and non-production hosts."""

    def classify(self, *, worker_uid: int) -> AmbientClassification:
        if int(worker_uid) <= 0:
            return AmbientClassification(status="failed_closed")
        return AmbientClassification(status="absent")


class DarwinDistnotedClassifier:
    """Classify Apple's per-user distnoted LaunchAgent for one dedicated UID.

    Attribution queries the exact launchd job
    ``user/<uid>/com.apple.distnoted.xpc.agent``.  It never scans the process
    table by name and never accepts a caller-provided PID.
    """

    def __init__(
        self,
        *,
        launchctl_print: Callable[[str], tuple[int, str, str]] | None = None,
        pid_executable: Callable[[int], Path | None] | None = None,
        program_identity: Callable[[Path], Mapping[str, Any] | None] | None = None,
    ) -> None:
        self._launchctl_print = launchctl_print or _launchctl_print
        self._pid_executable = pid_executable or _proc_pid_path
        self._program_identity = program_identity or _platform_program_identity

    def classify(self, *, worker_uid: int) -> AmbientClassification:
        uid = int(worker_uid)
        if uid <= 0:
            return AmbientClassification(status="failed_closed")
        spec = f"user/{uid}/{AMBIENT_LAUNCHD_LABEL}"
        try:
            returncode, stdout, stderr = self._launchctl_print(spec)
        except Exception:
            return AmbientClassification(status="failed_closed")
        if returncode != 0:
            combined = f"{stdout}\n{stderr}"
            if _job_absent(combined, returncode):
                return AmbientClassification(status="absent")
            return AmbientClassification(status="failed_closed")
        parsed = parse_distnoted_launchd_job(stdout, worker_uid=uid)
        if parsed is None:
            return AmbientClassification(status="failed_closed")
        executable = self._pid_executable(parsed["pid"])
        if executable is None:
            return AmbientClassification(status="failed_closed")
        if os.fspath(executable) != AMBIENT_PROGRAM_PATH:
            try:
                resolved = executable.resolve(strict=True)
                program = Path(AMBIENT_PROGRAM_PATH).resolve(strict=True)
            except OSError:
                return AmbientClassification(status="failed_closed")
            if resolved != program:
                return AmbientClassification(status="failed_closed")
        else:
            resolved = Path(AMBIENT_PROGRAM_PATH)
        identity = self._program_identity(resolved)
        if identity is None:
            return AmbientClassification(status="failed_closed")
        if (
            identity.get("path") != AMBIENT_PROGRAM_PATH
            or identity.get("codesign_identifier") != AMBIENT_CODESIGN_IDENTIFIER
            or identity.get("codesign_verified") is not True
        ):
            return AmbientClassification(status="failed_closed")
        try:
            device = int(identity["device"])
            inode = int(identity["inode"])
        except (KeyError, TypeError, ValueError):
            try:
                info = resolved.stat()
            except OSError:
                return AmbientClassification(status="failed_closed")
            device = int(info.st_dev)
            inode = int(info.st_ino)
        return AmbientClassification(
            status="attested",
            identities=(
                AmbientProcessIdentity(
                    pid=parsed["pid"],
                    uid=uid,
                    launchd_domain=parsed["domain"],
                    launchd_label=AMBIENT_LAUNCHD_LABEL,
                    launchd_reported_pid=parsed["pid"],
                    plist_path=parsed["path"],
                    program_path=parsed["program"],
                    executable_path=AMBIENT_PROGRAM_PATH,
                    executable_device=device,
                    executable_inode=inode,
                    codesign_identifier=str(identity["codesign_identifier"]),
                    codesign_verified=True,
                ),
            ),
        )


def parse_distnoted_launchd_job(stdout: str, *, worker_uid: int) -> dict[str, Any] | None:
    """Parse ``launchctl print user/<uid>/com.apple.distnoted.xpc.agent``.

    Fail closed on any missing, extra, or drifted load-bearing field.  Nested
    blocks are ignored: argv/name strings are not authority.
    """

    if not isinstance(stdout, str) or not stdout:
        return None
    header = f"user/{int(worker_uid)}/{AMBIENT_LAUNCHD_LABEL} = {{"
    if not stdout.lstrip().startswith(header):
        return None
    fields: dict[str, str] = {}
    for raw in stdout.splitlines():
        match = _TOP_LEVEL_ASSIGNMENT.fullmatch(raw)
        if match is None:
            continue
        key, value = match.group(1), match.group(2)
        if key in fields:
            return None
        fields[key] = value
    try:
        pid = int(fields["pid"])
    except (KeyError, ValueError):
        return None
    if pid <= 1:
        return None
    expected = {
        "path": AMBIENT_PLIST_PATH,
        "type": "LaunchAgent",
        "state": "running",
        "program": AMBIENT_PROGRAM_PATH,
        "domain": f"user/{int(worker_uid)}",
    }
    for key, value in expected.items():
        if fields.get(key) != value:
            return None
    return {
        "pid": pid,
        "path": fields["path"],
        "program": fields["program"],
        "domain": fields["domain"],
        "type": fields["type"],
        "state": fields["state"],
    }


def _job_absent(text: str, returncode: int) -> bool:
    lowered = text.lower()
    return returncode in {113, 125} or "could not find service" in lowered or "not found" in lowered


def _launchctl_print(spec: str) -> tuple[int, str, str]:
    completed = subprocess.run(
        [_LAUNCHCTL, "print", spec],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
    )
    return completed.returncode, completed.stdout, completed.stderr


def _proc_pid_path(pid: int) -> Path | None:
    try:
        libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        buf = ctypes.create_string_buffer(4096)
        n = libc.proc_pidpath(ctypes.c_int(int(pid)), buf, ctypes.c_uint32(len(buf)))
    except Exception:
        return None
    if n <= 0:
        return None
    raw = buf.raw[:n].split(b"\x00", 1)[0]
    if not raw:
        return None
    try:
        return Path(os.fsdecode(raw))
    except Exception:
        return None


def _platform_program_identity(path: Path) -> Mapping[str, Any] | None:
    lexical = Path(path)
    try:
        resolved = lexical.resolve(strict=True)
        info = resolved.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return None
    if os.fspath(resolved) != AMBIENT_PROGRAM_PATH:
        return None
    try:
        verify = subprocess.run(
            [_CODESIGN, "--verify", "--strict", os.fspath(resolved)],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
        )
        display = subprocess.run(
            [_CODESIGN, "-dv", "--verbose=4", os.fspath(resolved)],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
        )
    except Exception:
        return None
    if verify.returncode != 0:
        return None
    identifier = None
    for raw in (display.stderr or "").splitlines():
        if raw.startswith("Identifier="):
            identifier = raw.split("=", 1)[1]
            break
    if identifier != AMBIENT_CODESIGN_IDENTIFIER:
        return None
    return {
        "path": os.fspath(resolved),
        "codesign_identifier": identifier,
        "codesign_verified": True,
    }
