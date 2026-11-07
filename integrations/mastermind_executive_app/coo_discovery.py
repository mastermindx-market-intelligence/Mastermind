"""Finite v4 forwarding through the original audited Workspace App.

This creates no source owner, authenticated principal, durable operation,
publication engine, queue or retry. Both resource bearers are independently
verified by their incumbent owners; no bearer enters a tool body or result.
"""
from __future__ import annotations

import asyncio
import dataclasses
import httpx
from starlette.responses import JSONResponse

from common import coo_discovery_contract as wire
from common import coo_agentos_context_contract as context_wire
from control_plane.workspace_owned_task import await_owned
from integrations.mastermind_workspace_app.contract import principal_frame


async def forward_discovery_mcp(core, inner, request, tool, value):
    """Qualify the original MCP resource pair around the same HTTP adapter."""
    invoked = False
    try:
        value = wire.arguments(tool, value)
        pair = await core.current_context_auth(request)
        work_ref = wire.lookup(tool, value)["work_ref"]
        authority, context = await core._authority(pair[0][0], work_ref, pair[0][1])
        if (wire.action(tool, value) not in authority.principal_actions
                or await core.catalogue(*pair[0], work_ref=work_ref) != wire.CATALOGUE):
            raise ValueError("discovery_grant_unavailable")
        core.require_current_context_auth(*pair)
        headers = {"authorization": request.headers["authorization"],
                   "x-mastermind-workspace-authorization": request.headers["x-mastermind-workspace-authorization"]}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=inner),
                base_url="http://127.0.0.1", trust_env=False, follow_redirects=False) as client:
            invoked = True
            owned = asyncio.create_task(client.post("/v1/tools/" + tool, headers=headers, json={"arguments": value}))
            try:
                response = await await_owned(owned)
            except asyncio.CancelledError:
                if not owned.done() or owned.cancelled():
                    raise
                response = owned.result()
        if response.status_code != 200:
            raise ValueError("discovery_result_unavailable")
        payload = context_wire.decode(response.content, limit=wire.MAX_RESULT_BYTES)
        payload = wire.validate_result(payload, tool=tool, value=value,
            expected_context=dataclasses.asdict(context), capability_profile_digest=authority.capability_profile_digest,
            workspace_principal=principal_frame(pair[1][0]))
        if payload["state"] == "OBSERVED":
            if (await core.current_context_auth(request) != pair
                    or await core._authority(pair[0][0], work_ref, pair[0][1]) != (authority, context)
                    or await core.catalogue(*pair[0], work_ref=work_ref) != wire.CATALOGUE):
                raise ValueError("discovery_authority_changed")
            core.require_current_context_auth(*pair)
        return payload
    except (Exception, asyncio.CancelledError):
        if wire.mutating(tool, value) and invoked:
            state, reason = "EFFECT_UNKNOWN", "ORIGINAL_OUTCOME_UNKNOWN"
        elif not invoked:
            state, reason = "NOT_DISPATCHED", "AUTHORITY_UNAVAILABLE"
        else:
            state, reason = "UNAVAILABLE", "SOURCE_UNAVAILABLE"
        return wire.result(tool, value, state=state, reason=reason)


async def forward_discovery(core, request, authenticated, tool, value):
    value = wire.arguments(tool, value)
    selection, mode = wire.lookup(tool, value), wire.operation(tool, value)
    possible_mutation = False
    identity = {}
    stage_reason = "AUTHORITY_UNAVAILABLE"
    try:
        core.require_context_current()
        settings, workspace = core.settings, core._context_workspace_app
        if workspace is None:
            raise ValueError("workspace_owner_unavailable")
        routing_app, config = workspace._app, workspace._fresh_workspace_config
        if config is None:
            raise ValueError("workspace_owner_unavailable")
        pair = await core.current_context_auth(request)
        if pair[0] != authenticated:
            raise ValueError("principal_changed")
        principal, stamp = authenticated
        authority, context = await core._authority(principal, selection["work_ref"], stamp)
        if (wire.action(tool, value) not in authority.principal_actions
                or await core.catalogue(principal, stamp, work_ref=selection["work_ref"]) != wire.CATALOGUE):
            raise ValueError("discovery_grant_unavailable")
        identity = {"principal_context": dataclasses.asdict(context),
                    "capability_profile_digest": authority.capability_profile_digest,
                    "workspace_principal": principal_frame(pair[1][0])}
        context_wire.workspace_principal(identity["workspace_principal"])

        def current():
            core.require_current_context_auth(*pair)
            if (core.settings is not settings or core._context_workspace_app is not workspace
                    or workspace._app is not routing_app or workspace._fresh_workspace_config is not config):
                raise ValueError("original_workspace_owner_changed")

        async def qualify():
            current()
            if await core.current_context_auth(request) != pair:
                raise ValueError("principal_changed")
            current()
            if (await core._authority(principal, selection["work_ref"], stamp) != (authority, context)
                    or await core.catalogue(principal, stamp, work_ref=selection["work_ref"]) != wire.CATALOGUE):
                raise ValueError("discovery_authority_changed")
            current()

        await qualify()
        companions = request.headers.getlist("x-mastermind-workspace-authorization")
        if len(companions) != 1:
            raise ValueError("workspace_bearer_unavailable")
        headers = {"authorization": companions[0]}
        # Same-process HTTP adapter only. The existing Workspace App retains
        # the only authenticated Control carrier and original source owners.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=workspace),
                base_url="http://127.0.0.1", trust_env=False, follow_redirects=False) as client:
            async def invoke(method, path, payload, *, mutation=False):
                nonlocal possible_mutation, stage_reason
                await qualify()
                stage_reason = "SOURCE_UNAVAILABLE"
                if mutation:
                    possible_mutation = True
                owned = asyncio.create_task(client.request(method, path, headers=headers,
                    **({"params": payload} if method == "GET" else {"json": payload})))
                try:
                    response = await await_owned(owned)
                except asyncio.CancelledError:
                    if not owned.done() or owned.cancelled():
                        raise
                    response = owned.result()
                await qualify()
                if response.status_code != 200:
                    raise ValueError("workspace_result_unavailable")
                return context_wire.decode(response.content, limit=wire.MAX_RESULT_BYTES)

            if tool == wire.SOURCE_TOOL:
                path = ("/workspace/project-discovery-source/current" if mode == "current"
                        else "/workspace/source-operation/original")
                body = await invoke("GET", path, selection)
            elif mode == "prepare":
                body = await invoke("POST", "/workspace/source-operation/prepare",
                    {"action": wire.CORRECTION_ACTION, "request": value["request"]}, mutation=True)
            elif mode == "submit":
                # Bind all eight original fields before the three-field submit
                # carrier. An already-progressed original is observed only.
                body = await invoke("GET", "/workspace/source-operation/operation", selection)
                body = wire.validate_data(tool, value, body, workspace_principal=identity["workspace_principal"])
                if body["receipt"] is not None and body["receipt"]["kind"] == "INTENT":
                    payload = {k: selection[k] for k in ("action", "request_id", "work_ref")}
                    payload["preview_witness"] = value["preview_witness"]
                    body = await invoke("POST", "/workspace/source-operation/submit", payload, mutation=True)
            elif mode == "read":
                body = await invoke("GET", "/workspace/source-operation/operation", selection)
            else:
                body = await invoke("POST", "/workspace/source-operation/reconcile", selection, mutation=True)
        await qualify()
        payload = wire.result(tool, value, state="OBSERVED", reason="OWNER_RESULT", data=body, **identity)
    except (Exception, asyncio.CancelledError):
        # A rejection after entering the owner may follow a durable Event or
        # Git effect. Keep the original lookup even when authentication changed.
        if possible_mutation:
            state, reason = "EFFECT_UNKNOWN", "ORIGINAL_OUTCOME_UNKNOWN"
        elif wire.mutating(tool, value):
            state, reason = "NOT_DISPATCHED", stage_reason
        else:
            state, reason = "UNAVAILABLE", stage_reason
        payload = wire.result(tool, value, state=state, reason=reason)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})
