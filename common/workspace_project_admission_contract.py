"""Workspace project admission pause-wire contract (pure shape validation).

Public wire shapes exchanged between the workspace project admission flow and
the authenticated Runtime adapter over HTTP.  This module validates shape
only.  It owns no transport, no credentials, no state, no store, no
dispatcher, no controller and no authority:

* A validated frame grants nothing.  The verified HTTP owner derives the
  principal and ``admission_expires_at`` itself; a Runtime actor is never
  taken from caller-provided frame data.  The embedded read principal proves
  identity only; the distinct sealed project-admission suspend grant and the
  exact selected workstream are required separately by the owner adapter and
  cannot be fabricated by this validator.
* ``request_digest`` on a receipt is format-checked only.  Only the owner
  recomputes the digest, with the actual server actor.
* ``COMMITTED`` means the Runtime owner returned the original committed
  receipt; it never means that running work was cancelled.  ``EFFECT_UNKNOWN``
  and ``NOT_OBSERVED`` are never collapsed into a no-effect conclusion, and
  an unobserved command never proves absence of effect nor permits a retry.
* No clock, currentness or grant is inferred from any accepted value.
  ``root_job_id`` travels on frames and result selections only; it is not
  part of the Runtime suspension receipt, because root authorization
  qualifies separately from this wire shape.

Errors are fixed sentinels that never echo input content:

``ValueError('invalid_input')``
    a JSON object whose shape violates this contract: an unknown field, a
    path/account/actor/action style variant, a bad pattern, a bad type, or a
    disposition/state pairing that does not match this contract.
``ValueError('source_unavailable')``
    a body that cannot be interpreted at all (not a JSON object), or an
    envelope that cannot be produced (not serializable, or over
    ``MAX_RESPONSE_BYTES``).  The input is never included in the message.
"""

from __future__ import annotations

import json
import re

from common import executive_workspace_contract as workspace

__all__ = [
    'MAX_REQUEST_BYTES',
    'MAX_RESPONSE_BYTES',
    'ACTION_FRAME_SCHEMA',
    'OPERATION',
    'STATUS_FRAME_SCHEMA',
    'STATUS_OPERATION',
    'ACTION_RESULT_SCHEMA',
    'STATUS_RESULT_SCHEMA',
    'ADMISSION_RECEIPT_SCHEMA',
    'READ_PRINCIPAL_RESOURCE',
    'READ_PRINCIPAL_SCOPES',
    'COMMITTED',
    'NOT_DISPATCHED',
    'EFFECT_UNKNOWN',
    'OBSERVED',
    'NOT_OBSERVED',
    'UNAVAILABLE',
    'RECEIPT_STATE_PAUSED',
    'NOT_DISPATCHED_REASON_CODES',
    'EFFECT_UNKNOWN_REASON_CODES',
    'UNAVAILABLE_REASON_CODES',
    'validate_frame',
    'selection',
    'validate_principal',
    'validate_receipt',
    'validate_action_result',
    'validate_status_result',
    'canonical_json_bytes',
    'canonical_request_bytes',
    'response_envelope_bytes',
]

MAX_REQUEST_BYTES = 16384
MAX_RESPONSE_BYTES = 32768

ACTION_FRAME_SCHEMA = 'mastermind.workspace_project_admission_action.v1'
FRAME_SCHEMA = ACTION_FRAME_SCHEMA
OPERATION = 'pause_workstream_admission'
STATUS_FRAME_SCHEMA = 'mastermind.workspace_project_admission_status.v1'
STATUS_OPERATION = 'read_pause_command'

ACTION_RESULT_SCHEMA = 'mastermind.workspace_project_admission_action_result.v1'
STATUS_RESULT_SCHEMA = 'mastermind.workspace_project_admission_status_result.v1'
ADMISSION_RECEIPT_SCHEMA = 'mastermind.workstream_admission_suspension_receipt.v1'

# Shape of the read principal carried on frames.  It proves identity only;
# the suspend grant itself is sealed elsewhere and is never validated here.
READ_PRINCIPAL_RESOURCE = workspace.RESOURCE
READ_PRINCIPAL_SCOPES = [workspace.SCOPE]

COMMITTED = 'COMMITTED'
NOT_DISPATCHED = 'NOT_DISPATCHED'
EFFECT_UNKNOWN = 'EFFECT_UNKNOWN'

OBSERVED = 'OBSERVED'
NOT_OBSERVED = 'NOT_OBSERVED'
UNAVAILABLE = 'UNAVAILABLE'

RECEIPT_STATE_PAUSED = 'PAUSED'

NOT_DISPATCHED_REASON_CODES = (
    'INVALID_INPUT',
    'ACCESS_DENIED',
    'SOURCE_UNAVAILABLE',
    'SOURCE_CHANGED',
    'ROOT_MISMATCH',
    'OWNER_NOT_READY',
)
EFFECT_UNKNOWN_REASON_CODES = ('OWNER_OUTCOME_UNCONFIRMED',)
UNAVAILABLE_REASON_CODES = NOT_DISPATCHED_REASON_CODES

ACTION_FRAME_KEYS = frozenset(
    {'schema', 'operation', 'selection', 'principal', 'admission_expires_at'}
)
SELECTION_KEYS = frozenset({'work_ref', 'root_job_id', 'command_id'})
PRINCIPAL_KEYS = workspace.PRINCIPAL_KEYS
ACTION_RESULT_KEYS = frozenset(
    {'schema', 'selection', 'disposition', 'receipt', 'reason_codes'}
)
STATUS_RESULT_KEYS = frozenset(
    {'schema', 'selection', 'state', 'receipt', 'reason_codes'}
)
RECEIPT_KEYS = frozenset(
    {
        'schema',
        'work_ref',
        'state',
        'event_id',
        'command_id',
        'request_digest',
        'committed_at_ms',
    }
)

_WORK_REF = re.compile(r'WS:[A-Z0-9][A-Za-z0-9._-]{1,63}')
_ROOT_JOB_ID = re.compile(r'JOB-[0-9]{1,9}')
_COMMAND_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}')
_REQUEST_DIGEST = re.compile(r'[0-9a-f]{64}')

_MAX_ID_CHARS = 256


def _invalid():
    return ValueError('invalid_input')


def _exact_keys(value, keys):
    if not isinstance(value, dict) or set(value.keys()) != set(keys):
        raise _invalid()


def _exact_int(value, minimum):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _invalid()


def _exact_str(value, maximum=_MAX_ID_CHARS):
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise _invalid()


def _detached(value):
    """Return a JSON-round-tripped copy sharing no mutable state with input."""
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError):
        raise _invalid() from None


def _expected_selection(expected):
    """Validate ``expected`` given as a selection, a frame or a result body."""
    if isinstance(expected, dict) and 'selection' in expected:
        return selection(expected['selection'])
    return selection(expected)


def _paired_no_receipt(receipt, reasons, allowed):
    if receipt is not None:
        raise _invalid()
    if not isinstance(reasons, list) or len(reasons) != 1:
        raise _invalid()
    code = reasons[0]
    if not isinstance(code, str) or code not in allowed:
        raise _invalid()


def selection(value):
    """Closed project selection with original command and optional root proof."""
    from common.workspace_project_admission_selection import selection as project_selection
    return project_selection(value, command=True)


def validate_principal(value):
    """Reuse the actual installed identity-shape owner; this grants no action."""
    workspace.validate_v3_frame({"schema": workspace.FRAME_SCHEMA_V3, "operation": "admitted_plan",
        "selection": {"work_ref": "WS:VALIDATOR", "root_job_id": "JOB-1"}, "principal": value})
    return _detached(value)


def validate_frame(value, status=False):
    """Validate a private admission frame and return a detached copy.

    ``status=False`` validates the pause action frame; ``status=True``
    validates the pause-command read frame.  The frame shape grants no
    authority: the verified HTTP owner derives principal and expiry itself
    and never accepts a caller-provided Runtime actor.
    """
    if status:
        expected_schema, expected_operation = STATUS_FRAME_SCHEMA, STATUS_OPERATION
    else:
        expected_schema, expected_operation = ACTION_FRAME_SCHEMA, OPERATION
    _exact_keys(value, ACTION_FRAME_KEYS)
    if value['schema'] != expected_schema or value['operation'] != expected_operation:
        raise _invalid()
    selection(value['selection'])
    validate_principal(value['principal'])
    _exact_int(value['admission_expires_at'], minimum=1)
    if len(canonical_json_bytes(value)) + 1 > MAX_REQUEST_BYTES:
        raise _invalid()
    return _detached(value)


def validate_receipt(value, expected_selection):
    """Validate a suspension receipt against ``expected_selection``.

    The public validator checks ``request_digest`` format only (64 lowercase
    hex); recomputation belongs to the verified owner with the actual server
    actor.  ``root_job_id`` is intentionally absent from receipts.
    """
    expected = _expected_selection(expected_selection)
    _exact_keys(value, RECEIPT_KEYS)
    if value['schema'] != ADMISSION_RECEIPT_SCHEMA or value['state'] != RECEIPT_STATE_PAUSED:
        raise _invalid()
    if value['work_ref'] != expected['work_ref']:
        raise _invalid()
    if value['command_id'] != expected['command_id']:
        raise _invalid()
    _exact_int(value['event_id'], minimum=1)
    _exact_int(value['committed_at_ms'], minimum=0)
    digest = value['request_digest']
    if not isinstance(digest, str) or _REQUEST_DIGEST.fullmatch(digest) is None:
        raise _invalid()
    return _detached(value)


def validate_action_result(value, expected):
    """Validate a public action-result body for ``expected`` selection.

    ``COMMITTED`` carries the original committed receipt from the Runtime
    owner; ``NOT_DISPATCHED`` and ``EFFECT_UNKNOWN`` carry no receipt and
    never collapse into a no-effect conclusion.
    """
    if not isinstance(value, dict):
        raise ValueError('source_unavailable')
    expected = _expected_selection(expected)
    _exact_keys(value, ACTION_RESULT_KEYS)
    if value['schema'] != ACTION_RESULT_SCHEMA:
        raise _invalid()
    body_selection = selection(value['selection'])
    if body_selection != expected:
        raise _invalid()
    disposition, receipt, reasons = (
        value['disposition'],
        value['receipt'],
        value['reason_codes'],
    )
    if disposition == COMMITTED:
        if receipt is None:
            raise _invalid()
        validate_receipt(receipt, body_selection)
        if reasons != []:
            raise _invalid()
    elif disposition == NOT_DISPATCHED:
        _paired_no_receipt(receipt, reasons, NOT_DISPATCHED_REASON_CODES)
    elif disposition == EFFECT_UNKNOWN:
        _paired_no_receipt(receipt, reasons, EFFECT_UNKNOWN_REASON_CODES)
    else:
        raise _invalid()
    if len(canonical_json_bytes({"ok": True, "result": value})) + 1 > MAX_RESPONSE_BYTES:
        raise ValueError("source_unavailable")
    return _detached(value)


def validate_status_result(value, expected):
    """Validate a public status-result body for ``expected`` selection.

    ``NOT_OBSERVED`` records absence of observation only: it never proves
    that no effect occurred and never permits a retry.
    """
    if not isinstance(value, dict):
        raise ValueError('source_unavailable')
    expected = _expected_selection(expected)
    _exact_keys(value, STATUS_RESULT_KEYS)
    if value['schema'] != STATUS_RESULT_SCHEMA:
        raise _invalid()
    body_selection = selection(value['selection'])
    if body_selection != expected:
        raise _invalid()
    state, receipt, reasons = value['state'], value['receipt'], value['reason_codes']
    if state == OBSERVED:
        if receipt is None:
            raise _invalid()
        validate_receipt(receipt, body_selection)
        if reasons != []:
            raise _invalid()
    elif state == NOT_OBSERVED:
        if receipt is not None or reasons != []:
            raise _invalid()
    elif state == UNAVAILABLE:
        _paired_no_receipt(receipt, reasons, UNAVAILABLE_REASON_CODES)
    else:
        raise _invalid()
    if len(canonical_json_bytes({"ok": True, "result": value})) + 1 > MAX_RESPONSE_BYTES:
        raise ValueError("source_unavailable")
    return _detached(value)


def canonical_json_bytes(value):
    """Canonical JSON: sorted keys, UTF-8, no spaces, NaN/Infinity rejected."""
    try:
        text = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(',', ':'),
        )
    except (TypeError, ValueError):
        raise _invalid() from None
    return text.encode('utf-8')


def canonical_request_bytes(value, status=False):
    """Validate a frame and return its bounded canonical request bytes."""
    frame = validate_frame(value, status=status)
    payload = canonical_json_bytes(frame)
    if len(payload) > MAX_REQUEST_BYTES:
        raise _invalid()
    return payload


def response_envelope_bytes(value, expected, *, status=False):
    """Validate a public body and return the bounded envelope bytes.

    The size counted is the canonical outer ``{'ok': True, 'result': body}``
    plus one trailing newline; an unusable or oversized body raises
    ``ValueError('source_unavailable')`` without echoing input.
    """
    if status:
        body = validate_status_result(value, expected)
    else:
        body = validate_action_result(value, expected)
    try:
        text = json.dumps(
            {'ok': True, 'result': body},
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(',', ':'),
        )
    except (TypeError, ValueError):
        raise ValueError('source_unavailable') from None
    payload = (text + '\n').encode('utf-8')
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError('source_unavailable')
    return payload
