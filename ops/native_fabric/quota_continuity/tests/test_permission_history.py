"""Regression for successful CLI completions with historical tool denials.

All streams and identities are synthetic. No provider, broker, installed home,
worker, credential or network is used. A CLI completion is never acceptance.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'candidate'), str(ROOT / 'source')]
import provider_outcome as outcome


def completed(denials=2):
    return [
        {'type': 'system', 'subtype': 'init'},
        {'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'name': 'Bash', 'id': 'fixture-tool'}]}},
        {'type': 'user', 'message': {'content': [
            {'type': 'tool_result', 'tool_use_id': 'fixture-tool',
             'is_error': True, 'content': 'PRIVATE_DENIAL_DETAIL'}]}},
        {'type': 'result', 'subtype': 'success', 'is_error': False,
         'terminal_reason': 'completed', 'num_turns': 62,
         'session_id': 'fixture-session', 'result': 'Return ready for parent review.',
         'permission_denials': [{'tool_name': 'Bash',
                                'tool_input': {'command': 'PRIVATE_COMMAND'}}
                               for _ in range(denials)]},
    ]


class PermissionHistory(unittest.TestCase):
    def parse(self, rows, rc=0, lines=False):
        raw = (''.join(json.dumps(row) + '\n' for row in rows).encode()
               if lines else json.dumps(rows).encode())
        return outcome.parse_claude(raw, rc)

    def test_completed_cli_is_not_failed_by_historical_denials(self):
        for lines in (False, True):
            with self.subTest(stream_json=lines):
                display, fields, final = self.parse(completed(), lines=lines)
                self.assertEqual(fields['kind'], 'success')
                self.assertEqual(fields['command_rc'], 0)
                self.assertEqual(fields['permission_denial_count'], 2)
                self.assertEqual(fields['permission_denials_role'], 'historical_nonterminal')
                self.assertEqual(fields['cli_subtype'], 'success')
                self.assertEqual(fields['cli_terminal_reason'], 'completed')
                self.assertFalse(fields['initial_rejection'])
                self.assertEqual(display, 'Return ready for parent review.\n')
                self.assertIsNotNone(final)
                self.assertNotIn('PRIVATE_', json.dumps(fields) + display)

    def test_success_without_optional_terminal_reason(self):
        rows = completed(); rows[-1].pop('terminal_reason')
        self.assertEqual(self.parse(rows)[1]['kind'], 'success')

    def test_real_failed_cli_keeps_permission_failure(self):
        for rc, patch in [
            (1, {}), (0, {'is_error': True}),
            (0, {'subtype': 'error_during_execution'}),
            (0, {'terminal_reason': 'stop_hook_prevented'}),
            (0, {'terminal_reason': 'hook_stopped'}),
            (0, {'terminal_reason': 'unknown_future_terminal'}),
            (0, {'api_error_status': 403}),
            (0, {'errors': ['provider-owned terminal error']}),
            (0, {'is_error': 0}),
        ]:
            with self.subTest(rc=rc, patch=patch):
                rows = completed(); rows[-1].update(patch)
                fields = self.parse(rows, rc)[1]
                self.assertNotEqual(fields['kind'], 'success')
                self.assertFalse(fields['initial_rejection'])

    def test_prior_structured_provider_error_is_not_suppressed(self):
        rows = completed()
        rows.insert(1, {'type': 'assistant', 'error': 'authentication_failed'})
        self.assertNotEqual(self.parse(rows)[1]['kind'], 'success')

    def test_incomplete_or_ambiguous_capture_is_not_success(self):
        for kind in ('duplicate_result', 'post_result_event', 'malformed_denials'):
            with self.subTest(kind=kind):
                rows = completed()
                if kind == 'duplicate_result': rows.append(deepcopy(rows[-1]))
                if kind == 'post_result_event': rows.append({'type': 'unknown_future_event'})
                if kind == 'malformed_denials': rows[-1]['permission_denials'] = 'denied'
                self.assertNotEqual(self.parse(rows)[1]['kind'], 'success')
                self.assertFalse(self.parse(rows)[1]['initial_rejection'])

    def test_no_denial_history_is_explicit_without_new_authority(self):
        fields = self.parse(completed(0))[1]
        self.assertEqual(fields['kind'], 'success')
        self.assertEqual(fields['permission_denial_count'], 0)
        self.assertEqual(fields['permission_denials_role'], 'none')
        self.assertNotIn('accepted', fields)
        self.assertNotIn('retry_authorized', fields)

    def test_real_wrapper_does_not_rewrite_zero_exit_to_permission_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = root / 'capture.jsonl'
            capture.write_text(''.join(json.dumps(row) + '\n' for row in completed()))
            target = root / 'fixture-run.provider.json'
            env = {'PATH': os.environ.get('PATH', ''), 'HOME': directory,
                   'POOL_OUTCOME_FILE': str(target),
                   'REMOTE_SUB_RUN_ID': 'fixture-run', 'POOL_LEASE_ID': 'fixture-lease',
                   'POOL_ACCOUNT': 'fixture-account', 'POOL_ORCHESTRATOR_ID': 'fixture-root',
                   'LANE_REMOTE_HOST': 'fixture-host'}
            result = subprocess.run(
                [sys.executable, str(ROOT / 'candidate/provider_outcome.py'),
                 'claude', str(capture), '0', 'glm', 'fixture-model'],
                env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('PROVIDER_TERMINAL kind=permission', result.stdout + result.stderr)
            receipt = json.loads(target.read_text())
            self.assertEqual(receipt['kind'], 'success')
            self.assertEqual(receipt['command_rc'], 0)
            self.assertEqual(receipt['cli_command_rc'], 0)
            self.assertEqual(receipt['permission_denial_count'], 2)
            self.assertFalse(receipt['initial_rejection'])
            self.assertNotIn('PRIVATE_', target.read_text() + result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
