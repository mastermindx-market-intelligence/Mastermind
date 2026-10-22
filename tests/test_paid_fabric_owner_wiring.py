"""Offline source checks; these fixtures do not authenticate a live owner."""
import asyncio
from copy import deepcopy
import dataclasses
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import paid_fabric_backend as backend
from control_plane import paid_fabric_wire as wire
from control_plane import paid_model_execution_contract as contract
from control_plane.fabric_control_start import launch_identity
from control_plane.worker_execution_contract import BinaryAttestation

ROOT=Path(__file__).parents[1]


def material():
    binary=dataclasses.asdict(BinaryAttestation(path='/usr/bin/python3',real_path='/usr/bin/python3',
        sha256='1'*64,size=100,device=1,inode=2,mode=0o100755,uid=0,gid=0,
        mtime_ns=123,version='3.12.3',team_identifier=None))
    source=dict(schema_version='mastermind.paid_worker_source/v1',worker_id='paid-worker',
        provider='glm',host_ref='ubuntu3',model='glm-5.3-flash',worker_uid=1000,
        worker_gid=1000,worker_user='runner',binary=binary,permission_profile_sha256='2'*64,
        execution_profile_digest='3'*64,service_source_sha256='4'*64,bridge_uid=501,
        socket_path='/var/run/mastermind-executive/fabric-glm-paid-01.sock',
        capture_root='/home/runner/lanes/ext/lanes',capacity_capability_id='paid-capacity')
    source['qualification']=dict(registry_key='ubuntu3',registry_sha256='8'*64,transport_alias='ubuntu3',
        host_env_path='/home/runner/lanes/ext/HOST_ENV.sh',host_env_sha256='9'*64,boot_id='boot-fixture',
        capture_identity=dict(device=1,inode=10,mode=0o40700,uid=1000,gid=1000),
        qualifier_source_manifest_sha256='a'*64,probe_sha256='b'*64,
        qualifier_sources_sha256={n:'c'*64 for n in ('host_pull.sh','host_pull_backend.py',
            'host_pull_probe.template','paid_host_qualification.py','remote_sub.sh')})
    source['host_ref']=contract.paid_host_reference('ubuntu3','ubuntu3')
    physical={**source,'schema_version':'mastermind.paid_fabric_host_binding/v1',
              'worker_source_config_digest':contract.digest(source)}
    del physical['capacity_capability_id']
    p=dict(binding=dict(root_id='JOB-root',job_id='JOB-child',attempt_id='ATT-1',
        effective_grant_digest='a'*64,commission_sha256='b'*64),
        physical_binding_sha256=contract.digest(physical),paid_physical_binding=physical,
        paid_source_config=source,paid_account='glm-account-1',paid_quota_class='paid-read',
        launch_spec=dict(worker_id='paid-worker',worker_user='runner',expected_worker_uid=1000,
            expected_worker_gid=1000,model='glm-5.3-flash',timeout_seconds=60,
            job_id='JOB-child',run_id='ATT-1',effective_grant_digest='a'*64,
            prompt='Exact sealed evidence 中文',authorities=['READ'],authority=None,
            allowed_artifact_paths=[],isolation_manifest_sha256='5'*64),
        paid_route=dict(provider='glm',host_ref=source['host_ref'],model='glm-5.3-flash',parent_job_id='JOB-root'),
        paid_input=dict(prompt='Exact sealed evidence 中文',result_schema={'type':'object'}),
        validation_commands=[])
    capsule={'test_data_only':'not-authority'}
    frame=dict(schema='mastermind.paid_model_owned_launch/v1',run_id='ATT-1',model='glm-5.3-flash',
        transport_host='ubuntu3',lease_id='lease-1',pid=1200,
        process_identity=dict(start_identity='5000',pgid=1200,session_id=1200,
            effective_uid=1000,effective_gid=1000,real_uid=1000,real_gid=1000,
            parent_pid=1100,boot_id='boot-fixture',device=1,inode=2,mode=0o100755,
            uid=0,gid=0,size=100,mtime_ns=123,ctime_ns=123,sha256='1'*64),
        observed_user='runner',launch_nonce='nonce-fixture',started_at='2026-10-22T20:00:00+00:00',
        python_path='/usr/bin/python3',python_version='3.12.3',source_manifest_sha256='6'*64,
        request_body_sha256=contract.descriptor(p)['request_body_sha256'],
        capsule_binding_sha256=contract.digest(capsule),capture_contract={'fixture':'closed-capture'},
        capture_paths={k:str(Path(source['capture_root'])/'ATT-1.paid'/v) for k,v in
            [('stdout_path','stdout'),('stderr_path','stderr'),('result_path','result.json')]})
    frame['host_context']={k:source['qualification'][k] for k in
        ('host_env_path','host_env_sha256','boot_id','capture_identity')}
    lease=dict(id='lease-1',orchestrator_id='JOB-root',pool='glm',account='glm-account-1',
               host='ubuntu3',model='glm-5.3-flash',pid=800)
    # Pure projection arguments, explicitly not a forged Control authority.
    projection=SimpleNamespace(fence_generation=1,pin_version=2,pin_identity_sha256=launch_identity(p))
    return p,frame,capsule,lease,projection


def test_actual_wire_joins_remote_owned_image_and_exact_control_pin():
    p,frame,capsule,lease,projection=material()
    result=wire.paid_start_from_owned_launch(p,frame,capsule=capsule,lease=lease,
        controller=dict(process_start_identity='controller-fixture',boot_id='m2-fixture'),authority=projection)
    ref,att=wire.validate_paid_start_wire(result,p)
    assert ref.host_ref==contract.paid_host_reference('ubuntu3','ubuntu3') and ref.binary.sha256==p['paid_physical_binding']['binary']['sha256']
    assert att['evidence']['pin_identity_sha256']==launch_identity(p)
    assert att['evidence']['source_manifest_sha256']=='6'*64
    assert 'provider_home' not in att and 'provider_session_id' not in ref.to_dict()
    changed=deepcopy(result);changed['process_ref']['host_ref']='ubuntu2'
    with pytest.raises(wire.PaidWireRefused):wire.validate_paid_start_wire(changed,p)


@pytest.mark.parametrize('path,value',[(('transport_host',),'ubuntu2'),(('lease_id',),'other'),
    (('process_identity','sha256'),'7'*64),(('process_identity','effective_uid'),501),
    (('python_path',),'/unqualified/python'),(('capture_paths','result_path'),'/tmp/other')])
def test_owned_launch_mismatches_refuse(path,value):
    p,frame,capsule,lease,projection=material()
    target=frame
    for key in path[:-1]:target=target[key]
    target[path[-1]]=value
    with pytest.raises(wire.PaidWireRefused):
        wire.paid_start_from_owned_launch(p,frame,capsule=capsule,lease=lease,
            controller=dict(process_start_identity='controller',boot_id='boot'),authority=projection)


def test_constructible_startup_and_context_do_not_construct_production_owner(tmp_path):
    startup=backend._QualifiedPaidStartup(tmp_path,tmp_path,tmp_path,tmp_path,501,{})
    with pytest.raises(backend.PaidOwnerRefused):backend.CanonicalPaidBackend(startup,object())


def test_original_sealed_input_closes_pre_log_spawn_absence(tmp_path):
    owner=object.__new__(backend.CanonicalPaidBackend)
    owner._startup=SimpleNamespace(log_dir=tmp_path);owner._operations={}
    assert not owner._occupied('ATT-1')
    (tmp_path/'.ATT-1.canonical-input.original').write_bytes(b'sealed original input')
    assert owner._occupied('ATT-1')
    assert not owner._occupied('ATT-2')


def test_paid_state_wrapper_denies_unqualified_environment_before_import(monkeypatch):
    path=ROOT/'ops/native_fabric/quota_continuity/candidate/paid_incumbent_state.py'
    spec=importlib.util.spec_from_file_location('state_fixture',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.delenv('FABRIC_CANONICAL_PAID_MODE',raising=False)
    monkeypatch.setattr(module.importlib,'import_module',lambda _:pytest.fail('import before gate'))
    with pytest.raises(ValueError):module.configure('lease_broker')
    with pytest.raises(ValueError):module.configure('pool_ledger')


def test_host_reference_is_versioned_data_and_transport_mapping_is_required():
    p,*_=material()
    ref=contract.paid_host_reference('ubuntu3','ubuntu3')
    assert ref.startswith('host-') and len(ref)==69
    assert ref==contract.paid_host_reference('ubuntu3','ubuntu3')
    changed=deepcopy(p)
    changed['paid_source_config']['qualification']['registry_key']='ubuntu2'
    changed['paid_physical_binding']['qualification']['registry_key']='ubuntu2'
    changed['paid_physical_binding']['worker_source_config_digest']=contract.digest(changed['paid_source_config'])
    changed['physical_binding_sha256']=contract.digest(changed['paid_physical_binding'])
    with pytest.raises(wire.PaidWireRefused):wire.require_paid_physical(changed)


def test_root_source_projection_mutation_is_detected(monkeypatch,tmp_path):
    from control_plane import executive_paid_fabric_composition as comp
    p,*_=material()
    document=dict(schema_version=comp.PAID_BINDINGS_SCHEMA,bindings=[dict(
        physical_binding=p['paid_physical_binding'],source_config=p['paid_source_config'],quota_class='paid-read')])
    raw=contract.canonical(document);sha=hashlib.sha256(raw).hexdigest()
    # Synthetic root-read DATA fixture, never an OS/root qualification claim.
    monkeypatch.setattr(comp,'_read_pinned',lambda path,digest:(raw,('same-original-file',)))
    source=comp.PaidBindingSource.from_path(tmp_path/'bindings.json',sha)
    physical=source.bindings[0]
    assert source(physical.host_ref,physical.worker_id)==physical
    physical.binary['sha256']='f'*64
    with pytest.raises(comp.FabricCompositionError):source(physical.host_ref,physical.worker_id)


def test_alias_labels_cannot_duplicate_same_qualified_boot_allowance(monkeypatch,tmp_path):
    from control_plane import executive_paid_fabric_composition as comp
    p,*_=material()
    other=deepcopy(p)
    other['paid_source_config']['worker_id']='second-worker'
    other['paid_source_config']['qualification']['registry_key']='alias3'
    other['paid_source_config']['qualification']['transport_alias']='alias3'
    other['paid_source_config']['host_ref']=contract.paid_host_reference('alias3','alias3')
    second={**other['paid_source_config'],'schema_version':'mastermind.paid_fabric_host_binding/v1',
            'worker_source_config_digest':contract.digest(other['paid_source_config'])}
    del second['capacity_capability_id']
    doc=dict(schema_version=comp.PAID_BINDINGS_SCHEMA,bindings=[
        dict(physical_binding=p['paid_physical_binding'],source_config=p['paid_source_config'],quota_class='paid-read'),
        dict(physical_binding=second,source_config=other['paid_source_config'],quota_class='paid-read')])
    raw=contract.canonical(doc)
    monkeypatch.setattr(comp,'_read_pinned',lambda path,digest:(raw,('fixture',)))
    with pytest.raises(comp.FabricCompositionError,match='physical instance duplicated'):
        comp.PaidBindingSource.from_path(tmp_path/'bindings.json',hashlib.sha256(raw).hexdigest())


def test_retained_collection_record_is_complete_above_old_256k_limit(tmp_path):
    import threading
    owner=object.__new__(backend.CanonicalPaidBackend)
    owner._gateway=SimpleNamespace(_signing_key=b'offline-test-key')
    path=tmp_path/'original.log'
    fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_APPEND,0o600)
    operation=SimpleNamespace(log_fd=fd,lock=threading.Lock())
    try:
        value={'stdout_utf8':'a'*300000}
        owner._journal(operation,'collection',value)
        raw=path.read_bytes()
        assert raw.startswith(backend._JOURNAL) and raw.endswith(b'\n')
        assert json.loads(raw[len(backend._JOURNAL):])['value']==value
        os.ftruncate(fd,backend._MAX_LOG)
        with pytest.raises(backend.PaidOwnerRefused):owner._journal(operation,'collection',value)
        assert os.fstat(fd).st_size==backend._MAX_LOG
    finally:os.close(fd)


def test_status_original_log_blocks_restart_refusal_and_same_id_replay(tmp_path,monkeypatch):
    import threading
    from control_plane import paid_fabric_bootstrap as helper
    owner=object.__new__(backend.CanonicalPaidBackend)
    owner._startup=SimpleNamespace(log_dir=tmp_path)
    import threading
    owner._lock=threading.RLock();owner._stop_fence=None;owner._metadata_active=0
    owner._gateway=SimpleNamespace(_signing_key=b'original-incumbent-key')
    owner.require_capacity_scope=lambda *args: None  # explicit source-only IO fixture seam
    calls=[]
    refusal=helper._result(helper.STATE_AUTH_REFUSED,helper.REASON_AUTH_REFUSED,'selected',1,
                           previous_reading_retained=True)
    monkeypatch.setattr(helper,'bootstrap_paid_account',lambda *args,**kw:(calls.append(1) or refusal))
    scope=dict(worker_id='worker',quota_class='paid-read',account_label='selected',provider='glm',
               transport_host='ubuntu2',model='glm-5.3-flash',source_sha256='a'*64,physical_sha256='b'*64)
    assert owner._quota_bootstrap_owned('status-original',scope,allow_start=True)==refusal
    assert owner._quota_bootstrap_owned('status-original',scope,allow_start=False)==refusal
    with pytest.raises(backend.PaidOwnerRefused):owner._quota_bootstrap_owned('status-replacement',scope,allow_start=True)
    assert calls==[1]
    owner._gateway._signing_key=b'restarted-incumbent-key'
    with pytest.raises(backend.PaidOwnerRefused):owner._quota_bootstrap_owned('status-original',scope,allow_start=False)
    assert calls==[1]
    other=dict(scope,account_label='another')
    with pytest.raises(FileNotFoundError):owner._quota_bootstrap_owned('status-missing',other,allow_start=False)
    assert len(list(tmp_path.glob('paid-quota-*.log')))==1 and calls==[1]


def test_status_lost_terminal_never_reenters_provider(tmp_path,monkeypatch):
    from control_plane import paid_fabric_bootstrap as helper
    owner=object.__new__(backend.CanonicalPaidBackend)
    owner._startup=SimpleNamespace(log_dir=tmp_path)
    import threading
    owner._lock=threading.RLock();owner._stop_fence=None;owner._metadata_active=0
    owner._gateway=SimpleNamespace(_signing_key=b'original-key')
    owner.require_capacity_scope=lambda *args:None
    calls=[]
    def lost(*args,**kw):calls.append(1);raise RuntimeError('synthetic lost response')
    monkeypatch.setattr(helper,'bootstrap_paid_account',lost)
    scope=dict(worker_id='worker',quota_class='paid-read',account_label='selected',provider='glm',
               transport_host='ubuntu2',model='glm-5.3-flash',source_sha256='a'*64,physical_sha256='b'*64)
    with pytest.raises(RuntimeError):owner._quota_bootstrap_owned('status-original',scope,allow_start=True)
    for mode in (False,True):
        with pytest.raises(backend.PaidOwnerRefused):owner._quota_bootstrap_owned('status-original',scope,allow_start=mode)
    assert calls==[1]
