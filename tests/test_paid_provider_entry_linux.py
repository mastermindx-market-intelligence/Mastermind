"""Actual compiled C processes on disposable Linux, never a paid/host proof.

Only existing public source, exclusive credentialless HOME fixture leaves and a
new exclusive loopback4141 listener are used. Control peer/Root startup factory
and broker rows are explicit test premises; commands, startup guard, Bash/FDs,
Linux process observations, gateway codec/intent and result owners stay real.
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import dataclasses
import datetime
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import pwd
import shlex
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from control_plane import fabric_control_start, paid_fabric_backend as backend
from control_plane import paid_fabric_wire as wire
from control_plane.executive_worker_broker import PeerCredentials
from control_plane.paid_model_execution_contract import compile_request, digest, paid_host_reference
from ops.native_fabric.quota_continuity.candidate import paid_provider_entry as entry
from ops.native_fabric.quota_continuity.candidate import paid_initializer as initializer
from ops.native_fabric.quota_continuity.candidate import linux_process_identity
from tests.test_paid_fabric_owner_wiring import material
from tests.test_paid_glm_canonical import modules

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'ops/native_fabric/quota_continuity/candidate'
linux_fixture=pytest.mark.skipif(sys.platform!='linux' or sys.version_info[:2]!=(3,12),
                            reason='actual Linux CPython3.12 compiled process/custody fixture')


def _identity(info):
    return [info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,
            info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns]


@contextmanager
def _exclusive_home_fixture():
    account=pwd.getpwuid(os.getuid())
    if account.pw_uid==0:pytest.skip('requires non-Root disposable Linux account')
    home=Path(account.pw_dir)
    # Never read/adopt an existing account configuration or a lane operation.
    owned=[]
    try:
        for name in ('lanes','.glm'):
            path=home/name
            try:path.mkdir(mode=0o700)
            except FileExistsError:pytest.skip('exclusive credentialless fixture namespace unavailable')
            owned.append((path,path.stat().st_ino))
        yield account,home/'lanes',home/'.glm'
    finally:
        for path,inode in reversed(owned):
            assert path.lstat().st_ino==inode and not path.is_symlink()
            # Only our exclusive disposable tree; immutable publication dirs
            # need owner write permission for test cleanup, never installed data.
            for directory,dirs,_ in os.walk(path,followlinks=False):
                os.chmod(directory,0o700)
            shutil.rmtree(path)


def _source_stage(tmp_path):
    output=tmp_path/'built'
    built=subprocess.run([sys.executable,str(ROOT/'ops/native_fabric/quota_continuity/rollout/build_review_stage.py'),
                          '--output',str(output)],capture_output=True,timeout=20)
    assert built.returncode==0,'public native stage did not build'
    return output/'native-code-stage/ext'


def _request_material(account,lanes,config,system,stage):
    p,_,_,_,_=material()
    real=system.resolve(strict=True);info=real.stat()
    assert info.st_uid==0 and not info.st_mode&0o022 and real.name=='python3.12'
    observed=json.loads(subprocess.check_output([str(system),'-I','-S','-B','-c',
        'import json,sys;print(json.dumps(dict(version=sys.version.split()[0],startup={k:getattr(sys,k) for k in ("prefix","exec_prefix","base_prefix","base_exec_prefix")})))'],timeout=5))
    assert set(observed['startup'].values())=={'/usr'},'fixture supports only actual Root /usr startup'
    (lanes/'ext/lanes').mkdir(parents=True,mode=0o700)
    (lanes/'ext/active').mkdir(mode=0o700)
    (lanes/'ext/hosts.json').write_text(json.dumps({'ubuntu0':dict(local=False,roles=['lanes'],allowed_modes=['glm'],hostnames=[socket.gethostname().split('.',1)[0]])}))
    (lanes/'tmp').mkdir(mode=0o700)
    (lanes/'support-releases').mkdir(mode=0o700)
    hook=lanes/'ext/HOST_ENV.sh';hook.write_bytes(initializer._NESTED_DATA._ORIGINAL if initializer._NESTED_DATA else
        __import__('ops.native_fabric.quota_continuity.candidate.paid_initializer_nested_data',fromlist=['_ORIGINAL'])._ORIGINAL)
    hook.chmod(0o600)
    helper=lanes/'ext/.host_glm_token.sh'
    helper.write_bytes(b'export GLM_SHIM_TOKEN="0123456789abcdef0123456789abcdef"\n');helper.chmod(0o600)
    config.write_bytes(b'{"fixture":true}\n');config.chmod(0o600)
    c=dict(schema_version=initializer.SCHEMA,purpose='canonical-paid-qualification.v1',
        initialization_contract=initializer.NESTED_CONTRACT,host_ref='ubuntu0',transport_alias='mmx-ubuntu0',
        lane_root=str(lanes),account=dict(uid=account.pw_uid,gid=account.pw_gid,user=account.pw_name,home=account.pw_dir),
        bootstrap_python=dict(path=str(real),real_path=str(real),sha256=hashlib.sha256(real.read_bytes()).hexdigest()),
        launch_python=dict(path=str(system),real_path=str(real),sha256=hashlib.sha256(real.read_bytes()).hexdigest()),
        startup=dict(profile=initializer.NO_SITE_PROFILE,**observed['startup']),
        host_env=dict(path=str(hook),sha256=hashlib.sha256(hook.read_bytes()).hexdigest(),size=hook.stat().st_size,uid=account.pw_uid,gid=account.pw_gid,mode=0o600),
        nested_helper=dict(path=str(helper),sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),size=helper.stat().st_size,uid=account.pw_uid,gid=account.pw_gid,mode=0o600),
        initialized_context=dict(home=account.pw_dir,glm_config=str(config)))
    # No expected selector rewrite: actual dca-style versioned bootstrap and
    # distinct actual post-initialization logical selector must both survive.
    assert c['bootstrap_python']['path']!=c['launch_python']['path']
    source=p['paid_source_config'];q=source['qualification']
    source.update(worker_uid=account.pw_uid,worker_gid=account.pw_gid,worker_user=account.pw_name,
        host_ref=paid_host_reference('ubuntu0','mmx-ubuntu0'),capture_root=str(lanes/'ext/lanes'))
    source['binary'].update(path=str(system),real_path=str(real),sha256=c['launch_python']['sha256'],
        size=info.st_size,device=info.st_dev,inode=info.st_ino,mode=info.st_mode,uid=info.st_uid,gid=info.st_gid,
        mtime_ns=info.st_mtime_ns,version=observed['version'],team_identifier=None)
    capture=(lanes/'ext/lanes').stat();boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    hashes={n:hashlib.sha256((stage/n).read_bytes()).hexdigest() for n in entry.SOURCE_NAMES}
    q.update(registry_key='ubuntu0',transport_alias='mmx-ubuntu0',boot_id=boot,
        host_env_path=str(hook),host_env_sha256=c['host_env']['sha256'],initializer_commitment=c,
        initializer_commitment_sha256=digest(c),capture_identity=dict(device=capture.st_dev,inode=capture.st_ino,
            mode=capture.st_mode,uid=capture.st_uid,gid=capture.st_gid))
    q['qualifier_sources_sha256'].update({n:hashes[n] for n in entry.INITIALIZER_NAMES})
    physical=deepcopy(source);physical.pop('capacity_capability_id')
    physical.update(schema_version='mastermind.paid_fabric_host_binding/v1',worker_source_config_digest=digest(source))
    p.update(paid_physical_binding=physical,physical_binding_sha256=digest(physical))
    p['paid_route']['host_ref']=source['host_ref']
    p['launch_spec'].update(expected_worker_uid=account.pw_uid,expected_worker_gid=account.pw_gid,worker_user=account.pw_name)
    binding=dict(schema_version='mastermind.paid_host_readiness_context/v1',host='ubuntu0',transport_alias='mmx-ubuntu0',
        worker_id=source['worker_id'],account=p['paid_account'],model=source['model'],boot_id=boot,
        source_config_sha256=digest(source),release_manifest_sha256=q['qualifier_source_manifest_sha256'],
        registry_sha256=q['registry_sha256'],initializer_commitment_sha256=digest(c),validator_sha256='d'*64,readiness_source_sha256='e'*64)
    descriptor=wire.provider_entry_descriptor(p,sources_sha256=hashes,readiness_binding=binding,
        config_identity=_identity(config.stat()))
    return p,descriptor


def _publish_support(stage,lanes,monkeypatch):
    from ops.native_fabric.quota_continuity.candidate import support_bundle as support
    from ops.native_fabric.quota_continuity.source import fabric_policy_snapshot as policy
    # Actual immutable support publisher and alias validation; this file is
    # fixture routing DATA, not an installed policy/admission authorization.
    monkeypatch.setitem(sys.modules,'fabric_policy_snapshot',policy)
    monkeypatch.setattr(policy,'validate_publication',lambda *a:None)
    sources=lanes/'fixture-support-source';sources.mkdir(mode=0o700)
    for name in support.PAID_INITIALIZED_SOURCE_FILES:
        raw=b'pools: {}\n' if name=='pools.yaml' else (stage/name).read_bytes()
        (sources/name).write_bytes(raw)
    manifest={n:hashlib.sha256((sources/n).read_bytes()).hexdigest() for n in support.PAID_INITIALIZED_SOURCE_FILES}
    return support.publish(sources,lanes/'ext',manifest),manifest


@linux_fixture
@pytest.mark.parametrize('failure',[None,'source-drift','expired','lost-response','truncated-response'])
def test_actual_compiled_c_executor_model_and_original_result(tmp_path,monkeypatch,modules,record_property,failure):
    cap,gw=modules
    stage=_source_stage(tmp_path)
    system=Path('/usr/bin/python3')
    with _exclusive_home_fixture() as (account,lanes,glm), ExitStack() as cleanup:
        p,descriptor=_request_material(account,lanes,glm/'config.json',system,stage)
        here,support=_publish_support(stage,lanes,monkeypatch)
        run=p['binding']['attempt_id'];now=time.time()
        # Explicit local Control peer, Root/source constructor and broker
        # fixture; actual authority/codec/intent algorithms are not replaced.
        p['control_start']=dict(schema_version=fabric_control_start.SCHEMA,attempt_id=run,fence_generation=1,pin_version=2,
            pin_identity_sha256=fabric_control_start.launch_identity(p),
            lease_expires_at=datetime.datetime.fromtimestamp(now+120,datetime.timezone.utc).isoformat())
        authority=fabric_control_start.authorize_control_command(p,peer=PeerCredentials(uid=450,gid=450))
        lease=dict(id='lease-compiled',orchestrator_id=p['binding']['root_id'],pool='glm',account=p['paid_account'],
            model=p['paid_route']['model'],host='ubuntu0',pid=os.getpid(),granted_at=now-1,ttl=120,last_heartbeat=now,state='held',renewable=1)
        db=tmp_path/'fixture-leases.sqlite'
        with sqlite3.connect(db) as connection:
            connection.execute('CREATE TABLE leases (id TEXT,orchestrator_id TEXT,pool TEXT,account TEXT,model TEXT,host TEXT,pid INTEGER,granted_at REAL,ttl INTEGER,last_heartbeat REAL,state TEXT,renewable INTEGER)')
            connection.execute('INSERT INTO leases VALUES ('+','.join('?' for _ in lease)+')',tuple(lease.values()))
        gateway=gw.GlmLeaseGateway(db,[p['paid_account']],[p['paid_route']['model']],signing_key=b'disposable-compiled-fixture-key-32-bytes')
        owner=object.__new__(backend.CanonicalPaidBackend);owner._lock=threading.RLock();owner._gateway=gateway;owner._operations={}
        owner.require_gateway=lambda actual:None if actual is gateway else entry.refuse()
        controller=linux_process_identity.inspect_linux_process_image(os.getpid())
        owner.require_original_controller=lambda *a,**k:dict(pid=os.getpid(),start_identity=controller['start_identity'],boot_id=controller['boot_id'])
        owner._provider_entry_descriptor=lambda payload:descriptor if payload==p else entry.refuse()
        gateway._canonical_owner=owner
        log=tmp_path/'original.log';fd=os.open(log,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_APPEND,0o600)
        cleanup.callback(os.close,fd)
        os.write(fd,('CANONICAL_PAID_REQUIRED schema=1 payload_sha256='+authority.payload_sha256+'\n').encode())
        operation=backend._Original(p,authority,SimpleNamespace(pid=os.getpid()),'a'*64,tmp_path/'packet',log,tmp_path/'output')
        operation.image=dict(process_start_identity=controller['start_identity'],boot_id=controller['boot_id'])
        operation.log_fd=fd
        from ops.native_fabric.quota_continuity.candidate import paid_controller_channel
        operation.intent=paid_controller_channel.ProviderIntent(fd,payload_sha256=authority.payload_sha256)
        cleanup.callback(operation.intent.close)
        owner._operations[run]=operation;operation.lease=lease
        body=compile_request(p)
        capsule=gateway._issue_canonical(p,authority=authority,lease_id=lease['id'],ttl=60,request_body=json.loads(body))
        capsule['provider_entry']=descriptor;operation.capsule=capsule
        if failure=='expired':capsule['expires_at']=time.time()-1
        capsule_raw=entry.canonical(capsule)
        packet=lanes/'tmp'/(run+'.txt');packet.write_bytes(body);packet.chmod(0o600)
        capsule_path=lanes/'tmp'/(run+'.glm-cap.json');capsule_path.write_bytes(capsule_raw);capsule_path.chmod(0o600)
        # The exact normal compiler, no test prefix, callback or source patch
        # is inserted into the generated executor/model startup programs.
        command=entry.executor_command(capsule_raw,support,here)
        assert len(command.encode())+1<=100000
        record_property('actual_executor_command_utf8_nul',len(command.encode())+1)
        if failure=='source-drift':
            target=here/'paid_model_owner.py';target.chmod(0o755);target.write_bytes(target.read_bytes()+b'\n# changed fixture source\n');target.chmod(0o555)
        posts=[];intents=[];errors=[];launches=[]
        from ops.native_fabric.quota_continuity.candidate import paid_glm_model_client
        monkeypatch.setitem(sys.modules,'paid_glm_model_client',paid_glm_model_client)
        receipt=lanes/'ext/lanes'/(run+'.process.jsonl')
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def do_POST(self):
                try:
                    assert self.path=='/v1/responses'
                    assert int(self.headers['Content-Length'])==len(body)
                    assert self.rfile.read(len(body))==body
                    posts.append(1)
                    # Original remote observer writes from the actual Popen;
                    # this fixture replaces only the SSH record delivery.
                    deadline=time.monotonic()+8
                    while not receipt.exists() or not receipt.stat().st_size:
                        if time.monotonic()>=deadline:raise AssertionError('original launch receipt missing')
                        time.sleep(.01)
                    from ops.native_fabric.quota_continuity.candidate import paid_model_owner
                    frame=paid_model_owner.retained_record(receipt,run,'launch')
                    start=wire.paid_start_from_owned_launch(p,frame,capsule=capsule,lease=lease,
                        controller=operation.image,authority=authority)
                    assert frame['pid']!=os.getpid() and frame['python_path']==str(system)
                    assert frame['process_identity']==linux_process_identity.inspect_linux_process_image(frame['pid'])
                    launches.append(frame);operation.launch_frame=frame;operation.start_result=start;operation.launch_ready.set()
                    claims=gateway.authorize_canonical(self.headers['Authorization'][7:],model=p['paid_route']['model'],run_id=run,host='ubuntu0')
                    gateway._consume_canonical_provider_intent(claims);intents.append(1)
                    if failure=='lost-response':self.close_connection=True;return
                    response=entry.canonical(dict(status='completed',error=None,incomplete_details=None,
                        output=[dict(type='message',role='assistant',status='completed',content=[dict(type='output_text',text='{"summary":"compiled-retained"}')])]))
                    if failure=='truncated-response':response=response[:len(response)//2]
                    self.send_response(200);self.send_header('Content-Length',str(len(response)));self.end_headers();self.wfile.write(response)
                except BaseException as error:
                    errors.append(type(error).__name__);self.close_connection=True
        # Exclusive bind only: never inspect or connect to an existing listener.
        try:server=HTTPServer(('127.0.0.1',4141),Handler)
        except OSError as error:
            if error.errno==98:pytest.skip('exclusive disposable loopback fixture unavailable')
            raise
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        env=dict(PATH='/usr/bin:/bin',HOME=account.pw_dir,LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',
            REMOTE_SUB_LANES=str(lanes),POOL_LEASE_ID=lease['id'],POOL_ACCOUNT=p['paid_account'],LANE_REMOTE_HOST='ubuntu0',
            SUPPORT_DIGEST=here.parent.name,REMOTE_SUB_CHILD_TIMEOUT='35',REMOTE_SUB_COMMISSION_BUDGET_SECONDS='35')
        try:
            executed=subprocess.run(shlex.split(command),env=env,stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=70)
            assert not errors,errors
            assert b'0123456789abcdef0123456789abcdef' not in executed.stdout+executed.stderr
            if failure in ('source-drift','expired'):
                assert executed.returncode!=0 and not posts and not intents
            else:
                assert posts==[1] and intents==[1] and len(launches)==1
                if failure is None:
                    assert executed.returncode==0
                    from ops.native_fabric.quota_continuity.candidate import paid_model_owner
                    terminal=paid_model_owner.retained_record(receipt,run,'terminal')
                    result=(lanes/'ext/lanes'/(run+'.paid/result.json')).read_bytes()
                    assert result==b'{"summary":"compiled-retained"}'
                    wire.validate_owned_terminal(terminal,launches[0])
                    collection=wire.paid_collection_from_owned_terminal(p,operation.start_result,terminal,result)
                    assert collection
                else:
                    assert executed.returncode!=0
                    assert not (lanes/'ext/lanes'/(run+'.paid/result.json')).exists()
                # The same actual intent cannot be consumed or POSTed again.
                observed=gateway.authorize_canonical(capsule['token'],model=p['paid_route']['model'],run_id=run,host='ubuntu0')
                with pytest.raises(gw.LeaseGatewayError):gateway._consume_canonical_provider_intent(observed)
                assert posts==[1] and intents==[1]
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)



def test_compiled_fixture_data_assembles_against_real_wire_and_compilers(tmp_path,monkeypatch):
    """Cross-platform shape check, explicitly NOT Linux execution/Root proof."""
    account=SimpleNamespace(pw_uid=os.getuid(),pw_gid=os.getgid(),pw_name='fixture-user',pw_dir=str(tmp_path/'home'))
    lanes=Path(account.pw_dir)/'lanes';lanes.mkdir(parents=True)
    config=tmp_path/'config.json'
    bindir=tmp_path/'bin';bindir.mkdir();image=bindir/'python3.12';image.write_bytes(b'fixture-image-not-executed');image.chmod(0o755)
    system=bindir/'python3';system.symlink_to(image)
    rawstat=os.stat;rawread=Path.read_text
    class ImageMetadata:
        def __init__(self,info):self.info=info
        st_uid=0;st_gid=0
        def __getattr__(self,key):return getattr(self.info,key)
    def observed_stat(path,*a,**kw):
        value=rawstat(path,*a,**kw)
        return ImageMetadata(value) if str(path)==str(image) else value
    monkeypatch.setattr(os,'stat',observed_stat)
    monkeypatch.setattr(Path,'read_text',lambda path,*a,**kw:
        '12345678-1234-1234-1234-123456789abc' if str(path)=='/proc/sys/kernel/random/boot_id' else rawread(path,*a,**kw))
    # This supplements the Linux test by checking its actual fixture DATA;
    # replacing this one observation cannot turn it into an OS/principal proof.
    monkeypatch.setattr(subprocess,'check_output',lambda *a,**kw:entry.canonical(dict(version='3.12.3',
        startup=dict(prefix='/usr',exec_prefix='/usr',base_prefix='/usr',base_exec_prefix='/usr'))))
    # Reuse the already-qualified public native inventory as DATA. This
    # supplemental case deliberately does NOT spawn/retry the stage builder.
    stage=tmp_path/'source-snapshot';stage.mkdir()
    quota=ROOT/'ops/native_fabric/quota_continuity'
    inventory=json.loads((quota/'rollout/native-source-inventory.json').read_bytes())
    for name,row in inventory['files'].items():
        source=(quota/row['source']).resolve()
        assert source.is_relative_to(ROOT/'ops/native_fabric')
        raw=source.read_bytes()
        assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
        (stage/Path(name).name).write_bytes(raw)
    p,d=_request_material(account,lanes,config,system,stage)
    body=compile_request(p)
    assert d['body_sha256']==hashlib.sha256(body).hexdigest()
    capsule=dict(token='v2.inert-fixture-not-authority',expires_at=time.time()+30,account=p['paid_account'],
        lease_id='fixture-lease',model=p['paid_route']['model'],host='ubuntu0',run_id=p['binding']['attempt_id'],
        root=p['binding']['root_id'],provider_entry=d)
    raw=entry.canonical(capsule)
    support={n:hashlib.sha256((stage/n).read_bytes()).hexdigest() if n!='pools.yaml' else 'f'*64 for n in entry.SUPPORT_FILES}
    command=entry.executor_command(raw,support,stage)
    request=entry.request_from_capsule(capsule,capsule_raw=raw,timeout_seconds=35,entry_nonce='a'*64)
    model=entry.model_command(stage,request,support)
    assert len(command.encode())+1<=100000 and sum(len(v.encode())+1 for v in model)<=100000
    assert 'v2.inert-fixture-not-authority' not in command and all('v2.inert-fixture-not-authority' not in v for v in model)
    assert shlex.split(command)[3]==str(image) and model[0]==str(system)
