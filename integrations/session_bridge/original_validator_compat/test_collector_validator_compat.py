"""Inert version-bound collector tests. No remote read/collect/replay."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch

SOURCE = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else Path(__file__).parent / "proposal"
sys.path.insert(0, str(SOURCE))
import artifact_reader as reader
import artifact_production as future
import artifact_delivery as delivery
import original_delivery_collector as collector
REAL_LOCAL_FILE = delivery.local_file

HERE = Path(__file__).parent
ORIGINAL_PATH = Path('/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering/original-parent-host-selection-20261013/artifact_production.c0f17c3e.before.py')
ORIGINAL_SHA = 'c0f17c3e489c83bdb369d6c1ea9adc2757f4732f515cbc76e230fe154a61f67e'
READER_SHA = 'e2b08b7967df0e4193ba668cf6f72225429138a9361322c42db6ec84150e3469'
RUN, ROOT, PARENT, HOST = 'synthetic-original', 'synthetic-root', 'synthetic-parent', 'synthetic-host'


def digest(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


class VersionBoundCollectorTests(unittest.TestCase):
    def setUp(self):
        self.original = (HERE / 'artifact_production.c0f17c3e.before.py').read_bytes()
        self.reader = (HERE / 'artifact_reader.py').read_bytes()
        self.future = (HERE / 'artifact_production.py').read_bytes()
        self.manifest = {'artifact_production.py': ORIGINAL_SHA, 'artifact_reader.py': READER_SHA,
                         'synthetic-extra.py': digest(b'inert public source')}
        self.support_digest = digest(canonical({'schema': 'remote-support-code.v1', 'files': self.manifest}))
        packet = future.encode_packet('Synthetic no-effect fixture.', root=ROOT, parent=PARENT,
                                      run_id=RUN, names=['proof.txt'], support_digest=self.support_digest).encode()
        self.contract = future.parse_packet(packet.decode())
        state = collector.HERE / 'state/remote_sub'
        self.binding_path = state / 'synthetic-binding.json'
        self.packet_path, self.log_path, self.support_path = state / (RUN + '.packet.fixture'), state / (RUN + '.log'), state / (RUN + '.support.json')
        log = '\n'.join('2026-10-13T00:00Z [remote_sub id=' + RUN + ' host=' + HOST + '] ' + line for line in [
            'LAUNCH stdout=lanes_' + RUN + '.stdout rc_file=ext/lanes_' + RUN + '.rc cwd=~',
            'LAUNCH_ATTEMPT attempt=1', 'SUPPORT_VERSION_READY digest=' + self.support_digest + ' policy=' + '1' * 64,
            'LEASE_OK pool=glm']).encode()
        support = canonical(self.manifest)
        binding = {'schema': collector.BINDING_SCHEMA, 'run_id': RUN, 'root': ROOT, 'parent': PARENT,
                   'host': HOST, 'mode': 'glm', 'requested_model': 'synthetic-model', 'cwd': '~',
                   'artifact_names': ['proof.txt'], 'sources': {
                       name: {'path': str(path), 'sha256': digest(raw)}
                       for name, path, raw in [('packet', self.packet_path, packet), ('log', self.log_path, log), ('support', self.support_path, support)]}}
        self.files = {str(ORIGINAL_PATH): self.original, str(delivery.HERE / 'artifact_reader.py'): self.reader,
                      str(delivery.HERE / 'artifact_production.py'): self.future,
                      str(self.binding_path): canonical(binding), str(self.packet_path): packet,
                      str(self.log_path): log, str(self.support_path): support,
                      str(delivery.HERE / 'hosts.json'): canonical({HOST: {'allowed_modes': ['glm'], 'ssh_alias': 'synthetic-host'}})}
        self.reads = []
        def local(path, limit=1048576):
            key = str(path); self.reads.append(key)
            if key not in self.files: raise FileNotFoundError('synthetic missing fixture')
            raw = self.files[key]
            if len(raw) > limit: raise ValueError('synthetic limit')
            return raw
        self.read_patch = patch.object(delivery, 'local_file', side_effect=local)
        self.read_patch.start(); self.addCleanup(self.read_patch.stop)
        self.family_patch = patch.object(delivery, 'assert_capsule_family', return_value=None)
        self.family_patch.start(); self.addCleanup(self.family_patch.stop)
        self.env_patch = patch.dict(os.environ, {'CODEX_THREAD_ID': ROOT})
        self.env_patch.start(); self.addCleanup(self.env_patch.stop)

    def replace_support(self, manifest):
        self.manifest = manifest
        self.support_digest = digest(canonical({'schema': 'remote-support-code.v1', 'files': manifest}))
        packet = future.encode_packet('Synthetic no-effect fixture.', root=ROOT, parent=PARENT,
            run_id=RUN, names=['proof.txt'], support_digest=self.support_digest).encode()
        self.contract = future.parse_packet(packet.decode())
        self.files[str(self.packet_path)] = packet
        self.files[str(self.support_path)] = canonical(manifest)
        old_log = self.files[str(self.log_path)].decode()
        import re
        self.files[str(self.log_path)] = re.sub(r'SUPPORT_VERSION_READY digest=[a-f0-9]{64}',
            'SUPPORT_VERSION_READY digest=' + self.support_digest, old_log).encode()
        binding = json.loads(self.files[str(self.binding_path)])
        for name in ('packet', 'support', 'log'):
            binding['sources'][name]['sha256'] = digest(self.files[binding['sources'][name]['path']])
        self.files[str(self.binding_path)] = canonical(binding)

    def context(self):
        return delivery.original_validator_context(self.manifest)

    def response(self, wrapper='plain'):
        data = b'Synthetic artifact bytes.'
        manifest = {'schema': future.RESULT_SCHEMA, 'root': ROOT, 'parent': PARENT, 'run_id': RUN, 'host': HOST,
                    'request_sha256': digest(canonical(self.contract)),
                    'files': [{'path': future.paths(self.contract)[0], 'bytes': len(data), 'sha256': digest(data)}]}
        line = future.RESULT_PREFIX + canonical(manifest).decode()
        if wrapper == 'whole': line = '**' + line + '**'
        if wrapper == 'expanded': line = '**' + future.RESULT_PREFIX.rstrip() + '** `' + canonical(manifest).decode() + '`'
        if wrapper == 'duplicate': line += '\n' + line
        stdout = line.encode()
        cleanup = {'identity_verified': True, 'census_proven': True, 'residual_count': 0, 'status': 'not_needed', 'error_code': None}
        for stem in ('stdin_delivery', 'stdout_capture', 'stderr_capture'):
            cleanup[stem + '_complete'] = True; cleanup[stem + '_error'] = None
        process = {'schema': 'mastermind.local_owned_process_receipt.v1', 'label': RUN, 'returncode': 0,
                   'timed_out': False, 'pid': 123, 'pgid': 123, 'stdout_bytes': len(stdout), 'stderr_bytes': 0,
                   'stdout_truncated': False, 'stderr_truncated': False, 'runtime_failure_code': None,
                   'started_at': '2026-10-13T00:00:00Z', 'ended_at': '2026-10-13T00:00:01Z', 'cleanup': cleanup,
                   'artifact_production': {'schema': 'mastermind.fabric_artifact_completion.v1', 'mode': 'glm',
                                           'contract': self.contract, 'manifest': manifest, 'stdout_sha256': digest(stdout)}}
        request = {'schema': collector.SCHEMA, 'root': ROOT, 'parent': PARENT, 'run_id': RUN, 'host': HOST, 'contract': self.contract}
        def blob(raw): return {'bytes': len(raw), 'sha256': digest(raw), 'data_base64': base64.b64encode(raw).decode()}
        row = {'schema': collector.SCHEMA, 'request_sha256': digest(canonical(request)), 'state': 'READ',
               'files': {'rc': blob(b'0\n'), 'stdout': blob(stdout), 'process': blob(canonical(process))},
               'artifacts': [{**manifest['files'][0], 'status': 'RETRIEVED', 'data_base64': base64.b64encode(data).decode(),
                              'observed_file': {'device': 1, 'inode': 2, 'mtime_ns': 3, 'uid': 1000, 'mode': 384}}]}
        return request, stdout, canonical(process), canonical(row), manifest

    def write_artifact_v2_log(self, events, suffix=b"", *, truncate=False):
        raw = "".join(
            f"2026-10-13T00:00Z [remote_sub id={RUN} host={HOST}] {event}\n"
            for event in events).encode() + suffix
        if truncate:
            raw = raw[:-1]
        self.files[str(self.log_path)] = raw
        outer = json.loads(self.files[str(self.binding_path)])
        outer["sources"]["log"]["sha256"] = digest(raw)
        self.files[str(self.binding_path)] = canonical(outer)

    def artifact_v2_fixture(self, acquisition_pool="glm-frontier"):
        manifest = dict(self.manifest)
        manifest["artifact_production.py"] = digest(self.future)
        self.replace_support(manifest)
        outer = json.loads(self.files[str(self.binding_path)])
        outer["requested_model"] = "glm-5.3"
        self.files[str(self.binding_path)] = canonical(outer)
        lease_id, account = "a" * 12, "account-one"
        acquired = f"LEASE={lease_id} ACCOUNT={account}\n".encode("ascii")
        record = {
            "schema": "mastermind.fabric_launch_binding.v2",
            "run_id": RUN, "root": ROOT, "parent": PARENT, "host": HOST,
            "mode": "glm", "requested_model": "glm-5.3",
            "pool": "glm", "acquisition_pool": acquisition_pool,
            "lease_id": lease_id, "account": account,
            "packet_sha256": digest(self.files[str(self.packet_path)]),
            "support_digest": self.support_digest,
            "acquire_response_sha256": digest(acquired),
            "source": "controller_original_acquire_return", "phase": "PRE_LAUNCH",
        }
        events = [
            "RUN_RESERVED explicit=1", "LEASE_OK pool=" + acquisition_pool,
            "SUPPORT_VERSION_READY digest=" + self.support_digest + " policy=" + "1" * 64,
            "LAUNCH_BINDING " + canonical(record).decode(),
            f"LAUNCH stdout=lanes_{RUN}.stdout rc_file=ext/lanes_{RUN}.rc cwd=~",
            "LAUNCH_ATTEMPT attempt=1",
        ]
        self.write_artifact_v2_log(events)
        return record, events

    def test_artifact_v2_frontier_and_fallback_load_binding(self):
        for acquisition_pool in ("glm-frontier", "glm"):
            with self.subTest(acquisition_pool=acquisition_pool):
                self.artifact_v2_fixture(acquisition_pool)
                loaded = collector.load_binding(
                    self.binding_path, run_id=RUN, root=ROOT, parent=PARENT)
                self.assertEqual(loaded[3], self.contract)
                self.assertIsNone(loaded[6])
                request, _, _, response, _ = self.response()
                collector.validate_response(
                    response, request, "glm", original_validator=loaded[6])

    def test_artifact_v2_rejects_repinned_semantic_and_sequence_faults(self):
        # Malformed v2 must not fall back through an otherwise ordinary tag.
        record, events = self.artifact_v2_fixture("glm")
        collector.load_binding(self.binding_path, run_id=RUN, root=ROOT, parent=PARENT)
        baseline_files = dict(self.files)
        changes = {
            "root": {"root": "foreign-root"}, "parent": {"parent": "foreign-parent"},
            "host": {"host": "foreign-host"}, "mode": {"mode": "qwen"},
            "model": {"requested_model": "glm-5.3-flash"},
            "logical_pool": {"pool": "glm-frontier"},
            "acquisition_pool": {"acquisition_pool": "bailian"},
            "packet": {"packet_sha256": "e" * 64},
            "support": {"support_digest": "e" * 64},
            "acquire_digest": {"acquire_response_sha256": "e" * 64},
            "account": {"account": "different-account"}, "lease": {"lease_id": "d" * 12},
            "unknown_schema": {"schema": "mastermind.fabric_launch_binding.v9"},
            "downgrade_with_tag": {"schema": "mastermind.fabric_launch_binding.v1"},
            "extra_field": {"unexpected": "field"},
        }
        faults = list(changes) + [
            "missing_tag", "duplicate_key", "wrong_order", "duplicate_binding",
            "wrong_lease_event", "foreign_line", "truncated", "prelaunch_failure",
            "postlaunch_binding",
        ]
        for fault in faults:
            with self.subTest(fault=fault):
                self.files = dict(baseline_files)
                changed = dict(record)
                changed.update(changes.get(fault, {}))
                if fault == "missing_tag":
                    del changed["acquisition_pool"]
                payload = canonical(changed).decode()
                if fault == "duplicate_key":
                    payload = payload[:-1] + ',"acquisition_pool":"glm"}'
                changed_events = list(events)
                changed_events[3] = "LAUNCH_BINDING " + payload
                if fault == "wrong_order":
                    changed_events[1], changed_events[2] = changed_events[2], changed_events[1]
                elif fault == "duplicate_binding":
                    changed_events.insert(3, changed_events[3])
                elif fault == "wrong_lease_event":
                    changed_events[1] = "LEASE_OK pool=glm-frontier"
                elif fault == "prelaunch_failure":
                    changed_events.insert(3, "TRANSPORT_FAILED rc=78")
                elif fault == "postlaunch_binding":
                    changed_events.append(changed_events.pop(3))
                self.write_artifact_v2_log(changed_events,
                    suffix=b"foreign diagnostic\n" if fault == "foreign_line" else b"",
                    truncate=fault == "truncated")
                with patch.object(delivery, "transport") as transport, \
                     patch.object(delivery, "reserve_destination") as reserve:
                    with self.assertRaises(ValueError):
                        collector.collect(self.binding_path, run_id=RUN, root=ROOT,
                            parent=PARENT, destination=HERE / "NEVER_CREATED")
                    transport.assert_not_called()
                    reserve.assert_not_called()

    def test_historical_binding_qualifies_using_exact_original_source(self):
        loaded = collector.load_binding(self.binding_path, run_id=RUN, root=ROOT, parent=PARENT)
        self.assertEqual(loaded[3], self.contract)
        self.assertIsNotNone(loaded[6])
        self.assertIn(str(ORIGINAL_PATH), self.reads)

    def test_historical_plain_and_wholeline_manifest_succeed(self):
        context = self.context()
        for wrapper in ('plain', 'whole'):
            request, stdout, process, response, manifest = self.response(wrapper)
            with self.subTest(wrapper=wrapper):
                self.assertEqual(delivery.validate_ordinary_producer(request, stdout, process, original_validator=context), manifest)
                blobs, artifacts, found = collector.validate_response(response, request, 'glm', original_validator=context)
                self.assertEqual(found, manifest); self.assertEqual(artifacts[0][1], b'Synthetic artifact bytes.')

    def test_expanded_wrapper_rejected_historically_but_future_unchanged_accepts(self):
        request, stdout, process, response, manifest = self.response('expanded')
        self.assertEqual(delivery.validate_ordinary_producer(request, stdout, process), manifest)
        with self.assertRaises(ValueError):
            delivery.validate_ordinary_producer(request, stdout, process, original_validator=self.context())
        with self.assertRaises(ValueError):
            collector.validate_response(response, request, 'glm', original_validator=self.context())

    def test_duplicate_manifest_is_rejected_by_both(self):
        request, stdout, process, response, _ = self.response('duplicate')
        for context in (None, self.context()):
            with self.subTest(historical=context is not None), self.assertRaises(ValueError):
                delivery.validate_ordinary_producer(request, stdout, process, original_validator=context)

    def test_missing_or_altered_original_or_reader_refuses_before_transport(self):
        for path in (str(ORIGINAL_PATH), str(delivery.HERE / 'artifact_reader.py')):
            for mutation in ('missing', 'altered'):
                original = self.files[path]
                if mutation == 'missing': self.files.pop(path)
                else: self.files[path] = original + b'\n# changed\n'
                with self.subTest(path=path, mutation=mutation), patch.object(delivery, 'transport') as tripwire:
                    with self.assertRaises((ValueError, OSError)):
                        collector.collect(self.binding_path, run_id=RUN, root=ROOT, parent=PARENT,
                                          destination=HERE / 'NEVER_CREATED')
                    tripwire.assert_not_called()
                self.files[path] = original
        self.assertFalse((HERE / 'NEVER_CREATED').exists())

    def test_context_rechecks_original_and_reader_after_construction(self):
        context = self.context()
        request, stdout, process, _, _ = self.response()
        for path in (str(ORIGINAL_PATH), str(delivery.HERE / 'artifact_reader.py')):
            original = self.files[path]; self.files[path] = original + b'\n'
            with self.subTest(path=path), self.assertRaises(ValueError):
                delivery.validate_ordinary_producer(request, stdout, process, original_validator=context)
            self.files[path] = original

    def test_root_parent_and_support_scope_mismatch_refused(self):
        context = self.context()
        request, stdout, process, _, _ = self.response()
        for key in ('root', 'parent'):
            changed = dict(request); changed[key] = 'other'
            with self.subTest(key=key), self.assertRaises(ValueError):
                delivery.validate_ordinary_producer(changed, stdout, process, original_validator=context)
        obj = json.loads(process); obj['artifact_production']['contract']['support_digest'] = 'f' * 64
        with self.assertRaises(ValueError):
            delivery.validate_ordinary_producer(request, stdout, canonical(obj), original_validator=context)

    def test_no_caller_module_or_unknown_validator_hash(self):
        request, stdout, process, _, _ = self.response()
        with self.assertRaises(ValueError):
            delivery.validate_ordinary_producer(request, stdout, process, original_validator=future)
        manifest = dict(self.manifest); manifest['artifact_production.py'] = 'f' * 64
        with self.assertRaises(ValueError): delivery.original_validator_context(manifest)


    def test_current_binding_keeps_default_validator_and_expanded_grammar(self):
        manifest = dict(self.manifest); manifest['artifact_production.py'] = digest(self.future)
        self.replace_support(manifest)
        loaded = collector.load_binding(self.binding_path, run_id=RUN, root=ROOT, parent=PARENT)
        self.assertIsNone(loaded[6])
        self.assertNotIn(str(ORIGINAL_PATH), self.reads)
        request, stdout, process, response, expected = self.response('expanded')
        self.assertEqual(delivery.validate_ordinary_producer(request, stdout, process), expected)
        self.assertEqual(collector.validate_response(response, request, 'glm')[2], expected)

    def test_current_producer_drift_refuses_before_transport(self):
        manifest = dict(self.manifest); manifest['artifact_production.py'] = digest(self.future)
        self.replace_support(manifest)
        self.files[str(delivery.HERE / 'artifact_production.py')] += b'\n'
        with patch.object(delivery, 'transport') as tripwire, self.assertRaises(ValueError):
            collector.collect(self.binding_path, run_id=RUN, root=ROOT, parent=PARENT,
                destination=HERE / 'NEVER_CREATED')
        tripwire.assert_not_called()

    def test_historical_scope_remains_independent_of_future_producer_bytes(self):
        self.files[str(delivery.HERE / 'artifact_production.py')] += b'\n# unrelated future change\n'
        loaded = collector.load_binding(self.binding_path, run_id=RUN, root=ROOT, parent=PARENT)
        request, _, _, response, expected = self.response()
        self.assertEqual(collector.validate_response(response, request, 'glm',
            original_validator=loaded[6])[2], expected)

    def test_context_immutable_and_no_mutation_of_installed_module(self):
        before = dict(vars(future))
        context = self.context()
        with self.assertRaises(AttributeError): context._support_digest = 'f' * 64
        with self.assertRaises(AttributeError): context.caller_module = future
        context.parse_packet(self.files[str(self.packet_path)].decode())
        request, stdout, process, _, expected = self.response('whole')
        self.assertEqual(delivery.validate_ordinary_producer(request, stdout, process,
            original_validator=context), expected)
        self.assertEqual(before, vars(future))

    def test_invalid_binding_support_refuses_before_transport(self):
        for value in ({}, [], {'artifact_production.py': 'wrong'},
                      {**self.manifest, 'artifact_reader.py': 'f' * 64}):
            original = self.files[str(self.support_path)]
            self.files[str(self.support_path)] = canonical(value)
            binding = json.loads(self.files[str(self.binding_path)])
            binding['sources']['support']['sha256'] = digest(self.files[str(self.support_path)])
            old_binding = self.files[str(self.binding_path)]
            self.files[str(self.binding_path)] = canonical(binding)
            with self.subTest(value=value), patch.object(delivery, 'transport') as tripwire:
                with self.assertRaises(ValueError):
                    collector.collect(self.binding_path, run_id=RUN, root=ROOT, parent=PARENT,
                        destination=HERE / 'NEVER_CREATED')
                tripwire.assert_not_called()
            self.files[str(self.support_path)] = original
            self.files[str(self.binding_path)] = old_binding

    def test_extra_support_file_change_invalidates_context(self):
        context = self.context()
        changed = dict(self.manifest); changed['synthetic-extra.py'] = 'f' * 64
        self.replace_support(changed)
        with self.assertRaises(ValueError):
            context.parse_packet(self.files[str(self.packet_path)].decode())

    def test_collector_keeps_completion_mode_and_contract_equality_fences(self):
        context = self.context()
        request, _, _, response, _ = self.response()
        for key, value in (('mode', 'qwen'), ('contract', {**self.contract, 'body_sha256': 'f' * 64})):
            row = json.loads(response)
            process = json.loads(base64.b64decode(row['files']['process']['data_base64']))
            process['artifact_production'][key] = value
            if key == 'contract':
                contract_hash = digest(canonical(value))
                # A valid replacement manifest still must equal the request's contract.
                manifest = process['artifact_production']['manifest']
                manifest['request_sha256'] = contract_hash
                stdout = (future.RESULT_PREFIX + canonical(manifest).decode()).encode()
                process['stdout_bytes'] = len(stdout)
                process['stdout_sha256'] = digest(stdout)
                process['artifact_production']['stdout_sha256'] = digest(stdout)
                row['files']['stdout'] = {'bytes': len(stdout), 'sha256': digest(stdout),
                    'data_base64': base64.b64encode(stdout).decode()}
            raw = canonical(process)
            row['files']['process'] = {'bytes': len(raw), 'sha256': digest(raw),
                'data_base64': base64.b64encode(raw).decode()}
            with self.subTest(key=key), self.assertRaises(ValueError):
                collector.validate_response(canonical(row), request, 'glm', original_validator=context)


    def test_secure_local_read_rejects_symlink_and_writable_original_before_transport(self):
        # The real custody reader requires private physical ancestry; the
        # repository mount may legitimately be group-writable.
        base = os.environ.get('NATIVE_ROLLOUT_TEST_ROOT', str(Path.home()))
        with tempfile.TemporaryDirectory(prefix='validator-inert-', dir=base) as folder:
            root = Path(folder)
            original = root / 'original.py'; original.write_bytes(self.original); original.chmod(0o600)
            unchanged_reader = root / 'reader.py'; unchanged_reader.write_bytes(self.reader); unchanged_reader.chmod(0o600)
            def secure_local(path, limit=1048576):
                if str(path) == str(ORIGINAL_PATH): return REAL_LOCAL_FILE(original, limit)
                if str(path) == str(delivery.HERE / 'artifact_reader.py'): return REAL_LOCAL_FILE(unchanged_reader, limit)
                return self.files[str(path)]
            with patch.object(delivery, 'local_file', side_effect=secure_local):
                self.assertIsNotNone(self.context())
                original.chmod(0o602)
                with patch.object(delivery, 'transport') as tripwire, self.assertRaises(ValueError):
                    collector.collect(self.binding_path, run_id=RUN, root=ROOT, parent=PARENT,
                        destination=HERE / 'NEVER_CREATED')
                tripwire.assert_not_called()
                original.chmod(0o600)
                target = root / 'target.py'; original.rename(target); original.symlink_to(target.name)
                with patch.object(delivery, 'transport') as tripwire, \
                     self.assertRaises(collector.LocalBindingRefused) as refused:
                    collector.collect(self.binding_path, run_id=RUN, root=ROOT, parent=PARENT,
                        destination=HERE / 'NEVER_CREATED')
                self.assertIsInstance(refused.exception.__cause__, OSError)
                tripwire.assert_not_called()
                original.unlink(); target.rename(original)
                unchanged_reader.chmod(0o602)
                with self.assertRaises(ValueError): self.context()
        self.assertFalse(root.exists())


if __name__ == '__main__': unittest.main()
