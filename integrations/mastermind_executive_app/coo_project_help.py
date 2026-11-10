"""Project-help read through the original independently authenticated owners."""
from __future__ import annotations

import dataclasses

from starlette.responses import JSONResponse

from common import coo_project_help_contract as wire
from integrations.mastermind_workspace_app.contract import principal_frame as workspace_frame


async def forward_project_help(core, request, authenticated, selected):
    from .coo import _owner_call, refused
    settings = core.settings
    provider = settings.project_help_provider
    principal, stamp = authenticated

    def current():
        core.require_context_current()
        if core.settings is not settings or settings.project_help_provider is not provider:
            raise ValueError("PROJECT_HELP_UNAVAILABLE")

    try:
        current()
        if provider is None:
            return refused()
        pair = await core.current_context_auth(request)
        current()
        if pair[0] != authenticated:
            return refused()
        workspace = pair[1][0]
        catalogue = await core.catalogue(principal, stamp, work_ref=selected["work_ref"])
        current()
        authority, context = await core._authority(principal, selected["work_ref"], stamp)
        current()
        if catalogue not in {wire.CATALOGUE, wire.API_REQUESTER_CATALOGUE} or wire.ACTION not in authority.principal_actions:
            return refused()
        if await core.current_context_auth(request) != pair:
            return refused()
        current()
        data = await _owner_call(provider, principal, workspace, context, authority.capability_profile_digest)
        current()
        wire.validate_result(data, expected_context=dataclasses.asdict(context),
            capability_profile_digest=authority.capability_profile_digest,
            expected_workspace_principal=workspace_frame(workspace))
        from .coo_project_help_avenues import read_avenues
        company, routes, avenues_current = await read_avenues(core._context_workspace_app,
            pair[1], work_ref=selected["work_ref"])
        current()
        # These are separate source reads. Re-prove the same enrolled source,
        # root and target facts after the Company/Capacity acquisitions.
        after = await _owner_call(provider, principal, workspace, context, authority.capability_profile_digest)
        current()
        if wire.read_identity(after) != wire.read_identity(data):
            return refused("source_unavailable", 503)
        avenues_current()
        data = {**after, "relationships": company, "execution_routes": routes}
        wire.validate_result(data, expected_context=dataclasses.asdict(context),
            capability_profile_digest=authority.capability_profile_digest,
            expected_workspace_principal=workspace_frame(workspace))
        if (await core._authority(principal, selected["work_ref"], stamp) != (authority, context)
                or await core.catalogue(principal, stamp, work_ref=selected["work_ref"]) != catalogue
                or await core.current_context_auth(request) != pair):
            return refused()
        current()
        core.require_current_context_auth(*pair)
        avenues_current()
        response = JSONResponse(core._read_result(wire.TOOL, data), headers={"Cache-Control": "no-store"})
        if len(response.body) > wire.MAX_RESPONSE_BYTES + 4096:
            return refused("output_too_large", 503)
        return response
    except Exception:
        return refused("source_unavailable", 503)
