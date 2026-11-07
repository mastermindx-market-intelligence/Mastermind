"""Fixed authenticated historical provider-capacity read through existing owners."""
import asyncio
from common import workspace_resource_capacity_contract as wire
from common.executive_workspace_contract import error
from control_plane.workspace_resource_capacity import project_capacity_source
from control_plane.workspace_read_service import _join, _qualified, _plan_validity_identity, digest, permission_stamp, await_owned


def read_capacity(owner, frame):
    selected = wire.selection(frame["selection"])
    try:
        before = owner.cache.snapshot()
    except Exception:
        return wire.unavailable(selected, "SOURCE_UNAVAILABLE")
    _join(before.document, selected)
    if not _qualified(before, selected):
        return wire.unavailable(selected, "SOURCE_UNAVAILABLE")
    from control_plane.executive_runtime import RuntimeRoleResultOverBudget
    try:
        runtime = owner._bounded_runtime(owner.runtime) if owner._bounded_runtime else owner.runtime
        with runtime.observe_bounded_read() as observation:
            source = observation.read_retained_capacity_bounded(selected["root_job_id"], selected["job_id"], selected["attempt_id"])
        receipt = observation.receipt
        after = owner.cache.snapshot()
        if (before.owner is not after.owner or before.instance != after.instance
                or before.publication != after.publication or digest(before.document) != digest(after.document)
                or digest(_plan_validity_identity(before.validity)) != digest(_plan_validity_identity(after.validity))
                or digest(before.currentness) != digest(after.currentness)):
            return wire.unavailable(selected, "SOURCE_CHANGED")
        _join(after.document, selected)
        if not _qualified(after, selected):
            return wire.unavailable(selected, "SOURCE_UNAVAILABLE")
        body = project_capacity_source(source, receipt, **selected, now_ms=owner.runtime.store.now_ms())
        observed = owner._result_observation(before, after, selected, receipt)
        observed["schema"] = wire.OBSERVATION_SCHEMA
        response = {"schema": wire.BODY_SCHEMA, "selection": selected, "availability": "AVAILABLE",
                    "reason_codes": [], "provider_capacity": body, "source_observation": observed}
        return {"ok": True, "result": wire.validate_result(response, selected)}
    except RuntimeRoleResultOverBudget:
        return wire.unavailable(selected, "OVER_BUDGET")
    except LookupError:
        raise
    except Exception:
        return wire.unavailable(selected, "SOURCE_UNAVAILABLE")


async def handle_capacity_frame(owner, frame, *, original_owner=None):
    try:
        wire.validate_frame(frame)
    except (TypeError, ValueError):
        return error("invalid_input", 400)
    principal, selected = frame["principal"], frame["selection"]
    try:
        if owner.authorize(principal) is not True:
            return error("access_denied", 403)
        stamp = permission_stamp(owner.authorize, principal)
        if stamp is None:
            return error("access_denied", 403)
        reader = original_owner if original_owner is not None else owner._activity_membership
        original_reader = owner._activity_membership
        marker = owner._activity_membership_marker(principal, selected, original_owner=reader)
    except Exception:
        return error("access_denied", 403)
    task = asyncio.create_task(asyncio.to_thread(read_capacity, owner, frame))
    try:
        response = await await_owned(task)
    except LookupError:
        response = error("selection_not_found", 404)
    except Exception:
        response = wire.unavailable(selected, "SOURCE_UNAVAILABLE")
    try:
        if (owner.authorize(principal) is not True or permission_stamp(owner.authorize, principal) != stamp
                or owner._activity_membership is not original_reader
                or owner._activity_membership_marker(principal, selected, original_owner=reader) != marker):
            return error("access_denied", 403)
    except Exception:
        return error("access_denied", 403)
    return response


async def handle_from_original_coo(owner, frame, installed_source):
    from ops.executive_os.coo_principal_host import CooInstalledSource
    if type(installed_source) is not CooInstalledSource:
        return error("access_denied", 403)
    return await handle_capacity_frame(owner, frame, original_owner=installed_source.for_workspace_read_principal)
