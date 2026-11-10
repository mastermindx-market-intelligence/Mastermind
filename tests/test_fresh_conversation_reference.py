"""Actual fresh admission survives new owner/reload without saved public opkey."""
import asyncio
import copy
import dataclasses
import json
import os
from pathlib import Path
import time
import pytest
from control_plane.fresh_conversation import FreshConversationOwner
from control_plane.principal_projection import neutral_principal_projection
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_executive_app.gateway import AppPolicies
from tests.test_fresh_conversation_http import mounted,post,rsa_key
from tests.test_fresh_conversation import cleanup
from tests import test_mastermind_executive_app_asgi as auth


def _principal(raw):return neutral_principal_projection(**{**raw,"scopes":tuple(raw["scopes"])})


def test_actual_fresh_create_new_owner_catalogue_reference_reopen_without_operation_key(tmp_path,rsa_key,monkeypatch):
    async def run():
        app,token,wt,service,runtime,request,adapters,calls,sink=await mounted(tmp_path,rsa_key,monkeypatch)
        try:
            _,preview=await post(app,"preview",request,token,wt)
            _,created=await post(app,"create",{**request,"preview_digest":preview["data"]["preview"]["digest"]},token,wt)
            assert created["ok"]
            principal=_principal(calls[-1]["principal"])
            expected=(principal.policy_id,principal.issuer_digest,principal.resource)
            # New host-owned stateless reader instance; no local operation-key
            # pointer or generic SessionBridge target is supplied or fabricated.
            reader=FreshConversationOwner(service,expected_policy=expected)
            before=runtime.events.list_events()
            catalogue=reader.project_references(principal,{"work_ref":"WS:ONE"})
            assert len(catalogue["entries"])==1 and catalogue["coverage"]["state"]=="COMPLETE"
            reference=catalogue["entries"][0]["reference"]
            assert "operation_key" not in reference and "target_ref" not in reference
            window=FreshConversationOwner(service,expected_policy=expected).read_reference(principal,reference)
            assert window["kind"]=="fresh_native" and window["state"]=="RETAINED"
            assert window["initial_message"]==request["message"] and window["initial_result"]
            assert window["locator"]==created["data"]["locator"] and not window["can_send"]
            assert set(window["epoch"])=={"attempt_id","binding_digest","generation_digest"}
            assert runtime.events.list_events()==before
            for field,value in (("root_event_sha256","0"*64),("root_job_id","JOB-999"),("principal_scope_sha256","0"*64),("work_ref","WS:TWO")):
                with pytest.raises((ValueError,RuntimeError)):
                    reader.read_reference(principal,{**reference,field:value})
            with pytest.raises(ValueError):reader.read_reference(dataclasses.replace(principal,subject_digest="f"*64),reference)
            # Actual independent signed READ policy uses only the existing
            # trusted host pair; no submit principal/capability is constructed.
            policies=AppPolicies(auth._read_policy(),auth._submit_policy())
            verifier=JwtAuthenticator(policy=policies.read,jwks_cache=auth._FakeJwksCache(rsa_key))
            now=int(time.time());read_token=auth._read_token(rsa_key,iat=now-1,nbf=now-1,exp=now+600)
            verified=await verifier.verify_token(read_token,now=now)
            read_principal=neutral_principal_projection(**dataclasses.asdict(verified))
            paired=FreshConversationOwner(service,expected_policy=expected,authorized_policies=policies)
            assert paired.project_references(read_principal,{"work_ref":"WS:ONE"})["entries"]==catalogue["entries"]
            assert paired.read_reference(read_principal,reference)==window
            with pytest.raises(ValueError):reader.read_reference(read_principal,reference)
            with pytest.raises(Exception):paired._current(read_principal)  # READ never grants submit.
            assert runtime.events.list_events()==before and adapters[0].begin_turn_calls==1
            output=os.environ.get("S34_REFERENCE_FIXTURE_OUTPUT")
            if output:
                with Path(output).open("x",encoding="utf-8") as stream:
                    json.dump(dict(schema="mastermind.s34.reference_fixture.v1",source_revision=os.environ["S34_SOURCE_REVISION"],
                        create=created,catalogue=catalogue,window=window,read_only_paired_window=paired.read_reference(read_principal,reference),
                        actual_counts=dict(jobs=2,attempts=1,turns=1,reader_added_events=0),
                        seams=["fixture company/host/catalogue authority","actual signed RS256 resource grants","inert private kernel peer and physical provider"]),stream,ensure_ascii=False,sort_keys=True,indent=2)
        finally:await cleanup(service)
    asyncio.run(run())


@pytest.mark.parametrize("fault",["missing_legacy","wrong_key","wrong_receipt_digest"])
def test_original_key_receipt_never_backfills_inverts_or_adopts_foreign_key(tmp_path,rsa_key,monkeypatch,fault):
    async def run():
        app,token,wt,service,runtime,request,adapters,calls,sink=await mounted(tmp_path,rsa_key,monkeypatch)
        original=runtime.store.append_event
        # A source fixture at the actual original immutable insert, not an edit
        # or trigger bypass. missing_legacy reproduces exact161's absent DATA.
        def write(connection,**kwargs):
            if kwargs.get("event_type")=="JOB_CREATED" and "fresh_conversation_original_request" in (kwargs.get("payload") or {}):
                payload=copy.deepcopy(kwargs["payload"])
                if fault=="missing_legacy":payload.pop("fresh_conversation_original_request")
                elif fault=="wrong_key":payload["fresh_conversation_original_request"]["operation_key"]="another-original-key"
                else:payload["fresh_conversation_original_request"]["creation_digest"]="0"*64
                kwargs["payload"]=payload
            return original(connection,**kwargs)
        monkeypatch.setattr(runtime.store,"append_event",write)
        try:
            _,preview=await post(app,"preview",request,token,wt)
            _,created=await post(app,"create",{**request,"preview_digest":preview["data"]["preview"]["digest"]},token,wt)
            assert created["ok"] and created["data"]["state"]=="CREATED",created
            principal=_principal(calls[-1]["principal"])
            owner=service._fixture_fresh_owner
            row=owner.project_references(principal,{"work_ref":request["work_ref"]})["entries"][0]
            window=owner.read_reference(principal,row["reference"])
            assert window["initial_result"]
            before=runtime.events.list_events()
            consume_ref=dict(work_ref=request["work_ref"],reference=row["reference"],initial_digest=window["initial_result"]["digest"])
            _,refused=await post(app,"consume",consume_ref,token,wt)
            assert not refused["ok"] and runtime.events.list_events()==before
            assert len(runtime.jobs.list_jobs())==2 and len(runtime.attempts.list_attempts())==1 and adapters[0].begin_turn_calls==1
            if fault=="missing_legacy":
                # A still-valid original controller can explicitly consume its
                # genuine original. Only that real record then supplies the key.
                legacy=dict(work_ref=request["work_ref"],operation_key=request["operation_key"],initial_digest=window["initial_result"]["digest"])
                _,kept=await post(app,"consume",legacy,token,wt)
                assert kept["ok"]
                before=runtime.events.list_events()
                _,recovered=await post(app,"consume",consume_ref,token,wt)
                assert recovered["ok"] and recovered["data"]["initial_consumption"]==kept["data"]["initial_consumption"]
                assert runtime.events.list_events()==before
                creation=runtime.store.unique_root_created_event(created["data"]["locator"]["root_job_id"])
                assert "fresh_conversation_original_request" not in creation.payload
        finally:await cleanup(service)
    asyncio.run(run())


def test_admitted_original_without_child_has_readable_absent_turn_not_resend_clearance(tmp_path,rsa_key,monkeypatch):
    async def run():
        app,token,wt,service,runtime,request,adapters,calls,sink=await mounted(tmp_path,rsa_key,monkeypatch)
        async def interrupted(root):raise OSError("fixture closed before child materialization")
        monkeypatch.setattr(service,"_run_coo_cycle",interrupted)
        try:
            _,preview=await post(app,"preview",request,token,wt)
            _,created=await post(app,"create",{**request,"preview_digest":preview["data"]["preview"]["digest"]},token,wt)
            assert not created["ok"] and len(runtime.jobs.list_jobs())==1
            principal=_principal(calls[-1]["principal"])
            owner=service._fixture_fresh_owner
            reference=owner.project_references(principal,{"work_ref":request["work_ref"]})["entries"][0]["reference"]
            window=owner.read_reference(principal,reference)
            assert window["state"]=="ADMITTED" and window["initial_result"] is None
            before=runtime.events.list_events()
            selected=dict(work_ref=request["work_ref"],reference=reference,turn_key="not-yet-created")
            _,status=await post(app,"turn_status",selected,token)
            assert status["ok"] and status["data"]["state"]=="ABSENT" and not status["data"]["can_send"],status
            await post(app,"turn",{**selected,"initial_digest":"0"*64,"message":"No result exists to consume."},token,wt)
            assert runtime.events.list_events()==before and not runtime.attempts.list_attempts() and not adapters
        finally:await cleanup(service)
    asyncio.run(run())
