"""Closed signed contracts for the fixed Workbench command canaries."""

from __future__ import annotations

import dataclasses
import math
import os
import re


COMMAND_TOKEN_SCHEMA = "mastermind.workbench_closed_command.v1"
COMMAND_CLAIM_SCHEMA = "mastermind.workbench_command_claim.v1"
COMMAND_PROCESS_SCHEMA = "mastermind.workbench_command_process.v1"
COMMAND_RESULT_SCHEMA = "mastermind.workbench_command_result.v1"
COMMAND_HMAC_PURPOSE = b"mastermind.workbench_closed_command.v1"
RECIPE_IDS = frozenset({"canary_checksum", "canary_refuse"})
RECIPE_SHA256 = {
    "canary_checksum": "6a472df0eab211d5c4c28a24522b73a440e30c7aea333305fca1600123a8b90c",
    "canary_refuse": "61073fcf43e07d547ecc224ac50dadb4a896f7e50a3001fbbc99b7521878f80a",
}
MAX_PROCESS_DEADLINE_S = 15.0
MAX_STDOUT_BYTES = 65536
MAX_STDERR_BYTES = 65536
MAX_PAGE_LINES = 128
MAX_PAGE_BYTES = 8192
MAX_CLAIM_BYTES = 4096
MAX_RESULT_JSON_BYTES = 16384
PAGE_LINE_COUNT = 40

_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_BOOT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SOURCE_IDENTITY = re.compile(r"^[0-9]+(:[0-9]+){8}$")


@dataclasses.dataclass(frozen=True)
class PreparedClosedCommand:
    schema: str
    action_id: str
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
    artifact_store_device: int
    artifact_store_inode: int
    committed_head: str | None
    host_id: str
    boot_session_id: str
    relative_path: str
    recipe_id: str
    preimage_sha256: str
    source_identity: str
    issued_at_ms: int
    expires_at_ms: int


@dataclasses.dataclass(frozen=True)
class CommandHostBinding:
    host_id: str
    boot_session_id: str
    python_executable: str
    python_sha256: str
    recipe_root: str
    process_deadline_seconds: float = MAX_PROCESS_DEADLINE_S


def validate_command_host_binding(value: object) -> CommandHostBinding:
    if type(value) is not CommandHostBinding:
        raise ValueError("invalid command host binding")
    if (
        type(value.host_id) is not str
        or _HEX64.fullmatch(value.host_id) is None
        or type(value.boot_session_id) is not str
        or _BOOT.fullmatch(value.boot_session_id) is None
        or type(value.python_executable) is not str
        or not os.path.isabs(value.python_executable)
        or not value.python_executable
        or "\x00" in value.python_executable
        or len(value.python_executable.encode("utf-8")) > 4096
        or _HEX64.fullmatch(value.python_sha256) is None
        or type(value.recipe_root) is not str
        or not os.path.isabs(value.recipe_root)
        or not value.recipe_root
        or "\x00" in value.recipe_root
        or len(value.recipe_root.encode("utf-8")) > 4096
        or isinstance(value.process_deadline_seconds, bool)
        or not isinstance(value.process_deadline_seconds, (int, float))
        or not math.isfinite(float(value.process_deadline_seconds))
        or not 0 < float(value.process_deadline_seconds) <= MAX_PROCESS_DEADLINE_S
    ):
        raise ValueError("invalid command host binding")
    return value


def validate_prepared_command(
    value: object, *, now_ms: int, require_fresh: bool = True
) -> PreparedClosedCommand:
    from .contracts import ActionContractError, MAX_ACTION_TTL_MS, validate_relative_path

    if type(value) is not PreparedClosedCommand:
        raise ActionContractError("invalid prepared command")
    if type(now_ms) is not int or not 0 <= now_ms < 2**63:
        raise ActionContractError("invalid prepared command")
    if (
        type(value.schema) is not str
        or value.schema != COMMAND_TOKEN_SCHEMA
        or type(value.action_id) is not str
        or _HEX32.fullmatch(value.action_id) is None
        or type(value.subject_digest) is not str
        or _HEX64.fullmatch(value.subject_digest) is None
        or type(value.client_ref) is not str
        or not value.client_ref
        or len(value.client_ref) > 256
        or type(value.resource) is not str
        or not value.resource
        or len(value.resource) > 2048
        or type(value.project_ref) is not str
        or _REF.fullmatch(value.project_ref) is None
        or type(value.context_ref) is not str
        or _REF.fullmatch(value.context_ref) is None
        or type(value.responsibility_ref) is not str
        or _REF.fullmatch(value.responsibility_ref) is None
        or type(value.operation_ref) is not str
        or _REF.fullmatch(value.operation_ref) is None
        or type(value.owner_ref) is not str
        or _REF.fullmatch(value.owner_ref) is None
        or type(value.generation) is not str
        or _REF.fullmatch(value.generation) is None
        or type(value.root_device) is not int
        or value.root_device < 0
        or type(value.root_inode) is not int
        or value.root_inode < 0
        or type(value.artifact_store_device) is not int
        or value.artifact_store_device < 0
        or type(value.artifact_store_inode) is not int
        or value.artifact_store_inode < 0
        or type(value.host_id) is not str
        or _HEX64.fullmatch(value.host_id) is None
        or type(value.boot_session_id) is not str
        or _BOOT.fullmatch(value.boot_session_id) is None
        or type(value.recipe_id) is not str
        or value.recipe_id not in RECIPE_IDS
        or type(value.preimage_sha256) is not str
        or _HEX64.fullmatch(value.preimage_sha256) is None
        or type(value.source_identity) is not str
        or _SOURCE_IDENTITY.fullmatch(value.source_identity) is None
    ):
        raise ActionContractError("invalid prepared command")
    validate_relative_path(value.relative_path)
    if value.committed_head is not None and (
        type(value.committed_head) is not str
        or _HEX40.fullmatch(value.committed_head) is None
    ):
        raise ActionContractError("invalid prepared command")
    if (
        type(value.issued_at_ms) is not int
        or type(value.expires_at_ms) is not int
        or value.issued_at_ms < 0
        or value.expires_at_ms <= value.issued_at_ms
        or value.expires_at_ms - value.issued_at_ms > MAX_ACTION_TTL_MS
        or value.expires_at_ms >= 2**63
    ):
        raise ActionContractError("prepared command expired or invalid")
    if require_fresh and value.expires_at_ms <= now_ms:
        raise ActionContractError("prepared command expired or invalid")
    return value


__all__ = [
    "COMMAND_CLAIM_SCHEMA",
    "COMMAND_HMAC_PURPOSE",
    "COMMAND_PROCESS_SCHEMA",
    "COMMAND_RESULT_SCHEMA",
    "COMMAND_TOKEN_SCHEMA",
    "MAX_CLAIM_BYTES",
    "MAX_PAGE_BYTES",
    "MAX_PAGE_LINES",
    "MAX_PROCESS_DEADLINE_S",
    "MAX_RESULT_JSON_BYTES",
    "MAX_STDERR_BYTES",
    "MAX_STDOUT_BYTES",
    "PAGE_LINE_COUNT",
    "RECIPE_IDS",
    "RECIPE_SHA256",
    "CommandHostBinding",
    "PreparedClosedCommand",
    "validate_command_host_binding",
    "validate_prepared_command",
]
