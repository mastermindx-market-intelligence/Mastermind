"""Retained JOB_CLAIMED capacity projection: verification and safe projection.

Positive cases rebuild the supplied synthetic ``good_snapshot`` validator vector
locally; they are validator vectors, not evidence about any live provider.
"""
from __future__ import annotations

import copy
from datetime import UTC, datetime
import json
import hashlib
import pytest

from control_plane import native_capacity_v2 as v2
from control_plane.retained_capacity_projection import (
    EVIDENCE_SCHEMA,
    RESULT_SCHEMA,
    RetainedCapacityError,
    project_retained_capacity,
)

CLAIM_AT_MS = 1_700_000_000_000
NOW_MS = CLAIM_AT_MS + 1_000
HOST_REF = 'host-' + 'a' * 64
BOOT_REF = 'boot-' + 'b' * 64
FINGERPRINT = 'c' * 64
ROOT_JOB_ID = 'root-' + '5' * 16
JOB_ID = 'job-' + '7' * 16
ATTEMPT_ID = 'attempt-' + '8' * 12
WORKER_ID = 'worker-' + '9' * 12
QUOTA_CLASS = 'subscription'
COMMAND_ID = f'coo-cycle:{ROOT_JOB_ID}:dispatch:{JOB_ID}:attempt:1'
CLAIM_EVENT_ID = 17
BEGIN_EVENT_ID = 16

RESULT_KEYS = frozenset({'schema', 'root_job_id', 'job_id', 'attempt_id', 'claim_event_id',
                         'begin_event_id', 'claim_recorded_at_ms', 'observed_at_ms', 'age_ms',
                         'source_snapshot_sha256', 'source_release_commit', 'host_ref',
                         'boot_ref', 'provider', 'provider_enabled', 'realm_auth',
                         'provider_health', 'cooling', 'quota_horizons', 'current_eligibility',
                         'can_place_work', 'observation_kind'})


def _stamp(ms):
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def good_snapshot(now):
    stamp = _stamp(now)
    reset = _stamp(now + 60000)
    row = {'host_ref': HOST_REF, 'boot_ref': BOOT_REF, 'capacity_capability_id': 'ncap_test',
           'capability_generation': 3, 'realm_generation': 2, 'enrollment_receipt_digest': 'e' * 64,
           'provider': 'minimax', 'provider_enabled': True, 'worker_source_config_digest': 'c' * 64,
           'observed_at': stamp,
           'realm_auth': {'state': 'authenticated', 'method': 'subscription_api_key',
                          'source_quality': 'native_provider'},
           'provider_health': {'state': 'healthy', 'error_class': None,
                               'scope': 'capability_generation', 'observed_at': stamp},
           'cooling': {'active': False, 'kind': None, 'reset_at': None,
                       'evidence': 'native_provider', 'scope': 'capability_generation',
                       'observed_at': stamp},
           'quota_horizons': [{'name': 'subscription', 'remaining': 1, 'limit': 10,
                               'reset_at': reset, 'scope': 'capability_generation',
                               'observed_at': stamp}],
           'last_provider_outcome': {'class': 'success', 'scope': 'capability_generation',
                                     'observed_at': stamp}}
    value = {'schema': v2.SCHEMA, 'generated_at_ms': now,
             'source': {'source_release_commit': 'a' * 40, 'previous_release_commit': 'b' * 40,
                        'material_source_digest': 'd' * 64, 'source_receipt_digest': 'f' * 64,
                        'registration_receipt_digest': '0' * 64},
             'producer_sha256': '1' * 64, 'slots': [row]}
    value['snapshot_hash'] = v2.digest(value)
    return value


def _reseal(snapshot):
    snapshot['snapshot_hash'] = v2.digest({k: v for k, v in snapshot.items() if k != 'snapshot_hash'})


def _physical():
    return {'host_ref': HOST_REF, 'boot_ref': BOOT_REF, 'deadline_ms': CLAIM_AT_MS + 60_000,
            'request_fingerprint': FINGERPRINT, 'begin_event_id': BEGIN_EVENT_ID}


def _claim_event(snapshot, physical):
    return {'event_id': CLAIM_EVENT_ID, 'event_type': 'JOB_CLAIMED', 'aggregate_type': 'job',
            'aggregate_id': JOB_ID, 'sequence': 7, 'command_id': COMMAND_ID,
            'actor': 'actor-secret-value', 'job_id': JOB_ID, 'attempt_id': ATTEMPT_ID,
            'worker_id': WORKER_ID, 'quota_class': QUOTA_CLASS,
            'payload': {'lease': 'internal-lease-detail',
                        'capacity_evidence': {'schema': EVIDENCE_SCHEMA,
                                              'provider_capacity': snapshot,
                                              'physical_capacity': physical}},
            'created_at': _stamp(CLAIM_AT_MS)}


def _begin_event(physical):
    return {'event_id': BEGIN_EVENT_ID, 'event_type': 'PHYSICAL_RESOURCE_BEGIN',
            'aggregate_type': 'physical_resource_operation', 'aggregate_id': hashlib.sha256(json.dumps([HOST_REF, f'finite-initial:{JOB_ID}'], sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'sequence': 3, 'command_id': f'physical:{COMMAND_ID}:begin', 'actor': 'broker-secret-actor',
            'job_id': None, 'attempt_id': None, 'worker_id': None, 'quota_class': None,
            'payload': {'action': 'begin', 'command_fingerprint': '3' * 64,
                        'receipt': {'operation_key': f'finite-initial:{JOB_ID}', 'request_fingerprint': physical['request_fingerprint'], 'commitments': [{'phase_key': 'attempt-1', 'state': 'EFFECT_MAY_HAVE_BEGUN', 'demands': [{'window_binding': {'boot_id': BOOT_REF}}]}]},
                        'original_event_id': None},
            'created_at': _stamp(CLAIM_AT_MS - 5_000)}


def scenario():
    snapshot = good_snapshot(CLAIM_AT_MS)
    physical = _physical()
    return {'root_job_id': ROOT_JOB_ID, 'job_id': JOB_ID, 'attempt_id': ATTEMPT_ID,
            'worker_id': WORKER_ID, 'quota_class': QUOTA_CLASS, 'command_id': COMMAND_ID,
            'claim_event': _claim_event(snapshot, physical),
            'begin_event': _begin_event(physical), 'now_ms': NOW_MS}


def _mutated(change):
    call = scenario()
    change(call)
    return call


def _assert_safe_integers(value):
    if type(value) is int:
        assert -(2**53 - 1) <= value <= 2**53 - 1
    elif type(value) is dict:
        for item in value.values():
            _assert_safe_integers(item)
    elif type(value) is list:
        for item in value:
            _assert_safe_integers(item)


def test_projects_retained_claim_into_safe_historical_shape():
    call = scenario()
    result = project_retained_capacity(**call)
    snapshot = call['claim_event']['payload']['capacity_evidence']['provider_capacity']
    _assert_safe_integers(result)
    assert set(result) == RESULT_KEYS
    assert result['schema'] == RESULT_SCHEMA
    assert (result['root_job_id'], result['job_id'], result['attempt_id']) == (ROOT_JOB_ID, JOB_ID, ATTEMPT_ID)
    assert result['claim_event_id'] == CLAIM_EVENT_ID
    assert result['begin_event_id'] == BEGIN_EVENT_ID
    assert result['claim_recorded_at_ms'] == CLAIM_AT_MS
    assert result['observed_at_ms'] == CLAIM_AT_MS
    assert result['age_ms'] == NOW_MS - CLAIM_AT_MS
    assert result['source_snapshot_sha256'] == snapshot['snapshot_hash']
    assert result['source_release_commit'] == 'a' * 40
    assert (result['host_ref'], result['boot_ref'], result['provider']) == (HOST_REF, BOOT_REF, 'minimax')
    assert result['provider_enabled'] is True
    assert result['realm_auth'] == {'state': 'authenticated', 'source_quality': 'native_provider'}
    assert result['provider_health'] == {'state': 'healthy', 'error_class': None}
    assert result['cooling'] == {'active': False, 'kind': None, 'reset_at': None}
    assert result['quota_horizons'] == [{'name': 'subscription', 'remaining': 1, 'limit': 10,
                                         'reset_at': _stamp(CLAIM_AT_MS + 60000)}]
    assert result['current_eligibility'] == 'NOT_EVALUATED'
    assert result['can_place_work'] is False
    assert result['observation_kind'] == 'RETAINED_CLAIM'


def test_projection_is_closed_and_redacted():
    result = project_retained_capacity(**scenario())
    rendered = json.dumps(result, sort_keys=True)
    assert set(result) == RESULT_KEYS
    assert set(result['realm_auth']) == {'state', 'source_quality'}
    assert set(result['provider_health']) == {'state', 'error_class'}
    assert set(result['cooling']) == {'active', 'kind', 'reset_at'}
    assert all(set(h) == {'name', 'remaining', 'limit', 'reset_at'} for h in result['quota_horizons'])
    for secret in ('actor-secret-value', 'broker-secret-actor', 'internal-lease-detail',
                   'subscription_api_key', '1' * 64, 'd' * 64, 'f' * 64, '0' * 64,
                   'e' * 64, 'c' * 64, 'cf-' + '3' * 12):
        assert secret not in rendered
    for forbidden in ('method', 'payload', 'actor', 'producer_sha256', 'material_source_digest',
                      'source_receipt_digest', 'registration_receipt_digest',
                      'enrollment_receipt_digest', 'worker_source_config_digest',
                      'last_provider_outcome', 'path', 'credential', 'account'):
        assert forbidden not in rendered


def test_unknown_historical_facts_are_projected_not_normalized_or_refused():
    def change(call):
        evidence = call['claim_event']['payload']['capacity_evidence']
        row = evidence['provider_capacity']['slots'][0]
        row['provider_enabled'] = None
        row['realm_auth'] = {'state': 'unknown', 'method': 'unknown', 'source_quality': 'unknown'}
        row['provider_health'] = {'state': 'unknown', 'error_class': None, 'scope': 'unknown',
                                  'observed_at': None}
        row['cooling'] = {'active': None, 'kind': None, 'reset_at': None, 'evidence': 'unknown',
                          'scope': 'unknown', 'observed_at': None}
        _reseal(evidence['provider_capacity'])

    result = project_retained_capacity(**_mutated(change))
    assert result['provider_enabled'] is None
    assert result['realm_auth'] == {'state': 'unknown', 'source_quality': 'unknown'}
    assert result['provider_health'] == {'state': 'unknown', 'error_class': None}
    assert result['cooling'] == {'active': None, 'kind': None, 'reset_at': None}
    assert result['current_eligibility'] == 'NOT_EVALUATED' and result['can_place_work'] is False


def test_empty_historical_quota_horizons_project_empty():
    def change(call):
        evidence = call['claim_event']['payload']['capacity_evidence']
        evidence['provider_capacity']['slots'][0]['quota_horizons'] = []
        _reseal(evidence['provider_capacity'])

    result = project_retained_capacity(**_mutated(change))
    assert result['quota_horizons'] == []
    assert result['current_eligibility'] == 'NOT_EVALUATED'


@pytest.mark.parametrize('change', [
    lambda call: call['claim_event'].update(event_type='JOB_OFFERED'),
    lambda call: call['claim_event'].update(aggregate_type='attempt'),
    lambda call: call['claim_event'].update(aggregate_id='job-mismatch'),
    lambda call: call['claim_event'].update(job_id='job-mismatch'),
    lambda call: call['claim_event'].update(attempt_id='attempt-mismatch'),
    lambda call: call['claim_event'].update(worker_id='worker-mismatch'),
    lambda call: call['claim_event'].update(quota_class='other-class'),
    lambda call: call['claim_event'].update(command_id='command-mismatch'),
    lambda call: call['claim_event'].update(sequence=True),
    lambda call: call['claim_event'].update(created_at=_stamp(NOW_MS + 5_000)),
    lambda call: call['claim_event']['payload'].pop('capacity_evidence'),
    lambda call: call['claim_event']['payload']['capacity_evidence'].update(
        schema='mastermind.finite_initial_claim/v2'),
    lambda call: call['claim_event']['payload']['capacity_evidence'].update(extra=True),
    lambda call: call['claim_event']['payload']['capacity_evidence']['physical_capacity'].update(
        begin_event_id='begin-event-other'),
    lambda call: call['claim_event']['payload']['capacity_evidence']['physical_capacity'].update(
        host_ref='host-' + 'e' * 64),
    lambda call: call['claim_event']['payload']['capacity_evidence']['physical_capacity'].update(
        deadline_ms=CLAIM_AT_MS),
    lambda call: call['claim_event']['payload']['capacity_evidence']['physical_capacity'].update(
        deadline_ms=CLAIM_AT_MS - 1),
    lambda call: call['begin_event'].update(event_type='PHYSICAL_RESOURCE_END'),
    lambda call: call['begin_event'].update(aggregate_type='job'),
    lambda call: call['begin_event'].update(event_id='begin-event-unreferenced'),
    lambda call: call['begin_event']['payload'].update(action='reserve'),
    lambda call: call['begin_event'].update(aggregate_id='e'*64),
    lambda call: call['begin_event']['payload']['receipt'].update(
        request_fingerprint='fp-mismatch'),
    lambda call: call['begin_event']['payload']['receipt'].pop('operation_key'),
    lambda call: call.update(now_ms=CLAIM_AT_MS - 1),
    lambda call: call.update(now_ms=0),
    lambda call: call.update(now_ms=2**53),
    lambda call: call.update(now_ms='now'),
    lambda call: call.update(worker_id=''),
    lambda call: _ambiguous_rows(call),
    lambda call: _zero_rows(call),
    lambda call: _tampered_snapshot(call),
])
def test_mismatch_and_clock_cases_fail_closed(change):
    with pytest.raises(RetainedCapacityError, match=r'^RETAINED_CAPACITY_INVALID$'):
        project_retained_capacity(**_mutated(change))


def _ambiguous_rows(call):
    evidence = call['claim_event']['payload']['capacity_evidence']
    snapshot = evidence['provider_capacity']
    extra = copy.deepcopy(snapshot['slots'][0])
    extra['capacity_capability_id'] = 'ncap_other'
    snapshot['slots'].append(extra)
    _reseal(snapshot)


def _zero_rows(call):
    evidence = call['claim_event']['payload']['capacity_evidence']
    evidence['provider_capacity']['slots'][0]['host_ref'] = 'host-' + 'e' * 64
    _reseal(evidence['provider_capacity'])


def _tampered_snapshot(call):
    evidence = call['claim_event']['payload']['capacity_evidence']
    evidence['provider_capacity']['snapshot_hash'] = 'f' * 64


def test_incumbent_snapshot_refusal_is_wrapped_without_raw_text():
    tampered = _mutated(_tampered_snapshot)
    try:
        v2.validate_snapshot(tampered['claim_event']['payload']['capacity_evidence']['provider_capacity'],
                             now_ms=CLAIM_AT_MS)
    except v2.NativeCapacityRefusal:
        pass
    else:
        raise AssertionError('tampered snapshot must fail the incumbent validator')
    with pytest.raises(RetainedCapacityError, match=r'^RETAINED_CAPACITY_INVALID$'):
        project_retained_capacity(**tampered)


def test_refusal_is_stable_value_error_without_incumbent_type():
    with pytest.raises(ValueError) as excinfo:
        project_retained_capacity(**_mutated(lambda call: call.update(now_ms='now')))
    error_type = type(excinfo.value)
    assert issubclass(error_type, ValueError)
    assert error_type is not v2.NativeCapacityRefusal
    assert str(excinfo.value) == 'RETAINED_CAPACITY_INVALID'
    assert getattr(error_type, 'code', None) == 'RETAINED_CAPACITY_INVALID'
