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


class BackendReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'home'
        self.home.mkdir(mode=0o700)
        self.fixture_root = mock.patch.object(svc, '_user_root', return_value=self.home)
        self.fixture_root.start()
        self.addCleanup(self.fixture_root.stop)
        self.account = svc.FABRIC_BACKEND_ACCOUNT
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
        stage = SimpleNamespace(account=self.account, port=45119, source=str(source),
            node=str(node), backend=str(self.old_backend), fabric_only=True,
            modern_fabric_protocol=None, enable_repository_workspaces=False,
            os_commission_config_sha256=None)
        self.capture(lambda: svc.cmd_stage(stage))
        deps = self.roots['node_modules'] / 'fixture-package'
        deps.mkdir(parents=True)
        (deps / 'index.js').write_text('export const preserved = true;\n')
        self.capture(lambda: svc.cmd_seal_runtime(SimpleNamespace(account=self.account)))
        # Preserve deliberately non-default policy values and opaque child env.
        config = json.loads(self.roots['config'].read_bytes())
        config.update({'requestTimeoutMs': 199_999, 'backendMode': 'shared-account',
                       'modernFabricProtocol': False, 'maxPerSessionConcurrency': 6})
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


if __name__ == '__main__':
    unittest.main()
