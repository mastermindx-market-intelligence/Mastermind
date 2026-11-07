"""Actual original evidence validation with an in-process remote-reader fixture."""
import base64
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import unittest
from unittest import mock

import test_plain_original_delivery as fixture

RUNS = ('fabric-app-native-drivers-j-20261105-01',
        'fabric-app-application-process-carrier-20261105-01')
ROOT = 'fabric-application-integration-20261104-sol'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


class ApplicationOriginalCollection(unittest.TestCase):
    RUN = RUNS[0]

    def setUp(self):
        self.directory = fixture.stack('application-original-proof-')
        self.addCleanup(self.directory.cleanup)
        self.patch = mock.patch.multiple(fixture, RUN_ID=self.RUN, ROOT=ROOT,
            PARENT=ROOT, HOST='ubuntu1', MODEL='MiniMax-M3')
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.fx = fixture.Fixture(Path(self.directory.name), mode='minimax',
            model='MiniMax-M3', acquisition_pool='minimax')
        self.collector = self.fx.collector_module()
        self.run = self.RUN
        # The fixture table is synthetic source evidence, not an authorization
        # override. Every byte/path/hash/validator check still executes.
        original = self.collector.PLAIN_SCOPES[self.run]
        self.original = dict(original)
        stamp = f'2026-11-05T02:36Z [remote_sub id={self.run} host=ubuntu1] '
        self.fx.log_path.write_text(''.join(stamp + line + '\n' for line in (
            'RUN_RESERVED explicit=1', 'LEASE_OK pool=minimax',
            f'SUPPORT_VERSION_READY digest={self.fx.support_digest} policy={fixture.POLICY}',
            f'LAUNCH stdout=lanes_{self.run}.stdout rc_file=ext/lanes_{self.run}.rc cwd=~',
            'LAUNCH_ATTEMPT attempt=1')))
        self.fx.log_path.chmod(0o600)
        self.collector.PLAIN_SCOPES[self.run] = dict(original,
            packet_path=str(self.fx.packet_pin), packet_sha256=sha(self.fx.packet),
            support_digest=self.fx.support_digest, destination=self.fx.destination,
            source_pins={'log': sha(self.fx.log_path.read_bytes()),
                         'support': sha(self.fx.support_pin.read_bytes())})
        self.fx.refresh_binding()
        environment = mock.patch.dict(os.environ, {}, clear=False)
        environment.start(); self.addCleanup(environment.stop)
        os.environ.pop('CODEX_THREAD_ID', None)
        os.environ.pop('POOL_ORCHESTRATOR_ID', None)
        self.observations = []
        self.transport = mock.patch.object(self.collector.delivery, 'transport', self.observe)
        self.transport.start(); self.addCleanup(self.transport.stop)
        # Any accidental physical launch is a test failure. The only transport
        # below executes the actual generated reader in this process.
        deny = mock.patch('subprocess.Popen', side_effect=AssertionError('real process forbidden'))
        deny.start(); self.addCleanup(deny.stop)

    def observe(self, alias, request):
        self.assertEqual(alias, fixture.ALIAS)
        self.observations.append(request)
        code = self.collector.code_for_request(request)
        namespace = {}
        exec(compile(code[:code.rfind('\ntry:\n raw=')], 'inert-original-reader', 'exec'), namespace)
        if getattr(self, 'forbid_payload_open', False):
            real_open = os.open
            def observed_open(filename, *args, **kwargs):
                name = os.fspath(filename) if not isinstance(filename, int) else ''
                self.assertFalse(str(name).endswith(('.stdout', '.process.jsonl')), name)
                return real_open(filename, *args, **kwargs)
            with mock.patch.object(namespace['os'], 'open', side_effect=observed_open):
                result = namespace['remote_envelope'](request, home=self.fx.home)
        else:
            result = namespace['remote_envelope'](request, home=self.fx.home)
        return namespace['canonical'](result)

    def call(self, action='collect', digest=None):
        return self.collector._gateway_original_delivery(action, self.run, digest)

    def completed(self):
        result = self.call()
        self.assertEqual(result['state'], 'COMPLETE', result)
        self.assertEqual(len(self.observations), 1)
        return result

    def test_exact_source_scope_matches_evidence_and_preserves_eight_predecessors(self):
        source = json.loads(Path(__file__).with_name('fabric_application_original_scopes.json').read_text())
        self.assertEqual(set(source['scopes']), set(RUNS))
        self.assertEqual(source['scopes'][self.run], self.original)
        self.assertEqual(self.collector.GATEWAY_ORIGINAL_RUNS, frozenset(RUNS))
        self.assertEqual(len(self.collector.PLAIN_SCOPES), 10)
        self.assertEqual(len(set(self.collector.PLAIN_SCOPES) - set(RUNS)), 8)
        self.assertFalse(source['producer_root_authenticated'])

    def test_real_collection_and_pinned_read_without_native_caller(self):
        result = self.completed()
        returned = self.call('result', result['receipt_sha256'])
        self.assertEqual(base64.b64decode(returned['stdout_base64']), fixture.STDOUT)
        self.assertEqual(len(self.observations), 1)
        receipt = json.loads((Path(self.fx.destination)/'receipt.json').read_bytes())
        self.assertEqual(receipt['acceptance'], 'NOT_RECORDED')
        self.assertEqual(receipt['lease_settlement'], 'UNKNOWN')
        self.assertEqual(receipt['controller_state'], 'UNKNOWN')
        self.assertFalse(receipt['original_operation_mutated'])
        self.assertIsNone(receipt.get('plain_launch_binding'))
        self.assertFalse(receipt['plain_provenance']['producer_root_authenticated'])
        self.assertFalse(receipt['plain_provenance']['producer_packet_consumption_attested'])
        self.assertNotIn('CODEX_THREAD_ID', os.environ)

    def test_public_native_caller_checks_remain_required(self):
        for value in (None, 'a-different-session'):
            with self.subTest(value=value), mock.patch.dict(os.environ, {}, clear=False):
                if value is not None: os.environ['CODEX_THREAD_ID'] = value
                for call in (
                    lambda: self.collector.load_binding(self.fx.binding_path(), run_id=self.run, root=ROOT, parent=ROOT),
                    lambda: self.collector.collect(self.fx.binding_path(), run_id=self.run, root=ROOT,
                                                  parent=ROOT, destination=self.fx.destination),
                    lambda: self.collector.read_collection(Path(self.fx.destination)/'receipt.json',
                        expected_sha256='0'*64, run_id=self.run, root=ROOT, parent=ROOT)):
                    with self.assertRaisesRegex(ValueError, 'original_native_root_required'): call()
        self.assertFalse(self.observations)

    def test_excluded_scopes_and_extra_receipt_selector_refuse_before_transport(self):
        for run in ('fabric-app-metabolism-durable-20261105-01',
                    'fabric-app-native-core-schema-20261105-01', 'future-run',
                    *sorted(set(self.collector.PLAIN_SCOPES)-set(RUNS))):
            with self.subTest(run=run), self.assertRaises(ValueError):
                self.collector._gateway_original_delivery('collect', run)
        for action, digest in (('other',None),('collect','0'*64),('status','0'*64),('result',None)):
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.call(action,digest)
        self.assertFalse(self.observations)

    def test_source_pin_change_refuses_before_reservation(self):
        self.fx.packet_pin.write_bytes(self.fx.packet+b'changed')
        result=self.call()
        self.assertEqual(result['state'],'REFUSED')
        self.assertFalse(Path(self.fx.destination).exists())
        self.assertFalse(self.observations)

    def test_historical_validator_change_refuses(self):
        target=self.fx.ctl/'artifact_reader.py';target.write_bytes(target.read_bytes()+b'\n# changed\n')
        self.assertEqual(self.call()['state'],'REFUSED')
        self.assertFalse(self.observations)

    def test_changed_log_pin_remains_guarded(self):
        self.fx.log_path.write_bytes(self.fx.log_path.read_bytes()+b'not the pinned evidence\n')
        self.assertEqual(self.call()['state'],'REFUSED')
        self.assertFalse(self.observations)

    def test_pinned_invalid_launch_events_refuse_before_reservation(self):
        original = self.fx.log_path.read_text()
        for before, after in (('cwd=~', 'cwd=/foreign'),
                ('LAUNCH_ATTEMPT attempt=1', 'LAUNCH_ATTEMPT attempt=2'),
                ('LEASE_OK pool=minimax', 'LEASE_OK pool=glm'),
                ('SUPPORT_VERSION_READY digest=', 'UNQUALIFIED_SUPPORT digest=')):
            with self.subTest(event=before):
                self.assertIn(before, original)
                self.fx.log_path.write_text(original.replace(before, after))
                self.collector.PLAIN_SCOPES[self.run]['source_pins']['log'] = sha(self.fx.log_path.read_bytes())
                self.assertEqual(self.call()['state'], 'REFUSED')
                self.assertFalse(Path(self.fx.destination).exists())
                self.assertFalse(self.observations)

    def test_host_registry_modes_and_alias_are_validated(self):
        path = self.fx.ctl/'hosts.json'
        for host in ({'allowed_modes': [], 'ssh_alias': fixture.ALIAS},
                     {'allowed_modes': ['minimax'], 'ssh_alias': '-oProxyCommand=foreign'}):
            with self.subTest(host=host):
                path.write_text(json.dumps({'ubuntu1': host}))
                self.assertEqual(self.call()['state'], 'REFUSED')
                self.assertFalse(Path(self.fx.destination).exists())
                self.assertFalse(self.observations)

    def test_source_change_after_remote_read_prevents_publication(self):
        def changed(alias,request):
            result=self.observe(alias,request)
            self.fx.packet_pin.write_bytes(self.fx.packet+b'changed')
            return result
        with mock.patch.object(self.collector.delivery,'transport',changed):
            result=self.call()
        self.assertEqual(result['state'],'UNKNOWN')
        self.assertTrue(result['destination_reserved'])
        self.assertFalse((Path(self.fx.destination)/'receipt.json').exists())
        self.assertEqual(len(self.observations),1)
        self.assertEqual(self.call()['state'],'UNKNOWN')
        self.assertEqual(len(self.observations),1)

    def test_nonzero_remote_result_is_not_complete(self):
        (self.fx.home/f'lanes/ext/lanes_{self.run}.rc').write_bytes(b'124\n')
        self.forbid_payload_open = True
        self.assertEqual(self.call()['state'],'UNKNOWN')
        self.assertEqual(len(self.observations),1)
        self.assertEqual(self.call()['state'],'UNKNOWN')
        self.assertEqual(len(self.observations),1)

    def test_partial_destination_survives_new_import_without_transport(self):
        Path(self.fx.destination).mkdir(mode=0o700)
        self.assertEqual(self.call()['state'],'UNKNOWN')
        fresh = self.fx.collector_module()
        self.assertIsNot(fresh, self.collector)
        fresh.PLAIN_SCOPES[self.run] = dict(self.collector.PLAIN_SCOPES[self.run])
        with mock.patch.object(fresh.delivery, 'transport', side_effect=AssertionError('replayed transport')):
            self.assertEqual(fresh._gateway_original_delivery('status', self.run)['state'], 'UNKNOWN')
            self.assertEqual(fresh._gateway_original_delivery('collect', self.run)['state'], 'UNKNOWN')
        self.assertFalse(self.observations)

    def test_missing_complete_chunk_remains_reserved_unknown(self):
        self.completed()
        (Path(self.fx.destination)/'stdout.000').unlink()
        status=self.call('status')
        self.assertEqual(status['state'],'UNKNOWN')
        self.assertTrue(status['destination_reserved'])
        self.assertEqual(self.call()['state'],'UNKNOWN')
        self.assertEqual(len(self.observations),1)

    def test_wrong_digest_and_replaced_receipt_refuse(self):
        self.completed()
        with self.assertRaises(ValueError): self.call('result','0'*64)
        receipt=Path(self.fx.destination)/'receipt.json'
        receipt.write_bytes(b'{}')
        self.assertEqual(self.call('status')['state'],'UNKNOWN')
        self.assertEqual(len(self.observations),1)

    def test_concurrent_collection_uses_one_destination_reservation(self):
        entered,release=threading.Event(),threading.Event()
        def barrier(alias,request):
            entered.set();self.assertTrue(release.wait(5));return self.observe(alias,request)
        with mock.patch.object(self.collector.delivery,'transport',barrier), concurrent.futures.ThreadPoolExecutor(2) as pool:
            first=pool.submit(self.call)
            self.assertTrue(entered.wait(5))
            second=pool.submit(self.call).result(5)
            self.assertEqual(second['state'],'UNKNOWN')
            release.set();self.assertEqual(first.result(5)['state'],'COMPLETE')
        self.assertEqual(len(self.observations),1)

    def test_reconcile_observation_is_collection_only_and_never_repeated(self):
        result=self.call('reconcile')
        self.assertEqual(result['state'],'COMPLETE',result)
        self.assertEqual(len(self.observations),1)
        receipt=json.loads((Path(self.fx.destination)/'receipt.json').read_bytes())
        self.assertEqual(receipt['acceptance'],'NOT_RECORDED')
        self.assertEqual(receipt['lease_settlement'],'UNKNOWN')
        self.assertEqual(receipt['controller_state'],'UNKNOWN')
        self.assertFalse(receipt['original_operation_mutated'])
        self.assertEqual(receipt['run_id'],self.run)
        # The same fixed leaf is never read again and never re-published.
        again=self.call('reconcile')
        self.assertEqual(again['state'],'REFUSED')
        self.assertEqual(again['reason'],'original_reconciliation_destination_exists')
        self.assertEqual(again['effect_state'],'NOT_APPLIED')
        self.assertEqual(len(self.observations),1)

    def test_reconcile_refuses_an_existing_leaf_of_any_kind_with_zero_transport(self):
        leaf=Path(self.fx.destination);leaf.mkdir(mode=0o700)
        result=self.call('reconcile')
        self.assertEqual(result['state'],'REFUSED')
        self.assertEqual(result['reason'],'original_reconciliation_destination_exists')
        self.assertEqual(result['effect_state'],'NOT_APPLIED')
        self.assertFalse(self.observations)
        self.assertFalse((leaf/'receipt.json').exists())

    def test_reconcile_refuses_a_missing_parent_chain_with_zero_transport(self):
        shutil.rmtree(Path(self.fx.destination).parent)
        result=self.call('reconcile')
        self.assertEqual(result['state'],'REFUSED')
        self.assertEqual(result['reason'],'original_reconciliation_refused')
        self.assertEqual(result['effect_state'],'NOT_APPLIED')
        self.assertFalse(self.observations)

    def test_reconcile_refuses_a_changed_source_pin_with_zero_transport(self):
        self.fx.packet_pin.write_bytes(self.fx.packet+b'changed')
        result=self.call('reconcile')
        self.assertEqual(result['state'],'REFUSED')
        self.assertFalse(self.observations)
        self.assertFalse(Path(self.fx.destination).exists())

    def test_reconcile_transport_failure_stays_unknown_and_never_reads_again(self):
        def failed(alias,request):
            raise OSError('transport_timeout')
        with mock.patch.object(self.collector.delivery,'transport',failed):
            result=self.call('reconcile')
        self.assertEqual(result['state'],'UNKNOWN')
        self.assertEqual(result['effect_state'],'UNKNOWN')
        self.assertFalse(self.observations)
        # The leaf was reserved before the transport, so the observation is
        # never eligible again and no second read happens.
        self.assertTrue(Path(self.fx.destination).exists())
        again=self.call('reconcile')
        self.assertEqual(again['state'],'REFUSED')
        self.assertEqual(again['reason'],'original_reconciliation_destination_exists')
        self.assertFalse(self.observations)

    def test_reconcile_late_file_exists_never_claims_no_remote_read(self):
        write = self.collector.delivery.write_exclusive
        def late_failure(fd, name, raw):
            if name == 'binding.json':
                raise FileExistsError('late local publication conflict')
            return write(fd, name, raw)
        with mock.patch.object(self.collector.delivery, 'write_exclusive', late_failure):
            result = self.call('reconcile')
        self.assertEqual(len(self.observations), 1)
        self.assertEqual(result['state'], 'UNKNOWN')
        self.assertEqual(result['effect_state'], 'UNKNOWN')
        self.assertTrue(result['this_invocation_remote_read_started'])
        self.assertEqual(self.call('reconcile')['state'], 'REFUSED')
        self.assertEqual(len(self.observations), 1)

    def test_reconcile_disappearing_leaf_after_transport_remains_unknown(self):
        def lost(alias, request):
            self.observe(alias, request)
            shutil.rmtree(self.fx.destination)
            raise OSError('lost transport and local evidence')
        with mock.patch.object(self.collector.delivery, 'transport', lost):
            result = self.call('reconcile')
        self.assertEqual(len(self.observations), 1)
        self.assertFalse(Path(self.fx.destination).exists())
        self.assertEqual(result['state'], 'UNKNOWN')
        self.assertEqual(result['effect_state'], 'UNKNOWN')
        self.assertTrue(result['this_invocation_remote_read_started'])


    def test_reconcile_success_then_lost_final_evidence_remains_unknown(self):
        original_collect = self.collector._collect_validated

        def collect_then_remove(*args, **kwargs):
            value = original_collect(*args, **kwargs)
            shutil.rmtree(self.fx.destination)
            return value

        with mock.patch.object(self.collector, '_collect_validated', collect_then_remove):
            result = self.call('reconcile')
        self.assertEqual(len(self.observations), 1)
        self.assertFalse(Path(self.fx.destination).exists())
        self.assertEqual(result['state'], 'UNKNOWN')
        self.assertEqual(result['effect_state'], 'UNKNOWN')
        self.assertTrue(result['this_invocation_remote_read_started'])
        self.assertFalse(result['retry_authorized'])


class ApplicationCarrierOriginalCollection(ApplicationOriginalCollection):
    RUN = RUNS[1]


if __name__=='__main__': unittest.main()
