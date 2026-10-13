"""Actual host factory/Runtime/Unix Relay composition; kernel and Slack are fixtures."""
import asyncio
from decimal import Decimal
import json
import os
import sqlite3
from types import SimpleNamespace

import pytest

from integrations.company_consultation_host import CompanyConsultationHost
from integrations import native_reply_host as module
from integrations.mastermind_company_mcp import native_return as contract
from integrations.slack_agent_dialogue.contract_v2 import render_parent_v2, render_message_v2
from integrations.slack_agent_dialogue.engine import DialogueEngine, DialoguePolicy, SlackMessage
from integrations.slack_agent_dialogue.engine_v2 import DialogueEngineV2
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
from integrations.slack_agent_dialogue.service import AgentDialogueService, ServiceConfig, DialogueServiceError
from integrations.slack_agent_dialogue import runtime as relay_runtime
from tests.test_slack_agent_dialogue_engine_v2 import ExactV2AuthorityPolicy
from tests.test_native_continuation_ack_ingress import native_case, submit


@pytest.mark.parametrize('fault', ['none', 'concurrent', 'lost_return', 'unknown_absent', 'handoff', 'unconsumed'])
def test_host_native_reply_uses_real_factory_and_commit_fence(native_case, short_socket_root, tmp_path, monkeypatch, fault):
    s, f = native_case, native_case.f
    if fault != 'unconsumed':
        submit(s)
    state = {'retired':False, 'commits':0, 'reads':0, 'closed':0}
    class AuthenticatedFixtureAuthority:
        def __init__(self, **kwargs):
            self.closed = False
        def revalidate(self, *, connection=None):
            assert not self.closed
            if state['retired']:
                raise ValueError('host process retired')
            return SimpleNamespace(binding=f.runtime.current_harness_binding_source(
                f.sealed.attempt_id, connection=connection))
        def close(self):
            self.closed = True
            state['closed'] += 1
    monkeypatch.setattr(module,'NativeReturnCallerAuthority',AuthenticatedFixtureAuthority)
    original_write = asyncio.StreamWriter.write
    def write(writer, raw):
        value = json.loads(raw)
        if value.get('commit') == 'COMMIT':
            state['commits'] += 1
            with sqlite3.connect(f.runtime.store.path, timeout=0) as competitor:
                with pytest.raises(sqlite3.OperationalError, match='locked'):
                    competitor.execute('BEGIN IMMEDIATE')
            assert any(e.event_type=='SESSION_BRIDGE_NATIVE_REPLY_COMMIT_STARTED'
                       for e in f.runtime.events.list_events())
        return original_write(writer,raw)
    monkeypatch.setattr(asyncio.StreamWriter,'write',write)
    actual_service = module.call_service
    async def service(path, request, **kwargs):
        response = await actual_service(path,request,**kwargs)
        if request['operation']=='read_thread':
            state['reads'] += 1
            if fault=='handoff' and state['reads']==2:
                state['retired']=True
        elif fault in {'lost_return','unknown_absent'}:
            raise DialogueServiceError('SEND_EFFECT_UNKNOWN')
        return response
    monkeypatch.setattr(module,'call_service',service)

    async def scenario():
        bot='U0RELAY001'
        client=InMemorySlackClient(relay_bot_user_id=bot)
        thread='1788000000.123456'
        client.add_parent(SlackMessage(ts=thread,author_user_id=bot,text=render_parent_v2(f.parent)))
        for timestamp,message in [('1788000001.123456',s.prior),('1788000002.123456',s.request)]:
            client.add_reply(SlackMessage(ts=timestamp,author_user_id=bot,text=render_message_v2(message),thread_ts=thread))
        client.next_timestamp=Decimal('1788000010.000001')
        policy=DialoguePolicy(workspace_id='T0BRD2AQXQV',channel_id='C0BSBM78V1N',relay_bot_user_id=bot,
            allowed_sol_user_ids=('U0BRETDUAS2',),allowed_parent_user_ids=(bot,),poll_interval_seconds=0,method_timeout_seconds=1)
        authority=ExactV2AuthorityPolicy()
        path=short_socket_root/'native-return.sock'
        relay=AgentDialogueService(ServiceConfig(socket_path=path,allowed_peer_uids=(os.geteuid(),)),
            DialogueEngine(policy,client,authority_policy=authority),
            engine_v2=DialogueEngineV2(policy,client,authority_policy=authority,
                                      active_waiter_registry=relay_runtime.ActiveWaiterRegistry()))
        await relay.start()
        try:
            host=CompanyConsultationHost(runtime=f.runtime,repository_root=tmp_path,worker_uid=451,
                relay_socket_path=path,workspace_id=policy.workspace_id,channel_id=policy.channel_id,native_return_armed=True)
            frame=contract.encode_request(contract.TOOL_NAME,dict(operation_key=s.args['operation_key'],
                in_reply_to=s.request['message_key'],text='Finding is confirmed.',next_step='Return to parent.'))
            async def call():
                return json.loads(await host.call('authenticated-fixture',frame))
            if fault=='concurrent':
                results=await asyncio.gather(call(),call())
                assert sum(result['ok'] for result in results)>=1,results
                assert state['commits']==client.post_call_count==1
            else:
                first=await call()
                if fault in {'handoff','unconsumed'}:
                    assert not first['ok'],first
                    assert state['commits']==client.post_call_count==0
                    return
                if fault=='none':
                    assert first['ok'],first
                    assert first['data']['parent_consumed'] is False
                else:
                    assert first['error']['code']=='EFFECT_UNKNOWN',first
                if fault=='unknown_absent':
                    client.thread_messages[thread]=client.thread_messages[thread][:2]
                second=await call()
                if fault=='unknown_absent':
                    assert second['error']['code']=='EFFECT_UNKNOWN',second
                else:
                    assert second['ok'] and second['data']['action']=='DUPLICATE',second
                assert state['commits']==client.post_call_count==1
        finally:
            await relay.close()
    asyncio.run(scenario())
    assert state['closed']>=1
