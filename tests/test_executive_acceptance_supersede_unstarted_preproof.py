"""One unstarted supersede_preproof_v1 preparation carries to a fresh release.

``supersede_unstarted_preproof_v1`` is the only admission that may select an
original ``supersede_preproof_v1`` release, and only while that selected
preparation is still untouched: exactly the six sealed preparation documents
(plus the legacy sealed SQLite pair where supported), the exact schema-only
preparing marker, no run marker, no carry receipt, and an absent Runtime
acceptance leaf. The real lineage walk continues through the selected
pre-proof descriptor's own interrupted prefix to the accepted ancestor with
the original evidence and canary propagation intact, a future accepted carry
validates the retained newtype lineage normally, and the incumbent
``supersede_unstarted_v1`` selector keeps refusing this shape.
"""
import argparse
import dataclasses
import hashlib
import json
import os
import shutil
import sqlite3
import socket
import subprocess
import getpass
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.executive_os import acceptance_maintenance as m
from tests.test_executive_acceptance_supersede_unstarted import (
    S, N, _fixture as unstarted_fixture, _rewrite,
)
from tests.test_executive_acceptance_supersede_preproof import (
    envelope, write_full_preproof_root,
)
from tests.test_executive_acceptance_maintenance_v2 import _terminal_fixture

# Captured before any test monkeypatches the owner: the real prior PASS chain
# walk, used to prove a future accepted carry re-enters the retained lineage.
_REAL_PRIOR_CARRY_MATERIAL = m.prior_carry_material

ACCEPTED = 'f'*40
DEEPER = S
MIDDLE = 'e'*40
SUCCESSOR = N


@pytest.fixture(autouse=True)
def _no_external_effects(monkeypatch):
    """Unit fixtures may not fall through into network, credentials or tools."""
    def forbidden(*args, **kwargs):
        raise AssertionError('external network/credential/process fallback in source fixture')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(os, 'system', forbidden)
    monkeypatch.setattr(getpass, 'getpass', forbidden)


def unstarted_preproof_fixture(tmp_path, monkeypatch):
    """Seal the middle unstarted ``supersede_preproof_v1`` preparation.

    The existing preproof fixture only yields a candidate; it never seals that
    candidate as an outer selected bundle. This fixture seals the middle
    six-entry preparation with the live envelope and no run marker or
    acceptance leaf, while the deeper selected prefix keeps its run marker,
    its eight pre-proof receipts and one probe, and the accepted chain.
    """
    _candidate, deeper, before, artifacts, canary, deeper_bundle, runtime = (
        unstarted_fixture(tmp_path, monkeypatch))
    deeper['predecessor_sha'] = ACCEPTED
    _rewrite(deeper_bundle/'descriptor.json', deeper)
    root = write_full_preproof_root(runtime, deeper, monkeypatch)
    evidence, live_envelope = m.preproof_evidence(DEEPER)
    middle_bundle = m.bundle_path(MIDDLE)
    middle_bundle.mkdir()
    shutil.copyfile(deeper_bundle/'prestate.sqlite3', middle_bundle/'prestate.sqlite3')
    (middle_bundle/'prestate.sqlite3').chmod(0o400)
    middle = dict(deeper, schema_version=m.SCHEMA_PREPROOF, successor_sha=MIDDLE,
                  interrupted_preproof_sha=DEEPER,
                  superseded_descriptor_sha256=m.digest(deeper),
                  preproof_evidence_sha256=evidence,
                  prior_canary_sha256=m.digest(live_envelope))
    for filename, value in [('descriptor.json', middle),
                            ('preparing.json', {'schema_version': m.SCHEMA_PREPROOF}),
                            ('baseline.json', before), ('inventory.json', artifacts),
                            ('prior-secret-canary.json', live_envelope)]:
        m.write_sealed(middle_bundle/filename, value, public=filename == 'descriptor.json')
    candidate = {key: value for key, value in middle.items()
                 if key not in {'interrupted_preproof_sha', 'preproof_evidence_sha256'}}
    candidate.update(schema_version=m.SCHEMA_UNSTARTED_PREPROOF, successor_sha=SUCCESSOR,
                     superseded_unstarted_preproof_sha=MIDDLE,
                     superseded_descriptor_sha256=m.digest(middle))
    return (candidate, middle, deeper, before, artifacts, canary, live_envelope,
            middle_bundle, deeper_bundle, root, runtime)


def test_walk_descends_through_the_selected_preproof_to_the_started_prefix(tmp_path, monkeypatch):
    (candidate, middle, deeper, before, artifacts, canary, live_envelope,
     middle_bundle, deeper_bundle, root, runtime) = unstarted_preproof_fixture(
        tmp_path, monkeypatch)
    paths = [*middle_bundle.iterdir(), *deeper_bundle.iterdir(), *root.iterdir()]
    original = {str(p): p.read_bytes() for p in paths}
    links = []
    real = m._validate_superseded_link

    def spy(descriptor, **kwargs):
        selected = real(descriptor, **kwargs)
        links.append((descriptor['schema_version'], selected['schema_version']))
        return selected

    monkeypatch.setattr(m, '_validate_superseded_link', spy)
    m.validate_superseded_binding(candidate, before=before, artifacts=artifacts,
                                  prior_canary=live_envelope)
    assert links == [(m.SCHEMA_UNSTARTED_PREPROOF, m.SCHEMA_PREPROOF),
                     (m.SCHEMA_PREPROOF, m.SCHEMA_V2)]
    assert original == {str(p): p.read_bytes() for p in paths}
    assert m.SCHEMA_UNSTARTED_PREPROOF in m._TERMINAL_CARRY_SCHEMAS
    # The selected preparation stays untouched: no marker, no carry, no leaf.
    assert not (middle_bundle/'run-started.json').exists()
    assert not (middle_bundle/'carry-forward.json').exists()
    assert not (runtime/'control'/'acceptance'/MIDDLE).exists()
    assert m.sealed_json(middle_bundle/'preparing.json') == {
        'schema_version': m.SCHEMA_PREPROOF}
    assert {p.name for p in middle_bundle.iterdir()} == {
        'descriptor.json', 'preparing.json', 'baseline.json', 'inventory.json',
        'prior-secret-canary.json', 'prestate.sqlite3'}


def test_new_descriptor_shape_is_closed_and_binds_distinct_releases(tmp_path, monkeypatch):
    (candidate, *_rest) = unstarted_preproof_fixture(tmp_path, monkeypatch)
    bundle = m.bundle_path(SUCCESSOR)
    bundle.mkdir()
    path = bundle/'descriptor.json'
    m.write_sealed(path, candidate, public=True)
    assert m.descriptor_for(SUCCESSOR) == candidate
    owner = object.__new__(m.Maintenance)
    owner.descriptor = candidate
    assert owner.predecessor_recovery_required is False
    assert m.recovery_permitted(None, 'old', SUCCESSOR, 'worker', 'proof') is False
    for mutation in [{'unexpected': True}, {'superseded_unstarted_preproof_sha': SUCCESSOR},
                     {'superseded_unstarted_preproof_sha': ACCEPTED},
                     {'superseded_unstarted_preproof_sha': 'invalid'},
                     {'superseded_unstarted_preproof_sha': 5},
                     {'superseded_descriptor_sha256': 'short'}]:
        _rewrite(path, dict(candidate, **mutation))
        with pytest.raises(m.MaintenanceError):
            m.descriptor_for(SUCCESSOR)


def test_incumbent_unstarted_mode_still_refuses_the_preproof_preparation(tmp_path, monkeypatch):
    (candidate, middle, deeper, before, artifacts, canary, live_envelope,
     middle_bundle, deeper_bundle, root, runtime) = unstarted_preproof_fixture(
        tmp_path, monkeypatch)
    incumbent = dict(candidate, schema_version=m.SCHEMA_SUPERSEDE,
                     superseded_unstarted_sha=MIDDLE,
                     superseded_descriptor_sha256=m.digest(middle))
    with pytest.raises(m.MaintenanceError,
                       match='superseded descriptor or accepted ancestor mismatch'):
        m.validate_superseded_binding(incumbent)


def test_only_the_original_preproof_schema_is_selectable(tmp_path, monkeypatch):
    (candidate, middle, deeper, before, artifacts, canary, live_envelope,
     middle_bundle, deeper_bundle, root, runtime) = unstarted_preproof_fixture(
        tmp_path, monkeypatch)
    nested_new = dict(candidate, successor_sha='1'*40)
    bundle = m.bundle_path('1'*40)
    bundle.mkdir()
    m.write_sealed(bundle/'descriptor.json', nested_new, public=True)
    nested_new_two = dict(nested_new, successor_sha='2'*40)
    bundle = m.bundle_path('2'*40)
    bundle.mkdir()
    m.write_sealed(bundle/'descriptor.json', nested_new_two, public=True)
    for selected_sha, selected_descriptor in [(DEEPER, deeper), ('1'*40, nested_new)]:
        attempt = dict(candidate, superseded_unstarted_preproof_sha=selected_sha,
                       superseded_descriptor_sha256=m.digest(selected_descriptor))
        with pytest.raises(m.MaintenanceError,
                           match='superseded descriptor or accepted ancestor mismatch'):
            m.validate_superseded_binding(attempt)
    preproof_attempt = dict(candidate, schema_version=m.SCHEMA_PREPROOF,
                            interrupted_preproof_sha='2'*40,
                            superseded_descriptor_sha256=m.digest(nested_new_two))
    with pytest.raises(m.MaintenanceError,
                       match='superseded descriptor or accepted ancestor mismatch'):
        m.validate_superseded_binding(preproof_attempt)


_SHARED_FIELD_FAULTS = {
    'root': ('root_job_id', 'foreign'),
    'root-identity': ('root_identity_sha256', '0'*64),
    'root-event': ('root_event_sha256', '0'*64),
    'ancestor': ('predecessor_sha', '9'*40),
    'frozen-base': ('frozen_base_sha', 'f'*40),
    'prior-descriptor': ('prior_descriptor_sha256', '0'*64),
    'prior-carry': ('prior_carry_sha256', '0'*64),
    'prior-summary': ('prior_summary_sha256', '0'*64),
    'template': ('template_proof_job_id', 'JOB-foreign'),
    'template-digest': ('template_proof_job_sha256', '0'*64),
    'terminal': ('terminal_job_id', 'JOB-foreign'),
    'terminal-attempt': ('terminal_attempt_id', 'ATT-foreign'),
    'terminal-marker': ('terminal_marker_event_sha256', '0'*64),
    'terminal-state': ('terminal_state_sha256', '0'*64),
    'assignment': ('assignment_seal_sha256', '0'*64),
    'quota': ('predecessor_quota_sha256', '0'*64),
    'baseline-field': ('baseline_sha256', '0'*64),
    'inventory-field': ('inventory_sha256', '0'*64),
    'canary-field': ('prior_canary_sha256', '0'*64),
}


def _mutate_bundle(path, value):
    _rewrite(path, value)


@pytest.mark.parametrize('fault', [
    *_SHARED_FIELD_FAULTS,
    'selected-baseline', 'selected-inventory', 'selected-canary', 'selected-backup',
    'selected-backup-mode', 'selected-backup-link', 'selected-preparing',
    'selected-marker', 'selected-carry', 'selected-extra', 'selected-partial',
    'selected-baseline-missing', 'selected-baseline-symlink', 'selected-prestate-missing',
    'selected-schema', 'selected-digest', 'selected-preparing-schema',
    'leaf-file', 'leaf-empty', 'leaf-dangling', 'leaf-symlink', 'leaf-denied',
    'deeper-evidence', 'deeper-canary', 'deeper-marker',
    'live-baseline', 'live-inventory', 'live-canary', 'cycle', 'depth',
])
def test_refuses_drift_or_any_later_selected_acceptance_state(tmp_path, monkeypatch, fault):
    (candidate, middle, deeper, before, artifacts, canary, live_envelope,
     middle_bundle, deeper_bundle, root, runtime) = unstarted_preproof_fixture(
        tmp_path, monkeypatch)
    if fault in _SHARED_FIELD_FAULTS:
        key, value = _SHARED_FIELD_FAULTS[fault]
        candidate[key] = value
    elif fault == 'selected-baseline':
        _mutate_bundle(middle_bundle/'baseline.json', {'changed': True})
    elif fault == 'selected-inventory':
        _mutate_bundle(middle_bundle/'inventory.json', {'changed': True})
    elif fault == 'selected-canary':
        _mutate_bundle(middle_bundle/'prior-secret-canary.json', {'passed': False})
    elif fault == 'selected-backup':
        (middle_bundle/'prestate.sqlite3').chmod(0o600)
        with sqlite3.connect(middle_bundle/'prestate.sqlite3') as conn:
            conn.execute('INSERT INTO schema_migrations VALUES(4)')
        (middle_bundle/'prestate.sqlite3').chmod(0o400)
    elif fault == 'selected-backup-mode':
        (middle_bundle/'prestate.sqlite3').chmod(0o600)
    elif fault == 'selected-backup-link':
        original = middle_bundle/'prestate.sqlite3'
        target = tmp_path/'other.sqlite3'
        original.rename(target)
        original.symlink_to(target)
    elif fault == 'selected-preparing':
        _mutate_bundle(middle_bundle/'preparing.json', {'schema_version': m.SCHEMA_SUPERSEDE})
    elif fault == 'selected-preparing-schema':
        _mutate_bundle(middle_bundle/'preparing.json', {'schema_version': m.SCHEMA})
    elif fault == 'selected-marker':
        m.write_sealed(middle_bundle/'run-started.json', {'schema_version': m.SCHEMA_PREPROOF})
    elif fault == 'selected-carry':
        m.write_sealed(middle_bundle/'carry-forward.json', {'passed': True})
    elif fault == 'selected-extra':
        m.write_sealed(middle_bundle/'unknown.json', {})
    elif fault == 'selected-partial':
        (middle_bundle/'unfinished').mkdir()
    elif fault == 'selected-baseline-missing':
        (middle_bundle/'baseline.json').unlink()
    elif fault == 'selected-baseline-symlink':
        original = middle_bundle/'baseline.json'
        target = tmp_path/'baseline-elsewhere.json'
        original.rename(target)
        original.symlink_to(target)
    elif fault == 'selected-prestate-missing':
        (middle_bundle/'prestate.sqlite3').unlink()
    elif fault == 'selected-schema':
        _mutate_bundle(middle_bundle/'descriptor.json',
                       dict(middle, schema_version=m.SCHEMA_SUPERSEDE))
    elif fault == 'selected-digest':
        candidate['superseded_descriptor_sha256'] = '0'*64
    elif fault in {'leaf-file', 'leaf-empty', 'leaf-dangling', 'leaf-symlink'}:
        leaf = runtime/'control'/'acceptance'/MIDDLE
        if fault == 'leaf-file':
            leaf.write_text('{}')
        elif fault == 'leaf-empty':
            leaf.mkdir()
        elif fault == 'leaf-dangling':
            leaf.symlink_to(tmp_path/'absent-leaf')
        else:
            target = tmp_path/'leaf-target'
            target.mkdir()
            leaf.symlink_to(target, target_is_directory=True)
    elif fault == 'leaf-denied':
        leaf = runtime/'control'/'acceptance'/MIDDLE
        original_lstat = Path.lstat

        def denied(path, *args, **kwargs):
            if path == leaf:
                raise PermissionError('protected read denied')
            return original_lstat(path, *args, **kwargs)

        monkeypatch.setattr(Path, 'lstat', denied)
    elif fault == 'deeper-evidence':
        receipt = root/'awaiting-canary-status.json'
        value = json.loads(receipt.read_text())
        value['result']['control_pid'] = 4242
        _mutate_bundle(receipt, value)
    elif fault == 'deeper-canary':
        receipt = root/'secret-canary-envelope.json'
        value = json.loads(receipt.read_text())
        value['control_environment_probe'] = {'pid': 4242}
        _mutate_bundle(receipt, value)
        middle = dict(middle, preproof_evidence_sha256=m.preproof_evidence(DEEPER)[0])
        _mutate_bundle(middle_bundle/'descriptor.json', middle)
        candidate['superseded_descriptor_sha256'] = m.digest(middle)
    elif fault == 'deeper-marker':
        _mutate_bundle(deeper_bundle/'run-started.json',
                       {'schema_version': m.SCHEMA_V2, 'descriptor_sha256': '0'*64})
    elif fault == 'live-baseline':
        before['changed'] = True
    elif fault == 'live-inventory':
        artifacts['changed'] = True
    elif fault == 'live-canary':
        live_envelope = {'passed': True, 'drift': True}
    elif fault == 'cycle':
        middle = dict(middle, interrupted_preproof_sha=MIDDLE)
        _mutate_bundle(middle_bundle/'descriptor.json', middle)
        candidate['superseded_descriptor_sha256'] = m.digest(middle)
    elif fault == 'depth':
        monkeypatch.setattr(m, '_MAX_SUPERSEDE_DEPTH', 2)
    with pytest.raises((m.MaintenanceError, OSError)):
        m.validate_superseded_binding(candidate, before=before, artifacts=artifacts,
                                      prior_canary=live_envelope)


def _prepare_fixture(tmp_path, monkeypatch):
    """The real producer shape: actual Runtime, SQLite prestate and inventory.

    The inherited fixture has a real v5 Runtime but synthetic accepted-ancestor,
    proof-template and assignment inputs. Host Root/platform/stopped/custody
    seams are also inert. This proves producer/consumer traversal, not actual
    host authority or a live historical seal. The deeper selected
    prefix and the accepted ancestor are sealed maintenance bundles on disk;
    the middle supersede_preproof_v1 preparation is unstarted.
    """
    from ops.executive_os import autonomy_control as ac
    fixture_root = tmp_path/'owner'
    fixture_root.mkdir()
    runtime, root, before, config, prior, material, proof, _, _ = _terminal_fixture(
        fixture_root, monkeypatch)
    proof.constraints['base_sha'] = ACCEPTED
    proof.to_dict = lambda: {'job_id': proof.job_id, 'base_sha': ACCEPTED}
    root = dataclasses.replace(root, constraints={**root.constraints, 'operator_harness_armed': False})
    prior['root_identity_sha256'] = m.root_identity(root)
    original = runtime.jobs.get_job
    monkeypatch.setattr(runtime.jobs, 'get_job', lambda job: root if job == root.job_id else original(job))
    from control_plane.executive_runtime import Runtime
    monkeypatch.setattr(Runtime, 'at', lambda *args, **kwargs: runtime)
    system = tmp_path/'system'
    (system/'config').mkdir(parents=True)
    monkeypatch.setattr(m, 'SYSTEM_ROOT', system)
    monkeypatch.setattr(m, '_TRUSTED_UID', os.getuid())
    monkeypatch.setattr(m, '_TRUSTED_GID', os.getgid())
    monkeypatch.setattr(m, '_sealed_ancestors', lambda path: [])
    monkeypatch.setattr(m, 'has_macos_acl', lambda *args, **kwargs: False)
    monkeypatch.setattr(m.os, 'geteuid', lambda: 0)
    # Keep the ACL observer on its actual host while simulating the Mac entry gate.
    monkeypatch.setattr(m, 'sys', SimpleNamespace(platform='darwin'))
    monkeypatch.setattr(m, 'require_stopped', lambda: None)
    runtime_root = fixture_root/'runtime'
    (runtime_root/'control'/'acceptance').mkdir(parents=True)
    monkeypatch.setattr(ac, 'RUNTIME_ROOT', runtime_root)
    config.update(runtime_root=str(runtime_root), proof_base_sha=MIDDLE,
                  ceo_submit_armed=False, coo_autonomy_armed=False, coo_operator_harness_armed=False)
    for key in ('proof_workspace_root', 'worker_runs_root', 'receipts_root', 'backup_root'):
        path = tmp_path/'artifacts'/key
        path.mkdir(parents=True)
        config[key] = str(path)
    canary_fixtures = runtime_root.parent.parent/'canary-fixtures'
    canary_fixtures.mkdir(exist_ok=True)
    live_envelope = envelope()
    canary_path = tmp_path/'prior-canary.json'
    canary_path.write_text(json.dumps(live_envelope))
    config['secret_canary_receipt_path'] = str(canary_path)
    (system/'config'/'control.json').write_text(json.dumps(config))
    (system/'config'/'worker-codex.json').write_text('{"operator_harness_armed":false}')
    artifacts = m.inventory([Path(config[key]) for key in
        ('proof_workspace_root', 'worker_runs_root', 'receipts_root', 'backup_root')] + [canary_fixtures])
    # The accepted ancestor is a real sealed V1 maintenance bundle; the whole
    # selected lineage binds its prior PASS material instead of loose digests.
    ancestor = dict(schema_version=m.SCHEMA, predecessor_sha='a'*40, successor_sha=ACCEPTED,
                    root_job_id=root.job_id, root_identity_sha256=prior['root_identity_sha256'],
                    root_event_id=prior['root_event_id'], root_event_sha256=prior['root_event_sha256'],
                    recovery_job_id=proof.job_id, recovery_attempt_id='ATT-ancestor',
                    recovery_job_sha256='2'*64, worker_id=config['worker_id'],
                    quota_class=config['quota_class'], baseline_sha256='3'*64,
                    backup_sha256='4'*64, inventory_sha256='5'*64, prior_canary_sha256='6'*64)
    ancestor_summary = b'accepted-ancestor-summary'
    ancestor_material = {
        'prior_descriptor_sha256': m.digest(ancestor),
        'prior_carry_sha256': m.digest(dict(
            schema_version=m.SCHEMA, passed=True, baseline_preserved=True,
            descriptor_sha256=m.digest(ancestor),
            acceptance_summary_sha256=hashlib.sha256(ancestor_summary).hexdigest())),
        'prior_summary_sha256': hashlib.sha256(ancestor_summary).hexdigest(),
        'frozen_base_sha': ancestor['predecessor_sha'],
    }
    ancestor_bundle = m.bundle_path(ACCEPTED)
    ancestor_bundle.mkdir(parents=True)
    m.write_sealed(ancestor_bundle/'descriptor.json', ancestor, public=True)
    m.write_sealed(ancestor_bundle/'carry-forward.json', dict(
        schema_version=m.SCHEMA, passed=True, baseline_preserved=True,
        descriptor_sha256=m.digest(ancestor),
        acceptance_summary_sha256=hashlib.sha256(ancestor_summary).hexdigest()))
    # Keep the terminal-carry material bound to the sealed ancestor on every
    # dispatch that the existing fixture stubs, so the published descriptor
    # and the real future carry walk read the same prior PASS chain.
    monkeypatch.setattr(m, 'prior_carry_material', lambda sha, **kwargs: (
        prior, {'success_job_id': proof.job_id}, ancestor_material))
    _proof, fields = m.terminal_carry_fields(runtime, root, config, before, ACCEPTED)
    deeper_bundle = m.bundle_path(DEEPER)
    deeper_bundle.mkdir(parents=True)
    with sqlite3.connect(runtime.store.path) as source, sqlite3.connect(deeper_bundle/'prestate.sqlite3') as dest:
        source.backup(dest)
    (deeper_bundle/'prestate.sqlite3').chmod(0o400)
    prior_canary = {'passed': True, 'generation': 'prior'}
    deeper = dict(schema_version=m.SCHEMA_V2, predecessor_sha=ACCEPTED, successor_sha=DEEPER,
                  root_job_id=root.job_id, root_identity_sha256=m.root_identity(root),
                  root_event_id=prior['root_event_id'], root_event_sha256=prior['root_event_sha256'],
                  worker_id=config['worker_id'], quota_class=config['quota_class'],
                  baseline_sha256=m.digest(before), inventory_sha256=m.digest(artifacts),
                  prior_canary_sha256=m.digest(prior_canary),
                  backup_sha256=m._file_digest(deeper_bundle/'prestate.sqlite3'), **fields)
    for filename, value in [('descriptor.json', deeper), ('preparing.json', {'schema_version': m.SCHEMA_V2}),
                            ('baseline.json', before), ('inventory.json', artifacts),
                            ('prior-secret-canary.json', prior_canary)]:
        m.write_sealed(deeper_bundle/filename, value, public=filename == 'descriptor.json')
    write_full_preproof_root(runtime_root, deeper, monkeypatch)
    evidence, read_envelope = m.preproof_evidence(DEEPER)
    assert read_envelope == live_envelope
    middle_bundle = m.bundle_path(MIDDLE)
    middle_bundle.mkdir()
    with sqlite3.connect(runtime.store.path) as source, sqlite3.connect(middle_bundle/'prestate.sqlite3') as dest:
        source.backup(dest)
    (middle_bundle/'prestate.sqlite3').chmod(0o400)
    middle = dict(deeper, schema_version=m.SCHEMA_PREPROOF, successor_sha=MIDDLE,
                  interrupted_preproof_sha=DEEPER,
                  superseded_descriptor_sha256=m.digest(deeper),
                  preproof_evidence_sha256=evidence,
                  prior_canary_sha256=m.digest(live_envelope))
    for filename, value in [('descriptor.json', middle), ('preparing.json', {'schema_version': m.SCHEMA_PREPROOF}),
                            ('baseline.json', before), ('inventory.json', artifacts),
                            ('prior-secret-canary.json', live_envelope)]:
        m.write_sealed(middle_bundle/filename, value, public=filename == 'descriptor.json')
    return SimpleNamespace(
        runtime=runtime, root=root, before=before, config=config, prior=prior,
        material=ancestor_material, proof=proof, deeper=deeper, middle=middle,
        ancestor=ancestor, ancestor_material=ancestor_material,
        ancestor_summary=ancestor_summary, deeper_bundle=deeper_bundle,
        middle_bundle=middle_bundle, live_envelope=live_envelope,
        canary_path=canary_path, canary_fixtures=canary_fixtures,
        runtime_root=runtime_root)


def _prepared(tmp_path, monkeypatch):
    """Drive the actual prepare() and prove the published newtype descriptor."""
    f = _prepare_fixture(tmp_path, monkeypatch)
    middle_originals = {p.name: p.read_bytes() for p in f.middle_bundle.iterdir()}
    deeper_originals = {p.name: p.read_bytes() for p in f.deeper_bundle.iterdir()}
    args = argparse.Namespace(predecessor_sha=ACCEPTED, successor_sha=SUCCESSOR,
                              root_job_id=f.root.job_id, recovery_job_id=None,
                              recovery_attempt_id=None, carry_terminal_dispatch=True,
                              supersede_unstarted_sha=None, supersede_prejob_sha=None,
                              supersede_preproof_sha=None,
                              supersede_unstarted_preproof_sha=MIDDLE,
                              superseded_descriptor_sha256=m.digest(f.middle))
    result = m.prepare(args)
    d = m.descriptor_for(SUCCESSOR)
    assert result == m.bundle_path(SUCCESSOR)
    assert d['schema_version'] == m.SCHEMA_UNSTARTED_PREPROOF
    assert d['superseded_unstarted_preproof_sha'] == MIDDLE
    assert d['superseded_descriptor_sha256'] == m.digest(f.middle)
    assert d['predecessor_sha'] == ACCEPTED
    assert d['prior_canary_sha256'] == m.digest(f.live_envelope)
    assert d['baseline_sha256'] == f.middle['baseline_sha256']
    assert d['inventory_sha256'] == f.middle['inventory_sha256']
    assert d['template_proof_job_id'] == f.proof.job_id and d['frozen_base_sha'] == 'a'*40
    for key in (m._DESCRIPTOR_V2_KEYS - m._DESCRIPTOR_KEYS
                - {'schema_version', 'successor_sha', 'backup_sha256'}):
        assert d[key] == f.middle[key]
    assert {p.name: p.read_bytes() for p in f.middle_bundle.iterdir()} == middle_originals
    assert {p.name: p.read_bytes() for p in f.deeper_bundle.iterdir()} == deeper_originals
    assert m.snapshot(f.runtime.store.path) == f.before
    assert not (result/'run-started.json').exists()
    assert not (f.middle_bundle/'carry-forward.json').exists()
    assert not (f.runtime_root/'control'/'acceptance'/MIDDLE).exists()
    assert {p.name for p in result.iterdir()} == {
        'descriptor.json', 'preparing.json', 'baseline.json', 'inventory.json',
        'prior-secret-canary.json', 'prestate.sqlite3'}
    assert m.sealed_json(result/'preparing.json') == {
        'schema_version': m.SCHEMA_UNSTARTED_PREPROOF}
    return f, d, result


def test_preparation_publishes_one_new_descriptor_without_modifying_selected(tmp_path, monkeypatch):
    _prepared(tmp_path, monkeypatch)


def test_acceptance_revalidates_the_selected_preparation_before_the_marker(tmp_path, monkeypatch):
    f, d, result = _prepared(tmp_path, monkeypatch)
    middle_originals = {p.name: p.read_bytes() for p in f.middle_bundle.iterdir()}
    deeper_originals = {p.name: p.read_bytes() for p in f.deeper_bundle.iterdir()}
    owner = m.Maintenance(SUCCESSOR, m.digest(d), f.config)
    assert owner.predecessor_recovery_required is False
    assert m.recovery_permitted(None, 'old', SUCCESSOR, 'worker', 'proof') is False
    assert m.sealed_json(result/'run-started.json') == {
        'schema_version': m.SCHEMA_UNSTARTED_PREPROOF, 'descriptor_sha256': m.digest(d)}
    assert {p.name: p.read_bytes() for p in f.middle_bundle.iterdir()} == middle_originals
    assert {p.name: p.read_bytes() for p in f.deeper_bundle.iterdir()} == deeper_originals
    assert m.snapshot(f.runtime.store.path) == f.before
    # The marker is exclusive: a second runmarker attempt cannot rewrite it.
    with pytest.raises(FileExistsError):
        m.Maintenance(SUCCESSOR, m.digest(d), f.config)


@pytest.mark.parametrize('fault', ['selected-baseline', 'selected-evidence', 'selected-leaf'])
def test_acceptance_refuses_selected_drift_before_any_runmarker(tmp_path, monkeypatch, fault):
    f, d, result = _prepared(tmp_path, monkeypatch)
    if fault == 'selected-baseline':
        _rewrite(f.middle_bundle/'baseline.json', {'drift': True})
    elif fault == 'selected-evidence':
        receipt = f.runtime_root/'control'/'acceptance'/DEEPER/'failure-control-status.json'
        _rewrite(receipt, {'ok': False, 'result': {'service_state': 'QUARANTINED', 'drift': True}})
    else:
        (f.runtime_root/'control'/'acceptance'/MIDDLE).mkdir()
    with pytest.raises(m.MaintenanceError):
        m.Maintenance(SUCCESSOR, m.digest(d), f.config)
    assert not (result/'run-started.json').exists()


def test_future_accepted_carry_validates_the_retained_newtype_lineage(tmp_path, monkeypatch):
    f, d, result = _prepared(tmp_path, monkeypatch)
    future_sha = '1'*40
    summaries = {
        ACCEPTED: ({'success_job_id': f.proof.job_id}, f.ancestor_summary),
        SUCCESSOR: ({'success_job_id': f.proof.job_id}, b'future-acceptance-summary'),
    }
    monkeypatch.setattr(m, 'summary_document', lambda sha: summaries[sha])
    monkeypatch.setattr(m, 'prior_carry_material', _REAL_PRIOR_CARRY_MATERIAL)
    m.write_sealed(result/'carry-forward.json', dict(
        schema_version=m.SCHEMA_UNSTARTED_PREPROOF, passed=True, baseline_preserved=True,
        descriptor_sha256=m.digest(d),
        acceptance_summary_sha256=hashlib.sha256(summaries[SUCCESSOR][1]).hexdigest()), public=True)
    prior_descriptor, summary, material = m.prior_carry_material(SUCCESSOR)
    assert prior_descriptor == d and summary == summaries[SUCCESSOR][0]
    assert material['prior_descriptor_sha256'] == m.digest(d)
    assert material['frozen_base_sha'] == 'a'*40
    future = {key: value for key, value in d.items()
              if key not in {'superseded_unstarted_preproof_sha', 'superseded_descriptor_sha256'}}
    future.update(schema_version=m.SCHEMA_V2, predecessor_sha=SUCCESSOR,
                  successor_sha=future_sha, **material)
    future_bundle = m.bundle_path(future_sha)
    future_bundle.mkdir()
    m.write_sealed(future_bundle/'descriptor.json', future, public=True)
    walks = []
    real = m.validate_superseded_binding

    def spy(descriptor, **kwargs):
        walks.append((descriptor['schema_version'], kwargs.get('historical', False)))
        return real(descriptor, **kwargs)

    monkeypatch.setattr(m, 'validate_superseded_binding', spy)
    m.validate_prior_carry_binding(future)
    assert walks == [(m.SCHEMA_UNSTARTED_PREPROOF, True)]
    # The walk genuinely descended into the retained lineage: deeper drift
    # in the unstarted selected preparation refuses the future carry too.
    _rewrite(f.middle_bundle/'baseline.json', {'drift': True})
    with pytest.raises(m.MaintenanceError, match='superseded sealed baseline drifted'):
        m.validate_prior_carry_binding(future)


@pytest.mark.parametrize('fault', ['selected-started', 'selected-leaf', 'selected-extra',
                                   'selected-baseline', 'selected-carry', 'live-inventory',
                                   'live-canary', 'wrong-digest', 'wrong-schema-selected',
                                   'mixed-selector', 'recovery-selector', 'no-terminal'])
def test_prepare_refuses_before_publication_and_leaves_no_partial_state(tmp_path, monkeypatch, fault):
    f = _prepare_fixture(tmp_path, monkeypatch)
    middle_originals = {p.name: p.read_bytes() for p in f.middle_bundle.iterdir()}
    deeper_originals = {p.name: p.read_bytes() for p in f.deeper_bundle.iterdir()}
    args = argparse.Namespace(predecessor_sha=ACCEPTED, successor_sha=SUCCESSOR,
                              root_job_id=f.root.job_id, recovery_job_id=None,
                              recovery_attempt_id=None, carry_terminal_dispatch=True,
                              supersede_unstarted_sha=None, supersede_prejob_sha=None,
                              supersede_preproof_sha=None,
                              supersede_unstarted_preproof_sha=MIDDLE,
                              superseded_descriptor_sha256=m.digest(f.middle))
    if fault == 'selected-started':
        m.write_sealed(f.middle_bundle/'run-started.json', {'schema_version': m.SCHEMA_PREPROOF})
    elif fault == 'selected-leaf':
        (f.runtime_root/'control'/'acceptance'/MIDDLE).mkdir()
    elif fault == 'selected-extra':
        m.write_sealed(f.middle_bundle/'unknown.json', {})
    elif fault == 'selected-baseline':
        _rewrite(f.middle_bundle/'baseline.json', {'drift': True})
    elif fault == 'selected-carry':
        m.write_sealed(f.middle_bundle/'carry-forward.json', {'passed': True})
    elif fault == 'live-inventory':
        (f.canary_fixtures/'drift.bin').write_bytes(b'drift')
    elif fault == 'live-canary':
        f.canary_path.write_text(json.dumps({'passed': True, 'drift': True}))
    elif fault == 'wrong-digest':
        args.superseded_descriptor_sha256 = '0'*64
    elif fault == 'wrong-schema-selected':
        args.supersede_unstarted_preproof_sha = DEEPER
        args.superseded_descriptor_sha256 = m.digest(f.deeper)
    elif fault == 'mixed-selector':
        args.supersede_unstarted_sha = MIDDLE
    elif fault == 'recovery-selector':
        args.recovery_job_id = 'JOB-old'
        args.recovery_attempt_id = 'ATT-old'
    else:
        args.carry_terminal_dispatch = False
    # The test injected the fault. The owner must preserve that observed state,
    # rather than undo it or mutate any other selected/deeper bytes.
    middle_after_fault = {p.name: p.read_bytes() for p in f.middle_bundle.iterdir()}
    deeper_after_fault = {p.name: p.read_bytes() for p in f.deeper_bundle.iterdir()}
    with pytest.raises((m.MaintenanceError, OSError)):
        m.prepare(args)
    assert not m.bundle_path(SUCCESSOR).exists()
    assert not list(m.bundle_path(SUCCESSOR).parent.glob('.preparing-*'))
    assert m.snapshot(f.runtime.store.path) == f.before
    assert {p.name: p.read_bytes() for p in f.middle_bundle.iterdir()} == middle_after_fault
    assert {p.name: p.read_bytes() for p in f.deeper_bundle.iterdir()} == deeper_after_fault


def test_prepare_selector_gate_matches_the_exact_installed_release(tmp_path, monkeypatch):
    f = _prepare_fixture(tmp_path, monkeypatch)
    # The selection is bound to the exact installed proof base; a different
    # installed release refuses before any Runtime read or publication.
    f.config['proof_base_sha'] = '7'*40
    (m.SYSTEM_ROOT/'config'/'control.json').write_text(json.dumps(f.config))
    args = argparse.Namespace(predecessor_sha=ACCEPTED, successor_sha=SUCCESSOR,
                              root_job_id=f.root.job_id, recovery_job_id=None,
                              recovery_attempt_id=None, carry_terminal_dispatch=True,
                              supersede_unstarted_sha=None, supersede_prejob_sha=None,
                              supersede_preproof_sha=None,
                              supersede_unstarted_preproof_sha=MIDDLE,
                              superseded_descriptor_sha256=m.digest(f.middle))
    def forbidden(*args, **kwargs):
        raise AssertionError('uninstalled selection reached the runtime read')
    monkeypatch.setattr(m, 'snapshot', forbidden)
    with pytest.raises(m.MaintenanceError, match='predecessor differs from installed release'):
        m.prepare(args)
    assert not m.bundle_path(SUCCESSOR).exists()



def _new_args(f):
    return argparse.Namespace(predecessor_sha=ACCEPTED, successor_sha=SUCCESSOR,
        root_job_id=f.root.job_id, recovery_job_id=None, recovery_attempt_id=None,
        carry_terminal_dispatch=True, supersede_unstarted_sha=None,
        supersede_prejob_sha=None, supersede_preproof_sha=None,
        supersede_unstarted_preproof_sha=MIDDLE,
        superseded_descriptor_sha256=m.digest(f.middle))


def _boundary_mutation(f, fault):
    if fault == 'selected-replace':
        path = f.middle_bundle/'descriptor.json'
    elif fault == 'deeper-replace':
        path = f.deeper_bundle/'baseline.json'
    elif fault == 'receipt-replace':
        path = f.runtime_root/'control'/'acceptance'/DEEPER/'protected-group-membership.json'
    elif fault == 'canary-replace':
        path = f.canary_path
    elif fault == 'acceptance-leaf':
        (f.runtime_root/'control'/'acceptance'/MIDDLE).mkdir()
        return
    elif fault == 'inventory-extra':
        (Path(f.config['receipts_root'])/'late').write_text('fixture')
        return
    elif fault == 'database':
        with sqlite3.connect(f.runtime.store.path) as connection:
            connection.execute("UPDATE worker_quota_classes SET fence_counter=fence_counter+1")
        return
    else:
        raise AssertionError(fault)
    replacement = path.with_name(path.name+'.replacement')
    replacement.write_bytes(path.read_bytes())
    replacement.chmod(path.stat().st_mode & 0o777)
    os.replace(replacement, path)


@pytest.mark.parametrize('fault', ['selected-replace', 'deeper-replace',
    'receipt-replace', 'canary-replace', 'acceptance-leaf', 'inventory-extra', 'database'])
def test_prepare_refuses_late_drift_after_durable_candidate(tmp_path, monkeypatch, fault):
    f = _prepare_fixture(tmp_path, monkeypatch)
    original = m.write_sealed
    def write_then_mutate(path, value, **kwargs):
        original(path, value, **kwargs)
        if path.name == 'descriptor.json' and path.parent.name.startswith('.preparing-'):
            _boundary_mutation(f, fault)
    monkeypatch.setattr(m, 'write_sealed', write_then_mutate)
    with pytest.raises(m.MaintenanceError):
        m.prepare(_new_args(f))
    assert not m.bundle_path(SUCCESSOR).exists()
    assert not (f.middle_bundle/'run-started.json').exists()
    # Failed private preparation is retained; no automatic cleanup/retry.
    assert list(f.middle_bundle.parent.glob('.preparing-'+SUCCESSOR+'-*'))


@pytest.mark.parametrize('fault', ['selected-replace', 'deeper-replace',
    'receipt-replace', 'canary-replace', 'acceptance-leaf', 'inventory-extra', 'database'])
def test_maintenance_refuses_late_drift_after_terminal_read(tmp_path, monkeypatch, fault):
    f, descriptor, bundle = _prepared(tmp_path, monkeypatch)
    original = m.terminal_carry_fields
    injected = False
    def terminal_then_mutate(*args, **kwargs):
        nonlocal injected
        result = original(*args, **kwargs)
        if not injected:
            injected = True
            _boundary_mutation(f, fault)
        return result
    monkeypatch.setattr(m, 'terminal_carry_fields', terminal_then_mutate)
    with pytest.raises(m.MaintenanceError):
        m.Maintenance(SUCCESSOR, m.digest(descriptor), f.config)
    assert injected
    assert not (bundle/'run-started.json').exists()


@pytest.mark.parametrize('fault', ['database', 'inventory-extra', 'canary-replace', 'deeper-replace'])
def test_marker_refuses_mutation_in_final_terminal_validation(tmp_path, monkeypatch, fault):
    f, descriptor, bundle = _prepared(tmp_path, monkeypatch)
    original = m.terminal_carry_fields
    calls = 0
    def terminal_then_mutate(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 2:
            _boundary_mutation(f, fault)
        return result
    monkeypatch.setattr(m, 'terminal_carry_fields', terminal_then_mutate)
    with pytest.raises(m.MaintenanceError):
        m.Maintenance(SUCCESSOR, m.digest(descriptor), f.config)
    assert calls == 2
    assert not (bundle/'run-started.json').exists()


def test_guard_retains_large_inventory_and_binary_backup_without_reading(tmp_path, monkeypatch):
    bundle = tmp_path/'bundle'
    bundle.mkdir()
    # Realistic shape: >16MiB inventory and binary SQLite-sized backup.
    with (bundle/'inventory.json').open('wb') as stream:
        stream.truncate(35_373_272)
    with (bundle/'prestate.sqlite3').open('wb') as stream:
        stream.write(b'not JSON\x00')
        stream.truncate(1_667_072)
    def no_payload(*args, **kwargs):
        raise AssertionError('identity guard attempted payload I/O')
    monkeypatch.setattr(os, 'read', no_payload)
    with m._UnstartedPreproofGuard() as guard:
        guard.tree(bundle)
        guard.check()
        descriptors = [record[0] for record in guard.nodes.values()]
        assert len(descriptors) >= 3
    for fd in descriptors:
        with pytest.raises(OSError):
            os.fstat(fd)


@pytest.mark.parametrize('fault', ['leaf-replace', 'extra', 'ancestor-replace', 'symlink-ancestor'])
def test_guard_refuses_identity_or_namespace_replacement_and_closes(tmp_path, fault):
    ancestor = tmp_path/'anchor'
    bundle = ancestor/'bundle'
    bundle.mkdir(parents=True)
    leaf = bundle/'descriptor.json'
    leaf.write_bytes(b'fixture')
    descriptors = []
    with pytest.raises((m.MaintenanceError, OSError)):
        with m._UnstartedPreproofGuard() as guard:
            guard.tree(bundle)
            descriptors = [record[0] for record in guard.nodes.values()]
            if fault == 'leaf-replace':
                replacement = tmp_path/'replacement'
                replacement.write_bytes(leaf.read_bytes())
                os.replace(replacement, leaf)
            elif fault == 'extra':
                (bundle/'extra').write_bytes(b'fixture')
            else:
                ancestor.rename(tmp_path/'retained-anchor')
                if fault == 'ancestor-replace':
                    bundle.mkdir(parents=True)
                    leaf.write_bytes(b'fixture')
                else:
                    ancestor.symlink_to(tmp_path/'retained-anchor', target_is_directory=True)
            guard.check()
    assert descriptors
    for fd in descriptors:
        with pytest.raises(OSError):
            os.fstat(fd)


@pytest.mark.parametrize('kind', ['fifo', 'symlink', 'directory'])
def test_guard_refuses_special_entries_without_payload_read(tmp_path, monkeypatch, kind):
    bundle = tmp_path/'bundle'
    bundle.mkdir()
    leaf = bundle/'descriptor.json'
    if kind == 'fifo':
        os.mkfifo(leaf)
    elif kind == 'symlink':
        foreign = tmp_path/'foreign'
        foreign.write_bytes(b'never read')
        leaf.symlink_to(foreign)
    else:
        leaf.mkdir()
    def no_payload(*args, **kwargs):
        raise AssertionError('identity guard attempted payload I/O')
    monkeypatch.setattr(os, 'read', no_payload)
    descriptors = []
    with pytest.raises((m.MaintenanceError, OSError)):
        with m._UnstartedPreproofGuard() as guard:
            try:
                guard.tree(bundle)
            finally:
                descriptors = [record[0] for record in guard.nodes.values()]
    for fd in descriptors:
        with pytest.raises(OSError):
            os.fstat(fd)


@pytest.mark.parametrize('fault', ['leaf', 'alias', 'parent'])
def test_guard_retains_explicit_runtime_alias_and_exact_absence(tmp_path, monkeypatch, fault):
    physical = tmp_path/'physical'
    parent = physical/'db/mastermind-executive/control/acceptance'
    parent.mkdir(parents=True)
    alias = tmp_path/'var'
    alias.symlink_to(physical, target_is_directory=True)
    monkeypatch.setattr(m, '_MACOS_VAR_ALIAS', alias)
    monkeypatch.setattr(m, '_MACOS_VAR_PHYSICAL', physical)
    monkeypatch.setattr(m, '_TRUSTED_UID', os.getuid())
    monkeypatch.setattr(m, 'sys', SimpleNamespace(platform='darwin'))
    with pytest.raises((m.MaintenanceError, OSError)):
        with m._UnstartedPreproofGuard() as guard:
            guard.absent(alias/'db/mastermind-executive/control/acceptance'/MIDDLE)
            if fault == 'leaf':
                (parent/MIDDLE).mkdir()
            elif fault == 'alias':
                alias.unlink()
                alias.symlink_to(tmp_path/'foreign', target_is_directory=True)
            else:
                parent.rename(parent.with_name('old-acceptance'))
                parent.mkdir()
            guard.check()


def test_prepare_does_not_replace_a_final_namespace_created_during_sealing(tmp_path, monkeypatch):
    f = _prepare_fixture(tmp_path, monkeypatch)
    final = m.bundle_path(SUCCESSOR)
    original = m.write_sealed
    def write_then_create_final(path, value, **kwargs):
        original(path, value, **kwargs)
        if path.name == 'descriptor.json' and path.parent.name.startswith('.preparing-'):
            final.mkdir()
    monkeypatch.setattr(m, 'write_sealed', write_then_create_final)
    with pytest.raises(m.MaintenanceError):
        m.prepare(_new_args(f))
    assert final.is_dir() and not list(final.iterdir())
    assert list(final.parent.glob('.preparing-'+SUCCESSOR+'-*'))
