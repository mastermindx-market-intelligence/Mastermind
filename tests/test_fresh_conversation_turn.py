"""Actual signed parent consume -> same retained TX5 second turn; no live I/O."""
import asyncio
import dataclasses
import json
import os
from pathlib import Path

import pytest
from common import fresh_conversation_contract as wire
from tests.test_fresh_conversation_http import mounted, post, rsa_key
from tests.test_fresh_conversation import cleanup


def test_signed_consumed_parent_second_turn_original_read_and_no_replay(tmp_path, rsa_key, monkeypatch):
    async def run():
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        request = {**request, "operation_key": os.environ.get("S34_CREATE_OPERATION_KEY", request["operation_key"])}
        diagnostics = []
        from control_plane import fresh_conversation_turn as module
        original_read = module.read_turn
        async def traced_read(*args, **kwargs):
            try: return await original_read(*args, **kwargs)
            except Exception as exc:
                frames=[]; trace=exc.__traceback__
                while trace is not None:
                    frames.append(trace.tb_frame.f_code.co_name);trace=trace.tb_next
                diagnostics.append((type(exc).__name__,str(exc)[:160],frames))
                raise
        monkeypatch.setattr(module,"read_turn",traced_read)
        try:
            _, preview = await post(app, "preview", request, token, wt)
            from common.executive_workspace_contract import FRAME_SCHEMA,FRAME_SCHEMA_V2,PRINCIPAL_KEYS
            backend=service._ceo_ingress_app_binding.workspace_read_provider_factory(runtime)
            workspace_principal={key:calls[-1]["workspace_principal"][key] for key in PRINCIPAL_KEYS}
            before_programs=runtime.events.list_events()
            programs=await backend.handle_frame(dict(schema=FRAME_SCHEMA,operation="programs",selection=None,principal=workspace_principal))
            assert programs["ok"] and runtime.events.list_events()==before_programs
            _, created = await post(app, "create", {**request,"preview_digest":preview["data"]["preview"]["digest"]}, token, wt)
            assert created["ok"] and created["data"]["state"] == "CREATED", created
            from control_plane.fresh_conversation import FreshConversationOwner
            from control_plane.principal_projection import neutral_principal_projection
            raw=calls[-1]["principal"]
            principal=neutral_principal_projection(**{**raw,"scopes":tuple(raw["scopes"])})
            expected=(principal.policy_id,principal.issuer_digest,principal.resource)
            from integrations.mastermind_executive_app.gateway import AppPolicies
            from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
            from tests import test_mastermind_executive_app_asgi as auth
            import time
            policies=AppPolicies(auth._read_policy(),auth._submit_policy())
            read_auth=JwtAuthenticator(policy=policies.read,jwks_cache=auth._FakeJwksCache(rsa_key))
            now=int(time.time());read_token=auth._read_token(rsa_key,iat=now-1,nbf=now-1,exp=now+600)
            actual_read_principal=await read_auth.verify_token(read_token,now=now)
            read_principal=neutral_principal_projection(**dataclasses.asdict(actual_read_principal))
            reader=FreshConversationOwner(service,expected_policy=expected,authorized_policies=policies)
            before_readers=runtime.events.list_events()
            mission=await backend.handle_frame(dict(schema=FRAME_SCHEMA_V2,operation="mission_v3",
                selection={key:created["data"]["locator"][key] for key in ("work_ref","root_job_id")},principal=workspace_principal))
            assert mission["ok"]
            # Simulate a fresh client/owner after persisted creation. Neither
            # catalogue/Open nor the following public actions use the old key.
            catalogue=reader.project_references(read_principal,{"work_ref":request["work_ref"]})
            reference=catalogue["entries"][0]["reference"]
            initial=FreshConversationOwner(service,expected_policy=expected,authorized_policies=policies).read_reference(read_principal,reference)
            assert runtime.events.list_events()==before_readers
            selected = dict(work_ref=request["work_ref"],reference=reference)
            initial_digest = initial["initial_result"]["digest"]
            before = runtime.events.get_event_by_command_id("orchestration-result-seal:"+created["data"]["locator"]["attempt_id"])
            consume_request = {**selected,"initial_digest":initial_digest}
            _, consumed = await post(app,"consume",consume_request,token,wt)
            assert consumed["ok"] and consumed["data"]["state"] == "CONSUMED" and consumed["data"]["can_send"] is True, consumed
            turn_request = {**consume_request,"turn_key":os.environ.get("S34_TURN_OPERATION_KEY", "original-followup-001"),"message":"Explain the next bounded action. 新消息"}
            code, second = await post(app,"turn",turn_request,token,wt)
            assert code == 200 and second["ok"] and second["data"]["state"] == "RECORDED", second
            assert second["data"]["result"]["envelope"]["summary"] == "Inert native follow-up answer."
            assert second["data"]["result"]["digest"] != initial_digest
            assert not second["data"]["parent_consumed"]
            assert turn_request["message"] in adapters[0].prompts[-1]
            assert second["data"]["initial_consumption"] == consumed["data"]["initial_consumption"]
            assert len(runtime.jobs.list_jobs()) == 2 and len(runtime.attempts.list_attempts()) == 1
            assert adapters[0].start_calls == 1 and adapters[0].begin_turn_calls == 2
            assert runtime.events.get_event_by_command_id(before.command_id) == before
            turn_selected = {**selected,"turn_key":turn_request["turn_key"]}
            _, read = await post(app,"turn_read",turn_selected,token)
            assert read["ok"] and read["data"]["result"] == second["data"]["result"],(read,diagnostics,service._dispatch_errors)
            # The original result may be durable before its background job
            # appends JOB_COMPLETED. Finish that original dispatch before
            # measuring whether the duplicate itself adds any event.
            task=service._dispatch_tasks.get(created["data"]["locator"]["job_id"])
            if task is not None:await asyncio.wait_for(asyncio.shield(task),5)
            events = runtime.events.list_events()
            _, repeated = await post(app,"turn",turn_request,token,wt)
            assert repeated["ok"] and repeated["data"]["result"] == second["data"]["result"],repeated
            assert runtime.events.list_events() == events and adapters[0].begin_turn_calls == 2
            _, status = await post(app,"turn_status",turn_selected,token)
            assert status["ok"] and status["data"]["result"] == second["data"]["result"]
            archived=FreshConversationOwner(service,expected_policy=expected,authorized_policies=policies).read_reference(read_principal,reference)
            assert archived["epoch"] is None and archived["state"]=="SETTLED"
            assert archived["initial_result"]["digest"]==initial_digest
            assert archived["turns"][0]["result"]==second["data"]["result"]
            assert "operation_key" not in consume_request and second["data"]["operation_key"] is None
            path = os.environ.get("S34_TURN_FIXTURE_OUTPUT")
            if path:
                with Path(path).open("x",encoding="utf-8") as stream:
                    json.dump(dict(schema="mastermind.s34.attended_turn_fixture.v1", source_revision=os.environ["S34_SOURCE_REVISION"], request=request,
                        preview=preview,programs=programs,create=created,mission=mission,catalogue=catalogue,initial_read=initial,archived_read=archived,consume_request=consume_request,
                        consume=consumed,turn_request=turn_request,turn=second,turn_read=read,
                        duplicate=repeated,status=status,actual_counts=dict(jobs=2,attempts=1,starts=1,turns=2),
                        seams=["fixture company authority/catalogue/host readiness", "actual RS256 resource verifiers",
                            "inert private kernel peer forwarding actual frame", "inert physical native provider"]),
                        stream,ensure_ascii=False,sort_keys=True,indent=2)
        finally:
            await cleanup(service)
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["unconsumed", "wrong_digest", "workspace_absent", "foreign_client"])
def test_second_turn_admission_refuses_before_reservation_or_io(tmp_path, rsa_key, monkeypatch, fault):
    async def run():
        from tests import test_mastermind_executive_app_asgi as auth
        from tests import test_workspace_read_app as workspace_auth
        import time
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path,rsa_key,monkeypatch)
        try:
            _, preview = await post(app,"preview",request,token,wt)
            _, created = await post(app,"create",{**request,"preview_digest":preview["data"]["preview"]["digest"]},token,wt)
            selected={key:request[key] for key in ("work_ref","operation_key")}
            _, initial=await post(app,"read",selected,token)
            consume_request={**selected,"initial_digest":initial["data"]["result"]["digest"]}
            if fault != "unconsumed":
                _, consumed=await post(app,"consume",consume_request,token,wt)
                assert consumed["ok"]
            turn={**consume_request,"turn_key":"refused-original-one","message":"Do one bounded follow-up."}
            if fault == "wrong_digest":turn["initial_digest"]="0"*64
            if fault == "workspace_absent":wt=None
            if fault == "foreign_client":
                now=int(time.time());wt=auth._token(rsa_key,scope=workspace_auth.SCOPE,aud=workspace_auth.RESOURCE,
                    client_id="foreign-client",iat=now-1,nbf=now-1,exp=now+600)
            before=runtime.events.list_events()
            _, refused=await post(app,"turn",turn,token,wt)
            assert not refused["ok"] and adapters[0].begin_turn_calls==1
            assert runtime.events.list_events()==before
            assert not any(event.event_type=="FRESH_CONVERSATION_TURN_REQUESTED" for event in before)
        finally:await cleanup(service)
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["request_closed", "workspace_revoked", "writer_changed", "source_changed", "lost_return"])
def test_interrupted_second_turn_is_original_unknown_never_resent(tmp_path, rsa_key, monkeypatch, fault):
    async def run():
        from control_plane.fresh_conversation_turn import FreshConversationTurnSource
        import copy
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path,rsa_key,monkeypatch)
        try:
            _, preview=await post(app,"preview",request,token,wt)
            _, created=await post(app,"create",{**request,"preview_digest":preview["data"]["preview"]["digest"]},token,wt)
            selected={key:request[key] for key in ("work_ref","operation_key")}
            _, initial=await post(app,"read",selected,token)
            consume_request={**selected,"initial_digest":initial["data"]["result"]["digest"]}
            _, consumed=await post(app,"consume",consume_request,token,wt)
            assert consumed["ok"]
            turn={**consume_request,"turn_key":"interrupted-original-one","message":"One original follow-up."}
            source_evidence=[]
            def before_turn(kwargs):
                source=service._native_operator_dispatch._fresh_turn_source
                assert type(source) is FreshConversationTurnSource and source.check()
                with pytest.raises(ValueError):copy.copy(source).check()
                source_evidence.append("actual-source-copy-refused")
                if fault=="request_closed":service._fixture_active_private_reader.feed_eof()
                elif fault=="workspace_revoked":
                    service._ceo_ingress_app_binding.workspace_read_provider_factory(runtime).authorize=lambda _:False
                elif fault=="writer_changed":
                    with runtime.store.transaction() as conn:
                        conn.execute("UPDATE process_generations SET provider_session_id='foreign-native-writer' WHERE process_generation_id=?",
                            (kwargs["generation"].process_generation_id,))
                elif fault=="source_changed":
                    original=service._ceo_ingress_dialogue_source_provider
                    def changed(*args):
                        data=original(*args);data["commission_ref"]={**data["commission_ref"],"content_sha256":"f"*64};return data
                    service._ceo_ingress_dialogue_source_provider=changed
                else:
                    # Real inert begin-turn accepted, return dropped before its
                    # native ACK reaches OHF: no public recorded reply may appear.
                    adapters[0].begin_turn_calls+=1
                    raise OSError("inert accepted native turn return lost")
            service._fixture_before_turn_io=before_turn
            code, response=await post(app,"turn",turn,token,wt)
            assert source_evidence and adapters[0].begin_turn_calls==(2 if fault=="lost_return" else 1)
            assert not response["ok"] or response["data"]["state"]=="RECONCILIATION_REQUIRED",response
            assert not any(event.event_type=="FRESH_CONVERSATION_TURN_RECORDED" for event in runtime.events.list_events())
            # Consume the incumbent actual cleanup task before testing the
            # read-only boundary. Those existing reconciliation Events are
            # execution settlement, not a replay caused by status/read.
            child_id=created["data"]["locator"]["job_id"]
            task=service._dispatch_tasks.get(child_id)
            if task is not None:
                await asyncio.wait_for(asyncio.shield(task),5)
            before=runtime.events.list_events();count=adapters[0].begin_turn_calls
            turn_selected={**selected,"turn_key":turn["turn_key"]}
            _, reopened=await post(app,"turn_status",turn_selected,token)
            assert not reopened["ok"] or reopened["data"]["state"]=="RECONCILIATION_REQUIRED",reopened
            await post(app,"turn",turn,token,wt)
            assert adapters[0].begin_turn_calls==count and runtime.events.list_events()==before
            assert len(runtime.jobs.list_jobs())==2 and len(runtime.attempts.list_attempts())==1
        finally:await cleanup(service)
    asyncio.run(run())


def test_pending_same_key_and_distinct_key_cannot_dispatch_another_turn(tmp_path,rsa_key,monkeypatch):
    async def run():
        import threading
        app,token,wt,service,runtime,request,adapters,calls,sink=await mounted(tmp_path,rsa_key,monkeypatch)
        release=threading.Event()
        try:
            _,preview=await post(app,"preview",request,token,wt)
            _,created=await post(app,"create",{**request,"preview_digest":preview["data"]["preview"]["digest"]},token,wt)
            selected={key:request[key] for key in ("work_ref","operation_key")}
            _,initial=await post(app,"read",selected,token)
            consumed_request={**selected,"initial_digest":initial["data"]["result"]["digest"]}
            _,consumed=await post(app,"consume",consumed_request,token,wt)
            assert consumed["ok"]
            entered=asyncio.Event();loop=asyncio.get_running_loop();retained_sources=[]
            def before_io(kwargs):
                retained_sources.append(service._native_operator_dispatch._fresh_turn_source)
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(5)
            service._fixture_before_turn_io=before_io
            turn={**consumed_request,"turn_key":"one-pending-turn","message":"Bounded follow-up."}
            first=asyncio.create_task(post(app,"turn",turn,token,wt))
            await asyncio.wait_for(entered.wait(),5)
            _,same=await post(app,"turn",turn,token,wt)
            assert same["ok"] and same["data"]["state"]=="RECONCILIATION_REQUIRED",same
            _,foreign=await post(app,"turn",{**turn,"turn_key":"another-turn"},token,wt)
            assert not foreign["ok"]
            assert adapters[0].begin_turn_calls==1
            assert len([e for e in runtime.events.list_events() if e.event_type=="FRESH_CONVERSATION_TURN_REQUESTED"])==1
            release.set();_,completed=await first
            assert completed["ok"] and completed["data"]["state"]=="RECORDED",completed
            task=service._dispatch_tasks.get(created["data"]["locator"]["job_id"])
            if task is not None:await asyncio.wait_for(asyncio.shield(task),5)
            with pytest.raises(ValueError):retained_sources[0].check()
            assert adapters[0].begin_turn_calls==2 and len(runtime.attempts.list_attempts())==1
        finally:
            release.set();await cleanup(service)
    asyncio.run(run())


def test_real_expiry_before_second_turn_io_leaves_original_unknown(tmp_path,rsa_key,monkeypatch):
    async def run():
        import time
        from tests import test_mastermind_executive_app_asgi as auth
        from tests import test_workspace_read_app as workspace_auth
        app,long_token,long_wt,service,runtime,request,adapters,calls,sink=await mounted(tmp_path,rsa_key,monkeypatch)
        now=int(time.time());expiry=now+10
        token=auth._submit_token(rsa_key,iat=now-1,nbf=now-1,exp=expiry)
        wt=auth._token(rsa_key,scope=workspace_auth.SCOPE,aud=workspace_auth.RESOURCE,iat=now-1,nbf=now-1,exp=expiry)
        try:
            _,preview=await post(app,"preview",request,token,wt)
            _,created=await post(app,"create",{**request,"preview_digest":preview["data"]["preview"]["digest"]},token,wt)
            assert created["ok"],created
            selected={key:request[key] for key in ("work_ref","operation_key")}
            _,initial=await post(app,"read",selected,token)
            consume_request={**selected,"initial_digest":initial["data"]["result"]["digest"]}
            _,consumed=await post(app,"consume",consume_request,token,wt)
            assert consumed["ok"],consumed
            def before_io(kwargs):time.sleep(max(0,expiry-time.time()+0.02))
            service._fixture_before_turn_io=before_io
            turn={**consume_request,"turn_key":"expired-original-turn","message":"One attended follow-up."}
            _,refused=await post(app,"turn",turn,token,wt)
            assert not refused["ok"] and adapters[0].begin_turn_calls==1
            task=service._dispatch_tasks.get(created["data"]["locator"]["job_id"])
            if task is not None:await asyncio.wait_for(asyncio.shield(task),5)
            before=runtime.events.list_events()
            _,status=await post(app,"turn_status",{**selected,"turn_key":turn["turn_key"]},long_token)
            assert status["ok"] and status["data"]["state"]=="RECONCILIATION_REQUIRED",status
            await post(app,"turn",turn,long_token,long_wt)
            assert adapters[0].begin_turn_calls==1 and runtime.events.list_events()==before
        finally:await cleanup(service)
    asyncio.run(run())
