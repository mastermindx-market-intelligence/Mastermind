"""MH1 gateway service packaging stays local, bounded and production-inert."""
from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import os
import plistlib
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "ops/executive_os/com.mastermind.executive.remote-worker-gateway.plist.template"
HOST_REF = "host-" + "a" * 64


def _service_module():
    from ops.executive_os import remote_worker_gateway_service as service

    return service


def _write(path: Path, data: str, mode: int) -> None:
    if path.exists() and not path.is_symlink():
        path.chmod(0o640)
    path.write_text(data, encoding="utf-8")
    path.chmod(mode)


def _fixture(tmp_path: Path):
    root = tmp_path / "gateway"
    tls = root / "tls"
    root.mkdir(mode=0o750)
    root.chmod(0o750)
    tls.mkdir(mode=0o750)
    tls.chmod(0o750)
    certificate = tls / "server.crt"
    key = tls / "server.key"
    ca = tls / "ca.crt"
    for path, data in ((certificate, "CERT"), (key, "KEY"), (ca, "CA")):
        _write(path, data, 0o440)
    config_path = root / "gateway.json"
    document = {
        "schema": "mastermind.remote_worker_gateway_config/v1",
        "host_ref": HOST_REF,
        "listen_host": "100.64.0.10",
        "listen_port": 9443,
        "certificate_path": str(certificate),
        "key_path": str(key),
        "ca_path": str(ca),
        "expected_control_fingerprint": "b" * 64,
        "broker_socket_path": "/var/run/mastermind-executive/worker-codex-pro-01.sock",
        "allowed_worker_ids": ["codex-pro-01"],
        "allowed_operations": ["capacity-observe/v1", "status"],
        "request_timeout_seconds": 30.0,
        "max_frame_bytes": 1048576,
    }
    _write(config_path, json.dumps(document, sort_keys=True), 0o440)
    return root, config_path, document


def test_secure_config_loader_returns_existing_gateway_config(tmp_path):
    service = _service_module()
    root, config_path, document = _fixture(tmp_path)

    config = service.load_remote_worker_gateway_config(
        config_path,
        allowed_root=root,
        broker_socket_root=Path("/var/run/mastermind-executive"),
        expected_owner_uid=os.geteuid(),
        expected_group_gid=root.lstat().st_gid,
    )

    assert config.schema == document["schema"]
    assert config.host_ref == HOST_REF
    assert config.listen_host == "100.64.0.10"
    assert config.broker_socket_path == Path(document["broker_socket_path"])
    assert config.allowed_worker_ids == frozenset({"codex-pro-01"})
    assert config.allowed_operations == frozenset({"capacity-observe/v1", "status"})
    assert service.remote_worker_gateway_config_digest(config).isalnum()
    assert len(service.remote_worker_gateway_config_digest(config)) == 64


def _entrypoint_module():
    path = ROOT / "scripts/executive_os_remote_worker_gateway.py"
    spec = importlib.util.spec_from_file_location("mh1_gateway_entrypoint", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(service, root: Path, config_path: Path):
    return service.load_remote_worker_gateway_config(
        config_path,
        allowed_root=root,
        broker_socket_root=Path("/var/run/mastermind-executive"),
        expected_owner_uid=os.geteuid(),
        expected_group_gid=root.lstat().st_gid,
    )


def test_launchd_renderer_is_fixed_and_contains_no_endpoint_or_tls_path(tmp_path):
    service = _service_module()
    root, config_path, _ = _fixture(tmp_path)
    rendered = service.render_remote_worker_gateway_plist(
        TEMPLATE.read_bytes(),
        python_binary=Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"),
        entrypoint=Path("/opt/mastermind/releases/abc/scripts/executive_os_remote_worker_gateway.py"),
        config_path=config_path,
        release_root=Path("/opt/mastermind/releases/abc"),
        control_home=Path("/Library/Application Support/MastermindExecutive/control-home"),
        stdout_path=Path("/var/log/mastermind-executive/mh1/stdout.log"),
        stderr_path=Path("/var/log/mastermind-executive/mh1/stderr.log"),
    )
    value = plistlib.loads(rendered)
    assert value["Label"] == "com.mastermind.executive.remote-worker-gateway"
    assert value["UserName"] == "_mastermind_exec"
    assert value["GroupName"] == "_mastermind_exec"
    assert value["ProgramArguments"] == [
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
        "-I",
        "-S",
        "-B",
        "/opt/mastermind/releases/abc/scripts/executive_os_remote_worker_gateway.py",
        "--config",
        str(config_path),
    ]
    assert value["HardResourceLimits"] == {
        "Core": 0,
        "FileSize": 16777216,
        "NumberOfFiles": 256,
        "NumberOfProcesses": 32,
    }
    assert value["EnvironmentVariables"]["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"
    assert b"100.64.0.10" not in rendered
    assert b"server.key" not in rendered
    assert b"server.crt" not in rendered
    assert b"ca.crt" not in rendered


@pytest.mark.parametrize("operation", [
    "capacity-observe/v0",
    "capacity-observe/v01",
    "capacity//v1",
    "capacity-observe/v1/extra",
    "../v1",
])
def test_operation_allowlist_rejects_arbitrary_path_grammars(tmp_path, operation):
    service = _service_module()
    root, config_path, document = _fixture(tmp_path)
    document["allowed_operations"] = [operation]
    _write(config_path, json.dumps(document, sort_keys=True), 0o440)
    with pytest.raises(service.RemoteWorkerGatewayServiceError):
        _load(service, root, config_path)


@pytest.mark.parametrize("change", ["mode", "link", "symlink", "group", "owner", "directory"])
def test_config_metadata_refuses_unsafe_objects(tmp_path, change):
    service = _service_module()
    root, config_path, _ = _fixture(tmp_path)
    kwargs = {
        "allowed_root": root,
        "broker_socket_root": Path("/var/run/mastermind-executive"),
        "expected_owner_uid": os.geteuid(),
        "expected_group_gid": root.lstat().st_gid,
    }
    target = config_path
    if change == "mode":
        target.chmod(0o640)
    elif change == "link":
        os.link(target, root / "second-link.json")
    elif change == "symlink":
        real = root / "real.json"
        target.rename(real)
        target.symlink_to(real)
    elif change == "group":
        kwargs["expected_group_gid"] = root.lstat().st_gid + 1
    elif change == "owner":
        kwargs["expected_owner_uid"] = os.geteuid() + 1
    elif change == "directory":
        root.chmod(0o770)
    with pytest.raises(service.RemoteWorkerGatewayServiceError):
        service.load_remote_worker_gateway_config(target, **kwargs)


def test_oversized_or_duplicate_key_config_refuses_before_projection(tmp_path):
    service = _service_module()
    root, config_path, document = _fixture(tmp_path)
    config_path.chmod(0o640)
    config_path.write_bytes(b" " * (service.MAX_CONFIG_BYTES + 1))
    config_path.chmod(0o440)
    with pytest.raises(service.RemoteWorkerGatewayServiceError, match="GATEWAY_CONFIG_OVERSIZE"):
        _load(service, root, config_path)
    raw = json.dumps(document, sort_keys=True)
    duplicate = raw[:-1] + ',"schema":"mastermind.remote_worker_gateway_config/v1"}'
    _write(config_path, duplicate, 0o440)
    with pytest.raises(service.RemoteWorkerGatewayServiceError, match="GATEWAY_CONFIG_INVALID"):
        _load(service, root, config_path)


def test_tls_paths_and_broker_socket_cannot_escape_owned_roots(tmp_path):
    service = _service_module()
    root, config_path, document = _fixture(tmp_path)
    outside = tmp_path / "outside.crt"
    _write(outside, "CERT", 0o440)
    document["certificate_path"] = str(outside)
    _write(config_path, json.dumps(document, sort_keys=True), 0o440)
    with pytest.raises(service.RemoteWorkerGatewayServiceError, match="GATEWAY_PATH_ESCAPE"):
        _load(service, root, config_path)

    document["certificate_path"] = str(root / "tls/server.crt")
    document["broker_socket_path"] = "/private/tmp/worker.sock"
    _write(config_path, json.dumps(document, sort_keys=True), 0o440)
    with pytest.raises(service.RemoteWorkerGatewayServiceError, match="GATEWAY_BROKER_SOCKET_INVALID"):
        _load(service, root, config_path)


def test_tls_file_metadata_is_strict(tmp_path):
    service = _service_module()
    root, config_path, document = _fixture(tmp_path)
    key = Path(document["key_path"])
    key.chmod(0o640)
    with pytest.raises(service.RemoteWorkerGatewayServiceError, match="GATEWAY_FILE_INVALID"):
        _load(service, root, config_path)

    key.chmod(0o440)
    original = root / "tls/key-real"
    key.rename(original)
    key.symlink_to(original)
    with pytest.raises(service.RemoteWorkerGatewayServiceError, match="GATEWAY_FILE_INVALID"):
        _load(service, root, config_path)


def test_allowlists_must_be_sorted_unique_nonempty_arrays(tmp_path):
    service = _service_module()
    root, config_path, document = _fixture(tmp_path)
    for field, value in (
        ("allowed_worker_ids", []),
        ("allowed_worker_ids", ["worker-b", "worker-a"]),
        ("allowed_worker_ids", ["worker-a", "worker-a"]),
        ("allowed_operations", "status"),
        ("allowed_operations", ["status", "capacity-observe/v1"]),
    ):
        changed = dict(document)
        changed[field] = value
        _write(config_path, json.dumps(changed, sort_keys=True), 0o440)
        with pytest.raises(service.RemoteWorkerGatewayServiceError):
            _load(service, root, config_path)


def test_service_lifecycle_closes_the_gateway_server(tmp_path):
    service = _service_module()
    root, config_path, _ = _fixture(tmp_path)
    config = _load(service, root, config_path)
    events: list[str] = []

    class Server:
        async def __aenter__(self):
            events.append("enter")
            return self

        async def __aexit__(self, *_args):
            events.append("exit")

        def close(self):
            events.append("close")

        async def wait_closed(self):
            events.append("wait_closed")

    class Gateway:
        def __init__(self, received):
            assert received is config
            events.append("gateway")

        async def start_server(self):
            events.append("start")
            return Server()

    async def shutdown():
        events.append("shutdown")

    asyncio.run(
        service.serve_remote_worker_gateway(
            config,
            gateway_factory=Gateway,
            shutdown_waiter=shutdown,
        )
    )
    assert events == [
        "gateway",
        "start",
        "enter",
        "shutdown",
        "exit",
        "close",
        "wait_closed",
    ]


def test_entrypoint_check_config_is_secret_free_and_does_not_start(tmp_path):
    service = _service_module()
    module = _entrypoint_module()
    root, config_path, _ = _fixture(tmp_path)
    config = _load(service, root, config_path)
    stdout, stderr = io.StringIO(), io.StringIO()
    calls: list[object] = []

    def loader(path, **kwargs):
        calls.append((path, kwargs))
        return config

    def runner(_config):
        raise AssertionError("check mode must not run the service")

    rc = module.main(
        ["--config", str(config_path), "--check-config"],
        loader=loader,
        runner=runner,
        geteuid=lambda: 501,
        getegid=lambda: 450,
        stdout=stdout,
        stderr=stderr,
    )
    assert rc == 0 and stderr.getvalue() == ""
    value = json.loads(stdout.getvalue())
    assert value == {
        "schema": service.SERVICE_CHECK_SCHEMA,
        "ok": True,
        "config_sha256": service.remote_worker_gateway_config_digest(config),
    }
    assert str(config_path) not in stdout.getvalue()
    assert "100.64.0.10" not in stdout.getvalue()
    assert calls == [(config_path, {"expected_owner_uid": 0, "expected_group_gid": 450})]


def test_entrypoint_refuses_root_before_loading_config(tmp_path):
    module = _entrypoint_module()
    stdout, stderr = io.StringIO(), io.StringIO()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("root refusal must precede config acquisition")

    rc = module.main(
        ["--config", str(tmp_path / "missing.json")],
        loader=forbidden,
        runner=forbidden,
        geteuid=lambda: 0,
        getegid=lambda: 0,
        stdout=stdout,
        stderr=stderr,
    )
    assert rc == 77 and stdout.getvalue() == ""
    assert json.loads(stderr.getvalue())["code"] == "ROOT_EXECUTION_REFUSED"


def test_entrypoint_collapses_config_and_service_failures(tmp_path):
    service = _service_module()
    module = _entrypoint_module()
    stdout, stderr = io.StringIO(), io.StringIO()

    def denied(*_args, **_kwargs):
        raise service.RemoteWorkerGatewayServiceError("PRIVATE_CONFIG_PATH")

    rc = module.main(
        ["--config", str(tmp_path / "missing.json")],
        loader=denied,
        geteuid=lambda: 501,
        getegid=lambda: 450,
        stdout=stdout,
        stderr=stderr,
    )
    assert rc == 65
    assert json.loads(stderr.getvalue())["code"] == "CONFIG_REFUSED"
    assert "PRIVATE_CONFIG_PATH" not in stderr.getvalue()

    root, config_path, _ = _fixture(tmp_path)
    config = _load(service, root, config_path)
    stdout, stderr = io.StringIO(), io.StringIO()

    def failed(_config):
        raise RuntimeError("PRIVATE_SOCKET_PATH")
    rc = module.main(
        ["--config", str(config_path)],
        loader=lambda *_args, **_kwargs: config,
        runner=failed,
        geteuid=lambda: 501,
        getegid=lambda: 450,
        stdout=stdout,
        stderr=stderr,
    )
    assert rc == 70
    assert json.loads(stderr.getvalue())["code"] == "SERVICE_FAILED"
    assert "PRIVATE_SOCKET_PATH" not in stderr.getvalue()


def test_config_read_failure_does_not_leak_exception_or_path(tmp_path, monkeypatch):
    service = _service_module()
    root, config_path, _ = _fixture(tmp_path)

    def denied(_descriptor, _length):
        raise OSError("PRIVATE_CONFIG_PATH")

    monkeypatch.setattr(service.os, "read", denied)
    with pytest.raises(service.RemoteWorkerGatewayServiceError) as error:
        _load(service, root, config_path)
    assert error.value.code == "GATEWAY_FILE_INVALID"
    assert "PRIVATE_CONFIG_PATH" not in str(error.value)
    assert str(config_path) not in str(error.value)


def test_installed_service_refuses_ephemeral_listener_port(tmp_path):
    service = _service_module()
    root, config_path, document = _fixture(tmp_path)
    document["listen_port"] = 0
    _write(config_path, json.dumps(document, sort_keys=True), 0o440)
    with pytest.raises(service.RemoteWorkerGatewayServiceError, match="GATEWAY_CONFIG_INVALID"):
        _load(service, root, config_path)
