"""One measured placement delta; the canonical resolver/coverage owner stays."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import ci_pytest as cip

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'tests/test_hermes_primary_application_enrollment.py'
HISTORICAL = 'eb8af32eaaab6403554719ca32fe7e0fa495fd92ba081badcc2f5e688474c2c2'


def positions(shards):
    return {path: index for index, shard in enumerate(shards) for path in shard}


def historical_pins():
    pins = {path: shard for path, shard in cip._MEASURED_SIX_JOB_PLACEMENT.items() if path != TARGET}
    canonical = json.dumps(pins, sort_keys=True, separators=(',', ':')).encode()
    assert len(pins) == 150 and hashlib.sha256(canonical).hexdigest() == HISTORICAL
    return pins


def hashed(path, jobs):
    return int.from_bytes(hashlib.sha256(path.encode()).digest()[:8], 'big') % jobs


def check_forward_contract(included):
    prior = historical_pins()
    before = {path: prior.get(path, hashed(path, 6)) for path in included}
    shards = cip.partition_modules(included, jobs=6)
    cip.verify_partition(included, shards)
    after = positions(shards)
    assert sorted(path for path in included if before[path] != after[path]) == [TARGET]
    assert before[TARGET] == 0 and after[TARGET] == 4
    assert sorted(path for shard in shards for path in shard) == sorted(included)
    assert len(after) == len(included)
    return after


def test_canonical_plan_moves_only_measured_hermes_module_and_covers_every_module_once():
    included = cip.resolve_gate(ROOT)['included']
    assert TARGET in included
    check_forward_contract(included)


@pytest.mark.parametrize('jobs', [1, 2, 3, 4, 5, 8])
def test_forward_pin_cannot_change_other_job_counts(jobs):
    included = cip.resolve_gate(ROOT)['included']
    shards = cip.partition_modules(included, jobs=jobs)
    cip.verify_partition(included, shards)
    for path, index in positions(shards).items():
        expected = cip._MEASURED_THREE_JOB_PLACEMENT.get(path, hashed(path, jobs)) if jobs == 3 else hashed(path, jobs)
        assert index == expected


def test_new_module_does_not_reshuffle_existing_assignments():
    included = cip.resolve_gate(ROOT)['included']
    before = check_forward_contract(included)
    extended = tuple(sorted((*included, 'tests/test_future_forward_pin_fixture.py')))
    after = positions(cip.partition_modules(extended, jobs=6))
    assert all(after[path] == index for path, index in before.items())


@pytest.mark.parametrize('mutation', ['historical-value', 'unrelated-pin'])
def test_unapproved_additional_placement_changes_are_detected(monkeypatch, mutation):
    pins = dict(cip._MEASURED_SIX_JOB_PLACEMENT)
    if mutation == 'historical-value':
        path = next(iter(pins)); pins[path] = (pins[path]+1) % 6
    else:
        pins['tests/test_unrelated_future_module.py'] = 1
    monkeypatch.setattr(cip, '_MEASURED_SIX_JOB_PLACEMENT', pins)
    with pytest.raises(AssertionError):
        historical_pins()


def test_retained_evidence_is_partial_and_does_not_claim_measured_speedup():
    value = json.loads((ROOT/'ci/shard_timings/42540190617-hermes-forward.json').read_text())
    assert value['source_run'] == 42540190617
    assert value['head'] == 'a40e48ef38f8b1afa1a69776711a9dae9a07ea19'
    assert value['observation']['module'] == TARGET and value['observation']['cases_finished'] == 44
    assert value['retention']['truncated'] is True and value['retention']['summary_rows'] == 256
    assert value['whole_run_speedup_measured'] is False
    assert value['historical_map_sha256'] == HISTORICAL
