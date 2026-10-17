"""Finite subscription READ facts, captured by the existing authenticated receiver.

These validators do not authenticate a DTO. Only a canonical accepted Runtime
subscription can supply a retained authorization. No token is stored or minted.
"""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import re

from control_plane.principal_projection import NeutralPrincipalProjection, neutral_principal_projection
from integrations.business_mcp_auth.contracts import validate_resource_policy

READ = "mastermind.executive.read"
SCHEMA = "mastermind.reply_subscription_authorization.v1"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = frozenset(f.name for f in dataclasses.fields(NeutralPrincipalProjection))
_KEYS = {"schema", "principal", "source_policy_sha256", "request_ref", "read_ref", "request_event_sha256", "expires_at"}


class BoundedReplyAuthorizationUnavailable(ValueError):
    def __init__(self):
        super().__init__("bounded original reply authorization unavailable")


def policy_fingerprint(policy):
    current = validate_resource_policy(policy)
    return hashlib.sha256(json.dumps(dataclasses.asdict(current), sort_keys=True,
        separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _source(principal, policy, expiry, now):
    current = validate_resource_policy(policy)
    if (type(principal) is not NeutralPrincipalProjection or type(now) is not int
            or type(expiry) is not int or type(principal.issued_at) is not int
            or type(principal.expires_at) is not int
            or not principal.issued_at <= now < expiry <= principal.expires_at
            or not 0 < principal.expires_at-principal.issued_at <= current.max_token_lifetime_seconds
            or principal.policy_id != current.policy_id or principal.issuer != current.issuer
            or principal.resource != current.resource or principal.scopes != current.required_scopes
            or READ not in principal.scopes or type(principal.subject_digest) is not str
            or not _SHA.fullmatch(principal.subject_digest)
            or type(principal.client_ref) is not str or not _ID.fullmatch(principal.client_ref)
            or principal.jti_digest is not None and (type(principal.jti_digest) is not str
                or not _SHA.fullmatch(principal.jti_digest))):
        raise ValueError
    allowed = False
    for subject in current.allowed_subject_digests:
        allowed |= hmac.compare_digest(principal.subject_digest, subject)
    if not allowed:
        raise ValueError
    # Reuse the sole neutral projection owner for issuer digest/encoding checks.
    neutral_principal_projection(**dataclasses.asdict(principal))
    return current


def capture_reply_authorization(principal, policy, *, subscription_expires_at,
                                request_ref, read_ref, request_event_sha256, now):
    try:
        _source(principal, policy, subscription_expires_at, now)
        if (any(type(v) is not str or not _ID.fullmatch(v) for v in (request_ref, read_ref))
                or type(request_event_sha256) is not str or not _SHA.fullmatch(request_event_sha256)):
            raise ValueError
        wire = dataclasses.asdict(principal)
        wire["scopes"] = list(principal.scopes)
        return {"schema":SCHEMA, "principal":wire, "source_policy_sha256":policy_fingerprint(policy),
            "request_ref":request_ref, "read_ref":read_ref, "request_event_sha256":request_event_sha256,
            "expires_at":subscription_expires_at}
    except Exception:
        raise BoundedReplyAuthorizationUnavailable() from None


def validate_reply_authorization(value, policy, *, now):
    try:
        if type(value) is not dict or set(value) != _KEYS or value["schema"] != SCHEMA:
            raise ValueError
        raw = value["principal"]
        if (type(raw) is not dict or set(raw) != _FIELDS or type(raw["scopes"]) is not list
                or not 1 <= len(raw["scopes"]) <= 32 or any(type(v) is not str for v in raw["scopes"])):
            raise ValueError
        principal = neutral_principal_projection(**{**raw, "scopes":tuple(raw["scopes"])})
        expected = capture_reply_authorization(principal, policy,
            subscription_expires_at=value["expires_at"], request_ref=value["request_ref"],
            read_ref=value["read_ref"], request_event_sha256=value["request_event_sha256"], now=now)
        if expected != value:
            raise ValueError
        return dataclasses.replace(principal, scopes=(READ,), expires_at=value["expires_at"])
    except Exception:
        raise BoundedReplyAuthorizationUnavailable() from None
