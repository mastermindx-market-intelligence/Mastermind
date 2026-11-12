"""Existing Workspace permission boundary for the current Capacity Fabric view."""
import asyncio

from common import workspace_capacity_fabric_contract as wire
from common.executive_workspace_contract import error
from control_plane.workspace_capacity_fabric import ExistingCapacityFabricSource
from control_plane.workspace_read_service import await_owned, permission_stamp


async def handle_capacity_fabric_frame(owner, frame):
    try:
        wire.validate_frame(frame)
    except (TypeError, ValueError):
        return error("invalid_input", 400)
    principal, authorizer = frame["principal"], owner.authorize
    source = owner._capacity_fabric_source
    try:
        if authorizer(principal) is not True:
            return error("access_denied", 403)
        stamp = permission_stamp(authorizer, principal)
        if stamp is None:
            return error("access_denied", 403)
    except Exception:
        return error("access_denied", 403)
    if type(source) is not ExistingCapacityFabricSource:
        return wire.unavailable()
    task = asyncio.create_task(asyncio.to_thread(source.read))
    try:
        response = await await_owned(task)
    except Exception:
        response = wire.unavailable()
    try:
        if (owner.authorize is not authorizer or authorizer(principal) is not True
                or permission_stamp(authorizer, principal) != stamp):
            return error("access_denied", 403)
        if owner._capacity_fabric_source is not source:
            return wire.unavailable("SOURCE_CHANGED")
    except Exception:
        return error("access_denied", 403)
    try:
        if type(response) is not dict or set(response) != {"ok", "result"} or response["ok"] is not True:
            return wire.unavailable()
        wire.validate_result(response["result"])
    except Exception:
        return wire.unavailable()
    return response
