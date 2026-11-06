"""Real temporary Runtime Events, actual verified principals and sealed v4 grants.

The observation/no-effect ``qualify_observation``/``qualify_no_effect`` callables
below are explicitly fixture-only stand-ins for the parent's trusted publisher
qualification; every Git, compiler, HTTP and host join remains parent-owned and
no live effect, credential or current Macro read exists anywhere in this file.
"""
import hashlib
import inspect
import threading
from types import SimpleNamespace

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.workspace_source_operations import (SourceOperationEvents,
                                                      SourceOperationConflict)
from integrations.mastermind_workspace_app.knowledge_publisher_events import (
    KNOWLEDGE_METADATA_SCHEMA, KnowledgeOperationConflict, KnowledgePublisherEvents,
)
from integrations.mastermind_workspace_app.owner_context import workspace_owner_context
from integrations.mastermind_workspace_app.source_operation_context import (
    WorkspaceSourceOperationContextFactory,
)
from tests.test_workspace_member_bindings import principal
from tests.test_workspace_project_authoring_grant import project_bindings, verified

FP = "2" * 64
STAMP = "3" * 64
REQUEST = "7" * 64
COMMIT = "a" * 40
BASE = "b" * 64
PUB_COMMIT = "d" * 40
OTHER_COMMIT = "9" * 40
BRANCH = "mmos/knowledge-" + "e" * 40
WS_PATH = "agentos/workstreams/WS-TEST.md"
WS_SHA = "e" * 64
FILE_PATH = "agentos/project-files/WS-TEST/" + "c" * 64 + ".txt"
FILE_SHA = "f" * 64
DECISION_PATH = "agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-TEST.md"
REF = {"schema": "mastermind.terminal_original_input_reference.v1",
       "input_ref": "terminal-input:" + "4" * 64,
       "artifact_sha256": "5" * 64, "payload_sha256": "6" * 64}
PR = {"number": 11, "url": "https://github.com/mastermindx-market-intelligence/macro/pull/11",
      "head_commit": "c" * 40, "head_branch": BRANCH}
FILE_GRANT = {"work_ref": "WS:TEST",
              "permission_digest": hashlib.sha256(b"project_file_add").hexdigest()}
PREF_GRANT = {"work_ref": "WS:TEST",
              "permission_digest": hashlib.sha256(b"project_preference_set").hexdigest()}
SECOND_MEMBER_GRANT = {"work_ref": "WS:TEST",
                       "permission_digest": hashlib.sha256(b"second-member-file-add").hexdigest()}


def lookup7(action="add_project_file", suffix="a" * 40, request=REQUEST, work_ref="WS:TEST",
            commit=COMMIT, base=BASE, preference=None):
    prefix = ("mmos-project-file-add-" if action == "add_project_file"
              else "mmos-project-preference-set-")
    return {"action": action, "request_id": prefix + suffix, "work_ref": work_ref,
            "source_commit": commit, "base_revision": base, "request_sha256": request,
            "expected_preference_revision": preference}


def lookup3(identity):
    return {"schema": "mastermind.workspace_source_operation_lookup.v1",
            "action": identity["action"], "request_id": identity["request_id"],
            "work_ref": identity["work_ref"]}


def postimages():
    return [{"path": WS_PATH, "content_sha256": WS_SHA, "expected_preimage_sha256": BASE},
            {"path": FILE_PATH, "content_sha256": FILE_SHA, "expected_preimage_sha256": None}]


def preference_images():
    return [{"path": WS_PATH, "content_sha256": WS_SHA, "expected_preimage_sha256": BASE},
            {"path": DECISION_PATH, "content_sha256": "1" * 64, "expected_preimage_sha256": None}]


def granted(action, field_grant, member="member-0"):
    """Actual sealed policy plus one explicit scoped v4 grant for one member."""
    policy, source = project_bindings()
    field = "project_file_add" if action == "add_project_file" else "project_preference_set"
    source["profiles"][member][field] = field_grant
    who = verified(policy, principal(source, member))
    contexts = WorkspaceSourceOperationContextFactory(policy=policy, load_bindings=lambda: source)
    return policy, source, who, contexts


def operation(events, scope, identity, branch=BRANCH, images=None):
    """Safe original binding committed before any preview or claim."""
    events.prepare(lookup3(identity), scope, request_sha256=REQUEST,
                   recipe_fingerprint_sha256=FP, original_input=REF,
                   permission_binding_digest=STAMP, guard=lambda: True,
                   lookup_binding=dict(identity),
                   publication_binding={"expected_commit": COMMIT, "branch": branch,
                                        "postimages": images if images is not None else postimages()})


def claim(events, scope, identity):
    return events.claim_phase(lookup3(identity), scope, permission_binding_digest=STAMP,
                              preview_witness={"original_input": REF,
                                               "recipe_fingerprint_sha256": FP},
                              guard=lambda: True)


def observe(events, scope, identity, *, sources=None, proposal=None):
    """Fixture-only inert qualification, exactly as documented in the module docstring."""
    return events.retain_observation(lookup3(identity), scope, phase="PUBLICATION",
                                     sources=[] if sources is None else sources,
                                     proposal=proposal,
                                     qualify_observation=lambda value: True,
                                     guard=lambda: True)


def source_pair(commit=PUB_COMMIT, second_commit=None):
    return [{"repository": "macro", "commit": commit, "path": WS_PATH, "content_sha256": WS_SHA},
            {"repository": "macro", "commit": second_commit or commit, "path": FILE_PATH,
             "content_sha256": FILE_SHA}]


def make_world(tmp_path, action="add_project_file", grant=FILE_GRANT, name="runtime", images=None):
    policy, source, who, contexts = granted(action, grant)
    runtime = Runtime.at(tmp_path / name)
    events = SourceOperationEvents(runtime.store)
    scope = workspace_owner_context(who)["principal_scope"]
    identity = lookup7(action)
    operation(events, scope, identity, images=images)
    adapter = KnowledgePublisherEvents(events=events, contexts=contexts)
    return SimpleNamespace(runtime=runtime, events=events, adapter=adapter, policy=policy,
                           source=source, who=who, contexts=contexts, scope=scope,
                           identity=identity)


@pytest.fixture
def world(tmp_path):
    return make_world(tmp_path)


def test_retained_metadata_is_exact_and_unknown_or_absent_states_stay_read_only(world):
    metadata = world.adapter.load_original_operation(world.who, world.identity)
    assert set(metadata) == {"schema", "identity", "recipe_fingerprint_sha256",
                             "permission_binding_digest", "phase", "expected_commit",
                             "postimages", "branch", "publication", "proposal"}
    assert metadata["schema"] == KNOWLEDGE_METADATA_SCHEMA
    assert metadata["identity"] == dict(world.identity) | {"principal_scope": world.scope}
    assert metadata["recipe_fingerprint_sha256"] == FP
    assert metadata["permission_binding_digest"] == STAMP  # original stamp, never current
    assert metadata["phase"] == "UNKNOWN"  # INTENT alone is never claim evidence
    assert metadata["expected_commit"] == COMMIT and metadata["branch"] == BRANCH
    assert metadata["postimages"] == postimages()
    assert metadata["publication"] is None and metadata["proposal"] is None
    assert world.adapter.load_original_operation(world.who, world.identity) == metadata
    # only actual absence returns None: a different request id with no Events at all
    assert world.adapter.load_original_operation(world.who, lookup7(suffix="b" * 40)) is None
    # read-only: loads, stamps and scopes never append an Event or a Job
    assert world.adapter.principal_scope(world.who) == world.scope
    before = world.runtime.store.list_events()
    world.adapter.knowledge_permission_stamp(world.who, "add_project_file", "WS:TEST")
    world.adapter.load_original_operation(world.who, world.identity)
    assert world.runtime.store.list_events() == before
    assert world.runtime.jobs.list_jobs() == []


def test_claimed_needs_a_live_lease_and_revokes_on_exit_and_reuse(world):
    permit = claim(world.events, world.scope, world.identity)
    # the committed PHASE_ATTEMPTED label alone never yields CLAIMED
    assert world.adapter.load_original_operation(world.who, world.identity)["phase"] == "UNKNOWN"
    assert world.adapter.validate_original_claim(world.who, world.identity, permit, {}) is False
    with world.adapter.bind_claim(world.who, world.identity, permit) as claimed:
        assert set(claimed) == {"schema", "identity", "recipe_fingerprint_sha256",
                                "permission_binding_digest", "phase", "expected_commit",
                                "postimages", "branch", "publication", "proposal"}
        assert claimed["phase"] == "CLAIMED"
        inside = world.adapter.load_original_operation(world.who, world.identity)
        assert inside == claimed  # stable snapshot within one live claim
        assert world.adapter.validate_original_claim(world.who, world.identity, permit, inside) is True
    assert world.adapter.load_original_operation(world.who, world.identity)["phase"] == "UNKNOWN"
    assert world.adapter.validate_original_claim(world.who, world.identity, permit, claimed) is False
    with pytest.raises(KnowledgeOperationConflict):
        with world.adapter.bind_claim(world.who, world.identity, permit):
            pass  # consumed before the first yield: exactly one invocation per permit


def test_exception_inside_claim_revokes_and_can_never_reuse_the_permit(world):
    permit = claim(world.events, world.scope, world.identity)
    with pytest.raises(RuntimeError):
        with world.adapter.bind_claim(world.who, world.identity, permit) as claimed:
            assert claimed["phase"] == "CLAIMED"
            raise RuntimeError("fixture failure inside the claim")
    assert world.adapter.load_original_operation(world.who, world.identity)["phase"] == "UNKNOWN"
    with pytest.raises(KnowledgeOperationConflict):
        with world.adapter.bind_claim(world.who, world.identity, permit):
            pass


def test_nested_and_cross_operation_leases_are_refused(world):
    pref = lookup7("set_project_communication_preference")
    world.source["profiles"]["member-0"]["project_preference_set"] = PREF_GRANT
    operation(world.events, world.scope, pref, images=preference_images())
    pref_permit = claim(world.events, world.scope, pref)
    permit = claim(world.events, world.scope, world.identity)
    with world.adapter.bind_claim(world.who, world.identity, permit):
        with pytest.raises(KnowledgeOperationConflict):
            with world.adapter.bind_claim(world.who, world.identity, permit):
                pass  # already consumed by the live outer invocation
        with pytest.raises(KnowledgeOperationConflict):
            with world.adapter.bind_claim(world.who, pref, pref_permit):
                pass  # one active lease per context, never a second permit
    # the refused pref bind never yielded, so its permit is still bindable once
    with world.adapter.bind_claim(world.who, pref, pref_permit) as claimed:
        assert claimed["phase"] == "CLAIMED"
    with pytest.raises(KnowledgeOperationConflict):
        with world.adapter.bind_claim(world.who, pref, pref_permit):
            pass


def test_later_observation_events_revoke_the_live_permit_and_map_the_stronger_proof(world):
    permit = claim(world.events, world.scope, world.identity)
    with world.adapter.bind_claim(world.who, world.identity, permit) as claimed:
        assert claimed["phase"] == "CLAIMED"
        observe(world.events, world.scope, world.identity, proposal=PR)
        current = world.adapter.load_original_operation(world.who, world.identity)
        assert current["phase"] == "PROPOSAL_PUBLISHED" and current["proposal"] == PR
        assert current["publication"] is None
        assert world.adapter.validate_original_claim(world.who, world.identity, permit, claimed) is False
        assert not world.events.validate_permit(permit, lookup3(world.identity), world.scope,
                                                guard=lambda: True)
        observe(world.events, world.scope, world.identity, sources=source_pair())
        settled = world.adapter.load_original_operation(world.who, world.identity)
        assert settled["phase"] == "SOURCE_PUBLISHED"
        assert settled["publication"] == {"repository": "mastermindx-market-intelligence/macro",
                                          "commit": PUB_COMMIT,
                                          "postimages": [{"path": WS_PATH, "content_sha256": WS_SHA},
                                                         {"path": FILE_PATH, "content_sha256": FILE_SHA}]}
        # the earlier proposal receipt is no longer the strongest retained proof
        # the allowed Events reads surface, so it maps as null, never as claim
        assert settled["proposal"] is None
        assert world.adapter.validate_original_claim(world.who, world.identity, permit, settled) is False
    assert world.adapter.load_original_operation(world.who, world.identity)["phase"] == "SOURCE_PUBLISHED"


def test_source_proof_needs_both_postimages_in_one_same_macro_commit(tmp_path):
    cases = [("partial", [source_pair()[0]]),
             ("split-commit", source_pair(PUB_COMMIT, second_commit=OTHER_COMMIT)),
             ("foreign-path", [{"repository": "macro", "commit": PUB_COMMIT,
                                "path": "agentos/workstreams/WS-FOREIGN.md",
                                "content_sha256": WS_SHA}] + source_pair()[1:])]
    for label, sources in cases:
        case_world = make_world(tmp_path, name="runtime-" + label)
        permit = claim(case_world.events, case_world.scope, case_world.identity)
        with case_world.adapter.bind_claim(case_world.who, case_world.identity, permit):
            observe(case_world.events, case_world.scope, case_world.identity, sources=sources)
            with pytest.raises(KnowledgeOperationConflict):
                case_world.adapter.load_original_operation(case_world.who, case_world.identity)
        # the mismatched retained proof stays fail-closed outside the lease too
        with pytest.raises(KnowledgeOperationConflict):
            case_world.adapter.load_original_operation(case_world.who, case_world.identity)
    exact = make_world(tmp_path, name="runtime-exact")
    permit = claim(exact.events, exact.scope, exact.identity)
    with exact.adapter.bind_claim(exact.who, exact.identity, permit):
        observe(exact.events, exact.scope, exact.identity, sources=source_pair())
        settled = exact.adapter.load_original_operation(exact.who, exact.identity)
        assert settled["phase"] == "SOURCE_PUBLISHED"
        assert settled["publication"]["commit"] == PUB_COMMIT


def test_retained_source_proof_survives_source_unavailability_with_zero_private_reads(tmp_path):
    proof_world = make_world(tmp_path)
    permit = claim(proof_world.events, proof_world.scope, proof_world.identity)
    with proof_world.adapter.bind_claim(proof_world.who, proof_world.identity, permit):
        observe(proof_world.events, proof_world.scope, proof_world.identity, sources=source_pair())
    metadata = proof_world.adapter.load_original_operation(proof_world.who, proof_world.identity)
    assert metadata["phase"] == "SOURCE_PUBLISHED"
    before = proof_world.runtime.store.list_events()
    assert proof_world.adapter.load_original_operation(proof_world.who, proof_world.identity) == metadata
    assert proof_world.runtime.store.list_events() == before
    assert proof_world.runtime.jobs.list_jobs() == []
    # the adapter owns no compiler, artifact body, current-Macro or provider seam
    assert set(inspect.signature(KnowledgePublisherEvents.__init__).parameters) == {
        "self", "events", "contexts"}
    with pytest.raises(TypeError):
        proof_world.adapter.load_original_operation(proof_world.who, proof_world.identity,
                                                    recipe={"body": True})


def test_same_invocation_no_effect_maps_not_dispatched_inside_a_live_claim(world):
    permit = claim(world.events, world.scope, world.identity)
    with pytest.raises(SourceOperationConflict):
        world.events.retain_no_effect(permit, lookup3(world.identity), world.scope,
                                      qualify_no_effect=lambda: False, guard=lambda: True)
    with world.adapter.bind_claim(world.who, world.identity, permit) as claimed:
        assert claimed["phase"] == "CLAIMED"
        world.events.retain_no_effect(permit, lookup3(world.identity), world.scope,
                                      qualify_no_effect=lambda: True, guard=lambda: True)
        metadata = world.adapter.load_original_operation(world.who, world.identity)
        assert metadata["phase"] == "NOT_DISPATCHED"
        assert metadata["publication"] is None and metadata["proposal"] is None
        assert world.adapter.validate_original_claim(world.who, world.identity, permit, claimed) is False
    with pytest.raises(KnowledgeOperationConflict):
        with world.adapter.bind_claim(world.who, world.identity, permit):
            pass


def test_cross_principal_action_work_and_lookup_shapes_fail_closed(world):
    world.source["profiles"]["member-1"]["project_file_add"] = SECOND_MEMBER_GRANT
    other = verified(world.policy, principal(world.source, "member-1"))
    assert world.adapter.authorize_knowledge(other, "add_project_file", "WS:TEST") is True
    assert world.adapter.load_original_operation(other, world.identity) is None
    permit = claim(world.events, world.scope, world.identity)
    with world.adapter.bind_claim(world.who, world.identity, permit) as claimed:
        assert claimed["phase"] == "CLAIMED"
    # a refused cross-principal bind burns its permit, so it uses its own aggregate
    other_identity = lookup7(suffix="b" * 40)
    operation(world.events, world.scope, other_identity)
    other_permit = claim(world.events, world.scope, other_identity)
    with pytest.raises(KnowledgeOperationConflict):
        with world.adapter.bind_claim(other, other_identity, other_permit):
            pass  # the permit aggregates exactly one principal scope
    pref = lookup7("set_project_communication_preference")
    # no sibling fallback: without the preference grant even reading that action
    # shape is denied, while the exact grant stays scoped to one action
    with pytest.raises(PermissionError):
        world.adapter.load_original_operation(world.who, pref)
    world.source["profiles"]["member-0"]["project_preference_set"] = PREF_GRANT
    assert world.adapter.load_original_operation(world.who, pref) is None
    world.source["profiles"]["member-0"]["project_preference_set"] = None
    # a grant rotated to a different work_ref still cannot retarget the retained
    # original: the actual Events owner pins the exact identity per row
    world.source["profiles"]["member-0"]["project_file_add"] = dict(FILE_GRANT, work_ref="WS:OTHER")
    with pytest.raises(SourceOperationConflict):
        world.adapter.load_original_operation(world.who, dict(world.identity, work_ref="WS:OTHER"))
    world.source["profiles"]["member-0"]["project_file_add"] = FILE_GRANT
    with pytest.raises(KnowledgeOperationConflict):
        world.adapter.load_original_operation(world.who, dict(world.identity, request_sha256="9" * 64))
    foreign = {"action": "publish_project_proposal", "request_id": "mmos-project-create-" + "a" * 40,
               "work_ref": "WS:TEST", "source_commit": COMMIT, "base_revision": BASE,
               "request_sha256": REQUEST, "expected_preference_revision": None}
    with pytest.raises(KnowledgeOperationConflict):
        world.adapter.load_original_operation(world.who, foreign)
    assert world.adapter.authorize_knowledge(world.who, "publish_project_proposal", None) is False
    assert world.adapter.authorize_knowledge(world.who, "ADOPT_PLAN", "WS:TEST") is False
    with pytest.raises(KnowledgeOperationConflict):
        world.adapter.knowledge_permission_stamp(world.who, "publish_project_proposal", None)


def test_preference_operations_map_proposal_branches_exactly(tmp_path):
    pref_world = make_world(tmp_path, action="set_project_communication_preference",
                            grant=PREF_GRANT, name="runtime-preference",
                            images=preference_images())
    identity = lookup7("set_project_communication_preference")
    assert pref_world.adapter.load_original_operation(pref_world.who, identity)["phase"] == "UNKNOWN"
    permit = claim(pref_world.events, pref_world.scope, identity)
    with pref_world.adapter.bind_claim(pref_world.who, identity, permit):
        observe(pref_world.events, pref_world.scope, identity, proposal=PR)
        assert (pref_world.adapter.load_original_operation(pref_world.who, identity)
                ["phase"] == "PROPOSAL_PUBLISHED")
    drifted = PR | {"head_branch": "other-proposal-branch"}
    drift_world = make_world(tmp_path, action="set_project_communication_preference",
                             grant=PREF_GRANT, name="runtime-drift", images=preference_images())
    drift_permit = claim(drift_world.events, drift_world.scope, identity)
    with drift_world.adapter.bind_claim(drift_world.who, identity, drift_permit):
        observe(drift_world.events, drift_world.scope, identity, proposal=drifted)
        with pytest.raises(KnowledgeOperationConflict):
            drift_world.adapter.load_original_operation(drift_world.who, identity)
    # without a retained planned branch no proposal can be verified as this operation's
    branchless = make_world(tmp_path, action="set_project_communication_preference",
                            grant=PREF_GRANT, name="runtime-branchless",
                            images=preference_images())
    branchless_identity = lookup7("set_project_communication_preference", suffix="b" * 40)
    operation(branchless.events, branchless.scope, branchless_identity, branch=None,
              images=preference_images())
    branchless_permit = claim(branchless.events, branchless.scope, branchless_identity)
    with branchless.adapter.bind_claim(branchless.who, branchless_identity, branchless_permit):
        observe(branchless.events, branchless.scope, branchless_identity, proposal=PR)
        with pytest.raises(KnowledgeOperationConflict):
            branchless.adapter.load_original_operation(branchless.who, branchless_identity)


def test_grant_rotation_keeps_the_original_stamp_and_revocation_stops_even_reads(world):
    permit = claim(world.events, world.scope, world.identity)
    with world.adapter.bind_claim(world.who, world.identity, permit) as claimed:
        assert claimed["permission_binding_digest"] == STAMP
        world.source["profiles"]["member-0"]["project_file_add"] = dict(
            FILE_GRANT, permission_digest="9" * 64)
        assert world.adapter.authorize_knowledge(world.who, "add_project_file", "WS:TEST") is True
        assert (world.adapter.knowledge_permission_stamp(world.who, "add_project_file", "WS:TEST")
                != STAMP)
        rotated = world.adapter.load_original_operation(world.who, world.identity)
        assert rotated["permission_binding_digest"] == STAMP  # never the current stamp
        assert world.adapter.validate_original_claim(world.who, world.identity, permit, rotated) is True
        world.source["profiles"]["member-0"]["project_file_add"] = None
        with pytest.raises(PermissionError):
            world.adapter.load_original_operation(world.who, world.identity)
        assert world.adapter.authorize_knowledge(world.who, "add_project_file", "WS:TEST") is False
        with pytest.raises(PermissionError):
            world.adapter.knowledge_permission_stamp(world.who, "add_project_file", "WS:TEST")
        assert world.adapter.validate_original_claim(world.who, world.identity, permit, rotated) is False


def test_expired_verified_principal_never_binds_reads_or_stamps(tmp_path):
    policy, source, who, _ = granted("add_project_file", FILE_GRANT)
    runtime = Runtime.at(tmp_path / "runtime-expired")
    events = SourceOperationEvents(runtime.store)
    scope = workspace_owner_context(who)["principal_scope"]
    identity = lookup7()
    operation(events, scope, identity)
    expired = WorkspaceSourceOperationContextFactory(policy=policy, load_bindings=lambda: source,
                                                     now=lambda: who.expires_at)
    adapter = KnowledgePublisherEvents(events=events, contexts=expired)
    assert adapter.authorize_knowledge(who, "add_project_file", "WS:TEST") is False
    with pytest.raises(PermissionError):
        adapter.load_original_operation(who, identity)
    with pytest.raises(PermissionError):
        adapter.knowledge_permission_stamp(who, "add_project_file", "WS:TEST")
    permit = claim(events, scope, identity)
    with pytest.raises(PermissionError):
        with adapter.bind_claim(who, identity, permit):
            pass  # the fresh bound scope check expires before any Events read
    assert len(runtime.store.list_events()) == 2  # the retained originals stay intact


def test_restart_and_foreign_claim_shapes_never_recreate_a_claim(world):
    permit = claim(world.events, world.scope, world.identity)
    restarted = KnowledgePublisherEvents(events=SourceOperationEvents(world.runtime.store),
                                         contexts=world.contexts)
    with pytest.raises(KnowledgeOperationConflict):
        with restarted.bind_claim(world.who, world.identity, permit):
            pass  # a restarted Events owner never recreates or validates the permit
    # the original owner instance still binds the real permit exactly once
    with world.adapter.bind_claim(world.who, world.identity, permit) as claimed:
        assert claimed["phase"] == "CLAIMED"
    assert world.adapter.validate_original_claim(world.who, world.identity, True, {}) is False
    assert world.adapter.validate_original_claim(world.who, world.identity, {"event_id": 2}, {}) is False
    assert world.adapter.validate_original_claim(world.who, world.identity, permit, None) is False
    assert world.adapter.validate_original_claim(world.who, "not-a-lookup", permit, {}) is False


def test_constructor_requires_exact_actual_owners_and_closed_error_text(world):
    with pytest.raises(KnowledgeOperationConflict):
        KnowledgePublisherEvents(events={}, contexts=world.contexts)
    with pytest.raises(KnowledgeOperationConflict):
        KnowledgePublisherEvents(events=world.events, contexts={"policy": True})
    assert str(KnowledgeOperationConflict()) == "KNOWLEDGE_OPERATION_CONFLICT"
    policy, source, _, _ = granted("add_project_file", FILE_GRANT)
    plain = verified(policy, principal(source, "member-1"))  # enrolled, but no knowledge grant
    with pytest.raises(PermissionError) as excinfo:
        world.adapter.load_original_operation(plain, world.identity)
    assert str(excinfo.value) == "SOURCE_OPERATION_UNAUTHORIZED"


def test_concurrent_threads_never_share_one_active_permit(tmp_path):
    world = make_world(tmp_path, name="runtime-threads")
    permit = claim(world.events, world.scope, world.identity)
    barrier = threading.Barrier(2)
    outcome = {}

    def worker():
        barrier.wait()
        try:
            with world.adapter.bind_claim(world.who, world.identity, permit) as claimed:
                outcome["winner"] = claimed["phase"]
        except KnowledgeOperationConflict:
            outcome["loser"] = True

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcome.get("winner") == "CLAIMED" and outcome.get("loser") is True
    # a lease in one thread is invisible to loads in another thread
    other = lookup7(suffix="c" * 40)
    operation(world.events, world.scope, other, images=preference_images())
    other_permit = claim(world.events, world.scope, other)
    started, release = threading.Event(), threading.Event()

    def holder():
        with world.adapter.bind_claim(world.who, other, other_permit):
            started.set()
            release.wait(10)

    thread = threading.Thread(target=holder)
    thread.start()
    assert started.wait(10)
    assert world.adapter.load_original_operation(world.who, other)["phase"] == "UNKNOWN"
    third = lookup7(suffix="e" * 40)
    operation(world.events, world.scope, third)
    third_permit = claim(world.events, world.scope, third)
    with world.adapter.bind_claim(world.who, third, third_permit) as claimed:
        assert claimed["phase"] == "CLAIMED"  # concurrent distinct permits are independent
    release.set()
    thread.join()
    assert world.runtime.jobs.list_jobs() == []
