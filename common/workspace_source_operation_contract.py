"""Closed-value source-operation STATUS contract (pure validation).

Validates Mastermind workspace source-operation lookup requests, ADOPT_PLAN
advance requests and status bodies against an exact closed shape, and builds
the null-evidence unavailable status body.  Stdlib only, no I/O, no clock,
no Runtime/SQL/store or worker/controller access, no auth issuance and no
publication: every function either returns a freshly allocated detached
value built from exact builtin ``dict``/``list``/``str``/``int``/``None``
types, or raises ``ValueError`` with the single constant code
``invalid_source_operation``.  Input values are never echoed and never
mutated; no attribute access, method dispatch or type coercion is ever
performed on caller-supplied data beyond exact-type inspection, so custom
mapping/sequence/string subclasses, duck-typed containers and data
properties are rejected without being invoked.

This module is not an owner receipt producer and grants nothing: a returned
body never authorizes a write and no digest is treated as proof of
authenticity.  Original IDs are validated against the strict per-action
grammar; they are never minted here.
"""

import json
import re

__all__ = [
    "validate_status",
    "validate_lookup",
    "validate_advance",
    "unavailable",
]

_INVALID = "invalid_source_operation"

_STATUS_SCHEMA = "mastermind.workspace_source_operation_status.v1"
_LOOKUP_SCHEMA = "mastermind.workspace_source_operation_lookup.v1"
_ADVANCE_SCHEMA = "mastermind.workspace_source_operation_advance.v1"

_REPOSITORY = "macro"
_PR_URL_PREFIX = "https://github.com/mastermindx-market-intelligence/macro/pull/"

_MAX_STATUS_BYTES = 32768  # canonical JSON bytes plus one trailing LF
_MAX_SAFEINT = 9007199254740991  # 2**53 - 1
_MAX_SOURCES = 3
_MAX_PATH_BYTES = 512  # UTF-8 bytes
_MAX_BRANCH_CHARS = 200  # ASCII chars
_MIN_WORK_REF_KEY = 2
_MAX_WORK_REF_KEY = 64

_ADOPT_ACTION = "ADOPT_PLAN"

_REQUEST_PREFIXES = {
    "publish_project_proposal": "mmos-project-create-",
    "publish_project_plan_proposal": "mmos-project-plan-proposal-",
    "ADOPT_PLAN": "mmos-project-adopt-",
    "ACCEPT_DIRECTION": "mmos-direction-accept-",
    "add_project_file": "mmos-project-file-add-",
    "set_project_communication_preference": "mmos-project-preference-set-",
    "correct_project_discovery": "mmos-project-discovery-correct-",
}

_PHASE_PUBLICATION = "PUBLICATION"
_PHASE_CANDIDATE = "CANDIDATE"
_PHASE_ADOPTION = "ADOPTION"
_ALL_PHASES = (_PHASE_PUBLICATION, _PHASE_CANDIDATE, _PHASE_ADOPTION)

_ADOPT_PHASES = (_PHASE_CANDIDATE, _PHASE_ADOPTION)
_PLAIN_PHASES = (_PHASE_PUBLICATION,)

_DISPOSITIONS = ("accepted", "refused", "unknown")

_REASON_ORIGINAL_NOT_OBSERVED = "ORIGINAL_OPERATION_NOT_OBSERVED"
_REASON_READY_FOR_ADVANCE = "READY_FOR_ADVANCE"

_REASON_SET = frozenset((
    "ORIGINAL_OPERATION_NOT_OBSERVED",
    "IN_PROGRESS",
    "PHASE_ATTEMPT_UNRESOLVED",
    "READY_FOR_ADVANCE",
    "PRECONDITION_UNAVAILABLE",
    "PRIVATE_INPUT_UNAVAILABLE",
    "SOURCE_UNAVAILABLE",
    "CONFLICT",
    "NOT_DISPATCHED",
    "REFUSED",
))
_REFUSED_REASONS = frozenset(("NOT_DISPATCHED", "REFUSED", "CONFLICT"))
_UNKNOWN_REASONS = _REASON_SET - frozenset(("REFUSED",))

_KIND_INTENT = "INTENT"
_KIND_PHASE_ATTEMPTED = "PHASE_ATTEMPTED"
_KIND_PROPOSAL_OBSERVED = "PROPOSAL_OBSERVED"
_KIND_SOURCE_OBSERVED = "SOURCE_OBSERVED"
_RECEIPT_KINDS = (
    _KIND_INTENT,
    _KIND_PHASE_ATTEMPTED,
    _KIND_PROPOSAL_OBSERVED,
    _KIND_SOURCE_OBSERVED,
)

_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_HEX40_RE = re.compile(r"[0-9a-f]{40}")
_WORK_REF_RE = re.compile(r"WS:([A-Z0-9]+(?:-[A-Z0-9]+)*)")
_REQUEST_ID_RES = {
    action: re.compile(re.escape(prefix) + r"[0-9a-f]{40}")
    for action, prefix in _REQUEST_PREFIXES.items()
}

_SELECTION_KEYS = frozenset(("action", "request_id", "work_ref"))
_LOOKUP_KEYS = frozenset(("schema", "action", "request_id", "work_ref"))
_ADVANCE_KEYS = frozenset(
    ("schema", "action", "request_id", "work_ref", "phase_receipt_digest")
)
_OWNER_CONTEXT_KEYS = frozenset(("principal_scope",))
_ADVANCE_WITNESS_KEYS = frozenset(("phase_receipt_digest",))
_RECEIPT_KEYS = frozenset((
    "kind", "event_id", "recorded_at_ms", "receipt_sha256", "sources", "proposal",
))
_SOURCE_KEYS = frozenset(("repository", "commit", "path", "content_sha256"))
_PROPOSAL_KEYS = frozenset(("number", "url", "head_commit", "head_branch"))
_STATUS_KEYS = frozenset((
    "schema", "selection", "owner_context", "disposition", "reason",
    "request_sha256", "recipe_fingerprint_sha256", "phase", "receipt", "advance",
))

_BRANCH_FORBIDDEN_CHARS = " ~^:?*["


def _fail():
    raise ValueError(_INVALID)


def _require_exact_dict(value, keys):
    if type(value) is not dict:
        _fail()
    if len(value) != len(keys):
        _fail()
    for key in value.keys():
        if type(key) is not str:
            _fail()
    if set(value.keys()) != keys:
        _fail()


def _require_str(value):
    if type(value) is not str:
        _fail()
    return value


def _require_hex(value, pattern):
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail()
    return value


def _require_optional_hex(value, pattern):
    if value is None:
        return None
    return _require_hex(value, pattern)


def _require_safe_int(value, minimum):
    if type(value) is not int:  # exact int: bool and float never pass
        _fail()
    if value < minimum or value > _MAX_SAFEINT:
        _fail()
    return value


def _validate_action(value):
    _require_str(value)
    if value not in _REQUEST_PREFIXES:
        _fail()
    return value


def _validate_request_id(action, value):
    _require_str(value)
    if _REQUEST_ID_RES[action].fullmatch(value) is None:
        _fail()
    return value


def _validate_work_ref(value):
    _require_str(value)
    match = _WORK_REF_RE.fullmatch(value)
    if match is None:
        _fail()
    key = match.group(1)
    if len(key) < _MIN_WORK_REF_KEY or len(key) > _MAX_WORK_REF_KEY:
        _fail()
    return value


def _validate_selection(value):
    _require_exact_dict(value, _SELECTION_KEYS)
    action = _validate_action(value["action"])
    request_id = _validate_request_id(action, value["request_id"])
    work_ref = _validate_work_ref(value["work_ref"])
    return {"action": action, "request_id": request_id, "work_ref": work_ref}


def _validate_path(value):
    _require_str(value)
    if not value:
        _fail()
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:  # lone surrogates can never round-trip JSON
        _fail()
    if len(encoded) > _MAX_PATH_BYTES:
        _fail()
    if "\\" in value:
        _fail()
    for char in value:
        code = ord(char)
        if code < 0x20 or 0x7F <= code <= 0x9F:
            _fail()
    for segment in value.split("/"):
        if segment == "" or segment == "." or segment == "..":
            _fail()
    return value


def _validate_branch(value):
    _require_str(value)
    if not value:
        _fail()
    if len(value) > _MAX_BRANCH_CHARS or not value.isascii():
        _fail()
    for char in value:
        code = ord(char)
        if (
            code < 0x20
            or 0x7F <= code <= 0x9F
            or char.isspace()
            or char in _BRANCH_FORBIDDEN_CHARS
        ):
            _fail()
    if value.startswith(("-", "/", ".")):
        _fail()
    if value.endswith(("/", ".")) or value.endswith(".lock"):
        _fail()
    if ".." in value or "@{" in value or "\\" in value or "//" in value:
        _fail()
    return value


def _validate_source(value):
    _require_exact_dict(value, _SOURCE_KEYS)
    repository = _require_str(value["repository"])
    if repository != _REPOSITORY:
        _fail()
    commit = _require_hex(value["commit"], _HEX40_RE)
    path = _validate_path(value["path"])
    content_sha256 = _require_hex(value["content_sha256"], _HEX64_RE)
    return {
        "repository": repository,
        "commit": commit,
        "path": path,
        "content_sha256": content_sha256,
    }


def _validate_proposal(value):
    if value is None:
        return None
    _require_exact_dict(value, _PROPOSAL_KEYS)
    number = _require_safe_int(value["number"], 1)
    url = _require_str(value["url"])
    if url != _PR_URL_PREFIX + str(number):
        _fail()
    head_commit = _require_hex(value["head_commit"], _HEX40_RE)
    head_branch = _validate_branch(value["head_branch"])
    return {
        "number": number,
        "url": url,
        "head_commit": head_commit,
        "head_branch": head_branch,
    }


def _validate_receipt(value):
    _require_exact_dict(value, _RECEIPT_KEYS)
    kind = _require_str(value["kind"])
    if kind not in _RECEIPT_KINDS:
        _fail()
    event_id = _require_safe_int(value["event_id"], 1)
    recorded_at_ms = _require_safe_int(value["recorded_at_ms"], 0)
    receipt_sha256 = _require_hex(value["receipt_sha256"], _HEX64_RE)
    raw_sources = value["sources"]
    if type(raw_sources) is not list:
        _fail()
    if len(raw_sources) > _MAX_SOURCES:
        _fail()
    sources = [_validate_source(entry) for entry in raw_sources]
    proposal = _validate_proposal(value["proposal"])
    return {
        "kind": kind,
        "event_id": event_id,
        "recorded_at_ms": recorded_at_ms,
        "receipt_sha256": receipt_sha256,
        "sources": sources,
        "proposal": proposal,
    }


def _validate_advance_witness(value):
    if value is None:
        return None
    _require_exact_dict(value, _ADVANCE_WITNESS_KEYS)
    digest = _require_hex(value["phase_receipt_digest"], _HEX64_RE)
    return {"phase_receipt_digest": digest}


def _check_semantics(
    selection,
    disposition,
    reason,
    request_sha256,
    recipe_fingerprint_sha256,
    phase,
    receipt,
    advance,
):
    action = selection["action"]
    adopt = action == _ADOPT_ACTION
    allowed_phases = _ADOPT_PHASES if adopt else _PLAIN_PHASES
    if phase is not None and phase not in allowed_phases:
        _fail()

    if reason is None:
        if disposition != "accepted":
            _fail()
    else:
        if disposition == "accepted":
            _fail()
        if disposition == "refused":
            if reason not in _REFUSED_REASONS:
                _fail()
            if receipt is not None or advance is not None:
                _fail()  # partial publication is never refused
        else:
            if reason not in _UNKNOWN_REASONS:
                _fail()

    if (
        request_sha256 is not None
        and recipe_fingerprint_sha256 is not None
        and request_sha256 == recipe_fingerprint_sha256
    ):
        _fail()  # the public request SHA is never substituted for the fingerprint

    if receipt is None:
        if phase is not None:
            _fail()
        if request_sha256 is not None or recipe_fingerprint_sha256 is not None:
            _fail()
        if advance is not None:
            _fail()
    else:
        if phase is None or request_sha256 is None or recipe_fingerprint_sha256 is None:
            _fail()

    if reason == _REASON_ORIGINAL_NOT_OBSERVED:
        if receipt is not None or advance is not None:
            _fail()

    if receipt is not None:
        kind = receipt["kind"]
        sources = receipt["sources"]
        proposal = receipt["proposal"]
        if kind in (_KIND_INTENT, _KIND_PHASE_ATTEMPTED):
            if sources or proposal is not None:
                _fail()
            if disposition != "unknown":
                _fail()
        elif kind == _KIND_PROPOSAL_OBSERVED:
            if proposal is None or sources:
                _fail()
            if disposition != "unknown":
                _fail()
        else:
            if not sources or proposal is not None:
                _fail()
            if phase == _PHASE_CANDIDATE and disposition != "unknown":
                _fail()

    if disposition == "accepted":
        if receipt is None or receipt["kind"] != _KIND_SOURCE_OBSERVED:
            _fail()
        if phase != (_PHASE_ADOPTION if adopt else _PHASE_PUBLICATION):
            _fail()
        if advance is not None:
            _fail()

    if reason == _REASON_READY_FOR_ADVANCE:
        if disposition != "unknown" or not adopt:
            _fail()
        if receipt is None or receipt["kind"] != _KIND_SOURCE_OBSERVED:
            _fail()
        if phase != _PHASE_CANDIDATE:
            _fail()
        if advance is None or advance["phase_receipt_digest"] != receipt["receipt_sha256"]:
            _fail()
    elif advance is not None:
        _fail()


def _check_serialized_budget(value):
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    if len(payload.encode("utf-8")) + 1 > _MAX_STATUS_BYTES:
        _fail()


def validate_status(value):
    """Validate a workspace source-operation status body.

    Returns a detached body rebuilt from exact builtin types; the canonical
    JSON encoding (``sort_keys=True``, ``separators=(',', ':')``,
    ``ensure_ascii=False``, ``allow_nan=False``) of the body plus one
    trailing LF must stay within 32768 UTF-8 bytes.  Absence of a receipt is
    never read as proof that no effect happened.  Raises
    ``ValueError("invalid_source_operation")`` on any violation; input is
    never mutated or echoed.
    """
    _require_exact_dict(value, _STATUS_KEYS)
    schema = _require_str(value["schema"])
    if schema != _STATUS_SCHEMA:
        _fail()
    selection = _validate_selection(value["selection"])

    raw_owner_context = value["owner_context"]
    _require_exact_dict(raw_owner_context, _OWNER_CONTEXT_KEYS)
    owner_context = {
        "principal_scope": _require_hex(raw_owner_context["principal_scope"], _HEX64_RE),
    }

    disposition = _require_str(value["disposition"])
    if disposition not in _DISPOSITIONS:
        _fail()

    raw_reason = value["reason"]
    reason = None if raw_reason is None else _require_str(raw_reason)
    if reason is not None and reason not in _REASON_SET:
        _fail()

    request_sha256 = _require_optional_hex(value["request_sha256"], _HEX64_RE)
    recipe_fingerprint_sha256 = _require_optional_hex(
        value["recipe_fingerprint_sha256"], _HEX64_RE
    )

    raw_phase = value["phase"]
    phase = None if raw_phase is None else _require_str(raw_phase)
    if phase is not None and phase not in _ALL_PHASES:
        _fail()

    raw_receipt = value["receipt"]
    receipt = None if raw_receipt is None else _validate_receipt(raw_receipt)
    advance = _validate_advance_witness(value["advance"])

    _check_semantics(
        selection,
        disposition,
        reason,
        request_sha256,
        recipe_fingerprint_sha256,
        phase,
        receipt,
        advance,
    )

    status = {
        "schema": _STATUS_SCHEMA,
        "selection": selection,
        "owner_context": owner_context,
        "disposition": disposition,
        "reason": reason,
        "request_sha256": request_sha256,
        "recipe_fingerprint_sha256": recipe_fingerprint_sha256,
        "phase": phase,
        "receipt": receipt,
        "advance": advance,
    }
    _check_serialized_budget(status)
    return status


def validate_lookup(value):
    """Validate an exact workspace source-operation lookup request body."""
    _require_exact_dict(value, _LOOKUP_KEYS)
    schema = _require_str(value["schema"])
    if schema != _LOOKUP_SCHEMA:
        _fail()
    action = _validate_action(value["action"])
    request_id = _validate_request_id(action, value["request_id"])
    work_ref = _validate_work_ref(value["work_ref"])
    return {
        "schema": _LOOKUP_SCHEMA,
        "action": action,
        "request_id": request_id,
        "work_ref": work_ref,
    }


def validate_advance(value):
    """Validate an exact ADOPT_PLAN phase-advance request body."""
    _require_exact_dict(value, _ADVANCE_KEYS)
    schema = _require_str(value["schema"])
    if schema != _ADVANCE_SCHEMA:
        _fail()
    action = _validate_action(value["action"])
    if action != _ADOPT_ACTION:
        _fail()
    request_id = _validate_request_id(action, value["request_id"])
    work_ref = _validate_work_ref(value["work_ref"])
    digest = _require_hex(value["phase_receipt_digest"], _HEX64_RE)
    return {
        "schema": _ADVANCE_SCHEMA,
        "action": action,
        "request_id": request_id,
        "work_ref": work_ref,
        "phase_receipt_digest": digest,
    }


def unavailable(action, request_id, work_ref, principal_scope):
    """Build the exact null-evidence unknown status body.

    Arguments are validated with the same closed grammars first; any
    violation raises the single constant error code.  The returned body is
    ``unknown``/``ORIGINAL_OPERATION_NOT_OBSERVED`` with no receipt, no
    advance and no digests: it never infers that no effect happened, never
    authorizes a write and never treats any digest as authenticity.
    """
    return validate_status({
        "schema": _STATUS_SCHEMA,
        "selection": {
            "action": action,
            "request_id": request_id,
            "work_ref": work_ref,
        },
        "owner_context": {"principal_scope": principal_scope},
        "disposition": "unknown",
        "reason": _REASON_ORIGINAL_NOT_OBSERVED,
        "request_sha256": None,
        "recipe_fingerprint_sha256": None,
        "phase": None,
        "receipt": None,
        "advance": None,
    })
