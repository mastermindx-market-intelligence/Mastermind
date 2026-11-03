"""Materialize one already-reviewed Browser Link native-host install plan.

This is a narrow host-filesystem effect only. It never launches Chrome, installs
an extension, starts the Browser owner, creates a grant, or links Auth0.
Foreign existing files and symlinked target directories fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from .native_host_install import (
    BrowserNativeHostInstallPlan,
    HOST_NAME,
)


class BrowserNativeHostMaterializeError(RuntimeError):
    """The native-host files cannot be materialized without ambiguity."""


@dataclass(frozen=True, slots=True)
class BrowserNativeHostMaterializeReceipt:
    host_manifest_path: str
    launcher_sha256: str
    enrollment_sha256: str
    host_manifest_sha256: str
    applied: bool = True

    @property
    def is_browser_registration(self) -> bool:
        return False

    @property
    def is_extension_installation(self) -> bool:
        return False


def _bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _owned_regular(path: Path, uid: int, field: str) -> None:
    try:
        st = path.lstat()
    except FileNotFoundError as exc:
        raise BrowserNativeHostMaterializeError(f"{field} is missing") from exc
    if not stat.S_ISREG(st.st_mode) or st.st_uid != uid:
        raise BrowserNativeHostMaterializeError(f"{field} is not an owned regular file")


def _owned_directory(path: Path, uid: int, field: str) -> None:
    try:
        st = path.lstat()
    except FileNotFoundError as exc:
        raise BrowserNativeHostMaterializeError(f"{field} is missing") from exc
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != uid:
        raise BrowserNativeHostMaterializeError(f"{field} is not an owned directory")


def _existing_state(path: Path, expected: bytes, mode: int, uid: int) -> bool:
    """Return True for exact already-materialized content; refuse all drift."""
    try:
        st = path.lstat()
    except FileNotFoundError:
        return False
    if (
        not stat.S_ISREG(st.st_mode)
        or st.st_uid != uid
        or stat.S_IMODE(st.st_mode) != mode
    ):
        raise BrowserNativeHostMaterializeError("existing native-host file conflicts")
    try:
        actual = path.read_bytes()
    except OSError as exc:
        raise BrowserNativeHostMaterializeError("existing native-host file unreadable") from exc
    if actual != expected:
        raise BrowserNativeHostMaterializeError("existing native-host file conflicts")
    return True


def _atomic_write(path: Path, payload: bytes, mode: int, uid: int) -> None:
    _owned_directory(path.parent, uid, "target parent")
    fd = None
    temp_path: Path | None = None
    try:
        fd, raw_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        temp_path = Path(raw_name)
        st = os.fstat(fd)
        if st.st_uid != uid or not stat.S_ISREG(st.st_mode):
            raise BrowserNativeHostMaterializeError("temporary file ownership invalid")
        os.fchmod(fd, mode)
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise BrowserNativeHostMaterializeError("native-host write failed")
            offset += written
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.replace(temp_path, path)
        temp_path = None
        final = path.lstat()
        if (
            not stat.S_ISREG(final.st_mode)
            or final.st_uid != uid
            or stat.S_IMODE(final.st_mode) != mode
            or path.read_bytes() != payload
        ):
            raise BrowserNativeHostMaterializeError("native-host readback mismatch")
    except BrowserNativeHostMaterializeError:
        raise
    except OSError as exc:
        raise BrowserNativeHostMaterializeError("native-host materialization failed") from exc
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass


def materialize_native_host(
    plan: BrowserNativeHostInstallPlan,
    *,
    native_manifest_dir: str | Path,
    expected_owner_uid: int,
) -> BrowserNativeHostMaterializeReceipt:
    """Write exact reviewed host files after complete preflight.

    An exact second invocation is idempotent. Any foreign or drifted target
    refuses before a new target file is created. The three files are not a
    transactional database; a process crash between atomic file publications
    is recovered by the same exact-plan invocation, which accepts exact prior
    bytes and writes only missing suffix files.
    """
    if type(plan) is not BrowserNativeHostInstallPlan:
        raise BrowserNativeHostMaterializeError("typed install plan required")
    if type(expected_owner_uid) is not int or isinstance(expected_owner_uid, bool) or expected_owner_uid < 0:
        raise BrowserNativeHostMaterializeError("expected_owner_uid is invalid")

    launcher = Path(plan.launcher_path)
    enrollment = Path(plan.enrollment_path)
    manifest_dir = Path(native_manifest_dir)
    if not manifest_dir.is_absolute() or ".." in manifest_dir.parts:
        raise BrowserNativeHostMaterializeError("native_manifest_dir is invalid")
    manifest = manifest_dir / f"{HOST_NAME}.json"

    _owned_regular(Path(plan.python_executable), expected_owner_uid, "python executable")
    _owned_regular(Path(plan.bridge_path), expected_owner_uid, "bridge")
    _owned_directory(launcher.parent, expected_owner_uid, "launcher parent")
    if enrollment.parent != launcher.parent:
        _owned_directory(enrollment.parent, expected_owner_uid, "enrollment parent")

    launcher_bytes = plan.launcher_source.encode("utf-8")
    enrollment_bytes = _bytes(plan.enrollment)
    manifest_bytes = _bytes(plan.host_manifest)

    targets = (
        (launcher, launcher_bytes, plan.launcher_mode),
        (enrollment, enrollment_bytes, plan.enrollment_mode),
        (manifest, manifest_bytes, plan.host_manifest_mode),
    )

    existing = []
    for path, payload, mode in targets:
        if path == manifest and not manifest_dir.exists():
            existing.append(False)
            continue
        if path == manifest:
            _owned_directory(manifest_dir, expected_owner_uid, "native manifest directory")
        existing.append(_existing_state(path, payload, mode, expected_owner_uid))

    if not manifest_dir.exists():
        try:
            manifest_dir.mkdir(
                mode=(
                    stat.S_IRWXU
                    | stat.S_IRGRP
                    | stat.S_IXGRP
                    | stat.S_IROTH
                    | stat.S_IXOTH
                )
            )
        except OSError as exc:
            raise BrowserNativeHostMaterializeError("native manifest directory creation failed") from exc
        _owned_directory(manifest_dir, expected_owner_uid, "native manifest directory")

    for already, (path, payload, mode) in zip(existing, targets):
        if not already:
            _atomic_write(path, payload, mode, expected_owner_uid)

    return BrowserNativeHostMaterializeReceipt(
        host_manifest_path=str(manifest),
        launcher_sha256=_digest(launcher_bytes),
        enrollment_sha256=_digest(enrollment_bytes),
        host_manifest_sha256=_digest(manifest_bytes),
    )
