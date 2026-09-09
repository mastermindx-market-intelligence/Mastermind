"""One bounded owner for synchronous physical attempts from async callers.

The active event loop supplies its existing default executor.  This object owns
only admission, worker-entry fencing, abandonment, drain, and close.  It never
retries an operation and never creates a thread pool or durable queue.
"""

from __future__ import annotations

import asyncio
import math
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

_Result = TypeVar("_Result")
_NOT_STARTED = object()


class SyncExecutorError(RuntimeError):
    """Base class for typed executor control failures."""

    code = "SYNC_EXECUTOR_ERROR"


class SyncExecutionTimeout(SyncExecutorError):
    code = "SYNC_EXECUTION_TIMEOUT"


class SyncExecutorClosed(SyncExecutorError):
    code = "SYNC_EXECUTOR_CLOSED"


class SyncExecutorLoopConflict(SyncExecutorError):
    code = "SYNC_EXECUTOR_LOOP_CONFLICT"


class SyncExecutorCloseTimeout(SyncExecutorError):
    code = "SYNC_EXECUTOR_CLOSE_TIMEOUT"

    def __init__(
        self, active_physical_operations: int, pending_operations: int
    ) -> None:
        self.active_physical_operations = active_physical_operations
        self.pending_operations = pending_operations
        super().__init__(
            "executor close timed out waiting for "
            f"{active_physical_operations} active physical and "
            f"{pending_operations} pending operation(s)"
        )


def _positive_timeout(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("timeout must be a positive finite number")
    selected = float(value)
    if not math.isfinite(selected) or selected <= 0:
        raise ValueError("timeout must be a positive finite number")
    return selected


class _Attempt:
    def __init__(self, *, deadline: float, clock: Callable[[], float]) -> None:
        self._gate = threading.Lock()
        self._state = "pending"
        self._abandonment: str | None = None
        self._deadline = deadline
        self._clock = clock
        self._physical_done = False
        self._wrapper_done = False
        self.task: asyncio.Task[Any] | None = None

    def enter(self) -> bool:
        with self._gate:
            if self._state != "pending":
                return False
            if self._clock() >= self._deadline:
                self._state = "abandoned"
                self._abandonment = "timeout"
                return False
            self._state = "started"
            return True

    def abandon(self, reason: str) -> bool:
        with self._gate:
            if self._state != "pending":
                return False
            self._state = "abandoned"
            self._abandonment = reason
            return True

    def started(self) -> bool:
        with self._gate:
            return self._state == "started"

    def abandonment(self) -> str | None:
        with self._gate:
            return self._abandonment

    def complete_physical(self) -> None:
        with self._gate:
            self._physical_done = True

    def physical_done(self) -> bool:
        with self._gate:
            return self._physical_done

    def complete_wrapper(self) -> None:
        with self._gate:
            self._wrapper_done = True

    def wrapper_done(self) -> bool:
        with self._gate:
            return self._wrapper_done


@dataclass(eq=False)
class _LoopEpoch:
    loop: asyncio.AbstractEventLoop
    semaphore: asyncio.Semaphore
    close_event: asyncio.Event
    idle_event: asyncio.Event
    reservations: int = 0
    waiters: int = 0
    attempts: set[_Attempt] = field(default_factory=set)

    @classmethod
    def create(cls, loop: asyncio.AbstractEventLoop, capacity: int) -> "_LoopEpoch":
        idle = asyncio.Event()
        idle.set()
        return cls(
            loop=loop,
            semaphore=asyncio.Semaphore(capacity),
            close_event=asyncio.Event(),
            idle_event=idle,
        )

    def idle(self) -> bool:
        return self.reservations == 0 and self.waiters == 0 and not self.attempts


class BoundedSyncExecutor:
    """Run one synchronous attempt with bounded physical concurrency.

    A live epoch belongs to exactly one event loop.  A later loop may reuse this
    object only after the prior epoch is completely idle.  Close is fail-closed:
    admission never reopens after close begins, even when drain times out.
    """

    def __init__(self, *, max_concurrency: int) -> None:
        if isinstance(max_concurrency, bool) or not isinstance(max_concurrency, int):
            raise TypeError("max_concurrency must be a positive integer")
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be a positive integer")
        self.max_concurrency = max_concurrency
        self._state_gate = threading.RLock()
        self._epoch: _LoopEpoch | None = None
        self._admission_closed = False
        self._terminal_closed = False

    def _bind_epoch(self, loop: asyncio.AbstractEventLoop) -> _LoopEpoch:
        with self._state_gate:
            if self._admission_closed:
                raise SyncExecutorClosed("executor admission is closed")
            epoch = self._epoch
            if epoch is None:
                epoch = _LoopEpoch.create(loop, self.max_concurrency)
                self._epoch = epoch
            elif epoch.loop is not loop:
                self._reap_detached_epoch(epoch)
                if not epoch.idle():
                    raise SyncExecutorLoopConflict(
                        "another event-loop epoch still owns executor work"
                    )
                epoch = _LoopEpoch.create(loop, self.max_concurrency)
                self._epoch = epoch
            epoch.reservations += 1
            self._mark_busy(epoch)
            return epoch

    def _reap_detached_epoch(self, epoch: _LoopEpoch) -> None:
        """Forget completed work when its owning event loop cannot retire it.

        This method runs under ``_state_gate`` and never touches an asyncio
        primitive owned by the detached loop.  The old epoch is discarded only
        after every waiter/reservation is gone and each remaining attempt has
        either completed physically or never entered user code.
        """

        if epoch.waiters != 0 or epoch.reservations != 0:
            return
        for attempt in tuple(epoch.attempts):
            if (
                attempt.started()
                and attempt.physical_done()
                and (
                    epoch.loop.is_closed()
                    or (attempt.task is not None and attempt.task.done())
                )
            ):
                epoch.attempts.discard(attempt)
            elif not attempt.started() and (
                (attempt.task is not None and attempt.task.done())
                or (epoch.loop.is_closed() and attempt.wrapper_done())
            ):
                epoch.attempts.discard(attempt)

    def _mark_busy(self, epoch: _LoopEpoch) -> None:
        epoch.idle_event.clear()

    def _mark_idle_if_complete(self, epoch: _LoopEpoch) -> None:
        if epoch.idle():
            epoch.idle_event.set()

    def _register_waiter(self, epoch: _LoopEpoch) -> None:
        with self._state_gate:
            if epoch.reservations <= 0:
                raise RuntimeError("executor reservation accounting underflow")
            epoch.reservations -= 1
            if self._admission_closed:
                self._mark_idle_if_complete(epoch)
                raise SyncExecutorClosed("executor admission is closed")
            epoch.waiters += 1

    def _drop_waiter(self, epoch: _LoopEpoch) -> None:
        with self._state_gate:
            if epoch.waiters <= 0:
                raise RuntimeError("executor waiter accounting underflow")
            epoch.waiters -= 1
            self._mark_idle_if_complete(epoch)

    async def _acquire_permit(self, epoch: _LoopEpoch, deadline: float) -> None:
        acquire = asyncio.create_task(epoch.semaphore.acquire())
        closing = asyncio.create_task(epoch.close_event.wait())
        keep_permit = False
        acquired = False
        try:
            remaining = max(0.0, deadline - epoch.loop.time())
            done, _pending = await asyncio.wait(
                {acquire, closing},
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if acquire.done() and not acquire.cancelled():
                error = acquire.exception()
                if error is not None:
                    raise error
                acquired = bool(acquire.result())
            if closing in done or self._admission_closed:
                raise SyncExecutorClosed("executor admission is closed")
            if acquire not in done or not acquired:
                raise SyncExecutionTimeout("timed out waiting for physical capacity")
            keep_permit = True
        finally:
            for task in (acquire, closing):
                if not task.done():
                    task.cancel()
            await asyncio.gather(acquire, closing, return_exceptions=True)
            # Cancellation may win immediately after the semaphore task has
            # completed but before the try body records its result. Reconcile
            # the actual task outcome before deciding whether cleanup owes the
            # permit back to this epoch.
            if (
                not acquired
                and acquire.done()
                and not acquire.cancelled()
                and acquire.exception() is None
            ):
                acquired = bool(acquire.result())
            if acquired and not keep_permit:
                epoch.semaphore.release()

    def _transition_to_attempt(self, epoch: _LoopEpoch, attempt: _Attempt) -> None:
        with self._state_gate:
            if epoch.waiters <= 0:
                raise RuntimeError("executor waiter accounting underflow")
            epoch.waiters -= 1
            if self._admission_closed:
                epoch.semaphore.release()
                self._mark_idle_if_complete(epoch)
                raise SyncExecutorClosed("executor admission is closed")
            epoch.attempts.add(attempt)

    def _discard_failed_attempt(self, epoch: _LoopEpoch, attempt: _Attempt) -> None:
        with self._state_gate:
            epoch.attempts.discard(attempt)
            epoch.semaphore.release()
            self._mark_idle_if_complete(epoch)

    def _invoke(
        self,
        epoch: _LoopEpoch,
        attempt: _Attempt,
        operation: Callable[[], _Result],
    ) -> _Result | object:
        # Close admission and worker entry share this one linearization gate.
        # It is released before the synchronous operation itself executes.
        entered = False
        try:
            with self._state_gate:
                if self._admission_closed:
                    attempt.abandon("closed")
                    return _NOT_STARTED
                if not attempt.enter():
                    return _NOT_STARTED
                entered = True
            return operation()
        finally:
            if entered:
                attempt.complete_physical()
                try:
                    epoch.loop.call_soon_threadsafe(
                        self._finish_started_attempt, epoch, attempt
                    )
                except RuntimeError:
                    # A later loop may reap this attempt only after the physical
                    # completion marker above is visible.
                    pass
            # A queued wrapper that is abandoned before entry still needs a
            # durable completion marker if its event loop closes before the
            # asyncio Task can settle.
            attempt.complete_wrapper()

    def _retire_attempt(self, epoch: _LoopEpoch, attempt: _Attempt) -> None:
        with self._state_gate:
            if attempt not in epoch.attempts:
                return
            epoch.attempts.remove(attempt)
            epoch.semaphore.release()
            self._mark_idle_if_complete(epoch)

    def _finish_started_attempt(self, epoch: _LoopEpoch, attempt: _Attempt) -> None:
        if attempt.physical_done():
            self._retire_attempt(epoch, attempt)

    def _finish_attempt(
        self, epoch: _LoopEpoch, attempt: _Attempt, task: asyncio.Task[Any]
    ) -> None:
        try:
            task.result()
        except BaseException:
            pass
        finally:
            # Started code is retired only by the worker's physical-done signal.
            if not attempt.started():
                self._retire_attempt(epoch, attempt)

    async def run(self, operation: Callable[[], _Result], *, timeout: float) -> _Result:
        if not callable(operation):
            raise TypeError("operation must be callable")
        selected_timeout = _positive_timeout(timeout)
        loop = asyncio.get_running_loop()
        with self._state_gate:
            if self._admission_closed:
                raise SyncExecutorClosed("executor admission is closed")
        epoch = self._bind_epoch(loop)
        deadline = loop.time() + selected_timeout
        self._register_waiter(epoch)
        waiter_registered = True
        try:
            await self._acquire_permit(epoch, deadline)
            attempt = _Attempt(deadline=deadline, clock=loop.time)
            self._transition_to_attempt(epoch, attempt)
            waiter_registered = False
        except BaseException:
            if waiter_registered:
                self._drop_waiter(epoch)
            raise

        try:
            physical = asyncio.create_task(
                asyncio.to_thread(self._invoke, epoch, attempt, operation)
            )
            attempt.task = physical
            physical.add_done_callback(
                lambda task: self._finish_attempt(epoch, attempt, task)
            )
        except BaseException:
            self._discard_failed_attempt(epoch, attempt)
            raise

        deadline_scope = asyncio.timeout_at(deadline)
        try:
            async with deadline_scope:
                result = await asyncio.shield(physical)
        except asyncio.TimeoutError as error:
            if deadline_scope.expired():
                attempt.abandon("timeout")
                raise SyncExecutionTimeout(
                    "synchronous attempt exceeded its deadline"
                ) from error
            raise
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if attempt.abandonment() == "closed" and (
                current is None or current.cancelling() == 0
            ):
                raise SyncExecutorClosed("executor admission is closed")
            attempt.abandon("caller")
            raise

        if result is _NOT_STARTED:
            reason = attempt.abandonment()
            if reason == "timeout":
                raise SyncExecutionTimeout("synchronous attempt exceeded its deadline")
            if reason == "closed":
                raise SyncExecutorClosed("executor admission is closed")
            raise SyncExecutorClosed("synchronous attempt was abandoned before entry")
        return result

    async def aclose(self, *, timeout: float) -> None:
        selected_timeout = _positive_timeout(timeout)
        loop = asyncio.get_running_loop()
        with self._state_gate:
            if self._terminal_closed:
                return
            epoch = self._epoch
            if epoch is not None and epoch.loop is not loop:
                self._reap_detached_epoch(epoch)
                if not epoch.idle():
                    raise SyncExecutorLoopConflict(
                        "another event-loop epoch still owns executor work"
                    )
            if epoch is None or epoch.loop is not loop:
                epoch = _LoopEpoch.create(loop, self.max_concurrency)
                self._epoch = epoch
            self._admission_closed = True
            epoch.close_event.set()
            for attempt in tuple(epoch.attempts):
                attempt.abandon("closed")
                if not attempt.started() and attempt.task is not None:
                    # A queued default-executor wrapper is not a physical call.
                    # Cancellation retires its async admission token; the shared
                    # gate still prevents a racing worker from entering user code.
                    attempt.task.cancel()
            already_idle = epoch.idle()

        if not already_idle:
            close_scope = asyncio.timeout(selected_timeout)
            try:
                async with close_scope:
                    await epoch.idle_event.wait()
            except asyncio.TimeoutError as error:
                with self._state_gate:
                    attempts = tuple(epoch.attempts)
                    active = sum(attempt.started() for attempt in attempts)
                    pending = epoch.waiters + len(attempts) - active
                raise SyncExecutorCloseTimeout(active, pending) from error

        with self._state_gate:
            if not epoch.idle():
                attempts = tuple(epoch.attempts)
                active = sum(attempt.started() for attempt in attempts)
                pending = epoch.waiters + len(attempts) - active
                raise SyncExecutorCloseTimeout(active, pending)
            self._terminal_closed = True

    def attempts_snapshot(self) -> tuple[_Attempt, ...]:
        """Read-only compatibility projection for owner-side diagnostics/tests."""
        with self._state_gate:
            if self._epoch is None:
                return ()
            return tuple(self._epoch.attempts)
