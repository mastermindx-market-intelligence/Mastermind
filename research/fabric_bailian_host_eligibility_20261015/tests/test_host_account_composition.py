"""Synthetic configuration and SQLite only; never uses a live host or account."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

import pytest

CANDIDATE=Path(os.environ.get('BAILIAN_READINESS_SOURCE',Path(__file__).resolve().parents[1]/'candidate'))
EXT=Path('/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext')

@pytest.fixture
def stage(tmp_path,monkeypatch):
    d=tmp_path/'code';d.mkdir(mode=0o700)
    for f in CANDIDATE.glob('*.py'): shutil.copy2(f,d/f.name)
    for n in ['glm_keys.py','bailian_keys.py','host_pick.py']:
        if not (d/n).exists():shutil.copy2(EXT/n,d/n)
    monkeypatch.syspath_prepend(str(EXT));monkeypatch.syspath_prepend(str(d))
    for n in ['glm_host_account_readiness','glm_host_account_source','glm_host_account_probe','lease_broker','pick']:
        monkeypatch.delitem(sys.modules,n,raising=False)
    return d

def module(stage,name):
    spec=importlib.util.spec_from_file_location(name,stage/(name+'.py'))
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def envelope(stage,host='h1',flags=None):
    return {'schema':'mastermind.bailian_local_account_readiness.v1','host':host,'transport_alias':host+'-ssh','mode':'qwen','config_scope':'launcher_bailian_config.v1','validator_sha256':hashlib.sha256((stage/'bailian_keys.py').read_bytes()).hexdigest(),'observed_at':1000,'status':'known','cooldown_checked':True,'accounts':flags if flags is not None else {'Kris':False,'Ryan':True}}

def setup_state(stage,hosts=None):
    hosts=hosts or ['h1']
    registry={h:{'ssh_alias':h+'-ssh','roles':['lanes'],'allowed_modes':['qwen']} for h in hosts}
    (stage/'hosts.json').write_text(json.dumps(registry))
    directory=stage/'state/hosts';directory.mkdir(parents=True,mode=0o700)
    for h in hosts:
        (directory/(h+'.json')).write_text(json.dumps({'host':h,'reachable':True,'ts':1000,'bailian_local_account_readiness':envelope(stage,h)}))
    return registry

def run_program(stage,tmp_path,config):
    probe=module(stage,'glm_host_account_probe')
    command=probe.build_probe('h1','h1-ssh',['Kris','Ryan'],(stage/'bailian_keys.py').read_bytes(),mode='qwen')
    inner=shlex.split(command)[-1];args=shlex.split(inner);i=args.index('python3')
    home=tmp_path/'synthetic-home';home.mkdir()
    if config is not None:
        (home/'.bailian').mkdir();(home/'.bailian/config.json').write_text(config)
    r=subprocess.run([sys.executable,'-c',args[i+2],args[i+3]],env={'HOME':str(home),'PATH':os.environ['PATH']},capture_output=True,text=True,timeout=5)
    assert r.returncode==0,r.stderr
    assert 'SYNTHETIC_CREDENTIAL' not in r.stdout+r.stderr
    assert 'unrelated-alias' not in r.stdout+r.stderr
    assert not (home/'lanes').exists()  # metadata observation creates no slots
    return json.loads(r.stdout.split('=',1)[1])

def test_probe_uses_actual_validator_and_emits_only_requested_booleans(stage,tmp_path):
    config={'token-plan':{'api_keys':[{'name':'Ryan','api_key':'SYNTHETIC_CREDENTIAL'},{'name':'unrelated-alias','api_key':'SYNTHETIC_CREDENTIAL'}]}}
    got=run_program(stage,tmp_path,json.dumps(config))
    assert got['status']=='known' and got['accounts']=={'Kris':False,'Ryan':True}
    assert got['validator_sha256']==hashlib.sha256((stage/'bailian_keys.py').read_bytes()).hexdigest()

@pytest.mark.parametrize('config',[None,'{bad','{}','{"token-plan":null}'])
def test_unreadable_or_wrong_config_is_unknown_not_absent(stage,tmp_path,config):
    got=run_program(stage,tmp_path,config)
    assert got['status']=='unknown' and got['accounts']=={}

@pytest.mark.parametrize('mutation',['none','duplicate','foreign_host','foreign_alias','wrong_digest'])
def test_collector_accepts_only_exact_single_envelope(stage,tmp_path,mutation):
    directory=tmp_path/'out';directory.mkdir(mode=0o700)
    obs=envelope(stage)
    if mutation=='foreign_host':obs['host']='other'
    if mutation=='foreign_alias':obs['transport_alias']='other'
    if mutation=='wrong_digest':obs['validator_sha256']='0'*64
    line='bailian_local_account_readiness='+json.dumps(obs)
    output='load1=0\nncpu=8\nts=1000\n'+line
    if mutation=='duplicate':output+='\n'+line
    r=subprocess.run([sys.executable,str(stage/'host_pull_backend.py'),'write-state',str(directory),'h1','0',output,'h1-ssh'],capture_output=True,text=True,timeout=5,env={**os.environ,'PYTHONPATH':str(stage)+os.pathsep+str(EXT)})
    assert r.returncode==0,r.stderr
    got=json.loads((directory/'h1.json').read_text())
    assert ('bailian_local_account_readiness' in got)==(mutation=='none')

@pytest.mark.parametrize('modes,held,expected',[(['qwen'],[],True),(['qwen'],['qwen'],False),([],[],False),(None,[],True),(['qwen'],['glm'],True)])
def test_existing_collector_flag_includes_only_admitted_providers(stage,tmp_path,modes,held,expected):
    path=tmp_path/'hosts.json';path.write_text(json.dumps({'h1':{'roles':['lanes'],'allowed_modes':modes,'qualification_only_modes':held,'ssh_alias':'h1-ssh'}}))
    r=subprocess.run([sys.executable,str(stage/'host_pull_backend.py'),'read-hosts',str(path),'','1','--glm-readiness'],capture_output=True,text=True,timeout=5,env={**os.environ,'PYTHONPATH':str(stage)+os.pathsep+str(EXT)})
    assert r.returncode==0,r.stderr
    assert r.stdout.strip().endswith('|'+str(int(expected)))

@pytest.fixture
def broker(stage,tmp_path,monkeypatch):
    setup_state(stage)
    accounts=tmp_path/'accounts.yaml';accounts.write_text('''schema: mastermind.provider_accounts.v1
providers:
  bailian:
    enabled: true
    pool_aliases: [qwen]
    accounts:
      - {name: Kris, per_account_cap: 7}
      - {name: Ryan, per_account_cap: 7}
''')
    m=module(stage,'lease_broker')
    br=m.Broker(db_path=str(tmp_path/'db.sqlite'),lock_path=str(tmp_path/'db.lock'),accounts_path=str(accounts),hosts_path=str(stage/'hosts.json'),now_fn=lambda:1000,external_gates=False,check_pid=False,status_json=str(tmp_path/'status.json'),grok_marker=str(tmp_path/'no-marker'),this_host='controller')
    return m,br

def acquire(br,**kwargs):
    return br.acquire(orchestrator_id='fixture-root',pool='qwen',task_class='remote-qwen',host='h1',model='qwen3.8-max',pid=os.getpid(),wait=0,**kwargs)

def test_broker_intersects_before_granting(broker):
    _,br=broker;r=acquire(br)
    assert r.ok and r.account=='Ryan'

@pytest.mark.parametrize('bad',['missing','stale','unknown','digest','preferred_missing'])
def test_bad_host_pairing_creates_neither_lease_nor_waiter(stage,broker,bad):
    _,br=broker;p=stage/'state/hosts/h1.json';doc=json.loads(p.read_text())
    if bad=='missing':doc.pop('bailian_local_account_readiness')
    elif bad=='stale':doc['ts']=1
    elif bad=='unknown':doc['bailian_local_account_readiness']['status']='unknown'
    elif bad=='digest':doc['bailian_local_account_readiness']['validator_sha256']='0'*64
    p.write_text(json.dumps(doc));r=acquire(br,**({'account':'Kris'} if bad=='preferred_missing' else {}))
    assert not r.ok and r.reason=='host_account_unavailable'
    with br._conn() as c:
        assert c.execute('select count(*) from leases').fetchone()[0]==0
        assert c.execute('select count(*) from waiters').fetchone()[0]==0

def test_nonremote_account_selection_unchanged(broker):
    _,br=broker
    r=br.acquire(orchestrator_id='fixture-root',pool='qwen',task_class='census',host='h1',account='Kris',pid=os.getpid(),wait=0)
    assert r.ok and r.account=='Kris'

@pytest.mark.parametrize('dishonest_view',[False,True])
def test_router_excludes_host_without_ready_account_before_selection(stage,broker,monkeypatch,dishonest_view):
    m,br=broker;p=stage/'hosts.json';registry=json.loads(p.read_text());registry['h0']={'ssh_alias':'h0-ssh','roles':['lanes'],'allowed_modes':['qwen']};p.write_text(json.dumps(registry))
    import host_pick,placement_view
    monkeypatch.setattr(host_pick,'load_registry',lambda:registry)
    monkeypatch.setattr(host_pick,'HOSTS_STATE_DIR',str(stage/'state/hosts'))
    monkeypatch.setattr(m,'default_broker',lambda:br)
    picked=[]
    def view(registry,state_dir,mode,**kw):
        picked.append(kw['excluded']);return {'host_choice':'h0' if dishonest_view else next((h for h in sorted(registry) if h not in kw['excluded']),None)}
    monkeypatch.setattr(placement_view,'build_placement_view',view)
    route=module(stage,'pick');monkeypatch.setattr(route,'_HOST_POOL_MODES',{'bailian':['qwen']})
    import datetime
    class Clock:
        @staticmethod
        def now(tz):return datetime.datetime.fromtimestamp(1000,tz)
    monkeypatch.setattr(route,'datetime',Clock)
    result=route._eligible_host_routes('auto',qwen_model='qwen3.8-max')
    assert 'h0' in picked[0] and 'h1' not in picked[0]
    assert result==({} if dishonest_view else {'bailian':('h1','qwen')})

@pytest.mark.parametrize('case',['missing','stale','future','foreign_host','foreign_alias','wrong_model','wrong_scope','wrong_digest','unknown','false_flag','unverified','preference'])
def test_pure_qwen_predicate_negative_fences(stage,case):
    m=module(stage,'glm_host_account_readiness');doc={'host':'h1','reachable':True,'ts':1000,'bailian_local_account_readiness':envelope(stage)}
    kw=dict(host='h1',transport_alias='h1-ssh',mode='qwen',model='qwen3.8-max',candidate_model='qwen3.8-max',validator_sha256=envelope(stage)['validator_sha256'],now=1000,source_verified=True)
    obs=doc['bailian_local_account_readiness']
    if case=='missing':doc.pop('bailian_local_account_readiness')
    if case=='stale':obs['observed_at']=1
    if case=='future':obs['observed_at']=1002
    if case=='foreign_host':obs['host']='other'
    if case=='foreign_alias':obs['transport_alias']='other'
    if case=='wrong_model':kw['candidate_model']='qwen3.8-flash'
    if case=='wrong_scope':obs['config_scope']='launcher_glm_config.v1'
    if case=='wrong_digest':obs['validator_sha256']='0'*64
    if case=='unknown':obs['status']='unknown'
    if case=='false_flag':obs['accounts']={'Kris':False,'Ryan':None}
    if case=='unverified':kw['source_verified']=False
    if case=='preference':kw['preferred']='Kris'
    rows=[{'name':'Kris'},{'name':'Ryan'}];got,why=m.filter_bailian_host_accounts(rows,doc,**kw)
    assert got==[] and why!='ok'

def test_qwen_ready_intersection_retains_original_rows_and_order(stage):
    m=module(stage,'glm_host_account_readiness');obs=envelope(stage,flags={'Kris':True,'Ryan':True,'unconfigured':False});doc={'host':'h1','reachable':True,'ts':1000,'bailian_local_account_readiness':obs}
    rows=[{'name':'Ryan'},{'name':'Kris'},{'name':'unconfigured'}]
    out,why=m.filter_bailian_host_accounts(rows,doc,host='h1',transport_alias='h1-ssh',mode='qwen',model='qwen3.8-flash',candidate_model='qwen3.8-flash',validator_sha256=obs['validator_sha256'],now=1000,source_verified=True)
    assert why=='ok' and out==rows[:2] and out[0] is rows[0]

@pytest.mark.parametrize('allowed,held,expected_modes',[(['qwen'],[],['qwen']),(['glm'],[],['glm']),(['glm','qwen'],['glm'],['qwen']),(['qwen'],['qwen'],[])])
def test_existing_live_generator_never_enables_held_provider(stage,tmp_path,monkeypatch,allowed,held,expected_modes):
    policy=tmp_path/'policy.yaml';policy.write_text('providers:\n  glm:\n    accounts: [{name: fixture}]\n  bailian:\n    accounts: [{name: Ryan}]\n')
    reg=stage/'hosts.json';reg.write_text(json.dumps({'h1':{'ssh_alias':'h1-ssh','roles':['lanes'],'allowed_modes':allowed,'qualification_only_modes':held}}))
    m=module(stage,'glm_host_account_probe');seen=[]
    monkeypatch.delenv('HOST_PULL_HOSTS_JSON',raising=False)
    monkeypatch.setattr(m,'build_probe',lambda host,alias,names,raw,mode='glm':seen.append(mode) or ':')
    m.main(['h1','h1-ssh',str(policy)])
    assert seen==expected_modes

@pytest.mark.parametrize('change',[
    {'qualification_only_modes':['qwen']}, {'allowed_modes':[]},
    {'allowed_modes':None}, {'roles':['candidate']}, {'roles':'lanes'},
    {'allowed_modes':['qwen','qwen']}, {'qualification_only_modes':'qwen'},
])
def test_current_admission_revocation_overrides_fresh_positive(stage,broker,change):
    _,br=broker
    path=stage/'hosts.json';registry=json.loads(path.read_text())
    registry['h1'].update(change);path.write_text(json.dumps(registry))
    result=acquire(br)
    assert not result.ok and result.reason=='host_account_unavailable'
    with br._conn() as c:
        assert c.execute('select count(*) from leases').fetchone()[0]==0
        assert c.execute('select count(*) from waiters').fetchone()[0]==0

@pytest.mark.parametrize('mode,pool,observed,emitted',[
    ('qwen','bailian','qwen3.8-max','qwen3.8-flash'),
    ('qwen','bailian','qwen3.8-max',None),
    ('qwen','bailian','qwen3.8-max','qwen3.8-max'),
    ('glm','glm','glm-5.3','glm-5.3-flash'),
])
def test_final_model_matches_account_observation(stage,monkeypatch,mode,pool,observed,emitted):
    route=module(stage,'pick')
    monkeypatch.setattr(route,'load_pools',lambda:{})
    monkeypatch.setattr(route,'_selection_model',lambda *a,**kw:(observed,False))
    monkeypatch.setattr(route,'_eligible_host_routes',lambda *a,**kw:{pool:('h1',mode)})
    line='POOL='+pool+(' MODEL='+emitted if emitted else '')
    monkeypatch.setattr(route,'_format_pick',lambda *a,**kw:line)
    got=route._format_pick_host('review',host='auto')
    assert got.startswith('POOL=')==(emitted==observed)

def test_existing_collector_shell_to_broker_metadata_composition(stage,tmp_path,monkeypatch):
    import yaml
    shutil.copytree(Path(yaml.__file__).parent,stage/'yaml')
    # Run the incumbent collector through a synthetic transport. The transport
    # executes only its generated readiness suffix, never the hardware probe.
    for name in ['host_pull.sh','host_pull_probe.template']:
        shutil.copy2(EXT/name,stage/name)
    setup_state(stage)
    policy=tmp_path/'accounts.yaml';policy.write_text('providers:\n  bailian:\n    accounts: [{name: Kris}, {name: Ryan}]\n')
    home=tmp_path/'home';(home/'.bailian').mkdir(parents=True)
    (home/'.bailian/config.json').write_text(json.dumps({'token-plan':{'api_keys':[{'name':'Ryan','api_key':'SYNTHETIC_CREDENTIAL'}]}}))
    bindir=tmp_path/'bin';bindir.mkdir()
    python_wrapper=bindir/'python3';python_wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' "$@"\n');python_wrapper.chmod(0o755)
    shim=bindir/'ssh';shim.write_text('''#!/usr/bin/env python3
import os,sys,time,subprocess
command=sys.argv[-1]
marker='PATH="${GLM_LAUNCH_BASE_PATH:-$PATH}" /bin/bash -c '
assert marker in command
suffix=command[command.index(marker):]
r=subprocess.run(['/bin/sh','-c',suffix],env=os.environ,capture_output=True,text=True,timeout=5)
assert r.returncode==0,r.stderr
assert 'SYNTHETIC_CREDENTIAL' not in r.stdout+r.stderr
print('ts='+str(time.time())+'\\nload1=0\\nncpu=8\\nactive_lanes=0')
print(r.stdout,end='')
''');shim.chmod(0o755)
    env={**os.environ,'HOME':str(home),'PATH':str(bindir)+os.pathsep+os.environ['PATH'],'PYTHONPATH':str(stage)+os.pathsep+str(EXT),'HOST_PULL_HOSTS_JSON':str(stage/'hosts.json'),'HOST_PULL_STATE_DIR':str(stage/'state/hosts'),'POOL_ACCOUNTS_YAML':str(policy),'HOST_PULL_PIDFILE':str(tmp_path/'pid')}
    r=subprocess.run(['/bin/bash',str(stage/'host_pull.sh'),'--once','--host','h1'],env=env,capture_output=True,text=True,timeout=10)
    assert r.returncode==0,r.stderr
    obs=json.loads((stage/'state/hosts/h1.json').read_text())['bailian_local_account_readiness']
    assert obs['status']=='known' and obs['accounts']=={'Kris':False,'Ryan':True}
    source=module(stage,'glm_host_account_source')
    rows,reason=source.filter_observed_accounts([{'name':'Kris'},{'name':'Ryan'}],host='h1',model='qwen3.8-flash',now=time.time(),mode='qwen')
    assert reason=='ok' and rows==[{'name':'Ryan'}]
