"""Discriminating parent-wiring checks; no live config, SSH, provider or lease."""
from pathlib import Path
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import types
import pytest

COMPONENT = Path(__file__).resolve().parents[1]/'integrations/session_bridge/glm_host_account_pairing'

@pytest.fixture
def ext(tmp_path, monkeypatch):
    dst=tmp_path/'ext';shutil.copytree(Path(__file__).parent/'fixtures/glm_host_account_pairing',dst)
    subprocess.run(['git','apply',str(COMPONENT/'glm-host-account-pairing.patch')],cwd=dst,check=True,capture_output=True)
    monkeypatch.syspath_prepend(str(dst))
    for name in ['glm_host_account_source','glm_host_account_probe','lease_broker']:
        monkeypatch.delitem(sys.modules,name,raising=False)
    return dst


def load(name, ext):
    spec=importlib.util.spec_from_file_location(name,ext/(name+'.py'))
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module


def probe_fixture(ext,tmp_path, *, source=True, raw=None, source_tail='', remove_default=False):
    module=load('glm_host_account_probe',ext)
    home=tmp_path/'home';(home/'lanes/ext').mkdir(parents=True)
    selected=tmp_path/'launch config.json'
    selected.write_text(raw if raw is not None else json.dumps({'accounts':{'ready':{'api_key':'DO_NOT_EMIT_THIS_SECRET'},'broken':{'api_key':'bad\nsecret'}}}))
    if source:
        import shlex
        (home/'lanes/ext/HOST_ENV.sh').write_text('export GLM_CONFIG='+shlex.quote(str(selected))+'\n'+source_tail)
    (home/'.glm').mkdir();(home/'.glm/config.json').write_text(json.dumps({'accounts':{'wrong-default':{'api_key':'default-secret'}}}))
    if remove_default: (home/'.glm/config.json').unlink()
    command=module.build_probe('h','h-route',['ready','broken','wrong-default','absent'],(ext/'glm_keys.py').read_bytes())
    r=subprocess.run(['sh','-c',command],env=dict(os.environ,HOME=str(home)),capture_output=True,text=True,timeout=10)
    assert r.returncode==0 and r.stderr==''
    assert 'SECRET' not in r.stdout and 'default-secret' not in r.stdout
    return json.loads(r.stdout.split('=',1)[1]),r.stdout


def test_probe_uses_actual_host_env_config_only_and_no_secret(ext,tmp_path):
    doc,_=probe_fixture(ext,tmp_path)
    assert doc['status']=='known'
    assert doc['accounts']=={'ready':True,'broken':False,'wrong-default':False,'absent':False}

@pytest.mark.parametrize('source,raw',[(False,None),(True,'no json'),(True,'[]'),(True,'{}')])
def test_failed_config_scope_or_invalid_source_is_unknown(ext,tmp_path,source,raw):
    doc,_=probe_fixture(ext,tmp_path,source=source,raw=raw,remove_default=not source)
    assert doc['status']=='unknown' and doc['accounts']=={}

@pytest.mark.parametrize('mutation',['symlink','mode','parent_mode','oversize','changed'])
def test_observation_reader_rejects_untrusted_or_changed_file(ext,tmp_path,monkeypatch,mutation):
    module=load('glm_host_account_source',ext)
    directory=tmp_path/'observations';directory.mkdir();p=directory/'h.json';p.write_text('{}')
    if mutation=='symlink':
        p.unlink();p.symlink_to(ext/'glm_keys.py')
    elif mutation=='mode':p.chmod(0o666)
    elif mutation=='parent_mode':directory.chmod(0o777)
    elif mutation=='oversize':p.write_bytes(b'x'*100)
    else:
        read=os.read
        def changed(fd,n):
            b=read(fd,n);p.write_text('replacement');return b
        monkeypatch.setattr(os,'read',changed)
    with pytest.raises((OSError,ValueError)):
        module.owned_bytes(p,maximum=20)


def test_backend_binds_actual_transport_and_refuses_duplicate_envelope(ext,tmp_path):
    doc,line=probe_fixture(ext,tmp_path)
    state=tmp_path/'state';state.mkdir()
    common='ts='+str(time.time())+'\nload1=0\nncpu=32\n'+line
    for alias,text,expect in [('h-route',common,True),('other',common,False),('h-route',common+line,False)]:
        r=subprocess.run([sys.executable,str(ext/'host_pull_backend.py'),'write-state',str(state),'h','0',text,alias],capture_output=True,timeout=5)
        assert r.returncode==0,r.stderr
        actual=json.loads((state/'h.json').read_text())
        assert ('glm_local_account_readiness' in actual)==expect


def test_collector_reads_configs_only_for_existing_glm_lane_hosts(ext,tmp_path):
    registry=tmp_path/'hosts.json'
    registry.write_text(json.dumps({'eligible':{'roles':['lanes'],'allowed_modes':['glm'],'ssh_alias':'h','worktree_root':'/home'},'seat':{'roles':['seat'],'local':True,'allowed_modes':['glm']},'other':{'roles':['lanes'],'allowed_modes':['minimax'],'ssh_alias':'m'}}))
    r=subprocess.run([sys.executable,str(ext/'host_pull_backend.py'),'read-hosts',str(registry),'','1','--glm-readiness'],capture_output=True,text=True,timeout=5)
    assert r.returncode==0
    assert {s.split('|')[0]:s.split('|')[-1] for s in r.stdout.splitlines()}=={'eligible':'1','other':'0','seat':'0'}


def broker_fixture(ext,tmp_path,monkeypatch,ready):
    import yaml
    module=load('lease_broker',ext)
    policy=tmp_path/'accounts.yaml'
    policy.write_text(yaml.safe_dump({'providers':{'glm':{'enabled':True,'accounts':[{'name':'absent','per_account_cap':2},{'name':'ready','per_account_cap':2}]}}}))
    br=module.Broker(db_path=str(tmp_path/'db'),lock_path=str(tmp_path/'lock'),accounts_path=str(policy),now_fn=lambda:1000,check_pid=False,external_gates=False,this_host='controller',status_json=str(tmp_path/'status.json'),hosts_path=str(tmp_path/'hosts.json'))
    source=load('glm_host_account_source',ext)
    calls=[]
    def observe(rows,**kwargs):
        calls.append(kwargs)
        chosen=[r for r in rows if r['name'] in ready]
        if kwargs['preferred'] is not None:
            chosen=[r for r in chosen if r['name']==kwargs['preferred']]
        return chosen,'fixture'
    monkeypatch.setattr(source,'filter_observed_accounts',observe)
    return br,calls


def acquire(br,**kw):
    return br.acquire('original-root','glm',host='worker-host',model='glm-5.3-flash',pid=123,
        task_class=kw.pop('task_class','remote-glm'),**kw)


def test_broker_intersects_before_lease_and_preserves_root(ext,tmp_path,monkeypatch):
    br,calls=broker_fixture(ext,tmp_path,monkeypatch,{'ready'})
    r=acquire(br)
    assert r.ok and r.account=='ready' and r.orchestrator_id=='original-root'
    assert calls[0]['host']=='worker-host' and calls[0]['model']=='glm-5.3-flash'
    rows=br.snapshot()['leases'];assert len(rows)==1 and rows[0]['account']=='ready'


def test_incompatible_pair_creates_no_demand_or_lease_and_does_not_wait(ext,tmp_path,monkeypatch):
    br,calls=broker_fixture(ext,tmp_path,monkeypatch,set())
    monkeypatch.setattr(time,'sleep',lambda *_:pytest.fail('no host/account wait loop'))
    r=acquire(br,wait=3600)
    assert not r.ok and r.reason=='host_account_unavailable'
    conn=br._conn()
    try:
        assert conn.execute('select count(*) from leases').fetchone()[0]==0
        assert conn.execute('select count(*) from waiters').fetchone()[0]==0
    finally:conn.close()


def test_explicit_unavailable_account_cannot_fall_back(ext,tmp_path,monkeypatch):
    br,_=broker_fixture(ext,tmp_path,monkeypatch,{'ready'})
    r=acquire(br,account='absent')
    assert not r.ok and r.reason=='host_account_unavailable'


def test_other_glm_transport_keeps_its_existing_auth_contract(ext,tmp_path,monkeypatch):
    br,calls=broker_fixture(ext,tmp_path,monkeypatch,set())
    r=acquire(br,task_class='remote-glm-codex')
    assert r.ok and calls==[]


def test_real_full_capacity_remains_capacity_not_readiness(ext,tmp_path,monkeypatch):
    br,_=broker_fixture(ext,tmp_path,monkeypatch,{'ready'})
    assert acquire(br).ok and acquire(br).ok
    r=acquire(br)
    assert not r.ok and r.reason in ('accounts_at_cap','cap_full')


def test_changed_shell_syntax(ext):
    subprocess.run(['bash','-n',str(ext/'host_pull.sh')],check=True,capture_output=True)

@pytest.mark.parametrize('extra',[{'qualification_only_modes':['glm']},{'qualification_only_modes':'glm'}, {'allowed_modes':['glm','glm']},{'allowed_modes':['glm','invalid']}, {'qualification_only_modes':['glm','glm']}])
def test_held_or_invalid_mode_policy_never_reads_config(ext,tmp_path,extra):
    registry=tmp_path/'hosts.json'
    registry.write_text(json.dumps({'h':dict(roles=['lanes'],allowed_modes=['glm'],ssh_alias='h',**{k:v for k,v in extra.items() if k!='allowed_modes'}) | ({'allowed_modes':extra['allowed_modes']} if 'allowed_modes' in extra else {})}))
    r=subprocess.run([sys.executable,str(ext/'host_pull_backend.py'),'read-hosts',str(registry),'','1','--glm-readiness'],capture_output=True,text=True,timeout=5)
    assert r.returncode==0,r.stderr
    assert r.stdout.rstrip().endswith('|0')


def test_collector_does_not_retain_group_writable_observation(ext,tmp_path):
    state=tmp_path/'state';state.mkdir();p=state/'h.json';p.write_text('{}');p.chmod(0o666)
    r=subprocess.run([sys.executable,str(ext/'host_pull_backend.py'),'write-state',str(state),'h','1','','h-route'],capture_output=True,timeout=5)
    assert r.returncode==0,r.stderr
    assert p.stat().st_mode & 0o777 == 0o644
    source=load('glm_host_account_source',ext)
    assert json.loads(source.owned_bytes(p))['reachable'] is False


def test_collector_refuses_unsafe_parent_directory(ext,tmp_path):
    state=tmp_path/'state';state.mkdir();state.chmod(0o777)
    r=subprocess.run([sys.executable,str(ext/'host_pull_backend.py'),'write-state',str(state),'h','1','','h-route'],capture_output=True,timeout=5)
    assert r.returncode!=0 and not (state/'h.json').exists()


def test_probe_resolves_python_in_launch_venv(ext,tmp_path):
    module=load('glm_host_account_probe',ext)
    home=tmp_path/'home';(home/'lanes/ext').mkdir(parents=True);(home/'lanes/venv/bin').mkdir(parents=True)
    config=tmp_path/'selected.json';config.write_text(json.dumps({'accounts':{'ready':{'api_key':'fixture'}}}))
    (home/'lanes/ext/HOST_ENV.sh').write_text('export GLM_CONFIG='+str(config)+'\n')
    python=home/'lanes/venv/bin/python3';marker=tmp_path/'used-exact-venv'
    import shlex
    python.write_text('#!/bin/sh\ntouch '+shlex.quote(str(marker))+'\nexec '+shlex.quote(sys.executable)+' "$@"\n');python.chmod(0o700)
    command=module.build_probe('h','h-route',['ready'],(ext/'glm_keys.py').read_bytes())
    r=subprocess.run(['sh','-c',command],env=dict(os.environ,HOME=str(home)),capture_output=True,text=True,timeout=5)
    assert r.returncode==0 and marker.exists()
    assert json.loads(r.stdout.split('=',1)[1])['accounts']=={'ready':True}


def test_picker_intersects_exact_model_room_before_host_choice(ext,tmp_path,monkeypatch):
    pick=load('pick',ext)
    captured=[]
    registry={'unready':{'ssh_alias':'bad'},'ready':{'ssh_alias':'good'}}
    hp=types.SimpleNamespace(load_registry=lambda:registry,HOSTS_STATE_DIR=str(tmp_path/'states'))
    monkeypatch.setitem(sys.modules,'host_pick',hp)
    class Connection:
        def close(self):pass
    br=types.SimpleNamespace(_conn=lambda:Connection(),hosts_path='registry.json',
        grantable_accounts=lambda _: [{'name':'full','_eff_cap':3},{'name':'room','_eff_cap':3}],
        account_model_cap=lambda *args:2,
        _account_held=lambda *args:0,
        _account_model_held=lambda conn,pool,name,model: 2 if name=='full' else 0)
    monkeypatch.setitem(sys.modules,'lease_broker',types.SimpleNamespace(default_broker=lambda:br))
    source=load('glm_host_account_source',ext)
    def filter_accounts(rows,**kw):
        captured.append((rows,kw))
        return (rows if kw['host']=='ready' else []),'fixture'
    monkeypatch.setattr(source,'filter_observed_accounts',filter_accounts)
    def view(registry,state,mode,**kw):
        available=sorted(set(registry)-kw['excluded'])
        return {'host_choice':available[0] if available else None,'host_eligibility':{'hosts':[]}}
    monkeypatch.setitem(sys.modules,'placement_view',types.SimpleNamespace(_default_read_bytes=lambda _:b'',build_placement_view=view))
    monkeypatch.setattr(pick,'_HOST_POOL_MODES',{'glm':('glm',)})
    routes=pick._eligible_host_routes('auto',glm_model='glm-5.3-flash')
    assert routes['glm']==('ready','glm')
    assert all([r['name'] for r in rows]==['room'] for rows,_ in captured)
    assert all(kw['model']=='glm-5.3-flash' for _,kw in captured)


def test_picker_refuses_model_change_after_placement(ext,monkeypatch):
    pick=load('pick',ext)
    monkeypatch.setattr(pick,'load_pools',lambda:{})
    monkeypatch.setattr(pick,'_selection_model',lambda *args,**kw:('glm-5.3',''))
    seen=[]
    def routes(*args,**kw):
        seen.append(kw['glm_model']);return {'glm':('h','glm')}
    monkeypatch.setattr(pick,'_eligible_host_routes',routes)
    monkeypatch.setattr(pick,'_format_pick',lambda *args,**kw:'POOL=glm KEY=- MODEL=glm-5.3-flash REASON=fixture')
    assert pick.format_pick('domain_orchestration',host='auto').startswith('NONE reason=glm model changed')
    assert seen==['glm-5.3']


def test_complete_local_projection_to_broker_consumes_only_compatible_pair(ext,tmp_path,monkeypatch):
    doc,line=probe_fixture(ext,tmp_path)
    state=ext/'state/hosts';state.mkdir(parents=True)
    observed='ts='+str(time.time())+'\nload1=0\nncpu=32\n'+line
    subprocess.run([sys.executable,str(ext/'host_pull_backend.py'),'write-state',str(state),'h','0',observed,'h-route'],check=True,capture_output=True,timeout=5)
    br,_=broker_fixture(ext,tmp_path,monkeypatch,{'unused-mock'})
    Path(br.hosts_path).write_text(json.dumps({'h':{'ssh_alias':'h-route'}}))
    br.now_fn=time.time
    load('glm_host_account_source',ext) # real stable-file reader + actual paid predicate
    granted=br.acquire('original-root','glm',host='h',model='glm-5.3-flash',pid=123,task_class='remote-glm')
    assert granted.ok and granted.account=='ready'
    denied=br.acquire('original-root','glm',host='h',account='absent',model='glm-5.3-flash',pid=123,task_class='remote-glm')
    assert not denied.ok and denied.reason=='host_account_unavailable'
    assert len(br.snapshot()['leases'])==1


def test_paid_predicate_contract_suite(ext):
    (ext/'tests').mkdir()
    script=ext/'tests/test_glm_host_account_readiness.py'
    shutil.copyfile(Path(__file__).parent/'fixtures/glm_host_account_pairing/predicate_contract.py',script)
    r=subprocess.run([sys.executable,str(script)],cwd=ext,capture_output=True,text=True,timeout=10)
    assert r.returncode==0,r.stdout+r.stderr
    assert 'Ran 33 tests' in r.stderr


def test_old_collector_retains_original_four_field_contract(ext,tmp_path):
    registry=tmp_path/'hosts.json'
    registry.write_text(json.dumps({'h':{'roles':['lanes'],'allowed_modes':['glm'],'ssh_alias':'h','worktree_root':'/home'}}))
    r=subprocess.run([sys.executable,str(ext/'host_pull_backend.py'),'read-hosts',str(registry),'','1'],capture_output=True,text=True,timeout=5)
    assert r.returncode==0 and r.stdout=='h|0|h|/home\n'


@pytest.mark.parametrize('source,tail,expected',[(True,'return 1\n','ready'),(False,'','wrong-default')])
def test_readiness_matches_launcher_when_host_env_returns_nonzero(ext,tmp_path,source,tail,expected):
    doc,_=probe_fixture(ext,tmp_path,source=source,source_tail=tail)
    import shlex
    command='export PATH=$HOME/lanes/venv/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH; source ~/lanes/ext/HOST_ENV.sh 2>/dev/null; '+shlex.quote(sys.executable)+' '+shlex.quote(str(ext/'glm_keys.py'))+' account-ready '+shlex.quote(expected)
    actual=subprocess.run(['/bin/bash','-c',command],env=dict(os.environ,HOME=str(tmp_path/'home')),capture_output=True,text=True,timeout=10)
    assert actual.returncode==0 and actual.stdout=='1\n'
    assert doc['status']=='known' and doc['accounts'][expected] is True


@pytest.mark.parametrize('ready,expected',[(set(),False),({'ready'},True)])
def test_review_f1_public_acquire_normalizes_alias_before_pairing(ext,tmp_path,monkeypatch,ready,expected):
    import yaml
    br,calls=broker_fixture(ext,tmp_path,monkeypatch,ready)
    policy=Path(br.accounts_path)
    doc=yaml.safe_load(policy.read_text());doc['providers']['glm']['pool_aliases']=['glm-frontier']
    policy.write_text(yaml.safe_dump(doc))
    result=br.acquire('original-root','glm-frontier',host='worker-host',model='glm-5.3',
                      pid=123,task_class='remote-glm',wait=0)
    assert result.ok is expected
    assert len(calls)==1 and calls[0]['host']=='worker-host'
    conn=br._conn()
    try:
        rows=conn.execute('select * from leases').fetchall()
        assert len(rows)==int(expected)
        assert conn.execute('select count(*) from waiters').fetchone()[0]==0
        if expected:
            assert rows[0]['pool']=='glm' and rows[0]['account']=='ready'
            assert rows[0]['orchestrator_id']=='original-root'
        else:assert result.reason=='host_account_unavailable'
    finally:conn.close()
