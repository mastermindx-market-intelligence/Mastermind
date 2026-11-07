"""Existing Workspace READ composition for ModelRouter configuration.

Configured aliases/routes only: no lease, account, token, provider request,
Runtime operation, selection override or activation authority is created.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from common import workspace_model_configuration_contract as wire
from common.executive_workspace_contract import error
from control_plane.model_router_configuration import ConfigurationError, load_configuration
from control_plane.workspace_read_service import await_owned, permission_stamp


def read_model_configuration():
    try:
        # Exactly the existing backend ModelRouter's source selection. No model,
        # browser, request or principal supplies a policy path or capability root.
        configuration = load_configuration()
        body = {
            "schema": wire.BODY_SCHEMA, "availability": "AVAILABLE",
            "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_owner": "model_router", "reason_codes": [],
            "configuration": configuration,
        }
        return {"ok": True, "result": wire.validate_result(body)}
    except ConfigurationError as exc:
        reason = ("SOURCE_CHANGED" if str(exc) in {
            "CONFIGURATION_CHANGED_DURING_READ", "CAPABILITY_POLICY_CHANGED_DURING_READ"
        } else "SOURCE_UNAVAILABLE")
        return wire.unavailable(reason)
    except Exception:
        return wire.unavailable()


async def handle_model_configuration_frame(owner, frame):
    try:
        wire.validate_frame(frame)
    except (TypeError, ValueError):
        return error("invalid_input", 400)
    principal = frame["principal"]
    authorizer = owner.authorize
    try:
        if authorizer(principal) is not True:
            return error("access_denied", 403)
        stamp = permission_stamp(authorizer, principal)
        if stamp is None:
            return error("access_denied", 403)
    except Exception:
        return error("access_denied", 403)
    task = asyncio.create_task(asyncio.to_thread(read_model_configuration))
    try:
        response = await await_owned(task)
    except Exception:
        response = wire.unavailable()
    try:
        if (owner.authorize is not authorizer or authorizer(principal) is not True
                or permission_stamp(authorizer, principal) != stamp):
            return error("access_denied", 403)
    except Exception:
        return error("access_denied", 403)
    return response
