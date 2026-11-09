"""Closed, read-only Hermes team roster projection (``mastermind.team_roster/v1``).

Enumerates the enrolled Hermes bots on one install from actual on-disk sources
and reports only what was observed.  This module owns no transport, queue,
registry, credential read or lifecycle: it is a projection over facts that
already exist (profile directories, ``profile.yaml`` identity, the per-profile
``gateway.lock`` owner claim, and each profile's ``state.db`` activity columns).

Honesty rules (binding, same family as WO-04 thermal):
  * an unobserved fact is ``unknown`` (readiness) or ``null`` (activity) with a
    typed reason code — never ``ready``, never zero, never a fabricated count;
  * recycled PIDs lie: a ``gateway.lock`` pid is only believed when the live
    ``ps`` row carries a gateway-shaped command line AND a process start time
    within ``PID_START_TOLERANCE_S`` of the lock's recorded ``start_time``
    (WO-19 §6 pitfall, applied here to roster liveness);
  * profile identity mirrors the roster mechanism in the Hermes agent source
    (``tools.bot_mode_probe._roster`` over ``hermes_constants`` predicates) at
    the pinned install revision: infra dirs, ghost shells and tombstoned
    profiles are never teammates;
  * no secret is ever read: ``profile.yaml`` contributes only display/role
    text; ``auth.json``/``.env`` are never opened.  Every emitted string passes
    a credential scrubber.

Pure standard library (PyYAML is used when importable; without it the
profile-derived display/role fields degrade to ``unknown`` honestly).
"""
from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

TEAM_ROSTER_SCHEMA = "mastermind.team_roster/v1"

READINESS_READY = "ready"
READINESS_DEGRADED = "degraded"
READINESS_UNKNOWN = "unknown"
READINESS_STATES = frozenset({READINESS_READY, READINESS_DEGRADED, READINESS_UNKNOWN})

# Mirror of hermes_constants._PROFILE_IDENTITY_MARKERS at the pinned revision.
PROFILE_IDENTITY_MARKERS = (
    "config.yaml", ".env", "SOUL.md", "profile.yaml", "auth.json", "state.db",
)
# Mirror of hermes_constants.PROFILE_ID_RE (canonical named-profile id grammar).
PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
# Mirror of hermes_constants._DELETED_PROFILES_DIR / profile_tombstone_path.
DELETED_PROFILES_DIR = ".deleted-profiles"

DEFAULT_PROFILE_ID = "default"
MAX_PROFILES = 64
MAX_TEXT_CHARS = 240
MAX_ROLE_CHARS = 160
MAX_REASON_CHARS = 64
REASON_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{1,63}")
ISO_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:?\d{2}|Z)")

HOST_UNKNOWN = "unknown"
HOST_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")

PID_START_TOLERANCE_S = 300.0
DB_OPEN_TIMEOUT_S = 2.0

GATEWAY_SOURCES = frozenset({"control_socket_identify", "gateway_lock", "none"})
FAILURE_REASONS = frozenset({
    "provider_auth_or_access", "provider_quota_limit", "provider_rate_limit",
    "provider_server_error", "context_overflow", "missing_config",
    "model_unavailable", "target_scope_unresolved", "unknown",
})

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"ghp_[A-Za-z0-9]{10,}"),
    re.compile(r"xox[abposr]-[A-Za-z0-9\-]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)(secret\"?\s*[:=]\s*\"?)[^\s\",}]{8,}"),
)


def scrub(value: str) -> str:
    """Credential-shaped content never enters a roster field."""
    out = value
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "[REDACTED]", out)
    return out


def bounded(value: Any, limit: int) -> str:
    text = scrub(" ".join(str(value or "").split()))
    return text[:limit]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _unix_to_iso(seconds: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(seconds), tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


# ── profile enumeration (mirrors tools.bot_mode_probe._roster) ───────────────


def profile_is_deleted(profile_dir: Path) -> bool:
    tombstone = profile_dir.parent / DELETED_PROFILES_DIR / profile_dir.name
    return tombstone.exists()


def profile_has_identity(profile_dir: Path) -> bool:
    """A dir is a profile only when an identity marker claims it (links count)."""
    for marker in PROFILE_IDENTITY_MARKERS:
        path = profile_dir / marker
        if path.is_symlink():
            return True
        try:
            if path.is_file():
                return True
        except OSError:
            continue
    return False


def enumerate_profiles(root: Path) -> list[tuple[str, Path]]:
    """(id, dir) for the default profile plus every live named profile, sorted.

    Same identity predicate as the roster mechanism: infra dirs, non-ids,
    tombstones and marker-less ghost shells are not teammates.
    """
    root = Path(root)
    roster: list[tuple[str, Path]] = [(DEFAULT_PROFILE_ID, root)]
    profiles = root / "profiles"
    named: list[tuple[str, Path]] = []
    if profiles.is_dir():
        try:
            candidates = sorted(profiles.iterdir())
        except OSError:
            candidates = []
        for entry in candidates:
            if (entry.name != DEFAULT_PROFILE_ID and PROFILE_ID_RE.match(entry.name)
                    and entry.is_dir() and profile_has_identity(entry)
                    and not profile_is_deleted(entry)):
                named.append((entry.name, entry))
    roster.extend(named)
    return roster[:MAX_PROFILES]


# ── profile.yaml identity (display name / role / Bot-Mode management) ───────


def read_profile_yaml(profile_dir: Path) -> dict | None:
    """Parsed profile.yaml mapping, or None when missing/unreadable/not a mapping."""
    path = Path(profile_dir) / "profile.yaml"
    try:
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    try:
        import yaml
    except ImportError:  # honest degradation, never a guess
        return None
    try:
        data = yaml.safe_load(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _bots_meta(data: dict | None) -> dict | None:
    ui_meta = data.get("ui_meta") if data else None
    bots = ui_meta.get("hermes-bots") if isinstance(ui_meta, dict) else None
    return bots if isinstance(bots, dict) else None


def profile_display_name(profile_id: str, data: dict | None) -> str:
    """Bot-Mode title, then profile display_name, else the profile id."""
    title = str((_bots_meta(data) or {}).get("title") or "").strip()
    display = str((data or {}).get("display_name") or "").strip()
    return bounded(title or display or profile_id, MAX_TEXT_CHARS)


def profile_role(data: dict | None) -> str:
    """'title — description' role line, "" when neither is set (≤160 chars)."""
    parts = [str((_bots_meta(data) or {}).get("title") or "").strip(),
             str((data or {}).get("description") or "").strip()]
    return bounded(" — ".join(part for part in parts if part), MAX_ROLE_CHARS)


def profile_is_bot_managed(data: dict | None) -> bool:
    return _bots_meta(data) is not None


# ── gateway owner evidence ───────────────────────────────────────────────────


def read_gateway_lock(profile_dir: Path) -> dict | None:
    path = Path(profile_dir) / "gateway.lock"
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def ps_rows() -> dict[str, dict]:
    """pid → {started_epoch_s, command} from one bounded ps call (empty on failure)."""
    try:
        out = subprocess.run(["ps", "-axo", "pid=,lstart=,command="],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return {}
    rows: dict[str, dict] = {}
    for line in out.stdout.splitlines():
        parts = line.strip().split(None, 6)
        if len(parts) < 7:
            continue
        try:
            started = datetime.strptime(" ".join(parts[2:6]), "%a %b %d %H:%M:%S %Y")
        except ValueError:
            continue
        rows[parts[0]] = {"started_epoch_s": started.timestamp(),
                          "command": parts[6]}
    return rows


def verify_lock_pid(lock: dict, processes: dict[str, dict]) -> tuple[bool, str]:
    """Believe a gateway.lock pid only with a live gateway-shaped command line
    and a start time consistent with the lock's claim (recycled PIDs lie)."""
    pid = lock.get("pid")
    if type(pid) is not int or pid <= 0:
        return False, "LOCK_PID_INVALID"
    row = processes.get(str(pid))
    if row is None:
        return False, "GATEWAY_PID_NOT_RUNNING"
    if not re.search(r"gateway|hermes", row["command"], re.I):
        return False, "GATEWAY_PID_RECYCLED"
    claimed = lock.get("start_time")
    if type(claimed) is int and claimed > 0:
        claimed_s = claimed / 1000.0 if claimed > 10**12 else float(claimed)
        if abs(row["started_epoch_s"] - claimed_s) > PID_START_TOLERANCE_S:
            return False, "GATEWAY_PID_START_MISMATCH"
    return True, "GATEWAY_LOCK_PID_VERIFIED"


def probe_control_socket(profile_dir: Path, timeout: float = 1.5) -> dict:
    """One read-only identify on the profile-local control socket, if any.

    Named profiles are usually served by the install root's multiplexer and
    carry no local socket; absence is reported, never guessed around.
    """
    path = Path(profile_dir) / "gateway.sock"
    if not path.exists():
        return {"observed": False, "reason": "NO_CONTROL_SOCKET"}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(timeout)
            peer.connect(str(path))
            peer.sendall(b'{"protocol":1,"id":1,"verb":"identify"}\n')
            data = bytearray()
            while b"\n" not in data:
                chunk = peer.recv(4096)
                if not chunk or len(data) + len(chunk) > 65536:
                    return {"observed": False, "reason": "SOCKET_ANSWER_INVALID"}
                data.extend(chunk)
    except OSError:
        return {"observed": False, "reason": "SOCKET_UNREACHABLE"}
    try:
        answer = json.loads(bytes(data).split(b"\n", 1)[0])
        result = answer.get("result") if isinstance(answer, dict) else None
        if not isinstance(result, dict) or answer.get("ok") is not True:
            return {"observed": False, "reason": "IDENTIFY_REFUSED"}
        if str(result.get("hermes_home")) != str(Path(profile_dir)):
            return {"observed": False, "reason": "GATEWAY_HOME_MISMATCH"}
        return {"observed": True, "state": str(result.get("state") or ""),
                "instance_id": str(result.get("instance_id") or ""),
                "authority_epoch": result.get("authority_epoch"),
                "code_version": str(result.get("code_version") or ""),
                "hermes_home": str(result.get("hermes_home"))}
    except (ValueError, TypeError):
        return {"observed": False, "reason": "IDENTIFY_ANSWER_INVALID"}


def gateway_observation(profile_dir: Path, *, processes: dict[str, dict],
                        identify: dict | None = None) -> dict:
    """Per-profile gateway evidence → closed projection with typed readiness."""
    identity: dict[str, Any] = {
        "observed": False, "source": "none", "instanceId": None,
        "authorityEpoch": None, "codeVersion": None, "pid": None, "state": None,
    }
    if identify is None or identify.get("observed") is not True:
        local = probe_control_socket(profile_dir)
        if local.get("observed") is True:
            identify = local
    if identify is not None and identify.get("observed") is True:
        claimed_home = str(identify.get("hermes_home") or "")
        if claimed_home and claimed_home != str(Path(profile_dir)):
            # An answering gateway that belongs to another home is real evidence
            # about ANOTHER profile: never readiness for this one.
            identity.update(observed=True, source="control_socket_identify",
                            state=bounded(identify.get("state"), 32) or None)
            return {"gateway": identity, "readiness": READINESS_DEGRADED,
                    "readinessReason": "GATEWAY_HOME_MISMATCH"}
        epoch = identify.get("authority_epoch")
        identity.update(observed=True, source="control_socket_identify",
                        instanceId=bounded(identify.get("instance_id"), 160) or None,
                        authorityEpoch=epoch if type(epoch) is int and epoch >= 1 else None,
                        codeVersion=bounded(identify.get("code_version"), 64) or None,
                        state=bounded(identify.get("state"), 32) or None)
        readiness = (READINESS_READY if identity["state"] == "ready"
                     else READINESS_DEGRADED)
        reason = "GATEWAY_IDENTIFY_READY" if readiness == READINESS_READY else "GATEWAY_NOT_READY_STATE"
        return {"gateway": identity, "readiness": readiness, "readinessReason": reason}
    lock = read_gateway_lock(profile_dir)
    if lock is None:
        # No live-owner evidence at all: absent lock AND no answering socket.
        return {"gateway": identity, "readiness": READINESS_UNKNOWN,
                "readinessReason": "NO_GATEWAY_LOCK"}
    identity.update(observed=True, source="gateway_lock",
                    pid=lock.get("pid") if type(lock.get("pid")) is int else None,
                    state="lock_only")
    believed, reason = verify_lock_pid(lock, processes)
    if believed:
        return {"gateway": identity, "readiness": READINESS_READY,
                "readinessReason": "GATEWAY_LOCK_PID_VERIFIED"}
    return {"gateway": identity, "readiness": READINESS_DEGRADED,
            "readinessReason": reason}


# ── activity (state.db last_activity columns, read-only) ─────────────────────


def read_activity(profile_dir: Path) -> dict:
    """Newest session activity from state.db (mode=ro), null + reason when unobserved."""
    db = Path(profile_dir) / "state.db"
    if not db.is_file():
        return {"lastActivity": None, "activitySummary": None, "activityReason": "NO_STATE_DB"}
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=DB_OPEN_TIMEOUT_S)
        try:
            row = con.execute(
                "select last_activity_at, title, last_activity_description "
                "from sessions order by last_activity_at desc limit 1").fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return {"lastActivity": None, "activitySummary": None,
                "activityReason": "STATE_DB_UNREADABLE"}
    if row is None or row[0] is None:
        return {"lastActivity": None, "activitySummary": None, "activityReason": "NO_SESSIONS"}
    iso = _unix_to_iso(row[0])
    if iso is None:
        return {"lastActivity": None, "activitySummary": None,
                "activityReason": "ACTIVITY_TIMESTAMP_INVALID"}
    summary = bounded(row[2] or row[1], MAX_TEXT_CHARS)
    return {"lastActivity": iso, "activitySummary": summary or None}


# ── projection ───────────────────────────────────────────────────────────────


def generate_team_roster(root: Path, *, host: str | None = None,
                         identify: Callable[[str, Path], dict] | None = None,
                         processes: dict[str, dict] | None = None,
                         now: str | None = None) -> dict:
    """Build the ``mastermind.team_roster/v1`` document for one install root.

    ``identify``: optional injected per-profile control-socket observation
    (used by tests and by hosts that already hold an identify answer for the
    primary profile).  ``processes``: optional injected ``ps`` rows.
    """
    root = Path(root)
    roster_dirs = enumerate_profiles(root)
    ps = processes if processes is not None else ps_rows()
    bots = []
    for profile_id, profile_dir in roster_dirs:
        data = read_profile_yaml(profile_dir)
        supplied = identify(profile_id, profile_dir) if identify else None
        observed = gateway_observation(profile_dir, processes=ps, identify=supplied)
        activity = read_activity(profile_dir)
        bots.append({
            "id": profile_id,
            "displayName": profile_display_name(profile_id, data),
            "role": profile_role(data),
            "profilePath": str(profile_dir),
            "managed": profile_is_bot_managed(data) if data is not None else None,
            "host": host if host is not None else (socket.gethostname() or HOST_UNKNOWN),
            **observed,
            **activity,
        })
    return {
        "schema": TEAM_ROSTER_SCHEMA,
        "generatedAt": now or _iso_now(),
        "host": host if host is not None else (socket.gethostname() or HOST_UNKNOWN),
        "bots": bots,
    }


# ── fail-closed validation (python mirror of the TS parser) ──────────────────


def _text(value: Any, limit: int, *, nullable=False, empty=False) -> str | None:
    if nullable and value is None:
        return None
    if type(value) is not str or (not empty and not value) or len(value) > limit:
        raise ValueError("invalid roster text")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("invalid roster text")
    return scrub(value)


def _reason(value: Any) -> str:
    if type(value) is not str or REASON_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid roster reason")
    return value


def validate_team_roster(value: Any) -> dict:
    """Closed-set validation; raises ValueError on any unknown/ill-typed field."""
    if type(value) is not dict or value.get("schema") != TEAM_ROSTER_SCHEMA:
        raise ValueError("invalid roster schema")
    if set(value) != {"schema", "generatedAt", "host", "bots"}:
        raise ValueError("invalid roster fields")
    if type(value["generatedAt"]) is not str or ISO_PATTERN.fullmatch(value["generatedAt"]) is None:
        raise ValueError("invalid roster timestamp")
    host = _text(value["host"], 64)
    if HOST_PATTERN.fullmatch(host) is None and host != HOST_UNKNOWN:
        raise ValueError("invalid roster host")
    bots = value["bots"]
    if type(bots) is not list or len(bots) > MAX_PROFILES:
        raise ValueError("invalid roster rows")
    ids: set[str] = set()
    for row in bots:
        if type(row) is not dict:
            raise ValueError("invalid roster row")
        if not set(row) <= {"id", "displayName", "role", "profilePath", "managed",
                            "host", "gateway", "readiness", "readinessReason",
                            "lastActivity", "activitySummary", "activityReason"}:
            raise ValueError("invalid roster row fields")
        for key in ("id", "displayName", "readiness", "readinessReason"):
            if key not in row:
                raise ValueError(f"missing roster field {key}")
        bot_id = _text(row["id"], 64)
        if PROFILE_ID_RE.fullmatch(bot_id) is None or bot_id in ids:
            raise ValueError("invalid roster id")
        ids.add(bot_id)
        _text(row["displayName"], MAX_TEXT_CHARS)
        if row.get("role") is not None:
            _text(row["role"], MAX_ROLE_CHARS, empty=True)
        if row.get("managed") is not None and type(row["managed"]) is not bool:
            raise ValueError("invalid roster managed flag")
        _text(row["host"], 64)
        if row["readiness"] not in READINESS_STATES:
            raise ValueError("invalid roster readiness")
        _reason(row["readinessReason"])
        if "profilePath" in row:
            path = _text(row["profilePath"], 512)
            if path is not None and (path.startswith("~") or "\n" in path
                    or not path.startswith("/")):
                raise ValueError("invalid roster profile path")
        if "lastActivity" in row:
            iso = row["lastActivity"]
            if iso is not None and (type(iso) is not str
                    or ISO_PATTERN.fullmatch(iso) is None):
                raise ValueError("invalid roster activity time")
        if "activitySummary" in row and row["activitySummary"] is not None:
            _text(row["activitySummary"], MAX_TEXT_CHARS)
        if "activityReason" in row and row["activityReason"] is not None:
            _reason(row["activityReason"])
        if row.get("lastActivity") is None and "activityReason" not in row:
            raise ValueError("unobserved activity needs a reason")
        if row.get("lastActivity") is not None and row.get("activityReason") is not None:
            raise ValueError("observed activity carries no reason")
        if "gateway" in row:
            gateway = row["gateway"]
            if type(gateway) is not dict or set(gateway) != {
                    "observed", "source", "instanceId", "authorityEpoch",
                    "codeVersion", "pid", "state"}:
                raise ValueError("invalid roster gateway")
            if type(gateway["observed"]) is not bool or gateway["source"] not in GATEWAY_SOURCES:
                raise ValueError("invalid roster gateway source")
            for key in ("instanceId", "codeVersion", "state"):
                if gateway[key] is not None:
                    _text(gateway[key], 160, empty=True)
            if gateway["authorityEpoch"] is not None and (
                    type(gateway["authorityEpoch"]) is not int or gateway["authorityEpoch"] < 1):
                raise ValueError("invalid roster gateway epoch")
            if gateway["pid"] is not None and (
                    type(gateway["pid"]) is not int or gateway["pid"] < 1):
                raise ValueError("invalid roster gateway pid")
            if gateway["observed"] is False and gateway["source"] != "none":
                raise ValueError("unobserved gateway has no source")
    return value
