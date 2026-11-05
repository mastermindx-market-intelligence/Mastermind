"""Isolated JSON citation consumer; no listener, MCP surface or auth store.

The launcher must supply its SAME CurrentGrantOwner, context builder and an
awaitable adapter to the real ReadService.resolve_evidence_item. This module
neither implements revision replay nor mounts itself. HTML uses the existing
OS shell via the separately reviewed edge route.
"""
from __future__ import annotations

import asyncio
import inspect
from typing import Callable

from integrations.business_mcp_auth.contracts import (AUTH_AUDIT_SCHEMA, AuthAuditEvent, AuthError, AuthErrorCode,
    ResourcePolicy, validate_resource_policy)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.principal_projection import principal_projection
from .contracts import ContractViolation
from .entitlement import ResearchEntitlement
from .runtime import CurrentGrantOwner

from .bounded_item_v1 import (
    ORIGIN, PREFIX, MAX_WIRE_BYTES, ITEM_ID_REGEX as _ID,
    EvidenceResponseRefused, evidence_wire,
)
_HEADERS = [(b"content-type", b"application/json; charset=utf-8"),
            (b"cache-control", b"no-store"), (b"vary", b"Accept"),
            (b"x-robots-tag", b"noindex, nofollow"),
            (b"referrer-policy", b"no-referrer"),
            (b"x-content-type-options", b"nosniff")]
_REFUSALS = {400: b'{"error":"INVALID_REQUEST"}',
             401: b'{"error":"AUTHENTICATION_REQUIRED"}',
             403: b'{"error":"NOT_ENTITLED"}',
             404: b'{"error":"ITEM_UNAVAILABLE"}',
             503: b'{"error":"SERVICE_UNAVAILABLE"}'}



def _request(scope):
    """Canonical raw route, fixed host and no selectors or alternate transports."""
    if (scope.get("type") != "http" or scope.get("method") != "GET"
            or scope.get("scheme") != "https" or scope.get("query_string") != b""):
        return None
    path = scope.get("path")
    if type(path) is not str or not path.startswith(PREFIX):
        return None
    try:
        if scope.get("raw_path") != path.encode("ascii"):
            return None
    except UnicodeError:
        return None
    item_id = path[len(PREFIX):]
    if _ID.fullmatch(item_id) is None:
        return None
    headers = {}
    for name, value in scope.get("headers", ()):
        if type(name) is not bytes or type(value) is not bytes:
            return None
        key = name.lower()
        if key in {b"host", b"origin", b"accept", b"authorization", b"content-length", b"transfer-encoding"}:
            if key in headers:
                return None
            headers[key] = value
    if (headers.get(b"host") != b"mcp.mastermind-x.com"
            or headers.get(b"accept") != b"application/json"
            or headers.get(b"origin", ORIGIN.encode()) != ORIGIN.encode()
            or headers.get(b"content-length", b"0") != b"0"
            or b"transfer-encoding" in headers):
        return None
    try:
        authorization = headers.get(b"authorization", b"").decode("ascii")
    except UnicodeError:
        return None
    return item_id, authorization


async def _empty_body(receive):
    for _ in range(32):
        message = await receive()
        if (message.get("type") != "http.request" or message.get("body", b"") != b""):
            return False
        if not message.get("more_body", False):
            return True
    return False


class EvidenceHttpApp:
    """Composition-only ASGI endpoint, deliberately not an executable launcher."""
    def __init__(self, *, policy: ResourcePolicy, authenticator: JwtAuthenticator,
                 grant_owner: CurrentGrantOwner, context_builder: Callable,
                 item_resolver: Callable, clock: Callable[[], int], audit_sink):
        validate_resource_policy(policy)
        if (type(policy) is not ResourcePolicy or not isinstance(authenticator, JwtAuthenticator)
                or authenticator.policy != policy
                or policy.required_scopes != ("mastermind.research.read",)
                or type(grant_owner) is not CurrentGrantOwner
                or grant_owner.deployment.policy_id != policy.policy_id
                or not callable(getattr(audit_sink, "emit", None))
                or any(not callable(value) for value in (context_builder, item_resolver, clock))):
            raise ValueError("EVIDENCE_COMPOSITION_REFUSED")
        self.policy, self.authenticator, self.grant_owner = policy, authenticator, grant_owner
        self.context_builder, self.item_resolver, self.clock = context_builder, item_resolver, clock
        self.audit_sink = audit_sink

    def _audit(self, code, accepted):
        # SAME deployment sink; fixed authentication facts only. A failed sink
        # fails this private read before lookup or final body emission.
        acknowledgment = self.audit_sink.emit(AuthAuditEvent(schema=AUTH_AUDIT_SCHEMA,
            policy_id=self.policy.policy_id, code=code, accepted=accepted))
        if acknowledgment is not None:
            if inspect.iscoroutine(acknowledgment):
                acknowledgment.close()
            raise ValueError("AUDIT_REFUSED")

    def _grant(self, projection):
        entitlement = self.grant_owner.entitlement(projection)
        if (type(entitlement) is not ResearchEntitlement
                or "evidence_passage" not in entitlement.content_classes
                or entitlement.expires_at <= self._now()
                or entitlement.quote_limit_chars <= 0):
            return None
        return entitlement

    def _now(self):
        now = self.clock()
        if type(now) is not int:
            raise ValueError("CLOCK_REFUSED")
        return now

    async def __call__(self, scope, receive, send):
        # No state, lookup or metadata access for an unqualified request.
        try:
            request = _request(scope)
        except Exception:
            request = None
        status, body = 404, _REFUSALS[404]
        if request is not None:
            try:
                empty = await asyncio.wait_for(_empty_body(receive), timeout=2)
                if not empty:
                    status, body = 400, _REFUSALS[400]
                else:
                    status, body = await self._resolve(*request)
            except Exception:
                status, body = 503, _REFUSALS[503]
        await send({"type": "http.response.start", "status": status,
                    "headers": [*_HEADERS, (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def _resolve(self, item_id, authorization):
        try:
            principal = await self.authenticator.verify_authorization_header(authorization, now=self._now())
            projection = principal_projection(principal)
        except AuthError as error:
            self._audit(error.code.value, False)
            return 401, _REFUSALS[401]
        self._audit("accepted", True)
        entitlement = self._grant(projection)
        if entitlement is None:
            self._audit(AuthErrorCode.SUBJECT_REFUSED.value, False)
            return 403, _REFUSALS[403]
        # The incumbent adapter supplies the actual trusted F10 context type.
        context = self.context_builder(entitlement)
        if (inspect.isawaitable(context) or getattr(context, "principal_id", None) != projection.subject_digest):
            if inspect.iscoroutine(context):
                context.close()
            raise ValueError("CONTEXT_REFUSED")
        try:
            pending = self.item_resolver(caller_context=context, item_id=item_id)
            if not inspect.isawaitable(pending):
                raise ValueError("RESOLVER_REFUSED")
            value = await pending
        except ContractViolation as error:
            status = 403 if error.code == "NOT_ENTITLED" else 404 if error.code in {"NOT_FOUND", "SOURCE_UNAVAILABLE"} else 503
            return status, _REFUSALS[status]
        # Bound untrusted result before the final token await. Never retain a body.
        evidence_wire(value, item_id, 1000)
        if len(value["text"]) > entitlement.quote_limit_chars:
            return 403, _REFUSALS[403]
        try:
            refreshed = principal_projection(await self.authenticator.verify_authorization_header(
                authorization, now=self._now()))
        except AuthError as error:
            self._audit(error.code.value, False)
            return 401, _REFUSALS[401]
        if refreshed != projection:
            self._audit(AuthErrorCode.TOKEN_CLAIMS_REFUSED.value, False)
            return 401, _REFUSALS[401]
        self._audit("accepted", True)
        current = self._grant(refreshed)
        if current != entitlement:
            self._audit(AuthErrorCode.SUBJECT_REFUSED.value, False)
            return 403, _REFUSALS[403]
        limit = self.grant_owner.quote_limit(refreshed.subject_digest)
        # Secure file/audit I/O is synchronous but time can still advance.
        decision_time = self._now()
        if refreshed.expires_at <= decision_time:
            self._audit(AuthErrorCode.TOKEN_EXPIRED.value, False)
            return 401, _REFUSALS[401]
        if current.expires_at <= decision_time:
            self._audit(AuthErrorCode.SUBJECT_REFUSED.value, False)
            return 403, _REFUSALS[403]
        # No await between final verification/current grant and preparing response.
        return 200, evidence_wire(value, item_id, min(current.quote_limit_chars, limit))
