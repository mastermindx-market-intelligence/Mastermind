"""Continuation selects only the same current qualified catalogue; no cursor store."""
import asyncio
import copy
import json
import subprocess

import httpx
import pytest

from common import workspace_project_archive_contract as wire
from control_plane.workspace_read_service import WorkspaceReadService, _qualified, digest
from control_plane.workspace_project_archive_read import ProjectArchiveReadAdapter
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA, principal_frame, workspace_authorizers
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_agentos_project_archive_source import bound, record
from tests.test_workspace_read_service import cache_fixture
from tests.test_workspace_read_app import rsa_key, _authenticator, _workspace_token, NOW, _make_app
from tests.test_workspace_result_socket import control, short_socket_root
from tests.test_workspace_project_archive_read import ROUTE


def many_catalogue(tmp_path, macro_sha, count):
    owners, clock, cache = cache_fixture(tmp_path)
    doc = owners[0].state_cache['doc']
    work, responsibility = copy.deepcopy(doc['work'][0]), copy.deepcopy(doc['autonomy']['responsibilities'][0])
    refs = ['WS:PAGE-' + str(i).zfill(3) for i in range(count)]
    doc['work'] = []
    doc['autonomy']['responsibilities'] = []
    for i, ref in enumerate(refs):
        item, row = copy.deepcopy(work), copy.deepcopy(responsibility)
        item['work_ref'] = ref
        row.update(responsibility_ref=ref, root_job_id='JOB-' + str(i + 1), root_job_candidates=['JOB-' + str(i + 1)])
        doc['work'].append(item); doc['autonomy']['responsibilities'].append(row)
    doc['sources'] = {'macro_sha': macro_sha}
    from scripts import chairman_control_room as ccr
    with owners[0].state_lock: ccr._publish_source_validity(owners[0], doc, tuple(clock), tuple(clock))
    assert _qualified(cache.snapshot())
    return owners, cache, refs


def test_real_helper_reaches_archived_record_beyond_first128_through_signed_socket(tmp_path, monkeypatch, rsa_key, short_socket_root):
    async def run():
        (tmp_path / 'source').mkdir(); (tmp_path / 'cache').mkdir()
        collector, seen = bound(tmp_path / 'source', monkeypatch)
        refs = ['WS:PAGE-' + str(i).zfill(3) for i in range(129)]
        for i, ref in enumerate(refs):
            value = record(archived=i == 128)
            old = 'ARCHIVE-TEST' if i == 128 else 'UNDECLARED-TEST'
            (seen['macro'] / ('agentos/workstreams/WS-' + ref[3:] + '.md')).write_text(value.replace(old, ref[3:]))
        subprocess.run(['git', '-C', str(seen['macro']), 'add', '.'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(seen['macro']), 'commit', '-qm', 'inert129 catalogue'], check=True, capture_output=True)
        seen['sha'] = subprocess.check_output(['git', '-C', str(seen['macro']), 'rev-parse', 'HEAD'], text=True).strip()
        owners, cache, refs = many_catalogue(tmp_path / 'cache', seen['sha'], 129)
        auth = _authenticator(rsa_key); token = _workspace_token(rsa_key)
        principal = await auth.verify_authorization_header('Bearer ' + token, now=NOW)
        slots = {'schema': BINDINGS_SCHEMA, 'profiles': {
            'web': {'enabled': True, 'binding': dict(principal_frame(principal), permission_digest='a' * 64)},
            'mac': {'enabled': False, 'binding': None}}}
        app_gate, frame_gate = workspace_authorizers(policy=auth.policy, load_bindings=lambda: slots)
        class NoRuntime:
            def __getattr__(self, key): pytest.fail('Archive continuation acquired Runtime')
        reader = collector.project_archive_reader(macro_root=seen['macro'])
        provider = WorkspaceReadService(cache=cache, runtime=NoRuntime(), authorize=frame_gate, armed={}, runtime_identity={}, project_archive_reader=reader)
        service = control(tmp_path / 'service', short_socket_root, lambda _: provider)
        await service.start()
        app = create_workspace_app(WorkspaceAppConfig(authenticator=auth, now=lambda: NOW, authorize_principal=app_gate,
            client=CeoIngressWorkspaceClient(service.ceo_ingress_socket_path, timeout_seconds=30)))
        headers = {'Authorization': 'Bearer ' + token}
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://mcp.mastermind-x.com') as client:
                first = await client.get(ROUTE, headers=headers)
                assert first.status_code == 200, first.text
                a = wire.validate_body(first.json())
                assert a['catalogue']['work_refs'] == refs[:128] and a['sample']['items'] == []
                cursor = {'after_work_ref': a['catalogue']['work_refs'][-1], 'catalogue_digest': a['catalogue']['document_digest']}
                second = await client.get(ROUTE, params=cursor, headers=headers)
                assert second.status_code == 200, second.text
                b = wire.validate_body(second.json())
                assert b['catalogue']['work_refs'] == refs[128:]
                assert [row['work_ref'] for row in b['sample']['items']] == [refs[128]]
                assert a['catalogue']['work_refs'] + b['catalogue']['work_refs'] == refs
                assert b['catalogue']['qualified_catalogue_count'] == 129
                assert b['sample']['coverage']['company_total'] is None
                before = len([argv for argv, _ in seen['calls'] if argv[0] != 'git'])
                for changed in [dict(cursor, catalogue_digest='f' * 64), dict(cursor, after_work_ref='WS:FOREIGN')]:
                    rejected = await client.get(ROUTE, params=changed, headers=headers)
                    assert rejected.status_code == 503 and rejected.json()['sample'] is None
                assert len([argv for argv, _ in seen['calls'] if argv[0] != 'git']) == before == 2
                slots['profiles']['web']['enabled'] = False
                revoked = await client.get(ROUTE, params=cursor, headers=headers)
                assert revoked.status_code == 403
                assert len([argv for argv, _ in seen['calls'] if argv[0] != 'git']) == before
        finally: await service.close()
    asyncio.run(run())


def test_all500_supplied_refs_have_bounded_disjoint_continuations_from_existing_owner(tmp_path):
    _owners, cache, refs = many_catalogue(tmp_path, 'a' * 40, 500)
    snapshot, seen, cursor = cache.snapshot(), [], None
    while True:
        page = ProjectArchiveReadAdapter._catalogue(snapshot, cursor)
        current = page['work_refs']
        assert len(current) <= 128 and not set(current).intersection(seen)
        seen.extend(current)
        if len(seen) == page['qualified_catalogue_count']: break
        cursor = {'after_work_ref': current[-1], 'catalogue_digest': page['document_digest']}
    assert seen == refs and len(seen) == 500


@pytest.mark.parametrize('query', [
    '?after_work_ref=WS:PAGE-127', '?catalogue_digest=' + 'a' * 64,
    '?after_work_ref=../private&catalogue_digest=' + 'a' * 64,
    '?after_work_ref=WS:PAGE-127&catalogue_digest=' + 'a' * 64 + '&after_work_ref=WS:PAGE-128',
    '?after_work_ref=WS:PAGE-127&catalogue_digest=' + 'a' * 64 + '&path=/private'])
def test_continuation_query_is_closed_before_backend(rsa_key, query):
    app, backend = _make_app(rsa_key)
    response = app.get(ROUTE + query, headers={'Authorization': 'Bearer ' + _workspace_token(rsa_key)})
    assert response.status_code == 400 and backend.calls == []


def test_continuation_is_not_a_grant_and_frame_cannot_carry_raw_members():
    from tests.test_workspace_read_service import frame
    principal = frame()['principal']
    cursor = {'after_work_ref': 'WS:PAGE-127', 'catalogue_digest': 'a' * 64}
    value = {'schema': wire.PAGE_FRAME_SCHEMA, 'operation': wire.PAGE_OPERATION, 'selection': cursor, 'principal': principal}
    assert wire.validate_read_frame(value) == value
    for key, extra in [('work_refs', ['WS:FOREIGN']), ('root_job_id', 'JOB-1'), ('source_commit', 'b' * 40)]:
        with pytest.raises(ValueError): wire.validate_read_frame(dict(value, **{key: extra}))
