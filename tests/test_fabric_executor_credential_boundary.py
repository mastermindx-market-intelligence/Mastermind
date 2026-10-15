"""Only inert typed realm observations and sentinel credentials; no live secret."""
import ast
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_fabric_original_owner_runner import setup, _inject_owner_test_keys
from test_fabric_owned_process_phases import lr


def test_original_process_boundary_has_actual_credential_input(tmp_path, monkeypatch):
    ns, args, _ = setup(tmp_path, monkeypatch)
    prepared, arguments, boundary = ns['_prepare_reserved_attended_under_lease'](**args)
    boundary()
    assert 'ANTHROPIC_AUTH_TOKEN' in arguments['env']
    assert 'ANTHROPIC_AUTH_TOKEN' not in prepared.descriptor.environment

from control_plane import fabric_control_start as control
from control_plane.codex_provider_realm import SubscriptionRealmOwner
import traceback


def credential_fixture(tmp_path, monkeypatch):
    """Export canonical prepared inputs and explicitly inert realm observations."""
    ns, args, expires = setup(tmp_path, monkeypatch)
    calls = []
    args['credential_loader'] = lambda: (calls.append('load'), 'inert-owner-token')[1]
    return ns, args, expires, calls


@pytest.mark.parametrize('damage', ['loader', 'unsealed', 'worker', 'catalog', 'binding'])
def test_missing_or_foreign_credential_composition_never_loads(tmp_path, monkeypatch, damage):
    ns, args, _, calls = credential_fixture(tmp_path, monkeypatch)
    if damage == 'loader': args['credential_loader'] = None
    if damage == 'unsealed': args['credential_realm_owner'] = object()
    if damage == 'worker':
        observed = args['credential_realm_owner'].observe()
        observed['worker_id'] = 'other-worker'
        monkeypatch.setattr(SubscriptionRealmOwner, 'observe', lambda self: dict(observed))
    if damage == 'catalog':
        args['credential_bindings_document']['bindings'][args['preparation']['binding'].binding_id]['implementation_state'] = 'SPEC_ONLY'
    if damage == 'binding':
        args['preparation']['binding'] = dataclasses.replace(args['preparation']['binding'],
                                                           effective_base_url='https://other.invalid')
    ns['run_owned_process'] = lambda **kw: pytest.fail('credential refusal spawned')
    with pytest.raises((control.ControlStartRefused, ValueError)):
        ns['_run_reserved_attended_under_lease'](**args)
    assert calls == [] and not args['state']['started']
    assert not args['receipt'].exists()


def test_control_and_owner_refusal_precede_credential_load(tmp_path, monkeypatch):
    ns, args, _, calls = credential_fixture(tmp_path, monkeypatch)
    args['authority'] = dataclasses.replace(args['authority'], _peer_verified=None)
    with pytest.raises(control.ControlStartRefused):
        ns['_prepare_reserved_attended_under_lease'](**args)
    assert calls == []


@pytest.mark.parametrize('value', [None, '', 'sentinel\ninvalid', 'sentinel\x00invalid', 'x' * 4097])
def test_invalid_credential_value_is_closed_before_spawn(tmp_path, monkeypatch, value):
    ns, args, _, _ = credential_fixture(tmp_path, monkeypatch)
    args['credential_loader'] = lambda: value
    prepared, arguments, boundary = ns['_prepare_reserved_attended_under_lease'](**args)
    with pytest.raises(control.ControlStartRefused, match='realm_credential_unavailable'):
        boundary()
    assert 'ANTHROPIC_AUTH_TOKEN' not in arguments['env']
    assert 'ANTHROPIC_AUTH_TOKEN' not in prepared.descriptor.environment
    assert not args['receipt'].exists()


def test_loader_exception_has_no_secret_diagnostic_or_context(tmp_path, monkeypatch):
    ns, args, _, _ = credential_fixture(tmp_path, monkeypatch)
    sentinel = 'inert-failed-loader-sensitive-value'
    def loader(): raise RuntimeError(sentinel)
    args['credential_loader'] = loader
    prepared, arguments, boundary = ns['_prepare_reserved_attended_under_lease'](**args)
    with pytest.raises(control.ControlStartRefused) as raised: boundary()
    assert raised.value.__context__ is None and raised.value.__cause__ is None
    assert sentinel not in ''.join(traceback.format_exception(raised.value))
    assert sentinel not in json.dumps(arguments) and sentinel not in repr(prepared.descriptor)
    assert not args['receipt'].exists()


@pytest.mark.parametrize('drift', ['expiry', 'catalog'])
def test_expiry_or_catalog_drift_during_load_refuses_and_scrubs(tmp_path, monkeypatch, drift):
    ns, args, expires, calls = credential_fixture(tmp_path, monkeypatch)
    def loader():
        calls.append('load')
        if drift == 'expiry':
            monkeypatch.setattr(control.time, 'time', lambda: expires + 1)
        else:
            args['credential_bindings_document']['bindings'][args['preparation']['binding'].binding_id]['implementation_state'] = 'SPEC_ONLY'
        return 'inert-owner-token'
    args['credential_loader'] = loader
    _, arguments, boundary = ns['_prepare_reserved_attended_under_lease'](**args)
    with pytest.raises(control.ControlStartRefused): boundary()
    assert calls == ['load'] and 'ANTHROPIC_AUTH_TOKEN' not in arguments['env']
    with pytest.raises(control.ControlStartRefused, match='already_consumed'): boundary()
    assert calls == ['load'] and not args['receipt'].exists()


def test_live_catalog_drift_before_boundary_stops_load(tmp_path, monkeypatch):
    ns, args, _, calls = credential_fixture(tmp_path, monkeypatch)
    _, arguments, boundary = ns['_prepare_reserved_attended_under_lease'](**args)
    args['credential_bindings_document']['bindings'][args['preparation']['binding'].binding_id]['implementation_state'] = 'SPEC_ONLY'
    with pytest.raises(control.ControlStartRefused): boundary()
    assert calls == [] and 'ANTHROPIC_AUTH_TOKEN' not in arguments['env']


def test_once_boundary_uses_actual_keys_without_secret_projection(lr, tmp_path, monkeypatch):
    ns, args, _, calls = credential_fixture(tmp_path, monkeypatch)
    prepared, arguments, boundary = ns['_prepare_reserved_attended_under_lease'](**args)
    boundary()
    env = arguments['env']
    assert calls == ['load']
    assert set(env) == set(prepared.descriptor.environment) | {'ANTHROPIC_AUTH_TOKEN'}
    assert lr._nonsecret_environment_sha256(env) == lr._nonsecret_environment_sha256(prepared.descriptor.environment)
    with pytest.raises(control.ControlStartRefused, match='already_consumed'): boundary()
    assert calls == ['load']
    env.pop('ANTHROPIC_AUTH_TOKEN')


@pytest.mark.parametrize('failure', [False, True])
def test_original_begin_scrubs_parent_mapping_on_return_or_failure(tmp_path, monkeypatch, failure):
    ns, args, _, calls = credential_fixture(tmp_path, monkeypatch)
    from test_fabric_bound_controller_wire import patched
    tree = ast.parse(patched(tmp_path, 'remote_sub_exec.py', 'EXECUTOR_SOURCE.json'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_begin_reserved_attended_under_lease')
    captured = {}
    def begin(**kw):
        kw['at_boundary']()
        captured['environment'] = kw['arguments']['env']
        assert captured['environment']['ANTHROPIC_AUTH_TOKEN'] == 'inert-owner-token'
        if failure: raise RuntimeError('inert-begin-refusal')
        return SimpleNamespace()
    import os
    ns.update(os=os, LaneRuntimeError=RuntimeError, _launch_receipt_directory=lambda path: None,
              _begin_lease_process=begin)
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<original-executor-begin>', 'exec'), ns)
    if failure:
        with pytest.raises(RuntimeError, match='inert-begin-refusal'):
            ns[node.name](**args)
    else:
        owner, commands = ns[node.name](**args)
        assert 'inert-owner-token' not in repr(owner) and commands == ()
    assert calls == ['load'] and 'ANTHROPIC_AUTH_TOKEN' not in captured['environment']
    assert not args['receipt'].exists()


def test_verifier_failure_has_no_sensitive_diagnostic_or_context(tmp_path, monkeypatch):
    ns, args, _, calls = credential_fixture(tmp_path, monkeypatch)
    from control_plane import codex_provider_realm as canonical
    sentinel = 'inert-verifier-sensitive-detail'
    def refuse(*a, **kw): raise RuntimeError(sentinel)
    monkeypatch.setattr(canonical.SubscriptionRealmOwner, 'observe', refuse)
    with pytest.raises(control.ControlStartRefused) as raised:
        ns['_prepare_reserved_attended_under_lease'](**args)
    assert raised.value.__context__ is None and raised.value.__cause__ is None
    assert sentinel not in ''.join(traceback.format_exception(raised.value))
    assert calls == [] and not args['receipt'].exists()


@pytest.mark.parametrize('field,value', [
    ('control_uid', True), ('control_uid', 999), ('realm_generation', False),
    ('realm_generation', 0), ('realm_config_sha256', 'b' * 64),
    ('catalog_digest', 'c' * 64), ('adapter_id', 'codex-cli'),
])
def test_current_realm_identity_join_refuses_before_credential(tmp_path, monkeypatch, field, value):
    ns, args, _, calls = credential_fixture(tmp_path, monkeypatch)
    observed = args['credential_realm_owner'].observe()
    observed[field] = value
    monkeypatch.setattr(SubscriptionRealmOwner, 'observe', lambda self: dict(observed))
    with pytest.raises(control.ControlStartRefused, match='realm_observation_unqualified'):
        ns['_prepare_reserved_attended_under_lease'](**args)
    assert calls == [] and not args['receipt'].exists()


@pytest.mark.parametrize('when', ['before_load', 'during_load'])
def test_changed_current_realm_generation_cannot_extend_original_admission(tmp_path, monkeypatch, when):
    ns, args, _, calls = credential_fixture(tmp_path, monkeypatch)
    observed = args['credential_realm_owner'].observe()
    monkeypatch.setattr(SubscriptionRealmOwner, 'observe', lambda self: dict(observed))
    def loader():
        calls.append('load')
        observed['realm_generation'] += 1
        return 'inert-owner-token'
    if when == 'during_load':
        args['credential_loader'] = loader
    _, arguments, boundary = ns['_prepare_reserved_attended_under_lease'](**args)
    if when == 'before_load':
        observed['realm_generation'] += 1
    with pytest.raises(control.ControlStartRefused, match='realm_observation_changed'):
        boundary()
    assert calls == ([] if when == 'before_load' else ['load'])
    assert 'ANTHROPIC_AUTH_TOKEN' not in arguments['env']
    assert not args['receipt'].exists()


def test_ordinary_credential_path_never_consumes_interactive_or_legacy_canary_as_authority(tmp_path, monkeypatch):
    ns, args, _, calls = credential_fixture(tmp_path, monkeypatch)
    from control_plane import subscription_canary_admission
    def forbidden(*args, **kwargs):
        pytest.fail('ordinary credential observation consumed a canary as task authority')
    monkeypatch.setattr(subscription_canary_admission, 'verify_subscription_canary_admission', forbidden)
    monkeypatch.setattr(subscription_canary_admission, 'verify_broker_subscription_canary_admission', forbidden)
    _, arguments, boundary = ns['_prepare_reserved_attended_under_lease'](**args)
    boundary()
    assert calls == ['load']
    arguments['env'].pop('ANTHROPIC_AUTH_TOKEN')


@pytest.mark.parametrize('damage', ['config', 'bridge', 'worker_uid', 'worker_gid', 'home'])
def test_independent_physical_realm_pin_refuses_before_secret_or_process(tmp_path, monkeypatch, damage):
    ns, args, _, calls = credential_fixture(tmp_path, monkeypatch)
    physical=args['credential_physical_binding']
    changes={'config':{'worker_source_config_digest':'b'*64},
             'bridge':{'bridge_uid':physical.bridge_uid+10000},
             'worker_uid':{'worker_uid':physical.worker_uid+10000},
             'worker_gid':{'worker_gid':physical.worker_gid+10000},
             'home':{'provider_home':str(tmp_path/'other-private-home')}}[damage]
    args['credential_physical_binding']=dataclasses.replace(physical, **changes)
    ns['run_owned_process']=lambda **kw:pytest.fail('foreign physical realm reached process')
    with pytest.raises(control.ControlStartRefused,match='realm_observation_unqualified'):
        ns['_run_reserved_attended_under_lease'](**args)
    assert calls==[] and not args['state']['started'] and not args['receipt'].exists()


def test_current_owner_self_pin_cannot_replace_original_physical_config(tmp_path, monkeypatch):
    ns,args,_,calls=credential_fixture(tmp_path,monkeypatch)
    observed=args['credential_realm_owner'].observe()
    observed['realm_config_sha256']='c'*64
    owner=dataclasses.replace(args['credential_realm_owner'],_config_sha256='c'*64)
    args['credential_realm_owner']=owner
    monkeypatch.setattr(SubscriptionRealmOwner,'observe',lambda self:dict(observed))
    assert owner.observe()['realm_config_sha256']==owner._config_sha256
    with pytest.raises(control.ControlStartRefused,match='realm_observation_unqualified'):
        ns['_prepare_reserved_attended_under_lease'](**args)
    assert calls==[] and not args['receipt'].exists()


@pytest.mark.parametrize('getter',['getuid','geteuid','getgid','getegid'])
def test_original_controller_cannot_claim_a_different_launch_principal(tmp_path,monkeypatch,getter):
    ns,args,_,calls=credential_fixture(tmp_path,monkeypatch)
    real=ns['os']
    view=SimpleNamespace(**{name:getattr(real,name) for name in ('getuid','geteuid','getgid','getegid')})
    setattr(view,getter,lambda:999999)
    ns['os']=view
    with pytest.raises(control.ControlStartRefused,match='realm_observation_unqualified'):
        ns['_prepare_reserved_attended_under_lease'](**args)
    assert calls==[] and not args['receipt'].exists()


@pytest.mark.parametrize('damage', ['inode', 'mode', 'dirty_git'])
def test_assignment_drift_during_credential_load_never_spawns(tmp_path, monkeypatch, damage):
    ns, args, _, calls = credential_fixture(tmp_path, monkeypatch)
    root = tmp_path / 'original-assignment'; root.mkdir(mode=0o700)
    original = root.stat()
    dirty = [False]
    def check(_prepared):
        current = root.stat()
        if (current.st_ino != original.st_ino or current.st_mode != original.st_mode or dirty[0]):
            raise control.ControlStartRefused('original_assignment_resource_changed')
    args['check_original_owner'] = check
    def loader():
        calls.append('load')
        if damage == 'inode':
            root.rename(tmp_path/'retained-original'); root.mkdir(mode=0o700)
        elif damage == 'mode': root.chmod(0o750)
        else: dirty[0] = True
        return 'inert-owner-token'
    args['credential_loader'] = loader
    ns['run_owned_process'] = lambda **kw: pytest.fail('changed assignment spawned')
    prepared, arguments, boundary = ns['_prepare_reserved_attended_under_lease'](**args)
    with pytest.raises(control.ControlStartRefused, match='original_assignment_resource_changed'):
        boundary()
    assert calls == ['load'] and 'ANTHROPIC_AUTH_TOKEN' not in arguments['env']
    assert not args['receipt'].exists() and not args['state']['started']
