"""Fail-closed Hermes-side client for the six Steward read tools.

The client is not an MCP server, a Steward replacement, or an organizational
store. It admits one bearer token, enforces the existing
``mastermind.steward.read`` claims policy, and forwards one allowlisted read
to an injected transport. Degraded and unknown upstream payloads are copied
through unchanged. Nothing in this module writes company state.
"""

from __future__ import annotations

import copy
import logging
import re
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from integrations.business_mcp_auth.claims import validate_verified_claims
from integrations.business_mcp_auth.contracts import (
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
)
from integrations.mastermind_secretary_mcp.schemas import (
    GROUNDING_STATES,
    MAX_REQUEST_BYTES,
    TOOL_SPECS,
    GatewayError,
    canonical_json,
    validate_tool_arguments,
)

logger = logging.getLogger("integrations.hermes_steward")

REQUIRED_SCOPE = "mastermind.steward.read"
ALLOWED_TOOLS = tuple(spec.name for spec in TOOL_SPECS)
_ALLOWED = frozenset(ALLOWED_TOOLS)
RESULT_SCHEMA = "mastermind.hermes_steward_read.v1"
# Same byte cap as the business MCP verifier. Compact JWT shape stays on the
# injected verifier; fixture tokens in the offline suite are not compact JWTs.
MAX_BEARER_TOKEN_BYTES = 16 * 1024

# Names and argument keys that ask for a mutation. These are refused before
# any transport call. The six Steward tools are not in this set.
_WRITE_NAME_RE = re.compile(
    r"(?i)(?:^|[._/-])(?:write|submit|create|update|delete|mutate|approve|"
    r"enqueue|dispatch|execute|post|put|patch)(?:$|[._/-])"
    r"|(?:write|submit|delete|mutate)"
)
_WRITE_ARGUMENT_KEYS = frozenset(
    {
        "action",
        "command",
        "intent",
        "mutation",
        "patch",
        "write",
    }
)

_AUTH_REFUSAL = {
    AuthErrorCode.AUTHORIZATION_MISSING: "AUTHORIZATION_MISSING",
    AuthErrorCode.AUTHORIZATION_MALFORMED: "TOKEN_REJECTED",
    AuthErrorCode.TOKEN_EXPIRED: "TOKEN_EXPIRED",
    AuthErrorCode.TOKEN_SIGNATURE_REFUSED: "TOKEN_REJECTED",
    AuthErrorCode.TOKEN_HEADER_REFUSED: "TOKEN_REJECTED",
    AuthErrorCode.TOKEN_CLAIMS_REFUSED: "TOKEN_REJECTED",
    AuthErrorCode.TOKEN_TOO_LARGE: "TOKEN_REJECTED",
    AuthErrorCode.TOKEN_NOT_YET_VALID: "TOKEN_REJECTED",
    AuthErrorCode.TOKEN_LIFETIME_REFUSED: "TOKEN_REJECTED",
    AuthErrorCode.ISSUER_REFUSED: "TOKEN_REJECTED",
    AuthErrorCode.RESOURCE_REFUSED: "AUDIENCE_REJECTED",
    AuthErrorCode.SCOPE_REFUSED: "SCOPE_REJECTED",
    AuthErrorCode.SUBJECT_REFUSED: "TOKEN_REJECTED",
    AuthErrorCode.KEY_NOT_FOUND: "TOKEN_REJECTED",
    AuthErrorCode.JWKS_REFUSED: "TOKEN_REJECTED",
    AuthErrorCode.JWKS_UNAVAILABLE: "TOKEN_REJECTED",
    AuthErrorCode.INTERNAL_ERROR: "TOKEN_REJECTED",
    AuthErrorCode.INVALID_POLICY: "TOKEN_REJECTED",
}


class ClaimsVerifier(Protocol):
    """Return signature-verified claims for one bearer token.

    Signature checking stays at this injected edge, the same split as
    ``integrations.business_mcp_auth``. This client always runs the pure
    claims policy afterwards. Implementations must not log the token.
    """

    def verify(self, token: str) -> Mapping[str, Any]: ...


class StewardUpstream(Protocol):
    """One read against the existing Steward MCP surface."""

    def call(self, tool: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]: ...


def _refusal(code: str, tool: str) -> dict[str, Any]:
    safe_tool = tool if tool in _ALLOWED else "unknown"
    return {
        "schema": RESULT_SCHEMA,
        "tool": safe_tool,
        "ok": False,
        "forwarded": False,
        "data": None,
        "error": {"code": code, "message": code},
    }


def _log_refusal(code: str, tool: str) -> None:
    visible = tool if tool in _ALLOWED else "-"
    logger.info("refusal code=%s tool=%s", code, visible)


def _bearer_token(authorization: object) -> str:
    if authorization is None or authorization == "":
        raise AuthError(AuthErrorCode.AUTHORIZATION_MISSING)
    if not isinstance(authorization, str):
        raise AuthError(AuthErrorCode.AUTHORIZATION_MALFORMED)
    if (
        authorization != authorization.strip()
        or authorization.count(" ") != 1
        or any(ord(character) < 32 or ord(character) == 127 for character in authorization)
    ):
        raise AuthError(AuthErrorCode.AUTHORIZATION_MALFORMED)
    try:
        authorization.encode("ascii")
    except UnicodeEncodeError:
        raise AuthError(AuthErrorCode.AUTHORIZATION_MALFORMED) from None
    scheme, token = authorization.split(" ", 1)
    if scheme.lower() != "bearer" or not token:
        raise AuthError(AuthErrorCode.AUTHORIZATION_MALFORMED)
    if len(token.encode("ascii")) > MAX_BEARER_TOKEN_BYTES:
        raise AuthError(AuthErrorCode.AUTHORIZATION_MALFORMED)
    return token


def _write_name(tool: object) -> bool:
    return isinstance(tool, str) and _WRITE_NAME_RE.search(tool) is not None


def _write_arguments(arguments: object) -> bool:
    if not isinstance(arguments, Mapping):
        return False
    for key in arguments:
        if not isinstance(key, str):
            return True
        if key in _WRITE_ARGUMENT_KEYS or _WRITE_NAME_RE.search(key):
            return True
    return False


def _byte_budget_exceeded(value: object, limit: int) -> bool:
    total = 0
    stack: list[object] = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            total += len(node.encode("utf-8"))
        elif isinstance(node, Mapping):
            for key, item in node.items():
                if isinstance(key, str):
                    total += len(key.encode("utf-8"))
                stack.append(item)
        elif isinstance(node, (list, tuple)):
            stack.extend(node)
        if total > limit:
            return True
    return False


def _request_too_large(tool: str, arguments: object) -> bool:
    payload = {"tool": tool, "arguments": {} if arguments is None else arguments}
    if _byte_budget_exceeded(payload, MAX_REQUEST_BYTES):
        return True
    try:
        raw = canonical_json(payload)
    except GatewayError:
        return False
    return len(raw) > MAX_REQUEST_BYTES


def _grounding_state(payload: Mapping[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, Mapping):
        state = data.get("state")
        if state in GROUNDING_STATES:
            return str(state)
    state = payload.get("state")
    if state in GROUNDING_STATES:
        return str(state)
    return "unspecified"


class StewardReadClient:
    """Read company state through the six existing Steward tools only."""

    def __init__(
        self,
        *,
        policy: ResourcePolicy,
        verifier: ClaimsVerifier,
        upstream: StewardUpstream,
        now: int,
        clock: Callable[[], int] | None = None,
    ) -> None:
        if not isinstance(policy, ResourcePolicy):
            raise TypeError("policy must be ResourcePolicy")
        if REQUIRED_SCOPE not in policy.required_scopes or len(policy.required_scopes) != 1:
            raise ValueError("policy must require only mastermind.steward.read")
        if not callable(getattr(verifier, "verify", None)):
            raise TypeError("verifier must provide verify")
        if not callable(getattr(upstream, "call", None)):
            raise TypeError("upstream must provide call")
        if type(now) is not int:
            raise TypeError("now must be an int unix second")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        self._policy = policy
        self._verifier = verifier
        self._upstream = upstream
        self._now = now
        self._clock = clock

    def _unix_now(self) -> int:
        if self._clock is None:
            return self._now
        instant = self._clock()
        if type(instant) is not int:
            raise TypeError("clock must return an int unix second")
        return instant

    def read(
        self,
        tool: str,
        arguments: object = None,
        *,
        authorization: object = None,
    ) -> dict[str, Any]:
        """Return one upstream read or a closed refusal. Never invents facts."""

        if _write_name(tool):
            _log_refusal("WRITE_REFUSED", tool if isinstance(tool, str) else "")
            return _refusal("WRITE_REFUSED", tool if isinstance(tool, str) else "")
        if not isinstance(tool, str) or tool not in _ALLOWED:
            _log_refusal("UNKNOWN_TOOL", "")
            return _refusal("UNKNOWN_TOOL", "")
        if _request_too_large(tool, arguments):
            _log_refusal("REQUEST_TOO_LARGE", tool)
            return _refusal("REQUEST_TOO_LARGE", tool)
        if _write_arguments(arguments):
            _log_refusal("WRITE_REFUSED", tool)
            return _refusal("WRITE_REFUSED", tool)

        try:
            token = _bearer_token(authorization)
            claims = self._verifier.verify(token)
            if not isinstance(claims, Mapping):
                raise AuthError(AuthErrorCode.TOKEN_CLAIMS_REFUSED)
            validate_verified_claims(claims, self._policy, now=self._unix_now())
        except AuthError as exc:
            code = _AUTH_REFUSAL.get(exc.code, "TOKEN_REJECTED")
            _log_refusal(code, tool)
            return _refusal(code, tool)
        except Exception:
            # Verifier failures can embed the presented token in their text.
            # The refusal stays a fixed code and the exception is not logged.
            _log_refusal("TOKEN_REJECTED", tool)
            return _refusal("TOKEN_REJECTED", tool)

        try:
            validated = validate_tool_arguments(tool, arguments)
        except GatewayError:
            _log_refusal("INVALID_REQUEST", tool)
            return _refusal("INVALID_REQUEST", tool)

        try:
            upstream = self._upstream.call(tool, validated)
        except Exception:
            _log_refusal("UPSTREAM_UNAVAILABLE", tool)
            return _refusal("UPSTREAM_UNAVAILABLE", tool)
        if not isinstance(upstream, Mapping):
            _log_refusal("UPSTREAM_INVALID", tool)
            return _refusal("UPSTREAM_INVALID", tool)

        # Copy the upstream document and stop. Missing predicates stay missing.
        forwarded = copy.deepcopy(dict(upstream))
        state = _grounding_state(forwarded)
        logger.info("forwarded tool=%s state=%s", tool, state)
        return {
            "schema": RESULT_SCHEMA,
            "tool": tool,
            "ok": True,
            "forwarded": True,
            "data": forwarded,
            "error": None,
        }


__all__ = [
    "ALLOWED_TOOLS",
    "REQUIRED_SCOPE",
    "RESULT_SCHEMA",
    "ClaimsVerifier",
    "StewardReadClient",
    "StewardUpstream",
]
