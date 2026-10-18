"""Sealed consecutive unstarted releases preserve one accepted baseline."""
import shutil

import pytest

from ops.executive_os import acceptance_maintenance as m
from tests.test_executive_acceptance_supersede_unstarted import _fixture, _rewrite


def _chain(tmp_path, monkeypatch, nodes):
    candidate, leaf, before, artifacts, canary, leaf_bundle, runtime = _fixture(tmp_path, monkeypatch)
    selected = [leaf]
    for index in range(nodes - 2):
        previous = selected[-1]
        sha = f"{index + 1:040x}"
        bundle = m.bundle_path(sha)
        shutil.copytree(leaf_bundle, bundle)
        descriptor = dict(previous, schema_version=m.SCHEMA_SUPERSEDE, successor_sha=sha,
                          superseded_unstarted_sha=previous['successor_sha'],
                          superseded_descriptor_sha256=m.digest(previous))
        _rewrite(bundle/'descriptor.json', descriptor)
        _rewrite(bundle/'preparing.json', {'schema_version': m.SCHEMA_SUPERSEDE})
        selected.append(descriptor)
    candidate.update(superseded_unstarted_sha=selected[-1]['successor_sha'],
                     superseded_descriptor_sha256=m.digest(selected[-1]))
    return candidate, selected, before, artifacts, canary, runtime


def _rebind(candidate, selected):
    for index, descriptor in enumerate(selected):
        if index:
            descriptor['superseded_descriptor_sha256'] = m.digest(selected[index - 1])
        _rewrite(m.bundle_path(descriptor['successor_sha'])/'descriptor.json', descriptor)
    candidate['superseded_descriptor_sha256'] = m.digest(selected[-1])


@pytest.mark.parametrize('nodes', [3, 63, 64])
def test_consecutive_unstarted_chain_preserves_every_bundle(tmp_path, monkeypatch, nodes):
    candidate, selected, before, artifacts, canary, runtime = _chain(tmp_path, monkeypatch, nodes)
    files = [p for descriptor in selected for p in m.bundle_path(descriptor['successor_sha']).iterdir()]
    original = {p: p.read_bytes() for p in files}
    m.validate_superseded_binding(candidate, before=before, artifacts=artifacts, prior_canary=canary)
    assert original == {p: p.read_bytes() for p in files}
    assert not m.bundle_path(candidate['successor_sha']).exists()
    assert list((runtime/'control/acceptance').iterdir()) == []


def test_prospective_successor_counts_in_finite_bound(tmp_path, monkeypatch):
    candidate, *_ = _chain(tmp_path, monkeypatch, 65)
    with pytest.raises(m.MaintenanceError, match='too deep'):
        m.validate_superseded_binding(candidate)
    assert not m.bundle_path(candidate['successor_sha']).exists()


def test_release_cycle_is_distinct_and_checked_before_depth(tmp_path, monkeypatch):
    candidate, selected, *_ = _chain(tmp_path, monkeypatch, 4)
    # The inner selected release points to the prospective successor. It need
    # not exist: identity repetition must refuse before reading its descriptor.
    selected[1]['superseded_unstarted_sha'] = candidate['successor_sha']
    _rebind(candidate, selected)
    monkeypatch.setattr(m, '_MAX_SUPERSEDE_DEPTH', 3, raising=False)
    with pytest.raises(m.MaintenanceError, match='cyclic'):
        m.validate_superseded_binding(candidate)


@pytest.mark.parametrize('position', [0, 1])
@pytest.mark.parametrize('fault', [
    'ancestor', 'root', 'frozen-base', 'descriptor-digest', 'preparing', 'baseline',
    'inventory', 'canary', 'backup', 'backup-mode', 'backup-link', 'run', 'carry',
    'extra', 'acceptance', 'missing',
])
def test_inner_selected_link_remains_sealed_and_unstarted(tmp_path, monkeypatch, position, fault):
    candidate, selected, before, artifacts, canary, runtime = _chain(tmp_path, monkeypatch, 4)
    target = selected[position]
    bundle = m.bundle_path(target['successor_sha'])
    if fault in {'ancestor', 'root', 'frozen-base'}:
        key = {'ancestor': 'predecessor_sha', 'root': 'root_identity_sha256',
               'frozen-base': 'frozen_base_sha'}[fault]
        target[key] = '9' * (64 if fault == 'root' else 40)
        _rebind(candidate, selected)
    elif fault == 'descriptor-digest':
        target['root_identity_sha256'] = '9'*64
        _rewrite(bundle/'descriptor.json', target)
    elif fault == 'preparing':
        _rewrite(bundle/'preparing.json', {'schema_version': m.SCHEMA_V2 if position else m.SCHEMA_SUPERSEDE})
    elif fault in {'baseline', 'inventory', 'canary'}:
        _rewrite(bundle/{'baseline': 'baseline.json', 'inventory': 'inventory.json',
                         'canary': 'prior-secret-canary.json'}[fault], {'drift': True})
    elif fault.startswith('backup'):
        backup = bundle/'prestate.sqlite3'
        if fault == 'backup-link':
            backup.unlink()
            backup.symlink_to(m.bundle_path(selected[-1]['successor_sha'])/'prestate.sqlite3')
        else:
            backup.chmod(0o600)
            if fault == 'backup':
                backup.write_bytes(b'changed database')
                backup.chmod(0o400)
    elif fault == 'acceptance':
        (runtime/'control/acceptance'/target['successor_sha']).mkdir()
    elif fault == 'missing':
        (bundle/'descriptor.json').unlink()
    else:
        m.write_sealed(bundle/{'run': 'run-started.json', 'carry': 'carry-forward.json',
                              'extra': 'unknown.json'}[fault], {})
    with pytest.raises(m.MaintenanceError):
        m.validate_superseded_binding(candidate, before=before, artifacts=artifacts, prior_canary=canary)
    assert not m.bundle_path(candidate['successor_sha']).exists()


def test_prejob_can_select_an_unstarted_supersession_successor(tmp_path, monkeypatch):
    from tests.test_executive_acceptance_supersede_prejob import unstarted_successor_fixture
    d, successor, leaf, before, artifacts, canary, *_ = unstarted_successor_fixture(tmp_path, monkeypatch)
    assert d['schema_version'] == m.SCHEMA_PREJOB and successor['schema_version'] == m.SCHEMA_SUPERSEDE
    m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)


def test_prejob_still_cannot_select_another_prejob_successor(tmp_path, monkeypatch):
    candidate, selected, *_ = _chain(tmp_path, monkeypatch, 3)
    inner = selected[-1]
    prejob_sha = 'e' * 40
    interrupted = {key: value for key, value in candidate.items() if key != 'superseded_unstarted_sha'}
    interrupted.update(schema_version=m.SCHEMA_PREJOB, successor_sha=prejob_sha,
                       interrupted_prejob_sha=inner['successor_sha'],
                       superseded_descriptor_sha256=m.digest(inner), prejob_evidence_sha256='f' * 64)
    bundle = m.bundle_path(prejob_sha)
    bundle.mkdir()
    m.write_sealed(bundle / 'descriptor.json', interrupted, public=True)
    assert m.descriptor_for(prejob_sha) == interrupted  # a real, valid supersede_prejob_v1 release
    top = dict(interrupted, successor_sha=candidate['successor_sha'], interrupted_prejob_sha=prejob_sha,
               superseded_descriptor_sha256=m.digest(interrupted))
    with pytest.raises(m.MaintenanceError, match='descriptor or accepted ancestor mismatch'):
        m.validate_superseded_binding(top)
