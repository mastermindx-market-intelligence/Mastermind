"""Source qualification over the real catalogue; no provider or host effects."""
import asyncio
import dataclasses
import hashlib
import json
import pytest
from control_plane import fabric_attended_routing as route, foreground_operation as foreground
from control_plane.model_router import ModelRouter, RoutingPolicyError
from control_plane.ceo_request import normalize_high_level_request
from control_plane.worker_adapter import ADAPTER_DESCRIPTORS
from control_plane.executive_runtime import Runtime
from control_plane.executive_service import ExecutiveControlService, StateConflict
from tests.test_foreground_operation import frame, admit


def digest(arguments):
    return hashlib.sha256(json.dumps(arguments,sort_keys=True,separators=(',', ':'),
        ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def selected(f=None):
    f = frame() if f is None else f
    q = route.AttendedQualification(f['arguments']['operation_key'], digest(normalize_high_level_request(f['arguments'])))
    return route.AttendedWorkPlacement('minimax.attended',
        'minimax-token-plan.claude-code-anthropic', 'minimax-read', qualification=q)


def test_real_catalogue_qualification_keeps_normal_route_and_r5_closed():
    router = ModelRouter.load()
    item = selected()
    member = route.placement_member(router, item)
    assert member['attended_route']['model'] == 'MiniMax-M3'
    assert not router.providers['minimax'].enabled
    assert not router.model_aliases['minimax.attended'].worker_eligible
    assert not ADAPTER_DESCRIPTORS['attended-fabric'].implemented
    with pytest.raises(RoutingPolicyError):
        router.resolve_model_alias('minimax.attended')
    with pytest.raises(RoutingPolicyError):
        router.resolve_attended_model_alias('minimax.attended', item.harness_binding_id)


@pytest.mark.parametrize('damage', ['enabled','autonomy','worker','model','alias','binding','implemented','write','network'])
def test_qualification_refuses_catalogue_escape(damage, monkeypatch):
    router, item = ModelRouter.load(), selected()
    if damage in {'enabled','autonomy'}:
        key = 'enabled' if damage == 'enabled' else 'autonomous_allowed'
        router.providers['minimax'] = dataclasses.replace(router.providers['minimax'], **{key:True})
    elif damage in {'worker','model'}:
        key, value = ('worker_eligible',True) if damage == 'worker' else ('model','another')
        router.model_aliases['minimax.attended'] = dataclasses.replace(router.model_aliases['minimax.attended'], **{key:value})
    elif damage in {'alias','binding'}:
        item = dataclasses.replace(item, **{'model_alias' if damage == 'alias' else 'harness_binding_id':'foreign'})
    elif damage == 'implemented':
        monkeypatch.setitem(ADAPTER_DESCRIPTORS,'attended-fabric',dataclasses.replace(ADAPTER_DESCRIPTORS['attended-fabric'],implemented=True))
    else:
        profile = router.capability_registry.profiles[route.CONTRACT_NAME]
        change = {'write_capable':True} if damage == 'write' else {'network_policy':'loopback-browser-only'}
        router.capability_registry.profiles[route.CONTRACT_NAME] = dataclasses.replace(profile, **change)
    with pytest.raises(RoutingPolicyError):
        route.placement_member(router,item)


def test_qualification_is_single_typed_foreground_only_configuration(tmp_path):
    from tests.test_executive_service import _config
    with pytest.raises(ValueError,match='foreground-only'):
        _config(tmp_path/'off',coo_attended_work_placements=(selected(),))
    with pytest.raises(ValueError,match='exactly one'):
        _config(tmp_path/'many',coo_foreground_only=True,coo_autonomy_armed=True,
                coo_attended_work_placements=(selected(),selected()))
    with pytest.raises(ValueError,match='typed'):
        dataclasses.replace(selected(),qualification={'operation_key':'fake'})


def make_service(tmp_path, f):
    from tests.test_executive_service import _config, _service
    config = _config(tmp_path,coo_foreground_only=True,coo_autonomy_armed=True,
        coo_attended_work_placements=(selected(f),))
    service,_ = _service(tmp_path,config=config)
    return service


@pytest.mark.parametrize('damage',['none','missing','operation','arguments','closed','foreign-root'])
def test_real_source_and_fresh_root_qualification(tmp_path,damage):
    f=frame(); service=make_service(tmp_path/'service',f)
    runtime=Runtime.at(tmp_path/'runtime')
    expected=service._load_coo_execution_binding()
    assert route.placement_member(ModelRouter.load(),selected(f)) in expected['work_placement_union']
    if damage=='operation': f['arguments']['operation_key']='foreign-operation'
    if damage=='arguments': f['arguments']['objective']='Foreign objective'
    async def run():
        if damage=='missing':
            with pytest.raises(foreground.ForegroundOperationClosed):
                service._require_coo_admission_binding()
            async with service._foreground_cycle_scope(None):
                pytest.fail('qualification without actual source admitted')
        async with foreground._session_bridge_foreground_dispatch(runtime,f,lambda:None) as op:
            if damage=='closed': op._mark_source_closed()
            async with service._foreground_cycle_scope(op):
                assert service._require_coo_admission_binding()==expected
                admitted=await admit(runtime,tmp_path,op,f)
                root=admitted['job_id']
                service._require_foreground_only_source('foreign' if damage=='foreign-root' else root,cycle_entry=True)
                assert op._root==root and runtime.attempts.list_attempts()==[]
                assert service._foreground_cycle_owner==(asyncio.current_task(),op)
        with pytest.raises(foreground.ForegroundOperationClosed):
            service._require_coo_admission_binding()
    if damage=='none':
        asyncio.run(run())
        assert len(runtime.jobs.list_jobs())==1
    else:
        with pytest.raises(foreground.ForegroundOperationRefusal): asyncio.run(run())
        assert len(runtime.jobs.list_jobs())==(1 if damage=='foreign-root' else 0)
    assert service._foreground_cycle_owner is None
    assert service._foreground_cycle_qualification is None


def test_changed_qualification_refuses_original_physical_before_admission(tmp_path):
    f=frame();service=make_service(tmp_path/'service',f);runtime=Runtime.at(tmp_path/'runtime')
    async def run():
        async with foreground._session_bridge_foreground_dispatch(runtime,f,lambda:None) as op:
            async with service._foreground_cycle_scope(op):
                result=await admit(runtime,tmp_path,op,f)
                service._require_foreground_only_source(result['job_id'])
                # Simulated host configuration replacement: not runtime mutation.
                changed=dataclasses.replace(selected(f).qualification, arguments_sha256='0'*64)
                service.config=dataclasses.replace(service.config, coo_attended_work_placements=(
                    dataclasses.replace(selected(f),qualification=changed),))
                with pytest.raises(foreground.ForegroundOperationRefusal,match='another request'):
                    service._require_foreground_only_source(result['job_id'])
                assert runtime.attempts.list_attempts()==[]
    asyncio.run(run())


def test_original_qualification_replay_has_no_fresh_bound_root(tmp_path):
    f=frame();service=make_service(tmp_path/'service',f);runtime=Runtime.at(tmp_path/'runtime')
    async def run():
        async with foreground._session_bridge_foreground_dispatch(runtime,f,lambda:None) as op:
            async with service._foreground_cycle_scope(op):
                original=await admit(runtime,tmp_path,op,f)
        async with foreground._session_bridge_foreground_dispatch(runtime,f,lambda:None) as op:
            async with service._foreground_cycle_scope(op):
                again=await admit(runtime,tmp_path,op,f)
                assert again['duplicate'] and op._root is None
                with pytest.raises(foreground.ForegroundOperationRefusal):
                    service._require_foreground_only_source(original['job_id'])
        assert len(runtime.jobs.list_jobs())==1 and runtime.attempts.list_attempts()==[]
    asyncio.run(run())


def test_qualified_startup_reaches_existing_owner_with_real_catalogue(tmp_path,monkeypatch):
    from tests.test_executive_fabric_composition import root_stats
    from tests.test_attended_control_startup import setup_startup
    from scripts import executive_os_phase1c as cli
    # Existing root-owned-file/host fixtures; catalogue and qualifier are real.
    root_stats.__wrapped__(monkeypatch)
    raw,_,captured=setup_startup(tmp_path,monkeypatch)
    raw.update(coo_foreground_only=True)
    placements=(selected(),)
    asyncio.run(cli._serve_from_config(tmp_path/'control.json',attended_work_placements=placements))
    assert captured['attended_work_placements'] is placements and captured['served']
    assert captured['fabric_worker_binding_source'] is not None
    assert captured['fabric_attended_probe_source'] is not None


def test_qualified_member_reaches_real_runtime_claim_and_launch_compiler(tmp_path):
    """Real catalogue/Runtime/compiler; inert adapter and binary fixture only."""
    from control_plane.executive_runtime import _project_work_placement
    from control_plane.fabric_attended_claude import prepare_attended_claude_launch
    from control_plane.subscription_catalog import get_binding
    from control_plane.subscription_provider_profiles import get_profile
    from tests.test_executive_supervisor import _supervisor, FakeAdapter, FakeInspector
    from tests.test_fabric_attended_claude import _binary

    placement = selected()
    member = route.placement_member(ModelRouter.load(), placement)
    actual_route = member['attended_route']
    runtime = Runtime.at(tmp_path / 'runtime')
    runtime.workers.register_worker('minimax-fixture', provider='minimax',
        account_label='inert-fixture', worker_type='attended-fabric', capabilities=['research'],
        quota_classes={'minimax-read': dict(provider='minimax', model=actual_route['model'],
            effort=actual_route['effort'], cost_class=actual_route['cost_class'],
            capabilities=['research'], metadata=dict(actual_route, attended_route=actual_route))})
    workspace = tmp_path / 'workspaces' / 'assigned'
    workspace.mkdir(parents=True, mode=0o700)
    constraints = {'work_placement_union': [member]}
    projected = _project_work_placement({}, constraints,
        {'provider_realm': 'minimax', 'quota_class': 'minimax-read'},
        raw_root_constraints=constraints)
    job = runtime.jobs.create_job('Inspect the assigned source', worktree=str(workspace),
        requested_authorities=['READ'], constraints=projected)
    supervisor = _supervisor(runtime, tmp_path, FakeAdapter(FakeInspector()))
    lease = runtime.attempts.claim_job(job.job_id, lease_owner=supervisor.instance_id)
    assert lease is not None
    schema = supervisor._run_dir(lease.attempt.attempt_id) / 'input' / 'result.schema.json'
    schema.parent.mkdir(parents=True, mode=0o700)
    schema.write_text('{}')
    spec = supervisor._launch_spec(runtime.jobs.get_job(job.job_id), lease, schema)
    assert spec.model == 'MiniMax-M3'
    prepared = prepare_attended_claude_launch(spec=spec, binary=_binary(),
        binding=get_binding(placement.harness_binding_id), profile=get_profile('minimax-token-plan'),
        model_class='routine', max_turns=2, result_schema={'type':'object'})
    assert prepared.environment['ANTHROPIC_MODEL'] == 'MiniMax-M3'
    assert not ADAPTER_DESCRIPTORS['attended-fabric'].implemented


@pytest.mark.parametrize('boundary', ['binding', 'execution'])
@pytest.mark.parametrize('change', ['replace', 'remove'])
def test_qualification_rechecked_after_blocking_binding_read(tmp_path, monkeypatch, boundary, change):
    f = frame()
    service = make_service(tmp_path / 'service', f)
    # Explicit inert host readiness boundary; route/source checks remain real.
    service._service_state = 'READY'
    monkeypatch.setattr(service, '_require_current_autonomy', lambda: None)
    monkeypatch.setattr(service, '_require_coo_worker_composed', lambda: None)
    expected_binding = service._load_coo_execution_binding()
    expectation = service._foreground_execution_state(binding=expected_binding)
    def changed_during_read():
        changed = dataclasses.replace(selected(f).qualification, arguments_sha256='0' * 64)
        service.config = dataclasses.replace(service.config, coo_attended_work_placements=(
            dataclasses.replace(selected(f), qualification=changed),) if change == 'replace' else ())
        return expected_binding
    monkeypatch.setattr(service, '_load_coo_execution_binding', changed_during_read)
    async def run():
        async with foreground._session_bridge_foreground_dispatch(Runtime.at(tmp_path/'runtime'), f, lambda: None):
            with pytest.raises((foreground.ForegroundOperationRefusal, StateConflict)):
                if boundary == 'binding':
                    service._require_coo_admission_binding()
                else:
                    service._require_foreground_execution(expectation)
    asyncio.run(run())


@pytest.mark.parametrize('edge', ['before', 'canonical-root-read'])
def test_qualifier_removal_after_root_binding_stops_actual_child_admission(tmp_path, monkeypatch, edge):
    from control_plane.executive_coo_cycle import CooCycle
    f = frame()
    service = make_service(tmp_path / 'service', f)
    runtime = Runtime.at(tmp_path / 'runtime')
    async def run():
        async with foreground._session_bridge_foreground_dispatch(runtime, f, lambda: None) as op:
            async with service._foreground_cycle_scope(op):
                root = (await admit(runtime, tmp_path, op, f))['job_id']
                service._require_foreground_only_source(root, cycle_entry=True)
                before = runtime.events.list_events()
                def remove():
                    service.config = dataclasses.replace(service.config, coo_attended_work_placements=())
                def before_admission(root_id):
                    if edge == 'before':
                        remove()
                        return service._require_foreground_only_source(root_id)
                    original = runtime.store.find_event_by_command_id
                    def blocking_read(*args, **kwargs):
                        result = original(*args, **kwargs)
                        remove()
                        return result
                    with monkeypatch.context() as patch:
                        patch.setattr(runtime.store, 'find_event_by_command_id', blocking_read)
                        return service._require_foreground_only_source(root_id)
                with pytest.raises((foreground.ForegroundOperationRefusal, StateConflict)):
                    CooCycle(runtime, before_admission=before_admission).run_once(root)
                assert runtime.events.list_events() == before
                assert len(runtime.jobs.list_jobs()) == 1 and runtime.attempts.list_attempts() == []
    asyncio.run(run())
