"""Hermetic security and lifecycle assertions; no real donor/model/network call."""

import contextlib
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from integrations.meta_ceo_open_harness.launch_seat import (
    ALLOWED_ENV, DONOR_SHA, Seat, SeatLaunchError,
    _checked_private_dir, _source_preflight, build_command,
    child_environment, prepare, run,
)


class SeatLaunchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        source = root / 'dsh'
        (source / '.git').mkdir(parents=True)
        (source / 'apps/cli/lib').mkdir(parents=True)
        (source / 'apps/cli/lib/bin.js').write_text('')
        (source / 'node_modules').mkdir()
        node = root / 'node'
        node.write_text('')
        node.chmod(0o755)
        self.seat = Seat('meta-ceo', source, root / 'state', 3080, node)

    def git(self, source, node):
        def runner(cmd, **_kwargs):
            class R:
                returncode = 0
                stdout = (DONOR_SHA + '\n') if cmd[-2:] == ['rev-parse', 'HEAD'] else ''
            return R()
        return patch('integrations.meta_ceo_open_harness.launch_seat.subprocess.run', side_effect=runner)

    def test_command_is_loopback_and_absolute(self):
        cmd = build_command(self.seat)
        self.assertEqual(cmd[:3], [str(self.seat.node), str(self.seat.source / 'apps/cli/lib/bin.js'), 'web'])
        self.assertEqual(cmd[-4:], ['--host', '127.0.0.1', '--port', '3080'])
        self.assertIn('--no-open', cmd)

    def test_two_seats_have_distinct_homes_and_ports(self):
        s = self.seat
        other = Seat('secretary', s.source, s.root, 3081, s.node)
        self.assertNotEqual(s.home, other.home)
        self.assertNotEqual(s.workspace, other.workspace)
        self.assertNotEqual(s.web_url, other.web_url)

    def test_no_ambient_secrets_cross_boundary(self):
        env = child_environment(self.seat, {
            'HOME':'/test-user', 'PATH':'/bin', 'DSH_HOME':'/malicious',
            'OPENAI_API_KEY':'topsecret', 'ZAI_API_KEY':'topsecret2',
            'ANTHROPIC_API_KEY':'topsecret3', 'CONTROL_PLANE_API_KEY':'secret4',
            'HTTPS_PROXY':'http://private-proxy', 'MMX_RUNTIME_ID':'forged',
        })
        self.assertEqual(env['DSH_HOME'], str(self.seat.home))
        self.assertEqual(env['PATH'], '/bin')
        self.assertTrue(set(env) <= ALLOWED_ENV | {'DSH_HOME', 'DSH_TELEMETRY_DISABLED'})
        self.assertNotIn('topsecret', str(env))
        self.assertNotIn('forged', str(env))

    def test_readonly_preflight_does_not_create_state(self):
        with self.git(self.seat.source, self.seat.node), contextlib.redirect_stdout(io.StringIO()) as output:
            run(self.seat, check=True)
        self.assertFalse(self.seat.root.exists())
        self.assertIn('PREFLIGHT_ONLY_NO_MODEL_OR_TOOL_PROOF', output.getvalue())

    def test_launch_prepares_private_directories_and_replaces_process(self):
        calls = []
        def exec_fn(*args):
            calls.append(args)
        with self.git(self.seat.source, self.seat.node):
            run(self.seat, execute=exec_fn, change_directory=lambda d: calls.append(('cwd', d)))
        for path in (self.seat.root, self.seat.root / self.seat.role,
                     self.seat.home, self.seat.workspace):
            self.assertTrue(path.is_dir())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o077, 0)
        self.assertEqual(calls[0], ('cwd', str(self.seat.workspace)))
        self.assertEqual(calls[1][0], str(self.seat.node))
        self.assertEqual(calls[1][1], build_command(self.seat))

    def test_symlink_root_refused(self):
        destination = self.seat.source
        self.seat.root.symlink_to(destination, target_is_directory=True)
        with self.git(self.seat.source, self.seat.node), self.assertRaisesRegex(SeatLaunchError, 'not_real_directory'):
            prepare(self.seat, create=True)

    def test_symlink_existing_seat_refused(self):
        self.seat.root.mkdir(mode=0o700)
        (self.seat.root / 'meta-ceo').symlink_to(self.seat.source, target_is_directory=True)
        with self.git(self.seat.source, self.seat.node), self.assertRaisesRegex(SeatLaunchError, 'not_real_directory'):
            prepare(self.seat, create=True)

    def test_world_accessible_state_refused(self):
        self.seat.root.mkdir(mode=0o700)
        self.seat.root.chmod(0o755)
        with self.git(self.seat.source, self.seat.node), self.assertRaisesRegex(SeatLaunchError, 'excess_permissions'):
            prepare(self.seat, create=True)

    def test_wrong_owner_refused(self):
        self.seat.root.mkdir(mode=0o700)
        fake_stat = self.seat.root.lstat()
        with patch('integrations.meta_ceo_open_harness.launch_seat.os.getuid', return_value=fake_stat.st_uid + 1):
            with self.assertRaisesRegex(SeatLaunchError, 'wrong_owner'):
                _checked_private_dir(self.seat.root, create=False)

    def test_tracked_dirty_refused(self):
        def runner(cmd, **_kwargs):
            class R:
                returncode = 0
                stdout = DONOR_SHA if cmd[-2:] == ['rev-parse', 'HEAD'] else ' M packages/llm/llm.ts\n'
            return R()
        with patch('integrations.meta_ceo_open_harness.launch_seat.subprocess.run', side_effect=runner):
            with self.assertRaisesRegex(SeatLaunchError, 'tracked_source_dirty'):
                _source_preflight(self.seat.source, self.seat.node)

    def test_donor_wrong_pin_refused(self):
        def runner(cmd, **_kwargs):
            class R:
                returncode = 0
                stdout = ('f' * 40) if cmd[-2:] == ['rev-parse', 'HEAD'] else ''
            return R()
        with patch('integrations.meta_ceo_open_harness.launch_seat.subprocess.run', side_effect=runner):
            with self.assertRaisesRegex(SeatLaunchError, 'pin_mismatch'):
                _source_preflight(self.seat.source, self.seat.node)

    def test_absent_built_binary_refused(self):
        (self.seat.source / 'apps/cli/lib/bin.js').unlink()
        with self.assertRaisesRegex(SeatLaunchError, 'build_or_dependencies_missing'):
            _source_preflight(self.seat.source, self.seat.node)

    def test_git_probe_failure_refused_without_parent_diagnostics(self):
        def runner(*_args, **_kwargs):
            class R:
                returncode = 1
                stdout = ''
                stderr = 'sensitive private error'
            return R()
        with patch('integrations.meta_ceo_open_harness.launch_seat.subprocess.run', side_effect=runner):
            with self.assertRaisesRegex(SeatLaunchError, 'git_probe_failed') as caught:
                _source_preflight(self.seat.source, self.seat.node)
        self.assertNotIn('sensitive private error', str(caught.exception))

    def test_invalid_ports_refused(self):
        for port in (0, 1, 80, 65536, -1):
            with self.subTest(port=port), self.git(self.seat.source, self.seat.node):
                seat = Seat(self.seat.role, self.seat.source, self.seat.root, port, self.seat.node)
                with self.assertRaisesRegex(SeatLaunchError, 'invalid_port'):
                    prepare(seat, create=False)

    def test_donor_source_symlink_refused(self):
        alias = self.seat.source.parent / 'alias'
        alias.symlink_to(self.seat.source, target_is_directory=True)
        with self.assertRaisesRegex(SeatLaunchError, 'source_absent_or_symlink'):
            _source_preflight(alias, self.seat.node)


if __name__ == '__main__':
    unittest.main()
