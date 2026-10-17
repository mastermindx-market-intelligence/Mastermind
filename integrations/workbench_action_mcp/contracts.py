"""Closed contracts for one attended Workbench text-patch action.

The signed action reference is stateless: it binds one authenticated caller,
one selected project/root generation, one exact relative path, one preimage and
one deterministic postimage. It is not a grant by itself; every use must
re-resolve the current owner binding.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import re
from typing import Any

from .command_contracts import (
    ARTIFACT_HMAC_PURPOSE,
    COMMAND_HMAC_PURPOSE,
    PreparedActionArtifact,
    PreparedClosedCommand,
    validate_prepared_artifact,
    validate_prepared_command,
)

ACTION_TOKEN_SCHEMA = "mastermind.workbench_text_patch.v2"
ACTION_TOKEN_SCHEMA_V1 = "mastermind.workbench_text_patch.v1"
ACTION_TOKEN_PURPOSE = "text_patch"
MAX_ACTION_REF_BYTES = 65536
MAX_PATCH_TEXT_BYTES = 16384
MAX_ACTION_TTL_MS = 5 * 60 * 1000
_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_BOOT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SOURCE_IDENTITY = re.compile(r"^[0-9]+(:[0-9]+){8}$")


@dataclasses.dataclass(frozen=True)
class ActionCaller:
    subject_digest: str
    client_ref: str
    resource: str
    scopes: tuple[str, ...]
    expires_at: int


@dataclasses.dataclass(frozen=True)
class ActionScope:
    """Request-local projection of an existing selected-project owner."""

    root_fd: int
    root_device: int
    root_inode: int
    context_ref: str
    responsibility_ref: str
    operation_ref: str
    owner_ref: str
    generation: str
    allowed_paths: tuple[str, ...]
    expires_at_ms: int
    committed_head: str | None = None


@dataclasses.dataclass(frozen=True)
class ProjectActionBinding:
    caller: ActionCaller
    project_ref: str
    scope: ActionScope


@dataclasses.dataclass(frozen=True)
class PreparedTextPatch:
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
    host_id: str
    boot_session_id: str
    purpose: str
    committed_head: str | None
    relative_path: str
    mode: str
    preimage_sha256: str | None
    postimage_sha256: str
    source_identity: str | None
    old_text: str | None
    new_text: str
    issued_at_ms: int
    expires_at_ms: int


class ActionContractError(ValueError):
    """Closed validation failure; callers must not expose dependency detail."""


def validate_relative_path(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value.startswith(("/", "~"))
        or "\\" in value
        or ":" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ActionContractError("invalid relative path")
    try:
        raw = value.encode("utf-8")
        parts = value.split("/")
        if (
            len(raw) > 512
            or len(parts) > 16
            or any(
                part in ("", ".", "..") or len(part.encode("utf-8")) > 255
                for part in parts
            )
        ):
            raise ActionContractError("invalid relative path")
    except UnicodeError as error:
        raise ActionContractError("invalid relative path") from error
    return value


def validate_action_scope(value: object, *, now_ms: int) -> ActionScope:
    if type(value) is not ActionScope:
        raise ActionContractError("invalid action scope")
    if (
        type(value.root_fd) is not int
        or value.root_fd < 0
        or type(value.root_device) is not int
        or value.root_device < 0
        or type(value.root_inode) is not int
        or value.root_inode < 0
        or type(value.expires_at_ms) is not int
        or value.expires_at_ms <= now_ms
        or value.expires_at_ms >= 2**63
    ):
        raise ActionContractError("invalid action scope")
    for name in ("context_ref", "responsibility_ref", "operation_ref", "owner_ref", "generation"):
        selected = getattr(value, name)
        if type(selected) is not str or _REF.fullmatch(selected) is None:
            raise ActionContractError("invalid action scope")
    if (
        type(value.allowed_paths) is not tuple
        or not value.allowed_paths
        or len(value.allowed_paths) > 64
    ):
        raise ActionContractError("invalid action scope")
    paths = tuple(validate_relative_path(path) for path in value.allowed_paths)
    if len(paths) != len(set(paths)):
        raise ActionContractError("invalid action scope")
    if value.committed_head is not None and (
        type(value.committed_head) is not str
        or _HEX40.fullmatch(value.committed_head) is None
    ):
        raise ActionContractError("invalid action scope")
    return value


def validate_action_caller(value: object) -> ActionCaller:
    if type(value) is not ActionCaller:
        raise ActionContractError("invalid action caller")
    if (
        type(value.subject_digest) is not str
        or _HEX64.fullmatch(value.subject_digest) is None
        or type(value.client_ref) is not str
        or not value.client_ref
        or len(value.client_ref) > 256
        or type(value.resource) is not str
        or not value.resource
        or len(value.resource) > 2048
        or value.scopes != ("workbench.action",)
        or type(value.expires_at) is not int
        or value.expires_at <= 0
    ):
        raise ActionContractError("invalid action caller")
    return value


def validate_prepared(
    value: object, *, now_ms: int, require_fresh: bool = True
) -> PreparedTextPatch:
    if type(value) is not PreparedTextPatch:
        raise ActionContractError("invalid prepared action")
    if value.schema == ACTION_TOKEN_SCHEMA_V1:
        raise ActionContractError("invalid action reference")
    if (
        value.schema != ACTION_TOKEN_SCHEMA
        or value.purpose != ACTION_TOKEN_PURPOSE
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
    ):
        raise ActionContractError("invalid prepared action")
    validate_relative_path(value.relative_path)
    if value.committed_head is not None and (
        type(value.committed_head) is not str
        or _HEX40.fullmatch(value.committed_head) is None
    ):
        raise ActionContractError("invalid prepared action")
    if value.mode not in ("CREATE", "REPLACE"):
        raise ActionContractError("invalid prepared action")
    if value.preimage_sha256 is not None and (
        type(value.preimage_sha256) is not str
        or _HEX64.fullmatch(value.preimage_sha256) is None
    ):
        raise ActionContractError("invalid prepared action")
    if (
        type(value.postimage_sha256) is not str
        or _HEX64.fullmatch(value.postimage_sha256) is None
    ):
        raise ActionContractError("invalid prepared action")
    if value.mode == "CREATE":
        if (
            value.preimage_sha256 is not None
            or value.old_text is not None
            or value.source_identity is not None
        ):
            raise ActionContractError("invalid prepared action")
    elif (
        value.preimage_sha256 is None
        or type(value.old_text) is not str
        or not value.old_text
        or type(value.source_identity) is not str
        or _SOURCE_IDENTITY.fullmatch(value.source_identity) is None
    ):
        raise ActionContractError("invalid prepared action")
    if type(value.new_text) is not str:
        raise ActionContractError("invalid prepared action")
    try:
        if (
            value.old_text is not None
            and len(value.old_text.encode("utf-8")) > MAX_PATCH_TEXT_BYTES
        ):
            raise ActionContractError("patch text too large")
        if len(value.new_text.encode("utf-8")) > MAX_PATCH_TEXT_BYTES:
            raise ActionContractError("patch text too large")
    except UnicodeError as error:
        raise ActionContractError("invalid patch text") from error
    if "\x00" in value.new_text or (
        value.old_text is not None and "\x00" in value.old_text
    ):
        raise ActionContractError("invalid patch text")
    if (
        type(value.issued_at_ms) is not int
        or type(value.expires_at_ms) is not int
        or value.issued_at_ms < 0
        or value.expires_at_ms <= value.issued_at_ms
        or value.expires_at_ms - value.issued_at_ms > MAX_ACTION_TTL_MS
        or value.expires_at_ms >= 2**63
    ):
        raise ActionContractError("prepared action expired or invalid")
    if require_fresh and value.expires_at_ms <= now_ms:
        raise ActionContractError("prepared action expired or invalid")
    return value


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    try:
        encoded = value.encode("ascii")
        padding = b"=" * (-len(encoded) % 4)
        decoded = base64.urlsafe_b64decode(encoded + padding)
        if _b64encode(decoded) != value:
            raise ActionContractError("invalid action reference")
        return decoded
    except ActionContractError:
        raise
    except Exception as error:
        raise ActionContractError("invalid action reference") from error


class ActionTokenCodec:
    """Stateless HMAC envelope for one already-prepared patch."""

    def __init__(self, key: bytes) -> None:
        if type(key) is not bytes or len(key) < 32:
            raise ValueError("action token key must contain at least 32 bytes")
        self._key = bytes(key)

    def _mac(self, payload: bytes, *, purpose: bytes | None = None) -> bytes:
        signed = payload if purpose is None else purpose + b"\x00" + payload
        return hmac.new(self._key, signed, hashlib.sha256).digest()

    def encode(self, value: PreparedTextPatch) -> str:
        validate_prepared(value, now_ms=value.issued_at_ms)
        payload = json.dumps(
            dataclasses.asdict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        if len(payload) > MAX_ACTION_REF_BYTES // 2:
            raise ActionContractError("prepared action is too large")
        signature = self._mac(payload)
        token = f"{_b64encode(payload)}.{_b64encode(signature)}"
        if len(token.encode("ascii")) > MAX_ACTION_REF_BYTES:
            raise ActionContractError("prepared action is too large")
        return token

    def decode(self, token: object, *, now_ms: int) -> PreparedTextPatch:
        return self._decode(token, now_ms=now_ms, require_fresh=True)

    def decode_evidence(self, token: object, *, now_ms: int) -> PreparedTextPatch:
        """Integrity-only decode. Expired apply tokens remain readable."""

        return self._decode(token, now_ms=now_ms, require_fresh=False)

    def _decode(
        self, token: object, *, now_ms: int, require_fresh: bool
    ) -> PreparedTextPatch:
        if type(token) is not str or not token or len(token.encode("utf-8")) > MAX_ACTION_REF_BYTES:
            raise ActionContractError("invalid action reference")
        parts = token.split(".")
        if len(parts) != 2:
            raise ActionContractError("invalid action reference")
        payload = _b64decode(parts[0])
        supplied = _b64decode(parts[1])
        expected = self._mac(payload)
        if len(supplied) != len(expected) or not hmac.compare_digest(supplied, expected):
            raise ActionContractError("invalid action reference")
        try:
            raw: Any = json.loads(payload.decode("utf-8"))
            names = {field.name for field in dataclasses.fields(PreparedTextPatch)}
            if type(raw) is not dict or set(raw) != names:
                raise ActionContractError("invalid action reference")
            value = PreparedTextPatch(**raw)
        except ActionContractError:
            raise
        except Exception as error:
            raise ActionContractError("invalid action reference") from error
        return validate_prepared(value, now_ms=now_ms, require_fresh=require_fresh)

    def encode_artifact(self, value: PreparedActionArtifact) -> str:
        validate_prepared_artifact(
            value, now_ms=value.issued_at_ms, require_fresh=True
        )
        payload = json.dumps(
            dataclasses.asdict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        if len(payload) > MAX_ACTION_REF_BYTES // 2:
            raise ActionContractError("artifact reference is too large")
        signature = self._mac(payload, purpose=ARTIFACT_HMAC_PURPOSE)
        token = f"{_b64encode(payload)}.{_b64encode(signature)}"
        if len(token.encode("ascii")) > MAX_ACTION_REF_BYTES:
            raise ActionContractError("artifact reference is too large")
        return token

    def decode_artifact(
        self, token: object, *, now_ms: int
    ) -> PreparedActionArtifact:
        return self._decode_artifact(token, now_ms=now_ms, require_fresh=True)

    def decode_artifact_evidence(
        self, token: object, *, now_ms: int
    ) -> PreparedActionArtifact:
        return self._decode_artifact(token, now_ms=now_ms, require_fresh=False)

    def _decode_artifact(
        self, token: object, *, now_ms: int, require_fresh: bool
    ) -> PreparedActionArtifact:
        try:
            if (
                type(token) is not str
                or not token
                or len(token.encode("utf-8")) > MAX_ACTION_REF_BYTES
            ):
                raise ActionContractError("invalid artifact reference")
            parts = token.split(".")
            if len(parts) != 2:
                raise ActionContractError("invalid artifact reference")
            payload = _b64decode(parts[0])
            supplied = _b64decode(parts[1])
            expected = self._mac(payload, purpose=ARTIFACT_HMAC_PURPOSE)
            if len(supplied) != len(expected) or not hmac.compare_digest(
                supplied, expected
            ):
                raise ActionContractError("invalid artifact reference")

            def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
                selected: dict[str, Any] = {}
                for key, item in items:
                    if key in selected:
                        raise ActionContractError("invalid artifact reference")
                    selected[key] = item
                return selected

            def constant(_value: str) -> None:
                raise ActionContractError("invalid artifact reference")

            raw: Any = json.loads(
                payload.decode("utf-8"),
                object_pairs_hook=pairs,
                parse_constant=constant,
            )
            names = {field.name for field in dataclasses.fields(PreparedActionArtifact)}
            if type(raw) is not dict or set(raw) != names:
                raise ActionContractError("invalid artifact reference")
            value = PreparedActionArtifact(**raw)
            return validate_prepared_artifact(
                value, now_ms=now_ms, require_fresh=require_fresh
            )
        except ActionContractError:
            raise
        except Exception as error:
            raise ActionContractError("invalid artifact reference") from error


    def encode_command(self, value: PreparedClosedCommand) -> str:
        validate_prepared_command(
            value, now_ms=value.issued_at_ms, require_fresh=True
        )
        payload = json.dumps(
            dataclasses.asdict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        if len(payload) > MAX_ACTION_REF_BYTES // 2:
            raise ActionContractError("prepared command is too large")
        signature = self._mac(payload, purpose=COMMAND_HMAC_PURPOSE)
        token = f"{_b64encode(payload)}.{_b64encode(signature)}"
        if len(token.encode("ascii")) > MAX_ACTION_REF_BYTES:
            raise ActionContractError("prepared command is too large")
        return token

    def decode_command(
        self, token: object, *, now_ms: int
    ) -> PreparedClosedCommand:
        return self._decode_command(token, now_ms=now_ms, require_fresh=True)

    def decode_command_evidence(
        self, token: object, *, now_ms: int
    ) -> PreparedClosedCommand:
        """Integrity-only command decode; a current grant still gates evidence."""

        return self._decode_command(token, now_ms=now_ms, require_fresh=False)

    def _decode_command(
        self, token: object, *, now_ms: int, require_fresh: bool
    ) -> PreparedClosedCommand:
        try:
            if (
                type(token) is not str
                or not token
                or len(token.encode("utf-8")) > MAX_ACTION_REF_BYTES
            ):
                raise ActionContractError("invalid command reference")
            parts = token.split(".")
            if len(parts) != 2:
                raise ActionContractError("invalid command reference")
            payload = _b64decode(parts[0])
            supplied = _b64decode(parts[1])
            expected = self._mac(payload, purpose=COMMAND_HMAC_PURPOSE)
            if len(supplied) != len(expected) or not hmac.compare_digest(
                supplied, expected
            ):
                raise ActionContractError("invalid command reference")

            def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
                selected: dict[str, Any] = {}
                for key, item in items:
                    if key in selected:
                        raise ActionContractError("invalid command reference")
                    selected[key] = item
                return selected

            def constant(_value: str) -> None:
                raise ActionContractError("invalid command reference")

            raw: Any = json.loads(
                payload.decode("utf-8"),
                object_pairs_hook=pairs,
                parse_constant=constant,
            )
            names = {field.name for field in dataclasses.fields(PreparedClosedCommand)}
            if type(raw) is not dict or set(raw) != names:
                raise ActionContractError("invalid command reference")
            value = PreparedClosedCommand(**raw)
            return validate_prepared_command(
                value, now_ms=now_ms, require_fresh=require_fresh
            )
        except ActionContractError:
            raise
        except Exception as error:
            raise ActionContractError("invalid command reference") from error


__all__ = [
    "ACTION_TOKEN_PURPOSE",
    "ACTION_TOKEN_SCHEMA",
    "ACTION_TOKEN_SCHEMA_V1",
    "MAX_ACTION_REF_BYTES",
    "MAX_ACTION_TTL_MS",
    "MAX_PATCH_TEXT_BYTES",
    "ActionCaller",
    "ActionContractError",
    "ActionScope",
    "ActionTokenCodec",
    "PreparedTextPatch",
    "ProjectActionBinding",
    "validate_action_caller",
    "validate_action_scope",
    "validate_prepared",
    "validate_relative_path",
]
