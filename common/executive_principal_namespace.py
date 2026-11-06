"""Canonical pure principal namespace; no authentication or authority.

Shared by the original App wrapper and the native private-peer owner.
"""
from __future__ import annotations

import hashlib

__all__ = ["NAMESPACE_SCOPE", "principal_scope_from_identity"]

#: Domain separation prefix for the documented, stable owner namespace.
NAMESPACE_SCOPE = b"mastermind.os.executive.principal_scope.v1"


def principal_scope_from_identity(
    *,
    issuer_digest: str,
    subject_digest: str,
    client_ref: str,
    resource: str,
) -> str:
    """Derive the one documented, stable, opaque owner namespace.

    The recipe is fixed: ``NAMESPACE_SCOPE``, the ASCII ``issuer_digest``, the
    ASCII ``subject_digest``, the UTF-8 ``client_ref``, and the LITERAL UTF-8
    ``resource`` bytes (never a digest of the resource) joined with NUL
    bytes, then SHA-256 hex-digested.  One recipe, no variants, no
    re-derivation of any field.

    This is a pure string-to-string derivation of an opaque namespace label.
    It does not authenticate data, verify identity, or grant any authority;
    whether the caller may act is decided elsewhere.
    """

    material = b"\0".join((
        NAMESPACE_SCOPE,
        issuer_digest.encode("ascii"),
        subject_digest.encode("ascii"),
        client_ref.encode("utf-8"),
        resource.encode("utf-8"),
    ))
    return hashlib.sha256(material).hexdigest()
