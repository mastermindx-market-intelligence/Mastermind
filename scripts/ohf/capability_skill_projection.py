"""Attempt-local, byte-identical Codex Skill projection (CAP-S1, Codex-canary scoped).

Per the vertical amendment (``docs/superpowers/specs/2026-09-01-sol-capability-fabric-
cap-s1-vertical-amendment.md`` §6.2) and the protocol-attestation amendment (``...cap-s1-
protocol-attestation-amendment.md`` §4), one already-verified ``CapabilityPackageGeneration``
is staged into a fresh subdirectory below the exact canary Attempt/workspace resource root,
so the App Server's only custom-Skill source is one byte-identical, receipt-bound tree.

This module is a **Codex-specific falsifier**, not the provider-neutral materializer owned
by HF1. It never introduces a generic package installer, durable staging registry, plugin
manager, or cross-provider API. If a change here would need to become provider-neutral, the
implementation must stop and return to Sol/HF1 rather than silently absorbing that owner.

Error messages are bounded to a field name and a closed reason token. They never echo a
caller-supplied path, digest, or identifier value -- the same discipline
``control_plane.executive_capability_packages`` uses. This includes failures raised by an
internal seam (a monkeypatched helper, an unexpected OS error mid-copy): any exception that
is not already one of this module's own bounded types, or the sibling
``CapabilityPackageError`` trust boundary, is normalized into a fixed, non-echoing
``SkillProjectionError`` before it ever leaves this module (see ``_reraise_after_rollback``).

Sol wave-3 review (5087139217, finding M6) hardened this module with:

- a typed, self-validating ``SkillProjectionReceipt`` (``validate_skill_projection_receipt``)
  that proves resolved root identities, distinct origin/projection row sets and their
  one-to-one equality, a monotonic creation time, and a closed ``origin_authentication``
  token -- called by ``stage_skill_projection`` on its own output and by
  ``cleanup_skill_projection`` first on its input;
- authenticated origin modes: ``INSTALLED_RELEASE`` requires the origin root's basename to
  equal the generation's exact ``source_commit`` (the Executive installer's
  ``releases/<sha>`` layout); ``VERIFIED_EPHEMERAL_GIT_ARCHIVE`` requires a typed, git-object-
  store-proven ``EphemeralGitOriginReceipt``;
- a bounded (<=64KiB chunk) write loop with short-write detection, and a rollback wrapper
  around the whole post-mkdir staging sequence so a mid-staging failure never leaves an
  orphan projection tree;
- cleanup authorization bound to the exact attempt-root parent identity, not merely the
  projection root's own basename and inode.
"""
from __future__ import annotations

import dataclasses
import hashlib
import io
import os
import re
import secrets
import stat
import subprocess
import tarfile
import time
from pathlib import Path
from typing import NoReturn

from control_plane.executive_capability_packages import (
    CapabilityPackageError,
    CapabilityPackageGeneration,
    verify_capability_package_source,
)

# ---------------------------------------------------------------------------
# Errors and constants
# ---------------------------------------------------------------------------


class SkillProjectionError(ValueError):
    """One projection, archive, or cleanup step refused."""


def _refuse(field: str, reason: str) -> NoReturn:
    raise SkillProjectionError(f"{field}: {reason}")


ORIGIN_INSTALLED_RELEASE = "INSTALLED_RELEASE"
ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE = "VERIFIED_EPHEMERAL_GIT_ARCHIVE"

_ORIGIN_MODES = frozenset({ORIGIN_INSTALLED_RELEASE, ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE})

# Bounded, closed ``origin_authentication`` tokens recorded on the receipt --
# distinct from the ``origin_mode`` values above: the mode is the caller's
# request, the authentication token is this module's own proof of which
# authenticated path actually cleared.
ORIGIN_AUTHENTICATION_INSTALLED_RELEASE = "installed-release-root"
ORIGIN_AUTHENTICATION_EPHEMERAL_GIT_ARCHIVE = "ephemeral-git-archive"

_ORIGIN_AUTHENTICATIONS = frozenset(
    {ORIGIN_AUTHENTICATION_INSTALLED_RELEASE, ORIGIN_AUTHENTICATION_EPHEMERAL_GIT_ARCHIVE}
)

PROJECTION_RECEIPT_SCHEMA_VERSION = "mastermind.skill_projection_receipt/v1"
EPHEMERAL_GIT_ORIGIN_SCHEMA_VERSION = "mastermind.ephemeral_git_origin/v1"
PROJECTION_CLEANUP_SCHEMA_VERSION = "mastermind.skill_projection_cleanup/v1"

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_HEX40_RE = re.compile(r"[0-9a-f]{40}")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")

_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)

_READ_CHUNK_BYTES = 65536
_WRITE_CHUNK_BYTES = 65536
_MAX_ARCHIVE_BYTES = 8 * 1024 * 1024

# Package-shape ceilings a receipt's row sets are re-checked against.
# Mirrors ``control_plane.executive_capability_packages``' own ceilings so a
# receipt can never describe a shape that module would itself have refused,
# without importing its private helpers.
MAX_PROJECTION_FILES = 64
MAX_PROJECTION_FILE_BYTES = 1024 * 1024
MAX_PROJECTION_TOTAL_BYTES = 8 * 1024 * 1024


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and _HEX64_RE.fullmatch(value) is not None


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class SkillProjectionReceipt:
    origin_mode: str
    origin_root_identity: tuple[int, int]
    repository: str
    source_commit: str
    source_tree_sha: str
    package_capability_id: str
    package_generation: str
    package_content_digest: str
    package_source_digest: str
    package_generation_digest: str
    skill_content_digests: tuple[tuple[str, str], ...]
    file_rows: tuple[tuple[str, str, int, bool], ...]
    projection_root: str
    projection_root_identity: tuple[int, int]
    skills_root: str
    owning_operation_id: str
    owning_process_generation: str
    read_only_applied: bool
    cleanup_state: str
    # --- Sol wave-3 M6 hardening: ADDED fields only; never rename/remove --
    # (adapter compatibility -- see control_plane.codex_operator_adapter
    # ._validate_skill_canary_binding, which reads named attributes and
    # never enumerates dataclass fields).
    schema_version: str = PROJECTION_RECEIPT_SCHEMA_VERSION
    origin_rows: tuple[tuple[str, str, int, bool], ...] = ()
    projection_rows: tuple[tuple[str, str, int, bool], ...] = ()
    origin_resolved_root: str = ""
    projection_resolved_root: str = ""
    attempt_root: str = ""
    attempt_root_identity: tuple[int, int] = (0, 0)
    created_at_monotonic_ns: int = 0
    origin_authentication: str = ""


@dataclasses.dataclass(frozen=True)
class SkillProjectionCleanupReceipt:
    projection_root: str
    removed: bool
    verified_absent: bool
    schema_version: str = PROJECTION_CLEANUP_SCHEMA_VERSION


@dataclasses.dataclass(frozen=True)
class EphemeralGitOriginReceipt:
    """Typed, self-describing proof that ``create_ephemeral_archive_origin``
    resolved and archived a specific commit's package subtree from the LOCAL
    git object store -- never a bare ``Path`` a caller must trust blindly."""

    schema_version: str
    repository_git_dir: str
    repository_git_dir_identity: tuple[int, int]
    source_commit: str
    source_tree_sha: str
    package_root: str
    origin_root: str
    origin_root_identity: tuple[int, int]
    member_count: int
    archive_digest: str
    inventory_digest: str


# ---------------------------------------------------------------------------
# Bounded field validation
# ---------------------------------------------------------------------------


def _validate_bounded_token(value: object, field: str) -> str:
    if not isinstance(value, str) or _TOKEN_RE.fullmatch(value) is None:
        _refuse(field, "invalid_token")
    return value  # type: ignore[return-value]


def _require_real_directory(path: object, field: str, unavailable_reason: str, symlink_reason: str) -> Path:
    try:
        candidate = Path(path)
    except TypeError:
        _refuse(field, unavailable_reason)
    try:
        st = os.lstat(str(candidate))
    except (OSError, ValueError):
        _refuse(field, unavailable_reason)
    if stat.S_ISLNK(st.st_mode):
        _refuse(field, symlink_reason)
    if not stat.S_ISDIR(st.st_mode):
        _refuse(field, unavailable_reason)
    return candidate


def _lstat_identity(path: Path, field: str) -> tuple[int, int]:
    try:
        st = os.lstat(str(path))
    except (OSError, ValueError):
        _refuse(field, "identity_unavailable")
    return (st.st_dev, st.st_ino)


def _ancestor_directories(relative_paths: "set[str] | frozenset[str]") -> set[str]:
    dirs: set[str] = set()
    for relative_path in relative_paths:
        parts = relative_path.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))
    return dirs


# ---------------------------------------------------------------------------
# validate_skill_projection_receipt -- self-validation boundary
# ---------------------------------------------------------------------------


def _validate_row_set(rows: object, field: str) -> tuple[tuple[str, str, int, bool], ...]:
    if not isinstance(rows, tuple):
        _refuse(field, "invalid_rows_type")
    if len(rows) > MAX_PROJECTION_FILES:
        _refuse(field, "too_many_rows")
    seen_paths: set[str] = set()
    total_bytes = 0
    for row in rows:
        if not isinstance(row, tuple) or len(row) != 4:
            _refuse(field, "invalid_row_shape")
        relative_path, sha256_value, byte_length, executable = row
        if not isinstance(relative_path, str) or relative_path == "":
            _refuse(field, "invalid_row_shape")
        if relative_path in seen_paths:
            _refuse(field, "duplicate_row_path")
        seen_paths.add(relative_path)
        if not _is_hex64(sha256_value):
            _refuse(field, "invalid_row_digest")
        if isinstance(byte_length, bool) or not isinstance(byte_length, int):
            _refuse(field, "invalid_row_shape")
        if byte_length < 0 or byte_length > MAX_PROJECTION_FILE_BYTES:
            _refuse(field, "row_byte_length_out_of_bounds")
        if not isinstance(executable, bool):
            _refuse(field, "invalid_row_shape")
        total_bytes += byte_length
    if total_bytes > MAX_PROJECTION_TOTAL_BYTES:
        _refuse(field, "rows_total_bytes_out_of_bounds")
    return rows  # type: ignore[return-value]


def _validate_identity_shape(value: object, field: str) -> None:
    if (
        not isinstance(value, tuple)
        or len(value) != 2
        or not all(isinstance(part, int) and not isinstance(part, bool) for part in value)
    ):
        _refuse(field, "invalid_identity_shape")


def validate_skill_projection_receipt(receipt: object) -> None:
    """Pure, filesystem-free proof that ``receipt`` is an internally
    consistent, well-formed ``SkillProjectionReceipt`` -- never a check that
    the receipt's paths still correspond to anything on disk (that is
    ``cleanup_skill_projection``'s own, separate, containment job).

    Called by ``stage_skill_projection`` on its own output before returning
    (self-validation) and by ``cleanup_skill_projection`` FIRST on its input
    (Sol wave-3 review finding M6).
    """
    if type(receipt) is not SkillProjectionReceipt:
        _refuse("receipt", "invalid_receipt_type")

    if receipt.schema_version != PROJECTION_RECEIPT_SCHEMA_VERSION:
        _refuse("schema_version", "invalid_schema_version")

    for value in (
        receipt.package_content_digest,
        receipt.package_source_digest,
        receipt.package_generation_digest,
    ):
        if not _is_hex64(value):
            _refuse("receipt", "invalid_digest")

    if not isinstance(receipt.skill_content_digests, tuple):
        _refuse("receipt", "invalid_skill_content_digests")
    for entry in receipt.skill_content_digests:
        if (
            not isinstance(entry, tuple)
            or len(entry) != 2
            or not isinstance(entry[0], str)
            or not _is_hex64(entry[1])
        ):
            _refuse("receipt", "invalid_skill_content_digests")

    origin_rows = _validate_row_set(receipt.origin_rows, "origin_rows")
    projection_rows = _validate_row_set(receipt.projection_rows, "projection_rows")
    if tuple(sorted(origin_rows)) != tuple(sorted(projection_rows)):
        _refuse("receipt", "origin_projection_rows_mismatch")

    for identity, field in (
        (receipt.origin_root_identity, "origin_root_identity"),
        (receipt.projection_root_identity, "projection_root_identity"),
        (receipt.attempt_root_identity, "attempt_root_identity"),
    ):
        _validate_identity_shape(identity, field)

    if receipt.origin_authentication not in _ORIGIN_AUTHENTICATIONS:
        _refuse("origin_authentication", "unsupported_value")

    if (
        isinstance(receipt.created_at_monotonic_ns, bool)
        or not isinstance(receipt.created_at_monotonic_ns, int)
        or receipt.created_at_monotonic_ns <= 0
    ):
        _refuse("created_at_monotonic_ns", "invalid_value")

    for value, field in (
        (receipt.origin_resolved_root, "origin_resolved_root"),
        (receipt.projection_resolved_root, "projection_resolved_root"),
        (receipt.attempt_root, "attempt_root"),
        (receipt.projection_root, "projection_root"),
        (receipt.skills_root, "skills_root"),
    ):
        if not isinstance(value, str) or value == "":
            _refuse(field, "invalid_path_value")


# ---------------------------------------------------------------------------
# Descriptor-relative, no-follow package tree copy
# ---------------------------------------------------------------------------


def _read_verified_file(parent_fd: int, name: str, row, field: str = "origin_root") -> bytes:
    try:
        fd = os.open(name, os.O_RDONLY | _O_NOFOLLOW | _O_NONBLOCK | _O_CLOEXEC, dir_fd=parent_fd)
    except OSError:
        _refuse(field, "origin_file_unavailable")
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            _refuse(field, "origin_file_unavailable")
        if st.st_size != row.byte_length:
            _refuse(field, "origin_file_drifted")
        actual_executable = bool(st.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        if actual_executable != row.executable:
            _refuse(field, "origin_file_drifted")

        data = bytearray()
        while True:
            try:
                chunk = os.read(fd, _READ_CHUNK_BYTES)
            except OSError:
                _refuse(field, "origin_file_unavailable")
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > row.byte_length:
                _refuse(field, "origin_file_drifted")
        if len(data) != row.byte_length:
            _refuse(field, "origin_file_drifted")
        if hashlib.sha256(bytes(data)).hexdigest() != row.sha256:
            _refuse(field, "origin_file_drifted")
    finally:
        os.close(fd)
    return bytes(data)


def _write_exclusive_file(parent_fd: int, name: str, data: bytes, executable: bool) -> None:
    """Create ``name`` exclusively and write ``data`` in full, via a bounded
    (<=64KiB per call) loop that keeps writing until every declared byte has
    landed and refuses on a short (zero-byte) write rather than silently
    truncating (Sol wave-3 review finding M6)."""
    mode = 0o755 if executable else 0o644
    try:
        fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _O_NOFOLLOW, mode, dir_fd=parent_fd)
    except FileExistsError:
        _refuse("projection_root", "projection_root_exists")
    except OSError:
        _refuse("projection_root", "projection_root_unavailable")
    try:
        _write_all_bounded(fd, data, "projection_root", "projection_root_write_failed")
        try:
            os.fsync(fd)
        except OSError:
            _refuse("projection_root", "projection_root_write_failed")
    finally:
        os.close(fd)


def _write_all_bounded(fd: int, data: bytes, field: str, reason: str) -> None:
    """Complete one bounded post-image even when the kernel short-writes.

    One-byte progress is the smallest lawful write, so ``len(data)`` calls
    is a strict upper bound. Zero, negative, over-reported, or non-integer
    results refuse instead of turning an injected seam into an unbounded
    loop or a truncated success.
    """

    total = len(data)
    written = 0
    calls = 0
    view = memoryview(data)
    while written < total:
        chunk = view[written : written + _WRITE_CHUNK_BYTES]
        try:
            count = os.write(fd, chunk)
        except OSError:
            _refuse(field, reason)
        calls += 1
        if type(count) is not int or count <= 0 or count > len(chunk) or calls > total:
            _refuse(field, reason)
        written += count
    if written != total:
        _refuse(field, reason)


def _open_chain_nofollow(root_fd: int, parts: list[str], field: str, unavailable_reason: str) -> tuple[int, list[int]]:
    """Descend `parts` below `root_fd` via no-follow directory opens.

    Returns the final directory fd and the list of newly opened fds (for the
    caller's own cleanup bookkeeping); `root_fd` itself is not included.
    """
    opened: list[int] = []
    current = root_fd
    for part in parts:
        try:
            st = os.lstat(part, dir_fd=current)
        except OSError:
            _refuse(field, unavailable_reason)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            _refuse(field, unavailable_reason)
        try:
            current = os.open(part, os.O_RDONLY | _O_NOFOLLOW | _O_DIRECTORY, dir_fd=current)
        except OSError:
            _refuse(field, unavailable_reason)
        opened.append(current)
    return current, opened


def _copy_package_tree(
    *,
    origin_root: Path,
    generation: CapabilityPackageGeneration,
    projection_root_fd: int,
) -> tuple[tuple[str, str, int, bool], ...]:
    package_root_parts = generation.package_root.split("/")
    opened: list[int] = []

    try:
        try:
            origin_root_fd = os.open(str(origin_root), os.O_RDONLY | _O_NOFOLLOW | _O_DIRECTORY)
        except OSError:
            _refuse("origin_root", "origin_root_unavailable")
        opened.append(origin_root_fd)

        origin_pkg_fd, chain_opened = _open_chain_nofollow(
            origin_root_fd, package_root_parts, "origin_root", "origin_package_root_unavailable"
        )
        opened.extend(chain_opened)

        # Create the destination package_root chain fresh, below the already
        # exclusively-created projection root.
        dest_pkg_fd = projection_root_fd
        for part in package_root_parts:
            try:
                os.mkdir(part, 0o700, dir_fd=dest_pkg_fd)
            except FileExistsError:
                _refuse("projection_root", "projection_root_exists")
            except OSError:
                _refuse("projection_root", "projection_root_unavailable")
            try:
                dest_pkg_fd = os.open(part, os.O_RDONLY | _O_NOFOLLOW | _O_DIRECTORY, dir_fd=dest_pkg_fd)
            except OSError:
                _refuse("projection_root", "projection_root_unavailable")
            opened.append(dest_pkg_fd)

        declared_paths = {row.relative_path for row in generation.files}
        declared_dirs = _ancestor_directories(declared_paths)

        origin_dirs: dict[str, int] = {"": origin_pkg_fd}
        dest_dirs: dict[str, int] = {"": dest_pkg_fd}
        for rel in sorted(declared_dirs, key=lambda p: (p.count("/"), p)):
            parent_rel, _sep, name = rel.rpartition("/")
            origin_parent_fd = origin_dirs[parent_rel]
            try:
                st = os.lstat(name, dir_fd=origin_parent_fd)
            except OSError:
                _refuse("origin_root", "origin_package_root_unavailable")
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                _refuse("origin_root", "origin_package_root_unavailable")
            try:
                origin_child_fd = os.open(name, os.O_RDONLY | _O_NOFOLLOW | _O_DIRECTORY, dir_fd=origin_parent_fd)
            except OSError:
                _refuse("origin_root", "origin_package_root_unavailable")
            opened.append(origin_child_fd)
            origin_dirs[rel] = origin_child_fd

            dest_parent_fd = dest_dirs[parent_rel]
            try:
                os.mkdir(name, 0o700, dir_fd=dest_parent_fd)
            except FileExistsError:
                _refuse("projection_root", "projection_root_exists")
            except OSError:
                _refuse("projection_root", "projection_root_unavailable")
            try:
                dest_child_fd = os.open(name, os.O_RDONLY | _O_NOFOLLOW | _O_DIRECTORY, dir_fd=dest_parent_fd)
            except OSError:
                _refuse("projection_root", "projection_root_unavailable")
            opened.append(dest_child_fd)
            dest_dirs[rel] = dest_child_fd

        file_rows: list[tuple[str, str, int, bool]] = []
        for row in generation.files:
            parent_rel, _sep, name = row.relative_path.rpartition("/")
            origin_parent_fd = origin_dirs.get(parent_rel)
            dest_parent_fd = dest_dirs.get(parent_rel)
            if origin_parent_fd is None or dest_parent_fd is None:
                _refuse("origin_root", "origin_package_root_unavailable")
            data = _read_verified_file(origin_parent_fd, name, row)
            _write_exclusive_file(dest_parent_fd, name, data, row.executable)
            file_rows.append((row.relative_path, row.sha256, row.byte_length, row.executable))

        return tuple(file_rows)
    finally:
        for fd in reversed(opened):
            try:
                os.close(fd)
            except OSError:
                pass


def _collect_verified_rows(
    root_path: Path, generation: CapabilityPackageGeneration, field: str
) -> tuple[tuple[str, str, int, bool], ...]:
    """Fresh, independent, read-only re-verification of every declared row
    under ``root_path`` -- never trusts that a prior write succeeded, always
    re-opens and re-hashes the actual bytes on disk."""
    package_root_parts = generation.package_root.split("/")
    opened: list[int] = []
    try:
        try:
            root_fd = os.open(str(root_path), os.O_RDONLY | _O_NOFOLLOW | _O_DIRECTORY)
        except OSError:
            _refuse(field, "projection_root_unavailable")
        opened.append(root_fd)

        pkg_fd, chain_opened = _open_chain_nofollow(root_fd, package_root_parts, field, "projection_root_unavailable")
        opened.extend(chain_opened)

        declared_paths = {row.relative_path for row in generation.files}
        declared_dirs = _ancestor_directories(declared_paths)

        dirs: dict[str, int] = {"": pkg_fd}
        for rel in sorted(declared_dirs, key=lambda p: (p.count("/"), p)):
            parent_rel, _sep, name = rel.rpartition("/")
            parent_fd = dirs[parent_rel]
            try:
                st = os.lstat(name, dir_fd=parent_fd)
            except OSError:
                _refuse(field, "projection_root_unavailable")
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                _refuse(field, "projection_root_unavailable")
            try:
                child_fd = os.open(name, os.O_RDONLY | _O_NOFOLLOW | _O_DIRECTORY, dir_fd=parent_fd)
            except OSError:
                _refuse(field, "projection_root_unavailable")
            opened.append(child_fd)
            dirs[rel] = child_fd

        rows: list[tuple[str, str, int, bool]] = []
        for row in generation.files:
            parent_rel, _sep, name = row.relative_path.rpartition("/")
            parent_fd = dirs.get(parent_rel)
            if parent_fd is None:
                _refuse(field, "projection_root_unavailable")
            _read_verified_file(parent_fd, name, row, field=field)
            rows.append((row.relative_path, row.sha256, row.byte_length, row.executable))

        return tuple(sorted(rows, key=lambda r: r[0]))
    finally:
        for fd in reversed(opened):
            try:
                os.close(fd)
            except OSError:
                pass


def _apply_read_only(projection_root: Path) -> bool:
    ok = True
    try:
        for dirpath, _dirnames, filenames in os.walk(str(projection_root), topdown=False):
            for name in filenames:
                try:
                    os.chmod(os.path.join(dirpath, name), 0o444)
                except OSError:
                    ok = False
            try:
                os.chmod(dirpath, 0o555)
            except OSError:
                ok = False
    except OSError:
        ok = False
    return ok


def _force_remove_tree(root: Path) -> bool:
    root_str = str(root)
    try:
        for dirpath, _dirnames, filenames in os.walk(root_str):
            try:
                os.chmod(dirpath, 0o700)
            except OSError:
                pass
            for name in filenames:
                try:
                    os.chmod(os.path.join(dirpath, name), 0o600)
                except OSError:
                    pass
    except OSError:
        return False

    try:
        for dirpath, dirnames, filenames in os.walk(root_str, topdown=False):
            for name in filenames:
                os.remove(os.path.join(dirpath, name))
            for name in dirnames:
                os.rmdir(os.path.join(dirpath, name))
        os.rmdir(root_str)
    except OSError:
        return False
    return True


def _rollback_projection_root(projection_root_path: Path) -> str:
    """Best-effort removal of a partially (or fully) staged projection root
    after a mid-staging failure, followed by a fresh absence check.

    Returns the bounded, non-echoing detail token appended to the re-raised
    error: ``"rollback_complete"`` when the root is gone afterward,
    ``"rollback_failed"`` otherwise. Never raises itself.
    """
    rollback_ok = _force_remove_tree(projection_root_path)
    try:
        os.lstat(str(projection_root_path))
        absent = False
    except (OSError, ValueError):
        absent = True
    return "rollback_complete" if (rollback_ok and absent) else "rollback_failed"


def _archive_inventory_digest(
    rows: "tuple[tuple[str, str, int, bool], ...] | list[tuple[str, str, int, bool]]",
) -> str:
    digest = hashlib.sha256()
    for relative_path, sha256, byte_length, executable in sorted(rows):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256.encode("ascii"))
        digest.update(b"\0")
        digest.update(str(byte_length).encode("ascii"))
        digest.update(b"\0")
        digest.update(b"1" if executable else b"0")
        digest.update(b"\n")
    return digest.hexdigest()


def _rederive_ephemeral_git_origin(
    receipt: EphemeralGitOriginReceipt,
    generation: CapabilityPackageGeneration,
    origin_root_path: Path,
) -> None:
    """Freshly prove the receipt's object-store provenance at consumption."""

    if (
        receipt.schema_version != EPHEMERAL_GIT_ORIGIN_SCHEMA_VERSION
        or receipt.package_root != generation.package_root
        or receipt.source_commit != generation.source_commit
        or receipt.source_tree_sha != generation.source_tree_sha
        or receipt.origin_root != str(origin_root_path)
        or receipt.member_count != len(generation.files)
        or not _is_hex64(receipt.archive_digest)
        or not _is_hex64(receipt.inventory_digest)
    ):
        _refuse("origin_receipt", "git_provenance_mismatch")

    git_dir_path = _require_real_directory(
        receipt.repository_git_dir,
        "origin_receipt",
        "git_provenance_mismatch",
        "git_provenance_mismatch",
    )
    if (
        os.path.realpath(str(git_dir_path)) != receipt.repository_git_dir
        or _lstat_identity(git_dir_path, "origin_receipt")
        != receipt.repository_git_dir_identity
        or _lstat_identity(origin_root_path, "origin_receipt")
        != receipt.origin_root_identity
    ):
        _refuse("origin_receipt", "git_provenance_mismatch")

    resolved_commit = _git_rev_or_none(
        git_dir_path, "rev-parse", f"{generation.source_commit}^{{commit}}"
    )
    resolved_tree = _git_rev_or_none(
        git_dir_path,
        "rev-parse",
        f"{generation.source_commit}:{generation.package_root}",
    )
    generation_rows = tuple(
        (row.relative_path, row.sha256, row.byte_length, row.executable)
        for row in generation.files
    )
    if (
        resolved_commit != generation.source_commit
        or resolved_tree != generation.source_tree_sha
        or _archive_inventory_digest(generation_rows) != receipt.inventory_digest
    ):
        _refuse("origin_receipt", "git_provenance_mismatch")


# ---------------------------------------------------------------------------
# stage_skill_projection
# ---------------------------------------------------------------------------


def stage_skill_projection(
    *,
    generation: CapabilityPackageGeneration,
    origin_mode: str,
    origin_root: "str | Path",
    attempt_root: "str | Path",
    owning_operation_id: str,
    owning_process_generation: str,
    origin_receipt: "EphemeralGitOriginReceipt | None" = None,
) -> SkillProjectionReceipt:
    # Law 1.
    if origin_mode not in _ORIGIN_MODES:
        _refuse("origin_mode", "unsupported_value")

    _validate_bounded_token(owning_operation_id, "owning_operation_id")
    _validate_bounded_token(owning_process_generation, "owning_process_generation")

    origin_root_path = _require_real_directory(
        origin_root, "origin_root", "origin_root_unavailable", "origin_root_symlink_refused"
    )
    origin_root_identity = _lstat_identity(origin_root_path, "origin_root")
    origin_resolved_root = os.path.realpath(str(origin_root_path))

    # Law 2.5 (Sol wave-3 M6): the origin must be AUTHENTICATED for the
    # declared mode, not merely present and byte-verified. A plain checkout
    # no longer authenticates as INSTALLED_RELEASE.
    if origin_mode == ORIGIN_INSTALLED_RELEASE:
        # Preserve the original package trust boundary's error precedence:
        # malformed bytes refuse as CapabilityPackageError before the
        # installed-release layout check.
        verified_origin = verify_capability_package_source(origin_root_path, generation)
        if origin_root_path.name != generation.source_commit:
            _refuse("origin_root", "installed_release_root_unauthenticated")
        origin_authentication = ORIGIN_AUTHENTICATION_INSTALLED_RELEASE
    else:
        # ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE (the only other member of
        # _ORIGIN_MODES).
        if type(origin_receipt) is not EphemeralGitOriginReceipt:
            _refuse("origin_receipt", "ephemeral_origin_receipt_required")
        if origin_receipt.origin_root != str(origin_root_path):
            _refuse("origin_receipt", "ephemeral_origin_receipt_root_mismatch")
        if origin_receipt.source_commit != generation.source_commit:
            _refuse("origin_receipt", "ephemeral_origin_receipt_commit_mismatch")
        if origin_receipt.source_tree_sha != generation.source_tree_sha:
            _refuse("origin_receipt", "ephemeral_origin_receipt_tree_mismatch")
        _rederive_ephemeral_git_origin(origin_receipt, generation, origin_root_path)
        origin_authentication = ORIGIN_AUTHENTICATION_EPHEMERAL_GIT_ARCHIVE
        # After object-store identity/provenance authentication,
        # independently re-open and verify the exact package post-image.
        verified_origin = verify_capability_package_source(origin_root_path, generation)

    # Law 3: attempt_root must exist, be a real non-symlink directory; the
    # projection root is created BELOW it with exclusive mkdir semantics.
    attempt_root_path = _require_real_directory(
        attempt_root, "attempt_root", "attempt_root_unavailable", "attempt_root_symlink_refused"
    )
    attempt_root_identity = _lstat_identity(attempt_root_path, "attempt_root")

    projection_dir_name = f"skill-projection-{owning_process_generation}"
    projection_root_path = attempt_root_path / projection_dir_name
    try:
        os.mkdir(projection_root_path, 0o700)
    except FileExistsError:
        _refuse("attempt_root", "projection_root_exists")
    except OSError:
        _refuse("attempt_root", "projection_root_unavailable")

    # Sol wave-3 M6: everything from here on operates on the exclusively
    # created projection root. ANY failure -- ours or an internal seam's --
    # triggers a best-effort rollback of that exact root before the original
    # (or a normalized) error is re-raised, so a mid-staging failure never
    # leaves an orphan tree behind.
    try:
        try:
            projection_root_fd = os.open(str(projection_root_path), os.O_RDONLY | _O_NOFOLLOW | _O_DIRECTORY)
        except OSError:
            _refuse("attempt_root", "projection_root_unavailable")

        try:
            # Law 4/5: copy exactly the declared rows, nothing else.
            file_rows = _copy_package_tree(
                origin_root=origin_root_path,
                generation=generation,
                projection_root_fd=projection_root_fd,
            )
        finally:
            os.close(projection_root_fd)

        # Law 6: read-only where the platform permits; never fail solely on
        # chmod refusal.
        read_only_applied = _apply_read_only(projection_root_path)

        # Law 7: re-verify the byte-identical staged copy against the SAME
        # generation object -- the projection mirrors <root>/<package_root>,
        # so the projection root itself is a lawful source_root.
        verify_capability_package_source(projection_root_path, generation)

        # Sol wave-3 M6: an independent, read-only, post-copy re-collection
        # of every declared row from the projection tree -- never trusts
        # that the write above landed correctly, re-opens and re-hashes.
        projection_rows = _collect_verified_rows(projection_root_path, generation, "projection_root")

        projection_root_identity = _lstat_identity(projection_root_path, "projection_root")
        projection_resolved_root = os.path.realpath(str(projection_root_path))
        skills_root = str(projection_root_path / generation.package_root / "skills")

        receipt = SkillProjectionReceipt(
            origin_mode=origin_mode,
            origin_root_identity=origin_root_identity,
            repository=generation.repository,
            source_commit=generation.source_commit,
            source_tree_sha=generation.source_tree_sha,
            package_capability_id=generation.capability_id,
            package_generation=generation.generation,
            package_content_digest=verified_origin.package_content_digest,
            package_source_digest=verified_origin.package_source_digest,
            package_generation_digest=verified_origin.package_generation_digest,
            skill_content_digests=verified_origin.skill_content_digests,
            file_rows=file_rows,
            projection_root=str(projection_root_path),
            projection_root_identity=projection_root_identity,
            skills_root=skills_root,
            owning_operation_id=owning_operation_id,
            owning_process_generation=owning_process_generation,
            read_only_applied=read_only_applied,
            cleanup_state="LIVE",
            schema_version=PROJECTION_RECEIPT_SCHEMA_VERSION,
            origin_rows=tuple(sorted(file_rows, key=lambda r: r[0])),
            projection_rows=projection_rows,
            origin_resolved_root=origin_resolved_root,
            projection_resolved_root=projection_resolved_root,
            attempt_root=str(attempt_root_path),
            attempt_root_identity=attempt_root_identity,
            created_at_monotonic_ns=time.monotonic_ns(),
            origin_authentication=origin_authentication,
        )

        # Self-validation: never return a receipt this module's own
        # validator would refuse.
        validate_skill_projection_receipt(receipt)

        return receipt
    except SkillProjectionError as exc:
        outcome = _rollback_projection_root(projection_root_path)
        raise SkillProjectionError(f"{exc}; {outcome}") from exc
    except CapabilityPackageError as exc:
        # Never masked as our own error type -- only annotated with the
        # rollback outcome, same bounded-token discipline.
        outcome = _rollback_projection_root(projection_root_path)
        raise CapabilityPackageError(f"{exc}; {outcome}") from exc
    except Exception as exc:  # noqa: BLE001 -- any other seam (e.g. an
        # internal helper monkeypatched for a falsifier, an unexpected OS
        # error) is normalized to our own bounded, non-echoing error rather
        # than letting an arbitrary exception's message (which may contain a
        # path) escape this module.
        outcome = _rollback_projection_root(projection_root_path)
        raise SkillProjectionError(f"projection_root: staging_failed; {outcome}") from exc


# ---------------------------------------------------------------------------
# create_ephemeral_archive_origin
# ---------------------------------------------------------------------------


def _run_git_archive(repository_git_dir: Path, source_commit: str, package_root: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", f"--git-dir={repository_git_dir}", "archive", "--format=tar", source_commit, "--", package_root],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        _refuse("repository_git_dir", "archive_failed")
    return completed.stdout


def _git_rev_or_none(repository_git_dir: Path, *args: str) -> "str | None":
    try:
        completed = subprocess.run(
            ["git", f"--git-dir={repository_git_dir}", *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value if value else None


def _extract_safe_tar(
    archive_bytes: bytes, dest_dir: Path, package_root: str
) -> tuple[int, str]:
    if len(archive_bytes) > _MAX_ARCHIVE_BYTES:
        _refuse("archive", "archive_too_large")

    package_root_parts = package_root.split("/")
    ancestor_prefixes = {"/".join(package_root_parts[: i + 1]) for i in range(len(package_root_parts))}
    nested_prefix = package_root.rstrip("/") + "/"

    try:
        tf = tarfile.open(fileobj=io.BytesIO(archive_bytes))
    except tarfile.TarError:
        _refuse("archive", "unsafe_tar_member")

    inventory_rows: list[tuple[str, str, int, bool]] = []
    try:
        try:
            members = tf.getmembers()
        except tarfile.TarError:
            _refuse("archive", "unsafe_tar_member")

        for member in members:
            name = member.name
            if not isinstance(name, str) or name == "":
                _refuse("archive", "unsafe_tar_member")
            if name.startswith("/") or name.startswith("\\"):
                _refuse("archive", "unsafe_tar_member")
            name_norm = name.rstrip("/")
            segments = name_norm.split("/")
            if any(part in ("", ".", "..") for part in segments):
                _refuse("archive", "unsafe_tar_member")
            if member.issym() or member.islnk():
                _refuse("archive", "unsafe_tar_member")
            if member.isdir():
                if name_norm not in ancestor_prefixes and not name_norm.startswith(nested_prefix):
                    _refuse("archive", "unsafe_tar_member")
            elif member.isreg():
                if not name_norm.startswith(nested_prefix):
                    _refuse("archive", "unsafe_tar_member")
            else:
                _refuse("archive", "unsafe_tar_member")

        for member in members:
            if not member.isreg():
                continue
            target = dest_dir / member.name
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                _refuse("archive", "unsafe_tar_member")
            extracted = tf.extractfile(member)
            if extracted is None:
                _refuse("archive", "unsafe_tar_member")
            data = extracted.read()
            if len(data) != member.size:
                _refuse("archive", "unsafe_tar_member")
            try:
                fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY | _O_NOFOLLOW, 0o644)
            except OSError:
                _refuse("archive", "unsafe_tar_member")
            try:
                _write_all_bounded(fd, data, "archive", "archive_write_failed")
                try:
                    os.fsync(fd)
                except OSError:
                    _refuse("archive", "archive_write_failed")
            finally:
                os.close(fd)
            if member.mode & 0o111:
                try:
                    os.chmod(target, 0o755)
                except OSError:
                    pass
            try:
                read_fd = os.open(
                    str(target),
                    os.O_RDONLY | _O_NOFOLLOW | _O_NONBLOCK | _O_CLOEXEC,
                )
            except OSError:
                _refuse("archive", "archive_postimage_unavailable")
            try:
                observed = bytearray()
                while len(observed) <= len(data):
                    try:
                        chunk = os.read(read_fd, _READ_CHUNK_BYTES)
                    except OSError:
                        _refuse("archive", "archive_postimage_unavailable")
                    if not chunk:
                        break
                    observed.extend(chunk)
            finally:
                os.close(read_fd)
            observed_bytes = bytes(observed)
            expected_digest = hashlib.sha256(data).hexdigest()
            if len(observed_bytes) != len(data) or hashlib.sha256(observed_bytes).hexdigest() != expected_digest:
                _refuse("archive", "archive_postimage_mismatch")
            inventory_rows.append(
                (
                    member.name[len(nested_prefix) :],
                    expected_digest,
                    len(data),
                    bool(member.mode & 0o111),
                )
            )
    finally:
        tf.close()
    return len(inventory_rows), _archive_inventory_digest(inventory_rows)


def create_ephemeral_archive_origin(
    *,
    repository_git_dir: "str | Path",
    source_commit: str,
    package_root: str,
    scratch_root: "str | Path",
    expected_package_tree_sha: "str | None" = None,
) -> EphemeralGitOriginReceipt:
    if not isinstance(source_commit, str) or _HEX40_RE.fullmatch(source_commit) is None:
        _refuse("source_commit", "invalid_source_commit")

    if not isinstance(package_root, str) or package_root == "" or package_root.startswith("/"):
        _refuse("package_root", "invalid_package_root")
    package_root_parts = package_root.split("/")
    if any(part in ("", ".", "..") for part in package_root_parts):
        _refuse("package_root", "invalid_package_root")

    if expected_package_tree_sha is not None and (
        not isinstance(expected_package_tree_sha, str) or _HEX40_RE.fullmatch(expected_package_tree_sha) is None
    ):
        _refuse("expected_package_tree_sha", "invalid_expected_package_tree_sha")

    git_dir_path = _require_real_directory(
        repository_git_dir, "repository_git_dir", "missing_git_dir", "missing_git_dir"
    )
    git_dir_path = Path(os.path.realpath(str(git_dir_path)))
    git_dir_identity = _lstat_identity(git_dir_path, "repository_git_dir")

    scratch_root_path = _require_real_directory(
        scratch_root, "scratch_root", "scratch_root_unavailable", "scratch_root_unavailable"
    )

    # Prove the commit exists in the LOCAL object store BEFORE archiving or
    # trusting anything derived from it (Sol wave-3 M6): a plain
    # ``git archive`` failure on an absent commit is a less legible refusal
    # than an explicit existence proof up front.
    try:
        exists = (
            subprocess.run(
                ["git", f"--git-dir={git_dir_path}", "cat-file", "-e", f"{source_commit}^{{commit}}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        _refuse("source_commit", "commit_unavailable")
    if not exists:
        _refuse("source_commit", "commit_unavailable")

    # The package SUBTREE sha at this commit (``git rev-parse
    # <commit>:<package_root>``) is exactly what
    # ``CapabilityPackageGeneration.source_tree_sha`` records -- proven here
    # via the local object store, never trusted from caller input.
    source_tree_sha = _git_rev_or_none(git_dir_path, "rev-parse", f"{source_commit}:{package_root}")
    if source_tree_sha is None or _HEX40_RE.fullmatch(source_tree_sha) is None:
        _refuse("package_root", "package_tree_unavailable")

    if expected_package_tree_sha is not None and source_tree_sha != expected_package_tree_sha:
        _refuse("expected_package_tree_sha", "package_tree_sha_mismatch")

    dest_dir = scratch_root_path / f"ephemeral-archive-{secrets.token_hex(16)}"
    try:
        os.mkdir(dest_dir, 0o700)
    except OSError:
        _refuse("scratch_root", "scratch_root_unavailable")

    try:
        archive_bytes = _run_git_archive(git_dir_path, source_commit, package_root)
        member_count, inventory_digest = _extract_safe_tar(
            archive_bytes, dest_dir, package_root
        )
        if member_count <= 0 or not _is_hex64(inventory_digest):
            _refuse("origin_root", "postimage_invalid")
        return EphemeralGitOriginReceipt(
            schema_version=EPHEMERAL_GIT_ORIGIN_SCHEMA_VERSION,
            repository_git_dir=str(git_dir_path),
            repository_git_dir_identity=git_dir_identity,
            source_commit=source_commit,
            source_tree_sha=source_tree_sha,
            package_root=package_root,
            origin_root=str(dest_dir),
            origin_root_identity=_lstat_identity(dest_dir, "origin_root"),
            member_count=member_count,
            archive_digest=hashlib.sha256(archive_bytes).hexdigest(),
            inventory_digest=inventory_digest,
        )
    except SkillProjectionError as exc:
        outcome = _rollback_projection_root(dest_dir)
        raise SkillProjectionError(f"{exc}; {outcome}") from exc
    except Exception as exc:  # noqa: BLE001 -- normalize arbitrary seam text
        outcome = _rollback_projection_root(dest_dir)
        raise SkillProjectionError(f"origin_root: creation_failed; {outcome}") from exc


# ---------------------------------------------------------------------------
# cleanup_skill_projection
# ---------------------------------------------------------------------------


def cleanup_skill_projection(receipt: SkillProjectionReceipt) -> SkillProjectionCleanupReceipt:
    # (1) Receipt self-validation FIRST (Sol wave-3 M6) -- pure shape check,
    # no filesystem access. A structurally invalid receipt (wrong type, bad
    # schema_version, mismatched row sets, malformed identities...) refuses
    # here, before anything below ever inspects a path.
    validate_skill_projection_receipt(receipt)

    projection_root_path = Path(receipt.projection_root)
    expected_name = f"skill-projection-{receipt.owning_process_generation}"

    # (2) Sol wave-3 M6: authorization now binds the exact attempt-root
    # PARENT identity, not merely the projection root's own basename and
    # inode. A fresh no-follow lstat of the projection root's parent
    # directory must equal the receipt's own ``attempt_root_identity`` --
    # any mismatch refuses before anything is touched, let alone removed.
    parent_path = projection_root_path.parent
    try:
        parent_lstat = os.lstat(str(parent_path))
    except (OSError, ValueError):
        _refuse("receipt", "projection_root_parent_unavailable")
    if stat.S_ISLNK(parent_lstat.st_mode) or not stat.S_ISDIR(parent_lstat.st_mode):
        _refuse("receipt", "projection_root_parent_unavailable")
    if (parent_lstat.st_dev, parent_lstat.st_ino) != receipt.attempt_root_identity:
        _refuse("receipt", "projection_root_parent_identity_mismatch")

    # (3) Containment check on the receipt's own value: the projection
    # root's name must still be the exact exclusive name it was minted
    # with, and a fresh no-follow lstat of that exact path must still match
    # the identity recorded at creation time. Either check failing means
    # the receipt no longer (or never did) describe the tree it claims to
    # -- refuse before touching anything.
    if projection_root_path.name != expected_name:
        _refuse("receipt", "projection_root_containment_refused")

    try:
        current_lstat = os.lstat(str(projection_root_path))
    except (OSError, ValueError):
        # Idempotent cleanup: already gone.
        return SkillProjectionCleanupReceipt(
            projection_root=str(projection_root_path),
            removed=True,
            verified_absent=True,
            schema_version=PROJECTION_CLEANUP_SCHEMA_VERSION,
        )

    if stat.S_ISLNK(current_lstat.st_mode) or not stat.S_ISDIR(current_lstat.st_mode):
        _refuse("receipt", "projection_root_containment_refused")

    if (current_lstat.st_dev, current_lstat.st_ino) != receipt.projection_root_identity:
        _refuse("receipt", "projection_root_containment_refused")

    removed = _force_remove_tree(projection_root_path)
    try:
        os.lstat(str(projection_root_path))
        verified_absent = False
    except (OSError, ValueError):
        verified_absent = True

    return SkillProjectionCleanupReceipt(
        projection_root=str(projection_root_path),
        removed=removed and verified_absent,
        verified_absent=verified_absent,
        schema_version=PROJECTION_CLEANUP_SCHEMA_VERSION,
    )
