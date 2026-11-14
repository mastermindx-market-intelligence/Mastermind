"""Service-owned exact-run observation using T3's incumbent native wait.

The optional native-watch CLI donor supports only local root threads. Native
wait already routes to enrolled remote environments and retains original run
identity. This adapter therefore uses bounded native waits plus bounded question
reads, not a second event service, auth flow, model worker or inference retry.
It is started and drained by the existing Runtime reply subscription owner.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from .t3_native_client import Run, T3NativeClient, Unavailable
from .t3_reply_events import T3ReturnEffectUnknown


class T3NativeReturnWait:
    """One shared original-run observation loop; failures never auto-reconnect."""
    def __init__(self, resolve: Callable, consume: Callable, *, capacity: asyncio.Semaphore,
                 timeout_ms: int = 30000, minimum_interval_seconds: float = 5):
        if not callable(resolve) or not callable(consume) or type(capacity) is not asyncio.Semaphore:
            raise TypeError("Current retained resolver, consumer and host I/O bound required")
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 30000:
            raise ValueError("Native wait must remain bounded")
        if (type(minimum_interval_seconds) not in (int, float)
                or not 0 < minimum_interval_seconds <= 30):
            raise ValueError("A bounded non-spinning observation interval is required")
        self.resolve, self.consume, self.capacity = resolve, consume, capacity
        self.timeout_ms, self.minimum_interval = timeout_ms, minimum_interval_seconds
        self.task = None
        self.state, self.code, self.observations = "NOT_STARTED", None, 0
        self._stop = asyncio.Event()

    async def start(self):
        if self.task is not None or self.state != "NOT_STARTED":
            raise Unavailable("Original native observer already exists")
        self.state = "STARTING"
        self.task = asyncio.create_task(self._run(), name="executive-t3-original-return-wait")
        return self

    async def _run(self):
        try:
            while not self._stop.is_set():
                started = time.monotonic()
                async with self.capacity:
                    if self._stop.is_set(): break
                    self.state = "RESOLVING_ORIGINAL_SUBSCRIBER"
                    selected = await self.resolve()
                    if selected is None:
                        self.state, self.code = "STOPPED", "NO_CURRENT_ORIGINAL_SUBSCRIBER"
                        return
                    principal, run, client = selected
                    if type(run) is not Run or type(client) is not T3NativeClient or client.scope != run.thread.scope:
                        raise Unavailable("Original native return scope changed")
                    if self._stop.is_set(): break
                    self.state = "WAITING_NATIVE"
                    state = await client.wait(run, timeout_ms=self.timeout_ms)
                    if self._stop.is_set(): break
                    self.state = "CONSUMING_ORIGINAL_OBSERVATION"
                    outcome = await self.consume(principal, run, state)
                self.observations += 1
                if outcome is not True:
                    self.state, self.code = "STOPPED", "ORIGINAL_RETURN_BOUNDARY_REACHED"
                    return
                # Some native waits return immediately for a pending question.
                # Bound such observations without starting another timer/queue
                # owner or consuming model turns to poll unchanged state.
                remaining = self.minimum_interval - (time.monotonic() - started)
                if remaining > 0:
                    self.state = "WAITING_NATIVE_INTERVAL"
                    try:
                        await asyncio.wait_for(self._stop.wait(), remaining)
                    except asyncio.TimeoutError:
                        pass
                else:
                    # An in-process native transport can satisfy each await
                    # synchronously. Always yield so shutdown, revocation and
                    # other original subscribers cannot be starved.
                    await asyncio.sleep(0)
            self.state = "STOPPED"
        except T3ReturnEffectUnknown:
            self.state, self.code = "EFFECT_UNKNOWN", "ORIGINAL_RETURN_COMMIT_UNCERTAIN"
        except asyncio.CancelledError:
            self.state, self.code = "STOPPED", "OWNED_OBSERVER_CANCELLED"
            raise
        except Exception:
            self.state, self.code = "UNAVAILABLE", "ORIGINAL_NATIVE_RETURN_UNAVAILABLE"

    async def close(self):
        self._stop.set()
        if self.task is not None and self.task is not asyncio.current_task():
            # An idle/read-only wait can cancel its own native helper without
            # stopping inference. An admitted result commit or callback must
            # drain through its incumbent effect owner, never be replayed.
            if not self.task.done() and self.state != "CONSUMING_ORIGINAL_OBSERVATION":
                self.task.cancel()
            try:
                await asyncio.shield(self.task)
            except asyncio.CancelledError:
                if not self.task.cancelled():
                    raise
        if self.state not in {"UNAVAILABLE", "EFFECT_UNKNOWN"}:
            self.state = "STOPPED"

    def status(self):
        return {"state": self.state, "code": self.code, "observations": self.observations,
                "transport": "native_exact_run_wait", "maximum_wait_ms": self.timeout_ms,
                "minimum_observation_interval_seconds": self.minimum_interval,
                "automatic_reconnect": False, "native_inference_started": False}
