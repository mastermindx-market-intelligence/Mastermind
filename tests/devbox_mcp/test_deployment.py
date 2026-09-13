from __future__ import annotations

import asyncio
import dataclasses

import pytest

from integrations.devbox_mcp.codespace_runtime import CodespaceBinding, DevBoxRuntimeError
from integrations.devbox_mcp.deployment import BoundDevBoxPort, StableDevBoxLease
from integrations.devbox_mcp.port import DevBoxCaller, DevBoxPortRefused

NOW = 1_789_270_000
SUBJECT = "a" * 64
CLIENT = "b" * 64
RESOURCE = "https://devbox.example/mcp"
TARGET = "target:" + "1" * 64
GENERATION = "generation:" + "2" * 64
OWNER = "owner:" + "3" * 64
HEAD = "4" * 40


def _binding() -> CodespaceBinding:
    return CodespaceBinding(
        target_ref=TARGET,
        generation=GENERATION,
        owner_ref=OWNER,
        repository="mastermindx-market-intelligence/Mastermind",
        committed_head=HEAD,
    )


def _lease(**changes) -> StableDevBoxLease:
    value = StableDevBoxLease(
        expected_subject_digest=SUBJECT,
        expected_client_ref=CLIENT,
        resource=RESOURCE,
        required_scopes=("workbench.execute",),
        target_ref=TARGET,
        generation=GENERATION,
        owner_ref=OWNER,
        repository="mastermindx-market-intelligence/Mastermind",
        committed_head=HEAD,
        lease_expires_at=NOW + 600,
    )
    return dataclasses.replace(value, **changes)


def _caller(**changes) -> DevBoxCaller:
    value = DevBoxCaller(
        subject_digest=SUBJECT,
        client_ref=CLIENT,
        resource=RESOURCE,
        scopes=("workbench.execute",),
        expires_at=NOW + 300,
    )
    return dataclasses.replace(value, **changes)


class Runtime:
    def __init__(self):
        self.binding = _binding()
        self.calls = []
        self.fail = None

    async def status(self, arguments):
        return await self._call("devbox_status", arguments)

    async def start_command(self, arguments):
        return await self._call("start_devbox_command", arguments)

    async def read_process(self, arguments):
        return await self._call("read_devbox_process", arguments)

    async def cancel_process(self, arguments):
        return await self._call("cancel_devbox_process", arguments)

    async def _call(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if self.fail:
            raise DevBoxRuntimeError(self.fail, "PRIVATE_RUNTIME_DETAIL")
        return {"tool": name, "arguments": dict(arguments)}


def _port(runtime=None, lease=None, now=lambda: NOW) -> BoundDevBoxPort:
    return BoundDevBoxPort(runtime=runtime or Runtime(), lease=lease or _lease(), now=now)


def _run(coro):
    return asyncio.run(coro)


def test_exact_caller_dispatches_all_four_tools_without_target_from_model() -> None:
    runtime = Runtime()
    port = _port(runtime=runtime)
    cases = [
        ("devbox_status", {}),
        ("start_devbox_command", {"operation_key": "op", "command_text": "true"}),
        ("read_devbox_process", {"process_ref": "process:" + "c" * 64}),
        ("cancel_devbox_process", {"process_ref": "process:" + "c" * 64}),
    ]
    for name, args in cases:
        result = _run(port.call(_caller(), name, args))
        assert result == {"tool": name, "arguments": args}
    assert runtime.calls == cases


@pytest.mark.parametrize(
    "caller",
    [
        _caller(subject_digest="c" * 64),
        _caller(client_ref="d" * 64),
        _caller(resource="https://other.example/mcp"),
        _caller(scopes=("workbench.read",)),
        _caller(expires_at=NOW),
    ],
)
def test_wrong_or_expired_caller_refuses_before_runtime(caller: DevBoxCaller) -> None:
    runtime = Runtime()
    port = _port(runtime=runtime)
    with pytest.raises(DevBoxPortRefused) as exc_info:
        _run(port.call(caller, "devbox_status", {}))
    assert exc_info.value.code == "DEVBOX_REFUSED"
    assert runtime.calls == []


def test_expired_lease_refuses_before_runtime() -> None:
    runtime = Runtime()
    port = _port(runtime=runtime, lease=_lease(lease_expires_at=NOW))
    with pytest.raises(DevBoxPortRefused) as exc_info:
        _run(port.call(_caller(), "devbox_status", {}))
    assert exc_info.value.code == "DEVBOX_REFUSED"
    assert runtime.calls == []


def test_runtime_binding_must_exactly_match_stable_lease() -> None:
    runtime = Runtime()
    runtime.binding = dataclasses.replace(_binding(), generation="generation:" + "9" * 64)
    with pytest.raises(ValueError, match="binding"):
        _port(runtime=runtime)


def test_clock_failure_or_non_integer_fails_closed() -> None:
    runtime = Runtime()
    for now in (lambda: True, lambda: 1.5, lambda: (_ for _ in ()).throw(RuntimeError("secret"))):
        port = _port(runtime=runtime, now=now)
        with pytest.raises(DevBoxPortRefused) as exc_info:
            _run(port.call(_caller(), "devbox_status", {}))
        assert exc_info.value.code == "DEVBOX_REFUSED"
    assert runtime.calls == []


def test_unknown_tool_refuses_without_runtime_call() -> None:
    runtime = Runtime()
    port = _port(runtime=runtime)
    with pytest.raises(DevBoxPortRefused) as exc_info:
        _run(port.call(_caller(), "shell", {"command_text": "true"}))
    assert exc_info.value.code == "DEVBOX_REFUSED"
    assert runtime.calls == []


@pytest.mark.parametrize(
    ("runtime_code", "port_code"),
    [
        ("BINDING_CHANGED", "BINDING_CHANGED"),
        ("OPERATION_CONFLICT", "OPERATION_CONFLICT"),
        ("PROCESS_NOT_FOUND", "PROCESS_NOT_FOUND"),
        ("PROCESS_IDENTITY_UNKNOWN", "PROCESS_IDENTITY_UNKNOWN"),
        ("EFFECT_UNKNOWN", "EFFECT_UNKNOWN"),
        ("CANCEL_UNCERTAIN", "CANCEL_UNCERTAIN"),
        ("START_REFUSED", "DEVBOX_REFUSED"),
        ("RECEIPT_UNAVAILABLE", "DEVBOX_REFUSED"),
        ("PRIVATE_UNKNOWN", "DEVBOX_REFUSED"),
    ],
)
def test_runtime_failures_map_to_closed_port_codes(runtime_code: str, port_code: str) -> None:
    runtime = Runtime()
    runtime.fail = runtime_code
    port = _port(runtime=runtime)
    with pytest.raises(DevBoxPortRefused) as exc_info:
        _run(port.call(_caller(), "devbox_status", {}))
    assert exc_info.value.code == port_code
    assert "PRIVATE_RUNTIME_DETAIL" not in str(exc_info.value)


def test_lease_is_immutable_and_requires_exact_execute_scope() -> None:
    with pytest.raises((TypeError, ValueError)):
        StableDevBoxLease(
            expected_subject_digest=SUBJECT,
            expected_client_ref=CLIENT,
            resource=RESOURCE,
            required_scopes=("workbench.read",),
            target_ref=TARGET,
            generation=GENERATION,
            owner_ref=OWNER,
            repository="mastermindx-market-intelligence/Mastermind",
            committed_head=HEAD,
            lease_expires_at=NOW + 600,
        )
