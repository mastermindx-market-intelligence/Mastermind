"""Closed workspace transport framing, independent of cache and Runtime owners."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

from control_plane.wake_events import JOB_ID_RE

RESOURCE = "https://mcp.mastermind-x.com/workspace/read"
SCOPE = "mastermind.workspace.read"
FRAME_SCHEMA = "mastermind.executive_workspace_read.v1"
PROGRAMS_SCHEMA = "mastermind.workspace_programs.v1"
OBSERVATION_SCHEMA = "mastermind.workspace_source_observation.v1"
MAX_REQUEST_BYTES = 8192
MAX_RESPONSE_BYTES = 2_000_000
_WORK_REF = re.compile(r"WS:[A-Z0-9][A-Za-z0-9._-]{1,63}")
PRINCIPAL_KEYS = frozenset({"policy_id", "issuer_digest", "subject_digest", "client_ref", "resource", "scopes"})


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def selection(value):
    if (type(value) is not dict or set(value) != {"work_ref", "root_job_id"}
            or type(value["work_ref"]) is not str or not _WORK_REF.fullmatch(value["work_ref"])
            or type(value["root_job_id"]) is not str or len(value["root_job_id"]) > 64
            or not JOB_ID_RE.fullmatch(value["root_job_id"])):
        raise ValueError("invalid_input")
    return dict(value)


def principal_frame(principal):
    from integrations.business_mcp_auth.contracts import VerifiedPrincipal
    if type(principal) is not VerifiedPrincipal:
        raise ValueError("access_denied")
    return {key: list(principal.scopes) if key == "scopes" else getattr(principal, key)
            for key in PRINCIPAL_KEYS}


def validate_frame(frame):
    if (type(frame) is not dict or set(frame) != {"schema", "operation", "selection", "principal"}
            or frame["schema"] != FRAME_SCHEMA or frame["operation"] not in ("programs", "mission")
            or type(frame["principal"]) is not dict or set(frame["principal"]) != PRINCIPAL_KEYS
            or frame["principal"]["resource"] != RESOURCE or frame["principal"]["scopes"] != [SCOPE]
            or any(type(frame["principal"][key]) is not str or not 1 <= len(frame["principal"][key]) <= 256
                   for key in PRINCIPAL_KEYS - {"scopes"})
            or len(canonical(frame)) + 1 > MAX_REQUEST_BYTES):
        raise ValueError("invalid_input")
    if frame["operation"] == "programs":
        if frame["selection"] is not None:
            raise ValueError("invalid_input")
    else:
        selection(frame["selection"])
    return frame


def error(code, status):
    return {"ok": False, "status": status, "error": {"code": code, "message": "workspace read refused"}}


def bounded_canonical(value, *, limit=MAX_RESPONSE_BYTES):
    """Serialize a closed response without retaining bytes beyond its fixed cap."""
    chunks = []
    length = 0
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    for chunk in encoder.iterencode(value):
        encoded = chunk.encode("utf-8")
        length += len(encoded)
        if length > limit:
            raise ValueError("source_unavailable")
        chunks.append(encoded)
    return b"".join(chunks)


BINDINGS_SCHEMA = "mastermind.workspace_acquisition_bindings.v1"
_BINDING_KEYS = PRINCIPAL_KEYS | {"permission_digest"}
_HEX = re.compile(r"[0-9a-f]{64}")


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


def permission_stamp(authorizer, principal):
    """Request-owned stamp for the existing sealed permission receipt, if supplied."""
    stamp = getattr(authorizer, "binding_digest", None)
    if not callable(stamp):
        return None
    try:
        value = stamp(principal)
    except Exception:
        raise ValueError("access_denied") from None
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("access_denied")
    return value
