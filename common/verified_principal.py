"""Dependency-neutral projection of an already verified caller identity.

Authentication and authorization remain owned by the integration edge.  This
module only defines the immutable pseudonymous value that lower layers may
consume after that edge has verified it.  Keeping the value at the bottom of
the dependency graph lets control-plane policy validate exact provenance
without importing an integration package.
"""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class VerifiedPrincipal:
    """Signature-verified, policy-authorized, pseudonymous caller projection."""

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


__all__ = ["VerifiedPrincipal"]
