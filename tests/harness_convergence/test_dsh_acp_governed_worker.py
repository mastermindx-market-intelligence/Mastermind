"""Actual pinned DSH + grant profile + MCP process; synthetic admission only.

An absent external supply skips this proof. A supplied but altered closure fails.
No installed Executive/provider/confinement proof is implied by these tests.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import pytest

from test_dsh_acp_worker import _binary, _git
from control_plane.worker_execution_contract import WorkerLaunchSpec, WorkerRunStatus
from control_plane.executive_worker_broker import BrokerEffectUnknownError
from control_plane.executive_supervisor import worker_result_schema
from integrations.acp_worker.adapter import AcpWorkerAdapter
from integrations.acp_worker.native import AcpNativeProcessOwner, AcpNativeProfile
from integrations.acp_worker.tool_admission import AcpNativeToolGate, AcpObservedTool
from integrations.acp_worker.turn import AcpProfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def supply():
    value = os.environ.get('MMX_DSH_GOVERNED_ACP_SUPPLY')
    if value is None:
        pytest.skip('governed DSH supply absent: real useful journey NOT executed')
    root = Path(value).resolve(strict=True)
    manifest = json.loads((root / 'supply-manifest.json').read_text())
    assert manifest['donor'] == '4878cdabd87d4041bdaff61d04c966883b9fd07a'
    assert manifest['profile_head'] == '4159c403cf63bac8bd18138fa232911589afe06f'
    assert manifest['r4_patch'] == '243ec445db513db3bb9ff0cad05bc70550df972a785b8af1546d89c055cadc1f'
    assert manifest['profile_artifact'] == 'c77814901495ebb3131d28b4968bd3f1cce3f39233e1c0cb580de5a7b9f9106c'
    for name, sha in manifest['files'].items():
        assert (root / name).resolve().is_relative_to(root)
        assert digest(root / name) == sha, name
    for name, sha in manifest['fixture_input'].items():
        assert digest(root / 'fixture-input' / name) == sha
    sources = Path(__file__).resolve().parents[2] / 'experiments/harness_convergence/dsh_worker'
    expected_sources = {'governed_acp_fixture.mjs','scoped_profile.mjs',
                        'scoped_profile.test.mjs','build_governed_fixture.cjs'}
    assert set(manifest['fixture_sources']) == expected_sources
    for name, sha in manifest['fixture_sources'].items():
        assert digest(sources / name) == sha, 'fixture source changed: rebuild supplied bundle'
    assert digest(root / 'profile1060.mjs') == manifest['profile_artifact']
    assert digest(root / 'governed-acp-mount.patch') == manifest['r4_patch']
    node = Path(manifest['node']).resolve(strict=True)
    assert digest(node) == manifest['node_sha256']
    return root, manifest, node


def test_real_profile_scope_compatibility_and_adverse_controls():
    root, _, node = supply()
    result = subprocess.run([str(node),'--test',str(root/'runtime/build/scoped_profile.test.mjs')],
        env={'PATH':'/usr/bin:/bin','MMX_GOVERNED_INPUT':str(root)},
        capture_output=True,text=True,timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '# pass 2' in result.stdout and '# fail 0' in result.stdout


async def exercise(tmp_path, mode='ok', *, cancel=False, model='fixture-model'):
    root, manifest, node = supply()
    tmp_path = tmp_path.resolve()
    workspace, run_dir = tmp_path / 'workspace', tmp_path / 'run'
    workspace.mkdir(mode=0o700); run_dir.mkdir(mode=0o700)
    (run_dir / 'input').mkdir(mode=0o700)
    _git(workspace, 'init', '--template=', '-q')
    _git(workspace, '-c', 'user.name=Governed Fixture', '-c', 'user.email=fixture@example.invalid',
         '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'fixture')
    base = _git(workspace, 'rev-parse', 'HEAD')
    schema = run_dir / 'input/result.schema.json'
    schema.write_text(json.dumps(worker_result_schema(
        job_id='GOVERNED-JOB', run_id='governed-run', worker_id='governed-worker')))
    projection = json.loads((root / 'projection.json').read_text())
    tools = tuple(AcpObservedTool('mcp__granted__'+tool['name'], hashlib.sha256(json.dumps(tool,
        sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()) for tool in projection['tools'])
    bundle = root / 'runtime/build/governed_acp_fixture.mjs'
    gate = AcpNativeToolGate(digest(root / 'projection.json'), manifest['profile_artifact'], tools,
        tuple((str(root / path), manifest['files'][path]) for path in
              ('runtime/build/governed_acp_fixture.mjs','runtime/package.json','profile1060.mjs',
               'projection.json','fixture-config.json','stdio-fixture-server.mjs')))
    owner = AcpNativeProcessOwner(AcpNativeProfile('dsh-governed-fixture', _binary(node),
        (str(node),str(bundle)),private_startup=True,
        allowed_environment_keys=('PATH','MMX_GOVERNED_INPUT','MMX_GOVERNED_BEHAVIOR')),
        environment_loader=lambda:{'PATH':'/usr/bin:/bin','MMX_GOVERNED_INPUT':str(root),
                                   'MMX_GOVERNED_BEHAVIOR':mode}, tool_gate=gate)
    adapter = AcpWorkerAdapter(AcpProfile('deepseek-harness-acp','0.0.1',model_option_provider='fixture'),
                              inspector=owner.inspector,open_run=owner.open_run)
    spec = WorkerLaunchSpec('governed-run','GOVERNED-JOB','governed-worker',workspace,run_dir,
        'Read memo.txt, search its nonce, and report the actual read/search results as JSON.', schema,
        authorities=('READ','RESEARCH'),model=model,timeout_seconds=12,cancel_grace_seconds=4,
        expected_base_sha=base,expected_worker_uid=os.geteuid(),expected_worker_gid=os.getegid())
    event_path = root / 'fixture-input/events.jsonl'
    previous = len(event_path.read_text().splitlines())
    begin = time.monotonic()
    ref = await adapter.start(spec)
    receipt = None
    unknown = None
    try:
        if cancel:
            for _ in range(300):
                if b'GOVERNED_MODEL_CALL 2' in Path(ref.stderr_path).read_bytes(): break
                await asyncio.sleep(0.02)
            else: raise AssertionError('governed model did not enter hanging turn')
            await asyncio.wait_for(adapter.cancel(ref,'governed fixture cancellation'), 15)
            receipt = adapter._runs[spec.run_id].receipt
        else:
            try:
                receipt = await asyncio.wait_for(adapter.collect_result(ref), 20)
            except BrokerEffectUnknownError as exc:
                unknown = exc
    finally:
        # On an unexpected assertion/timeout, settle through the original owner.
        if owner._active is not None:
            pending = adapter._runs[spec.run_id].task
            if pending is not None and not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
        assert owner._active is None
        assert adapter.unsettled_tasks == ()
        assert not owner._identity_matches(ref)
    events = [json.loads(line) for line in event_path.read_text().splitlines()[previous:]]
    pids = {event['pid'] for event in events if event['event']=='start'}
    for pid in pids:
        with pytest.raises(ProcessLookupError): os.kill(pid, 0)
    assert not any(event['event'] in {'ungranted-write','resource-read'} for event in events)
    assert all(event.get('nodeOptions') is None and event.get('ambient') is None
               for event in events if event['event']=='start')
    assert _git(workspace,'status','--porcelain') == ''
    for name, sha in manifest['fixture_input'].items(): assert digest(root/'fixture-input'/name)==sha
    return receipt, unknown, events, ref, adapter, time.monotonic()-begin


def test_real_governed_read_search_returns_common_worker_result(tmp_path):
    receipt, unknown, events, ref, adapter, elapsed = asyncio.run(exercise(tmp_path))
    assert unknown is None and receipt is not None
    assert receipt.result.status is WorkerRunStatus.SUCCEEDED
    envelope = receipt.result.structured_output
    assert envelope['job_id']=='GOVERNED-JOB' and envelope['run_id']==ref.run_id
    assert envelope['worker_id']=='governed-worker' and envelope['status']=='COMPLETED'
    assert envelope['errors']==envelope['validations']==()
    result = json.loads(envelope['summary'])
    root, _, _ = supply()
    nonce = json.loads((root/'fixture-input/fixture.json').read_text())['nonce']
    assert result['read']['nonce']==nonce and result['search']['nonce']==nonce
    assert result['read']['text']==(root/'fixture-input/memo.txt').read_text()
    assert result['read']['sha256']==digest(root/'fixture-input/memo.txt')
    assert len(result['search']['matches'])==2 and result['model_calls']==3
    evidence=receipt.result.usage['acp_tool_observation']
    assert evidence['observations']['calls']==evidence['observations']['terminal']==2
    assert evidence['session_id']==receipt.result.provider_session_id
    assert [e['event'] for e in events if e['event'] in {'read','search'}]==['read','search']
    assert elapsed < 20


@pytest.mark.parametrize('mode', ['failed-tool','revoked'])
def test_failed_actual_tool_result_is_preserved_without_forbidden_body(tmp_path,mode):
    receipt,unknown,events,ref,_,_=asyncio.run(exercise(tmp_path,mode))
    assert unknown is None and receipt.result.status is WorkerRunStatus.SUCCEEDED
    envelope=receipt.result.structured_output
    assert envelope['status']=='FAILED' and envelope['errors']
    output=json.loads(envelope['summary'])
    assert output['read' if mode=='failed-tool' else 'search']['error'] is True
    assert not any(e['event']=='search' for e in events)
    if mode=='failed-tool': assert not any(e['event']=='read' for e in events)
    updates=[json.loads(line) for line in Path(ref.stdout_path).read_text().splitlines()]
    assert any(row.get('params',{}).get('update',{}).get('status')=='failed' for row in updates)


@pytest.mark.parametrize('mode',['schema-mismatch','source-mismatch'])
def test_discovery_or_source_drift_prevents_prompt(tmp_path,mode):
    receipt,unknown,events,ref,_,_=asyncio.run(exercise(tmp_path,mode))
    assert receipt is None or receipt.result.status is not WorkerRunStatus.SUCCEEDED
    assert b'GOVERNED_MODEL_CALL' not in Path(ref.stderr_path).read_bytes()
    assert not any(e['event'] in {'read','search'} for e in events)


def test_new_donor_invalid_result_is_not_success(tmp_path):
    receipt,unknown,*_=asyncio.run(exercise(tmp_path,'invalid-result'))
    assert unknown is None and receipt.result.status is WorkerRunStatus.INVALID_RESULT
    assert receipt.result.structured_output is None


@pytest.mark.parametrize('mode',['wrong-result-identity','invalid-result-status'])
def test_canonical_result_identity_and_status_are_not_self_asserted(tmp_path,mode):
    receipt,unknown,*_=asyncio.run(exercise(tmp_path,mode))
    assert unknown is None and receipt.result.status is WorkerRunStatus.INVALID_RESULT
    assert receipt.result.structured_output is None


def test_new_donor_cancel_settles_original_generation(tmp_path):
    receipt,unknown,*_=asyncio.run(exercise(tmp_path,'hang',cancel=True))
    assert unknown is None and receipt.result.status is WorkerRunStatus.CANCELLED


def test_new_donor_model_mismatch_prevents_prompt(tmp_path):
    receipt,unknown,events,ref,_,_=asyncio.run(exercise(tmp_path,model='unavailable-model'))
    assert receipt is None or receipt.result.status is not WorkerRunStatus.SUCCEEDED
    assert b'GOVERNED_MODEL_CALL' not in Path(ref.stderr_path).read_bytes()
    assert not any(e['event'] in {'read','search'} for e in events)
