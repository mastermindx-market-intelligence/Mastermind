"""Durable, descriptor-relative auth audit for one fixed policy log.

The sink owns independently opened directory and file descriptions.  Every
append revalidates the named file before and after one write plus fsync.  Any
identity, flag, size, write, or durability uncertainty poisons the instance;
there is no retry, rotation, replacement descriptor, or second event schema.

The same instance is the only reader of its own ledger.  A read proves the
identical continuity an append proves (owned identity, owned size, owner
lock) and decodes every line back through the exact event encoders, so a
torn, foreign, or off-policy line is uncertainty rather than data.  Reads
never append, never poison, and never reopen admission.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import stat
import threading
from collections.abc import Iterable
from typing import Any

from .contracts import (
    AUTH_AUDIT_SCHEMA,
    CHANNEL_AUDIT_SCHEMA,
    AuthAuditEvent,
    AuthErrorCode,
    ChannelAuditEvent,
)

_AUDIT_NAME = "auth-audit.jsonl"
_POLICY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,95}$")
_CODES = frozenset({"accepted", *(code.value for code in AuthErrorCode)})
_CHANNEL_CODES = frozenset({"accepted", "channel_refused", "request_refused"})
_CHANNEL_TOOLS = frozenset(
    {
        "workspace_manifest",
        "read_project_file",
        "preview_text_replace",
        "prepare_text_patch",
        "commit_text_patch",
        "reconcile_text_patch",
        "prepare_project_command",
        "run_project_command",
        "read_action_result",
        "reconcile_action",
    }
)
# Modifying tools are the only admissions that can precede an effect
# dispatch.  Read/reconcile admissions never claim or publish anything.
_CHANNEL_MODIFYING_TOOLS = frozenset({"commit_text_patch", "run_project_command"})
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_CHANNEL_LINE_KEYS = frozenset(
    {"accepted", "action_digest", "channel_ref", "code", "policy_id", "schema", "tool"}
)
_OAUTH_LINE_KEYS = frozenset({"accepted", "code", "policy_id", "schema"})
ADMISSION_REFUSED_ONLY = "REFUSED_ONLY"
ADMISSION_ACCEPTED = "ACCEPTED"
ADMISSION_ABSENT = "ABSENT"
ADMISSION_UNCERTAIN = "UNCERTAIN"
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
        # One closed dispatch over the exact event types.  There is no
        # arbitrary callback serializer: each schema is encoded literally.
        if type(event) is AuthAuditEvent:
            return self._encode_oauth(event)
        if type(event) is ChannelAuditEvent:
            return self._encode_channel(event)
        raise AuditSinkPoisoned("audit event contract refused")

    def _encode_oauth(self, event: AuthAuditEvent) -> bytes:
        if (
            event.schema != AUTH_AUDIT_SCHEMA
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

    def _encode_channel(self, event: ChannelAuditEvent) -> bytes:
        if (
            event.schema != CHANNEL_AUDIT_SCHEMA
            or event.policy_id != self._policy_id
            or type(event.code) is not str
            or event.code not in _CHANNEL_CODES
            or type(event.accepted) is not bool
            or event.accepted != (event.code == "accepted")
            or type(event.channel_ref) is not str
            or _HEX64_RE.fullmatch(event.channel_ref) is None
            or type(event.tool) is not str
            or event.tool not in _CHANNEL_TOOLS
            or (
                event.action_digest is not None
                and (
                    type(event.action_digest) is not str
                    or _HEX64_RE.fullmatch(event.action_digest) is None
                )
            )
        ):
            raise AuditSinkPoisoned("audit channel event contract refused")
        payload = (
            json.dumps(
                {
                    "accepted": event.accepted,
                    "action_digest": event.action_digest,
                    "channel_ref": event.channel_ref,
                    "code": event.code,
                    "policy_id": event.policy_id,
                    "schema": event.schema,
                    "tool": event.tool,
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

    def emit(self, event: AuthAuditEvent | ChannelAuditEvent) -> None:
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

    def read_channel_admissions(self, action_digest: str) -> tuple[ChannelAuditEvent, ...]:
        """Return every durable channel admission fact for one exact action digest.

        The ledger is read through an independently opened read-only description
        of the same named file, gated by the same continuity proof an append
        uses: the named file must still carry the owned identity at the owned
        size with the owner lock held, before and after the bytes are taken.
        Every line is decoded and re-encoded through the exact event encoders
        and must round-trip byte-for-byte, so a torn, foreign, or off-policy line
        refuses the whole read.  The read never appends, never poisons the
        instance, and never reopens effect admission.
        """

        if type(action_digest) is not str or _HEX64_RE.fullmatch(action_digest) is None:
            raise AuditSinkPoisoned("audit action digest is invalid")
        nofollow, _directory, cloexec = _platform_flags()
        with self._gate:
            if self._closed or self._poisoned:
                raise AuditSinkPoisoned("audit sink is not live")
            expected_size = self._expected_size
            self._validate_live(expected_size=expected_size)
            reader = -1
            try:
                reader = os.open(
                    _AUDIT_NAME,
                    os.O_RDONLY | nofollow | cloexec,
                    dir_fd=self._directory_fd,
                )
                opened = os.fstat(reader)
                self._check_file_stat(opened)
                if _identity(opened) != self._file_identity or opened.st_size != expected_size:
                    raise AuditSinkPoisoned("audit read identity or size changed")
                chunks: list[bytes] = []
                remaining = expected_size
                while remaining > 0:
                    chunk = os.read(reader, min(remaining, 65536))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                if remaining != 0 or os.read(reader, 1):
                    raise AuditSinkPoisoned("audit read was short or ambiguous")
                closing = os.fstat(reader)
                if _identity(closing) != self._file_identity or closing.st_size != expected_size:
                    raise AuditSinkPoisoned("audit read identity or size changed")
            except AuditSinkPoisoned:
                raise
            except BaseException as error:
                raise AuditSinkPoisoned("durable audit read is uncertain") from error
            finally:
                if reader >= 0:
                    try:
                        os.close(reader)
                    except BaseException as error:
                        raise AuditSinkPoisoned("audit read close is uncertain") from error
            self._validate_live(expected_size=expected_size)
        raw = b"".join(chunks)
        if raw and not raw.endswith(b"\n"):
            raise AuditSinkPoisoned("audit ledger is torn")
        matched: list[ChannelAuditEvent] = []
        for line in raw.split(b"\n")[:-1] if raw else ():
            event = self._decode_line(line)
            if type(event) is ChannelAuditEvent and event.action_digest == action_digest:
                matched.append(event)
        return tuple(matched)

    def _decode_line(self, line: bytes) -> AuthAuditEvent | ChannelAuditEvent:
        # One closed dispatch back through the exact encoders: the decoded
        # event must re-encode to the identical bytes or the line is refused.
        if len(line) + 1 > self._max_line_bytes:
            raise AuditSinkPoisoned("audit line exceeds its fixed line budget")
        try:
            payload = json.loads(line.decode("ascii"))
        except (UnicodeError, ValueError, RecursionError) as error:
            raise AuditSinkPoisoned("audit line is not decodable") from error
        if type(payload) is not dict:
            raise AuditSinkPoisoned("audit line contract refused")
        keys = frozenset(payload)
        event: AuthAuditEvent | ChannelAuditEvent
        if keys == _CHANNEL_LINE_KEYS:
            event = ChannelAuditEvent(
                schema=payload["schema"],
                policy_id=payload["policy_id"],
                code=payload["code"],
                accepted=payload["accepted"],
                channel_ref=payload["channel_ref"],
                tool=payload["tool"],
                action_digest=payload["action_digest"],
            )
        elif keys == _OAUTH_LINE_KEYS:
            event = AuthAuditEvent(
                schema=payload["schema"],
                policy_id=payload["policy_id"],
                code=payload["code"],
                accepted=payload["accepted"],
            )
        else:
            raise AuditSinkPoisoned("audit line contract refused")
        if self._encode(event) != line + b"\n":
            raise AuditSinkPoisoned("audit line contract refused")
        return event

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


def classify_channel_admissions(
    events: Iterable[ChannelAuditEvent],
    *,
    action_digest: str,
    channel_ref: str,
    policy_id: str,
    modifying_tool: str,
) -> str:
    """Closed pre-dispatch admission verdict for one exact action digest.

    ``REFUSED_ONLY``: this channel durably refused ``modifying_tool`` for the
    digest before dispatch at least once, and no modifying tool was ever
    accepted for the digest by any channel in this ledger.  ``ACCEPTED``: some
    modifying admission was accepted, so a dispatch may have crossed the
    effect boundary.  ``ABSENT``: no modifying admission exists for the digest.
    ``UNCERTAIN``: a fact for the digest is off-contract for this policy or
    channel, so the ledger cannot be trusted to speak for this action.  Only
    ``REFUSED_ONLY`` may ever support ``NOT_APPLIED``; every other verdict
    leaves the effect unknown.
    """

    if (
        type(action_digest) is not str
        or _HEX64_RE.fullmatch(action_digest) is None
        or type(channel_ref) is not str
        or _HEX64_RE.fullmatch(channel_ref) is None
        or type(policy_id) is not str
        or _POLICY_ID_RE.fullmatch(policy_id) is None
        or modifying_tool not in _CHANNEL_MODIFYING_TOOLS
    ):
        return ADMISSION_UNCERTAIN
    refused = False
    for event in events:
        if type(event) is not ChannelAuditEvent or event.action_digest != action_digest:
            continue
        if (
            event.schema != CHANNEL_AUDIT_SCHEMA
            or event.policy_id != policy_id
            or event.code not in _CHANNEL_CODES
            or type(event.accepted) is not bool
            or event.accepted != (event.code == "accepted")
            or event.tool not in _CHANNEL_TOOLS
        ):
            return ADMISSION_UNCERTAIN
        if event.tool not in _CHANNEL_MODIFYING_TOOLS:
            continue
        if event.accepted:
            return ADMISSION_ACCEPTED
        if event.code != "channel_refused" or event.channel_ref != channel_ref:
            return ADMISSION_UNCERTAIN
        if event.tool == modifying_tool:
            refused = True
    return ADMISSION_REFUSED_ONLY if refused else ADMISSION_ABSENT


__all__ = [
    "ADMISSION_ABSENT",
    "ADMISSION_ACCEPTED",
    "ADMISSION_REFUSED_ONLY",
    "ADMISSION_UNCERTAIN",
    "AuditAcquisitionUncertain",
    "AuditSinkPoisoned",
    "DurableAuthAuditSink",
    "classify_channel_admissions",
]
