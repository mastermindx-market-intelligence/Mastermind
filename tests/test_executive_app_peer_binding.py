"""The installed App gets its own exact peer and no C1 capabilities."""
import asyncio
import json
import os

import pytest

from control_plane import executive_ceo_ingress as ingress
from control_plane.executive_service import ExecutiveControlService
from tests.test_executive_ceo_ingress import (
    _config, _FakeGrounding, _FakeSupervisor, _raw_ceo_request,
    _submit_v2_bytes, _status_v2_bytes, _submit_bytes,
    _research_request, GROUNDING_A,
)
from tests.test_executive_ceo_ingress import short_socket_root  # noqa: F401


def test_app_peer_admits_once_without_arming_c1(tmp_path, short_socket_root, monkeypatch):
    async def exercise():
        from control_plane.executive_service import CeoIngressAppBinding
        app_uid = os.geteuid()
        c1_uid = app_uid + 1000
        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / 'ceo.sock',
            ceo_ingress_peer_uid=c1_uid,
            ceo_ingress_grounding_provider=_FakeGrounding(error=RuntimeError()),
            ceo_ingress_armed=False,
            ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=app_uid, armed=True, grounding_provider=_FakeGrounding(),
            ),
        )
        await service.start()
        try:
            first = await _raw_ceo_request(service.ceo_ingress_socket_path, _submit_v2_bytes())
            again = await _raw_ceo_request(service.ceo_ingress_socket_path, _submit_v2_bytes())
            assert first['ok'] is True, first
            assert again['result']['job_id'] == first['result']['job_id']
            jobs = service.runtime.jobs.list_jobs()
            assert len(jobs) == 1
            assert service.runtime.attempts.list_attempts(jobs[0].job_id) == []
            assert service.runtime.workers.list_workers() == []
            # The App never obtains the C1 v1 surface.
            v1 = await _raw_ceo_request(service.ceo_ingress_socket_path,
                _submit_bytes(observed_grounding=GROUNDING_A, request=_research_request()))
            assert v1['error']['code'] == 'peer_denied'
            monkeypatch.setattr('control_plane.executive_service._peer_uid', lambda sock: c1_uid)
            c1 = await _raw_ceo_request(service.ceo_ingress_socket_path, _submit_v2_bytes())
            assert c1['error']['code'] == 'ingress_unavailable'
            assert len(service.runtime.jobs.list_jobs()) == 1
        finally:
            await service.close()
    asyncio.run(exercise())


def test_unarmed_app_peer_cannot_create_job(tmp_path, short_socket_root):
    async def exercise():
        from control_plane.executive_service import CeoIngressAppBinding
        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / 'ceo.sock',
            ceo_ingress_peer_uid=os.geteuid()+1000,
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=os.geteuid(), armed=False, grounding_provider=_FakeGrounding(),
            ),
        )
        await service.start()
        try:
            result = await _raw_ceo_request(service.ceo_ingress_socket_path, _submit_v2_bytes())
            assert result['error']['code'] == 'ingress_unavailable'
            assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()
    asyncio.run(exercise())


@pytest.mark.parametrize('uid', [-1, True, '458'])
def test_app_binding_refuses_invalid_uid(uid):
    from control_plane.executive_service import CeoIngressAppBinding
    with pytest.raises(ValueError):
        CeoIngressAppBinding(peer_uid=uid, armed=False, grounding_provider=_FakeGrounding())


def test_app_reads_share_admitted_runtime_and_c1_cannot_read_them(tmp_path, short_socket_root, monkeypatch):
    async def exercise():
        from control_plane.executive_service import CeoIngressAppBinding, CEO_APP_READ_SCHEMA
        from integrations.executive_mcp.installed import InstalledExecutiveReaders
        config = _config(tmp_path, socket_root=short_socket_root)
        c1_uid = os.geteuid() + 1000
        readers = InstalledExecutiveReaders(
            repo_root=config.proof_source_repository,
            macro_root=config.proof_source_repository,
            runtime_root=config.runtime_root,
        )
        service = ExecutiveControlService(
            config, supervisor_factory=lambda runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root/'ceo.sock',
            ceo_ingress_peer_uid=c1_uid, ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=os.geteuid(), armed=True, grounding_provider=_FakeGrounding(),
                read_provider=readers,
            ),
        )
        await service.start()
        try:
            admitted = await _raw_ceo_request(service.ceo_ingress_socket_path, _submit_v2_bytes())
            job_id = admitted['result']['job_id']
            frame = {'schema': CEO_APP_READ_SCHEMA, 'tool': 'executive_job', 'arguments': {'job_id': job_id}}
            read = await _raw_ceo_request(service.ceo_ingress_socket_path, (json.dumps(frame)+'\n').encode())
            assert read['ok'] is True, read
            assert read['result']['ok'] is True, read
            assert read['result']['data']['job']['job_id'] == job_id
            assert read['result']['data']['attempt_count'] == 0
            frame['tool'] = 'submit_ceo_intent'
            frame['arguments'] = _research_request()
            denied = await _raw_ceo_request(service.ceo_ingress_socket_path, (json.dumps(frame)+'\n').encode())
            assert denied['ok'] is False
            frame['tool'] = 'executive_job'
            frame['arguments'] = {'job_id': job_id}
            monkeypatch.setattr('control_plane.executive_service._peer_uid', lambda sock: c1_uid)
            c1 = await _raw_ceo_request(service.ceo_ingress_socket_path, (json.dumps(frame)+'\n').encode())
            assert c1['ok'] is False
            assert len(service.runtime.jobs.list_jobs()) == 1
        finally:
            await service.close()
            await readers.aclose()
    asyncio.run(exercise())


def test_installed_fallback_delegates_to_canonical_boot_owner(tmp_path, monkeypatch):
    from control_plane import ceo_boot_packet
    from integrations.executive_mcp import installed as installed_module

    repo = tmp_path / 'mastermind'
    macro = tmp_path / 'macro'
    runtime = tmp_path / 'runtime'
    for path in (repo, macro, runtime):
        path.mkdir()
    expected = {'schema': ceo_boot_packet.SCHEMA, 'degraded': []}
    seen = {}

    def fake_builder(**kwargs):
        seen.update(kwargs)
        return expected

    monkeypatch.setattr(ceo_boot_packet, 'build_packet_in_interpreter', fake_builder)
    readers = installed_module.InstalledExecutiveReaders(
        repo_root=repo, macro_root=macro, runtime_root=runtime,
    )
    try:
        result = readers._installed_packet(
            repo_root=repo, macro_root_flag=str(macro), timeout=3.0,
            now='2026-09-16T10:00:00Z',
        )
        assert result == expected
        assert seen == {
            'boot_python': None,
            'repo_root': repo.resolve(),
            'macro_root': macro.resolve(),
            'timeout': 3.0,
            'now': '2026-09-16T10:00:00Z',
        }
    finally:
        asyncio.run(readers.aclose())


def test_installed_fallback_binding_mismatch_degrades_locally(tmp_path, monkeypatch):
    from control_plane import ceo_boot_packet
    from integrations.executive_mcp import installed as installed_module

    repo = tmp_path / 'mastermind'
    macro = tmp_path / 'macro'
    runtime = tmp_path / 'runtime'
    other = tmp_path / 'other'
    for path in (repo, macro, runtime, other):
        path.mkdir()
    monkeypatch.setattr(
        ceo_boot_packet, 'build_packet',
        lambda **_kwargs: {'schema': ceo_boot_packet.SCHEMA, 'degraded': []},
    )
    readers = installed_module.InstalledExecutiveReaders(
        repo_root=repo, macro_root=macro, runtime_root=runtime,
    )
    try:
        result = readers._installed_packet(
            repo_root=other, macro_root_flag=str(macro), timeout=3.0,
        )
        assert result['degraded'] == [
            'installed boot helper unavailable: source_binding_mismatch'
        ]
    finally:
        asyncio.run(readers.aclose())
