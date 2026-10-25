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
    raw = Path(g.__file__).read_bytes()
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
    # Build the actual candidate; no model-generated count or placeholder files.
    target = root / 'current'
    with mock.patch.object(sys, 'argv', ['builder', '--output', str(target)]), \
            contextlib.redirect_stdout(io.StringIO()):
        builder.main()
    manifest = json.loads((target / 'native-manifest.json').read_bytes())
    assert g.digest((target / 'native-manifest.json').read_bytes()) == installer.SUCCESSOR_MANIFEST
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
    path.write_bytes(Path(g.__file__).read_bytes() + b'\n# extra source\n')
    with mock.patch.object(g, '__file__', str(path)):
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
