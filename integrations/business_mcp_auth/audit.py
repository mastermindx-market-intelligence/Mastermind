"""Durable, descriptor-relative auth audit for one fixed policy log.

The sink owns independently opened directory and file descriptions.  Every
append revalidates the named file before and after one write plus fsync.  Any
identity, flag, size, write, or durability uncertainty poisons the instance;
there is no retry, rotation, replacement descriptor, or second event schema.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import stat
import threading
from typing import Any

from .contracts import (
    AUTH_AUDIT_SCHEMA,
    AuthAuditEvent,
    AuthErrorCode,
)

_AUDIT_NAME = "auth-audit.jsonl"
_POLICY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,95}$")
_CODES = frozenset({"accepted", *(code.value for code in AuthErrorCode)})
_DEFAULT_MAX_LINE_BYTES = 4096
_DEFAULT_MAX_FILE_BYTES = 16 * 1024 * 1024


class AuditSinkPoisoned(RuntimeError):
    """The named durable audit effect is refused or uncertain."""


class AuditAcquisitionUncertain(AuditSinkPoisoned):
    """Partially acquired audit descriptions were not cleanly released."""

    def __init__(
        self,
        message: str,
        *,
        primary_error: BaseException,
        cleanup_errors: tuple[BaseException, ...],
    ) -> None:
        self.primary_error = primary_error
        self.cleanup_errors = cleanup_errors
        super().__init__(message)


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_uid,
        stat.S_IMODE(value.st_mode),
        value.st_nlink,
    )


def _directory_identity(value: os.stat_result) -> tuple[int, int, int]:
    return value.st_dev, value.st_ino, value.st_uid


def _platform_flags() -> tuple[int, int, int]:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if (
        not nofollow
        or not directory
        or not cloexec
        or os.open not in os.supports_dir_fd
        or os.stat not in os.supports_dir_fd
    ):
        raise AuditSinkPoisoned("descriptor-relative audit is not qualified")
    return nofollow, directory, cloexec


def _validate_policy_id(value: object) -> str:
    if type(value) is not str or _POLICY_ID_RE.fullmatch(value) is None:
        raise AuditSinkPoisoned("audit policy identity is invalid")
    return value


def _validate_budget(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise AuditSinkPoisoned(f"{name} is invalid")
    return value


class DurableAuthAuditSink:
    """One fail-closed append sink for ``AuthAuditEvent``."""

    def __init__(
        self,
        *,
        directory_fd: int,
        audit_fd: int,
        policy_id: str,
        directory_identity: tuple[int, int, int],
        file_identity: tuple[int, int, int, int, int],
        expected_size: int,
        max_line_bytes: int,
        max_file_bytes: int,
    ) -> None:
        self._directory_fd = directory_fd
        self._audit_fd = audit_fd
        self._policy_id = policy_id
        self._directory_identity = directory_identity
        self._file_identity = file_identity
        self._expected_size = expected_size
        self._max_line_bytes = max_line_bytes
        self._max_file_bytes = max_file_bytes
        self._gate = threading.Lock()
        self._poisoned = False
        self._closed = False
        self._close_uncertain = False

    @classmethod
    def open(
        cls,
        host_directory_fd: int,
        *,
        policy_id: str,
        max_line_bytes: int = _DEFAULT_MAX_LINE_BYTES,
        max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES,
    ) -> "DurableAuthAuditSink":
        selected_policy = _validate_policy_id(policy_id)
        line_budget = _validate_budget(max_line_bytes, "max_line_bytes")
        file_budget = _validate_budget(max_file_bytes, "max_file_bytes")
        if line_budget > file_budget:
            raise AuditSinkPoisoned("audit budgets are inconsistent")
        nofollow, directory, cloexec = _platform_flags()
        owned_directory = -1
        audit_fd = -1
        try:
            host_stat = os.fstat(host_directory_fd)
            cls._check_directory_stat(host_stat)
            owned_directory = os.open(
                ".",
                os.O_RDONLY | directory | nofollow | cloexec,
                dir_fd=host_directory_fd,
            )
            owned_stat = os.fstat(owned_directory)
            cls._check_directory_stat(owned_stat)
            if _directory_identity(owned_stat) != _directory_identity(host_stat):
                raise AuditSinkPoisoned("audit directory identity changed")
            if os.get_inheritable(owned_directory):
                raise AuditSinkPoisoned("audit directory descriptor is inheritable")

            audit_fd = os.open(
                _AUDIT_NAME,
                os.O_WRONLY | os.O_APPEND | os.O_CREAT | nofollow | cloexec,
                0o600,
                dir_fd=owned_directory,
            )
            file_stat = os.fstat(audit_fd)
            cls._check_file_stat(file_stat)
            named_stat = os.stat(
                _AUDIT_NAME, dir_fd=owned_directory, follow_symlinks=False
            )
            cls._check_file_stat(named_stat)
            if _identity(file_stat) != _identity(named_stat):
                raise AuditSinkPoisoned("audit file identity changed during open")
            if file_stat.st_size > file_budget:
                raise AuditSinkPoisoned("audit file exceeds its fixed budget")
            cls._check_file_flags(audit_fd)
            fcntl.flock(audit_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return cls(
                directory_fd=owned_directory,
                audit_fd=audit_fd,
                policy_id=selected_policy,
                directory_identity=_directory_identity(owned_stat),
                file_identity=_identity(file_stat),
                expected_size=file_stat.st_size,
                max_line_bytes=line_budget,
                max_file_bytes=file_budget,
            )
        except BaseException as error:
            cleanup_errors: list[BaseException] = []
            for descriptor in (audit_fd, owned_directory):
                if descriptor < 0:
                    continue
                try:
                    os.close(descriptor)
                except BaseException as cleanup_error:
                    cleanup_errors.append(cleanup_error)
            if cleanup_errors:
                raise AuditAcquisitionUncertain(
                    "durable audit acquisition cleanup is uncertain",
                    primary_error=error,
                    cleanup_errors=tuple(cleanup_errors),
                ) from cleanup_errors[0]
            if isinstance(error, AuditSinkPoisoned):
                raise
            raise AuditSinkPoisoned("durable audit acquisition refused") from error

    @staticmethod
    def _check_directory_stat(value: os.stat_result) -> None:
        if (
            not stat.S_ISDIR(value.st_mode)
            or value.st_uid != os.geteuid()
            or stat.S_IMODE(value.st_mode) & 0o022
        ):
            raise AuditSinkPoisoned("audit directory security refused")

    @staticmethod
    def _check_file_stat(value: os.stat_result) -> None:
        if (
            not stat.S_ISREG(value.st_mode)
            or value.st_uid != os.geteuid()
            or stat.S_IMODE(value.st_mode) != 0o600
            or value.st_nlink != 1
        ):
            raise AuditSinkPoisoned("audit file security refused")

    @staticmethod
    def _check_file_flags(audit_fd: int) -> None:
        flags = fcntl.fcntl(audit_fd, fcntl.F_GETFL)
        if (
            flags & os.O_ACCMODE != os.O_WRONLY
            or not flags & os.O_APPEND
            or os.get_inheritable(audit_fd)
        ):
            raise AuditSinkPoisoned("audit descriptor flags refused")

    @staticmethod
    def _lock_is_contended(error: OSError) -> bool:
        return error.errno in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}

    def _prove_owner_lock(self, *, expected_size: int) -> None:
        nofollow, _directory, cloexec = _platform_flags()
        witness = -1
        witness_acquired = False
        primary_error: BaseException | None = None
        cleanup_errors: list[BaseException] = []
        try:
            witness = os.open(
                _AUDIT_NAME,
                os.O_WRONLY | os.O_APPEND | nofollow | cloexec,
                dir_fd=self._directory_fd,
            )
            witness_stat = os.fstat(witness)
            self._check_file_stat(witness_stat)
            if (
                _identity(witness_stat) != self._file_identity
                or witness_stat.st_size != expected_size
            ):
                raise AuditSinkPoisoned(
                    "audit lock witness identity or size changed"
                )
            self._check_file_flags(witness)
            try:
                fcntl.flock(witness, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if not self._lock_is_contended(error):
                    raise
            else:
                witness_acquired = True
                raise AuditSinkPoisoned("audit owner lock is absent")

            try:
                fcntl.flock(
                    self._audit_fd, fcntl.LOCK_EX | fcntl.LOCK_NB
                )
            except OSError as error:
                if self._lock_is_contended(error):
                    raise AuditSinkPoisoned(
                        "audit owner lock changed"
                    ) from error
                raise
        except BaseException as error:
            primary_error = error

        if witness >= 0:
            if witness_acquired:
                try:
                    fcntl.flock(witness, fcntl.LOCK_UN)
                except BaseException as error:
                    cleanup_errors.append(error)
            try:
                os.close(witness)
            except BaseException as error:
                cleanup_errors.append(error)

        if cleanup_errors:
            self._close_uncertain = True
            if primary_error is not None:
                raise AuditAcquisitionUncertain(
                    "audit lock ownership proof cleanup is uncertain",
                    primary_error=primary_error,
                    cleanup_errors=tuple(cleanup_errors),
                ) from cleanup_errors[0]
            raise AuditSinkPoisoned(
                "audit lock witness cleanup is uncertain"
            ) from cleanup_errors[0]
        if primary_error is not None:
            if isinstance(primary_error, AuditSinkPoisoned):
                raise primary_error
            raise AuditSinkPoisoned(
                "audit lock ownership proof failed"
            ) from primary_error

    def _validate_live(self, *, expected_size: int) -> None:
        directory = os.fstat(self._directory_fd)
        self._check_directory_stat(directory)
        relative_directory = os.stat(
            ".", dir_fd=self._directory_fd, follow_symlinks=False
        )
        self._check_directory_stat(relative_directory)
        if (
            _directory_identity(directory) != self._directory_identity
            or _directory_identity(relative_directory) != self._directory_identity
        ):
            raise AuditSinkPoisoned("audit directory identity changed")

        opened = os.fstat(self._audit_fd)
        named = os.stat(_AUDIT_NAME, dir_fd=self._directory_fd, follow_symlinks=False)
        self._check_file_stat(opened)
        self._check_file_stat(named)
        if (
            _identity(opened) != self._file_identity
            or _identity(named) != self._file_identity
            or opened.st_size != expected_size
            or named.st_size != expected_size
        ):
            raise AuditSinkPoisoned("named audit file identity or size changed")
        self._check_file_flags(self._audit_fd)
        self._prove_owner_lock(expected_size=expected_size)

    def _encode(self, event: object) -> bytes:
        if (
            type(event) is not AuthAuditEvent
            or event.schema != AUTH_AUDIT_SCHEMA
            or event.policy_id != self._policy_id
            or type(event.code) is not str
            or event.code not in _CODES
            or type(event.accepted) is not bool
            or event.accepted != (event.code == "accepted")
        ):
            raise AuditSinkPoisoned("audit event contract refused")
        payload = (
            json.dumps(
                {
                    "accepted": event.accepted,
                    "code": event.code,
                    "policy_id": event.policy_id,
                    "schema": event.schema,
                },
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        if len(payload) > self._max_line_bytes:
            raise AuditSinkPoisoned("audit event exceeds its fixed line budget")
        return payload

    def emit(self, event: AuthAuditEvent) -> None:
        with self._gate:
            if self._closed or self._poisoned:
                raise AuditSinkPoisoned("audit sink is not live")
            try:
                payload = self._encode(event)
                target_size = self._expected_size + len(payload)
                if target_size > self._max_file_bytes:
                    raise AuditSinkPoisoned("audit file exceeds its fixed budget")
                self._validate_live(expected_size=self._expected_size)
                written = os.write(self._audit_fd, payload)
                if written != len(payload):
                    raise AuditSinkPoisoned("audit append was short or ambiguous")
                os.fsync(self._audit_fd)
                self._validate_live(expected_size=target_size)
                self._expected_size = target_size
            except BaseException as error:
                self._poisoned = True
                if isinstance(error, AuditSinkPoisoned):
                    raise
                raise AuditSinkPoisoned("durable audit append is uncertain") from error

    def close(self) -> None:
        with self._gate:
            if self._closed:
                if self._close_uncertain:
                    raise AuditSinkPoisoned("audit close is uncertain")
                return
            prior_close_uncertainty = self._close_uncertain
            errors: list[BaseException] = []
            try:
                self._validate_live(expected_size=self._expected_size)
            except BaseException as error:
                self._poisoned = True
                errors.append(error)
            self._closed = True
            try:
                fcntl.flock(self._audit_fd, fcntl.LOCK_UN)
            except BaseException as error:
                errors.append(error)
            for descriptor in (self._audit_fd, self._directory_fd):
                try:
                    os.close(descriptor)
                except BaseException as error:
                    errors.append(error)
            if errors or prior_close_uncertainty:
                self._poisoned = True
                self._close_uncertain = True
                if errors:
                    raise AuditSinkPoisoned("audit close is uncertain") from errors[0]
                raise AuditSinkPoisoned("audit close is uncertain")


__all__ = [
    "AuditAcquisitionUncertain",
    "AuditSinkPoisoned",
    "DurableAuthAuditSink",
]
