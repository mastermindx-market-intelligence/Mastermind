"""Real native owner-channel tests, without a tool/provider execution claim."""
import asyncio
import dataclasses
import hashlib
import json
import time
from pathlib import Path

import pytest

from test_acp_native_startup import launch  # reuse the actual clean native launch fixture
from integrations.acp_worker.native import AcpNativeProcessOwner
from integrations.acp_worker.tool_admission import AcpAdmissionChannel, AcpNativeToolGate, AcpObservedTool

PROBE = '''
import json, os, socket, sys, hashlib
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
    if mode == 'overlay-spoof':
        message['attempt_overlay']['env']['MMX_ACP_JOB_ID'] = 'other-job'
    if seed['schema'] == 'mastermind.acp_tools_ready/v2' and mode != 'legacy-echo':
        overlay = seed['attempt_overlay']
        message['attempt_overlay_sha256'] = hashlib.sha256(
            json.dumps(overlay, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if mode in ('capture', 'legacy-echo', 'overlay-spoof'):
        print(json.dumps({'schema':seed['schema'],
          'attempt':seed.get('attempt_overlay'),
          'proof_present': 'attempt_overlay_sha256' in message,
          'ambient_attempt_keys': sorted(k for k in os.environ
            if k.startswith('MMX_ACP_') and k != 'MMX_ACP_ATTEST_FD'),
          'inherited_secret': os.environ.get('OPENAI_API_KEY')}), flush=True)
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

def _trusted_attempt_overlay(spec, workspace):
    """Synthetic equivalent of the installed packet's six-field projection."""
    return {
        "cwd": str(workspace),
        "env": {
            "MMX_ACP_WORKSPACE_PATH": str(workspace),
            "MMX_ACP_WORKSPACE_BASE_SHA": spec.expected_base_sha,
            "MMX_ACP_RUN_ID": spec.run_id,
            "MMX_ACP_JOB_ID": spec.job_id,
            "MMX_ACP_WORKER_ID": spec.worker_id,
            "MMX_ACP_DEADLINE_MS": str(int(time.time() * 1000)
                                         + int(spec.timeout_seconds * 1000)),
        },
    }


def _overlay_owner(launch, tmp_path, mode="capture", overlay_change=None):
    owner, spec, _ = setup(launch, tmp_path, mode)
    profile = owner.profile

    def overlay(spec, workspace, run_dir):
        assert workspace == spec.workspace_path.resolve(strict=True)
        assert run_dir == spec.run_dir.resolve(strict=True)
        value = _trusted_attempt_overlay(spec, workspace)
        if overlay_change:
            overlay_change(value)
        return value

    return AcpNativeProcessOwner(
        profile,
        environment_loader=lambda: {},
        tool_gate=owner.tool_gate,
        launch_argv_builder=lambda _spec, _workspace, _run: profile.argv,
        attempt_overlay_builder=overlay,
    ), spec


def test_v2_child_receives_exact_attempt_on_original_inherited_socket(launch, tmp_path, monkeypatch):
    owner, spec = _overlay_owner(launch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-must-not-reach-child")
    monkeypatch.setenv("HOME", str(tmp_path / "outside-home"))

    async def scenario():
        resources = await owner.open_run(spec)
        try:
            observed = json.loads(await asyncio.wait_for(resources.reader.readline(), 2))
            assert observed["schema"] == "mastermind.acp_tools_ready/v2"
            assert observed["attempt"]["cwd"] == str(spec.workspace_path.resolve(strict=True))
            assert observed["attempt"]["env"]["MMX_ACP_JOB_ID"] == spec.job_id
            assert set(observed["attempt"]["env"]) == {
                "MMX_ACP_WORKSPACE_PATH", "MMX_ACP_WORKSPACE_BASE_SHA",
                "MMX_ACP_RUN_ID", "MMX_ACP_JOB_ID", "MMX_ACP_WORKER_ID",
                "MMX_ACP_DEADLINE_MS",
            }
            assert observed["proof_present"] is True
            assert observed["ambient_attempt_keys"] == []
            assert observed["inherited_secret"] is None
            assert "OPENAI_API_KEY" not in observed["attempt"]["env"]
            receipt = await asyncio.wait_for(resources.prepare_prompt("session-1", spec.model), 2)
            assert receipt.matches(spec, resources.process_ref, "session-1", spec.model)
            assert json.loads(await resources.reader.readline()) == {"accepted": True}
        finally:
            completion = await resources.finish(None)
        assert completion.settled and owner._active is None
        assert not owner._identity_matches(resources.process_ref)

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ("legacy-echo", "overlay-spoof"))
def test_v2_rejects_legacy_or_forged_child_ack(launch, tmp_path, mode):
    owner, spec = _overlay_owner(launch, tmp_path, mode)
    async def scenario():
        resources = await owner.open_run(spec)
        try:
            observed = json.loads(await asyncio.wait_for(resources.reader.readline(), 2))
            assert observed["schema"] == "mastermind.acp_tools_ready/v2"
            with pytest.raises(ValueError, match="readiness identity refused"):
                await asyncio.wait_for(resources.prepare_prompt("session-1", spec.model), 2)
        finally:
            completion = await resources.finish("v2 invalid ack")
        assert await asyncio.wait_for(resources.reader.read(), 2) == b""
        assert completion.settled and owner._active is None
    asyncio.run(scenario())


@pytest.mark.parametrize("variant", (
    "foreign_job", "extra_env", "foreign_workspace", "expired", "write_authority",
))
def test_v2_refuses_widened_owner_overlay_before_any_process(
    launch, tmp_path, monkeypatch, variant,
):
    def change(value):
        if variant == "foreign_job":
            value["env"]["MMX_ACP_JOB_ID"] = "foreign"
        elif variant == "extra_env":
            value["env"]["OPENAI_API_KEY"] = "forbidden"
        elif variant == "foreign_workspace":
            value["cwd"] = str(tmp_path)
        elif variant == "expired":
            value["env"]["MMX_ACP_DEADLINE_MS"] = "1000"

    owner, spec = _overlay_owner(launch, tmp_path, overlay_change=change)
    if variant == "write_authority":
        spec = dataclasses.replace(spec, authorities=("READ", "WRITE_BRANCH"))
    async def forbidden(*args, **kwargs):
        pytest.fail("foreign ACP Attempt reached native spawn")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    with pytest.raises(ValueError, match="ACP Attempt channel"):
        asyncio.run(owner.open_run(spec))
    assert owner._active is None


def test_attempt_channel_cannot_be_constructed_without_existing_private_gate(launch):
    profile, spec = launch
    with pytest.raises(ValueError, match="requires fixed private"):
        AcpNativeProcessOwner(
            profile, environment_loader=lambda: {},
            attempt_overlay_builder=lambda *_: _trusted_attempt_overlay(spec, spec.workspace_path),
        )
