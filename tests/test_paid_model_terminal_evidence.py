"""Focused synthetic-fixture tests for paid_model_terminal_evidence.

Pure standard library; no I/O, process, provider, network or lease effects.
Nothing here claims real runtime acceptance: these are unit fixtures only.
"""

import copy
import dataclasses
import hashlib
import json
import math
import unittest
from collections.abc import Mapping

from control_plane import paid_model_terminal_evidence as pmte
from control_plane.worker_execution_contract import PaidModelProcessRef, BinaryAttestation
from control_plane.paid_model_execution_contract import POLICY, paid_host_reference


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def owner_canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def std_digest(value):
    return hashlib.sha256(canon(value)).hexdigest()


JOB_ID = 'job-1'
ATTEMPT = 'attempt-1'
HOST = paid_host_reference('ubuntu1','mmx-ubuntu1')
WORKER = 'worker-1'
USER = 'runner'
PID = 4242
UID = 1000
STARTED = '2026-10-22T12:00:00+00:00'
ENDED = '2026-10-22T12:00:05+00:00'
NONCE = hashlib.sha256(b'nonce').hexdigest()
SRC = hashlib.sha256(b'source').hexdigest()
REQ = hashlib.sha256(b'request').hexdigest()
CAPS = hashlib.sha256(b'capsule').hexdigest()
BINSHA = hashlib.sha256(b'binary').hexdigest()
EMPTY = hashlib.sha256(b'').hexdigest()

GRANT = {
    'schema_version': pmte.SCHEMA_GRANT,
    'role': 'work',
    'policy_sha': 'a' * 64,
    'job_id': JOB_ID,
    'authorities': ['READ', 'RESEARCH'],
    'validation_argv': [],
    'write_paths': [],
}
GRANT_DIGEST = std_digest(GRANT)
BINDING = {
    'job_id': JOB_ID,
    'attempt_id': ATTEMPT,
    'root_id': 'root-1',
    'commission_sha256': 'b' * 64,
    'effective_grant_digest': GRANT_DIGEST,
}
ENVELOPE = {
    'role': 'worker',
    'attempt': ATTEMPT,
    'complete': True,
    'payload': {'answer': 42},
}
STDOUT_TEXT = json.dumps(ENVELOPE, sort_keys=True, separators=(',', ':'))
STDOUT_BYTES = len(STDOUT_TEXT.encode('utf-8'))
STDOUT_SHA = hashlib.sha256(STDOUT_TEXT.encode('utf-8')).hexdigest()
CONTRACT = {
    'schema': pmte.SCHEMA_CAPTURE_CONTRACT,
    'capture_limit_bytes': 262144,
    'stdout_encoding': 'utf-8',
    'stderr_encoding': 'utf-8',
    'require_complete': True,
    'require_cleanup': True,
}
IMAGE = {
    'parent_pid': 111,
    'pgid': PID,
    'session_id': PID,
    'effective_uid': UID,
    'real_uid': UID,
    'effective_gid': UID,
    'real_gid': UID,
    'start_identity': 'start-abc',
    'boot_id': 'boot-xyz',
    'sha256': BINSHA, 'device':1, 'inode':2, 'mode':0o755,
    'uid':0, 'gid':0, 'size':1000, 'mtime_ns':1, 'ctime_ns':1,
}
BINARY = {'path': '/usr/bin/python3', 'real_path': '/usr/bin/python3',
    'version': '3.11.0', 'sha256': BINSHA, 'team_identifier': None,
    'size': 1000, 'device': 1, 'inode': 2, 'mode': 0o755, 'uid': 0, 'gid': 0, 'mtime_ns': 1}
REF = PaidModelProcessRef(run_id=ATTEMPT, worker_id=WORKER, host_ref=HOST,
    pid=PID, pgid=PID, session_id=PID, process_start_identity='start-abc',
    boot_session_id='boot-xyz', launch_nonce=NONCE, started_at=STARTED,
    effective_uid=UID, effective_gid=UID, real_uid=UID, real_gid=UID,
    binary=BinaryAttestation(**BINARY),
    stdout_path='/srv/capture/'+ATTEMPT+'.paid/stdout',
    stderr_path='/srv/capture/'+ATTEMPT+'.paid/stderr',
    result_path='/srv/capture/'+ATTEMPT+'.paid/result')
Ref = PaidModelProcessRef
SOURCE = {'schema_version': 'mastermind.paid_worker_source/v1',
    'worker_id': WORKER, 'provider': 'glm', 'host_ref': HOST, 'model': 'glm-5.3',
    'worker_uid': UID, 'worker_gid': UID, 'worker_user': USER, 'binary': BINARY,
    'permission_profile_sha256': 'c'*64, 'execution_profile_digest': 'd'*64,
    'service_source_sha256': 'e'*64, 'bridge_uid': 501, 'socket_path': '/srv/control.sock',
    'capacity_capability_id': 'cap-1', 'capture_root': '/srv/capture',
    'qualification': {'registry_key':'ubuntu1','registry_sha256':'1'*64,'transport_alias':'mmx-ubuntu1',
        'host_env_path':'/srv/HOST_ENV.sh','host_env_sha256':'2'*64,'boot_id':'boot-xyz',
        'capture_identity':{'device':1,'inode':22,'mode':0o700,'uid':UID,'gid':UID},
        'qualifier_source_manifest_sha256':'3'*64,'probe_sha256':'4'*64,
        'qualifier_sources_sha256': dict.fromkeys(('host_pull.sh','host_pull_backend.py',
            'host_pull_probe.template','paid_host_qualification.py','remote_sub.sh'),'5'*64)}}
PHYSICAL = {key:value for key,value in SOURCE.items() if key != 'capacity_capability_id'}
PHYSICAL.update(schema_version='mastermind.paid_fabric_host_binding/v1',
                worker_source_config_digest=std_digest(SOURCE))
PHYSICAL_SHA = std_digest(PHYSICAL)
PAID_ROUTE = {'provider':'glm', 'host_ref': HOST, 'model':'glm-5.3', 'parent_job_id':'root-1'}
REQUEST = {'binding': BINDING, 'physical_binding_sha256': PHYSICAL_SHA,
    'paid_source_config': SOURCE, 'paid_physical_binding': PHYSICAL,
    'paid_account':'glm-account-1', 'paid_route':PAID_ROUTE,
    'launch_spec': {'run_id': ATTEMPT, 'job_id': JOB_ID, 'worker_id': WORKER,
                    'expected_worker_uid':UID,'expected_worker_gid':UID,'worker_user':USER}}
LAUNCH_IDENTITY = {'physical_binding_sha256': PHYSICAL_SHA, 'request': REQUEST}
ATTESTATION = {'schema_version': pmte.SCHEMA_ATTESTATION,
    'profile_id':'fabric.paid.glm.sealed-input.v1', 'adapter_id':'canonical-paid-fabric',
    'execution_surface':'glm-model-only', 'binding':BINDING, 'paid_route':PAID_ROUTE,
    'worker_id':WORKER, 'quota_class':'glm-paid-read',
    'process_identity': {key: IMAGE[key] for key in ('pgid','session_id',
        'start_identity','boot_id','effective_uid','effective_gid','real_uid','real_gid')}
        | {'pid': PID, 'observed_user': USER, 'launch_nonce':NONCE},
    'lease_binding': {'lease_id':'lease-9','orchestrator_id':'root-1','pool':'glm',
        'account':'glm-account-1','host_ref':HOST,'model':'glm-5.3',
        'controller_process':{'pid':111,'start_identity':'control-start','boot_id':'control-boot'},
        'runtime_fence_generation':1,'runtime_pin_version':1},
    'evidence':dict.fromkeys(('python_sha256','source_manifest_sha256','policy_sha256',
        'prompt_sha256','request_body_sha256','result_schema_sha256','capsule_binding_sha256',
        'physical_binding_sha256','pin_identity_sha256','capture_contract_sha256',
        'control_input_isolation_manifest_sha256'), 'f'*64)}
ATTESTATION['evidence'].update(python_sha256=BINSHA,source_manifest_sha256=SRC,
    request_body_sha256=REQ,capsule_binding_sha256=CAPS,
    physical_binding_sha256=PHYSICAL_SHA,pin_identity_sha256=std_digest(LAUNCH_IDENTITY),
    capture_contract_sha256=std_digest(CONTRACT), policy_sha256=std_digest(POLICY))

CLEANUP = {
    'census_proven': True,
    'identity_verified': True,
    'residual_count': 0,
    'status': 'terminated',
    'session_id': PID,
    'sweep_note': 'original diagnostic retained',
    'stdout_capture_complete': True, 'stderr_capture_complete': True, 'stdin_delivery_complete': True,
}


def build_evidence():
    owned_launch = {
        'schema': pmte.SCHEMA_OWNED_LAUNCH,
        'run_id': ATTEMPT,
        'model': 'glm-5.3',
        'transport_host': 'ubuntu1',
        'lease_id': 'lease-9',
        'pid': PID,
        'process_identity': dict(IMAGE),
        'observed_user': USER,
        'launch_nonce': NONCE,
        'started_at': STARTED,
        'python_path': '/usr/bin/python3',
        'python_version': '3.11.0',
        'source_manifest_sha256': SRC,
        'request_body_sha256': REQ,
        'capsule_binding_sha256': CAPS,
        'capture_contract': dict(CONTRACT),
        'capture_paths': {key: REF.to_dict()[key] for key in ('stdout_path','stderr_path','result_path')},
        'host_context': {key:copy.deepcopy(SOURCE['qualification'][key]) for key in ('host_env_path','host_env_sha256','boot_id','capture_identity')},
    }
    receipt = {
        'schema': pmte.SCHEMA_PROCESS_RECEIPT,
        'label': ATTEMPT,
        'pid': PID,
        'pgid': PID,
        'started_at': STARTED,
        'ended_at': ENDED,
        'returncode': 0,
        'timed_out': False,
        'nice_requested': None,
        'nice_applied': 0,
        'stdout_bytes': STDOUT_BYTES,
        'stdout_sha256': STDOUT_SHA,
        'stderr_bytes': 0,
        'stderr_sha256': EMPTY,
        'stdout_truncated': False,
        'stderr_truncated': False,
        'runtime_failure_code': None,
        'cleanup': copy.deepcopy(CLEANUP),
    }
    owned_terminal = {
        'schema': pmte.SCHEMA_OWNED_TERMINAL,
        'run_id': ATTEMPT,
        'launch_sha256': hashlib.sha256(owner_canon(owned_launch)).hexdigest(),
        'terminal': receipt,
    }
    capture = {
        'schema_version': pmte.SCHEMA_CAPTURE,
        'stdout_utf8': STDOUT_TEXT,
        'stdout_sha256': STDOUT_SHA,
        'stdout_bytes': STDOUT_BYTES,
        'stderr_sha256': EMPTY,
        'stderr_bytes': 0,
    }
    result = {
        'job_id': JOB_ID,
        'run_id': ATTEMPT,
        'worker_id': WORKER,
        'status': 'SUCCEEDED',
        'structured_output': copy.deepcopy(ENVELOPE),
        'artifact_manifest': [],
        'git_manifest': {},
        'usage': {'input_tokens': 11, 'output_tokens': 3},
        'provider_session_id': None,
        'exit_code': 0,
        'started_at': STARTED,
        'finished_at': ENDED,
        'error': None,
    }
    collection = {
        'process_ref': REF.to_dict(),
        'result': result,
        'stdout_sha256': STDOUT_SHA,
        'stderr_sha256': EMPTY,
        'result_sha256': STDOUT_SHA,
    }
    collection_receipt = {
        'schema_version': pmte.SCHEMA_COLLECTION,
        'collection': collection,
        'fabric_cleanup': copy.deepcopy(CLEANUP),
        'effective_grant_digest': GRANT_DIGEST,
    }
    validation_receipts = {
        'attempt_id': ATTEMPT,
        'job_id': JOB_ID,
        'commands': list(GRANT['validation_argv']),
        'effective_grant_digest': GRANT_DIGEST,
    }
    identity = {'path': '/srv/run/' + ATTEMPT, 'device': 64512,
                'inode': 999, 'mode': 0o755, 'uid': UID, 'gid': UID,
                'mtime_ns': 1000}
    sealed = dict(identity, mode=0o700, mtime_ns=2000)
    seal = {
        'schema_version': pmte.SCHEMA_SEAL,
        'sealed_at': '2026-10-22T12:00:06+00:00',
        'control_uid': UID,
        'paths': {
            'run': {'before': dict(identity), 'after': dict(sealed),
                    'worker_traversal_revoked': True},
            'workspace': {'before': dict(identity), 'after': dict(sealed),
                          'worker_traversal_revoked': True},
        },
        'passed': True,
    }
    seal['paths']['workspace']['before']['path'] = '/srv/local-workspace'
    seal['paths']['workspace']['after']['path'] = '/srv/local-workspace'
    seal = {'schema_version': pmte.SCHEMA_CONTROL_RETENTION, 'attempt_id': ATTEMPT,
        'job_id': JOB_ID, 'effective_grant_digest': GRANT_DIGEST, 'control_seal': seal}
    launch_identity = copy.deepcopy(LAUNCH_IDENTITY)
    return {
        'schema_version': pmte.SCHEMA_SEALED_EVIDENCE,
        'launch_identity': launch_identity,
        'owned_launch': owned_launch,
        'owned_terminal': owned_terminal,
        'capture': capture,
        'collection_receipt': collection_receipt,
        'collection_receipt_digest': std_digest(collection_receipt),
        'validation_receipts': validation_receipts,
        'validation_receipts_digest': std_digest(validation_receipts),
        'assignment_seal_receipt': seal,
        'assignment_seal_receipt_digest': std_digest(seal),
    }


def kwargs():
    return {
        'expected_binding': copy.deepcopy(BINDING),
        'expected_process_ref': REF,
        'expected_launch_attestation': copy.deepcopy(ATTESTATION),
        'expected_launch_identity_sha256': std_digest(LAUNCH_IDENTITY),
        'expected_result_envelope': copy.deepcopy(ENVELOPE),
        'expected_grant': copy.deepcopy(GRANT),
    }


def validate(mutated=None, **overrides):
    value = mutated if mutated is not None else build_evidence()
    options = kwargs()
    options.update(overrides)
    return pmte.validate_paid_model_terminal_evidence(value, **options)


class PaidModelTerminalEvidenceTests(unittest.TestCase):
    def assert_refused(self, mutator=None, **overrides):
        value = build_evidence()
        if mutator is not None:
            mutator(value)
        with self.assertRaises(pmte.PaidModelTerminalRefused) as caught:
            validate(mutated=value, **overrides)
        message = str(caught.exception)
        self.assertIsInstance(caught.exception, ValueError)
        self.assertNotIn(STDOUT_TEXT, message)
        return message

    def test_fixture_uses_actual_complete_paid_attestation_contract(self):
        from control_plane.paid_model_execution_principal import validate_paid_model_attestation
        result = validate_paid_model_attestation(ATTESTATION,
            expected_binding=BINDING, expected_route=PAID_ROUTE, expected_worker_id=WORKER,
            expected_quota_class='glm-paid-read', expected_process=ATTESTATION['process_identity'],
            expected_lease_binding=ATTESTATION['lease_binding'], expected_evidence=ATTESTATION['evidence'])
        self.assertEqual(result, ATTESTATION)

    def test_cycles_deep_nesting_and_hostile_keys_fail_without_echo(self):
        cycle = build_evidence()
        cycle['capture']['cycle'] = cycle
        with self.assertRaises(pmte.PaidModelTerminalRefused):
            validate(mutated=cycle)
        hostile = build_evidence()
        hostile['owned_terminal']['terminal']['cleanup']['SECRET_DO_NOT_ECHO'] = object()
        with self.assertRaises(pmte.PaidModelTerminalRefused) as caught:
            validate(mutated=hostile)
        self.assertNotIn('SECRET_DO_NOT_ECHO', str(caught.exception))

    def test_positive_roundtrip_returns_detached_exact_dict(self):
        value = build_evidence()
        result = validate(mutated=value)
        self.assertIs(type(result), dict)
        self.assertEqual(result, value)
        self.assertIsNot(result, value)
        self.assertIsNot(result['owned_terminal'],
                         value['owned_terminal'])
        value['owned_terminal']['terminal']['cleanup']['residual_count'] = 7
        value['capture']['stdout_utf8'] = 'mutated'
        value['collection_receipt']['collection']['result']['usage'][
            'input_tokens'] = 999
        self.assertEqual(
            result['owned_terminal']['terminal']['cleanup']['residual_count'],
            0)
        self.assertEqual(result['capture']['stdout_utf8'], STDOUT_TEXT)
        self.assertEqual(result['collection_receipt']['collection']['result'][
            'usage']['input_tokens'], 11)

    def test_positive_preserves_actual_cleanup_diagnostics_unchanged(self):
        result = validate()
        receipt = result['owned_terminal']['terminal']
        self.assertEqual(receipt['cleanup']['sweep_note'],
                         'original diagnostic retained')

    def test_positive_empty_stderr_chain(self):
        result = validate()
        self.assertEqual(result['capture']['stderr_sha256'], EMPTY)
        self.assertEqual(
            result['owned_terminal']['terminal']['stderr_sha256'], EMPTY)
        self.assertEqual(
            result['collection_receipt']['collection']['stderr_sha256'],
            EMPTY)

    def test_actual_owned_terminal_requires_complete_capture_delivery(self):
        for flag in ('stdout_capture_complete','stderr_capture_complete','stdin_delivery_complete'):
            self.assert_refused(lambda v: v['owned_terminal']['terminal']['cleanup'].update({flag:False}))
        self.assert_refused(lambda v: v['owned_terminal']['terminal'].update({'scheduler_slot':'invented'}))
        self.assert_refused(lambda v: v['owned_launch']['host_context'].update({'boot_id':'other-boot'}))

    def test_top_level_schema_and_keys_closed(self):
        self.assert_refused(
            lambda v: v.update({'extra': 1}))
        self.assert_refused(
            lambda v: v.pop('capture'))
        self.assert_refused(
            lambda v: v.update({'schema_version': 'other/v1'}))

    def test_launch_identity_digest_and_request(self):
        self.assert_refused(
            lambda v: v['launch_identity'].update({'owner_note': 'drift'}))
        self.assert_refused(
            lambda v: v['launch_identity'].pop('request'))
        self.assert_refused(
            expected_launch_identity_sha256='0' * 64)
        self.assert_refused(
            expected_launch_identity_sha256='not-a-digest')

    def test_attestation_binding_and_schema(self):
        self.assert_refused(
            expected_launch_attestation=dict(
                ATTESTATION, binding=dict(BINDING, job_id='job-2')))
        self.assert_refused(
            expected_launch_attestation=dict(
                ATTESTATION, schema_version='mastermind.other/v1'))
        self.assert_refused(
            expected_launch_attestation=dict(
                ATTESTATION, model='glm-5.3-flash'))

    def test_owned_launch_shape_and_fields(self):
        self.assert_refused(
            lambda v: v['owned_launch'].update({'extra_observed': 1}))
        self.assert_refused(
            lambda v: v['owned_launch'].pop('capsule_binding_sha256'))
        self.assert_refused(
            lambda v: v['owned_launch'].update({'schema': 'x/v1'}))
        self.assert_refused(
            lambda v: v['owned_launch'].update({'model': 'glm-5.3-flash'}))
        self.assert_refused(
            lambda v: v['owned_launch'].update({'transport_host': 'ubuntu2'}))
        self.assert_refused(
            lambda v: v['owned_launch'].update({'lease_id': 'lease-8'}))
        self.assert_refused(
            lambda v: v['owned_launch'].update({'observed_user': 'nobody'}))
        self.assert_refused(
            lambda v: v['owned_launch'].update({'launch_nonce': 'b' * 64}))
        self.assert_refused(
            lambda v: v['owned_launch'].update({'started_at':
                                                ENDED.replace('+00:00', '')}))
        self.assert_refused(
            lambda v: v['owned_launch'].update({'pid': True}))
        self.assert_refused(
            lambda v: v['owned_launch'].update({'pid': PID + 1}))
        self.assert_refused(
            lambda v: v['owned_launch'].update({'run_id': 'other-run'}))

    def test_process_identity_coordinates(self):
        self.assert_refused(
            lambda v: v['owned_launch']['process_identity'].pop('pgid'))
        self.assert_refused(
            lambda v: v['owned_launch']['process_identity'].update(
                {'pgid': PID + 1}))
        self.assert_refused(
            lambda v: v['owned_launch']['process_identity'].update(
                {'session_id': PID + 2}))
        self.assert_refused(
            lambda v: v['owned_launch']['process_identity'].update(
                {'effective_uid': UID + 1}))
        self.assert_refused(
            lambda v: v['owned_launch']['process_identity'].update(
                {'start_identity': 'start-other'}))
        self.assert_refused(
            lambda v: v['owned_launch']['process_identity'].update(
                {'sha256': 'c' * 64}))

    def test_capture_contract_flags(self):
        self.assert_refused(
            lambda v: v['owned_launch']['capture_contract'].update(
                {'require_complete': False}))
        self.assert_refused(
            lambda v: v['owned_launch']['capture_contract'].update(
                {'stderr_encoding': 'latin-1'}))
        self.assert_refused(
            lambda v: v['owned_launch']['capture_contract'].update(
                {'capture_limit_bytes': 4}))

    def test_owned_terminal_digest_and_receipt(self):
        self.assert_refused(
            lambda v: v['owned_terminal'].update(
                {'launch_sha256': 'd' * 64}))
        self.assert_refused(
            lambda v: v['owned_terminal'].update({'run_id': 'other-run'}))
        self.assert_refused(
            lambda v: v['owned_terminal'].pop('terminal'))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal'].update(
                {'schema': 'mastermind.legacy_receipt/v1'}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal'].update(
                {'label': 'not-the-attempt'}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal'].update({'pid': 5}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal'].update({'pgid': 6}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal'].update(
                {'returncode': 1}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal'].update(
                {'returncode': True}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal'].update(
                {'timed_out': True}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal'].update(
                {'stdout_truncated': True}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal'].update(
                {'stderr_truncated': True}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal'].update(
                {'runtime_failure_code': 'CAPTURE_LIMIT'}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal'].update(
                {'stderr_bytes': 3}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal'].update(
                {'stderr_sha256': STDOUT_SHA}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal'].update(
                {'stdout_bytes': STDOUT_BYTES + 1}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal'].pop('nice_applied'))

    def test_cleanup_receipt_is_proven_semantics(self):
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal']['cleanup'].update(
                {'census_proven': False}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal']['cleanup'].update(
                {'identity_verified': False}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal']['cleanup'].update(
                {'residual_count': False}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal']['cleanup'].update(
                {'residual_count': 2}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal']['cleanup'].update(
                {'status': 'residuals_remain'}))
        self.assert_refused(
            lambda v: v['owned_terminal']['terminal']['cleanup'].update(
                {'session_id': PID + 1}))

    def test_capture_byte_and_json_integrity(self):
        self.assert_refused(
            lambda v: v['capture'].update(
                {'stdout_utf8': STDOUT_TEXT + ' trailing'}))
        self.assert_refused(
            lambda v: v['capture'].update({'stdout_bytes': 3}))
        self.assert_refused(
            lambda v: v['capture'].update({'stdout_sha256': 'e' * 64}))
        self.assert_refused(
            lambda v: v['capture'].update({'stdout_utf8': 'x\x00y'}))
        self.assert_refused(
            lambda v: v['capture'].update({'stderr_bytes': 1}))
        self.assert_refused(
            lambda v: v['capture'].update({'stderr_sha256': STDOUT_SHA}))
        self.assert_refused(
            lambda v: v['capture'].pop('stderr_sha256'))
        self.assert_refused(
            expected_result_envelope=dict(ENVELOPE, complete=False))

    def test_duplicate_json_keys_and_oversize_refused(self):
        duplicate = '{"answer": 1, "answer": 2}'
        value = build_evidence()
        value['capture']['stdout_utf8'] = duplicate
        value['capture']['stdout_bytes'] = len(duplicate.encode('utf-8'))
        value['capture']['stdout_sha256'] = hashlib.sha256(
            duplicate.encode('utf-8')).hexdigest()
        with self.assertRaises(pmte.PaidModelTerminalRefused):
            validate(mutated=value)
        big = '{"payload": "' + 'a' * (pmte.MAX_STDOUT_BYTES + 32) + '"}'
        value = build_evidence()
        value['capture']['stdout_utf8'] = big
        value['capture']['stdout_bytes'] = len(big.encode('utf-8'))
        value['capture']['stdout_sha256'] = hashlib.sha256(
            big.encode('utf-8')).hexdigest()
        with self.assertRaises(pmte.PaidModelTerminalRefused):
            validate(mutated=value)

    def test_collection_receipt_exactness(self):
        self.assert_refused(
            lambda v: v['collection_receipt'].pop('fabric_cleanup'))
        self.assert_refused(
            lambda v: v['collection_receipt']['collection'].update(
                {'extra': 1}))
        self.assert_refused(
            lambda v: v['collection_receipt']['collection']['process_ref']
            .update({'pid': PID + 1}))
        self.assert_refused(
            lambda v: v['collection_receipt']['collection']['process_ref']
            .update({'worker_id': 'worker-2'}))
        self.assert_refused(
            lambda v: v['collection_receipt']['collection']['result'].update(
                {'provider_session_id': 'sess-1'}))
        self.assert_refused(
            lambda v: v['collection_receipt']['collection']['result'].update(
                {'artifact_manifest': [{'path': 'a'}]}))
        self.assert_refused(
            lambda v: v['collection_receipt']['collection']['result'].update(
                {'git_manifest': {'HEAD': 'x'}}))
        self.assert_refused(
            lambda v: v['collection_receipt']['collection']['result'].update(
                {'status': 'FAILED'}))
        self.assert_refused(
            lambda v: v['collection_receipt']['collection']['result'].update(
                {'exit_code': True}))
        self.assert_refused(
            lambda v: v['collection_receipt']['collection']['result'].update(
                {'error': 'boom'}))
        self.assert_refused(
            lambda v: v['collection_receipt']['collection']['result'].update(
                {'structured_output': dict(ENVELOPE, role='other')}))
        self.assert_refused(
            lambda v: v['collection_receipt']['collection']['result'].update(
                {'started_at': ENDED}))
        self.assert_refused(
            lambda v: v['collection_receipt']['collection']['result'].update(
                {'finished_at': ENDED.replace('+00:00', '')}))
        self.assert_refused(
            lambda v: v['collection_receipt']['collection'].update(
                {'result_sha256': 'f' * 64}))
        self.assert_refused(
            lambda v: v['collection_receipt'].update(
                {'fabric_cleanup': dict(CLEANUP, status='not_needed')}))
        self.assert_refused(
            lambda v: v['collection_receipt'].update(
                {'effective_grant_digest': '1' * 64}))

    def test_process_ref_custom_mapping_result_refused(self):
        value = build_evidence()
        ref_record = value['collection_receipt']['collection']['process_ref']

        class RefMap(Mapping):
            def __init__(self, inner):
                self._inner = inner

            def __getitem__(self, key):
                return self._inner[key]

            def __iter__(self):
                return iter(self._inner)

            def __len__(self):
                return len(self._inner)

        value['collection_receipt']['collection']['process_ref'] = \
            RefMap(ref_record)
        with self.assertRaises(pmte.PaidModelTerminalRefused):
            validate(mutated=value)

    def test_grant_authorities_and_digest(self):
        self.assert_refused(
            expected_grant=dict(GRANT, authorities=['READ', 'RUN_TESTS']))
        self.assert_refused(
            expected_grant=dict(GRANT, authorities=['RESEARCH']))
        self.assert_refused(
            expected_grant=dict(GRANT, authorities=[]))
        self.assert_refused(
            expected_grant=dict(GRANT, job_id='job-2'))
        self.assert_refused(
            expected_grant=dict(GRANT, schema_version='mastermind.other_grant/v1'))
        self.assert_refused(
            expected_grant=dict(GRANT, validation_argv='python3 -m pytest'))
        self.assert_refused(
            expected_binding=dict(BINDING,
                                  effective_grant_digest='2' * 64))

    def test_validation_receipts(self):
        self.assert_refused(
            lambda v: v['validation_receipts'].update(
                {'attempt_id': 'attempt-2'}))
        self.assert_refused(
            lambda v: v['validation_receipts'].update({'job_id': 'job-2'}))
        self.assert_refused(
            lambda v: v['validation_receipts'].update(
                {'commands': ['python3', '-c', 'print(1)']}))
        self.assert_refused(
            lambda v: v['validation_receipts'].update(
                {'effective_grant_digest': '3' * 64}))
        self.assert_refused(
            lambda v: v.update({'validation_receipts_digest': '4' * 64}))

    def test_assignment_seal(self):
        self.assert_refused(
            lambda v: v['assignment_seal_receipt']['control_seal'].update({'passed': False}))
        self.assert_refused(
            lambda v: v['assignment_seal_receipt'].update(
                {'attempt_id': 'attempt-9'}))
        self.assert_refused(
            lambda v: v['assignment_seal_receipt']['control_seal'].update(
                {'sealed_at': '2026-10-22T12:00:06'}))
        self.assert_refused(
            lambda v: v['assignment_seal_receipt']['control_seal'].update(
                {'control_uid': True}))
        self.assert_refused(
            lambda v: v['assignment_seal_receipt']['control_seal']['paths'].update(
                {'git_home': {'before': {}, 'after': {},
                              'worker_traversal_revoked': True}}))
        self.assert_refused(
            lambda v: v['assignment_seal_receipt']['control_seal']['paths']['run'].update(
                {'worker_traversal_revoked': False}))
        self.assert_refused(
            lambda v: v['assignment_seal_receipt']['control_seal']['paths']['workspace']
            ['after'].update({'mode': 0o755}))
        self.assert_refused(
            lambda v: v['assignment_seal_receipt']['control_seal']['paths']['run']
            ['after'].update({'uid': UID + 1}))
        self.assert_refused(
            lambda v: v['assignment_seal_receipt']['control_seal']['paths']['run']
            ['before'].update({'inode': 998}))
        self.assert_refused(
            lambda v: v['assignment_seal_receipt'].update(
                {'effective_grant_digest': '5' * 64}))

    def test_no_fabricated_uid_sweep_and_capture_namespace(self):
        self.assert_refused(lambda v: v['assignment_seal_receipt'].update(
            {'uid_sweep': {'schema':'mastermind.executive_uid_sweep/v2','passed':True}}))
        self.assert_refused(lambda v: v['assignment_seal_receipt']['control_seal'].update(
            {'uid_sweep': {'passed':True}}))
        for path in ('/srv/control/run/stdout', '/srv/capture/other.paid/stdout'):
            self.assert_refused(lambda v: v['owned_launch']['capture_paths'].update({'stdout_path':path}))

    def test_component_digests(self):
        self.assert_refused(
            lambda v: v.update({'collection_receipt_digest': '6' * 64}))
        self.assert_refused(
            lambda v: v.update(
                {'assignment_seal_receipt_digest': '7' * 64}))
        self.assert_refused(
            lambda v: v['collection_receipt']['collection']['result'].update(
                {'usage': {'input_tokens': 12, 'output_tokens': 3}}))

    def test_json_safety_and_types(self):
        nan_value = build_evidence()
        nan_value['collection_receipt']['collection']['result']['usage'][
            'input_tokens'] = float('nan')
        with self.assertRaises(pmte.PaidModelTerminalRefused):
            validate(mutated=nan_value)
        inf_value = build_evidence()
        inf_value['assignment_seal_receipt']['control_seal']['paths']['run']['before'][
            'mtime_ns'] = math.inf
        with self.assertRaises(pmte.PaidModelTerminalRefused):
            validate(mutated=inf_value)
        tuple_value = build_evidence()
        tuple_value['validation_receipts']['commands'] = ('python3',)
        with self.assertRaises(pmte.PaidModelTerminalRefused):
            validate(mutated=tuple_value)
        int_key = build_evidence()
        int_key['owned_terminal']['terminal']['cleanup'] = {
            1: 'x', 'census_proven': True, 'identity_verified': True,
            'residual_count': 0, 'status': 'terminated', 'session_id': PID}
        with self.assertRaises(pmte.PaidModelTerminalRefused):
            validate(mutated=int_key)

    def test_top_level_type_refused(self):
        for bad in (None, 7, 'evidence', [], ()):
            with self.assertRaises(pmte.PaidModelTerminalRefused):
                pmte.validate_paid_model_terminal_evidence(bad, **kwargs())

    def test_expected_process_ref_must_be_dataclass_value(self):
        with self.assertRaises(pmte.PaidModelTerminalRefused):
            validate(expected_process_ref=dataclasses.fields(REF))
        with self.assertRaises(pmte.PaidModelTerminalRefused):
            validate(expected_process_ref=Ref)


if __name__ == '__main__':
    unittest.main(verbosity=2)
