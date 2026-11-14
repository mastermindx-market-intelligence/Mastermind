"""Private native stdio composition is fenced to the original Workbench owner."""
from __future__ import annotations

import asyncio

import pytest

from integrations.workbench_action_mcp.runtime import WorkbenchActionRuntime
from integrations.workbench_action_mcp.worker_admission import WorkerWorkbenchAdmission
from integrations.workbench_app_use import worker
import integrations.workbench_action_mcp.tunnel as action_tunnel


def synthetic_owner():
    """Pure composition fixture. Actual Runtime admission is tested separately."""
    runtime = object.__new__(WorkbenchActionRuntime)
    admission = object.__new__(WorkerWorkbenchAdmission)
    admission._workbench = runtime
    admission.domain = "native-app"
    return runtime, admission


def test_native_server_uses_original_runtime_and_exact_admission(monkeypatch):
    runtime, admission = synthetic_owner()
    seen = []
    marker = object()

    def real_factory(*args, **kwargs):
        seen.append((args, kwargs))
        return marker

    monkeypatch.setattr(worker, "create_worker_native_server", real_factory)
    policy = lambda _: None
    provider = object()
    assert worker.create_worker_native_stdio_server(
        runtime, provider=provider, native_grant_provider=policy,
        admission=admission,
    ) is marker
    assert seen == [( (runtime,), {
        "provider": provider, "native_grant_provider": policy,
        "admission": admission,
    })]

    admission.domain = "browser"
    with pytest.raises(ValueError, match="NATIVE_WORKER_ADMISSION_REFUSED"):
        worker.create_worker_native_stdio_server(
            runtime, provider=provider, native_grant_provider=policy,
            admission=admission,
        )
    admission.domain = "native-app"
    with pytest.raises(ValueError, match="NATIVE_WORKER_ADMISSION_REFUSED"):
        worker.create_worker_native_stdio_server(
            object.__new__(WorkbenchActionRuntime), provider=provider,
            native_grant_provider=policy, admission=admission,
        )


def test_native_stdio_reuses_existing_channel_shutdown_and_fence(monkeypatch):
    runtime, admission = synthetic_owner()
    events = []
    marker = object()
    provider = object()
    policy = lambda _: None

    def native_factory(*args, **kwargs):
        events.append(("factory", args, kwargs))
        return marker

    async def stdio_owner(owned, *, server_factory, close_timeout_seconds):
        assert owned is runtime
        assert close_timeout_seconds == 7.0
        assert server_factory(runtime) is marker
        events.append(("served",))

    monkeypatch.setattr(worker, "create_worker_native_server", native_factory)
    monkeypatch.setattr(action_tunnel, "run_server_stdio", stdio_owner)

    asyncio.run(worker.serve_worker_native_stdio(
        runtime, provider=provider, native_grant_provider=policy,
        admission=admission, close_timeout_seconds=7.0,
    ))
    assert [event[0] for event in events] == ["factory", "served"]

    admission.domain = "browser"
    with pytest.raises(ValueError, match="NATIVE_WORKER_ADMISSION_REFUSED"):
        asyncio.run(worker.serve_worker_native_stdio(
            runtime, provider=provider, native_grant_provider=policy,
            admission=admission, close_timeout_seconds=7.0,
        ))
    assert [event[0] for event in events] == ["factory", "served"]
