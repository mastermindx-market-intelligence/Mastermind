"""Fresh, stateless Browser inventory projection over existing owner facts.

This module never owns browser lifecycle, placement, ranking, admission, effects,
leases, retries, processes, or a browser registry. It re-reads already-owned
resource/tab facts and mints short-lived caller-bound session/tab references.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import inspect
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .catalog import SCHEMA_DIGEST
from .facade import OwnerRefused
from .owner_adapter import BrowserCallerBinding
from .tab_ref import (
    BROWSER_SESSION_SCHEMA,
    HIGH_LEVEL_ACTIONS,
    MAX_TAB_REF_LIFETIME_MS,
    TAB_REF_SCHEMA,
    BrowserSessionRef,
    BrowserTabRef,
    BrowserTabRefCodec,
    BrowserTabRefError,
    TabBackend,
)

_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_BROWSER_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~:-]{15,16383}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MAX_TITLE = 512
_MAX_URL = 2048


def _token(value: object, field: str) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        raise ValueError(f"{field} is invalid")
    return value


def _browser_ref(value: object) -> str:
    if (
        type(value) is not str
        or _BROWSER_REF.fullmatch(value) is None
        or len(value.encode("utf-8")) > 16 * 1024
    ):
        raise ValueError("browser_ref is invalid")
    return value


def _integer(value: object, field: str) -> int:
    if type(value) is not int or value < 0 or value >= 2**63:
        raise ValueError(f"{field} is invalid")
    return value


def _actions(value: object) -> tuple[str, ...]:
    if (
        type(value) is not tuple
        or not value
        or value != tuple(sorted(value))
        or len(set(value)) != len(value)
        or any(type(item) is not str or item not in HIGH_LEVEL_ACTIONS for item in value)
    ):
        raise ValueError("allowed_actions is invalid")
    return value


def _digest(value: object, field: str) -> str:
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise ValueError(f"{field} is invalid")
    return value


def _http_url(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > _MAX_URL
        or any(ord(ch) < 32 for ch in value)
    ):
        raise ValueError("url is invalid")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError("url is invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("url is invalid")
    return value


def _safe_title(value: object) -> str:
    if (
        type(value) is not str
        or len(value) > _MAX_TITLE
        or any(ord(ch) < 32 for ch in value)
    ):
        raise ValueError("title is invalid")
    return value


@dataclass(frozen=True, slots=True)
class ActiveBrowserResource:
    """One already-live resource observation from the incumbent Browser owner."""

    backend: str
    browser_ref: str
    host_ref: str
    boot_ref: str
    profile_ref: str
    browser_instance_ref: str
    connection_generation: str
    consent_ref: str | None
    allowed_actions: tuple[str, ...]
    catalog_schema_digest: str
    backend_schema_digest: str
    expires_at_ms: int

    def __post_init__(self) -> None:
        if self.backend not in {item.value for item in TabBackend}:
            raise ValueError("backend is invalid")
        _browser_ref(self.browser_ref)
        for field in (
            "host_ref",
            "boot_ref",
            "profile_ref",
            "browser_instance_ref",
            "connection_generation",
        ):
            _token(getattr(self, field), field)
        if self.backend == TabBackend.SHARED_HUMAN.value:
            if self.consent_ref is None:
                raise ValueError("consent_ref is required")
            _token(self.consent_ref, "consent_ref")
        elif self.consent_ref is not None:
            raise ValueError("consent_ref is not allowed")
        _actions(self.allowed_actions)
        _digest(self.catalog_schema_digest, "catalog_schema_digest")
        _digest(self.backend_schema_digest, "backend_schema_digest")
        _integer(self.expires_at_ms, "expires_at_ms")


@dataclass(frozen=True, slots=True)
class BrowserTabObservation:
    """One current exact tab/document observation from the resource owner."""

    browser_ref: str
    tab_locator: int
    document_revision: int
    title: str
    url: str
    observed_at_ms: int
    expires_at_ms: int

    def __post_init__(self) -> None:
        _browser_ref(self.browser_ref)
        _integer(self.tab_locator, "tab_locator")
        _integer(self.document_revision, "document_revision")
        _safe_title(self.title)
        _http_url(self.url)
        observed = _integer(self.observed_at_ms, "observed_at_ms")
        expires = _integer(self.expires_at_ms, "expires_at_ms")
        if expires <= observed:
            raise ValueError("tab observation validity window is invalid")


async def _maybe(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class BrowserInventoryOwner:
    """Caller-bound projection of live owner resources and one exact tab each."""

    def __init__(
        self,
        *,
        codec: BrowserTabRefCodec,
        clock_ms: Callable[[], int],
        caller_binding: Callable[[Any], BrowserCallerBinding],
        resource_reader: Callable[[Any, int], Any],
        tab_reader: Callable[[Any, ActiveBrowserResource], Any],
        expected_catalog_schema_digest: str = SCHEMA_DIGEST,
    ) -> None:
        if type(codec) is not BrowserTabRefCodec:
            raise TypeError("signed Browser ref codec is required")
        if not all(
            callable(value)
            for value in (clock_ms, caller_binding, resource_reader, tab_reader)
        ):
            raise TypeError("existing Browser owner readers are required")
        if (
            type(expected_catalog_schema_digest) is not str
            or _HEX64.fullmatch(expected_catalog_schema_digest) is None
        ):
            raise TypeError("catalog schema digest is invalid")
        self._codec = codec
        self._clock_ms = clock_ms
        self._caller_binding = caller_binding
        self._resource_reader = resource_reader
        self._tab_reader = tab_reader
        self._catalog_digest = expected_catalog_schema_digest

    def _now(self) -> int:
        value = self._clock_ms()
        if type(value) is not int or value < 0 or value >= 2**63:
            raise OwnerRefused("CLOCK_UNAVAILABLE")
        return value

    async def _caller(self, caller: Any) -> BrowserCallerBinding:
        try:
            value = await _maybe(self._caller_binding(caller))
        except OwnerRefused:
            raise
        except Exception as exc:
            raise OwnerRefused("CALLER_BINDING_CHANGED") from exc
        if type(value) is not BrowserCallerBinding:
            raise OwnerRefused("CALLER_BINDING_CHANGED")
        return value

    async def _resources(
        self,
        caller: Any,
        *,
        limit: int,
        now_ms: int,
    ) -> tuple[ActiveBrowserResource, ...]:
        try:
            raw = await _maybe(self._resource_reader(caller, limit))
        except OwnerRefused:
            raise
        except Exception as exc:
            raise OwnerRefused("INVENTORY_UNAVAILABLE") from exc
        if (
            isinstance(raw, (str, bytes, bytearray))
            or not isinstance(raw, Sequence)
            or len(raw) > limit
        ):
            raise OwnerRefused("INVENTORY_INVALID")
        rows: list[ActiveBrowserResource] = []
        seen: set[str] = set()
        for item in raw:
            if type(item) is not ActiveBrowserResource:
                raise OwnerRefused("INVENTORY_INVALID")
            try:
                item.__post_init__()
            except ValueError as exc:
                raise OwnerRefused("INVENTORY_INVALID") from exc
            if item.browser_ref in seen:
                raise OwnerRefused("INVENTORY_DUPLICATE")
            seen.add(item.browser_ref)
            if item.expires_at_ms <= now_ms:
                continue
            if item.catalog_schema_digest != self._catalog_digest:
                continue
            rows.append(item)
        return tuple(rows)

    @staticmethod
    def _same_resource(
        resource: ActiveBrowserResource,
        session: BrowserSessionRef | BrowserTabRef,
    ) -> bool:
        return (
            resource.backend == session.backend
            and resource.browser_ref == session.browser_ref
            and resource.host_ref == session.host_ref
            and resource.boot_ref == session.boot_ref
            and resource.profile_ref == session.profile_ref
            and resource.browser_instance_ref == session.browser_instance_ref
            and resource.connection_generation == session.connection_generation
            and resource.consent_ref == session.consent_ref
            and resource.allowed_actions == session.allowed_actions
            and resource.catalog_schema_digest == session.catalog_schema_digest
            and resource.backend_schema_digest == session.backend_schema_digest
        )

    async def _current_resource(
        self,
        caller: Any,
        session: BrowserSessionRef | BrowserTabRef,
        *,
        now_ms: int,
    ) -> ActiveBrowserResource:
        rows = await self._resources(caller, limit=50, now_ms=now_ms)
        matches = [row for row in rows if row.browser_ref == session.browser_ref]
        if len(matches) != 1 or not self._same_resource(matches[0], session):
            raise OwnerRefused("BROWSER_BINDING_CHANGED")
        return matches[0]

    async def _current_tab(
        self,
        caller: Any,
        resource: ActiveBrowserResource,
        *,
        now_ms: int,
    ) -> BrowserTabObservation:
        try:
            raw = await _maybe(self._tab_reader(caller, resource))
        except OwnerRefused:
            raise
        except Exception as exc:
            raise OwnerRefused("TAB_UNAVAILABLE") from exc
        if isinstance(raw, (str, bytes, bytearray)) or not isinstance(raw, Sequence):
            raise OwnerRefused("TAB_UNAVAILABLE")
        if len(raw) == 0:
            raise OwnerRefused("TAB_UNAVAILABLE")
        if len(raw) != 1:
            raise OwnerRefused("TAB_GROUP_NOT_EXCLUSIVE")
        observed = raw[0]
        if type(observed) is not BrowserTabObservation:
            raise OwnerRefused("TAB_UNAVAILABLE")
        try:
            observed.__post_init__()
        except ValueError as exc:
            raise OwnerRefused("TAB_UNAVAILABLE") from exc
        if observed.browser_ref != resource.browser_ref:
            raise OwnerRefused("TAB_BINDING_CHANGED")
        if (
            observed.observed_at_ms > now_ms
            or now_ms >= observed.expires_at_ms
        ):
            raise OwnerRefused("TAB_OBSERVATION_NOT_CURRENT")
        return observed

    @staticmethod
    def _display_url(value: str) -> str:
        parsed = urlsplit(value)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))

    async def browser_fleet(self, caller: Any, args: dict) -> dict:
        if type(args) is not dict or any(key != "limit" for key in args):
            raise OwnerRefused("INVALID_ARGUMENTS")
        limit = args.get("limit", 10)
        if type(limit) is not int or isinstance(limit, bool) or not 1 <= limit <= 50:
            raise OwnerRefused("INVALID_ARGUMENTS")
        binding = await self._caller(caller)
        now = self._now()
        rows = await self._resources(caller, limit=limit, now_ms=now)
        browsers = []
        for resource in rows:
            expires = min(
                resource.expires_at_ms,
                now + MAX_TAB_REF_LIFETIME_MS,
            )
            if expires <= now:
                continue
            session = BrowserSessionRef(
                schema=BROWSER_SESSION_SCHEMA,
                backend=resource.backend,
                browser_ref=resource.browser_ref,
                subject_digest=binding.subject_digest,
                client_ref=binding.client_ref,
                resource=binding.resource,
                host_ref=resource.host_ref,
                boot_ref=resource.boot_ref,
                profile_ref=resource.profile_ref,
                browser_instance_ref=resource.browser_instance_ref,
                connection_generation=resource.connection_generation,
                consent_ref=resource.consent_ref,
                allowed_actions=resource.allowed_actions,
                catalog_schema_digest=resource.catalog_schema_digest,
                backend_schema_digest=resource.backend_schema_digest,
                issued_at_ms=now,
                expires_at_ms=expires,
            )
            browsers.append(
                {
                    "browser_ref": self._codec.encode_session(session),
                    "backend": resource.backend,
                    "host_ref": resource.host_ref,
                    "profile_ref": resource.profile_ref,
                    "allowed_actions": list(resource.allowed_actions),
                    "expires_at_ms": expires,
                }
            )
        return {"browsers": browsers}

    async def browser_tabs(self, caller: Any, args: dict) -> dict:
        if type(args) is not dict or set(args) != {"browser_ref"}:
            raise OwnerRefused("INVALID_ARGUMENTS")
        binding = await self._caller(caller)
        now = self._now()
        try:
            session = self._codec.decode_session(
                args["browser_ref"],
                now_ms=now,
                subject_digest=binding.subject_digest,
                client_ref=binding.client_ref,
                resource=binding.resource,
            )
        except BrowserTabRefError as exc:
            raise OwnerRefused(str(exc)) from exc
        resource = await self._current_resource(caller, session, now_ms=now)
        observed = await self._current_tab(caller, resource, now_ms=now)
        expires = min(
            resource.expires_at_ms,
            observed.expires_at_ms,
            now + MAX_TAB_REF_LIFETIME_MS,
        )
        if expires <= now:
            raise OwnerRefused("TAB_OBSERVATION_NOT_CURRENT")
        signed = BrowserTabRef(
            schema=TAB_REF_SCHEMA,
            backend=resource.backend,
            browser_ref=resource.browser_ref,
            subject_digest=binding.subject_digest,
            client_ref=binding.client_ref,
            resource=binding.resource,
            host_ref=resource.host_ref,
            boot_ref=resource.boot_ref,
            profile_ref=resource.profile_ref,
            browser_instance_ref=resource.browser_instance_ref,
            connection_generation=resource.connection_generation,
            tab_locator=observed.tab_locator,
            document_revision=observed.document_revision,
            consent_ref=resource.consent_ref,
            allowed_actions=resource.allowed_actions,
            catalog_schema_digest=resource.catalog_schema_digest,
            backend_schema_digest=resource.backend_schema_digest,
            issued_at_ms=now,
            expires_at_ms=expires,
        )
        return {
            "tabs": [
                {
                    "tab_ref": self._codec.encode(signed),
                    "title": observed.title,
                    "url": self._display_url(observed.url),
                }
            ]
        }

    async def revalidate_tab(self, caller: Any, tab: BrowserTabRef) -> bool:
        if type(tab) is not BrowserTabRef:
            raise OwnerRefused("TAB_BINDING_CHANGED")
        try:
            tab.__post_init__()
        except BrowserTabRefError as exc:
            raise OwnerRefused(str(exc)) from exc
        binding = await self._caller(caller)
        if (
            tab.subject_digest != binding.subject_digest
            or tab.client_ref != binding.client_ref
            or tab.resource != binding.resource
        ):
            raise OwnerRefused("CALLER_BINDING_CHANGED")
        now = self._now()
        if now < tab.issued_at_ms or now >= tab.expires_at_ms:
            return False
        try:
            resource = await self._current_resource(caller, tab, now_ms=now)
            observed = await self._current_tab(caller, resource, now_ms=now)
        except OwnerRefused as exc:
            if exc.code in {
                "BROWSER_BINDING_CHANGED",
                "TAB_UNAVAILABLE",
                "TAB_GROUP_NOT_EXCLUSIVE",
                "TAB_BINDING_CHANGED",
                "TAB_OBSERVATION_NOT_CURRENT",
            }:
                return False
            raise
        return (
            observed.tab_locator == tab.tab_locator
            and observed.document_revision == tab.document_revision
        )


__all__ = [
    "ActiveBrowserResource",
    "BrowserInventoryOwner",
    "BrowserTabObservation",
]
