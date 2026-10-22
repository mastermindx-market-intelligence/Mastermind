"""Hermetic attended-Fabric target discrimination tests for the remote gateway.

These tests stub only the filesystem metadata and the transport objects.  No
provider, network service, or real host endpoint is ever contacted.
"""
from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path

import pytest

from ops.executive_os import remote_worker_gateway as gateway_module
from ops.executive_os import remote_worker_gateway_config as config_module
from ops.executive_os import remote_worker_gateway_service as service
from ops.executive_os.remote_worker_gateway import RemoteWorkerGateway
from ops.executive_os.remote_worker_gateway_config import (
    FABRIC_ALLOWED_OPERATIONS,
    FABRIC_BROKER_TARGET,
    REMOTE_WORKER_GATEWAY_CONFIG_SCHEMA,
    RemoteWorkerGatewayConfig,
)
from tests.test_remote_worker_gateway_service import (
    HOST_REF,
    _config_with_live_broker_socket,
    _fixture as _service_fixture,
    _write,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def control_uid(monkeypatch: pytest.MonkeyPatch) -> int:
    """Pin the Executive Control uid so peer-uid distinctness is deterministic."""

    monkeypatch.setattr(config_module, "CONTROL_UID", 501)
    return 501


FABRIC_SOCKET = Path("/var/run/mastermind-executive/fabric-worker.sock")


def _config(tmp_path: Path, **overrides: object) -> RemoteWorkerGatewayConfig:
    for name in ("server.pem", "server.key", "ca.pem"):
        (tmp_path / name).write_text("placeholder", encoding="utf-8")
    values: dict[str, object] = {
        "schema": REMOTE_WORKER_GATEWAY_CONFIG_SCHEMA,
        "host_ref": HOST_REF,
        "listen_host": "127.0.0.1",
        "listen_port": 9443,
        "certificate_path": tmp_path / "server.pem",
        "key_path": tmp_path / "server.key",
        "ca_path": tmp_path / "ca.pem",
        "expected_control_fingerprint": "a" * 64,
        "broker_socket_path": tmp_path / "broker.sock",
        "allowed_worker_ids": {"WORKER-001"},
        "allowed_operations": {"status"},
    }
    values.update(overrides)
    return RemoteWorkerGatewayConfig(**values)


class _StubClientFactory:
    """Record WorkerBrokerClient construction without any transport I/O."""

    def __init__(self) -> None:
        self.construction: list[dict] = []

    def __call__(self, socket_path, *, timeout_seconds=30.0, **kwargs):
        self.construction.append(
            {"socket_path": socket_path, "timeout_seconds": timeout_seconds, **kwargs}
        )
        return self


def _no_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        RemoteWorkerGateway, "_build_server_ssl_context", lambda self: None
    )


def _stat(mode: int, *, uid: int = 0, nlink: int = 1, ino: int = 1) -> os.stat_result:
    return os.stat_result((mode, ino, 7, nlink, uid, 0, 1, 0, 0, 0))


def _dir(mode: int = 0o755, *, uid: int = 0) -> os.stat_result:
    return _stat(stat.S_IFDIR | mode, uid=uid)


def _sock(
    mode: int = 0o600,
    *,
    uid: int = 0,
    ino: int = 42,
    nlink: int = 1,
    fmt: int = stat.S_IFSOCK,
) -> os.stat_result:
    return _stat(fmt | mode, uid=uid, ino=ino, nlink=nlink)


def _install_lstat(monkeypatch: pytest.MonkeyPatch, socket_answer, *, parent_overrides=None):
    """Stub service._lstat with per-path answers; lists pop sequentially."""

    answers = dict(parent_overrides or {})
    if not isinstance(socket_answer, list):
        socket_answer = [socket_answer]

    def lstat(path: Path) -> os.stat_result:
        key = os.fspath(path)
        if key == os.fspath(FABRIC_SOCKET):
            if len(socket_answer) > 1:
                return socket_answer.pop(0)
            answer = socket_answer[0]
            if isinstance(answer, Exception):
                raise answer
            return answer
        if key in answers:
            answer = answers[key]
            if isinstance(answer, Exception):
                raise answer
            return answer
        return _dir()

    monkeypatch.setattr(service, "_lstat", lstat)
    return lstat


def _load_with(tmp_path: Path, **extra: object):
    root, config_path, document = _service_fixture(tmp_path)
    document.update(extra)
    _write(config_path, json.dumps(document, sort_keys=True), 0o440)
    config = service.load_remote_worker_gateway_config(
        config_path,
        allowed_root=root,
        broker_socket_root=Path("/var/run/mastermind-executive"),
        expected_owner_uid=os.geteuid(),
        expected_group_gid=root.lstat().st_gid,
    )
    return document, config


# --- config contract -------------------------------------------------------


def test_default_target_keeps_worker_broker_and_refuses_peer_uid(tmp_path: Path) -> None:
    config = _config(tmp_path)
    assert config.broker_target == "worker-broker"
    assert config.expected_broker_peer_uid is None
    values = {
        field.name: getattr(config, field.name)
        for field in config.__dataclass_fields__.values()
    }
    values["expected_broker_peer_uid"] = 502
    with pytest.raises(ValueError, match="requires the Fabric target"):
        RemoteWorkerGatewayConfig(**values)


def test_actual_control_principal_is_never_a_fabric_worker(tmp_path: Path) -> None:
    from ops.executive_os.capacity_broker_topology import CONTROL_UID
    with pytest.raises(ValueError, match="Control uid"):
        _config(tmp_path, broker_target=FABRIC_BROKER_TARGET,
                expected_broker_peer_uid=CONTROL_UID)


def test_fabric_target_requires_positive_distinct_integer_uid(
    tmp_path: Path, control_uid: int
) -> None:
    for bad in (None, 0, -1, True, "502", 502.0):
        with pytest.raises(ValueError, match="peer uid"):
            _config(
                tmp_path,
                broker_target=FABRIC_BROKER_TARGET,
                expected_broker_peer_uid=bad,
            )
    config = _config(
        tmp_path,
        broker_target=FABRIC_BROKER_TARGET,
        expected_broker_peer_uid=502,
    )
    assert config.broker_target == FABRIC_BROKER_TARGET
    assert config.expected_broker_peer_uid == 502
    with pytest.raises(ValueError, match="Control uid"):
        _config(
            tmp_path,
            broker_target=FABRIC_BROKER_TARGET,
            expected_broker_peer_uid=control_uid,
        )


def test_fabric_target_refuses_unknown_or_bool_target(tmp_path: Path) -> None:
    for bad in ("fabric", "attended", "worker-broker-fabric", True):
        with pytest.raises(ValueError, match="broker target"):
            _config(
                tmp_path,
                broker_target=bad,
                expected_broker_peer_uid=502,
            )


def test_fabric_target_refuses_unqualified_assignment_control_binding(
    tmp_path: Path, control_uid: int
) -> None:
    with pytest.raises(ValueError, match="Control binding differs"):
        _config(
            tmp_path,
            broker_target=FABRIC_BROKER_TARGET,
            expected_broker_peer_uid=502,
            assignment_control=object(),
        )


def _assignment_binding(tmp_path: Path, *, control_uid: int = 501, worker_uid: int = 502):
    from ops.executive_os.remote_assignment_control import AssignmentControlBinding
    return AssignmentControlBinding("WORKER-001", control_uid, 551, worker_uid, 552,
                                    tmp_path / "workspace", tmp_path / "runs")


def test_fabric_seal_requires_bound_control_and_original_worker(
    tmp_path: Path, control_uid: int
) -> None:
    values = dict(broker_target=FABRIC_BROKER_TARGET,
                  expected_broker_peer_uid=502,
                  allowed_operations={"assignment-seal", "assignment-seal-finalize"})
    with pytest.raises(ValueError, match="explicit Control binding"):
        _config(tmp_path, **values)
    config = _config(tmp_path, **values, assignment_control=_assignment_binding(tmp_path))
    assert config.allowed_operations <= FABRIC_ALLOWED_OPERATIONS
    for binding in (_assignment_binding(tmp_path, worker_uid=503),
                    _assignment_binding(tmp_path, control_uid=500)):
        with pytest.raises(ValueError, match="Control binding differs"):
            _config(tmp_path, **values, assignment_control=binding)


def test_default_seal_still_requires_control_binding(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit Control binding"):
        _config(tmp_path, allowed_operations={"assignment-seal"})


def test_fabric_operation_allowlist_is_closed_subset(
    tmp_path: Path, control_uid: int
) -> None:
    with pytest.raises(ValueError):
        _config(
            tmp_path,
            broker_target=FABRIC_BROKER_TARGET,
            expected_broker_peer_uid=502,
            allowed_operations={"status", "capacity-observe/v1"},
        )


# --- canonical digest compatibility ---------------------------------------


def test_default_canonical_config_stays_byte_identical(tmp_path: Path) -> None:
    _, config = _load_with(tmp_path)
    canonical = json.loads(service._canonical_config(config))
    assert "broker_target" not in canonical
    assert "expected_broker_peer_uid" not in canonical
    assert set(canonical) == set(service.CONFIG_FIELDS)
    digest = service.remote_worker_gateway_config_digest(config)
    assert len(digest) == 64 and digest.isalnum()


def test_fabric_canonical_config_adds_only_target_fields(
    tmp_path: Path, control_uid: int
) -> None:
    _, config = _load_with(
        tmp_path,
        broker_target="attended-fabric",
        expected_broker_peer_uid=502,
        allowed_operations=["status"],
    )
    canonical = json.loads(service._canonical_config(config))
    assert canonical["broker_target"] == FABRIC_BROKER_TARGET
    assert canonical["expected_broker_peer_uid"] == 502
    assert set(canonical) - {"broker_target", "expected_broker_peer_uid"} == set(
        service.CONFIG_FIELDS
    )


# --- loader pairing and refusals ------------------------------------------


def test_loader_default_target_loads_without_new_fields(
    tmp_path: Path, control_uid: int
) -> None:
    document, config = _load_with(tmp_path)
    assert "broker_target" not in document
    assert config.broker_target == "worker-broker"
    assert config.expected_broker_peer_uid is None


def test_loader_accepts_paired_fabric_fields(tmp_path: Path, control_uid: int) -> None:
    _, config = _load_with(
        tmp_path,
        broker_target="attended-fabric",
        expected_broker_peer_uid=502,
        allowed_operations=["collect", "status"],
    )
    assert config.broker_target == FABRIC_BROKER_TARGET
    assert config.expected_broker_peer_uid == 502


@pytest.mark.parametrize(
    "extra",
    [
        {"broker_target": "attended-fabric"},
        {"expected_broker_peer_uid": 502},
        {"broker_target": "attended-fabric", "expected_broker_peer_uid": True},
        {"broker_target": "attended-fabric", "expected_broker_peer_uid": 0},
        {"broker_target": "attended-fabric", "expected_broker_peer_uid": "502"},
        {
            "broker_target": "attended-fabric",
            "expected_broker_peer_uid": 502,
            "unknown_key": 1,
        },
        {
            "broker_target": "attended-fabric",
            "expected_broker_peer_uid": 502,
            "assignment_control": {"worker_id": "codex-pro-01"},
        },
    ],
)
def test_loader_refuses_unpaired_or_malformed_fabric_fields(
    tmp_path: Path, control_uid: int, extra: dict
) -> None:
    with pytest.raises(
        service.RemoteWorkerGatewayServiceError, match="GATEWAY_CONFIG_INVALID"
    ):
        _load_with(tmp_path, **extra)


# --- dispatch: intercept vs forward ---------------------------------------


async def test_fabric_assignment_seal_uses_configured_control_not_forward_fallback(
    tmp_path: Path, control_uid: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = _StubClientFactory()
    monkeypatch.setattr(gateway_module, "WorkerBrokerClient", factory)
    _no_tls(monkeypatch)
    binding = _assignment_binding(tmp_path)
    sealed = []

    async def _seal(control, request, broker_call, *, fabric_target):
        sealed.append((control, request, broker_call, fabric_target))
        return {"sealed": True}

    monkeypatch.setattr(gateway_module, "seal_original_assignment", _seal)
    gateway = RemoteWorkerGateway(_config(tmp_path,
        broker_target=FABRIC_BROKER_TARGET, expected_broker_peer_uid=502,
        allowed_operations={"assignment-seal"}, assignment_control=binding))

    async def forbidden(*args, **kwargs):
        raise AssertionError("assignment seal must not fall back to forwarding")

    gateway.broker_call = forbidden
    request = {"broker_operation": "assignment-seal", "broker_request": {}}
    assert await gateway._dispatch_authenticated(request) == {"sealed": True}
    assert sealed == [(binding, request, gateway.broker_call, True)]
    assert factory.construction[0]["expected_peer_uid"] == 502
    assert factory.construction[0]["socket_path"] == gateway.config.broker_socket_path


async def test_default_assignment_seal_still_intercepts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = _StubClientFactory()
    monkeypatch.setattr(gateway_module, "WorkerBrokerClient", factory)
    _no_tls(monkeypatch)
    binding = object()
    sealed: list[tuple[object, object, object]] = []

    async def _seal(control: object, request: object, broker_call: object) -> dict:
        sealed.append((control, request, broker_call))
        return {"sealed": True}

    monkeypatch.setattr(gateway_module, "seal_original_assignment", _seal)
    # Stub the sealed default shape directly: a default config cannot be born
    # with assignment-seal and no binding, so project both after construction.
    config = _config(tmp_path)
    object.__setattr__(config, "assignment_control", binding)
    object.__setattr__(config, "allowed_operations", frozenset({"assignment-seal"}))
    gateway = RemoteWorkerGateway(config)

    async def forbidden(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("default target must intercept assignment-seal")

    gateway.broker_call = forbidden
    request = {"broker_operation": "assignment-seal", "broker_request": {}}
    assert await gateway._dispatch_authenticated(request) == {"sealed": True}
    assert sealed[0][0] is binding
    assert sealed[0][2] is gateway.broker_call
    # The default target pins no broker peer uid at all.
    assert factory.construction[0] == {
        "socket_path": config.broker_socket_path,
        "timeout_seconds": config.request_timeout_seconds,
    }


# --- service startup -------------------------------------------------------


class _Server:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def __aenter__(self) -> "_Server":
        self._events.append("enter")
        return self

    async def __aexit__(self, *_args: object) -> None:
        self._events.append("exit")

    def close(self) -> None:
        self._events.append("close")

    async def wait_closed(self) -> None:
        self._events.append("wait_closed")


def test_fabric_service_start_exposes_listener_without_status_probe(
    tmp_path: Path, control_uid: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    probes: list[tuple[str, object]] = []

    class Gateway:
        def __init__(self, received: RemoteWorkerGatewayConfig) -> None:
            assert received.broker_target == FABRIC_BROKER_TARGET
            events.append("gateway")

        async def broker_call(self, operation: str, payload: object) -> dict:
            probes.append((operation, payload))
            raise AssertionError("Fabric startup must not probe the broker")

        async def start_server(self) -> _Server:
            events.append("start")
            return _Server(events)

    async def shutdown() -> None:
        events.append("shutdown")

    _install_lstat(monkeypatch, _sock())
    config = _config(
        tmp_path,
        broker_socket_path=FABRIC_SOCKET,
        broker_target=FABRIC_BROKER_TARGET,
        expected_broker_peer_uid=502,
    )
    asyncio.run(
        service.serve_remote_worker_gateway(
            config, gateway_factory=Gateway, shutdown_waiter=shutdown
        )
    )
    assert probes == []
    assert events == [
        "gateway",
        "start",
        "enter",
        "shutdown",
        "exit",
        "close",
        "wait_closed",
    ]


def test_fabric_service_start_refuses_when_endpoint_identity_changes(
    tmp_path: Path, control_uid: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_lstat(monkeypatch, [_sock(ino=1), _sock(ino=2)])
    config = _config(
        tmp_path,
        broker_socket_path=FABRIC_SOCKET,
        broker_target=FABRIC_BROKER_TARGET,
        expected_broker_peer_uid=502,
    )
    started: list[bool] = []

    class Gateway:
        def __init__(self, _config: RemoteWorkerGatewayConfig) -> None:
            pass

        async def start_server(self) -> object:
            started.append(True)
            raise AssertionError("listener must not start")

    async def shutdown() -> None:
        raise AssertionError("shutdown wait must not start")

    with pytest.raises(
        service.RemoteWorkerGatewayServiceError, match="GATEWAY_BROKER_SOCKET_INVALID"
    ):
        asyncio.run(
            service.serve_remote_worker_gateway(
                config, gateway_factory=Gateway, shutdown_waiter=shutdown
            )
        )
    assert started == []


@pytest.mark.parametrize(
    "socket_answer,parent_overrides",
    [
        pytest.param(
            # A missing node surfaces as the mapped lstat refusal, because the
            # stub replaces the real _lstat OSError mapping wholesale.
            service.RemoteWorkerGatewayServiceError("GATEWAY_BROKER_SOCKET_INVALID"),
            {},
            id="missing",
        ),
        pytest.param(_sock(fmt=stat.S_IFREG), {}, id="regular-file"),
        pytest.param(_stat(stat.S_IFLNK | 0o777), {}, id="socket-symlink"),
        pytest.param(_sock(uid=501), {}, id="socket-wrong-owner"),
        pytest.param(_sock(mode=0o606), {}, id="socket-world-perms"),
        pytest.param(_sock(nlink=2), {}, id="socket-linked-twice"),
        pytest.param(_sock(), {"/var": _dir(uid=501)}, id="parent-not-root-owned"),
        pytest.param(_sock(), {"/var/run": _dir(0o775)}, id="parent-group-writable"),
        pytest.param(
            _sock(),
            {"/var/run/mastermind-executive": _stat(stat.S_IFLNK | 0o755)},
            id="parent-symlink",
        ),
    ],
)
def test_fabric_service_start_refuses_unsafe_endpoint_metadata(
    tmp_path: Path,
    control_uid: int,
    monkeypatch: pytest.MonkeyPatch,
    socket_answer: object,
    parent_overrides: dict,
) -> None:
    config = _config(
        tmp_path,
        broker_socket_path=FABRIC_SOCKET,
        broker_target=FABRIC_BROKER_TARGET,
        expected_broker_peer_uid=502,
    )
    constructed: list[bool] = []

    class ForbiddenGateway:
        def __init__(self, _config: RemoteWorkerGatewayConfig) -> None:
            constructed.append(True)

        async def start_server(self) -> object:
            raise AssertionError("listener must not start")

    async def shutdown() -> None:
        raise AssertionError("shutdown wait must not start")

    with pytest.raises(
        service.RemoteWorkerGatewayServiceError, match="GATEWAY_BROKER_SOCKET_INVALID"
    ):
        asyncio.run(
            service.serve_remote_worker_gateway(
                config,
                gateway_factory=ForbiddenGateway,
                shutdown_waiter=shutdown,
            )
        )
    assert constructed == []


def test_default_service_start_still_probes_status(tmp_path: Path) -> None:
    config, broker = _config_with_live_broker_socket(service, tmp_path)
    events: list[str] = []

    class Gateway:
        def __init__(self, received: RemoteWorkerGatewayConfig) -> None:
            assert received is config
            events.append("gateway")

        async def broker_call(self, operation: str, payload: dict) -> dict:
            assert operation == "status"
            assert payload == {}
            events.append("probe")
            return {"broker_pid": 123}

        async def start_server(self) -> _Server:
            events.append("start")
            return _Server(events)

    async def shutdown() -> None:
        events.append("shutdown")

    try:
        asyncio.run(
            service.serve_remote_worker_gateway(
                config, gateway_factory=Gateway, shutdown_waiter=shutdown
            )
        )
    finally:
        broker.close()
    assert events == [
        "gateway",
        "probe",
        "start",
        "enter",
        "shutdown",
        "exit",
        "close",
        "wait_closed",
    ]
