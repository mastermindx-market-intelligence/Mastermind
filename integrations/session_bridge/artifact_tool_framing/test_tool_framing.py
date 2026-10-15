"""Inert seal tool/final-answer protocol checks; no provider or historical edits."""
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
spec = importlib.util.spec_from_file_location('tool_framing_subject', target)
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)

TOOL_PREFIX = 'FABRIC_ARTIFACT_SEAL_V1 '
SCOPE = dict(root='original-root', parent='assigning-parent', run_id='new-run', host='ubuntu1')


def packet():
    return subject.encode_packet('Produce a bounded patch.',
        **{k: SCOPE[k] for k in ('root', 'parent', 'run_id')},
        names=['repair.patch'], support_digest='c' * 64)


def manifest():
    return dict(schema=subject.RESULT_SCHEMA, request_sha256='a' * 64, **SCOPE,
        files=[dict(path=subject.directory(SCOPE) + '/repair.patch',
                    bytes=5, sha256=hashlib.sha256(b'patch').hexdigest())])


def run_seal(tmp_path, monkeypatch, capsys, tool_output=False, refuse=None):
    packet_path = tmp_path / 'packet.txt'
    packet_path.write_text(packet())
    calls = []
    def bind(contract, run_id, mode, env, here):
        calls.append('bind')
        assert contract['root'] == SCOPE['root']
        assert contract['parent'] == SCOPE['parent']
        assert run_id == SCOPE['run_id']
        assert mode == 'qwen'
        if refuse == 'bind':
            raise ValueError('fixture_binding_refusal')
    def observed(contract, host):
        calls.append('observe')
        assert calls == ['bind', 'observe']
        assert host == SCOPE['host']
        if refuse == 'observe':
            raise ValueError('fixture_observation_refusal')
        return manifest()
    monkeypatch.setattr(subject, 'bind', bind)
    monkeypatch.setattr(subject, 'observed_manifest', observed)
    monkeypatch.setenv('REMOTE_SUB_RUN_ID', SCOPE['run_id'])
    monkeypatch.setenv('MODE', 'qwen')
    monkeypatch.setenv('LANE_REMOTE_HOST', SCOPE['host'])
    monkeypatch.setattr(sys, 'argv', ['artifact_production.py', 'seal', '--packet', str(packet_path)]
                        + (['--tool-output'] if tool_output else []))
    subject.main()
    assert calls == ['bind', 'observe']
    return capsys.readouterr().out


def test_generated_packet_uses_distinct_tool_output_and_one_terminal_line():
    encoded = packet()
    assert 'seal --tool-output --packet ' in encoded
    assert 'Change only the prefix' in encoded
    assert TOOL_PREFIX.rstrip() in encoded
    assert 'ONE complete FABRIC_ARTIFACTS_V1 JSON line' in encoded
    assert subject.parse_packet(encoded)['names'] == ['repair.patch']


def test_actual_helper_tool_transcript_plus_final_answer_is_unambiguous(tmp_path, monkeypatch, capsys):
    diagnostic = run_seal(tmp_path, monkeypatch, capsys, tool_output=True)
    assert diagnostic == TOOL_PREFIX + subject.reader.canonical(manifest()).decode() + '\n'
    # The worker follows the packet: copy JSON exactly; replace only the prefix.
    final_line = subject.RESULT_PREFIX + diagnostic[len(TOOL_PREFIX):]
    transcript = 'tool stdout:\n' + diagnostic + '\nfinal answer:\n' + final_line
    before = transcript.encode()
    assert subject.manifest_from_stdout(transcript, **SCOPE) == manifest()
    assert transcript.encode() == before


def test_legacy_seal_output_remains_byte_compatible(tmp_path, monkeypatch, capsys):
    line = run_seal(tmp_path, monkeypatch, capsys)
    assert line == subject.RESULT_PREFIX + subject.reader.canonical(manifest()).decode() + '\n'
    assert subject.manifest_from_stdout(line, **SCOPE) == manifest()


@pytest.mark.parametrize('refuse', ['bind', 'observe'])
def test_tool_mode_preserves_binding_and_observation_refusals(tmp_path, monkeypatch, capsys, refuse):
    with pytest.raises(ValueError, match='fixture_.*_refusal'):
        run_seal(tmp_path, monkeypatch, capsys, tool_output=True, refuse=refuse)
    assert capsys.readouterr().out == ''


def test_tool_diagnostic_alone_is_not_terminal_evidence():
    with pytest.raises(ValueError, match='missing_or_duplicate'):
        subject.manifest_from_stdout(TOOL_PREFIX + subject.reader.canonical(manifest()).decode(), **SCOPE)


@pytest.mark.parametrize('different', [False, True])
def test_two_terminal_lines_still_refuse_identical_or_conflicting(different):
    first = manifest()
    second = copy.deepcopy(first)
    if different:
        second['files'][0]['sha256'] = 'b' * 64
    text = '\n'.join(subject.RESULT_PREFIX + subject.reader.canonical(v).decode() for v in (first, second))
    with pytest.raises(ValueError, match='missing_or_duplicate'):
        subject.manifest_from_stdout(text, **SCOPE)


def test_tool_diagnostic_cannot_mask_wrong_terminal_scope_or_file_digest(monkeypatch):
    expected = manifest()
    diagnostic = TOOL_PREFIX + subject.reader.canonical(expected).decode() + '\n'
    wrong = copy.deepcopy(expected)
    wrong['parent'] = 'different-parent'
    with pytest.raises(ValueError, match='artifact_manifest_scope'):
        subject.manifest_from_stdout(diagnostic + subject.RESULT_PREFIX + json.dumps(wrong), **SCOPE)
    class Owner:
        def verify(self):
            pass
    monkeypatch.setattr(subject, 'observed_manifest', lambda *a, **kw: expected)
    wrong = copy.deepcopy(expected)
    wrong['files'][0]['sha256'] = 'b' * 64
    with pytest.raises(ValueError, match='artifact_manifest_mismatch'):
        subject.verify_completion(SCOPE, Owner(), diagnostic + subject.RESULT_PREFIX + json.dumps(wrong), SCOPE['host'])


def test_packet_body_cannot_inject_the_new_reserved_marker():
    with pytest.raises(ValueError, match='artifact_contract_reserved_marker'):
        subject.encode_packet(TOOL_PREFIX + '{}',
            **{k: SCOPE[k] for k in ('root', 'parent', 'run_id')},
            names=['repair.patch'], support_digest='c' * 64)
