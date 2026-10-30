"""Shared, dependency-free core for the Subagent Fabric tunnel-client recovery.

Source law for this integration is the sibling ``RECOVERY_PLAN.md`` at plan
commit 6dd11e7015235eff3c0242ef90dea554f4f4c58d on
``sol/fabric-tunnels-autoheal-20261030-01``, written against protected master
bb85b429f2ffffd38408080ce4df7d6378c34100 (Skillpack 1.0.1).

Hard fences implemented here (violations raise, never degrade to a warning):

- Exactly five EXISTING user LaunchAgents are in scope. Their labels are the
  ones the recovery plan names; nothing else in the
  ``com.mastermind.subagent-fabric-tunnel.*`` family is adoptable, and any
  unexpected family member is reported as a rogue label that refuses install.
- ``com.mastermind.desktop-commander.remote`` is a permanently forbidden
  action target. It is never bootout-ed, kickstart-ed, bootstrapped, parsed,
  or rewritten by any code path in this integration.
- No tunnel identity, credential, command argument, or terminal binding is
  invented anywhere in this module. Per-seat argv and host paths are recorded
  at explicit operator qualification time into a PRIVATE manifest
  (mode 0600, under ``~/Library/Application Support``) and are never
  committed, logged, or printed unredacted.
- No sudo, no security/SIP change, no CURRENT.json selection, no host-pull
  repin, no additional queue or process watcher. The only mutation this
  integration performs on the five seats is the launchd policy trio
  (``RunAtLoad=true``, unconditional ``KeepAlive=true``,
  ``ThrottleInterval>=10``) behind a verified preimage backup, and the only
  recovery action it performs is ``launchctl kickstart`` of an already
  qualified original job under a persisted cooldown.

Everything is standard-library Python 3.11+ so the modules stay importable
in hermetic tests and in the installed watchdog copy without the repo.
"""
from __future__ import annotations

import hashlib
import os
import plistlib
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

# ---------------------------------------------------------------------------
# Source law pins (identity of the plan this code implements).
# ---------------------------------------------------------------------------

PLAN_COMMIT = "6dd11e7015235eff3c0242ef90dea554f4f4c58d"
MASTER_SHA = "bb85b429f2ffffd38408080ce4df7d6378c34100"

# ---------------------------------------------------------------------------
# Immutable scope. The five seat keys and the family prefix are taken verbatim
# from RECOVERY_PLAN.md. The watchdog label is the one NEW label this
# integration owns, derived from the same family namespace.
# ---------------------------------------------------------------------------

TUNNEL_SEATS: tuple[str, ...] = (
    "c1",
    "c2-business",
    "c2-personal",
    "c3",
    "c4",
)
TUNNEL_LABEL_PREFIX = "com.mastermind.subagent-fabric-tunnel."
TUNNEL_LABELS: frozenset[str] = frozenset(TUNNEL_LABEL_PREFIX + seat for seat in TUNNEL_SEATS)
WATCHDOG_LABEL = TUNNEL_LABEL_PREFIX + "health"
OWNED_LABELS: frozenset[str] = TUNNEL_LABELS | frozenset({WATCHDOG_LABEL})

# Permanently forbidden action targets. Membership is asserted before every
# launchd action this integration constructs.
FORBIDDEN_LABELS: frozenset[str] = frozenset({
    "com.mastermind.desktop-commander.remote",
})

# ---------------------------------------------------------------------------
# launchd policy under FTR-2. KeepAlive is an unconditional BOOLEAN: the
# tunnel client may exit 0 after SIGTERM, so any conditional dict form
# (SuccessfulExit/Crashed/...) must be replaced, not merged.
# ---------------------------------------------------------------------------

RUN_AT_LOAD = True
KEEP_ALIVE = True  # unconditional boolean; dictionaries are replaced
THROTTLE_INTERVAL_MIN = 10
POLICY_KEYS: tuple[str, ...] = ("RunAtLoad", "KeepAlive", "ThrottleInterval")

# FTR-3 thresholds. The heartbeat path itself is never invented here; it is
# recorded per seat in the operator-qualified private manifest.
STALE_HEARTBEAT_SECONDS = 300
DEFAULT_STALE_TELEMETRY_SECONDS = 900
KICKSTART_COOLDOWN_SECONDS = 1800
# After this many consecutive kickstarts without an observed fresh heartbeat,
# the seat escalates to alert-only until one fresh heartbeat is witnessed.
KICKSTART_ESCALATION_LIMIT = 3
WATCHDOG_START_INTERVAL_SECONDS = 60
MANIFEST_MAX_AGE_SECONDS = 86400

LAUNCHCTL = "/bin/launchctl"

IDENTITY_MANIFEST_SCHEMA = "mastermind.subagent-fabric-tunnels.identity-manifest.v1"
KICK_LEDGER_SCHEMA = "mastermind.subagent-fabric-tunnels.kick-ledger.v1"
PASS_REPORT_SCHEMA = "mastermind.subagent-fabric-tunnels.pass-report.v1"

# Used only to detect OTHER seats' identity inside a candidate executable
# path (the chatgpt1 cross-seat adoption hazard named in the plan). Matching
# is boundary-delimited so unrelated digit runs do not false-match.
_FOREIGN_KEY_NAMES: tuple[str, ...] = TUNNEL_SEATS + ("chatgpt1",)


def foreign_identity_pattern(foreign_key: str) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(foreign_key) + r"(?![A-Za-z0-9])")


# ---------------------------------------------------------------------------
# Typed refusals. Every refusal is terminal for the action it guards; callers
# surface them as alerts and never retry around them.
# ---------------------------------------------------------------------------


class IdentityRejected(Exception):
    """The installed plist/executable/job identity failed deterministic
    verification. No on-disk or launchd action may proceed for that seat."""


class PolicyRefused(Exception):
    """A requested mutation is outside the allowed policy trio or violates a
    plan fence (forbidden label, unqualified manifest, drift, rogue label)."""


class ActionRefused(Exception):
    """A launchd action was refused (unknown/stale/unqualified target,
    cooldown suppression, or a forbidden target was requested)."""


# ---------------------------------------------------------------------------
# Process seam. Every launchd invocation goes through this callable so
# hermetic tests can inject a fake runner; the real runner never uses a shell
# and never inherits or logs job environment contents.
# ---------------------------------------------------------------------------

Runner = Callable[[Sequence[str], float], "RunResult"]


@dataclass(frozen=True)
class RunResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def subprocess_runner(argv: Sequence[str], timeout: float = 10.0) -> RunResult:
    """Default runner. argv-list only, no shell, bounded timeout."""
    argv = tuple(argv)
    if argv[:1] != (LAUNCHCTL,):
        raise ActionRefused("non-launchctl process spawn is outside this integration")
    try:
        proc = subprocess.run(  # noqa: S603 - fixed binary, list argv, no shell
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return RunResult(argv, proc.returncode, proc.stdout or "", proc.stderr or "")
    except subprocess.TimeoutExpired:
        return RunResult(argv, 124, "", "", timed_out=True)


# ---------------------------------------------------------------------------
# Paths. All host-relative; a test supplies its own fake home. The private
# state root lives OUTSIDE any repository work tree so backups can never be
# committed, and is created 0700 with 0600 files.
# ---------------------------------------------------------------------------


def plist_relpath(label: str) -> str:
    return f"Library/LaunchAgents/{label}.plist"


def launchagents_dir(home: Path) -> Path:
    return Path(home) / "Library" / "LaunchAgents"


def private_state_root(home: Path) -> Path:
    return Path(home) / "Library" / "Application Support" / "mastermind-subagent-fabric-tunnels"


def backups_dir(home: Path) -> Path:
    return private_state_root(home) / "backups"


def state_dir(home: Path) -> Path:
    return private_state_root(home) / "state"


def watchdog_dir(home: Path) -> Path:
    return private_state_root(home) / "watchdog"


def manifest_path(home: Path) -> Path:
    return state_dir(home) / "identity-manifest.json"


def kick_ledger_path(home: Path) -> Path:
    return state_dir(home) / "kick-ledger.json"


def last_pass_path(home: Path) -> Path:
    return state_dir(home) / "last-pass.json"


# ---------------------------------------------------------------------------
# Secret-safety. Job environment contents are never echoed; any mapping value
# that reaches an evidence line is reduced to a length + digest prefix.
# ---------------------------------------------------------------------------

_SECRET_KEY_RE = re.compile(
    r"(?i)(token|secret|passwd|password|credential|api[_-]?key|apikey|auth|cookie|session)"
)


def looks_secret_key(key: str) -> bool:
    return bool(_SECRET_KEY_RE.search(key or ""))


def redact_value(key: str, value: Any) -> Any:
    """Return a printable, secret-safe reduction of ``value``."""
    if looks_secret_key(key):
        return "<redacted>"
    if isinstance(value, str) and len(value) >= 32:
        digest = hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:12]
        return f"<len={len(value)} sha256:{digest}>"
    if isinstance(value, dict):
        return {k: redact_value(str(k), v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [redact_value(key, item) for item in value]
    return value


def evidence_line(label: str, fields: Mapping[str, Any]) -> str:
    rendered = " ".join(f"{k}={redact_value(k, v)!r}" for k, v in sorted(fields.items()))
    return f"{label} {rendered}"


# ---------------------------------------------------------------------------
# Filesystem verification helpers (fail closed).
# ---------------------------------------------------------------------------


def require_regular_file(path: Path, *, code: str) -> None:
    try:
        st = path.lstat()
    except OSError as exc:
        raise IdentityRejected(f"{code}: unreadable ({exc.strerror})") from exc
    if stat.S_ISLNK(st.st_mode):
        raise IdentityRejected(f"{code}: symlink is not an acceptable identity")
    if not stat.S_ISREG(st.st_mode):
        raise IdentityRejected(f"{code}: not a regular file")


def require_owner_writable_safe(path: Path, uid: int, *, code: str) -> None:
    """The plist/LaunchAgents files this integration owns must be owned by the
    seat user and must not be group- or world-writable (hijack guard)."""
    try:
        st = path.lstat()
    except OSError as exc:
        raise IdentityRejected(f"{code}: unreadable ({exc.strerror})") from exc
    if st.st_uid != uid:
        raise IdentityRejected(f"{code}: owner uid {st.st_uid} != seat uid {uid}")
    if st.st_mode & 0o022:
        raise IdentityRejected(f"{code}: group/world-writable mode {oct(st.st_mode & 0o777)}")


def require_parent_safe(path: Path, uid: int, *, code: str) -> None:
    """Every ancestor of ``path`` must exist, be a real directory (no symlink
    escape), and must not be group-writable or world-writable-without-sticky.

    A sticky world-writable directory (mode 1777, e.g. the temp root) keeps
    other users from renaming or replacing entries inside it, so it is
    accepted; an unprotected world-writable ancestor is a hijack vector and
    rejects. Owner expectations are enforced on the launchd-owned files
    themselves, not on system ancestors like ``/Users``."""
    current = Path(path).resolve()
    for component in reversed(current.parents):
        try:
            st = component.lstat()
        except OSError as exc:
            raise IdentityRejected(f"{code}: unreadable ancestor ({exc.strerror})") from exc
        if stat.S_ISLNK(st.st_mode):
            raise IdentityRejected(f"{code}: symlinked ancestor {component}")
        if not stat.S_ISDIR(st.st_mode):
            raise IdentityRejected(f"{code}: non-directory ancestor {component}")
        world_writable = bool(st.st_mode & 0o0002)
        group_writable = bool(st.st_mode & 0o0020)
        sticky = bool(st.st_mode & 0o1000)
        if world_writable and sticky:
            continue  # protected convention directory (mode 1777)
        if world_writable or group_writable:
            raise IdentityRejected(f"{code}: unprotected writable ancestor {component}")


def executable_path_reject_reason(
    seat_label: str,
    executable: str,
    all_labels: "frozenset[str] | set[str]" = TUNNEL_LABELS,
) -> str | None:
    """Cross-seat adoption guard for argv[0].

    Rejects an executable whose path carries a DIFFERENT in-scope seat key or
    the ``chatgpt1`` reference named by the plan as the known contamination
    vector. A seat's own key in its own path is expected and allowed.
    """
    own_seat = seat_label.rpartition(TUNNEL_LABEL_PREFIX)[2]
    for foreign in sorted(_FOREIGN_KEY_NAMES):
        if own_seat == foreign:
            continue
        if foreign_identity_pattern(foreign).search(executable):
            return f"executable references foreign seat identity {foreign!r}"
    return None


# ---------------------------------------------------------------------------
# Plist serialization with byte-exact preimage discipline.
# ---------------------------------------------------------------------------


def parse_plist_bytes(raw: bytes, *, code: str) -> dict[str, Any]:
    try:
        loaded = plistlib.loads(raw)
    except Exception as exc:  # plistlib raises several unrelated types
        raise IdentityRejected(f"{code}: not parseable as a plist ({exc.__class__.__name__})") from exc
    if not isinstance(loaded, dict):
        raise IdentityRejected(f"{code}: plist root is not a dictionary")
    return loaded


def serialize_plist(working: Mapping[str, Any]) -> bytes:
    return plistlib.dumps(dict(working), fmt=plistlib.FMT_XML)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def atomic_write_bytes(path: Path, raw: bytes, mode: int) -> None:
    """Write ``raw`` to ``path`` via a same-directory temp file + rename.

    The bytes are parsed back (plist for ``.plist``, JSON for ``.json``)
    before the rename so a serialization fault can never replace a good
    file. The directory is fsynced so the rename is durable before any
    launchd reload is attempted.
    """
    if path.suffix == ".plist":
        parsed_back = parse_plist_bytes(raw, code="atomic_write_roundtrip")
        if parsed_back is None:
            raise IdentityRejected("atomic_write_roundtrip: empty serialization")
    elif path.suffix == ".json":
        import json as _json

        try:
            _json.loads(raw)
        except ValueError as exc:
            raise IdentityRejected(f"atomic_write_roundtrip: invalid JSON ({exc})") from exc
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".ftr-mutation-", dir=str(directory))
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, mode & 0o7777)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise
    try:
        dir_fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


# ---------------------------------------------------------------------------
# launchd command construction. Every builder asserts the allowlist and the
# forbidden set BEFORE returning argv, so no call site can bypass the fence.
# ---------------------------------------------------------------------------


def _assert_action_label(label: str) -> None:
    if label in FORBIDDEN_LABELS:
        raise ActionRefused(f"forbidden action target: {label}")
    if label not in OWNED_LABELS:
        raise ActionRefused(f"label outside owned allowlist: {label}")


def launchctl_print_argv(uid: int, label: str) -> list[str]:
    _assert_action_label(label)
    return [LAUNCHCTL, "print", f"gui/{uid}/{label}"]


def launchctl_kickstart_argv(uid: int, label: str, *, force: bool) -> list[str]:
    _assert_action_label(label)
    argv = [LAUNCHCTL, "kickstart"]
    if force:
        argv.append("-k")
    argv.append(f"gui/{uid}/{label}")
    return argv


def launchctl_bootout_argv(uid: int, label: str) -> list[str]:
    _assert_action_label(label)
    return [LAUNCHCTL, "bootout", f"gui/{uid}/{label}"]


def launchctl_bootstrap_argv(uid: int, plist_path: Path) -> list[str]:
    label = plist_path.stem
    _assert_action_label(label)
    return [LAUNCHCTL, "bootstrap", f"gui/{uid}", str(plist_path)]


def parse_print_pid(state_output: str) -> int | None:
    """Extract the first ``pid = N`` line from ``launchctl print`` output.

    launchd prints ``pid = <int>`` only while the job holds a running PID; a
    stopped job has no pid line, which classifies as missing PID (FTR-3).
    """
    for line in state_output.splitlines():
        match = re.match(r"\s*pid\s*=\s*(\d+)\s*(?:\(.*\))?\s*$", line)
        if match:
            return int(match.group(1))
    return None


# ---------------------------------------------------------------------------
# Evidence records shared by install/health modules.
# ---------------------------------------------------------------------------


@dataclass
class Alert:
    code: str
    label: str
    detail: str = ""
    acted: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "detail": redact_value("detail", self.detail) if self.detail else "",
            "acted": self.acted,
        }


@dataclass
class PassReport:
    started_at: float
    finished_at: float | None = None
    seats: dict[str, Any] = field(default_factory=dict)
    alerts: list[Alert] = field(default_factory=list)
    generation: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": PASS_REPORT_SCHEMA,
            "plan_commit": PLAN_COMMIT,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "seats": self.seats,
            "generation": self.generation,
            "alerts": [alert.as_dict() for alert in self.alerts],
        }
