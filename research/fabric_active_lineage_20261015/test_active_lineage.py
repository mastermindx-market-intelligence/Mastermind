import importlib.util
import builtins
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess

import pytest

HERE = Path(__file__).parent
EXT = Path.home()/'.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
sys.path.insert(0, str(EXT))
import artifact_production
import artifact_delivery
import remote_sub_helpers


def load(name, file):
    source = Path(os.environ.get('LINEAGE_SOURCE_DIR', str(HERE/'candidate')))
    spec = importlib.util.spec_from_file_location(name, source/file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = load('active_lineage_candidate', 'fabric_task.py')
observation = load('scope_diagnostic_candidate', 'run_observation_delivery.py')


@pytest.fixture
def fixture(monkeypatch):
    base = Path.home()/'.mastermind/agent-evidence/fabric-active-lineage-inert'
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        root = Path(directory)
        logs = root/'state/remote_sub'
        logs.mkdir(parents=True, mode=0o700)
        packet = root/'packet.txt'
        packet.write_text(artifact_production.encode_packet('Bounded test artifact', root='root-v1', parent='parent-v1', run_id='worker-v1', names=['answer.txt'], support_digest='a'*64))
        acquired = root/'acquired.txt'
        acquired.write_text('LEASE=012345abcdef ACCOUNT=account-v1\n')
        log = logs/'worker-v1.log'
        prefix = '2026-10-15T22:00Z [remote_sub id=worker-v1 host=ubuntu2] '
        before = ['RUN_RESERVED explicit=1', 'LEASE_OK pool=glm', 'SUPPORT_VERSION_READY digest='+('a'*64)+' policy='+('b'*64)]
        log.write_text(''.join(prefix+event+'\n' for event in before))
        for file in (packet, acquired, log):
            file.chmod(0o600)
        kw = dict(run_id='worker-v1', root='root-v1', parent='parent-v1', host='ubuntu2', mode='glm', model='glm-5.3-flash', support_digest='a'*64, launch_lease_id='012345abcdef', launch_account='account-v1')
        remote_sub_helpers.record_launch_binding(log, packet, acquired, **kw)
        with log.open('a') as stream:
            stream.write(prefix+'LAUNCH stdout=original rc_file=original cwd=~\n')
            stream.write(prefix+'LAUNCH_ATTEMPT attempt=1\n')
            stream.write(prefix+'POLL 1/7200 elapsed=0 file=original\n')
        monkeypatch.setattr(adapter, 'HERE', root)
        monkeypatch.setattr(adapter.pool_ledger, 'read_acceptance', lambda *a, **k: pytest.fail('active path read terminal ledger'))
        monkeypatch.setattr(adapter.pool_ledger, 'read_execution_identity', lambda *a, **k: pytest.fail('active path read terminal ledger'))
        yield log, packet, acquired, prefix, kw


def status():
    return adapter.inspect_run('worker-v1')


def rewrite_binding(log, transform):
    lines = log.read_text().splitlines(keepends=True)
    index = next(i for i, line in enumerate(lines) if ' LAUNCH_BINDING ' in line)
    prefix, raw = lines[index].split(' LAUNCH_BINDING ', 1)
    record = json.loads(raw)
    transform(record)
    lines[index] = prefix+' LAUNCH_BINDING '+json.dumps(record)+'\n'
    log.write_text(''.join(lines))


def unverified(value):
    assert value['root_id'] is None and value['parent_run_id'] is None
    assert value['accepted'] is None and value['acceptance_state'] == 'UNVERIFIED'


def test_actual_producer_binding_projects_only_correlation(fixture):
    result = status()
    unverified(result)
    lineage = result['controller_lineage']
    assert lineage['root_id'] == 'root-v1' and lineage['parent_run_id'] == 'parent-v1'
    assert lineage['state'] == 'RECORDED_PRE_LAUNCH'
    assert lineage['is_authentication'] is False
    assert result['accepted'] is None and result['acceptance_state'] == 'UNVERIFIED'
    assert result['state'] == 'ACTIVE_OR_WAITING'
    assert result['controller_observation']['worker_state'] == 'UNKNOWN'
    assert result['controller_observation']['retry_authorized'] is False


def test_native_facade_does_not_promote_active_correlation(fixture):
    result=status()
    # A partially delivered file is not terminal, verified result evidence.
    result.update(result_available=True,result_bytes=12)
    facade=(HERE.parents[1]/'integrations/studio_direct_mcp/fabric-backend.mjs').as_uri()
    code='''
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const {createFabricFacade}=await import(process.argv[1]);
const status=JSON.parse(readFileSync(0,'utf8'));
let calls=0;
const engine={async callTool(){calls++;return {content:[{type:'text',text:
 'Process started with PID 123 (shell: /bin/zsh)\\nInitial output:\\n'+JSON.stringify(status)+'\\nMMX_FABRIC_EXIT=0\\n'}]};}};
const facade=createFabricFacade(engine,{adapterPath:'/host/fabric_task.py',python:'python3',workerCwd:'~'});
const unwrap=r=>r.structuredContent??JSON.parse(r.content[0].text);
const args={run_id:'worker-v1',root_id:'root-v1'};
const observed=unwrap(await facade.call('fabric_status',args));
assert.equal(observed.root_verified,false);
assert.equal(observed.status.controller_lineage.root_id,'root-v1');
const retained=unwrap(await facade.call('fabric_result',args));
assert.equal(retained.error,'ROOT_UNVERIFIED');
assert.equal(calls,2);
'''
    checked=subprocess.run(['node','--input-type=module','-e',code,facade],input=json.dumps(result),text=True,capture_output=True,timeout=10)
    assert checked.returncode==0,checked.stderr


def test_absent_binding_does_not_invent_plain_packet_lineage(fixture):
    log = fixture[0]
    log.write_text(''.join(line for line in log.read_text().splitlines(keepends=True) if ' LAUNCH_BINDING ' not in line))
    unverified(status())


@pytest.mark.parametrize('key,value', [('root',''),('parent',None),('root',[]),('run_id','foreign-run'),('host','ubuntu3'),('phase','STARTED'),('source','caller'),('pool','bailian'),('mode','grok'),('lease_id','bad'),('packet_sha256','bad'),('support_digest','f'*64),('acquire_response_sha256',False)])
def test_invalid_or_mismatched_binding_stays_unverified(fixture,key,value):
    rewrite_binding(fixture[0], lambda r:r.__setitem__(key,value))
    unverified(status())


def test_partial_binding_stays_unverified(fixture):
    rewrite_binding(fixture[0], lambda r:r.pop('parent'))
    unverified(status())


def test_duplicate_binding_stays_unverified(fixture):
    log=fixture[0]
    line=next(line for line in log.read_text().splitlines(keepends=True) if ' LAUNCH_BINDING ' in line)
    with log.open('a') as stream: stream.write(line)
    unverified(status())


def test_duplicate_json_key_stays_unverified(fixture):
    log=fixture[0]
    log.write_text(log.read_text().replace('LAUNCH_BINDING {','LAUNCH_BINDING {"root":"other",',1))
    unverified(status())


def test_binding_after_launch_stays_unverified(fixture):
    log=fixture[0]
    lines=log.read_text().splitlines(keepends=True)
    binding=next(line for line in lines if ' LAUNCH_BINDING ' in line)
    lines.remove(binding);lines.append(binding)
    log.write_text(''.join(lines))
    unverified(status())


def test_partial_log_stays_unverified(fixture):
    log=fixture[0];log.write_bytes(log.read_bytes().rstrip(b'\n'))
    unverified(status())


def test_misordered_original_events_stay_unverified(fixture):
    log=fixture[0];lines=log.read_text().splitlines(keepends=True)
    lines[0],lines[2]=lines[2],lines[0]
    log.write_text(''.join(lines));unverified(status())


@pytest.mark.parametrize('kind',['symlink','hardlink','mode','group_write','directory_mode'])
def test_unsafe_source_stays_unverified(fixture,kind):
    log=fixture[0]
    if kind=='symlink':
        target=log.with_name('original');log.rename(target);log.symlink_to(target)
    elif kind=='hardlink':os.link(log,log.with_name('alias'))
    elif kind=='mode':log.chmod(0o666)
    elif kind=='group_write':log.chmod(0o660)
    else:log.parent.chmod(0o775)
    unverified(status())


def test_changed_local_read_stays_unverified(fixture,monkeypatch):
    original=artifact_delivery.local_file
    count=0
    def racing(path,limit):
        nonlocal count
        count+=1
        data=original(path,limit)
        return data if count==1 else data+b'changed'
    monkeypatch.setattr(artifact_delivery,'local_file',racing)
    unverified(status())


@pytest.mark.parametrize('event',['EFFECT_UNKNOWN original','LAUNCH_FAILED original','OBSERVATION_REFUSED original'])
def test_post_binding_uncertainty_is_not_projected(fixture,event):
    log=fixture[0]
    with log.open('a') as stream:stream.write(fixture[3]+event+'\n')
    result=status();unverified(result)
    assert result['controller_lineage']['state']=='UNVERIFIED'


def test_oversized_log_cannot_hide_conflicting_binding(fixture,monkeypatch):
    log=fixture[0]
    original=log.read_bytes()
    with log.open('a') as stream:
        stream.write(fixture[3]+'LAUNCH_BINDING {"root":"other"}\n')
    monkeypatch.setattr(adapter,'MAX_LOG_BYTES',len(original))
    assert adapter._active_lineage_projection('worker-v1',original)=={'controller_lineage':{'state':'UNVERIFIED'}}


def test_missing_optional_evidence_reader_stays_unverified(fixture,monkeypatch):
    original=builtins.__import__
    def unavailable(name,*args,**kwargs):
        if name=='artifact_delivery':raise ImportError('evidence reader unavailable')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',unavailable)
    result=status();unverified(result)
    assert result['controller_lineage']['state']=='UNVERIFIED'


def test_existing_producer_rejects_root_packet_mismatch(fixture):
    log,packet,acquired,prefix,kw=fixture
    log.write_text(prefix+'RUN_RESERVED explicit=1\n')
    with pytest.raises(ValueError,match='launch_binding_packet_mismatch'):
        remote_sub_helpers.record_launch_binding(log,packet,acquired,**(kw|{'root':'foreign-root'}))


def test_effect_unknown_does_not_get_active_projection(fixture,monkeypatch):
    log=fixture[0]
    with log.open('a') as stream:stream.write(fixture[3]+'LEASE_PRESERVED effect_unknown=1\n')
    monkeypatch.setattr(adapter,'_active_lineage_projection',lambda *a:pytest.fail('uncertain effect projected active'))
    result=status();assert result['state']=='EFFECT_UNKNOWN';unverified(result)


def test_unknown_observation_scope_reports_exact_reason_without_transport(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(observation,'observe',lambda *a:pytest.fail('unadmitted transport'))
    destination=tmp_path/'not-created'
    rc=observation.main(['synthetic-unadmitted','--root','root-v1','--destination',str(destination)])
    assert rc==75 and not destination.exists()
    assert json.loads(capsys.readouterr().out)=={'state':'REFUSED','reason':'observation_scope_not_admitted'}


def test_wrong_root_is_same_scope_refusal(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(observation,'observe',lambda *a:pytest.fail('wrong-root transport'))
    rc=observation.main([next(iter(observation.SCOPES)),'--root','wrong-root','--destination',str(tmp_path/'unused')])
    assert rc==75
    assert json.loads(capsys.readouterr().out)['reason']=='observation_scope_not_admitted'


def test_other_failure_retains_generic_refusal(tmp_path,monkeypatch,capsys):
    rid=next(iter(observation.SCOPES))
    def failure(*a):raise ValueError('unrelated')
    monkeypatch.setattr(observation,'observe',failure)
    rc=observation.main([rid,'--root',observation.SCOPES[rid]['root'],'--destination',str(tmp_path/'unused')])
    assert rc==75
    assert json.loads(capsys.readouterr().out)['reason']=='original_run_observation_unconfirmed'
