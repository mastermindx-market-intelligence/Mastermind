"""Grounded discovery semantics: no claimed creativity or hidden execution."""
from copy import deepcopy
import json

import pytest

from brain import improvement_discovery as D

NOW = "2026-09-24T06:00:00Z"


@pytest.fixture
def bundle():
    return {
        "schema": D.INPUT_SCHEMA, "case_id": "gmi-revealed",
        "origin": "CHAIRMAN_REVEALED", "cutoff_at": None,
        "sources": [{
            "id": "source-1", "owner": "GITHUB", "ref": "repo/path",
            "revision": "a" * 40, "content_sha256": "sha256:" + "b" * 64,
            "available_at": "2026-09-23T00:00:00Z",
            "observed_at": "2026-09-24T05:00:00Z",
            "valid_until": "2026-09-25T05:00:00Z", "state": "CURRENT",
        }],
        "expectations": [{
            "id": "rerating", "scope": "gmi:finance", "user_job": "Explain sector changes",
            "consumer": "Existing sector research view", "requirement": "Causal mechanism evidence",
            "expectation_source": "source-1",
        }],
        "observations": [{
            "expectation_id": "rerating", "scope": "gmi:finance",
            "source_refs": ["source-1"], "scope_complete": True,
            "state": "GAP", "finding": "Explicit owner audit identifies a missing mechanism.",
        }],
        "existing_work": [],
    }


def result(bundle):
    return D.evaluate(bundle, now=NOW)


def entry(bundle):
    return result(bundle)["opportunities"][0]


def test_explicit_gap_retains_job_consumer_and_no_execution(bundle):
    r = result(bundle)
    assert entry(bundle)["diagnosis"] == "EVIDENCED_GAP"
    assert entry(bundle)["disposition"] == "REVIEW_AND_DUPLICATE_CHECK"
    assert r["jobs_created"] == 0
    assert r["execution_authority_granted"] is False
    assert r["independent_discovery_proven"] is False
    assert r["evaluation_use"] == "REVEALED_REGRESSION"
    assert entry(bundle)["alternatives"][-1] == "HOLD"


def test_missing_observation_is_not_a_gap(bundle):
    bundle["observations"] = []
    assert entry(bundle)["diagnosis"] == "UNASSESSED"


@pytest.mark.parametrize("state,complete,diagnosis", [
    ("UNKNOWN", False, "UNASSESSED"), ("GAP", False, "UNVERIFIED_GAP"),
    ("SATISFIED", True, "SATISFIED"), ("SATISFIED", False, "UNASSESSED"),
    ("NOT_EXPOSED", True, "CONSUMER_GAP"),
])
def test_completeness_and_observation_are_separate(bundle, state, complete, diagnosis):
    bundle["observations"][0].update(state=state, scope_complete=complete)
    assert entry(bundle)["diagnosis"] == diagnosis


@pytest.mark.parametrize("state", ["STALE", "UNAVAILABLE", "CONFLICT", "RETRACTED"])
def test_bad_source_holds_not_empty_success(bundle, state):
    bundle["sources"][0]["state"] = state
    assert entry(bundle)["diagnosis"] == "HELD_SOURCE"
    assert entry(bundle)["disposition"] == "RECONCILE_EVIDENCE"


def test_expiry_effective_state_visible(bundle):
    bundle["sources"][0]["valid_until"] = "2026-09-24T05:30:00Z"
    r = result(bundle)
    assert r["opportunities"][0]["source_problems"] == ["STALE"]
    assert r["sources"][0]["effective_state"] == "STALE"


def test_opposing_observations_never_majority_vote(bundle):
    other = deepcopy(bundle["observations"][0]); other["state"] = "SATISFIED"
    bundle["observations"].append(other)
    assert entry(bundle)["diagnosis"] == "CONFLICTING_OBSERVATIONS"


def test_existing_proposal_is_not_new_job_or_running_worker(bundle):
    bundle["existing_work"] = [{"expectation_id": "rerating", "source_ref": "source-1",
                                 "disposition": "OPEN_PROPOSAL"}]
    r = entry(bundle)
    assert r["disposition"] == "ATTACH_TO_EXISTING_PROPOSAL"
    assert "not a running worker" in r["next_evidence"]


@pytest.mark.parametrize("state,disposition", [("SATISFIED", "PRESERVE_ACCEPTED"),
                                              ("GAP", "RECONCILE_ACCEPTED")])
def test_accepted_work_cannot_be_silently_redone(bundle, state, disposition):
    bundle["observations"][0]["state"] = state
    bundle["existing_work"] = [{"expectation_id": "rerating", "source_ref": "source-1",
                                 "disposition": "ACCEPTED"}]
    assert entry(bundle)["disposition"] == disposition


def test_stable_opportunity_identity_but_changed_evidence_digest(bundle):
    before = result(bundle)
    bundle["sources"][0]["content_sha256"] = "sha256:" + "c" * 64
    after = result(bundle)
    assert before["opportunities"][0]["id"] == after["opportunities"][0]["id"]
    assert before["digest"] != after["digest"]


def test_input_not_mutated_and_semantic_reordering_is_stable(bundle):
    second = deepcopy(bundle["sources"][0]); second["id"] = "source-2"
    bundle["sources"].append(second)
    bundle["observations"][0]["source_refs"].append("source-2")
    before = deepcopy(bundle); first = result(bundle)
    assert bundle == before
    bundle["sources"].reverse(); bundle["observations"][0]["source_refs"].reverse()
    assert result(bundle) == first


def test_frozen_replay_rejects_later_evidence(bundle):
    bundle.update(origin="FROZEN_REPLAY", cutoff_at="2026-09-22T00:00:00Z")
    with pytest.raises(ValueError, match="post_cutoff_source"):
        result(bundle)


def test_frozen_replay_is_never_itself_creativity_proof(bundle):
    bundle.update(origin="FROZEN_REPLAY", cutoff_at="2026-09-23T12:00:00Z")
    assert result(bundle)["independent_discovery_proven"] is False


@pytest.mark.parametrize("mutate", [
    lambda b: b["sources"].append(deepcopy(b["sources"][0])),
    lambda b: b["expectations"].append(deepcopy(b["expectations"][0])),
    lambda b: b["observations"][0].update(source_refs=[]),
    lambda b: b["observations"][0].update(scope="other"),
    lambda b: b["observations"][0].update(scope_complete="yes"),
    lambda b: b["sources"][0].update(observed_at="2027-01-01T00:00:00Z"),
    lambda b: b["sources"][0].update(revision="master"),
    lambda b: b["sources"][0].update(content_sha256="guess"),
    lambda b: b.update(unbounded_permission=True),
])
def test_malformed_inputs_fail_closed(bundle, mutate):
    mutate(bundle)
    with pytest.raises(ValueError):
        result(bundle)


def test_public_projection_has_no_private_prose_or_refs(bundle):
    bundle["observations"][0]["finding"] = "SECRET_PRIVATE_RESEARCH"
    bundle["sources"][0]["ref"] = "private-canonical-source"
    projection = json.dumps(D.agenda_projection(result(bundle)))
    assert "SECRET_PRIVATE" not in projection
    assert "private-canonical" not in projection
    assert "EVIDENCED_GAP" in projection


def test_internal_markdown_neutralizes_markup(bundle):
    bundle["observations"][0]["finding"] = "<script>alert(1)</script> [click](javascript:x)"
    md = D.render_markdown(result(bundle))
    assert "<script>" not in md
    assert "[click](javascript:x)" not in md
    assert "Independent discovery is NOT proven" in md


@pytest.mark.parametrize("present,complete,state", [
    (["engine/a.py"], True, "GAP"),
    (["engine/a.py", "contracts/b.json"], True, "SATISFIED"),
    ([], False, "UNKNOWN"), (None, True, "UNKNOWN"),
])
def test_named_path_sensor_derives_observation_not_llm_label(present, complete, state):
    row = D.observe_named_paths(expectation_id="dependency-paths", scope="gmi:exact-dependencies",
        required_paths=["engine/a.py", "contracts/b.json"], present_paths=present,
        source_refs=["git-inventory"], inventory_complete=complete)
    assert row["state"] == state
    assert row["scope_complete"] is (complete and present is not None)


def test_named_path_sensor_refuses_traversal_and_out_of_scope():
    for required, present in [(["../secrets"], []), (["engine/a.py"], ["engine/b.py"])]:
        with pytest.raises(ValueError):
            D.observe_named_paths(expectation_id="dependency-paths", scope="gmi:exact-dependencies",
                required_paths=required, present_paths=present, source_refs=["git-inventory"],
                inventory_complete=True)


def test_committed_real_source_case_reproduces_without_broad_duplicate_suppression():
    from pathlib import Path
    directory = Path(__file__).resolve().parents[1] / "research" / "improvement_discovery"
    b = json.loads((directory / "GMI_SOURCE_CANARY_2026-09-24.input.json").read_text())
    expected = json.loads((directory / "GMI_SOURCE_CANARY_2026-09-24.result.json").read_text())
    assert D.evaluate(b, now=expected["as_of"]) == expected
    summary = D.agenda_projection(expected)
    assert summary["diagnosis_counts"] == {"EVIDENCED_GAP": 6, "UNASSESSED": 1}
    assert summary["disposition_counts"] == {"ATTACH_TO_EXISTING_PROPOSAL": 4, "REVIEW_AND_DUPLICATE_CHECK": 3}
    assert expected["evaluation_use"] == "REVEALED_REGRESSION"
