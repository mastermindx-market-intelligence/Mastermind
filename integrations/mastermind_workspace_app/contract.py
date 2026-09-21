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
#: v2 frame schema and result observation schema for the result-detail and
#: Mission v3 routes.  Frozen by the parent-ratified workspace contract.
FRAME_SCHEMA_V2 = "mastermind.executive_workspace_read.v2"
PROGRAMS_SCHEMA = "mastermind.workspace_programs.v1"
OBSERVATION_SCHEMA = "mastermind.workspace_source_observation.v1"
RESULT_OBSERVATION_SCHEMA = "mastermind.workspace_result_observation.v1"
RESULT_BODY_SCHEMA = "mastermind.workspace_role_result.v1"
PROJECTION_SCHEMA = "mastermind.fabric_role_result_view.v1"
FABRIC_VIEW_SCHEMA_V2 = "mastermind.fabric_job_view.v2"
FABRIC_VIEW_SCHEMA_V3 = "mastermind.fabric_job_view.v3"
MAX_REQUEST_BYTES = 8192
MAX_RESPONSE_BYTES = 2_000_000
#: Result response ceiling — the entire canonical UTF-8 socket
#: ``{ok:true,result:BODY}`` serialization including the trailing LF must fit
#: in this many bytes, and the public BODY serialization must also fit alone.
MAX_RESULT_RESPONSE_BYTES = 16_384
_WORK_REF = re.compile(r"WS:[A-Z0-9][A-Za-z0-9._-]{1,63}")
#: Frozen v2 C public shape JOB-[0-9]{1,9} with the existing max16-character
#: guard.  Differs from the legacy ``wake_events.JOB_ID_RE`` (3+ digits) only
#: in the lower bound, which the v2 contract freezes to 1+ to match the
#: ``D_IMPLEMENTATION_PACKET`` job ID grammar.
_JOB_ID_RE_V2 = re.compile(r"^JOB-[0-9]{1,9}$")
_JOB_ID_MAX = 16
_ATTEMPT_ID = re.compile(r"^ATT-[0-9a-f]{32}$")
_DIGEST_64 = re.compile(r"^[0-9a-f]{64}$")
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


# ---------------------------------------------------------------------------
# v2 frozen selector grammar — same work_ref/job/attempt/digest patterns.
# ---------------------------------------------------------------------------


def _check_work_ref(value):
    return type(value) is str and _WORK_REF.fullmatch(value) is not None


def _check_job_id(value):
    return (type(value) is str and len(value) <= _JOB_ID_MAX
            and _JOB_ID_RE_V2.fullmatch(value) is not None)


def _check_attempt_id(value):
    return type(value) is str and _ATTEMPT_ID.fullmatch(value) is not None


def _check_envelope_digest(value):
    return type(value) is str and _DIGEST_64.fullmatch(value) is not None


def v2_selection(value, operation):
    """Validate the v2 selection exactly against the closed operation grammar.

    Returns a detached dict.  Raises ``ValueError("invalid_input")`` on any
    shape deviation, missing/extra/duplicate field, malformed selector token,
    or operation/grammar confusion.  These are selectors, not authority —
    Runtime remains the actual acceptor.
    """
    if type(value) is not dict:
        raise ValueError("invalid_input")
    keys = set(value)
    if operation == "result":
        expected = {"work_ref", "root_job_id", "job_id", "attempt_id", "result_envelope_digest"}
    elif operation == "mission_v3":
        expected = {"work_ref", "root_job_id"}
    else:
        raise ValueError("invalid_input")
    if keys != expected:
        raise ValueError("invalid_input")
    if not _check_work_ref(value["work_ref"]):
        raise ValueError("invalid_input")
    if not _check_job_id(value["root_job_id"]):
        raise ValueError("invalid_input")
    if operation == "result":
        if not _check_job_id(value["job_id"]):
            raise ValueError("invalid_input")
        if not _check_attempt_id(value["attempt_id"]):
            raise ValueError("invalid_input")
        if not _check_envelope_digest(value["result_envelope_digest"]):
            raise ValueError("invalid_input")
    return {key: value[key] for key in sorted(expected)}


def validate_v2_frame(frame):
    """Validate one frozen v2 frame: schema, operation, selection, principal."""
    if (type(frame) is not dict or set(frame) != {"schema", "operation", "selection", "principal"}
            or frame["schema"] != FRAME_SCHEMA_V2
            or frame["operation"] not in ("mission_v3", "result")
            or type(frame["principal"]) is not dict or set(frame["principal"]) != PRINCIPAL_KEYS
            or frame["principal"]["resource"] != RESOURCE or frame["principal"]["scopes"] != [SCOPE]
            or any(type(frame["principal"][key]) is not str or not 1 <= len(frame["principal"][key]) <= 256
                   for key in PRINCIPAL_KEYS - {"scopes"})):
        raise ValueError("invalid_input")
    v2_selection(frame["selection"], frame["operation"])
    if len(canonical(frame)) + 1 > MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    return frame


def response_ceiling_for(operation):
    """Return the frozen response ceiling for the supplied v2 operation.

    Returns the existing Mission v2 ``MAX_RESPONSE_BYTES`` for unknown or
    v1 operations and the 16384-byte result ceiling for ``"result"`` so the
    caller cannot widen an unknown frame to a larger ceiling.
    """
    if operation == "result":
        return MAX_RESULT_RESPONSE_BYTES
    return MAX_RESPONSE_BYTES


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
