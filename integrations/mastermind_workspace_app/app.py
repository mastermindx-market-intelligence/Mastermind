"""integrations.mastermind_workspace_app.app — the fixed authenticated read edge.

Two Starlette sibling routes only:

* ``GET /workspace/programs/current`` — the current-programs observation.
* ``GET /workspace/mission/current?work_ref=WS:...&root_job_id=JOB-...`` —
  the current mission observation for one named worktree + root job.

Both routes share an identical envelope:

* Authenticate via :data:`integrations.mastermind_executive_app.app._authenticate`,
  which is the existing A1 ``JwtAuthenticator`` wiring for resource-policy
  RS256/JWKS bearer verification (the very same code path that
  ``/v1/tools/executive_state`` uses).
* Reject any non-empty request body by refusing the first non-empty chunk
  before the client is ever consulted.
* Reject unknown or duplicate query parameters, plus all raw-path alias
  spellings (encoded separators, duplicate slashes), and trailing-slash
  variants: the same defense profile BSC-E1 applies on its own routes.
* Verify the principal is the one the installed owner client permits.
* Send exactly one closed frame to the host-installed client
  (``config.client.request(frame)``) and translate its closed envelope back
  to a typed HTTP status without ever leaking internal exception text.

The module holds NO durable state, NO in-memory cache, NO token store, and
NO Runtime import — the canonical workspace read primitives live behind the
host-installed client; this file is a closed transport framing only.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import unquote

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_executive_app.app import _authenticate
from integrations.mastermind_workspace_app import contract

__all__ = ["WorkspaceAppConfig", "create_workspace_app"]


#: Marker bytes the raw-path fence must reject (mirrors BSC-E1 fence).
_SUSPICIOUS_RAW_PATH_MARKERS = (b"%2f", b"%5c", b"//")

#: HTTP status code → client envelope status mapping (closed vocabulary).
_ENVELOPE_STATUS_TO_HTTP: dict[int, int] = {400: 400, 403: 403, 404: 404, 503: 503}

#: Routes — fixed, full /workspace/... prefix preserved verbatim for parent
#: mounting at any depth.  No path parameters, no template substitution.
_PROGRAMS_ROUTE = "/workspace/programs/current"
_MISSION_ROUTE = "/workspace/mission/current"
_MISSION_QUERY_KEYS = frozenset({"work_ref", "root_job_id"})


def _envelope_response(envelope: Mapping[str, Any]) -> JSONResponse:
    """Translate one closed-client envelope into the only legal HTTP shape.

    On ``ok: True``, the HTTP body is the result dict itself (the contract's
    "exact result" rule — never the wrapper that encloses it).  On refusal,
    the HTTP body is the closed envelope the client returned verbatim, so
    callers see the same ``{ok, status, error}`` shape they sent.
    """

    if type(envelope) is not dict:
        return _refuse_json(503, "internal_error")
    ok = envelope.get("ok")
    if ok is True:
        if set(envelope) != {"ok", "result"}:
            return _refuse_json(503, "internal_error")
        result = envelope.get("result")
        if not isinstance(result, Mapping):
            return _refuse_json(503, "internal_error")
        try:
            body = contract.bounded_canonical(dict(result))
        except (TypeError, ValueError):
            return _refuse_json(503, "source_unavailable")
        status = 503 if result.get("schema") == contract.PROGRAMS_SCHEMA and result.get("availability") == "UNAVAILABLE" else 200
        return Response(body, status_code=status, media_type="application/json", headers={"Cache-Control": "no-store"})
    if ok is False:
        if set(envelope) != {"ok", "status", "error"}:
            return _refuse_json(503, "internal_error")
        error_obj = envelope.get("error")
        status = envelope.get("status")
        if (type(error_obj) is not dict or set(error_obj) != {"code", "message"}
                or error_obj.get("code") not in {"invalid_input", "access_denied", "selection_not_found", "source_unavailable", "internal_error"}
                or type(status) is not int):
            return _refuse_json(503, "internal_error")
        try:
            status_code = int(status)
        except (TypeError, ValueError):
            return _refuse_json(503, "internal_error")
        http_status = _ENVELOPE_STATUS_TO_HTTP.get(status_code)
        if http_status is None:
            return _refuse_json(503, "internal_error")
        return JSONResponse(
            {"ok": False, "error": {"code": error_obj["code"], "message": "workspace read refused"}},
            status_code=http_status,
            headers={"Content-Type": "application/json", "Cache-Control": "no-store"},
        )
    return _refuse_json(503, "internal_error")


def _refuse_json(status: int, code: str) -> JSONResponse:
    """One closed HTTP refusal with no leakage of dependency detail."""

    return JSONResponse(
        {"ok": False, "error": {"code": code, "message": "workspace read refused"}},
        status_code=_ENVELOPE_STATUS_TO_HTTP.get(status, 503),
        headers={"Content-Type": "application/json", "Cache-Control": "no-store"},
    )


def _decode_query(query_string: bytes) -> dict[str, str]:
    """Decode one ASGI ``query_string`` into a single-occurrence dict.

    Percent-decodes both key and value.  Rejects duplicates and any
    percent-encoding that fails to decode cleanly.  Does NOT touch the
    raw-path / encoded-separator fence — that lives in :class:`_RawPathFence`,
    so ``?work_ref=WS%3AAB12cd`` (colon percent-encoded) is fine, while
    ``/path%2Fother`` (slash percent-encoded in the path) is not.
    """
    if not query_string:
        return {}
    if len(query_string) > contract.MAX_REQUEST_BYTES:
        return {"__invalid__": True}
    try:
        decoded = query_string.decode("ascii")
    except UnicodeDecodeError:
        return {"__invalid__": True}  # type: ignore[dict-item]
    parsed_raw: list[tuple[str, str]] = []
    for pair in decoded.split("&"):
        if not pair:
            return {"__invalid__": True}
        try:
            if "=" in pair:
                raw_key, raw_value = pair.split("=", 1)
            else:
                raw_key, raw_value = pair, ""
            key = unquote(raw_key.replace("+", " "))
            value = unquote(raw_value.replace("+", " "))
        except (ValueError, UnicodeDecodeError):
            return {"__invalid__": True}  # type: ignore[dict-item]
        parsed_raw.append((key, value))
    result: dict[str, str] = {}
    for key, value in parsed_raw:
        if key in result:
            return {"__invalid__": True}  # type: ignore[dict-item]
        result[key] = value
    return result


def _mission_selection(query: Mapping[str, str]) -> tuple[dict[str, str] | None, bool]:
    """Validate the mission route's query string exactly.

    Returns ``(selection, ok)``.  When ``ok`` is False the request refuses
    400; ``selection`` is None for the empty / no-keys cases (which is also
    a 400 because the mission endpoint requires both keys).
    """
    invalid = query.get("__invalid__") is True
    if invalid:
        return None, False
    keys = set(query)
    if keys != _MISSION_QUERY_KEYS:
        return None, False
    return {"work_ref": query["work_ref"], "root_job_id": query["root_job_id"]}, True


@dataclasses.dataclass(frozen=True)
class WorkspaceAppConfig:
    """One host-closed configuration bundle for the workspace read app.

    Every field is operator-supplied; none is read from a request.  The
    constructor rigidly enforces the closed binding between the
    :class:`JwtAuthenticator` policy and :mod:`contract`'s resource / scope:
    a different ``resource`` or different ``required_scopes`` is refused at
    construction so the edge cannot be instantiated with the wrong policy.
    """

    authenticator: JwtAuthenticator
    now: Callable[[], int] = dataclasses.field(default=lambda: int(time.time()))
    authorize_principal: Callable[[VerifiedPrincipal], bool] | None = None
    client: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.authenticator, JwtAuthenticator):
            raise ValueError("authenticator must be a JwtAuthenticator")
        if self.now is None or not callable(self.now):
            raise ValueError("now must be a callable returning an int second")
        if self.authorize_principal is None or not callable(self.authorize_principal):
            raise ValueError("authorize_principal must be callable")
        if self.client is None or not callable(getattr(self.client, "request", None)):
            raise ValueError("client must expose an async request(frame) method")
        if not inspect.iscoroutinefunction(getattr(self.client, "request", None)):
            raise ValueError("client.request must be a coroutine function")
        # Revalidate the authenticator's policy first — a frozen dataclass can
        # still be substituted or low-level mutated, and the wiring contract
        # below requires the immutable ResourcePolicy it claims to bind.
        from integrations.business_mcp_auth.contracts import validate_resource_policy

        try:
            policy = validate_resource_policy(self.authenticator.policy)
        except Exception as exc:
            raise ValueError(f"authenticator policy refused: {exc}") from exc
        if policy.resource != contract.RESOURCE:
            raise ValueError(
                f"authenticator resource {policy.resource!r} does not equal "
                f"contract.RESOURCE {contract.RESOURCE!r}"
            )
        if tuple(policy.required_scopes) != (contract.SCOPE,):
            raise ValueError(
                f"authenticator required_scopes {tuple(policy.required_scopes)!r} "
                f"does not equal ({contract.SCOPE!r},)"
            )


async def _reject_any_body(request: Request) -> JSONResponse | None:
    """Refuse on the first non-empty body chunk, BEFORE the client is read.

    Returns the refusal JSONResponse (caller sends + returns), or None.
    Only an empty body (or no body) is permitted; chunked transfer or any
    non-empty payload - including a stray single byte - is a 400.
    """
    received_nonempty = False
    try:
        async for chunk in request.stream():
            if chunk:
                return _refuse_json(400, "invalid_input")
    except Exception:
        # A malformed stream counts as a body present, refusing as 400.
        return _refuse_json(400, "invalid_input")
    if received_nonempty:
        return _refuse_json(400, "invalid_input")
    return None


def _check_authorize(
    authorize_principal: Callable[[VerifiedPrincipal], bool], principal: VerifiedPrincipal,
) -> JSONResponse | None:
    """Return None iff the installed owner client permits this principal."""
    try:
        permitted = authorize_principal(principal) is True
    except Exception:
        return _refuse_json(503, "internal_error")
    if not permitted:
        return _refuse_json(403, "access_denied")
    return None


async def programs_current(
    request: Request, *, config: WorkspaceAppConfig,
) -> JSONResponse:
    """Handle ``GET /workspace/programs/current``.

    Sequence (each stage refuses before the next runs):

    1. Authenticate the bearer via the shared ``_authenticate`` (any failure
       here is an existing A1 error envelope).
    2. Refuse a non-empty body.
    3. The programs endpoint carries no selection; any query string is 400.
    4. Reject unless the installed owner client permits the principal.
    5. Build and validate the closed frame; dispatch via ``client.request``.
    6. Recheck the bearer ``expires_at`` against ``config.now()`` and the
       installed owner permission once more before returning the client
       envelope — a permission revocation or clock expiry that happens
       during the read produces a 403, never an unauthorized disclosure.
    """
    principal_or_response = await _authenticate(
        request, config.authenticator, clock=config.now,
    )
    if isinstance(principal_or_response, JSONResponse):
        # Re-attach the canonical Cache-Control so an A1 refusal is
        # never cached. _authenticate leaves its own (correct) status code.
        return _with_no_store(principal_or_response)
    principal = principal_or_response

    body_response = await _reject_any_body(request)
    if body_response is not None:
        return body_response

    raw_query = request.scope.get("query_string") or b""
    if raw_query:
        return _refuse_json(400, "invalid_input")

    permit = _check_authorize(config.authorize_principal, principal)
    if permit is not None:
        return permit

    try:
        permission_before = contract.permission_stamp(config.authorize_principal, principal)
        principal_frame = contract.principal_frame(principal)
    except ValueError:
        return _refuse_json(403, "access_denied")

    try:
        frame = contract.validate_frame({
            "schema": contract.FRAME_SCHEMA,
            "operation": "programs",
            "selection": None,
            "principal": principal_frame,
        })
    except ValueError:
        return _refuse_json(400, "invalid_input")

    try:
        envelope = await config.client.request(frame)
    except Exception:
        # Cancellation or any other request-stage exception: a closed 503,
        # never a leaked traceback.  Note: ``asyncio.CancelledError`` is a
        # ``BaseException`` subclass on Python 3.8+; this branch will NOT
        # catch it, so it propagates upwards and cancels this task cleanly.
        return _refuse_json(503, "internal_error")

    try:
        instant = config.now()
        if type(instant) is not int or instant >= principal.expires_at:
            return _refuse_json(403, "access_denied")
    except Exception:
        return _refuse_json(503, "internal_error")

    permit_after = _check_authorize(config.authorize_principal, principal)
    if permit_after is not None:
        return permit_after

    try:
        if contract.permission_stamp(config.authorize_principal, principal) != permission_before:
            return _refuse_json(403, "access_denied")
    except Exception:
        return _refuse_json(403, "access_denied")
    return _envelope_response(envelope)


async def mission_current(
    request: Request, *, config: WorkspaceAppConfig,
) -> JSONResponse:
    """Handle ``GET /workspace/mission/current?work_ref=WS:...&root_job_id=JOB-...``.

    Same envelope as :func:`programs_current`; selection parsed and
    validated through :func:`contract.selection` exactly once, here, before
    any client call.
    """
    principal_or_response = await _authenticate(
        request, config.authenticator, clock=config.now,
    )
    if isinstance(principal_or_response, JSONResponse):
        return _with_no_store(principal_or_response)
    principal = principal_or_response

    body_response = await _reject_any_body(request)
    if body_response is not None:
        return body_response

    raw_query: bytes = request.scope.get("query_string") or b""
    if not raw_query:
        return _refuse_json(400, "invalid_input")
    parsed_query = _decode_query(raw_query)
    selection_value, ok = _mission_selection(parsed_query)
    if not ok:
        return _refuse_json(400, "invalid_input")
    assert selection_value is not None

    permit = _check_authorize(config.authorize_principal, principal)
    if permit is not None:
        return permit

    try:
        permission_before = contract.permission_stamp(config.authorize_principal, principal)
        principal_frame = contract.principal_frame(principal)
    except ValueError:
        return _refuse_json(403, "access_denied")

    try:
        frame = contract.validate_frame({
            "schema": contract.FRAME_SCHEMA,
            "operation": "mission",
            "selection": contract.selection(selection_value),
            "principal": principal_frame,
        })
    except ValueError:
        return _refuse_json(400, "invalid_input")

    try:
        envelope = await config.client.request(frame)
    except Exception:
        return _refuse_json(503, "internal_error")

    try:
        instant = config.now()
        if type(instant) is not int or instant >= principal.expires_at:
            return _refuse_json(403, "access_denied")
    except Exception:
        return _refuse_json(503, "internal_error")

    permit_after = _check_authorize(config.authorize_principal, principal)
    if permit_after is not None:
        return permit_after

    try:
        if contract.permission_stamp(config.authorize_principal, principal) != permission_before:
            return _refuse_json(403, "access_denied")
    except Exception:
        return _refuse_json(403, "access_denied")
    return _envelope_response(envelope)


def _with_no_store(response: JSONResponse) -> JSONResponse:
    """Attach the canonical ``Cache-Control: no-store`` to an A1 JSONResponse
    in place.  Starlette's :class:`MutableHeaders` supports in-place update,
    so we never rebuild the response body."""

    response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("content-type", "application/json")
    return response


class _RawPathFence:
    """ASGI wrapper refusing any HTTP request whose raw path bytes contain an
    encoded/alternate separator or whose method is not GET, before routing
    or authentication ever runs.  Mirrors BSC-E1's profile exactly.
    """

    #: Starlette auto-binds HEAD alongside GET; we explicitly refuse it so
    #: a non-GET method never reaches authentication, validating the
    #: closed-method surface the workspace contract requires.
    _ALLOWED_METHODS = frozenset({"GET"})

    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(self, scope: Mapping[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            raw_path = scope.get("raw_path") or b""
            lowered = bytes(raw_path).lower()
            if b"%" in lowered or any(marker in lowered for marker in _SUSPICIOUS_RAW_PATH_MARKERS):
                response = JSONResponse(
                    {"ok": False, "status": 400,
                     "error": {"code": "invalid_input",
                               "message": "path contains an unsupported encoded separator"}},
                    status_code=400,
                    headers={"Cache-Control": "no-store", "Content-Type": "application/json"},
                )
                await response(scope, receive, send)
                return
            method = str(scope.get("method") or "").upper()
            path = scope.get("path") or ""
            if method not in self._ALLOWED_METHODS and (path == _PROGRAMS_ROUTE or path == _MISSION_ROUTE):
                response = JSONResponse(
                    {"ok": False, "status": 405,
                     "error": {"code": "not_found",
                               "message": "method not allowed"}},
                    status_code=405,
                    headers={"Cache-Control": "no-store", "Content-Type": "application/json", "Allow": "GET"},
                )
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)


def create_workspace_app(config: WorkspaceAppConfig) -> Any:
    """Build the closed, fixed authenticated workspace read app."""

    async def programs_endpoint(request: Request) -> JSONResponse:
        return await programs_current(request, config=config)

    async def mission_endpoint(request: Request) -> JSONResponse:
        return await mission_current(request, config=config)

    routes = [
        Route(_PROGRAMS_ROUTE, programs_endpoint, methods=["GET"]),
        Route(_MISSION_ROUTE, mission_endpoint, methods=["GET"]),
    ]
    application = Starlette(routes=routes)
    # Never silently rewrite a trailing-slash alias onto a different route:
    # an encoded/trailing-slash/raw-path ambiguity must refuse as a plain
    # 404 (trailing slash) or 400 (encoded separator), never be silently
    # redirected before auth has even run.
    application.router.redirect_slashes = False
    return _RawPathFence(application)
