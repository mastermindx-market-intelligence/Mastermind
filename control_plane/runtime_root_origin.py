"""Pure legacy/root-creation origin classifier.

Answers one question about a canonical ROOT job creation record: was this
root created as a generic (NON_CEO) creation, or as a LEGACY_CEO creation
carrying a ``mastermind.ceo_intent.v1`` provenance envelope?

The function is pure: no I/O, no thresholds, no candidate inference, no
normalization of malformed fields.  Anything unresolved, malformed,
conflicting or unsupported raises ``ValueError``.  Strict v2 orchestration
Jobs are deliberately NOT classified here — the Runtime's own strict v2
validator owns them and this module refuses every Job carrying non-null
orchestration metadata rather than competing with it.
"""

import re
from typing import Any, Mapping

__all__ = ["classify_legacy_root_creation"]

INTENT_SCHEMA = "mastermind.ceo_intent.v1"
BOOT_PACKET_SCHEMA = "mastermind.ceo_boot_packet.v1"
_CREATION_EVENT_TYPE = "JOB_CREATED"
_CREATION_STATUS = "QUEUED"
_COMMAND_PREFIX = "ceo-intent:"

_JOB_ID_RE = re.compile(r"JOB-[0-9]+\Z")
_INTENT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,63}\Z")
_ACTOR_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{1,63}\Z")
_LOWER_HEX64_RE = re.compile(r"[0-9a-f]{64}\Z")
_LOWER_HEX40_RE = re.compile(r"[0-9a-f]{40}\Z")
_WORKSTREAM_RE = re.compile(r"WS:[A-Z0-9][A-Za-z0-9._-]{1,63}\Z")

_PROVENANCE_KEYS = frozenset(
    {"schema", "intent_id", "actor", "fingerprint", "grounding", "workstream"}
)
_GROUNDING_KEYS = frozenset({"mastermind_sha", "macro_sha", "boot_packet_schema"})
_LEGACY_METADATA_FIELDS = ("orchestration_role", "orchestration_provenance_digest")
_EVENT_ATTRIBUTION_FIELDS = ("attempt_id", "worker_id", "quota_class")


def _fail(message: str) -> None:
    raise ValueError(f"runtime_root_origin: {message}")


def _is_plain_int(value: Any) -> bool:
    # bool is an int subclass; a boolean depth is malformed, never zero.
    return isinstance(value, int) and not isinstance(value, bool)


def _required_attr(obj: Any, name: str) -> Any:
    if not hasattr(obj, name):
        _fail(f"{type(obj).__name__} is missing required attribute {name!r}")
    return getattr(obj, name)


def _validate_job(job: Any) -> str:
    """Only a canonical root creation classifies: JOB-<digits>, self-rooted, depth 0."""
    job_id = _required_attr(job, "job_id")
    if not isinstance(job_id, str) or _JOB_ID_RE.fullmatch(job_id) is None:
        _fail(f"job_id is not a valid root job id: {job_id!r}")
    root_job_id = _required_attr(job, "root_job_id")
    if root_job_id != job_id:
        _fail(f"root_job_id {root_job_id!r} != job_id {job_id!r}; only root creations classify")
    parent_job_id = _required_attr(job, "parent_job_id")
    if parent_job_id is not None:
        _fail(f"parent_job_id is {parent_job_id!r}; only root creations classify")
    depth = _required_attr(job, "depth")
    if not _is_plain_int(depth) or depth != 0:
        _fail(f"depth is {depth!r}; root creations are integer 0")
    for field in ("orchestration_role", "orchestration_provenance",
                  "orchestration_provenance_digest"):
        if _required_attr(job, field) is not None:
            _fail(f"Job carries {field}; legacy classification is unresolved")
    return job_id


def _validate_event(job: Any, event: Any, job_id: str) -> Mapping[str, Any]:
    """Validate one creation envelope; the Runtime caller proves uniqueness."""
    if _required_attr(event, "event_type") != _CREATION_EVENT_TYPE:
        _fail(f"event_type is {_required_attr(event, 'event_type')!r}, not {_CREATION_EVENT_TYPE!r}")
    if _required_attr(event, "aggregate_type") != "job":
        _fail(f"aggregate_type is {_required_attr(event, 'aggregate_type')!r}, not 'job'")
    aggregate_id = _required_attr(event, "aggregate_id")
    event_job_id = _required_attr(event, "job_id")
    if aggregate_id != job_id or event_job_id != job_id:
        _fail(
            "creation event identity does not match the job: "
            f"aggregate_id={aggregate_id!r} job_id={event_job_id!r} job.job_id={job_id!r}"
        )
    for field in _EVENT_ATTRIBUTION_FIELDS:
        if getattr(event, field, None) is not None:
            _fail(f"creation event carries {field} attribution")
    payload = _required_attr(event, "payload")
    if not isinstance(payload, Mapping):
        _fail(f"creation event payload is {type(payload).__name__}, not a mapping")
    if payload.get("root_job_id") != job_id:
        _fail(f"payload root_job_id {payload.get('root_job_id')!r} != {job_id!r}")
    if "parent_job_id" not in payload or payload["parent_job_id"] is not None:
        _fail(f"payload parent_job_id is {payload.get('parent_job_id')!r}, not None")
    payload_depth = payload.get("depth")
    if not _is_plain_int(payload_depth) or payload_depth != 0:
        _fail(f"payload depth is {payload_depth!r}; creation depth is integer 0")
    if payload.get("status") != _CREATION_STATUS:
        # The CREATION state is what classifies; the job's current status is ignored.
        _fail(f"creation status is {payload.get('status')!r}, not {_CREATION_STATUS!r}")
    return payload


def _command_id(event: Any) -> Any:
    command_id = getattr(event, "command_id", None)
    if command_id is None:
        return None
    if not isinstance(command_id, str) or not command_id:
        _fail(f"event command_id is {command_id!r}; expected a nonempty string or None")
    return command_id


def _reject_orchestration_metadata(payload: Mapping[str, Any]) -> None:
    for field in _LEGACY_METADATA_FIELDS:
        if field in payload:
            _fail(
                f"payload carries {field}; strict orchestration Jobs are "
                "owned by the strict v2 validator, not this classifier"
            )


def _classify_generic(command_id: Any) -> dict[str, Any]:
    if command_id is not None and command_id.startswith(_COMMAND_PREFIX):
        _fail(
            f"command_id {command_id!r} claims the {_COMMAND_PREFIX} namespace without "
            "provenance; a typed prefix alone is not proof of origin"
        )
    return {"kind": "NON_CEO", "provenance": None}


def _classify_legacy(event: Any, provenance: Mapping[str, Any], command_id: Any) -> dict[str, Any]:
    keys = frozenset(provenance)
    if keys != _PROVENANCE_KEYS:
        missing = sorted(_PROVENANCE_KEYS - keys)
        unexpected = sorted(keys - _PROVENANCE_KEYS)
        _fail(
            "provenance is not the closed legacy v1 envelope: "
            f"missing={missing} unexpected={unexpected}"
        )
    schema = provenance["schema"]
    if schema != INTENT_SCHEMA:
        _fail(f"unsupported provenance schema {schema!r}; only {INTENT_SCHEMA!r} classifies here")
    intent_id = provenance["intent_id"]
    if not isinstance(intent_id, str) or _INTENT_ID_RE.fullmatch(intent_id) is None:
        _fail(f"provenance intent_id is malformed: {intent_id!r}")
    actor = provenance["actor"]
    if not isinstance(actor, str) or _ACTOR_RE.fullmatch(actor) is None:
        _fail(f"provenance actor is malformed: {actor!r}")
    fingerprint = provenance["fingerprint"]
    if not isinstance(fingerprint, str) or _LOWER_HEX64_RE.fullmatch(fingerprint) is None:
        _fail(f"provenance fingerprint is not lowercase 64-hex: {fingerprint!r}")
    if command_id != f"{_COMMAND_PREFIX}{intent_id}":
        _fail(
            f"event command_id {command_id!r} does not bind {_COMMAND_PREFIX}{intent_id!r}"
        )
    grounding = provenance["grounding"]
    if not isinstance(grounding, Mapping) or frozenset(grounding) != _GROUNDING_KEYS:
        _fail("provenance grounding is not the closed canonical grounding")
    safe_grounding: dict[str, Any] = {}
    for key in ("mastermind_sha", "macro_sha"):
        value = grounding[key]
        if not isinstance(value, str) or _LOWER_HEX40_RE.fullmatch(value) is None:
            _fail(f"grounding {key} is not lowercase 40-hex: {value!r}")
        safe_grounding[key] = value
    if grounding["boot_packet_schema"] != BOOT_PACKET_SCHEMA:
        _fail(f"grounding boot_packet_schema is {grounding['boot_packet_schema']!r}")
    safe_grounding["boot_packet_schema"] = BOOT_PACKET_SCHEMA
    workstream = provenance["workstream"]
    if not isinstance(workstream, str) or _WORKSTREAM_RE.fullmatch(workstream) is None:
        _fail(f"provenance workstream is missing or malformed: {workstream!r}")
    return {
        "kind": "LEGACY_CEO",
        "provenance": {
            "schema": schema,
            "intent_id": intent_id,
            "actor": actor,
            "fingerprint": fingerprint,
            "grounding": safe_grounding,
            "workstream": workstream,
        },
    }


def classify_legacy_root_creation(job: Any, event: Any) -> dict[str, Any]:
    """Classify one canonical ROOT creation as NON_CEO or LEGACY_CEO.

    ``job`` and ``event`` are the existing attribute-bearing Job and creation
    Event records.  Returns ``{"kind": "NON_CEO", "provenance": None}`` for a
    generic root creation, or ``{"kind": "LEGACY_CEO", "provenance": <copy>}``
    for a ``mastermind.ceo_intent.v1`` root creation.  Anything else raises
    ``ValueError``: unresolved, malformed, conflicting and unsupported records
    are never silently classified.  Strict v2 Jobs (non-null orchestration
    metadata) are refused here; the Runtime's strict v2 validator owns them.
    """
    job_id = _validate_job(job)
    payload = _validate_event(job, event, job_id)
    _reject_orchestration_metadata(payload)
    command_id = _command_id(event)
    if "provenance" in payload and payload["provenance"] is None:
        _fail("payload provenance is explicitly null: malformed, not generic absence")
    provenance = payload.get("provenance")
    if provenance is None:
        return _classify_generic(command_id)
    if not isinstance(provenance, Mapping):
        _fail(f"payload provenance is {type(provenance).__name__}, not a mapping")
    return _classify_legacy(event, provenance, command_id)
