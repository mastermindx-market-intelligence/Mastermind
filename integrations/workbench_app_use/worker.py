"""Private native app MCP channel composed by the existing Operator supervisor.

No worker, provider, authority, process, lease, transport or GUI helper is created
here. The trusted supervisor supplies the original Workbench runtime, owned
native provider, exact original-Attempt admission and fixed native resource policy.
The worker receives only the supervisor-bound private stdio channel.
"""
from __future__ import annotations

from collections.abc import Callable

from integrations.workbench_action_mcp.runtime import WorkbenchActionRuntime
from integrations.workbench_action_mcp.worker_admission import WorkerWorkbenchAdmission
from integrations.workbench_app_use.native_port import NativeProvider
from integrations.workbench_app_use.tunnel import create_worker_native_server


def create_worker_native_stdio_server(
    runtime: WorkbenchActionRuntime,
    *,
    provider: NativeProvider,
    native_grant_provider: Callable,
    admission: WorkerWorkbenchAdmission,
):
    """Reuse the exact native grant and live original-Attempt fence at call time."""
    if (
        not isinstance(runtime, WorkbenchActionRuntime)
        or type(admission) is not WorkerWorkbenchAdmission
        or admission.domain != "native-app"
        or admission._workbench is not runtime
    ):
        raise ValueError("NATIVE_WORKER_ADMISSION_REFUSED")
    return create_worker_native_server(
        runtime,
        provider=provider,
        native_grant_provider=native_grant_provider,
        admission=admission,
    )


async def serve_worker_native_stdio(
    runtime: WorkbenchActionRuntime,
    *,
    provider: NativeProvider,
    native_grant_provider: Callable,
    admission: WorkerWorkbenchAdmission,
    close_timeout_seconds: float,
) -> None:
    """Serve the supervisor-owned private stdio channel; keep runtime as its owner.

    The existing Workbench channel performs bounded close, audit, revocation,
    original work/attempt fencing and no-retry evidence semantics.
    """
    from integrations.workbench_action_mcp.tunnel import run_server_stdio

    # Check before registering any server tools or starting the stdio session.
    if (
        not isinstance(runtime, WorkbenchActionRuntime)
        or type(admission) is not WorkerWorkbenchAdmission
        or admission.domain != "native-app"
        or admission._workbench is not runtime
    ):
        raise ValueError("NATIVE_WORKER_ADMISSION_REFUSED")

    await run_server_stdio(
        runtime,
        server_factory=lambda owned: create_worker_native_stdio_server(
            owned,
            provider=provider,
            native_grant_provider=native_grant_provider,
            admission=admission,
        ),
        close_timeout_seconds=close_timeout_seconds,
    )
