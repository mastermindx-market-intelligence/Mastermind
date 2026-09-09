from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from typing import Any

import pytest

from common import bounded_sync_executor as executor_module
from common.bounded_sync_executor import (
    BoundedSyncExecutor,
    SyncExecutionTimeout,
    SyncExecutorClosed,
    SyncExecutorCloseTimeout,
    SyncExecutorLoopConflict,
)


class BlockingOperation:
    def __init__(self, result: object = "done") -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.result = result
        self._lock = threading.Lock()
        self.started = 0
        self.finished = 0

    def __call__(self) -> object:
        with self._lock:
            self.started += 1
        self.entered.set()
        try:
            if not self.release.wait(5):
                raise AssertionError("blocking operation was not released")
            return self.result
        finally:
            with self._lock:
                self.finished += 1


async def wait_until(predicate: Callable[[], bool], timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("condition was not reached")
        await asyncio.sleep(0.001)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_timeout_retains_capacity_until_physical_completion() -> None:
    executor = BoundedSyncExecutor(max_concurrency=1)
    physical = BlockingOperation()
    late_started = threading.Event()

    def late() -> str:
        late_started.set()
        return "late"

    async def scenario() -> None:
        first = asyncio.create_task(executor.run(physical, timeout=0.03))
        assert await asyncio.to_thread(physical.entered.wait, 1)
        with pytest.raises(SyncExecutionTimeout):
            await first
        assert physical.started == 1 and physical.finished == 0

        with pytest.raises(SyncExecutionTimeout):
            await executor.run(late, timeout=0.03)
        assert not late_started.is_set()

        physical.release.set()
        await wait_until(lambda: physical.finished == 1)
        assert await executor.run(late, timeout=1) == "late"
        await executor.aclose(timeout=1)

    run(scenario())


def test_cancelled_waiter_never_enters_after_capacity_returns() -> None:
    executor = BoundedSyncExecutor(max_concurrency=1)
    physical = BlockingOperation()
    queued_started = threading.Event()

    def queued() -> None:
        queued_started.set()

    async def scenario() -> None:
        first = asyncio.create_task(executor.run(physical, timeout=2))
        assert await asyncio.to_thread(physical.entered.wait, 1)
        second = asyncio.create_task(executor.run(queued, timeout=2))
        await asyncio.sleep(0)
        second.cancel()
        cancelled = await asyncio.gather(second, return_exceptions=True)
        assert isinstance(cancelled[0], asyncio.CancelledError)

        physical.release.set()
        assert await first == "done"
        await asyncio.sleep(0.02)
        assert not queued_started.is_set()
        await executor.aclose(timeout=1)

    run(scenario())


def test_close_is_fail_closed_until_started_work_physically_drains() -> None:
    executor = BoundedSyncExecutor(max_concurrency=1)
    physical = BlockingOperation()

    async def scenario() -> None:
        running = asyncio.create_task(executor.run(physical, timeout=2))
        assert await asyncio.to_thread(physical.entered.wait, 1)
        queued = asyncio.create_task(executor.run(lambda: "forbidden", timeout=2))
        await asyncio.sleep(0)

        with pytest.raises(SyncExecutorCloseTimeout) as captured:
            await executor.aclose(timeout=0.02)
        assert captured.value.active_physical_operations == 1
        with pytest.raises(SyncExecutorClosed):
            await executor.run(lambda: "forbidden", timeout=1)
        with pytest.raises(SyncExecutorClosed):
            await queued

        physical.release.set()
        assert await running == "done"
        await executor.aclose(timeout=1)
        await executor.aclose(timeout=0.01)

    run(scenario())


def test_concurrent_foreign_loop_refuses_without_poisoning_owner_epoch() -> None:
    executor = BoundedSyncExecutor(max_concurrency=1)
    physical = BlockingOperation("first")
    owner_result: list[object] = []
    owner_error: list[BaseException] = []

    def owner() -> None:
        async def scenario() -> None:
            owner_result.append(await executor.run(physical, timeout=2))

        try:
            asyncio.run(scenario())
        except BaseException as error:
            owner_error.append(error)

    thread = threading.Thread(target=owner)
    thread.start()
    assert physical.entered.wait(1)

    async def foreign() -> None:
        with pytest.raises(SyncExecutorLoopConflict):
            await executor.run(lambda: "foreign", timeout=0.1)
        with pytest.raises(SyncExecutorLoopConflict):
            await executor.aclose(timeout=0.1)

    run(foreign())
    physical.release.set()
    thread.join(2)
    assert not thread.is_alive()
    assert not owner_error
    assert owner_result == ["first"]

    async def next_epoch() -> None:
        assert await executor.run(lambda: "second", timeout=1) == "second"
        await executor.aclose(timeout=1)

    run(next_epoch())


def test_cancellation_racing_successful_permit_acquisition_does_not_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = BoundedSyncExecutor(max_concurrency=1)
    real_wait = executor_module.asyncio.wait
    armed = True

    async def cancellation_race(*args: Any, **kwargs: Any):
        nonlocal armed
        done, pending = await real_wait(*args, **kwargs)
        if armed:
            armed = False
            current = asyncio.current_task()
            assert current is not None
            current.cancel()
            await asyncio.sleep(0)
        return done, pending

    async def scenario() -> None:
        monkeypatch.setattr(executor_module.asyncio, "wait", cancellation_race)
        cancelled = asyncio.create_task(executor.run(lambda: "unseen", timeout=1))
        result = await asyncio.gather(cancelled, return_exceptions=True)
        assert isinstance(result[0], asyncio.CancelledError)
        monkeypatch.undo()
        assert await executor.run(lambda: "recovered", timeout=0.2) == "recovered"
        await executor.aclose(timeout=1)

    run(scenario())


def test_loop_shutdown_keeps_started_physical_attempt_owned_until_completion() -> None:
    executor = BoundedSyncExecutor(max_concurrency=1)
    physical = BlockingOperation("physical")
    caller_cancelled = threading.Event()
    owner_errors: list[BaseException] = []

    def owner() -> None:
        async def scenario() -> None:
            pending = asyncio.create_task(executor.run(physical, timeout=5))
            assert await asyncio.to_thread(physical.entered.wait, 1)
            pending.cancel()
            result = await asyncio.gather(pending, return_exceptions=True)
            assert isinstance(result[0], asyncio.CancelledError)
            caller_cancelled.set()

        try:
            asyncio.run(scenario())
        except BaseException as error:
            owner_errors.append(error)

    thread = threading.Thread(target=owner)
    thread.start()
    assert physical.entered.wait(1)
    assert caller_cancelled.wait(1)

    # Let asyncio.run enter shutdown and cancel its shielded to_thread wrapper.
    threading.Event().wait(0.1)
    assert thread.is_alive()

    async def foreign() -> None:
        with pytest.raises(SyncExecutorLoopConflict):
            await executor.run(lambda: "foreign", timeout=0.1)

    run(foreign())
    physical.release.set()
    thread.join(2)
    assert not thread.is_alive()
    assert not owner_errors

    async def next_epoch() -> None:
        assert await executor.run(lambda: "next", timeout=1) == "next"
        await executor.aclose(timeout=1)

    run(next_epoch())


def test_close_retires_caller_abandoned_default_executor_queue() -> None:
    executor = BoundedSyncExecutor(max_concurrency=1)
    pool_entered = threading.Event()
    pool_release = threading.Event()
    forbidden_started = threading.Event()

    def occupy_default_pool() -> None:
        pool_entered.set()
        if not pool_release.wait(5):
            raise AssertionError("default pool blocker was not released")

    def forbidden() -> None:
        forbidden_started.set()

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        occupied = asyncio.create_task(asyncio.to_thread(occupy_default_pool))
        await wait_until(pool_entered.is_set)
        queued = asyncio.create_task(executor.run(forbidden, timeout=2))
        await wait_until(lambda: len(executor.attempts_snapshot()) == 1)
        queued.cancel()
        result = await asyncio.gather(queued, return_exceptions=True)
        assert isinstance(result[0], asyncio.CancelledError)
        await executor.aclose(timeout=0.2)
        assert not forbidden_started.is_set()
        pool_release.set()
        await occupied
        assert not forbidden_started.is_set()

    run(scenario())


def test_first_waiter_registration_is_atomic_with_loop_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = BoundedSyncExecutor(max_concurrency=1)
    original_register = executor._register_waiter
    first_bound = threading.Event()
    allow_first_register = threading.Event()
    start_second = threading.Event()
    release = threading.Event()
    registration_gate = threading.Lock()
    state_gate = threading.Lock()
    first = True
    active = 0
    maximum_active = 0
    errors: list[BaseException] = []

    def delayed_register(epoch: Any) -> None:
        nonlocal first
        with registration_gate:
            selected_first = first
            first = False
        if selected_first:
            first_bound.set()
            if not allow_first_register.wait(2):
                raise AssertionError("first registration was not released")
        original_register(epoch)

    monkeypatch.setattr(executor, "_register_waiter", delayed_register)

    def operation() -> str:
        nonlocal active, maximum_active
        with state_gate:
            active += 1
            maximum_active = max(maximum_active, active)
        try:
            if not release.wait(5):
                raise AssertionError("two-loop admission test was not released")
            return "done"
        finally:
            with state_gate:
                active -= 1

    def caller(wait_for_second: bool) -> None:
        if wait_for_second:
            start_second.wait(2)
        try:
            asyncio.run(executor.run(operation, timeout=2))
        except BaseException as error:
            errors.append(error)

    first_thread = threading.Thread(target=caller, args=(False,))
    second_thread = threading.Thread(target=caller, args=(True,))
    first_thread.start()
    assert first_bound.wait(1)
    second_thread.start()
    start_second.set()
    threading.Event().wait(0.1)
    allow_first_register.set()
    threading.Event().wait(0.1)
    with state_gate:
        observed_maximum = maximum_active
    release.set()
    for thread in (first_thread, second_thread):
        thread.join(3)
        assert not thread.is_alive()

    assert observed_maximum == 1
    assert sum(isinstance(error, SyncExecutorLoopConflict) for error in errors) == 1


def test_close_reaps_completed_attempt_after_original_loop_is_closed() -> None:
    executor = BoundedSyncExecutor(max_concurrency=1)
    physical = BlockingOperation("physical")
    owner_closed = threading.Event()
    owner_errors: list[BaseException] = []
    pool = ThreadPoolExecutor(max_workers=1)

    def owner() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_default_executor(pool)
        loop.set_exception_handler(lambda _loop, _context: None)

        async def scenario() -> None:
            pending = asyncio.create_task(executor.run(physical, timeout=5))
            while not physical.entered.is_set():
                await asyncio.sleep(0.001)
            with pytest.raises(SyncExecutorCloseTimeout):
                await executor.aclose(timeout=0.01)
            pending.cancel()
            result = await asyncio.gather(pending, return_exceptions=True)
            assert isinstance(result[0], asyncio.CancelledError)
            attempts = executor.attempts_snapshot()
            assert len(attempts) == 1 and attempts[0].task is not None

        try:
            loop.run_until_complete(scenario())
        except BaseException as error:
            owner_errors.append(error)
        finally:
            loop.close()
            owner_closed.set()

    thread = threading.Thread(target=owner)
    thread.start()
    assert physical.entered.wait(1)
    assert owner_closed.wait(2)
    thread.join(2)
    assert not thread.is_alive() and not owner_errors

    physical.release.set()
    for _ in range(200):
        if physical.finished == 1:
            break
        threading.Event().wait(0.01)
    assert physical.finished == 1

    asyncio.run(executor.aclose(timeout=1))
    assert executor.attempts_snapshot() == ()

    pool.shutdown(wait=True)


def test_foreign_close_does_not_reap_completed_attempt_from_open_owner_loop() -> None:
    executor = BoundedSyncExecutor(max_concurrency=1)
    physical = BlockingOperation("physical")
    owner_paused = threading.Event()
    allow_owner_drain = threading.Event()
    owner_closed = threading.Event()
    owner_errors: list[BaseException] = []

    def owner() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def scenario() -> None:
            pending = asyncio.create_task(executor.run(physical, timeout=5))
            while not physical.entered.is_set():
                await asyncio.sleep(0.001)
            pending.cancel()
            result = await asyncio.gather(pending, return_exceptions=True)
            assert isinstance(result[0], asyncio.CancelledError)

        try:
            loop.run_until_complete(scenario())
            owner_paused.set()
            if not allow_owner_drain.wait(5):
                raise AssertionError("owner loop was not released")
            loop.run_until_complete(asyncio.sleep(0.02))
        except BaseException as error:
            owner_errors.append(error)
        finally:
            loop.close()
            owner_closed.set()

    thread = threading.Thread(target=owner)
    thread.start()
    assert physical.entered.wait(1)
    assert owner_paused.wait(2)

    physical.release.set()
    for _ in range(200):
        if physical.finished == 1:
            break
        threading.Event().wait(0.01)
    assert physical.finished == 1

    with pytest.raises(SyncExecutorLoopConflict):
        asyncio.run(executor.aclose(timeout=0.1))

    allow_owner_drain.set()
    assert owner_closed.wait(2)
    thread.join(2)
    assert not thread.is_alive() and not owner_errors

    asyncio.run(executor.aclose(timeout=1))
    assert executor.attempts_snapshot() == ()


def test_close_reaps_abandoned_queued_wrapper_after_owner_loop_closes() -> None:
    executor = BoundedSyncExecutor(max_concurrency=1)
    pool = ThreadPoolExecutor(max_workers=1)
    pool_entered = threading.Event()
    release_pool = threading.Event()
    owner_closed = threading.Event()
    owner_errors: list[BaseException] = []
    operation_calls: list[str] = []

    def occupy_pool() -> None:
        pool_entered.set()
        assert release_pool.wait(5)

    def forbidden_operation() -> str:
        operation_calls.append("called")
        return "unexpected"

    blocker = pool.submit(occupy_pool)
    assert pool_entered.wait(1)

    def owner() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_default_executor(pool)
        loop.set_exception_handler(lambda _loop, _context: None)

        async def scenario() -> None:
            pending = asyncio.create_task(executor.run(forbidden_operation, timeout=5))
            for _ in range(500):
                attempts = executor.attempts_snapshot()
                if len(attempts) == 1 and attempts[0].task is not None:
                    break
                await asyncio.sleep(0.001)
            else:
                raise AssertionError("queued wrapper never registered")
            assert not attempts[0].started()
            pending.cancel()
            result = await asyncio.gather(pending, return_exceptions=True)
            assert isinstance(result[0], asyncio.CancelledError)

        try:
            loop.run_until_complete(scenario())
        except BaseException as error:
            owner_errors.append(error)
        finally:
            loop.close()
            owner_closed.set()

    thread = threading.Thread(target=owner)
    thread.start()
    assert owner_closed.wait(2)
    thread.join(2)
    assert not thread.is_alive() and not owner_errors

    release_pool.set()
    blocker.result(timeout=2)
    pool.shutdown(wait=True)
    assert operation_calls == []

    asyncio.run(executor.aclose(timeout=1))
    assert executor.attempts_snapshot() == ()
