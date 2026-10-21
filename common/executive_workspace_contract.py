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
FRAME_SCHEMA_V3 = "mastermind.executive_workspace_read.v3"
PLAN_BODY_SCHEMA = "mastermind.workspace_admitted_execution_plan.v1"
PLAN_OBSERVATION_SCHEMA = "mastermind.workspace_plan_observation.v1"
MAX_PLAN_RESPONSE_BYTES = 16_384
PLAN_REFUSAL_REASONS = frozenset({
    "ADMISSION_NOT_ESTABLISHED", "ADMISSION_CONFLICT", "SOURCE_CHANGED",
    "SOURCE_UNAVAILABLE", "OVER_BUDGET", "CONTENT_WITHHELD",
    "CONTENT_OVER_BUDGET", "RESPONSE_OVER_BUDGET",
})
PROGRAMS_SCHEMA = "mastermind.workspace_programs.v1"
OBSERVATION_SCHEMA = "mastermind.workspace_source_observation.v1"
RESULT_OBSERVATION_SCHEMA = "mastermind.workspace_result_observation.v1"
RESULT_BODY_SCHEMA = "mastermind.workspace_role_result.v1"
PROJECTION_SCHEMA = "mastermind.fabric_role_result_view.v1"
FABRIC_VIEW_SCHEMA_V2 = "mastermind.fabric_job_view.v2"
FABRIC_VIEW_SCHEMA_V3 = "mastermind.fabric_job_view.v3"
WORK_SCHEMA = "mastermind.workspace_work_queue.v1"
#: Closed set of work-queue refusal reason codes the read service may emit
#: on a typed UNAVAILABLE body.  Anything outside this set is a contract
#: violation — the closed-key-set guard in the read service refuses it.
WORK_REFUSAL_REASON_CODES = frozenset({
    "source_unavailable",
    "runtime_observation_not_same",
    "projection_refused",
    "source_integrity_unverified",
})
MAX_REQUEST_BYTES = 8192
MAX_RESPONSE_BYTES = 2_000_000
#: Result response ceiling — the entire canonical UTF-8 socket
#: ``{ok:true,result:BODY}`` serialization including the trailing LF must fit
#: in this many bytes, and the public BODY serialization must also fit alone.
MAX_RESULT_RESPONSE_BYTES = 16_384
#: Closed vocabulary for ``effect_exception.reason`` in
#: ``mastermind.workspace_work_queue.v1``.  The composer emits the first
#: four (its own vocabulary for the control room / autonomy input it was
#: handed); the read service emits the fifth (its own vocabulary for
#: ``source_unavailable`` / ``projection_refused`` / etc. — see
#: :data:`WORK_REFUSAL_REASON_CODES`).  Anything outside this set on
#: ``effect_exception.reason`` is a contract violation.  Both producer
#: sites assert membership; the workspace-app contract facade re-exports
#: the constant so the facade-parity test exercises it.
QUEUE_EFFECT_EXCEPTION_REASONS = frozenset({
    "control_room_missing",
    "autonomy_missing",
    "no_exception_observed",
    "exception_observed",
    "read_refused",
})
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


def v3_selection(value):
    """The plan selector reuses the existing two-field v2 grammar."""
    return v2_selection(value, "mission_v3")


def validate_v3_frame(frame):
    """The separate v3 schema admits only the read-only admitted_plan operation."""
    if (type(frame) is not dict or set(frame) != {"schema", "operation", "selection", "principal"}
            or frame["schema"] != FRAME_SCHEMA_V3 or frame["operation"] != "admitted_plan"
            or type(frame["principal"]) is not dict or set(frame["principal"]) != PRINCIPAL_KEYS
            or frame["principal"]["resource"] != RESOURCE or frame["principal"]["scopes"] != [SCOPE]
            or any(type(frame["principal"][key]) is not str or not 1 <= len(frame["principal"][key]) <= 256
                   for key in PRINCIPAL_KEYS - {"scopes"})):
        raise ValueError("invalid_input")
    v3_selection(frame["selection"])
    if len(canonical(frame)) + 1 > MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    return frame


def validate_available_plan_observation(value, selected):
    """Validate the existing finalized public receipt without acquiring a source."""
    selected = v3_selection(selected)
    if (type(value) is not dict
            or set(value) != {"schema", "state", "selection", "control_room", "runtime"}
            or value["schema"] != PLAN_OBSERVATION_SCHEMA or value["state"] != "SAME"
            or type(value["selection"]) is not dict or value["selection"] != selected):
        raise ValueError("invalid_input")
    runtime, control_room = value["runtime"], value["control_room"]
    if (type(runtime) is not dict
            or set(runtime) != {"schema", "state", "source_identity", "before", "after"}
            or runtime["schema"] != "mastermind.runtime_read_observation.v1"
            or runtime["state"] != "SAME"
            or type(runtime["source_identity"]) is not str
            or re.fullmatch(r"[0-9a-f]{32}", runtime["source_identity"]) is None
            or type(runtime["before"]) is not int or runtime["before"] < 0
            or type(runtime["after"]) is not int or runtime["before"] != runtime["after"]):
        raise ValueError("invalid_input")
    if (type(control_room) is not dict
            or set(control_room) != {
                "instance_before", "instance_after", "publication_before", "publication_after",
                "document_digest", "source_validity_digest", "cache_currentness_digest"}
            or type(control_room["instance_before"]) is not str or not control_room["instance_before"]
            or type(control_room["instance_after"]) is not str
            or control_room["instance_before"] != control_room["instance_after"]
            or type(control_room["publication_before"]) is not int or control_room["publication_before"] <= 0
            or type(control_room["publication_after"]) is not int
            or control_room["publication_before"] != control_room["publication_after"]
            or any(type(control_room[key]) is not str
                   or _DIGEST_64.fullmatch(control_room[key]) is None
                   for key in ("document_digest", "source_validity_digest", "cache_currentness_digest"))):
        raise ValueError("invalid_input")


def plan_unavailable(selected, reason):
    """Small closed refusal shared by the producer and transport budget fences."""
    if reason not in PLAN_REFUSAL_REASONS:
        raise ValueError("invalid_input")
    selected = v3_selection(selected)
    return {"ok": True, "result": {
        "schema": PLAN_BODY_SCHEMA, "selection": dict(selected),
        "availability": "UNAVAILABLE", "reason_codes": [reason], "plan": None,
        "source_observation": {
            "schema": PLAN_OBSERVATION_SCHEMA, "selection": dict(selected),
            "state": "CONFLICT" if reason == "SOURCE_CHANGED" else "UNKNOWN",
            "control_room": None, "runtime": None,
        },
    }}


def response_ceiling_for(operation):
    """Return the frozen response ceiling for the supplied Workspace read operation.

    Returns the existing Mission v2 ``MAX_RESPONSE_BYTES`` for unknown or
    v1 operations and the 16384-byte ceiling for result and admitted-plan reads so the
    caller cannot widen an unknown frame to a larger ceiling.
    """
    if operation == "admitted_plan":
        return MAX_PLAN_RESPONSE_BYTES
    if operation == "result":
        return MAX_RESULT_RESPONSE_BYTES
    return MAX_RESPONSE_BYTES




def validate_frame(frame):
    if (type(frame) is not dict or set(frame) != {"schema", "operation", "selection", "principal"}
            or frame["schema"] != FRAME_SCHEMA or frame["operation"] not in ("programs", "work", "mission")
            or type(frame["principal"]) is not dict or set(frame["principal"]) != PRINCIPAL_KEYS
            or frame["principal"]["resource"] != RESOURCE or frame["principal"]["scopes"] != [SCOPE]
            or any(type(frame["principal"][key]) is not str or not 1 <= len(frame["principal"][key]) <= 256
                   for key in PRINCIPAL_KEYS - {"scopes"})
            or len(canonical(frame)) + 1 > MAX_REQUEST_BYTES):
        raise ValueError("invalid_input")
    if frame["operation"] in ("programs", "work"):
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
