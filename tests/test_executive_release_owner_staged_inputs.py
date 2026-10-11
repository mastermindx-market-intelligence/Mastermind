"""Staged input contract and consumer compatibility; never installation proof."""
import copy
import dataclasses
import hashlib
import traceback

import pytest

from control_plane import executive_release_factory as f
from ops.executive_os import release_owner_staged_inputs as subject
from tests.test_executive_release_factory import image, inputs, wire


def arguments(image):
    docs = image['docs']
    template = docs['preconditions-template.json']
    keys = ('owner_installation_id', 'target_ref', 'boot_id',
            'from_installed_manifest_digest', 'installed_configuration_digest',
            'python_runtime_provenance_digest', 'provider_binary_attestation_digest',
            'authority_policy_hash', 'issuer_binding_digest')
    context = {k: template[k] for k in keys}
    context.update({k: image['effect'][k] for k in ('from_release_commit', 'from_release_tree')})
    return dict(artifact=image['files'][image['directory'] / 'release-artifact.bin'],
                **{key.replace('-', '_'): wire(docs[key + '.json']) for key in (
                    'installer-profile', 'configuration-transition', 'source-proof',
                    'compatibility-proof', 'rollback-evidence')},
                retained_paths=copy.deepcopy(docs['preservation-plan.json']['retained_paths']),
                excluded_secret_classes=copy.deepcopy(docs['preservation-plan.json']['excluded_secret_classes']),
                now_seconds=image['now'][0], installed_context=context)


def consume(image, result):
    stage = f._STAGING / result.transition_digest
    for name, raw in result.files:
        image['files'][stage / name] = raw
    image['files'][f._REGISTRY] = wire(dict(
        schema='mastermind.executive_release_owner_staged_registry/v1',
        registration_generation=1, registry_generation=2,
        transitions=[dict(transition_digest=result.transition_digest,
                          staging_generation=2, state='STAGED')]))
    return f.build_release_owner(image['config'])._snapshot(result.transition_digest)


def test_upgrade_exact_bytes_and_actual_consumer(image):
    kw = arguments(image)
    before = copy.deepcopy(kw)
    result = subject.compile_staged_inputs(**kw)
    assert kw == before
    expected = {p.name: raw for p, raw in image['files'].items() if p.parent == image['directory']}
    assert dict(result.files) == expected
    assert result.transition_digest == image['transition']
    assert consume(image, result).effect.to_dict() == image['effect']
    assert subject.compile_staged_inputs(**kw) == result
    assert type(result.files) is tuple and all(type(row) is tuple and type(row[1]) is bytes for row in result.files)
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        result.transition_digest = '0' * 64


def test_ancestor_rollback_actual_consumer(image):
    kw = arguments(image)
    profile = f.file_document(kw['installer_profile'])
    profile.update(action='executive.release.rollback', source_policy_mode='frozen_accepted_ancestor')
    kw['installer_profile'] = wire(profile)
    source = f.file_document(kw['source_proof'])
    source.update(source_policy_mode='frozen_accepted_ancestor', to_release_commit='c' * 40, to_release_tree='d' * 40)
    kw['source_proof'] = wire(source)
    compatibility = f.file_document(kw['compatibility_proof'])
    compatibility.update(to_release_commit=source['to_release_commit'], to_release_tree=source['to_release_tree'],
                         installer_profile_digest=hashlib.sha256(f.contract.canonical_release_bytes(profile)).hexdigest())
    kw['compatibility_proof'] = wire(compatibility)
    rollback = f.file_document(kw['rollback_evidence'])
    rollback.update(action=profile['action'], to_release_commit=source['to_release_commit'], to_release_tree=source['to_release_tree'],
                    original_upgrade_request_id='p4r-' + 'a' * 48,
                    original_terminal_or_reconciliation_digest='b' * 64,
                    retained_artifact_digest='c' * 64, preimage_digest='d' * 64,
                    current_compatibility_digest='e' * 64)
    kw['rollback_evidence'] = wire(rollback)
    result = subject.compile_staged_inputs(**kw)
    snapshot = consume(image, result)
    effect = snapshot.effect.to_dict()
    assert effect['action'] == 'executive.release.rollback'
    assert effect['installer_source_tree'] == source['installer_source_tree']
    assert effect['rollback_evidence']['original_upgrade_request_id'] == rollback['original_upgrade_request_id']
    assert effect['to_release_commit'] == 'c' * 40


@pytest.mark.parametrize('key,value', [
    ('boot_id', 'boot-1'), ('boot_id', '00000000-0000-0000-0000-000000000000'),
    ('owner_installation_id', '11111111-1111-4111-8111-11111111111X'),
    ('issuer_binding_digest', 'A' * 64), ('from_release_tree', 'f' * 39),
    ('installed_configuration_digest', False), ('unexpected', 'value'),
])
def test_closed_context(image, key, value):
    kw = arguments(image)
    kw['installed_context'][key] = value
    with pytest.raises(subject.StagedInputError):
        subject.compile_staged_inputs(**kw)


@pytest.mark.parametrize('field', ['installer_profile', 'configuration_transition', 'source_proof', 'compatibility_proof', 'rollback_evidence'])
@pytest.mark.parametrize('suffix', [b'\n', b' ', b'\x00'])
def test_exact_canonical_file_delimiter(image, field, suffix):
    kw = arguments(image)
    kw[field] += suffix
    with pytest.raises(subject.StagedInputError):
        subject.compile_staged_inputs(**kw)


@pytest.mark.parametrize('age,accepted', [(86399, True), (86400, False), (86401, False)])
def test_exact_freshness_boundary(image, age, accepted):
    kw = arguments(image)
    kw['now_seconds'] = 180 + age
    if accepted:
        subject.compile_staged_inputs(**kw)
    else:
        with pytest.raises(subject.StagedInputError):
            subject.compile_staged_inputs(**kw)


@pytest.mark.parametrize('path', ['/tmp/value', '../value', 'a/../b', 'a//b', 'a/./b', 'a\\b', 'a\x00b', ''])
def test_preservation_path_refusal(image, path):
    kw = arguments(image)
    kw['retained_paths'] = [path]
    with pytest.raises(subject.StagedInputError):
        subject.compile_staged_inputs(**kw)


def test_error_traceback_does_not_disclose_input(image):
    kw = arguments(image)
    value = f.file_document(kw['source_proof'])
    value['unexpected'] = 'DO_NOT_DISCLOSE_TEST_MARKER_51c08c'
    kw['source_proof'] = wire(value)
    try:
        subject.compile_staged_inputs(**kw)
    except subject.StagedInputError as error:
        formatted = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        assert value['unexpected'] not in formatted
    else:
        pytest.fail('invalid source accepted')


def test_compile_has_no_ambient_effects(image, monkeypatch):
    import builtins
    import os
    from pathlib import Path
    import socket
    import subprocess
    import time
    import uuid
    kw = arguments(image)
    def forbidden(*args, **kwargs):
        raise AssertionError('compiler used ambient effect')
    with monkeypatch.context() as guard:
        for module, names in (
            (builtins, ('open',)), (os, ('open', 'getenv', 'urandom')),
            (Path, ('read_bytes', 'read_text', 'write_bytes', 'write_text')),
            (socket, ('socket', 'create_connection')),
            (subprocess, ('Popen', 'run', 'check_output')),
            (time, ('time', 'time_ns', 'monotonic', 'monotonic_ns')),
            (uuid, ('uuid4',)),
        ):
            for name in names:
                guard.setattr(module, name, forbidden)
        result = subject.compile_staged_inputs(**kw)
    assert result.transition_digest == image['transition']


@pytest.mark.parametrize('document,field,value', [
    ('installer_profile', 'profile_version', True),
    ('installer_profile', 'profile_version', 0),
    ('installer_profile', 'profile_version', 1 << 31),
    ('installer_profile', 'profile_id', 'not an identifier'),
    ('installer_profile', 'repository', 'other/repository'),
    ('installer_profile', 'platform', 'linux'),
    ('installer_profile', 'architecture', 'unknown'),
    ('installer_profile', 'source_policy_mode', 'unknown'),
    ('source_proof', 'from_release_commit', 'f' * 40),
    ('source_proof', 'from_release_tree', 'f' * 40),
    ('source_proof', 'protected_source_tree', 'f' * 40),
    ('source_proof', 'installer_source_commit', 'f' * 40),
    ('source_proof', 'to_release_tree', 'f' * 40),
    ('source_proof', 'source_policy_mode', 'frozen_accepted_ancestor'),
    ('source_proof', 'producer', 'unqualified'),
    ('configuration_transition', 'from_configuration_digest', 'f' * 64),
    ('configuration_transition', 'to_configuration_digest', 'not-a-digest'),
    ('configuration_transition', 'changed_keys', []),
    ('configuration_transition', 'restart_roles', ['b', 'a']),
    ('compatibility_proof', 'to_release_commit', 'f' * 40),
    ('compatibility_proof', 'installer_profile_digest', 'f' * 64),
    ('compatibility_proof', 'result', 'FAIL'),
    ('compatibility_proof', 'checks', ['duplicate', 'duplicate']),
    ('rollback_evidence', 'action', 'executive.release.rollback'),
    ('rollback_evidence', 'from_release_tree', 'f' * 40),
    ('rollback_evidence', 'result', 'FAIL'),
    ('rollback_evidence', 'checks', [False]),
    ('rollback_evidence', 'original_upgrade_request_id', 'p4r-' + 'a' * 48),
])
def test_leaf_identity_schema_and_result_refusals(image, document, field, value):
    kw = arguments(image)
    doc = f.file_document(kw[document])
    doc[field] = value
    kw[document] = wire(doc)
    with pytest.raises(subject.StagedInputError):
        subject.compile_staged_inputs(**kw)


@pytest.mark.parametrize('document', ['installer_profile', 'configuration_transition', 'source_proof', 'compatibility_proof', 'rollback_evidence'])
@pytest.mark.parametrize('change', ['missing_schema', 'extra_key', 'wrong_schema'])
def test_closed_leaf_shapes(image, document, change):
    kw = arguments(image)
    doc = f.file_document(kw[document])
    if change == 'missing_schema':
        del doc['schema']
    elif change == 'wrong_schema':
        doc['schema'] = 'unknown.schema/v1'
    else:
        doc['unexpected'] = False
    kw[document] = wire(doc)
    with pytest.raises(subject.StagedInputError):
        subject.compile_staged_inputs(**kw)


@pytest.mark.parametrize('raw', [b'', bytearray(b'value'), None, 'value'])
def test_artifact_input_type_and_empty_refusal(image, raw):
    kw = arguments(image)
    kw['artifact'] = raw
    with pytest.raises(subject.StagedInputError):
        subject.compile_staged_inputs(**kw)


def test_artifact_byte_ceiling(image, monkeypatch):
    assert subject._MAX_ARTIFACT_BYTES == 536_870_912
    kw = arguments(image)
    ceiling = len(kw['artifact'])
    monkeypatch.setattr(subject, '_MAX_ARTIFACT_BYTES', ceiling)
    subject.compile_staged_inputs(**kw)
    kw['artifact'] += b'x'
    with pytest.raises(subject.StagedInputError):
        subject.compile_staged_inputs(**kw)


@pytest.mark.parametrize('now', [False, -1, 1.0, '200', 1 << 63, 179])
def test_explicit_clock_type_bounds_and_future_receipt(image, now):
    kw = arguments(image)
    kw['now_seconds'] = now
    with pytest.raises(subject.StagedInputError):
        subject.compile_staged_inputs(**kw)


@pytest.mark.parametrize('raw', [b'{}\n', b'[]\n', b'{"x":null}\n', b'{"x":NaN}\n', b'{"x":1e999}\n',
                               b'{"x":1,"x":2}\n', b'\xff\n', b' ' * 16385 + b'\n',
                               b'{"x":' + b'[' * 10 + b'0' + b']' * 10 + b'}\n'])
def test_bounded_strict_leaf_parser(image, raw):
    kw = arguments(image)
    kw['installer_profile'] = raw
    with pytest.raises(subject.StagedInputError):
        subject.compile_staged_inputs(**kw)


def test_array_maxima_and_detached_result(image):
    kw = arguments(image)
    kw['retained_paths'] = [f'config/file-{i:03d}' for i in range(128)]
    kw['excluded_secret_classes'] = [f'class-{i:03d}' for i in range(128)]
    doc = f.file_document(kw['compatibility_proof'])
    doc['checks'] = [f'check-{i:03d}' for i in range(64)]
    kw['compatibility_proof'] = wire(doc)
    result = subject.compile_staged_inputs(**kw)
    original = dict(result.files)['preservation-plan.json']
    kw['retained_paths'].append('late/path')
    assert dict(result.files)['preservation-plan.json'] == original
    with pytest.raises(subject.StagedInputError):
        subject.compile_staged_inputs(**kw)


@pytest.mark.parametrize('field', ['retained_paths', 'excluded_secret_classes'])
@pytest.mark.parametrize('value', [[], ['b', 'a'], ['a', 'a'], ['a', False], ('a',)])
def test_preservation_array_shapes(image, field, value):
    kw = arguments(image)
    kw[field] = value
    with pytest.raises(subject.StagedInputError):
        subject.compile_staged_inputs(**kw)
