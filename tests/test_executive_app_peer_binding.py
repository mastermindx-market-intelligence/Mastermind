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


def test_installed_boot_helper_is_isolated_and_grounded(tmp_path, monkeypatch):
    from control_plane import ceo_boot_packet
    from integrations.executive_mcp import installed as installed_module

    repo = tmp_path / 'mastermind'
    macro = tmp_path / 'macro'
    runtime = tmp_path / 'runtime'
    for path in (repo, macro, runtime):
        path.mkdir()
    boot_python = tmp_path / 'sealed-python'
    mastermind_sha = 'a' * 40
    macro_sha = 'b' * 40
    packet = {
        'schema': ceo_boot_packet.SCHEMA,
        'mastermind': {'sha': mastermind_sha},
        'macro': {'sha': macro_sha},
    }
    seen = {}

    class Result:
        returncode = 0
        stdout = json.dumps(packet)

    def fake_run(argv, **kwargs):
        seen['argv'] = list(argv)
        seen['kwargs'] = dict(kwargs)
        return Result()

    def fake_sha(path):
        return mastermind_sha if path.resolve() == repo.resolve() else macro_sha

    monkeypatch.setattr(installed_module.subprocess, 'run', fake_run)
    monkeypatch.setattr(installed_module.ceo_boot_packet, 'git_sha', fake_sha)
    readers = installed_module.InstalledExecutiveReaders(
        repo_root=repo, macro_root=macro, runtime_root=runtime,
        boot_python=boot_python,
    )
    try:
        result = readers._installed_packet(
            repo_root=repo, macro_root_flag=str(macro), timeout=3.0,
            now='2026-09-16T10:00:00Z',
        )
        assert result == packet
        assert seen['argv'][:3] == [str(boot_python), '-I', '-B']
        env = seen['kwargs']['env']
        assert 'HOME' not in env
        assert env['PYTHONNOUSERSITE'] == '1'
        assert env['GIT_CONFIG_COUNT'] == '2'
        assert {env['GIT_CONFIG_VALUE_0'], env['GIT_CONFIG_VALUE_1']} == {
            str(repo.resolve()), str(macro.resolve()),
        }
        assert env['MACRO_MASTERMIND_REPO'] == str(repo.resolve())
    finally:
        asyncio.run(readers.aclose())


def test_installed_boot_helper_grounding_mismatch_degrades(tmp_path, monkeypatch):
    from control_plane import ceo_boot_packet
    from integrations.executive_mcp import installed as installed_module

    repo = tmp_path / 'mastermind'
    macro = tmp_path / 'macro'
    runtime = tmp_path / 'runtime'
    for path in (repo, macro, runtime):
        path.mkdir()
    packet = {
        'schema': ceo_boot_packet.SCHEMA,
        'mastermind': {'sha': 'c' * 40},
        'macro': {'sha': 'd' * 40},
    }

    class Result:
        returncode = 0
        stdout = json.dumps(packet)

    monkeypatch.setattr(installed_module.subprocess, 'run', lambda *a, **k: Result())
    monkeypatch.setattr(installed_module.ceo_boot_packet, 'git_sha', lambda _p: 'a' * 40)
    monkeypatch.setattr(
        installed_module.ceo_boot_packet, 'build_packet',
        lambda **_kwargs: {'schema': ceo_boot_packet.SCHEMA, 'degraded': []},
    )
    readers = installed_module.InstalledExecutiveReaders(
        repo_root=repo, macro_root=macro, runtime_root=runtime,
        boot_python=tmp_path / 'sealed-python',
    )
    try:
        result = readers._installed_packet(
            repo_root=repo, macro_root_flag=str(macro), timeout=3.0,
        )
        assert result['degraded'] == [
            'installed boot helper unavailable: grounding_mismatch'
        ]
    finally:
        asyncio.run(readers.aclose())
