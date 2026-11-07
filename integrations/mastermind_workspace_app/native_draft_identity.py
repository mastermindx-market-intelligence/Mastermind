"""Current Workspace principal observation for native in-memory draft privacy.

No project, Runtime, content, token or grant is returned. This existing READ
owner's observation is not an action capability or an Executive identity map.
The native owner independently binds this fixed response to the exact bearer
and auth generation used for the request; a caller JSON/event is never proof.
"""
from dataclasses import astuple
from http import HTTPStatus
from starlette.responses import JSONResponse
from .app import WorkspaceAppConfig, _authenticate, _reject_any_body, _refuse_json, _with_no_store
from .contract import permission_stamp
from .owner_context import workspace_principal_scope

ROUTE = "/workspace/native-draft-identity/current"
SCHEMA = "mastermind.native_draft_identity.v1"
MAX_RESPONSE_BYTES = 1024


async def native_draft_identity_current(request, *, config):
    if type(config) is not WorkspaceAppConfig:
        raise TypeError("existing Workspace owner required")
    if (request.method != "GET" or request.scope.get("raw_path", ROUTE.encode()) != ROUTE.encode()
            or request.scope.get("query_string")):
        return _with_no_store(_refuse_json(HTTPStatus.BAD_REQUEST, "invalid_input"))
    authenticator, authorize, clock = config.authenticator, config.authorize_principal, config.now
    policy, policy_state = authenticator.policy, astuple(authenticator.policy)
    principal = await _authenticate(request, authenticator, clock=clock)
    if isinstance(principal, JSONResponse):
        return _with_no_store(principal)

    def current():
        now = clock()
        if (config.authenticator is not authenticator or config.authorize_principal is not authorize
                or config.now is not clock or authenticator.policy is not policy or astuple(policy) != policy_state
                or type(now) is not int or not principal.issued_at <= now < principal.expires_at
                or authorize(principal) is not True):
            raise ValueError("access_denied")
        stamp = permission_stamp(authorize, principal)
        if stamp is None:
            raise ValueError("access_denied")
        return stamp
    try:
        before = current()
        refused = await _reject_any_body(request)
        if refused is not None:
            return _with_no_store(refused)
        if current() != before:
            raise ValueError("access_denied")
        expires = principal.expires_at * 1000
        if type(expires) is not int or not 1 <= expires <= 8_640_000_000_000_000:
            raise ValueError("access_denied")
        body = {"schema": SCHEMA, "principal_scope": workspace_principal_scope(principal), "expires_at_ms": expires}
        if current() != before:
            raise ValueError("access_denied")
        return JSONResponse(body, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
    except Exception:
        return _with_no_store(_refuse_json(HTTPStatus.FORBIDDEN, "access_denied"))
