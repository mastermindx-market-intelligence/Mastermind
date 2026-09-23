"""Sealed service-owned Mosyle credential reader.

This follows the existing Executive provider-file trust pattern: a fixed file
beneath the existing root-owned config directory, owned by the already-bound
MCP service identity, mode 0600, single link, ACL-free and opened O_NOFOLLOW.
"""
from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path

from control_plane.fs_security import FilesystemSecurityError, has_macos_acl
from integrations.mosyle_mdm.client import MosyleCredential

CREDENTIAL_PATH = Path(
    "/Library/Application Support/MastermindExecutive/config/mosyle-readonly.json"
)
MAX_CREDENTIAL_BYTES = 32 * 1024


class MosyleCredentialFileError(RuntimeError):
    pass


class FileMosyleCredentialSource:
    def __init__(
        self,
        *,
        path: Path = CREDENTIAL_PATH,
        expected_uid: int,
        expected_gid: int,
    ) -> None:
        self._path = Path(path)
        self._expected_uid = int(expected_uid)
        self._expected_gid = int(expected_gid)

    async def resolve(self) -> MosyleCredential:
        try:
            raw = await asyncio.to_thread(
                _read_credential_file,
                self._path,
                expected_uid=self._expected_uid,
                expected_gid=self._expected_gid,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise MosyleCredentialFileError(
                "Mosyle service credential is unavailable"
            ) from exc
        return _parse_credential(raw)


def _validate_parent(path: Path) -> None:
    parent = path.parent
    try:
        before = parent.lstat()
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(parent, flags)
    except OSError:
        raise MosyleCredentialFileError(
            "Mosyle credential parent metadata is unsafe"
        ) from None
    try:
        observed = os.fstat(descriptor)
        if (
            before.st_dev != observed.st_dev
            or before.st_ino != observed.st_ino
            or stat.S_ISLNK(before.st_mode)
            or not stat.S_ISDIR(observed.st_mode)
            or observed.st_uid != 0
            or observed.st_gid != 0
            or stat.S_IMODE(observed.st_mode) & 0o022
            or _has_acl(parent, before, descriptor)
        ):
            raise MosyleCredentialFileError(
                "Mosyle credential parent metadata is unsafe"
            )
    finally:
        os.close(descriptor)


def _read_credential_file(
    path: Path, *, expected_uid: int, expected_gid: int
) -> bytes:
    _validate_parent(path)
    try:
        before = path.lstat()
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        descriptor = os.open(path, flags)
    except OSError:
        raise MosyleCredentialFileError(
            "Mosyle service credential is unavailable"
        ) from None
    try:
        observed = os.fstat(descriptor)
        if (
            before.st_dev != observed.st_dev
            or before.st_ino != observed.st_ino
            or stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != expected_uid
            or observed.st_gid != expected_gid
            or stat.S_IMODE(observed.st_mode) != 0o600
            or observed.st_nlink != 1
            or observed.st_size < 1
            or observed.st_size > MAX_CREDENTIAL_BYTES
            or _has_acl(path, before, descriptor)
        ):
            raise MosyleCredentialFileError(
                "Mosyle service credential metadata is unsafe"
            )
        raw = bytearray()
        while len(raw) <= MAX_CREDENTIAL_BYTES:
            chunk = os.read(descriptor, min(4096, MAX_CREDENTIAL_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(descriptor)
        if (
            len(raw) > MAX_CREDENTIAL_BYTES
            or after.st_dev != observed.st_dev
            or after.st_ino != observed.st_ino
            or after.st_size != observed.st_size
            or after.st_mtime_ns != observed.st_mtime_ns
        ):
            raise MosyleCredentialFileError(
                "Mosyle service credential changed during read"
            )
        return bytes(raw)
    finally:
        os.close(descriptor)


def _has_acl(path: Path, identity: os.stat_result, descriptor: int) -> bool:
    try:
        return has_macos_acl(
            path,
            expected_identity=identity,
            descriptor=descriptor,
        )
    except FilesystemSecurityError:
        raise MosyleCredentialFileError(
            "Mosyle service credential metadata is unsafe"
        ) from None


def _parse_credential(raw: bytes) -> MosyleCredential:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise MosyleCredentialFileError(
            "Mosyle service credential is unavailable"
        ) from exc
    if (
        not isinstance(value, dict)
        or set(value) - {"access_token", "bearer_token"}
        or "access_token" not in value
        or (
            value.get("bearer_token") is not None
            and not isinstance(value.get("bearer_token"), str)
        )
    ):
        raise MosyleCredentialFileError(
            "Mosyle service credential is unavailable"
        )
    try:
        return MosyleCredential(
            access_token=value["access_token"],
            bearer_token=value.get("bearer_token"),
        )
    except (TypeError, ValueError) as exc:
        raise MosyleCredentialFileError(
            "Mosyle service credential is unavailable"
        ) from exc


__all__ = [
    "CREDENTIAL_PATH",
    "FileMosyleCredentialSource",
    "MAX_CREDENTIAL_BYTES",
    "MosyleCredentialFileError",
]
