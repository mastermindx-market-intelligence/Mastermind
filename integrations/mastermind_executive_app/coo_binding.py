"""Pure sealed COO principal binding over Business MCP OAuth facts.

This is an authorization adapter, not an identity store. It consumes one
already-verified Business MCP principal plus a root-sealed installed binding
projection supplied by the existing Executive MCP installation owner.

No token, raw subject, client id, credential, session, Runtime, Job, queue,
clock, network, filesystem, or persistence owner lives here.

Two binding document generations are supported side by side. The incumbent v1
document carries exactly one enrolled client. The opt-in v2 document carries a
bounded set of enrolled clients so one installation can serve several distinct
COO clients. Selection is always by exact authenticated-frame match: there is
no alias, no role-derived identity, no primary/fallback client, no caller
index or session selector, and no default record.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from typing import Any

from integrations.business_mcp_auth.contracts import (
    ResourcePolicy,
    VerifiedPrincipal,
    validate_resource_policy,
)

BINDING_SCHEMA = "mastermind.executive_coo_principal_binding.v1"
# Opt-in bounded multi-client generation. It is a distinct schema, never a
# normalization of v1: a v1 document is validated and returned as v1, and a v2
# document is validated and returned as v2.
COO_BINDING_SCHEMA_V2 = "mastermind.executive_coo_principal_binding.v2"
MAX_COO_BINDINGS = 8
# Canonical UTF-8 byte ceiling for one v2 document.
MAX_COO_BINDING_MATERIAL_BYTES = 65536
READ_SCOPE = "mastermind.executive.read"
COO_ACTION_SCOPE = "mastermind.executive.coo.act"
COO_SCOPES = tuple(sorted((READ_SCOPE, COO_ACTION_SCOPE)))

_PRINCIPAL_KEY_ORDER = (
    "policy_id",
    "issuer_digest",
    "subject_digest",
    "client_ref",
    "resource",
    "scopes",
)
_PRINCIPAL_KEYS = frozenset(_PRINCIPAL_KEY_ORDER)
_BINDING_KEYS = _PRINCIPAL_KEYS | {"permission_digest"}
_ENVELOPE_KEYS = frozenset({"schema", "enabled", "binding"})
_ENVELOPE_KEYS_V2 = frozenset({"schema", "enabled", "bindings"})
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def principal_frame(principal: VerifiedPrincipal) -> dict[str, Any]:
    """Project only stable pseudonymous authorization identity.

    Token issue/expiry/JTI are deliberately excluded: they prove the current
    bearer instance, not the durable enrolled principal/client binding.
    """
    if type(principal) is not VerifiedPrincipal:
        raise ValueError("access_denied")
    return {
        "policy_id": principal.policy_id,
        "issuer_digest": principal.issuer_digest,
        "subject_digest": principal.subject_digest,
        "client_ref": principal.client_ref,
        "resource": principal.resource,
        "scopes": list(principal.scopes),
    }


def _validate_record(record: object, policy: ResourcePolicy) -> dict[str, Any]:
    """Validate one exact enrolled-client record and return it detached.

    Every incumbent policy, issuer, subject, resource, scope and digest
    validator applies unchanged to both generations: the record is the same
    seven-field shape, and permission_digest remains an enrollment-owner
    receipt digest rather than a new mission grant.
    """
    if not isinstance(record, Mapping) or set(record) != _BINDING_KEYS:
        raise ValueError("access_denied")
    expected_issuer_digest = hashlib.sha256(policy.issuer.encode("utf-8")).hexdigest()
    if (
        record.get("policy_id") != policy.policy_id
        or record.get("issuer_digest") != expected_issuer_digest
        or record.get("subject_digest") not in policy.allowed_subject_digests
        or record.get("resource") != policy.resource
        or record.get("scopes") != list(COO_SCOPES)
        or any(
            type(record.get(key)) is not str
            or _HEX64.fullmatch(record[key]) is None
            for key in ("issuer_digest", "subject_digest", "client_ref", "permission_digest")
        )
    ):
        raise ValueError("access_denied")
    return json.loads(_canonical(record))


def _validate_v1(value: Mapping[str, Any], policy: ResourcePolicy) -> dict[str, Any]:
    """Validate the incumbent single-client document."""
    if set(value) != _ENVELOPE_KEYS:
        raise ValueError("access_denied")
    if value.get("schema") != BINDING_SCHEMA or type(value.get("enabled")) is not bool:
        raise ValueError("access_denied")
    binding = value.get("binding")
    if not value["enabled"]:
        if binding is not None:
            raise ValueError("access_denied")
        return {"schema": BINDING_SCHEMA, "enabled": False, "binding": None}
    _validate_record(binding, policy)
    return json.loads(_canonical(value))


def _validate_v2(value: Mapping[str, Any], policy: ResourcePolicy) -> dict[str, Any]:
    """Validate the opt-in bounded multi-client document.

    Records are stored in ascending canonical digest order. A duplicated
    record digest and a duplicated six-field principal identity are both
    refused, so no principal can select two grants. There is no default
    record and no ordering fallback: only an exact frame match selects.
    """
    if set(value) != _ENVELOPE_KEYS_V2:
        raise ValueError("access_denied")
    if (
        value.get("schema") != COO_BINDING_SCHEMA_V2
        or type(value.get("enabled")) is not bool
    ):
        raise ValueError("access_denied")
    bindings = value.get("bindings")
    if not isinstance(bindings, list):
        raise ValueError("access_denied")
    if not value["enabled"]:
        if bindings:
            raise ValueError("access_denied")
        return {"schema": COO_BINDING_SCHEMA_V2, "enabled": False, "bindings": []}
    if not 1 <= len(bindings) <= MAX_COO_BINDINGS:
        raise ValueError("access_denied")
    records: list[dict[str, Any]] = []
    digests: list[str] = []
    identities: set[bytes] = set()
    for raw in bindings:
        record = _validate_record(raw, policy)
        digest = _digest(record)
        # The six-field principal identity, canonicalized so it is hashable
        # and independent of key order.
        identity = _canonical({key: record[key] for key in _PRINCIPAL_KEY_ORDER})
        if digest in digests or identity in identities:
            raise ValueError("access_denied")
        digests.append(digest)
        identities.add(identity)
        records.append(record)
    if digests != sorted(digests):
        raise ValueError("access_denied")
    document = {"schema": COO_BINDING_SCHEMA_V2, "enabled": True, "bindings": records}
    if len(_canonical(document)) > MAX_COO_BINDING_MATERIAL_BYTES:
        raise ValueError("access_denied")
    return document


def validate_coo_binding(value: object, policy: ResourcePolicy) -> dict[str, Any]:
    """Validate one closed installed COO client binding.

    The returned document is the normalized *same-version* document: a v1
    input is never widened into v2 and a v2 input is never narrowed into v1.
    permission_digest is an enrollment-owner receipt digest. This reducer
    verifies its shape; it does not mint or reinterpret that receipt as
    mission authority.
    """
    policy = validate_resource_policy(policy)
    if tuple(policy.required_scopes) != COO_SCOPES:
        raise ValueError("access_denied")
    if not isinstance(value, Mapping):
        raise ValueError("access_denied")
    schema = value.get("schema")
    if schema == BINDING_SCHEMA:
        return _validate_v1(value, policy)
    if schema == COO_BINDING_SCHEMA_V2:
        return _validate_v2(value, policy)
    raise ValueError("access_denied")


def coo_binding_records(value: object, policy: ResourcePolicy) -> tuple[dict[str, Any], ...]:
    """Return the validated, detached enrolled-client records.

    A disabled document grants nothing, an enabled v1 document carries
    exactly one record, and an enabled v2 document carries its validated
    tuple.  Records are detached copies: mutating one never rewrites the
    caller's document or any other record.
    """
    document = validate_coo_binding(value, policy)
    if document["schema"] == BINDING_SCHEMA:
        binding = document["binding"]
        if binding is None:
            return ()
        return (json.loads(_canonical(binding)),)
    return tuple(json.loads(_canonical(record)) for record in document["bindings"])


def select_coo_binding(
    value: object,
    policy: ResourcePolicy,
    frame: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Select the one enrolled-client record matching an exact frame.

    The frame must carry exactly the six principal fields and every one of
    them must match.  A malformed document, a malformed frame, no match and
    an ambiguous match all fail closed with None.  This helper does not
    authenticate the frame, parse a token or create authority: the caller's
    real authenticated transport remains the only source of principal facts.
    """
    if not isinstance(frame, Mapping) or set(frame) != _PRINCIPAL_KEYS:
        return None
    try:
        records = coo_binding_records(value, policy)
    except Exception:
        return None
    matches = [
        record
        for record in records
        if all(record[key] == frame[key] for key in _PRINCIPAL_KEYS)
    ]
    if len(matches) != 1:
        return None
    return json.loads(_canonical(matches[0]))


def coo_authorizer(*, policy: ResourcePolicy, load_binding: Callable[[], object]):
    """Return an exact principal gate that reloads sealed binding every call."""
    if not callable(load_binding):
        raise ValueError("access_denied")
    selected_policy = validate_resource_policy(policy)
    validate_coo_binding(load_binding(), selected_policy)

    def binding_digest(principal: VerifiedPrincipal) -> str | None:
        try:
            frame = principal_frame(principal)
            selected = select_coo_binding(load_binding(), selected_policy, frame)
            return _digest(selected) if selected is not None else None
        except Exception:
            pass
        return None

    def authorize(principal: VerifiedPrincipal) -> bool:
        return binding_digest(principal) is not None

    authorize.binding_digest = binding_digest
    return authorize


__all__ = [
    "BINDING_SCHEMA",
    "COO_ACTION_SCOPE",
    "COO_BINDING_SCHEMA_V2",
    "COO_SCOPES",
    "MAX_COO_BINDINGS",
    "MAX_COO_BINDING_MATERIAL_BYTES",
    "READ_SCOPE",
    "coo_authorizer",
    "coo_binding_records",
    "principal_frame",
    "select_coo_binding",
    "validate_coo_binding",
]
