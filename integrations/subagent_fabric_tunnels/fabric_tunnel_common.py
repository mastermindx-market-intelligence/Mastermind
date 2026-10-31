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
import json
import math
import os
import plistlib
import re
import select
import stat
import subprocess
import tempfile
import time
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

# Host-pull telemetry qualification. Health reads a bounded, CLOSED set of
# operator-qualified explicit telemetry files (relative to the qualified
# telemetry root) and evaluates the OLDEST of them, so an unrelated fresh
# file under the same root can never mask stale telemetry and a large
# directory can never make the minute watchdog unbounded.
TELEMETRY_FILE_SUFFIXES = (".json",)
MAX_TELEMETRY_FILES = 32
# Bounded relative-path spelling length shared by qualification and health
# reads: a qualified telemetry/fact relative path never exceeds this length.
MAX_TUNNEL_RELATIVE_PATH = 512

# ---------------------------------------------------------------------------
# First-party CLI control-plane-poll heartbeat (strictly typed FTR-3 mode).
#
# The FILE-mtime heartbeat mode above stays exactly as qualified; this mode is
# the stronger first-party proof: per pass, the seat's OWN qualified
# tunnel-client binary is invoked READ-ONLY as
#   <qualified executable> health --url-file <qualified locator>
#       --require-control-plane-poll --json
# and the numeric ``control_plane_poll.value`` (Unix seconds of the client's
# last successful control-plane poll) becomes the last-seen signal. Every
# bound here is a fail-closed limit: nothing outside them may authorize a
# kickstart, and no URL, profile, locator, or raw payload is ever printed.
# ---------------------------------------------------------------------------

HEARTBEAT_MODE_FILE_MTIME = "file_mtime_attested"
HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL = "first_party_cli_control_plane_poll"
# Closed mode set: any other spelling is refused at qualification, never
# guessed into a behavior.
TUNNEL_HEARTBEAT_MODES: frozenset[str] = frozenset({
    HEARTBEAT_MODE_FILE_MTIME,
    HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL,
})
# Strict per-seat probe deadline. A hanging or wedged child can never stretch
# the bounded pass; the probe is killed and the evidence refused.
CLI_POLL_TIMEOUT_SECONDS = 5.0
# stdout and stderr are EACH hard-capped: past either cap the child is killed
# and the partial output is discarded (truncated evidence may not authorize
# anything). Applied twice: the real runner enforces it while reading, and
# payload validation re-asserts it so an injected/fake runner cannot sneak an
# oversized payload through.
CLI_POLL_MAX_OUTPUT_BYTES = 16384
# The qualified profile and URL-locator files are bounded reads; a larger or
# growing file is not a config file this integration may parse.
CLI_POLL_MAX_PROFILE_BYTES = 16384
# Clock-skew tolerance: a poll value slightly ahead of local time clamps to a
# fresh age of zero (fresh evidence authorizes nothing), while a value further
# ahead than this is future garbage and refuses the whole payload.
CLI_POLL_FUTURE_SKEW_SECONDS = 300.0

LAUNCHCTL = "/bin/launchctl"

# ---------------------------------------------------------------------------
# Executable-ancestor Homebrew Cellar allowance (identity repair, 2026-10-31).
#
# The five incumbent seats legitimately SHARE one user-owned, safe-mode
# tunnel-client binary installed under the canonical Apple-Silicon Homebrew
# prefix, whose ``Cellar`` directory is user-owned mode 0775 by Homebrew's own
# layout. Host-side permission changes (chmod/sudo/SIP) are forbidden, so the
# ONLY relaxation this integration makes for that reality is a caller-local,
# executable-only, narrowly anchored exception:
#
# - :func:`require_parent_safe` stays byte-for-byte strict GLOBALLY (plists,
#   profiles, URL locators, telemetry, manifests, watchdog roots);
# - :func:`require_executable_parent_safe` applies strict semantics to EVERY
#   ancestor of an EXECUTABLE except exactly ONE: the directory whose absolute
#   lexical path equals :data:`CANONICAL_HOMEBREW_CELLAR`, which must itself
#   verify as a real (non-symlink) directory, owned by the seat user, with
#   mode EXACTLY :data:`CELLAR_ALLOWED_MODE` (group-shared, never
#   world-writable, no sticky/setgid/setuid bits);
# - at most ONE ancestor may consume the allowance, and every other ancestor
#   keeps full strict checking;
# - the allowance directory's dev/ino/uid/mode are pinned at qualification and
#   re-proven before every effect (see fabric_tunnel_identity).
#
# Hermetic tests may inject a controlled fake prefix by patching the module
# constant; no runtime caller chooses a prefix — production callers pass no
# prefix, so the anchor is always the exact canonical path below.
CANONICAL_HOMEBREW_CELLAR = "/opt/homebrew/Cellar"
# user-owned rwxrwxr-x: group-shared, NOT world-writable, no setid/sticky bits.
CELLAR_ALLOWED_MODE = stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH | stat.S_IXOTH

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
    # True when a bounded reader killed the child because an output stream
    # exceeded its cap; the partial output is then discarded, never parsed.
    truncated: bool = False


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
# First-party CLI control-plane-poll seam. The payload validator is pure and
# shared by qualification (one probe at qualify time) and every health pass;
# the real runner below is the only process-spawning implementation and is
# injectable in hermetic tests exactly like the launchctl runner.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ControlPlanePollVerdict:
    """Typed outcome of :func:`validate_control_plane_poll_payload`.

    ``ok`` is True only for the exact known-good shape; ``reason`` is a
    stable refusal code (never payload content, never a URL or profile
    value); ``value`` is the accepted absolute Unix-seconds last-seen and
    ``age_seconds`` the derived ``now - value`` (a value within the future
    skew clamps to a fresh zero, because fresh evidence authorizes nothing).
    """

    ok: bool
    reason: str = ""
    value: float | None = None
    age_seconds: float | None = None


def validate_control_plane_poll_payload(
    stdout: str,
    stderr: str,
    returncode: int,
    *,
    now: float,
    timed_out: bool = False,
    truncated: bool = False,
) -> ControlPlanePollVerdict:
    """Strictly validate one control-plane-poll payload, failing closed.

    Only the exact known-good shape may pass: rc 0, bounded stdout+stderr,
    JSON object with ``result == "ok"``, ``healthz.ok is True``,
    ``readyz.ok is True``, and ``control_plane_poll.ok is True`` carrying a
    finite positive numeric Unix-seconds ``value`` not further ahead of
    ``now`` than the future skew. Malformed, missing, oversized, false-flag
    (any ``ok`` that is not the boolean True), non-positive, or
    future-beyond-skew payloads refuse with a stable code; refusals never
    authorize a kickstart and never echo payload content.
    """
    refused = lambda code: ControlPlanePollVerdict(False, code)  # noqa: E731 - local guard
    if timed_out:
        return refused("cli_poll_timeout")
    if truncated:
        return refused("cli_poll_output_oversized")
    if len(stdout.encode("utf-8", "replace")) > CLI_POLL_MAX_OUTPUT_BYTES:
        return refused("cli_poll_output_oversized")
    if len(stderr.encode("utf-8", "replace")) > CLI_POLL_MAX_OUTPUT_BYTES:
        return refused("cli_poll_output_oversized")
    if returncode != 0:
        return refused("cli_poll_nonzero_rc")
    try:
        doc = json.loads(stdout)
    except ValueError:
        return refused("cli_poll_malformed_json")
    if not isinstance(doc, dict):
        return refused("cli_poll_malformed_json")
    if doc.get("result") != "ok" or isinstance(doc.get("result"), bool):
        return refused("cli_poll_result_not_ok")
    healthz = doc.get("healthz")
    if not isinstance(healthz, dict) or healthz.get("ok") is not True:
        return refused("cli_poll_healthz_not_ok")
    readyz = doc.get("readyz")
    if not isinstance(readyz, dict) or readyz.get("ok") is not True:
        return refused("cli_poll_readyz_not_ok")
    poll = doc.get("control_plane_poll")
    if not isinstance(poll, dict) or poll.get("ok") is not True:
        return refused("cli_poll_not_ok")
    value = poll.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return refused("cli_poll_invalid_value")
    value = float(value)
    if value <= 0:
        return refused("cli_poll_nonpositive_value")
    if value - now > CLI_POLL_FUTURE_SKEW_SECONDS:
        return refused("cli_poll_value_in_future")
    age = now - value
    if age < 0:
        age = 0.0  # within-skew future: fresh evidence, authorizes nothing
    return ControlPlanePollVerdict(True, "", value, age)


def build_control_plane_poll_argv(executable: str, url_locator: str) -> list[str]:
    """The EXACT read-only probe argv, asserted before any caller may use it.

    Nothing else is ever executed for the first-party CLI heartbeat: no
    shell, no extra flags, no executable or locator other than the qualified
    ones this integration pins in the private manifest."""
    argv = [str(executable), "health", "--url-file", str(url_locator),
            "--require-control-plane-poll", "--json"]
    if argv[0] != executable or not os.path.isabs(argv[0]) or argv[0] == LAUNCHCTL:
        raise ActionRefused("control_plane_poll_argv_requires_absolute_qualified_executable")
    if argv[1:] != ["health", "--url-file", url_locator,
                    "--require-control-plane-poll", "--json"]:
        raise ActionRefused("control_plane_poll_argv_shape_invalid")
    return argv


def control_plane_poll_runner(argv: Sequence[str], timeout: float = CLI_POLL_TIMEOUT_SECONDS) -> RunResult:
    """Bounded read-only runner for the qualified tunnel-client health probe.

    argv-list only, no shell, ``stdin`` detached, hard deadline, and both
    output streams hard-capped at ``CLI_POLL_MAX_OUTPUT_BYTES``: past either
    cap the child is killed, the partial output is discarded, and the result
    is marked truncated so validation can never accept an oversized payload.
    This seam is separate from :func:`subprocess_runner` — it refuses to run
    launchctl, which refuses to run anything else — so no caller can cross
    the two without an explicit, reviewed choice."""
    argv = tuple(argv)
    if (
        not argv
        or not os.path.isabs(argv[0])
        or argv[0] == LAUNCHCTL
        or any(not isinstance(part, str) for part in argv)
    ):
        raise ActionRefused("control_plane_poll_runner_requires_absolute_non_launchctl_argv")
    deadline = time.monotonic() + max(0.05, float(timeout))
    try:
        proc = subprocess.Popen(  # noqa: S603 - qualified binary, list argv, no shell
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            close_fds=True,
        )
    except OSError:
        return RunResult(argv, 127, "", "", timed_out=False, truncated=False)
    out_fd = proc.stdout.fileno()
    err_fd = proc.stderr.fileno()
    caps: dict[int, bytearray] = {out_fd: bytearray(), err_fd: bytearray()}
    open_fds = [out_fd, err_fd]
    truncated = False
    timed_out = False
    while open_fds:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            break
        readable, _, _ = select.select(open_fds, [], [], min(remaining, 0.2))
        for fd in readable:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                chunk = b""
            if not chunk:
                open_fds.remove(fd)
                continue
            buffer = caps[fd]
            room = (CLI_POLL_MAX_OUTPUT_BYTES + 1) - len(buffer)
            if room > 0:
                buffer.extend(chunk[:room])
            if len(buffer) > CLI_POLL_MAX_OUTPUT_BYTES:
                truncated = True
        if truncated:
            break
    if timed_out or truncated:
        proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover - kill is best-effort
        pass
    for stream in (proc.stdout, proc.stderr):
        try:
            stream.close()
        except OSError:
            pass
    if timed_out:
        return RunResult(argv, proc.returncode if proc.returncode is not None else -9,
                         "", "", timed_out=True, truncated=False)
    if truncated:
        return RunResult(argv, proc.returncode if proc.returncode is not None else -9,
                         "", "", timed_out=False, truncated=True)
    stdout = bytes(caps[out_fd]).decode("utf-8", "replace")
    stderr = bytes(caps[err_fd]).decode("utf-8", "replace")
    returncode = proc.returncode if proc.returncode is not None else -9
    return RunResult(argv, returncode, stdout, stderr, timed_out=False, truncated=False)


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
        offending_mode_text = oct(st.st_mode & 0o777)
        raise IdentityRejected(f"{code}: group/world-writable mode {offending_mode_text}")


def require_parent_safe(path: Path, uid: int, *, code: str) -> None:
    """Every LEXICAL ancestor of ``path`` must exist, be a real directory (no
    symlink escape), and must not be group-writable or world-writable-without-
    sticky.

    Ancestors are lstat-walked on the lexical (normalized, un-resolved) path
    BEFORE any symlink resolution: a symlinked intermediate component (e.g. a
    swapped ``~/Library``) is rejected even when its target is a perfectly
    normal directory, because resolution would silently remove the inspected
    component from the path. The final component itself is not inspected here;
    its own symlink/regular-file discipline belongs to the caller.

    A sticky world-writable directory (mode 1777, e.g. the temp root) keeps
    other users from renaming or replacing entries inside it, so it is
    accepted; an unprotected world-writable ancestor is a hijack vector and
    rejects. Owner expectations are enforced on the launchd-owned files
    themselves, not on system ancestors like ``/Users``."""
    current = Path(os.path.abspath(path))
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


def verify_cellar_allowance_dir(cellar_dir: Path, uid: int, *, code: str) -> None:
    """Strict checks for the ONE allowed Cellar ancestor directory.

    It must be a real directory (never a symlink), owned by the seat user,
    and its permission bits must be EXACTLY ``CELLAR_ALLOWED_MODE``:
    group-shared, never world-writable, no sticky/setgid/setuid bits. Any
    other shape refuses; nothing here weakens the global parent guard."""
    try:
        st = cellar_dir.lstat()
    except OSError as exc:
        raise IdentityRejected(f"{code}: cellar allowance dir unreadable ({exc.strerror})") from exc
    if stat.S_ISLNK(st.st_mode):
        raise IdentityRejected(f"{code}: cellar allowance dir is a symlink")
    if not stat.S_ISDIR(st.st_mode):
        raise IdentityRejected(f"{code}: cellar allowance dir is not a directory")
    if st.st_uid != uid:
        raise IdentityRejected(f"{code}: cellar allowance dir not owned by seat user")
    actual_mode = stat.S_IMODE(st.st_mode)
    if actual_mode != CELLAR_ALLOWED_MODE:
        raise IdentityRejected(
            f"{code}: cellar allowance dir mode {oct(actual_mode)} != {oct(CELLAR_ALLOWED_MODE)}"
        )


@dataclass(frozen=True)
class ExecutableParentVerdict:
    """Result of the executable-only ancestor walk: which ancestor, if any,
    consumed the single Cellar allowance, so the caller can pin its exact
    directory identity and re-prove it before every effect."""

    cellar_ancestor: str | None = None


def require_executable_parent_safe(
    path: Path,
    uid: int,
    *,
    code: str,
    cellar_dir: str | None = None,
) -> ExecutableParentVerdict:
    """``require_parent_safe`` semantics for an EXECUTABLE's lexical ancestor
    chain, with exactly ONE narrowly anchored exception.

    Every ancestor is walked exactly as :func:`require_parent_safe` walks
    them (lexical, lstat, symlink-refusing, protected-world-writable and
    group-write rules — the strict reference implementation above is kept
    byte-for-byte unchanged). The single difference: an ancestor whose
    absolute lexical path equals the allowance anchor may instead pass
    :func:`verify_cellar_allowance_dir`'s exact shape checks; at most ONE
    ancestor may consume the allowance, and every other ancestor stays fully
    strict. The anchor is :data:`CANONICAL_HOMEBREW_CELLAR`; the ``cellar_dir``
    parameter exists for hermetic tests to inject a controlled fake prefix
    and is never passed by any runtime caller."""
    anchor = os.path.abspath(cellar_dir) if cellar_dir is not None else CANONICAL_HOMEBREW_CELLAR
    current = Path(os.path.abspath(path))
    cellar_ancestor: str | None = None
    for component in reversed(current.parents):
        component_text = str(component)
        if component_text == anchor:
            if cellar_ancestor is not None:
                raise IdentityRejected(f"{code}: multiple cellar allowance ancestors")
            verify_cellar_allowance_dir(component, uid, code=code)
            cellar_ancestor = component_text
            continue
        try:
            st = component.lstat()
        except OSError as exc:
            raise IdentityRejected(f"{code}: unreadable ancestor ({exc.strerror})") from exc
        if stat.S_ISLNK(st.st_mode):
            raise IdentityRejected(f"{code}: symlinked ancestor {component}")
        if not stat.S_ISDIR(st.st_mode):
            raise IdentityRejected(f"{code}: non-directory ancestor {component}")
        if (st.st_mode & stat.S_IWOTH) and (st.st_mode & stat.S_ISVTX):
            continue  # protected convention directory (mode 1777)
        if (st.st_mode & stat.S_IWOTH) or (st.st_mode & stat.S_IWGRP):
            raise IdentityRejected(f"{code}: unprotected writable ancestor {component}")
    return ExecutableParentVerdict(cellar_ancestor=cellar_ancestor)


@dataclass(frozen=True)
class FileIdentity:
    """Pinned identity of one verified regular file, read from a single
    nofollow descriptor so the metadata and the digested bytes are ONE inode
    observation: ``(dev, ino)`` as a hard in-place-replacement tripwire,
    owner uid, permission bits, link count, declared size, and the SHA-256
    of the exact bytes read through that descriptor."""

    dev: int
    ino: int
    uid: int
    mode: int  # permission bits (stat.S_IMODE) as fstat reported them
    nlink: int
    size: int
    sha256: str
    data: bytes


def verified_file_identity(
    path: Path,
    uid: int,
    *,
    code: str,
    max_bytes: int | None = None,
    require_owner_uid: bool = False,
    require_nlink_one: bool = False,
) -> FileIdentity:
    """Open ``path`` with ``O_NOFOLLOW``, fstat the descriptor, and digest the
    exact bytes read through it, failing closed.

    A symlink at ``path`` never opens (ELOOP); a replacement between any
    earlier lstat and this call cannot split the recorded identity, because
    every pinned field comes from ONE descriptor observation. Consumers pin
    this result and re-compare dev/ino/uid/mode/digest before every effect.
    Refusal messages carry the stable ``code`` prefix and never file
    contents."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise IdentityRejected(f"{code}: unreadable ({exc.strerror})") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise IdentityRejected(f"{code}: not a regular file")
        if require_owner_uid and st.st_uid != uid:
            raise IdentityRejected(f"{code}: owner uid {st.st_uid} != seat uid {uid}")
        if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise IdentityRejected(
                f"{code}: group/world-writable mode {oct(stat.S_IMODE(st.st_mode))}"
            )
        if require_nlink_one and st.st_nlink != 1:
            raise IdentityRejected(f"{code}: hardlink (nlink={st.st_nlink}) is not a unique private file")
        chunks: list[bytes] = []
        remaining = max_bytes + 1 if max_bytes is not None else -1
        while remaining != 0:
            chunk = os.read(fd, 65536 if remaining < 0 else min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            if remaining > 0:
                remaining -= len(chunk)
        data = b"".join(chunks)
        if max_bytes is not None and len(data) > max_bytes:
            raise IdentityRejected(f"{code}_oversized")
        return FileIdentity(
            dev=st.st_dev,
            ino=st.st_ino,
            uid=st.st_uid,
            mode=stat.S_IMODE(st.st_mode),
            nlink=st.st_nlink,
            size=st.st_size,
            sha256=sha256_bytes(data),
            data=data,
        )
    finally:
        os.close(fd)


@dataclass(frozen=True)
class DirIdentity:
    """Pinned identity of one verified directory from a nofollow descriptor:
    the ``(dev, ino)`` in-place-replacement tripwire, owner uid, and
    permission bits."""

    dev: int
    ino: int
    uid: int
    mode: int


def verified_dir_identity(
    path: Path,
    uid: int,
    *,
    code: str,
    require_owner_uid: bool = False,
) -> DirIdentity:
    """Open ``path`` with ``O_NOFOLLOW|O_DIRECTORY`` and fstat it, failing
    closed. The pinned ``(dev, ino, uid, mode)`` lets consumers detect an
    in-place directory replacement (same path, different inode) before any
    effect, not merely after an age boundary."""
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise IdentityRejected(f"{code}: unreadable ({exc.strerror})") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISDIR(st.st_mode):
            raise IdentityRejected(f"{code}: not a directory")
        if require_owner_uid and st.st_uid != uid:
            raise IdentityRejected(f"{code}: owner uid {st.st_uid} != seat uid {uid}")
        return DirIdentity(
            dev=st.st_dev, ino=st.st_ino, uid=st.st_uid, mode=stat.S_IMODE(st.st_mode)
        )
    finally:
        os.close(fd)


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
