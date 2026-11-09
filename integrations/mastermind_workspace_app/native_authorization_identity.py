"""Fixed metadata-only identity observations over incumbent READ owners.

No token, source body, grant, subject, selector or identity store is returned.
The comparable result is native-only data, never a continuation/action grant.
"""
from dataclasses import astuple
import asyncio
from starlette.responses import JSONResponse
from starlette.routing import Route
from common import native_authorization_identity_contract as wire
from integrations.business_mcp_auth.contracts import VerifiedPrincipal

ORIGIN = "https://mcp.mastermind-x.com"

def _response(status, body):
    return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})

def _request_valid(request, kind):
    scope = request.scope
    headers = scope.get("headers", [])
    if (scope.get("type") != "http" or scope.get("method") != "GET"
        or scope.get("scheme") != "https" or scope.get("root_path")
        or scope.get("raw_path") != wire.ROUTES[kind].encode("ascii")
        or scope.get("path") != wire.ROUTES[kind] or scope.get("query_string")
        or type(headers) not in (list, tuple) or len(headers) > 32):
        return False
    found = {}
    for pair in headers:
        if (type(pair) not in (list, tuple) or len(pair) != 2
            or not all(type(v) is bytes for v in pair) or len(pair[1]) > 17000):
            return False
        name, value = pair[0].lower(), pair[1]
        found.setdefault(name, []).append(value)
    if (found.get(b"host") != [b"mcp.mastermind-x.com"]
        or len(found.get(b"authorization", [])) != 1
        or len(found.get(b"origin", [])) > 1
        or found.get(b"origin", [ORIGIN.encode()]) != [ORIGIN.encode()]
        or found.get(b"content-length", [b"0"]) != [b"0"]
        or b"transfer-encoding" in found):
        return False
    return True

async def _empty_body(request):
    async def read():
        count = 0
        async for chunk in request.stream():
            count += 1
            if chunk or count > 8:
                return False
        return True
    try:
        return await asyncio.wait_for(read(), 2) is True
    except Exception:
        return False

def _principal_body(principal, kind):
    if type(principal) is not VerifiedPrincipal or principal.resource != wire.RESOURCES[kind]:
        raise ValueError("identity_unavailable")
    return wire.validate_body({"schema": wire.SCHEMA, "resource": kind,
        "account_digest": wire.comparable_account_digest(principal.issuer_digest,
            principal.subject_digest, principal.client_ref),
        "expires_at_ms": principal.expires_at * 1000}, kind)

async def acquisition_identity_current(request, *, config):
    from .app import WorkspaceAppConfig, _authenticate
    from .contract import permission_stamp
    if type(config) is not WorkspaceAppConfig:
        raise TypeError("existing Workspace owner required")
    kind = "ACQUISITION"
    if not _request_valid(request, kind):
        return _response(400, {"error": "invalid_input"})
    authenticator, authorize, clock = config.authenticator, config.authorize_principal, config.now
    policy = authenticator.policy
    policy_state = astuple(policy)
    principal = await _authenticate(request, authenticator, clock=clock)
    if isinstance(principal, JSONResponse):
        principal.headers["Cache-Control"] = "no-store"
        return principal
    def current():
        now = clock()
        if (config.authenticator is not authenticator or config.authorize_principal is not authorize
            or config.now is not clock or authenticator.policy is not policy or astuple(policy) != policy_state
            or type(now) is not int or not principal.issued_at <= now < principal.expires_at
            or authorize(principal) is not True):
            raise ValueError("identity_unavailable")
        stamp = permission_stamp(authorize, principal)
        if stamp is None:
            raise ValueError("identity_unavailable")
        return stamp
    try:
        before = current()
        if not await _empty_body(request):
            return _response(400, {"error": "invalid_input"})
        body = _principal_body(principal, kind)
        if current() != before:
            raise ValueError("identity_unavailable")
        return _response(200, body)
    except Exception:
        return _response(403, {"error": "identity_unavailable"})

def content_identity_endpoint(reader):
    """Only an actual Business JWT/current-source owner can issue this route."""
    from integrations.mastermind_window_reader.owner_read_resource import _content_identity_reader
    read = _content_identity_reader(reader)
    async def endpoint(request):
        if not _request_valid(request, "CONTENT"):
            return _response(400, {"error": "invalid_input"})
        try:
            header = request.headers["authorization"]
            before = await asyncio.wait_for(read(header), reader._timeout)
            if not await _empty_body(request):
                return _response(400, {"error": "invalid_input"})
            after = await asyncio.wait_for(read(header), reader._timeout)
            if before != after:
                raise ValueError("identity_unavailable")
            return _response(200, wire.validate_body(after[0], "CONTENT"))
        except Exception:
            return _response(403, {"error": "identity_unavailable"})
    return endpoint

def identity_routes(*, acquisition_config, content_reader):
    """Additive two-route composition, no mounting/enrollment side effect.

    Requires both actual owners; there is no default content permission and no
    caller-selected resource. Existing S35 v1 response/path are untouched.
    """
    from .app import WorkspaceAppConfig
    if type(acquisition_config) is not WorkspaceAppConfig:
        raise TypeError("existing Workspace owner required")
    content = content_identity_endpoint(content_reader)
    async def acquisition(request):
        return await acquisition_identity_current(request, config=acquisition_config)
    return [Route(wire.ROUTES["ACQUISITION"], acquisition, methods=["GET"]),
            Route(wire.ROUTES["CONTENT"], content, methods=["GET"])]


def content_identity_app(reader):
    """ASGI adapter only for the nominal fixed Content owner above."""
    from starlette.requests import Request
    endpoint = content_identity_endpoint(reader)
    async def app(scope, receive, send):
        response = await endpoint(Request(scope, receive))
        await response(scope, receive, send)
    return app
