"""Proposed owner/control boundary and real disposable directory metadata only.

TrustedOwner below is an inert owner fixture, NOT an actual runtime grant. The
missing concrete native registration remains explicit in component/README.
"""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import pytest
from test_provider_plan_auto_routing import source_stage

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/'ops/native_fabric/original_directory_custody/reader.py'


@pytest.fixture
def control(source_stage,monkeypatch,tmp_path):
    names=('artifact_production','artifact_reader','current_source_observation','artifact_delivery','native_runtime_bindings')
    old={k:sys.modules.get(k) for k in names}
    for k in old:sys.modules.pop(k,None)
    monkeypatch.syspath_prepend(str(source_stage))
    import artifact_delivery as incumbent_delivery
    spec=importlib.util.spec_from_file_location('original_custody_proposal',MODULE)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    fs=tmp_path/'owned-root';fs.mkdir(mode=0o700)
    home=fs/'account/home';leaf=home/'lanes/ext/lanes'
    leaf.mkdir(parents=True,mode=0o700)
    secret=leaf/'plan-review-component.patch';secret.write_bytes(b'UNREAD_PRIVATE_ARTIFACT')
    prefixes=[fs,*[fs.joinpath(*Path('/account/home/lanes/ext/lanes').parts[1:i]) for i in range(2,7)]]
    opens=[];fdpaths={};outstanding=set();fault={'kind':None};counts={};fstat_counts={}
    real_open,real_stat,real_fstat,real_close=os.open,os.stat,os.fstat,os.close
    def op(path,flags,*a,**kw):
        candidate=fs if path=='/' else fdpaths[kw['dir_fd']]/path
        opens.append((candidate,flags))
        assert candidate in prefixes and flags & os.O_DIRECTORY
        assert not flags & (os.O_CREAT|os.O_WRONLY|os.O_RDWR)
        fd=real_open(fs,flags) if path=='/' else real_open(path,flags,*a,**kw)
        fdpaths[fd]=candidate;outstanding.add(fd);return fd
    def st(path,*a,**kw):
        candidate=fs if path=='/' else fdpaths[kw['dir_fd']]/path
        info=real_stat(fs,follow_symlinks=False) if path=='/' else real_stat(path,*a,**kw)
        counts[candidate]=counts.get(candidate,0)+1
        if candidate==leaf and fault['kind']=='uid':return _changed_info(info,st_uid=os.getuid()+1)
        if candidate==leaf and fault['kind']=='directory' and counts[candidate]>1:return _changed_info(info,st_ino=info.st_ino+1)
        if path=='/' and fault['kind']=='ancestor':return _changed_info(info,st_ino=info.st_ino+1)
        return info
    def fst(fd):
        fstat_counts[fd]=fstat_counts.get(fd,0)+1
        if (fstat_counts[fd]==1 and ((fault['kind']=='initial_root_fstat' and fdpaths[fd]==fs)
                or (fault['kind']=='initial_child_fstat' and fdpaths[fd]==fs/'account'))):
            raise OSError('inert initial fstat failure')
        info=real_fstat(fd)
        if fdpaths.get(fd)==leaf and fault['kind']=='uid':return _changed_info(info,st_uid=os.getuid()+1)
        return info
    def close(fd):
        real_close(fd);outstanding.remove(fd)
    def with_io(action):
        counts.clear();fstat_counts.clear()
        with monkeypatch.context() as m:
            m.setattr(module.os,'open',op);m.setattr(module.os,'stat',st);m.setattr(module.os,'fstat',fst);m.setattr(module.os,'close',close)
            m.setattr(module.pwd,'getpwuid',lambda uid:SimpleNamespace(pw_dir='/account/home'))
            m.setattr(module.os,'read',lambda *a,**kw:pytest.fail('artifact bytes must never be read'))
            for name in ('chmod','chown','mkdir','unlink','rename','listdir','readlink'):
                m.setattr(module.os,name,lambda *a,**kw:pytest.fail('metadata engine must not mutate or enumerate'))
            return action()
    def transport(binding,value):
        assert binding.host=='ubuntu3'
        return module.canonical(with_io(lambda:module._metadata(value)))
    def guard():
        def execute():
            with incumbent_delivery.DirectoryChain(Path('/account/home/lanes/ext/lanes')):pass
        return with_io(execute)
    class TrustedOwner(module.OriginalDirectoryOwner):
        # Explicit inert existing-native-owner facts, never an installed grant.
        def __init__(self):
            self.permission=True;self.active=True;self.claimed=False;self._inert_transport=transport
            self.binding=module.OwnerTransportBinding('ubuntu3','inert-existing-alias',hashlib.sha256(b'inert-account').hexdigest(),os.getuid())
        def admit_original_directory_metadata(self,view,uid):
            assert type(view) is module.MetadataActionView
            assert view.action==module.ACTION and view.request_sha256==module.validate_request(module.request())
            assert view.run_id==module.RUN and view.root==view.parent==module.ROOT and view.host=='ubuntu3'
            assert view.directory_scope=='ACCOUNT_LANES_EXT_RESULT_DIRECTORY'
            assert view.artifact_namespace==module.production.directory(module.request()['contract'])
            assert uid==os.getuid()
            if not self.permission or self.claimed:return False
            self.claimed=True;return True
        def original_directory_metadata_current(self,view,uid):return self.active and self.permission and self.claimed
        def original_directory_transport_binding(self,view,uid):return self.binding
        def original_directory_metadata_transport(self,binding,value):return self._inert_transport(binding,value)
    try:yield SimpleNamespace(m=module,owner=TrustedOwner(),owner_type=TrustedOwner,transport=transport,
        tmp=fs,home=home,leaf=leaf,secret=secret,opens=opens,fault=fault,depth=5,prefixes=prefixes,guard=guard,outstanding=outstanding)
    finally:
        # Only test-created leaked FDs are closed after an adverse assertion.
        for fd in tuple(outstanding):real_close(fd);outstanding.remove(fd)
        sys.modules.pop(spec.name,None)
        for k,v in old.items():
            sys.modules.pop(k,None)
            if v is not None:sys.modules[k]=v


def test_admitted_fixture_observes_fixed_namespace_without_opening_artifact(control):
    c=control;before=c.secret.read_bytes();mode=c.leaf.stat().st_mode
    out=c.m.inspect_metadata(c.m.request(),owner=c.owner)
    assert out['state']=='SAFE_AT_OBSERVATION' and out['reason'] is None
    assert out['directories']==[{'component':'RESULT_DIRECTORY','depth':c.depth,'uid':os.getuid(),'invoking_uid':os.getuid(),'mode':0o700,'kind':'DIRECTORY'}]
    assert len(c.opens)==len(c.prefixes) and c.secret.read_bytes()==before and c.leaf.stat().st_mode==mode
    assert c.m.validate_response(c.m.canonical(out),c.m.request())==out
    assert out['artifact_files_opened']==out['artifact_bytes_read']==0
    assert all(out[k] is False for k in ('retry_authorized','execution_replayed','permission_changed','outcome_accepted'))
    with pytest.raises(c.m.Refused,match='not_admitted'):
        c.m.inspect_metadata(c.m.request(),owner=c.owner)
    assert len(c.opens)==len(c.prefixes)


@pytest.mark.parametrize('owner_kind',['missing','mapping','default_owner','old_current_owner','denied'])
def test_only_separately_admitted_native_owner_can_reach_metadata(control,owner_kind):
    c=control
    class CurrentOnly(c.m.NativeInvocationOwner):
        def admit_invocation(self,*a):return True
    owner={'missing':None,'mapping':{'root':c.m.ROOT,'admitted':True},
        'default_owner':c.m.OriginalDirectoryOwner(),'old_current_owner':CurrentOnly(),'denied':c.owner}[owner_kind]
    c.owner.permission=False
    with pytest.raises(c.m.Refused):c.m.inspect_metadata(c.m.request(),owner=owner)
    assert c.opens==[]


@pytest.mark.parametrize('field',['run_id','root','parent','host','original_request_sha256','original_binding_sha256','original_refusal_sha256','contract','extra_path'])
def test_foreign_or_changed_selector_cannot_be_made_a_grant(control,field):
    c=control;value=c.m.request()
    value[field]={'path':'/tmp/other'} if field=='contract' else 'foreign'
    with pytest.raises(c.m.Refused):c.m.inspect_metadata(value,owner=c.owner)
    assert not c.owner.claimed and c.opens==[]


@pytest.mark.parametrize('phase',['before','after'])
@pytest.mark.parametrize('change',['withdraw','account','alias'])
def test_live_owner_account_fence_withholds_late_observation(control,phase,change):
    c=control;calls=[]
    def withdraw():
        if change=='withdraw':c.owner.active=False
        else:c.owner.binding=c.m.OwnerTransportBinding('ubuntu3',
            'changed-alias' if change=='alias' else c.owner.binding.ssh_alias,
            'a'*64 if change=='account' else c.owner.binding.account_scope_sha256,c.owner.binding.remote_uid)
    original_binding=c.owner.original_directory_transport_binding
    def binding(view,uid):
        result=original_binding(view,uid)
        if phase=='before' and not calls:calls.append('bound');withdraw()
        return result
    c.owner.original_directory_transport_binding=binding
    def transport(*a):
        calls.append('transport');raw=c.transport(*a)
        if phase=='after':withdraw()
        return raw
    c.owner._inert_transport=transport
    with pytest.raises(c.m.Refused):c.m.inspect_metadata(c.m.request(),owner=c.owner)
    assert ('transport' in calls)==(phase=='after')
    assert c.owner.claimed  # No release or retry after any attempted claim.


@pytest.mark.parametrize('kind,reason',[('mode','GROUP_OR_OTHER_WRITABLE'),('symlink','SYMLINK'),('regular','NOT_DIRECTORY'),('missing','DIRECTORY_MISSING')])
def test_diagnosis_reports_exact_metadata_predicate_only(control,kind,reason):
    c=control
    if kind=='mode':c.leaf.chmod(0o775)  # Disposable local fixture only.
    else:
        c.secret.unlink();c.leaf.rmdir()
        if kind=='symlink':c.leaf.symlink_to(c.tmp,target_is_directory=True)
        if kind=='regular':c.leaf.write_bytes(b'UNREAD')
    out=c.m.inspect_metadata(c.m.request(),owner=c.owner)
    assert out['reason']==reason
    assert out['state']==('UNAVAILABLE' if kind=='missing' else 'UNSAFE')
    assert len(c.opens)==len(c.prefixes)-1 and out['artifact_bytes_read']==0


def test_transport_failure_retains_unknown_claim_and_has_closed_error(control):
    c=control
    def broken(*a):raise OSError('PRIVATE_PROVIDER_DETAIL')
    c.owner._inert_transport=broken
    with pytest.raises(c.m.Refused) as e:c.m.inspect_metadata(c.m.request(),owner=c.owner)
    assert str(e.value)=='original_directory_observation_unconfirmed' and c.owner.claimed
    with pytest.raises(c.m.Refused):c.m.inspect_metadata(c.m.request(),owner=c.owner)
    assert c.opens==[]


@pytest.mark.parametrize('field,value',[('artifact_bytes_read',True),('permission_changed',True),('retry_authorized',True),('request_sha256','a'*64),('reason','SYMLINK')])
def test_consumer_rejects_forged_authority_or_predicate(control,field,value):
    c=control;raw=c.transport(c.owner.binding,c.m.request());out=json.loads(raw);out[field]=value
    with pytest.raises(c.m.Refused):c.m.validate_response(c.m.canonical(out),c.m.request())


def test_authorized_fixture_without_registered_carrier_is_still_unavailable(control):
    c=control
    c.owner.original_directory_metadata_transport=c.m.OriginalDirectoryOwner.original_directory_metadata_transport.__get__(c.owner)
    with pytest.raises(c.m.Refused,match='registration_required'):
        c.m.inspect_metadata(c.m.request(),owner=c.owner)
    assert not c.owner.claimed and c.opens==[]


def test_owner_exception_is_closed_before_any_metadata(control):
    c=control
    def denied(*a):raise OSError('PRIVATE_PERMISSION_DETAIL')
    c.owner.admit_original_directory_metadata=denied
    with pytest.raises(c.m.Refused) as error:c.m.inspect_metadata(c.m.request(),owner=c.owner)
    assert str(error.value)=='original_directory_owner_unavailable' and c.opens==[]


def _changed_info(info,**changes):
    names=('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_mtime_ns','st_ctime_ns')
    return SimpleNamespace(**{k:changes.get(k,getattr(info,k)) for k in names})


def test_foreign_directory_uid_is_metadata_not_permission_to_open(control):
    c=control;c.fault['kind']='uid'
    out=c.m.inspect_metadata(c.m.request(),owner=c.owner)
    assert out['reason']=='OWNER_MISMATCH' and out['directories'][0]['uid']==os.getuid()+1
    assert out['directories'][0]['component']=='RESULT_DIRECTORY'
    assert len(c.opens)==len(c.prefixes)-1 and out['artifact_files_opened']==0


@pytest.mark.parametrize('changed',['directory','ancestor'])
def test_named_metadata_rejoin_rejects_changed_identity(control,changed):
    c=control;c.fault['kind']=changed
    out=c.m.inspect_metadata(c.m.request(),owner=c.owner)
    assert out['state']=='UNAVAILABLE' and out['reason']=='DIRECTORY_CHANGED'
    assert out['directories']==[]


def test_caller_mutation_after_admission_cannot_retarget_detached_metadata(control):
    c=control;value=c.m.request();original_admit=c.owner.admit_original_directory_metadata
    def admitted(view,uid):
        result=original_admit(view,uid)
        value['host']='foreign';value['contract']['names']=['foreign-file']
        return result
    c.owner.admit_original_directory_metadata=admitted
    out=c.m.inspect_metadata(value,owner=c.owner)
    assert out['state']=='SAFE_AT_OBSERVATION' and len(c.opens)==len(c.prefixes)


def test_component_seals_actual_incumbent_dependencies_without_installing_admission(control):
    c=control
    meta=json.loads((MODULE.parent/'component.json').read_text())
    assert hashlib.sha256(MODULE.read_bytes()).hexdigest()==meta['new_module']['sha256']
    for name in meta['existing_dependency_sources']:
        loaded=Path(sys.modules[name.removesuffix('.py')].__file__)
        assert hashlib.sha256(loaded.read_bytes()).hexdigest()==meta['existing_dependency_sources'][name]
    assert meta['status']=='UNREGISTERED_DEFAULT_DENY_SOURCE_PROPOSAL'
    assert meta['registration_installed'] is meta['transport_or_cli_registered'] is meta['admission_issued'] is False


@pytest.mark.parametrize('binding',['foreign_host','bad_alias','unbound_account'])
def test_qualified_action_cannot_change_transport_account_or_host(control,binding):
    c=control;old=c.owner.binding
    c.owner.binding=c.m.OwnerTransportBinding(
        'ubuntu2' if binding=='foreign_host' else old.host,
        'other alias' if binding=='bad_alias' else old.ssh_alias,
        'not-a-proof' if binding=='unbound_account' else old.account_scope_sha256,old.remote_uid)
    with pytest.raises(c.m.Refused,match='account_unbound'):
        c.m.inspect_metadata(c.m.request(),owner=c.owner)
    assert c.opens==[] and c.owner.claimed


def test_consistent_foreign_invoking_uid_does_not_pass_account_binding(control):
    c=control
    def foreign(*args):
        out=json.loads(c.transport(*args))
        out['directories'][0]['uid']+=1;out['directories'][0]['invoking_uid']+=1
        return c.m.canonical(out)
    c.owner._inert_transport=foreign
    with pytest.raises(c.m.Refused,match='observation_unconfirmed'):
        c.m.inspect_metadata(c.m.request(),owner=c.owner)
    assert c.owner.claimed


@pytest.mark.parametrize('component',['ACCOUNT_HOME','LANES','EXT','RESULT_DIRECTORY'])
def test_first_failed_directory_matches_actual_incumbent_custody_predicate(control,component):
    c=control
    target={'ACCOUNT_HOME':c.home,'LANES':c.home/'lanes','EXT':c.home/'lanes/ext','RESULT_DIRECTORY':c.leaf}[component]
    target.chmod(0o775)  # Newly owned synthetic namespace only; never host setup.
    out=c.m.inspect_metadata(c.m.request(),owner=c.owner)
    assert out['state']=='UNSAFE' and out['reason']=='GROUP_OR_OTHER_WRITABLE'
    assert out['directories'][0]['component']==component
    assert out['artifact_files_opened']==0
    with pytest.raises(ValueError,match='directory_owner_or_mode'):c.guard()


def test_uid_predicate_matches_incumbent_directory_chain_without_chown(control):
    c=control;c.fault['kind']='uid'
    out=c.m.inspect_metadata(c.m.request(),owner=c.owner)
    assert out['reason']=='OWNER_MISMATCH'
    with pytest.raises(ValueError,match='directory_owner_or_mode'):c.guard()


def test_public_caller_cannot_supply_replacement_transport(control):
    c=control
    with pytest.raises(TypeError):
        c.m.inspect_metadata(c.m.request(),owner=c.owner,transport=lambda *a:b'')
    assert c.opens==[] and not c.owner.claimed


@pytest.mark.parametrize('fault',['initial_root_fstat','initial_child_fstat'])
def test_initial_fstat_failure_closes_every_owned_directory_fd(control,fault):
    c=control;c.fault['kind']=fault
    out=c.m.inspect_metadata(c.m.request(),owner=c.owner)
    assert out['state']=='UNAVAILABLE' and out['reason']=='FILESYSTEM_REFUSED'
    assert out['directories']==[] and out['artifact_files_opened']==out['artifact_bytes_read']==0
    assert c.outstanding==set(), 'initial fstat left a test-owned directory FD open'
