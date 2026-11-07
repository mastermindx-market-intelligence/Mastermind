"""Fixed C3 selection and real installed helper closure in disposable owners."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace as S
import unittest
from unittest import mock

import control_bundle_closure_test as closure
import private_service_test as fixtures

service = fixtures.svc
RUNS = ('fabric-app-native-drivers-j-20261105-01',
        'fabric-app-application-process-carrier-20261105-01')
ACCOUNT = 'fabric-c3-570f6f34'


class OriginalSelectionTests(unittest.TestCase):
    def descriptor(self, home):
        return {'enabled': True, 'schema': service.ORIGINAL_COLLECTION_SCHEMA,
            'pythonPath': '/inert/python', 'pythonSha256': '1'*64,
            'controlPath': str(home/'.local/share/studio-direct-mcp/control/private_service.py'),
            'controlSha256': '2'*64, 'controlBundleDigest': '3'*64,
            'nativeStore': str(home/'inert-native-store'), 'nativeGeneration': '4'*64}

    def test_cli_default_explicit_enable_and_explicit_shrink(self):
        args = ['upgrade', '--account', ACCOUNT, '--port', '45280', '--source', '/inert/source',
                '--node', '/inert/node', '--backend', '/inert/backend']
        self.assertIsNone(service.build_parser().parse_args(args).original_collection)
        self.assertIs(service.build_parser().parse_args(args+['--original-collection']).original_collection, True)
        self.assertIs(service.build_parser().parse_args(args+['--no-original-collection']).original_collection, False)
        self.assertIsNone(service._original_collection_setting(S(), {}, None, True, True))
        with self.assertRaises(SystemExit):
            service._original_collection_setting(S(original_collection=1), {}, None, True, True)

    def test_wrong_profile_refuses_before_resolving_native_state(self):
        with mock.patch.object(service, '_original_collection_native', side_effect=AssertionError('native state visited')):
            for account, port, fabric, modern in ((ACCOUNT, 1, True, True),
                    ('another-account', 45280, True, True), (ACCOUNT, 45280, False, True),
                    (ACCOUNT, 45280, True, False)):
                with self.subTest(account=account, port=port, fabric=fabric, modern=modern), self.assertRaises(ValueError):
                    service._original_collection_setting(S(original_collection=True, account=account, port=port),
                        {}, None, fabric, modern)

    def test_actual_stage_upgrade_retention_and_explicit_shrink(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); home=root/'home';home.mkdir()
            source=fixtures._make_source(root);node=fixtures._make_node(root);backend=fixtures._make_backend(root)
            args=fixtures._stage_args(source,node,backend,ACCOUNT,45280)
            args.fabric_only=True;args.modern_fabric_protocol=True;args.original_collection=True
            descriptor=self.descriptor(home)
            with mock.patch.dict(os.environ, {'HOME':str(home)}), \
                    mock.patch.object(service,'_run',fixtures.CmdRecorder()), \
                    mock.patch.object(service,'_original_collection_native',return_value=(descriptor,None,None,None)):
                fixtures._capture_stdout(lambda:service.cmd_stage(args))
                paths=service._build_runtime_roots(ACCOUNT);fixtures._seed_node_modules(paths)
                self.assertEqual(json.loads(paths['config'].read_text())['originalCollection'], descriptor)
                upgraded=fixtures._make_upgrade_source(root)
                upgrade=fixtures._stage_args(upgraded,node,backend,ACCOUNT,45280)
                fixtures._capture_stdout(lambda:service.cmd_upgrade(upgrade))
                self.assertEqual(json.loads(paths['config'].read_text())['originalCollection'], descriptor)
                upgrade.original_collection=False
                fixtures._capture_stdout(lambda:service.cmd_upgrade(upgrade))
                config=json.loads(paths['config'].read_text())
                self.assertNotIn('originalCollection',config)
                self.assertTrue(config['modernFabricProtocol'])
                self.assertTrue(config['fabricOnly'])
                self.assertEqual(json.loads(paths['manifest'].read_text())['configHash'],service._sha256_file(paths['config']))

    def test_retained_selection_requires_original_config_hash_and_closed_profile(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td);descriptor=self.descriptor(home)
            config=service._build_config(ACCOUNT,'127.0.0.1',45280,Path('/inert/node'),
                Path('/inert/backend'),Path('/inert/state'),home,fabric_only=True,modern_fabric=True,
                original_collection=descriptor)
            path=home/'config.json';path.write_text(json.dumps(config))
            args=S(account=ACCOUNT,port=45280,original_collection=None)
            with mock.patch.object(service,'_original_collection_native',return_value=(descriptor,None,None,None)):
                prior={'configHash':service._sha256_file(path)}
                self.assertEqual(service._original_collection_setting(args,{'config':path},prior,True,True),descriptor)
                path.write_text(json.dumps(dict(config,caller_approved=True)))
                with self.assertRaises(SystemExit):service._original_collection_setting(args,{'config':path},prior,True,True)
                for key,value in (('backendMode','per-session'),('repositoryWorkspaces',{}),
                                  ('originalCollection',dict(descriptor,unrecognized=True))):
                    path.write_text(json.dumps(dict(config,**{key:value})))
                    with self.assertRaises(SystemExit):
                        service._original_collection_setting(args,{'config':path},
                            {'configHash':service._sha256_file(path)},True,True)


class InstalledOriginalHelperTests(unittest.TestCase):
    def setUp(self):
        self.fixture=closure.InstalledClosureTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.cleanup_fixture)
        self.fixture._install()
        self.home=self.fixture.home
        self.marker=self.home/'inert-collector-invocations'
        self.entered=self.home/'inert-collector-entered'
        self.release=self.home/'inert-collector-release'
        path=closure.HERE.parent.parent/'ops/native_fabric/quota_continuity/rollout/native_generation.py'
        spec=importlib.util.spec_from_file_location('original_helper_inert_native',path)
        self.native=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.native)
        self.stable=self.home/('.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/'
            'handoff_kits/meta-ceo-b-2026-09-08/ext')
        self.stable.mkdir(parents=True,mode=0o700)
        self.store=self.stable.parent/self.native.STORE_NAME
        self.generation=self.publish()
        selected=self.fixture._child('print(json.dumps(svc._original_collection_native()[0]))\n')
        self.assertEqual(selected.returncode,0,selected.stderr)
        self.descriptor=json.loads(selected.stdout)

    def cleanup_fixture(self):
        try:self.fixture.tearDown()
        finally:self.fixture.doCleanups()

    def publish(self, *, runs=RUNS, wait=False):
        source=self.fixture.root/('native-fixture-'+str(time.monotonic_ns()))
        (source/'ext').mkdir(parents=True,mode=0o700)
        payload=("from pathlib import Path\nimport time\n"
            +f"GATEWAY_ORIGINAL_RUNS=frozenset({runs!r})\n"
            +"def _gateway_original_delivery(action,run_id,receipt_sha256=None):\n"
            +f" with Path({str(self.marker)!r}).open('a') as out:out.write(action+'\\n')\n"
            +(f" Path({str(self.entered)!r}).write_text('ready')\n"
              +" deadline=time.monotonic()+10\n"
              +f" while not Path({str(self.release)!r}).exists():\n"
              +"  if time.monotonic()>deadline:raise ValueError('inert barrier timeout')\n"
              +"  time.sleep(.01)\n" if wait else '')
            +" return {'run_id':run_id,'state':'COMPLETE','fixture_only':True}\n").encode()
        files={'pool':b'#!/bin/sh\nexit 0\n','ext/fabric_task.py':b'# inert task\n',
            'ext/remote_sub.sh':b'#!/bin/sh\nexit 0\n','ext/original_delivery_collector.py':payload,
            **{'ext/'+name:b'# inert companion; never imported\n' for name in
               ('artifact_delivery.py','artifact_reader.py','artifact_production.py','native_runtime_bindings.py')}}
        for name,raw in files.items():(source/name).write_bytes(raw)
        generation=self.native.publish(source,self.stable,{name:self.native.digest(raw) for name,raw in files.items()})
        prior=self.native.current(self.store)
        self.native.select(self.store,generation.name,prior['generation'] if prior else None)
        return generation

    def command(self, *, source=False):
        entry=(closure.HERE if source else self.fixture.control)/'private_service.py'
        return [sys.executable,'-I','-S','-B',str(entry),'_original-collection-helper']

    def request(self, action='collect', descriptor=None, run=None):
        value={'configuration':descriptor or self.descriptor,'operation':action,'run_id':run or RUNS[0]}
        if action=='result':value['receipt_sha256']='a'*64
        return json.dumps(value)

    def call(self, action='collect', *, descriptor=None, source=False, run=None):
        return subprocess.run(self.command(source=source),input=self.request(action,descriptor,run),
            cwd=self.fixture.empty,env={'HOME':str(self.home),'PATH':'/usr/bin:/bin','LANG':'C'},
            capture_output=True,text=True,timeout=15)

    def assert_refused_without_invocation(self, result):
        self.assertNotEqual(result.returncode,0,result.stdout)
        self.assertFalse(self.marker.exists())

    def test_actual_installed_control_and_native_closure_dispatch_both_fixed_runs(self):
        for run in RUNS:
            result=self.call(run=run)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),{'run_id':run,'state':'COMPLETE','fixture_only':True})
        self.assertEqual(self.marker.read_text().splitlines(),['collect','collect'])

    def test_source_mode_cannot_masquerade_as_installed_helper(self):
        self.assert_refused_without_invocation(self.call(source=True))

    def test_wrong_descriptor_interpreter_or_generation_refuses_before_collector(self):
        for key in ('pythonSha256','controlSha256','controlBundleDigest','nativeGeneration'):
            with self.subTest(key=key):
                self.assert_refused_without_invocation(self.call(descriptor=dict(self.descriptor,**{key:'0'*64})))

    def test_changed_installed_control_companion_refuses_before_collector(self):
        path=self.fixture.control/'private_service_pin.py'
        path.write_bytes(path.read_bytes()+b'\n# unsealed fixture drift\n')
        self.assert_refused_without_invocation(self.call())

    def test_changed_native_collector_refuses_before_import(self):
        target=self.generation/'ext/original_delivery_collector.py'
        target.chmod(0o755);target.write_bytes(target.read_bytes()+b'\n# unsealed fixture drift\n')
        self.assert_refused_without_invocation(self.call())

    def test_verified_native_collector_with_wrong_scope_refuses_before_dispatch(self):
        self.generation=self.publish(runs=('unrecognized-run',))
        observed=self.fixture._child('print(json.dumps(svc._original_collection_native()[0]))\n')
        self.assertEqual(observed.returncode,0,observed.stderr)
        self.descriptor=json.loads(observed.stdout)
        self.assert_refused_without_invocation(self.call())

    def test_pinned_read_survives_corrupt_current_but_collection_does_not(self):
        (self.store/'CURRENT.json').write_text('{}\n')
        for action in ('status','result'):
            result=self.call(action)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(json.loads(result.stdout)['fixture_only'])
        refused=self.call()
        self.assertNotEqual(refused.returncode,0)
        self.assertEqual(json.loads(refused.stdout)['effect_state'],'NOT_APPLIED')
        self.assertEqual(self.marker.read_text().splitlines(),['status','result'])

    def test_actual_helper_holds_the_incumbent_control_lock_through_dispatch(self):
        self.generation=self.publish(wait=True)
        observed=self.fixture._child('print(json.dumps(svc._original_collection_native()[0]))\n')
        self.assertEqual(observed.returncode,0,observed.stderr);self.descriptor=json.loads(observed.stdout)
        process=subprocess.Popen(self.command(),cwd=self.fixture.empty,
            env={'HOME':str(self.home),'PATH':'/usr/bin:/bin','LANG':'C'},
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            process.stdin.write(self.request());process.stdin.close();process.stdin=None
            deadline=time.monotonic()+5
            while not self.entered.exists() and time.monotonic()<deadline:time.sleep(.01)
            self.assertTrue(self.entered.exists(),'inert collector never reached barrier')
            with self.assertRaisesRegex(closure.bundle.Refusal,'CONTROL_BUNDLE_BUSY'):self.fixture._install()
        finally:
            self.release.write_text('release')
            try:out,err=process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill();out,err=process.communicate(timeout=5)
        self.assertEqual(process.returncode,0,err)
        self.assertTrue(json.loads(out)['fixture_only'])
        self.assertEqual(self.fixture._install()['state'],'CONTROL_BUNDLE_INSTALLED')


if __name__=='__main__':unittest.main()
