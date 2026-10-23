"""Real finite installer transactions in disposable owners; no live operations."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import pwd
import socket
import sys
import tempfile
import threading
import unittest
from unittest import mock

_active = False
_expected = False
_unexpected = []
_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
_private = tuple(str(_home / name) for name in
                 ('.glm', '.bailian', '.minimax', '.qwen', '.claude/projects',
                  '.codex/auth.json', '.claude/.credentials.json'))


class FixtureBoundaryError(AssertionError):
    pass


def _audit(event, args):
    if not _active:
        return
    kind = None
    if event.startswith('socket.') or event == 'urllib.Request':
        kind = 'network'
    elif event in ('subprocess.Popen', 'os.system', 'os.posix_spawn'):
        kind = 'process'
    elif event in ('open', 'os.mkdir', 'os.remove', 'os.rename', 'os.rmdir', 'os.symlink', 'os.chmod'):
        for value in args[:2]:
            if isinstance(value, (str, bytes, os.PathLike)):
                path = os.path.abspath(os.fsdecode(value))
                if any(path == p or path.startswith(p + os.sep) for p in _private):
                    kind = 'private_owner'
    if kind:
        if not _expected:
            _unexpected.append(kind)
        raise FixtureBoundaryError('installer fixture blocked ' + kind)


sys.addaudithook(_audit)
_active = True  # before loading any source under test
try:
    import native_generation as g
    import native_install as installer
    import build_review_stage as builder
finally:
    _active = False


def _cleanup(temp):
    # Only our own disposable root; never traverse declared state links.
    for directory, _, _ in os.walk(temp.name, followlinks=False):
        os.chmod(directory, 0o700)
    temp.cleanup()


class PairedLauncherUpgrade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _active
        _active = True
        try:
            cls.shared = tempfile.TemporaryDirectory(prefix='upgrade-source-')
            cls.built = Path(cls.shared.name).resolve() / 'built'
            with mock.patch.object(sys, 'argv', ['builder', '--output', str(cls.built)]), \
                    contextlib.redirect_stdout(io.StringIO()):
                builder.main()
            cls.manifest = json.loads((cls.built / 'native-manifest.json').read_bytes())
            if (len(cls.manifest) != 95 or
                    g.digest((cls.built / 'native-manifest.json').read_bytes()) != installer.UPGRADE_MANIFEST):
                raise AssertionError('actual protected composition differs from upgrade pin')
        finally:
            _active = False

    @classmethod
    def tearDownClass(cls):
        _cleanup(cls.shared)

    def setUp(self):
        global _active
        _active = True
        self.temp = tempfile.TemporaryDirectory(prefix='paired-upgrade-')
        self.root = Path(self.temp.name).resolve()
        self.ext = self.root / 'kit/ext'
        self.ext.mkdir(parents=True)
        (self.root / 'bin').mkdir()
        self.pool = self.root / 'bin/pool'
        original_pool = ('#!/bin/bash\nKIT_DIR="' + str(self.ext.parent) + '"\nexit 0\n').encode()
        self.pool.write_bytes(original_pool)
        self.pool.chmod(0o755)
        task = b'"""Inert fixture API."""\nAPI_VERSION="original"\n'
        remote = b'#!/bin/bash\nexit 0\n'
        for name, raw in (('fabric_task.py', task), ('remote_sub.sh', remote)):
            (self.ext / name).write_bytes(raw)
            (self.ext / name).chmod(0o755)
        source = self.root / 'source'
        (source / 'ext').mkdir(parents=True)
        payloads = {'pool': installer.relocate_pool(original_pool),
                    'ext/fabric_task.py': task, 'ext/remote_sub.sh': remote}
        for name, raw in payloads.items():
            (source / name).write_bytes(raw)
        manifest = {name: g.digest(raw) for name, raw in payloads.items()}
        self.initial = g.publish(source, self.ext, manifest)
        self.store = self.ext.parent / g.STORE_NAME
        raw = Path(g.__file__).read_bytes().replace(
            b'or parts[1] in {"yes", "host_pull_probe.template",\n'
            b'                        "paid_pyyaml_6_0_3.zip", "paid_pyyaml_provenance.json"})',
            b'or parts[1] in {"yes", "host_pull_probe.template"})')
        self.assertEqual(g.digest(raw), installer.UPGRADE_FROM)
        old_file = self.root / 'old_generation.py'
        old_file.write_bytes(raw)
        spec = importlib.util.spec_from_file_location('upgrade_old_generation', old_file)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        self.original = self.root / 'original'
        with mock.patch.object(installer, 'generation', old):
            self.base = installer.prepare(self.store, self.initial.name, self.pool, self.original)
            installer.phase1(self.original)
        # Actual installed selection may have advanced since first installation.
        self.previous = g.select(self.store, self.initial.name, self.initial.name)
        self.target = g.publish(self.built / 'native-code-stage', self.ext, self.manifest)
        self.bundle = self.root / 'upgrade'
        self.plan = installer.prepare_upgrade(self.original, self.target.name, self.bundle)
        self.old_plan = (self.original / 'PLAN.json').read_bytes()
        self.old_remote = (self.ext / 'remote_sub.sh').read_bytes()

    def tearDown(self):
        global _active
        _active = False
        _cleanup(self.temp)
        self.assertEqual(_unexpected, [], 'a forbidden fallback was attempted')

    def assert_complete(self):
        result = installer.upgrade(self.bundle)
        current = g.current(self.store)
        self.assertEqual(current, result['selection'])
        self.assertEqual(current['generation'], self.target.name)
        self.assertEqual(current['sequence'], self.previous['sequence'] + 1)
        for name in ('pool', 'task'):
            self.assertEqual(g.digest(g.regular_bytes(self.plan['entries'][name]['target'])),
                             self.plan['entries'][name]['bridge'])
        self.assertEqual((self.original / 'PLAN.json').read_bytes(), self.old_plan)
        self.assertEqual((self.ext / 'remote_sub.sh').read_bytes(), self.old_remote)
        self.assertEqual(g.verify(self.store, self.initial.name)[0], self.initial)
        return result

    def test_real_95_closure_and_original_epoch_upgrade_once(self):
        result = self.assert_complete()
        pointer_inode = (self.store / 'CURRENT.json').stat().st_ino
        with mock.patch.object(g, 'atomic_bytes', side_effect=AssertionError('completed replay wrote')):
            self.assertEqual(installer.upgrade(self.bundle), result)
        self.assertEqual((self.store / 'CURRENT.json').stat().st_ino, pointer_inode)

    def interrupt_after(self, target):
        atomic = g.atomic_bytes
        def fail(path, *args):
            atomic(path, *args)
            if Path(path) == target:
                raise OSError('fixture interruption after committed atomic write')
        with mock.patch.object(g, 'atomic_bytes', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'fixture interruption'):
                installer.upgrade(self.bundle)
        self.assert_complete()

    def test_recover_original_intent(self):
        self.interrupt_after(self.store / 'bootstrap/.paired-launcher-upgrade.json')

    def test_recover_sealed_launcher(self):
        self.interrupt_after(self.store / 'launchers' / (installer.UPGRADE_TO + '.py'))

    def test_recover_first_bridge(self):
        self.interrupt_after(self.pool)

    def test_recover_second_bridge(self):
        self.interrupt_after(self.ext / 'fabric_task.py')

    def test_recover_selected_pointer_without_second_cas(self):
        self.interrupt_after(self.store / 'CURRENT.json')

    def test_recover_completion_receipt_without_replay(self):
        self.interrupt_after(self.store / 'bootstrap' / (self.plan['digest'] + '.upgrade.json'))

    def test_stale_sequence_same_generation_refuses(self):
        g.select(self.store, self.initial.name, self.initial.name)
        with self.assertRaisesRegex(ValueError, 'compare-and-swap'):
            installer.upgrade(self.bundle)
        self.assertEqual(g.digest(self.pool.read_bytes()), self.plan['entries']['pool']['previous'])

    def test_foreign_pair_and_source_symlink_refuse(self):
        g.atomic_bytes(self.pool, b'foreign-pool\n', 0o755)
        with self.assertRaisesRegex(ValueError, 'preimage refused'):
            installer.upgrade(self.bundle)
        self.assertEqual(self.pool.read_bytes(), b'foreign-pool\n')

    def test_symlink_payload_refuses(self):
        path = self.bundle / 'task.bridge'
        raw = path.read_bytes()
        twin = self.root / 'twin'; twin.write_bytes(raw)
        path.unlink(); path.symlink_to(twin)
        with self.assertRaises(ValueError):
            installer.upgrade(self.bundle)

    def test_symlink_entry_refuses_before_intent(self):
        task = self.ext / 'fabric_task.py'
        task.unlink(); task.symlink_to(self.original / 'task.original')
        with self.assertRaises(ValueError):
            installer.upgrade(self.bundle)
        self.assertFalse((self.store / 'bootstrap/.paired-launcher-upgrade.json').exists())

    def test_original_receipt_and_foreign_intent_refuse(self):
        path = self.store / 'bootstrap/.paired-launcher-upgrade.json'
        g.atomic_bytes(path, g.canonical({'schema': installer.UPGRADE_SCHEMA,
            'plan_digest': 'f' * 64, 'bootstrap_digest': self.base['digest']}), 0o600)
        with self.assertRaisesRegex(ValueError, 'foreign paired'):
            installer.upgrade(self.bundle)

    def test_original_receipt_cannot_be_supplied_by_caller(self):
        receipt = self.store / 'bootstrap' / (self.base['digest'] + '.phase1.json')
        g.atomic_bytes(receipt, b'{}\n', 0o600)
        with self.assertRaisesRegex(ValueError, 'original paired installation receipt'):
            installer.upgrade(self.bundle)

    def test_closed_plan_and_target_pin_refuse(self):
        path = self.bundle / 'PLAN.json'
        malformed = dict(self.plan, caller_approved=True)
        g.atomic_bytes(path, g.canonical(malformed), 0o600)
        with self.assertRaises(ValueError):
            installer.upgrade(self.bundle)
        with self.assertRaisesRegex(ValueError, 'reviewed 95-member'):
            installer.prepare_upgrade(self.original, self.initial.name, self.root / 'bad-target')

    def test_existing_prepare_remains_refused_on_bridged_pool(self):
        with self.assertRaisesRegex(ValueError, 'already bridged'):
            installer.prepare(self.store, self.initial.name, self.pool, self.root / 'not-a-new-epoch')

    def test_changed_completed_selection_cannot_reactivate(self):
        self.assert_complete()
        changed = g.select(self.store, self.initial.name, self.target.name)
        with self.assertRaisesRegex(ValueError, 'completed upgrade'):
            installer.upgrade(self.bundle)
        self.assertEqual(g.current(self.store), changed)

    def test_concurrent_original_transaction_fails_promptly(self):
        entered, release = threading.Event(), threading.Event()
        atomic = g.atomic_bytes
        errors = []
        def pause(path, *args):
            atomic(path, *args)
            if Path(path).name == '.paired-launcher-upgrade.json':
                entered.set()
                if not release.wait(5):
                    raise AssertionError('fixture synchronization expired')
        def run():
            try:
                installer.upgrade(self.bundle)
            except BaseException as exc:
                errors.append(exc)
        with mock.patch.object(g, 'atomic_bytes', side_effect=pause):
            thread = threading.Thread(target=run)
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaisesRegex(ValueError, 'publication already in progress'):
                    installer.upgrade(self.bundle)
            finally:
                release.set(); thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assert_complete()

    def test_foreign_bytes_after_partial_write_are_not_recovered(self):
        atomic = g.atomic_bytes
        def interrupt(path, *args):
            atomic(path, *args)
            if Path(path) == self.pool:
                raise OSError('partial fixture')
        with mock.patch.object(g, 'atomic_bytes', side_effect=interrupt):
            with self.assertRaisesRegex(OSError, 'partial fixture'):
                installer.upgrade(self.bundle)
        task = self.ext / 'fabric_task.py'
        g.atomic_bytes(task, b'foreign-partial-state\n', 0o755)
        with self.assertRaisesRegex(ValueError, 'preimage refused'):
            installer.upgrade(self.bundle)
        self.assertEqual(g.current(self.store), self.previous)
        self.assertEqual(task.read_bytes(), b'foreign-partial-state\n')

    def test_conflicting_completion_receipt_refuses_without_repair(self):
        self.assert_complete()
        receipt = self.store / 'bootstrap' / (self.plan['digest'] + '.upgrade.json')
        g.atomic_bytes(receipt, b'{}\n', 0o600)
        with mock.patch.object(g, 'atomic_bytes', side_effect=AssertionError('foreign receipt repair')):
            with self.assertRaisesRegex(ValueError, 'completed upgrade'):
                installer.upgrade(self.bundle)
        self.assertEqual(receipt.read_bytes(), b'{}\n')

    def test_real_network_and_credentials_block_before_effect(self):
        global _expected
        _expected = True
        try:
            with self.assertRaisesRegex(FixtureBoundaryError, 'network'):
                socket.getaddrinfo('offline-fixture.invalid', 443)
            with self.assertRaisesRegex(FixtureBoundaryError, 'private_owner'):
                open(_home / '.bailian/config.json', 'rb')
        finally:
            _expected = False


if __name__ == '__main__':
    unittest.main()
