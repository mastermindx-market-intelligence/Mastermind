"""Offline, provider-free qualification for the Harness^2 adaptation evidence bridge."""
import copy

import pytest

from scripts.agent_eval.harness2_bridge import (
    SCHEMA, Harness2ComparisonError, assess,
)


def fixture(n=10, gain=0.1):
    rows = []
    for i in range(n):
        for arm, score in (("baseline", 0.60), ("candidate", 0.60 + gain)):
            rows.append(dict(case_id=f"case-{i}", split="sealed_holdout", arm=arm,
                             score=score, accepted=True, resource_units=5,
                             authority_violations=0, effect_state="NONE",
                             grader_digest="f" * 64))
    return dict(schema=SCHEMA, experiment_id="local-test", task_domain="code",
                harness2_source_sha="1cfe254e8d25b15f37048c3730134686abe60335",
                baseline_harness_digest="a" * 64,
                candidate_harness_digest="b" * 64,
                configuration_digest="c" * 64,
                holdout_commitment_digest="d" * 64,
                observations=rows)


def test_eligible_is_only_proposal():
    r = assess(fixture())
    assert r["status"] == "PROPOSAL_ELIGIBLE_FOR_INDEPENDENT_REVIEW"
    assert r["promotion"] == "NONE"
    assert r["runtime_authority"] == "NONE"
    assert not r["automatic_agentos_write"]
    assert r["matched_holdout_cases"] == 10


def test_insufficient_sample_refuses():
    assert assess(fixture(n=9))["status"] == "INSUFFICIENT_OR_REGRESSIVE_EVIDENCE"


def test_nonimproving_candidate_refuses():
    assert assess(fixture(gain=-0.1))["status"] == "INSUFFICIENT_OR_REGRESSIVE_EVIDENCE"


def test_safety_regression_refuses():
    d = fixture()
    d["observations"][1]["authority_violations"] = 1
    assert assess(d)["status"] == "INSUFFICIENT_OR_REGRESSIVE_EVIDENCE"


def test_acceptance_regression_refuses():
    d = fixture()
    d["observations"][1]["accepted"] = False
    assert assess(d)["status"] == "INSUFFICIENT_OR_REGRESSIVE_EVIDENCE"


def test_failed_candidate_refuses_even_when_baseline_also_fails():
    d = fixture()
    d["observations"][0]["accepted"] = False
    d["observations"][1]["accepted"] = False
    assert assess(d)["status"] == "INSUFFICIENT_OR_REGRESSIVE_EVIDENCE"


def test_resource_regression_refuses():
    d = fixture()
    d["observations"][1]["resource_units"] = 100
    assert assess(d)["status"] == "INSUFFICIENT_OR_REGRESSIVE_EVIDENCE"


@pytest.mark.parametrize("change", [
    lambda d: d["observations"].append(copy.deepcopy(d["observations"][0])),
    lambda d: d["observations"].pop(),
    lambda d: d["observations"][0].update(split="training"),
    lambda d: d["observations"][0].update(effect_state="EFFECT_UNKNOWN"),
    lambda d: d["observations"][0].update(score=float("nan")),
    lambda d: d["observations"][0].update(score=True),
    lambda d: d["observations"][0].update(accepted=1),
    lambda d: d["observations"][0].update(authority_violations=True),
    lambda d: d["observations"][0].update(grader_digest="e" * 64),
    lambda d: d.update(candidate_harness_digest=d["baseline_harness_digest"]),
    lambda d: d.update(schema="wrong"),
    lambda d: d.update(unexpected=True),
    lambda d: d["observations"][0].update(extra="bad"),
])
def test_bad_inputs_fail_closed(change):
    d = fixture()
    change(d)
    with pytest.raises(Harness2ComparisonError):
        assess(d)


def test_pure_repeatable_digests_and_input_unchanged():
    d = fixture()
    original = copy.deepcopy(d)
    assert assess(d) == assess(d)
    assert d == original
