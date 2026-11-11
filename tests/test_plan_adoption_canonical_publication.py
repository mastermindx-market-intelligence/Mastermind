"""Actual two-phase temp-Git publication/Events -> nominal READ proof.

No live grants, credentials, services or publication. The existing action
fixture uses the real a5 compiler/private owner and a disposable bare remote.
"""
from copy import deepcopy
import pytest
from tests.test_project_plan_adoption_source_owner import joined, advance_request
from tests.test_agentos_plan_continuity_capture import repository, read
from tests.test_workspace_plan_adoption_git_publisher import isolated_git_env
from control_plane.canonical_data_publication import capture_source_publication, select_source_publication, CanonicalPublicationUnavailable
from common.plan_adoption_publication_contract import validate_adoption_publication


def settled(f):
    _, pending = f.prepare_submit(); f.merge(pending)
    ready = f.source.reconcile(f.lookup, f.who)
    pending = f.source.advance(advance_request(f, ready), f.who); f.merge(pending)
    return f.source.reconcile(f.lookup, f.who)


def test_actual_final_adoption_sources_reopen_as_nominal_proof_and_real_plan_compare(joined):
    f = joined; final = settled(f)
    scope = f.permissions.bind(f.who, action="ADOPT_PLAN", work_ref=f.work).principal_scope
    proof = capture_source_publication(f.events, f.lookup, scope, guard=lambda: True)
    actual = proof.check(scope)
    assert actual["sources"] == final["receipt"]["sources"]
    assert len(actual["sources"]) == 3 and actual["selection"]["request_id"] == f.rid
    binding = f.events.publication_binding(f.lookup, scope, phase="ADOPTION", guard=lambda: True)
    validate_adoption_publication(actual["selection"], binding["postimages"], actual["sources"])
    chosen = select_source_publication(f.events, f.work, scope, guard=lambda: True,
        qualify=lambda candidate: candidate.check(scope) == actual)
    assert chosen.check(scope) == actual
    body, _ = read(f.repo)
    assert body["continuity"]["adoption"]["state"] == "AVAILABLE"
    assert body["continuity"]["adoption"]["decision_ref"] == "DEC:PLAN-ADOPTION-" + "9" * 40
    row = body["continuity"]["proposals"]["items"][0]
    assert row["adoption_relation"] == "CURRENT_DECISION_REFERENCES_PROPOSAL"
    assert row["comparison_basis"] == "RECORDED_PREDECESSOR"
    assert f.pr.create_calls == 2 and f.runtime.jobs.list_jobs() == []
    # A current READ guard is required for every requalification; a receipt
    # dictionary or write grant is not substituted for this nominal owner.
    with pytest.raises(CanonicalPublicationUnavailable): proof.check("f" * 64)
    with pytest.raises(CanonicalPublicationUnavailable): capture_source_publication(f.events, f.lookup, scope, guard=lambda: False)


def test_candidate_ready_and_unsettled_decision_never_qualify_as_adoption(joined):
    f = joined; _, pending = f.prepare_submit()
    scope = f.permissions.bind(f.who, action="ADOPT_PLAN", work_ref=f.work).principal_scope
    with pytest.raises(CanonicalPublicationUnavailable): capture_source_publication(f.events, f.lookup, scope, guard=lambda: True)
    f.merge(pending); ready = f.source.reconcile(f.lookup, f.who)
    assert ready["reason"] == "READY_FOR_ADVANCE"
    assert f.events.publication_candidates(f.work, scope, guard=lambda: True)["lookups"] == []
    with pytest.raises(CanonicalPublicationUnavailable): capture_source_publication(f.events, f.lookup, scope, guard=lambda: True)
    f.source.advance(advance_request(f, ready), f.who)  # PR only, not default
    with pytest.raises(CanonicalPublicationUnavailable): capture_source_publication(f.events, f.lookup, scope, guard=lambda: True)


@pytest.mark.parametrize("fault", ["partial", "mixed_commit", "wrong_command", "wrong_work", "wrong_predecessor", "duplicate", "wrong_before"])
def test_whole_original_phase_postimages_are_required(joined, fault):
    f = joined; final = settled(f)
    scope = f.permissions.bind(f.who, action="ADOPT_PLAN", work_ref=f.work).principal_scope
    binding = f.events.publication_binding(f.lookup, scope, phase="ADOPTION", guard=lambda: True)
    images, sources = deepcopy(binding["postimages"]), deepcopy(final["receipt"]["sources"])
    selection = {k: f.lookup[k] for k in ("action", "request_id", "work_ref")}
    if fault == "partial": sources.pop()
    if fault == "mixed_commit": sources[0]["commit"] = "a" * 40
    if fault == "wrong_command": selection["request_id"] = "mmos-project-adopt-" + "8" * 40
    if fault == "wrong_work": selection["work_ref"] = "WS:FOREIGN"
    if fault == "wrong_predecessor": sources[-1]["path"] = "agentos/decisions/DEC-FOREIGN.md"
    if fault == "duplicate": sources[1] = deepcopy(sources[0])
    if fault == "wrong_before": next(i for i in images if i["path"].startswith("agentos/workstreams/"))["expected_preimage_sha256"] = None
    with pytest.raises(ValueError): validate_adoption_publication(selection, images, sources)
