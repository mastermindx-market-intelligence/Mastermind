"""Canonical bearer verification for the delegated, fixed commission operation.

An Executive token authenticates identity; a separately installed publication
grant authorizes the Studio source effect. This module cannot grant studio.control
or dispatch a Studio tool. Callers must reauthenticate before each source effect.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Callable

from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.mastermind_executive_app.os_transport import (
    _access_matches_principal,
    principal_scope,
)

RESOURCE = "https://mcp.mastermind-x.com/os/executive"
SCOPES = ("mastermind.executive.intent.submit", "mastermind.executive.read")
_HEX64 = re.compile(r"[0-9a-f]{64}")


@dataclasses.dataclass(frozen=True)
class PublicationIdentity:
    principal_scope: str
    policy_digest: str
    expires_at: int


class PublicationAuthRefused(ValueError):
    """One closed refusal; never reflect a bearer, identity or dependency error."""


class OsPublicationAuthenticator:
    def __init__(
        self, *, verifier: MastermindTokenVerifier, authenticator: JwtAuthenticator,
        allowed_principal_scopes: tuple[str, ...], clock: Callable[[], int],
    ) -> None:
        if type(verifier) is not MastermindTokenVerifier or type(authenticator) is not JwtAuthenticator:
            raise TypeError("canonical audited verifier pair required")
        policy = authenticator.policy
        if policy.resource != RESOURCE or policy.required_scopes != SCOPES:
            raise ValueError("exact OS publication authentication policy required")
        if (type(allowed_principal_scopes) is not tuple or not allowed_principal_scopes
                or len(allowed_principal_scopes) > 16
                or len(set(allowed_principal_scopes)) != len(allowed_principal_scopes)
                or any(type(scope) is not str or not _HEX64.fullmatch(scope) for scope in allowed_principal_scopes)
                or not callable(clock)):
            raise ValueError("explicit publication principal grant required")
        self._verifier = verifier
        self._authenticator = authenticator
        self._scopes = frozenset(allowed_principal_scopes)
        self._clock = clock
        self._policy = policy
        self._policy_digest = hashlib.sha256(json.dumps(
            dataclasses.asdict(policy), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()

    async def authenticate(self, bearer: str) -> PublicationIdentity:
        try:
            if self._authenticator.policy != self._policy:
                raise PublicationAuthRefused()
            access, _ = await self._verifier.verify_token_with_code(bearer)
            now = self._clock()
            if access is None or type(now) is not int:
                raise PublicationAuthRefused()
            principal = await self._authenticator.verify_token(bearer, now=now)
            if (type(principal) is not VerifiedPrincipal
                    or principal.resource != RESOURCE or principal.scopes != SCOPES
                    or not now < principal.expires_at
                    or not _access_matches_principal(access, principal)):
                raise PublicationAuthRefused()
            namespace = principal_scope(principal)
            if namespace not in self._scopes:
                raise PublicationAuthRefused()
            return PublicationIdentity(namespace, self._policy_digest, principal.expires_at)
        except Exception:
            raise PublicationAuthRefused("publication authentication refused") from None
