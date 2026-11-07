"""One normally installed prepared parent continues its own bounded chain.

The installed selector, its schema, its exact nine-entry namespace and the
normal-input producer stay exactly as accepted; the new behavior is only that
one installed prepared parent can itself be superseded by the same selector,
re-authenticating its whole sealed lineage down to the genuine original
sixteen-origin leaf without ever demanding that a historical ancestor is
still the current installation. Real SQLite, issuers, migrations, prepared
successor producers, proof/backup/restore producers and every maintenance
validator execute; the existing Root/account/ACL/install/ancestor seams stay
the same inert fixture inputs. No live host or provider is touched.
"""
import copy
import fcntl
import hashlib
import json
import os
import sqlite3
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.test_executive_persistent_origin import filesystem


@pytest.fixture(autouse=True)
def _current_data_anchor_fixture(filesystem):
    """Explicit raw Root/Darwin facts; real held anchor predicates execute."""
    yield filesystem

from control_plane import executive_backup as b
from ops.executive_os import acceptance_maintenance as m
from ops.executive_os import prepare_control_successor as producer
from tests import test_executive_acceptance_v5_to_v7 as fixtures
from tests import test_executive_installed_migration_successor as installed
from tests import test_executive_prepared_migration_successor as prepared

P, F, G, H = prepared.P, installed.R, '3'*40, '5'*40
_INSTALL_SEQUENCE = [P, P, F, F]


def _rewrite(path, raw):
    mode = stat.S_IMODE(path.lstat().st_mode)
    path.chmod(0o600); path.write_bytes(raw); path.chmod(mode)
    assert stat.S_IMODE(path.lstat().st_mode) == mode


def _bundle_state(sha):
    return {path: (path.read_bytes(), path.stat().st_ino)
            for path in m.bundle_path(sha).iterdir()}


def _strict_install(f, monkeypatch, current):
    """The real observer refuses every release that is not the one installation."""
    def observe(sha):
        f.install_checks.append(sha)
        if sha != current[0]:
            raise m.MaintenanceError('inert fullseal/plist refusal for a noncurrent release')
    monkeypatch.setattr(m, '_require_preparation_install', observe)


def _stage_release(monkeypatch, sha):
    (m.SYSTEM_ROOT/'releases'/sha).mkdir(mode=0o700)
    monkeypatch.setattr(b, '_SCHEMA_UPGRADE_RELEASE_OBSERVER', lambda: dict(
        release_root=str(m.SYSTEM_ROOT/'releases'/sha), release_sha=sha,
        release_tree_sha='b'*40, release_manifest_sha256='c'*64))


def _install_release(f, parent_sha):
    """Model the existing normal selected-config transition of one prepared parent."""
    source = m.sealed_bytes(m.bundle_path(parent_sha)/m._INSTALLED_PARENT_CONTROL_NAME,
                            m._MAX_DOCUMENT_BYTES)
    original = producer._parse(source)
    value = producer.build_successor(original, source_sha=parent_sha,
                                    macro_root=original['ceo_ingress_app_macro_root'])
    raw = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False)+'\n').encode()
    assert raw == m._normal_installed_preparation_config(source, parent_sha)
    f.config.clear(); f.config.update(json.loads(raw))
    _rewrite(m.SYSTEM_ROOT/'config/control.json', raw)
    return raw


def _select_installed(f, target, parent_sha):
    args = copy.deepcopy(f.new_args)
    args.supersede_unstarted_migration_preparation_sha = None
    args.supersede_installed_unstarted_migration_preparation_sha = parent_sha
    args.superseded_migration_preparation_descriptor_sha256 = m.digest(m.descriptor_for(parent_sha))
    args.successor_sha = target
    raw = _install_release(f, parent_sha)
    args.expected_installed_parent_control_config_sha256 = hashlib.sha256(raw).hexdigest()
    return args


def _accept(f, target, tmp_path, monkeypatch, owner):
    """The real proof delta, backup chain, receipts, PASS summary and finish."""
    monkeypatch.setattr(fixtures, 'SUCCESSOR', target)
    proof_ids = fixtures._actual_proof_delta(f, m.descriptor_for(target))
    receipt, verification, drill, applied = fixtures._proof_backup_chain(f, tmp_path)
    acceptance = fixtures._write_proof_receipts(f, receipt, verification, drill, applied)
    summary = acceptance/'acceptance-summary.json'
    fixtures._write_receipt(summary, fixtures._real_pass_summary(f, proof_ids))
    fd = os.open(f.lock, os.O_RDWR); fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
    live = sqlite3.connect(f.database); live.execute('PRAGMA journal_mode=WAL')
    with live: live.execute('UPDATE workers SET last_seen_at_ms=last_seen_at_ms+1,'
                            'updated_at_ms=updated_at_ms+1,version=version+1')
    try: owner.finish(proof_ids, summary)
    finally: live.close(); fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)
    return proof_ids, summary


def _later_carry(f, descriptor, carry, summary, successor, job_text):
    future = {key: value for key, value in descriptor.items() if key in m._DESCRIPTOR_V2_KEYS}
    future.update(schema_version=m.SCHEMA_V2, predecessor_sha=successor, successor_sha='1'*40,
        prior_descriptor_sha256=m.digest(descriptor), prior_carry_sha256=m.digest(carry),
        prior_summary_sha256=hashlib.sha256(summary.read_bytes()).hexdigest())
    bundle = m.bundle_path('1'*40); bundle.mkdir()
    m.write_sealed(bundle/'descriptor.json', future, public=True)
    from control_plane.executive_runtime import Runtime
    Runtime.at(f.runtime_root).jobs.create_job(job_text)
    m.validate_prior_carry_binding(future)


def _fabricated_installed_bundle(sha, parent_sha, parent_digest):
    """A shape-exact installed bundle whose inherited content is fabricated."""
    keys = m._DESCRIPTOR_INSTALLED_PREPARED_MIGRATION_SUCCESSOR_KEYS
    control = b'fabricated-installed-parent-control\n'
    value = {key: ('a'*64 if key.endswith('_sha256') else 'JOB-fixture') for key in keys}
    value.update(schema_version=m.SCHEMA_INSTALLED_PREPARED_MIGRATION_SUCCESSOR,
        predecessor_sha='9'*40, successor_sha=sha, root_event_id=1, terminal_marker_event_id=1,
        worker_id='fixture-worker', quota_class='fixture-quota', terminal_attempt_id='ATT-fixture',
        frozen_base_sha='9'*40, superseded_unstarted_preproof_sha='8'*40,
        superseded_unstarted_migration_preparation_sha=parent_sha,
        superseded_migration_preparation_descriptor_sha256=parent_digest,
        installed_parent_control_config_sha256=hashlib.sha256(control).hexdigest())
    directory = m.bundle_path(sha)
    directory.mkdir()
    m.write_sealed(directory/'preparing.json',
                   {'schema_version': m.SCHEMA_INSTALLED_PREPARED_MIGRATION_SUCCESSOR})
    m.write_sealed_bytes(directory/m._INSTALLED_PARENT_CONTROL_NAME, control)
    for name in m._V5_TO_V7_BUNDLE_NAMES - {'descriptor.json', 'preparing.json'}:
        target = directory/name
        target.write_bytes(b'fabricated')
        os.chmod(target, 0o400)
    m.write_sealed(directory/'descriptor.json', value, public=True)
    return value


@pytest.fixture
def walker_env(tmp_path, monkeypatch):
    """Only the SYSTEM_ROOT/custody seams the pure parent walk itself reads."""
    monkeypatch.setattr(m, 'SYSTEM_ROOT', tmp_path/'system')
    (m.SYSTEM_ROOT/'acceptance-maintenance').mkdir(parents=True, mode=0o755)
    monkeypatch.setattr(m, '_TRUSTED_UID', os.getuid())
    monkeypatch.setattr(m, '_TRUSTED_GID', os.getgid())
    monkeypatch.setattr(m, '_sealed_ancestors', lambda path: [])
    monkeypatch.setattr(m, 'has_macos_acl', lambda *args, **kwargs: False)
    monkeypatch.setattr(m, 'os', SimpleNamespace(
        **{name: getattr(os, name) for name in dir(os) if name != 'geteuid'},
        geteuid=lambda: 0))
    monkeypatch.setattr(m, 'sys', SimpleNamespace(platform='darwin'))
    yield tmp_path


def test_installed_parent_chain_prepare_admit_restore_finish_and_carry(tmp_path, monkeypatch):
    f = installed._installed_fixture(tmp_path, monkeypatch)
    current = [P]
    _strict_install(f, monkeypatch, current)
    # The uninstalled selector still refuses the normally installed preimage.
    with pytest.raises(m.MaintenanceError, match='config or original root'):
        m.prepare(f.old_args)
    assert f.install_checks == []
    result = m.prepare(f.new_args)
    descriptor = m.descriptor_for(F)
    assert descriptor['schema_version'] == m.SCHEMA_INSTALLED_PREPARED_MIGRATION_SUCCESSOR
    assert f.install_checks == [P, P]
    assert len(list(result.iterdir())) == 9
    installed_raw = (result/m._INSTALLED_PARENT_CONTROL_NAME).read_bytes()
    assert installed_raw == f.installed_raw
    parent_state, leaf_state = _bundle_state(F), _bundle_state(P)
    # Continue the existing installed selector through the installed parent.
    current[0] = F
    _install_release(f, F)
    _stage_release(monkeypatch, G)
    g_result = m.prepare(_select_installed(f, G, F))
    g_descriptor = m.descriptor_for(G)
    assert g_descriptor['schema_version'] == m.SCHEMA_INSTALLED_PREPARED_MIGRATION_SUCCESSOR
    assert g_descriptor['superseded_unstarted_migration_preparation_sha'] == F
    assert g_descriptor['installed_parent_control_config_sha256'] == hashlib.sha256(
        (m.SYSTEM_ROOT/'config/control.json').read_bytes()).hexdigest()
    assert all((g_result/name).read_bytes() == (result/name).read_bytes()
               for name in m._V5_TO_V7_BUNDLE_NAMES - {'descriptor.json', 'preparing.json'})
    assert (g_result/m._INSTALLED_PARENT_CONTROL_NAME).read_bytes() == \
        m._normal_installed_preparation_config(installed_raw, F)
    assert f.install_checks == [P, P, F, F]
    # The immediate installed parent stays distinct from the genuine leaf executor.
    parent = m._prepared_migration_parent(g_descriptor)
    assert parent['descriptor']['successor_sha'] == F
    assert m._v5_to_v7_tool_release(
        m.sealed_json(g_result/m._V5_TO_V7_EVIDENCE_NAME)) == P
    assert _bundle_state(F) == parent_state and _bundle_state(P) == leaf_state
    prepared._assert_parent_unchanged(f)
    # Admit the actual newly installed G and take it through the real acceptance.
    current[0] = G
    _install_release(f, G)
    owner = m.Maintenance(G, m.digest(g_descriptor), f.config)
    assert m.sealed_json(g_result/'run-started.json')['schema_version'] == \
        m.SCHEMA_INSTALLED_PREPARED_MIGRATION_SUCCESSOR
    assert f.install_checks == [P, P, F, F, G, G]
    proof_ids, summary = _accept(f, G, tmp_path, monkeypatch, owner)
    carry = m.sealed_json(g_result/'carry-forward.json')
    assert carry['passed'] is True
    assert carry['schema_version'] == m.SCHEMA_INSTALLED_PREPARED_MIGRATION_SUCCESSOR
    assert not (m.bundle_path(F)/'run-started.json').exists()
    assert not (f.runtime_root.parent/'acceptance'/F).exists()
    prepared._assert_parent_unchanged(f)
    # An accepted G — its bundle now carries its own terminal files — is never
    # an unstarted-parent candidate again; no target or install request follows.
    with pytest.raises(m.MaintenanceError,
                       match='prepared migration parent is not an intact unstarted preparation'):
        m.prepare(_select_installed(f, '7'*40, G))
    assert not m.bundle_path('7'*40).exists()
    assert f.install_checks == [P, P, F, F, G, G]
    # The uninstalled selector still cannot widen its own issuance onto an
    # installed parent, end to end and at the walker entry.
    wrong = copy.deepcopy(f.new_args)
    wrong.supersede_unstarted_migration_preparation_sha = F
    wrong.supersede_installed_unstarted_migration_preparation_sha = None
    wrong.expected_installed_parent_control_config_sha256 = None
    wrong.superseded_migration_preparation_descriptor_sha256 = m.digest(descriptor)
    wrong.successor_sha = '8'*40
    with pytest.raises(m.MaintenanceError,
                       match='prepared migration parent is not an intact unstarted preparation'):
        m.prepare(wrong)
    assert not m.bundle_path('8'*40).exists()
    with m._UnstartedPreproofGuard() as guard:
        with pytest.raises(m.MaintenanceError,
                           match='prepared migration parent is not an intact unstarted preparation'):
            m._read_prepared_migration_parent(F, m.digest(descriptor), guard, installed=False)
    # Later ordinary carry over the accepted G: the whole history re-derives
    # through the real owners and never requests a retired installation.
    _later_carry(f, g_descriptor, carry, summary, G,
                 'later unrelated installed-chain fixture job')
    assert f.install_checks == [P, P, F, F, G, G]
    assert _bundle_state(F) == parent_state and _bundle_state(P) == leaf_state
    prepared._assert_parent_unchanged(f)


def test_second_unstarted_installed_epoch_recurses_with_one_walk_memo(tmp_path, monkeypatch):
    f = installed._installed_fixture(tmp_path, monkeypatch)
    current = [P]
    _strict_install(f, monkeypatch, current)
    m.prepare(f.new_args)
    current[0] = F; _install_release(f, F)
    _stage_release(monkeypatch, G)
    m.prepare(_select_installed(f, G, F))
    current[0] = G; _install_release(f, G)
    _stage_release(monkeypatch, H)
    h_result = m.prepare(_select_installed(f, H, G))
    h_descriptor = m.descriptor_for(H)
    assert h_descriptor['superseded_unstarted_migration_preparation_sha'] == G
    assert f.install_checks == [P, P, F, F, G, G]
    # The walk recurses through two installed links to the genuine original leaf.
    g_digest = h_descriptor['superseded_migration_preparation_descriptor_sha256']
    g_sha = h_descriptor['superseded_unstarted_migration_preparation_sha']
    with m._UnstartedPreproofGuard() as guard:
        chain = m._read_prepared_migration_parent(g_sha, g_digest, guard, installed=True)
        assert chain['descriptor']['successor_sha'] == G
        assert chain['descriptor']['superseded_unstarted_migration_preparation_sha'] == F
        assert m._v5_to_v7_tool_release(chain['material']) == P
    counts = {'inventory': 0}
    real_sealed_json = m.sealed_json
    def counting(path, *args, **kwargs):
        if path.name == 'inventory.json': counts['inventory'] += 1
        return real_sealed_json(path, *args, **kwargs)
    monkeypatch.setattr(m, 'sealed_json', counting)
    with m._UnstartedPreproofGuard() as guard:
        first = m._read_prepared_migration_parent(g_sha, g_digest, guard, installed=True)
        cold = counts['inventory']
        assert cold == 3
        again = m._read_prepared_migration_parent(g_sha, g_digest, guard, installed=True)
        assert again is first and counts['inventory'] == cold
        raw = m._installed_preparation_snapshot(h_descriptor, h_result, guard=guard)
        assert raw == (h_result/m._INSTALLED_PARENT_CONTROL_NAME).read_bytes()
        assert counts['inventory'] == cold
        with pytest.raises(m.MaintenanceError):
            m._read_prepared_migration_parent(G, '0'*64, guard, installed=True)
    assert guard.prepared_parents == {} and guard.closed is True
    with pytest.raises(m.MaintenanceError, match='live retained custody'):
        m._read_prepared_migration_parent(G, g_digest, guard, installed=True)
    with pytest.raises(m.MaintenanceError, match='live retained custody'):
        m._read_prepared_migration_parent(G, g_digest, object(), installed=True)
    # Admit the actual newly installed H and complete its real acceptance.
    current[0] = H; _install_release(f, H)
    owner = m.Maintenance(H, m.digest(h_descriptor), f.config)
    assert f.install_checks == [P, P, F, F, G, G, H, H]
    proof_ids, summary = _accept(f, H, tmp_path, monkeypatch, owner)
    carry = m.sealed_json(h_result/'carry-forward.json')
    assert carry['passed'] is True
    assert carry['schema_version'] == m.SCHEMA_INSTALLED_PREPARED_MIGRATION_SUCCESSOR
    # Both earlier epochs stay exact unstarted installed ancestors.
    assert not (m.bundle_path(F)/'run-started.json').exists()
    assert not (m.bundle_path(G)/'run-started.json').exists()
    assert not (f.runtime_root.parent/'acceptance'/F).exists()
    assert not (f.runtime_root.parent/'acceptance'/G).exists()
    _later_carry(f, h_descriptor, carry, summary, H,
                 'later unrelated second-epoch fixture job')
    assert f.install_checks == [P, P, F, F, G, G, H, H]
    prepared._assert_parent_unchanged(f)


def test_fabricated_parent_cycle_refuses(walker_env):
    _fabricated_installed_bundle('b'*40, 'a'*40, '0'*64)
    a_value = _fabricated_installed_bundle('a'*40, 'b'*40, m.digest(m.descriptor_for('b'*40)))
    with m._UnstartedPreproofGuard() as guard:
        with pytest.raises(m.MaintenanceError, match='cyclic'):
            m._read_prepared_migration_parent('a'*40, m.digest(a_value), guard, installed=True)


def test_fabricated_parent_depth_bound_refuses(walker_env):
    shas = [f'{index:040x}' for index in range(65)]
    deepest = 'f'*40
    previous = _fabricated_installed_bundle(shas[63], deepest, '0'*64)
    for index in range(62, -1, -1):
        previous = _fabricated_installed_bundle(shas[index], shas[index+1], m.digest(previous))
    with m._UnstartedPreproofGuard() as guard:
        with pytest.raises(m.MaintenanceError, match='too deep'):
            m._read_prepared_migration_parent(shas[0], m.digest(previous), guard, installed=True)
    assert not m.bundle_path(deepest).exists()


def test_walk_requires_live_retained_custody(walker_env):
    with m._UnstartedPreproofGuard() as guard:
        pass
    with pytest.raises(m.MaintenanceError, match='live retained custody'):
        m._read_prepared_migration_parent('a'*40, 'b'*64, guard, installed=True)
    with pytest.raises(m.MaintenanceError, match='live retained custody'):
        m._read_prepared_migration_parent('a'*40, 'b'*64, object(), installed=True)


@pytest.mark.parametrize('fault', ['parent-cas', 'installed-pin', 'old-snapshot',
                                   'current-config', 'install-refusal', 'parent-started',
                                   'grandparent-pin', 'grandparent-acceptance'])
def test_unqualified_installed_chain_never_publishes_the_new_target(tmp_path, monkeypatch, fault):
    f = installed._installed_fixture(tmp_path, monkeypatch)
    result = m.prepare(f.new_args)
    descriptor = m.descriptor_for(F)
    current = [F]
    _strict_install(f, monkeypatch, current)
    _install_release(f, F)
    _stage_release(monkeypatch, G)
    g_args = _select_installed(f, G, F)
    if fault == 'parent-cas':
        g_args.superseded_migration_preparation_descriptor_sha256 = '0'*64
    elif fault == 'installed-pin':
        _rewrite(result/m._INSTALLED_PARENT_CONTROL_NAME,
                 (result/m._INSTALLED_PARENT_CONTROL_NAME).read_bytes()+b' ')
    elif fault == 'old-snapshot':
        # F must retain its real P-era installed snapshot. Replacing it with
        # the CURRENT F input is the wrong historical edge, even after the
        # attacker recomputes both snapshot and immediate descriptor pins.
        source = m.sealed_bytes(m.bundle_path(P)/m._V5_TO_V7_SOURCE_CONTROL_NAME,
                                m._MAX_DOCUMENT_BYTES)
        original = producer._parse(source)
        wrong = producer.build_successor(original, source_sha=F,
            macro_root=original['ceo_ingress_app_macro_root'])
        wrong['terminal_return_socket_path'] = '/var/db/mastermind-agent-relay/socket/agent-relay.sock'
        stale = (json.dumps(wrong, sort_keys=True, indent=2, ensure_ascii=False)+'\n').encode()
        assert stale != (result/m._INSTALLED_PARENT_CONTROL_NAME).read_bytes()
        _rewrite(result/m._INSTALLED_PARENT_CONTROL_NAME, stale)
        forged = dict(descriptor, installed_parent_control_config_sha256=hashlib.sha256(stale).hexdigest())
        _rewrite(result/'descriptor.json',
                 (json.dumps(forged, sort_keys=True, indent=2)+'\n').encode())
        g_args.superseded_migration_preparation_descriptor_sha256 = m.digest(forged)
        assert m.descriptor_for(F) == forged
        assert m.sealed_bytes(result/m._INSTALLED_PARENT_CONTROL_NAME,
                              m._MAX_DOCUMENT_BYTES) == stale
    elif fault == 'current-config':
        _rewrite(m.SYSTEM_ROOT/'config/control.json',
                 (m.SYSTEM_ROOT/'config/control.json').read_bytes()+b' ')
        g_args.expected_installed_parent_control_config_sha256 = hashlib.sha256(
            (m.SYSTEM_ROOT/'config/control.json').read_bytes()).hexdigest()
    elif fault == 'install-refusal':
        current[0] = 'd'*40
    elif fault == 'parent-started':
        m.write_sealed(m.bundle_path(F)/'run-started.json',
                       {'schema_version': descriptor['schema_version']})
    elif fault == 'grandparent-pin':
        path = m.bundle_path(P)/m._V5_TO_V7_EVIDENCE_NAME
        material = m.sealed_json(path)
        material['chain']['tool_release']['sha'] = '4'*40
        _rewrite(path, (json.dumps(material, sort_keys=True, indent=2)+'\n').encode())
        assert m.sealed_json(path) == material
    else:
        (f.runtime_root.parent/'acceptance'/P).mkdir()
    expected = ({'installed-pin': 'installed preparation source config differs',
                 'old-snapshot': 'installed preparation source config differs',
                 'current-config': 'config or original root binding differs'}.get(fault))
    with pytest.raises((m.MaintenanceError, ValueError, OSError), match=expected):
        m.prepare(g_args)
    assert not m.bundle_path(G).exists()
    assert not list(m.bundle_path(G).parent.glob('.preparing-'+G+'-*'))


def test_late_installed_pin_mutation_keeps_only_the_private_candidate(tmp_path, monkeypatch):
    f = installed._installed_fixture(tmp_path, monkeypatch)
    result = m.prepare(f.new_args)
    current = [F]
    _strict_install(f, monkeypatch, current)
    _install_release(f, F)
    _stage_release(monkeypatch, G)
    g_args = _select_installed(f, G, F)
    real = m._requalify_unstarted_preproof_v5_to_v7
    def late(*args, **kwargs):
        value = real(*args, **kwargs)
        path = m.bundle_path(F)/m._INSTALLED_PARENT_CONTROL_NAME
        path.chmod(0o600); path.write_bytes(path.read_bytes()+b' '); path.chmod(0o400)
        return value
    monkeypatch.setattr(m, '_requalify_unstarted_preproof_v5_to_v7', late)
    with pytest.raises((m.MaintenanceError, ValueError, OSError)):
        m.prepare(g_args)
    assert not m.bundle_path(G).exists()
    assert list(m.bundle_path(G).parent.glob('.preparing-'+G+'-*'))


@pytest.mark.parametrize('fault', ['acceptance', 'partial'])
def test_cached_parent_rechecks_each_older_ancestor_state(tmp_path, monkeypatch, fault):
    f = installed._installed_fixture(tmp_path, monkeypatch)
    m.prepare(f.new_args)
    descriptor = m.descriptor_for(F)
    with m._UnstartedPreproofGuard() as guard:
        m._read_prepared_migration_parent(F, m.digest(descriptor), guard, installed=True)
        if fault == 'acceptance':
            (f.runtime_root.parent/'acceptance'/P).mkdir()
        else:
            (m.bundle_path(P).parent/('.preparing-'+P+'-late-foreign')).mkdir()
        with pytest.raises(m.MaintenanceError):
            m._read_prepared_migration_parent(F, m.digest(descriptor), guard, installed=True)


def test_cached_chain_cannot_skip_transitive_depth_budget(tmp_path, monkeypatch):
    f = installed._installed_fixture(tmp_path, monkeypatch)
    m.prepare(f.new_args)
    descriptor = m.descriptor_for(F)
    with m._UnstartedPreproofGuard() as guard:
        m._read_prepared_migration_parent(F, m.digest(descriptor), guard, installed=True)
        monkeypatch.setattr(m, '_MAX_SUPERSEDE_DEPTH', 2)
        with pytest.raises(m.MaintenanceError, match='too deep'):
            m._read_prepared_migration_parent_link(F, m.digest(descriptor), guard, ('7'*40,))


def test_prospective_successor_counts_toward_full_parent_budget(tmp_path, monkeypatch):
    f = installed._installed_fixture(tmp_path, monkeypatch)
    m.prepare(f.new_args)
    immediate = m.descriptor_for(F)
    proposed = dict(immediate, successor_sha=G,
        superseded_unstarted_migration_preparation_sha=F,
        superseded_migration_preparation_descriptor_sha256=m.digest(immediate))
    # Real F + original P consume two nodes. The distinct proposed G is the
    # third node even though it has not been published and has no directory.
    monkeypatch.setattr(m, '_MAX_SUPERSEDE_DEPTH', 2)
    with m._UnstartedPreproofGuard() as guard:
        with pytest.raises(m.MaintenanceError, match='too deep'):
            m._prepared_migration_parent(proposed, guard=guard)
    assert not m.bundle_path(G).exists()


def test_older_acceptance_absence_stays_held_through_final_read(tmp_path, monkeypatch):
    f = installed._installed_fixture(tmp_path, monkeypatch)
    m.prepare(f.new_args)
    descriptor = m.descriptor_for(F)
    real = m._require_runtime_acceptance_absent
    changed = []
    def late(path):
        real(path)
        if path.name == F and not changed:
            (f.runtime_root.parent/'acceptance'/P).mkdir()
            changed.append(P)
    monkeypatch.setattr(m, '_require_runtime_acceptance_absent', late)
    with m._UnstartedPreproofGuard() as guard:
        with pytest.raises(m.MaintenanceError):
            m._read_prepared_migration_parent(F, m.digest(descriptor), guard, installed=True)
    assert changed == [P]
