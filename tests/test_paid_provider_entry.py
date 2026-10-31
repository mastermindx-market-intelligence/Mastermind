"""Offline new-entry contracts; synthetic platform facts are never admission."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

from control_plane import paid_fabric_wire as wire
from control_plane.paid_model_execution_contract import digest
from control_plane.paid_model_execution_contract import compile_request
from ops.native_fabric.quota_continuity.candidate import paid_provider_entry as entry
from ops.native_fabric.quota_continuity.candidate import paid_glm_model_client as client
from ops.native_fabric.quota_continuity.candidate import linux_process_identity
from tests.test_paid_fabric_owner_wiring import material
from tests.test_paid_initializer_nosite import nested_commitment
from tests.test_paid_glm_canonical import modules


@pytest.fixture(autouse=True)
def model_child_startup(monkeypatch):
    # Explicit child startup metadata seam, independent of the expected input.
    monkeypatch.setattr(entry,'_runtime_observation',lambda:dict(
        python_path='/usr/bin/python3',python_version='3.12.3',
        startup=dict(prefix='/usr',exec_prefix='/usr',base_prefix='/usr',base_exec_prefix='/usr')))


def bound_material(tmp_path=None):
    p,frame,_,lease,authority=material()
    source=p['paid_source_config'];q=source['qualification'];c=nested_commitment()
    source.update(worker_uid=os.getuid(),worker_gid=os.getgid())
    p['launch_spec'].update(expected_worker_uid=os.getuid(),expected_worker_gid=os.getgid())
    c['account'].update(uid=os.getuid(),gid=os.getgid())
    for name in ('host_env','nested_helper'):c[name].update(uid=os.getuid(),gid=os.getgid())
    q['capture_identity'].update(uid=os.getuid(),gid=os.getgid())
    home=str(tmp_path/'worker') if tmp_path else '/home/runner'
    c.update(host_ref='ubuntu3',transport_alias='ubuntu3',lane_root=home+'/lanes')
    c['account'].update(user='runner',home=home)
    c['host_env']['path']=home+'/lanes/ext/HOST_ENV.sh'
    c['nested_helper']['path']=home+'/lanes/ext/.host_glm_token.sh'
    c['initialized_context'].update(home=home,glm_config=home+'/lanes/ext/glm.json')
    for name in ('bootstrap_python','launch_python'):
        c[name]=dict(path=source['binary']['path'],real_path=source['binary']['real_path'],
                     sha256=source['binary']['sha256'])
    source['capture_root']=c['lane_root']+'/ext/lanes'
    q.update(initializer_commitment=c,initializer_commitment_sha256=digest(c),
             host_env_path=c['host_env']['path'],host_env_sha256=c['host_env']['sha256'])
    for name in entry.INITIALIZER_NAMES:q['qualifier_sources_sha256'][name]='c'*64
    physical=deepcopy(source);physical.pop('capacity_capability_id')
    physical.update(schema_version='mastermind.paid_fabric_host_binding/v1',
                    worker_source_config_digest=digest(source))
    p.update(paid_physical_binding=physical,physical_binding_sha256=digest(physical))
    binding=dict(schema_version='mastermind.paid_host_readiness_context/v1',host='ubuntu3',
        transport_alias='ubuntu3',worker_id=physical['worker_id'],account=p['paid_account'],
        model=physical['model'],boot_id=q['boot_id'],source_config_sha256=digest(source),
        release_manifest_sha256=q['qualifier_source_manifest_sha256'],registry_sha256=q['registry_sha256'],
        initializer_commitment_sha256=q['initializer_commitment_sha256'],validator_sha256='d'*64,
        readiness_source_sha256='e'*64)
    descriptor=wire.provider_entry_descriptor(p,sources_sha256={n:('c' if n in entry.INITIALIZER_NAMES else 'f')*64 for n in entry.SOURCE_NAMES},
                                               readiness_binding=binding,config_identity=[1,20,0o100600,os.getuid(),os.getgid(),1,30,5,6])
    return p,frame,lease,authority,descriptor


def inputs(tmp_path,*,with_payload=False):
    p,_,_,_,descriptor=bound_material(tmp_path)
    c=descriptor['initializer_commitment'];run=p['binding']['attempt_id']
    lanes=Path(c['lane_root']);(lanes/'tmp').mkdir(parents=True)
    capture=Path(descriptor['capture_root'])/(run+'.paid');capture.mkdir(parents=True,mode=0o700)
    root=capture.parent;info=root.stat()
    p['paid_source_config']['qualification']['capture_identity']=dict(device=info.st_dev,
        inode=info.st_ino,mode=info.st_mode,uid=info.st_uid,gid=info.st_gid)
    physical=deepcopy(p['paid_source_config']);physical.pop('capacity_capability_id')
    physical.update(schema_version='mastermind.paid_fabric_host_binding/v1',
                    worker_source_config_digest=digest(p['paid_source_config']))
    p.update(paid_physical_binding=physical,physical_binding_sha256=digest(physical))
    binding=descriptor['readiness_binding'];binding['source_config_sha256']=digest(p['paid_source_config'])
    descriptor=wire.provider_entry_descriptor(p,sources_sha256=descriptor['sources_sha256'],
                                               readiness_binding=binding,config_identity=descriptor['config_identity'])
    body=compile_request(p)
    descriptor['body_sha256']=hashlib.sha256(body).hexdigest()
    capsule=dict(token='v2.inert-test-data-not-a-grant',expires_at=time.time()+60,
        account=p['paid_account'],lease_id='lease-1',model=p['paid_route']['model'],
        host='ubuntu3',run_id=run,root='JOB-root',provider_entry=descriptor)
    capsule_raw=entry.canonical(capsule)
    for path,raw in ((lanes/'tmp'/(run+'.txt'),body),
                     (lanes/'tmp'/(run+'.glm-cap.json'),capsule_raw)):
        path.write_bytes(raw);path.chmod(0o600)
    request=entry.request_from_capsule(capsule,capsule_raw=capsule_raw,
                                     timeout_seconds=55,entry_nonce='a'*64)
    helper=c['nested_helper'];hook=c['host_env']
    identity=lambda wanted:[1,2,0o100000|wanted['mode'],wanted['uid'],wanted['gid'],1,wanted['size'],5,6]
    pre=dict(commitment_sha256=digest(c),snapshot_sealed=True,
        snapshot_sha256='87198f3568e199c64a4deb2d41242a1c812dd65797f60ecc0db00fdf71b6e378',
        host_env_identity=identity(hook),helper_origin_identity=identity(helper),
        bootstrap_sha256=c['bootstrap_python']['sha256'],launch_sha256=c['launch_python']['sha256'],
        nested_inputs=dict(schema_version='mastermind.paid_nested_data_inputs/v1',
            initialization_contract=c['initialization_contract'],legacy_outer_sha256=hook['sha256'],
            transformed_outer_sha256='87198f3568e199c64a4deb2d41242a1c812dd65797f60ecc0db00fdf71b6e378',
            helper={'schema_version':'mastermind.paid_helper_private_data/v1',
                    **{k:helper[k] for k in ('sha256','size','uid','gid','mode')}}))
    result=(request,body,capsule_raw,capture,pre)
    return result+(p,) if with_payload else result


def test_descriptor_requires_real_correlated_installed_projection():
    p,_,_,_,d=bound_material()
    assert d['initializer_commitment_sha256']==digest(d['initializer_commitment'])
    assert d['physical_binding_sha256']==p['physical_binding_sha256']
    for field in ('host','account','model','registry_sha256','source_config_sha256','boot_id'):
        bad=deepcopy(d['readiness_binding']);bad[field]='foreign'
        with pytest.raises(wire.PaidWireRefused):
            wire.provider_entry_descriptor(p,sources_sha256=d['sources_sha256'],readiness_binding=bad,config_identity=d['config_identity'])
    p['paid_physical_binding']['qualification'].pop('initializer_commitment')
    with pytest.raises(wire.PaidWireRefused):
        wire.provider_entry_descriptor(p,sources_sha256=d['sources_sha256'],readiness_binding=d['readiness_binding'],config_identity=d['config_identity'])


@pytest.mark.parametrize('key,value',[('purpose','canonical-paid-qualification.v1'),
    ('model','glm-unadmitted'),('entry_nonce',''),('timeout_seconds',True),('timeout_seconds',7201),
    ('expires_at',float('inf'))])
def test_request_has_no_legacy_or_mixed_purpose_fallback(tmp_path,key,value):
    request,*_=inputs(tmp_path);request[key]=value
    with pytest.raises(entry.ProviderEntryRefused):entry.validate_request(request)


def test_fixed_client_is_after_context_and_exact_private_input_checks(tmp_path,monkeypatch):
    request,body,capsule_raw,capture,pre=inputs(tmp_path)
    checks=[];calls=[]
    context=SimpleNamespace(pre_execution=pre,check=lambda:checks.append('held'))
    monkeypatch.setattr(linux_process_identity,'inspect_linux_process_image',
                        lambda pid:dict(start_identity='actual-fixture-start',boot_id='boot-fixture'))
    # Fixed client's real input validation/Request construction/response decoder;
    # ONLY its final network transport is an inert response.
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,n):
            return client.canonical(dict(status='completed',error=None,incomplete_details=None,
                output=[dict(type='message',role='assistant',status='completed',
                             content=[dict(type='output_text',text='{"summary":"inert"}')])]))
    def open_(req,timeout):
        assert (capture/'entry-ready.json').exists() and len(checks)>=4
        assert req.full_url==client.URL and req.method=='POST' and req.data==body
        calls.append('fixed-post');return Response()
    monkeypatch.setattr(client,'build_opener',lambda *args:SimpleNamespace(open=open_))
    assert entry._run_model_entry(request,client,context)==b'{"summary":"inert"}'
    assert calls==['fixed-post'] and len(checks)>=5
    ready=json.loads((capture/'entry-ready.json').read_bytes())
    assert entry.validate_ready(ready,request,pid=os.getpid(),
        process_identity=dict(start_identity='actual-fixture-start',boot_id='boot-fixture'))==ready
    assert b'v2.' not in entry.canonical(ready) and b'inert sealed evidence' not in entry.canonical(ready)


@pytest.mark.parametrize('mutation',['precreated','body','capsule','context'])
def test_precreated_or_mixed_context_never_reaches_fixed_client(tmp_path,monkeypatch,mutation):
    request,_,_,capture,pre=inputs(tmp_path);calls=[]
    context=SimpleNamespace(pre_execution=pre,check=lambda:None)
    monkeypatch.setattr(linux_process_identity,'inspect_linux_process_image',
                        lambda pid:dict(start_identity='start',boot_id='boot-fixture'))
    monkeypatch.setattr(client,'execute',lambda *args:calls.append('FORBIDDEN_PROVIDER'))
    if mutation=='precreated':(capture/'entry-ready.json').write_bytes(b'foreign-stale-proof')
    elif mutation=='body':request['body_sha256']='0'*64
    elif mutation=='capsule':request['capsule_sha256']='0'*64
    else:
        def changed():raise entry.ProviderEntryRefused()
        context.check=changed
    with pytest.raises((entry.ProviderEntryRefused,FileExistsError)):
        entry._run_model_entry(request,client,context)
    assert calls==[]


def test_slow_ready_time_does_not_refresh_original_client_budget(tmp_path,monkeypatch):
    request,_,_,capture,pre=inputs(tmp_path);posts=[];seen=[]
    deadline=request['deadline_monotonic_ns']
    def check():
        seen.append(1)
        if len(seen)>=4:monkeypatch.setattr(entry.time,'monotonic_ns',lambda:deadline+1)
    context=SimpleNamespace(pre_execution=pre,check=check)
    monkeypatch.setattr(linux_process_identity,'inspect_linux_process_image',
                        lambda pid:dict(start_identity='start',boot_id='boot-fixture'))
    monkeypatch.setattr(client,'execute',lambda *a,**k:posts.append('FORBIDDEN_POST'))
    with pytest.raises(entry.ProviderEntryRefused):entry._run_model_entry(request,client,context)
    assert (capture/'entry-ready.json').exists() and posts==[]


def test_fixed_compiler_measures_actual_utf8_commands_and_never_contains_token(tmp_path,record_property):
    import shlex
    request,_,raw,_,_=inputs(tmp_path)
    capsule=json.loads(raw);d=capsule['provider_entry']
    root=Path(__file__).parents[1]/'ops/native_fabric/quota_continuity/candidate'
    hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in entry.SOURCE_NAMES}
    d['sources_sha256']=hashes
    raw=entry.canonical(capsule)
    support={n:hashes.get(n,'f'*64) for n in entry.SUPPORT_FILES}
    command=entry.executor_command(raw,support,root)
    argc=shlex.split(command)
    assert argc[0]=='/usr/bin/env' and argc[3]==d['python_path']
    assert argc[4:7]==['-I','-S','-B'] and argc[9]=='executor'
    assert b'v2.inert-test' not in command.encode() and 'source ' not in command[:command.index('-c')]
    request=entry.request_from_capsule(capsule,capsule_raw=raw,timeout_seconds=55,entry_nonce='a'*64)
    model=entry.model_command(root,request,support)
    assert model[:4]==[d['python_path'],'-I','-S','-B'] and model[6]=='model'
    measured=dict(executor_utf8_nul=len(command.encode())+1,
                  model_argv_utf8_nuls=sum(len(v.encode())+1 for v in model))
    assert all(value<=100000 for value in measured.values())
    record_property('canonical_entry_transport_bounds',json.dumps(measured,sort_keys=True))
    with pytest.raises(entry.ProviderEntryRefused):
        entry.executor_command(raw,{**support,'caller.py':'f'*64},root)


def test_source_sets_preserve_every_prior_generation_exactly():
    from ops.native_fabric.quota_continuity.candidate import support_bundle as support
    from ops.native_fabric.quota_continuity.candidate import paid_model_owner
    assert entry.SUPPORT_FILES==paid_model_owner._PAID_SUPPORT_FILES==support.PAID_INITIALIZED_SOURCE_FILES
    assert support.PAID_INITIALIZED_SOURCE_FILES-support.PAID_MODEL_SOURCE_FILES=={
        'paid_provider_entry.py','paid_initializer.py','paid_initializer_token_data.py','paid_initializer_nested_data.py',
        'paid_yaml_runtime.py','paid_pyyaml_6_0_3.zip','paid_pyyaml_provenance.json'}
    assert entry.YAML_NAMES=={'paid_yaml_runtime.py','paid_pyyaml_6_0_3.zip','paid_pyyaml_provenance.json'}
    assert len(entry.BUNDLE_NAMES)==len(entry.INITIALIZER_NAMES)==len(entry.YAML_NAMES)==3
    assert entry.SOURCE_NAMES==entry.BUNDLE_NAMES|entry.INITIALIZER_NAMES|entry.YAML_NAMES
    assert len(entry.SOURCE_NAMES)==9 and len(entry.SUPPORT_FILES)==47
    assert support.PRE_HELD_YAML_PAID_INITIALIZED_SOURCE_FILES==entry.SUPPORT_FILES-entry.YAML_NAMES
    assert len(support.PRE_HELD_YAML_PAID_INITIALIZED_SOURCE_FILES)==44
    assert len(support.PRE_HELD_YAML_PAID_INITIALIZED_PHYSICAL_ROOT_SOURCE_FILES)==45
    assert support.PRE_HELD_YAML_PAID_INITIALIZED_SOURCE_FILES in support.SOURCE_GENERATIONS
    assert support.PRE_HELD_YAML_PAID_INITIALIZED_PHYSICAL_ROOT_SOURCE_FILES in support.SOURCE_GENERATIONS
    assert support.PAID_MODEL_SOURCE_FILES in support.SOURCE_GENERATIONS
    assert support.PAID_MODEL_PHYSICAL_ROOT_SOURCE_FILES in support.SOURCE_GENERATIONS
    assert support.SOURCE_FILES in support.SOURCE_GENERATIONS


@pytest.mark.parametrize('failure',[None,'foreign-ready','wrong-lease','revoked-control',
                                  'context-drift','lost-response','truncated-response'])
def test_actual_observer_gateway_intent_and_client_join(tmp_path,monkeypatch,modules,failure):
    """Real code/SQLite/Control validation; physical factory and HTTP are inert.

    No real process, kernel peer, installed context, lease acquisition or
    provider is represented. Those explicit external seams cannot grant a Job.
    """
    import sqlite3
    import threading
    import datetime
    import sys
    from control_plane import paid_fabric_backend as backend
    from control_plane import fabric_control_start
    from control_plane.executive_worker_broker import PeerCredentials
    from ops.native_fabric.quota_continuity.candidate import paid_model_owner as model_owner
    from ops.native_fabric.quota_continuity.candidate import lane_runtime
    from ops.native_fabric.quota_continuity.candidate import paid_controller_channel
    cap,gw=modules
    request,body,_,capture,pre,p=inputs(tmp_path,with_payload=True)
    now=time.time();key=b'inert-source-test-key-at-least-32-bytes'
    db=tmp_path/'leases.sqlite'
    lease=dict(id='lease-1',orchestrator_id='JOB-root',pool='glm',account=p['paid_account'],
        model=p['paid_route']['model'],host='ubuntu3',pid=800,granted_at=now-10,
        ttl=600,last_heartbeat=now,state='held',renewable=1)
    with sqlite3.connect(db) as connection:
        connection.execute('CREATE TABLE leases (id TEXT,orchestrator_id TEXT,pool TEXT,account TEXT,'
            'model TEXT,host TEXT,pid INTEGER,granted_at REAL,ttl INTEGER,last_heartbeat REAL,state TEXT,renewable INTEGER)')
        connection.execute('INSERT INTO leases VALUES ('+','.join('?' for _ in lease)+')',tuple(lease.values()))
    gateway=gw.GlmLeaseGateway(db,[p['paid_account']],[p['paid_route']['model']],signing_key=key)
    p['control_start']=dict(schema_version=fabric_control_start.SCHEMA,attempt_id='ATT-1',
        fence_generation=1,pin_version=2,pin_identity_sha256=fabric_control_start.launch_identity(p),
        lease_expires_at=datetime.datetime.fromtimestamp(now+120,datetime.timezone.utc).isoformat())
    authority=fabric_control_start.authorize_control_command(p,peer=PeerCredentials(uid=450,gid=450))
    owner=object.__new__(backend.CanonicalPaidBackend)
    owner._lock=threading.RLock();owner._gateway=gateway;owner._operations={}
    # Explicit external production-constructor/kernel/source qualification seam.
    # Actual original authority, route/lease codec and intent are NOT replaced.
    owner.require_gateway=lambda observed:None if observed is gateway else entry.refuse()
    owner.require_original_controller=lambda *a,**kw:dict(pid=800,start_identity='controller',boot_id='m2')
    owner._provider_entry_descriptor=lambda payload:descriptor
    gateway._canonical_owner=owner
    log=tmp_path/'original.log';fd=os.open(log,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_APPEND,0o600)
    os.write(fd,('CANONICAL_PAID_REQUIRED schema=1 payload_sha256='+authority.payload_sha256+'\n').encode())
    operation=backend._Original(p,authority,SimpleNamespace(pid=800),'a'*64,
        tmp_path/'packet',log,tmp_path/'output')
    operation.log_fd=fd
    operation.intent=paid_controller_channel.ProviderIntent(fd,payload_sha256=authority.payload_sha256)
    owner._operations['ATT-1']=operation
    descriptor=json.loads((Path(request['capture_root']).parent.parent/'tmp/ATT-1.glm-cap.json').read_bytes())['provider_entry']
    capsule=gateway._issue_canonical(p,authority=authority,lease_id='lease-1',ttl=60,
                                    request_body=json.loads(body))
    capsule['provider_entry']=descriptor;operation.capsule=capsule;operation.lease=lease
    capsule_raw=paid_controller_channel.canonical(capsule)
    (Path(request['capture_root']).parent.parent/'tmp/ATT-1.glm-cap.json').write_bytes(capsule_raw)
    request=entry.request_from_capsule(capsule,capsule_raw=capsule_raw,timeout_seconds=55,entry_nonce='a'*64)
    proc=SimpleNamespace(pid=os.getpid(),poll=lambda:None)
    _,frame,_,_,_=bound_material(tmp_path)
    image=frame['process_identity'];image.update(pgid=proc.pid,session_id=proc.pid,
        parent_pid=os.getpid(),effective_uid=os.geteuid(),real_uid=os.getuid(),
        effective_gid=os.getegid(),real_gid=os.getgid())
    monkeypatch.setattr(linux_process_identity,'inspect_linux_process_image',lambda pid:dict(image))
    monkeypatch.setattr(model_owner.pwd,'getpwuid',lambda uid:SimpleNamespace(pw_name='runner'))
    monkeypatch.setattr(model_owner,'sys',SimpleNamespace(
        executable='/usr/bin/python3.12',
        version=p['paid_source_config']['binary']['version']+' inert-platform-metadata'))
    for name,module in (('paid_glm_model_client',client),('paid_provider_entry',entry),
                        ('linux_process_identity',linux_process_identity),('lane_runtime',lane_runtime)):
        monkeypatch.setitem(sys.modules,name,module)
    monkeypatch.setenv('GLM_REMOTE_CAPABILITY_FILE',str(Path(request['capture_root']).parent.parent/'tmp/ATT-1.glm-cap.json'))
    monkeypatch.setenv('LANE_REMOTE_HOST','ubuntu3');monkeypatch.setenv('POOL_LEASE_ID','lease-1')
    monkeypatch.setenv('SUPPORT_DIGEST','6'*64)
    capture.rmdir()
    observer=model_owner.launch_observer(Path(__file__).parents[1]/'ops/native_fabric/quota_continuity/candidate',
        Path(request['capture_root']).parent.parent/'tmp/ATT-1.txt','ATT-1',request['model'],
        Path(request['capture_root'])/'ATT-1.process.jsonl',entry_request=request)
    root_before=entry._identity(Path(request['capture_root']).stat())
    posts=[];provider_entries=[]
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):
            if failure=='lost-response':raise TimeoutError('inert loss AFTER original intent')
            if failure=='truncated-response':return b'{"status":"completed"'
            return client.canonical(dict(status='completed',error=None,incomplete_details=None,
                output=[dict(type='message',role='assistant',status='completed',
                             content=[dict(type='output_text',text='{"summary":"retained"}')])]))
    def open_(req,timeout):
        posts.append('loopback-post')
        if failure=='foreign-ready':
            path=capture/'entry-ready.json';data=json.loads(path.read_bytes());data['entry_nonce']='b'*64
            path.write_bytes(entry.canonical(data))
        observer(proc,'2026-10-24T00:00:00+00:00')
        launch=model_owner.retained_record(Path(request['capture_root'])/'ATT-1.process.jsonl','ATT-1','launch')
        assert launch['python_path']=='/usr/bin/python3'!=model_owner.sys.executable
        result=wire.paid_start_from_owned_launch(p,launch,capsule=capsule,lease=lease,
            controller=dict(process_start_identity='controller',boot_id='m2'),authority=authority)
        operation.launch_frame=launch;operation.start_result=result;operation.launch_ready.set()
        if failure=='wrong-lease':
            with sqlite3.connect(db) as connection:connection.execute("UPDATE leases SET account='foreign'")
        if failure=='revoked-control':operation.payload=deepcopy(p);operation.payload['paid_account']='foreign'
        if failure=='context-drift':
            owner._provider_entry_descriptor=lambda payload:{**descriptor,'readiness_binding_sha256':'0'*64}
        claims=gateway.authorize_canonical(req.get_header('Authorization')[7:],
            model=request['model'],run_id='ATT-1',host='ubuntu3')
        assert hashlib.sha256(req.data).hexdigest()==claims['request_body_sha256']
        gateway._consume_canonical_provider_intent(claims)
        provider_entries.append('one-authenticated-intent')
        return Response()
    monkeypatch.setattr(client,'build_opener',lambda *a:SimpleNamespace(open=open_))
    context=SimpleNamespace(pre_execution=pre,check=lambda:None)
    try:
        if failure is None:
            result_bytes=entry._run_model_entry(request,client,context)
            assert result_bytes==b'{"summary":"retained"}'
            # Normal owner appends and artifact retention MUST NOT invalidate
            # the exact initializer-held capture-root directory identity.
            assert entry._identity(Path(request['capture_root']).stat())==root_before
            cleanup=dict(census_proven=True,identity_verified=True,residual_count=0,status='not_needed',
                stdout_capture_complete=True,stderr_capture_complete=True,stdin_delivery_complete=True)
            terminal=dict(schema=lane_runtime.PROCESS_RECEIPT_SCHEMA,label='ATT-1',pid=proc.pid,pgid=proc.pid,
                started_at='2026-10-24T00:00:00+00:00',ended_at='2026-10-24T00:00:01+00:00',
                returncode=0,timed_out=False,nice_requested=10,nice_applied=True,
                stdout_bytes=len(result_bytes),stdout_sha256=hashlib.sha256(result_bytes).hexdigest(),
                stderr_bytes=0,stderr_sha256=hashlib.sha256(b'').hexdigest(),
                stdout_truncated=False,stderr_truncated=False,runtime_failure_code=None,cleanup=cleanup)
            receipt=Path(request['capture_root'])/'ATT-1.process.jsonl'
            lane_runtime._append_process_receipt(receipt,terminal)
            # Empty stderr is part of the capture owner contract.
            result=lane_runtime.OwnedProcessResult(0,result_bytes.decode(),'',False,proc.pid,proc.pid,cleanup)
            model_owner.retain_result(receipt,'ATT-1',result)
            owned=model_owner.retained_record(receipt,'ATT-1','terminal')
            wire.validate_owned_terminal(owned,operation.launch_frame)
            collection=wire.paid_collection_from_owned_terminal(p,operation.start_result,owned,result_bytes)
            assert collection['result']['structured_output']=={'summary':'retained'}
            assert entry._identity(Path(request['capture_root']).stat())==root_before
            old=receipt.read_bytes()
            with pytest.raises(FileExistsError):
                model_owner.launch_observer(Path(__file__).parents[1]/'ops/native_fabric/quota_continuity/candidate',
                    Path(request['capture_root']).parent.parent/'tmp/ATT-1.txt','ATT-1',request['model'],
                    receipt,entry_request=request)
            assert receipt.read_bytes()==old
        else:
            with pytest.raises(Exception):entry._run_model_entry(request,client,context)
        assert posts==['loopback-post']
        if failure in (None,'lost-response','truncated-response'):
            assert provider_entries==['one-authenticated-intent']
            # A lost/truncated response stays spent. No second HTTP POST is
            # attempted; direct repeat of the genuine intent sink refuses.
            with pytest.raises(Exception):operation.intent.consume()
        else:assert provider_entries==[]
    finally:
        operation.intent.close();os.close(fd)
