"""Network-only COO fact adapter over the incumbent bounded Workspace client.

No Runtime handle, authority cache, token acquisition, or mutable grant store.
"""
from __future__ import annotations
import dataclasses
from control_plane.coo_principal_host import FACT_SCHEMA, validate_facts_frame
from control_plane.coo_principal_mandate import AuthorityFact, ReleaseClass
from integrations.mastermind_executive_app.coo_binding import principal_frame
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient


class CooFactsClient:
    def __init__(self, socket_path):
        self._client = CeoIngressWorkspaceClient(socket_path)
        self._context_client = self._client
        self._context_socket_path = self._client.socket_path
        self._context_request = self._client.request

    async def _read(self, principal, work_ref, operation):
        frame = dict(schema=FACT_SCHEMA, operation=operation, work_ref=work_ref,
                     principal=principal_frame(principal))
        validate_facts_frame(frame)
        response = await self._client.request(frame)
        if response.get("ok") is not True:
            raise ValueError("installed COO facts unavailable")
        return response["result"]

    async def authority(self, principal, work_ref):
        value = await self._read(principal, work_ref, "authority")
        if type(value) is not dict or set(value) != {f.name for f in dataclasses.fields(AuthorityFact)}:
            raise ValueError("installed COO authority shape refused")
        actions = value.get("principal_actions")
        if type(actions) is not list:
            raise ValueError("installed COO principal action grant refused")
        parsed = dict(
            value,
            release_class=ReleaseClass(value["release_class"]),
            principal_actions=tuple(actions),
        )
        authority = AuthorityFact(**parsed)
        if authority.work_ref != work_ref or authority.release_class is not ReleaseClass.RESERVED_RELEASE:
            raise ValueError("installed COO authority identity refused")
        if authority.source_grant_digest is not None or authority.economic_envelope_digest is not None:
            raise ValueError("bounded job admission cannot grant direct source or spend authority")
        return authority

    async def mission(self, principal, work_ref):
        value = await self._read(principal, work_ref, "mission")
        if (type(value) is not dict or value.get("schema") != "mastermind.mission_workspace.v3"
                or value.get("program", {}).get("work_ref") != work_ref):
            raise ValueError("installed COO mission identity refused")
        return value

    async def agentos_context(self, principal, context, capability_profile_digest):
        return await self._context_read(principal, context, capability_profile_digest)

    async def agentos_current_context(self, principal, workspace, context, capability_profile_digest):
        return await self._context_read(principal, context, capability_profile_digest, workspace=workspace)

    async def _context_read(self, principal, context, capability_profile_digest, *, workspace=None):
        from common import coo_agentos_context_contract as wire
        client, request = self._context_client, self._context_request
        def current():
            if (self._client is not client or client.socket_path != self._context_socket_path
                    or getattr(client.request, "__self__", None) is not client
                    or getattr(client.request, "__func__", None) is not request.__func__):
                raise ValueError("installed COO context transport changed")
        current()
        frame = {"schema": wire.CURRENT_FRAME_SCHEMA if workspace is not None else wire.FRAME_SCHEMA,
            "principal": principal_frame(principal),
            "principal_context": dataclasses.asdict(context), "capability_profile_digest": capability_profile_digest}
        if workspace is not None:
            from integrations.mastermind_workspace_app.contract import principal_frame as workspace_frame
            frame["workspace_principal"] = workspace_frame(workspace)
            wire.validate_current_frame(frame)
        else:
            wire.validate_frame(frame)
        response = await request(frame)
        current()
        if response.get("ok") is not True:
            raise ValueError("installed COO context unavailable")
        value = response["result"]
        if workspace is not None:
            wire.validate_current_result(value, expected_context=frame["principal_context"],
                capability_profile_digest=capability_profile_digest, expected_workspace_principal=frame["workspace_principal"])
        else:
            wire.validate_result(value, expected_context=frame["principal_context"],
                capability_profile_digest=capability_profile_digest)
        return value
