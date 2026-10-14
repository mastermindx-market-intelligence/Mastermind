"""Fabric-only is a restricted profile of the incumbent installer, not a new owner."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock
import private_service_test as fixtures
service = fixtures.svc


class FabricProfileTests(unittest.TestCase):
    def config(self, **kwargs):
        return service._build_config('fabric-test', '127.0.0.1', 45217,
            Path('/owned/node'), Path('/owned/backend'), Path('/owned/state'), Path('/owned/home'), **kwargs)

    def test_fabric_profile_does_not_add_git_paper_or_workspace_capabilities(self):
        with mock.patch.object(service, '_typed_git_config', side_effect=AssertionError('unrelated Git')), \
             mock.patch.object(service, '_paper_design_config', side_effect=AssertionError('unrelated Paper')):
            config = self.config(fabric_only=True)
        self.assertIs(config['fabricOnly'], True)
        self.assertIs(config['gitPublish'], False)
        self.assertIs(config['paperDesign'], False)
        self.assertEqual(config['childEnv']['MMX_FABRIC_SDK_PACKAGE'], '/owned/package.json')
        self.assertNotIn('repositoryWorkspaces', config)
        self.assertNotIn('commissionPublication', config)

    def test_existing_studio_profile_is_unchanged(self):
        config = self.config()
        self.assertNotIn('fabricOnly', config)
        self.assertIsInstance(config['gitPublish'], dict)
        self.assertIsInstance(config['paperDesign'], dict)

    def test_cli_allows_explicit_profile_and_rejects_invalid_combinations(self):
        for command in ('stage', 'upgrade'):
            args = service.build_parser().parse_args([command, '--account', 'fabric-test', '--port', '45217',
                '--source', '/owned/source', '--node', '/owned/node', '--backend', '/owned/backend', '--fabric-only'])
            self.assertIs(args.fabric_only, True)
        for kwargs in ({'fabric_only': 1}, {'fabric_only': True, 'repository_workspaces': True},
                       {'fabric_only': True, 'commission_digest': 'a'*64}):
            with self.assertRaises((ValueError, SystemExit)):
                self.config(**kwargs)

    def test_actual_stage_and_upgrade_retain_profile_without_paper_dependency(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home = root / 'home'
            home.mkdir()
            source = fixtures._make_source(root)
            node = fixtures._make_node(root)
            backend = fixtures._make_backend(root)
            args = fixtures._stage_args(source, node, backend)
            args.fabric_only = True
            with mock.patch.dict('os.environ', {'HOME': str(home)}), \
                 mock.patch.object(service, '_run', fixtures.CmdRecorder()), \
                 mock.patch.object(service, '_verify_paper_runtime', side_effect=AssertionError('Paper must not be consulted')):
                fixtures._capture_stdout(lambda: service.cmd_stage(args))
                paths = service._build_runtime_roots('test-account')
                fixtures._seed_node_modules(paths)
                args.fabric_only = False
                fixtures._capture_stdout(lambda: service.cmd_stage(args))
                upgraded = fixtures._make_upgrade_source(root)
                fixtures._capture_stdout(lambda: service.cmd_upgrade(fixtures._stage_args(upgraded, node, backend)))
                config = json.loads(paths['config'].read_text())
                self.assertIs(config['fabricOnly'], True)
                self.assertIs(config['gitPublish'], False)
                self.assertIs(config['paperDesign'], False)
                manifest = json.loads(paths['manifest'].read_text())
                self.assertEqual(manifest['configHash'], service._sha256_file(paths['config']))

    def test_profile_cannot_silently_repurpose_existing_studio_install(self):
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / 'config.json'
            config.write_text(json.dumps({'gitPublish': {'enabled': True}, 'paperDesign': {'enabled': True}}))
            prior = {'configHash': service._sha256_file(config)}
            with self.assertRaises(SystemExit):
                service._fabric_profile_setting(SimpleNamespace(fabric_only=True), {'config': config}, prior)

    def test_invalid_or_drifted_retained_profile_is_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / 'config.json'
            for value in ({'fabricOnly': 1}, {'fabricOnly': True, 'gitPublish': {}, 'paperDesign': False}):
                config.write_text(json.dumps(value))
                prior = {'configHash': service._sha256_file(config)}
                with self.assertRaises(SystemExit):
                    service._fabric_profile_setting(SimpleNamespace(), {'config': config}, prior)
            config.write_text('{}')
            with self.assertRaises(SystemExit):
                service._fabric_profile_setting(SimpleNamespace(), {'config': config}, {'configHash':'0'*64})


    def test_fabric_only_rejects_machine_fleet_inventory_even_when_installed(self):
        """An M2 with installed fleetStatus must not expose that unrelated tool.

        RED-first based on the actual newly staged C3 profile tool listing.
        Ordinary Studio profiles still retain the incumbent fleetStatus owner.
        """
        fleet = {"enabled": True, "launcherPath": "/owned/control/launcher",
                 "launcherSha256": "b" * 64, "timeoutMs": 5000}
        with mock.patch.object(service, '_fleet_status_config', return_value=fleet):
            fabric = self.config(fabric_only=True)
            normal = self.config()
        self.assertNotIn('fleetStatus', fabric)
        self.assertEqual(normal.get('fleetStatus'), fleet)
        self.assertTrue(fabric['fabricOnly'])
        self.assertEqual(fabric['gitPublish'], False)
        self.assertEqual(fabric['paperDesign'], False)

    def test_restage_refuses_insecure_retained_fabric_fleet_config(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / 'config.json'
            config = {'fabricOnly': True, 'gitPublish': False,
                      'paperDesign': False,
                      'fleetStatus': {'enabled': True, 'launcherPath': '/owner/fleet'}}
            path.write_text(json.dumps(config))
            prior = {'configHash': service._sha256_file(path)}
            with self.assertRaisesRegex(SystemExit, 'Fabric-only'):
                service._fabric_profile_setting(
                    SimpleNamespace(fabric_only=False), {'config': path}, prior)


if __name__ == '__main__':
    unittest.main()
