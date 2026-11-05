"""Real JWT + existing UNIX App-peer + Runtime grant + native COMMIT; fake HTTPS.

Disposable fixtures are source proof, not sealed installation or live enrollment.
"""
import asyncio
import base64
import copy
import dataclasses
import hashlib
import json
import os
import socket
import time
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from control_plane.executive_service import ExecutiveControlService, CeoIngressAppBinding
from integrations.business_mcp_auth.contracts import AUTH_POLICY_SCHEMA, load_resource_policy, subject_digest
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.mastermind_executive_app.gateway import AppPolicies
from integrations.session_bridge.installed_reply_events import RuntimeReplyEventHost, InstalledReplyEventClient
from integrations.session_bridge.reply_policy_selection import ReplyPolicySelection
from integrations.session_bridge.runtime_reply_authorization import capture_reply_authorization, validate_reply_authorization, BoundedReplyAuthorizationUnavailable, policy_fingerprint
from integrations.session_bridge.runtime_reply_subscriptions import ExecutiveReplyCipher
from integrations.session_bridge.web_reply_event_rpc import EventSubscribeRequest, EventUnsubscribeRequest
from integrations.session_bridge.native_reply import NativeReplyWriter
from integrations.session_bridge.dialogue_reply import AgentDialogueContinueWriter
from integrations.slack_agent_dialogue.service import RELAY_PARENT_ATTESTATION
from tests.test_native_continuation_ack_ingress import submit
from tests.test_native_continuation_ack_ingress import (
    _strict_dialogue_runtime, build_message_v2, WakeLedgerRepository, _material,
    RuntimeFabricTargetProjector, RuntimeCodexTargetProjector, RuntimeSessionReturn,
    requested_record, route_obligation, make_delivery_attempt, mint_nudge_id,
    LedgerPhase, attempt_record, TrustedWorkerWakeAckProjection, replace,
)
from tests.test_session_bridge_parenting_composition import NATIVE
from tests.test_executive_ceo_ingress import short_socket_root, _config

URL = 'https://receiver.example.com/private_fixture_callback'
SECRET = 'whsec_'+base64.b64encode(b'a'*32).decode()

@pytest.fixture
def authenticated_receiver(monkeypatch):
    issuer='https://auth.example.test/'
    raw={'schema':AUTH_POLICY_SCHEMA,'policy_id':'session-profile','resource':'https://exec.example.test/mcp',
         'resource_metadata_url':'https://exec.example.test/.well-known/oauth-protected-resource/mcp',
         'issuer':issuer,'authorization_servers':[issuer],'jwks_uri':issuer+'.well-known/jwks.json',
         'required_scopes':['mastermind.executive.intent.submit','mastermind.executive.read'],
         'allowed_subject_digests':[subject_digest(issuer=issuer,subject='source-fixture-chairman')],
         'allowed_algorithms':['RS256'],'clock_skew_seconds':0,'max_token_lifetime_seconds':900,
         'jwks_cache_ttl_seconds':300,'unknown_kid_refresh_cooldown_seconds':30,'fetch_failure_backoff_seconds':5}
    policy=load_resource_policy(raw)
    read=load_resource_policy({**raw,'policy_id':'session-profile-read','required_scopes':['mastermind.executive.read']})
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    jwk=jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(),as_dict=True)
    class Keys:
        async def key_for(self,kid):
            assert kid=='fixture';return jwk
    now=int(time.time())
    token=jwt.encode({'iss':issuer,'aud':policy.resource,'sub':'source-fixture-chairman','client_id':'fixture-client',
        'scope':' '.join(policy.required_scopes),'iat':now-10,'exp':now+300,'jti':'fixture-jti'},key,algorithm='RS256',headers={'kid':'fixture'})
    verified=asyncio.run(JwtAuthenticator(policy=policy,jwks_cache=Keys()).verify_token(token,now=now))
    monkeypatch.setattr('tests.test_session_bridge_installed.PRINCIPAL',verified)
    return SimpleNamespace(principal=principal_projection(verified),policies=ReplyPolicySelection((AppPolicies(read=read,submit=policy),)),policy=policy,now=[now],token=token)

@pytest.fixture
def native_case(tmp_path, monkeypatch, authenticated_receiver):
    f = _strict_dialogue_runtime(tmp_path, monkeypatch, provider_session_id=NATIVE)
    actor = {'kind':'worker_attempt','job_id':f.sealed.job_id,'attempt_id':f.sealed.attempt_id,'worker_id':'worker-a'}
    prior = build_message_v2(dict(schema='mastermind.agent_dialogue.v2',message_key='asd-prior-result-001',
        message_type='PROGRESS', work_ref=f.parent['work_ref'],commission_ref=f.parent['commission_ref'],
        session_ref=f.parent['session_ref'],actor_ref=actor,reply_to_message_key=None,
        applies_to={'kind':'executive_attempt',**{k:actor[k] for k in ('job_id','attempt_id','worker_id')}},
        summary='Existing result.',body={'stage':'source','completed':'Done.','next':'Continue.'},
        evidence_refs=[],requires_response=False,created_at='2026-09-03T01:00:00Z'))
    repo = WakeLedgerRepository(f.runtime)
    obligation, physical = _material(f, prior)
    repo.append_record(requested_record(obligation, physical_source=physical), obligation=obligation)
    fabric = RuntimeFabricTargetProjector(f.runtime)
    codex = RuntimeCodexTargetProjector(fabric, owner_configured=lambda:True)
    owner = RuntimeSessionReturn(f.runtime, fabric=fabric,codex=codex,socket_path=Path('/private/tmp/fixture.sock'))
    target = fabric.list_targets()[0]
    native = codex.resolve('codex:'+target.target_ref.split(':',1)[1])
    binding = native.reply_binding()
    principal = authenticated_receiver.principal
    args = dict(target_ref=native.target_ref,operation_key=binding.continuation_operation_key,
                instruction='Read the bounded request.',stop_condition='Reply once.')
    ref = owner.bind_request(principal,args)
    request = AgentDialogueContinueWriter._message(request_message=prior,
        context=AgentDialogueContinueWriter._context(binding), instruction=args['instruction'],
        stop_condition=args['stop_condition'],operation_key=args['operation_key'])
    owner.begin_continuation_commit(principal,args,binding=binding,context=AgentDialogueContinueWriter._context(binding),request_message=prior,message=request)
    obligation, physical = _material(f, request)
    repo.append_record(requested_record(obligation,physical_source=physical),obligation=obligation)
    route = route_obligation(obligation,f.registry,binding=f.binding)
    attempt = make_delivery_attempt(obligation,route,attempt_n=1)
    nudge = mint_nudge_id(route.destination_digest,(attempt.attempt_command_id,))
    attempt = replace(attempt,nudge_id=nudge,nudge_attempt_command_ids=(attempt.attempt_command_id,))
    for phase in (LedgerPhase.DELIVERY_ATTEMPT,LedgerPhase.DELIVERED):
        repo.append_record(attempt_record(attempt,phase))
    trusted = TrustedWorkerWakeAckProjection(target_attempt_id=f.sealed.attempt_id,
        process_generation_id=f.generation.process_generation_id,binding_id=f.binding.binding_id,
        binding_generation=f.binding.binding_generation,provider_session_id=NATIVE,
        provider_native_turn_id='turn-original',nudge_id=nudge,
        obligation_ids=(obligation.obligation_id,),terminal_ack_trailer=True)
    return SimpleNamespace(f=f,repo=repo,owner=owner,ref=ref,request=request,prior=prior,args=args,
                           trusted=trusted,obligation=obligation)

@pytest.fixture
def event_case(authenticated_receiver,native_case):
    s=native_case;a=authenticated_receiver
    s.principal=a.principal;s.auth=a;s.event=s.f.runtime.events.get_event_by_command_id('session-bridge-continue:'+s.ref.removeprefix('session-reply-'))
    s.messages=[{'message':copy.deepcopy(s.prior),'primary_ts':'1788000001.123456'},
                {'message':copy.deepcopy(s.request),'primary_ts':'1788000002.123456'}]
    s.http=[];s.fail_http=False;s.http_hook=None
    async def carrier(path,frame,*,before_write=None):
        operation=frame['operation']
        if operation=='read_bound_parent':return {'ok':True,'result':{'attestation':RELAY_PARENT_ATTESTATION,'thread_ts':frame['args']['thread_ts'],'parent':copy.deepcopy(s.f.parent)}}
        if operation=='read_thread':return {'ok':True,'result':{'thread_ts':frame['args']['thread_ts'],'historical_messages':[],'mutated_count':0,'messages':copy.deepcopy(s.messages)}}
        assert operation=='send_message'
        if before_write:await before_write()
        message=frame['args']['message'];binding=s.owner.resolve(native_session_id=NATIVE,operation_key=s.args['operation_key'],in_reply_to=s.request['message_key'])
        with s.owner.native_reply_commit_fence(binding,message,guard=lambda conn:s.owner.require_native_ack(binding,workspace_id='T0BRD2AQXQV',channel_id='C0BSBM78V1N',connection=conn)):
            s.messages.append({'message':copy.deepcopy(message),'primary_ts':'1788000003.123456'})
        return {'ok':True,'result':{'action':'POSTED','message_key':message['message_key'],'fingerprint':message['fingerprint']}}
    s.owner.service_call=carrier
    class HTTPS:
        def request(self,method,path,body=None,headers=None):
            packet=json.loads(body);s.http.append((packet,headers))
            if s.http_hook:s.http_hook(packet)
            if s.fail_http and packet.get('type')!='verification':raise TimeoutError('synthetic lost response')
            self.body=json.dumps({'challenge':packet['challenge']}).encode() if packet.get('type')=='verification' else b'accepted'
        def getresponse(self):return SimpleNamespace(status=200,read=lambda _limit:self.body)
        def close(self):pass
    def dns(*args,**kwargs):return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))]
    s.host=RuntimeReplyEventHost(s.owner,ExecutiveReplyCipher('fixture-key',b'k'*32),a.policies,clock=lambda:a.now[0],enabled=True,resolver=dns,connector=lambda *args:HTTPS())
    return s

async def native_commit(s):
    # Real causal ACK and canonical Runtime COMMIT fences, not a fixture grant.
    submit(s)
    return await NativeReplyWriter(s.owner,native_session_id=NATIVE,socket_path=s.owner.socket_path,service_call=s.owner.service_call)({'operation_key':s.args['operation_key'],'in_reply_to':s.request['message_key'],'text':'Confirmed source finding.','next_step':'Continue original parent.'})

async def with_peer(s,tmp_path,socket_root,call):
    binding=CeoIngressAppBinding(peer_uid=os.geteuid(),armed=True,grounding_provider=SimpleNamespace(observe=lambda:None),reply_event_provider_factory=lambda runtime:s.host.ingress)
    path=socket_root/'events.sock'
    service=ExecutiveControlService(_config(tmp_path,socket_root=socket_root),ceo_ingress_app_binding=binding,ceo_ingress_socket_path=path,ceo_ingress_peer_uid=os.geteuid()+1,ceo_ingress_grounding_provider=binding.grounding_provider)
    service.runtime=s.f.runtime;service._ceo_ingress_ready=True
    server=await asyncio.start_unix_server(service._handle_ceo_ingress_connection,path=path)
    try:
        client=InstalledReplyEventClient(path,s.auth.policies)
        return await call(client,service)
    finally:
        server.close();await server.wait_closed()
        if service._ceo_ingress_tasks:await asyncio.gather(*tuple(service._ceo_ingress_tasks),return_exceptions=True)
        path.unlink(missing_ok=True)


def test_authenticated_existing_peer_persists_then_native_commit_delivers_after_disconnect(event_case,tmp_path,short_socket_root):
    s=event_case
    async def subscribe(client,service):
        assert await client.can_discover(s.principal)
        return await client.subscribe(s.principal,EventSubscribeRequest(s.event.command_id,URL,SECRET,600000))
    receipt=asyncio.run(with_peer(s,tmp_path,short_socket_root,subscribe))
    assert receipt.expires_at==s.principal.expires_at and receipt.persisted
    assert len(s.http)==1 and s.http[0][0]['type']=='verification'
    assert URL not in repr(s.f.runtime.events.list_events(aggregate_type='reply_subscription'))
    # Network request is closed; no raw bearer is stored. Restart uses same
    # Runtime/custody source and canonical reader, not the registration object.
    source=s.host;s.host=RuntimeReplyEventHost(s.owner,ExecutiveReplyCipher('fixture-key',b'k'*32),s.auth.policies,clock=lambda:s.auth.now[0],enabled=True,resolver=source.challenge.resolver,connector=source.challenge.connector)
    native=asyncio.run(native_commit(s));assert native['reply_committed'] and native['parent_consumed'] is False
    results=asyncio.run(s.host.consumer.handle_committed(read_ref=s.ref,message_key=native['message_key'],fingerprint=native['fingerprint']))
    assert results[0]['state']=='TRANSPORT_ACCEPTED_PARENT_UNPROVEN' and results[0]['parent_consumed'] is False
    again=asyncio.run(s.host.consumer.handle_committed(read_ref=s.ref,message_key=native['message_key'],fingerprint=native['fingerprint']))
    assert again[0]['fresh_send'] is False and len(s.http)==2
    assert s.auth.token not in repr(s.f.runtime.events.list_events())


def test_observed_current_policy_removal_tombstones_and_restore_cannot_resurrect(event_case,tmp_path,short_socket_root):
    s=event_case
    async def subscribe(client,service):return await client.subscribe(s.principal,EventSubscribeRequest(s.event.command_id,URL,SECRET,600000))
    receipt=asyncio.run(with_peer(s,tmp_path,short_socket_root,subscribe));native=asyncio.run(native_commit(s))
    old=s.auth.policies._variants
    pair=old[0];s.auth.policies._variants=(AppPolicies(read=dataclasses.replace(pair.read,allowed_subject_digests=('f'*64,)),submit=dataclasses.replace(pair.submit,allowed_subject_digests=('f'*64,))),)
    results=asyncio.run(s.host.consumer.handle_committed(read_ref=s.ref,message_key=native['message_key'],fingerprint=native['fingerprint']))
    assert results[0]['state']=='NOT_SENT' and len(s.http)==1
    assert asyncio.run(s.host.store.read(receipt.subscription_id)) is None
    s.auth.policies._variants=old
    assert asyncio.run(s.host.consumer.handle_committed(read_ref=s.ref,message_key=native['message_key'],fingerprint=native['fingerprint']))==()


def test_grant_clamp_policy_digest_and_read_only_scope(authenticated_receiver):
    a=authenticated_receiver
    value=capture_reply_authorization(a.principal,a.policy,subscription_expires_at=a.now[0]+100,request_ref='request-fixture',read_ref='read-fixture',request_event_sha256='a'*64,now=a.now[0])
    output=validate_reply_authorization(value,a.policy,now=a.now[0])
    assert output.scopes==('mastermind.executive.read',) and output.expires_at==a.now[0]+100
    assert value['source_policy_sha256']==policy_fingerprint(a.policy) and value['source_policy_sha256']!=a.principal.issuer_digest
    for changed in ({**value,'expires_at':a.principal.expires_at+1},{**value,'source_policy_sha256':a.principal.issuer_digest}):
        with pytest.raises(BoundedReplyAuthorizationUnavailable):validate_reply_authorization(changed,a.policy,now=a.now[0])
    with pytest.raises(BoundedReplyAuthorizationUnavailable):validate_reply_authorization(value,a.policy,now=value['expires_at'])


def installed_policy_fixture(s,tmp_path,monkeypatch):
    from ops.executive_os import executive_mcp_entry as entry
    from tests.test_executive_coo_install_binding import base_document
    from integrations.session_bridge.reply_policy_selection import InstalledReplyPolicySelection
    raw=base_document();raw.update(executive_mcp_profile='web_ceo_v3',reply_events_armed=True)
    raw['policies']={k:dataclasses.asdict(v) for k,v in (('read',s.auth.policies._variants[0].read),('submit',s.auth.policy))}
    path=tmp_path/'synthetic-mcp-document.json';path.write_text(json.dumps(raw))
    # Only root ownership of this disposable fixture is simulated. The actual
    # installed validator, file reload, variant selector and policy checks run.
    def fixture_seal(selected):assert Path(selected)==path
    monkeypatch.setattr(entry,'require_sealed_path',fixture_seal)
    policies=InstalledReplyPolicySelection(path,release_sha=raw['release_sha'],peer_uid=raw['service_uid'])
    s.host.policies=policies;s.host.audiences.policies=policies
    return path,raw


def test_installed_selected_policy_reloads_after_queue_and_denies_before_http(event_case,tmp_path,short_socket_root,monkeypatch):
    s=event_case;path,raw=installed_policy_fixture(s,tmp_path,monkeypatch)
    async def subscribe(client,service):return await client.subscribe(s.principal,EventSubscribeRequest(s.event.command_id,URL,SECRET,600000))
    receipt=asyncio.run(with_peer(s,tmp_path,short_socket_root,subscribe));native=asyncio.run(native_commit(s))
    original_to_thread=asyncio.to_thread
    async def queued(func,*args,**kwargs):
        if getattr(func,'__name__',None)=='_send_selected':
            changed=copy.deepcopy(raw)
            changed['policies']['submit']['allowed_subject_digests']=['f'*64]
            path.write_text(json.dumps(changed))
        return await original_to_thread(func,*args,**kwargs)
    monkeypatch.setattr(asyncio,'to_thread',queued)
    observations=asyncio.run(s.host.consumer.handle_committed(read_ref=s.ref,message_key=native['message_key'],fingerprint=native['fingerprint']))
    assert native['reply_committed'] and observations[0]['state']=='NOT_SENT' and len(s.http)==1
    assert asyncio.run(s.host.store.read(receipt.subscription_id)) is None
    path.write_text(json.dumps(raw))
    assert asyncio.run(s.host.consumer.handle_committed(read_ref=s.ref,message_key=native['message_key'],fingerprint=native['fingerprint']))==()


def test_expiry_and_real_unsubscribe_after_commit_withhold_send(event_case,tmp_path,short_socket_root):
    s=event_case
    async def subscribe(client,service):return await client.subscribe(s.principal,EventSubscribeRequest(s.event.command_id,URL,SECRET,600000))
    receipt=asyncio.run(with_peer(s,tmp_path,short_socket_root,subscribe));native=asyncio.run(native_commit(s))
    s.auth.now[0]=receipt.expires_at
    result=asyncio.run(s.host.consumer.handle_committed(read_ref=s.ref,message_key=native['message_key'],fingerprint=native['fingerprint']))
    # Expired subscriber: capture raises BoundedReplyAuthorizationUnavailable
    # before deliver_subscription. No callback is sent and no reservation is made.
    assert result[0]['state']=='UNAVAILABLE' and result[0]['parent_consumed'] is False
    assert len(s.http)==1
    assert s.f.runtime.events.list_events(aggregate_type='reply_subscription_delivery')==[]
    s.auth.now[0]=receipt.expires_at-1
    async def stop(client,service):return await client.unsubscribe(s.principal,EventUnsubscribeRequest(s.event.command_id,URL))
    stopped=asyncio.run(with_peer(s,tmp_path,short_socket_root,stop));assert stopped.committed
    assert asyncio.run(s.host.consumer.handle_committed(read_ref=s.ref,message_key=native['message_key'],fingerprint=native['fingerprint']))==()


def test_post_send_settlement_failure_records_effect_unknown(event_case,tmp_path,short_socket_root):
    s=event_case
    async def subscribe(client,service):return await client.subscribe(s.principal,EventSubscribeRequest(s.event.command_id,URL,SECRET,600000))
    asyncio.run(with_peer(s,tmp_path,short_socket_root,subscribe));native=asyncio.run(native_commit(s))
    original=s.host.store.settle_delivery
    async def fail_settlement(delivery_ref,*,outcome,http_status=None):
        if outcome=='EFFECT_UNKNOWN':
            raise RuntimeError('post-send settlement unknown')
        return await original(delivery_ref,outcome=outcome,http_status=http_status)
    s.host.store.settle_delivery=fail_settlement
    s.fail_http=True
    result=asyncio.run(s.host.consumer.handle_committed(read_ref=s.ref,message_key=native['message_key'],fingerprint=native['fingerprint']))
    assert result[0]['state']=='EFFECT_UNKNOWN' and result[0]['parent_consumed'] is False
    assert len(s.http)==2 and s.http[1][0].get('type')!='verification'
    started=s.f.runtime.events.list_events(aggregate_type='reply_subscription_delivery')
    assert [event.event_type for event in started]==['REPLY_DELIVERY_STARTED']
    s.host.store.settle_delivery=original
    s.fail_http=False
    again=asyncio.run(s.host.consumer.handle_committed(read_ref=s.ref,message_key=native['message_key'],fingerprint=native['fingerprint']))
    assert again[0]['fresh_send'] is False and again[0]['state']=='EFFECT_UNKNOWN' and len(s.http)==2


def test_callback_failure_preserves_native_receipt_and_unknown_reservation(event_case,tmp_path,short_socket_root):
    s=event_case
    async def subscribe(client,service):return await client.subscribe(s.principal,EventSubscribeRequest(s.event.command_id,URL,SECRET,600000))
    asyncio.run(with_peer(s,tmp_path,short_socket_root,subscribe));native=asyncio.run(native_commit(s));s.fail_http=True
    before=copy.deepcopy(native)
    results=asyncio.run(s.host.consumer.handle_committed(read_ref=s.ref,message_key=native['message_key'],fingerprint=native['fingerprint']))
    assert native==before and native['reply_committed'] and results[0]['state']=='EFFECT_UNKNOWN'
    again=asyncio.run(s.host.consumer.handle_committed(read_ref=s.ref,message_key=native['message_key'],fingerprint=native['fingerprint']))
    assert again[0]['fresh_send'] is False and len(s.http)==2


def test_default_off_composition_does_not_read_policy_key_or_enter_private_owner(monkeypatch):
    from integrations.session_bridge.reply_event_host_composition import build_installed_reply_event_host
    from integrations.session_bridge.installed_reply_events import build_installed_reply_event_rpc
    def prohibited(*args,**kwargs):raise AssertionError('disarmed path performed custody I/O')
    monkeypatch.setattr('integrations.session_bridge.reply_event_host_composition._provisioned_cipher',prohibited)
    monkeypatch.setattr('integrations.session_bridge.reply_event_host_composition.InstalledReplyPolicySelection',prohibited)
    assert build_installed_reply_event_host(None,None,release_sha=None,peer_uid=None,dialogue_socket_path=None,native_owner_configured=None) is None
    assert build_installed_reply_event_rpc(None,None,clock=None) is None


def test_existing_executive_post_commit_consumer_keeps_receipt_on_callback_loss(event_case,tmp_path,short_socket_root):
    s=event_case
    async def subscribe(client,service):return await client.subscribe(s.principal,EventSubscribeRequest(s.event.command_id,URL,SECRET,600000))
    asyncio.run(with_peer(s,tmp_path,short_socket_root,subscribe));native=asyncio.run(native_commit(s));s.fail_http=True
    binding=CeoIngressAppBinding(peer_uid=os.geteuid(),armed=True,grounding_provider=SimpleNamespace(observe=lambda:None),reply_event_provider_factory=lambda runtime:s.host.ingress)
    path=short_socket_root/'unused.sock'
    service=ExecutiveControlService(_config(tmp_path,socket_root=short_socket_root),ceo_ingress_app_binding=binding,ceo_ingress_socket_path=path,ceo_ingress_peer_uid=os.geteuid()+1,ceo_ingress_grounding_provider=binding.grounding_provider)
    service.runtime=s.f.runtime;service._company_consultation_host=SimpleNamespace(reply_event_consumer=s.host.consumer)
    before=copy.deepcopy(native)
    asyncio.run(service._notify_native_reply_events(s.ref,native))
    assert native==before and native['reply_committed'] and len(s.http)==2 and service._service_state=='READY'
    asyncio.run(service._notify_native_reply_events(s.ref,native));assert len(s.http)==2


def test_policy_change_during_dns_is_rechecked_before_request_and_tombstoned(event_case,tmp_path,short_socket_root):
    s=event_case
    async def subscribe(client,service):return await client.subscribe(s.principal,EventSubscribeRequest(s.event.command_id,URL,SECRET,600000))
    receipt=asyncio.run(with_peer(s,tmp_path,short_socket_root,subscribe));native=asyncio.run(native_commit(s))
    original=s.host.delivery._resolver
    def changed_dns(*args,**kwargs):
        pair=s.auth.policies._variants[0]
        s.auth.policies._variants=(AppPolicies(read=pair.read,submit=dataclasses.replace(pair.submit,allowed_subject_digests=('f'*64,))),)
        return original(*args,**kwargs)
    s.host.delivery._resolver=changed_dns
    observations=asyncio.run(s.host.consumer.handle_committed(read_ref=s.ref,message_key=native['message_key'],fingerprint=native['fingerprint']))
    assert observations[0]['state']=='NOT_SENT' and len(s.http)==1
    assert asyncio.run(s.host.store.read(receipt.subscription_id)) is None


def test_existing_private_peer_refuses_foreign_runtime_before_callback(event_case,tmp_path,short_socket_root):
    s=event_case
    async def attempt(client,service):
        from common.reply_subscription_private_contract import ReplyEventIngressOwner
        alien=ReplyEventIngressOwner(object(),s.host.validate_frame,s.host.handle_frame)
        service._ceo_ingress_app_binding=dataclasses.replace(service._ceo_ingress_app_binding,reply_event_provider_factory=lambda runtime:alien)
        assert await client.can_discover(s.principal) is False
    asyncio.run(with_peer(s,tmp_path,short_socket_root,attempt));assert s.http==[]


def test_sealed_policy_and_missing_key_fail_closed_without_custody_bypass(tmp_path):
    from integrations.session_bridge.reply_policy_selection import InstalledReplyPolicySelection, ReplyPolicyUnavailable
    from integrations.session_bridge.reply_event_host_composition import _provisioned_cipher
    path=tmp_path/'unsealed-key';path.write_bytes(b'k'*32)
    with pytest.raises(ValueError):_provisioned_cipher(path,'fixture',control_uid=os.geteuid())
    with pytest.raises(ReplyPolicyUnavailable):InstalledReplyPolicySelection(tmp_path/'missing.json',release_sha='a'*40,peer_uid=458)


def test_installed_event_opt_in_is_closed_and_service_refuses_before_activation(tmp_path,monkeypatch):
    from ops.executive_os import executive_mcp_entry as entry
    from scripts import executive_os_phase1c as service_entry
    from tests.test_executive_coo_install_binding import base_document
    from tests.test_c1_ceo_ingress_composition import _raw
    from control_plane.executive_service import ServiceError
    raw=base_document()
    assert entry.validate_document(raw).get('reply_events_armed',False) is False
    with pytest.raises(ValueError):entry.validate_document({**raw,'reply_events_armed':True})
    assert entry.validate_document({**raw,'executive_mcp_profile':'web_ceo_v3','reply_events_armed':True})['reply_events_armed'] is True
    with pytest.raises(ValueError):entry.validate_document({**raw,'reply_events_armed':'true'})
    def no_activation(*args,**kwargs):raise AssertionError('unqualified event host activated a listener')
    monkeypatch.setattr(service_entry,'activate_launchd_socket',no_activation)
    config=_raw(tmp_path)
    config['reply_events']={'armed':True,'mcp_config_path':'/fixture/mcp.json','storage_key_path':'/fixture/reply.key','storage_key_id':'fixture'}
    with pytest.raises(ServiceError,match='armed App/native Company'):
        service_entry._service_from_config(config)


def test_provisioned_key_uses_existing_control_owner_private_mode_and_sealed_parent(tmp_path,monkeypatch):
    from ops.executive_os import executive_mcp_entry as entry
    from integrations.session_bridge.reply_event_host_composition import _provisioned_cipher
    path=tmp_path/'synthetic-control-key';path.write_bytes(b'k'*32);path.chmod(0o600)
    checked=[]
    def fixture_parent(selected,*,directory=False):
        assert Path(selected)==tmp_path and directory is True
        checked.append(selected)
    monkeypatch.setattr(entry,'require_sealed_path',fixture_parent)
    assert type(_provisioned_cipher(path,'fixture',control_uid=os.geteuid())) is ExecutiveReplyCipher
    assert checked==[tmp_path]
    path.chmod(0o640)
    with pytest.raises(ValueError):_provisioned_cipher(path,'fixture',control_uid=os.geteuid())
    path.chmod(0o600)
    with pytest.raises(ValueError):_provisioned_cipher(path,'fixture',control_uid=os.geteuid()+1)
    other=tmp_path/'other';other.symlink_to(path)
    with pytest.raises(OSError):_provisioned_cipher(other,'fixture',control_uid=os.geteuid())


def test_installed_host_factory_composes_actual_runtime_read_and_company_consumer(event_case,tmp_path,monkeypatch):
    from integrations.session_bridge import reply_event_host_composition as composition
    from integrations.company_consultation_host import CompanyConsultationHost
    s=event_case
    monkeypatch.setattr(composition,'InstalledReplyPolicySelection',lambda *args,**kwargs:s.auth.policies)
    seen=[]
    def existing_key(path,key_id,*,control_uid):
        seen.append((path,key_id,control_uid))
        return ExecutiveReplyCipher('fixture-key',b'k'*32)
    monkeypatch.setattr(composition,'_provisioned_cipher',existing_key)
    host=composition.build_installed_reply_event_host(s.f.runtime,
        {'armed':True,'mcp_config_path':'/fixture/mcp.json','storage_key_path':'/fixture/reply.key','storage_key_id':'fixture-key'},
        release_sha='a'*40,peer_uid=458,control_uid=os.geteuid(),
        dialogue_socket_path=s.owner.socket_path,native_owner_configured=lambda:True,service_call=s.owner.service_call)
    assert type(host) is RuntimeReplyEventHost and host.runtime is s.f.runtime
    assert host.returns.runtime is s.f.runtime and host.returns.service_call is s.owner.service_call
    assert host.consumer.runtime is s.f.runtime and host.ingress.runtime is s.f.runtime
    assert seen==[('/fixture/reply.key','fixture-key',os.geteuid())]
    # Exact Company owner consumes this host; its constructor validates Runtime.
    company=CompanyConsultationHost(runtime=s.f.runtime,repository_root=tmp_path,
        worker_uid=os.geteuid()+1,relay_socket_path=s.owner.socket_path,
        workspace_id='T0BRD2AQXQV',channel_id='C0BSBM78V1N',native_return_armed=True,reply_event_host=host)
    assert company.reply_event_consumer is host.consumer


def test_executive_native_postcommit_scheduler_receives_canonical_message_not_writer_receipt(event_case,tmp_path,short_socket_root):
    """The production source reads the committed Dialogue message, not native writer receipt."""
    from common.reply_subscription_private_contract import ReplyEventCommitConsumer
    s=event_case
    async def subscribe(client,service):
        return await client.subscribe(s.principal,EventSubscribeRequest(s.event.command_id,URL,SECRET,600000))
    asyncio.run(with_peer(s,tmp_path,short_socket_root,subscribe))
    assert len(s.http)==1
    native=asyncio.run(native_commit(s))
    assert native["reply_committed"] is True
    canonical=asyncio.run(s.owner.require_committed_native_reply(read_ref=s.ref))
    assert canonical["message_type"]=="PROGRESS"
    assert canonical["body"]["stage"]=="message_reply"
    assert "reply_committed" not in canonical
    assert canonical["message_key"]==native["message_key"]
    assert canonical["fingerprint"]==native["fingerprint"]

    binding=CeoIngressAppBinding(peer_uid=os.geteuid(),armed=True,
        grounding_provider=SimpleNamespace(observe=lambda:None),
        reply_event_provider_factory=lambda runtime:s.host.ingress)
    service=ExecutiveControlService(
        _config(tmp_path,socket_root=short_socket_root),
        ceo_ingress_app_binding=binding,
        ceo_ingress_socket_path=short_socket_root/'unarmed-test.sock',
        ceo_ingress_peer_uid=os.geteuid()+1,
        ceo_ingress_grounding_provider=binding.grounding_provider,
    )
    service.runtime=s.f.runtime
    service._service_state="READY"
    service._company_consultation_host=SimpleNamespace(reply_event_consumer=s.host.consumer)
    async def scheduled():
        service._schedule_native_reply_events(s.ref,canonical)
        for pending in tuple(service._physical_workers):
            await asyncio.wait_for(pending,timeout=5)
    asyncio.run(scheduled())
    assert len(s.http)==2, "exact committed reply must reach bound subscriber"
    assert s.http[1][0]["name"]=="session.reply_committed"
    assert s.http[1][0]["data"]["read_ref"]==s.ref
    assert s.http[1][0]["data"]["parent_consumed"] is False
