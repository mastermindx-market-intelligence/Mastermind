"""Descriptor-owned per-action claim and receipt helper.

The helper borrows one already-open host-owned artifact directory descriptor.
It does not open or close a runtime root or store owner, create a service,
own an executor, launch processes, or scan artifact directories. Closed
per-action names only.

Artifacts belong to the existing Action runtime. Patch and command reuse the
same borrowed fd and the same claim/create/finalize/read operations with a
distinct purpose and schema payload. This is not a queue, global index,
ledger, retry owner, or Executive Job/Attempt.

Attended F0 treats the artifact store and the dedicated project as exclusive
Workbench write custody. Advisory flock plus identity checks are not an
atomic CAS against an arbitrary non-cooperating same-UID writer.
"""

from __future__ import annotations

import dataclasses
import errno
import fcntl
import json
import os
import re
import stat
import threading
from collections.abc import Mapping
from typing import Any

ACTION_CLAIM_SCHEMA = "mastermind.workbench_action_claim.v1"
ACTION_RESULT_SCHEMA = "mastermind.workbench_action_result.v1"
ACTION_PURPOSE_TEXT_PATCH = "text_patch"
ACTION_PURPOSE_CLOSED_COMMAND = "closed_command"
ACTION_PURPOSES = frozenset(
    {ACTION_PURPOSE_TEXT_PATCH, ACTION_PURPOSE_CLOSED_COMMAND}
)
ACTION_ARTIFACT_KINDS = frozenset({"claim", "result", "stdout", "stderr"})
MAX_CLAIM_BYTES = 4096
MAX_RESULT_BYTES = 16384
MAX_BLOB_BYTES = 65536
MAX_DETAILS_BYTES = 2048
_EFFECTS = frozenset({"NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"})
_DURABILITY = frozenset({"durable", "uncertain"})
_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_BOOT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_THREAD_LOCKS: dict[tuple[int, int], threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


class ActionArtifactError(Exception):
    """Closed artifact-helper failure."""


class ActionArtifactBusy(ActionArtifactError):
    """Nonblocking store writer mutex is held."""


class ActionArtifactUncertain(ActionArtifactError):
    """Store, claim, or receipt cannot be classified honestly."""


@dataclasses.dataclass(frozen=True)
class ActionHostBinding:
    host_id: str
    boot_session_id: str


@dataclasses.dataclass(frozen=True)
class ActionArtifactStore:
    """Borrowed host-owned artifact directory. The helper never closes dir_fd."""

    dir_fd: int
    device: int
    inode: int
    owner_uid: int


@dataclasses.dataclass(frozen=True)
class ActionArtifactIdentity:
    action_id: str
    purpose: str
    subject_digest: str
    client_ref: str
    resource: str
    project_ref: str
    context_ref: str
    responsibility_ref: str
    operation_ref: str
    owner_ref: str
    generation: str
    root_device: int
    root_inode: int
    store_device: int
    store_inode: int
    host_id: str
    boot_session_id: str
    relative_path: str
    source_identity: str | None


@dataclasses.dataclass(frozen=True)
class ActionClaimRecord:
    schema: str
    identity: ActionArtifactIdentity
    claimed_at_ms: int
    phase: str


@dataclasses.dataclass(frozen=True)
class ActionResultRecord:
    schema: str
    identity: ActionArtifactIdentity
    effect_state: str
    observed_sha256: str | None
    completed_at_ms: int
    durability: str
    details: dict[str, Any]


@dataclasses.dataclass(frozen=True)
class ClaimOutcome:
    created: bool
    claim: ActionClaimRecord | None
    uncertain: bool


@dataclasses.dataclass(frozen=True)
class ActionClassification:
    effect_state: str
    claim: ActionClaimRecord | None
    result: ActionResultRecord | None
    store_valid: bool


class ArtifactWriterLock:
    """Process flock plus same-store thread lock. Release is explicit."""

    def __init__(
        self,
        store: ActionArtifactStore,
        thread_lock: threading.Lock,
        *,
        flocked: bool,
    ) -> None:
        self._store = store
        self._thread_lock = thread_lock
        self._flocked = flocked
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        errors: list[BaseException] = []
        if self._flocked:
            try:
                fcntl.flock(self._store.dir_fd, fcntl.LOCK_UN)
            except OSError as error:
                errors.append(error)
        try:
            self._thread_lock.release()
        except RuntimeError as error:
            errors.append(error)
        if errors:
            raise ActionArtifactUncertain("writer lock release uncertain") from errors[0]

    def __enter__(self) -> ArtifactWriterLock:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def validate_host_binding(value: object) -> ActionHostBinding:
    if type(value) is not ActionHostBinding:
        raise ActionArtifactError("invalid host binding")
    if (
        type(value.host_id) is not str
        or _HEX64.fullmatch(value.host_id) is None
        or type(value.boot_session_id) is not str
        or _BOOT.fullmatch(value.boot_session_id) is None
    ):
        raise ActionArtifactError("invalid host binding")
    return value


def validate_artifact_identity(value: object) -> ActionArtifactIdentity:
    if type(value) is not ActionArtifactIdentity:
        raise ActionArtifactError("invalid artifact identity")
    if (
        type(value.action_id) is not str
        or _HEX32.fullmatch(value.action_id) is None
        or value.purpose not in ACTION_PURPOSES
        or type(value.subject_digest) is not str
        or _HEX64.fullmatch(value.subject_digest) is None
        or type(value.client_ref) is not str
        or not value.client_ref
        or len(value.client_ref) > 256
        or type(value.resource) is not str
        or not value.resource
        or len(value.resource) > 2048
        or type(value.host_id) is not str
        or _HEX64.fullmatch(value.host_id) is None
        or type(value.boot_session_id) is not str
        or _BOOT.fullmatch(value.boot_session_id) is None
    ):
        raise ActionArtifactError("invalid artifact identity")
    for name in (
        "project_ref",
        "context_ref",
        "responsibility_ref",
        "operation_ref",
        "owner_ref",
        "generation",
        "relative_path",
    ):
        selected = getattr(value, name)
        if type(selected) is not str or not selected or len(selected) > 512:
            raise ActionArtifactError("invalid artifact identity")
        if name != "relative_path" and _REF.fullmatch(selected) is None:
            raise ActionArtifactError("invalid artifact identity")
    for name in ("root_device", "root_inode", "store_device", "store_inode"):
        selected = getattr(value, name)
        if type(selected) is not int or selected < 0:
            raise ActionArtifactError("invalid artifact identity")
    if value.source_identity is not None and (
        type(value.source_identity) is not str
        or not value.source_identity
        or len(value.source_identity) > 256
    ):
        raise ActionArtifactError("invalid artifact identity")
    return value


def artifact_name(action_id: str, kind: str) -> str:
    if type(action_id) is not str or _HEX32.fullmatch(action_id) is None:
        raise ActionArtifactError("invalid action identity")
    if kind not in ACTION_ARTIFACT_KINDS:
        raise ActionArtifactError("invalid artifact kind")
    return f"{action_id}.{kind}"


def adopt_artifact_store(dir_fd: int) -> ActionArtifactStore:
    """Borrow an already-open directory fd. Never dups or closes it."""

    if type(dir_fd) is not int or dir_fd < 0:
        raise ActionArtifactError("invalid artifact store")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    if (
        not nofollow
        or not directory
        or not cloexec
        or not nonblock
        or os.open not in os.supports_dir_fd
        or os.stat not in os.supports_dir_fd
        or os.unlink not in os.supports_dir_fd
    ):
        raise ActionArtifactError("artifact store unavailable")
    try:
        opened = os.fstat(dir_fd)
    except OSError as error:
        raise ActionArtifactUncertain("artifact store inaccessible") from error
    _check_store_stat(opened)
    if os.get_inheritable(dir_fd):
        raise ActionArtifactError("artifact store descriptor is inheritable")
    return ActionArtifactStore(
        dir_fd=dir_fd,
        device=opened.st_dev,
        inode=opened.st_ino,
        owner_uid=opened.st_uid,
    )


def revalidate_artifact_store(store: ActionArtifactStore) -> ActionArtifactStore:
    if type(store) is not ActionArtifactStore:
        raise ActionArtifactError("invalid artifact store")
    try:
        opened = os.fstat(store.dir_fd)
    except OSError as error:
        raise ActionArtifactUncertain("artifact store inaccessible") from error
    _check_store_stat(opened)
    if (
        opened.st_dev != store.device
        or opened.st_ino != store.inode
        or opened.st_uid != store.owner_uid
        or opened.st_uid != os.geteuid()
    ):
        raise ActionArtifactUncertain("artifact store replaced")
    return store


def acquire_store_writer(store: ActionArtifactStore) -> ArtifactWriterLock:
    """Nonblocking descriptor-bound mutex. Busy is a pre-effect refusal."""

    revalidate_artifact_store(store)
    thread_lock = _thread_lock_for(store)
    if not thread_lock.acquire(blocking=False):
        raise ActionArtifactBusy("store writer busy")
    try:
        fcntl.flock(store.dir_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        thread_lock.release()
        if error.errno in {errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK}:
            raise ActionArtifactBusy("store writer busy") from error
        raise ActionArtifactUncertain("store writer lock unavailable") from error
    return ArtifactWriterLock(store, thread_lock, flocked=True)


def claim_action(
    store: ActionArtifactStore,
    identity: ActionArtifactIdentity,
    *,
    claimed_at_ms: int,
) -> ClaimOutcome:
    """Durable O_EXCL claim. Existing or uncertain claims are not overwritten."""

    store = revalidate_artifact_store(store)
    identity = validate_artifact_identity(identity)
    _assert_store_binding(store, identity)
    if type(claimed_at_ms) is not int or not 0 <= claimed_at_ms < 2**63:
        raise ActionArtifactError("invalid claim timestamp")
    body = {
        "schema": ACTION_CLAIM_SCHEMA,
        "identity": dataclasses.asdict(identity),
        "claimed_at_ms": claimed_at_ms,
        "phase": "claimed",
    }
    try:
        _write_exclusive_json(
            store,
            artifact_name(identity.action_id, "claim"),
            body,
            max_bytes=MAX_CLAIM_BYTES,
        )
    except FileExistsError:
        existing = _read_claim_record(store, identity, require_match=False)
        return ClaimOutcome(
            created=False,
            claim=existing.record if existing.status == "ok" else None,
            uncertain=existing.status != "ok",
        )
    except ActionArtifactUncertain:
        return ClaimOutcome(created=False, claim=None, uncertain=True)
    record = ActionClaimRecord(
        schema=ACTION_CLAIM_SCHEMA,
        identity=identity,
        claimed_at_ms=claimed_at_ms,
        phase="claimed",
    )
    return ClaimOutcome(created=True, claim=record, uncertain=False)


def finalize_action(
    store: ActionArtifactStore,
    identity: ActionArtifactIdentity,
    *,
    effect_state: str,
    observed_sha256: str | None,
    completed_at_ms: int,
    durability: str,
    details: Mapping[str, Any] | None = None,
) -> ActionResultRecord:
    """O_EXCL completion receipt. Never overwrites an existing result."""

    store = revalidate_artifact_store(store)
    identity = validate_artifact_identity(identity)
    _assert_store_binding(store, identity)
    if effect_state not in _EFFECTS or durability not in _DURABILITY:
        raise ActionArtifactError("invalid result classification")
    if durability != "durable" and effect_state == "APPLIED":
        raise ActionArtifactError("uncertain durability cannot be APPLIED")
    if effect_state == "APPLIED" and durability != "durable":
        raise ActionArtifactError("uncertain durability cannot be APPLIED")
    if observed_sha256 is not None and (
        type(observed_sha256) is not str or _HEX64.fullmatch(observed_sha256) is None
    ):
        raise ActionArtifactError("invalid observed digest")
    if type(completed_at_ms) is not int or not 0 <= completed_at_ms < 2**63:
        raise ActionArtifactError("invalid result timestamp")
    payload = _closed_details(details)
    body = {
        "schema": ACTION_RESULT_SCHEMA,
        "identity": dataclasses.asdict(identity),
        "effect_state": effect_state,
        "observed_sha256": observed_sha256,
        "completed_at_ms": completed_at_ms,
        "durability": durability,
        "details": payload,
    }
    _write_exclusive_json(
        store,
        artifact_name(identity.action_id, "result"),
        body,
        max_bytes=MAX_RESULT_BYTES,
    )
    return ActionResultRecord(
        schema=ACTION_RESULT_SCHEMA,
        identity=identity,
        effect_state=effect_state,
        observed_sha256=observed_sha256,
        completed_at_ms=completed_at_ms,
        durability=durability,
        details=payload,
    )


def write_action_blob(
    store: ActionArtifactStore,
    action_id: str,
    kind: str,
    payload: bytes,
) -> None:
    """O_EXCL regular blob for command stdout/stderr reuse. Same fd rules."""

    if kind not in {"stdout", "stderr"}:
        raise ActionArtifactError("invalid artifact kind")
    if type(payload) is not bytes or len(payload) > MAX_BLOB_BYTES:
        raise ActionArtifactError("invalid artifact blob")
    store = revalidate_artifact_store(store)
    _write_exclusive_bytes(
        store,
        artifact_name(action_id, kind),
        payload,
        max_bytes=MAX_BLOB_BYTES,
    )


def read_action_claim(
    store: ActionArtifactStore,
    identity: ActionArtifactIdentity,
) -> ActionClaimRecord | None:
    """Strict claim read. Missing is None; corruption is uncertain."""

    result = _read_claim_record(store, identity, require_match=True)
    if result.status == "missing":
        return None
    if result.status != "ok" or result.record is None:
        raise ActionArtifactUncertain("claim is unreadable")
    return result.record


def read_action_result(
    store: ActionArtifactStore,
    identity: ActionArtifactIdentity,
) -> ActionResultRecord | None:
    result = _read_result_record(store, identity, require_match=True)
    if result.status == "missing":
        return None
    if result.status != "ok" or result.record is None:
        raise ActionArtifactUncertain("result is unreadable")
    return result.record


def read_action_blob(
    store: ActionArtifactStore,
    action_id: str,
    kind: str,
    *,
    max_bytes: int = MAX_BLOB_BYTES,
) -> bytes | None:
    if kind not in {"stdout", "stderr"}:
        raise ActionArtifactError("invalid artifact kind")
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BLOB_BYTES:
        raise ActionArtifactError("invalid artifact bound")
    store = revalidate_artifact_store(store)
    raw = _read_regular_file(
        store,
        artifact_name(action_id, kind),
        max_bytes=max_bytes,
        missing_ok=True,
    )
    return raw


def classify_action(
    store: ActionArtifactStore,
    identity: ActionArtifactIdentity,
) -> ActionClassification:
    """Read-only reconciliation. Never creates a claim or infers from project bytes."""

    try:
        revalidate_artifact_store(store)
        identity = validate_artifact_identity(identity)
        _assert_store_binding(store, identity)
    except (ActionArtifactError, ActionArtifactUncertain):
        return ActionClassification(
            effect_state="EFFECT_UNKNOWN",
            claim=None,
            result=None,
            store_valid=False,
        )
    claim_read = _read_claim_record(store, identity, require_match=True)
    result_read = _read_result_record(store, identity, require_match=True)
    if claim_read.status == "uncertain" or result_read.status == "uncertain":
        return ActionClassification(
            effect_state="EFFECT_UNKNOWN",
            claim=claim_read.record if claim_read.status == "ok" else None,
            result=result_read.record if result_read.status == "ok" else None,
            store_valid=True,
        )
    claim = claim_read.record if claim_read.status == "ok" else None
    result = result_read.record if result_read.status == "ok" else None
    if result is not None:
        effect = (
            result.effect_state
            if result.durability == "durable" and result.effect_state in _EFFECTS
            else "EFFECT_UNKNOWN"
        )
        return ActionClassification(
            effect_state=effect,
            claim=claim,
            result=result,
            store_valid=True,
        )
    if claim is not None:
        return ActionClassification(
            effect_state="EFFECT_UNKNOWN",
            claim=claim,
            result=None,
            store_valid=True,
        )
    return ActionClassification(
        effect_state="EFFECT_UNKNOWN",
        claim=None,
        result=None,
        store_valid=True,
    )


def _check_store_stat(value: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(value.st_mode)
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) & 0o022
    ):
        raise ActionArtifactError("artifact store security refused")


def _assert_store_binding(
    store: ActionArtifactStore, identity: ActionArtifactIdentity
) -> None:
    if (
        store.device != identity.store_device
        or store.inode != identity.store_inode
        or store.owner_uid != os.geteuid()
    ):
        raise ActionArtifactUncertain("artifact store binding changed")


def _thread_lock_for(store: ActionArtifactStore) -> threading.Lock:
    key = (store.device, store.inode)
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.Lock())


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _dumps(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _closed_details(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if type(value) is not dict:
        raise ActionArtifactError("invalid result details")
    raw = _dumps(dict(value))
    if len(raw) > MAX_DETAILS_BYTES:
        raise ActionArtifactError("result details too large")
    parsed = json.loads(raw.decode("utf-8"))
    if type(parsed) is not dict:
        raise ActionArtifactError("invalid result details")
    return parsed


def _write_all(fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(fd, payload[offset:])
        if type(written) is not int or written <= 0:
            raise OSError("short write")
        offset += written


def _write_exclusive_json(
    store: ActionArtifactStore,
    name: str,
    body: dict[str, Any],
    *,
    max_bytes: int,
) -> None:
    payload = _dumps(body)
    if len(payload) > max_bytes:
        raise ActionArtifactError("artifact payload too large")
    _write_exclusive_bytes(store, name, payload, max_bytes=max_bytes)


def _write_exclusive_bytes(
    store: ActionArtifactStore,
    name: str,
    payload: bytes,
    *,
    max_bytes: int,
) -> None:
    if len(payload) > max_bytes:
        raise ActionArtifactError("artifact payload too large")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow | cloexec
    fd = -1
    created = False
    try:
        fd = os.open(name, flags, 0o600, dir_fd=store.dir_fd)
        created = True
        _write_all(fd, payload)
        os.fsync(fd)
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) & 0o022
        ):
            raise ActionArtifactUncertain("artifact identity refused")
        named = os.stat(name, dir_fd=store.dir_fd, follow_symlinks=False)
        if _file_identity(named) != _file_identity(opened):
            raise ActionArtifactUncertain("artifact name drifted")
        os.fsync(store.dir_fd)
    except FileExistsError:
        raise
    except (OSError, TypeError, ValueError, OverflowError) as error:
        raise ActionArtifactUncertain("artifact write uncertain") from error
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError as error:
                if created:
                    raise ActionArtifactUncertain("artifact close uncertain") from error


def _read_regular_file(
    store: ActionArtifactStore,
    name: str,
    *,
    max_bytes: int,
    missing_ok: bool,
) -> bytes | None:
    revalidate_artifact_store(store)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    fd = -1
    try:
        try:
            before = os.stat(name, dir_fd=store.dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise ActionArtifactUncertain("artifact missing") from None
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.geteuid()
            or before.st_uid != store.owner_uid
            or stat.S_IMODE(before.st_mode) & 0o022
            or before.st_size > max_bytes
        ):
            raise ActionArtifactUncertain("artifact identity refused")
        fd = os.open(
            name, os.O_RDONLY | nofollow | nonblock | cloexec, dir_fd=store.dir_fd
        )
        opened = os.fstat(fd)
        if _file_identity(opened) != _file_identity(before):
            raise ActionArtifactUncertain("artifact identity changed")
        chunks: list[bytes] = []
        count = 0
        while True:
            chunk = os.read(fd, min(65536, before.st_size - count + 1))
            if not chunk:
                break
            count += len(chunk)
            if count > before.st_size or count > max_bytes:
                raise ActionArtifactUncertain("artifact changed during read")
            chunks.append(chunk)
        if count != before.st_size:
            raise ActionArtifactUncertain("artifact changed during read")
        after_fd = os.fstat(fd)
        after_path = os.stat(name, dir_fd=store.dir_fd, follow_symlinks=False)
        if (
            _file_identity(after_fd) != _file_identity(before)
            or _file_identity(after_path) != _file_identity(before)
        ):
            raise ActionArtifactUncertain("artifact identity changed")
        return b"".join(chunks)
    except ActionArtifactUncertain:
        raise
    except FileNotFoundError:
        if missing_ok:
            return None
        raise ActionArtifactUncertain("artifact missing") from None
    except (OSError, TypeError, ValueError, OverflowError) as error:
        raise ActionArtifactUncertain("artifact read uncertain") from error
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError as error:
                raise ActionArtifactUncertain("artifact close uncertain") from error


@dataclasses.dataclass(frozen=True)
class _RecordRead:
    status: str
    record: Any | None


def _parse_identity(raw: object) -> ActionArtifactIdentity:
    if type(raw) is not dict:
        raise ActionArtifactUncertain("invalid identity")
    names = {field.name for field in dataclasses.fields(ActionArtifactIdentity)}
    if set(raw) != names:
        raise ActionArtifactUncertain("invalid identity")
    try:
        value = ActionArtifactIdentity(**raw)
    except (TypeError, ValueError) as error:
        raise ActionArtifactUncertain("invalid identity") from error
    try:
        return validate_artifact_identity(value)
    except ActionArtifactError as error:
        raise ActionArtifactUncertain("invalid identity") from error


def _read_claim_record(
    store: ActionArtifactStore,
    identity: ActionArtifactIdentity,
    *,
    require_match: bool,
) -> _RecordRead:
    try:
        raw = _read_regular_file(
            store,
            artifact_name(identity.action_id, "claim"),
            max_bytes=MAX_CLAIM_BYTES,
            missing_ok=True,
        )
    except ActionArtifactUncertain:
        return _RecordRead(status="uncertain", record=None)
    if raw is None:
        return _RecordRead(status="missing", record=None)
    try:
        body = json.loads(raw.decode("utf-8"))
        if type(body) is not dict or set(body) != {
            "schema",
            "identity",
            "claimed_at_ms",
            "phase",
        }:
            raise ActionArtifactUncertain("invalid claim")
        if body["schema"] != ACTION_CLAIM_SCHEMA or body["phase"] != "claimed":
            raise ActionArtifactUncertain("invalid claim")
        if type(body["claimed_at_ms"]) is not int or not 0 <= body["claimed_at_ms"] < 2**63:
            raise ActionArtifactUncertain("invalid claim")
        parsed = _parse_identity(body["identity"])
        if require_match and parsed != identity:
            raise ActionArtifactUncertain("claim identity mismatch")
        record = ActionClaimRecord(
            schema=ACTION_CLAIM_SCHEMA,
            identity=parsed,
            claimed_at_ms=body["claimed_at_ms"],
            phase="claimed",
        )
        return _RecordRead(status="ok", record=record)
    except (ActionArtifactUncertain, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return _RecordRead(status="uncertain", record=None)


def _read_result_record(
    store: ActionArtifactStore,
    identity: ActionArtifactIdentity,
    *,
    require_match: bool,
) -> _RecordRead:
    try:
        raw = _read_regular_file(
            store,
            artifact_name(identity.action_id, "result"),
            max_bytes=MAX_RESULT_BYTES,
            missing_ok=True,
        )
    except ActionArtifactUncertain:
        return _RecordRead(status="uncertain", record=None)
    if raw is None:
        return _RecordRead(status="missing", record=None)
    try:
        body = json.loads(raw.decode("utf-8"))
        if type(body) is not dict or set(body) != {
            "schema",
            "identity",
            "effect_state",
            "observed_sha256",
            "completed_at_ms",
            "durability",
            "details",
        }:
            raise ActionArtifactUncertain("invalid result")
        if (
            body["schema"] != ACTION_RESULT_SCHEMA
            or body["effect_state"] not in _EFFECTS
            or body["durability"] not in _DURABILITY
            or type(body["completed_at_ms"]) is not int
            or not 0 <= body["completed_at_ms"] < 2**63
            or (body["observed_sha256"] is not None and not (
                type(body["observed_sha256"]) is str
                and _HEX64.fullmatch(body["observed_sha256"])
            ))
            or type(body["details"]) is not dict
        ):
            raise ActionArtifactUncertain("invalid result")
        parsed = _parse_identity(body["identity"])
        if require_match and parsed != identity:
            raise ActionArtifactUncertain("result identity mismatch")
        record = ActionResultRecord(
            schema=ACTION_RESULT_SCHEMA,
            identity=parsed,
            effect_state=body["effect_state"],
            observed_sha256=body["observed_sha256"],
            completed_at_ms=body["completed_at_ms"],
            durability=body["durability"],
            details=body["details"],
        )
        return _RecordRead(status="ok", record=record)
    except (ActionArtifactUncertain, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return _RecordRead(status="uncertain", record=None)


__all__ = [
    "ACTION_ARTIFACT_KINDS",
    "ACTION_CLAIM_SCHEMA",
    "ACTION_PURPOSE_CLOSED_COMMAND",
    "ACTION_PURPOSE_TEXT_PATCH",
    "ACTION_PURPOSES",
    "ACTION_RESULT_SCHEMA",
    "MAX_BLOB_BYTES",
    "MAX_CLAIM_BYTES",
    "MAX_RESULT_BYTES",
    "ActionArtifactBusy",
    "ActionArtifactError",
    "ActionArtifactIdentity",
    "ActionArtifactStore",
    "ActionArtifactUncertain",
    "ActionClaimRecord",
    "ActionClassification",
    "ActionHostBinding",
    "ActionResultRecord",
    "ArtifactWriterLock",
    "ClaimOutcome",
    "acquire_store_writer",
    "adopt_artifact_store",
    "artifact_name",
    "claim_action",
    "classify_action",
    "finalize_action",
    "read_action_blob",
    "read_action_claim",
    "read_action_result",
    "revalidate_artifact_store",
    "validate_artifact_identity",
    "validate_host_binding",
    "write_action_blob",
]
