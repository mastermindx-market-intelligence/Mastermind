"""Real native owner-channel tests, without a tool/provider execution claim."""
import asyncio
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from test_acp_native_startup import launch  # reuse the actual clean native launch fixture
from integrations.acp_worker.native import AcpNativeProcessOwner
from integrations.acp_worker.tool_admission import AcpAdmissionChannel, AcpNativeToolGate, AcpObservedTool

PROBE = '''
import json, os, socket, sys
sock = socket.socket(fileno=int(os.environ['MMX_ACP_ATTEST_FD']))
f = sock.makefile('rwb', buffering=0)
seed = json.loads(f.readline())
mode = sys.argv[1]
if mode == 'missing':
    sys.stdin.read()
else:
    message = dict(seed, ready=True)
    if mode == 'nonce': message['launch_nonce'] = 'wrong'
    if mode == 'tools': message['admitted_tools'] = []
    if mode == 'extra': message['self_grant'] = 'shell'
    raw = json.dumps(message)
    if mode == 'duplicate': raw = raw[:-1] + ',"ready":true}'
    f.write(raw.encode() + b'\\n')
    ack = f.readline()
    if ack: print(ack.decode().strip(), flush=True)
    f.close(); sock.close()
    sys.stdin.read()
'''


def setup(launch, tmp_path, mode='ok'):
    profile, spec = launch
    probe = tmp_path / 'gate_probe.py'
    probe.write_text(PROBE)
    profile = dataclasses.replace(profile, argv=(profile.argv[0], str(probe), mode))
    sha = hashlib.sha256(probe.read_bytes()).hexdigest()
    gate = AcpNativeToolGate('a' * 64, sha, (AcpObservedTool('mcp__granted__read_file', 'b' * 64),),
                             ((str(probe), sha),))
    return AcpNativeProcessOwner(profile, environment_loader=lambda: {}, tool_gate=gate), spec, probe


def test_actual_inherited_channel_binds_generation_and_is_single_use(launch, tmp_path):
    owner, spec, _ = setup(launch, tmp_path)
    async def run():
        resources = await owner.open_run(spec)
        try:
            receipt = await asyncio.wait_for(resources.prepare_prompt('session-1', spec.model), 2)
            assert receipt.matches(spec, resources.process_ref, 'session-1', spec.model)
            assert not receipt.matches(spec, dataclasses.replace(resources.process_ref, launch_nonce='wrong'),
                                       'session-1', spec.model)
            assert json.loads(await resources.reader.readline()) == {'accepted': True}
            with pytest.raises(ValueError, match='already consumed'):
                await resources.prepare_prompt('session-1', spec.model)
        finally:
            complete = await resources.finish(None)
        assert complete.settled and owner._active is None
        assert not owner._identity_matches(resources.process_ref)
        assert owner._runs[spec.run_id].admission_channel.task.done()
    asyncio.run(run())


@pytest.mark.parametrize('mode', ['nonce', 'tools', 'extra', 'duplicate'])
def test_child_cannot_change_owner_receipt(launch, tmp_path, mode):
    owner, spec, _ = setup(launch, tmp_path, mode)
    async def run():
        resources = await owner.open_run(spec)
        try:
            with pytest.raises(ValueError):
                await asyncio.wait_for(resources.prepare_prompt('session-1', spec.model), 2)
        finally:
            complete = await resources.finish('readiness refused')
        assert complete.settled and owner._active is None
        assert await resources.reader.read() == b''  # no acceptance ACK
    asyncio.run(run())


def test_missing_readiness_is_cancelled_by_original_owner(launch, tmp_path):
    owner, spec, _ = setup(launch, tmp_path, 'missing')
    async def run():
        resources = await owner.open_run(spec)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(resources.prepare_prompt('session-1', spec.model), 0.05)
        complete = await resources.finish('missing readiness')
        assert complete.settled and owner._active is None
        assert owner._runs[spec.run_id].admission_channel.task.done()
    asyncio.run(run())


def test_artifact_drift_refuses_before_native_effect(launch, tmp_path, monkeypatch):
    owner, spec, probe = setup(launch, tmp_path)
    probe.write_text('print("changed")')
    async def forbidden(*args, **kwargs):
        pytest.fail('changed artifact reached spawn')
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', forbidden)
    with pytest.raises(ValueError, match='artifact changed'):
        asyncio.run(owner.open_run(spec))
    assert owner._active is None


def test_artifact_drift_after_ready_refuses_prompt(launch, tmp_path):
    owner, spec, probe = setup(launch, tmp_path)
    async def run():
        resources = await owner.open_run(spec)
        try:
            assert json.loads(await resources.reader.readline()) == {'accepted': True}
            probe.write_text('changed after ready')
            with pytest.raises(ValueError, match='artifact changed'):
                await resources.prepare_prompt('session-1', spec.model)
        finally:
            complete = await resources.finish('artifact drift')
        assert complete.settled
    asyncio.run(run())


def test_channel_close_failure_never_becomes_settled(launch, tmp_path):
    owner, spec, _ = setup(launch, tmp_path)
    async def run():
        resources = await owner.open_run(spec)
        await resources.prepare_prompt('session-1', spec.model)
        channel = owner._runs[spec.run_id].admission_channel
        close, count = channel.close, []
        async def broken_once():
            count.append(1)
            await close()
            raise OSError('synthetic close failure')
        channel.close = broken_once
        complete = await resources.finish('close failed')
        assert len(count) == 1 and not complete.settled
        assert owner._active == spec.run_id
    asyncio.run(run())


def test_receipt_transport_close_failure_is_shared_and_never_retried(launch, tmp_path):
    owner, _, _ = setup(launch, tmp_path)
    async def run():
        channel = AcpAdmissionChannel(owner.tool_gate)
        class BrokenWriter:
            closes = 0
            waits = 0
            def close(self): self.closes += 1
            async def wait_closed(self):
                self.waits += 1
                await asyncio.sleep(0)
                raise OSError('first close failed')
        writer = channel.writer = BrokenWriter()
        try:
            results = await asyncio.gather(channel._close_writer(), channel._close_writer(),
                                           return_exceptions=True)
            assert all(isinstance(result, OSError) for result in results)
            with pytest.raises(OSError, match='first close failed'):
                await channel.close()
            assert writer.closes == writer.waits == 1
        finally:
            channel.close_unstarted()
    asyncio.run(run())
