"""Finite probe joins with explicit fixture issuers; no installed host probe."""
import asyncio
import copy
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import fabric_attended_canary as probe
from control_plane import foreground_operation
from control_plane.executive_worker_broker import BrokerStateError
from scripts import executive_os_phase1c as control
from scripts import executive_os_phase1c_worker as worker
from tests.test_executive_fabric_adapter import _fixture
from tests.test_executive_fabric_composition import root_stats
from tests.test_executive_fabric_bridge_broker import broker, start_payload, envelope, execute


def finite_definition():
    value = dict(schema_version=worker.SUBSCRIPTION_CONFIG_SCHEMA_VERSION,
        control_uid=450, control_gid=450, worker_uid=460, worker_gid=460,
        allowed_supplementary_gids=[], worker_user='finite', worker_id='finite-1',
        workspace_root='/srv/executive/workers/finite-1/jobs/workspaces', run_root='/srv/executive/workers/finite-1/jobs/runs',
        provider_home='/srv/executive/workers/finite-1/provider-home',
        claude_binary='/opt/bin/claude', claude_attestation_receipt='/etc/finite/binary.json',
        claude_attestation_sha256='a'*64, allowed_claude_versions=['2.1.0'],
        launchd_socket_name='Finite', uid_sweep_receipt='/etc/finite/sweep.json',
        require_secret_canary=True, operator_harness_armed=False, harness_binding_id=probe.BINDING,
        subscription_realm_enrollment={'generation':1,'binding_id':probe.BINDING},
        attended_secret_canary=copy.deepcopy(probe.PRESET))
    return value


def test_finite_closed_definition_loads_but_does_not_arm_service(tmp_path):
    value=finite_definition(); path=tmp_path/'worker.json'
    path.write_text(json.dumps(value));path.chmod(0o600)
    loaded=worker._load_config(path,require_root_owner=False)
    assert loaded==value
    with pytest.raises(worker.WorkerConfigError,match='existing Fabric bridge'):
        worker._assert_service_activation_allowed(loaded)


@pytest.mark.parametrize('change',[
    {'attended_secret_canary':{'environment_probe':'linux','schema_version':probe.PRESET['schema_version']}},
    {'attended_secret_canary':{**probe.PRESET,'shell':'true'}},
    {'control_gid':460}, {'claude_attestation_sha256':'wrong'},
    {'operator_harness_armed':True}, {'subscription_realm_enrollment':None},
    {'codex_binary':'/opt/bin/codex'},
])
def test_bad_definition_refuses(tmp_path,change):
    value={**finite_definition(),**change};path=tmp_path/'worker.json'
    path.write_text(json.dumps(value));path.chmod(0o600)
    with pytest.raises(worker.WorkerConfigError):worker._load_config(path,require_root_owner=False)


@pytest.mark.parametrize('stanza',[{}, {'worker_config_path':'relative'},
    {'worker_config_path':'/safe/../other'}, {'worker_config_path':'/safe/file','callback':'other'}])
def test_control_reference_is_one_closed_data_path(stanza):
    with pytest.raises(control.ServiceError):
        control._validate_fabric_bridge_config(dict(fabric_bridge_armed=False,
            fabric_bindings_path='/etc/fabric.json',fabric_bindings_sha256='a'*64,
            fabric_attended_probe=stanza))


def test_missing_coupled_v2_input_and_unsupported_platform_refuse(monkeypatch):
    with pytest.raises(control.ServiceError,match='coupled'):
        control._validate_canary_envelope({},raw={},control_attestation={},attended_config=object())
    monkeypatch.setattr(probe.sys,'platform','linux')
    with pytest.raises(BrokerStateError):probe.produce(object(),{})
    with pytest.raises(BrokerStateError):probe.AttendedControlProbeSource.from_startup(Path('/unused'), {}, {'config_sha256':'a'*64}).snapshot(None,None)


def request():
    p=start_payload();p.pop('validation_commands');p['run_id']=p['binding']['attempt_id']
    p['control_environment_attestation']=dict.fromkeys(worker._CONTROL_ENV_ATTESTATION_FIELDS, 'fixture')
    return p


def test_broker_probe_has_no_start_or_status_preflight(tmp_path,monkeypatch):
    calls=[]
    class Backend:
        async def execute(self,op,p):
            calls.append(op)
            return dict(adapter_id='attended-fabric',binding=p['binding'],
                physical_binding_sha256=p['physical_binding_sha256'],
                probe_request_sha256=probe.digest(p),envelope={'fixture':True})
    b=broker(tmp_path,monkeypatch,Backend());p=request()
    response=execute(b,envelope(probe.OPERATION,p))
    assert response['ok'] and calls==[probe.OPERATION]
    assert not (probe.OPERATION in b.config.validation_commands)


@pytest.mark.parametrize('fault',['foreign_run','extra_path','wrong_digest'])
def test_broker_probe_refuses_unbound_request_or_reply(tmp_path,monkeypatch,fault):
    class Backend:
        async def execute(self,op,p):
            return dict(adapter_id='attended-fabric',binding=p['binding'],
                physical_binding_sha256=p['physical_binding_sha256'],
                probe_request_sha256='0'*64,envelope={})
    b=broker(tmp_path,monkeypatch,Backend());p=request()
    if fault=='foreign_run':p['run_id']='other'
    if fault=='extra_path':p['credential_path']='/other'
    from control_plane.executive_fabric_bridge_broker import BridgeProtocolError
    with pytest.raises(BridgeProtocolError):execute(b,envelope(probe.OPERATION,p))


def adapter_case(tmp_path,monkeypatch,during=None):
    class Client:
        calls=[]
        async def request(self,op,p,**kw):
            self.calls.append(op)
            if during:during(self)
            return dict(adapter_id='attended-fabric',binding=p['binding'],
                physical_binding_sha256=p['physical_binding_sha256'],
                probe_request_sha256=probe.digest(p),envelope={'fixture':'v2'})
    from control_plane import fabric_attended_assignment
    monkeypatch.setattr(fabric_attended_assignment, 'prepare_assignment', lambda spec, worker, job: (spec, {
        'source_workspace':str(spec.workspace_path), 'input_root':str(Path(spec.run_dir)/'input')}))
    client=Client();rt,job,lease,a,s,p=_fixture(tmp_path,monkeypatch,client)
    original_get=rt.jobs.get_job
    monkeypatch.setattr(rt.jobs,'get_job',lambda ident:dataclasses.replace(original_get(ident),
        constraints={**job.constraints,'attended_route':{'fixture':'canonical route validated separately'}}))
    a._attended_probe_source=probe.AttendedControlProbeSource.from_startup(Path('/fixture/control'), {}, {'config_sha256':'a'*64})
    monkeypatch.setattr(probe.AttendedControlProbeSource,'snapshot',lambda self,physical,spec:
        ({}, {}, {'fixture':'current attestation'}, SimpleNamespace(spec=spec)))
    verdict={'fixture':'new-v2-verdict'}
    monkeypatch.setattr(probe.AttendedControlProbeSource,'validate',lambda self,snap,result:verdict)
    foreground=SimpleNamespace(_current_claim=lambda *args:None)
    monkeypatch.setattr(foreground_operation,'current_foreground_operation',lambda:foreground)
    client.runtime=rt;client.lease=lease;client.adapter=a
    client.foreground=foreground
    return client,rt,job,lease,a,s,p,verdict


def test_adapter_enriches_original_spec_without_pin_or_start(tmp_path,monkeypatch):
    c,rt,job,lease,a,s,p,verdict=adapter_case(tmp_path,monkeypatch)
    final=asyncio.run(a.prepare_attended_launch_spec(s,lease=lease))
    assert dataclasses.replace(final,secret_canary_verdict=s.secret_canary_verdict)==s
    assert final.secret_canary_verdict==verdict and final.effective_grant_digest==s.effective_grant_digest
    assert c.calls==[probe.OPERATION] and not a._bound and not a._leases
    assert not rt.attempts.get_attempt(s.run_id).launch_metadata


@pytest.mark.parametrize('fault',['fence','foreground','definition'])
def test_drift_during_probe_refuses_before_pin(tmp_path,monkeypatch,fault):
    def during(c):
        if fault=='fence':
            c.runtime.attempts.adopt_attempt(c.lease.attempt.attempt_id,
                expected_fence_generation=c.lease.attempt.fence_generation,lease_owner='successor')
        if fault=='foreground':
            c.foreground._current_claim=lambda *args:(_ for _ in ()).throw(
                foreground_operation.ForegroundOperationClosed())
        if fault=='definition':
            monkeypatch.setattr(probe.AttendedControlProbeSource,'snapshot',
                lambda *args:({}, {}, {'fixture':'changed'}, SimpleNamespace(spec=args[-1])))
    c,rt,job,lease,a,s,p,_=adapter_case(tmp_path,monkeypatch,during)
    with pytest.raises(Exception):asyncio.run(a.prepare_attended_launch_spec(s,lease=lease))
    assert c.calls==[probe.OPERATION] and not a._bound and not a._leases
    assert not rt.attempts.get_attempt(s.run_id).launch_metadata


def test_legacy_route_never_requests_probe(tmp_path,monkeypatch):
    class Client:
        async def request(self,*args,**kw):pytest.fail('legacy route must not request a probe')
    _,_,lease,a,s,_=_fixture(tmp_path,monkeypatch,Client())
    assert asyncio.run(a.prepare_attended_launch_spec(s,lease=lease)) is s


def test_transport_classifies_probe_as_observation():
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
    from control_plane.fabric_remote_transport import FABRIC_OPERATIONS
    from ops.executive_os.remote_worker_gateway_config import FABRIC_ALLOWED_OPERATIONS
    assert probe.OPERATION in FABRIC_OPERATIONS & FABRIC_ALLOWED_OPERATIONS
    assert RemoteWorkerBrokerClient._operation_is_observational(probe.OPERATION,{})


@pytest.mark.parametrize('fault', ['definition', 'config_digest', 'attestation'])
def test_current_matching_definition_cannot_replace_original_startup(tmp_path, monkeypatch, fault):
    raw={'fabric_attended_probe':{'worker_config_path':'/fixture/worker'},
         'control_environment_attestation_path':'/fixture/attestation', 'proof_base_sha':'a'*40}
    att={'config_sha256':'b'*64, 'fixture_identity':'original'}
    source=probe.AttendedControlProbeSource.from_startup(tmp_path/'control.json', raw, att)
    current=copy.deepcopy(raw); now=copy.deepcopy(att)
    if fault=='definition': current['other']='replacement'
    if fault=='config_digest': now['config_sha256']='c'*64
    if fault=='attestation': now['fixture_identity']='replacement'
    monkeypatch.setattr(probe.sys,'platform','darwin')
    monkeypatch.setattr(control,'load_control_config',lambda path:current)
    monkeypatch.setattr(control,'_load_control_environment_attestation',lambda *a,**k:now)
    monkeypatch.setattr(probe,'definition',lambda *a:{})
    monkeypatch.setattr(probe,'binding',lambda *a:pytest.fail('changed startup must refuse before binding'))
    with pytest.raises(BrokerStateError): source.snapshot(None,None)


def test_injected_source_must_belong_to_service_loaded_definition(tmp_path):
    raw={'fabric_bridge_armed':False}
    source=probe.AttendedControlProbeSource.from_startup(tmp_path/'control', raw, {'config_sha256':'a'*64})
    with pytest.raises(BrokerStateError):
        control._service_from_config({**raw, 'fixture':'other'},fabric_attended_probe_source=source)


def test_real_factory_v2_helper_and_coupled_validator_compose(tmp_path,monkeypatch):
    """Fixture enrollment/environment issuer; real harmless open/close denials."""
    import os
    from tests.test_executive_boot_autonomy_canary import _fixture as boot_fixture
    from tests.test_fabric_attended_secret_canary import inputs
    from control_plane import executive_canary as canary, codex_provider_realm as realm
    from control_plane import executive_worker_broker as wire
    # Explicit Darwin environment fixture; filesystem denials remain real.
    # The separate unsupported-platform test preserves Linux refusal.
    # Do not mutate shared sys.platform: Linux CI must retain its native ACL path.
    monkeypatch.setattr(probe,'sys',SimpleNamespace(platform='darwin'))
    release,host,raw,att=boot_fixture(tmp_path)
    uid,gid=os.getuid(),os.getgid()
    assert uid > 0
    raw.update(worker_uid=uid,worker_gid=gid,control_uid=uid+1,control_gid=gid+1,
        attended_secret_canary=probe.PRESET)
    for key,name in [('workspace_root','workspaces'),('run_root','runs')]:
        path=host/'workers'/raw['worker_id']/'jobs'/name;path.mkdir(parents=True)
        raw[key]=str(path)
    att['process_identity'].update(effective_uid=uid+1,real_uid=uid+1,effective_gid=gid+1,real_gid=gid+1)
    home=Path(raw['provider_home']);home.chmod(0o700)
    credential=home/'provider-credential';credential.write_bytes(b'harmless-test-only');credential.chmod(0o600)
    _,args=inputs()
    spec=dataclasses.replace(args['spec'],worker_id=raw['worker_id'],expected_worker_uid=uid,
        expected_worker_gid=gid,model='fixture-model')
    physical=SimpleNamespace(worker_source_config_digest='a'*64,digest='b'*64,
        worker_id=raw['worker_id'],worker_uid=uid,worker_gid=gid,model=spec.model,
        provider_home=str(home),provider='minimax')
    owner=realm.SubscriptionRealmOwner(tmp_path/'fixture-config','a'*64,realm._SUBSCRIPTION_REALM_OWNER_SEAL)
    observation={'realm_config_sha256':'a'*64,'worker_id':spec.worker_id,
        'binding_id':probe.BINDING,'control_uid':uid+1}
    monkeypatch.setattr(realm.SubscriptionRealmOwner,'observe',lambda self:dict(observation))
    monkeypatch.setattr(realm,'_native_read_config',lambda *a:dict(raw))
    monkeypatch.setattr(probe,'definition',lambda *a:dict(raw))
    monkeypatch.setattr(wire,'_launch_spec_from_wire',lambda *a:spec)
    monkeypatch.setattr(worker,'_ROOT',release)
    expected=probe.probe_config(raw,release_sha=release.name,probe_sha256='c'*64,control_gid=gid+1)
    protected=[expected.administrative_checkout_sentinel,*canary._database_paths(expected.executive_database),
        expected.other_worker_home_sentinel,expected.forbidden_production_sentinel]
    for path in protected:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'harmless-denied-test');path.chmod(0)
    def environment(argv):
        assert str(release/'scripts/executive_os_phase1c_env_probe.py') in argv
        identity=att['process_identity']
        return dict(schema_version='mastermind.executive_control_env_probe/v1',passed=True,
            control_process_identity=identity,worker_principal=dict(real_uid=uid,effective_uid=uid,real_gid=gid,effective_gid=gid),
            config_sha256=att['config_sha256'],release_manifest_sha256=att['release_manifest_sha256'],
            sentinel_value_sha256=att['sentinel_value_sha256'],process_identity_sha256=probe.digest(identity),
            checks=dict(launchctl='DENIED',ps='DENIED',kern_procargs2='DENIED'))
    actual_factory=worker._build_autonomy_canary_factory
    monkeypatch.setattr(worker,'_build_autonomy_canary_factory',lambda *a,**kw:
        actual_factory(*a,**kw,environment_probe_runner=environment))
    resources=SimpleNamespace(credential_realm_owner=owner,physical=physical,preparation={'policy':{}})
    packet=dict(physical_binding_sha256=physical.digest,launch_spec={},
        control_environment_attestation=att,binding={'fixture':'original-assignment'})
    response=probe.produce(resources,packet)
    assert response['probe_request_sha256']==probe.digest(packet)
    verdict=response['envelope']['secret_canary']
    assert verdict['schema_version']=='mastermind.executive_secret_canary/v2'
    assert verdict['realm_binding']['run_id']==spec.run_id
    assert verdict['realm_binding']['physical_binding_sha256']==physical.digest
    assert all(value=='DENIED' for value in verdict['checks'].values())
    # Original Control source validates the very same produced bytes.
    source=probe.AttendedControlProbeSource.from_startup(tmp_path/'control',{},att)
    control_raw=dict(raw,runtime_root=str(host/'control/db'),
        proof_source_repository=str(host/'control/admin-checkout'/release.name),worker_provider_home=str(home))
    assert source.validate((control_raw,raw,att,probe.binding(spec,physical)),response)==verdict


def test_cancelled_probe_waiter_does_not_release_inflight_owner(tmp_path,monkeypatch):
    import threading
    from integrations.session_bridge.bound_launch_capture.fabric_attended_backend import _FixedOwnerResources,_SingleAssignmentComposition,AttendedBackendRefused
    entered=threading.Event();finish=threading.Event()
    def producer(*args):
        entered.set()
        assert finish.wait(5)
        return {'fixture':'completed'}
    monkeypatch.setattr(probe,'produce',producer)
    resources=_FixedOwnerResources({},None,None,'root','parent',tmp_path)
    owner=_SingleAssignmentComposition(resources)
    async def exercise():
        first=asyncio.create_task(owner.execute(probe.OPERATION,{}))
        assert await asyncio.to_thread(entered.wait,2)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):await first
        assert owner._probe_busy and owner._probe_task is not None
        with pytest.raises(AttendedBackendRefused):await owner.execute(probe.OPERATION,{})
        assert owner._backend is None and owner._attempted is False
        finish.set()
        await owner._probe_task
        await asyncio.sleep(0)
        assert not owner._probe_busy and owner._probe_task is None
    try:asyncio.run(exercise())
    finally:finish.set()


@pytest.mark.parametrize('stale_receipt',[False,True])
def test_supervisor_retains_final_probe_in_start_pin_and_recovery(tmp_path,monkeypatch,stale_receipt):
    """Real commission/grant/SQLite/Supervisor; inert profile, provenance and RPC issuers."""
    import hashlib
    import os
    import pwd
    from tests.test_executive_supervisor import _strict_v2_root_with_commission
    from tests.test_executive_fabric_adapter import physical as fixture_physical
    from tests.test_executive_fabric_bridge_broker import start_result
    from tests.test_fabric_attended_secret_canary import inputs
    from control_plane import executive_fabric_adapter as adapter_module, fabric_attended_routing
    from control_plane.executive_supervisor import ExecutiveSupervisor,SupervisorError,CleanupPolicy
    from control_plane.worker_execution_contract import OrchestrationLaunchSpec,WorkerRecoveryBinding
    from control_plane.executive_runtime import REMOTE_LAUNCH_IDENTITY_KEY
    from control_plane.executive_worker_broker import _launch_spec_to_json
    rt,root,workspace,content=_strict_v2_root_with_commission(tmp_path)
    uid,gid=os.getuid(),os.getgid(); username=pwd.getpwuid(uid).pw_name
    rt.workers.register_worker('worker-cycle',provider='codex',account_label='fixture-only',
        worker_type='fixture',capabilities=['read'],quota_classes={'default':{
        'provider':'codex','capabilities':['read'],'cost_class':'small'}})
    job=rt.jobs.create_cycle_planner(root.job_id,command_id=f'coo-cycle:{root.job_id}:create-planner:0')
    original_get=rt.jobs.get_job
    monkeypatch.setattr(rt.jobs,'get_job',lambda ident:dataclasses.replace(original_get(ident),
        constraints={**original_get(ident).constraints,'attended_route':{'fixture':'profile'}}))
    physical=dataclasses.replace(fixture_physical(),worker_id='worker-cycle',provider='minimax',
        worker_uid=uid,worker_gid=gid,provider_home=str(tmp_path/'realm'))
    source=probe.AttendedControlProbeSource.from_startup(tmp_path/'fixture-control',{}, {'config_sha256':'a'*64})
    verdict={}
    finite_root=tmp_path/'host/workers/worker-cycle'
    workspaces=finite_root/'jobs/workspaces';runs=finite_root/'jobs/runs'
    for path in (workspaces,runs):path.mkdir(parents=True,mode=0o710)
    worker_raw=dict(worker_id='worker-cycle', worker_uid=uid, worker_gid=gid, control_uid=uid,
        provider_home=str(finite_root/'provider-home'), workspace_root=str(workspaces), run_root=str(runs))
    def snapshot(self,host,spec):
        # Fixture definition issuer supplies the actual remote principal. The
        # adapter must carry this same spec through START and durable recovery.
        bound=dataclasses.replace(spec,worker_user=username,shared_run_gid=gid)
        return {},worker_raw, {'fixture':'environment'},probe.binding(bound,host)
    def validate(self,snap,response):
        return response['envelope']['secret_canary']
    monkeypatch.setattr(probe.AttendedControlProbeSource,'snapshot',snapshot)
    monkeypatch.setattr(probe.AttendedControlProbeSource,'validate',validate)
    foreground=SimpleNamespace(_current_claim=lambda *a:None)
    monkeypatch.setattr(foreground_operation,'current_foreground_operation',lambda:foreground)
    monkeypatch.setattr(foreground_operation,'_current_foreground_operation_or_none',lambda:None)
    monkeypatch.setattr(fabric_attended_routing,'attended_launch_model',lambda *a:'fixture-model')
    calls=[];captured={}
    class Client:
        async def request(self,op,p,**kw):
            calls.append(op)
            if op==probe.OPERATION:
                value,_=inputs();value['realm_binding']=dict(
                    execution_profile_id=probe.PROFILE,harness_binding_id=probe.BINDING,
                    physical_binding_sha256=physical.digest,provider_home=physical.provider_home,
                    run_id=p['launch_spec']['run_id'],job_id=p['launch_spec']['job_id'],worker_id='worker-cycle')
                verdict.update(value)
                return dict(adapter_id='attended-fabric',binding=p['binding'],
                    physical_binding_sha256=physical.digest,probe_request_sha256=probe.digest(p),
                    envelope={'secret_canary':value})
            assert op=='start'
            payload={k:v for k,v in p.items() if k!='control_start'}
            captured.update(copy.deepcopy(payload))
            response=start_result(payload);s=p['launch_spec'];r=response['process_ref'];a=response['launch_attestation']
            response['physical_binding_sha256']=physical.digest
            r.update(run_id=s['run_id'],base_sha=s['expected_base_sha'],effective_uid=uid,real_uid=uid,effective_gid=gid,real_gid=gid)
            for key,name in [('stdout_path','stdout'),('stderr_path','stderr'),('result_path','result')]:r[key]=s['run_dir']+'/'+name
            a.update(expected_base_sha=s['expected_base_sha'],observed_base_sha=s['expected_base_sha'],
                isolation_manifest_sha256=s['isolation_manifest_sha256'],secret_canary_verdict=({'passed':True} if stale_receipt else s['secret_canary_verdict']))
            a['workspace_identity'].update(uid=uid,gid=gid)
            a['provider_home_identity'].update(path=s['run_dir']+'/home',uid=uid,gid=gid)
            a['process_identity'].update(effective_uid=uid,real_uid=uid,effective_gid=gid,real_gid=gid)
            a['worker_identity'].update(requested_user=username,observed_user=username,expected_uid=uid,expected_gid=gid,effective_uid=uid,real_uid=uid,effective_gid=gid,real_gid=gid)
            return response
    adapter=adapter_module.AttendedFabricWorkerAdapter(rt,lambda *a:physical,
        client_factory=lambda *a:Client(),attended_probe_source=source)
    def resolve(spec,*,launch,control_recovery=None):
        attempt=rt.attempts.get_attempt(spec.run_id)
        payload=dict(binding=dict(root_id=root.job_id,job_id=spec.job_id,attempt_id=spec.run_id,
            effective_grant_digest=attempt.effective_grant_digest,commission_sha256=hashlib.sha256(content).hexdigest()),
            physical_binding_sha256=physical.digest,launch_spec=_launch_spec_to_json(spec),validation_commands=[])
        context=control_recovery or adapter._control_recovery.get(spec.run_id)
        if context is not None:payload['control_recovery']=dict(context)
        return attempt,physical,payload
    monkeypatch.setattr(adapter,'_resolve',resolve)
    supervisor=ExecutiveSupervisor(rt,adapter,runs_root=runs,
        isolation_roots=(tmp_path/'workspaces',runs),worker_uid=uid,worker_gid=gid,worker_user='control-only',shared_run_gid=gid,
        require_complete_launch_attestation=True,cleanup_policy=CleanupPolicy.FABRIC_PROCESS_GROUP,
        process_controller=adapter,instance_id='fixture-supervisor')
    # Profile admission and source provenance are separate fixture issuers.
    monkeypatch.setattr(supervisor,'_validate_execution_profile',lambda *a:None)
    if stale_receipt:
        with pytest.raises(SupervisorError,match='Fabric launch identity is unavailable'):
            asyncio.run(supervisor.start_cycle_job(job.job_id,command_id=f'coo-cycle:{root.job_id}:dispatch:{job.job_id}:attempt:1'))
        assert calls==[probe.OPERATION,'start'] and not adapter._refs
        refused=rt.attempts.get_attempt(captured['binding']['attempt_id'])
        assert refused.launch_metadata[REMOTE_LAUNCH_IDENTITY_KEY]
        assert refused.pid is None and refused.status.value=='CLAIMED'
        return
    active=asyncio.run(supervisor.start_cycle_job(job.job_id,command_id=f'coo-cycle:{root.job_id}:dispatch:{job.job_id}:attempt:1'))
    assert calls==[probe.OPERATION,'start']
    assert type(active.launch_spec) is OrchestrationLaunchSpec
    assert active.launch_spec.worker_user==username and active.launch_spec.shared_run_gid==gid
    assert captured['launch_spec']['worker_user']==username and captured['launch_spec']['shared_run_gid']==gid
    assert supervisor.worker_user=='control-only' and supervisor.shared_run_gid==gid
    attempt=rt.attempts.get_attempt(active.launch_spec.run_id);metadata=attempt.launch_metadata
    assert active.launch_spec.effective_grant_digest==attempt.effective_grant_digest
    assert active.launch_spec.secret_canary_verdict==captured['launch_spec']['secret_canary_verdict']==verdict
    assert metadata['launch_attestation']['secret_canary_verdict']==verdict
    recovery=WorkerRecoveryBinding.from_dict(metadata['worker_recovery_binding'])
    restored=recovery.recover_launch_spec(OrchestrationLaunchSpec)
    assert restored==active.launch_spec
    assert Path(restored.workspace_path).parent==workspaces and Path(restored.run_dir).parent==runs
    assert original_get(job.job_id).worktree==job.worktree
    assert recovery.control_recovery['source_workspace']==job.worktree
    supervisor._revalidate_recovery_inputs(attempt,restored)
    assert metadata[REMOTE_LAUNCH_IDENTITY_KEY]['sha256']==adapter._identity(physical,captured)
    assert attempt.pid==1234 and attempt.status.value=='CHECKPOINTED'


def test_actual_loaded_control_paths_pin_and_snapshot(tmp_path,monkeypatch,root_stats):
    from tests.test_ceo_submit_armed_composition import _raw,_write
    from tests.test_executive_fabric_phase1c import staged
    raw=_raw(tmp_path);raw.update(staged(tmp_path,raw))
    raw['fabric_attended_probe']={'worker_config_path':str(tmp_path/'worker.json')}
    path=_write(tmp_path,raw);loaded=control.load_control_config(path)
    assert isinstance(loaded['runtime_root'],Path)
    att={'config_sha256':'a'*64}
    source=probe.AttendedControlProbeSource.from_startup(path,loaded,att)
    source.require_definition(control.load_control_config(path))
    monkeypatch.setattr(probe.sys,'platform','darwin')
    fixture_worker={**finite_definition(), 'fixture':'worker-definition','worker_user':'finite'}
    monkeypatch.setattr(probe,'definition',lambda *a:fixture_worker)
    monkeypatch.setattr(probe,'binding',lambda *a:'fixture-binding')
    monkeypatch.setattr(control,'_load_control_environment_attestation',lambda *a,**kw:att)
    spec=dataclasses.make_dataclass('FixtureSpec',[('worker_user',str),('shared_run_gid',int)])('control',450)
    assert source.snapshot(SimpleNamespace(worker_gid=460),spec)==(loaded,fixture_worker,att,'fixture-binding')
