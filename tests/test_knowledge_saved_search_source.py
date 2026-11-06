"""One canonical project + genuine owned saved reply; no live session/provider.

Existing Runtime original/grant/crypto owners and signed Executive READ are real.
Native admission/carrier and Workspace enrollment are explicit hermetic premises.
No captured/projected row is relabelled and no target is derived from the project.
"""
import asyncio
import copy
import json
import hashlib
import os
import time
from pathlib import Path
from types import SimpleNamespace

from tests.test_session_bridge_runtime_return import setup, bind
from tests.test_project_plan_continuity import owner
from tests import test_mastermind_os_session_transport as http
from tests.test_mastermind_executive_app_asgi import rsa_key
from tests.knowledge_recipe_test_support import canonical_workstream
from tests.fresh_conversation_full_cache import CanonicalFixtureCache
from tests.test_workspace_project_git_publisher import git, rev_parse
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.mastermind_executive_app.gateway import AppPolicies, TRANSPORT_SENT_OK
from integrations.session_bridge.runtime_return import RuntimeSessionReturn
from integrations.session_bridge.native_read import NativeReplyReader
from integrations.session_bridge.installed import InstalledSessionBridgeProvider


def test_actual_scoped_history_read_and_saved_reply_without_current_target(setup,owner,rsa_key,tmp_path,monkeypatch):
    s=setup;app,peer,clock,_=http.make_app(rsa_key)
    now=int(time.time());monkeypatch.setattr(http.auth_fixture,'NOW',now);clock[0]=now
    submit_token=http.auth_fixture._submit_token(rsa_key)
    principal=asyncio.run(app._submit_pair[1].verify_token(submit_token,now=now))
    s.principal=principal;s.projection=principal_projection(principal)
    s.owner=RuntimeSessionReturn(s.runtime,fabric=s.owner.fabric,codex=s.owner.codex,
        socket_path=s.owner.socket_path,service_call=s.service,
        authorized_policies=AppPolicies(read=app._read_pair[1].policy,submit=app._submit_pair[1].policy))
    # Select the genuine incumbent Fabric view BEFORE original admission.
    # Native Codex refs intentionally remain outside the older Saved READ API.
    s.binding=s.target.reply_binding()
    s.args.update(target_ref=s.binding.target_ref,operation_key=s.binding.continuation_operation_key)
    original=bind(s)
    from integrations.session_bridge.dialogue_reply import AgentDialogueContinueWriter
    from integrations.slack_agent_dialogue.contract_v2 import MESSAGE_SCHEMA_V2,build_message_v2
    request=AgentDialogueContinueWriter._message(request_message={'message_key':s.binding.reply_to_message_key,'created_at':'2026-10-01T20:00:00Z'},
        context=AgentDialogueContinueWriter._context(s.binding),instruction=s.args['instruction'],stop_condition=s.args['stop_condition'],operation_key=s.args['operation_key'])
    _,value=s.owner._stored_request(original);context=value['context']
    reply_key='asd-native-reply-'+hashlib.sha256(('mastermind.session_bridge.native_reply.v1\n'+s.args['operation_key']).encode()).hexdigest()[:40]
    message=build_message_v2({'schema':MESSAGE_SCHEMA_V2,'message_key':reply_key,'message_type':'PROGRESS',
        **{k:context[k] for k in ('work_ref','commission_ref','session_ref','actor_ref','applies_to')},
        'reply_to_message_key':request['message_key'],'summary':'Bounded fixture reply.',
        'body':{'stage':'message_reply','completed':'The bounded finding is confirmed.','next':'Continue the parent task.'},
        'evidence_refs':[],'requires_response':False,'created_at':request['created_at']})
    s.service.items=[{'message':request,'primary_ts':'1788000001.123456'},{'message':message,'primary_ts':'1788000002.123456'}]
    s.enabled[0]=False;monkeypatch.setattr(s.owner.fabric,'resolve',lambda _ref:None);s.service.calls.clear()
    def no_effect(*_args,**_kwargs):raise AssertionError('Saved READ must not discover a target or modify a session')
    reply=NativeReplyReader(s.owner,socket_path=Path('/private/tmp/no-live-saved-search.sock'),service_call=s.service,projected_principal=True)
    provider=InstalledSessionBridgeProvider(target_projector=no_effect,reply_handler=no_effect,summon_handler=no_effect,
        reply_read_handler=reply,reference_handler=lambda who,args:s.owner.session_reply_references(principal=who,**args))
    frames=[]
    async def send_frame(_path,frame):
        frames.append(copy.deepcopy(frame))
        return SimpleNamespace(transport=TRANSPORT_SENT_OK,ok=True,result=await provider.handle_frame(frame))
    peer.send_frame=send_frame
    work=s.binding.work_ref;token=http.auth_fixture._read_token(rsa_key)
    read_who=asyncio.run(app._read_pair[1].verify_token(token,now=now))
    before=s.runtime.events.list_events()
    context_status,context=http.request(app,token,'history_context',{'selection':{'work_ref':work}},
        raw_path=b'/os/executive/session/history-context',scope_changes={'path':'/os/executive/session/history-context'})
    assert context_status==200 and context['data']['selection']=={'work_ref':work},context
    # Diagnostic selects the SAME pure source on the same temporary Runtime;
    # does not authorize a public response or change any guard/budget.
    direct=s.owner.session_reply_references(principal=principal_projection(read_who),work_ref=work,page_size=4)
    assert len(direct['references'])==1,direct
    refs_status,refs=http.request(app,token,'references',{'arguments':{'work_ref':work,'page_size':4}})
    assert refs_status==200 and len(refs['data']['references'])==1,refs
    reference=refs['data']['references'][0]
    assert reference['work_ref']==work and reference['read_ref']==original
    reply_status,answer=http.request(app,token,'reply',{'arguments':{'operation_key':reference['operation_key']}})
    assert reply_status==200 and answer['data']['text']=='The bounded finding is confirmed.',answer
    assert answer['data']['parent_consumed'] is False
    assert all(frame['tool'] in ('session_reply_read','session_reply_references') for frame in frames)
    assert s.runtime.events.list_events()==before and all(c['operation']=='read_thread' for c in s.service.calls)
    # Seed an actual canonical fixture workstream BEFORE publication. The code
    # and Store/CCR reducer project it; no output row/ref/clock is rewritten.
    root=Path(owner.__file__).parents[1]
    record=root/'agentos/workstreams'/('WS-'+work[3:]+'.md');record.parent.mkdir(parents=True)
    record.write_text(canonical_workstream().replace('ALPHA',work[3:]))
    from tests.test_agentos_project_knowledge import canonical_decision
    decision=root/'agentos/decisions/DEC-EARLIER-CALL.md';decision.parent.mkdir(parents=True)
    decision.write_text(canonical_decision().replace('ALPHA',work[3:]))
    git(root,'init','-q')
    git(root,'config','user.name','Source fixture')
    git(root,'config','user.email','source-fixture@example.invalid')
    git(root,'add','.');git(root,'commit','-m','Canonical saved-search source fixture')
    cache=CanonicalFixtureCache(root,tmp_path/'canonical',mastermind_revision=rev_parse(Path.cwd(),'HEAD'))
    from tests import test_workspace_read_app as workspace_http
    from tests.test_workspace_project_authoring_grant import project_bindings
    from integrations.mastermind_workspace_app.contract import principal_frame,workspace_authorizers
    from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
    from control_plane.workspace_read_service import WorkspaceReadService
    auth=workspace_http._authenticator(rsa_key)
    encoded=workspace_http._workspace_token(rsa_key,iat=now-10,nbf=now-10,exp=now+600)
    who=asyncio.run(auth.verify_authorization_header('Bearer '+encoded,now=now))
    _,bindings=project_bindings(selected=None)
    for slot in bindings['profiles'].values():slot.update(enabled=False,binding=None)
    bindings['profiles'][bindings['primary_profile']].update(enabled=True,binding=dict(principal_frame(who),permission_digest='a'*64))
    _,authorize=workspace_authorizers(policy=auth.policy,load_bindings=lambda:legacy_workspace_document(bindings,auth.policy))
    reader=WorkspaceReadService(cache=cache.cache,runtime=s.runtime,authorize=authorize,armed={},runtime_identity={})
    programs=asyncio.run(reader.handle_frame({'schema':'mastermind.executive_workspace_read.v1','operation':'programs',
        'selection':None,'principal':principal_frame(who)}))
    assert programs['ok'] and any(row['work_ref']==work for row in programs['result']['control_room']['work']),programs
    output={'work_ref':work,'programs':programs['result'],'history_context':context,'references':refs,'reply':answer,
        'executive_context':{'schema':'mastermind.os.executive.owner_context.v1','principal_scope':context['data']['principal_scope'],
            'verified_expiry':context['data']['verified_expiry'],'profile':{'name':'web_ceo_v3','server_version':'1.5.0'}},
        'source':cache.provenance(),'clock_seconds':now,'no_current_target':True,'read_only_event_count':len(before)}
    destination=os.environ.get('MMOS_KNOWLEDGE_SAVED_FIXTURE')
    if destination:Path(destination).write_text(json.dumps(output,ensure_ascii=False,sort_keys=True))
