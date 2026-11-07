"""Tests for the workspace project admission pause-wire contract.

Real pytest fixtures only; no network, no secrets, no provider credentials,
no dependency installs.  Every fabricated value is local wire data.
"""

from __future__ import annotations

import json
import sys

import pytest

from common import workspace_project_admission_contract as contract


@pytest.fixture
def long_int_digits():
    """Temporarily lift CPython's 4300-digit int<->str conversion limit."""
    previous = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(60000)
    yield
    if previous:
        sys.set_int_max_str_digits(previous)
    else:
        sys.set_int_max_str_digits(0)


def canonical(value):
    """Independent canonical encoder used to cross-check module output."""
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(',', ':'),
    ).encode('utf-8')


def assert_invalid(callable_value):
    with pytest.raises(ValueError) as excinfo:
        callable_value()
    assert str(excinfo.value) == 'invalid_input'


def assert_source_unavailable(callable_value):
    with pytest.raises(ValueError) as excinfo:
        callable_value()
    assert str(excinfo.value) == 'source_unavailable'


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def selection():
    return {'work_ref': 'WS:ACQ', 'root_job_id': 'JOB-42', 'command_id': 'cmd-1'}


@pytest.fixture
def principal():
    return {
        'issuer_digest': 'tenant-1',
        'subject_digest': 'user-1',
        'policy_id': 'policy-1',
        'client_ref': 'v4',
        'resource': contract.READ_PRINCIPAL_RESOURCE,
        'scopes': list(contract.READ_PRINCIPAL_SCOPES),
    }


@pytest.fixture
def admission_expires_at():
    return 1800000000000


@pytest.fixture
def action_frame(selection, principal, admission_expires_at):
    return {
        'operation': contract.OPERATION,
        'admission_expires_at': admission_expires_at,
        'schema': contract.ACTION_FRAME_SCHEMA,
        'principal': principal,
        'selection': dict(selection),
    }


@pytest.fixture
def status_frame(selection, principal, admission_expires_at):
    return {
        'schema': contract.STATUS_FRAME_SCHEMA,
        'operation': contract.STATUS_OPERATION,
        'selection': dict(selection),
        'principal': principal,
        'admission_expires_at': admission_expires_at,
    }


@pytest.fixture
def receipt(selection):
    return {
        'schema': contract.ADMISSION_RECEIPT_SCHEMA,
        'work_ref': selection['work_ref'],
        'state': contract.RECEIPT_STATE_PAUSED,
        'event_id': 17,
        'command_id': selection['command_id'],
        'request_digest': 'a' * 64,
        'committed_at_ms': 1700000000000,
    }


@pytest.fixture
def committed_body(selection, receipt):
    return {
        'schema': contract.ACTION_RESULT_SCHEMA,
        'selection': dict(selection),
        'disposition': contract.COMMITTED,
        'receipt': dict(receipt),
        'reason_codes': [],
    }


@pytest.fixture
def not_dispatched_body(selection):
    return {
        'schema': contract.ACTION_RESULT_SCHEMA,
        'selection': dict(selection),
        'disposition': contract.NOT_DISPATCHED,
        'receipt': None,
        'reason_codes': ['ACCESS_DENIED'],
    }


@pytest.fixture
def effect_unknown_body(selection):
    return {
        'schema': contract.ACTION_RESULT_SCHEMA,
        'selection': dict(selection),
        'disposition': contract.EFFECT_UNKNOWN,
        'receipt': None,
        'reason_codes': ['OWNER_OUTCOME_UNCONFIRMED'],
    }


@pytest.fixture
def observed_body(selection, receipt):
    return {
        'schema': contract.STATUS_RESULT_SCHEMA,
        'selection': dict(selection),
        'state': contract.OBSERVED,
        'receipt': dict(receipt),
        'reason_codes': [],
    }


@pytest.fixture
def not_observed_body(selection):
    return {
        'schema': contract.STATUS_RESULT_SCHEMA,
        'selection': dict(selection),
        'state': contract.NOT_OBSERVED,
        'receipt': None,
        'reason_codes': [],
    }


@pytest.fixture
def unavailable_body(selection):
    return {
        'schema': contract.STATUS_RESULT_SCHEMA,
        'selection': dict(selection),
        'state': contract.UNAVAILABLE,
        'receipt': None,
        'reason_codes': ['SOURCE_UNAVAILABLE'],
    }


# --------------------------------------------------------------------------- constants


def test_exported_constants_are_exact():
    assert contract.MAX_REQUEST_BYTES == 16384
    assert contract.MAX_RESPONSE_BYTES == 32768
    assert contract.ACTION_FRAME_SCHEMA == (
        'mastermind.workspace_project_admission_action.v1'
    )
    assert contract.OPERATION == 'pause_workstream_admission'
    assert contract.STATUS_FRAME_SCHEMA == (
        'mastermind.workspace_project_admission_status.v1'
    )
    assert contract.STATUS_OPERATION == 'read_pause_command'
    assert contract.ACTION_RESULT_SCHEMA == (
        'mastermind.workspace_project_admission_action_result.v1'
    )
    assert contract.STATUS_RESULT_SCHEMA == (
        'mastermind.workspace_project_admission_status_result.v1'
    )
    assert contract.ADMISSION_RECEIPT_SCHEMA == (
        'mastermind.workstream_admission_suspension_receipt.v1'
    )
    assert contract.READ_PRINCIPAL_RESOURCE == (
        'https://mcp.mastermind-x.com/workspace/read'
    )
    assert contract.READ_PRINCIPAL_SCOPES == ['mastermind.workspace.read']


def test_reason_code_sets():
    assert contract.NOT_DISPATCHED_REASON_CODES == (
        'INVALID_INPUT',
        'ACCESS_DENIED',
        'SOURCE_UNAVAILABLE',
        'SOURCE_CHANGED',
        'ROOT_MISMATCH',
        'OWNER_NOT_READY',
    )
    assert contract.EFFECT_UNKNOWN_REASON_CODES == ('OWNER_OUTCOME_UNCONFIRMED',)
    assert contract.UNAVAILABLE_REASON_CODES == contract.NOT_DISPATCHED_REASON_CODES


# --------------------------------------------------------------------------- frames


def test_valid_action_frame_roundtrip_detached(
    action_frame, selection, principal, admission_expires_at
):
    result = contract.validate_frame(action_frame)
    assert result == {
        'schema': contract.ACTION_FRAME_SCHEMA,
        'operation': contract.OPERATION,
        'selection': selection,
        'principal': principal,
        'admission_expires_at': admission_expires_at,
    }
    assert result is not action_frame
    assert result['selection'] is not action_frame['selection']
    result['selection']['work_ref'] = 'WS:MUTATED'
    assert action_frame['selection']['work_ref'] == 'WS:ACQ'


def test_valid_status_frame_roundtrip(status_frame, selection):
    result = contract.validate_frame(status_frame, status=True)
    assert result['selection'] == selection
    assert result['operation'] == contract.STATUS_OPERATION


def test_frame_mode_is_exact(action_frame, status_frame):
    assert_invalid(lambda: contract.validate_frame(action_frame, status=True))
    assert_invalid(lambda: contract.validate_frame(status_frame, status=False))


@pytest.mark.parametrize(
    'schema,operation',
    [
        ('mastermind.workspace_project_admission_status.v1', 'pause_workstream_admission'),
        ('mastermind.workspace_project_admission_action.v1', 'read_pause_command'),
        ('mastermind.workspace_project_admission_action.v2', 'pause_workstream_admission'),
        ('other.schema.v1', 'other.operation'),
    ],
)
def test_frame_rejects_cross_schema_variants(action_frame, schema, operation):
    mixed = dict(action_frame)
    mixed['schema'] = schema
    mixed['operation'] = operation
    assert_invalid(lambda: contract.validate_frame(mixed))


def test_frame_rejects_unknown_keys(action_frame):
    extra = dict(action_frame)
    extra['account'] = 'acct-1'
    assert_invalid(lambda: contract.validate_frame(extra))
    for key in ('schema', 'operation', 'selection', 'principal', 'admission_expires_at'):
        missing = dict(action_frame)
        del missing[key]
        assert_invalid(lambda m=missing: contract.validate_frame(m))
    for variant in (
        {'path': 'p', **{k: v for k, v in action_frame.items() if k != 'selection'}},
        {**{k: v for k, v in action_frame.items() if k != 'principal'}, 'account': action_frame['principal']},
        {**{k: v for k, v in action_frame.items() if k != 'operation'}, 'action': action_frame['operation']},
        {**{k: v for k, v in action_frame.items() if k != 'schema'}, 'frame': action_frame['schema']},
    ):
        assert_invalid(lambda v=variant: contract.validate_frame(v))


def test_frame_rejects_non_object():
    for bad in (None, 5, 'frame', [], True):
        assert_invalid(lambda b=bad: contract.validate_frame(b))


# --------------------------------------------------------------------------- selection


@pytest.mark.parametrize(
    'field,bad',
    [
        ('work_ref', 'WS:'),
        ('work_ref', 'ws:ACQ'),
        ('work_ref', 'WS:acq'),
        ('work_ref', 'WS:A'),
        ('work_ref', 'WS:AC Q'),
        ('work_ref', 'WS:' + 'A' + 'a' * 64),
        ('work_ref', 'JOB-42'),
        ('work_ref', ''),
        ('root_job_id', 'JOB-'),
        ('root_job_id', 'JOB-1234567890'),
        ('root_job_id', 'JOB-12a'),
        ('root_job_id', 'job-42'),
        ('root_job_id', 'WS:ACQ'),
        ('command_id', ''),
        ('command_id', '-cmd'),
        ('command_id', '.cmd'),
        ('command_id', 'cmd 1'),
        ('command_id', 'a' * 129),
    ],
)
def test_selection_rejects_foreign_identifiers(selection, field, bad):
    foreign = dict(selection)
    foreign[field] = bad
    assert_invalid(lambda: contract.selection(foreign))


@pytest.mark.parametrize(
    'field,good',
    [
        ('work_ref', 'WS:AB'),
        ('work_ref', 'WS:0-0'),
        ('work_ref', 'WS:' + 'A' * 64),
        ('root_job_id', 'JOB-0'),
        ('root_job_id', 'JOB-007'),
        ('root_job_id', 'JOB-123456789'),
        ('command_id', 'a'),
        ('command_id', 'a' * 128),
        ('command_id', 'a.b:c-d_e'),
        ('command_id', 'WS:ACQ'),
    ],
)
def test_selection_accepts_boundary_identifiers(selection, field, good):
    edge = dict(selection)
    edge[field] = good
    assert contract.selection(edge) == edge


def test_selection_rejects_shape(selection):
    extra = dict(selection)
    extra['actor'] = 'someone'
    assert_invalid(lambda: contract.selection(extra))
    for key in ('work_ref', 'command_id'):
        missing = dict(selection)
        del missing[key]
        assert_invalid(lambda: contract.selection(missing))
    rootless = {key: value for key, value in selection.items() if key != 'root_job_id'}
    assert contract.selection(rootless) == rootless
    for bad in (None, 5, 'WS:ACQ', [], True):
        assert_invalid(lambda b=bad: contract.selection(b))


def test_selection_is_detached(selection):
    result = contract.selection(selection)
    assert result is not selection
    result['work_ref'] = 'WS:OTHER'
    assert selection['work_ref'] == 'WS:ACQ'


# --------------------------------------------------------------------------- principal


@pytest.mark.parametrize(
    'field,bad',
    [
        ('issuer_digest', ''),
        ('issuer_digest', 'x' * 257),
        ('issuer_digest', 5),
        ('issuer_digest', None),
        ('subject_digest', ''),
        ('subject_digest', 'x' * 257),
        ('policy_id', ''),
        ('policy_id', 'x' * 257),
        ('client_ref', ''),
        ('client_ref', 'x' * 257),
    ],
)
def test_principal_rejects_bad_identity_fields(principal, field, bad):
    shaped = json.loads(json.dumps(principal))
    shaped[field] = bad
    assert_invalid(lambda: contract.validate_principal(shaped))


def test_principal_rejects_wrong_resource_and_scopes(principal):
    wrong_resource = json.loads(json.dumps(principal))
    wrong_resource['resource'] = 'https://other.example.com/acquisition'
    assert_invalid(lambda: contract.validate_principal(wrong_resource))

    for scopes in ([], ['other.scope'], ['mastermind.workspace.read', 'extra'],
                   'mastermind.workspace.read', ('mastermind.workspace.read',)):
        shaped = json.loads(json.dumps(principal))
        shaped['scopes'] = scopes
        assert_invalid(lambda s=shaped: contract.validate_principal(s))


def test_principal_rejects_key_variants(principal):
    extra = json.loads(json.dumps(principal))
    extra['actor'] = 'runtime-1'
    assert_invalid(lambda: contract.validate_principal(extra))
    for key in ('issuer_digest', 'subject_digest', 'policy_id', 'client_ref', 'resource', 'scopes'):
        missing = json.loads(json.dumps(principal))
        del missing[key]
        assert_invalid(lambda k=key: contract.validate_principal(missing))
    for bad in (None, 5, 'principal', []):
        assert_invalid(lambda b=bad: contract.validate_principal(b))


def test_principal_boundary_lengths_accepted(principal):
    edge = json.loads(json.dumps(principal))
    edge['issuer_digest'] = 'é' * 256
    edge['subject_digest'] = 'x' * 256
    assert contract.validate_principal(edge) == edge


# --------------------------------------------------------------------------- expiry


@pytest.mark.parametrize('bad', [0, -1, True, False, 1.5, '123', None, [], {}])
def test_frame_rejects_invalid_expiry(action_frame, bad):
    shaped = json.loads(json.dumps(action_frame))
    shaped['admission_expires_at'] = bad
    assert_invalid(lambda: contract.validate_frame(shaped))


def test_frame_accepts_positive_int_expiry(action_frame):
    shaped = json.loads(json.dumps(action_frame))
    shaped['admission_expires_at'] = 1
    assert contract.validate_frame(shaped)['admission_expires_at'] == 1


# --------------------------------------------------------------------------- receipt


def test_valid_receipt_matches_selection(receipt, selection):
    result = contract.validate_receipt(receipt, selection)
    assert result == receipt
    assert result is not receipt


def test_receipt_accepts_frame_or_body_as_expected(receipt, selection, action_frame, committed_body):
    assert contract.validate_receipt(receipt, action_frame) == receipt
    assert contract.validate_receipt(receipt, committed_body) == receipt
    assert contract.validate_receipt(receipt, contract.selection(selection)) == receipt


def test_receipt_rejects_foreign_selection(receipt, selection):
    foreign = dict(selection)
    foreign['work_ref'] = 'WS:OTHER'
    assert_invalid(lambda: contract.validate_receipt(receipt, foreign))
    foreign_command = dict(selection)
    foreign_command['command_id'] = 'other-cmd'
    assert_invalid(lambda: contract.validate_receipt(receipt, foreign_command))


def test_receipt_does_not_carry_root(receipt, selection):
    with_root = dict(receipt)
    with_root['root_job_id'] = selection['root_job_id']
    assert_invalid(lambda: contract.validate_receipt(with_root, selection))


@pytest.mark.parametrize(
    'field,bad',
    [
        ('schema', 'mastermind.workstream_admission_suspension_receipt.v2'),
        ('schema', 'mastermind.workspace_project_admission_action.v1'),
        ('state', 'RUNNING'),
        ('state', 'PAUSED '),
        ('state', 'paused'),
        ('event_id', 0),
        ('event_id', -1),
        ('event_id', True),
        ('event_id', False),
        ('event_id', 1.0),
        ('event_id', '17'),
        ('committed_at_ms', -1),
        ('committed_at_ms', True),
        ('committed_at_ms', 1.5),
        ('committed_at_ms', '1700000000000'),
        ('request_digest', 'A' * 64),
        ('request_digest', 'a' * 63),
        ('request_digest', 'a' * 65),
        ('request_digest', 'g' * 64),
        ('request_digest', 170),
        ('work_ref', 'WS:OTHER'),
        ('command_id', 'other-cmd'),
    ],
)
def test_receipt_rejects_bad_fields(receipt, selection, field, bad):
    shaped = json.loads(json.dumps(receipt))
    shaped[field] = bad
    assert_invalid(lambda: contract.validate_receipt(shaped, selection))


def test_receipt_rejects_shape(receipt, selection):
    extra = dict(receipt)
    extra['actor'] = 'runtime-1'
    assert_invalid(lambda: contract.validate_receipt(extra, selection))
    for key in ('schema', 'work_ref', 'state', 'event_id', 'command_id', 'request_digest', 'committed_at_ms'):
        missing = dict(receipt)
        del missing[key]
        assert_invalid(lambda k=key: contract.validate_receipt(missing, selection))
    for bad in (None, 5, 'receipt', []):
        assert_invalid(lambda b=bad: contract.validate_receipt(bad, selection))


def test_receipt_digest_is_format_checked_only(selection):
    """Any 64-lowercase-hex value validates; recomputation is owner-only."""
    for digest in ('0' * 64, 'f' * 64, '0123456789abcdef' * 4):
        shaped = {
            'schema': contract.ADMISSION_RECEIPT_SCHEMA,
            'work_ref': selection['work_ref'],
            'state': 'PAUSED',
            'event_id': 1,
            'command_id': selection['command_id'],
            'request_digest': digest,
            'committed_at_ms': 0,
        }
        assert contract.validate_receipt(shaped, selection)['request_digest'] == digest


# --------------------------------------------------------------------------- action results


def test_valid_action_result_all_dispositions(committed_body, not_dispatched_body, effect_unknown_body, selection):
    for body in (committed_body, not_dispatched_body, effect_unknown_body):
        result = contract.validate_action_result(body, selection)
        assert result == body
        assert result is not body


@pytest.mark.parametrize(
    'reason',
    [
        'INVALID_INPUT',
        'ACCESS_DENIED',
        'SOURCE_UNAVAILABLE',
        'SOURCE_CHANGED',
        'ROOT_MISMATCH',
        'OWNER_NOT_READY',
    ],
)
def test_not_dispatched_accepts_each_reason(selection, reason):
    body = {
        'schema': contract.ACTION_RESULT_SCHEMA,
        'selection': dict(selection),
        'disposition': contract.NOT_DISPATCHED,
        'receipt': None,
        'reason_codes': [reason],
    }
    assert contract.validate_action_result(body, selection) == body


@pytest.mark.parametrize(
    'mutate',
    [
        lambda b: {**b, 'disposition': 'NO_EFFECT'},
        lambda b: {**b, 'disposition': 'CANCELLED'},
        lambda b: {**b, 'disposition': 'COMMIT'},
        lambda b: {**b, 'disposition': 'committed'},
        lambda b: {**b, 'schema': 'mastermind.workspace_project_admission_status_result.v1'},
        lambda b: {**b, 'schema': 'mastermind.workspace_project_admission_action_result.v2'},
        lambda b: {**b, 'selection': {**b['selection'], 'work_ref': 'WS:OTHER'}},
        lambda b: {**b, 'selection': {**b['selection'], 'root_job_id': 'JOB-7'}},
        lambda b: {**b, 'receipt': {'schema': 'x'}},
        lambda b: {**b, 'extra': 1},
        lambda b: {**b, 'actor': 'runtime-1'},
    ],
)
def test_action_result_rejects_common_variants(
    committed_body, not_dispatched_body, effect_unknown_body, selection, mutate
):
    for base in (committed_body, not_dispatched_body, effect_unknown_body):
        shaped = json.loads(json.dumps(base))
        shaped = mutate(shaped)
        assert_invalid(lambda s=shaped: contract.validate_action_result(s, selection))


@pytest.mark.parametrize(
    'reasons',
    [
        [],
        ['ACCESS_DENIED', 'INVALID_INPUT'],
        ['NO_EFFECT'],
        ['access_denied'],
        ['OWNER_OUTCOME_UNCONFIRMED', 'ACCESS_DENIED'],
        'ACCESS_DENIED',
    ],
)
def test_no_receipt_dispositions_reject_bad_reason_lists(
    not_dispatched_body, effect_unknown_body, selection, reasons
):
    for base in (not_dispatched_body, effect_unknown_body):
        shaped = json.loads(json.dumps(base))
        shaped['reason_codes'] = reasons
        assert_invalid(lambda s=shaped: contract.validate_action_result(s, selection))


def test_committed_with_reasons_is_invalid(committed_body, selection):
    for reasons in (['INVALID_INPUT'], ['OWNER_OUTCOME_UNCONFIRMED'], ['ACCESS_DENIED', 'INVALID_INPUT']):
        shaped = json.loads(json.dumps(committed_body))
        shaped['reason_codes'] = reasons
        assert_invalid(lambda s=shaped: contract.validate_action_result(s, selection))


def test_committed_requires_valid_receipt(committed_body, selection, receipt):
    no_receipt = json.loads(json.dumps(committed_body))
    no_receipt['receipt'] = None
    assert_invalid(lambda: contract.validate_action_result(no_receipt, selection))

    bad_receipt = json.loads(json.dumps(committed_body))
    bad_receipt['receipt'] = dict(receipt)
    bad_receipt['receipt']['state'] = 'RUNNING'
    assert_invalid(lambda: contract.validate_action_result(bad_receipt, selection))

    with_reasons = json.loads(json.dumps(committed_body))
    with_reasons['reason_codes'] = ['INVALID_INPUT']
    assert_invalid(lambda: contract.validate_action_result(with_reasons, selection))


def test_effect_unknown_requires_exact_reason(selection, effect_unknown_body):
    empty = json.loads(json.dumps(effect_unknown_body))
    empty['reason_codes'] = []
    assert_invalid(lambda: contract.validate_action_result(empty, selection))
    doubled = json.loads(json.dumps(effect_unknown_body))
    doubled['reason_codes'] = ['OWNER_OUTCOME_UNCONFIRMED', 'OWNER_OUTCOME_UNCONFIRMED']
    assert_invalid(lambda: contract.validate_action_result(doubled, selection))


def test_action_result_rejects_foreign_expected_selection(committed_body, selection):
    foreign = dict(selection)
    foreign['command_id'] = 'other-cmd'
    assert_invalid(lambda: contract.validate_action_result(committed_body, foreign))
    foreign_root = dict(selection)
    foreign_root['root_job_id'] = 'JOB-999999999'
    assert_invalid(lambda: contract.validate_action_result(committed_body, foreign_root))


def test_action_result_rejects_bad_body(selection):
    for bad in (None, 5, 'body', [], True):
        assert_source_unavailable(lambda b=bad: contract.validate_action_result(b, selection))


def test_action_result_rejects_status_body(observed_body, not_observed_body, unavailable_body, selection):
    for body in (observed_body, not_observed_body, unavailable_body):
        assert_invalid(lambda b=body: contract.validate_action_result(b, selection))


# --------------------------------------------------------------------------- status results


def test_valid_status_result_all_states(observed_body, not_observed_body, unavailable_body, selection):
    for body in (observed_body, not_observed_body, unavailable_body):
        result = contract.validate_status_result(body, selection)
        assert result == body
        assert result is not body


@pytest.mark.parametrize(
    'mutate',
    [
        lambda b: {**b, 'state': 'PAUSED'},
        lambda b: {**b, 'state': 'OBSERVED '},
        lambda b: {**b, 'state': 'observed'},
        lambda b: {**b, 'schema': 'mastermind.workspace_project_admission_action_result.v1'},
        lambda b: {**b, 'schema': 'mastermind.workspace_project_admission_status_result.v2'},
        lambda b: {**b, 'selection': {**b['selection'], 'root_job_id': 'JOB-7'}},
        lambda b: {**b, 'receipt': {'schema': 'x'}},
        lambda b: {**b, 'reason_codes': ['ACCESS_DENIED']},
        lambda b: {**b, 'reason_codes': ['OWNER_OUTCOME_UNCONFIRMED']},
        lambda b: {**b, 'extra': 1},
        lambda b: {**b, 'actor': 'runtime-1'},
    ],
)
def test_status_result_rejects_variants(observed_body, not_observed_body, selection, mutate):
    for base in (observed_body, not_observed_body):
        shaped = json.loads(json.dumps(base))
        shaped = mutate(shaped)
        assert_invalid(lambda s=shaped: contract.validate_status_result(s, selection))


@pytest.mark.parametrize(
    'reasons',
    [
        [],
        ['NO_EFFECT'],
        ['OWNER_OUTCOME_UNCONFIRMED'],
        ['ACCESS_DENIED', 'INVALID_INPUT'],
        'ACCESS_DENIED',
    ],
)
def test_unavailable_rejects_bad_reason_lists(unavailable_body, selection, reasons):
    shaped = json.loads(json.dumps(unavailable_body))
    shaped['reason_codes'] = reasons
    assert_invalid(lambda s=shaped: contract.validate_status_result(s, selection))


@pytest.mark.parametrize(
    'reason',
    [
        'INVALID_INPUT',
        'ACCESS_DENIED',
        'SOURCE_UNAVAILABLE',
        'SOURCE_CHANGED',
        'ROOT_MISMATCH',
        'OWNER_NOT_READY',
    ],
)
def test_unavailable_accepts_each_reason(selection, reason):
    body = {
        'schema': contract.STATUS_RESULT_SCHEMA,
        'selection': dict(selection),
        'state': contract.UNAVAILABLE,
        'receipt': None,
        'reason_codes': [reason],
    }
    assert contract.validate_status_result(body, selection) == body


def test_status_result_pairing_rules(observed_body, not_observed_body, unavailable_body, selection, receipt):
    observed_no_receipt = json.loads(json.dumps(observed_body))
    observed_no_receipt['receipt'] = None
    assert_invalid(lambda: contract.validate_status_result(observed_no_receipt, selection))

    observed_reasons = json.loads(json.dumps(observed_body))
    observed_reasons['reason_codes'] = ['ACCESS_DENIED']
    assert_invalid(lambda: contract.validate_status_result(observed_reasons, selection))

    observed_bad_receipt = json.loads(json.dumps(observed_body))
    observed_bad_receipt['receipt'] = dict(receipt)
    observed_bad_receipt['receipt']['request_digest'] = 'z' * 64
    assert_invalid(lambda: contract.validate_status_result(observed_bad_receipt, selection))

    observed_with_receipt = json.loads(json.dumps(not_observed_body))
    observed_with_receipt['receipt'] = dict(receipt)
    assert_invalid(lambda: contract.validate_status_result(observed_with_receipt, selection))

    unavailable_with_receipt = json.loads(json.dumps(unavailable_body))
    unavailable_with_receipt['receipt'] = dict(receipt)
    assert_invalid(lambda: contract.validate_status_result(unavailable_with_receipt, selection))


def test_not_observed_records_absence_only(not_observed_body, selection):
    result = contract.validate_status_result(not_observed_body, selection)
    assert result['receipt'] is None
    assert result['reason_codes'] == []


def test_status_result_rejects_bad_body(selection):
    for bad in (None, 5, 'body', [], False):
        assert_source_unavailable(lambda b=bad: contract.validate_status_result(b, selection))


def test_status_result_rejects_action_body(committed_body, not_dispatched_body, selection):
    for body in (committed_body, not_dispatched_body):
        assert_invalid(lambda b=body: contract.validate_status_result(b, selection))


# --------------------------------------------------------------------------- canonicalization


def test_canonical_request_bytes_exact(action_frame):
    payload = contract.canonical_request_bytes(action_frame)
    assert payload == canonical(action_frame)
    assert payload.decode('utf-8') == json.dumps(
        action_frame, sort_keys=True, ensure_ascii=False, separators=(',', ':')
    )
    assert b', ' not in payload
    assert b': ' not in payload
    assert len(payload) <= contract.MAX_REQUEST_BYTES


def test_canonical_request_bytes_sorted_despite_insertion_order(action_frame):
    reordered = {
        'admission_expires_at': action_frame['admission_expires_at'],
        'principal': action_frame['principal'],
        'selection': action_frame['selection'],
        'operation': action_frame['operation'],
        'schema': action_frame['schema'],
    }
    assert contract.canonical_request_bytes(reordered) == canonical(action_frame)


def test_canonical_request_bytes_status_mode(status_frame):
    payload = contract.canonical_request_bytes(status_frame, status=True)
    assert payload == canonical(status_frame)


def test_canonical_request_bytes_rejects_invalid_frames(action_frame, status_frame):
    assert_invalid(lambda: contract.canonical_request_bytes(status_frame))
    assert_invalid(lambda: contract.canonical_request_bytes(action_frame, status=True))
    assert_invalid(lambda: contract.canonical_request_bytes(None))


def test_request_bound_counts_utf8_bytes(action_frame):
    shaped = json.loads(json.dumps(action_frame))
    shaped['principal']['issuer_digest'] = 'é' * 256
    payload = contract.canonical_request_bytes(shaped)
    assert 'é'.encode('utf-8') in payload
    assert len(payload) == len(json.dumps(shaped, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    assert len(payload.decode('utf-8')) < len(payload)


def test_request_bound_rejects_oversized_frame(action_frame, long_int_digits):
    """A valid-shaped frame whose canonical encoding exceeds 16384 bytes."""
    shaped = json.loads(json.dumps(action_frame))
    shaped['admission_expires_at'] = 10 ** 20000
    assert_invalid(lambda: contract.validate_frame(shaped))
    assert_invalid(lambda: contract.canonical_request_bytes(shaped))


def test_canonical_json_bytes_rejects_nan_and_foreign_types():
    assert_invalid(lambda: contract.canonical_json_bytes({'a': float('nan')}))
    assert_invalid(lambda: contract.canonical_json_bytes({'a': float('inf')}))
    assert_invalid(lambda: contract.canonical_json_bytes({'a': {1, 2}}))


def test_response_envelope_bytes_exact(committed_body, selection):
    payload = contract.response_envelope_bytes(committed_body, selection)
    expected = (
        json.dumps(
            {'ok': True, 'result': committed_body},
            sort_keys=True,
            ensure_ascii=False,
            separators=(',', ':'),
        )
        + '\n'
    ).encode('utf-8')
    assert payload == expected
    assert payload.endswith(b'\n')
    assert b'{"ok":true,"result":' in payload
    assert len(payload) <= contract.MAX_RESPONSE_BYTES


def test_response_envelope_bytes_status_mode(observed_body, selection):
    payload = contract.response_envelope_bytes(observed_body, selection, status=True)
    assert payload.endswith(b'\n')
    assert b'"result":{' in payload
    assert len(payload) <= contract.MAX_RESPONSE_BYTES


def test_response_envelope_rejects_oversized_body(committed_body, selection, long_int_digits):
    shaped = json.loads(json.dumps(committed_body))
    shaped['receipt']['event_id'] = 10 ** 40000
    assert_source_unavailable(lambda: contract.response_envelope_bytes(shaped, selection))


def test_response_envelope_accepts_large_valid_body(committed_body, selection, long_int_digits):
    shaped = json.loads(json.dumps(committed_body))
    shaped['receipt']['event_id'] = 10 ** 20000
    payload = contract.response_envelope_bytes(shaped, selection)
    assert payload.endswith(b'\n')
    assert len(payload) <= contract.MAX_RESPONSE_BYTES


def test_response_envelope_rejects_bad_body(selection):
    for bad in (None, 7, 'body', []):
        assert_source_unavailable(lambda b=bad: contract.response_envelope_bytes(b, selection))


def test_no_input_echo_in_errors(selection, action_frame):
    # A body that is not a JSON object is unusable: source_unavailable, no echo.
    for bad_body in (None, 7, 'caller-input', [1, 2], True):
        assert_source_unavailable(lambda b=bad_body: contract.validate_action_result(b, selection))
        assert_source_unavailable(lambda b=bad_body: contract.validate_status_result(b, selection))
    # A JSON object violating the shape is the caller's fault: invalid_input, no echo.
    for bad_object in ({'secret_marker': 'caller-input'}, {'schema': 'x'}, {'selection': 'x'}):
        assert_invalid(lambda b=bad_object: contract.validate_action_result(b, selection))
    with pytest.raises(ValueError) as invalid:
        contract.validate_frame({'secret_marker': 'caller-input'})
    assert str(invalid.value) == 'invalid_input'


# --------------------------------------------------------------------------- detachment


def test_action_result_is_detached(committed_body, selection):
    result = contract.validate_action_result(committed_body, selection)
    result['receipt']['event_id'] = 999
    result['reason_codes'].append('EXTRA')
    assert committed_body['receipt']['event_id'] != 999
    assert committed_body['reason_codes'] == []


def test_status_result_is_detached(observed_body, selection):
    result = contract.validate_status_result(observed_body, selection)
    result['selection']['work_ref'] = 'WS:MUTATED'
    assert observed_body['selection']['work_ref'] == 'WS:ACQ'


# --------------------------------------------------------------------------- no authority surface


def test_module_has_no_authority_surface():
    exported = set(contract.__all__)
    for forbidden in ('grant', 'clock', 'now', 'dispatch', 'store', 'controller', 'actor'):
        assert not any(forbidden in name for name in exported)
