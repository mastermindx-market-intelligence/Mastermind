"""Browser-specific composition using the shared original-Attempt admission."""
from __future__ import annotations

from integrations.workbench_action_mcp.runtime import WorkbenchActionRuntime
from integrations.workbench_action_mcp.service import BrowserServiceConfig
from integrations.workbench_action_mcp.worker_admission import (
    WorkerWorkbenchAdmission, project_worker_workbench_lease,
)
from .tunnel import create_browser_tunnel_server


def _refuse():
    raise ValueError("BROWSER_WORKER_ADMISSION_REFUSED")


class WorkerBrowserAdmission(WorkerWorkbenchAdmission):
    def __init__(self, *args, **kwargs):
        if "domain" in kwargs:
            _refuse()
        try:
            super().__init__(*args, **kwargs, domain="browser")
        except ValueError as error:
            raise ValueError("BROWSER_WORKER_ADMISSION_REFUSED") from error


def project_worker_browser_lease(lease, *, attempt, epoch, generation, profile):
    try:
        return project_worker_workbench_lease(lease, attempt=attempt, epoch=epoch,
            generation=generation, profile=profile, domain="browser")
    except ValueError as error:
        raise ValueError("BROWSER_WORKER_ADMISSION_REFUSED") from error


def create_worker_browser_server(runtime: WorkbenchActionRuntime,
                                config: BrowserServiceConfig,
                                admission: WorkerBrowserAdmission):
    """The supervisor serves this on its admitted attempt-private stdio pair."""
    if type(admission) is not WorkerBrowserAdmission or admission._workbench is not runtime:
        _refuse()
    return create_browser_tunnel_server(runtime, config, mcp_grant=admission.grant,
        resolve_binding=admission.resolve_binding)


async def serve_worker_browser_stdio(runtime: WorkbenchActionRuntime,
                                     config: BrowserServiceConfig,
                                     admission: WorkerBrowserAdmission, *,
                                     close_timeout_seconds: float) -> None:
    """Serve a supervisor-owned private stdio channel and retire its runtime.

    Call only in the trusted channel process whose stdin/stdout are already
    bound to this Attempt by the supervisor. This does not allocate or pass
    pipes, spawn a worker, or accept authority through model-facing arguments.
    The existing runner owns framing, revocation and bounded shutdown, including
    factory failure and uncertain cleanup; those exceptions remain observable.
    """
    from integrations.workbench_action_mcp.tunnel import run_server_stdio

    await run_server_stdio(runtime,
        server_factory=lambda owned: create_worker_browser_server(owned, config, admission),
        close_timeout_seconds=close_timeout_seconds)
