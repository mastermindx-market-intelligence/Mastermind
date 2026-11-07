"""Real temporary Runtime Events; no provider, Git, installed or live effects."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.workspace_source_operations import SourceOperationEvents, SourceOperationConflict

SCOPE = "1" * 64
FP = "2" * 64
STAMP = "3" * 64
REF = {"schema": "mastermind.terminal_original_input_reference.v1",
       "input_ref": "terminal-input:" + "4" * 64,
       "artifact_sha256": "5" * 64, "payload_sha256": "6" * 64}
SOURCE = {"repository": "macro", "commit": "a" * 40,
          "path": "agentos/workstreams/WS-TEST.md", "content_sha256": "b" * 64}
PR = {"number": 7, "url": "https://github.com/mastermindx-market-intelligence/macro/pull/7",
      "head_commit": "c" * 40, "head_branch": "project-source-test"}


def lookup(action="ADOPT_PLAN"):
    prefix = "mmos-project-adopt-" if action == "ADOPT_PLAN" else "mmos-project-create-"
    return {"schema": "mastermind.workspace_source_operation_lookup.v1", "action": action,
            "request_id": prefix + "a" * 40, "work_ref": "WS:TEST"}


@pytest.fixture
def env(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    return runtime, SourceOperationEvents(runtime.store)


def prepare(owner, selected=None, **changes):
    args = {"request_sha256": "7" * 64, "recipe_fingerprint_sha256": FP,
            "original_input": REF, "permission_binding_digest": STAMP, "guard": lambda: True}
    args.update(changes)
    return owner.prepare(selected or lookup(), SCOPE, **args)


def claim(owner, selected=None, **changes):
    args = {"permission_binding_digest": STAMP, "guard": lambda: True,
            "preview_witness": {"original_input": REF, "recipe_fingerprint_sha256": FP}}
    args.update(changes)
    return owner.claim_phase(selected or lookup(), SCOPE, **args)


def observe(owner, phase="CANDIDATE", sources=None, proposal=None, **changes):
    args = {"phase": phase, "sources": [SOURCE] if sources is None else sources,
            "proposal": proposal, "qualify_observation": lambda value: True, "guard": lambda: True}
    args.update(changes)
    return owner.retain_observation(lookup(), SCOPE, **args)


def test_no_evidence_is_unknown_and_read_has_no_writes(env):
    runtime, owner = env
    before = runtime.store.list_events()
    body = owner.read_status(lookup(), SCOPE, guard=lambda: True)
    assert body["disposition"] == "unknown" and body["receipt"] is None
    assert body["request_sha256"] is None and body["reason"] == "ORIGINAL_OPERATION_NOT_OBSERVED"
    assert runtime.store.list_events() == before
    assert runtime.jobs.list_jobs() == []


def test_original_intent_is_idempotent_and_changed_target_or_payload_conflicts(env):
    runtime, owner = env
    first = prepare(owner)
    assert prepare(owner) == first
    assert len(runtime.store.list_events()) == 1
    with pytest.raises(SourceOperationConflict):
        prepare(owner, request_sha256="8" * 64)
    with pytest.raises(SourceOperationConflict):
        prepare(owner, selected=lookup() | {"work_ref": "WS:FOREIGN"})
    body = owner.read_status(lookup(), "9" * 64, guard=lambda: True)
    assert body["receipt"] is None


def test_revocation_at_commit_rolls_back_intent(env):
    runtime, owner = env
    calls = []
    def guard():
        calls.append(True)
        return len(calls) < 3
    with pytest.raises(PermissionError):
        prepare(owner, guard=guard)
    assert runtime.store.list_events() == []


def test_one_phase_permit_under_concurrent_submit_and_restart_never_reissues(env):
    runtime, owner = env
    prepare(owner)
    with ThreadPoolExecutor(max_workers=2) as pool:
        permits = list(pool.map(lambda _: claim(owner), range(2)))
    assert sum(p is not None for p in permits) == 1
    permit = next(p for p in permits if p is not None)
    assert owner.validate_permit(permit, lookup(), SCOPE, guard=lambda: True)
    restarted = SourceOperationEvents(runtime.store)
    assert claim(restarted) is None
    assert not restarted.validate_permit(permit, lookup(), SCOPE, guard=lambda: True)
    assert len(runtime.store.list_events()) == 2 and runtime.jobs.list_jobs() == []


def test_claim_requires_actual_original_preview_and_distinct_current_binding(env):
    _, owner = env
    prepare(owner)
    with pytest.raises(SourceOperationConflict):
        claim(owner, preview_witness={"original_input": REF, "recipe_fingerprint_sha256": "0" * 64})
    with pytest.raises(PermissionError):
        claim(owner, permission_binding_digest="0" * 64)


def test_proposal_then_explicit_source_observation_then_exact_advance(env):
    runtime, owner = env
    prepare(owner)
    permit = claim(owner)
    proposal = observe(owner, sources=[], proposal=PR)
    assert proposal["kind"] == "PROPOSAL_OBSERVED"
    assert not owner.validate_permit(permit, lookup(), SCOPE, guard=lambda: True)
    count = len(runtime.store.list_events())
    for _ in range(2):
        status = owner.read_status(lookup(), SCOPE, guard=lambda: True)
        assert status["advance"] is None and status["disposition"] == "unknown"
    assert len(runtime.store.list_events()) == count
    source_receipt = observe(owner)
    assert observe(owner) == source_receipt
    current = owner.read_status(lookup(), SCOPE, guard=lambda: True)
    assert current["advance"] == {"phase_receipt_digest": source_receipt["receipt_sha256"]}
    with pytest.raises(SourceOperationConflict):
        claim(owner, phase_receipt_digest="0" * 64)
    phase2 = claim(owner, phase_receipt_digest=source_receipt["receipt_sha256"])
    assert phase2 is not None
    assert owner.read_status(lookup(), SCOPE, guard=lambda: True)["advance"] is None
    observe(owner, phase="ADOPTION")
    settled = owner.read_status(lookup(), SCOPE, guard=lambda: True)
    assert settled["disposition"] == "accepted" and settled["phase"] == "ADOPTION"
    assert not owner.validate_permit(phase2, lookup(), SCOPE, guard=lambda: True)
    assert runtime.jobs.list_jobs() == []


def test_observation_needs_prior_attempt_and_qualified_exact_source(env):
    runtime, owner = env
    prepare(owner)
    with pytest.raises(SourceOperationConflict):
        observe(owner)
    claim(owner)
    with pytest.raises(SourceOperationConflict):
        observe(owner, qualify_observation=lambda _: False)
    assert len(runtime.store.list_events()) == 2
    observe(owner)
    with pytest.raises(SourceOperationConflict):
        observe(owner, sources=[SOURCE | {"commit": "d" * 40}])


def test_no_private_input_is_in_runtime_events(env):
    runtime, owner = env
    prepare(owner)
    encoded = json.dumps([event.to_dict() for event in runtime.store.list_events()])
    assert "initial_snapshot" not in encoded and "rationale" not in encoded
    assert "payload_sha256" in encoded and "principal_scope" in encoded
    assert "workspace:" + SCOPE in encoded


def test_safe_knowledge_lookup_and_recipe_cas_metadata_survive_without_private_body(env):
    _, owner = env
    target = {"schema": "mastermind.workspace_source_operation_lookup.v1", "action": "add_project_file",
              "request_id": "mmos-project-file-add-" + "a" * 40, "work_ref": "WS:TEST"}
    binding = {k: target[k] for k in ("action", "request_id", "work_ref")} | {
        "source_commit": "a" * 40, "base_revision": "b" * 64,
        "request_sha256": "7" * 64, "expected_preference_revision": None}
    publication = {"expected_commit": "a" * 40, "branch": None,
        "postimages": [{"path": "agentos/project-files/WS-TEST/" + "c" * 64 + ".txt",
                        "content_sha256": "d" * 64, "expected_preimage_sha256": None},
                       {"path": "agentos/workstreams/WS-TEST.md", "content_sha256": "e" * 64,
                        "expected_preimage_sha256": "b" * 64}]}
    prepare(owner, selected=target, lookup_binding=binding, publication_binding=publication)
    retained = owner.original(target, SCOPE, guard=lambda: True)
    assert retained["lookup_binding"] == binding and retained["publication_binding"] == publication
    with pytest.raises(SourceOperationConflict):
        prepare(owner, selected=target, lookup_binding=binding | {"source_commit": "f" * 40},
                publication_binding=publication)
    with pytest.raises(SourceOperationConflict):
        prepare(owner, selected=target, lookup_binding=binding,
                publication_binding=publication | {"postimages": publication["postimages"][:1]})


def test_late_prior_phase_observation_cannot_regress_an_active_adoption(env):
    _, owner = env
    prepare(owner)
    claim(owner)
    settled = observe(owner)
    claim(owner, phase_receipt_digest=settled["receipt_sha256"])
    assert observe(owner) == settled  # exact prior observation read, no new event
    with pytest.raises(SourceOperationConflict):
        observe(owner, sources=[], proposal=PR)
    assert owner.read_status(lookup(), SCOPE, guard=lambda: True)["phase"] == "ADOPTION"


def test_only_actual_same_invocation_no_effect_can_settle_a_reserved_phase(env):
    runtime, owner = env
    prepare(owner)
    permit = claim(owner)
    with pytest.raises(SourceOperationConflict):
        owner.retain_no_effect(permit, lookup(), SCOPE, qualify_no_effect=lambda: False, guard=lambda: True)
    owner.retain_no_effect(permit, lookup(), SCOPE, qualify_no_effect=lambda: True, guard=lambda: True)
    body = owner.read_status(lookup(), SCOPE, guard=lambda: True)
    assert body["disposition"] == "refused" and body["reason"] == "NOT_DISPATCHED"
    assert body["receipt"] is None and body["request_sha256"] is None
    assert claim(owner) is None and len(runtime.store.list_events()) == 3


def test_prior_partial_publication_cannot_be_cleared_by_later_no_effect(env):
    _, owner = env
    prepare(owner)
    permit = claim(owner)
    candidate = observe(owner)
    next_permit = claim(owner, phase_receipt_digest=candidate["receipt_sha256"])
    with pytest.raises(SourceOperationConflict):
        owner.retain_no_effect(next_permit, lookup(), SCOPE, qualify_no_effect=lambda: True, guard=lambda: True)
    restarted = SourceOperationEvents(owner.store)
    with pytest.raises(SourceOperationConflict):
        restarted.retain_no_effect(permit, lookup(), SCOPE, qualify_no_effect=lambda: True, guard=lambda: True)
    assert owner.read_status(lookup(), SCOPE, guard=lambda: True)["disposition"] == "unknown"


def published_create(owner):
    selected = lookup("publish_project_proposal")
    prepare(owner, selected=selected, publication_binding={
        "expected_commit": "a" * 40, "branch": None,
        "postimages": [{"path": SOURCE["path"], "content_sha256": SOURCE["content_sha256"],
                        "expected_preimage_sha256": None}]})
    claim(owner, selected=selected)
    receipt = owner.retain_observation(selected, SCOPE, phase="PUBLICATION", sources=[SOURCE],
        proposal=None, qualify_observation=lambda _: True, guard=lambda: True)
    return selected, {"event_id": receipt["event_id"], "receipt_sha256": receipt["receipt_sha256"],
                      "source": dict(SOURCE), "guard": lambda: True}


def test_publication_read_uses_exact_committed_source_event_and_detaches(env):
    runtime, owner = env
    selected, args = published_create(owner)
    before = runtime.store.list_events()
    proof = owner.read_publication(selected, SCOPE, **args)
    assert proof["source"] == SOURCE and proof["request_sha256"] == "7" * 64
    assert proof["receipt"]["event_id"] == args["event_id"]
    assert set(proof) == {"schema", "selection", "owner_context", "source", "receipt",
                          "request_sha256", "recipe_fingerprint_sha256"}
    proof["receipt"]["sources"][0]["content_sha256"] = "0" * 64
    assert owner.read_publication(selected, SCOPE, **args)["source"] == SOURCE
    assert runtime.store.list_events() == before and runtime.jobs.list_jobs() == []


@pytest.mark.parametrize("change", [
    {"event_id": True}, {"event_id": 999999}, {"receipt_sha256": "0" * 64},
    {"source": SOURCE | {"commit": "f" * 40}},
    {"source": SOURCE | {"path": "agentos/workstreams/WS-FOREIGN.md"}},
    {"source": SOURCE | {"content_sha256": "0" * 64}},
])
def test_publication_read_rejects_changed_or_uncommitted_proof(env, change):
    runtime, owner = env
    selected, args = published_create(owner)
    before = runtime.store.list_events()
    with pytest.raises(SourceOperationConflict):
        owner.read_publication(selected, SCOPE, **(args | change))
    assert runtime.store.list_events() == before


def test_publication_read_denies_foreign_identity_candidate_and_revocation(env):
    runtime, owner = env
    selected, args = published_create(owner)
    for other, scope in [(selected, "9" * 64), (selected | {"work_ref": "WS:FOREIGN"}, SCOPE),
                         (lookup(), SCOPE)]:
        with pytest.raises(SourceOperationConflict):
            owner.read_publication(other, scope, **args)
    calls = []
    def revoked():
        calls.append(True)
        return len(calls) < 2
    before = runtime.store.list_events()
    with pytest.raises(PermissionError):
        owner.read_publication(selected, SCOPE, **(args | {"guard": revoked}))
    assert runtime.store.list_events() == before


def test_later_adoption_cas_binding_is_committed_with_unique_phase_before_effect(env):
    runtime, owner = env
    prepare(owner); claim(owner)
    prior = observe(owner)
    binding = {"expected_commit": SOURCE["commit"], "branch": None, "postimages": [
        {"path": "agentos/workstreams/WS-TEST.md", "content_sha256": "d" * 64,
         "expected_preimage_sha256": "e" * 64},
        {"path": "agentos/decisions/DEC-TEST.md", "content_sha256": "f" * 64,
         "expected_preimage_sha256": None}]}
    assert owner.publication_binding(lookup(), SCOPE, phase="ADOPTION", guard=lambda: True) is None
    permit = claim(owner, phase_receipt_digest=prior["receipt_sha256"], phase_publication_binding=binding)
    assert owner.validate_permit(permit, lookup(), SCOPE, guard=lambda: True)
    retained = owner.publication_binding(lookup(), SCOPE, phase="ADOPTION", guard=lambda: True)
    assert retained == binding
    retained["postimages"].clear()
    assert owner.publication_binding(lookup(), SCOPE, phase="ADOPTION", guard=lambda: True) == binding
    # Recovery sees the existing reservation, never a replacement recipe/permit.
    assert claim(owner, phase_receipt_digest=prior["receipt_sha256"], phase_publication_binding=binding) is None
    with pytest.raises(SourceOperationConflict):
        claim(owner, phase_receipt_digest=prior["receipt_sha256"],
              phase_publication_binding=binding | {"expected_commit": "b" * 40})
    assert runtime.store.list_events()[-1].payload["publication_binding"] == binding
    assert runtime.jobs.list_jobs() == []


def test_plan_proposal_uses_distinct_original_id_and_one_publication_phase(env):
    runtime, owner = env
    selected = {"schema":"mastermind.workspace_source_operation_lookup.v1",
        "action":"publish_project_plan_proposal", "request_id":"mmos-project-plan-proposal-"+"a"*40,
        "work_ref":"WS:TEST"}
    prepare(owner, selected=selected)
    permit = claim(owner, selected=selected)
    assert permit.phase == "PUBLICATION"
    owner.retain_observation(selected, SCOPE, phase="PUBLICATION", sources=[SOURCE], proposal=None,
        qualify_observation=lambda value: True, guard=lambda: True)
    assert owner.read_status(selected,SCOPE,guard=lambda:True)["disposition"] == "accepted"
    assert runtime.jobs.list_jobs() == []
    with pytest.raises(ValueError, match="invalid_source_operation"):
        prepare(owner,selected=selected | {"request_id":"mmos-project-create-"+"a"*40})
