"""Immutable, neutral authorization input for authenticated principals.

Authentication owns its verified edge type. Authorization consumes only this
validated projection and never reaches back into an integration package.
"""

from __future__ import annotations

import dataclasses
import hashlib


@dataclasses.dataclass(frozen=True, slots=True)
class NeutralPrincipalProjection:
    policy_id: str
    issuer: str
    issuer_digest: str
    resource: str
    subject_digest: str
    client_ref: str
    scopes: tuple[str, ...]
    issued_at: int
    expires_at: int
    jti_digest: str | None


def neutral_principal_projection(
    *,
    policy_id: str,
    issuer: str,
    issuer_digest: str,
    resource: str,
    subject_digest: str,
    client_ref: str,
    scopes: tuple[str, ...],
    issued_at: int,
    expires_at: int,
    jti_digest: str | None,
) -> NeutralPrincipalProjection:
    if type(issuer) is not str or not issuer or len(issuer) > 2048:
        raise ValueError("issuer")
    if type(resource) is not str or not resource or len(resource) > 2048:
        raise ValueError("resource")
    if type(scopes) is not tuple or any(type(scope) is not str for scope in scopes):
        raise ValueError("scopes")
    if any(ord(char) < 32 or ord(char) == 127 for char in issuer + resource):
        raise ValueError("principal_text")
    try:
        issuer_bytes = issuer.encode("utf-8", errors="strict")
        resource.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ValueError("principal_encoding") from None
    if issuer_digest != hashlib.sha256(issuer_bytes).hexdigest():
        raise ValueError("issuer_digest")
    return NeutralPrincipalProjection(
        policy_id=policy_id,
        issuer=issuer,
        issuer_digest=issuer_digest,
        resource=resource,
        subject_digest=subject_digest,
        client_ref=client_ref,
        scopes=scopes,
        issued_at=issued_at,
        expires_at=expires_at,
        jti_digest=jti_digest,
    )
