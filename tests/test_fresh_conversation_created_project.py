"""Actual CREATE/default/SourceEvent -> current-N project read; no invented row."""
import asyncio
import copy
import dataclasses
import faulthandler
import json
import os
from pathlib import Path
import time
import pytest
from tests.test_project_journey_canonical_create import joined, owner, env, isolated_git_env, identity
from tests.test_mastermind_executive_app_asgi import rsa_key
from tests.test_fresh_conversation import case, cleanup
from tests.test_workspace_read_service import cache_fixture
from control_plane.workspace_read_service import WorkspaceReadService
from control_plane.principal_projection import neutral_principal_projection
from integrations.mastermind_workspace_app.contract import workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from scripts import chairman_control_room as ccr


@pytest.fixture(autouse=True)
def fatal_only_traceback_diagnostics():
    # Retained88781 crashed in CPython's periodic cross-thread stack walker
    # (_PyFrame_SafeGetCode), not a Python source exception. Keep fatal crash
    # diagnostics and every pre-import effect guard; only retire that sampler.
    faulthandler.cancel_dump_traceback_later()
    faulthandler.enable()


def test_actual_created_n_project_membership_uses_canonical_read_not_c_snapshot(joined,tmp_path,monkeypatch):
    j=joined
    owners,clock,cache=cache_fixture(tmp_path/'fresh-read-cache')
    doc=owners[0].state_cache['doc'];doc['sources']={'macro_sha':j['code']}
    with owners[0].state_lock:ccr._publish_source_validity(owners[0],doc,tuple(clock),tuple(clock))
    _,authorize=workspace_authorizers(policy=j['factory'].workspace_policy,
        load_bindings=lambda:legacy_workspace_document(j['document'],j['factory'].workspace_policy))
    reader=WorkspaceReadService(cache=cache,runtime=j['runtime'],authorize=authorize,armed={},runtime_identity={},
        canonical_project_data=j['data'].installed_binding(),project_plan_reader=j['factory'].plan_reader)
    principal=neutral_principal_projection(**dataclasses.asdict(j['args']['principal']))
    workspace=neutral_principal_projection(**dataclasses.asdict(j['workspace']))
    service,runtime,fresh,principal,request,adapters=case(tmp_path/'fresh-native',principal,
        runtime_override=j['runtime'],workspace_override=workspace,workspace_reader_override=reader)
    work=j['args']['work_ref']
    assert not any(row['work_ref']==work for row in doc['work'])
    before=runtime.events.list_events();started=time.monotonic()
    projected=fresh._project(principal,workspace,work)
    print('canonical_membership_seconds',round(time.monotonic()-started,3))
    membership=projected['canonical_membership']
    assert membership['code_commit']==j['code'] and membership['data_commit']==j['current']
    assert membership['source']=={key:value for key,value in j['source'].items() if key!='repository'}|{'repository':'mastermindx-market-intelligence/macro','commit':j['current']}
    assert j['status']['receipt']['kind']=='SOURCE_OBSERVED'
    assert runtime.events.list_events()==before and not runtime.jobs.list_jobs() and not adapters


def _native_read_owner(j,tmp_path):
    owners,clock,cache=cache_fixture(tmp_path/'fresh-current-c')
    doc=owners[0].state_cache['doc'];doc['sources']={'macro_sha':j['code']}
    with owners[0].state_lock:ccr._publish_source_validity(owners[0],doc,tuple(clock),tuple(clock))
    _,authorize=workspace_authorizers(policy=j['factory'].workspace_policy,
        load_bindings=lambda:legacy_workspace_document(j['document'],j['factory'].workspace_policy))
    reader=WorkspaceReadService(cache=cache,runtime=j['runtime'],authorize=authorize,armed={},runtime_identity={},
        canonical_project_data=j['data'].installed_binding(),project_plan_reader=j['factory'].plan_reader)
    return reader,doc


def test_signed_created_n_preview_measures_complete_preeffect_callgraph(joined,tmp_path,monkeypatch,rsa_key):
    async def run():
        from tests.test_fresh_conversation_http import mounted,post
        j=joined;reader,doc=_native_read_owner(j,tmp_path)
        workspace=neutral_principal_projection(**dataclasses.asdict(j['workspace']))
        def actual_case(principal):
            return case(tmp_path/'native-preeffect',principal,runtime_override=j['runtime'],workspace_override=workspace,
                workspace_reader_override=reader,work_ref_override=j['args']['work_ref'])
        parts=await mounted(tmp_path/'http',rsa_key,monkeypatch,case_factory=actual_case,
            executive_policy=j['factory'].policies.submit,workspace_policy=j['factory'].workspace_policy,
            claims=dict(iss=j['factory'].policies.submit.issuer,sub='inert-chairman',client_id='inert-client',aud=j['factory'].policies.submit.resource))
        app,token,wt,service,runtime,request,adapters,calls,sink=parts
        request={**request,"operation_key":os.environ.get("S34_CREATE_OPERATION_KEY",request["operation_key"])}
        before=runtime.events.list_events();timings=[];acquisitions=[]
        from control_plane import installed_canonical_project_data_binding as binding_module
        actual_read=binding_module.read_installed_project_data
        def acquired(*args,**kwargs):
            acquisitions.append(time.monotonic());return actual_read(*args,**kwargs)
        monkeypatch.setattr(binding_module,"read_installed_project_data",acquired)
        original=service._fixture_fresh_owner._project
        def measured(*args,**kwargs):
            start=time.monotonic()
            try:return original(*args,**kwargs)
            finally:timings.append(round(time.monotonic()-start,3))
        monkeypatch.setattr(service._fixture_fresh_owner,'_project',measured)
        try:
            from control_plane.fresh_conversation_membership import _project_validation_phase
            proof_principal=neutral_principal_projection(**dataclasses.asdict(j['args']['principal']))
            with _project_validation_phase(service._fixture_fresh_owner,proof_principal,workspace,request['work_ref']):
                snapshot=reader.cache.snapshot();copied_owner=copy.copy(snapshot.owner)
                assert copied_owner is not snapshot.owner and copied_owner==snapshot.owner
                with monkeypatch.context() as m:
                    m.setattr(reader.cache,'snapshot',lambda:dataclasses.replace(snapshot,owner=copied_owner))
                    with pytest.raises(ValueError):service._fixture_fresh_owner._project(proof_principal,workspace,request['work_ref'])
                with pytest.raises(ValueError):service._fixture_fresh_owner._project(dataclasses.replace(proof_principal),workspace,request['work_ref'])
                with pytest.raises(ValueError):service._fixture_fresh_owner._project(proof_principal,dataclasses.replace(workspace),request['work_ref'])
            timings.clear();acquisitions.clear()
            code,prepared=await post(app,'preview',request,token,wt)
            print('actual_preeffect_membership_calls',len(timings),'seconds',timings)
            assert code==200 and prepared['ok'],prepared
            assert runtime.events.list_events()==before and not runtime.jobs.list_jobs() and not adapters
            assert not any(row['work_ref']==request['work_ref'] for row in doc['work'])
            timings.clear();acquisitions.clear();begin=time.monotonic()
            # The actual public foreground request is bounded to300s; the
            # helper's15s convenience timeout is not the Macro READ budget.
            # Every individual nominal canonical observation retains15s/10s.
            code,created=await post(app,'create',{**request,'preview_digest':prepared['data']['preview']['digest']},token,wt,timeout_seconds=300)
            print('actual_create_membership_calls',len(timings),'actual_acquisitions',len(acquisitions),'seconds',timings,'total',round(time.monotonic()-begin,3))
            assert code==200 and created['ok'] and created['data']['state']=='CREATED',created
            assert runtime is j['runtime'] and len(runtime.jobs.list_jobs())==2 and len(runtime.attempts.list_attempts())==1
            assert adapters[0].begin_turn_calls==1
            from common.executive_workspace_contract import FRAME_SCHEMA,FRAME_SCHEMA_V2,PRINCIPAL_KEYS
            from common import workspace_project_plan_contract as plan_wire
            raw_workspace={key:calls[-1]['workspace_principal'][key] for key in PRINCIPAL_KEYS}
            before_context_readers=runtime.events.list_events()
            programs=await reader.handle_frame(dict(schema=FRAME_SCHEMA,operation='programs',selection=None,principal=raw_workspace))
            selected_project=await reader.handle_frame(dict(schema=plan_wire.FRAME_SCHEMA,operation=plan_wire.OPERATION,
                selection={'work_ref':request['work_ref']},principal=raw_workspace))
            mission=await reader.handle_frame(dict(schema=FRAME_SCHEMA_V2,operation='mission_v3',
                selection={key:created['data']['locator'][key] for key in ('work_ref','root_job_id')},principal=raw_workspace))
            assert runtime.events.list_events()==before_context_readers
            # Export exact actual current read responses, including unavailable
            # catalogue/Mission context. Never invent a new C row or title.
            from control_plane.fresh_conversation import FreshConversationOwner
            principal=neutral_principal_projection(**{**calls[-1]['principal'],'scopes':tuple(calls[-1]['principal']['scopes'])})
            expected=(principal.policy_id,principal.issuer_digest,principal.resource)
            # A new owner reads only actual immutable provenance; no original
            # operation key or synthetic target is supplied by the catalogue.
            reopened_owner=FreshConversationOwner(service,expected_policy=expected,authorized_policies=j['factory'].policies)
            before_readers=runtime.events.list_events()
            catalogue=reopened_owner.project_references(principal,{'work_ref':request['work_ref']})
            reference=catalogue['entries'][0]['reference']
            initial=reopened_owner.read_reference(principal,reference)
            assert runtime.events.list_events()==before_readers
            consume=dict(work_ref=request['work_ref'],reference=reference,initial_digest=initial['initial_result']['digest'])
            initial_seal=runtime.events.get_event_by_command_id('orchestration-result-seal:'+created['data']['locator']['attempt_id'])
            service._fixture_lose_consume_return=True
            code,lost=await post(app,'consume',consume,token,wt,timeout_seconds=300)
            assert code==202 and not lost['ok'] and lost['error']['code']=='effect_unknown',lost
            _,recovered=await post(app,'consume_status',consume,token)
            assert recovered['ok'] and recovered['data']['state']=='CONSUMED' and recovered['data']['can_send'] is False,recovered
            turn_request={**consume,'turn_key':os.environ.get('S34_TURN_OPERATION_KEY','current-n-original-followup'),
                'message':'Explain this project’s next bounded action. 下一步'}
            prior=runtime.events.list_events()
            _,ready=await post(app,'turn_preview',turn_request,token,wt,timeout_seconds=300)
            assert ready['ok'] and ready['data']['state']=='TURN_READY',ready
            assert runtime.events.list_events()==prior and adapters[0].begin_turn_calls==1
            turn_request={**turn_request,'preview_digest':ready['data']['preview_digest']}
            _,second=await post(app,'turn',turn_request,token,wt,timeout_seconds=300)
            assert second['ok'] and second['data']['state']=='RECORDED',second
            assert runtime.events.get_event_by_command_id(initial_seal.command_id)==initial_seal
            task=service._dispatch_tasks.get(created['data']['locator']['job_id'])
            if task is not None:await asyncio.wait_for(asyncio.shield(task),5)
            selected=dict(work_ref=request['work_ref'],reference=reference,turn_key=turn_request['turn_key'])
            before_readers=runtime.events.list_events()
            _,status=await post(app,'turn_status',selected,token)
            _,read=await post(app,'turn_read',selected,token)
            _,duplicate=await post(app,'turn',turn_request,token,wt,timeout_seconds=300)
            archived=FreshConversationOwner(service,expected_policy=expected,authorized_policies=j['factory'].policies).read_reference(principal,reference)
            assert all(value['ok'] and value['data']['result']==second['data']['result'] for value in (status,read,duplicate))
            assert archived['state']=='SETTLED' and archived['epoch'] is None and archived['initial_result']==initial['initial_result']
            assert runtime.events.list_events()==before_readers and len(runtime.jobs.list_jobs())==2 and len(runtime.attempts.list_attempts())==1
            assert adapters[0].start_calls==1 and adapters[0].begin_turn_calls==2
            target=os.environ.get('S34_CREATED_N_FIXTURE_OUTPUT')
            if target:
                with Path(target).open('x',encoding='utf-8') as stream:
                    json.dump(dict(schema='mastermind.s34.created_n_recovered_turn_fixture.v1',
                        source_revision=os.environ['S34_SOURCE_REVISION'],project_source=j['status'],
                        code_commit=j['code'],data_commit=j['current'],request=request,preview=prepared,create=created,
                        programs=programs,selected_project=selected_project,mission=mission,
                        catalogue=catalogue,initial_read=initial,consume_request=consume,lost_consume=lost,
                        consume_status=recovered,turn_preview=ready,turn_request=turn_request,turn=second,
                        status=status,turn_read=read,duplicate=duplicate,archived_read=archived,
                        actual_counts=dict(jobs=2,attempts=1,starts=1,turns=2),
                        seams=['genuine disposable CREATE/compiler/Git default/SOURCE_OBSERVED',
                            'synthetic Root source seal, credentials and PR identity',
                            'actual signed independent resource bearers',
                            'inert private kernel peer and physical native provider']),stream,ensure_ascii=False,sort_keys=True,indent=2)
        finally:await cleanup(service)
    asyncio.run(run())


def test_nominal_pure_current_phase_reuses_only_active_issued_read_and_refuses_currentness(joined,tmp_path,monkeypatch):
    import copy
    from control_plane.fresh_conversation_membership import _project_validation_phase, _PHASE
    from control_plane.project_canonical_data import _CAPTURE
    from control_plane import installed_canonical_project_data_binding as binding_module
    from tests.test_workspace_project_git_publisher import git
    j=joined;reader,doc=_native_read_owner(j,tmp_path)
    principal=neutral_principal_projection(**dataclasses.asdict(j['args']['principal']))
    workspace=neutral_principal_projection(**dataclasses.asdict(j['workspace']))
    service,runtime,fresh,principal,request,adapters=case(tmp_path/'native-pure',principal,
        runtime_override=j['runtime'],workspace_override=workspace,workspace_reader_override=reader,
        work_ref_override=j['args']['work_ref'])
    work=request['work_ref'];before=runtime.events.list_events();acquisitions=[]
    actual=binding_module.read_installed_project_data
    def observed(*args,**kwargs):
        acquisitions.append(time.monotonic());return actual(*args,**kwargs)
    monkeypatch.setattr(binding_module,'read_installed_project_data',observed)
    standalone=[fresh._project(principal,workspace,work) for _ in range(3)]
    assert standalone[0]==standalone[1]==standalone[2] and len(acquisitions)==3
    acquisitions.clear()
    with _project_validation_phase(fresh,principal,workspace,work):
        phase=_PHASE.get();capture=_CAPTURE.get();view=phase.view
        assert phase.active and capture is phase.capture
        assert all(fresh._project(principal,workspace,work)==standalone[0] for _ in range(3))
        assert len(acquisitions)==1
        with pytest.raises(ValueError):fresh._project(dataclasses.replace(principal),workspace,work)
        with pytest.raises(ValueError):fresh._project(principal,dataclasses.replace(workspace),work)
        with pytest.raises(ValueError):
            with _project_validation_phase(fresh,dataclasses.replace(principal),workspace,work):pass
        with monkeypatch.context() as m:
            m.setattr(fresh,'_project_validation_phase',copy.copy(phase))
            with pytest.raises(ValueError):fresh._project(principal,workspace,work)
        with monkeypatch.context() as m:
            m.setattr(reader,'authorize',lambda _:False)
            with pytest.raises(ValueError):fresh._project(principal,workspace,work)
        with monkeypatch.context() as m:
            m.setitem(j['document']['profiles'][j['document']['primary_profile']], 'project_canonical_data_read', None)
            with pytest.raises(ValueError):fresh._project(principal,workspace,work)
    assert _PHASE.get() is None and _CAPTURE.get() is None and not phase.active and phase.view is None
    # A copied or closed phase, including inside a bare generic capture, cannot
    # resurrect that issued view or provide a cross-callback observation.
    with view.capture_scope():
        token=_PHASE.set(phase)
        try:
            with pytest.raises(ValueError):fresh._project(principal,workspace,work)
        finally:_PHASE.reset(token)
    with pytest.raises(ValueError):fresh._project(principal,workspace,'WS:FOREIGN')
    with pytest.raises(ValueError):fresh._project(principal,dataclasses.replace(workspace,expires_at=int(time.time())-1),work)
    # Real elapsed monotonic expiry, no fake clock or deadline extension.
    with pytest.raises(ValueError):
        with _project_validation_phase(fresh,principal,workspace,work):
            deadline=_PHASE.get().view._operation.read_deadline
            time.sleep(max(0,deadline-time.monotonic())+0.01)
            fresh._project(principal,workspace,work)
    assert _PHASE.get() is None and _CAPTURE.get() is None
    # Change actual protected/default Git after the pure body; full exit must
    # refuse and the unchanged old Event must never prove unsupported new N.
    with pytest.raises(ValueError):
        with _project_validation_phase(fresh,principal,workspace,work):
            root=j['integrator'];path=root/'independent-default.txt';path.write_text('unqualified current default movement')
            git(root,'add',str(path.relative_to(root)));git(root,'commit','-m','Independent fresh membership drift')
            git(root,'push','origin','main')
    # A new observation may legitimately prove unrelated default movement
    # using the unchanged exact CREATE postimages; that is not old-view reuse.
    assert fresh._project(principal,workspace,work)['canonical_membership']['data_commit']!=j['current']
    source_path=j['integrator']/j['source']['path']
    source_path.write_bytes(source_path.read_bytes()+b'\nUnsupported selected source change.\n')
    git(j['integrator'],'add',j['source']['path']);git(j['integrator'],'commit','-m','Unproved selected project bytes')
    git(j['integrator'],'push','origin','main')
    with pytest.raises(ValueError):fresh._project(principal,workspace,work)
    assert runtime.events.list_events()==before and not runtime.jobs.list_jobs() and not adapters
    print('actual_membership_acquisitions_standalone',3,'same_pure_phase',1,'real_expiry_and_default_exit_refused')
