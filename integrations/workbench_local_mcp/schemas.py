"""Closed schemas for the local Workbench tunnel profile.

This module intentionally has no MCP SDK dependency. The Personal-Pro profile
is read/compute-only: every advertised tool is side-effect free with respect to
the selected project and host.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

CONFIG_SCHEMA = "mastermind.workbench_local_profile.v1"
RESULT_SCHEMA = "mastermind.workbench_local_result.v1"
SERVER_NAME = "Mastermind Workbench Local"
SERVER_VERSION = "0.1.0"
PROFILE_PRO_READ_PREPARE = "pro_read_prepare"
MAX_CONFIG_BYTES = 64 * 1024
MAX_ARGUMENT_BYTES = 64 * 1024
MAX_RESULT_BYTES = 192 * 1024
MAX_PREVIEW_TEXT_BYTES = 16 * 1024
MAX_PREVIEW_DIFF_BYTES = 96 * 1024
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_PROJECT_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CONFIG_KEYS = frozenset(
    {
        "schema",
        "profile",
        "project_ref",
        "project_root",
        "allowed_paths",
        "committed_head",
        "lease_expires_at_ms",
    }
)


class LocalProfileError(ValueError):
    _CODES = frozenset(
        {
            "CONFIGURATION_REFUSED",
            "CONFIGURATION_CLEANUP_UNCERTAIN",
            "PROJECT_CLEANUP_UNCERTAIN",
            "INVALID_REQUEST",
            "TOOL_NOT_AVAILABLE",
            "PROJECT_READ_REFUSED",
            "PREIMAGE_MISMATCH",
            "SOURCE_CHANGED",
            "PREVIEW_NOT_APPLICABLE",
            "PREVIEW_TOO_LARGE",
            "INTERNAL_ERROR",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._CODES:
            raise ValueError("unknown local Workbench error code")
        self.code = code
        super().__init__(code)


@dataclasses.dataclass(frozen=True)
class LocalProfileConfig:
    schema: str
    profile: str
    project_ref: str
    project_root: str
    allowed_paths: tuple[str, ...]
    committed_head: str | None
    lease_expires_at_ms: int


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    annotations: dict[str, bool]


def _read_annotations() -> dict[str, bool]:
    return {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }


TOOL_SPECS = (
    ToolSpec(
        name="workspace_manifest",
        description=(
            "Inspect the fixed local Workbench profile and its explicitly allowed paths. "
            "This tool cannot write files, run commands, or grant access."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        annotations=_read_annotations(),
    ),
    ToolSpec(
        name="read_project_file",
        description=(
            "Read bounded UTF-8 content from one explicitly allowed file in the fixed project. "
            "The project root is host-owned and cannot be selected by the caller."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "relative_path": {"type": "string", "minLength": 1, "maxLength": 512},
                "line_start": {"type": "integer", "minimum": 0, "maximum": 1048576},
                "line_count": {"type": "integer", "minimum": 1, "maximum": 256},
                "expected_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "required": ["relative_path"],
            "additionalProperties": False,
        },
        annotations=_read_annotations(),
    ),
    ToolSpec(
        name="preview_text_replace",
        description=(
            "Compute an in-memory preview of one exact text replacement against a required file "
            "preimage. It returns a diff and proposed hash but never writes or stages anything."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "relative_path": {"type": "string", "minLength": 1, "maxLength": 512},
                "expected_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "old_text": {"type": "string", "minLength": 1, "maxLength": MAX_PREVIEW_TEXT_BYTES},
                "new_text": {"type": "string", "maxLength": MAX_PREVIEW_TEXT_BYTES},
            },
            "required": ["relative_path", "expected_sha256", "old_text", "new_text"],
            "additionalProperties": False,
        },
        annotations=_read_annotations(),
    ),
    ToolSpec(
        name="preview_project_command",
        description=(
            "Render one reviewed validation recipe as argv without starting a process. "
            "This is a planning/inspection tool only; no command is executed."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "recipe": {
                    "type": "string",
                    "enum": ["git_diff_check", "pytest_targets", "compileall_paths"],
                },
                "targets": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1, "maxLength": 512},
                    "maxItems": 16,
                },
            },
            "required": ["recipe"],
            "additionalProperties": False,
        },
        annotations=_read_annotations(),
    ),
)
TOOL_NAMES = tuple(spec.name for spec in TOOL_SPECS)


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _refuse() -> None:
    raise LocalProfileError("CONFIGURATION_REFUSED")


def _path(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value.startswith(("/", "~"))
        or "\\" in value
        or ":" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        _refuse()
    try:
        raw = value.encode("utf-8")
        parts = value.split("/")
    except UnicodeError:
        _refuse()
    if (
        len(raw) > 512
        or len(parts) > 16
        or any(part in ("", ".", "..") or len(part.encode("utf-8")) > 255 for part in parts)
        or parts[0] == ".git"
    ):
        _refuse()
    return value


def _closed_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _refuse()
        result[key] = value
    return result


def _config_snapshot(selected: os.stat_result) -> tuple[int, ...]:
    """Return every stable field needed to bind one regular-file acquisition."""

    return (
        selected.st_dev,
        selected.st_ino,
        selected.st_mode,
        selected.st_nlink,
        selected.st_uid,
        selected.st_gid,
        selected.st_size,
        selected.st_mtime_ns,
        selected.st_ctime_ns,
    )


def _secure_json(path: str) -> dict[str, object]:
    selected = Path(path)
    if not selected.is_absolute() or "\x00" in path:
        _refuse()
    try:
        before = selected.lstat()
    except OSError:
        _refuse()
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.geteuid()
        or stat.S_IMODE(before.st_mode) & 0o022
        or before.st_size > MAX_CONFIG_BYTES
    ):
        _refuse()
    cloexec = getattr(os, "O_CLOEXEC", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    nonblocking = getattr(os, "O_NONBLOCK", 0)
    if not cloexec or not nofollow or not nonblocking:
        _refuse()
    flags = os.O_RDONLY | cloexec | nofollow | nonblocking
    descriptor = -1
    chunks: list[bytes] = []
    total = 0
    close_error: BaseException | None = None
    read_error: BaseException | None = None
    try:
        descriptor = os.open(selected, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or _config_snapshot(opened) != _config_snapshot(before)
            or os.get_inheritable(descriptor)
        ):
            _refuse()
        expected_size = opened.st_size
        while total < expected_size:
            chunk = os.read(descriptor, min(4096, expected_size - total))
            if not chunk:
                _refuse()
            chunks.append(chunk)
            total += len(chunk)
        if os.read(descriptor, 1):
            _refuse()
        post_read = os.fstat(descriptor)
        if (
            not stat.S_ISREG(post_read.st_mode)
            or post_read.st_nlink != 1
            or _config_snapshot(post_read) != _config_snapshot(opened)
        ):
            _refuse()
    except BaseException as error:
        read_error = error
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except BaseException as error:
                close_error = error
            descriptor = -1
    if close_error is not None:
        raise LocalProfileError("CONFIGURATION_CLEANUP_UNCERTAIN") from close_error
    if read_error is not None:
        if isinstance(read_error, LocalProfileError):
            raise read_error
        _refuse()
    try:
        after = selected.lstat()
    except OSError:
        _refuse()
    if not stat.S_ISREG(after.st_mode) or after.st_nlink != 1 or (
        _config_snapshot(after) != _config_snapshot(before)
    ):
        _refuse()
    try:
        decoded = b"".join(chunks).decode("utf-8", errors="strict")
        payload = json.loads(decoded, object_pairs_hook=_closed_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        _refuse()
    if type(payload) is not dict:
        _refuse()
    return payload


def parse_config(payload: object) -> LocalProfileConfig:
    if type(payload) is not dict or set(payload) != _CONFIG_KEYS:
        _refuse()
    if payload.get("schema") != CONFIG_SCHEMA or payload.get("profile") != PROFILE_PRO_READ_PREPARE:
        _refuse()
    project_ref = payload.get("project_ref")
    project_root = payload.get("project_root")
    paths = payload.get("allowed_paths")
    committed = payload.get("committed_head")
    expiry = payload.get("lease_expires_at_ms")
    if type(project_ref) is not str or _PROJECT_REF.fullmatch(project_ref) is None:
        _refuse()
    if type(project_root) is not str or not project_root.startswith("/") or "\x00" in project_root:
        _refuse()
    if type(paths) is not list or not 1 <= len(paths) <= 64:
        _refuse()
    selected_paths = tuple(_path(item) for item in paths)
    if len(selected_paths) != len(set(selected_paths)):
        _refuse()
    if committed is not None and (type(committed) is not str or _HEX40.fullmatch(committed) is None):
        _refuse()
    if type(expiry) is not int or isinstance(expiry, bool) or not 0 <= expiry < 2**63:
        _refuse()
    return LocalProfileConfig(
        schema=CONFIG_SCHEMA,
        profile=PROFILE_PRO_READ_PREPARE,
        project_ref=project_ref,
        project_root=project_root,
        allowed_paths=selected_paths,
        committed_head=committed,
        lease_expires_at_ms=expiry,
    )


def load_config(path: str) -> LocalProfileConfig:
    return parse_config(_secure_json(path))


def schema_snapshot() -> dict[str, object]:
    return {
        "server_name": SERVER_NAME,
        "server_version": SERVER_VERSION,
        "profile": PROFILE_PRO_READ_PREPARE,
        "mutation_allowed": False,
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
                "annotations": spec.annotations,
            }
            for spec in TOOL_SPECS
        ],
    }


def schema_snapshot_sha256() -> str:
    return hashlib.sha256(canonical_json(schema_snapshot())).hexdigest()
