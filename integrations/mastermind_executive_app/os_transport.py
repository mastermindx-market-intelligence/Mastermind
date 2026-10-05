"""Fixed, authenticated HTTP bridge to the installed v3 App operations.

The outer host verifies first and forwards the original bearer. This adapter
never decodes JWTs, stores credentials, injects a principal into ASGI state,
changes routes, or selects the inner tool from request data.  A committed
submit whose response is lost stays the original request's ``effect_unknown``;
a status failure is never settlement and never mints a new operation.

* The same exact ``MastermindTokenVerifier`` pair and matching
  ``JwtAuthenticator`` already used by the existing v3 composition is reused
  here.  No read fallback, no workspace/read/extra-authority verifier.
* Body bytes are received under a 65,536 byte ceiling AND a 5 second receive
  deadline.  Malformed JSON, malformed bearer, audit failures, and verifier
  exceptions all close the request with a non-cacheable refusal.
* ``http.response.start`` is consumed exactly once, body frames are appended
  up to a cumulative 262,144 byte ceiling, completion is observed only on
  the final body frame.  Out-of-order or post-completion events refuse.
* After the inner awaits, the original bearer and exact
  :class:`VerifiedPrincipal` are re-verified through the audited verifier.
  Expiry, identity, or audit drift withholds context and status responses;
  submit after a possible effect returns the SAME original ``request_ref``
  ``effect_unknown`` and never changes the operation key.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections.abc import Awaitable, Callable, Mapping
from http import HTTPStatus
from typing import Any

from starlette.responses import JSONResponse, Response

from integrations.business_mcp_auth.contracts import (
    AuthError,
    AuthErrorCode,
    VerifiedPrincipal,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.executive_mcp.e1_http import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
)
from integrations.mastermind_executive_app.admission import (
    AdmissionOutcome,
    STATUS_EFFECT_UNKNOWN,
)


#: All responses from the OS Executive transport carry this fixed set of
#: headers; nothing in this module sets ``Cache-Control`` to anything else.
_OS_HTTP_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}

#: Closed owner-context schema.  Server version is carried by the v3 profile
#: qualifier, not by this schema's identifier.
_CONTEXT_SCHEMA = "mastermind.os.executive.owner_context.v1"
#: Domain separation prefix for the documented, stable owner namespace.
_NAMESPACE_SCOPE = b"mastermind.os.executive.principal_scope.v1"

#: Receive deadline for one bounded body.  Mirrors e1_http for symmetry.
RECEIVE_DEADLINE_SECONDS = 5.0
#: Maximum body frames accepted on the wire before refusing.
_MAX_BODY_FRAMES = 32


class _ReceiveTimeout(Exception):
    """Receive deadline elapsed before a complete body arrived."""


class _InvalidBody(Exception):
    """Body failed closed-form validation."""


class _NoStoreRefusal(Exception):
    """Bearer, verifier, or audit failure; transport closes without cache."""


# ---------------------------------------------------------------------------
# request body: bounded streaming, strict JSON
# ---------------------------------------------------------------------------


async def _bounded_receive_body(
    receive: Callable[[], Awaitable[Mapping[str, Any]]],
    *,
    deadline_seconds: float,
) -> bytes:
    """Stream the body up to MAX_REQUEST_BYTES with a receive deadline.

    A duplicate header, a malformed JSON-RPC frame, or a non-finite number
    inside the body all close as invalid-input; the closed vocabulary is
    the same ``invalid_input`` code the existing app uses.
    """

    body = bytearray()
    total = 0
    frames = 0
    deadline = asyncio.get_running_loop().time() + deadline_seconds
    try:
        while True:
            try:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise asyncio.TimeoutError
                event = await asyncio.wait_for(receive(), timeout=remaining)
            except asyncio.TimeoutError as exc:
                raise _ReceiveTimeout() from exc
            event_type = event.get("type")
            if event_type == "http.disconnect":
                raise _InvalidBody("body was disconnected")
            if event_type != "http.request":
                raise _InvalidBody("body event was not http.request")
            frames += 1
            if frames > _MAX_BODY_FRAMES:
                raise _InvalidBody("body frames exceed the transport budget")
            chunk = event.get("body", b"")
            if not isinstance(chunk, (bytes, bytearray)):
                raise _InvalidBody("body chunk is not bytes")
            total += len(chunk)
            if total > MAX_REQUEST_BYTES:
                raise _InvalidBody("body exceeds 65536 bytes")
            body.extend(chunk)
            if not event.get("more_body", False):
                return bytes(body)
    finally:
        pass


def _parse_body(raw: bytes) -> dict[str, Any]:
    """Strict JSON: no duplicate keys, no non-finite numbers, top-level dict."""

    if not raw:
        raise _InvalidBody("body is empty")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _InvalidBody("body is not utf-8") from exc

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: set[str] = set()
        result: dict[str, Any] = {}
        for key, value in items:
            if key in seen:
                raise _InvalidBody("body contains duplicate key")
            seen.add(key)
            result[key] = value
        return result

    def reject_constant(_value: str) -> Any:
        raise _InvalidBody("body contains non-finite number")

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)
    except (ValueError, TypeError) as exc:
        raise _InvalidBody("body is not json") from exc
    _walk_nonfinite(value)
    if not isinstance(value, dict):
        raise _InvalidBody("body is not a json object")
    return value


def _walk_nonfinite(value: Any) -> None:
    pending: list[Any] = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, float) and not math.isfinite(current):
            raise _InvalidBody("body contains non-finite number")
        if isinstance(current, dict):
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)


# ---------------------------------------------------------------------------
# bearer extraction (closed form, never a request body field)
# ---------------------------------------------------------------------------


def _bearer_token(header_value: bytes) -> str:
    try:
        text = header_value.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise _NoStoreRefusal("malformed bearer") from exc
    if " " not in text:
        raise _NoStoreRefusal("malformed bearer")
    scheme, token = text.split(" ", 1)
    if scheme.lower() != "bearer":
        raise _NoStoreRefusal("malformed bearer")
    if not token or any(character.isspace() for character in token):
        raise _NoStoreRefusal("malformed bearer")
    try:
        token.encode("ascii", errors="strict")
    except UnicodeEncodeError as exc:
        raise _NoStoreRefusal("malformed bearer") from exc
    return token


def principal_scope(principal: VerifiedPrincipal) -> str:
    """Derive the one documented, stable, opaque owner namespace."""

    material = b"\0".join((
        _NAMESPACE_SCOPE,
        principal.issuer_digest.encode("ascii"),
        principal.subject_digest.encode("ascii"),
        principal.client_ref.encode("utf-8"),
        principal.resource.encode("utf-8"),
    ))
    return hashlib.sha256(material).hexdigest()


def _access_matches_principal(
    access: Any, principal: VerifiedPrincipal
) -> bool:
    """Require the audited AccessToken to match the actual VerifiedPrincipal.

    ``client_id``, ``scopes``, ``expires_at``, ``resource``, ``subject``, and
    the closed claim dict ``issuer_digest`` / ``client_ref`` / ``jti_digest``
    must all equal the values the inner :class:`JwtAuthenticator` derived
    from the same exact token.
    """

    claims = access.claims if isinstance(access.claims, Mapping) else {}
    return (
        access.client_id == principal.client_ref
        and tuple(access.scopes) == tuple(principal.scopes)
        and access.expires_at == principal.expires_at
        and access.resource == principal.resource
        and access.subject == principal.subject_digest
        and claims.get("issuer_digest") == principal.issuer_digest
        and claims.get("client_ref") == principal.client_ref
        and claims.get("jti_digest") == principal.jti_digest
    )


# ---------------------------------------------------------------------------
# ASGI event collection: bounded response envelope
# ---------------------------------------------------------------------------


class _CollectError(Exception):
    """The inner ASGI emit an invalid or oversize event."""


async def _drive_inner(
    inner_app: Any,
    inner_scope: Mapping[str, Any],
    replay_body: bytes,
) -> tuple[dict[str, Any], bytes]:
    """Drive ``inner_app`` once with a replayed ``http.request`` body and
    collect exactly one ``start`` and the body frames.

    The call completes only when the final body frame arrives (its
    ``more_body`` is False).  A second ``start``, a body frame before
    ``start``, an oversize cumulative body, or any event after the final
    frame raises :class:`_CollectError`.
    """

    start: dict[str, Any] | None = None
    body = bytearray()
    total = 0
    complete = False
    replayed = False

    async def replay_receive() -> Mapping[str, Any]:
        nonlocal replayed
        if not replayed:
            replayed = True
            return {"type": "http.request", "body": replay_body, "more_body": False}
        return {"type": "http.disconnect"}

    async def collect(event: Mapping[str, Any]) -> None:
        nonlocal start, body, total, complete
        event_type = event.get("type")
        if event_type == "http.response.start":
            if start is not None or complete:
                raise _CollectError("duplicate or post-final start")
            if not isinstance(event.get("status"), int) or not isinstance(event.get("headers"), list):
                raise _CollectError("malformed start")
            start = {
                "status": int(event["status"]),
                "headers": list(event["headers"]),
            }
            return
        if event_type == "http.response.body":
            if start is None:
                raise _CollectError("body frame before start")
            if complete:
                raise _CollectError("body frame after completion")
            chunk = event.get("body", b"")
            if not isinstance(chunk, (bytes, bytearray)):
                raise _InvalidBody("body chunk is not bytes")
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise _CollectError("body exceeds 262144 bytes")
            body.extend(chunk)
            if not event.get("more_body", False):
                complete = True
            return
        if event_type == "http.response.trailers":
            raise _CollectError("trailers not permitted")
        raise _CollectError("unrecognised response event")

    await asyncio.wait_for(inner_app(inner_scope, replay_receive, collect), timeout=5.0)
    if start is None or not complete:
        raise _CollectError("inner response did not complete")
    return start, bytes(body)


# ---------------------------------------------------------------------------
# dispatch: context, submit, status
# ---------------------------------------------------------------------------


def _context_payload(principal: VerifiedPrincipal) -> dict[str, Any]:
    from integrations.executive_mcp.web_ceo_v3 import (
        WEB_CEO_V3_PROFILE,
        WEB_CEO_V3_SERVER_VERSION,
    )
    return {
        "schema": _CONTEXT_SCHEMA,
        "principal_scope": principal_scope(principal),
        "verified_expiry": principal.expires_at,
        "profile": {
            "name": WEB_CEO_V3_PROFILE,
            "server_version": WEB_CEO_V3_SERVER_VERSION,
        },
    }


def _unknown_outcome(request_ref: str) -> dict[str, Any]:
    from control_plane.ceo_request import automated_intent_id
    from integrations.mastermind_executive_app.app import _outcome_response
    intent_id = automated_intent_id(request_ref)
    response = _outcome_response(AdmissionOutcome(
        status=STATUS_EFFECT_UNKNOWN,
        request_ref=request_ref,
        code="effect_unknown",
        message=(
            "the Executive response is unavailable; read ceo_intent_status "
            f"with intent_id={intent_id} for this original request. "
            "A not_found response does not authorize resubmission. "
            "Preserve request_ref and require canonical reconciliation "
            "before any further submission."
        ),
    ))
    return json.loads(response.body)


class OsExecutiveTransportApp:
    """The three fixed OS routes around the exact BoundedE1App instance."""

    ROUTES: tuple[str, ...] = (
        "/os/executive/context",
        "/os/executive/submit",
        "/os/executive/status",
    )

    def __init__(
        self,
        inner_app: Any,
        *,
        submit_verifier: MastermindTokenVerifier | tuple[MastermindTokenVerifier, ...],
        submit_authenticator: JwtAuthenticator | tuple[JwtAuthenticator, ...],
        clock: Callable[[], int],
        commission_preparer: Any | None = None,
    ) -> None:
        verifiers = submit_verifier if isinstance(submit_verifier, tuple) else (submit_verifier,)
        if not verifiers or any(type(v) is not MastermindTokenVerifier for v in verifiers):
            raise TypeError("audited submit MastermindTokenVerifier required")
        if not (isinstance(submit_authenticator, JwtAuthenticator)
                or (isinstance(submit_authenticator, tuple)
                    and submit_authenticator
                    and all(isinstance(item, JwtAuthenticator) for item in submit_authenticator))):
            raise TypeError("submit JwtAuthenticator (or tuple thereof) required")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._inner_app = inner_app
        authenticators = submit_authenticator if isinstance(submit_authenticator, tuple) else (submit_authenticator,)
        if len(verifiers) != len(authenticators) or any(
            frozenset(a.policy.required_scopes) != frozenset(("mastermind.executive.read", "mastermind.executive.intent.submit"))
            for a in authenticators
        ):
            raise ValueError("exact Executive submit-policy pairs required")
        self._submit_verifiers = verifiers
        self._submit_authenticators = authenticators
        self._clock = clock
        from integrations.mastermind_executive_app.os_commission_client import StudioCommissionClient
        if commission_preparer is not None and type(commission_preparer) is not StudioCommissionClient:
            raise TypeError("installed Studio commission client required")
        self._commission_preparer = commission_preparer

    # ---------------------------------------------------------------- ASGI

    async def __call__(
        self,
        scope: Mapping[str, Any],
        receive: Callable[[], Awaitable[Mapping[str, Any]]],
        send: Callable[[Mapping[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self._inner_app(scope, receive, send)
            return
        path = scope.get("path", "")
        method = scope.get("method")
        raw_path = scope.get("raw_path")
        query_string = scope.get("query_string") or b""
        scheme = scope.get("scheme")
        if (
            method != "POST"
            or path not in self.ROUTES
            or not isinstance(raw_path, (bytes, bytearray))
            or bytes(raw_path) != path.encode("ascii")
            or query_string
            or scheme != "https"
        ):
            await Response(status_code=HTTPStatus.NOT_FOUND, headers=_OS_HTTP_HEADERS)(scope, receive, send)
            return

        headers = scope.get("headers") or ()
        hosts = [v for k, v in headers if k.lower() == b"host"]
        origins = [v for k, v in headers if k.lower() == b"origin"]
        authorizations = [v for k, v in headers if k.lower() == b"authorization"]
        if (
            hosts != [b"mcp.mastermind-x.com"]
            or len(origins) > 1
            or (origins and origins != [b"https://mcp.mastermind-x.com"])
            or len(authorizations) != 1
        ):
            await JSONResponse(
                {"ok": False, "error": {"code": "transport_refused",
                                         "message": "fixed OS transport refused"}},
                status_code=HTTPStatus.FORBIDDEN,
                headers=_OS_HTTP_HEADERS,
            )(scope, receive, send)
            return

        try:
            token = _bearer_token(bytes(authorizations[0]))
        except _NoStoreRefusal:
            await JSONResponse(
                {"ok": False, "error": {"code": "authentication_required",
                                         "message": "authentication required"}},
                status_code=HTTPStatus.UNAUTHORIZED,
                headers={**_OS_HTTP_HEADERS, "WWW-Authenticate": "Bearer"},
            )(scope, receive, send)
            return

        principal = await self._verified_binding(token)
        if principal is None:
            await JSONResponse(
                {"ok": False, "error": {"code": "authentication_required", "message": "authentication required"}},
                status_code=HTTPStatus.UNAUTHORIZED, headers={**_OS_HTTP_HEADERS, "WWW-Authenticate": "Bearer"},
            )(scope, receive, send)
            return

        try:
            raw = await _bounded_receive_body(receive, deadline_seconds=RECEIVE_DEADLINE_SECONDS)
        except _ReceiveTimeout:
            await JSONResponse(
                {"ok": False, "error": {"code": "invalid_input",
                                         "message": "body receive deadline exceeded"}},
                status_code=HTTPStatus.BAD_REQUEST,
                headers=_OS_HTTP_HEADERS,
            )(scope, receive, send)
            return
        except _InvalidBody as exc:
            await JSONResponse(
                {"ok": False, "error": {"code": "invalid_input",
                                         "message": str(exc) or "request body is invalid"}},
                status_code=HTTPStatus.BAD_REQUEST,
                headers=_OS_HTTP_HEADERS,
            )(scope, receive, send)
            return

        try:
            body_obj = _parse_body(raw)
        except _InvalidBody as exc:
            await JSONResponse(
                {"ok": False, "error": {"code": "invalid_input",
                                         "message": str(exc) or "request body is invalid"}},
                status_code=HTTPStatus.BAD_REQUEST,
                headers=_OS_HTTP_HEADERS,
            )(scope, receive, send)
            return

        if (path == "/os/executive/context" and body_obj) or (
            path != "/os/executive/context" and set(body_obj) != {"arguments"}
        ):
            await JSONResponse({"ok": False, "error": {"code": "invalid_input", "message": "fixed request body required"}},
                               status_code=HTTPStatus.BAD_REQUEST, headers=_OS_HTTP_HEADERS)(scope, receive, send)
            return

        # Revalidate the original bearer after each awaited operation before
        # releasing identity or effect evidence to the caller.
        try:
            response = await self._dispatch(path, scope, body_obj, principal)
        except _CollectError:
            response = JSONResponse(
                {"ok": False, "error": {"code": "backend_unavailable",
                                         "message": "Executive response is unavailable"}},
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                headers=_OS_HTTP_HEADERS,
            )
        except Exception:
            response = JSONResponse(
                {"ok": False, "error": {"code": "backend_unavailable",
                                         "message": "Executive response is unavailable"}},
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                headers=_OS_HTTP_HEADERS,
            )
        await response(scope, receive, send)

    # ---------------------------------------------------------------- helpers

    async def _verified_binding(self, token: str) -> VerifiedPrincipal | None:
        """Pair an audited AccessToken with its exact actual submit principal."""
        try:
            for verifier, authenticator in zip(self._submit_verifiers, self._submit_authenticators):
                access, code = await verifier.verify_token_with_code(token)
                if access is None:
                    if code == AuthErrorCode.RESOURCE_REFUSED:
                        continue
                    return None
                now = self._clock()
                if type(now) is not int:
                    return None
                principal = await authenticator.verify_token(token, now=now)
                if (type(principal) is VerifiedPrincipal and now < principal.expires_at
                        and _access_matches_principal(access, principal)):
                    return principal
                return None
        except Exception:
            return None
        return None

    async def _still_current(self, scope: Mapping[str, Any], principal: VerifiedPrincipal) -> bool:
        try:
            return await self._verified_binding(self._bearer_from_scope(scope)) == principal
        except Exception:
            return False

    async def _dispatch(
        self,
        path: str,
        scope: Mapping[str, Any],
        body_obj: dict[str, Any],
        principal: VerifiedPrincipal,
    ) -> Response:
        if path == "/os/executive/context":
            if not await self._still_current(scope, principal):
                return JSONResponse({"ok": False, "error": {"code": "identity_unverified", "message": "context authorization changed"}}, status_code=HTTPStatus.UNAUTHORIZED, headers=_OS_HTTP_HEADERS)
            return JSONResponse(_context_payload(principal), status_code=HTTPStatus.OK,
                                headers=_OS_HTTP_HEADERS)
        if path == "/os/executive/submit":
            return await self._dispatch_submit(scope, body_obj, principal)
        return await self._dispatch_status(scope, body_obj, principal)

    async def _dispatch_submit(
        self,
        scope: Mapping[str, Any],
        body_obj: dict[str, Any],
        principal: VerifiedPrincipal,
    ) -> Response:
        from control_plane.ceo_request import app_request_ref, automated_intent_id
        from integrations.executive_mcp.schemas import (
            ERROR_CODES, GatewayError, validate_tool_arguments,
        )

        arguments = body_obj.get("arguments")
        if not isinstance(arguments, dict):
            return JSONResponse(
                {"ok": False, "error": {"code": "invalid_input",
                                         "message": "body must contain exactly {\"arguments\": {...}}"}},
                status_code=HTTPStatus.BAD_REQUEST,
                headers=_OS_HTTP_HEADERS,
            )
        try:
            validated = validate_tool_arguments("submit_ceo_intent", arguments)
        except GatewayError as exc:
            if exc.code not in ERROR_CODES:
                return JSONResponse(
                    {"ok": False, "error": {"code": "invalid_input",
                                             "message": "invalid submit arguments"}},
                    status_code=HTTPStatus.BAD_REQUEST,
                    headers=_OS_HTTP_HEADERS,
                )
            return JSONResponse(
                {"ok": False, "error": {"code": exc.code, "message": exc.message}},
                status_code=HTTPStatus.BAD_REQUEST,
                headers=_OS_HTTP_HEADERS,
            )

        try:
            request_ref = app_request_ref(validated["operation_key"])
        except Exception:
            return JSONResponse(
                {"ok": False, "error": {"code": "invalid_input",
                                         "message": "operation_key is not admissible"}},
                status_code=HTTPStatus.BAD_REQUEST,
                headers=_OS_HTTP_HEADERS,
            )

        if self._commission_preparer is not None:
            try:
                prepared = await self._commission_preparer.prepare(
                    arguments=arguments, bearer=self._bearer_from_scope(scope),
                    principal_scope=principal_scope(principal),
                )
            except Exception:
                prepared = None
            # Source publication is not Job admission. Uncertain publication or
            # authorization drift keeps the original pointer and never submits.
            if (prepared is None or prepared.status != "prepared"
                    or prepared.operation_key != validated["operation_key"]
                    or not await self._still_current(scope, principal)):
                return JSONResponse(_unknown_outcome(request_ref),
                                    status_code=HTTPStatus.ACCEPTED, headers=_OS_HTTP_HEADERS)

        # Build the inner submit scope with the ORIGINAL bearer forwarded so
        # the inner submit tool independently re-verifies.  No new operation
        # key, no resubmission, no request_ref mutation.
        inner_scope = _build_inner_scope(scope, "/v1/tools/submit_ceo_intent")
        replay_body = json.dumps(
            {"arguments": validated}, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
        try:
            start, body = await _drive_inner(self._inner_app, inner_scope, replay_body)
        except Exception:
            return JSONResponse(_unknown_outcome(request_ref), status_code=HTTPStatus.ACCEPTED,
                                headers=_OS_HTTP_HEADERS)

        if not await self._still_current(scope, principal):
            return JSONResponse(_unknown_outcome(request_ref), status_code=HTTPStatus.ACCEPTED, headers=_OS_HTTP_HEADERS)
        if start["status"] not in (200, 202, 409, 503) or not body:
            return JSONResponse(_unknown_outcome(request_ref), status_code=HTTPStatus.ACCEPTED,
                                headers=_OS_HTTP_HEADERS)
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return JSONResponse(_unknown_outcome(request_ref), status_code=HTTPStatus.ACCEPTED,
                                headers=_OS_HTTP_HEADERS)
        from integrations.executive_mcp.server import _executive_outcome
        if _executive_outcome(decoded, request_ref, start["status"]):
            if decoded["status"] == "accepted":
                receipt = decoded["receipt"]
                if receipt.get("intent_id") != automated_intent_id(request_ref):
                    return JSONResponse(_unknown_outcome(request_ref), status_code=HTTPStatus.ACCEPTED,
                                        headers=_OS_HTTP_HEADERS)
                # Strict-v2 work identity must come from the durable producer.
                if receipt.get("work_ref") != validated.get("workstream"):
                    return JSONResponse(_unknown_outcome(request_ref), status_code=HTTPStatus.ACCEPTED,
                                        headers=_OS_HTTP_HEADERS)
            if decoded["status"] != "effect_unknown":
                return JSONResponse(decoded, status_code=start["status"], headers=_OS_HTTP_HEADERS)
        # Malformed or unknown replies retain the original identity for recovery.
        return JSONResponse(_unknown_outcome(request_ref), status_code=HTTPStatus.ACCEPTED,
                            headers=_OS_HTTP_HEADERS)

    async def _dispatch_status(
        self,
        scope: Mapping[str, Any],
        body_obj: dict[str, Any],
        principal: VerifiedPrincipal,
    ) -> Response:
        from integrations.executive_mcp.schemas import (
            ERROR_CODES, GatewayError, validate_tool_arguments,
        )

        arguments = body_obj.get("arguments")
        if not isinstance(arguments, dict):
            return JSONResponse(
                {"ok": False, "error": {"code": "invalid_input",
                                         "message": "status body must contain intent_id arguments"}},
                status_code=HTTPStatus.BAD_REQUEST,
                headers=_OS_HTTP_HEADERS,
            )
        try:
            validated = validate_tool_arguments("ceo_intent_status", arguments)
        except GatewayError as exc:
            if exc.code not in ERROR_CODES:
                return JSONResponse(
                    {"ok": False, "error": {"code": "invalid_input",
                                             "message": "invalid status arguments"}},
                    status_code=HTTPStatus.BAD_REQUEST,
                    headers=_OS_HTTP_HEADERS,
                )
            return JSONResponse(
                {"ok": False, "error": {"code": exc.code, "message": exc.message}},
                status_code=HTTPStatus.BAD_REQUEST,
                headers=_OS_HTTP_HEADERS,
            )

        inner_scope = _build_inner_scope(scope, "/v1/tools/ceo_intent_status")
        replay_body = json.dumps(
            {"arguments": validated}, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
        try:
            start, body = await _drive_inner(self._inner_app, inner_scope, replay_body)
        except _CollectError:
            return JSONResponse(
                {"ok": False, "error": {"code": "backend_unavailable",
                                         "message": "Executive response is unavailable"}},
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                headers=_OS_HTTP_HEADERS,
            )
        if not await self._still_current(scope, principal):
            return JSONResponse({"ok": False, "error": {"code": "identity_unverified", "message": "status authorization changed"}}, status_code=HTTPStatus.UNAUTHORIZED, headers=_OS_HTTP_HEADERS)
        if start["status"] != 200 or not body:
            return JSONResponse(
                {"ok": False, "error": {"code": "backend_unavailable",
                                         "message": "Executive response is unavailable"}},
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                headers=_OS_HTTP_HEADERS,
            )
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return JSONResponse(
                {"ok": False, "error": {"code": "backend_unavailable",
                                         "message": "Executive response is unavailable"}},
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                headers=_OS_HTTP_HEADERS,
            )
        # Status failures are never settlement: a not_found response does not
        # authorise resubmission.  The same pointer is preserved; we never
        # mint a new operation.
        from integrations.executive_mcp.server import _is_e1_envelope
        from integrations.executive_mcp.web_ceo_v3 import WEB_CEO_V3_SERVER_VERSION
        if _is_e1_envelope(decoded, "ceo_intent_status", WEB_CEO_V3_SERVER_VERSION):
            if not decoded["ok"] or (
                isinstance(decoded["data"], dict)
                and decoded["data"].get("intent_id") == validated["intent_id"]
            ):
                return JSONResponse(decoded, status_code=HTTPStatus.OK, headers=_OS_HTTP_HEADERS)
        return JSONResponse(
            {"ok": False, "error": {"code": "backend_unavailable",
                                     "message": "Executive response is unavailable"}},
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            headers=_OS_HTTP_HEADERS,
        )

    def _bearer_from_scope(self, scope: Mapping[str, Any]) -> str:
        headers = scope.get("headers") or ()
        authorizations = [v for k, v in headers if k.lower() == b"authorization"]
        if len(authorizations) != 1:
            raise _NoStoreRefusal("authorization count changed")
        return _bearer_token(bytes(authorizations[0]))


# ---------------------------------------------------------------------------
# scope replay for the inner BoundedE1App
# ---------------------------------------------------------------------------


def _build_inner_scope(
    outer_scope: Mapping[str, Any],
    inner_path: str,
) -> dict[str, Any]:
    inner = dict(outer_scope)
    inner["path"] = inner_path
    inner["raw_path"] = inner_path.encode("ascii")
    inner["query_string"] = b""
    inner["method"] = "POST"
    # Carry the original Authorization byte string forward unchanged.
    headers = [
        (key, value)
        for key, value in outer_scope.get("headers", ())
        if key.lower() != b"host" and key.lower() != b"origin"
    ]
    inner["headers"] = headers
    return inner


# ---------------------------------------------------------------------------
# exported surface
# ---------------------------------------------------------------------------


__all__ = [
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "OsExecutiveTransportApp",
    "RECEIVE_DEADLINE_SECONDS",
    "_OS_EXECUTIVE_ROUTES",
    "principal_scope",
]


#: Backwards-compatible alias for ``server._OS_EXECUTIVE_ROUTES``.
_OS_EXECUTIVE_ROUTES = OsExecutiveTransportApp.ROUTES