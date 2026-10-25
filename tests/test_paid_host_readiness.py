"""Inert recurring-readiness contracts; no installed or remote private reads."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'ops/native_fabric/quota_continuity/candidate'


def module():
    path = SOURCE/'paid_host_readiness.py'
    if not path.exists():
        return SimpleNamespace()
    spec = importlib.util.spec_from_file_location('inert_paid_host_readiness', path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def binding():
    return dict(schema_version='mastermind.paid_host_readiness_context/v1',
        host='ubuntu0', transport_alias='mmx-ubuntu0', worker_id='glm-paid-01',
        account='inert-account', model='glm-5.3-flash',
        boot_id='12345678-1234-1234-1234-123456789abc',
        source_config_sha256='a'*64, release_manifest_sha256='b'*64,
        registry_sha256='c'*64, initializer_commitment_sha256='d'*64,
        validator_sha256='e'*64, readiness_source_sha256='f'*64)


def envelope():
    return dict(schema='mastermind.glm_qualified_account_readiness/v1', host='ubuntu0',
        transport_alias='mmx-ubuntu0', mode='glm', config_scope='qualified_glm_context.v1',
        validator_sha256='e'*64, observed_at=1000, status='known',
        accounts={'inert-account': True}, context=binding(),
        config_identity=[1,2,0o100600,1000,1000,1,50,100,100])


def test_distinct_observation_not_qualification_object_or_legacy_projection():
    m=module()
    assert callable(getattr(m, 'validate_observation', None)), 'qualified observation producer is missing'
    assert m.validate_observation(envelope(), binding=binding(), now=1000)==envelope()
    with pytest.raises(ValueError):m.validate_observation({}, binding=binding(), now=1000)
    old=envelope();old['schema']='mastermind.glm_local_account_readiness.v1'
    with pytest.raises(ValueError):m.validate_observation(old, binding=binding(), now=1000)


@pytest.mark.parametrize('field',list(binding()))
def test_each_context_field_must_match_real_current_binding(field):
    m=module()
    assert callable(getattr(m,'validate_observation',None)), 'qualified context consumer is missing'
    value=envelope();value['context'][field]='foreign'
    with pytest.raises(ValueError):m.validate_observation(value,binding=binding(),now=1000)


@pytest.mark.parametrize('at',[399,1002,True,float('nan'),float('inf'),None])
def test_stale_future_bool_nonfinite_unknown_never_ready(at):
    m=module()
    assert callable(getattr(m,'validate_observation',None)), 'qualified freshness consumer is missing'
    value=envelope();value['observed_at']=at
    with pytest.raises(ValueError):m.validate_observation(value,binding=binding(),now=1000)


@pytest.mark.parametrize('flags',[{'foreign':True},{'inert-account':1},{'inert-account':'true'},{}])
def test_no_fabricated_or_extra_alias_flags(flags):
    m=module()
    assert callable(getattr(m,'validate_observation',None)), 'qualified account join is missing'
    value=envelope();value['accounts']=flags
    with pytest.raises(ValueError):m.validate_observation(value,binding=binding(),now=1000)


def test_actual_consumer_intersection_and_independent_physical_freshness():
    m=module()
    assert callable(getattr(m,'filter_accounts',None))
    rows=[{'name':'inert-account'},{'name':'foreign'}]
    doc=dict(host='ubuntu0',ts=1000,reachable=True,boot_id=binding()['boot_id'],
             glm_local_account_readiness=envelope())
    kw=dict(binding=binding(),host='ubuntu0',transport_alias='mmx-ubuntu0',
            model='glm-5.3-flash',validator_sha256='e'*64,now=1000)
    ready,reason=m.filter_accounts(rows,doc,**kw)
    assert ready==[rows[0]] and ready[0] is rows[0] and reason=='ok'
    for key,value in [('ts',819),('reachable',False),('boot_id','foreign')]:
        changed=copy.deepcopy(doc);changed[key]=value
        assert m.filter_accounts(rows,changed,**kw)[0]==[]
    doc['ts']=1000;doc['glm_local_account_readiness']['observed_at']=399
    assert m.filter_accounts(rows,doc,**kw)[0]==[]


def test_real_remote_fixed_validator_no_secret_or_hook_code(tmp_path,monkeypatch):
    m=module()
    assert type(getattr(m,'READINESS_PROBE',None)) is str, 'fixed readiness observer missing'
    import subprocess,sys
    config=tmp_path/'config.json'
    config.write_text(json.dumps({'accounts':{'inert-account':{'api_key':'SYNTHETIC_CANARY_DO_NOT_EMIT'}}}))
    config.chmod(0o600)
    validator=(ROOT/'ops/native_fabric/quota_continuity/source/glm_keys.py').read_bytes()
    request=dict(initializer_commitment={'initialized_context':{'home':str(tmp_path),'glm_config':str(config)}},context=binding(),validator_b64=__import__('base64').b64encode(validator).decode())
    request['context']['validator_sha256']=hashlib.sha256(validator).hexdigest()
    request['context']['boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip() if sys.platform=='linux' else '12345678-1234-1234-1234-123456789abc'
    # Only the fixed observer body executes. Kernel boot reader is a disclosed
    # fixture on Darwin; Linux uses the actual disposable process observation.
    program=m.READINESS_PROBE
    if sys.platform!='linux':
        program=program.replace("Path('/proc/sys/kernel/random/boot_id').read_text().strip()",repr(request['context']['boot_id']))
    # Disposable filesystem root fixture: actual held-file reads/validator run,
    # but Root ancestor authority is synthetic, never a native qualification.
    request['initializer_commitment']['initialized_context']['glm_config']='/config.json'
    setup="import os,types\n_open=os.open\n_fstat=os.fstat\n_fixture_root=None\ndef _root_open(path,flags,*args,**kwargs):\n global _fixture_root\n if path=='/':\n  _fixture_root=_open("+repr(str(tmp_path))+",flags);return _fixture_root\n return _open(path,flags,*args,**kwargs)\ndef _root_stat(fd):\n s=_fstat(fd)\n if fd==_fixture_root:return types.SimpleNamespace(st_mode=s.st_mode,st_uid=0)\n return s\nos.open=_root_open;os.fstat=_root_stat\n"
    if sys.platform!='linux':
        start=program.index('def no_acl(fd):');end=program.index('def check():',start)
        program=program[:start]+'def no_acl(fd):pass\n'+program[end:]
    script='import base64,json,sys\n_p=json.loads(base64.b64decode(sys.argv[1]))\n'+setup+program
    r=subprocess.run([sys.executable,'-I','-S','-B','-c',script,
        __import__('base64').b64encode(json.dumps(request).encode()).decode()],
        env={'PATH':'/usr/bin:/bin','HOME':str(tmp_path),'GLM_CONFIG':'/config.json'},
        capture_output=True,timeout=10)
    assert r.returncode==0 and r.stderr==b''
    value=json.loads(r.stdout)['readiness']
    assert value['accounts']=={'inert-account':True}
    assert b'SYNTHETIC_CANARY' not in r.stdout+r.stderr
    assert 'source ' not in program and 'subprocess' not in program


def test_physical_recurring_mode_is_explicit_and_does_not_call_readiness_builder():
    s=(SOURCE/'host_pull.sh').read_text()
    assert '--physical-only' in s, 'recurring physical-only mode missing'
    assert 'pass_physical_only' in s
    start=s.index('pass_physical_only()')
    end=s.index('\n}\n',start)
    body=s[start:end]
    assert 'GLM_PROBE_FILE' not in body and 'HOST_ENV' not in body
    assert 'write-physical-state' in body


@pytest.fixture
def context(tmp_path):
    m=module()
    from tests.test_paid_initializer_nested_join import request
    request_data=request()
    c=request_data['initializer_commitment']
    c['host_ref']='ubuntu0';c['transport_alias']='mmx-ubuntu0'
    c['startup']['profile']='cpython-3.12-linux-root-prefix-nosite.v1'
    sources={name:(SOURCE/name).read_bytes() for name in (
        'paid_initializer.py','paid_initializer_token_data.py','paid_initializer_nested_data.py',
        'paid_host_qualification.py','host_pull.sh','host_pull_backend.py','paid_host_readiness.py')}
    sources['glm_keys.py']=(ROOT/'ops/native_fabric/quota_continuity/source/glm_keys.py').read_bytes()
    b=binding();b['validator_sha256']=hashlib.sha256(sources['glm_keys.py']).hexdigest()
    b['initializer_commitment_sha256']=m._digest(c)
    b['readiness_source_sha256']=hashlib.sha256(sources['paid_host_readiness.py']).hexdigest()
    checks=[]
    ctx=m.InstalledReadinessContext(m._SEAL,binding=b,commitment=c,sources=sources,
                                  root=tmp_path/('a'*40),checks=[lambda:checks.append('source-rechecked')])
    return m,ctx,checks


def test_fixed_compiler_first_policy_and_stdin_hash_no_argv_expansion(context):
    import shlex
    m,ctx,checks=context
    plan=m.prepare_refresh(ctx)
    parts=shlex.split(plan['command'])
    assert parts[0]==ctx.initializer_commitment['bootstrap_python']['path']
    assert parts[1:5]==['-I','-S','-B','-c']
    assert parts[5].startswith('import sys\n')
    assert parts[5].index('_paid_no_site_check()')<parts[5].index('import base64')
    assert hashlib.sha256(plan['stdin'].encode()).hexdigest()==parts[6]
    assert len(plan['command'].encode())<100000 and len(plan['stdin'])>65536
    assert len(parts)==7 and len(checks)>3
    # No mutable remote path/module load or helper source is generated.
    assert 'sys.path' not in parts[5] and 'source ' not in parts[5]
    assert plan['request']['schema']=='mastermind.paid_readiness_probe/v1'


def test_real_host_codec_and_new_observation_join_without_opaque_object(context):
    from tests.test_paid_initializer_nested_join import observation as host_observation
    m,ctx,checks=context
    plan=m.prepare_refresh(ctx)
    host=host_observation(plan['request'])
    host['boot_id']=ctx.binding['boot_id']
    ready=envelope();ready['context']=ctx.binding
    ready['validator_sha256']=ctx.binding['validator_sha256']
    wire={'readiness':ready,'host_observation':dict(host),'pre_execution':host['pre_execution']}
    wire['host_observation'].pop('pre_execution')
    assert m.validate_refresh_result(m.canonical(wire),plan,ctx,now=1000)==ready
    wire['pre_execution']['nested_inputs']['helper']['sha256']='0'*64
    with pytest.raises(ValueError):m.validate_refresh_result(m.canonical(wire),plan,ctx,now=1000)


def test_context_data_detached_opaque_and_revocation_at_source_edge(context):
    import pickle
    m,ctx,checks=context
    value=ctx.binding;value['account']='foreign'
    assert ctx.binding['account']=='inert-account'
    with pytest.raises(ValueError):ctx._binding=b'{}'
    with pytest.raises(ValueError):pickle.dumps(ctx)
    ctx._checks.append(m._refuse)
    with pytest.raises(ValueError):m.prepare_refresh(ctx)


class OwnerMetadataFixture:
    """UID501 metadata fixture only; real disposable file I/O and CAS execute."""
    def __init__(self,real,uid=501):self.real=real;self.uid=uid
    def __getattr__(self,name):return getattr(self.real,name)
    def getuid(self):return self.uid
    def geteuid(self):return self.uid
    def fchown(self,fd,uid,gid):
        assert uid==501 and type(gid)is int
    @staticmethod
    def calibrated(s):
        data={name:getattr(s,name) for name in dir(s) if name.startswith('st_')}
        data['st_uid']=501
        return SimpleNamespace(**data)
    def fstat(self,fd):return self.calibrated(self.real.fstat(fd))
    def stat(self,*args,**kwargs):return self.calibrated(self.real.stat(*args,**kwargs))
    def lstat(self,*args,**kwargs):return self.calibrated(self.real.lstat(*args,**kwargs))


@pytest.fixture
def state(context,tmp_path,monkeypatch):
    import os
    m,ctx,checks=context
    directory=tmp_path/'hosts';directory.mkdir(mode=0o700)
    document=dict(host='ubuntu0',ts=1000,reachable=True,boot_id=ctx.binding['boot_id'],
        telemetry_mode='physical-only.v1',load1=0.25,ncpu=32)
    (directory/'ubuntu0.json').write_bytes(m.canonical(document))
    monkeypatch.setattr(m,'os',OwnerMetadataFixture(os))
    monkeypatch.setattr(m.time,'time',lambda:1000)
    return m,ctx,directory,document


def test_genuine_state_publication_does_not_freshen_physical_time(state):
    m,ctx,directory,doc=state
    ready=envelope();ready['context']=ctx.binding;ready['validator_sha256']=ctx.binding['validator_sha256']
    published=m._publish(directory,ctx,ready)
    assert published['ts']==doc['ts'] and published['glm_local_account_readiness']==ready
    ready['observed_at']=1001
    m._publish(directory,ctx,ready)
    assert json.loads((directory/'ubuntu0.json').read_bytes())['ts']==1000


def test_refusal_durable_restart_cannot_clear_or_dispatch(state,monkeypatch):
    from contextlib import contextmanager
    m,ctx,directory,doc=state
    refused=m._refusal(ctx,now=1000)
    m._publish(directory,ctx,refused)
    original=(directory/'ubuntu0.json').read_bytes()
    @contextmanager
    def installed():yield ctx
    monkeypatch.setattr(m,'open_installed_context',installed)
    monkeypatch.setattr(m,'_OWNER',directory.parent)
    # Production fixes state/hosts; only this private path fixture maps it.
    monkeypatch.setattr(m,'_state_read',lambda ignored: (original,None,None))
    monkeypatch.setattr(m,'_observe',lambda *_:pytest.fail('refused original must not be queried'))
    with pytest.raises(ValueError):m.refresh()
    # A new reader process must reach the same refusal before transport.
    with pytest.raises(ValueError):m.refresh()
    assert (directory/'ubuntu0.json').read_bytes()==original
    with pytest.raises(ValueError):m._publish(directory,ctx,None)


def test_root_correction_invalid_cas_no_dispatch_and_failed_query_retains(state,monkeypatch):
    import os,sys
    from contextlib import contextmanager
    m,ctx,directory,doc=state
    refused=m._refusal(ctx,now=1000);m._publish(directory,ctx,refused)
    original=(directory/'ubuntu0.json').read_bytes()
    @contextmanager
    def installed():yield ctx
    monkeypatch.setattr(m,'open_installed_context',installed)
    monkeypatch.setattr(m,'os',OwnerMetadataFixture(os,uid=0))
    monkeypatch.setattr(m,'sys',SimpleNamespace(platform='darwin',flags=SimpleNamespace(isolated=1,no_site=1),dont_write_bytecode=True))
    monkeypatch.setattr(m,'_correction_interval',lambda: __import__('contextlib').nullcontext())
    # Fixed normal namespace is redirected only by the private test fixture.
    monkeypatch.setattr(m,'_OWNER',directory.parent)
    read=m._state_read
    monkeypatch.setattr(m,'_state_read',lambda ignored:read(directory))
    seen=[]
    def unavailable(_,**kw):seen.append('query');raise m.ObservationUnavailable()
    monkeypatch.setattr(m,'_observe',unavailable)
    kw=dict(expected_context_sha256=m._digest(ctx.binding),expected_refusal_sha256=m._digest(refused))
    with pytest.raises(ValueError):m.correct_refusal(**dict(kw,expected_refusal_sha256='0'*64))
    assert seen==[]
    with pytest.raises(m.ObservationUnavailable):m.correct_refusal(**kw)
    assert seen==['query'] and (directory/'ubuntu0.json').read_bytes()==original


@pytest.fixture
def actual_consumer(context,tmp_path,monkeypatch):
    import sys
    from contextlib import contextmanager
    m,old,_=context
    monkeypatch.syspath_prepend(str(ROOT/'ops/native_fabric/quota_continuity/source'))
    monkeypatch.syspath_prepend(str(SOURCE))
    spec=importlib.util.spec_from_file_location('glm_host_account_readiness',ROOT/'ops/native_fabric/quota_continuity/source/glm_host_account_readiness.py')
    predicate=importlib.util.module_from_spec(spec);spec.loader.exec_module(predicate)
    monkeypatch.setitem(sys.modules,'glm_host_account_readiness',predicate)
    spec=importlib.util.spec_from_file_location('actual_qualified_consumer',SOURCE/'glm_host_account_source.py')
    source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
    registry=tmp_path/'registry.json'
    registry.write_bytes(m.canonical({'ubuntu0':dict(platform='linux',roles=['lanes'],
        ssh_alias='mmx-ubuntu0',allowed_modes=['glm'],qualification_only_modes=[])}))
    validator=tmp_path/'validator.py';validator.write_bytes(old._sources['glm_keys.py'])
    directory=tmp_path/'readiness';directory.mkdir(mode=0o700)
    b=old.binding;b['registry_sha256']=hashlib.sha256(registry.read_bytes()).hexdigest()
    ctx=m.InstalledReadinessContext(m._SEAL,binding=b,commitment=old.initializer_commitment,
        sources=old._sources,root=old._root,checks=old._checks)
    @contextmanager
    def installed():
        ctx.check();yield ctx;ctx.check()
    monkeypatch.setattr(m,'open_installed_context',installed)
    monkeypatch.setitem(sys.modules,'paid_host_readiness',m)
    value=envelope();value['context']=ctx.binding;value['validator_sha256']=ctx.binding['validator_sha256']
    doc=dict(host='ubuntu0',ts=1000,reachable=True,boot_id=ctx.binding['boot_id'],glm_local_account_readiness=value)
    path=directory/'ubuntu0.json';path.write_bytes(m.canonical(doc))
    options=dict(host='ubuntu0',model='glm-5.3-flash',now=1000,
        hosts_path=registry,state_dir=directory,validator_path=validator,mode='glm')
    return source,m,ctx,path,options


def test_actual_current_reader_qualified_context_and_legacy_distinction(actual_consumer):
    source,m,ctx,path,options=actual_consumer
    rows=[{'name':'inert-account'}]
    assert source.filter_observed_accounts(rows,**options,require_qualified_context=True)==(rows,'ok')
    # The ordinary picker automatically validates a new envelope too.
    assert source.filter_observed_accounts(rows,**options)[0]==rows
    doc=json.loads(path.read_bytes());doc['glm_local_account_readiness']['context']['source_config_sha256']='0'*64
    path.write_bytes(m.canonical(doc))
    assert source.filter_observed_accounts(rows,**options)[0]==[]
    doc['glm_local_account_readiness']=dict(schema='mastermind.glm_local_account_readiness.v1',
        host='ubuntu0',transport_alias='mmx-ubuntu0',mode='glm',config_scope='launcher_glm_config.v1',
        validator_sha256=ctx.binding['validator_sha256'],observed_at=1000,status='known',accounts={'inert-account':True})
    path.write_bytes(m.canonical(doc))
    assert source.filter_observed_accounts(rows,**options)[0]==rows
    assert source.filter_observed_accounts(rows,**options,require_qualified_context=True)[0]==[]


@pytest.mark.parametrize('change',['stale','boot','validator','registry','source_revoked','config_uid','config_gid'])
def test_actual_current_reader_refuses_changed_inputs(actual_consumer,change):
    source,m,ctx,path,options=actual_consumer
    doc=json.loads(path.read_bytes())
    if change=='stale':doc['glm_local_account_readiness']['observed_at']=399
    elif change=='boot':doc['boot_id']='00000000-0000-0000-0000-000000000000'
    elif change=='validator':options['validator_path'].write_text('changed')
    elif change=='registry':options['hosts_path'].write_bytes(m.canonical({'ubuntu0':dict(ssh_alias='other',roles=['lanes'],allowed_modes=['glm'],qualification_only_modes=[])}))
    elif change=='config_uid':doc['glm_local_account_readiness']['config_identity'][3]=1001
    elif change=='config_gid':doc['glm_local_account_readiness']['config_identity'][4]=1001
    else:ctx._checks.append(m._refuse)
    path.write_bytes(m.canonical(doc))
    assert source.filter_observed_accounts([{'name':'inert-account'}],**options,require_qualified_context=True)[0]==[]


def test_physical_writer_preserves_new_observation_time_and_original_refusal(context,tmp_path,monkeypatch):
    import sys
    m,ctx,_=context
    monkeypatch.syspath_prepend(str(ROOT/'ops/native_fabric/quota_continuity/source'))
    monkeypatch.syspath_prepend(str(SOURCE))
    spec=importlib.util.spec_from_file_location('inert_new_physical_backend',SOURCE/'host_pull_backend.py')
    backend=importlib.util.module_from_spec(spec);spec.loader.exec_module(backend)
    directory=tmp_path/'physical';directory.mkdir(mode=0o700)
    code=hashlib.sha256((SOURCE/'lane_runtime.py').read_bytes()).hexdigest()
    physical=('HOST_PULL_PHYSICAL_V1 BEGIN\nts=1000\nload1=0\nload5=0\nncpu=32\nmem_free_gb=10\ndisk_free_gb=100\n'
        'process_active_lanes=0\nactive_lanes=0\nactive_lanes_status=known\nlease_active_lanes=0\nlease_locked_lanes=0\n'
        'lease_legacy_lanes=0\nlease_unlocked_lanes=0\ntools=python3,codex\noccupancy_source_sha256='+code+'\nboot_id='+ctx.binding['boot_id']+
        '\nHOST_PULL_PHYSICAL_V1 EXIT 0\n')
    path=directory/'ubuntu0.json'
    ready=envelope();path.write_bytes(m.canonical(dict(host='ubuntu0',glm_local_account_readiness=ready)))
    args=['backend',str(directory),'ubuntu0','0',physical,'mmx-ubuntu0']
    monkeypatch.setattr(sys,'argv',args)
    backend.write_state(physical_only=True)
    value=json.loads(path.read_bytes())
    assert value['reachable'] is True and value['boot_id']==ctx.binding['boot_id']
    assert value['glm_local_account_readiness']==ready
    assert value['glm_local_account_readiness']['observed_at']==1000
    refusal=m._refusal(ctx,now=900)
    value['glm_local_account_readiness']=refusal;path.write_bytes(m.canonical(value))
    backend.write_state(physical_only=True)
    assert json.loads(path.read_bytes())['glm_local_account_readiness']==refusal
    assert json.loads(path.read_bytes())['probe_diagnostic']['optional_readiness']['state']=='NOT_REQUESTED'


def test_actual_picker_and_sqlite_broker_use_same_new_observation(actual_consumer,tmp_path,monkeypatch):
    """Real routing/acquire algorithms, disposable policy/DB, no live lease."""
    import sys,datetime
    source,m,ctx,path,options=actual_consumer
    monkeypatch.setitem(sys.modules,'glm_host_account_source',source)
    monkeypatch.setattr(source,'HERE',tmp_path)
    (tmp_path/'glm_keys.py').write_bytes(options['validator_path'].read_bytes())
    state=tmp_path/'state/hosts';state.mkdir(parents=True,mode=0o700)
    document=json.loads(path.read_bytes())
    document.update(load1=0.0,load5=0.0,ncpu=32,mem_free_gb=10,disk_free_gb=100,
        active_lanes=0,active_lanes_status='known',process_active_lanes=0,tools=['claude','python3'])
    actual_state=state/'ubuntu0.json';actual_state.write_bytes(m.canonical(document))
    registry=json.loads(options['hosts_path'].read_bytes())
    registry['ubuntu0'].update(load_gate=10,min_free_mem_gb=3,min_free_gb=60,
                               max_active=2,lane_ceiling=2,cores=32)
    options['hosts_path'].write_bytes(m.canonical(registry))
    # Reissue only the explicit source fixture binding after changing its DATA.
    b=ctx.binding;b['registry_sha256']=hashlib.sha256(options['hosts_path'].read_bytes()).hexdigest()
    nextctx=m.InstalledReadinessContext(m._SEAL,binding=b,commitment=ctx.initializer_commitment,
        sources=ctx._sources,root=ctx._root,checks=ctx._checks)
    from contextlib import contextmanager
    @contextmanager
    def installed():yield nextctx
    monkeypatch.setattr(m,'open_installed_context',installed)
    document['glm_local_account_readiness']['context']=b
    actual_state.write_bytes(m.canonical(document))
    import lease_broker
    policy=tmp_path/'accounts.json'
    policy.write_bytes(m.canonical({'providers':{'glm':{'enabled':True,'accounts':[
        {'name':'inert-account','per_account_cap':2}]}}}))
    broker=lease_broker.Broker(db_path=str(tmp_path/'inert-leases.sqlite'),lock_path=str(tmp_path/'inert-leases.lock'),
        accounts_path=str(policy),now_fn=lambda:1000,check_pid=False,external_gates=False,
        this_host='inert-controller',hosts_path=str(options['hosts_path']),status_json=str(tmp_path/'empty-status.json'))
    import host_pick,pick
    monkeypatch.setattr(host_pick,'load_registry',lambda:registry)
    monkeypatch.setattr(host_pick,'HOSTS_STATE_DIR',str(state))
    monkeypatch.setattr(lease_broker,'default_broker',lambda:broker)
    monkeypatch.setattr(pick,'datetime',SimpleNamespace(now=lambda tz:datetime.datetime.fromtimestamp(1000,datetime.timezone.utc)))
    routes=pick._eligible_host_routes('auto',required_modes=['glm'],required_platforms=['linux'],glm_model='glm-5.3-flash')
    assert 'glm' in routes,(dict(routes),routes.blockers)
    result=broker.acquire('inert-original-root','glm',host='ubuntu0',model='glm-5.3-flash',
        task_class='remote-glm',pid=123,ttl=60,wait=0)
    assert result.ok and result.account=='inert-account'
    assert broker.release(result.lease_id,'inert-original-root')
    document['glm_local_account_readiness']['context']['initializer_commitment_sha256']='0'*64
    actual_state.write_bytes(m.canonical(document))
    assert 'glm' not in pick._eligible_host_routes('auto',required_modes=['glm'],required_platforms=['linux'],glm_model='glm-5.3-flash')
    refused=broker.acquire('inert-second-root','glm',host='ubuntu0',model='glm-5.3-flash',
        task_class='remote-glm',pid=124,ttl=60,wait=0)
    assert not refused.ok and refused.reason=='host_account_unavailable'
    with broker._conn() as conn:
        assert conn.execute("select count(*) from leases where orchestrator_id='inert-second-root'").fetchone()[0]==0
        assert conn.execute('select count(*) from waiters').fetchone()[0]==0


@pytest.mark.parametrize('status',['unknown','refused'])
def test_root_correction_nonobserved_result_retains_exact_original(state,monkeypatch,status):
    import os
    from contextlib import contextmanager
    m,ctx,directory,_=state
    refused=m._refusal(ctx,now=1000);m._publish(directory,ctx,refused)
    original=(directory/'ubuntu0.json').read_bytes()
    @contextmanager
    def installed():yield ctx
    monkeypatch.setattr(m,'open_installed_context',installed)
    monkeypatch.setattr(m,'os',OwnerMetadataFixture(os,uid=0))
    monkeypatch.setattr(m,'sys',SimpleNamespace(platform='darwin',flags=SimpleNamespace(isolated=1,no_site=1),dont_write_bytecode=True))
    monkeypatch.setattr(m,'_correction_interval',lambda: __import__('contextlib').nullcontext())
    monkeypatch.setattr(m,'_OWNER',directory.parent)
    read=m._state_read;monkeypatch.setattr(m,'_state_read',lambda _:read(directory))
    result=m._refusal(ctx,now=1000);result['status']=status
    monkeypatch.setattr(m,'_observe',lambda _,**kw:result)
    with pytest.raises(ValueError):m.correct_refusal(expected_context_sha256=m._digest(ctx.binding),expected_refusal_sha256=m._digest(refused))
    assert (directory/'ubuntu0.json').read_bytes()==original


def test_root_correction_only_genuine_valid_observation_replaces_refusal(state,monkeypatch):
    import os
    from contextlib import contextmanager
    m,ctx,directory,_=state
    refused=m._refusal(ctx,now=1000);m._publish(directory,ctx,refused)
    @contextmanager
    def installed():yield ctx
    monkeypatch.setattr(m,'open_installed_context',installed)
    monkeypatch.setattr(m,'os',OwnerMetadataFixture(os,uid=0))
    monkeypatch.setattr(m,'sys',SimpleNamespace(platform='darwin',flags=SimpleNamespace(isolated=1,no_site=1),dont_write_bytecode=True))
    monkeypatch.setattr(m,'_correction_interval',lambda: __import__('contextlib').nullcontext())
    monkeypatch.setattr(m,'_OWNER',directory.parent)
    read=m._state_read;monkeypatch.setattr(m,'_state_read',lambda _:read(directory))
    publish=m._publish
    monkeypatch.setattr(m,'_publish',lambda _,context,observation,**kw:publish(directory,context,observation,**kw))
    actual=envelope();actual['context']=ctx.binding;actual['validator_sha256']=ctx.binding['validator_sha256']
    seen=[]
    def new_observation(context,**kw):
        seen.append(context.binding)
        return m.validate_observation(actual,binding=context.binding,now=1000)
    monkeypatch.setattr(m,'_observe',new_observation)
    assert m.correct_refusal(expected_context_sha256=m._digest(ctx.binding),expected_refusal_sha256=m._digest(refused))=='OBSERVED'
    assert len(seen)==1
    assert json.loads((directory/'ubuntu0.json').read_bytes())['glm_local_account_readiness']==actual


def test_loss_is_unavailable_next_readonly_cycle_eligible_not_refusal(state,monkeypatch):
    from contextlib import contextmanager
    m,ctx,directory,_=state
    @contextmanager
    def installed():yield ctx
    monkeypatch.setattr(m,'open_installed_context',installed)
    monkeypatch.setattr(m,'_OWNER',directory.parent)
    read=m._state_read;monkeypatch.setattr(m,'_state_read',lambda _:read(directory))
    publish=m._publish;monkeypatch.setattr(m,'_publish',lambda _,context,observation,**kw:publish(directory,context,observation,**kw))
    seen=[]
    actual=envelope();actual['context']=ctx.binding;actual['validator_sha256']=ctx.binding['validator_sha256']
    def observe(_):
        seen.append('new-readonly-observation')
        if len(seen)==1:raise m.ObservationUnavailable()
        return actual
    monkeypatch.setattr(m,'_observe',observe)
    assert m.refresh()=='UNAVAILABLE'
    assert 'glm_local_account_readiness' not in json.loads((directory/'ubuntu0.json').read_bytes())
    assert m.refresh()=='OBSERVED' and len(seen)==2


def test_no_root_or_cas_corrective_mode_cannot_dispatch(context,monkeypatch):
    m,ctx,_=context
    monkeypatch.setattr(m,'_observe',lambda _:pytest.fail('unqualified correction dispatch'))
    with pytest.raises(ValueError):m.correct_refusal(expected_context_sha256='a'*64,expected_refusal_sha256='b'*64)


def test_native_kernel_peer_reports_actual_uid_no_root_claim(context):
    import os,socket
    m,_,_=context
    a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        assert m._kernel_peer_uid(a)==os.geteuid()
        assert m._kernel_peer_uid(b)==os.geteuid()
    finally:a.close();b.close()


@pytest.mark.parametrize('mutation',['missing','wrong_uid','wrong_request','wrong_refusal','replay'])
def test_internal_dispatch_refusal_gate_never_accepts_labels(context,tmp_path,monkeypatch,mutation):
    import os,socket
    from contextlib import contextmanager
    m,ctx,_=context
    plan=m.prepare_refresh(ctx)
    refused=m._refusal(ctx,now=1000)
    @contextmanager
    def installed():yield ctx
    monkeypatch.setattr(m,'open_installed_context',installed)
    monkeypatch.setattr(m,'_state_read',lambda _: (m.canonical({'glm_local_account_readiness':refused}),None,None))
    monkeypatch.delenv('H1_READINESS_CORRECTION_FD',raising=False)
    if mutation=='missing':
        with pytest.raises(ValueError):m.prepare_transport_request(m.canonical(plan['request']))
        return
    parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
    descriptor=child.detach()
    monkeypatch.setenv('H1_READINESS_CORRECTION_FD',str(descriptor))
    frame=dict(schema='mastermind.qualified_readiness_correction/v1',context_sha256=m._digest(ctx.binding),
               request_sha256=m._digest(plan['request']),refusal_sha256=m._digest(refused))
    if mutation=='wrong_request':frame['request_sha256']='0'*64
    elif mutation=='wrong_refusal':frame['refusal_sha256']='0'*64
    elif mutation=='replay':frame['request_sha256']=m._digest(m.prepare_refresh(ctx)['request'])
    if mutation!='wrong_uid':monkeypatch.setattr(m,'_kernel_peer_uid',lambda _:0)
    parent.sendall(m.canonical(frame));parent.shutdown(socket.SHUT_WR)
    try:
        with pytest.raises(ValueError):m.prepare_transport_request(m.canonical(plan['request']))
    finally:
        parent.close()
        try:os.close(descriptor)
        except OSError:pass


def test_private_root_frame_one_use_exact_binding_and_socket_closed(context,monkeypatch):
    import os,socket
    from contextlib import contextmanager
    m,ctx,_=context
    plan=m.prepare_refresh(ctx);refused=m._refusal(ctx,now=1000)
    @contextmanager
    def installed():yield ctx
    monkeypatch.setattr(m,'open_installed_context',installed)
    monkeypatch.setattr(m,'_state_read',lambda _: (m.canonical({'glm_local_account_readiness':refused}),None,None))
    parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM);fd=child.detach()
    monkeypatch.setenv('H1_READINESS_CORRECTION_FD',str(fd))
    # Only kernel Root principal is synthetic; actual AF_UNIX framing/lifetime,
    # nonce/context/refusal/request validation and compiler execute unchanged.
    monkeypatch.setattr(m,'_kernel_peer_uid',lambda _:0)
    parent.sendall(m.canonical(dict(schema='mastermind.qualified_readiness_correction/v1',
        context_sha256=m._digest(ctx.binding),request_sha256=m._digest(plan['request']),refusal_sha256=m._digest(refused))))
    parent.shutdown(socket.SHUT_WR)
    try:
        assert m.prepare_transport_request(m.canonical(plan['request']))['request']==plan['request']
        with pytest.raises(OSError):os.fstat(fd)
        with pytest.raises((OSError,ValueError)):m.prepare_transport_request(m.canonical(plan['request']))
    finally:parent.close()


def test_same_shell_transport_strict_flags_stdin_and_private_fd_closed(tmp_path):
    import os,shutil,subprocess,sys,socket
    ext=tmp_path/'ext';ext.mkdir()
    shutil.copyfile(SOURCE/'host_pull.sh',ext/'host_pull.sh')
    (ext/'host_pull_probe.template').write_text('inert-unused')
    (ext/'host_pull_backend.py').write_text("import os,sys\nassert sys.argv[1:] == ['qualified-readiness-prepare']\nassert os.fstat(9)\nassert sys.stdin.buffer.read()==b'{}'\nprint('mmx-ubuntu0')\nprint('fixed-inert-remote-command')\nprint('{\"public\":true}')\n")
    bin=tmp_path/'bin';bin.mkdir();(bin/'python3').symlink_to(sys.executable)
    args=tmp_path/'args.json';data=tmp_path/'stdin'
    ssh=bin/'ssh'
    ssh.write_text('#!'+sys.executable+'\nimport os,sys,json\ntry:os.fstat(9)\nexcept OSError:pass\nelse:raise SystemExit(99)\nassert "H1_READINESS_CORRECTION_FD" not in os.environ\nopen('+repr(str(args))+',"w").write(json.dumps(sys.argv[1:]))\nopen('+repr(str(data))+',"wb").write(sys.stdin.buffer.read())\nprint("{}")\n')
    ssh.chmod(0o700)
    parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
    wrapper='import os,sys\nfd=int(sys.argv[1])\nif fd!=9:os.dup2(fd,9);os.close(fd)\nos.set_inheritable(9,True)\nos.execve("/bin/bash",["/bin/bash",sys.argv[2],"--qualified-readiness-transport","ubuntu0"],dict(os.environ,H1_READINESS_CORRECTION_FD="9"))'
    try:
        r=subprocess.run([sys.executable,'-I','-S','-B','-c',wrapper,str(child.fileno()),str(ext/'host_pull.sh')],
            input=b'{}',pass_fds=(child.fileno(),),env={'PATH':str(bin)+':/usr/bin:/bin','HOME':str(tmp_path)},
            capture_output=True,timeout=10)
    finally:parent.close();child.close()
    assert r.returncode==0,r.stderr
    argv=json.loads(args.read_bytes())
    for value in ('BatchMode=yes','StrictHostKeyChecking=yes','UpdateHostKeys=no'):assert value in argv
    assert argv[-2:]==['mmx-ubuntu0','fixed-inert-remote-command']
    assert data.read_bytes()==b'{"public":true}\n'


@pytest.mark.parametrize('extra',[['--inspect-host-env','ubuntu0'],['--diagnose-physical','ubuntu0'],['--paid-qualification','ubuntu0']])
def test_physical_publication_cannot_enter_old_private_mode(tmp_path,extra):
    import os,subprocess
    r=subprocess.run(['/bin/bash',str(SOURCE/'host_pull.sh'),'--physical-only',*extra],
        env={'PATH':'/usr/bin:/bin','HOME':str(tmp_path)},capture_output=True,timeout=5)
    assert r.returncode==78
    assert b'modes are exclusive' in r.stderr


def test_provider_config_identity_same_fresh_current_observation_and_no_timestamp_pin(state,monkeypatch):
    m,ctx,directory,_=state
    actual=envelope();actual['context']=ctx.binding;actual['validator_sha256']=ctx.binding['validator_sha256']
    m._publish(directory,ctx,actual)
    monkeypatch.setattr(m,'_OWNER',directory.parent)
    read=m._state_read;monkeypatch.setattr(m,'_state_read',lambda _:read(directory))
    before=m.qualified_config_identity(ctx)
    actual['observed_at']=1001;m._publish(directory,ctx,actual)
    assert m.qualified_config_identity(ctx)==before
    before[0]=999
    assert m.qualified_config_identity(ctx)[0]==1
    actual['accounts']['inert-account']=False;m._publish(directory,ctx,actual)
    with pytest.raises(ValueError):m.qualified_config_identity(ctx)


@pytest.mark.parametrize('change',['mode','uid','gid','stale','changed_source'])
def test_provider_config_identity_refuses_foreign_or_drifted_observation(state,monkeypatch,change):
    m,ctx,directory,_=state
    actual=envelope();actual['context']=ctx.binding;actual['validator_sha256']=ctx.binding['validator_sha256']
    if change=='mode':actual['config_identity'][2]=0o100644
    elif change=='uid':actual['config_identity'][3]=1001
    elif change=='gid':actual['config_identity'][4]=1001
    elif change=='stale':actual['observed_at']=399
    else:actual['context']['source_config_sha256']='0'*64
    doc=json.loads((directory/'ubuntu0.json').read_bytes());doc['glm_local_account_readiness']=actual
    (directory/'ubuntu0.json').write_bytes(m.canonical(doc))
    monkeypatch.setattr(m,'_OWNER',directory.parent)
    read=m._state_read;monkeypatch.setattr(m,'_state_read',lambda _:read(directory))
    with pytest.raises(ValueError):m.qualified_config_identity(ctx)
