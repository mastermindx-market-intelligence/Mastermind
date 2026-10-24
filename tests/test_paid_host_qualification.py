"""Synthetic qualification fixtures only: no host, credential or installed reads."""
import ast
import copy
import errno
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import pickle
import stat
import subprocess
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'ops/native_fabric/quota_continuity/candidate'
spec = importlib.util.spec_from_file_location('paid_host_qualification_test_source', SOURCE/'paid_host_qualification.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
H = 'a'*64
R = 'b'*40
SOURCE_HASHES = {name: H for name in m.SOURCE_NAMES}
from tests.paid_initializer_fixtures import commitment,witness,module as initializer_module
INITIALIZER_RAW=(SOURCE/'paid_initializer.py').read_bytes()
SOURCE_HASHES['paid_initializer.py']=hashlib.sha256(INITIALIZER_RAW).hexdigest()

@pytest.fixture(autouse=True)
def selected_initializer_source_fixture(monkeypatch):
    # Source/custody fixture seam; real closed contract/command code executes.
    def load(expected):
        assert expected==hashlib.sha256(INITIALIZER_RAW).hexdigest()
        return initializer_module,INITIALIZER_RAW
    monkeypatch.setattr(m,'_initializer_module',load)

BINDING = dict(host_ref='ubuntu2', hosts_path='/safe/hosts.json', release_sha=R,
    source_manifest_sha256=H, preimage_sha256='c'*64, expected_sources=SOURCE_HASHES,initializer_commitment=commitment(python='/home/worker/lanes/venv/bin/python3',binary_sha=H,hook_sha=H))
BINDING['initializer_commitment']['launch_python']['real_path']='/usr/bin/python3.12'
PRINCIPAL = dict(uid=501, gid=20, user='operator', home='/Users/operator')
SNAPSHOT = dict(sources={name:dict(sha256=H,identity=(1,2)) for name in m.SOURCE_NAMES},
    registry_sha256='d'*64, registry_identity=(3,4), alias='ubuntu2')


def request():
    c=commitment(python='/home/worker/lanes/venv/bin/python3',binary_sha=H,hook_sha=H)
    c['launch_python']['real_path']='/usr/bin/python3.12'
    return dict(schema='mastermind.paid_host_probe_request/v2', host_ref='ubuntu2',
        transport_alias='ubuntu2', nonce='nonce1', python_path='/home/worker/lanes/venv/bin/python3',
        capture_root='/home/worker/lanes/ext/lanes', release_sha=R, source_manifest_sha256=H,
        preimage_sha256='c'*64, registry_sha256='d'*64, sources_sha256=SOURCE_HASHES.copy(),
        probe_sha256=hashlib.sha256(m._REMOTE_PROBE.encode()).hexdigest(), context=m._CONTEXT,initializer_commitment=c,initializer_commitment_sha256=m._digest(c))


def response(req):
    return dict(schema='mastermind.paid_host_observation/v2', request=copy.deepcopy(req),pre_execution=witness(req),
        binary=dict(path=req['python_path'], real_path='/usr/bin/python3.12', version='3.12.10',
            sha256=H, team_identifier=None, size=1000, device=1, inode=2, mode=stat.S_IFREG|0o755,
            uid=0, gid=0, mtime_ns=100), worker_uid=1000, worker_gid=1000, worker_user='worker',
        boot_id='12345678-1234-1234-1234-123456789abc', capture_root=req['capture_root'],
        capture_identity=dict(device=1,inode=3,mode=stat.S_IFDIR|0o700,uid=1000,gid=1000,mtime_ns=100),
        context_identity=dict(profile=m._CONTEXT,host_env_path='/home/worker/lanes/ext/HOST_ENV.sh',
            host_env_sha256=H,kernel_executable='/usr/bin/python3.12',lane_root='/home/worker/lanes'))


@pytest.fixture
def mocked_owner(monkeypatch):
    """Deliberately synthetic root/source/transport, no production qualification."""
    monkeypatch.setattr(m.os,'geteuid',lambda:0)
    monkeypatch.setattr(m.os,'getuid',lambda:0)
    monkeypatch.setattr(m,'_snapshot',lambda *a:copy.deepcopy(SNAPSHOT))
    monkeypatch.setattr(m,'_transport_principal',lambda:PRINCIPAL.copy())
    seen=[]
    def transport(req, principal):
        seen.append(copy.deepcopy(req))
        # Genuine consumed local process object; inert synthetic transport,
        # not the production host-pull command or qualification evidence.
        child=m._POPEN_TYPE([sys.executable,'-I','-S','-c','pass'])
        child.wait(timeout=5)
        return m._canonical(response(req)),child
    monkeypatch.setattr(m,'_owned_transport',transport)
    return seen


def produce():
    return m.qualify_paid_host(**BINDING,python_path=request()['python_path'],capture_root=request()['capture_root'])


def consume(value, **changes):
    data=dict(BINDING);data.update(changes)
    return m.consume_paid_host_qualification(value,**data)


def test_actual_producer_path_and_one_time_consumption(mocked_owner):
    q=produce()
    assert len(mocked_owner)==1
    assert type(q) is m.PaidHostQualification
    observed=consume(q)
    assert observed==response(mocked_owner[0])
    assert observed['request']['nonce']!='nonce1'
    with pytest.raises(m.QualificationRefused):consume(q)


@pytest.mark.parametrize('supplied',[{},True,dict(returncode=0),dict(schema='mastermind.paid_host_observation/v2')])
def test_caller_data_never_qualifies(mocked_owner,supplied):
    with pytest.raises(m.QualificationRefused):consume(supplied)


def test_type_alone_and_serialization_never_qualify(mocked_owner):
    with pytest.raises(m.QualificationRefused):m.PaidHostQualification()
    with pytest.raises(m.QualificationRefused):consume(object.__new__(m.PaidHostQualification))
    q=produce()
    with pytest.raises(m.QualificationRefused):pickle.dumps(q)
    with pytest.raises(m.QualificationRefused):q._observation={}


@pytest.mark.parametrize('field,value',[
    ('host_ref','ubuntu1'),('release_sha','e'*40),('preimage_sha256','e'*64),
    ('source_manifest_sha256','e'*64),('hosts_path','/safe/other.json'),
    ('expected_sources',{n:'e'*64 for n in m.SOURCE_NAMES}),
])
def test_mismatched_transaction_cannot_consume(mocked_owner,field,value):
    with pytest.raises(m.QualificationRefused):consume(produce(),**{field:value})


@pytest.mark.parametrize('gate',['uid','realuid','pid','age','snapshot','principal'])
def test_root_process_freshness_and_current_join(mocked_owner,monkeypatch,gate):
    q=produce()
    if gate=='uid':monkeypatch.setattr(m.os,'geteuid',lambda:501)
    if gate=='realuid':monkeypatch.setattr(m.os,'getuid',lambda:501)
    if gate=='pid':monkeypatch.setattr(m.os,'getpid',lambda:q._pid+1)
    if gate=='age':monkeypatch.setattr(m.time,'monotonic',lambda:q._at+61)
    if gate=='snapshot':monkeypatch.setattr(m,'_snapshot',lambda *a:{})
    if gate=='principal':monkeypatch.setattr(m,'_transport_principal',lambda:{})
    with pytest.raises(m.QualificationRefused):consume(q)


def test_nonroot_refused_before_transport(mocked_owner,monkeypatch):
    monkeypatch.setattr(m.os,'geteuid',lambda:501)
    with pytest.raises(m.QualificationRefused):produce()
    assert mocked_owner==[]


@pytest.mark.parametrize('mutator',[
    lambda v:v['request'].__setitem__('nonce','different'),
    lambda v:v['request'].__setitem__('host_ref','ubuntu1'),
    lambda v:v['request'].__setitem__('source_manifest_sha256','e'*64),
    lambda v:v['request'].__setitem__('preimage_sha256','e'*64),
    lambda v:v['request'].__setitem__('context','different'),
    lambda v:v['binary'].__setitem__('path','/usr/bin/python3'),
    lambda v:v['binary'].__setitem__('sha256','tool-present'),
    lambda v:v['binary'].__setitem__('uid',99),
    lambda v:v['binary'].__setitem__('mode',stat.S_IFREG|0o777),
    lambda v:v['binary'].__setitem__('size',True),
    lambda v:v['binary'].__setitem__('team_identifier','fiction'),
    lambda v:v.__setitem__('worker_uid',0),
    lambda v:v.__setitem__('worker_gid',True),
    lambda v:v.__setitem__('boot_id','unknown'),
    lambda v:v.__setitem__('tools',['python3']),
    lambda v:v['capture_identity'].__setitem__('mode',stat.S_IFDIR|0o755),
    lambda v:v['capture_identity'].__setitem__('uid',0),
    lambda v:v['context_identity'].__setitem__('kernel_executable','/other/python'),
    lambda v:v['context_identity'].__setitem__('host_env_sha256','unknown'),
])
def test_mixed_wrong_or_telemetry_observation_refused(mocked_owner,monkeypatch,mutator):
    def transport(req,principal):
        v=response(req);mutator(v)
        return m._canonical(v),dict(pid=700,returncode=0)
    monkeypatch.setattr(m,'_owned_transport',transport)
    with pytest.raises(m.QualificationRefused):produce()


@pytest.mark.parametrize('raw',[b'{}',b'{"a":1,"a":2}',b'{"a":NaN}',b'x'*65537,b'',b'[]'])
def test_bad_json_cannot_be_observation(raw):
    with pytest.raises(m.QualificationRefused):m._observation(raw,request())


@pytest.mark.parametrize('field,value',[
    ('host_ref','-oProxyCommand=bad'),('python_path','/bad/../python'),
    ('python_path','/bin/python\ncommand'),('capture_root','/home/worker/other'),
    ('release_sha','e'*64),('probe_sha256','e'*64),('context','generic-telemetry'),
])
def test_request_refuses_unqualified_selection(field,value):
    p=request();p[field]=value
    with pytest.raises(m.QualificationRefused):m.build_paid_probe(p)


def test_command_is_exact_context_not_system_python():
    alias,command=m.build_paid_probe(request())
    assert alias=='ubuntu2'
    assert 'HOST_ENV.sh' in command and '/venv/bin' in command
    assert command.startswith('/usr/bin/python3 -I -S -B -c ')
    assert 'sealed_snapshot' in command
    assert 'source /proc/self/fd/' in command
    ast.parse(m._REMOTE_PROBE)


def test_backend_selection_mismatch_refused():
    with pytest.raises(m.QualificationRefused):m.prepare_paid_transport('ubuntu1',m._canonical(request()))


def test_source_and_registry_pin_is_not_tools_presence(monkeypatch):
    reg={'ubuntu2':dict(ssh_alias='ubuntu2',platform='linux',local=False,
        roles=['lanes'],allowed_modes=['glm'],qualification_only_modes=[])}
    def read(path,**kw):
        if str(path).endswith('hosts.json'):return m._canonical(reg),(1,2)
        return b'source',(1,2)
    monkeypatch.setattr(m,'_read_owned',read)
    hashes={n:hashlib.sha256(b'source').hexdigest() for n in m.SOURCE_NAMES}
    assert m._snapshot('/safe/hosts.json','ubuntu2',hashes)['alias']=='ubuntu2'
    for key,value in [('local',True),('platform','darwin'),('allowed_modes',[]),
            ('qualification_only_modes',['glm']),('ssh_alias','-option'),('roles',[]),
            ('local','false'),('allowed_modes',['glm','glm']),('allowed_modes',['glm',True]),
            ('qualification_only_modes',['grok','grok'])]:
        changed=copy.deepcopy(reg);changed['ubuntu2'][key]=value
        monkeypatch.setattr(m,'_read_owned',lambda path,**kw:
            (m._canonical(changed),(1,2)) if str(path).endswith('hosts.json') else (b'source',(1,2)))
        with pytest.raises(m.QualificationRefused):m._snapshot('/safe/hosts.json','ubuntu2',hashes)
    monkeypatch.setattr(m,'_read_owned',read)
    hashes['host_pull.sh']='e'*64
    with pytest.raises(m.QualificationRefused):m._snapshot('/safe/hosts.json','ubuntu2',hashes)


def remote_namespace():
    ns={'__name__':'inert_probe_fixture'}
    exec(compile(m._REMOTE_PROBE,'pinned-probe','exec'),ns)
    return ns


def test_remote_acl_presence_and_unknown_refuse_without_reads():
    ns=remote_namespace()
    for error in (None,errno.EACCES,errno.ENOTSUP):
        def xattr(*args):
            if error is not None:raise OSError(error,'fixture')
            return b'acl'
        ns['os']=SimpleNamespace(getxattr=xattr)
        with pytest.raises(ValueError):ns['acl'](9)
    ns['os']=SimpleNamespace(getxattr=mock.Mock(side_effect=OSError(errno.ENODATA,'fixture')))
    ns['acl'](9)


def test_remote_binary_and_context_fixture_no_host_access(monkeypatch):
    ns=remote_namespace();p=request()
    file_stat=SimpleNamespace(st_dev=1,st_ino=2,st_mode=stat.S_IFREG|0o755,
        st_uid=0,st_gid=0,st_size=1000,st_mtime_ns=100,st_ctime_ns=100)
    capture=SimpleNamespace(**{**file_stat.__dict__,'st_ino':3,'st_mode':stat.S_IFDIR|0o700,'st_uid':1000,'st_gid':1000})
    realpath=lambda path:'/usr/bin/python3.12' if path in (p['python_path'],'/proc/self/exe') else path
    fakepath=SimpleNamespace(**{name:getattr(os.path,name) for name in ('abspath','split','dirname','normpath','join')},realpath=realpath)
    link_stat=SimpleNamespace(**{**file_stat.__dict__,'st_mode':stat.S_IFLNK|0o777,'st_uid':1000})
    def fixture_stat(path,**kw):
        if path==p['capture_root']:return capture
        if path=='python3':return link_stat
        return file_stat
    fakeos=SimpleNamespace(path=fakepath,getuid=lambda:1000,getgid=lambda:1000,
        geteuid=lambda:1000,getegid=lambda:1000,stat=fixture_stat,
        lstat=lambda path:link_stat,readlink=lambda path:'/usr/bin/python3.12',
        fstat=lambda fd:capture,close=lambda fd:None)
    ns['os']=fakeos;ns['sys']=SimpleNamespace(platform='linux',executable=p['python_path'],version='3.12.10')
    ns['pwd']=SimpleNamespace(getpwuid=lambda uid:SimpleNamespace(pw_name='worker'),
        getpwnam=lambda name:SimpleNamespace(pw_uid=1000))
    ns['walk']=lambda path,uid:9;ns['acl']=lambda fd:None
    ns['read_file']=lambda path,uid,limit:(b'python' if path=='/usr/bin/python3.12' else b'context',file_stat)
    ns['open']=lambda *args,**kw:io.StringIO('12345678-1234-1234-1234-123456789abc')
    observed=ns['observe'](p)
    assert observed['binary']['sha256']==hashlib.sha256(b'python').hexdigest()
    assert observed['context_identity']['host_env_sha256']==hashlib.sha256(b'context').hexdigest()
    ns['sys'].executable='/usr/bin/python3'
    with pytest.raises(ValueError):ns['observe'](p)
    ns['sys'].executable=p['python_path']
    capture.st_mode=stat.S_IFDIR|0o755
    with pytest.raises(ValueError):ns['observe'](p)


def test_transport_owned_child_capture_inert_local_process(monkeypatch):
    # Replaces ONLY the process at the syscall boundary with inert local Python;
    # no host_pull command, SSH, user change, credential or host probe executes.
    actual=subprocess.Popen;seen=[]
    def spawn(argv,**kw):
        seen.append((argv,copy.deepcopy({k:v for k,v in kw.items() if k not in ('stdin','stdout','stderr')})))
        return actual([sys.executable,'-I','-S','-c',
            'import sys;sys.stdin.buffer.read();sys.stdout.buffer.write(b"fixture")'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    monkeypatch.setattr(m.subprocess,'Popen',spawn)
    raw,child=m._owned_transport(request(),PRINCIPAL)
    assert raw==b'fixture' and type(child) is m._POPEN_TYPE and child.returncode==0 and child.pid>0
    argv,kw=seen[0]
    assert argv[0]=='/bin/bash' and argv[-2:]==['--paid-qualification','ubuntu2']
    assert kw['user']==501 and kw['group']==20 and kw['extra_groups']==[]
    assert kw['env']['HOME']=='/Users/operator'
    assert not any(k.startswith('HOST_PULL_') for k in kw['env'])


def test_shell_transport_is_shared_and_qualification_bypasses_cache():
    shell=(SOURCE/'host_pull.sh').read_text()
    assert sum("perl -e 'alarm 25; exec @ARGV' ssh" in line for line in shell.splitlines() if not line.lstrip().startswith("#"))==1
    assert 'OUT=$(run_probe "$is_local" "$alias" "$probe")' in shell
    qual=shell[shell.index('if [ "$PAID_REQUESTED" -eq 1 ]; then'):shell.index('pass_once() {')]
    assert 'run_probe 0 "$PAID_ALIAS" "$PAID_PROBE"' in qual
    assert 'write_state' not in qual and 'mkdir' not in qual
    subprocess.run(['/bin/bash','-n',str(SOURCE/'host_pull.sh')],check=True)


@pytest.mark.parametrize('mode',['nonzero','stderr','oversize','timeout'])
def test_owned_transport_failure_has_no_retry_or_other_host(monkeypatch,mode):
    actual=subprocess.Popen;children=[]
    script={'nonzero':'import sys;sys.stdin.buffer.read();sys.exit(7)',
        'stderr':'import sys;sys.stdin.buffer.read();sys.stderr.write("fixture");print("ok")',
        'oversize':'import sys;sys.stdin.buffer.read();sys.stdout.buffer.write(b"x"*65537)',
        'timeout':'import time;time.sleep(10)'}[mode]
    def spawn(*a,**k):
        child=actual([sys.executable,'-I','-S','-c',script],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        children.append(child);return child
    monkeypatch.setattr(m.subprocess,'Popen',spawn)
    if mode=='timeout':
        ticks=iter([0,40])
        monkeypatch.setattr(m,'time',SimpleNamespace(monotonic=lambda:next(ticks,40)))
    with pytest.raises(m.QualificationRefused):m._owned_transport(request(),PRINCIPAL)
    assert len(children)==1 and children[0].poll() is not None


def test_qualification_source_drift_after_transport_refused(mocked_owner,monkeypatch):
    snapshots=iter([SNAPSHOT,dict(SNAPSHOT,registry_sha256='e'*64)])
    monkeypatch.setattr(m,'_snapshot',lambda *a:next(snapshots))
    with pytest.raises(m.QualificationRefused):produce()
    assert len(mocked_owner)==1


def test_actual_shell_modes_use_only_inert_transport(tmp_path):
    """Exercise changed shell + backend using fake ssh, no host transport."""
    import shutil
    ext=tmp_path/'ext';ext.mkdir()
    for name in ('host_pull.sh','host_pull_backend.py','host_pull_probe.template','paid_host_qualification.py','paid_initializer.py'):
        shutil.copyfile((SOURCE/name if (SOURCE/name).exists() else SOURCE.parent/'source'/name),ext/name)
    binpath=tmp_path/'bin';binpath.mkdir()
    ssh=binpath/'ssh'
    ssh.write_text('#!/bin/sh\nprintf "fixture-response\\n"\n')
    ssh.chmod(0o700)
    env={**os.environ,'PATH':str(binpath)+':'+str(Path(sys.executable).parent)+':/usr/bin:/bin',
        'HOST_PULL_STATE_DIR':str(tmp_path/'must-not-be-created'),
        'HOST_PULL_PIDFILE':str(tmp_path/'must-not-be-created'/'pid')}
    # Caller Python search path cannot substitute a forged protocol producer.
    poison=tmp_path/'poison';poison.mkdir()
    (poison/'sitecustomize.py').write_text('raise RuntimeError("untrusted site executed")')
    env['PYTHONPATH']=str(poison)
    # These copied files are deliberately NOT a Root-owned selected release.
    # The new preexec source verifier must refuse before the inert SSH marker.
    result=subprocess.run(['/bin/bash',str(ext/'host_pull.sh'),'--paid-qualification','ubuntu2'],
        input=m._canonical(request()),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=5)
    assert result.returncode==78 and result.stdout==b''
    assert not (tmp_path/'must-not-be-created').exists()
    bad=subprocess.run(['/bin/bash',str(ext/'host_pull.sh'),'--paid-qualification',''],
        input=m._canonical(request()),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=5)
    assert bad.returncode==78 and not (tmp_path/'must-not-be-created').exists()
    # Legacy --once --host uses same shell transport and retains writer call.
    (ext/'host_pull_backend.py').write_text('import sys\nfrom pathlib import Path\n'
        'if sys.argv[1]=="read-hosts":print("ubuntu2|0|ubuntu2|/home|0")\n'
        'elif sys.argv[1]=="write-state":\n'
        ' Path(sys.argv[2],"called").write_text(sys.argv[5]);print("written")\n')
    state=tmp_path/'legacy-state';env['HOST_PULL_STATE_DIR']=str(state)
    result=subprocess.run(['/bin/bash',str(ext/'host_pull.sh'),'--once','--host','ubuntu2'],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=5)
    assert result.returncode==0 and b'host=ubuntu2 rc=0' in result.stdout
    assert (state/'called').read_text()=='fixture-response'


@pytest.mark.parametrize('fault',[None,'owner','writable','drift','symlink','hardlink','truncated'])
def test_pinned_local_reader_physical_custody_and_drift(monkeypatch,fault):
    fileinfo=SimpleNamespace(st_dev=1,st_ino=2,st_mode=stat.S_IFREG|0o444,
        st_uid=0,st_gid=0,st_size=3,st_mtime_ns=10,st_ctime_ns=10,st_nlink=1)
    dirinfo=SimpleNamespace(**{**fileinfo.__dict__,'st_mode':stat.S_IFDIR|0o755})
    if fault=='owner':fileinfo.st_uid=501
    if fault=='writable':fileinfo.st_mode|=0o020
    if fault=='hardlink':fileinfo.st_nlink=2
    calls=[];reads=iter([b'ab' if fault=='truncated' else b'abc',b''])
    fstats=0
    def openfile(path,flags,**kw):
        calls.append((path,flags))
        if fault=='symlink' and path=='file':raise OSError(errno.ELOOP,'fixture')
        return {'/':10,'safe':11,'file':12}[path]
    def fstat(fd):
        nonlocal fstats
        if fd!=12:return dirinfo
        fstats+=1
        if fault=='drift' and fstats>1:
            return SimpleNamespace(**{**fileinfo.__dict__,'st_ino':3})
        return fileinfo
    fake=SimpleNamespace(**{name:getattr(os,name) for name in ('O_RDONLY','O_DIRECTORY','O_NOFOLLOW','O_NONBLOCK')},
        open=openfile,fstat=fstat,stat=lambda *a,**kw:fileinfo,
        read=lambda *a:next(reads),close=lambda fd:None)
    monkeypatch.setattr(m,'os',fake)
    if fault is None:
        assert m._read_owned('/safe/file',owners={0})[0]==b'abc'
    else:
        with pytest.raises((m.QualificationRefused,OSError)):
            m._read_owned('/safe/file',owners={0})
    assert all(flags & os.O_NOFOLLOW for path,flags in calls)


def test_result_does_not_alias_opaque_owner_evidence(mocked_owner):
    q=produce();value=consume(q)
    value['binary']['sha256']='e'*64
    assert q._observation['binary']['sha256']==H


def test_callback_keys_headers_and_extra_sources_are_not_accepted():
    class Trap:
        def __eq__(self,other):raise AssertionError('callback invoked')
    for field in ('schema','context'):
        p=request();p[field]=Trap()
        with pytest.raises(m.QualificationRefused):m.build_paid_probe(p)
    p=request();p['sources_sha256']['foreign']='e'*64
    with pytest.raises(m.QualificationRefused):m.build_paid_probe(p)


def test_dict_receipt_cannot_substitute_for_retained_owned_process(mocked_owner,monkeypatch):
    q=produce()
    # Deliberately corrupt private fixture state to exercise the consumer;
    # ordinary callers cannot replace a sealed attribute.
    object.__setattr__(q,'_child',dict(pid=700,returncode=0))
    with pytest.raises(m.QualificationRefused):consume(q)


def test_old_postsource_request_cannot_enter_initializer_transport(mocked_owner):
    old=request();old['schema']='mastermind.paid_host_probe_request/v1'
    with pytest.raises(m.QualificationRefused):m.build_paid_probe(old)
    assert mocked_owner==[]


def test_paid_shell_transport_enforces_fixed_host_keys_before_fake_ssh(tmp_path):
    """Actual shell argv only; backend/SSH are inert fixture executables."""
    import shutil
    ext=tmp_path/'ext';ext.mkdir()
    shutil.copyfile(SOURCE/'host_pull.sh',ext/'host_pull.sh')
    (ext/'host_pull_probe.template').write_text('unused telemetry probe')
    (ext/'host_pull_backend.py').write_text('import sys\nassert sys.argv[1:]==["paid-qualification","ubuntu2"]\nprint("fixed-fixture-alias\\ninert-fixture-command")\n')
    binpath=tmp_path/'bin';binpath.mkdir()
    ssh=binpath/'ssh';ssh.write_text('#!/bin/sh\nprintf "%s\\000" "$@" > "$MM_ARGV_FILE"\nprintf fixture-only\n');ssh.chmod(0o700)
    record=tmp_path/'argv'
    env={**os.environ,'PATH':str(binpath)+':'+str(Path(sys.executable).parent)+':/usr/bin:/bin',
         'MM_ARGV_FILE':str(record),'HOST_PULL_STATE_DIR':str(tmp_path/'no-state')}
    result=subprocess.run(['/bin/bash',str(ext/'host_pull.sh'),'--paid-qualification','ubuntu2'],
        env=env,capture_output=True,timeout=5)
    assert result.returncode==0 and result.stdout==b'fixture-only'
    assert record.read_bytes().split(b'\0')==[b'-o',b'BatchMode=yes',b'-o',b'ConnectTimeout=8',
        b'-o',b'StrictHostKeyChecking=yes',b'-o',b'UpdateHostKeys=no',
        b'fixed-fixture-alias',b'inert-fixture-command',b'']
    assert not (tmp_path/'no-state').exists()
