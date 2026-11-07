"""Fixed, body-free company READ alias. The existing executive_state owns facts."""

from __future__ import annotations
import json, re
from starlette.responses import JSONResponse, Response
from integrations.business_mcp_auth.contracts import VerifiedPrincipal, AuthErrorCode
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.mastermind_executive_app.os_transport import (
    _OS_HTTP_HEADERS,
    _bounded_receive_body,
    _parse_body,
    _bearer_token,
    _access_matches_principal,
    _build_inner_scope,
    _drive_inner,
    RECEIVE_DEADLINE_SECONDS,
    principal_scope,
)

PATH = "/os/executive/company-priorities"
SCHEMA = "mastermind.company_priorities.v1"


def project(envelope, principal):
    from integrations.mastermind_executive_app.gateway import CeoIngressReadGateway

    if (
        type(envelope) is not dict
        or envelope.get("ok") is not True
        or envelope.get("tool") != "executive_state"
        or envelope.get("schema") != "mastermind.executive_mcp_result.v1"
        or envelope.get("bounded") != []
        or type(envelope.get("degraded")) is not list
    ):
        raise ValueError("source_unavailable")
    data = envelope.get("data")
    if not CeoIngressReadGateway._valid_state_data(data, bounded=[]):
        raise ValueError("source_unavailable")
    strategy = data["strategic_state"]
    if type(strategy) is not dict or "authored_orientation" not in strategy:
        raise ValueError("source_unavailable")
    from control_plane.company_orientation import validate

    meta = validate(strategy["authored_orientation"])
    revision = data["mastermind"]["sha"]
    if not re.fullmatch("[0-9a-f]{40}", revision):
        raise ValueError("source_unavailable")
    return {
        "schema": SCHEMA,
        "source": {
            "owner": "STRATEGIC_STATE",
            "revision": revision,
            "path": "config/strategic_state.yml",
            "observed_at": envelope["generated_at"],
        },
        "owner_context": {
            "principal_scope": principal_scope(principal),
            "verified_expiry": principal.expires_at,
        },
        "authority": meta["authority"],
        "as_of": meta["as_of"],
        "company_phase": strategy["company_phase"],
        "north_star": strategy["north_star"],
        "priorities": strategy["p0"],
        "phase_review_criteria": strategy["phase_gates"],
    }


class CompanyPrioritiesTransport:
    def __init__(self, inner, *, read_pair, submit_pair, clock):
        self._inner = inner
        self._clock = clock
        self._pairs = (read_pair, submit_pair)
        for verifier, auth in self._pairs:
            if (
                type(verifier) is not MastermindTokenVerifier
                or type(auth) is not JwtAuthenticator
                or verifier._validated_composition() != auth.policy
            ):
                raise TypeError("actual current Executive READ pairs required")
        a, b = (x[1].policy for x in self._pairs)
        if (
            set(a.required_scopes) != {"mastermind.executive.read"}
            or set(b.required_scopes)
            != {"mastermind.executive.read", "mastermind.executive.intent.submit"}
            or a.resource != b.resource
            or a.issuer != b.issuer
            or a.allowed_subject_digests != b.allowed_subject_digests
        ):
            raise ValueError("same Executive resource required")

    async def _auth(self, token):
        try:
            for verifier, auth in self._pairs:
                access, code = await verifier.verify_token_with_code(token)
                if access is None:
                    if code == AuthErrorCode.SCOPE_REFUSED:
                        continue
                    return None
                now = self._clock()
                p = await auth.verify_token(token, now=now)
                released = self._clock()
                return (
                    p
                    if type(p) is VerifiedPrincipal
                    and type(now) is int
                    and type(released) is int
                    and now <= released < p.expires_at
                    and _access_matches_principal(access, p)
                    else None
                )
        except Exception:
            return None

    async def __call__(self, scope, receive, send):
        def fail(status):
            return JSONResponse(
                {"error": "company_priorities_unavailable"},
                status_code=status,
                headers=_OS_HTTP_HEADERS,
            )

        headers = scope.get("headers", [])
        try:
            if (
                scope.get("method") != "POST"
                or scope.get("path") != PATH
                or scope.get("raw_path") != PATH.encode()
                or scope.get("query_string")
                or scope.get("scheme") != "https"
            ):
                raise ValueError()
            if [v for k, v in headers if k.lower() == b"host"] != [
                b"mcp.mastermind-x.com"
            ]:
                raise ValueError()
            origins = [v for k, v in headers if k.lower() == b"origin"]
            if origins not in ([], [b"https://mcp.mastermind-x.com"]):
                raise ValueError()
            tokens = [v for k, v in headers if k.lower() == b"authorization"]
            if len(tokens) != 1:
                raise ValueError()
            if any(
                k.lower() in (b"x-mastermind-workspace-authorization",)
                for k, v in headers
            ):
                raise ValueError()
            if [
                v.lower().split(b";", 1)[0].strip()
                for k, v in headers
                if k.lower() == b"content-type"
            ] != [b"application/json"]:
                raise ValueError()
            token = _bearer_token(tokens[0])
        except Exception:
            await fail(403)(scope, receive, send)
            return
        principal = await self._auth(token)
        if principal is None:
            await fail(401)(scope, receive, send)
            return
        try:
            body = _parse_body(
                await _bounded_receive_body(
                    receive, deadline_seconds=RECEIVE_DEADLINE_SECONDS
                )
            )
            if body != {}:
                await fail(400)(scope, receive, send)
                return
            if await self._auth(token) != principal:
                await fail(401)(scope, receive, send)
                return
            start, raw = await _drive_inner(
                self._inner,
                _build_inner_scope(scope, "/v1/tools/executive_state"),
                b'{"arguments":{}}',
            )
            if start["status"] != 200:
                raise ValueError()
            data = project(json.loads(raw), principal)
            response = JSONResponse(data, headers=_OS_HTTP_HEADERS)
            if len(response.body) > 65536:
                raise ValueError()
        except Exception:
            await fail(503)(scope, receive, send)
            return
        if await self._auth(token) != principal:
            await fail(401)(scope, receive, send)
            return
        await response(scope, receive, send)
