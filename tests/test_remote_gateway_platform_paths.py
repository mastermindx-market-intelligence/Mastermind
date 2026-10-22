"""The deployed gateway entrypoint uses the installer's platform namespaces."""
import io
import json
from pathlib import Path

import pytest

from ops.executive_os import remote_worker_gateway_service as service
from test_remote_worker_gateway_service import _entrypoint_module


def document(root, socket):
    return dict(
        schema="mastermind.remote_worker_gateway_config/v1",
        host_ref="host-" + "a" * 64, listen_host="100.64.0.10", listen_port=9443,
        certificate_path=str(root / "tls/server.crt"),
        key_path=str(root / "tls/server.key"), ca_path=str(root / "tls/ca.crt"),
        expected_control_fingerprint="b" * 64, broker_socket_path=str(socket),
        allowed_worker_ids=["codex-01"], allowed_operations=["status"],
        request_timeout_seconds=30.0, max_frame_bytes=1048576,
    )


@pytest.mark.parametrize("platform,root,socket", [
    ("linux", "/etc/mastermind-executive", "/run/mastermind-executive-worker-codex-01.sock"),
    ("darwin", "/Library/Application Support/MastermindExecutive/remote-worker-gateway",
     "/var/run/mastermind-executive/worker-codex-01.sock"),
])
def test_actual_entrypoint_uses_installer_namespace(monkeypatch, platform, root, socket):
    root, socket = Path(root), Path(socket)
    config_path = root / "remote-worker-gateway.json"
    raw = json.dumps(document(root, socket)).encode()
    reads, runs = [], []

    def metadata_fixture(path, **kwargs):
        reads.append((path, kwargs))
        return raw if kwargs["read_bytes"] else b""

    monkeypatch.setattr(service.sys, "platform", platform)
    monkeypatch.setattr(service, "_secure_regular_file", metadata_fixture)
    monkeypatch.setattr(Path, "is_file", lambda path: path in {
        root / "tls/server.crt", root / "tls/server.key", root / "tls/ca.crt"})
    stderr = io.StringIO()
    rc = _entrypoint_module().main(
        ["--config", str(config_path)], loader=service.load_remote_worker_gateway_config,
        runner=runs.append, geteuid=lambda: 450, getegid=lambda: 450,
        stdout=io.StringIO(), stderr=stderr)
    assert rc == 0, stderr.getvalue()
    assert len(runs) == 1 and runs[0].broker_socket_path == socket
    assert len(reads) == 4
    assert all(item[1]["root"] == root and item[1]["expected_owner_uid"] == 0
               and item[1]["expected_group_gid"] == 450 for item in reads)


@pytest.mark.parametrize("platform,path", [
    ("linux", "/Library/Application Support/MastermindExecutive/remote-worker-gateway/gateway.json"),
    ("darwin", "/etc/mastermind-executive/remote-worker-gateway.json"),
])
def test_cross_platform_config_is_not_a_fallback(monkeypatch, platform, path):
    reads = []
    monkeypatch.setattr(service.sys, "platform", platform)
    monkeypatch.setattr(service, "_secure_regular_file", lambda *a, **k: reads.append(a))
    with pytest.raises(service.RemoteWorkerGatewayServiceError, match="GATEWAY_PATH_ESCAPE"):
        service.load_remote_worker_gateway_config(path, expected_group_gid=450)
    assert reads == []


@pytest.mark.parametrize('socket,accepted', [
    ('/private/var/run/mastermind-executive/fabric.sock', True),
    ('/var/run/mastermind-executive/fabric.sock', False),
])
def test_darwin_fabric_requires_canonical_namespace_without_relaxing_symlink_guard(monkeypatch, socket, accepted):
    root = Path('/Library/Application Support/MastermindExecutive/remote-worker-gateway')
    raw = document(root, Path(socket))
    raw.update(broker_target='attended-fabric', expected_broker_peer_uid=451)
    monkeypatch.setattr(service.sys, 'platform', 'darwin')
    monkeypatch.setattr(service, '_secure_regular_file',
                        lambda path, **kw: json.dumps(raw).encode() if kw['read_bytes'] else b'')
    monkeypatch.setattr(Path, 'is_file', lambda path: True)
    if accepted:
        result = service.load_remote_worker_gateway_config(root/'config.json', expected_group_gid=450)
        assert result.broker_socket_path == Path(socket)
    else:
        with pytest.raises(service.RemoteWorkerGatewayServiceError, match='GATEWAY_BROKER_SOCKET_INVALID'):
            service.load_remote_worker_gateway_config(root/'config.json', expected_group_gid=450)
