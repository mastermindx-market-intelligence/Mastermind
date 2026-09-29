"""Durable, source-only state journal for Executive release transitions.

The journal records actuator progress.  It has no installer, child-process,
network, credential, or service-control surface.  Host effects remain owned by
the privileged broker that composes this journal later.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import errno
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import threading
import time
from typing import Any

from control_plane.ceo_request import CeoRequestError, app_request_ref
from control_plane.executive_release_contract import (
    ReleaseContractError,
    ReleaseRecord,
    canonical_release_bytes,
    parse_release_json,
    validate_admission,
    validate_precondition_manifest,
)
from control_plane.fs_security import FilesystemSecurityError, has_macos_acl


JOURNAL_PRODUCTION_ROOT = "/var/db/mastermind-executive/release-actuator/journal"

_SCHEMA = "mastermind.executive_release_actuator_journal/v1"
_STATES = (
    "STARTED",
    "PUBLISHED",
    "BROKER_RESTART_PENDING",
    "RECOVERING",
    "SUCCEEDED",
    "ROLLED_BACK",
    "FAILED_NOT_APPLIED",
)
_TERMINAL_STATES = frozenset(_STATES[4:])
_NEXT_STATE = {
    "STARTED": frozenset({"PUBLISHED"}),
    "PUBLISHED": frozenset({"BROKER_RESTART_PENDING"}),
    "BROKER_RESTART_PENDING": frozenset({"RECOVERING"}),
    "RECOVERING": _TERMINAL_STATES,
}
_IDENTITY_FIELDS = frozenset(
    {
        "operation_key",
        "request_fingerprint",
        "approval_evidence_digest",
        "normalized_requested_effect_digest",
        "expected_source_and_precondition_digest",
        "action_target_digest",
        "owner_installation_id",
        "target_ref",
        "before_release_commit",
        "before_release_tree",
        "before_installed_manifest_digest",
        "before_configuration_digest",
        "target_release_commit",
        "target_release_tree",
        "boot_id",
    }
)
_RECORD_FIELDS = frozenset(
    {
        "schema",
        "state",
        *_IDENTITY_FIELDS,
        "preconditions",
        "admission",
        "actuator_generation",
        "journal_generation",
        "started_at_ms",
    }
)
_TERMINAL_FIELDS = frozenset(
    {"completed_at_ms", "postcondition_digest", "after", "rollback"}
)
_INSTALLED_IDENTITY_FIELDS = frozenset(
    {
        "release_commit",
        "release_tree",
        "installed_manifest_digest",
        "configuration_digest",
    }
)
_HEX64 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_HEX40 = re.compile(r"[0-9a-f]{40}", re.ASCII)
_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}"
    r"-[0-9a-f]{12}",
    re.ASCII,
)
_MAX_INT = (1 << 63) - 1
_MAX_RECORD_BYTES = 16 * 1024
_ROOT_MODE = 0o700
_FILE_MODE = 0o600
_LOCK_TIMEOUT_SECONDS = 5.0
_LOCK_POLL_SECONDS = 0.01
_OPEN_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_OPEN_RECORD = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_LOCAL_LOCK = threading.Lock()


class ExecutiveReleaseActuatorJournalError(RuntimeError):
    """A bounded journal refusal with no rejected value in its text."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise ExecutiveReleaseActuatorJournalError(code)


def _exact_mapping(value: Any, fields: frozenset[str], code: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != fields:
        _fail(code)
    return {field: value[field] for field in fields}


def _text(value: Any, pattern: re.Pattern[str], code: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail(code)
    return value


def _digest(value: Any, code: str) -> str:
    return _text(value, _HEX64, code)


def _commit(value: Any, code: str) -> str:
    return _text(value, _HEX40, code)


def _uuid(value: Any, code: str) -> str:
    return _text(value, _UUID, code)


def _integer(value: Any, code: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= _MAX_INT:
        _fail(code)
    return value


def _operation_key(value: Any) -> str:
    if type(value) is not str:
        _fail("INVALID_OPERATION_KEY")
    try:
        app_request_ref(value)
    except CeoRequestError:
        _fail("INVALID_OPERATION_KEY")
    return value


def _hash_record(value: Any) -> str:
    try:
        raw = canonical_release_bytes(value)
    except ReleaseContractError:
        _fail("INVALID_RECORD")
    return hashlib.sha256(raw).hexdigest()


def _before_identity(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "release_commit": record["before_release_commit"],
        "release_tree": record["before_release_tree"],
        "installed_manifest_digest": record["before_installed_manifest_digest"],
        "configuration_digest": record["before_configuration_digest"],
    }


def _validate_installed_identity(value: Any, code: str) -> dict[str, Any]:
    identity = _exact_mapping(value, _INSTALLED_IDENTITY_FIELDS, code)
    _commit(identity["release_commit"], code)
    _commit(identity["release_tree"], code)
    _digest(identity["installed_manifest_digest"], code)
    _digest(identity["configuration_digest"], code)
    return identity


def _validate_terminal(terminal: Any, record: Mapping[str, Any]) -> dict[str, Any]:
    value = _exact_mapping(terminal, _TERMINAL_FIELDS, "INVALID_TERMINAL")
    completed_at_ms = _integer(
        value["completed_at_ms"], "INVALID_COMPLETED_AT_MS"
    )
    if completed_at_ms < record["started_at_ms"]:
        _fail("INVALID_COMPLETED_AT_MS")
    _digest(value["postcondition_digest"], "INVALID_POSTCONDITION_DIGEST")
    after = _validate_installed_identity(value["after"], "INVALID_AFTER")
    rollback = value["rollback"]
    if not isinstance(rollback, Mapping) or frozenset(rollback) not in (
        frozenset({"attempted"}),
        frozenset({"attempted", "restored_preimage_digest"}),
    ):
        _fail("INVALID_ROLLBACK")
    attempted = rollback["attempted"]
    if type(attempted) is not bool:
        _fail("INVALID_ROLLBACK")
    if attempted:
        if frozenset(rollback) != frozenset(
            {"attempted", "restored_preimage_digest"}
        ):
            _fail("INVALID_ROLLBACK")
        _digest(rollback["restored_preimage_digest"], "INVALID_ROLLBACK")
    elif frozenset(rollback) != frozenset({"attempted"}):
        _fail("INVALID_ROLLBACK")

    before = _before_identity(record)
    state = record["state"]
    if state == "SUCCEEDED":
        if (
            after["release_commit"] != record["target_release_commit"]
            or after["release_tree"] != record["target_release_tree"]
            or attempted
        ):
            _fail("INVALID_TERMINAL_TRUTH")
    elif state == "FAILED_NOT_APPLIED":
        if after != before or attempted:
            _fail("INVALID_TERMINAL_TRUTH")
    elif state == "ROLLED_BACK":
        restored = _hash_record(before)
        if (
            after != before
            or not attempted
            or rollback["restored_preimage_digest"] != restored
        ):
            _fail("INVALID_TERMINAL_TRUTH")
    else:
        _fail("INVALID_TERMINAL")
    return {
        "completed_at_ms": completed_at_ms,
        "postcondition_digest": value["postcondition_digest"],
        "after": after,
        "rollback": dict(rollback),
    }


def _validate_record(value: Any) -> ReleaseRecord:
    if not isinstance(value, Mapping):
        _fail("INVALID_RECORD")
    state = value.get("state")
    expected = _RECORD_FIELDS | ({"terminal"} if state in _TERMINAL_STATES else set())
    record = _exact_mapping(value, frozenset(expected), "INVALID_RECORD_FIELDS")
    if record["schema"] != _SCHEMA or state not in _STATES:
        _fail("INVALID_RECORD")

    _operation_key(record["operation_key"])
    for field in (
        "request_fingerprint",
        "approval_evidence_digest",
        "normalized_requested_effect_digest",
        "expected_source_and_precondition_digest",
        "action_target_digest",
        "target_ref",
        "before_installed_manifest_digest",
        "before_configuration_digest",
    ):
        _digest(record[field], "INVALID_IDENTITY")
    for field in (
        "before_release_commit",
        "before_release_tree",
        "target_release_commit",
        "target_release_tree",
    ):
        _commit(record[field], "INVALID_IDENTITY")
    _uuid(record["owner_installation_id"], "INVALID_IDENTITY")
    _uuid(record["boot_id"], "INVALID_IDENTITY")
    _integer(record["actuator_generation"], "INVALID_GENERATION", minimum=1)
    _integer(record["journal_generation"], "INVALID_GENERATION", minimum=1)
    _integer(record["started_at_ms"], "INVALID_STARTED_AT_MS")

    try:
        preconditions = validate_precondition_manifest(record["preconditions"])
        admission = validate_admission(record["admission"])
    except ReleaseContractError:
        _fail("INVALID_EMBEDDED_RECORD")
    required_preconditions = {
        "owner_installation_id": record["owner_installation_id"],
        "target_ref": record["target_ref"],
        "boot_id": record["boot_id"],
        "approval_evidence_digest": record["approval_evidence_digest"],
    }
    required_admission = {
        "operation_key": record["operation_key"],
        "target_ref": record["target_ref"],
        "owner_installation_id": record["owner_installation_id"],
        "boot_id": record["boot_id"],
        "request_fingerprint": record["request_fingerprint"],
        "effective_grant_digest": preconditions["grant_digest"],
        "admission_contract_digest": preconditions["admission_contract_digest"],
    }
    if any(preconditions[key] != expected for key, expected in required_preconditions.items()):
        _fail("INVALID_JOIN")
    if any(admission[key] != expected for key, expected in required_admission.items()):
        _fail("INVALID_JOIN")
    if (
        record["before_installed_manifest_digest"]
        != preconditions["from_installed_manifest_digest"]
        or record["before_configuration_digest"]
        != preconditions["installed_configuration_digest"]
    ):
        _fail("INVALID_JOIN")
    if record["expected_source_and_precondition_digest"] != _hash_record(preconditions):
        _fail("INVALID_JOIN")

    detached = dict(record)
    detached["preconditions"] = preconditions.to_dict()
    detached["admission"] = admission.to_dict()
    if state in _TERMINAL_STATES:
        detached["terminal"] = _validate_terminal(record["terminal"], detached)
    try:
        raw = canonical_release_bytes(detached)
        if len(raw) > _MAX_RECORD_BYTES:
            _fail("RECORD_SIZE")
        return parse_release_json(raw)
    except ReleaseContractError:
        _fail("INVALID_RECORD")


def _file_identity(info: os.stat_result) -> tuple[Any, ...]:
    return (
        info.st_dev,
        info.st_ino,
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _directory_identity(info: os.stat_result) -> tuple[Any, ...]:
    return (
        info.st_dev,
        info.st_ino,
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        info.st_uid,
        info.st_gid,
    )


class _ExecutiveReleaseActuatorJournal:
    def __init__(self) -> None:
        self._root = Path(JOURNAL_PRODUCTION_ROOT)
        self._expected_uid = 0
        self._lock_timeout = _LOCK_TIMEOUT_SECONDS

    @classmethod
    def _for_tests(
        cls,
        root: Path | str,
        *,
        expected_uid: int | None = None,
        lock_timeout: float = 1.0,
    ) -> "_ExecutiveReleaseActuatorJournal":
        if type(lock_timeout) not in (int, float) or lock_timeout <= 0:
            _fail("INVALID_LOCK_TIMEOUT")
        journal = cls.__new__(cls)
        journal._root = Path(root)
        journal._expected_uid = os.geteuid() if expected_uid is None else expected_uid
        journal._lock_timeout = float(lock_timeout)
        return journal

    @staticmethod
    def _name(operation_key: str) -> str:
        value = _operation_key(operation_key)
        return hashlib.sha256(value.encode("ascii")).hexdigest() + ".json"

    def _check_descriptor(
        self,
        descriptor: int,
        info: os.stat_result,
        *,
        directory: bool,
        mode: int,
        code: str,
    ) -> None:
        expected_type = stat.S_IFDIR if directory else stat.S_IFREG
        if (
            stat.S_IFMT(info.st_mode) != expected_type
            or stat.S_IMODE(info.st_mode) != mode
            or info.st_uid != self._expected_uid
            or (not directory and info.st_nlink != 1)
        ):
            _fail(code)
        try:
            if has_macos_acl("", expected_identity=info, descriptor=descriptor):
                _fail(code)
        except FilesystemSecurityError:
            _fail(code)

    def _open_root(self, *, create: bool) -> tuple[int, tuple[Any, ...]]:
        try:
            before = os.stat(self._root, follow_symlinks=False)
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                _fail("ROOT_OPEN")
            before = None
        try:
            descriptor = os.open(self._root, _OPEN_DIRECTORY)
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                _fail("ROOT_OPEN")
            if not create:
                _fail("NOT_FOUND")
            self._create_root()
            try:
                before = os.stat(self._root, follow_symlinks=False)
                descriptor = os.open(self._root, _OPEN_DIRECTORY)
            except OSError:
                _fail("ROOT_OPEN")
        info = os.fstat(descriptor)
        try:
            if before is None or _directory_identity(before) != _directory_identity(info):
                _fail("ROOT_REPLACED")
            self._check_descriptor(
                descriptor,
                info,
                directory=True,
                mode=_ROOT_MODE,
                code="ROOT_METADATA",
            )
        except BaseException:
            os.close(descriptor)
            raise
        return descriptor, _directory_identity(info)

    def _assert_root_path(
        self, descriptor: int, expected_identity: tuple[Any, ...]
    ) -> None:
        try:
            path_info = os.stat(self._root, follow_symlinks=False)
            descriptor_info = os.fstat(descriptor)
        except OSError:
            _fail("ROOT_REPLACED")
        if (
            _directory_identity(path_info) != expected_identity
            or _directory_identity(descriptor_info) != expected_identity
        ):
            _fail("ROOT_REPLACED")

    def _create_root(self) -> None:
        parent_descriptor = None
        try:
            parent_descriptor = os.open(self._root.parent, _OPEN_DIRECTORY)
            parent_info = os.fstat(parent_descriptor)
            if (
                not stat.S_ISDIR(parent_info.st_mode)
                or parent_info.st_uid != self._expected_uid
                or stat.S_IMODE(parent_info.st_mode) & 0o022
            ):
                _fail("ROOT_PARENT_METADATA")
            try:
                if has_macos_acl(
                    "", expected_identity=parent_info, descriptor=parent_descriptor
                ):
                    _fail("ROOT_PARENT_METADATA")
            except FilesystemSecurityError:
                _fail("ROOT_PARENT_METADATA")
            try:
                os.mkdir(self._root.name, _ROOT_MODE, dir_fd=parent_descriptor)
            except FileExistsError:
                pass
            os.fsync(parent_descriptor)
        except ExecutiveReleaseActuatorJournalError:
            raise
        except OSError:
            _fail("ROOT_CREATE")
        finally:
            if parent_descriptor is not None:
                os.close(parent_descriptor)

    @staticmethod
    def _fsync_directory(descriptor: int) -> None:
        try:
            os.fsync(descriptor)
        except OSError:
            _fail("ROOT_FSYNC")

    def _open_lock(
        self, root_descriptor: int, lock_name: str
    ) -> tuple[int, tuple[Any, ...]]:
        created = False
        try:
            descriptor = os.open(
                lock_name,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                _FILE_MODE,
                dir_fd=root_descriptor,
            )
            created = True
        except FileExistsError:
            try:
                descriptor = os.open(
                    lock_name,
                    os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=root_descriptor,
                )
            except OSError:
                _fail("LOCK_OPEN")
        except OSError:
            _fail("LOCK_OPEN")
        try:
            if created:
                os.fchmod(descriptor, _FILE_MODE)
                os.fsync(descriptor)
                self._fsync_directory(root_descriptor)
            info = os.fstat(descriptor)
            self._check_descriptor(
                descriptor,
                info,
                directory=False,
                mode=_FILE_MODE,
                code="LOCK_METADATA",
            )
            if info.st_size != 0:
                _fail("LOCK_METADATA")
            return descriptor, _file_identity(info)
        except BaseException:
            os.close(descriptor)
            raise

    @staticmethod
    def _assert_file_path(
        root_descriptor: int,
        name: str,
        descriptor: int,
        expected_identity: tuple[Any, ...],
        code: str,
    ) -> None:
        try:
            path_info = os.stat(
                name, dir_fd=root_descriptor, follow_symlinks=False
            )
            descriptor_info = os.fstat(descriptor)
        except OSError:
            _fail(code)
        if (
            _file_identity(path_info) != expected_identity
            or _file_identity(descriptor_info) != expected_identity
        ):
            _fail(code)

    def _acquire_flock(self, descriptor: int, deadline: float) -> None:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    _fail("LOCK_TIMEOUT")
                time.sleep(_LOCK_POLL_SECONDS)
            except OSError:
                _fail("LOCK_ACQUIRE")

    def _locked(
        self,
        name: str,
        operation: Callable[[int, str], ReleaseRecord],
        *,
        create_root: bool,
    ) -> ReleaseRecord:
        deadline = time.monotonic() + self._lock_timeout
        remaining = max(0.0, deadline - time.monotonic())
        if not _LOCAL_LOCK.acquire(timeout=remaining):
            _fail("LOCK_TIMEOUT")
        root_descriptor = None
        lock_descriptor = None
        try:
            root_descriptor, root_identity = self._open_root(create=create_root)
            lock_name = name[:-5] + ".lock"
            lock_descriptor, lock_identity = self._open_lock(
                root_descriptor, lock_name
            )
            self._acquire_flock(lock_descriptor, deadline)
            self._assert_root_path(root_descriptor, root_identity)
            self._assert_file_path(
                root_descriptor,
                lock_name,
                lock_descriptor,
                lock_identity,
                "LOCK_REPLACED",
            )
            result = operation(root_descriptor, name)
            self._assert_file_path(
                root_descriptor,
                lock_name,
                lock_descriptor,
                lock_identity,
                "LOCK_REPLACED",
            )
            self._assert_root_path(root_descriptor, root_identity)
            return result
        finally:
            if lock_descriptor is not None:
                try:
                    fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
                except OSError:
                    pass
                os.close(lock_descriptor)
            if root_descriptor is not None:
                os.close(root_descriptor)
            _LOCAL_LOCK.release()

    def _read_file(
        self, root_descriptor: int, name: str, *, required: bool
    ) -> tuple[bytes, tuple[Any, ...]]:
        try:
            before = os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            if required:
                _fail("NOT_FOUND")
            return b"", ()
        except OSError:
            _fail("RECORD_OPEN")
        if not stat.S_ISREG(before.st_mode):
            _fail("RECORD_METADATA")
        try:
            descriptor = os.open(name, _OPEN_RECORD, dir_fd=root_descriptor)
        except OSError:
            _fail("RECORD_OPEN")
        try:
            opened = os.fstat(descriptor)
            identity = _file_identity(opened)
            if _file_identity(before) != identity:
                _fail("RECORD_REPLACED")
            self._check_descriptor(
                descriptor,
                opened,
                directory=False,
                mode=_FILE_MODE,
                code="RECORD_METADATA",
            )
            if opened.st_size > _MAX_RECORD_BYTES:
                _fail("RECORD_SIZE")
            chunks: list[bytes] = []
            size = 0
            while size <= _MAX_RECORD_BYTES:
                chunk = os.read(descriptor, _MAX_RECORD_BYTES + 1 - size)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            raw = b"".join(chunks)
            try:
                path_after = os.stat(
                    name, dir_fd=root_descriptor, follow_symlinks=False
                )
            except OSError:
                _fail("RECORD_REPLACED")
            if size > _MAX_RECORD_BYTES:
                _fail("RECORD_SIZE")
            if (
                _file_identity(os.fstat(descriptor)) != identity
                or _file_identity(path_after) != identity
            ):
                _fail("RECORD_REPLACED")
            return raw, identity
        except ExecutiveReleaseActuatorJournalError:
            raise
        except OSError:
            _fail("RECORD_READ")
        finally:
            os.close(descriptor)

    @staticmethod
    def _decode(raw: bytes) -> ReleaseRecord:
        try:
            parsed = parse_release_json(raw)
        except ReleaseContractError:
            _fail("RECORD_BYTES")
        try:
            validated = _validate_record(parsed)
            if canonical_release_bytes(validated) != raw:
                _fail("RECORD_BYTES")
            return validated
        except (ReleaseContractError, ExecutiveReleaseActuatorJournalError):
            _fail("RECORD_BYTES")

    def _write_new(self, root_descriptor: int, name: str, raw: bytes) -> None:
        if not 0 < len(raw) <= _MAX_RECORD_BYTES:
            _fail("RECORD_SIZE")
        descriptor = None
        created = False
        try:
            descriptor = os.open(
                name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | os.O_NOFOLLOW
                | os.O_CLOEXEC,
                _FILE_MODE,
                dir_fd=root_descriptor,
            )
            created = True
            os.fchmod(descriptor, _FILE_MODE)
            info = os.fstat(descriptor)
            self._check_descriptor(
                descriptor,
                info,
                directory=False,
                mode=_FILE_MODE,
                code="RECORD_METADATA",
            )
            view = memoryview(raw)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    _fail("RECORD_WRITE")
                view = view[written:]
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            self._fsync_directory(root_descriptor)
        except FileExistsError:
            _fail("RECORD_EXISTS")
        except ExecutiveReleaseActuatorJournalError:
            raise
        except OSError:
            _fail("RECORD_WRITE")
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if created:
                try:
                    observed = os.stat(
                        name, dir_fd=root_descriptor, follow_symlinks=False
                    )
                except OSError:
                    observed = None
                if observed is not None and observed.st_size != len(raw):
                    try:
                        os.unlink(name, dir_fd=root_descriptor)
                        self._fsync_directory(root_descriptor)
                    except OSError:
                        pass

    def create(
        self,
        *,
        actuator_generation: int,
        identity: Mapping[str, Any],
        preconditions: Mapping[str, Any],
        admission: Mapping[str, Any],
        started_at_ms: int,
    ) -> ReleaseRecord:
        supplied = _exact_mapping(identity, _IDENTITY_FIELDS, "INVALID_IDENTITY")
        candidate = {
            "schema": _SCHEMA,
            "state": "STARTED",
            **supplied,
            "preconditions": preconditions,
            "admission": admission,
            "actuator_generation": actuator_generation,
            "journal_generation": 1,
            "started_at_ms": started_at_ms,
        }
        validated = _validate_record(candidate)
        raw = canonical_release_bytes(validated)
        name = self._name(validated["operation_key"])
        return self._locked(
            name,
            lambda root, record_name: self._create_locked(
                root, record_name, raw
            ),
            create_root=True,
        )

    def _create_locked(
        self, root_descriptor: int, name: str, candidate: bytes
    ) -> ReleaseRecord:
        current, _ = self._read_file(root_descriptor, name, required=False)
        if current:
            existing = self._decode(current)
            if current == candidate:
                return existing
            _fail("CONFLICT")
        self._write_new(root_descriptor, name, candidate)
        written, _ = self._read_file(root_descriptor, name, required=True)
        if written != candidate:
            _fail("RECORD_REPLACED")
        return self._decode(written)

    def read(self, operation_key: str) -> ReleaseRecord:
        name = self._name(operation_key)
        return self._locked(
            name,
            lambda root, record_name: self._decode(
                self._read_file(root, record_name, required=True)[0]
            ),
            create_root=False,
        )

    def advance(
        self,
        operation_key: str,
        *,
        expected_generation: int,
        state: str,
        completed_at_ms: int | None = None,
        postcondition_digest: str | None = None,
        after: Mapping[str, Any] | None = None,
        rollback: Mapping[str, Any] | None = None,
    ) -> ReleaseRecord:
        _integer(expected_generation, "INVALID_EXPECTED_GENERATION", minimum=1)
        if type(state) is not str or state not in _STATES:
            _fail("INVALID_STATE")
        terminal_arguments = (
            completed_at_ms,
            postcondition_digest,
            after,
            rollback,
        )
        if state in _TERMINAL_STATES:
            if any(value is None for value in terminal_arguments):
                _fail("TERMINAL_ARGUMENTS")
        elif any(value is not None for value in terminal_arguments):
            _fail("TERMINAL_ARGUMENTS")
        name = self._name(operation_key)
        return self._locked(
            name,
            lambda root, record_name: self._advance_locked(
                root,
                record_name,
                expected_generation=expected_generation,
                state=state,
                completed_at_ms=completed_at_ms,
                postcondition_digest=postcondition_digest,
                after=after,
                rollback=rollback,
            ),
            create_root=False,
        )

    def _advance_locked(
        self,
        root_descriptor: int,
        name: str,
        *,
        expected_generation: int,
        state: str,
        completed_at_ms: int | None,
        postcondition_digest: str | None,
        after: Mapping[str, Any] | None,
        rollback: Mapping[str, Any] | None,
    ) -> ReleaseRecord:
        current_raw, current_identity = self._read_file(
            root_descriptor, name, required=True
        )
        current = self._decode(current_raw)
        if current["state"] in _TERMINAL_STATES:
            _fail("TERMINAL_IMMUTABLE")
        if current["journal_generation"] != expected_generation:
            _fail("GENERATION_MISMATCH")
        if state not in _NEXT_STATE[current["state"]]:
            _fail("INVALID_TRANSITION")
        if current["journal_generation"] == _MAX_INT:
            _fail("GENERATION_EXHAUSTED")

        updated = current.to_dict()
        updated["state"] = state
        updated["journal_generation"] += 1
        if state in _TERMINAL_STATES:
            updated["terminal"] = {
                "completed_at_ms": completed_at_ms,
                "postcondition_digest": postcondition_digest,
                "after": after,
                "rollback": rollback,
            }
        validated = _validate_record(updated)
        replacement = canonical_release_bytes(validated)
        temporary_name = name[:-5] + ".tmp"
        self._write_new(root_descriptor, temporary_name, replacement)
        try:
            temporary_raw, temporary_identity = self._read_file(
                root_descriptor, temporary_name, required=True
            )
            if temporary_raw != replacement:
                _fail("RECORD_REPLACED")
            observed_raw, observed_identity = self._read_file(
                root_descriptor, name, required=True
            )
            if observed_raw != current_raw or observed_identity != current_identity:
                _fail("RECORD_REPLACED")
            temporary_again, temporary_identity_again = self._read_file(
                root_descriptor, temporary_name, required=True
            )
            if (
                temporary_again != replacement
                or temporary_identity_again != temporary_identity
            ):
                _fail("RECORD_REPLACED")
            try:
                os.replace(
                    temporary_name,
                    name,
                    src_dir_fd=root_descriptor,
                    dst_dir_fd=root_descriptor,
                )
            except OSError:
                _fail("RECORD_REPLACE")
            self._fsync_directory(root_descriptor)
            final, _ = self._read_file(root_descriptor, name, required=True)
            if final != replacement:
                _fail("RECORD_REPLACED")
            return self._decode(final)
        finally:
            try:
                os.unlink(temporary_name, dir_fd=root_descriptor)
                self._fsync_directory(root_descriptor)
            except FileNotFoundError:
                pass
            except OSError:
                _fail("TEMP_CLEANUP")


ExecutiveReleaseActuatorJournal = _ExecutiveReleaseActuatorJournal

__all__ = [
    "ExecutiveReleaseActuatorJournal",
    "ExecutiveReleaseActuatorJournalError",
    "JOURNAL_PRODUCTION_ROOT",
]
