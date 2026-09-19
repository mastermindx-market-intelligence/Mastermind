"""Descriptor-relative prepared text patch owner for Workbench Action.

The port is deliberately narrower than a filesystem API. Preparation is
read-only. Commit consumes one signed prepared action and performs at most one
same-directory atomic file publication after a durable per-action claim.
Reconciliation never replays a write and never infers an effect from current
project bytes alone.  An action with no artifact at all is ``NOT_APPLIED`` only
when the entry point's durable pre-dispatch admission ledger proves the commit
was refused before dispatch and never accepted for that exact reference, and
the source still reads as never patched; absent that proof it stays
``EFFECT_UNKNOWN``.

Attended F0 write paths are direct children of the owned project root.
Arbitrary POSIX rename is publication, not compare-and-swap against a
non-cooperating same-UID writer. Exclusive Workbench custody is the contract
for that race; extra stat and advisory flock do not close it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import os
import secrets
import stat
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from .action_artifacts import (
    ACTION_PURPOSE_TEXT_PATCH,
    ActionArtifactBusy,
    ActionArtifactError,
    ActionArtifactIdentity,
    ActionArtifactStore,
    ActionArtifactUncertain,
    ActionHostBinding,
    acquire_store_writer,
    claim_action,
    classify_action,
    finalize_action,
    revalidate_artifact_store,
    validate_host_binding,
)
from .contracts import (
    ACTION_TOKEN_PURPOSE,
    ACTION_TOKEN_SCHEMA,
    MAX_ACTION_TTL_MS,
    MAX_PATCH_TEXT_BYTES,
    ActionCaller,
    ActionContractError,
    ActionScope,
    ActionTokenCodec,
    PreparedTextPatch,
    ProjectActionBinding,
    validate_action_caller,
    validate_action_scope,
    validate_relative_path,
)

MAX_FILE_BYTES = 1024 * 1024
_EFFECTS = frozenset({"NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"})
_REQUEST_KEYS = frozenset(
    {"project_ref", "relative_path", "mode", "expected_sha256", "old_text", "new_text"}
)
_HEX64 = frozenset("0123456789abcdef")


class ProjectActionRefused(Exception):
    _CODES = frozenset(
        {
            "PROJECT_ACTION_REFUSED",
            "ACTION_BINDING_CHANGED",
            "ACTION_PREIMAGE_MISMATCH",
            "ACTION_SOURCE_CHANGED",
            "ACTION_INVALID",
            "ACTION_EXPIRED",
            "ACTION_UNAVAILABLE",
            "ARTIFACT_INVALID",
            "ARTIFACT_EXPIRED",
            "ARTIFACT_BINDING_CHANGED",
            "ARTIFACT_UNAVAILABLE",
            "ARTIFACT_RANGE_INVALID",
        }
    )

    def __init__(self, code: str = "PROJECT_ACTION_REFUSED") -> None:
        if code not in self._CODES:
            raise ValueError("unknown project action refusal")
        self.code = code
        super().__init__(code)


ActionBindingResolver = Callable[[ActionCaller, str], ProjectActionBinding | None]
ActionExecutor = Callable[[Callable[[], dict[str, Any]]], Awaitable[dict[str, Any]]]
# Durable pre-dispatch admission verdict for one exact action reference, owned
# by the entry point that audits admission.  Only this exact verdict may ever
# turn artifact absence into NOT_APPLIED.
AdmissionEvidence = Callable[[object], str]
ADMISSION_REFUSED_ONLY = "REFUSED_ONLY"


@dataclasses.dataclass(frozen=True)
class _FileSnapshot:
    raw: bytes
    sha256: str
    mode: int
    identity: tuple[int, ...]


def _publication_gate(_prepared: PreparedTextPatch) -> None:
    """Test hook. Production is a no-op; never used as a fallback owner."""

    return None


def _now(clock_ms: Callable[[], int]) -> int:
    try:
        value = clock_ms()
    except Exception as error:
        raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
    if type(value) is not int or not 0 <= value < 2**63:
        raise ProjectActionRefused("ACTION_UNAVAILABLE")
    return value


def _digest_ok(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in _HEX64 for character in value)
    )


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


def _encode_source_identity(value: tuple[int, ...]) -> str:
    return ":".join(str(item) for item in value)


def _dir_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid


def _binding_key(value: ProjectActionBinding) -> tuple[object, ...]:
    scope = value.scope
    return (
        value.caller,
        value.project_ref,
        scope.root_device,
        scope.root_inode,
        scope.context_ref,
        scope.responsibility_ref,
        scope.operation_ref,
        scope.owner_ref,
        scope.generation,
        scope.allowed_paths,
        scope.expires_at_ms,
        scope.committed_head,
    )


def _assert_direct_write_path(value: str) -> str:
    validate_relative_path(value)
    if "/" in value or value.startswith("."):
        raise ProjectActionRefused("ACTION_INVALID")
    return value


def _assert_action_fresh(prepared: PreparedTextPatch, now_ms: int) -> None:
    if prepared.expires_at_ms <= now_ms:
        raise ProjectActionRefused("ACTION_EXPIRED")


def _artifact_identity(prepared: PreparedTextPatch) -> ActionArtifactIdentity:
    return ActionArtifactIdentity(
        action_id=prepared.action_id,
        purpose=ACTION_PURPOSE_TEXT_PATCH,
        subject_digest=prepared.subject_digest,
        client_ref=prepared.client_ref,
        resource=prepared.resource,
        project_ref=prepared.project_ref,
        context_ref=prepared.context_ref,
        responsibility_ref=prepared.responsibility_ref,
        operation_ref=prepared.operation_ref,
        owner_ref=prepared.owner_ref,
        generation=prepared.generation,
        root_device=prepared.root_device,
        root_inode=prepared.root_inode,
        store_device=prepared.artifact_store_device,
        store_inode=prepared.artifact_store_inode,
        host_id=prepared.host_id,
        boot_session_id=prepared.boot_session_id,
        relative_path=prepared.relative_path,
        source_identity=prepared.source_identity,
    )


def _current_binding(
    *,
    caller: ActionCaller,
    project_ref: str,
    resolve_binding: ActionBindingResolver,
    clock_ms: Callable[[], int],
) -> ProjectActionBinding:
    validate_action_caller(caller)
    timestamp = _now(clock_ms)
    if timestamp >= caller.expires_at * 1000:
        raise ProjectActionRefused("ACTION_BINDING_CHANGED")
    try:
        value = resolve_binding(dataclasses.replace(caller), project_ref)
    except Exception as error:
        raise ProjectActionRefused("ACTION_BINDING_CHANGED") from error
    if (
        type(value) is not ProjectActionBinding
        or type(value.caller) is not ActionCaller
        or value.caller != caller
        or type(value.project_ref) is not str
        or value.project_ref != project_ref
    ):
        raise ProjectActionRefused("ACTION_BINDING_CHANGED")
    try:
        validate_action_scope(value.scope, now_ms=timestamp)
    except ActionContractError as error:
        raise ProjectActionRefused("ACTION_BINDING_CHANGED") from error
    if timestamp >= min(value.scope.expires_at_ms, caller.expires_at * 1000):
        raise ProjectActionRefused("ACTION_BINDING_CHANGED")
    return value


def _assert_action_binding(
    prepared: PreparedTextPatch, binding: ProjectActionBinding
) -> None:
    scope = binding.scope
    caller = binding.caller
    if (
        caller.subject_digest != prepared.subject_digest
        or caller.client_ref != prepared.client_ref
        or caller.resource != prepared.resource
        or binding.project_ref != prepared.project_ref
        or scope.context_ref != prepared.context_ref
        or scope.responsibility_ref != prepared.responsibility_ref
        or scope.operation_ref != prepared.operation_ref
        or scope.owner_ref != prepared.owner_ref
        or scope.generation != prepared.generation
        or scope.root_device != prepared.root_device
        or scope.root_inode != prepared.root_inode
        or scope.committed_head != prepared.committed_head
        or prepared.relative_path not in scope.allowed_paths
    ):
        raise ProjectActionRefused("ACTION_BINDING_CHANGED")


def _assert_apply_host(
    prepared: PreparedTextPatch,
    *,
    store: ActionArtifactStore,
    host: ActionHostBinding,
) -> None:
    try:
        revalidate_artifact_store(store)
        validate_host_binding(host)
    except (ActionArtifactError, ActionArtifactUncertain) as error:
        raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
    if (
        host.host_id != prepared.host_id
        or host.boot_session_id != prepared.boot_session_id
        or store.device != prepared.artifact_store_device
        or store.inode != prepared.artifact_store_inode
    ):
        raise ProjectActionRefused("ACTION_BINDING_CHANGED")


def _open_parent(
    store: ActionArtifactStore, scope: ActionScope, relative_path: str
) -> tuple[list[int], int, str]:
    validate_relative_path(relative_path)
    if relative_path not in scope.allowed_paths:
        raise ProjectActionRefused()
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if (
        not nofollow
        or not directory
        or not cloexec
        or os.open not in os.supports_dir_fd
        or os.stat not in os.supports_dir_fd
        or os.unlink not in os.supports_dir_fd
    ):
        raise ProjectActionRefused("ACTION_UNAVAILABLE")
    fds: list[int] = []
    try:
        root = os.dup(scope.root_fd)
        fds.append(root)
        root_stat = os.fstat(root)
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or (root_stat.st_dev, root_stat.st_ino)
            != (scope.root_device, scope.root_inode)
        ):
            raise ProjectActionRefused("ACTION_BINDING_CHANGED")
        parent = root
        for atom in relative_path.split("/")[:-1]:
            before = os.stat(atom, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode) or before.st_dev != scope.root_device:
                raise ProjectActionRefused("ACTION_SOURCE_CHANGED")
            child = os.open(
                atom, os.O_RDONLY | nofollow | directory | cloexec, dir_fd=parent
            )
            fds.append(child)
            opened = os.fstat(child)
            if _dir_identity(before) != _dir_identity(opened):
                raise ProjectActionRefused("ACTION_SOURCE_CHANGED")
            parent = child
        return fds, parent, relative_path.split("/")[-1]
    except BaseException:
        _close_readers(store, fds)
        raise


def _close_readers(store: ActionArtifactStore, fds: list[int]) -> None:
    failed = False
    for fd in reversed(fds):
        try:
            os.close(fd)
        except OSError:
            failed = True
            store.mark_cleanup_uncertain("project_reader_close")
    if failed:
        raise ProjectActionRefused("ACTION_UNAVAILABLE")


def _read_leaf(
    store: ActionArtifactStore, scope: ActionScope, relative_path: str, *, allow_absent: bool
) -> _FileSnapshot | None:
    fds, parent, leaf = _open_parent(store, scope, relative_path)
    file_fd = -1
    try:
        try:
            before = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            if allow_absent:
                return None
            raise ProjectActionRefused("ACTION_SOURCE_CHANGED") from None
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_dev != scope.root_device
            or before.st_size > MAX_FILE_BYTES
        ):
            raise ProjectActionRefused("ACTION_SOURCE_CHANGED")
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        nonblock = getattr(os, "O_NONBLOCK", 0)
        cloexec = getattr(os, "O_CLOEXEC", 0)
        if not nonblock:
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
        file_fd = os.open(
            leaf, os.O_RDONLY | nofollow | nonblock | cloexec, dir_fd=parent
        )
        opened = os.fstat(file_fd)
        if _file_identity(opened) != _file_identity(before):
            raise ProjectActionRefused("ACTION_SOURCE_CHANGED")
        chunks: list[bytes] = []
        count = 0
        while True:
            chunk = os.read(file_fd, min(65536, before.st_size - count + 1))
            if not chunk:
                break
            count += len(chunk)
            if count > before.st_size or count > MAX_FILE_BYTES:
                raise ProjectActionRefused("ACTION_SOURCE_CHANGED")
            chunks.append(chunk)
        if count != before.st_size:
            raise ProjectActionRefused("ACTION_SOURCE_CHANGED")
        after_fd = os.fstat(file_fd)
        after_path = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        if (
            _file_identity(after_fd) != _file_identity(before)
            or _file_identity(after_path) != _file_identity(before)
        ):
            raise ProjectActionRefused("ACTION_SOURCE_CHANGED")
        raw = b"".join(chunks)
        return _FileSnapshot(
            raw=raw,
            sha256=hashlib.sha256(raw).hexdigest(),
            mode=stat.S_IMODE(before.st_mode),
            identity=_file_identity(before),
        )
    except ProjectActionRefused:
        raise
    except (OSError, TypeError, ValueError, OverflowError) as error:
        raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
    finally:
        _close_readers(store, fds + ([file_fd] if file_fd >= 0 else []))


def _candidate_from_snapshot(
    snapshot: _FileSnapshot, *, old_text: str, new_text: str
) -> bytes:
    try:
        current = snapshot.raw.decode("utf-8")
    except UnicodeError as error:
        raise ProjectActionRefused("ACTION_SOURCE_CHANGED") from error
    if "\x00" in current or current.count(old_text) != 1:
        raise ProjectActionRefused("ACTION_PREIMAGE_MISMATCH")
    candidate = current.replace(old_text, new_text, 1).encode("utf-8")
    if len(candidate) > MAX_FILE_BYTES:
        raise ProjectActionRefused("ACTION_INVALID")
    return candidate


def _write_all(fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(fd, payload[offset:])
        if type(written) is not int or written <= 0:
            raise OSError("short write")
        offset += written


def _observe(
    store: ActionArtifactStore, scope: ActionScope, relative_path: str
) -> str | None:
    snapshot = _read_leaf(store, scope, relative_path, allow_absent=True)
    return None if snapshot is None else snapshot.sha256


def _receipt(
    *,
    effect_state: str,
    observed_sha256: str | None,
) -> dict[str, Any]:
    return {"effect_state": effect_state, "observed_sha256": observed_sha256}


def _finalize_receipt(
    store: ActionArtifactStore,
    prepared: PreparedTextPatch,
    *,
    effect_state: str,
    observed_sha256: str | None,
    completed_at_ms: int,
    durability: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        record = finalize_action(
            store,
            _artifact_identity(prepared),
            effect_state=effect_state,
            observed_sha256=observed_sha256,
            completed_at_ms=completed_at_ms,
            durability=durability,
            details=details,
        )
        return _receipt(
            effect_state=record.effect_state,
            observed_sha256=observed_sha256,
        )
    except (ActionArtifactError, ActionArtifactUncertain, FileExistsError):
        return _receipt(effect_state="EFFECT_UNKNOWN", observed_sha256=observed_sha256)


def _publish_candidate(
    *,
    scope: ActionScope,
    prepared: PreparedTextPatch,
    candidate: bytes,
    mode: int,
    confirm_binding: Callable[[], ActionScope],
    clock_ms: Callable[[], int],
    store: ActionArtifactStore,
) -> dict[str, Any]:
    _assert_direct_write_path(prepared.relative_path)
    fds, parent, leaf = _open_parent(store, scope, prepared.relative_path)
    temp_fd = -1
    temp_name = f".mmx-workbench-action-{prepared.action_id}.tmp"
    created_temp = False
    temp_identity: tuple[int, ...] | None = None
    effect_started = False
    close_uncertain = False
    cleanup_uncertain = False
    pending: dict[str, Any] | None = None
    refusal: ProjectActionRefused | None = None

    def _pending(
        effect_state: str,
        observed_sha256: str | None,
        durability: str,
        reason: str,
    ) -> None:
        nonlocal pending
        pending = {
            "effect_state": effect_state,
            "observed_sha256": observed_sha256,
            "durability": durability,
            "reason": reason,
        }

    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            temp_fd = os.open(temp_name, flags, 0o600, dir_fd=parent)
        except FileExistsError:
            observed = _observe(store, confirm_binding(), prepared.relative_path)
            _pending("EFFECT_UNKNOWN", observed, "uncertain", "temp_collision")
        else:
            created_temp = True
            # Retain ownership even if the subsequent write/fsync fails.
            temp_identity = _file_identity(os.fstat(temp_fd))
            _write_all(temp_fd, candidate)
            os.fchmod(temp_fd, mode)
            os.fsync(temp_fd)
            temp_stat = os.fstat(temp_fd)
            if not stat.S_ISREG(temp_stat.st_mode) or temp_stat.st_nlink != 1:
                raise ProjectActionRefused("ACTION_UNAVAILABLE")
            temp_identity = _file_identity(temp_stat)
            named = os.stat(temp_name, dir_fd=parent, follow_symlinks=False)
            if _file_identity(named) != temp_identity:
                created_temp = False
                observed = _observe(store, confirm_binding(), prepared.relative_path)
                _pending("EFFECT_UNKNOWN", observed, "uncertain", "temp_identity_drift")
            else:
                current_scope = confirm_binding()
                if (
                    current_scope.root_device != scope.root_device
                    or current_scope.root_inode != scope.root_inode
                ):
                    raise ProjectActionRefused("ACTION_BINDING_CHANGED")
                _assert_action_fresh(prepared, _now(clock_ms))
                current = _read_leaf(
                    store,
                    current_scope,
                    prepared.relative_path,
                    allow_absent=prepared.mode == "CREATE",
                )
                if prepared.mode == "CREATE":
                    if current is not None:
                        _pending(
                            "EFFECT_UNKNOWN",
                            current.sha256,
                            "durable",
                            "create_target_exists",
                        )
                    elif os.link not in os.supports_dir_fd:
                        raise ProjectActionRefused("ACTION_UNAVAILABLE")
                elif (
                    current is None
                    or current.sha256 != prepared.preimage_sha256
                    or _encode_source_identity(current.identity)
                    != prepared.source_identity
                ):
                    observed = None if current is None else current.sha256
                    _pending(
                        "EFFECT_UNKNOWN",
                        observed,
                        "durable",
                        "preimage_or_source_changed",
                    )
                else:
                    expected = _candidate_from_snapshot(
                        current,
                        old_text=prepared.old_text or "",
                        new_text=prepared.new_text,
                    )
                    if hashlib.sha256(expected).hexdigest() != prepared.postimage_sha256:
                        raise ProjectActionRefused("ACTION_INVALID")
                    if os.rename not in os.supports_dir_fd:
                        raise ProjectActionRefused("ACTION_UNAVAILABLE")
                if pending is None:
                    _publication_gate(prepared)
                    _assert_action_fresh(prepared, _now(clock_ms))
                    confirm_binding()
                    named = os.stat(temp_name, dir_fd=parent, follow_symlinks=False)
                    held = os.fstat(temp_fd)
                    if (
                        temp_identity is None
                        or _file_identity(named) != temp_identity
                        or _file_identity(held) != temp_identity
                    ):
                        created_temp = False
                        observed = _observe(store, current_scope, prepared.relative_path)
                        _pending(
                            "EFFECT_UNKNOWN",
                            observed,
                            "uncertain",
                            "temp_replaced",
                        )
                    else:
                        if prepared.mode == "CREATE":
                            os.link(
                                temp_name,
                                leaf,
                                src_dir_fd=parent,
                                dst_dir_fd=parent,
                                follow_symlinks=False,
                            )
                        else:
                            os.rename(
                                temp_name,
                                leaf,
                                src_dir_fd=parent,
                                dst_dir_fd=parent,
                            )
                        effect_started = True
                        if created_temp and temp_identity is not None:
                            try:
                                named = os.stat(
                                    temp_name, dir_fd=parent, follow_symlinks=False
                                )
                                if (named.st_dev, named.st_ino) == temp_identity[:2]:
                                    os.unlink(temp_name, dir_fd=parent)
                                    created_temp = False
                            except FileNotFoundError:
                                created_temp = False
                            except OSError:
                                cleanup_uncertain = True
                        try:
                            os.fsync(parent)
                        except OSError:
                            final = _read_leaf(
                                store,
                                confirm_binding(),
                                prepared.relative_path,
                                allow_absent=True,
                            )
                            observed = None if final is None else final.sha256
                            _pending(
                                "EFFECT_UNKNOWN",
                                observed,
                                "uncertain",
                                "directory_fsync_failed",
                            )
                        else:
                            final_scope = confirm_binding()
                            final = _read_leaf(
                                store,
                                final_scope,
                                prepared.relative_path,
                                allow_absent=True,
                            )
                            observed = None if final is None else final.sha256
                            if observed != prepared.postimage_sha256:
                                _pending(
                                    "EFFECT_UNKNOWN",
                                    observed,
                                    "uncertain",
                                    "readback_mismatch",
                                )
                            else:
                                _pending(
                                    "APPLIED",
                                    observed,
                                    "durable",
                                    "published",
                                )
    except ProjectActionRefused as error:
        if pending is None and effect_started:
            observed = None
            try:
                observed = _observe(store, scope, prepared.relative_path)
            except ProjectActionRefused:
                observed = None
            _pending("EFFECT_UNKNOWN", observed, "uncertain", "refused_after_effect")
        elif pending is None and error.code == "ACTION_EXPIRED":
            observed = None
            try:
                observed = _observe(store, scope, prepared.relative_path)
            except ProjectActionRefused:
                observed = None
            _pending("NOT_APPLIED", observed, "durable", "expired_before_publication")
        elif pending is None:
            refusal = error
    except (OSError, TypeError, ValueError, OverflowError) as error:
        if pending is None and effect_started:
            _pending("EFFECT_UNKNOWN", None, "uncertain", "publish_uncertain")
        elif pending is None:
            refusal = ProjectActionRefused("ACTION_UNAVAILABLE")
            refusal.__cause__ = error
    finally:
        if temp_fd >= 0:
            try:
                os.close(temp_fd)
            except OSError:
                close_uncertain = True
        if created_temp and temp_identity is None:
            cleanup_uncertain = True
        if created_temp and temp_identity is not None:
            try:
                named = os.stat(temp_name, dir_fd=parent, follow_symlinks=False)
                if (named.st_dev, named.st_ino) == temp_identity[:2]:
                    os.unlink(temp_name, dir_fd=parent)
                    os.fsync(parent)
            except FileNotFoundError:
                pass
            except OSError:
                cleanup_uncertain = True
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                close_uncertain = True

    if close_uncertain:
        store.mark_cleanup_uncertain("project_writer_close")
    if cleanup_uncertain:
        store.mark_cleanup_uncertain("project_temp_cleanup")

    if pending is not None:
        effect = pending["effect_state"]
        durability = pending["durability"]
        reason = pending["reason"]
        if store.cleanup_uncertain:
            effect = "EFFECT_UNKNOWN"
            durability = "uncertain"
            reason = "cleanup_uncertain"
        return _finalize_receipt(
            store,
            prepared,
            effect_state=effect,
            observed_sha256=pending["observed_sha256"],
            completed_at_ms=_now(clock_ms),
            durability=durability,
            details={"reason": reason},
        )
    if refusal is not None:
        raise refusal
    raise ProjectActionRefused("ACTION_UNAVAILABLE")


def create_text_patch_port(
    *,
    resolve_binding: ActionBindingResolver,
    clock_ms: Callable[[], int],
    run_io: ActionExecutor,
    token_codec: ActionTokenCodec,
    artifact_store: ActionArtifactStore,
    host: ActionHostBinding,
    action_ttl_ms: int = MAX_ACTION_TTL_MS,
    admission_evidence: AdmissionEvidence | None = None,
):
    """Create prepare/commit/reconcile callbacks over existing owner services.

    ``admission_evidence`` is the entry point's durable pre-dispatch admission
    reader.  Without it (the OAuth adapter), artifact absence stays
    ``EFFECT_UNKNOWN`` exactly as before.
    """

    if not all(callable(value) for value in (resolve_binding, clock_ms, run_io)):
        raise TypeError("explicit binding, clock and I/O integration required")
    if admission_evidence is not None and not callable(admission_evidence):
        raise TypeError("admission evidence must be callable")
    if not isinstance(token_codec, ActionTokenCodec):
        raise TypeError("explicit action token codec required")
    if type(action_ttl_ms) is not int or not 1000 <= action_ttl_ms <= MAX_ACTION_TTL_MS:
        raise ValueError("action ttl is outside the closed F0 range")
    try:
        store = revalidate_artifact_store(artifact_store)
        host_binding = validate_host_binding(host)
    except (ActionArtifactError, ActionArtifactUncertain) as error:
        raise TypeError("explicit host-owned artifact store and host binding required") from error

    def _live_store() -> ActionArtifactStore:
        try:
            return revalidate_artifact_store(store)
        except (ActionArtifactError, ActionArtifactUncertain) as error:
            raise ProjectActionRefused("ACTION_UNAVAILABLE") from error

    async def prepare(caller: ActionCaller, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            request = dict(arguments)
            if set(request) - _REQUEST_KEYS:
                raise ProjectActionRefused("ACTION_INVALID")
            project_ref = request["project_ref"]
            relative_path = _assert_direct_write_path(
                validate_relative_path(request["relative_path"])
            )
            mode = request["mode"]
            new_text = request["new_text"]
            if type(project_ref) is not str or not project_ref or len(project_ref) > 256:
                raise ProjectActionRefused("ACTION_INVALID")
            if mode not in ("CREATE", "REPLACE") or type(new_text) is not str:
                raise ProjectActionRefused("ACTION_INVALID")
            if "\x00" in new_text or len(new_text.encode("utf-8")) > MAX_PATCH_TEXT_BYTES:
                raise ProjectActionRefused("ACTION_INVALID")
            if mode == "CREATE":
                if "expected_sha256" in request or "old_text" in request:
                    raise ProjectActionRefused("ACTION_INVALID")
                old_text = None
                expected_sha = None
            else:
                old_text = request.get("old_text")
                expected_sha = request.get("expected_sha256")
                if (
                    type(old_text) is not str
                    or not old_text
                    or "\x00" in old_text
                    or len(old_text.encode("utf-8")) > MAX_PATCH_TEXT_BYTES
                    or not _digest_ok(expected_sha)
                ):
                    raise ProjectActionRefused("ACTION_INVALID")
        except ProjectActionRefused:
            raise
        except Exception as error:
            raise ProjectActionRefused("ACTION_INVALID") from error

        original = _current_binding(
            caller=caller,
            project_ref=project_ref,
            resolve_binding=resolve_binding,
            clock_ms=clock_ms,
        )
        if relative_path not in original.scope.allowed_paths:
            raise ProjectActionRefused()
        binding_key = _binding_key(original)
        current_store = _live_store()
        current_host = validate_host_binding(host_binding)

        def current_scope() -> ActionScope:
            current = _current_binding(
                caller=caller,
                project_ref=project_ref,
                resolve_binding=resolve_binding,
                clock_ms=clock_ms,
            )
            if _binding_key(current) != binding_key:
                raise ProjectActionRefused("ACTION_BINDING_CHANGED")
            return current.scope

        def operation() -> dict[str, Any]:
            if store.cleanup_uncertain:
                raise ProjectActionRefused("ACTION_UNAVAILABLE")
            scope = current_scope()
            snapshot = _read_leaf(store, scope, relative_path, allow_absent=mode == "CREATE")
            if mode == "CREATE":
                if snapshot is not None:
                    raise ProjectActionRefused("ACTION_PREIMAGE_MISMATCH")
                candidate = new_text.encode("utf-8")
                preimage = None
                source_identity = None
            else:
                if snapshot is None or snapshot.sha256 != expected_sha:
                    raise ProjectActionRefused("ACTION_PREIMAGE_MISMATCH")
                candidate = _candidate_from_snapshot(
                    snapshot, old_text=old_text or "", new_text=new_text
                )
                preimage = snapshot.sha256
                source_identity = _encode_source_identity(snapshot.identity)
            current_scope()
            return {
                "preimage_sha256": preimage,
                "postimage_sha256": hashlib.sha256(candidate).hexdigest(),
                "source_identity": source_identity,
            }

        pending = run_io(operation)
        if not inspect.isawaitable(pending):
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
        try:
            result = await pending
        except ProjectActionRefused:
            raise
        except Exception as error:
            raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
        final = _current_binding(
            caller=caller,
            project_ref=project_ref,
            resolve_binding=resolve_binding,
            clock_ms=clock_ms,
        )
        if _binding_key(final) != binding_key:
            raise ProjectActionRefused("ACTION_BINDING_CHANGED")
        final_store = _live_store()
        if (
            final_store.device != current_store.device
            or final_store.inode != current_store.inode
        ):
            raise ProjectActionRefused("ACTION_BINDING_CHANGED")
        issued_at = _now(clock_ms)
        expires_at = min(
            issued_at + action_ttl_ms,
            final.scope.expires_at_ms,
            caller.expires_at * 1000,
        )
        if expires_at <= issued_at:
            raise ProjectActionRefused("ACTION_EXPIRED")
        prepared = PreparedTextPatch(
            schema=ACTION_TOKEN_SCHEMA,
            action_id=secrets.token_hex(16),
            subject_digest=caller.subject_digest,
            client_ref=caller.client_ref,
            resource=caller.resource,
            project_ref=project_ref,
            context_ref=final.scope.context_ref,
            responsibility_ref=final.scope.responsibility_ref,
            operation_ref=final.scope.operation_ref,
            owner_ref=final.scope.owner_ref,
            generation=final.scope.generation,
            root_device=final.scope.root_device,
            root_inode=final.scope.root_inode,
            artifact_store_device=final_store.device,
            artifact_store_inode=final_store.inode,
            host_id=current_host.host_id,
            boot_session_id=current_host.boot_session_id,
            purpose=ACTION_TOKEN_PURPOSE,
            committed_head=final.scope.committed_head,
            relative_path=relative_path,
            mode=mode,
            preimage_sha256=result["preimage_sha256"],
            postimage_sha256=result["postimage_sha256"],
            source_identity=result["source_identity"],
            old_text=old_text,
            new_text=new_text,
            issued_at_ms=issued_at,
            expires_at_ms=expires_at,
        )
        action_ref = token_codec.encode(prepared)
        return {
            "status": "PREPARED",
            "action_ref": action_ref,
            "project_ref": project_ref,
            "responsibility_ref": prepared.responsibility_ref,
            "operation_ref": prepared.operation_ref,
            "relative_path": relative_path,
            "preimage_sha256": prepared.preimage_sha256,
            "postimage_sha256": prepared.postimage_sha256,
            "expires_at_ms": expires_at,
        }

    def _decode_for_caller(
        caller: ActionCaller, action_ref: object, *, evidence: bool
    ) -> PreparedTextPatch:
        validate_action_caller(caller)
        try:
            if evidence:
                prepared = token_codec.decode_evidence(action_ref, now_ms=_now(clock_ms))
            else:
                prepared = token_codec.decode(action_ref, now_ms=_now(clock_ms))
        except ActionContractError as error:
            code = "ACTION_EXPIRED" if "expired" in str(error) else "ACTION_INVALID"
            raise ProjectActionRefused(code) from error
        if (
            caller.subject_digest != prepared.subject_digest
            or caller.client_ref != prepared.client_ref
            or caller.resource != prepared.resource
        ):
            raise ProjectActionRefused("ACTION_BINDING_CHANGED")
        return prepared

    def _binding_for_prepared(caller: ActionCaller, prepared: PreparedTextPatch) -> ProjectActionBinding:
        current = _current_binding(
            caller=caller,
            project_ref=prepared.project_ref,
            resolve_binding=resolve_binding,
            clock_ms=clock_ms,
        )
        _assert_action_binding(prepared, current)
        return current

    def _classified_receipt(
        prepared: PreparedTextPatch, *, observed_sha256: str | None
    ) -> dict[str, Any] | None:
        try:
            classified = classify_action(_live_store(), _artifact_identity(prepared))
        except (ActionArtifactError, ActionArtifactUncertain):
            return _receipt(effect_state="EFFECT_UNKNOWN", observed_sha256=observed_sha256)
        if not classified.store_valid:
            return _receipt(effect_state="EFFECT_UNKNOWN", observed_sha256=observed_sha256)
        if classified.claimable:
            return None
        return _receipt(
            effect_state=classified.effect_state,
            observed_sha256=observed_sha256,
        )

    def _unclaimed_effect(
        prepared: PreparedTextPatch,
        action_ref: object,
        *,
        observed_sha256: str | None,
        observation_ok: bool,
    ) -> str:
        # No claim artifact exists.  Absence alone is never NOT_APPLIED: the
        # commit may have been admitted and lost before its claim.  It becomes
        # NOT_APPLIED only when the durable admission ledger proves the commit
        # was refused before dispatch and never accepted for this exact
        # reference, and the source still reads as never patched.  The ledger
        # is consulted last so a commit admitted during this read is seen.
        if admission_evidence is None or not observation_ok:
            return "EFFECT_UNKNOWN"
        if prepared.mode == "CREATE":
            untouched = observed_sha256 is None
        else:
            untouched = (
                observed_sha256 is not None
                and observed_sha256 == prepared.preimage_sha256
            )
        if not untouched:
            return "EFFECT_UNKNOWN"
        try:
            verdict = admission_evidence(action_ref)
        except Exception:
            return "EFFECT_UNKNOWN"
        return "NOT_APPLIED" if verdict == ADMISSION_REFUSED_ONLY else "EFFECT_UNKNOWN"

    async def commit(caller: ActionCaller, action_ref: object) -> Mapping[str, Any]:
        prepared = _decode_for_caller(caller, action_ref, evidence=False)
        original = _binding_for_prepared(caller, prepared)
        binding_key = _binding_key(original)
        _assert_apply_host(prepared, store=_live_store(), host=host_binding)
        _assert_direct_write_path(prepared.relative_path)
        _assert_action_fresh(prepared, _now(clock_ms))

        def current_scope() -> ActionScope:
            current = _binding_for_prepared(caller, prepared)
            if _binding_key(current) != binding_key:
                raise ProjectActionRefused("ACTION_BINDING_CHANGED")
            _assert_apply_host(prepared, store=_live_store(), host=host_binding)
            return current.scope

        def operation() -> dict[str, Any]:
            _assert_action_fresh(prepared, _now(clock_ms))
            scope = current_scope()
            writer = None
            claimed = False
            try:
                writer = acquire_store_writer(_live_store())
            except ActionArtifactBusy as error:
                raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
            except ActionArtifactUncertain as error:
                raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
            try:
                observed = _observe(store, scope, prepared.relative_path)
                existing = _classified_receipt(prepared, observed_sha256=observed)
                if existing is not None:
                    return existing
                current = _read_leaf(
                    store,
                    scope,
                    prepared.relative_path,
                    allow_absent=prepared.mode == "CREATE",
                )
                if prepared.mode == "CREATE":
                    if current is not None:
                        raise ProjectActionRefused("ACTION_PREIMAGE_MISMATCH")
                    candidate = prepared.new_text.encode("utf-8")
                    file_mode = 0o644
                else:
                    if current is None or current.sha256 != prepared.preimage_sha256:
                        raise ProjectActionRefused("ACTION_PREIMAGE_MISMATCH")
                    if _encode_source_identity(current.identity) != prepared.source_identity:
                        raise ProjectActionRefused("ACTION_SOURCE_CHANGED")
                    candidate = _candidate_from_snapshot(
                        current,
                        old_text=prepared.old_text or "",
                        new_text=prepared.new_text,
                    )
                    file_mode = current.mode
                if hashlib.sha256(candidate).hexdigest() != prepared.postimage_sha256:
                    raise ProjectActionRefused("ACTION_INVALID")
                _assert_action_fresh(prepared, _now(clock_ms))
                outcome = claim_action(
                    _live_store(),
                    _artifact_identity(prepared),
                    claimed_at_ms=_now(clock_ms),
                )
                if outcome.uncertain:
                    return _receipt(effect_state="EFFECT_UNKNOWN", observed_sha256=observed)
                if not outcome.created:
                    replay = _classified_receipt(prepared, observed_sha256=observed)
                    return replay or _receipt(
                        effect_state="EFFECT_UNKNOWN", observed_sha256=observed
                    )
                claimed = True
                return _publish_candidate(
                    scope=scope,
                    prepared=prepared,
                    candidate=candidate,
                    mode=file_mode,
                    confirm_binding=current_scope,
                    clock_ms=clock_ms,
                    store=_live_store(),
                )
            except ProjectActionRefused:
                if claimed:
                    observed = None
                    try:
                        observed = _observe(store, scope, prepared.relative_path)
                    except ProjectActionRefused:
                        observed = None
                    return _finalize_receipt(
                        _live_store(),
                        prepared,
                        effect_state="EFFECT_UNKNOWN",
                        observed_sha256=observed,
                        completed_at_ms=_now(clock_ms),
                        durability="uncertain",
                        details={"reason": "refused_after_claim"},
                    )
                raise
            finally:
                if writer is not None:
                    try:
                        writer.release()
                    except ActionArtifactUncertain as error:
                        if not claimed:
                            raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
                        # Effect receipt remains separately available for qualified
                        # historical reads. This completion cannot claim clean release.
                        return _receipt(effect_state="EFFECT_UNKNOWN", observed_sha256=None)

        pending = run_io(operation)
        if not inspect.isawaitable(pending):
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
        try:
            result = await pending
        except ProjectActionRefused:
            raise
        except Exception as error:
            raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
        if result.get("effect_state") not in _EFFECTS:
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
        return {
            "status": "OK",
            "effect_state": result["effect_state"],
            "project_ref": prepared.project_ref,
            "responsibility_ref": prepared.responsibility_ref,
            "operation_ref": prepared.operation_ref,
            "relative_path": prepared.relative_path,
            "preimage_sha256": prepared.preimage_sha256,
            "postimage_sha256": prepared.postimage_sha256,
            "observed_sha256": result.get("observed_sha256"),
            "cleanup_state": "UNCERTAIN" if store.cleanup_uncertain else "CLEAN",
        }

    async def reconcile(caller: ActionCaller, action_ref: object) -> Mapping[str, Any]:
        prepared = _decode_for_caller(caller, action_ref, evidence=True)
        binding = _binding_for_prepared(caller, prepared)
        binding_key = _binding_key(binding)
        if prepared.host_id != host_binding.host_id:
            raise ProjectActionRefused("ACTION_BINDING_CHANGED")

        def operation() -> dict[str, Any]:
            current = _binding_for_prepared(caller, prepared)
            if _binding_key(current) != binding_key:
                raise ProjectActionRefused("ACTION_BINDING_CHANGED")
            try:
                live = _live_store()
            except ProjectActionRefused:
                return _receipt(effect_state="EFFECT_UNKNOWN", observed_sha256=None)
            if (
                live.device != prepared.artifact_store_device
                or live.inode != prepared.artifact_store_inode
            ):
                return _receipt(effect_state="EFFECT_UNKNOWN", observed_sha256=None)
            observed = None
            observation_ok = True
            try:
                observed = _observe(store, current.scope, prepared.relative_path)
            except ProjectActionRefused:
                observation_ok = False
            existing = _classified_receipt(prepared, observed_sha256=observed)
            if existing is not None:
                return existing
            return _receipt(
                effect_state=_unclaimed_effect(
                    prepared,
                    action_ref,
                    observed_sha256=observed,
                    observation_ok=observation_ok,
                ),
                observed_sha256=observed,
            )

        pending = run_io(operation)
        if not inspect.isawaitable(pending):
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
        try:
            result = await pending
        except ProjectActionRefused:
            raise
        except Exception as error:
            raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
        return {
            "status": "OK",
            "effect_state": result["effect_state"],
            "project_ref": prepared.project_ref,
            "responsibility_ref": prepared.responsibility_ref,
            "operation_ref": prepared.operation_ref,
            "relative_path": prepared.relative_path,
            "preimage_sha256": prepared.preimage_sha256,
            "postimage_sha256": prepared.postimage_sha256,
            "observed_sha256": result.get("observed_sha256"),
            "cleanup_state": "UNCERTAIN" if store.cleanup_uncertain else "CLEAN",
        }

    return prepare, commit, reconcile


__all__ = [
    "ADMISSION_REFUSED_ONLY",
    "ActionBindingResolver",
    "ActionExecutor",
    "AdmissionEvidence",
    "MAX_FILE_BYTES",
    "ProjectActionRefused",
    "create_text_patch_port",
]
