"""Original live-handle provenance and publication mechanics, not full START.

Harmless local child and inert identity/cleanup observations; no provider or
real /proc, realm, authentication or policy qualification is exercised here.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_fabric_owned_process_phases import lr, begin
from test_fabric_bound_controller_wire import patched
from test_fabric_reserved_attended_launch import fixture
from integrations.session_bridge.bound_launch_capture.fabric_reserved_attended_launch import prepare_reserved_attended_launch


def encode(record):
    return json.dumps(record, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode()


def active(lr, tmp_path):
    owner, release = begin(lr, tmp_path, cwd=tmp_path, input_text='original prompt',
                          env={'PATH': '/usr/bin', 'PRIVATE_TOKEN': 'do-not-retain-value'})
    holds = []
    owner._original_lease = SimpleNamespace(hold_for_reconciliation=holds.append)
    owner._original_preparation = SimpleNamespace(environment={'PATH': '/usr/bin'})
    owner._original_start_context = dict(binding={'attempt_id': owner.label},
        request_sha256='a' * 64, physical_binding_sha256='b' * 64)
    owner._original_start_receipt_path = tmp_path / 'original.start.json'
    identity = owner.process_identity
    ref = dict(run_id=owner.label, pid=identity['pid'], pgid=identity['pgid'],
        session_id=identity['session_id'], boot_session_id=identity['boot_id'],
        process_start_identity=identity['process_start_identity'],
        launch_nonce=owner.launch_nonce, started_at=owner.started_at,
        **{k: identity[k] for k in ('effective_uid', 'effective_gid', 'real_uid', 'real_gid')})
    att_id = {k: identity[k] for k in ('pid', 'pgid', 'session_id', 'boot_id',
        'effective_uid', 'effective_gid', 'real_uid', 'real_gid')}
    att_id['start_identity'] = identity['process_start_identity']
    att = dict(launch_nonce=owner.launch_nonce, process_identity=att_id,
        rendered_argv=owner.invocation['command'],
        environment_keys=owner.invocation['environment_keys'],
        prompt_sha256=owner.invocation['prompt_sha256'], workspace_identity={'path': str(tmp_path)})
    result = dict(adapter_id='attended-fabric', **owner._original_start_context,
                  process_ref=ref, launch_attestation=att)
    record = dict(schema='mastermind.fabric_owned_complete_start/v1',
        contract_name='fixture-not-an-attestation', run_id=owner.label,
        adapter_id='attended-fabric', request_sha256='a' * 64,
        physical_binding_sha256='b' * 64, start_result=result, retained_at=owner.started_at)
    return owner, release, holds, record


def test_actual_invocation_is_retained_without_prompt_or_secret_values(lr, tmp_path):
    owner, release, _, _ = active(lr, tmp_path)
    invocation = owner.invocation
    assert invocation['cwd'] == str(tmp_path) and invocation['shell'] is False
    assert invocation['prompt_sha256'] == hashlib.sha256(b'original prompt').hexdigest()
    assert 'PRIVATE_TOKEN' in invocation['environment_keys']
    assert 'do-not-retain-value' not in json.dumps(invocation)
    assert 'original prompt' not in json.dumps(invocation)
    invocation['command'].append('mutated')
    assert 'mutated' not in owner.invocation['command']
    assert len(owner.launch_nonce) == 32 and owner.started_at
    release.touch(); lr.finish_owned_process(owner)


def test_nonce_failure_precedes_exec_gate_and_spawn(lr, tmp_path, monkeypatch):
    def unavailable(*args): raise OSError('inert nonce unavailable')
    monkeypatch.setattr(lr.os, 'urandom', unavailable)
    monkeypatch.setattr(lr.os, 'pipe', lambda: pytest.fail('gate opened before provenance'))
    monkeypatch.setattr(lr.subprocess, 'Popen', lambda *a, **kw: pytest.fail('spawn before provenance'))
    with pytest.raises(OSError, match='nonce unavailable'):
        begin(lr, tmp_path)
    assert lr._EXECUTION_OWNER is None


def test_same_environment_keys_cannot_hide_changed_prepared_controls(lr, tmp_path):
    owner, release, holds, record = active(lr, tmp_path)
    owner._original_preparation = SimpleNamespace(environment={'PATH': '/different'})
    with pytest.raises(lr.LaneRuntimeError, match='prepared_environment_changed'):
        lr.retain_owned_start_bytes(owner, encode(record))
    assert holds and owner.process.poll() is None
    release.touch(); lr.finish_owned_process(owner)


def test_once_only_retention_does_not_transfer_original_process_or_lease(lr, tmp_path):
    owner, release, holds, record = active(lr, tmp_path)
    payload = encode(record)
    before = owner.process, owner._steps, owner._original_lease
    digest = lr.retain_owned_start_bytes(owner, payload)
    assert digest == hashlib.sha256(payload).hexdigest()
    assert owner._original_start_receipt_path.read_bytes() == payload
    assert owner._original_start_receipt_path.stat().st_mode & 0o777 == 0o400
    assert (owner.process, owner._steps, owner._original_lease) == before
    assert owner.result is None and owner.process.poll() is None and holds == []
    with pytest.raises(lr.LaneRuntimeError, match='already_attempted'):
        lr.retain_owned_start_bytes(owner, payload)
    release.touch(); assert lr.finish_owned_process(owner).cleanup_proven


@pytest.mark.parametrize('field', ['launch_nonce', 'started_at', 'pid', 'process_start_identity'])
def test_wrong_original_process_provenance_refuses_without_resend(lr, tmp_path, field):
    owner, release, holds, record = active(lr, tmp_path)
    record['start_result']['process_ref'][field] = 'changed'
    with pytest.raises(lr.LaneRuntimeError, match='invocation_changed'):
        lr.retain_owned_start_bytes(owner, encode(record))
    assert holds == ['owned_start_publication_unconfirmed']
    assert not owner._original_start_receipt_path.exists()
    assert owner.process.poll() is None and owner.result is None
    with pytest.raises(lr.LaneRuntimeError, match='already_attempted'):
        lr.retain_owned_start_bytes(owner, encode(record))
    release.touch(); lr.finish_owned_process(owner)


@pytest.mark.parametrize('field', ['rendered_argv', 'environment_keys', 'prompt_sha256', 'workspace_identity'])
def test_descriptor_alone_cannot_replace_actual_invocation(lr, tmp_path, field):
    owner, release, holds, record = active(lr, tmp_path)
    record['start_result']['launch_attestation'][field] = {'path': '/different'} if field == 'workspace_identity' else 'changed'
    with pytest.raises(lr.LaneRuntimeError, match='invocation_changed'):
        lr.retain_owned_start_bytes(owner, encode(record))
    assert holds and owner.process.poll() is None
    release.touch(); lr.finish_owned_process(owner)


@pytest.mark.parametrize('failure_at', ['file', 'directory'])
def test_fsync_uncertainty_holds_original_lease_and_never_republishes(lr, tmp_path, monkeypatch, failure_at):
    owner, release, holds, record = active(lr, tmp_path)
    real = lr.os.fsync
    calls = []
    def uncertain(fd):
        calls.append(fd)
        if len(calls) == (1 if failure_at == 'file' else 3):
            raise OSError('inert durability uncertainty')
        return real(fd)
    with monkeypatch.context() as scoped:
        scoped.setattr(lr.os, 'fsync', uncertain)
        with pytest.raises(lr.LaneRuntimeError, match='publication_failed'):
            lr.retain_owned_start_bytes(owner, encode(record))
    assert holds == ['owned_start_publication_unconfirmed']
    assert owner._start_record_sha256 is None
    with pytest.raises(lr.LaneRuntimeError, match='already_attempted'):
        lr.retain_owned_start_bytes(owner, encode(record))
    assert owner.process.poll() is None
    release.touch(); lr.finish_owned_process(owner)


def test_existing_carrier_never_becomes_exact_replay_authority(lr, tmp_path):
    owner, release, holds, record = active(lr, tmp_path)
    payload = encode(record)
    owner._original_start_receipt_path.write_bytes(payload)
    with pytest.raises(lr.LaneRuntimeError, match='publication_failed'):
        lr.retain_owned_start_bytes(owner, payload)
    assert owner._original_start_receipt_path.read_bytes() == payload and holds
    release.touch(); lr.finish_owned_process(owner)


def test_settled_or_foreign_handle_cannot_publish(lr, tmp_path):
    owner, release, _, record = active(lr, tmp_path)
    with pytest.raises(lr.LaneRuntimeError, match='owner_thread_required'):
        lr.retain_owned_start_bytes(object(), encode(record))
    release.touch(); lr.finish_owned_process(owner)
    with pytest.raises(lr.LaneRuntimeError, match='not_live'):
        lr.retain_owned_start_bytes(owner, encode(record))
    assert not owner._original_start_receipt_path.exists()


@pytest.mark.parametrize('occupied', [False, True])
def test_reserved_seam_binds_real_descriptor_request_and_carrier_before_spawn(tmp_path, occupied):
    payload, kw = fixture(tmp_path)
    prepared = prepare_reserved_attended_launch(payload, **kw)
    src = patched(tmp_path, 'remote_sub_exec.py', 'EXECUTOR_SOURCE.json')
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)
              and n.name == '_begin_reserved_attended_under_lease')
    owners, effects = [], []
    receipt = tmp_path / 'original.process.jsonl'
    start = receipt.with_suffix('.start.json')
    if occupied: start.write_text('unknown original publication')
    def begin_mock(**args):
        effects.append(args); owner = SimpleNamespace(); owners.append(owner); return owner
    def safe_parent(path):
        assert path == start
    ns = dict(json=json, Path=Path, os=os, LaneRuntimeError=RuntimeError,
        _launch_receipt_directory=safe_parent,
        _prepare_reserved_attended_under_lease=lambda **kw: (prepared, prepared.lane_runtime_arguments(), lambda: None),
        _begin_lease_process=begin_mock)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), '<actual-executor-function>', 'exec'), ns)
    args = dict(payload=payload, receipt=receipt, lease=object(), state={}, key='run-1')
    if occupied:
        with pytest.raises(RuntimeError, match='carrier_exists'): ns[fn.name](**args)
        assert effects == []
    else:
        owner, commands = ns[fn.name](**args)
        assert owner._original_preparation is prepared.descriptor
        assert owner._original_start_receipt_path == start
        assert owner._original_start_context['request_sha256'] == prepared.request_sha256
        assert owner._original_start_context['binding'] == payload['binding']
        assert commands == prepared.validation_commands and len(effects) == 1


def test_capture_option_does_not_escape_actual_strict_preparation_signature(tmp_path,monkeypatch):
    """Actual source functions reject inert authority before any preparation/effect."""
    from control_plane.fabric_control_start import ControlStartRefused
    from integrations.session_bridge.bound_launch_capture import fabric_reserved_attended_launch
    monkeypatch.setitem(__import__('sys').modules,'fabric_reserved_attended_launch',fabric_reserved_attended_launch)
    source=patched(tmp_path,'remote_sub_exec.py','EXECUTOR_SOURCE.json')
    names={'_prepare_reserved_attended_under_lease','_begin_reserved_attended_under_lease'}
    nodes=[node for node in ast.parse(source).body if isinstance(node,ast.FunctionDef) and node.name in names]
    ns=dict(json=json,Path=Path,os=os,LaneRuntimeError=RuntimeError)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<actual-capture-option-composition>','exec'),ns)
    with pytest.raises(ControlStartRefused,match='authenticated_original_owner_required'):
        ns['_begin_reserved_attended_under_lease'](owned_capture=True,payload={},authority=object(),
            preparation={},lease=object(),state={},key='original',receipt=tmp_path/'receipt',
            nice=0,check_original_owner=lambda _: None)
