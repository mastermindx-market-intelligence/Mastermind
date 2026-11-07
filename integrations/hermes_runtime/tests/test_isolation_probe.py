"""Synthetic regressions for final-role evidence. No provider, key or service calls.

Actual cgroup/Landlock guards are mocked in orchestration tests. Linux-only
fixture tests exercise owned disposable sockets/children, not a production role.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import datetime
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from integrations.hermes_runtime import isolation_probe as probe
from integrations.hermes_runtime import role_isolation, system_service, tcp_sandbox
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.profile import RuntimeProfile

REPO = Path(__file__).resolve().parents[3]
SOURCE = Path(probe.__file__).read_text()


def make_profile(role: str = "mmsecretary", *, state_dir: Path | None = None,
                 secrets_file: Path | None = None,
                 gateway_port: int | None = None,
                 backend_port: int | None = None) -> RuntimeProfile:
    """A profile built directly, so the test never needs the harness package."""
    ports = probe.ROLE_FIXED_PORTS[role]
    state = state_dir or Path("/srv/hermes") / role / "state"
    secrets = secrets_file or Path("/srv/hermes") / role / "private" / "role.env"
    return RuntimeProfile(
        schema="mastermind.hermes_runtime_profile.v1",
        role=role,
        sha="1c0cd667746d3395fe9e1b6c74f8f85952486f18",
        repository="https://github.com/NousResearch/hermes-agent.git",
        tool_allowlist=frozenset({"clarify"}),
        secrets_file=secrets,
        gateway_host=probe.ROLE_PROXY_HOST[role],
        gateway_port=ports["gateway"] if gateway_port is None else gateway_port,
        backend_port=ports["backend"] if backend_port is None else backend_port,
        auth_required=True,
        state_dir=state,
        hermes_home=state / "current" / "hermes-home",
        restart="on-failure",
        restart_sec=2.0,
        start_limit_burst=5,
        start_limit_interval_sec=60,
        memory_sample_interval_sec=5.0,
        model_provider="zai",
        model_default="glm-5.3-flash",
        source_path=Path("/srv/hermes/profile.yaml"),
        service_name=f"hermes-runtime-{role}",
    )


def case_by_id(case_id: str, role: str = "mmsecretary") -> probe._Case:
    """A matrix case bound to the role's real ports, as the probe binds it."""
    ports = probe.ROLE_FIXED_PORTS[role]
    for case in probe._bind_cases(role, ports["gateway"], ports["backend"],
                                  probe.DEFAULT_DENIED_PORT[role]):
        if case.case_id == case_id:
            return case
    raise AssertionError(f"unknown case {case_id}")


def current(case):
    return {'sufficient': True, 'pid': 101, 'start_ticks': 22, 'socket_inode': 333,
            'host': case.host, 'port': case.port}


def identity(role='mmsecretary'):
    uid = 2101 if role == 'mmsecretary' else 2102
    group = f'/system.slice/hermes-runtime-{role}.service'
    return {'role': role, 'nss_user': role, 'nss_uid': uid, 'nss_primary_gid': uid,
            'nss_gid': uid, 'nss_home': f'/home/{role}', 'process_uid': uid,
            'process_euid': uid, 'process_gid': uid, 'process_egid': uid,
            'process_groups': [uid], 'uid_is_nss_uid': True, 'gid_is_nss_gid': True,
            'no_extra_supplementary_groups': True, 'effective_cgroup_expected': group,
            'effective_cgroup_observed': group, 'effective_cgroup_raw': ['0::' + group]}


def provenance(role='mmsecretary'):
    return {'qualification_id': 'unit-q1', 'host': {'machine_id': 'a' * 32,
            'boot_id': '11111111-2222-3333-4444-555555555555', 'netns': [4, 5], 'kernel': 'test'},
            'sources': {'probe': 'c' * 64}, 'profile_sha256': ('a' if role == 'mmsecretary' else 'b') * 64,
            'profile_file': {'device': 1, 'inode': 2}, 'profile_resolved': f'/srv/{role}/profile.yaml'}


def args_for(profile=None):
    profile = profile or make_profile()
    return argparse.Namespace(profile=profile.source_path, role=profile.role,
        own_file=profile.state_dir / 'qualification' / 'synthetic.txt',
        peer_file=Path('/srv/hermes/mmmeta/state/qualification/synthetic.txt'), peer_report=None,
        qualification_id='unit-q1', peer_profile_sha256=None, peer_report_sha256=None,
        denied_port=None, report=None, connect_timeout=0.1, only='', list_cases=False,
        _provenance=provenance(profile.role), _context_stable=True,
        _observational_recheck={'observed_identity': identity(profile.role),
            'guards': [{'name': n, 'status': 'PASS', 'code': None} for n in probe.GUARD_ORDER[:3]],
            'identity_matched': True, 'guards_matched': True, 'provenance_matched': True},
        _profile_semantic=probe._profile_values(probe.asdict(profile)))


def report_fixture(role='mmmeta', *, complete=False):
    profile = make_profile(role)
    args = args_for(profile)
    ident = identity(role)
    cases = probe._bind_cases(role, profile.gateway_port, profile.backend_port, probe.DEFAULT_DENIED_PORT[role])
    records = {}
    facts = {'device': 1, 'inode': 2, 'uid': ident['nss_uid'], 'gid': ident['nss_gid'],
             'mode': '0o600', 'nlink': 1, 'size': len(probe.SYNTHETIC_MARKER), 'mtime_ns': 3, 'ctime_ns': 4}
    for case in cases:
        witness = {'sufficient': True}
        target = {}
        observed = case.expected
        if case.case_id == 'file.own.read':
            witness.update(facts=facts, sha256=probe.SYNTHETIC_MARKER_SHA256)
            target = {'path': str(args.own_file)}
        if not complete and case.case_id in {'file.peer.read', 'tcp.sibling_alias.gateway_port', 'tcp.shared_loopback.gateway_port'}:
            observed, witness = probe.OBSERVED_UNAVAILABLE, {'sufficient': False}
        records[case.case_id] = probe._case_record(case, probe._Outcome(observed, witness=witness, target=target), selected=True)
    guards = [{'name': name, 'status': probe.STATUS_PASS, 'code': None} for name in probe.GUARD_ORDER]
    bind, connect = probe.role_tcp_ports(profile)
    result = probe._build_report(profile, role, 'mmsecretary' if role == 'mmmeta' else 'mmmeta',
        ident, guards, records, set(records), bind, connect, probe.DEFAULT_DENIED_PORT[role], args,
        witnesses={'cleanup_complete': True}, listeners={})
    return result, profile, args, records, guards


class SourceBoundaryTests(unittest.TestCase):
    def test_guards_are_the_production_functions(self):
        self.assertIs(probe.assert_root_service_cgroup, system_service.assert_root_service_cgroup)
        self.assertIs(probe.assert_role_network_profile, system_service.assert_role_network_profile)
        self.assertIs(probe.assert_role_credential_isolation, role_isolation.assert_role_credential_isolation)
        self.assertIs(probe.enforce_role_tcp_ports, tcp_sandbox.enforce_role_tcp_ports)

    def test_no_secret_provider_or_lifecycle_imports(self):
        for text in ('from .secrets import', 'from .supervisor import', 'from .cli import',
                     'systemctl', 'os.system', 'os.killpg', 'iptables', 'nft '):
            self.assertNotIn(text, SOURCE)
        self.assertFalse(hasattr(probe, 'load_secrets'))
        self.assertFalse(hasattr(probe, 'ServiceRuntime'))

    def test_import_is_inert(self):
        code = "import integrations.hermes_runtime.isolation_probe; import sys; print('integrations.hermes_runtime.cli' in sys.modules)"
        r = subprocess.run([sys.executable, '-c', code], cwd=REPO,
            env={'PATH': os.defpath, 'PYTHONPATH': str(REPO), 'PYTHONDONTWRITEBYTECODE': '1'},
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), 'False')

    def test_guard_order_and_stop_on_refusal(self):
        order = []
        with mock.patch.object(probe, 'assert_root_service_cgroup', side_effect=lambda *_: order.append('cgroup')), \
             mock.patch.object(probe, 'assert_role_network_profile', side_effect=lambda *_: order.append('network')), \
             mock.patch.object(probe, 'assert_role_credential_isolation', side_effect=lambda *_: order.append('credential')):
            guards, ok = probe._run_guards(make_profile(), 'mmsecretary')
        self.assertTrue(ok)
        self.assertEqual(order, ['cgroup', 'network', 'credential'])
        self.assertEqual([g['name'] for g in guards], list(probe.GUARD_ORDER[:3]))
        with mock.patch.object(probe, 'assert_root_service_cgroup', side_effect=RuntimeRefusal('REFUSED')), \
             mock.patch.object(probe, 'assert_role_network_profile') as after:
            guards, ok = probe._run_guards(make_profile(), 'mmsecretary')
        self.assertFalse(ok)
        after.assert_not_called()


class ClassificationTests(unittest.TestCase):
    def tcp(self, code, symptom, *, baseline=True, after=True, case_id='tcp.own_alias.denied_port'):
        case = case_by_id(case_id)
        now = current(case)
        old = {'reached': baseline, 'target': f'{case.host}:{case.port}', 'listener': now}
        with mock.patch.object(probe, '_listener_current', side_effect=[now, now if after else {'sufficient': False}]), \
             mock.patch.object(probe, '_connect', return_value=(code, symptom)):
            return case, probe._tcp_outcome(case, {case.listener: {}}, {case.listener: old}, frozenset({8765, 8766, 18651}), 0.1)

    def test_only_immediate_expected_errno_with_real_baseline_and_bracket_passes(self):
        for code in (errno.EACCES, errno.EPERM):
            case, outcome = self.tcp(code, 'refused_immediately')
            self.assertEqual(probe._status_for(case, outcome), probe.STATUS_PASS)
            self.assertEqual(outcome.attribution, 'LANDLOCK_TCP_PORT')
        for baseline, after in ((False, True), (True, False)):
            case, outcome = self.tcp(errno.EACCES, 'refused_immediately', baseline=baseline, after=after)
            self.assertEqual(probe._status_for(case, outcome), probe.STATUS_UNAVAILABLE)

    def test_unrelated_tcp_errors_and_timeouts_never_pass_as_port_denial(self):
        for code, symptom in ((errno.EIO, 'refused_immediately'), (errno.ENETUNREACH, 'refused_immediately'),
                              (errno.EMFILE, 'refused_immediately'), (errno.EAGAIN, 'timed_out'),
                              (errno.ETIMEDOUT, 'timed_out'), (None, 'error'), (errno.ECONNREFUSED, 'refused_immediately')):
            with self.subTest(code=code, symptom=symptom):
                case, outcome = self.tcp(code, symptom)
                self.assertNotEqual(probe._status_for(case, outcome), probe.STATUS_PASS)
                self.assertNotEqual(outcome.attribution, 'LANDLOCK_TCP_PORT')

    def test_same_cgroup_cannot_supply_the_external_ip_positive(self):
        for case_id in ('tcp.sibling_alias.gateway_port', 'tcp.shared_loopback.gateway_port'):
            for baseline in (False, True):
                case, outcome = self.tcp(errno.EAGAIN, 'timed_out', baseline=baseline, case_id=case_id)
                self.assertEqual(probe._status_for(case, outcome), probe.STATUS_UNAVAILABLE)
                self.assertTrue(outcome.witness['external_positive_required'])

    def test_observed_forbidden_success_fails_even_if_listener_dies_afterward(self):
        case, outcome = self.tcp(None, 'connected', after=False)
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_FAIL)

    def test_allowed_success_requires_current_synthetic_listener(self):
        case, outcome = self.tcp(None, 'connected', after=False, case_id='tcp.own_alias.gateway_port')
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_UNAVAILABLE)
        case, outcome = self.tcp(None, 'connected', case_id='tcp.own_alias.gateway_port')
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_PASS)

    def test_missing_listener_stops_before_touching_an_unowned_endpoint(self):
        case = case_by_id('tcp.own_alias.denied_port')
        with mock.patch.object(probe, '_listener_current', return_value={'sufficient': False}), \
             mock.patch.object(probe, '_connect') as connect:
            outcome = probe._tcp_outcome(case, {}, {}, frozenset(), 0.1)
        connect.assert_not_called()
        self.assertEqual(outcome.observed, probe.OBSERVED_UNAVAILABLE)

    def test_truthy_or_empty_witnesses_do_not_prove_anything(self):
        self.assertFalse(probe._same_listener({'sufficient': True}, {'sufficient': True}))
        for expected in (probe.OBSERVED_ALLOWED, probe.OBSERVED_REFUSED):
            case = probe._Case('x', 'x', 'x', expected)
            for witness in ({}, {'sufficient': 'yes'}, {'sufficient': 1}):
                self.assertNotEqual(probe._status_for(case, probe._Outcome(expected, witness=witness)), probe.STATUS_PASS)


class ExecTests(unittest.TestCase):
    def outcome(self, observed, *, baseline=('connected', None), bracket=True):
        case = case_by_id('exec.own_alias.denied_port')
        now = current(case)
        with mock.patch.object(probe, '_listener_current', side_effect=[now, now if bracket else {'sufficient': False}]), \
             mock.patch.object(probe, '_exec_probe', return_value=observed):
            result = probe._exec_outcome(case, baseline, 0.1, {}, now)
        return probe._status_for(case, result), result

    def test_child_deadline_protocol_failure_timeout_and_other_errno_never_pass(self):
        for result in (('error', None), ('timeout', None), ('timed_out', errno.EAGAIN),
                       ('refused_immediately', errno.EIO), ('refused_immediately', errno.ENETUNREACH),
                       ('refused_immediately', errno.ECONNREFUSED), ('refused_immediately', 0)):
            with self.subTest(result=result):
                self.assertNotEqual(self.outcome(result)[0], probe.STATUS_PASS)

    def test_expected_exec_denial_requires_same_target_baseline_and_current_witness(self):
        self.assertEqual(self.outcome(('refused_immediately', errno.EACCES))[0], probe.STATUS_PASS)
        self.assertEqual(self.outcome(('refused_immediately', errno.EPERM), baseline=('error', None))[0], probe.STATUS_UNAVAILABLE)
        self.assertEqual(self.outcome(('refused_immediately', errno.EACCES), bracket=False)[0], probe.STATUS_UNAVAILABLE)
        self.assertEqual(self.outcome(('connected', None), baseline=('error', None))[0], probe.STATUS_FAIL)

    def test_parser_does_not_turn_malformed_or_failed_execution_into_errno(self):
        for output in ('ERR:0', 'ERR:-1', 'ERR:13\nOK', 'ERR:99999', 'anything'):
            with mock.patch.object(probe.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output, '')):
                self.assertEqual(probe._exec_probe('127.0.0.2', 45151, 0.1), ('error', None))
        with mock.patch.object(probe.subprocess, 'run', side_effect=subprocess.TimeoutExpired('x', 1)):
            self.assertEqual(probe._exec_probe('127.0.0.2', 45151, 0.1), ('timeout', None))
        with mock.patch.object(probe.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ERR:13', '')) as run:
            self.assertEqual(probe._exec_probe('127.0.0.2', 45151, 0.1), ('refused_immediately', errno.EACCES))
            self.assertEqual(run.call_args.args[0][1:3], ['-I', '-S'])
            self.assertEqual(run.call_args.kwargs['stdin'], subprocess.DEVNULL)


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name).resolve()
        self.file = self.state / 'qualification' / 'synthetic.txt'
        self.file.parent.mkdir(mode=0o700)
        self.file.write_bytes(probe.SYNTHETIC_MARKER)
        # BSD/macOS temp files may inherit a directory group other than getgid().
        os.chown(self.file, os.getuid(), os.getgid())
        self.file.chmod(0o600)

    def tearDown(self):
        self.temp.cleanup()

    def own(self):
        return probe._file_outcome_own(self.file, self.state, os.getuid(), os.getgid())

    def test_own_fixture_uses_actual_bounded_fd_facts(self):
        outcome = self.own()
        self.assertEqual(outcome.observed, probe.OBSERVED_ALLOWED)
        self.assertEqual(outcome.witness['facts']['inode'], self.file.stat().st_ino)
        self.assertEqual(outcome.witness['sha256'], probe.SYNTHETIC_MARKER_SHA256)

    def test_arbitrary_secret_path_is_rejected_before_open(self):
        with mock.patch.object(probe.os, 'open') as opened:
            result = probe._file_outcome_own(self.state / 'private.env', self.state, 1, 1)
        opened.assert_not_called()
        self.assertEqual(result.observed, probe.OBSERVED_ERROR)

    def test_symlink_fifo_hardlink_oversize_and_wrong_mode_do_not_pass(self):
        self.file.write_bytes(probe.SYNTHETIC_MARKER + b'x')
        self.assertNotEqual(self.own().observed, probe.OBSERVED_ALLOWED)
        self.file.write_bytes(probe.SYNTHETIC_MARKER)
        self.file.chmod(0o644)
        self.assertNotEqual(self.own().observed, probe.OBSERVED_ALLOWED)
        self.file.chmod(0o600)
        linked = self.state / 'link'; os.link(self.file, linked)
        self.assertNotEqual(self.own().observed, probe.OBSERVED_ALLOWED)
        linked.unlink(); self.file.unlink()
        self.file.symlink_to(linked)
        self.assertNotEqual(self.own().observed, probe.OBSERVED_ALLOWED)
        self.file.unlink(); os.mkfifo(self.file)
        self.assertNotEqual(self.own().observed, probe.OBSERVED_ALLOWED)

    def test_replacement_during_fd_read_invalidates_observation(self):
        original_read = os.read
        changed = False
        def replace(fd, n):
            nonlocal changed
            data = original_read(fd, n)
            if not changed:
                other = self.state / 'replacement'
                other.write_bytes(probe.SYNTHETIC_MARKER); other.chmod(0o600)
                os.replace(other, self.file); changed = True
            return data
        with mock.patch.object(probe.os, 'read', side_effect=replace):
            self.assertEqual(self.own().observed, probe.OBSERVED_ERROR)

    def test_successful_peer_read_always_wins_over_prior_stat_denial(self):
        with mock.patch.object(probe, '_try_stat', return_value={'errno': errno.EACCES}), \
             mock.patch.object(probe, '_try_read', return_value={'readable': True, 'errno': None}):
            result = probe._file_outcome_peer(self.file, {'sufficient': False})
        self.assertEqual(probe._status_for(case_by_id('file.peer.read'), result), probe.STATUS_FAIL)

    def test_parent_symlink_substitution_cannot_redirect_qualified_read(self):
        original_open = os.open
        actual = self.state / 'original-qualification'
        redirected = self.state / 'redirected'
        redirected.mkdir()
        alternate = redirected / 'synthetic.txt'
        alternate.write_bytes(probe.SYNTHETIC_MARKER)
        os.chown(alternate, os.getuid(), os.getgid()); alternate.chmod(0o600)
        changed = False
        def substitute(path, flags, *args, **kwargs):
            nonlocal changed
            if path == 'synthetic.txt' and not changed:
                self.file.parent.rename(actual)
                self.file.parent.symlink_to(redirected, target_is_directory=True)
                changed = True
            return original_open(path, flags, *args, **kwargs)
        with mock.patch.object(probe.os, 'open', side_effect=substitute):
            outcome = self.own()
        self.assertTrue(changed)
        self.assertNotEqual(outcome.observed, probe.OBSERVED_ALLOWED)

    def test_contradictory_missing_peer_never_becomes_denial_pass(self):
        with mock.patch.object(probe, '_try_stat', return_value={'errno': errno.EACCES}), \
             mock.patch.object(probe, '_try_read', return_value={'readable': False, 'errno': errno.ENOENT}):
            result = probe._file_outcome_peer(self.file, {'sufficient': True})
        self.assertEqual(result.observed, probe.OBSERVED_UNAVAILABLE)

    def test_no_qualified_peer_report_means_no_unwitnessed_file_read(self):
        with mock.patch.object(probe, '_try_read') as read:
            result = probe._file_outcome(case_by_id('file.peer.read'), make_profile(), 2101, 2101,
                self.file, self.file, None)
        read.assert_not_called()
        self.assertEqual(result.observed, probe.OBSERVED_UNAVAILABLE)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.target = self.root / 'report-q1.json'

    def tearDown(self):
        self.temp.cleanup()

    def test_existing_file_and_symlink_are_not_overwritten(self):
        self.target.write_bytes(b'original')
        with self.assertRaises(FileExistsError), contextlib.redirect_stdout(io.StringIO()):
            probe._write_report({'new': True}, self.target)
        self.assertEqual(self.target.read_bytes(), b'original')
        self.target.unlink(); other = self.root / 'other'; other.write_bytes(b'other')
        self.target.symlink_to(other)
        with self.assertRaises(FileExistsError), contextlib.redirect_stdout(io.StringIO()):
            probe._write_report({'new': True}, self.target)
        self.assertEqual(other.read_bytes(), b'other')

    def test_complete_private_report_is_published_and_read_back(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            probe._write_report({'case': 'unit'}, self.target)
        self.assertEqual(output.getvalue().encode(), self.target.read_bytes())
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o600)
        self.assertEqual(self.target.stat().st_nlink, 1)
        self.assertEqual([p.name for p in self.root.iterdir()], [self.target.name])

    def test_failed_flush_leaves_no_final_partial_report(self):
        with mock.patch.object(probe.os, 'fsync', side_effect=OSError(errno.EIO, 'synthetic')), \
             self.assertRaises(OSError), contextlib.redirect_stdout(io.StringIO()):
            probe._write_report({'case': 'unit'}, self.target)
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_concurrent_publish_has_exactly_one_winner(self):
        errors, winners = [], []
        def publish(value):
            try:
                probe._write_report({'winner': value}, self.target); winners.append(value)
            except FileExistsError:
                errors.append('exists')
        with contextlib.redirect_stdout(io.StringIO()):
            threads = [threading.Thread(target=publish, args=(i,)) for i in (1, 2)]
            for t in threads: t.start()
            for t in threads: t.join(timeout=5)
        self.assertTrue(all(not t.is_alive() for t in threads))
        self.assertEqual(len(winners), 1); self.assertEqual(errors, ['exists'])
        self.assertEqual(json.loads(self.target.read_text())['winner'], winners[0])

    def test_parent_replacement_before_publication_leaves_no_final_report(self):
        parent = self.root / 'qualification'; parent.mkdir()
        target = parent / 'report-q1.json'
        original = self.root / 'original'; redirected = self.root / 'redirected'; redirected.mkdir()
        fsync = os.fsync
        changed = False
        def substitute(fd):
            nonlocal changed
            fsync(fd)
            if not changed:
                parent.rename(original); parent.symlink_to(redirected, target_is_directory=True)
                changed = True
        with mock.patch.object(probe.os, 'fsync', side_effect=substitute), \
             self.assertRaises((OSError, RuntimeRefusal)), contextlib.redirect_stdout(io.StringIO()):
            probe._write_report({'case': 'unit'}, target)
        self.assertFalse((redirected / target.name).exists())
        self.assertFalse((original / target.name).exists())
        self.assertEqual(list(original.iterdir()), [])


class ReportAndBindTests(unittest.TestCase):
    def test_first_a_can_be_incomplete_with_valid_own_file_evidence(self):
        report, *_ = report_fixture()
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertFalse(report['qualified'])
        self.assertEqual(report['own_file']['status'], probe.STATUS_PASS)
        self.assertEqual(report['context']['expected_cgroup'],
                         report['context']['identity']['effective_cgroup_expected'])

    def test_fully_mocked_pass_requires_guards_full_matrix_stable_context_and_cleanup(self):
        report, profile, args, records, guards = report_fixture(complete=True)
        self.assertEqual(report['status'], 'PASS')  # aggregate logic only; all matrix boundaries mocked
        bind, connect = probe.role_tcp_ports(profile)
        for field in ('guards', 'selection', 'stable', 'cleanup'):
            local = copy.deepcopy(args)
            if field == 'stable': local._context_stable = False
            altered = probe._build_report(profile, profile.role, 'mmsecretary', identity(profile.role),
                [] if field == 'guards' else guards, records,
                {'file.own.read'} if field == 'selection' else set(records), bind, connect, 45152, local,
                witnesses={'cleanup_complete': field != 'cleanup'}, listeners={})
            self.assertFalse(altered['qualified'], field)

    def test_host_boot_source_and_full_profile_change_fingerprint(self):
        original, profile, args, records, guards = report_fixture()
        bind, connect = probe.role_tcp_ports(profile)
        for field in ('machine', 'boot', 'source', 'profile'):
            local = copy.deepcopy(args)
            if field == 'machine': local._provenance['host']['machine_id'] = 'd' * 32
            if field == 'boot': local._provenance['host']['boot_id'] = 'new-boot'
            if field == 'source': local._provenance['sources']['probe'] = 'e' * 64
            if field == 'profile': local._profile_semantic['model_default'] = 'different'
            changed = probe._build_report(profile, profile.role, 'mmsecretary', identity(profile.role), guards,
                records, set(records), bind, connect, 45152, local, witnesses={'cleanup_complete': True}, listeners={})
            self.assertNotEqual(original['context_fingerprint'], changed['context_fingerprint'])

    def test_post_landlock_fixed_bind_and_ephemeral_denial_are_explicit_cases(self):
        fixed = case_by_id('bind.own_alias.gateway_port')
        with mock.patch.object(probe, '_listener_current', return_value=current(fixed)):
            result = probe._bind_outcome(fixed, {'own_gateway': {'created_after_landlock': True}}, {})
            self.assertEqual(probe._status_for(fixed, result), probe.STATUS_PASS)
            result = probe._bind_outcome(fixed, {'own_gateway': {'created_after_landlock': False}}, {})
            self.assertNotEqual(probe._status_for(fixed, result), probe.STATUS_PASS)
        case = case_by_id('bind.own_alias.ephemeral_port')
        for code, expected in ((errno.EACCES, probe.STATUS_PASS), (errno.EPERM, probe.STATUS_PASS),
                               (None, probe.STATUS_FAIL), (errno.EADDRINUSE, probe.STATUS_FAIL)):
            with mock.patch.object(probe, '_ephemeral_bind', return_value=(code, 12345 if code is None else None)):
                result = probe._bind_outcome(case, {}, {'bound': True})
                self.assertEqual(probe._status_for(case, result), expected)
        with mock.patch.object(probe, '_ephemeral_bind', return_value=(errno.EACCES, None)):
            self.assertEqual(probe._status_for(case, probe._bind_outcome(case, {}, {'bound': False})), probe.STATUS_UNAVAILABLE)

    def test_nan_infinite_timeouts_and_bad_qualification_ids_refuse(self):
        base = ['--profile', '/p', '--role', 'mmmeta', '--own-file', '/o', '--peer-file', '/x', '--qualification-id', 'q1']
        for value in ('nan', 'inf', '-inf', '0', '31'):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                probe._parse_args([*base, '--connect-timeout=' + value])
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            probe._parse_args([*base[:-1], '../q'])


class OrchestrationTests(unittest.TestCase):
    def test_final_identity_or_observation_guard_drift_invalidates_context(self):
        initial = [{'name': n, 'status': 'PASS', 'code': None} for n in probe.GUARD_ORDER[:3]]
        for changed in ('identity', 'guard'):
            args = args_for(); args.only = 'profile.fixed_ports'
            later_identity = identity()
            later_guards = copy.deepcopy(initial)
            if changed == 'identity': later_identity['effective_cgroup_observed'] = '/foreign'
            else: later_guards[-1].update(status='REFUSED', code='SYNTHETIC_DRIFT')
            with self.subTest(changed=changed), \
                 mock.patch.object(probe, '_capture_provenance', return_value=provenance()), \
                 mock.patch.object(probe, 'load_profile', return_value=make_profile()), \
                 mock.patch.object(probe, '_identity_facts', side_effect=[identity(), later_identity]), \
                 mock.patch.object(probe, '_run_guards', side_effect=[(initial, True), (later_guards, changed != 'guard')]), \
                 mock.patch.object(probe, 'enforce_role_tcp_ports') as restrict, \
                 mock.patch.object(probe, '_write_report') as write:
                probe._run_probe(args)
            restrict.assert_called_once()
            report = write.call_args.args[0]
            self.assertFalse(report['context_rechecked'])
            self.assertFalse(report['qualified'])
            self.assertEqual(report['guards'][:3], initial)

    def test_allowed_listener_bind_occurs_after_restriction_and_cleanup_before_report(self):
        events, final = [], []
        profile, args = make_profile(), args_for()
        def spawn(host, port):
            events.append(('bind', host, port))
            return 500 + len(events), {'bound': True, 'bind_host': host, 'bind_port': port}
        def enforce(_): events.append(('restrict',))
        def write(report, _): events.append(('report',)); final.append(report)
        guards = [{'name': n, 'status': 'PASS', 'code': None} for n in probe.GUARD_ORDER[:3]]
        with mock.patch.object(probe, '_capture_provenance', return_value=provenance()), \
             mock.patch.object(probe, 'load_profile', return_value=profile), \
             mock.patch.object(probe, '_identity_facts', return_value=identity()), \
             mock.patch.object(probe, '_run_guards', return_value=(guards, True)), \
             mock.patch.object(probe, '_spawn_listener', side_effect=spawn), \
             mock.patch.object(probe, '_pre_landlock_baseline', return_value={'reached': False}), \
             mock.patch.object(probe, '_listener_current', return_value={'sufficient': False}), \
             mock.patch.object(probe, '_exec_probe', return_value=('error', None)), \
             mock.patch.object(probe, '_ephemeral_bind', return_value=(errno.EACCES, None)), \
             mock.patch.object(probe, 'enforce_role_tcp_ports', side_effect=enforce), \
             mock.patch.object(probe, '_file_outcome', return_value=probe._Outcome(probe.OBSERVED_UNAVAILABLE)), \
             mock.patch.object(probe, '_terminate_children', side_effect=lambda _: events.append(('cleanup',)) or True), \
             mock.patch.object(probe, '_write_report', side_effect=write):
            probe._run_probe(args)
        point = events.index(('restrict',))
        self.assertLess(events.index(('bind', profile.gateway_host, 45151)), point)
        self.assertGreater(events.index(('bind', profile.gateway_host, profile.gateway_port)), point)
        self.assertGreater(events.index(('bind', profile.gateway_host, profile.backend_port)), point)
        self.assertLess(events.index(('cleanup',)), events.index(('report',)))
        self.assertFalse(final[0]['qualified'])

    def test_observation_guard_refusal_never_creates_listeners_or_applies_landlock(self):
        with mock.patch.object(probe, '_capture_provenance', return_value=provenance()), \
             mock.patch.object(probe, 'load_profile', return_value=make_profile()), \
             mock.patch.object(probe, '_identity_facts', return_value=identity()), \
             mock.patch.object(probe, '_run_guards', return_value=([{'name': 'assert_root_service_cgroup', 'status': 'REFUSED', 'code': 'NO'}], False)), \
             mock.patch.object(probe, '_spawn_listener') as spawn, \
             mock.patch.object(probe, 'enforce_role_tcp_ports') as enforce, \
             mock.patch.object(probe, '_write_report') as write:
            self.assertEqual(probe._run_probe(args_for()), probe.CONFIG_EXIT)
        spawn.assert_not_called(); enforce.assert_not_called()
        self.assertFalse(write.call_args.args[0]['qualified'])


@unittest.skipUnless(sys.platform.startswith('linux'), 'actual Linux proc/socket fixture only')
class LinuxListenerTests(unittest.TestCase):
    def test_owned_pid_start_inode_and_exact_address_are_required_and_reaped(self):
        pid, listener = probe._spawn_listener('127.0.0.1', 0)
        listener['bind_port'] = listener.get('listen_port', 0)
        try:
            now = probe._listener_current(listener, '127.0.0.1', listener['bind_port'])
            self.assertTrue(now['sufficient'])
            for change in ({'socket_inode': listener['socket_inode'] + 1}, {'start_ticks': listener['start_ticks'] + 1}):
                self.assertFalse(probe._listener_current({**listener, **change}, '127.0.0.1', listener['bind_port'])['sufficient'])
            self.assertFalse(probe._listener_current(listener, '127.0.0.2', listener['bind_port'])['sufficient'])
        finally:
            self.assertTrue(probe._terminate_children([listener]))
        self.assertFalse(probe._listener_current(listener, '127.0.0.1', listener['bind_port'])['sufficient'])

    def test_cleanup_kills_only_owned_child_that_ignores_term_with_finite_deadline(self):
        readfd, writefd = os.pipe(); pid = os.fork()
        if pid == 0:
            os.close(readfd); signal.signal(signal.SIGTERM, signal.SIG_IGN)
            signal.alarm(10); os.write(writefd, b'1'); os.close(writefd)
            while True: signal.pause()
        os.close(writefd); self.assertEqual(os.read(readfd, 1), b'1'); os.close(readfd)
        child = probe._process_identity(pid)
        started = time.monotonic()
        self.assertTrue(probe._terminate_children([child]))
        self.assertLess(time.monotonic() - started, 5)
        self.assertTrue(probe._terminate_children([{'pid': os.getpid(), 'start_ticks': 1}]))


@unittest.skipUnless(sys.platform.startswith('linux') and os.geteuid() == 0, 'actual root-copied report custody only')
class PeerReportRootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mmx-peer-test-', dir='/run')
        self.path = Path(self.temp.name) / 'peer.json'
        self.report, *_ = report_fixture()
        self.account = SimpleNamespace(pw_name='mmmeta', pw_uid=2102, pw_gid=2102, pw_dir='/home/mmmeta')
        self.group = SimpleNamespace(gr_gid=2102)
        self.digest = self.write(self.report)

    def tearDown(self): self.temp.cleanup()

    def write(self, report):
        report['context_fingerprint'] = hashlib.sha256(probe._canonical({'context': report['context'], 'selected': report['selected_matrix']})).hexdigest()
        raw = json.dumps(report, sort_keys=True).encode()
        self.path.write_bytes(raw); self.path.chmod(0o644)
        return hashlib.sha256(raw).hexdigest()

    def load(self, digest=None):
        with mock.patch.object(probe.pwd, 'getpwnam', return_value=self.account), \
             mock.patch.object(probe.grp, 'getgrnam', return_value=self.group):
            return probe._load_peer_report(self.path, 'mmmeta', qualification_id='unit-q1', provenance=provenance(),
                expected_profile_sha256='b' * 64, expected_report_sha256=digest or self.digest)

    def test_root_copied_incomplete_first_a_is_valid_earlier_evidence_not_current_denial_proof(self):
        report, reason = self.load()
        self.assertIsNotNone(report, reason)
        self.assertEqual(report['status'], 'INCOMPLETE')
        witness = probe._peer_witness(report, Path(report['own_file']['path']))
        self.assertTrue(witness['artifact_qualified'])
        self.assertFalse(witness['sufficient'])
        with mock.patch.object(probe, '_try_stat', return_value={'errno': errno.EACCES}), \
             mock.patch.object(probe, '_try_read', return_value={'readable': False, 'errno': errno.EACCES}):
            result = probe._file_outcome_peer(Path(report['own_file']['path']), witness)
        self.assertEqual(probe._status_for(case_by_id('file.peer.read'), result), probe.STATUS_UNAVAILABLE)

    def test_host_boot_run_source_role_profile_identity_guard_and_fixture_mismatch_refuse(self):
        mutators = [
            lambda r: r['context']['provenance']['host'].update(machine_id='d' * 32),
            lambda r: r['context']['provenance']['host'].update(boot_id='new'),
            lambda r: r.update(qualification_id='other'),
            lambda r: r['context']['provenance']['sources'].update(probe='e' * 64),
            lambda r: r['context']['provenance'].update(profile_sha256='c' * 64),
            lambda r: r.update(role='mmsecretary'),
            lambda r: r['context']['identity'].update(process_uid=2101),
            lambda r: r['context']['identity'].update(effective_cgroup_observed='/system.slice/foreign.service'),
            lambda r: r['guards'].pop(),
            lambda r: r['own_file']['facts'].update(inode=True),
            lambda r: r['own_file'].update(sha256='f' * 64),
            lambda r: r.update(context_rechecked=False),
            lambda r: r.update(cleanup_complete=False),
            lambda r: r.update(generated_at_utc='2000-01-01T00:00:00Z'),
        ]
        for i, mutate in enumerate(mutators):
            changed = copy.deepcopy(self.report); mutate(changed)
            with self.subTest(case=i):
                report, _ = self.load(self.write(changed)); self.assertIsNone(report)

    def test_old_minimal_or_unsealed_report_is_rejected(self):
        self.path.write_text(json.dumps({'schema': probe.SCHEMA, 'role': 'mmmeta', 'own_file': {
            'status': 'PASS', 'sha256': probe.SYNTHETIC_MARKER_SHA256, 'path': '/x/qualification/synthetic.txt'}}))
        report, _ = self.load(hashlib.sha256(self.path.read_bytes()).hexdigest()); self.assertIsNone(report)
        self.digest = self.write(self.report); self.path.chmod(0o666)
        self.assertIsNone(self.load()[0])

    def test_changed_hash_symlink_hardlink_and_oversize_custody_refuse(self):
        self.path.write_bytes(self.path.read_bytes() + b' ')
        self.assertIsNone(self.load()[0])
        self.digest = self.write(self.report)
        other = self.path.with_name('other'); os.link(self.path, other)
        self.assertIsNone(self.load()[0]); other.unlink()
        self.path.rename(other); self.path.symlink_to(other)
        self.assertIsNone(self.load()[0]); self.path.unlink(); other.unlink()
        self.path.write_bytes(b'x' * (probe.MAX_REPORT_BYTES + 1)); self.path.chmod(0o644)
        self.assertIsNone(self.load(hashlib.sha256(self.path.read_bytes()).hexdigest())[0])


class PeerReportSemanticTests(PeerReportRootTests):
    """Real decoder/joins on every platform; only FD custody and NSS are mocked."""
    __unittest_skip__ = False
    __unittest_skip_why__ = ''

    def setUp(self):
        self.path = Path('/qualified-root/peer.json')
        self.report, *_ = report_fixture()
        self.account = SimpleNamespace(pw_name='mmmeta', pw_uid=2102, pw_gid=2102, pw_dir='/home/mmmeta')
        self.group = SimpleNamespace(gr_gid=2102)
        self.digest = self.write(self.report)

    def tearDown(self):
        pass

    def write(self, report):
        report['context_fingerprint'] = hashlib.sha256(probe._canonical(
            {'context': report['context'], 'selected': report['selected_matrix']})).hexdigest()
        self.raw = json.dumps(report, sort_keys=True).encode()
        return hashlib.sha256(self.raw).hexdigest()

    def load(self, digest=None):
        with mock.patch.object(probe, '_read_regular', return_value=(self.raw, {'uid': 0, 'mode': '0o644'})):
            return super().load(digest)

    def test_old_minimal_or_unsealed_report_is_rejected(self):
        self.raw = json.dumps({'schema': probe.SCHEMA, 'role': 'mmmeta', 'own_file': {
            'status': 'PASS', 'sha256': probe.SYNTHETIC_MARKER_SHA256,
            'path': '/x/qualification/synthetic.txt'}}).encode()
        self.assertIsNone(self.load(hashlib.sha256(self.raw).hexdigest())[0])

    def test_changed_hash_symlink_hardlink_and_oversize_custody_refuse(self):
        # Actual symlink/hardlink/size custody is exercised only by the root class.
        self.raw += b' '
        self.assertIsNone(self.load()[0])

    def test_final_observational_recheck_must_match_initial_identity_and_guards(self):
        for field in ('identity_matched', 'guards_matched', 'provenance_matched', 'guards', 'observed_identity'):
            altered = copy.deepcopy(self.report)
            altered['observational_recheck'][field] = False if field.endswith('_matched') else {}
            with self.subTest(field=field):
                self.assertIsNone(self.load(self.write(altered))[0])


if __name__ == '__main__':
    unittest.main()
