"""Descriptor-relative prepared text patch owner for Workbench Action.

The port is deliberately narrower than a filesystem API. Preparation is
read-only. Commit consumes one signed prepared action and performs at most one
same-directory atomic file publication. Reconciliation never replays a write.
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

from .contracts import (
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
        }
    )

    def __init__(self, code: str = "PROJECT_ACTION_REFUSED") -> None:
        if code not in self._CODES:
            raise ValueError("unknown project action refusal")
        self.code = code
        super().__init__(code)


ActionBindingResolver = Callable[[ActionCaller, str], ProjectActionBinding | None]
ActionExecutor = Callable[[Callable[[], dict[str, Any]]], Awaitable[dict[str, Any]]]


@dataclasses.dataclass(frozen=True)
class _FileSnapshot:
    raw: bytes
    sha256: str
    mode: int
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
        scope.owner_ref,
        scope.generation,
        scope.allowed_paths,
        scope.expires_at_ms,
        scope.committed_head,
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
        or scope.owner_ref != prepared.owner_ref
        or scope.generation != prepared.generation
        or scope.root_device != prepared.root_device
        or scope.root_inode != prepared.root_inode
        or scope.committed_head != prepared.committed_head
        or prepared.relative_path not in scope.allowed_paths
    ):
        raise ProjectActionRefused("ACTION_BINDING_CHANGED")


def _open_parent(scope: ActionScope, relative_path: str) -> tuple[list[int], int, str]:
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
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                pass
        raise


def _read_leaf(
    scope: ActionScope, relative_path: str, *, allow_absent: bool
) -> _FileSnapshot | None:
    fds, parent, leaf = _open_parent(scope, relative_path)
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
        if file_fd >= 0:
            try:
                os.close(file_fd)
            except OSError:
                pass
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                pass


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


def _publish_candidate(
    *,
    scope: ActionScope,
    prepared: PreparedTextPatch,
    candidate: bytes,
    mode: int,
    confirm_binding: Callable[[], ActionScope],
) -> dict[str, Any]:
    fds, parent, leaf = _open_parent(scope, prepared.relative_path)
    temp_fd = -1
    temp_name = f".mmx-workbench-action-{prepared.action_id}.tmp"
    effect_started = False
    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        temp_fd = os.open(temp_name, flags, 0o600, dir_fd=parent)
        _write_all(temp_fd, candidate)
        os.fchmod(temp_fd, mode)
        os.fsync(temp_fd)
        temp_stat = os.fstat(temp_fd)
        if not stat.S_ISREG(temp_stat.st_mode) or temp_stat.st_nlink != 1:
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
        os.close(temp_fd)
        temp_fd = -1

        current_scope = confirm_binding()
        if (
            current_scope.root_device != scope.root_device
            or current_scope.root_inode != scope.root_inode
        ):
            raise ProjectActionRefused("ACTION_BINDING_CHANGED")
        current = _read_leaf(
            current_scope,
            prepared.relative_path,
            allow_absent=prepared.mode == "CREATE",
        )
        if prepared.mode == "CREATE":
            if current is not None:
                return {
                    "effect_state": "APPLIED"
                    if current.sha256 == prepared.postimage_sha256
                    else "EFFECT_UNKNOWN",
                    "observed_sha256": current.sha256,
                }
            if os.link not in os.supports_dir_fd:
                raise ProjectActionRefused("ACTION_UNAVAILABLE")
            os.link(
                temp_name,
                leaf,
                src_dir_fd=parent,
                dst_dir_fd=parent,
                follow_symlinks=False,
            )
            effect_started = True
            os.unlink(temp_name, dir_fd=parent)
        else:
            if current is None or current.sha256 != prepared.preimage_sha256:
                observed = None if current is None else current.sha256
                return {"effect_state": "EFFECT_UNKNOWN", "observed_sha256": observed}
            expected = _candidate_from_snapshot(
                current, old_text=prepared.old_text or "", new_text=prepared.new_text
            )
            if hashlib.sha256(expected).hexdigest() != prepared.postimage_sha256:
                raise ProjectActionRefused("ACTION_INVALID")
            if os.rename not in os.supports_dir_fd:
                raise ProjectActionRefused("ACTION_UNAVAILABLE")
            os.rename(temp_name, leaf, src_dir_fd=parent, dst_dir_fd=parent)
            effect_started = True
        try:
            os.fsync(parent)
        except OSError:
            # Publication may already be visible. Reconciliation below decides.
            pass
        final_scope = confirm_binding()
        final = _read_leaf(final_scope, prepared.relative_path, allow_absent=True)
        observed = None if final is None else final.sha256
        return {
            "effect_state": "APPLIED"
            if observed == prepared.postimage_sha256
            else "EFFECT_UNKNOWN",
            "observed_sha256": observed,
        }
    except FileExistsError:
        current = _read_leaf(scope, prepared.relative_path, allow_absent=True)
        observed = None if current is None else current.sha256
        return {
            "effect_state": "APPLIED"
            if observed == prepared.postimage_sha256
            else "EFFECT_UNKNOWN",
            "observed_sha256": observed,
        }
    except ProjectActionRefused:
        if effect_started:
            return {"effect_state": "EFFECT_UNKNOWN", "observed_sha256": None}
        raise
    except (OSError, TypeError, ValueError, OverflowError) as error:
        if effect_started:
            return {"effect_state": "EFFECT_UNKNOWN", "observed_sha256": None}
        raise ProjectActionRefused("ACTION_UNAVAILABLE") from error
    finally:
        if temp_fd >= 0:
            try:
                os.close(temp_fd)
            except OSError:
                pass
        try:
            os.unlink(temp_name, dir_fd=parent)
        except (FileNotFoundError, OSError):
            pass
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                pass


def create_text_patch_port(
    *,
    resolve_binding: ActionBindingResolver,
    clock_ms: Callable[[], int],
    run_io: ActionExecutor,
    token_codec: ActionTokenCodec,
    action_ttl_ms: int = MAX_ACTION_TTL_MS,
):
    """Create prepare/commit/reconcile callbacks over existing owner services."""

    if not all(callable(value) for value in (resolve_binding, clock_ms, run_io)):
        raise TypeError("explicit binding, clock and I/O integration required")
    if not isinstance(token_codec, ActionTokenCodec):
        raise TypeError("explicit action token codec required")
    if type(action_ttl_ms) is not int or not 1000 <= action_ttl_ms <= MAX_ACTION_TTL_MS:
        raise ValueError("action ttl is outside the closed F0 range")

    async def prepare(caller: ActionCaller, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            request = dict(arguments)
            if set(request) - _REQUEST_KEYS:
                raise ProjectActionRefused("ACTION_INVALID")
            project_ref = request["project_ref"]
            relative_path = validate_relative_path(request["relative_path"])
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
            scope = current_scope()
            snapshot = _read_leaf(scope, relative_path, allow_absent=mode == "CREATE")
            if mode == "CREATE":
                if snapshot is not None:
                    raise ProjectActionRefused("ACTION_PREIMAGE_MISMATCH")
                candidate = new_text.encode("utf-8")
                preimage = None
            else:
                if snapshot is None or snapshot.sha256 != expected_sha:
                    raise ProjectActionRefused("ACTION_PREIMAGE_MISMATCH")
                candidate = _candidate_from_snapshot(
                    snapshot, old_text=old_text or "", new_text=new_text
                )
                preimage = snapshot.sha256
            current_scope()
            return {
                "preimage_sha256": preimage,
                "postimage_sha256": hashlib.sha256(candidate).hexdigest(),
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
            owner_ref=final.scope.owner_ref,
            generation=final.scope.generation,
            root_device=final.scope.root_device,
            root_inode=final.scope.root_inode,
            committed_head=final.scope.committed_head,
            relative_path=relative_path,
            mode=mode,
            preimage_sha256=result["preimage_sha256"],
            postimage_sha256=result["postimage_sha256"],
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
            "relative_path": relative_path,
            "preimage_sha256": prepared.preimage_sha256,
            "postimage_sha256": prepared.postimage_sha256,
            "expires_at_ms": expires_at,
        }

    def _decode_for_caller(caller: ActionCaller, action_ref: object) -> PreparedTextPatch:
        validate_action_caller(caller)
        try:
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

    async def commit(caller: ActionCaller, action_ref: object) -> Mapping[str, Any]:
        prepared = _decode_for_caller(caller, action_ref)
        original = _binding_for_prepared(caller, prepared)
        binding_key = _binding_key(original)

        def current_scope() -> ActionScope:
            current = _binding_for_prepared(caller, prepared)
            if _binding_key(current) != binding_key:
                raise ProjectActionRefused("ACTION_BINDING_CHANGED")
            return current.scope

        def operation() -> dict[str, Any]:
            scope = current_scope()
            current = _read_leaf(
                scope,
                prepared.relative_path,
                allow_absent=prepared.mode == "CREATE",
            )
            if current is not None and current.sha256 == prepared.postimage_sha256:
                return {"effect_state": "APPLIED", "observed_sha256": current.sha256}
            if prepared.mode == "CREATE":
                if current is not None:
                    return {"effect_state": "EFFECT_UNKNOWN", "observed_sha256": current.sha256}
                candidate = prepared.new_text.encode("utf-8")
                file_mode = 0o644
            else:
                if current is None or current.sha256 != prepared.preimage_sha256:
                    observed = None if current is None else current.sha256
                    return {"effect_state": "EFFECT_UNKNOWN", "observed_sha256": observed}
                candidate = _candidate_from_snapshot(
                    current,
                    old_text=prepared.old_text or "",
                    new_text=prepared.new_text,
                )
                file_mode = current.mode
            if hashlib.sha256(candidate).hexdigest() != prepared.postimage_sha256:
                raise ProjectActionRefused("ACTION_INVALID")
            return _publish_candidate(
                scope=scope,
                prepared=prepared,
                candidate=candidate,
                mode=file_mode,
                confirm_binding=current_scope,
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
        if result.get("effect_state") not in _EFFECTS:
            raise ProjectActionRefused("ACTION_UNAVAILABLE")
        return {
            "status": "OK",
            "effect_state": result["effect_state"],
            "project_ref": prepared.project_ref,
            "relative_path": prepared.relative_path,
            "preimage_sha256": prepared.preimage_sha256,
            "postimage_sha256": prepared.postimage_sha256,
            "observed_sha256": result.get("observed_sha256"),
        }

    async def reconcile(caller: ActionCaller, action_ref: object) -> Mapping[str, Any]:
        prepared = _decode_for_caller(caller, action_ref)
        binding = _binding_for_prepared(caller, prepared)
        binding_key = _binding_key(binding)

        def operation() -> dict[str, Any]:
            current = _binding_for_prepared(caller, prepared)
            if _binding_key(current) != binding_key:
                raise ProjectActionRefused("ACTION_BINDING_CHANGED")
            snapshot = _read_leaf(
                current.scope,
                prepared.relative_path,
                allow_absent=True,
            )
            observed = None if snapshot is None else snapshot.sha256
            if observed == prepared.postimage_sha256:
                effect = "APPLIED"
            elif prepared.mode == "CREATE" and observed is None:
                effect = "NOT_APPLIED"
            elif prepared.mode == "REPLACE" and observed == prepared.preimage_sha256:
                effect = "NOT_APPLIED"
            else:
                effect = "EFFECT_UNKNOWN"
            return {"effect_state": effect, "observed_sha256": observed}

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
            "relative_path": prepared.relative_path,
            "preimage_sha256": prepared.preimage_sha256,
            "postimage_sha256": prepared.postimage_sha256,
            "observed_sha256": result.get("observed_sha256"),
        }

    return prepare, commit, reconcile


__all__ = [
    "ActionBindingResolver",
    "ActionExecutor",
    "MAX_FILE_BYTES",
    "ProjectActionRefused",
    "create_text_patch_port",
]
