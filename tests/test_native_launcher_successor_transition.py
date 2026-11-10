"""B11: real old-owner refusal and one bounded successor in disposable owners.

No installation on the real kit, process launch, provider, network or credentials.
The retained original historical fixture supplies a genuine 8bc bootstrap and
completed d044 transaction. Studio consumer observations use its private root.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from unittest import mock

import pytest

ROLLOUT = Path(__file__).resolve().parents[1] / 'ops/native_fabric/quota_continuity/rollout'
sys.path.insert(0, str(ROLLOUT))
# This incumbent fixture installs its network/process/private-owner audit guard
# before importing the actual source owners. Do not replace its validators.
import test_native_launcher_upgrade as historical

g = historical.g
installer = historical.installer
builder = historical.builder


@pytest.fixture(scope='module')
def source_owners(tmp_path_factory):
    root = tmp_path_factory.mktemp('successor-source').resolve()
    raw = installer._HISTORICAL_LAUNCHER.read_bytes()
    addition = (b'    # One vetted flat plist. Not a suffix rule and not a directory walk.\n'
                b'    if relative == "ext/host_pull_launchd.plist.template":\n'
                b'        return\n')
    assert g.digest(raw) == installer.SUCCESSOR_TO and raw.count(addition) == 1
    old_raw = raw.replace(addition, b'', 1)
    assert g.digest(old_raw) == installer.SUCCESSOR_FROM
    path = root / 'old_d044.py'
    path.write_bytes(old_raw)
    spec = importlib.util.spec_from_file_location('successor_old_d044_fixture', path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    # Build current source first, then restore the exact historical B11 target.
    # Later ordinary generations must not relabel that one finite transition.
    target = root / 'current'
    with mock.patch.object(sys, 'argv', ['builder', '--output', str(target)]), \
            contextlib.redirect_stdout(io.StringIO()):
        builder.main()
    current_raw = (target / 'native-manifest.json').read_bytes()
    manifest = historical.verify_current_stage(target)
    import base64, zlib
    fixture = ROLLOUT.parents[3] / 'tests/fixtures/native-catalog-predecessor102-0be933.json'
    retained_raw = fixture.read_bytes()
    assert g.digest(retained_raw) == '1df5d35c48678fea337238cf23aca6a68e3a16169192259873f7f48c36212fb9'
    retained = json.loads(retained_raw)
    assert retained['schema'] == 'mastermind.test_native_catalog_predecessor102/v1'
    assert retained['source_commit'] == '58083bf128fdac2d8eab374641c78bb403e7d18c'
    historical_manifest = retained['manifest']
    added = {'ext/post_failure_observation.py', 'ext/post_failure_observation_delivery.py',
                'ext/participant_binding.py', 'ext/fabric_participant_owner.py',
                'ext/original_advertised_artifact.py'}
    assert set(manifest) == set(historical_manifest) | added
    # Remove only the two reviewed S14, two participant and one recovery additions inside this disposable102
    # inverse, after proving each is the actual current staged payload.
    for name in added:
        path = target / 'native-code-stage' / name
        assert g.digest(path.read_bytes()) == manifest[name]
        path.unlink()
    manifest = {name: digest for name, digest in manifest.items() if name not in added}
    # S7 changed three additional members of the CURRENT closure. Restore
    # their exact protected predecessor bytes in this historical B11 fixture;
    # the immutable original fixture and paired-upgrade target stay unchanged.
    diagnostic_raw = (ROLLOUT.parents[3] / 'tests/fixtures/native-diagnostic-predecessors-e5f49cf4.json').read_bytes()
    assert g.digest(diagnostic_raw) == 'fcc3ab7de9a8f517ca59d94cf745c1d894fc14478f399e7d18f198f0679233df'
    diagnostic = json.loads(diagnostic_raw)
    assert diagnostic['schema'] == 'mastermind.test_native_diagnostic_predecessors/v1'
    assert diagnostic['source_commit'] == 'e5f49cf4dbe8d06382c1d6f32368e9e9fb51c63d'
    assert set(retained['files']) == {'ext/fabric_task.py', 'ext/pool_ledger.py'}
    assert set(diagnostic['files']) == {'ext/original_delivery_collector.py',
                                      'ext/provider_outcome.py', 'ext/remote_sub.sh'}
    # The 2026-11-03 finite long-horizon source extension legitimately changes
    # ten more CURRENT members than this immutable B11 historical102 snapshot.
    # Restore exact predecessor *bytes* only in the disposable source fixture,
    # with independent protected commit and historical SHA readback, rather
    # than relabeling the old release or ignoring changed-member differences.
    long_path = (ROLLOUT.parents[3] /
                 'tests/fixtures/native-long-horizon-predecessors-20261103.json')
    long_raw = long_path.read_bytes()
    assert g.digest(long_raw) == 'bb924475a501aa732ca0c5b1f05f9428c100c546bcbfb5d3e0c2ceaf268d6f19'
    long_retained = json.loads(long_raw)
    long_names = {'ext/commission_deadline.py','ext/fabric_continuation.py',
                  'ext/remote_sub_exec.py','ext/remote_sub_helpers.py','ext/slot.py'}
    assert (long_retained['schema'] ==
            'mastermind.test_native_long_horizon_predecessors102/v1')
    assert long_retained['source_commit'] == '9f65957e29eba92245d78609f032aaea523b7cb4'
    assert set(long_retained['files']) == long_names
    base_paths = {
        # Only historical102 lacks this retained APPLICATION carrier predecessor.
        # Historical95 already carries its distinct support bytes in its fixture.
        'ext/support_bundle.py':
            ROLLOUT / 'preimages/support_bundle_e5e6153.py',
        'ext/artifact_delivery.py':
            ROLLOUT.parents[1] / 'grok47/overlay/artifact_delivery.py',
        'ext/fabric_operator_contract.py':
            ROLLOUT.parents[1] / 'grok47/overlay/fabric_operator_contract.py',
        'ext/fabric_operator_owner.py':
            ROLLOUT.parent / 'source/fabric_operator_owner.py',
        'ext/native_remote.py':
            ROLLOUT.parents[1] / 'grok47/overlay/native_remote.py',
        'ext/oc_free_exec.sh':
            ROLLOUT.parent / 'source/oc_free_exec.sh',
        'ext/sub.sh':
            ROLLOUT.parents[1] / 'grok47/overlay/sub.sh',
        # Protected899ac broker blob b39e1fbcebe88513ee9c1dd756c56a9c68ff72b1.
        # Restore only this disposable historical102 payload, not CURRENT.
        'ext/lease_broker.py':
            fixture.with_name('native-lease-broker-pre-fair-share-899ac3a9.py.txt'),
        # Protected49c2 custody predecessors are immutable fixture data.
        # The existing loop joins each complete payload to the frozen102 map.
        'ext/linux_process_identity.py':
            fixture.parent / 'native_historical_payloads/linux_process_identity.py.txt',
        'ext/paid_host_qualification.py':
            fixture.parent / 'native_historical_payloads/paid_host_qualification.py.txt',
        'ext/paid_initializer.py':
            fixture.parent / 'native_historical_payloads/paid_initializer.py.txt',
    }
    new_names = long_names | set(base_paths)
    # S9 also changes the CURRENT picker. Bind its authentic protected
    # pre-observer bytes; never widen the immutable B11 transition target.
    selection_raw = (ROLLOUT.parents[3] / 'tests/fixtures/fabric-selection-preobserver-pick-9f65957e.json').read_bytes()
    assert g.digest(selection_raw) == 'b8792950a718d9b7628a8d3917f3ce11c567cfb87fdaa0e917dc6e7fb8c5866c'
    selection = json.loads(selection_raw)
    assert selection['schema'] == 'fabric.selection-preobserver-source.v1'
    assert selection['commit'] == '9f65957e29eba92245d78609f032aaea523b7cb4'
    assert selection['blob'] == 'dd542dbc5bb746c0ad1428b177b25a98b7a02536'
    assert selection['path'] == 'ops/native_fabric/quota_continuity/candidate/pick.py'
    # Reuse the exact protected observer bytes already checked against the
    # immutable95 and102 maps; source/ preimages belong to another epoch.
    observer_raw = (ROLLOUT.parents[3] / 'tests/fixtures/native-observer-historical95-48ca.json').read_bytes()
    assert g.digest(observer_raw) == '0dd81a279641b9c456ef94439d519d97f7670ec18831f5bd78f69bcdd710b3b2'
    observer = json.loads(observer_raw)
    assert observer['schema'] == 'mastermind.test_native_observer_historical95/v1'
    assert observer['source_commit'] == '48ca51f882338c58e377a0acf16931066c703384'
    assert set(observer['files']) == {'ext/run_observation.py', 'ext/run_observation_delivery.py'}
    # Ubuntu4 Grok qualification changes CURRENT policy only. Keep the exact
    # historical B11 policy bytes bound to their protected source and digest.
    qualification_raw = (ROLLOUT.parents[3] / 'tests/fixtures/ubuntu4-grok-qualification-predecessor-f374289e.json').read_bytes()
    assert g.digest(qualification_raw) == '93f5285a758f1045be1f178f35d17e792459f167d2d631ff2914778253b64ebb'
    qualification = json.loads(qualification_raw)
    assert qualification['schema'] == 'fabric.ubuntu4-qualification-predecessor.v1'
    assert qualification['commit'] == 'f374289eb74587eaa755f5bc8e5a3252d00850e0'
    assert qualification['blob'] == 'f72b12eac939143b1b2ed298139d55b06667a2c2'
    assert qualification['path'] == 'ops/native_fabric/quota_continuity/candidate/fabric_host_qualification.py'
    # Restore the byte-pinned old runtime only in this historical102 fixture.
    # The current procfs fallback must not relabel the accepted transition.
    runtime_raw = fixture.with_name('native-historical-lane-runtime-61350902.json').read_bytes()
    assert g.digest(runtime_raw) == '1d658364949b3089ecb35b1ca6f3f8ac79970de1ab44dcc17dd6198a1f1eb3c0'
    runtime = json.loads(runtime_raw)
    assert runtime['schema'] == 'mastermind.native_historical_lane_runtime.v1'
    assert runtime['original_sha256'] == historical_manifest['ext/lane_runtime.py']
    runtime_predecessor = {
        'bytes': runtime['original_bytes'], 'sha256': runtime['original_sha256'],
        'zlib_base64': runtime['zlib_base64'],
    }
    # Restore the exact protected host-pull predecessors only in this
    # historical102 fixture. CURRENT retains the repaired source payloads.
    host_raw = fixture.with_name('native-host-pull-predecessors-9141013f.json').read_bytes()
    assert g.digest(host_raw) == 'f73799e6bb662c7a807ed4865723f770a759d73ae226768709b9bca3d6df3383'
    host = json.loads(host_raw)
    assert host['schema'] == 'mastermind.test_native_host_pull_predecessors/v1'
    assert host['source_commit'] == '9141013f5a969d59f508784b9f4f76794983caa5'
    assert set(host['files']) == {'ext/host_pull.sh', 'ext/host_pull_backend.py',
                                 'ext/host_pull_daemon.sh'}
    predecessor_files = {**retained['files'], **diagnostic['files'], **host['files'],
                         **observer['files'], 'ext/pick.py': selection,
                         'ext/fabric_host_qualification.py': qualification,
                         'ext/lane_runtime.py': runtime_predecessor}
    assert {name for name in manifest if manifest[name] != historical_manifest[name]} == (
        set(predecessor_files) | new_names | set(historical.APPLICATION_PREIMAGES)
    )
    for name, digest in manifest.items():
        assert g.digest((target / 'native-code-stage' / name).read_bytes()) == digest
    for name, item in predecessor_files.items():
        raw = zlib.decompress(base64.b64decode(item['zlib_base64'], validate=True))
        assert len(raw) == item['bytes']
        assert g.digest(raw) == item['sha256'] == historical_manifest[name]
        (target / 'native-code-stage' / name).write_bytes(raw)
    for name, item in long_retained['files'].items():
        payload = zlib.decompress(base64.b64decode(item['zlib_base64'], validate=True))
        assert len(payload) == item['bytes']
        assert g.digest(payload) == item['sha256'] == historical_manifest[name]
        (target / 'native-code-stage' / name).write_bytes(payload)
    for name, predecessor in base_paths.items():
        payload = predecessor.read_bytes()
        assert g.digest(payload) == historical_manifest[name]
        (target / 'native-code-stage' / name).write_bytes(payload)
    historical.restore_application_preimages(target / 'native-code-stage', historical_manifest)
    manifest = historical_manifest
    historical_raw = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    assert g.digest(historical_raw) == retained['manifest_sha256'] == installer.SUCCESSOR_MANIFEST
    for name, digest in manifest.items():
        assert g.digest((target / 'native-code-stage' / name).read_bytes()) == digest
    assert len(manifest) == installer.SUCCESSOR_MEMBER_COUNT
    assert 'ext/host_pull_launchd.plist.template' in manifest
    # The historical fixture alone receives the authentic old verifier.
    with mock.patch.object(historical, 'g', old), mock.patch.object(installer, 'generation', old):
        historical.PairedLauncherUpgrade.setUpClass()
    yield old, target / 'native-code-stage', manifest
    historical.PairedLauncherUpgrade.tearDownClass()
    historical.PairedLauncherUpgrade.doClassCleanups()


@pytest.fixture
def owner(source_owners):
    old, target_stage, manifest = source_owners
    case = historical.PairedLauncherUpgrade('test_real_95_closure_and_original_epoch_upgrade_once')
    # Keep the outer restoration scopes through registered fixture cleanups.
    # The legacy fixture may itself bind d044 in setUp; the successor phase
    # deliberately restores the actual current source owner, never a fallback.
    with mock.patch.object(historical, 'g', old), mock.patch.object(installer, 'generation', old):
        try:
            case.setUp()
            case.predecessor_receipt = installer.upgrade(case.bundle)
            historical.g = g
            installer.generation = g
            case.old = old
            case.predecessor = case.bundle
            case.new_target = g.publish(target_stage, case.ext, manifest)
            case.successor = case.root / 'successor'
            case.original_bytes = {p.name: p.read_bytes() for p in case.original.iterdir()}
            case.predecessor_bytes = {p.name: p.read_bytes() for p in case.predecessor.iterdir()}
            case.history_receipt = case.store / 'bootstrap' / (case.plan['digest'] + '.upgrade.json')
            case.history_bytes = case.history_receipt.read_bytes()
            yield case
        finally:
            case.tearDown()
            case.doCleanups()


def prepare(owner):
    return installer.prepare_successor(owner.predecessor, owner.new_target.name, owner.successor)


def unchanged_history(owner):
    assert {p.name: p.read_bytes() for p in owner.original.iterdir()} == owner.original_bytes
    assert {p.name: p.read_bytes() for p in owner.predecessor.iterdir()} == owner.predecessor_bytes
    assert owner.history_receipt.read_bytes() == owner.history_bytes
    assert (owner.ext / 'remote_sub.sh').read_bytes() == owner.old_remote


def test_actual_old_rejects_new_target_successor_enters_once(owner):
    with pytest.raises(ValueError, match='flat code'):
        owner.old.verify(owner.store, owner.new_target.name)
    assert g.verify(owner.store, owner.new_target.name)[0] == owner.new_target
    plan = prepare(owner)
    before = g.current(owner.store)
    receipt = installer.apply_successor(owner.successor)
    assert receipt['selection'] == g.current(owner.store)
    assert receipt['selection']['generation'] == owner.new_target.name
    assert receipt['selection']['sequence'] == before['sequence'] + 1
    assert receipt['prior_upgrade_digest'] == owner.plan['digest']
    assert receipt['remote'] == 'legacy'
    for name in ('pool', 'task'):
        assert g.digest(g.regular_bytes(plan['entries'][name]['target'])) == plan['entries'][name]['bridge']
    unchanged_history(owner)
    with mock.patch.object(g, 'atomic_bytes', side_effect=AssertionError('completed replay wrote')):
        assert installer.apply_successor(owner.successor) == receipt


def test_historical_upgrade_contract_is_not_relabelled(owner):
    assert installer.UPGRADE_MANIFEST == '6ac208bbd80f706931b11e8147a879f6e3ced6fe704cde7b9f15e1c098e37ee4'
    assert installer.UPGRADE_TO == owner.old.digest(Path(owner.old.__file__).read_bytes())
    with mock.patch.object(installer, 'generation', owner.old):
        # Replaying the completed old transition is refused on its real current
        # paid-zip selection. Its original admission boundary also rejects the
        # new target when supplied the authentic historical pre-upgrade snapshot.
        with pytest.raises(ValueError, match='old launcher cannot verify the prior selection'):
            installer.prepare_upgrade(owner.original, owner.new_target.name, owner.root / 'not-historical')
        with pytest.raises(ValueError, match='flat code'):
            installer._upgrade_plan(owner.original, owner.new_target.name, owner.plan['expected_selection'])
    assert not (owner.root / 'not-historical').exists()
    unchanged_history(owner)


@pytest.mark.parametrize('artifact', ['receipt', 'intent', 'payload', 'original_source'])
def test_missing_or_changed_predecessor_never_creates_successor(owner, artifact):
    if artifact == 'receipt':
        owner.history_receipt.unlink()
    elif artifact == 'intent':
        g.atomic_bytes(owner.store / 'bootstrap/.paired-launcher-upgrade.json', b'{}\n', 0o600)
    elif artifact == 'payload':
        g.atomic_bytes(owner.predecessor / 'pool.bridge', b'foreign\n', 0o600)
    else:
        g.atomic_bytes(owner.original / 'native_generation.py', b'foreign\n', 0o600)
    with pytest.raises((ValueError, OSError)):
        prepare(owner)
    assert not owner.successor.exists()
    assert not (owner.store / 'bootstrap/.launcher-successor-v1.json').exists()


def test_self_rehashed_prior_plan_is_not_authority(owner):
    p = owner.predecessor / 'PLAN.json'
    value = json.loads(p.read_bytes())
    value['entries']['remote']['previous'] = 'a' * 64
    value.pop('digest')
    value['digest'] = g.digest(g.canonical(value))
    g.atomic_bytes(p, g.canonical(value) + b'\n', 0o600)
    with pytest.raises(ValueError, match='derivation'):
        prepare(owner)
    assert not owner.successor.exists()


def test_wrong_target_cannot_be_admitted(owner):
    with pytest.raises(ValueError, match='reviewed successor closure'):
        installer.prepare_successor(owner.predecessor, owner.initial.name, owner.successor)
    assert not owner.successor.exists()


def test_source_owner_hash_is_not_a_caller_hint(owner):
    path = owner.root / 'wrong_generation.py'
    path.write_bytes(installer._HISTORICAL_LAUNCHER.read_bytes() + b'\n# extra source\n')
    with mock.patch.object(installer, '_HISTORICAL_LAUNCHER', path):
        with pytest.raises(ValueError, match='source differs'):
            prepare(owner)
    assert not owner.successor.exists()


def test_new_bundle_symlink_refuses(owner):
    prepare(owner)
    path = owner.successor / 'task.bridge'
    raw = path.read_bytes()
    path.unlink()
    twin = owner.root / 'twin'; twin.write_bytes(raw)
    path.symlink_to(twin)
    with pytest.raises((ValueError, OSError)):
        installer.apply_successor(owner.successor)
    assert not (owner.store / 'bootstrap/.launcher-successor-v1.json').exists()


@pytest.mark.parametrize('observation', ['conflict', 'unavailable', 'not_list'])
def test_real_pin_authority_refuses_before_intent(owner, observation):
    prepare(owner)
    before = g.current(owner.store)
    if observation == 'unavailable':
        effect = mock.patch.object(installer.studio_consumer_owner, 'pinned_consumers', side_effect=OSError('private detail'))
    else:
        effect = mock.patch.object(installer.studio_consumer_owner, 'pinned_consumers',
                                   return_value=['private account'] if observation == 'conflict' else None)
    with effect, pytest.raises(ValueError, match='STUDIO_CONSUMER_') as raised:
        installer.apply_successor(owner.successor)
    assert 'private' not in str(raised.value)
    assert not (owner.store / 'bootstrap/.launcher-successor-v1.json').exists()
    assert g.current(owner.store) == before


def test_stale_full_pointer_same_generation_refuses(owner):
    prepare(owner)
    before = g.current(owner.store)
    g.select(owner.store, before['generation'], before['generation'])
    with pytest.raises(ValueError, match='compare-and-swap'):
        installer.apply_successor(owner.successor)
    assert not (owner.store / 'bootstrap/.launcher-successor-v1.json').exists()


def test_foreign_remote_or_ingress_refuses(owner):
    prepare(owner)
    g.atomic_bytes(owner.ext / 'remote_sub.sh', b'foreign\n', 0o755)
    with pytest.raises(ValueError, match='preimage refused'):
        installer.apply_successor(owner.successor)
    assert not (owner.store / 'bootstrap/.launcher-successor-v1.json').exists()


def test_foreign_same_slot_intent_refuses(owner):
    prepare(owner)
    g.atomic_bytes(owner.store / 'bootstrap/.launcher-successor-v1.json', b'{}\n', 0o600)
    with pytest.raises(ValueError, match='foreign launcher successor'):
        installer.apply_successor(owner.successor)


@pytest.mark.parametrize('edge', ['intent', 'launcher', 'pool', 'task', 'selection', 'receipt'])
def test_each_actual_atomic_edge_recovers_same_operation_only(owner, edge):
    plan = prepare(owner)
    targets = {
        'intent': owner.store / 'bootstrap/.launcher-successor-v1.json',
        'launcher': owner.store / 'launchers' / (installer.SUCCESSOR_TO + '.py'),
        'pool': owner.pool, 'task': owner.ext / 'fabric_task.py',
        'selection': owner.store / 'CURRENT.json',
        'receipt': owner.store / 'bootstrap' / (plan['digest'] + '.successor.json'),
    }
    atomic = g.atomic_bytes
    def fail(path, *args):
        atomic(path, *args)
        if Path(path) == targets[edge]:
            raise OSError('disposable interruption after committed write')
    with mock.patch.object(g, 'atomic_bytes', side_effect=fail), pytest.raises(OSError, match='disposable interruption'):
        installer.apply_successor(owner.successor)
    before = g.current(owner.store)
    receipt = installer.apply_successor(owner.successor)
    assert g.current(owner.store) == receipt['selection']
    if edge in ('selection', 'receipt'):
        assert before == receipt['selection']
    unchanged_history(owner)


def test_selected_missing_launcher_is_not_repaired(owner):
    prepare(owner)
    atomic = g.atomic_bytes
    def stop(path, *args):
        atomic(path, *args)
        if Path(path) == owner.store / 'CURRENT.json':
            raise OSError('selected')
    with mock.patch.object(g, 'atomic_bytes', side_effect=stop), pytest.raises(OSError, match='selected'):
        installer.apply_successor(owner.successor)
    launcher = owner.store / 'launchers' / (installer.SUCCESSOR_TO + '.py')
    launcher.unlink()
    with mock.patch.object(g, 'atomic_bytes', side_effect=AssertionError('repair wrote')):
        with pytest.raises((ValueError, OSError)):
            installer.apply_successor(owner.successor)
    assert not launcher.exists()


def test_predecessor_drift_after_first_ingress_stops_before_second(owner):
    prepare(owner)
    atomic = g.atomic_bytes
    before = g.current(owner.store)
    task = (owner.ext / 'fabric_task.py').read_bytes()
    def drift(path, *args):
        atomic(path, *args)
        if Path(path) == owner.pool:
            atomic(owner.history_receipt, b'{}\n', 0o600)
    with mock.patch.object(g, 'atomic_bytes', side_effect=drift), pytest.raises(ValueError, match='predecessor intent or receipt'):
        installer.apply_successor(owner.successor)
    assert (owner.ext / 'fabric_task.py').read_bytes() == task
    assert g.current(owner.store) == before
    assert (owner.store / 'bootstrap/.launcher-successor-v1.json').exists()


def test_cli_uses_the_actual_prepare_and_apply(owner):
    with mock.patch.object(sys, 'argv', ['installer', 'prepare-successor',
             '--prior-upgrade-bundle', str(owner.predecessor), '--target-generation', owner.new_target.name,
             '--output', str(owner.successor)]), contextlib.redirect_stdout(io.StringIO()) as output:
        installer.main()
    assert json.loads(output.getvalue())['schema'] == installer.SUCCESSOR_SCHEMA
    with mock.patch.object(sys, 'argv', ['installer', 'successor', '--bundle', str(owner.successor)]), \
            contextlib.redirect_stdout(io.StringIO()) as output:
        installer.main()
    assert json.loads(output.getvalue())['selection'] == g.current(owner.store)
    unchanged_history(owner)


def test_normal_selection_since_completed_predecessor_is_bound(owner):
    old = g.current(owner.store)
    advanced = owner.old.select(owner.store, old['generation'], old['generation'])
    assert advanced['sequence'] > owner.predecessor_receipt['selection']['sequence']
    plan = prepare(owner)
    assert plan['expected_selection'] == advanced
    receipt = installer.apply_successor(owner.successor)
    assert receipt['previous_selection'] == advanced
    assert receipt['selection']['sequence'] == advanced['sequence'] + 1
    unchanged_history(owner)


def test_late_pin_conflict_keeps_intent_without_replacing_pool(owner):
    prepare(owner)
    before = g.current(owner.store)
    pool = owner.pool.read_bytes()
    task = (owner.ext / 'fabric_task.py').read_bytes()
    with mock.patch.object(installer.studio_consumer_owner, 'pinned_consumers',
                           side_effect=[[], ['private account']]) as census:
        with pytest.raises(ValueError, match='STUDIO_CONSUMER_PIN_MIGRATION_REQUIRED'):
            installer.apply_successor(owner.successor)
    assert census.call_count == 2
    assert owner.pool.read_bytes() == pool
    assert (owner.ext / 'fabric_task.py').read_bytes() == task
    assert g.current(owner.store) == before
    assert (owner.store / 'bootstrap/.launcher-successor-v1.json').exists()


def test_late_full_pointer_drift_refuses_before_selection_cas(owner):
    prepare(owner)
    atomic = g.atomic_bytes
    before = g.current(owner.store)
    drifted = dict(before, sequence=before['sequence'] + 7)
    def drift(path, *args):
        atomic(path, *args)
        if Path(path) == owner.ext / 'fabric_task.py':
            atomic(owner.store / 'CURRENT.json', g.canonical(drifted) + b'\n', 0o600)
    with mock.patch.object(g, 'atomic_bytes', side_effect=drift), \
            mock.patch.object(g, '_select_locked', side_effect=AssertionError('stale CAS reached')):
        with pytest.raises(ValueError, match='selection changed before commit'):
            installer.apply_successor(owner.successor)
    assert g.current(owner.store) == drifted
    assert (owner.store / 'bootstrap/.launcher-successor-v1.json').exists()


def test_paired_entries_resolve_through_real_new_owner_without_process_launch(owner):
    plan = prepare(owner)
    receipt = installer.apply_successor(owner.successor)
    # Real launch selection/verification/entry construction, intercepted only at
    # execve. This is not provider execution or a live installed fresh-load proof.
    class CapturedExec(Exception):
        pass
    for entry, relative in [('pool', 'pool'), ('task', 'ext/fabric_task.py')]:
        with mock.patch.dict(g.os.environ, {'PATH': '/usr/bin:/bin'}, clear=True), \
                mock.patch.object(g.os, 'execve', side_effect=CapturedExec) as effect:
            with pytest.raises(CapturedExec):
                g.launch(owner.store, entry, ['--help'])
        executable, argv, environment = effect.call_args.args
        assert argv[1] == str(owner.new_target / relative)
        assert argv[2:] == ['--help']
        assert environment['FABRIC_NATIVE_CODE_GENERATION'] == receipt['selection']['generation']
        assert g.digest(g.regular_bytes(plan['entries'][entry]['target'])) == plan['entries'][entry]['bridge']


@pytest.mark.parametrize('edge', ['publication', 'pool', 'task'])
def test_published_successor_owner_drift_refuses_before_next_authority_edge(owner, edge):
    prepare(owner)
    before = g.current(owner.store)
    pool, task = owner.pool.read_bytes(), (owner.ext / 'fabric_task.py').read_bytes()
    launcher = owner.store / 'launchers' / (installer.SUCCESSOR_TO + '.py')
    atomic = g.atomic_bytes
    def drift(path, *args):
        atomic(path, *args)
        changed_at = {'publication': launcher, 'pool': owner.pool,
                      'task': owner.ext / 'fabric_task.py'}[edge]
        if Path(path) == changed_at:
            atomic(launcher, b'foreign owner bytes\n', 0o555)
    with mock.patch.object(g, 'atomic_bytes', side_effect=drift):
        with pytest.raises(ValueError, match='successor launcher differs'):
            installer.apply_successor(owner.successor)
    if edge == 'publication':
        assert owner.pool.read_bytes() == pool
    if edge != 'task':
        assert (owner.ext / 'fabric_task.py').read_bytes() == task
    assert g.current(owner.store) == before
    assert (owner.store / 'bootstrap/.launcher-successor-v1.json').exists()


def test_installed_control_resolves_actual_completed_successor(owner, tmp_path):
    """Construct under the installer guard, then prove the sealed read context."""
    import importlib.util
    import os
    import subprocess
    repository = ROLLOUT.parents[3]
    control_source = repository / "integrations/studio_direct_mcp"
    spec = importlib.util.spec_from_file_location(
        "successor_installed_control_bundle", control_source / "control_bundle.py")
    bundle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bundle)
    import hashlib
    import stat
    def owner_bytes():
        result = {}
        for path in sorted(owner.root.rglob("*")):
            info = path.lstat()
            value = (os.readlink(path) if path.is_symlink() else
                     hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else
                     "directory")
            result[str(path.relative_to(owner.root))] = (stat.S_IMODE(info.st_mode), value)
        return result
    plan = prepare(owner)
    receipt = installer.apply_successor(owner.successor)
    before = owner_bytes()
    pointer = g.current(owner.store)
    # Close the real installer's audited phase through its normal teardown.
    # Its existing registered cleanup retains this disposable tree until the
    # installed-control read phase completes; no audit exception is added.
    owner.tearDown()
    home = tmp_path / "installed-home"
    home.mkdir(mode=0o700)
    control = home / ".local/share/studio-direct-mcp/control"
    control.mkdir(parents=True, mode=0o700)
    launcher = home / ".local/bin/studio-direct"
    launcher.parent.mkdir(parents=True, mode=0o700)
    launcher.write_text("#!/bin/sh\nexit 0\n")
    launcher.chmod(0o700)
    with mock.patch.object(bundle.Path, "home", return_value=home):
        installed = bundle.install(source=control_source, control_root=control,
                                   launcher=launcher)
    assert len(installed["files"]) == 74
    code = r"""
import importlib.util,json,sys
from pathlib import Path
from types import SimpleNamespace
root=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location("installed_successor_proof",root/"private_service.py")
svc=importlib.util.module_from_spec(spec);sys.modules[spec.name]=svc
spec.loader.exec_module(svc)
args=SimpleNamespace(successor_bundle=Path(sys.argv[2]),
    successor_plan_sha256=sys.argv[3],account="chatgpt1",operation="status")
with svc._pin_native_context(args) as observed:
    assert observed["phase"]=="SELECTED"
    print(json.dumps(observed,sort_keys=True))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", code, str(control),
         str(owner.successor), plan["digest"]],
        cwd=home, env={"HOME": str(home), "PATH": "/usr/bin:/bin", "LANG": "C"},
        capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["successor_digest"] == plan["digest"]
    assert observed["selection"] == receipt["selection"] == pointer
    assert observed["pool_bridge"] == plan["entries"]["pool"]["bridge"]
    assert owner_bytes() == before
    assert g.current(owner.store) == pointer
