"""Strict projection of already-retained qualified JOB_CLAIMED capacity evidence.

Pure, additive and fail-closed: the caller has independently qualified the
coordinates, root membership and the current Attempt. This module only verifies
the retained evidence chain -- claim event coordinates, the physical BEGIN
receipt binding and the incumbent V2 snapshot at the immutable claim instant --
and projects the historical provider-capacity row into a safe closed shape.

No acquisition, no Runtime read/write, no authentication and no current-grant
decision happens here: ``known_admissible`` is never consulted, observation age
and source are never refreshed, and every projection is explicitly
``NOT_EVALUATED`` with ``can_place_work=False``.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import hashlib
import json
import re

from control_plane import native_capacity_v2 as v2

RESULT_SCHEMA = 'mastermind.retained_provider_capacity.v1'
EVIDENCE_SCHEMA = 'mastermind.finite_initial_claim/v1'
CLAIM_EVENT_TYPE = 'JOB_CLAIMED'
CLAIM_AGGREGATE_TYPE = 'job'
BEGIN_EVENT_TYPE = 'PHYSICAL_RESOURCE_BEGIN'
BEGIN_AGGREGATE_TYPE = 'physical_resource_operation'
SAFE_INTEGER_MAX = 2**53 - 1

_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}')
_STAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)')
_EVENT_KEYS = frozenset({'event_id','event_type','aggregate_type','aggregate_id','sequence',
                         'command_id','actor','job_id','attempt_id','worker_id','quota_class',
                         'payload','created_at'})
_EVIDENCE_KEYS = frozenset({'schema','provider_capacity','physical_capacity'})
_PHYSICAL_KEYS = frozenset({'host_ref','boot_ref','deadline_ms','request_fingerprint','begin_event_id'})
_BEGIN_PAYLOAD_KEYS = frozenset({'action','command_fingerprint','receipt','original_event_id'})

class RetainedCapacityError(ValueError):
    """Stable fail-closed refusal; the message is the bare code, never input."""

    code = 'RETAINED_CAPACITY_INVALID'

def _refuse():
    raise RetainedCapacityError('RETAINED_CAPACITY_INVALID')

def _identifier(value):
    if type(value) is not str or _ID.fullmatch(value) is None:
        _refuse()
    return value

def _safe(value, minimum=0, maximum=SAFE_INTEGER_MAX):
    if type(value) is not int or not minimum <= value <= maximum:
        _refuse()
    return value

def _stamp_ms(value):
    """Incumbent ISO UTC stamp as bounded milliseconds; never refreshed."""
    if type(value) is not str or _STAMP.fullmatch(value) is None:
        _refuse()
    try:
        return _safe(int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() * 1000), 1)
    except (ValueError, OverflowError):
        _refuse()

def _event(value):
    if not isinstance(value, Mapping) or set(value) != _EVENT_KEYS:
        _refuse()
    return value

def project_retained_capacity(*, root_job_id: str, job_id: str, attempt_id: str, worker_id: str,
                              quota_class: str, command_id: str, claim_event: Mapping,
                              begin_event: Mapping, now_ms: int) -> dict:
    """Verify retained claim evidence and project its historical capacity row."""
    now_ms = _safe(now_ms, 1)
    for identifier in (root_job_id, job_id, attempt_id, worker_id, quota_class, command_id):
        _identifier(identifier)
    claim_event = _event(claim_event)
    begin_event = _event(begin_event)
    claim_ms = _stamp_ms(claim_event['created_at'])
    if claim_ms > now_ms:
        _refuse()
    _verify_claim(claim_event, job_id=job_id, attempt_id=attempt_id, worker_id=worker_id,
                  quota_class=quota_class, command_id=command_id)
    evidence = _capacity_evidence(claim_event)
    physical = _physical_capacity(evidence)
    if physical['deadline_ms'] <= claim_ms:
        _refuse()
    if command_id != f'coo-cycle:{root_job_id}:dispatch:{job_id}:attempt:1':
        _refuse()
    _verify_begin(begin_event, physical, job_id=job_id, command_id=command_id, claim_ms=claim_ms)
    snapshot, row = _historical_row(evidence['provider_capacity'], physical, claim_ms)
    return _project(root_job_id=root_job_id, job_id=job_id, attempt_id=attempt_id,
                    claim_event_id=claim_event['event_id'], begin_event_id=begin_event['event_id'],
                    now_ms=now_ms, claim_ms=claim_ms, snapshot=snapshot, row=row)

def _verify_claim(event, *, job_id, attempt_id, worker_id, quota_class, command_id):
    if (event['event_type'] != CLAIM_EVENT_TYPE or event['aggregate_type'] != CLAIM_AGGREGATE_TYPE
            or event['aggregate_id'] != job_id or event['job_id'] != job_id
            or event['attempt_id'] != attempt_id or event['worker_id'] != worker_id
            or event['quota_class'] != quota_class or event['command_id'] != command_id):
        _refuse()
    _safe(event['event_id'], 1)
    _safe(event['sequence'], 1)

def _capacity_evidence(event):
    payload = event['payload']
    if type(payload) is not dict:
        _refuse()
    evidence = payload.get('capacity_evidence')
    if (type(evidence) is not dict or set(evidence) != _EVIDENCE_KEYS
            or evidence['schema'] != EVIDENCE_SCHEMA):
        _refuse()
    return evidence

def _physical_capacity(evidence):
    physical = evidence['physical_capacity']
    if type(physical) is not dict or set(physical) != _PHYSICAL_KEYS:
        _refuse()
    for key, prefix in (('host_ref', 'host-'), ('boot_ref', 'boot-'), ('request_fingerprint', '')):
        value = physical[key]
        if type(value) is not str or re.fullmatch(re.escape(prefix) + r'[0-9a-f]{64}', value) is None:
            _refuse()
    _safe(physical['begin_event_id'], 1)
    _safe(physical['deadline_ms'], 1)
    return physical

def _verify_begin(event, physical, *, job_id, command_id, claim_ms):
    operation_key = f'finite-initial:{job_id}'
    aggregate = hashlib.sha256(json.dumps([physical['host_ref'], operation_key], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if (event['event_type'] != BEGIN_EVENT_TYPE or event['aggregate_type'] != BEGIN_AGGREGATE_TYPE
            or event['event_id'] != physical['begin_event_id'] or event['aggregate_id'] != aggregate
            or event['command_id'] != f'physical:{command_id}:begin'
            or _stamp_ms(event['created_at']) > claim_ms):
        _refuse()
    _safe(event['event_id'], 1)
    _safe(event['sequence'], 1)
    payload = event['payload']
    if (type(payload) is not dict or set(payload) not in (_BEGIN_PAYLOAD_KEYS, _BEGIN_PAYLOAD_KEYS | {'capacity_capture'})
            or payload['action'] != 'begin' or payload['original_event_id'] is not None
            or type(payload['command_fingerprint']) is not str
            or re.fullmatch(r'[0-9a-f]{64}', payload['command_fingerprint']) is None):
        _refuse()
    if 'capacity_capture' in payload:
        capture = payload['capacity_capture']
        if type(capture) is not dict or capture.get('schema') != 'mastermind.physical_capacity_capture/v1' or capture.get('can_place_work') is not False:
            _refuse()
    receipt = payload['receipt']
    if (type(receipt) is not dict or set(receipt) != {'operation_key', 'request_fingerprint', 'commitments'}
            or receipt['operation_key'] != operation_key
            or receipt['request_fingerprint'] != physical['request_fingerprint']
            or type(receipt['commitments']) is not list or len(receipt['commitments']) != 1):
        _refuse()
    commitment = receipt['commitments'][0]
    if (type(commitment) is not dict or commitment.get('phase_key') != 'attempt-1'
            or commitment.get('state') != 'EFFECT_MAY_HAVE_BEGUN'
            or type(commitment.get('demands')) is not list or not 1 <= len(commitment['demands']) <= 64):
        _refuse()
    for demand in commitment['demands']:
        if (type(demand) is not dict or type(demand.get('window_binding')) is not dict
                or demand['window_binding'].get('boot_id') != physical['boot_ref']):
            _refuse()

def _historical_row(provider_capacity, physical, claim_ms):
    """Incumbent strict verification at the immutable claim instant, then the
    exactly-one historical row bound to this physical host+boot."""
    try:
        snapshot = v2.validate_snapshot(provider_capacity, now_ms=claim_ms)
    except (v2.NativeCapacityRefusal, TypeError, ValueError, KeyError, RecursionError):
        _refuse()
    rows = [row for row in snapshot['slots'] if row['host_ref'] == physical['host_ref']
            and row['boot_ref'] == physical['boot_ref']]
    if len(rows) != 1:
        _refuse()
    return snapshot, rows[0]

def _project(*, root_job_id, job_id, attempt_id, claim_event_id, begin_event_id, now_ms,
             claim_ms, snapshot, row):
    observed_ms = _stamp_ms(row['observed_at'])
    return {
        'schema': RESULT_SCHEMA,
        'root_job_id': root_job_id,
        'job_id': job_id,
        'attempt_id': attempt_id,
        'claim_event_id': claim_event_id,
        'begin_event_id': begin_event_id,
        'claim_recorded_at_ms': claim_ms,
        'observed_at_ms': observed_ms,
        'age_ms': _safe(now_ms - observed_ms),
        'source_snapshot_sha256': snapshot['snapshot_hash'],
        'source_release_commit': snapshot['source']['source_release_commit'],
        'host_ref': row['host_ref'],
        'boot_ref': row['boot_ref'],
        'provider': row['provider'],
        'provider_enabled': row['provider_enabled'],
        'realm_auth': {'state': row['realm_auth']['state'],
                       'source_quality': row['realm_auth']['source_quality']},
        'provider_health': {'state': row['provider_health']['state'],
                            'error_class': row['provider_health']['error_class']},
        'cooling': {'active': row['cooling']['active'], 'kind': row['cooling']['kind'],
                    'reset_at': row['cooling']['reset_at']},
        'quota_horizons': [{'name': horizon['name'], 'remaining': _safe(horizon['remaining'], 0),
                            'limit': _safe(horizon['limit'], 0), 'reset_at': horizon['reset_at']}
                           for horizon in row['quota_horizons']],
        'current_eligibility': 'NOT_EVALUATED',
        'can_place_work': False,
        'observation_kind': 'RETAINED_CLAIM',
    }
