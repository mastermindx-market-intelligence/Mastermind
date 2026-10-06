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
        parsed = dict(value, release_class=ReleaseClass(value["release_class"]))
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
