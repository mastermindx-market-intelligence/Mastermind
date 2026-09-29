"""Regressions from independent R1 review, plus publication/security boundaries.

Root/ACL/boot facts are synthetic; descriptor operations and file races are real.
The immutable original review tests remain in the evidence carrier.
"""
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import pytest
from control_plane import executive_release_factory as f
from control_plane import executive_installed_peer as peer
from control_plane import executive_privileged_broker as broker
from control_plane import executive_release_consumer as consumer
from control_plane import executive_release_ingress as ingress
from control_plane import executive_release_owner as owner
from tests.test_executive_release_controller_policy import inputs
from tests.test_executive_release_factory import image, wire
from tests.test_executive_release_consumer import installed, counts

REAL_READER = f._Reader


def frame(image, operation, **args):
    return {**ingress.project_frame(operation, args, principal=image['principal']),
            'schema': consumer.BROKER_SCHEMA, 'approval': None}


def reproject_control(image, raw):
    image['files'][f._CONTROL] = raw
    evidence = f.file_document(image['files'][f._EVIDENCE])
    evidence['control_config_digest'] = f._hash(raw)
    evidence['broker_config_digest'] = f._hash(image['files'][f._BROKER_CONFIG])
    evidence['installed_configuration_digest'] = f._digest({
        'schema': 'mastermind.executive_installed_configuration_set/v1',
        'files': [{'path': name, 'sha256': f._hash(image['files'][path])}
                  for name, path in [('config/control.json', f._CONTROL),
                  ('config/authority_map.yml', image['config'].release_root / 'config/authority_map.yml'),
                  ('config/privileged-broker.json', f._BROKER_CONFIG)]]})
    image['files'][f._EVIDENCE] = wire(evidence)


@pytest.mark.parametrize('constant', ['NaN', 'Infinity', '-Infinity', '1e999'])
def test_control_projection_rejects_same_nonfinite_input_as_installed_peer(image, constant):
    raw = image['files'][f._CONTROL][:-1] + b',"extra":' + constant.encode() + b'}'
    # Causal comparison: the same bytes fail the existing installed-peer rules.
    with pytest.raises(peer.PeerIdentityError):
        peer._load_strict_json(raw, code='SERVICE_CONFIG_MALFORMED')
    reproject_control(image, raw)
    with pytest.raises(consumer.ReleaseConsumerError):
        f.build_release_owner(image['config'])


@pytest.fixture
def disk_image(image, tmp_path, monkeypatch):
    """Real bytes/fds/renames; only root identity, ACL, boot and legacy gate synthetic."""
    if sys.platform != 'darwin':
        pytest.skip('real Darwin descriptor fixture')
    base = tmp_path
    old_root = image['config'].release_root
    new_root = base / 'releases' / old_root.name
    old_fixed = {key: getattr(f, key) for key in
                 ('_REGISTRATION', '_KEY', '_REGISTRY', '_EVIDENCE', '_CONTROL', '_BROKER_CONFIG', '_STAGING')}
    mapping = {old: base / ('release-staging' if key == '_STAGING' else 'config/' + old.name)
               for key, old in old_fixed.items()}
    config = dataclasses.replace(image['config'], release_root=new_root, receipt_root=base / 'receipts')
    for key, old in old_fixed.items():
        monkeypatch.setattr(f, key, mapping[old])
    monkeypatch.setattr(broker, '_RELEASE_PREFIX', new_root.parent)
    monkeypatch.setattr(broker, '_RECEIPT_ROOT', config.receipt_root)
    files = {}
    for path, raw in image['files'].items():
        if path in mapping:
            files[mapping[path]] = raw
        elif path.is_relative_to(old_root):
            files[new_root / path.relative_to(old_root)] = raw
        elif path.is_relative_to(old_fixed['_STAGING']):
            files[f._STAGING / path.relative_to(old_fixed['_STAGING'])] = raw
    doc = json.loads(files[f._BROKER_CONFIG])
    doc.update(release_root=str(new_root), receipt_root=str(config.receipt_root))
    files[f._BROKER_CONFIG] = json.dumps(doc).encode()
    image['files'] = files
    image['config'] = config
    reproject_control(image, files[f._CONTROL])
    # Rebind the staged configuration to the disposable installed paths and
    # recompute the acyclic leaf/effect identities for real approval tests.
    old_stage = f._STAGING / image['transition']
    evidence = f.file_document(files[f._EVIDENCE])
    configuration = f.file_document(files[old_stage / 'configuration-transition.json'])
    configuration['from_configuration_digest'] = evidence['installed_configuration_digest']
    preservation = f.file_document(files[old_stage / 'preservation-plan.json'])
    preservation['configuration_transition_digest'] = f._digest(configuration)
    effect = f.file_document(files[old_stage / 'effect.json'])
    effect.update(configuration_transition_digest=f._digest(configuration),
                  preservation_plan_digest=f._digest(preservation))
    preconditions = f.file_document(files[old_stage / 'preconditions-template.json'])
    preconditions.update(installed_configuration_digest=evidence['installed_configuration_digest'],
                         preservation_plan_digest=f._digest(preservation))
    for name, value in [('configuration-transition.json', configuration),
                        ('preservation-plan.json', preservation), ('effect.json', effect),
                        ('preconditions-template.json', preconditions)]:
        files[old_stage / name] = wire(value)
    transition = f._digest(effect)
    new_stage = f._STAGING / transition
    for path in list(files):
        if path.parent == old_stage:
            files[new_stage / path.name] = files.pop(path)
    table = f.file_document(files[f._REGISTRY])
    table['transitions'][0]['transition_digest'] = transition
    files[f._REGISTRY] = wire(table)
    image.update(transition=transition, effect=effect, directory=new_stage)
    for path, raw in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        mode = 0o440 if path == f._CONTROL else 0o444 if path.is_relative_to(new_root) else 0o400
        path.chmod(mode)
    for path in [f._STAGING, *f._STAGING.iterdir()]:
        path.chmod(0o500)
    real_stat, real_fstat = os.stat, os.fstat
    control_ino = real_stat(f._CONTROL).st_ino
    volume_ino = real_stat('/Volumes/Mastermind').st_ino
    def facts(info):
        fields = [name for name in dir(info) if name.startswith('st_')]
        values = {name: getattr(info, name) for name in fields}
        values.update(st_uid=0, st_gid=450 if info.st_ino == control_ino else 0)
        # The disposable fixture lives on the user's group-writable SSD, not in /Library.
        # Only that outside ancestor's permission fact is synthetic; never chmod it.
        if info.st_ino == volume_ino and stat.S_ISDIR(info.st_mode):
            values['st_mode'] = info.st_mode & ~0o022
        return SimpleNamespace(**values)
    def observed_stat(*args, **kwargs):
        return facts(real_stat(*args, **kwargs))
    monkeypatch.setattr(f.os, 'stat', observed_stat)
    monkeypatch.setattr(f.os, 'fstat', lambda fd: facts(real_fstat(fd)))
    monkeypatch.setattr(f.os, 'supports_dir_fd', os.supports_dir_fd | {observed_stat})
    monkeypatch.setattr(f, 'has_macos_acl', lambda *a, **k: False)
    monkeypatch.setattr(f, '_Reader', REAL_READER)
    return image


def test_registry_atomic_publication_does_not_destroy_resident_history(disk_image):
    root = f.build_release_owner(disk_image['config'])
    original = root._history_trust()
    resident_paths = [p for p in disk_image['files']
                      if p != f._REGISTRY and not p.is_relative_to(f._STAGING)]
    before = {p: (p.read_bytes(), p.stat().st_ino) for p in resident_paths}
    value = f.file_document(f._REGISTRY.read_bytes())
    value['registry_generation'] += 1
    temporary = f._REGISTRY.with_name('new-registry')
    temporary.write_bytes(wire(value))
    temporary.chmod(0o400)
    temporary.replace(f._REGISTRY)
    assert before == {p: (p.read_bytes(), p.stat().st_ino) for p in resident_paths}
    # Required R6 boundary: registry may change between requests and is not history trust.
    assert root._history_trust().input_identity_digest == original.input_identity_digest


@pytest.mark.parametrize('which', ['root', 'transition'])
def test_staging_directories_require_wheel_group(disk_image, monkeypatch, which):
    directory = f._STAGING if which == 'root' else next(f._STAGING.iterdir())
    target = directory.stat().st_ino
    leaf_dir = next(f._STAGING.iterdir())
    # A positive identical-path control proves any later refusal is caused by gid.
    assert f._Reader().observe(leaf_dir, maximum=0, mode=0o500,
                              directory=True, names=f._STAGE_FILES)
    # Keep real directory mode/inode/bytes; vary only the exact trusted group fact.
    old_stat, old_fstat = os.stat, os.fstat
    def foreign_group(info):
        if info.st_ino == target:
            info.st_gid = 450
        return info
    def observed_stat(*a, **k): return foreign_group(old_stat(*a, **k))
    monkeypatch.setattr(f.os, 'stat', observed_stat)
    monkeypatch.setattr(f.os, 'fstat', lambda fd: foreign_group(old_fstat(fd)))
    monkeypatch.setattr(f.os, 'supports_dir_fd', os.supports_dir_fd | {observed_stat})
    with pytest.raises(consumer.ReleaseConsumerError):
        f._Reader().observe(leaf_dir, maximum=0, mode=0o500,
                            directory=True, names=f._STAGE_FILES)


def test_history_checks_total_resident_deadline_after_legacy_trust(disk_image, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(f.time, 'monotonic', lambda: clock[0])
    root = f.build_release_owner(disk_image['config'])
    # Simulate the already required legacy trust check consuming the remaining budget.
    def slow_trust(config):
        clock[0] += 6.0
    monkeypatch.setattr(broker, 'verify_production_trust', slow_trust)
    with pytest.raises(consumer.ReleaseConsumerError):
        root._history_trust()


@pytest.mark.parametrize('field', ['owner_installation_id', 'target_ref', 'registration_generation',
    'release_commit', 'release_tree', 'control_config_digest', 'broker_config_digest',
    'installed_configuration_digest', 'python_runtime_provenance_digest', 'provider_attestation_role',
    'provider_attestation_boot_id', 'issuer_binding_owner_installation_id', 'issuer_binding_role',
    'issuer_binding_release_commit', 'issuer_binding_boot_id'])
def test_resident_projection_cross_joins_refuse(image, field):
    d = f.file_document(image['files'][f._EVIDENCE])
    d[field] = d[field] + 1 if type(d[field]) is int else 'f' * len(d[field])
    image['files'][f._EVIDENCE] = wire(d)
    with pytest.raises(consumer.ReleaseConsumerError):
        f.build_release_owner(image['config'])


@pytest.mark.parametrize('mutation', ['extra', 'bool-as-int', 'enabled'])
def test_disarming_exact_false_object(image, mutation):
    d = f.file_document(image['files'][f._EVIDENCE])
    if mutation == 'extra': d['production_disarming']['extra'] = False
    elif mutation == 'bool-as-int': d['production_disarming']['worker_start'] = 0
    else: d['production_disarming']['commit_prepared_release_transition'] = True
    image['files'][f._EVIDENCE] = wire(d)
    with pytest.raises(consumer.ReleaseConsumerError):
        f.build_release_owner(image['config'])


@pytest.mark.parametrize('field', ['proof_base_sha', 'control_uid', 'python_runtime_provenance_digest'])
def test_control_projection_required_fields(image, field):
    raw = json.loads(image['files'][f._CONTROL]); del raw[field]
    reproject_control(image, json.dumps(raw).encode())
    with pytest.raises(consumer.ReleaseConsumerError):
        f.build_release_owner(image['config'])


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'content', 'size', 'mode'])
def test_complete_manifest_dependency_membership(image, change):
    p = image['config'].release_root / '.executive-release-manifest.json'
    manifest = json.loads(image['files'][p]); entry = manifest['entries'][1]
    if change == 'missing': manifest['entries'].pop(1)
    elif change == 'duplicate': manifest['entries'].append(copy.deepcopy(entry))
    elif change == 'content': entry['sha256'] = 'f' * 64
    elif change == 'size': entry['size'] += 1
    else: entry['mode'] = True
    image['files'][p] = json.dumps(manifest).encode()
    with pytest.raises(consumer.ReleaseConsumerError):
        f.build_release_owner(image['config'])


@pytest.mark.parametrize('name', ['registry_generation', 'staging_generation'])
def test_registry_change_between_two_reads_refuses_before_approval(image, name):
    root = f.build_release_owner(image['config']); original = root._snapshot; calls = []
    def snapshot(transition):
        result = original(transition)
        if not calls:
            d = f.file_document(image['files'][f._REGISTRY])
            if name == 'registry_generation': d[name] += 1
            else: d['transitions'][0][name] += 1
            image['files'][f._REGISTRY] = wire(d)
        calls.append(True)
        return result
    root._snapshot = snapshot
    raw = frame(image, 'approve_release_transition', operation_key='indep-two-reads',
                action=image['effect']['action'], transition_digest=image['transition'])
    with pytest.raises(consumer.ReleaseConsumerError, match='RELEASE_PRECONDITIONS_CHANGED'):
        root.handle(raw, None)
    assert len(calls) == 2


@pytest.mark.parametrize('delta', [0, 86379, 86380, 172800])
def test_socket_restart_history_and_effect_counts(image, installed, delta):
    installed['root_broker']._release_owner = f.build_release_owner(image['config'])
    before = counts(installed['runtime'])
    args = dict(operation_key='indep-socket', action=image['effect']['action'],
                transition_digest=image['transition'])
    approved = installed['call']('approve_release_transition', args)
    assert approved['ok'] is True
    prepared = installed['call']('prepare_release_transition', dict(operation_key=args['operation_key'],
                 approved_transition_ref=approved['approved_transition_ref']))
    assert prepared['ok'] is True
    refused = installed['call']('commit_prepared_release_transition',
                               {'prepared_token': prepared['prepared_token']})
    assert refused['error']['code'] == 'RELEASE_COMMIT_DISARMED'
    image['now'][0] += delta
    installed['now'][0] = image['now'][0] * 1000
    installed['root_broker']._release_owner = f.build_release_owner(image['config'])
    for path in list(image['files']):
        if path == f._REGISTRY or path.is_relative_to(f._STAGING): del image['files'][path]
    principal = dataclasses.replace(image['principal'], issued_at=image['now'][0]-10,
                                    expires_at=image['now'][0]+1000)
    recovered = installed['call']('reconcile_release_transition', {'operation_key': args['operation_key']},
                                 as_principal=principal)
    assert recovered['approval']['approved_transition_ref'] == approved['approved_transition_ref']
    assert counts(installed['runtime']) == (before[0]+1, before[1], before[2])
    assert installed['root_broker']._executor.calls == []


def test_later_stage_publication_supports_approval_and_original_history(disk_image):
    root = f.build_release_owner(disk_image['config'])
    first = root.handle(frame(disk_image, 'approve_release_transition',
        operation_key='before-publication', action=disk_image['effect']['action'],
        transition_digest=disk_image['transition']), None)['approval']
    original = f._STAGING / disk_image['transition']
    content = {path.name: path.read_bytes() for path in original.iterdir()}
    artifact = b'a second synthetic artifact, never executable'
    metadata = f.file_document(content['artifact-metadata.json'])
    metadata.update(artifact_size_bytes=len(artifact), artifact_sha256=f._hash(artifact))
    effect = f.file_document(content['effect.json'])
    effect.update(staged_artifact_digest=f._hash(artifact),
                  staged_content_metadata_digest=f._digest(metadata))
    preconditions = f.file_document(content['preconditions-template.json'])
    preconditions.update(staged_artifact_digest=effect['staged_artifact_digest'],
                         staged_content_metadata_digest=effect['staged_content_metadata_digest'])
    content.update({'release-artifact.bin': artifact, 'artifact-metadata.json': wire(metadata),
                    'effect.json': wire(effect), 'preconditions-template.json': wire(preconditions)})
    digest = f._digest(effect)
    pending = f._STAGING.parent / 'pending'
    pending.mkdir()
    for name, raw in content.items():
        path = pending / name
        path.write_bytes(raw)
        path.chmod(0o400)
    # Model the root producer's publication using user-owned disposable files.
    # macOS requires the moving directory writable to update its parent link.
    f._STAGING.chmod(0o700)
    pending.rename(f._STAGING / digest)
    (f._STAGING / digest).chmod(0o500)
    f._STAGING.chmod(0o500)
    table = f.file_document(f._REGISTRY.read_bytes())
    table['registry_generation'] += 1
    table['transitions'].append(dict(transition_digest=digest, staging_generation=1, state='STAGED'))
    table['transitions'].sort(key=lambda row: row['transition_digest'])
    replacement = f._REGISTRY.with_name('next-registry')
    replacement.write_bytes(wire(table))
    replacement.chmod(0o400)
    replacement.replace(f._REGISTRY)
    second = root.handle(frame(disk_image, 'approve_release_transition',
        operation_key='after-publication', action=effect['action'], transition_digest=digest), None)
    assert second['approval']['transition_digest'] == digest
    request = frame(disk_image, 'reconcile_release_transition', operation_key='before-publication')
    request['approval'] = first
    assert root.handle(request, None)['approval'] == first


@pytest.mark.parametrize('change', ['inode', 'mode', 'acl', 'leaf'])
def test_resident_directory_security_and_leaf_changes_still_refuse(disk_image, monkeypatch, change):
    root = f.build_release_owner(disk_image['config'])
    root._history_trust()
    parent = f._REGISTRATION.parent
    if change == 'inode':
        held = parent.with_name('old-config')
        parent.rename(held)
        parent.mkdir()
        for path in held.iterdir():
            path.rename(parent / path.name)
    elif change == 'mode':
        parent.chmod(0o777)
    elif change == 'acl':
        inode = parent.stat().st_ino
        monkeypatch.setattr(f, 'has_macos_acl', lambda _path, **kw:
                            kw['expected_identity'].st_ino == inode)
    else:
        # Byte-identical replacement is still resident identity drift.
        pending = f._REGISTRATION.with_name('replaced-registration')
        pending.write_bytes(f._REGISTRATION.read_bytes())
        pending.chmod(0o400)
        pending.replace(f._REGISTRATION)
    with pytest.raises(consumer.ReleaseConsumerError):
        root._history_trust()


@pytest.mark.parametrize('delay', [0.25, 5.0, 6.0])
@pytest.mark.parametrize('step', ['legacy', 'boot'])
def test_resident_total_budget_covers_late_steps(disk_image, monkeypatch, delay, step):
    clock = [0.0]
    monkeypatch.setattr(f.time, 'monotonic', lambda: clock[0])
    root = f.build_release_owner(disk_image['config'])
    original_boot = f._boot_id
    def delayed(*_args):
        clock[0] += delay
        return original_boot() if step == 'boot' else None
    if step == 'boot':
        monkeypatch.setattr(f, '_boot_id', delayed)
    else:
        monkeypatch.setattr(broker, 'verify_production_trust', delayed)
    if delay < 5:
        assert root._history_trust()
    else:
        with pytest.raises(consumer.ReleaseConsumerError):
            root._history_trust()


@pytest.mark.parametrize('raw', [b'{"x":{"nested":[NaN]}}',
    b'{"x":[{"nested":Infinity}]}', b'{"x":[-Infinity]}', b'{"x":{"nested":1e999}}'])
def test_nested_nonfinite_values_refuse(raw):
    with pytest.raises(consumer.ReleaseConsumerError):
        f._strict_json(raw)


def test_strict_json_preserves_finite_numbers_and_escaped_unicode():
    assert f._strict_json(b'{"x":1.5,"nested":[-2.75,0.0],"label":"\\u4e2d"}') == {
        'x': 1.5, 'nested': [-2.75, 0.0], 'label': '\u4e2d'}
