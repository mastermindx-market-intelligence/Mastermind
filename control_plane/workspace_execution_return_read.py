"""Read retained returns through the existing authenticated Workspace owner.

No native I/O, effects, retry, queue, timer, consumption or acceptance owner.
The exact result selector and current CCR membership precede every Runtime read.
"""
import asyncio

from common import workspace_execution_return_contract as wire
from common.executive_workspace_contract import bounded_canonical, digest, error
from control_plane.execution_return_projection import (
    validate_execution_return, validate_execution_return_receipt,
)
from control_plane.executive_runtime import RuntimeRoleResultOverBudget
from control_plane.workspace_owned_task import await_owned


def validate_body(body, selected=None):
    return wire.validate_body(body, selected, record_validator=validate_execution_return,
                              receipt_validator=validate_execution_return_receipt)


def read_execution_return(owner, frame):
    from control_plane.workspace_read_service import (
        _retained_root_join, _qualified_retained_root, _plan_validity_identity,
    )
    selected = wire.selection(frame["selection"])
    cache, runtime, bounded_factory = owner.cache, owner.runtime, owner._bounded_runtime
    try:
        before = cache.snapshot()
    except Exception:
        return wire.unavailable(selected, "SOURCE_UNAVAILABLE")
    retained_row = _retained_root_join(before.document, selected)  # 404 before Runtime for a foreign root.
    if not _qualified_retained_root(before, selected):
        return wire.unavailable(selected, "SOURCE_UNAVAILABLE")
    try:
        bounded = bounded_factory(runtime) if bounded_factory else runtime
        with bounded.observe_bounded_read() as observation:
            source = observation.read_execution_return_bounded(
                selected["root_job_id"], selected["job_id"],
                expected_attempt_id=selected["attempt_id"],
                expected_result_envelope_digest=selected["result_envelope_digest"],
            )
        receipt = observation.receipt  # Finalized only after the physical close.
        after = cache.snapshot()
        if (owner.cache is not cache or owner.runtime is not runtime or owner._bounded_runtime is not bounded_factory
                or before.owner is not after.owner or before.instance != after.instance
                or before.publication != after.publication or digest(before.document) != digest(after.document)
                or digest(_plan_validity_identity(before.validity)) != digest(_plan_validity_identity(after.validity))
                or digest(before.currentness) != digest(after.currentness)):
            return wire.unavailable(selected, "SOURCE_CHANGED")
        if (not _qualified_retained_root(after, selected)
                or not owner._result_binding_verified(source.role_result, receipt, selected)
                or (retained_row.get("runtime_root_state") == "CONFLICT"
                    and source.role_result.root_metadata.work_ref != selected["work_ref"])):
            return wire.unavailable(selected, "SOURCE_UNAVAILABLE")
        body = {
            "schema": wire.BODY_SCHEMA, "selection": selected, "availability": "AVAILABLE",
            "reason_codes": [], "source_observation": owner._result_observation(before, after, selected, receipt),
            "execution_return": source.execution_return, "delivery_receipt": source.delivery_receipt,
        }
        try:
            bounded_canonical({"ok": True, "result": body}, limit=wire.MAX_RESPONSE_BYTES - 1)
        except (TypeError, ValueError):
            return wire.unavailable(selected, "RESPONSE_OVER_BUDGET")
        return {"ok": True, "result": validate_body(body, selected)}
    except RuntimeRoleResultOverBudget:
        return wire.unavailable(selected, "OVER_BUDGET")
    except LookupError:
        raise
    except Exception:
        return wire.unavailable(selected, "SOURCE_UNAVAILABLE")


async def handle_execution_return_frame(owner, frame):
    from control_plane.workspace_read_service import permission_stamp
    try:
        wire.validate_frame(frame)
    except (TypeError, ValueError):
        return error("invalid_input", 400)
    principal, authorize = frame["principal"], owner.authorize
    try:
        stamp = permission_stamp(authorize, principal)
        if authorize(principal) is not True or stamp is None:
            return error("access_denied", 403)
    except Exception:
        return error("access_denied", 403)
    task = asyncio.create_task(asyncio.to_thread(read_execution_return, owner, frame))
    try:
        response = await await_owned(task)
    except LookupError:
        response = error("selection_not_found", 404)
    except Exception:
        response = wire.unavailable(frame["selection"], "SOURCE_UNAVAILABLE")
    try:
        if (owner.authorize is not authorize or authorize(principal) is not True
                or permission_stamp(authorize, principal) != stamp):
            return error("access_denied", 403)
    except Exception:
        return error("access_denied", 403)
    return response
