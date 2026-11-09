"""Bounded provider-free workspace read/search tools for governed ACP workers.

The Executive Job/Attempt owns the workspace and lifecycle. This module owns no
grant, queue, lease, provider route, credential, or process. It reuses the
existing descriptor-relative source observer and binds each requested relative
path to the already-admitted exact workspace root.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from integrations.workbench_read_mcp.observer import (
    MAX_TEXT_BYTES,
    ReadRefusal,
    ReadScope,
    observe_file,
)

SERVER_NAME = "mastermind-acp-workspace-read"
SERVER_VERSION = "1.0.0"
MAX_RESULT_BYTES = 192 * 1024
MAX_QUERY_BYTES = 1024
MAX_MATCHES = 32
_REQUIRED_ENV = frozenset(
    {
        "MMX_ACP_WORKSPACE_PATH",
        "MMX_ACP_WORKSPACE_BASE_SHA",
        "MMX_ACP_RUN_ID",
        "MMX_ACP_JOB_ID",
        "MMX_ACP_WORKER_ID",
        "MMX_ACP_DEADLINE_MS",
    }
)
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")


def _annotations() -> dict[str, bool]:
    return {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }


_READ_INPUT = {
    "type": "object",
    "properties": {
        "relative_path": {"type": "string", "minLength": 1, "maxLength": 512},
        "start_line": {"type": "integer", "minimum": 0, "maximum": 1048576},
        "max_lines": {"type": "integer", "minimum": 1, "maximum": 512},
        "max_content_bytes": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_TEXT_BYTES,
        },
        "expected_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    },
    "required": ["relative_path"],
    "additionalProperties": False,
}
_SEARCH_INPUT = {
    "type": "object",
    "properties": {
        "relative_path": {"type": "string", "minLength": 1, "maxLength": 512},
        "query": {"type": "string", "minLength": 1, "maxLength": 256},
        "start_line": {"type": "integer", "minimum": 0, "maximum": 1048576},
        "max_lines": {"type": "integer", "minimum": 1, "maximum": 512},
        "max_matches": {"type": "integer", "minimum": 1, "maximum": MAX_MATCHES},
        "case_sensitive": {"type": "boolean"},
        "expected_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    },
    "required": ["relative_path", "query"],
    "additionalProperties": False,
}

_TOOL_CATALOG = (
    {
        "name": "read_file",
        "inputSchema": _READ_INPUT,
        "annotations": _annotations(),
    },
    {
        "name": "search_text",
        "inputSchema": _SEARCH_INPUT,
        "annotations": _annotations(),
    },
)

# Generated from control_plane.executive_agent_capabilities.
# observed_mcp_tool_schema_digest; the test pins equality to that sole owner.
TOOL_SCHEMA_DIGEST = "76bc2f621a26a36cae7a1e90edab3af113cdc6924a662fa83004f6b56babd18d"


def tool_catalog() -> list[dict[str, Any]]:
    return json.loads(json.dumps(list(_TOOL_CATALOG), sort_keys=True))


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _path(value: object) -> str:
    if type(value) is not str or _SAFE_PATH.fullmatch(value) is None:
        raise ValueError("INVALID_REQUEST")
    parts = value.split("/")
    if (
        value.startswith(("/", "~"))
        or "\\" in value
        or ":" in value
        or len(parts) > 16
        or any(part in ("", ".", "..") for part in parts)
        or parts[0] == ".git"
    ):
        raise ValueError("INVALID_REQUEST")
    try:
        if any(len(part.encode("utf-8")) > 255 for part in parts):
            raise ValueError("INVALID_REQUEST")
    except UnicodeError:
        raise ValueError("INVALID_REQUEST") from None
    return value


def _int(value: object, default: int, low: int, high: int) -> int:
    selected = default if value is None else value
    if type(selected) is not int or not low <= selected <= high:
        raise ValueError("INVALID_REQUEST")
    return selected


def _result(tool: str, identity: "_WorkspaceIdentity", data: object) -> dict[str, Any]:
    value = {
        "schema": "mastermind.acp_workspace_read_result.v1",
        "tool": tool,
        "ok": True,
        "server_name": SERVER_NAME,
        "server_version": SERVER_VERSION,
        "run_id": identity.run_id,
        "job_id": identity.job_id,
        "worker_id": identity.worker_id,
        "data": data,
        "error": None,
    }
    if len(_canonical(value)) > MAX_RESULT_BYTES:
        raise ValueError("INTERNAL_ERROR")
    return value


def _error(tool: str, identity: "_WorkspaceIdentity", code: str) -> dict[str, Any]:
    return {
        "schema": "mastermind.acp_workspace_read_result.v1",
        "tool": tool,
        "ok": False,
        "server_name": SERVER_NAME,
        "server_version": SERVER_VERSION,
        "run_id": identity.run_id,
        "job_id": identity.job_id,
        "worker_id": identity.worker_id,
        "data": None,
        "error": {"code": code},
    }


@dataclasses.dataclass(frozen=True)
class _WorkspaceIdentity:
    lexical_root: Path
    root_fd: int
    root_device: int
    root_inode: int
    base_sha: str
    run_id: str
    job_id: str
    worker_id: str
    deadline_ms: int
    context_ref: str
    owner_ref: str
    generation: str


class WorkspaceReadGateway:
    """One exact Executive workspace generation; model input cannot retarget it."""

    def __init__(self, identity: _WorkspaceIdentity) -> None:
        self._identity = identity
        self._closed = False

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "WorkspaceReadGateway":
        if not isinstance(environment, Mapping):
            raise ValueError("ACP workspace read environment is invalid")
        try:
            values = {key: environment[key] for key in _REQUIRED_ENV}
        except (KeyError, TypeError):
            raise ValueError("ACP workspace read environment is incomplete") from None
        if any(not isinstance(value, str) or not value for value in values.values()):
            raise ValueError("ACP workspace read environment is invalid")
        root = Path(values["MMX_ACP_WORKSPACE_PATH"])
        if not root.is_absolute() or "\x00" in str(root):
            raise ValueError("ACP workspace read environment is invalid")
        if _HEX40.fullmatch(values["MMX_ACP_WORKSPACE_BASE_SHA"]) is None:
            raise ValueError("ACP workspace read environment is invalid")
        for key in ("MMX_ACP_RUN_ID", "MMX_ACP_JOB_ID", "MMX_ACP_WORKER_ID"):
            if _TOKEN.fullmatch(values[key]) is None:
                raise ValueError("ACP workspace read environment is invalid")
        try:
            deadline = int(values["MMX_ACP_DEADLINE_MS"], 10)
        except (TypeError, ValueError):
            raise ValueError("ACP workspace read environment is invalid") from None
        if not 0 < deadline < 2**63:
            raise ValueError("ACP workspace read environment is invalid")
        try:
            before = root.lstat()
        except OSError:
            raise ValueError("ACP workspace read environment is unavailable") from None
        if (
            stat.S_ISLNK(before.st_mode)
            or not stat.S_ISDIR(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) & 0o022
        ):
            raise ValueError("ACP workspace read environment is unsafe")
        directory = getattr(os, "O_DIRECTORY", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        cloexec = getattr(os, "O_CLOEXEC", 0)
        if not directory or not nofollow or not cloexec:
            raise ValueError("ACP workspace read environment is unsupported")
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
                raise ValueError("ACP workspace read environment changed")
            material = {
                "root_device": opened.st_dev,
                "root_inode": opened.st_ino,
                "base_sha": values["MMX_ACP_WORKSPACE_BASE_SHA"],
                "run_id": values["MMX_ACP_RUN_ID"],
                "job_id": values["MMX_ACP_JOB_ID"],
                "worker_id": values["MMX_ACP_WORKER_ID"],
                "deadline_ms": deadline,
            }
            digest = hashlib.sha256(_canonical(material)).hexdigest()
            identity = _WorkspaceIdentity(
                lexical_root=root,
                root_fd=descriptor,
                root_device=opened.st_dev,
                root_inode=opened.st_ino,
                base_sha=values["MMX_ACP_WORKSPACE_BASE_SHA"],
                run_id=values["MMX_ACP_RUN_ID"],
                job_id=values["MMX_ACP_JOB_ID"],
                worker_id=values["MMX_ACP_WORKER_ID"],
                deadline_ms=deadline,
                context_ref=f"context:{digest}",
                owner_ref="owner:" + hashlib.sha256(
                    b"mastermind.acp_workspace_read"
                ).hexdigest(),
                generation=f"generation:{digest}",
            )
            descriptor = -1
            return cls(identity)
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        os.close(self._identity.root_fd)

    def _scope(self, relative_path: str) -> ReadScope:
        if self._closed:
            raise ReadRefusal("SCOPE_UNAVAILABLE")
        identity = self._identity
        try:
            current = identity.lexical_root.lstat()
            opened = os.fstat(identity.root_fd)
        except OSError:
            raise ReadRefusal("ROOT_IDENTITY_CHANGED") from None
        if (
            not stat.S_ISDIR(current.st_mode)
            or current.st_dev != identity.root_device
            or current.st_ino != identity.root_inode
            or opened.st_dev != identity.root_device
            or opened.st_ino != identity.root_inode
        ):
            raise ReadRefusal("ROOT_IDENTITY_CHANGED")
        return ReadScope(
            root_fd=identity.root_fd,
            root_device=identity.root_device,
            root_inode=identity.root_inode,
            context_ref=identity.context_ref,
            owner_ref=identity.owner_ref,
            generation=identity.generation,
            allowed_paths=(relative_path,),
            expires_at_ms=identity.deadline_ms,
            committed_head=identity.base_sha,
        )

    @staticmethod
    def _clock_ms() -> int:
        return int(time.time() * 1000)

    def _observe(self, request: dict[str, Any]) -> dict[str, Any]:
        relative = _path(request.get("relative_path"))
        selected = {
            "relative_path": relative,
            "start_line": _int(request.get("start_line"), 0, 0, 1048576),
            "max_lines": _int(request.get("max_lines"), 128, 1, 512),
            "max_content_bytes": _int(
                request.get("max_content_bytes"), MAX_TEXT_BYTES, 1, MAX_TEXT_BYTES
            ),
        }
        expected = request.get("expected_sha256")
        if expected is not None:
            if (
                type(expected) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected) is None
            ):
                raise ValueError("INVALID_REQUEST")
            selected["expected_sha256"] = expected
        return observe_file(
            selected,
            lambda: self._scope(relative),
            clock_ms=self._clock_ms,
        )

    def call(self, name: str, arguments: object) -> dict[str, Any]:
        tool = name if name in {"read_file", "search_text"} else "unknown"
        try:
            if type(arguments) is not dict:
                raise ValueError("INVALID_REQUEST")
            if name == "read_file":
                if set(arguments) - {
                    "relative_path",
                    "start_line",
                    "max_lines",
                    "max_content_bytes",
                    "expected_sha256",
                }:
                    raise ValueError("INVALID_REQUEST")
                observed = self._observe(dict(arguments))
                return _result(
                    name,
                    self._identity,
                    {
                        **observed,
                        "run_id": self._identity.run_id,
                        "job_id": self._identity.job_id,
                        "worker_id": self._identity.worker_id,
                    },
                )
            if name == "search_text":
                allowed = {
                    "relative_path",
                    "query",
                    "start_line",
                    "max_lines",
                    "max_matches",
                    "case_sensitive",
                    "expected_sha256",
                }
                if set(arguments) - allowed:
                    raise ValueError("INVALID_REQUEST")
                query = arguments.get("query")
                if (
                    type(query) is not str
                    or not query
                    or len(query.encode("utf-8")) > MAX_QUERY_BYTES
                    or "\x00" in query
                ):
                    raise ValueError("INVALID_REQUEST")
                case_sensitive = arguments.get("case_sensitive", False)
                if type(case_sensitive) is not bool:
                    raise ValueError("INVALID_REQUEST")
                max_matches = _int(
                    arguments.get("max_matches"), 16, 1, MAX_MATCHES
                )
                observed = self._observe(
                    {
                        "relative_path": arguments.get("relative_path"),
                        "start_line": arguments.get("start_line", 0),
                        "max_lines": arguments.get("max_lines", 128),
                        "max_content_bytes": MAX_TEXT_BYTES,
                        **(
                            {"expected_sha256": arguments["expected_sha256"]}
                            if "expected_sha256" in arguments
                            else {}
                        ),
                    }
                )
                needle = query if case_sensitive else query.casefold()
                matches: list[dict[str, object]] = []
                total_matches = 0
                for index, line in enumerate(
                    observed["content"].splitlines(),
                    start=observed["line_start"],
                ):
                    candidate = line if case_sensitive else line.casefold()
                    if needle in candidate:
                        total_matches += 1
                        if len(matches) < max_matches:
                            matches.append({"line": index, "text": line})
                return _result(
                    name,
                    self._identity,
                    {
                        "relative_path": observed["relative_path"],
                        "query": query,
                        "case_sensitive": case_sensitive,
                        "searched_line_start": observed["line_start"],
                        "searched_line_end": observed["line_end"],
                        "next_line": observed["next_line"],
                        "file_sha256": observed["file_sha256"],
                        "matches": matches,
                        "matches_truncated": total_matches > len(matches),
                        "observation_digest": observed["observation_digest"],
                    },
                )
            return _error(tool, self._identity, "TOOL_NOT_AVAILABLE")
        except ReadRefusal as exc:
            return _error(tool, self._identity, exc.code)
        except (ValueError, TypeError, UnicodeError):
            return _error(tool, self._identity, "INVALID_REQUEST")
        except Exception:
            return _error(tool, self._identity, "INTERNAL_ERROR")


__all__ = [
    "MAX_MATCHES",
    "MAX_QUERY_BYTES",
    "MAX_RESULT_BYTES",
    "SERVER_NAME",
    "SERVER_VERSION",
    "TOOL_SCHEMA_DIGEST",
    "WorkspaceReadGateway",
    "tool_catalog",
]
