"""Per-request turn ceilings, using the real adapter and existing shell profile.

Routing and transport are inert. Shell cases execute only the profile function;
no installed state, provider, credential, worker or lease is touched.
"""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_adapter_continuity as fixture

api = fixture.api
ROOT = fixture.ROOT


class RequestTurnBudget(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.calls = []
        self.routes = []
        self.mode = 'glm'
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        def route(task_class, **options):
            self.routes.append(options)
            return f'POOL={self.mode} MODEL=fixture-model HOST=fixture MODE={self.mode}'
        def transport(argv, env):
            self.calls.append((argv, dict(env)))
            return SimpleNamespace(returncode=0)
        for target, name, replacement in (
            (api, 'HERE', self.root),
            (api.pick, 'format_pick', route),
            (api.pick, 'launch_policy', lambda *a, **k: {'allowed': True}),
            (api.subprocess, 'run', transport),
        ):
            p = patch.object(target, name, replacement)
            p.start()
            self.addCleanup(p.stop)

    def request(self, **kwargs):
        return api.request('fixture-run', 'mechanical', cwd='~', packet=None,
                           stdin_bytes=b'bounded assignment\n', root_id='fixture-root',
                           parent_run_id='fixture-parent',
                           task_complexity='C0_MECHANICAL', **kwargs)

    def test_valid_request_reaches_existing_profile_without_raising_ambient_limit(self):
        os.environ['POOL_MAX_TURNS'] = '8'
        self.assertEqual(self.request(max_turns=25), 0)
        env = self.calls[0][1]
        self.assertEqual(env['POOL_REQUEST_MAX_TURNS'], '25')
        self.assertEqual(env['POOL_MAX_TURNS'], '8')
        self.assertEqual(self.routes[0]['required_modes'], ['glm', 'minimax'])
        retained = json.loads((self.root / 'state/remote_sub/fixture-run.request.json').read_text())
        self.assertEqual(retained['max_turns'], 25)
        self.assertEqual(env['POOL_ORCHESTRATOR_ID'], 'fixture-root')
        self.assertEqual(env['POOL_PARENT_RUN_ID'], 'fixture-parent')

    def test_invalid_request_refused_before_retention_routing_or_transport(self):
        for value in (0, -1, 401, True, False, 25.5, '25'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(api.FabricTaskError, 'MAX_TURNS_INVALID'):
                    self.request(max_turns=value)
                self.assertFalse((self.root / 'state').exists())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.routes, [])

    def test_absent_request_preserves_legacy_profile_but_not_inherited_request_cap(self):
        os.environ.update(POOL_MAX_TURNS='11', POOL_REQUEST_MAX_TURNS='1')
        self.assertEqual(self.request(), 0)
        self.assertEqual(self.calls[0][1]['POOL_MAX_TURNS'], '11')
        self.assertNotIn('POOL_REQUEST_MAX_TURNS', self.calls[0][1])
        self.assertNotIn('required_modes', self.routes[0])
        retained = json.loads((self.root / 'state/remote_sub/fixture-run.request.json').read_text())
        self.assertNotIn('max_turns', retained)

    def test_unqualified_route_cannot_silently_ignore_ceiling(self):
        self.mode = 'qwen'
        with self.assertRaisesRegex(api.FabricTaskError, 'MAX_TURNS_ROUTE_UNSUPPORTED'):
            self.request(max_turns=25)
        self.assertEqual(self.calls, [])
        state = self.root / 'state/remote_sub'
        self.assertFalse((state / 'fixture-run.request-launch.json').exists())
        refused = json.loads((state / 'fixture-run.request-refused.json').read_text())
        self.assertIs(refused['launch_attempted'], False)

    def test_cli_forwards_explicit_ceiling(self):
        with patch.object(api, 'request', return_value=0) as requested:
            stream = SimpleNamespace(buffer=io.BytesIO(b'assignment'))
            with patch.object(api.sys, 'stdin', stream):
                self.assertEqual(api.main(['request', '--id', 'cli-fixture', '--class',
                    'mechanical', '--stdin', '--max-turns', '25']), 0)
        self.assertEqual(requested.call_args.kwargs['max_turns'], 25)


class ExistingShellProfile(unittest.TestCase):
    def profile(self, *, requested=None, incumbent=None, pool='glm', model='glm-5.3'):
        text = (ROOT / 'candidate/sub.sh').read_text()
        body = text.split('CLAUDE_WORKER_MAX_TURNS=120\n', 1)[1]
        body = body.split('\n}\n', 1)[0] + '\n}\n'
        script = 'CLAUDE_WORKER_MAX_TURNS=120\n' + body
        script += '\n_claude_worker_profile "$1" "$2" || exit $?\nprintf "%s\\n" "$CLAUDE_WORKER_MAX_TURNS"\n'
        env = {'PATH': '/usr/bin:/bin', 'POOL_TASK_COMPLEXITY': 'C0_MECHANICAL'}
        if requested is not None:
            env['POOL_REQUEST_MAX_TURNS'] = str(requested)
        if incumbent is not None:
            env['POOL_MAX_TURNS'] = str(incumbent)
        return subprocess.run(['/bin/bash', '-c', script, 'fixture', pool, model],
                              env=env, text=True, capture_output=True, timeout=5)

    def test_request_only_tightens_existing_limits(self):
        for requested, incumbent, expected in ((25, None, 25), (400, None, 120),
                (25, 8, 8), (25, 200, 25), (400, 400, 400), (1, None, 1)):
            with self.subTest(requested=requested, incumbent=incumbent):
                result = self.profile(requested=requested, incumbent=incumbent)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), str(expected))

    def test_absent_ceiling_preserves_default_profiles(self):
        for pool, model, expected in (('glm', 'glm-5.3', 120),
                                     ('glm', 'glm-5.3-flash', 240),
                                     ('minimax', 'MiniMax-M3', 240)):
            with self.subTest(pool=pool, model=model):
                result = self.profile(pool=pool, model=model)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), str(expected))

    def test_malformed_request_or_incumbent_is_not_sanitized_into_a_grant(self):
        for value in ('0', '-1', '401', '1.5', 'bad'):
            with self.subTest(requested=value):
                self.assertNotEqual(self.profile(requested=value).returncode, 0)
        self.assertNotEqual(self.profile(requested=25, incumbent='bad').returncode, 0)

    def test_existing_transport_explicitly_relays_the_request_ceiling(self):
        result = subprocess.run([sys.executable,
            str(ROOT / 'candidate/remote_sub_helpers.py'), 'routing-env'],
            env={'PATH': '/usr/bin:/bin', 'POOL_REQUEST_MAX_TURNS': '25'},
            text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('POOL_REQUEST_MAX_TURNS=25', result.stdout)


class ContinuationTurnBudget(unittest.TestCase):
    def setUp(self):
        import test_foreground_continuation as foreground_fixture
        self.f = foreground_fixture.Foreground(
            methodName='test_quota_then_success_keeps_exact_attempt_and_effective_identity')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.api.validate_request_max_turns = api.validate_request_max_turns

    def test_proven_pretask_successor_keeps_original_ceiling_and_deadline(self):
        self.assertEqual(self.f.run_owner(max_turns=25), 0)
        self.assertEqual(len(self.f.calls), 2)
        for run, task_class, options in self.f.calls:
            self.assertEqual(options['max_turns'], 25)
            self.assertEqual(options['root_id'], 'root')
            self.assertEqual(options['parent_run_id'], 'parent')
        self.assertEqual(len({kw['request_deadline_ns'] for _, _, kw in self.f.calls}), 1)
        retained = json.loads(self.f.path('origin', '.continuation-request.json').read_text())
        self.assertEqual(retained['max_turns'], 25)
        self.assertFalse(retained['background_execution'])

    def test_invalid_ceiling_precedes_continuation_intent_and_worker(self):
        with self.assertRaisesRegex(api.FabricTaskError, 'MAX_TURNS_INVALID'):
            self.f.run_owner(max_turns=401)
        self.assertEqual(self.f.calls, [])
        self.assertFalse(self.f.path('origin', '.continuation-request.json').exists())

    def test_turn_exhaustion_does_not_become_quota_retry(self):
        original = self.f.api.request
        def limited(run, task_class, **options):
            original(run, task_class, **options)
            self.f.statuses[run].update(rc=1, signal='other')
            return 1
        self.f.api.request = limited
        self.assertEqual(self.f.run_owner(max_turns=25), 1)
        self.assertEqual(len(self.f.calls), 1)
        self.assertFalse(self.f.path('origin', '.successor.json').exists())


if __name__ == '__main__':
    unittest.main()
