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
            current_manifest = (cls.built / 'native-manifest.json').read_bytes()
            if current_manifest != (Path(builder.__file__).parent / 'native-manifest.json').read_bytes():
                raise AssertionError('current builder differs from protected manifest')
            cls.manifest = json.loads(current_manifest)
            # This suite tests the historical 8bc -> d044 paired transition,
            # not a later ordinary generation selection through d044. Recreate
            # only its exact two-line controller preimage in this disposable
            # fixture; both the whole controller and whole old manifest bind it.
            controller = cls.built / 'native-code-stage/ext/remote_sub.sh'
            current = controller.read_bytes()
            if g.digest(current) != '09e000db51b2eca4fadd2e3d1a201f4027b4ea725359d1b42ef4d3baf92fe5d7':
                raise AssertionError('historical fixture current controller differs')
            fixed = (b'      ECONOMIC_SOURCE_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"\n'
                     b'      if ! ECONOMIC_DECISION=$(commission_run launch-policy "$REMOTE_SUB_PYTHON" "$ECONOMIC_SOURCE_DIR/pick.py" launch-policy')
            prior = (b'      POLICY_SOURCE="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"\n'
                     b'      if ! ECONOMIC_DECISION=$(commission_run launch-policy "$REMOTE_SUB_PYTHON" "$POLICY_SOURCE/pick.py" launch-policy')
            if current.count(fixed) != 1:
                raise AssertionError('historical fixture inverse is not exact')
            original = current.replace(fixed, prior)
            original_sha = 'ccd49590f1a8e8b5b337c6581aabd1671791f4e7b339b041112c8aadd99b5351'
            if g.digest(original) != original_sha:
                raise AssertionError('historical fixture controller preimage differs')
            controller.write_bytes(original)
            cls.manifest['ext/remote_sub.sh'] = original_sha
            # Reconstruct the reviewed historical 95-file epoch using only
            # exact inverse hunks in THIS disposable fixture. Never repin the
            # original upgrade installer, preimages or installed selection.
            def undo_manual_patch(value, member, expected):
                patch_file = (Path(__file__).resolve().parents[2] /
                              'patches/native_generation_manual_preview_20261022.patch')
                patch_raw = patch_file.read_bytes()
                if g.digest(patch_raw) != '6b1dade16fe58b732064d66e0645396dd6dd02fc255c3befbf0d03e105b23e6b':
                    raise AssertionError('reviewed manual patch source drift')
                section = b'diff --git a/' + member.encode() + b' b/' + member.encode() + b'\n'
                if patch_raw.count(section) != 1:
                    raise AssertionError('reviewed inverse member missing')
                lines = patch_raw.split(section, 1)[1].split(b'\ndiff --git ', 1)[0].splitlines(keepends=True)
                groups, block = [], None
                for line in lines:
                    if line.startswith(b'@@ '):
                        block = []
                        groups.append(block)
                    elif block is not None and line[:1] in (b' ', b'+', b'-'):
                        block.append(line)
                if not groups:
                    raise AssertionError('reviewed inverse has no hunks')
                for group in reversed(groups):
                    applied = b''.join(line[1:] for line in group if line[:1] in (b' ', b'+'))
                    previous = b''.join(line[1:] for line in group if line[:1] in (b' ', b'-'))
                    if value.count(applied) != 1:
                        raise AssertionError('reviewed inverse hunk not unique')
                    value = value.replace(applied, previous, 1)
                if g.digest(value) != expected:
                    raise AssertionError('reviewed historical inverse hash differs: ' + member)
                return value

            # B10: source now composes F1 strict manual model + independent
            # judgment #1797. Undo BOTH independent changes before restoring
            # the original 95-member frozen launcher epoch.
            pick = cls.built / 'native-code-stage/ext/pick.py'
            reviewed_pick = pick.read_bytes()
            if g.digest(reviewed_pick) != '4311200ae485ffd19b2560434e46c0c01899fbb58f0793c198292dba6004503b':
                raise AssertionError('combined manual/judgment pick differs')
            judgment_hunks = (
                (b'"operator", "reviewer", "review", "adjudicate", "decompose", "audit", "repair",',
                 b'"operator", "reviewer", "adjudicate", "decompose", "audit", "repair",'),
                (b'    # Independent review/audit remain judgment even when legacy execute_classes includes them.\n'
                 b'    # Preserve explicit-pool gates above; do not score implicit reviewers into Qwen.\n'
                 b'    if tc not in {"review", "audit"} and (is_execute_class(tc, doc) or tc in LABOR_CLASSES_R30):\n',
                 b'    if is_execute_class(tc, doc) or tc in LABOR_CLASSES_R30:\n'),
            )
            for current_hunk, old_hunk in judgment_hunks:
                if reviewed_pick.count(current_hunk) != 1:
                    raise AssertionError('reviewed judgment inverse mismatch')
                reviewed_pick = reviewed_pick.replace(current_hunk, old_hunk, 1)
            if g.digest(reviewed_pick) != '9bbb96c8da84e38bbd802fdd373a0e8ba386395abc5a80bc8628b49d5afd8174':
                raise AssertionError('manual-only picker inverse differs')
            old_pick = undo_manual_patch(reviewed_pick, 'ext/pick.py',
                                         'a3c3a9822779e244f4140dc1223c4a2617243ed35c12c0358527d637fc1fc1ee')
            pick.write_bytes(old_pick)
            cls.manifest['ext/pick.py'] = g.digest(old_pick)

            pool = cls.built / 'native-code-stage/pool'
            new_pool = pool.read_bytes()
            if g.digest(new_pool) != '12602edd2f0bf3a5a789eb2b77043a1973bbed533ff35d307357e00be1531679':
                raise AssertionError('manual new-pool digest mismatch')
            old_pool = undo_manual_patch(new_pool, 'pool',
                                         '4026eb128fe803e575151bbeec49a4d8f5838408db1177feedd64ad24f4f2059')
            pool.write_bytes(old_pool)
            cls.manifest['pool'] = g.digest(old_pool)

            # Restore historical fabric_task BEFORE its preexisting qualification-
            # host inverse, retaining the independent paired-upgrade test.
            task = cls.built / 'native-code-stage/ext/fabric_task.py'
            newest_task = task.read_bytes()
            if g.digest(newest_task) != '48699864fdc9e96d12f51ff22fef74bd438a2fcd500f25c836e6fab2dea728d7':
                raise AssertionError('approved AUTO task digest mismatch')
            task.write_bytes(undo_manual_patch(newest_task, 'ext/fabric_task.py',
                          '3ceba9777a475fb1cfc568f13035b4c23ae15c7bd54316c4cb006335557a545b'))
            # Preserve the old preimage restoration, no historical pin rewrite.
            current_task = task.read_bytes()
            current_line = (
                b'    p_request.add_argument("--qualification-host", choices=("mb", "m1", "ubuntu4"), '
                b'help="Explicit pending-host first worker (Grok on Mac, MiniMax on M1 or Ubuntu4); no provider enrollment")\n'
            )
            original_line = (
                b'    p_request.add_argument("--qualification-host", choices=("mb", "m1"), '
                b'help="Explicit first Grok worker on a pending qualified Mac; no enrollment")\n'
            )
            if current_task.count(current_line) != 1:
                raise AssertionError('historical task fixture new CLI preimage differs')
            prior_task = current_task.replace(current_line, original_line)
            prior_task_sha = '0ed7b286dc1d51ecd6349d34d9342fa144097ec3a74257bce6186aa15b8b65de'
            if g.digest(prior_task) != prior_task_sha:
                raise AssertionError('historical task fixture reverse transform differs')
            task.write_bytes(prior_task)
            cls.manifest['ext/fabric_task.py'] = prior_task_sha
            # This is the historical paired upgrade, not later diagnostic
            # publication. Restore exact retained pre-diagnostic payloads only
            # inside this disposable stage, with closed names and whole hashes.
            import base64, zlib
            fixture = Path(__file__).resolve().parents[4] / 'tests/fixtures/host-pull-prediagnostic-968e.json'
            retained = json.loads(fixture.read_bytes())
            if retained['source'] != '968e1a62842927dd763ac6041cf7312f4433ebb7' or set(retained['files']) != {'host_pull.sh', 'host_pull_backend.py'}:
                raise AssertionError('historical collector fixture identity differs')
            expected = {'host_pull.sh': '4671e6e3094ad4fdafa77f373648de66fabc866a8e6ec2f76da17215cdedb7cc',
                        'host_pull_backend.py': 'b8629cee082334319391bf48285668c727150a7d20d5ae831497cbb10336b073'}
            for name, digest in expected.items():
                raw = zlib.decompress(base64.b64decode(retained['files'][name]['zlib_base64'], validate=True))
                if retained['files'][name]['sha256'] != digest or g.digest(raw) != digest:
                    raise AssertionError('historical collector preimage differs')
                (cls.built / 'native-code-stage/ext' / name).write_bytes(raw)
                cls.manifest['ext/' + name] = digest
            # The host-pull daemon and plist are later than this paired upgrade.
            # The disposable target keeps the reviewed 95-member closure.
            for relative in ('ext/host_pull_daemon.sh', 'ext/host_pull_launchd.plist.template'):
                cls.manifest.pop(relative)
                (cls.built / 'native-code-stage' / relative).unlink()
            historical_manifest = (json.dumps(cls.manifest, sort_keys=True, indent=2) + '\n').encode()
            if len(cls.manifest) != 95 or g.digest(historical_manifest) != installer.UPGRADE_MANIFEST:
                raise AssertionError('historical paired-upgrade manifest differs')
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
        admission = (
            b"    # One vetted flat plist. Not a suffix rule and not a directory walk.\n"
            b"    if relative == \"ext/host_pull_launchd.plist.template\":\n"
            b"        return\n")
        live = Path(g.__file__).read_bytes()
        self.assertEqual(live.count(admission), 1)
        pinned = live.replace(admission, b"")
        self.assertEqual(g.digest(pinned), installer.UPGRADE_TO)
        raw = pinned.replace(
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
        # prepare_upgrade requires the launcher bytes to be exactly UPGRADE_TO.
        # Reads of this repo file return those pinned bytes. Writes stay on this module.
        live_path = Path(g.__file__).resolve()
        original_regular = g.regular_bytes
        def regular_bytes(path, *args, **kwargs):
            if Path(path).resolve() == live_path:
                return pinned
            return original_regular(path, *args, **kwargs)
        self.bytes_patch = mock.patch.object(g, 'regular_bytes', regular_bytes)
        self.bytes_patch.start()
        self.addCleanup(self.bytes_patch.stop)
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

    def stop_after_selection(self):
        atomic = g.atomic_bytes
        def interrupt(path, *args):
            atomic(path, *args)
            if Path(path) == self.store / 'CURRENT.json':
                raise OSError('selection committed fixture')
        with mock.patch.object(g, 'atomic_bytes', side_effect=interrupt):
            with self.assertRaisesRegex(OSError, 'selection committed'):
                installer.upgrade(self.bundle)

    def test_selected_recovery_only_writes_missing_completion_receipt(self):
        self.stop_after_selection()
        atomic = g.atomic_bytes
        writes = []
        def track(path, *args):
            writes.append(Path(path))
            atomic(path, *args)
        with mock.patch.object(g, 'atomic_bytes', side_effect=track):
            installer.upgrade(self.bundle)
        self.assertEqual(writes, [self.store / 'bootstrap' / (self.plan['digest'] + '.upgrade.json')])
        self.assert_complete()

    def test_lost_issued_receipt_recovers_identical_original_identity_only(self):
        self.assert_complete()
        path = self.store / 'bootstrap' / (self.plan['digest'] + '.upgrade.json')
        issued = path.read_bytes()
        path.unlink()
        before = (self.store / 'CURRENT.json').stat().st_ino
        atomic = g.atomic_bytes
        writes = []
        def track(target, *args):
            writes.append(Path(target))
            atomic(target, *args)
        with mock.patch.object(g, 'atomic_bytes', side_effect=track):
            installer.upgrade(self.bundle)
        self.assertEqual(writes, [path])
        self.assertEqual(path.read_bytes(), issued)
        self.assertEqual((self.store / 'CURRENT.json').stat().st_ino, before)

    def test_selected_missing_launcher_refuses_without_any_write(self):
        self.stop_after_selection()
        launcher = self.store / 'launchers' / (installer.UPGRADE_TO + '.py')
        launcher.unlink()
        with mock.patch.object(g, 'atomic_bytes', side_effect=AssertionError('selected repair wrote')):
            with self.assertRaises(FileNotFoundError):
                installer.upgrade(self.bundle)
        self.assertFalse(launcher.exists())
        self.assertFalse((self.store / 'bootstrap' / (self.plan['digest'] + '.upgrade.json')).exists())

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
