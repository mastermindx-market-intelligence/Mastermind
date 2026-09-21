"""Real owner result/Mission integration. Namespace custody is fixture-only."""
import asyncio
import copy
import json
import threading
from contextlib import contextmanager
from dataclasses import replace

import pytest

from control_plane import executive_runtime as er
from control_plane import fabric_result_projection as frp
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.mastermind_workspace_app.contract import canonical, error, FRAME_SCHEMA_V2
from scripts import chairman_control_room as ccr
from tests.test_fabric_result_projection import complete_all_severity_chain, _bound_reader, _release, _select_bound
from tests.test_workspace_read_service import cache_fixture, frame
from tests.test_mission_workspace import _owner_observation_inputs


@pytest.fixture
def result_owner(tmp_path):
    writer, root, work, review = complete_all_severity_chain(tmp_path / 'runtime')
    keeper, namespace, binding, reader = _bound_reader(writer)
    try:
        snapshot, receipt = _select_bound(reader, root.job_id, review)
        selection = dict(work_ref=snapshot.root_metadata.work_ref or 'WS:ONE',
                         root_job_id=root.job_id, job_id=review.job.job_id,
                         attempt_id=review.attempt.attempt_id, result_envelope_digest=review.result_digest)
        owners, clock, cache = cache_fixture(tmp_path)
        doc = _owner_observation_inputs()['control_room']
        doc = json.loads(json.dumps(doc).replace('JOB-1', root.job_id).replace('WS:ONE', selection['work_ref']).replace('2026-09-20', '2026-09-21'))
        doc['generated_at'] = owners[0].state_cache['doc']['generated_at']
        doc['autonomy']['generated_at'] = doc['generated_at']
        doc['autonomy']['schema'] = 'mastermind.autonomy_control_room.v1'
        row = doc['autonomy']['responsibilities'][0]
        row['freshness'] = 'current'
        row['validity'] = owners[0].state_cache['doc']['autonomy']['responsibilities'][0]['validity']
        owners[0].state_cache['doc'] = doc
        owners[0].state_cache.pop('source_validity_bounds', None)
        with owners[0].state_lock:
            ccr._publish_source_validity(owners[0], doc, tuple(clock), tuple(clock))
        yield dict(writer=writer, reader=reader, namespace=namespace, binding=binding,
                   owners=owners, clock=clock, cache=cache, selection=selection,
                   snapshot=snapshot, receipt=receipt, expected=frp.project_fabric_role_result(snapshot, receipt))
    finally:
        _release(keeper, binding)


def request(owner, operation='result'):
    value = frame()
    value.update(schema=FRAME_SCHEMA_V2, operation=operation, selection=dict(owner['selection']))
    if operation == 'mission_v3':
        value['selection'] = {k: value['selection'][k] for k in ('work_ref', 'root_job_id')}
    return value


def service(owner, **kwargs):
    def bound(actual):
        assert actual is owner['writer']
        return owner['reader']
    return WorkspaceReadService(cache=owner['cache'], runtime=owner['writer'],
        authorize=kwargs.pop('authorize', lambda p: True), armed={}, runtime_identity={'db_present': True},
        bounded_runtime=kwargs.pop('bounded_runtime', bound), **kwargs)


def call(owner, **kwargs):
    return asyncio.run(service(owner, **kwargs).handle_frame(request(owner)))


def test_actual_result_preserves_shared_document_and_finalized_receipt(result_owner):
    o = result_owner
    before = o['namespace'].entries
    seen = {}
    def project(snapshot, receipt):
        seen['projection'] = frp.project_fabric_role_result(snapshot, receipt)
        return seen['projection']
    result = call(o, result_project=project)['result']
    assert result['availability'] == 'AVAILABLE'
    assert result['result'] == seen['projection'].complete
    assert result['source_observation']['runtime'] == result['result']['generation']
    assert result['result']['review']['verdict'] == 'reject'
    assert result['selection']['result_envelope_digest'] != result['result']['review']['reviewed_result_digest']
    assert o['namespace'].entries == before + 1 == o['namespace'].exits
    assert not o['namespace'].active
    assert len(canonical({'ok': True, 'result': result})) + 1 <= 16384


def test_missing_ccr_join_404_before_read(result_owner):
    o = result_owner
    o['owners'][0].state_cache['doc']['work'] = []
    before = o['namespace'].entries
    assert call(o) == error('selection_not_found', 404)
    assert o['namespace'].entries == before


@pytest.mark.parametrize('exception,reason', [(er.RuntimeReadUnavailable('unproven'), 'SOURCE_UNAVAILABLE'),
    (er.StateConflict('unproven'), 'SOURCE_UNAVAILABLE'), (ValueError('private'), 'SOURCE_UNAVAILABLE'),
    (er.RuntimeRoleResultOverBudget(), 'OVER_BUDGET')])
def test_typed_acquisition_refusal_discards_source(result_owner, exception, reason):
    def refused(*a, **kw): raise exception
    result = call(result_owner, result_acquire=refused,
                  result_project=lambda *a: pytest.fail('projected refused acquisition'))['result']
    assert result['availability'] == 'UNAVAILABLE' and result['reason_codes'] == [reason]
    assert result['result'] is None
    assert result['source_observation']['control_room'] is None
    assert result['source_observation']['runtime'] is None
    assert result['source_observation']['state'] == 'UNKNOWN'


@pytest.mark.parametrize('mutation', ['owner', 'publication', 'document'])
def test_proven_ccr_change_discards_result(result_owner, mutation):
    o = result_owner; original = o['cache'].snapshot; count = [0]
    def snapshot():
        count[0] += 1
        if count[0] == 2:
            if mutation == 'owner':
                owners, _, _ = cache_fixture(o['writer'].store.root)
                o['owners'][0] = owners[0]
            elif mutation == 'publication': o['owners'][0].state_published_seq += 1
            else: o['owners'][0].state_cache['doc']['work'][0]['agent_os']['title'] = 'changed'
        return original()
    o['cache'].snapshot = snapshot
    body = call(o)['result']
    assert body['reason_codes'] == ['SOURCE_CHANGED']
    assert body['source_observation']['state'] == 'CONFLICT'
    assert body['source_observation']['control_room'] is None and body['source_observation']['runtime'] is None


@pytest.mark.parametrize('stage', ['before', 'after'])
@pytest.mark.parametrize('mutation', ['disable', 'missing_stamp', 'changed_stamp'])
def test_permission_reload_gates_material(result_owner, stage, mutation, monkeypatch):
    authority = {'enabled': True, 'digest': 'a' * 64}
    def change():
        if mutation == 'disable': authority['enabled'] = False
        else: authority['digest'] = None if mutation == 'missing_stamp' else 'b' * 64
    def authorize(p): return authority['enabled']
    authorize.binding_digest = lambda p: authority['digest']
    o = result_owner; original = er.Runtime.observe_bounded_read
    @contextmanager
    def observed(runtime):
        with original(runtime) as read: yield read
        if runtime is o['reader'] and stage == 'after': change()
    monkeypatch.setattr(er.Runtime, 'observe_bounded_read', observed)
    if stage == 'before':
        if mutation == 'changed_stamp': authority['digest'] = None  # absence of an admitted initial stamp
        else: change()
    before = o['namespace'].entries
    assert call(o, authorize=authorize) == error('access_denied', 403)
    assert o['namespace'].entries - before == (stage == 'after')


def test_two_cancellations_wait_for_actual_physical_close(result_owner, monkeypatch):
    o = result_owner; entered = threading.Event(); release = threading.Event(); closed = threading.Event()
    original = er.RuntimeStore._close_read_connection
    def blocked(binding, connection):
        if binding is o['reader'].store:
            entered.set()
            if not release.wait(5): raise AssertionError('fixture close barrier expired')
        result = original(binding, connection)
        if binding is o['reader'].store: closed.set()
        return result
    monkeypatch.setattr(er.RuntimeStore, '_close_read_connection', blocked)
    async def run():
        task = asyncio.create_task(service(o).handle_frame(request(o)))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            for _ in range(2):
                task.cancel(); await asyncio.sleep(0); await asyncio.sleep(0)
                assert not task.done() and not closed.is_set()
            release.set()
            with pytest.raises(asyncio.CancelledError): await asyncio.wait_for(task, 5)
            assert closed.is_set() and not o['namespace'].active
        finally:
            release.set()
            if not task.done():
                try: await asyncio.wait_for(task, 5)
                except asyncio.CancelledError: pass
    asyncio.run(run())


@pytest.mark.parametrize('kind', ['complete', 'fallback', 'discard', 'foreign_selector'])
def test_wrapper_uses_exact_projector_documents(result_owner, kind):
    o = result_owner; expected = o['expected']; complete = copy.deepcopy(expected.complete); fallback = copy.deepcopy(expected.content_over_budget)
    if kind in ('fallback', 'discard'): complete['content']['summary'] = '漢' * 6000
    if kind == 'discard': fallback['omitted'] = ['x' * 17000]
    if kind == 'foreign_selector': complete['selection']['job_id'] = 'JOB-999999'
    projection = frp.FabricRoleResultProjection(complete=complete, content_over_budget=fallback)
    body = call(o, result_project=lambda *a: projection)['result']
    if kind == 'complete': assert body['result'] == complete and body['availability'] == 'AVAILABLE'
    elif kind == 'fallback': assert body['result'] == fallback and body['availability'] == 'CONTENT_OVER_BUDGET'
    else:
        assert body['result'] is None and body['source_observation']['runtime'] is None
        assert body['reason_codes'] == ['SOURCE_UNAVAILABLE' if kind == 'foreign_selector' else 'RESPONSE_OVER_BUDGET']
    assert len(canonical({'ok': True, 'result': body})) + 1 <= 16384


def test_canonical_mission_v3_uses_same_custody_and_nested_receipt(result_owner):
    o = result_owner; before = o['namespace'].entries
    result = asyncio.run(service(o).handle_frame(request(o, 'mission_v3')))
    assert result['ok'] is True, result
    body = result['result']
    assert body['schema'] == 'mastermind.mission_workspace.v3'
    assert body['read_state']['state'] == 'CURRENT', body['source']
    assert body['source']['owner_observation']['runtime']['state'] == 'SAME'
    assert body['result_refs']['generation'] == {k: v for k, v in body['source']['owner_observation']['runtime'].items() if k != 'snapshot_digest'}
    assert any(ref['result_envelope_digest'] == o['selection']['result_envelope_digest'] for ref in body['result_refs']['refs'])
    assert o['namespace'].entries == before + 1 == o['namespace'].exits


@pytest.mark.parametrize('fault', ['close', 'identity', 'work_ref'])
def test_unproven_runtime_material_never_reaches_projector(result_owner, monkeypatch, fault):
    o=result_owner
    kwargs={'result_project':lambda *a:pytest.fail('unqualified material projected')}
    if fault == 'close':
        original=er.RuntimeStore._close_read_connection
        def close(store, connection):
            original(store, connection)
            if store is o['reader'].store:raise er.RuntimeReadUnavailable('fixture close uncertainty')
        monkeypatch.setattr(er.RuntimeStore,'_close_read_connection',close)
    else:
        snapshot=o['snapshot']
        if fault=='identity':snapshot=replace(snapshot,observation_source_identity='f'*32)
        else:snapshot=replace(snapshot,root_metadata=replace(snapshot.root_metadata,work_ref='WS:FOREIGN'))
        kwargs['result_acquire']=lambda *a,**k:(snapshot,o['receipt'])
    body=call(o,**kwargs)['result']
    assert body['availability']=='UNAVAILABLE' and body['reason_codes']==['SOURCE_UNAVAILABLE']
    assert body['result'] is None and body['source_observation']['runtime'] is None


@pytest.mark.parametrize('size',[16383,16384,16385])
def test_whole_wrapper_chooses_actual_fallback_at_exact_boundary(result_owner,size):
    o=result_owner; before=o['cache'].snapshot(); svc=service(o)
    complete=copy.deepcopy(o['expected'].complete);fallback=o['expected'].content_over_budget
    complete['content']['summary']='漢'
    body={'schema':'mastermind.workspace_role_result.v1','selection':o['selection'],
          'availability':'AVAILABLE','reason_codes':[],
          'source_observation':svc._result_observation(before,before,o['selection'],o['receipt']),
          'result':complete}
    complete['content']['summary']+='x'*(size-len(canonical({'ok':True,'result':body}))-1)
    assert len(canonical({'ok':True,'result':body}))+1==size
    projected=frp.FabricRoleResultProjection(complete=complete,content_over_budget=fallback)
    response=call(o,result_project=lambda *a:projected)
    assert response['result']['result']==(complete if size<=16384 else fallback)
    assert response['result']['availability']==('AVAILABLE' if size<=16384 else 'CONTENT_OVER_BUDGET')
