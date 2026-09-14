"""Closed contracts for one bounded attended Workbench validation process.

The model selects only an owner-provisioned recipe and may lower its time/output
ceilings. It never selects an executable, shell, cwd, environment, host, root,
credential, network policy, process PID, or retry carrier. The signed command
reference binds caller + selected-project authority + exact recipe generation.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import re
from typing import Any

from .contracts import ActionCaller, ActionContractError, ActionScope

COMMAND_TOKEN_SCHEMA = "mastermind.workbench_attended_command.v1"
MAX_COMMAND_REF_BYTES = 32768
MAX_COMMAND_TTL_MS = 5 * 60 * 1000
MAX_RECIPE_COUNT = 16
MAX_RECIPE_ARG_BYTES = 512
MAX_RECIPE_DESCRIPTION_BYTES = 512
MAX_RECIPE_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_RECIPE_TIMEOUT_SECONDS = 60
_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_RECIPE = re.compile(r"^[a-z][a-z0-9._-]{2,63}$")
_FORBIDDEN_EXECUTABLES = frozenset(
    {
        "/bin/sh",
        "/bin/bash",
        "/bin/zsh",
        "/usr/bin/env",
        "/usr/bin/osascript",
    }
)
_DOMAIN = b"mastermind.workbench_attended_command.v1\0"


@dataclasses.dataclass(frozen=True)
class ValidationRecipe:
    recipe_id: str
    description: str
    argv: tuple[str, ...]
    timeout_seconds: int
    max_output_bytes: int

    @property
    def digest(self) -> str:
        return recipe_digest(self)


@dataclasses.dataclass(frozen=True)
class PreparedCommand:
    schema: str
    command_id: str
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
    committed_head: str | None
    recipe_id: str
    recipe_digest: str
    runner_digest: str
    timeout_seconds: int
    max_output_bytes: int
    issued_at_ms: int
    expires_at_ms: int


class ProcessContractError(ActionContractError):
    """Closed command/ref validation failure."""


def _text(value: object, *, maximum_bytes: int, allow_space: bool = True) -> str:
    if type(value) is not str or not value or "\x00" in value:
        raise ProcessContractError("invalid text")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ProcessContractError("invalid text")
    if not allow_space and value != value.strip():
        raise ProcessContractError("invalid text")
    try:
        if len(value.encode("utf-8")) > maximum_bytes:
            raise ProcessContractError("text too large")
    except UnicodeError as error:
        raise ProcessContractError("invalid text") from error
    return value


def validate_recipe(value: object) -> ValidationRecipe:
    if type(value) is not ValidationRecipe:
        raise ProcessContractError("invalid validation recipe")
    if type(value.recipe_id) is not str or _RECIPE.fullmatch(value.recipe_id) is None:
        raise ProcessContractError("invalid validation recipe")
    _text(value.description, maximum_bytes=MAX_RECIPE_DESCRIPTION_BYTES)
    if type(value.argv) is not tuple or not 1 <= len(value.argv) <= 32:
        raise ProcessContractError("invalid validation recipe")
    argv: list[str] = []
    for index, item in enumerate(value.argv):
        selected = _text(item, maximum_bytes=MAX_RECIPE_ARG_BYTES)
        if index == 0:
            if not selected.startswith("/") or selected in _FORBIDDEN_EXECUTABLES:
                raise ProcessContractError("recipe executable is not admitted")
        argv.append(selected)
    if type(value.timeout_seconds) is not int or not 1 <= value.timeout_seconds <= MAX_RECIPE_TIMEOUT_SECONDS:
        raise ProcessContractError("invalid validation recipe")
    if type(value.max_output_bytes) is not int or not 1024 <= value.max_output_bytes <= MAX_RECIPE_OUTPUT_BYTES:
        raise ProcessContractError("invalid validation recipe")
    return value


def recipe_digest(value: ValidationRecipe) -> str:
    selected = validate_recipe(value)
    payload = {
        "recipe_id": selected.recipe_id,
        "description": selected.description,
        "argv": list(selected.argv),
        "timeout_seconds": selected.timeout_seconds,
        "max_output_bytes": selected.max_output_bytes,
    }
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_recipe_set(value: object) -> tuple[ValidationRecipe, ...]:
    if type(value) is not tuple or not 1 <= len(value) <= MAX_RECIPE_COUNT:
        raise ProcessContractError("invalid validation recipe set")
    selected = tuple(validate_recipe(recipe) for recipe in value)
    ids = tuple(recipe.recipe_id for recipe in selected)
    if len(ids) != len(set(ids)) or ids != tuple(sorted(ids)):
        raise ProcessContractError("validation recipes must be sorted and unique")
    return selected


def validate_prepared_command(
    value: object, *, now_ms: int, allow_expired: bool = False
) -> PreparedCommand:
    if type(value) is not PreparedCommand:
        raise ProcessContractError("invalid prepared command")
    if (
        value.schema != COMMAND_TOKEN_SCHEMA
        or type(value.command_id) is not str
        or _HEX32.fullmatch(value.command_id) is None
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
        or type(value.recipe_id) is not str
        or _RECIPE.fullmatch(value.recipe_id) is None
        or type(value.recipe_digest) is not str
        or _HEX64.fullmatch(value.recipe_digest) is None
        or type(value.runner_digest) is not str
        or _HEX64.fullmatch(value.runner_digest) is None
    ):
        raise ProcessContractError("invalid prepared command")
    if value.committed_head is not None and (
        type(value.committed_head) is not str or _HEX40.fullmatch(value.committed_head) is None
    ):
        raise ProcessContractError("invalid prepared command")
    if type(value.timeout_seconds) is not int or not 1 <= value.timeout_seconds <= MAX_RECIPE_TIMEOUT_SECONDS:
        raise ProcessContractError("invalid prepared command")
    if type(value.max_output_bytes) is not int or not 1024 <= value.max_output_bytes <= MAX_RECIPE_OUTPUT_BYTES:
        raise ProcessContractError("invalid prepared command")
    if (
        type(value.issued_at_ms) is not int
        or type(value.expires_at_ms) is not int
        or value.issued_at_ms < 0
        or value.expires_at_ms <= value.issued_at_ms
        or value.expires_at_ms - value.issued_at_ms > MAX_COMMAND_TTL_MS
        or (not allow_expired and value.expires_at_ms <= now_ms)
        or value.expires_at_ms >= 2**63
    ):
        raise ProcessContractError("prepared command expired or invalid")
    return value


def prepared_matches_authority(
    prepared: PreparedCommand,
    caller: ActionCaller,
    scope: ActionScope,
    project_ref: str,
) -> bool:
    return (
        caller.subject_digest == prepared.subject_digest
        and caller.client_ref == prepared.client_ref
        and caller.resource == prepared.resource
        and project_ref == prepared.project_ref
        and scope.context_ref == prepared.context_ref
        and scope.responsibility_ref == prepared.responsibility_ref
        and scope.operation_ref == prepared.operation_ref
        and scope.owner_ref == prepared.owner_ref
        and scope.generation == prepared.generation
        and scope.root_device == prepared.root_device
        and scope.root_inode == prepared.root_inode
        and scope.committed_head == prepared.committed_head
    )


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    try:
        encoded = value.encode("ascii")
        padding = b"=" * (-len(encoded) % 4)
        decoded = base64.urlsafe_b64decode(encoded + padding)
        if _b64encode(decoded) != value:
            raise ProcessContractError("invalid command reference")
        return decoded
    except ProcessContractError:
        raise
    except Exception as error:
        raise ProcessContractError("invalid command reference") from error


class CommandTokenCodec:
    """Stateless, domain-separated HMAC envelope for one prepared command."""

    def __init__(self, key: bytes) -> None:
        if type(key) is not bytes or len(key) < 32:
            raise ValueError("command token key must contain at least 32 bytes")
        self._key = hmac.new(key, _DOMAIN, hashlib.sha256).digest()

    def encode(self, value: PreparedCommand) -> str:
        validate_prepared_command(value, now_ms=value.issued_at_ms)
        payload = json.dumps(
            dataclasses.asdict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        signature = hmac.new(self._key, payload, hashlib.sha256).digest()
        token = f"{_b64encode(payload)}.{_b64encode(signature)}"
        if len(token.encode("ascii")) > MAX_COMMAND_REF_BYTES:
            raise ProcessContractError("prepared command is too large")
        return token

    def decode(
        self, token: object, *, now_ms: int, allow_expired: bool = False
    ) -> PreparedCommand:
        if type(token) is not str or not token or len(token.encode("utf-8")) > MAX_COMMAND_REF_BYTES:
            raise ProcessContractError("invalid command reference")
        parts = token.split(".")
        if len(parts) != 2:
            raise ProcessContractError("invalid command reference")
        payload = _b64decode(parts[0])
        supplied = _b64decode(parts[1])
        expected = hmac.new(self._key, payload, hashlib.sha256).digest()
        if len(supplied) != len(expected) or not hmac.compare_digest(supplied, expected):
            raise ProcessContractError("invalid command reference")
        try:
            raw: Any = json.loads(payload.decode("utf-8"))
            names = {field.name for field in dataclasses.fields(PreparedCommand)}
            if type(raw) is not dict or set(raw) != names:
                raise ProcessContractError("invalid command reference")
            value = PreparedCommand(**raw)
        except ProcessContractError:
            raise
        except Exception as error:
            raise ProcessContractError("invalid command reference") from error
        return validate_prepared_command(
            value, now_ms=now_ms, allow_expired=allow_expired
        )


__all__ = [
    "COMMAND_TOKEN_SCHEMA",
    "MAX_COMMAND_REF_BYTES",
    "MAX_COMMAND_TTL_MS",
    "MAX_RECIPE_OUTPUT_BYTES",
    "MAX_RECIPE_TIMEOUT_SECONDS",
    "CommandTokenCodec",
    "PreparedCommand",
    "ProcessContractError",
    "ValidationRecipe",
    "prepared_matches_authority",
    "recipe_digest",
    "validate_prepared_command",
    "validate_recipe",
    "validate_recipe_set",
]
