"""New read route uses real Runtime/receipt/reducers and existing auth brackets."""
import asyncio
import json
import os
import threading
from pathlib import Path

import pytest

from common import product_acceptance_read_contract as contract
from control_plane.workspace_read_service import WorkspaceReadService
from tests.test_product_acceptance_read_projection import case
from tests.test_workspace_read_service import cache_fixture, frame
from tests.test_mission_workspace import _owner_observation_inputs
from scripts import chairman_control_room as ccr


def provider(tmp_path, runtime, basis_reader, selected, bound, *, authorize=lambda _: True):
    from integrations.product_acceptance_read import read_acceptance
    from integrations.product_acceptance_selector import read_original_acceptance_observation
    owners, clock, cache = cache_fixture(tmp_path)
    doc = _owner_observation_inputs()['control_room']
    doc = json.loads(json.dumps(doc).replace('JOB-1', selected['root_job_id'])
        .replace('WS:ONE', selected['work_ref']).replace('2026-09-20', '2026-09-21'))
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
    svc = WorkspaceReadService(cache=cache, runtime=runtime, authorize=authorize, armed={},
        runtime_identity={'db_present': True}, bounded_runtime=lambda _: bound,
        product_acceptance_basis_reader=basis_reader,
        product_acceptance_read=read_acceptance,
        product_acceptance_observe=read_original_acceptance_observation)
    request = {**frame(), 'schema': contract.FRAME_SCHEMA, 'operation': contract.OPERATION, 'selection': selected}
    return svc, request, owners


def test_real_current_mission_and_exact_terminal_acceptance_are_projected(tmp_path, monkeypatch):
    with case(tmp_path, monkeypatch) as (runtime, owner, target, _, selected, run):
        events = runtime.events.list_events()
        def read(bound):
            svc, request, _ = provider(tmp_path, runtime, owner.reader, selected, bound)
            return asyncio.run(svc.handle_frame(request))
        response = run(read)
        assert response['ok'] is True, response
        body = response['result']
        assert body['schema'] == contract.MISSION_SCHEMA
        assert body['mission']['read_state']['state'] == 'CURRENT', body['mission']['source']
        assert body['mission']['acceptance']['state'] == 'NOT_PROJECTED'
        assert body['product_acceptance']['state'] == 'ACCEPTED', body['product_acceptance']
        assert body['product_acceptance']['receipt']['subject_job_id'] == target.job_id
        assert runtime.events.list_events() == events
        destination = os.environ.get('R2_ACCEPTANCE_FIXTURE')
        if destination:
            Path(destination).write_text(json.dumps(body, sort_keys=True, indent=2)+'\n')


@pytest.mark.parametrize('mutation', ['publication_aba', 'permission_aba'])
def test_currentness_or_permission_change_withholds_accepted_receipt(tmp_path, monkeypatch, mutation):
    with case(tmp_path, monkeypatch) as (runtime, owner, _, _, selected, run):
        def read(bound):
            authorize = lambda _: True
            epochs = ['a'*64, 'b'*64]
            if mutation == 'permission_aba': authorize.binding_digest = lambda _: epochs.pop(0)
            svc, request, owners = provider(tmp_path, runtime, owner.reader, selected, bound, authorize=authorize)
            if mutation == 'publication_aba':
                original, count = svc.cache.snapshot, [0]
                def snapshot():
                    count[0] += 1
                    if count[0] == 2:
                        # Content returns to the same bytes, but its publication epoch changed.
                        owners[0].state_published_seq += 2
                    return original()
                svc.cache.snapshot = snapshot
            return asyncio.run(svc.handle_frame(request))
        response = run(read)
        if mutation == 'permission_aba':
            assert response['ok'] is False and response['status'] == 403
        else:
            assert response['result']['product_acceptance']['state'] == 'UNAVAILABLE'
            assert response['result']['product_acceptance']['receipt'] is None


def test_cancellation_settles_exact_read_and_never_discloses_result(tmp_path, monkeypatch):
    owners, _, cache = cache_fixture(tmp_path)
    svc = WorkspaceReadService(cache=cache, runtime=object(), authorize=lambda _: True,
        armed={}, runtime_identity={})
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    def read(_):
        started.set()
        try:
            assert release.wait(3)
            return {'ok': True, 'result': {'should_not_be_disclosed': True}}
        finally:
            finished.set()
    monkeypatch.setattr(svc, '_read_mission_v4', read)
    request = {**frame(), 'schema': contract.FRAME_SCHEMA, 'operation': contract.OPERATION,
        'selection': {'work_ref':'WS:ONE','root_job_id':'JOB-001','request_message_key':'asd-mcp-'+'a'*32}}
    async def execute():
        task = asyncio.create_task(svc.handle_frame(request))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            task.cancel(); await asyncio.sleep(.02)
            task.cancel(); await asyncio.sleep(.02)
            assert not task.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError): await task
        assert finished.is_set()
    asyncio.run(execute())
