"""R132 causal source proof through public initial/work/review/same-owner paths."""
import asyncio
import copy
import dataclasses
import json
import sqlite3

import pytest

from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor, ExecutiveOperatorSupervisorError
from control_plane.executive_runtime import AttemptLease, AttemptStatus, JobPayload, JobStatus, Runtime, StateConflict, WorkerStatus
from control_plane.executive_orchestration_result import canonical_bytes
from control_plane.operator_harness_contract import ProcessLiveness, ProviderWriterState, ReconcileObservation
from control_plane.operator_harness_orchestrator import OperatorEffectUnknown
from tests.test_executive_coo_r131_service_domain_owner import _context, _settle
from tests.test_executive_coo_r119_later_turn import _inventory
from tests.test_executive_operator_supervisor import _PromptSource


def _consumed(tmp_path, monkeypatch):
    ctx = _context(tmp_path, monkeypatch)
    service, rt, root, domain, outcome, session, calls, rpc, initial, later, command = ctx
    projection, body = _settle(ctx)
    adapter = later['transport']
    adapter.observed_attestation = lambda generation: session.observed
    stops = []
    def stop(generation, **kwargs):
        stops.append((generation, kwargs))
        return dataclasses.replace(initial[0].graceful_stop(generation, **kwargs),
            observed_config_digest=session.observed.effective_config_digest)
    adapter.graceful_stop = stop
    service.operator_supervisor._claimed_adapter_factory = lambda *a, **kw: adapter
    returned = asyncio.run(service._dispatch_cycle_job_exact(domain.job_id, command))
    seal = returned.to_dict()['consumption_seal']
    lease = service._coo_domain_owners[domain.job_id].lease
    return ctx, lease, seal, stops, projection, body


def _finish(state, **changes):
    ctx, lease, seal, *_ = state
    return ctx[0].operator_supervisor.complete_domain_consumption(
        changes.get('lease', lease), consumption_seal=changes.get('seal', seal))


def _handoff(rt, root):
    return rt.jobs.create_cycle_handoff(root.job_id, command_id=f'coo-cycle:{root.job_id}:aggregation-handoff:1')


def test_same_original_owner_stops_completes_and_aggregation_consumes_full_result(tmp_path, monkeypatch):
    state = _consumed(tmp_path, monkeypatch)
    ctx, lease, seal, stops, projection, body = state
    _, rt, root, domain, outcome, session, *_ = ctx
    initial = rt.events.get_event_by_command_id('orchestration-result-seal:'+lease.attempt.attempt_id)
    terminal = _finish(state)
    assert len(stops) == 1 and stops[0][0] == session.generation
    assert terminal['schema_version'] == 'mastermind.executive_coo_domain_terminal/v1'
    assert terminal['consumption_seal'] == seal
    assert terminal['initial_plan_seal'] == initial.payload
    assert terminal['consumption_projection'] == projection
    assert terminal['consumed_result'] == body['consumed_result']
    assert terminal['cleanup_gate'] == 'RESIDUAL_PROCESS_CENSUS_UNAVAILABLE'
    assert 'residual_pids' not in json.dumps(terminal)
    assert lease.lease_token not in json.dumps(terminal)
    assert terminal['stop_evidence']['applied']['payload']['process_liveness'] == 'PROVEN_DEAD'
    assert terminal['stop_evidence']['observation']['payload']['observation']['provider_writer_state'] == 'RELEASED'
    assert rt.jobs.get_job(domain.job_id).status is JobStatus.COMPLETED
    assert rt.attempts.get_attempt(outcome.attempt.attempt_id).status is AttemptStatus.COMPLETED
    assert rt.events.get_event_by_command_id(initial.command_id) == initial
    handoff = _handoff(rt, root)
    assert handoff['domain_terminal'] == terminal
    assert handoff['consumed_result'] == body['consumed_result']
    before = _inventory(rt)
    assert _handoff(rt, root) == handoff
    assert rt.jobs.get_cycle_handoff(root.job_id) == handoff
    assert rt.jobs.read_cycle_domain_terminal(root.job_id) == terminal
    assert _inventory(rt) == before
    with pytest.raises((StateConflict, ExecutiveOperatorSupervisorError)):
        _finish(state)
    assert len(stops) == 1


@pytest.mark.parametrize('bad', ['omit_result','result','body','projection','initial_plan','fence_bool','fence_float','token','worker','quota','owner','principal','profile','host','root','attempt','native','g1','replacement'])
def test_pre_stop_revalidation_refuses_without_source_or_stop_effect(tmp_path, monkeypatch, bad):
    state = _consumed(tmp_path, monkeypatch)
    ctx, lease, seal, stops, *_ = state
    service, rt, *_ = ctx
    changed = copy.deepcopy(seal)
    if bad == 'omit_result': changed['consumption_result'].pop('consumed_result')
    elif bad == 'result': changed['consumption_result']['consumed_result'] = 'foreign body'
    elif bad == 'body': changed['consumed_body_digest'] = 'b'*64
    elif bad == 'projection': changed['selected_revisions'] = []
    elif bad == 'initial_plan': changed = rt.events.get_event_by_command_id('orchestration-result-seal:'+lease.attempt.attempt_id).payload
    elif bad in {'fence_bool','fence_float'}: lease = AttemptLease(dataclasses.replace(lease.attempt, fence_generation=True if bad=='fence_bool' else float(lease.attempt.fence_generation)), lease.lease_token)
    elif bad == 'token': lease = AttemptLease(lease.attempt, 'foreign')
    elif bad in {'worker','quota','owner','principal','profile','host','attempt'}:
        field = dict(worker='worker_id',quota='quota_class',owner='lease_owner',principal='execution_principal_snapshot_digest',profile='requested_execution_profile_digest',host='placement_snapshot_digest',attempt='attempt_id')[bad]
        lease = AttemptLease(dataclasses.replace(lease.attempt, **{field:'foreign'}), lease.lease_token)
    elif bad == 'root': changed['root_job_id'] = 'foreign'
    elif bad == 'native': changed['provider_native_turn_id'] = 'foreign'
    elif bad == 'g1': changed['process_generation_id'] = 'foreign'
    elif bad == 'replacement':
        old = service.operator_supervisor
        service.operator_supervisor = ExecutiveOperatorSupervisor(rt,claimed_adapter_factory=old._claimed_adapter_factory,prompt_source=_PromptSource(),instance_id=old.instance_id)
    before = _inventory(rt)
    with pytest.raises((StateConflict, ExecutiveOperatorSupervisorError)):
        _finish(state, lease=lease, seal=changed)
    assert _inventory(rt) == before and not stops


def test_alive_consumed_domain_cannot_aggregate_or_use_ordinary_plan_terminal(tmp_path, monkeypatch):
    state = _consumed(tmp_path, monkeypatch)
    ctx, lease, *_ = state
    _, rt, root, domain, *_ = ctx
    before = _inventory(rt)
    with pytest.raises(StateConflict): _handoff(rt, root)
    with pytest.raises(StateConflict): rt.jobs.read_cycle_domain_terminal(root.job_id)
    assert _inventory(rt) == before


@pytest.mark.parametrize('bad', ['unknown','alive','held','foreign_process','interrupted'])
def test_failed_stop_preserves_spent_final_and_consumption_nonterminal(tmp_path, monkeypatch, bad):
    state = _consumed(tmp_path, monkeypatch)
    ctx, lease, seal, stops, *_ = state
    _, rt, root, domain, _, session, _, _, initial, later, _ = ctx
    observation = dataclasses.replace(initial[0].graceful_stop(session.generation),
        observed_config_digest=session.observed.effective_config_digest)
    if bad == 'unknown': observation = dataclasses.replace(observation, process_liveness=ProcessLiveness.UNKNOWN)
    if bad == 'alive': observation = dataclasses.replace(observation, process_liveness=ProcessLiveness.ALIVE)
    if bad == 'held': observation = dataclasses.replace(observation, provider_writer_state=ProviderWriterState.HELD)
    if bad == 'foreign_process': observation = dataclasses.replace(observation, observed_process=dataclasses.replace(observation.observed_process, pid=999999))
    def stop(*a, **kw):
        stops.append((a,kw))
        if bad == 'interrupted': raise RuntimeError('stop interrupted')
        return observation
    monkeypatch.setattr(later['transport'], 'graceful_stop', stop)
    with pytest.raises(OperatorEffectUnknown): _finish(state)
    assert rt.attempts.get_attempt(lease.attempt.attempt_id).status is AttemptStatus.CHECKPOINTED
    assert rt.events.get_event_by_command_id(seal['command_id']).payload == seal
    with rt.store.read() as c:
        assert c.execute("SELECT COUNT(*) FROM coo_provider_charges WHERE root_job_id=? AND effect_class='FINAL'",(root.job_id,)).fetchone()[0] == 1
    before = _inventory(rt)
    with pytest.raises(StateConflict): _handoff(rt, root)
    with pytest.raises((StateConflict, ExecutiveOperatorSupervisorError)): _finish(state)
    assert _inventory(rt) == before and len(stops) == 1


def _corrupt_rows(rt, sql, args):
    # Fault injection only, after public affirmative setup. Deliberately bypass
    # FK enforcement to exercise Runtime provenance checks independently.
    with sqlite3.connect(rt.store.path) as connection:
        connection.execute(sql,args)


def _alter_event(rt, command, edit):
    with rt.store.transaction() as c:
        row = c.execute('SELECT * FROM events WHERE command_id=?', (command,)).fetchone()
        payload = json.loads(row['payload_json'])
        edit(payload)
        c.execute('UPDATE events SET payload_json=? WHERE event_id=?', (canonical_bytes(payload).decode(),row['event_id']))


def _alias(rt, source, *, payload=None, header_foreign=False):
    with rt.store.transaction() as c:
        rt.store.append_event(c, aggregate_type='job' if header_foreign else source.aggregate_type,
            aggregate_id='foreign' if header_foreign else source.aggregate_id,
            event_type=source.event_type, actor=source.actor,
            job_id=None if header_foreign else source.job_id,
            attempt_id=None if header_foreign else source.attempt_id,
            worker_id=source.worker_id, quota_class=source.quota_class,
            command_id='r132-negative-alias', payload=payload if payload is not None else source.payload)


@pytest.mark.parametrize('stage', ['create','replay'])
@pytest.mark.parametrize('bad', [
    'missing_consumption','missing_terminal','consumed_result','consumed_body','projection',
    'revisions','plan_substitution','consumption_duplicate','terminal_duplicate','terminal_orphan_digest',
    'consumption_orphan_native','missing_applied','foreign_applied','missing_death','foreign_death',
    'missing_release','foreign_release','stop_unknown','wrong_shutdown_generation','alive','held',
    'consumption_numeric_bool','terminal_numeric_float','current_profile','current_principal','current_host',
    'foreign_root','foreign_attempt','foreign_worker','foreign_quota','foreign_owner','foreign_fence',
    'final_turn','initial_native','dispatch_alias',
])
def test_aggregation_create_and_replay_revalidate_complete_immutable_material(tmp_path, monkeypatch, stage, bad):
    state = _consumed(tmp_path, monkeypatch)
    ctx, lease, seal, *_ = state
    _, rt, root, domain, *_ = ctx
    terminal = _finish(state)
    # Privileged corruption fixtures deliberately remove DB immutability guards
    # after the entirely public positive path. Runtime must still refuse reads.
    with rt.store.transaction() as c:
        c.execute('DROP TRIGGER events_are_immutable_update')
        c.execute('DROP TRIGGER events_are_immutable_delete')
        for trigger in c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='attempts'").fetchall():
            c.execute('DROP TRIGGER '+trigger['name'])
    if stage == 'replay': _handoff(rt, root)
    terminal_command = terminal['command_id']
    stop = terminal['stop_evidence']
    commands = dict(missing_consumption=seal['command_id'],missing_terminal=terminal_command,
        missing_applied=stop['applied']['command_id'],missing_death=stop['observation']['command_id'],
        missing_release=stop['epoch_release']['command_id'])
    if bad in commands:
        with rt.store.transaction() as c: c.execute('DELETE FROM events WHERE command_id=?',(commands[bad],))
    elif bad == 'consumed_result': _alter_event(rt, seal['command_id'], lambda p:p['consumption_result'].update(consumed_result='changed after stop'))
    elif bad == 'consumed_body': _alter_event(rt, seal['command_id'], lambda p:p.update(consumed_body_digest='b'*64))
    elif bad == 'projection': _alter_event(rt, terminal_command, lambda p:p['consumption_projection'].update(revision_results=[]))
    elif bad == 'revisions':
        work = terminal['consumption_projection']['revisions'][0]['current_job_id']
        _corrupt_rows(rt,'UPDATE jobs SET current_attempt_id=? WHERE job_id=?',(lease.attempt.attempt_id,work))
    elif bad == 'plan_substitution': _alter_event(rt, terminal_command, lambda p:p.update(consumption_seal=p['initial_plan_seal']))
    elif bad == 'consumption_duplicate': _alias(rt,rt.events.get_event_by_command_id(seal['command_id']))
    elif bad == 'terminal_duplicate': _alias(rt,rt.events.get_event_by_command_id(terminal_command))
    elif bad == 'terminal_orphan_digest': _alias(rt,rt.events.get_event_by_command_id(terminal_command),payload={'terminal_evidence_digest':terminal['terminal_evidence_digest']},header_foreign=True)
    elif bad == 'consumption_orphan_native': _alias(rt,rt.events.get_event_by_command_id(seal['command_id']),payload={'provider_session_id':seal['provider_session_id'],'provider_native_turn_id':seal['provider_native_turn_id']},header_foreign=True)
    elif bad == 'foreign_applied': _alter_event(rt,stop['applied']['command_id'],lambda p:p.update(process_generation_id='foreign'))
    elif bad == 'foreign_death': _alter_event(rt,stop['observation']['command_id'],lambda p:p['observation']['observed_process'].update(pid=999999))
    elif bad == 'foreign_release': _alter_event(rt,stop['applied']['command_id'],lambda p:p.update(provider_writer_state='HELD',executive_writer_released=False))
    elif bad == 'stop_unknown': _alias(rt,rt.events.get_event_by_command_id(stop['applied']['command_id']),payload={'operation_kind':'graceful_stop','process_generation_id':seal['process_generation_id']})
    elif bad == 'wrong_shutdown_generation': _alter_event(rt,stop['intent']['command_id'],lambda p:p.update(process_generation_id='foreign'))
    elif bad in {'alive','held'}:
        with rt.store.transaction() as c:
            if bad == 'alive': c.execute('UPDATE process_generations SET ended_at_ms=NULL WHERE process_generation_id=?',(seal['process_generation_id'],))
            else: c.execute("UPDATE process_generations SET executive_writer_held=1,provider_writer_state='HELD' WHERE process_generation_id=?",(seal['process_generation_id'],))
    elif bad == 'consumption_numeric_bool': _alter_event(rt,seal['command_id'],lambda p:p.update(fence_generation=True))
    elif bad == 'terminal_numeric_float': _alter_event(rt,terminal_command,lambda p:p['original_owner'].update(fence_generation=float(p['original_owner']['fence_generation'])))
    elif bad in {'current_profile','current_principal','current_host','foreign_worker','foreign_quota','foreign_owner','foreign_fence'}:
        field = dict(current_profile='requested_execution_profile_digest',current_principal='execution_principal_snapshot_digest',current_host='placement_snapshot_digest',foreign_worker='worker_id',foreign_quota='quota_class',foreign_owner='lease_owner',foreign_fence='fence_generation')[bad]
        _corrupt_rows(rt,f'UPDATE attempts SET {field}=? WHERE attempt_id=?',(99 if bad=='foreign_fence' else ('b'*64 if bad.startswith('current_') else ('r131-work' if bad=='foreign_worker' else (ctx[0].config.coo_quota_class if bad=='foreign_quota' else 'foreign'))),lease.attempt.attempt_id))
    elif bad in {'foreign_root','foreign_attempt'}: _alter_event(rt,seal['command_id'],lambda p:p.update(**{dict(foreign_root='root_job_id',foreign_attempt='domain_attempt_id')[bad]:'foreign'}))
    elif bad == 'final_turn': _alter_event(rt,seal['applied_event_command_id'],lambda p:p.update(provider_native_turn_id='foreign'))
    elif bad == 'initial_native': _alter_event(rt,terminal['initial_plan_seal']['candidate_event_command_id'],lambda p:p['events'][0].update(turn_id='foreign'))
    elif bad == 'dispatch_alias': _alias(rt,rt.events.get_event_by_command_id(seal['dispatch_event_command_id']))
    before = _inventory(rt)
    with pytest.raises(StateConflict): _handoff(rt, root)
    with pytest.raises(StateConflict): rt.jobs.read_cycle_domain_terminal(root.job_id)
    if stage=='replay':
        with pytest.raises(StateConflict): rt.jobs.get_cycle_handoff(root.job_id)
    assert _inventory(rt) == before


@pytest.mark.parametrize('bad',['omit','result','terminal','projection','plan'])
def test_aggregation_handoff_body_cannot_be_backfilled_or_changed(tmp_path, monkeypatch, bad):
    state = _consumed(tmp_path, monkeypatch)
    rt, root = state[0][1:3]
    terminal = _finish(state)
    handoff = _handoff(rt, root)
    def edit(p):
        if bad=='omit': p.pop('consumed_result')
        if bad=='result': p['consumed_result']='changed'
        if bad=='terminal': p['domain_terminal'].pop('consumption_seal')
        if bad=='projection': p['domain_terminal']['consumption_projection']['revision_results']=[]
        if bad=='plan': p['domain_terminal']['consumption_seal']=terminal['initial_plan_seal']
        # Even a recomputed outer handoff digest cannot authorize new inner evidence.
        from control_plane.executive_orchestration_principal import digest as orchestration_digest
        p.pop('handoff_digest')
        p['handoff_digest']=orchestration_digest(p)
    with rt.store.transaction() as c: c.execute('DROP TRIGGER events_are_immutable_update')
    _alter_event(rt,handoff['command_id'],edit)
    before=_inventory(rt)
    with pytest.raises(StateConflict): _handoff(rt,root)
    assert _inventory(rt)==before


@pytest.mark.parametrize('alias',['header','digest'])
def test_terminal_transaction_refuses_preexisting_alias_before_job_completion(tmp_path,monkeypatch,alias):
    state=_consumed(tmp_path,monkeypatch)
    ctx,lease,seal,*_=state
    rt=ctx[1]
    original=rt.attempts.complete_attempt
    def inject(attempt_id, **kwargs):
        material=kwargs['payload']
        with rt.store.transaction() as c:
            rt.store.append_event(c,aggregate_type='job',aggregate_id=material['root_job_id'] if alias=='header' else 'foreign',
                event_type='COO_DOMAIN_TERMINAL_SEALED',actor='coo',
                job_id=material['root_job_id'] if alias=='header' else None,
                attempt_id=attempt_id if alias=='header' else None,
                worker_id=lease.attempt.worker_id,quota_class=lease.attempt.quota_class,
                command_id='r132-terminal-negative-prior',payload=material if alias=='header' else {'terminal_evidence_digest':material['terminal_evidence_digest']})
        before=_inventory(rt)
        with pytest.raises(StateConflict): original(attempt_id,**kwargs)
        assert _inventory(rt)==before
        raise StateConflict('expected terminal alias refusal')
    monkeypatch.setattr(rt.attempts,'complete_attempt',inject)
    with pytest.raises(StateConflict): _finish(state)
    assert rt.attempts.get_attempt(lease.attempt.attempt_id).status is AttemptStatus.CHECKPOINTED
    assert rt.events.get_event_by_command_id(seal['command_id']).payload==seal


def test_aggregation_actor_packet_contains_actual_full_consumed_result(tmp_path,monkeypatch):
    state=_consumed(tmp_path,monkeypatch)
    ctx,lease,seal,*_=state
    service,rt,root,*_=ctx
    terminal=_finish(state)
    handoff=_handoff(rt,root)
    dispatched=rt.attempts.dispatch_cycle_job(root.job_id,
        command_id=f'coo-cycle:{root.job_id}:dispatch:{root.job_id}:attempt:1',
        worker_id='r131-work',quota_class=service.config.coo_quota_class)
    assert dispatched is not None
    from control_plane.executive_supervisor import ExecutiveSupervisor
    source=ExecutiveSupervisor(rt,object(),inspector=object())
    prompt=source._prompt(rt.jobs.get_job(root.job_id),dispatched.attempt,dispatched.attempt.effective_grant)
    packet=json.JSONDecoder().raw_decode(prompt[prompt.index('{'):])[0]
    assert packet['orchestration']['aggregation_handoff']==handoff
    assert packet['orchestration']['aggregation_handoff']['domain_terminal']==terminal
    assert packet['orchestration']['aggregation_handoff']['consumed_result']==seal['consumption_result']['consumed_result']


def test_live_terminal_refuses_current_authority_movement_before_stop(tmp_path,monkeypatch):
    state=_consumed(tmp_path,monkeypatch)
    rt=state[0][1]
    from control_plane.executive_authority import ExecutiveAuthorityPolicy
    policy=ExecutiveAuthorityPolicy.load()
    moved=dataclasses.replace(policy,sha256='b'*64)
    monkeypatch.setattr(ExecutiveAuthorityPolicy,'load',classmethod(lambda cls,path=None:moved))
    before=_inventory(rt)
    with pytest.raises(StateConflict): _finish(state)
    assert _inventory(rt)==before and not state[3]


@pytest.mark.parametrize('numeric',['float','bool'])
def test_stop_observation_rejects_invalid_numeric_process_types(tmp_path,monkeypatch,numeric):
    state=_consumed(tmp_path,monkeypatch)
    ctx,lease,seal,stops,*_=state
    _,rt,_,_,_,session,_,_,initial,later,_=ctx
    observation=dataclasses.replace(initial[0].graceful_stop(session.generation),
        observed_config_digest=session.observed.effective_config_digest)
    value=float(observation.observed_process.pid) if numeric=='float' else True
    observation=dataclasses.replace(observation,observed_process=dataclasses.replace(observation.observed_process,pid=value))
    monkeypatch.setattr(later['transport'],'graceful_stop',lambda *a,**kw:observation)
    with pytest.raises(OperatorEffectUnknown): _finish(state)
    assert rt.attempts.get_attempt(lease.attempt.attempt_id).status is AttemptStatus.CHECKPOINTED
    assert rt.events.get_event_by_command_id(seal['command_id']).payload==seal


@pytest.mark.parametrize('bad',['invented_residual_proof','cleanup_gate'])
def test_missing_canonical_residual_census_cannot_be_fabricated_in_terminal_material(tmp_path,monkeypatch,bad):
    state=_consumed(tmp_path,monkeypatch)
    rt,root=state[0][1:3]
    terminal=_finish(state)
    with rt.store.transaction() as c:c.execute('DROP TRIGGER events_are_immutable_update')
    if bad=='invented_residual_proof':
        _alter_event(rt,terminal['stop_evidence']['observation']['command_id'],lambda p:p['observation'].update(residual_pids=[98765]))
    else:
        _alter_event(rt,terminal['command_id'],lambda p:p.update(cleanup_gate='PROVEN_CLEAN'))
    before=_inventory(rt)
    with pytest.raises(StateConflict):_handoff(rt,root)
    assert _inventory(rt)==before


def test_missing_consumption_after_final_cannot_fall_back_to_initial_plan_completion(tmp_path,monkeypatch):
    state=_consumed(tmp_path,monkeypatch)
    ctx,lease,seal,*_=state
    rt=ctx[1]
    original=rt.attempts.complete_attempt
    initial=rt.events.get_event_by_command_id('orchestration-result-seal:'+lease.attempt.attempt_id)
    def attempt_initial(attempt_id,**kwargs):
        with rt.store.transaction() as c:
            c.execute('DROP TRIGGER events_are_immutable_delete')
            c.execute('DELETE FROM events WHERE command_id=?',(seal['command_id'],))
        legacy=ctx[0].operator_supervisor._terminal_payload(job=rt.jobs.get_job(lease.attempt.job_id),lease=lease,
            canonical_result_json=canonical_bytes(initial.payload['result_envelope']).decode())
        before=_inventory(rt)
        with pytest.raises(StateConflict):original(attempt_id,**(kwargs|{'payload':legacy}))
        assert _inventory(rt)==before
        raise StateConflict('expected missing consumption refusal')
    monkeypatch.setattr(rt.attempts,'complete_attempt',attempt_initial)
    with pytest.raises(StateConflict):_finish(state)
    assert rt.attempts.get_attempt(lease.attempt.attempt_id).status is AttemptStatus.CHECKPOINTED


@pytest.mark.parametrize('numeric',['bool','float'])
def test_runtime_terminal_transaction_refuses_numeric_caller_fence_alias(tmp_path,monkeypatch,numeric):
    state=_consumed(tmp_path,monkeypatch)
    ctx,lease,seal,*_=state
    rt=ctx[1]
    original=rt.attempts.complete_attempt
    def try_alias(attempt_id,**kwargs):
        before=_inventory(rt)
        value=True if numeric=='bool' else float(kwargs['fence_generation'])
        with pytest.raises(StateConflict):original(attempt_id,**(kwargs|{'fence_generation':value}))
        assert _inventory(rt)==before
        raise StateConflict('expected invalid caller fence refusal')
    monkeypatch.setattr(rt.attempts,'complete_attempt',try_alias)
    with pytest.raises(StateConflict):_finish(state)
    assert rt.attempts.get_attempt(lease.attempt.attempt_id).status is AttemptStatus.CHECKPOINTED
    assert rt.events.get_event_by_command_id(seal['command_id']).payload==seal


def _alias_payload_for(material, kind):
    """Return a payload containing the exact identity-kind under test only.

    The aliased event uses foreign/null headers and only the requested
    owner-specific identity link.  Each variant must independently reach
    the terminal affiliation census through the existing
    _domain_receipt_inventory code path.
    """
    if kind == 'native_pair':
        return {'provider_session_id': material['consumption_seal']['provider_session_id'],
                'provider_native_turn_id': material['consumption_seal']['provider_native_turn_id']}
    if kind in {'candidate_digest', 'applied_digest', 'dispatch_digest',
                'intent_digest', 'initial_plan_digest', 'final_digest'}:
        key = kind.removesuffix('_digest') + '_event_digest'
        value = material['consumption_seal'][key]
        assert type(value) is str and len(value) == 64
        return {key: value}
    if kind == 'final_event_id':
        value = material['consumption_seal']['final_event_id']
        assert type(value) is int
        return {'final_event_id': value}
    raise AssertionError(kind)


def _inject_terminal_alias(rt, lease, material, kind):
    """Pre-append a foreign/null-header COO_DOMAIN_TERMINAL_SEALED event
    carrying only the requested owner-specific link under test.
    """
    payload = _alias_payload_for(material, kind)
    with rt.store.transaction() as c:
        rt.store.append_event(c,
            aggregate_type='job', aggregate_id='foreign',
            event_type='COO_DOMAIN_TERMINAL_SEALED', actor='coo',
            job_id=None, attempt_id=None,
            worker_id=lease.attempt.worker_id, quota_class=lease.attempt.quota_class,
            command_id=f'r132-r1-alias-{kind}', payload=payload)


@pytest.mark.parametrize('kind', [
    'native_pair', 'candidate_digest', 'applied_digest',
    'dispatch_digest', 'intent_digest', 'initial_plan_digest', 'final_digest', 'final_event_id',
])
def test_terminal_affiliate_census_refuses_owner_specific_only_alias_before_append(tmp_path, monkeypatch, kind):
    state=_consumed(tmp_path, monkeypatch)
    ctx, lease, seal, *_=state
    rt=ctx[1]
    complete=rt.attempts.complete_attempt
    seen=set()
    def shim(attempt_id, **kwargs):
        material=kwargs['payload']
        _alias_payload_for(material, kind)  # touch helper for coverage
        _inject_terminal_alias(rt, lease, material, kind)
        seen.add(kind)
        before=_inventory(rt)
        with pytest.raises(StateConflict): complete(attempt_id, **kwargs)
        assert _inventory(rt)==before
        raise StateConflict('expected owner-specific terminal alias refusal')
    monkeypatch.setattr(rt.attempts, 'complete_attempt', shim)
    with pytest.raises(StateConflict): _finish(state)
    assert kind in seen
    assert rt.attempts.get_attempt(lease.attempt.attempt_id).status is AttemptStatus.CHECKPOINTED
    assert rt.events.get_event_by_command_id(seal['command_id']).payload == seal


@pytest.mark.parametrize('stage', ['create', 'replay'])
@pytest.mark.parametrize('kind', [
    'native_pair', 'candidate_digest', 'applied_digest',
    'dispatch_digest', 'intent_digest', 'initial_plan_digest', 'final_digest', 'final_event_id',
])
def test_terminal_affiliate_census_refuses_owner_specific_only_alias_on_read_aggregation(tmp_path, monkeypatch, kind, stage):
    state=_consumed(tmp_path, monkeypatch)
    ctx, lease, seal, *_=state
    _, rt, root, domain, *_=ctx
    terminal=_finish(state)
    with rt.store.read() as conn:
        triggers_before=[tuple(row) for row in conn.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name")]
    if stage=='replay': _handoff(rt, root)
    _inject_terminal_alias(rt, lease, terminal, kind)
    before=_inventory(rt)
    with pytest.raises(StateConflict): _handoff(rt, root)
    with pytest.raises(StateConflict): rt.jobs.read_cycle_domain_terminal(root.job_id)
    if stage=='replay':
        with pytest.raises(StateConflict): rt.jobs.get_cycle_handoff(root.job_id)
    assert _inventory(rt)==before
    with rt.store.read() as conn:
        assert [tuple(row) for row in conn.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name")] == triggers_before


@pytest.mark.parametrize('kind', ['session_only', 'turn_only', 'shared_worker_id', 'shared_quota_class'])
def test_terminal_affiliate_census_ignores_shared_or_unpaired_native_keys(tmp_path, monkeypatch, kind):
    """Controls: native pair must be atomic; shared worker/quota values are
    not independent affiliation.  None of these aliases must trigger refusal.
    """
    state=_consumed(tmp_path, monkeypatch)
    ctx, lease, seal, *_=state
    rt=ctx[1]
    complete=rt.attempts.complete_attempt
    payload=None
    if kind == 'session_only':
        payload = {'provider_session_id': seal['provider_session_id']}
    elif kind == 'turn_only':
        payload = {'provider_native_turn_id': seal['provider_native_turn_id']}
    elif kind == 'shared_worker_id':
        payload = {'worker_id': lease.attempt.worker_id}
    elif kind == 'shared_quota_class':
        payload = {'quota_class': lease.attempt.quota_class}
    def shim(attempt_id, **kwargs):
        material=kwargs['payload']
        with rt.store.transaction() as c:
            rt.store.append_event(c,
                aggregate_type='job', aggregate_id='foreign',
                event_type='COO_DOMAIN_TERMINAL_SEALED', actor='coo',
                job_id=None, attempt_id=None,
                worker_id=lease.attempt.worker_id, quota_class=lease.attempt.quota_class,
                command_id=f'r132-r1-shared-{kind}', payload=payload)
        # The foreign event carries only a shared/unpaired value; it is not
        # an independently affiliated terminal receipt.
        result = complete(attempt_id, **kwargs)
        return result
    monkeypatch.setattr(rt.attempts, 'complete_attempt', shim)
    # Control case: _finish succeeds; the JOB_COMPLETED event still
    # carries the cleanup_gate so the residual qualifier is not lost.
    terminal=_finish(state)
    assert terminal['cleanup_gate'] == 'RESIDUAL_PROCESS_CENSUS_UNAVAILABLE'


@pytest.mark.parametrize('kind', ['bool', 'float', 'nonmatching_int'])
def test_terminal_affiliate_census_final_event_id_is_exact_int_only(tmp_path, monkeypatch, kind):
    """bool/float must never acquire int identity; a nonmatching int value
    must not be treated as the same final_event_id affiliation.
    """
    state=_consumed(tmp_path, monkeypatch)
    ctx, lease, seal, *_=state
    rt=ctx[1]
    complete=rt.attempts.complete_attempt
    real_final=seal['final_event_id']
    assert type(real_final) is int
    if kind == 'bool':
        sentinel = True
    elif kind == 'float':
        sentinel = float(real_final)
    else:
        sentinel = real_final + 1
    def shim(attempt_id, **kwargs):
        material=kwargs['payload']
        with rt.store.transaction() as c:
            rt.store.append_event(c,
                aggregate_type='job', aggregate_id='foreign',
                event_type='COO_DOMAIN_TERMINAL_SEALED', actor='coo',
                job_id=None, attempt_id=None,
                worker_id=lease.attempt.worker_id, quota_class=lease.attempt.quota_class,
                command_id=f'r132-r1-numeric-{kind}', payload={'final_event_id': sentinel})
        # Numeric coercion and nonmatching ids are not affiliation, so
        # complete_attempt must succeed.
        return complete(attempt_id, **kwargs)
    monkeypatch.setattr(rt.attempts, 'complete_attempt', shim)
    terminal=_finish(state)
    assert terminal['cleanup_gate'] == 'RESIDUAL_PROCESS_CENSUS_UNAVAILABLE'


def test_domain_terminal_completion_keeps_exact_quota_in_error_and_carries_cleanup_gate(tmp_path, monkeypatch):
    state=_consumed(tmp_path, monkeypatch)
    ctx, lease, seal, *_=state
    _, rt, root, domain, *_=ctx
    exact=(lease.attempt.worker_id, lease.attempt.quota_class)
    with rt.store.read() as c:
        other_before=[dict(r) for r in c.execute(
            "SELECT * FROM worker_quota_classes WHERE NOT(worker_id=? AND quota_class=?)", exact)]
    terminal=_finish(state)
    quota=rt.workers.get_quota_class(*exact)
    assert quota is not None and quota.active_attempt_id is None
    assert quota.status is WorkerStatus.ERROR
    with rt.store.read() as c:
        other_after=[dict(r) for r in c.execute(
            "SELECT * FROM worker_quota_classes WHERE NOT(worker_id=? AND quota_class=?)", exact)]
    assert other_after==other_before
    events=[e for e in rt.events.list_events() if e.event_type=='JOB_COMPLETED'
            and e.attempt_id==lease.attempt.attempt_id]
    assert len(events)==1
    assert events[0].payload['cleanup_gate']=='RESIDUAL_PROCESS_CENSUS_UNAVAILABLE'
    assert events[0].payload['capacity_status']==WorkerStatus.ERROR.value
    assert rt.jobs.get_job(domain.job_id).status is JobStatus.COMPLETED
    assert rt.attempts.get_attempt(lease.attempt.attempt_id).status is AttemptStatus.COMPLETED
    assert _handoff(rt, root)['domain_terminal']==terminal
    # Isolate the exact quota with supported resource administration on OTHER
    # idle fixture quotas. Never promote the unqualified domain quota.
    for row in other_after:
        assert row['held_attempt_id'] is None
        rt.workers.set_worker_status(row['worker_id'], WorkerStatus.DRAINING,
                                    quota_class=row['quota_class'])
    ordinary=rt.jobs.create_job('Capacity refusal probe', constraints={
        'eligible_quota_classes':[exact[1]], 'provider':quota.provider,
        'model':quota.model, 'effort':quota.effort, 'cost_class':quota.cost_class})
    before=_inventory(rt)
    assert rt.broker.select_worker(ordinary.job_id) is None
    assert rt.attempts.claim_job(ordinary.job_id, worker_id=exact[0], quota_class=exact[1]) is None
    assert _inventory(rt)==before
    assert rt.workers.get_quota_class(*exact).status is WorkerStatus.ERROR


def test_ordinary_completed_worker_returns_to_available_unchanged(tmp_path):
    # A separate ordinary role-null public lifecycle establishes actual
    # completion behavior without recovering the unqualified domain quota.
    rt=Runtime.at(tmp_path)
    rt.workers.register_worker('ordinary-r132', provider='codex',
                              account_label='ordinary-fixture', worker_type='fixture')
    job=rt.jobs.create_job('Ordinary completion control')
    assert job.orchestration_role is None
    assert rt.broker.select_worker(job.job_id).worker_id=='ordinary-r132'
    lease=rt.broker.claim(job.job_id, worker_id='ordinary-r132')
    assert lease is not None
    assert rt.workers.get_quota_class('ordinary-r132','default').status is WorkerStatus.BUSY
    completed=rt.attempts.complete_attempt(lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
        payload=JobPayload(summary='Ordinary fixture done', current_state='complete'))
    assert completed.status is JobStatus.COMPLETED
    quota=rt.workers.get_quota_class('ordinary-r132','default')
    assert quota.status is WorkerStatus.AVAILABLE and quota.active_attempt_id is None
    events=[e for e in rt.events.list_events() if e.event_type=='JOB_COMPLETED'
            and e.attempt_id==lease.attempt.attempt_id]
    assert len(events)==1
    assert 'cleanup_gate' not in events[0].payload and 'capacity_status' not in events[0].payload
    next_job=rt.jobs.create_job('Fresh ordinary capacity control')
    assert rt.broker.select_worker(next_job.job_id).worker_id=='ordinary-r132'
    assert rt.attempts.claim_job(next_job.job_id, worker_id='ordinary-r132') is not None


@pytest.mark.parametrize('value,affiliated', [(True,False),(1.0,False),(1,True),(2,False)])
def test_terminal_affiliate_census_final_one_rejects_numeric_coercion(tmp_path,value,affiliated):
    # Exact-type discriminator supplements the public lifecycle controls above:
    # bool True and float 1.0 compare equal to int 1 in Python.
    from control_plane.executive_runtime import _domain_receipt_inventory
    rt=Runtime.at(tmp_path)
    with rt.store.transaction() as c:
        rt.store.append_event(c, aggregate_type='job', aggregate_id='foreign',
            event_type='COO_DOMAIN_TERMINAL_SEALED', actor='coo', job_id=None,
            attempt_id=None, command_id='numeric-exact-one', payload={'final_event_id':value})
        rows=_domain_receipt_inventory(c, event_type='COO_DOMAIN_TERMINAL_SEALED',
            command_id='canonical-exact-one', root_id='root',
            row={'job_id':'domain','attempt_id':'attempt'}, source={'final_event_id':1})
    assert bool(rows) is affiliated


@pytest.mark.parametrize('retained_status', [WorkerStatus.ERROR, WorkerStatus.DRAINING, WorkerStatus.OFFLINE])
def test_domain_completion_event_reports_retained_nonavailable_capacity(tmp_path, monkeypatch, retained_status):
    state=_consumed(tmp_path, monkeypatch)
    ctx,lease,seal,*_=state
    rt=ctx[1]
    complete=rt.attempts.complete_attempt
    exact=(lease.attempt.worker_id, lease.attempt.quota_class)
    def preserve_disposition(attempt_id, **kwargs):
        # Supported public resource disposition after the Supervisor has
        # validated/stopped the exact original owner, before atomic terminal.
        rt.workers.set_worker_status(exact[0], retained_status, quota_class=exact[1])
        return complete(attempt_id, **kwargs)
    monkeypatch.setattr(rt.attempts,'complete_attempt',preserve_disposition)
    terminal=_finish(state)
    quota=rt.workers.get_quota_class(*exact)
    assert quota.status is retained_status and quota.active_attempt_id is None
    events=[e for e in rt.events.list_events() if e.event_type=='JOB_COMPLETED'
            and e.attempt_id==lease.attempt.attempt_id]
    assert len(events)==1
    assert events[0].payload['capacity_status']==retained_status.value
    assert events[0].payload['cleanup_gate']==terminal['cleanup_gate']=='RESIDUAL_PROCESS_CENSUS_UNAVAILABLE'


@pytest.mark.parametrize('missing', ['row', 'status'])
def test_domain_capacity_readback_failure_rolls_back_terminal_transaction(tmp_path, monkeypatch, missing):
    from contextlib import contextmanager
    state=_consumed(tmp_path,monkeypatch)
    ctx,lease,seal,*_=state
    rt=ctx[1]
    complete=rt.attempts.complete_attempt
    transaction=rt.store.transaction
    seen=[]
    class Connection:
        def __init__(self, connection): self.connection=connection
        def __getattr__(self, name): return getattr(self.connection,name)
        def execute(self, sql, parameters=()):
            cursor=self.connection.execute(sql,parameters)
            normalized=' '.join(sql.split())
            if normalized=='SELECT status FROM worker_quota_classes WHERE worker_id=? AND quota_class=? AND held_attempt_id IS NULL':
                seen.append(parameters)
                class Cursor:
                    def fetchone(self): return None if missing=='row' else {'status':None}
                return Cursor()
            return cursor
    @contextmanager
    def readback_unavailable():
        with transaction() as connection:
            yield Connection(connection)
    def shim(attempt_id, **kwargs):
        # Stop effects are already recorded before entering this transaction;
        # the terminal writes themselves must roll back on unavailable readback.
        before=_inventory(rt)
        with monkeypatch.context() as scoped:
            scoped.setattr(rt.store,'transaction',readback_unavailable)
            with pytest.raises(StateConflict): complete(attempt_id,**kwargs)
        assert _inventory(rt)==before
        raise StateConflict('expected exact capacity readback refusal')
    monkeypatch.setattr(rt.attempts,'complete_attempt',shim)
    with pytest.raises(StateConflict): _finish(state)
    assert seen==[(lease.attempt.worker_id,lease.attempt.quota_class)]
    assert rt.attempts.get_attempt(lease.attempt.attempt_id).status is AttemptStatus.CHECKPOINTED
    assert rt.events.get_event_by_command_id(seal['command_id']).payload==seal
