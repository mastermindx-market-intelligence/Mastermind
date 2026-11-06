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
import re
import signal
import sys
from pathlib import Path
import socket
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
            expected_plan_sha256=None, preflight_only=True,
            source_provenance=svc.FABRIC_RELEASE_LOCAL_PROVENANCE)

    def enable_public(self):
        self.args.source_provenance = svc.FABRIC_RELEASE_PUBLIC_PROVENANCE
        self.tree_sha = self.git('rev-parse', self.commit + '^{tree}').strip()
        self.source_sha = self.git('rev-parse', self.commit + ':' + svc.FABRIC_BACKEND_SOURCE).strip()
        self.source_size = self.backend.stat().st_size
        self.public_calls = []
        self.public_override = None
        self.local_git_fail_closed = mock.patch.object(svc, '_fabric_release_local_source',
            side_effect=AssertionError('public mode entered local Git'))
        self.local_git_fail_closed.start()
        self.addCleanup(self.local_git_fail_closed.stop)

        def metadata(url, *, deadline=None):
            self.public_calls.append(url)
            if self.public_override is not None:
                return self.public_override(url)
            prefix = svc.FABRIC_PUBLIC_API_ROOT
            if url == prefix + '/git/ref/heads/master':
                return {'ref': svc.FABRIC_PUBLIC_REF, 'object': {'type': 'commit', 'sha': self.commit}}
            if url == prefix + '/git/commits/' + self.commit:
                return {'sha': self.commit, 'tree': {'sha': self.tree_sha}}
            if url == prefix + '/git/trees/' + self.tree_sha:
                return {'sha': self.tree_sha, 'truncated': False, 'tree': [
                    {'path': 'integrations', 'mode': '040000', 'type': 'tree', 'sha': '1' * 40}]}
            if url == prefix + '/git/trees/' + '1' * 40:
                return {'sha': '1' * 40, 'truncated': False, 'tree': [
                    {'path': 'studio_direct_mcp', 'mode': '040000', 'type': 'tree', 'sha': '2' * 40}]}
            if url == prefix + '/git/trees/' + '2' * 40:
                return {'sha': '2' * 40, 'truncated': False, 'tree': [
                    {'path': 'fabric-backend.mjs', 'mode': '100644', 'type': 'blob',
                     'sha': self.source_sha, 'size': self.source_size}]}
            raise AssertionError('non-canonical public metadata URL: ' + url)

        def raw_metadata(url, *, deadline=None):
            saved, self.public_override = self.public_override, None
            try:
                return metadata(url)
            finally:
                self.public_override = saved
        self.raw_metadata = raw_metadata
        self.metadata = mock.patch.object(svc, '_fabric_public_https_json', side_effect=metadata)
        self.metadata.start()
        self.addCleanup(self.metadata.stop)

    def assert_public_refused_without_write(self, pattern='Fabric'):
        with self.assertRaisesRegex(SystemExit, pattern):
            self.preview()
        self.assertEqual(self.snapshot(), self.before)
        self.args.expected_manifest_sha256 = svc._sha256_file(self.roots['manifest'])
        self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())

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

        cases = [
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
        ]
        missing = dict(base)
        missing.pop('launcherSha256')
        all_cases = cases + [(missing, 'legacy fleetStatus requires exact')]
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


    def test_final_public_provenance_validation_cannot_cross_deadline(self):
        self.enable_public()
        real_read = svc._fabric_release_bytes
        clock = [100.0]
        def late_backend(path, **kwargs):
            value = real_read(path, **kwargs)
            if path == self.backend:
                clock[0] = 111.0
            return value
        with mock.patch.object(svc.time, 'monotonic', side_effect=lambda: clock[0]), \
             mock.patch.object(svc, '_fabric_release_bytes', side_effect=late_backend), \
             mock.patch.object(svc, '_fabric_release_new',
                               side_effect=AssertionError('transaction writes forbidden')) as intent:
            with self.assertRaisesRegex(SystemExit, 'deadline exceeded'):
                self.preview()
        intent.assert_not_called()
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())

    def test_shared_absolute_deadline_exhausts_on_actual_fifth_transport(self):
        self.enable_public()
        self.metadata.stop()
        actual_https_json = svc._fabric_public_https_json
        actual_popen = svc.subprocess.Popen
        observations, children = [], []
        def document(url, *, deadline):
            observations.append((url, deadline))
            if len(observations) < 5:
                return self.raw_metadata(url)
            # The fifth real finite child gets a typed streaming response.
            # The actual bounded reader runs there, below each socket timeout,
            # with 20 actual bytes over 2 seconds > .2-second total deadline.
            # Transport-level only: exact finite child with a response which
            # drips below inactivity but > shared TTL. No monkeypatched timeout.
            script = svc._FABRIC_PUBLIC_READ_CHILD.replace(
                "private_service._fabric_public_bounded_read(canonical_source[2], deadline)", """import time
class Response:
    status = 200
    def read(self, limit):
        for byte in b'{}' * 40:
            time.sleep(.025)
        return b'{}'
    def close(self):
        pass
class Opener:
    def open(self, request, timeout):
        return Response()
private_service._fabric_public_opener = Opener
private_service._fabric_public_bounded_read(canonical_source[2], deadline)
""")
            with mock.patch.object(svc, '_FABRIC_PUBLIC_READ_CHILD', script):
                return actual_https_json(url, deadline=deadline)
        def observe(*args, **kwargs):
            child = actual_popen(*args, **kwargs)
            children.append(child)
            return child
        with mock.patch.object(svc, 'FABRIC_PUBLIC_TIMEOUT_SECONDS', 0.20), \
             mock.patch.object(svc, '_fabric_public_https_json', side_effect=document), \
             mock.patch.object(svc.subprocess, 'Popen', side_effect=observe), \
             mock.patch.object(svc, '_fabric_release_new', side_effect=AssertionError('intent/config/manifest writes forbidden')) as intent_write:
            with self.assertRaisesRegex(SystemExit, 'deadline exceeded'):
                self.preview()
        intent_write.assert_not_called()
        self.assertEqual(len(observations), 5)
        self.assertEqual(len(children), 1)
        self.assertIn(children[0].returncode, (-signal.SIGKILL, -signal.SIGALRM))
        self.assertEqual(len({item[1] for item in observations}), 1)
        print('FINAL_DOCUMENT_ABSOLUTE_DEADLINE documents=%d child_rc=%d' % (len(observations), children[0].returncode))
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())
        self.assertFalse((self.home / '.forbidden-intent').exists())
        for child in children:
            with self.assertRaises(OSError):
                os.kill(child.pid, 0)


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
        self.assertEqual(len(original_manifest['files']), len(svc.STAGE_FILES))
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

    def test_public_provenance_modern_preview_apply_and_zero_private_git(self):
        self.enable_public()
        self.repo.rename(self.home / 'forbidden-public-mode-repo-must-not-be-read')
        preview = self.preview()
        proof = preview['releaseProvenance']
        self.assertEqual(proof['sourceProvenance'], 'github_public_protected_v1')
        self.assertEqual(proof['repository'], 'mastermindx-market-intelligence/Mastermind')
        self.assertEqual(proof['ref'], 'refs/heads/master')
        self.assertEqual(proof['commitTree'], self.tree_sha)
        self.assertEqual(proof['backendGitBlob'], self.source_sha)
        self.assertEqual(proof['backendSize'], self.source_size)
        self.assertEqual(proof['stagedBackendPath'], str(self.backend))
        self.prepare_apply()
        result = self.capture(lambda: svc.cmd_fabric_backend_release(self.args))
        self.assertEqual(result['effect'], 'APPLIED')
        self.assertEqual(json.loads((self.transaction() / 'intent.json').read_text())['releaseProvenance'], proof)

    def test_public_provenance_refuses_source_drift_and_never_falls_back(self):
        self.enable_public()
        self.prepare_apply()
        original = self.public_override
        self.public_override = lambda url: ({'ref': svc.FABRIC_PUBLIC_REF,
            'object': {'type': 'commit', 'sha': 'f' * 40}}
            if url.endswith('/git/ref/heads/master') else original(url))
        with self.assertRaisesRegex(SystemExit, 'protected master'):
            svc.cmd_fabric_backend_release(self.args)
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())

    def test_public_provenance_refuses_wrong_tree_path_mode_blob_sha_and_size(self):
        self.enable_public()
        cases = (
            ('commitSha', {'sha': 'f' * 40, 'tree': {'sha': self.tree_sha}}),
            ('rootTree', {'sha': self.tree_sha, 'truncated': False, 'tree': []}),
            ('treeType', {'sha': self.tree_sha, 'truncated': False, 'tree': [
                {'path': 'integrations', 'mode': '040000', 'type': 'blob', 'sha': '1' * 40}]}),
        )
        for name, value in cases:
            with self.subTest(case=name):
                self.public_override = lambda url, value=value: value if (
                    (name in ('commitSha', 'commitTree') and '/git/commits/' in url)
                    or (name == 'ref' and '/git/ref/' in url)
                    or (name in ('rootTree', 'treeType') and '/git/trees/' in url)
                ) else self.raw_metadata(url)
                self.assert_public_refused_without_write()
        self.public_override = None
        for key, value in (('mode', '120000'), ('type', 'tree'), ('sha', '0' * 40), ('size', self.source_size + 1)):
            with self.subTest(field=key, value=value):
                entry = {'path': 'fabric-backend.mjs', 'mode': '100644', 'type': 'blob',
                         'sha': self.source_sha, 'size': self.source_size}
                entry[key] = value
                self.public_override = lambda url, entry=entry: {'sha': '2' * 40, 'truncated': False,
                    'tree': [entry]} if url.endswith('/git/trees/' + '2' * 40) else self.raw_metadata(url)
                self.assert_public_refused_without_write()

    def test_public_provenance_refuses_staged_bytes_and_inode_replacement(self):
        self.enable_public()
        original = self.backend.read_bytes()
        self.backend.write_bytes(original + b'// drift\n')
        self.assert_public_refused_without_write('differs from the public source')

    def test_public_provenance_refuses_staged_inode_replacement_before_write(self):
        self.enable_public()
        self.prepare_apply()
        replacement = self.backend.with_suffix('.replacement')
        replacement.write_bytes(self.backend.read_bytes())
        replacement.replace(self.backend)
        with self.assertRaisesRegex(SystemExit, 'preview plan|changed before write'):
            svc.cmd_fabric_backend_release(self.args)
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())

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
                        # Persistently unverified absence remains EFFECT_UNKNOWN
                        # at the existing settle deadline; no duplicate bootout.
                        with mock.patch.object(svc.time, "monotonic", side_effect=[100.0, 111.0]):
                            with self.assertRaisesRegex(SystemExit, 'EFFECT_UNKNOWN after bootout; service absence is unverified'):
                                svc.cmd_stop(SimpleNamespace(account=self.account))
                self.assertEqual(calls, [
                    ['launchctl', 'print', target],
                    ['launchctl', 'bootout', target],
                    ['launchctl', 'print', target],
                ])
                self.assertEqual(self.snapshot(), self.before)


    def test_apply_interleaving_after_first_source_before_second_is_refused(self):
        self.enable_public()
        self.prepare_apply()
        actual_source = svc._fabric_release_source
        completed = [0]
        def source(commit, sha, provenance=svc.FABRIC_RELEASE_LOCAL_PROVENANCE):
            result = actual_source(commit, sha, provenance)
            completed[0] += 1
            if completed[0] == 1:
                replacement = self.backend.with_suffix('.interleaved')
                replacement.write_bytes(self.backend.read_bytes())
                replacement.replace(self.backend)
            return result
        with mock.patch.object(svc, '_fabric_release_source', side_effect=source):
            with self.assertRaisesRegex(SystemExit, 'changed before write'):
                svc.cmd_fabric_backend_release(self.args)
        self.assertEqual(completed[0], 2)
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())

    def test_public_ref_interleaving_refuses_before_second_transaction(self):
        self.enable_public()
        self.prepare_apply()
        actual_metadata = self.raw_metadata
        observations = []
        def between_complete_source_observations(url, *, deadline=None):
            observations.append(url)
            if len(observations) == 6:
                # All five first-plan documents completed. Change the protected
                # ref immediately before apply's second source observation returns.
                # raw_metadata deliberately restores this override after return;
                # mutating it here alone would erase the controlled interleaving.
                self.public_override = actual_metadata
                return {'ref': svc.FABRIC_PUBLIC_REF,
                        'object': {'type': 'commit', 'sha': 'f' * 40}}
            return actual_metadata(url)
        self.public_override = between_complete_source_observations
        with self.assertRaisesRegex(SystemExit, 'protected master'):
            svc.cmd_fabric_backend_release(self.args)
        self.assertEqual(len(observations), 6)
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse((self.roots['state'] / 'fabric-backend-releases').exists())


class PublicProvenanceTransportTests(unittest.TestCase):
    URL = svc.FABRIC_PUBLIC_API_ROOT + '/git/ref/heads/master'

    def test_fixed_direct_transport_under_ambient_proxy_credentials(self):
        env = {name: 'http://proxy-user:proxy-pass@proxy.invalid:8888'
               for name in ('https_proxy', 'HTTPS_PROXY', 'http_proxy', 'HTTP_PROXY',
                            'all_proxy', 'ALL_PROXY')}
        with mock.patch.dict(os.environ, env), \
             mock.patch.object(svc.urllib.request, 'getproxies',
                               side_effect=AssertionError('ambient proxies discovered')), \
             mock.patch.object(socket, 'create_connection',
                               side_effect=AssertionError('network forbidden')):
            opener = svc._fabric_public_opener()
        self.assertFalse(any(isinstance(item, svc.urllib.request.ProxyHandler)
                             and item.proxies for item in opener.handlers))
        request = svc.urllib.request.Request(self.URL)
        self.assertFalse(request.has_header('Authorization'))
        self.assertFalse(request.has_header('Proxy-authorization'))

    def test_actual_opener_has_no_proxy_handlers_and_keeps_verified_https(self):
        env = {name: 'http://proxy-user:proxy-pass@proxy.invalid:8888'
               for name in ('https_proxy', 'HTTPS_PROXY', 'http_proxy', 'HTTP_PROXY',
                            'all_proxy', 'ALL_PROXY')}
        import ssl
        with mock.patch.dict(os.environ, env), \
             mock.patch.object(ssl, '_create_unverified_context',
                               side_effect=AssertionError('TLS verification disabled')):
            opener = svc._fabric_public_opener()
        proxies = [item for item in opener.handlers if isinstance(item, svc.urllib.request.ProxyHandler)]
        https = [item for item in opener.handlers if isinstance(item, svc.urllib.request.HTTPSHandler)]
        self.assertEqual(proxies, [])
        self.assertFalse(any(isinstance(item, (svc.urllib.request.HTTPBasicAuthHandler,
                                              svc.urllib.request.HTTPCookieProcessor))
                             for item in opener.handlers))
        context = https[0]._context or ssl._create_default_https_context()
        self.assertEqual(context.check_hostname, True)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertNotIn('http_error_302', opener.handle_open.get('https', {}))

    def test_genuine_redirect_handler_response_is_refused_and_closed(self):
        unexpected, retained_errors = [], []
        class Opener:
            def __init__(self):
                self.production = svc._fabric_public_opener()
            def open(self, request, timeout):
                response = io.BytesIO(b'{}')
                unexpected.append(response)
                response.close = mock.Mock(wraps=response.close)
                response.code = 302
                response.msg = 'Found'
                response.headers = {'Location': 'https://elsewhere.invalid/x'}
                try:
                    self.production.error('https', request, response, 302, 'Found', response.headers)
                except svc.urllib.error.HTTPError as error:
                    # Retain the owner: garbage collection cannot satisfy close.
                    retained_errors.append(error)
                    raise
        with mock.patch.object(svc, '_fabric_public_opener', return_value=Opener()):
            with self.assertRaisesRegex(SystemExit, 'bounded GitHub metadata unavailable'):
                svc._fabric_public_bounded_read(self.URL, svc.time.monotonic() + 2)
        self.assertEqual(len(unexpected), 1)
        self.assertEqual(len(retained_errors), 1)
        self.assertTrue(retained_errors[0].closed)
        self.assertEqual(unexpected[0].close.call_count, 1)
        self.assertTrue(unexpected[0].closed)

    def test_non_200_response_and_bad_status_are_closed_and_refused(self):
        responses = []
        class Response:
            status = 503
            def __init__(self):
                responses.append(self)
                self.close = mock.Mock(wraps=self._close)
                self.closed = False
            def _close(self):
                self.closed = True
            def read(self, size):
                raise AssertionError('status refused before body')
        class Opener:
            def open(self, request, timeout):
                return Response()
        with mock.patch.object(svc, '_fabric_public_opener', return_value=Opener()):
            with self.assertRaisesRegex(SystemExit, 'GitHub metadata refused'):
                svc._fabric_public_bounded_read(self.URL, svc.time.monotonic() + 2)
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0].close.call_count, 1)
        self.assertTrue(responses[0].closed)

    def test_invalid_urls_and_sha_types_have_zero_transport(self):
        valid = self.URL
        bad = [None, 1, {}, 'https://example.invalid/x', svc.FABRIC_PUBLIC_API_ROOT,
               svc.FABRIC_PUBLIC_API_ROOT + '/../other',
               svc.FABRIC_PUBLIC_API_ROOT + '/git/ref/heads/master/',
               svc.FABRIC_PUBLIC_API_ROOT + '/git/ref/heads/master?x=1',
               svc.FABRIC_PUBLIC_API_ROOT + '/git/ref/heads/master#x',
               svc.FABRIC_PUBLIC_API_ROOT + '/git/ref/heads/master%2f..%2fother',
               svc.FABRIC_PUBLIC_API_ROOT + '/git/ref/heads/master/other',
               svc.FABRIC_PUBLIC_API_ROOT + '@example.invalid/git/ref/heads/master',
               svc.FABRIC_PUBLIC_API_ROOT + '/git/commits/' + 'A' * 40,
               svc.FABRIC_PUBLIC_API_ROOT + '/git/trees/' + 'a' * 39,
               svc.FABRIC_PUBLIC_API_ROOT + '/git/trees/' + 'a' * 40 + '.git']
        with mock.patch.object(svc, '_fabric_public_opener',
                               side_effect=AssertionError('transport must not be constructed')) as transport:
            for url in bad:
                with self.subTest(url=url), self.assertRaisesRegex(SystemExit, 'non-canonical'):
                    svc._fabric_public_https_json(url)
        transport.assert_not_called()

    def test_intermediate_tree_sha_is_validated_before_transport(self):
        for value in (None, 1, '', 'A' * 40, 'a' * 39, 'a' * 40 + '/../other', '../other'):
            with self.subTest(value=value):
                with mock.patch.object(svc, '_fabric_public_https_json',
                                       return_value={'sha': '1' * 40, 'truncated': False, 'tree': [
                                           {'path': 'integrations', 'mode': '040000',
                                            'type': 'tree', 'sha': value}]}) as metadata:
                    args = SimpleNamespace(account=svc.FABRIC_BACKEND_ACCOUNT,
                                           release_commit='1' * 40, backend_sha256='a' * 64)
                    # Direct public-provenance calls stop at the root's first child,
                    # before creating a URL from the malformed child SHA.
                    commit = {'sha': '1' * 40, 'tree': {'sha': '1' * 40}}
                    metadata.side_effect = lambda url, deadline=None: (
                        {'ref': svc.FABRIC_PUBLIC_REF,
                         'object': {'type': 'commit', 'sha': '1' * 40}}
                        if '/git/ref/' in url else commit if '/git/commits/' in url else
                        {'sha': '1' * 40, 'truncated': False, 'tree': [
                            {'path': 'integrations', 'mode': '040000', 'type': 'tree', 'sha': value}]})
                    with self.assertRaisesRegex(SystemExit, 'intermediate tree'):
                        svc._fabric_public_provenance('1' * 40, 'a' * 64)
                self.assertEqual(metadata.call_count, 3)


    def test_strict_json_bounded_deadline_size_and_pre_expiry_transport(self):
        with mock.patch.object(svc, '_fabric_public_https_json_child', return_value=b'{}') as finite_read:
            self.assertEqual(svc._fabric_public_https_json(self.URL), {})
            self.assertEqual(finite_read.call_count, 1)
        for payload in (b'{', b'{"x":1,"x":2}', b'[]', b'{"x":NaN}',
                        b' ' * (svc.FABRIC_PUBLIC_JSON_LIMIT + 1)):
            with self.subTest(kind=payload[:20], size=len(payload)):
                with mock.patch.object(svc, '_fabric_public_https_json_child', return_value=payload):
                    with self.assertRaisesRegex(SystemExit, 'strict GitHub JSON|JSON object required|too large'):
                        svc._fabric_public_https_json(self.URL)
        with mock.patch.object(svc.subprocess, 'Popen', side_effect=AssertionError('expired before child')) as spawn:
            with self.assertRaisesRegex(SystemExit, 'deadline exceeded'):
                svc._fabric_public_https_json(self.URL, deadline=svc.time.monotonic() - 1)
        spawn.assert_not_called()

    def test_deadline_is_checked_after_strict_parsing(self):
        real_loads = json.loads
        def late_parse(*args, **kwargs):
            value = real_loads(*args, **kwargs)
            clock[0] = 11.0
            return value
        clock = [9.0]
        with mock.patch.object(svc.time, 'monotonic', side_effect=lambda: clock[0]), \
             mock.patch.object(svc, '_fabric_public_https_json_child', return_value=b'{}'), \
             mock.patch.object(svc.json, 'loads', side_effect=late_parse):
            with self.assertRaisesRegex(SystemExit, 'deadline exceeded'):
                svc._fabric_public_https_json(self.URL, deadline=10.0)

    def test_captured_source_child_never_imports_matching_bytecode(self):
        import importlib.util
        import importlib._bootstrap_external
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'private_service.py'
            good = Path(svc.__file__).read_bytes()
            source.write_bytes(good)
            marker = root / 'bytecode-executed'
            payload = compile("from pathlib import Path\nPath(%r).write_text('bad')\n" % str(marker),
                              str(source), 'exec')
            # Ask the actual isolated interpreter: Apple source-mode Python
            # can use a cache prefix which -I deliberately ignores.
            probe = subprocess.run([sys.executable, '-I', '-S', '-B', '-c',
                                    'import importlib.util,sys;print(importlib.util.cache_from_source(sys.argv[1]))',
                                    str(source)], capture_output=True, text=True, timeout=4, check=True)
            cache = Path(probe.stdout.strip())
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(importlib._bootstrap_external._code_to_timestamp_pyc(
                payload, int(source.stat().st_mtime), len(good)))
            # A genuine normal import establishes this exact cache is executable.
            control = subprocess.run(
                [sys.executable, '-I', '-S', '-B', '-c',
                 'import sys;sys.path.insert(0,sys.argv[1]);import private_service', str(root)],
                capture_output=True, timeout=4, check=False)
            self.assertEqual(control.returncode, 0, control.stderr)
            self.assertTrue(marker.exists())
            marker.unlink()
            call = 'private_service._fabric_public_bounded_read(canonical_source[2], deadline)'
            bootstrap = svc._FABRIC_PUBLIC_READ_CHILD.replace(call, 'print(\'{"captured":true}\')')
            with mock.patch.object(svc, '__file__', str(source)), \
                 mock.patch.object(svc, '_FABRIC_PUBLIC_READ_CHILD', bootstrap):
                self.assertEqual(svc._fabric_public_https_json(
                    self.URL, deadline=svc.time.monotonic() + 4), {'captured': True})
            self.assertFalse(marker.exists())

    def test_installed_child_uses_captured_bytes_after_named_source_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'private_service.py'
            captured = Path(svc.__file__).read_bytes()
            marker = root / 'changed-source-executed'
            source.write_text("from pathlib import Path\nPath(%r).write_text('bad')\n" % str(marker))
            call = 'private_service._fabric_public_bounded_read(canonical_source[2], deadline)'
            bootstrap = svc._FABRIC_PUBLIC_READ_CHILD.replace(call, 'print(\'{"captured":true}\')')
            context = {'root': root, 'files': {'private_service.py': captured}}
            with mock.patch.object(svc, '_INSTALLED_CONTROL_CONTEXT', context), \
                 mock.patch.object(svc, '_FABRIC_PUBLIC_READ_CHILD', bootstrap):
                self.assertEqual(svc._fabric_public_https_json(
                    self.URL, deadline=svc.time.monotonic() + 4), {'captured': True})
            self.assertFalse(marker.exists())

    def _verified_drip_transport(self, phase, *, parent_exit=False, ambient_only=False):
        import ssl
        import threading
        asset = tempfile.TemporaryDirectory()
        self.addCleanup(asset.cleanup)
        cert = Path(asset.name)
        subprocess.run(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048',
                        '-nodes', '-days', '1', '-subj', '/CN=localhost',
                        '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1',
                        '-keyout', str(cert / 'key.pem'), '-out', str(cert / 'cert.pem')],
                       check=True, capture_output=True, timeout=10)
        connections, server_errors = [], []
        reading = threading.Event()
        def serve(sock):
            conn = None
            try:
                conn, _ = sock.accept()
                conn.settimeout(3)
                connections.append(conn.getpeername())
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                context.load_cert_chain(str(cert / 'cert.pem'), str(cert / 'key.pem'))
                with context.wrap_socket(conn, server_side=True) as client:
                    request = b''
                    while b'\r\n\r\n' not in request:
                        part = client.recv(4096)
                        if not part or len(request) + len(part) > 8192:
                            return
                        request += part
                    reading.set()
                    if phase == 'headers':
                        # Keep the header incomplete beyond the 2s deadline even on
                        # fast Linux startup; the old 91-byte header finished early.
                        fragments = (b'HTTP/1.1 200 OK\r\nX-Fixture-Drip: ' + b'x' * 256 +
                                     b'\r\nContent-Type: application/json\r\nContent-Length: 440\r\nConnection: close\r\n\r\n')
                    else:
                        client.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 440\r\nConnection: close\r\n\r\n')
                        fragments = b'{"slow":true}' * 40
                    for fragment in fragments:
                        client.sendall(bytes([fragment]))
                        svc.time.sleep(0.020)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError, OSError) as error:
                server_errors.append(type(error).__name__)
            finally:
                if conn is not None:
                    conn.close()
        server = socket.socket()
        server.settimeout(3)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', 0)); server.listen(1)
        thread = threading.Thread(target=serve, args=(server,))
        thread.start()
        root = 'https://localhost:%d' % server.getsockname()[1]
        local = re.compile(re.escape(root) + r'/git/ref/heads/master\Z')
        call = 'private_service._fabric_public_bounded_read(canonical_source[2], deadline)'
        bootstrap = svc._FABRIC_PUBLIC_READ_CHILD
        if not ambient_only:
            # Explicit fixture CA only: production bootstrap has no trust override.
            fixture_opener = (
                'import ssl\nprivate_service._fabric_public_opener = lambda: '
                'private_service.urllib.request.build_opener('
                'private_service.urllib.request.ProxyHandler({}), private_service._FabricNoRedirect(), '
                'private_service.urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile='
                + repr(str(cert / 'cert.pem')) + ')))\n')
            self.assertEqual(bootstrap.count(call), 1)
            bootstrap = bootstrap.replace(call, fixture_opener + call)
        pids, child_envs = [], []
        actual_popen = svc.subprocess.Popen
        def observe(*args, **kwargs):
            child_envs.append(kwargs.get('env'))
            child = actual_popen(*args, **kwargs)
            waiter = mock.Mock(wraps=child.wait)
            child.wait = waiter
            pids.append((child, waiter))
            return child
        parent = None
        child_pid = None
        started = svc.time.monotonic()
        try:
            if parent_exit:
                pid_file = cert / 'reader.pid'
                source_path, source_text = svc._fabric_public_child_source()
                # One real helper parent, then terminate only that parent while
                # its real child is reading verified TLS. No application runner.
                parent_code = r"""
import json,sys,types,re,signal
from pathlib import Path
source_path,source_text,url,bootstrap,pid_file,transport_deadline = json.loads(sys.stdin.read())
svc = types.ModuleType("_parent_fixture")
svc.__file__ = source_path
sys.modules[svc.__name__] = svc
exec(compile(source_text,source_path,"exec"),svc.__dict__)
# Exercise differing monotonic origins and inherited blocked SIGALRM, both
# without changing the real TLS traffic or the shared OS deadline.
original_clock = svc.time.monotonic
svc.time.monotonic = lambda: original_clock() + 5000.0
deadline = svc.time.monotonic() + transport_deadline - svc.time.clock_gettime(svc.time.CLOCK_MONOTONIC)
signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
svc.FABRIC_PUBLIC_METADATA_URL_RE = re.compile(re.escape(url)+r"\Z")
svc._FABRIC_PUBLIC_READ_CHILD = bootstrap
actual = svc.subprocess.Popen
def observed(*args,**kwargs):
    child = actual(*args,**kwargs)
    Path(pid_file).write_text(str(child.pid))
    return child
svc.subprocess.Popen = observed
svc._fabric_public_https_json(url,deadline=deadline)
"""
                deadline = started + 2.0
                parent = actual_popen([sys.executable, '-I', '-S', '-B', '-c', parent_code],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, env={'HOME': str(Path.home())})
                document = [source_path, source_text, root + '/git/ref/heads/master',
                            bootstrap, str(pid_file),
                            svc.time.clock_gettime(svc.time.CLOCK_MONOTONIC) + deadline - svc.time.monotonic()]
                parent.stdin.write(json.dumps(document).encode())
                parent.stdin.close()
                self.assertTrue(reading.wait(timeout=1.5), 'fixture never reached the real TLS read')
                child_pid = int(pid_file.read_text())
                parent.kill()
                parent.wait(timeout=1)
                self.assertEqual(parent.returncode, -signal.SIGKILL)
                self.assertLess(svc.time.monotonic(), deadline)
                # An orphan can briefly be a zombie on Linux; it must cease
                # execution by the original TTL. Normal parents separately
                # prove wait/reap. This does not signal or rescue the reader.
                state = 'RUNNING'
                while svc.time.monotonic() < deadline + 0.75:
                    status = subprocess.run(['/bin/ps', '-o', 'stat=', '-p', str(child_pid)],
                                            capture_output=True, text=True, timeout=1)
                    state = status.stdout.strip()
                    if not state or state.startswith('Z'):
                        break
                    svc.time.sleep(0.02)
                self.assertTrue(not state or state.startswith('Z'), 'reader outlived original deadline')
                elapsed = svc.time.monotonic() - started
                self.assertLess(elapsed, 2.8)
                result = {'phase': phase, 'parent_exit': True, 'elapsed_seconds': round(elapsed, 6),
                          'child_pid': child_pid, 'child_state': state or 'REAPED'}
            else:
                ambient = {'SSL_CERT_FILE': str(cert / 'cert.pem'), 'SSL_CERT_DIR': str(cert),
                           'SSLKEYLOGFILE': str(cert / 'keylog'), 'PYTHONPATH': str(cert),
                           'HTTPS_PROXY': 'http://user:password@proxy.invalid:8888'}
                with mock.patch.dict(os.environ, ambient), \
                     mock.patch.object(svc, 'FABRIC_PUBLIC_METADATA_URL_RE', local), \
                     mock.patch.object(svc, '_FABRIC_PUBLIC_READ_CHILD', bootstrap), \
                     mock.patch.object(svc.subprocess, 'Popen', side_effect=observe):
                    with self.assertRaisesRegex(SystemExit, 'bounded GitHub metadata unavailable'
                                                if ambient_only else 'deadline exceeded'):
                        svc._fabric_public_https_json(root + '/git/ref/heads/master',
                                                      deadline=started + 2.0)
                    elapsed = svc.time.monotonic() - started
                self.assertEqual(child_envs, [{'HOME': str(Path.home())}])
                self.assertEqual(len(pids), 1)
                self.assertIsNotNone(pids[0][0].returncode)
                self.assertGreater(pids[0][1].call_count, 0)
                with self.assertRaises(OSError):
                    os.kill(pids[0][0].pid, 0)
                self.assertFalse((cert / 'keylog').exists())
                if not ambient_only:
                    self.assertGreaterEqual(elapsed, 1.9)
                    self.assertLess(elapsed, 2.8)
                    self.assertTrue(reading.is_set())
                else:
                    self.assertFalse(reading.is_set(), 'ambient CA changed production trust')
                result = {'phase': phase, 'ambient_only': ambient_only,
                          'elapsed_seconds': round(elapsed, 6), 'connections': len(connections),
                          'child_pid': pids[0][0].pid, 'child_returncode': pids[0][0].returncode,
                          'wait_count': pids[0][1].call_count}
            self.assertEqual(len(connections), 1)
        finally:
            if parent is not None:
                if parent.poll() is None:
                    parent.kill()
                    parent.wait(timeout=1)
                parent.stdout.close()
                parent.stderr.close()
            server.close()
            thread.join(timeout=3.5)
        self.assertFalse(thread.is_alive())
        return result

    def test_verified_tls_headers_and_body_drip_expire_and_reap(self):
        for phase in ('headers', 'body'):
            with self.subTest(phase=phase):
                print('DRIP_ABSOLUTE_DEADLINE ' + json.dumps(self._verified_drip_transport(phase)))

    def test_child_has_its_own_deadline_after_parent_termination(self):
        print('ORPHAN_ABSOLUTE_DEADLINE ' +
              json.dumps(self._verified_drip_transport('body', parent_exit=True)))

    def test_ambient_ca_and_keylog_do_not_change_actual_child_trust(self):
        print('AMBIENT_TRUST_REFUSED ' +
              json.dumps(self._verified_drip_transport('body', ambient_only=True)))


if __name__ == '__main__':
    unittest.main()
