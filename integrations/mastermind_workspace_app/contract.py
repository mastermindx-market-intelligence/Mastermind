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
    FRAME_SCHEMA_V3, PLAN_BODY_SCHEMA, PLAN_OBSERVATION_SCHEMA,
    MAX_PLAN_RESPONSE_BYTES, PLAN_REFUSAL_REASONS,
    v3_selection, validate_v3_frame, plan_unavailable, validate_available_plan_observation,
    PROGRAMS_SCHEMA,
    OBSERVATION_SCHEMA,
    RESULT_OBSERVATION_SCHEMA,
    RESULT_BODY_SCHEMA,
    PROJECTION_SCHEMA,
    FABRIC_VIEW_SCHEMA_V2,
    FABRIC_VIEW_SCHEMA_V3,
    WORK_SCHEMA,
    WORK_REFUSAL_REASON_CODES,
    QUEUE_EFFECT_EXCEPTION_REASONS,
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



MEMBER_BINDINGS_SCHEMA = "mastermind.workspace_acquisition_bindings.v2"
ACTION_BINDINGS_SCHEMA = "mastermind.workspace_acquisition_bindings.v3"
CONTROL_ROOM_ACTIONS = frozenset({"discover", "open", "bind", "unbind", "refresh-builds"})
MAX_MEMBER_PROFILES = 128
_PROFILE_REF = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")


def validate_workspace_bindings(value, policy):
    """Validate versioned membership in the existing sealed permission owner.

    V1 retains exactly web/mac and its original unique-client semantics. V2
    permits bounded enrolled subject/client pairs sharing a public OAuth client.
    primary_profile is a designation, never an additional scope or admin grant.
    permission_digest still comes from the actual enrolled owner's receipt.
    V3 adds explicit per-action receipt digests to this same sealed owner.
    Disabled profiles have no retained action grants; READ receipt reuse is
    refused. Neither membership nor primary designation grants an action.
    No file, principal, token, enrollment, issuer or authority is created here.
    """
    from integrations.business_mcp_auth.contracts import validate_resource_policy
    policy = validate_resource_policy(policy)
    if policy.resource != RESOURCE or policy.required_scopes != (SCOPE,):
        raise ValueError("access_denied")
    if type(value) is not dict or type(value.get("profiles")) is not dict:
        raise ValueError("access_denied")
    actions = value.get("schema") == ACTION_BINDINGS_SCHEMA
    members = actions or value.get("schema") == MEMBER_BINDINGS_SCHEMA
    if not members:
        if (set(value) != {"schema", "profiles"} or value.get("schema") != BINDINGS_SCHEMA
                or set(value["profiles"]) != {"web", "mac"}):
            raise ValueError("access_denied")
    elif (set(value) != {"schema", "profiles", "primary_profile"}
            or not 1 <= len(value["profiles"]) <= MAX_MEMBER_PROFILES
            or any(type(ref) is not str or _PROFILE_REF.fullmatch(ref) is None
                   for ref in value["profiles"])
            or (value["primary_profile"] is not None and (
                type(value["primary_profile"]) is not str
                or value["primary_profile"] not in value["profiles"]))):
        raise ValueError("access_denied")
    issuer = hashlib.sha256(policy.issuer.encode()).hexdigest()
    clients = set()
    principal_pairs = set()
    slot_keys = {"enabled", "binding", "control_room_actions"} if actions else {"enabled", "binding"}
    for slot in value["profiles"].values():
        if type(slot) is not dict or set(slot) != slot_keys or type(slot["enabled"]) is not bool:
            raise ValueError("access_denied")
        grants = slot["control_room_actions"] if actions else {}
        if actions and (type(grants) is not dict or set(grants) != CONTROL_ROOM_ACTIONS
                or any(value is not None and (type(value) is not str or _HEX.fullmatch(value) is None)
                       for value in grants.values())
                or (not slot["enabled"] and any(value is not None for value in grants.values()))):
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
                or (not members and binding["client_ref"] in clients)
                or (binding["subject_digest"], binding["client_ref"]) in principal_pairs):
            raise ValueError("access_denied")
        if any(value == binding["permission_digest"] for value in grants.values()):
            raise ValueError("access_denied")
        clients.add(binding["client_ref"])
        principal_pairs.add((binding["subject_digest"], binding["client_ref"]))
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


def workspace_control_room_authorizers(*, policy, load_bindings, action):
    """Bind one explicit action grant to the existing sealed membership owner.

    Legacy membership always denies actions. Every check reloads the same
    owner; no grant cache or permission fallback is introduced. Stamps bind
    this action and member, so unrelated action revocation stays independent.
    Actual receipt provenance and sealed installation remain owner duties.
    """
    if type(action) is not str or action not in CONTROL_ROOM_ACTIONS or not callable(load_bindings):
        raise ValueError("access_denied")
    validate_workspace_bindings(load_bindings(), policy)

    def binding_digest(principal):
        try:
            if type(principal) is not dict:
                principal = principal_frame(principal)
            if set(principal) != PRINCIPAL_KEYS:
                return None
            bindings = validate_workspace_bindings(load_bindings(), policy)
            if bindings["schema"] != ACTION_BINDINGS_SCHEMA:
                return None
            matches = [slot for slot in bindings["profiles"].values()
                       if slot["enabled"] and slot["binding"] is not None
                       and all(principal[k] == slot["binding"][k] for k in PRINCIPAL_KEYS)]
            if len(matches) != 1:
                return None
            slot = matches[0]
            grant = slot["control_room_actions"][action]
            if grant is None:
                return None
            return digest({
                "schema": "mastermind.workspace_control_room_permission.v1",
                "binding": slot["binding"], "action": action, "permission_digest": grant,
            })
        except Exception:
            return None

    def authorize_frame(principal):
        return type(principal) is dict and binding_digest(principal) is not None

    def authorize_principal(principal):
        try:
            return authorize_frame(principal_frame(principal))
        except Exception:
            return False

    authorize_principal.binding_digest = binding_digest
    authorize_frame.binding_digest = binding_digest
    return authorize_principal, authorize_frame
