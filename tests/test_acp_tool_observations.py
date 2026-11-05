"""Native SDK callbacks and common WorkerResult with private owner evidence."""
import asyncio
import dataclasses
import hashlib
import os
from pathlib import Path

import pytest

acp = pytest.importorskip("acp", reason="optional ACP SDK absent; tool observations NOT qualified")

from test_acp_native_startup import launch
from integrations.acp_worker.native import AcpNativeProcessOwner
from integrations.acp_worker.adapter import AcpWorkerAdapter
from integrations.acp_worker.turn import AcpProfile
from integrations.acp_worker.tool_admission import AcpNativeToolGate, AcpObservedTool
from control_plane.executive_worker_broker import BrokerEffectUnknownError
from control_plane.worker_execution_contract import WorkerRunStatus


def native(launch, mode):
    profile, spec = launch
    peer = Path(__file__).with_name('fixtures') / 'acp_governed_peer.py'
    profile = dataclasses.replace(profile, argv=(profile.argv[0], str(peer), mode),
        allowed_environment_keys=('PYTHONPATH', 'PYTHONDONTWRITEBYTECODE', 'PYTHONNOUSERSITE'))
    spec = dataclasses.replace(spec, model='model-a', timeout_seconds=2)
    digest = hashlib.sha256(peer.read_bytes()).hexdigest()
    gate = AcpNativeToolGate('a' * 64, digest,
        (AcpObservedTool('mcp__granted__read_file', 'b' * 64),), ((str(peer), digest),))
    owner = AcpNativeProcessOwner(profile, tool_gate=gate, environment_loader=lambda: {
        'PYTHONPATH': str(Path(acp.__file__).resolve().parents[1]),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'})
    adapter = AcpWorkerAdapter(AcpProfile('gate-peer', '1'), inspector=owner.inspector, open_run=owner.open_run)
    return owner, adapter, spec


@pytest.mark.parametrize('mode', ['ok', 'failed'])
def test_native_ordered_observations_reach_common_result(launch, mode):
    owner, adapter, spec = native(launch, mode)
    async def run():
        ref = await adapter.start(spec)
        result = (await asyncio.wait_for(adapter.collect_result(ref), 5)).result
        assert result.status is WorkerRunStatus.SUCCEEDED
        assert dict(result.structured_output) == {'answer': 42}
        observed = result.usage['acp_tool_observation']
        assert observed['session_id'] == 'governed-session'
        assert observed['projection_sha256'] == 'a' * 64
        assert observed['admitted_tools'][0]['name'] == 'mcp__granted__read_file'
        assert observed['observations']['calls'] == observed['observations']['terminal'] == 1
        assert owner._active is None and adapter.unsettled_tasks == ()
        assert not owner._identity_matches(ref)
    asyncio.run(run())


@pytest.mark.parametrize('mode', ['denied', 'orphan', 'duplicate-start', 'duplicate-result', 'pending', 'bad-ready', 'late'])
def test_native_violation_never_becomes_success(launch, mode):
    owner, adapter, spec = native(launch, mode)
    async def run():
        ref = await adapter.start(spec)
        try:
            result = (await asyncio.wait_for(adapter.collect_result(ref), 6)).result
            assert result.status is not WorkerRunStatus.SUCCEEDED
            assert result.structured_output is None
        except BrokerEffectUnknownError:
            assert adapter._quarantined
        assert owner._active is None and adapter.unsettled_tasks == ()
        assert not owner._identity_matches(ref)
        if mode == 'bad-ready':
            assert b'PROMPT' not in Path(ref.stderr_path).read_bytes()
    asyncio.run(run())


@pytest.mark.parametrize('key,value', [('content', []), ('content', None), ('locations', []),
    ('rawOutput', {}), ('unknownAuthority', 'WRITE')])
def test_falsey_or_extra_tool_fields_refuse(launch, key, value):
    owner, adapter, spec = native(launch, 'ok')
    async def run():
        ref = await adapter.start(spec)
        await adapter.collect_result(ref)
        turn = adapter._runs[ref.run_id].turn
        turn._phase = 'prompt'  # isolated validator probe after settled real admission
        data = {'sessionUpdate': 'tool_call', 'toolCallId': 'new', 'title': 'mcp__granted__read_file',
                'kind': 'other', 'status': 'in_progress', 'rawInput': {}, key: value}
        assert turn.validate_update(data) == 'ACP_TOOL_CALL_REFUSED'
    asyncio.run(run())
