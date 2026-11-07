"""Modern Fabric selection stays in the exact incumbent private installation."""
import json
from pathlib import Path
from types import SimpleNamespace as S
import tempfile
import unittest
from unittest import mock
import private_service_test as fixtures
service = fixtures.svc

class ModernFabricSelectionTests(unittest.TestCase):
    def config(self, **kwargs):
        return service._build_config('fabric-test','127.0.0.1',45280,Path('/owned/node'),
            Path('/owned/backend'),Path('/owned/state'),Path('/owned/home'),**kwargs)

    def test_default_keeps_both_legacy_profiles_unchanged(self):
        for fabric in (False,True):
            config=self.config(fabric_only=fabric)
            self.assertNotIn('modernFabricProtocol',config)
            self.assertNotIn('backendMode',config)

    def test_explicit_modern_selection_is_fabric_only_and_shared_backend(self):
        config=self.config(fabric_only=True,modern_fabric=True)
        self.assertIs(config['modernFabricProtocol'],True)
        self.assertEqual(config['backendMode'],'shared-account')
        self.assertEqual(config['accountLabel'],'fabric-test')
        self.assertEqual(config['port'],45280)
        self.assertIs(config['gitPublish'],False)
        self.assertIs(config['paperDesign'],False)
        self.assertNotIn('fleetStatus',config)
        for kwargs in ({'modern_fabric':True},{'fabric_only':True,'modern_fabric':1}):
            with self.assertRaises(ValueError):self.config(**kwargs)

    def test_cli_explicit_enable_disable_and_unspecified(self):
        base=['upgrade','--account','fabric-test','--port','45280','--source','/owned/source',
              '--node','/owned/node','--backend','/owned/backend']
        self.assertIsNone(service.build_parser().parse_args(base).modern_fabric_protocol)
        self.assertIs(service.build_parser().parse_args(base+['--modern-fabric-protocol']).modern_fabric_protocol,True)
        self.assertIs(service.build_parser().parse_args(base+['--no-modern-fabric-protocol']).modern_fabric_protocol,False)

    def test_retained_selection_requires_verified_fabric_and_shared_mode(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'config.json'
            config=self.config(fabric_only=True,modern_fabric=True)
            path.write_text(json.dumps(config))
            roots={'config':path};prior={'configHash':service._sha256_file(path)}
            select=service._modern_fabric_setting
            self.assertTrue(select(S(),roots,prior,True))
            self.assertFalse(select(S(modern_fabric_protocol=False),roots,prior,True))
            with self.assertRaises(SystemExit):select(S(),roots,{'configHash':'0'*64},True)
            with self.assertRaises(SystemExit):select(S(modern_fabric_protocol=True),roots,prior,False)
            config['backendMode']='per-session';path.write_text(json.dumps(config))
            with self.assertRaises(SystemExit):select(S(),roots,{'configHash':service._sha256_file(path)},True)

    def test_stage_upgrade_preserve_activation_and_explicit_shrink(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);home=root/'home';home.mkdir()
            source=fixtures._make_source(root);node=fixtures._make_node(root);backend=fixtures._make_backend(root)
            args=fixtures._stage_args(source,node,backend);args.fabric_only=True;args.modern_fabric_protocol=True
            with mock.patch.dict('os.environ',{'HOME':str(home)}),mock.patch.object(service,'_run',fixtures.CmdRecorder()):
                fixtures._capture_stdout(lambda:service.cmd_stage(args))
                paths=service._build_runtime_roots('test-account');fixtures._seed_node_modules(paths)
                upgraded=fixtures._make_upgrade_source(root)
                upgrade=fixtures._stage_args(upgraded,node,backend)
                fixtures._capture_stdout(lambda:service.cmd_upgrade(upgrade))
                config=json.loads(paths['config'].read_text());self.assertIs(config['modernFabricProtocol'],True)
                self.assertEqual(config['backendMode'],'shared-account')
                upgrade.modern_fabric_protocol=False
                fixtures._capture_stdout(lambda:service.cmd_upgrade(upgrade))
                config=json.loads(paths['config'].read_text());self.assertNotIn('modernFabricProtocol',config)
                self.assertNotIn('backendMode',config)
                self.assertIs(config['fabricOnly'],True)
                manifest=json.loads(paths['manifest'].read_text())
                self.assertEqual(manifest['configHash'],service._sha256_file(paths['config']))

if __name__=='__main__':unittest.main()
