"""Principal Company Dialogue reuses the incumbent Executive service lifetime."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

import control_plane.executive_service as service_module
from control_plane.executive_service import (
    CompanyConsultationBinding,
    ExecutiveControlService,
    PrincipalCompanyDialogueBinding,
    ServiceError,
)
from test_executive_service import _FakeSupervisor, _config, short_socket_root


class Host:
    def __init__(self, runtime, *, gate=None):
        self.runtime = runtime
        self.gate = gate
        self.calls = 0
        self.entered = asyncio.Event()

    async def handle_connection(self, reader, writer):
        self.calls += 1
        self.entered.set()
        if self.gate is not None:
            await self.gate.wait()
        await reader.readline()
        if not writer.is_closing():
            writer.write(b"principal-accepted\n")
            await writer.drain()


def _service(tmp_path, short, *, gate=None, company=False):
    principal_hosts = []
    company_hosts = []

    def principal_factory(runtime):
        value = Host(runtime, gate=gate)
        principal_hosts.append(value)
        return value

    principal_path = short / "company" / "principal.sock"
    principal = PrincipalCompanyDialogueBinding(
        principal_path,
        worker_uid=451,
        group_gid=os.getegid(),
        host_factory=principal_factory,
    )

    company_binding = None
    company_path = short / "company" / "consult.sock"
    if company:
        def company_factory(runtime):
            value = Host(runtime)
            company_hosts.append(value)
            return value

        company_binding = CompanyConsultationBinding(
            company_path,
            worker_uid=451,
            group_gid=os.getegid(),
            host_factory=company_factory,
        )

    config = _config(tmp_path, socket_root=short, shutdown_grace_seconds=0.1)
    service = ExecutiveControlService(
        config,
        supervisor_factory=_FakeSupervisor,
        company_consultation_binding=company_binding,
        principal_company_dialogue_binding=principal,
    )
    return service, principal_path, principal_hosts, company_path, company_hosts


def test_principal_listener_binds_current_runtime_and_cleans_exact_socket(
    tmp_path, short_socket_root, monkeypatch
):
    monkeypatch.setattr(service_module, "_peer_uid", lambda _connection: 451)

    async def scenario():
        service, path, hosts, _, _ = _service(tmp_path, short_socket_root)
        assert hosts == []
        await service.start()
        try:
            assert hosts[0].runtime is service.runtime
            assert service._principal_company_dialogue_ready
            assert path.stat().st_mode & 0o777 == 0o660
            assert path.parent.stat().st_mode & 0o777 == 0o710

            reader, writer = await asyncio.open_unix_connection(path)
            writer.write(b"read_thread\n")
            await writer.drain()
            assert await reader.readline() == b"principal-accepted\n"
            assert await reader.read() == b""
            writer.close()
            await writer.wait_closed()
            assert hosts[0].calls == 1
        finally:
            await service.close()

        assert not path.exists()
        assert service._lock_fd is None
        assert not service._principal_company_dialogue_tasks

    asyncio.run(scenario())


@pytest.mark.parametrize("peer,ready", [(452, True), (451, False)])
def test_principal_listener_refuses_foreign_peer_and_unready_service(
    tmp_path, short_socket_root, monkeypatch, peer, ready
):
    monkeypatch.setattr(service_module, "_peer_uid", lambda _connection: peer)

    async def scenario():
        service, path, hosts, _, _ = _service(tmp_path, short_socket_root)
        await service.start()
        try:
            if not ready:
                service._service_state = "AWAITING_CANARY"
            reader, writer = await asyncio.open_unix_connection(path)
            assert await asyncio.wait_for(reader.read(), timeout=1) == b""
            writer.close()
            await writer.wait_closed()
            assert hosts[0].calls == 0
        finally:
            await service.close()

    asyncio.run(scenario())


def test_principal_and_consultation_listeners_coexist_without_aliasing(
    tmp_path, short_socket_root, monkeypatch
):
    monkeypatch.setattr(service_module, "_peer_uid", lambda _connection: 451)

    async def scenario():
        service, principal_path, principals, company_path, companies = _service(
            tmp_path,
            short_socket_root,
            company=True,
        )
        await service.start()
        try:
            assert service._principal_company_dialogue_ready
            assert service._company_consultation_ready
            assert principal_path != company_path
            assert principal_path.exists() and company_path.exists()

            for path, expected in (
                (principal_path, b"principal-accepted\n"),
                (company_path, b"principal-accepted\n"),
            ):
                reader, writer = await asyncio.open_unix_connection(path)
                writer.write(b"request\n")
                await writer.drain()
                assert await reader.readline() == expected
                writer.close()
                await writer.wait_closed()

            assert principals[0].calls == 1
            assert companies[0].calls == 1
        finally:
            await service.close()

        assert not principal_path.exists()
        assert not company_path.exists()

    asyncio.run(scenario())


def test_principal_binding_refuses_alias_of_company_socket(
    tmp_path, short_socket_root
):
    path = short_socket_root / "company" / "same.sock"
    company = CompanyConsultationBinding(
        path,
        worker_uid=451,
        group_gid=os.getegid(),
        host_factory=lambda _runtime: Host(_runtime),
    )
    principal = PrincipalCompanyDialogueBinding(
        path,
        worker_uid=451,
        group_gid=os.getegid(),
        host_factory=lambda _runtime: Host(_runtime),
    )
    config = _config(tmp_path, socket_root=short_socket_root)

    with pytest.raises(ValueError, match="must be distinct"):
        ExecutiveControlService(
            config,
            supervisor_factory=_FakeSupervisor,
            company_consultation_binding=company,
            principal_company_dialogue_binding=principal,
        )


def test_principal_partial_start_closes_listener_and_releases_custody(
    tmp_path, short_socket_root, monkeypatch
):
    async def scenario():
        service, path, hosts, _, _ = _service(tmp_path, short_socket_root)

        async def fail():
            assert service._principal_company_dialogue_server is not None
            assert not service._principal_company_dialogue_ready
            raise ServiceError("injected Operator start failure")

        monkeypatch.setattr(service, "_start_operator_serving", fail)
        with pytest.raises(ServiceError, match="injected"):
            await service.start()

        assert service._lock_fd is None
        assert service._server is None
        assert service._principal_company_dialogue_server is None
        assert service._principal_company_dialogue_host is None
        assert not path.exists()
        assert hosts

    asyncio.run(scenario())


def test_principal_never_reclaims_ambiguous_preexisting_socket_node(
    tmp_path, short_socket_root
):
    async def scenario():
        service, path, _, _, _ = _service(tmp_path, short_socket_root)
        path.parent.mkdir(mode=0o710)
        path.parent.chmod(0o710)
        os.chown(path.parent, os.geteuid(), os.getegid())
        path.write_text("preexisting node")

        with pytest.raises(ServiceError, match="pre-existing"):
            await service.start()

        assert path.is_file()
        assert service._lock_fd is None

    asyncio.run(scenario())


def test_principal_shutdown_never_unlinks_replaced_socket_inode(
    tmp_path, short_socket_root, monkeypatch
):
    monkeypatch.setattr(service_module, "_peer_uid", lambda _connection: 451)

    async def scenario():
        service, path, _, _, _ = _service(tmp_path, short_socket_root)
        await service.start()
        bound = path.lstat()

        path.unlink()
        path.write_text("foreign replacement", encoding="utf-8")
        await service.close()

        assert path.read_text(encoding="utf-8") == "foreign replacement"
        assert (bound.st_dev, bound.st_ino) != (
            path.lstat().st_dev,
            path.lstat().st_ino,
        )

    asyncio.run(scenario())


def test_principal_listener_test_is_in_existing_ci_gate():
    from scripts.ci_pytest import resolve_gate

    root = Path(__file__).resolve().parents[1]
    gate = resolve_gate(root)
    assert "tests/test_company_dialogue_principal_listener.py" in gate["included"]
