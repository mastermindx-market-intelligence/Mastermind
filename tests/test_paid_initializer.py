"""Credentialless pure/OS primitive tests. Linux execution is CI-only here."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import venv

import pytest
from ops.native_fabric.quota_continuity.candidate import paid_initializer as m


def commitment():
    return dict(schema_version=m.SCHEMA,host_ref='ubuntu2',transport_alias='ubuntu2',
        lane_root='/home/worker/lanes',account=dict(uid=1000,gid=1000,user='worker',home='/home/worker'),
        bootstrap_python=dict(path='/usr/bin/python3',real_path='/usr/bin/python3.12',sha256='a'*64),
        launch_python=dict(path='/usr/bin/python3',real_path='/usr/bin/python3.12',sha256='a'*64),
        host_env=dict(path='/home/worker/lanes/ext/HOST_ENV.sh',sha256='b'*64,size=64,uid=1000,gid=1000,mode=0o600),
        initialized_context=dict(home='/home/worker',glm_config='/home/worker/lanes/ext/glm.json'),
        initialization_contract=m.CONTRACT,purpose=m.PURPOSE,
        startup=dict(profile='cpython-3.12-linux-root-prefix.v1',prefix='/usr',exec_prefix='/usr',base_prefix='/usr',base_exec_prefix='/usr'))


def selectors():return dict(host_ref='ubuntu2',transport_alias='ubuntu2',python_path='/usr/bin/python3',capture_root='/home/worker/lanes/ext/lanes')


def _linux_completion(request,profile=None):
    # Structured Actions notice only after the real assertions complete. This
    # gives the retained safe annotation API exact-case evidence; no XML or
    # raw terminal escape rendering is required or claimed.
    reporter=request.config.pluginmanager.getplugin('terminalreporter')
    if reporter is not None:
        with request.getfixturevalue('capsys').disabled():
            reporter.write_line('\n::notice file=tests/test_paid_initializer.py,title=H1 Linux case executed::'
                +request.node.name+' ASSERTIONS_COMPLETED Python '+'.'.join(map(str,sys.version_info[:3]))
                +(' launch_fixture='+profile if profile else ''))


def _system_fixture_launch(*,no_site=False):
    """Select only an existing fixed Root/ACL-free CPython3.12 distribution.

    This test precondition cannot grant production trust. The actual owner and
    child still recheck it. No install/chmod/ACL change or alternate lookup.
    """
    import errno
    import stat
    logical=Path('/usr/bin/python3')
    try:
        real=logical.resolve(strict=True)
        if real.name!='python3.12':return None
        def guarded(path,allow_link=False):
            info=path.lstat()
            if info.st_uid!=0 or info.st_mode&0o022 or (path.is_symlink() and not allow_link):raise ValueError()
            for key in ('system.posix_acl_access','system.posix_acl_default'):
                try:os.getxattr(path,key,follow_symlinks=False)
                except OSError as error:
                    if error.errno not in (errno.ENODATA,getattr(errno,'ENOATTR',errno.ENODATA)):raise
                else:raise ValueError()
        for path in (logical,real):
            guarded(path,allow_link=path==logical)
            for ancestor in path.parents:guarded(ancestor)
        count=0
        # The fixed system fixture supports only the existing /usr layout.
        # Qualify its image/startup metadata before executing getpath.
        for prefix in ('/usr',):
            library=Path(prefix)/'lib/python3.12';guarded(library)
            if no_site:
                for name,info in m._no_site_startup_entries(str(library)):
                    count+=1
                    if count>20000:raise ValueError()
                    if name==str(library/'sitecustomize.py') and stat.S_ISLNK(info.st_mode):
                        directory=os.open(library,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                        try:
                            with m._IgnoredNoSiteNode(directory):pass
                        finally:os.close(directory)
                    else:guarded(Path(name))
            else:
                for parent,dirs,files in os.walk(library,followlinks=False):
                    dirs[:]=[v for v in dirs if v not in ('site-packages','dist-packages')]
                    for leaf in dirs+files:
                        count+=1
                        if count>20000:raise ValueError()
                        guarded(Path(parent)/leaf)
            optional=Path(prefix)/'lib/python312.zip'
            if optional.exists():guarded(optional)
        for directory in (logical.parent,logical.parent.parent):
            if (directory/'pyvenv.cfg').exists() or any(v.name.endswith('._pth') for v in directory.iterdir()):return None
        code='import json,sys;print(json.dumps(dict(version=list(sys.version_info[:2]),prefixes=[sys.prefix,sys.exec_prefix,sys.base_prefix,sys.base_exec_prefix])))'
        if no_site:code=m.NO_SITE_PREAMBLE+code+'\n_paid_no_site_check()'
        data=json.loads(subprocess.check_output([str(logical),'-I','-S','-B','-c',code],stderr=subprocess.DEVNULL,timeout=5))
        if data['version']!=[3,12]:return None
        if data['prefixes']!=['/usr']*4:return None
        return logical
    except (OSError,ValueError,subprocess.SubprocessError):return None


def _observer_metadata_fixture(probe,*,exact,prefixes,root_directories=(),root_files=()):
    """Fallback ONLY: finite ACL and enumerated directory metadata premise.

    The real observer body/read/identity validators remain. No production source,
    actual host ACL, environment or output record is changed by this fixture.
    """
    exact=sorted(set(map(str,exact)));prefixes=sorted(set(map(str,prefixes)))
    root_directories=sorted(set(map(str,root_directories)));root_files=sorted(set(map(str,root_files)))
    return ("import os,errno,stat\n_fixture_raw_getxattr=os.getxattr\n"
        +"_fixture_root_directories="+repr(root_directories)+"\n_fixture_root_files="+repr(root_files)+"\n"
        +"_fixture_raw_stat=os.stat;_fixture_raw_fstat=os.fstat\n"
        +"class _FixtureRootMetadata:\n"
        +"    def __init__(self,value):self._value=value;self.st_uid=0;self.st_mode=value.st_mode&~0o022\n"
        +"    def __getattr__(self,key):return getattr(self._value,key)\n"
        +"def _fixture_directory_metadata(value,name):\n"
        +"    return _FixtureRootMetadata(value) if (stat.S_ISDIR(value.st_mode) and name in _fixture_root_directories) or (stat.S_ISREG(value.st_mode) and name in _fixture_root_files) else value\n"
        +"def _fixture_fstat(fd):\n"
        +"    return _fixture_directory_metadata(_fixture_raw_fstat(fd),os.path.realpath('/proc/self/fd/'+str(fd)))\n"
        +"def _fixture_stat(name,*args,**kwargs):\n"
        +"    actual=os.path.join(os.readlink('/proc/self/fd/'+str(kwargs['dir_fd'])),str(name)) if kwargs.get('dir_fd') is not None else os.fspath(name)\n"
        +"    actual=os.path.normpath(actual)\n"
        +"    return _fixture_directory_metadata(_fixture_raw_stat(name,*args,**kwargs),actual)\n"
        +"os.fstat=_fixture_fstat;os.stat=_fixture_stat\n"
        +"_fixture_exact="+repr(exact)+"\n_fixture_prefixes="+repr(prefixes)+"\n"
        +"def _fixture_getxattr(name,key,*args,**kwargs):\n"
        +"    actual=os.path.realpath('/proc/self/fd/'+str(name)) if isinstance(name,int) else str(name)\n"
        +"    if key in ('system.posix_acl_access','system.posix_acl_default') and (actual in _fixture_exact or any(actual==p or actual.startswith(p+'/') for p in _fixture_prefixes)):\n"
        +"        raise OSError(errno.ENODATA,'inert trusted metadata has no ACL')\n"
        +"    return _fixture_raw_getxattr(name,key,*args,**kwargs)\n"
        +"os.getxattr=_fixture_getxattr\n"+probe)


_DIAGNOSTIC_SCHEMA='mastermind.inert_observer_guard.v1'
_DIAGNOSTIC_FUNCTIONS={'<module>','fail','acl','walk','read_file','observe'}
_DIAGNOSTIC_FIELDS={'uid','write_mode','kind','size','acl','selector_or_context','identity_or_content'}
_OBSERVER_DIAGNOSTIC_PREFIX=r"""
import sys as _ds, json as _dj, os as _do, stat as _dt

def _inert_guard_diagnostic(error):
    sites=[];trace=error.__traceback__
    while trace is not None:
        name=trace.tb_frame.f_code.co_name;fields=[]
        if name in ('<module>','fail','acl','walk','read_file','observe'):
            item=trace.tb_frame.f_locals.get('s') if name=='walk' else trace.tb_frame.f_locals.get('before') if name=='read_file' else None
            if item is not None:
                if getattr(item,'st_uid',_do.getuid()) not in (0,_do.getuid()):fields.append('uid')
                if getattr(item,'st_mode',0)&0o022:fields.append('write_mode')
                if name=='read_file' and not _dt.S_ISREG(getattr(item,'st_mode',0)):fields.append('kind')
            if name=='acl':fields.append('acl')
            sites.append(dict(function=name,line=trace.tb_lineno,fields=fields))
        trace=trace.tb_next
    kind=type(error).__name__
    if kind not in ('ValueError','AssertionError','OSError','PermissionError'):kind='REFUSAL'
    number=getattr(error,'errno',None)
    if type(number)is not int or not 0<=number<=4096:number=None
    _ds.stdout.write(_dj.dumps(dict(schema='mastermind.inert_observer_guard.v1',kind=kind,sites=sites[-6:],errno=number),sort_keys=True,separators=(',',':'))+'\n')
_ds.excepthook=lambda typ,error,trace:_inert_guard_diagnostic(error)
"""


def _decode_observer_diagnostic(raw):
    """Only fixed test-owned fields may reach an annotation; never raw output."""
    try:
        if type(raw) not in (bytes,bytearray) or not 0<len(raw)<=4096:return None
        def pairs(items):
            value={}
            for key,item in items:
                if key in value:raise ValueError()
                value[key]=item
            return value
        value=json.loads(raw,object_pairs_hook=pairs)
        if type(value)is not dict or set(value)!={'schema','kind','sites','errno'}:return None
        if value['schema']!=_DIAGNOSTIC_SCHEMA or value['kind'] not in ('ValueError','AssertionError','OSError','PermissionError','REFUSAL'):return None
        if value['errno'] is not None and (type(value['errno'])is not int or not 0<=value['errno']<=4096):return None
        if type(value['sites'])is not list or len(value['sites'])>6:return None
        for site in value['sites']:
            if type(site)is not dict or set(site)!={'function','line','fields'}:return None
            if site['function'] not in _DIAGNOSTIC_FUNCTIONS or type(site['line'])is not int or not 1<=site['line']<=100000:return None
            if type(site['fields'])is not list or len(site['fields'])>7 or any(type(x)is not str or x not in _DIAGNOSTIC_FIELDS for x in site['fields']):return None
        return value
    except (ValueError,TypeError,UnicodeError,RecursionError):return None


def _guard_notice(fixture,value,*,phase='PIPELINE_REFUSAL'):
    if fixture is None:return
    if phase not in ('FINAL_OBSERVER_REFUSAL','CLEANUP_AFTER_OBSERVER_REFUSAL','PIPELINE_REFUSAL'):phase='PIPELINE_REFUSAL'
    try:public=_decode_observer_diagnostic(json.dumps(value,allow_nan=False).encode())
    except (ValueError,TypeError):public=None
    if public is None:public=dict(schema=_DIAGNOSTIC_SCHEMA,kind='REFUSAL',sites=[],errno=None)
    reporter=fixture.config.pluginmanager.getplugin('terminalreporter')
    if reporter is not None:
        with fixture.getfixturevalue('capsys').disabled():
            reporter.write_line('\n::error file=tests/test_paid_initializer.py,title=H1 Linux guard diagnostic::'
                +fixture.node.name+' phase='+phase+' '+json.dumps(public,sort_keys=True,separators=(',',':'),ensure_ascii=True))


def _inert_bootstrap(request,probe,*,owner=m,diagnostic_request=None):
    # Final observer only. Capture/caller environment and stderr stay private.
    from unittest.mock import patch
    original=owner._bounded_child;diagnostic=[]
    def traced(argv,**kwargs):
        final=len(argv)==7 and argv[1:5]==['-I','-S','-B','-c'] and 'def observe(p):' in argv[5]
        if final:
            before='    except Exception:\n        sys.exit(78)'
            assert argv[5].count(before)==1
            argv=list(argv);argv[5]=_OBSERVER_DIAGNOSTIC_PREFIX+argv[5].replace(before,'    except Exception as _error:\n        _inert_guard_diagnostic(_error)\n        sys.exit(78)')
        try:return original(argv,**kwargs)
        except owner.InitializerCommitmentRefused as error:
            if final:
                frame=error.__traceback__
                while frame is not None:
                    if frame.tb_frame.f_code is original.__code__:
                        value=_decode_observer_diagnostic(frame.tb_frame.f_locals.get('raw'))
                        if value is not None:diagnostic.append((value,error))
                    frame=frame.tb_next
            raise
    try:
        with patch.object(owner,'_bounded_child',traced):return owner.run_bootstrap(request,probe)
    except Exception as error:
        frame=error.__traceback__;site=None
        while frame is not None:
            if frame.tb_frame.f_code.co_filename==owner.__file__ and frame.tb_frame.f_code.co_name!='refuse':site=frame.tb_lineno
            frame=frame.tb_next
        public=diagnostic[-1][0] if diagnostic else dict(schema=_DIAGNOSTIC_SCHEMA,kind='REFUSAL',sites=[],errno=None)
        phase=('FINAL_OBSERVER_REFUSAL' if diagnostic[-1][1] is error else 'CLEANUP_AFTER_OBSERVER_REFUSAL') if diagnostic else 'PIPELINE_REFUSAL'
        _guard_notice(diagnostic_request,public,phase=phase)
        # Suppress producer frames that may contain environment arguments. The
        # fixed source line and allowlisted diagnostic retain the real refusal.
        raise AssertionError('inert initializer guard line='+str(site)+' phase='+phase+' diagnostic='+json.dumps(public,sort_keys=True,separators=(',',':'))) from None


def test_closed_commitment_is_detached_expected_input():
    value=commitment();raw=m.canonical(value);proved=m.decode_commitment(raw,hashlib.sha256(raw).hexdigest(),**selectors())
    assert proved==value and proved is not value
    value['account']['user']='mutated';assert proved['account']['user']=='worker'


@pytest.mark.parametrize('field,value',[(k,v) for k in ('host_ref','transport_alias') for v in ('-option','üser',None,True)]+[
    ('purpose','worker-start'),('initialization_contract','source-path'),('lane_root','/x/../lanes'),
    ('lane_root','//home/worker/lanes'),('startup',{}),('unknown','value')])
def test_bad_closed_input_refuses(field,value):
    c=commitment();c[field]=value
    with pytest.raises(m.InitializerCommitmentRefused):m.validate_commitment(c,**selectors())


@pytest.mark.parametrize('section,key,value',[
    ('account','uid',True),('account','gid',-1),('host_env','mode',0o622),('host_env','size',65537),
    ('host_env','sha256','newly-observed'),('bootstrap_python','path','python3'),
    ('launch_python','path','/home/worker/python3'),('initialized_context','home','/other'),
    ('initialized_context','glm_config','/a/../secret'),('startup','profile','mutable-venv'),
    ('startup','prefix','relative')])
def test_context_and_identity_mutation_refuses(section,key,value):
    c=commitment();c[section][key]=value
    with pytest.raises(m.InitializerCommitmentRefused):m.validate_commitment(c,**selectors())


@pytest.mark.parametrize('raw',[b'{}',b'{"a":1,"a":2}',b'{"a":NaN}',b'[]',b'x'*16385])
def test_raw_commitment_refuses(raw):
    with pytest.raises(m.InitializerCommitmentRefused):m.decode_commitment(raw,hashlib.sha256(raw).hexdigest(),**selectors())


def test_different_input_digest_is_not_approval():
    with pytest.raises(m.InitializerCommitmentRefused):m.decode_commitment(m.canonical(commitment()),'f'*64,**selectors())


@pytest.mark.skipif(sys.platform!='linux',reason='requires actual Linux memfd sealing')
def test_hook_snapshot_cannot_change_after_approval_even_when_original_changes(tmp_path,request):
    original=tmp_path/'HOST_ENV.sh';raw=b'export MM_INERT_APPROVED=exact\n';original.write_bytes(raw)
    fd=m.sealed_snapshot(original.read_bytes())
    try:
        original.write_bytes(b'echo wrong\n')
        for operation in (lambda:os.write(fd,b'x'),lambda:os.ftruncate(fd,0)):
            with pytest.raises(OSError):operation()
        result=subprocess.run(['/bin/bash','--noprofile','--norc','-c',f'source /proc/self/fd/{fd}; printf %s "$MM_INERT_APPROVED"'],
            pass_fds=(fd,),capture_output=True,check=True)
        assert result.stdout==b'exact'
    finally:os.close(fd)
    _linux_completion(request)


@pytest.mark.skipif(sys.platform!='linux' or sys.version_info[:2]!=(3,12),reason='requires actual Linux CPython3.12 fd-exec/getpath')
def test_actual_pinned_image_exec_matches_normal_isolated_venv_startup(tmp_path,request):
    """Kernel image, argv0 and venv configuration are separate observations."""
    root=tmp_path/'venv';venv.EnvBuilder(with_pip=False).create(root)
    logical=root/'bin/python3';real=logical.resolve(strict=True)
    code='import json,os,sys;print(json.dumps(dict(executable=sys.executable,prefix=sys.prefix,exec_prefix=sys.exec_prefix,base_prefix=sys.base_prefix,base_exec_prefix=sys.base_exec_prefix,kernel=os.path.realpath("/proc/self/exe"),flags=[sys.flags.isolated,sys.flags.no_site,sys.dont_write_bytecode])))'
    normal=subprocess.check_output([str(logical),'-I','-S','-B','-c',code])
    fd=os.open(real,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        by_fd=subprocess.check_output([str(logical),'-I','-S','-B','-c',code],executable=f'/proc/self/fd/{fd}',pass_fds=(fd,))
        assert json.loads(by_fd)==json.loads(normal)
        assert json.loads(by_fd)['kernel']==str(real)
        # argv0 may label startup DATA, but cannot alter the held kernel image.
        foreign=tmp_path/'foreign-python3'
        foreign.symlink_to(real)
        changed=subprocess.check_output([str(foreign),'-I','-S','-B','-c',code],executable=f'/proc/self/fd/{fd}',pass_fds=(fd,))
        assert json.loads(changed)['kernel']==str(real)
        assert json.loads(changed)['executable']!=str(logical)
    finally:os.close(fd)
    _linux_completion(request)


@pytest.mark.skipif(sys.platform!='linux' or sys.version_info[:2]!=(3,12),reason='requires actual Linux CPython3.12 initializer/getpath')
def test_actual_linux_initializer_exec_and_selector_drift_before_hook(tmp_path,monkeypatch,request):
    """Real FD/snapshot/Bash/getpath; trusted-platform metadata is simulated.

    No remote/system mutation, credential read or provider is used. This does
    not qualify the current host's package ownership/trust or a live hook.
    """
    import pwd
    import tempfile
    from tests import test_paid_host_qualification as qualifier
    if os.getuid()==0:pytest.skip('production qualifier requires a non-Root transport account')
    account=pwd.getpwuid(os.getuid())
    # The hosted toolcache supplies LD_LIBRARY_PATH. This inert fixture models
    # the supported clean bootstrap premise; production never normalizes it.
    for key in tuple(os.environ):
        if key.startswith(('LD_','BASH_FUNC_')) or key in ('BASH_ENV','ENV','PYTHONHOME','PYTHONEXECUTABLE','__PYVENV_LAUNCHER__'):
            monkeypatch.delenv(key)
    bootstrap=Path(sys.executable).with_name('python3')
    system_launch=_system_fixture_launch()
    logical=system_launch or bootstrap
    monkeypatch.setenv('PATH',str(logical.parent)+':/usr/bin:/bin')
    assert logical.exists()
    real=logical.resolve()
    observed=json.loads(subprocess.check_output([str(logical),'-I','-S','-B','-c',
        'import json,sys;print(json.dumps({k:getattr(sys,k) for k in ("prefix","exec_prefix","base_prefix","base_exec_prefix")}))']))
    rawstat=os.stat;rawfstat=os.fstat;rawlstat=os.lstat;rawxattr=os.getxattr
    protected=([str(bootstrap.resolve()),str(bootstrap.parent)] if system_launch else [str(real),str(logical.parent),*set(observed.values())])
    ancestry=(bootstrap.resolve(),bootstrap) if system_launch else (real,logical,*map(Path,observed.values()))
    ancestors={str(v) for p in ancestry for v in p.parents}
    private=[];fault_acl=False
    def distribution(name):
        return str(name) in ancestors or any(str(name)==p or str(name).startswith(p+'/') for p in protected)
    def root_view(info):
        fields=list(info);fields[4]=0;fields[0]&=~0o022
        return os.stat_result(fields)
    def owned_fstat(fd):
        info=rawfstat(fd)
        try:name=os.path.realpath('/proc/self/fd/'+str(fd))
        except OSError:return info
        return root_view(info) if distribution(name) else info
    def owned_stat(name,*args,**kwargs):
        info=rawstat(name,*args,**kwargs)
        if kwargs.get('dir_fd') is not None:
            name=os.path.join(os.readlink('/proc/self/fd/'+str(kwargs['dir_fd'])),str(name))
        return root_view(info) if distribution(name) else info
    def owned_lstat(name,*args,**kwargs):
        info=rawlstat(name,*args,**kwargs)
        return root_view(info) if distribution(name) else info
    def modeled_xattr(name,key,*args,**kwargs):
        # Only metadata of the fixed image/startup chain and this disposable
        # private account chain is modeled; no general ACL bypass exists.
        actual=os.path.realpath('/proc/self/fd/'+str(name)) if isinstance(name,int) else str(name)
        modeled=distribution(actual) or actual in private or any(actual.startswith(p+'/') for p in private[-1:])
        if key in ('system.posix_acl_access','system.posix_acl_default') and modeled:
            if fault_acl and actual==str(hook):return b'inert-extended-acl'
            import errno
            raise OSError(errno.ENODATA,'inert trusted metadata has no ACL')
        return rawxattr(name,key,*args,**kwargs)
    with tempfile.TemporaryDirectory(prefix='.mmx-inert-init-',dir=account.pw_dir) as scratch:
        private.extend([str(v) for v in Path(scratch).parents]+[scratch])
        lane=Path(scratch)/'lanes';(lane/'ext/lanes').mkdir(parents=True,mode=0o700)
        hook=lane/'ext/HOST_ENV.sh';config=Path(scratch)/'not-read.json'
        hook.write_text('export GLM_CONFIG='+str(config)+'\n');hook.chmod(0o600)
        c=commitment();c.update(lane_root=str(lane),account=dict(uid=os.getuid(),gid=os.getgid(),user=account.pw_name,home=account.pw_dir),
            bootstrap_python=dict(path=str(bootstrap),real_path=str(bootstrap.resolve()),sha256=hashlib.sha256(bootstrap.resolve().read_bytes()).hexdigest()),
            launch_python=dict(path=str(logical),real_path=str(real),sha256=hashlib.sha256(real.read_bytes()).hexdigest()),
            startup=dict(profile='cpython-3.12-linux-root-prefix.v1',**observed),
            host_env=dict(path=str(hook),sha256=hashlib.sha256(hook.read_bytes()).hexdigest(),size=hook.stat().st_size,uid=os.getuid(),gid=os.getgid(),mode=0o600),
            initialized_context=dict(home=account.pw_dir,glm_config=str(config)))
        req=qualifier.request();req.update(python_path=str(logical),capture_root=str(lane/'ext/lanes'),initializer_commitment=c,
            initializer_commitment_sha256=hashlib.sha256(m.canonical(c)).hexdigest())
        # Explicit ownership/mode/ACL-only trusted-platform seam; actual child/process/
        # image/getpath/Bash/immutable FD and protocol validators stay real.
        monkeypatch.setattr(os,'fstat',owned_fstat);monkeypatch.setattr(os,'stat',owned_stat);monkeypatch.setattr(os,'lstat',owned_lstat);monkeypatch.setattr(os,'getxattr',modeled_xattr)
        monkeypatch.setenv('HOME',account.pw_dir)
        probe=qualifier.m._REMOTE_PROBE if system_launch else _observer_metadata_fixture(qualifier.m._REMOTE_PROBE,exact=ancestors|set(private),prefixes=protected+[scratch],root_directories=ancestors,root_files=[real])
        result=json.loads(_inert_bootstrap(req,probe,diagnostic_request=request))
        assert result['binary']['real_path']==str(real)
        assert result['pre_execution']['snapshot_sealed'] is True
        assert result['context_identity']['host_env_sha256']==c['host_env']['sha256']
        assert not config.exists()  # Selector was compared, never opened/read.
        # Hook-created Bash functions used to forge command selection and
        # replace exec with arbitrary observer JSON. They are no longer called:
        # the original pinned parent launches the genuine fixed probe itself.
        forged=Path(scratch)/'shadow-exec-must-not-run'
        hook.write_text('export GLM_CONFIG='+str(config)+'\n'
            +'command() { printf /forged/python3; }; exec() { echo forged > '+str(forged)+'; printf "{}"; }; export -n -f command exec\n')
        c['host_env'].update(sha256=hashlib.sha256(hook.read_bytes()).hexdigest(),size=hook.stat().st_size)
        req['initializer_commitment_sha256']=hashlib.sha256(m.canonical(c)).hexdigest()
        actual=json.loads(_inert_bootstrap(req,probe,diagnostic_request=request))
        assert actual['binary']['real_path']==str(real) and not forged.exists()
        # Unsupported startup projection refuses before the approved hook body.
        marker=Path(scratch)/'must-not-exist'
        hook.write_text('echo effect > '+str(marker)+'\nexport GLM_CONFIG='+str(config)+'\n')
        c['host_env'].update(sha256=hashlib.sha256(hook.read_bytes()).hexdigest(),size=hook.stat().st_size)
        req['initializer_commitment_sha256']=hashlib.sha256(m.canonical(c)).hexdigest()
        # Real production ACL predicate is still invoked; injected metadata
        # must refuse before a single hook marker is written.
        fault_acl=True
        with pytest.raises(m.InitializerCommitmentRefused):m.run_bootstrap(req,qualifier.m._REMOTE_PROBE)
        assert not marker.exists()
        fault_acl=False
        # Forbidden loader environment is not silently cleaned by production.
        monkeypatch.setenv('LD_LIBRARY_PATH','/inert-not-a-library-path')
        with pytest.raises(m.InitializerCommitmentRefused):m.run_bootstrap(req,qualifier.m._REMOTE_PROBE)
        assert not marker.exists()
        monkeypatch.delenv('LD_LIBRARY_PATH')
        c['startup']['prefix']='/not-the-observed-prefix'
        req['initializer_commitment_sha256']=hashlib.sha256(m.canonical(c)).hexdigest()
        with pytest.raises(m.InitializerCommitmentRefused):m.run_bootstrap(req,qualifier.m._REMOTE_PROBE)
        assert not marker.exists()
    _linux_completion(request,'system-root-launch' if system_launch else 'finite-metadata-simulation')


@pytest.mark.parametrize('raw',[b'HOME=x',b'HOME=x\0HOME=y\0',b'BASH_FUNC_exec%%=x\0',
    b'LD_PRELOAD=x\0',b'PYTHONHOME=x\0',b'ENV=x\0',b'HOME=x\0',b'x'*65537])
def test_untrusted_initializer_environment_refuses(raw):
    with pytest.raises(m.InitializerCommitmentRefused):m._initialized_environment(raw,commitment())


def test_shell_stdout_cannot_be_a_probe_witness():
    # The old shell could return forged JSON. The new boundary accepts only
    # a closed/bounded environment DATA transfer, not observer JSON.
    raw=b'{"pre_execution":{"snapshot_sealed":true}}\n'
    with pytest.raises(m.InitializerCommitmentRefused):m._initialized_environment(raw,commitment())


def test_child_output_is_bounded_before_materialization():
    with pytest.raises(m.InitializerCommitmentRefused):
        m._bounded_child([sys.executable,'-I','-S','-c','import sys;sys.stdout.write("x"*65537)'],timeout=5)


def test_native_initializer_extends_only_exact_preimage_members():
    """Changing current pins cannot replace unrelated/historical native bytes."""
    import base64
    root=Path(__file__).resolve().parents[1]
    retained=json.loads((root/'tests/fixtures/paid-host-preinitializer-f608.json').read_bytes())
    assert retained['source']=='f608f52f35384dcfa8e4305dc594f1fbe823d5ec'
    raw=base64.b64decode(retained['native_manifest']['base64'],validate=True)
    assert hashlib.sha256(raw).hexdigest()==retained['native_manifest']['sha256']=='74c5bd3e38e54430c45cc8ccb8d109a3b50fe0abba171ba572cc7be9d35a6270'
    before=json.loads(raw)
    native=root/'ops/native_fabric/quota_continuity'
    current=json.loads((native/'rollout/native-manifest.json').read_bytes())
    assert len(before)==95 and len(current)==98
    assert set(before)<=set(current)
    assert set(current)-set(before)=={'ext/paid_initializer.py','ext/paid_initializer_token_data.py','ext/paid_initializer_nested_data.py'}
    assert {p for p in before if before[p]!=current[p]}=={'ext/host_pull.sh','ext/paid_host_qualification.py'}
    assert sum(before[p]==current[p] for p in before)==93
    for name in ('host_pull.sh','paid_host_qualification.py','paid_initializer.py','paid_initializer_token_data.py','paid_initializer_nested_data.py'):
        assert current['ext/'+name]==hashlib.sha256((native/'candidate'/name).read_bytes()).hexdigest()
    # The paired-upgrade target remains historical; only ordinary generation
    # selection consumes the new complete current closure.
    source=(native/'rollout/native_install.py').read_text()
    assert '6ac208bbd80f706931b11e8147a879f6e3ced6fe704cde7b9f15e1c098e37ee4' in source


def test_completion_notice_has_own_line_with_real_ci_capture(tmp_path):
    program=tmp_path/'test_notice_fixture.py'
    program.write_text('def test_a_before():pass\n'
        'def test_notice_fixture(request):\n'
        ' from tests.test_paid_initializer import _linux_completion\n'
        ' _linux_completion(request)\n')
    env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONDONTWRITEBYTECODE':'1'}
    child=subprocess.run([sys.executable,'-m','pytest','-p','scripts.ci_pytest_timing',
        '-q','-p','no:cacheprovider',str(program)],cwd=Path(__file__).resolve().parents[1],
        env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
    assert child.returncode==0,child.stdout
    notices=[v for v in child.stdout.splitlines() if v.startswith('::notice ')]
    assert len(notices)==1 and 'test_notice_fixture ASSERTIONS_COMPLETED' in notices[0]


@pytest.mark.skipif(sys.platform!='linux' or sys.version_info[:2]!=(3,12),reason='requires actual Linux private package/initializer/FD execution')
def test_actual_nested_initializer_private_package_context_and_wire(tmp_path,monkeypatch,request):
    """Real mechanics/owner validators; trusted platform metadata is simulated.

    Uses only an exclusively created credentialless HOME/lanes fixture. Existing
    HOME/lanes is never read/adopted. No actual config/token/provider is read.
    """
    import pwd
    import shutil
    from tests import test_paid_host_qualification as qualifier
    account=pwd.getpwuid(os.getuid())
    if os.getuid()==0:pytest.skip('requires a non-Root fixture account')
    lane=Path(account.pw_dir)/'lanes'
    try:lane.mkdir(mode=0o700)
    except FileExistsError:pytest.skip('requires an unused credentialless HOME/lanes fixture namespace')
    owned=lane.stat()
    try:
        (lane/'ext/lanes').mkdir(parents=True,mode=0o700)
        (lane/'venv/bin').mkdir(parents=True,mode=0o700)
        bootstrap=Path(sys.executable).with_name('python3')
        system_launch=_system_fixture_launch();real=(system_launch or bootstrap).resolve()
        monkeypatch.setenv('PATH','/usr/bin:/bin')
        logical=lane/'venv/bin/python3';logical.symlink_to(real)
        for key in tuple(os.environ):
            if key.startswith(('LD_','BASH_FUNC_')) or key in ('BASH_ENV','ENV','PYTHONHOME','PYTHONEXECUTABLE','__PYVENV_LAUNCHER__','GLM_CONFIG','GLM_SHIM_TOKEN'):
                monkeypatch.delenv(key)
        monkeypatch.setenv('HOME',account.pw_dir)
        observed=json.loads(subprocess.check_output([str(logical),'-I','-S','-B','-c',
            'import json,sys;print(json.dumps({k:getattr(sys,k) for k in ("prefix","exec_prefix","base_prefix","base_exec_prefix")}))']))
        native=Path(m.__file__).parent
        sources={name:(native/name).read_bytes() for name in ('paid_initializer.py','paid_initializer_token_data.py','paid_initializer_nested_data.py')}
        hashes={name:hashlib.sha256(raw).hexdigest() for name,raw in sources.items()}
        namespace={};exec(qualifier.m._PACKAGE_LOADER,namespace)
        owner=namespace['_load_qualified_package'](sources,hashes)
        assert owner._NESTED_DATA.sealed_snapshot is owner.sealed_snapshot
        assert owner._NESTED_DATA.FrozenHelper is owner._TOKEN_DATA.FrozenHelper
        hook=lane/'ext/HOST_ENV.sh';hook.write_bytes(owner._NESTED_DATA._ORIGINAL);hook.chmod(0o600)
        helper=lane/'ext/.host_glm_token.sh'
        private_token='0123456789abcdef0123456789abcdef'
        helper.write_text('export GLM_SHIM_TOKEN="'+private_token+'"\n');helper.chmod(0o600)
        c=commitment();c.update(initialization_contract=owner.NESTED_CONTRACT,lane_root=str(lane),
            account=dict(uid=os.getuid(),gid=os.getgid(),user=account.pw_name,home=account.pw_dir),
            bootstrap_python=dict(path=str(bootstrap),real_path=str(bootstrap.resolve()),sha256=hashlib.sha256(bootstrap.resolve().read_bytes()).hexdigest()),
            launch_python=dict(path=str(logical),real_path=str(real),sha256=hashlib.sha256(real.read_bytes()).hexdigest()),
            host_env=dict(path=str(hook),sha256=hashlib.sha256(hook.read_bytes()).hexdigest(),size=hook.stat().st_size,uid=os.getuid(),gid=os.getgid(),mode=0o600),
            nested_helper=dict(path=str(helper),sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),size=helper.stat().st_size,uid=os.getuid(),gid=os.getgid(),mode=0o600),
            initialized_context=dict(home=account.pw_dir,glm_config=account.pw_dir+'/.glm/config.json'),
            startup=dict(profile='cpython-3.12-linux-root-prefix.v1',**observed))
        req=qualifier.request();req.update(python_path=str(logical),capture_root=str(lane/'ext/lanes'),initializer_commitment=c,
            initializer_commitment_sha256=hashlib.sha256(m.canonical(c)).hexdigest())
        req['sources_sha256'].update(hashes)
        rawstat=os.stat;rawfstat=os.fstat;rawlstat=os.lstat;rawxattr=os.getxattr
        protected=([str(bootstrap.resolve()),str(bootstrap.parent),str(logical.parent)] if system_launch else [str(real),str(logical.parent),*set(observed.values())])
        ancestry=(bootstrap.resolve(),bootstrap,logical) if system_launch else (real,logical,*map(Path,observed.values()))
        ancestors={str(v) for p in ancestry for v in p.parents}
        private=[];fault_acl=False
        def distribution(name):
            return str(name) in ancestors or any(str(name)==p or str(name).startswith(p+'/') for p in protected)
        def root_view(info):
            fields=list(info);fields[4]=0;fields[0]&=~0o022
            return os.stat_result(fields)
        def owned_fstat(fd):
            info=rawfstat(fd)
            try:name=os.path.realpath('/proc/self/fd/'+str(fd))
            except OSError:return info
            return root_view(info) if distribution(name) else info
        def owned_stat(name,*args,**kwargs):
            info=rawstat(name,*args,**kwargs)
            if kwargs.get('dir_fd') is not None:
                name=os.path.join(os.readlink('/proc/self/fd/'+str(kwargs['dir_fd'])),str(name))
            return root_view(info) if distribution(name) else info
        def owned_lstat(name,*args,**kwargs):
            info=rawlstat(name,*args,**kwargs)
            return root_view(info) if distribution(name) else info
        def modeled_xattr(name,key,*args,**kwargs):
            # Only metadata of the fixed image/startup chain and this disposable
            # private account chain is modeled; no general ACL bypass exists.
            actual=os.path.realpath('/proc/self/fd/'+str(name)) if isinstance(name,int) else str(name)
            modeled=distribution(actual) or actual in private or any(actual.startswith(p+'/') for p in private[-1:])
            if key in ('system.posix_acl_access','system.posix_acl_default') and modeled:
                if fault_acl and actual==str(helper):return b'inert-extended-acl'
                import errno
                raise OSError(errno.ENODATA,'inert trusted metadata has no ACL')
            return rawxattr(name,key,*args,**kwargs)
        private.extend([str(v) for v in lane.parents]+[str(lane)])
        monkeypatch.setattr(os,'fstat',owned_fstat);monkeypatch.setattr(os,'stat',owned_stat)
        monkeypatch.setattr(os,'lstat',owned_lstat);monkeypatch.setattr(os,'getxattr',modeled_xattr)
        # Source-custody seam only; pure request, peer loader and observation
        # validators are the genuine existing owner, not stubbed success DTOs.
        monkeypatch.setattr(qualifier.m,'_initializer_module',lambda expected:(owner,sources['paid_initializer.py']) if expected==hashes['paid_initializer.py'] else m.refuse())
        req=qualifier.m._request(req)
        probe=qualifier.m._REMOTE_PROBE if system_launch else _observer_metadata_fixture(qualifier.m._REMOTE_PROBE,exact=ancestors|set(private),prefixes=protected+[str(lane)],root_directories=ancestors,root_files=[real])
        raw=_inert_bootstrap(req,probe,owner=owner,diagnostic_request=request)
        result=qualifier.m._observation(raw,req)
        assert private_token.encode() not in raw
        assert result['binary']['path']==str(logical)!=str(bootstrap)
        assert result['pre_execution']['snapshot_sha256']==owner._NESTED_DATA.TRANSFORMED_SHA256
        assert result['context_identity']['host_env_sha256']==owner.NESTED_OUTER_SHA256
        assert result['pre_execution']['nested_inputs']['helper']['sha256']==c['nested_helper']['sha256']
        # The source witness cannot be relabelled or silently use old semantics.
        wrong=copy.deepcopy(result);wrong['pre_execution']['nested_inputs']['helper']['sha256']='f'*64
        with pytest.raises(qualifier.m.QualificationRefused):qualifier.m._observation(qualifier.m._canonical(wrong),req)
        wrong=copy.deepcopy(result);wrong['pre_execution']['snapshot_sha256']=owner.NESTED_OUTER_SHA256
        with pytest.raises(qualifier.m.QualificationRefused):qualifier.m._observation(qualifier.m._canonical(wrong),req)
        # Private data must not be read at all with mismatched private metadata.
        helper.chmod(0o640);reads=[];read=os.read;pread=os.pread
        def check_read(fd,*args,**kwargs):
            if os.path.realpath('/proc/self/fd/'+str(fd))==str(helper):
                reads.append(fd);raise AssertionError('private bytes read before exact metadata')
        def checked_read(fd,*args,**kwargs):check_read(fd);return read(fd,*args,**kwargs)
        def checked_pread(fd,*args,**kwargs):check_read(fd);return pread(fd,*args,**kwargs)
        with monkeypatch.context() as faults:
            faults.setattr(os,'read',checked_read);faults.setattr(os,'pread',checked_pread)
            with pytest.raises(owner.InitializerCommitmentRefused):owner.run_bootstrap(req,qualifier.m._REMOTE_PROBE)
        assert not reads;helper.chmod(0o600)
        fault_acl=True
        with monkeypatch.context() as faults:
            faults.setattr(os,'read',checked_read);faults.setattr(os,'pread',checked_pread)
            with pytest.raises(owner.InitializerCommitmentRefused):owner.run_bootstrap(req,qualifier.m._REMOTE_PROBE)
        assert not reads;fault_acl=False
        # Lost/changed token capture is a refusal, never a reinjection/repair.
        capture=owner._capture_environment;bounded=owner._bounded_child;starts=[]
        def changed_capture(*args,**kwargs):
            return capture(*args,**kwargs).replace(private_token.encode(),b'fedcba9876543210fedcba9876543210')
        def counted_child(argv,**kwargs):
            if argv[0]==str(logical):starts.append(argv[0])
            return bounded(argv,**kwargs)
        with monkeypatch.context() as faults:
            faults.setattr(owner,'_capture_environment',changed_capture);faults.setattr(owner,'_bounded_child',counted_child)
            with pytest.raises(ValueError):owner.run_bootstrap(req,qualifier.m._REMOTE_PROBE)
        assert not starts
        # New profile: the actual compiler/isolated bootstrap/private package,
        # getpath child and final observer, using only the existing system image.
        # Source ownership is a declared fixture; platform metadata here is real.
        import shlex
        with monkeypatch.context() as current:
            current.setattr(os,'stat',rawstat);current.setattr(os,'fstat',rawfstat)
            current.setattr(os,'lstat',rawlstat);current.setattr(os,'getxattr',rawxattr)
            system=_system_fixture_launch(no_site=True)
            assert system is not None,'required Root system fixture cannot establish native no-site custody'
            image=system.resolve();logical.unlink();logical.symlink_to(image)
            c['startup'].update(profile=owner.NO_SITE_PROFILE,prefix='/usr',exec_prefix='/usr',base_prefix='/usr',base_exec_prefix='/usr')
            c['bootstrap_python']=dict(path=str(system),real_path=str(image),sha256=hashlib.sha256(image.read_bytes()).hexdigest())
            c['launch_python']=dict(path=str(logical),real_path=str(image),sha256=c['bootstrap_python']['sha256'])
            req['initializer_commitment_sha256']=hashlib.sha256(owner.canonical(c)).hexdigest()
            current.setattr(qualifier.m,'_initializer_bundle',lambda expected:(owner,sources) if all(expected[name]==hashes[name] for name in sources) else owner.refuse())
            alias,command=qualifier.m.build_paid_probe(req);argv=shlex.split(command)
            assert alias==req['transport_alias'] and argv[5].startswith(owner.NO_SITE_PREAMBLE)
            assert len(command.encode('utf-8'))+1<=qualifier.m.MAX_REMOTE_COMMAND_BYTES
            execution=subprocess.run(argv,env=dict(HOME=account.pw_dir,PATH='/usr/bin:/bin'),stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30)
            assert execution.returncode==0,'compiled no-site journey refused'
            assert private_token.encode() not in execution.stdout
            actual=qualifier.m._observation(execution.stdout,req)
            assert actual['binary']['real_path']==str(image)
            assert actual['pre_execution']['snapshot_sha256']==owner._NESTED_DATA.TRANSFORMED_SHA256
    finally:
        current=lane.lstat()
        assert (current.st_dev,current.st_ino)==(owned.st_dev,owned.st_ino)
        shutil.rmtree(lane)
    _linux_completion(request,'old-profile-finite-premise+real-system-nosite')


def test_observer_metadata_fixture_is_finite_and_does_not_hide_other_errors():
    # This is a test-fixture discriminator, not a Linux/ACL/platform receipt.
    source="import os\ndef denied(*args,**kwargs):raise PermissionError('inert underlying refusal')\nos.getxattr=denied\n"
    body="""
for name in ('/modeled/fixed','/modeled/private/child'):
    try:os.getxattr(name,'system.posix_acl_access')
    except OSError as error:assert error.errno==errno.ENODATA
    else:raise AssertionError('modeled metadata did not execute')
for name,key in (('/outside','system.posix_acl_access'),('/modeled/fixed','user.unmodeled')):
    try:os.getxattr(name,key)
    except PermissionError:pass
    else:raise AssertionError('unmodeled refusal was hidden')
"""
    child=subprocess.run([sys.executable,'-I','-S','-B','-c',source+_observer_metadata_fixture(body,exact=['/modeled/fixed'],prefixes=['/modeled/private'])],capture_output=True,timeout=5)
    assert child.returncode==0 and not child.stdout and not child.stderr


@pytest.mark.parametrize('unhandled',[False,True])
def test_child_diagnostic_is_allowlisted_and_preserves_nonzero(unhandled):
    private='DO_NOT_EMIT_TOKEN_OR_PRIVATE_PATH'
    if unhandled:body='raise AssertionError('+repr(private)+')\n'
    else:
        body=('import types\ndef fail():raise ValueError('+repr(private)+')\n'
              'def walk():\n s=types.SimpleNamespace(st_uid=os.getuid()+100000,st_mode=0o100777)\n fail()\n'
              'def observe(p):walk()\n'
              'try:observe({})\nexcept Exception as error:\n _inert_guard_diagnostic(error)\n sys.exit(78)\n')
    source='import os,sys\n'+_OBSERVER_DIAGNOSTIC_PREFIX+body
    child=subprocess.run([sys.executable,'-I','-S','-B','-c',source],capture_output=True,timeout=5)
    assert child.returncode==(1 if unhandled else 78) and not child.stderr
    assert private.encode() not in child.stdout
    value=_decode_observer_diagnostic(child.stdout)
    assert value is not None and value['kind']==('AssertionError' if unhandled else 'ValueError')
    if not unhandled:assert any(site['fields']==['uid','write_mode'] for site in value['sites'])


@pytest.mark.parametrize('change',[
    lambda v:v.update(environment={'GLM_SHIM_TOKEN':'must-not-emit'}),
    lambda v:v.update(kind='/private/never-render'),lambda v:v.update(errno=True),
    lambda v:v['sites'][0].update(function='/private/path'),
    lambda v:v['sites'][0].update(line=True),lambda v:v['sites'][0].update(fields=['secret-value']),
])
def test_child_diagnostic_decoder_rejects_unbounded_or_private_fields(change):
    value=dict(schema=_DIAGNOSTIC_SCHEMA,kind='ValueError',sites=[dict(function='walk',line=10,fields=['write_mode'])],errno=None)
    change(value)
    assert _decode_observer_diagnostic(json.dumps(value).encode()) is None


def test_guard_failure_annotation_has_own_line_with_actual_ci_capture(tmp_path):
    program=tmp_path/'test_guard_annotation_fixture.py'
    program.write_text('def test_a_before():pass\n'
        'def test_guard_fixture(request):\n'
        ' from tests.test_paid_initializer import _guard_notice,_DIAGNOSTIC_SCHEMA\n'
        ' _guard_notice(request,dict(schema=_DIAGNOSTIC_SCHEMA,kind="ValueError",sites=[],errno=None))\n'
        ' raise AssertionError("controlled expected test failure")\n')
    child=subprocess.run([sys.executable,'-m','pytest','-p','scripts.ci_pytest_timing','-q','--tb=short','-p','no:cacheprovider',str(program)],cwd=Path(__file__).resolve().parents[1],env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONDONTWRITEBYTECODE':'1'},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
    assert child.returncode==1
    notices=[v for v in child.stdout.splitlines() if v.startswith('::error ')]
    assert len(notices)==1 and 'H1 Linux guard diagnostic' in notices[0]
    assert 'test_guard_fixture' in notices[0] and '/private/' not in notices[0]


def test_fast_preflight_is_supplementary_and_full_ci_fanin_unchanged():
    from scripts import ci_parallel_shard as fan
    from scripts import ci_pytest as policy
    import shlex,yaml
    text=(Path(__file__).resolve().parents[1]/'.github/workflows/ci.yml').read_text()
    fan.validate_parallel_workflow(text)
    value=yaml.load(text,Loader=policy._WorkflowYAMLLoader)
    assert set(value['jobs'])=={'pytest_shards','test'}
    steps=value['jobs']['pytest_shards']['steps']
    preflight=[(i,x) for i,x in enumerate(steps) if x.get('name')=='H1 initializer Linux fast preflight']
    full=[(i,x) for i,x in enumerate(steps) if x.get('name')=='Run repository test shard']
    assert len(preflight)==len(full)==1 and preflight[0][0]<full[0][0]
    pre=preflight[0][1];assert pre['if']=='matrix.index == 2' and not pre.get('continue-on-error',False)
    assert shlex.split(pre['run'])==['python','-m','pytest','-q','--tb=short','-p','scripts.ci_pytest_timing',
        'tests/test_paid_initializer_token_data.py::TestLinuxFrozenData::test_real_seals_custody_private_env_and_cleanup',
        'tests/test_paid_initializer.py::test_actual_linux_initializer_exec_and_selector_drift_before_hook',
        'tests/test_paid_initializer.py::test_actual_nested_initializer_private_package_context_and_wire',
        'tests/test_paid_initializer_nosite.py']
    assert full[0][1]['run']=='python -m scripts.ci_parallel_shard --jobs 3 --index ${{ matrix.index }}'
    assert full[0][1].get('if') is None


def test_annotation_boundary_itself_never_renders_unapproved_fields():
    from types import SimpleNamespace
    from contextlib import nullcontext
    lines=[]
    reporter=SimpleNamespace(write_line=lines.append)
    fixture=SimpleNamespace(config=SimpleNamespace(pluginmanager=SimpleNamespace(getplugin=lambda _:reporter)),getfixturevalue=lambda _:SimpleNamespace(disabled=nullcontext),node=SimpleNamespace(name='synthetic-case'))
    secret='DO_NOT_EMIT_PRIVATE_DATA'
    _guard_notice(fixture,dict(environment={'GLM_SHIM_TOKEN':secret},path='/private/'+secret))
    assert len(lines)==1 and secret not in lines[0] and '/private/' not in lines[0]
    assert '"kind":"REFUSAL"' in lines[0] and '"sites":[]' in lines[0]


def test_unexpected_pipeline_exception_keeps_private_repr_out_of_diagnostics(monkeypatch):
    secret='NOT_REAL_SECRET_MUST_NOT_BE_RENDERED'
    def fail(*args):raise OSError(secret)
    monkeypatch.setattr(m,'run_bootstrap',fail)
    with pytest.raises(AssertionError) as caught:_inert_bootstrap({},'')
    assert secret not in str(caught.value) and 'diagnostic=' in str(caught.value)
    assert caught.value.__suppress_context__ is True


@pytest.mark.parametrize('cleanup',[False,True])
def test_final_observer_primary_and_cleanup_refusals_stay_distinct(monkeypatch,cleanup):
    from types import SimpleNamespace
    private='PRIVATE_CLEANUP_TEXT_MUST_NOT_ESCAPE'
    public=dict(schema=_DIAGNOSTIC_SCHEMA,kind='ValueError',sites=[dict(function='walk',line=17,fields=['kind'])],errno=None)
    def bounded(argv,**kwargs):
        raw=bytearray(json.dumps(public).encode())
        raise m.InitializerCommitmentRefused()
    owner=SimpleNamespace(_bounded_child=bounded,InitializerCommitmentRefused=m.InitializerCommitmentRefused,__file__=__file__)
    def run(request,probe):
        try:return owner._bounded_child(['python','-I','-S','-B','-c','def observe(p):pass\n    except Exception:\n        sys.exit(78)','{}'])
        finally:
            if cleanup:raise ValueError(private)
    owner.run_bootstrap=run
    notices=[]
    monkeypatch.setattr(sys.modules[__name__],'_guard_notice',lambda fixture,value,**kw:notices.append((value,kw['phase'])))
    expected='CLEANUP_AFTER_OBSERVER_REFUSAL' if cleanup else 'FINAL_OBSERVER_REFUSAL'
    with pytest.raises(AssertionError) as caught:_inert_bootstrap({},'',owner=owner)
    assert notices==[(public,expected)]
    assert 'phase='+expected in str(caught.value) and private not in str(caught.value)
    assert caught.value.__suppress_context__ is True


@pytest.mark.skipif(sys.platform!='linux',reason='requires actual Linux proc FD names')
def test_observer_directory_premise_is_exact_and_preserves_unmodeled_writes(tmp_path):
    modeled=tmp_path/'modeled';private=tmp_path/'private';unmodeled=tmp_path/'unmodeled'
    for path in (modeled,private,unmodeled):path.mkdir(mode=0o777);path.chmod(0o777)
    child_probe="""
import json
p=json.loads(sys.argv[1])
for key in ('modeled','private','unmodeled'):
    name=p[key];fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY)
    try:
        actual=_fixture_raw_fstat(fd);view=os.fstat(fd)
        assert view.st_ino==actual.st_ino and view.st_mtime_ns==actual.st_mtime_ns and view.st_ctime_ns==actual.st_ctime_ns
        assert bool(view.st_mode&0o022)==(key!='modeled')
        assert bool(os.stat(name).st_mode&0o022)==(key!='modeled')
        assert bool(os.stat('.',dir_fd=fd).st_mode&0o022)==(key!='modeled')
    finally:os.close(fd)
# A regular file at an enumerated pathname must never get directory semantics.
fd=os.open(p['file'],os.O_RDONLY)
try:assert os.fstat(fd).st_mode==_fixture_raw_fstat(fd).st_mode
finally:os.close(fd)
"""
    # Reuse the actual observer guard; only the explicit directory premise is
    # simulated. Siblings/private leaves remain genuinely writable and refuse.
    from ops.native_fabric.quota_continuity.candidate.paid_host_qualification import _REMOTE_PROBE
    definitions,separator,_=_REMOTE_PROBE.partition("\nif __name__=='__main__':")
    assert separator
    child_probe+='''
for key in ('modeled','private','unmodeled'):
    try:fd=walk(p[key],os.getuid())
    except ValueError:
        assert key!='modeled'
    else:
        os.close(fd);assert key=='modeled'
'''
    child_probe+='''
raw,info=read_file(p['image'],os.getuid(),4096)
assert raw==b'inert-image' and info.st_uid==0 and not info.st_mode&0o022
try:read_file(p['file'],os.getuid(),4096)
except ValueError:pass
else:raise AssertionError('unmodeled writable file admitted')
'''
    regular=tmp_path/'regular';regular.write_bytes(b'inert');regular.chmod(0o666)
    image=tmp_path/'image';image.write_bytes(b'inert-image');image.chmod(0o666)
    data=dict(modeled=str(modeled),private=str(private),unmodeled=str(unmodeled),file=str(regular),image=str(image))
    source='import sys\n'+_observer_metadata_fixture(definitions+'\n'+child_probe,exact=[*modeled.parents,modeled],prefixes=[],root_directories=[*modeled.parents,modeled,regular],root_files=[image])
    child=subprocess.run([sys.executable,'-I','-S','-B','-c',source,json.dumps(data)],capture_output=True,timeout=5)
    assert child.returncode==0 and not child.stdout and not child.stderr
