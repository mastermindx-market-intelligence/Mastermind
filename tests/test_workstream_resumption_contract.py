"""Tests for the closed workstream admission resumption contract math.

Pure stdlib, no I/O and no live effects: every case exercises the public
contract functions directly and asserts the single fixed validation error
``ValueError('WORKSTREAM_RESUMPTION_INVALID')`` for all bad input.
"""

import copy
import hashlib
import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from control_plane import workstream_resumption_contract as contract  # noqa: E402


REQUEST_SCHEMA = 'mastermind.workstream_admission_resumption.request.v1'
PAYLOAD_SCHEMA = 'mastermind.workstream_admission_resumption.v1'
PAUSE_RECEIPT_SCHEMA = 'mastermind.workstream_admission_suspension_receipt.v1'
RESUMPTION_RECEIPT_SCHEMA = 'mastermind.workstream_admission_resumption_receipt.v1'

WORK_REF = 'WS:RESUME01'
OTHER_WORK_REF = 'WS:RESUME02'
COMMAND_ID = 'cmd-resume-1'
OTHER_COMMAND_ID = 'cmd-resume-2'
ACTOR = 'actor.fabric:worker-1'
OTHER_ACTOR = 'actor.fabric:worker-2'
PAUSE_COMMAND_ID = 'cmd-pause-1'

PAUSE_EVENT_ID = 41
RESUME_EVENT_ID = 42
PAUSE_COMMITTED_AT_MS = 1000
RESUME_CREATED_AT_MS = 2000

DIGEST_A = 'a' * 64
DIGEST_B = 'b' * 64
DIGEST_C = 'c' * 64

EXPECTED_REQUEST_KEYS = {
    'schema', 'operation', 'work_ref', 'command_id', 'actor',
    'expected_pause_event_id', 'expected_pause_receipt_digest',
}
EXPECTED_PAUSE_RECEIPT_KEYS = {
    'schema', 'work_ref', 'state', 'event_id', 'command_id',
    'request_digest', 'committed_at_ms',
}
EXPECTED_PAYLOAD_KEYS = {
    'schema', 'state', 'work_ref', 'request_digest',
    'pause_event_id', 'pause_receipt_digest',
}
EXPECTED_EVENT_KEYS = {
    'event_id', 'aggregate_type', 'aggregate_id', 'event_type',
    'command_id', 'actor', 'payload_json', 'created_at_ms',
}
EXPECTED_RESUMPTION_RECEIPT_KEYS = {
    'schema', 'work_ref', 'state', 'event_id', 'command_id',
    'request_digest', 'committed_at_ms', 'pause_event_id',
    'pause_receipt_digest',
}


def canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        allow_nan=False,
    )


def sha256_canonical(value):
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def make_pause_receipt(event_id=PAUSE_EVENT_ID, work_ref=WORK_REF,
                       state='PAUSED', committed_at_ms=PAUSE_COMMITTED_AT_MS,
                       command_id=PAUSE_COMMAND_ID, request_digest=DIGEST_A):
    return {
        'schema': PAUSE_RECEIPT_SCHEMA,
        'work_ref': work_ref,
        'state': state,
        'event_id': event_id,
        'command_id': command_id,
        'request_digest': request_digest,
        'committed_at_ms': committed_at_ms,
    }


def pause_digest(receipt=None):
    if receipt is None:
        receipt = make_pause_receipt()
    return contract.pause_receipt_digest(receipt)


def make_request(work_ref=WORK_REF, command_id=COMMAND_ID, actor=ACTOR,
                 pause_event_id=PAUSE_EVENT_ID, pause_receipt_digest=None):
    if pause_receipt_digest is None:
        pause_receipt_digest = pause_digest()
    return contract.make_resume_request(
        work_ref, command_id, actor, pause_event_id, pause_receipt_digest)


def make_payload(**kwargs):
    return contract.make_resume_payload(make_request(**kwargs))


def make_event(payload, event_id=RESUME_EVENT_ID, work_ref=WORK_REF,
               command_id=COMMAND_ID, actor=ACTOR,
               created_at_ms=RESUME_CREATED_AT_MS,
               aggregate_type='workstream',
               event_type=contract.RESUMED_EVENT_TYPE):
    return {
        'event_id': event_id,
        'aggregate_type': aggregate_type,
        'aggregate_id': work_ref,
        'event_type': event_type,
        'command_id': command_id,
        'actor': actor,
        'payload_json': canonical_json(payload),
        'created_at_ms': created_at_ms,
    }


def valid_pair(work_ref=WORK_REF, pause_event_id=PAUSE_EVENT_ID,
               resume_event_id=RESUME_EVENT_ID,
               pause_committed_at_ms=PAUSE_COMMITTED_AT_MS,
               resume_created_at_ms=RESUME_CREATED_AT_MS):
    pause_receipt = make_pause_receipt(event_id=pause_event_id,
                                       work_ref=work_ref,
                                       committed_at_ms=pause_committed_at_ms)
    digest = contract.pause_receipt_digest(pause_receipt)
    request = make_request(work_ref=work_ref, pause_event_id=pause_event_id,
                           pause_receipt_digest=digest)
    payload = contract.make_resume_payload(request)
    event = make_event(payload, event_id=resume_event_id, work_ref=work_ref,
                       created_at_ms=resume_created_at_ms)
    return pause_receipt, request, payload, event


# Distinct sentinel so a deliberate None input is not mistaken for "omitted".
_UNSET = object()


class ResumptionContractTestCase(unittest.TestCase):

    def assertInvalid(self, func, *args, **kwargs):
        with self.assertRaises(ValueError) as caught:
            func(*args, **kwargs)
        self.assertEqual(str(caught.exception), contract.ERROR_MESSAGE)
        self.assertIs(type(caught.exception), ValueError)


class MakeResumeRequestTest(ResumptionContractTestCase):

    def test_valid_request_has_exact_fixed_shape(self):
        digest = pause_digest()
        request = make_request(pause_receipt_digest=digest)
        self.assertEqual(set(request), EXPECTED_REQUEST_KEYS)
        self.assertEqual(request, {
            'schema': REQUEST_SCHEMA,
            'operation': 'resume',
            'work_ref': WORK_REF,
            'command_id': COMMAND_ID,
            'actor': ACTOR,
            'expected_pause_event_id': PAUSE_EVENT_ID,
            'expected_pause_receipt_digest': digest,
        })
        self.assertIs(type(request['expected_pause_event_id']), int)

    def test_accepts_full_work_ref_and_identifier_ranges(self):
        longest_ref = 'WS:' + 'A' + 'b' * 63
        longest_identifier = 'a' + 'b' * 127
        request = contract.make_resume_request(
            longest_ref, longest_identifier, longest_identifier, 1, DIGEST_A)
        self.assertEqual(request['work_ref'], longest_ref)
        self.assertEqual(request['command_id'], longest_identifier)
        self.assertEqual(request['actor'], longest_identifier)

    def test_requests_are_detached_new_dicts(self):
        first = make_request()
        second = make_request()
        self.assertIsNot(first, second)
        self.assertEqual(first, second)
        first['work_ref'] = OTHER_WORK_REF
        first['expected_pause_event_id'] = 10 ** 9
        self.assertEqual(make_request()['work_ref'], WORK_REF)
        self.assertEqual(make_request()['expected_pause_event_id'],
                         PAUSE_EVENT_ID)

    def test_rejects_foreign_work_refs(self):
        bad_work_refs = [
            '',
            'WS:',
            'WS:A',
            'WS:A' * 2,
            'ws:RESUME01',
            'WS:resume01',
            'WS: RESUME01',
            'WS:RESUME01 ',
            'WS:RESUME01\n',
            '\nWS:RESUME01',
            'WS:RESUME01\n',
            'WS:RESU ME01',
            'WS:RESU#ME01',
            'WS:RESU/ME01',
            'WS:RESU:ME01',
            'WS:É X',
            'WS:' + 'A' + 'b' * 64,
            'WS:' + 'A' + 'b' * 100,
            'WORKSTREAM:RESUME01',
            None,
            7,
            7.0,
            b'WS:RESUME01',
            ('WS:RESUME01',),
        ]
        for work_ref in bad_work_refs:
            self.assertInvalid(contract.make_resume_request, work_ref,
                               COMMAND_ID, ACTOR, PAUSE_EVENT_ID, DIGEST_A)

    def test_rejects_foreign_command_and_actor(self):
        bad_identifiers = [
            '',
            '.dot',
            '_under',
            '-dash',
            ':colon',
            'has space',
            'has\nnewline',
            'has\ttab',
            'a' * 129,
            'a' * 1000,
            None,
            9,
            9.5,
            b'cmd-resume-1',
            ('cmd-resume-1',),
        ]
        for identifier in bad_identifiers:
            self.assertInvalid(contract.make_resume_request, WORK_REF,
                               identifier, ACTOR, PAUSE_EVENT_ID, DIGEST_A)
            self.assertInvalid(contract.make_resume_request, WORK_REF,
                               COMMAND_ID, identifier, PAUSE_EVENT_ID, DIGEST_A)

    def test_rejects_non_integer_pause_event_ids(self):
        bad_event_ids = [
            0,
            -1,
            -PAUSE_EVENT_ID,
            True,
            False,
            str(PAUSE_EVENT_ID),
            PAUSE_EVENT_ID + 0.0,
            None,
            (PAUSE_EVENT_ID,),
        ]
        for event_id in bad_event_ids:
            self.assertInvalid(contract.make_resume_request, WORK_REF,
                               COMMAND_ID, ACTOR, event_id, DIGEST_A)

    def test_rejects_foreign_pause_receipt_digests(self):
        bad_digests = [
            '',
            'A' * 64,
            'a' * 63,
            'a' * 65,
            'a' * 32,
            'g' * 64,
            'a' * 63 + 'g',
            'a' * 64 + '\n',
            '-a' * 32,
            None,
            0,
            b'a' * 64,
        ]
        for digest in bad_digests:
            self.assertInvalid(contract.make_resume_request, WORK_REF,
                               COMMAND_ID, ACTOR, PAUSE_EVENT_ID, digest)


class RequestDigestTest(ResumptionContractTestCase):

    def test_digest_matches_manual_canonical_sha256(self):
        request = make_request()
        self.assertEqual(contract.request_digest(request),
                         sha256_canonical(request))

    def test_digest_is_independent_of_key_insertion_order(self):
        request = make_request()
        reordered = {
            'expected_pause_receipt_digest':
                request['expected_pause_receipt_digest'],
            'expected_pause_event_id': request['expected_pause_event_id'],
            'actor': request['actor'],
            'command_id': request['command_id'],
            'work_ref': request['work_ref'],
            'operation': request['operation'],
            'schema': request['schema'],
        }
        self.assertEqual(contract.request_digest(reordered),
                         contract.request_digest(request))

    def test_digest_binds_every_request_field(self):
        base = contract.request_digest(make_request())
        variants = [
            make_request(work_ref=OTHER_WORK_REF),
            make_request(command_id=OTHER_COMMAND_ID),
            make_request(actor=OTHER_ACTOR),
            make_request(pause_event_id=PAUSE_EVENT_ID + 1),
            make_request(pause_receipt_digest=DIGEST_B),
        ]
        for variant in variants:
            self.assertNotEqual(contract.request_digest(variant), base)

    def test_rejects_wrong_schema_operation_and_key_sets(self):
        request = make_request()
        for key in EXPECTED_REQUEST_KEYS:
            broken = dict(request)
            broken.pop(key)
            self.assertInvalid(contract.request_digest, broken)
        for schema in ('', 'nope', REQUEST_SCHEMA + '.x',
                       REQUEST_SCHEMA.upper(), None, 5):
            broken = dict(request)
            broken['schema'] = schema
            self.assertInvalid(contract.request_digest, broken)
        for operation in ('pause', 'resume ', 'RESUME', '', None, 5):
            broken = dict(request)
            broken['operation'] = operation
            self.assertInvalid(contract.request_digest, broken)
        extra = dict(request)
        extra['unexpected'] = 1
        self.assertInvalid(contract.request_digest, extra)

    def test_rejects_non_dict_and_malformed_requests(self):
        self.assertInvalid(contract.request_digest, None)
        self.assertInvalid(contract.request_digest, {})
        self.assertInvalid(contract.request_digest, {'schema': 'nope'})
        self.assertInvalid(contract.request_digest, [])
        self.assertInvalid(contract.request_digest, ())
        self.assertInvalid(contract.request_digest, 'request')
        self.assertInvalid(contract.request_digest, 5)
        bad_values = [
            ('work_ref', 'ws:RESUME01'),
            ('command_id', ''),
            ('actor', 'has space'),
            ('expected_pause_event_id', True),
            ('expected_pause_event_id', 0),
            ('expected_pause_receipt_digest', 'A' * 64),
            ('expected_pause_receipt_digest', 'a' * 63),
        ]
        for key, value in bad_values:
            broken = dict(make_request())
            broken[key] = value
            self.assertInvalid(contract.request_digest, broken)


class PauseReceiptDigestTest(ResumptionContractTestCase):

    def test_digest_matches_manual_canonical_sha256(self):
        receipt = make_pause_receipt()
        self.assertEqual(contract.pause_receipt_digest(receipt),
                         sha256_canonical(receipt))

    def test_digest_is_independent_of_key_insertion_order(self):
        receipt = make_pause_receipt()
        reordered = {
            'committed_at_ms': receipt['committed_at_ms'],
            'request_digest': receipt['request_digest'],
            'command_id': receipt['command_id'],
            'event_id': receipt['event_id'],
            'state': receipt['state'],
            'work_ref': receipt['work_ref'],
            'schema': receipt['schema'],
        }
        self.assertEqual(contract.pause_receipt_digest(reordered),
                         contract.pause_receipt_digest(receipt))

    def test_digest_binds_every_receipt_field(self):
        base = contract.pause_receipt_digest(make_pause_receipt())
        variants = [
            make_pause_receipt(event_id=PAUSE_EVENT_ID + 1),
            make_pause_receipt(work_ref=OTHER_WORK_REF),
            make_pause_receipt(command_id='cmd-pause-2'),
            make_pause_receipt(request_digest=DIGEST_B),
            make_pause_receipt(committed_at_ms=PAUSE_COMMITTED_AT_MS + 1),
        ]
        for variant in variants:
            self.assertNotEqual(contract.pause_receipt_digest(variant), base)

    def test_rejects_wrong_schema_state_and_key_sets(self):
        receipt = make_pause_receipt()
        for key in EXPECTED_PAUSE_RECEIPT_KEYS:
            broken = dict(receipt)
            broken.pop(key)
            self.assertInvalid(contract.pause_receipt_digest, broken)
        for schema in ('', 'nope', PAUSE_RECEIPT_SCHEMA + '.x', None, 5):
            broken = dict(receipt)
            broken['schema'] = schema
            self.assertInvalid(contract.pause_receipt_digest, broken)
        for state in ('RESUMED', 'paused', 'PAUSED ', 'PAUSED\n', '', None, 5):
            broken = dict(receipt)
            broken['state'] = state
            self.assertInvalid(contract.pause_receipt_digest, broken)
        extra = dict(receipt)
        extra['unexpected'] = 1
        self.assertInvalid(contract.pause_receipt_digest, extra)

    def test_rejects_non_dict_and_malformed_receipts(self):
        self.assertInvalid(contract.pause_receipt_digest, None)
        self.assertInvalid(contract.pause_receipt_digest, {})
        self.assertInvalid(contract.pause_receipt_digest, [])
        self.assertInvalid(contract.pause_receipt_digest, 'receipt')
        self.assertInvalid(contract.pause_receipt_digest, 5)
        bad_values = [
            ('work_ref', 'ws:RESUME01'),
            ('event_id', 0),
            ('event_id', -1),
            ('event_id', True),
            ('event_id', str(PAUSE_EVENT_ID)),
            ('event_id', PAUSE_EVENT_ID + 0.0),
            ('command_id', ''),
            ('command_id', 'has space'),
            ('request_digest', 'A' * 64),
            ('request_digest', 'a' * 65),
            ('committed_at_ms', -1),
            ('committed_at_ms', True),
            ('committed_at_ms', 1.5),
            ('committed_at_ms', str(PAUSE_COMMITTED_AT_MS)),
        ]
        for key, value in bad_values:
            broken = dict(make_pause_receipt())
            broken[key] = value
            self.assertInvalid(contract.pause_receipt_digest, broken)


class MakeResumePayloadTest(ResumptionContractTestCase):

    def test_payload_has_exact_fixed_shape(self):
        request = make_request(pause_event_id=7)
        payload = contract.make_resume_payload(request)
        self.assertEqual(set(payload), EXPECTED_PAYLOAD_KEYS)
        self.assertEqual(payload, {
            'schema': PAYLOAD_SCHEMA,
            'state': 'RESUMED',
            'work_ref': WORK_REF,
            'request_digest': contract.request_digest(request),
            'pause_event_id': 7,
            'pause_receipt_digest': request['expected_pause_receipt_digest'],
        })

    def test_payload_tracks_the_request_it_derives_from(self):
        other = make_payload(work_ref=OTHER_WORK_REF, pause_event_id=9,
                             pause_receipt_digest=DIGEST_B)
        self.assertEqual(other['work_ref'], OTHER_WORK_REF)
        self.assertEqual(other['pause_event_id'], 9)
        self.assertEqual(other['pause_receipt_digest'], DIGEST_B)

    def test_payloads_are_detached_new_dicts(self):
        request = make_request()
        first = contract.make_resume_payload(request)
        second = contract.make_resume_payload(request)
        self.assertIsNot(first, second)
        self.assertEqual(first, second)
        first['work_ref'] = OTHER_WORK_REF
        first['pause_event_id'] = 10 ** 9
        self.assertEqual(contract.make_resume_payload(request)['work_ref'],
                         WORK_REF)
        self.assertEqual(contract.make_resume_payload(request)['pause_event_id'],
                         PAUSE_EVENT_ID)

    def test_rejects_invalid_requests(self):
        self.assertInvalid(contract.make_resume_payload, None)
        self.assertInvalid(contract.make_resume_payload, {})
        self.assertInvalid(contract.make_resume_payload, [])
        self.assertInvalid(contract.make_resume_payload, 'request')
        broken = dict(make_request())
        broken.pop('actor')
        self.assertInvalid(contract.make_resume_payload, broken)
        broken = dict(make_request())
        broken['expected_pause_event_id'] = True
        self.assertInvalid(contract.make_resume_payload, broken)


class ParseResumptionEventValidTest(ResumptionContractTestCase):

    def test_valid_roundtrip_receipt_has_exact_fixed_shape(self):
        pause_receipt, request, payload, event = valid_pair()
        receipt = contract.parse_resumption_event(event, pause_receipt)
        self.assertEqual(set(receipt), EXPECTED_RESUMPTION_RECEIPT_KEYS)
        self.assertEqual(receipt, {
            'schema': RESUMPTION_RECEIPT_SCHEMA,
            'work_ref': WORK_REF,
            'state': 'RESUMED',
            'event_id': RESUME_EVENT_ID,
            'command_id': COMMAND_ID,
            'request_digest': contract.request_digest(request),
            'committed_at_ms': RESUME_CREATED_AT_MS,
            'pause_event_id': PAUSE_EVENT_ID,
            'pause_receipt_digest': contract.pause_receipt_digest(pause_receipt),
        })
        self.assertEqual(receipt['request_digest'], sha256_canonical(request))

    def test_accepts_non_default_work_event_and_clock_values(self):
        pause_receipt, request, payload, event = valid_pair(
            work_ref=OTHER_WORK_REF,
            pause_event_id=7,
            resume_event_id=8,
            pause_committed_at_ms=5,
            resume_created_at_ms=9,
        )
        receipt = contract.parse_resumption_event(event, pause_receipt)
        self.assertEqual(receipt['work_ref'], OTHER_WORK_REF)
        self.assertEqual(receipt['event_id'], 8)
        self.assertEqual(receipt['pause_event_id'], 7)
        self.assertEqual(receipt['committed_at_ms'], 9)

    def test_wall_clock_ordering_is_never_claimed(self):
        # Event ids are monotonic; the wall clock may move, so a resumption
        # event stamped before (or exactly at) the pause wall clock is valid.
        pause_receipt, request, payload, event = valid_pair(
            pause_committed_at_ms=10000, resume_created_at_ms=5)
        receipt = contract.parse_resumption_event(event, pause_receipt)
        self.assertEqual(receipt['committed_at_ms'], 5)
        pause_receipt, request, payload, event = valid_pair(
            pause_committed_at_ms=0, resume_created_at_ms=0)
        receipt = contract.parse_resumption_event(event, pause_receipt)
        self.assertEqual(receipt['committed_at_ms'], 0)

    def test_inputs_are_never_mutated_and_output_is_detached(self):
        pause_receipt, request, payload, event = valid_pair()
        frozen_receipt = copy.deepcopy(pause_receipt)
        frozen_event = copy.deepcopy(event)
        receipt = contract.parse_resumption_event(event, pause_receipt)
        frozen_result = copy.deepcopy(receipt)
        self.assertEqual(pause_receipt, frozen_receipt)
        self.assertEqual(event, frozen_event)
        receipt['event_id'] = 10 ** 9
        receipt['work_ref'] = OTHER_WORK_REF
        receipt['pause_receipt_digest'] = DIGEST_B
        again = contract.parse_resumption_event(event, pause_receipt)
        self.assertEqual(again, frozen_result)
        self.assertIsNot(again, event)
        self.assertIsNot(again, pause_receipt)


class ParseResumptionEventInvalidTest(ResumptionContractTestCase):

    def setUp(self):
        self.pause_receipt, self.request, self.payload, self.event = valid_pair()

    def parse(self, event=_UNSET, pause_receipt=_UNSET):
        return contract.parse_resumption_event(
            self.event if event is _UNSET else event,
            self.pause_receipt if pause_receipt is _UNSET else pause_receipt,
        )

    def test_rejects_wrong_event_key_sets(self):
        for key in ('event_id', 'aggregate_type', 'aggregate_id', 'event_type',
                    'command_id', 'actor', 'payload_json', 'created_at_ms'):
            broken = dict(self.event)
            broken.pop(key)
            self.assertInvalid(self.parse, broken)
        extra = dict(self.event)
        extra['unexpected'] = 1
        self.assertInvalid(self.parse, extra)

    def test_rejects_wrong_aggregate_and_event_types(self):
        for aggregate_type in ('workstream_admission', 'workstreams',
                               'WORKSTREAM', '', None, 5):
            broken = dict(self.event)
            broken['aggregate_type'] = aggregate_type
            self.assertInvalid(self.parse, broken)
        for event_type in ('WORKSTREAM_ADMISSION_PAUSED',
                           'workstream_admission_resumed',
                           'WORKSTREAM_ADMISSION_RESUMED ', '', None, 5):
            broken = dict(self.event)
            broken['event_type'] = event_type
            self.assertInvalid(self.parse, broken)

    def test_rejects_malformed_aggregate_id(self):
        for aggregate_id in ('', 'ws:RESUME01', 'WS:A', OTHER_WORK_REF,
                             'WS:RESUME01\n', None, 5, b'WS:RESUME01'):
            broken = dict(self.event)
            broken['aggregate_id'] = aggregate_id
            self.assertInvalid(self.parse, broken)

    def test_rejects_bad_event_id_and_timestamp_types(self):
        for event_id in (0, -1, True, False, str(RESUME_EVENT_ID),
                         RESUME_EVENT_ID + 0.0, None):
            broken = dict(self.event)
            broken['event_id'] = event_id
            self.assertInvalid(self.parse, broken)
        for created_at_ms in (-1, True, False, str(RESUME_CREATED_AT_MS),
                              RESUME_CREATED_AT_MS + 0.5, None):
            broken = dict(self.event)
            broken['created_at_ms'] = created_at_ms
            self.assertInvalid(self.parse, broken)

    def test_rejects_malformed_event_command_and_actor(self):
        for bad in ('', 'has space', 'has\nnewline', '.dot', 'a' * 129, None, 5):
            broken = dict(self.event)
            broken['command_id'] = bad
            self.assertInvalid(self.parse, broken)
            broken = dict(self.event)
            broken['actor'] = bad
            self.assertInvalid(self.parse, broken)

    def test_rejects_non_string_payload_json(self):
        for payload_json in (None, 5, 5.5, b'{}', ('{}',), {}, True):
            broken = dict(self.event)
            broken['payload_json'] = payload_json
            self.assertInvalid(self.parse, broken)

    def test_rejects_oversize_payload_json(self):
        oversize_blob = 'x' * (contract.PAYLOAD_JSON_MAX_BYTES + 1)
        broken = dict(self.event)
        broken['payload_json'] = oversize_blob
        self.assertInvalid(self.parse, broken)
        oversize_field = canonical_json(
            dict(self.payload, pad='x' * (contract.PAYLOAD_JSON_MAX_BYTES + 1)))
        broken = dict(self.event)
        broken['payload_json'] = oversize_field
        self.assertInvalid(self.parse, broken)

    def test_rejects_non_canonical_payload_json(self):
        insertion_ordered = json.dumps(self.payload, ensure_ascii=False,
                                       sort_keys=False, separators=(',', ':'))
        self.assertNotEqual(insertion_ordered,
                            canonical_json(self.payload))
        spaced = json.dumps(self.payload, ensure_ascii=False)
        escaped = canonical_json(self.payload).replace(
            '"schema"', '"\\u0073chema"', 1)
        for payload_json in (insertion_ordered, spaced, escaped):
            broken = dict(self.event)
            broken['payload_json'] = payload_json
            self.assertInvalid(self.parse, broken)

    def test_rejects_duplicate_keys_nan_and_unknown_payload_fields(self):
        duplicate = canonical_json(self.payload)[:-1] + ',"state":"RESUMED"}'
        nan_text = canonical_json(self.payload).replace(
            '"pause_event_id":%d' % PAUSE_EVENT_ID, '"pause_event_id":NaN')
        unknown = dict(self.payload)
        unknown['unexpected'] = 'x'
        unknown_payload_json = canonical_json(unknown)
        for payload_json in (duplicate, nan_text, unknown_payload_json):
            broken = dict(self.event)
            broken['payload_json'] = payload_json
            self.assertInvalid(self.parse, broken)

    def test_rejects_invalid_or_non_object_payload_json(self):
        for payload_json in ('', 'not json', '{', '[]', '5', 'null', '"x"',
                             'true', '{}'):
            broken = dict(self.event)
            broken['payload_json'] = payload_json
            self.assertInvalid(self.parse, broken)

    def test_rejects_payload_with_wrong_schema_state_or_field_formats(self):
        for schema in ('', 'nope', PAYLOAD_SCHEMA + '.x', None, 5):
            broken = dict(self.payload)
            broken['schema'] = schema
            self.assertInvalid(self.parse, make_event(broken))
        for state in ('PAUSED', 'resumed', 'RESUMED ', '', None, 5):
            broken = dict(self.payload)
            broken['state'] = state
            self.assertInvalid(self.parse, make_event(broken))
        for key, value in (
                ('work_ref', 'ws:RESUME01'),
                ('work_ref', OTHER_WORK_REF),
                ('request_digest', 'A' * 64),
                ('request_digest', 'a' * 63),
                ('pause_event_id', True),
                ('pause_event_id', 0),
                ('pause_receipt_digest', 'a' * 65),
                ('pause_receipt_digest', DIGEST_C)):
            broken = dict(self.payload)
            broken[key] = value
            self.assertInvalid(self.parse, make_event(broken))

    def test_rejects_foreign_work_refs(self):
        # aggregate_id no longer matches the payload work_ref
        broken = dict(self.event)
        broken['aggregate_id'] = OTHER_WORK_REF
        self.assertInvalid(self.parse, broken)
        # payload carries another work_ref than the aggregate/receipt
        broken_payload = dict(self.payload)
        broken_payload['work_ref'] = OTHER_WORK_REF
        broken_payload['request_digest'] = DIGEST_B
        self.assertInvalid(self.parse, make_event(broken_payload))
        # pause receipt belongs to another work than the aggregate/payload
        self.assertInvalid(self.parse,
                           pause_receipt=make_pause_receipt(
                               work_ref=OTHER_WORK_REF))

    def test_rejects_foreign_command_and_actor_in_event(self):
        broken = dict(self.event)
        broken['command_id'] = OTHER_COMMAND_ID
        self.assertInvalid(self.parse, broken)
        broken = dict(self.event)
        broken['actor'] = OTHER_ACTOR
        self.assertInvalid(self.parse, broken)

    def test_rejects_tampered_pause_tokens_in_payload(self):
        broken_payload = dict(self.payload)
        broken_payload['request_digest'] = DIGEST_B
        self.assertInvalid(self.parse, make_event(broken_payload))
        broken_payload = dict(self.payload)
        broken_payload['pause_event_id'] = PAUSE_EVENT_ID + 1
        self.assertInvalid(self.parse, make_event(broken_payload))
        broken_payload = dict(self.payload)
        broken_payload['pause_receipt_digest'] = DIGEST_C
        self.assertInvalid(self.parse, make_event(broken_payload))

    def test_rejects_resume_event_at_or_before_pause_event(self):
        self.assertInvalid(self.parse,
                           event=make_event(self.payload,
                                            event_id=PAUSE_EVENT_ID))
        self.assertInvalid(self.parse,
                           event=make_event(self.payload,
                                            event_id=PAUSE_EVENT_ID - 1))

    def test_rejects_invalid_pause_receipt(self):
        self.assertInvalid(self.parse, pause_receipt=None)
        self.assertInvalid(self.parse, pause_receipt={})
        self.assertInvalid(self.parse, pause_receipt=[])
        self.assertInvalid(self.parse, pause_receipt=5)
        for state in ('RESUMED', 'paused', '', None):
            self.assertInvalid(self.parse,
                               pause_receipt=make_pause_receipt(state=state))
        broken = dict(self.pause_receipt)
        broken.pop('committed_at_ms')
        self.assertInvalid(self.parse, pause_receipt=broken)
        broken = dict(self.pause_receipt)
        broken['event_id'] = True
        self.assertInvalid(self.parse, pause_receipt=broken)
        broken = dict(self.pause_receipt)
        broken['unexpected'] = 1
        self.assertInvalid(self.parse, pause_receipt=broken)

    def test_fixed_error_message_without_input_echo(self):
        with self.assertRaises(ValueError) as caught:
            self.parse(pause_receipt=make_pause_receipt(
                work_ref=OTHER_WORK_REF))
        message = str(caught.exception)
        self.assertEqual(message, 'WORKSTREAM_RESUMPTION_INVALID')
        self.assertNotIn(WORK_REF, message)
        self.assertNotIn(OTHER_WORK_REF, message)
        self.assertNotIn(COMMAND_ID, message)
        self.assertNotIn(ACTOR, message)

    def test_parse_matches_an_independently_built_valid_pair_after_rejecting(self):
        # Sanity guard: the fixture used by the rejection tests above is
        # itself valid, so every rejection comes from the injected defect.
        receipt = self.parse()
        self.assertEqual(receipt['event_id'], RESUME_EVENT_ID)
        self.assertEqual(receipt['pause_event_id'], PAUSE_EVENT_ID)


if __name__ == '__main__':
    unittest.main(verbosity=2)
