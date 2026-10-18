"""Exercise the real release owner against sealed temp seats and real Git objects.

Only launchctl is replaced. No live files, dependencies, credentials or service
are read, and the Git fixture has no network operations.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import private_service as svc


class BackendReleaseFixture:
    ACCOUNT = svc.FABRIC_BACKEND_ACCOUNT
    PORT = 45119
    MODERN = False

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'home'
        self.home.mkdir(mode=0o700)
        self.fixture_root = mock.patch.object(svc, '_user_root', return_value=self.home)
        self.fixture_root.start()
        self.addCleanup(self.fixture_root.stop)
        self.account = self.ACCOUNT
        self.label = f'com.mastermind.studio-direct-private.{self.account}'
        self.roots = svc._build_runtime_roots(self.account)
        self.loaded = False
        self.launch_error = False
        self.calls = []
        original_run = svc._run

        def run(argv, **kwargs):
            if argv[0] != 'launchctl':
                return original_run(argv, **kwargs)
            self.calls.append(list(argv))
            self.assertEqual(argv, ['launchctl', 'print', svc._launchd_target(self.label)])
            if self.launch_error:
                return svc.CmdResult(1, '', 'permission denied')
            if self.loaded:
                return svc.CmdResult(0, f'{svc._launchd_target(self.label)} = {{\n'
                    f'\tpath = {self.roots["plist"]}\n\tstate = running\n\tpid = 4321\n}}\n', '')
            return svc.CmdResult(113, '', f'Bad request.\nCould not find service "{self.label}" '
                f'in domain for user gui: {os.getuid()}\n')

        self.runner = mock.patch.object(svc, '_run', run)
        self.runner.start()
        self.addCleanup(self.runner.stop)
        source = self.home / 'old-gateway-source'
        source.mkdir()
        for name in svc.STAGE_FILES:
            (source / name).write_text('// sealed fixture ' + name + '\n')
        node = self.home / 'node'
        node.write_text('#!/bin/sh\nexit 0\n')
        node.chmod(0o700)
        self.old_backend = self.home / 'old-backend.mjs'
        self.old_backend.write_text('export const oldBackend = true;\n')
        stage = SimpleNamespace(account=self.account, port=self.PORT, source=str(source),
            node=str(node), backend=str(self.old_backend), fabric_only=True,
            modern_fabric_protocol=True if self.MODERN else None, enable_repository_workspaces=False,
            os_commission_config_sha256=None)
        self.capture(lambda: svc.cmd_stage(stage))
        deps = self.roots['node_modules'] / 'fixture-package'
        deps.mkdir(parents=True)
        (deps / 'index.js').write_text('export const preserved = true;\n')
        self.capture(lambda: svc.cmd_seal_runtime(SimpleNamespace(account=self.account)))
        # Preserve deliberately non-default policy values and opaque child env.
        config = json.loads(self.roots['config'].read_bytes())
        config.update({'requestTimeoutMs': 199_999, 'backendMode': 'shared-account',
                       'modernFabricProtocol': self.MODERN, 'maxPerSessionConcurrency': 6})
        config['args'].append('--retained-existing-flag')
        config['childEnv']['OPAQUE_EXISTING_POLICY'] = 'fixture-only'
        self.roots['config'].write_bytes(svc._fabric_release_json(config))
        manifest = json.loads(self.roots['manifest'].read_bytes())
        manifest['configHash'] = svc._sha256_file(self.roots['config'])
        self.roots['manifest'].write_bytes(svc._fabric_release_json(manifest))
        self.before = self.snapshot()
        self.repo = self.home / svc.TYPED_GIT_SOURCE_REPOSITORY_REL
        self.repo.mkdir(parents=True)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Isolated release fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('remote', 'add', 'origin', svc.TYPED_GIT_REMOTE_URL)
        backend_source = self.repo / svc.FABRIC_BACKEND_SOURCE
        backend_source.parent.mkdir(parents=True)
        backend_source.write_text('export const newBackend = true;\n')
        self.git('add', svc.FABRIC_BACKEND_SOURCE)
        self.git('commit', '-q', '-m', 'Isolated merged release fixture')
        self.commit = self.git('rev-parse', 'HEAD').strip()
        self.git('update-ref', 'refs/remotes/origin/master', self.commit)
        self.backend = self.home / svc.FABRIC_BACKEND_RELEASES_REL / ('fabric-c3-' + self.commit) / svc.FABRIC_BACKEND_SOURCE
        self.backend.parent.mkdir(parents=True)
        self.backend.write_bytes(backend_source.read_bytes())
        self.args = SimpleNamespace(account=self.account, expected_manifest_sha256=svc._sha256_file(self.roots['manifest']),
            release_commit=self.commit, backend_sha256=svc._sha256_file(self.backend),
            expected_plan_sha256=None, preflight_only=True)

    def git(self, *argv):
        return subprocess.run([svc.TYPED_GIT_BINARY, '-C', str(self.repo), *argv],
            check=True, capture_output=True, text=True).stdout

    def capture(self, fn):
        stream = io.StringIO()
        with mock.patch('sys.stdout', stream):
            rc = fn()
        self.assertEqual(rc, 0)
        return json.loads(stream.getvalue())

    def snapshot(self):
        paths = [self.roots['config'], self.roots['manifest'], self.roots['plist'], self.old_backend]
        paths.extend(self.roots['base'] / name for name in svc.STAGE_FILES)
        paths.extend(p for p in self.roots['node_modules'].rglob('*') if p.is_file())
        return {p: p.read_bytes() for p in paths}

    def preview(self):
        return self.capture(lambda: svc.cmd_fabric_backend_release(self.args))

    def prepare_apply(self):
        preview = self.preview()
        self.args.expected_plan_sha256 = preview['planSha256']
        self.args.preflight_only = False
        return preview

    def transaction(self):
        dirs = list((self.roots['state'] / 'fabric-backend-releases').iterdir())
        self.assertEqual(len(dirs), 1)
        return dirs[0]

class BackendReleaseTests(BackendReleaseFixture, unittest.TestCase):
    def test_live_preview_has_no_effect_and_exact_diff_then_apply_preserves_seal(self):
        self.loaded = True
        preview = self.preview()
        self.assertEqual(preview['changedConfigFields'], ['args[0]'])
        self.assertEqual(preview['changedManifestFields'], ['backend', 'backendHash', 'configHash'])
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())
        self.args.preflight_only = False
        self.args.expected_plan_sha256 = preview['planSha256']
        with self.assertRaisesRegex(SystemExit, 'service is loaded'):
            svc.cmd_fabric_backend_release(self.args)
        self.loaded = False
        result = self.capture(lambda: svc.cmd_fabric_backend_release(self.args))
        self.assertEqual(result['effect'], 'APPLIED')
        self.assertFalse(result['serviceStarted'])
        old_config = json.loads(self.before[self.roots['config']])
        new_config = json.loads(self.roots['config'].read_bytes())
        expected_config = copy.deepcopy(old_config)
        expected_config['args'][0] = str(self.backend)
        self.assertEqual(new_config, expected_config)
        old_manifest = json.loads(self.before[self.roots['manifest']])
        new_manifest = json.loads(self.roots['manifest'].read_bytes())
        self.assertEqual({k for k in new_manifest if old_manifest[k] != new_manifest[k]},
                         {'backend', 'backendHash', 'configHash'})
        for path, data in self.before.items():
            if path not in (self.roots['config'], self.roots['manifest']):
                self.assertEqual(path.read_bytes(), data)
        self.assertEqual(svc._verify_staged_install(self.account, self.label, self.roots), new_manifest)
        tx = self.transaction()
        intent = (tx / 'intent.json').read_bytes()
        recorded = json.loads((tx / 'result.json').read_bytes())
        self.assertEqual(recorded['intentSha256'], hashlib.sha256(intent).hexdigest())
        self.assertEqual(recorded['effect'], 'APPLIED')
        for p in tx.iterdir():
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
        self.assertEqual((tx / 'config.before.json').read_bytes(), self.before[self.roots['config']])
        self.assertTrue(all(call[1] == 'print' for call in self.calls))

    def test_rejects_stale_manifest_plan_and_unknown_launchctl_without_writes(self):
        self.prepare_apply()
        self.args.expected_manifest_sha256 = '0' * 64
        with self.assertRaisesRegex(SystemExit, 'CAS mismatch'):
            svc.cmd_fabric_backend_release(self.args)
        self.args.expected_manifest_sha256 = hashlib.sha256(self.before[self.roots['manifest']]).hexdigest()
        self.args.expected_plan_sha256 = '0' * 64
        with self.assertRaisesRegex(SystemExit, 'preview plan'):
            svc.cmd_fabric_backend_release(self.args)
        self.args.preflight_only = True
        self.prepare_apply()
        self.launch_error = True
        with self.assertRaisesRegex(SystemExit, 'state is indeterminate'):
            svc.cmd_fabric_backend_release(self.args)
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())

    def test_rejects_arbitrary_source_and_unmerged_commit(self):
        self.backend.write_text('export const unauthorized = true;\n')
        self.args.backend_sha256 = svc._sha256_file(self.backend)
        with self.assertRaisesRegex(SystemExit, 'differs from the merged source'):
            self.preview()
        self.backend.write_bytes((self.repo / svc.FABRIC_BACKEND_SOURCE).read_bytes())
        self.args.backend_sha256 = svc._sha256_file(self.backend)
        self.git('remote', 'set-url', 'origin', 'https://example.invalid/other.git')
        with self.assertRaisesRegex(SystemExit, 'exact Mastermind origin'):
            self.preview()
        self.git('remote', 'set-url', 'origin', svc.TYPED_GIT_REMOTE_URL)
        (self.repo / svc.FABRIC_BACKEND_SOURCE).write_text('export const future = true;\n')
        self.git('add', svc.FABRIC_BACKEND_SOURCE)
        self.git('commit', '-q', '-m', 'Unmerged fixture')
        self.args.release_commit = self.git('rev-parse', 'HEAD').strip()
        with self.assertRaisesRegex(SystemExit, 'Git evidence refused'):
            self.preview()
        self.assertEqual(self.snapshot(), self.before)

    def test_rejects_symlink_backend_and_unsealed_or_non_fabric_profile(self):
        original = self.backend.read_bytes()
        self.backend.unlink()
        self.backend.symlink_to(self.repo / svc.FABRIC_BACKEND_SOURCE)
        with self.assertRaises(SystemExit):
            self.preview()
        self.backend.unlink()
        self.backend.write_bytes(original)
        (self.roots['node_modules'] / 'fixture-package' / 'index.js').write_text('drift\n')
        with self.assertRaisesRegex(SystemExit, 'dependency tree hash mismatch'):
            self.preview()
        for path, value in self.before.items():
            path.write_bytes(value)
        config = json.loads(self.roots['config'].read_bytes())
        config['gitPublish'] = {'enabled': True}
        self.roots['config'].write_bytes(svc._fabric_release_json(config))
        manifest = json.loads(self.roots['manifest'].read_bytes())
        manifest['configHash'] = svc._sha256_file(self.roots['config'])
        self.roots['manifest'].write_bytes(svc._fabric_release_json(manifest))
        self.args.expected_manifest_sha256 = svc._sha256_file(self.roots['manifest'])
        with self.assertRaisesRegex(SystemExit, 'restricted profile'):
            self.preview()

    def test_precommit_failure_restores_exact_original_with_durable_evidence(self):
        self.prepare_apply()
        write = svc._atomic_write_bytes

        def fail_manifest(path, data, *args, **kwargs):
            if path == self.roots['manifest']:
                raise OSError('fixture failure before manifest replacement')
            return write(path, data, *args, **kwargs)

        with mock.patch.object(svc, '_atomic_write_bytes', side_effect=fail_manifest):
            with self.assertRaisesRegex(SystemExit, 'NOT_APPLIED; original sealed state restored'):
                svc.cmd_fabric_backend_release(self.args)
        self.assertEqual(self.snapshot(), self.before)
        tx = self.transaction()
        self.assertEqual(json.loads((tx / 'rollback.json').read_bytes())['effect'], 'ROLLED_BACK')
        self.assertEqual(json.loads((tx / 'result.json').read_bytes())['effect'], 'NOT_APPLIED')
        with self.assertRaisesRegex(SystemExit, 'retained transaction already exists'):
            svc.cmd_fabric_backend_release(self.args)

    def test_failure_after_manifest_replace_preserves_commit_and_unknown_effect(self):
        self.prepare_apply()
        write = svc._atomic_write_bytes

        def fail_after_manifest(path, data, *args, **kwargs):
            value = write(path, data, *args, **kwargs)
            if path == self.roots['manifest']:
                raise OSError('fixture failure after replacement')
            return value

        with mock.patch.object(svc, '_atomic_write_bytes', side_effect=fail_after_manifest):
            with self.assertRaisesRegex(SystemExit, 'EFFECT_UNKNOWN'):
                svc.cmd_fabric_backend_release(self.args)
        self.assertNotEqual(self.roots['manifest'].read_bytes(), self.before[self.roots['manifest']])
        self.assertEqual(svc._verify_staged_install(self.account, self.label, self.roots)['backend'], str(self.backend))
        tx = self.transaction()
        self.assertTrue((tx / 'intent.json').is_file())
        self.assertFalse((tx / 'rollback.json').exists())
        self.assertFalse((tx / 'result.json').exists())
        self.assertEqual(json.loads((tx / 'failure.json').read_bytes())['effect'], 'EFFECT_UNKNOWN')

    def test_concurrent_config_change_is_never_rolled_back_over(self):
        self.prepare_apply()
        write = svc._atomic_write_bytes
        alien = b'{"concurrent": "not our bytes"}\n'

        def inject_config_change(path, data, *args, **kwargs):
            result = write(path, data, *args, **kwargs)
            if path == self.roots['config']:
                path.write_bytes(alien)
            return result

        with mock.patch.object(svc, '_atomic_write_bytes', side_effect=inject_config_change):
            with self.assertRaisesRegex(SystemExit, 'EFFECT_UNKNOWN'):
                svc.cmd_fabric_backend_release(self.args)
        self.assertEqual(self.roots['config'].read_bytes(), alien)
        self.assertEqual(self.roots['manifest'].read_bytes(), self.before[self.roots['manifest']])
        self.assertFalse((self.transaction() / 'rollback.json').exists())

    def test_original_owner_lock_fences_apply_and_start(self):
        self.prepare_apply()
        with svc._c2_lifecycle_mutex(self.account):
            with self.assertRaisesRegex(SystemExit, 'already in progress'):
                svc.cmd_fabric_backend_release(self.args)
            with self.assertRaisesRegex(SystemExit, 'already in progress'):
                svc.cmd_start(SimpleNamespace(account=self.account))
            with self.assertRaisesRegex(SystemExit, 'already in progress'):
                svc.cmd_stop(SimpleNamespace(account=self.account))
        self.assertEqual(self.snapshot(), self.before)

    def test_intent_then_concurrent_edit_is_preserved_before_first_config_write(self):
        self.prepare_apply()
        persist = svc._fabric_release_new
        alien = b'{"concurrent": "edit after release intent"}\n'

        def edit_after_intent(path, data):
            value = persist(path, data)
            if path.name == 'intent.json':
                self.roots['config'].write_bytes(alien)
            return value

        with mock.patch.object(svc, '_fabric_release_new', side_effect=edit_after_intent):
            with self.assertRaisesRegex(SystemExit, 'EFFECT_UNKNOWN'):
                svc.cmd_fabric_backend_release(self.args)
        self.assertEqual(self.roots['config'].read_bytes(), alien)
        self.assertEqual(self.roots['manifest'].read_bytes(), self.before[self.roots['manifest']])

    def _install_legacy_fleet_status_profile(self):
        """Drop modern selectors, install a launcher, and seal the matching legacy fleetStatus.

        Mirrors the historical restricted install: fleetStatus is present, while
        modernFabricProtocol and backendMode are absent. The launcher is harmless
        and owned by the fixture so the existing safe regular-file hash check
        produces the same digest both when the fixture is sealed and when the
        owner re-derives fleet_status_config.
        """
        launcher = self.home / svc.FLEET_STATUS_LAUNCHER_REL
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text('#!/bin/sh\nexit 0\n')
        launcher.chmod(0o700)
        fleet_status = svc._fleet_status_config(self.home)
        self.assertIsNotNone(fleet_status)
        config = json.loads(self.roots['config'].read_bytes())
        config.pop('modernFabricProtocol', None)
        config.pop('backendMode', None)
        config['fleetStatus'] = fleet_status
        self.roots['config'].write_bytes(svc._fabric_release_json(config))
        manifest = json.loads(self.roots['manifest'].read_bytes())
        manifest['configHash'] = svc._sha256_file(self.roots['config'])
        self.roots['manifest'].write_bytes(svc._fabric_release_json(manifest))
        self.before = self.snapshot()
        self.args.expected_manifest_sha256 = svc._sha256_file(self.roots['manifest'])

    def _reseal_with_fleet_status(self, value):
        config = json.loads(self.roots['config'].read_bytes())
        config.pop('modernFabricProtocol', None)
        config.pop('backendMode', None)
        config['fleetStatus'] = value
        self.roots['config'].write_bytes(svc._fabric_release_json(config))
        manifest = json.loads(self.roots['manifest'].read_bytes())
        manifest['configHash'] = svc._sha256_file(self.roots['config'])
        self.roots['manifest'].write_bytes(svc._fabric_release_json(manifest))
        self.args.expected_manifest_sha256 = svc._sha256_file(self.roots['manifest'])
        self.before = self.snapshot()

    def test_regression_legacy_fleet_status_preview_and_apply_round_trip(self):
        """The pre-fix release refused any sealed config containing fleetStatus.

        The accepted legacy install lacks modernFabricProtocol/backendMode. After
        the fix, preview and apply preserve the legacy fleetStatus exactly while
        changing only args[0] in the config and the three documented manifest
        fields.
        """
        self._install_legacy_fleet_status_profile()
        preview = self.preview()
        self.assertEqual(preview['changedConfigFields'], ['args[0]'])
        self.assertEqual(preview['changedManifestFields'], ['backend', 'backendHash', 'configHash'])
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())
        self.args.preflight_only = False
        self.args.expected_plan_sha256 = preview['planSha256']
        result = self.capture(lambda: svc.cmd_fabric_backend_release(self.args))
        self.assertEqual(result['effect'], 'APPLIED')
        self.assertFalse(result['serviceStarted'])
        old_config = json.loads(self.before[self.roots['config']])
        new_config = json.loads(self.roots['config'].read_bytes())
        expected_config = copy.deepcopy(old_config)
        expected_config['args'][0] = str(self.backend)
        self.assertEqual(new_config, expected_config)
        self.assertEqual(new_config['fleetStatus'], old_config['fleetStatus'])
        self.assertNotIn('modernFabricProtocol', new_config)
        self.assertNotIn('backendMode', new_config)
        old_manifest = json.loads(self.before[self.roots['manifest']])
        new_manifest = json.loads(self.roots['manifest'].read_bytes())
        self.assertEqual({k for k in new_manifest if old_manifest[k] != new_manifest[k]},
                         {'backend', 'backendHash', 'configHash'})
        for path, data in self.before.items():
            if path not in (self.roots['config'], self.roots['manifest']):
                self.assertEqual(path.read_bytes(), data)

    def test_rejects_legacy_fleet_status_with_modern_protocol_selector(self):
        """A present modernFabricProtocol selector (even False) violates the legacy form."""
        self._install_legacy_fleet_status_profile()
        config = json.loads(self.roots['config'].read_bytes())
        config['modernFabricProtocol'] = False
        self.roots['config'].write_bytes(svc._fabric_release_json(config))
        manifest = json.loads(self.roots['manifest'].read_bytes())
        manifest['configHash'] = svc._sha256_file(self.roots['config'])
        self.roots['manifest'].write_bytes(svc._fabric_release_json(manifest))
        self.args.expected_manifest_sha256 = svc._sha256_file(self.roots['manifest'])
        self.before = self.snapshot()
        with self.assertRaisesRegex(SystemExit, 'legacy fleetStatus requires absent'):
            self.preview()
        self.assertEqual(self.snapshot(), self.before)

    def test_rejects_legacy_fleet_status_with_backend_mode_selector(self):
        """A present backendMode selector (even null) violates the legacy form."""
        self._install_legacy_fleet_status_profile()
        config = json.loads(self.roots['config'].read_bytes())
        config['backendMode'] = None
        self.roots['config'].write_bytes(svc._fabric_release_json(config))
        manifest = json.loads(self.roots['manifest'].read_bytes())
        manifest['configHash'] = svc._sha256_file(self.roots['config'])
        self.roots['manifest'].write_bytes(svc._fabric_release_json(manifest))
        self.args.expected_manifest_sha256 = svc._sha256_file(self.roots['manifest'])
        self.before = self.snapshot()
        with self.assertRaisesRegex(SystemExit, 'legacy fleetStatus requires absent'):
            self.preview()
        self.assertEqual(self.snapshot(), self.before)

    def test_rejects_legacy_fleet_status_with_invalid_field_types(self):
        """Legacy fleetStatus must satisfy exact type contract for all four keys."""
        launcher = self.home / svc.FLEET_STATUS_LAUNCHER_REL
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text('#!/bin/sh\nexit 0\n')
        launcher.chmod(0o700)
        base = svc._fleet_status_config(self.home)

        cases = (
            ({**base, 'enabled': 1}, 'legacy fleetStatus field types'),
            ({**base, 'enabled': None}, 'legacy fleetStatus field types'),
            ({**base, 'enabled': False}, 'legacy fleetStatus field types'),
            ({**base, 'timeoutMs': True}, 'legacy fleetStatus field types'),
            ({**base, 'timeoutMs': False}, 'legacy fleetStatus field types'),
            ({**base, 'timeoutMs': 15000.0}, 'legacy fleetStatus field types'),
            ({**base, 'launcherPath': 12345}, 'legacy fleetStatus field types'),
            ({**base, 'launcherPath': None}, 'legacy fleetStatus field types'),
            ({**base, 'launcherSha256': 12345}, 'legacy fleetStatus field types'),
            ({**base, 'launcherSha256': None}, 'legacy fleetStatus field types'),
            ({**base, 'extra': 'unauthorized'}, 'legacy fleetStatus requires exact'),
        )
        missing = dict(base)
        missing.pop('launcherSha256')
        all_cases = cases + ((missing, 'legacy fleetStatus requires exact'),)
        for value, expected_message in all_cases:
            self._reseal_with_fleet_status(value)
            with self.assertRaisesRegex(SystemExit, expected_message):
                self.preview()
            self.assertEqual(self.snapshot(), self.before)

    def test_rejects_legacy_fleet_status_with_owner_mismatch(self):
        """Legacy fleetStatus must equal the current owner's fresh output exactly."""
        self._install_legacy_fleet_status_profile()
        base = svc._fleet_status_config(self.home)
        cases = (
            ({**base, 'launcherPath': str(self.home / 'fake-launcher')}),
            ({**base, 'launcherSha256': 'a' * 64}),
            ({**base, 'timeoutMs': 12345}),
        )
        for value in cases:
            self._reseal_with_fleet_status(value)
            with self.assertRaisesRegex(SystemExit, 'legacy fleetStatus does not match owner'):
                self.preview()
            self.assertEqual(self.snapshot(), self.before)

    def test_rejects_legacy_fleet_status_when_owner_launcher_is_missing_or_unsafe(self):
        """None / missing / unsafe owner launcher must fail closed without writing."""
        self._install_legacy_fleet_status_profile()
        launcher = self.home / svc.FLEET_STATUS_LAUNCHER_REL
        # 1. Owner launcher deleted -> fresh _fleet_status_config returns None.
        launcher.unlink()
        with self.assertRaisesRegex(SystemExit, 'legacy fleetStatus owner launcher unavailable'):
            self.preview()
        self.assertEqual(self.snapshot(), self.before)
        # 2. Owner launcher replaced by a symlink -> safe regular-file hash raises.
        launcher.symlink_to(self.home / 'node')
        with self.assertRaisesRegex(SystemExit, 'Studio Direct control launcher'):
            self.preview()
        self.assertEqual(self.snapshot(), self.before)

    def test_legacy_fleet_status_apply_revalidates_after_state_change(self):
        """Apply revalidates under the existing lock; an earlier passing preview cannot bypass."""
        self._install_legacy_fleet_status_profile()
        preview = self.preview()
        self.assertEqual(preview['changedConfigFields'], ['args[0]'])
        self.args.preflight_only = False
        self.args.expected_plan_sha256 = preview['planSha256']
        # Tamper with the sealed config so the legacy form no longer holds.
        config = json.loads(self.roots['config'].read_bytes())
        config['modernFabricProtocol'] = True
        self.roots['config'].write_bytes(svc._fabric_release_json(config))
        manifest = json.loads(self.roots['manifest'].read_bytes())
        manifest['configHash'] = svc._sha256_file(self.roots['config'])
        self.roots['manifest'].write_bytes(svc._fabric_release_json(manifest))
        self.args.expected_manifest_sha256 = svc._sha256_file(self.roots['manifest'])
        with self.assertRaisesRegex(SystemExit, 'legacy fleetStatus requires absent'):
            svc.cmd_fabric_backend_release(self.args)
        # No service mutation: the transaction directory was never created.
        self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())

    def test_rejects_legacy_fleet_status_when_launcher_descriptor_owner_changes(self):
        """Wrong-owner launcher descriptor fails closed even with valid bytes.

        The sealed config and launcher bytes stay valid; only the descriptor
        st_uid the validator sees is narrow-mocked to a different owner. The
        rest of the validator runs and the file system itself is untouched
        (no chown, no process-wide UID change, no whole-validator mock).
        """
        self._install_legacy_fleet_status_profile()
        launcher = self.home / svc.FLEET_STATUS_LAUNCHER_REL
        # _fabric_release_bytes consults both os.open and os.fstat. Patch only
        # these two module-level names so the launcher's fstat reports a
        # different st_uid. Every other path uses the real syscall.
        real_open = os.open
        real_fstat = os.fstat
        launcher_path = os.path.realpath(str(launcher))
        launcher_fds: set[int] = set()

        def tracking_open(path, *args, **kwargs):
            fd = real_open(path, *args, **kwargs)
            try:
                opened = os.path.realpath(os.fspath(path))
            except (TypeError, ValueError):
                opened = ''
            if opened == launcher_path:
                launcher_fds.add(fd)
            return fd

        def faked_fstat(fd):
            result = real_fstat(fd)
            if fd in launcher_fds:
                # os.stat_result is a structseq; rebuild with st_uid overridden.
                # st_uid is at positional index 4 in the standard sequence.
                return os.stat_result(
                    result[:4]
                    + (((result.st_uid + 1) % (2 ** 32),) if result.st_uid != (2 ** 32) - 1 else (0,))
                    + result[5:]
                )
            return result

        with mock.patch('os.open', tracking_open), mock.patch('os.fstat', faked_fstat):
            with self.assertRaisesRegex(SystemExit, 'unsafe or too large'):
                self.preview()
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())

    def test_legacy_fleet_status_preview_then_apply_drift_refuses_with_seal_intact(self):
        """Apply revalidates freshly; a passing preview cannot bypass a later
        launcher-byte change. Config, manifest, expected_manifest_sha256 and
        expected_plan_sha256 stay pinned. Sealed files remain unchanged and
        no transaction is created.
        """
        self._install_legacy_fleet_status_profile()
        preview = self.prepare_apply()
        launcher = self.home / svc.FLEET_STATUS_LAUNCHER_REL
        original_launcher_bytes = launcher.read_bytes()
        launcher.write_text('#!/bin/sh\necho drifted launcher\n')
        launcher.chmod(0o700)
        try:
            with self.assertRaisesRegex(SystemExit, 'legacy fleetStatus does not match owner'):
                svc.cmd_fabric_backend_release(self.args)
            self.assertEqual(self.snapshot(), self.before)
            self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())
        finally:
            launcher.write_bytes(original_launcher_bytes)
            launcher.chmod(0o700)


class ModernBackendReleaseTests(BackendReleaseFixture, unittest.TestCase):
    ACCOUNT = svc.FABRIC_BACKEND_MODERN_ACCOUNT
    PORT = svc.FABRIC_BACKEND_MODERN_PORT
    MODERN = True

    def reseal_config(self, config, **manifest_fields):
        """Keep the fixture seal valid so profile refusals exercise admission."""
        self.roots['config'].write_bytes(svc._fabric_release_json(config))
        manifest = json.loads(self.roots['manifest'].read_bytes())
        manifest.update(manifest_fields)
        manifest['configHash'] = svc._sha256_file(self.roots['config'])
        self.roots['manifest'].write_bytes(svc._fabric_release_json(manifest))
        self.args.expected_manifest_sha256 = svc._sha256_file(self.roots['manifest'])
        self.before = self.snapshot()

    def assert_profile_refused_without_write(self):
        with self.assertRaisesRegex(SystemExit, 'modern profile|restricted profile'):
            self.preview()
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())

    def test_modern_13_file_preview_apply_preserves_every_other_byte(self):
        self.assertEqual(self.account, 'fabric-c3-570f6f34')
        original_manifest = json.loads(self.before[self.roots['manifest']])
        self.assertEqual(len(original_manifest['files']), 13)
        self.assertIn('modern-fabric-http.mjs', original_manifest['files'])
        original_config = json.loads(self.before[self.roots['config']])
        self.assertIs(original_config['modernFabricProtocol'], True)
        self.assertEqual(original_config['backendMode'], 'shared-account')
        self.assertEqual(original_config['port'], 45280)
        self.assertNotIn('fleetStatus', original_config)
        # Exercise every existing round-trip, seal, transaction and no-lifecycle
        # assertion against the modern seat, without inheriting legacy-only tests.
        BackendReleaseTests.test_live_preview_has_no_effect_and_exact_diff_then_apply_preserves_seal(self)
        expected_config = {**original_config, 'args': [str(self.backend), *original_config['args'][1:]]}
        expected_config_bytes = svc._fabric_release_json(expected_config)
        self.assertEqual(self.roots['config'].read_bytes(), expected_config_bytes)
        expected_manifest = {**original_manifest, 'backend': str(self.backend),
            'backendHash': self.args.backend_sha256,
            'configHash': hashlib.sha256(expected_config_bytes).hexdigest()}
        self.assertEqual(self.roots['manifest'].read_bytes(), svc._fabric_release_json(expected_manifest))

    def test_neighbor_accounts_cannot_release_or_acquire_enrolled_lock(self):
        for account in ('fabric-c3-570f6f35', 'fabric-c3-other', 'subagent-fabric-c3-extra'):
            with self.subTest(account=account):
                args = SimpleNamespace(**{**vars(self.args), 'account': account})
                with self.assertRaisesRegex(SystemExit, 'explicitly enrolled restricted c3 account'):
                    svc.cmd_fabric_backend_release(args)
                with self.assertRaisesRegex(SystemExit, 'cannot select another account'):
                    with svc._c2_lifecycle_mutex(account):
                        self.fail('neighbor acquired an enrolled lifecycle lock')
                self.assertFalse(svc._build_runtime_roots(account)['base'].exists())
                self.assertEqual(self.snapshot(), self.before)

    def test_modern_selectors_are_required_with_exact_types_and_values(self):
        original = json.loads(self.before[self.roots['config']])
        cases = (
            ('modernFabricProtocol', False), ('modernFabricProtocol', None),
            ('modernFabricProtocol', 1), ('modernFabricProtocol', 'true'),
            ('backendMode', 'per-session'), ('backendMode', None),
            ('backendMode', False), ('backendMode', 'SHARED-ACCOUNT'),
        )
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.reseal_config({**original, key: value})
                self.assert_profile_refused_without_write()
        for key in ('modernFabricProtocol', 'backendMode'):
            with self.subTest(missing=key):
                config = {k: v for k, v in original.items() if k != key}
                self.reseal_config(config)
                self.assert_profile_refused_without_write()

    def test_modern_port_is_the_exact_enrolled_integer(self):
        original = json.loads(self.before[self.roots['config']])
        for port in (45119, 45281, '45280', 45280.0, True, None):
            with self.subTest(port=port):
                self.reseal_config({**original, 'port': port}, port=port)
                self.assert_profile_refused_without_write()
        self.reseal_config({k: v for k, v in original.items() if k != 'port'}, port=45280)
        self.assert_profile_refused_without_write()

    def test_modern_capability_boundary_cannot_be_broadened_or_normalized(self):
        original = json.loads(self.before[self.roots['config']])
        for key in ('fleetStatus', 'repositoryWorkspaces', 'commissionPublication',
                    'fleetRouting', 'publicUrl'):
            with self.subTest(forbidden=key):
                self.reseal_config({**original, key: None})
                self.assert_profile_refused_without_write()
        for key, value in (('fabricOnly', False), ('fabricOnly', 1),
                           ('gitPublish', True), ('gitPublish', 0),
                           ('paperDesign', True), ('paperDesign', 0),
                           ('host', 'localhost'), ('host', '0.0.0.0'),
                           ('accountLabel', 'fabric-c3-570f6f35')):
            with self.subTest(key=key, value=value):
                self.reseal_config({**original, key: value})
                self.assert_profile_refused_without_write()

    def test_modern_release_and_lifecycle_share_the_same_lock(self):
        self.prepare_apply()
        with svc._c2_lifecycle_mutex(self.account):
            with self.assertRaisesRegex(SystemExit, 'already in progress'):
                svc.cmd_fabric_backend_release(self.args)
            for operation in (svc.cmd_start, svc.cmd_stop, svc.cmd_seal_runtime):
                with self.subTest(operation=operation.__name__):
                    with self.assertRaisesRegex(SystemExit, 'already in progress'):
                        operation(SimpleNamespace(account=self.account))
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())

    def test_legacy_lock_does_not_block_modern_lock_or_release(self):
        legacy_roots = svc._build_runtime_roots(svc.FABRIC_BACKEND_ACCOUNT)
        legacy_roots['state'].mkdir(mode=0o700, parents=True)
        self.prepare_apply()
        with svc._c2_lifecycle_mutex(svc.FABRIC_BACKEND_ACCOUNT):
            legacy_lock = legacy_roots['state'] / svc.C2_LIFECYCLE_LOCK_NAME
            legacy_identity = (legacy_lock.stat().st_dev, legacy_lock.stat().st_ino)
            with svc._c2_lifecycle_mutex(self.account):
                modern_lock = self.roots['state'] / svc.C2_LIFECYCLE_LOCK_NAME
                self.assertNotEqual(legacy_identity, (modern_lock.stat().st_dev, modern_lock.stat().st_ino))
            result = self.capture(lambda: svc.cmd_fabric_backend_release(self.args))
            self.assertEqual(result['effect'], 'APPLIED')
            self.assertEqual(legacy_identity, (legacy_lock.stat().st_dev, legacy_lock.stat().st_ino))
            self.assertEqual(legacy_lock.read_bytes(), b'')
            self.assertFalse(legacy_roots['config'].exists())
            self.assertFalse(legacy_roots['manifest'].exists())
            self.assertFalse((legacy_roots['state'] / 'fabric-backend-releases').exists())

    def test_malformed_named_absence_blocks_modern_release_before_intent(self):
        self.prepare_apply()
        exact_absence = (f'Bad request.\nCould not find service "{self.label}" '
                         f'in domain for user gui: {os.getuid()}\n')
        cases = (
            svc.CmdResult(1, '', 'permission denied'),
            svc.CmdResult(113, 'unexpected output', exact_absence),
            svc.CmdResult(113, '', exact_absence + '\n'),
            svc.CmdResult(113, '', exact_absence.replace(self.account, svc.FABRIC_BACKEND_ACCOUNT)),
            svc.CmdResult(0, '', ''),
        )
        original_run = svc._run
        for result in cases:
            def run(argv, **kwargs):
                if argv[0] == 'launchctl':
                    self.assertEqual(argv, ['launchctl', 'print', svc._launchd_target(self.label)])
                    return result
                return original_run(argv, **kwargs)
            with self.subTest(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr):
                with mock.patch.object(svc, '_run', side_effect=run):
                    with self.assertRaisesRegex(SystemExit, 'state is indeterminate'):
                        svc.cmd_fabric_backend_release(self.args)
                self.assertEqual(self.snapshot(), self.before)
                self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())

    def test_modern_stop_preserves_unknown_after_bootout_until_exact_absence(self):
        target = svc._launchd_target(self.label)
        running = svc.CmdResult(0, f'{target} = {{\n'
            f'\tpath = {self.roots["plist"]}\n\tstate = running\n\tpid = 4321\n}}\n', '')
        exact_absence = svc.CmdResult(113, '',
            f'Bad request.\nCould not find service "{self.label}" '
            f'in domain for user gui: {os.getuid()}\n')
        for after_bootout in (svc.CmdResult(113, '', 'unverified absence'), exact_absence):
            calls = []
            observations = iter((running, after_bootout))

            def run(argv, **kwargs):
                calls.append(argv)
                if argv == ['launchctl', 'print', target]:
                    return next(observations)
                self.assertEqual(argv, ['launchctl', 'bootout', target])
                return svc.CmdResult(0, '', '')

            with self.subTest(stderr=after_bootout.stderr):
                with mock.patch.object(svc, '_run', side_effect=run):
                    if after_bootout is exact_absence:
                        result = self.capture(lambda: svc.cmd_stop(SimpleNamespace(account=self.account)))
                        self.assertIs(result['stopped'], True)
                        self.assertEqual(result['account'], self.account)
                    else:
                        with self.assertRaisesRegex(SystemExit, 'EFFECT_UNKNOWN after bootout; service absence is unverified'):
                            svc.cmd_stop(SimpleNamespace(account=self.account))
                self.assertEqual(calls, [
                    ['launchctl', 'print', target],
                    ['launchctl', 'bootout', target],
                    ['launchctl', 'print', target],
                ])
                self.assertEqual(self.snapshot(), self.before)


if __name__ == '__main__':
    unittest.main()
