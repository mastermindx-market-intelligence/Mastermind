"""Real temporary incumbent counts/Broker/ledger, no live admission or provider.

Explicit fixtures supply account capacity, clock, installation and process
availability. Production keeps its external gates and fixed namespace; these
tests disable host probes and PID GC only inside disposable test Broker data.
No API key, native source, private case, source grant or paid request is used.
"""
import copy
import hashlib
import importlib
import os
import json
from pathlib import Path
import sqlite3
import sys
import socket

import pytest

# Explicit source-qualification input only; never selects or reads an installed generation.
NATIVE=Path(os.environ.get('MMX_PROTECTED_MEMORY_TEST_STAGE',
    str(Path(__file__).resolve().parents[1]/'ops/native_fabric/provider_plans/memory118/native_owner'))).resolve()
sys.path[:0]=[str(NATIVE),str(Path(__file__).resolve().parents[1]/'ops/native_fabric/quota_continuity/candidate'),
              str(Path(__file__).resolve().parents[1]/'ops/native_fabric/quota_continuity/source')]
from fabric_operator_owner import OperatorOwner, DelegationRefused
from lease_broker import Broker
import pool_ledger
from protected_memory_economic import ProtectedMemoryEconomicOwner
assert Path(importlib.import_module('fabric_operator_owner').__file__).resolve()==NATIVE/'fabric_operator_owner.py'
assert Path(importlib.import_module('lease_broker').__file__).resolve()==NATIVE/'lease_broker.py'


@pytest.fixture
def economy(tmp_path,monkeypatch,request):
    fixture_lifecycle=request
    here=tmp_path/'ext';(here/'broker').mkdir(parents=True)
    policy=tmp_path/'orch/fabric/pools.yaml';policy.parent.mkdir(parents=True)
    policy.write_text(json.dumps({'pools':{'glm':{'models':{'executor':'glm-5.3-flash'}}}}))
    (here/'state/remote_sub').mkdir(parents=True)
    accounts=tmp_path/'accounts.json'
    accounts.write_text(json.dumps({'providers':{'glm':{'enabled':True,'concurrency_cap':8,
        'accounts':[{'name':'configured-fixture-account','per_account_cap':8}]}}}))
    hosts=tmp_path/'hosts.json';hosts.write_text('{}')
    status=tmp_path/'status.json';status.write_text('{}')
    clock=[1000.0]
    # Explicit inert current host/account observation premise only. All real
    # Broker count/quota/fairness/lease SQL remains exercised. Production calls
    # the incumbent strict reader with fixed original-owner state paths.
    import glm_host_account_source
    monkeypatch.setattr(glm_host_account_source,'filter_observed_accounts',
        lambda accounts,**_kw:(accounts,'fixture_current_host_account'))
    broker=Broker(db_path=str(here/'broker/leases.sqlite'),lock_path=str(here/'broker/leases.lock'),
        accounts_path=str(accounts),status_json=str(status),hosts_path=str(hosts),
        this_host=socket.gethostname().split()[0],now_fn=lambda:clock[0],external_gates=False,check_pid=False)
    owner=OperatorOwner(here=here,clock=lambda:clock[0])
    parent=broker.acquire('native-root','glm',account='configured-fixture-account',host=broker.this_host,
        pid=123,model='glm-5.3',task_class='remote-glm',ttl=180)
    assert parent.ok
    owner.authorize_root('native-root',3,2200.0)
    token=owner.issue(dict(root='native-root',run_id='native-parent',lease_id=parent.lease_id,
        pool='glm',model='glm-5.3',account='configured-fixture-account',host=broker.this_host,
        support_sha256='a'*64,packet_sha256='b'*64,task_class='domain_orchestration'),2)['token']
    ledger=tmp_path/'ledger.jsonl';ledger.touch(mode=0o600)
    monkeypatch.setattr(pool_ledger,'LEDGER_PATH',str(ledger))
    request=dict(schema='mastermind.fabric_protected_memory_pre_input.v1',root='native-root',parent='native-parent',
        run_id='native-child',task_class='extract',task_complexity='C1_ROUTINE_BOUNDED',
        pre_input_sha256='c'*64,profile_sha256='d'*64,model='glm-5.3-flash')
    selector={k:request[k] for k in ('root','parent','run_id','pre_input_sha256','profile_sha256')}
    route=dict(account='configured-fixture-account',model='glm-5.3-flash',host=broker.this_host)
    engine=ProtectedMemoryEconomicOwner(owner,broker)
    # Explicit kernel-root/helper identity premise. Public dictionaries or a
    # budget bearer alone cannot issue this nominal source invocation.
    from control_plane import executive_peer_identity as peers
    import protected_memory_economic as economic
    root_socket,other=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
    fixture_lifecycle.addfinalizer(lambda:(root_socket.close(),other.close()))
    previous=peers._observe_socket
    def observe(connection):
        if connection.fileno()==root_socket.fileno():
            return peers._KernelObservation(b'R'*32,0,os.getppid(),987,peers._descriptor_identity(root_socket))
        return previous(connection)
    monkeypatch.setattr(peers,'_observe_socket',observe)
    def authority(scope):
        current=os.geteuid;monkeypatch.setattr(os,'geteuid',lambda:501)
        try:return economic.root_helper_invocation(root_socket,scope)
        finally:monkeypatch.setattr(os,'geteuid',current)
    engine._fixture_root_authority=authority
    return owner,broker,engine,token,request,selector,route,clock,ledger


def authorize(economy):
    owner,broker,engine,token,request,selector,route,_,_=economy
    delegation={k:request[k] for k in ('task_class','task_complexity','model')};delegation['token']=token
    return engine.acquire(selector,route,controller_pid=os.getpid(),delegation=delegation,
        authority=engine._fixture_root_authority(request))


def bind(engine,selector):
    engine.bind_input(selector,dict(input_sha256='e'*64,input_bytes=9856,body_sha256='f'*64))
    return engine.consume(selector,dict(attempt_id='runtime-attempt',process_ref_sha256='1'*64))


@pytest.mark.parametrize('shape',['absent','dict','clone'])
def test_original_bearer_without_actual_root_invocation_cannot_reserve_count_or_child(economy,shape):
    owner,_,_,token,request,_,_,_,_=economy
    from protected_memory_economic import RootEconomicInvocation
    value=None if shape=='absent' else ({'root':True} if shape=='dict' else object.__new__(RootEconomicInvocation))
    before=owner.describe(token)['child_budget_remaining']
    with pytest.raises(DelegationRefused):owner.reserve_protected_memory(token,request,authority=value)
    assert owner.describe(token)['child_budget_remaining']==before
    with owner.transaction() as con:
        assert con.execute('SELECT count(*) FROM operator_child_authorizations').fetchone()[0]==0
        assert con.execute('SELECT count(*) FROM leases').fetchone()[0]==1


def test_actual_original_count_new_paid_lease_unique_consume_and_durable_accounting(economy):
    owner,broker,engine,token,request,selector,route,_,ledger=economy
    before=owner.describe(token)['child_budget_remaining']
    admitted=authorize(economy)
    assert admitted['phase']=='ADMITTED' and owner.describe(token)['child_budget_remaining']==before-1
    assert engine.current(selector)['phase']=='RESERVED'
    with owner.transaction() as con:
        leases=con.execute('SELECT id FROM leases').fetchall()
        assert len(leases)==2
        row=con.execute('SELECT request_json FROM operator_child_authorizations').fetchone()[0]
        assert 'packet' not in row and 'result' not in row
    delegation=dict(token=token,**{k:request[k] for k in ('task_class','task_complexity','model')})
    with pytest.raises(DelegationRefused):engine.acquire(selector,route,controller_pid=os.getpid(),delegation=delegation,
        authority=engine._fixture_root_authority(request))
    with pytest.raises(DelegationRefused):owner.reserve_protected_memory(token,request,authority=engine._fixture_root_authority(request))
    assert bind(engine,selector)['phase']=='CONSUMED'
    with pytest.raises(DelegationRefused):engine.consume(selector,dict(attempt_id='runtime-attempt',process_ref_sha256='1'*64))
    assert engine.heartbeat(selector)['phase']=='CONSUMED'
    terminal=dict(rc=0,result_sha256='2'*64,result_bytes=97)
    assert engine.settle(selector,terminal)['phase']=='SETTLED'
    records=[json.loads(x) for x in ledger.read_text().splitlines()]
    assert len(records)==1 and records[0]['root_id']=='native-root' and records[0]['parent_run_id']=='native-parent'
    assert records[0]['accepted_by'] is None and records[0]['tokens'] is None
    assert records[0]['credits'] is None and records[0]['job_class']=='extract'
    with owner.transaction() as con:
        assert owner.lease(con,admitted['lease_id'])['state']=='released'
        assert con.execute('SELECT count(*) FROM operator_child_authorizations').fetchone()[0]==1


@pytest.mark.parametrize('damage',['missing','foreign-root','foreign-parent','preinput','profile'])
def test_no_matching_current_original_row_cannot_acquire_any_child_lease(economy,damage):
    owner,broker,engine,token,request,selector,route,_,_=economy
    selected=dict(selector)
    if damage=='foreign-root':selected['root']='other-root'
    elif damage=='foreign-parent':selected['parent']='other-parent'
    elif damage=='preinput':selected['pre_input_sha256']='3'*64
    elif damage=='profile':selected['profile_sha256']='4'*64
    delegation=dict(token='0'*64 if damage=='missing' else token,
        **{k:request[k] for k in ('task_class','task_complexity','model')})
    with pytest.raises(DelegationRefused):engine.acquire(selected,route,controller_pid=os.getpid(),delegation=delegation,
        authority=engine._fixture_root_authority(request))
    with owner.transaction() as con:assert con.execute('SELECT count(*) FROM leases').fetchone()[0]==1


@pytest.mark.parametrize('damage',['class','complexity','future-input','token','exhausted','expired','economics'])
def test_grant_class_budget_and_deadline_refuse_before_source_or_new_row(economy,damage):
    owner,_,engine,token,request,_,_,clock,_=economy
    selected=copy.deepcopy(request)
    if damage=='class':selected['task_class']='scientific_study'
    elif damage=='complexity':selected['task_complexity']='C2'
    elif damage=='future-input':selected['input_sha256']='f'*64
    elif damage=='token':token='0'*64
    elif damage=='expired':clock[0]=2201
    elif damage=='economics':selected['model']='glm-5.3'
    else:
        with owner.transaction() as con:con.execute('UPDATE operator_root_grants SET child_limit=0')
    with pytest.raises(DelegationRefused):owner.reserve_protected_memory(token,selected,authority=engine._fixture_root_authority(selected))
    with owner.transaction() as con:assert con.execute('SELECT count(*) FROM operator_child_authorizations').fetchone()[0]==0


@pytest.mark.parametrize('damage',['parent-revoked','child-expired','wrong-input','duplicate-bind'])
def test_current_grant_and_exact_one_input_fence_provider_consumption(economy,damage):
    owner,_,engine,_,_,selector,_,clock,_=economy
    admitted=authorize(economy)
    engine.bind_input(selector,dict(input_sha256='e'*64,input_bytes=9856,body_sha256='f'*64))
    if damage=='parent-revoked':
        with owner.transaction() as con:con.execute("UPDATE leases SET state='released' WHERE id!=?",(admitted['lease_id'],))
    elif damage=='child-expired':
        with owner.transaction() as con:con.execute('UPDATE leases SET last_heartbeat=0 WHERE id=?',(admitted['lease_id'],))
    elif damage=='wrong-input':
        with pytest.raises(DelegationRefused):engine.bind_input(selector,dict(input_sha256='3'*64,input_bytes=9856,body_sha256='f'*64))
        return
    else:
        with pytest.raises(DelegationRefused):engine.bind_input(selector,dict(input_sha256='e'*64,input_bytes=9856,body_sha256='f'*64))
        return
    with pytest.raises(DelegationRefused):engine.consume(selector,dict(attempt_id='runtime-attempt',process_ref_sha256='1'*64))


def test_existing_generic_result_status_and_artifact_paths_deny_economic_v3(economy):
    owner,_,engine,token,request,_,_,_,_=economy
    owner.reserve_protected_memory(token,request,authority=engine._fixture_root_authority(request))
    for read in (lambda:owner.child_binding(token,request['run_id']),
                 lambda:owner.observe(token,'status',request['run_id']),lambda:owner.returns(token)):
        with pytest.raises(DelegationRefused,match='participant_view_required'):read()


def test_ledger_failure_retains_original_consumption_and_lease_no_refund(economy,monkeypatch):
    owner,_,engine,_,_,selector,_,_,_=economy
    admitted=authorize(economy);bind(engine,selector)
    monkeypatch.setattr(pool_ledger,'append',lambda **_k:False)
    with pytest.raises(DelegationRefused,match='accounting_unknown'):
        engine.settle(selector,dict(rc=0,result_sha256='2'*64,result_bytes=97))
    with owner.transaction() as con:
        row=con.execute('SELECT * FROM operator_child_authorizations').fetchone()
        assert json.loads(row['request_json'])['economic']['phase']=='SETTLING'
        assert owner.lease(con,admitted['lease_id'])['state']=='held'
    with pytest.raises(DelegationRefused):engine.consume(selector,dict(attempt_id='runtime-attempt',process_ref_sha256='1'*64))


@pytest.mark.parametrize('withdrawal',['host','account'])
def test_current_account_or_host_withdrawal_after_admission_refuses_consumption(economy,monkeypatch,withdrawal):
    owner,broker,engine,_,_,selector,_,_,_=economy
    authorize(economy)
    engine.bind_input(selector,dict(input_sha256='e'*64,input_bytes=9856,body_sha256='f'*64))
    if withdrawal=='host':
        import glm_host_account_source
        monkeypatch.setattr(glm_host_account_source,'filter_observed_accounts',lambda *_a,**_k:([],'withdrawn'))
    else:
        path=Path(broker.accounts_path);data=json.loads(path.read_text())
        data['providers']['glm']['enabled']=False;path.write_text(json.dumps(data));broker._accounts_mtime=None
    with pytest.raises(DelegationRefused,match='readiness_withdrawn'):
        engine.consume(selector,dict(attempt_id='runtime-attempt',process_ref_sha256='1'*64))
    with owner.transaction() as con:
        assert json.loads(con.execute('SELECT request_json FROM operator_child_authorizations').fetchone()[0])['economic']['phase']=='BOUND'


def test_existing_only_broker_never_creates_or_migrates_missing_namespace(economy,tmp_path,monkeypatch):
    _,broker,_,_,_,_,_,_,_=economy
    def forbidden(_self):raise AssertionError('no schema initialization')
    monkeypatch.setattr(Broker,'_init_db',forbidden)
    reopened=Broker(db_path=broker.db_path,lock_path=broker.lock_path,accounts_path=broker.accounts_path,
        now_fn=broker.now_fn,this_host=broker.this_host,existing_only=True)
    with reopened._conn() as con:assert con.execute('SELECT count(*) FROM leases').fetchone()[0]==1
    missing=tmp_path/'absent'
    with pytest.raises(FileNotFoundError):Broker(db_path=str(missing/'db'),lock_path=str(missing/'lock'),existing_only=True)
    assert not missing.exists()
