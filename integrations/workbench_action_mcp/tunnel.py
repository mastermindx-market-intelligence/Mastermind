"""Fixed-channel stdio composition for Workbench Action.

This module is the transport seam only: one host-selected Secure MCP Tunnel
channel becomes one stdio child that reuses the existing
``WorkbenchActionRuntime`` root/lease/executor ownership, text patch port, and
borrowed protected Read port.  The tunnel association authenticates the channel, never a
cryptographically attested end user, so no ``JwtAuthenticator``,
``ResourcePolicy``, token verifier, or OAuth-accepted audit row exists on this
path.  Channel admission is durably audited before dispatch, and an audit
failure blocks the effect.  The same durable admission ledger is the only
evidence that lets a reconcile classify an artifact-less action as
``NOT_APPLIED``: a modifying call refused before dispatch and never accepted
for that exact reference.  It creates no new auth service, credential,
process/lifecycle registry, queue, or retry state, and the model can never
supply the channel, lease, key, or any location bound here.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time

from control_plane.codex_worker import ProcessInspector
from jsonschema import Draft202012Validator
import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from integrations.workbench_stdio_boundary import (
    MAX_WIRE_BYTES,
    MODERN_PROTOCOL_VERSION,
    is_modern_protocol_request,
    parse_modern_protocol_request,
    private_stdio_server,
    read_bounded_stdio_line,
    write_bounded_stdio_json,
)
from mcp.types import CallToolResult, ServerResult, TextContent, Tool, ToolAnnotations

from common.bounded_sync_executor import SyncExecutionTimeout
from integrations.business_mcp_auth.audit import (
    AuditSinkPoisoned,
    DurableAuthAuditSink,
    classify_channel_admissions,
)
from integrations.business_mcp_auth.contracts import CHANNEL_AUDIT_SCHEMA, ChannelAuditEvent
from integrations.workbench_read_mcp.runtime import (
    RuntimeCloseIncomplete,
    RuntimeCloseUncertain,
    RuntimeClosed,
)

from .app import (
    COMMIT_TOOL,
    PREPARE_TOOL,
    RECONCILE_TOOL,
    _ACTION_REF_SCHEMA,
    _EFFECT_OUTPUT_SCHEMA,
    _PREPARE_OUTPUT_SCHEMA,
    _PREPARE_SCHEMA,
)
from .contracts import ActionTokenCodec
from .command_contracts import (
    MAX_PAGE_BYTES as MAX_COMMAND_PAGE_BYTES,
    MAX_PAGE_LINES as MAX_COMMAND_PAGE_LINES,
    MAX_PROCESS_DEADLINE_S,
    RECIPE_SHA256,
    CommandHostBinding,
)
from .command_port import create_command_port
from .patch_port import ProjectActionRefused, create_text_patch_port
from .read_composition import (
    READ_OUTPUT_SCHEMAS,
    READ_REFUSAL_CODES,
    READ_TOOL_NAMES,
    READ_TOOL_SPECS,
    create_bound_read_composition,
)
from .runtime import (
    CHANNEL_AUTHORITY_KIND,
    ChannelRuntimeServices,
    FixedTunnelChannel,
    StableWorkbenchActionLease,
    WorkbenchActionRuntime,
    channel_binding_ref,
    validate_fixed_tunnel_channel,
)
from .service import ShutdownOutcome, shutdown_exit_code

TUNNEL_SCHEMA = "mastermind.workbench_action_tunnel.v1"
TUNNEL_RECEIPT_SCHEMA = "mastermind.workbench_action_tunnel_receipt.v1"
SERVER_NAME = "Mastermind Workbench Action Tunnel"
SERVER_VERSION = "0.1.0"
MAX_CONFIG_BYTES = 64 * 1024
MAX_CONCURRENCY = 8
MAX_TIMEOUT_SECONDS = 60.0
MAX_ACTION_TTL_MS = 5 * 60 * 1000
MAX_ARGUMENT_BYTES = 65536
MAX_RESULT_BYTES = 131072
_AUDIT_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,95}$")
# Deliberately the same closed input/output schemas as the OAuth adapter so the
# two entry points can never drift; the private names are the single source.
_PREPARE_INPUT = _PREPARE_SCHEMA
_ACTION_REF_INPUT = _ACTION_REF_SCHEMA
_PREPARE_OUTPUT = _PREPARE_OUTPUT_SCHEMA
_EFFECT_OUTPUT = _EFFECT_OUTPUT_SCHEMA
PREPARE_COMMAND_TOOL = "prepare_project_command"
RUN_COMMAND_TOOL = "run_project_command"
READ_ACTION_RESULT_TOOL = "read_action_result"
RECONCILE_ACTION_TOOL = "reconcile_action"
COMMAND_TOOL_NAMES = (
    PREPARE_COMMAND_TOOL,
    RUN_COMMAND_TOOL,
    READ_ACTION_RESULT_TOOL,
    RECONCILE_ACTION_TOOL,
)
_KNOWN_TUNNEL_TOOLS = frozenset(
    {
        *READ_TOOL_NAMES,
        PREPARE_TOOL,
        COMMIT_TOOL,
        RECONCILE_TOOL,
        *COMMAND_TOOL_NAMES,
    }
)


def _closed_schema(
    properties: dict[str, object], required: tuple[str, ...]
) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


_HEX64_SCHEMA = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_REFERENCE_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 256}
_COMMAND_PREPARE_INPUT = _closed_schema(
    {
        "project_ref": _REFERENCE_SCHEMA,
        "relative_path": {"type": "string", "minLength": 1, "maxLength": 512},
        "recipe_id": {
            "type": "string",
            "enum": ["canary_checksum", "canary_refuse"],
        },
        "expected_sha256": _HEX64_SCHEMA,
    },
    ("project_ref", "relative_path", "recipe_id", "expected_sha256"),
)
_COMMAND_PREPARE_OUTPUT = _closed_schema(
    {
        "status": {"const": "PREPARED"},
        "action_ref": {"type": "string", "minLength": 1, "maxLength": 65536},
        "project_ref": _REFERENCE_SCHEMA,
        "responsibility_ref": _REFERENCE_SCHEMA,
        "operation_ref": _REFERENCE_SCHEMA,
        "recipe_id": {
            "type": "string",
            "enum": ["canary_checksum", "canary_refuse"],
        },
        "relative_path": {"type": "string", "minLength": 1, "maxLength": 512},
        "preimage_sha256": _HEX64_SCHEMA,
        "source_identity": {
            "type": "string",
            "pattern": "^[0-9]+(:[0-9]+){8}$",
        },
        "host_id": _HEX64_SCHEMA,
        "boot_session_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "expires_at_ms": {"type": "integer", "minimum": 0},
    },
    (
        "status",
        "action_ref",
        "project_ref",
        "responsibility_ref",
        "operation_ref",
        "recipe_id",
        "relative_path",
        "preimage_sha256",
        "source_identity",
        "host_id",
        "boot_session_id",
        "expires_at_ms",
    ),
)
_COMMAND_ACTION_REF_INPUT = _closed_schema(
    {"action_ref": {"type": "string", "minLength": 1, "maxLength": 65536}},
    ("action_ref",),
)
_COMMAND_READ_INPUT = _closed_schema(
    {
        "action_ref": {"type": "string", "minLength": 1, "maxLength": 65536},
        "stream": {"type": "string", "enum": ["stdout", "stderr"]},
        "start_line": {"type": "integer", "minimum": 0, "maximum": 1048576},
        "max_lines": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_COMMAND_PAGE_LINES,
        },
        "max_content_bytes": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_COMMAND_PAGE_BYTES,
        },
    },
    ("action_ref", "stream"),
)
_PROCESS_IDENTITY_SCHEMA = _closed_schema(
    {
        "pid": {"type": "integer", "minimum": 1},
        "process_start_identity": {"type": "string", "minLength": 1},
        "pgid": {"type": "integer", "minimum": 1},
        "session_id": {"type": "integer", "minimum": 1},
        "host_id": _HEX64_SCHEMA,
        "boot_session_id": {"type": "string", "minLength": 1, "maxLength": 128},
    },
    (
        "pid",
        "process_start_identity",
        "pgid",
        "session_id",
        "host_id",
        "boot_session_id",
    ),
)
_COMMAND_EFFECT_OUTPUT = _closed_schema(
    {
        "status": {"const": "OK"},
        "effect_state": {
            "type": "string",
            "enum": ["NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"],
        },
        "isError": {"const": False},
        "project_ref": _REFERENCE_SCHEMA,
        "recipe_id": {
            "type": "string",
            "enum": ["canary_checksum", "canary_refuse"],
        },
        "relative_path": {"type": "string", "minLength": 1, "maxLength": 512},
        "preimage_sha256": _HEX64_SCHEMA,
        "cleanup_state": {"type": "string", "enum": ["CLEAN", "UNCERTAIN"]},
        "exit_code": {"type": "integer", "minimum": -(2**31), "maximum": 2**31 - 1},
        "stdout_sha256": _HEX64_SCHEMA,
        "stderr_sha256": _HEX64_SCHEMA,
        "stdout_bytes": {"type": "integer", "minimum": 0, "maximum": 65536},
        "stderr_bytes": {"type": "integer", "minimum": 0, "maximum": 65536},
        "truncated": {"type": "boolean"},
        "process_identity": _PROCESS_IDENTITY_SCHEMA,
        "timed_out": {"type": "boolean"},
    },
    (
        "status",
        "effect_state",
        "isError",
        "project_ref",
        "recipe_id",
        "relative_path",
        "preimage_sha256",
        "cleanup_state",
    ),
)
_COMMAND_EFFECT_OUTPUT["allOf"] = [
    {
        "if": {"properties": {"effect_state": {"const": "APPLIED"}}},
        "then": {
            "required": [
                "exit_code",
                "stdout_sha256",
                "stderr_sha256",
                "stdout_bytes",
                "stderr_bytes",
                "truncated",
                "process_identity",
                "timed_out",
            ]
        },
    }
]
_COMMAND_READ_OUTPUT = _closed_schema(
    {
        **_COMMAND_EFFECT_OUTPUT["properties"],
        "stream": {"type": "string", "enum": ["stdout", "stderr"]},
        "content": {"type": "string", "maxLength": MAX_COMMAND_PAGE_BYTES},
        "line_start": {"type": "integer", "minimum": 0},
        "line_end": {"type": "integer", "minimum": 0},
        "total_lines": {"type": "integer", "minimum": 0},
        "next_line": {
            "anyOf": [{"type": "null"}, {"type": "integer", "minimum": 0}]
        },
        "file_sha256": _HEX64_SCHEMA,
    },
    ("status", "effect_state", "isError"),
)
_COMMAND_READ_OUTPUT["oneOf"] = [
    {
        "required": [
            "project_ref",
            "recipe_id",
            "relative_path",
            "preimage_sha256",
            "cleanup_state",
        ]
    },
    {
        "required": [
            "stream",
            "content",
            "line_start",
            "line_end",
            "total_lines",
            "next_line",
            "truncated",
            "file_sha256",
            "exit_code",
        ]
    },
]
_CONFIG_KEYS = frozenset(
    {
        "schema",
        "tunnel_id",
        "organization_id",
        "workspace_id",
        "audit_policy_id",
        "project_root",
        "audit_directory",
        "artifact_directory",
        "host_id",
        "action_key_file",
        "python_executable",
        "python_sha256",
        "recipe_root",
        "process_deadline_seconds",
        "max_concurrency",
        "io_timeout_seconds",
        "close_timeout_seconds",
        "action_ttl_ms",
        "lease",
    }
)
_LEASE_KEYS = frozenset(
    {
        "expected_subject_digest",
        "expected_client_ref",
        "resource",
        "required_scopes",
        "project_ref",
        "context_ref",
        "responsibility_ref",
        "operation_ref",
        "owner_ref",
        "generation",
        "allowed_paths",
        "committed_head",
        "lease_expires_at_ms",
    }
)


class TunnelConfigurationError(RuntimeError):
    _CODES = frozenset(
        {
            "TUNNEL_CONFIGURATION_REFUSED",
            "TUNNEL_STARTUP_CLEANUP_UNCERTAIN",
        }
    )

    def __init__(self, code: str = "TUNNEL_CONFIGURATION_REFUSED") -> None:
        if code not in self._CODES:
            raise ValueError("unknown Workbench Action tunnel error code")
        self.code = code
        super().__init__(code)


@dataclasses.dataclass(frozen=True)
class TunnelConfig:
    """One closed host-selected fixed-channel composition document."""

    schema: str
    channel: FixedTunnelChannel
    audit_policy_id: str
    project_root: str
    audit_directory: str
    artifact_directory: str
    host_id: str
    action_key_file: str
    python_executable: str
    python_sha256: str
    recipe_root: str
    process_deadline_seconds: float
    max_concurrency: int
    io_timeout_seconds: float
    close_timeout_seconds: float
    action_ttl_ms: int
    lease: StableWorkbenchActionLease


def _refuse(code: str = "TUNNEL_CONFIGURATION_REFUSED") -> None:
    raise TunnelConfigurationError(code)


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _refuse()
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    _refuse()


def _absolute_path(value: object) -> str:
    if type(value) is not str or not value or not value.startswith("/") or "\x00" in value:
        _refuse()
    return value


def _bounded_int(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _refuse()
    return value


def _bounded_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _refuse()
    selected = float(value)
    if not math.isfinite(selected) or not 0 < selected <= MAX_TIMEOUT_SECONDS:
        _refuse()
    return selected


def _bounded_process_deadline(value: object) -> float:
    selected = _bounded_timeout(value)
    if selected > MAX_PROCESS_DEADLINE_S:
        _refuse()
    return selected


def _channel_identifier(value: object) -> str:
    if type(value) is not str or not value or len(value) > 512:
        _refuse()
    if any(ord(character) <= 32 or ord(character) == 127 for character in value):
        _refuse()
    return value


def _host_id(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _refuse()
    return value


def _sha256(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _refuse()
    return value


def _audit_policy_id(value: object) -> str:
    if type(value) is not str or _AUDIT_ID.fullmatch(value) is None:
        _refuse()
    return value


def _lease(value: object) -> StableWorkbenchActionLease:
    if not isinstance(value, dict) or set(value) != _LEASE_KEYS:
        _refuse()
    scopes = value.get("required_scopes")
    paths = value.get("allowed_paths")
    if scopes != ["workbench.action"]:
        _refuse()
    if (
        not isinstance(paths, list)
        or not 1 <= len(paths) <= 64
        or any(type(item) is not str or not item for item in paths)
        or len(paths) != len(set(paths))
    ):
        _refuse()
    committed = value.get("committed_head")
    if committed is not None and (
        type(committed) is not str
        or len(committed) != 40
        or any(character not in "0123456789abcdef" for character in committed)
    ):
        _refuse()
    expiry = value.get("lease_expires_at_ms")
    if type(expiry) is not int or not 0 <= expiry < 2**63:
        _refuse()
    try:
        return StableWorkbenchActionLease(
            expected_subject_digest=value["expected_subject_digest"],  # type: ignore[arg-type]
            expected_client_ref=value["expected_client_ref"],  # type: ignore[arg-type]
            resource=value["resource"],  # type: ignore[arg-type]
            required_scopes=("workbench.action",),
            project_ref=value["project_ref"],  # type: ignore[arg-type]
            context_ref=value["context_ref"],  # type: ignore[arg-type]
            responsibility_ref=value["responsibility_ref"],  # type: ignore[arg-type]
            operation_ref=value["operation_ref"],  # type: ignore[arg-type]
            owner_ref=value["owner_ref"],  # type: ignore[arg-type]
            generation=value["generation"],  # type: ignore[arg-type]
            allowed_paths=tuple(paths),
            committed_head=committed,
            lease_expires_at_ms=expiry,
        )
    except (KeyError, TypeError, ValueError):
        _refuse()
    raise AssertionError("unreachable")


def _regular_file_snapshot(
    info: os.stat_result, *, required_imode: int | None
) -> tuple[int, int, int, int, int, int, int, int]:
    """Closed identity for a host-selected regular file.

    Compared fields are exactly the review's required snapshot:
    dev/ino/uid/mode/nlink/size/mtime_ns/ctime_ns.
    """

    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.geteuid()
    ):
        _refuse()
    mode = stat.S_IMODE(info.st_mode)
    if required_imode is None:
        if mode & 0o022:
            _refuse()
    elif mode != required_imode:
        _refuse()
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read_exact_bytes(fd: int, expected: int, *, maximum: int) -> bytes:
    if type(expected) is not int or expected <= 0 or expected > maximum:
        _refuse()
    chunks: list[bytes] = []
    total = 0
    while total < expected:
        chunk = os.read(fd, min(4096, expected - total))
        if not chunk:
            _refuse()
        total += len(chunk)
        if total > expected:
            _refuse()
        chunks.append(chunk)
    return b"".join(chunks)


def _acquire_regular_file_bytes(
    path: str,
    *,
    maximum: int,
    required_imode: int | None,
    allowed_sizes: frozenset[int] | None = None,
) -> bytes:
    selected = Path(_absolute_path(path))
    try:
        before = selected.lstat()
    except OSError:
        _refuse()
    expected = _regular_file_snapshot(before, required_imode=required_imode)
    if allowed_sizes is not None and expected[5] not in allowed_sizes:
        _refuse()
    if expected[5] > maximum:
        _refuse()
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if not nofollow or not nonblock or not cloexec:
        _refuse()
    fd = -1
    raw = b""
    primary: BaseException | None = None
    cleanup: BaseException | None = None
    try:
        fd = os.open(selected, os.O_RDONLY | nofollow | nonblock | cloexec)
        opened = os.fstat(fd)
        if os.get_inheritable(fd) or _regular_file_snapshot(
            opened, required_imode=required_imode
        ) != expected:
            _refuse()
        raw = _read_exact_bytes(fd, expected[5], maximum=maximum)
        reread = os.fstat(fd)
        if _regular_file_snapshot(reread, required_imode=required_imode) != expected:
            _refuse()
    except BaseException as error:
        primary = error
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except BaseException as error:
                cleanup = error
    if cleanup is not None:
        raise TunnelConfigurationError("TUNNEL_STARTUP_CLEANUP_UNCERTAIN") from cleanup
    if primary is not None:
        if isinstance(primary, TunnelConfigurationError):
            raise primary
        _refuse()
    try:
        after = selected.lstat()
    except OSError:
        _refuse()
    if _regular_file_snapshot(after, required_imode=required_imode) != expected:
        _refuse()
    return raw


def parse_tunnel_config(value: object) -> TunnelConfig:
    if not isinstance(value, dict) or set(value) != _CONFIG_KEYS:
        _refuse()
    if value.get("schema") != TUNNEL_SCHEMA:
        _refuse()
    try:
        channel = validate_fixed_tunnel_channel(
            FixedTunnelChannel(
                tunnel_id=_channel_identifier(value.get("tunnel_id")),
                organization_id=_channel_identifier(value.get("organization_id")),
                workspace_id=_channel_identifier(value.get("workspace_id")),
            )
        )
    except TunnelConfigurationError:
        raise
    except Exception:
        _refuse()
    ttl = _bounded_int(value.get("action_ttl_ms"), minimum=1000, maximum=MAX_ACTION_TTL_MS)
    return TunnelConfig(
        schema=TUNNEL_SCHEMA,
        channel=channel,
        audit_policy_id=_audit_policy_id(value.get("audit_policy_id")),
        project_root=_absolute_path(value.get("project_root")),
        audit_directory=_absolute_path(value.get("audit_directory")),
        artifact_directory=_absolute_path(value.get("artifact_directory")),
        host_id=_host_id(value.get("host_id")),
        action_key_file=_absolute_path(value.get("action_key_file")),
        python_executable=_absolute_path(value.get("python_executable")),
        python_sha256=_sha256(value.get("python_sha256")),
        recipe_root=_absolute_path(value.get("recipe_root")),
        process_deadline_seconds=_bounded_process_deadline(
            value.get("process_deadline_seconds")
        ),
        max_concurrency=_bounded_int(
            value.get("max_concurrency"), minimum=1, maximum=MAX_CONCURRENCY
        ),
        io_timeout_seconds=_bounded_timeout(value.get("io_timeout_seconds")),
        close_timeout_seconds=_bounded_timeout(value.get("close_timeout_seconds")),
        action_ttl_ms=ttl,
        lease=_lease(value.get("lease")),
    )


def _secure_json(path: str, *, maximum: int) -> dict[str, object]:
    raw = _acquire_regular_file_bytes(path, maximum=maximum, required_imode=None)
    try:
        decoded = raw.decode("ascii", errors="strict")
        result = json.loads(
            decoded,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except TunnelConfigurationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        _refuse()
    if not isinstance(result, dict):
        _refuse()
    return result


def _bind_command_host(runtime: WorkbenchActionRuntime, config: TunnelConfig) -> None:
    if (
        not isinstance(runtime, WorkbenchActionRuntime)
        or not isinstance(config, TunnelConfig)
        or config.host_id != runtime.host_binding.host_id
        or config.process_deadline_seconds > MAX_PROCESS_DEADLINE_S
    ):
        _refuse()
    runtime._tunnel_command_host = CommandHostBinding(
        host_id=runtime.host_binding.host_id,
        boot_session_id=runtime.host_binding.boot_session_id,
        python_executable=config.python_executable,
        python_sha256=config.python_sha256,
        recipe_root=config.recipe_root,
        process_deadline_seconds=config.process_deadline_seconds,
    )


def load_private_json(path: str, *, maximum: int = MAX_CONFIG_BYTES) -> dict[str, object]:
    """Read one same-UID private configuration document with tunnel hardening."""

    if type(maximum) is not int or not 1 <= maximum <= 4 * 1024 * 1024:
        _refuse()
    return _secure_json(path, maximum=maximum)


def load_tunnel_config(path: str) -> TunnelConfig:
    return parse_tunnel_config(load_private_json(path))


def _secure_action_key(path: str) -> bytes:
    raw = _acquire_regular_file_bytes(
        path,
        maximum=65,
        required_imode=0o600,
        allowed_sizes=frozenset({64, 65}),
    )
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if len(raw) != 64 or any(byte not in b"0123456789abcdef" for byte in raw):
        _refuse()
    return bytes.fromhex(raw.decode("ascii"))


def _open_safe_directory(path: str) -> int:
    selected = Path(_absolute_path(path))
    try:
        before = selected.lstat()
    except OSError:
        _refuse()
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISDIR(before.st_mode)
        or before.st_uid != os.geteuid()
        or stat.S_IMODE(before.st_mode) & 0o022
    ):
        _refuse()
    directory = getattr(os, "O_DIRECTORY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if not directory or not nofollow or not cloexec:
        _refuse()
    fd = -1
    try:
        fd = os.open(selected, os.O_RDONLY | directory | nofollow | cloexec)
        opened = os.fstat(fd)
        if (
            opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or not stat.S_ISDIR(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) & 0o022
            or os.get_inheritable(fd)
        ):
            _refuse()
        return fd
    except BaseException as error:
        if fd >= 0:
            try:
                os.close(fd)
            except BaseException as cleanup_error:
                raise TunnelConfigurationError(
                    "TUNNEL_STARTUP_CLEANUP_UNCERTAIN"
                ) from cleanup_error
        if isinstance(error, TunnelConfigurationError):
            raise
        _refuse()
    raise AssertionError("unreachable")


async def create_runtime_channel(
    config: TunnelConfig,
    *,
    call_receipt_sink=None,
) -> WorkbenchActionRuntime:
    """Compose the fixed-channel entry point from one closed configuration."""

    if not isinstance(config, TunnelConfig):
        _refuse()
    action_token_key = _secure_action_key(config.action_key_file)
    project_fd = -1
    audit_fd = -1
    artifact_fd = -1
    runtime: WorkbenchActionRuntime | None = None
    primary_error: BaseException | None = None
    cleanup_errors: list[BaseException] = []
    try:
        project_fd = _open_safe_directory(config.project_root)
        audit_fd = _open_safe_directory(config.audit_directory)
        artifact_fd = _open_safe_directory(config.artifact_directory)
        runtime = WorkbenchActionRuntime.open_channel(
            channel=config.channel,
            clock_ms=lambda: int(time.time() * 1000),
            project_directory_fd=project_fd,
            audit_directory_fd=audit_fd,
            host_artifact_fd=artifact_fd,
            host_id=config.host_id,
            audit_policy_id=config.audit_policy_id,
            lease=config.lease,
            action_token_key=action_token_key,
            call_receipt_sink=call_receipt_sink,
            max_concurrency=config.max_concurrency,
            io_timeout_seconds=config.io_timeout_seconds,
            action_ttl_ms=config.action_ttl_ms,
        )
        _bind_command_host(runtime, config)
    except BaseException as error:
        primary_error = error
    finally:
        for descriptor in (artifact_fd, audit_fd, project_fd):
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except BaseException as error:
                    cleanup_errors.append(error)
    if cleanup_errors:
        if runtime is not None:
            try:
                await runtime.aclose(timeout=config.close_timeout_seconds)
            except BaseException:
                pass
        raise TunnelConfigurationError("TUNNEL_STARTUP_CLEANUP_UNCERTAIN") from cleanup_errors[0]
    if primary_error is not None:
        if runtime is not None:
            try:
                await runtime.aclose(timeout=config.close_timeout_seconds)
            except (RuntimeCloseIncomplete, RuntimeCloseUncertain):
                raise TunnelConfigurationError(
                    "TUNNEL_STARTUP_CLEANUP_UNCERTAIN"
                ) from primary_error
        if isinstance(primary_error, (RuntimeCloseIncomplete, RuntimeCloseUncertain)):
            raise TunnelConfigurationError(
                "TUNNEL_STARTUP_CLEANUP_UNCERTAIN"
            ) from primary_error
        if isinstance(primary_error, TunnelConfigurationError):
            raise primary_error
        _refuse()
    if runtime is None:
        _refuse()
    return runtime


def _snapshot(value: object, maximum: int) -> object:
    text = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    raw = text.encode("utf-8", errors="strict")
    if len(raw) > maximum:
        raise _PayloadTooLarge("payload too large")
    return json.loads(text)


class _PayloadTooLarge(ValueError):
    """Internal size classification; never serialized with its message."""


def _error(code: str) -> CallToolResult:
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps({"code": code}, separators=(",", ":")),
            )
        ],
        isError=True,
    )


def _action_digest(value: object) -> str | None:
    if type(value) is not str:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fits_maximum_mcp_response(result: CallToolResult) -> bool:
    """Account for the exact escaped result plus the largest admitted request id."""

    response = mcp_types.JSONRPCResponse(
        jsonrpc="2.0",
        id="\x01" * 256,
        result=result.model_dump(mode="json", by_alias=True, exclude_none=True),
    )
    return (
        len(response.model_dump_json(by_alias=True, exclude_none=True).encode("utf-8"))
        + 1
        <= MAX_WIRE_BYTES
    )


class _ClosedTunnelServer(Server):
    """Server-local boundary: unknown names never reach SDK lookup logs."""

    async def _get_cached_tool_definition(self, tool_name: str) -> mcp_types.Tool | None:
        if type(tool_name) is not str or tool_name not in _KNOWN_TUNNEL_TOOLS:
            return None
        return await super()._get_cached_tool_definition(tool_name)

    def call_tool(self, *, validate_input: bool = True):
        register = super().call_tool(validate_input=validate_input)

        def decorator(func):
            registered = register(func)
            sdk_handler = self.request_handlers[mcp_types.CallToolRequest]

            async def closed_call_tool(req: mcp_types.CallToolRequest) -> ServerResult:
                params = getattr(req, "params", None)
                name = getattr(params, "name", None)
                if type(name) is not str or name not in _KNOWN_TUNNEL_TOOLS:
                    return ServerResult(_error("TOOL_NOT_AVAILABLE"))
                return await sdk_handler(req)

            self.request_handlers[mcp_types.CallToolRequest] = closed_call_tool
            return registered

        return decorator


def create_tunnel_action_server(runtime: WorkbenchActionRuntime) -> Server:
    """One low-level MCP server for the fixed channel, or a typed refusal.

    Exactly two request handlers are registered (``tools/list`` and
    ``tools/call``). The existing text patch port and accepted borrowed Read
    port both remain behind the same runtime ownership.
    """

    if not isinstance(runtime, WorkbenchActionRuntime):
        raise ValueError("WORKBENCH_ACTION_RUNTIME_REQUIRED")
    services = getattr(runtime, "channel_services", None)
    if (
        type(services) is not ChannelRuntimeServices
        or type(services.channel) is not FixedTunnelChannel
        or not isinstance(services.audit_sink, DurableAuthAuditSink)
        or services.channel_ref != channel_binding_ref(services.channel)
    ):
        raise ValueError("FIXED_CHANNEL_SERVICES_REQUIRED")
    caller = services.caller
    project_ref = services.project_ref
    command_host = getattr(runtime, "_tunnel_command_host", None)
    if (
        type(command_host) is not CommandHostBinding
        or command_host.host_id != services.host_binding.host_id
        or command_host.boot_session_id != services.host_binding.boot_session_id
    ):
        raise ValueError("FIXED_COMMAND_HOST_REQUIRED")
    read_composition = create_bound_read_composition(runtime)
    token_codec = ActionTokenCodec(services.action_token_key)

    def admission_evidence_for(modifying_tool: str):
        # The durable channel audit written before every dispatch is the only
        # admission owner on this path, so it is the only evidence that can
        # prove a modifying call never crossed the effect boundary.  The
        # digest is the same SHA-256 of the exact action reference the
        # admission rows carry; nothing here reopens admission or retries.
        def admission_evidence(action_ref: object) -> str:
            digest = _action_digest(action_ref)
            if digest is None:
                raise ValueError("action reference digest unavailable")
            return classify_channel_admissions(
                runtime.read_channel_admissions(digest),
                action_digest=digest,
                channel_ref=services.channel_ref,
                policy_id=services.audit_policy_id,
                modifying_tool=modifying_tool,
            )

        return admission_evidence

    prepare, commit, reconcile = create_text_patch_port(
        resolve_binding=runtime.resolve_binding,
        clock_ms=services.clock_ms,
        run_io=runtime.run_io,
        token_codec=token_codec,
        artifact_store=services.artifact_store,
        host=services.host_binding,
        action_ttl_ms=services.action_ttl_ms,
        admission_evidence=admission_evidence_for(COMMIT_TOOL),
    )
    (
        prepare_project_command,
        run_project_command,
        read_action_result,
        reconcile_action,
    ) = create_command_port(
        resolve_binding=runtime.resolve_binding,
        clock_ms=services.clock_ms,
        run_io=runtime.run_io,
        token_codec=token_codec,
        artifact_store=runtime.artifact_store,
        host=command_host,
        inspector=ProcessInspector(),
        action_ttl_ms=services.action_ttl_ms,
        admission_evidence=admission_evidence_for(RUN_COMMAND_TOOL),
    )
    prepare_validator = Draft202012Validator(_PREPARE_INPUT)
    ref_validator = Draft202012Validator(_ACTION_REF_INPUT)
    prepare_output_validator = Draft202012Validator(_PREPARE_OUTPUT)
    effect_output_validator = Draft202012Validator(_EFFECT_OUTPUT)
    read_input_validators = {
        spec.name: Draft202012Validator(spec.input_schema) for spec in READ_TOOL_SPECS
    }
    read_output_validators = {
        name: Draft202012Validator(schema) for name, schema in READ_OUTPUT_SCHEMAS.items()
    }
    command_input_validators = {
        PREPARE_COMMAND_TOOL: Draft202012Validator(_COMMAND_PREPARE_INPUT),
        RUN_COMMAND_TOOL: Draft202012Validator(_COMMAND_ACTION_REF_INPUT),
        READ_ACTION_RESULT_TOOL: Draft202012Validator(_COMMAND_READ_INPUT),
        RECONCILE_ACTION_TOOL: Draft202012Validator(_COMMAND_ACTION_REF_INPUT),
    }
    command_output_validators = {
        PREPARE_COMMAND_TOOL: Draft202012Validator(_COMMAND_PREPARE_OUTPUT),
        RUN_COMMAND_TOOL: Draft202012Validator(_COMMAND_EFFECT_OUTPUT),
        READ_ACTION_RESULT_TOOL: Draft202012Validator(_COMMAND_READ_OUTPUT),
        RECONCILE_ACTION_TOOL: Draft202012Validator(_COMMAND_EFFECT_OUTPUT),
    }

    async def emit_channel_audit(
        *, code: str, accepted: bool, tool: str, action_digest: str | None
    ) -> None:
        # One durable admission fact per tool call, owned by the runtime's
        # bounded physical executor.  Any failure poisons the sink and must
        # block the effect rather than degrade to memory. The narrow runtime
        # method can durably record denial after revocation without reopening
        # effect admission; closing/closed still refuse the audit attempt.
        event = ChannelAuditEvent(
            schema=CHANNEL_AUDIT_SCHEMA,
            policy_id=services.audit_policy_id,
            code=code,
            accepted=accepted,
            channel_ref=services.channel_ref,
            tool=tool,
            action_digest=action_digest,
        )
        await runtime.emit_channel_audit(event)

    def emit_call_receipt(*, name: str, request: object) -> None:
        sink = services.call_receipt_sink
        if sink is None:
            return
        try:
            canonical = json.dumps(
                request,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            call_ref = hashlib.sha256(
                caller.subject_digest.encode("ascii")
                + b"\0"
                + services.channel_ref.encode("ascii")
                + b"\0"
                + name.encode("ascii")
                + b"\0"
                + canonical
            ).hexdigest()
            sink(
                {
                    "schema": TUNNEL_RECEIPT_SCHEMA,
                    "phase": "RECEIVED",
                    "authority_kind": CHANNEL_AUTHORITY_KIND,
                    "channel_ref": services.channel_ref,
                    "tool": name,
                    "call_ref": call_ref,
                }
            )
        except Exception:
            # Diagnostic telemetry is not an authority/effect owner. A sink
            # outage must never mutate action semantics or trigger a retry.
            return

    server: Server = _ClosedTunnelServer(SERVER_NAME, version=SERVER_VERSION)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        read_tools = [
            Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=spec.input_schema,
                outputSchema=READ_OUTPUT_SCHEMAS[spec.name],
                annotations=ToolAnnotations(**spec.annotations),
            )
            for spec in READ_TOOL_SPECS
        ]
        return [
            *read_tools,
            Tool(
                name=PREPARE_TOOL,
                description=(
                    "Prepare exactly one bounded CREATE or unique-text REPLACE "
                    "against the fixed channel's approved project path. This "
                    "does not write."
                ),
                inputSchema=_PREPARE_INPUT,
                outputSchema=_PREPARE_OUTPUT,
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            ),
            Tool(
                name=COMMIT_TOOL,
                description=(
                    "Commit exactly one previously prepared text patch. The only "
                    "input is its signed action reference. Safe replay reconciles "
                    "the same postimage; never substitute another path or payload."
                ),
                inputSchema=_ACTION_REF_INPUT,
                outputSchema=_EFFECT_OUTPUT,
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            ),
            Tool(
                name=RECONCILE_TOOL,
                description=(
                    "Read current source state for one prepared action and classify "
                    "NOT_APPLIED, APPLIED, or EFFECT_UNKNOWN without writing."
                ),
                inputSchema=_ACTION_REF_INPUT,
                outputSchema=_EFFECT_OUTPUT,
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            ),
            Tool(
                name=PREPARE_COMMAND_TOOL,
                description=(
                    "Prepare one pinned command recipe against one exact allowed "
                    "file preimage. This returns a signed reference and starts no process."
                ),
                inputSchema=_COMMAND_PREPARE_INPUT,
                outputSchema=_COMMAND_PREPARE_OUTPUT,
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            ),
            Tool(
                name=RUN_COMMAND_TOOL,
                description=(
                    "Run exactly one previously prepared pinned canary recipe. "
                    "The only input is its signed action reference."
                ),
                inputSchema=_COMMAND_ACTION_REF_INPUT,
                outputSchema=_COMMAND_EFFECT_OUTPUT,
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            ),
            Tool(
                name=READ_ACTION_RESULT_TOOL,
                description=(
                    "Read one bounded page of retained stdout or stderr from a "
                    "completed command action without starting a process."
                ),
                inputSchema=_COMMAND_READ_INPUT,
                outputSchema=_COMMAND_READ_OUTPUT,
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            ),
            Tool(
                name=RECONCILE_ACTION_TOOL,
                description=(
                    "Classify retained command evidence for one signed action "
                    "without starting or replaying a process."
                ),
                inputSchema=_COMMAND_ACTION_REF_INPUT,
                outputSchema=_COMMAND_EFFECT_OUTPUT,
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            ),
        ]

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, object] | None) -> CallToolResult:
        if name not in _KNOWN_TUNNEL_TOOLS:
            return _error("TOOL_NOT_AVAILABLE")
        action_digest: str | None = None
        try:
            request = _snapshot(arguments, MAX_ARGUMENT_BYTES)
            if name in READ_TOOL_NAMES:
                read_input_validators[name].validate(request)
            elif name in COMMAND_TOOL_NAMES:
                command_input_validators[name].validate(request)
                if name != PREPARE_COMMAND_TOOL:
                    action_digest = _action_digest(request["action_ref"])
            elif name == PREPARE_TOOL:
                prepare_validator.validate(request)
            else:
                ref_validator.validate(request)
                action_digest = _action_digest(request["action_ref"])
        except Exception:
            try:
                await emit_channel_audit(
                    code="request_refused",
                    accepted=False,
                    tool=name,
                    action_digest=None,
                )
            except AuditSinkPoisoned:
                return _error("CHANNEL_AUDIT_UNAVAILABLE")
            except (RuntimeClosed, SyncExecutionTimeout):
                return _error("CHANNEL_AUDIT_UNAVAILABLE")
            return _error("INVALID_REQUEST")

        # The fixed channel is the only admission authority on this path.  It
        # is re-resolved live: expiry, root identity, or lease revocation
        # refuses here, before any durable acceptance is written.
        if runtime.resolve_binding(caller, project_ref) is None:
            try:
                await emit_channel_audit(
                    code="channel_refused",
                    accepted=False,
                    tool=name,
                    action_digest=action_digest,
                )
            except AuditSinkPoisoned:
                return _error("CHANNEL_AUDIT_UNAVAILABLE")
            except (RuntimeClosed, SyncExecutionTimeout):
                # A closing/closed or timed-out audit remains unavailable;
                # effect admission stays refused.
                return _error("CHANNEL_ADMISSION_REFUSED")
            return _error("CHANNEL_ADMISSION_REFUSED")
        try:
            await emit_channel_audit(
                code="accepted",
                accepted=True,
                tool=name,
                action_digest=action_digest,
            )
        except (AuditSinkPoisoned, RuntimeClosed, SyncExecutionTimeout):
            # Custody precedes effect: without the durable admission fact the
            # tool call is refused, never silently un-audited.
            return _error("CHANNEL_AUDIT_UNAVAILABLE")

        emit_call_receipt(name=name, request=request)
        try:
            if name in READ_TOOL_NAMES:
                observed = await read_composition.call(name, request)
            elif name == PREPARE_COMMAND_TOOL:
                observed = await prepare_project_command(caller, request)
            elif name == RUN_COMMAND_TOOL:
                observed = await run_project_command(caller, request["action_ref"])
            elif name == READ_ACTION_RESULT_TOOL:
                observed = await read_action_result(caller, request)
            elif name == RECONCILE_ACTION_TOOL:
                observed = await reconcile_action(caller, request["action_ref"])
            elif name == PREPARE_TOOL:
                observed = await prepare(caller, request)
            elif name == COMMIT_TOOL:
                observed = await commit(caller, request["action_ref"])
            else:
                observed = await reconcile(caller, request["action_ref"])
        except ProjectActionRefused as error:
            return _error(error.code)
        except (RuntimeClosed, SyncExecutionTimeout):
            return _error(
                "ACTION_EFFECT_UNKNOWN"
                if name in (COMMIT_TOOL, RUN_COMMAND_TOOL)
                else "CHANNEL_ADMISSION_CHANGED"
            )
        except Exception:
            return _error("ACTION_UNAVAILABLE")

        if name in READ_TOOL_NAMES and observed.get("ok") is not True:
            error = observed.get("error")
            code = error.get("code") if type(error) is dict else None
            return _error(
                code if code in READ_REFUSAL_CODES else "ACTION_RESULT_UNVERIFIED"
            )

        # A response loss after commit may hide an already-applied effect.
        # Never convert post-action admission uncertainty into an invitation
        # to retry.
        if runtime.resolve_binding(caller, project_ref) is None:
            return _error(
                "ACTION_EFFECT_UNKNOWN"
                if name in (COMMIT_TOOL, RUN_COMMAND_TOOL)
                else "CHANNEL_ADMISSION_CHANGED"
            )
        try:
            data = _snapshot(dict(observed), MAX_RESULT_BYTES)
            if name in READ_TOOL_NAMES:
                read_output_validators[name].validate(data)
            elif name in COMMAND_TOOL_NAMES:
                command_output_validators[name].validate(data)
            elif name == PREPARE_TOOL:
                prepare_output_validator.validate(data)
            else:
                effect_output_validator.validate(data)
            result = CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                    )
                ],
                structuredContent=data,
                isError=False,
            )
            if not _fits_maximum_mcp_response(result):
                return _error(
                    "PREVIEW_TOO_LARGE"
                    if name == "preview_text_replace"
                    else (
                        "ACTION_EFFECT_UNKNOWN"
                        if name in (COMMIT_TOOL, RUN_COMMAND_TOOL)
                        else "ACTION_RESULT_UNVERIFIED"
                    )
                )
            return result
        except _PayloadTooLarge:
            return _error(
                "PREVIEW_TOO_LARGE"
                if name == "preview_text_replace"
                else (
                    "ACTION_EFFECT_UNKNOWN"
                    if name in (COMMIT_TOOL, RUN_COMMAND_TOOL)
                    else "ACTION_RESULT_UNVERIFIED"
                )
            )
        except Exception:
            return _error(
                "ACTION_EFFECT_UNKNOWN"
                if name in (COMMIT_TOOL, RUN_COMMAND_TOOL)
                else "ACTION_RESULT_UNVERIFIED"
            )

    return server


_MODERN_SERVER_INFO_KEY = "io.modelcontextprotocol/serverInfo"


def _modern_server_meta() -> dict[str, object]:
    return {
        _MODERN_SERVER_INFO_KEY: {"name": SERVER_NAME, "version": SERVER_VERSION}
    }


def _modern_response(request_id: str | int, result: dict[str, object]) -> dict[str, object]:
    result["resultType"] = "complete"
    result["_meta"] = _modern_server_meta()
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _modern_error(
    request_id: str | int | None, code: int, message: str
) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _modern_model_dump(value: object) -> dict[str, object]:
    dump = getattr(value, "model_dump", None)
    if not callable(dump):
        raise TypeError("MODERN_MCP_RESULT_REQUIRED")
    selected = dump(by_alias=True, mode="json", exclude_none=True)
    if type(selected) is not dict:
        raise TypeError("MODERN_MCP_RESULT_REQUIRED")
    return dict(selected)


async def _serve_modern_stdio(server: Server, first_line: str) -> None:
    """Serve the bounded 2026 tool envelope without creating another effect plane."""

    line: str | None = first_line
    while line is not None:
        request_id: str | int | None = None
        try:
            request = parse_modern_protocol_request(line)
            if "id" not in request:
                # Modern notifications carry no response.  Workbench currently
                # advertises no notification-driven capability.
                line = await read_bounded_stdio_line()
                continue
            request_id = request["id"]  # validated by the boundary
            method = request["method"]
            params = request.get("params") or {}
            if type(params) is not dict:
                raise ValueError("PROTOCOL_PARAMS")

            if method == "server/discover":
                if set(params) - {"_meta"}:
                    await write_bounded_stdio_json(
                        _modern_error(request_id, -32602, "invalid params")
                    )
                else:
                    await write_bounded_stdio_json(
                        _modern_response(
                            request_id,
                            {
                                "ttlMs": 0,
                                "cacheScope": "public",
                                "supportedVersions": [MODERN_PROTOCOL_VERSION],
                                "capabilities": {"tools": {"listChanged": False}},
                            },
                        )
                    )
            elif method == "tools/list":
                cursor = params.get("cursor")
                if set(params) - {"_meta", "cursor"} or cursor not in (None, ""):
                    await write_bounded_stdio_json(
                        _modern_error(request_id, -32602, "invalid params")
                    )
                else:
                    handler = server.request_handlers[mcp_types.ListToolsRequest]
                    response = await handler(None)
                    tools = [
                        _modern_model_dump(tool) for tool in response.root.tools
                    ]
                    await write_bounded_stdio_json(
                        _modern_response(
                            request_id,
                            {
                                "ttlMs": 0,
                                "cacheScope": "public",
                                "tools": tools,
                            },
                        )
                    )
            elif method == "tools/call":
                if set(params) - {"_meta", "name", "arguments"}:
                    await write_bounded_stdio_json(
                        _modern_error(request_id, -32602, "invalid params")
                    )
                else:
                    name = params.get("name")
                    arguments = params.get("arguments")
                    if type(name) is not str or (
                        arguments is not None and type(arguments) is not dict
                    ):
                        await write_bounded_stdio_json(
                            _modern_error(request_id, -32602, "invalid params")
                        )
                    else:
                        handler = server.request_handlers[mcp_types.CallToolRequest]
                        response = await handler(
                            mcp_types.CallToolRequest(
                                params=mcp_types.CallToolRequestParams(
                                    name=name, arguments=arguments
                                )
                            )
                        )
                        await write_bounded_stdio_json(
                            _modern_response(
                                request_id, _modern_model_dump(response.root)
                            )
                        )
            elif method == "ping":
                if set(params) - {"_meta"}:
                    await write_bounded_stdio_json(
                        _modern_error(request_id, -32602, "invalid params")
                    )
                else:
                    await write_bounded_stdio_json(
                        _modern_response(request_id, {})
                    )
            else:
                await write_bounded_stdio_json(
                    _modern_error(request_id, -32601, "method not found")
                )
        except (ValueError, TypeError, RecursionError, UnicodeError):
            await write_bounded_stdio_json(
                _modern_error(request_id, -32600, "WORKBENCH_MCP_INVALID_REQUEST")
            )
        except Exception:
            await write_bounded_stdio_json(
                _modern_error(request_id, -32603, "WORKBENCH_MCP_INTERNAL_ERROR")
            )
        line = await read_bounded_stdio_line()


async def run_server_stdio(
    runtime: WorkbenchActionRuntime,
    *,
    server_factory,
    close_timeout_seconds: float,
) -> None:
    """Serve one fixed-channel MCP server and always close the runtime owner.

    The caller selects only the model-facing tool server. Runtime/lease/audit/
    artifact/process ownership remains the existing Workbench runtime.
    """

    if not isinstance(runtime, WorkbenchActionRuntime):
        raise ValueError("WORKBENCH_ACTION_RUNTIME_REQUIRED")
    if not callable(server_factory):
        raise ValueError("WORKBENCH_STDIO_SERVER_FACTORY_REQUIRED")
    primary: BaseException | None = None
    try:
        server = server_factory(runtime)
        if not isinstance(server, Server):
            raise ValueError("WORKBENCH_STDIO_SERVER_REQUIRED")
        options = server.create_initialization_options(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        )
        first_line = await read_bounded_stdio_line()
        if first_line is None:
            return
        if is_modern_protocol_request(first_line):
            await _serve_modern_stdio(server, first_line)
        else:
            async with private_stdio_server(initial_line=first_line) as (read_stream, write_stream):
                await server.run(read_stream, write_stream, options)
    except BaseException as error:
        primary = error
        raise
    finally:
        runtime.revoke()
        try:
            await runtime.aclose(timeout=close_timeout_seconds)
        except (RuntimeCloseIncomplete, RuntimeCloseUncertain) as close_error:
            raise close_error from primary
        except BaseException as close_error:
            if primary is None:
                raise
            raise close_error from primary


async def run_stdio(runtime: WorkbenchActionRuntime, *, close_timeout_seconds: float) -> None:
    """Serve the existing Action fixed-channel surface over stdio."""

    await run_server_stdio(
        runtime,
        server_factory=create_tunnel_action_server,
        close_timeout_seconds=close_timeout_seconds,
    )


async def _serve(config: TunnelConfig) -> int:
    runtime = await create_runtime_channel(config)
    try:
        await run_stdio(runtime, close_timeout_seconds=config.close_timeout_seconds)
    except RuntimeCloseIncomplete:
        return shutdown_exit_code(ShutdownOutcome.RUNTIME_CLOSE_INCOMPLETE)
    except RuntimeCloseUncertain:
        return shutdown_exit_code(ShutdownOutcome.RUNTIME_CLOSE_UNCERTAIN)
    except BaseException:
        return shutdown_exit_code(ShutdownOutcome.SERVER_FAILED)
    return shutdown_exit_code(ShutdownOutcome.CLEAN)


def run_configured_stdio(path: str) -> int:
    try:
        config = load_tunnel_config(path)
        return asyncio.run(_serve(config))
    except TunnelConfigurationError as error:
        print(error.code, file=sys.stderr, flush=True)
        return 5 if error.code == "TUNNEL_STARTUP_CLEANUP_UNCERTAIN" else 2
    except BaseException:
        print("TUNNEL_RUNTIME_FAILED", file=sys.stderr, flush=True)
        return 5


__all__ = [
    "SERVER_NAME",
    "SERVER_VERSION",
    "TUNNEL_RECEIPT_SCHEMA",
    "TUNNEL_SCHEMA",
    "TunnelConfig",
    "TunnelConfigurationError",
    "create_runtime_channel",
    "create_tunnel_action_server",
    "load_private_json",
    "load_tunnel_config",
    "parse_tunnel_config",
    "run_configured_stdio",
    "run_server_stdio",
    "run_stdio",
]
