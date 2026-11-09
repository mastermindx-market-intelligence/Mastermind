"""Private inert fixtures; no broker/network/provider access."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
    return m


@pytest.fixture
def env(tmp_path,monkeypatch):
    candidate=Path(os.environ['OPERATOR_BINDING_CANDIDATE'])
    x=Path(os.environ['FABRIC_INSTALLED_EXT'])
    monkeypatch.syspath_prepend(str(x))
    d=load('artifact_delivery',candidate/'artifact_delivery.py')
    load('fabric_operator_owner',candidate/'fabric_operator_owner.py')
    c=load('original_delivery_collector',candidate/'original_delivery_collector.py')
    m=load('operator_stdout_delivery',candidate/'operator_stdout_delivery.py')
    monkeypatch.setattr(d,'HERE',x)
    monkeypatch.setattr(d,'DESTINATION_ROOT',tmp_path)
    destination=tmp_path/'collection'
    monkeypatch.setattr(m,'DESTINATION',destination)
    monkeypatch.setenv('CODEX_THREAD_ID',m.ROOT)
    monkeypatch.delenv('POOL_ORCHESTRATOR_ID',raising=False)
    monkeypatch.setattr(d,'transport',lambda *a,**k:pytest.fail('unexpected transport'))
    monkeypatch.setattr(m.OperatorOwner,'original_delivery_binding',lambda *a,**k:pytest.fail('unexpected actual broker'))
    return m,d,c,destination


def process(m,stdout):
    cleanup=dict(identity_verified=True,census_proven=True,residual_count=0,status='not_needed',error_code=None)
    for stem in ('stdin_delivery','stdout_capture','stderr_capture'):
        cleanup[stem+'_complete']=True;cleanup[stem+'_error']=None
    return dict(schema='mastermind.local_owned_process_receipt.v1',label=m.RUN_ID,
        returncode=0,timed_out=False,pid=1234,pgid=1234,stdout_bytes=len(stdout),stderr_bytes=0,
        stdout_sha256=m.sha(stdout),stdout_truncated=False,stderr_truncated=False,runtime_failure_code=None,
        started_at='2026-10-13T00:00:00Z',ended_at='2026-10-13T00:00:01Z',cleanup=cleanup)


def response(m,stdout=b'bounded original result',patch=None):
    p=process(m,stdout)
    if patch:patch(p)
    blobs=dict(rc=b'0\n',process=m.canonical(p),stdout=stdout)
    return m.canonical(dict(schema=m.SCHEMA,request_sha256=m.sha(m.canonical(m.REQUEST)),state='READ',
        files={k:dict(bytes=len(v),sha256=m.sha(v),data_base64=base64.b64encode(v).decode()) for k,v in blobs.items()},artifacts=[]))


def test_multichunk_receipt_consumed_by_existing_reader_and_no_replay(env,monkeypatch):
    m,d,c,dest=env
    stdout=b'x'*(d.reader.MAX_FILE+13)
    monkeypatch.setattr(m,'qualify',lambda _:dict(ssh_alias='inert'))
    calls=[]
    monkeypatch.setattr(d,'transport',lambda *args:calls.append(args) or response(m,stdout))
    result=m.collect(m.RUN_ID,str(dest))
    assert result['state']=='COMPLETE' and result['delivery_verified'] and result['worker_terminal_proof']
    assert result['children_settlement']==result['lease_settlement']=='UNKNOWN'
    assert not result['original_operation_mutated'] and result['acceptance']=='NOT_RECORDED'
    raw=(dest/'receipt.json').read_bytes()
    assert c.read_collection(dest/'receipt.json',expected_sha256=m.sha(raw),run_id=m.RUN_ID,root=m.ROOT,parent=m.PARENT)==stdout
    with pytest.raises(FileExistsError):m.collect(m.RUN_ID,str(dest))
    assert len(calls)==1


@pytest.mark.parametrize('identity,pool',[(None,None),('wrong',None),('root','wrong')])
def test_wrong_caller_precedes_qualification_and_reservation(env,monkeypatch,identity,pool):
    m,d,c,dest=env
    if identity is None:monkeypatch.delenv('CODEX_THREAD_ID')
    else:monkeypatch.setenv('CODEX_THREAD_ID',m.ROOT if identity=='root' else identity)
    if pool:monkeypatch.setenv('POOL_ORCHESTRATOR_ID',pool)
    monkeypatch.setattr(m,'qualify',lambda _:pytest.fail('qualification must not run'))
    with pytest.raises(ValueError,match='root_required'):m.collect(m.RUN_ID,str(dest))
    assert not dest.exists()


def test_wrong_destination_precedes_qualification(env,monkeypatch):
    m,d,c,dest=env
    monkeypatch.setattr(m,'qualify',lambda _:pytest.fail('qualification must not run'))
    with pytest.raises(ValueError,match='destination_not_admitted'):m.collect(m.RUN_ID,str(dest)+'other')


@pytest.mark.parametrize('patch,reason',[
    (lambda p:p.update(stdout_sha256='0'*64),'digest_mismatch'),
    (lambda p:p.update(label='other'),'process_unqualified'),
    (lambda p:p.update(returncode=1),'process_unqualified'),
    (lambda p:p.update(stdout_truncated=True),'process_unqualified'),
    (lambda p:p['cleanup'].update(residual_count=1),'cleanup_unproven'),
    (lambda p:p['cleanup'].update(stdout_capture_complete=False),'capture_unproven'),
])
def test_terminal_and_capture_negatives(env,patch,reason):
    m,d,c,dest=env
    with pytest.raises(ValueError,match=reason):m.validate_response(response(m,patch=patch))


def test_equal_length_substitution_and_multiple_process_records(env):
    m,d,c,dest=env
    row=json.loads(response(m));old=base64.b64decode(row['files']['stdout']['data_base64'])
    other=b'y'*len(old)
    row['files']['stdout']=dict(bytes=len(other),sha256=m.sha(other),data_base64=base64.b64encode(other).decode())
    with pytest.raises(ValueError,match='digest_mismatch'):m.validate_response(m.canonical(row))
    row=json.loads(response(m));item=row['files']['process'];raw=base64.b64decode(item['data_base64'])*2
    row['files']['process']=dict(bytes=len(raw),sha256=m.sha(raw),data_base64=base64.b64encode(raw).decode())
    with pytest.raises(ValueError):m.validate_response(m.canonical(row))


def failure(m,request=None,schema=None):
    return dict(schema=schema or m.SCHEMA,request_sha256=m.sha(m.canonical(request or m.REQUEST)),
        state='UNAVAILABLE',files={},artifacts=[],reason='original_file_owner_mode_type_or_size')


def test_refusal_preserved_no_complete_or_retry(env,monkeypatch):
    m,d,c,dest=env
    raw=m.canonical(failure(m));monkeypatch.setattr(m,'qualify',lambda _:dict(ssh_alias='inert'))
    monkeypatch.setattr(d,'transport',lambda *a:raw)
    result=m.collect(m.RUN_ID,str(dest))
    assert result['state']=='UNAVAILABLE' and not result['delivery_verified'] and not result['worker_terminal_proof']
    assert result['reason']=='original_file_owner_mode_type_or_size' and result['retry_authorized'] is False
    assert (dest/'read-response.000').read_bytes()==raw
    receipt=(dest/'receipt.json').read_bytes()
    with pytest.raises(ValueError,match='not_verified'):
        c.read_collection(dest/'receipt.json',expected_sha256=m.sha(receipt),run_id=m.RUN_ID,root=m.ROOT,parent=m.PARENT)


@pytest.mark.parametrize('mutation',[
    lambda r:r.update(request_sha256='0'*64),lambda r:r.update(reason='arbitrary'),
    lambda r:r.update(extra=True),lambda r:r.update(files={'stdout':'leak'}),
    lambda r:r.update(artifacts=[{'payload':'untrusted'}]),lambda r:r.update(schema='wrong'),
])
def test_failure_envelope_corruption_is_not_typed_refusal(env,mutation):
    m,d,c,dest=env
    row=failure(m);mutation(row)
    with pytest.raises(ValueError,match='failure_envelope_invalid') as caught:m.validate_response(m.canonical(row))
    assert not isinstance(caught.value,c.OriginalDeliveryRefused)


def test_original_collector_failure_diagnostic_and_inert_retained_r2_envelope(env):
    m,d,c,dest=env
    request=dict(schema=c.SCHEMA,run_id='r2-original',root='r2-root',parent='r2-parent',host='ubuntu2',contract={})
    raw=m.canonical(failure(m,request,c.SCHEMA))
    with pytest.raises(c.OriginalDeliveryRefused,match='original_file_owner_mode_type_or_size'):
        c.validate_response(raw,request,'qwen')
    actual=Path('/Volumes/Mastermind/evidence/r2-office-20261012/original-reply-collection-v1/read-response.000')
    # Explicit local retained response only; no network or new source observation.
    data=actual.read_bytes()
    assert m.sha(data)=='c93b06f3c96f767d06c62bda205ee8bb54ce887289d0d9bf7cc2f37fbe214a16'
    request=json.loads(actual.with_name('read-request.json').read_bytes())
    with pytest.raises(c.OriginalDeliveryRefused):c.validate_response(data,request,'qwen')


def test_publication_source_drift_clears_all_positive_flags(env,monkeypatch):
    m,d,c,dest=env
    calls=[]
    def qualify(_):
        calls.append(1)
        return dict(ssh_alias='inert',changed=len(calls)>4)
    monkeypatch.setattr(m,'qualify',qualify)
    monkeypatch.setattr(d,'transport',lambda *a:response(m))
    with pytest.raises(ValueError):m.collect(m.RUN_ID,str(dest))
    receipt=json.loads((dest/'receipt.json').read_bytes())
    assert receipt['state']=='UNAVAILABLE' and not receipt['delivery_verified'] and not receipt['worker_terminal_proof']


def remote_home(m,tmp_path):
    home=tmp_path/'home';ext=home/'lanes/ext';lanes=ext/'lanes';lanes.mkdir(parents=True)
    stdout=b'original remote stdout';rid=m.RUN_ID
    for p,b in [(ext/f'lanes_{rid}.rc',b'0\n'),(ext/f'lanes_{rid}.stdout',stdout),
        (lanes/(rid+'.process.jsonl'),m.canonical(process(m,stdout)))]:
        p.write_bytes(b);p.chmod(0o600)
    return home,ext


def test_remote_held_reader_and_generated_source(env,tmp_path):
    m,d,c,dest=env;home,ext=remote_home(m,tmp_path)
    assert m.validate_response(m.canonical(m.remote_read(m.REQUEST,home=home)))['stdout']==b'original remote stdout'
    code=m.code_for_request(m.REQUEST)
    compile(code,'generated-original-reader','exec')
    # Execute exactly the generated functions under their documented inert-home seam.
    prefix=code.split('\ntry:\n raw=sys.stdin.buffer.read(65537)',1)[0]
    ns={};exec(prefix,ns)
    assert ns['remote_read'](m.REQUEST,home=home)['state']=='READ'
    with pytest.raises(ValueError,match='scope'):m.code_for_request(dict(m.REQUEST,host='ubuntu1'))


@pytest.mark.parametrize('kind',['writable','symlink','hardlink','empty','directory'])
def test_remote_guards_remain_intact(env,tmp_path,kind):
    m,d,c,dest=env;home,ext=remote_home(m,tmp_path);p=ext/f'lanes_{m.RUN_ID}.stdout'
    if kind=='writable':p.chmod(0o664)
    elif kind=='hardlink':os.link(p,ext/'other')
    elif kind=='empty':p.write_bytes(b'')
    elif kind=='symlink':
        p.unlink();p.symlink_to(ext/f'lanes_{m.RUN_ID}.rc')
    else:p.unlink();p.mkdir()
    with pytest.raises((OSError,ValueError)):m.remote_read(m.REQUEST,home=home)


def test_pending_and_nonzero_are_not_completion(env,tmp_path):
    m,d,c,dest=env;home,ext=remote_home(m,tmp_path);p=ext/f'lanes_{m.RUN_ID}.rc'
    p.write_bytes(b'7\n');row=m.remote_read(m.REQUEST,home=home)
    with pytest.raises(ValueError,match='terminal_delivery'):m.validate_response(m.canonical(row))
    p.unlink();row=m.remote_read(m.REQUEST,home=home)
    assert m.validate_response(m.canonical(row)) is None
