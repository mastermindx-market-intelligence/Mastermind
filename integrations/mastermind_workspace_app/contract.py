"""Workspace authentication adapters over the canonical shared framing contract.

Keep the established integration import path and object identities, including
private helpers consumed by existing callers. Pure owners import common directly.
"""
from __future__ import annotations

from common.executive_workspace_contract import (  # noqa: F401
    hashlib,
    json,
    re,
    Mapping,
    JOB_ID_RE,
    RESOURCE,
    SCOPE,
    FRAME_SCHEMA,
    FRAME_SCHEMA_V2,
    PROGRAMS_SCHEMA,
    OBSERVATION_SCHEMA,
    RESULT_OBSERVATION_SCHEMA,
    RESULT_BODY_SCHEMA,
    PROJECTION_SCHEMA,
    FABRIC_VIEW_SCHEMA_V2,
    FABRIC_VIEW_SCHEMA_V3,
    WORK_SCHEMA,
    WORK_REFUSAL_REASON_CODES,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    MAX_RESULT_RESPONSE_BYTES,
    _WORK_REF,
    _JOB_ID_RE_V2,
    _JOB_ID_MAX,
    _ATTEMPT_ID,
    _DIGEST_64,
    PRINCIPAL_KEYS,
    canonical,
    digest,
    selection,
    _check_work_ref,
    _check_job_id,
    _check_attempt_id,
    _check_envelope_digest,
    v2_selection,
    validate_v2_frame,
    response_ceiling_for,
    validate_frame,
    error,
    bounded_canonical,
    BINDINGS_SCHEMA,
    _BINDING_KEYS,
    _HEX,
    permission_stamp,
)


def principal_frame(principal):
    from integrations.business_mcp_auth.contracts import VerifiedPrincipal
    if type(principal) is not VerifiedPrincipal:
        raise ValueError("access_denied")
    return {key: list(principal.scopes) if key == "scopes" else getattr(principal, key)
            for key in PRINCIPAL_KEYS}



def validate_workspace_bindings(value, policy):
    """Validate the existing sealed owner's two acquisition permission slots.

    permission_digest is the enrolled owner receipt's digest, not a content
    grant. This pure function cannot enroll a client or mint that receipt.
    """
    from integrations.business_mcp_auth.contracts import validate_resource_policy
    policy = validate_resource_policy(policy)
    if policy.resource != RESOURCE or policy.required_scopes != (SCOPE,):
        raise ValueError("access_denied")
    if (type(value) is not dict or set(value) != {"schema", "profiles"}
            or value["schema"] != BINDINGS_SCHEMA or type(value["profiles"]) is not dict
            or set(value["profiles"]) != {"web", "mac"}):
        raise ValueError("access_denied")
    issuer = hashlib.sha256(policy.issuer.encode()).hexdigest()
    clients = set()
    for slot in value["profiles"].values():
        if type(slot) is not dict or set(slot) != {"enabled", "binding"} or type(slot["enabled"]) is not bool:
            raise ValueError("access_denied")
        binding = slot["binding"]
        if binding is None:
            if slot["enabled"]:
                raise ValueError("access_denied")
            continue
        if (type(binding) is not dict or set(binding) != _BINDING_KEYS
                or binding["policy_id"] != policy.policy_id or binding["issuer_digest"] != issuer
                or binding["subject_digest"] not in policy.allowed_subject_digests
                or binding["resource"] != RESOURCE or binding["scopes"] != [SCOPE]
                or any(type(binding[k]) is not str or _HEX.fullmatch(binding[k]) is None
                       for k in ("issuer_digest", "subject_digest", "client_ref", "permission_digest"))
                or binding["client_ref"] in clients):
            raise ValueError("access_denied")
        clients.add(binding["client_ref"])
    # Return detached closed bytes: no caller-owned mutable dict aliases.
    return json.loads(canonical(value))



def workspace_authorizers(*, policy, load_bindings):
    """Construct both App/control gates using the existing sealed-config loader.

    Reload on every check, including the post-read release check. No global
    principal, cache of grants, new file, registry or permission fallback.
    """
    if not callable(load_bindings):
        raise ValueError("access_denied")
    validate_workspace_bindings(load_bindings(), policy)

    def binding_digest(principal):
        try:
            if type(principal) is not dict:
                principal = principal_frame(principal)
            bindings = validate_workspace_bindings(load_bindings(), policy)
            matches = [slot["binding"] for slot in bindings["profiles"].values()
                       if slot["enabled"] and slot["binding"] is not None
                       and all(principal[k] == slot["binding"][k] for k in PRINCIPAL_KEYS)]
            return digest(matches[0]) if len(matches) == 1 else None
        except Exception:
            return None

    def authorize_frame(principal):
        try:
            if type(principal) is not dict or set(principal) != PRINCIPAL_KEYS:
                return False
            bindings = validate_workspace_bindings(load_bindings(), policy)
            return any(slot["enabled"] and slot["binding"] is not None
                       and all(principal[k] == slot["binding"][k] for k in PRINCIPAL_KEYS)
                       for slot in bindings["profiles"].values())
        except Exception:
            return False

    def authorize_principal(principal):
        try:
            return authorize_frame(principal_frame(principal))
        except Exception:
            return False
    authorize_principal.binding_digest = binding_digest
    authorize_frame.binding_digest = binding_digest
    return authorize_principal, authorize_frame
