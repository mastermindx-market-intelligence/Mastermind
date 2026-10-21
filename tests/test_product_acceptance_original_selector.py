"""Canonical Runtime/issuance/Wake join; account, Relay and source are fixtures."""
import dataclasses
import asyncio
import threading

import pytest

from control_plane.dialogue_source_resolution import (
    DialogueSourceObservation, PhysicalDialogueSourceIdentity,
    attention_source_ref, correlated_source_ref,
)
from control_plane.executive_delegation_identity import derive_delegation_identity
from control_plane.wake_events import mint_obligation
from control_plane.wake_ledger import (
    AckMode, SourceReadHealth, TrustedAckContext, acknowledge, ack_record,
    expected_resolution_code, requested_record, resolve_source, resolved_record,
)
from control_plane.wake_persist import WakeLedgerRepository
from integrations.product_acceptance_ruling_owner import ProductAcceptanceRulingReceiptReader
from integrations.product_acceptance_selector import (
    ProductAcceptanceSelectionUnavailable, read_original_acceptance_selection,
    read_original_acceptance_observation,
)
from tests import test_product_acceptance_ruling_owner as ruling_fixture
from tests.test_product_acceptance_read_projection import case


def bind_actual_issuer(monkeypatch):
    original = ruling_fixture.programme

    def programme(*args, **kwargs):
        runtime, owner, binding, target, basis = original(*args, **kwargs)
        child = runtime.jobs.get_job(binding.actor_ref['job_id'])
        identity = derive_delegation_identity(child)
        return runtime, owner, dataclasses.replace(binding,
            operation_key=identity.operation_key, session_ref=identity.session_ref), target, basis

    monkeypatch.setattr(ruling_fixture, 'programme', programme)


def anchor(runtime, owner, selected, *, defect=None):
    raw = ProductAcceptanceRulingReceiptReader(owner)._request(selected['request_message_key'])
    subject, context, message = raw['subject'], raw['context'], raw['message']
    key = 'asd-mcp-' + '9' * 32 if defect == 'ordinary' else message['message_key']
    candidate = {'mode': 'ACTIVE_CURRENT_WORKER', 'root_job_id': subject['root_job_id'],
        **{name: subject['issuer_' + name] for name in ('job_id', 'attempt_id', 'worker_id')},
        'evidence_digest': 'b' * 64}
    if defect == 'issuer': candidate['worker_id'] = 'foreign-worker'
    operation = 'foreign-operation' if defect == 'operation' else context['operation_key']
    work = 'WS:FOREIGN' if defect == 'work' else context['work_ref']
    fingerprint = 'c' * 64 if defect == 'fingerprint' else message['fingerprint']
    thread = '1787896129.625239' if defect == 'thread' else raw['thread_ts']
    logical = correlated_source_ref(attention_source_ref=attention_source_ref(
        parent_fingerprint='a' * 64, message_key=key, target_seat='coo'),
        parent_fingerprint='a' * 64, operation_key=operation, candidate=candidate)
    obligation = mint_obligation(wake_kind='dialogue_turn_pending',
        source_kind='agent_dialogue_attention', source_ref=logical,
        declared_target_seat='coo', job_id=candidate['job_id'], attempt_id=candidate['attempt_id'],
        root_job_id=candidate['root_job_id'], source_workstream=work, emitted_at='2026-10-14T00:00:00Z')
    physical = PhysicalDialogueSourceIdentity.create(logical_source_ref=logical,
        obligation_id=obligation.obligation_id,
        observation=DialogueSourceObservation('T0BRD2AQXQV', 'C0BSBM78V1N', thread, key, fingerprint),
        parent_fingerprint='a' * 64, operation_key=operation, target_seat='coo', candidate=candidate)
    repository = WakeLedgerRepository(runtime)
    repository.append_record(requested_record(obligation, physical_source=physical), obligation=obligation)
    if defect == 'resolved':
        ack = acknowledge(obligation, trusted=TrustedAckContext(ack_mode=AckMode.HUMAN_OPERATOR,
            target_seat='coo', session_alias='SYNTHETIC-OPERATOR', reasoning_surface='human',
            acknowledged_at='2026-10-14T00:00:01Z', operator_authority_receipt='SYNTHETIC-READ'),
            claimed_obligation_ids=(obligation.obligation_id,))
        repository.append_record(ack_record(obligation, ack))
        resolution = resolve_source(obligation, code=expected_resolution_code(obligation),
            health=SourceReadHealth.HEALTHY, source_present=False, snapshot_digest='d' * 64,
            resolved_at='2026-10-14T00:00:02Z')
        repository.append_record(resolved_record(obligation, resolution))
    return obligation


def read(bound, owner, selected, obligation, **kwargs):
    return read_original_acceptance_selection(bound, owner.reader,
        original_obligation_id=obligation.obligation_id,
        expected_work_ref=selected['work_ref'], expected_root_job_id=selected['root_job_id'],
        receiving_read_guard=kwargs.pop('receiving_read_guard', lambda: None), **kwargs)


@pytest.mark.parametrize(('complete', 'defect'), [(False, None), (True, None), (True, 'resolved')])
def test_existing_original_issuance_yields_only_selector_without_new_effect(tmp_path, monkeypatch, complete, defect):
    bind_actual_issuer(monkeypatch)
    with case(tmp_path, monkeypatch, complete=complete) as (runtime, owner, _, _, selected, run):
        obligation = anchor(runtime, owner, selected, defect=defect)
        before = runtime.events.list_events()
        assert run(lambda bound: read(bound, owner, selected, obligation)) == selected
        assert runtime.events.list_events() == before


def test_cancelled_owner_read_settles_physical_work_and_never_returns_body(tmp_path, monkeypatch):
    from control_plane.principal_ruling_target import PrincipalRulingTarget
    from tests.test_product_acceptance_workspace_read import provider
    import integrations.product_acceptance_selector as selector
    bind_actual_issuer(monkeypatch)
    with case(tmp_path, monkeypatch) as (runtime, owner, _, _, selected, run):
        obligation = anchor(runtime, owner, selected)
        target = PrincipalRulingTarget(selected['work_ref'], obligation.obligation_id, 'test-owner')
        started, release, settled = threading.Event(), threading.Event(), threading.Event()
        actual = selector.read_original_acceptance_selection
        def blocked(*args, **kwargs):
            started.set()
            try:
                assert release.wait(3)
                return actual(*args, **kwargs)
            finally: settled.set()
        monkeypatch.setattr(selector, 'read_original_acceptance_selection', blocked)
        def execute(bound):
            svc, frame, _ = provider(tmp_path, runtime, owner.reader, selected, bound)
            frame = {**frame, 'schema': 'mastermind.executive_workspace_read.v2', 'operation': 'mission_v3',
                'selection': {k: selected[k] for k in ('work_ref', 'root_job_id')}}
            async def cancel():
                task = asyncio.create_task(read_original_acceptance_observation(svc, frame, owner_target=target))
                try:
                    assert await asyncio.to_thread(started.wait, 2)
                    task.cancel(); await asyncio.sleep(.01)
                    task.cancel(); await asyncio.sleep(.01)
                    assert not task.done() and not settled.is_set()
                finally: release.set()
                with pytest.raises(asyncio.CancelledError): await task
                assert settled.is_set()
            asyncio.run(cancel())
        before = runtime.events.list_events()
        run(execute)
        assert runtime.events.list_events() == before


@pytest.mark.parametrize('defect', ['work', 'ordinary', 'fingerprint', 'thread', 'operation', 'issuer', 'root'])
def test_foreign_or_uncorrelated_original_anchor_has_no_fallback(tmp_path, monkeypatch, defect):
    bind_actual_issuer(monkeypatch)
    with case(tmp_path, monkeypatch) as (runtime, owner, _, _, selected, run):
        obligation = anchor(runtime, owner, selected, defect=defect)
        if defect == 'root': selected = {**selected, 'root_job_id': 'JOB-999'}
        # A second valid source must never rescue a bad exact selection.
        if defect in ('ordinary', 'operation'):
            anchor(runtime, owner, {**selected, 'root_job_id': owner._test_root.job_id})
        before = runtime.events.list_events()
        with pytest.raises(ProductAcceptanceSelectionUnavailable, match='^PRODUCT_ACCEPTANCE_SELECTION_UNAVAILABLE$'):
            run(lambda bound: read(bound, owner, selected, obligation))
        assert runtime.events.list_events() == before


@pytest.mark.parametrize('guard_kind', ['missing', 'truthy', 'async', 'revoked_after'])
def test_receiving_owner_guard_is_required_before_and_after_read(tmp_path, monkeypatch, guard_kind):
    bind_actual_issuer(monkeypatch)
    with case(tmp_path, monkeypatch) as (runtime, owner, _, _, selected, run):
        obligation = anchor(runtime, owner, selected)
        calls = []
        def guard():
            calls.append(True)
            if len(calls) == 2: raise PermissionError('PRIVATE_PERMISSION_DETAIL')
        async def async_guard(): pass
        selected_guard = {'missing': None, 'truthy': lambda: True, 'async': async_guard,
                          'revoked_after': guard}[guard_kind]
        with pytest.raises(ProductAcceptanceSelectionUnavailable) as caught:
            run(lambda bound: read(bound, owner, selected, obligation, receiving_read_guard=selected_guard))
        assert str(caught.value) == 'PRODUCT_ACCEPTANCE_SELECTION_UNAVAILABLE'
        assert caught.value.__cause__ is None
        if guard_kind == 'revoked_after': assert len(calls) == 2


def test_unbound_runtime_and_anchor_drift_do_not_publish_selector(tmp_path, monkeypatch):
    bind_actual_issuer(monkeypatch)
    with case(tmp_path, monkeypatch) as (runtime, owner, _, _, selected, run):
        obligation = anchor(runtime, owner, selected)
        with pytest.raises(ProductAcceptanceSelectionUnavailable):
            read(runtime, owner, selected, obligation)
        import integrations.product_acceptance_selector as selector
        original = selector.read_original_principal_dialogue_obligation
        calls = []
        def changed(*args, **kwargs):
            result = original(*args, **kwargs); calls.append(True)
            return dataclasses.replace(result, observed_event_ids=()) if len(calls) == 2 else result
        monkeypatch.setattr(selector, 'read_original_principal_dialogue_obligation', changed)
        with pytest.raises(ProductAcceptanceSelectionUnavailable):
            run(lambda bound: read(bound, owner, selected, obligation))
        assert len(calls) == 2


@pytest.mark.parametrize('change', ['none', 'pending_parent', 'permission', 'permission_aba',
    'publication_aba', 'wrong_target', 'unbound', 'not_mission', 'after_await',
    'publication_after_await', 'owner_after_await'])
def test_existing_workspace_owner_composes_selector_and_receipt_with_current_guards(
    tmp_path, monkeypatch, change,
):
    from control_plane.principal_ruling_target import PrincipalRulingTarget
    from tests.test_product_acceptance_workspace_read import provider
    bind_actual_issuer(monkeypatch)
    with case(tmp_path, monkeypatch, complete=change != 'pending_parent') as (
        runtime, owner, _, _, selected, run,
    ):
        obligation = anchor(runtime, owner, selected)
        target = PrincipalRulingTarget(selected['work_ref'], obligation.obligation_id, 'test-owner')
        if change == 'wrong_target': target = dataclasses.replace(target, work_ref='WS:FOREIGN')
        before = runtime.events.list_events()
        def execute(bound):
            epoch = [0]
            def authorize(_): return change != 'permission'
            authorize.binding_digest = lambda _: str(epoch[0]) * 64
            svc, frame, sources = provider(tmp_path, runtime, owner.reader, selected, bound, authorize=authorize)
            if change == 'unbound': svc._bounded_runtime = lambda _: runtime
            frame = {**frame, 'schema': 'mastermind.executive_workspace_read.v2', 'operation': 'mission_v3',
                'selection': {k: selected[k] for k in ('work_ref', 'root_job_id')}}
            if change == 'not_mission': frame['operation'] = 'work'
            original = svc._read_mission_v4
            def changed(actual):
                result = original(actual)
                if change == 'permission_aba': epoch[0] += 2
                if change == 'publication_aba': sources[0].state_published_seq += 2
                return result
            svc._read_mission_v4 = changed
            if change in ('after_await', 'publication_after_await', 'owner_after_await'):
                import control_plane.workspace_read_service as workspace
                original_wait = workspace.await_owned
                async def waited(task):
                    result = await original_wait(task)
                    if change == 'after_await': epoch[0] += 1
                    elif change == 'publication_after_await': sources[0].state_published_seq += 2
                    else: svc.authorize = lambda _: True
                    return result
                monkeypatch.setattr(workspace, 'await_owned', waited)
            return asyncio.run(read_original_acceptance_observation(svc, frame, owner_target=target))
        if change in ('none', 'pending_parent'):
            result = run(execute)
            assert result['product_acceptance']['selection'] == selected
            assert result['mission']['source']['owner_observation']['state'] == 'SAME'
            assert result['product_acceptance']['state'] == ('ACCEPTED' if change == 'none' else 'UNAVAILABLE')
        else:
            with pytest.raises(ProductAcceptanceSelectionUnavailable): run(execute)
        assert runtime.events.list_events() == before
