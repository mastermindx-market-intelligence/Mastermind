"""Pure-effect Workbench adapter for the Personal-Pro tunnel profile.

The adapter owns one already-selected project descriptor and composes the
existing descriptor-relative Workbench observer. It never writes a project
file, starts a process, opens a network socket, publishes a job, or persists a
prepared action. Preview tools return data only.
"""
from __future__ import annotations

import dataclasses
import difflib
import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
import re
import stat
import threading
import time
from typing import Any

from integrations.workbench_read_mcp.observer import ReadRefusal, ReadScope, observe_file
from .schemas import (
    MAX_ARGUMENT_BYTES,
    MAX_PREVIEW_DIFF_BYTES,
    MAX_PREVIEW_TEXT_BYTES,
    MAX_RESULT_BYTES,
    PROFILE_PRO_READ_PREPARE,
    LocalProfileConfig,
    LocalProfileError,
    RESULT_SCHEMA,
    SERVER_VERSION,
    TOOL_NAMES,
    canonical_json,
)

_SAFE_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")
_PROJECT_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")


def _valid_scope_reference(value: object) -> bool:
    if (
        type(value) is not str
        or not value
        or len(value) > 256
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return False
    try:
        value.encode("utf-8")
    except UnicodeError:
        return False
    return True


@dataclasses.dataclass(frozen=True)
class _OwnedProject:
    fd: int
    device: int
    inode: int
    uid: int
    mode: int


class _ReadOperations:
    """Pure read/preview operations over one current owner-supplied scope."""

    def __init__(
        self,
        *,
        project_ref: str,
        profile: str,
        allowed_paths: tuple[str, ...],
        resolve_scope: Callable[[], ReadScope],
        clock_ms: Callable[[], int],
        on_cleanup_uncertain: Callable[[], None] | None = None,
    ) -> None:
        self._project_ref = project_ref
        self._profile = profile
        self._allowed_paths = allowed_paths
        self._resolve_scope = resolve_scope
        self._clock_ms = clock_ms
        self._on_cleanup_uncertain = on_cleanup_uncertain
        self._cleanup_uncertainty: LocalProfileError | None = None
        self._cleanup_uncertainty_lock = threading.Lock()
        self._port_closed = False

    def _record_cleanup_uncertainty(self) -> None:
        claimed_callback: Callable[[], None] | None = None
        with self._cleanup_uncertainty_lock:
            if self._cleanup_uncertainty is None:
                self._cleanup_uncertainty = LocalProfileError(
                    "PROJECT_CLEANUP_UNCERTAIN"
                )
                claimed_callback = self._on_cleanup_uncertain
        if claimed_callback is not None:
            try:
                claimed_callback()
            except Exception:
                pass

    def _raise_if_cleanup_uncertain(self) -> None:
        if self._cleanup_uncertainty is not None:
            raise self._cleanup_uncertainty

    def _scope(self) -> ReadScope:
        self._raise_if_cleanup_uncertain()
        if self._port_closed:
            raise LocalProfileError("PROJECT_READ_REFUSED")
        try:
            now_ms = self._clock_ms()
            scope = self._resolve_scope()
        except LocalProfileError:
            raise
        except ReadRefusal as error:
            if error.code in {
                "FILE_CHANGED",
                "FILE_IDENTITY_CHANGED",
                "ROOT_IDENTITY_CHANGED",
                "ANCESTRY_CHANGED",
                "SCOPE_CHANGED",
            }:
                raise LocalProfileError("SOURCE_CHANGED") from None
            raise LocalProfileError("PROJECT_READ_REFUSED") from None
        except Exception:
            raise LocalProfileError("PROJECT_READ_REFUSED") from None
        if type(now_ms) is not int or not 0 <= now_ms < 2**63:
            raise LocalProfileError("PROJECT_READ_REFUSED")
        if type(scope) is not ReadScope:
            raise LocalProfileError("PROJECT_READ_REFUSED")
        if (
            type(scope.root_fd) is not int
            or scope.root_fd < 0
            or type(scope.root_device) is not int
            or scope.root_device < 0
            or type(scope.root_inode) is not int
            or scope.root_inode < 0
            or type(scope.expires_at_ms) is not int
            or scope.expires_at_ms <= now_ms
            or scope.allowed_paths != self._allowed_paths
            or any(
                not _valid_scope_reference(value)
                for value in (scope.context_ref, scope.owner_ref, scope.generation)
            )
            or (
                scope.committed_head is not None
                and (
                    type(scope.committed_head) is not str
                    or _HEX40.fullmatch(scope.committed_head) is None
                )
            )
        ):
            raise LocalProfileError("PROJECT_READ_REFUSED")
        try:
            current = os.fstat(scope.root_fd)
        except (OSError, OverflowError, ValueError):
            raise LocalProfileError("SOURCE_CHANGED") from None
        if (
            not stat.S_ISDIR(current.st_mode)
            or current.st_dev != scope.root_device
            or current.st_ino != scope.root_inode
        ):
            raise LocalProfileError("SOURCE_CHANGED")
        return scope

    def close(self) -> None:
        """Revoke this local port without assuming ownership of a descriptor."""

        self._port_closed = True
        self._raise_if_cleanup_uncertain()

    def _result(self, tool: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "schema": RESULT_SCHEMA,
            "tool": tool,
            "ok": True,
            "server_version": SERVER_VERSION,
            "profile": self._profile,
            "mutation_allowed": False,
            "project_ref": self._project_ref,
            "data": data,
            "error": None,
        }
        if len(canonical_json(payload)) > MAX_RESULT_BYTES:
            raise LocalProfileError("INTERNAL_ERROR")
        return payload

    def _error(self, tool: str, code: str) -> dict[str, Any]:
        return {
            "schema": RESULT_SCHEMA,
            "tool": tool,
            "ok": False,
            "server_version": SERVER_VERSION,
            "profile": self._profile,
            "mutation_allowed": False,
            "project_ref": self._project_ref,
            "data": None,
            "error": {"code": code},
        }

    @staticmethod
    def _snapshot_arguments(arguments: object) -> dict[str, Any]:
        try:
            raw = canonical_json(arguments)
            if len(raw) > MAX_ARGUMENT_BYTES:
                raise ValueError
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise LocalProfileError("INVALID_REQUEST") from None
        if type(value) is not dict:
            raise LocalProfileError("INVALID_REQUEST")
        return value

    def call(self, name: str, arguments: object) -> dict[str, Any]:
        if name not in TOOL_NAMES:
            return self._error("unknown", "TOOL_NOT_AVAILABLE")
        try:
            self._raise_if_cleanup_uncertain()
            request = self._snapshot_arguments(arguments)
            scope = self._scope()
            if name == "workspace_manifest":
                return self._manifest(request, scope)
            if name == "read_project_file":
                return self._read(name, request)
            if name == "preview_text_replace":
                return self._preview_replace(name, request)
            if name == "preview_project_command":
                return self._preview_command(name, request)
            return self._error(name, "TOOL_NOT_AVAILABLE")
        except LocalProfileError as error:
            return self._error(name, error.code)
        except Exception:
            return self._error(name, "INTERNAL_ERROR")

    def _manifest(
        self, request: dict[str, Any], scope: ReadScope
    ) -> dict[str, Any]:
        if request:
            raise LocalProfileError("INVALID_REQUEST")
        return self._result(
            "workspace_manifest",
            {
                "capability_state": "BUILT_NOT_PROVEN",
                "transport": "stdio-via-secure-mcp-tunnel",
                "project_ref": self._project_ref,
                "profile": self._profile,
                "allowed_paths": list(scope.allowed_paths),
                "committed_head": scope.committed_head,
                "lease_expires_at_ms": scope.expires_at_ms,
                "context_ref": scope.context_ref,
                "owner_ref": scope.owner_ref,
                "generation": scope.generation,
                "effects": {
                    "file_write": False,
                    "process_start": False,
                    "network_call": False,
                    "durable_prepare": False,
                },
            },
        )

    def _observe(self, request: dict[str, Any], *, full_preview: bool = False) -> dict[str, Any]:
        allowed = {"relative_path", "line_start", "line_count", "expected_sha256"}
        if set(request) - allowed or "relative_path" not in request:
            raise LocalProfileError("INVALID_REQUEST")
        relative_path = request.get("relative_path")
        if type(relative_path) is not str or relative_path not in self._allowed_paths:
            raise LocalProfileError("PROJECT_READ_REFUSED")
        selected: dict[str, Any] = {"relative_path": relative_path}
        if full_preview:
            selected.update({"start_line": 0, "max_lines": 512, "max_content_bytes": 32768})
        else:
            if "line_start" in request:
                selected["start_line"] = request["line_start"]
            if "line_count" in request:
                selected["max_lines"] = request["line_count"]
        if "expected_sha256" in request:
            selected["expected_sha256"] = request["expected_sha256"]
        try:
            return observe_file(
                selected,
                self._scope,
                clock_ms=self._clock_ms,
                on_cleanup_uncertain=self._record_cleanup_uncertainty,
            )
        except ReadRefusal as error:
            if error.code == "CLEANUP_UNCERTAIN":
                self._record_cleanup_uncertainty()
                raise self._cleanup_uncertainty from None
            if error.code == "PREIMAGE_MISMATCH":
                raise LocalProfileError("PREIMAGE_MISMATCH") from None
            if error.code in {
                "FILE_CHANGED",
                "FILE_IDENTITY_CHANGED",
                "ROOT_IDENTITY_CHANGED",
                "ANCESTRY_CHANGED",
                "SCOPE_CHANGED",
            }:
                raise LocalProfileError("SOURCE_CHANGED") from None
            raise LocalProfileError("PROJECT_READ_REFUSED") from None

    def _read(self, tool: str, request: dict[str, Any]) -> dict[str, Any]:
        observed = self._observe(request)
        observed = {**observed, "project_ref": self._project_ref}
        return self._result(tool, observed)

    def _preview_replace(self, tool: str, request: dict[str, Any]) -> dict[str, Any]:
        required = {"relative_path", "expected_sha256", "old_text", "new_text"}
        if set(request) != required:
            raise LocalProfileError("INVALID_REQUEST")
        relative_path = request["relative_path"]
        expected = request["expected_sha256"]
        old_text = request["old_text"]
        new_text = request["new_text"]
        if (
            type(relative_path) is not str
            or relative_path not in self._allowed_paths
            or type(expected) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected) is None
            or type(old_text) is not str
            or not old_text
            or type(new_text) is not str
            or len(old_text.encode("utf-8")) > MAX_PREVIEW_TEXT_BYTES
            or len(new_text.encode("utf-8")) > MAX_PREVIEW_TEXT_BYTES
        ):
            raise LocalProfileError("INVALID_REQUEST")
        observed = self._observe(
            {"relative_path": relative_path, "expected_sha256": expected},
            full_preview=True,
        )
        if observed.get("truncated"):
            raise LocalProfileError("PREVIEW_TOO_LARGE")
        content = observed.get("content")
        if type(content) is not str or content.count(old_text) != 1:
            raise LocalProfileError("PREVIEW_NOT_APPLICABLE")
        proposed = content.replace(old_text, new_text, 1)
        proposed_raw = proposed.encode("utf-8")
        diff = "".join(
            difflib.unified_diff(
                content.splitlines(keepends=True),
                proposed.splitlines(keepends=True),
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
                n=3,
            )
        )
        diff_raw = diff.encode("utf-8")
        if len(diff_raw) > MAX_PREVIEW_DIFF_BYTES:
            raise LocalProfileError("PREVIEW_TOO_LARGE")
        proposed_hash = hashlib.sha256(proposed_raw).hexdigest()
        change_digest = hashlib.sha256(
            canonical_json(
                {
                    "project_ref": self._project_ref,
                    "relative_path": relative_path,
                    "preimage_sha256": expected,
                    "proposed_sha256": proposed_hash,
                    "diff_sha256": hashlib.sha256(diff_raw).hexdigest(),
                }
            )
        ).hexdigest()
        return self._result(
            tool,
            {
                "status": "PREVIEW_ONLY",
                "relative_path": relative_path,
                "preimage_sha256": expected,
                "proposed_sha256": proposed_hash,
                "diff": diff,
                "change_digest": change_digest,
                "applied": False,
                "persisted": False,
            },
        )

    @staticmethod
    def _validated_target(value: object, *, test_only: bool = False) -> str:
        if type(value) is not str or _SAFE_TARGET.fullmatch(value) is None:
            raise LocalProfileError("INVALID_REQUEST")
        if value.startswith(("/", "~", ".git/")) or ".." in value.split("/") or "\\" in value:
            raise LocalProfileError("INVALID_REQUEST")
        if test_only and (not value.startswith("tests/") or not value.endswith(".py")):
            raise LocalProfileError("INVALID_REQUEST")
        return value

    def _preview_command(self, tool: str, request: dict[str, Any]) -> dict[str, Any]:
        if set(request) - {"recipe", "targets"} or "recipe" not in request:
            raise LocalProfileError("INVALID_REQUEST")
        recipe = request.get("recipe")
        targets = request.get("targets", [])
        if type(recipe) is not str or type(targets) is not list or len(targets) > 16:
            raise LocalProfileError("INVALID_REQUEST")
        if recipe == "git_diff_check":
            if targets:
                raise LocalProfileError("INVALID_REQUEST")
            argv = ["git", "diff", "--check"]
        elif recipe == "pytest_targets":
            if not targets:
                raise LocalProfileError("INVALID_REQUEST")
            selected = [self._validated_target(item, test_only=True) for item in targets]
            argv = ["python3", "-m", "pytest", "-q", *selected]
        elif recipe == "compileall_paths":
            if not targets:
                raise LocalProfileError("INVALID_REQUEST")
            selected = [self._validated_target(item) for item in targets]
            argv = ["python3", "-m", "compileall", *selected]
        else:
            raise LocalProfileError("INVALID_REQUEST")
        digest = hashlib.sha256(
            canonical_json({"recipe": recipe, "argv": argv})
        ).hexdigest()
        return self._result(
            tool,
            {
                "status": "PREVIEW_ONLY",
                "recipe": recipe,
                "argv": argv,
                "command_digest": digest,
                "started": False,
                "process_ref": None,
            },
        )


class LocalWorkbenchGateway(_ReadOperations):
    """One fixed project/profile generation; model inputs cannot retarget it."""

    def __init__(self, config: LocalProfileConfig, project: _OwnedProject) -> None:
        self.config = config
        self._project = project
        fingerprint = {
            "profile": config.profile,
            "project_ref": config.project_ref,
            "allowed_paths": config.allowed_paths,
            "committed_head": config.committed_head,
            "root_device": project.device,
            "root_inode": project.inode,
        }
        digest = hashlib.sha256(canonical_json(fingerprint)).hexdigest()
        self._context_ref = f"context:{digest}"
        self._owner_ref = "owner:" + hashlib.sha256(b"mastermind.workbench_local_mcp").hexdigest()
        self._generation = "generation:" + hashlib.sha256(
            canonical_json({"fingerprint": digest, "started_at_ns": time.time_ns()})
        ).hexdigest()
        self._closed = False
        self._root_close_attempted = False
        super().__init__(
            project_ref=config.project_ref,
            profile=config.profile,
            allowed_paths=config.allowed_paths,
            resolve_scope=self._owned_scope,
            clock_ms=lambda: int(time.time() * 1000),
        )

    @classmethod
    def open(cls, config: LocalProfileConfig) -> "LocalWorkbenchGateway":
        if not isinstance(config, LocalProfileConfig):
            raise LocalProfileError("CONFIGURATION_REFUSED")
        root = Path(config.project_root)
        try:
            before = root.lstat()
        except OSError:
            raise LocalProfileError("CONFIGURATION_REFUSED") from None
        if (
            stat.S_ISLNK(before.st_mode)
            or not stat.S_ISDIR(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) & 0o022
        ):
            raise LocalProfileError("CONFIGURATION_REFUSED")
        directory = getattr(os, "O_DIRECTORY", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        cloexec = getattr(os, "O_CLOEXEC", 0)
        if not directory or not nofollow or not cloexec:
            raise LocalProfileError("CONFIGURATION_REFUSED")
        descriptor = -1
        try:
            descriptor = os.open(root, os.O_RDONLY | directory | nofollow | cloexec)
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
                or opened.st_uid != before.st_uid
                or stat.S_IMODE(opened.st_mode) != stat.S_IMODE(before.st_mode)
                or os.get_inheritable(descriptor)
            ):
                raise LocalProfileError("CONFIGURATION_REFUSED")
            project = _OwnedProject(
                fd=descriptor,
                device=opened.st_dev,
                inode=opened.st_ino,
                uid=opened.st_uid,
                mode=stat.S_IMODE(opened.st_mode),
            )
            descriptor = -1
            return cls(config, project)
        except LocalProfileError:
            raise
        except OSError:
            raise LocalProfileError("CONFIGURATION_REFUSED") from None
        finally:
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    raise LocalProfileError("CONFIGURATION_REFUSED") from None

    def close(self) -> None:
        if self._closed:
            self._raise_if_cleanup_uncertain()
            return
        if self._root_close_attempted:
            self._record_cleanup_uncertainty()
            self._raise_if_cleanup_uncertain()
        self._root_close_attempted = True
        self._port_closed = True
        try:
            os.close(self._project.fd)
        except OSError as error:
            self._record_cleanup_uncertainty()
            raise self._cleanup_uncertainty from error
        self._closed = True
        self._raise_if_cleanup_uncertain()

    def __enter__(self) -> "LocalWorkbenchGateway":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def _owned_scope(self) -> ReadScope:
        if self._port_closed:
            raise LocalProfileError("PROJECT_READ_REFUSED")
        try:
            current = os.fstat(self._project.fd)
        except OSError:
            raise LocalProfileError("SOURCE_CHANGED") from None
        if (
            not stat.S_ISDIR(current.st_mode)
            or current.st_dev != self._project.device
            or current.st_ino != self._project.inode
            or current.st_uid != self._project.uid
            or stat.S_IMODE(current.st_mode) != self._project.mode
        ):
            raise LocalProfileError("SOURCE_CHANGED")
        now_ms = int(time.time() * 1000)
        if now_ms >= self.config.lease_expires_at_ms:
            raise LocalProfileError("PROJECT_READ_REFUSED")
        return ReadScope(
            root_fd=self._project.fd,
            root_device=self._project.device,
            root_inode=self._project.inode,
            context_ref=self._context_ref,
            owner_ref=self._owner_ref,
            generation=self._generation,
            allowed_paths=self.config.allowed_paths,
            expires_at_ms=self.config.lease_expires_at_ms,
            committed_head=self.config.committed_head,
        )


class BoundWorkbenchReadPort(_ReadOperations):
    """Read/preview port borrowing all live authority from one scope callback."""

    def __init__(
        self,
        *,
        project_ref: str,
        profile: str,
        allowed_paths: tuple[str, ...],
        resolve_scope: Callable[[], ReadScope],
        clock_ms: Callable[[], int],
        on_cleanup_uncertain: Callable[[], None] | None = None,
    ) -> None:
        if (
            type(project_ref) is not str
            or _PROJECT_REF.fullmatch(project_ref) is None
            or profile != PROFILE_PRO_READ_PREPARE
            or type(allowed_paths) is not tuple
            or not 1 <= len(allowed_paths) <= 64
            or len(allowed_paths) != len(set(allowed_paths))
            or any(not _valid_bound_path(path) for path in allowed_paths)
            or not callable(resolve_scope)
            or not callable(clock_ms)
            or (
                on_cleanup_uncertain is not None
                and not callable(on_cleanup_uncertain)
            )
        ):
            raise LocalProfileError("CONFIGURATION_REFUSED")
        super().__init__(
            project_ref=project_ref,
            profile=profile,
            allowed_paths=allowed_paths,
            resolve_scope=resolve_scope,
            clock_ms=clock_ms,
            on_cleanup_uncertain=on_cleanup_uncertain,
        )


def _valid_bound_path(value: object) -> bool:
    if (
        type(value) is not str
        or not value
        or value.startswith(("/", "~", ".git/"))
        or "\\" in value
        or ":" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return False
    try:
        raw = value.encode("utf-8")
        parts = value.split("/")
        return (
            len(raw) <= 512
            and len(parts) <= 16
            and all(
                part not in ("", ".", "..") and len(part.encode("utf-8")) <= 255
                for part in parts
            )
        )
    except UnicodeError:
        return False


def create_bound_read_port(
    project_ref: str,
    profile: str,
    allowed_paths: tuple[str, ...],
    resolve_scope: Callable[[], ReadScope],
    clock_ms: Callable[[], int],
    *,
    on_cleanup_uncertain: Callable[[], None] | None = None,
) -> BoundWorkbenchReadPort:
    """Bind pure operations to a current external scope without taking ownership."""

    return BoundWorkbenchReadPort(
        project_ref=project_ref,
        profile=profile,
        allowed_paths=allowed_paths,
        resolve_scope=resolve_scope,
        clock_ms=clock_ms,
        on_cleanup_uncertain=on_cleanup_uncertain,
    )
