from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from control_plane.remote_worker_transport import (
    TransportValidationError,
    build_request,
)
from ops.executive_os.remote_worker_gateway_config import (
    REMOTE_WORKER_GATEWAY_CONFIG_SCHEMA,
    RemoteWorkerGatewayConfig,
)


OPAQUE_HOST_REF = "host-" + "b" * 64


def _identity(host_ref: str) -> dict[str, str]:
    return {
        "host_ref": host_ref,
        "job_id": "job-1",
        "attempt_id": "attempt-1",
        "worker_id": "worker-1",
        "operation_id": "op-1",
    }


def _file(root: Path, name: str) -> Path:
    path = root / name
    path.write_text("test-material", encoding="utf-8")
    return path


def _gateway_kwargs(tmp_path: Path) -> dict[str, object]:
    return {
        "schema": REMOTE_WORKER_GATEWAY_CONFIG_SCHEMA,
        "listen_host": "127.0.0.1",
        "listen_port": 0,
        "certificate_path": _file(tmp_path, "server.crt"),
        "key_path": _file(tmp_path, "server.key"),
        "ca_path": _file(tmp_path, "ca.crt"),
        "expected_control_fingerprint": "a" * 64,
        "broker_socket_path": tmp_path / "worker.sock",
        "allowed_worker_ids": {"worker-1"},
        "allowed_operations": {"status"},
    }


def test_transport_accepts_owner_supplied_opaque_host_ref() -> None:
    request = build_request(_identity(OPAQUE_HOST_REF), "status", {})
    assert request["host_ref"] == OPAQUE_HOST_REF


def test_transport_refuses_reserved_unbound_host_ref() -> None:
    with pytest.raises(TransportValidationError, match="transport identity is invalid"):
        build_request(_identity("local-unbound"), "status", {})


def test_transport_refuses_host_ref_outside_owner_namespace() -> None:
    invalid_values = (
        "not-a-host-ref",
        "host-capacity-a1b2c3d4",
        "A" * 64,
        "host-" + "B" * 64,
        "host-" + "a" * 63,
        "host-" + "a" * 65,
    )
    for invalid in invalid_values:
        with pytest.raises(TransportValidationError, match="transport identity is invalid"):
            build_request(_identity(invalid), "status", {})


def test_gateway_config_uses_same_opaque_host_ref_contract(tmp_path: Path) -> None:
    kwargs = _gateway_kwargs(tmp_path)
    config = RemoteWorkerGatewayConfig(host_ref=OPAQUE_HOST_REF, **kwargs)
    assert config.host_ref == OPAQUE_HOST_REF

    legacy = RemoteWorkerGatewayConfig(host_ref="a" * 64, **kwargs)
    assert legacy.host_ref == "a" * 64

    invalid_values = (
        "local-unbound",
        "not-a-host-ref",
        "host-capacity-a1b2c3d4",
        "A" * 64,
        "host-" + "B" * 64,
        "host-" + "a" * 63,
        "host-" + "a" * 65,
    )
    for invalid in invalid_values:
        with pytest.raises(ValueError, match="host_ref is invalid"):
            RemoteWorkerGatewayConfig(host_ref=invalid, **kwargs)


def test_gateway_config_does_not_coerce_non_string_host_identity(tmp_path: Path) -> None:
    kwargs: dict[str, Any] = _gateway_kwargs(tmp_path)
    with pytest.raises(ValueError, match="host_ref is invalid"):
        RemoteWorkerGatewayConfig(host_ref=12345678, **kwargs)  # type: ignore[arg-type]
