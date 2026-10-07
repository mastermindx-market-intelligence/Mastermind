"""Pure sealed COO principal binding over Business MCP OAuth facts.

This is an authorization adapter, not an identity store. It consumes one
already-verified Business MCP principal plus a root-sealed installed binding
projection supplied by the existing Executive MCP installation owner.

No token, raw subject, client id, credential, session, Runtime, Job, queue,
clock, network, filesystem, or persistence owner lives here.
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
READ_SCOPE = "mastermind.executive.read"
COO_ACTION_SCOPE = "mastermind.executive.coo.act"
COO_SCOPES = tuple(sorted((READ_SCOPE, COO_ACTION_SCOPE)))

_PRINCIPAL_KEYS = frozenset(
    {"policy_id", "issuer_digest", "subject_digest", "client_ref", "resource", "scopes"}
)
_BINDING_KEYS = _PRINCIPAL_KEYS | {"permission_digest"}
_ENVELOPE_KEYS = frozenset({"schema", "enabled", "binding"})
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


def validate_coo_binding(value: object, policy: ResourcePolicy) -> dict[str, Any]:
    """Validate one closed installed COO client binding.

    permission_digest is an enrollment-owner receipt digest. This reducer
    verifies its shape; it does not mint or reinterpret that receipt as
    mission authority.
    """
    policy = validate_resource_policy(policy)
    if tuple(policy.required_scopes) != COO_SCOPES:
        raise ValueError("access_denied")
    if not isinstance(value, Mapping) or set(value) != _ENVELOPE_KEYS:
        raise ValueError("access_denied")
    if value.get("schema") != BINDING_SCHEMA or type(value.get("enabled")) is not bool:
        raise ValueError("access_denied")
    binding = value.get("binding")
    if not value["enabled"]:
        if binding is not None:
            raise ValueError("access_denied")
        return {"schema": BINDING_SCHEMA, "enabled": False, "binding": None}
    if not isinstance(binding, Mapping) or set(binding) != _BINDING_KEYS:
        raise ValueError("access_denied")
    expected_issuer_digest = hashlib.sha256(policy.issuer.encode("utf-8")).hexdigest()
    if (
        binding.get("policy_id") != policy.policy_id
        or binding.get("issuer_digest") != expected_issuer_digest
        or binding.get("subject_digest") not in policy.allowed_subject_digests
        or binding.get("resource") != policy.resource
        or binding.get("scopes") != list(COO_SCOPES)
        or any(
            type(binding.get(key)) is not str
            or _HEX64.fullmatch(binding[key]) is None
            for key in ("issuer_digest", "subject_digest", "client_ref", "permission_digest")
        )
    ):
        raise ValueError("access_denied")
    return json.loads(_canonical(value))


def coo_authorizer(*, policy: ResourcePolicy, load_binding: Callable[[], object]):
    """Return an exact principal gate that reloads sealed binding every call."""
    if not callable(load_binding):
        raise ValueError("access_denied")
    selected_policy = validate_resource_policy(policy)
    validate_coo_binding(load_binding(), selected_policy)

    def binding_digest(principal: VerifiedPrincipal) -> str | None:
        try:
            frame = principal_frame(principal)
            current = validate_coo_binding(load_binding(), selected_policy)
            binding = current["binding"]
            if (
                current["enabled"] is True
                and isinstance(binding, dict)
                and all(frame[key] == binding[key] for key in _PRINCIPAL_KEYS)
            ):
                return _digest(binding)
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
    "COO_SCOPES",
    "READ_SCOPE",
    "coo_authorizer",
    "principal_frame",
    "validate_coo_binding",
]
