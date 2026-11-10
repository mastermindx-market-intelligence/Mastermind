"""Actual Workspace company/capacity READ owners for one authenticated help call."""
from __future__ import annotations

from common import coo_project_help_contract as wire
from common import workspace_capacity_fabric_contract as capacity_wire
from integrations.paperclip_control.agent_context import company_context, unavailable_company


async def read_avenues(owner, authenticated, *, work_ref):
    from integrations.executive_mcp.server import AuditedWorkspaceApp
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
    from integrations.mastermind_workspace_app.contract import principal_frame
    from integrations.paperclip_control.service import PaperclipWorkspace
    if type(owner) is not AuditedWorkspaceApp:
        raise ValueError("PROJECT_HELP_UNAVAILABLE")
    principal, stamp = authenticated
    config = owner._fresh_workspace_config
    if config is None:
        raise ValueError("PROJECT_HELP_UNAVAILABLE")
    binding, client, authorize, clock = config.paperclip, config.client, config.authorize_principal, config.now

    held = {"company_service": None, "company_raw": None, "company_context": None, "capacity": None}

    def current():
        owner.require_context_principal(principal, stamp)
        if (owner._fresh_workspace_config is not config or config.paperclip is not binding
                or config.client is not client or config.authorize_principal is not authorize or config.now is not clock):
            raise ValueError("PROJECT_HELP_UNAVAILABLE")
        service = held["company_service"]
        if service is not None and (service._check() != service.access
                or binding.credential(service.access) != service._token):
            raise ValueError("PROJECT_HELP_UNAVAILABLE")
        if held["company_context"] is not None and company_context(held["company_raw"],
                work_ref=work_ref, now=clock()) != held["company_context"]:
            raise ValueError("PROJECT_HELP_UNAVAILABLE")
        if held["capacity"] is not None:
            capacity_wire.validate_result(held["capacity"], now=clock())

    current()
    company = unavailable_company("company_not_composed")
    if binding is not None:
        try:
            service = PaperclipWorkspace(binding, principal, authorize=authorize, now=clock)
            raw = await service.read({"view": "overview"})
            current()
            company = company_context(raw, work_ref=work_ref, now=clock())
            held.update(company_service=service, company_raw=raw, company_context=company)
        except Exception:
            company = unavailable_company("company_current_read_unavailable")
        current()
    routes = wire.unavailable_routes("CAPACITY_READ_NOT_COMPOSED")
    if type(client) is CeoIngressWorkspaceClient:
        try:
            frame = capacity_wire.validate_frame({"schema": capacity_wire.FRAME_SCHEMA,
                "operation": capacity_wire.OPERATION, "selection": None, "principal": principal_frame(principal)})
            envelope = await client.request(frame)
            current()
            if type(envelope) is not dict or set(envelope) != {"ok", "result"} or envelope["ok"] is not True:
                raise ValueError("capacity_unavailable")
            body = capacity_wire.validate_result(envelope["result"], now=clock())
            if body["availability"] == "AVAILABLE":
                routes = wire.observed_routes(body)
                held["capacity"] = body
            else:
                routes = wire.unavailable_routes("CURRENT_CAPACITY_UNAVAILABLE")
        except Exception:
            routes = wire.unavailable_routes("CURRENT_CAPACITY_UNAVAILABLE")
        current()
    return company, routes, current
