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

The single operator-facing qualification entrypoint is :func:`qualify_install`
(dry-run capable, closed facts schema, private 0600 manifest). After the
manifest's one-day attestation bound passes, :func:`revalidate_stale_identity`
lets a READ-ONLY health pass continue by re-proving each seat's installed
identity, program digest/argv, and qualified heartbeat from live host state —
mutation paths keep requiring a fresh manifest.

Shared-executable identity repair (2026-10-31): the five real seats
legitimately share ONE user-owned binary under the canonical Homebrew Cellar
prefix (user-owned mode 0775). A shared binary is therefore legal exactly
when every sharing seat proves itself through a private poll profile — its
installed argv names the profile with exactly one absolute ``--profile-file``
option equal to the operator fact, the profile and its derived locator are
unique per seat by path/inode/digest (never hardlinks), and the profile's
``control_plane.tunnel_id`` is present, well-formed, and unique, pinned ONLY
as a domain-separated digest. The executable, its parent directory, and the
single narrowly anchored Cellar allowance directory are pinned by
``(dev, ino, uid, mode)`` from nofollow descriptor observations, and
:func:`seat_identity_drift_problems` re-proves them before EVERY kickstart
and install effect — never merely after the attestation day boundary. The
residual group-member rename/exec TOCTOU inside the group-writable Cellar is
documented in RUNBOOK.md and is reduced, not eliminated.
"""
from __future__ import annotations

import json
import os
import posixpath
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from fabric_tunnel_common import (
    CLI_POLL_MAX_PROFILE_BYTES,
    CLI_POLL_TIMEOUT_SECONDS,
    HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL,
    HEARTBEAT_MODE_FILE_MTIME,
    IDENTITY_MANIFEST_SCHEMA,
    KEEP_ALIVE,
    MANIFEST_MAX_AGE_SECONDS,
    MASTER_SHA,
    MAX_TELEMETRY_FILES,
    MAX_TUNNEL_RELATIVE_PATH,
    PLAN_COMMIT,
    RUN_AT_LOAD,
    TELEMETRY_FILE_SUFFIXES,
    THROTTLE_INTERVAL_MIN,
    TUNNEL_HEARTBEAT_MODES,
    TUNNEL_LABELS,
    TUNNEL_LABEL_PREFIX,
    OWNED_LABELS,
    WATCHDOG_LABEL,
    Alert,
    ActionRefused,
    IdentityRejected,
    PolicyRefused,
    backups_dir,
    build_control_plane_poll_argv,
    control_plane_poll_runner,
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
    validate_control_plane_poll_payload,
    verified_dir_identity,
    verified_file_identity,
    require_executable_parent_safe,
)

# argv[0] must be absolute; launchd requires it for user agents and it is the
# anchor of every executable identity check below.
_ARGV_MAX = 64

# Heartbeat and host-fact fields recorded per seat / per host at
# qualification. They are OPTIONAL: absence is an unqualified-health alert,
# never a guessed default path.
#
# ``heartbeat_kind`` / ``heartbeat_proof_note`` are the B6 first-party
# attestation: without an operator-declared kind plus a proof note, a
# heartbeat file's mtime is NOT treated as the tunnel-client/control-plane
# last-seen signal, and a stale heartbeat is alert-only (no forced restart).
#
# ``heartbeat_mode`` selects the strictly typed evidence source:
# ``file_mtime_attested`` (the legacy file-mtime mode, also the meaning of an
# ABSENT mode on a safe legacy manifest) requires ``heartbeat_path``;
# ``first_party_cli_control_plane_poll`` requires ``heartbeat_profile_file``
# and derives ``heartbeat_url_locator`` (the profile's ``health.url_file``)
# at qualification. The locator is DERIVED, never an accepted operator fact,
# so a manifest cannot be steered to an unvetted URL file through facts.
_SEAT_OPTIONAL_FIELDS = (
    "heartbeat_path",
    "heartbeat_kind",
    "heartbeat_proof_note",
    "heartbeat_mode",
    "heartbeat_profile_file",
    "heartbeat_url_locator",
)
_HOST_OPTIONAL_FIELDS = (
    "native_store_path",
    "host_pull_telemetry_dir",
    "host_pull_telemetry_files",
    "pinned_generation",
    "stale_telemetry_seconds",
    "repair",
)

# Closed operator facts schema accepted by ``qualify_install`` (B4). Anything
# not listed here is refused, never guessed. ``heartbeat_url_locator`` is
# deliberately NOT a fact: it is derived from the qualified profile.
_SEAT_FACT_FIELDS = (
    "heartbeat_path",
    "heartbeat_kind",
    "heartbeat_proof_note",
    "heartbeat_mode",
    "heartbeat_profile_file",
)
_HOST_FACT_FIELDS = (
    "native_store_path",
    "host_pull_telemetry_dir",
    "host_pull_telemetry_files",
    "pinned_generation",
    "stale_telemetry_seconds",
    "repair",
)
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
# Clock-skew tolerance for a recorded_at that lands slightly in the future.
_RECORDED_AT_FUTURE_TOLERANCE_SECONDS = 300

# ---------------------------------------------------------------------------
# Per-seat tunnel-id binding (identity repair, 2026-10-31).
#
# When several seats legitimately share ONE verified executable binary, the
# per-seat identity invariant moves from the executable to the seat's private
# profile and its operator-qualified control-plane tunnel id. The raw id is
# NEVER stored, logged, or printed: only a DOMAIN-SEPARATED SHA-256 digest is
# pinned, so the manifest cannot leak or be replayed as the id itself, and
# digest uniqueness across seats proves the ids are distinct without knowing
# them. The shape rule is deliberately conservative: a printable, bounded,
# URL-shaped id (any ``/``, and therefore any ``scheme://...``) refuses, so a
# credential-looking value can never be smuggled through as a tunnel id.
# ---------------------------------------------------------------------------
_TUNNEL_ID_HASH_DOMAIN = b"mastermind.subagent-fabric-tunnels.control-plane.tunnel-id.v1\x00"
_TUNNEL_ID_MAX_LENGTH = 128
_TUNNEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,%d}$" % (_TUNNEL_ID_MAX_LENGTH - 1))


def tunnel_id_binding_hash(tunnel_id: str) -> str:
    """Domain-separated SHA-256 of one control-plane tunnel id.

    The raw id never enters the manifest, evidence, or logs; only this
    digest does. Domain separation prevents digest-reuse confusion with any
    other hash this integration computes."""
    return sha256_bytes(_TUNNEL_ID_HASH_DOMAIN + tunnel_id.encode("utf-8"))


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
    # Pinned executable identity from ONE nofollow descriptor observation
    # (dev/ino/owner/mode), the executable's immediate parent directory
    # identity, and the Homebrew Cellar allowance directory when the
    # executable-only ancestor exception consumed it. Zero defaults mean
    # "not observed" and keep direct constructions of this dataclass valid.
    executable_dev: int = 0
    executable_ino: int = 0
    executable_owner_uid: int = 0
    executable_mode: int = 0
    executable_parent_dev: int = 0
    executable_parent_ino: int = 0
    executable_parent_uid: int = 0
    executable_parent_mode: int = 0
    cellar_ancestor: str | None = None
    cellar_dev: int = 0
    cellar_ino: int = 0
    cellar_uid: int = 0
    cellar_mode: int = 0

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
    # Executable-ONLY ancestor walk: strict everywhere except the single
    # narrowly anchored canonical Homebrew Cellar allowance (see
    # fabric_tunnel_common.require_executable_parent_safe). Every other path
    # kind in this integration keeps the strict require_parent_safe walk.
    parent_verdict = require_executable_parent_safe(
        exec_path, uid, code=f"{label}_executable_parent_unsafe"
    )
    try:
        exec_mode = exec_path.stat().st_mode
    except OSError as exc:
        raise IdentityRejected(f"{label}_executable_unavailable ({exc.strerror})") from exc
    if exec_mode & 0o022:
        raise IdentityRejected(f"{label}_executable_group_world_writable")
    try:
        exec_path.read_bytes()
    except OSError as exc:
        raise IdentityRejected(f"{label}_executable_unreadable ({exc.strerror})") from exc
    # Pin the executable from ONE nofollow descriptor observation so an
    # in-place replacement between the checks above and the digest cannot
    # split the recorded identity: dev/ino/owner/mode and the digest all
    # describe the SAME inode read through the SAME descriptor.
    exec_identity = verified_file_identity(exec_path, uid, code=f"{label}_executable_pin")
    parent_identity = verified_dir_identity(
        exec_path.parent, uid, code=f"{label}_executable_parent_pin"
    )
    cellar_identity = None
    if parent_verdict.cellar_ancestor is not None:
        cellar_identity = verified_dir_identity(
            Path(parent_verdict.cellar_ancestor),
            uid,
            code=f"{label}_cellar_ancestor_pin",
            require_owner_uid=True,
        )
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
        executable_sha256=exec_identity.sha256,
        uid=uid,
        executable_dev=exec_identity.dev,
        executable_ino=exec_identity.ino,
        executable_owner_uid=exec_identity.uid,
        executable_mode=exec_identity.mode,
        executable_parent_dev=parent_identity.dev,
        executable_parent_ino=parent_identity.ino,
        executable_parent_uid=parent_identity.uid,
        executable_parent_mode=parent_identity.mode,
        cellar_ancestor=parent_verdict.cellar_ancestor,
        cellar_dev=cellar_identity.dev if cellar_identity is not None else 0,
        cellar_ino=cellar_identity.ino if cellar_identity is not None else 0,
        cellar_uid=cellar_identity.uid if cellar_identity is not None else 0,
        cellar_mode=cellar_identity.mode if cellar_identity is not None else 0,
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
        # Pinned executable + parent + Cellar-allowance identity (dev/ino
        # tripwires, owner, mode): re-proven against the LIVE filesystem
        # before every kickstart and install effect, not merely after the
        # attestation day boundary.
        entry["executable_dev"] = int(identity.executable_dev)
        entry["executable_ino"] = int(identity.executable_ino)
        entry["executable_owner_uid"] = int(identity.executable_owner_uid)
        entry["executable_mode"] = int(identity.executable_mode)
        entry["executable_parent_dev"] = int(identity.executable_parent_dev)
        entry["executable_parent_ino"] = int(identity.executable_parent_ino)
        entry["executable_parent_uid"] = int(identity.executable_parent_uid)
        entry["executable_parent_mode"] = int(identity.executable_parent_mode)
        if identity.cellar_ancestor is not None:
            entry["cellar_ancestor"] = {
                "path": identity.cellar_ancestor,
                "dev": int(identity.cellar_dev),
                "ino": int(identity.cellar_ino),
                "uid": int(identity.cellar_uid),
                "mode": int(identity.cellar_mode),
            }
        profile_binding = (seat_options or {}).get(identity.label, {}).get("poll_profile")
        if isinstance(profile_binding, dict):
            # Private per-seat poll-profile binding (path/dev/ino/uid/mode/
            # digest + derived locator identity + domain-separated tunnel-id
            # digest). The raw tunnel id and the profile JSON are never
            # recorded, logged, or printed anywhere.
            entry["poll_profile"] = dict(profile_binding)
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


def load_manifest(
    home: Path,
    *,
    now: float,
    allow_stale_revalidation: bool = False,
) -> dict[str, Any]:
    """Load and structurally verify the private qualification manifest.

    Install-time freshness is preserved by default: a manifest older than
    ``MANIFEST_MAX_AGE_SECONDS`` is refused for every MUTATION path
    (install / rollback / verify / watchdog install). Read-only health passes
    may pass ``allow_stale_revalidation=True`` — the day boundary then no
    longer disables recovery outright, but the caller MUST pair it with
    :func:`revalidate_stale_identity` so trust is re-derived from live host
    state every pass instead of from the aging attestation. The manifest is
    still never trusted blindly at any age.
    """
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
    try:
        recorded_at = float(manifest.get("recorded_at", 0))
    except (TypeError, ValueError) as exc:
        raise PolicyRefused("manifest_recorded_at_invalid") from exc
    if recorded_at - now > _RECORDED_AT_FUTURE_TOLERANCE_SECONDS:
        raise PolicyRefused("manifest_recorded_at_in_future")
    if now - recorded_at > MANIFEST_MAX_AGE_SECONDS and not allow_stale_revalidation:
        raise PolicyRefused("manifest_stale_requalify_required")
    seats = manifest.get("seats")
    if not isinstance(seats, dict) or set(seats) != set(TUNNEL_LABELS):
        raise PolicyRefused("manifest_seat_set_mismatch")
    return manifest


def manifest_is_stale(manifest: Mapping[str, Any], now: float) -> bool:
    """True when the operator attestation has passed the install-time bound.

    Staleness never blocks a revalidating health pass by itself; it only
    switches the pass onto live revalidation and keeps a persistent
    ``manifest_stale_revalidated`` alert raised so the operator requalifies.
    """
    try:
        recorded_at = float(manifest.get("recorded_at", 0))
    except (TypeError, ValueError):
        return True
    return (now - recorded_at) > MANIFEST_MAX_AGE_SECONDS


def seat_identity_drift_problems(
    home: Path,
    manifest: Mapping[str, Any],
    label: str,
) -> list[str]:
    """Strict live-vs-pinned per-seat identity re-proof.

    This is the engine used before EVERY kickstart and install effect (and
    for stale-manifest passes) — not merely after the attestation day
    boundary. It re-proves, from the LIVE filesystem against the qualified
    manifest: whole argv, executable path and digest, the pinned executable
    ``dev/ino/owner/mode``, the pinned parent-directory identity, the pinned
    Homebrew Cellar-allowance identity, and — for seats with a pinned
    poll-profile binding — the full profile/locator/tunnel-id binding (path,
    inode, owner, mode, digest, derived locator, locator identity,
    domain-separated tunnel-id digest). An in-place replacement or any parent
    drift between attestation and effect refuses here.

    Deliberately NOT here: the installed plist bytes against the qualified
    preimage. A SUCCESSFUL install legitimately extends the plist with the
    policy trio, so post-install plists differ from the qualified preimage by
    design; that CAS belongs to the install preflight
    (:func:`assert_current_bytes_match_manifest`) and to rollback's
    backup-post digest CAS, which compare against the correct reference for
    their own effect. This engine proves the identity that must survive the
    install unchanged: the whole argv, the executable, and the pinned
    filesystem identity around them.

    Legacy manifest entries without the new pins skip exactly those pinned
    comparisons (backward compatible) and keep the historical lstat shape
    checks: a MISSING profile/locator/heartbeat file stays a normal health
    state, while a path that now exists as a symlink or special file is a
    qualification break.

    Returns stable problem codes only — never argv bodies, profile JSON, or
    raw tunnel ids. An empty list means the seat's identity is proven
    current."""
    entry = manifest["seats"][label]
    uid = int(entry["uid"])
    try:
        identity = verify_seat(home, label, uid)
    except IdentityRejected as rejected:
        return [f"identity_rejected:{rejected}"]
    problems: list[str] = []
    if list(identity.program_arguments) != list(entry.get("program_arguments", [])):
        problems.append("argv_changed")
    if identity.executable != entry.get("executable"):
        problems.append("executable_path_changed")
    if identity.executable_sha256 != entry.get("executable_sha256"):
        problems.append("executable_digest_changed")
    if entry.get("executable_ino") is not None and (
        identity.executable_dev,
        identity.executable_ino,
    ) != (int(entry.get("executable_dev") or 0), int(entry["executable_ino"])):
        problems.append("executable_inode_changed")
    if entry.get("executable_owner_uid") is not None and (
        identity.executable_owner_uid != int(entry["executable_owner_uid"])
    ):
        problems.append("executable_owner_changed")
    if entry.get("executable_mode") is not None and (
        identity.executable_mode != int(entry["executable_mode"])
    ):
        problems.append("executable_mode_changed")
    if entry.get("executable_parent_ino") is not None and (
        identity.executable_parent_dev,
        identity.executable_parent_ino,
    ) != (
        int(entry.get("executable_parent_dev") or 0),
        int(entry["executable_parent_ino"]),
    ):
        problems.append("executable_parent_inode_changed")
    if entry.get("executable_parent_uid") is not None and (
        identity.executable_parent_uid != int(entry["executable_parent_uid"])
    ):
        problems.append("executable_parent_owner_changed")
    if entry.get("executable_parent_mode") is not None and (
        identity.executable_parent_mode != int(entry["executable_parent_mode"])
    ):
        problems.append("executable_parent_mode_changed")
    pinned_cellar = entry.get("cellar_ancestor")
    if isinstance(pinned_cellar, dict):
        if identity.cellar_ancestor != pinned_cellar.get("path"):
            problems.append("cellar_ancestor_changed")
        elif (
            identity.cellar_dev,
            identity.cellar_ino,
            identity.cellar_uid,
            identity.cellar_mode,
        ) != (
            int(pinned_cellar.get("dev") or 0),
            int(pinned_cellar.get("ino") or 0),
            int(pinned_cellar.get("uid") or 0),
            int(pinned_cellar.get("mode") or 0),
        ):
            problems.append("cellar_ancestor_identity_changed")
    elif pinned_cellar is None and identity.cellar_ancestor is not None:
        # The manifest predates the Cellar allowance: an allowance ancestor
        # present NOW was not the qualified shape and was never pinned.
        problems.append("cellar_ancestor_unpinned")
    heartbeat_path = entry.get("heartbeat_path")
    if heartbeat_path:
        # A MISSING heartbeat file is a normal health state (per-pass
        # classification raises heartbeat_missing, alert-only), but a path
        # that now exists as a symlink or special file is a qualification
        # break.
        try:
            st = Path(heartbeat_path).lstat()
        except OSError:
            st = None
        if st is not None and (stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode)):
            problems.append("heartbeat_path_not_regular")
    profile_fact = entry.get("heartbeat_profile_file")
    if entry.get("heartbeat_mode") == HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL and profile_fact:
        pinned_profile = entry.get("poll_profile")
        if isinstance(pinned_profile, dict):
            # Full binding re-proof for pinned seats: the profile must still
            # be the pinned inode with the pinned digest, still derive the
            # pinned locator with its pinned identity, and still hash to the
            # pinned tunnel id. A vanished, swapped, rewritten, re-linked
            # (hardlinked), or re-tunnelled profile refuses here.
            required_tunnel = bool(pinned_profile.get("tunnel_id_hash"))
            try:
                binding = verified_poll_profile_binding(
                    label,
                    str(profile_fact),
                    uid,
                    require_tunnel_id=required_tunnel,
                )
            except (PolicyRefused, IdentityRejected) as rejected:
                problems.append(f"poll_profile_binding_refused:{rejected}")
            else:
                if binding.profile_path != pinned_profile.get("path"):
                    problems.append("poll_profile_path_changed")
                if (binding.profile_dev, binding.profile_ino) != (
                    int(pinned_profile.get("dev") or 0),
                    int(pinned_profile.get("ino") or 0),
                ):
                    problems.append("poll_profile_inode_changed")
                if binding.profile_uid != int(pinned_profile.get("uid") or 0):
                    problems.append("poll_profile_owner_changed")
                if binding.profile_mode != int(pinned_profile.get("mode") or 0):
                    problems.append("poll_profile_mode_changed")
                if binding.profile_sha256 != pinned_profile.get("sha256"):
                    problems.append("poll_profile_digest_changed")
                if binding.locator != entry.get("heartbeat_url_locator"):
                    problems.append("poll_locator_changed")
                if (binding.locator_dev, binding.locator_ino) != (
                    int(pinned_profile.get("locator_dev") or 0),
                    int(pinned_profile.get("locator_ino") or 0),
                ):
                    problems.append("poll_locator_inode_changed")
                if binding.locator_sha256 != pinned_profile.get("locator_sha256"):
                    problems.append("poll_locator_digest_changed")
                if required_tunnel and (
                    binding.tunnel_id_hash != pinned_profile.get("tunnel_id_hash")
                ):
                    problems.append("poll_tunnel_id_changed")
        else:
            # Legacy unpinned CLI seat: a MISSING profile/locator is a normal
            # health state (the per-pass classification refuses the evidence,
            # alert-only), but a path that now exists as a symlink or special
            # file is a qualification break.
            for field_name, problem in (
                ("heartbeat_profile_file", "heartbeat_profile_not_regular"),
                ("heartbeat_url_locator", "heartbeat_locator_not_regular"),
            ):
                recorded = entry.get(field_name)
                if not recorded:
                    continue
                try:
                    st = Path(recorded).lstat()
                except OSError:
                    st = None
                if st is not None and (stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode)):
                    problems.append(problem)
    return problems


def revalidate_stale_identity(
    home: Path,
    manifest: Mapping[str, Any],
) -> tuple[list[Alert], frozenset[str]]:
    """Live per-seat revalidation used after the attestation day boundary.

    Deterministic, host-derived, and never a renewal of the stale manifest:
    every check of :func:`seat_identity_drift_problems` runs per seat against
    the pinned manifest values from the LIVE filesystem. A seat whose live
    identity no longer matches is returned in ``suspect_labels`` and must
    receive ALERT ONLY recovery treatment (no kickstart) until a human
    requalifies. Detail strings carry stable reason codes only — never argv
    bodies, profile JSON, or raw tunnel ids.
    """
    home = Path(home)
    alerts: list[Alert] = []
    suspects: set[str] = set()
    prefix = "identity_rejected:"
    for label in sorted(TUNNEL_LABELS):
        problems = seat_identity_drift_problems(home, manifest, label)
        rejected = [p for p in problems if p.startswith(prefix)]
        if rejected:
            alerts.append(Alert("seat_identity_rejected", label, rejected[0][len(prefix):]))
            suspects.add(label)
            continue
        if problems:
            alerts.append(Alert("seat_identity_tampered_alert_only", label, ",".join(problems)))
            suspects.add(label)
    return alerts, frozenset(suspects)


def telemetry_relative_path_reject_reason(rel: str) -> str | None:
    """Closed-shape validation for a qualified telemetry relative path.

    Deterministic and shared by qualification (refuses) and health reads
    (rejects the whole reading): relative POSIX path, no empty/`.`/`..`
    components, bounded length, and a qualified suffix.
    """
    if not isinstance(rel, str) or not rel or len(rel) > MAX_TUNNEL_RELATIVE_PATH:
        return "shape"
    if rel.startswith("/") or "\\" in rel:
        return "not_relative_posix"
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return "traversal"
    if Path(rel).suffix not in TELEMETRY_FILE_SUFFIXES:
        return "suffix"
    return None


def _relative_path_reject_reason(rel: Any) -> str | None:
    """Relative-path shape check for qualified facts (no suffix constraint)."""
    if not isinstance(rel, str) or not rel or len(rel) > MAX_TUNNEL_RELATIVE_PATH:
        return "shape"
    if rel.startswith("/") or "\\" in rel:
        return "not_relative_posix"
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return "traversal"
    return None


def _resolved_inside_root(root: Path, candidate: Path) -> bool:
    try:
        resolved = candidate.resolve()
        root_resolved = root.resolve()
    except OSError:
        return False
    return resolved != root_resolved and root_resolved in resolved.parents


def _validated_facts(
    facts: Mapping[str, Any] | None,
) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    """Validate the operator facts mapping for :func:`qualify_install`.

    The schema is CLOSED: unknown fields, unknown seats, non-absolute paths,
    missing/symlinked/special files, malformed digests, and unbounded file
    sets are refused with stable codes. Nothing is invented: every recorded
    fact was explicitly supplied by the operator for this host.
    """
    if facts is None:
        return {}, {}
    if not isinstance(facts, Mapping):
        raise PolicyRefused("facts_shape_invalid")
    unknown_top = sorted(set(facts) - {"seats", "host"})
    if unknown_top:
        raise PolicyRefused(f"facts_unknown_field: {','.join(unknown_top)}")
    raw_seats = facts.get("seats") or {}
    raw_host = facts.get("host") or {}
    if not isinstance(raw_seats, dict) or not isinstance(raw_host, dict):
        raise PolicyRefused("facts_shape_invalid")

    seat_options: dict[str, dict[str, str]] = {}
    for key, entry in raw_seats.items():
        if key not in TUNNEL_LABELS:
            raise PolicyRefused(f"facts_unknown_seat: {key}")
        if not isinstance(entry, dict):
            raise PolicyRefused(f"facts_seat_shape_invalid: {key}")
        unknown = sorted(set(entry) - set(_SEAT_FACT_FIELDS))
        if unknown:
            raise PolicyRefused(f"facts_unknown_seat_field: {key}:{','.join(unknown)}")
        validated: dict[str, str] = {}
        heartbeat = entry.get("heartbeat_path")
        kind = entry.get("heartbeat_kind")
        note = entry.get("heartbeat_proof_note")
        mode = entry.get("heartbeat_mode")
        profile = entry.get("heartbeat_profile_file")
        if mode is not None:
            # Strictly typed: an unknown mode spelling is refused, never
            # guessed into a behavior.
            if not isinstance(mode, str) or mode not in TUNNEL_HEARTBEAT_MODES:
                raise PolicyRefused(f"facts_heartbeat_mode_unknown: {key}")
            validated["heartbeat_mode"] = mode
        cli_mode = mode == HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL
        if profile is not None and not cli_mode:
            raise PolicyRefused(f"facts_heartbeat_profile_file_requires_cli_poll_mode: {key}")
        if cli_mode:
            # Modes are exclusive: the CLI poll mode never takes a heartbeat
            # FILE path, and its profile locator is DERIVED at qualification,
            # never accepted as an operator fact.
            if heartbeat is not None:
                raise PolicyRefused(f"facts_heartbeat_path_only_for_file_mtime_mode: {key}")
            if (
                not isinstance(profile, str)
                or not profile.startswith("/")
                or len(profile) > MAX_TUNNEL_RELATIVE_PATH
            ):
                raise PolicyRefused(f"facts_heartbeat_profile_file_not_absolute: {key}")
            # The B6 first-party attestation (kind + proof note) is required
            # for the CLI poll mode exactly as for the file mode.
            if not isinstance(kind, str) or not kind.strip():
                raise PolicyRefused(f"facts_heartbeat_kind_required: {key}")
            if not isinstance(note, str) or not note.strip():
                raise PolicyRefused(f"facts_heartbeat_proof_note_required: {key}")
            validated["heartbeat_profile_file"] = profile
            validated["heartbeat_kind"] = kind.strip()
            validated["heartbeat_proof_note"] = note.strip()
        elif mode == HEARTBEAT_MODE_FILE_MTIME and heartbeat is None:
            raise PolicyRefused(f"facts_heartbeat_path_required_for_file_mtime_mode: {key}")
        if heartbeat is not None:
            if not isinstance(heartbeat, str) or not heartbeat.startswith("/"):
                raise PolicyRefused(f"facts_heartbeat_path_not_absolute: {key}")
            if not isinstance(kind, str) or not kind.strip():
                raise PolicyRefused(f"facts_heartbeat_kind_required: {key}")
            if not isinstance(note, str) or not note.strip():
                raise PolicyRefused(f"facts_heartbeat_proof_note_required: {key}")
            path = Path(heartbeat)
            try:
                st = path.lstat()
            except OSError as exc:
                raise PolicyRefused(f"facts_heartbeat_path_unavailable: {key}") from exc
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                raise PolicyRefused(f"facts_heartbeat_path_not_regular: {key}")
            validated["heartbeat_path"] = heartbeat
            validated["heartbeat_kind"] = kind.strip()
            validated["heartbeat_proof_note"] = note.strip()
        elif not cli_mode and (kind is not None or note is not None):
            # Legacy shape: kind/note without a heartbeat path. (The CLI-poll
            # mode requires kind+note itself, above.)
            raise PolicyRefused(f"facts_heartbeat_path_required_with_kind: {key}")
        if validated:
            seat_options[key] = validated

    host_options: dict[str, Any] = {}
    unknown_host = sorted(set(raw_host) - set(_HOST_FACT_FIELDS))
    if unknown_host:
        raise PolicyRefused(f"facts_unknown_host_field: {','.join(unknown_host)}")
    store = raw_host.get("native_store_path")
    if store is not None:
        if not isinstance(store, str) or not store.startswith("/") or not Path(store).is_dir():
            raise PolicyRefused("facts_native_store_path_unavailable")
        host_options["native_store_path"] = store
    telemetry_dir = raw_host.get("host_pull_telemetry_dir")
    telemetry_files = raw_host.get("host_pull_telemetry_files")
    if telemetry_dir is not None or telemetry_files is not None:
        if not isinstance(telemetry_dir, str) or not telemetry_dir.startswith("/") or not Path(telemetry_dir).is_dir():
            raise PolicyRefused("facts_telemetry_dir_unavailable")
        if (
            not isinstance(telemetry_files, list)
            or not telemetry_files
            or not all(isinstance(item, str) for item in telemetry_files)
        ):
            raise PolicyRefused("facts_telemetry_files_required")
        if len(telemetry_files) > MAX_TELEMETRY_FILES:
            raise PolicyRefused("facts_telemetry_files_too_many")
        seen: set[str] = set()
        root = Path(telemetry_dir)
        for rel in telemetry_files:
            reason = telemetry_relative_path_reject_reason(rel)
            if reason:
                raise PolicyRefused(f"facts_telemetry_file_invalid: {reason}")
            if rel in seen:
                raise PolicyRefused(f"facts_telemetry_file_duplicated: {rel}")
            seen.add(rel)
            candidate = root / rel
            try:
                st = candidate.lstat()
            except OSError as exc:
                raise PolicyRefused(f"facts_telemetry_file_missing: {rel}") from exc
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                raise PolicyRefused(f"facts_telemetry_file_not_regular: {rel}")
            if not _resolved_inside_root(root, candidate):
                raise PolicyRefused(f"facts_telemetry_file_escapes_root: {rel}")
        host_options["host_pull_telemetry_dir"] = telemetry_dir
        host_options["host_pull_telemetry_files"] = list(telemetry_files)
    pinned = raw_host.get("pinned_generation")
    if pinned is not None:
        if not isinstance(pinned, str) or not _HEX64_RE.match(pinned):
            raise PolicyRefused("facts_pinned_generation_invalid")
        host_options["pinned_generation"] = pinned
    stale_seconds = raw_host.get("stale_telemetry_seconds")
    if stale_seconds is not None:
        if (
            isinstance(stale_seconds, bool)
            or not isinstance(stale_seconds, int)
            or not (60 <= stale_seconds <= 7 * 86400)
        ):
            raise PolicyRefused("facts_stale_telemetry_seconds_invalid")
        host_options["stale_telemetry_seconds"] = stale_seconds
    repair = raw_host.get("repair")
    if repair is not None:
        if not isinstance(repair, dict):
            raise PolicyRefused("facts_repair_shape_invalid")
        unknown_repair = sorted(set(repair) - {"files", "source_commit"})
        if unknown_repair:
            raise PolicyRefused(f"facts_repair_unknown_field: {','.join(unknown_repair)}")
        files = repair.get("files")
        if not isinstance(files, dict) or not files:
            raise PolicyRefused("facts_repair_files_required")
        if len(files) > MAX_TELEMETRY_FILES:
            raise PolicyRefused("facts_repair_files_too_many")
        for rel, digest in files.items():
            reason = _relative_path_reject_reason(rel)
            if reason:
                raise PolicyRefused(f"facts_repair_file_invalid: {reason}")
            if not isinstance(digest, str) or not _HEX64_RE.match(digest):
                raise PolicyRefused(f"facts_repair_digest_invalid: {rel}")
        source_commit = repair.get("source_commit")
        if source_commit is not None and (not isinstance(source_commit, str) or len(source_commit) > 64):
            raise PolicyRefused("facts_repair_source_commit_invalid")
        host_options["repair"] = {
            "files": dict(files),
            **({"source_commit": source_commit} if source_commit else {}),
        }
    return seat_options, host_options


_PROFILE_FILE_FLAG = "--profile-file"


def installed_argv_profile_file(label: str, program_arguments: Any) -> str | None:
    """Extract the EXACTLY ONE absolute ``--profile-file`` value from the
    INSTALLED plist argv (never from operator facts).

    Accepts both the ``--profile-file <value>`` and ``--profile-file=<value>``
    spellings. Returns ``None`` when the flag is absent (a legacy seat whose
    executable is its own identity). Refuses, with stable codes: a duplicated
    flag in either spelling, a flag with no value, and a value that is not an
    absolute path. The value text is never echoed into the refusal."""
    items = list(program_arguments)
    value: str | None = None
    index = 1  # argv[0] is the executable itself
    while index < len(items):
        item = items[index]
        if item == _PROFILE_FILE_FLAG:
            if value is not None:
                raise IdentityRejected(f"{label}_profile_file_flag_duplicated")
            if index + 1 >= len(items):
                raise IdentityRejected(f"{label}_profile_file_flag_missing_value")
            value = items[index + 1]
            index += 2
            continue
        if item.startswith(_PROFILE_FILE_FLAG + "="):
            if value is not None:
                raise IdentityRejected(f"{label}_profile_file_flag_duplicated")
            value = item[len(_PROFILE_FILE_FLAG) + 1:]
            index += 1
            continue
        index += 1
    if value is not None and not (value.startswith("/") and len(value) > 1):
        raise IdentityRejected(f"{label}_profile_file_flag_not_absolute")
    return value


@dataclass(frozen=True)
class PollProfileBinding:
    """Verified per-seat poll-profile binding, pinned from ONE nofollow
    descriptor observation per file.

    This is the identity invariant that replaces the old blanket rejection of
    shared executables: when seats share one binary, each seat is proven
    distinct through its own private profile — distinct path, distinct
    ``(dev, ino)`` inode, distinct content digest, a distinct derived URL
    locator, and a distinct domain-separated control-plane tunnel-id digest.
    The raw tunnel id and the profile JSON are never recorded."""

    profile_path: str
    locator: str
    profile_dev: int
    profile_ino: int
    profile_uid: int
    profile_mode: int
    profile_sha256: str
    locator_dev: int
    locator_ino: int
    locator_uid: int
    locator_mode: int
    locator_sha256: str
    tunnel_id_hash: str | None

    def manifest_fields(self) -> dict[str, Any]:
        """The exact private-manifest block for this binding."""
        return {
            "path": self.profile_path,
            "dev": int(self.profile_dev),
            "ino": int(self.profile_ino),
            "uid": int(self.profile_uid),
            "mode": int(self.profile_mode),
            "sha256": self.profile_sha256,
            "locator": self.locator,
            "locator_dev": int(self.locator_dev),
            "locator_ino": int(self.locator_ino),
            "locator_uid": int(self.locator_uid),
            "locator_mode": int(self.locator_mode),
            "locator_sha256": self.locator_sha256,
            "tunnel_id_hash": self.tunnel_id_hash,
        }


def _shared_executable_labels(list_of_identities: list[SeatIdentity]) -> frozenset[str]:
    """Labels whose ``(executable path, executable digest)`` pair is shared
    with at least one other seat — the group whose per-seat identity must be
    proven through private profile bindings instead of distinct binaries."""
    by_exec: dict[tuple[str, str], list[str]] = {}
    for identity in list_of_identities:
        by_exec.setdefault((identity.executable, identity.executable_sha256), []).append(identity.label)
    return frozenset(
        label for labels in by_exec.values() if len(labels) > 1 for label in labels
    )


def _require_shared_executables_fully_bound(
    list_of_identities: list[SeatIdentity],
    bindings: Mapping[str, PollProfileBinding],
) -> None:
    """Qualification-time shared-executable rule.

    REPLACES the old blanket rejection of any two seats sharing an executable
    path+digest. The real five seats legitimately share ONE installed
    tunnel-client binary, so sharing is legal exactly when every seat in the
    shared group carries the full verified profile binding derived in
    :func:`qualify_install` — a facts-declared ``--profile-file`` that the
    INSTALLED argv names, proven as a private 0600 regular file (never a
    hardlink) whose ``(dev, ino)`` inode, content digest, derived URL locator,
    and present, well-formed, group-unique ``control_plane.tunnel_id`` digest
    are distinct per seat. Distinct WHOLE argv tuples remain enforced by
    :func:`verify_all_seats`; distinct executables stay fully supported with
    no binding required."""
    shared_labels = _shared_executable_labels(list_of_identities)
    for label in sorted(shared_labels):
        binding = bindings.get(label)
        if binding is None:
            raise PolicyRefused(f"executable_shared_requires_profile_binding:{label}")
        if not binding.tunnel_id_hash:
            raise PolicyRefused(f"executable_shared_requires_tunnel_id:{label}")


def _require_bounded_safe_private_file(path: Path, uid: int, *, code: str) -> None:
    """Shared qualification/health guard for the qualified poll profile and
    its derived URL locator: regular non-symlink file, owned by the seat
    user, not group/world-writable, every lexical ancestor symlink-free and
    unwritable-by-others, and a bounded size (a growing file is not a config
    file this integration may parse). Structural IdentityRejected refusals
    surface as PolicyRefused so facts-level verification fails closed with
    the same stable codes either way."""
    try:
        require_regular_file(path, code=f"{code}_unavailable")
        require_owner_writable_safe(path, uid, code=f"{code}_owner_unsafe")
        require_parent_safe(path, uid, code=f"{code}_parent_unsafe")
        st = path.lstat()
    except IdentityRejected as rejected:
        raise PolicyRefused(str(rejected)) from rejected
    if st.st_size > CLI_POLL_MAX_PROFILE_BYTES:
        raise PolicyRefused(f"{code}_oversized")


def _reject_traversal_components(text: str, label: str, *, code: str) -> None:
    if any(part in ("", "..") for part in text.split("/")[1:]):
        raise PolicyRefused(f"{label}_{code}_traversal")


def verified_poll_profile_binding(
    label: str,
    profile_text: str,
    uid: int,
    *,
    require_tunnel_id: bool = False,
) -> PollProfileBinding:
    """Qualification-time proof of one seat's first-party CLI poll profile.

    Extends the locator derivation with the FULL per-seat binding that makes
    a shared executable legally provable: every step fails closed with a
    stable code and nothing but the typed binding is returned or recorded.

    - the profile path must not carry another seat's identity (cross-seat
      adoption guard, same rule as executables);
    - the profile must be a bounded, seat-owned, safely-moded regular file
      with a symlink-free lexical ancestor chain, never a HARDLINK (a second
      name for the same inode could be swapped or mutated out of band), and
      its ``(dev, ino, uid, mode, sha256)`` identity is pinned from ONE
      nofollow descriptor observation;
    - its parsed ``health.url_file`` must be an absolute bounded path without
      traversal components, free of foreign seat identity, itself a bounded,
      seat-owned, safely-moded, non-hardlinked regular file, and pinned the
      same way;
    - ``control_plane.tunnel_id`` must be a present, non-empty, bounded,
      URL-free string whenever ``require_tunnel_id`` is set (shared-executable
      seats), and is returned ONLY as its domain-separated digest. A
      profile that carries a malformed tunnel id refuses even when one was
      not required.

    NEVER invoked on a path from untrusted facts at health time: the health
    pass re-derives the binding from the pinned profile only to CHECK it
    still equals the pinned values."""
    foreign = executable_path_reject_reason(label, profile_text)
    if foreign:
        raise PolicyRefused(f"{label}_poll_profile_foreign_identity: {foreign}")
    _reject_traversal_components(profile_text, label, code="poll_profile")
    profile_path = Path(profile_text)
    _require_bounded_safe_private_file(profile_path, uid, code=f"{label}_poll_profile")
    try:
        profile_identity = verified_file_identity(
            profile_path,
            uid,
            code=f"{label}_poll_profile",
            max_bytes=CLI_POLL_MAX_PROFILE_BYTES,
            require_owner_uid=True,
            require_nlink_one=True,
        )
    except IdentityRejected as rejected:
        raise PolicyRefused(str(rejected)) from rejected
    try:
        doc = json.loads(profile_identity.data)
    except ValueError as exc:
        raise PolicyRefused(f"{label}_poll_profile_not_json") from exc
    if not isinstance(doc, dict):
        raise PolicyRefused(f"{label}_poll_profile_shape_invalid")
    tunnel_id_hash = _verified_tunnel_id_hash(label, doc, require=require_tunnel_id)
    health = doc.get("health")
    if not isinstance(health, dict):
        raise PolicyRefused(f"{label}_poll_profile_health_missing")
    locator = health.get("url_file")
    if not isinstance(locator, str) or not locator.startswith("/") or len(locator) > MAX_TUNNEL_RELATIVE_PATH:
        raise PolicyRefused(f"{label}_poll_locator_not_absolute")
    foreign = executable_path_reject_reason(label, locator)
    if foreign:
        raise PolicyRefused(f"{label}_poll_locator_foreign_identity: {foreign}")
    _reject_traversal_components(locator, label, code="poll_locator")
    locator_path = Path(locator)
    _require_bounded_safe_private_file(locator_path, uid, code=f"{label}_poll_locator")
    try:
        locator_identity = verified_file_identity(
            locator_path,
            uid,
            code=f"{label}_poll_locator",
            max_bytes=CLI_POLL_MAX_PROFILE_BYTES,
            require_owner_uid=True,
            require_nlink_one=True,
        )
    except IdentityRejected as rejected:
        raise PolicyRefused(str(rejected)) from rejected
    return PollProfileBinding(
        profile_path=str(profile_path),
        locator=locator,
        profile_dev=profile_identity.dev,
        profile_ino=profile_identity.ino,
        profile_uid=profile_identity.uid,
        profile_mode=profile_identity.mode,
        profile_sha256=profile_identity.sha256,
        locator_dev=locator_identity.dev,
        locator_ino=locator_identity.ino,
        locator_uid=locator_identity.uid,
        locator_mode=locator_identity.mode,
        locator_sha256=locator_identity.sha256,
        tunnel_id_hash=tunnel_id_hash,
    )


def _verified_tunnel_id_hash(label: str, profile_doc: Mapping[str, Any], *, require: bool) -> str | None:
    """Extract and digest ``control_plane.tunnel_id`` from a parsed profile.

    The raw id is never returned, stored, logged, or printed — only its
    domain-separated digest. Missing is refused only when ``require`` is set
    (shared-executable seats); a PRESENT but empty, oversized, URL-shaped, or
    otherwise malformed id always refuses."""
    control = profile_doc.get("control_plane")
    tunnel_id = control.get("tunnel_id") if isinstance(control, dict) else None
    if tunnel_id is None:
        if require:
            raise PolicyRefused(f"{label}_poll_tunnel_id_missing")
        return None
    if (
        isinstance(tunnel_id, bool)
        or not isinstance(tunnel_id, str)
        or not _TUNNEL_ID_RE.match(tunnel_id)
    ):
        raise PolicyRefused(f"{label}_poll_tunnel_id_malformed")
    return tunnel_id_binding_hash(tunnel_id)


def verified_poll_profile_locator(label: str, profile_text: str, uid: int) -> str:
    """Qualification/health-time DERIVED ``health.url_file`` locator path.

    Backward-compatible thin view of :func:`verified_poll_profile_binding`:
    same proofs, same stable refusal codes, locator-only return. Seats whose
    manifest pins the full binding are re-proved through the binding itself;
    the tunnel id is validated (a malformed PRESENT id refuses) but not
    required for legacy entries."""
    return verified_poll_profile_binding(
        label, profile_text, uid, require_tunnel_id=False
    ).locator


def qualify_install(
    home: Path,
    *,
    uid: int,
    facts: Mapping[str, Any] | None,
    operator_confirmed: bool,
    now: float,
    dry_run: bool = False,
    poll_runner: Any = None,
) -> list[str]:
    """The single sanctioned operator qualification entrypoint (B4).

    Reads the five ACTUAL installed plists via :func:`verify_all_seats`,
    enforces distinct whole argv tuples and the shared-executable identity
    rule (distinct binaries OR a fully proven private profile/tunnel-id
    binding per shared seat — :func:`_require_shared_executables_fully_bound`),
    validates the closed operator facts schema (heartbeat attestation,
    native store, telemetry closed file set, pinned generation, repair
    digests — all explicit, never hardcoded or invented), assembles the
    manifest via :func:`build_manifest` with the pinned executable/parent/
    Cellar-allowance and poll-profile identities, and persists it PRIVATE
    (0600). ``dry_run`` performs every check and returns the secret-safe
    evidence without writing anything, which makes a first install from an
    empty manifest demonstrably feasible. Any refusal raises before ANY
    write, so an incomplete qualification fails closed.

    Seats declared ``first_party_cli_control_plane_poll`` are additionally
    PROVEN at qualification time, before anything is written: the seat's own
    verified executable and profile are checked (bounded, seat-owned, safe
    modes, symlink-free ancestors, cross-seat isolation), the profile's
    ``health.url_file`` locator is derived and verified, and ONE read-only
    probe — the exact health argv with the seat's pinned executable — must
    return the known-good control-plane-poll shape (``poll_runner`` is the
    injectable seam; the default is the real bounded runner). A probe that
    times out, errors, or fails schema validation refuses the whole
    qualification: an evidence source that never worked is never recorded.
    """
    if not dry_run and not operator_confirmed:
        # A dry run writes nothing, so it needs no operator confirmation;
        # any qualification that WRITES the manifest always does.
        raise PolicyRefused("qualify_requires_explicit_operator_confirmation")
    home = Path(home)
    seat_options, host_options = _validated_facts(facts)
    rogue = scan_family(home)
    if rogue:
        raise PolicyRefused(f"rogue_family_labels_present: {','.join(rogue)}")
    identities = verify_all_seats(home, uid)
    identity_by_label = {identity.label: identity for identity in identities}
    shared_exec_labels = _shared_executable_labels(identities)

    # First-party CLI control-plane-poll seats: derive + prove the evidence
    # source before anything else, so an unverifiable mode refuses loudly.
    cli_seats = sorted(
        key for key, options in seat_options.items()
        if options.get("heartbeat_mode") == HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL
    )
    bindings: dict[str, PollProfileBinding] = {}
    seen_profiles: dict[str, str] = {}
    seen_locators: dict[str, str] = {}
    seen_profile_identities: dict[tuple[int, int, str], str] = {}
    seen_locator_identities: dict[tuple[int, int, str], str] = {}
    seen_tunnel_ids: dict[str, str] = {}
    for key in cli_seats:
        entry = seat_options[key]
        seat_uid = int(identity_by_label[key].uid)
        seat_needs_binding = key in shared_exec_labels
        if seat_needs_binding:
            # The INSTALLED argv must carry EXACTLY ONE absolute
            # --profile-file option and it must equal the operator fact
            # byte-for-byte: the fact is accepted only for the file the job
            # itself names, so a swapped, steered, or relative profile can
            # never qualify a shared-executable seat.
            argv_profile = installed_argv_profile_file(
                key, identity_by_label[key].program_arguments
            )
            if argv_profile != entry["heartbeat_profile_file"]:
                raise PolicyRefused(f"facts_poll_profile_argv_mismatch:{key}")
        binding = verified_poll_profile_binding(
            key,
            entry["heartbeat_profile_file"],
            seat_uid,
            require_tunnel_id=seat_needs_binding,
        )
        # Cross-seat isolation: two seats may never share a profile file or a
        # URL locator — by path, by inode, by content digest, or by tunnel id
        # — or one swap would steer both seats' evidence.
        holder = seen_profiles.get(entry["heartbeat_profile_file"])
        if holder is not None:
            raise PolicyRefused(f"facts_poll_profile_duplicated:{key}:{holder}")
        seen_profiles[entry["heartbeat_profile_file"]] = key
        holder = seen_locators.get(binding.locator)
        if holder is not None:
            raise PolicyRefused(f"facts_poll_locator_duplicated:{key}:{holder}")
        seen_locators[binding.locator] = key
        profile_key = (binding.profile_dev, binding.profile_ino, binding.profile_sha256)
        holder = seen_profile_identities.get(profile_key)
        if holder is not None:
            raise PolicyRefused(f"facts_poll_profile_identity_duplicated:{key}:{holder}")
        seen_profile_identities[profile_key] = key
        locator_key = (binding.locator_dev, binding.locator_ino, binding.locator_sha256)
        holder = seen_locator_identities.get(locator_key)
        if holder is not None:
            raise PolicyRefused(f"facts_poll_locator_identity_duplicated:{key}:{holder}")
        seen_locator_identities[locator_key] = key
        if binding.tunnel_id_hash:
            holder = seen_tunnel_ids.get(binding.tunnel_id_hash)
            if holder is not None:
                raise PolicyRefused(f"facts_poll_tunnel_id_duplicated:{key}:{holder}")
            seen_tunnel_ids[binding.tunnel_id_hash] = key
        probe_argv = build_control_plane_poll_argv(identity_by_label[key].executable, binding.locator)
        runner = poll_runner if poll_runner is not None else control_plane_poll_runner
        try:
            result = runner(probe_argv, CLI_POLL_TIMEOUT_SECONDS)
        except (ActionRefused, OSError) as exc:
            raise PolicyRefused(f"facts_cli_poll_probe_refused: {key}") from exc
        verdict = validate_control_plane_poll_payload(
            result.stdout,
            result.stderr,
            result.returncode,
            now=now,
            timed_out=result.timed_out,
            truncated=result.truncated,
        )
        if not verdict.ok:
            raise PolicyRefused(f"facts_cli_poll_probe_failed: {key}:{verdict.reason}")
        entry["heartbeat_url_locator"] = binding.locator
        if seat_needs_binding:
            # Only shared-executable seats pin the full binding: their
            # per-seat identity IS the binding. Distinct-executable seats
            # keep the exact legacy manifest shape (backward compatible).
            entry["poll_profile"] = binding.manifest_fields()
        bindings[key] = binding

    # Shared-executable legality: the old blanket rejection of a shared
    # binary is replaced by this positive proof — every seat in a shared
    # group must carry the full binding above, with a present, well-formed,
    # group-unique tunnel-id digest.
    _require_shared_executables_fully_bound(identities, bindings)

    observed: dict[str, dict[str, Any]] = {}
    for identity in identities:
        raw = (home / identity.plist_rel).read_bytes()
        observed[identity.label] = parse_plist_bytes(raw, code=identity.label + "_qualify_read")
    manifest = build_manifest(
        home,
        uid,
        identities,
        observed,
        operator_confirmed=True,
        now=now,
        seat_options=seat_options,
        host_options=host_options,
    )
    lines = list(manifest_public_evidence(manifest))
    lines.append(
        evidence_line(
            "qualify",
            {
                "dry_run": bool(dry_run),
                "manifest_written": bool(not dry_run),
                "heartbeat_seats_attested": sum(
                    1 for options in seat_options.values() if options.get("heartbeat_kind")
                ),
                "heartbeat_cli_poll_seats": len(cli_seats),
                "telemetry_files_qualified": len(host_options.get("host_pull_telemetry_files", [])),
            },
        )
    )
    if not dry_run:
        write_manifest(home, manifest)
    return lines


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
        cli_poll = entry.get("heartbeat_mode") == HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL
        # Secret-safety: the CLI-poll profile and URL-locator paths are never
        # printed — the locator names the file that holds the control-plane
        # URL — so a cli seat shows a fixed placeholder instead of any path.
        # The tunnel-id digest is likewise shown only as a short prefix: the
        # raw id is never recorded anywhere to print.
        heartbeat_display = (
            "<first-party-cli-poll>" if cli_poll else entry.get("heartbeat_path", "<unset>")
        )
        pinned_profile = entry.get("poll_profile")
        lines.append(
            evidence_line(
                label,
                {
                    "plist_sha256": entry["plist_sha256"][:16],
                    "argv_len": len(entry["program_arguments"]),
                    "executable": entry["executable"],
                    "executable_sha256": entry["executable_sha256"][:16],
                    "heartbeat_mode": "cli_poll" if cli_poll else "file",
                    "heartbeat_path": heartbeat_display,
                    "profile_bound": bool(isinstance(pinned_profile, dict)),
                    "tunnel_id_hash": ((pinned_profile or {}).get("tunnel_id_hash") or "")[:16],
                    "cellar_allowed": bool(entry.get("cellar_ancestor")),
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
        mode = entry.get("heartbeat_mode")
        cli_poll = mode == HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL
        if cli_poll or (mode is None and entry.get("heartbeat_profile_file")):
            if mode is None or entry.get("heartbeat_path"):
                # Strictly typed modes: a manifest that mixes the file-mtime
                # evidence with the CLI-poll profile is ambiguous and is
                # never classified — alert-only until requalified.
                alerts.append(Alert("heartbeat_mode_ambiguous", label))
                continue
            if not entry.get("heartbeat_profile_file"):
                alerts.append(Alert("heartbeat_poll_profile_unqualified", label))
            elif not entry.get("heartbeat_kind"):
                alerts.append(Alert("heartbeat_first_party_unproven", label))
            continue
        if mode is not None and mode != HEARTBEAT_MODE_FILE_MTIME:
            alerts.append(Alert("heartbeat_mode_ambiguous", label))
        elif not entry.get("heartbeat_path"):
            alerts.append(Alert("heartbeat_path_unqualified", label))
        elif not entry.get("heartbeat_kind"):
            # A recorded heartbeat path without an operator first-party
            # attestation (B6): its mtime must never be treated as the
            # control-plane last-seen signal. Alert-only; forced restart on
            # staleness stays disabled for that seat.
            alerts.append(Alert("heartbeat_first_party_unproven", label))
    host = manifest
    if not host.get("native_store_path"):
        alerts.append(Alert("native_store_path_unqualified", "host"))
    if not host.get("host_pull_telemetry_dir"):
        alerts.append(Alert("host_pull_telemetry_unqualified", "host"))
    telemetry_files = host.get("host_pull_telemetry_files")
    if not isinstance(telemetry_files, list) or not telemetry_files:
        alerts.append(Alert("host_pull_telemetry_files_unqualified", "host"))
    if not host.get("pinned_generation"):
        alerts.append(Alert("pinned_generation_unqualified", "host"))
    repair = host.get("repair")
    if not isinstance(repair, dict) or not repair.get("files"):
        alerts.append(Alert("stdin_argmax_repair_unqualified", "host"))
    del home
    return alerts
