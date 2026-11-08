"""Inert host permission premises + real disposable intent/carrier subprocess.

No real native tool permission, SSH account, remote read or original bytes are
used. The production host export remains unsupported/default-deny.
"""
import ast
from dataclasses import replace
import hashlib
import importlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest
from test_provider_plan_auto_routing import source_stage

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT/'ops/native_fabric/original_directory_custody'


@pytest.fixture
def wiring(source_stage, tmp_path, monkeypatch):
    stage = tmp_path/'ext'
    shutil.copytree(source_stage, stage)
    patch = COMPONENT/'owner-registration.forward.patch'
    applied = subprocess.run(['patch','--batch','--forward','-p1','-i',str(patch)], cwd=tmp_path,
                             text=True, capture_output=True)
    assert applied.returncode == 0, applied.stderr + applied.stdout
    for source, target in (('reader.py','original_directory_custody_reader.py'),
                           ('owner.py','original_directory_custody_owner.py')):
        shutil.copyfile(COMPONENT/source, stage/target)
    names = {p.stem for p in stage.glob('*.py')}
    old = {name:sys.modules.get(name) for name in names}
    for name in names:sys.modules.pop(name,None)
    monkeypatch.syspath_prepend(str(stage))
    m = importlib.import_module('original_directory_custody_owner')
    task = importlib.import_module('fabric_task')
    r = m.reader
    entry = {'roles':['lanes'],'ssh_alias':'inert-enrolled-alias','allowed_modes':['glm']}
    (stage/'hosts.json').write_text(json.dumps({r.HOST:entry}))
    metadata = tmp_path/'fixture-metadata';metadata.mkdir()
    pins = []
    for name in ('binding.json','read-request.json'):
        path = metadata/name;path.write_bytes(b'{"inert_original_metadata":true}')
        pins.append((path,hashlib.sha256(path.read_bytes()).hexdigest()))
    monkeypatch.setattr(m,'METADATA',tuple(pins))
    destination = tmp_path/'diagnostic-action'
    monkeypatch.setattr(m,'DESTINATION',str(destination))
    real_open = os.open
    class Chain:
        def __init__(self):
            destination.mkdir(mode=0o700)
            self.fd = real_open(destination,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            self.closed=False
        def verify(self):
            assert not self.closed
            a=os.stat(destination,follow_symlinks=False);b=os.fstat(self.fd)
            assert (a.st_dev,a.st_ino,a.st_uid,a.st_mode)==(b.st_dev,b.st_ino,b.st_uid,b.st_mode)
        def close(self):
            if not self.closed:os.close(self.fd);self.closed=True
    def reserve(path):
        assert path==str(destination)
        return Chain()
    # Ancestor/permission rules remain in the incumbent reserve_destination;
    # fixture isolates its fresh-leaf premise, uses actual O_EXCL/fsync writes.
    monkeypatch.setattr(m.delivery,'reserve_destination',reserve)
    account = r.OwnerTransportBinding(r.HOST,entry['ssh_alias'],'1'*64,os.getuid())
    class Permission(m.NativeMetadataPermissionSource):
        def __init__(self):
            self.context=object();self.live=True;self.bound=account;self.calls=[]
            self.denied=False;self.expected=None
        def open_permission(self,view,uid,source,entry):
            assert view.root==view.parent==r.ROOT and view.run_id==r.RUN and view.host==r.HOST
            assert view.request_sha256==r.validate_request(r.request()) and uid==os.getuid()
            self.expected=(view,uid,source,entry);self.calls.append('open')
            return None if self.denied else self.context
        def current(self,context,view,uid,source,entry):
            self.calls.append('current')
            return self.live and context is self.context and (view,uid,source,entry)==self.expected
        def binding(self,context):
            assert context is self.context
            return self.bound
    p=Permission();calls=[];after=[]
    # Exercise the actual bounded incumbent transport. Replace only SSH's
    # process with a local Python child whose filesystem is exclusively ours.
    fs=tmp_path/'remote-fixture';(fs/'account/home/lanes/ext/lanes').mkdir(parents=True)
    for folder in (fs,*[fs.joinpath(*Path('account/home/lanes/ext/lanes').parts[:n]) for n in range(1,6)]):
        folder.chmod(0o700)
    child_prefix = '''import os,pwd
from types import SimpleNamespace
_open,_stat=os.open,os.stat
_fs=FS
def _fixture_open(path,*a,**kw):
 if path=='/':path=_fs
 return _open(path,*a,**kw)
def _fixture_stat(path,*a,**kw):
 if path=='/':path=_fs
 return _stat(path,*a,**kw)
os.open=_fixture_open
os.stat=_fixture_stat
pwd.getpwuid=lambda uid:SimpleNamespace(pw_dir='/account/home')
'''.replace('FS',repr(str(fs)))
    actual_popen=subprocess.Popen
    def popen(argv,**kw):
        assert argv[:7]==['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8']
        assert argv[7]==entry['ssh_alias'] and len(argv)==9
        parsed=shlex.split(argv[8]);assert parsed[:4]==['python3','-I','-S','-c'] and len(parsed)==5
        calls.append(argv)
        process=actual_popen([sys.executable,'-I','-S','-c',child_prefix+parsed[4]],**kw)
        return process
    monkeypatch.setattr(m.delivery.subprocess,'Popen',popen)
    original_transport=m.delivery.transport
    def transport(*a,**kw):
        result=original_transport(*a,**kw)
        for callback in after:callback()
        return result
    monkeypatch.setattr(m.delivery,'transport',transport)
    try:
        yield SimpleNamespace(m=m,r=r,task=task,p=p,stage=stage,destination=destination,
                              pins=pins,calls=calls,after=after,entry=entry,Permission=Permission)
    finally:
        for name in names:
            sys.modules.pop(name,None)
            if old[name] is not None:sys.modules[name]=old[name]


def test_fixed_factory_carrier_intent_and_closed_metadata_consumer(wiring):
    w=wiring;owner=w.task._original_directory_owner_factory(w.p)
    assert not w.destination.exists() and w.calls==[] and w.p.calls==[]
    result=w.m.run_fixed_metadata_action(owner)
    assert result['state']=='SAFE_AT_OBSERVATION' and result['artifact_bytes_read']==0
    assert result['directories'][0]['component']=='RESULT_DIRECTORY'
    assert len(w.calls)==1 and owner._chain.closed
    intent=json.loads((w.destination/'intent.json').read_bytes())
    observed=json.loads((w.destination/'observed.json').read_bytes())
    assert intent['state']=='EFFECT_UNKNOWN' and intent['retry_authorized'] is False
    assert observed['state']=='OBSERVED_METADATA_ONLY' and observed['original_outcome_accepted'] is False
    assert set(p.name for p in w.destination.iterdir())=={'intent.json','metadata-response.json','observed.json'}
    with pytest.raises(w.r.Refused):w.m.run_fixed_metadata_action(owner)
    another=w.m.owner_factory(w.Permission())
    with pytest.raises(w.r.Refused):w.m.run_fixed_metadata_action(another)
    assert len(w.calls)==1


@pytest.mark.parametrize('source',['missing','default','mapping','old_current'])
def test_no_native_permission_export_refuses_without_metadata_intent_or_transport(wiring,source,monkeypatch):
    w=wiring
    supplied={'missing':None,'default':w.m.NativeMetadataPermissionSource(),
              'mapping':{'grant':True,'root':w.r.ROOT},'old_current':w.r.NativeInvocationOwner()}[source]
    monkeypatch.setattr(w.m.delivery,'local_file',lambda *a,**k:pytest.fail('default-deny must not read'))
    with pytest.raises(w.r.Refused,match='export_unavailable'):w.task._original_directory_owner_factory(supplied)
    assert not w.destination.exists() and w.calls==[]


@pytest.mark.parametrize('kind',['denied','boolean','mapping','expired','uid','alias','account','metadata','registry','source','permission_method'])
def test_exact_permission_account_source_and_metadata_fences(wiring,kind):
    w=wiring;owner=w.m.owner_factory(w.p)
    if kind=='denied':w.p.denied=True
    elif kind=='boolean':w.p.context=True
    elif kind=='mapping':w.p.context={'grant':True}
    elif kind=='expired':w.p.live=False
    elif kind in ('uid','alias','account'):
        b=w.p.bound
        w.p.bound=w.r.OwnerTransportBinding(b.host,'different' if kind=='alias' else b.ssh_alias,
            'bad' if kind=='account' else b.account_scope_sha256,0 if kind=='uid' else b.remote_uid)
    elif kind=='metadata':w.pins[0][0].write_bytes(b'changed')
    elif kind=='registry':(w.stage/'hosts.json').write_text(json.dumps({w.r.HOST:dict(w.entry,extra=True)}))
    elif kind=='source':(w.stage/'original_directory_custody_reader.py').write_bytes(b'changed')
    elif kind=='permission_method':w.p.current=lambda *a:True
    with pytest.raises(w.r.Refused):w.m.run_fixed_metadata_action(owner)
    assert not w.destination.exists() and w.calls==[]


@pytest.mark.parametrize('change',['permission','account','registry','metadata','source'])
def test_late_withdrawal_keeps_unknown_intent_and_withholds_observed(wiring,change):
    w=wiring;owner=w.m.owner_factory(w.p)
    def withdraw():
        if change=='permission':w.p.live=False
        elif change=='account':w.p.bound=w.r.OwnerTransportBinding(w.r.HOST,w.entry['ssh_alias'],'2'*64,os.getuid())
        elif change=='registry':(w.stage/'hosts.json').write_text('{}')
        elif change=='metadata':w.pins[0][0].write_bytes(b'changed')
        elif change=='source':(w.stage/'original_directory_custody_owner.py').write_bytes(b'changed')
    w.after.append(withdraw)
    with pytest.raises(w.r.Refused):w.m.run_fixed_metadata_action(owner)
    assert len(w.calls)==1 and (w.destination/'intent.json').exists()
    assert not (w.destination/'observed.json').exists() and owner._chain.closed


def test_interrupted_carrier_never_releases_or_adopts_durable_intent(wiring,monkeypatch):
    w=wiring;calls=[]
    def lost(*a,**kw):calls.append(1);raise OSError('inert lost transport')
    monkeypatch.setattr(w.m.delivery,'transport',lost)
    with pytest.raises(w.r.Refused):w.m.run_fixed_metadata_action(w.m.owner_factory(w.p))
    assert (w.destination/'intent.json').exists() and not (w.destination/'observed.json').exists()
    with pytest.raises(w.r.Refused):w.m.run_fixed_metadata_action(w.m.owner_factory(w.Permission()))
    assert calls==[1]


def test_direct_carrier_request_cannot_bypass_owner(wiring):
    w=wiring
    with pytest.raises(w.r.Refused):w.m.delivery.transport(w.entry['ssh_alias'],w.r.request())
    owner=w.m.owner_factory(w.p)
    with pytest.raises(w.r.Refused):w.m.delivery.transport(w.entry['ssh_alias'],w.r.request(),original_directory_owner=owner)
    assert w.calls==[] and not w.destination.exists()


@pytest.mark.parametrize('field',['root','parent','run_id','host','action','request_sha256','directory_scope','artifact_namespace'])
def test_foreign_owner_view_refuses_before_permission_open(wiring,field):
    w=wiring;owner=w.m.owner_factory(w.p);v=w.r.request()
    view=w.r.MetadataActionView(w.r.SCHEMA,w.r.ACTION,w.r.validate_request(v),w.r.RUN,
        w.r.ROOT,w.r.ROOT,w.r.HOST,v['directory_scope'],w.r.production.directory(v['contract']))
    assert owner.admit_original_directory_metadata(replace(view,**{field:'foreign'}),os.getuid()) is False
    assert w.p.calls==[] and w.calls==[] and not w.destination.exists()


def test_wrong_remote_uid_withholds_same_account_observation(wiring):
    w=wiring;w.p.bound=w.r.OwnerTransportBinding(w.r.HOST,w.entry['ssh_alias'],'1'*64,os.getuid()+1)
    with pytest.raises(w.r.Refused):w.m.run_fixed_metadata_action(w.m.owner_factory(w.p))
    assert len(w.calls)==1 and (w.destination/'intent.json').exists()
    assert not (w.destination/'observed.json').exists()


def test_permission_withdrawal_during_intent_blocks_carrier(wiring,monkeypatch):
    w=wiring;write=w.m.delivery.write_exclusive
    def withdraw(fd,name,raw):
        value=write(fd,name,raw)
        if name=='intent.json':w.p.live=False
        return value
    monkeypatch.setattr(w.m.delivery,'write_exclusive',withdraw)
    owner=w.m.owner_factory(w.p)
    with pytest.raises(w.r.Refused):w.m.run_fixed_metadata_action(owner)
    assert w.calls==[] and (w.destination/'intent.json').exists() and owner._chain.closed


@pytest.mark.parametrize('change',['bytes','inode'])
def test_durable_intent_preimage_and_inode_cannot_be_substituted(wiring,monkeypatch,change):
    w=wiring;write=w.m.delivery.write_exclusive
    def alter(fd,name,raw):
        value=write(fd,name,raw)
        if name=='intent.json':
            path=w.destination/name
            if change=='inode':path.rename(w.destination/'original-fixture-intent')
            path.write_bytes(b'changed fixture intent')
        return value
    monkeypatch.setattr(w.m.delivery,'write_exclusive',alter)
    owner=w.m.owner_factory(w.p)
    with pytest.raises(w.r.Refused):w.m.run_fixed_metadata_action(owner)
    assert w.calls==[] and (w.destination/'intent.json').exists() and owner._chain.closed


def test_closed_old_collector_and_no_cli_activation(wiring):
    w=wiring
    assert w.m.DESTINATION!=str(w.m.ORIGINAL/'plan-review-original-collection-1230')
    assert w.r.request()['contract']['names']==['plan-review-component.patch']
    module=ast.parse((COMPONENT/'owner.py').read_text())
    assert not any(isinstance(node,ast.If) and isinstance(node.test,ast.Compare) for node in module.body)
    assert 'original_directory_owner' not in w.task.main.__code__.co_names


@pytest.mark.parametrize('name',['artifact_production.py','artifact_reader.py','original_directory_custody_reader.py'])
def test_generated_program_is_bound_to_exact_captured_source_bytes(wiring,name):
    w=wiring;expected=w.m._sources();expected[name]='0'*64
    with pytest.raises(w.r.Refused,match='generated_source_changed'):w.m._remote_source(expected)
    assert w.calls==[] and not w.destination.exists()


@pytest.mark.parametrize('change',['permission','account','method','uid','same_bytes_inode'])
def test_last_intent_read_changes_cannot_progress_to_carrier(wiring,monkeypatch,change):
    w=wiring;owner=w.m.owner_factory(w.p);armed={'value':False};changed=[]
    generate=w.m._remote_source;read=w.m.delivery.read_local_at
    def after_generation(expected):
        result=generate(expected);armed['value']=True;return result
    def last_read(chain,name,limit,**kw):
        if armed['value'] and name=='intent.json':
            armed['value']=False
            if change=='same_bytes_inode':
                path=w.destination/name;raw=path.read_bytes()
                path.rename(w.destination/'held-original-fixture-intent')
                path.write_bytes(raw)
                changed.append((w.destination/'held-original-fixture-intent').stat().st_ino)
                return read(chain,name,limit,**kw)
            raw=read(chain,name,limit,**kw)
            if change=='permission':w.p.live=False
            elif change=='account':w.p.bound=w.r.OwnerTransportBinding(w.r.HOST,w.entry['ssh_alias'],'2'*64,os.getuid())
            elif change=='method':w.p.current=lambda *a:True
            elif change=='uid':
                uid=os.getuid();monkeypatch.setattr(w.m.os,'getuid',lambda:uid+1)
            changed.append(change)
            return raw
        return read(chain,name,limit,**kw)
    monkeypatch.setattr(w.m,'_remote_source',after_generation)
    monkeypatch.setattr(w.m.delivery,'read_local_at',last_read)
    with pytest.raises(w.r.Refused):w.m.run_fixed_metadata_action(owner)
    assert changed and w.calls==[], 'late change must refuse BEFORE any carrier Popen'
    assert (w.destination/'intent.json').exists() and not (w.destination/'observed.json').exists()
    assert owner._chain.closed
    if change=='same_bytes_inode':
        assert (w.destination/'intent.json').stat().st_ino!=changed[0]
        assert (w.destination/'intent.json').read_bytes()==(w.destination/'held-original-fixture-intent').read_bytes()


@pytest.mark.parametrize('change',['permission','same_bytes_inode'])
def test_last_response_read_cannot_publish_after_withdrawal_or_replacement(wiring,monkeypatch,change):
    w=wiring;owner=w.m.owner_factory(w.p);read=w.m.delivery.read_local_at;changed=[]
    def intercept(chain,name,limit,**kw):
        if name=='metadata-response.json':
            if change=='same_bytes_inode':
                path=w.destination/name;raw=path.read_bytes()
                path.rename(w.destination/'held-original-fixture-response');path.write_bytes(raw)
                changed.append(change)
                return read(chain,name,limit,**kw)
            raw=read(chain,name,limit,**kw);w.p.live=False;changed.append(change);return raw
        return read(chain,name,limit,**kw)
    monkeypatch.setattr(w.m.delivery,'read_local_at',intercept)
    with pytest.raises(w.r.Refused):w.m.run_fixed_metadata_action(owner)
    assert changed and len(w.calls)==1 and owner._chain.closed
    assert (w.destination/'intent.json').exists() and not (w.destination/'observed.json').exists()


def test_forward_patch_preserves_every_existing_factory_and_transport_branch(wiring,source_stage):
    w=wiring
    original=ast.parse((source_stage/'fabric_task.py').read_text())
    patched=ast.parse((w.stage/'fabric_task.py').read_text())
    patched.body=[node for node in patched.body if not isinstance(node,ast.FunctionDef) or node.name!='_original_directory_owner_factory']
    assert ast.dump(patched)==ast.dump(original)
    before=(source_stage/'artifact_delivery.py').read_text()
    after=(w.stage/'artifact_delivery.py').read_text()
    after=after.replace('def read_local_at(chain, name, limit, *, expected_inode=None):',
        'def read_local_at(chain, name, limit):').replace(
        '        if expected_inode is not None and (before.st_dev, before.st_ino) != expected_inode:\n'
        '            raise ValueError("local_evidence_inode_changed")\n','')
    assert after.replace(',\n              original_directory_owner=None','').replace(
        '    if type(request) is dict and request.get("schema") == "mastermind.original_directory_metadata.v1":\n'
        '        import original_directory_custody_owner\n'
        '        code = original_directory_custody_owner.code_for_registered_transport(\n'
        '            alias, request, original_directory_owner)\n'
        '        response_limit = 8192\n'
        '    elif type(request) is dict and request.get("schema") == "mastermind.original_operator_stdout_read.v1":',
        '    if type(request) is dict and request.get("schema") == "mastermind.original_operator_stdout_read.v1":')==before
