"""Edge-owned projection from verified authentication into authorization."""

from __future__ import annotations

from control_plane.principal_projection import (
    NeutralPrincipalProjection,
    neutral_principal_projection,
)
from integrations.business_mcp_auth.contracts import VerifiedPrincipal


class PrincipalProjectionError(ValueError):
    """The caller did not supply a valid exact verified-principal contract."""


def principal_projection(principal: object) -> NeutralPrincipalProjection:
    if type(principal) is not VerifiedPrincipal:
        raise PrincipalProjectionError("verified principal required")
    try:
        return neutral_principal_projection(
            policy_id=principal.policy_id,
            issuer=principal.issuer,
            issuer_digest=principal.issuer_digest,
            resource=principal.resource,
            subject_digest=principal.subject_digest,
            client_ref=principal.client_ref,
            scopes=principal.scopes,
            issued_at=principal.issued_at,
            expires_at=principal.expires_at,
            jti_digest=principal.jti_digest,
        )
    except (TypeError, ValueError) as exc:
        raise PrincipalProjectionError(str(exc)) from None
