"""Isolated producer tests: actual adaptive-429 receipt custody and the
prospective Qwen outcome feedback adapter.

Every store, policy file, key config, session capture and receipt destination
is a disposable fixture under one private temp root. No credential, no network,
no live slot state and no installed configuration is read or changed. The
existing int `cooldown` API, the adaptive ladder, the soft-cap floor and all
generic Claude/Codex behavior must stay exactly as supplied. The wrapper script
is checked statically only (bash syntax and wiring); the real controller
process binding and quota-circuit consumer joins remain the parent's
integrated fixtures.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock

TESTS_DIR = Path(__file__).resolve().parent
CANDIDATE_DIR = TESTS_DIR.parent / 'candidate'
sys.path[:0] = [str(CANDIDATE_DIR), str(TESTS_DIR.parent / 'source'), str(TESTS_DIR)]
from _offline_boundary import (acquire as _offline_acquire, release as _offline_release,
    guarded_python_child, guarded_python_file, guarded_bash_syntax)

def setUpModule():
    _offline_acquire()

def tearDownModule():
    _offline_release()

import bailian_keys as bk  # noqa: E402  (real candidate module, fixture stores)
import provider_outcome as po  # noqa: E402

FIXTURE_KEYS = {'acct-a': 'fixture-value-a', 'acct-b': 'fixture-value-b'}
FIXTURE_POLICY = {
    'per_key_cap': 7,
    'onpeak_per_key_cap': 3,
    'soft_cap_on_429': True,
    'offpeak_window': {'start': '22:00', 'end': '08:00', 'tz': 'Asia/Shanghai'},
    'discounted_models': ['qwen3.8-flash'],
    'offpeak_default_model': 'qwen3.8-flash',
}
FEEDBACK_KEYS = {
    'schema', 'account', 'classification_source', 'classification',
    'policy_source', 'observed_at', 'until_ts', 'duration_seconds',
    'soft_cap', 'soft_cap_enabled'}
OUTCOME_FIXED_KEYS = {
    'kind', 'command_rc', 'initial_rejection', 'complete_event_capture',
    'api_status', 'reset_at', 'reset_source', 'session_id', 'capture_sha256',
    'capture_bytes', 'stdout_sha256'}
OUTCOME_ENVELOPE_KEYS = {
    'schema', 'run_id', 'lease_id', 'account', 'root_id', 'host', 'provider',
    'model', 'observed_at'}


class FixtureRoot(unittest.TestCase):
    """One disposable temp root; restore the real module store paths after."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='qwen-feedback-fixture-'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        stored = ('POLICY_PATH', 'CONFIG_PATH', 'SLOTS_ROOT', 'LOCK_PATH')
        self._saved = {name: getattr(bk, name) for name in stored}
        self.addCleanup(self._restore_stores)
        (self.root / 'slots').mkdir()
        bk.POLICY_PATH = str(self.root / 'bailian_policy.json')
        bk.CONFIG_PATH = str(self.root / 'config.json')
        bk.SLOTS_ROOT = str(self.root / 'slots')
        bk.LOCK_PATH = str(self.root / 'slots' / '.lock')
        self.write_policy(FIXTURE_POLICY)
        (self.root / 'config.json').write_text(json.dumps(
            {'token-plan': {'api_keys': [
                {'name': name, 'api_key': value}
                for name, value in FIXTURE_KEYS.items()]}}))

    def _restore_stores(self):
        for name, value in self._saved.items():
            setattr(bk, name, value)

    def write_policy(self, policy):
        Path(bk.POLICY_PATH).write_text(json.dumps(policy))

    def cooldown_line(self, name):
        path = Path(bk.SLOTS_ROOT) / f'{name}.cooldown'
        return path.read_text().strip() if path.exists() else None

    def new_receipt_path(self):
        return self.root / 'qwen_429_feedback.json'

    def add_slot_marker(self, name, pid):
        slot = Path(bk.SLOTS_ROOT) / name
        slot.mkdir(parents=True, exist_ok=True)
        (slot / str(pid)).write_text(f'{pid} {int(time.time())}\n')

    def assertNoTempFiles(self):
        self.assertEqual([], list(self.root.rglob('*.tmp')))

    @contextlib.contextmanager
    def bound_environ(self, **over):
        """Hermetic bound scope for adapter calls, ambient keys removed."""
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('POOL_', 'REMOTE_SUB_', 'LANE_'))}
        env.update({
            'POOL_OUTCOME_FILE': str(self.target),
            'REMOTE_SUB_RUN_ID': 'run-fixture-0001',
            'POOL_LEASE_ID': 'lease-fixture-0001',
            'POOL_ACCOUNT': 'acct-a',
            'POOL_ORCHESTRATOR_ID': 'root-fixture-0001',
            'LANE_REMOTE_HOST': 'fixture-host',
        })
        env.update(over)
        # Restore every ambient key, not only the scope labels. Removing the
        # inherited PATH here leaks into later unittest-discovered modules.
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            yield env


class AdaptiveReceiptCustody(FixtureRoot):

    def test_first_429_records_actual_120s_same_event_receipt(self):
        target = self.new_receipt_path()
        expiry, receipt = bk.cooldown_feedback(
            'acct-a', 1800, 'http_429', receipt_path=str(target))
        self.assertIsNotNone(receipt)
        # The adaptive policy decided, not the requested 1800 s.
        self.assertEqual(120, receipt['duration_seconds'])
        self.assertEqual(expiry, receipt['until_ts'])
        self.assertEqual(10, len(receipt))
        self.assertEqual(FEEDBACK_KEYS, set(receipt))
        self.assertEqual('mastermind.qwen_adaptive429_feedback.v1',
                         receipt['schema'])
        self.assertEqual('acct-a', receipt['account'])
        self.assertEqual('429', receipt['classification'])
        self.assertEqual('bailian_keys.adaptive_http_429',
                         receipt['policy_source'])
        self.assertEqual('qwen_wrapper_inference',
                         receipt['classification_source'])
        # Soft-cap floor: no active slots, soft cap enabled.
        self.assertEqual(3, receipt['soft_cap'])
        self.assertIs(True, receipt['soft_cap_enabled'])
        # Same event, same lock: the persisted cooldown line, the recorded 429
        # epoch and the receipt must be one observation, never another's.
        self.assertEqual(f'{expiry} http_429', self.cooldown_line('acct-a'))
        self.assertEqual([receipt['observed_at']], bk._read_429count('acct-a'))
        on_disk = json.loads(target.read_text())
        self.assertEqual(receipt, on_disk)
        self.assertEqual(0o600, stat.S_IMODE(target.stat().st_mode))
        self.assertNoTempFiles()

    def test_receipt_race_cannot_replace_an_incumbent_destination(self):
        target = self.new_receipt_path()
        actual_link = bk.os.link
        def race(src, dst, **kwargs):
            Path(dst).write_bytes(b'incumbent fixture bytes')
            return actual_link(src, dst, **kwargs)
        with unittest.mock.patch.object(bk.os, 'link', side_effect=race):
            self.assertFalse(bk._write_private_json(str(target), {'fixture': True}))
        self.assertEqual(b'incumbent fixture bytes', target.read_bytes())
        self.assertNoTempFiles()

    def test_second_429_doubles_to_240_not_the_requested_value(self):
        _, first = bk.cooldown_feedback('acct-a', 1800, 'http_429')
        self.assertEqual(120, first['duration_seconds'])
        target = self.new_receipt_path()
        expiry, second = bk.cooldown_feedback(
            'acct-a', 600, 'http_429', receipt_path=str(target))
        self.assertIsNotNone(second)
        self.assertEqual(240, second['duration_seconds'])
        self.assertEqual(expiry, second['until_ts'])
        self.assertEqual(f'{expiry} http_429', self.cooldown_line('acct-a'))
        self.assertFalse(target.exists() and json.loads(
            target.read_text())['duration_seconds'] == 600)

    def test_adaptive_ladder_unchanged_through_1800_cap(self):
        seen = []
        for _ in range(5):
            _, receipt = bk.cooldown_feedback('acct-a', 99999, 'http_429')
            seen.append(receipt['duration_seconds'])
        self.assertEqual([120, 240, 480, 960, 1800], seen)

    def test_soft_cap_reflects_actual_active_count_with_floor_three(self):
        procs = [subprocess.Popen(
            [sys.executable, '-c', guarded_python_child('import time; time.sleep(20)')],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(5)]
        try:
            for proc in procs:
                self.addCleanup(proc.wait)
                self.add_slot_marker('acct-a', proc.pid)
            self.assertEqual(5, bk.active_count('acct-a'))
            _, receipt = bk.cooldown_feedback('acct-a', 1800, 'http_429')
            expected = max(3, min(bk.current_per_key_cap(), 4))
            self.assertEqual(expected, receipt['soft_cap'])
            self.assertEqual(bk._effective_cap_for_key('acct-a'),
                             receipt['soft_cap'])
            self.assertGreaterEqual(receipt['soft_cap'], 3)
        finally:
            for proc in procs:
                proc.kill()
                proc.wait()

    def test_disabled_soft_cap_reports_base_cap_and_flag(self):
        policy = dict(FIXTURE_POLICY)
        policy['soft_cap_on_429'] = False
        self.write_policy(policy)
        _, receipt = bk.cooldown_feedback('acct-a', 1800, 'http_429')
        self.assertIs(False, receipt['soft_cap_enabled'])
        self.assertEqual(bk.current_per_key_cap(), receipt['soft_cap'])
        self.assertEqual(receipt['soft_cap'],
                         bk._effective_cap_for_key('acct-a'))

    def test_old_int_api_unchanged_and_clears_429_state(self):
        bk.cooldown_feedback('acct-a', 1800, 'http_429')
        self.assertTrue(bk._read_429count('acct-a'))
        expiry = bk.cooldown('acct-a', 60, 'manual')
        self.assertEqual(int, type(expiry))
        self.assertEqual(f'{expiry} manual', self.cooldown_line('acct-a'))
        self.assertEqual([], bk._read_429count('acct-a'))
        self.assertIsNone(bk._read_soft_cap('acct-a'))
        self.assertEqual([], list(Path(bk.SLOTS_ROOT).rglob('*.json')))

    def test_non_429_cooldown_never_writes_a_receipt(self):
        target = self.new_receipt_path()
        expiry, receipt = bk.cooldown_feedback(
            'acct-a', 86400, 'invalid_api_key', receipt_path=str(target))
        self.assertIsNone(receipt)
        self.assertFalse(target.exists())
        self.assertEqual(f'{expiry} invalid_api_key',
                         self.cooldown_line('acct-a'))

    def test_unqualified_classification_source_refused_without_state(self):
        with self.assertRaises(ValueError):
            bk.cooldown_feedback('acct-a', 1800, 'http_429',
                                 classification_source='agent_prose')
        with self.assertRaises(ValueError):
            bk.cooldown_feedback('acct-a', 1800, 'http_429',
                                 classification_source='codex_error_enum ',
                                 receipt_path=str(self.new_receipt_path()))
        self.assertIsNone(self.cooldown_line('acct-a'))
        self.assertFalse(self.new_receipt_path().exists())
        self.assertEqual([], bk._read_429count('acct-a'))

    def test_unknown_account_refused_before_any_state(self):
        with self.assertRaises(SystemExit) as caught:
            bk.cooldown_feedback('nope', 1800, 'http_429',
                                 receipt_path=str(self.new_receipt_path()))
        self.assertEqual(2, caught.exception.code)
        self.assertIsNone(self.cooldown_line('nope'))
        self.assertFalse(self.new_receipt_path().exists())


class CooldownReceiptCli(FixtureRoot):
    """End-to-end CLI custody: the helper process writes its own receipt."""

    def setUp(self):
        super().setUp()
        self.cli_dir = self.root / 'cli'
        self.cli_dir.mkdir()
        shutil.copyfile(CANDIDATE_DIR / 'bailian_keys.py',
                        self.cli_dir / 'bailian_keys.py')
        (self.cli_dir / 'bailian_policy.json').write_text(json.dumps(FIXTURE_POLICY))
        self.clihome = self.root / 'clihome'
        (self.clihome / '.bailian').mkdir(parents=True)
        (self.clihome / '.bailian' / 'config.json').write_text(json.dumps(
            {'token-plan': {'api_keys': [
                {'name': name, 'api_key': value}
                for name, value in FIXTURE_KEYS.items()]}}))

    def cli_env(self, **over):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('LANE_', 'POOL_', 'BAILIAN_',
                                      'REMOTE_SUB_'))}
        env['HOME'] = str(self.clihome)
        env.update(over)
        return env

    def cli(self, *args, **envover):
        return subprocess.run(
            guarded_python_file(self.cli_dir / 'bailian_keys.py', args),
            env=self.cli_env(**envover), capture_output=True, text=True,
            timeout=60)

    def cli_cooldown_line(self, name):
        path = self.cli_dir / 'slots' / 'bailian' / f'{name}.cooldown'
        return path.read_text().strip() if path.exists() else None

    def test_helper_writes_actual_receipt_for_the_leased_account(self):
        target = self.root / 'cli_receipt.json'
        done = self.cli('cooldown-receipt', 'acct-a', '1800', 'http_429',
                        str(target), 'qwen_wrapper_inference')
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn('qwen_429_receipt written', done.stderr)
        self.assertIn('cooldown name=acct-a seconds=1800 expiry=', done.stdout)
        self.assertTrue(target.exists())
        receipt = json.loads(target.read_text())
        self.assertEqual(FEEDBACK_KEYS, set(receipt))
        self.assertEqual('acct-a', receipt['account'])
        self.assertEqual(120, receipt['duration_seconds'])
        self.assertEqual(receipt['until_ts'],
                         receipt['observed_at'] + receipt['duration_seconds'])
        self.assertEqual('qwen_wrapper_inference',
                         receipt['classification_source'])
        line = self.cli_cooldown_line('acct-a')
        self.assertEqual(str(receipt['until_ts']), line.split()[0])
        self.assertEqual('http_429', line.split()[1])
        self.assertEqual(0o600, stat.S_IMODE(target.stat().st_mode))
        # Credential custody: key values never reach outputs or receipts.
        self.assertNotIn('fixture-value', done.stdout)
        self.assertNotIn('fixture-value', done.stderr)
        self.assertNotIn(b'fixture-value', target.read_bytes())

    def test_leased_mode_requires_the_exact_pool_account(self):
        target = self.root / 'lease_receipt.json'
        refused = self.cli('cooldown-receipt', 'acct-a', '1800', 'http_429',
                           str(target), LANE_LEASED='1', POOL_ACCOUNT='acct-b')
        self.assertEqual(78, refused.returncode, refused.stderr)
        self.assertIn('BAILIAN_RECEIPT_OUTER_ACCOUNT_MISMATCH', refused.stderr)
        self.assertFalse(target.exists())
        self.assertIsNone(self.cli_cooldown_line('acct-a'))
        unbound = self.cli('cooldown-receipt', 'acct-a', '1800', 'http_429',
                           str(target), LANE_LEASED='1')
        self.assertEqual(78, unbound.returncode, unbound.stderr)
        self.assertFalse(target.exists())
        self.assertIsNone(self.cli_cooldown_line('acct-a'))
        matched = self.cli('cooldown-receipt', 'acct-a', '1800', 'http_429',
                           str(target), LANE_LEASED='1', POOL_ACCOUNT='acct-a')
        self.assertEqual(0, matched.returncode, matched.stderr)
        self.assertEqual('acct-a', json.loads(target.read_text())['account'])

    def test_destination_must_be_a_new_absolute_file(self):
        relative = self.cli('cooldown-receipt', 'acct-a', '1800', 'http_429',
                            'relative.json')
        self.assertEqual(2, relative.returncode, relative.stderr)
        self.assertIn('BAILIAN_RECEIPT_DESTINATION_UNQUALIFIED', relative.stderr)
        existing = self.root / 'already.json'
        existing.write_text('x\n')
        occupied = self.cli('cooldown-receipt', 'acct-a', '1800', 'http_429',
                            str(existing))
        self.assertEqual(2, occupied.returncode, occupied.stderr)
        self.assertIsNone(self.cli_cooldown_line('acct-a'))
        self.assertFalse((self.root / 'relative.json').exists())

    def test_non_429_reason_commits_cooldown_but_no_receipt(self):
        target = self.root / 'auth_receipt.json'
        done = self.cli('cooldown-receipt', 'acct-a', '86400', 'invalid_api_key',
                        str(target))
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn('qwen_429_receipt withheld', done.stderr)
        self.assertFalse(target.exists())
        self.assertEqual('invalid_api_key',
                         self.cli_cooldown_line('acct-a').split()[1])

    def test_bad_classification_source_refused_without_state(self):
        target = self.root / 'prose_receipt.json'
        done = self.cli('cooldown-receipt', 'acct-a', '1800', 'http_429',
                        str(target), 'model_prose')
        self.assertEqual(2, done.returncode, done.stderr)
        self.assertIn('BAILIAN_RECEIPT_SOURCE_UNQUALIFIED', done.stderr)
        self.assertFalse(target.exists())
        self.assertIsNone(self.cli_cooldown_line('acct-a'))


def meta_event(session='sess-fixture-0001'):
    return {'type': 'session_meta', 'payload': {'id': session}}


def typed_error(info):
    return {'type': 'event_msg',
            'payload': {'type': 'error', 'codex_error_info': info}}


class QwenOutcomeFeedback(FixtureRoot):
    """The prospective adapter: typed facts stay typed, inference stays named."""

    def setUp(self):
        super().setUp()
        self.home = self.root / 'codex_home'
        self.last = self.root / 'text.txt'
        self.target = self.root / 'outcome.provider.json'

    def test_bound_fixture_restores_all_ambient_environment(self):
        with unittest.mock.patch.dict(os.environ, {
                'PATH': '/fixture/path', 'NON_SCOPE_FIXTURE': 'preserved',
                'POOL_ACCOUNT': 'original-account'}):
            before = dict(os.environ)
            with self.bound_environ(POOL_ACCOUNT='acct-a'):
                self.assertEqual('acct-a', os.environ['POOL_ACCOUNT'])
                self.assertEqual('/fixture/path', os.environ['PATH'])
                os.environ['ONLY_IN_BOUND_FIXTURE'] = 'temporary'
            self.assertEqual(before, dict(os.environ))

    def write_session(self, events, name='rollout-fixture.jsonl'):
        sessions = self.home / 'sessions'
        sessions.mkdir(parents=True, exist_ok=True)
        (sessions / name).write_text(
            ''.join(json.dumps(event) + '\n' for event in events))

    def make_receipt(self, account='acct-a'):
        target = self.root / f'receipt-{account}.json'
        _, receipt = bk.cooldown_feedback(account, 1800, 'http_429',
                                          receipt_path=str(target))
        self.assertIsNotNone(receipt)
        return target, receipt

    def run_codex_main(self, rc='3', feedback=True, last_bytes=None,
                       pass_empty=False, session_events=None,
                       receipt_name='receipt-acct-a.json', **scope):
        """Drive the adapter exactly as the wrapper's outcome block does."""
        if session_events is not None:
            self.write_session(session_events)
        self.last.write_bytes(b'' if last_bytes is None else last_bytes)
        last_arg = self.last
        if pass_empty:
            # The wrapper publishes EMPTY stdout on failure and hands the
            # adapter its empty sidecar, never the private captured tail.
            last_arg = self.root / 'final_stdout_empty'
            last_arg.write_bytes(b'')
        args = [str(self.home), str(rc), 'bailian', 'qwen3.8-flash', str(last_arg)]
        if feedback:
            args.append(str(self.root / receipt_name))
        captured = io.StringIO()
        with self.bound_environ(**scope):
            with contextlib.redirect_stderr(captured):
                code = po.codex_main(args)
        self.assertEqual(0, code)
        if self.target.exists():
            return json.loads(self.target.read_text()), captured.getvalue()
        return None, captured.getvalue()

    def test_typed_rate_limit_joins_actual_helper_receipt(self):
        _, expected = self.make_receipt()
        outcome, _ = self.run_codex_main(
            rc='3',
            session_events=[meta_event(), typed_error('rate_limit_exceeded'),
                            {'type': 'turn_context',
                             'payload': {'cwd': '/tmp'}}])
        self.assertIsNotNone(outcome)
        # Retain the actual typed diagnostic separately from inferred policy.
        self.assertEqual('unknown', outcome['kind'])
        self.assertFalse(outcome['initial_rejection'])
        self.assertEqual('rate_limit', outcome['qwen_cli_kind'])
        self.assertTrue(outcome['qwen_cli_initial_rejection'])
        self.assertEqual(3, outcome['command_rc'])
        self.assertIsNone(outcome['api_status'])
        self.assertIsNone(outcome['reset_at'])
        self.assertIsNone(outcome['reset_source'])
        self.assertEqual(po.digest(b''), outcome['stdout_sha256'])
        # The exact 10-field frozen interface joins the outcome unchanged.
        self.assertEqual(OUTCOME_FIXED_KEYS | {'qwen_policy_feedback', 'qwen_cli_kind', 'qwen_cli_initial_rejection'},
                         set(outcome) - OUTCOME_ENVELOPE_KEYS)
        self.assertEqual(expected, outcome['qwen_policy_feedback'])
        # Typed enum and labeled wrapper inference stay distinct provenance.
        self.assertEqual('qwen_wrapper_inference',
                         outcome['qwen_policy_feedback']['classification_source'])
        self.assertEqual('bailian', outcome['provider'])
        self.assertEqual('acct-a', outcome['account'])
        self.assertEqual('run-fixture-0001', outcome['run_id'])
        self.assertEqual(0o600, stat.S_IMODE(self.target.stat().st_mode))

    def test_failure_binds_empty_stdout_not_a_captured_tail(self):
        self.make_receipt()
        outcome, _ = self.run_codex_main(
            rc='1', last_bytes=b'STATUS: BLOCKED\n', pass_empty=True,
            session_events=[meta_event(), typed_error({'http': 429})])
        self.assertIsNotNone(outcome)
        self.assertEqual(po.digest(b''), outcome['stdout_sha256'])
        # A non-string codex_error_info is not a typed enum, so the kind stays
        # UNKNOWN even though the labeled inference receipt is attached.
        self.assertEqual('unknown', outcome['kind'])
        self.assertFalse(outcome['initial_rejection'])
        self.assertEqual('qwen_wrapper_inference',
                         outcome['qwen_policy_feedback']['classification_source'])

    def test_success_stdout_binds_and_never_carries_feedback(self):
        self.make_receipt()
        outcome, _ = self.run_codex_main(
            rc='0', last_bytes=b'STATUS: COMPLETE\n',
            session_events=[meta_event(),
                            {'type': 'response_item',
                             'payload': {'type': 'message', 'role': 'assistant',
                                         'content': [{'type': 'text',
                                                      'text': 'done'}]}}])
        self.assertIsNotNone(outcome)
        self.assertEqual('success', outcome['kind'])
        self.assertEqual(po.digest(b'STATUS: COMPLETE\n'),
                         outcome['stdout_sha256'])
        self.assertNotIn('qwen_policy_feedback', outcome)
        self.assertNotIn('PROVIDER_FEEDBACK_WITHHELD', _)

    def test_missing_receipt_keeps_unknown_without_feedback(self):
        outcome, stderr = self.run_codex_main(
            rc='3', feedback=True,
            session_events=[meta_event(), {'type': 'turn_context',
                                           'payload': {'cwd': '/tmp'}}])
        self.assertIsNotNone(outcome)
        self.assertEqual('unknown', outcome['kind'])
        self.assertFalse(outcome['initial_rejection'])
        self.assertNotIn('qwen_policy_feedback', outcome)
        self.assertEqual('', stderr)

    def test_wrapper_prose_is_never_http_proof(self):
        self.make_receipt()
        outcome, _ = self.run_codex_main(
            rc='3',
            session_events=[
                meta_event(),
                {'type': 'response_item',
                 'payload': {'type': 'message', 'role': 'assistant',
                             'content': [{'type': 'text',
                                          'text': 'HTTP 429 too many '
                                                  'requests'}]}},
                typed_error({'http': 429})])
        self.assertIsNotNone(outcome)
        # A non-string codex_error_info is not a typed enum, and assistant
        # prose mentioning 429 proves nothing about HTTP status: the kind and
        # HTTP-shaped fields stay untouched while the inference stays labeled.
        self.assertEqual('unknown', outcome['kind'])
        self.assertFalse(outcome['initial_rejection'])
        self.assertIsNone(outcome['api_status'])
        self.assertIsNone(outcome['reset_at'])
        self.assertIsNone(outcome['reset_source'])
        self.assertEqual('qwen_wrapper_inference',
                         outcome['qwen_policy_feedback']['classification_source'])
        self.assertEqual('429', outcome['qwen_policy_feedback']['classification'])

    def test_typed_auth_conflict_withholds_the_receipt(self):
        self.make_receipt()
        outcome, stderr = self.run_codex_main(
            rc='3', session_events=[meta_event(), typed_error('unauthorized')])
        self.assertIsNotNone(outcome)
        self.assertEqual('authentication', outcome['kind'])
        self.assertNotIn('qwen_policy_feedback', outcome)
        self.assertIn('PROVIDER_FEEDBACK_WITHHELD', stderr)
        self.assertIn('typed_auth_contradicts_inferred_429', stderr)

    def test_foreign_account_receipt_is_withheld(self):
        self.make_receipt('acct-b')
        outcome, stderr = self.run_codex_main(
            rc='3', receipt_name='receipt-acct-b.json',
            session_events=[meta_event(),
                            typed_error('rate_limit_exceeded')])
        self.assertIsNotNone(outcome)
        self.assertEqual('unknown', outcome['kind'])
        self.assertEqual('rate_limit', outcome['qwen_cli_kind'])
        self.assertNotIn('qwen_policy_feedback', outcome)
        self.assertIn('receipt_account_unqualified', stderr)

    def test_unbound_lease_scope_produces_no_outcome(self):
        outcome, stderr = self.run_codex_main(
            rc='3', feedback=False, POOL_LEASE_ID='not a valid ident!!',
            session_events=[meta_event(),
                            typed_error('rate_limit_exceeded')])
        self.assertIsNone(outcome)
        self.assertIn('PROVIDER_OUTCOME_UNAVAILABLE', stderr)

    def test_malformed_receipts_withhold_honestly(self):
        good = dict(self.make_receipt()[1])
        variants = {
            'unparseable': b'not json\n',
            'extra_field': dict(good, unexpected=1),
            'wrong_expiry': dict(good, until_ts=good['until_ts'] + 5),
            'string_duration': dict(good,
                                    duration_seconds=str(good['duration_seconds'])),
            'string_flag': dict(good, soft_cap_enabled='yes'),
            'bad_source': dict(good, classification_source='model_prose'),
            'foreign_account': dict(good, account='acct-b'),
            'bool_time': dict(good, observed_at=True),
        }
        for name, payload in variants.items():
            with self.subTest(variant=name):
                path = self.root / f'bad-{name}.json'
                if isinstance(payload, bytes):
                    path.write_bytes(payload)
                else:
                    path.write_text(json.dumps(payload))
                value, reason = po.load_qwen_feedback(path, 'acct-a')
                self.assertIsNone(value, name)
                self.assertNotEqual('receipt_qualified', reason, name)

    def test_symlinked_or_missing_receipt_never_qualifies(self):
        real = self.root / 'real.json'
        real.write_text(json.dumps(self.make_receipt()[1]))
        link = self.root / 'link.json'
        link.symlink_to(real)
        value, reason = po.load_qwen_feedback(link, 'acct-a')
        self.assertIsNone(value)
        self.assertEqual('receipt_unreadable', reason)
        value, reason = po.load_qwen_feedback(self.root / 'absent.json',
                                              'acct-a')
        self.assertIsNone(value)
        self.assertEqual('receipt_unreadable', reason)
        value, reason = po.load_qwen_feedback(real, 'totally-foreign')
        self.assertIsNone(value)
        self.assertEqual('receipt_account_unqualified', reason)

    def test_mixed_capture_refuses_the_outcome(self):
        self.write_session([meta_event()], name='one.jsonl')
        self.write_session([meta_event()], name='two.jsonl')
        outcome, stderr = self.run_codex_main(rc='3', feedback=False)
        self.assertIsNone(outcome)
        self.assertIn('PROVIDER_OUTCOME_UNAVAILABLE', stderr)
        self.assertFalse(self.target.exists())

    def test_outcome_write_is_one_shot(self):
        self.make_receipt()
        outcome, _ = self.run_codex_main(
            rc='3', session_events=[meta_event(),
                                    typed_error('rate_limit_exceeded')])
        self.assertIsNotNone(outcome)
        before = self.target.read_bytes()
        captured = io.StringIO()
        with self.bound_environ():
            with contextlib.redirect_stderr(captured):
                po.codex_main([str(self.home), '3', 'bailian', 'qwen3.8-flash',
                               str(self.last),
                               str(self.root / 'receipt-acct-a.json')])
        self.assertEqual(before, self.target.read_bytes())
        self.assertIn('PROVIDER_OUTCOME_UNAVAILABLE', captured.getvalue())

    def test_cli_dispatch_five_and_six_argument_forms(self):
        self.make_receipt()
        self.write_session([meta_event(), typed_error('rate_limit_exceeded')])
        self.last.write_bytes(b'')
        with self.bound_environ() as env:
            plain = subprocess.run(
                guarded_python_file(CANDIDATE_DIR / 'provider_outcome.py',
                ['codex', str(self.home), '3', 'bailian', 'qwen3.8-flash', str(self.last)]),
                env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(0, plain.returncode, plain.stderr)
        outcome = json.loads(self.target.read_text())
        self.assertNotIn('qwen_policy_feedback', outcome)
        self.assertEqual('unknown', outcome['kind'])
        self.assertEqual('rate_limit', outcome['qwen_cli_kind'])
        self.target.unlink()
        with self.bound_environ() as env:
            with_receipt = subprocess.run(
                guarded_python_file(CANDIDATE_DIR / 'provider_outcome.py',
                ['codex', str(self.home), '3', 'bailian', 'qwen3.8-flash', str(self.last), str(self.root / 'receipt-acct-a.json')]),
                env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(0, with_receipt.returncode, with_receipt.stderr)
        outcome = json.loads(self.target.read_text())
        self.assertIn('qwen_policy_feedback', outcome)

    def test_actual_producer_fields_join_original_broker_and_never_hard_fallback(self):
        # Real candidate helper/exporter/Broker/SQLite; capture and process
        # receipt are synthetic inert fixture evidence, not a live worker claim.
        import fcntl
        import lease_broker
        import quota_circuit
        for with_feedback in (True, False):
            with self.subTest(feedback=with_feedback), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                config = work / 'accounts.json'
                config.write_text(json.dumps({'providers': {'bailian': {
                    'enabled': True, 'concurrency_cap': 8,
                    'accounts': [{'name': 'acct-a', 'per_account_cap': 8}]}}}))
                br = lease_broker.Broker(db_path=str(work / 'broker.sqlite'),
                    lock_path=str(work / 'broker.lock'), accounts_path=str(config),
                    now_fn=lambda: 1000., check_pid=False, external_gates=False,
                    grok_marker=str(work / 'no-marker'), this_host='fixture-host')
                lease = br.acquire('root-fixture-0001', 'bailian', account='acct-a',
                    model='qwen3.8-flash', host='fixture-host', task_class='fixture', wait=0)
                self.assertTrue(lease.ok)
                self.target.unlink(missing_ok=True)
                if with_feedback:
                    with unittest.mock.patch.object(bk.time, 'time', return_value=1000):
                        self.make_receipt()
                with unittest.mock.patch.object(po.time, 'time', return_value=1000):
                    value, _ = self.run_codex_main(feedback=with_feedback,
                        POOL_LEASE_ID=lease.lease_id,
                        session_events=[meta_event(), typed_error('rate_limit_exceeded')])
                self.assertEqual('unknown', value['kind'])
                self.assertEqual('rate_limit', value['qwen_cli_kind'])
                self.assertFalse(value['initial_rejection'])
                self.assertIsNone(value['api_status'])
                process = dict(schema='mastermind.local_owned_process_receipt.v1',
                    label=value['run_id'], returncode=3, stdout_sha256=po.digest(b''),
                    stdout_truncated=False, stderr_truncated=False, timed_out=False,
                    cleanup=dict(census_proven=True, identity_verified=True,
                        residual_count=0, status='not_needed'))
                pp = work / 'process.json'; pp.write_text(json.dumps(process))
                lock = br._lock()
                try:
                    conn = br._conn()
                    try:
                        result = quota_circuit.observe_locked(br, conn, lease.lease_id,
                            lease.orchestrator_id, value['run_id'], self.target, pp)
                        rows = [dict(r) for r in conn.execute('SELECT * FROM quota_cooldowns')]
                        if with_feedback:
                            self.assertEqual(1, len(rows))
                            self.assertEqual(('SOFT', 1120, 3),
                                (rows[0]['mode'], rows[0]['until_ts'], rows[0]['soft_cap']))
                        else:
                            self.assertEqual([], rows)
                        again = quota_circuit.observe_locked(br, conn, lease.lease_id,
                            lease.orchestrator_id, value['run_id'], self.target, pp)
                        self.assertTrue(again['duplicate'])
                        bad = dict(value); bad['qwen_cli_kind'] = 'quota_exhausted'
                        self.target.write_text(json.dumps(bad))
                        with self.assertRaisesRegex(ValueError, 'terminal_observation_conflict'):
                            quota_circuit.observe_locked(br, conn, lease.lease_id,
                                lease.orchestrator_id, value['run_id'], self.target, pp)
                    finally:
                        conn.close()
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN); lock.close()

    def test_typed_quota_and_claimed_enum_conflicts_withhold_policy_feedback(self):
        self.make_receipt()
        value, diagnostic = self.run_codex_main(
            session_events=[meta_event(), typed_error('UsageLimitExceeded')])
        self.assertEqual('unknown', value['kind'])
        self.assertEqual('quota_exhausted', value['qwen_cli_kind'])
        self.assertNotIn('qwen_policy_feedback', value)
        self.assertIn('typed_quota_contradicts', diagnostic)
        self.target.unlink()
        receipt = self.root / 'receipt-acct-a.json'
        data = json.loads(receipt.read_text())
        data['classification_source'] = 'codex_error_enum'
        receipt.write_text(json.dumps(data))
        value, diagnostic = self.run_codex_main(
            session_events=[meta_event(), typed_error({'http': 429})])
        self.assertEqual('unknown', value['kind'])
        self.assertNotIn('qwen_policy_feedback', value)
        self.assertIn('typed_rate_limit_unconfirmed', diagnostic)

    def test_known_noncapacity_terminal_cannot_create_soft_or_hard_broker_hold(self):
        # Actual helper/exporter/Broker/SQLite, with inert capture/process DATA.
        # The helper's existing local policy event is retained; exporter and
        # Broker must not turn incompatible inferred prose into another hold.
        import fcntl
        import lease_broker
        import quota_circuit
        cases = {name: kind for name, kind in po.CODEX_ERRORS.items()
                 if kind in {'context_limit', 'budget_limit', 'provider_error',
                             'invalid_request', 'permission'}}
        self.assertTrue({'ContextWindowExceeded', 'SessionBudgetExceeded'} <= cases.keys())
        for enum, kind in cases.items():
            with self.subTest(enum=enum), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                config = work / 'accounts.json'
                config.write_text(json.dumps({'providers': {'bailian': {
                    'enabled': True, 'concurrency_cap': 8,
                    'accounts': [{'name': 'acct-a', 'per_account_cap': 8}]}}}))
                br = lease_broker.Broker(db_path=str(work / 'broker.sqlite'),
                    lock_path=str(work / 'broker.lock'), accounts_path=str(config),
                    now_fn=lambda: 1000., check_pid=False, external_gates=False,
                    grok_marker=str(work / 'no-marker'), this_host='fixture-host')
                lease = br.acquire('root-fixture-0001', 'bailian', account='acct-a',
                    model='qwen3.8-flash', host='fixture-host', task_class='fixture', wait=0)
                self.assertTrue(lease.ok)
                self.target.unlink(missing_ok=True)
                receipt_path = self.root / 'receipt-acct-a.json'
                receipt_path.unlink(missing_ok=True)
                with unittest.mock.patch.object(bk.time, 'time', return_value=1000):
                    self.make_receipt()
                local_before = self.cooldown_line('acct-a')
                receipt_before = receipt_path.read_bytes()
                with unittest.mock.patch.object(po.time, 'time', return_value=1000):
                    value, diagnostic = self.run_codex_main(
                        POOL_LEASE_ID=lease.lease_id,
                        session_events=[meta_event(), typed_error(enum)])
                self.assertEqual(kind, value['kind'])
                self.assertNotIn('qwen_policy_feedback', value)
                self.assertIn('typed_terminal_contradicts_inferred_429', diagnostic)
                self.assertIsNone(value['api_status'])
                process = dict(schema='mastermind.local_owned_process_receipt.v1',
                    label=value['run_id'], returncode=3, stdout_sha256=po.digest(b''),
                    stdout_truncated=False, stderr_truncated=False, timed_out=False,
                    cleanup=dict(census_proven=True, identity_verified=True,
                        residual_count=0, status='not_needed'))
                pp = work / 'process.json'; pp.write_text(json.dumps(process))
                lock = br._lock()
                try:
                    conn = br._conn()
                    try:
                        quota_circuit.observe_locked(br, conn, lease.lease_id,
                            lease.orchestrator_id, value['run_id'], self.target, pp)
                        self.assertEqual([], list(conn.execute('SELECT * FROM quota_cooldowns')))
                    finally:
                        conn.close()
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN); lock.close()
                self.assertEqual(local_before, self.cooldown_line('acct-a'))
                self.assertEqual(receipt_before, receipt_path.read_bytes())

    def test_other_provider_codex_capacity_projection_is_unchanged(self):
        self.write_session([meta_event(), typed_error('rate_limit_exceeded')])
        self.last.write_bytes(b'')
        with self.bound_environ():
            po.codex_main([str(self.home), '3', 'minimax', 'fixture-model', str(self.last)])
        value = json.loads(self.target.read_text())
        self.assertEqual('rate_limit', value['kind'])
        self.assertTrue(value['initial_rejection'])
        self.assertNotIn('qwen_cli_kind', value)
        self.assertNotIn('qwen_policy_feedback', value)

    def test_generic_claude_parse_is_unchanged(self):
        raw = json.dumps({
            'type': 'result', 'subtype': 'success', 'is_error': False,
            'result': 'ok', 'session_id': 'sess-claude-1', 'num_turns': 1,
        }).encode()
        display, fields, final = po.parse_claude(raw, 0)
        self.assertEqual('success', fields['kind'])
        self.assertIsNone(fields['api_status'])
        self.assertFalse(fields['initial_rejection'])
        display, fields, final = po.parse_claude(b'', 75)
        self.assertEqual('unknown', fields['kind'])
        # An old plain-text responder diagnostic stays display-only evidence.
        display, fields, final = po.parse_claude(
            b'gateway 429 too many requests', 1)
        self.assertEqual('unknown', fields['kind'])
        self.assertIsNone(fields['api_status'])
        self.assertIsNone(fields['reset_at'])
        self.assertIsNone(fields['reset_source'])


class WrapperScriptStaticCheck(unittest.TestCase):
    """Static custody wiring only. Behavior of the real wrapper stays with the
    parent's integrated owned-process fixtures; nothing here launches it."""

    def test_wrapper_script_parses_and_keeps_receipt_inside_private_workdir(self):
        script = CANDIDATE_DIR / 'qwen_exec.sh'
        done = subprocess.run(guarded_bash_syntax(script),
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(0, done.returncode, done.stderr)
        text = script.read_text()
        self.assertIn('FEEDBACK_FILE="$WORKDIR/qwen_429_feedback.json"', text)
        self.assertIn('cooldown-receipt "$NAME" "$SECS" "$REASON"'
                      ' "$FEEDBACK_FILE" qwen_wrapper_inference', text)
        self.assertIn('"$HERE/provider_outcome.py" codex "$CODEX_RUN_HOME"'
                      ' "$FINAL_RC" bailian "$MODEL" "$FINAL_STDOUT_FILE"'
                      ' "$FEEDBACK_FILE"', text)


if __name__ == '__main__':
    unittest.main()
