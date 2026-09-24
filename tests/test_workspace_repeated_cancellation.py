"""Independent reviewer lifecycle regressions retained by the source owner; all work is test-owned."""
import asyncio
import threading
import pytest
from tests.test_workspace_read_service import cache_fixture, service, frame


def test_repeated_cancel_retains_acquisition_until_close(tmp_path):
    _, _, cache = cache_fixture(tmp_path)
    started, release, closed = threading.Event(), threading.Event(), threading.Event()
    baseline = service(cache)._acquire
    def acquire(*args, **kwargs):
        started.set()
        try:
            assert release.wait(3)
            return baseline(*args, **kwargs)
        finally:
            closed.set()
    async def check():
        task = asyncio.create_task(service(cache, acquire=acquire).handle_frame(frame()))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            task.cancel()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not task.done(), 'request relinquished custody before acquisition closed'
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
            assert await asyncio.to_thread(closed.wait, 2)
    asyncio.run(check())


def test_repeated_cancel_retains_host_close_until_drain(tmp_path):
    from tests.test_workspace_control_room_lifecycle import config
    from control_plane.workspace_control_room_lifecycle import HostedControlRoom
    entered, release, drained = threading.Event(), threading.Event(), threading.Event()
    host = HostedControlRoom(config(tmp_path))
    def close_owned():
        entered.set()
        try:
            assert release.wait(3)
        finally:
            drained.set()
    host._close = close_owned
    async def check():
        task = asyncio.create_task(host.close())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            task.cancel()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not task.done(), 'host close returned before owned drain completed'
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
            assert await asyncio.to_thread(drained.wait, 2)
    asyncio.run(check())


def test_repeated_cancel_start_waits_before_cleanup(tmp_path):
    from tests.test_workspace_control_room_lifecycle import config
    from control_plane.workspace_control_room_lifecycle import HostedControlRoom
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    cleanup_saw_finished = []
    host = HostedControlRoom(config(tmp_path))
    def start_owned():
        entered.set()
        assert release.wait(3)
        finished.set()
    def close_owned():
        cleanup_saw_finished.append(finished.is_set())
    host._start, host._close = start_owned, close_owned
    async def check():
        task = asyncio.create_task(host.start())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            for _ in range(20):
                if cleanup_saw_finished: break
                await asyncio.sleep(.005)
            assert not cleanup_saw_finished, 'cleanup raced ahead of incomplete startup'
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
            assert await asyncio.to_thread(finished.wait, 2)
    asyncio.run(check())
