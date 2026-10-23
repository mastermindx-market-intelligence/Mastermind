"""Strict request lower bounds, using only guarded source and disposable state."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'candidate'), str(ROOT / 'source'), str(ROOT / 'tests')]
from _offline_boundary import (acquire, release, guarded_python_file,
                               guarded_prelaunch_shell)

def setUpModule():
    acquire()

def tearDownModule():
    release()

import caller_not_before as bound
import fabric_task
import lease_broker
import remote_sub_helpers

PAST = '1970-01-01T00:00:01Z'
WITNESS = '2026-10-23T00:47:19.721Z'
CUTOFF = 1792716439721000000
FUTURE = '9999-12-31T23:59:59.999999Z'


class ClockContract(unittest.TestCase):
    def test_before_equality_after_and_exact_fractional_witness(self):
        with self.assertRaises(bound.CallerNotBeforePending) as caught:
            bound.require_not_before(WITNESS, now_ns=CUTOFF - 1)
        self.assertEqual(WITNESS, caught.exception.eligible_at)
        self.assertEqual(WITNESS, bound.require_not_before(WITNESS, now_ns=CUTOFF))
        self.assertEqual(WITNESS, bound.require_not_before(WITNESS, now_ns=CUTOFF + 1))

    def test_absence_has_no_new_clock_obligation(self):
        with mock.patch.object(bound.time, 'time_ns', side_effect=AssertionError('clock')):
            self.assertIsNone(bound.require_not_before(None))

    def test_malformed_never_coerces_or_admits(self):
        for value in ('', False, True, 0, 1.0, float('nan'), float('inf'), {},
                      '2026-10-23T00:47:19', '2026-10-23T00:47:19+00:00',
                      '2026-02-30T00:00:00Z', '2026-10-23T00:47:60Z',
                      '2026-10-23T00:47:19.1234567Z', WITNESS + '\n'):
            with self.subTest(value=repr(value)), self.assertRaises(bound.CallerNotBeforeInvalid):
                bound.require_not_before(value)
        for clock in (-1, False, 1.0, float('nan')):
            with self.subTest(clock=repr(clock)), self.assertRaises(bound.CallerNotBeforeInvalid):
                bound.require_not_before(PAST, now_ns=clock)


class RequestContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = mock.patch.object(fabric_task, 'HERE', self.root)
        self.patch.start(); self.addCleanup(self.patch.stop)

    def request(self, run, **kwargs):
        return fabric_task.request(run, 'mechanical', cwd='~', packet=None,
            stdin_bytes=b'fixture source work', root_id='fixture-root',
            parent_run_id='fixture-parent', **kwargs)

    def test_future_bound_retained_before_route_and_never_launches_or_sleeps(self):
        with (mock.patch.object(fabric_task.pick, 'format_pick', side_effect=AssertionError('route')),
             mock.patch.object(fabric_task.subprocess, 'run', side_effect=AssertionError('process')),
             mock.patch.object(fabric_task.time, 'sleep', side_effect=AssertionError('sleep'))):
            with self.assertRaises(bound.CallerNotBeforePending):
                self.request('fixture-future', not_before=FUTURE)
        directory = self.root / 'state/remote_sub'
        request = json.loads((directory / 'fixture-future.request.json').read_text())
        refused = json.loads((directory / 'fixture-future.request-refused.json').read_text())
        self.assertEqual(FUTURE, request['not_before'])
        self.assertEqual(FUTURE, refused['eligible_at'])
        self.assertFalse(refused['launch_attempted'])
        self.assertEqual(hashlib.sha256((directory / 'fixture-future.request.json').read_bytes()).hexdigest(),
                         refused['request_sha256'])
        self.assertFalse((directory / 'fixture-future.request-launch.json').exists())
        with self.assertRaisesRegex(fabric_task.FabricTaskError, 'ALREADY_EXISTS'):
            self.request('fixture-future', not_before=PAST)

    def test_admitted_bound_is_identical_in_request_launch_argv_and_environment(self):
        with (mock.patch.object(fabric_task.pick, 'format_pick', return_value='POOL=glm HOST=ubuntu2 MODE=glm MODEL=glm-5.3-flash'),
             mock.patch.object(fabric_task.pick, 'launch_policy', return_value={'allowed': True}),
             mock.patch.object(fabric_task.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run):
            self.assertEqual(0, self.request('fixture-past', not_before=PAST))
        argv = run.call_args.args[0]
        self.assertEqual(PAST, argv[argv.index('--not-before') + 1])
        self.assertEqual(PAST, run.call_args.kwargs['env'][bound.ENV])
        directory = self.root / 'state/remote_sub'
        raw = (directory / 'fixture-past.request.json').read_bytes()
        launch = json.loads((directory / 'fixture-past.request-launch.json').read_text())
        self.assertEqual(PAST, launch['not_before'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), launch['request_sha256'])

    def test_omitted_option_clears_inherited_label_and_preserves_old_shapes(self):
        with (mock.patch.dict(os.environ, {bound.ENV: FUTURE}),
             mock.patch.object(fabric_task.pick, 'format_pick', return_value='POOL=glm HOST=ubuntu2 MODE=glm MODEL=glm-5.3-flash'),
             mock.patch.object(fabric_task.pick, 'launch_policy', return_value={'allowed': True}),
             mock.patch.object(fabric_task.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run):
            self.assertEqual(0, self.request('fixture-old'))
        self.assertNotIn(bound.ENV, run.call_args.kwargs['env'])
        self.assertNotIn('--not-before', run.call_args.args[0])
        directory = self.root / 'state/remote_sub'
        for suffix in ('request.json', 'request-launch.json'):
            self.assertNotIn('not_before', json.loads((directory / ('fixture-old.' + suffix)).read_text()))


class BrokerContract(unittest.TestCase):
    def test_cli_refuses_before_constructing_state_owner(self):
        with (mock.patch.object(lease_broker, 'default_broker', side_effect=AssertionError('broker')),
             contextlib.redirect_stdout(io.StringIO()) as out):
            self.assertEqual(75, lease_broker.main(['acquire', '--pool', 'bailian', '--not-before', FUTURE]))
        self.assertIn('eligible_at=' + FUTURE, out.getvalue())

    def test_library_refuses_before_lock_gc_waiter_or_any_database_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / 'accounts.json'
            config.write_text(json.dumps({'providers': {'bailian': {'enabled': True,
                'concurrency_cap': 4, 'accounts': [{'name': 'qa', 'per_account_cap': 4}]}}}))
            br = lease_broker.Broker(db_path=str(root / 'db'), lock_path=str(root / 'lock'),
                accounts_path=str(config), external_gates=False, check_pid=False, this_host='fixture')
            with (mock.patch.object(br, '_lock', side_effect=AssertionError('lock')),
                 mock.patch.object(br, '_gc_locked', side_effect=AssertionError('gc')),
                 mock.patch.object(br, '_conn', side_effect=AssertionError('database'))):
                with self.assertRaises(bound.CallerNotBeforePending):
                    br.acquire('fixture', 'bailian', not_before=FUTURE)
            # A reached bound still requires all incumbent account/lease gates.
            result = br.acquire('fixture', 'bailian', not_before=PAST, wait=0)
            self.assertTrue(result.ok)

    def test_lock_wait_rechecks_bound_before_gc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / 'accounts.json'
            config.write_text(json.dumps({'providers': {'bailian': {'enabled': True,
                'concurrency_cap': 4, 'accounts': [{'name': 'qa', 'per_account_cap': 4}]}}}))
            br = lease_broker.Broker(db_path=str(root / 'db'), lock_path=str(root / 'lock'),
                accounts_path=str(config), external_gates=False, check_pid=False, this_host='fixture')
            with (mock.patch.object(bound.time, 'time_ns', side_effect=[CUTOFF + 1, CUTOFF + 1, CUTOFF - 1]),
                  mock.patch.object(br, '_gc_locked', side_effect=AssertionError('gc'))):
                with self.assertRaises(bound.CallerNotBeforePending):
                    br.acquire('fixture', 'bailian', not_before=WITNESS)



class ControllerContract(unittest.TestCase):
    def test_routing_projection_omits_absence_and_preserves_exact_present_bound(self):
        with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()) as out:
            remote_sub_helpers.routing_env()
        self.assertNotIn(bound.ENV, out.getvalue())
        with mock.patch.dict(os.environ, {bound.ENV: WITNESS}, clear=True), contextlib.redirect_stdout(io.StringIO()) as out:
            remote_sub_helpers.routing_env()
        self.assertIn(bound.ENV + '=' + WITNESS, out.getvalue())

    def test_real_shell_prelaunch_refuses_with_transport_and_credentials_unavailable(self):
        for name, args in (('remote_sub.sh', ['ubuntu2', 'qwen', 'fixture-packet', '~', 'qwen3.8-flash']),
                           ('qwen_exec.sh', ['~', 'qwen3.8-flash', 'fixture-packet'])):
            with self.subTest(script=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                script = root / name
                shutil.copyfile(ROOT / 'candidate' / name, script)
                shutil.copyfile(ROOT / 'candidate/caller_not_before.py', root / 'caller_not_before.py')
                bin_dir = root / 'bin'; bin_dir.mkdir()
                # No ssh/scp/rsync/provider/status CLI exists on this PATH.
                # Every Python helper enters the existing audit boundary first.
                launcher = bin_dir / 'python3'
                launcher.write_text('#!' + sys.executable + '\nimport sys,runpy\n'
                    + 'sys.path[:0]=' + repr([str(ROOT / 'candidate'), str(ROOT / 'source'), str(ROOT / 'tests')]) + '\n'
                    + 'from _offline_boundary import acquire,release\nacquire()\ntry:\n'
                    + ' sys.argv=sys.argv[1:]\n runpy.run_path(sys.argv[0],run_name="__main__")\nfinally:\n release()\n')
                launcher.chmod(0o700)
                (bin_dir / 'dirname').symlink_to('/usr/bin/dirname')
                env = {'PATH': str(bin_dir), 'HOME': str(root / 'home'), bound.ENV: FUTURE}
                result = subprocess.run(guarded_prelaunch_shell(script, args), env=env,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(75, result.returncode, result.stderr)
                self.assertIn('caller_not_before eligible_at=' + FUTURE, result.stderr)
                self.assertEqual({'bin', name, 'caller_not_before.py'}, {p.name for p in root.iterdir()})


if __name__ == '__main__':
    unittest.main()
