"""Independent reviewer lifecycle regressions retained by the source owner; all work is test-owned."""
import asyncio
import os
import threading
import pytest

import control_plane.workspace_control_room_lifecycle as lifecycle_mod
from control_plane.workspace_control_room_lifecycle import HostedControlRoom
from scripts import chairman_control_room as ccr
from scripts.chairman_control_room import UNIX_CONTROL_ROOM_ORIGIN
from tests.executive_installed_control_fixture import unix_listener
from tests.test_workspace_read_service import cache_fixture, service, frame


def _unix_room(tmp_path, *, monkeypatch, shutdown_timeout=10.0):
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    listener, path = unix_listener()
    config = ccr.ServerConfig(repo_root=tmp_path, macro_root=None, bindings_path=None,
        token="fixture", origin=UNIX_CONTROL_ROOM_ORIGIN, port=0, state_ttl=10.0)
    host = HostedControlRoom(config, listener=listener, socket_path=path,
                             allowed_peer_uids=(os.geteuid(),),
                             shutdown_timeout=shutdown_timeout)
    return host, listener, path


def _dispose(listener, path):
    listener.close()
    try:
        os.unlink(path)
    except OSError:
        pass


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


def test_repeated_cancel_retains_host_close_until_drain(tmp_path, monkeypatch):
    host, listener, path = _unix_room(tmp_path, monkeypatch=monkeypatch)
    entered, release, drained = threading.Event(), threading.Event(), threading.Event()
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
    try:
        asyncio.run(check())
    finally:
        _dispose(listener, path)


def test_repeated_cancel_start_waits_before_cleanup(tmp_path, monkeypatch):
    host, listener, path = _unix_room(tmp_path, monkeypatch=monkeypatch)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    cleanup_saw_finished = []
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
    try:
        asyncio.run(check())
    finally:
        _dispose(listener, path)
