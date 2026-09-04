"""Provider-work-free Claude Worker realm/auth preflight.

This executable is the single Claude preflight family reserved by PF1 and
advanced by Operator Continuity OCR-1 V3. It owns only non-secret binary/auth
readiness observations. It does not perform login, execute a model turn,
select capacity, create Executive lifecycle state, or persist provider identity.

V1 intentionally permits only two provider commands:

* ``claude --version``
* ``claude auth status``

The public receipt is a closed, secret-free contract. Provider account PII is
never copied into it. Host/principal references are wire identities supplied by
their existing canonical owners; syntax validation in this module is never
proof that the current process matches those owners.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "mastermind.claude_worker_preflight.v1"
EXECUTION_CONTEXTS = frozenset({"INTERACTIVE_PRINCIPAL", "WORKER_BROKER"})
AUTH_IDENTITY_CONFIDENCE = frozenset({"SLOT_ONLY", "PROVIDER_REPORTED"})
ISOLATION_BASES = frozenset(
    {"OS_PRINCIPAL_KEYCHAIN", "NON_MACOS_PROVIDER_PATH", "UNKNOWN"}
)
AUTH_METHODS = frozenset({"claudeai", "non_native", "unknown"})
API_PROVIDERS = frozenset({"first_party", "non_native", "unknown"})
VERDICTS = frozenset(
    {
        "INTERACTIVE_AUTH_READY",
        "WORKER_CONTEXT_AUTH_READY",
        "LOGIN_REQUIRED",
        "NATIVE_AUTH_NOT_SELECTED",
        "WORKER_CONTEXT_AUTH_UNAVAILABLE",
        "EXECUTION_CONTEXT_UNPROVEN",
        "HOST_IDENTITY_SEAM_UNAVAILABLE",
        "PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE",
        "PRINCIPAL_CONTEXT_MISMATCH",
        "BINARY_UNAVAILABLE",
        "AUTH_STATUS_UNSUPPORTED",
    }
)
REASON_CODES = VERDICTS | frozenset(
    {
        "COMMAND_NOT_ALLOWED",
        "BINARY_INVALID",
        "PROVIDER_TIMEOUT",
        "PROVIDER_COMMAND_FAILED",
    }
)

_RECEIPT_KEYS = frozenset(
    {
        "schema",
        "realm_label",
        "host_ref",
        "os_principal_ref",
        "observed_at",
        "claude_binary_sha256",
        "claude_version",
        "auth_ready",
        "auth_method",
        "api_provider",
        "auth_identity_confidence",
        "macos_credential_isolation_basis",
        "execution_context",
        "worker_id",
        "quota_class",
        "verdict",
        "reason_codes",
    }
)
_READY_VERDICTS = frozenset({"INTERACTIVE_AUTH_READY", "WORKER_CONTEXT_AUTH_READY"})
_REALM_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_HOST_RE = re.compile(r"^host-[A-Za-z0-9][A-Za-z0-9._-]{7,63}$")
_PRINCIPAL_RE = re.compile(r"^principal-[A-Za-z0-9][A-Za-z0-9._-]{7,63}$")
_WORKER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_QUOTA_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CLAUDE_VERSION_RE = re.compile(
    r"^(?:0|[1-9][0-9]{0,3})\."
    r"(?:0|[1-9][0-9]{0,3})\."
    r"(?:0|[1-9][0-9]{0,7})$"
)
_CLAUDE_VERSION_OUTPUT_RE = re.compile(
    r"^(?P<version>(?:0|[1-9][0-9]{0,3})\."
    r"(?:0|[1-9][0-9]{0,3})\."
    r"(?:0|[1-9][0-9]{0,7}))"
    r"(?: \(Claude Code\))?$"
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_RE = re.compile(
    r"(?i)(?:xox[a-z]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})"
)
_RAW_AUTH_ALLOWED_KEYS = frozenset(
    {
        "loggedIn",
        "authMethod",
        "apiProvider",
        "subscriptionType",
        "apiKeySource",
        # Known provider PII is tolerated as INPUT only so it can be discarded.
        # It is never returned or persisted by this module.
        "email",
        "organization",
        "accountId",
        "organizationId",
    }
)
_PROVIDER_TIMEOUT_SECONDS = 15.0
_PROVIDER_IDLE_TIMEOUT_SECONDS = 5.0
_PROCESS_TERMINATE_GRACE_SECONDS = 0.5
_READ_CHUNK_BYTES = 8 * 1024
_HASH_CHUNK_BYTES = 1024 * 1024
# A reviewed provider binary may be large, but hashing must never read an
# unbounded caller-selected file into memory or chase growth without a ceiling.
MAX_BINARY_BYTES = 512 * 1024 * 1024
MAX_STDOUT_BYTES = 16 * 1024
MAX_STDERR_BYTES = 4 * 1024
MAX_OUTPUT_LINE_BYTES = 16 * 1024
MAX_AUTH_JSON_BYTES = 16 * 1024
MAX_AUTH_STRING_BYTES = 1024

_SAFE_CHILD_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
_CHILD_ENV_PATH_KEYS = frozenset(
    {
        "HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "CLAUDE_CONFIG_DIR",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
)
_DENIED_PROVIDER_ENV_KEYS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_API_URL",
        "ANTHROPIC_PROFILE",
        "ANTHROPIC_FEDERATION_RULE_ID",
        "ANTHROPIC_ORGANIZATION_ID",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
        "CLAUDE_CODE_API_KEY_HELPER",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_BEARER_TOKEN_BEDROCK",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "CLOUD_ML_REGION",
    }
)
_DENIED_PROVIDER_ENV_PREFIXES = (
    "ANTHROPIC_",
    "CLAUDE_CODE_OAUTH_TOKEN_",
)


class PreflightError(RuntimeError):
    """Bounded fail-closed preflight refusal."""


@dataclasses.dataclass(frozen=True)
class AuthObservation:
    auth_ready: bool
    auth_method: str
    api_provider: str
    reason_codes: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class CommandObservation:
    returncode: int
    stdout: bytes | str


@dataclasses.dataclass(frozen=True)
class _DirectoryIdentity:
    device: int
    inode: int
    mode: int
    uid: int
    gid: int


@dataclasses.dataclass(frozen=True)
class _BinaryIdentity:
    device: int
    inode: int
    mode: int
    links: int
    uid: int
    gid: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclasses.dataclass
class _RetainedExecutable:
    """Process-local descriptor graph for one exact executable object."""

    path: Path
    directory_fds: tuple[int, ...]
    directory_names: tuple[str, ...]
    directory_identities: tuple[_DirectoryIdentity, ...]
    leaf_name: str
    fd: int
    identity: _BinaryIdentity
    sha256: str
    execution_directory: Path
    execution_directory_fd: int
    execution_directory_identity: _DirectoryIdentity
    execution_name: str
    execution_fd: int
    execution_identity: _BinaryIdentity
    closed: bool = False
    cleanup_failed: bool = False

    @property
    def execution_path(self) -> str:
        if self.closed or self.execution_fd < 0:
            _raise("BINARY_CHANGED_DURING_PREFLIGHT")
        # Darwin has no public fexecve/execveat equivalent. This private-copy
        # coordinate is therefore valid only inside the canonical OS-principal
        # trust boundary enforced by F6; it is not a hostile-same-EUID sandbox.
        return str(self.execution_directory / self.execution_name)

    def close(self) -> None:
        if self.closed:
            if self.cleanup_failed:
                _raise("BINARY_CHANGED_DURING_PREFLIGHT")
            return
        self.closed = True
        cleanup_ok = True
        cleanup_directory_fd = self.execution_directory_fd
        cleanup_execution_fd = self.execution_fd
        self.execution_directory_fd = -1
        self.execution_fd = -1
        if cleanup_execution_fd >= 0:
            try:
                os.close(cleanup_execution_fd)
            except OSError:
                cleanup_ok = False
        if cleanup_directory_fd >= 0:
            try:
                os.fchmod(cleanup_directory_fd, 0o700)
            except OSError:
                pass
            cleanup_ok = (
                _remove_execution_file(cleanup_directory_fd, self.execution_name)
                and cleanup_ok
            )
            try:
                os.close(cleanup_directory_fd)
            except OSError:
                cleanup_ok = False
        cleanup_ok = (
            _remove_execution_directory(
                self.execution_directory,
                self.execution_directory_identity,
            )
            and cleanup_ok
        )

        descriptors = (self.fd, *reversed(self.directory_fds))
        self.fd = -1
        for descriptor in descriptors:
            if descriptor < 0:
                continue
            try:
                os.close(descriptor)
            except OSError:
                cleanup_ok = False
        self.cleanup_failed = not cleanup_ok
        if self.cleanup_failed:
            _raise("BINARY_CHANGED_DURING_PREFLIGHT")

    def __enter__(self) -> _RetainedExecutable:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback
        self.close()


def _raise(code: str) -> None:
    raise PreflightError(code)


def _reject_secret_shaped(value: Any) -> None:
    if isinstance(value, str):
        if _SECRET_RE.search(value):
            _raise("SECRET_SHAPED_VALUE")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_secret_shaped(str(key))
            _reject_secret_shaped(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _reject_secret_shaped(item)


def _bounded_text(value: Any, *, maximum: int = 128) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum or _CONTROL_RE.search(text):
        _raise("RECEIPT_INVALID")
    _reject_secret_shaped(text)
    return text


def _require_utc(value: Any) -> str:
    text = _bounded_text(value, maximum=40)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        _raise("RECEIPT_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() != datetime.now(UTC).utcoffset():
        _raise("RECEIPT_INVALID")
    return text


def _normalize_claude_version(value: Any) -> str:
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8", "strict").strip()
        except UnicodeDecodeError:
            _raise("BINARY_INVALID")
    elif isinstance(value, str):
        text = value.strip()
    else:
        _raise("BINARY_INVALID")
    if not text or len(text) > 128 or _CONTROL_RE.search(text):
        _raise("BINARY_INVALID")
    _reject_secret_shaped(text)
    match = _CLAUDE_VERSION_OUTPUT_RE.fullmatch(text)
    if match is None:
        _raise("BINARY_INVALID")
    return match.group("version")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def require_canonical_identity(host_ref: str, os_principal_ref: str) -> tuple[str, str]:
    """Validate only the closed opaque identity wire.

    This function deliberately does *not* prove that the caller currently runs
    on that host or OS principal. That proof belongs to the existing identity
    owners and must be established before a ready receipt can be minted.
    """

    host = str(host_ref or "").strip()
    principal = str(os_principal_ref or "").strip()
    if not host or host == "local-unbound" or _HOST_RE.fullmatch(host) is None:
        _raise("HOST_IDENTITY_SEAM_UNAVAILABLE")
    if not principal or _PRINCIPAL_RE.fullmatch(principal) is None:
        _raise("PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE")
    return host, principal


def require_current_identity_owner(host_ref: str, os_principal_ref: str) -> None:
    """Fail closed until the current estate exposes the accepted host owner.

    OCR-1 V3 Task 2 forbids deriving a competing host/principal identity from
    hostname, UID, username, home path, or machine UUID. Current protected
    Capacity/Executive law has no concrete host-ref resolver available to this
    CLI, so a syntactically valid caller declaration remains unproven.
    """

    require_canonical_identity(host_ref, os_principal_ref)
    _raise("HOST_IDENTITY_SEAM_UNAVAILABLE")


def _required_open_flags(*names: str) -> int:
    flags = 0
    for name in names:
        value = getattr(os, name, None)
        if type(value) is not int or value == 0:
            _raise("BINARY_INVALID")
        flags |= value
    return flags


def _directory_identity(info: os.stat_result) -> _DirectoryIdentity:
    mode = stat.S_IMODE(info.st_mode)
    writable_by_others = bool(mode & (stat.S_IWGRP | stat.S_IWOTH))
    safe_shared_directory = (
        info.st_uid == 0 and bool(mode & stat.S_ISVTX) and stat.S_ISDIR(info.st_mode)
    )
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid not in {0, os.geteuid()}
        or (writable_by_others and not safe_shared_directory)
    ):
        _raise("BINARY_INVALID")
    return _DirectoryIdentity(
        device=int(info.st_dev),
        inode=int(info.st_ino),
        mode=mode,
        uid=int(info.st_uid),
        gid=int(info.st_gid),
    )


def _binary_identity(info: os.stat_result) -> _BinaryIdentity:
    mode = stat.S_IMODE(info.st_mode)
    owner_execute = bool(mode & stat.S_IXUSR) if info.st_uid == os.geteuid() else False
    root_execute = bool(mode & stat.S_IXOTH) if info.st_uid == 0 else False
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid not in {0, os.geteuid()}
        or not (owner_execute or root_execute)
        or bool(mode & (stat.S_IWGRP | stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID))
        or info.st_nlink != 1
        or info.st_size <= 0
        or info.st_size > MAX_BINARY_BYTES
    ):
        _raise("BINARY_INVALID")
    return _BinaryIdentity(
        device=int(info.st_dev),
        inode=int(info.st_ino),
        mode=mode,
        links=int(info.st_nlink),
        uid=int(info.st_uid),
        gid=int(info.st_gid),
        size=int(info.st_size),
        modified_ns=int(info.st_mtime_ns),
        changed_ns=int(info.st_ctime_ns),
    )


def _sha256_descriptor(
    descriptor: int,
    *,
    expected_size: int,
    error_code: str,
) -> str:
    if not hasattr(os, "pread"):
        _raise(error_code)
    digest = hashlib.sha256()
    total = 0
    try:
        while True:
            chunk = os.pread(descriptor, _HASH_CHUNK_BYTES, total)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BINARY_BYTES:
                _raise(error_code)
            digest.update(chunk)
    except OSError:
        _raise(error_code)
    if total != expected_size or total <= 0:
        _raise(error_code)
    return digest.hexdigest()


def _same_directory(info: os.stat_result, expected: _DirectoryIdentity) -> bool:
    return (
        stat.S_ISDIR(info.st_mode)
        and int(info.st_dev) == expected.device
        and int(info.st_ino) == expected.inode
        and stat.S_IMODE(info.st_mode) == expected.mode
        and int(info.st_uid) == expected.uid
        and int(info.st_gid) == expected.gid
    )


def _same_binary(info: os.stat_result, expected: _BinaryIdentity) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and int(info.st_dev) == expected.device
        and int(info.st_ino) == expected.inode
        and stat.S_IMODE(info.st_mode) == expected.mode
        and int(info.st_nlink) == expected.links
        and int(info.st_uid) == expected.uid
        and int(info.st_gid) == expected.gid
        and int(info.st_size) == expected.size
        and int(info.st_mtime_ns) == expected.modified_ns
        and int(info.st_ctime_ns) == expected.changed_ns
    )


def _remove_execution_file(directory_fd: int, execution_name: str) -> bool:
    for _ in range(2):
        try:
            os.unlink(execution_name, dir_fd=directory_fd)
        except FileNotFoundError:
            return True
        except OSError:
            continue
        return True
    return False


def _remove_execution_directory(
    directory: Path,
    expected: _DirectoryIdentity | None,
) -> bool:
    for _ in range(2):
        try:
            current = directory.lstat()
        except FileNotFoundError:
            return True
        except OSError:
            continue
        if (
            not stat.S_ISDIR(current.st_mode)
            or (expected is not None and int(current.st_dev) != expected.device)
            or (expected is not None and int(current.st_ino) != expected.inode)
            or (expected is None and int(current.st_uid) != os.geteuid())
        ):
            return False
        try:
            os.rmdir(directory)
        except FileNotFoundError:
            return True
        except OSError:
            continue
        return True
    return False


def _safe_scratch_root() -> Path:
    try:
        root = Path("/tmp").resolve(strict=True)
        _directory_identity(root.lstat())
    except (OSError, PreflightError):
        _raise("BINARY_INVALID")
    return root


def _create_execution_copy(
    source_fd: int,
    source_identity: _BinaryIdentity,
    source_sha256: str,
) -> tuple[Path, int, _DirectoryIdentity, str, int, _BinaryIdentity]:
    directory = Path(
        tempfile.mkdtemp(
            prefix="mastermind-claude-preflight-",
            dir=str(_safe_scratch_root()),
        )
    )
    directory_fd = -1
    writer_fd = -1
    execution_fd = -1
    execution_name = "claude"
    complete = False
    cleanup_directory_identity: _DirectoryIdentity | None = None
    try:
        directory_fd = os.open(
            directory,
            os.O_RDONLY | _required_open_flags("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC"),
        )
        initial_directory = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(initial_directory.st_mode)
            or initial_directory.st_uid != os.geteuid()
            or stat.S_IMODE(initial_directory.st_mode) != 0o700
        ):
            _raise("BINARY_INVALID")
        cleanup_directory_identity = _directory_identity(initial_directory)

        writer_fd = os.open(
            execution_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | _required_open_flags("O_NOFOLLOW", "O_CLOEXEC"),
            0o700,
            dir_fd=directory_fd,
        )
        copied_digest = hashlib.sha256()
        offset = 0
        while offset < source_identity.size:
            chunk = os.pread(
                source_fd,
                min(_HASH_CHUNK_BYTES, source_identity.size - offset),
                offset,
            )
            if not chunk:
                _raise("BINARY_CHANGED_DURING_PREFLIGHT")
            copied_digest.update(chunk)
            written = 0
            while written < len(chunk):
                count = os.write(writer_fd, chunk[written:])
                if count <= 0:
                    _raise("BINARY_INVALID")
                written += count
            offset += len(chunk)
        if os.pread(source_fd, 1, offset):
            _raise("BINARY_CHANGED_DURING_PREFLIGHT")
        if copied_digest.hexdigest() != source_sha256:
            _raise("BINARY_CHANGED_DURING_PREFLIGHT")
        os.fsync(writer_fd)
        os.fchmod(writer_fd, 0o500)
        writer_identity = _binary_identity(os.fstat(writer_fd))
        os.close(writer_fd)
        writer_fd = -1

        execution_fd = os.open(
            execution_name,
            os.O_RDONLY | _required_open_flags("O_NOFOLLOW", "O_CLOEXEC"),
            dir_fd=directory_fd,
        )
        execution_identity = _binary_identity(os.fstat(execution_fd))
        if execution_identity != writer_identity:
            _raise("BINARY_INVALID")
        if (
            _sha256_descriptor(
                execution_fd,
                expected_size=execution_identity.size,
                error_code="BINARY_INVALID",
            )
            != source_sha256
        ):
            _raise("BINARY_INVALID")

        os.fchmod(directory_fd, 0o500)
        directory_identity = _directory_identity(os.fstat(directory_fd))
        complete = True
        return (
            directory,
            directory_fd,
            directory_identity,
            execution_name,
            execution_fd,
            execution_identity,
        )
    except PreflightError:
        raise
    except (OSError, ValueError, TypeError):
        _raise("BINARY_INVALID")
    finally:
        cleanup_ok = True
        if writer_fd >= 0:
            try:
                os.close(writer_fd)
            except OSError:
                cleanup_ok = False
        if not complete:
            if execution_fd >= 0:
                try:
                    os.close(execution_fd)
                except OSError:
                    cleanup_ok = False
            if directory_fd >= 0:
                try:
                    os.fchmod(directory_fd, 0o700)
                except OSError:
                    pass
                cleanup_ok = (
                    _remove_execution_file(directory_fd, execution_name)
                    and cleanup_ok
                )
                try:
                    os.close(directory_fd)
                except OSError:
                    cleanup_ok = False
            cleanup_ok = (
                _remove_execution_directory(directory, cleanup_directory_identity)
                and cleanup_ok
            )
            if not cleanup_ok:
                _raise("BINARY_CHANGED_DURING_PREFLIGHT")


def _assert_retained_binary(
    retained: _RetainedExecutable, *, verify_source_digest: bool = True
) -> None:
    if (
        retained.closed
        or retained.fd < 0
        or retained.execution_fd < 0
        or retained.execution_directory_fd < 0
        or not retained.directory_fds
    ):
        _raise("BINARY_CHANGED_DURING_PREFLIGHT")
    try:
        if not _same_directory(
            os.fstat(retained.directory_fds[0]), retained.directory_identities[0]
        ):
            _raise("BINARY_CHANGED_DURING_PREFLIGHT")
        for index, name in enumerate(retained.directory_names, start=1):
            named = os.stat(
                name,
                dir_fd=retained.directory_fds[index - 1],
                follow_symlinks=False,
            )
            opened = os.fstat(retained.directory_fds[index])
            expected = retained.directory_identities[index]
            if not _same_directory(named, expected) or not _same_directory(
                opened, expected
            ):
                _raise("BINARY_CHANGED_DURING_PREFLIGHT")

        named_leaf = os.stat(
            retained.leaf_name,
            dir_fd=retained.directory_fds[-1],
            follow_symlinks=False,
        )
        opened_leaf = os.fstat(retained.fd)
        if not _same_binary(named_leaf, retained.identity) or not _same_binary(
            opened_leaf, retained.identity
        ):
            _raise("BINARY_CHANGED_DURING_PREFLIGHT")
        if verify_source_digest:
            digest = _sha256_descriptor(
                retained.fd,
                expected_size=retained.identity.size,
                error_code="BINARY_CHANGED_DURING_PREFLIGHT",
            )
            if digest != retained.sha256 or not _same_binary(
                os.fstat(retained.fd), retained.identity
            ):
                _raise("BINARY_CHANGED_DURING_PREFLIGHT")

        execution_directory = os.fstat(retained.execution_directory_fd)
        named_execution_directory = retained.execution_directory.lstat()
        named_execution = os.stat(
            retained.execution_name,
            dir_fd=retained.execution_directory_fd,
            follow_symlinks=False,
        )
        opened_execution = os.fstat(retained.execution_fd)
        if not _same_directory(
            execution_directory, retained.execution_directory_identity
        ) or not _same_directory(
            named_execution_directory, retained.execution_directory_identity
        ) or not _same_binary(
            named_execution, retained.execution_identity
        ) or not _same_binary(opened_execution, retained.execution_identity):
            _raise("BINARY_CHANGED_DURING_PREFLIGHT")
        execution_digest = _sha256_descriptor(
            retained.execution_fd,
            expected_size=retained.execution_identity.size,
            error_code="BINARY_CHANGED_DURING_PREFLIGHT",
        )
        if execution_digest != retained.sha256 or not _same_binary(
            os.fstat(retained.execution_fd), retained.execution_identity
        ):
            _raise("BINARY_CHANGED_DURING_PREFLIGHT")
    except PreflightError:
        raise
    except (OSError, ValueError):
        _raise("BINARY_CHANGED_DURING_PREFLIGHT")


def _retain_binary(binary: Path) -> _RetainedExecutable:
    raw = Path(binary)
    if (
        not raw.is_absolute()
        or raw.anchor != "/"
        or len(raw.parts) < 2
        or any(part in {"", ".", ".."} for part in raw.parts[1:])
    ):
        _raise("BINARY_INVALID")

    directory_fds: list[int] = []
    directory_names: list[str] = []
    directory_identities: list[_DirectoryIdentity] = []
    leaf_fd = -1
    try:
        root_flags = os.O_RDONLY | _required_open_flags("O_DIRECTORY", "O_CLOEXEC")
        directory_flags = root_flags | _required_open_flags("O_NOFOLLOW")
        # The leaf is caller-selected and has not been type-checked yet.  A
        # blocking read-open would hang forever on a FIFO before the fixed
        # refusal boundary or any provider timeout exists.
        leaf_flags = os.O_RDONLY | _required_open_flags(
            "O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK"
        )

        root_fd = os.open("/", root_flags)
        directory_fds.append(root_fd)
        directory_identities.append(_directory_identity(os.fstat(root_fd)))

        for part in raw.parts[1:-1]:
            child_fd = os.open(part, directory_flags, dir_fd=directory_fds[-1])
            directory_names.append(part)
            directory_fds.append(child_fd)
            directory_identities.append(_directory_identity(os.fstat(child_fd)))

        leaf_fd = os.open(raw.name, leaf_flags, dir_fd=directory_fds[-1])
        identity = _binary_identity(os.fstat(leaf_fd))
        digest = _sha256_descriptor(
            leaf_fd,
            expected_size=identity.size,
            error_code="BINARY_INVALID",
        )
        (
            execution_directory,
            execution_directory_fd,
            execution_directory_identity,
            execution_name,
            execution_fd,
            execution_identity,
        ) = _create_execution_copy(leaf_fd, identity, digest)
        retained = _RetainedExecutable(
            path=raw,
            directory_fds=tuple(directory_fds),
            directory_names=tuple(directory_names),
            directory_identities=tuple(directory_identities),
            leaf_name=raw.name,
            fd=leaf_fd,
            identity=identity,
            sha256=digest,
            execution_directory=execution_directory,
            execution_directory_fd=execution_directory_fd,
            execution_directory_identity=execution_directory_identity,
            execution_name=execution_name,
            execution_fd=execution_fd,
            execution_identity=execution_identity,
        )
        try:
            _assert_retained_binary(retained, verify_source_digest=False)
        except BaseException:
            retained.close()
            leaf_fd = -1
            directory_fds = []
            raise
        leaf_fd = -1
        directory_fds = []
        return retained
    except FileNotFoundError:
        _raise("BINARY_UNAVAILABLE")
    except PreflightError:
        raise
    except (OSError, ValueError, TypeError):
        _raise("BINARY_INVALID")
    finally:
        if leaf_fd >= 0:
            try:
                os.close(leaf_fd)
            except OSError:
                pass
        for descriptor in reversed(directory_fds):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _require_binary(binary: Path) -> Path:
    with _retain_binary(binary) as retained:
        return retained.path


def build_allowed_argv(
    binary: Path | _RetainedExecutable, operation: str
) -> tuple[str, ...]:
    if not isinstance(binary, _RetainedExecutable):
        _raise("BINARY_INVALID")
    _assert_retained_binary(binary, verify_source_digest=False)
    coordinate = binary.execution_path
    if operation == "version":
        return (coordinate, "--version")
    if operation == "auth_status":
        return (coordinate, "auth", "status")
    _raise("COMMAND_NOT_ALLOWED")


def normalize_auth_status(raw: Mapping[str, Any]) -> AuthObservation:
    if not isinstance(raw, Mapping) or not set(raw).issubset(_RAW_AUTH_ALLOWED_KEYS):
        _raise("AUTH_STATUS_UNSUPPORTED")
    logged_in = raw.get("loggedIn")
    if type(logged_in) is not bool:
        _raise("AUTH_STATUS_UNSUPPORTED")

    method_raw = raw.get("authMethod")
    provider_raw = raw.get("apiProvider")
    if not logged_in:
        return AuthObservation(
            auth_ready=False,
            auth_method="unknown",
            api_provider="unknown",
            reason_codes=("LOGIN_REQUIRED",),
        )
    if not isinstance(method_raw, str) or not isinstance(provider_raw, str):
        _raise("AUTH_STATUS_UNSUPPORTED")

    method = method_raw.strip()
    provider = provider_raw.strip()
    if method == "claude.ai" and provider == "firstParty":
        return AuthObservation(
            auth_ready=True,
            auth_method="claudeai",
            api_provider="first_party",
            reason_codes=(),
        )
    return AuthObservation(
        auth_ready=False,
        auth_method="non_native",
        api_provider="non_native",
        reason_codes=("NATIVE_AUTH_NOT_SELECTED",),
    )


def validate_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the closed public wire; do not treat validity as mint authority."""

    _reject_secret_shaped(value)
    if not isinstance(value, Mapping) or set(value) != _RECEIPT_KEYS:
        _raise("RECEIPT_INVALID")
    result = dict(value)
    if result["schema"] != SCHEMA:
        _raise("RECEIPT_INVALID")

    realm = _bounded_text(result["realm_label"], maximum=64)
    if _REALM_RE.fullmatch(realm) is None:
        _raise("RECEIPT_INVALID")
    host, principal = require_canonical_identity(
        str(result["host_ref"]), str(result["os_principal_ref"])
    )
    result["host_ref"], result["os_principal_ref"] = host, principal
    _require_utc(result["observed_at"])
    digest = result["claude_binary_sha256"]
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        _raise("RECEIPT_INVALID")
    version = result["claude_version"]
    if not isinstance(version, str) or _CLAUDE_VERSION_RE.fullmatch(version) is None:
        _raise("RECEIPT_INVALID")
    if type(result["auth_ready"]) is not bool:
        _raise("RECEIPT_INVALID")
    if result["auth_method"] not in AUTH_METHODS:
        _raise("RECEIPT_INVALID")
    if result["api_provider"] not in API_PROVIDERS:
        _raise("RECEIPT_INVALID")
    if result["auth_identity_confidence"] not in AUTH_IDENTITY_CONFIDENCE:
        _raise("RECEIPT_INVALID")
    isolation_basis = result["macos_credential_isolation_basis"]
    if isolation_basis not in ISOLATION_BASES:
        _raise("RECEIPT_INVALID")

    context = result["execution_context"]
    if context not in EXECUTION_CONTEXTS:
        _raise("RECEIPT_INVALID")
    worker_id, quota_class = result["worker_id"], result["quota_class"]
    if context == "INTERACTIVE_PRINCIPAL":
        if worker_id is not None or quota_class is not None:
            _raise("RECEIPT_INVALID")
    elif (
        not isinstance(worker_id, str)
        or _WORKER_RE.fullmatch(worker_id) is None
        or not isinstance(quota_class, str)
        or _QUOTA_RE.fullmatch(quota_class) is None
    ):
        _raise("RECEIPT_INVALID")

    if result["verdict"] not in VERDICTS:
        _raise("RECEIPT_INVALID")
    reasons = result["reason_codes"]
    if (
        not isinstance(reasons, list)
        or len(reasons) > 8
        or len(reasons) != len(set(reasons))
        or any(not isinstance(item, str) or item not in REASON_CODES for item in reasons)
    ):
        _raise("RECEIPT_INVALID")
    if result["auth_ready"]:
        if isolation_basis == "UNKNOWN":
            _raise("RECEIPT_INVALID")
        if (
            result["auth_method"] != "claudeai"
            or result["api_provider"] != "first_party"
        ):
            _raise("RECEIPT_INVALID")
        expected = (
            "INTERACTIVE_AUTH_READY"
            if context == "INTERACTIVE_PRINCIPAL"
            else "WORKER_CONTEXT_AUTH_READY"
        )
        if result["verdict"] != expected or reasons:
            _raise("RECEIPT_INVALID")
    elif result["verdict"] in _READY_VERDICTS:
        _raise("RECEIPT_INVALID")
    return result


def _provider_environment_key_is_denied(key: str) -> bool:
    upper = key.upper()
    if upper in _DENIED_PROVIDER_ENV_KEYS:
        return True
    if any(upper.startswith(prefix) for prefix in _DENIED_PROVIDER_ENV_PREFIXES):
        return True
    if upper.startswith("CLAUDE_CODE_") and any(
        marker in upper
        for marker in ("API", "AUTH", "TOKEN", "GATEWAY", "HELPER", "FEDERATION")
    ):
        return True
    return False


def _closed_child_environment(
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    incoming = os.environ if source is None else source
    for key in incoming:
        if not isinstance(key, str) or _provider_environment_key_is_denied(key):
            _raise("PROVIDER_ENV_REFUSED")

    result = {
        "PATH": _SAFE_CHILD_PATH,
        "LANG": "C",
        "LC_ALL": "C",
        "TMPDIR": "/tmp",
    }
    for key in _CHILD_ENV_PATH_KEYS:
        value = incoming.get(key)
        if value is None:
            continue
        try:
            encoded_length = len(value.encode("utf-8", "strict"))
        except (AttributeError, UnicodeError):
            _raise("PROVIDER_ENV_REFUSED")
        if (
            not isinstance(value, str)
            or not value
            or encoded_length > 4096
            or _CONTROL_RE.search(value)
            or _SECRET_RE.search(value)
            or not Path(value).is_absolute()
        ):
            _raise("PROVIDER_ENV_REFUSED")
        result[key] = value
    return result


def _line_length_after(current: int, chunk: bytes) -> int:
    pieces = chunk.split(b"\n")
    if len(pieces) == 1:
        candidate = current + len(chunk)
        if candidate > MAX_OUTPUT_LINE_BYTES:
            _raise("PROVIDER_COMMAND_FAILED")
        return candidate
    if current + len(pieces[0]) > MAX_OUTPUT_LINE_BYTES or any(
        len(piece) > MAX_OUTPUT_LINE_BYTES for piece in pieces[1:-1]
    ):
        _raise("PROVIDER_COMMAND_FAILED")
    if len(pieces[-1]) > MAX_OUTPUT_LINE_BYTES:
        _raise("PROVIDER_COMMAND_FAILED")
    return len(pieces[-1])


def _process_group_exists(group_id: int) -> bool:
    try:
        os.killpg(group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_process_group(group_id: int, requested_signal: int) -> bool:
    try:
        os.killpg(group_id, requested_signal)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return True


def _wait_for_process_group_exit(group_id: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while _process_group_exists(group_id) and time.monotonic() < deadline:
        time.sleep(0.01)
    return not _process_group_exists(group_id)


def _cleanup_owned_process(proc: subprocess.Popen[bytes], group_id: int) -> bool:
    cleanup_ok = True
    if _process_group_exists(group_id):
        cleanup_ok = _signal_process_group(group_id, signal.SIGTERM)
    try:
        proc.wait(timeout=_PROCESS_TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        # An owned child may ignore TERM; reaching the KILL phase is expected.
        pass
    except OSError:
        cleanup_ok = False

    group_gone = _wait_for_process_group_exit(
        group_id, _PROCESS_TERMINATE_GRACE_SECONDS
    )
    if not group_gone:
        cleanup_ok = _signal_process_group(group_id, signal.SIGKILL) and cleanup_ok
        try:
            proc.wait(timeout=_PROCESS_TERMINATE_GRACE_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            cleanup_ok = False
        group_gone = _wait_for_process_group_exit(
            group_id, _PROCESS_TERMINATE_GRACE_SECONDS
        )
    if proc.returncode is None:
        try:
            proc.kill()
            proc.wait(timeout=_PROCESS_TERMINATE_GRACE_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            cleanup_ok = False
    return cleanup_ok and group_gone and proc.returncode is not None


def _collect_bounded_output(
    proc: subprocess.Popen[bytes],
    *,
    timeout_seconds: float,
) -> tuple[bytes, int]:
    if proc.stdout is None or proc.stderr is None:
        _raise("PROVIDER_COMMAND_FAILED")
    selector = selectors.DefaultSelector()
    streams = {"stdout": proc.stdout, "stderr": proc.stderr}
    sizes = {"stdout": 0, "stderr": 0}
    line_lengths = {"stdout": 0, "stderr": 0}
    stdout = bytearray()
    started = time.monotonic()
    absolute_deadline = started + timeout_seconds
    idle_deadline = started + min(timeout_seconds, _PROVIDER_IDLE_TIMEOUT_SECONDS)
    try:
        for name, stream in streams.items():
            descriptor = stream.fileno()
            os.set_blocking(descriptor, False)
            selector.register(descriptor, selectors.EVENT_READ, name)

        while selector.get_map():
            now = time.monotonic()
            wait_seconds = min(absolute_deadline, idle_deadline) - now
            if wait_seconds <= 0:
                _raise("PROVIDER_TIMEOUT")
            try:
                ready = selector.select(wait_seconds)
            except OSError:
                _raise("PROVIDER_COMMAND_FAILED")
            if not ready:
                _raise("PROVIDER_TIMEOUT")

            made_progress = False
            for key, _ in ready:
                name = str(key.data)
                limit = MAX_STDOUT_BYTES if name == "stdout" else MAX_STDERR_BYTES
                remaining = max(0, limit - sizes[name])
                try:
                    chunk = os.read(key.fd, min(_READ_CHUNK_BYTES, remaining + 1))
                except BlockingIOError:
                    continue
                except OSError:
                    _raise("PROVIDER_COMMAND_FAILED")
                if not chunk:
                    try:
                        selector.unregister(key.fd)
                    except (KeyError, ValueError):
                        pass
                    streams[name].close()
                    continue

                made_progress = True
                sizes[name] += len(chunk)
                if sizes[name] > limit or sum(sizes.values()) > (
                    MAX_STDOUT_BYTES + MAX_STDERR_BYTES
                ):
                    _raise("PROVIDER_COMMAND_FAILED")
                line_lengths[name] = _line_length_after(line_lengths[name], chunk)
                if name == "stdout":
                    stdout.extend(chunk)
            if made_progress:
                idle_deadline = time.monotonic() + min(
                    timeout_seconds, _PROVIDER_IDLE_TIMEOUT_SECONDS
                )

        remaining = min(absolute_deadline, idle_deadline) - time.monotonic()
        if remaining <= 0:
            _raise("PROVIDER_TIMEOUT")
        try:
            return bytes(stdout), int(proc.wait(timeout=remaining))
        except subprocess.TimeoutExpired:
            _raise("PROVIDER_TIMEOUT")
        except OSError:
            _raise("PROVIDER_COMMAND_FAILED")
    finally:
        try:
            selector.close()
        finally:
            for stream in streams.values():
                try:
                    stream.close()
                except OSError:
                    pass


def _run(
    argv: tuple[str, ...],
    *,
    accepted_returncodes: frozenset[int] = frozenset({0}),
    timeout_seconds: float = _PROVIDER_TIMEOUT_SECONDS,
    pass_fds: tuple[int, ...] = (),
    launch_guard: _RetainedExecutable | None = None,
) -> CommandObservation:
    if (
        os.name != "posix"
        or type(timeout_seconds) not in {int, float}
        or timeout_seconds <= 0
        or not argv
        or any(not isinstance(item, str) or not item for item in argv)
        or any(type(descriptor) is not int or descriptor < 0 for descriptor in pass_fds)
        or (launch_guard is not None and not isinstance(launch_guard, _RetainedExecutable))
    ):
        _raise("PROVIDER_COMMAND_FAILED")
    environment = _closed_child_environment()
    if launch_guard is not None:
        _assert_retained_binary(launch_guard, verify_source_digest=False)
        if argv[0] != launch_guard.execution_path:
            _raise("PROVIDER_COMMAND_FAILED")
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            bufsize=0,
            close_fds=True,
            pass_fds=pass_fds,
            start_new_session=True,
            env=environment,
        )
    except (OSError, ValueError, TypeError):
        _raise("PROVIDER_COMMAND_FAILED")

    failure: PreflightError | None = None
    observation: CommandObservation | None = None
    try:
        stdout, returncode = _collect_bounded_output(
            proc, timeout_seconds=float(timeout_seconds)
        )
        if returncode not in accepted_returncodes:
            _raise("PROVIDER_COMMAND_FAILED")
        observation = CommandObservation(returncode=returncode, stdout=stdout)
    except PreflightError as exc:
        failure = exc
    except BaseException:
        failure = PreflightError("PROVIDER_COMMAND_FAILED")

    cleanup_ok = _cleanup_owned_process(proc, proc.pid)
    if not cleanup_ok:
        _raise("PROVIDER_COMMAND_FAILED")
    if failure is not None:
        raise failure from None
    if observation is None:
        _raise("PROVIDER_COMMAND_FAILED")
    return observation


def _sha256_bounded(path: Path) -> str:
    with _retain_binary(path) as retained:
        return retained.sha256


def _retained_executable(
    binary: Path | _RetainedExecutable,
) -> tuple[_RetainedExecutable, bool]:
    if isinstance(binary, _RetainedExecutable):
        return binary, False
    return _retain_binary(binary), True


def observe_binary(
    binary: Path | _RetainedExecutable,
) -> tuple[str, str]:
    retained, owned = _retained_executable(binary)
    try:
        _assert_retained_binary(retained)
        observed = _run(
            build_allowed_argv(retained, "version"),
            launch_guard=retained,
        )
        _assert_retained_binary(retained)
        version = _normalize_claude_version(observed.stdout)
        return retained.sha256, version
    finally:
        if owned:
            retained.close()


class _DuplicateJsonKey(ValueError):
    pass


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    del value
    raise ValueError


def _parse_auth_status(raw: bytes | str) -> dict[str, Any]:
    try:
        encoded = raw if isinstance(raw, bytes) else raw.encode("utf-8", "strict")
    except (AttributeError, UnicodeError):
        _raise("AUTH_STATUS_UNSUPPORTED")
    if not encoded or len(encoded) > MAX_AUTH_JSON_BYTES:
        _raise("AUTH_STATUS_UNSUPPORTED")
    try:
        text = encoded.decode("utf-8", "strict")
        parsed = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except (MemoryError, RecursionError, TypeError, UnicodeError, ValueError):
        _raise("AUTH_STATUS_UNSUPPORTED")
    if not isinstance(parsed, dict):
        _raise("AUTH_STATUS_UNSUPPORTED")
    if not set(parsed).issubset(_RAW_AUTH_ALLOWED_KEYS):
        _raise("AUTH_STATUS_UNSUPPORTED")
    for key, value in parsed.items():
        if key == "loggedIn":
            if type(value) is not bool:
                _raise("AUTH_STATUS_UNSUPPORTED")
            continue
        if value is not None and not isinstance(value, str):
            _raise("AUTH_STATUS_UNSUPPORTED")
        if isinstance(value, str):
            try:
                encoded_length = len(value.encode("utf-8", "strict"))
            except UnicodeError:
                _raise("AUTH_STATUS_UNSUPPORTED")
            if (
                encoded_length > MAX_AUTH_STRING_BYTES
                or _CONTROL_RE.search(value)
                or _SECRET_RE.search(value)
            ):
                _raise("AUTH_STATUS_UNSUPPORTED")
        if key == "apiKeySource" and value not in {None, "/login managed key"}:
            _raise("AUTH_STATUS_UNSUPPORTED")
    return parsed


def observe_auth(binary: Path | _RetainedExecutable) -> AuthObservation:
    retained, owned = _retained_executable(binary)
    try:
        _assert_retained_binary(retained)
        observed = _run(
            build_allowed_argv(retained, "auth_status"),
            accepted_returncodes=frozenset({0, 1}),
            launch_guard=retained,
        )
        _assert_retained_binary(retained)
        parsed = _parse_auth_status(observed.stdout)
    finally:
        if owned:
            retained.close()

    # Current first-party Claude Code contract: auth status exits 0 when logged
    # in and 1 when logged out, while still emitting the JSON status document.
    logged_in = parsed.get("loggedIn")
    if type(logged_in) is not bool:
        _raise("AUTH_STATUS_UNSUPPORTED")
    if (observed.returncode == 0) is not logged_in:
        _raise("AUTH_STATUS_UNSUPPORTED")
    return normalize_auth_status(parsed)


def build_ready_receipt(
    *,
    realm_label: str,
    host_ref: str,
    os_principal_ref: str,
    execution_context: str,
    binary_sha256: str,
    version: str,
    auth: AuthObservation,
    worker_id: str | None = None,
    quota_class: str | None = None,
    isolation_basis: str = "OS_PRINCIPAL_KEYCHAIN",
    observed_at: str | None = None,
) -> dict[str, Any]:
    if execution_context != "INTERACTIVE_PRINCIPAL":
        # Task 3 owns the real Worker-broker composition. This Task 1/2 slice
        # cannot turn a caller declaration into worker-context evidence.
        _raise("EXECUTION_CONTEXT_UNPROVEN")
    require_current_identity_owner(host_ref, os_principal_ref)
    if not auth.auth_ready:
        _raise(auth.reason_codes[0] if auth.reason_codes else "AUTH_STATUS_UNSUPPORTED")
    return validate_receipt(
        {
            "schema": SCHEMA,
            "realm_label": realm_label,
            "host_ref": host_ref,
            "os_principal_ref": os_principal_ref,
            "observed_at": observed_at or now_iso(),
            "claude_binary_sha256": binary_sha256,
            "claude_version": version,
            "auth_ready": True,
            "auth_method": auth.auth_method,
            "api_provider": auth.api_provider,
            "auth_identity_confidence": "SLOT_ONLY",
            "macos_credential_isolation_basis": isolation_basis,
            "execution_context": execution_context,
            "worker_id": worker_id,
            "quota_class": quota_class,
            "verdict": "INTERACTIVE_AUTH_READY",
            "reason_codes": [],
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provider-work-free Claude Worker preflight")
    parser.add_argument("--realm-label", required=True)
    parser.add_argument("--host-ref", required=True)
    parser.add_argument("--os-principal-ref", required=True)
    parser.add_argument(
        "--execution-context",
        required=True,
        choices=sorted(EXECUTION_CONTEXTS),
    )
    parser.add_argument("--worker-id")
    parser.add_argument("--quota-class")
    parser.add_argument("--claude-binary", required=True, type=Path)
    args = parser.parse_args(argv)

    # The ordinary CLI is not the Worker broker. Preserve the closed future
    # wire, but do not allow this slice to mint Worker-context evidence.
    if args.execution_context == "WORKER_BROKER":
        _raise("EXECUTION_CONTEXT_UNPROVEN")

    # Validate caller wire shape, then require actual existing-owner proof.
    # Current protected estate has no concrete host owner exposed to this CLI,
    # so this fails closed before any provider metadata command is started.
    require_current_identity_owner(args.host_ref, args.os_principal_ref)

    # Unreachable under the current Task-2 estate. Kept as the bounded positive
    # composition that a future accepted identity owner may invoke without
    # introducing a second preflight family.
    with _retain_binary(args.claude_binary) as retained:
        digest, version = observe_binary(retained)
        auth = observe_auth(retained)
        receipt = build_ready_receipt(
            realm_label=args.realm_label,
            host_ref=args.host_ref,
            os_principal_ref=args.os_principal_ref,
            execution_context=args.execution_context,
            worker_id=args.worker_id,
            quota_class=args.quota_class,
            binary_sha256=digest,
            version=version,
            auth=auth,
        )
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PreflightError as exc:
        # Stable low-cardinality refusal only. Never echo provider stdout/stderr
        # or advertise the closed receipt schema on a non-receipt object.
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        raise SystemExit(2) from None
