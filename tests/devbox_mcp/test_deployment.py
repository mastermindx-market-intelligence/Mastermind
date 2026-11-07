from __future__ import annotations

import asyncio
import dataclasses

import pytest

from integrations.devbox_mcp.codespace_runtime import CodespaceBinding, DevBoxRuntimeError
from integrations.devbox_mcp.contracts import OBSERVE_SCOPE, OBSERVE_TOOL_NAMES, TOOL_NAMES
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
EXECUTE_SCOPE = "workbench.execute"


def _binding() -> CodespaceBinding:
    return CodespaceBinding(
        target_ref=TARGET,
        generation=GENERATION,
        owner_ref=OWNER,
        repository="mastermindx-market-intelligence/Mastermind",
        committed_head=HEAD,
    )


def _lease(scope: str = EXECUTE_SCOPE, **changes) -> StableDevBoxLease:
    value = StableDevBoxLease(
        expected_subject_digest=SUBJECT,
        expected_client_ref=CLIENT,
        resource=RESOURCE,
        required_scopes=(scope,),
        target_ref=TARGET,
        generation=GENERATION,
        owner_ref=OWNER,
        repository="mastermindx-market-intelligence/Mastermind",
        committed_head=HEAD,
        lease_expires_at=NOW + 600,
    )
    return dataclasses.replace(value, **changes)


def _caller(scope: str = EXECUTE_SCOPE, **changes) -> DevBoxCaller:
    value = DevBoxCaller(
        subject_digest=SUBJECT,
        client_ref=CLIENT,
        resource=RESOURCE,
        scopes=(scope,),
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


def test_observe_lease_dispatches_status_and_read_but_refuses_modify_tools() -> None:
    runtime = Runtime()
    port = _port(runtime=runtime, lease=_lease(OBSERVE_SCOPE))
    caller = _caller(OBSERVE_SCOPE)

    for name, args in (
        ("devbox_status", {}),
        ("read_devbox_process", {"process_ref": "process:" + "c" * 64}),
    ):
        result = _run(port.call(caller, name, args))
        assert result == {"tool": name, "arguments": args}

    for name, args in (
        ("start_devbox_command", {"operation_key": "op", "command_text": "true"}),
        ("cancel_devbox_process", {"process_ref": "process:" + "c" * 64}),
    ):
        with pytest.raises(DevBoxPortRefused) as exc_info:
            _run(port.call(caller, name, args))
        assert exc_info.value.code == "TOOL_NOT_AVAILABLE"

    assert [name for name, _args in runtime.calls] == list(OBSERVE_TOOL_NAMES)
    assert port._allowed_tools == OBSERVE_TOOL_NAMES


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
        ("SOURCE_DIRTY", "SOURCE_DIRTY"),
        ("OPERATION_CONFLICT", "OPERATION_CONFLICT"),
        ("PROCESS_NOT_FOUND", "PROCESS_NOT_FOUND"),
        ("PROCESS_IDENTITY_UNKNOWN", "PROCESS_IDENTITY_UNKNOWN"),
        ("EFFECT_UNKNOWN", "EFFECT_UNKNOWN"),
        ("CANCEL_UNCERTAIN", "CANCEL_UNCERTAIN"),
        ("PRE_EFFECT_RECEIPT_UNAVAILABLE", "PRE_EFFECT_RECEIPT_UNAVAILABLE"),
        ("START_REFUSED", "DEVBOX_REFUSED"),
        ("RECEIPT_UNAVAILABLE", "RECEIPT_UNAVAILABLE"),
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


@pytest.mark.parametrize(
    "required_scopes",
    [(), ("workbench.read",), (OBSERVE_SCOPE, EXECUTE_SCOPE)],
)
def test_lease_requires_one_exact_supported_scope(required_scopes: tuple[str, ...]) -> None:
    with pytest.raises((TypeError, ValueError)):
        StableDevBoxLease(
            expected_subject_digest=SUBJECT,
            expected_client_ref=CLIENT,
            resource=RESOURCE,
            required_scopes=required_scopes,
            target_ref=TARGET,
            generation=GENERATION,
            owner_ref=OWNER,
            repository="mastermindx-market-intelligence/Mastermind",
            committed_head=HEAD,
            lease_expires_at=NOW + 600,
        )


def test_execute_lease_keeps_existing_four_tool_profile() -> None:
    port = _port()
    assert port._allowed_tools == TOOL_NAMES
