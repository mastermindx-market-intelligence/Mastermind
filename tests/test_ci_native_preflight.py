"""Actual framework failures through the incumbent fixed artifact, never logs."""
import ast
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml
from scripts import ci_native_preflight as preflight

ROOT = Path(__file__).resolve().parents[1]
UNIT = 'ops/native_fabric/quota_continuity/tests/test_application_turn_leaf.py'
ROLLOUT = 'ops/native_fabric/quota_continuity/tests/test_go_native_stage.py'
ORDINARY = 'tests/test_native_launcher_successor_transition.py'


def fixture(tmp_path, module=UNIT, source=None):
    root = tmp_path / 'repo'; root.mkdir()
    for name in ('scripts/ci_native_preflight.py', 'scripts/ci_fixed_diagnostics.py',
                 'scripts/native_unittest_diagnostics.py'):
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
    path = root / module; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source or '''import unittest
class Leaf(unittest.TestCase):
 def test_failure(self):
  self.fail("PRIVATE https://user:password@private/?token=PRIVATE")
 def test_error(self):
  raise ValueError("PRIVATE exception and environment")
''')
    for args in (('init', '-q'), ('add', '.'), ('-c', 'user.name=Fixture', '-c',
                 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')):
        subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
    output = tmp_path / 'diagnostics'; output.mkdir(mode=0o700)
    env = dict(os.environ, MMX_CI_FIXED_DIAGNOSTICS_DIR=str(output),
               PYTHONPATH=str(root), PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    return root, output, env


def child_unit(root, env, module=UNIT):
    code = ('import unittest\nfrom scripts.ci_native_preflight import unittest_runner\n'
            f'suite=unittest.defaultTestLoader.discover("{str(Path(module).parent)}", pattern="{Path(module).name}")\n'
            'result=unittest_runner(verbosity=0).run(suite)\nraise SystemExit(not result.wasSuccessful())\n')
    return subprocess.run([sys.executable, '-c', code], cwd=root, env=env,
                          capture_output=True, timeout=30)


def snapshot(output, profile):
    raw = (output / profile / 'ci-fixed-diagnostics.json').read_bytes()
    assert b'PRIVATE' not in raw and b'password' not in raw
    value = json.loads(raw)
    assert value['schema'] == 'ci.fixed-diagnostics.v1'
    return value


def test_real_unittest_failure_classes_and_exit_without_private_messages(tmp_path):
    root, output, env = fixture(tmp_path)
    result = child_unit(root, env)
    assert result.returncode == 1 and b'PRIVATE' in result.stderr
    value = snapshot(output, 'native-admission-unit')
    assert value['head'] == subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    assert {(r['case'], r['kind'], r['phase']) for r in value['failures']} == {
        ('Leaf.test_failure', 'AssertionError', 'call'), ('Leaf.test_error', 'ValueError', 'call')}
    assert {r['module'] for r in value['failures']} == {UNIT}
    assert all(r['line'] > 0 for r in value['failures'])
    assert not (output / 'ci-fixed-diagnostics.json').exists()


def test_unittest_subtest_does_not_publish_parameters(tmp_path):
    root, output, env = fixture(tmp_path, source='''import unittest
class Leaf(unittest.TestCase):
 def test_parent(self):
  with self.subTest(secret="PRIVATE"):
   self.fail("PRIVATE")
''')
    assert child_unit(root, env).returncode == 1
    assert snapshot(output, 'native-admission-unit')['failures'][0]['case'] == 'Leaf.test_parent'


@pytest.mark.parametrize('module', [ROLLOUT, ORDINARY])
def test_actual_pytest_failure_and_expected_failure_keep_original_outcome(tmp_path, module):
    root, output, env = fixture(tmp_path, module, source='''import pytest
@pytest.mark.parametrize("secret", [pytest.param("PRIVATE", id="PRIVATE")])
def test_failure(secret):
 assert False, "PRIVATE https://private/?key=PRIVATE"
@pytest.mark.xfail(reason="PRIVATE")
def test_expected():
 raise ValueError("PRIVATE")
def test_skip():
 pytest.skip("PRIVATE")
''')
    result = subprocess.run([sys.executable, '-m', 'pytest', '--noconftest', '-q',
        '-p', 'scripts.ci_native_preflight', module], cwd=root, env=env, capture_output=True, timeout=30)
    assert result.returncode == 1 and b'PRIVATE' in result.stdout
    rows = snapshot(output, 'native-admission-rollout')['failures']
    assert len(rows) == 1 and rows[0]['case'] == rows[0]['function'] == 'test_failure'
    assert rows[0]['module'] == module and rows[0]['phase'] == 'call' and rows[0]['kind'] == 'AssertionError'


@pytest.mark.parametrize('defect', ['untracked', 'changed', 'outside-selection'])
def test_unqualified_source_never_becomes_public_failure_fact(tmp_path, defect):
    module = UNIT if defect != 'outside-selection' else 'ops/native_fabric/quota_continuity/tests/test_private_unselected.py'
    root, output, env = fixture(tmp_path, module)
    if defect == 'untracked':
        subprocess.run(['git', '-C', str(root), 'rm', '--cached', module], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(root), '-c', 'user.name=Fixture', '-c',
                        'user.email=fixture@example.invalid', 'commit', '-qm', 'remove'], check=True)
    elif defect == 'changed':
        with (root / module).open('a') as stream: stream.write('\n# PRIVATE changed postimage\n')
    assert child_unit(root, env, module).returncode == 1
    value = snapshot(output, 'native-admission-unit')
    assert value['failures'] == [] and value['truncated'] is True


@pytest.mark.parametrize('defect', ['absent', 'public-mode', 'symlink', 'already-owned'])
def test_capture_unavailable_preserves_test_exit_and_existing_evidence(tmp_path, defect):
    root, output, env = fixture(tmp_path)
    if defect == 'absent': env.pop('MMX_CI_FIXED_DIAGNOSTICS_DIR')
    elif defect == 'public-mode': output.chmod(0o755)
    elif defect == 'symlink':
        link = tmp_path / 'linked'; link.symlink_to(output, target_is_directory=True)
        env['MMX_CI_FIXED_DIAGNOSTICS_DIR'] = str(link)
    else:
        phase = output / 'native-admission-unit'; phase.mkdir(mode=0o700)
        (phase / 'ci-fixed-diagnostics.json').write_text('KEEP')
    assert child_unit(root, env).returncode == 1
    if defect == 'already-owned':
        assert (output / 'native-admission-unit/ci-fixed-diagnostics.json').read_text() == 'KEEP'
    else: assert not list(output.iterdir())


def test_no_diagnostic_failure_or_private_repr_can_turn_original_success_into_failure(tmp_path):
    root, output, env = fixture(tmp_path, source='''import unittest
class Leaf(unittest.TestCase):
 def test_ok(self): pass
''')
    output.chmod(0o755)
    assert child_unit(root, env).returncode == 0
    assert not list(output.iterdir())


def check_layout(job):
    steps = job['steps']
    prepare = next(s for s in steps if s.get('name') == 'Prepare fixed test diagnostics')
    native = next(s for s in steps if s.get('name') == 'Verify native application admission and dispatch custody')
    repository = next(s for s in steps if s.get('name') == 'Run repository test shard')
    upload = next(s for s in steps if s.get('name') == 'Upload fixed test diagnostics')
    assert steps.index(prepare) < steps.index(native) < steps.index(repository) < steps.index(upload)
    assert upload['if'] == 'always()' and upload['timeout-minutes'] == 2
    assert job['timeout-minutes'] == 75 and repository['timeout-minutes'] == 45
    assert upload['with']['path'].splitlines() == [
        '${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/ci-fixed-diagnostics.json',
        '${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/native-admission-unit/ci-fixed-diagnostics.json',
        '${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/native-admission-rollout/ci-fixed-diagnostics.json']
    assert upload['with']['name'] == 'ci-fixed-diagnostics-${{ matrix.index }}'
    assert '-p scripts.ci_native_preflight' in native['run']
    block = native['run'].split("python - <<'PYTEST'\n", 1)[1].split('\nPYTEST', 1)[0]
    loop = next(n for n in ast.parse(block).body if isinstance(n, ast.For))
    assert tuple(ast.literal_eval(loop.iter)) == preflight.UNIT_PATTERNS
    import re
    modules = re.findall(r'(?:ops/native_fabric/quota_continuity/(?:tests|rollout)|tests)/test_[a-z_]+[.]py', native['run'])
    assert len(modules) == len(set(modules)) == 14 and set(modules) == preflight.ROLLOUT_MODULES
    assert 'raise SystemExit(not result.wasSuccessful())' in native['run']
    assert 'all(totals[k] == 0 for k in ("failures", "errors", "skipped"))' in native['run']


def test_actual_workflow_initializes_before_failure_and_retains_exact_tests_and_gates():
    from scripts.ci_pytest import _WorkflowYAMLLoader
    job = yaml.load((ROOT / '.github/workflows/ci.yml').read_text(), Loader=_WorkflowYAMLLoader)['jobs']['pytest_shards']
    check_layout(job)
    bad = copy.deepcopy(job)
    prepare = next(s for s in bad['steps'] if s.get('name') == 'Prepare fixed test diagnostics')
    bad['steps'].remove(prepare)
    where = next(i for i,s in enumerate(bad['steps']) if s.get('name') == 'Run repository test shard')
    bad['steps'].insert(where, prepare)
    with pytest.raises(AssertionError): check_layout(bad)


def test_actual_native_workflow_failure_retains_rollout_fact_before_repository_phase(tmp_path):
    root, output, env = fixture(tmp_path, UNIT, source="import unittest\nclass Leaf(unittest.TestCase):\n def test_ok(self):pass\n")
    for module in preflight.ROLLOUT_MODULES:
        path = root / module; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("def test_public():pass\n")
    (root / ROLLOUT).write_text("def test_failure():\n assert False, 'PRIVATE'\n")
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Fixture', '-c',
                    'user.email=fixture@example.invalid', 'commit', '-qm', 'rollout'], check=True)
    home = tmp_path / 'home'; home.mkdir(mode=0o700); env['HOME'] = str(home)
    # The real job already selected Python3.12; mirror that setup for its literal python command.
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', '')
    from scripts.ci_pytest import _WorkflowYAMLLoader
    workflow = yaml.load((ROOT / '.github/workflows/ci.yml').read_text(), Loader=_WorkflowYAMLLoader)
    command = next(s['run'] for s in workflow['jobs']['pytest_shards']['steps']
                   if s.get('name') == 'Verify native application admission and dispatch custody')
    # Execute the actual workflow body against inert tracked public test owners.
    result = subprocess.run(['bash', '--noprofile', '--norc', '-e', '-o', 'pipefail', '-c', command],
        cwd=root, env=env, capture_output=True, timeout=30)
    assert result.returncode == 1
    assert (output / 'native-admission-unit/ci-fixed-diagnostics.json').exists(), result.stderr.decode()[:1200]
    assert snapshot(output, 'native-admission-unit')['failures'] == []
    rows = snapshot(output, 'native-admission-rollout')['failures']
    assert len(rows) == 1 and rows[0]['module'] == ROLLOUT and rows[0]['case'] == 'test_failure'
    assert not list(home.iterdir())  # Original temp-root trap still executes.
    assert not (output / 'ci-fixed-diagnostics.json').exists()  # Repository phase never ran.
