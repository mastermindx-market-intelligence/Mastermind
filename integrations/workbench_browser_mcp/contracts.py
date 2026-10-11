"""Signed browser references bound to existing Workbench owner context."""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from control_plane.browser_resource_contract import ALLOWED_BROWSER_TOOLS, BrowserMode


START_SCHEMA = "mastermind.workbench_browser_start.v1"
RESOURCE_SCHEMA = "mastermind.workbench_browser_ref.v1"
ACTION_SCHEMA = "mastermind.workbench_browser_action.v1"

_MAX_TOKEN_BYTES = 16 * 1024
_MAX_ARGUMENT_BYTES = 64 * 1024
_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,255}$")
_BOOT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")

_START_PURPOSE = b"mastermind.workbench-browser.start.v1"
_RESOURCE_PURPOSE = b"mastermind.workbench-browser.resource.v1"
_ACTION_PURPOSE = b"mastermind.workbench-browser.action.v1"


class BrowserContractError(ValueError):
    """A browser capability reference is malformed, stale, or unauthentic."""


@dataclass(frozen=True)
class PreparedBrowserStart:
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
    store_device: int
    store_inode: int
    host_id: str
    boot_session_id: str
    mode: str
    profile_ref: str | None
    issued_at_ms: int
    expires_at_ms: int
    resource_expires_at_ms: int


@dataclass(frozen=True)
class BrowserResourceRef:
    schema: str
    start_action_id: str
    subject_digest: str
    client_ref: str
    resource: str
    project_ref: str
    context_ref: str
    responsibility_ref: str
    operation_ref: str
    owner_ref: str
    generation: str
    host_id: str
    boot_session_id: str
    relay_pid: int
    relay_start_identity: str
    relay_pgid: int
    relay_session_id: int
    mode: str
    profile_ref: str | None
    tool_schema_digest: str
    issued_at_ms: int
    expires_at_ms: int


@dataclass(frozen=True)
class PreparedBrowserAction:
    schema: str
    action_id: str
    browser_ref_sha256: str
    subject_digest: str
    client_ref: str
    resource: str
    project_ref: str
    context_ref: str
    responsibility_ref: str
    operation_ref: str
    owner_ref: str
    generation: str
    host_id: str
    boot_session_id: str
    tool_name: str
    arguments_json: str
    issued_at_ms: int
    expires_at_ms: int


def _ref(value: object, name: str) -> str:
    if type(value) is not str or _REF.fullmatch(value) is None:
        raise BrowserContractError(f"{name} is invalid")
    return value


def _text(value: object, name: str, *, maximum: int) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > maximum:
        raise BrowserContractError(f"{name} is invalid")
    return value


def _hex(value: object, pattern: re.Pattern[str], name: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise BrowserContractError(f"{name} is invalid")
    return value


def _time_window(issued: object, expires: object, *, now_ms: int, require_fresh: bool) -> None:
    if (
        type(issued) is not int
        or type(expires) is not int
        or type(now_ms) is not int
        or issued < 0
        or expires <= issued
        or now_ms < 0
        or now_ms < issued
    ):
        raise BrowserContractError("browser reference time window is invalid")
    if require_fresh and now_ms >= expires:
        raise BrowserContractError("browser reference expired")


def _mode_profile(mode: object, profile_ref: object) -> tuple[str, str | None]:
    if mode not in {BrowserMode.ISOLATED.value, BrowserMode.PERSISTENT.value}:
        raise BrowserContractError("browser mode is invalid")
    if mode == BrowserMode.ISOLATED.value:
        if profile_ref is not None:
            raise BrowserContractError("isolated browser cannot carry a persistent profile")
        return mode, None
    if profile_ref is None:
        raise BrowserContractError("persistent browser requires a profile reference")
    return mode, _ref(profile_ref, "profile_ref")


def _common(
    *,
    schema: object,
    expected_schema: str,
    subject_digest: object,
    client_ref: object,
    resource: object,
    project_ref: object,
    context_ref: object,
    responsibility_ref: object,
    operation_ref: object,
    owner_ref: object,
    generation: object,
    host_id: object,
    boot_session_id: object,
    issued_at_ms: object,
    expires_at_ms: object,
    now_ms: int,
    require_fresh: bool,
) -> None:
    if schema != expected_schema:
        raise BrowserContractError("browser reference schema is invalid")
    _hex(subject_digest, _HEX64, "subject_digest")
    _text(client_ref, "client_ref", maximum=256)
    _text(resource, "resource", maximum=2048)
    for name, value in (
        ("project_ref", project_ref),
        ("context_ref", context_ref),
        ("responsibility_ref", responsibility_ref),
        ("operation_ref", operation_ref),
        ("owner_ref", owner_ref),
        ("generation", generation),
    ):
        _ref(value, name)
    _hex(host_id, _HEX64, "host_id")
    if type(boot_session_id) is not str or _BOOT.fullmatch(boot_session_id) is None:
        raise BrowserContractError("boot_session_id is invalid")
    _time_window(
        issued_at_ms,
        expires_at_ms,
        now_ms=now_ms,
        require_fresh=require_fresh,
    )


def validate_prepared_browser_start(
    value: object, *, now_ms: int, require_fresh: bool = True
) -> PreparedBrowserStart:
    if type(value) is not PreparedBrowserStart:
        raise BrowserContractError("invalid browser start reference")
    _common(
        schema=value.schema,
        expected_schema=START_SCHEMA,
        subject_digest=value.subject_digest,
        client_ref=value.client_ref,
        resource=value.resource,
        project_ref=value.project_ref,
        context_ref=value.context_ref,
        responsibility_ref=value.responsibility_ref,
        operation_ref=value.operation_ref,
        owner_ref=value.owner_ref,
        generation=value.generation,
        host_id=value.host_id,
        boot_session_id=value.boot_session_id,
        issued_at_ms=value.issued_at_ms,
        expires_at_ms=value.expires_at_ms,
        now_ms=now_ms,
        require_fresh=require_fresh,
    )
    _hex(value.action_id, _HEX32, "action_id")
    for name in ("root_device", "root_inode", "store_device", "store_inode"):
        selected = getattr(value, name)
        if type(selected) is not int or selected < 0:
            raise BrowserContractError(f"{name} is invalid")
    _mode_profile(value.mode, value.profile_ref)
    _time_window(
        value.issued_at_ms,
        value.resource_expires_at_ms,
        now_ms=now_ms,
        require_fresh=False,
    )
    if value.resource_expires_at_ms < value.expires_at_ms:
        raise BrowserContractError("browser resource lifetime is shorter than start token")
    return value


def validate_browser_resource_ref(
    value: object, *, now_ms: int, require_fresh: bool = True
) -> BrowserResourceRef:
    if type(value) is not BrowserResourceRef:
        raise BrowserContractError("invalid browser resource reference")
    _common(
        schema=value.schema,
        expected_schema=RESOURCE_SCHEMA,
        subject_digest=value.subject_digest,
        client_ref=value.client_ref,
        resource=value.resource,
        project_ref=value.project_ref,
        context_ref=value.context_ref,
        responsibility_ref=value.responsibility_ref,
        operation_ref=value.operation_ref,
        owner_ref=value.owner_ref,
        generation=value.generation,
        host_id=value.host_id,
        boot_session_id=value.boot_session_id,
        issued_at_ms=value.issued_at_ms,
        expires_at_ms=value.expires_at_ms,
        now_ms=now_ms,
        require_fresh=require_fresh,
    )
    _hex(value.start_action_id, _HEX32, "start_action_id")
    for name in ("relay_pid", "relay_pgid", "relay_session_id"):
        selected = getattr(value, name)
        if type(selected) is not int or selected <= 0:
            raise BrowserContractError(f"{name} is invalid")
    _text(value.relay_start_identity, "relay_start_identity", maximum=160)
    _mode_profile(value.mode, value.profile_ref)
    _hex(value.tool_schema_digest, _HEX64, "tool_schema_digest")
    return value


def canonical_browser_arguments(value: object) -> str:
    if type(value) is not dict:
        raise BrowserContractError("browser arguments must be an object")
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise BrowserContractError("browser arguments are not JSON-safe") from error
    if len(encoded.encode("utf-8")) > _MAX_ARGUMENT_BYTES:
        raise BrowserContractError("browser arguments are too large")
    return encoded


def validate_prepared_browser_action(
    value: object, *, now_ms: int, require_fresh: bool = True
) -> PreparedBrowserAction:
    if type(value) is not PreparedBrowserAction:
        raise BrowserContractError("invalid browser action reference")
    _common(
        schema=value.schema,
        expected_schema=ACTION_SCHEMA,
        subject_digest=value.subject_digest,
        client_ref=value.client_ref,
        resource=value.resource,
        project_ref=value.project_ref,
        context_ref=value.context_ref,
        responsibility_ref=value.responsibility_ref,
        operation_ref=value.operation_ref,
        owner_ref=value.owner_ref,
        generation=value.generation,
        host_id=value.host_id,
        boot_session_id=value.boot_session_id,
        issued_at_ms=value.issued_at_ms,
        expires_at_ms=value.expires_at_ms,
        now_ms=now_ms,
        require_fresh=require_fresh,
    )
    _hex(value.action_id, _HEX32, "action_id")
    _hex(value.browser_ref_sha256, _HEX64, "browser_ref_sha256")
    if value.tool_name not in ALLOWED_BROWSER_TOOLS:
        raise BrowserContractError("browser tool is not granted")
    try:
        parsed = json.loads(value.arguments_json)
    except (TypeError, json.JSONDecodeError) as error:
        raise BrowserContractError("browser arguments are invalid") from error
    if canonical_browser_arguments(parsed) != value.arguments_json:
        raise BrowserContractError("browser arguments are not canonical")
    return value


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    try:
        encoded = value.encode("ascii")
        padding = b"=" * (-len(encoded) % 4)
        decoded = base64.urlsafe_b64decode(encoded + padding)
        if _b64encode(decoded) != value:
            raise BrowserContractError("invalid browser reference")
        return decoded
    except BrowserContractError:
        raise
    except Exception as error:
        raise BrowserContractError("invalid browser reference") from error


def _strict_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise BrowserContractError("duplicate browser reference field")
            result[key] = value
        return result

    def constant(_value: str) -> None:
        raise BrowserContractError("invalid browser reference number")

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except BrowserContractError:
        raise
    except Exception as error:
        raise BrowserContractError("invalid browser reference") from error


class BrowserRefCodec:
    """Domain-separated HMAC references using an owner-provisioned Workbench key."""

    def __init__(self, key: bytes) -> None:
        if type(key) is not bytes or len(key) < 32:
            raise ValueError("browser reference key must contain at least 32 bytes")
        self._key = bytes(key)

    def _encode(
        self,
        value: object,
        *,
        purpose: bytes,
        validate: Callable[..., object],
    ) -> str:
        issued_at = getattr(value, "issued_at_ms", None)
        validate(value, now_ms=issued_at, require_fresh=True)
        payload = json.dumps(
            dataclasses.asdict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        if len(payload) > _MAX_TOKEN_BYTES // 2:
            raise BrowserContractError("browser reference is too large")
        signature = hmac.new(self._key, purpose + b"\x00" + payload, hashlib.sha256).digest()
        token = f"{_b64encode(payload)}.{_b64encode(signature)}"
        if len(token.encode("ascii")) > _MAX_TOKEN_BYTES:
            raise BrowserContractError("browser reference is too large")
        return token

    def _decode(
        self,
        token: object,
        *,
        purpose: bytes,
        cls: type,
        validate: Callable[..., object],
        now_ms: int,
        require_fresh: bool = True,
    ):
        if type(token) is not str or not token or len(token.encode("utf-8")) > _MAX_TOKEN_BYTES:
            raise BrowserContractError("invalid browser reference")
        parts = token.split(".")
        if len(parts) != 2:
            raise BrowserContractError("invalid browser reference")
        payload = _b64decode(parts[0])
        supplied = _b64decode(parts[1])
        expected = hmac.new(self._key, purpose + b"\x00" + payload, hashlib.sha256).digest()
        if len(supplied) != len(expected) or not hmac.compare_digest(supplied, expected):
            raise BrowserContractError("invalid browser reference")
        raw = _strict_json(payload)
        names = {field.name for field in dataclasses.fields(cls)}
        if type(raw) is not dict or set(raw) != names:
            raise BrowserContractError("invalid browser reference")
        try:
            value = cls(**raw)
        except Exception as error:
            raise BrowserContractError("invalid browser reference") from error
        return validate(value, now_ms=now_ms, require_fresh=require_fresh)

    def encode_start(self, value: PreparedBrowserStart) -> str:
        return self._encode(value, purpose=_START_PURPOSE, validate=validate_prepared_browser_start)

    def decode_start(
        self, token: object, *, now_ms: int, require_fresh: bool = True
    ) -> PreparedBrowserStart:
        return self._decode(
            token,
            purpose=_START_PURPOSE,
            cls=PreparedBrowserStart,
            validate=validate_prepared_browser_start,
            now_ms=now_ms,
            require_fresh=require_fresh,
        )

    def encode_resource(self, value: BrowserResourceRef) -> str:
        return self._encode(value, purpose=_RESOURCE_PURPOSE, validate=validate_browser_resource_ref)

    def decode_resource(
        self, token: object, *, now_ms: int, require_fresh: bool = True
    ) -> BrowserResourceRef:
        return self._decode(
            token,
            purpose=_RESOURCE_PURPOSE,
            cls=BrowserResourceRef,
            validate=validate_browser_resource_ref,
            now_ms=now_ms,
            require_fresh=require_fresh,
        )

    def encode_action(self, value: PreparedBrowserAction) -> str:
        return self._encode(value, purpose=_ACTION_PURPOSE, validate=validate_prepared_browser_action)

    def decode_action(
        self, token: object, *, now_ms: int, require_fresh: bool = True
    ) -> PreparedBrowserAction:
        return self._decode(
            token,
            purpose=_ACTION_PURPOSE,
            cls=PreparedBrowserAction,
            validate=validate_prepared_browser_action,
            now_ms=now_ms,
            require_fresh=require_fresh,
        )


__all__ = [
    "ACTION_SCHEMA",
    "RESOURCE_SCHEMA",
    "START_SCHEMA",
    "BrowserContractError",
    "BrowserRefCodec",
    "BrowserResourceRef",
    "PreparedBrowserAction",
    "PreparedBrowserStart",
    "canonical_browser_arguments",
    "validate_browser_resource_ref",
    "validate_prepared_browser_action",
    "validate_prepared_browser_start",
]
