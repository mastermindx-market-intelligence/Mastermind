"""Inert original-operation delivery: real bounded files, no network/provider."""
import base64
import copy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
import original_delivery_collector as c
import artifact_delivery as d
import artifact_production as p
import artifact_reader as r


def put(path,data):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    path.write_bytes(data);path.chmod(0o600)


@pytest.fixture
def world(tmp_path,monkeypatch):
    here=tmp_path/'installed';here.mkdir(mode=0o700)
    monkeypatch.setattr(c,'HERE',here);monkeypatch.setattr(d,'HERE',here)
    monkeypatch.setattr(d,'DESTINATION_ROOT',tmp_path)
    monkeypatch.setenv('CODEX_THREAD_ID','original-root')
    monkeypatch.delenv('POOL_ORCHESTRATOR_ID',raising=False)
    for name in ('artifact_production.py','artifact_reader.py'):
        put(here/name,Path(p.__file__ if name=='artifact_production.py' else r.__file__).read_bytes())
    support={name:c.sha((here/name).read_bytes()) for name in ('artifact_production.py','artifact_reader.py')}
    digest=c.sha(c.canonical({'schema':'remote-support-code.v1','files':support}))
    rid='original-run'
    body='Bounded useful patch only.\n'
    contract=dict(schema=p.SCHEMA,root='original-root',parent='original-parent',run_id=rid,
        names=['useful.patch'],body_sha256=c.sha(body.encode()),support_digest=digest)
    packet=p.REQUEST_PREFIX+c.canonical(contract).decode()+'\n'+body
    events=['RUN_RESERVED explicit=1','LEASE_OK pool=glm',f'SUPPORT_VERSION_READY digest={digest} policy='+('a'*64),
        f'LAUNCH stdout=lanes_{rid}.stdout rc_file=ext/lanes_{rid}.rc cwd=~','LAUNCH_ATTEMPT attempt=1',
        'POLL_TRANSPORT_FAILED rc=255 poll=9']
    log='\n'.join('2026-10-13T03:57Z [remote_sub id='+rid+' host=ubuntu1] '+e for e in events)+'\n'
    state=here/'state/remote_sub';state.mkdir(parents=True,mode=0o700)
    sources={}
    for name,filename,data in [('packet',rid+'.packet.test',packet.encode()),('log',rid+'.log',log.encode()),('support',rid+'.support.json',c.canonical(support))]:
        path=state/filename;put(path,data);sources[name]={'path':str(path),'sha256':c.sha(data)}
    put(here/'hosts.json',c.canonical({'ubuntu1':{'ssh_alias':'ubuntu1','allowed_modes':['glm','qwen']}}))
    binding={'schema':c.BINDING_SCHEMA,'run_id':rid,'root':'original-root','parent':'original-parent',
        'host':'ubuntu1','mode':'glm','requested_model':'glm-5.3-flash','cwd':'~','artifact_names':['useful.patch'],'sources':sources}
    binding_path=tmp_path/'binding.json';put(binding_path,c.canonical(binding))
    artifact=b'original useful patch\n'
    path=p.paths(contract)[0]
    manifest={'schema':p.RESULT_SCHEMA,**{k:contract[k] for k in ('root','parent','run_id')},'host':'ubuntu1',
        'request_sha256':c.sha(c.canonical(contract)),'files':[{'path':path,'bytes':len(artifact),'sha256':c.sha(artifact)}]}
    stdout=('Completed original assignment.\nFABRIC_ARTIFACTS_V1 '+c.canonical(manifest).decode()+'\n').encode()
    process={'schema':'mastermind.local_owned_process_receipt.v1','label':rid,'returncode':0,'timed_out':False,
        'pid':234,'pgid':234,'stdout_bytes':len(stdout),'stderr_bytes':0,'stdout_truncated':False,'stderr_truncated':False,
        'runtime_failure_code':None,'started_at':'2026-10-13T03:00:00Z','ended_at':'2026-10-13T03:01:00Z',
        'cleanup':{'identity_verified':True,'census_proven':True,'residual_count':0,'status':'not_needed','error_code':None,
            **{stem+suffix:value for stem in ('stdin_delivery','stdout_capture','stderr_capture') for suffix,value in [('_complete',True),('_error',None)]}},
        'artifact_production':{'schema':'mastermind.fabric_artifact_completion.v1','mode':'glm','contract':contract,'manifest':manifest,'stdout_sha256':c.sha(stdout)}}
    home=tmp_path/'remote-home';ext=home/'lanes/ext';lanes=ext/'lanes';lanes.mkdir(parents=True,mode=0o700)
    files={'rc':ext/f'lanes_{rid}.rc','stdout':ext/f'lanes_{rid}.stdout','process':lanes/f'{rid}.process.jsonl'}
    for name,data in [('rc',b'0\n'),('stdout',stdout),('process',c.canonical(process))]:put(files[name],data)
    def artifact_read(path,remaining):
        return {'path':path,'status':'RETRIEVED','bytes':len(artifact),'sha256':c.sha(artifact),
            'data_base64':base64.b64encode(artifact).decode(),
            'observed_file':{'device':1,'inode':2,'mtime_ns':3,'uid':os.getuid(),'mode':0o600}}
    monkeypatch.setattr(r,'read_one',artifact_read)
    calls=[]
    def transport(alias,request):
        calls.append((alias,copy.deepcopy(request)));return c.canonical(c.remote_read(request,home=home))
    monkeypatch.setattr(d,'transport',transport)
    def collect(destination=None):return c.collect(binding_path,run_id=rid,root='original-root',parent='original-parent',destination=destination or tmp_path/'delivered')
    return SimpleNamespace(**locals())


def test_same_operation_retained_delivery_and_parent_consumption(world):
    w=world;before={k:Path(v['path']).read_bytes() for k,v in w.sources.items()}
    receipt=w.collect()
    assert receipt['state']=='COMPLETE' and receipt['delivery_verified'] and receipt['worker_terminal_proof']
    assert receipt['lease_settlement']==receipt['controller_state']=='UNKNOWN'
    assert receipt['acceptance']=='NOT_RECORDED' and not receipt['original_operation_mutated']
    path=w.tmp_path/'delivered/receipt.json'
    assert c.read_collection(path,expected_sha256=c.sha(path.read_bytes()),run_id=w.rid,root='original-root',parent='original-parent')==w.stdout
    assert len(w.calls)==1 and {k:Path(v['path']).read_bytes() for k,v in w.sources.items()}==before
    assert all(path.exists() for path in w.files.values())
    with pytest.raises(FileExistsError):w.collect()
    assert len(w.calls)==1


@pytest.mark.parametrize('fault',['root','parent','host','packet','support','log','names','caller','inherited_root','plaintext','second_launch'])
def test_wrong_original_source_refuses_before_transport(world,monkeypatch,fault):
    w=world;binding=copy.deepcopy(w.binding)
    if fault in ('root','parent','host'):binding[fault]='other'
    if fault in ('packet','support','log'):binding['sources'][fault]['sha256']='0'*64
    if fault=='names':binding['artifact_names']=['other.patch']
    if fault=='caller':monkeypatch.setenv('CODEX_THREAD_ID','another-root')
    if fault=='inherited_root':monkeypatch.setenv('POOL_ORCHESTRATOR_ID','another-root')
    if fault in ('plaintext','second_launch'):
        name='packet' if fault=='plaintext' else 'log';path=Path(binding['sources'][name]['path'])
        raw=b'no historical producer binding' if fault=='plaintext' else path.read_bytes()+b'2026-10-13T03:58Z [remote_sub id=original-run host=ubuntu1] LAUNCH_ATTEMPT attempt=1\n'
        put(path,raw);binding['sources'][name]['sha256']=c.sha(raw)
    put(w.binding_path,c.canonical(binding))
    with pytest.raises(ValueError):w.collect()
    assert w.calls==[]


@pytest.mark.parametrize('fault',['cleanup','capture','stdout','parent','support','manifest','mode','rc'])
def test_terminal_and_producer_negatives_cannot_publish_verified_result(world,fault):
    w=world;process=copy.deepcopy(w.process)
    if fault=='cleanup':process['cleanup']['residual_count']=1
    if fault=='capture':process['cleanup']['stdout_capture_complete']=False
    if fault=='stdout':process['artifact_production']['stdout_sha256']='0'*64
    if fault in ('parent','support'):
        process['artifact_production']['contract']['parent' if fault=='parent' else 'support_digest']='foreign' if fault=='parent' else '0'*64
    if fault=='manifest':process['artifact_production']['manifest']['files'][0]['sha256']='0'*64
    if fault=='mode':process['artifact_production']['mode']='qwen'
    if fault=='rc':put(w.files['rc'],b'1\n')
    put(w.files['process'],c.canonical(process))
    with pytest.raises(ValueError):w.collect()
    assert len(w.calls)==1 and not (w.tmp_path/'delivered/receipt.json').exists()


@pytest.mark.parametrize('fault',['symlink','fifo','group_write','oversize','malformed_rc','missing_process'])
def test_remote_fixed_file_guards(world,fault):
    w=world;path=w.files['process']
    if fault=='symlink':path.rename(path.with_suffix('.saved'));path.symlink_to(path.with_suffix('.saved'))
    if fault=='fifo':path.unlink();os.mkfifo(path)
    if fault=='group_write':path.chmod(0o660)
    if fault=='oversize':put(path,b'x'*65537)
    if fault=='malformed_rc':put(w.files['rc'],b'0\n0\n')
    if fault=='missing_process':path.unlink()
    with pytest.raises((ValueError,OSError)):w.collect()
    assert len(w.calls)==1 and not (w.tmp_path/'delivered/receipt.json').exists()


def test_missing_rc_is_pending_not_absence_or_terminal(world):
    w=world;w.files['rc'].unlink();receipt=w.collect()
    assert receipt['state']=='PENDING' and receipt['delivery_verified'] is False and receipt['worker_terminal_proof'] is False
    assert receipt['lease_settlement']=='UNKNOWN' and w.files['stdout'].exists()


def test_source_changed_during_read_and_transport_refusal_do_not_retry(world,monkeypatch):
    w=world
    def unavailable(*args):w.calls.append(args);raise ValueError('transport_unavailable')
    monkeypatch.setattr(d,'transport',unavailable)
    with pytest.raises(ValueError,match='transport_unavailable'):w.collect()
    assert len(w.calls)==1 and not (w.tmp_path/'delivered/receipt.json').exists()


def test_original_log_change_during_read_does_not_steal_controller(world,monkeypatch):
    w=world;original=d.transport
    def changed(*args):
        response=original(*args);path=Path(w.sources['log']['path']);put(path,path.read_bytes()+b'original controller still owns its log\n');return response
    monkeypatch.setattr(d,'transport',changed)
    with pytest.raises(ValueError,match='original_source_changed'):w.collect()
    assert len(w.calls)==1 and b'original controller' in Path(w.sources['log']['path']).read_bytes()


def test_directory_swap_during_read_is_refused(world,monkeypatch):
    w=world;original=r.read_one
    def changed(*args):
        response=original(*args);w.ext.rename(w.ext.with_name('retained-ext'));w.ext.mkdir(mode=0o700);return response
    monkeypatch.setattr(r,'read_one',changed)
    with pytest.raises(ValueError,match='directory_chain_changed'):w.collect()
    assert len(w.calls)==1


def test_fixed_remote_code_compiles_without_running(world):
    w=world;request={'schema':c.SCHEMA,**{k:w.binding[k] for k in ('run_id','root','parent','host')},'contract':w.contract}
    source=c.code_for_request(request)
    compile(source,'<fixed-original-reader>','exec')
    assert 'subprocess' not in source and 'os.kill' not in source and 'os.chmod' not in source
