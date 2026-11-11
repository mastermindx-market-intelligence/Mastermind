"""Frozen contract for the executive workspace result-references route.

Closed body vocabulary for HTTP operation ``result_references`` over the
existing v2 workspace read frame.  The route answers one normalized
``{work_ref, root_job_id}`` selection with the already-acquired Fabric v3
result-reference index for that root — never with result content, and
never with a Job, Attempt, digest, URL or path as a list-request input.

The body is fail-closed.  An AVAILABLE body carries the actual index with
a finalized SAME generation receipt, the exact existing
``mastermind.workspace_source_observation.v1`` owner pair receipt from the
cache bracket around the single bounded Fabric v3 read, and an orientation
catalogue.  An UNAVAILABLE body releases no source internals at all: null
index, null control-room/runtime receipts, and the fixed UNKNOWN
catalogue.  The whole canonical framed ``{ok:true,result:BODY}``
serialization plus its trailing LF must fit inside the existing 16384-byte
result ceiling; the producer translates an over-budget AVAILABLE body into
the typed OVER_BUDGET unavailable shape instead of truncating the index or
fabricating absence after the fact.

Authentication, final permission and transport framing remain the
existing frame owner's unchanged authority; nothing in this module grants
or re-checks either.
"""

from __future__ import annotations

from common.executive_workspace_contract import (
    FRAME_SCHEMA_V2,
    MAX_REQUEST_BYTES,
    MAX_RESULT_RESPONSE_BYTES,
    OBSERVATION_SCHEMA,
    canonical,
    v2_selection,
)

#: Result body schema of this route (distinct from the frame schema).
SCHEMA = "mastermind.workspace_result_references.v1"
#: Fixed HTTP operation name routed by the existing v2 frame transport.
OPERATION = "result_references"
#: The route rides the existing closed v2 frame envelope unchanged.
FRAME_KEYS = frozenset({"schema", "operation", "selection", "principal"})
#: Frozen closed seven-key body shape.  There is no ``mission_current``
#: field: the catalogue is orientation only.
BODY_KEYS = frozenset({
    "schema", "selection", "availability", "reason_codes", "index",
    "source_observation", "catalogue",
})
#: Exact existing ``mastermind.workspace_source_observation.v1`` shape.
SOURCE_OBSERVATION_KEYS = frozenset({
    "schema", "state", "selection", "control_room", "runtime",
})
CATALOGUE_KEYS = frozenset({"generated_at", "freshness"})
#: The existing seven-key owner pair receipt the read service's
#: ``_observation`` emits for one cache bracket around the Fabric v3 read.
CONTROL_ROOM_RECEIPT_KEYS = frozenset({
    "instance_before", "instance_after",
    "publication_before", "publication_after",
    "document_digest", "source_validity_digest", "cache_currentness_digest",
})
AVAILABILITY_STATES = ("AVAILABLE", "UNAVAILABLE")
#: Closed refusal vocabulary.  AVAILABLE bodies carry no reason code;
#: UNAVAILABLE bodies carry exactly one.
REASON_CODES = frozenset({
    "SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "OVER_BUDGET",
    "REFERENCE_INDEX_UNAVAILABLE",
})
#: Index availability an AVAILABLE body may carry.  The existing owner
#: legitimately emits PARTIAL (real omissions/truncation); a genuinely
#: UNAVAILABLE index is refused into the typed unavailable body instead.
INDEX_AVAILABILITY_STATES = ("AVAILABLE", "PARTIAL")
CATALOGUE_FRESHNESS = ("CURRENT", "STALE", "UNKNOWN")


def selection(value):
    """Normalized ``{root_job_id, work_ref}`` selection for this route.

    The frozen request grammar is exactly the closed two-key mission v3
    selector — the same work_ref and root job identity, nothing else.
    """
    return v2_selection(value, "mission_v3")


def frame_selection(frame):
    """Validated normalized selection for one ``result_references`` frame.

    Frame envelope, size bound and the frozen selector grammar are checked
    here with the established ``ValueError("invalid_input")`` refusal.  The
    principal is only required to be present as a mapping: authentication
    and final permission stay with the existing frame owner, and this
    module never duplicates that authority.
    """
    if (type(frame) is not dict or set(frame) != FRAME_KEYS
            or frame["schema"] != FRAME_SCHEMA_V2
            or frame["operation"] != OPERATION
            or type(frame["principal"]) is not dict):
        raise ValueError("invalid_input")
    if len(canonical(frame)) + 1 > MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    return selection(frame["selection"])


def unavailable(selection, reason):
    """Typed UNAVAILABLE body for one closed reason code.

    Releases no source internals: null index, the fixed UNKNOWN catalogue,
    and a five-key source observation whose state is CONFLICT exactly when
    the reason is SOURCE_CHANGED (else UNKNOWN) with null control-room and
    runtime receipts.
    """
    # The parameter shadows the module-level ``selection`` helper, so the
    # frozen selector grammar is invoked through its underlying owner.
    selected = v2_selection(selection, "mission_v3")
    if type(reason) is not str or reason not in REASON_CODES:
        raise ValueError("invalid_input")
    body = {
        "schema": SCHEMA,
        "selection": selected,
        "availability": "UNAVAILABLE",
        "reason_codes": [reason],
        "index": None,
        "source_observation": {
            "schema": OBSERVATION_SCHEMA,
            "state": "CONFLICT" if reason == "SOURCE_CHANGED" else "UNKNOWN",
            "selection": selected,
            "control_room": None,
            "runtime": None,
        },
        "catalogue": {"generated_at": None, "freshness": "UNKNOWN"},
    }
    return {"ok": True, "result": validate_body(body, selected)}


def validate_body(body, selected):
    """Validate one result-references body against the frozen contract.

    Returns the body unchanged, or raises ``ValueError`` on any shape,
    enum, partition, cross-receipt or budget deviation.  The AVAILABLE
    index is validated by the existing owner's closed nine-key index
    validator — never by a local re-derivation.
    """
    selected = selection(selected)
    if (type(body) is not dict or set(body) != BODY_KEYS
            or body["schema"] != SCHEMA
            or body["availability"] not in AVAILABILITY_STATES
            or body["selection"] != selected):
        raise ValueError("invalid result-references body")
    codes = body["reason_codes"]
    if (type(codes) is not list
            or any(type(code) is not str or code not in REASON_CODES
                   for code in codes)):
        raise ValueError("invalid result-references reason codes")
    observation = body["source_observation"]
    if (type(observation) is not dict
            or set(observation) != SOURCE_OBSERVATION_KEYS
            or observation["schema"] != OBSERVATION_SCHEMA
            or observation["selection"] != selected):
        raise ValueError("invalid result-references source observation")
    catalogue = body["catalogue"]
    if type(catalogue) is not dict or set(catalogue) != CATALOGUE_KEYS:
        raise ValueError("invalid result-references catalogue")
    if catalogue["freshness"] not in CATALOGUE_FRESHNESS:
        raise ValueError("invalid result-references catalogue freshness")
    generated_at = catalogue["generated_at"]
    if generated_at is not None and type(generated_at) is not str:
        raise ValueError("invalid result-references catalogue timestamp")
    if body["availability"] == "AVAILABLE":
        _validate_available(body, observation, selected)
    else:
        _validate_unavailable(body, observation, catalogue)
    if len(canonical({"ok": True, "result": body})) + 1 > MAX_RESULT_RESPONSE_BYTES:
        raise ValueError("result-references response over budget")
    return body


def _validate_available(body, observation, selected):
    """AVAILABLE: actual readable index, finalized generation, SAME receipts."""
    if body["reason_codes"] != []:
        raise ValueError("available result-references carries no reason codes")
    index = body["index"]
    if type(index) is not dict:
        raise ValueError("available result-references requires the actual index")
    from control_plane.mission_workspace import _validate_result_reference_index
    index = _validate_result_reference_index(index)
    if index["availability"] not in INDEX_AVAILABILITY_STATES:
        raise ValueError("available result-references index is not readable")
    if index["root_job_id"] != selected["root_job_id"]:
        raise ValueError("available result-references index is for another root")
    generation = index["generation"]
    if generation["state"] != "SAME":
        raise ValueError("available result-references index generation is not finalized")
    if observation["state"] != "SAME":
        raise ValueError("available result-references observation is not SAME")
    control_room = observation["control_room"]
    if (type(control_room) is not dict
            or set(control_room) != CONTROL_ROOM_RECEIPT_KEYS
            or type(control_room["publication_before"]) is not int
            or type(control_room["publication_after"]) is not int
            or any(type(control_room[key]) is not str or not control_room[key]
                   for key in CONTROL_ROOM_RECEIPT_KEYS
                   - {"publication_before", "publication_after"})):
        raise ValueError("available result-references control room receipt is malformed")
    if observation["runtime"] != generation:
        raise ValueError(
            "available result-references runtime receipt must equal the index generation")


def _validate_unavailable(body, observation, catalogue):
    """UNAVAILABLE: one closed reason code and no released source internals."""
    if len(body["reason_codes"]) != 1:
        raise ValueError("unavailable result-references requires one reason code")
    if body["index"] is not None:
        raise ValueError("unavailable result-references carries no index")
    if catalogue != {"generated_at": None, "freshness": "UNKNOWN"}:
        raise ValueError("unavailable result-references catalogue is fixed")
    if observation["control_room"] is not None or observation["runtime"] is not None:
        raise ValueError("unavailable result-references releases no source receipt")
    expected = "CONFLICT" if body["reason_codes"][0] == "SOURCE_CHANGED" else "UNKNOWN"
    if observation["state"] != expected:
        raise ValueError("unavailable result-references observation state mismatch")
