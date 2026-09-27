"""Attended coordinator composition; real local shims, no credentials or models."""
from __future__ import annotations
import inspect
import json
from pathlib import Path
import tomllib

import pytest
from ops.codex_fabric import attended_parent as launch
from ops.codex_fabric import orchestrator_bundle as bundle

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def case(monkeypatch):
    from tests.test_codex_fabric_attended_parent import AttendedParentTests
    obj = AttendedParentTests('test_preflight_only_reads_census_and_builds_five_tool_invocation')
    obj.setUp()
    try:
        for name in bundle.BUNDLE_PATHS:
            target = obj.module_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / 'ops/codex_fabric' / name).read_bytes())
        obj.home = obj.root / 'codex home'
        obj.home.mkdir()
        monkeypatch.setenv('CODEX_HOME', str(obj.home))
        obj.digest = bundle.inspect_bundle(obj.home, source_root=obj.module_dir)['bundle_digest']
        bundle.install_bundle(obj.home, expected_bundle_digest=obj.digest, source_root=obj.module_dir)
        yield obj
    finally:
        obj.doCleanups()

def prepared(case, **kwargs):
    assert 'expected_bundle_digest' in inspect.signature(launch.prepare_launch).parameters, 'bundle/launcher composition is absent'
    return case.prepare(expected_bundle_digest=case.digest, **kwargs)

def settings(plan):
    return {arg.split('=', 1)[0]: tomllib.loads('value=' + arg.split('=', 1)[1])['value']
            for i, arg in enumerate(plan.argv) if i and plan.argv[i-1] == '-c'}

def test_bundle_composes_into_existing_five_tool_launcher_without_writes(case):
    before = {str(p): p.read_bytes() for p in case.home.rglob('*') if p.is_file()}
    plan = prepared(case)
    values = settings(plan)
    assert values['model'] == 'gpt-6-astra'
    assert values['agents.enabled'] is True
    assert values['agents.max_concurrent_threads_per_session'] == 1
    assert values['sandbox_mode'] == 'read-only'
    assert values['approval_policy'] == 'never'
    for role in ('sol', 'astra'):
        assert values[f'agents.l2_{role}_ceo.config_file'] == str(case.home / f'agents/l2-{role}-ceo.toml')
    assert values['mcp_servers.mastermind-executive.enabled_tools'] == list(launch.EXECUTIVE_TOOLS)
    assert values['mcp_servers.mastermind-executive.required'] is True
    assert case.calls_read() == [case.census_args, case.detail_args]
    assert {str(p): p.read_bytes() for p in case.home.rglob('*') if p.is_file()} == before
    receipt = plan.to_dict()
    assert receipt['orchestrator_bundle_digest'] == case.digest
    assert receipt['codex_home'] == str(case.home)
    assert receipt['role_selection_proven'] is False
    assert receipt['child_enforcement_proven'] is False
    assert receipt['worker_dispatch_authorized'] is False

@pytest.mark.parametrize('digest', ['', 'bad', '0' * 64, True])
def test_invalid_or_changed_bundle_digest_refuses_before_census(case, digest):
    with pytest.raises(launch.BootstrapError):
        assert 'expected_bundle_digest' in inspect.signature(launch.prepare_launch).parameters, 'bundle/launcher composition is absent'
        case.prepare(expected_bundle_digest=digest)
    assert case.calls_read() == []

@pytest.mark.parametrize('name', bundle.BUNDLE_PATHS)
def test_missing_installed_file_refuses_before_census(case, name):
    (case.home / name).unlink()
    with pytest.raises(launch.BootstrapError): prepared(case)
    assert case.calls_read() == []

@pytest.mark.parametrize('name', bundle.BUNDLE_PATHS)
def test_tampered_installed_file_refuses_without_echo(case, name):
    (case.home / name).write_text('private-test-sentinel')
    with pytest.raises(launch.BootstrapError) as exc: prepared(case)
    assert 'private-test-sentinel' not in str(exc.value)
    assert case.calls_read() == []

def test_unsupported_auth_stays_held_for_optional_bundle(case):
    case.census.write_text(json.dumps([dict(case.row, auth_status='unsupported')]))
    plan = prepared(case)
    assert plan.launch_allowed is False
    assert plan.to_dict()['status'] == 'PREPARED_AUTH_STATUS_UNRESOLVED'
    result = case.cli('--orchestrator-bundle-digest', case.digest, '--launch')
    assert result.returncode == 2
    assert 'authentication status is unresolved' in result.stderr
    assert all(call in (case.census_args, case.detail_args) for call in case.calls_read())

def test_cli_coordinator_preflight_does_not_launch(case):
    result = case.cli('--orchestrator-bundle-digest', case.digest)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['orchestrator_bundle_digest'] == case.digest
    assert case.calls_read() == [case.census_args, case.detail_args]

def test_explicit_coordinator_launch_uses_the_composed_argv_once(case):
    result = case.cli('--orchestrator-bundle-digest', case.digest, '--launch')
    assert result.returncode == 0, result.stderr
    executed = json.loads(result.stdout)['executed']
    assert 'agents.enabled=true' in executed
    assert 'sandbox_mode="read-only"' in executed
    assert len(case.calls_read()) == 3
    assert case.calls_read()[-1] == executed

@pytest.mark.parametrize('change', ['home', 'role', 'helper', 'profile'])
def test_changed_input_after_preparation_refuses_before_exec(case, monkeypatch, capsys, change):
    plan = prepared(case)
    if change == 'home':
        other = case.root / 'other home'; other.mkdir()
        monkeypatch.setenv('CODEX_HOME', str(other))
    elif change == 'role':
        (case.home / 'agents/l2-astra-ceo.toml').write_text('# changed after preparation')
    elif change == 'helper':
        (case.module_dir / 'executive_mcp_auth.py').write_text('# changed helper')
    else:
        (case.module_dir / 'mastermind-orchestrators.config.toml').write_text('# changed source')
    monkeypatch.setattr(launch, 'prepare_launch', lambda *a, **kw: plan)
    def forbidden_exec(*args): pytest.fail('changed input reached exec')
    monkeypatch.setattr(launch.os, 'execv', forbidden_exec)
    assert launch.main(['--url', case.row['transport']['url'], '--project-dir', str(case.project), '--launch']) == 2
    assert 'changed' in capsys.readouterr().err.lower()

def test_default_projection_remains_disabled_with_joined_named_sol_profile(case):
    plan = case.prepare()
    values = settings(plan)
    assert values['agents.enabled'] is False
    assert not any(key.startswith('agents.l2_') for key in values)

@pytest.mark.parametrize('replacement', ['enabled = 1', 'enabled = "true"'])
def test_joined_profile_never_accepts_non_boolean_enable(case, replacement):
    case.profile.write_text(case.profile.read_text().replace('enabled = true', replacement))
    with pytest.raises(launch.BootstrapError): case.prepare()
    assert case.calls_read() == []


def test_same_path_rebound_home_refuses_even_with_identical_role_bytes(case, monkeypatch):
    import shutil
    plan = prepared(case)
    old = case.root / 'former codex home'
    case.home.rename(old)
    shutil.copytree(old, case.home)
    monkeypatch.setattr(launch, 'prepare_launch', lambda *a, **kw: plan)
    def forbidden_exec(*args): pytest.fail('rebound credential home reached exec')
    monkeypatch.setattr(launch.os, 'execv', forbidden_exec)
    assert launch.main(['--url', case.row['transport']['url'], '--project-dir', str(case.project), '--launch']) == 2


def test_legacy_disabled_profile_remains_compatible(case):
    case.profile.write_text('model = "gpt-6-astra"\nmodel_reasoning_effort = "high"\n'
        '[agents]\nenabled = false\nmax_concurrent_threads_per_session = 1\n'
        'default_subagent_model = "gpt-5.6-sol"\ndefault_subagent_reasoning_effort = "high"\n')
    assert settings(case.prepare())['agents.enabled'] is False
    case.profile.write_text(case.profile.read_text().replace('enabled = false', 'enabled = true'))
    with pytest.raises(launch.BootstrapError): case.prepare()


def test_unknown_named_role_cannot_enter_legacy_projection(case):
    case.profile.write_text(case.profile.read_text().replace('agents.l2_sol_ceo', 'agents.unreviewed'))
    with pytest.raises(launch.BootstrapError): case.prepare()
    assert case.calls_read() == []


def test_source_changed_during_metadata_reads_never_returns_a_usable_plan(case, monkeypatch):
    original = launch._run
    def changed_after_read(*args, **kwargs):
        result = original(*args, **kwargs)
        (case.module_dir / 'executive_mcp_auth.py').write_text('# source moved during census')
        return result
    monkeypatch.setattr(launch, '_run', changed_after_read)
    with pytest.raises(launch.BootstrapError, match='changed'): prepared(case)
    assert case.calls_read() == [case.census_args, case.detail_args]


def test_native_unknown_auth_is_inspectable_but_never_launchable(case):
    case.census.write_text(json.dumps([dict(case.row, auth_status='unknown')]))
    plan = prepared(case)
    assert plan.native_auth_status == 'unknown'
    assert plan.launch_allowed is False
    assert plan.to_dict()['status'] == 'PREPARED_AUTH_STATUS_UNRESOLVED'
    result = case.cli('--orchestrator-bundle-digest', case.digest, '--launch')
    assert result.returncode == 2
    assert 'authentication status is unresolved' in result.stderr
    assert all(call in (case.census_args, case.detail_args) for call in case.calls_read())
