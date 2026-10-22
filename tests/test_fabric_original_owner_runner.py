"""Actual compiler/shared runner; owner, lease and host admission are inert fixtures.

One positive invokes a harmless local executable through the incumbent runtime.
No provider, real credentials, remote process probe, live lease or START attestation.
"""
import ast
import dataclasses
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from control_plane import fabric_control_start as control
from control_plane.executive_worker_broker import PeerCredentials
from control_plane.executive_fabric_bridge_broker import start_request_sha256
from integrations.session_bridge.bound_launch_capture.fabric_reserved_attended_launch import ReservedLaunchRefused, prepare_reserved_attended_launch
from test_fabric_reserved_attended_launch import fixture

BUNDLE = Path(__file__).resolve().parents[1] / 'integrations/session_bridge/bound_launch_capture'
RUNTIME = BUNDLE / 'fixtures/lane_runtime.base.py'
from test_fabric_bound_controller_wire import patched
from test_claude_subscription_worker import (_inject_owner_test_keys, _documents, _owner_seal)
from control_plane.claude_subscription_worker import _resolve_catalog_pair
from integrations.session_bridge.bound_launch_capture import fabric_reserved_attended_launch
rs = importlib.util.spec_from_file_location('fixture_lane_runtime', RUNTIME)
lr = importlib.util.module_from_spec(rs)
sys.modules[rs.name] = lr
rs.loader.exec_module(lr)


class HeldOriginalLease:
    """Explicit fixture; does not confer host or provider admission."""
    def __init__(self): self.holds = []
    def hold_for_reconciliation(self, reason): self.holds.append(reason)


def runner(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "fabric_reserved_attended_launch", fabric_reserved_attended_launch)
    src = tmp_path / 'remote_sub_exec.py'
    tree = ast.parse(patched(tmp_path, 'remote_sub_exec.py', 'EXECUTOR_SOURCE.json'))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in {'_run_lease_process', '_run_reserved_attended_under_lease',
                                '_prepare_reserved_attended_under_lease', '_retain_original_cleanup_hold',
                                '_verify_reserved_realm_observation'}]
    ns = dict(json=json, os=__import__("os"), Path=Path, install_signal_cleanup=lambda **kw: None,
              run_owned_process=lr.run_owned_process, OwnedProcessStartError=lr.OwnedProcessStartError,
              cleanup_receipt_is_proven=lr.cleanup_receipt_is_proven)
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(src), 'exec'), ns)
    return ns


def setup(tmp_path, monkeypatch):
    payload, kw = fixture(tmp_path)
    bindings, profiles = _documents()
    binding, profile, _ = _resolve_catalog_pair("glm-coding-plan.claude-code-anthropic",
        bindings_document=bindings, profiles_document=profiles)
    kw['binding'], kw['profile'] = binding, profile
    from control_plane.codex_provider_realm import SubscriptionRealmOwner, _SUBSCRIPTION_REALM_OWNER_SEAL
    from control_plane.subscription_catalog import compose_catalog_digest
    from control_plane.executive_fabric_adapter import FabricHostBinding
    physical = FabricHostBinding(socket_path=str(tmp_path/'inert.sock'), host_ref='inert-host',
        worker_id=kw['policy'].worker_id, worker_uid=kw['policy'].worker_uid,
        worker_gid=kw['policy'].worker_gid, bridge_uid=kw['policy'].worker_uid,
        provider=binding.provider, model=binding.model_for(profile,kw['model_class']),
        worker_source_config_digest='a'*64, execution_profile_digest='e'*64,
        service_source_sha256='f'*64, provider_home=str(kw['policy'].provider_home),
        binary_sha256=kw['binary'].sha256, permission_profile_sha256='b'*64)
    payload['physical_binding_sha256']=physical.digest
    kw['correlation']['runtime_binding']['physical_binding_sha256']=physical.digest
    owner = SubscriptionRealmOwner(tmp_path / 'inert-root-config', 'a' * 64, _SUBSCRIPTION_REALM_OWNER_SEAL)
    observed = dict(worker_id=payload['launch_spec']['worker_id'], control_uid=kw['policy'].control_uid,
        binding_id=binding.binding_id, profile_id=profile.profile_id, adapter_id=binding.adapter_id,
        realm_config_sha256=owner._config_sha256, realm_generation=1,
        catalog_digest=compose_catalog_digest(bindings_document=bindings, profiles_document=profiles))
    # Inert realm observation only. Separate observer tests exercise filesystem/principal checks.
    monkeypatch.setattr(SubscriptionRealmOwner, 'observe', lambda self: dict(observed))
    payload['launch_spec']['model'] = binding.model_for(profile, kw['model_class'])
    kw['correlation']['runtime_binding']['start_request_sha256'] = start_request_sha256(payload)
    expires = time.time() + 60
    projection = dict(schema_version=control.SCHEMA, attempt_id='run-1',
        fence_generation=1, pin_version=1, pin_identity_sha256=control.launch_identity(payload),
        lease_expires_at=datetime.fromtimestamp(expires, timezone.utc).isoformat())
    authority = control.authorize_control_command({**payload, 'control_start': projection},
        peer=PeerCredentials(uid=450, gid=450))  # fabricated unit peer, NOT a kernel receipt
    ns = runner(monkeypatch, tmp_path)
    args = dict(payload=payload, authority=authority, preparation=kw,
        lease=HeldOriginalLease(), state={'started': False}, key='run-1',
        receipt=tmp_path/'terminal.jsonl', nice=10, check_original_owner=lambda prepared: None)
    args.update(credential_loader=lambda: 'inert-owner-token',
        credential_realm_owner=owner, credential_physical_binding=physical, credential_bindings_document=bindings,
        credential_profiles_document=profiles)
    return ns, args, expires


def forbid(ns):
    def fail(**kw): pytest.fail('refused request reached spawn')
    ns['run_owned_process'] = fail


def test_public_control_fields_cannot_construct_inprocess_authority(tmp_path, monkeypatch):
    ns, args, _ = setup(tmp_path, monkeypatch); forbid(ns)
    args['authority'] = dataclasses.replace(args['authority'], _peer_verified=None)
    with pytest.raises(control.ControlStartRefused): ns['_run_reserved_attended_under_lease'](**args)
    assert not args['state']['started'] and args['lease'].holds == []


def test_ordinary_ssh_peer_cannot_authorize_even_digest_correct_request(tmp_path):
    payload, kw = fixture(tmp_path)
    with pytest.raises(control.ControlStartRefused, match='control_peer_required'):
        control.authorize_control_command(payload, peer=PeerCredentials(uid=1000, gid=1000))


def test_owner_wait_does_not_extend_control_expiry(tmp_path, monkeypatch):
    ns, args, expires = setup(tmp_path, monkeypatch); forbid(ns)
    def check(prepared): monkeypatch.setattr(control.time, 'time', lambda: expires + 1)
    args['check_original_owner'] = check
    with pytest.raises(control.ControlStartRefused): ns['_run_reserved_attended_under_lease'](**args)
    assert not args['state']['started'] and args['lease'].holds == []


@pytest.mark.parametrize('outcome', [False, True, PermissionError('owner gate refused')])
def test_callback_boolean_is_not_admission_and_actual_refusal_stops(tmp_path, monkeypatch, outcome):
    ns, args, _ = setup(tmp_path, monkeypatch); forbid(ns)
    def check(prepared):
        if isinstance(outcome, Exception): raise outcome
        return outcome
    args['check_original_owner'] = check
    with pytest.raises((control.ControlStartRefused, PermissionError)):
        ns['_run_reserved_attended_under_lease'](**args)
    assert not args['state']['started'] and args['lease'].holds == []


def test_original_validation_commands_are_preserved_immutable_and_allowlisted(tmp_path):
    payload, kw = fixture(tmp_path)
    payload['validation_commands'] = [['/usr/bin/true']]
    kw['correlation']['runtime_binding']['start_request_sha256'] = start_request_sha256(payload)
    with pytest.raises(ReservedLaunchRefused, match='reserved_validation_not_allowed'):
        prepare_reserved_attended_launch(payload, **kw)
    kw['allowed_validation_commands'] = (('/usr/bin/true',),)
    prepared = prepare_reserved_attended_launch(payload, **kw)
    payload['validation_commands'][0][0] = '/usr/bin/false'
    assert prepared.validation_commands == (('/usr/bin/true',),)


def test_post_spawn_exception_preserves_original_cleanup_hold(tmp_path, monkeypatch):
    ns, args, _ = setup(tmp_path, monkeypatch)
    def fail(**kw): raise OSError('inert failure after unknown spawn')
    ns['run_owned_process'] = fail
    with pytest.raises(OSError): ns['_run_reserved_attended_under_lease'](**args)
    assert args['state']['started'] and args['lease'].holds == ['worker_cleanup_unproven']


def test_proven_exec_failure_does_not_masquerade_as_started(tmp_path, monkeypatch):
    ns, args, _ = setup(tmp_path, monkeypatch)
    def fail(**kw): raise lr.OwnedProcessStartError(7)
    ns['run_owned_process'] = fail
    with pytest.raises(lr.OwnedProcessStartError): ns['_run_reserved_attended_under_lease'](**args)
    assert not args['state']['started'] and args['lease'].holds == []


def test_compiled_stdin_closed_environment_through_original_runner(tmp_path, monkeypatch):
    ns, args, _ = setup(tmp_path, monkeypatch)
    binary = tmp_path/'inert-harness'
    binary.write_text('#!' + sys.executable + '\nimport os,sys,json\n'
        'print(json.dumps({"stdin":sys.stdin.read(),"argv":sys.argv[1:],"env":{k:v for k,v in os.environ.items() if k != "ANTHROPIC_AUTH_TOKEN"}}))\n')
    binary.chmod(0o700)
    args['preparation']['binary'] = dataclasses.replace(args['preparation']['binary'],
        path=str(binary), real_path=str(binary), sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    # Bound only this local harmless child. No fleet process/UID census.
    monkeypatch.setattr(lr, '_session_pids', lambda pgid: ())
    def wait(proc, pgid, timeout):
        try: proc.wait(timeout=timeout); return 'completed'
        except subprocess.TimeoutExpired: return 'timeout'
    def cleanup(proc, pgid, **kw):
        assert proc.poll() is not None
        return dict(status='settled', identity_verified=True, census_proven=True, residual_count=0)
    monkeypatch.setattr(lr, '_wait_owned_process_with_fuse', wait)
    monkeypatch.setattr(lr, '_terminate_verified_group', cleanup)
    monkeypatch.setenv('INHERITED_SECRET_FIXTURE', 'must-not-travel')
    output, commands = ns['_run_reserved_attended_under_lease'](**args)
    assert output.returncode == 0 and output.cleanup_proven and commands == ()
    captured = json.loads(output.stdout)
    assert captured['stdin'] == args['payload']['launch_spec']['prompt']
    assert captured['stdin'] not in captured['argv']
    assert captured['env']['PATH'] == '/usr/bin:/bin:/usr/sbin:/sbin'
    assert 'INHERITED_SECRET_FIXTURE' not in captured['env']
    assert captured['env']['HOME'] == args['payload']['launch_spec']['run_dir'] + '/home'
    assert args['lease'].holds == []
    retained = json.loads(args['receipt'].read_text().splitlines()[-1])
    assert retained['stdout_sha256'] == hashlib.sha256(output.stdout.encode()).hexdigest()
    assert retained['label'] == 'run-1'
