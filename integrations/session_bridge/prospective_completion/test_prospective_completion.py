"""Inert prospective fixtures only. No provider, remote transport or old run reads."""
import base64
import copy
from datetime import datetime, timezone
import fcntl
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

import pytest

BASE = Path(__file__).parent
EXT = Path.home()/'.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
sys.path[:0] = [str(BASE/'candidate'), str(EXT)]
import original_delivery_collector as c
import remote_sub_exec as producer
import artifact_production as production
import artifact_reader as reader
import artifact_delivery as delivery
import fabric_task as adapter


def raw(value):return reader.canonical(value)


def process(binding, stdout=b'useful bounded result\n'):
    now=datetime.now(timezone.utc).isoformat()
    return dict(schema='mastermind.local_owned_process_receipt.v1',label=binding['run_id'],
        returncode=0,timed_out=False,pid=12345,pgid=12345,started_at=now,ended_at=now,
        stdout_bytes=len(stdout),stderr_bytes=0,stdout_truncated=False,stderr_truncated=False,
        runtime_failure_code=None,cleanup=dict(identity_verified=True,census_proven=True,
        residual_count=0,status='not_needed',error_code=None,session_id=12345,
        stdin_delivery_complete=True,stdin_delivery_error=None,stdout_capture_complete=True,
        stdout_capture_error=None,stderr_capture_complete=True,stderr_capture_error=None))


@pytest.fixture
def capsule(tmp_path,monkeypatch):
    here=tmp_path/'ext';here.mkdir();(here/'state/remote_sub').mkdir(parents=True)
    for name in ('fabric_task.py','remote_sub.sh','original_delivery_collector.py',
                 'artifact_delivery.py','artifact_reader.py','remote_sub_exec.py'):
        source=BASE/'candidate'/name
        (here/name).write_bytes((source if source.is_file() else EXT/name).read_bytes())
    (here/'hosts.json').write_bytes(raw({'ubuntu1':{'ssh_alias':'fixture-host','allowed_modes':['glm','qwen','minimax']}}))
    monkeypatch.setattr(c,'HERE',here)
    monkeypatch.setattr(delivery,'DESTINATION_ROOT',tmp_path)
    monkeypatch.setattr(adapter,'HERE',here)
    root='fixture-root';parent='fixture-parent';run='fixture-'+uuid.uuid4().hex
    monkeypatch.setenv('CODEX_THREAD_ID',parent);monkeypatch.setenv('POOL_ORCHESTRATOR_ID',root)
    support={'remote_sub_exec.py':c.sha((here/'remote_sub_exec.py').read_bytes())};digest=c.sha(raw({'schema':'remote-support-code.v1','files':support}))
    (here/'state/remote_sub'/f'{run}.support.json').write_bytes(raw(support))
    route={'MODE':'glm','MODEL':'glm-5.3-flash','HOST':'ubuntu1'}
    packet=b'Only the new fixture task.'
    store=c.begin_completion(run,root,parent,route,packet,'~',digest)
    sealed=c.seal_completion(str(store.path),run,root,parent,'ubuntu1','glm','glm-5.3-flash',
        'fixture-account','fixture-lease',digest,'7200','600','900',str(os.getpid()),str(store.lock))
    binding=json.loads(Path(sealed).read_bytes())
    # Model Linux's literal /tmp descriptor on this macOS test host. Preserve
    # real O_NOFOLLOW, mode/uid checks and actual directory/file descriptors.
    remote_tmp=tmp_path/'linux-tmp';remote_tmp.mkdir(mode=0o700)
    original_open=os.open
    def host_open(path,*args,**kwargs):
        return original_open(remote_tmp if path=='/tmp' else path,*args,**kwargs)
    monkeypatch.setattr(os,'open',host_open)
    remote_dir=remote_tmp/production.directory(binding).split('/')[-1]
    x=SimpleNamespace(here=here,run=run,root=root,parent=parent,packet=packet,store=store,
        binding=binding,remote_dir=remote_dir,dest=tmp_path/'delivery',route=route,digest=digest)
    yield x
    store.close()


def publish(x,change=None,stdout=b'useful bounded result\n'):
    row=process(x.binding,stdout)
    if change:change(row)
    with production.NewDirectory(x.binding) as owner:
        producer.prepare_completion(owner,x.binding)
        producer.publish_completion(owner,x.binding,raw(row),stdout,0)


def request(x):return dict(schema=c.SCHEMA,run_id=x.run,root=x.root,parent=x.parent,host='ubuntu1',contract=x.binding)


def transport_fixture(monkeypatch,calls):
    def transfer(alias,req):
        calls.append((alias,req))
        return raw(c.remote_envelope(req))
    monkeypatch.setattr(delivery,'transport',transfer)


def collect(x):return c.collect_prospective(x.run,x.root,x.parent,x.dest)


def test_retained_completion_consumed_by_exact_assigning_parent(capsule,monkeypatch):
    x=capsule;publish(x);x.store.close();calls=[];transport_fixture(monkeypatch,calls)
    receipt=collect(x)
    assert len(calls)==1 and receipt['delivery_verified'] and receipt['worker_terminal_proof']
    assert receipt['acceptance']=='NOT_RECORDED'
    assert receipt['lease_settlement']=='UNCHANGED_REQUIRES_EXISTING_OWNER'
    path=x.dest/'receipt.json'
    assert c.read_collection(path,expected_sha256=c.sha(path.read_bytes()),run_id=x.run,root=x.root,parent=x.parent)==b'useful bounded result\n'
    with pytest.raises(FileExistsError):collect(x)
    assert len(calls)==1


def test_active_original_controller_blocks_collection(capsule,monkeypatch):
    calls=[];transport_fixture(monkeypatch,calls)
    with pytest.raises(BlockingIOError):collect(capsule)
    assert not calls and not (capsule.store.path/'collection-intent.json').exists()


def test_another_collector_blocks_collection(capsule,monkeypatch):
    x=capsule;x.store.close();calls=[];transport_fixture(monkeypatch,calls)
    with c.CompletionDirectory(x.store.path) as other:
        other.claim()
        with pytest.raises(BlockingIOError):collect(x)
    assert not calls


@pytest.mark.parametrize('edge',['root','parent','environment','packet','support','hosts','code','lock'])
def test_changed_original_custody_or_source_refuses_before_transport(capsule,monkeypatch,edge):
    x=capsule;x.store.close();calls=[];transport_fixture(monkeypatch,calls)
    if edge=='root':x.root='different'
    elif edge=='parent':x.parent='different'
    elif edge=='environment':monkeypatch.setenv('CODEX_THREAD_ID','foreign')
    elif edge=='packet':(x.store.path/'packet.txt').write_bytes(b'changed')
    elif edge=='support':(x.store.path/'support.json').write_bytes(raw({'changed':'b'*64}))
    elif edge=='hosts':(x.here/'hosts.json').write_bytes(b'{}')
    elif edge=='code':(x.here/'fabric_task.py').write_bytes(b'changed')
    else:
        (x.store.path/'custody.lock').rename(x.store.path/'old-custody.lock')
        (x.store.path/'custody.lock').touch(mode=0o600)
    with pytest.raises((ValueError,FileNotFoundError)):collect(x)
    assert not calls


@pytest.mark.parametrize('edge',['lease_id','account','packet_sha256','support_digest','controller','parent'])
def test_remote_producer_identity_mismatch_is_not_delivery(capsule,monkeypatch,edge):
    x=capsule;publish(x);x.store.close();calls=[]
    response=c.prospective_remote_read(request(x))
    p=json.loads(base64.b64decode(response['files']['process']['data_base64']))
    b=p['prospective_completion']['binding']
    b[edge]=dict(b[edge],generation='b'*32) if edge=='controller' else 'changed'
    data=raw(p);response['files']['process']={'bytes':len(data),'sha256':c.sha(data),'data_base64':base64.b64encode(data).decode()}
    monkeypatch.setattr(delivery,'transport',lambda *_:raw(response))
    with pytest.raises(ValueError,match='producer_binding'):collect(x)
    assert not (x.dest/'receipt.json').exists()


@pytest.mark.parametrize('edge',['cleanup','stdout','marker','partial','symlink','mode','missing-binding'])
def test_unproven_terminal_or_corrupt_capsule_never_delivers(capsule,monkeypatch,edge):
    x=capsule
    if edge=='cleanup':
        with pytest.raises(ValueError):publish(x,lambda p:p['cleanup'].update(residual_count=1))
    else:publish(x)
    x.store.close();calls=[];transport_fixture(monkeypatch,calls)
    if edge=='stdout':(x.remote_dir/'stdout.txt').write_bytes(b'corrupt')
    elif edge=='marker':(x.remote_dir/'terminal.json').write_bytes(b'{}')
    elif edge=='partial':(x.remote_dir/'terminal.json').unlink()
    elif edge=='symlink':
        (x.remote_dir/'stdout.txt').unlink();(x.remote_dir/'stdout.txt').symlink_to('/etc/passwd')
    elif edge=='mode':x.remote_dir.chmod(0o775)
    elif edge=='missing-binding':(x.remote_dir/'binding.json').unlink()
    with pytest.raises((ValueError,KeyError)):collect(x)
    assert not (x.dest/'receipt.json').exists()
    with pytest.raises(FileExistsError):collect(x)
    assert len(calls)==1


@pytest.mark.parametrize('phase',['transport','after-transport','publication','after-publication'])
def test_uncertain_collection_is_sticky_no_second_read(capsule,monkeypatch,phase):
    x=capsule;publish(x);x.store.close();calls=[];transport_fixture(monkeypatch,calls)
    original=delivery.transport
    if phase in ('transport','after-transport'):
        def interrupted(*args):
            if phase=='transport':calls.append(args)
            else:original(*args)
            raise OSError('simulated lost response')
        monkeypatch.setattr(delivery,'transport',interrupted)
    elif phase=='publication':
        monkeypatch.setattr(delivery,'publish_receipt',lambda *a,**kw:(_ for _ in ()).throw(OSError('publication interrupted')))
    else:
        original_write=c.CompletionDirectory.write
        def write(self,name,data):
            if name=='collection-complete.json':raise OSError('post-publication interrupted')
            return original_write(self,name,data)
        monkeypatch.setattr(c.CompletionDirectory,'write',write)
    with pytest.raises(OSError):collect(x)
    assert (x.store.path/'collection-intent.json').exists()
    with pytest.raises(FileExistsError):collect(x)
    assert len(calls)==1


def test_original_unknown_operation_cannot_gain_capsule(capsule):
    x=capsule;old='old-unknown-fixture'
    (x.here/'state/remote_sub'/f'{old}.log').write_bytes(b'LAUNCH\nEFFECT_UNKNOWN\n')
    with pytest.raises(ValueError,match='existing_run_not_adopted'):
        c.begin_completion(old,x.root,x.parent,x.route,x.packet,'~',x.digest)
    assert not c.completion_path(old).exists()


def test_launch_binding_once_and_requires_inherited_descriptor(capsule):
    x=capsule
    args=(str(x.store.path),x.run,x.root,x.parent,'ubuntu1','glm','glm-5.3-flash',
        'fixture-account','fixture-lease',x.digest,'7200','600','900',str(os.getpid()))
    with pytest.raises((OSError,ValueError)):c.seal_completion(*args,'999999')
    with pytest.raises(FileExistsError):c.seal_completion(*args,str(x.store.lock))


def test_producer_checks_packet_environment_deadline_and_regular_file(capsule):
    x=capsule;b=x.binding
    env={'POOL_ORCHESTRATOR_ID':x.root,'POOL_PARENT_RUN_ID':x.parent,'LANE_REMOTE_HOST':'ubuntu1',
        'POOL_LEASE_ID':'fixture-lease','POOL_ACCOUNT':'fixture-account','SUPPORT_DIGEST':x.digest}
    path=x.store.path/'launch.json'
    assert producer.completion_producer_binding(path,x.packet,x.run,'glm','glm-5.3-flash',env)==b
    for key in env:
        with pytest.raises(ValueError):producer.completion_producer_binding(path,x.packet,x.run,'glm','glm-5.3-flash',dict(env,**{key:'changed'}))
    with pytest.raises(ValueError):producer.completion_producer_binding(path,b'wrong',x.run,'glm','glm-5.3-flash',env)
    link=x.store.path/'link';link.symlink_to(path)
    with pytest.raises(OSError):producer.completion_producer_binding(link,x.packet,x.run,'glm','glm-5.3-flash',env)


def test_adapter_holds_original_custody_across_existing_controller(capsule,monkeypatch):
    x=capsule;run='new-'+uuid.uuid4().hex;seen=[]
    monkeypatch.setattr(adapter.pick,'format_pick',lambda *a,**kw: 'POOL=glm MODE=glm MODEL=glm-5.3-flash HOST=ubuntu1')
    monkeypatch.setattr(adapter.pick,'launch_policy',lambda *a,**kw:{'allowed':True})
    monkeypatch.setattr(production,'source_digest',lambda _:x.digest)
    def controller(argv,env,pass_fds):
        assert argv[1]==str(x.here/'remote_sub.sh') and argv[-1]==run
        assert Path(argv[4]).read_bytes()==x.packet
        assert int(env['FABRIC_COMPLETION_CUSTODY_FD'])==pass_fds[0]
        with c.CompletionDirectory(c.completion_path(run)) as second:
            with pytest.raises(BlockingIOError):second.claim()
        seen.append(argv);return SimpleNamespace(returncode=0)
    monkeypatch.setattr(adapter.subprocess,'run',controller)
    assert adapter.request(run,'census',cwd='~',packet=None,stdin_bytes=x.packet,
        root_id=x.root,parent_run_id=x.parent,recoverable_return=True)==0
    assert len(seen)==1
    with c.CompletionDirectory(c.completion_path(run)) as second:second.claim()


def test_collection_only_entry_never_enters_controller(capsule,monkeypatch):
    seen=[]
    monkeypatch.setattr(adapter.subprocess,'run',lambda argv:seen.append(argv) or SimpleNamespace(returncode=75))
    assert adapter.main(['collect-prospective',capsule.run,'--root',capsule.root,'--parent',capsule.parent,
        '--destination',str(capsule.dest)])==75
    assert '--collect-existing' in seen[0] and '--prospective' in seen[0]
    shell=(BASE/'candidate/remote_sub.sh').read_text()
    assert shell.index('exec python3')<shell.index('\ntrap ')<shell.index('broker acquire')
    assert 'FABRIC_COMPLETION_CONTEXT:-}" ]; then RETRYABLE_ADMISSION_MODE=0' in shell
    assert shell.index('--seal-completion')<shell.index('LAUNCH_REMOTE=')


def test_fixed_remote_reader_code_compiles(capsule):
    # Tests the actual code assembled for the incumbent bounded transport.
    (capsule.here/'artifact_reader.py').write_bytes((EXT/'artifact_reader.py').read_bytes())
    compile(c.code_for_request(request(capsule)),'fixed-original-reader','exec')


def test_real_controller_interruption_releases_only_original_custody(capsule,monkeypatch):
    x=capsule;publish(x)
    # Only this newly-created inert local fixture process is interrupted.
    child=subprocess.Popen([sys.executable,'-c',
        'import sys,time; print("HELD",flush=True); time.sleep(20)'],
        pass_fds=(x.store.lock,),stdout=subprocess.PIPE,text=True)
    try:
        assert child.stdout.readline().strip()=='HELD'
        x.store.close();calls=[];transport_fixture(monkeypatch,calls)
        with pytest.raises(BlockingIOError):collect(x)
        child.terminate();child.wait(timeout=5)
        assert collect(x)['delivery_verified'] and len(calls)==1
    finally:
        if child.poll() is None:child.terminate();child.wait(timeout=5)
        child.stdout.close()


def test_actual_owned_process_capture_produces_collectable_result(capsule,monkeypatch):
    from lane_runtime import run_owned_process
    x=capsule;path=x.store.path/'actual-fixture-process.json'
    with production.NewDirectory(x.binding) as owner:
        producer.prepare_completion(owner,x.binding)
        outcome=run_owned_process([sys.executable,'-c','print("owned fixture return")'],
            timeout=5,label=x.run,receipt_path=path)
        assert outcome.returncode==0
        producer.publish_completion(owner,x.binding,path.read_bytes(),outcome.stdout.encode(),outcome.returncode)
    x.store.close();calls=[];transport_fixture(monkeypatch,calls)
    assert collect(x)['delivery_verified']
    receipt=x.dest/'receipt.json'
    assert c.read_collection(receipt,expected_sha256=c.sha(receipt.read_bytes()),
        run_id=x.run,root=x.root,parent=x.parent)==b'owned fixture return\n'


def test_published_receipt_without_final_owner_readback_cannot_be_consumed(capsule,monkeypatch):
    x=capsule;publish(x);x.store.close();transport_fixture(monkeypatch,[]);collect(x)
    (x.store.path/'collection-complete.json').unlink()
    path=x.dest/'receipt.json'
    with pytest.raises(FileNotFoundError):
        c.read_collection(path,expected_sha256=c.sha(path.read_bytes()),run_id=x.run,root=x.root,parent=x.parent)


def test_actual_embedded_transport_reader_returns_original_capsule(capsule,monkeypatch):
    import io
    x=capsule;publish(x)
    code=c.code_for_request(request(x));captured=io.BytesIO()
    with monkeypatch.context() as patch:
        patch.setattr(sys,'stdin',SimpleNamespace(buffer=io.BytesIO(raw(request(x)))))
        patch.setattr(sys,'stdout',SimpleNamespace(buffer=captured))
        exec(compile(code,'fixed-original-reader','exec'),{'__name__':'fixture_reader'})
    blobs,artifacts,manifest=c.validate_response(captured.getvalue(),request(x),'glm')
    assert blobs['stdout']==b'useful bounded result\n' and artifacts==[] and manifest is None


def test_prelaunch_seal_cli_preserves_inherited_kernel_custody(capsule,monkeypatch):
    import shutil
    x=capsule
    # New isolated run: no old launch or provider; CLI only seals evidence.
    for name in ('original_delivery_collector.py','remote_sub_exec.py'):
        shutil.copy2(BASE/'candidate'/name,x.here/name)
    run='cli-'+uuid.uuid4().hex
    (x.here/'state/remote_sub'/f'{run}.support.json').write_bytes((x.store.path/'support.json').read_bytes())
    with c.begin_completion(run,x.root,x.parent,x.route,x.packet,'~',x.digest) as owner:
        argv=[sys.executable,str(x.here/'original_delivery_collector.py'),run,'--root',x.root,'--parent',x.parent,
            '--seal-completion',str(owner.path),run,x.root,x.parent,'ubuntu1','glm','glm-5.3-flash',
            'fixture-account','fixture-lease',x.digest,'7200','600','900',str(os.getpid()),str(owner.lock)]
        result=subprocess.run(["/bin/bash","-c",'out=$("$@") || exit $?; printf "%s\\n" "$out"',"seal",*argv],env=dict(os.environ,PYTHONPATH=str(EXT)),pass_fds=(owner.lock,),
            capture_output=True,text=True,timeout=5)
        assert result.returncode==0,(result.stdout,result.stderr)
        assert result.stdout.strip()==str(owner.path/'launch.json')
        with c.CompletionDirectory(owner.path) as other:
            with pytest.raises(BlockingIOError):other.claim()


def test_actual_executor_ordinary_profile_wires_prelaunch_and_terminal(capsule,monkeypatch):
    x=capsule
    monkeypatch.setattr(producer,'__file__',str(x.here/'remote_sub_exec.py'))
    (x.here/'sub.sh').write_text('#!/bin/bash\nprintf "executor fixture result\\n"\n')
    monkeypatch.setattr(production,'source_digest',lambda _:x.digest)
    monkeypatch.setattr(producer.os,'getloadavg',lambda:(0.,0.,0.))
    monkeypatch.setattr(producer,'install_signal_cleanup',lambda **_:None)
    for key,value in {'FABRIC_COMPLETION_BINDING':str(x.store.path/'launch.json'),
        'LANE_MAX_ACTIVE':'2','LANE_MAX_LOAD_RATIO':'1.5','LANE_NICE':'0','LANE_LEASED':'1',
        'REMOTE_SUB_CHILD_TIMEOUT':'5','POOL_PARENT_RUN_ID':x.parent,'LANE_REMOTE_HOST':'ubuntu1','POOL_LEASE_ID':'fixture-lease',
        'POOL_ACCOUNT':'fixture-account','SUPPORT_DIGEST':x.digest}.items():monkeypatch.setenv(key,value)
    assert producer._execute(['remote_sub_exec.py',x.run,'glm',str(x.store.path/'packet.txt'),'~','glm-5.3-flash'],{})==0
    response=c.remote_envelope(request(x))
    blobs,_,_=c.validate_response(raw(response),request(x),'glm')
    assert blobs['stdout']==b'executor fixture result\n'


def test_f1_validator_change_after_binding_refuses_before_transport(capsule,monkeypatch):
    x=capsule
    dependency=x.here/'remote_sub_exec.py'
    assert dependency.read_bytes()==(BASE/'candidate/remote_sub_exec.py').read_bytes()
    publish(x);x.store.close();calls=[];transport_fixture(monkeypatch,calls)
    dependency.write_bytes(dependency.read_bytes()+b'\n# F1 inert post-binding drift\n')
    with pytest.raises(ValueError,match='source|dependency'):
        collect(x)
    assert calls==[] and not (x.dest/'receipt.json').exists()
    assert not (x.store.path/'collection-intent.json').exists()


def test_f1_validator_change_before_launch_seal_refuses(capsule):
    x=capsule;run='f1-seal-'+uuid.uuid4().hex
    (x.here/'state/remote_sub'/f'{run}.support.json').write_bytes((x.store.path/'support.json').read_bytes())
    with c.begin_completion(run,x.root,x.parent,x.route,x.packet,'~',x.digest) as owner:
        dep=x.here/'remote_sub_exec.py';dep.write_bytes(dep.read_bytes()+b'\n# F1 before seal\n')
        with pytest.raises(ValueError,match='source'):
            c.seal_completion(str(owner.path),run,x.root,x.parent,'ubuntu1','glm','glm-5.3-flash',
                'fixture-account','fixture-lease',x.digest,'7200','600','900',str(os.getpid()),str(owner.lock))
        assert not (owner.path/'launch.json').exists()


@pytest.mark.parametrize('phase',['after-transport','publication'])
def test_f1_validator_change_during_collection_prevents_publication(capsule,monkeypatch,phase):
    x=capsule;publish(x);x.store.close();calls=[];transport_fixture(monkeypatch,calls)
    dep=x.here/'remote_sub_exec.py'
    def drift():dep.write_bytes(dep.read_bytes()+b'\n# F1 during collection\n')
    if phase=='after-transport':
        original=delivery.transport
        def transfer(*args):
            result=original(*args);drift();return result
        monkeypatch.setattr(delivery,'transport',transfer)
    else:
        original=delivery.publish_receipt
        def publication(*args,**kwargs):
            drift();return original(*args,**kwargs)
        monkeypatch.setattr(delivery,'publish_receipt',publication)
    with pytest.raises(ValueError):collect(x)
    assert len(calls)==1
    receipt=x.dest/'receipt.json'
    assert not receipt.exists() or json.loads(receipt.read_bytes()).get('state')!='COMPLETE'
    assert not (x.store.path/'collection-complete.json').exists()
    with pytest.raises((ValueError,FileExistsError)):collect(x)
    assert len(calls)==1
