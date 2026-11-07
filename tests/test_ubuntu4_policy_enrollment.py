"""Hermetic fixed-owner policy enrollment; never uses host/network/provider state."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ops.native_fabric.quota_continuity.rollout import ubuntu4_policy as policy


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class PolicyEnrollment(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve(strict=True)
        for name in ['lanes/ext/active', 'lanes/ext/state', 'lanes/orch/fabric']:
            (self.home/name).mkdir(parents=True, mode=0o700)
        self.active = self.home/'lanes/ext/active'
        self.state = self.home/'lanes/ext/state'
        self.target = self.home/'lanes/orch/fabric/pools.yaml'
        (self.active/'.admission.lock').write_bytes(b'')
        (self.active/'.admission.lock').chmod(0o600)
        self.scope = dict(home=self.home, uid=os.getuid(), platform='linux',
                          account='ubuntu4', hostname='ubuntu4-MS-7E61')
        self.payload = b'routing: {mode: retained}\npools: {minimax: {enabled: true}}\n'

    def inspect(self, **kw):
        return policy.operate(kind='inspect', **dict(self.scope, **kw))

    def install(self, **kw):
        args = dict(kind='install', payload=self.payload,
                    expected_after=sha(self.payload), expected_before='ABSENT',
                    operation_id='fixed-policy-test', original_settled=True, **self.scope)
        args.update(kw)
        return policy.operate(**args)

    def test_inspect_is_read_only_and_absent_is_explicit(self):
        before = sorted(str(p.relative_to(self.home)) for p in self.home.rglob('*'))
        result = self.inspect()
        self.assertEqual(result['preimage'], 'ABSENT')
        self.assertFalse(result['installation_authorized'])
        self.assertEqual(before, sorted(str(p.relative_to(self.home)) for p in self.home.rglob('*')))

    def test_first_install_exact_bytes_then_any_new_id_held(self):
        self.assertEqual(self.install()['state'], 'VERIFIED')
        self.assertEqual(self.target.read_bytes(), self.payload)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.inspect()['preimage'], sha(self.payload))
        with self.assertRaisesRegex(ValueError, 'preimage_changed_or_prior_install_hold'):
            self.install(operation_id='other-id')

    def test_existing_policy_never_overwritten(self):
        self.target.write_bytes(b'current owner policy')
        with self.assertRaisesRegex(ValueError, 'preimage_changed'):
            self.install()
        self.assertEqual(self.target.read_bytes(), b'current owner policy')
        self.assertFalse((self.state/policy.RECORD).exists())

    def test_missing_settlement_or_preimage_never_writes(self):
        for kw in [dict(original_settled=False), dict(expected_before=None),
                   dict(expected_before='0'*64), dict(expected_after='0'*64)]:
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.install(**kw)
        self.assertFalse(self.target.exists())
        self.assertFalse((self.state/policy.RECORD).exists())

    def test_wrong_account_host_or_platform(self):
        for kw in [dict(account='other'), dict(hostname='other'), dict(platform='darwin'), dict(uid=0)]:
            with self.subTest(kw=kw), self.assertRaisesRegex(ValueError, 'fixed_host_account'):
                self.inspect(**kw)

    def test_active_and_unknown_entries_hold_without_history_write(self):
        for name in ['worker.active', 'unknown']:
            p = self.active/name
            p.write_text('held')
            with self.assertRaisesRegex(ValueError, 'active_or_unknown_marker'):
                self.install()
            p.unlink()
        self.assertFalse((self.state/policy.RECORD).exists())

    def test_admission_lock_busy(self):
        import fcntl
        with (self.active/'.admission.lock').open('r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, 'admission_lock_busy'):
                self.inspect()

    def test_symlink_policy_is_not_followed(self):
        outside = self.home/'untouched'
        outside.write_bytes(b'outside')
        self.target.symlink_to(outside)
        with self.assertRaises(OSError):
            self.install()
        self.assertEqual(outside.read_bytes(), b'outside')

    def test_marker_inserted_during_read_withholds_inspection(self):
        original = policy.storage._read
        def read(fd, name, uid):
            result = original(fd, name, uid)
            if name == 'pools.yaml':
                (self.active/'new-marker').write_text('unknown')
            return result
        with mock.patch.object(policy.storage, '_read', side_effect=read):
            with self.assertRaisesRegex(ValueError, 'active_or_unknown_marker'):
                self.inspect()

    def test_replaced_lock_is_independently_acquirable_but_withheld(self):
        import fcntl
        original = policy.storage._read
        def read(fd, name, uid):
            result = original(fd, name, uid)
            if name == 'pools.yaml':
                lock = self.active/'.admission.lock'
                lock.unlink();lock.write_bytes(b'');lock.chmod(0o600)
                with lock.open('r+') as new:
                    fcntl.flock(new, fcntl.LOCK_EX|fcntl.LOCK_NB)
            return result
        with mock.patch.object(policy.storage, '_read', side_effect=read):
            with self.assertRaisesRegex(ValueError, 'admission_lock_changed'):
                self.inspect()

    def test_state_directory_replacement_withholds_terminal(self):
        original = policy.storage._write_new
        def write(fd, name, raw):
            original(fd, name, raw)
            if name == policy.RECORD:
                self.state.rename(self.state.with_name('state-old'))
                self.state.mkdir(mode=0o700)
        with mock.patch.object(policy.storage, '_write_new', side_effect=write):
            with self.assertRaisesRegex(ValueError, 'install_effect_unknown_no_replay'):
                self.install()
        self.assertFalse(self.target.exists())
        self.assertTrue((self.state.with_name('state-old')/policy.RECORD).exists())

    def test_late_marker_and_failed_companion_still_hold_new_id(self):
        original = policy.storage._write_new
        def write(fd, name, raw):
            original(fd, name, raw)
            if name.endswith('.verified'):
                (self.active/'late-marker').write_text('unknown')
        with mock.patch.object(policy.storage, '_write_new', side_effect=write):
            with self.assertRaisesRegex(ValueError, 'install_effect_unknown_no_replay'):
                self.install()
        (self.active/'late-marker').unlink()
        self.target.unlink()  # Hermetic fixture models observed target loss, not remediation.
        with self.assertRaisesRegex(ValueError, 'prior_install_hold'):
            self.install(operation_id='never-replay')

    def test_policy_replacement_during_inspection_is_withheld(self):
        self.target.write_bytes(b'old')
        original = policy.storage._read
        def read(fd, name, uid):
            value = original(fd, name, uid)
            if name == policy.RECORD:
                self.target.unlink();self.target.write_bytes(b'new')
            return value
        with mock.patch.object(policy.storage, '_read', side_effect=read):
            with self.assertRaisesRegex(ValueError, 'policy_changed'):
                self.inspect()

    def test_missing_lock_or_directory_is_not_created(self):
        lock = self.active/'.admission.lock'
        lock.unlink()
        with self.assertRaises(FileNotFoundError):
            self.inspect()
        self.assertFalse(lock.exists())
        self.target.parent.rmdir()
        with self.assertRaises(FileNotFoundError):
            self.inspect()
        self.assertFalse(self.target.parent.exists())

    def test_noncooperating_target_creation_is_not_overwritten(self):
        original = policy.os.link
        def link(*args, **kwargs):
            self.target.write_bytes(b'other owner')
            return original(*args, **kwargs)
        with mock.patch.object(policy.os, 'link', side_effect=link):
            with self.assertRaisesRegex(ValueError, 'install_effect_unknown_no_replay'):
                self.install()
        self.assertEqual(self.target.read_bytes(), b'other owner')
        self.assertTrue((self.state/policy.RECORD).exists())

    def test_remote_default_ignores_home_environment_and_requires_passwd_home(self):
        import types
        row = types.SimpleNamespace(pw_name='ubuntu4', pw_dir='/home/ubuntu4')
        with mock.patch.object(policy.pwd, 'getpwuid', return_value=row), \
             mock.patch.dict(os.environ, {'HOME': str(self.home)}):
            observed, _ = policy._scope(None, os.getuid(), 'linux', 'ubuntu4', 'ubuntu4-MS-7E61')
            self.assertEqual(observed, Path('/home/ubuntu4'))
        row.pw_dir = str(self.home)
        with mock.patch.object(policy.pwd, 'getpwuid', return_value=row):
            with self.assertRaisesRegex(ValueError, 'fixed_account_home'):
                policy._scope(None, os.getuid(), 'linux', 'ubuntu4', 'ubuntu4-MS-7E61')

    def test_public_reasons_are_closed_and_never_exception_text(self):
        import errno
        cases = [(policy.storage.InstallHeld('active_or_unknown_marker'),'ACTIVE_OR_UNKNOWN_MARKER'),
                 (policy.storage.InstallHeld('owner_or_mode'),'OWNER_OR_MODE_UNQUALIFIED'),
                 (FileNotFoundError(errno.ENOENT,'private path token'),'REQUIRED_PATH_ABSENT'),
                 (PermissionError(errno.EACCES,'private path token'),'OS_ACCESS_REFUSED'),
                 (OSError(errno.ELOOP,'private path token'),'SYMLINK_REFUSED'),
                 (ValueError('private path token'),'UNCLASSIFIED'),
                 (policy.storage.InstallHeld('private path token'),'UNCLASSIFIED'),
                 (OSError(errno.EIO,'private path token'),'OS_ERROR_UNCLASSIFIED')]
        for exc,expected in cases:
            self.assertEqual(policy.public_reason(exc),expected)
            self.assertNotIn('private',policy.public_reason(exc))
        class Foreign(OSError):pass
        self.assertEqual(policy.public_reason(Foreign(errno.ENOENT,'private')),'UNCLASSIFIED')

    def test_plan_has_no_dispatch_and_rejects_pin_drift(self):
        class Driver:
            SSH = ['existing-ssh-owner']
        registry = json.dumps({'ubuntu4': {'platform':'linux','ssh_alias':'mmx-ubuntu4',
                                         'hostnames':['ubuntu4-MS-7E61']}}).encode()
        ssh = b'Host mmx-ubuntu4\n HostName 192.168.8.220\n User ubuntu4\n'
        args = dict(kind='inspect', expected_module_sha=sha(Path(policy.__file__).read_bytes()),
                    expected_storage_sha=sha(Path(policy.storage.__file__).read_bytes()))
        plan = policy.transport_plan(Driver, registry, ssh, **args)
        self.assertFalse(plan['dispatch_authorized'])
        self.assertEqual(plan['argv'][:2], ['existing-ssh-owner','mmx-ubuntu4'])
        self.assertNotIn('assert ', plan['argv'][-1])
        import shlex
        compile(shlex.split(plan['argv'][-1])[2], '<fixed-plan>', 'exec')
        with self.assertRaisesRegex(ValueError, 'installer_source_pin'):
            policy.transport_plan(Driver, registry, ssh, **dict(args,expected_module_sha='0'*64))
        with self.assertRaisesRegex(ValueError, 'preimage_or_settlement_required'):
            policy.transport_plan(Driver, registry, ssh, **dict(args,kind='install',
                                   payload=self.payload,expected_before='ABSENT',
                                   original_settled=True,operation_id='x',expected_policy_sha='0'*64))


if __name__ == '__main__':
    unittest.main()
