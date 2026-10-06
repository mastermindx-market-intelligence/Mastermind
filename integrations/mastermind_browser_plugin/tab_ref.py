"""Stateless signed tab references shared by Browser backends.

A tab reference is a projection of authority already held by the Browser owner.
It does not create a tab registry, grant, lease, browser session, retry record,
placement decision, or authentication plane. The caller must still revalidate
the underlying browser resource and backend generation immediately before use.
"""
from __future__ import annotations

import base64
import dataclasses
import enum
import hashlib
import hmac
import json
import re
from typing import Any

TAB_REF_SCHEMA = "mastermind.browser_tab_ref.v1"
TAB_REF_VERSION = "v1"
MAX_TAB_REF_BYTES = 16 * 1024
MAX_TAB_REF_LIFETIME_MS = 5 * 60 * 1000
HIGH_LEVEL_ACTIONS = frozenset(
    {"snapshot", "screenshot", "click", "type", "scroll", "navigate"}
)

_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_BROWSER_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~:-]{15,16383}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_PURPOSE = b"mastermind.browser-tab-ref.v1\0"


class BrowserTabRefError(ValueError):
    """Closed tab-reference refusal containing no caller-supplied secret."""


def _refuse(code: str) -> None:
    raise BrowserTabRefError(code)


class TabBackend(str, enum.Enum):
    MANAGED = "managed"
    SHARED_HUMAN = "shared_human"


def _token(value: object) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        _refuse("REFERENCE_INVALID")
    return value


def _hex64(value: object, code: str) -> str:
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        _refuse(code)
    return value


def _integer(value: object, code: str) -> int:
    if type(value) is not int or value < 0 or value >= 2**63:
        _refuse(code)
    return value


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: object) -> bytes:
    if type(value) is not str or not value:
        _refuse("TAB_REF_INVALID")
    try:
        padding = "=" * (-len(value) % 4)
        return base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, UnicodeError):
        _refuse("TAB_REF_INVALID")


def _strict_pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            _refuse("TAB_REF_INVALID")
        result[key] = value
    return result


@dataclasses.dataclass(frozen=True)
class BrowserTabRef:
    schema: str
    backend: str
    browser_ref: str
    subject_digest: str
    client_ref: str
    resource: str
    host_ref: str
    boot_ref: str
    profile_ref: str
    browser_instance_ref: str
    connection_generation: str
    tab_locator: int
    document_revision: int
    consent_ref: str | None
    allowed_actions: tuple[str, ...]
    catalog_schema_digest: str
    backend_schema_digest: str
    issued_at_ms: int
    expires_at_ms: int

    def __post_init__(self) -> None:
        if self.schema != TAB_REF_SCHEMA:
            _refuse("SCHEMA_INVALID")
        if self.backend not in {item.value for item in TabBackend}:
            _refuse("BACKEND_INVALID")
        if (
            type(self.browser_ref) is not str
            or _BROWSER_REF.fullmatch(self.browser_ref) is None
            or len(self.browser_ref.encode("utf-8")) > MAX_TAB_REF_BYTES
        ):
            _refuse("BROWSER_REF_INVALID")
        _hex64(self.subject_digest, "SUBJECT_INVALID")
        for value in (
            self.client_ref,
            self.resource,
            self.host_ref,
            self.boot_ref,
            self.profile_ref,
            self.browser_instance_ref,
            self.connection_generation,
        ):
            _token(value)
        _integer(self.tab_locator, "TAB_LOCATOR_INVALID")
        _integer(self.document_revision, "DOCUMENT_REVISION_INVALID")
        if self.backend == TabBackend.SHARED_HUMAN.value:
            if self.consent_ref is None:
                _refuse("CONSENT_REQUIRED")
            _token(self.consent_ref)
        elif self.consent_ref is not None:
            _refuse("CONSENT_NOT_ALLOWED")
        if (
            type(self.allowed_actions) is not tuple
            or not self.allowed_actions
            or tuple(sorted(self.allowed_actions)) != self.allowed_actions
            or len(set(self.allowed_actions)) != len(self.allowed_actions)
            or any(
                type(action) is not str or action not in HIGH_LEVEL_ACTIONS
                for action in self.allowed_actions
            )
        ):
            _refuse("ACTIONS_INVALID")
        _hex64(self.catalog_schema_digest, "CATALOG_SCHEMA_DIGEST_INVALID")
        _hex64(self.backend_schema_digest, "BACKEND_SCHEMA_DIGEST_INVALID")
        issued = _integer(self.issued_at_ms, "TIME_WINDOW_INVALID")
        expires = _integer(self.expires_at_ms, "TIME_WINDOW_INVALID")
        if (
            expires <= issued
            or expires - issued > MAX_TAB_REF_LIFETIME_MS
        ):
            _refuse("TIME_WINDOW_INVALID")


class BrowserTabRefCodec:
    """HMAC codec over canonical JSON. Holds only a signing key, never tab state."""

    __slots__ = ("_key",)

    def __init__(self, key: bytes) -> None:
        if type(key) is not bytes or len(key) < 32:
            raise BrowserTabRefError("SIGNING_KEY_INVALID")
        self._key = bytes(key)

    @staticmethod
    def _dict(value: BrowserTabRef) -> dict[str, object]:
        if type(value) is not BrowserTabRef:
            _refuse("TAB_REF_INVALID")
        value.__post_init__()
        return {
            "schema": value.schema,
            "backend": value.backend,
            "browser_ref": value.browser_ref,
            "subject_digest": value.subject_digest,
            "client_ref": value.client_ref,
            "resource": value.resource,
            "host_ref": value.host_ref,
            "boot_ref": value.boot_ref,
            "profile_ref": value.profile_ref,
            "browser_instance_ref": value.browser_instance_ref,
            "connection_generation": value.connection_generation,
            "tab_locator": value.tab_locator,
            "document_revision": value.document_revision,
            "consent_ref": value.consent_ref,
            "allowed_actions": list(value.allowed_actions),
            "catalog_schema_digest": value.catalog_schema_digest,
            "backend_schema_digest": value.backend_schema_digest,
            "issued_at_ms": value.issued_at_ms,
            "expires_at_ms": value.expires_at_ms,
        }

    def _payload(self, value: BrowserTabRef) -> bytes:
        try:
            raw = json.dumps(
                self._dict(value),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError):
            _refuse("TAB_REF_INVALID")
        if not raw or len(raw) > MAX_TAB_REF_BYTES:
            _refuse("TAB_REF_INVALID")
        return raw

    def encode(self, value: BrowserTabRef) -> str:
        payload = self._payload(value)
        signature = hmac.new(self._key, _PURPOSE + payload, hashlib.sha256).digest()
        return f"{TAB_REF_VERSION}.{_b64encode(payload)}.{_b64encode(signature)}"

    def decode(
        self,
        token: object,
        *,
        now_ms: int,
    ) -> BrowserTabRef:
        _integer(now_ms, "TIME_WINDOW_INVALID")
        if type(token) is not str or len(token.encode("utf-8")) > MAX_TAB_REF_BYTES * 2:
            _refuse("TAB_REF_INVALID")
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != TAB_REF_VERSION:
            _refuse("TAB_REF_INVALID")
        payload = _b64decode(parts[1])
        signature = _b64decode(parts[2])
        if len(payload) > MAX_TAB_REF_BYTES or len(signature) != hashlib.sha256().digest_size:
            _refuse("TAB_REF_INVALID")
        expected = hmac.new(self._key, _PURPOSE + payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            _refuse("TAB_REF_SIGNATURE_INVALID")
        try:
            raw = json.loads(
                payload.decode("utf-8"),
                object_pairs_hook=_strict_pairs,
                parse_constant=lambda _value: _refuse("TAB_REF_INVALID"),
            )
        except BrowserTabRefError:
            raise
        except (UnicodeDecodeError, ValueError, TypeError, RecursionError):
            _refuse("TAB_REF_INVALID")
        if type(raw) is not dict:
            _refuse("TAB_REF_INVALID")
        expected_fields = {field.name for field in dataclasses.fields(BrowserTabRef)}
        if set(raw) != expected_fields:
            _refuse("TAB_REF_INVALID")
        if type(raw.get("allowed_actions")) is not list:
            _refuse("TAB_REF_INVALID")
        try:
            value = BrowserTabRef(
                **{
                    **raw,
                    "allowed_actions": tuple(raw["allowed_actions"]),
                }
            )
        except TypeError:
            _refuse("TAB_REF_INVALID")
        if now_ms < value.issued_at_ms:
            _refuse("TIME_WINDOW_INVALID")
        if now_ms >= value.expires_at_ms:
            _refuse("TAB_REF_EXPIRED")
        return value

    def decode_for_call(
        self,
        token: object,
        *,
        now_ms: int,
        subject_digest: object,
        client_ref: object,
        resource: object,
        action: object,
    ) -> BrowserTabRef:
        value = self.decode(token, now_ms=now_ms)
        if (
            type(subject_digest) is not str
            or type(client_ref) is not str
            or type(resource) is not str
            or subject_digest != value.subject_digest
            or client_ref != value.client_ref
            or resource != value.resource
        ):
            _refuse("CALLER_BINDING_CHANGED")
        if type(action) is not str or action not in HIGH_LEVEL_ACTIONS:
            _refuse("ACTION_NOT_GRANTED")
        if action not in value.allowed_actions:
            _refuse("ACTION_NOT_GRANTED")
        return value


__all__ = [
    "HIGH_LEVEL_ACTIONS",
    "MAX_TAB_REF_BYTES",
    "MAX_TAB_REF_LIFETIME_MS",
    "TAB_REF_SCHEMA",
    "BrowserTabRef",
    "BrowserTabRefCodec",
    "BrowserTabRefError",
    "TabBackend",
]
