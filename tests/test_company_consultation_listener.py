"""Company uses the incumbent service lifetime and a dedicated worker-only socket."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

from control_plane import executive_service as service_module
from control_plane.executive_service import (
    CompanyConsultationBinding, ExecutiveControlService, ServiceError,
)
from scripts import executive_os_phase1c as cli
from test_executive_service import _config, _FakeSupervisor, short_socket_root
from test_c1_ceo_ingress_composition import _raw

CANONICAL = "/var/run/mastermind-executive/company-consultation.sock"


def _settings(armed=True):
    return {"armed": armed, "socket_path": CANONICAL, "launchd_socket_name": "CompanyConsultation"}


@pytest.mark.parametrize("value", [None, {}, {"armed": True},
    dict(_settings(), worker_uid=451), dict(_settings(), workspace_id="foreign"),
    dict(_settings(), armed=1), dict(_settings(), socket_path="/tmp/company.sock"),
    dict(_settings(), launchd_socket_name="Operator")])
def test_company_config_refuses_partial_or_caller_selected_binding(value):
    with pytest.raises(ServiceError, match="Company consultation"):
        cli.company_consultation_launchd_entry(
            {"company_consultation": value, "control_uid": 450, "worker_uid": 451, "worker_gid": 451})


@pytest.mark.parametrize("armed", [False, True])
def test_company_plist_projection_is_optional_and_uses_existing_worker_identity(armed):
    raw = dict(company_consultation=_settings(armed), control_uid=450, worker_uid=451, worker_gid=451)
    expected = dict(SockPathName=CANONICAL, SockType="stream", SockPassive=True,
                    SockPathOwner=450, SockPathGroup=451, SockPathMode=0o660)
    assert cli.company_consultation_launchd_entry(raw) == (expected if armed else None)
    assert cli.company_consultation_launchd_entry({}) is None


@pytest.mark.parametrize("armed", [None, False, True])
def test_installed_company_factory_has_one_runtime_and_canonical_relay_scope(tmp_path, monkeypatch, armed):
    from integrations import company_consultation_host
    from ops.executive_os.a2_agent_relay_enrollment import SLACK_WORKSPACE_ID, SLACK_CHANNEL_ID
    raw = _raw(tmp_path)
    raw.update(control_uid=450, worker_uid=451, worker_gid=451)
    if armed is not None:
        raw["company_consultation"] = _settings(armed)
    captured, hosts, activated = {}, [], []
    class Capture:
        def __init__(self, config, **kwargs):
            captured.update(kwargs)
    def activate(name):
        activated.append(name)
        if name == "CompanyConsultation":
            return SimpleNamespace(family=socket.AF_UNIX, getsockname=lambda: CANONICAL, getsockopt=lambda *args: 1)
        return object()
    monkeypatch.setattr(cli, "ExecutiveControlService", Capture)
    monkeypatch.setattr(cli, "activate_launchd_socket", activate)
    monkeypatch.setattr(company_consultation_host, "CompanyConsultationHost",
                        lambda **kwargs: hosts.append(kwargs) or object())
    cli._service_from_config(raw)
    binding = captured["company_consultation_binding"]
    if not armed:
        assert binding is None and hosts == []
        assert "CompanyConsultation" not in activated
    else:
        assert hosts == []  # Runtime is opened only by service startup.
        runtime = object()
        binding.host_factory(runtime)
        assert hosts == [dict(runtime=runtime, repository_root=raw["proof_source_repository"],
                             worker_uid=451, relay_socket_path=cli._CANONICAL_AGENT_RELAY_SOCKET,
                             workspace_id=SLACK_WORKSPACE_ID, channel_id=SLACK_CHANNEL_ID)]
        assert binding.worker_uid == binding.group_gid == 451
        assert activated.count("CompanyConsultation") == 1


class Host:
    def __init__(self, runtime, *, gate=None):
        self.runtime, self.gate = runtime, gate
        self.entered = asyncio.Event()
        self.calls = 0

    async def handle_connection(self, reader, writer):
        self.calls += 1
        assert await reader.readline() == b"company\n"
        self.entered.set()
        if self.gate is not None:
            await self.gate.wait()
        if not writer.is_closing():
            writer.write(b"accepted\n")
            await writer.drain()


def _service(tmp_path, short, *, gate=None, activated=None, grace=0.1):
    captured = []
    def factory(runtime):
        value = Host(runtime, gate=gate)
        captured.append(value)
        return value
    path = short / "company" / "consult.sock"
    binding = CompanyConsultationBinding(
        path, worker_uid=451, group_gid=os.getegid(), host_factory=factory,
        activated_socket=activated)
    config = _config(tmp_path, socket_root=short, shutdown_grace_seconds=grace)
    service = ExecutiveControlService(
        config, supervisor_factory=_FakeSupervisor, company_consultation_binding=binding)
    return service, path, captured


def test_company_listener_binds_before_acceptance_and_uses_current_runtime(tmp_path, short_socket_root, monkeypatch):
    monkeypatch.setattr(service_module, "_peer_uid", lambda connection: 451)
    async def scenario():
        service, path, hosts = _service(tmp_path, short_socket_root)
        assert hosts == []
        await service.start()
        try:
            assert hosts[0].runtime is service.runtime
            assert service._company_consultation_ready
            assert path.stat().st_mode & 0o777 == 0o660
            assert path.parent.stat().st_mode & 0o777 == 0o710
            reader, writer = await asyncio.open_unix_connection(path)
            writer.write(b"company\n"); await writer.drain()
            assert await reader.readline() == b"accepted\n"
            assert await reader.read() == b""
            writer.close(); await writer.wait_closed()
            assert hosts[0].calls == 1
        finally:
            await service.close()
        assert not path.exists() and service._lock_fd is None
        assert not service._company_consultation_tasks
    asyncio.run(scenario())


@pytest.mark.parametrize("peer,ready", [(452, True), (451, False)])
def test_company_listener_refuses_foreign_peer_and_unready_service(tmp_path, short_socket_root, monkeypatch, peer, ready):
    monkeypatch.setattr(service_module, "_peer_uid", lambda connection: peer)
    async def scenario():
        service, path, hosts = _service(tmp_path, short_socket_root)
        await service.start()
        try:
            if not ready:
                service._service_state = "AWAITING_CANARY"
            reader, writer = await asyncio.open_unix_connection(path)
            assert await asyncio.wait_for(reader.read(), timeout=1) == b""
            writer.close(); await writer.wait_closed()
            assert hosts[0].calls == 0
        finally:
            await service.close()
    asyncio.run(scenario())


def test_company_partial_start_closes_all_listeners_and_releases_custody(tmp_path, short_socket_root, monkeypatch):
    async def scenario():
        service, path, hosts = _service(tmp_path, short_socket_root)
        async def fail():
            assert service._company_consultation_server is not None
            assert not service._company_consultation_ready
            raise ServiceError("injected Operator start failure")
        monkeypatch.setattr(service, "_start_operator_serving", fail)
        with pytest.raises(ServiceError, match="injected"):
            await service.start()
        assert service._lock_fd is None
        assert service._server is service._company_consultation_server is None
        assert service._company_consultation_host is None
        assert not path.exists()
    asyncio.run(scenario())


def test_company_shutdown_retains_custody_until_active_handler_drains(tmp_path, short_socket_root, monkeypatch):
    monkeypatch.setattr(service_module, "_peer_uid", lambda connection: 451)
    async def scenario():
        gate = asyncio.Event()
        service, path, hosts = _service(tmp_path, short_socket_root, gate=gate, grace=0.1)
        await service.start()
        reader, writer = await asyncio.open_unix_connection(path)
        writer.write(b"company\n"); await writer.drain()
        await hosts[0].entered.wait()
        try:
            with pytest.raises(ServiceError, match="custody retained"):
                await service.close()
            assert service._lock_fd is not None
            assert not service._company_consultation_ready
            assert service._company_consultation_server is None
            assert service._company_consultation_tasks
            gate.set()
            await asyncio.gather(*service._company_consultation_tasks)
            await service.close()
            assert service._lock_fd is None and not path.exists()
            # The same operation can restart after its real drain.
            await service.start()
            await service.close()
        finally:
            gate.set()
            writer.close(); await writer.wait_closed()
            await service.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("replace_inode", [False, True])
def test_company_never_reclaims_ambiguous_socket_nodes(tmp_path, short_socket_root, replace_inode):
    async def scenario():
        service, path, _ = _service(tmp_path, short_socket_root)
        if replace_inode:
            await service.start()
            path.unlink()
            path.write_text("different inode")
            await service.close()
        else:
            path.parent.mkdir(mode=0o710)
            path.parent.chmod(0o710)
            os.chown(path.parent, os.geteuid(), os.getegid())
            path.write_text("preexisting node")
            with pytest.raises(ServiceError, match="pre-existing"):
                await service.start()
        assert path.is_file()
        assert service._lock_fd is None
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", [0o600, 0o660])
def test_company_activated_socket_requires_exact_dac_and_stays_launchd_owned(tmp_path, short_socket_root, mode):
    async def scenario():
        path = short_socket_root / "company" / "consult.sock"
        path.parent.mkdir()
        activated = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        activated.bind(str(path)); activated.listen()
        path.chmod(mode)
        os.chown(path, os.geteuid(), os.getegid())
        service, _, _ = _service(tmp_path, short_socket_root, activated=activated)
        try:
            if mode != 0o660:
                with pytest.raises(ServiceError, match="permissions"):
                    await service.start()
            else:
                await service.start()
        finally:
            await service.close()
        assert path.exists()  # Only launchd owns removal.
        assert service._lock_fd is None
    asyncio.run(scenario())


@pytest.mark.parametrize("armed", [None, False, True, "invalid"])
def test_installer_projects_company_socket_without_changing_service_owner(tmp_path, armed):
    import json
    import plistlib
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    source = (root / "ops/executive_os/install.sh").read_text()
    start = source.index("# The optional Company socket belongs to this same service")
    embedded = source[start:].split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    raw = dict(control_uid=450, worker_uid=451, worker_gid=451)
    if armed is not None:
        raw["company_consultation"] = _settings(armed)
    config = tmp_path / "control.json"
    config.write_text(json.dumps(raw))
    plist = tmp_path / "control.plist"
    original = dict(Label="com.mastermind.executive.control",
                    UserName="_mastermind_exec", GroupName="_mastermind_exec",
                    Sockets={"Operator": {"fixture": "unchanged"}})
    plist.write_bytes(plistlib.dumps(original))
    before = plist.read_bytes()
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-", str(root), str(config), str(plist)],
        input=embedded, text=True, capture_output=True)
    if armed == "invalid":
        assert result.returncode != 0
        assert plist.read_bytes() == before
        return
    assert result.returncode == 0, result.stderr
    observed = plistlib.loads(plist.read_bytes())
    assert {k: v for k, v in observed.items() if k != "Sockets"} == {
        k: v for k, v in original.items() if k != "Sockets"}
    assert observed["Sockets"]["Operator"] == original["Sockets"]["Operator"]
    assert set(observed["Sockets"]) == ({"Operator", "CompanyConsultation"} if armed else {"Operator"})
    if armed:
        assert observed["Sockets"]["CompanyConsultation"] == {
            "SockPathName": CANONICAL, "SockType": "stream", "SockPassive": True,
            "SockPathOwner": 450, "SockPathGroup": 451, "SockPathMode": 0o660}


@pytest.mark.parametrize("bound", [
    "/private/var/run/mastermind-executive/company-consultation.sock",
    "/var/run/mastermind-executive/company-consultation.sock",
])
def test_company_activation_accepts_only_same_canonical_path(bound, monkeypatch):
    real_resolve = Path.resolve
    def resolve(path, *args, **kwargs):
        value = str(path)
        if value == "/foreign-alias/consult.sock":
            return Path("/private" + CANONICAL)
        if value.startswith("/var/"):
            return Path("/private" + value)
        return real_resolve(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", resolve)
    activated = SimpleNamespace(family=socket.AF_UNIX, getsockname=lambda: bound,
                                getsockopt=lambda *args: 1)
    CompanyConsultationBinding(Path(CANONICAL), 451, 451, lambda runtime: None, activated)
    for different in ("/foreign-alias/consult.sock", "/var/run/other.sock", "/var/run/../run/mastermind-executive/company-consultation.sock"):
        activated.getsockname = lambda: different
        with pytest.raises(ValueError, match="path mismatch"):
            CompanyConsultationBinding(Path(CANONICAL), 451, 451, lambda runtime: None, activated)


@pytest.mark.parametrize("drift", ["mode", "group"])
def test_company_close_preserves_same_inode_after_custody_drift(tmp_path, short_socket_root, monkeypatch, drift):
    async def scenario():
        service, path, _ = _service(tmp_path, short_socket_root)
        await service.start()
        before = path.lstat()
        if drift == "mode":
            path.chmod(0o600)
        else:
            real_lstat = Path.lstat
            def lstat(candidate, *args, **kwargs):
                info = real_lstat(candidate, *args, **kwargs)
                if candidate == path:
                    fields = list(info)
                    fields[5] = info.st_gid + 1
                    return os.stat_result(fields)
                return info
            monkeypatch.setattr(Path, "lstat", lstat)
        await service.close()
        assert path.exists()
        assert path.lstat().st_ino == before.st_ino
        assert service._lock_fd is None
    asyncio.run(scenario())
