"""Private selected-source guards. No wire fields or source ownership live here."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import re
import inspect
from typing import Any, Callable

from .contracts import ContractViolation


@dataclass(frozen=True)
class GuardedOperation:
    value: Any
    selection_identity: tuple[str, str, str, int]
    delivery_guard: Callable[[], None]


class _Capture:
    def __init__(self, bounded):
        self.bounded = bounded
        self.identity = None
        self.guard = None
        self.calls = 0
        self.invalid = False

    def invalidate(self):
        self.invalid = True
        self.identity = self.guard = None

    def _refuse(self):
        self.invalidate()
        raise ContractViolation("SOURCE_UNAVAILABLE")

    def retain(self, result):
        if self.invalid or type(result) is not GuardedOperation or not callable(result.delivery_guard):
            self._refuse()
        key = result.selection_identity
        if (type(key) is not tuple or len(key) != 4
                or any(type(x) is not str or not 0 < len(x) <= 1024 for x in key[:3])
                or re.fullmatch(r"[0-9a-f]{64}", key[2]) is None
                or type(key[3]) is not int or key[3] < 0):
            self._refuse()
        if self.identity is not None and self.identity != key:
            self._refuse()
        self.calls += 1
        if self.calls > 22:
            self._refuse()
        self.identity, self.guard = key, result.delivery_guard
        return result.value

    async def check(self):
        if self.invalid or self.identity is None or self.guard is None:
            self._refuse()
        guard = self.guard
        def verify():
            try:
                observed = guard()
                if inspect.iscoroutine(observed):
                    observed.close()
                if observed is not None:
                    raise ValueError("invalid guard result")
            except Exception:
                self.invalidate()
                raise ContractViolation("SOURCE_UNAVAILABLE") from None
        # Share the adapter's actual four slots, including cancellation custody.
        await self.bounded(verify)


class SelectionScopes:
    def __init__(self, bounded):
        self.bounded = bounded
        self.current = ContextVar("research_delivery_selection", default=None)

    @contextmanager
    def capture(self):
        if self.current.get() is not None:
            raise ContractViolation("SOURCE_UNAVAILABLE")
        value = _Capture(self.bounded)
        token = self.current.set(value)
        try:
            yield value
        finally:
            self.current.reset(token)

    def active(self):
        value = self.current.get()
        if value is None or value.invalid:
            raise ContractViolation("SOURCE_UNAVAILABLE")
        return value
