"""Finite authenticated MCP request lifetime; Runtime retains all effect authority."""
from __future__ import annotations
import asyncio
import contextlib
import contextvars
import math
import time

# This is a transport ceiling, not admission or launch authority.
MAX_FOREGROUND_SECONDS = 300.0
_SCOPE_KEY = "mastermind.session_bridge.http_foreground"
_MINT = object()
_ACTIVE = contextvars.ContextVar("mastermind_session_bridge_http_foreground", default=None)

class HttpForegroundClosed(RuntimeError):
    pass

class _HttpInvocation:
    def __init__(self, mint, scope, *, deadline_seconds=MAX_FOREGROUND_SECONDS):
        if mint is not _MINT:
            raise HttpForegroundClosed("HTTP invocation is transport composed")
        if (type(deadline_seconds) not in (int, float) or not math.isfinite(deadline_seconds)
                or not 0 < deadline_seconds <= MAX_FOREGROUND_SECONDS):
            raise ValueError("finite HTTP deadline required")
        self._scope = scope
        self._deadline = time.monotonic() + deadline_seconds
        self._closed = False
        self._bound = False
        self._writer = None
        self._writer_attached = False
        self._closed_event = asyncio.Event()
        self._token_expiry = None
        self._clock = time.time

    def require_live(self):
        if (self._closed or time.monotonic() >= self._deadline
                or (self._token_expiry is not None and self._now() >= self._token_expiry)):
            self.close()
            raise HttpForegroundClosed("originating HTTP request is no longer live")

    def remaining_seconds(self):
        self.require_live()
        return min(self._deadline-time.monotonic(),
                   MAX_FOREGROUND_SECONDS if self._token_expiry is None else self._token_expiry-self._now())

    def _now(self):
        value = self._clock()
        if type(value) not in (int, float) or not math.isfinite(value):
            self.close()
            raise HttpForegroundClosed("installed authentication clock unavailable")
        return value

    def bind(self, scope, principal, *, clock=None):
        self.require_live()
        if scope is not self._scope or self._bound:
            raise HttpForegroundClosed("originating HTTP request binding unavailable")
        if clock is not None:
            if not callable(clock):
                raise HttpForegroundClosed("installed authentication clock unavailable")
            self._clock = clock
        if (type(principal.issued_at) is not int or type(principal.expires_at) is not int
                or not principal.issued_at <= self._now() < principal.expires_at):
            raise HttpForegroundClosed("current authenticated principal unavailable")
        self._token_expiry = principal.expires_at
        self._bound = True

    def attach_writer(self, writer):
        self.require_live()
        if not self._bound or _ACTIVE.get() is not self or self._writer_attached:
            raise HttpForegroundClosed("private connection is not this invocation")
        self._writer, self._writer_attached = writer, True

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._closed_event.set()
        writer, self._writer = self._writer, None
        if writer is not None:
            writer.close()
            # End this request's own private transport, never its worker/controller.
            if writer.transport is not None:
                writer.transport.abort()

    async def watch(self, receive):
        try:
            while True:
                message = await asyncio.wait_for(receive(), timeout=self.remaining_seconds())
                if message.get("type") == "http.disconnect":
                    return
                # The body has already been consumed in full by the real outer owner.
                # An unexpected extra body/event cannot prove continued attendance.
                return
        except (asyncio.TimeoutError, HttpForegroundClosed):
            pass
        finally:
            self.close()

    async def run(self, call):
        self.require_live()
        if _ACTIVE.get() is not self:
            raise HttpForegroundClosed("originating invocation is no longer current")
        task = asyncio.create_task(call())
        closed = asyncio.create_task(self._closed_event.wait())
        try:
            done, _ = await asyncio.wait((task, closed), return_when=asyncio.FIRST_COMPLETED)
            self.require_live()
            if task not in done:
                raise HttpForegroundClosed("originating HTTP request ended")
            return await task
        finally:
            # This cancels only the network-side await; canonical effect remains on
            # its original operation and is reconciled, never replaced or replayed.
            for pending in (task, closed):
                if not pending.done():
                    pending.cancel()
            await asyncio.gather(task, closed, return_exceptions=True)

@contextlib.contextmanager
def bind_request(request, principal, *, clock=None):
    value = request.scope.get(_SCOPE_KEY)
    if type(value) is not _HttpInvocation:
        raise HttpForegroundClosed("actual upstream request source is unavailable")
    value.bind(request.scope, principal, clock=clock)
    token = _ACTIVE.set(value)
    try:
        yield value
    finally:
        value.close()
        _ACTIVE.reset(token)

def current_request():
    value = _ACTIVE.get()
    if type(value) is not _HttpInvocation or not value._bound:
        raise HttpForegroundClosed("actual upstream request source is unavailable")
    value.require_live()
    return value

def _current_request_or_none():
    # Absence retains the incumbent one-shot path. A copied but expired source
    # must refuse rather than silently obtaining a fresh legacy request.
    if _ACTIVE.get() is None:
        return None
    return current_request()

@contextlib.asynccontextmanager
async def owned_request(scope, receive, *, deadline_seconds=MAX_FOREGROUND_SECONDS):
    # A new scope is passed to the actual ASGI/MCP owner. Client DTOs and headers
    # cannot create the nominal object stored here.
    current = dict(scope)
    value = _HttpInvocation(_MINT, current, deadline_seconds=deadline_seconds)
    current[_SCOPE_KEY] = value
    watcher = asyncio.create_task(value.watch(receive), name="session-bridge-http-request-lifetime")
    try:
        yield current
    finally:
        value.close()
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
