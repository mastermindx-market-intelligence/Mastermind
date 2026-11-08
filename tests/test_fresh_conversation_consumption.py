"""Actual lost Keep response -> original readonly receipt, no second mutation."""
import asyncio
import dataclasses
import pytest
from tests.test_fresh_conversation_http import mounted,post,rsa_key
from tests.test_fresh_conversation import cleanup
from control_plane.principal_projection import neutral_principal_projection


def test_lost_original_keep_readonly_recovery_before_any_turn_then_same_turn(tmp_path,rsa_key,monkeypatch):
    async def run():
        app,token,wt,service,runtime,request,adapters,calls,sink=await mounted(tmp_path,rsa_key,monkeypatch)
        import os
        request={**request,'operation_key':os.environ.get('S34_CREATE_OPERATION_KEY',request['operation_key'])}
        try:
            _,preview=await post(app,'preview',request,token,wt)
            _,created=await post(app,'create',{**request,'preview_digest':preview['data']['preview']['digest']},token,wt,timeout_seconds=60)
            assert created['ok']
            raw=calls[-1]['principal'];principal=neutral_principal_projection(**{**raw,'scopes':tuple(raw['scopes'])})
            owner=service._fixture_fresh_owner
            reference=owner.project_references(principal,{'work_ref':request['work_ref']})['entries'][0]['reference']
            window=owner.read_reference(principal,reference)
            consume=dict(work_ref=request['work_ref'],reference=reference,initial_digest=window['initial_result']['digest'])
            _,absent=await post(app,'consume_status',consume,token)
            assert absent['ok'] and absent['data']['state']=='ABSENT' and not absent['data']['can_send']
            service._fixture_lose_consume_return=True
            code,lost=await post(app,'consume',consume,token,wt)
            assert code==202 and not lost['ok'] and lost['error']['code']=='effect_unknown',lost
            assert len([e for e in runtime.events.list_events() if e.event_type=='FRESH_CONVERSATION_INITIAL_CONSUMED'])==1
            assert not any(e.event_type=='FRESH_CONVERSATION_TURN_REQUESTED' for e in runtime.events.list_events())
            before=runtime.events.list_events()
            _,recovered=await post(app,'consume_status',consume,token)
            assert recovered['ok'] and recovered['data']['state']=='CONSUMED' and recovered['data']['initial_consumption']
            legacy=dict(work_ref=request['work_ref'],operation_key=request['operation_key'],initial_digest=consume['initial_digest'])
            _,same=await post(app,'consume_status',legacy,token)
            assert same['ok'] and same['data']['initial_consumption']==recovered['data']['initial_consumption']
            assert runtime.events.list_events()==before and adapters[0].begin_turn_calls==1
            _,wrong=await post(app,'consume_status',{**consume,'initial_digest':'0'*64},token)
            assert not wrong['ok'] and runtime.events.list_events()==before
            with monkeypatch.context() as m:
                m.setattr(service,'_ceo_ingress_app_binding',dataclasses.replace(service._ceo_ingress_app_binding))
                _,stale=await post(app,'consume_status',consume,token)
                assert not stale['ok'] and runtime.events.list_events()==before
            _,foreign=await post(app,'consume_status',{**consume,'reference':{**reference,'principal_scope_sha256':'0'*64}},token)
            assert not foreign['ok'] and runtime.events.list_events()==before
            # Read-only receipt recovery does not grant Send. A fresh exact
            # dual-resource preview qualifies one composed original turn.
            turn_request={**consume,'turn_key':os.environ.get('S34_TURN_OPERATION_KEY','same-original-after-keep'),'message':'One bounded follow-up.'}
            _,no_workspace=await post(app,'turn_preview',turn_request,token)
            assert not no_workspace['ok'] and runtime.events.list_events()==before
            _,ready=await post(app,'turn_preview',turn_request,token,wt)
            assert ready['ok'] and ready['data']['state']=='TURN_READY' and ready['data']['can_send'] is True,ready
            assert runtime.events.list_events()==before and adapters[0].begin_turn_calls==1
            _,wrong_preview=await post(app,'turn',{**turn_request,'preview_digest':'0'*64},token,wt)
            assert not wrong_preview['ok'] and runtime.events.list_events()==before and adapters[0].begin_turn_calls==1
            _,changed_message=await post(app,'turn',{**turn_request,'message':'Changed after preview','preview_digest':ready['data']['preview_digest']},token,wt)
            assert not changed_message['ok'] and runtime.events.list_events()==before
            with monkeypatch.context() as m:
                m.setattr(owner._app.workspace_read_provider_factory(runtime),'authorize',lambda _:False)
                _,revoked=await post(app,'turn',{**turn_request,'preview_digest':ready['data']['preview_digest']},token,wt)
                assert not revoked['ok'] and runtime.events.list_events()==before and adapters[0].begin_turn_calls==1
            # No reconsume after the lost response. Only one new attended turn.
            final_turn_request={**turn_request,'preview_digest':ready['data']['preview_digest']}
            monkeypatch.setattr("control_plane.executive_service._NATIVE_CONTINUATION_WAIT_SECONDS", 2.0)
            _,turn=await post(app,'turn',final_turn_request,token,wt)
            assert turn['ok'] and turn['data']['state']=='RECORDED',turn
            assert adapters[0].begin_turn_calls==2 and len(runtime.jobs.list_jobs())==2 and len(runtime.attempts.list_attempts())==1
            assert len([e for e in runtime.events.list_events() if e.event_type=='FRESH_CONVERSATION_INITIAL_CONSUMED'])==1
            task=service._dispatch_tasks.get(created["data"]["locator"]["job_id"])
            if task is not None:await asyncio.wait_for(asyncio.shield(task),5)
            after=runtime.events.list_events()
            _,not_ready=await post(app,'turn_preview',turn_request,token,wt)
            assert not not_ready['ok'] and runtime.events.list_events()==after and adapters[0].begin_turn_calls==2
            _,duplicate=await post(app,'turn',final_turn_request,token,wt)
            assert duplicate['ok'] and duplicate['data']['result']==turn['data']['result']
            assert runtime.events.list_events()==after and adapters[0].begin_turn_calls==2
        finally:await cleanup(service)
    asyncio.run(run())
