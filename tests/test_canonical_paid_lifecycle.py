#!/usr/bin/env python3
"""Offline mechanical tests for the canonical paid GLM bridge lifecycle.

Every fake, fixture and scripted payload in this file is a mechanical test
double and is explicitly NOT live authentication, NOT a real broker context,
NOT a real launchd/launchctl observation and NOT a real readiness, quiescence
or qualification producer. No test opens a socket, runs launchctl, signs in
to any provider, reads a credential, touches a launchd job or performs any
UID census. Substitutions are confined to this module's own explicitly
mechanical seams (the host seam, the parent helper seams and the pure
validators); production verdicts are never replaced.
"""
from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

from ops.executive_os import canonical_paid_lifecycle as mod


RELEASE = 'a' * 40
DEFINITION = 'd' * 64
MANIFEST = 'b' * 64
BOOT = 'C0FFEE12-3456-7890-ABCD-EF0123456789'
PAID_BOOT = 'D34DB33F-1111-2222-3333-444455556666'
FILES = frozenset({'profile.json', 'bridge.json', 'bindings.json',
                   mod.PAID_LABEL + '.plist'})
FAKE_IDENTITY = {
    'label': mod.PAID_LABEL, 'socket': mod.PAID_SOCKET_PATH,
    'definition': Path('/tmp/mechanical-fixture-only/fabric-glm-paid-01'),
    'plist': Path('/tmp/mechanical-fixture-only/fabric-glm-paid-01/'
                  + mod.PAID_LABEL + '.plist'),
    'files': FILES, 'bridge_uid': 501, 'python': mod.PYTHON,
}
SNAPSHOT = {
    'release_sha': RELEASE, 'manifest_sha256': MANIFEST,
    'definition_sha256': DEFINITION,
    'definition_hashes': {name: 'c' * 64 for name in sorted(FILES)},
    'profile': {'bridge_gid': 20, 'bridge_uid': 501},
    'bindings_rows': 0, 'control_sha256': '1' * 64, 'worker_sha256': '2' * 64,
    'python_image': '/fixture/pinned-python',
}


def readiness_payload(**over):
    payload = {
        'schema_version': mod.READINESS_SCHEMA, 'adapter_id': mod.ADAPTER_ID,
        'profile_id': mod.PROFILE_ID, 'execution_surface': mod.EXECUTION_SURFACE,
        'release_sha': RELEASE, 'manifest_sha256': MANIFEST,
        'definition_hashes': {name: 'c' * 64 for name in sorted(FILES)},
        'process': {'pid': 4242, 'effective_uid': 501, 'effective_gid': 20,
                    'real_uid': 501, 'real_gid': 20,
                    'start_identity': '100000/4242', 'boot_id': PAID_BOOT},
        'socket': {'path': mod.PAID_SOCKET_PATH, 'device': 1, 'inode': 2,
                   'uid': 0, 'gid': 450, 'mode': 0o660},
        'adopted': {'device': 1, 'inode': 2},
        'incumbent_context': mod.INCUMBENT_CONTEXT,
        'nonce': '0' * 32,
    }
    payload.update(over)
    return payload


def quiesce_receipt(**over):
    receipt = {
        'schema_version': mod.QUIESCENCE_SCHEMA,
        'stop_intent': {'request_id': 'req-1', 'request_sha256': 'e' * 64,
                        'release_sha': RELEASE,
                        'expected_definition_sha256': DEFINITION},
        'fence_id': 'f' * 64,
        'process': {'pid': 4242, 'effective_uid': 501, 'effective_gid': 20,
                    'real_uid': 501, 'real_gid': 20,
                    'start_identity': '100000/4242', 'boot_id': PAID_BOOT},
        'quiesced': True,
        'broker_process': {'pid': 999, 'pidversion': 7, 'euid': 0,
                           'audit_identity_digest': '1' * 64, 'boot_id': BOOT},
        'receipt_sha256': '2' * 64,
        'kernel_peer': {'euid': 501, 'pid': 4242, 'pidversion': 9,
                        'audit_identity_digest': '3' * 64, 'boot_id': PAID_BOOT},
    }
    receipt.update(over)
    return receipt


class FakeHost:
    """Mechanical host fixture: never a production verdict or live authority."""

    def __init__(self, *, state='absent', pid=None, override='default',
                   after_bootstrap='running', after_kickstart='running',
                   after_bootout='absent', recheck_fail_after=None,
                   readiness_payload=None, interval_error=None,
                   enable_fails=False, bootstrap_fails=False,
                   bootout_fails=False, disable_ignored=False):
        self.definition_sha = DEFINITION
        self.sha = None
        self.state = state
        self.pid = pid
        self.override_value = override
        self.after_bootstrap = after_bootstrap
        self.after_kickstart = after_kickstart
        self.after_bootout = after_bootout
        self.recheck_fail_after = recheck_fail_after
        self.readiness_payload = readiness_payload
        self.interval_error = interval_error
        self.enable_fails = enable_fails
        self.bootstrap_fails = bootstrap_fails
        self.bootout_fails = bootout_fails
        self.disable_ignored = disable_ignored
        self.snapshot = dict(SNAPSHOT)
        self.modifies = []
        self.idle_calls = 0
        self.pauses = 0
        self.recheck_calls = 0
        self.readiness_calls = 0
        self.registration_calls = 0
        self.interval_opened = 0

    @contextmanager
    def qualified_interval(self, sha):
        self.sha = sha
        self.interval_opened += 1
        if self.interval_error is not None:
            raise self.interval_error
        yield self.snapshot

    def recheck(self, snapshot):
        self.recheck_calls += 1
        if (self.recheck_fail_after is not None
                and self.recheck_calls >= self.recheck_fail_after):
            raise mod.PaidLifecycleError('protected_generation_changed')
        if snapshot != self.snapshot:
            raise mod.PaidLifecycleError('protected_generation_changed')

    def require_incumbent_absent(self):
        pass  # Mechanical fixture only, no real absence claim.

    def registration(self):
        self.registration_calls += 1
        if self.state == 'running':
            return dict(state='running', pid=self.pid)
        if self.state == 'registered':
            return dict(state='registered', pid=None)
        return dict(state='absent', pid=None)

    def override(self):
        return self.override_value

    def modify(self, verb):
        self.modifies.append(verb)
        if verb == 'enable':
            if self.enable_fails:
                raise mod.PaidLifecycleError('native_command_failed')
            self.override_value = 'enabled'
        elif verb == 'disable':
            if not self.disable_ignored:
                self.override_value = 'disabled'
        elif verb == 'bootstrap':
            if self.bootstrap_fails:
                raise mod.PaidLifecycleError('native_command_failed')
            self.state = self.after_bootstrap
        elif verb == 'kickstart':
            self.state = self.after_kickstart
        elif verb == 'bootout':
            if self.bootout_fails:
                raise mod.PaidLifecycleError('native_command_failed')
            self.state = self.after_bootout

    def require_idle(self, snapshot):
        self.idle_calls += 1

    def readiness(self, snapshot, registration):
        self.readiness_calls += 1
        if registration.get('state') != 'running':
            raise mod.PaidLifecycleError('registered_not_ready')
        if self.readiness_payload and self.readiness_payload != {'fixture': True}:
            return dict(self.readiness_payload)
        receipt = quiesce_receipt()
        return {'process': dict(receipt['process']),
                'kernel_peer': {key: value for key, value in receipt['kernel_peer'].items()
                                if key != 'boot_id'}}

    def pause(self):
        self.pauses += 1


class Recorder:
    """Records parent-helper seam calls; scripted replies only, no authority."""

    def __init__(self, *, acquire=None, revalidate=None, release=None,
                 error=None):
        self.calls = []
        self.acquire = acquire
        self.revalidate = revalidate
        self.release = release
        self.error = error

    def __call__(self, phase, release_sha, definition_sha, *, fence=None):
        self.calls.append((phase, release_sha, definition_sha, fence))
        if self.error is not None:
            raise self.error
        if phase == 'acquire':
            return self.acquire
        if phase == 'revalidate':
            return self.revalidate
        return self.release


class ArgumentClosureTests(unittest.TestCase):
    def test_run_lifecycle_rejects_unknown_action_and_types(self):
        for action in ('start-finite', 'START', None, 1, b'start', {'start'}):
            with self.assertRaises(mod.PaidLifecycleError) as caught:
                mod.run_lifecycle(FakeHost(), action, RELEASE)
            self.assertEqual(caught.exception.code, 'arguments_invalid')
            self.assertFalse(caught.exception.effect_unknown)

    def test_run_lifecycle_rejects_malformed_release(self):
        for sha in (None, 40, 'A' * 40, 'a' * 39, 'a' * 41, 'g' * 40):
            with self.assertRaises(mod.PaidLifecycleError) as caught:
                mod.run_lifecycle(FakeHost(), 'status', sha)
            self.assertEqual(caught.exception.code, 'arguments_invalid')

    def test_run_paid_lifecycle_rejects_closed_input_types(self):
        for action in (None, 7, 'deploy', frozenset({'start'})):
            with self.assertRaises(mod.PaidLifecycleError) as caught:
                mod.run_paid_lifecycle(action, RELEASE, DEFINITION)
            self.assertEqual(caught.exception.code, 'arguments_invalid')
        for sha in (None, 5, 'a' * 41, 'A' * 40):
            with self.assertRaises(mod.PaidLifecycleError):
                mod.run_paid_lifecycle('status', sha, DEFINITION)
        for sha in (None, 'd' * 63, 'D' * 64, 64):
            with self.assertRaises(mod.PaidLifecycleError):
                mod.run_paid_lifecycle('status', RELEASE, sha)

    @unittest.skipUnless(sys.platform != 'darwin', 'asserts the non-Darwin refusal')
    def test_run_paid_lifecycle_requires_darwin(self):
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod.run_paid_lifecycle('status', RELEASE, DEFINITION)
        self.assertEqual(caught.exception.code, 'darwin_required')

    @unittest.skipUnless(sys.platform == 'darwin', 'root/Darwin-only gate ordering')
    def test_run_paid_lifecycle_requires_root_before_any_effect(self):
        if os.geteuid() == 0:
            self.skipTest('running as root')
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod.run_paid_lifecycle('status', RELEASE, DEFINITION)
        self.assertEqual(caught.exception.code, 'root_privilege_required')

    def test_main_requires_fixed_installed_arguments(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = mod.main(['status', '--expected-sha', RELEASE,
                             '--expected-definition-sha256', DEFINITION])
        self.assertEqual(code, 65)
        reply = json.loads(buffer.getvalue())
        self.assertEqual(reply, {'status': 'REFUSED',
                                 'code': 'fixed_installed_arguments_required'})

    def test_main_rejects_probe_flag_confusion(self):
        for args in ([mod.PROBE_VERB, '--expected-sha', RELEASE, '--expected-x', MANIFEST],
                     ['start', '--expected-manifest-sha256', RELEASE, 'x', DEFINITION],
                     ['status', '--expected-sha', RELEASE, 'extra', DEFINITION, 'x']):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = mod.main(list(args))
            self.assertEqual(code, 65, args)


class DefinitionAggregateTests(unittest.TestCase):
    def test_aggregate_is_the_documented_canonical_encoding(self):
        hashes = {'bridge.json': '1' * 64, 'profile.json': '2' * 64,
                  'bindings.json': '3' * 64, mod.PAID_LABEL + '.plist': '4' * 64}
        import hashlib
        expected_raw = (json.dumps(
            {'bindings.json': '3' * 64, 'bridge.json': '1' * 64,
             'profile.json': '2' * 64, mod.PAID_LABEL + '.plist': '4' * 64},
            sort_keys=True, separators=(',', ':'), ensure_ascii=False,
            allow_nan=False)).encode('utf-8')
        self.assertEqual(mod.definition_aggregate(hashes),
                         hashlib.sha256(expected_raw).hexdigest())

    def test_aggregate_is_order_independent_and_sensitive(self):
        hashes = {name: 'c' * 64 for name in FILES}
        first = mod.definition_aggregate(hashes)
        self.assertEqual(first, mod.definition_aggregate(dict(reversed(list(hashes.items())))))
        changed = dict(hashes)
        changed['profile.json'] = '9' * 64
        self.assertNotEqual(first, mod.definition_aggregate(changed))

    def test_aggregate_refuses_non_digest_maps(self):
        for bad in ({}, {'profile.json': 'short'}, {1: 'c' * 64},
                    {'profile.json': 5}, [(['profile.json'], 'c' * 64)]):
            with self.assertRaises(mod.PaidLifecycleError):
                mod.definition_aggregate(bad)


class LaunchctlParsingTests(unittest.TestCase):
    def registration_text(self, *, label=mod.PAID_LABEL, pid='4242',
                          state='running', path=None):
        plist = str(FAKE_IDENTITY['plist']) if path is None else path
        lines = ['system/' + label + ' = {']
        lines.append('\tstate = ' + state)
        if pid is not None:
            lines.append('\tpid = ' + pid)
        lines.append('\tpath = ' + plist)
        lines.append('}')
        return '\n'.join(lines)

    def test_running_registration_is_parsed_with_exact_pid(self):
        parsed = mod.parse_registration(self.registration_text(),
                                        label=mod.PAID_LABEL,
                                        plist_path=FAKE_IDENTITY['plist'])
        self.assertEqual(parsed, {'state': 'running', 'pid': 4242})

    def test_registered_states_without_pid_are_unambiguous(self):
        for state in ('waiting', 'not running', 'spawn scheduled'):
            parsed = mod.parse_registration(
                self.registration_text(state=state, pid=None),
                label=mod.PAID_LABEL, plist_path=FAKE_IDENTITY['plist'])
            self.assertEqual(parsed, {'state': 'registered', 'pid': None})

    def test_running_without_pid_or_bad_pid_refuses(self):
        for text in (self.registration_text(pid=None),
                     self.registration_text(pid='0'),
                     self.registration_text(pid='-5'),
                     self.registration_text(pid='99999999999999')):
            with self.assertRaises(mod.PaidLifecycleError):
                mod.parse_registration(text, label=mod.PAID_LABEL,
                                       plist_path=FAKE_IDENTITY['plist'])

    def test_label_path_and_structure_mismatches_refuse(self):
        with self.assertRaises(mod.PaidLifecycleError):
            mod.parse_registration(self.registration_text(label='com.other.thing'),
                                   label=mod.PAID_LABEL,
                                   plist_path=FAKE_IDENTITY['plist'])
        with self.assertRaises(mod.PaidLifecycleError):
            mod.parse_registration(self.registration_text(path='/tmp/other.plist'),
                                   label=mod.PAID_LABEL,
                                   plist_path=FAKE_IDENTITY['plist'])
        with self.assertRaises(mod.PaidLifecycleError):
            mod.parse_registration('garbage', label=mod.PAID_LABEL,
                                   plist_path=FAKE_IDENTITY['plist'])
        with self.assertRaises(mod.PaidLifecycleError):
            mod.parse_registration(self.registration_text() + '\n\t}',
                                   label=mod.PAID_LABEL,
                                   plist_path=FAKE_IDENTITY['plist'])

    def test_duplicate_fields_and_unknown_states_refuse(self):
        doubled = self.registration_text().rsplit('}', 1)[0] + '\tpid = 4242\n}'
        with self.assertRaises(mod.PaidLifecycleError):
            mod.parse_registration(doubled, label=mod.PAID_LABEL,
                                   plist_path=FAKE_IDENTITY['plist'])
        with self.assertRaises(mod.PaidLifecycleError):
            mod.parse_registration(self.registration_text(state='weird', pid=None),
                                   label=mod.PAID_LABEL,
                                   plist_path=FAKE_IDENTITY['plist'])

    def test_override_states_map_to_closed_values(self):
        def text(row):
            return 'disabled services = {\n\t"%s" => %s\n}' % (mod.PAID_LABEL, row)
        self.assertEqual(mod.parse_override(text('disabled'), label=mod.PAID_LABEL), 'disabled')
        self.assertEqual(mod.parse_override(text('true'), label=mod.PAID_LABEL), 'disabled')
        self.assertEqual(mod.parse_override(text('enabled'), label=mod.PAID_LABEL), 'enabled')
        self.assertEqual(mod.parse_override('disabled services = {\n\t"com.other" => disabled\n}',
                                            label=mod.PAID_LABEL), 'default')

    def test_override_malformed_documents_refuse(self):
        for text in ('', 'disabled services = {}', 'other = {',
                     'disabled services = {\n\t"' + mod.PAID_LABEL + '" => maybe\n}',
                     'disabled services = {\n\t"' + mod.PAID_LABEL + '" => disabled\n\t"'
                     + mod.PAID_LABEL + '" => enabled\n}'):
            with self.assertRaises(mod.PaidLifecycleError):
                mod.parse_override(text, label=mod.PAID_LABEL)


class ReadinessPayloadTests(unittest.TestCase):
    def validate(self, payload, extra=frozenset({'nonce'})):
        return mod._validate_readiness_payload(payload, FAKE_IDENTITY, extra=extra)

    def test_valid_probe_payload_is_accepted(self):
        self.assertIsNone(self.validate(readiness_payload()))

    def test_valid_root_payload_admits_only_kernel_peer(self):
        host_reply = dict(readiness_payload(nonce=None))
        del host_reply['nonce']
        host_reply['kernel_peer'] = {'euid': 501, 'pid': 4242, 'pidversion': 9,
                                     'audit_identity_digest': '3' * 64}
        self.assertIsNone(self.validate(host_reply, extra=frozenset({'kernel_peer'})))
        with self.assertRaises(mod.PaidLifecycleError):
            self.validate(host_reply, extra=frozenset({'nonce'}))

    def test_identity_fields_are_pinned(self):
        for over in ({'schema_version': 'mastermind.other/v1'},
                     {'adapter_id': 'other-adapter'},
                     {'profile_id': 'other.profile'},
                     {'execution_surface': 'other-surface'},
                     {'incumbent_context': 'OTHER'}):
            with self.assertRaises(mod.PaidLifecycleError):
                self.validate(readiness_payload(**over))

    def test_payload_key_set_is_exact(self):
        payload = readiness_payload()
        del payload['adopted']
        with self.assertRaises(mod.PaidLifecycleError):
            self.validate(payload)
        with self.assertRaises(mod.PaidLifecycleError):
            self.validate(readiness_payload(extra_field=1))

    def test_release_manifest_and_definition_hashes_are_bounded(self):
        for over in ({'release_sha': 'z' * 40}, {'release_sha': 40},
                     {'manifest_sha256': 'b' * 63},
                     {'definition_hashes': {name: 'c' * 64 for name in sorted(FILES)}
                      | {'extra.json': 'c' * 64}},
                     {'definition_hashes': {name: 'short' for name in FILES}},
                     {'definition_hashes': 5}):
            with self.assertRaises(mod.PaidLifecycleError):
                self.validate(readiness_payload(**over))

    def test_process_fields_are_bounded_and_undecorated(self):
        good = readiness_payload()['process']
        for process in ({**good, 'pid': 0}, {**good, 'pid': 2 ** 31},
                        {**good, 'effective_uid': -1}, {**good, 'real_gid': None},
                        {**good, 'start_identity': 'darwin:100000/4242'},
                        {**good, 'start_identity': ''},
                        {**good, 'boot_id': 'not-a-boot-uuid'},
                        {key: value for key, value in good.items() if key != 'boot_id'}):
            with self.assertRaises(mod.PaidLifecycleError):
                self.validate(readiness_payload(process=process))

    def test_socket_and_adopted_shapes_are_pinned(self):
        for socket in ({**readiness_payload()['socket'], 'uid': 501},
                       {**readiness_payload()['socket'], 'gid': 0},
                       {**readiness_payload()['socket'], 'mode': 0o777},
                       {**readiness_payload()['socket'], 'path': '/tmp/other.sock'},
                       {key: value for key, value in
                        readiness_payload()['socket'].items() if key != 'inode'}):
            with self.assertRaises(mod.PaidLifecycleError):
                self.validate(readiness_payload(socket=socket))
        for adopted in ({'device': 1}, {'device': 1, 'inode': 0}, {**readiness_payload()['adopted'], 'inode': '2'}):
            with self.assertRaises(mod.PaidLifecycleError):
                self.validate(readiness_payload(adopted=adopted))


class QuiescenceReceiptTests(unittest.TestCase):
    def test_valid_receipt_is_accepted_and_returned(self):
        receipt = quiesce_receipt()
        self.assertIs(mod._validate_quiescence_receipt(receipt, RELEASE, DEFINITION),
                      receipt)

    def test_receipt_top_level_shape_is_exact(self):
        receipt = quiesce_receipt()
        del receipt['broker_process']
        with self.assertRaises(mod.PaidLifecycleError):
            mod._validate_quiescence_receipt(receipt, RELEASE, DEFINITION)
        with self.assertRaises(mod.PaidLifecycleError):
            mod._validate_quiescence_receipt(quiesce_receipt(surplus=1), RELEASE, DEFINITION)

    def test_receipt_identity_and_digests_are_bounded(self):
        for over in ({'schema_version': 'mastermind.other/v1'}, {'quiesced': False},
                     {'quiesced': 'true'}, {'fence_id': 'f' * 63},
                     {'fence_id': 'F' * 64}, {'receipt_sha256': None}):
            with self.assertRaises(mod.PaidLifecycleError):
                mod._validate_quiescence_receipt(quiesce_receipt(**over), RELEASE, DEFINITION)

    def test_stop_intent_must_match_this_request_exactly(self):
        for over in ({'stop_intent': {**quiesce_receipt()['stop_intent'],
                                      'release_sha': 'b' * 40}},
                     {'stop_intent': {**quiesce_receipt()['stop_intent'],
                                      'expected_definition_sha256': 'e' * 64}},
                     {'stop_intent': {**quiesce_receipt()['stop_intent'],
                                      'request_sha256': 'short'}},
                     {'stop_intent': {'request_id': 'req-1', 'request_sha256': 'e' * 64}},
                     {'stop_intent': 5}):
            with self.assertRaises(mod.PaidLifecycleError):
                mod._validate_quiescence_receipt(quiesce_receipt(**over), RELEASE, DEFINITION)

    def test_broker_and_peer_shapes_are_closed(self):
        broker = dict(quiesce_receipt()['broker_process'])
        for over in ({'broker_process': {**broker, 'euid': 501}},
                     {'broker_process': {**broker, 'pidversion': 0}},
                     {'broker_process': {**broker, 'audit_identity_digest': 'x' * 64}},
                     {'broker_process': {**broker, 'boot_id': 'nope'}}):
            with self.assertRaises(mod.PaidLifecycleError):
                mod._validate_quiescence_receipt(quiesce_receipt(**over), RELEASE, DEFINITION)
        peer = dict(quiesce_receipt()['kernel_peer'])
        for over in ({'kernel_peer': {**peer, 'euid': 0}},
                     {'kernel_peer': {**peer, 'euid': 470}},
                     {'kernel_peer': {**peer, 'pidversion': -1}},
                     {'kernel_peer': {key: value for key, value in peer.items()
                                      if key != 'boot_id'}}):
            with self.assertRaises(mod.PaidLifecycleError):
                mod._validate_quiescence_receipt(quiesce_receipt(**over), RELEASE, DEFINITION)

    def test_release_own_fence_requires_exact_confirmed_fence(self):
        calls = []
        def seam(phase, release_sha, definition_sha, *, fence=None):
            calls.append((phase, release_sha, definition_sha, fence))
            return quiesce_receipt()
        with mock.patch.object(mod, '_quiesce_paid_service', seam):
            self.assertTrue(mod._release_own_fence(quiesce_receipt(), RELEASE, DEFINITION))
        self.assertEqual(calls, [('release', RELEASE, DEFINITION, 'f' * 64)])

    def test_release_own_fence_refuses_foreign_or_failed_receipts(self):
        def foreign(phase, release_sha, definition_sha, *, fence=None):
            return quiesce_receipt(fence_id='9' * 64)
        def failing(phase, release_sha, definition_sha, *, fence=None):
            raise mod.PaidLifecycleError('parent_quiesce_helper_unavailable')
        with mock.patch.object(mod, '_quiesce_paid_service', foreign):
            self.assertFalse(mod._release_own_fence(quiesce_receipt(), RELEASE, DEFINITION))
        with mock.patch.object(mod, '_quiesce_paid_service', failing):
            self.assertFalse(mod._release_own_fence(quiesce_receipt(), RELEASE, DEFINITION))


class ParentHelperSeamTests(unittest.TestCase):
    def test_owner_gate_refuses_without_parent_implementation(self):
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod._require_paid_lifecycle_owner('start', RELEASE, DEFINITION)
        self.assertEqual(caught.exception.code, 'parent_owner_refused')

    def test_quiesce_seam_validates_phase_and_fence_before_import(self):
        for phase in ('acquire!', None, 5, 'Acquire', ''):
            with self.assertRaises(mod.PaidLifecycleError):
                mod._quiesce_paid_service(phase, RELEASE, DEFINITION)
        with self.assertRaises(mod.PaidLifecycleError):
            mod._quiesce_paid_service('acquire', RELEASE, DEFINITION, fence=7)
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod._quiesce_paid_service('acquire', RELEASE, DEFINITION)
        self.assertEqual(caught.exception.code, 'parent_quiesce_unconfirmed')
        self.assertTrue(caught.exception.effect_unknown)


class StatusTests(unittest.TestCase):
    def test_status_absent_reports_faithfully_with_no_effect(self):
        helper = Recorder(error=AssertionError('quiesce must never run for status'))
        host = FakeHost()
        with mock.patch.object(mod, '_quiesce_paid_service', helper):
            result = mod.run_lifecycle(host, 'status', RELEASE)
        self.assertEqual(result['state'], 'ABSENT')
        self.assertFalse(result['effect'])
        self.assertEqual(result['enabled_override'], 'default')
        self.assertFalse(result['bridge_armed'])
        self.assertFalse(result['capacity_admitted'])
        self.assertEqual(host.modifies, [])
        self.assertEqual(host.idle_calls, 1)
        self.assertEqual(helper.calls, [])

    @mock.patch.object(mod, 'observed_socket_state', return_value=(1, 2, 3, 0, 450, 1, 0, 0, 0))
    def test_status_absent_with_residual_socket_refuses(self, _patched):
        host = FakeHost()
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod.run_lifecycle(host, 'status', RELEASE)
        self.assertEqual(caught.exception.code, 'preflight:residual_socket_present')
        self.assertFalse(caught.exception.effect_unknown)
        self.assertEqual(host.modifies, [])

    def test_status_running_probes_readiness_read_only(self):
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True})
        result = mod.run_lifecycle(host, 'status', RELEASE)
        self.assertEqual(result['state'], 'READY')
        self.assertFalse(result['effect'])
        self.assertEqual(result['enabled_override'], 'enabled')
        self.assertEqual(host.modifies, [])
        self.assertEqual(host.readiness_calls, 1)

    def test_status_registered_state_refuses(self):
        host = FakeHost(state='registered', override='enabled')
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod.run_lifecycle(host, 'status', RELEASE)
        self.assertEqual(caught.exception.code, 'preflight:registered_not_ready')
        self.assertFalse(caught.exception.effect_unknown)
        self.assertEqual(host.modifies, [])

    def test_status_snapshot_change_refuses(self):
        host = FakeHost(recheck_fail_after=1)
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod.run_lifecycle(host, 'status', RELEASE)
        self.assertEqual(caught.exception.code, 'preflight:protected_generation_changed')

    def test_status_with_occupied_mutex_refuses(self):
        host = FakeHost(interval_error=mod.PaidLifecycleError('config_publication_mutex_occupied'))
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod.run_lifecycle(host, 'status', RELEASE)
        self.assertEqual(caught.exception.code, 'preflight:config_publication_mutex_occupied')


class StartTests(unittest.TestCase):
    def test_start_from_absent_default_reaches_running_disarmed(self):
        host = FakeHost(state='absent', after_bootstrap='running')
        result = mod.run_lifecycle(host, 'start', RELEASE)
        self.assertEqual(result['state'], 'RUNNING_DISARMED')
        self.assertTrue(result['effect'])
        self.assertTrue(result['service_started'])
        self.assertFalse(result['admitted'])
        self.assertFalse(result['armed'])
        self.assertEqual(result['enabled_override'], 'enabled')
        self.assertEqual(host.modifies, ['enable', 'bootstrap'])

    def test_start_kickstarts_only_registered_jobs(self):
        host = FakeHost(state='absent', after_bootstrap='registered',
                        after_kickstart='running')
        result = mod.run_lifecycle(host, 'start', RELEASE)
        self.assertEqual(result['state'], 'RUNNING_DISARMED')
        self.assertEqual(host.modifies, ['enable', 'bootstrap', 'kickstart'])

    def test_start_refuses_registered_or_running_jobs_without_retry(self):
        for state in ('registered', 'running'):
            host = FakeHost(state=state, override='enabled')
            with self.assertRaises(mod.PaidLifecycleError) as caught:
                mod.run_lifecycle(host, 'start', RELEASE)
            self.assertEqual(caught.exception.code,
                             'preflight:start_requires_unloaded_unregistered')
            self.assertFalse(caught.exception.effect_unknown)
            self.assertEqual(host.modifies, [])

    def test_start_refuses_enabled_absent_partial_state(self):
        host = FakeHost(state='absent', override='enabled')
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod.run_lifecycle(host, 'start', RELEASE)
        self.assertEqual(caught.exception.code, 'preflight:start_requires_unloaded_unenabled')
        self.assertEqual(host.modifies, [])

    @mock.patch.object(mod, 'observed_socket_state', return_value=(1, 2, 3, 0, 450, 1, 0, 0, 0))
    def test_start_refuses_when_socket_is_occupied(self, _patched):
        host = FakeHost(state='absent', override='default')
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod.run_lifecycle(host, 'start', RELEASE)
        self.assertEqual(caught.exception.code, 'preflight:start_socket_occupied')
        self.assertEqual(host.modifies, [])

    def test_start_refuses_changed_preimage_before_any_effect(self):
        host = FakeHost(state='absent', recheck_fail_after=1)
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod.run_lifecycle(host, 'start', RELEASE)
        self.assertEqual(caught.exception.code, 'preflight:protected_generation_changed')
        self.assertFalse(caught.exception.effect_unknown)
        self.assertEqual(host.modifies, [])

    def test_start_enable_unconfirmed_is_effect_unknown(self):
        host = FakeHost(state='absent', enable_fails=True)
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod.run_lifecycle(host, 'start', RELEASE)
        self.assertEqual(caught.exception.code, 'enable:native_command_failed')
        self.assertTrue(caught.exception.effect_unknown)

    def test_start_bootstrap_unconfirmed_is_effect_unknown(self):
        host = FakeHost(state='absent', after_bootstrap='absent')
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod.run_lifecycle(host, 'start', RELEASE)
        self.assertEqual(caught.exception.code, 'bootstrap:bootstrap_unconfirmed')
        self.assertTrue(caught.exception.effect_unknown)

    def test_start_registration_lost_is_effect_unknown(self):
        host = FakeHost(state='absent', after_bootstrap='registered',
                        after_kickstart='absent')
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod.run_lifecycle(host, 'start', RELEASE)
        self.assertEqual(caught.exception.code, 'readiness:startup_registration_lost')
        self.assertTrue(caught.exception.effect_unknown)

    def test_start_readiness_deadline_never_adopts_a_replacement(self):
        host = FakeHost(state='absent', after_bootstrap='registered',
                        after_kickstart='registered')
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod.run_lifecycle(host, 'start', RELEASE)
        self.assertEqual(caught.exception.code, 'readiness:readiness_deadline')
        self.assertTrue(caught.exception.effect_unknown)
        self.assertEqual(host.pauses, 30)

    def test_start_ready_generation_change_refuses(self):
        host = FakeHost(state='absent', after_bootstrap='running')
        original_recheck = host.recheck
        seen = {'count': 0}

        def flip_second_recheck(snapshot):
            seen['count'] += 1
            if seen['count'] >= 2:
                host.override_value = 'disabled'
            original_recheck(snapshot)

        host.recheck = flip_second_recheck
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod.run_lifecycle(host, 'start', RELEASE)
        self.assertEqual(caught.exception.code, 'readiness:ready_generation_changed')
        self.assertTrue(caught.exception.effect_unknown)


class StopTests(unittest.TestCase):
    @staticmethod
    def running_socket(host):
        """Fixture socket observation: present while the job is not absent."""
        return lambda: None if host.state == 'absent' else (1, 2, 3, 0, 450, 1, 0, 0, 0)

    def stop_with(self, host, helper):
        with mock.patch.object(mod, '_quiesce_paid_service', helper), \
                mock.patch.object(mod, 'observed_socket_state',
                                  side_effect=self.running_socket(host)):
            return mod.run_lifecycle(host, 'stop', RELEASE)

    def assert_refusal(self, context, code, unknown):
        self.assertEqual(context.exception.code, code)
        self.assertEqual(context.exception.effect_unknown, unknown)

    def test_stop_from_running_enabled_reaches_absent_with_fence_reported(self):
        receipt = quiesce_receipt()
        helper = Recorder(acquire=receipt, revalidate=receipt,
                          release=AssertionError('successful stop never releases'))
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True})
        result = self.stop_with(host, helper)
        self.assertEqual(result['state'], 'ABSENT')
        self.assertTrue(result['effect'])
        self.assertEqual(result['enabled_override'], 'disabled')
        self.assertEqual(result['quiescence_fence_id'], 'f' * 64)
        self.assertEqual(host.modifies, ['disable', 'bootout'])
        self.assertEqual([call[0] for call in helper.calls], ['acquire', 'revalidate'])
        self.assertEqual(helper.calls[0][3], None)
        self.assertEqual(helper.calls[1][3], 'f' * 64)

    def test_stop_refuses_without_enabled_running_original(self):
        for state, override in (('absent', 'default'), ('absent', 'enabled'),
                                ('registered', 'enabled'), ('running', 'disabled'),
                                ('running', 'default')):
            host = FakeHost(state=state, pid=4242, override=override)
            helper = Recorder(acquire=quiesce_receipt())
            with mock.patch.object(mod, '_quiesce_paid_service', helper):
                with self.assertRaises(mod.PaidLifecycleError) as caught:
                    mod.run_lifecycle(host, 'stop', RELEASE)
            self.assert_refusal(caught,
                                'preflight:stop_requires_enabled_running_original', False)
            self.assertEqual(host.modifies, [])
            self.assertEqual(helper.calls, [])

    def test_stop_denies_before_any_modify_when_quiesce_helper_is_unavailable(self):
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True})
        helper = Recorder(error=mod.PaidLifecycleError('parent_quiesce_helper_unavailable'))
        with mock.patch.object(mod, '_quiesce_paid_service', helper):
            with self.assertRaises(mod.PaidLifecycleError) as caught:
                mod.run_lifecycle(host, 'stop', RELEASE)
        self.assert_refusal(caught,
                            'quiesce_acquire:parent_quiesce_helper_unavailable', False)
        self.assertEqual(host.modifies, [])

    def test_stop_denies_on_transport_failure_before_any_fence_is_trusted(self):
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True})
        helper = Recorder(error=OSError('transport unavailable'))
        with mock.patch.object(mod, '_quiesce_paid_service', helper):
            with self.assertRaises(mod.PaidLifecycleError) as caught:
                mod.run_lifecycle(host, 'stop', RELEASE)
        self.assert_refusal(caught, 'quiesce_acquire:qualification_unavailable', True)
        self.assertEqual(host.modifies, [])

    def test_stop_retains_fence_on_ambiguous_or_malformed_acquire(self):
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True})
        helper = Recorder(acquire=quiesce_receipt(fence_id='short'))
        self.stop_raises(host, helper, 'quiesce_acquire:quiesce_receipt_identity_invalid',
                         True, phases=['acquire'], modifies=[])

    def stop_raises(self, host, helper, code, unknown, *, phases, modifies):
        with mock.patch.object(mod, '_quiesce_paid_service', helper), \
                mock.patch.object(mod, 'observed_socket_state',
                                  side_effect=self.running_socket(host)):
            with self.assertRaises(mod.PaidLifecycleError) as caught:
                mod.run_lifecycle(host, 'stop', RELEASE)
        self.assert_refusal(caught, code, unknown)
        self.assertEqual([call[0] for call in helper.calls], phases)
        self.assertEqual(host.modifies, modifies)

    def test_pre_launchctl_refusal_after_acquire_releases_only_own_fence(self):
        receipt = quiesce_receipt()
        helper = Recorder(acquire=receipt, revalidate=receipt, release=receipt)
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True}, recheck_fail_after=2)
        self.stop_raises(host, helper, 'quiesce_hold:protected_generation_changed',
                         False, phases=['acquire', 'release'], modifies=[])
        self.assertEqual(helper.calls[1][3], 'f' * 64)

    def test_failed_fence_release_after_acquire_is_effect_unknown_and_retained(self):
        receipt = quiesce_receipt()
        helper = Recorder(acquire=receipt,
                          release=mod.PaidLifecycleError('parent_quiesce_helper_unavailable'))
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True}, recheck_fail_after=2)
        self.stop_raises(host, helper, 'quiesce_hold:quiesce_fence_retained',
                         True, phases=['acquire', 'release'], modifies=[])

    def test_revalidate_generation_mismatch_refuses_and_never_boots_out(self):
        receipt = quiesce_receipt()
        helper = Recorder(acquire=receipt,
                          revalidate=quiesce_receipt(receipt_sha256='9' * 64))
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True})
        self.stop_raises(host, helper, 'revalidate:quiesce_generation_changed',
                         True, phases=['acquire', 'revalidate'], modifies=['disable'])

    def test_revalidate_fence_intent_broker_process_or_peer_drift_refuses(self):
        receipt = quiesce_receipt()
        for over in ({'fence_id': '9' * 64},
                     {'stop_intent': {**receipt['stop_intent'],
                                      'request_sha256': '9' * 64}},
                     {'broker_process': {**receipt['broker_process'], 'pid': 1000}},
                     {'kernel_peer': {**receipt['kernel_peer'], 'pidversion': 10}},
                     {'process': {**receipt['process'], 'boot_id': BOOT}}):
            helper = Recorder(acquire=receipt, revalidate=quiesce_receipt(**over))
            host = FakeHost(state='running', pid=4242, override='enabled',
                            readiness_payload={'fixture': True})
            self.stop_raises(host, helper, 'revalidate:quiesce_generation_changed',
                             True, phases=['acquire', 'revalidate'], modifies=['disable'])

    def test_stop_disable_unconfirmed_is_effect_unknown_without_bootout(self):
        receipt = quiesce_receipt()
        helper = Recorder(acquire=receipt, revalidate=receipt)
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True}, disable_ignored=True)
        self.stop_raises(host, helper, 'disable:disable_unconfirmed', True,
                         phases=['acquire'], modifies=['disable'])

    def test_stop_bootout_failure_is_unknown_and_never_auto_unquiesces(self):
        receipt = quiesce_receipt()
        helper = Recorder(acquire=receipt, revalidate=receipt,
                          release=AssertionError('must not release on unknown stop'))
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True}, bootout_fails=True)
        self.stop_raises(host, helper, 'bootout:native_command_failed', True,
                         phases=['acquire', 'revalidate'], modifies=['disable', 'bootout'])

    def test_stop_absence_poll_refuses_replacement_generation(self):
        receipt = quiesce_receipt()
        helper = Recorder(acquire=receipt, revalidate=receipt)
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True}, after_bootout='registered')
        self.stop_raises(host, helper, 'absence:stop_generation_changed', True,
                         phases=['acquire', 'revalidate'],
                         modifies=['disable', 'bootout'])

    def test_stop_residual_socket_after_absence_refuses(self):
        receipt = quiesce_receipt()
        helper = Recorder(acquire=receipt, revalidate=receipt)
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True})
        with mock.patch.object(mod, '_quiesce_paid_service', helper), \
                mock.patch.object(mod, 'observed_socket_state',
                                  return_value=(1, 2, 3, 0, 450, 1, 0, 0, 0)):
            with self.assertRaises(mod.PaidLifecycleError) as caught:
                mod.run_lifecycle(host, 'stop', RELEASE)
        self.assert_refusal(caught, 'absence:residual_socket_remains', True)
        self.assertEqual(host.modifies, ['disable', 'bootout'])

    def test_stop_preimage_readiness_drift_refuses_before_quiesce(self):
        receipt = quiesce_receipt()
        helper = Recorder(acquire=receipt)
        host = FakeHost(state='running', pid=4242, override='enabled')
        replies = [{'fixture': True}, {'fixture': False}]
        host.readiness = lambda snapshot, registration: replies.pop(0)
        with mock.patch.object(mod, '_quiesce_paid_service', helper):
            with self.assertRaises(mod.PaidLifecycleError) as caught:
                mod.run_lifecycle(host, 'stop', RELEASE)
        self.assert_refusal(caught, 'preflight:stop_generation_changed', False)
        self.assertEqual(helper.calls, [])

    def test_stop_socket_absent_drift_before_disable_releases_own_fence(self):
        receipt = quiesce_receipt()
        helper = Recorder(acquire=receipt, release=receipt)
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True})
        with mock.patch.object(mod, '_quiesce_paid_service', helper), \
                mock.patch.object(mod, 'observed_socket_state', return_value=None):
            with self.assertRaises(mod.PaidLifecycleError) as caught:
                mod.run_lifecycle(host, 'stop', RELEASE)
        self.assert_refusal(caught, 'quiesce_hold:stop_socket_absent', False)
        self.assertEqual([call[0] for call in helper.calls], ['acquire', 'release'])
        self.assertEqual(helper.calls[1][3], 'f' * 64)
        self.assertEqual(host.modifies, [])

    def test_stop_registration_generation_drift_after_acquire_releases_own_fence(self):
        receipt = quiesce_receipt()
        helper = Recorder(acquire=receipt, revalidate=receipt, release=receipt)
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True})
        original = host.registration
        observed = {'count': 0}

        def drift_third_observation():
            result = original()
            observed['count'] += 1
            if observed['count'] >= 3:
                return dict(state='running', pid=5252)
            return result
        host.registration = drift_third_observation
        self.stop_raises(host, helper, 'quiesce_hold:stop_generation_changed',
                         False, phases=['acquire', 'release'], modifies=[])
        self.assertEqual(helper.calls[1][3], 'f' * 64)



class RobustnessTests(unittest.TestCase):
    def test_unexpected_host_failure_is_reported_unknown_with_stage(self):
        host = FakeHost(state='absent')

        def explode():
            raise RuntimeError('fixture failure')
        host.override = explode
        with self.assertRaises(mod.PaidLifecycleError) as caught:
            mod.run_lifecycle(host, 'status', RELEASE)
        self.assertEqual(caught.exception.code, 'preflight:qualification_unavailable')
        self.assertTrue(caught.exception.effect_unknown)

    def test_quiesce_helper_receives_exact_release_and_definition_identity(self):
        receipt = quiesce_receipt()
        helper = Recorder(acquire=receipt, revalidate=receipt)
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True})
        with mock.patch.object(mod, '_quiesce_paid_service', helper), \
                mock.patch.object(mod, 'observed_socket_state',
                                  side_effect=StopTests.running_socket(host)):
            mod.run_lifecycle(host, 'stop', RELEASE)
        self.assertEqual(len(helper.calls), 2)
        for _phase, release_sha, definition_sha, _fence in helper.calls:
            self.assertEqual((release_sha, definition_sha), (RELEASE, DEFINITION))

    def test_status_ready_reports_disarmed_profile_identity(self):
        host = FakeHost(state='running', pid=4242, override='enabled',
                        readiness_payload={'fixture': True})
        result = mod.run_lifecycle(host, 'status', RELEASE)
        self.assertEqual(result['profile_id'], mod.PROFILE_ID)
        self.assertEqual(result['definition_sha256'], DEFINITION)
        self.assertFalse(result['bridge_armed'])
        self.assertFalse(result['capacity_admitted'])

    def test_unqualified_definition_never_reaches_any_launchctl_effect(self):
        host = FakeHost(state='absent',
                        interval_error=mod.PaidLifecycleError('definition_aggregate_changed'))
        for action in ('start', 'stop', 'status'):
            with self.assertRaises(mod.PaidLifecycleError) as caught:
                mod.run_lifecycle(host, action, RELEASE)
            self.assertEqual(caught.exception.code,
                             'preflight:definition_aggregate_changed')
            self.assertFalse(caught.exception.effect_unknown)
            self.assertEqual(host.modifies, [])


class SourceHygieneTests(unittest.TestCase):
    SOURCE = Path(mod.__file__).read_text()

    def test_finite_owner_is_never_imported_called_or_named(self):
        for token in ('finite_service_lifecycle', 'minimax-finite-01', '_mastermind_minimax',
                      'run_lifecycle(host, None', 'probe_socket'):
            self.assertNotIn(token, self.SOURCE)

    def test_no_bridge_uid_census_anywhere(self):
        for token in ('_ps_pids_for_uid', 'getgrouplist', 'uid 501 census',
                      'Classification', 'codesign_verified'):
            self.assertNotIn(token, self.SOURCE)
        self.assertNotIn(str(470), self.SOURCE)

    def test_lifecycle_never_signals_kills_or_adopts(self):
        for token in ('os.kill', 'kill(', 'killpg', 'SIGTERM', 'SIGKILL',
                      'signal.', 'setuid', 'setgid', 'ptrace'):
            self.assertNotIn(token, self.SOURCE)

    def test_no_new_store_marker_or_journal_is_written(self):
        for token in ('shutil', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.unlink',
                      'os.remove', 'write_bytes', 'write_text', 'makedirs',
                      'os.truncate', 'tempfile'):
            self.assertNotIn(token, self.SOURCE)

    def test_launchctl_verbs_are_the_only_fixed_effects(self):
        self.assertIn("{'enable', 'disable', 'bootstrap', 'kickstart', 'bootout'}", self.SOURCE)
        for token in ('subprocess.Popen', 'shell=True', 'os.system'):
            self.assertNotIn(token, self.SOURCE)

    def test_public_surface_is_exactly_the_contract(self):
        self.assertEqual(mod.ACTIONS, frozenset({'start', 'stop', 'status'}))
        signature = mod.run_paid_lifecycle.__code__.co_varnames[
            :mod.run_paid_lifecycle.__code__.co_argcount]
        self.assertEqual(signature, ('action', 'expected_release_sha',
                                     'expected_definition_sha256'))
        for name in ('run_paid_lifecycle', 'run_lifecycle', 'ProductionHost',
                     'PaidLifecycleError', 'definition_aggregate'):
            self.assertTrue(callable(getattr(mod, name)))


class IntegratedContractTests(unittest.TestCase):
    """Offline DATA/owner-seam counterexamples; no runtime qualification claim."""
    def test_wire_digest_matches_actual_contract_without_document_newline(self):
        from control_plane.paid_model_execution_contract import digest
        hashes = {name: 'a' * 64 for name in FILES}
        self.assertEqual(mod.definition_aggregate(hashes), digest(hashes))

    def test_source_profile_id_differs_from_execution_profile_id(self):
        from ops.executive_os.canonical_paid_definition import PROFILE_ID
        self.assertEqual(mod.DEFINITION_PROFILE_ID, PROFILE_ID)
        profile = dict(schema_version=mod.PROFILE_SCHEMA_V2,profile_id=PROFILE_ID,
            worker_id=mod.WORKER_ID,bridge_uid=501,bridge_armed=False,
            capacity_admitted=False,socket_path=mod.PAID_SOCKET_PATH,
            label=mod.PAID_LABEL,release_commit=RELEASE,
            registration=dict(worker_id=mod.WORKER_ID,quota_class='paid',account_label='data'),
            bindings_sha256='a'*64,expected_remote_binary={},
            remote_worker_identity=dict(worker_uid=1000,worker_gid=1000,worker_user='worker'))
        mod._validate_profile_pins(profile,FAKE_IDENTITY,RELEASE)
        profile['profile_id']=mod.PROFILE_ID
        with self.assertRaises(mod.PaidLifecycleError):
            mod._validate_profile_pins(profile,FAKE_IDENTITY,RELEASE)

    def test_current_control_binding_and_actual_principal_must_join(self):
        definition=Path('/fixed/paid')
        principal=dict(bridge_uid=501,bridge_gid=20,bridge_user='fixture')
        hashes={'bindings.json':'a'*64}
        binding=dict(bindings_path='/fixed/paid/bindings.json',bindings_sha256='a'*64)
        mod._require_control_profile_joins({'canonical_paid_fabric':binding},
            dict(principal),principal,definition,hashes)
        for bad in ({}, {'canonical_paid_fabric':dict(binding,bindings_sha256='b'*64)},
                    {'canonical_paid_fabric':dict(binding,bindings_path='/other')},
                    {'canonical_paid_fabric':dict(binding,extra=True)}):
            with self.assertRaises(mod.PaidLifecycleError):
                mod._require_control_profile_joins(bad,dict(principal),principal,definition,hashes)
        with self.assertRaises(mod.PaidLifecycleError):
            mod._require_control_profile_joins({'canonical_paid_fabric':binding},
                dict(principal,bridge_gid=21),principal,definition,hashes)

    def test_acquired_quiescence_must_match_original_readiness_generation(self):
        host=FakeHost(state='running',pid=4242,override='enabled')
        receipt=quiesce_receipt(process={**quiesce_receipt()['process'],'start_identity':'other'})
        with mock.patch.object(mod,'observed_socket_state',return_value=('fixture',)), \
             mock.patch.object(mod,'_quiesce_paid_service',Recorder(acquire=receipt)):
            with self.assertRaises(mod.PaidLifecycleError) as caught:
                mod.run_lifecycle(host,'stop',RELEASE)
        self.assertTrue(caught.exception.effect_unknown)
        self.assertEqual(host.modifies,[])
        self.assertIn('quiesce_original_process_changed',caught.exception.code)

    def test_incumbent_unknown_refuses_before_any_enable(self):
        host=FakeHost()
        host.require_incumbent_absent=mock.Mock(side_effect=mod.PaidLifecycleError('incumbent_present_or_unknown'))
        with mock.patch.object(mod,'observed_socket_state',return_value=None):
            with self.assertRaises(mod.PaidLifecycleError) as caught:
                mod.run_lifecycle(host,'start',RELEASE)
        self.assertFalse(caught.exception.effect_unknown)
        self.assertEqual(host.modifies,[])

    def test_existing_lock_observation_never_creates_or_deletes_state(self):
        import tempfile, fcntl, subprocess
        with tempfile.TemporaryDirectory() as directory:
            lock=Path(directory)/'shim.lock'
            with mock.patch.object(mod,'INCUMBENT_LOCK',lock), \
                 mock.patch.object(mod,'BRIDGE_UID',os.getuid()), \
                 mock.patch.object(mod,'checked_command') as command:
                with self.assertRaises(mod.PaidLifecycleError):
                    mod.require_incumbent_absent()
                self.assertFalse(lock.exists());command.assert_not_called()
                lock.write_text('retained-pid');lock.chmod(0o600)
                command.return_value=subprocess.CompletedProcess([],1,b'',b'')
                mod.require_incumbent_absent()
                self.assertEqual(lock.read_text(),'retained-pid')
                with lock.open('rb') as held:
                    fcntl.flock(held.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    with self.assertRaises(mod.PaidLifecycleError):
                        mod.require_incumbent_absent()
                for reply in (subprocess.CompletedProcess([],0,b'p123\n',b''),
                              subprocess.CompletedProcess([],1,b'',b'failure')):
                    command.return_value=reply
                    with self.assertRaises(mod.PaidLifecycleError):
                        mod.require_incumbent_absent()
                self.assertEqual(lock.read_text(),'retained-pid')

    def test_release_fence_refuses_changed_issuer_even_with_same_fence(self):
        held=quiesce_receipt()
        reply=quiesce_receipt(broker_process={**held['broker_process'],'pid':1000})
        with mock.patch.object(mod,'_quiesce_paid_service',return_value=reply):
            self.assertFalse(mod._release_own_fence(held,RELEASE,DEFINITION))


if __name__ == '__main__':
    raise SystemExit(unittest.main())
