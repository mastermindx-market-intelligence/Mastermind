"""Private App-peer identity carrier for source commands.

The public HTTP owner supplies the actual verified six-field frame and token
expiry. The existing kernel-peer checked ingress supplies a fresh private host
guard. This carrier never reconstructs a VerifiedPrincipal, maps credentials,
or grants an action: the downstream sealed action authorizer still checks the
same exact frame and token deadline before every commit/write.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from common.executive_workspace_contract import canonical, PRINCIPAL_KEYS, RESOURCE, SCOPE
from integrations.mastermind_workspace_app.contract import principal_frame

_ISSUER = object()


@dataclass(frozen=True, slots=True, init=False)
class _PrivateSourcePrincipal:
    _encoded: bytes
    expires_at: int
    _peer_guard: object
    _issuer: object

    def __init__(self, frame, expires_at, peer_guard, issuer):
        if issuer is not _ISSUER:
            raise ValueError("SOURCE_OPERATION_PRINCIPAL_INVALID")
        object.__setattr__(self, "_encoded", canonical(frame))
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "_peer_guard", peer_guard)
        object.__setattr__(self, "_issuer", issuer)


def bind_private_source_principal(frame, *, verified_expires_at, peer_guard):
    """Private ingress composition ONLY, after the actual App-peer check.

    ``peer_guard`` must retain the accepted socket's actual host capability;
    it is never a public request field, persisted proof or replacement grant.
    """
    if (type(frame) is not dict or set(frame) != PRINCIPAL_KEYS
            or frame["resource"] != RESOURCE or type(frame["scopes"]) is not list
            or frame["scopes"] != [SCOPE]
            or any(type(frame[k]) is not str or not 1 <= len(frame[k]) <= 256
                   or not frame[k].isascii() or any(ord(c) < 32 or ord(c) == 127 for c in frame[k])
                   for k in PRINCIPAL_KEYS - {"scopes"})
            or type(verified_expires_at) is not int or not 0 <= verified_expires_at <= 2**53 - 1
            or not callable(peer_guard) or peer_guard() is not True):
        raise ValueError("SOURCE_OPERATION_PRINCIPAL_INVALID")
    value = _PrivateSourcePrincipal(frame, verified_expires_at, peer_guard, _ISSUER)
    if peer_guard() is not True:
        raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
    return value


def is_private_source_principal(value):
    return type(value) is _PrivateSourcePrincipal and value._issuer is _ISSUER


def source_principal_frame(principal):
    if not is_private_source_principal(principal):
        return principal_frame(principal)
    if principal._peer_guard() is not True:
        raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
    return json.loads(principal._encoded)


def source_principal_scope(principal):
    return hashlib.sha256(canonical(source_principal_frame(principal))).hexdigest()
