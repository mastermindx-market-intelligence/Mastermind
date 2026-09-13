"""Owning tests for the concrete Workbench Read loopback service process."""
from __future__ import annotations

import dataclasses
import socket

import pytest

from integrations.workbench_read_mcp.app import ReadCaller
from integrations.workbench_read_mcp.observer import ReadScope
from integrations.workbench_read_mcp.read_port import ProjectReadBinding
from integrations.workbench_read_mcp.runtime import StableWorkbenchLease
from integrations.workbench_read_mcp import service


HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
HEX_D = "d" * 64


def lease_document() -> dict[str, object]:
    return {
        "expected_subject_digest": HEX_A,
        "expected_client_ref": HEX_B,
        "resource": "https://read.example.test/mcp",
        "required_scopes": ["workbench.read"],
        "project_ref": "project:" + HEX_A,
        "context_ref": "context:" + HEX_B,
        "owner_ref": "owner:" + HEX_C,
        "generation": "generation:" + HEX_D,
        "allowed_paths": ["README.md", "docs/guide.md"],
        "committed_head": "1" * 40,
        "lease_expires_at_ms": 2_000_000,
    }


def document() -> dict[str, object]:
    return {
        "schema": service.SERVICE_SCHEMA,
        "policy_file": "/tmp/workbench-policy.json",
        "project_root": "/tmp/workbench-project",
        "audit_directory": "/tmp/workbench-audit",
        "bind_host": "127.0.0.1",
        "bind_port": 48765,
        "incoming_authority": "read.example.test:443",
        "max_concurrency": 4,
        "io_timeout_seconds": 5.0,
        "close_timeout_seconds": 7.0,
        "lease": lease_document(),
    }


def test_service_config_is_closed_and_constructs_exact_stable_lease() -> None:
    selected = service.parse_service_config(document())
    assert selected.schema == service.SERVICE_SCHEMA
    assert selected.bind_host == "127.0.0.1"
    assert selected.bind_port == 48765
    assert selected.incoming_authority == "read.example.test:443"
    assert selected.max_concurrency == 4
    assert selected.allowed_hosts == ("read.example.test:443",)
    assert selected.allowed_origins == ()
    assert selected.lease == StableWorkbenchLease(
        expected_subject_digest=HEX_A,
        expected_client_ref=HEX_B,
        resource="https://read.example.test/mcp",
        required_scopes=("workbench.read",),
        project_ref="project:" + HEX_A,
        context_ref="context:" + HEX_B,
        owner_ref="owner:" + HEX_C,
        generation="generation:" + HEX_D,
        allowed_paths=("README.md", "docs/guide.md"),
        committed_head="1" * 40,
        lease_expires_at_ms=2_000_000,
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(extra="forbidden"),
        lambda value: value.update(bind_host="0.0.0.0"),
        lambda value: value.update(bind_port=0),
        lambda value: value.update(bind_port=True),
        lambda value: value.update(incoming_authority="read.example.test"),
        lambda value: value.update(incoming_authority="bad..host:443"),
        lambda value: value.update(incoming_authority="http://read.example.test:443"),
        lambda value: value.update(io_timeout_seconds=float("nan")),
        lambda value: value.update(close_timeout_seconds=61),
        lambda value: value.update(max_concurrency=33),
        lambda value: value["lease"].update(extra="forbidden"),
        lambda value: value["lease"].update(required_scopes=["workbench.read", "other"]),
        lambda value: value["lease"].update(allowed_paths=["README.md", "README.md"]),
    ],
)
def test_service_config_refuses_authority_widening(mutation) -> None:
    value = document()
    mutation(value)
    with pytest.raises(service.ServiceConfigurationError, match="^SERVICE_CONFIGURATION_REFUSED$"):
        service.parse_service_config(value)


def test_reserved_socket_is_exact_loopback_noninheritable_and_occupied_port_refuses() -> None:
    selected = dataclasses.replace(service.parse_service_config(document()), bind_port=0)
    # Port zero is forbidden by the wire, but this lower-level helper accepts an
    # explicitly test-owned ephemeral port only when asked through its test seam.
    sock = service.reserve_loopback_socket(selected, _allow_ephemeral_for_test=True)
    try:
        assert sock.family == socket.AF_INET
        assert sock.getsockname()[0] == "127.0.0.1"
        assert sock.getsockname()[1] > 0
        assert not sock.get_inheritable()
        occupied = dataclasses.replace(selected, bind_port=sock.getsockname()[1])
        with pytest.raises(service.ServiceConfigurationError, match="^SERVICE_BIND_REFUSED$"):
            service.reserve_loopback_socket(occupied)
    finally:
        sock.close()


class _RuntimeProbe:
    def __init__(self, selected: service.ServiceConfig) -> None:
        self.selected = selected
        self.calls: list[tuple[ReadCaller, str]] = []
        self.revoked = False

    def resolve_binding(self, caller: ReadCaller, project_ref: str):
        self.calls.append((caller, project_ref))
        if self.revoked:
            return None
        stable = self.selected.lease
        return ProjectReadBinding(
            caller=caller,
            project_ref=project_ref,
            scope=ReadScope(
                root_fd=123,
                root_device=1,
                root_inode=2,
                context_ref=stable.context_ref,
                owner_ref=stable.owner_ref,
                generation=stable.generation,
                allowed_paths=stable.allowed_paths,
                expires_at_ms=stable.lease_expires_at_ms,
                committed_head=stable.committed_head,
            ),
        )


def test_readiness_probe_is_local_non_authorizing_and_exact() -> None:
    selected = service.parse_service_config(document())
    runtime = _RuntimeProbe(selected)
    state = service.ServiceState()
    state.lifespan_started = True
    state.socket_owned = True
    assert service.is_ready(runtime, selected, state)
    assert len(runtime.calls) == 1
    caller, project_ref = runtime.calls[0]
    assert caller.subject_digest == selected.lease.expected_subject_digest
    assert caller.client_ref == selected.lease.expected_client_ref
    assert caller.resource == selected.lease.resource
    assert caller.scopes == ("workbench.read",)
    assert caller.expires_at * 1000 <= selected.lease.lease_expires_at_ms
    assert project_ref == selected.lease.project_ref
    state.stopping = True
    assert not service.is_ready(runtime, selected, state)
    runtime.revoked = True
    state.stopping = False
    assert not service.is_ready(runtime, selected, state)


def test_shutdown_outcomes_map_to_fixed_exit_truth() -> None:
    assert service.shutdown_exit_code(service.ShutdownOutcome.CLEAN) == 0
    assert service.shutdown_exit_code(service.ShutdownOutcome.RUNTIME_CLOSE_INCOMPLETE) == 3
    assert service.shutdown_exit_code(service.ShutdownOutcome.RUNTIME_CLOSE_UNCERTAIN) == 4
    assert service.shutdown_exit_code(service.ShutdownOutcome.SERVER_FAILED) == 5
