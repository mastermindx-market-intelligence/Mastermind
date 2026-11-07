"""Finite owned-query lifetime join on the protected Hermes installation owner.

All processes below are newly-created inert fixtures. No real systemctl, unit,
Hermes process, credential, installation record or host is inspected.
"""
import asyncio
import os
import signal
import sys
import time

import pytest

from common.hermes_role_status_contract import RoleStatusError
from ops.executive_os import hermes_role_metadata_observer as observer


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class CountedProcess:
    def __init__(self, process):
        self.process = process
        self.waits = 0
        self.kills = 0
        self.stdout = process.stdout

    @property
    def returncode(self):
        return self.process.returncode

    def kill(self):
        self.kills += 1
        self.process.kill()

    async def wait(self):
        self.waits += 1
        return await self.process.wait()


@pytest.mark.anyio
@pytest.mark.parametrize('mode', ['cancel', 'cancel-twice', 'timeout'])
async def test_fixed_query_cancellation_awaits_exact_owned_child(monkeypatch, mode):
    actual_create = asyncio.create_subprocess_exec
    started = asyncio.Event()
    captured = []

    async def inert_create(*args, **kwargs):
        assert args[0] == '/usr/bin/systemctl' and args[-2:] == tuple(observer.UNITS)
        process = await actual_create(sys.executable, '-I', '-S', '-B', '-c',
            'import time; time.sleep(60)', stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        wrapper = CountedProcess(process)
        captured.append(wrapper)
        started.set()
        return wrapper

    monkeypatch.setattr(observer.asyncio, 'create_subprocess_exec', inert_create)
    published = []

    async def request():
        if mode == 'timeout':
            async with asyncio.timeout(0.05):
                published.append(await observer._query_fixed_pid1())
        else:
            published.append(await observer._query_fixed_pid1())

    task = asyncio.create_task(request())
    await asyncio.wait_for(started.wait(), 2)
    try:
        if mode != 'timeout':
            task.cancel()
            if mode == 'cancel-twice':
                await asyncio.sleep(0)
                task.cancel()
        expected = asyncio.TimeoutError if mode == 'timeout' else asyncio.CancelledError
        with pytest.raises(expected):
            await asyncio.wait_for(task, 2)
        process = captured[0]
        assert process.waits >= 1
        assert process.returncode is not None and published == []
        assert process.kills == 1
    finally:
        process = captured[0].process
        if process.returncode is None:
            process.kill()
        await asyncio.wait_for(process.wait(), 2)


@pytest.mark.anyio
async def test_reaped_parent_with_inherited_pipe_is_bounded_refusal():
    # The fixture knows its own new session. Production does not probe/signal
    # that group to turn an unqualified descendant into a settlement claim.
    script = """import subprocess,sys,time
subprocess.Popen([sys.executable,'-I','-S','-B','-c','import time;time.sleep(60)'])
print('READY',flush=True)
time.sleep(60)
"""
    process = await asyncio.create_subprocess_exec(sys.executable, '-I', '-S', '-B',
        '-c', script, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, start_new_session=True)
    try:
        assert await process.stdout.readline() == b'READY\n'
        process.kill()
        while process.returncode is None:
            await asyncio.sleep(0)
        counted = CountedProcess(process)
        began = time.monotonic()
        with pytest.raises(RoleStatusError):
            await asyncio.wait_for(observer._settle_owned_query(counted), 1.2)
        assert time.monotonic() - began < 1.2
        assert counted.waits == 1 and counted.kills == 0
    finally:
        # Separate explicit fixture custody, never part of the helper.
        os.killpg(process.pid, signal.SIGKILL)
        await asyncio.wait_for(process.wait(), 2)
        await asyncio.wait_for(process.stdout.read(), 2)


@pytest.mark.anyio
async def test_cleanup_refusal_preserves_active_and_repeated_cancellation():
    async def refused():
        await asyncio.sleep(0.02)
        raise RoleStatusError()

    async def request():
        try:
            await asyncio.sleep(60)
        finally:
            cleanup = asyncio.create_task(refused())
            await observer._await_query_cleanup(cleanup)

    task = asyncio.create_task(request())
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)


@pytest.mark.anyio
async def test_cleanup_refusal_without_cancellation_remains_refusal():
    async def refused():
        raise RoleStatusError()
    with pytest.raises(RoleStatusError):
        await observer._await_query_cleanup(asyncio.create_task(refused()))


@pytest.mark.anyio
async def test_exited_exact_child_settles_without_another_signal():
    process = await asyncio.create_subprocess_exec(sys.executable, '-I', '-S', '-B',
        '-c', 'pass', stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL)
    await process.wait()
    counted = CountedProcess(process)
    await observer._settle_owned_query(counted)
    assert counted.waits == 1 and counted.kills == 0 and process.returncode == 0
