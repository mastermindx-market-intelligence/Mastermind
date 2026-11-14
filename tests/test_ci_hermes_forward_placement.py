"""One measured placement table; the canonical resolver/coverage owner stays."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import ci_pytest as cip

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'tests/test_hermes_primary_application_enrollment.py'
# CI Lightning F3 re-derivation, measured on exact merge-group run 42708053350:
# the 150 slowest measured included modules are pinned longest-processing-time-
# first over overhead-aware starting loads, and TARGET keeps its hermes-forward
# pin on shard 4. Any table change requires new evidence and this hash to move.
# Since ci/pytest_timings.json landed, this frozen table is the FALLBACK used
# only when the timing table is missing or invalid; the fixture below forces
# that fallback so the frozen contract stays exactly verified.
F3_EVIDENCE = 'ci/shard_timings/42708053350.json'
F3_SOURCE_RUN = 42708053350
F3_TABLE_SHA256 = '7b298530d545a62576288712ecdef21b57108b918fc0d37d5d690cfb0b4f1521'
LEGACY_HERMES_FORWARD_SHA256 = 'eb8af32eaaab6403554719ca32fe7e0fa495fd92ba081badcc2f5e688474c2c2'


@pytest.fixture(autouse=True)
def frozen_fallback(monkeypatch):
    monkeypatch.setattr(cip, 'load_module_timings', lambda path=None: None)


def positions(shards):
    return {path: index for index, shard in enumerate(shards) for path in shard}


def pinned_table():
    pins = dict(cip._MEASURED_SIX_JOB_PLACEMENT)
    canonical = json.dumps(pins, sort_keys=True, separators=(',', ':')).encode()
    assert len(pins) == 151 and hashlib.sha256(canonical).hexdigest() == F3_TABLE_SHA256
    return pins


def check_f3_contract(included):
    pins = pinned_table()
    evidence = json.loads((ROOT / F3_EVIDENCE).read_text())
    assert evidence['source_run'] == F3_SOURCE_RUN
    assert evidence['pinned_modules'] == len(pins)
    # The LPT pins are exactly the 150 slowest modules the frozen evidence
    # measured, minus the canonical exclusions (deterministic tie-break);
    # TARGET is not among them and keeps shard 4. Derived from the frozen
    # evidence, not today's inclusion set, so deleting or renaming a pinned
    # module cannot promote an unpinned one into the comparison.
    excluded = set(cip.resolve_gate(ROOT)['excluded'])
    measured = {
        path: seconds for path, seconds in evidence['modules'].items()
        if path not in excluded and path != TARGET
    }
    slowest = sorted(measured.items(), key=lambda item: (-item[1], item[0]))[:150]
    assert {path for path in pins if path != TARGET} == {path for path, _ in slowest}
    assert pins[TARGET] == 4
    shards = cip.partition_modules(included, jobs=6)
    cip.verify_partition(included, shards)
    placed = positions(shards)
    assert sorted(placed) == sorted(included)
    assert placed[TARGET] == 4
    # A pin whose module was since removed is inert; every present one holds.
    assert all(placed[path] == shard for path, shard in pins.items() if path in placed)
    return placed


def hashed(path, jobs):
    return int.from_bytes(hashlib.sha256(path.encode()).digest()[:8], 'big') % jobs


def test_canonical_plan_pins_measured_slowest_and_covers_every_module_once():
    included = cip.resolve_gate(ROOT)['included']
    assert TARGET in included
    check_f3_contract(included)


@pytest.mark.parametrize('jobs', [1, 2, 3, 4, 5, 8])
def test_forward_pin_cannot_change_other_job_counts(jobs):
    included = cip.resolve_gate(ROOT)['included']
    shards = cip.partition_modules(included, jobs=jobs)
    cip.verify_partition(included, shards)
    for path, index in positions(shards).items():
        expected = cip._MEASURED_THREE_JOB_PLACEMENT.get(path, hashed(path, jobs)) if jobs == 3 else hashed(path, jobs)
        assert index == expected


def test_removed_pinned_module_does_not_break_the_contract():
    included = cip.resolve_gate(ROOT)['included']
    pins = pinned_table()
    gone = next(path for path in sorted(pins) if path != TARGET)
    before = check_f3_contract(included)
    after = check_f3_contract(tuple(path for path in included if path != gone))
    assert all(after[path] == index for path, index in before.items() if path != gone)


def test_new_module_does_not_reshuffle_existing_assignments():
    included = cip.resolve_gate(ROOT)['included']
    before = check_f3_contract(included)
    extended = tuple(sorted((*included, 'tests/test_future_forward_pin_fixture.py')))
    after = positions(cip.partition_modules(extended, jobs=6))
    assert all(after[path] == index for path, index in before.items())


@pytest.mark.parametrize('mutation', ['table-value', 'unrelated-pin'])
def test_unapproved_additional_placement_changes_are_detected(monkeypatch, mutation):
    pins = dict(cip._MEASURED_SIX_JOB_PLACEMENT)
    if mutation == 'table-value':
        path = next(iter(pins)); pins[path] = (pins[path]+1) % 6
    else:
        pins['tests/test_unrelated_future_module.py'] = 1
    monkeypatch.setattr(cip, '_MEASURED_SIX_JOB_PLACEMENT', pins)
    with pytest.raises(AssertionError):
        pinned_table()


def test_retained_evidence_is_partial_and_does_not_claim_measured_speedup():
    value = json.loads((ROOT/'ci/shard_timings/42540190617-hermes-forward.json').read_text())
    assert value['source_run'] == 42540190617
    assert value['head'] == 'a40e48ef38f8b1afa1a69776711a9dae9a07ea19'
    assert value['observation']['module'] == TARGET and value['observation']['cases_finished'] == 44
    assert value['retention']['truncated'] is True and value['retention']['summary_rows'] == 256
    assert value['whole_run_speedup_measured'] is False
    assert value['historical_map_sha256'] == LEGACY_HERMES_FORWARD_SHA256
