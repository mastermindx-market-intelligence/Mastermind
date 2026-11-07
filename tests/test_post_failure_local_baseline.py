"""Inert replicas of the real incumbent local preflight; never reader transport.

Native metadata, log and SQLite rows are synthetic private test fixtures. The
actual generic lineage implementation is exercised without replacing its verdict.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

import pytest

NATIVE=Path(__file__).resolve().parents[1]/'ops/native_fabric/quota_continuity'
sys.path[:0]=[str(NATIVE/'candidate'),str(NATIVE/'source')]
import post_failure_observation_delivery as owner


def encode(v):return owner.reader.canonical(v)


@pytest.fixture
def baseline(monkeypatch):
    with tempfile.TemporaryDirectory(prefix='postfailure-baseline-',dir=NATIVE/'tests') as tmp:
        home=Path(tmp).resolve();here=home/'ext';state=here/'state/remote_sub';state.mkdir(parents=True)
        sessions=home/'.codex/sessions';sessions.mkdir(parents=True)
        run='macro-native-publisher-main-workflows-20261105-01a1aaa4';scope=owner.model.scope_for(run)
        for ident,parent in [(scope['parent'],scope['root']),(scope['root'],None)]:
            (sessions/('test-'+ident+'.jsonl')).write_bytes(encode({'type':'session_meta','payload':{'id':ident,'parent_thread_id':parent}})+b'\n')
        monkeypatch.setattr(owner.Path,'home',classmethod(lambda cls:home))
        monkeypatch.setenv('CODEX_THREAD_ID',scope['parent']);monkeypatch.setenv('POOL_ORCHESTRATOR_ID',scope['root'])
        witness=json.loads((NATIVE.parents[2]/'tests/fixtures/post-failure-routing-observation.json').read_bytes())
        files=witness['request']['artifact']['support_files']
        binding={'schema':'mastermind.fabric_launch_binding.v2','run_id':run,'root':scope['root'],'parent':scope['parent'],
                 'host':scope['host'],'mode':'qwen','requested_model':'qwen3.8-plus','pool':'bailian','acquisition_pool':'bailian',
                 'lease_id':scope['lease_id'],'account':scope['account'],'packet_sha256':'a'*64,'support_digest':owner.model.SUPPORT,
                 'acquire_response_sha256':hashlib.sha256(('LEASE='+scope['lease_id']+' ACCOUNT='+scope['account']+'\n').encode()).hexdigest(),
                 'source':'controller_original_acquire_return','phase':'PRE_LAUNCH'}
        events=['RUN_RESERVED explicit=1','LEASE_OK pool=bailian','SUPPORT_VERSION_READY digest='+owner.model.SUPPORT+' policy='+'b'*64,
                'LAUNCH_BINDING '+encode(binding).decode(),'LAUNCH mode=qwen','LAUNCH_ATTEMPT attempt=1','REMOTE_DONE rc=76',
                'REMOTE_EFFECT_UNKNOWN worker_rc=76 same_run_reconciliation_required=1','REMOTE_ARTIFACTS_PRESERVED effect_unknown=1',
                'DONE rc=76 signal=effect_unknown reason=remote_cleanup_unproven','LEASE_PRESERVED effect_unknown=1 lease='+scope['lease_id']]
        def log_bytes():return ''.join('2026-11-05T13:18Z [remote_sub id='+run+' host=ubuntu3] '+x+'\n' for x in events).encode()
        logpath=state/(run+'.log');logpath.write_bytes(log_bytes())
        recorded={'schema':'mastermind.fabric_request_artifact.v1','run_id':run,'root_id':scope['root'],'parent_run_id':scope['parent'],
                  'packet':run+'.request.packet','packet_sha256':'c'*64}
        raw=encode(recorded);(state/(run+'.request.json')).write_bytes(raw)
        (state/(run+'.request-launch.json')).write_bytes(encode({'schema':'mastermind.fabric_request_launch.v1','run_id':run,'root_id':scope['root'],
             'parent_run_id':scope['parent'],'state':'LAUNCH_ATTEMPT_RESERVED','packet_sha256':'c'*64,'request_sha256':hashlib.sha256(raw).hexdigest()}))
        (state/(run+'.support.json')).write_bytes(encode(files))
        (here/'hosts.json').write_bytes(encode({'ubuntu3':{'ssh_alias':'inert-same-host','allowed_modes':['qwen']}}))
        for name in ('run_observation.py','post_failure_observation.py','artifact_reader.py'):
            source=NATIVE/'candidate'/name
            if not source.exists():source=NATIVE/'source'/name
            (here/name).write_bytes(source.read_bytes())
        for path in home.rglob('*'):
            path.chmod(0o700 if path.is_dir() else 0o600)
        monkeypatch.setattr(owner.delivery,'HERE',here);monkeypatch.setattr(owner.fabric_task,'HERE',here)
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.execute('create table leases(id,orchestrator_id,host,account,model,pool)')
        db.execute('insert into leases values(?,?,?,?,?,?)',(scope['lease_id'],scope['root'],scope['host'],scope['account'],binding['requested_model'],binding['pool']))
        row=db.execute('select * from leases').fetchone();assert isinstance(row,sqlite3.Row)
        monkeypatch.setattr(owner.delivery,'retained_lease',lambda *a,**k:row)
        yield {'run':run,'scope':scope,'logpath':logpath,'log_bytes':log_bytes,'events':events,'binding':binding,'row':row,'db':db,'here':here}
        db.close()


def test_real_generic_guard_remains_unverified_for_full_terminal_and_prefix(baseline):
    b=baseline;full=b['logpath'].read_bytes()
    assert owner.fabric_task._active_lineage_projection(b['run'],full)['controller_lineage']['state']=='UNVERIFIED'
    prefix=full[:full.index(b'REMOTE_DONE')].rsplit(b'\n',1)[0]+b'\n'
    assert owner.fabric_task._active_lineage_projection(b['run'],prefix)['controller_lineage']['state']=='UNVERIFIED'


def test_full_local_snapshot_qualifies_real_row_and_ancestry_without_transport(baseline,monkeypatch):
    def no_transport(*a,**k):raise AssertionError('No transport in local preflight')
    monkeypatch.setattr(owner.delivery,'transport',no_transport)
    request,proof=owner.snapshot(baseline['run'],invocation_id='d'*32)
    assert request['terminal_log_sha256']==hashlib.sha256(baseline['logpath'].read_bytes()).hexdigest()
    assert len(proof['native_ancestry'])==2
    assert proof['ssh_alias']=='inert-same-host'
    assert owner.fabric_task._active_lineage_projection(baseline['run'],baseline['logpath'].read_bytes())['controller_lineage']['state']=='UNVERIFIED'


@pytest.mark.parametrize('subject',[0,1])
def test_actual_original_full_metadata_preflight_keeps_generic_guard_closed(baseline,monkeypatch,subject):
    import base64,zlib
    path=NATIVE.parents[2]/'tests/fixtures/postfailure-local-terminal76-metadata.json'
    raw=path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='c0d2c259844fdf039326a5a7b5a1ba0111344ea1749083631f5c75ff8cb54665'
    item=json.loads(raw)['subjects'][subject];run=item['run_id'];b=item['original_launch_binding'];here=baseline['here'];state=here/'state/remote_sub'
    copies={}
    for key,row in item['files'].items():
        value=zlib.decompress(base64.b64decode(row['zlib_base64'],validate=True))
        assert len(value)==row['bytes'] and hashlib.sha256(value).hexdigest()==row['sha256']
        copies[key]=value
    for key,suffix in [('log','.log'),('request','.request.json'),('launch','.request-launch.json'),('support','.support.json')]:
        target=state/(run+suffix);target.write_bytes(copies[key]);target.chmod(0o600)
    (here/'hosts.json').write_bytes(encode({'ubuntu3':{'ssh_alias':'mmx-ubuntu3','allowed_modes':['glm']}}))
    db=baseline['db'];db.execute('delete from leases');db.execute('insert into leases values(?,?,?,?,?,?)',
        (b['lease_id'],b['root'],b['host'],b['account'],b['requested_model'],b['pool']))
    row=db.execute('select * from leases').fetchone();assert isinstance(row,sqlite3.Row)
    monkeypatch.setattr(owner.delivery,'retained_lease',lambda *a,**k:row)
    if subject==0:
        witness=here/'routing-prior.json';witness.write_bytes((NATIVE.parents[2]/'tests/fixtures/post-failure-routing-observation.json').read_bytes());witness.chmod(0o600)
        monkeypatch.setitem(owner.PRIOR,run,witness)
    full=copies['log']
    assert owner.fabric_task._active_lineage_projection(run,full)['controller_lineage']['state']=='UNVERIFIED'
    correlation,binding,_,_=owner.historical_launch_correlation(run,full,state/(run+'.log'))
    assert binding==b and correlation['state']=='RECORDED_HISTORICAL_PRE_LAUNCH' and correlation['is_authentication'] is False
    request,proof=owner.snapshot(run,invocation_id='d'*32)
    assert request['terminal_log_sha256']==item['files']['log']['sha256']
    assert len(proof['native_ancestry'])==2
    assert owner.fabric_task._active_lineage_projection(run,full)['controller_lineage']['state']=='UNVERIFIED'


@pytest.mark.parametrize('field',['id','orchestrator_id','host','account','model','pool'])
def test_real_sqlite_row_mismatch_refuses_without_transport(baseline,monkeypatch,field):
    db=baseline['db'];db.execute('update leases set '+field+'=?',('mismatch',));row=db.execute('select * from leases').fetchone()
    monkeypatch.setattr(owner.delivery,'retained_lease',lambda *a,**k:row)
    with pytest.raises(ValueError,match='retained_lease_binding_mismatch'):
        owner.snapshot(baseline['run'],invocation_id='d'*32)


@pytest.mark.parametrize('fault',['acquire','pool','root','lease','account','schema','phase','extra','duplicate','attempt','order','rc','hold','refusal','reserve','supportorder','missingunknown','newline'])
def test_full_historical_correlation_rejects_drift(baseline,fault):
    b=baseline;events=b['events'];binding=dict(b['binding'])
    if fault in ('acquire','pool','root','lease','account','schema','phase','extra'):
        fields={'acquire':('acquire_response_sha256','0'*64),'pool':('acquisition_pool','glm'),'root':('root','wrong-root'),
                'lease':('lease_id','0'*12),'account':('account','wrong-account'),'schema':('schema','mastermind.fabric_launch_binding.v1'),
                'phase':('phase','AFTER_LAUNCH'),'extra':('unexpected',True)}
        key,value=fields[fault];binding[key]=value;events[3]='LAUNCH_BINDING '+encode(binding).decode()
    elif fault=='duplicate':events.insert(4,events[3])
    elif fault=='attempt':events[5]='LAUNCH_ATTEMPT attempt=2'
    elif fault=='order':events[6],events[7]=events[7],events[6]
    elif fault=='rc':events[6]='REMOTE_DONE rc=0'
    elif fault=='hold':events[-1]='LEASE_PRESERVED effect_unknown=1 lease='+'0'*12
    elif fault=='refusal':events.insert(4,'PROVIDER_REFUSED rc=77')
    elif fault=='reserve':events[0]='RUN_RESERVED explicit=0'
    elif fault=='supportorder':events[1],events[2]=events[2],events[1]
    elif fault=='missingunknown':events[7]='POLL_PENDING poll=1'
    raw=b['log_bytes']()
    if fault=='newline':raw=raw[:-1]
    b['logpath'].write_bytes(raw)
    with pytest.raises(ValueError):owner.historical_launch_correlation(b['run'],raw,b['logpath'])


def test_historical_log_must_remain_the_same_full_inode_and_bytes(baseline,monkeypatch):
    b=baseline;path=b['logpath'];raw=path.read_bytes();real=owner.delivery.local_file;calls=[]
    def changed(p,*a):
        value=real(p,*a)
        if Path(p)==path:
            calls.append(True)
            if len(calls)==2:return value+b'UNQUALIFIED_APPEND'
        return value
    monkeypatch.setattr(owner.delivery,'local_file',changed)
    with pytest.raises(ValueError):owner.historical_launch_correlation(b['run'],raw,path)


def test_same_bytes_replaced_log_inode_is_not_stable(baseline,monkeypatch):
    b=baseline;path=b['logpath'];raw=path.read_bytes();real=owner.delivery.local_file;calls=[]
    def replaced(p,*a):
        value=real(p,*a)
        if Path(p)==path:
            calls.append(True)
            if len(calls)==2:
                path.rename(path.with_suffix('.held'))
                path.write_bytes(raw);path.chmod(0o600)
        return value
    monkeypatch.setattr(owner.delivery,'local_file',replaced)
    with pytest.raises(ValueError):owner.historical_launch_correlation(b['run'],raw,path)
