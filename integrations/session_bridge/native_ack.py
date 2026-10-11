"""Join an authenticated same-CONTINUE ACK to immutable original request evidence."""
import hashlib

from control_plane.wake_ledger import NativeContinuationAckEvidence, LedgerPhase
from integrations.session_bridge.runtime_return import stored_continuation_request, _generation, _digest, _epoch
from integrations.workspace_agent_runtime_binding import _read_current_target


def native_continuation_ack_evidence(runtime, requested, delivered, trusted, *, connection):
    obligation, source = requested.obligation, requested.physical_source
    if (source is None or obligation is None or obligation.attempt_id != trusted.target_attempt_id
            or obligation.wake_kind != 'dialogue_turn_pending'
            or obligation.source_kind != 'agent_dialogue_attention'
            or delivered.phase is not LedgerPhase.DELIVERED or delivered.reasoning_surface != 'codex'
            or delivered.wake_transport != 'codex-app-server' or delivered.nudge_id != trusted.nudge_id):
        raise ValueError('not an authenticated native continuation')
    events = runtime.store.list_events(aggregate_type='session_bridge_continue',
        attempt_id=trusted.target_attempt_id, connection=connection)
    if len(events) > 256:
        raise ValueError('continuation evidence exceeds bound')
    matches = [event for event in events if event.event_type == 'SESSION_BRIDGE_CONTINUE_REQUESTED'
               and event.payload.get('request_message_key') == source.predecessor_message_key]
    if len(matches) != 1:
        raise ValueError('exact original CONTINUE unavailable')
    event, value = stored_continuation_request(runtime, matches[0].payload['read_ref'])
    facts = runtime.current_harness_binding_source(trusted.target_attempt_id, connection=connection)
    if (event.to_dict() != matches[0].to_dict() or not value['target_ref'].startswith('codex:')
            or _generation(facts) != value['generation']
            or facts.provider_session_id != trusted.provider_session_id
            or facts.process_generation_id != trusted.process_generation_id
            or value['generation']['binding_id'] != trusted.binding_id
            or value['generation']['binding_generation'] != trusted.binding_generation
            or source.operation_key != value['context']['operation_key']
            or {k:getattr(source,k) for k in ('workspace_id','channel_id','thread_ts')} != value['carrier']
            or (source.candidate.root_job_id,source.candidate.job_id,source.candidate.attempt_id,source.candidate.worker_id)
               != (value['root_job_id'],value['job_id'],value['attempt_id'],value['worker_id'])
            or obligation.job_id != value['job_id'] or obligation.source_workstream != value['context']['work_ref']
            or _epoch(_read_current_target(runtime, source.operation_key)) != value['epoch']):
        raise ValueError('native continuation authority changed')
    return NativeContinuationAckEvidence(schema='mastermind.native_continuation_ack.v1',
        request_event_id=event.event_id,request_event_sha256=_digest(event.to_dict()),
        target_attempt_id=trusted.target_attempt_id,process_generation_id=trusted.process_generation_id,
        native_session_sha256=hashlib.sha256(trusted.provider_session_id.encode()).hexdigest(),
        native_turn_sha256=hashlib.sha256(trusted.provider_native_turn_id.encode()).hexdigest(),
        nudge_id=trusted.nudge_id)
