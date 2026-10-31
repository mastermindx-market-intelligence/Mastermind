"""Retained v5-to-v7 schema-upgrade evidence reader for the Executive store.

This module is an additive, read-only evidence boundary beside the existing
closed offline migration owners in ``control_plane.executive_backup``.  It
reads the four fixed upgrade receipts and the eight retained backup files of a
genuine ``upgrade_v5_to_v6`` + ``upgrade_v6_to_v7`` chain under actual Root
custody, re-verifies every retained backup with the unchanged public backup
validators, recomputes every claimed preservation fact from the verified
copies, and hands the resulting DATA to the existing Root Maintenance owner.

The real installed layout is the only layout addressed here: the configured
Control ``runtime_root`` is ``<host top>/control/db`` under the fixed physical
host root named by ``autonomy_control.RUNTIME_ROOT``, the authoritative store
lives at exactly ``<runtime_root>/data/control_plane/executive.sqlite3``
(``executive_runtime._DB_RELATIVE_PATH``), and the migration receipts, the
canonical service lock, the upgrade barrier and the service marker all live in
that same authoritative database directory, exactly as the existing offline
upgrade owner writes them.  The qualified backup root is the fixed
``<host top>/control/backups`` sibling; the Control configuration may only
confirm those two derived roots and can never nominate an arbitrary alias or
sibling of its own.

The reader is not an issuance, arm, restore, or migration authority.  It never
writes to the authoritative store, never constructs a ``RuntimeStore``, never
acquires the canonical service lock flock, never runs the writer census, and
never mutates original Control evidence.  Every temporary artifact is a private
verified copy created inside the context and removed on exit.
"""

from __future__ import annotations

import dataclasses
import grp
import hashlib
import json
import os
import pwd
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from control_plane import executive_backup as backup
from control_plane.executive_runtime import RuntimeProofError, _DB_RELATIVE_PATH
from control_plane.fs_security import has_macos_acl
from ops.executive_os import autonomy_control
from ops.executive_os import release_manifest

MATERIAL_SCHEMA_VERSION = "mastermind.executive_schema_upgrade_evidence_material/v1"
RECOVERED_MATERIAL_SCHEMA_VERSION = "mastermind.executive_schema_upgrade_evidence/pre_census_recovery_v1"
_RECOVERED_PREFLIGHT_SCHEMA = "mastermind.executive_schema_upgrade_pre_census_preflight/v1"
SPENT_CTIME_MATERIAL_SCHEMA_VERSION = "mastermind.executive_schema_upgrade_evidence/spent_pre_census_ctime_recovery_v1"
_SPENT_CTIME_PREFLIGHT_SCHEMA = "mastermind.executive_schema_upgrade_spent_pre_census_ctime_preflight/v1"
EVIDENCE_PHASE_INITIAL = "INITIAL"
EVIDENCE_PHASE_HISTORICAL = "HISTORICAL"
_EVIDENCE_PHASES = (EVIDENCE_PHASE_INITIAL, EVIDENCE_PHASE_HISTORICAL)

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ACCEPTANCE_DATABASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_RECEIPT_BYTES = 64 * 1024
_MAX_CONFIG_BYTES = getattr(autonomy_control, "_MAX_JSON_BYTES", 64 * 1024)
_MAX_DATABASE_BYTES = 8 * 1024 * 1024 * 1024
_COPY_BLOCK = 1024 * 1024

_SIDE_CAR_SUFFIXES = ("-wal", "-shm", "-journal")
_STEP_SOURCE_VERSIONS = {5: 6, 6: 7}

# The one genuine fixed system mapping the platform itself performs.  Nothing
# else may rewrite a configured path into a different physical location.
_FIXED_SYSTEM_MAPPINGS: tuple[tuple[Path, Path], ...] = (
    (Path("/var"), Path("/private/var")),
)

_DATABASE_KEYS = frozenset({"path", "device", "inode", "size", "sha256"})
_RECEIPT_COMMON_KEYS = frozenset(
    {
        "schema_version",
        "operation_id",
        "source_schema_version",
        "target_schema_version",
        "tool_release_root",
        "tool_release_tree_sha",
        "tool_release_manifest_sha256",
        "release_sha",
    }
)
_PREFLIGHT_KEYS = _RECEIPT_COMMON_KEYS | {
    "database",
    "migration_vector",
    "normalized_schema_digest",
    "barrier_identity",
    "quiesce_writer_census",
    "quiesce_writer_census_digest",
    "created_at",
}
_COMPLETION_KEYS = _RECEIPT_COMMON_KEYS | {
    "preflight_receipt_digest",
    "migration_vector",
    "quiesce_writer_census_digest",
    "completed_at",
}
_BACKUP_COMMON_KEYS = frozenset(
    {
        "database_path",
        "database_sha256",
        "manifest_path",
        "manifest_sha256",
        "restore_drill_receipt",
        "restore_drill_digest",
    }
)
_DRILL_KEYS = frozenset(
    {
        "database_sha256",
        "runtime_schema_version",
        "migration_versions",
        "integrity_check",
        "foreign_key_check",
        "normalized_schema_digest",
        "legacy_content_digest",
    }
)
# Acceptance origin identity wire: exact full physical identity of one original
# file, with no role, kind, or payload provenance mixed in.
_IDENTITY_RECORD_KEYS = frozenset(
    {
        "path",
        "device",
        "inode",
        "uid",
        "gid",
        "mode",
        "nlink",
        "size",
        "mtime_ns",
        "ctime_ns",
        "sha256",
    }
)
_ORIGIN_KEYS = _IDENTITY_RECORD_KEYS | {"kind", "role"}
_RECEIPT_ORIGIN_KEYS = _ORIGIN_KEYS | {"payload_digest"}
_MATERIAL_KEYS = frozenset({"schema_version", "phase", "host", "origin_records", "chain"})
_HOST_KEYS = frozenset(
    {"runtime_root", "backup_root", "control_uid", "control_gid"}
)
_TOOL_RELEASE_KEYS = frozenset(
    {"root", "sha", "tree_sha", "manifest_sha256"}
)
_STEP_KEYS = frozenset({"operation_id", "preflight", "completion"})
_RECEIPT_REF_KEYS = frozenset({"path", "sha256", "payload_digest"})
_CHAIN_KEYS = frozenset(
    {
        "source_schema_version",
        "target_schema_version",
        "database_path",
        "tool_release",
        "step_v5_to_v6",
        "step_v6_to_v7",
        "full_v4_content_digest",
        "legacy_content_digest",
        "original_full_v5_content_digest",
        "preserved_full_v5_content_digest",
        "intermediate_full_v6_content_digest",
        "initial_v7_full_v6_content_digest",
        "initial_v7_physical_history_digest",
        "initial_v7_backup_identity",
    }
)
_BACKUP_IDENTITY_KEYS = frozenset(
    {"database_path", "database_sha256", "manifest_path", "manifest_sha256"}
)
_EXPECTED_ROLES = (
    "P56",
    "C56",
    "P67",
    "C67",
    "v5_backup_database",
    "v5_backup_manifest",
    "c56_v6_backup_database",
    "c56_v6_backup_manifest",
    "p67_v6_backup_database",
    "p67_v6_backup_manifest",
    "v7_backup_database",
    "v7_backup_manifest",
)
_RECOVERY_ROLES = ("pre_census_qualification", "pre_census_continuation")
_RECOVERED_ROLES = _EXPECTED_ROLES + _RECOVERY_ROLES
_SPENT_CTIME_ROLES = _EXPECTED_ROLES + (
    "pre_census_qualification", "spent_pre_census_continuation",
    "spent_pre_census_ctime_reconciliation", "spent_pre_census_ctime_continuation")
_SPENT_CTIME_REFERENCE_KEYS = frozenset({"qualification_identity", "spent_continuation_identity",
                                        "reconciliation_identity", "continuation_identity"})
_SPENT_CTIME_CHAIN_KEYS = _SPENT_CTIME_REFERENCE_KEYS | {"original_tool", "original_barrier"}
_RECOVERY_REFERENCE_KEYS = frozenset({"qualification_identity", "continuation_identity"})
_RECOVERY_CHAIN_KEYS = frozenset({"original_tool", "original_barrier",
                                  "qualification_identity", "continuation_identity"})


class SchemaUpgradeEvidenceError(RuntimeProofError):
    """Base class for retained schema-upgrade evidence failures."""


class EvidenceCustodyError(SchemaUpgradeEvidenceError):
    """Retained evidence is not under exact qualified Root/Control custody."""


class RetainedChainInvalid(SchemaUpgradeEvidenceError):
    """The retained v5-to-v7 chain does not prove the claimed transition."""


# ---------------------------------------------------------------------------
# Private production seams.  Isolated tests may monkeypatch these to the
# current fixture UID/platform; production always uses the real Root gate,
# the fixed Control principal database lookup, and the installed release
# observers.  No public authority flows through a seam.
# ---------------------------------------------------------------------------


def _root_darwin_gate() -> None:
    """Refuse anything but the actual Root principal on the Darwin host."""
    if sys.platform != "darwin":
        raise EvidenceCustodyError(
            "schema upgrade evidence requires the qualified Darwin host"
        )
    if os.geteuid() != 0:
        raise EvidenceCustodyError(
            "schema upgrade evidence requires the actual Root principal"
        )


def _control_identity() -> tuple[int, int]:
    """Resolve the fixed protected Control principal, never the caller's UID."""
    try:
        record = pwd.getpwnam(autonomy_control.CONTROL_USER)
        group = grp.getgrnam(autonomy_control.CONTROL_GROUP)
    except (KeyError, OSError, ValueError) as exc:
        raise EvidenceCustodyError(
            "protected Control principal is unavailable"
        ) from exc
    uid, gid = record.pw_uid, group.gr_gid
    if type(uid) is not int or type(gid) is not int or uid <= 0 or gid <= 0:
        raise EvidenceCustodyError("protected Control principal is malformed")
    if (record.pw_name != autonomy_control.CONTROL_USER
            or record.pw_gid != gid
            or group.gr_name != autonomy_control.CONTROL_GROUP):
        raise EvidenceCustodyError("protected Control principal is ambiguous")
    return uid, gid


def _physical_host_top() -> Path:
    """Return the real qualified physical canonical host top root."""
    logical = autonomy_control.RUNTIME_ROOT
    expected = logical
    if logical == Path("/var/db/mastermind-executive"):
        alias = Path("/var")
        info = alias.lstat()
        if (not stat.S_ISLNK(info.st_mode) or info.st_uid != 0
                or os.readlink(alias) not in ("private/var", "/private/var")):
            raise EvidenceCustodyError("fixed system /var alias is unqualified")
        expected = Path("/private/var/db/mastermind-executive")
    canonical = Path(os.path.realpath(logical))
    if canonical != expected:
        raise EvidenceCustodyError("fixed host namespace contains a foreign alias")
    try:
        info = canonical.lstat()
    except OSError as exc:
        raise EvidenceCustodyError(
            "qualified physical host top mapping is unavailable"
        ) from exc
    if (stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != 0 or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != 0o711 or _path_has_acl(canonical, info)):
        raise EvidenceCustodyError(
            "qualified physical host top mapping is not the bootstrap Root0711 directory"
        )
    return canonical


def _system_alias_identity(runtime_root: Path) -> tuple[Any, ...] | None:
    """Retain only the fixed system alias; fixtures use an explicit host seam."""
    if runtime_root != Path("/private/var/db/mastermind-executive/control/db"):
        return None
    path = Path("/var")
    info = path.lstat()
    target = os.readlink(path)
    if (not stat.S_ISLNK(info.st_mode) or info.st_uid != 0
            or target not in ("private/var", "/private/var")):
        raise EvidenceCustodyError("fixed system alias is unqualified")
    return (*_identity_tuple(info), target)


def _host_layout() -> tuple[Path, Path]:
    """Derive the fixed runtime and backup roots from the physical host top.

    ``install.sh`` lays down exactly ``<top>/control/db`` as the Control
    runtime root and ``<top>/control/backups`` as the backup root.  The
    configuration may only confirm these derived roots; it can never nominate
    an arbitrary sibling or alias.
    """
    top = _physical_host_top()
    return top / "control" / "db", top / "control" / "backups"


def _control_config_path() -> Path:
    return autonomy_control.CONTROL_CONFIG


def _read_qualified_control_config(
    path: Path, *, control_gid: int
) -> tuple[dict[str, Any], bytes]:
    """Read the Root-owned Control configuration through its exact real gate.

    The installed Control configuration is ``root:<Control group> 0440`` with
    no ACL, a single link, and no symlink: this is a strictly different
    custody gate from the Control-owned 0600 originals, so it is never
    qualified with the generic owner-only profile.
    """
    return autonomy_control._root_json(
        path,
        modes=frozenset({0o440}),
        uid=0,
        gid=control_gid,
    )


def _control_profile(control_uid: int, control_gid: int) -> "_CustodyProfile":
    """Exact custody of Control-owned original artifacts (receipts/backups)."""
    return _CustodyProfile(uid=control_uid, gid=control_gid, mode=0o600)


def _control_config_profile(
    control_uid: int, control_gid: int
) -> "_CustodyProfile":
    """Exact custody of the Root-owned 0440 Control configuration."""
    return _CustodyProfile(uid=0, gid=control_gid, mode=0o440)


def _config_namespace_profile() -> "_CustodyProfile":
    """Bootstrap-owned fixed config directory; distinct from Control-private state."""
    return _CustodyProfile(uid=0, gid=0, mode=0o755)


def _prove_current_release(expected_sha: str) -> dict[str, str]:
    """INITIAL tool proof through the existing exact-SHA release observer."""
    return dict(backup._prove_upgrade_release(expected_sha))


def _verify_pinned_release(root: Path, sha: str, tree_sha: str) -> dict[str, Any]:
    """HISTORICAL tool proof of the retained original release, not this module."""
    expected_root = autonomy_control.SYSTEM_ROOT / "releases" / sha
    if root != expected_root or root.name != sha or root.resolve(strict=True) != root:
        raise RetainedChainInvalid("retained tool root is not its fixed sealed release")
    value = dict(release_manifest.verify(root, sha, tree_sha))
    # Reuse the existing fixed-SHA, manifest-only 4 MiB owner.  Generic
    # configuration limits and the full sealed-release verification stay intact.
    raw = autonomy_control._release_manifest_bytes(sha)
    value["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    return value


def _path_has_acl(path: Path, info: os.stat_result) -> bool:
    try:
        return has_macos_acl(path, expected_identity=info)
    except Exception as exc:  # noqa: BLE001 - fail closed on any ACL fault
        raise EvidenceCustodyError(
            f"retained evidence ACL observation failed: {path.name}"
        ) from exc


# ---------------------------------------------------------------------------
# Strict JSON and closed-shape helpers
# ---------------------------------------------------------------------------


def _strict_evidence_json(raw: bytes, label: str) -> Any:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise RetainedChainInvalid(
                    f"{label} has duplicate JSON key {key!r}"
                )
            result[key] = value
        return result

    def refuse_constant(name: str) -> Any:
        raise RetainedChainInvalid(f"{label} contains non-finite constant {name}")

    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_constant=refuse_constant,
        )
    except RetainedChainInvalid:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RetainedChainInvalid(f"{label} is not strict UTF-8 JSON: {exc}") from exc


def _require_closed(value: Any, keys: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise RetainedChainInvalid(f"{label} is not the closed evidence shape")
    return dict(value)


def _require_hex(value: Any, label: str, *, length: int = 64) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        rf"^[0-9a-f]{{{length}}}$", value
    ):
        raise RetainedChainInvalid(f"{label} is not an exact lowercase digest")
    return value


def _require_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise RetainedChainInvalid(f"{label} is not a plain nonnegative integer")
    return value


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RetainedChainInvalid(f"{label} is not a nonempty string")
    return value


# ---------------------------------------------------------------------------
# Descriptor custody
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _CustodyProfile:
    """Exact owner/group/mode custody of one class of original file."""

    uid: int
    gid: int
    mode: int


@dataclasses.dataclass(frozen=True)
class _HeldDirectory:
    path: Path
    descriptor: int
    identity: os.stat_result


@dataclasses.dataclass(frozen=True)
class _HeldFile:
    role: str
    kind: str
    path: Path
    descriptor: int
    held: os.stat_result
    named: os.stat_result
    sha256: str
    raw: bytes | None = None
    payload: dict[str, Any] | None = None
    payload_digest: str | None = None

    def identity_record(self) -> dict[str, Any]:
        """Exact closed full-identity wire of one original file."""
        return {
            "path": str(self.path),
            "device": int(self.held.st_dev),
            "inode": int(self.held.st_ino),
            "uid": int(self.held.st_uid),
            "gid": int(self.held.st_gid),
            "mode": stat.S_IMODE(self.held.st_mode),
            "nlink": int(self.held.st_nlink),
            "size": int(self.held.st_size),
            "mtime_ns": int(self.held.st_mtime_ns),
            "ctime_ns": int(self.held.st_ctime_ns),
            "sha256": self.sha256,
        }

    def origin_record(self) -> dict[str, Any]:
        """Material origin wire: provenance plus the full physical identity."""
        value: dict[str, Any] = {
            "kind": self.kind,
            "role": self.role,
            **self.identity_record(),
        }
        if self.payload_digest is not None:
            value["payload_digest"] = self.payload_digest
        return value

    def identity(self) -> tuple[int, ...]:
        return _identity_tuple(self.held)


def _identity_tuple(info: os.stat_result) -> tuple[int, ...]:
    """Complete physical identity including file times."""
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_size),
        int(info.st_mode),
        int(info.st_uid),
        int(info.st_gid),
        int(info.st_nlink),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
    )


def _read_descriptor(descriptor: int, limit: int, label: str) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.pread(descriptor, _COPY_BLOCK, total)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise EvidenceCustodyError(f"{label} exceeds its closed size bound")
        chunks.append(chunk)
    return b"".join(chunks)


def _qualify_control_file(
    path: Path,
    *,
    role: str,
    kind: str,
    profile: _CustodyProfile,
    limit: int,
) -> _HeldFile:
    """Open one original nofollow and bind its complete physical identity.

    The named object and the opened descriptor must be the same file with the
    exact custody profile, and the identity and ACL are re-observed after the
    bytes are read, so the held hash always belongs to the named original.
    """
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise EvidenceCustodyError(f"{role} is unavailable: {exc}") from exc
    try:
        held = os.fstat(descriptor)
        named = os.lstat(path)
        if (
            not stat.S_ISREG(held.st_mode)
            or held.st_nlink != 1
            or held.st_uid != profile.uid
            or held.st_gid != profile.gid
            or stat.S_IMODE(held.st_mode) != profile.mode
            or (named.st_dev, named.st_ino) != (held.st_dev, held.st_ino)
            or _identity_tuple(named) != _identity_tuple(held)
        ):
            raise EvidenceCustodyError(
                f"{role} is not an exact qualified owner-only single-link original"
            )
        if _path_has_acl(path, held):
            raise EvidenceCustodyError(f"{role} carries a filesystem ACL")
        raw = _read_descriptor(descriptor, limit, role)
        after = os.fstat(descriptor)
        after_named = os.lstat(path)
        if (
            _identity_tuple(after) != _identity_tuple(held)
            or _identity_tuple(after_named) != _identity_tuple(held)
            or (after_named.st_dev, after_named.st_ino)
            != (held.st_dev, held.st_ino)
        ):
            raise EvidenceCustodyError(f"{role} changed while it was being read")
        if _path_has_acl(path, after):
            raise EvidenceCustodyError(f"{role} gained a filesystem ACL during read")
    except BaseException:
        os.close(descriptor)
        raise
    return _HeldFile(
        role=role,
        kind=kind,
        path=path,
        descriptor=descriptor,
        held=held,
        named=named,
        sha256=hashlib.sha256(raw).hexdigest(),
        raw=raw if kind == "receipt" else None,
    )


def _validate_namespace(
    leaf: Path,
    *,
    protected_root: Path,
    control_uid: int,
    held_dirs: dict[Path, _HeldDirectory],
    directory_profile: _CustodyProfile | None = None,
) -> None:
    """Walk the lexical ancestor chain and hold every qualified directory FD.

    The walk is strictly lexical from the filesystem anchor down to the leaf,
    opening every component with ``O_NOFOLLOW|O_DIRECTORY`` relative to its
    already-held parent descriptor, so an arbitrary alias or symlink hidden in
    the middle of the path can never be silently resolved into the qualified
    location.  Root-owned system ancestors above the protected root are
    accepted exactly as the installed layout permits; every directory at or
    below the protected root must be Control-private.
    """
    if not leaf.is_absolute() or not protected_root.is_absolute():
        raise EvidenceCustodyError("qualified namespace paths must be absolute")
    if leaf != protected_root and protected_root not in leaf.parents:
        raise EvidenceCustodyError(
            f"retained evidence escapes its qualified root: {leaf}"
        )
    current = Path(leaf.anchor)
    anchor = held_dirs.get(current)
    if anchor is None:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        descriptor = os.open(current, flags)
        try:
            held = os.fstat(descriptor)
            if (not stat.S_ISDIR(held.st_mode) or held.st_uid != 0 or held.st_gid != 0
                    or stat.S_IMODE(held.st_mode) & 0o022):
                raise EvidenceCustodyError("filesystem anchor is unqualified")
            if _path_has_acl(current, held):
                raise EvidenceCustodyError("filesystem anchor carries an ACL")
        except BaseException:
            os.close(descriptor)
            raise
        held_dirs[current] = _HeldDirectory(current, descriptor, held)
        anchor = held_dirs[current]
    parent_descriptor: int | None = anchor.descriptor
    below = False
    for component in leaf.parts[1:]:
        next_path = current / component
        below = below or next_path == protected_root
        already = held_dirs.get(next_path)
        if already is not None:
            current = next_path
            parent_descriptor = already.descriptor
            continue
        try:
            if parent_descriptor is None:
                named = os.lstat(next_path)
            else:
                named = os.lstat(component, dir_fd=parent_descriptor)
        except OSError as exc:
            raise EvidenceCustodyError(
                f"retained evidence namespace is unavailable: {next_path}"
            ) from exc
        if stat.S_ISLNK(named.st_mode) or not stat.S_ISDIR(named.st_mode):
            raise EvidenceCustodyError(
                f"retained evidence namespace contains an alias: {next_path}"
            )
        if _path_has_acl(next_path, named):
            raise EvidenceCustodyError("retained evidence namespace carries an ACL")
        if below and directory_profile is not None:
            if (named.st_uid != directory_profile.uid
                    or named.st_gid != directory_profile.gid
                    or stat.S_IMODE(named.st_mode) != directory_profile.mode):
                raise EvidenceCustodyError("Root configuration namespace is unqualified")
        elif below:
            if named.st_uid != control_uid or stat.S_IMODE(named.st_mode) & 0o077:
                raise EvidenceCustodyError(
                    f"protected evidence directory is not Control-private: {next_path}"
                )
        elif (named.st_uid not in (0, control_uid)
                or (stat.S_IMODE(named.st_mode) & 0o022
                    and not (named.st_uid == 0 and named.st_mode & stat.S_ISVTX))):
            raise EvidenceCustodyError(
                f"protected evidence namespace has a foreign or writable owner: {next_path}"
            )
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            if parent_descriptor is None:
                descriptor = os.open(next_path, flags)
            else:
                descriptor = os.open(component, flags, dir_fd=parent_descriptor)
        except OSError as exc:
            raise EvidenceCustodyError(
                f"cannot hold protected evidence directory: {next_path}"
            ) from exc
        try:
            held = os.fstat(descriptor)
        except OSError as exc:
            os.close(descriptor)
            raise EvidenceCustodyError(
                f"cannot observe protected evidence directory: {next_path}"
            ) from exc
        if (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino):
            os.close(descriptor)
            raise EvidenceCustodyError(
                f"protected evidence directory changed while opening: {next_path}"
            )
        held_dirs[next_path] = _HeldDirectory(next_path, descriptor, held)
        current = next_path
        parent_descriptor = descriptor


def _fixed_lexical_variants(path: Path) -> tuple[Path, ...]:
    """The one canonical path plus its genuine fixed system-mapped spelling."""
    variants = [path]
    for logical, physical in _FIXED_SYSTEM_MAPPINGS:
        for source, target in ((logical, physical), (physical, logical)):
            try:
                variants.append(target / path.relative_to(source))
            except ValueError:
                continue
    return tuple(dict.fromkeys(variants))


def _resolve_runtime_root_argument(
    argument: Path,
    *,
    runtime_physical: Path,
    control_uid: int,
    guard: "_EvidenceGuard",
) -> Path:
    """Address evidence only through the qualified fixed host runtime root."""
    if not isinstance(argument, Path):
        argument = Path(argument)
    if not argument.is_absolute():
        raise EvidenceCustodyError("runtime_root must be an absolute canonical path")
    lexical = Path(os.path.normpath(argument))
    if lexical not in _fixed_lexical_variants(runtime_physical):
        raise EvidenceCustodyError(
            "runtime_root is not the qualified physical canonical host mapping"
        )
    if Path(os.path.realpath(lexical)) != runtime_physical:
        raise EvidenceCustodyError(
            "runtime_root does not resolve to the qualified host mapping"
        )
    _validate_namespace(
        runtime_physical,
        protected_root=runtime_physical,
        control_uid=control_uid,
        held_dirs=guard.dirs,
    )
    return runtime_physical


def _require_no_sidecars(database: Path, *, label: str) -> None:
    for suffix in _SIDE_CAR_SUFFIXES:
        if os.path.lexists(database.with_name(database.name + suffix)):
            raise EvidenceCustodyError(f"{label} has a SQLite sidecar")


def _require_absent(path: Path, *, label: str) -> None:
    if os.path.lexists(path):
        raise EvidenceCustodyError(f"{label} exists; refused")


def _copy_descriptor_to_temp(
    descriptor: int, destination: Path, *, expected_sha256: str
) -> Path:
    """Copy exact held bytes into an explicit private 0600 temporary file."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    target = os.open(destination, flags, 0o600)
    digest = hashlib.sha256()
    offset = 0
    try:
        while True:
            chunk = os.pread(descriptor, _COPY_BLOCK, offset)
            if not chunk:
                break
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(target, view)
                if written <= 0:  # pragma: no cover - defensive OS boundary
                    raise OSError("short write while staging retained evidence copy")
                view = view[written:]
            offset += len(chunk)
        os.fsync(target)
    finally:
        os.close(target)
    if digest.hexdigest() != expected_sha256:
        destination.unlink(missing_ok=True)
        raise EvidenceCustodyError(
            f"retained evidence copy does not match its original: {destination.name}"
        )
    return destination


_BACKUP_V4DIGEST_KEYS = _BACKUP_COMMON_KEYS | {"full_v4_content_digest"}
_BACKUP_V5_KEYS = _BACKUP_V4DIGEST_KEYS
_BACKUP_V6_KEYS = _BACKUP_COMMON_KEYS | {"full_v6_content_digest"}
_BACKUP_V7_KEYS = _BACKUP_COMMON_KEYS | {
    "full_v6_content_digest",
    "physical_history_digest",
}
_BARRIER_IDENTITY_KEYS = frozenset(
    {"path", "device", "inode", "size", "sha256", "payload_digest"}
)


def _migration5_receipt_digest(connection: sqlite3.Connection) -> str:
    """Recompute migration 5's retained receipt digest from a verified copy."""
    rows = connection.execute(
        "SELECT typeof(version),version,typeof(name),name,typeof(checksum),checksum,"
        "typeof(applied_at_ms),applied_at_ms FROM schema_migrations WHERE version=5"
    ).fetchall()
    if (
        len(rows) != 1
        or rows[0][0] != "integer"
        or type(rows[0][1]) is not int
        or rows[0][1] != 5
        or rows[0][2] != "text"
        or not isinstance(rows[0][3], str)
        or rows[0][4] != "text"
        or not isinstance(rows[0][5], str)
        or rows[0][6] != "integer"
        or type(rows[0][7]) is not int
    ):
        raise RetainedChainInvalid("retained migration-5 receipt identity is invalid")
    return backup._upgrade_digest(list(rows[0]))


def _require_initial_physical_history(connection: sqlite3.Connection) -> str:
    """Recompute the closed initial-v7 physical history from a verified copy."""
    for table in ("physical_resource_commitments", "physical_resource_demands"):
        if connection.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone() is not None:
            raise RetainedChainInvalid(
                "initial v7 material requires empty physical tables"
            )
    if connection.execute(
        f"SELECT 1 FROM events WHERE {backup._PHYSICAL_EVENT_PREDICATE} LIMIT 1"
    ).fetchone() is not None:
        raise RetainedChainInvalid("initial v7 material retains a physical Event")
    return backup.physical_history_digest(connection)


# ---------------------------------------------------------------------------
# Context custody guard
# ---------------------------------------------------------------------------


class _EvidenceGuard:
    """Own every retained descriptor, namespace FD, and temporary copy."""

    def __init__(self, control_uid: int, control_gid: int) -> None:
        self.control_uid = control_uid
        self.control_gid = control_gid
        self.files: list[_HeldFile] = []
        self.dirs: dict[Path, _HeldDirectory] = {}
        self.temp_root: Path | None = None
        self._temp_counter = 0
        self.backup_root: Path | None = None
        # The frozen exactly-eight qualified backup additions.  Acceptance
        # pairs verified later never enter this mapping.
        self.inventory_paths: dict[Path, str] = {}
        self.inventory_additions: dict[str, dict[str, Any]] = {}
        self.initial_paths_absent: tuple[Path, ...] = ()
        # Immutable migration and acceptance backup pairs remain sidecar-free
        # throughout custody, including HISTORICAL openings with a live service.
        self.backup_databases: set[Path] = set()
        self.host_roots: tuple[Path, Path] | None = None
        self.system_alias_identity: tuple[Any, ...] | None = None

    def temp_directory(self) -> Path:
        self._temp_counter += 1
        if self.temp_root is None:
            raw = tempfile.mkdtemp(prefix="mastermind-executive-upgrade-evidence-")
            root = Path(raw)
            root.chmod(0o700)
            self.temp_root = root
        directory = self.temp_root / f"material-{self._temp_counter:04d}"
        directory.mkdir(mode=0o700)
        return directory

    def hold(self, item: _HeldFile) -> _HeldFile:
        self.files.append(item)
        return item

    def check(self) -> list[dict[str, Any]]:
        """Revalidate every retained FD, name, namespace, and hash."""
        if self.host_roots is not None:
            if (_host_layout() != self.host_roots
                    or _system_alias_identity(self.host_roots[0]) != self.system_alias_identity):
                raise EvidenceCustodyError("fixed host namespace mapping changed")
        for directory in self.dirs.values():
            held = os.fstat(directory.descriptor)
            named = os.lstat(directory.path)
            # Directory st_nlink is only the live subdirectory count of a
            # possibly shared system directory, so it is deliberately outside
            # the revalidation identity; object identity, mode, and owner are
            # what custody actually rests on.
            if (
                not stat.S_ISDIR(held.st_mode)
                or (
                    int(held.st_dev),
                    int(held.st_ino),
                    int(held.st_mode),
                    int(held.st_uid),
                    int(held.st_gid),
                )
                != (
                    int(directory.identity.st_dev),
                    int(directory.identity.st_ino),
                    int(directory.identity.st_mode),
                    int(directory.identity.st_uid),
                    int(directory.identity.st_gid),
                )
                or (named.st_dev, named.st_ino) != (held.st_dev, held.st_ino)
            ):
                raise EvidenceCustodyError(
                    f"protected evidence directory changed: {directory.path}"
                )
            if _path_has_acl(directory.path, held):
                raise EvidenceCustodyError("retained namespace gained an ACL")
        records: list[dict[str, Any]] = []
        for item in self.files:
            records.append(self._check_file(item))
        if self.backup_root is not None:
            observed = _inventory_records(self.backup_root, self.inventory_paths)
            if observed != self.inventory_additions:
                raise EvidenceCustodyError(
                    "qualified backup root inventory changed during evidence custody"
                )
        for database in self.backup_databases:
            _require_no_sidecars(database, label="retained backup custody")
        for path in self.initial_paths_absent:
            _require_absent(path, label=f"retained custody artifact {path.name}")
        return records

    def _check_file(self, item: _HeldFile) -> dict[str, Any]:
        held = os.fstat(item.descriptor)
        named = os.lstat(item.path)
        if (
            not stat.S_ISREG(held.st_mode)
            or item.identity() != _identity_tuple(held)
            or _identity_tuple(named) != _identity_tuple(held)
            or (named.st_dev, named.st_ino) != (held.st_dev, held.st_ino)
            or held.st_nlink != 1
        ):
            raise EvidenceCustodyError(
                f"retained evidence identity changed: {item.role}"
            )
        if _path_has_acl(item.path, held):
            raise EvidenceCustodyError("retained original gained an ACL")
        raw = _read_descriptor(item.descriptor, _limit_for(item), item.role)
        if hashlib.sha256(raw).hexdigest() != item.sha256:
            raise EvidenceCustodyError(f"retained evidence bytes changed: {item.role}")
        if item.payload is not None and backup._upgrade_receipt_bytes(item.payload) != raw:
            raise EvidenceCustodyError(
                f"retained receipt producer bytes changed: {item.role}"
            )
        return item.origin_record()

    def close(self) -> None:
        for item in self.files:
            try:
                os.close(item.descriptor)
            except OSError:
                pass
        self.files.clear()
        for directory in self.dirs.values():
            try:
                os.close(directory.descriptor)
            except OSError:
                pass
        self.dirs.clear()
        if self.temp_root is not None:
            shutil.rmtree(self.temp_root, ignore_errors=True)
            self.temp_root = None


def _limit_for(item: _HeldFile) -> int:
    if item.kind == "receipt":
        return _MAX_RECEIPT_BYTES
    if item.kind == "config":
        return _MAX_CONFIG_BYTES
    return _MAX_DATABASE_BYTES


def _inventory_records(
    backup_root: Path, digests: Mapping[Path, str]
) -> dict[str, dict[str, Any]]:
    """Maintenance inventory shape over exactly the eight qualified additions.

    Preexisting and unrelated backups in the qualified root belong to the
    existing Maintenance owner's exact old-inventory guard, so this reader
    neither scans for them nor adopts them: it only reports the retained
    migration files it already holds under named custody.
    """
    result: dict[str, dict[str, Any]] = {}
    for path, digest in sorted(
        digests.items(), key=lambda item: os.fspath(item[0])
    ):
        if not path.is_relative_to(backup_root):
            raise EvidenceCustodyError(
                f"qualified inventory entry escapes its backup root: {path}"
            )
        try:
            info = os.lstat(path)
        except OSError as exc:
            raise EvidenceCustodyError(
                f"qualified backup root entry is unavailable: {path.name}"
            ) from exc
        if not stat.S_ISREG(info.st_mode):
            raise EvidenceCustodyError(
                f"qualified inventory entry is not a regular file: {path.name}"
            )
        if _path_has_acl(path, info):
            raise EvidenceCustodyError(
                f"qualified backup root entry carries an ACL: {path.name}"
            )
        result[str(path)] = {
            "uid": int(info.st_uid),
            "gid": int(info.st_gid),
            "mode": stat.S_IMODE(info.st_mode),
            "nlink": int(info.st_nlink),
            "sha256": digest,
        }
    return result


# ---------------------------------------------------------------------------
# Receipt and retained-backup verification
# ---------------------------------------------------------------------------


def _require_within_root(path: Path, root: Path, *, label: str) -> Path:
    """Require strict lexical containment and a real in-root object."""
    if not path.is_absolute() or path == root or not path.is_relative_to(root):
        raise EvidenceCustodyError(
            f"{label} is outside its qualified root: {path}"
        )
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise EvidenceCustodyError(f"{label} is unavailable: {exc}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise EvidenceCustodyError(
            f"{label} escapes its qualified root through a symlink alias: {path}"
        )
    return path


_RECEIPT_KEYS: dict[str, frozenset[str]] = {
    "P56": _PREFLIGHT_KEYS
    | {"full_v4_content_digest", "v5_migration_receipt_digest", "v5_backup"},
    "C56": _COMPLETION_KEYS
    | {
        "authoritative_v6_database",
        "authoritative_v6_schema_digest",
        "pre_full_v4_content_digest",
        "post_full_v4_content_digest",
        "pre_v5_migration_receipt_digest",
        "post_v5_migration_receipt_digest",
        "full_v4_content_equal",
        "pre_v4_legacy_content_digest",
        "post_v4_legacy_content_digest",
        "legacy_content_equal",
        "v6_backup",
    },
    "P67": _PREFLIGHT_KEYS | {"full_v6_content_digest", "v6_backup"},
    "C67": _COMPLETION_KEYS
    | {
        "authoritative_v7_database",
        "authoritative_v7_schema_digest",
        "pre_full_v6_content_digest",
        "post_full_v6_content_digest",
        "full_v6_content_equal",
        "physical_history_digest",
        "initial_physical_tables_empty",
        "pre_v6_legacy_content_digest",
        "post_v6_legacy_content_digest",
        "legacy_content_equal",
        "v7_backup",
    },
}


def _load_receipt(
    guard: _EvidenceGuard,
    path: Path,
    *,
    role: str,
    schema: str,
    source_version: int,
    target_version: int,
    protected_root: Path,
) -> tuple[_HeldFile, dict[str, Any], str]:
    held = guard.hold(
        _qualify_control_file(
            path,
            role=role,
            kind="receipt",
            profile=_control_profile(guard.control_uid, guard.control_gid),
            limit=_MAX_RECEIPT_BYTES,
        )
    )
    payload = _strict_evidence_json(held.raw, role)
    recovered = (role == "P56" and isinstance(payload, dict)
                 and payload.get("schema_version") in {_RECOVERED_PREFLIGHT_SCHEMA, _SPENT_CTIME_PREFLIGHT_SCHEMA})
    keys = _RECEIPT_KEYS[role] | {"pre_census_reconciliation"} if recovered else _RECEIPT_KEYS[role]
    payload = _require_closed(payload, keys, role)
    if payload["schema_version"] not in ({_RECOVERED_PREFLIGHT_SCHEMA, _SPENT_CTIME_PREFLIGHT_SCHEMA} if recovered else {schema}):
        raise RetainedChainInvalid(f"{role} schema version is not the closed producer")
    if (
        payload["source_schema_version"] != source_version
        or payload["target_schema_version"] != target_version
    ):
        raise RetainedChainInvalid(f"{role} does not prove its exact closed transition")
    if backup._upgrade_receipt_bytes(payload) != held.raw:
        raise RetainedChainInvalid(f"{role} is not canonical producer bytes")
    digest = backup._upgrade_digest(payload)
    _validate_namespace(
        path.parent,
        protected_root=protected_root,
        control_uid=guard.control_uid,
        held_dirs=guard.dirs,
    )
    return held, payload, digest


def _artifact_reference(held: _HeldFile, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"path": str(held.path), "device": held.held.st_dev,
            "inode": held.held.st_ino, "size": held.held.st_size,
            "sha256": held.sha256, "payload_digest": backup._upgrade_digest(payload)}


def _load_pre_census_reconciliation(guard, preflight, state_directory):
    """Retain two explicit recovery origins without changing the normal wire."""
    if preflight["schema_version"] == _SPENT_CTIME_PREFLIGHT_SCHEMA:
        return _load_spent_ctime_reconciliation(guard, preflight, state_directory)
    if preflight["schema_version"] != _RECOVERED_PREFLIGHT_SCHEMA:
        return None
    refs = _require_closed(preflight["pre_census_reconciliation"],
                           _RECOVERY_REFERENCE_KEYS, "recovery preflight references")
    specifications = (
        ("pre_census_qualification", backup.PRE_CENSUS_QUALIFICATION_NAME,
         _control_config_profile(guard.control_uid, guard.control_gid)),
        ("pre_census_continuation", backup.PRE_CENSUS_CONTINUATION_NAME,
         _control_profile(guard.control_uid, guard.control_gid)),
    )
    records, payloads, identities = [], [], []
    for role, name, profile in specifications:
        held = guard.hold(_qualify_control_file(
            state_directory / name, role=role, kind="receipt", profile=profile,
            limit=_MAX_RECEIPT_BYTES))
        value = _strict_evidence_json(held.raw, role)
        if not isinstance(value, dict) or backup._upgrade_receipt_bytes(value) != held.raw:
            raise RetainedChainInvalid("recovery origin is not canonical producer bytes")
        held = dataclasses.replace(held, payload=value,
                                   payload_digest=backup._upgrade_digest(value))
        guard.files[-1] = held
        identity = _artifact_reference(held, value)
        ref_key = ("qualification_identity" if role == "pre_census_qualification"
                   else "continuation_identity")
        if refs[ref_key] != identity:
            raise RetainedChainInvalid("recovery preflight origin identity differs")
        records.append(held.origin_record())
        payloads.append(value)
        identities.append(identity)
    qualification, continuation = payloads
    backup._validate_pre_census_qualification(qualification)
    expected_intent_keys = {"schema_version", "operation_id", "original_barrier_identity",
                            "qualification_identity", "recovery_tool", "created_at"}
    _require_closed(continuation, expected_intent_keys, "recovery continuation")
    if (continuation["schema_version"] != backup.PRE_CENSUS_CONTINUATION_SCHEMA
            or continuation["operation_id"] != qualification["operation_id"]
            or continuation["original_barrier_identity"] != qualification["original_barrier"]["identity"]
            or continuation["qualification_identity"] != identities[0]
            or continuation["recovery_tool"] != qualification["recovery_tool"]):
        raise RetainedChainInvalid("one-use recovery continuation binding differs")
    _require_text(continuation["created_at"], "continuation issuance time")
    return {"qualification": qualification, "continuation": continuation,
            "qualification_identity": identities[0], "continuation_identity": identities[1],
            "records": records}


def _validate_pre_census_reconciliation(recovery, receipts, pairs, chain,
                                       runtime_root, backup_root, control_uid, control_gid):
    """Join historical Root qualification to genuine source backup and executors.

    This is immutable provenance validation in both phases. It does not infer
    the original failed process's phase or read the present authoritative DB.
    """
    if recovery.get("spent_ctime") is True:
        return _validate_spent_ctime_reconciliation(recovery, receipts, pairs, chain,
            runtime_root, backup_root, control_uid, control_gid)
    qualification = recovery["qualification"]
    preflight = receipts["P56"][0]
    original = qualification["original_barrier"]
    if (qualification["operation_id"] != preflight["operation_id"]
            or original["identity"] != preflight["barrier_identity"]
            or original["payload"]["created_at"] != preflight["created_at"]
            or original["payload"]["database_path"] != chain["database_path"]
            or qualification["host"] != {"runtime_root": str(runtime_root),
                                         "backup_root": str(backup_root),
                                         "control_uid": control_uid, "control_gid": control_gid}
            or qualification["recovery_tool"] != chain["tool_release"]):
        raise RetainedChainInvalid("recovery source, original barrier or executor differs")
    source = qualification["database"]
    if any(source[key] != preflight["database"][key] for key in _DATABASE_KEYS):
        raise RetainedChainInvalid("recovery qualified database differs from migration source")
    verified = pairs["P56"]["verification"]
    if (qualification["full_v5_content_digest"] != chain["original_full_v5_content_digest"]
            or qualification["normalized_schema_digest"] != verified.normalized_schema_digest
            or qualification["migration_vector"] != [row.to_dict() for row in verified.migrations]):
        raise RetainedChainInvalid("recovery Root source proof differs from verified v5 backup")
    if qualification["source_control_config"]["path"] != str(_control_config_path()):
        raise RetainedChainInvalid("recovery qualification names a foreign source config")
    tool = qualification["original_tool"]
    if (tool["root"] != original["payload"]["tool_release_root"]
            or tool["sha"] != original["payload"]["release_sha"]
            or tool["tree_sha"] != original["payload"]["tool_release_tree_sha"]
            or tool["manifest_sha256"] != original["payload"]["tool_release_manifest_sha256"]):
        raise RetainedChainInvalid("recovery original tool differs from its retained barrier")
    verified_tool = _verify_pinned_release(Path(tool["root"]), tool["sha"], tool["tree_sha"])
    if (verified_tool.get("commit_sha") != tool["sha"]
            or verified_tool.get("tree_sha") != tool["tree_sha"]
            or verified_tool.get("manifest_sha256") != tool["manifest_sha256"]):
        raise RetainedChainInvalid("recovery original tool seal differs")
    return {"original_tool": dict(tool), "original_barrier": dict(original),
            "qualification_identity": recovery["qualification_identity"],
            "continuation_identity": recovery["continuation_identity"]}


def _load_spent_ctime_reconciliation(guard, preflight, state_directory):
    """Load exactly four immutable authority origins; no current-state adoption."""
    refs = _require_closed(preflight["pre_census_reconciliation"],
                           _SPENT_CTIME_REFERENCE_KEYS, "spent ctime references")
    specifications = (
        ("pre_census_qualification", backup.PRE_CENSUS_QUALIFICATION_NAME,
         "qualification_identity", True),
        ("spent_pre_census_continuation", backup.PRE_CENSUS_CONTINUATION_NAME,
         "spent_continuation_identity", False),
        ("spent_pre_census_ctime_reconciliation", backup.SPENT_PRE_CENSUS_CTIME_RECONCILIATION_NAME,
         "reconciliation_identity", True),
        ("spent_pre_census_ctime_continuation", backup.SPENT_PRE_CENSUS_CTIME_CONTINUATION_NAME,
         "continuation_identity", False))
    records, payloads, identities = [], [], {}
    for role, name, ref, root_owned in specifications:
        profile = (_control_config_profile(guard.control_uid, guard.control_gid)
                   if root_owned else _control_profile(guard.control_uid, guard.control_gid))
        held = guard.hold(_qualify_control_file(state_directory / name,
            role=role, kind="receipt", profile=profile, limit=_MAX_RECEIPT_BYTES))
        value = _strict_evidence_json(held.raw, role)
        if not isinstance(value, dict) or backup._upgrade_receipt_bytes(value) != held.raw:
            raise RetainedChainInvalid("spent ctime origin is not canonical producer bytes")
        held = dataclasses.replace(held, payload=value, payload_digest=backup._upgrade_digest(value))
        guard.files[-1] = held
        identity = _artifact_reference(held, value)
        if refs[ref] != identity:
            raise RetainedChainInvalid("spent ctime preflight origin differs")
        identities[ref] = identity
        records.append(held.origin_record()); payloads.append(value)
    qualification, spent, reconciliation, continuation = payloads
    original = qualification.get("original_barrier", {})
    backup._validate_spent_pre_census_ctime_reconciliation(reconciliation,
        barrier_payload=original.get("payload"), barrier_identity=original.get("identity"),
        qualification_payload=qualification, qualification_identity=identities["qualification_identity"],
        spent_continuation_payload=spent, spent_continuation_identity=identities["spent_continuation_identity"])
    expected = dict(schema_version=backup.SPENT_PRE_CENSUS_CTIME_CONTINUATION_SCHEMA,
        operation_id=qualification["operation_id"], original_barrier_identity=original["identity"],
        qualification_identity=identities["qualification_identity"],
        spent_continuation_identity=identities["spent_continuation_identity"],
        reconciliation_identity=identities["reconciliation_identity"],
        recovery_tool=reconciliation["recovery_tool"], created_at=continuation.get("created_at"))
    if continuation != expected:
        raise RetainedChainInvalid("spent ctime one-use continuation binding differs")
    backup._pre_census_time(continuation.get("created_at"))
    return dict(spent_ctime=True, qualification=qualification, spent_continuation=spent,
                reconciliation=reconciliation, continuation=continuation,
                records=records, **identities)


def _validate_spent_ctime_reconciliation(recovery, receipts, pairs, chain,
                                        runtime_root, backup_root, control_uid, control_gid):
    """Immutable sixteen-origin history; never infer a checkpoint phase."""
    q, r = recovery["qualification"], recovery["reconciliation"]
    p = receipts["P56"][0]
    original = q["original_barrier"]
    if (p["schema_version"] != _SPENT_CTIME_PREFLIGHT_SCHEMA
            or q["operation_id"] != p["operation_id"]
            or p["barrier_identity"] != original["identity"]
            or p["created_at"] != original["payload"]["created_at"]
            or original["payload"]["database_path"] != chain["database_path"]
            or q["host"] != dict(runtime_root=str(runtime_root), backup_root=str(backup_root),
                                control_uid=control_uid, control_gid=control_gid)
            or r["recovery_tool"] != chain["tool_release"]
            or any(r["database"][key] != p["database"][key] for key in _DATABASE_KEYS)):
        raise RetainedChainInvalid("spent ctime source, host, barrier or executor differs")
    verified = pairs["P56"]["verification"]
    if (q["full_v5_content_digest"] != chain["original_full_v5_content_digest"]
            or q["normalized_schema_digest"] != verified.normalized_schema_digest
            or q["migration_vector"] != [row.to_dict() for row in verified.migrations]
            or q["source_control_config"]["path"] != str(_control_config_path())):
        raise RetainedChainInvalid("spent ctime source backup or config origin differs")
    old = q["original_tool"]
    if old != dict(root=original["payload"]["tool_release_root"],
                   sha=original["payload"]["release_sha"],
                   tree_sha=original["payload"]["tool_release_tree_sha"],
                   manifest_sha256=original["payload"]["tool_release_manifest_sha256"]):
        raise RetainedChainInvalid("spent ctime original tool differs from barrier")
    # The original barrier executor and the spent executor remain separately
    # sealed.  Neither is relabelled as the actual current migration executor.
    for tool in (old, q["recovery_tool"]):
        seal = _verify_pinned_release(Path(tool["root"]), tool["sha"], tool["tree_sha"])
        if any(seal.get(key) != tool[field] for key, field in (
                ("commit_sha", "sha"), ("tree_sha", "tree_sha"), ("manifest_sha256", "manifest_sha256"))):
            raise RetainedChainInvalid("spent ctime historical executor seal differs")
    return dict(original_tool=dict(old), original_barrier=dict(original),
                **{key: recovery[key] for key in _SPENT_CTIME_REFERENCE_KEYS})


def _normalize_drill(drill: Mapping[str, Any]) -> dict[str, Any]:
    """Detach the drill wire into plain JSON data with no tuple residue."""
    value = dict(drill)
    if set(value) != set(_DRILL_KEYS):
        raise RetainedChainInvalid("restore drill is not the closed receipt")
    value["migration_versions"] = [int(item) for item in value["migration_versions"]]
    return value


def _verify_retained_backup(
    guard: _EvidenceGuard,
    *,
    label: str,
    database_role: str,
    manifest_role: str,
    record: Mapping[str, Any],
    version: int,
    record_keys: frozenset[str],
    backup_root: Path,
) -> dict[str, Any]:
    record = _require_closed(record, record_keys, f"{label} backup record")
    database_path = Path(_require_text(record["database_path"], f"{label} database path"))
    manifest_path = Path(_require_text(record["manifest_path"], f"{label} manifest path"))
    if not database_path.is_absolute() or not manifest_path.is_absolute():
        raise EvidenceCustodyError(f"{label} backup paths must be absolute")
    if manifest_path != database_path.with_suffix(".manifest.json"):
        raise EvidenceCustodyError(f"{label} manifest is not the database twin")
    _require_within_root(database_path, backup_root, label=f"{label} database")
    _require_within_root(manifest_path, backup_root, label=f"{label} manifest")
    _require_no_sidecars(database_path, label=f"{label} retained backup")
    held_database = guard.hold(
        _qualify_control_file(
            database_path,
            role=database_role,
            kind="database",
            profile=_control_profile(guard.control_uid, guard.control_gid),
            limit=_MAX_DATABASE_BYTES,
        )
    )
    held_manifest = guard.hold(
        _qualify_control_file(
            manifest_path,
            role=manifest_role,
            kind="manifest",
            profile=_control_profile(guard.control_uid, guard.control_gid),
            limit=_MAX_RECEIPT_BYTES,
        )
    )
    for path in (database_path, manifest_path):
        _validate_namespace(
            path.parent,
            protected_root=backup_root,
            control_uid=guard.control_uid,
            held_dirs=guard.dirs,
        )
    guard.backup_databases.add(database_path)
    directory = guard.temp_directory()
    copy_database = _copy_descriptor_to_temp(
        held_database.descriptor,
        directory / database_path.name,
        expected_sha256=held_database.sha256,
    )
    copy_manifest = _copy_descriptor_to_temp(
        held_manifest.descriptor,
        directory / manifest_path.name,
        expected_sha256=held_manifest.sha256,
    )
    verification = backup.verify_backup(
        copy_database, copy_manifest, expected_schema_version=version
    )
    drill = _normalize_drill(
        backup.verify_restore_drill(
            copy_database, copy_manifest, expected_schema_version=version
        ).to_dict()
    )
    if verification.database_sha256 != held_database.sha256:
        raise RetainedChainInvalid(f"{label} backup copy hash differs from its original")
    if _require_hex(record["database_sha256"], f"{label} database sha256") != (
        verification.database_sha256
    ):
        raise RetainedChainInvalid(f"{label} backup hash differs from its receipt")
    if _require_hex(record["manifest_sha256"], f"{label} manifest sha256") != (
        verification.manifest_sha256
    ):
        raise RetainedChainInvalid(f"{label} manifest hash differs from its receipt")
    if backup._upgrade_digest(drill) != _require_hex(
        record["restore_drill_digest"], f"{label} drill digest"
    ):
        raise RetainedChainInvalid(f"{label} restore drill digest differs from receipt")
    if drill["database_sha256"] != verification.database_sha256:
        raise RetainedChainInvalid(f"{label} drill and backup hashes differ")
    with backup._readonly_database(copy_database) as connection:
        facts: dict[str, Any] = {
            "legacy_content_digest": backup.legacy_content_digest(
                connection, expected_schema_version=version
            ),
            "full_v4_content_digest": backup.full_v4_content_digest(connection),
            "full_v5_content_digest": backup.full_v5_content_digest(connection),
            "migration5_receipt_digest": _migration5_receipt_digest(connection),
        }
        if version >= 6:
            facts["full_v6_content_digest"] = backup.full_v6_content_digest(connection)
        if version >= 7:
            facts["physical_history_digest"] = backup.physical_history_digest(connection)
            facts["initial_physical_history"] = _require_initial_physical_history(
                connection
            )
    return {
        "label": label,
        "version": version,
        "verification": verification,
        "drill": drill,
        "facts": facts,
        "copy": copy_database,
        "database_identity": held_database.origin_record(),
        "manifest_identity": held_manifest.origin_record(),
    }


def _validate_retained_producer_evidence(
    receipts: Mapping[str, tuple[dict[str, Any], str]],
    pairs: Mapping[str, dict[str, Any]],
    *, database: Path, control_uid: int,
    recovered_barrier: Mapping[str, Any] | None = None,
) -> None:
    """Validate retained producer DATA without invoking its effectful observer.

    The original upgrader PID and lock FD are retained historical identities;
    they are neither the current Root process nor a grant to act as that process.
    Each transition owns its own identities, which may differ between steps.
    """
    for role, field in (("P56", "v5_backup"), ("C56", "v6_backup"),
                        ("P67", "v6_backup"), ("C67", "v7_backup")):
        record = receipts[role][0][field]
        retained = _require_closed(record["restore_drill_receipt"], _DRILL_KEYS,
                                   f"{role} retained restore drill")
        if backup._canonical_bytes(retained) != backup._canonical_bytes(pairs[role]["drill"]):
            raise RetainedChainInvalid(f"{role} retained restore drill differs from recomputation")
        for key in ("full_v4_content_digest", "full_v6_content_digest", "physical_history_digest"):
            if key in record and record[key] != pairs[role]["facts"][key]:
                raise RetainedChainInvalid(f"{role} backup {key} differs from recomputation")
    lock = database.parent / backup.DEFAULT_SERVICE_LOCK_NAME
    barrier = database.parent / backup._UPGRADE_BARRIER_NAME
    expected_paths = [str(database), *(str(database.with_name(database.name + suffix))
                        for suffix in _SIDE_CAR_SUFFIXES), str(lock), str(barrier)]
    for role in ("P56", "P67"):
        payload = receipts[role][0]
        if payload["normalized_schema_digest"] != pairs[role]["verification"].normalized_schema_digest:
            raise RetainedChainInvalid(f"{role} schema digest differs from recomputation")
        recovered_census = role == "P56" and recovered_barrier is not None
        census = _require_closed(payload["quiesce_writer_census"], frozenset({
            "schema_version", "control_uids", "upgrader_pid", "inspected_paths",
            "process_sensor", "file_sensor", "processes", "open_files"}), f"{role} census")
        pid = _require_int(census["upgrader_pid"], "retained census upgrader PID", minimum=1)
        process_sensor = _require_closed(census["process_sensor"], frozenset({
            "binary", "upgrader_observed", "sensor_child_observed"}), "census process sensor")
        file_sensor = _require_closed(census["file_sensor"], frozenset({
            "binary", "held_lock_observed"}), "census file sensor")
        expected_census_schema = (backup.PRE_CENSUS_CENSUS_SCHEMA if recovered_census
                                  else backup.UPGRADE_CENSUS_SCHEMA)
        if (census["schema_version"] != expected_census_schema
                or type(census["control_uids"]) is not list
                or census["control_uids"] != [control_uid]
                or any(type(uid) is not int for uid in census["control_uids"])
                or census["inspected_paths"] != expected_paths
                or type(census["processes"]) is not list or census["processes"] != []
                or process_sensor["binary"] != "/bin/ps"
                or process_sensor["upgrader_observed"] is not True
                or process_sensor["sensor_child_observed"] is not True
                or file_sensor["binary"] != "/usr/sbin/lsof"
                or file_sensor["held_lock_observed"] is not True
                or type(census["open_files"]) is not list
                or len(census["open_files"]) != (3 if recovered_census else 1)):
            raise RetainedChainInvalid(f"{role} retained census is adverse or inconsistent")
        paths, descriptors = [], []
        for row in census["open_files"]:
            row = _require_closed(row, frozenset({"pid", "uid", "fd", "path"}),
                                  "census original retained descriptor")
            if (type(row["pid"]) is not int or row["pid"] != pid
                    or type(row["uid"]) is not int or row["uid"] != control_uid
                    or not isinstance(row["fd"], str)
                    or re.fullmatch(r"[0-9]+", row["fd"]) is None):
                raise RetainedChainInvalid(f"{role} retained census descriptor binding differs")
            paths.append(row["path"])
            descriptors.append(int(row["fd"]))
        expected_open_paths = [str(lock), str(barrier), str(database)] if recovered_census else [str(lock)]
        if (sorted(paths) != sorted(expected_open_paths)
                or len(set(descriptors)) != len(descriptors)
                or (recovered_census and descriptors != sorted(descriptors))):
            raise RetainedChainInvalid(f"{role} retained census paths or descriptors differ")
        original_barrier = {
            "schema_version": backup.UPGRADE_BARRIER_SCHEMA,
            "operation_id": payload["operation_id"], "database_path": str(database),
            "tool_release_root": payload["tool_release_root"],
            "tool_release_tree_sha": payload["tool_release_tree_sha"],
            "tool_release_manifest_sha256": payload["tool_release_manifest_sha256"],
            "release_sha": payload["release_sha"], "control_uid": control_uid,
            "created_at": payload["created_at"],
        }
        if role == "P56" and recovered_barrier is not None:
            original_barrier = dict(recovered_barrier)
            if (original_barrier["operation_id"] != payload["operation_id"]
                    or original_barrier["created_at"] != payload["created_at"]
                    or original_barrier["database_path"] != str(database)
                    or original_barrier["control_uid"] != control_uid):
                raise RetainedChainInvalid("recovered original barrier lineage differs")
        raw = backup._upgrade_receipt_bytes(original_barrier)
        identity = _require_closed(payload["barrier_identity"], _BARRIER_IDENTITY_KEYS,
                                   "retained original barrier")
        if (identity["path"] != str(barrier)
                or identity["device"] != payload["database"]["device"]
                or _require_int(identity["inode"], "original barrier inode", minimum=1) < 1
                or identity["size"] != len(raw)
                or identity["sha256"] != hashlib.sha256(raw).hexdigest()
                or identity["payload_digest"] != backup._upgrade_digest(original_barrier)):
            raise RetainedChainInvalid(f"{role} retained original barrier binding differs")


def _require_database_record(value: Any, label: str) -> dict[str, Any]:
    record = _require_closed(value, _DATABASE_KEYS, label)
    _require_text(record["path"], f"{label} path")
    for key in ("device", "inode", "size"):
        _require_int(record[key], f"{label} {key}")
    _require_hex(record["sha256"], f"{label} sha256")
    return record


def _require_tool_release(payload: Mapping[str, Any], label: str) -> dict[str, str]:
    tool = {
        "root": _require_text(payload["tool_release_root"], f"{label} tool root"),
        "sha": _require_hex(payload["release_sha"], f"{label} release sha", length=40),
        "tree_sha": _require_hex(
            payload["tool_release_tree_sha"], f"{label} tool tree sha", length=40
        ),
        "manifest_sha256": _require_hex(
            payload["tool_release_manifest_sha256"],
            f"{label} tool manifest sha256",
        ),
    }
    if not Path(tool["root"]).is_absolute():
        raise RetainedChainInvalid(f"{label} tool release root is not absolute")
    return tool


def _require_receipt_vector(
    payload: Mapping[str, Any], migration_receipts: tuple[Any, ...], label: str
) -> None:
    vector = payload["migration_vector"]
    if not isinstance(vector, list) or vector != [
        item.to_dict() for item in migration_receipts
    ]:
        raise RetainedChainInvalid(f"{label} migration vector differs from the copies")


def _validate_chain(
    *,
    receipts: Mapping[str, tuple[dict[str, Any], str]],
    receipt_identities: Mapping[str, tuple[Path, str]],
    pairs: Mapping[str, dict[str, Any]],
    expected_release: Mapping[str, str] | None,
) -> dict[str, Any]:
    """Fold the four receipts and four verified pairs into chain facts."""
    pre56, digest56 = receipts["P56"]
    c56, _digest_c56 = receipts["C56"]
    p67, digest67 = receipts["P67"]
    c67, _digest_c67 = receipts["C67"]

    if c56["operation_id"] != pre56["operation_id"]:
        raise RetainedChainInvalid("5-to-6 completion operation differs from preflight")
    if c67["operation_id"] != p67["operation_id"]:
        raise RetainedChainInvalid("6-to-7 completion operation differs from preflight")
    if pre56["operation_id"] == p67["operation_id"]:
        raise RetainedChainInvalid("both steps claim one upgrade operation")
    for role, payload, digest in (
        ("C56", c56, digest56),
        ("C67", c67, digest67),
    ):
        if payload["preflight_receipt_digest"] != digest:
            raise RetainedChainInvalid(
                f"{role} preflight digest differs from the retained preflight"
            )
    for payload in (pre56, p67):
        _require_closed(payload["barrier_identity"], _BARRIER_IDENTITY_KEYS, "barrier")
        census = payload["quiesce_writer_census"]
        expected_schema = (backup.PRE_CENSUS_CENSUS_SCHEMA
                           if payload is pre56 and pre56["schema_version"] in {_RECOVERED_PREFLIGHT_SCHEMA, _SPENT_CTIME_PREFLIGHT_SCHEMA}
                           else backup.UPGRADE_CENSUS_SCHEMA)
        if not isinstance(census, Mapping) or census.get("schema_version") != expected_schema:
            raise RetainedChainInvalid("retained preflight census is not the closed wire")
        if backup._upgrade_digest(census) != _require_hex(
            payload["quiesce_writer_census_digest"], "preflight census digest"
        ):
            raise RetainedChainInvalid("retained census digest differs from its census")
    for role, payload, preflight in (
        ("C56", c56, pre56),
        ("C67", c67, p67),
    ):
        if payload["quiesce_writer_census_digest"] != preflight[
            "quiesce_writer_census_digest"
        ]:
            raise RetainedChainInvalid(
                f"{role} census digest differs from its preflight"
            )

    source_record = _require_database_record(pre56["database"], "P56 source database")
    c56_target = _require_database_record(
        c56["authoritative_v6_database"], "C56 authoritative v6 database"
    )
    p67_source = _require_database_record(p67["database"], "P67 source database")
    c67_target = _require_database_record(
        c67["authoritative_v7_database"], "C67 authoritative v7 database"
    )
    canonical_path = source_record["path"]
    if not Path(canonical_path).is_absolute() or (
        canonical_path != c56_target["path"]
        or canonical_path != p67_source["path"]
        or canonical_path != c67_target["path"]
    ):
        raise RetainedChainInvalid("retained chain does not share one canonical database")
    if (c56_target["device"], c56_target["inode"]) != (
        p67_source["device"],
        p67_source["inode"],
    ):
        raise RetainedChainInvalid(
            "C56 authoritative target and P67 source are not the same database object"
        )

    tool = _require_tool_release(pre56, "P56")
    for role, payload in (("C56", c56), ("P67", p67), ("C67", c67)):
        if _require_tool_release(payload, role) != tool:
            raise RetainedChainInvalid(f"{role} binds a different tool release")
    if tool["sha"] != pre56["release_sha"]:
        raise RetainedChainInvalid("preflight release identity is inconsistent")
    if expected_release is not None:
        if (
            tool["root"] != expected_release["release_root"]
            or tool["sha"] != expected_release["release_sha"]
            or tool["tree_sha"] != expected_release["release_tree_sha"]
            or tool["manifest_sha256"] != expected_release["release_manifest_sha256"]
        ):
            raise RetainedChainInvalid(
                "retained tool release differs from the qualified release proof"
            )

    source_facts = pairs["P56"]["facts"]
    full_v4 = source_facts["full_v4_content_digest"]
    legacy = source_facts["legacy_content_digest"]
    original_v5 = source_facts["full_v5_content_digest"]
    m5 = source_facts["migration5_receipt_digest"]
    if full_v4 != _require_hex(
        pre56["full_v4_content_digest"], "P56 full v4 digest"
    ) or full_v4 != _require_hex(c56["pre_full_v4_content_digest"], "C56 pre full v4"):
        raise RetainedChainInvalid("original full-v4 digest differs from its receipts")
    if m5 != _require_hex(
        pre56["v5_migration_receipt_digest"], "P56 migration-5 digest"
    ) or m5 != _require_hex(
        c56["pre_v5_migration_receipt_digest"], "C56 pre migration-5 digest"
    ):
        raise RetainedChainInvalid("migration-5 receipt digest differs from its receipts")
    for role in ("C56", "P67", "C67"):
        facts = pairs[role]["facts"]
        if facts["full_v4_content_digest"] != full_v4:
            raise RetainedChainInvalid(f"{role} did not preserve full-v4 content")
        if facts["full_v5_content_digest"] != original_v5:
            raise RetainedChainInvalid(f"{role} did not preserve full-v5 content")
        if facts["migration5_receipt_digest"] != m5:
            raise RetainedChainInvalid(f"{role} did not preserve the migration-5 receipt")
        if facts["legacy_content_digest"] != legacy:
            raise RetainedChainInvalid(f"{role} did not preserve legacy content")
    if legacy != _require_hex(
        c56["pre_v4_legacy_content_digest"], "C56 pre legacy digest"
    ) or legacy != _require_hex(
        c56["post_v4_legacy_content_digest"], "C56 post legacy digest"
    ):
        raise RetainedChainInvalid("C56 legacy digest differs from the verified copies")
    if legacy != _require_hex(
        c67["pre_v6_legacy_content_digest"], "C67 pre legacy digest"
    ) or legacy != _require_hex(
        c67["post_v6_legacy_content_digest"], "C67 post legacy digest"
    ):
        raise RetainedChainInvalid("C67 legacy digest differs from the verified copies")
    if c56["full_v4_content_equal"] is not True or c56["legacy_content_equal"] is not True:
        raise RetainedChainInvalid("C56 does not attest equal preserved content")
    if c67["full_v6_content_equal"] is not True or c67["legacy_content_equal"] is not True:
        raise RetainedChainInvalid("C67 does not attest equal preserved content")
    if c67["initial_physical_tables_empty"] is not True:
        raise RetainedChainInvalid("C67 does not attest the initial empty physical state")

    intermediate_v6 = pairs["C56"]["facts"]["full_v6_content_digest"]
    for role in ("P67", "C67"):
        if pairs[role]["facts"]["full_v6_content_digest"] != intermediate_v6:
            raise RetainedChainInvalid(
                f"{role} does not carry the same retained v6 semantics"
            )
    if intermediate_v6 != _require_hex(
        p67["full_v6_content_digest"], "P67 full v6 digest"
    ):
        raise RetainedChainInvalid("P67 preflight differs from the retained v6 copies")
    if _require_hex(c56["post_full_v4_content_digest"], "C56 post full v4") != full_v4:
        raise RetainedChainInvalid("C56 post full-v4 digest differs from the copies")
    if _require_hex(
        c56["post_v5_migration_receipt_digest"], "C56 post migration-5"
    ) != m5:
        raise RetainedChainInvalid("C56 post migration-5 digest differs from the copies")
    if _require_hex(c67["pre_full_v6_content_digest"], "C67 pre full v6") != (
        intermediate_v6
    ) or _require_hex(c67["post_full_v6_content_digest"], "C67 post full v6") != (
        intermediate_v6
    ):
        raise RetainedChainInvalid("C67 full-v6 digests differ from the verified copies")

    receipt_paths = {role: item[0] for role, item in receipt_identities.items()}
    receipt_shas = {role: item[1] for role, item in receipt_identities.items()}

    if pre56["normalized_schema_digest"] != pairs["P56"]["verification"].normalized_schema_digest:
        raise RetainedChainInvalid("P56 schema digest differs from the verified v5 copy")
    if c56["authoritative_v6_schema_digest"] != pairs["C56"][
        "verification"
    ].normalized_schema_digest:
        raise RetainedChainInvalid("C56 schema digest differs from the verified v6 copy")
    if c67["authoritative_v7_schema_digest"] != pairs["C67"][
        "verification"
    ].normalized_schema_digest:
        raise RetainedChainInvalid("C67 schema digest differs from the verified v7 copy")

    _require_receipt_vector(pre56, pairs["P56"]["verification"].migrations, "P56")
    _require_receipt_vector(c56, pairs["C56"]["verification"].migrations, "C56")
    _require_receipt_vector(p67, pairs["P67"]["verification"].migrations, "P67")
    _require_receipt_vector(c67, pairs["C67"]["verification"].migrations, "C67")
    if c56["migration_vector"] != p67["migration_vector"]:
        raise RetainedChainInvalid("the two retained v6 states carry different vectors")

    initial_physical = pairs["C67"]["facts"]["physical_history_digest"]
    if initial_physical != _require_hex(
        c67["physical_history_digest"], "C67 physical history digest"
    ):
        raise RetainedChainInvalid("C67 physical history differs from the verified copy")
    if pairs["C67"]["facts"]["initial_physical_history"] != initial_physical:
        raise RetainedChainInvalid("initial v7 material is not the empty physical state")

    return {
        "source_schema_version": 5,
        "target_schema_version": 7,
        "database_path": canonical_path,
        "tool_release": tool,
        "step_v5_to_v6": {
            "operation_id": _require_text(pre56["operation_id"], "P56 operation"),
            "preflight": {
                "path": str(receipt_paths["P56"]),
                "sha256": receipt_shas["P56"],
                "payload_digest": digest56,
            },
            "completion": {
                "path": str(receipt_paths["C56"]),
                "sha256": receipt_shas["C56"],
                "payload_digest": _require_hex(
                    receipts["C56"][1], "C56 payload digest"
                ),
            },
        },
        "step_v6_to_v7": {
            "operation_id": _require_text(p67["operation_id"], "P67 operation"),
            "preflight": {
                "path": str(receipt_paths["P67"]),
                "sha256": receipt_shas["P67"],
                "payload_digest": digest67,
            },
            "completion": {
                "path": str(receipt_paths["C67"]),
                "sha256": receipt_shas["C67"],
                "payload_digest": _require_hex(
                    receipts["C67"][1], "C67 payload digest"
                ),
            },
        },
        "full_v4_content_digest": full_v4,
        "legacy_content_digest": legacy,
        "original_full_v5_content_digest": original_v5,
        "preserved_full_v5_content_digest": original_v5,
        "intermediate_full_v6_content_digest": intermediate_v6,
        "initial_v7_full_v6_content_digest": intermediate_v6,
        "initial_v7_physical_history_digest": initial_physical,
        "initial_v7_backup_identity": {
            "database_path": pairs["C67"]["database_identity"]["path"],
            "database_sha256": pairs["C67"]["database_identity"]["sha256"],
            "manifest_path": pairs["C67"]["manifest_identity"]["path"],
            "manifest_sha256": pairs["C67"]["manifest_identity"]["sha256"],
        },
    }


def _qualified_roots_from_config(
    config_value: Mapping[str, Any],
    *,
    runtime_physical: Path,
    backup_physical: Path,
) -> None:
    """The Control config may only confirm the fixed derived host roots."""
    configured_runtime = config_value.get("runtime_root")
    if not isinstance(configured_runtime, str) or not Path(configured_runtime).is_absolute():
        raise EvidenceCustodyError("control config runtime_root is not an absolute path")
    runtime_lexical = Path(os.path.normpath(configured_runtime))
    if runtime_lexical not in _fixed_lexical_variants(runtime_physical) or (
        Path(os.path.realpath(runtime_lexical)) != runtime_physical
    ):
        raise EvidenceCustodyError(
            "control config runtime_root is not the qualified fixed host runtime root"
        )
    configured_backup = config_value.get("backup_root")
    if not isinstance(configured_backup, str) or not Path(configured_backup).is_absolute():
        raise EvidenceCustodyError("control config backup_root is not an absolute path")
    lexical = Path(os.path.normpath(configured_backup))
    if lexical not in _fixed_lexical_variants(backup_physical) or (
        Path(os.path.realpath(lexical)) != backup_physical
    ):
        raise EvidenceCustodyError(
            "control config backup_root is not the qualified fixed host backup "
            "root; an arbitrary alias is refused"
        )
    if backup_physical == runtime_physical or backup_physical.is_relative_to(
        runtime_physical
    ) or runtime_physical.is_relative_to(backup_physical):
        raise EvidenceCustodyError("configured roots must stay disjoint")
    try:
        info = backup_physical.lstat()
    except OSError as exc:
        raise EvidenceCustodyError("configured backup root is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise EvidenceCustodyError("configured backup root is not a real directory")


def _verify_current_initial(
    guard: _EvidenceGuard,
    *,
    runtime_physical: Path,
    state_directory: Path,
    database_path: Path,
    c67: Mapping[str, Any],
) -> dict[str, Any]:
    """Prove the live authoritative v7 store still equals the C67 postimage."""
    if database_path != runtime_physical / _DB_RELATIVE_PATH:
        raise EvidenceCustodyError(
            "retained canonical database escapes the fixed runtime database layout"
        )
    database = database_path
    authoritative = _require_database_record(
        c67["authoritative_v7_database"], "C67 authoritative v7 database"
    )
    if str(database) != authoritative["path"]:
        raise RetainedChainInvalid(
            "INITIAL live database path differs from the retained completion"
        )
    _require_no_sidecars(database, label="authoritative v7 database")
    _require_absent(
        state_directory / backup._UPGRADE_BARRIER_NAME, label="schema upgrade barrier"
    )
    _require_absent(
        state_directory / backup.DEFAULT_SERVICE_MARKER_NAME, label="service marker"
    )
    lock = state_directory / backup.DEFAULT_SERVICE_LOCK_NAME
    guard.hold(
        _qualify_control_file(
            lock,
            role="executive-service.lock",
            kind="lock",
            profile=_control_profile(guard.control_uid, guard.control_gid),
            limit=_MAX_RECEIPT_BYTES,
        )
    )
    _validate_namespace(
        database.parent,
        protected_root=runtime_physical,
        control_uid=guard.control_uid,
        held_dirs=guard.dirs,
    )
    held_database = guard.hold(
        _qualify_control_file(
            database,
            role="authoritative.v7.database",
            kind="database",
            profile=_control_profile(guard.control_uid, guard.control_gid),
            limit=_MAX_DATABASE_BYTES,
        )
    )
    identity = {
        "path": str(database),
        "device": int(held_database.held.st_dev),
        "inode": int(held_database.held.st_ino),
        "size": int(held_database.held.st_size),
        "sha256": held_database.sha256,
    }
    if identity != {key: authoritative[key] for key in (
        "path", "device", "inode", "size", "sha256"
    )}:
        raise RetainedChainInvalid(
            "INITIAL live v7 database differs from the retained completion identity"
        )
    guard.initial_paths_absent = (
        state_directory / backup._UPGRADE_BARRIER_NAME,
        state_directory / backup.DEFAULT_SERVICE_MARKER_NAME,
        database.with_name(database.name + "-wal"),
        database.with_name(database.name + "-shm"),
        database.with_name(database.name + "-journal"),
    )
    copy = _copy_descriptor_to_temp(
        held_database.descriptor,
        guard.temp_directory() / database.name,
        expected_sha256=held_database.sha256,
    )
    verification = backup.verify_backup(copy, expected_schema_version=7)
    with backup._readonly_database(copy) as connection:
        facts = {
            "full_v6_content_digest": backup.full_v6_content_digest(connection),
            "physical_history_digest": backup.physical_history_digest(connection),
            "legacy_content_digest": backup.legacy_content_digest(
                connection, expected_schema_version=7
            ),
        }
    return {
        "copy": copy,
        "identity": identity,
        "verification": verification,
        "facts": facts,
    }


def _validate_pinned_material(pinned: Mapping[str, Any]) -> dict[str, Any]:
    value = _require_closed(pinned, _MATERIAL_KEYS, "pinned material")
    spent_ctime = value["schema_version"] == SPENT_CTIME_MATERIAL_SCHEMA_VERSION
    recovered = value["schema_version"] == RECOVERED_MATERIAL_SCHEMA_VERSION or spent_ctime
    if value["schema_version"] not in {MATERIAL_SCHEMA_VERSION, RECOVERED_MATERIAL_SCHEMA_VERSION,
                                      SPENT_CTIME_MATERIAL_SCHEMA_VERSION}:
        raise RetainedChainInvalid("pinned material schema version is unsupported")
    expected_roles = (_SPENT_CTIME_ROLES if spent_ctime else
                      _RECOVERED_ROLES if recovered else _EXPECTED_ROLES)
    if value["phase"] != EVIDENCE_PHASE_INITIAL:
        raise RetainedChainInvalid("pinned material is not original INITIAL provenance")
    host = _require_closed(value["host"], _HOST_KEYS, "pinned host mapping")
    _require_text(host["runtime_root"], "pinned runtime_root")
    _require_text(host["backup_root"], "pinned backup_root")
    if not Path(host["runtime_root"]).is_absolute() or not Path(
        host["backup_root"]
    ).is_absolute():
        raise RetainedChainInvalid("pinned host mapping paths must be absolute")
    _require_int(host["control_uid"], "pinned control_uid")
    _require_int(host["control_gid"], "pinned control_gid")
    records = value["origin_records"]
    if not isinstance(records, list) or len(records) != len(expected_roles):
        raise RetainedChainInvalid(
            "pinned material does not carry the closed twelve origin records"
        )
    roles: list[str] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise RetainedChainInvalid("pinned origin record is not an object")
        keys = _RECEIPT_ORIGIN_KEYS if record.get("kind") == "receipt" else _ORIGIN_KEYS
        record = _require_closed(record, keys, "pinned origin record")
        _require_text(record["kind"], "origin kind")
        _require_text(record["role"], "origin role")
        _require_text(record["path"], "origin path")
        if not Path(record["path"]).is_absolute():
            raise RetainedChainInvalid("pinned origin path must be absolute")
        for key in (
            "device",
            "inode",
            "size",
            "mode",
            "uid",
            "gid",
            "nlink",
            "mtime_ns",
            "ctime_ns",
        ):
            _require_int(record[key], f"origin {key}")
        _require_hex(record["sha256"], "origin sha256")
        if record["kind"] == "receipt":
            _require_hex(record["payload_digest"], "origin payload digest")
        roles.append(record["role"])
    if sorted(roles) != sorted(expected_roles):
        raise RetainedChainInvalid("pinned origin records are not the closed twelve roles")
    chain = _require_closed(value["chain"], _CHAIN_KEYS | ({"pre_census_reconciliation"} if recovered else set()), "pinned chain")
    if recovered:
        _require_closed(chain["pre_census_reconciliation"], _SPENT_CTIME_CHAIN_KEYS if spent_ctime else _RECOVERY_CHAIN_KEYS, "pinned recovery")
    if chain["source_schema_version"] != 5 or chain["target_schema_version"] != 7:
        raise RetainedChainInvalid("pinned chain does not prove the closed 5-to-7 span")
    _require_text(chain["database_path"], "pinned database path")
    tool = _require_closed(chain["tool_release"], _TOOL_RELEASE_KEYS, "pinned tool release")
    _require_text(tool["root"], "pinned tool root")
    _require_hex(tool["sha"], "pinned tool sha", length=40)
    _require_hex(tool["tree_sha"], "pinned tool tree sha", length=40)
    _require_hex(tool["manifest_sha256"], "pinned tool manifest sha256")
    for step_key in ("step_v5_to_v6", "step_v6_to_v7"):
        step = _require_closed(chain[step_key], _STEP_KEYS, f"pinned {step_key}")
        _require_text(step["operation_id"], f"pinned {step_key} operation")
        for ref_key in ("preflight", "completion"):
            ref = _require_closed(step[ref_key], _RECEIPT_REF_KEYS, f"pinned {ref_key}")
            _require_text(ref["path"], f"pinned {ref_key} path")
            _require_hex(ref["sha256"], f"pinned {ref_key} sha256")
            _require_hex(ref["payload_digest"], f"pinned {ref_key} payload digest")
    for key in (
        "full_v4_content_digest",
        "legacy_content_digest",
        "original_full_v5_content_digest",
        "preserved_full_v5_content_digest",
        "intermediate_full_v6_content_digest",
        "initial_v7_full_v6_content_digest",
        "initial_v7_physical_history_digest",
    ):
        _require_hex(chain[key], f"pinned {key}")
    _require_closed(
        chain["initial_v7_backup_identity"], _BACKUP_IDENTITY_KEYS, "pinned v7 baseline"
    )
    return value


@dataclasses.dataclass(frozen=True)
class V7AcceptanceBackupEvidence:
    """Verified DATA for one exact-v7 acceptance backup under retained custody."""

    database: Path
    verification: dict[str, Any]
    restore_drill: dict[str, Any]
    origin_identities: dict[str, Any]


class RetainedV5ToV7Evidence:
    """Read-only DATA view over one retained v5-to-v7 evidence chain.

    The object is a verification result consumed by the existing actual Root
    Maintenance owner.  It grants no issuance, arm, restore, migration, or
    bypass authority and is never a self-authenticating pass receipt.
    ``phase`` is the runtime observation of this opening; the stable
    ``material`` keeps the pinned provenance phase untouched.
    """

    def __init__(
        self,
        *,
        phase: str,
        guard: _EvidenceGuard,
        material: dict[str, Any],
        source_v5_database: Path,
        source_v5_content_digest: str,
        target_v7_database: Path,
        target_v7_database_identity: dict[str, Any],
        control_config_bytes: bytes,
        control_config_identity: dict[str, Any],
        backup_root: Path,
        pre_census_qualification: dict[str, Any] | None = None,
        prepared_reader_record: dict[str, str] | None = None,
    ) -> None:
        self.phase = phase
        self._prepared_reader_record = dict(prepared_reader_record) if prepared_reader_record is not None else None
        self.pre_census_qualification = (json.loads(json.dumps(pre_census_qualification))
                                         if pre_census_qualification is not None else None)
        self.material = material
        self.source_v5_database = source_v5_database
        self.source_v5_content_digest = source_v5_content_digest
        self.target_v7_database = target_v7_database
        self.target_v7_database_identity = target_v7_database_identity
        self.control_config_bytes = control_config_bytes
        self.control_config_identity = control_config_identity
        self.inventory_additions: dict[str, dict[str, Any]] = dict(
            guard.inventory_additions
        )
        self._guard = guard
        self._backup_root = backup_root

    def check(self) -> dict[str, Any]:
        """Revalidate every retained FD, name, namespace, and hash identity."""
        records = self._guard.check()
        return {
            "phase": self.phase,
            "origin_records": records,
            "inventory_additions": dict(self._guard.inventory_additions),
            "held_files": len(records),
            "held_directories": len(self._guard.dirs),
        }

    def check_prepared_sources(self) -> None:
        """Re-pin the actual reader and original executor at a new-mode write edge."""
        if self._prepared_reader_record is None:
            raise RetainedChainInvalid("prepared successor source proof is unavailable")
        if _prove_current_release(self._prepared_reader_record["release_sha"]) != self._prepared_reader_record:
            raise RetainedChainInvalid("prepared successor reader source changed")
        tool = self.material["chain"]["tool_release"]
        seal = _verify_pinned_release(Path(tool["root"]), tool["sha"], tool["tree_sha"])
        if any(seal.get(key) != tool[field] for key, field in (
                ("commit_sha", "sha"), ("tree_sha", "tree_sha"), ("manifest_sha256", "manifest_sha256"))):
            raise RetainedChainInvalid("prepared successor migration source changed")

    def verify_v7_acceptance_backup(
        self,
        database_name: str,
        expected_database_sha256: str,
        expected_manifest_sha256: str,
    ) -> V7AcceptanceBackupEvidence:
        """Verify one exact-v7 acceptance pair from the qualified backup root.

        The pair is qualified and rechecked under its own held custody, but it
        never enters the frozen eight-entry inventory additions and never
        mutates the stable material.
        """
        name = _validate_acceptance_name(database_name)
        _require_hex(expected_database_sha256, "expected database sha256")
        _require_hex(expected_manifest_sha256, "expected manifest sha256")
        database_path = self._backup_root / name
        manifest_path = database_path.with_suffix(".manifest.json")
        if manifest_path == database_path:
            raise EvidenceCustodyError("v7 acceptance manifest is not a sibling file")
        _require_within_root(
            database_path, self._backup_root, label="v7 acceptance database"
        )
        _require_within_root(
            manifest_path, self._backup_root, label="v7 acceptance manifest"
        )
        _require_no_sidecars(database_path, label="v7 acceptance backup")
        held_database = self._guard.hold(
            _qualify_control_file(
                database_path,
                role=f"v7-acceptance.{name}",
                kind="database",
                profile=_control_profile(
                    self._guard.control_uid, self._guard.control_gid
                ),
                limit=_MAX_DATABASE_BYTES,
            )
        )
        held_manifest = self._guard.hold(
            _qualify_control_file(
                manifest_path,
                role=f"v7-acceptance.{manifest_path.name}",
                kind="manifest",
                profile=_control_profile(
                    self._guard.control_uid, self._guard.control_gid
                ),
                limit=_MAX_RECEIPT_BYTES,
            )
        )
        for path in (database_path, manifest_path):
            _validate_namespace(
                path.parent,
                protected_root=self._backup_root,
                control_uid=self._guard.control_uid,
                held_dirs=self._guard.dirs,
            )
        self._guard.backup_databases.add(database_path)
        directory = self._guard.temp_directory()
        copy_database = _copy_descriptor_to_temp(
            held_database.descriptor,
            directory / database_path.name,
            expected_sha256=held_database.sha256,
        )
        _copy_descriptor_to_temp(
            held_manifest.descriptor,
            directory / manifest_path.name,
            expected_sha256=held_manifest.sha256,
        )
        verification = backup.verify_backup(
            copy_database, directory / manifest_path.name, expected_schema_version=7
        )
        if verification.database_sha256 != expected_database_sha256:
            raise RetainedChainInvalid(
                "v7 acceptance database hash differs from the expected identity"
            )
        if verification.manifest_sha256 != expected_manifest_sha256:
            raise RetainedChainInvalid(
                "v7 acceptance manifest hash differs from the expected identity"
            )
        drill = _normalize_drill(
            backup.verify_restore_drill(
                copy_database, directory / manifest_path.name, expected_schema_version=7
            ).to_dict()
        )
        # Recheck the complete retained namespace before exposing new DATA.
        self._guard.check()
        return V7AcceptanceBackupEvidence(
            database=copy_database,
            verification=verification.to_dict(),
            restore_drill=drill,
            origin_identities={
                "database": held_database.identity_record(),
                "manifest": held_manifest.identity_record(),
            },
        )


def _validate_acceptance_name(database_name: str) -> str:
    if not isinstance(database_name, str):
        raise EvidenceCustodyError("v7 acceptance database name must be a string")
    if (
        _ACCEPTANCE_DATABASE_RE.fullmatch(database_name) is None
        or not database_name.endswith(".sqlite3")
        or len(database_name) > 128
    ):
        raise EvidenceCustodyError(
            "v7 acceptance database name is not a strict simple sqlite3 basename"
        )
    return database_name


def _open_chain_evidence(
    runtime_root: Path, expected_release_sha: str, pinned_material: Mapping[str, Any] | None,
    *, _prepared_reader_sha: str | None = None,
    _prepared_material: Mapping[str, Any] | None = None,
) -> RetainedV5ToV7Evidence:
    if not isinstance(expected_release_sha, str) or _SHA_RE.fullmatch(
        expected_release_sha
    ) is None:
        raise SchemaUpgradeEvidenceError(
            "expected_release_sha must be an exact lowercase 40-hex Git SHA"
        )
    phase = (
        EVIDENCE_PHASE_HISTORICAL
        if pinned_material is not None
        else EVIDENCE_PHASE_INITIAL
    )
    pinned = (
        _validate_pinned_material(pinned_material)
        if pinned_material is not None
        else None
    )
    if (_prepared_reader_sha is None) != (_prepared_material is None):
        raise RetainedChainInvalid("prepared successor inputs must be complete")
    prepared = _validate_pinned_material(_prepared_material) if _prepared_material is not None else None
    if prepared is not None and (pinned_material is not None
            or prepared["schema_version"] != SPENT_CTIME_MATERIAL_SCHEMA_VERSION
            or prepared["chain"]["tool_release"]["sha"] != expected_release_sha
            or _prepared_reader_sha == expected_release_sha):
        raise RetainedChainInvalid("prepared successor requires distinct INITIAL sixteen-origin provenance")
    _root_darwin_gate()
    control_uid, control_gid = _control_identity()
    guard = _EvidenceGuard(control_uid, control_gid)
    # Every failure from here on must release every already-held descriptor
    # and private temporary copy before the error reaches the caller.
    try:
        runtime_physical, backup_physical = _host_layout()
        guard.host_roots = (runtime_physical, backup_physical)
        guard.system_alias_identity = _system_alias_identity(runtime_physical)
        _resolve_runtime_root_argument(
            runtime_root,
            runtime_physical=runtime_physical,
            control_uid=control_uid,
            guard=guard,
        )
        _validate_namespace(
            backup_physical,
            protected_root=backup_physical,
            control_uid=control_uid,
            held_dirs=guard.dirs,
        )
        config_path = _control_config_path()
        _validate_namespace(
            config_path.parent, protected_root=config_path.parent,
            control_uid=control_uid, held_dirs=guard.dirs,
            directory_profile=_config_namespace_profile(),
        )
        # Prove a nonblocking regular-file descriptor before the unchanged
        # Root JSON reader opens the fixed name. Never block on a FIFO/device.
        try:
            held_config = guard.hold(
                _qualify_control_file(
                    config_path, role="control.config", kind="config",
                    profile=_control_config_profile(control_uid, control_gid),
                    limit=_MAX_CONFIG_BYTES,
                )
            )
        except EvidenceCustodyError as exc:
            raise EvidenceCustodyError("qualified control config custody refused") from exc
        try:
            config_value, config_raw = _read_qualified_control_config(
                config_path, control_gid=control_gid
            )
        except autonomy_control.HostControlError as exc:
            raise EvidenceCustodyError(
                "qualified control config custody refused"
            ) from exc
        _qualified_roots_from_config(
            config_value,
            runtime_physical=runtime_physical,
            backup_physical=backup_physical,
        )
        if held_config.sha256 != hashlib.sha256(config_raw).hexdigest():
            raise EvidenceCustodyError("qualified control config changed during opening")

        expected_release: dict[str, str] | None = None
        prepared_reader_record = None
        if phase == EVIDENCE_PHASE_INITIAL:
            if prepared is None:
                expected_release = _prove_current_release(expected_release_sha)
            else:
                # Reader identity is an independent actual running-code proof.
                # The immutable migration executor is neither rewritten nor
                # substituted for this source-origin check.
                prepared_reader_record = _prove_current_release(_prepared_reader_sha)
                tool = prepared["chain"]["tool_release"]
                seal = _verify_pinned_release(Path(tool["root"]), tool["sha"], tool["tree_sha"])
                if any(seal.get(key) != tool[field] for key, field in (
                        ("commit_sha", "sha"), ("tree_sha", "tree_sha"),
                        ("manifest_sha256", "manifest_sha256"))):
                    raise RetainedChainInvalid("prepared migration executor seal differs")
                expected_release = dict(release_root=tool["root"], release_sha=tool["sha"],
                    release_tree_sha=tool["tree_sha"], release_manifest_sha256=tool["manifest_sha256"])

        db_path = runtime_physical / _DB_RELATIVE_PATH
        state_directory = db_path.parent
        receipt_identities: dict[str, tuple[Path, str]] = {}
        receipt_records: dict[str, dict[str, Any]] = {}
        receipts: dict[str, tuple[dict[str, Any], str]] = {}
        receipt_specs = (
            ("P56", backup._UPGRADE_V5_TO_V6_PREFLIGHT_NAME,
             backup.UPGRADE_PREFLIGHT_SCHEMA, 5, 6),
            ("C56", backup._UPGRADE_V5_TO_V6_COMPLETION_NAME,
             backup.UPGRADE_COMPLETION_SCHEMA, 5, 6),
            ("P67", backup._UPGRADE_V6_TO_V7_PREFLIGHT_NAME,
             backup.UPGRADE_PREFLIGHT_SCHEMA, 6, 7),
            ("C67", backup._UPGRADE_V6_TO_V7_COMPLETION_NAME,
             backup.UPGRADE_COMPLETION_SCHEMA, 6, 7),
        )
        for role, name, schema, source_version, target_version in receipt_specs:
            path = state_directory / name
            held, payload, digest = _load_receipt(
                guard,
                path,
                role=role,
                schema=schema,
                source_version=source_version,
                target_version=target_version,
                protected_root=runtime_physical,
            )
            held = dataclasses.replace(held, payload=payload, payload_digest=digest)
            guard.files[-1] = held
            receipts[role] = (payload, digest)
            receipt_records[role] = held.origin_record()
            receipt_identities[role] = (path, held.sha256)

        recovery = _load_pre_census_reconciliation(guard, receipts["P56"][0], state_directory)

        pair_specs = (
            ("P56", "v5_backup", 5, _BACKUP_V5_KEYS,
             "v5_backup_database", "v5_backup_manifest"),
            ("C56", "v6_backup", 6, _BACKUP_V4DIGEST_KEYS,
             "c56_v6_backup_database", "c56_v6_backup_manifest"),
            ("P67", "v6_backup", 6, _BACKUP_V6_KEYS,
             "p67_v6_backup_database", "p67_v6_backup_manifest"),
            ("C67", "v7_backup", 7, _BACKUP_V7_KEYS,
             "v7_backup_database", "v7_backup_manifest"),
        )
        pairs: dict[str, dict[str, Any]] = {}
        for receipt_role, field, version, keys, database_role, manifest_role in pair_specs:
            pairs[receipt_role] = _verify_retained_backup(
                guard,
                label=f"{receipt_role}.{field}",
                database_role=database_role,
                manifest_role=manifest_role,
                record=receipts[receipt_role][0][field],
                version=version,
                record_keys=keys,
                backup_root=backup_physical,
            )

        chain = _validate_chain(
            receipts=receipts,
            receipt_identities=receipt_identities,
            pairs=pairs,
            expected_release=expected_release,
        )
        if recovery is not None:
            chain["pre_census_reconciliation"] = _validate_pre_census_reconciliation(
                recovery, receipts, pairs, chain, runtime_physical, backup_physical,
                control_uid, control_gid)
        if Path(chain["database_path"]) != db_path:
            raise RetainedChainInvalid(
                "retained chain does not name the fixed authoritative database layout"
            )
        _validate_retained_producer_evidence(
            receipts, pairs, database=db_path, control_uid=control_uid,
            recovered_barrier=(recovery["qualification"]["original_barrier"]["payload"]
                               if recovery is not None else None),
        )
        if chain["tool_release"]["sha"] != expected_release_sha:
            raise RetainedChainInvalid("retained tool release differs from expected SHA")
        if phase == EVIDENCE_PHASE_HISTORICAL:
            tool = chain["tool_release"]
            verified_release = _verify_pinned_release(
                Path(tool["root"]), tool["sha"], tool["tree_sha"]
            )
            if (
                not isinstance(verified_release, Mapping)
                or verified_release.get("commit_sha") != tool["sha"]
                or verified_release.get("tree_sha") != tool["tree_sha"]
                or verified_release.get("manifest_sha256") != tool["manifest_sha256"]
            ):
                raise RetainedChainInvalid(
                    "retained tool release does not verify against its retained manifest"
                )

        guard.inventory_paths = {
            item.path: item.sha256
            for item in guard.files
            if item.path.is_relative_to(backup_physical)
        }
        guard.inventory_additions = _inventory_records(
            backup_physical, guard.inventory_paths
        )

        if phase == EVIDENCE_PHASE_INITIAL:
            current = _verify_current_initial(
                guard,
                runtime_physical=runtime_physical,
                state_directory=state_directory,
                database_path=db_path,
                c67=receipts["C67"][0],
            )
            target_copy = current["copy"]
            target_identity = current["identity"]
            if current["facts"]["full_v6_content_digest"] != chain[
                "intermediate_full_v6_content_digest"
            ] or current["facts"]["physical_history_digest"] != chain[
                "initial_v7_physical_history_digest"
            ]:
                raise RetainedChainInvalid(
                    "INITIAL live v7 semantics differ from the retained completion"
                )
        else:
            target_copy = pairs["C67"]["copy"]
            target_identity = {
                key: receipts["C67"][0]["authoritative_v7_database"][key]
                for key in ("path", "device", "inode", "size", "sha256")
            }

        host = {
            "runtime_root": str(runtime_physical),
            "backup_root": str(backup_physical),
            "control_uid": control_uid,
            "control_gid": control_gid,
        }
        spent_ctime = recovery is not None and recovery.get("spent_ctime") is True
        expected_roles = (_SPENT_CTIME_ROLES if spent_ctime else
                          _RECOVERED_ROLES if recovery is not None else _EXPECTED_ROLES)
        order = {role: index for index, role in enumerate(expected_roles)}
        origin_records = sorted(
            [
                *receipt_records.values(),
                *(recovery["records"] if recovery is not None else []),
                pairs["P56"]["database_identity"],
                pairs["P56"]["manifest_identity"],
                pairs["C56"]["database_identity"],
                pairs["C56"]["manifest_identity"],
                pairs["P67"]["database_identity"],
                pairs["P67"]["manifest_identity"],
                pairs["C67"]["database_identity"],
                pairs["C67"]["manifest_identity"],
            ],
            key=lambda record: order[record["role"]],
        )
        # The stable material keeps the pinned provenance phase; the runtime
        # phase of this opening is carried separately on the evidence object.
        material_phase = pinned["phase"] if pinned is not None else EVIDENCE_PHASE_INITIAL
        material = {
            "schema_version": (SPENT_CTIME_MATERIAL_SCHEMA_VERSION if spent_ctime else
                               RECOVERED_MATERIAL_SCHEMA_VERSION if recovery is not None
                               else MATERIAL_SCHEMA_VERSION),
            "phase": material_phase,
            "host": host,
            "origin_records": origin_records,
            "chain": chain,
        }
        if pinned is not None and material != dict(pinned):
            raise RetainedChainInvalid(
                "retained evidence does not match the exact pinned material"
            )

        if prepared is not None and material != prepared:
            raise RetainedChainInvalid("prepared successor INITIAL evidence differs from the sealed preparation")

        # Later verification may have raced an earlier retained origin.  Never
        # expose qualified DATA before the full held-custody recheck succeeds.
        guard.check()
        return RetainedV5ToV7Evidence(
            phase=phase,
            guard=guard,
            material=material,
            source_v5_database=pairs["P56"]["copy"],
            source_v5_content_digest=chain["original_full_v5_content_digest"],
            target_v7_database=target_copy,
            target_v7_database_identity=target_identity,
            control_config_bytes=config_raw,
            control_config_identity=held_config.identity_record(),
            backup_root=backup_physical,
            pre_census_qualification=(recovery["qualification"] if recovery is not None else None),
            prepared_reader_record=prepared_reader_record,
        )
    except BaseException:
        guard.close()
        raise


@contextmanager
def open_v5_to_v7_evidence(
    runtime_root: Path, expected_release_sha: str
) -> Iterator[RetainedV5ToV7Evidence]:
    """Open the retained chain under strict INITIAL current-custody proof.

    Requires services stopped, the canonical existing service lock, no upgrade
    or restore barrier, no SQLite sidecars, and exact current v7 identity and
    semantic equality to the retained completion before any DATA is yielded.
    """
    evidence: RetainedV5ToV7Evidence | None = None
    try:
        evidence = _open_chain_evidence(runtime_root, expected_release_sha, None)
        yield evidence
    except BaseException:
        if evidence is not None:
            evidence._guard.close()
        raise
    try:
        evidence.check()
    finally:
        evidence._guard.close()


@contextmanager
def open_retained_v5_to_v7_evidence(
    runtime_root: Path,
    expected_release_sha: str,
    pinned_material: Mapping[str, Any],
) -> Iterator[RetainedV5ToV7Evidence]:
    """Reopen only the immutable historical chain against exact pinned material.

    Never reads the current authoritative database, never demands the live
    inode or bytes to stay equal to the initial v7 target, and never grants
    issuance, arm, restore, or migration authority.
    """
    evidence: RetainedV5ToV7Evidence | None = None
    try:
        evidence = _open_chain_evidence(
            runtime_root, expected_release_sha, pinned_material
        )
        yield evidence
    except BaseException:
        if evidence is not None:
            evidence._guard.close()
        raise
    try:
        evidence.check()
    finally:
        evidence._guard.close()


__all__ = [
    "EVIDENCE_PHASE_HISTORICAL",
    "EVIDENCE_PHASE_INITIAL",
    "MATERIAL_SCHEMA_VERSION",
    "EvidenceCustodyError",
    "RetainedChainInvalid",
    "RetainedV5ToV7Evidence",
    "SchemaUpgradeEvidenceError",
    "V7AcceptanceBackupEvidence",
    "open_retained_v5_to_v7_evidence",
    "open_v5_to_v7_evidence",
    "open_prepared_successor_v5_to_v7_evidence",
]


@contextmanager
def open_prepared_successor_v5_to_v7_evidence(
    runtime_root: Path, expected_reader_release_sha: str,
    prepared_material: Mapping[str, Any],
) -> Iterator[RetainedV5ToV7Evidence]:
    """Strict current INITIAL evidence under a separately sealed successor reader.

    The material is expected DATA, never historical authority or a skip flag.
    This finite entry admits only the existing sixteen-origin preparation;
    all current target checks run and the returned material is identical.
    The maintenance owner separately authenticates the actual unstarted
    preparation bundle and its selected-source lineage.
    """
    prepared = _validate_pinned_material(prepared_material)
    if prepared["schema_version"] != SPENT_CTIME_MATERIAL_SCHEMA_VERSION:
        raise RetainedChainInvalid("prepared successor requires the closed sixteen-origin variant")
    evidence = None
    try:
        evidence = _open_chain_evidence(runtime_root, prepared["chain"]["tool_release"]["sha"], None,
            _prepared_reader_sha=expected_reader_release_sha, _prepared_material=prepared)
        evidence.check_prepared_sources()
        yield evidence
        evidence.check_prepared_sources()
        evidence.check()
    finally:
        if evidence is not None:
            evidence._guard.close()
