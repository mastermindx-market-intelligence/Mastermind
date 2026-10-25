"""Inert original-run read qualification; no transport, process or lease effects."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
import pytest

HERE=Path(__file__).resolve().parent
EXT=Path('/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext')
sys.path.insert(0,str(EXT))
RUN='mm-os-incident-issuer-custody-preflight-20261013-01a104e6'
ROOT='01a104e6-58f8-76d3-8d99-1302a1cca072'
BASE=os.environ.get('OBSERVATION_BASELINE')=='1'
def load(name):
    from importlib.machinery import SourceFileLoader
    source=Path(os.environ.get('OBSERVATION_SOURCE_DIR', str(HERE)))
    path=source/(name+('.py.base' if BASE else '.py'))
    spec=importlib.util.spec_from_loader('test_'+name,SourceFileLoader('test_'+name,str(path)))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
D=load('run_observation_delivery');R=load('run_observation')
sha=lambda b:hashlib.sha256(b).hexdigest()

def test_exact_run_is_supported():
    req=D.request_for(RUN,ROOT)
    assert req['parent']==ROOT and req['observe_pid'] is False
    assert req['support_digest']=='4014714eb8865585f11b2a0120975479c10f0567cad968c5a57e5101f8c8f114'

def packet(scope):
    body=b'inert bounded task\n'
    h=dict(root=ROOT,parent=ROOT,run_id=RUN,support_digest=scope['support_digest'],body_sha256=sha(body))
    return b'FABRIC_ARTIFACT_REQUEST_V1 '+json.dumps(h).encode()+b'\n'+body

@pytest.fixture
def f(monkeypatch):
    scope=dict(D.SCOPES[RUN]);p=packet(scope);scope['packet_sha256']=sha(p)
    monkeypatch.setitem(D.SCOPES,RUN,scope)
    raw=dict(log=(HERE/'launch-prefix.log').read_bytes(),packet=p,registry=b'{"ubuntu2":{"ssh_alias":"ubuntu2"}}',observer=b'inert observer')
    return D.request_for(RUN,ROOT),scope,raw

def event(text,host='ubuntu2'):
    return f'2026-10-13T21:30Z [remote_sub id={RUN} host={host}] {text}\n'.encode()

def test_append_is_stable(f):
    req,s,raw=f;a=D.qualify_bytes(req,s,raw)
    raw['log']+=event('POLL 60/7200 elapsed=1800')+event('POLL_PENDING poll=60')
    assert D.qualify_bytes(req,s,raw)==a

@pytest.mark.parametrize('suffix',[b'',event('LAUNCH_ATTEMPT attempt=1'),event('LAUNCH_ATTEMPT attempt=2'),event('LAUNCH stdout=wrong'),event('SUPPORT_VERSION_READY digest=wrong policy=wrong'),event('POLL_PENDING poll=60','ubuntu1'),event('RUN_RESERVED explicit=1')])
def test_changed_launch_or_identity_refused(f,suffix):
    req,s,raw=f
    if suffix:raw['log']+=suffix
    else:raw['log']=raw['log'][:-1]
    with pytest.raises(ValueError):D.qualify_bytes(req,s,raw)

@pytest.mark.parametrize('field',['root','parent','run_id','support_digest','body_sha256'])
def test_header_binding_refused(f,field):
    req,s,raw=f;head,body=raw['packet'].split(b'\n',1);h=json.loads(head.split(b' ',1)[1]);h[field]='wrong'
    raw['packet']=b'FABRIC_ARTIFACT_REQUEST_V1 '+json.dumps(h).encode()+b'\n'+body
    # Even under a fixture's newly pinned envelope, inconsistent header/body refuses.
    s['packet_sha256']=sha(raw['packet'])
    with pytest.raises(ValueError):D.qualify_bytes(req,s,raw)

def test_changed_packet_refused(f):
    req,s,raw=f;raw['packet']+=b'changed'
    with pytest.raises(ValueError):D.qualify_bytes(req,s,raw)

def test_live_log_append_and_rewrite_between_reads(f,monkeypatch):
    req,s,raw=f;state=[raw['log']];observed=[]
    paths={str(D.delivery.HERE/'state/remote_sub'/(RUN+'.log')):'log',s['packet_path']:'packet',str(D.delivery.HERE/'hosts.json'):'registry',str(D.delivery.HERE/'run_observation.py'):'observer'}
    def read(path,limit=1048576):
        k=paths[str(path)]
        if k=='log':
            value=state[0];state[0]+=event('POLL_PENDING poll=60');return value
        return raw[k]
    monkeypatch.setattr(D.delivery,'local_file',read)
    a=D.qualify(req,observed_log=observed)
    assert D.qualify(req,observed_log=observed)==a
    state[0]=raw['log']+event('POLL_PENDING poll=61')
    with pytest.raises(ValueError,match='rewritten'):D.qualify(req,observed_log=observed)

def manifest_reader(names):
    contents={n:('inert '+n).encode() for n in names};files={n:sha(b) for n,b in contents.items()}
    digest=sha(json.dumps({'schema':R.RELEASE_SCHEMA,'files':files},sort_keys=True,separators=(',',':')).encode())
    manifest=json.dumps(dict(schema=R.RELEASE_SCHEMA,files=files,digest=digest)).encode()
    class Reader:
        def read(self,parts,limit,mode=None):
            b=manifest if parts[-1]=='RELEASE.json' else contents[parts[-1]]
            assert len(b)<=limit
            assert mode==(0o444 if parts[-1]=='RELEASE.json' else 0o555)
            return b,None
    return Reader(),digest,contents

def test_exact_30_name_generation(monkeypatch):
    names=R.SOURCE_FILES|{'fabric_operator_client.py','fabric_operator_stop.py','fabric_policy_snapshot.py','pools.yaml','fabric_operator_diagnostics.py','yes'}
    reader,digest,_=manifest_reader(names);monkeypatch.setattr(R,'ACTIVE_SUPPORT_DIGEST',digest,raising=False)
    assert R.support(reader,digest)['verified_code_files']==30

@pytest.mark.parametrize('mutation',['missing','extra','bad_hash','historical'])
def test_support_closure_negative(monkeypatch,mutation):
    names=R.ACTIVE_SUPPORT_FILES
    if mutation=='missing':names=names-{'yes'}
    if mutation=='extra':names=names|{'unapproved.py'}
    reader,digest,contents=manifest_reader(names)
    if mutation!='historical':monkeypatch.setattr(R,'ACTIVE_SUPPORT_DIGEST',digest)
    if mutation=='bad_hash':contents['yes']=b'changed'
    with pytest.raises(R.Invalid):R.support(reader,digest)

def test_legacy_generation_unchanged():
    reader,digest,_=manifest_reader(R.SOURCE_FILES)
    assert R.support(reader,digest)['verified_code_files']==24

def test_remote_permission_stops_without_fallback(monkeypatch):
    calls=[]
    class Refused:
        def __init__(self,*a,**kw):raise PermissionError(13,'denied')
    monkeypatch.setattr(R,'Reader',Refused)
    monkeypatch.setattr(R,'marker',lambda *a:calls.append('marker'))
    out=R.observe(RUN,R.ACTIVE_SUPPORT_DIGEST,observe_pid=False)
    assert out['status']=='unavailable' and not calls

def test_no_request_expansion():
    req=D.request_for(RUN,ROOT)
    for key,value in [('parent','foreign'),('root','foreign'),('host','ubuntu1'),('observe_pid',True),('stdout_content',True)]:
        bad=dict(req);bad[key]=value
        with pytest.raises(ValueError):D.validate_request(bad)
    with pytest.raises(ValueError):D.request_for(RUN+'-replacement',ROOT)

def test_strict_directory_guard_preserved(tmp_path):
    p=tmp_path/'shared';p.mkdir(mode=0o775);p.chmod(0o775)
    # Test the actual custody predicate without relying on temp-root permissions.
    reader=object.__new__(R.Reader);reader.uid=os.getuid()
    with pytest.raises(R.Invalid):reader._directory(p.stat())

def response(req,count=30):
    support=dict(status='observed',digest=req['support_digest'],verified_code_files=count,verification='manifest_and_fixed_code_hashes',running_process_source_identity_proven=False,release_links_verified=False)
    obs={k:dict(status='absent',reason='missing_at_observation') for k in ('marker','returncode','stdout','process_receipt')};obs['support']=support
    report=dict(schema='mastermind.run_observation.v1',run_id=req['run_id'],expected_support_digest=req['support_digest'],status='observed',observations=obs,limits=D.LIMITS)
    return dict(schema=D.SCHEMA,request_sha256=sha(D.reader.canonical(req)),report=report)

def test_response_scope_and_legacy_30_refusal():
    req=D.request_for(RUN,ROOT);value=response(req)
    assert D.validate_response(json.dumps(value).encode(),req)['status']=='observed'
    old='native-host-review-22f77378-01a0e0c7';req=D.request_for(old,D.SCOPES[old]['root'])
    with pytest.raises(ValueError,match='support_shape'):D.validate_response(json.dumps(response(req)).encode(),req)

@pytest.mark.parametrize('change',['digest','support','proc','stdout_content','count'])
def test_response_rejects_expansion(change):
    req=D.request_for(RUN,ROOT);value=response(req);obs=value['report']['observations']
    if change=='digest':value['request_sha256']='0'*64
    if change=='support':obs['support']['digest']='0'*64
    if change=='proc':obs['proc']={'status':'observed'}
    if change=='stdout_content':obs['stdout']={'status':'observed','content_read':True,'text':'forbidden'}
    if change=='count':obs['support']['verified_code_files']=24
    with pytest.raises(ValueError):D.validate_response(json.dumps(value).encode(),req)
