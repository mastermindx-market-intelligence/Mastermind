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
_loopback_network = None
_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
_private = tuple(str(_home / name) for name in
                 ('.glm', '.bailian', '.minimax', '.qwen', '.claude/projects',
                  '.codex/auth.json', '.claude/.credentials.json'))


class FixtureBoundaryError(AssertionError):
    pass


def _allowed_loopback_event(event, args):
    """Only the two registered, numeric-loopback HTTP fixture endpoints."""
    scope = _loopback_network
    if scope is None:
        return False
    if event == 'socket.__new__':
        return (len(args) == 4 and args[1] == socket.AF_INET
                and args[2] == socket.SOCK_STREAM and args[3] in (0, socket.IPPROTO_TCP))
    if event in ('socket.bind', 'socket.connect'):
        sock, address = args
        return (sock.family == socket.AF_INET and sock.type == socket.SOCK_STREAM
                and isinstance(address, tuple) and len(address) == 2
                and address[0] == '127.0.0.1' and type(address[1]) is int
                and (address[1] == 0 if event == 'socket.bind'
                     else address[1] in scope['ports']))
    if event == 'socket.getaddrinfo':
        host, port, family, kind, protocol = args
        return (host == '127.0.0.1' and type(port) is int and port in scope['ports']
                and family in (0, socket.AF_INET) and kind in (0, socket.SOCK_STREAM)
                and protocol in (0, socket.IPPROTO_TCP))
    if event == 'urllib.Request':
        return len(args) == 4 and args[0] in scope['post_urls'] and args[3] == 'POST'
    return False


@contextlib.contextmanager
def numeric_loopback_network():
    """Opt in after installation; process and private-owner guards stay active."""
    global _loopback_network
    assert _active and _loopback_network is None
    scope = {'ports': set(), 'post_urls': set()}
    _loopback_network = scope
    try:
        yield scope
    finally:
        _loopback_network = None


def _audit(event, args):
    if not _active:
        return
    kind = None
    if event.startswith('socket.') or event == 'urllib.Request':
        if _allowed_loopback_event(event, args):
            return
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


APPLICATION_PREIMAGES = {
    # Retained f7 candidate bytes keep both historical95/102 transitions exact.
    'ext/quota_circuit.py': ('rollout/preimages/quota_circuit_b119865.py', 28768,
        '0962d638a0a5655a71ea7a6eeb83088ad60af30f4a26e9c5bc47a92c3ab77945'),
    'ext/lease_broker.py': ('rollout/preimages/lease_broker_f1059fe.py', 73321,
        'a2847a29abe590cb168c2cd8ae34e0b1c3222b6e92ab4c00f252a342d56e6406'),
    'ext/go_lease_capability.py': ('source/go_lease_capability.py', 9456,
        '9f350698ba94d64fedc3f64ebffce993840d7ee3376b46254756d58bdb78c66a'),
    'ext/go_lease_gateway.py': ('source/go_lease_gateway.py', 4513,
        '7b1e1d48933218135771c770a1d25c994aa0332bc6bc8461c5b9d625ef8a7658'),
}


def verify_current_stage(output):
    """Qualify the current107 build before restoring any historical bytes."""
    native = Path(builder.__file__).parent.parent
    manifest_raw = (output / 'native-manifest.json').read_bytes()
    inventory_raw = (output / 'native-source-inventory.json').read_bytes()
    baseline_raw = (native / 'rollout/native-manifest.json').read_bytes()
    baseline_inventory_raw = (native / 'rollout/native-source-inventory.json').read_bytes()
    manifest = json.loads(manifest_raw)
    inventory = json.loads(inventory_raw)
    if (manifest_raw != baseline_raw or inventory_raw != baseline_inventory_raw
            or len(manifest) != 107
            or set(manifest) != {'ext/' + name for name in builder.BASE_FILES | builder.ADDITIONS} | {'pool'}
            or set(inventory['files']) != set(manifest)
            or inventory['native_code_files'] != len(manifest)):
        raise AssertionError('current application source closure differs')
    for name, wanted in manifest.items():
        data = (output / 'native-code-stage' / name).read_bytes()
        row = inventory['files'][name]
        source = (native / row['source']).read_bytes()
        if (g.digest(data) != wanted or row['sha256'] != wanted
                or row['bytes'] != len(data) or source != data):
            raise AssertionError('current captured source differs: ' + name)
        if name in APPLICATION_PREIMAGES:
            candidate = 'candidate/' + name.split('/')[1]
            if row['source'] != candidate or (native / candidate).read_bytes() != data:
                raise AssertionError('current application candidate differs: ' + name)
    return manifest


def restore_application_preimages(stage, manifest):
    native = Path(builder.__file__).parent.parent
    for name, (relative, size, expected) in APPLICATION_PREIMAGES.items():
        raw = (native / relative).read_bytes()
        if len(raw) != size or g.digest(raw) != expected or manifest[name] != expected:
            raise AssertionError('historical application preimage differs: ' + name)
        (stage / name).write_bytes(raw)


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
            cls.manifest = verify_current_stage(cls.built)
            # Rebuild the original finite paired epoch, never relabel the
            # current H1/daemon generation as the historical95 target. The
            # snapshot contains only changed public code plus its whole95 map.
            import base64, zlib
            fixture = Path(__file__).resolve().parents[4] / 'tests/fixtures/native-paired-historical95-6ac208.json'
            raw = fixture.read_bytes()
            if g.digest(raw) != '98e532bd0dd819d94988fe61475e40b36b40676f5e561c38d6198e4b196d72d6':
                raise AssertionError('historical95 fixture bytes changed')
            retained = json.loads(raw)
            old = retained['manifest']
            removed = set(retained['removed_current_members']) | {
                'ext/post_failure_observation.py', 'ext/post_failure_observation_delivery.py',
                'ext/participant_binding.py', 'ext/fabric_participant_owner.py',
                'ext/original_advertised_artifact.py'}
            if (retained['schema'] != 'mastermind.test_native_paired_historical95/v1'
                    or set(cls.manifest) - set(old) != removed or set(old) - set(cls.manifest)
                    or len(old) != 95 or retained['historical_manifest_sha256'] != installer.UPGRADE_MANIFEST):
                raise AssertionError('historical95 fixture namespace differs')
            for name in removed:
                target = cls.built / 'native-code-stage' / name
                if g.digest(target.read_bytes()) != cls.manifest[name]:
                    raise AssertionError('current source differs before historical inverse')
                target.unlink()
            for name,item in retained['files'].items():
                if name not in old or item['sha256'] != old[name]:
                    raise AssertionError('historical95 payload not in fixed manifest')
                payload = zlib.decompress(base64.b64decode(item['zlib_base64'],validate=True))
                if g.digest(payload) != old[name]:
                    raise AssertionError('historical95 payload differs')
                (cls.built / 'native-code-stage' / name).write_bytes(payload)
            # The held-executor YAML repair changes a member which the
            # original inverse did not need to retain. Restore its exact
            # historical public bytes without changing the retained95 map.
            yaml_preimage = fixture.with_name('paid-yaml-root-pre-held-5cba.py.txt').read_bytes()
            if g.digest(yaml_preimage) != 'ea16d60373ccb50a93d85ed3f1557aad765174b7ddef81fb65622648b0c02f07' or old['ext/paid_yaml_runtime.py'] != g.digest(yaml_preimage):
                raise AssertionError('historical YAML loader preimage differs')
            (cls.built / 'native-code-stage/ext/paid_yaml_runtime.py').write_bytes(yaml_preimage)
            # The catalog reader overlays a new pool ledger in candidate/.
            # This finite historical95 target retains the original source
            # preimage, never the current namespace-bound reader bytes.
            pool_preimage = (Path(builder.__file__).parent.parent / 'source/pool_ledger.py').read_bytes()
            if g.digest(pool_preimage) != '85d40296487f1f040ef3597b8110966e36a9b6ebee781e05a5e6172b8610d78e' or old['ext/pool_ledger.py'] != g.digest(pool_preimage):
                raise AssertionError('historical pool ledger preimage differs')
            (cls.built / 'native-code-stage/ext/pool_ledger.py').write_bytes(pool_preimage)
            # Ubuntu4 changes current first-worker policy. Restore its exact
            # protected predecessor; never repin the immutable95 target.
            qualification_raw = fixture.with_name('ubuntu4-grok-qualification-predecessor-f374289e.json').read_bytes()
            if g.digest(qualification_raw) != '93f5285a758f1045be1f178f35d17e792459f167d2d631ff2914778253b64ebb':
                raise AssertionError('qualification predecessor fixture changed')
            qualification = json.loads(qualification_raw)
            if (qualification['schema'] != 'fabric.ubuntu4-qualification-predecessor.v1'
                    or qualification['commit'] != 'f374289eb74587eaa755f5bc8e5a3252d00850e0'
                    or qualification['blob'] != 'f72b12eac939143b1b2ed298139d55b06667a2c2'
                    or qualification['path'] != 'ops/native_fabric/quota_continuity/candidate/fabric_host_qualification.py'):
                raise AssertionError('qualification predecessor scope differs')
            qualification_payload = zlib.decompress(base64.b64decode(qualification['zlib_base64'], validate=True))
            if (len(qualification_payload) != qualification['bytes']
                    or g.digest(qualification_payload) != qualification['sha256']
                    or qualification['sha256'] != old['ext/fabric_host_qualification.py']):
                raise AssertionError('historical95 qualification predecessor differs')
            (cls.built / 'native-code-stage/ext/fabric_host_qualification.py').write_bytes(qualification_payload)
            # S7 changed two members that the authentic historical95 inverse
            # previously left untouched. Restore their exact protected bytes;
            # never repin the immutable95 manifest or its paired-upgrade owner.
            diagnostic_raw = fixture.with_name('native-diagnostic-predecessors-e5f49cf4.json').read_bytes()
            if g.digest(diagnostic_raw) != 'fcc3ab7de9a8f517ca59d94cf745c1d894fc14478f399e7d18f198f0679233df':
                raise AssertionError('diagnostic predecessor fixture changed')
            diagnostic = json.loads(diagnostic_raw)
            if (diagnostic['schema'] != 'mastermind.test_native_diagnostic_predecessors/v1'
                    or diagnostic['source_commit'] != 'e5f49cf4dbe8d06382c1d6f32368e9e9fb51c63d'
                    or set(diagnostic['files']) != {'ext/original_delivery_collector.py',
                        'ext/provider_outcome.py', 'ext/remote_sub.sh'}):
                raise AssertionError('diagnostic predecessor scope differs')
            for name in ('ext/original_delivery_collector.py','ext/provider_outcome.py'):
                item=diagnostic['files'][name]
                payload=zlib.decompress(base64.b64decode(item['zlib_base64'],validate=True))
                if len(payload)!=item['bytes'] or g.digest(payload)!=item['sha256'] or item['sha256']!=old[name]:
                    raise AssertionError('historical95 diagnostic preimage differs')
                (cls.built/'native-code-stage'/name).write_bytes(payload)
            # PR2097 changed precisely these two original95 members. Restore
            # authentic protected candidate bytes only in the disposable owner;
            # source/ preimages are a different generation and are not valid.
            observer_raw = fixture.with_name('native-observer-historical95-48ca.json').read_bytes()
            if g.digest(observer_raw) != '0dd81a279641b9c456ef94439d519d97f7670ec18831f5bd78f69bcdd710b3b2':
                raise AssertionError('historical observer fixture changed')
            observer = json.loads(observer_raw)
            if (observer['schema'] != 'mastermind.test_native_observer_historical95/v1'
                    or observer['source_commit'] != '48ca51f882338c58e377a0acf16931066c703384'
                    or set(observer['files']) != {'ext/run_observation.py', 'ext/run_observation_delivery.py'}):
                raise AssertionError('historical observer fixture scope differs')
            for name,item in observer['files'].items():
                payload = zlib.decompress(base64.b64decode(item['zlib_base64'],validate=True))
                if len(payload) != item['bytes'] or g.digest(payload) != item['sha256'] or item['sha256'] != old[name]:
                    raise AssertionError('historical95 observer preimage differs')
                (cls.built/'native-code-stage'/name).write_bytes(payload)
            # Pinned finite long-horizon forward deltas are not historical95
            # bytes. Restore ONLY these named changed members inside this
            # disposable historical fixture; retain original SHA checks.
            native_root = Path(builder.__file__).parent.parent
            baseline_sources = {
                'ext/artifact_delivery.py': native_root.parent / 'grok47/overlay/artifact_delivery.py',
                'ext/fabric_operator_contract.py': native_root.parent / 'grok47/overlay/fabric_operator_contract.py',
                'ext/native_remote.py': native_root.parent / 'grok47/overlay/native_remote.py',
                'ext/sub.sh': native_root.parent / 'grok47/overlay/sub.sh',
                'ext/oc_free_exec.sh': native_root / 'source/oc_free_exec.sh',
                'ext/fabric_operator_owner.py': native_root / 'source/fabric_operator_owner.py',
                # Protected899ac broker blob b39e1fbcebe88513ee9c1dd756c56a9c68ff72b1.
                # Historical95 retains its pinned bytes; CURRENT fair-share stays unchanged.
                'ext/lease_broker.py': fixture.with_name('native-lease-broker-pre-fair-share-899ac3a9.py.txt'),
                # Protected49c2 predecessor, retained as data after the held
                # process qualifier changed CURRENT. Never relabel old95.
                'ext/linux_process_identity.py': (
                    fixture.parent / 'native_historical_payloads/linux_process_identity.py.txt'),
            }
            for name, predecessor in baseline_sources.items():
                original = predecessor.read_bytes()
                if g.digest(original) != old[name]:
                    raise AssertionError('long-horizon historical predecessor differs: '+name)
                (cls.built/'native-code-stage'/name).write_bytes(original)
            # A new polling helper delta cannot be inverted into historical95.
            # Restore its already retained, independently hash-bound preimage.
            long_raw = fixture.with_name('native-long-horizon-predecessors-20261103.json').read_bytes()
            if g.digest(long_raw) != 'bb924475a501aa732ca0c5b1f05f9428c100c546bcbfb5d3e0c2ceaf268d6f19':
                raise AssertionError('long-horizon predecessor fixture changed')
            long_fixture = json.loads(long_raw)
            if (long_fixture['schema'] != 'mastermind.test_native_long_horizon_predecessors102/v1'
                    or long_fixture['source_commit'] != '9f65957e29eba92245d78609f032aaea523b7cb4'
                    or set(long_fixture['files']) != {'ext/commission_deadline.py',
                        'ext/fabric_continuation.py', 'ext/remote_sub_exec.py',
                        'ext/remote_sub_helpers.py', 'ext/slot.py'}):
                raise AssertionError('long-horizon predecessor scope differs')
            helper_name = 'ext/remote_sub_helpers.py'
            helper_item = long_fixture['files'][helper_name]
            helper_payload = zlib.decompress(base64.b64decode(helper_item['zlib_base64'], validate=True))
            if (len(helper_payload) != helper_item['bytes']
                    or g.digest(helper_payload) != helper_item['sha256']
                    or helper_item['sha256'] != old[helper_name]):
                raise AssertionError('historical95 polling helper preimage differs')
            (cls.built / 'native-code-stage' / helper_name).write_bytes(helper_payload)
            inverse = {
                'ext/commission_deadline.py': [
                    ('not 0 <= result <= 14400', 'not 0 <= result <= 7200'),
                ],
                'ext/fabric_continuation.py': [
                    ('if not 1 <= budget <= 14400:', 'if not 1 <= budget <= 7200:'),
                    ('floor = 14400 if kwargs.get("task_complexity") == "C3_FRONTIER_JUDGMENT" else (\n'
                     '        7200 if kwargs.get("task_complexity") == "C2_COMPLEX_BOUNDED" else (\n'
                     '        3600 if kwargs.get("task_complexity") in (None, "") else 0))',
                     'floor = 7200 if kwargs.get("task_complexity") == "C3_FRONTIER_JUDGMENT" else (\n'
                     '        3600 if kwargs.get("task_complexity") in (None, "", "C2_COMPLEX_BOUNDED") else 0)'),
                ],
                'ext/slot.py': [
                    ('MAX_CHILD_TIMEOUT_S = 14400.0', 'MAX_CHILD_TIMEOUT_S = 7200.0'),
                    ('not 0.01 <= result.ttl <= 15000', 'not 0.01 <= result.ttl <= 7500'),
                    ('14400s deadline plus 300s settlement allowance', '7200s deadline plus 300s settlement allowance'),
                    ('not 0.01 <= ttl <= 15000', 'not 0.01 <= ttl <= 7500'),
                    ('not 0.01 <= LEASE_TTL_S <= 15000', 'not 0.01 <= LEASE_TTL_S <= 7500'),
                ],
            }
            for name, changes in inverse.items():
                target = cls.built/'native-code-stage'/name
                raw = target.read_bytes()
                for newest, previous in changes:
                    newer, older = newest.encode(), previous.encode()
                    if raw.count(newer) != 1:
                        raise AssertionError('long-horizon inverse changed shape: '+name)
                    raw = raw.replace(newer, older, 1)
                if g.digest(raw) != old[name]:
                    raise AssertionError('long-horizon historical inverse unqualified: '+name)
                target.write_bytes(raw)
            restore_application_preimages(cls.built / 'native-code-stage', old)
            # A new current-generation census implementation must never be
            # relabeled as the immutable historical paired-upgrade payload.
            # Restore the exact old lane runtime from a byte-pinned fixture.
            historic_path = (Path(__file__).resolve().parents[4] /
                'tests/fixtures/native-historical-lane-runtime-61350902.json')
            historic_raw = historic_path.read_bytes()
            if g.digest(historic_raw) != '1d658364949b3089ecb35b1ca6f3f8ac79970de1ab44dcc17dd6198a1f1eb3c0':
                raise AssertionError('historical lane runtime fixture changed')
            historic = json.loads(historic_raw)
            original_runtime = zlib.decompress(
                base64.b64decode(historic['zlib_base64'], validate=True)
            )
            if (historic['schema'] != 'mastermind.native_historical_lane_runtime.v1'
                    or historic['original_sha256'] != old['ext/lane_runtime.py']
                    or historic['original_bytes'] != len(original_runtime)
                    or g.digest(original_runtime) != old['ext/lane_runtime.py']):
                raise AssertionError('historical lane runtime preimage unqualified')
            (cls.built / 'native-code-stage/ext/lane_runtime.py').write_bytes(
                original_runtime
            )
            cls.manifest = old
            for name,wanted in cls.manifest.items():
                if g.digest((cls.built / 'native-code-stage' / name).read_bytes()) != wanted:
                    raise AssertionError('historical95 full payload differs: '+name)
            historical_manifest = (json.dumps(cls.manifest,sort_keys=True,indent=2)+'\n').encode()
            if g.digest(historical_manifest) != installer.UPGRADE_MANIFEST:
                raise AssertionError('historical paired-upgrade manifest differs')
        finally:
            _active = False

    @classmethod
    def tearDownClass(cls):
        _cleanup(cls.shared)

    @staticmethod
    def _reset_fixture_audit():
        global _active
        _active = False

    def setUp(self):
        global _active, g
        _active = True
        # Unittest invokes addCleanup even when setUp raises. Keep the global
        # audit sentinel and throwaway fixture from poisoning later test packs.
        self.addCleanup(self._reset_fixture_audit)
        self.temp = tempfile.TemporaryDirectory(prefix='paired-upgrade-')
        self.addCleanup(_cleanup, self.temp)
        self.root = Path(self.temp.name).resolve()
        # Current ordinary publisher admits one new template; this suite
        # remains exactly the historical 8bc -> d044 transition. Restore only
        # that closed three-line addition in a disposable module, not a pin.
        original_g = g
        epoch_raw = installer._HISTORICAL_LAUNCHER.read_bytes()
        added = (b'    # One vetted flat plist. Not a suffix rule and not a directory walk.\n'
                 b'    if relative == "ext/host_pull_launchd.plist.template":\n'
                 b'        return\n')
        if g.digest(epoch_raw) == '43e814339a16582e2205f12117e1f17c40dce2e42a9c52d815a37c043e772e1b':
            self.assertEqual(epoch_raw.count(added),1)
            epoch_raw = epoch_raw.replace(added,b'',1)
        self.assertEqual(g.digest(epoch_raw),installer.UPGRADE_TO)
        epoch_path = self.root / 'historical_generation.py'
        epoch_path.write_bytes(epoch_raw)
        spec = importlib.util.spec_from_file_location('historical_paired_generation',epoch_path)
        epoch = importlib.util.module_from_spec(spec);spec.loader.exec_module(epoch)
        g = epoch
        self.addCleanup(lambda: globals().__setitem__('g',original_g))
        epoch_binding = mock.patch.object(installer,'generation',epoch)
        epoch_binding.start();self.addCleanup(epoch_binding.stop)
        # Reuse the real Studio pin-census owner with an enumerable, throwaway
        # zero-consumer fixture. Never consult actual private Studio accounts.
        studio_root = self.root / 'studio-consumers'
        studio_root.mkdir(mode=0o700)
        patch = mock.patch.object(installer.studio_consumer_owner,
                                  'STUDIO_CONSUMER_ROOT', studio_root)
        patch.start()
        self.addCleanup(patch.stop)
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
        raw = Path(g.__file__).read_bytes().replace(
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
        self.bundle = self.root / 'upgrade'
        self.plan = installer.prepare_upgrade(self.original, self.target.name, self.bundle)
        self.old_plan = (self.original / 'PLAN.json').read_bytes()
        self.old_remote = (self.ext / 'remote_sub.sh').read_bytes()

    def tearDown(self):
        global _active
        _active = False
        # Registered cleanups restore the census binding and dispose the
        # throwaway owner even if an assertion or setUp fails.
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
