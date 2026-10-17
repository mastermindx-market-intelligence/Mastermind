"""Inactive original source composition; OS/physical authority remains fixture-only."""
import asyncio
import dataclasses
import json
import pytest
from control_plane import finite_initial_admission as initial
from control_plane import finite_initial_registration as registration
from control_plane import native_capacity_acquisition as acquisition
from control_plane import executive_runtime as rt
from control_plane.fabric_attended_routing import installed_control_placements
from scripts import executive_os_phase1c as service
from tests.test_finite_initial_transaction import setup,claim,snap
from tests.test_native_capacity_v2 import composed,reader,native,bound,enrolled,good_snapshot
from tests.test_installed_finite_control import finite_raw
from tests.test_executive_fabric_composition import root_stats


def test_actual_registration_is_offline_v2_and_never_migrates(composed,tmp_path):
    source,reader=composed;runtime=rt.Runtime.at(tmp_path/'registration')
    placement=installed_control_placements(finite_raw())[0]
    calls=[]
    worker=registration.register_initial(runtime,placement,source,lambda:calls.append('guard'))
    quota=runtime.workers.get_quota_class(initial.WORKER,initial.QUOTA)
    assert worker.status==quota.status==rt.WorkerStatus.OFFLINE
    assert quota.metadata['capacity_join']['capability_generation']==3
    assert quota.metadata['finite_initial_capacity']==initial.CLASSIFICATION
    assert len(calls)==3 and reader.requests==[]
    with pytest.raises(rt.StateConflict,match='absent identity'):
        registration.register_initial(runtime,placement,source,lambda:None)
    with runtime.store.read() as c:
        assert c.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]==0


def test_existing_v1_registration_is_never_adopted(composed,tmp_path):
    source,_=composed;runtime=rt.Runtime.at(tmp_path/'legacy')
    runtime.workers.register_worker(initial.WORKER,provider='minimax',account_label='legacy',
        worker_type='attended-fabric',status=rt.WorkerStatus.OFFLINE,
        quota_classes={initial.QUOTA:dict(metadata={'capacity_join':{'schema':'mastermind.executive_capacity_join/v1'}})})
    original=runtime.workers.get_worker(initial.WORKER)
    with pytest.raises(rt.StateConflict,match='absent identity'):
        registration.register_initial(runtime,installed_control_placements(finite_raw())[0],source,lambda:None)
    assert runtime.workers.get_worker(initial.WORKER)==original


def test_original_dispatch_replays_without_any_acquisition_or_live_origin(setup,composed,monkeypatch):
    s=setup;source,_=composed;lease=claim(s);s.operation._closed=True
    async def forbidden(_self):pytest.fail('replay attempted source acquisition')
    monkeypatch.setattr(acquisition.NativeCapacitySource,'acquire',forbidden)
    before=snap(s)
    replay=asyncio.run(initial.FiniteInitialAdmission(source).dispatch(s.runtime,s.job.job_id,s.command,lease_owner='local-supervisor'))
    assert replay.attempt.attempt_id==lease.attempt.attempt_id and not replay.claimed_now
    assert snap(s)==before


def test_real_acquisition_unknowns_refuse_before_claim(setup,composed):
    s=setup;source,reader=composed;before=snap(s)
    # The canonical fixture row and this actual source have intentionally
    # different host identity. Either unknown facts or that join must refuse.
    with pytest.raises(ValueError):
        asyncio.run(initial.FiniteInitialAdmission(source).dispatch(s.runtime,s.job.job_id,s.command,lease_owner='fixture'))
    assert len(reader.requests)==1 and snap(s)==before


def test_known_fixture_still_cannot_create_physical_authority(setup,composed,monkeypatch):
    s=setup;source,_=composed;before=snap(s)
    async def fixture(_self):
        assert not s.runtime.store._write_connections
        return s.p.evidence['provider_capacity']
    monkeypatch.setattr(acquisition.NativeCapacitySource,'acquire',fixture)
    with pytest.raises(initial.InitialPhysicalCompositionUnavailable) as exc:
        asyncio.run(initial.FiniteInitialAdmission(source).dispatch(s.runtime,s.job.job_id,s.command,lease_owner='fixture'))
    candidate=json.loads(exc.value.candidate_json)
    assert candidate['runtime_schema_version']==5 and not candidate['physical_caller_composed']
    assert candidate['job_id']==s.job.job_id and candidate['root_creation_command_id']==s.operation._command
    assert snap(s)==before


@pytest.mark.parametrize('fault',['none','extra','path','nonground','no-probe'])
def test_actual_control_config_accepts_only_fixed_optional_definition(fault):
    raw={'fabric_bindings_path':'/fixture/bindings','fabric_bindings_sha256':'a'*64,
        'fabric_attended_probe':{'worker_config_path':'/fixture/worker'},'coo_foreground_only':True,
        'native_capacity_v2':{'macro_release':'b'*40,'producer_sha256':'c'*64}}
    if fault=='none':
        assert service._validate_fabric_bridge_config(raw)
        return
    if fault=='extra':raw['native_capacity_v2']['available']=True
    if fault=='path':raw['native_capacity_v2']['macro_release']='../caller'
    if fault=='nonground':raw['coo_foreground_only']=False
    if fault=='no-probe':del raw['fabric_attended_probe']
    with pytest.raises(service.ServiceError):service._validate_fabric_bridge_config(raw)


def test_actual_startup_wires_same_source_to_registration_and_mixed_owner(composed,tmp_path,monkeypatch,root_stats):
    from types import SimpleNamespace
    from control_plane.fabric_attended_canary import AttendedControlProbeSource
    from control_plane import executive_worker_broker as broker
    from tests.test_ceo_submit_armed_composition import _raw,_write
    source,reader=composed
    raw=_raw(tmp_path);raw.update(finite_raw());raw['native_capacity_v2']=reader.raw['native_capacity_v2']
    monkeypatch.setattr(service,'_staged_fabric_binding_source',lambda _raw:source.bindings)
    raw=service.load_control_config(_write(tmp_path,raw))
    probe=AttendedControlProbeSource.from_startup(tmp_path/'control.json',raw,{'config_sha256':'a'*64})
    _,worker,attestation=source.probe.configuration(reader.physical)
    worker=dict(worker,run_root=str(tmp_path/'finite-runs'))
    monkeypatch.setattr(AttendedControlProbeSource,'configuration',lambda self,p:(raw,worker,attestation))
    captured={}
    monkeypatch.setattr(broker,'WorkerBrokerClient',lambda *a,**kw:object())
    monkeypatch.setattr(service,'activate_launchd_socket',lambda name:object())
    def holder(config,**kw):captured.update(kw);return SimpleNamespace(config=config)
    monkeypatch.setattr(service,'ExecutiveControlService',holder)
    service._service_from_config(raw,fabric_worker_binding_source=source.bindings,
        fabric_attended_probe_source=probe,attended_work_placements=installed_control_placements(raw))
    runtime=rt.Runtime.at(tmp_path/'wired')
    mixed=captured['supervisor_factory'](runtime)
    assert type(mixed._initial_admission) is initial.FiniteInitialAdmission
    assert mixed._initial_admission.source.probe is probe
    # Capture only the registration function at its external acquisition
    # boundary; assert the startup callback passes the same fixed source.
    def capture(rt_arg,placement,source_arg,guard):
        assert rt_arg is runtime and source_arg is mixed._initial_admission.source
        return 'original-registration-owner'
    monkeypatch.setattr(registration,'register_initial',capture)
    assert captured['attended_worker_registration'](runtime)=='original-registration-owner'
    assert reader.requests==[]
