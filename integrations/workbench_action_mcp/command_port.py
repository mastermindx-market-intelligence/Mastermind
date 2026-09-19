"""Closed, descriptor-bound command canary port for Workbench Action.

A claim artifact always precedes a spawn, so an action with no artifact never
ran through this port.  That absence is still reported as ``EFFECT_UNKNOWN``
unless the entry point's durable pre-dispatch admission ledger proves the run
was refused before dispatch and never accepted for that exact reference, in
which case the same rule as the text patch port yields ``NOT_APPLIED``.
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import inspect
import os
import secrets
import selectors
import signal
import stat
import subprocess
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from control_plane.codex_worker import ProcessIdentityError, ProcessInspector

from .action_artifacts import (
    ACTION_PURPOSE_CLOSED_COMMAND,
    ActionArtifactBusy,
    ActionArtifactError,
    ActionArtifactIdentity,
    ActionArtifactStore,
    ActionArtifactUncertain,
    acquire_store_writer,
    claim_action,
    classify_action,
    finalize_action,
    read_action_blob,
    read_action_process,
    revalidate_artifact_store,
    write_action_blob,
    write_action_process,
)
from .command_contracts import (
    ARTIFACT_TOKEN_SCHEMA,
    COMMAND_TOKEN_SCHEMA,
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACT_CHUNK_BYTES,
    MAX_DIRECT_IMAGE_BYTES,
    MAX_PAGE_BYTES,
    MAX_PAGE_LINES,
    MAX_PROCESS_DEADLINE_S,
    MAX_STDERR_BYTES,
    MAX_STDOUT_BYTES,
    PNG_MEDIA_TYPE,
    RECIPE_IDS,
    RECIPE_SHA256,
    TEXT_MEDIA_TYPE,
    CommandHostBinding,
    PreparedActionArtifact,
    PreparedClosedCommand,
    artifact_media_type,
    derive_artifact_id,
    validate_command_host_binding,
)
from .contracts import (
    MAX_ACTION_TTL_MS,
    ActionCaller,
    ActionContractError,
    ActionScope,
    ActionTokenCodec,
    ProjectActionBinding,
    validate_action_caller,
    validate_action_scope,
    validate_relative_path,
)
from .patch_port import ADMISSION_REFUSED_ONLY, AdmissionEvidence, ProjectActionRefused


MAX_INPUT_BYTES = 65536
MAX_EXECUTABLE_BYTES = 64 * 1024 * 1024
_REQUEST_KEYS = frozenset(
    {"project_ref", "relative_path", "recipe_id", "expected_sha256"}
)
_READ_KEYS = frozenset(
    {"action_ref", "stream", "start_line", "max_lines", "max_content_bytes"}
)
_ARTIFACT_READ_KEYS = frozenset({"artifact_ref", "offset", "max_bytes"})
ARTIFACT_DESCRIPTOR_SCHEMA = "mastermind.workbench_action_artifact_descriptor.v1"
ARTIFACT_OWNER = "mastermind.workbench_action"
_RESULT_KEYS = frozenset(
    {
        "recipe_id",
        "exit_code",
        "stdout_sha256",
        "stderr_sha256",
        "stdout_bytes",
        "stderr_bytes",
        "stdout_truncated",
        "stderr_truncated",
        "pid",
        "process_start_identity",
        "pgid",
        "session_id",
        "released",
        "timed_out",
    }
)
_HEX64 = frozenset("0123456789abcdef")

ActionBindingResolver = Callable[[ActionCaller, str], ProjectActionBinding | None]
ActionExecutor = Callable[[Callable[[], dict[str, Any]]], Awaitable[dict[str, Any]]]


@dataclasses.dataclass(frozen=True)
class _HeldInput:
    root_fd: int
    input_fd: int
    raw: bytes
    sha256: str
    identity: tuple[int, ...]


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


def _source_identity(value: tuple[int, ...]) -> str:
    return ":".join(str(item) for item in value)


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


def _direct_label(value: object) -> str:
    try:
        selected = validate_relative_path(value)
    except ActionContractError as error:
        raise ProjectActionRefused("ACTION_INVALID") from error
    if "/" in selected or selected.startswith(".") or len(selected) > 128:
        raise ProjectActionRefused("ACTION_INVALID")
    return selected


def _current_binding(
    caller: ActionCaller,
    project_ref: str,
    resolve_binding: ActionBindingResolver,
    clock_ms: Callable[[], int],
) -> ProjectActionBinding:
    try:
        validate_action_caller(caller)
        timestamp = _now(clock_ms)
        if timestamp >= caller.expires_at * 1000:
            raise ProjectActionRefused("ACTION_BINDING_CHANGED")
        value = resolve_binding(dataclasses.replace(caller), project_ref)
        if (
            type(value) is not ProjectActionBinding
            or value.caller != caller
            or value.project_ref != project_ref
        ):
            raise ProjectActionRefused("ACTION_BINDING_CHANGED")
        validate_action_scope(value.scope, now_ms=timestamp)
        return value
    except ProjectActionRefused:
        raise
    except Exception as error:
        raise ProjectActionRefused("ACTION_BINDING_CHANGED") from error


def _assert_binding(prepared: PreparedClosedCommand, value: ProjectActionBinding) -> None:
    scope = value.scope
    caller = value.caller
    if (
        caller.subject_digest != prepared.subject_digest
        or caller.client_ref != prepared.client_ref
        or caller.resource != prepared.resource
        or value.project_ref != prepared.project_ref
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


def _boot(inspector: ProcessInspector, expected: str, *, prepare: bool) -> str:
    try:
        value = inspector.boot_session_id()
    except Exception as error:
        raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
    if (
        type(value) is not str
        or not value
        or value.startswith("adapter-")
        or value != expected
    ):
        code = "ACTION_UNAVAILABLE" if prepare and value == expected else "ACTION_BINDING_CHANGED"
        raise ProjectActionRefused(code)
    return value


def _live_store(store: ActionArtifactStore) -> ActionArtifactStore:
    try:
        return revalidate_artifact_store(store)
    except (ActionArtifactError, ActionArtifactUncertain) as error:
        raise ProjectActionRefused("ACTION_UNAVAILABLE") from error


def _artifact_identity(prepared: PreparedClosedCommand) -> ActionArtifactIdentity:
    return ActionArtifactIdentity(
        action_id=prepared.action_id,
        purpose=ACTION_PURPOSE_CLOSED_COMMAND,
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


def _open_input(
    store: ActionArtifactStore, scope: ActionScope, relative_path: str
) -> _HeldInput:
    if relative_path not in scope.allowed_paths:
        raise ProjectActionRefused("PROJECT_ACTION_REFUSED")
    root_fd = input_fd = -1
    try:
        required = (
            getattr(os, "O_DIRECTORY", 0),
            getattr(os, "O_NOFOLLOW", 0),
            getattr(os, "O_CLOEXEC", 0),
            getattr(os, "O_NONBLOCK", 0),
        )
        if not all(required) or os.open not in os.supports_dir_fd:
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
        root_fd = os.open(
            ".",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=scope.root_fd,
        )
        root = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(root.st_mode)
            or (root.st_dev, root.st_ino) != (scope.root_device, scope.root_inode)
            or root.st_uid != os.geteuid()
        ):
            raise ProjectActionRefused("ACTION_BINDING_CHANGED")
        before = os.stat(relative_path, dir_fd=root_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_dev != scope.root_device
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or not 0 <= before.st_size <= MAX_INPUT_BYTES
        ):
            raise ProjectActionRefused("ACTION_SOURCE_CHANGED")
        input_fd = os.open(
            relative_path,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=root_fd,
        )
        opened = os.fstat(input_fd)
        if _file_identity(opened) != _file_identity(before):
            raise ProjectActionRefused("ACTION_SOURCE_CHANGED")
        chunks: list[bytes] = []
        count = 0
        while count <= MAX_INPUT_BYTES:
            chunk = os.read(input_fd, MAX_INPUT_BYTES + 1 - count)
            if not chunk:
                break
            chunks.append(chunk)
            count += len(chunk)
            if count > MAX_INPUT_BYTES:
                raise ProjectActionRefused("ACTION_SOURCE_CHANGED")
        raw = b"".join(chunks)
        after_fd = os.fstat(input_fd)
        after_path = os.stat(relative_path, dir_fd=root_fd, follow_symlinks=False)
        if (
            len(raw) != before.st_size
            or _file_identity(after_fd) != _file_identity(before)
            or _file_identity(after_path) != _file_identity(before)
        ):
            raise ProjectActionRefused("ACTION_SOURCE_CHANGED")
        os.lseek(input_fd, 0, os.SEEK_SET)
        held = _HeldInput(
            root_fd=root_fd,
            input_fd=input_fd,
            raw=raw,
            sha256=hashlib.sha256(raw).hexdigest(),
            identity=_file_identity(before),
        )
        root_fd = input_fd = -1
        return held
    except FileNotFoundError:
        raise ProjectActionRefused("ACTION_SOURCE_CHANGED") from None
    except ProjectActionRefused:
        raise
    except (OSError, TypeError, ValueError, OverflowError) as error:
        raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
    finally:
        for fd in (input_fd, root_fd):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    store.mark_cleanup_uncertain("command_input_open_close")


def _close_held(store: ActionArtifactStore, held: _HeldInput) -> None:
    failed = False
    for fd in (held.input_fd, held.root_fd):
        try:
            os.close(fd)
        except OSError:
            failed = True
    if failed:
        store.mark_cleanup_uncertain("command_input_close")


def _revalidate_held(held: _HeldInput, scope: ActionScope, relative_path: str) -> None:
    try:
        root = os.fstat(held.root_fd)
        current_fd = os.fstat(held.input_fd)
        current_path = os.stat(
            relative_path, dir_fd=held.root_fd, follow_symlinks=False
        )
    except OSError as error:
        raise ProjectActionRefused("ACTION_SOURCE_CHANGED") from error
    if (
        (root.st_dev, root.st_ino) != (scope.root_device, scope.root_inode)
        or _file_identity(current_fd) != held.identity
        or _file_identity(current_path) != held.identity
    ):
        raise ProjectActionRefused("ACTION_SOURCE_CHANGED")
    os.lseek(held.input_fd, 0, os.SEEK_SET)


def _attest_path(
    store: ActionArtifactStore, path: str, expected_sha256: str
) -> None:
    fd = -1
    try:
        before = os.lstat(path)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) & 0o022
            or not 0 <= before.st_size <= MAX_EXECUTABLE_BYTES
        ):
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        opened = os.fstat(fd)
        if _file_identity(opened) != _file_identity(before):
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(fd, min(65536, before.st_size - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > before.st_size or total > MAX_EXECUTABLE_BYTES:
                raise ProjectActionRefused("ACTION_UNAVAILABLE")
            digest.update(chunk)
        if (
            total != before.st_size
            or digest.hexdigest() != expected_sha256
            or _file_identity(os.fstat(fd)) != _file_identity(before)
            or _file_identity(os.lstat(path)) != _file_identity(before)
        ):
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
    except ProjectActionRefused:
        raise
    except (OSError, TypeError, ValueError) as error:
        raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                store.mark_cleanup_uncertain("command_attestation_close")
                raise ProjectActionRefused("ACTION_UNAVAILABLE") from None


def _recipe_path(host: CommandHostBinding, recipe_id: str) -> str:
    root = os.path.normpath(host.recipe_root)
    selected = os.path.normpath(os.path.join(root, f"{recipe_id}.py"))
    if os.path.dirname(selected) != root:
        raise ProjectActionRefused("ACTION_UNAVAILABLE")
    try:
        root_stat = os.lstat(root)
    except OSError as error:
        raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
    if (
        not stat.S_ISDIR(root_stat.st_mode)
        or root_stat.st_uid != os.geteuid()
        or stat.S_IMODE(root_stat.st_mode) & 0o022
    ):
        raise ProjectActionRefused("ACTION_UNAVAILABLE")
    return selected


def _result_receipt(
    prepared: PreparedClosedCommand,
    *,
    effect_state: str,
    details: Mapping[str, Any] | None = None,
    cleanup_uncertain: bool = False,
) -> dict[str, Any]:
    selected = dict(details or {})
    response: dict[str, Any] = {
        "status": "OK",
        "effect_state": effect_state,
        "isError": False,
        "project_ref": prepared.project_ref,
        "recipe_id": prepared.recipe_id,
        "relative_path": prepared.relative_path,
        "preimage_sha256": prepared.preimage_sha256,
        "cleanup_state": "UNCERTAIN" if cleanup_uncertain else "CLEAN",
    }
    if selected:
        response.update(
            {
                "exit_code": selected["exit_code"],
                "stdout_sha256": selected["stdout_sha256"],
                "stderr_sha256": selected["stderr_sha256"],
                "stdout_bytes": selected["stdout_bytes"],
                "stderr_bytes": selected["stderr_bytes"],
                "truncated": bool(
                    selected["stdout_truncated"] or selected["stderr_truncated"]
                ),
                "process_identity": {
                    "pid": selected["pid"],
                    "process_start_identity": selected["process_start_identity"],
                    "pgid": selected["pgid"],
                    "session_id": selected["session_id"],
                    "host_id": prepared.host_id,
                    "boot_session_id": prepared.boot_session_id,
                },
                "timed_out": selected["timed_out"],
            }
        )
    return response


def _validated_details(value: object, prepared: PreparedClosedCommand) -> dict[str, Any] | None:
    if type(value) is not dict or set(value) != _RESULT_KEYS:
        return None
    if (
        value["recipe_id"] != prepared.recipe_id
        or type(value["exit_code"]) is not int
        or not -(2**31) <= value["exit_code"] < 2**31
        or not _digest_ok(value["stdout_sha256"])
        or not _digest_ok(value["stderr_sha256"])
        or type(value["stdout_bytes"]) is not int
        or not 0 <= value["stdout_bytes"] <= MAX_STDOUT_BYTES
        or type(value["stderr_bytes"]) is not int
        or not 0 <= value["stderr_bytes"] <= MAX_STDERR_BYTES
        or type(value["stdout_truncated"]) is not bool
        or type(value["stderr_truncated"]) is not bool
        or type(value["pid"]) is not int
        or value["pid"] <= 0
        or type(value["process_start_identity"]) is not str
        or not value["process_start_identity"]
        or type(value["pgid"]) is not int
        or value["pgid"] <= 0
        or type(value["session_id"]) is not int
        or value["session_id"] <= 0
        or type(value["released"]) is not bool
        or not value["released"]
        or type(value["timed_out"]) is not bool
    ):
        return None
    return dict(value)



@dataclasses.dataclass(frozen=True)
class _QualifiedCommandEvidence:
    details: dict[str, Any]
    stdout: bytes
    stderr: bytes


def _qualified_evidence(
    store: ActionArtifactStore, prepared: PreparedClosedCommand
) -> tuple[str, _QualifiedCommandEvidence | None]:
    identity = _artifact_identity(prepared)
    try:
        classified = classify_action(store, identity)
        if classified.claimable:
            return "absent", None
        if (
            classified.evidence_status != "qualified"
            or classified.effect_state != "APPLIED"
            or classified.result is None
        ):
            return "uncertain", None
        details = _validated_details(classified.result.details, prepared)
        process = read_action_process(store, identity)
        stdout = read_action_blob(store, prepared.action_id, "stdout")
        stderr = read_action_blob(store, prepared.action_id, "stderr")
        if (
            details is None
            or process is None
            or classified.result.observed_sha256 != prepared.preimage_sha256
            or classified.result.completed_at_ms < process.recorded_at_ms
            or stdout is None
            or stderr is None
            or process.pid != details["pid"]
            or process.process_start_identity != details["process_start_identity"]
            or process.pgid != details["pgid"]
            or process.session_id != details["session_id"]
            or hashlib.sha256(stdout).hexdigest() != details["stdout_sha256"]
            or hashlib.sha256(stderr).hexdigest() != details["stderr_sha256"]
            or len(stdout) != details["stdout_bytes"]
            or len(stderr) != details["stderr_bytes"]
        ):
            raise ActionArtifactUncertain("command evidence mismatch")
        return "qualified", _QualifiedCommandEvidence(
            details=details, stdout=stdout, stderr=stderr
        )
    except (ActionArtifactError, ActionArtifactUncertain, OSError, ValueError, TypeError):
        return "uncertain", None


def _qualified_result(
    store: ActionArtifactStore,
    prepared: PreparedClosedCommand,
    artifact_issuer: Callable[
        [PreparedClosedCommand, _QualifiedCommandEvidence], list[dict[str, Any]]
    ]
    | None = None,
) -> dict[str, Any] | None:
    status, evidence = _qualified_evidence(store, prepared)
    if status == "absent":
        return None
    if status != "qualified" or evidence is None:
        return _result_receipt(
            prepared,
            effect_state="EFFECT_UNKNOWN",
            cleanup_uncertain=True,
        )
    receipt = _result_receipt(
        prepared,
        effect_state="APPLIED",
        details=evidence.details,
        cleanup_uncertain=store.cleanup_uncertain,
    )
    if artifact_issuer is not None:
        receipt["artifacts"] = artifact_issuer(prepared, evidence)
    return receipt


def _artifact_size_state(byte_length: int, truncated: bool) -> str:
    if truncated:
        return "retained_prefix"
    return "empty" if byte_length == 0 else "complete"


def _artifact_producer(prepared: PreparedClosedCommand) -> dict[str, Any]:
    return {
        "kind": "workbench_action",
        "action_id": prepared.action_id,
        "recipe_id": prepared.recipe_id,
        "project_ref": prepared.project_ref,
        "context_ref": prepared.context_ref,
        "responsibility_ref": prepared.responsibility_ref,
        "operation_ref": prepared.operation_ref,
        "owner_ref": prepared.owner_ref,
        "generation": prepared.generation,
        "host_id": prepared.host_id,
        "boot_session_id": prepared.boot_session_id,
    }


def _artifact_source(prepared: PreparedClosedCommand) -> dict[str, Any]:
    return {
        "relative_path": prepared.relative_path,
        "preimage_sha256": prepared.preimage_sha256,
        "source_identity": prepared.source_identity,
    }


def _artifact_descriptor(
    prepared: PreparedClosedCommand,
    *,
    stream: str,
    raw: bytes,
    truncated: bool,
    issued_at_ms: int,
    expires_at_ms: int,
    token_codec: ActionTokenCodec,
) -> dict[str, Any]:
    media_type = artifact_media_type(prepared.recipe_id, stream)
    digest = hashlib.sha256(raw).hexdigest()
    artifact_id = derive_artifact_id(
        action_id=prepared.action_id,
        project_ref=prepared.project_ref,
        generation=prepared.generation,
        recipe_id=prepared.recipe_id,
        relative_path=prepared.relative_path,
        preimage_sha256=prepared.preimage_sha256,
        source_identity=prepared.source_identity,
        stream=stream,
        media_type=media_type,
        byte_length=len(raw),
        sha256=digest,
        truncated=truncated,
    )
    reference = PreparedActionArtifact(
        schema=ARTIFACT_TOKEN_SCHEMA,
        artifact_id=artifact_id,
        action_id=prepared.action_id,
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
        artifact_store_device=prepared.artifact_store_device,
        artifact_store_inode=prepared.artifact_store_inode,
        committed_head=prepared.committed_head,
        host_id=prepared.host_id,
        boot_session_id=prepared.boot_session_id,
        relative_path=prepared.relative_path,
        recipe_id=prepared.recipe_id,
        preimage_sha256=prepared.preimage_sha256,
        source_identity=prepared.source_identity,
        command_issued_at_ms=prepared.issued_at_ms,
        command_expires_at_ms=prepared.expires_at_ms,
        stream=stream,
        media_type=media_type,
        byte_length=len(raw),
        sha256=digest,
        truncated=truncated,
        issued_at_ms=issued_at_ms,
        expires_at_ms=expires_at_ms,
    )
    direct_view = (
        media_type == PNG_MEDIA_TYPE and len(raw) <= MAX_DIRECT_IMAGE_BYTES
    )
    return {
        "schema": ARTIFACT_DESCRIPTOR_SCHEMA,
        "artifact_id": artifact_id,
        "artifact_ref": token_codec.encode_artifact(reference),
        "owner": ARTIFACT_OWNER,
        "stream": stream,
        "media_type": media_type,
        "byte_length": len(raw),
        "sha256": digest,
        "truncated": truncated,
        "size_state": _artifact_size_state(len(raw), truncated),
        "producer": _artifact_producer(prepared),
        "source": _artifact_source(prepared),
        "transfer": {
            "maximum_artifact_bytes": MAX_ARTIFACT_BYTES,
            "maximum_chunk_bytes": MAX_ARTIFACT_CHUNK_BYTES,
            "direct_view_supported": direct_view,
        },
        "issued_at_ms": issued_at_ms,
        "expires_at_ms": expires_at_ms,
    }


def _prepared_from_artifact(reference: PreparedActionArtifact) -> PreparedClosedCommand:
    return PreparedClosedCommand(
        schema=COMMAND_TOKEN_SCHEMA,
        action_id=reference.action_id,
        subject_digest=reference.subject_digest,
        client_ref=reference.client_ref,
        resource=reference.resource,
        project_ref=reference.project_ref,
        context_ref=reference.context_ref,
        responsibility_ref=reference.responsibility_ref,
        operation_ref=reference.operation_ref,
        owner_ref=reference.owner_ref,
        generation=reference.generation,
        root_device=reference.root_device,
        root_inode=reference.root_inode,
        artifact_store_device=reference.artifact_store_device,
        artifact_store_inode=reference.artifact_store_inode,
        committed_head=reference.committed_head,
        host_id=reference.host_id,
        boot_session_id=reference.boot_session_id,
        relative_path=reference.relative_path,
        recipe_id=reference.recipe_id,
        preimage_sha256=reference.preimage_sha256,
        source_identity=reference.source_identity,
        issued_at_ms=reference.command_issued_at_ms,
        expires_at_ms=reference.command_expires_at_ms,
    )

def _capture_process(
    process: subprocess.Popen[bytes],
    *,
    deadline_seconds: float,
    inspector: ProcessInspector,
    process_start_identity: str,
    pgid: int,
    boot_session_id: str,
    store: ActionArtifactStore,
) -> tuple[int, bytes, bytes, bool, bool, bool]:
    selector = selectors.DefaultSelector()
    streams = ((process.stdout, MAX_STDOUT_BYTES), (process.stderr, MAX_STDERR_BYTES))
    buffers: dict[int, bytearray] = {}
    truncated: dict[int, bool] = {}
    for stream, _limit in streams:
        if stream is None:
            raise OSError("missing child pipe")
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ)
        buffers[stream.fileno()] = bytearray()
        truncated[stream.fileno()] = False
    started = time.monotonic()
    timed_out = False
    cleanup_uncertain = False
    signaled = False
    try:
        while selector.get_map() or process.poll() is None:
            elapsed = time.monotonic() - started
            if not timed_out and elapsed >= deadline_seconds and process.poll() is None:
                timed_out = True
                try:
                    current_boot = inspector.boot_session_id()
                    observed = inspector.inspect(process.pid)
                    safe = (
                        current_boot == boot_session_id
                        and not current_boot.startswith("adapter-")
                        and observed.start_identity == process_start_identity
                        and observed.pgid == pgid
                        and observed.session_id == process.pid
                        and observed.effective_uid == os.geteuid()
                        and observed.real_uid == os.getuid()
                    )
                except Exception:
                    safe = False
                if safe:
                    try:
                        os.killpg(pgid, signal.SIGTERM)
                        signaled = True
                    except ProcessLookupError:
                        pass
                    except OSError:
                        cleanup_uncertain = True
                        store.mark_cleanup_uncertain("command_deadline_signal")
                else:
                    cleanup_uncertain = True
                    store.mark_cleanup_uncertain("command_identity_safe_kill")
            if signaled and process.poll() is None and time.monotonic() - started >= deadline_seconds + 0.25:
                try:
                    observed = inspector.inspect(process.pid)
                    if observed.start_identity == process_start_identity and observed.pgid == pgid:
                        try:
                            os.killpg(pgid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        except OSError:
                            cleanup_uncertain = True
                            store.mark_cleanup_uncertain("command_deadline_signal")
                    else:
                        cleanup_uncertain = True
                        store.mark_cleanup_uncertain("command_deadline_identity")
                except ProcessIdentityError:
                    pass
                except Exception:
                    cleanup_uncertain = True
                    store.mark_cleanup_uncertain("command_deadline_identity")
                signaled = False
            events = selector.select(0.05)
            for key, _mask in events:
                stream = key.fileobj
                fd = stream.fileno()
                try:
                    chunk = os.read(fd, 65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    continue
                limit = MAX_STDOUT_BYTES if stream is process.stdout else MAX_STDERR_BYTES
                room = limit - len(buffers[fd])
                if room > 0:
                    buffers[fd].extend(chunk[:room])
                if len(chunk) > room:
                    truncated[fd] = True
        exit_code = process.wait()
        if type(exit_code) is not int:
            raise OSError("missing child returncode")
        stdout_fd = process.stdout.fileno() if process.stdout is not None else -1
        stderr_fd = process.stderr.fileno() if process.stderr is not None else -1
        return (
            exit_code,
            bytes(buffers[stdout_fd]),
            bytes(buffers[stderr_fd]),
            truncated[stdout_fd],
            truncated[stderr_fd],
            timed_out,
        )
    finally:
        try:
            selector.close()
        except OSError:
            cleanup_uncertain = True
            store.mark_cleanup_uncertain("command_selector_close")
        for stream, _limit in streams:
            try:
                stream.close()
            except OSError:
                cleanup_uncertain = True
                store.mark_cleanup_uncertain("command_pipe_close")


def _abort_child(
    process: subprocess.Popen[bytes],
    *,
    inspector: ProcessInspector,
    boot_session_id: str,
    expected_start_identity: str | None,
    expected_pgid: int | None,
    deadline_seconds: float,
    store: ActionArtifactStore,
) -> None:
    """Close an unreleased barrier and retain ownership until actual reap."""

    if process.stdin is not None and not process.stdin.closed:
        try:
            process.stdin.close()
        except OSError:
            store.mark_cleanup_uncertain("command_barrier_close")
        process.stdin = None
    try:
        process.wait(timeout=deadline_seconds)
    except subprocess.TimeoutExpired:
        safe = False
        try:
            observed = inspector.inspect(process.pid)
            current_boot = inspector.boot_session_id()
            safe = (
                expected_start_identity is not None
                and expected_pgid is not None
                and current_boot == boot_session_id
                and not current_boot.startswith("adapter-")
                and observed.start_identity == expected_start_identity
                and observed.pgid == expected_pgid
                and observed.session_id == process.pid
                and observed.effective_uid == os.geteuid()
                and observed.real_uid == os.getuid()
            )
        except Exception:
            safe = False
        if safe:
            try:
                os.killpg(expected_pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except OSError:
                store.mark_cleanup_uncertain("command_abort_signal")
            try:
                process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                try:
                    observed = inspector.inspect(process.pid)
                    if (
                        observed.start_identity == expected_start_identity
                        and observed.pgid == expected_pgid
                    ):
                        os.killpg(expected_pgid, signal.SIGKILL)
                    else:
                        store.mark_cleanup_uncertain("command_abort_identity")
                except ProcessIdentityError:
                    pass
                except OSError:
                    store.mark_cleanup_uncertain("command_abort_signal")
                process.wait()
        else:
            store.mark_cleanup_uncertain("command_abort_identity")
            process.wait()
    finally:
        for stream in (process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    store.mark_cleanup_uncertain("command_pipe_close")


def create_command_port(
    *,
    resolve_binding: ActionBindingResolver,
    clock_ms: Callable[[], int],
    run_io: ActionExecutor,
    token_codec: ActionTokenCodec,
    artifact_store: ActionArtifactStore,
    host: CommandHostBinding,
    inspector: ProcessInspector,
    action_ttl_ms: int = MAX_ACTION_TTL_MS,
    admission_evidence: AdmissionEvidence | None = None,
):
    """Return prepare, run, bounded-read and reconcile callbacks.

    ``admission_evidence`` is the entry point's durable pre-dispatch admission
    reader; without it artifact absence stays ``EFFECT_UNKNOWN``.
    """

    if not all(callable(value) for value in (resolve_binding, clock_ms, run_io)):
        raise TypeError("explicit binding, clock and I/O integration required")
    if admission_evidence is not None and not callable(admission_evidence):
        raise TypeError("admission evidence must be callable")
    if not isinstance(token_codec, ActionTokenCodec):
        raise TypeError("explicit action token codec required")
    if not callable(getattr(inspector, "boot_session_id", None)) or not callable(
        getattr(inspector, "inspect", None)
    ):
        raise TypeError("explicit process inspector required")
    if type(action_ttl_ms) is not int or not 1000 <= action_ttl_ms <= MAX_ACTION_TTL_MS:
        raise ValueError("action ttl is outside the closed F0 range")
    try:
        store = revalidate_artifact_store(artifact_store)
        host_binding = validate_command_host_binding(host)
    except (ActionArtifactError, ActionArtifactUncertain, ValueError) as error:
        raise TypeError("explicit command host and artifact store required") from error

    def decode(caller: ActionCaller, action_ref: object, *, evidence: bool) -> PreparedClosedCommand:
        validate_action_caller(caller)
        try:
            prepared = (
                token_codec.decode_command_evidence(action_ref, now_ms=_now(clock_ms))
                if evidence
                else token_codec.decode_command(action_ref, now_ms=_now(clock_ms))
            )
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

    def binding_for(caller: ActionCaller, prepared: PreparedClosedCommand) -> ProjectActionBinding:
        value = _current_binding(caller, prepared.project_ref, resolve_binding, clock_ms)
        _assert_binding(prepared, value)
        current_store = _live_store(store)
        if (
            current_store.device != prepared.artifact_store_device
            or current_store.inode != prepared.artifact_store_inode
            or host_binding.host_id != prepared.host_id
        ):
            raise ProjectActionRefused("ACTION_BINDING_CHANGED")
        return value


    def decode_artifact(
        caller: ActionCaller, artifact_ref: object
    ) -> PreparedActionArtifact:
        validate_action_caller(caller)
        try:
            reference = token_codec.decode_artifact_evidence(
                artifact_ref, now_ms=_now(clock_ms)
            )
        except ActionContractError as error:
            raise ProjectActionRefused("ARTIFACT_INVALID") from error
        if _now(clock_ms) >= reference.expires_at_ms:
            raise ProjectActionRefused("ARTIFACT_EXPIRED")
        if (
            caller.subject_digest != reference.subject_digest
            or caller.client_ref != reference.client_ref
            or caller.resource != reference.resource
        ):
            raise ProjectActionRefused("ARTIFACT_BINDING_CHANGED")
        return reference

    def artifact_binding_for(
        caller: ActionCaller, reference: PreparedActionArtifact
    ) -> tuple[PreparedClosedCommand, ProjectActionBinding]:
        prepared = _prepared_from_artifact(reference)
        try:
            return prepared, binding_for(caller, prepared)
        except ProjectActionRefused as error:
            raise ProjectActionRefused("ARTIFACT_BINDING_CHANGED") from error

    def issue_artifacts(
        caller: ActionCaller,
        prepared: PreparedClosedCommand,
        evidence: _QualifiedCommandEvidence,
    ) -> list[dict[str, Any]]:
        initial = binding_for(caller, prepared)
        initial_key = _binding_key(initial)
        issued_at = _now(clock_ms)
        expires_at = min(
            issued_at + action_ttl_ms,
            initial.scope.expires_at_ms,
            caller.expires_at * 1000,
        )
        if expires_at <= issued_at:
            raise ProjectActionRefused("ARTIFACT_BINDING_CHANGED")
        rows = [
            _artifact_descriptor(
                prepared,
                stream="stdout",
                raw=evidence.stdout,
                truncated=evidence.details["stdout_truncated"],
                issued_at_ms=issued_at,
                expires_at_ms=expires_at,
                token_codec=token_codec,
            ),
            _artifact_descriptor(
                prepared,
                stream="stderr",
                raw=evidence.stderr,
                truncated=evidence.details["stderr_truncated"],
                issued_at_ms=issued_at,
                expires_at_ms=expires_at,
                token_codec=token_codec,
            ),
        ]
        final = binding_for(caller, prepared)
        if _binding_key(final) != initial_key:
            raise ProjectActionRefused("ARTIFACT_BINDING_CHANGED")
        return rows

    def artifact_issuer(caller: ActionCaller):
        return lambda prepared, evidence: issue_artifacts(
            caller, prepared, evidence
        )

    async def prepare_project_command(
        caller: ActionCaller, arguments: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        try:
            request = dict(arguments)
            if set(request) != _REQUEST_KEYS:
                raise ProjectActionRefused("ACTION_INVALID")
            project_ref = request["project_ref"]
            recipe_id = request["recipe_id"]
            expected_sha256 = request["expected_sha256"]
            relative_path = _direct_label(request["relative_path"])
            if (
                type(project_ref) is not str
                or not project_ref
                or len(project_ref) > 256
                or recipe_id not in RECIPE_IDS
                or type(recipe_id) is not str
                or not _digest_ok(expected_sha256)
            ):
                raise ProjectActionRefused("ACTION_INVALID")
        except ProjectActionRefused:
            raise
        except Exception as error:
            raise ProjectActionRefused("ACTION_INVALID") from error
        original = _current_binding(caller, project_ref, resolve_binding, clock_ms)
        if relative_path not in original.scope.allowed_paths:
            raise ProjectActionRefused("PROJECT_ACTION_REFUSED")
        original_key = _binding_key(original)
        current_store = _live_store(store)
        def operation() -> dict[str, Any]:
            _boot(inspector, host_binding.boot_session_id, prepare=True)
            current = _current_binding(caller, project_ref, resolve_binding, clock_ms)
            if _binding_key(current) != original_key:
                raise ProjectActionRefused("ACTION_BINDING_CHANGED")
            held = _open_input(store, current.scope, relative_path)
            try:
                if held.sha256 != expected_sha256:
                    raise ProjectActionRefused("ACTION_PREIMAGE_MISMATCH")
                _boot(inspector, host_binding.boot_session_id, prepare=True)
                return {
                    "sha256": held.sha256,
                    "source_identity": _source_identity(held.identity),
                }
            finally:
                _close_held(store, held)

        pending = run_io(operation)
        if not inspect.isawaitable(pending):
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
        try:
            observed = await pending
        except ProjectActionRefused:
            raise
        except Exception as error:
            raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
        final = _current_binding(caller, project_ref, resolve_binding, clock_ms)
        if _binding_key(final) != original_key:
            raise ProjectActionRefused("ACTION_BINDING_CHANGED")
        if store.cleanup_uncertain:
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
        if _live_store(store) != current_store:
            raise ProjectActionRefused("ACTION_BINDING_CHANGED")
        issued_at = _now(clock_ms)
        expires_at = min(
            issued_at + action_ttl_ms,
            final.scope.expires_at_ms,
            caller.expires_at * 1000,
        )
        if expires_at <= issued_at:
            raise ProjectActionRefused("ACTION_EXPIRED")
        prepared = PreparedClosedCommand(
            schema=COMMAND_TOKEN_SCHEMA,
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
            artifact_store_device=current_store.device,
            artifact_store_inode=current_store.inode,
            committed_head=final.scope.committed_head,
            host_id=host_binding.host_id,
            boot_session_id=host_binding.boot_session_id,
            relative_path=relative_path,
            recipe_id=recipe_id,
            preimage_sha256=observed["sha256"],
            source_identity=observed["source_identity"],
            issued_at_ms=issued_at,
            expires_at_ms=expires_at,
        )
        return {
            "status": "PREPARED",
            "action_ref": token_codec.encode_command(prepared),
            "project_ref": project_ref,
            "responsibility_ref": prepared.responsibility_ref,
            "operation_ref": prepared.operation_ref,
            "recipe_id": recipe_id,
            "relative_path": relative_path,
            "preimage_sha256": prepared.preimage_sha256,
            "source_identity": prepared.source_identity,
            "host_id": prepared.host_id,
            "boot_session_id": prepared.boot_session_id,
            "expires_at_ms": expires_at,
        }

    async def run_project_command(
        caller: ActionCaller, action_ref: object
    ) -> Mapping[str, Any]:
        prepared = decode(caller, action_ref, evidence=False)
        original = binding_for(caller, prepared)
        original_key = _binding_key(original)
        def current_scope() -> ActionScope:
            current = binding_for(caller, prepared)
            if _binding_key(current) != original_key:
                raise ProjectActionRefused("ACTION_BINDING_CHANGED")
            _boot(inspector, prepared.boot_session_id, prepare=False)
            return current.scope

        def operation() -> dict[str, Any]:
            held = _open_input(store, current_scope(), prepared.relative_path)
            process: subprocess.Popen[bytes] | None = None
            observed = None
            writer = None
            claimed = False
            returned: dict[str, Any] | None = None

            def reply(value: dict[str, Any]) -> dict[str, Any]:
                nonlocal returned
                returned = value
                return value

            try:
                if held.sha256 != prepared.preimage_sha256:
                    raise ProjectActionRefused("ACTION_PREIMAGE_MISMATCH")
                if _source_identity(held.identity) != prepared.source_identity:
                    raise ProjectActionRefused("ACTION_SOURCE_CHANGED")
                _attest_path(
                    store,
                    host_binding.python_executable,
                    host_binding.python_sha256,
                )
                recipe_path = _recipe_path(host_binding, prepared.recipe_id)
                _attest_path(store, recipe_path, RECIPE_SHA256[prepared.recipe_id])
                try:
                    writer = acquire_store_writer(_live_store(store))
                except ActionArtifactBusy:
                    return reply(
                        _qualified_result(store, prepared, artifact_issuer(caller))
                        or _result_receipt(
                            prepared,
                            effect_state="EFFECT_UNKNOWN",
                            cleanup_uncertain=store.cleanup_uncertain,
                        )
                    )
                except ActionArtifactUncertain as error:
                    raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
                existing = _qualified_result(store, prepared, artifact_issuer(caller))
                if existing is not None:
                    return reply(existing)
                outcome = claim_action(
                    store, _artifact_identity(prepared), claimed_at_ms=_now(clock_ms)
                )
                if not outcome.created:
                    return reply(
                        _result_receipt(
                            prepared,
                            effect_state="EFFECT_UNKNOWN",
                            cleanup_uncertain=outcome.uncertain
                            or store.cleanup_uncertain,
                        )
                    )
                claimed = True
                _revalidate_held(held, current_scope(), prepared.relative_path)
                os.lseek(held.input_fd, 0, os.SEEK_SET)
                argv = [
                    host_binding.python_executable,
                    "-I",
                    "-S",
                    recipe_path,
                    str(held.input_fd),
                    str(held.root_fd),
                    str(prepared.root_device),
                    str(prepared.root_inode),
                    prepared.preimage_sha256,
                    prepared.relative_path,
                ]
                process = subprocess.Popen(
                    argv,
                    cwd="/",
                    env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONSAFEPATH": "1"},
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    close_fds=True,
                    pass_fds=(held.root_fd, held.input_fd),
                    start_new_session=True,
                )
                observed = inspector.inspect(process.pid)
                if (
                    not observed.start_identity
                    or observed.pgid <= 0
                    or observed.session_id <= 0
                    or observed.pgid != process.pid
                    or observed.session_id != process.pid
                    or observed.effective_uid != os.geteuid()
                    or observed.real_uid != os.getuid()
                    or observed.effective_gid != os.getegid()
                    or observed.real_gid != os.getgid()
                ):
                    raise ProcessIdentityError("incomplete command process identity")
                write_action_process(
                    store,
                    _artifact_identity(prepared),
                    pid=process.pid,
                    process_start_identity=observed.start_identity,
                    pgid=observed.pgid,
                    session_id=observed.session_id,
                    host_id=prepared.host_id,
                    boot_session_id=prepared.boot_session_id,
                    recorded_at_ms=_now(clock_ms),
                )
                _revalidate_held(held, current_scope(), prepared.relative_path)
                if _now(clock_ms) >= prepared.expires_at_ms:
                    raise ProjectActionRefused("ACTION_EXPIRED")
                if process.stdin is None:
                    raise OSError("missing launch barrier")
                process.stdin.write(b"\x01")
                process.stdin.flush()
                try:
                    process.stdin.close()
                except OSError:
                    store.mark_cleanup_uncertain("command_barrier_close")
                finally:
                    process.stdin = None
                result = _capture_process(
                    process,
                    deadline_seconds=float(host_binding.process_deadline_seconds),
                    inspector=inspector,
                    process_start_identity=observed.start_identity,
                    pgid=observed.pgid,
                    boot_session_id=prepared.boot_session_id,
                    store=store,
                )
                exit_code, stdout, stderr, stdout_truncated, stderr_truncated, timed_out = result
                details = {
                    "recipe_id": prepared.recipe_id,
                    "exit_code": exit_code,
                    "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                    "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
                    "stdout_bytes": len(stdout),
                    "stderr_bytes": len(stderr),
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    "pid": process.pid,
                    "process_start_identity": observed.start_identity,
                    "pgid": observed.pgid,
                    "session_id": observed.session_id,
                    "released": True,
                    "timed_out": timed_out,
                }
                write_action_blob(store, prepared.action_id, "stdout", stdout)
                write_action_blob(store, prepared.action_id, "stderr", stderr)
                finalize_action(
                    store,
                    _artifact_identity(prepared),
                    effect_state="APPLIED",
                    observed_sha256=prepared.preimage_sha256,
                    completed_at_ms=_now(clock_ms),
                    durability="durable",
                    details=details,
                )
                return reply(
                    _qualified_result(
                        store, prepared, artifact_issuer(caller)
                    )
                    or _result_receipt(
                        prepared,
                        effect_state="EFFECT_UNKNOWN",
                        cleanup_uncertain=True,
                    )
                )
            except ProjectActionRefused:
                if not claimed:
                    raise
                if process is not None:
                    _abort_child(
                        process,
                        inspector=inspector,
                        boot_session_id=prepared.boot_session_id,
                        expected_start_identity=(
                            None if observed is None else observed.start_identity
                        ),
                        expected_pgid=None if observed is None else observed.pgid,
                        deadline_seconds=float(host_binding.process_deadline_seconds),
                        store=store,
                    )
                return reply(
                    _result_receipt(
                        prepared,
                        effect_state="EFFECT_UNKNOWN",
                        cleanup_uncertain=True,
                    )
                )
            except (ActionArtifactError, ActionArtifactUncertain, OSError, ProcessIdentityError, ValueError, TypeError):
                if process is not None:
                    _abort_child(
                        process,
                        inspector=inspector,
                        boot_session_id=prepared.boot_session_id,
                        expected_start_identity=(
                            None if observed is None else observed.start_identity
                        ),
                        expected_pgid=None if observed is None else observed.pgid,
                        deadline_seconds=float(host_binding.process_deadline_seconds),
                        store=store,
                    )
                if claimed:
                    return reply(
                        _result_receipt(
                            prepared,
                            effect_state="EFFECT_UNKNOWN",
                            cleanup_uncertain=True,
                        )
                    )
                raise ProjectActionRefused("ACTION_UNAVAILABLE") from None
            finally:
                if writer is not None:
                    try:
                        writer.release()
                    except ActionArtifactUncertain:
                        store.mark_cleanup_uncertain("command_writer_release")
                _close_held(store, held)
                if returned is not None and store.cleanup_uncertain:
                    returned["cleanup_state"] = "UNCERTAIN"

        pending = run_io(operation)
        if not inspect.isawaitable(pending):
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
        try:
            return await pending
        except asyncio.CancelledError:
            return _result_receipt(
                prepared, effect_state="EFFECT_UNKNOWN", cleanup_uncertain=False
            )
        except ProjectActionRefused:
            raise
        except Exception:
            return _result_receipt(
                prepared, effect_state="EFFECT_UNKNOWN", cleanup_uncertain=False
            )

    def historical_binding(caller: ActionCaller, prepared: PreparedClosedCommand) -> None:
        binding_for(caller, prepared)

    def unclaimed_receipt(
        prepared: PreparedClosedCommand, action_ref: object
    ) -> dict[str, Any]:
        # No claim artifact exists, so no process was ever spawned for this
        # reference through this port.  Absence alone still stays unknown: the
        # run may have been admitted and lost before its claim.  It becomes
        # NOT_APPLIED only when the durable admission ledger proves the run was
        # refused before dispatch and never accepted for this exact reference.
        # The ledger is read last so a run admitted meanwhile is seen.
        effect = "EFFECT_UNKNOWN"
        if admission_evidence is not None:
            try:
                verdict = admission_evidence(action_ref)
            except Exception:
                verdict = None
            if verdict == ADMISSION_REFUSED_ONLY:
                effect = "NOT_APPLIED"
        return _result_receipt(
            prepared, effect_state=effect, cleanup_uncertain=store.cleanup_uncertain
        )


    async def read_action_artifact(
        caller: ActionCaller, arguments: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        try:
            request = dict(arguments)
            if (
                not set(request) <= _ARTIFACT_READ_KEYS
                or "artifact_ref" not in request
            ):
                raise ProjectActionRefused("ARTIFACT_INVALID")
            offset = request.get("offset", 0)
            maximum = request.get("max_bytes", MAX_ARTIFACT_CHUNK_BYTES)
            if (
                type(offset) is not int
                or not 0 <= offset <= MAX_ARTIFACT_BYTES
                or type(maximum) is not int
                or not 1 <= maximum <= MAX_ARTIFACT_CHUNK_BYTES
            ):
                raise ProjectActionRefused("ARTIFACT_RANGE_INVALID")
        except ProjectActionRefused:
            raise
        except Exception as error:
            raise ProjectActionRefused("ARTIFACT_INVALID") from error
        reference = decode_artifact(caller, request["artifact_ref"])

        def operation() -> dict[str, Any]:
            if _now(clock_ms) >= reference.expires_at_ms:
                raise ProjectActionRefused("ARTIFACT_EXPIRED")
            prepared, initial = artifact_binding_for(caller, reference)
            initial_key = _binding_key(initial)
            status, evidence = _qualified_evidence(_live_store(store), prepared)
            if status != "qualified" or evidence is None:
                raise ProjectActionRefused("ARTIFACT_UNAVAILABLE")
            raw = evidence.stdout if reference.stream == "stdout" else evidence.stderr
            truncated = evidence.details[f"{reference.stream}_truncated"]
            media_type = artifact_media_type(prepared.recipe_id, reference.stream)
            digest = hashlib.sha256(raw).hexdigest()
            artifact_id = derive_artifact_id(
                action_id=prepared.action_id,
                project_ref=prepared.project_ref,
                generation=prepared.generation,
                recipe_id=prepared.recipe_id,
                relative_path=prepared.relative_path,
                preimage_sha256=prepared.preimage_sha256,
                source_identity=prepared.source_identity,
                stream=reference.stream,
                media_type=media_type,
                byte_length=len(raw),
                sha256=digest,
                truncated=truncated,
            )
            if (
                reference.artifact_id != artifact_id
                or reference.media_type != media_type
                or reference.byte_length != len(raw)
                or reference.sha256 != digest
                or reference.truncated is not truncated
            ):
                raise ProjectActionRefused("ARTIFACT_UNAVAILABLE")
            if offset > len(raw):
                raise ProjectActionRefused("ARTIFACT_RANGE_INVALID")
            end = min(len(raw), offset + maximum)
            content_kind = "blob"
            payload: dict[str, Any] = {}
            if media_type == TEXT_MEDIA_TYPE:
                try:
                    raw.decode("utf-8", errors="strict")
                    raw[:offset].decode("utf-8", errors="strict")
                except UnicodeError as error:
                    raise ProjectActionRefused("ARTIFACT_RANGE_INVALID") from error
                while end > offset:
                    try:
                        selected_text = raw[offset:end].decode(
                            "utf-8", errors="strict"
                        )
                        break
                    except UnicodeDecodeError as error:
                        if error.reason != "unexpected end of data":
                            raise ProjectActionRefused(
                                "ARTIFACT_RANGE_INVALID"
                            ) from error
                        end -= 1
                else:
                    if offset < len(raw):
                        raise ProjectActionRefused("ARTIFACT_RANGE_INVALID")
                    selected_text = ""
                selected = raw[offset:end]
                content_kind = "text"
                payload["text"] = selected_text
            else:
                selected = raw[offset:end]
                if (
                    media_type == PNG_MEDIA_TYPE
                    and offset == 0
                    and end == len(raw)
                    and len(raw) <= MAX_DIRECT_IMAGE_BYTES
                ):
                    content_kind = "image"
                payload["_payload_base64"] = base64.b64encode(selected).decode(
                    "ascii"
                )
            confirmed = read_action_blob(
                _live_store(store), prepared.action_id, reference.stream
            )
            if confirmed is None or confirmed != raw:
                raise ProjectActionRefused("ARTIFACT_UNAVAILABLE")
            _prepared, final = artifact_binding_for(caller, reference)
            if _binding_key(final) != initial_key:
                raise ProjectActionRefused("ARTIFACT_BINDING_CHANGED")
            if _now(clock_ms) >= reference.expires_at_ms:
                raise ProjectActionRefused("ARTIFACT_EXPIRED")
            response = {
                "status": "OK",
                "artifact_id": artifact_id,
                "owner": ARTIFACT_OWNER,
                "stream": reference.stream,
                "media_type": media_type,
                "byte_length": len(raw),
                "sha256": digest,
                "truncated": truncated,
                "size_state": _artifact_size_state(len(raw), truncated),
                "offset": offset,
                "returned_bytes": len(selected),
                "next_offset": None if end >= len(raw) else end,
                "chunk_sha256": hashlib.sha256(selected).hexdigest(),
                "content_kind": content_kind,
                "producer": _artifact_producer(prepared),
                "source": _artifact_source(prepared),
            }
            response.update(payload)
            return response

        pending = run_io(operation)
        if not inspect.isawaitable(pending):
            raise ProjectActionRefused("ARTIFACT_UNAVAILABLE")
        try:
            observed = await pending
            if _now(clock_ms) >= reference.expires_at_ms:
                raise ProjectActionRefused("ARTIFACT_EXPIRED")
            return observed
        except asyncio.CancelledError:
            raise
        except ProjectActionRefused:
            raise
        except Exception as error:
            raise ProjectActionRefused("ARTIFACT_UNAVAILABLE") from error

    async def reconcile_action(
        caller: ActionCaller, action_ref: object
    ) -> Mapping[str, Any]:
        prepared = decode(caller, action_ref, evidence=True)

        def operation() -> dict[str, Any]:
            historical_binding(caller, prepared)
            return _qualified_result(
                _live_store(store), prepared, artifact_issuer(caller)
            ) or unclaimed_receipt(
                prepared, action_ref
            )

        pending = run_io(operation)
        if not inspect.isawaitable(pending):
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
        try:
            return await pending
        except asyncio.CancelledError:
            raise
        except ProjectActionRefused:
            raise
        except Exception:
            return _result_receipt(
                prepared, effect_state="EFFECT_UNKNOWN", cleanup_uncertain=True
            )

    async def read_action_result(
        caller: ActionCaller, arguments: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        try:
            request = dict(arguments)
            if not set(request) <= _READ_KEYS or not {"action_ref", "stream"} <= set(request):
                raise ProjectActionRefused("ACTION_INVALID")
            stream = request["stream"]
            start_line = request.get("start_line", 0)
            max_lines = request.get("max_lines", 16)
            max_content_bytes = request.get("max_content_bytes", 4096)
            if (
                stream not in {"stdout", "stderr"}
                or type(start_line) is not int
                or start_line < 0
                or type(max_lines) is not int
                or not 1 <= max_lines <= MAX_PAGE_LINES
                or type(max_content_bytes) is not int
                or not 1 <= max_content_bytes <= MAX_PAGE_BYTES
            ):
                raise ProjectActionRefused("ACTION_INVALID")
        except ProjectActionRefused:
            raise
        except Exception as error:
            raise ProjectActionRefused("ACTION_INVALID") from error
        prepared = decode(caller, request["action_ref"], evidence=True)

        def operation() -> dict[str, Any]:
            historical_binding(caller, prepared)
            receipt = _qualified_result(_live_store(store), prepared)
            if receipt is None or receipt["effect_state"] != "APPLIED":
                return receipt or unclaimed_receipt(prepared, request["action_ref"])
            try:
                raw = read_action_blob(store, prepared.action_id, stream)
                if raw is None:
                    raise ActionArtifactUncertain("missing command stream")
                text = raw.decode("utf-8")
            except (ActionArtifactError, ActionArtifactUncertain, UnicodeError):
                return _result_receipt(
                    prepared, effect_state="EFFECT_UNKNOWN", cleanup_uncertain=True
                )
            lines = text.splitlines(keepends=True)
            selected: list[str] = []
            selected_bytes = 0
            index = min(start_line, len(lines))
            while index < len(lines) and len(selected) < max_lines:
                encoded = lines[index].encode("utf-8")
                if selected_bytes + len(encoded) > max_content_bytes:
                    break
                selected.append(lines[index])
                selected_bytes += len(encoded)
                index += 1
            if index == min(start_line, len(lines)) and index < len(lines):
                raise ProjectActionRefused("ACTION_INVALID")
            return {
                "status": "OK",
                "stream": stream,
                "content": "".join(selected),
                "line_start": min(start_line, len(lines)),
                "line_end": index,
                "total_lines": len(lines),
                "next_line": None if index >= len(lines) else index,
                "truncated": receipt["truncated"],
                "file_sha256": hashlib.sha256(raw).hexdigest(),
                "exit_code": receipt["exit_code"],
                "effect_state": receipt["effect_state"],
                "isError": False,
            }

        pending = run_io(operation)
        if not inspect.isawaitable(pending):
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
        try:
            return await pending
        except asyncio.CancelledError:
            raise
        except ProjectActionRefused:
            raise
        except Exception:
            return _result_receipt(
                prepared, effect_state="EFFECT_UNKNOWN", cleanup_uncertain=True
            )

    return (
        prepare_project_command,
        run_project_command,
        read_action_result,
        read_action_artifact,
        reconcile_action,
    )


__all__ = ["create_command_port"]
