from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "scripts" / "executive_os_linux_worker.py"
WORKER_SERVICE = ROOT / "ops" / "executive_os" / "mastermind-executive-worker.service.template"
WORKER_SOCKET = ROOT / "ops" / "executive_os" / "mastermind-executive-worker.socket.template"
GATEWAY_SERVICE = ROOT / "ops" / "executive_os" / "mastermind-executive-remote-worker-gateway.service.template"


def _load():
    assert ENTRY.is_file(), "Linux worker entrypoint is not implemented"
    spec = importlib.util.spec_from_file_location("executive_os_linux_worker", ENTRY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _config(tmp_path: Path) -> dict[str, object]:
    return {
        "schema_version": "mastermind.executive_linux_worker_broker_config/v1",
        "control_uid": 450,
        "control_gid": 450,
        "worker_uid": os.geteuid(),
        "worker_gid": os.getegid(),
        "worker_user": "worker-fixture",
        "worker_id": "codex-linux-fixture",
        "workspace_root": str(tmp_path / "workspaces"),
        "run_root": str(tmp_path / "runs"),
        "provider_home": str(tmp_path / "provider-home"),
        "codex_binary": str(tmp_path / "codex"),
        "allowed_codex_versions": ["0.157.1"],
        "socket_path": str(tmp_path / "worker.sock"),
        "uid_sweep_receipt": str(tmp_path / "uid-sweep.json"),
        "operator_harness_armed": False,
    }


def test_source_and_units_exist_and_parse() -> None:
    _load()
    for path in (WORKER_SERVICE, WORKER_SOCKET, GATEWAY_SERVICE):
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        assert "[Unit]" in text
    completed = subprocess.run(
        [sys.executable, "-m", "py_compile", str(ENTRY)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_linux_config_is_closed_and_secret_free(tmp_path: Path) -> None:
    m = _load()
    value = _config(tmp_path)
    path = tmp_path / "worker.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    observed = m.load_linux_worker_config(path, require_root_owner=False)
    assert observed == value

    for forbidden in ("token", "password", "api_key", "credential", "email", "account_id"):
        assert all(forbidden not in key.lower() for key in observed)

    value["provider_token"] = "secret"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(m.LinuxWorkerConfigError, match="fields"):
        m.load_linux_worker_config(path, require_root_owner=False)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("operator_harness_armed", True),
        ("worker_uid", True),
        ("worker_uid", 0),
        ("worker_gid", 0),
        ("control_uid", 0),
        ("control_gid", 0),
        ("allowed_codex_versions", []),
        ("socket_path", "relative.sock"),
    ],
)
def test_linux_config_refuses_authority_or_identity_widening(
    tmp_path: Path, field: str, bad: object
) -> None:
    m = _load()
    value = _config(tmp_path)
    value[field] = bad
    path = tmp_path / "worker.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(m.LinuxWorkerConfigError):
        m.load_linux_worker_config(path, require_root_owner=False)


def test_linux_config_refuses_symlink_and_group_writable(tmp_path: Path) -> None:
    m = _load()
    target = tmp_path / "target.json"
    target.write_text(json.dumps(_config(tmp_path)), encoding="utf-8")
    target.chmod(0o600)
    link = tmp_path / "config.json"
    link.symlink_to(target)
    with pytest.raises(m.LinuxWorkerConfigError):
        m.load_linux_worker_config(link, require_root_owner=False)

    link.unlink()
    target.chmod(0o620)
    with pytest.raises(m.LinuxWorkerConfigError):
        m.load_linux_worker_config(target, require_root_owner=False)


def test_systemd_socket_activation_is_exact_and_no_fallback(tmp_path: Path) -> None:
    m = _load()
    path = tmp_path / "worker.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(1)
    try:
        activated = m.activate_systemd_socket(
            path,
            expected_owner_uid=os.geteuid(),
            expected_group_gid=os.getegid(),
            expected_mode=stat.S_IMODE(path.lstat().st_mode),
            env={"LISTEN_PID": str(os.getpid()), "LISTEN_FDS": "1", "LISTEN_FDNAMES": "worker"},
            fd=listener.fileno(),
            duplicate_fd=True,
        )
        try:
            assert activated.fileno() != listener.fileno()
            assert activated.getsockname() == listener.getsockname()
        finally:
            activated.close()
        with pytest.raises(m.LinuxWorkerConfigError):
            m.activate_systemd_socket(
                path,
                expected_owner_uid=os.geteuid(),
                expected_group_gid=os.getegid(),
                expected_mode=stat.S_IMODE(path.lstat().st_mode),
                env={},
                fd=listener.fileno(),
                duplicate_fd=True,
            )
    finally:
        listener.close()


def test_worker_builder_reuses_broker_and_linux_attestation(monkeypatch, tmp_path: Path) -> None:
    m = _load()
    value = _config(tmp_path)
    for key in ("workspace_root", "run_root", "provider_home"):
        Path(str(value[key])).mkdir(parents=True)
    binary = Path(str(value["codex_binary"]))
    binary.write_bytes(b"ELF")
    binary.chmod(0o755)

    from control_plane.worker_execution_contract import BinaryAttestation

    calls: list[tuple[Path, frozenset[str], object]] = []

    def fake_attest(path, *, allowed_versions, required_team_identifier):
        path = Path(path)
        calls.append((path, allowed_versions, required_team_identifier))
        info = path.stat()
        return BinaryAttestation(
            path=str(path), real_path=str(path.resolve()), version="0.157.1",
            sha256="a" * 64, team_identifier=None, size=info.st_size,
            device=info.st_dev, inode=info.st_ino, mode=0o755, uid=0, gid=0,
            mtime_ns=info.st_mtime_ns,
        )

    monkeypatch.setattr(m, "attest_codex_binary", fake_attest)
    monkeypatch.setattr(m.os, "geteuid", lambda: int(value["worker_uid"]))
    monkeypatch.setattr(m.os, "getegid", lambda: int(value["worker_gid"]))
    monkeypatch.setattr(m.os, "getgroups", lambda: [int(value["worker_gid"])])

    broker = m.build_linux_worker_broker(value)
    assert broker.policy.worker_id == value["worker_id"]
    assert broker.policy.allowed_supplementary_gids == frozenset()
    assert broker.sweeper.ambient_classifier.__class__.__name__ == "NullAmbientClassifier"
    assert calls == [(binary, frozenset({"0.157.1"}), None)]


def test_systemd_units_preserve_principal_socket_and_inert_install_boundary() -> None:
    worker = WORKER_SERVICE.read_text(encoding="utf-8")
    sock = WORKER_SOCKET.read_text(encoding="utf-8")
    gateway = GATEWAY_SERVICE.read_text(encoding="utf-8")

    assert "Requires=__WORKER_SOCKET_UNIT__" in worker
    assert "User=__WORKER_USER__" in worker
    assert "Group=__WORKER_GROUP__" in worker
    assert "ExecStart=__PYTHON_BINARY__ -I -S -B __WORKER_ENTRYPOINT__ serve --config __WORKER_CONFIG__" in worker
    assert "NoNewPrivileges=true" in worker
    assert "ProtectSystem=strict" in worker
    assert "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" in worker
    assert "HOME=__PROVIDER_HOME__" in worker
    assert "sudo" not in worker.lower()

    assert "ListenStream=__WORKER_SOCKET__" in sock
    assert "SocketUser=__CONTROL_USER__" in sock
    assert "SocketGroup=__CONTROL_GROUP__" in sock
    assert "SocketMode=0600" in sock
    assert "RemoveOnStop=true" in sock
    assert "Service=__WORKER_SERVICE_UNIT__" in sock

    assert "User=__CONTROL_USER__" in gateway
    assert "Group=__CONTROL_GROUP__" in gateway
    assert "__GATEWAY_ENTRYPOINT__ --config __GATEWAY_CONFIG__" in gateway
    assert "NoNewPrivileges=true" in gateway
    assert "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" in gateway

    # Source package can be installed without silently arming either service.
    for text in (worker, sock, gateway):
        assert "WantedBy=multi-user.target" not in text
        assert "WantedBy=sockets.target" not in text
        assert "systemctl enable" not in text
        assert "systemctl start" not in text


def test_linux_entrypoint_has_no_scheduler_registry_or_provider_login_plane() -> None:
    text = ENTRY.read_text(encoding="utf-8")
    for forbidden in (
        "RuntimeStore",
        "sqlite3",
        "codex login",
        "claude auth",
        "device-auth",
        "retry",
        "failover",
        "provider_token",
        "api_key",
        "requests.",
        "urllib",
    ):
        assert forbidden not in text
    assert "mode 0440" in text
    assert "ExecutiveWorkerBroker" in text
    assert "DedicatedUIDSweeper" in text
    assert "NullAmbientClassifier" in text
