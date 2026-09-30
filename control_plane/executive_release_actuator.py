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
    validate_approval_evidence,
    validate_precondition_manifest,
    validate_release_prestart_cancellation,
    validate_release_prestart_reservation,
)
from control_plane.fs_security import FilesystemSecurityError, has_macos_acl


JOURNAL_PRODUCTION_ROOT = "/var/db/mastermind-executive/release-actuator/journal"

_SCHEMA = "mastermind.executive_release_actuator_journal/v2"
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
        "root_qualification_digest",
    }
)
_TERMINAL_FIELDS = frozenset(
    {"completed_at_ms", "postcondition_digest", "before", "after", "rollback"}
)
_INSTALLED_IDENTITY_FIELDS = frozenset(
    {
        "release_commit",
        "release_tree",
        "installed_manifest_digest",
        "configuration_digest",
        "broker_source_commit",
        "broker_source_tree",
        "broker_binary_digest",
        "service_generation_digests",
    }
)
_SERVICE_ROLES = frozenset({"control", "worker", "relay", "gateway", "broker"})
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
_OPEN_RECORD = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
_LOCAL_LOCK = threading.Lock()
_RESERVATION_SUFFIX = ".reservation.json"
_CANCELLATION_SUFFIX = ".cancellation.json"


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


def _operation_stem(operation_key: str) -> str:
    """One stem derived from the validated original operation key.

    The stem names the START `.json`, `.start`, `.next`, `.lock` family and
    the separate `.reservation.json` / `.cancellation.json` sidecars. It is
    sha256(operation_key) so callers digest the original operation key once.
    """

    return _operation_key(operation_key) and hashlib.sha256(
        _operation_key(operation_key).encode("ascii")
    ).hexdigest()


def _validate_contract_record(
    value: Any,
    validator: Callable[..., ReleaseRecord],
    **expected: Any,
) -> ReleaseRecord:
    try:
        validated = validator(value, **expected)
    except ReleaseContractError:
        _fail("INVALID_EMBEDDED_RECORD")
    return validated


def _before_identity(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "release_commit": record["before_release_commit"],
        "release_tree": record["before_release_tree"],
        "installed_manifest_digest": record["before_installed_manifest_digest"],
        "configuration_digest": record["before_configuration_digest"],
    }


def _start_identity(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **{field: record[field] for field in _IDENTITY_FIELDS},
        "preconditions": record["preconditions"],
        "admission": record["admission"],
        "actuator_generation": record["actuator_generation"],
        "started_at_ms": record["started_at_ms"],
        "root_qualification_digest": record["root_qualification_digest"],
    }


def _validate_installed_identity(value: Any, code: str) -> dict[str, Any]:
    identity = _exact_mapping(value, _INSTALLED_IDENTITY_FIELDS, code)
    _commit(identity["release_commit"], code)
    _commit(identity["release_tree"], code)
    _digest(identity["installed_manifest_digest"], code)
    _digest(identity["configuration_digest"], code)
    _commit(identity["broker_source_commit"], code)
    _commit(identity["broker_source_tree"], code)
    _digest(identity["broker_binary_digest"], code)
    services = identity["service_generation_digests"]
    if not isinstance(services, Mapping) or frozenset(services) != _SERVICE_ROLES:
        _fail(code)
    identity["service_generation_digests"] = {
        role: _digest(services[role], code + ".service_generation_digests." + role)
        for role in _SERVICE_ROLES
    }
    return identity


def _validate_terminal(terminal: Any, record: Mapping[str, Any]) -> dict[str, Any]:
    value = _exact_mapping(terminal, _TERMINAL_FIELDS, "INVALID_TERMINAL")
    completed_at_ms = _integer(
        value["completed_at_ms"], "INVALID_COMPLETED_AT_MS"
    )
    if completed_at_ms < record["started_at_ms"]:
        _fail("INVALID_COMPLETED_AT_MS")
    _digest(value["postcondition_digest"], "INVALID_POSTCONDITION_DIGEST")
    before = _validate_installed_identity(value["before"], "INVALID_BEFORE")
    after = _validate_installed_identity(value["after"], "INVALID_AFTER")
    # terminal.before first four content fields must equal the START identity.
    if (
        before["release_commit"] != record["before_release_commit"]
        or before["release_tree"] != record["before_release_tree"]
        or before["installed_manifest_digest"]
        != record["before_installed_manifest_digest"]
        or before["configuration_digest"]
        != record["before_configuration_digest"]
    ):
        _fail("INVALID_BEFORE")
    # broker_source commit/tree of before must equal before release commit/tree.
    if (
        before["broker_source_commit"] != before["release_commit"]
        or before["broker_source_tree"] != before["release_tree"]
    ):
        _fail("INVALID_BEFORE")
    # broker_source commit/tree of after must equal after release commit/tree.
    if (
        after["broker_source_commit"] != after["release_commit"]
        or after["broker_source_tree"] != after["release_tree"]
    ):
        _fail("INVALID_AFTER")
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
        "before": before,
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
    _digest(record["root_qualification_digest"], "INVALID_ROOT_QUALIFICATION")
    _integer(record["actuator_generation"], "INVALID_GENERATION", minimum=1)
    _integer(record["journal_generation"], "INVALID_GENERATION", minimum=1)
    _integer(record["started_at_ms"], "INVALID_STARTED_AT_MS")

    try:
        preconditions = validate_precondition_manifest(record["preconditions"])
        admission = validate_admission(record["admission"])
    except ReleaseContractError:
        _fail("INVALID_EMBEDDED_RECORD")
    # The embedded validated admission already carries approved_transition_ref
    # and target_observation_digest, derived from operation_key and the
    # canonical Runtime producer respectively. They are not caller-controlled
    # copies at the START identity level.
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
        return _operation_stem(value) + ".json"

    def _check_descriptor(
        self,
        descriptor: int,
        info: os.stat_result,
        *,
        directory: bool,
        mode: int,
        code: str,
        expected_links: int = 1,
    ) -> None:
        expected_type = stat.S_IFDIR if directory else stat.S_IFREG
        if (
            stat.S_IFMT(info.st_mode) != expected_type
            or stat.S_IMODE(info.st_mode) != mode
            or info.st_uid != self._expected_uid
            or (not directory and info.st_nlink != expected_links)
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
                    os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
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
        self,
        root_descriptor: int,
        name: str,
        *,
        required: bool,
        expected_links: int = 1,
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
                expected_links=expected_links,
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

    @classmethod
    def _decode_for_operation(
        cls, raw: bytes, operation_key: str
    ) -> ReleaseRecord:
        record = cls._decode(raw)
        if record["operation_key"] != operation_key:
            _fail("OPERATION_MISMATCH")
        return record

    @staticmethod
    def _decode_approval(raw: Mapping[str, Any]) -> ReleaseRecord:
        return _validate_contract_record(raw, validate_approval_evidence)

    @staticmethod
    def _validated_contract_bytes(record: ReleaseRecord) -> bytes:
        encoded = canonical_release_bytes(record)
        if len(encoded) > _MAX_RECORD_BYTES:
            _fail("RECORD_SIZE")
        return encoded

    @classmethod
    def _decode_reservation(
        cls,
        raw: Mapping[str, Any],
        approval: ReleaseRecord,
    ) -> tuple[bytes, ReleaseRecord]:
        record = _validate_contract_record(
            raw,
            validate_release_prestart_reservation,
            expected_approval=approval,
        )
        return cls._validated_contract_bytes(record), record

    @classmethod
    def _decode_cancellation(
        cls,
        raw: Mapping[str, Any],
        reservation: ReleaseRecord,
        admission: Mapping[str, Any],
        approval: ReleaseRecord,
    ) -> tuple[bytes, ReleaseRecord]:
        record = _validate_contract_record(
            raw,
            validate_release_prestart_cancellation,
            expected_reservation=reservation,
            expected_admission=admission,
            expected_approval=approval,
        )
        return cls._validated_contract_bytes(record), record

    def _read_prestart_snapshot(
        self,
        root_descriptor: int,
        stem: str,
        *,
        kind: str,
        required: bool,
    ) -> tuple[bytes, tuple[Any, ...]]:
        suffix = _RESERVATION_SUFFIX if kind == "reservation" else _CANCELLATION_SUFFIX
        return self._read_file(
            root_descriptor,
            stem + suffix,
            required=required,
        )

    def _read_prestart_bytes(
        self,
        root_descriptor: int,
        stem: str,
        *,
        kind: str,
        required: bool,
    ) -> bytes:
        """Compatibility wrapper used by stable replay's middle observation."""

        return self._read_prestart_snapshot(
            root_descriptor,
            stem,
            kind=kind,
            required=required,
        )[0]

    def _read_stable_prestart_snapshot(
        self,
        root_descriptor: int,
        stem: str,
        *,
        kind: str,
        required: bool,
    ) -> tuple[bytes, tuple[Any, ...]]:
        first_raw, first_identity = self._read_prestart_snapshot(
            root_descriptor,
            stem,
            kind=kind,
            required=required,
        )
        if not first_identity:
            return first_raw, first_identity
        middle_raw = self._read_prestart_bytes(
            root_descriptor,
            stem,
            kind=kind,
            required=True,
        )
        final_raw, final_identity = self._read_prestart_snapshot(
            root_descriptor,
            stem,
            kind=kind,
            required=True,
        )
        if (
            first_raw != middle_raw
            or middle_raw != final_raw
            or first_identity != final_identity
        ):
            _fail("RECORD_REPLACED")
        return final_raw, final_identity

    def _validate_prestart_snapshot(
        self,
        raw: bytes,
        *,
        kind: str,
        operation_key: str,
        approval: ReleaseRecord,
        reservation: ReleaseRecord | None = None,
        admission: Mapping[str, Any] | None = None,
    ) -> ReleaseRecord:
        # An existing zero-byte sidecar is interrupted or malformed evidence,
        # never absence. Keep it in place and fail closed.
        if not raw:
            _fail("RECORD_BYTES")
        try:
            parsed = parse_release_json(raw)
        except ReleaseContractError:
            _fail("RECORD_BYTES")
        if kind == "reservation":
            encoded, record = self._decode_reservation(parsed.to_dict(), approval)
        else:
            encoded, record = self._decode_cancellation(
                parsed.to_dict(),
                reservation,
                admission,
                approval,
            )
        if encoded != raw:
            _fail("RECORD_BYTES")
        if record["operation_key"] != operation_key:
            _fail("OPERATION_MISMATCH")
        return record

    def _read_and_validate_prestart(
        self,
        root_descriptor: int,
        stem: str,
        *,
        kind: str,
        operation_key: str,
        required: bool,
        approval: ReleaseRecord,
        reservation: ReleaseRecord | None = None,
        admission: Mapping[str, Any] | None = None,
    ) -> tuple[bytes, ReleaseRecord | None]:
        raw, identity = self._read_prestart_snapshot(
            root_descriptor,
            stem,
            kind=kind,
            required=required,
        )
        if not identity:
            return b"", None
        record = self._validate_prestart_snapshot(
            raw,
            kind=kind,
            operation_key=operation_key,
            approval=approval,
            reservation=reservation,
            admission=admission,
        )
        return raw, record

    def _start_evidence_exists(
        self,
        root_descriptor: int,
        stem: str,
        operation_key: str,
    ) -> bool:
        final_name = stem + ".json"
        staged_name = stem + ".start"

        def metadata(name: str) -> os.stat_result | None:
            try:
                return os.stat(
                    name, dir_fd=root_descriptor, follow_symlinks=False
                )
            except FileNotFoundError:
                return None
            except OSError:
                _fail("RECORD_METADATA")

        final_info = metadata(final_name)
        staged_info = metadata(staged_name)
        if final_info is None and staged_info is None:
            return False

        # START publication has three valid durable shapes: a standalone
        # staged inode before link(), a linked staged/final pair before staged
        # cleanup, and a standalone final inode after cleanup. Reject every
        # other shape rather than treating ambiguous filesystem state as an
        # absence of START authority.
        if final_info is not None and staged_info is not None:
            if (
                (final_info.st_dev, final_info.st_ino)
                != (staged_info.st_dev, staged_info.st_ino)
                or final_info.st_nlink != 2
                or staged_info.st_nlink != 2
            ):
                _fail("RECORD_METADATA")
            expected_final_links = expected_staged_links = 2
        elif final_info is not None:
            if final_info.st_nlink != 1:
                _fail("RECORD_METADATA")
            expected_final_links, expected_staged_links = 1, None
        else:
            if staged_info is None or staged_info.st_nlink != 1:
                _fail("RECORD_METADATA")
            expected_final_links, expected_staged_links = None, 1

        final_raw = b""
        staged_raw = b""
        if expected_final_links is not None:
            final_raw, _ = self._read_file(
                root_descriptor,
                final_name,
                required=True,
                expected_links=expected_final_links,
            )
        if expected_staged_links is not None:
            staged_raw, _ = self._read_file(
                root_descriptor,
                staged_name,
                required=True,
                expected_links=expected_staged_links,
            )
        if final_raw and staged_raw and final_raw != staged_raw:
            _fail("RECORD_METADATA")
        for raw in (final_raw, staged_raw):
            if raw:
                record = self._decode(raw)
                if record["operation_key"] != operation_key:
                    _fail("OPERATION_MISMATCH")
        return True

    def reserve_prestart(
        self,
        *,
        reservation: Mapping[str, Any],
        approval: Mapping[str, Any],
    ) -> ReleaseRecord:
        validated_approval = self._decode_approval(approval)
        reservation_bytes, validated_reservation = self._decode_reservation(
            reservation,
            validated_approval,
        )
        operation_key = validated_reservation["operation_key"]
        stem = _operation_stem(operation_key)
        name = stem + ".json"
        return self._locked(
            name,
            lambda root, _: self._reserve_locked(
                root,
                stem,
                reservation_bytes,
                operation_key,
                validated_approval,
            ),
            create_root=True,
        )

    def _reserve_locked(
        self,
        root_descriptor: int,
        stem: str,
        reservation_bytes: bytes,
        operation_key: str,
        validated_approval: ReleaseRecord,
    ) -> ReleaseRecord:
        # Read before write: exact byte-identical replay returns the stored
        # record without any rewrite of metadata, including after cancellation
        # or START. That is immutable history readback, not new authority. A
        # different byte sequence conflicts before any state is changed.
        existing_raw, existing_identity = self._read_stable_prestart_snapshot(
            root_descriptor,
            stem,
            kind="reservation",
            required=False,
        )
        if existing_identity:
            if existing_raw == reservation_bytes:
                return self._validate_prestart_snapshot(
                    existing_raw,
                    kind="reservation",
                    operation_key=operation_key,
                    approval=validated_approval,
                )
            _fail("RESERVATION_CONFLICT")
        # A genuinely fresh reservation cannot appear after cancellation,
        # final START, or any staged/partial START evidence.
        _cancellation_raw, cancellation_identity = self._read_prestart_snapshot(
            root_descriptor,
            stem,
            kind="cancellation",
            required=False,
        )
        if cancellation_identity:
            _fail("RESERVATION_CONFLICT")
        if self._start_evidence_exists(root_descriptor, stem, operation_key):
            _fail("RESERVATION_CONFLICT")
        created_identity = self._write_new(
            root_descriptor,
            stem + _RESERVATION_SUFFIX,
            reservation_bytes,
        )
        stored, stored_identity = self._read_prestart_snapshot(
            root_descriptor,
            stem,
            kind="reservation",
            required=True,
        )
        if stored != reservation_bytes or stored_identity != created_identity:
            _fail("RECORD_REPLACED")
        return self._validate_prestart_snapshot(
            stored,
            kind="reservation",
            operation_key=operation_key,
            approval=validated_approval,
        )

    def read_prestart_reservation(
        self, operation_key: str, *, approval: Mapping[str, Any]
    ) -> ReleaseRecord:
        return self._read_prestart_reservation_snapshot(
            operation_key, approval=approval
        )[0]

    def _read_prestart_reservation_snapshot(
        self, operation_key: str, *, approval: Mapping[str, Any]
    ) -> tuple[ReleaseRecord, bytes, tuple[Any, ...]]:
        """Read validated reservation content and identity under one lock."""

        validated_operation_key = _operation_key(operation_key)
        validated_approval = self._decode_approval(approval)
        stem = _operation_stem(validated_operation_key)
        name = stem + ".json"
        return self._locked(
            name,
            lambda root, _: self._read_prestart_reservation_snapshot_locked(
                root, stem, validated_operation_key, validated_approval
            ),
            create_root=False,
        )

    def _read_prestart_reservation_snapshot_locked(
        self,
        root_descriptor: int,
        stem: str,
        operation_key: str,
        validated_approval: ReleaseRecord,
    ) -> tuple[ReleaseRecord, bytes, tuple[Any, ...]]:
        raw, identity = self._read_prestart_snapshot(
            root_descriptor, stem, kind="reservation", required=True
        )
        record = self._validate_prestart_snapshot(
            raw,
            kind="reservation",
            operation_key=operation_key,
            approval=validated_approval,
        )
        return record, raw, identity

    def cancel_prestart(
        self,
        *,
        cancellation: Mapping[str, Any],
        reservation: Mapping[str, Any],
        admission: Mapping[str, Any],
        approval: Mapping[str, Any],
    ) -> ReleaseRecord:
        validated_approval = self._decode_approval(approval)
        reservation_bytes, validated_reservation = self._decode_reservation(
            reservation,
            validated_approval,
        )
        operation_key = validated_reservation["operation_key"]
        stem = _operation_stem(operation_key)
        name = stem + ".json"
        return self._locked(
            name,
            lambda root, _: self._cancel_locked(
                root,
                stem,
                cancellation,
                reservation_bytes,
                validated_reservation,
                admission,
                validated_approval,
            ),
            create_root=False,
        )

    def _cancel_locked(
        self,
        root_descriptor: int,
        stem: str,
        cancellation: Mapping[str, Any],
        reservation_bytes: bytes,
        validated_reservation: ReleaseRecord,
        admission: Mapping[str, Any],
        validated_approval: ReleaseRecord,
    ) -> ReleaseRecord:
        operation_key = validated_reservation["operation_key"]
        # Cancellation requires a byte-identical stored reservation.
        stored_reservation_bytes, stored_reservation = (
            self._read_and_validate_prestart(
                root_descriptor,
                stem,
                kind="reservation",
                operation_key=operation_key,
                required=True,
                approval=validated_approval,
            )
        )
        if reservation_bytes != stored_reservation_bytes:
            _fail("RESERVATION_MISMATCH")
        # Re-decode cancellation against the immutable stored reservation so
        # all frozen validator joins are exercised against the on-disk bytes.
        cancellation_bytes, validated_cancellation = self._decode_cancellation(
            cancellation,
            stored_reservation,
            admission,
            validated_approval,
        )
        # Refuse final or staged START.
        if self._start_evidence_exists(root_descriptor, stem, operation_key):
            _fail("RESERVATION_CONFLICT")
        existing_raw, existing_identity = self._read_stable_prestart_snapshot(
            root_descriptor,
            stem,
            kind="cancellation",
            required=False,
        )
        if existing_identity:
            if existing_raw == cancellation_bytes:
                return self._validate_prestart_snapshot(
                    existing_raw,
                    kind="cancellation",
                    operation_key=operation_key,
                    approval=validated_approval,
                    reservation=stored_reservation,
                    admission=admission,
                )
            _fail("CANCELLATION_CONFLICT")
        created_identity = self._write_new(
            root_descriptor,
            stem + _CANCELLATION_SUFFIX,
            cancellation_bytes,
        )
        # The reservation file must never be deleted or rewritten.
        stored, stored_identity = self._read_prestart_snapshot(
            root_descriptor,
            stem,
            kind="cancellation",
            required=True,
        )
        if stored != cancellation_bytes or stored_identity != created_identity:
            _fail("RECORD_REPLACED")
        return self._validate_prestart_snapshot(
            stored,
            kind="cancellation",
            operation_key=operation_key,
            approval=validated_approval,
            reservation=stored_reservation,
            admission=admission,
        )

    def read_prestart_cancellation(
        self,
        operation_key: str,
        *,
        reservation: Mapping[str, Any],
        admission: Mapping[str, Any],
        approval: Mapping[str, Any],
    ) -> ReleaseRecord:
        validated_operation_key = _operation_key(operation_key)
        validated_approval = self._decode_approval(approval)
        reservation_bytes, validated_reservation = self._decode_reservation(
            reservation,
            validated_approval,
        )
        if validated_reservation["operation_key"] != validated_operation_key:
            _fail("OPERATION_MISMATCH")
        stem = _operation_stem(validated_operation_key)
        name = stem + ".json"
        return self._locked(
            name,
            lambda root, _: self._read_and_validate_prestart(
                root,
                stem,
                kind="cancellation",
                operation_key=validated_operation_key,
                required=True,
                approval=validated_approval,
                reservation=validated_reservation,
                admission=admission,
            )[1],
            create_root=False,
        )

    def _read_closure_snapshot(
        self,
        operation_key: str,
        *,
        initial_reservation_bytes: bytes,
        initial_reservation_identity: tuple[Any, ...] | None,
        approval: Mapping[str, Any],
        admission: Mapping[str, Any],
    ) -> tuple[ReleaseRecord | None, ReleaseRecord | None]:
        """Coherent journal + cancellation snapshot under one operation lock.

        Acquires the per-operation `.lock` once, then revalidates the
        reservation sidecar (the same operation lock guards it against an
        interleaving mutation between the initial reservation read and this
        external snapshot). Requires exact canonical byte equality against
        ``initial_reservation_bytes`` and exact filesystem identity
        equality against ``initial_reservation_identity``; refuses with
        ``RESERVATION_REPLACED`` on any drift or absence rather than
        adopting replacement bytes as a new truth. Replays the same
        immutable joins the closure reader and terminal advance already
        enforce against the stored reservation and sealed approval, and
        reads the journal and cancellation under the same lock. Refuses
        with ``RECORD_BYTES`` / ``RESERVATION_MISMATCH`` /
        ``ROOT_QUALIFICATION_MISMATCH`` / ``BEFORE_MISMATCH`` on any other
        drift before returning. No external Runtime, network, broker, or
        provider I/O is performed under the operation lock.
        """

        validated_operation_key = _operation_key(operation_key)
        validated_approval = self._decode_approval(approval)
        validated_admission = validate_admission(admission)
        if (
            not isinstance(initial_reservation_bytes, bytes)
            or not initial_reservation_bytes
            or not initial_reservation_identity
        ):
            _fail("RESERVATION_REPLACED")
        stem = _operation_stem(validated_operation_key)
        name = stem + ".json"
        return self._locked(
            name,
            lambda root, _: self._closure_snapshot_locked(
                root,
                validated_operation_key,
                stem,
                initial_reservation_bytes=initial_reservation_bytes,
                initial_reservation_identity=initial_reservation_identity,
                validated_approval=validated_approval,
                validated_admission=validated_admission,
            ),
            create_root=False,
        )

    def _closure_snapshot_locked(
        self,
        root_descriptor: int,
        operation_key: str,
        stem: str,
        *,
        initial_reservation_bytes: bytes,
        initial_reservation_identity: tuple[Any, ...],
        validated_approval: ReleaseRecord,
        validated_admission: Any,
    ) -> tuple[ReleaseRecord | None, ReleaseRecord | None]:
        # 1. Re-read the reservation sidecar; require canonical bytes and
        # filesystem identity to match the initial reservation observation.
        # An inode-only replacement with byte-identical content still
        # differs in filesystem identity and is refused as drift; any
        # byte-level replacement is refused the same way. Bytes-drift
        # is unambiguous refusal; we do not adopt replacement bytes as a
        # new truth.
        stored_reservation_bytes, stored_reservation_identity = (
            self._read_prestart_snapshot(
                root_descriptor,
                stem,
                kind="reservation",
                required=True,
            )
        )
        if (
            stored_reservation_bytes != initial_reservation_bytes
            or stored_reservation_identity != initial_reservation_identity
        ):
            _fail("RESERVATION_REPLACED")
        # 2. Re-decode the stored reservation against the sealed approval to
        # bind every immutable join to the canonical bytes we just observed.
        stored_reservation = self._validate_prestart_snapshot(
            stored_reservation_bytes,
            kind="reservation",
            operation_key=operation_key,
            approval=validated_approval,
        )
        reservation_digest = hashlib.sha256(
            stored_reservation_bytes
        ).hexdigest()
        # 3. Repeat admission joins against the stored reservation and the
        # supplied admission. The closure reader had the same evidence before
        # the external call, so any drift here is unambiguous refusal.
        self._validate_admission_joins(
            validated_admission, stored_reservation, operation_key
        )
        # 4. Read the journal record under the same lock; refuse on
        # root-digest drift, START/reservation drift, or terminal full-before
        # drift.
        journal_raw, _ = self._read_file(
            root_descriptor, stem + ".json", required=False
        )
        journal_record: ReleaseRecord | None = None
        if journal_raw:
            journal_record = self._decode_for_operation(journal_raw, operation_key)
            if journal_record["root_qualification_digest"] != reservation_digest:
                _fail("ROOT_QUALIFICATION_MISMATCH")
            self._validate_start_reservation_joins(
                journal_record, stored_reservation, validated_approval
            )
            if journal_record["state"] in _TERMINAL_STATES:
                if (
                    canonical_release_bytes(journal_record["terminal"]["before"])
                    != canonical_release_bytes(stored_reservation["before"])
                ):
                    # Preserve the established closure-reader error contract;
                    # terminal advance uses BEFORE_MISMATCH for caller input,
                    # while a stored journal inconsistency is RECORD_MISMATCH.
                    _fail("RECORD_MISMATCH")
        # 5. Read the cancellation sidecar under the same lock, validating
        # it against the stored reservation (not the initial one).
        cancellation_raw, cancellation_identity = self._read_prestart_snapshot(
            root_descriptor, stem, kind="cancellation", required=False
        )
        cancellation_record: ReleaseRecord | None = None
        if cancellation_identity:
            cancellation_record = self._validate_prestart_snapshot(
                cancellation_raw,
                kind="cancellation",
                operation_key=operation_key,
                approval=validated_approval,
                reservation=stored_reservation,
                admission=validated_admission,
            )
        # Quiet the no-op bind for the cached sidecar identity.
        del cancellation_identity
        return journal_record, cancellation_record

    def _write_new(
        self, root_descriptor: int, name: str, raw: bytes
    ) -> tuple[Any, ...]:
        if not 0 < len(raw) <= _MAX_RECORD_BYTES:
            _fail("RECORD_SIZE")
        descriptor = None
        created = False
        created_inode = None
        created_identity = None
        complete = False
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
            created_inode = (info.st_dev, info.st_ino)
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
            completed_info = os.fstat(descriptor)
            self._check_descriptor(
                descriptor,
                completed_info,
                directory=False,
                mode=_FILE_MODE,
                code="RECORD_METADATA",
            )
            created_identity = _file_identity(completed_info)
            self._assert_file_path(
                root_descriptor,
                name,
                descriptor,
                created_identity,
                "RECORD_REPLACED",
            )
            self._fsync_directory(root_descriptor)
            complete = True
            os.close(descriptor)
            descriptor = None
        except FileExistsError:
            _fail("RECORD_EXISTS")
        except ExecutiveReleaseActuatorJournalError:
            raise
        except OSError:
            _fail("RECORD_WRITE")
        finally:
            if created and not complete and created_inode is not None:
                try:
                    observed = os.stat(
                        name, dir_fd=root_descriptor, follow_symlinks=False
                    )
                except OSError:
                    observed = None
                if (
                    observed is not None
                    and (observed.st_dev, observed.st_ino) == created_inode
                ):
                    try:
                        os.unlink(name, dir_fd=root_descriptor)
                        self._fsync_directory(root_descriptor)
                    except OSError:
                        pass
            if descriptor is not None:
                os.close(descriptor)
        if created_identity is None:
            _fail("RECORD_WRITE")
        return created_identity

    def _unlink_owned(
        self,
        root_descriptor: int,
        name: str,
        expected_identity: tuple[Any, ...],
        code: str,
    ) -> None:
        try:
            observed = os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError:
            _fail(code)
        if _file_identity(observed) != expected_identity:
            _fail(code)
        try:
            os.unlink(name, dir_fd=root_descriptor)
            self._fsync_directory(root_descriptor)
        except OSError:
            _fail(code)

    def create(
        self,
        *,
        actuator_generation: int,
        identity: Mapping[str, Any],
        preconditions: Mapping[str, Any],
        admission: Mapping[str, Any],
        approval: Mapping[str, Any],
        reservation: Mapping[str, Any],
        root_qualification_digest: str,
        started_at_ms: int,
        commit_qualifier: Callable[[], int] | None = None,
    ) -> ReleaseRecord:
        if commit_qualifier is not None and not callable(commit_qualifier):
            raise TypeError("commit qualifier must be callable")
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
            "root_qualification_digest": root_qualification_digest,
        }
        validated = _validate_record(candidate)
        raw = canonical_release_bytes(validated)
        validated_approval = self._decode_approval(approval)
        reservation_bytes, validated_reservation = self._decode_reservation(
            reservation,
            validated_approval,
        )
        operation_key = validated_reservation["operation_key"]
        if operation_key != validated["operation_key"]:
            _fail("OPERATION_MISMATCH")
        stem = _operation_stem(operation_key)
        name = stem + ".json"
        supplied_root_digest = _digest(
            root_qualification_digest,
            "INVALID_ROOT_QUALIFICATION",
        )

        def create_with_reservation(root_descriptor: int, record_name: str):
            # 1. Read stored reservation; it must match caller bytes exactly.
            stored_reservation_bytes, stored_reservation = (
                self._read_and_validate_prestart(
                    root_descriptor,
                    stem,
                    kind="reservation",
                    operation_key=operation_key,
                    required=True,
                    approval=validated_approval,
                )
            )
            if reservation_bytes != stored_reservation_bytes:
                _fail("RESERVATION_MISMATCH")
            # 2. The supplied root digest must equal sha256(stored reservation).
            if supplied_root_digest != hashlib.sha256(
                stored_reservation_bytes
            ).hexdigest():
                _fail("ROOT_QUALIFICATION_MISMATCH")
            # 3. Bind every applicable START identity and the exact persisted
            # precondition snapshot to the immutable reservation/approval.
            self._validate_start_reservation_joins(
                validated,
                stored_reservation,
                validated_approval,
            )
            # 4. Explicit admission join to reservation, preconditions, etc.
            self._validate_admission_joins(
                validated["admission"],
                stored_reservation,
                operation_key,
            )
            # 5. Any cancellation inode, including an interrupted zero-byte
            # sidecar, permanently blocks START and remains for reconciliation.
            _cancellation_raw, cancellation_identity = (
                self._read_prestart_snapshot(
                    root_descriptor,
                    stem,
                    kind="cancellation",
                    required=False,
                )
            )
            if cancellation_identity:
                _fail("RESERVATION_CONFLICT")
            # 6. A composed owner may requalify current authority and time
            # after every blocking journal read, while this operation lock is
            # still held. Existing callers retain the original fixed timestamp.
            locked_validated = validated
            locked_raw = raw
            if commit_qualifier is not None:
                locked_candidate = {
                    **candidate,
                    "started_at_ms": commit_qualifier(),
                }
                locked_validated = _validate_record(locked_candidate)
                locked_raw = canonical_release_bytes(locked_validated)
                self._validate_start_reservation_joins(
                    locked_validated,
                    stored_reservation,
                    validated_approval,
                )
                self._validate_admission_joins(
                    locked_validated["admission"],
                    stored_reservation,
                    operation_key,
                )
            # 7. Delegate exact-replay/recovery to the protected _create_locked.
            return self._create_locked(
                root_descriptor,
                record_name,
                locked_raw,
                locked_validated,
            )

        return self._locked(
            name,
            create_with_reservation,
            create_root=True,
        )

    @staticmethod
    def _validate_start_reservation_joins(
        start: ReleaseRecord,
        reservation: ReleaseRecord,
        approval: ReleaseRecord,
    ) -> None:
        before = reservation["before"]
        effect = approval["normalized_requested_effect"]
        expected = {
            "operation_key": reservation["operation_key"],
            "request_fingerprint": reservation["request_fingerprint"],
            "approval_evidence_digest": reservation["approval_evidence_digest"],
            "normalized_requested_effect_digest": reservation[
                "normalized_requested_effect_digest"
            ],
            "expected_source_and_precondition_digest": reservation[
                "expected_precondition_digest"
            ],
            "action_target_digest": reservation["action_target_digest"],
            "owner_installation_id": reservation["owner_installation_id"],
            "target_ref": reservation["target_ref"],
            "before_release_commit": before["release_commit"],
            "before_release_tree": before["release_tree"],
            "before_installed_manifest_digest": before[
                "installed_manifest_digest"
            ],
            "before_configuration_digest": before["configuration_digest"],
            "target_release_commit": reservation["to_release_commit"],
            "target_release_tree": effect["to_release_tree"],
            "boot_id": reservation["preconditions"]["boot_id"],
        }
        if any(start[key] != value for key, value in expected.items()):
            _fail("RESERVATION_MISMATCH")
        if canonical_release_bytes(start["preconditions"]) != canonical_release_bytes(
            reservation["preconditions"]
        ):
            _fail("RESERVATION_MISMATCH")
        prepared = reservation["prepared_payload"]
        if not (
            reservation["reserved_at_ms"]
            <= start["started_at_ms"]
            < prepared["expires_at_ms"]
        ):
            _fail("RESERVATION_MISMATCH")

    @staticmethod
    def _validate_admission_joins(
        admission: Mapping[str, Any],
        reservation: ReleaseRecord,
        operation_key: str,
    ) -> None:
        # Validate the admission with the frozen validator first, then
        # explicitly byte-join its identity fields to the stored reservation.
        try:
            validated_admission = validate_admission(admission)
        except ReleaseContractError:
            _fail("INVALID_ADMISSION")
        for key in (
            "operation_key",
            "approved_transition_ref",
            "target_ref",
            "owner_installation_id",
            "effective_grant_digest",
            "request_fingerprint",
        ):
            if validated_admission[key] != reservation[key]:
                _fail("ADMISSION_JOIN_MISMATCH")
        if validated_admission["boot_id"] != reservation["preconditions"]["boot_id"]:
            _fail("ADMISSION_JOIN_MISMATCH")
        if (
            validated_admission["admission_contract_digest"]
            != reservation["preconditions"]["admission_contract_digest"]
        ):
            _fail("ADMISSION_JOIN_MISMATCH")
        if (
            validated_admission["target_observation_digest"]
            != reservation["target_observation_digest"]
        ):
            _fail("ADMISSION_JOIN_MISMATCH")
        if validated_admission["operation_key"] != operation_key:
            _fail("ADMISSION_JOIN_MISMATCH")

    def _create_locked(
        self,
        root_descriptor: int,
        name: str,
        candidate: bytes,
        candidate_record: ReleaseRecord,
    ) -> ReleaseRecord:
        recovered = self._recover_linked_start(
            root_descriptor, name, candidate, candidate_record["operation_key"]
        )
        if recovered is not None:
            return recovered
        current, _ = self._read_file(root_descriptor, name, required=False)
        if current:
            existing = self._decode_for_operation(
                current, candidate_record["operation_key"]
            )
            # Exact START replay returns only if the complete start identity,
            # including root_qualification_digest, matches.
            if _start_identity(existing) == _start_identity(candidate_record):
                return existing
            _fail("CONFLICT")
        self._publish_start(root_descriptor, name, candidate)
        written, _ = self._read_file(root_descriptor, name, required=True)
        if written != candidate:
            _fail("RECORD_REPLACED")
        return self._decode_for_operation(
            written, candidate_record["operation_key"]
        )

    def _recover_linked_start(
        self,
        root_descriptor: int,
        name: str,
        candidate: bytes,
        operation_key: str,
    ) -> ReleaseRecord | None:
        staged_name = name[:-5] + ".start"
        try:
            final_info = os.stat(
                name, dir_fd=root_descriptor, follow_symlinks=False
            )
        except FileNotFoundError:
            return None
        except OSError:
            _fail("RECORD_OPEN")
        if final_info.st_nlink != 2:
            return None
        try:
            staged_info = os.stat(
                staged_name, dir_fd=root_descriptor, follow_symlinks=False
            )
        except OSError:
            _fail("RECORD_METADATA")
        if (
            (final_info.st_dev, final_info.st_ino)
            != (staged_info.st_dev, staged_info.st_ino)
            or staged_info.st_nlink != 2
        ):
            _fail("RECORD_METADATA")
        final_raw, final_identity = self._read_file(
            root_descriptor, name, required=True, expected_links=2
        )
        staged_raw, staged_identity = self._read_file(
            root_descriptor, staged_name, required=True, expected_links=2
        )
        if (
            final_raw != candidate
            or staged_raw != candidate
            or final_identity[:2] != staged_identity[:2]
        ):
            _fail("START_STAGED_CONFLICT")
        self._decode_for_operation(final_raw, operation_key)
        self._unlink_owned(
            root_descriptor,
            staged_name,
            staged_identity,
            "START_STAGED_REPLACED",
        )
        published, _ = self._read_file(root_descriptor, name, required=True)
        if published != candidate:
            _fail("RECORD_REPLACED")
        return self._decode_for_operation(published, operation_key)

    def _publish_start(
        self, root_descriptor: int, name: str, candidate: bytes
    ) -> None:
        staged_name = name[:-5] + ".start"
        staged_raw, staged_identity = self._read_file(
            root_descriptor, staged_name, required=False
        )
        if staged_raw:
            if staged_raw != candidate:
                _fail("START_STAGED_CONFLICT")
        else:
            created_identity = self._write_new(
                root_descriptor, staged_name, candidate
            )
            staged_raw, staged_identity = self._read_file(
                root_descriptor, staged_name, required=True
            )
            if staged_raw != candidate or staged_identity != created_identity:
                _fail("RECORD_REPLACED")
        self._decode(candidate)
        staged_again, staged_identity_again = self._read_file(
            root_descriptor, staged_name, required=True
        )
        if staged_again != candidate or staged_identity_again != staged_identity:
            _fail("START_STAGED_REPLACED")
        try:
            os.link(
                staged_name,
                name,
                src_dir_fd=root_descriptor,
                dst_dir_fd=root_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError:
            _fail("RECORD_EXISTS")
        except OSError:
            _fail("RECORD_PUBLISH")
        self._fsync_directory(root_descriptor)
        final_linked_raw, final_linked_identity = self._read_file(
            root_descriptor, name, required=True, expected_links=2
        )
        staged_linked_raw, staged_linked_identity = self._read_file(
            root_descriptor, staged_name, required=True, expected_links=2
        )
        if (
            final_linked_raw != candidate
            or staged_linked_raw != candidate
            or final_linked_identity[:2] != staged_linked_identity[:2]
            or staged_linked_identity[:2] != staged_identity[:2]
        ):
            _fail("START_STAGED_REPLACED")
        self._unlink_owned(
            root_descriptor,
            staged_name,
            staged_linked_identity,
            "START_STAGED_REPLACED",
        )

    def read(self, operation_key: str) -> ReleaseRecord:
        validated_operation_key = _operation_key(operation_key)
        name = self._name(validated_operation_key)
        return self._locked(
            name,
            lambda root, record_name: self._decode_for_operation(
                self._read_file(root, record_name, required=True)[0],
                validated_operation_key,
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
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
        rollback: Mapping[str, Any] | None = None,
        reservation: Mapping[str, Any] | None = None,
        approval: Mapping[str, Any] | None = None,
    ) -> ReleaseRecord:
        _integer(expected_generation, "INVALID_EXPECTED_GENERATION", minimum=1)
        if type(state) is not str or state not in _STATES:
            _fail("INVALID_STATE")
        terminal_arguments = (
            completed_at_ms,
            postcondition_digest,
            before,
            after,
            rollback,
        )
        ancestry_arguments = (reservation, approval)
        if state in _TERMINAL_STATES:
            if any(value is None for value in terminal_arguments):
                _fail("TERMINAL_ARGUMENTS")
            if any(value is None for value in ancestry_arguments):
                _fail("ANCESTRY_ARGUMENTS")
        else:
            if any(value is not None for value in terminal_arguments):
                _fail("TERMINAL_ARGUMENTS")
            if any(value is not None for value in ancestry_arguments):
                _fail("ANCESTRY_ARGUMENTS")
        validated_operation_key = _operation_key(operation_key)
        name = self._name(validated_operation_key)
        supplied_reservation_bytes: bytes | None = None
        validated_approval: ReleaseRecord | None = None
        if state in _TERMINAL_STATES:
            # The reservation/approval are validated through the protected
            # validators; that yields canonical bytes for the reservation.
            validated_approval = self._decode_approval(approval)
            supplied_reservation_bytes, _validated_reservation = self._decode_reservation(
                reservation, validated_approval
            )
        return self._locked(
            name,
            lambda root, record_name: self._advance_locked(
                root,
                record_name,
                expected_generation=expected_generation,
                state=state,
                completed_at_ms=completed_at_ms,
                postcondition_digest=postcondition_digest,
                before=before,
                after=after,
                rollback=rollback,
                operation_key=validated_operation_key,
                supplied_reservation_bytes=supplied_reservation_bytes,
                validated_approval=validated_approval,
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
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        rollback: Mapping[str, Any] | None,
        operation_key: str,
        supplied_reservation_bytes: bytes | None,
        validated_approval: ReleaseRecord | None,
    ) -> ReleaseRecord:
        current_raw, current_identity = self._read_file(
            root_descriptor, name, required=True
        )
        current = self._decode_for_operation(current_raw, operation_key)
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
        initial_reservation_bytes: bytes | None = None
        initial_reservation_identity: tuple[Any, ...] | None = None
        initial_reservation: ReleaseRecord | None = None
        if state in _TERMINAL_STATES:
            # R9 terminal ancestry: revalidate the immutable reservation
            # sidecar from inside the operation/process lock before any
            # replacement journal bytes are written. The supplied approval
            # has already been validated and the supplied reservation
            # validated against it; preserve canonical bytes here. Capture
            # both the canonical bytes and the inode/size/mtime identity so
            # the final-publication guard below can detect an inode-only
            # replacement during staging that leaves the canonical bytes
            # unchanged.
            stem = _operation_stem(operation_key)
            stored_reservation_bytes, stored_reservation_identity = (
                self._read_prestart_snapshot(
                    root_descriptor,
                    stem,
                    kind="reservation",
                    required=True,
                )
            )
            stored_reservation = self._validate_prestart_snapshot(
                stored_reservation_bytes,
                kind="reservation",
                operation_key=operation_key,
                approval=validated_approval,
            )
            if supplied_reservation_bytes != stored_reservation_bytes:
                _fail("RESERVATION_MISMATCH")
            # START root_qualification_digest must be the sha256 of the
            # stored reservation's canonical bytes, not any caller value.
            expected_root_digest = hashlib.sha256(
                stored_reservation_bytes
            ).hexdigest()
            if current["root_qualification_digest"] != expected_root_digest:
                _fail("ROOT_QUALIFICATION_MISMATCH")
            # Repeat the existing immutable joins between the stored
            # reservation/approval and the START record identity.
            self._validate_start_reservation_joins(
                current,
                stored_reservation,
                validated_approval,
            )
            self._validate_admission_joins(
                current["admission"],
                stored_reservation,
                operation_key,
            )
            # The terminal before must byte-equal the reservation's full
            # 8-field before — not just the first four fields.
            if (
                canonical_release_bytes(before)
                != canonical_release_bytes(stored_reservation["before"])
            ):
                _fail("BEFORE_MISMATCH")
            initial_reservation_bytes = stored_reservation_bytes
            initial_reservation_identity = stored_reservation_identity
            initial_reservation = stored_reservation
            updated["terminal"] = {
                "completed_at_ms": completed_at_ms,
                "postcondition_digest": postcondition_digest,
                "before": before,
                "after": after,
                "rollback": rollback,
            }
        validated = _validate_record(updated)
        replacement = canonical_release_bytes(validated)
        temporary_name = name[:-5] + ".tmp"
        temporary_identity = self._write_new(
            root_descriptor, temporary_name, replacement
        )
        try:
            temporary_raw, observed_temporary_identity = self._read_file(
                root_descriptor, temporary_name, required=True
            )
            if (
                temporary_raw != replacement
                or observed_temporary_identity != temporary_identity
            ):
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
            if state in _TERMINAL_STATES:
                # Final-publication guard: revalidate the reservation
                # sidecar under the same operation lock immediately before
                # ``os.replace``. Require exact canonical-bytes equality
                # with the first under-lock observation and equal
                # filesystem identity (an inode-only replacement that
                # happens to keep the canonical bytes equal still leaves
                # the original reservation unchanged; a byte drift is
                # unambiguous refusal). Repeat root digest, START/
                # reservation, admission/reservation, and full-before
                # joins against the retained original identity. On
                # refusal the original nonterminal journal stays intact
                # and the owned temporary inode is the only file the
                # finally clause unlinks.
                stem = _operation_stem(operation_key)
                final_reservation_bytes, final_reservation_identity = (
                    self._read_prestart_snapshot(
                        root_descriptor,
                        stem,
                        kind="reservation",
                        required=True,
                    )
                )
                if (
                    final_reservation_bytes != initial_reservation_bytes
                    or final_reservation_identity
                    != initial_reservation_identity
                ):
                    _fail("RESERVATION_REPLACED")
                expected_root_digest = hashlib.sha256(
                    initial_reservation_bytes
                ).hexdigest()
                if current["root_qualification_digest"] != expected_root_digest:
                    _fail("ROOT_QUALIFICATION_MISMATCH")
                self._validate_start_reservation_joins(
                    current,
                    initial_reservation,
                    validated_approval,
                )
                self._validate_admission_joins(
                    current["admission"],
                    initial_reservation,
                    operation_key,
                )
                if (
                    canonical_release_bytes(before)
                    != canonical_release_bytes(initial_reservation["before"])
                ):
                    _fail("BEFORE_MISMATCH")
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
            return self._decode_for_operation(final, operation_key)
        finally:
            if temporary_identity is not None:
                self._unlink_owned(
                    root_descriptor,
                    temporary_name,
                    temporary_identity,
                    "TEMP_REPLACED",
                )


ExecutiveReleaseActuatorJournal = _ExecutiveReleaseActuatorJournal

__all__ = [
    "ExecutiveReleaseActuatorJournal",
    "ExecutiveReleaseActuatorJournalError",
    "JOURNAL_PRODUCTION_ROOT",
]
