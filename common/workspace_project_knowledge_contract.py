"""Closed DTO contracts for workspace project knowledge capture.

Schemas defined here:

* ``mastermind.workspace_project_knowledge.v1`` - catalogue of a workstream's
  project files, bounded record sample and communication-preference memory.
* ``mastermind.workspace_project_source.v1`` - one exact source open.
* ``mastermind.workspace_project_preference.v1`` - the project communication
  preference read.

Lower-core/common module: pure stdlib, no filesystem access, no network, no
``control_plane`` imports.  Capture code (``control_plane``) depends on this
module, never the reverse.  Validators never mutate caller state; every
validated value is returned as a canonical JSON copy.  A schema violation
raises ``ContractInvalid`` (a ``ValueError``): callers fail closed on it.

Canonical identity notes this revision enforces:

* ``work_ref`` is the colon citation form ``WS:<KEY>``; the key is upper-kebab
  of 2..64 characters and the canonical record filename is
  ``agentos/workstreams/WS-<KEY>.md``.
* Every ``revision`` is the actual Git blob SHA-1 of the exact bytes; only
  ``source.commit`` (and ``catalogue.source.commit``) carry the Macro commit.
* All bounded sizes are UTF-8 **byte** budgets, not character counts, and the
  only permitted control characters anywhere are LF, CR and TAB: every other
  C0, the whole C1 range and DEL are refused.
"""

from __future__ import annotations

import hashlib
import json
import re

__all__ = [
    "CATALOGUE_SCHEMA",
    "SOURCE_SCHEMA",
    "PREFERENCE_SCHEMA",
    "PREFERENCE_PAYLOAD_SCHEMA",
    "REPOSITORY",
    "REASON_CODES",
    "MAX_DISPLAY_NAME",
    "MAX_FILE_METADATA",
    "MAX_MEMORY_VALUE",
    "MAX_SOURCE_BODY",
    "MAX_SCANNED_RECORDS",
    "MAX_MATCHED_RECORDS",
    "ContractInvalid",
    "validate_selection",
    "validate_catalogue",
    "validate_source",
    "validate_memory",
    "validate_preference_payload",
    "unavailable_catalogue",
    "unavailable_source",
    "unavailable_memory",
    "empty_memory",
]

CATALOGUE_SCHEMA = "mastermind.workspace_project_knowledge.v1"
SOURCE_SCHEMA = "mastermind.workspace_project_source.v1"
PREFERENCE_SCHEMA = "mastermind.workspace_project_preference.v1"
PREFERENCE_PAYLOAD_SCHEMA = "agentos.project_preference.v1"

REPOSITORY = "mastermindx-market-intelligence/macro"
REPOSITORY_KEYS = ("macro", "terminal", "mastermind")
MEDIA_TYPES = ("text/markdown", "text/plain")
FILE_STATES = (
    "READABLE",
    "SOURCE_MISSING",
    "SOURCE_INVALID",
    "CONTENT_OVER_BUDGET",
    "UNSUPPORTED_SOURCE",
)
ORIGIN_KINDS = ("PRINCIPAL_UPLOAD", "DECLARED_ARTIFACT")
RECORD_KINDS = (
    "WORKSTREAM",
    "DECISION",
    "DISCOVERY",
    "HANDOFF",
    "PROJECT_PREFERENCE",
)
MEMORY_STATES = ("AVAILABLE", "EMPTY", "UNAVAILABLE")
FILE_COVERAGE_STATES = ("COMPLETE", "PARTIAL")
RECORD_COVERAGE_STATES = ("BOUNDED_SAMPLE",)
PREFERENCE_ORIGIN_KINDS = ("USER_EDIT", "CONVERSATION")
REASON_CODES = (
    "SOURCE_UNAVAILABLE",
    "SOURCE_CHANGED",
    "RECORD_NOT_FOUND",
    "SOURCE_MISMATCH",
    "SOURCE_INVALID",
    "CONTENT_OVER_BUDGET",
    "RESPONSE_OVER_BUDGET",
    "UNSUPPORTED_SOURCE",
    "CONFLICT",
)
AVAILABILITY = ("AVAILABLE", "UNAVAILABLE")
MEMORY_AVAILABILITY = ("AVAILABLE", "EMPTY", "UNAVAILABLE")
VIEWER_RELATION = "UNKNOWN"
SOURCE_REF_PREFIXES = ("project-file.v1.", "project-record.v1.")
SESSION_REPLY_PREFIX = "session-reply-"

MAX_DISPLAY_NAME = 128
MAX_FILE_METADATA = 32
MAX_MEMORY_VALUE = 2000
MAX_SOURCE_BODY = 32768
MAX_SCANNED_RECORDS = 128
MAX_MATCHED_RECORDS = 64
MAX_PATH = 512
MAX_TITLE = 512

_SHA40 = re.compile(r"[0-9a-f]{40}")
_SHA64 = re.compile(r"[0-9a-f]{64}")
# Colon citation form: WS: plus an upper-kebab key of 2..64 characters.
_WORK_REF = re.compile(r"WS-[A-Z0-9]+(?:-[A-Z0-9]+)*")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_STAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})"
)
# Permitted controls are exactly LF, CR and TAB.  Every other C0, the whole
# C1 range (U+0080..U+009F, reachable from valid UTF-8 such as b"\xc2\x80")
# and DEL are refused.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]")


class ContractInvalid(ValueError):
    """A value does not satisfy a closed schema.  Callers fail closed."""


def _fail(message: str) -> None:
    raise ContractInvalid(message)


def _ulen(value: str) -> int:
    """UTF-8 byte length: every bounded size in these schemas is a byte budget."""
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ContractInvalid("value is not encodable UTF-8: %s" % exc) from exc


def _plain(value, *, depth=0, budget=None, seen=None):
    if budget is None: budget = [8192]
    if seen is None: seen = set()
    budget[0] -= 1
    if budget[0] < 0 or depth > 48:
        _fail("response structure exceeds its bound")
    kind = type(value)
    if kind in (dict, list):
        if id(value) in seen: _fail("response cycle")
        seen.add(id(value))
        if kind is dict:
            for key, item in value.items():
                if type(key) is not str: _fail("response field type")
                _plain(item, depth=depth+1, budget=budget, seen=seen)
        else:
            for item in value: _plain(item, depth=depth+1, budget=budget, seen=seen)
        seen.remove(id(value))
    elif kind not in (str, int, float, bool, type(None)):
        _fail("response value type")


def _copy(value):
    """Canonical JSON copy: no caller mutation, custom dispatch or aliases."""
    _plain(value)
    try:
        return json.loads(
            json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))
        )
    except (TypeError, ValueError) as exc:
        raise ContractInvalid("value is not canonically JSON encodable: %s" % exc) from exc


def _keys(value, expected, field):
    if type(value) is not dict:
        _fail(field + " must be an object")
    extra = sorted(set(value) - set(expected))
    if extra:
        _fail(field + " has unexpected keys: " + ", ".join(extra))
    missing = [key for key in expected if key not in value]
    if missing:
        _fail(field + " is missing keys: " + ", ".join(missing))


def _text(value, field, *, allow_empty=False, max_len=None):
    if type(value) is not str:
        _fail(field + " must be a string")
    if not allow_empty and value == "":
        _fail(field + " must be nonempty")
    if _CONTROL.search(value):
        _fail(field + " carries control characters (only LF, CR, TAB allowed)")
    if max_len is not None and _ulen(value) > max_len:
        _fail(field + " exceeds " + str(max_len) + " UTF-8 bytes")
    return value


def _sha(value, field, digest):
    _text(value, field, max_len=digest)
    if digest == 40 and _SHA40.fullmatch(value) is None:
        _fail(field + " must be 40 lowercase hex")
    if digest == 64 and _SHA64.fullmatch(value) is None:
        _fail(field + " must be 64 lowercase hex")
    return value


def _int(value, field, maximum=None):
    if type(value) is not int:
        _fail(field + " must be an integer")
    if value < 0:
        _fail(field + " must be nonnegative")
    if maximum is not None and value > maximum:
        _fail(field + " exceeds " + str(maximum))
    return value


def _flag(value, field, allowed):
    if type(value) is not str or value not in allowed:
        _fail(field + " must be one of " + ", ".join(allowed))
    return value


def validate_selection(work_ref):
    """Validate the canonical colon citation ``WS:<KEY>`` (upper kebab, 2..64)."""
    _text(work_ref, "selection.work_ref", max_len=3 + 64)
    if not work_ref.startswith("WS:"):
        _fail("selection.work_ref must be the colon citation WS:<KEY>")
    key = work_ref[3:]
    if _WORK_REF.fullmatch("WS-" + key) is None or not 2 <= len(key) <= 64:
        _fail("selection.work_ref must be WS: plus an upper-kebab key of 2..64 chars")
    return work_ref


def _source_ref(value, field, prefix):
    _text(value, field, max_len=len(prefix) + 64)
    if not value.startswith(prefix) or _SHA64.fullmatch(value[len(prefix):]) is None:
        _fail(field + " must be " + prefix + "<64 lowercase hex>")
    return value


def _utc_stamp(value, field):
    if value is None:
        return None
    _text(value, field, max_len=64)
    if _STAMP.fullmatch(value) is None or not value.endswith("Z"):
        _fail(field + " must be an actual UTC ISO-8601 Git clock ending in Z")
    return value


def _optional_text(value, field, max_len):
    if value is None:
        return None
    return _text(value, field, max_len=max_len)


def _optional_sha(value, field):
    if value is None:
        return None
    return _sha(value, field, 64)


def _source_object(value, field):
    """The immutable source identity shared by the source and memory DTOs."""
    _keys(value, ("commit", "committed_at", "content_sha256", "path", "repository", "revision"), field)
    if value["repository"] != REPOSITORY:
        _fail(field + ".repository must be " + REPOSITORY)
    _sha(value["commit"], field + ".commit", 40)
    _sha(value["revision"], field + ".revision", 40)
    _sha(value["content_sha256"], field + ".content_sha256", 64)
    _text(value["path"], field + ".path", max_len=MAX_PATH)
    _utc_stamp(value["committed_at"], field + ".committed_at")
    return value


def _actor_ref(value, field):
    _text(value, field, max_len=256)
    if re.fullmatch(r"workspace:[0-9a-f]{64}", value) is None:
        _fail(field + " must identify the canonical Workspace principal scope")
    return value


def _file_origin(value, field):
    _keys(value, ("actor_ref", "kind", "request_sha256"), field)
    _flag(value["kind"], field + ".kind", ORIGIN_KINDS)
    if value["kind"] == "PRINCIPAL_UPLOAD":
        _actor_ref(value["actor_ref"], field + ".actor_ref")
        _sha(value["request_sha256"], field + ".request_sha256", 64)
    elif value["actor_ref"] is not None or value["request_sha256"] is not None:
        _fail(field + " declared artifact has no inferred actor")
    return value


def _preference_origin(value, field):
    _keys(value, ("actor_ref", "kind", "source_ref", "source_revision"), field)
    _flag(value["kind"], field + ".kind", PREFERENCE_ORIGIN_KINDS)
    _actor_ref(value["actor_ref"], field + ".actor_ref")
    if value["kind"] == "USER_EDIT":
        if value["source_ref"] is not None or value["source_revision"] is not None:
            _fail(field + ".source_ref/.source_revision must be null for USER_EDIT")
    else:
        ref = value["source_ref"]
        if (
            type(ref) is not str
            or not ref.startswith(SESSION_REPLY_PREFIX)
            or _SHA64.fullmatch(ref[len(SESSION_REPLY_PREFIX):]) is None
        ):
            _fail(field + ".source_ref must be " + SESSION_REPLY_PREFIX + "<64 hex> for CONVERSATION")
        if type(value["source_revision"]) is not str or _SHA64.fullmatch(value["source_revision"]) is None:
            _fail(field + ".source_revision must be 64 lowercase hex for CONVERSATION")
    return value


def _preference_last_edit(value, field):
    _keys(value, ("actor_ref", "request_sha256"), field)
    _actor_ref(value["actor_ref"], field + ".actor_ref")
    _sha(value["request_sha256"], field + ".request_sha256", 64)
    return value


def _preference_value(value, field):
    _text(value, field, max_len=MAX_MEMORY_VALUE)
    if value.strip() == "":
        _fail(field + " must be a nonblank literal")
    return value


def validate_preference_payload(value):
    """Validate the canonical ``agentos.project_preference.v1`` record payload.

    Shape only: workstream association and decision anchoring are checked by
    the capture module against the actual Git record, not here.
    """
    check = _copy(value)
    _keys(check, ("kind", "last_edit", "origin", "schema", "value", "work_ref"), "project_preference")
    if check["schema"] != PREFERENCE_PAYLOAD_SCHEMA:
        _fail("project_preference.schema must be " + PREFERENCE_PAYLOAD_SCHEMA)
    validate_selection(check["work_ref"])
    _flag(check["kind"], "project_preference.kind", ("COMMUNICATION",))
    _preference_value(check["value"], "project_preference.value")
    _preference_origin(check["origin"], "project_preference.origin")
    _preference_last_edit(check["last_edit"], "project_preference.last_edit")
    return check


def _file_row(value, field):
    _keys(
        value,
        (
            "content_sha256",
            "display_name",
            "media_type",
            "origin",
            "path",
            "repository",
            "revision",
            "source_ref",
            "state",
            "viewer_relation",
        ),
        field,
    )
    _source_ref(value["source_ref"], field + ".source_ref", "project-file.v1.")
    state = _flag(value["state"], field + ".state", FILE_STATES)
    if value["viewer_relation"] != VIEWER_RELATION:
        _fail(field + ".viewer_relation must be " + VIEWER_RELATION)
    repository = value["repository"]
    path = value["path"]
    if repository is None:
        if path is not None:
            _fail(field + ".path must be null when repository is null")
    else:
        _flag(repository, field + ".repository", REPOSITORY_KEYS)
        _text(path, field + ".path", max_len=MAX_PATH)
    _text(value["display_name"], field + ".display_name", max_len=MAX_DISPLAY_NAME)
    media = value["media_type"]
    if media is not None:
        _flag(media, field + ".media_type", MEDIA_TYPES)
    _optional_sha(value["content_sha256"], field + ".content_sha256")
    if state == "READABLE":
        if repository != "macro" or path is None or media is None:
            _fail(field + " must be fully identified when READABLE")
        if value["revision"] is None:
            _fail(field + ".revision is required when READABLE")
    elif value["revision"] is not None and path is None:
        _fail(field + ".revision requires an identified path")
    _file_origin(value["origin"], field + ".origin")
    if value["origin"]["kind"] == "PRINCIPAL_UPLOAD" and value["origin"]["actor_ref"] is None:
        _fail(field + ".origin.actor_ref is required for PRINCIPAL_UPLOAD")
    return value


def _record_row(value, field):
    _keys(value, ("authored_at", "committed_at", "kind", "path", "revision", "source_ref", "title"), field)
    _source_ref(value["source_ref"], field + ".source_ref", "project-record.v1.")
    _flag(value["kind"], field + ".kind", RECORD_KINDS)
    _text(value["path"], field + ".path", max_len=MAX_PATH)
    _sha(value["revision"], field + ".revision", 40)
    _text(value["title"], field + ".title", max_len=MAX_TITLE)
    authored = value["authored_at"]
    if authored is not None:
        _text(authored, field + ".authored_at", max_len=10)
        if _DATE.fullmatch(authored) is None:
            _fail(field + ".authored_at must be YYYY-MM-DD")
    _utc_stamp(value["committed_at"], field + ".committed_at")
    return value


def _file_coverage(value, field):
    _keys(value, ("declared", "listed", "omitted", "state"), field)
    _flag(value["state"], field + ".state", FILE_COVERAGE_STATES)
    _int(value["declared"], field + ".declared")
    _int(value["listed"], field + ".listed")
    _int(value["omitted"], field + ".omitted")
    if value["state"] == "COMPLETE" and value["omitted"] != 0:
        _fail(field + ".state COMPLETE requires zero omitted")
    if value["declared"] < value["listed"]:
        _fail(field + ".declared must cover every listed row")
    return value


def _record_coverage(value, field):
    _keys(value, ("invalid", "matched", "omitted", "scanned", "state"), field)
    _flag(value["state"], field + ".state", RECORD_COVERAGE_STATES)
    _int(value["scanned"], field + ".scanned", MAX_SCANNED_RECORDS)
    _int(value["matched"], field + ".matched", MAX_MATCHED_RECORDS)
    _int(value["omitted"], field + ".omitted")
    _int(value["invalid"], field + ".invalid")
    # Honest bounded-sample accounting: the scan window covers every matched
    # row, and nothing matched can be reported as scanned-away.  Scanned,
    # matched, omitted and invalid deliberately need not sum to scanned
    # because valid candidates of other projects are neither matched, omitted
    # nor invalid.
    if value["scanned"] < value["matched"]:
        _fail(field + ".scanned must cover every matched row")
    if value["invalid"] > value["scanned"]:
        _fail(field + ".invalid cannot exceed the scanned window")
    return value


def _catalogue_memory(value, field):
    _keys(value, ("revision", "source_ref", "state"), field)
    state = _flag(value["state"], field + ".state", MEMORY_STATES)
    if state == "AVAILABLE":
        if value["source_ref"] is None or value["revision"] is None:
            _fail(field + " must carry source_ref and revision when AVAILABLE")
    elif value["source_ref"] is not None or value["revision"] is not None:
        _fail(field + " must be null unless AVAILABLE")
    if value["source_ref"] is not None:
        _source_ref(value["source_ref"], field + ".source_ref", "project-record.v1.")
    if value["revision"] is not None:
        _sha(value["revision"], field + ".revision", 40)
    return value


def _catalogue_project(value, field):
    _keys(value, ("coverage", "files", "memory", "records", "title"), field)
    _text(value["title"], field + ".title", max_len=MAX_TITLE)
    if type(value["files"]) is not list:
        _fail(field + ".files must be a list")
    for index, row in enumerate(value["files"]):
        _file_row(row, field + ".files[%d]" % index)
    if len(value["files"]) > MAX_FILE_METADATA:
        _fail(field + ".files exceeds the metadata bound")
    if type(value["records"]) is not list:
        _fail(field + ".records must be a list")
    for index, row in enumerate(value["records"]):
        _record_row(row, field + ".records[%d]" % index)
    if len(value["records"]) > MAX_MATCHED_RECORDS:
        _fail(field + ".records exceeds the matched bound")
    _catalogue_memory(value["memory"], field + ".memory")
    _keys(value["coverage"], ("files", "records"), field + ".coverage")
    _file_coverage(value["coverage"]["files"], field + ".coverage.files")
    _record_coverage(value["coverage"]["records"], field + ".coverage.records")
    if value["coverage"]["files"]["listed"] != len(value["files"]):
        _fail(field + ".coverage.files.listed must equal len(files)")
    if value["coverage"]["records"]["matched"] != len(value["records"]):
        _fail(field + ".coverage.records.matched must equal len(records)")
    if value["coverage"]["records"]["omitted"] < (
        value["coverage"]["records"]["matched"] - len(value["records"])
    ):
        _fail(field + ".coverage.records.omitted must cover matched rows not returned")
    return value


def _reason_codes(value, field, *, nonempty):
    if type(value) is not list:
        _fail(field + " must be a list")
    for index, reason in enumerate(value):
        _flag(reason, field + "[%d]" % index, REASON_CODES)
    if len(set(value)) != len(value):
        _fail(field + " must not repeat a reason code")
    if nonempty and not value:
        _fail(field + " must name at least one closed reason")
    if not nonempty and value:
        _fail(field + " must be empty on success")
    return value


def _read_context_keys(value, keys, field):
    _keys(value, tuple(keys) + tuple(k for k in ("code_context", "data_observation") if k in value), field)


def _read_context(value):
    if "data_observation" in value and "code_context" not in value:
        _fail("data_observation requires independently issued code_context")
    context = value.get("code_context")
    if "code_context" in value:
        _keys(context, ("schema", "work_ref", "executable_macro_commit", "reader_source_commit"), "code_context")
        if context["schema"] != "mastermind.project_knowledge_code_context.v1" or context["work_ref"] != value["selection"]["work_ref"]:
            _fail("code_context selection/schema mismatch")
        _sha(context["executable_macro_commit"], "code_context.executable_macro_commit", 40)
        _sha(context["reader_source_commit"], "code_context.reader_source_commit", 40)
    if "data_observation" in value:
        from common.canonical_project_data_observation_contract import validate
        try:
            observation = validate(value["data_observation"])
        except (ValueError, TypeError, OverflowError):
            _fail("data_observation invalid")
        if observation["executable_macro_commit"] != context["executable_macro_commit"]:
            _fail("data_observation executable CODE mismatch")
        if value["source"] is not None and observation["canonical_data_commit"] != value["source"]["commit"]:
            _fail("data_observation canonical DATA mismatch")
        operation = observation["source_operation"]
        if operation is not None and operation["selection"]["work_ref"] != value["selection"]["work_ref"]:
            _fail("data_observation project mismatch")
        continuity = observation.get("data_continuity")
        if continuity is not None and continuity["work_ref"] != value["selection"]["work_ref"]:
            _fail("data_continuity project mismatch")
        value["data_observation"] = observation
    elif context is not None and value["source"] is not None and value["source"]["commit"] != context["executable_macro_commit"]:
        _fail("legacy source must match CODE when no DATA observation exists")
    return value


def validate_catalogue(value):
    """Validate ``mastermind.workspace_project_knowledge.v1``; returns a copy."""
    check = _copy(value)
    _read_context_keys(check, ("availability", "project", "reason_codes", "schema", "selection", "source"), "catalogue")
    if check["schema"] != CATALOGUE_SCHEMA:
        _fail("catalogue.schema must be " + CATALOGUE_SCHEMA)
    _keys(check["selection"], ("work_ref",), "catalogue.selection")
    validate_selection(check["selection"]["work_ref"])
    availability = _flag(check["availability"], "catalogue.availability", AVAILABILITY)
    _reason_codes(check["reason_codes"], "catalogue.reason_codes", nonempty=availability == "UNAVAILABLE")
    if check["source"] is not None:
        _keys(check["source"], ("commit", "repository", "workstream_sha256"), "catalogue.source")
        if check["source"]["repository"] != REPOSITORY:
            _fail("catalogue.source.repository must be " + REPOSITORY)
        _sha(check["source"]["commit"], "catalogue.source.commit", 40)
        _sha(check["source"]["workstream_sha256"], "catalogue.source.workstream_sha256", 64)
    if check["project"] is not None:
        _catalogue_project(check["project"], "catalogue.project")
    if availability == "UNAVAILABLE":
        if check["source"] is not None or check["project"] is not None:
            _fail("catalogue must keep source and project null when UNAVAILABLE")
    elif check["source"] is None or check["project"] is None:
        _fail("catalogue must carry source and project when AVAILABLE")
    return _read_context(check)


def validate_source(value):
    """Validate ``mastermind.workspace_project_source.v1``; returns a copy."""
    check = _copy(value)
    _read_context_keys(check, ("availability", "document", "reason_codes", "schema", "selection", "source"), "source")
    if check["schema"] != SOURCE_SCHEMA:
        _fail("source.schema must be " + SOURCE_SCHEMA)
    _keys(check["selection"], ("source_ref", "work_ref"), "source.selection")
    validate_selection(check["selection"]["work_ref"])
    _text(check["selection"]["source_ref"], "source.selection.source_ref", max_len=82)
    if not any(
        check["selection"]["source_ref"].startswith(prefix)
        and _SHA64.fullmatch(check["selection"]["source_ref"][len(prefix):]) is not None
        for prefix in SOURCE_REF_PREFIXES
    ):
        _fail("source.selection.source_ref must be project-file.v1. or project-record.v1. + 64 hex")
    availability = _flag(check["availability"], "source.availability", AVAILABILITY)
    _reason_codes(check["reason_codes"], "source.reason_codes", nonempty=availability == "UNAVAILABLE")
    if check["source"] is not None:
        _source_object(check["source"], "source.source")
    if check["document"] is not None:
        _keys(check["document"], ("content_sha256", "content_utf8", "media_type", "title"), "source.document")
        _text(check["document"]["title"], "source.document.title", max_len=MAX_TITLE)
        _flag(check["document"]["media_type"], "source.document.media_type", MEDIA_TYPES)
        _text(check["document"]["content_utf8"], "source.document.content_utf8", max_len=MAX_SOURCE_BODY)
        digest = hashlib.sha256(check["document"]["content_utf8"].encode("utf-8")).hexdigest()
        if check["document"]["content_sha256"] != digest:
            _fail("source.document.content_sha256 must hash the exact content_utf8 body")
    if availability == "UNAVAILABLE":
        if check["source"] is not None or check["document"] is not None:
            _fail("source must keep source and document null when UNAVAILABLE")
    else:
        if check["source"] is None or check["document"] is None:
            _fail("source must carry source and document when AVAILABLE")
        if check["source"]["content_sha256"] != check["document"]["content_sha256"]:
            _fail("source.source.content_sha256 must equal source.document.content_sha256")
    return _read_context(check)


def _memory_block(value, field):
    _keys(value, ("last_edit", "origin", "value"), field)
    _preference_value(value["value"], field + ".value")
    _preference_origin(value["origin"], field + ".origin")
    _preference_last_edit(value["last_edit"], field + ".last_edit")
    return value


def validate_memory(value):
    """Validate ``mastermind.workspace_project_preference.v1``; returns a copy."""
    check = _copy(value)
    _read_context_keys(check, ("availability", "memory", "reason_codes", "schema", "selection", "source"), "memory")
    if check["schema"] != PREFERENCE_SCHEMA:
        _fail("memory.schema must be " + PREFERENCE_SCHEMA)
    _keys(check["selection"], ("work_ref",), "memory.selection")
    validate_selection(check["selection"]["work_ref"])
    availability = _flag(check["availability"], "memory.availability", MEMORY_AVAILABILITY)
    _reason_codes(
        check["reason_codes"], "memory.reason_codes", nonempty=availability == "UNAVAILABLE"
    )
    if check["source"] is not None:
        _source_object(check["source"], "memory.source")
    if check["memory"] is not None:
        _memory_block(check["memory"], "memory.memory")
    if availability == "UNAVAILABLE":
        if check["source"] is not None or check["memory"] is not None:
            _fail("memory must keep source and memory null when UNAVAILABLE")
    elif availability == "EMPTY":
        if check["source"] is not None or check["memory"] is not None or check["reason_codes"]:
            _fail("memory must be empty with no reasons when EMPTY")
    else:
        if check["source"] is None or check["memory"] is None:
            _fail("memory must carry source and memory when AVAILABLE")
    return _read_context(check)


def unavailable_catalogue(work_ref, *reason_codes):
    """Safe catalogue builder: every private payload stays null."""
    return validate_catalogue(
        {
            "schema": CATALOGUE_SCHEMA,
            "selection": {"work_ref": work_ref},
            "availability": "UNAVAILABLE",
            "reason_codes": list(reason_codes),
            "source": None,
            "project": None,
        }
    )


def unavailable_source(work_ref, source_ref, *reason_codes):
    """Safe source builder: no document body, no source identity."""
    return validate_source(
        {
            "schema": SOURCE_SCHEMA,
            "selection": {"work_ref": work_ref, "source_ref": source_ref},
            "availability": "UNAVAILABLE",
            "reason_codes": list(reason_codes),
            "source": None,
            "document": None,
        }
    )


def unavailable_memory(work_ref, *reason_codes):
    """Safe preference builder: value, origin and source stay null."""
    return validate_memory(
        {
            "schema": PREFERENCE_SCHEMA,
            "selection": {"work_ref": work_ref},
            "availability": "UNAVAILABLE",
            "reason_codes": list(reason_codes),
            "source": None,
            "memory": None,
        }
    )


def empty_memory(work_ref):
    """Safe builder for an honestly empty preference (no invented value)."""
    return validate_memory(
        {
            "schema": PREFERENCE_SCHEMA,
            "selection": {"work_ref": work_ref},
            "availability": "EMPTY",
            "reason_codes": [],
            "source": None,
            "memory": None,
        }
    )
