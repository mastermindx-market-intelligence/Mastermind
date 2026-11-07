"""Same-CONTINUE acknowledgment through production ingress on real Runtime."""
from dataclasses import replace
import hashlib
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.session_targets import route_obligation
from control_plane.wake_dispatcher import mint_nudge_id
from control_plane.wake_ledger import LedgerPhase, attempt_record, make_delivery_attempt, requested_record
from control_plane.wake_persist import WakeLedgerRepository
from control_plane.wake_ack_ingress import TrustedWorkerWakeAckProjection, WakeAckClaim, WakeAckIngressError, acknowledge_consumed_wakes
from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector, RuntimeCodexTargetProjector
from integrations.session_bridge.runtime_return import RuntimeSessionReturn
from integrations.session_bridge.dialogue_reply import AgentDialogueContinueWriter
from integrations.slack_agent_dialogue.contract_v2 import build_message_v2
from tests.test_executive_service import _strict_dialogue_runtime
from tests.test_session_bridge_parenting_composition import _material, NATIVE
from tests.test_session_bridge_installed import principal_frame
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.business_mcp_auth.principal_projection import principal_projection


@pytest.fixture
def native_case(tmp_path, monkeypatch):
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
    p = principal_frame()
    p['issued_at'],p['expires_at'] = int(time.time())-60,int(time.time())+3600
    p['scopes'] = tuple(p['scopes'])
    principal = principal_projection(VerifiedPrincipal(**p))
    args = dict(target_ref=native.target_ref,operation_key=binding.continuation_operation_key,
                instruction='Read the bounded request.',stop_condition='Reply once.')
    ref = owner.bind_request(principal,args)
    request = AgentDialogueContinueWriter._message(request_message=prior,
        context=AgentDialogueContinueWriter._context(binding), instruction=args['instruction'],
        stop_condition=args['stop_condition'],operation_key=args['operation_key'])
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


def submit(s, trusted=None):
    return acknowledge_consumed_wakes(s.f.runtime,s.f.registry,
        claim=WakeAckClaim((s.obligation.obligation_id,)),trusted=trusted or s.trusted)


def test_same_continue_ingress_persists_exact_native_evidence(native_case):
    s = native_case
    result = submit(s)
    assert len(result)==1 and result[0].inserted
    evidence = result[0].record.ack.native_continuation
    assert evidence.process_generation_id == s.trusted.process_generation_id
    assert evidence.native_session_sha256 == hashlib.sha256(NATIVE.encode()).hexdigest()
    assert evidence.native_turn_sha256 == hashlib.sha256(b'turn-original').hexdigest()
    assert evidence.target_attempt_id == s.f.sealed.attempt_id
    assert s.repo.get_by_command_id(result[0].event.command_id).record == result[0].record
    binding = s.owner.resolve(native_session_id=NATIVE,operation_key=s.args['operation_key'],
                              in_reply_to=s.request['message_key'])
    assert s.owner.require_native_ack(binding,workspace_id='T0BRD2AQXQV',channel_id='C0BSBM78V1N') == result[0].event.command_id
    assert submit(s)[0].inserted is False


@pytest.mark.parametrize('field,value', [('provider_session_id','foreign-session'),
    ('process_generation_id','GEN-other'),('binding_generation',99),('binding_id','bind-other')])
def test_same_source_is_not_permission_for_stale_target(native_case, field, value):
    s = native_case
    with pytest.raises(WakeAckIngressError):
        submit(s,replace(s.trusted,**{field:value}))
    assert not any(e.event_type=='TARGET_ACKNOWLEDGED' for e in s.f.runtime.events.list_events())


def test_changed_native_turn_cannot_replay_prior_ack(native_case):
    s = native_case
    submit(s)
    with pytest.raises(WakeAckIngressError):
        submit(s,replace(s.trusted,provider_native_turn_id='different-turn'))


def test_same_attempt_without_original_continue_cannot_ack(native_case):
    s = native_case
    # The prior ordinary result also has the same native Attempt as its source.
    # Delivering it must not turn source identity into acknowledgment authority.
    oid, physical = _material(s.f, s.prior)
    route = route_obligation(oid,s.f.registry,binding=s.f.binding)
    attempt = make_delivery_attempt(oid,route,attempt_n=1)
    nudge = mint_nudge_id(route.destination_digest,(attempt.attempt_command_id,))
    attempt = replace(attempt,nudge_id=nudge,nudge_attempt_command_ids=(attempt.attempt_command_id,))
    for phase in (LedgerPhase.DELIVERY_ATTEMPT,LedgerPhase.DELIVERED):
        s.repo.append_record(attempt_record(attempt,phase))
    trusted = replace(s.trusted,nudge_id=nudge,obligation_ids=(oid.obligation_id,))
    with pytest.raises(WakeAckIngressError):
        acknowledge_consumed_wakes(s.f.runtime,s.f.registry,claim=WakeAckClaim(trusted.obligation_ids),trusted=trusted)


def test_current_writer_contract_refuses_wrong_observed_native_turn():
    from tests.test_codex_app_server_wake_rpc import (_worker_projection, FakeRemoteAttentionAdapter,
        _deliver_via_wake_client, GENERATION, NATIVE_HANDLE, NUDGE_ID, ACK_OPAQUE_IDS)
    from control_plane.operator_harness_contract import AttentionTurnObservation
    with pytest.raises((ValueError, RuntimeError)):
        adapter=FakeRemoteAttentionAdapter(response=AttentionTurnObservation(
            process_generation_id=GENERATION.process_generation_id,provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,provider_native_turn_id='actual-turn',accepted=True,delivered=True,
            wake_ack_projection=_worker_projection()))
        _deliver_via_wake_client(adapter,opaque_ids=ACK_OPAQUE_IDS)
