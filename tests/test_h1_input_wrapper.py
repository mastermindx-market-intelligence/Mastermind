"""Only inert local fixtures. No SSH/process/hook/provider/config invocation."""
import base64
from contextlib import ExitStack
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys

import pytest

PATH=Path(__file__).resolve().parents[1]/'tools/admin_inputs/h1_input_wrapper.py'
spec=importlib.util.spec_from_file_location('h1_wrapper',PATH)
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
CANARY=b'0123456789abcdef0123456789abcdef'
RAW=b'export GLM_SHIM_TOKEN="'+CANARY+b'"\n'


def data():
    return {'schema_version':w.SCHEMA,'host_ref':'ubuntu0','transport_alias':'mmx-ubuntu0',
       'account':dict(uid=1000,gid=1000,user='ubuntu0',home=w.HOME),
       'helper':{'path':w.HELPER,'fingerprint':{'schema_version':'mastermind.paid_helper_private_data/v1','sha256':hashlib.sha256(RAW).hexdigest(),'size':len(RAW),'uid':1000,'gid':1000,'mode':0o600},'origin_identity':[1,2,stat.S_IFREG|0o600,1000,1000,1,len(RAW),3,4]},
       'selectors':{'home':w.HOME,'glm_config':w.HOME+'/.glm/config.json','launch_python':{'path':'/usr/bin/python3','real_path':w.BOOT,'sha256':w.IMAGE_SHA},'startup_basis':'RETAINED_EXPECTATION_NOT_GETPATH_PROOF'},
       'custody':'HELD_NAMED_FULL9_ACL_CHECKED_NOT_APPROVAL'}


def test_assemble_real_reviewed_codec_no_secret():
    result=w.assemble(data());raw=w.canonical(result)
    assert CANARY not in raw and RAW not in raw
    assert result['status']=='DATA_CANDIDATE_NOT_APPROVAL_NOT_QUALIFICATION'
    assert len(result['commitment'])==13
    assert hashlib.sha256(result['canonical_utf8'].encode()).hexdigest()==result['commitment_sha256']
    assert result['commitment']['host_env']['sha256']==w.OUTER_SHA
    assert result['commitment']['nested_helper']['sha256']==hashlib.sha256(RAW).hexdigest()
    parent=w.package()['paid_initializer.py']
    assert parent.decode_commitment(result['canonical_utf8'].encode(),result['commitment_sha256'],host_ref='ubuntu0',transport_alias='mmx-ubuntu0',python_path='/usr/bin/python3',capture_root=w.LANE+'/ext/lanes')==result['commitment']


@pytest.mark.parametrize('mutate',[
 lambda d:d.update(extra='x'),lambda d:d.update(host_ref='ubuntu1'),lambda d:d.update(transport_alias='foreign'),
 lambda d:d['account'].update(uid=1001),lambda d:d['helper'].update(path='/tmp/other'),
 lambda d:d['helper']['fingerprint'].update(mode=0o644),lambda d:d['helper']['fingerprint'].update(size=1),
 lambda d:d['helper']['origin_identity'].__setitem__(5,2),lambda d:d['helper']['origin_identity'].__setitem__(2,stat.S_IFLNK|0o600),
 lambda d:d['selectors'].update(startup_basis=True),lambda d:d['selectors'].update(home='/home/other'),
 lambda d:d['selectors']['launch_python'].update(real_path='/tmp/python3'),lambda d:d['selectors']['launch_python'].update(sha256='0'*64),
 lambda d:d['selectors'].update(glm_config='relative')])
def test_assembly_refuses_closed_shape_and_custody(mutate):
    value=data();mutate(value)
    with pytest.raises(Exception):w.assemble(value)


@pytest.mark.parametrize('raw',[b'{"x":1,"x":2}',b'{"x":NaN}',b'{',b'',b'x'*16385])
def test_strict_input_codec(raw):
    with pytest.raises(Exception):w.decode(raw)


def test_private_package_pins_and_empty_search_path(monkeypatch):
    before=set(sys.modules);modules=w.package()
    assert set(sys.modules)==before
    assert set(modules)==set(w.PINS)
    for name,raw in w.SOURCES.items():assert hashlib.sha256(base64.b64decode(raw)).hexdigest()==w.PINS[name]
    bad=dict(w.PINS);bad['paid_initializer.py']='0'*64;monkeypatch.setattr(w,'PINS',bad)
    with pytest.raises(Exception):w.package()
    assert set(sys.modules)==before


def test_first_selector_exact_owner_order_no_skip(monkeypatch):
    seen=[];first=w.LANE+'/venv/bin/python3'
    monkeypatch.setattr(w.os.path,'isfile',lambda p:seen.append(p) is None and p==first)
    monkeypatch.setattr(w.os,'access',lambda *_:True)
    selected,path=w.first_python({'HOME':w.HOME,'PATH':'/usr/bin:/bin'})
    assert selected==first and seen==[first]
    assert path.startswith(w.LANE+'/venv/bin:'+w.HOME+'/.npm-global/bin:')
    class NeverOpen:
        def open(self,*a,**k):raise AssertionError('should refuse earlier account selector before image open')
    monkeypatch.setattr(w.os,'lstat',lambda _:type('S',(),{'st_mode':stat.S_IFREG|0o755})())
    with pytest.raises(w.Refused):w.image(NeverOpen(),selected)


@pytest.mark.parametrize('env',[{'HOME':'/home/other','PATH':'/usr/bin'}, {'HOME':w.HOME,'BASH_ENV':'secret'}, {'HOME':w.HOME,'LD_PRELOAD':'secret'}, {'HOME':w.HOME,'PATH':'x'*16385}])
def test_environment_refuses_before_filesystem(monkeypatch,env):
    monkeypatch.setattr(w.os.path,'isfile',lambda _:pytest.fail('filesystem selector consulted'))
    with pytest.raises(w.Refused):w.first_python(env)


@pytest.fixture
def local(monkeypatch,tmp_path):
    # Test-only physical namespace/model, no production bypass parameter.
    p=tmp_path/'private-helper';p.write_bytes(RAW);p.chmod(0o600)
    monkeypatch.setattr(w,'HELPER',str(p));monkeypatch.setattr(w,'UID',os.getuid());monkeypatch.setattr(w,'GID',os.getgid())
    # /private/tmp is shared; this test checks actual final fixture objects and
    # held edges while allowing those known test-only directory modes.
    original=w.Custody.open
    def fixture_open(self,path,*,owners,directory=False):
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
        self.held.append((fd,None,None,w.identity(os.fstat(fd))))
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1: w.refuse()
        return fd
    monkeypatch.setattr(w.Custody,'open',fixture_open)
    monkeypatch.setattr(w.Custody,'check',lambda self:None)
    return p


@pytest.mark.parametrize('kind',['mode','hardlink','symlink','grammar','size'])
def test_helper_refuses_without_secret_or_child(monkeypatch,local,kind):
    token=w.package()['paid_initializer_token_data.py']
    if kind=='mode':local.chmod(0o644)
    if kind=='hardlink':os.link(local,str(local)+'.link')
    if kind=='symlink':local.rename(str(local)+'.original');local.symlink_to(str(local)+'.original')
    if kind=='grammar':local.write_bytes(RAW.replace(b'export',b'zzzzzz'))
    if kind=='size':local.write_bytes(RAW+b'echo SECRET')
    monkeypatch.setattr(token,'freeze_helper_data',lambda *a,**k:pytest.fail('bad input reached sealing'))
    with pytest.raises(Exception) as error:
        with w.Custody() as c, ExitStack() as contexts:w.read_helper(c,contexts,token)
    assert CANARY.decode() not in str(error.value)


def test_full9_named_drift_real_custody_check(tmp_path,monkeypatch):
    monkeypatch.setattr(w.Custody,'acl',staticmethod(lambda _:None))  # Linux ACL model only.
    p=tmp_path/'private';p.write_bytes(b'inert');p.chmod(0o600)
    c=w.Custody();fd=os.open(p,os.O_RDONLY);parent=os.open(tmp_path,os.O_RDONLY)
    c.held=[(parent,None,None,w.identity(os.fstat(parent))),(fd,parent,'private',w.identity(os.fstat(fd)))]
    # Root record must refer to real /; keep only actual leaf edge for this test.
    c.held=c.held[1:];p.write_bytes(b'changed')
    try:
        with pytest.raises(w.Refused):c.check()
    finally:c.__exit__(None,None,None);os.close(parent)


def test_closes_every_fd_after_partial_failure(monkeypatch):
    closed=[];c=w.Custody();c.held=[(7,None,None,[]),(8,None,None,[])]
    def close(fd):
        closed.append(fd)
        if fd==8:raise OSError(CANARY.decode())
    monkeypatch.setattr(w.os,'close',close)
    with pytest.raises(w.Refused) as error:c.__exit__(None,None,None)
    assert closed==[8,7] and not c.held and CANARY.decode() not in str(error.value)


class BytesIO:
    def __init__(self,raw=b''):self.buffer=io.BytesIO(raw)


@pytest.mark.parametrize('mode',['--assemble','--acquire','--unknown'])
def test_cli_only_safe_error_canary_never_echoes(monkeypatch,mode):
    out=BytesIO();err=io.StringIO();monkeypatch.setattr(sys,'stdout',out);monkeypatch.setattr(sys,'stderr',err);monkeypatch.setattr(sys,'stdin',BytesIO(RAW))
    monkeypatch.setattr(w,'acquire',lambda:(_ for _ in ()).throw(ValueError(CANARY.decode())))
    assert w.main([mode])==78
    assert out.buffer.getvalue()==b'' and err.getvalue()=='h1_input_acquisition_refused\n'


def test_packet_fixed_route_no_execution():
    result=w.packet(PATH.read_bytes())
    assert result['argv']==['/usr/bin/ssh','-T','-oBatchMode=yes','-oStrictHostKeyChecking=yes','-oUpdateHostKeys=no','-oConnectTimeout=8','mmx-ubuntu0','/usr/bin/python3.12 -I -S -B -']
    assert result['status']=='PROPOSED_NOT_EXECUTED' and CANARY not in w.canonical(result)
    assert hashlib.sha256(result['stdin_utf8'].encode()).hexdigest()==result['stdin_sha256']
    compile(result['stdin_utf8'],'<not-executed-packet>','exec')


def test_public_acquire_platform_refusal_before_any_access(monkeypatch):
    monkeypatch.setattr(sys,'platform','unsupported')
    monkeypatch.setattr(w.os,'open',lambda *a,**k:pytest.fail('filesystem accessed'))
    monkeypatch.setattr(w.os,'pread',lambda *a,**k:pytest.fail('credential read'))
    with pytest.raises(w.Refused):w.acquire()


def test_partial_fstat_failure_still_closes_opened_descriptor(monkeypatch):
    closed=[]
    monkeypatch.setattr(w.os,'open',lambda *a,**k:91)
    monkeypatch.setattr(w.os,'fstat',lambda _:(_ for _ in ()).throw(OSError('inert failure')))
    monkeypatch.setattr(w.os,'close',lambda fd:closed.append(fd))
    with pytest.raises(OSError):
        with w.Custody() as c:c.open('/inert',owners={0})
    assert closed==[91]


def test_native_acl_refusal_is_not_fixture_disabled(monkeypatch):
    monkeypatch.setattr(w.os,'listxattr',lambda _:['system.posix_acl_access'],raising=False)
    with pytest.raises(w.Refused):w.Custody.acl(3)


def test_unsupported_acl_platform_has_no_fallback(monkeypatch):
    monkeypatch.delattr(w.os,'listxattr',raising=False)
    with pytest.raises(AttributeError):w.Custody.acl(3)


@pytest.mark.skipif(sys.platform!='linux',reason='real Linux memfd sealing required; no Darwin substitute')
def test_real_private_helper_snapshot_on_linux(monkeypatch,local):
    token=w.package()['paid_initializer_token_data.py']
    with w.Custody() as c, ExitStack() as contexts:
        helper,info=w.read_helper(c,contexts,token)
        assert helper.fingerprint['sha256']==hashlib.sha256(RAW).hexdigest()
        assert CANARY not in w.canonical(helper.fingerprint)
        local.write_bytes(RAW.replace(b'0',b'1',1))
        with pytest.raises(Exception):helper.check()


def test_packet_body_never_imports_remote_mutable_search_path():
    import ast
    tree=ast.parse(PATH.read_text())
    assert not any(isinstance(n,ast.Import) and any(x.name in ('subprocess','socket') for x in n.names) for n in tree.body)
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('system','popen','execve','spawnv','connect') for n in ast.walk(tree))
    # Embedded reviewed dependencies do contain their legitimate execution
    # owner. The packet only calls acquire, never their run_bootstrap.
    assert 'run_bootstrap(' not in PATH.read_text()


def test_actual_acquisition_codec_private_credential_canary(monkeypatch,local):
    # Explicit platform/account/image/ACL/seal test models. Actual private
    # grammar, file pread, fingerprint, context codec and closed output run.
    from contextlib import contextmanager
    from types import SimpleNamespace
    modules=w.package();token=modules['paid_initializer_token_data.py'];seen=[]
    @contextmanager
    def mechanical_seal(fd,*,expected):
        raw=os.pread(fd,expected['size']+1,0);token.parse_helper_data(raw)
        assert hashlib.sha256(raw).hexdigest()==expected['sha256']
        seen.append(True)
        yield SimpleNamespace(fingerprint={'schema_version':token.SCHEMA,**expected},check=lambda:None)
    monkeypatch.setattr(token,'freeze_helper_data',mechanical_seal)
    monkeypatch.setattr(w,'package',lambda:modules)
    monkeypatch.setattr(sys,'platform','linux')
    monkeypatch.setattr(sys,'flags',SimpleNamespace(isolated=1,no_site=1))
    monkeypatch.setattr(sys,'dont_write_bytecode',True)
    monkeypatch.setattr(w.pwd,'getpwuid',lambda _:SimpleNamespace(pw_name=w.USER,pw_dir=w.HOME))
    monkeypatch.setattr(w.os.path,'realpath',lambda _:w.BOOT)
    monkeypatch.setattr(w,'first_python',lambda _:('/usr/bin/python3','/usr/bin'))
    monkeypatch.setattr(w,'image',lambda c,path:({'path':path,'real_path':w.BOOT,'sha256':w.IMAGE_SHA},[]))
    monkeypatch.setenv('HOME',w.HOME);monkeypatch.delenv('GLM_CONFIG',raising=False)
    monkeypatch.setattr(w.os.path,'isfile',lambda p:p=='/usr/bin/python3')
    monkeypatch.setattr(w.os,'access',lambda *_:True)
    result=w.acquire();encoded=w.canonical(result)
    assert seen==[True] and CANARY not in encoded and RAW not in encoded
    assert result['selectors']['glm_config']==w.HOME+'/.glm/config.json'
    assert result['selectors']['startup_basis']=='RETAINED_EXPECTATION_NOT_GETPATH_PROOF'
    assert set(result)=={'schema_version','host_ref','transport_alias','account','helper','selectors','custody'}


def test_refusal_stream_failure_cannot_format_primary_canary(monkeypatch):
    class Broken:
        def write(self,*_):raise OSError('closed destination')
    monkeypatch.setattr(w,'acquire',lambda:(_ for _ in ()).throw(ValueError(CANARY.decode())))
    monkeypatch.setattr(sys,'stderr',Broken())
    assert w.main(['--acquire'])==78
