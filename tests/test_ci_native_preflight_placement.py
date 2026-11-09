"""Placement of the whole existing native gate; no native test/timing rerun."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts import ci_parallel_shard as fan
from scripts import ci_pytest as cip

ROOT = Path(__file__).resolve().parents[1]
NAME = 'Verify native application admission and dispatch custody'


def workflow():
    return yaml.load((ROOT/'.github/workflows/ci.yml').read_text(), Loader=cip._WorkflowYAMLLoader)


def step(job, name):
    matches=[s for s in job['steps'] if s.get('name')==name]
    assert len(matches)==1
    return matches[0]


def contract(value):
    fan.validate_parallel_workflow(yaml.safe_dump(value, sort_keys=False))
    job=value['jobs']['pytest_shards']; steps=job['steps']; native=step(job, NAME)
    assert job['strategy']['matrix']['index']==[0,1,2,3,4,5]
    assert job['strategy']['max-parallel']==6 and job['strategy']['fail-fast'] is False
    assert job['runs-on']=='ubuntu-latest'
    assert job['permissions']=={'contents':'read','actions':'read'}
    assert native['if']=='matrix.index == 5'
    # Prerequisites are unconditional and in the SAME job for every matrix worker.
    prerequisites=[s for s in steps if s.get('uses') in ('actions/setup-node@v4','actions/setup-python@v5')]
    prerequisites += [step(job,'Install project'),step(job,'Prepare fixed test diagnostics')]
    assert len(prerequisites)==4
    for prior in prerequisites:
        assert prior.get('if') is None and steps.index(prior)<steps.index(native)
    evidence=json.loads((ROOT/'ci/shard_timings/42545600621-native-forward.json').read_text())
    assert hashlib.sha256(native['run'].encode()).hexdigest()==evidence['unchanged_step_body_sha256']
    assert '$GITHUB_ENV' not in native['run'] and '$GITHUB_OUTPUT' not in native['run']
    assert 'NATIVE_ROLLOUT_TEST_ROOT="$native_rollout_test_root" python -m pytest' in native['run']
    assert "trap 'rm -rf \"$native_rollout_test_root\"' EXIT" in native['run']
    # Its scratch/JUnit proof is not a functional input to any following gate.
    for later in steps[steps.index(native)+1:]:
        assert not any(name in later.get('run','') for name in (
            'native_rollout_test_root','native-proof.xml','NATIVE_ROLLOUT_TEST_ROOT'))
    upload=step(job,'Upload fixed test diagnostics')
    assert steps.index(upload)>steps.index(native) and upload['if']=='always()'
    assert upload['with']['name']=='ci-fixed-diagnostics-${{ matrix.index }}'
    assert upload['with']['path'].splitlines()==[
        '${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/ci-fixed-diagnostics.json',
        '${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/native-admission-unit/ci-fixed-diagnostics.json',
        '${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/native-admission-rollout/ci-fixed-diagnostics.json']
    assert job['timeout-minutes']==75 and step(job,'Run repository test shard')['timeout-minutes']==45
    assert upload['timeout-minutes']==2 and value['jobs']['test']['timeout-minutes']==8


def test_actual_native_gate_runs_once_on_worker_five_with_common_prerequisites():
    value=workflow();contract(value)
    native=step(value['jobs']['pytest_shards'],NAME)
    selected=[i for i in range(6) if native['if']==f'matrix.index == {i}']
    assert selected==[5]


@pytest.mark.parametrize('condition',[None,True,False,'matrix.index == 0','matrix.index == 4',
    "${{ matrix.index == 5 && steps.previous_ci.outputs.reuse != 'true' }}"])
def test_real_validator_refuses_wrong_missing_or_reuse_gated_native_assignment(condition):
    value=workflow();native=step(value['jobs']['pytest_shards'],NAME)
    if condition is None:native.pop('if')
    else:native['if']=condition
    with pytest.raises(cip.PolicyError):fan.validate_parallel_workflow(yaml.safe_dump(value,sort_keys=False))


@pytest.mark.parametrize('mutation',['missing','duplicate','after-proof'])
def test_real_validator_refuses_dropped_duplicated_or_reused_native_gate(mutation):
    value=workflow();job=value['jobs']['pytest_shards'];native=step(job,NAME)
    if mutation=='missing':job['steps'].remove(native)
    elif mutation=='duplicate':job['steps'].append(copy.deepcopy(native))
    else:
        job['steps'].remove(native);job['steps'].append(native)
    with pytest.raises(cip.PolicyError):fan.validate_parallel_workflow(yaml.safe_dump(value,sort_keys=False))


@pytest.mark.parametrize('name',['Install project','Prepare fixed test diagnostics'])
def test_prerequisites_cannot_be_shard_zero_only(name):
    value=workflow();step(value['jobs']['pytest_shards'],name)['if']='matrix.index == 0'
    with pytest.raises(AssertionError):contract(value)


def test_whole_native_body_and_all_checks_cannot_silently_shrink():
    value=workflow();native=step(value['jobs']['pytest_shards'],NAME)
    native['run']=native['run'].replace('test_qwen_account_eligibility.py','test_omitted.py')
    with pytest.raises(AssertionError):contract(value)


def test_measured_placement_does_not_claim_complete_setup_or_speedup():
    value=json.loads((ROOT/'ci/shard_timings/42545600621-native-forward.json').read_text())
    assert value['observed_native_step_seconds']==754
    assert value['observed_unit_envelope_seconds']==38.937942
    assert value['observed_rollout_envelope_seconds']==713.602082
    assert value['target_worker']==5 and value['whole_run_speedup_measured'] is False
