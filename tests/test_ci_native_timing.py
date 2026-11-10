"""Genuine inert framework callbacks; fake clocks are explicit fixture operands."""
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import ci_native_preflight as preflight
from scripts import ci_fixed_diagnostics as fixed
from tests.test_ci_native_preflight import fixture, snapshot, UNIT, ROLLOUT


def unit_with_clock(root, env, ticks, *, extra=''):
    code = ("import unittest,time\nfrom scripts import ci_native_preflight as p\n"
            f"ticks=iter({ticks})\n"
            "def clock():\n value=next(ticks)\n"
            " if isinstance(value,Exception): raise value\n return value\n"
            "time.monotonic_ns=clock\n" + extra + '\n'
            f'suite=unittest.defaultTestLoader.discover("{Path(UNIT).parent}", pattern="{Path(UNIT).name}")\n'
            'result=p.unittest_runner(verbosity=0).run(suite)\nraise SystemExit(not result.wasSuccessful())\n')
    return subprocess.run([sys.executable, '-c', code], cwd=root, env=env,
                          capture_output=True, timeout=30)


def test_actual_successful_unittest_retains_measured_elapsed_and_original_result(tmp_path):
    root, output, env = fixture(tmp_path, source='''import unittest
class Leaf(unittest.TestCase):
 def test_a(self): pass
 def test_b(self): pass
''')
    result = unit_with_clock(root, env, '[0,1000000000,3000000000,4000000000,9000000000,12000000000]')
    assert result.returncode == 0, result.stderr
    value = snapshot(output, 'native-admission-unit')
    assert value['failures'] == [] and value['timing_observations'] == 2
    assert {(r['case'], r['phase'], r['seconds']) for r in value['timings']} == {
        ('Leaf.test_a', 'test', 2.0), ('Leaf.test_b', 'test', 5.0)}
    assert all(r['module'] == UNIT for r in value['timings'])
    assert value['envelope'] == {'scope': 'unittest_runner', 'seconds': 12.0}


def test_actual_pytest_retains_only_public_case_and_real_phase_durations(tmp_path):
    root, output, env = fixture(tmp_path, ROLLOUT, source='''import pytest
@pytest.fixture
def prepared(): return 7
@pytest.mark.parametrize("secret", [pytest.param("PRIVATE",id="PRIVATE-token")])
def test_public(secret, prepared): assert prepared == 7
''')
    result = subprocess.run([sys.executable, '-m', 'pytest', '--noconftest', '-q',
        '-p', 'scripts.ci_native_preflight', ROLLOUT], cwd=root, env=env,
        capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    value = snapshot(output, 'native-admission-rollout')
    assert value['failures'] == [] and value['timing_observations'] == 3
    assert {r['phase'] for r in value['timings']} == {'setup', 'call', 'teardown'}
    assert all(r['module'] == ROLLOUT and r['case'] == 'test_public'
               and math.isfinite(r['seconds']) and r['seconds'] >= 0 for r in value['timings'])
    assert value['envelope']['scope'] == 'pytest_session'
    assert value['envelope']['seconds'] >= sum(r['seconds'] for r in value['timings']) - 0.000003


def test_runner_envelope_includes_class_fixtures_without_claiming_discovery_time(tmp_path):
    root, output, env = fixture(tmp_path, source='''import unittest,__main__
class Leaf(unittest.TestCase):
 @classmethod
 def setUpClass(cls): __main__.ticks_ns += 20000000000
 def test_public(self): __main__.ticks_ns += 3000000000
 @classmethod
 def tearDownClass(cls): __main__.ticks_ns += 5000000000
''')
    code = ("import unittest,time\nfrom scripts import ci_native_preflight as p\n"
            "ticks_ns=0\ntime.monotonic_ns=lambda:ticks_ns\n"
            f'suite=unittest.defaultTestLoader.discover("{Path(UNIT).parent}",pattern="{Path(UNIT).name}")\n'
            "ticks_ns=100000000000\n"  # Before runner: explicitly unmeasured discovery/startup.
            "result=p.unittest_runner(verbosity=0).run(suite)\nraise SystemExit(not result.wasSuccessful())\n")
    result = subprocess.run([sys.executable,'-c',code],cwd=root,env=env,capture_output=True,timeout=30)
    assert result.returncode == 0, result.stderr
    value=snapshot(output,'native-admission-unit')
    assert value['envelope']=={'scope':'unittest_runner','seconds':28.0}
    assert value['timings']==[{'module':UNIT,'case':'Leaf.test_public','phase':'test','seconds':3.0}]
    # The25s gap is runner work outside this test span, not a source-attributed phase.
    assert value['envelope']['seconds']-sum(r['seconds'] for r in value['timings'])==25.0


def test_oversized_but_public_case_cannot_expand_timing_identifiers(tmp_path):
    name='A'*128; method='test_'+'a'*123
    root,output,env=fixture(tmp_path,source=f'import unittest\nclass {name}(unittest.TestCase):\n def {method}(self): pass\n')
    assert unit_with_clock(root,env,'[0,1,2,3]').returncode==0
    value=snapshot(output,'native-admission-unit')
    assert value['failures']==[] and value.get('timings',[])==[] and value['truncated'] is True


@pytest.mark.parametrize('ticks', [
    '[0,10,9,20]', '[False]', '[float("nan")]', '[RuntimeError("PRIVATE")]',
    '[0,10,RuntimeError("PRIVATE"),20]', '[0,0,7201000000000,7201000000000]',
])
def test_clock_adversity_keeps_success_and_never_fabricates_duration(tmp_path, ticks):
    root, output, env = fixture(tmp_path, source='''import unittest
class Leaf(unittest.TestCase):
 def test_ok(self): pass
''')
    assert unit_with_clock(root, env, ticks).returncode == 0
    value = snapshot(output, 'native-admission-unit')
    assert value['failures'] == [] and value['truncated'] is True
    assert value.get('timings', []) == []


def test_bounded_retention_keeps_slowest_real_observations_and_truthful_count(tmp_path):
    count = preflight.MAX_TIMINGS + 5
    source = 'import unittest\nclass Leaf(unittest.TestCase):\n' + ''.join(
        f' def test_n{i:03d}(self): pass\n' for i in range(count))
    root, output, env = fixture(tmp_path, source=source)
    ticks = [0]; now = 1000000000
    for n in range(1, count + 1):
        ticks.extend([now, now + n * 1000000000]); now += (n + 1) * 1000000000
    ticks.append(now)
    assert unit_with_clock(root, env, repr(ticks)).returncode == 0
    value = snapshot(output, 'native-admission-unit')
    assert value['timing_observations'] == count and value['truncated'] is True
    assert len(value['timings']) == preflight.MAX_TIMINGS
    assert [r['seconds'] for r in value['timings']] == list(range(count, 5, -1))
    assert (output/'native-admission-unit/ci-fixed-diagnostics.json').stat().st_size <= fixed.MAX_SNAPSHOT


def test_same_writer_byte_bound_preserves_failure_facts_and_retains_slowest(tmp_path):
    source = 'import unittest\nclass Leaf(unittest.TestCase):\n' + ''.join(
        f' def test_n{i:03d}(self): pass\n' for i in range(20)) + ' def test_z_failure(self): self.fail("PRIVATE")\n'
    root, output, env = fixture(tmp_path, source=source)
    ticks=[0]; now=1000000000
    for n in range(1,22): ticks.extend([now,now+n*1000000000]);now+=(n+1)*1000000000
    ticks.append(now)
    assert unit_with_clock(root, env, repr(ticks), extra='p.fixed.MAX_SNAPSHOT=1024').returncode == 1
    value = snapshot(output, 'native-admission-unit')
    assert value['timing_observations'] == 21 and value['truncated'] is True
    assert len(value['failures'])==1 and value['failures'][0]['case']=='Leaf.test_z_failure'
    assert value['failures'][0]['kind']=='AssertionError' and value['timings'][0]['seconds']==21
    assert len(value['timings']) < 21
    assert (output/'native-admission-unit/ci-fixed-diagnostics.json').stat().st_size <= 1024


@pytest.mark.parametrize('bad', ['count-bool', 'count-overflow', 'row-mutation', 'forged-row', 'envelope-mutation'])
def test_tampered_timing_state_cannot_replace_qualified_snapshot(tmp_path, monkeypatch, bad):
    root, output, env = fixture(tmp_path, source='import unittest\nclass Leaf(unittest.TestCase):\n def test_ok(self): pass\n')
    monkeypatch.setattr(preflight, 'ROOT', root)
    monkeypatch.setenv('MMX_CI_FIXED_DIAGNOSTICS_DIR', str(output))
    writer = preflight._writer('native-admission-unit')
    writer.timing_record(UNIT+'::Leaf::test_ok', 'test', 2)
    writer.begin_envelope('unittest_runner'); writer.end_envelope('unittest_runner')
    path=output/'native-admission-unit/ci-fixed-diagnostics.json'; before=path.read_bytes()
    if bad == 'count-bool': writer.timing_observations = True
    elif bad == 'count-overflow': writer.timing_observations = preflight.MAX_OBSERVATIONS+1
    elif bad == 'row-mutation': writer.timings[0]['module'] = 'PRIVATE'
    elif bad == 'forged-row': writer.timings.append(dict(writer.timings[0]))
    else: writer.envelope['scope']='PRIVATE'
    writer.flush()
    assert path.read_bytes() == before


@pytest.mark.parametrize('node,phase,seconds', [
    (UNIT+'::Leaf::test_ok','setup',1), (UNIT+'::Leaf::foreign','test',1),
    ('PRIVATE::test_ok','test',1), (UNIT+'::Leaf::test_ok','test',True),
    (UNIT+'::Leaf::test_ok','test',float('nan')), (UNIT+'::Leaf::test_ok','test',-1),
])
def test_unqualified_ids_phases_and_values_never_become_timing_facts(tmp_path, monkeypatch, node, phase, seconds):
    root, output, env = fixture(tmp_path, source='import unittest\nclass Leaf(unittest.TestCase):\n def test_ok(self): pass\n')
    monkeypatch.setattr(preflight, 'ROOT', root)
    monkeypatch.setenv('MMX_CI_FIXED_DIAGNOSTICS_DIR', str(output))
    writer=preflight._writer('native-admission-unit')
    writer.timing_record(node,phase,seconds)
    value=snapshot(output,'native-admission-unit')
    assert 'timings' not in value and value['truncated'] is True
