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
``control_plane.executive_capability_packages`` uses.
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
from pathlib import Path
from typing import NoReturn

from control_plane.executive_capability_packages import (
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

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_HEX40_RE = re.compile(r"[0-9a-f]{40}")

_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)

_READ_CHUNK_BYTES = 65536
_MAX_ARCHIVE_BYTES = 8 * 1024 * 1024


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


@dataclasses.dataclass(frozen=True)
class SkillProjectionCleanupReceipt:
    projection_root: str
    removed: bool
    verified_absent: bool


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
# Descriptor-relative, no-follow package tree copy
# ---------------------------------------------------------------------------


def _read_verified_file(parent_fd: int, name: str, row) -> bytes:
    try:
        fd = os.open(name, os.O_RDONLY | _O_NOFOLLOW | _O_NONBLOCK | _O_CLOEXEC, dir_fd=parent_fd)
    except OSError:
        _refuse("origin_root", "origin_file_unavailable")
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            _refuse("origin_root", "origin_file_unavailable")
        if st.st_size != row.byte_length:
            _refuse("origin_root", "origin_file_drifted")
        actual_executable = bool(st.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        if actual_executable != row.executable:
            _refuse("origin_root", "origin_file_drifted")

        data = bytearray()
        while True:
            try:
                chunk = os.read(fd, _READ_CHUNK_BYTES)
            except OSError:
                _refuse("origin_root", "origin_file_unavailable")
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > row.byte_length:
                _refuse("origin_root", "origin_file_drifted")
        if len(data) != row.byte_length:
            _refuse("origin_root", "origin_file_drifted")
        if hashlib.sha256(bytes(data)).hexdigest() != row.sha256:
            _refuse("origin_root", "origin_file_drifted")
    finally:
        os.close(fd)
    return bytes(data)


def _write_exclusive_file(parent_fd: int, name: str, data: bytes, executable: bool) -> None:
    mode = 0o755 if executable else 0o644
    try:
        fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _O_NOFOLLOW, mode, dir_fd=parent_fd)
    except FileExistsError:
        _refuse("projection_root", "projection_root_exists")
    except OSError:
        _refuse("projection_root", "projection_root_unavailable")
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


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
) -> SkillProjectionReceipt:
    # Law 1: the generation must clear the package module's own trust
    # boundary against the exact origin root BEFORE anything else -- its
    # receipt supplies the verified digests bound into the projection
    # receipt below.
    verified_origin = verify_capability_package_source(origin_root, generation)

    # Law 2.
    if origin_mode not in _ORIGIN_MODES:
        _refuse("origin_mode", "unsupported_value")

    _validate_bounded_token(owning_operation_id, "owning_operation_id")
    _validate_bounded_token(owning_process_generation, "owning_process_generation")

    origin_root_path = _require_real_directory(
        origin_root, "origin_root", "origin_root_unavailable", "origin_root_symlink_refused"
    )
    origin_root_identity = _lstat_identity(origin_root_path, "origin_root")

    # Law 3: attempt_root must exist, be a real non-symlink directory; the
    # projection root is created BELOW it with exclusive mkdir semantics.
    attempt_root_path = _require_real_directory(
        attempt_root, "attempt_root", "attempt_root_unavailable", "attempt_root_symlink_refused"
    )

    projection_dir_name = f"skill-projection-{owning_process_generation}"
    projection_root_path = attempt_root_path / projection_dir_name
    try:
        os.mkdir(projection_root_path, 0o700)
    except FileExistsError:
        _refuse("attempt_root", "projection_root_exists")
    except OSError:
        _refuse("attempt_root", "projection_root_unavailable")

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
    # generation object -- the projection mirrors <root>/<package_root>, so
    # the projection root itself is a lawful source_root.
    verify_capability_package_source(projection_root_path, generation)

    projection_root_identity = _lstat_identity(projection_root_path, "projection_root")
    skills_root = str(projection_root_path / generation.package_root / "skills")

    return SkillProjectionReceipt(
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
    )


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


def _extract_safe_tar(archive_bytes: bytes, dest_dir: Path, package_root: str) -> None:
    if len(archive_bytes) > _MAX_ARCHIVE_BYTES:
        _refuse("archive", "archive_too_large")

    package_root_parts = package_root.split("/")
    ancestor_prefixes = {"/".join(package_root_parts[: i + 1]) for i in range(len(package_root_parts))}
    nested_prefix = package_root.rstrip("/") + "/"

    try:
        tf = tarfile.open(fileobj=io.BytesIO(archive_bytes))
    except tarfile.TarError:
        _refuse("archive", "unsafe_tar_member")

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
                if not (name_norm == package_root or name_norm.startswith(nested_prefix)):
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
                os.write(fd, data)
            finally:
                os.close(fd)
            if member.mode & 0o111:
                try:
                    os.chmod(target, 0o755)
                except OSError:
                    pass
    finally:
        tf.close()


def create_ephemeral_archive_origin(
    *,
    repository_git_dir: "str | Path",
    source_commit: str,
    package_root: str,
    scratch_root: "str | Path",
) -> Path:
    if not isinstance(source_commit, str) or _HEX40_RE.fullmatch(source_commit) is None:
        _refuse("source_commit", "invalid_source_commit")

    if not isinstance(package_root, str) or package_root == "" or package_root.startswith("/"):
        _refuse("package_root", "invalid_package_root")
    package_root_parts = package_root.split("/")
    if any(part in ("", ".", "..") for part in package_root_parts):
        _refuse("package_root", "invalid_package_root")

    git_dir_path = _require_real_directory(
        repository_git_dir, "repository_git_dir", "missing_git_dir", "missing_git_dir"
    )

    scratch_root_path = _require_real_directory(
        scratch_root, "scratch_root", "scratch_root_unavailable", "scratch_root_unavailable"
    )

    dest_dir = scratch_root_path / f"ephemeral-archive-{secrets.token_hex(16)}"
    try:
        os.mkdir(dest_dir, 0o700)
    except OSError:
        _refuse("scratch_root", "scratch_root_unavailable")

    archive_bytes = _run_git_archive(git_dir_path, source_commit, package_root)
    _extract_safe_tar(archive_bytes, dest_dir, package_root)
    return dest_dir


# ---------------------------------------------------------------------------
# cleanup_skill_projection
# ---------------------------------------------------------------------------


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


def cleanup_skill_projection(receipt: SkillProjectionReceipt) -> SkillProjectionCleanupReceipt:
    if type(receipt) is not SkillProjectionReceipt:
        _refuse("receipt", "invalid_receipt")

    projection_root_path = Path(receipt.projection_root)
    expected_name = f"skill-projection-{receipt.owning_process_generation}"

    # Containment check on the receipt's own value: the projection root's
    # name must still be the exact exclusive name it was minted with, and a
    # fresh no-follow lstat of that exact path must still match the identity
    # recorded at creation time. Either check failing means the receipt no
    # longer (or never did) describe the tree it claims to -- refuse before
    # touching anything.
    if projection_root_path.name != expected_name:
        _refuse("receipt", "projection_root_containment_refused")

    try:
        current_lstat = os.lstat(str(projection_root_path))
    except (OSError, ValueError):
        # Idempotent cleanup: already gone.
        return SkillProjectionCleanupReceipt(
            projection_root=str(projection_root_path), removed=True, verified_absent=True
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
    )
