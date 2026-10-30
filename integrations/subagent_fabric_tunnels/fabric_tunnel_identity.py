"""Deterministic identity verification and the private qualification manifest.

FTR-2 first half: before any plist is extended, each of the five EXISTING
seats must pass every check here. Qualification is an explicit operator step
performed against first-party host readback; it records the exact observed
identity into a PRIVATE manifest (0600) that later installs re-verify. This
is the mechanism that makes it impossible to accidentally adopt another
seat's argv (the chatgpt1 hazard the plan names): an install refuses unless
the current plist bytes are exactly the qualified bytes.

Nothing in this module invents a tunnel identity, credential, command
argument, or terminal binding. It only observes, pins, and re-verifies.
"""
from __future__ import annotations

import json
import os
import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from fabric_tunnel_common import (
    IDENTITY_MANIFEST_SCHEMA,
    KEEP_ALIVE,
    MANIFEST_MAX_AGE_SECONDS,
    MASTER_SHA,
    PLAN_COMMIT,
    RUN_AT_LOAD,
    THROTTLE_INTERVAL_MIN,
    TUNNEL_LABELS,
    TUNNEL_LABEL_PREFIX,
    OWNED_LABELS,
    WATCHDOG_LABEL,
    Alert,
    IdentityRejected,
    PolicyRefused,
    backups_dir,
    evidence_line,
    executable_path_reject_reason,
    launchagents_dir,
    manifest_path,
    parse_plist_bytes,
    plist_relpath,
    private_state_root,
    require_owner_writable_safe,
    require_parent_safe,
    require_regular_file,
    serialize_plist,
    sha256_bytes,
)

# argv[0] must be absolute; launchd requires it for user agents and it is the
# anchor of every executable identity check below.
_ARGV_MAX = 64

# Heartbeat and host-fact fields recorded per seat / per host at
# qualification. They are OPTIONAL: absence is an unqualified-health alert,
# never a guessed default path.
_SEAT_OPTIONAL_FIELDS = ("heartbeat_path",)
_HOST_OPTIONAL_FIELDS = (
    "native_store_path",
    "host_pull_telemetry_dir",
    "pinned_generation",
    "stale_telemetry_seconds",
    "repair",
)


@dataclass(frozen=True)
class SeatIdentity:
    label: str
    plist_rel: str
    plist_sha256: str
    plist_mode: int
    program_arguments: tuple[str, ...]
    executable: str
    executable_sha256: str
    uid: int

    def public_fields(self) -> dict[str, Any]:
        """Secret-safe identity table fields (no argv body, no env)."""
        return {
            "label": self.label,
            "plist_relpath": self.plist_rel,
            "plist_sha256": self.plist_sha256[:16],
            "plist_mode": oct(self.plist_mode),
            "argv_len": len(self.program_arguments),
            "executable": self.executable,
            "executable_sha256": self.executable_sha256[:16],
            "uid": self.uid,
        }


# ---------------------------------------------------------------------------
# Structural verification of one installed plist.
# ---------------------------------------------------------------------------


def verify_seat(home: Path, label: str, uid: int, *, now: float | None = None) -> SeatIdentity:
    """Verify one seat's installed plist identity, failing closed.

    Rejection codes are stable strings so runbook/tooling evidence can cite
    the exact fence that fired.
    """
    del now  # reserved for freshness policy; identity checks are time-free
    home = Path(home)
    if label not in TUNNEL_LABELS:
        raise IdentityRejected("label_outside_allowlist")
    launch_dir = launchagents_dir(home)
    require_parent_safe(launch_dir / "x", uid, code="launchagents_parent_unsafe")
    if launch_dir.is_symlink():
        raise IdentityRejected("launchagents_symlink")
    plist_path = home / plist_relpath(label)
    require_regular_file(plist_path, code=f"{label}_plist_unavailable")
    require_owner_writable_safe(plist_path, uid, code=f"{label}_plist_owner_unsafe")

    raw = plist_path.read_bytes()
    working = parse_plist_bytes(raw, code=f"{label}_plist_invalid")

    observed_label = working.get("Label")
    if observed_label != label:
        raise IdentityRejected(f"{label}_label_mismatch (observed {observed_label!r})")

    argv = working.get("ProgramArguments")
    if not isinstance(argv, list) or not (1 <= len(argv) <= _ARGV_MAX):
        raise IdentityRejected(f"{label}_argv_invalid_shape")
    if not all(isinstance(item, str) and item for item in argv):
        raise IdentityRejected(f"{label}_argv_invalid_element")
    program = working.get("Program")
    if program is not None and program != argv[0]:
        raise IdentityRejected(f"{label}_program_argv0_mismatch")
    executable = argv[0]
    if not posixpath.isabs(executable):
        raise IdentityRejected(f"{label}_argv0_not_absolute")

    contamination = executable_path_reject_reason(label, executable)
    if contamination:
        raise IdentityRejected(f"{label}_foreign_identity: {contamination}")

    exec_path = Path(executable)
    require_regular_file(exec_path, code=f"{label}_executable_unavailable")
    require_parent_safe(exec_path, uid, code=f"{label}_executable_parent_unsafe")
    try:
        exec_mode = exec_path.stat().st_mode
    except OSError as exc:
        raise IdentityRejected(f"{label}_executable_unavailable ({exc.strerror})") from exc
    if exec_mode & 0o022:
        raise IdentityRejected(f"{label}_executable_group_world_writable")
    try:
        exec_bytes = exec_path.read_bytes()
    except OSError as exc:
        raise IdentityRejected(f"{label}_executable_unreadable ({exc.strerror})") from exc
    # Self-referential and state-root escapes are rejected outright.
    state_root = str(private_state_root(home))
    resolved_exec = str(exec_path.resolve())
    if resolved_exec.startswith(str(launchagents_dir(home).resolve()) + os.sep):
        raise IdentityRejected(f"{label}_executable_inside_launchagents")
    if resolved_exec.startswith(state_root + os.sep):
        raise IdentityRejected(f"{label}_executable_inside_private_state")

    return SeatIdentity(
        label=label,
        plist_rel=plist_relpath(label),
        plist_sha256=sha256_bytes(raw),
        plist_mode=plist_path.stat().st_mode & 0o7777,
        program_arguments=tuple(argv),
        executable=resolved_exec,
        executable_sha256=sha256_bytes(exec_bytes),
        uid=uid,
    )


def verify_all_seats(home: Path, uid: int) -> list[SeatIdentity]:
    home = Path(home)
    """Verify all five seats in stable label order; tuple distinctness enforced.

    Byte-identical ProgramArguments across two seats means one seat is wearing
    another's tunnel identity — exactly the adoption failure the plan forbids.
    """
    identities = [verify_seat(home, label, uid) for label in sorted(TUNNEL_LABELS)]
    seen_argv: dict[tuple[str, ...], str] = {}
    for identity in identities:
        holder = seen_argv.get(identity.program_arguments)
        if holder is not None:
            raise IdentityRejected(
                f"argv_tuple_duplicated:{identity.label}:{holder}"
            )
        seen_argv[identity.program_arguments] = identity.label
    return identities


def scan_family(home: Path) -> list[str]:
    """List plist filenames in the integration's label family.

    Any family member outside the owned labels (five clients + watchdog) is a
    rogue label: install refuses while it exists, and the runbook requires an
    explicit human decision about it. The Desktop Commander carrier is NOT in
    this family and is never returned, parsed, or referenced here.
    """
    launch_dir = launchagents_dir(Path(home))
    if not launch_dir.is_dir():
        return []
    rogue: list[str] = []
    for entry in sorted(launch_dir.glob("*.plist")):
        stem = entry.stem
        if not stem.startswith(TUNNEL_LABEL_PREFIX):
            continue
        if stem not in OWNED_LABELS:
            rogue.append(stem)
    return rogue


# ---------------------------------------------------------------------------
# Policy deltas (FTR-2): the ONLY keys this integration ever changes.
# ---------------------------------------------------------------------------


def policy_changes(observed: Mapping[str, Any]) -> dict[str, Any]:
    """Return exactly the policy keys that must change to reach FTR-2 state.

    - RunAtLoad: must be boolean True.
    - KeepAlive: must be the unconditional boolean True; dict forms are
      replaced (the tunnel client may exit 0 after SIGTERM and must restart).
    - ThrottleInterval: raised to 10 when absent or below 10; a compliant
      larger incumbent value is preserved.
    """
    changes: dict[str, Any] = {}
    if observed.get("RunAtLoad") is not RUN_AT_LOAD:
        changes["RunAtLoad"] = RUN_AT_LOAD
    keep = observed.get("KeepAlive")
    if keep is not KEEP_ALIVE or not isinstance(keep, bool):
        changes["KeepAlive"] = KEEP_ALIVE
    throttle = observed.get("ThrottleInterval")
    if not isinstance(throttle, int) or isinstance(throttle, bool) or throttle < THROTTLE_INTERVAL_MIN:
        changes["ThrottleInterval"] = THROTTLE_INTERVAL_MIN
    return changes


# ---------------------------------------------------------------------------
# Private qualification manifest.
# ---------------------------------------------------------------------------


def build_manifest(
    home: Path,
    uid: int,
    identities: list[SeatIdentity],
    observed_plists: Mapping[str, Mapping[str, Any]],
    *,
    operator_confirmed: bool,
    now: float,
    seat_options: Mapping[str, Mapping[str, Any]] | None = None,
    host_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the manifest. ``observed_plists`` keeps each seat's full
    pre-install plist so post-install verification can prove that ONLY the
    policy trio changed; it stays private (0600) and is never printed whole.
    """
    if not operator_confirmed:
        raise PolicyRefused("manifest_requires_explicit_operator_confirmation")
    home = Path(home)
    if sorted(identity.label for identity in identities) != sorted(TUNNEL_LABELS):
        raise PolicyRefused("manifest_requires_exactly_five_seats")
    rogue = scan_family(home)
    if rogue:
        raise PolicyRefused(f"rogue_family_labels_present: {','.join(rogue)}")

    seats: dict[str, Any] = {}
    for identity in identities:
        observed = observed_plists.get(identity.label)
        if observed is None or serialize_plist(observed) != serialize_plist(
            parse_plist_bytes(
                (home / identity.plist_rel).read_bytes(), code=identity.label + "_manifest_pin"
            )
        ):
            raise PolicyRefused(f"{identity.label}_observed_plist_not_current_bytes")
        entry: dict[str, Any] = {
            "plist_relpath": identity.plist_rel,
            "plist_sha256": identity.plist_sha256,
            "plist_mode": identity.plist_mode,
            "program_arguments": list(identity.program_arguments),
            "executable": identity.executable,
            "executable_sha256": identity.executable_sha256,
            "uid": identity.uid,
            "observed_plist": json.loads(json.dumps(observed)),
        }
        for field_name in _SEAT_OPTIONAL_FIELDS:
            value = (seat_options or {}).get(identity.label, {}).get(field_name)
            if value is not None:
                entry[field_name] = str(value)
        seats[identity.label] = entry

    manifest: dict[str, Any] = {
        "schema": IDENTITY_MANIFEST_SCHEMA,
        "plan_commit": PLAN_COMMIT,
        "master_sha": MASTER_SHA,
        "recorded_at": now,
        "operator_confirmed": True,
        "recorded_note": "first-party host readback, operator-confirmed; private, never committed",
        "seats": seats,
    }
    for field_name in _HOST_OPTIONAL_FIELDS:
        value = (host_options or {}).get(field_name)
        if value is not None:
            manifest[field_name] = value
    return manifest


def write_manifest(home: Path, manifest: Mapping[str, Any]) -> Path:
    from fabric_tunnel_common import atomic_write_bytes

    home = Path(home)
    target = manifest_path(home)
    raw = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    atomic_write_bytes(target, raw, 0o600)
    os.chmod(target, 0o600)
    return target


def load_manifest(home: Path, *, now: float) -> dict[str, Any]:
    home = Path(home)
    path = manifest_path(home)
    require_regular_file(path, code="manifest_unavailable")
    if path.stat().st_mode & 0o077:
        raise PolicyRefused("manifest_permissions_unsafe")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PolicyRefused(f"manifest_unreadable ({exc.__class__.__name__})") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != IDENTITY_MANIFEST_SCHEMA:
        raise PolicyRefused("manifest_schema_unknown")
    if manifest.get("plan_commit") != PLAN_COMMIT:
        raise PolicyRefused("manifest_plan_commit_mismatch")
    if manifest.get("master_sha") != MASTER_SHA:
        raise PolicyRefused("manifest_master_sha_mismatch")
    if not manifest.get("operator_confirmed"):
        raise PolicyRefused("manifest_not_operator_confirmed")
    if now - float(manifest.get("recorded_at", 0)) > MANIFEST_MAX_AGE_SECONDS:
        raise PolicyRefused("manifest_stale_requalify_required")
    seats = manifest.get("seats")
    if not isinstance(seats, dict) or set(seats) != set(TUNNEL_LABELS):
        raise PolicyRefused("manifest_seat_set_mismatch")
    return manifest


def assert_current_bytes_match_manifest(home: Path, manifest: Mapping[str, Any], label: str) -> dict[str, Any]:
    """CAS guard: the live plist must still be byte-identical to the qualified
    preimage, otherwise the seat drifted after qualification and install must
    refuse (re-qualify first). Returns the parsed live dict."""
    entry = manifest["seats"][label]
    home = Path(home)
    plist_path = home / entry["plist_relpath"]
    raw = plist_path.read_bytes()
    if sha256_bytes(raw) != entry["plist_sha256"]:
        raise PolicyRefused(f"{label}_drift_since_qualification")
    return parse_plist_bytes(raw, code=f"{label}_post_qualify_read")


def manifest_public_evidence(manifest: Mapping[str, Any]) -> list[str]:
    """Secret-safe, per-seat evidence lines for stdout (no argv body, no env)."""
    lines = [
        evidence_line(
            "manifest",
            {
                "schema": manifest.get("schema"),
                "plan_commit": manifest.get("plan_commit"),
                "recorded_at": manifest.get("recorded_at"),
                "seats": len(manifest.get("seats", {})),
            },
        )
    ]
    for label in sorted(manifest.get("seats", {})):
        entry = manifest["seats"][label]
        lines.append(
            evidence_line(
                label,
                {
                    "plist_sha256": entry["plist_sha256"][:16],
                    "argv_len": len(entry["program_arguments"]),
                    "executable": entry["executable"],
                    "executable_sha256": entry["executable_sha256"][:16],
                    "heartbeat_path": entry.get("heartbeat_path", "<unset>"),
                },
            )
        )
    return lines


def unqualified_health_alerts(home: Path, manifest: Mapping[str, Any]) -> list[Alert]:
    """Health-readiness warnings derived from manifest completeness.

    Missing optional host facts never block an install, but the health loop
    must not pretend to classify what was never qualified: each absent field
    becomes a distinct alert and no recovery is planned for seats whose
    heartbeat path is unqualified.
    """
    alerts: list[Alert] = []
    for label in sorted(TUNNEL_LABELS):
        entry = manifest["seats"][label]
        if not entry.get("heartbeat_path"):
            alerts.append(Alert("heartbeat_path_unqualified", label))
    host = manifest
    if not host.get("native_store_path"):
        alerts.append(Alert("native_store_path_unqualified", "host"))
    if not host.get("host_pull_telemetry_dir"):
        alerts.append(Alert("host_pull_telemetry_unqualified", "host"))
    if not host.get("pinned_generation"):
        alerts.append(Alert("pinned_generation_unqualified", "host"))
    repair = host.get("repair")
    if not isinstance(repair, dict) or not repair.get("files"):
        alerts.append(Alert("stdin_argmax_repair_unqualified", "host"))
    del home
    return alerts
