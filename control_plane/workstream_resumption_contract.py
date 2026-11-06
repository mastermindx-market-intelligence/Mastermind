"""Closed workstream admission resumption contract math.

Pure-stdlib, side-effect-free helpers for the resume half of the workstream
admission suspension/resumption protocol.  This leaf owns only the closed
request/payload/event/receipt math:

- ``make_resume_request`` builds the resume admission request from five
  already-canonical inputs.
- ``request_digest`` validates a request against the fixed request schema and
  hashes its canonical JSON form.
- ``pause_receipt_digest`` validates an actual PAUSED public suspension
  receipt and hashes its canonical JSON form.
- ``make_resume_payload`` derives the RESUMED workstream payload.
- ``parse_resumption_event`` validates a RESUMED workstream event against the
  actual pause receipt and returns the detached public resumption receipt.

Ownership boundaries honored by this module:

- Pure stdlib only.  No state, store, controller, provider, clock read,
  network, subprocess or other live effect is used or created.  Every return
  value is a detached new dict and inputs are never mutated.
- The parent Runtime owns the Runtime SQL chain, CAS and auth.  It must
  separately establish, under BEGIN, that the pause event referenced by a
  resume is the CURRENT immediately preceding workstream state.  This module
  recomputes the closed math only and never claims to have verified that SQL
  fact.
- Actor and command identifiers are carried verbatim as labels.  Nothing here
  treats an actor label, a pause grant, or a suspension receipt as a resume
  grant or as any other authority; format validation never mints permission.
- Ordering between the pause and the resumption is judged by event id
  monotonicity only.  Wall-clock ``committed_at_ms`` values are never
  compared to each other because the wall clock may move.

Every public function rejects bad input with the single fixed error
``ValueError('WORKSTREAM_RESUMPTION_INVALID')`` and never echoes any part of
the rejected input in the message.
"""

import hashlib
import json
import re

__all__ = [
    'AGGREGATE_TYPE_WORKSTREAM',
    'ERROR_MESSAGE',
    'PAUSED_STATE',
    'PAUSE_RECEIPT_SCHEMA',
    'PAYLOAD_JSON_MAX_BYTES',
    'PAYLOAD_SCHEMA',
    'REQUEST_SCHEMA',
    'RESUMED_EVENT_TYPE',
    'RESUMED_STATE',
    'RESUME_OPERATION',
    'RESUMPTION_RECEIPT_SCHEMA',
    'make_resume_payload',
    'make_resume_request',
    'parse_resumption_event',
    'pause_receipt_digest',
    'request_digest',
]

REQUEST_SCHEMA = 'mastermind.workstream_admission_resumption.request.v1'
PAYLOAD_SCHEMA = 'mastermind.workstream_admission_resumption.v1'
PAUSE_RECEIPT_SCHEMA = 'mastermind.workstream_admission_suspension_receipt.v1'
RESUMPTION_RECEIPT_SCHEMA = 'mastermind.workstream_admission_resumption_receipt.v1'
RESUME_OPERATION = 'resume'
PAUSED_STATE = 'PAUSED'
RESUMED_STATE = 'RESUMED'
RESUMED_EVENT_TYPE = 'WORKSTREAM_ADMISSION_RESUMED'
AGGREGATE_TYPE_WORKSTREAM = 'workstream'
PAYLOAD_JSON_MAX_BYTES = 4096
ERROR_MESSAGE = 'WORKSTREAM_RESUMPTION_INVALID'

_REQUEST_KEYS = frozenset((
    'schema',
    'operation',
    'work_ref',
    'command_id',
    'actor',
    'expected_pause_event_id',
    'expected_pause_receipt_digest',
))

_PAUSE_RECEIPT_KEYS = frozenset((
    'schema',
    'work_ref',
    'state',
    'event_id',
    'command_id',
    'request_digest',
    'committed_at_ms',
))

_PAYLOAD_KEYS = frozenset((
    'schema',
    'state',
    'work_ref',
    'request_digest',
    'pause_event_id',
    'pause_receipt_digest',
))

_EVENT_KEYS = frozenset((
    'event_id',
    'aggregate_type',
    'aggregate_id',
    'event_type',
    'command_id',
    'actor',
    'payload_json',
    'created_at_ms',
))

_WORK_REF_RE = re.compile(r'WS:[A-Z0-9][A-Za-z0-9._-]{1,63}')
_IDENTIFIER_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}')
_DIGEST_RE = re.compile(r'[0-9a-f]{64}')


def _invalid():
    return ValueError(ERROR_MESSAGE)


def _require_exact_keys(value, expected_keys):
    if not isinstance(value, dict) or set(value.keys()) != expected_keys:
        raise _invalid()


def _require_str_format(value, pattern):
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise _invalid()
    return value


def _require_positive_int(value):
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise _invalid()
    return value


def _require_non_negative_int(value):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _invalid()
    return value


def _canonical_json_text(value):
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise _invalid() from None


def _sha256_canonical(value):
    try:
        encoded = _canonical_json_text(value).encode('utf-8')
    except ValueError:
        raise _invalid() from None
    return hashlib.sha256(encoded).hexdigest()


def _reject_duplicate_pairs(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise _invalid()
        seen[key] = value
    return seen


def _reject_non_json_constant(name):
    raise _invalid()


def _parse_payload_object(payload_json):
    try:
        parsed = json.loads(
            payload_json,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_non_json_constant,
        )
    except ValueError:
        raise _invalid() from None
    _require_exact_keys(parsed, _PAYLOAD_KEYS)
    if parsed['schema'] != PAYLOAD_SCHEMA or parsed['state'] != RESUMED_STATE:
        raise _invalid()
    _require_str_format(parsed['work_ref'], _WORK_REF_RE)
    _require_str_format(parsed['request_digest'], _DIGEST_RE)
    _require_positive_int(parsed['pause_event_id'])
    _require_str_format(parsed['pause_receipt_digest'], _DIGEST_RE)
    if _canonical_json_text(parsed) != payload_json:
        raise _invalid()
    return parsed


def make_resume_request(work_ref, command_id, actor,
                        expected_pause_event_id, expected_pause_receipt_digest):
    """Build the resume admission request for one paused workstream.

    Every argument must already be in final canonical form: nothing is
    trimmed, coerced or defaulted here, and the actor label is carried
    verbatim as an identifier, never as a grant.
    """
    _require_str_format(work_ref, _WORK_REF_RE)
    _require_str_format(command_id, _IDENTIFIER_RE)
    _require_str_format(actor, _IDENTIFIER_RE)
    _require_positive_int(expected_pause_event_id)
    _require_str_format(expected_pause_receipt_digest, _DIGEST_RE)
    return {
        'schema': REQUEST_SCHEMA,
        'operation': RESUME_OPERATION,
        'work_ref': work_ref,
        'command_id': command_id,
        'actor': actor,
        'expected_pause_event_id': expected_pause_event_id,
        'expected_pause_receipt_digest': expected_pause_receipt_digest,
    }


def request_digest(request):
    """Validate ``request`` and return its canonical JSON sha256 hex digest."""
    _require_exact_keys(request, _REQUEST_KEYS)
    if request['schema'] != REQUEST_SCHEMA or request['operation'] != RESUME_OPERATION:
        raise _invalid()
    _require_str_format(request['work_ref'], _WORK_REF_RE)
    _require_str_format(request['command_id'], _IDENTIFIER_RE)
    _require_str_format(request['actor'], _IDENTIFIER_RE)
    _require_positive_int(request['expected_pause_event_id'])
    _require_str_format(request['expected_pause_receipt_digest'], _DIGEST_RE)
    return _sha256_canonical(request)


def pause_receipt_digest(receipt):
    """Validate an actual PAUSED public receipt and hash its canonical form.

    The receipt must be the actual public suspension receipt fetched and
    validated by the caller; hashing its canonical whole public form is all
    this function does and it grants no authority by itself.
    """
    _require_exact_keys(receipt, _PAUSE_RECEIPT_KEYS)
    if receipt['schema'] != PAUSE_RECEIPT_SCHEMA or receipt['state'] != PAUSED_STATE:
        raise _invalid()
    _require_str_format(receipt['work_ref'], _WORK_REF_RE)
    _require_positive_int(receipt['event_id'])
    _require_str_format(receipt['command_id'], _IDENTIFIER_RE)
    _require_str_format(receipt['request_digest'], _DIGEST_RE)
    _require_non_negative_int(receipt['committed_at_ms'])
    return _sha256_canonical(receipt)


def make_resume_payload(request):
    """Derive the RESUMED workstream payload from a validated request."""
    digest = request_digest(request)
    return {
        'schema': PAYLOAD_SCHEMA,
        'state': RESUMED_STATE,
        'work_ref': request['work_ref'],
        'request_digest': digest,
        'pause_event_id': request['expected_pause_event_id'],
        'pause_receipt_digest': request['expected_pause_receipt_digest'],
    }


def parse_resumption_event(event, pause_receipt):
    """Validate one RESUMED workstream event against its actual pause receipt.

    Returns the detached public resumption receipt.  The caller (parent
    Runtime) must separately establish, under BEGIN, that the pause event
    referenced here is the CURRENT immediately preceding workstream state;
    this helper recomputes only the closed request/payload/event math and
    does not pretend to have verified that SQL fact.  Ordering is judged by
    event id monotonicity only: ``committed_at_ms`` wall-clock values are
    never compared to each other.
    """
    _require_exact_keys(event, _EVENT_KEYS)
    pause_digest = pause_receipt_digest(pause_receipt)
    if event['aggregate_type'] != AGGREGATE_TYPE_WORKSTREAM:
        raise _invalid()
    if event['event_type'] != RESUMED_EVENT_TYPE:
        raise _invalid()
    work_ref = _require_str_format(event['aggregate_id'], _WORK_REF_RE)
    event_id = _require_positive_int(event['event_id'])
    command_id = _require_str_format(event['command_id'], _IDENTIFIER_RE)
    actor = _require_str_format(event['actor'], _IDENTIFIER_RE)
    committed_at_ms = _require_non_negative_int(event['created_at_ms'])
    payload_json = event['payload_json']
    if not isinstance(payload_json, str):
        raise _invalid()
    try:
        payload_bytes = payload_json.encode('utf-8')
    except UnicodeEncodeError:
        raise _invalid() from None
    if len(payload_bytes) > PAYLOAD_JSON_MAX_BYTES:
        raise _invalid()
    payload = _parse_payload_object(payload_json)

    if payload['work_ref'] != work_ref or pause_receipt['work_ref'] != work_ref:
        raise _invalid()
    if payload['pause_event_id'] != pause_receipt['event_id']:
        raise _invalid()
    if payload['pause_receipt_digest'] != pause_digest:
        raise _invalid()
    if event_id <= pause_receipt['event_id']:
        raise _invalid()

    rebuilt_request = make_resume_request(
        work_ref,
        command_id,
        actor,
        payload['pause_event_id'],
        payload['pause_receipt_digest'],
    )
    recomputed_digest = request_digest(rebuilt_request)
    if recomputed_digest != payload['request_digest']:
        raise _invalid()

    return {
        'schema': RESUMPTION_RECEIPT_SCHEMA,
        'work_ref': work_ref,
        'state': RESUMED_STATE,
        'event_id': event_id,
        'command_id': command_id,
        'request_digest': recomputed_digest,
        'committed_at_ms': committed_at_ms,
        'pause_event_id': pause_receipt['event_id'],
        'pause_receipt_digest': pause_digest,
    }
