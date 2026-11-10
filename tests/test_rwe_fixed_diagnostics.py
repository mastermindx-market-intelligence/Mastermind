"""Canonical RWE execution retains the incumbent closed public diagnostics only."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

from scripts import ci_parallel_shard, ci_pytest, rwe_env
from scripts.ci_fixed_diagnostics import MAX_SNAPSHOT

ROOT = Path(__file__).resolve().parents[1]
PREPARE = 'Prepare fixed test diagnostics'
UPLOAD = 'Upload fixed test diagnostics'
PATHS = [
    '${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/ci-fixed-diagnostics.json',
    '${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/native-admission-unit/ci-fixed-diagnostics.json',
    '${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/native-admission-rollout/ci-fixed-diagnostics.json',
]


def workflow():
    return yaml.load((ROOT/'.github/workflows/rwe-shadow.yml').read_text(),
                     Loader=ci_pytest._WorkflowYAMLLoader)


def check_join(document):
    job = document['jobs']['shadow-shards']
    steps = job['steps']
    prepare = next(s for s in steps if s.get('name') == PREPARE)
    run = next(s for s in steps if s.get('name') == 'Run canonical test shard inside the realized environment')
    upload = next(s for s in steps if s.get('name') == UPLOAD)
    ordinary = yaml.load((ROOT/'.github/workflows/ci.yml').read_text(),
                         Loader=ci_pytest._WorkflowYAMLLoader)['jobs']['pytest_shards']['steps']
    assert prepare == next(s for s in ordinary if s.get('name') == PREPARE)
    assert steps.index(prepare) < steps.index(run) < steps.index(upload)
    assert run == {'name': 'Run canonical test shard inside the realized environment',
                   'run': 'python scripts/rwe_env.py gate --env /tmp/rwe-env --shard-index ${{ matrix.index }}'}
    assert upload == {'name': UPLOAD, 'if': 'always()', 'timeout-minutes': 2,
        'uses': 'actions/upload-artifact@v4', 'with': {
            'name': 'rwe-fixed-diagnostics-${{ matrix.index }}', 'path': '\n'.join(PATHS)+'\n',
            'if-no-files-found': 'warn', 'retention-days': 3, 'compression-level': 0}}
    assert not any('continue-on-error' in s for s in steps)
    assert job['timeout-minutes'] == 45
    assert document['permissions'] == {'contents': 'read'}
    assert 'scripts/ci_fixed_diagnostics.py' in document['on']['pull_request']['paths']


def test_shadow_joins_exact_existing_private_prepare_and_closed_three_artifacts():
    check_join(workflow())


@pytest.mark.parametrize('mutation', ['path', 'always', 'selector', 'environment', 'prepare', 'outcome'])
def test_join_contract_rejects_path_selector_environment_and_outcome_widening(mutation):
    document = copy.deepcopy(workflow()); steps = document['jobs']['shadow-shards']['steps']
    run = next(s for s in steps if s.get('name') == 'Run canonical test shard inside the realized environment')
    upload = next(s for s in steps if s.get('name') == UPLOAD)
    prepare = next(s for s in steps if s.get('name') == PREPARE)
    if mutation == 'path': upload['with']['path'] += '${{ runner.temp }}/**\n'
    if mutation == 'always': upload['if'] = 'success()'
    if mutation == 'selector': run['run'] += ' --subset tests/test_public.py'
    if mutation == 'environment': run['env'] = {'PYTEST_ADDOPTS': '-p caller_plugin'}
    if mutation == 'prepare': prepare['run'] += '\nchmod 0777 "$diagnostic_dir"\n'
    if mutation == 'outcome': run['continue-on-error'] = True
    with pytest.raises(AssertionError): check_join(document)


@pytest.mark.parametrize('fails', [False, True])
def test_real_canonical_rwe_child_retains_public_case_and_original_result(tmp_path, monkeypatch, fails):
    """Inert disposable owner; no realized vendor/install/provider claim."""
    root = tmp_path/'project'
    for directory in ('scripts', 'tests', 'ci', '.github/workflows'):
        (root/directory).mkdir(parents=True)
    for name in ('ci_parallel_shard.py', 'ci_pytest.py', 'ci_pytest_timing.py', 'ci_fixed_diagnostics.py'):
        shutil.copyfile(ROOT/'scripts'/name, root/'scripts'/name)
    (root/'scripts/__init__.py').touch()
    (root/'pyproject.toml').write_text('[tool.pytest.ini_options]\n')
    (root/'ci/pytest_exclusions.toml').write_text('version = 1\nexclude = []\n')
    shutil.copyfile(ROOT/'.github/workflows/ci.yml', root/'.github/workflows/ci.yml')
    candidates = tuple(f'tests/test_rwe_public_{i}.py' for i in range(60))
    paths = tuple(group[0] for group in ci_pytest.partition_modules(candidates, jobs=6))
    for index, path in enumerate(paths):
        source = 'def test_public(): pass\n'
        if index == 5:
            source = ('import pytest\n'
                      '@pytest.mark.parametrize("value", ["PRIVATE_RWE_VALUE"], ids=["PRIVATE_RWE_ID"])\n'
                      'def test_public(value):\n'
                      '    private_local = value\n'
                      + ('    raise ValueError(private_local)\n' if fails else '    assert private_local\n'))
        (root/path).write_text(source)
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Inert Fixture',
                    '-c', 'user.email=inert@example.invalid', 'commit', '-qm', 'public fixture'], check=True)
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    diagnostic = tmp_path/'diagnostics'; diagnostic.mkdir(mode=0o700)
    environment = tmp_path/'environment'; environment.mkdir()
    # Only the interpreter/vendor premises are fixture substitutions. The
    # actual cmd_gate -> canonical plan -> pytest/plugin/catalog/writer run.
    monkeypatch.setattr(rwe_env, '_venv_python', lambda _: Path(sys.executable))
    monkeypatch.setattr(rwe_env, 'require_supported_interpreter', lambda _: None)
    monkeypatch.setattr(rwe_env, 'vendor_present', lambda _: True)
    for name in ('PYTHONPATH', 'PYTEST_ADDOPTS', 'PYTEST_PLUGINS'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')
    monkeypatch.setenv('MMX_CI_FIXED_DIAGNOSTICS_DIR', str(diagnostic))
    args = argparse.Namespace(root=str(root), env=str(environment), subset=None, shard_index=5)
    code = rwe_env.cmd_gate(args)
    assert code == int(fails)
    raw = (diagnostic/'ci-fixed-diagnostics.json').read_bytes()
    value = json.loads(raw)
    assert len(raw) <= MAX_SNAPSHOT
    assert value['schema'] == 'ci.fixed-diagnostics.v2' and value['head'] == head
    assert b'PRIVATE' not in raw and str(tmp_path).encode() not in raw
    assert set(value) == {'schema', 'head', 'progress', 'failures', 'truncated', 'lifecycle'}
    assert {row['module'] for row in value['progress']} == {paths[5]}
    if fails:
        assert value['failures'] == [dict(module=paths[5], case='test_public',
            phase='call', kind='ValueError', function='test_public', line=5)]
    else:
        assert value['failures'] == []
    proof = json.loads((environment/rwe_env.RECEIPT_FILENAME).read_text())['proof']
    assert 'gate' not in proof
    assert proof['shard']['exit'] == code and proof['shard']['plan_observation'] == 'matched'
    assert proof['shard']['selected_modules'] == 1
    assert proof['shard']['included_sha256'] == ci_parallel_shard.shard_plan(root, jobs=6, index=5)[2]
    assert all(row['exitstatus'] == code for row in value['lifecycle'])
