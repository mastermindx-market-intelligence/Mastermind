"""Behavioral boundaries for the Paperclip/T3 native transport."""
import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

from integrations.paperclip_teamlink.native_port import Port, process_snapshot, sanitized
from integrations.session_bridge.t3_native_client import Rejected, Scope


CONFIG = {'nativeCliPath': '/installed/native/bin.mjs', 'nodePath': '/installed/node',
          't3Home': '/home/operator/.t3', 'environmentId': 'environment',
          'projectIds': ['project'], 't3Port': 3773}


class NativePortTests(unittest.TestCase):
    def test_child_census_never_consumes_child_transcript(self):
        class Client:
            scope = Scope('connection', 'environment', 'project')

            async def list_threads(self, **kwargs):
                self.included = kwargs
                return {'threads': [{'threadId': 'child', 'parentThreadId': 'parent'}], 'nextCursor': None}

            async def read(self, *_args, **_kwargs):
                raise AssertionError('child transcript must never be read')

        with self.assertRaises(Rejected):
            asyncio.run(Port(CONFIG).root(Client(), 'child'))

    def test_unknown_root_relationship_is_not_guessed(self):
        class Client:
            scope = Scope('connection', 'environment', 'project')

            async def list_threads(self, **_kwargs):
                return {'threads': [{'threadId': 'unknown'}], 'nextCursor': None}

        with self.assertRaises(Rejected):
            asyncio.run(Port(CONFIG).root(Client(), 'unknown'))

    def test_permission_responses_are_not_in_the_port_surface(self):
        with self.assertRaises(Rejected):
            Port(CONFIG).tool('t3_pending_request', {'action': 'respond', 'requestId': 'question'})

    def test_process_failure_is_unavailable_not_an_empty_healthy_machine(self):
        with patch('integrations.paperclip_teamlink.native_port.subprocess.run', side_effect=OSError()):
            result = process_snapshot(3773)
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['processes'])

    def test_process_projection_is_only_listener_descendants_and_omits_arguments(self):
        root = subprocess.CompletedProcess([], 0, stdout='100\n')
        processes = subprocess.CompletedProcess([], 0, stdout=(
            '100 1 Tue Nov 10 00:00:00 2026 01:00 0.2 0.1 /Applications/T3.app/T3\n'
            '101 100 Tue Nov 10 00:00:00 2026 00:30 0.1 0.1 /bin/provider\n'
            '900 1 Tue Nov 10 00:00:00 2026 00:20 0.0 0.1 /bin/unrelated\n'))
        with patch('integrations.paperclip_teamlink.native_port.subprocess.run', side_effect=[root, processes]) as call:
            result = process_snapshot(3773)
        self.assertEqual({x['pid'] for x in result['processes']}, {100, 101})
        self.assertEqual(result['processes'][0]['executable'], 'T3')
        self.assertNotIn('args', json.dumps(call.call_args_list))
        self.assertNotIn('command', result['processes'][0])

    def test_malformed_native_stdout_is_not_recovered_by_stripping_diagnostics(self):
        response = subprocess.CompletedProcess([], 0, stdout='Warning\n{"structuredContent":{}}', stderr='')
        with patch('integrations.paperclip_teamlink.native_port.subprocess.run', return_value=response):
            with self.assertRaises(ValueError):
                Port(CONFIG).cli(['native-catalog'])

    def test_native_stderr_does_not_leak_credentials(self):
        response = subprocess.CompletedProcess([], 1, stdout='', stderr='authorization=very-private-token')
        with patch('integrations.paperclip_teamlink.native_port.subprocess.run', return_value=response):
            with self.assertRaises(Exception) as error:
                Port(CONFIG).cli(['native-catalog'])
        self.assertNotIn('very-private-token', str(error.exception))

    def test_common_secret_forms_are_redacted_from_returned_native_text(self):
        text = 'Authorization: Bearer ' + 'a' * 30 + '\nAPI_KEY=' + 'b' * 20
        result = sanitized(text)
        self.assertNotIn('a' * 30, result)
        self.assertNotIn('b' * 20, result)

    @unittest.skipUnless(shutil.which('node'), 'Node is required for the Paperclip worker suite')
    def test_worker_delivery_failure_scenarios(self):
        root = Path(__file__).resolve().parents[1]
        suite = root / 'integrations/paperclip_teamlink/test/teamlink.test.mjs'
        result = subprocess.run([shutil.which('node'), '--test', str(suite)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
