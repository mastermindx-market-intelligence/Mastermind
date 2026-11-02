"""Pure owner-namespace derivation for the OS Executive transport.

This module is the single home of the documented, stable recipe that maps an
already-verified principal's closed identity fields onto the one opaque owner
namespace string.  It deliberately imports only the standard library so the
root-owned, pinned runtime (``python3.12 -I -S -B``, no site, no third-party
packages, no bytecode) can import and evaluate it directly — unlike
:mod:`integrations.mastermind_executive_app.os_transport`, whose Starlette
edge imports keep it out of that runtime.

The helper performs data derivation only.  Calling it proves nothing: it does
not verify a token, authorize a caller, or authenticate any input.  The
caller remains responsible for having verified the identity fields it passes.
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
