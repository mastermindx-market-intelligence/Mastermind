"""Focused source tests; imports use inert protected-reader collaborators only."""
import ast
from contextlib import contextmanager
import copy
import grp
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, Mapping, Sequence
import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'ops/executive_os/acceptance.py'
NAMES = {'_protected_control_definition', '_attended_worker_membership',
         '_validate_protected_membership_snapshot', '_validate_service_directory_group_sets',
         '_live_directory_membership_snapshot'}


def target():
    # Compile the exact production definitions, avoiding unrelated opt-in host
    # acceptance imports. No parallel validator implementation is substituted.
    tree = ast.parse(SOURCE.read_text())
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
    assert len(selected) == len(NAMES)
    namespace = dict(Path=Path, os=os, grp=grp, stat=stat, hashlib=hashlib, re=re,
                     Any=Any, Mapping=Mapping, Sequence=Sequence,
                     AcceptanceError=type('AcceptanceError', (RuntimeError,), {}),
                     CONTROL_USER='_mastermind_exec', CONTROL_GROUP='_mastermind_exec',
                     WORKER_USER='_mastermind_worker', WORKER_GROUP='_mastermind_worker',
                     OPS_GROUP='_mastermind_ops', AGENT_RELAY_UID=457, AGENT_RELAY_GID=457,
                     AGENT_RELAY_USER='_mastermind_agent_relay', AGENT_RELAY_GROUP='_mastermind_agent_relay',
                     _UUID_RE=re.compile(r'^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$'),
                     _REVIEWED_MACOS_ACCOUNT_GROUPS={'everyone':12, 'localaccounts':61, '_lpoperator':100, 'com.apple.access_disabled':396})
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return SimpleNamespace(**namespace)


@pytest.fixture
def subject():
    return target()


def group_args(subject):
    return dict(system_group_gids=subject._REVIEWED_MACOS_ACCOUNT_GROUPS,
                control_groups=[450,451,12,61,100], worker_groups=[451,12,61,100],
                control_gid=450, worker_gid=451)


def test_ordinary_control_and_worker_groups_are_preserved(subject):
    assert subject._validate_service_directory_group_sets(**group_args(subject)) == {451,12,61,100}


@pytest.mark.parametrize('where', ['control_groups', 'worker_groups'])
def test_extra_unbound_group_remains_refused(subject, where):
    args=group_args(subject);args[where]+=[471]
    with pytest.raises(subject.AcceptanceError):
        subject._validate_service_directory_group_sets(**args)


def test_selected_finite_gid_added_only_to_control(subject):
    args=group_args(subject);args['control_groups']+=[471];args['attended_worker_gid']=471
    assert subject._validate_service_directory_group_sets(**args)=={451,12,61,100}
    args['worker_groups']+=[471]
    with pytest.raises(subject.AcceptanceError):
        subject._validate_service_directory_group_sets(**args)


@pytest.mark.parametrize('gid', [450,451,453,454,455,456,457,True,0,501])
def test_reserved_or_malformed_finite_gid_is_never_admitted(subject,gid):
    args=group_args(subject);args['attended_worker_gid']=gid;args['control_groups']+=[gid]
    with pytest.raises(subject.AcceptanceError):
        subject._validate_service_directory_group_sets(**args)


def snapshot():
    names=['_mastermind_exec','_mastermind_worker','operator','_mastermind_paid_test']
    uids=[450,451,501,470];gids=[450,451,20,471]
    users={n:dict(unique_uid=u,primary_gid=g,generated_uid=f'00000000-0000-0000-0000-{i+1:012d}')
           for i,(n,u,g) in enumerate(zip(names,uids,gids))}
    groups={}
    for i,(name,gid,member) in enumerate([('_mastermind_exec',450,None),('_mastermind_worker',451,names[0]),
                                       ('_mastermind_ops',453,'operator'),('_mastermind_paid_test',471,names[0])]):
        groups[name]=dict(primary_gid=gid,generated_uid=f'10000000-0000-0000-0000-{i+1:012d}',
                          name_members=[] if member is None else [member],
                          uuid_members=[] if member is None else [users[member]['generated_uid']],nested_groups=[])
    return dict(users=users,groups=groups,group_primary_gids={k:v['primary_gid'] for k,v in groups.items()})


def membership_args():
    return dict(control_user='_mastermind_exec',worker_user='_mastermind_worker',operator_user='operator',
                control_uid=450,worker_uid=451,operator_uid=501,control_gid=450,worker_gid=451,ops_gid=453,
                attended_worker=dict(worker_user='_mastermind_paid_test',worker_group='_mastermind_paid_test',worker_uid=470,worker_gid=471))


def test_all_four_secondary_membership_forms_join(subject):
    result=subject._validate_protected_membership_snapshot(snapshot(),**membership_args())
    assert result['_mastermind_paid_test']==['_mastermind_exec','_mastermind_paid_test']


@pytest.mark.parametrize('fault',['named','uuid','nested','primary','uid_alias','gid_alias','shared_uuid','missing_user'])
def test_secondary_membership_drift_refuses(subject,fault):
    data=snapshot();group=data['groups']['_mastermind_paid_test']
    if fault=='named':group['name_members']+=['operator']
    if fault=='uuid':group['uuid_members']+=['99999999-9999-9999-9999-999999999999']
    if fault=='nested':group['nested_groups']=['nested']
    if fault=='primary':data['users']['extra']={'primary_gid':471,'unique_uid':499}
    if fault=='uid_alias':data['users']['extra']={'primary_gid':20,'unique_uid':470}
    if fault=='gid_alias':data['group_primary_gids']['alias']=471
    if fault=='shared_uuid':data['users']['_mastermind_paid_test']['generated_uid']=data['users']['_mastermind_exec']['generated_uid']
    if fault=='missing_user':del data['users']['_mastermind_paid_test']
    with pytest.raises(subject.AcceptanceError):
        subject._validate_protected_membership_snapshot(data,**membership_args())


@pytest.fixture
def composition(monkeypatch,subject):
    raw=dict(worker_id='paid-test-01',worker_user='_mastermind_paid_test',worker_uid=470,worker_gid=471,
             control_uid=450,control_gid=450,allowed_supplementary_gids=[],
             provider_home='/private/var/db/mastermind-executive/workers/paid-test-01/provider-home')
    physical=SimpleNamespace(provider='minimax',host_ref='this-host',worker_id='paid-test-01',
                             worker_source_config_digest='b'*64,digest='c'*64)
    seen=[]
    class BoundSource:
        expected_sha256='a'*64
        bindings=(physical,)
        def __call__(self,host,worker):
            seen.append(('lookup',host,worker));return physical
    bound=BoundSource()
    class Factory:
        @classmethod
        def from_path(cls,path,sha):
            assert (path,sha)==('/protected/bindings.json','a'*64)
            seen.append(('bindings',path,sha));return bound
    binding_module=ModuleType('control_plane.executive_fabric_composition');binding_module.FabricBindingSource=Factory
    canary_module=ModuleType('control_plane.fabric_attended_canary')
    def definition(path,binding):
        assert str(path)=='/protected/finite-worker.json';assert binding is physical
        seen.append(('definition',str(path)));return raw
    canary_module.definition=definition
    if 'control_plane' not in sys.modules:
        module=ModuleType('control_plane');module.__path__=[];monkeypatch.setitem(sys.modules,'control_plane',module)
    monkeypatch.setitem(sys.modules,binding_module.__name__,binding_module)
    monkeypatch.setitem(sys.modules,canary_module.__name__,canary_module)
    monkeypatch.setattr(grp,'getgrgid',lambda gid:SimpleNamespace(gr_name='_mastermind_paid_test'))
    config=dict(fabric_attended_probe={'worker_config_path':'/protected/finite-worker.json'},fabric_bindings_path='/protected/bindings.json',fabric_bindings_sha256='a'*64)
    args=dict(control_uid=450,control_gid=450,primary_worker_uid=451,primary_worker_gid=451,ops_gid=453)
    return SimpleNamespace(raw=raw,physical=physical,bound=bound,seen=seen,config=config,args=args)


def test_factory_joins_exact_definition_binding_and_records_hashes(subject,composition):
    c=composition;result=subject._attended_worker_membership(c.config,**c.args)
    assert result['worker_gid']==471
    assert result['worker_config_sha256']=='b'*64 and result['physical_binding_sha256']=='c'*64
    assert [s[0] for s in c.seen]==['bindings','definition','lookup']


def test_absent_finite_stanza_grants_no_group(subject,composition):
    assert subject._attended_worker_membership({},**composition.args) is None
    assert composition.seen==[]


@pytest.mark.parametrize('fault',['extra_stanza_key','duplicate_binding','wrong_uid','reserved_gid','nonempty_groups','wrong_control','wrong_home','wrong_user','unreadable_definition'])
def test_unjoined_definition_never_grants_membership(subject,composition,fault,monkeypatch):
    c=composition
    if fault=='extra_stanza_key':c.config['fabric_attended_probe']['gid']=471
    if fault=='duplicate_binding':c.bound.bindings=(c.physical,c.physical)
    if fault=='wrong_uid':c.raw['worker_uid']=451
    if fault=='reserved_gid':c.raw['worker_gid']=454
    if fault=='nonempty_groups':c.raw['allowed_supplementary_gids']=[450]
    if fault=='wrong_control':c.raw['control_gid']=451
    if fault=='wrong_home':c.raw['provider_home']='/private/var/db/other/home'
    if fault=='wrong_user':c.raw['worker_user']='operator'
    if fault=='unreadable_definition':
        def fail(*args):raise subject.AcceptanceError('native reader refused')
        monkeypatch.setattr(sys.modules['control_plane.fabric_attended_canary'],'definition',fail)
    with pytest.raises(subject.AcceptanceError):
        subject._attended_worker_membership(c.config,**c.args)


def test_control_bytes_are_custody_checked_and_digest_bound(subject,monkeypatch,tmp_path):
    path=tmp_path/'control.json';raw=b'{"finite":"fixture"}\n';path.write_bytes(raw);observed=[]
    @contextmanager
    def opened(candidate):
        assert candidate==path
        descriptor=os.open(path,os.O_RDONLY)
        try:yield descriptor,SimpleNamespace(st_gid=450,st_mode=stat.S_IFREG|0o440,st_size=len(raw))
        finally:os.close(descriptor)
    def reread(candidate,digest):
        observed.append((candidate,digest));assert digest==hashlib.sha256(raw).hexdigest();return json.loads(raw)
    module=ModuleType('control_plane.codex_provider_realm');module._native_open=opened;module._native_read_config=reread
    monkeypatch.setitem(sys.modules,module.__name__,module)
    value,digest=subject._protected_control_definition(path,450)
    assert value=={'finite':'fixture'} and observed==[(path,digest)]


def test_live_snapshot_includes_the_selected_secondary_account_and_group(subject,monkeypatch):
    function=subject._live_directory_membership_snapshot
    lookups=[]
    names=['_mastermind_exec','_mastermind_worker','operator','_mastermind_paid_test']
    uids=[450,451,501,470];gids=[450,451,20,471]
    def census(kind,attribute,**kwargs):
        if kind=='Groups':return {'_mastermind_exec':450,'_mastermind_worker':451,'_mastermind_ops':453,'_mastermind_paid_test':471}
        return dict(zip(names,uids if attribute=='UniqueID' else gids))
    def attribute(record,key):
        lookups.append((record,key))
        if key=='PrimaryGroupID':return str(census('Groups',key)[record.rsplit('/',1)[1]])
        return '00000000-0000-0000-0000-000000000001'
    monkeypatch.setitem(function.__globals__,'_numeric_directory_census',census)
    monkeypatch.setitem(function.__globals__,'_directory_attribute',attribute)
    monkeypatch.setitem(function.__globals__,'_directory_values',lambda *args:())
    value=function(operator_user='operator',attended_worker=membership_args()['attended_worker'])
    assert value['users']['_mastermind_paid_test']['unique_uid']==470
    assert value['groups']['_mastermind_paid_test']['primary_gid']==471
    assert ('/Users/_mastermind_paid_test','GeneratedUID') in lookups
    assert ('/Groups/_mastermind_paid_test','GeneratedUID') in lookups


@pytest.mark.parametrize('gid,mode,size', [(451,0o440,2),(450,0o640,2),(450,0o440,0),(450,0o440,65537)])
def test_control_custody_failure_precedes_definition_interpretation(subject,monkeypatch,tmp_path,gid,mode,size):
    path=tmp_path/'untrusted-control';path.write_bytes(b'{}')
    @contextmanager
    def opened(candidate):
        descriptor=os.open(path,os.O_RDONLY)
        try:yield descriptor,SimpleNamespace(st_gid=gid,st_mode=stat.S_IFREG|mode,st_size=size)
        finally:os.close(descriptor)
    def forbidden(*args):raise AssertionError('untrusted bytes were interpreted')
    module=ModuleType('control_plane.codex_provider_realm');module._native_open=opened;module._native_read_config=forbidden
    monkeypatch.setitem(sys.modules,module.__name__,module)
    with pytest.raises(subject.AcceptanceError):subject._protected_control_definition(path,450)
