"""Fixed C3 selection and real installed helper closure in disposable owners."""
import contextlib
from functools import partial
import hashlib
import importlib.util
import json
import os
import fcntl
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace as S
import unittest
import venv
from unittest import mock

import control_bundle_closure_test as closure
import private_service_test as fixtures

service = fixtures.svc
RUNS = ('fabric-app-native-drivers-j-20261105-01',
        'fabric-app-application-process-carrier-20261105-01')
ACCOUNT = 'fabric-c3-570f6f34'
PRINCIPAL = 'p:tunnel:' + ACCOUNT
ROOT = 'fabric-application-integration-20261104-sol'
# The fixed machine-owned scope of the two enrolled original runs.
SCOPES = {run: {'root': ROOT, 'parent': ROOT, 'host': 'ubuntu1',
    'destination': f'/Volumes/Mastermind/evidence/{ROOT}/original-collections/{run}-collection-v1'}
    for run in RUNS}


def absent_observation(run):
    """The original status contract for a first call that reserved nothing."""
    return {'acceptance': 'NOT_RECORDED', 'controller_state': 'UNKNOWN',
        'destination_reserved': False, 'effect_state': 'UNKNOWN',
        'lease_settlement': 'UNKNOWN', 'original_operation_mutated': False,
        'reason': 'destination_absence_is_not_execution_absence',
        'retry_authorized': False, 'run_id': run, 'state': 'ABSENT'}


def complete_observation(run):
    return {'acceptance': 'NOT_RECORDED', 'controller_state': 'UNKNOWN',
        'destination_reserved': True, 'delivery_verified': True,
        'lease_settlement': 'UNKNOWN', 'original_operation_mutated': False,
        'receipt_sha256': 'a'*64, 'retry_authorized': False, 'run_id': run, 'state': 'COMPLETE'}


def original_fixture_lock(home):
    lock = home/'.local/share/studio-direct-mcp/control/.control-bundle.lock'
    lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock.touch(mode=0o600, exist_ok=True)


def reseal_fixture_config(paths, config):
    paths['config'].write_text(json.dumps(config))
    manifest = json.loads(paths['manifest'].read_text())
    manifest['configHash'] = service._sha256_file(paths['config'])
    paths['manifest'].write_text(json.dumps(manifest))
    return manifest


def seed_original_service(root, home, descriptor):
    source = fixtures._make_source(root)
    node, backend = fixtures._make_node(root), fixtures._make_backend(root)
    args = fixtures._stage_args(source, node, backend, ACCOUNT, 45280)
    args.fabric_only = args.modern_fabric_protocol = args.original_collection = True
    with mock.patch.dict(os.environ, {'HOME': str(home)}), \
            mock.patch.object(service, '_run', fixtures.CmdRecorder()), \
            mock.patch.object(service, '_lifecycle_inspect', return_value=None), \
            mock.patch.object(service, '_original_collection_native', return_value=(descriptor, None, None, None)):
        fixtures._capture_stdout(lambda: service.cmd_stage(args))
        paths = service._build_runtime_roots(ACCOUNT)
        fixtures._seed_node_modules(paths)
        fixtures._seal_runtime(ACCOUNT)
    return paths, node, backend


def original_absent_commands():
    recorder = fixtures.CmdRecorder()
    def recorded(args, **kwargs):
        if list(args[:2]) == ['launchctl', 'print']:
            label = str(args[2]).split('/')[-1]
            absent = 'Bad request.\nCould not find service "' + label + '" in domain for user gui: ' + str(os.getuid()) + '\n'
            return subprocess.CompletedProcess(args, 113, '', absent)
        return recorder(args, **kwargs)
    return recorded


class OriginalSelectionTests(unittest.TestCase):
    def descriptor(self, home):
        return {'enabled': True, 'schema': service.ORIGINAL_COLLECTION_SCHEMA,
            'pythonPath': '/inert/python', 'pythonSha256': '1'*64,
            'controlPath': str(home/'.local/share/studio-direct-mcp/control/private_service.py'),
            'controlSha256': '2'*64, 'controlBundleDigest': '3'*64,
            'nativeStore': str(home/'inert-native-store'), 'nativeGeneration': '4'*64,
            'predecessor': None}

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
                    mock.patch.object(service,'_run',original_absent_commands()), \
                    mock.patch.object(service,'_original_collection_native',return_value=(descriptor,None,None,None)):
                fixtures._capture_stdout(lambda:service.cmd_stage(args))
                paths=service._build_runtime_roots(ACCOUNT);fixtures._seed_node_modules(paths)
                original_fixture_lock(home)
                self.assertEqual(json.loads(paths['config'].read_text())['originalCollection'], descriptor)
                upgraded=fixtures._make_upgrade_source(root)
                upgrade=fixtures._stage_args(upgraded,node,backend,ACCOUNT,45280)
                with self.assertRaisesRegex(SystemExit, 'retained original receipt'):
                    service.cmd_upgrade(upgrade)
                self.assertEqual(json.loads(paths['config'].read_text())['originalCollection'], descriptor)
                upgrade.original_collection=False
                fixtures._capture_stdout(lambda:service.cmd_upgrade(upgrade))
                config=json.loads(paths['config'].read_text())
                self.assertNotIn('originalCollection',config)
                self.assertTrue(config['modernFabricProtocol'])
                self.assertTrue(config['fabricOnly'])
                self.assertEqual(json.loads(paths['manifest'].read_text())['configHash'],service._sha256_file(paths['config']))

    def test_upgrade_seals_the_predecessor_and_carries_it_forward(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); home=root/'home';home.mkdir()
            source=fixtures._make_source(root);node=fixtures._make_node(root);backend=fixtures._make_backend(root)
            args=fixtures._stage_args(source,node,backend,ACCOUNT,45280)
            args.fabric_only=True;args.modern_fabric_protocol=True;args.original_collection=True
            descriptor=self.descriptor(home)
            receipt=root/'retained-first-call-receipt.json'
            receipt.write_text(json.dumps({'call':{'response':absent_observation(RUNS[0])}}))
            digest=hashlib.sha256(receipt.read_bytes()).hexdigest()
            with mock.patch.dict(os.environ, {'HOME':str(home)}), \
                    mock.patch.object(service,'_run',original_absent_commands()), \
                    mock.patch.object(service,'_original_collection_native',
                        return_value=(descriptor,None,None,None)):
                fixtures._capture_stdout(lambda:service.cmd_stage(args))
                paths=service._build_runtime_roots(ACCOUNT);fixtures._seed_node_modules(paths)
                original_fixture_lock(home)
                with mock.patch.object(service, '_lifecycle_inspect', return_value=None):
                    fixtures._seal_runtime(ACCOUNT)
                staged=json.loads(paths['config'].read_text())['originalCollection']
                self.assertEqual(staged['schema'],service.ORIGINAL_COLLECTION_SCHEMA)
                self.assertIsNone(staged['predecessor'])
                # Actual v1 descriptor and sealed dependencies precede the upgrade.
                config=json.loads(paths['config'].read_text())
                legacy=dict(staged, schema=service.ORIGINAL_COLLECTION_LEGACY_SCHEMA)
                del legacy['predecessor']
                config['originalCollection']=legacy
                config['requestTimeoutMs']=43210
                config['childEnv']['RETAINED_FIXTURE_SETTING']='kept'
                prior=reseal_fixture_config(paths, config)
                # The preserving upgrade seals the retained first-call receipt.
                upgrade=fixtures._stage_args(fixtures._make_upgrade_source(root),node,backend,ACCOUNT,45280)
                upgrade.original_predecessor_receipt=str(receipt)
                upgrade.original_predecessor_sha256=digest
                with mock.patch.object(service,'_original_collection_collector',
                        return_value=S(PLAIN_SCOPES=SCOPES, _gateway_collection_status=complete_observation)):
                    fixtures._capture_stdout(lambda:service.cmd_upgrade(upgrade))
                sealed=json.loads(paths['config'].read_text())['originalCollection']['predecessor']
                self.assertEqual(sealed['receipt_sha256'],digest)
                service._original_predecessor_verify(sealed)
                self.assertEqual(sealed['runs'][RUNS[0]]['destination'],SCOPES[RUNS[0]]['destination'])
                self.assertEqual(json.loads(sealed['runs'][RUNS[1]]['observation']), complete_observation(RUNS[1]))
                after=json.loads(paths['config'].read_text())
                self.assertEqual({k:v for k,v in after.items() if k!='originalCollection'},
                    {k:v for k,v in config.items() if k!='originalCollection'})
                self.assertEqual(json.loads(paths['manifest'].read_text())['dependencyTreeHash'], prior['dependencyTreeHash'])
                # A different receipt over an installed seal is refused.
                other=root/'other-receipt.json'
                other.write_text(json.dumps({'call':{'response':absent_observation(RUNS[0])},'x':1}))
                conflict=fixtures._stage_args(fixtures._make_upgrade_source(root),node,backend,ACCOUNT,45280)
                conflict.original_predecessor_receipt=str(other)
                conflict.original_predecessor_sha256=hashlib.sha256(other.read_bytes()).hexdigest()
                with mock.patch.object(service,'_original_collection_collector',
                        return_value=S(PLAIN_SCOPES=SCOPES)):
                    with self.assertRaises(SystemExit):
                        service.cmd_upgrade(conflict)
                # A plain upgrade carries the sealed binding forward unchanged.
                carried_upgrade=fixtures._stage_args(fixtures._make_upgrade_source(root),node,backend,ACCOUNT,45280)
                fixtures._capture_stdout(lambda:service.cmd_upgrade(carried_upgrade))
                carried=json.loads(paths['config'].read_text())['originalCollection']['predecessor']
                self.assertEqual(carried,sealed)
                # The owner readback reports the sealed binding and no attempt.
                rc, readback=fixtures._capture_stdout(lambda:service.cmd_original_predecessor_readback(
                    S(account=ACCOUNT)))
                self.assertEqual(rc,0)
                report=json.loads(readback)
                self.assertTrue(report['sealed'])
                self.assertEqual(report['predecessor'],sealed)
                self.assertEqual(report['reconciliation'],dict.fromkeys(RUNS))
                self.assertEqual(report['pending_helpers'],[])

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
                with self.assertRaisesRegex(SystemExit, 'retained original receipt'):
                    service._original_collection_setting(args,{'config':path},prior,True,True)
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
        self.paths, self.node, self.backend = seed_original_service(self.fixture.root, self.home, self.descriptor)

    def cleanup_fixture(self):
        try:self.fixture.tearDown()
        finally:self.fixture.doCleanups()

    def publish(self, *, runs=RUNS, wait=False):
        source=self.fixture.root/('native-fixture-'+str(time.monotonic_ns()))
        (source/'ext').mkdir(parents=True,mode=0o700)
        scopes={run:SCOPES[run] for run in RUNS}
        payload=("from pathlib import Path\nimport base64,hashlib,time\n"
            +f"GATEWAY_ORIGINAL_RUNS=frozenset({runs!r})\n"
            +f"PLAIN_SCOPES={scopes!r}\n"
            +"def _gateway_original_delivery(action,run_id,receipt_sha256=None):\n"
            +f" with Path({str(self.marker)!r}).open('a') as out:out.write(action+'\\n')\n"
            +(f" Path({str(self.entered)!r}).write_text('ready')\n"
              +" deadline=time.monotonic()+10\n"
              +f" while not Path({str(self.release)!r}).exists():\n"
              +"  if time.monotonic()>deadline:raise ValueError('inert barrier timeout')\n"
              +"  time.sleep(.01)\n" if wait else '')
            +" if action in ('reconcile','result'):\n"
            +"  raw=b'inert original result bytes\\n'\n"
            +"  return {'run_id':run_id,'state':'COMPLETE','fixture_only':True,\n"
            +"   'receipt_sha256':'a'*64,'acceptance':'NOT_RECORDED',\n"
            +"   'lease_settlement':'UNKNOWN','retry_authorized':False,\n"
            +"   'stdout_base64':base64.b64encode(raw).decode(),'stdout_bytes':len(raw),\n"
            +"   'stdout_sha256':hashlib.sha256(raw).hexdigest()}\n"
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

    def install_descriptor(self):
        config=json.loads(self.paths['config'].read_text())
        config['originalCollection']=self.descriptor
        reseal_fixture_config(self.paths,config)

    def request(self, action='status', descriptor=None, run=None):
        value={'configuration':descriptor or self.descriptor,'operation':action,'run_id':run or RUNS[0]}
        if action=='result':value['receipt_sha256']='a'*64
        return json.dumps(value)

    def call(self, action='status', *, descriptor=None, source=False, run=None):
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
        self.assertEqual(self.marker.read_text().splitlines(),['status','status'])

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
        self.install_descriptor()
        self.assert_refused_without_invocation(self.call())

    def test_pinned_read_survives_corrupt_current_but_collection_does_not(self):
        (self.store/'CURRENT.json').write_text('{}\n')
        for action in ('status','result'):
            result=self.call(action)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(json.loads(result.stdout)['fixture_only'])
        refused=self.call('collect')
        self.assertNotEqual(refused.returncode,0)
        self.assertEqual(json.loads(refused.stdout)['effect_state'],'NOT_APPLIED')
        self.assertEqual(self.marker.read_text().splitlines(),['status','result'])

    def test_actual_helper_holds_the_incumbent_control_lock_through_dispatch(self):
        self.generation=self.publish(wait=True)
        observed=self.fixture._child('print(json.dumps(svc._original_collection_native()[0]))\n')
        self.assertEqual(observed.returncode,0,observed.stderr);self.descriptor=json.loads(observed.stdout)
        self.install_descriptor()
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

    def test_resealed_foreign_predecessor_cannot_replace_the_installed_descriptor(self):
        receipt=self.home/'receipt.json'
        receipt.write_text(json.dumps({'response': absent_observation(RUNS[0])}))
        predecessor=service._original_predecessor_build(str(receipt),
            hashlib.sha256(receipt.read_bytes()).hexdigest(), self.descriptor,
            json.loads(self.paths['manifest'].read_text())['configHash'], SCOPES)
        self.descriptor=dict(self.descriptor, predecessor=predecessor)
        self.install_descriptor()
        forged=json.loads(json.dumps(self.descriptor))
        forged['predecessor']['prior']['configHash']='f'*64
        forged['predecessor']['seal']=service._original_predecessor_seal(forged['predecessor'])
        service._original_predecessor_verify(forged['predecessor'])
        self.assert_refused_without_invocation(self.call(descriptor=forged))
        config=json.loads(self.paths['config'].read_text())
        config['originalCollection']=forged
        self.paths['config'].write_text(json.dumps(config))
        self.assert_refused_without_invocation(self.call(descriptor=forged))
        report=self.fixture._child('svc.cmd_original_predecessor_readback(type("Args",(),{"account":'+repr(ACCOUNT)+'})())\n')
        self.assertNotEqual(report.returncode,0)

    def test_shared_lifecycle_lock_prevents_helper_entry_during_upgrade(self):
        with mock.patch.dict(os.environ, {'HOME': str(self.home)}):
            with service._c2_lifecycle_mutex(ACCOUNT):
                self.assert_refused_without_invocation(self.call())
        self.assertEqual(self.call().returncode,0)

    def test_legacy_helper_without_a_marker_blocks_upgrade_quiescence(self):
        lock=self.fixture.control/'.control-bundle.lock'
        fd=os.open(lock,os.O_RDONLY)
        try:
            fcntl.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
            with mock.patch.dict(os.environ, {'HOME': str(self.home)}):
                self.assertEqual(service._original_helper_pending(ACCOUNT),[])
                with self.assertRaisesRegex(SystemExit, 'quiescence'):
                    with service._original_control_quiescence():
                        self.fail('upgrade entered while the old helper held its lock')
        finally: os.close(fd)

    def test_marker_failure_is_not_an_empty_quiescent_state(self):
        with mock.patch.dict(os.environ, {'HOME': str(self.home)}):
            with mock.patch.object(Path,'iterdir',side_effect=OSError('unreadable')):
                with self.assertRaisesRegex(SystemExit,'quiescence'):
                    service._original_helper_pending(ACCOUNT)
            with mock.patch.object(service,'_original_fsync_dir',side_effect=OSError('not durable')):
                with self.assertRaises(OSError): service._original_helper_marker_take()
            self.assertTrue(service._original_helper_pending(ACCOUNT))


class OriginalPredecessorImportTests(unittest.TestCase):
    """Machine-owner sealing, qualification and the durable one-use fence."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mmx-predecessor-')
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.descriptor = {'controlSha256': 'a'*64, 'nativeGeneration': 'b'*64,
            'controlBundleDigest': 'c'*64}
        self.config_hash = 'd'*64

    def receipt(self, value):
        path = self.root/'retained-first-call-receipt.json'
        path.write_text(json.dumps(value), encoding='utf-8')
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def build(self, value, digest=None):
        path, actual = self.receipt(value)
        return service._original_predecessor_build(
            str(path), digest or actual, self.descriptor, self.config_hash, SCOPES)

    def test_whole_file_digest_is_the_only_accepted_expectation(self):
        observation = absent_observation(RUNS[0])
        path, digest = self.receipt({'call': {'response': observation}})
        predecessor = service._original_predecessor_build(
            str(path), digest, self.descriptor, self.config_hash, SCOPES)
        self.assertEqual(predecessor['receipt_sha256'], digest)
        self.assertEqual(predecessor['runs'][RUNS[0]]['destination'], SCOPES[RUNS[0]]['destination'])
        self.assertEqual(json.loads(predecessor['runs'][RUNS[0]]['observation']), observation)
        self.assertEqual(predecessor['prior']['account'], ACCOUNT)
        self.assertEqual(predecessor['prior']['principal'], PRINCIPAL)
        self.assertEqual(predecessor['prior']['root'], ROOT)
        self.assertEqual(predecessor['prior']['controlSha256'], self.descriptor['controlSha256'])
        self.assertEqual(predecessor['prior']['nativeGeneration'], self.descriptor['nativeGeneration'])
        self.assertEqual(predecessor['prior']['configHash'], self.config_hash)
        # An inner response digest is never a substitute for the whole file.
        inner = hashlib.sha256(json.dumps(observation).encode()).hexdigest()
        self.assertNotEqual(inner, digest)
        with self.assertRaises(SystemExit):
            service._original_predecessor_build(
                str(path), inner, self.descriptor, self.config_hash, SCOPES)

    def test_receipt_without_one_unique_contract_observation_refuses(self):
        with self.assertRaises(SystemExit) as caught:
            self.build({'call': {'response': {'state': 'ABSENT'}}})
        self.assertIn('original status contract', str(caught.exception))
        with self.assertRaises(SystemExit):
            self.build({'a': absent_observation(RUNS[0]), 'b': absent_observation(RUNS[0])})
        with self.assertRaises(SystemExit):
            self.build({'call': {'response': absent_observation('another-run')}})

    def test_observation_semantics_are_qualified(self):
        for key, value in (('acceptance', 'ACCEPTED'), ('retry_authorized', True),
                ('original_operation_mutated', True), ('lease_settlement', 'SETTLED'),
                ('controller_state', 'COMPLETE'), ('effect_state', 'NOT_APPLIED'),
                ('state', 'COMPLETE'), ('destination_reserved', True)):
            with self.subTest(key=key):
                observation = dict(absent_observation(RUNS[0]))
                observation[key] = value
                with self.assertRaises(SystemExit):
                    self.build({'response': observation})
        # The retry spelling of the contract is accepted as well.
        observation = absent_observation(RUNS[0])
        observation['retry_allowed'] = observation.pop('retry_authorized')
        predecessor = self.build({'response': observation})
        self.assertEqual(json.loads(predecessor['runs'][RUNS[0]]['observation'])['state'], 'ABSENT')

    def test_seal_binds_the_prior_commitments(self):
        predecessor = self.build({'response': absent_observation(RUNS[0])})
        service._original_predecessor_verify(predecessor)
        for mutate in (lambda d: d.__setitem__('seal', '0'*64),
                lambda d: d['prior'].__setitem__('account', 'another-seat'),
                lambda d: d['prior'].__setitem__('root', 'another-root'),
                lambda d: d['prior'].__setitem__('configHash', 'e'*64),
                lambda d: d['runs'][RUNS[0]].__setitem__('observation', '{"state":"ABSENT"}'),
                lambda d: d.__setitem__('receipt_sha256', 'f'*64)):
            with self.subTest():
                broken = json.loads(json.dumps(predecessor))
                mutate(broken)
                with self.assertRaises(ValueError):
                    service._original_predecessor_verify(broken)

    def test_predecessor_is_carried_forward_and_never_becomes_empty(self):
        predecessor = self.build({'response': absent_observation(RUNS[0])})
        args = S(original_predecessor_receipt=None, original_predecessor_sha256=None)
        carried = service._original_predecessor_setting(
            args, {}, {'configHash': self.config_hash}, {'controlSha256': 'a'*64},
            predecessor, self.descriptor)
        self.assertEqual(carried, predecessor)
        # One sealed import per installation: a different receipt is refused.
        path, digest = self.receipt({'response': absent_observation(RUNS[0]), 'extra': 'different'})
        again = S(original_predecessor_receipt=str(path), original_predecessor_sha256=digest)
        with self.assertRaises(SystemExit):
            service._original_predecessor_setting(
                again, {}, {'configHash': self.config_hash}, {'controlSha256': 'a'*64},
                predecessor, self.descriptor)
        # An identical request is idempotent.
        same = S(original_predecessor_receipt=str(path),
            original_predecessor_sha256=predecessor['receipt_sha256'])
        self.assertEqual(service._original_predecessor_setting(
            same, {}, {'configHash': self.config_hash}, {'controlSha256': 'a'*64},
            predecessor, self.descriptor), predecessor)
        # A predecessor without an existing original collection install refuses.
        with self.assertRaises(SystemExit):
            service._original_predecessor_setting(
                again, {}, {'configHash': self.config_hash}, None, None, self.descriptor)
        # Only an actual explicit value counts as supplied.
        with self.assertRaises(SystemExit):
            service._original_predecessor_setting(
                S(original_predecessor_receipt=str(path)), {}, {'configHash': self.config_hash},
                {'controlSha256': 'a'*64}, None, self.descriptor)

    def test_reconciliation_claim_is_durable_and_one_use(self):
        predecessor = self.build({'response': absent_observation(RUNS[0])})
        configuration = {'predecessor': predecessor}
        collector = S(PLAIN_SCOPES=SCOPES)
        with mock.patch.dict(os.environ, {'HOME': str(self.root)}):
            path, destination = service._original_reconcile_claim(
                configuration, RUNS[0], predecessor['receipt_sha256'], collector)
            self.assertTrue(path.is_file())
            self.assertEqual(destination, SCOPES[RUNS[0]]['destination'])
            record = json.loads(path.read_text())
            self.assertEqual(record['state'], 'INTENT')
            self.assertEqual(record['predecessor_sha256'], predecessor['receipt_sha256'])
            # The record's existence is the fence: a second claim never happens.
            with self.assertRaises(FileExistsError):
                service._original_reconcile_claim(
                    configuration, RUNS[0], predecessor['receipt_sha256'], collector)
            # A settled outcome never releases the fence.
            service._original_reconcile_settle(path, {'state': 'COMPLETE',
                'receipt_sha256': 'a'*64}, RUNS[0], predecessor['receipt_sha256'], destination)
            self.assertTrue(path.is_file())
            self.assertEqual(json.loads(path.read_text())['state'], 'COMPLETE')
            with self.assertRaises(FileExistsError):
                service._original_reconcile_claim(
                    configuration, RUNS[0], predecessor['receipt_sha256'], collector)
            # A wrong predecessor digest and an unenrolled run never claim.
            with self.assertRaises(ValueError):
                service._original_reconcile_claim(
                    configuration, RUNS[0], '0'*64, collector)
            with self.assertRaises(ValueError):
                service._original_reconcile_claim(
                    configuration, 'another-run', predecessor['receipt_sha256'], collector)

    def test_real_mcp_text_envelope_and_both_slots_are_retained(self):
        original = absent_observation(RUNS[0])
        envelope = {'response': json.dumps({'content': [
            {'type': 'text', 'text': json.dumps(original)}]})}
        predecessor = self.build(envelope)
        self.assertEqual(set(predecessor['runs']), set(RUNS))
        self.assertEqual(json.loads(predecessor['runs'][RUNS[0]]['observation']), original)
        self.assertIsNone(predecessor['runs'][RUNS[1]]['observation'])
        service._original_predecessor_verify(predecessor)
        del predecessor['runs'][RUNS[1]]
        predecessor['seal'] = service._original_predecessor_seal(predecessor)
        with self.assertRaises(ValueError):
            service._original_predecessor_verify(predecessor)

    def test_duplicate_malformed_and_unexhausted_envelopes_refuse(self):
        original = absent_observation(RUNS[0])
        malformed = json.dumps(original)[:-1] + ',"state":"ABSENT"}'
        for envelope in ({'content': [{'type': 'text', 'text': malformed}]},
                {'content': [{'type': 'text', 'text': '{invalid'}]},
                {'wide': [0] * 4100, 'result': original}):
            with self.subTest(), self.assertRaises(SystemExit):
                self.build(envelope)
        nested = original
        for _ in range(18): nested = {'response': nested}
        with self.assertRaises(SystemExit): self.build(nested)

    def test_legacy_unknown_is_retained_without_invented_fields_or_new_attempt(self):
        original = dict(absent_observation(RUNS[0]), state='UNKNOWN')
        del original['destination_reserved']
        predecessor = self.build({'result': original})
        self.assertEqual(json.loads(predecessor['runs'][RUNS[0]]['observation']), original)
        service._original_predecessor_verify(predecessor)
        with mock.patch.dict(os.environ, {'HOME': str(self.root)}), self.assertRaises(ValueError):
            service._original_reconcile_claim({'predecessor': predecessor}, RUNS[0],
                predecessor['receipt_sha256'], S(PLAIN_SCOPES=SCOPES))

    def test_directory_durability_failure_keeps_the_fence_and_blocks_transport(self):
        predecessor = self.build({'response': absent_observation(RUNS[0])})
        with mock.patch.dict(os.environ, {'HOME': str(self.root)}):
            with mock.patch.object(service, '_original_fsync_dir', side_effect=OSError('directory fsync failed')):
                with self.assertRaises(OSError):
                    service._original_reconcile_claim({'predecessor': predecessor}, RUNS[0],
                        predecessor['receipt_sha256'], S(PLAIN_SCOPES=SCOPES))
            with self.assertRaises(FileExistsError):
                service._original_reconcile_claim({'predecessor': predecessor}, RUNS[0],
                    predecessor['receipt_sha256'], S(PLAIN_SCOPES=SCOPES))

    def test_node_owner_holds_empty_slots_and_rejects_resealed_partial_imports(self):
        node=shutil.which('node');self.assertIsNotNone(node)
        predecessor=self.build({'response':absent_observation(RUNS[0])})
        payload=self.root/'predecessor.json';payload.write_text(json.dumps(predecessor))
        script=r'''
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const { createOriginalDelivery }=await import(process.argv[1]);
const predecessor=JSON.parse(readFileSync(process.argv[2],'utf8'));
const principal='p:tunnel:fabric-c3-570f6f34';
const runs=Object.keys(predecessor.runs);
const value=result=>JSON.parse(result.content[0].text);
for(const retained of [null,predecessor]) {
 const owner=createOriginalDelivery({predecessor:retained},principal);
 for(const run of runs) {
  const result=value(await owner.call('fabric_collect_original',{run_id:run},principal));
  assert.equal(result.state,retained&&run==='fabric-app-native-drivers-j-20261105-01'?'ABSENT':'UNKNOWN');
 }
 await owner.close();
}
const broken=structuredClone(predecessor);delete broken.runs[runs[0]];
const owner=createOriginalDelivery({predecessor:broken},principal);
assert.equal(value(await owner.call('fabric_collect_original',{run_id:runs[1]},principal)).state,'REFUSED');
await owner.close();
console.log('owner import guards passed');
'''
        result=subprocess.run([node,'--input-type=module','-e',script,
            str(closure.HERE/'original-delivery.mjs'),str(payload)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'owner import guards passed')


class ComposedPreservingMigrationTests(unittest.TestCase):
    """Installed v1 configuration -> preserving upgrade -> actual retained return.

    Fixture source pins and the external transport are synthetic. The real
    installer, sealed helper, collector, destination fence and result parser run.
    """
    def setUp(self):
        temporary=tempfile.TemporaryDirectory
        with mock.patch.object(tempfile,'TemporaryDirectory',
                side_effect=lambda **kw:temporary(dir=Path.home(),**kw)):
            self.fixture=closure.InstalledClosureTests(methodName='runTest')
            self.fixture.setUp()
        self.addCleanup(self.cleanup_fixture)
        self.fixture._install();self.home=self.fixture.home
        # The sealed real helper requires a private regular interpreter. Hosted
        # tool-cache permissions/hard links are environment properties, not the
        # subject of this migration fixture. Build a disposable copy through
        # stdlib venv; do not chmod the host interpreter or relax its guard.
        runtime = self.home / "fixture-python"
        venv.EnvBuilder(with_pip=False, symlinks=False).create(runtime)
        interpreter = (runtime / "bin/python").resolve(strict=True)
        interpreter.chmod(0o700)
        self.assertEqual(interpreter.stat().st_nlink, 1)
        self.assertNotEqual(interpreter, Path(sys.executable).resolve())
        self.fixture._child = partial(self.fixture._child, interpreter=interpreter)
        self.marker=self.home/'fixture-remote-reads.jsonl'
        rollout=closure.HERE.parent.parent/'ops/native_fabric/quota_continuity/rollout'
        sys.path.insert(0,str(rollout));self.addCleanup(lambda:sys.path.remove(str(rollout)))
        import test_plain_original_delivery as plain
        self.plain=plain
        spec=importlib.util.spec_from_file_location('composed_original_native',rollout/'native_generation.py')
        self.native=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.native)
        self.stable=self.home/('.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/'
            'handoff_kits/meta-ceo-b-2026-09-08/ext')
        self.stable.mkdir(parents=True,mode=0o700)
        self.store=self.stable.parent/self.native.STORE_NAME
        self.publish()
        selected=self.fixture._child('print(json.dumps(svc._original_collection_native()[0]))\n')
        self.assertEqual(selected.returncode,0,selected.stderr)
        self.descriptor=json.loads(selected.stdout)
        self.paths,self.node,self.backend=seed_original_service(self.fixture.root,self.home,self.descriptor)
        config=json.loads(self.paths['config'].read_text())
        legacy=dict(self.descriptor,schema=service.ORIGINAL_COLLECTION_LEGACY_SCHEMA)
        del legacy['predecessor'];config['originalCollection']=legacy
        config['requestTimeoutMs']=43210
        config['childEnv']['RETAINED_FIXTURE_SETTING']='unchanged'
        self.before_config=config
        self.prior=reseal_fixture_config(self.paths,config)

    def cleanup_fixture(self):
        try:self.fixture.tearDown()
        finally:self.fixture.doCleanups()

    def publish(self):
        plain=self.plain;all_fx=[];scopes={};homes={}
        destination_root=self.home/'evidence'
        final_parent=destination_root/ROOT/'original-collections'
        final_parent.mkdir(parents=True,mode=0o700)
        for run in RUNS:
            with mock.patch.multiple(plain,RUN_ID=run,ROOT=ROOT,PARENT=ROOT,HOST='ubuntu1',MODEL='MiniMax-M3'):
                fx=plain.Fixture(self.home,mode='minimax',model='MiniMax-M3',acquisition_pool='minimax')
                if all_fx:
                    shared=all_fx[0].ctl
                    for evidence in (fx.ctl/'state/remote_sub').iterdir():
                        shutil.copyfile(evidence,shared/'state/remote_sub'/evidence.name)
                        (shared/'state/remote_sub'/evidence.name).chmod(0o600)
                    fx.ctl=shared
                    fx.packet_pin=shared/'state/remote_sub'/(run+'.request.packet')
                    fx.log_path=shared/'state/remote_sub'/(run+'.log')
                    fx.support_pin=shared/'state/remote_sub'/(run+'.support.json')
                stamp=f'2026-11-05T02:36Z [remote_sub id={run} host=ubuntu1] '
                fx.log_path.write_text(''.join(stamp+line+'\n' for line in (
                    'RUN_RESERVED explicit=1','LEASE_OK pool=minimax',
                    f'SUPPORT_VERSION_READY digest={fx.support_digest} policy={plain.POLICY}',
                    f'LAUNCH stdout=lanes_{run}.stdout rc_file=ext/lanes_{run}.rc cwd=~',
                    'LAUNCH_ATTEMPT attempt=1')))
                fx.log_path.chmod(0o600);fx.refresh_binding()
                scopes[run]={'root':ROOT,'parent':ROOT,'host':'ubuntu1','mode':'minimax',
                    'requested_model':'MiniMax-M3','packet_path':str(fx.packet_pin),
                    'packet_sha256':plain.sha(fx.packet),'support_digest':fx.support_digest,
                    'destination':str(final_parent/(run+'-collection-v1')),
                    'source_pins':{'log':plain.sha(fx.log_path.read_bytes()),'support':plain.sha(fx.support_pin.read_bytes())}}
                homes[run]=str(fx.home);all_fx.append(fx)
        self.scopes=scopes
        source=self.home/'native-fixture-source';(source/'ext').mkdir(parents=True,mode=0o700)
        ctl=all_fx[0].ctl
        names=('original_delivery_collector.py','artifact_delivery.py','artifact_reader.py',
               'artifact_production.py','native_runtime_bindings.py','remote_sub_helpers.py')
        files={'ext/'+name:(ctl/name).read_bytes() for name in names}
        fixture_tail=(
            '\nHERE=Path('+repr(str(ctl))+')\n'
            'delivery.HERE=HERE\n'
            'PLAIN_SCOPES.update('+repr(scopes)+')\n'
            'delivery.DESTINATION_ROOT=Path('+repr(str(destination_root))+')\n'
            '_fixture_homes='+repr(homes)+'\n'
            'def _fixture_transport(alias,request):\n'
            ' assert alias=='+repr(plain.ALIAS)+'\n'
            ' with Path('+repr(str(self.marker))+').open("a") as out:out.write(request["run_id"]+"\\n")\n'
            ' code=code_for_request(request)\n'
            ' namespace={}\n'
            ' exec(compile(code[:code.rfind("\\ntry:\\n raw=")],"fixture-reader","exec"),namespace)\n'
            ' response=namespace["remote_envelope"](request,home=Path(_fixture_homes[request["run_id"]]))\n'
            ' return namespace["canonical"](response)\n'
            'delivery.transport=_fixture_transport\n')
        files['ext/original_delivery_collector.py']+=fixture_tail.encode()
        files.update({'pool':b'#!/bin/sh\nexit 0\n','ext/fabric_task.py':b'# fixture task\n','ext/remote_sub.sh':b'#!/bin/sh\nexit 0\n'})
        for name,raw in files.items():(source/name).write_bytes(raw)
        generation=self.native.publish(source,self.stable,{name:self.native.digest(raw) for name,raw in files.items()})
        self.native.select(self.store,generation.name,None)

    def test_composed_preserving_migration_imports_then_observes_once(self):
        node=shutil.which('node');self.assertIsNotNone(node,'composition requires the existing Node runtime')
        prior=self.fixture._child(
            'collector=svc._original_collection_collector()\n'
            'print(json.dumps({"carrier":collector._gateway_original_delivery("collect",'+repr(RUNS[1])+'),'
            '"j":collector._gateway_collection_status('+repr(RUNS[0])+')}))\n')
        self.assertEqual(prior.returncode,0,prior.stderr)
        observed=json.loads(prior.stdout)
        self.assertEqual(observed['carrier']['state'],'COMPLETE',observed)
        self.assertEqual(observed['j']['state'],'ABSENT')
        receipt=self.home/'retained-first-call-receipt.json'
        receipt.write_text(json.dumps({'response':json.dumps({'content':[{'type':'text','text':json.dumps(observed['j'])}]})}))
        digest=hashlib.sha256(receipt.read_bytes()).hexdigest()
        argv=['upgrade','--account',ACCOUNT,'--port','45280','--source',str(closure.HERE),
              '--node',str(self.node),'--backend',str(self.backend),
              '--original-predecessor-receipt',str(receipt),'--original-predecessor-sha256',digest]
        upgraded=self.fixture._child('svc._lifecycle_inspect=lambda account,label,roots,**kwargs:None\n'
            'svc.cmd_upgrade(svc.build_parser().parse_args('+repr(argv)+'))\n')
        self.assertEqual(upgraded.returncode,0,upgraded.stderr)
        after=json.loads(self.paths['config'].read_text());configuration=after['originalCollection']
        self.assertEqual(configuration['predecessor']['receipt_sha256'],digest)
        self.assertEqual(json.loads(configuration['predecessor']['runs'][RUNS[1]]['observation']),observed['carrier'])
        self.assertEqual({k:v for k,v in after.items() if k!='originalCollection'},
                         {k:v for k,v in self.before_config.items() if k!='originalCollection'})
        self.assertEqual(json.loads(self.paths['manifest'].read_text())['dependencyTreeHash'],self.prior['dependencyTreeHash'])
        descriptor_path=self.home/'descriptor.json';descriptor_path.write_text(json.dumps(configuration))
        driver=self.home/'driver.mjs';driver.write_text(DRIVER)
        child_env={'HOME':str(self.home),'PATH':'/usr/bin:/bin','LANG':'C'}
        # Hosted Linux Python can depend on setup-python's shared-library path.
        # Keep that loader dependency when the real sealed helper is executed.
        if 'LD_LIBRARY_PATH' in os.environ:
            child_env['LD_LIBRARY_PATH']=os.environ['LD_LIBRARY_PATH']
        completed=subprocess.run([node,str(driver),str(self.paths['base']/'original-delivery.mjs'),str(descriptor_path)],
            cwd=self.fixture.empty,env=child_env,
            capture_output=True,text=True,timeout=30)
        self.assertEqual(completed.returncode,0,completed.stderr)
        returned=json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(returned['collect'],observed['j'])
        self.assertEqual(returned['collect_after'],observed['j'])
        self.assertEqual(returned['carrier'],observed['carrier'])
        self.assertEqual(returned['reconcile']['state'],'COMPLETE',returned)
        self.assertEqual(returned['result_text'],self.plain.STDOUT.decode())
        self.assertEqual(returned['restart_reconcile']['state'],'REFUSED')
        self.assertEqual(self.marker.read_text().splitlines(),[RUNS[1],RUNS[0]])
        record=self.paths['state']/('original-reconciliation-'+RUNS[0]+'.json')
        self.assertEqual(json.loads(record.read_text())['state'],'COMPLETE')
        readback=self.fixture._child('svc.cmd_original_predecessor_readback(type("Args",(),{"account":'+repr(ACCOUNT)+'})())\n')
        self.assertEqual(readback.returncode,0,readback.stderr)
        self.assertTrue(json.loads(readback.stdout)['sealed'])


DRIVER = r"""import cp from 'node:child_process';
import { syncBuiltinESMExports } from 'node:module';
const helperDiagnostics = [];
for (const method of ['spawn', 'spawnSync', 'execFile', 'execFileSync']) {
  const original = cp[method];
  cp[method] = function (...args) {
    const started = performance.now();
    const options = args.find(value => value && typeof value === 'object' && !Array.isArray(value));
    const record = { method, executable: String(args[0]),
      flags: Array.isArray(args[1]) ? args[1].filter(value => typeof value === 'string' && value.startsWith('-')) : [],
      ldLibraryPathPresent: !!options?.env?.LD_LIBRARY_PATH,
      stdoutBytes: 0, stderrBytes: 0, stdout: '', stderr: '' };
    helperDiagnostics.push(record);
    const capture = (key, value) => {
      const bytes = Buffer.isBuffer(value) ? value : Buffer.from(String(value ?? ''));
      record[key + 'Bytes'] += bytes.length;
      const remaining = 4096 - Buffer.byteLength(record[key]);
      if (remaining > 0) record[key] += bytes.subarray(0, remaining).toString('utf8');
    };
    let result;
    try { result = Reflect.apply(original, this, args); }
    catch (error) {
      record.error = { name: error?.name, code: error?.code };
      record.status = error?.status ?? null; record.signal = error?.signal ?? null;
      capture('stdout', error?.stdout); capture('stderr', error?.stderr);
      record.elapsedMs = Math.round(performance.now() - started);
      throw error;
    }
    if (result && typeof result === 'object' && 'status' in result) {
      record.status = result.status; record.signal = result.signal;
      record.error = result.error ? { name: result.error.name, code: result.error.code } : null;
      capture('stdout', result.stdout); capture('stderr', result.stderr);
      record.elapsedMs = Math.round(performance.now() - started);
    } else if (result && typeof result.once === 'function') {
      result.stdout?.on('data', data => capture('stdout', data));
      result.stderr?.on('data', data => capture('stderr', data));
      result.once('error', error => { record.error = { name: error.name, code: error.code }; });
      result.once('close', (status, signal) => {
        record.status = status; record.signal = signal;
        record.elapsedMs = Math.round(performance.now() - started);
      });
    }
    return result;
  };
}
syncBuiltinESMExports();
import { readFileSync, lstatSync } from 'node:fs';
import { createHash } from 'node:crypto';
const positiveControl = await new Promise((resolve, reject) => {
  const child = cp.spawn(process.execPath, ['-e', 'process.stdout.write("fixture-spawn-control")'],
    { stdio: ['ignore', 'pipe', 'pipe'], env: process.env });
  child.once('error', reject);
  child.once('close', resolve);
});
if (positiveControl !== 0 || helperDiagnostics.length !== 1 ||
    helperDiagnostics[0].method !== 'spawn' ||
    helperDiagnostics[0].stdout !== 'fixture-spawn-control') {
  throw new Error('synthetic helper spawn diagnostic positive control failed');
}
function pinnedFileDiagnostic(filename, expected, executable) {
  try {
    const stat = lstatSync(filename);
    return { filename, regular: stat.isFile(), symbolicLink: stat.isSymbolicLink(),
      links: stat.nlink, mode: (stat.mode & 0o7777).toString(8), owner: stat.uid,
      currentOwner: process.getuid(), executableRequired: executable,
      digestMatches: createHash('sha256').update(readFileSync(filename)).digest('hex') === expected };
  } catch (error) { return { filename, error: error.code ?? error.name }; }
}
const modulePath = process.argv[2];
const descriptorPath = process.argv[3];
const { createOriginalDelivery } = await import(modulePath);
const configuration = JSON.parse(readFileSync(descriptorPath, 'utf8'));
const principal = 'p:tunnel:fabric-c3-570f6f34';
const runId = 'fabric-app-native-drivers-j-20261105-01';
const owner = createOriginalDelivery(configuration, principal);
const text = result => result.content.find(item => item.type === 'text').text;
const carrier = text(await owner.call('fabric_collect_original', { run_id: 'fabric-app-application-process-carrier-20261105-01' }, principal));
const collect = text(await owner.call('fabric_collect_original', { run_id: runId }, principal));
const collectAfter = text(await owner.call('fabric_collect_original', { run_id: runId }, principal));
const reconcile = text(await owner.call('fabric_original_collection_reconcile',
  { run_id: runId, predecessor_sha256: configuration.predecessor.receipt_sha256 }, principal));
const parsed = JSON.parse(reconcile);
if (parsed.state !== 'COMPLETE') {
  process.stderr.write('MMX_SYNTHETIC_PREFLIGHT_DIAGNOSTICS ' + JSON.stringify({
    calls: helperDiagnostics, files: [
      pinnedFileDiagnostic(configuration.pythonPath, configuration.pythonSha256, true),
      pinnedFileDiagnostic(configuration.controlPath, configuration.controlSha256, false),
    ], node: process.version,
  }) + '\n');
  throw new Error('composed reconciliation failed: ' + reconcile);
}
const resultText = text(await owner.call('fabric_original_collection_result',
  { run_id: runId, receipt_sha256: parsed.receipt_sha256 }, principal));
await owner.close();
const restarted = createOriginalDelivery(configuration, principal);
const restartReconcile = text(await restarted.call('fabric_original_collection_reconcile', { run_id: runId, predecessor_sha256: configuration.predecessor.receipt_sha256 }, principal));
await restarted.close();
console.log(JSON.stringify({ collect: JSON.parse(collect), collect_after: JSON.parse(collectAfter),
  reconcile: parsed, result_text: resultText, carrier: JSON.parse(carrier), restart_reconcile: JSON.parse(restartReconcile) }));
"""


class OriginalUpgradeCustodyTests(unittest.TestCase):
    @contextlib.contextmanager
    def installation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / 'home'
            home.mkdir()
            source = fixtures._make_source(root)
            node, backend = fixtures._make_node(root), fixtures._make_backend(root)
            descriptor = OriginalSelectionTests().descriptor(home)
            args = fixtures._stage_args(source, node, backend, ACCOUNT, 45280)
            args.fabric_only = args.modern_fabric_protocol = args.original_collection = True
            receipt = root / 'first-call.json'
            receipt.write_text(json.dumps({'call': {'response': absent_observation(RUNS[0])}}))
            digest = hashlib.sha256(receipt.read_bytes()).hexdigest()
            with mock.patch.dict(os.environ, {'HOME': str(home)}), \
                    mock.patch.object(service, '_run', fixtures.CmdRecorder()), \
                    mock.patch.object(service, '_launchd_inspect', return_value=None), \
                    mock.patch.object(service, '_lifecycle_inspect', return_value=None), \
                    mock.patch.object(service, '_original_collection_native',
                                      return_value=(descriptor, None, None, None)), \
                    mock.patch.object(service, '_original_collection_collector',
                                      return_value=S(PLAIN_SCOPES=SCOPES,
                                                     _gateway_collection_status=complete_observation)):
                fixtures._capture_stdout(lambda: service.cmd_stage(args))
                paths = service._build_runtime_roots(ACCOUNT)
                fixtures._seed_node_modules(paths)
                original_fixture_lock(home)
                fixtures._seal_runtime(ACCOUNT)
                upgraded = fixtures._make_upgrade_source(root)
                changed = upgraded / 'original-delivery.mjs'
                changed.write_text(changed.read_text() + '\n// changed original owner fixture\n')
                upgrade = fixtures._stage_args(upgraded, node, backend, ACCOUNT, 45280)
                upgrade.original_predecessor_receipt = str(receipt)
                upgrade.original_predecessor_sha256 = digest
                yield paths, upgrade, digest

    def interrupt_after_module(self, paths, upgrade):
        target = paths['base'] / 'original-delivery.mjs'
        old = target.read_bytes()
        atomic = service._atomic_write_bytes
        def interrupted(path, raw, *args, **kwargs):
            result = atomic(path, raw, *args, **kwargs)
            if Path(path) == target:
                raise OSError('interrupted after original owner module replacement')
            return result
        with mock.patch.object(service, '_atomic_write_bytes', interrupted):
            with self.assertRaisesRegex(OSError, 'after original owner'):
                service.cmd_upgrade(upgrade)
        self.assertNotEqual(target.read_bytes(), old)

    def test_same_upgrade_resumes_partial_module_install_without_rediscovery(self):
        with self.installation() as (paths, upgrade, digest):
            prior = json.loads(paths['manifest'].read_text())
            self.interrupt_after_module(paths, upgrade)
            def frozen_native(configuration=None, **kwargs):
                self.assertIsNotNone(configuration, 'fresh native discovery forbidden')
                self.assertEqual(configuration['predecessor']['receipt_sha256'], digest)
                return configuration, None, None, None
            with mock.patch.object(service, '_original_collection_native', side_effect=frozen_native):
                rc, _ = fixtures._capture_stdout(lambda: service.cmd_upgrade(upgrade))
            self.assertEqual(rc, 0)
            after = json.loads(paths['manifest'].read_text())
            self.assertEqual(after['dependencyTreeHash'], prior['dependencyTreeHash'])
            self.assertEqual(after['configHash'], service._sha256_file(paths['config']))
            for name, expected in after['files'].items():
                self.assertEqual(service._sha256_file(paths['base'] / name), expected)
            predecessor = json.loads(paths['config'].read_text())['originalCollection']['predecessor']
            self.assertEqual(predecessor['receipt_sha256'], digest)
            self.assertEqual(json.loads(predecessor['runs'][RUNS[1]]['observation']),
                             complete_observation(RUNS[1]))


    def target_snapshot(self, paths):
        return {str(p): p.read_bytes() for p in service._stage_dest_files(paths) if p.exists()}

    @contextlib.contextmanager
    def forbid_target_writes(self, paths):
        targets = set(service._stage_dest_files(paths))
        atomic = service._atomic_write_bytes
        def checked(path, *args, **kwargs):
            if Path(path) in targets:
                raise AssertionError('completed or refused original must not replace targets')
            return atomic(path, *args, **kwargs)
        with mock.patch.object(service, '_atomic_write_bytes', checked):
            yield

    def test_plan_directory_sync_failure_writes_no_target_and_resumes_same_plan(self):
        with self.installation() as (paths, upgrade, digest):
            before = self.target_snapshot(paths)
            sync = service._original_install_fsync_parent
            def fail_plan(path):
                if Path(path) == paths['state'] and list(paths['state'].glob('original-preserving-upgrade-*.json')):
                    raise OSError('plan directory sync failed')
                return sync(path)
            with mock.patch.object(service, '_original_install_fsync_parent', fail_plan):
                with self.assertRaisesRegex(OSError, 'plan directory'):
                    service.cmd_upgrade(upgrade)
            self.assertEqual(self.target_snapshot(paths), before)
            plans = list(paths['state'].glob('original-preserving-upgrade-*.json'))
            self.assertEqual(len(plans), 1)
            retained = plans[0].read_bytes()
            with self.assertRaisesRegex(SystemExit, 'requires reconciliation'):
                service.cmd_start(S(account=ACCOUNT))
            with self.assertRaisesRegex(ValueError, 'requires reconciliation'):
                service._original_installed_descriptor()
            with mock.patch.object(service, '_original_predecessor_setting',
                                   side_effect=AssertionError('predecessor must not be rebuilt')):
                rc, _ = fixtures._capture_stdout(lambda: service.cmd_upgrade(upgrade))
            self.assertEqual(rc, 0)
            self.assertEqual(plans[0].read_bytes(), retained)

    def test_manifest_commit_gap_completes_receipt_without_target_replacement(self):
        with self.installation() as (paths, upgrade, digest):
            publish = service._fabric_release_new
            def no_completion(path, raw):
                if str(path).endswith('.complete.json'):
                    raise OSError('completion not yet published')
                return publish(path, raw)
            with mock.patch.object(service, '_fabric_release_new', no_completion):
                with self.assertRaisesRegex(OSError, 'completion not yet'):
                    service.cmd_upgrade(upgrade)
            committed = self.target_snapshot(paths)
            self.assertEqual(json.loads(paths['manifest'].read_text())['configHash'],
                             service._sha256_file(paths['config']))
            with self.assertRaisesRegex(SystemExit, 'requires reconciliation'):
                service.cmd_start(S(account=ACCOUNT))
            with self.forbid_target_writes(paths), \
                    mock.patch.object(service, '_original_predecessor_setting',
                                      side_effect=AssertionError('predecessor must not be rebuilt')):
                rc, _ = fixtures._capture_stdout(lambda: service.cmd_upgrade(upgrade))
                self.assertEqual(rc, 0)
                rc, _ = fixtures._capture_stdout(lambda: service.cmd_upgrade(upgrade))
                self.assertEqual(rc, 0)
            self.assertEqual(self.target_snapshot(paths), committed)
            self.assertEqual(len(list(paths['state'].glob('original-preserving-upgrade-*.json'))), 2)

    def test_visible_completion_requires_durable_readback_before_start(self):
        with self.installation() as (paths, upgrade, digest):
            sync = service._original_install_fsync_parent
            def fail_completion(path):
                if Path(path) == paths['state'] and list(paths['state'].glob('original-preserving-upgrade-*.complete.json')):
                    raise OSError('completion directory sync failed')
                return sync(path)
            with mock.patch.object(service, '_original_install_fsync_parent', fail_completion):
                with self.assertRaisesRegex(OSError, 'completion directory'):
                    service.cmd_upgrade(upgrade)
                with self.assertRaisesRegex(OSError, 'completion directory'):
                    service.cmd_start(S(account=ACCOUNT))
                with self.assertRaisesRegex(OSError, 'completion directory'):
                    service._original_installed_descriptor()
            committed = self.target_snapshot(paths)
            records = {p.name: p.read_bytes() for p in paths['state'].glob('original-preserving-upgrade-*.json')}
            with self.forbid_target_writes(paths):
                rc, _ = fixtures._capture_stdout(lambda: service.cmd_upgrade(upgrade))
            self.assertEqual(rc, 0)
            self.assertEqual(self.target_snapshot(paths), committed)
            self.assertEqual({p.name: p.read_bytes() for p in paths['state'].glob('original-preserving-upgrade-*.json')}, records)

    def test_pending_original_refuses_changed_request_source_and_foreign_target(self):
        for change in ('request', 'source', 'foreign', 'symlink', 'malformed_plan'):
            with self.subTest(change=change), self.installation() as (paths, upgrade, digest):
                self.interrupt_after_module(paths, upgrade)
                if change == 'request':
                    upgrade.port = 45281
                elif change == 'source':
                    p = Path(upgrade.source) / 'original-delivery.mjs'
                    p.write_text(p.read_text() + '\n// different source after original intent\n')
                elif change == 'foreign':
                    paths['config'].write_bytes(paths['config'].read_bytes() + b'\n')
                elif change == 'symlink':
                    target = paths['base'] / 'original-delivery.mjs'
                    backing = paths['base'] / 'foreign-copy.mjs'
                    backing.write_bytes(target.read_bytes())
                    target.unlink()
                    target.symlink_to(backing)
                else:
                    plan = next(paths['state'].glob('original-preserving-upgrade-*.json'))
                    plan.write_bytes(plan.read_bytes()[:80])
                with self.forbid_target_writes(paths):
                    with self.assertRaises(SystemExit):
                        service.cmd_upgrade(upgrade)
                self.assertFalse(list(paths['state'].glob('original-preserving-upgrade-*.complete.json')))

    def test_orphan_completion_holds_upgrade_and_start_without_installing(self):
        with self.installation() as (paths, upgrade, digest):
            before = self.target_snapshot(paths)
            orphan = paths['state'] / ('original-preserving-upgrade-' + 'a' * 64 + '.complete.json')
            orphan.write_bytes(service._original_install_encode(
                {'schema': service._ORIGINAL_INSTALL_SCHEMA, 'planSha256': 'a' * 64,
                 'targetManifestSha256': 'b' * 64, 'state': 'COMPLETE'}))
            orphan.chmod(0o600)
            with self.forbid_target_writes(paths):
                with self.assertRaisesRegex(SystemExit, 'orphan completion'):
                    service.cmd_upgrade(upgrade)
                with self.assertRaisesRegex(SystemExit, 'orphan completion'):
                    service.cmd_start(S(account=ACCOUNT))
            self.assertEqual(self.target_snapshot(paths), before)

    def test_completed_history_does_not_reinstall_or_block_a_later_source(self):
        with self.installation() as (paths, upgrade, digest):
            fixtures._capture_stdout(lambda: service.cmd_upgrade(upgrade))
            historical = {p.name: p.read_bytes() for p in paths['state'].glob('original-preserving-upgrade-*.json')}
            changed = Path(upgrade.source) / 'original-delivery.mjs'
            changed.write_text(changed.read_text() + '\n// a later admitted source revision\n')
            fixtures._capture_stdout(lambda: service.cmd_upgrade(upgrade))
            self.assertEqual((paths['base'] / changed.name).read_bytes(), changed.read_bytes())
            for name, raw in historical.items():
                self.assertEqual((paths['state'] / name).read_bytes(), raw)
            self.assertEqual(len(list(paths['state'].glob('original-preserving-upgrade-*.json'))), 4)
            with self.forbid_target_writes(paths):
                rc, _ = fixtures._capture_stdout(lambda: service.cmd_upgrade(upgrade))
            self.assertEqual(rc, 0)

    def test_directory_open_failure_holds_plan_without_target_writes(self):
        with self.installation() as (paths, upgrade, digest):
            before = self.target_snapshot(paths)
            original_open = service.os.open
            def fail_directory(path, flags, *args, **kwargs):
                if Path(path) == paths['state']:
                    raise OSError('state directory open failed')
                return original_open(path, flags, *args, **kwargs)
            with mock.patch.object(service.os, 'open', fail_directory):
                with self.assertRaisesRegex(OSError, 'directory open'):
                    service.cmd_upgrade(upgrade)
            self.assertEqual(self.target_snapshot(paths), before)
            plans = list(paths['state'].glob('original-preserving-upgrade-*.json'))
            self.assertEqual(len(plans), 1)
            retained = plans[0].read_bytes()
            rc, _ = fixtures._capture_stdout(lambda: service.cmd_upgrade(upgrade))
            self.assertEqual(rc, 0)
            self.assertEqual(plans[0].read_bytes(), retained)

    def test_directory_open_failure_cannot_admit_visible_completion(self):
        with self.installation() as (paths, upgrade, digest):
            original_open = service.os.open
            def fail_directory(path, flags, *args, **kwargs):
                if Path(path) == paths['state'] and list(paths['state'].glob('original-preserving-upgrade-*.complete.json')):
                    raise OSError('completion directory open failed')
                return original_open(path, flags, *args, **kwargs)
            with mock.patch.object(service.os, 'open', fail_directory):
                with self.assertRaisesRegex(OSError, 'completion directory open'):
                    service.cmd_upgrade(upgrade)
                with self.assertRaisesRegex(OSError, 'completion directory open'):
                    service.cmd_start(S(account=ACCOUNT))
                with self.assertRaisesRegex(OSError, 'completion directory open'):
                    service._original_installed_descriptor()
            before = self.target_snapshot(paths)
            records = {p.name: p.read_bytes() for p in paths['state'].glob('original-preserving-upgrade-*.json')}
            with self.forbid_target_writes(paths):
                rc, _ = fixtures._capture_stdout(lambda: service.cmd_upgrade(upgrade))
            self.assertEqual(rc, 0)
            self.assertEqual(self.target_snapshot(paths), before)
            self.assertEqual({p.name: p.read_bytes() for p in paths['state'].glob('original-preserving-upgrade-*.json')}, records)

    def test_pending_upgrade_requires_exact_stopped_service_evidence(self):
        strict_inspect = service._lifecycle_inspect
        with self.installation() as (paths, upgrade, digest):
            self.interrupt_after_module(paths, upgrade)
            before = self.target_snapshot(paths)
            records = {p.name: p.read_bytes() for p in paths['state'].glob('original-preserving-upgrade-*.json')}
            for rc, stdout, stderr in [(2, '', 'permission denied'), (0, 'malformed', '')]:
                with self.subTest(rc=rc), self.forbid_target_writes(paths), \
                        mock.patch.object(service, '_lifecycle_inspect', strict_inspect), \
                        mock.patch.object(service, '_run', return_value=subprocess.CompletedProcess([], rc, stdout, stderr)):
                    with self.assertRaisesRegex(SystemExit, 'indeterminate'):
                        service.cmd_upgrade(upgrade)
                self.assertEqual(self.target_snapshot(paths), before)
                self.assertEqual({p.name: p.read_bytes() for p in paths['state'].glob('original-preserving-upgrade-*.json')}, records)
            label = 'com.mastermind.studio-direct-private.' + ACCOUNT
            absent = 'Bad request.\nCould not find service "' + label + '" in domain for user gui: ' + str(os.getuid()) + '\n'
            with mock.patch.object(service, '_lifecycle_inspect', strict_inspect), \
                    mock.patch.object(service, '_run', return_value=subprocess.CompletedProcess([], 113, '', absent)):
                rc, _ = fixtures._capture_stdout(lambda: service.cmd_upgrade(upgrade))
            self.assertEqual(rc, 0)



if __name__=='__main__':unittest.main()
