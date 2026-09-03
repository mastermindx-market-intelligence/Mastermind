"""Ephemeral W3C runtime primitives owned by the existing Agent Relay process.

The waiter registry and candidate collector are deliberately process-local and
persistence-free. They own no dialogue, Wake, provider, lifecycle, target,
retry, queue, cursor, scheduler, thread pool, or durable authority.
"""
from __future__ import annotations

import asyncio
import inspect
import math
import re
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Generic, TypeVar


_T = TypeVar("_T")
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,255}$")
_WAITER_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,256}$")
_SESSION_REF_RE = re.compile(r"\Aasd-session-[a-z0-9][a-z0-9-]{7,63}\Z")


class TurnRuntimePrimitiveError(RuntimeError):
    """One fixed, payload-free W3C primitive refusal."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ActiveWaiterConflict(TurnRuntimePrimitiveError):
    def __init__(self) -> None:
        super().__init__("ACTIVE_WAITER_CONFLICT")


class CandidateCollectionBusy(TurnRuntimePrimitiveError):
    def __init__(self) -> None:
        super().__init__("CANDIDATE_COLLECTION_INFLIGHT")


class CandidateCollectionUnavailable(TurnRuntimePrimitiveError):
    def __init__(self) -> None:
        super().__init__("CANDIDATE_SOURCE_UNAVAILABLE")


class CandidateCollectionTimeout(TurnRuntimePrimitiveError):
    def __init__(self) -> None:
        super().__init__("CANDIDATE_COLLECTION_TIMEOUT")


class CandidateCollectionOverflow(TurnRuntimePrimitiveError):
    def __init__(self) -> None:
        super().__init__("CANDIDATE_COLLECTION_OVERFLOW")


def _token(value: Any, *, code: str) -> str:
    if not isinstance(value, str) or _TOKEN_RE.fullmatch(value) is None:
        raise TurnRuntimePrimitiveError(code)
    return value


@dataclass(frozen=True, slots=True)
class ActiveWaiterKey:
    """Exact non-authoritative identity of one active Relay wait call."""

    parent_fingerprint: str
    operation_key: str
    session_ref_canonical: str
    target_seat: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.parent_fingerprint, str)
            or _FINGERPRINT_RE.fullmatch(self.parent_fingerprint) is None
        ):
            raise TurnRuntimePrimitiveError("WAITER_KEY_INVALID")
        _token(self.operation_key, code="WAITER_KEY_INVALID")
        _token(self.target_seat, code="WAITER_KEY_INVALID")
        if (
            not isinstance(self.session_ref_canonical, str)
            or _SESSION_REF_RE.fullmatch(self.session_ref_canonical) is None
        ):
            raise TurnRuntimePrimitiveError("WAITER_KEY_INVALID")

    @classmethod
    def from_parent(
        cls,
        parent: Mapping[str, Any],
        *,
        target_seat: str,
    ) -> "ActiveWaiterKey":
        if not isinstance(parent, Mapping):
            raise TurnRuntimePrimitiveError("WAITER_KEY_INVALID")
        return cls(
            parent_fingerprint=parent.get("fingerprint"),
            operation_key=parent.get("operation_key"),
            session_ref_canonical=parent.get("session_ref"),
            target_seat=target_seat,
        )


@dataclass(frozen=True, slots=True)
class ActiveWaiterRegistration:
    key: ActiveWaiterKey
    token: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, ActiveWaiterKey):
            raise TurnRuntimePrimitiveError("WAITER_REGISTRATION_INVALID")
        if (
            not isinstance(self.token, str)
            or _WAITER_TOKEN_RE.fullmatch(self.token) is None
        ):
            raise TurnRuntimePrimitiveError("WAITER_REGISTRATION_INVALID")


class ActiveWaiterRegistry:
    """One process-local exact waiter set with compare-and-delete removal."""

    def __init__(self, *, token_factory: Callable[[], str] | None = None) -> None:
        self._tokens: dict[ActiveWaiterKey, str] = {}
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(24))
        self._generation = 0

    def register(self, key: ActiveWaiterKey) -> ActiveWaiterRegistration:
        if not isinstance(key, ActiveWaiterKey):
            raise TurnRuntimePrimitiveError("WAITER_KEY_INVALID")
        if key in self._tokens:
            raise ActiveWaiterConflict()
        try:
            material = self._token_factory()
        except Exception:
            raise TurnRuntimePrimitiveError("WAITER_TOKEN_UNAVAILABLE") from None
        if (
            type(material) is not str
            or _WAITER_TOKEN_RE.fullmatch(material) is None
        ):
            raise TurnRuntimePrimitiveError("WAITER_REGISTRATION_INVALID")
        generation = self._generation + 1
        suffix = f"-{generation:x}"
        if len(suffix) >= 256:
            raise TurnRuntimePrimitiveError("WAITER_TOKEN_UNAVAILABLE")
        # The monotonic suffix makes each process-lifetime registration unique
        # even under a deterministic or colliding entropy source.  It avoids
        # retaining an unbounded graveyard of old tokens while making stale
        # compare-delete registrations permanently inert.
        token = f"{material[: 256 - len(suffix)]}{suffix}"
        registration = ActiveWaiterRegistration(key=key, token=token)
        if token in self._tokens.values():
            raise TurnRuntimePrimitiveError("WAITER_TOKEN_CONFLICT")
        self._generation = generation
        self._tokens[key] = token
        return registration

    def is_active(self, key: ActiveWaiterKey) -> bool:
        if not isinstance(key, ActiveWaiterKey):
            raise TurnRuntimePrimitiveError("WAITER_KEY_INVALID")
        return key in self._tokens

    def unregister(self, registration: ActiveWaiterRegistration) -> bool:
        if not isinstance(registration, ActiveWaiterRegistration):
            raise TurnRuntimePrimitiveError("WAITER_REGISTRATION_INVALID")
        current = self._tokens.get(registration.key)
        if current != registration.token:
            return False
        del self._tokens[registration.key]
        return True

    @property
    def active_count(self) -> int:
        return len(self._tokens)

    @asynccontextmanager
    async def hold(self, key: ActiveWaiterKey):
        registration = self.register(key)
        try:
            yield registration
        finally:
            self.unregister(registration)


def _is_async_callable(value: object) -> bool:
    """Return whether calling ``value`` starts in this event loop asynchronously."""

    if inspect.iscoroutinefunction(value):
        return True
    return inspect.iscoroutinefunction(getattr(value, "__call__", None))


class AsyncCandidateCollector(Generic[_T]):
    """Acquire and collect one bounded immutable candidate tuple asynchronously.

    The source itself must be an async callable and must return one async
    iterator. Source acquisition and iteration share one absolute collection
    timeout. No synchronous callback, iterable fallback, thread, or executor
    escape exists. Only one collection may be in flight; every exit path closes
    an acquired iterator when it exposes ``aclose`` and releases the in-flight
    guard so a later healthy pass can recover.
    """

    def __init__(
        self,
        *,
        source: Callable[[], Awaitable[AsyncIterator[_T]]],
        max_candidates: int,
        timeout_seconds: float,
        cleanup_timeout_seconds: float = 1.0,
    ) -> None:
        if not _is_async_callable(source):
            raise TypeError("source must be an async callable")
        if (
            isinstance(max_candidates, bool)
            or not isinstance(max_candidates, int)
            or not 1 <= max_candidates <= 256
        ):
            raise ValueError("max_candidates must be an integer between 1 and 256")
        for value, name in (
            (timeout_seconds, "timeout_seconds"),
            (cleanup_timeout_seconds, "cleanup_timeout_seconds"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) <= 0
            ):
                raise ValueError(f"{name} must be finite and positive")
        self._source = source
        self.max_candidates = max_candidates
        self.timeout_seconds = float(timeout_seconds)
        self.cleanup_timeout_seconds = float(cleanup_timeout_seconds)
        self._inflight = False

    @property
    def inflight(self) -> bool:
        return self._inflight

    async def _close(self, iterator: object) -> None:
        close = getattr(iterator, "aclose", None)
        if not callable(close):
            return
        try:
            result = close()
        except Exception:
            return
        if not hasattr(result, "__await__"):
            return
        task = asyncio.create_task(result)
        try:
            await asyncio.wait_for(task, timeout=self.cleanup_timeout_seconds)
        except asyncio.CancelledError:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        except Exception:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def collect(self) -> tuple[_T, ...]:
        if self._inflight:
            raise CandidateCollectionBusy()
        self._inflight = True
        iterator: object | None = None
        try:
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    try:
                        iterator = await self._source()
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        raise CandidateCollectionUnavailable() from exc

                    if (
                        not hasattr(iterator, "__aiter__")
                        or not hasattr(iterator, "__anext__")
                    ):
                        raise CandidateCollectionUnavailable()

                    values: list[_T] = []
                    try:
                        async for value in iterator:  # type: ignore[union-attr]
                            values.append(value)
                            if len(values) > self.max_candidates:
                                raise CandidateCollectionOverflow()
                    except (CandidateCollectionOverflow, asyncio.CancelledError):
                        raise
                    except Exception as exc:
                        raise CandidateCollectionUnavailable() from exc
                    return tuple(values)
            except (CandidateCollectionOverflow, CandidateCollectionUnavailable):
                raise
            except TimeoutError as exc:
                raise CandidateCollectionTimeout() from exc
        finally:
            try:
                if iterator is not None:
                    await self._close(iterator)
            finally:
                self._inflight = False


__all__ = [
    "ActiveWaiterConflict",
    "ActiveWaiterKey",
    "ActiveWaiterRegistration",
    "ActiveWaiterRegistry",
    "AsyncCandidateCollector",
    "CandidateCollectionBusy",
    "CandidateCollectionOverflow",
    "CandidateCollectionTimeout",
    "CandidateCollectionUnavailable",
    "TurnRuntimePrimitiveError",
]
