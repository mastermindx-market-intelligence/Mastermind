"""Inert framing regressions; no worker, transport, export or historical edit."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

EXT = Path.home() / '.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
sys.path.insert(0, str(EXT))
target = Path(os.environ.get('ARTIFACT_SOURCE', Path(__file__).with_name('artifact_production.py')))
spec = importlib.util.spec_from_file_location('framing_subject', target)
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)

SCOPE = dict(root='test-root', parent='test-parent', run_id='test-run', host='ubuntu2')


def manifest():
    return dict(schema=subject.RESULT_SCHEMA, request_sha256='a' * 64, **SCOPE,
                files=[dict(path=subject.directory(SCOPE) + '/repair.patch',
                            bytes=5, sha256=hashlib.sha256(b'patch').hexdigest())])


def render(value, style='marker'):
    raw = json.dumps(value, separators=(',', ':'))
    if style == 'plain':
        return subject.RESULT_PREFIX + raw
    if style == 'full':
        return '**' + subject.RESULT_PREFIX + raw + '**'
    return '**' + subject.RESULT_PREFIX.rstrip() + '** `' + raw + '`'


@pytest.mark.parametrize('style', ['plain', 'full', 'marker'])
def test_supported_frame_keeps_identity_and_input_bytes(style):
    text = render(manifest(), style)
    before = text.encode()
    assert subject.manifest_from_stdout(text, **SCOPE) == manifest()
    assert text.encode() == before


@pytest.mark.parametrize('other', ['plain', 'full', 'marker'])
def test_duplicate_across_frames_refuses(other):
    with pytest.raises(ValueError, match='missing_or_duplicate'):
        subject.manifest_from_stdout(render(manifest()) + '\n' + render(manifest(), other), **SCOPE)


@pytest.mark.parametrize('transform', [
    lambda s: s[:-1],
    lambda s: s + ' trailing prose',
    lambda s: s.replace('** `', '**  `', 1),
    lambda s: s.replace('** `', '** ```', 1) + '``',
    lambda s: s.replace('"files":', '"files":[],"files":', 1),
    lambda s: s.replace('"schema":', '"schema":null,"schema":', 1),
])
def test_malformed_or_ambiguous_frame_refuses(transform):
    with pytest.raises((ValueError, TypeError)):
        subject.manifest_from_stdout(transform(render(manifest())), **SCOPE)


@pytest.mark.parametrize('field', ['root', 'parent', 'run_id', 'host'])
def test_wrong_scope_refuses(field):
    value = manifest()
    value[field] = 'other'
    with pytest.raises(ValueError, match='artifact_manifest_scope'):
        subject.manifest_from_stdout(render(value), **SCOPE)


@pytest.mark.parametrize('change', [
    {'path': '/tmp/fabric-other/repair.patch'},
    {'bytes': 0},
    {'bytes': True},
    {'sha256': 'not-a-digest'},
])
def test_file_constraints_unchanged(change):
    value = manifest()
    value['files'][0].update(change)
    with pytest.raises(ValueError):
        subject.manifest_from_stdout(render(value), **SCOPE)


def test_wrapper_limit_remains_bounded():
    with pytest.raises(ValueError, match='artifact_manifest_wrapper'):
        subject.manifest_from_stdout('**FABRIC_ARTIFACTS_V1** `' + 'x' * subject.reader.MAX_REQUEST + '`', **SCOPE)


def test_parser_acceptance_does_not_skip_actual_file_match(monkeypatch):
    class Owner:
        def verify(self):
            pass
    expected = manifest()
    monkeypatch.setattr(subject, 'observed_manifest', lambda *a, **kw: expected)
    assert subject.verify_completion(SCOPE, Owner(), render(expected), SCOPE['host']) == expected
    different = copy.deepcopy(expected)
    different['files'][0]['sha256'] = 'b' * 64
    with pytest.raises(ValueError, match='artifact_manifest_mismatch'):
        subject.verify_completion(SCOPE, Owner(), render(different), SCOPE['host'])


def test_absent_original_completion_seal_still_refuses():
    import artifact_delivery
    process = dict(schema='mastermind.local_owned_process_receipt.v1', returncode=0)
    with pytest.raises((KeyError, ValueError)):
        artifact_delivery.validate_ordinary_producer(SCOPE, render(manifest()).encode(), json.dumps(process).encode())


def test_new_packet_keeps_exact_line_instruction_and_digest():
    encoded = subject.encode_packet('Bounded task.', root=SCOPE['root'], parent=SCOPE['parent'],
                                    run_id=SCOPE['run_id'], names=['repair.patch'], support_digest='c' * 64)
    assert 'Do not add emphasis, backticks, code fences or prose to that line.' in encoded
    assert subject.parse_packet(encoded)['names'] == ['repair.patch']
