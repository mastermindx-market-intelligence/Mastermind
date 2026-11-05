"""Additive rootless Direction READ adapter over the existing Workspace owner.

No Runtime/Job selector, source cache, principal registry or publisher is created.
Shared registration attaches this adapter only after issuing its sealed reader.
"""
import asyncio

from common import workspace_project_direction_contract as wire
from common.executive_workspace_contract import error
from control_plane.agentos_project_direction import AgentOsProjectDirectionReader
from control_plane.workspace_read_service import (
    WorkspaceReadService, _qualified, _plan_validity_identity, digest,
    permission_stamp, await_owned,
)


class ProjectDirectionReadAdapter:
    def __init__(self, *, workspace, reader):
        if type(workspace) is not WorkspaceReadService or reader is not None and type(reader) is not AgentOsProjectDirectionReader:
            raise ValueError("SOURCE_UNAVAILABLE")
        self._workspace = workspace
        self._reader = reader

    @staticmethod
    def _member(snapshot, work_ref):
        if not _qualified(snapshot):
            raise ValueError("SOURCE_UNAVAILABLE")
        rows = [row for row in snapshot.document["work"] if row.get("work_ref") == work_ref]
        if len(rows) != 1:
            raise LookupError("selection_not_found")

    def _read(self, selected):
        owner, reader = self._workspace, self._reader
        before = owner.cache.snapshot()
        self._member(before, selected["work_ref"])
        if reader is None:
            return wire.unavailable(selected["work_ref"], "SOURCE_UNAVAILABLE")
        result = wire.validate_body(reader.read(work_ref=selected["work_ref"]))
        after = owner.cache.snapshot()
        self._member(after, selected["work_ref"])
        if (self._workspace is not owner or self._reader is not reader
                or before.owner is not after.owner or before.instance != after.instance
                or before.publication != after.publication or digest(before.document) != digest(after.document)
                or digest(_plan_validity_identity(before.validity)) != digest(_plan_validity_identity(after.validity))
                or digest(before.currentness) != digest(after.currentness)):
            return wire.unavailable(selected["work_ref"], "SOURCE_CHANGED")
        if (result["selection"] != selected or result["availability"] == "AVAILABLE"
                and result["source"]["commit"] != before.document.get("sources", {}).get("macro_sha")):
            return wire.unavailable(selected["work_ref"], "SOURCE_CHANGED")
        return result

    async def handle_frame(self, frame):
        try:
            wire.validate_frame(frame)
        except (TypeError, ValueError):
            return error("invalid_input", 400)
        owner = self._workspace
        principal, selected = frame["principal"], frame["selection"]
        authorizer = owner.authorize
        try:
            if authorizer(principal) is not True:
                return error("access_denied", 403)
            stamp = permission_stamp(authorizer, principal)
            if stamp is None:
                return error("access_denied", 403)
        except Exception:
            return error("access_denied", 403)
        task = asyncio.create_task(asyncio.to_thread(self._read, selected))
        try:
            body = await await_owned(task)
            result = {"ok": True, "result": body}
        except LookupError:
            result = error("selection_not_found", 404)
        except Exception:
            result = {"ok": True, "result": wire.unavailable(selected["work_ref"], "SOURCE_UNAVAILABLE")}
        try:
            if (self._workspace is not owner or owner.authorize is not authorizer
                    or authorizer(principal) is not True or permission_stamp(authorizer, principal) != stamp):
                return error("access_denied", 403)
        except Exception:
            return error("access_denied", 403)
        return result
