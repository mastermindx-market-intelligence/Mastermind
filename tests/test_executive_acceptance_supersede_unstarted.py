"""Hermetic same-schema supersession regressions; real guards remain exercised."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import argparse
import hashlib
import json
import os
import sqlite3

import pytest
from ops.executive_os import acceptance_maintenance as m
from tests.test_executive_acceptance_maintenance_v2 import _preserved_proof_delta, _chain

A, S, N = 'a'*40, 'b'*40, 'c'*40


def _fixture(tmp_path, monkeypatch):
    from ops.executive_os import autonomy_control as ac
    system = tmp_path/'system'
    runtime = tmp_path/'runtime'
    (runtime/'control'/'acceptance').mkdir(parents=True)
    monkeypatch.setattr(m, 'SYSTEM_ROOT', system)
    monkeypatch.setattr(ac, 'RUNTIME_ROOT', runtime)
    monkeypatch.setattr(m, '_TRUSTED_UID', os.getuid())
    monkeypatch.setattr(m, '_TRUSTED_GID', os.getgid())
    monkeypatch.setattr(m, '_sealed_ancestors', lambda path: [])
    monkeypatch.setattr(m, 'has_macos_acl', lambda *args, **kwargs: False)
    bundle = m.bundle_path(S)
    bundle.mkdir(parents=True)
    db = bundle/'prestate.sqlite3'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY)')
        c.execute('INSERT INTO schema_migrations VALUES(5)')
    db.chmod(0o400)
    baseline = m.snapshot(db)
    artifacts = {'preserved': {'sha256': 'd'*64}}
    canary = {'passed': True, 'generation': 'prior'}
    keys = m._DESCRIPTOR_V2_KEYS
    selected = {key: 'f'*64 for key in keys}
    for key in keys:
        if key.endswith(('_job_id', '_attempt_id')) or key in {'worker_id', 'quota_class'}:
            selected[key] = 'fixture-'+key
        elif key.endswith('_event_id'):
            selected[key] = 1
    selected.update(schema_version=m.SCHEMA_V2, predecessor_sha=A, successor_sha=S,
                    frozen_base_sha='d'*40, baseline_sha256=m.digest(baseline),
                    backup_sha256=m._file_digest(db), inventory_sha256=m.digest(artifacts),
                    prior_canary_sha256=m.digest(canary))
    for filename, value in [('descriptor.json', selected), ('preparing.json', {'schema_version': m.SCHEMA_V2}),
                            ('baseline.json', baseline), ('inventory.json', artifacts),
                            ('prior-secret-canary.json', canary)]:
        m.write_sealed(bundle/filename, value, public=filename == 'descriptor.json')
    candidate = dict(selected, schema_version=m.SCHEMA_SUPERSEDE, successor_sha=N,
                     superseded_unstarted_sha=S, superseded_descriptor_sha256=m.digest(selected))
    return candidate, selected, baseline, artifacts, canary, bundle, runtime


def _rewrite(path, value):
    path.chmod(0o600)
    path.write_text(json.dumps(value))
    path.chmod(0o444 if path.name == 'descriptor.json' else 0o400)


def test_exact_selected_v2_and_full_baseline_are_admitted(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, runtime = _fixture(tmp_path, monkeypatch)
    originals = {p.name: p.read_bytes() for p in bundle.iterdir()}
    m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)
    assert {p.name: p.read_bytes() for p in bundle.iterdir()} == originals
    assert d['predecessor_sha'] == A
    assert not (bundle/'carry-forward.json').exists()
    new = m.bundle_path(N)
    new.mkdir()
    m.write_sealed(new/'descriptor.json', d, public=True)
    assert m.descriptor_for(N) == d
    owner = object.__new__(m.Maintenance)
    owner.descriptor = d
    assert owner.predecessor_recovery_required is False
    assert m.recovery_permitted(None, 'old', N, 'worker', 'proof') is False


@pytest.mark.parametrize('fault', ['root', 'ancestor', 'descriptor-digest', 'selected-schema', 'baseline',
    'backup', 'backup-mode', 'backup-link', 'inventory', 'canary', 'live-baseline', 'live-inventory',
    'live-canary', 'schema', 'preparing', 'marker', 'carry', 'partial-bundle', 'partial-directory',
    'acceptance-summary', 'partial-acceptance', 'empty-acceptance', 'acceptance-symlink'])
def test_supersession_refuses_every_changed_binding_and_acceptance_state(tmp_path, monkeypatch, fault):
    d, selected, before, artifacts, canary, bundle, runtime = _fixture(tmp_path, monkeypatch)
    if fault == 'root':
        d['root_job_id'] = 'foreign'
    elif fault == 'ancestor':
        d['predecessor_sha'] = '9'*40
    elif fault == 'descriptor-digest':
        d['superseded_descriptor_sha256'] = '0'*64
    elif fault == 'selected-schema':
        selected['schema_version'] = m.SCHEMA_SUPERSEDE
        _rewrite(bundle/'descriptor.json', selected)
    elif fault in {'baseline', 'inventory', 'canary'}:
        filename = {'baseline': 'baseline.json', 'inventory': 'inventory.json', 'canary': 'prior-secret-canary.json'}[fault]
        _rewrite(bundle/filename, {'changed': True})
    elif fault == 'backup':
        (bundle/'prestate.sqlite3').chmod(0o600)
        with sqlite3.connect(bundle/'prestate.sqlite3') as c:
            c.execute('INSERT INTO schema_migrations VALUES(4)')
        (bundle/'prestate.sqlite3').chmod(0o400)
    elif fault == 'backup-mode':
        (bundle/'prestate.sqlite3').chmod(0o600)
    elif fault == 'backup-link':
        original = bundle/'prestate.sqlite3'
        target = tmp_path/'other.sqlite3'
        original.rename(target)
        original.symlink_to(target)
    elif fault.startswith('live-'):
        {'live-baseline': before, 'live-inventory': artifacts, 'live-canary': canary}[fault]['changed'] = True
    elif fault == 'schema':
        before['tables']['schema_migrations'][0]['version'] = 6
        _rewrite(bundle/'baseline.json', before)
        (bundle/'prestate.sqlite3').chmod(0o600)
        with sqlite3.connect(bundle/'prestate.sqlite3') as c:
            c.execute('UPDATE schema_migrations SET version=6')
        (bundle/'prestate.sqlite3').chmod(0o400)
        selected.update(baseline_sha256=m.digest(before), backup_sha256=m._file_digest(bundle/'prestate.sqlite3'))
        _rewrite(bundle/'descriptor.json', selected)
        d.update(baseline_sha256=selected['baseline_sha256'], backup_sha256=selected['backup_sha256'],
                 superseded_descriptor_sha256=m.digest(selected))
    elif fault == 'preparing':
        _rewrite(bundle/'preparing.json', {'schema_version': m.SCHEMA})
    elif fault in {'marker', 'carry', 'partial-bundle', 'partial-directory'}:
        filename = {'marker': 'run-started.json', 'carry': 'carry-forward.json',
                    'partial-bundle': 'unfinished.json', 'partial-directory': 'unfinished'}[fault]
        path = bundle/filename
        if fault == 'partial-directory':
            path.mkdir()
        else:
            m.write_sealed(path, {'passed': True})
    else:
        output = runtime/'control'/'acceptance'/S
        if fault == 'acceptance-symlink':
            output.symlink_to(tmp_path/'absent')
        else:
            output.mkdir()
            if fault != 'empty-acceptance':
                (output/('acceptance-summary.json' if fault == 'acceptance-summary' else 'identity.json')).write_text('{}')
    with pytest.raises((m.MaintenanceError, OSError)):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)


def test_absence_requires_existing_canonical_parent_and_propagates_access_denial(tmp_path, monkeypatch):
    with pytest.raises(FileNotFoundError):
        m._require_absent(tmp_path/'missing'/'release')
    actual = tmp_path/'actual'
    actual.mkdir()
    alias = tmp_path/'alias'
    alias.symlink_to(actual)
    with pytest.raises(m.MaintenanceError, match='canonical'):
        m._require_absent(alias/'release')
    original = Path.lstat
    leaf = actual/'release'
    def deny(path, *args, **kwargs):
        if path == leaf:
            raise PermissionError('protected read denied')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', deny)
    with pytest.raises(PermissionError, match='denied'):
        m._require_absent(leaf)




@pytest.mark.skipif(m.sys.platform != 'darwin', reason='macOS OS alias proof')
def test_actual_macos_var_alias_preserves_generic_absence_guard(tmp_path, monkeypatch):
    canonical = tmp_path.resolve(strict=True)
    if not canonical.is_relative_to('/private/var'):
        pytest.skip('host temporary directory is outside the OS /var alias')
    logical = Path('/var') / canonical.relative_to('/private/var') / S
    with pytest.raises(m.MaintenanceError, match='canonical'):
        m._require_absent(logical)
    # Verify the actual OS alias and production spelling without reading or
    # modifying the live Runtime. The strict leaf check uses our own fixture.
    physical = Path('/private/var/db/mastermind-executive/control/acceptance') / S
    original = m._require_absent
    observed = []
    def observe(path):
        assert path == physical
        observed.append(path)
        original(canonical/S)
    monkeypatch.setattr(m, '_require_absent', observe)
    m._require_runtime_acceptance_absent(Path('/var/db/mastermind-executive/control/acceptance') / S)
    assert observed == [physical]
    assert not (canonical/S).exists()


def _var_alias_fixture(tmp_path, monkeypatch, *, absolute=False):
    from ops.executive_os import autonomy_control as ac
    values = _fixture(tmp_path, monkeypatch)
    physical = tmp_path/'private'/'var'
    physical.mkdir(parents=True)
    (physical/'db').mkdir()
    values[-1].rename(physical/'db'/'mastermind-executive')
    alias = tmp_path/'var'
    alias.symlink_to(physical if absolute else 'private/var', target_is_directory=True)
    monkeypatch.setattr(m, '_MACOS_VAR_ALIAS', alias, raising=False)
    monkeypatch.setattr(m, '_MACOS_VAR_PHYSICAL', physical, raising=False)
    monkeypatch.setattr(m, 'sys', SimpleNamespace(platform='darwin'))
    monkeypatch.setattr(ac, 'RUNTIME_ROOT', alias/'db'/'mastermind-executive')
    return values, alias, physical


@pytest.mark.parametrize('absolute', [False, True])
def test_supersession_accepts_only_standard_os_var_alias(tmp_path, monkeypatch, absolute):
    values, alias, physical = _var_alias_fixture(tmp_path, monkeypatch, absolute=absolute)
    d, _, before, artifacts, canary, bundle, _ = values
    originals = {p.name: p.read_bytes() for p in bundle.iterdir()}
    m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)
    assert {p.name: p.read_bytes() for p in bundle.iterdir()} == originals
    # Admission is limited to the trusted Runtime seam; arbitrary evidence stays strict.
    with pytest.raises(m.MaintenanceError, match='canonical'):
        m._require_absent(alias/'db'/'mastermind-executive'/'control'/'acceptance'/S)



@pytest.mark.parametrize('relative', [
    'db/other/control/acceptance/' + S,
    'db/mastermind-executive/control/acceptance/not-a-sha',
    'db/mastermind-executive/control/acceptance/' + S.upper(),
])
def test_os_alias_exception_is_limited_to_exact_runtime_acceptance(tmp_path, monkeypatch, relative):
    _, alias, physical = _var_alias_fixture(tmp_path, monkeypatch)
    (physical/relative).parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(m.MaintenanceError, match='canonical'):
        m._require_runtime_acceptance_absent(alias/relative)

@pytest.mark.parametrize('fault', [
    'unexpected-target', 'normalized-target', 'alias-directory', 'untrusted-owner',
    'symlink-descendant', 'symlink-physical-parent', 'missing-parent',
    'denied-parent', 'denied-leaf', 'existing-file', 'existing-directory',
    'dangling-leaf', 'alias-changed', 'non-darwin',
])
def test_runtime_alias_does_not_weaken_absence_guards(tmp_path, monkeypatch, fault):
    values, alias, physical = _var_alias_fixture(tmp_path, monkeypatch)
    d, _, before, artifacts, canary, _, _ = values
    parent = physical/'db'/'mastermind-executive'/'control'/'acceptance'
    leaf = parent/S
    if fault in {'unexpected-target', 'normalized-target', 'alias-directory'}:
        alias.unlink()
        if fault == 'alias-directory':
            alias.mkdir()
        else:
            alias.symlink_to(physical.parent if fault == 'unexpected-target' else 'private/./var')
    elif fault == 'untrusted-owner':
        original = Path.lstat
        def foreign_owner(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if path == alias:
                return SimpleNamespace(**{name: getattr(info, name) for name in dir(info)
                    if name.startswith('st_') and name != 'st_uid'}, st_uid=info.st_uid + 1)
            return info
        monkeypatch.setattr(Path, 'lstat', foreign_owner)
    elif fault in {'symlink-descendant', 'symlink-physical-parent'}:
        selected = parent if fault == 'symlink-descendant' else physical.parent
        moved = tmp_path/'moved'
        selected.rename(moved)
        selected.symlink_to(moved, target_is_directory=True)
    elif fault == 'missing-parent':
        parent.rmdir()
    elif fault in {'denied-parent', 'denied-leaf'}:
        method = 'resolve' if fault == 'denied-parent' else 'lstat'
        original = getattr(Path, method)
        def denied(path, *args, **kwargs):
            if path == (parent if fault == 'denied-parent' else leaf):
                raise PermissionError('protected read denied')
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, method, denied)
    elif fault == 'existing-file':
        leaf.write_text('prior acceptance')
    elif fault == 'existing-directory':
        leaf.mkdir()
    elif fault == 'dangling-leaf':
        leaf.symlink_to(tmp_path/'absent')
    elif fault == 'alias-changed':
        original = m._require_absent
        def changed(path):
            original(path)
            alias.unlink()
            alias.symlink_to('private/./var')
        monkeypatch.setattr(m, '_require_absent', changed)
    elif fault == 'non-darwin':
        monkeypatch.setattr(m, 'sys', SimpleNamespace(platform='linux'))
    with pytest.raises((m.MaintenanceError, OSError)):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)

def test_new_shape_remains_closed_and_sha_identities_distinct(tmp_path, monkeypatch):
    d, *_ = _fixture(tmp_path, monkeypatch)
    bundle = m.bundle_path(N)
    bundle.mkdir()
    path = bundle/'descriptor.json'
    for mutation in [{'unexpected': True}, {'superseded_unstarted_sha': N},
                     {'superseded_unstarted_sha': A}, {'superseded_unstarted_sha': 'invalid'}]:
        value = dict(d, **mutation)
        if path.exists():
            _rewrite(path, value)
        else:
            m.write_sealed(path, value, public=True)
        with pytest.raises(m.MaintenanceError):
            m.descriptor_for(N)


@pytest.mark.parametrize('fault', [None, 'historical-root', 'historical-attempt', 'old-recovery', 'schema', 'unrelated'])
def test_new_variant_uses_exact_existing_v2_proof_delta(tmp_path, monkeypatch, fault):
    before, after, d = _preserved_proof_delta()
    d['schema_version'] = m.SCHEMA_SUPERSEDE
    monkeypatch.setattr(m, '_validate_recovery_event', lambda *args: None)
    if fault == 'historical-root':
        after['tables']['jobs'][1]['status'] = 'COMPLETED'
    elif fault == 'historical-attempt':
        after['tables']['attempts'][0]['status'] = 'COMPLETED'
    elif fault == 'old-recovery':
        after['tables']['events'].append(dict(event_id=99, event_type='PROOF_CAPACITY_RECOVERED',
            job_id='JOB-template', attempt_id='ATT-prior', worker_id='worker', quota_class='proof'))
    elif fault == 'schema':
        after['schema'].append(['changed'])
    elif fault == 'unrelated':
        after['tables']['untouched'][0]['value'] = 'changed'
    if fault is None:
        m.verify_preserved(before, after, d, ['JOB-new1', 'JOB-new2'])
    else:
        with pytest.raises(m.MaintenanceError):
            m.verify_preserved(before, after, d, ['JOB-new1', 'JOB-new2'])


def test_future_pass_chain_binds_accepted_ancestor_and_selected_separately(monkeypatch):
    descriptors, receipts, summaries = _chain(monkeypatch)
    current = descriptors['c'*40]
    current.update(schema_version=m.SCHEMA_SUPERSEDE, superseded_unstarted_sha='9'*40,
                   superseded_descriptor_sha256='7'*64)
    receipts['c'*40].update(schema_version=m.SCHEMA_SUPERSEDE, descriptor_sha256=m.digest(current))
    seen = []
    monkeypatch.setattr(m, 'validate_superseded_binding', lambda descriptor, **kw: seen.append(descriptor))
    prior, summary, material = m.prior_carry_material('c'*40)
    assert prior is current and material['frozen_base_sha'] == 'a'*40
    assert seen == [current]
    future = dict(current, schema_version=m.SCHEMA_V2, predecessor_sha='c'*40, successor_sha='d'*40, **material)
    m.validate_prior_carry_binding(future)
    assert seen == [current, current]
    receipts['b'*40]['passed'] = False
    with pytest.raises(m.MaintenanceError):
        m.validate_prior_carry_binding(future)


@pytest.mark.parametrize('selected,digest,terminal,installed', [
    (S, None, True, S), (None, '0'*64, True, A), (S, '0'*64, False, S),
    (S, 'invalid', True, S), (A, '0'*64, True, A), (N, '0'*64, True, N),
    (S, '0'*64, True, A), (None, None, True, S),
])
def test_prepare_selector_requires_exact_installed_selected_release(tmp_path, monkeypatch, selected, digest, terminal, installed):
    system = tmp_path/'system'
    (system/'config').mkdir(parents=True)
    (system/'config'/'control.json').write_text(json.dumps(dict(proof_base_sha=installed,
        ceo_submit_armed=False, coo_autonomy_armed=False, coo_operator_harness_armed=False)))
    (system/'config'/'worker-codex.json').write_text('{"operator_harness_armed":false}')
    monkeypatch.setattr(m, 'SYSTEM_ROOT', system)
    monkeypatch.setattr(m.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(m, 'sys', SimpleNamespace(platform='darwin'))
    monkeypatch.setattr(m, 'require_stopped', lambda: None)
    def forbidden(*args):
        raise AssertionError('invalid selector reached runtime read')
    monkeypatch.setattr(m, 'snapshot', forbidden)
    args = argparse.Namespace(predecessor_sha=A, successor_sha=N, root_job_id='root',
        supersede_unstarted_sha=selected, superseded_descriptor_sha256=digest,
        carry_terminal_dispatch=terminal, recovery_job_id=None, recovery_attempt_id=None)
    with pytest.raises(m.MaintenanceError):
        m.prepare(args)


def test_acceptance_revalidates_full_selected_prestate_before_marker(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, runtime = _fixture(tmp_path, monkeypatch)
    new = m.bundle_path(N)
    new.mkdir()
    for filename in ['baseline.json', 'inventory.json', 'prior-secret-canary.json', 'prestate.sqlite3']:
        (new/filename).write_bytes((bundle/filename).read_bytes())
        (new/filename).chmod(0o400)
    m.write_sealed(new/'descriptor.json', d, public=True)
    # The prior-chain owner has its own canonical suite; this test isolates the
    # real supersession guard at the acceptance start boundary.
    monkeypatch.setattr(m, 'validate_prior_carry_binding', lambda descriptor: None)
    monkeypatch.setattr(m, 'require_stopped', lambda: None)
    monkeypatch.setattr(m, 'verify_inventory', lambda value: None)
    (runtime/'data'/'control_plane').mkdir(parents=True)
    (runtime/'data'/'control_plane'/'executive.sqlite3').write_bytes((bundle/'prestate.sqlite3').read_bytes())
    live_canary = tmp_path/'live-canary.json'
    live_canary.write_text(json.dumps(canary))
    from control_plane.executive_runtime import Runtime
    monkeypatch.setattr(Runtime, 'at', lambda *args, **kwargs: SimpleNamespace(
        jobs=SimpleNamespace(get_job=lambda job: SimpleNamespace(job_id=job))))
    monkeypatch.setattr(m, 'terminal_carry_fields', lambda *args: (None, {
        key: d[key] for key in m._DESCRIPTOR_V2_KEYS-m._DESCRIPTOR_KEYS}))
    config = dict(runtime_root=str(runtime), secret_canary_receipt_path=str(live_canary),
                  ceo_submit_armed=False, coo_autonomy_armed=False, coo_operator_harness_armed=False)
    m.write_sealed(bundle/'run-started.json', {'schema_version': m.SCHEMA_V2})
    with pytest.raises(m.MaintenanceError):
        m.Maintenance(N, m.digest(d), config)
    assert not (new/'run-started.json').exists()
    (bundle/'run-started.json').unlink()
    owner = m.Maintenance(N, m.digest(d), config)
    assert owner.predecessor_recovery_required is False
    assert m.sealed_json(new/'run-started.json') == {
        'schema_version': m.SCHEMA_SUPERSEDE, 'descriptor_sha256': m.digest(d)}


@pytest.mark.parametrize(('prejob', 'nested_fault'), [
    (False, None), (True, None), (False, 'valid'), (False, 'canary'), (False, 'depth')])
def test_preparation_publishes_one_new_descriptor_without_modifying_selected(tmp_path, monkeypatch, prejob, nested_fault):
    nested = nested_fault is not None
    import dataclasses
    from control_plane.executive_runtime import Runtime
    from ops.executive_os import autonomy_control as ac
    from tests.test_executive_acceptance_maintenance_v2 import _terminal_fixture
    # This helper freezes the complete historical v5 contract for this test.
    # Use one monkeypatch scope so teardown cannot restore a nested v5 vector
    # over the current schema and leak it into later tests.
    runtime, root, before, config, prior, material, proof, _, _ = _terminal_fixture(tmp_path, monkeypatch)
    accepted, selected_sha, successor = 'b'*40, 'e'*40, 'f'*40
    root = dataclasses.replace(root, constraints={**root.constraints, 'operator_harness_armed': False})
    prior['root_identity_sha256'] = m.root_identity(root)
    original = runtime.jobs.get_job
    monkeypatch.setattr(runtime.jobs, 'get_job', lambda job: root if job == root.job_id else original(job))
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
    runtime_root = tmp_path/'runtime'
    (runtime_root/'control'/'acceptance').mkdir(parents=True)
    monkeypatch.setattr(ac, 'RUNTIME_ROOT', runtime_root)
    config.update(runtime_root=str(runtime_root), proof_base_sha=selected_sha,
                  ceo_submit_armed=False, coo_autonomy_armed=False, coo_operator_harness_armed=False)
    for key in ('proof_workspace_root', 'worker_runs_root', 'receipts_root', 'backup_root'):
        path = tmp_path/'artifacts'/key
        path.mkdir(parents=True)
        config[key] = str(path)
    canary_fixtures = runtime_root.parent.parent/'canary-fixtures'
    canary_fixtures.mkdir(exist_ok=True)
    canary_path = tmp_path/'prior-canary.json'
    canary = {'passed': True}
    canary_path.write_text(json.dumps(canary))
    config['secret_canary_receipt_path'] = str(canary_path)
    (system/'config'/'control.json').write_text(json.dumps(config))
    (system/'config'/'worker-codex.json').write_text('{"operator_harness_armed":false}')
    artifacts = m.inventory([Path(config[key]) for key in
        ('proof_workspace_root', 'worker_runs_root', 'receipts_root', 'backup_root')] + [canary_fixtures])
    _proof, fields = m.terminal_carry_fields(runtime, root, config, before, accepted)
    bundle = m.bundle_path(selected_sha)
    bundle.mkdir(parents=True)
    with sqlite3.connect(runtime.store.path) as source, sqlite3.connect(bundle/'prestate.sqlite3') as dest:
        source.backup(dest)
    (bundle/'prestate.sqlite3').chmod(0o400)
    selected = dict(schema_version=m.SCHEMA_V2, predecessor_sha=accepted, successor_sha=selected_sha,
        root_job_id=root.job_id, root_identity_sha256=m.root_identity(root), root_event_id=prior['root_event_id'],
        root_event_sha256=prior['root_event_sha256'], worker_id=config['worker_id'], quota_class=config['quota_class'],
        baseline_sha256=m.digest(before), inventory_sha256=m.digest(artifacts), prior_canary_sha256=m.digest(canary),
        backup_sha256=m._file_digest(bundle/'prestate.sqlite3'), **fields)
    for filename, value in [('descriptor.json', selected), ('preparing.json', {'schema_version': m.SCHEMA_V2}),
                            ('baseline.json', before), ('inventory.json', artifacts), ('prior-secret-canary.json', canary)]:
        m.write_sealed(bundle/filename, value, public=filename == 'descriptor.json')
    if nested:
        import shutil
        older_sha = 'd'*40
        older_bundle = m.bundle_path(older_sha)
        shutil.copytree(bundle, older_bundle)
        older = dict(selected, successor_sha=older_sha)
        _rewrite(older_bundle/'descriptor.json', older)
        selected.update(schema_version=m.SCHEMA_SUPERSEDE,
                        superseded_unstarted_sha=older_sha,
                        superseded_descriptor_sha256=m.digest(older))
        _rewrite(bundle/'descriptor.json', selected)
        _rewrite(bundle/'preparing.json', {'schema_version': m.SCHEMA_SUPERSEDE})
        if nested_fault == 'canary':
            _rewrite(older_bundle/'prior-secret-canary.json', {'passed': False})
        elif nested_fault == 'depth':
            monkeypatch.setattr(m, '_MAX_SUPERSEDE_DEPTH', 2)
        older_originals = {p.name: p.read_bytes() for p in older_bundle.iterdir()}
    if prejob:
        from tests.test_executive_acceptance_supersede_prejob import receipt_prefix
        receipt_prefix(runtime_root, selected, monkeypatch)
    originals = {p.name: p.read_bytes() for p in bundle.iterdir()}
    args = argparse.Namespace(predecessor_sha=accepted, successor_sha=successor, root_job_id=root.job_id,
        recovery_job_id=None, recovery_attempt_id=None, carry_terminal_dispatch=True,
        supersede_unstarted_sha=None if prejob else selected_sha,
        supersede_prejob_sha=selected_sha if prejob else None,
        superseded_descriptor_sha256=m.digest(selected))
    if nested_fault in {'canary', 'depth'}:
        with pytest.raises(m.MaintenanceError, match='sealed baseline drifted' if nested_fault == 'canary' else 'too deep'):
            m.prepare(args)
        assert {p.name: p.read_bytes() for p in bundle.iterdir()} == originals
        assert {p.name: p.read_bytes() for p in older_bundle.iterdir()} == older_originals
        assert m.snapshot(runtime.store.path) == before
        assert not m.bundle_path(successor).exists()
        assert not list(m.bundle_path(successor).parent.glob('.preparing-*'))
        return
    result = m.prepare(args)
    d = m.descriptor_for(successor)
    assert result == m.bundle_path(successor)
    assert d['schema_version'] == (m.SCHEMA_PREJOB if prejob else m.SCHEMA_SUPERSEDE)
    assert d['predecessor_sha'] == accepted
    assert d['interrupted_prejob_sha' if prejob else 'superseded_unstarted_sha'] == selected_sha
    assert d['template_proof_job_id'] == proof.job_id and d['frozen_base_sha'] == 'a'*40
    assert {p.name: p.read_bytes() for p in bundle.iterdir()} == originals
    if nested:
        assert {p.name: p.read_bytes() for p in older_bundle.iterdir()} == older_originals
    assert m.snapshot(runtime.store.path) == before
    assert not (result/'run-started.json').exists()
    assert not (bundle/'carry-forward.json').exists()


@pytest.mark.parametrize('fault', [None, 'wal-nonempty', 'wal-missing', 'shm-missing',
    'wal-mode', 'shm-mode', 'wal-symlink', 'shm-symlink', 'shm-directory',
    'wal-hardlink', 'shm-hardlink', 'shm-size', 'uid', 'gid', 'acl', 'race'])
def test_only_exact_legacy_sealed_empty_wal_pair_is_admitted(tmp_path, monkeypatch, fault):
    d, selected, before, artifacts, canary, bundle, _runtime = _fixture(tmp_path, monkeypatch)
    wal, shm = bundle/'prestate.sqlite3-wal', bundle/'prestate.sqlite3-shm'
    wal.write_bytes(b'')
    shm.write_bytes(b'X'*32768)
    wal.chmod(0o400)
    shm.chmod(0o400)
    # Match the fixture's simulated trusted group, not macOS temp's wheel group.
    os.chown(wal, -1, os.getgid())
    os.chown(shm, -1, os.getgid())
    if fault == 'wal-nonempty':
        wal.chmod(0o600)
        wal.write_bytes(b'committed transaction')
        wal.chmod(0o400)
    elif fault in {'wal-missing', 'shm-missing'}:
        (wal if fault == 'wal-missing' else shm).unlink()
    elif fault in {'wal-mode', 'shm-mode'}:
        (wal if fault == 'wal-mode' else shm).chmod(0o600)
    elif fault in {'wal-symlink', 'shm-symlink'}:
        target = wal if fault == 'wal-symlink' else shm
        preserved = tmp_path/'preserved-sidecar'
        target.rename(preserved)
        target.symlink_to(preserved)
    elif fault == 'shm-directory':
        shm.unlink()
        shm.mkdir()
    elif fault in {'wal-hardlink', 'shm-hardlink'}:
        os.link(wal if fault == 'wal-hardlink' else shm, tmp_path/'linked-sidecar')
    elif fault == 'shm-size':
        shm.chmod(0o600)
        shm.write_bytes(b'partial')
        shm.chmod(0o400)
    elif fault == 'uid':
        original_lstat = Path.lstat
        def foreign_uid(path, *args, **kwargs):
            info = original_lstat(path, *args, **kwargs)
            if path == shm:
                fields = {key: getattr(info, key) for key in
                    ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
                     'st_size', 'st_mtime_ns', 'st_ctime_ns')}
                fields['st_uid'] += 1
                return SimpleNamespace(**fields)
            return info
        monkeypatch.setattr(Path, 'lstat', foreign_uid)
    elif fault == 'gid':
        monkeypatch.setattr(m, '_TRUSTED_GID', os.getgid()+1)
    elif fault == 'acl':
        monkeypatch.setattr(m, 'has_macos_acl', lambda path, **kwargs: path == shm)
    elif fault == 'race':
        original_snapshot = m.snapshot
        def race(path, **kwargs):
            result = original_snapshot(path, **kwargs)
            if path == bundle/'prestate.sqlite3':
                shm.chmod(0o600)
                shm.write_bytes(b'Y'*32768)
                shm.chmod(0o400)
            return result
        monkeypatch.setattr(m, 'snapshot', race)
    original_open = Path.open
    def deny_sidecar_read(path, *args, **kwargs):
        mode = kwargs.get('mode', args[0] if args else 'r')
        if path in {wal, shm} and 'w' not in mode:
            raise AssertionError('sidecar bytes must not be read')
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', deny_sidecar_read)
    identities = {entry.name: m._identity(entry.lstat()) for entry in bundle.iterdir()}
    if fault is None:
        m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)
        assert {entry.name: m._identity(entry.lstat()) for entry in bundle.iterdir()} == identities
    else:
        with pytest.raises((m.MaintenanceError, OSError)):
            m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)
