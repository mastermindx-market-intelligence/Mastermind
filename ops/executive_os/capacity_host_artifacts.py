"""Data-only CF2-H0 source transport and closed runtime helpers.

The privileged host preparer accepts only two inert files from the operator:
an exact Git-object transport produced by this module and the pinned PyYAML
wheel.  No caller checkout, Git config, hooks, index, ignored files, or
credential material crosses the privilege boundary.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import csv
import errno
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import struct
import sys
import tempfile
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

try:
    from ops.executive_os.capacity_source_contract import (
        PRODUCER_COMMIT,
        PRODUCER_MATERIAL_PATHS,
        PRODUCER_REPOSITORY,
        SourceClosureEvidence,
        validate_source_closure_evidence,
    )
except ModuleNotFoundError:  # pragma: no cover - direct Apple Python execution
    from capacity_source_contract import (  # type: ignore[no-redef]
        PRODUCER_COMMIT,
        PRODUCER_MATERIAL_PATHS,
        PRODUCER_REPOSITORY,
        SourceClosureEvidence,
        validate_source_closure_evidence,
    )


TRANSPORT_SCHEMA = "mastermind.capacity_source_transport/v1"
TRANSPORT_SCHEMA_V2 = "mastermind.capacity_source_transport/v2"
RECOVERY_INTENT_SCHEMA = "mastermind.executive_capacity_h0_recovery_intent/v1"
RECOVERY_RECEIPT_SCHEMA = "mastermind.executive_capacity_h0_recovery/v1"
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_OBJECT_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_LAUNCHD_LABEL_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_MATERIAL_MODES = frozenset({"100644", "100755"})
_TRANSPORT_MEMBERS = frozenset({"manifest.json", "payload.pack"})
_WHEEL_PREFIXES = ("yaml/", "_yaml/", "pyyaml-6.0.3.dist-info/")
_APPROVED_SYSTEM_XATTRS = frozenset({b"com.apple.provenance"})
_CLOSED_DIRECTORY_MODES = frozenset({0o555, 0o700})
_CLOSED_FILE_MODES = frozenset({0o400, 0o444, 0o555})
_DARWIN_XATTR_LIST_MAX_BYTES = 64 * 1024
_DARWIN_XATTR_ERANGE_RETRIES = 3
_V2_MANIFEST_MAX_BYTES = 1024 * 1024
_V2_PACK_TYPES = frozenset({"commit", "tree", "blob", "tag"})
_V2_CONFIG = (
    b"[core]\n"
    b"\trepositoryformatversion = 0\n"
    b"\tfilemode = true\n"
    b"\tbare = false\n"
    b"\tlogallrefupdates = true\n"
    b"\thooksPath = /dev/null\n"
    b"\tfsmonitor = false\n"
    b"[extensions]\n"
    b"\tworktreeConfig = true\n"
    b"[pack]\n"
    b"\twriteReverseIndex = false\n"
)
_V2_WORKTREE_CONFIG = (
    b"[core]\n"
    b"\tsparseCheckout = true\n"
    b"\tsparseCheckoutCone = false\n"
)
_V2_SPARSE_CHECKOUT = b"".join(
    f"/{path}\n".encode("utf-8") for path in PRODUCER_MATERIAL_PATHS
)
_V2_ZIP32_ERROR = "TRANSPORT_V2_ZIP32_LIMIT_EXCEEDED"


class CapacityHostArtifactError(ValueError):
    """Closed refusal for malformed or unsafe H0 artifacts."""


@dataclass(frozen=True)
class ObjectInventoryRow:
    oid: str
    object_type: str
    size: int

    def encoded(self) -> bytes:
        return f"{self.oid} {self.object_type} {self.size}\n".encode("ascii")


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CapacityHostArtifactError("NON_CANONICAL_JSON") from exc


def parse_launchctl_disabled(output: str, label: str) -> dict[str, str]:
    """Normalize the two exact disabled spellings emitted by supported macOS hosts."""

    if _LAUNCHD_LABEL_RE.fullmatch(label) is None or len(output.encode("utf-8")) > 256 * 1024:
        raise CapacityHostArtifactError("LAUNCHCTL_DISABLED_STATE_INVALID")
    matches: list[str] = []
    for line in output.splitlines():
        match = re.fullmatch(r'\s*"([^"\r\n]+)"\s*=>\s*(\S+)\s*', line)
        if match is not None and match.group(1) == label:
            matches.append(match.group(2))
    if len(matches) != 1 or matches[0] not in {"true", "disabled"}:
        raise CapacityHostArtifactError("LAUNCHCTL_DISABLED_STATE_INVALID")
    return {
        "label": label,
        "normalized_state": "disabled",
        "observed_state": matches[0],
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_bytes_exclusive(path: Path, payload: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, mode)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise CapacityHostArtifactError("SHORT_WRITE")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_descriptor(descriptor: int, maximum_bytes: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    output = bytearray()
    while True:
        chunk = os.read(descriptor, min(64 * 1024, maximum_bytes + 1 - len(output)))
        if not chunk:
            return bytes(output)
        output.extend(chunk)
        if len(output) > maximum_bytes:
            raise CapacityHostArtifactError("CANONICAL_CANDIDATE_TOO_LARGE")


def _validate_canonical_file(
    path: Path,
    payload: bytes,
    *,
    mode: int,
    expected_uid: int,
) -> None:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or path.is_symlink()
        or info.st_nlink != 1
        or info.st_uid != expected_uid
        or stat.S_IMODE(info.st_mode) != mode
        or _extended_attribute_names(path) - _APPROVED_SYSTEM_XATTRS
        or path.read_bytes() != payload
    ):
        raise CapacityHostArtifactError("CANONICAL_FILE_INVALID")


def _publish_resumable_canonical_file(
    path: Path,
    payload: bytes,
    *,
    mode: int,
    expected_uid: int,
) -> None:
    """Publish through a resumable prefix candidate, then fsync its directory."""

    candidate = path.with_name(f".{path.name}.candidate")
    if path.exists() or path.is_symlink():
        if candidate.exists() or candidate.is_symlink():
            raise CapacityHostArtifactError("CANONICAL_PUBLICATION_AMBIGUOUS")
        _validate_canonical_file(path, payload, mode=mode, expected_uid=expected_uid)
        return
    candidate_mode = mode | stat.S_IWUSR
    if candidate.exists() or candidate.is_symlink():
        candidate_info = candidate.lstat()
        if (
            not stat.S_ISREG(candidate_info.st_mode)
            or candidate.is_symlink()
            or candidate_info.st_nlink != 1
            or candidate_info.st_uid != expected_uid
            or stat.S_IMODE(candidate_info.st_mode) not in {mode, candidate_mode}
            or _extended_attribute_names(candidate) - _APPROVED_SYSTEM_XATTRS
        ):
            raise CapacityHostArtifactError("CANONICAL_CANDIDATE_METADATA_INVALID")
        candidate.chmod(candidate_mode)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(candidate, flags, candidate_mode)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != expected_uid
            or stat.S_IMODE(info.st_mode) != candidate_mode
        ):
            raise CapacityHostArtifactError("CANONICAL_CANDIDATE_METADATA_INVALID")
        existing = _read_descriptor(descriptor, len(payload))
        if not payload.startswith(existing):
            raise CapacityHostArtifactError("CANONICAL_CANDIDATE_PREFIX_INVALID")
        os.lseek(descriptor, 0, os.SEEK_END)
        view = memoryview(payload)[len(existing):]
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise CapacityHostArtifactError("SHORT_WRITE")
            view = view[written:]
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if path.exists() or path.is_symlink():
        raise CapacityHostArtifactError("CANONICAL_PUBLICATION_AMBIGUOUS")
    candidate.rename(path)
    _fsync_directory(path.parent)
    _validate_canonical_file(path, payload, mode=mode, expected_uid=expected_uid)


def _canonical_transport_bytes(manifest: Mapping[str, Any], payload: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, body in (
            ("manifest.json", canonical_json(manifest)),
            ("payload.pack", payload),
        ):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o400) << 16
            archive.writestr(info, body)
    return output.getvalue()


def copy_closed_input(
    source: Path,
    destination: Path,
    *,
    operator_uid: int,
    expected_sha256: str,
    maximum_bytes: int = 65 * 1024 * 1024,
) -> dict[str, Any]:
    """Copy one operator file through a no-follow descriptor and bind its bytes."""

    if (
        isinstance(operator_uid, bool)
        or operator_uid < 1
        or _DIGEST_RE.fullmatch(expected_sha256) is None
        or maximum_bytes < 1
    ):
        raise CapacityHostArtifactError("CLOSED_INPUT_ARGUMENT_INVALID")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(source, flags)
    output_descriptor: int | None = None
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != operator_uid
            or stat.S_IMODE(info.st_mode) & 0o022
            or info.st_size > maximum_bytes
        ):
            raise CapacityHostArtifactError("CLOSED_INPUT_METADATA_INVALID")
        output_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        output_descriptor = os.open(destination, output_flags, 0o400)
        if os.geteuid() == 0:
            os.fchown(output_descriptor, 0, 0)
        os.fchmod(output_descriptor, 0o400)
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > maximum_bytes:
                raise CapacityHostArtifactError("CLOSED_INPUT_TOO_LARGE")
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(output_descriptor, view)
                if written <= 0:
                    raise CapacityHostArtifactError("SHORT_WRITE")
                view = view[written:]
        os.fsync(output_descriptor)
        observed = digest.hexdigest()
        if observed != expected_sha256 or size != info.st_size:
            raise CapacityHostArtifactError("CLOSED_INPUT_DIGEST_MISMATCH")
        return {"sha256": observed, "size": size}
    except Exception:
        if output_descriptor is not None:
            os.close(output_descriptor)
            output_descriptor = None
        destination.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)
        if output_descriptor is not None:
            os.close(output_descriptor)


def _extended_attribute_names(path: Path) -> frozenset[bytes]:
    """Inspect one object without following links, using macOS xattr(1) as fallback."""

    listxattr = getattr(os, "listxattr", None)
    if listxattr is not None:
        return frozenset(os.fsencode(name) for name in listxattr(path, follow_symlinks=False))
    if sys.platform != "darwin":
        raise CapacityHostArtifactError("RECOVERY_XATTR_INSPECTION_UNAVAILABLE")
    arguments = ["/usr/bin/xattr"]
    if path.is_symlink():
        arguments.append("-s")
    arguments.append(os.fspath(path))
    completed = subprocess.run(
        arguments,
        capture_output=True,
        check=False,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
        timeout=5,
    )
    if completed.returncode != 0:
        raise CapacityHostArtifactError("RECOVERY_XATTR_INSPECTION_FAILED")
    return frozenset(name for name in completed.stdout.splitlines() if name)


def _descriptor_extended_attribute_names(descriptor: int) -> frozenset[bytes]:
    if sys.platform != "darwin":
        listxattr = getattr(os, "listxattr", None)
        if listxattr is None:
            raise CapacityHostArtifactError("CLOSURE_XATTR_INSPECTION_UNAVAILABLE")
        try:
            return frozenset(os.fsencode(name) for name in listxattr(descriptor))
        except (OSError, TypeError, ValueError) as exc:
            raise CapacityHostArtifactError("CLOSURE_XATTR_INSPECTION_FAILED") from exc
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        flistxattr = libc.flistxattr
    except (AttributeError, OSError) as exc:
        raise CapacityHostArtifactError("CLOSURE_XATTR_INSPECTION_UNAVAILABLE") from exc
    flistxattr.argtypes = [
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_int,
    ]
    flistxattr.restype = ctypes.c_ssize_t
    for _attempt in range(_DARWIN_XATTR_ERANGE_RETRIES):
        ctypes.set_errno(0)
        required = flistxattr(descriptor, None, 0, 0)
        if required < 0:
            raise CapacityHostArtifactError("CLOSURE_XATTR_INSPECTION_FAILED")
        if required == 0:
            return frozenset()
        if required > _DARWIN_XATTR_LIST_MAX_BYTES:
            raise CapacityHostArtifactError("CLOSURE_XATTR_LIST_TOO_LARGE")
        buffer = ctypes.create_string_buffer(required)
        ctypes.set_errno(0)
        observed = flistxattr(descriptor, buffer, required, 0)
        if observed < 0:
            if ctypes.get_errno() == errno.ERANGE:
                continue
            raise CapacityHostArtifactError("CLOSURE_XATTR_INSPECTION_FAILED")
        raw = buffer.raw[:observed]
        if observed > required or not raw.endswith(b"\0"):
            raise CapacityHostArtifactError("CLOSURE_XATTR_LIST_INVALID")
        names = raw[:-1].split(b"\0")
        if (
            any(not name or len(name) > 127 for name in names)
            or len(set(names)) != len(names)
        ):
            raise CapacityHostArtifactError("CLOSURE_XATTR_LIST_INVALID")
        return frozenset(names)
    raise CapacityHostArtifactError("CLOSURE_XATTR_LIST_UNSTABLE")


def _descriptor_has_extended_acl(descriptor: int) -> bool:
    if sys.platform != "darwin":
        return False
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        acl_get_fd_np = libc.acl_get_fd_np
        acl_get_entry = libc.acl_get_entry
        acl_free = libc.acl_free
    except (AttributeError, OSError) as exc:
        raise CapacityHostArtifactError("CLOSURE_ACL_INSPECTION_UNAVAILABLE") from exc
    acl_get_fd_np.argtypes = [ctypes.c_int, ctypes.c_int]
    acl_get_fd_np.restype = ctypes.c_void_p
    acl_get_entry.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    acl_get_entry.restype = ctypes.c_int
    acl_free.argtypes = [ctypes.c_void_p]
    acl_free.restype = ctypes.c_int
    ctypes.set_errno(0)
    acl = acl_get_fd_np(descriptor, 0x00000100)
    if not acl:
        if ctypes.get_errno() == errno.ENOENT:
            return False
        raise CapacityHostArtifactError("CLOSURE_ACL_INSPECTION_UNAVAILABLE")
    try:
        entry = ctypes.c_void_p()
        result = acl_get_entry(acl, 0, ctypes.byref(entry))
        if result == 0:
            return True
        if result == 1:
            return False
        raise CapacityHostArtifactError("CLOSURE_ACL_INSPECTION_FAILED")
    finally:
        if acl_free(acl) != 0:
            raise CapacityHostArtifactError("CLOSURE_ACL_INSPECTION_FAILED")


def _descriptor_sha256(descriptor: int) -> str:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    for chunk in iter(lambda: os.read(descriptor, 1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _descriptor_directory_names(descriptor: int) -> list[str]:
    try:
        with os.scandir(descriptor) as entries:
            names = [entry.name for entry in entries]
    except OSError as exc:
        raise CapacityHostArtifactError("CLOSURE_DIRECTORY_UNREADABLE") from exc
    try:
        ordered_names = sorted(names, key=lambda name: name.encode("utf-8", "strict"))
    except UnicodeEncodeError as exc:
        raise CapacityHostArtifactError("CLOSURE_PATH_INVALID") from exc
    if any(name in {"", ".", ".."} or "/" in name for name in ordered_names):
        raise CapacityHostArtifactError("CLOSURE_PATH_INVALID")
    return ordered_names


def _descriptor_directory_state(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_nlink,
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        info.st_uid,
        info.st_gid,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def closed_tree_digest(
    root: Path,
    *,
    expected_uid: int,
    expected_gid: int,
    approved_xattrs: frozenset[bytes] = frozenset({b"com.apple.provenance"}),
) -> str:
    """Hash one closed tree through no-follow descriptors and exact metadata rows."""

    if (
        isinstance(expected_uid, bool)
        or not isinstance(expected_uid, int)
        or expected_uid < 0
        or isinstance(expected_gid, bool)
        or not isinstance(expected_gid, int)
        or expected_gid < 0
        or not isinstance(approved_xattrs, frozenset)
        or any(not isinstance(name, bytes) for name in approved_xattrs)
        or not approved_xattrs.issubset(_APPROVED_SYSTEM_XATTRS)
    ):
        raise CapacityHostArtifactError("CLOSURE_ARGUMENT_INVALID")

    open_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    rows: list[dict[str, Any]] = []

    def visit(descriptor: int, relative: str) -> None:
        before = os.fstat(descriptor)
        if before.st_uid != expected_uid or before.st_gid != expected_gid:
            raise CapacityHostArtifactError("CLOSURE_OWNER_INVALID")
        if _descriptor_extended_attribute_names(descriptor) - approved_xattrs:
            raise CapacityHostArtifactError("CLOSURE_XATTR_INVALID")
        if _descriptor_has_extended_acl(descriptor):
            raise CapacityHostArtifactError("CLOSURE_ACL_INVALID")
        mode = stat.S_IMODE(before.st_mode)
        if stat.S_ISDIR(before.st_mode):
            if mode not in _CLOSED_DIRECTORY_MODES:
                raise CapacityHostArtifactError("CLOSURE_MODE_INVALID")
            rows.append(
                {
                    "path": relative,
                    "type": "directory",
                    "uid": before.st_uid,
                    "gid": before.st_gid,
                    "mode": f"{mode:04o}",
                    "nlink": before.st_nlink,
                }
            )
            ordered_names = _descriptor_directory_names(descriptor)
            for name in ordered_names:
                child_relative = name if relative == "." else f"{relative}/{name}"
                try:
                    child_descriptor = os.open(
                        name, open_flags, dir_fd=descriptor
                    )
                except OSError as exc:
                    raise CapacityHostArtifactError("CLOSURE_TYPE_INVALID") from exc
                try:
                    visit(child_descriptor, child_relative)
                finally:
                    os.close(child_descriptor)
            after = os.fstat(descriptor)
            final_names = _descriptor_directory_names(descriptor)
            final = os.fstat(descriptor)
            if (
                _descriptor_directory_state(after)
                != _descriptor_directory_state(before)
                or final_names != ordered_names
                or _descriptor_directory_state(final)
                != _descriptor_directory_state(after)
            ):
                raise CapacityHostArtifactError("CLOSURE_DIRECTORY_DRIFT")
        elif stat.S_ISREG(before.st_mode):
            if before.st_nlink != 1:
                raise CapacityHostArtifactError("CLOSURE_LINK_INVALID")
            if mode not in _CLOSED_FILE_MODES:
                raise CapacityHostArtifactError("CLOSURE_MODE_INVALID")
            digest = _descriptor_sha256(descriptor)
            after = os.fstat(descriptor)
            if (
                after.st_dev != before.st_dev
                or after.st_ino != before.st_ino
                or after.st_size != before.st_size
                or after.st_mtime_ns != before.st_mtime_ns
                or after.st_ctime_ns != before.st_ctime_ns
            ):
                raise CapacityHostArtifactError("CLOSURE_FILE_DRIFT")
            rows.append(
                {
                    "path": relative,
                    "type": "file",
                    "uid": before.st_uid,
                    "gid": before.st_gid,
                    "mode": f"{mode:04o}",
                    "nlink": 1,
                    "size": before.st_size,
                    "sha256": digest,
                }
            )
        else:
            raise CapacityHostArtifactError("CLOSURE_TYPE_INVALID")

    try:
        descriptor = os.open(root, open_flags)
    except OSError as exc:
        raise CapacityHostArtifactError("CLOSURE_TYPE_INVALID") from exc
    try:
        visit(descriptor, ".")
    finally:
        os.close(descriptor)
    rows.sort(key=lambda row: row["path"].encode("utf-8"))
    return hashlib.sha256(canonical_json(rows)).hexdigest()


def verify_approved_xattrs(path: Path) -> dict[str, Any]:
    """Reject caller-controlled xattrs while tolerating macOS system provenance."""

    if not path.exists() and not path.is_symlink():
        raise CapacityHostArtifactError("XATTR_ROOT_ABSENT")
    paths = [path]
    if path.is_dir() and not path.is_symlink():
        paths.extend(
            sorted(path.rglob("*"), key=lambda value: value.relative_to(path).as_posix())
        )
    for candidate in paths:
        if _extended_attribute_names(candidate) - _APPROVED_SYSTEM_XATTRS:
            raise CapacityHostArtifactError("UNAPPROVED_EXTENDED_ATTRIBUTE")
    return {
        "approved_system_xattrs": ["com.apple.provenance"],
        "inspected_object_count": len(paths),
    }


def _closed_tree_digest(path: Path, *, expected_uid: int) -> str:
    paths = [path]
    if path.is_dir() and not path.is_symlink():
        paths.extend(
            sorted(path.rglob("*"), key=lambda value: value.relative_to(path).as_posix())
        )
    rows: list[dict[str, Any]] = []
    for candidate in paths:
        info = candidate.lstat()
        relative = "." if candidate == path else candidate.relative_to(path).as_posix()
        if (
            stat.S_ISLNK(info.st_mode)
            or info.st_uid != expected_uid
            or stat.S_IMODE(info.st_mode) & 0o022
            or _extended_attribute_names(candidate) - _APPROVED_SYSTEM_XATTRS
        ):
            raise CapacityHostArtifactError("RECOVERY_OBJECT_INVALID")
        if stat.S_ISDIR(info.st_mode):
            row: dict[str, Any] = {
                "gid": info.st_gid,
                "mode": f"{stat.S_IMODE(info.st_mode):04o}",
                "nlink": info.st_nlink,
                "path": relative,
                "type": "directory",
                "uid": info.st_uid,
            }
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            row = {
                "gid": info.st_gid,
                "mode": f"{stat.S_IMODE(info.st_mode):04o}",
                "nlink": 1,
                "path": relative,
                "sha256": sha256_file(candidate),
                "size": info.st_size,
                "type": "file",
                "uid": info.st_uid,
            }
        else:
            raise CapacityHostArtifactError("RECOVERY_OBJECT_INVALID")
        rows.append(row)
    return hashlib.sha256(canonical_json(rows)).hexdigest()


def create_recovery_intent(
    archive: Path,
    sources: Sequence[Path],
    *,
    expected_uid: int,
) -> dict[str, Any]:
    if not sources or len(set(sources)) != len(sources):
        raise CapacityHostArtifactError("RECOVERY_SOURCE_INVENTORY_INVALID")
    info = archive.lstat()
    intent_path = archive / "recovery-intent.json"
    intent_candidate = archive / ".recovery-intent.json.candidate"
    archive_entries = set(archive.iterdir())
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != expected_uid
        or stat.S_IMODE(info.st_mode) & 0o022
        or archive_entries not in (set(), {intent_candidate})
    ):
        raise CapacityHostArtifactError("RECOVERY_ARCHIVE_INVALID")
    rows = []
    ordered_sources = sorted(sources, key=os.fspath)
    for index, source in enumerate(ordered_sources, start=1):
        if (
            not source.is_absolute()
            or archive in (source, *source.parents)
            or source in (archive, *archive.parents)
        ):
            raise CapacityHostArtifactError("RECOVERY_SOURCE_PATH_INVALID")
        rows.append(
            {
                "destination_name": f"{index}-{source.name}",
                "source_path": os.fspath(source),
                "tree_sha256": _closed_tree_digest(source, expected_uid=expected_uid),
            }
        )
    value = {"schema_version": RECOVERY_INTENT_SCHEMA, "targets": rows}
    _publish_resumable_canonical_file(
        intent_path,
        canonical_json(value) + b"\n",
        mode=0o400,
        expected_uid=expected_uid,
    )
    return value


def resume_recovery_archive(archive: Path, *, expected_uid: int) -> dict[str, Any]:
    intent_path = archive / "recovery-intent.json"
    try:
        intent_bytes = intent_path.read_bytes()
        intent = json.loads(intent_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CapacityHostArtifactError("RECOVERY_INTENT_UNREADABLE") from exc
    if intent_bytes != canonical_json(intent) + b"\n" or set(intent) != {"schema_version", "targets"}:
        raise CapacityHostArtifactError("RECOVERY_INTENT_INVALID")
    targets = intent.get("targets")
    if intent.get("schema_version") != RECOVERY_INTENT_SCHEMA or not isinstance(targets, list) or not targets:
        raise CapacityHostArtifactError("RECOVERY_INTENT_INVALID")
    _validate_canonical_file(intent_path, intent_bytes, mode=0o400, expected_uid=expected_uid)
    expected_fields = {"destination_name", "source_path", "tree_sha256"}
    sources: set[Path] = set()
    destinations: set[Path] = set()
    for index, row in enumerate(targets, start=1):
        if not isinstance(row, Mapping) or set(row) != expected_fields:
            raise CapacityHostArtifactError("RECOVERY_INTENT_ROW_INVALID")
        source = Path(str(row["source_path"]))
        destination = archive / str(row["destination_name"])
        if (
            not source.is_absolute()
            or destination.parent != archive
            or destination.name != f"{index}-{source.name}"
            or _DIGEST_RE.fullmatch(str(row["tree_sha256"])) is None
            or source in sources
            or destination in destinations
        ):
            raise CapacityHostArtifactError("RECOVERY_INTENT_ROW_INVALID")
        sources.add(source)
        destinations.add(destination)
    receipt_path = archive / "recovery-receipt.json"
    receipt_candidate = archive / ".recovery-receipt.json.candidate"
    expected_archive_entries = {intent_path, *destinations}
    observed_archive_entries = set(archive.iterdir())
    if receipt_path in observed_archive_entries:
        expected_archive_entries.add(receipt_path)
    if receipt_candidate in observed_archive_entries:
        expected_archive_entries.add(receipt_candidate)
    if observed_archive_entries - expected_archive_entries:
        raise CapacityHostArtifactError("RECOVERY_ARCHIVE_INVENTORY_INVALID")
    if receipt_path in observed_archive_entries and receipt_candidate in observed_archive_entries:
        raise CapacityHostArtifactError("RECOVERY_RECEIPT_POSITION_AMBIGUOUS")
    if receipt_path in observed_archive_entries or receipt_candidate in observed_archive_entries:
        for row in targets:
            source = Path(str(row["source_path"]))
            destination = archive / str(row["destination_name"])
            if source.exists() or source.is_symlink() or not destination.exists() or destination.is_symlink():
                raise CapacityHostArtifactError("RECOVERY_RECEIPT_POSITION_INVALID")

    for row in targets:
        source = Path(str(row["source_path"]))
        destination = archive / str(row["destination_name"])
        source_present = source.exists() or source.is_symlink()
        destination_present = destination.exists() or destination.is_symlink()
        if source_present == destination_present:
            raise CapacityHostArtifactError("RECOVERY_POSITION_AMBIGUOUS")
        current = source if source_present else destination
        if _closed_tree_digest(current, expected_uid=expected_uid) != row["tree_sha256"]:
            raise CapacityHostArtifactError("RECOVERY_TREE_DIGEST_MISMATCH")
        if source_present:
            source.rename(destination)
            _fsync_directory(source.parent)
            _fsync_directory(archive)
            if _closed_tree_digest(destination, expected_uid=expected_uid) != row["tree_sha256"]:
                raise CapacityHostArtifactError("RECOVERY_TREE_DIGEST_MISMATCH")
    receipt = {
        "schema_version": RECOVERY_RECEIPT_SCHEMA,
        "outcome": "INTERRUPTED_H0_PARTIAL_RECOVERED",
        "intent_sha256": hashlib.sha256(intent_bytes).hexdigest(),
        "recovered_target_count": len(targets),
        "recovered_targets": list(targets),
        "service_state": "labels_disabled_unloaded",
        "socket_state": "nodes_absent",
        "credential_state": "not_read_or_changed",
        "continuation": "same_carrier_preparation_resumed",
    }
    encoded = canonical_json(receipt) + b"\n"
    _publish_resumable_canonical_file(
        receipt_path,
        encoded,
        mode=0o400,
        expected_uid=expected_uid,
    )
    return receipt


def _git_environment() -> dict[str, str]:
    return {
        "HOME": "/var/empty",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_CONFIG_COUNT": "3",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": "/dev/null",
        "GIT_CONFIG_KEY_1": "core.fsmonitor",
        "GIT_CONFIG_VALUE_1": "false",
        "GIT_CONFIG_KEY_2": "core.attributesFile",
        "GIT_CONFIG_VALUE_2": "/dev/null",
    }


def _git(
    repository: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
) -> bytes:
    completed = subprocess.run(
        ["/usr/bin/git", "--no-replace-objects", "-C", os.fspath(repository), *arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
        env=_git_environment(),
    )
    if completed.returncode != 0:
        raise CapacityHostArtifactError("GIT_OBJECT_TRANSPORT_REFUSED")
    return completed.stdout


def _material_rows(
    repository: Path,
    *,
    commit: str,
    material_paths: Sequence[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_path in material_paths:
        candidate = PurePosixPath(raw_path)
        if (
            candidate.is_absolute()
            or not candidate.parts
            or ".." in candidate.parts
            or os.fspath(candidate) != raw_path
        ):
            raise CapacityHostArtifactError("MATERIAL_PATH_INVALID")
        output = _git(repository, "ls-tree", "-z", commit, "--", raw_path)
        values = output.rstrip(b"\0").split(b"\t", 1)
        if len(values) != 2 or values[1].decode("utf-8", "strict") != raw_path:
            raise CapacityHostArtifactError("MATERIAL_PATH_MISSING")
        header = values[0].decode("ascii", "strict").split()
        if len(header) != 3 or header[0] not in _MATERIAL_MODES or header[1] != "blob":
            raise CapacityHostArtifactError("MATERIAL_OBJECT_INVALID")
        object_id = header[2]
        if _OBJECT_RE.fullmatch(object_id) is None:
            raise CapacityHostArtifactError("MATERIAL_OBJECT_INVALID")
        payload = _git(repository, "cat-file", "blob", object_id)
        rows.append(
            {
                "path": raw_path,
                "mode": header[0],
                "git_blob": object_id,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
            }
        )
    if [row["path"] for row in rows] != sorted({row["path"] for row in rows}):
        raise CapacityHostArtifactError("MATERIAL_PATH_ORDER_INVALID")
    return rows


def build_source_transport(
    source_repository: Path,
    output: Path,
    *,
    commit: str,
    material_paths: Sequence[str],
) -> dict[str, Any]:
    """Build one data-only ZIP containing a narrow Git pack and closed manifest."""

    if _COMMIT_RE.fullmatch(commit) is None:
        raise CapacityHostArtifactError("COMMIT_INVALID")
    source = source_repository.resolve(strict=True)
    if output.exists() or output.is_symlink():
        raise CapacityHostArtifactError("OUTPUT_EXISTS")
    observed_commit = _git(source, "rev-parse", f"{commit}^{{commit}}").decode().strip()
    if observed_commit != commit:
        raise CapacityHostArtifactError("COMMIT_MISMATCH")
    rows = _material_rows(source, commit=commit, material_paths=material_paths)

    graph_objects = _git(
        source,
        "rev-list",
        "--objects",
        "--filter=blob:none",
        "--no-object-names",
        "--max-count=1",
        commit,
    ).decode("ascii", "strict").splitlines()
    object_ids = sorted(set(graph_objects) | {str(row["git_blob"]) for row in rows})
    if not object_ids or any(_OBJECT_RE.fullmatch(value) is None for value in object_ids):
        raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID")
    payload = _git(
        source,
        "pack-objects",
        "--stdout",
        input_bytes=("\n".join(object_ids) + "\n").encode("ascii"),
    )
    if not payload.startswith(b"PACK"):
        raise CapacityHostArtifactError("PACK_INVALID")
    manifest = {
        "schema_version": TRANSPORT_SCHEMA,
        "repository": "mastermindx-market-intelligence/macro",
        "commit": commit,
        "object_format": "sha1",
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "material": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        _write_bytes_exclusive(output, _canonical_transport_bytes(manifest, payload), 0o600)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return manifest


def validate_transport_manifest(
    value: Any,
    *,
    expected_commit: str,
    material_paths: Sequence[str],
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "repository",
        "commit",
        "object_format",
        "payload_sha256",
        "material",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise CapacityHostArtifactError("TRANSPORT_MANIFEST_FIELDS_INVALID")
    if (
        value.get("schema_version") != TRANSPORT_SCHEMA
        or value.get("repository") != "mastermindx-market-intelligence/macro"
        or value.get("commit") != expected_commit
        or value.get("object_format") != "sha1"
        or _DIGEST_RE.fullmatch(str(value.get("payload_sha256"))) is None
    ):
        raise CapacityHostArtifactError("TRANSPORT_MANIFEST_MISMATCH")
    rows = value.get("material")
    if not isinstance(rows, list) or [row.get("path") for row in rows if isinstance(row, Mapping)] != list(material_paths):
        raise CapacityHostArtifactError("TRANSPORT_MATERIAL_INVENTORY_INVALID")
    row_fields = {"path", "mode", "git_blob", "sha256", "size"}
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or set(row) != row_fields
            or row.get("mode") not in _MATERIAL_MODES
            or _OBJECT_RE.fullmatch(str(row.get("git_blob"))) is None
            or _DIGEST_RE.fullmatch(str(row.get("sha256"))) is None
            or isinstance(row.get("size"), bool)
            or not isinstance(row.get("size"), int)
            or row["size"] < 0
        ):
            raise CapacityHostArtifactError("TRANSPORT_MATERIAL_ROW_INVALID")
    return dict(value)


def extract_source_transport(
    archive_path: Path,
    destination: Path,
    *,
    expected_commit: str,
    material_paths: Sequence[str],
) -> dict[str, Any]:
    """Validate and extract exactly manifest.json and payload.pack."""

    archive_info = archive_path.lstat()
    if (
        not stat.S_ISREG(archive_info.st_mode)
        or archive_info.st_nlink != 1
        or archive_info.st_size > 65 * 1024 * 1024
    ):
        raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_FILE_INVALID")
    try:
        destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    except Exception:
        os.close(archive_descriptor)
        raise
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            if {info.filename for info in infos} != _TRANSPORT_MEMBERS or len(infos) != 2:
                raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_INVENTORY_INVALID")
            for info in infos:
                mode = info.external_attr >> 16
                if (
                    not stat.S_ISREG(mode)
                    or stat.S_IMODE(mode) != 0o400
                    or info.flag_bits & 0x1
                    or info.compress_type != zipfile.ZIP_STORED
                    or info.file_size > 64 * 1024 * 1024
                    or info.compress_size != info.file_size
                ):
                    raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_MEMBER_INVALID")
            manifest_bytes = archive.read("manifest.json")
            manifest = validate_transport_manifest(
                json.loads(manifest_bytes),
                expected_commit=expected_commit,
                material_paths=material_paths,
            )
            payload = archive.read("payload.pack")
        if manifest_bytes != canonical_json(manifest):
            raise CapacityHostArtifactError("TRANSPORT_MANIFEST_NONCANONICAL")
        if hashlib.sha256(payload).hexdigest() != manifest["payload_sha256"]:
            raise CapacityHostArtifactError("TRANSPORT_PAYLOAD_DIGEST_MISMATCH")
        if archive_path.read_bytes() != _canonical_transport_bytes(manifest, payload):
            raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_NONCANONICAL")
        for name, body in (
            ("manifest.json", canonical_json(manifest)),
            ("payload.pack", payload),
        ):
            target = destination / name
            _write_bytes_exclusive(target, body, 0o400)
        return manifest
    except Exception:
        for child in destination.iterdir():
            child.unlink(missing_ok=True)
        destination.rmdir()
        raise


def _run_git(
    repository: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
) -> bytes:
    completed = subprocess.run(
        ["/usr/bin/git", "--no-replace-objects", "-C", os.fspath(repository), *arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
        env=_git_environment(),
    )
    if completed.returncode != 0:
        raise CapacityHostArtifactError("GIT_MATERIALIZATION_REFUSED")
    return completed.stdout


def verify_materialized_source(
    source_root: Path,
    *,
    manifest: Mapping[str, Any],
) -> None:
    """Prove the checkout has only exact reviewed material blobs."""

    commit = str(manifest["commit"])
    if _run_git(source_root, "rev-parse", "HEAD").decode().strip() != commit:
        raise CapacityHostArtifactError("SOURCE_HEAD_MISMATCH")
    if _run_git(source_root, "branch", "--show-current").strip():
        raise CapacityHostArtifactError("SOURCE_HEAD_ATTACHED")
    if _run_git(source_root, "remote").strip():
        raise CapacityHostArtifactError("SOURCE_REMOTE_PRESENT")
    expected_paths = [str(row["path"]) for row in manifest["material"]]
    observed_paths = sorted(
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*")
        if ".git" not in path.relative_to(source_root).parts and path.is_file()
    )
    if observed_paths != expected_paths:
        raise CapacityHostArtifactError("SOURCE_WORKTREE_INVENTORY_MISMATCH")
    for row in manifest["material"]:
        path = source_root / str(row["path"])
        info = path.lstat()
        expected_modes = {0o755, 0o555} if row["mode"] == "100755" else {0o644, 0o444}
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) not in expected_modes
            or info.st_size != row["size"]
            or sha256_file(path) != row["sha256"]
        ):
            raise CapacityHostArtifactError("SOURCE_WORKTREE_FILE_MISMATCH")
        observed_blob = _run_git(source_root, "hash-object", "--no-filters", os.fspath(path)).decode().strip()
        tree_line = _run_git(source_root, "ls-tree", "-z", commit, "--", str(row["path"]))
        if observed_blob != row["git_blob"] or f" {row['git_blob']}\t".encode() not in tree_line:
            raise CapacityHostArtifactError("SOURCE_GIT_BLOB_MISMATCH")
    status = _run_git(source_root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise CapacityHostArtifactError("SOURCE_WORKTREE_DIRTY")


def materialize_source_transport(
    archive_path: Path,
    source_root: Path,
    *,
    expected_commit: str,
    material_paths: Sequence[str],
) -> dict[str, Any]:
    """Create a fresh repository from the inert pack; never copy caller Git state."""

    transport = source_root.with_name(f".{source_root.name}.transport")
    if source_root.exists() or source_root.is_symlink() or transport.exists():
        raise CapacityHostArtifactError("SOURCE_DESTINATION_EXISTS")
    manifest = extract_source_transport(
        archive_path,
        transport,
        expected_commit=expected_commit,
        material_paths=material_paths,
    )
    try:
        source_root.mkdir(mode=0o700, parents=False, exist_ok=False)
        _run_git(source_root, "init", "--quiet")
        _run_git(source_root, "config", "core.hooksPath", "/dev/null")
        _run_git(source_root, "config", "core.fsmonitor", "false")
        for hook in (source_root / ".git" / "hooks").iterdir():
            if not hook.is_file() or hook.is_symlink():
                raise CapacityHostArtifactError("SOURCE_DEFAULT_HOOK_INVENTORY_INVALID")
            hook.chmod(0o400)
        pack_output = _run_git(
            source_root,
            "index-pack",
            "--stdin",
            "--fix-thin",
            input_bytes=(transport / "payload.pack").read_bytes(),
        ).decode("ascii", "strict").strip()
        match = re.fullmatch(r"(?:pack\s+)?([0-9a-f]{40})", pack_output)
        if match is None:
            raise CapacityHostArtifactError("SOURCE_PACK_IDENTITY_INVALID")
        pack_base = source_root / ".git" / "objects" / "pack" / f"pack-{match.group(1)}"
        if not pack_base.with_suffix(".pack").is_file() or not pack_base.with_suffix(".idx").is_file():
            raise CapacityHostArtifactError("SOURCE_PACK_INSTALL_INVALID")
        pack_base.with_suffix(".promisor").write_bytes(b"")

        _run_git(source_root, "config", "extensions.partialClone", "cf2h0-offline")
        _run_git(source_root, "config", "extensions.worktreeConfig", "true")
        _run_git(source_root, "config", "--worktree", "core.sparseCheckout", "true")
        _run_git(source_root, "config", "--worktree", "core.sparseCheckoutCone", "false")
        sparse = source_root / ".git" / "info" / "sparse-checkout"
        sparse.write_text("".join(f"/{path}\n" for path in material_paths), encoding="utf-8")
        _run_git(source_root, "checkout", "--detach", expected_commit)
        for row in manifest["material"]:
            material_path = source_root / str(row["path"])
            descriptor = os.open(
                material_path,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
            )
            try:
                material_info = os.fstat(descriptor)
                if not stat.S_ISREG(material_info.st_mode) or material_info.st_nlink != 1:
                    raise CapacityHostArtifactError("SOURCE_WORKTREE_FILE_MISMATCH")
                os.fchmod(descriptor, 0o755 if row["mode"] == "100755" else 0o644)
            finally:
                os.close(descriptor)
        (source_root / ".git" / "cf2-h0-transport-manifest.json").write_bytes(
            canonical_json(manifest)
        )
        _run_git(source_root, "fsck", "--full", "--strict", "--no-progress")
        verify_materialized_source(source_root, manifest=manifest)
        return manifest
    except Exception:
        raise
    finally:
        for child in transport.iterdir():
            child.unlink(missing_ok=True)
        transport.rmdir()


def _inventory_digest(rows: Sequence[ObjectInventoryRow]) -> str:
    return hashlib.sha256(b"".join(row.encoded() for row in rows)).hexdigest()


def _source_common_git_directory(repository: Path) -> Path:
    raw = _git(repository, "rev-parse", "--git-common-dir").decode("utf-8", "strict").strip()
    if not raw or "\0" in raw or "\r" in raw or "\n" in raw:
        raise CapacityHostArtifactError("SOURCE_GIT_DIRECTORY_INVALID")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = repository / candidate
    return candidate.resolve(strict=True)


def _path_lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _read_small_nofollow(path: Path, maximum_bytes: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CapacityHostArtifactError("SOURCE_METADATA_INVALID") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        return _read_descriptor(descriptor, maximum_bytes)
    finally:
        os.close(descriptor)


def _refuse_ambient_object_sources(repository: Path) -> None:
    """Refuse ambient object graph inputs that Git environment variables cannot erase."""

    git_dir = _source_common_git_directory(repository)
    alternates = git_dir / "objects" / "info" / "alternates"
    grafts = git_dir / "info" / "grafts"
    shallow = git_dir / "shallow"
    if any(_path_lstat(path) is not None for path in (alternates, grafts, shallow)):
        raise CapacityHostArtifactError("SOURCE_AMBIENT_OBJECT_STATE_PRESENT")
    replace = git_dir / "refs" / "replace"
    replace_info = _path_lstat(replace)
    if replace_info is not None:
        if not stat.S_ISDIR(replace_info.st_mode) or any(replace.iterdir()):
            raise CapacityHostArtifactError("SOURCE_REPLACEMENT_REF_PRESENT")
    packed_refs = git_dir / "packed-refs"
    if _path_lstat(packed_refs) is not None:
        if b"refs/replace/" in _read_small_nofollow(packed_refs, 16 * 1024 * 1024):
            raise CapacityHostArtifactError("SOURCE_REPLACEMENT_REF_PRESENT")
    pack_dir = git_dir / "objects" / "pack"
    if pack_dir.is_dir() and any(path.name.endswith(".promisor") for path in pack_dir.iterdir()):
        raise CapacityHostArtifactError("SOURCE_PROMISOR_STATE_PRESENT")
    config = git_dir / "config"
    if _path_lstat(config) is not None:
        lowered = _read_small_nofollow(config, 16 * 1024 * 1024).lower()
        if b"partialclone" in lowered or b"promisor" in lowered:
            raise CapacityHostArtifactError("SOURCE_PROMISOR_STATE_PRESENT")


def enumerate_reachable_objects(
    repository: Path, commit: str
) -> tuple[ObjectInventoryRow, ...]:
    """Return the exact semantic inventory reachable from one commit, or refuse missing state."""

    if _COMMIT_RE.fullmatch(commit) is None:
        raise CapacityHostArtifactError("COMMIT_INVALID")
    source = repository.resolve(strict=True)
    _refuse_ambient_object_sources(source)
    observed_commit = _git(source, "rev-parse", f"{commit}^{{commit}}").decode().strip()
    if observed_commit != commit:
        raise CapacityHostArtifactError("COMMIT_MISMATCH")
    raw_objects = _git(
        source,
        "rev-list",
        "--objects",
        "--no-object-names",
        "--missing=print",
        commit,
    ).decode("ascii", "strict").splitlines()
    if (
        not raw_objects
        or any(value.startswith("?") for value in raw_objects)
        or any(_OBJECT_RE.fullmatch(value) is None for value in raw_objects)
        or len(set(raw_objects)) != len(raw_objects)
    ):
        raise CapacityHostArtifactError("OBJECT_CLOSURE_MISSING")
    object_ids = sorted(raw_objects)
    checked = _git(
        source,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_bytes=("\n".join(object_ids) + "\n").encode("ascii"),
    ).decode("ascii", "strict").splitlines()
    if len(checked) != len(object_ids):
        raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID")
    rows: list[ObjectInventoryRow] = []
    for expected_oid, line in zip(object_ids, checked):
        fields = line.split(" ")
        if len(fields) != 3 or fields[0] != expected_oid or fields[1] not in _V2_PACK_TYPES:
            raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID")
        try:
            size = int(fields[2], 10)
        except ValueError as exc:
            raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID") from exc
        if size < 0 or str(size) != fields[2]:
            raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID")
        rows.append(ObjectInventoryRow(expected_oid, fields[1], size))
    return tuple(rows)


def _write_complete_pack(
    repository: Path, rows: Sequence[ObjectInventoryRow], output: Path
) -> None:
    object_input = b"".join(f"{row.oid}\n".encode("ascii") for row in rows)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(output, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            completed = subprocess.run(
                [
                    "/usr/bin/git",
                    "--no-replace-objects",
                    "-C",
                    os.fspath(repository),
                    "pack-objects",
                    "--stdout",
                ],
                input=object_input,
                stdout=handle,
                stderr=subprocess.PIPE,
                check=False,
                env=_git_environment(),
            )
            handle.flush()
        if completed.returncode != 0:
            raise CapacityHostArtifactError("GIT_OBJECT_TRANSPORT_REFUSED")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validate_pack_file(path: Path, *, expected_count: int) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CapacityHostArtifactError("PACK_INVALID") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size < 32:
            raise CapacityHostArtifactError("PACK_INVALID")
        header = os.read(descriptor, 12)
        if len(header) != 12 or header[:4] != b"PACK":
            raise CapacityHostArtifactError("PACK_INVALID")
        version, count = struct.unpack(">II", header[4:])
        if version not in {2, 3} or count != expected_count:
            raise CapacityHostArtifactError("PACK_OBJECT_INVENTORY_MISMATCH")
        content_size = before.st_size - 20
        os.lseek(descriptor, 0, os.SEEK_SET)
        digest = hashlib.sha1()
        remaining = content_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise CapacityHostArtifactError("PACK_INVALID")
            digest.update(chunk)
            remaining -= len(chunk)
        trailer = os.read(descriptor, 21)
        after = os.fstat(descriptor)
        if (
            len(trailer) != 20
            or trailer != digest.digest()
            or after.st_dev != before.st_dev
            or after.st_ino != before.st_ino
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or after.st_ctime_ns != before.st_ctime_ns
        ):
            raise CapacityHostArtifactError("PACK_TRAILER_INVALID")
    finally:
        os.close(descriptor)


def _zip_info(name: str, *, size: int = 0) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (stat.S_IFREG | 0o400) << 16
    info.file_size = size
    return info


def _require_v2_zip32_size(size: int) -> None:
    # This is the exact preflight used by ZipFile.open(..., force_zip64=False).
    if size < 0 or size * 1.05 > zipfile.ZIP64_LIMIT:
        raise CapacityHostArtifactError(_V2_ZIP32_ERROR)


def _write_transport_v2_archive(
    output: Path, manifest: Mapping[str, Any], payload_path: Path
) -> None:
    payload_size = payload_path.stat().st_size
    manifest_bytes = canonical_json(manifest)
    _require_v2_zip32_size(len(manifest_bytes))
    _require_v2_zip32_size(payload_size)
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(output, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w+b", closefd=False) as raw:
            try:
                with zipfile.ZipFile(
                    raw,
                    "w",
                    compression=zipfile.ZIP_STORED,
                    allowZip64=False,
                ) as archive:
                    archive.writestr(
                        _zip_info("manifest.json", size=len(manifest_bytes)),
                        manifest_bytes,
                    )
                    with payload_path.open("rb") as source, archive.open(
                        _zip_info("payload.pack", size=payload_size), "w"
                    ) as target:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            target.write(chunk)
            except zipfile.LargeZipFile as exc:
                raise CapacityHostArtifactError(_V2_ZIP32_ERROR) from exc
            raw.flush()
        os.fsync(descriptor)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def build_source_transport_v2(
    source_repository: Path,
    output: Path,
    *,
    commit: str,
) -> dict[str, Any]:
    """Build the complete v2 pack with frozen CF1 projection and semantic closure identity."""

    if commit != PRODUCER_COMMIT or _COMMIT_RE.fullmatch(commit) is None:
        raise CapacityHostArtifactError("COMMIT_MISMATCH")
    if output.exists() or output.is_symlink():
        raise CapacityHostArtifactError("OUTPUT_EXISTS")
    source = source_repository.resolve(strict=True)
    rows = enumerate_reachable_objects(source, commit)
    material = _material_rows(
        source, commit=commit, material_paths=PRODUCER_MATERIAL_PATHS
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.payload-", dir=os.fspath(output.parent)
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    try:
        _write_complete_pack(source, rows, temporary)
        _validate_pack_file(temporary, expected_count=len(rows))
        manifest = {
            "schema_version": TRANSPORT_SCHEMA_V2,
            "repository": PRODUCER_REPOSITORY,
            "commit": commit,
            "object_format": "sha1",
            "closure_kind": "complete_reachable_commit_graph",
            "payload_sha256": sha256_file(temporary),
            "object_count": len(rows),
            "object_inventory_sha256": _inventory_digest(rows),
            "material": material,
        }
        _write_transport_v2_archive(output, manifest, temporary)
        return manifest
    except Exception:
        output.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)


def validate_transport_manifest_v2(
    value: Any, *, expected_commit: str
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "repository",
        "commit",
        "object_format",
        "closure_kind",
        "payload_sha256",
        "object_count",
        "object_inventory_sha256",
        "material",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise CapacityHostArtifactError("TRANSPORT_V2_MANIFEST_FIELDS_INVALID")
    count = value.get("object_count")
    if (
        expected_commit != PRODUCER_COMMIT
        or value.get("schema_version") != TRANSPORT_SCHEMA_V2
        or value.get("repository") != PRODUCER_REPOSITORY
        or value.get("commit") != expected_commit
        or value.get("object_format") != "sha1"
        or value.get("closure_kind") != "complete_reachable_commit_graph"
        or _DIGEST_RE.fullmatch(str(value.get("payload_sha256"))) is None
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 1
        or _DIGEST_RE.fullmatch(str(value.get("object_inventory_sha256"))) is None
    ):
        raise CapacityHostArtifactError("TRANSPORT_V2_MANIFEST_MISMATCH")
    rows = value.get("material")
    if (
        not isinstance(rows, list)
        or [row.get("path") for row in rows if isinstance(row, Mapping)]
        != list(PRODUCER_MATERIAL_PATHS)
    ):
        raise CapacityHostArtifactError("TRANSPORT_MATERIAL_INVENTORY_INVALID")
    row_fields = {"path", "mode", "git_blob", "sha256", "size"}
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or set(row) != row_fields
            or row.get("mode") not in _MATERIAL_MODES
            or _OBJECT_RE.fullmatch(str(row.get("git_blob"))) is None
            or _DIGEST_RE.fullmatch(str(row.get("sha256"))) is None
            or isinstance(row.get("size"), bool)
            or not isinstance(row.get("size"), int)
            or row["size"] < 0
        ):
            raise CapacityHostArtifactError("TRANSPORT_MATERIAL_ROW_INVALID")
    return dict(value)


def _validate_transport_v2_zip_layout(
    descriptor: int,
    infos: Sequence[zipfile.ZipInfo],
    *,
    manifest_bytes: bytes,
    payload_crc32: int,
) -> None:
    if [info.filename for info in infos] != ["manifest.json", "payload.pack"]:
        raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_INVENTORY_INVALID")
    crcs = (zlib.crc32(manifest_bytes) & 0xFFFFFFFF, payload_crc32)
    local_offset = 0
    central_records: list[bytes] = []
    for info, expected_crc in zip(infos, crcs):
        name = info.filename.encode("ascii")
        _require_v2_zip32_size(info.file_size)
        local_header = struct.pack(
            "<IHHHHHIIIHH",
            0x04034B50,
            20,
            0,
            zipfile.ZIP_STORED,
            0,
            33,
            expected_crc,
            info.file_size,
            info.file_size,
            len(name),
            0,
        ) + name
        if info.header_offset != local_offset or os.pread(
            descriptor, len(local_header), local_offset
        ) != local_header:
            raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_NONCANONICAL")
        data_offset = local_offset + len(local_header)
        if info.filename == "manifest.json" and os.pread(
            descriptor, len(manifest_bytes), data_offset
        ) != manifest_bytes:
            raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_NONCANONICAL")
        central_records.append(
            struct.pack(
                "<IHHHHHHIIIHHHHHII",
                0x02014B50,
                (3 << 8) | 20,
                20,
                0,
                zipfile.ZIP_STORED,
                0,
                33,
                expected_crc,
                info.file_size,
                info.file_size,
                len(name),
                0,
                0,
                0,
                0,
                (stat.S_IFREG | 0o400) << 16,
                local_offset,
            )
            + name
        )
        local_offset = data_offset + info.file_size
    central = b"".join(central_records)
    eocd = struct.pack(
        "<IHHHHIIH",
        0x06054B50,
        0,
        0,
        len(infos),
        len(infos),
        len(central),
        local_offset,
        0,
    )
    expected_tail = central + eocd
    before = os.fstat(descriptor)
    if (
        os.pread(descriptor, len(expected_tail), local_offset) != expected_tail
        or before.st_size != local_offset + len(expected_tail)
    ):
        raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_NONCANONICAL")


def _stream_zip_member(
    archive: zipfile.ZipFile, name: str, destination: Path
) -> tuple[str, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(destination, flags, 0o400)
    digest = hashlib.sha256()
    crc32 = 0
    try:
        with archive.open(name, "r") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
                crc32 = zlib.crc32(chunk, crc32)
                view = memoryview(chunk)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise CapacityHostArtifactError("SHORT_WRITE")
                    view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return digest.hexdigest(), crc32 & 0xFFFFFFFF


def extract_source_transport_v2(
    archive_path: Path,
    destination: Path,
    *,
    expected_commit: str,
) -> dict[str, Any]:
    """Stream and validate the exact two-member complete transport."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    archive_descriptor = os.open(archive_path, flags)
    archive_info = os.fstat(archive_descriptor)
    if not stat.S_ISREG(archive_info.st_mode) or archive_info.st_nlink != 1 or (
        stat.S_IMODE(archive_info.st_mode) & 0o022
    ):
        os.close(archive_descriptor)
        raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_FILE_INVALID")
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        with os.fdopen(os.dup(archive_descriptor), "rb") as raw:
            with zipfile.ZipFile(raw, "r") as archive:
                infos = archive.infolist()
                if [info.filename for info in infos] != ["manifest.json", "payload.pack"]:
                    raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_INVENTORY_INVALID")
                for info in infos:
                    mode = info.external_attr >> 16
                    if (
                        info.date_time != (1980, 1, 1, 0, 0, 0)
                        or info.create_system != 3
                        or not stat.S_ISREG(mode)
                        or stat.S_IMODE(mode) != 0o400
                        or info.flag_bits != 0
                        or info.compress_type != zipfile.ZIP_STORED
                        or info.compress_size != info.file_size
                        or info.extra != b""
                        or info.comment != b""
                    ):
                        raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_MEMBER_INVALID")
                    _require_v2_zip32_size(info.file_size)
                with archive.open("manifest.json", "r") as manifest_source:
                    manifest_bytes = manifest_source.read(_V2_MANIFEST_MAX_BYTES + 1)
                if len(manifest_bytes) > _V2_MANIFEST_MAX_BYTES:
                    raise CapacityHostArtifactError("TRANSPORT_MANIFEST_TOO_LARGE")
                manifest = validate_transport_manifest_v2(
                    json.loads(manifest_bytes), expected_commit=expected_commit
                )
                if manifest_bytes != canonical_json(manifest):
                    raise CapacityHostArtifactError("TRANSPORT_MANIFEST_NONCANONICAL")
                _write_bytes_exclusive(destination / "manifest.json", manifest_bytes, 0o400)
                observed_payload, payload_crc32 = _stream_zip_member(
                    archive, "payload.pack", destination / "payload.pack"
                )
                _validate_transport_v2_zip_layout(
                    archive_descriptor,
                    infos,
                    manifest_bytes=manifest_bytes,
                    payload_crc32=payload_crc32,
                )
        after = os.fstat(archive_descriptor)
        if _descriptor_directory_state(archive_info) != _descriptor_directory_state(after):
            raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_FILE_INVALID")
        if observed_payload != manifest["payload_sha256"]:
            raise CapacityHostArtifactError("TRANSPORT_PAYLOAD_DIGEST_MISMATCH")
        _validate_pack_file(
            destination / "payload.pack", expected_count=manifest["object_count"]
        )
        return manifest
    except Exception:
        if destination.exists():
            for child in destination.iterdir():
                child.unlink(missing_ok=True)
            destination.rmdir()
        raise
    finally:
        os.close(archive_descriptor)


def _run_git_file_input(repository: Path, input_path: Path, *arguments: str) -> bytes:
    with input_path.open("rb") as source:
        completed = subprocess.run(
            ["/usr/bin/git", "--no-replace-objects", "-C", os.fspath(repository), *arguments],
            stdin=source,
            capture_output=True,
            check=False,
            env=_git_environment(),
        )
    if completed.returncode != 0:
        raise CapacityHostArtifactError("GIT_MATERIALIZATION_REFUSED")
    return completed.stdout


def _normalize_complete_repository_modes(source_root: Path) -> None:
    executable_paths = {
        os.fspath(source_root / str(row))
        for row in PRODUCER_MATERIAL_PATHS
        if str(row).startswith("scripts/")
    }
    for current, directory_names, file_names in os.walk(
        source_root, topdown=False, followlinks=False
    ):
        current_path = Path(current)
        for name in file_names:
            path = current_path / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_nlink != 1:
                raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
            path.chmod(0o555 if os.fspath(path) in executable_paths else 0o444)
        for name in directory_names:
            path = current_path / name
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or path.is_symlink():
                raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
            path.chmod(0o555)
    source_root.chmod(0o555)


def _read_verified_metadata_file(
    path: Path, *, expected_uid: int, expected_gid: int, maximum_bytes: int
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CapacityHostArtifactError("SOURCE_METADATA_INVALID") from exc
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != expected_uid
            or info.st_gid != expected_gid
            or stat.S_IMODE(info.st_mode) != 0o444
            or _descriptor_extended_attribute_names(descriptor) - _APPROVED_SYSTEM_XATTRS
            or _descriptor_has_extended_acl(descriptor)
        ):
            raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        return _read_descriptor(descriptor, maximum_bytes)
    finally:
        os.close(descriptor)


def _refuse_optional_lock(path: Path) -> None:
    if _path_lstat(path.with_name(f"{path.name}.lock")) is not None:
        raise CapacityHostArtifactError("SOURCE_METADATA_LOCK_PRESENT")


def _repository_snapshot_state(info: os.stat_result) -> tuple[int, ...]:
    return _descriptor_directory_state(info) + (info.st_size,)


class _RepositoryView:
    """Retained descriptor graph that makes transient pathname swaps observable."""

    def __init__(self, source_root: Path) -> None:
        absolute = source_root.absolute()
        parent_flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        self.parent_descriptor = os.open(absolute.parent, parent_flags)
        self.root_name = absolute.name
        self.descriptors: dict[str, int] = {}
        self.states: dict[str, tuple[int, ...]] = {}
        self.directory_names: dict[str, tuple[str, ...]] = {}
        self.parents: dict[str, tuple[str, str]] = {}
        try:
            root_descriptor = os.open(
                self.root_name, parent_flags, dir_fd=self.parent_descriptor
            )
            self.root_descriptor = root_descriptor
            self._retain(".", root_descriptor)
            self.root_relation_state = self.states["."]
        except Exception:
            self.close()
            raise

    def _retain(self, relative: str, descriptor: int) -> None:
        info = os.fstat(descriptor)
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        self.descriptors[relative] = descriptor
        self.states[relative] = _repository_snapshot_state(info)
        if not stat.S_ISDIR(info.st_mode):
            return
        names = tuple(_descriptor_directory_names(descriptor))
        self.directory_names[relative] = names
        for name in names:
            child = name if relative == "." else f"{relative}/{name}"
            child_info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISLNK(child_info.st_mode) or not (
                stat.S_ISDIR(child_info.st_mode) or stat.S_ISREG(child_info.st_mode)
            ):
                raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
            if stat.S_ISDIR(child_info.st_mode):
                flags |= getattr(os, "O_DIRECTORY", 0)
            else:
                flags |= getattr(os, "O_NONBLOCK", 0)
            child_descriptor = os.open(name, flags, dir_fd=descriptor)
            self.parents[child] = (relative, name)
            self._retain(child, child_descriptor)

    def revalidate(self) -> None:
        try:
            root_info = os.stat(
                self.root_name,
                dir_fd=self.parent_descriptor,
                follow_symlinks=False,
            )
            if _repository_snapshot_state(root_info) != self.root_relation_state:
                raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")
            for relative, descriptor in self.descriptors.items():
                if _repository_snapshot_state(os.fstat(descriptor)) != self.states[relative]:
                    raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")
                if relative in self.directory_names and tuple(
                    _descriptor_directory_names(descriptor)
                ) != self.directory_names[relative]:
                    raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")
            for relative, (parent, name) in self.parents.items():
                observed = os.stat(
                    name,
                    dir_fd=self.descriptors[parent],
                    follow_symlinks=False,
                )
                if _repository_snapshot_state(observed) != self.states[relative]:
                    raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")
        except CapacityHostArtifactError:
            raise
        except (OSError, UnicodeError) as exc:
            raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT") from exc

    def close(self) -> None:
        for descriptor in getattr(self, "descriptors", {}).values():
            try:
                os.close(descriptor)
            except OSError:
                pass
        self.descriptors = {}
        parent_descriptor = getattr(self, "parent_descriptor", None)
        if parent_descriptor is not None:
            try:
                os.close(parent_descriptor)
            except OSError:
                pass
            self.parent_descriptor = None


def _run_git_v2(
    view: _RepositoryView,
    *arguments: str,
    input_bytes: bytes | None = None,
) -> bytes:
    view.revalidate()
    root_descriptor = view.root_descriptor

    def enter_retained_root() -> None:
        os.fchdir(root_descriptor)

    completed = subprocess.run(
        ["/usr/bin/git", "--no-replace-objects", *arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
        env=_git_environment(),
        pass_fds=(root_descriptor,),
        preexec_fn=enter_retained_root,
    )
    view.revalidate()
    if completed.returncode != 0:
        raise CapacityHostArtifactError("GIT_MATERIALIZATION_REFUSED")
    return completed.stdout


def _inspect_complete_repository_direct(
    source_root: Path, manifest: Mapping[str, Any], view: _RepositoryView
) -> tuple[str, str]:
    view.revalidate()
    root_info = os.fstat(view.root_descriptor)
    if not stat.S_ISDIR(root_info.st_mode):
        raise CapacityHostArtifactError("SOURCE_ROOT_INVALID")
    expected_uid = root_info.st_uid
    expected_gid = root_info.st_gid
    if any(PurePosixPath(relative).name.endswith(".lock") for relative in view.states):
        raise CapacityHostArtifactError("SOURCE_METADATA_LOCK_PRESENT")
    if view.directory_names.get(".git/hooks") != ():
        raise CapacityHostArtifactError("SOURCE_HOOK_PRESENT")
    if view.directory_names.get(".git/objects") != ("info", "pack"):
        raise CapacityHostArtifactError("SOURCE_OBJECT_NAMESPACE_INVALID")
    if view.directory_names.get(".git/objects/info") != ():
        raise CapacityHostArtifactError("SOURCE_OBJECT_NAMESPACE_INVALID")
    expected_info_names = ("exclude", "sparse-checkout")
    if view.directory_names.get(".git/info") != expected_info_names:
        raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
    git_dir = source_root / ".git"
    config = git_dir / "config"
    worktree_config = git_dir / "config.worktree"
    index = git_dir / "index"
    head = git_dir / "HEAD"
    stored_manifest = git_dir / "cf2-h0-transport-manifest.json"
    for path in (config, worktree_config, index, head, stored_manifest):
        _refuse_optional_lock(path)
    if _read_verified_metadata_file(
        config,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        maximum_bytes=64 * 1024,
    ) != _V2_CONFIG:
        raise CapacityHostArtifactError("SOURCE_CONFIG_INVALID")
    if _read_verified_metadata_file(
        worktree_config,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        maximum_bytes=64 * 1024,
    ) != _V2_WORKTREE_CONFIG:
        raise CapacityHostArtifactError("SOURCE_CONFIG_INVALID")
    if _read_verified_metadata_file(
        stored_manifest,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        maximum_bytes=_V2_MANIFEST_MAX_BYTES,
    ) != canonical_json(manifest):
        raise CapacityHostArtifactError("SOURCE_MANIFEST_MISMATCH")
    if _read_verified_metadata_file(
        git_dir / "info" / "sparse-checkout",
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        maximum_bytes=len(_V2_SPARSE_CHECKOUT),
    ) != _V2_SPARSE_CHECKOUT:
        raise CapacityHostArtifactError("SOURCE_SPARSE_CHECKOUT_INVALID")

    alternates = git_dir / "objects" / "info" / "alternates"
    shallow = git_dir / "shallow"
    grafts = git_dir / "info" / "grafts"
    packed_refs = git_dir / "packed-refs"
    for path in (alternates, shallow, grafts, packed_refs):
        _refuse_optional_lock(path)
    if _path_lstat(alternates) is not None:
        raise CapacityHostArtifactError("SOURCE_ALTERNATES_PRESENT")
    if _path_lstat(shallow) is not None:
        raise CapacityHostArtifactError("SOURCE_SHALLOW_PRESENT")
    if _path_lstat(grafts) is not None:
        graft_bytes = _read_verified_metadata_file(
            grafts,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            maximum_bytes=16 * 1024 * 1024,
        )
        if any(line.strip() and not line.lstrip().startswith(b"#") for line in graft_bytes.splitlines()):
            raise CapacityHostArtifactError("SOURCE_GRAFT_PRESENT")
    if _path_lstat(packed_refs) is not None:
        packed_bytes = _read_verified_metadata_file(
            packed_refs,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            maximum_bytes=16 * 1024 * 1024,
        )
        if b"refs/replace/" in packed_bytes:
            raise CapacityHostArtifactError("SOURCE_REPLACEMENT_REF_PRESENT")
    replace_dir = git_dir / "refs" / "replace"
    replace_info = _path_lstat(replace_dir)
    if replace_info is not None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(replace_dir, flags)
        try:
            if _descriptor_directory_names(descriptor):
                raise CapacityHostArtifactError("SOURCE_REPLACEMENT_REF_PRESENT")
        finally:
            os.close(descriptor)

    pack_dir = git_dir / "objects" / "pack"
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        pack_descriptor = os.open(pack_dir, flags)
    except OSError as exc:
        raise CapacityHostArtifactError("SOURCE_PACK_INSTALL_INVALID") from exc
    try:
        pack_names = _descriptor_directory_names(pack_descriptor)
    finally:
        os.close(pack_descriptor)
    if any(name.endswith((".promisor", ".lock")) for name in pack_names):
        raise CapacityHostArtifactError("SOURCE_PROMISOR_OR_LOCK_PRESENT")
    packs = [name for name in pack_names if re.fullmatch(r"pack-[0-9a-f]{40}\.pack", name)]
    indexes = [name for name in pack_names if re.fullmatch(r"pack-[0-9a-f]{40}\.idx", name)]
    if (
        len(packs) != 1
        or len(indexes) != 1
        or packs[0][:-5] != indexes[0][:-4]
        or set(pack_names) != {packs[0], indexes[0]}
    ):
        raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
    pack_path = pack_dir / packs[0]
    index_path = pack_dir / indexes[0]
    _refuse_optional_lock(pack_path)
    _refuse_optional_lock(index_path)
    _validate_pack_file(pack_path, expected_count=int(manifest["object_count"]))
    view.revalidate()
    return (
        f".git/objects/pack/{packs[0]}",
        f".git/objects/pack/{indexes[0]}",
    )


def _pack_inventory(repository: Path, index_path: Path) -> tuple[ObjectInventoryRow, ...]:
    output = _run_git(repository, "verify-pack", "-v", os.fspath(index_path)).decode(
        "ascii", "strict"
    )
    object_ids: list[str] = []
    for line in output.splitlines():
        fields = line.split()
        if not fields or _OBJECT_RE.fullmatch(fields[0]) is None:
            continue
        if len(fields) < 3 or fields[1] not in _V2_PACK_TYPES:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
        object_ids.append(fields[0])
    ordered_ids = sorted(object_ids)
    if not ordered_ids or len(set(ordered_ids)) != len(ordered_ids):
        raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
    checked = _run_git(
        repository,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_bytes=("\n".join(ordered_ids) + "\n").encode("ascii"),
    ).decode("ascii", "strict").splitlines()
    if len(checked) != len(ordered_ids):
        raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
    rows: list[ObjectInventoryRow] = []
    for expected_oid, line in zip(ordered_ids, checked):
        fields = line.split(" ")
        if len(fields) != 3 or fields[0] != expected_oid or fields[1] not in _V2_PACK_TYPES:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
        try:
            size = int(fields[2], 10)
        except ValueError as exc:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID") from exc
        if size < 0:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
        rows.append(ObjectInventoryRow(expected_oid, fields[1], size))
    return tuple(rows)


def _pack_inventory_v2(
    view: _RepositoryView, index_path: str
) -> tuple[ObjectInventoryRow, ...]:
    output = _run_git_v2(view, "verify-pack", "-v", index_path).decode(
        "ascii", "strict"
    )
    object_ids: list[str] = []
    for line in output.splitlines():
        fields = line.split()
        if not fields or _OBJECT_RE.fullmatch(fields[0]) is None:
            continue
        if len(fields) < 3 or fields[1] not in _V2_PACK_TYPES:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
        object_ids.append(fields[0])
    ordered_ids = sorted(object_ids)
    if not ordered_ids or len(set(ordered_ids)) != len(ordered_ids):
        raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
    checked = _run_git_v2(
        view,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_bytes=("\n".join(ordered_ids) + "\n").encode("ascii"),
    ).decode("ascii", "strict").splitlines()
    rows: list[ObjectInventoryRow] = []
    if len(checked) != len(ordered_ids):
        raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
    for expected_oid, line in zip(ordered_ids, checked):
        fields = line.split(" ")
        if len(fields) != 3 or fields[0] != expected_oid or fields[1] not in _V2_PACK_TYPES:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
        try:
            size = int(fields[2], 10)
        except ValueError as exc:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID") from exc
        if size < 0 or str(size) != fields[2]:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
        rows.append(ObjectInventoryRow(expected_oid, fields[1], size))
    return tuple(rows)


def _enumerate_reachable_objects_v2(
    view: _RepositoryView, commit: str
) -> tuple[ObjectInventoryRow, ...]:
    if _COMMIT_RE.fullmatch(commit) is None:
        raise CapacityHostArtifactError("COMMIT_INVALID")
    observed = _run_git_v2(view, "rev-parse", f"{commit}^{{commit}}").decode().strip()
    if observed != commit:
        raise CapacityHostArtifactError("COMMIT_MISMATCH")
    raw_objects = _run_git_v2(
        view,
        "rev-list",
        "--objects",
        "--no-object-names",
        "--missing=print",
        commit,
    ).decode("ascii", "strict").splitlines()
    if (
        not raw_objects
        or any(value.startswith("?") for value in raw_objects)
        or any(_OBJECT_RE.fullmatch(value) is None for value in raw_objects)
        or len(set(raw_objects)) != len(raw_objects)
    ):
        raise CapacityHostArtifactError("OBJECT_CLOSURE_MISSING")
    object_ids = sorted(raw_objects)
    checked = _run_git_v2(
        view,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_bytes=("\n".join(object_ids) + "\n").encode("ascii"),
    ).decode("ascii", "strict").splitlines()
    if len(checked) != len(object_ids):
        raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID")
    rows: list[ObjectInventoryRow] = []
    for expected_oid, line in zip(object_ids, checked):
        fields = line.split(" ")
        if len(fields) != 3 or fields[0] != expected_oid or fields[1] not in _V2_PACK_TYPES:
            raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID")
        try:
            size = int(fields[2], 10)
        except ValueError as exc:
            raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID") from exc
        if size < 0 or str(size) != fields[2]:
            raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID")
        rows.append(ObjectInventoryRow(expected_oid, fields[1], size))
    return tuple(rows)


def _observed_worktree_files_v2(view: _RepositoryView) -> list[str]:
    return sorted(
        (
            relative
            for relative, state in view.states.items()
            if relative != "."
            and not relative.startswith(".git/")
            and stat.S_ISREG(state[3])
        ),
        key=lambda value: value.encode("utf-8"),
    )


def _observed_worktree_files(source_root: Path) -> list[str]:
    output: list[str] = []
    for current, directory_names, file_names in os.walk(source_root, followlinks=False):
        if Path(current) == source_root and ".git" in directory_names:
            directory_names.remove(".git")
        relative_root = Path(current).relative_to(source_root)
        for name in file_names:
            relative = (relative_root / name).as_posix()
            output.append(relative)
    return sorted(output, key=lambda value: value.encode("utf-8"))


def verify_complete_repository(
    source_root: Path, manifest: Mapping[str, Any]
) -> SourceClosureEvidence:
    """Descriptor-first proof of a direct, complete, sparse ordinary repository."""

    validated = validate_transport_manifest_v2(
        manifest, expected_commit=str(manifest.get("commit"))
    )
    view = _RepositoryView(source_root)
    try:
        root_info = os.fstat(view.root_descriptor)
        first_tree_digest = closed_tree_digest(
            source_root,
            expected_uid=root_info.st_uid,
            expected_gid=root_info.st_gid,
        )
        view.revalidate()
        _pack_path, index_path = _inspect_complete_repository_direct(
            source_root, validated, view
        )
        commit = str(validated["commit"])
        if _run_git_v2(view, "rev-parse", "HEAD").decode().strip() != commit:
            raise CapacityHostArtifactError("SOURCE_HEAD_MISMATCH")
        if _run_git_v2(view, "branch", "--show-current").strip():
            raise CapacityHostArtifactError("SOURCE_HEAD_ATTACHED")
        if _run_git_v2(view, "remote").strip():
            raise CapacityHostArtifactError("SOURCE_REMOTE_PRESENT")
        _run_git_v2(view, "fsck", "--full", "--strict", "--no-progress")
        reachable = _enumerate_reachable_objects_v2(view, commit)
        packed = _pack_inventory_v2(view, index_path)
        if reachable != packed:
            raise CapacityHostArtifactError("SOURCE_PACK_OBJECT_SET_MISMATCH")
        if (
            len(reachable) != validated["object_count"]
            or _inventory_digest(reachable) != validated["object_inventory_sha256"]
        ):
            raise CapacityHostArtifactError("SOURCE_OBJECT_INVENTORY_MISMATCH")
        expected_paths = list(PRODUCER_MATERIAL_PATHS)
        if _observed_worktree_files_v2(view) != expected_paths:
            raise CapacityHostArtifactError("SOURCE_WORKTREE_INVENTORY_MISMATCH")
        for row in validated["material"]:
            relative = str(row["path"])
            descriptor = view.descriptors.get(relative)
            if descriptor is None:
                raise CapacityHostArtifactError("SOURCE_WORKTREE_FILE_MISMATCH")
            before = os.fstat(descriptor)
            expected_mode = 0o555 if row["mode"] == "100755" else 0o444
            observed_digest = _descriptor_sha256(descriptor)
            after = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != expected_mode
                or before.st_size != row["size"]
                or observed_digest != row["sha256"]
                or _repository_snapshot_state(before) != _repository_snapshot_state(after)
            ):
                raise CapacityHostArtifactError("SOURCE_WORKTREE_FILE_MISMATCH")
            observed_blob = _run_git_v2(
                view, "hash-object", "--no-filters", relative
            ).decode().strip()
            tree_line = _run_git_v2(
                view, "ls-tree", "-z", commit, "--", relative
            )
            if observed_blob != row["git_blob"] or (
                f" {row['git_blob']}\t".encode() not in tree_line
            ):
                raise CapacityHostArtifactError("SOURCE_GIT_BLOB_MISMATCH")
        if _run_git_v2(
            view, "status", "--porcelain=v1", "--untracked-files=all"
        ):
            raise CapacityHostArtifactError("SOURCE_WORKTREE_DIRTY")
        final_tree_digest = closed_tree_digest(
            source_root,
            expected_uid=root_info.st_uid,
            expected_gid=root_info.st_gid,
        )
        view.revalidate()
        if final_tree_digest != first_tree_digest:
            raise CapacityHostArtifactError("SOURCE_TREE_DRIFT")
        return validate_source_closure_evidence(
            SourceClosureEvidence(
                object_count=len(reachable),
                object_inventory_sha256=_inventory_digest(reachable),
                source_tree_sha256=final_tree_digest,
            )
        )
    finally:
        view.close()


def materialize_source_transport_v2(
    archive_path: Path,
    source_root: Path,
    *,
    expected_commit: str,
) -> dict[str, Any]:
    """Create one complete direct repository without inheriting operator Git state."""

    transport = source_root.with_name(f".{source_root.name}.transport-v2")
    if source_root.exists() or source_root.is_symlink() or transport.exists():
        raise CapacityHostArtifactError("SOURCE_DESTINATION_EXISTS")
    manifest = extract_source_transport_v2(
        archive_path, transport, expected_commit=expected_commit
    )
    try:
        source_root.mkdir(mode=0o700, parents=False, exist_ok=False)
        _run_git(source_root, "init", "--quiet")
        hooks = source_root / ".git" / "hooks"
        for hook in hooks.iterdir():
            if not hook.is_file() or hook.is_symlink():
                raise CapacityHostArtifactError("SOURCE_DEFAULT_HOOK_INVENTORY_INVALID")
            hook.unlink()
        (source_root / ".git" / "config").write_bytes(_V2_CONFIG)
        (source_root / ".git" / "config.worktree").write_bytes(_V2_WORKTREE_CONFIG)
        pack_output = _run_git_file_input(
            source_root,
            transport / "payload.pack",
            "index-pack",
            "--stdin",
            "--fix-thin",
        ).decode("ascii", "strict").strip()
        match = re.fullmatch(r"(?:pack\s+)?([0-9a-f]{40})", pack_output)
        if match is None:
            raise CapacityHostArtifactError("SOURCE_PACK_IDENTITY_INVALID")
        pack_base = source_root / ".git" / "objects" / "pack" / f"pack-{match.group(1)}"
        if not pack_base.with_suffix(".pack").is_file() or not pack_base.with_suffix(".idx").is_file():
            raise CapacityHostArtifactError("SOURCE_PACK_INSTALL_INVALID")
        sparse = source_root / ".git" / "info" / "sparse-checkout"
        sparse.write_bytes(_V2_SPARSE_CHECKOUT)
        _run_git(source_root, "checkout", "--detach", expected_commit)
        (source_root / ".git" / "cf2-h0-transport-manifest.json").write_bytes(
            canonical_json(manifest)
        )
        _normalize_complete_repository_modes(source_root)
        verify_complete_repository(source_root, manifest)
        return manifest
    finally:
        if transport.exists():
            for child in transport.iterdir():
                child.unlink(missing_ok=True)
            transport.rmdir()


def _safe_wheel_member(info: zipfile.ZipInfo) -> PurePosixPath:
    candidate = PurePosixPath(info.filename)
    mode = info.external_attr >> 16
    if (
        candidate.is_absolute()
        or not candidate.parts
        or ".." in candidate.parts
        or "" in candidate.parts
        or not any(info.filename.startswith(prefix) for prefix in _WHEEL_PREFIXES)
    ):
        raise CapacityHostArtifactError("WHEEL_MEMBER_PATH_INVALID")
    kind = stat.S_IFMT(mode)
    if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise CapacityHostArtifactError("WHEEL_MEMBER_TYPE_INVALID")
    return candidate


def extract_pyyaml_wheel(wheel: Path, runtime_root: Path) -> Path:
    """Extract the pinned wheel with no pip, scripts, links, or archive modes."""

    site_packages = runtime_root / "lib" / "python3.12" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    with zipfile.ZipFile(wheel, "r") as archive:
        for info in archive.infolist():
            candidate = _safe_wheel_member(info)
            normalized = os.fspath(candidate)
            if normalized in seen:
                raise CapacityHostArtifactError("WHEEL_MEMBER_DUPLICATE")
            seen.add(normalized)
            target = site_packages.joinpath(*candidate.parts)
            if info.is_dir():
                target.mkdir(mode=0o755, parents=True, exist_ok=True)
                continue
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
            try:
                with archive.open(info, "r") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        os.write(descriptor, chunk)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    return site_packages


def verify_pyyaml_record(runtime_root: Path) -> str:
    site_packages = runtime_root / "lib" / "python3.12" / "site-packages"
    record = site_packages / "pyyaml-6.0.3.dist-info" / "RECORD"
    try:
        rows = list(csv.reader(record.read_text(encoding="utf-8").splitlines()))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise CapacityHostArtifactError("PYYAML_RECORD_UNREADABLE") from exc
    declared: dict[str, tuple[str, str]] = {}
    for row in rows:
        if len(row) != 3 or row[0] in declared:
            raise CapacityHostArtifactError("PYYAML_RECORD_INVALID")
        path = PurePosixPath(row[0])
        if path.is_absolute() or ".." in path.parts or not any(row[0].startswith(prefix) for prefix in _WHEEL_PREFIXES):
            raise CapacityHostArtifactError("PYYAML_RECORD_PATH_INVALID")
        declared[row[0]] = (row[1], row[2])
    observed = {
        path.relative_to(site_packages).as_posix()
        for path in site_packages.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if observed != set(declared):
        raise CapacityHostArtifactError("PYYAML_RECORD_INVENTORY_MISMATCH")
    for relative, (encoded_hash, encoded_size) in declared.items():
        path = site_packages / relative
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise CapacityHostArtifactError("PYYAML_RECORD_FILE_INVALID")
        if relative.endswith(".dist-info/RECORD") and not encoded_hash and not encoded_size:
            continue
        if not encoded_hash.startswith("sha256=") or not encoded_size.isdecimal():
            raise CapacityHostArtifactError("PYYAML_RECORD_HASH_INVALID")
        digest = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest()).rstrip(b"=").decode("ascii")
        if digest != encoded_hash.removeprefix("sha256=") or info.st_size != int(encoded_size):
            raise CapacityHostArtifactError("PYYAML_RECORD_HASH_MISMATCH")
    for forbidden in ("sitecustomize.py", "usercustomize.py"):
        if (site_packages / forbidden).exists():
            raise CapacityHostArtifactError("RUNTIME_SITE_INJECTION_PRESENT")
    if any(site_packages.rglob("*.pth")):
        raise CapacityHostArtifactError("RUNTIME_PTH_PRESENT")
    return sha256_file(record)


def runtime_tree_digest(runtime_root: Path) -> str:
    rows: list[dict[str, Any]] = []
    paths = [runtime_root, *sorted(
        runtime_root.rglob("*"),
        key=lambda value: value.relative_to(runtime_root).as_posix(),
    )]
    for path in paths:
        info = path.lstat()
        relative = "." if path == runtime_root else path.relative_to(runtime_root).as_posix()
        if stat.S_ISLNK(info.st_mode):
            raise CapacityHostArtifactError("RUNTIME_SYMLINK_PRESENT")
        if stat.S_ISDIR(info.st_mode):
            row: dict[str, Any] = {
                "mode": f"{stat.S_IMODE(info.st_mode):04o}",
                "nlink": info.st_nlink,
                "path": relative,
                "type": "directory",
            }
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            row = {
                "mode": f"{stat.S_IMODE(info.st_mode):04o}",
                "nlink": 1,
                "path": relative,
                "sha256": sha256_file(path),
                "size": info.st_size,
                "type": "file",
            }
        else:
            raise CapacityHostArtifactError("RUNTIME_OBJECT_INVALID")
        rows.append(row)
    return hashlib.sha256(canonical_json(rows)).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or inspect inert CF2-H0 artifacts")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build-source-transport")
    build.add_argument("--source-repository", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--commit", required=True)
    build.add_argument("--material-path", action="append", default=[])
    extract = commands.add_parser("extract-source-transport")
    extract.add_argument("--archive", type=Path, required=True)
    extract.add_argument("--destination", type=Path, required=True)
    extract.add_argument("--commit", required=True)
    extract.add_argument("--material-path", action="append", default=[])
    materialize = commands.add_parser("materialize-source-transport")
    materialize.add_argument("--archive", type=Path, required=True)
    materialize.add_argument("--destination", type=Path, required=True)
    materialize.add_argument("--commit", required=True)
    materialize.add_argument("--material-path", action="append", default=[])
    verify_source = commands.add_parser("verify-materialized-source")
    verify_source.add_argument("--source-root", type=Path, required=True)
    verify_source.add_argument("--manifest", type=Path, required=True)
    verify_source.add_argument("--commit", required=True)
    verify_source.add_argument("--material-path", action="append", default=[])
    build_v2 = commands.add_parser("build-source-transport-v2")
    build_v2.add_argument("--source-repository", type=Path, required=True)
    build_v2.add_argument("--output", type=Path, required=True)
    build_v2.add_argument("--commit", required=True)
    extract_v2 = commands.add_parser("extract-source-transport-v2")
    extract_v2.add_argument("--archive", type=Path, required=True)
    extract_v2.add_argument("--destination", type=Path, required=True)
    extract_v2.add_argument("--commit", required=True)
    materialize_v2 = commands.add_parser("materialize-source-transport-v2")
    materialize_v2.add_argument("--archive", type=Path, required=True)
    materialize_v2.add_argument("--destination", type=Path, required=True)
    materialize_v2.add_argument("--commit", required=True)
    verify_complete = commands.add_parser("verify-complete-repository")
    verify_complete.add_argument("--source-root", type=Path, required=True)
    verify_complete.add_argument("--manifest", type=Path, required=True)
    verify_complete.add_argument("--commit", required=True)
    wheel = commands.add_parser("extract-pyyaml-wheel")
    wheel.add_argument("--wheel", type=Path, required=True)
    wheel.add_argument("--runtime-root", type=Path, required=True)
    runtime = commands.add_parser("verify-runtime-tree")
    runtime.add_argument("--runtime-root", type=Path, required=True)
    closed = commands.add_parser("copy-closed-input")
    closed.add_argument("--source", type=Path, required=True)
    closed.add_argument("--destination", type=Path, required=True)
    closed.add_argument("--operator-uid", type=int, required=True)
    closed.add_argument("--expected-sha256", required=True)
    recovery_intent = commands.add_parser("create-recovery-intent")
    recovery_intent.add_argument("--archive", type=Path, required=True)
    recovery_intent.add_argument("--expected-uid", type=int, required=True)
    recovery_intent.add_argument("--source", type=Path, action="append", default=[])
    recovery_resume = commands.add_parser("resume-recovery-archive")
    recovery_resume.add_argument("--archive", type=Path, required=True)
    recovery_resume.add_argument("--expected-uid", type=int, required=True)
    approved_xattrs = commands.add_parser("verify-approved-xattrs")
    approved_xattrs.add_argument("--path", type=Path, required=True)
    launchctl_disabled = commands.add_parser("check-launchctl-disabled")
    launchctl_disabled.add_argument("--label", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build-source-transport":
            value: Any = build_source_transport(
                args.source_repository,
                args.output,
                commit=args.commit,
                material_paths=tuple(args.material_path),
            )
        elif args.command == "extract-source-transport":
            value = extract_source_transport(
                args.archive,
                args.destination,
                expected_commit=args.commit,
                material_paths=tuple(args.material_path),
            )
        elif args.command == "materialize-source-transport":
            value = materialize_source_transport(
                args.archive,
                args.destination,
                expected_commit=args.commit,
                material_paths=tuple(args.material_path),
            )
        elif args.command == "verify-materialized-source":
            manifest = validate_transport_manifest(
                json.loads(args.manifest.read_text(encoding="utf-8")),
                expected_commit=args.commit,
                material_paths=tuple(args.material_path),
            )
            verify_materialized_source(args.source_root, manifest=manifest)
            value = manifest
        elif args.command == "build-source-transport-v2":
            value = build_source_transport_v2(
                args.source_repository,
                args.output,
                commit=args.commit,
            )
        elif args.command == "extract-source-transport-v2":
            value = extract_source_transport_v2(
                args.archive,
                args.destination,
                expected_commit=args.commit,
            )
        elif args.command == "materialize-source-transport-v2":
            value = materialize_source_transport_v2(
                args.archive,
                args.destination,
                expected_commit=args.commit,
            )
        elif args.command == "verify-complete-repository":
            manifest = validate_transport_manifest_v2(
                json.loads(_read_small_nofollow(args.manifest, _V2_MANIFEST_MAX_BYTES)),
                expected_commit=args.commit,
            )
            evidence = verify_complete_repository(args.source_root, manifest)
            value = {
                "object_count": evidence.object_count,
                "object_inventory_sha256": evidence.object_inventory_sha256,
                "source_tree_sha256": evidence.source_tree_sha256,
            }
        elif args.command == "extract-pyyaml-wheel":
            value = {"site_packages": str(extract_pyyaml_wheel(args.wheel, args.runtime_root))}
        elif args.command == "verify-runtime-tree":
            value = {
                "pyyaml_record_sha256": verify_pyyaml_record(args.runtime_root),
                "runtime_tree_sha256": runtime_tree_digest(args.runtime_root),
            }
        elif args.command == "copy-closed-input":
            value = copy_closed_input(
                args.source,
                args.destination,
                operator_uid=args.operator_uid,
                expected_sha256=args.expected_sha256,
            )
        elif args.command == "create-recovery-intent":
            value = create_recovery_intent(
                args.archive,
                tuple(args.source),
                expected_uid=args.expected_uid,
            )
        elif args.command == "resume-recovery-archive":
            value = resume_recovery_archive(
                args.archive,
                expected_uid=args.expected_uid,
            )
        elif args.command == "verify-approved-xattrs":
            value = verify_approved_xattrs(args.path)
        else:
            value = parse_launchctl_disabled(sys.stdin.read(256 * 1024 + 1), args.label)
    except CapacityHostArtifactError as exc:
        reason = str(exc)
        if re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", reason) is None:
            reason = type(exc).__name__
        print(f"capacity host artifact refused: {reason}", file=sys.stderr)
        return 65
    except (OSError, UnicodeError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        print(f"capacity host artifact refused: {type(exc).__name__}", file=sys.stderr)
        return 65
    sys.stdout.write(canonical_json(value).decode("utf-8") + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
