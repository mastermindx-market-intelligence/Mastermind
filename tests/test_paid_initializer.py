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


def _linux_completion(request):
    # Structured Actions notice only after the real assertions complete. This
    # gives the retained safe annotation API exact-case evidence; no XML or
    # raw terminal escape rendering is required or claimed.
    reporter=request.config.pluginmanager.getplugin('terminalreporter')
    if reporter is not None:
        with request.getfixturevalue('capsys').disabled():
            reporter.write_line('\n::notice file=tests/test_paid_initializer.py,title=H1 Linux case executed::'
                +request.node.name+' ASSERTIONS_COMPLETED Python '+'.'.join(map(str,sys.version_info[:3])))


def _inert_bootstrap(request,probe,*,owner=m):
    # Public source location only; never emit environment/config/credential
    # values if the deliberately simulated distribution does not qualify.
    try:return owner.run_bootstrap(request,probe)
    except owner.InitializerCommitmentRefused as error:
        frame=error.__traceback__;site=None
        while frame is not None:
            if frame.tb_frame.f_code.co_filename==owner.__file__ and frame.tb_frame.f_code.co_name!='refuse':
                site=frame.tb_lineno
            frame=frame.tb_next
        raise AssertionError('inert initializer source guard refused at paid_initializer.py:'+str(site)) from error


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
    logical=Path(sys.executable).with_name('python3')
    assert logical.exists()
    real=logical.resolve()
    observed=json.loads(subprocess.check_output([str(logical),'-I','-S','-B','-c',
        'import json,sys;print(json.dumps({k:getattr(sys,k) for k in ("prefix","exec_prefix","base_prefix","base_exec_prefix")}))']))
    rawstat=os.stat;rawfstat=os.fstat;rawlstat=os.lstat;rawxattr=os.getxattr
    protected=[str(real),str(logical.parent),*set(observed.values())]
    ancestors={str(v) for p in (real,logical,*map(Path,observed.values())) for v in p.parents}
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
    with tempfile.TemporaryDirectory(prefix='.mmx-inert-init-',dir=account.pw_dir) as scratch:
        private.extend([str(v) for v in Path(scratch).parents]+[scratch])
        lane=Path(scratch)/'lanes';(lane/'ext/lanes').mkdir(parents=True,mode=0o700)
        hook=lane/'ext/HOST_ENV.sh';config=Path(scratch)/'not-read.json'
        hook.write_text('export GLM_CONFIG='+str(config)+'\n');hook.chmod(0o600)
        c=commitment();c.update(lane_root=str(lane),account=dict(uid=os.getuid(),gid=os.getgid(),user=account.pw_name,home=account.pw_dir),
            bootstrap_python=dict(path=str(logical),real_path=str(real),sha256=hashlib.sha256(real.read_bytes()).hexdigest()),
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
        result=json.loads(_inert_bootstrap(req,qualifier.m._REMOTE_PROBE))
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
        actual=json.loads(_inert_bootstrap(req,qualifier.m._REMOTE_PROBE))
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
    _linux_completion(request)


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
        bootstrap=Path(sys.executable).with_name('python3');real=bootstrap.resolve()
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
            bootstrap_python=dict(path=str(bootstrap),real_path=str(real),sha256=hashlib.sha256(real.read_bytes()).hexdigest()),
            launch_python=dict(path=str(logical),real_path=str(real),sha256=hashlib.sha256(real.read_bytes()).hexdigest()),
            host_env=dict(path=str(hook),sha256=hashlib.sha256(hook.read_bytes()).hexdigest(),size=hook.stat().st_size,uid=os.getuid(),gid=os.getgid(),mode=0o600),
            nested_helper=dict(path=str(helper),sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),size=helper.stat().st_size,uid=os.getuid(),gid=os.getgid(),mode=0o600),
            initialized_context=dict(home=account.pw_dir,glm_config=account.pw_dir+'/.glm/config.json'),
            startup=dict(profile='cpython-3.12-linux-root-prefix.v1',**observed))
        req=qualifier.request();req.update(python_path=str(logical),capture_root=str(lane/'ext/lanes'),initializer_commitment=c,
            initializer_commitment_sha256=hashlib.sha256(m.canonical(c)).hexdigest())
        req['sources_sha256'].update(hashes)
        rawstat=os.stat;rawfstat=os.fstat;rawlstat=os.lstat;rawxattr=os.getxattr
        protected=[str(real),str(logical.parent),*set(observed.values())]
        ancestors={str(v) for p in (real,logical,*map(Path,observed.values())) for v in p.parents}
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
        raw=_inert_bootstrap(req,qualifier.m._REMOTE_PROBE,owner=owner)
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
    finally:
        current=lane.lstat()
        assert (current.st_dev,current.st_ino)==(owned.st_dev,owned.st_ino)
        shutil.rmtree(lane)
    _linux_completion(request)
