"""Selected policy READ composed through the incumbent Workspace owner.

No new lifecycle, policy owner, permission or host collector is installed.
The fixed HTTP/socket handler may call this adapter after consequence review.
It retains the original admitted-plan acquisition and brackets the additional
policy-source projection with the same permission and catalogue identities.
"""
from __future__ import annotations

from common import executive_workspace_contract as workspace
from common import workspace_autonomy_read_contract as wire
from control_plane.executive_coo_policy import CooCyclePolicy
from control_plane.workspace_autonomy_read import compose_autonomy_policy_read


def _same_source(before, after, validity_identity):
    return (before.owner is after.owner and before.instance == after.instance
            and before.publication == after.publication
            and workspace.digest(before.document) == workspace.digest(after.document)
            and workspace.digest(validity_identity(before.validity)) == workspace.digest(validity_identity(after.validity))
            and workspace.digest(before.currentness) == workspace.digest(after.currentness))


async def read_autonomy_policy(service, frame):
    """One source read; no host status or project pause effect is reachable."""
    from control_plane.workspace_read_service import (
        WorkspaceReadService, _join, _qualified, _plan_validity_identity,
    )
    if type(service) is not WorkspaceReadService:
        raise ValueError("existing Workspace read owner required")
    try:
        wire.validate_frame(frame)
    except (TypeError, ValueError):
        return workspace.error("invalid_input", 400)
    principal, selected = frame["principal"], frame["selection"]
    authorize, cache, runtime, bounded_runtime = (
        service.authorize, service.cache, service.runtime, service._bounded_runtime,
    )

    def permit(stamp=None):
        try:
            if service.authorize is not authorize or authorize(principal) is not True:
                return None
            current = workspace.permission_stamp(authorize, principal)
            return current if current is not None and (stamp is None or current == stamp) else None
        except Exception:
            return None

    stamp = permit()
    if stamp is None:
        return workspace.error("access_denied", 403)
    try:
        before = cache.snapshot()
        _join(before.document, selected)
        if not _qualified(before, selected):
            response = wire.unavailable(selected, "SOURCE_UNAVAILABLE")
        else:
            # The existing owner keeps all physical Runtime-read/close and
            # original admission observation semantics; no alternate reader.
            original = await service.handle_frame({
                **frame, "schema": workspace.FRAME_SCHEMA_V3, "operation": "admitted_plan",
            })
            if permit(stamp) is None:
                return workspace.error("access_denied", 403)
            if original.get("ok") is not True:
                response = original
            elif original["result"]["availability"] != "AVAILABLE":
                reason = "SOURCE_CHANGED" if "SOURCE_CHANGED" in original["result"]["reason_codes"] else "SOURCE_UNAVAILABLE"
                response = wire.unavailable(selected, reason)
            else:
                body = original["result"]
                policy = CooCyclePolicy.for_digest(body["plan"]["policy_sha"])
                projected = compose_autonomy_policy_read(body, policy)
                after_policy = CooCyclePolicy.for_digest(policy.policy_sha256)
                after = cache.snapshot()
                if (service.cache is not cache or service.runtime is not runtime
                        or service._bounded_runtime is not bounded_runtime
                        or policy.source_sha256 != after_policy.source_sha256
                        or policy.policy_sha256 != after_policy.policy_sha256
                        or not _same_source(before, after, _plan_validity_identity)):
                    response = wire.unavailable(selected, "SOURCE_CHANGED")
                elif not _qualified(after, selected):
                    response = wire.unavailable(selected, "SOURCE_UNAVAILABLE")
                else:
                    response = {"ok": True, "result": projected}
                    workspace.bounded_canonical(response, limit=wire.MAX_RESPONSE_BYTES - 1)
    except LookupError:
        response = workspace.error("selection_not_found", 404)
    except Exception:
        response = wire.unavailable(selected, "SOURCE_UNAVAILABLE")
    if permit(stamp) is None:
        return workspace.error("access_denied", 403)
    return response
