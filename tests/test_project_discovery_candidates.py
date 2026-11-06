"""Real temporary Runtime Events; no provider, Git, installed or live effects."""
import dataclasses

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.project_discovery_candidates import (
    DOCUMENT_SCHEMA,
    UNAVAILABLE,
    CreatedProjectCandidates,
    capture_created_project_candidates,
)
from control_plane.workspace_source_operations import AGGREGATE, SCHEMA
from tests.test_workspace_source_operations import (
    claim,
    env,
    lookup,
    observe,
    prepare,
    FP,
    REF,
    SCOPE,
    SOURCE,
    STAMP,
)

PUBLICATION = "PUBLICATION"


def create_lookup(key="TEST", req="a" * 40):
    return {"schema": "mastermind.workspace_source_operation_lookup.v1",
            "action": "publish_project_proposal",
            "request_id": "mmos-project-create-" + req, "work_ref": "WS:" + key}


def _binding(key):
    return {"expected_commit": "a" * 40, "branch": None,
            "postimages": [{"path": "agentos/workstreams/WS-" + key + ".md",
                            "content_sha256": "b" * 64, "expected_preimage_sha256": None}]}


def _source(key):
    return [{"repository": "macro", "commit": "b" * 40,
             "path": "agentos/workstreams/WS-" + key + ".md",
             "content_sha256": "c" * 64}]


def publish(owner, key="TEST", req="a" * 40):
    """Retain one real PUBLICATION CREATE source event under the fixture scope."""
    selected = create_lookup(key, req)
    prepare(owner, selected, publication_binding=_binding(key))
    claim(owner, selected)
    receipt = owner.retain_observation(selected, SCOPE, phase=PUBLICATION,
                                       sources=_source(key), proposal=None,
                                       qualify_observation=lambda value: True,
                                       guard=lambda: True)
    return selected, receipt


def publish_as(owner, scope, key="TEST", req="a" * 40):
    """The same real retention under an explicit principal scope."""
    selected = create_lookup(key, req)
    owner.prepare(selected, scope, request_sha256="7" * 64,
                  recipe_fingerprint_sha256=FP, original_input=REF,
                  permission_binding_digest=STAMP, guard=lambda: True,
                  publication_binding=_binding(key))
    owner.claim_phase(selected, scope, permission_binding_digest=STAMP,
                      preview_witness={"original_input": REF,
                                       "recipe_fingerprint_sha256": FP}, guard=lambda: True)
    receipt = owner.retain_observation(selected, scope, phase=PUBLICATION,
                                       sources=_source(key), proposal=None,
                                       qualify_observation=lambda value: True,
                                       guard=lambda: True)
    return selected, receipt


def hostile_identity(req="d" * 40, key="HOSTILE"):
    return {"action": "publish_project_proposal",
            "request_id": "mmos-project-create-" + req,
            "work_ref": "WS:" + key, "principal_scope": SCOPE}


def hostile_payload(identity=None, **changes):
    payload = {"schema": SCHEMA, "identity": identity or hostile_identity(),
               "kind": "SOURCE_OBSERVED", "phase": PUBLICATION,
               "request_sha256": "7" * 64, "recipe_fingerprint_sha256": FP}
    payload.update(changes)
    return payload


def append_raw(runtime, payload):
    """Insert a row whose data alone matches every selector predicate."""
    with runtime.store.transaction() as connection:
        runtime.store.append_event(connection, aggregate_type=AGGREGATE,
                                   aggregate_id="f" * 64,
                                   event_type="PROJECT_SOURCE_SOURCE_OBSERVED",
                                   actor="workspace:" + SCOPE, payload=payload)


def capture(owner, scope=SCOPE, guard=None):
    return capture_created_project_candidates(owner, scope,
                                              guard=guard or (lambda: True))


def unavailable(error):
    return type(error) is ValueError and str(error) == UNAVAILABLE


def test_empty_scope_selects_nothing(env):
    runtime, owner = env
    candidates = capture(owner)
    assert candidates.document() == {"schema": DOCUMENT_SCHEMA, "lookups": [],
                                     "has_more": False, "high_water": 0}
    assert candidates.check(SCOPE) is True
    assert runtime.jobs.list_jobs() == []


def test_single_published_create_is_selected_with_its_event(env):
    runtime, owner = env
    selected, receipt = publish(owner)
    candidates = capture(owner)
    assert candidates.document() == {"schema": DOCUMENT_SCHEMA, "lookups": [selected],
                                     "has_more": False,
                                     "high_water": receipt["event_id"]}
    assert candidates.check(SCOPE) is True


def test_multiple_projects_keep_latest_first_order(env):
    runtime, owner = env
    published = [publish(owner, key="W%d" % number, req="%040x" % number)
                 for number in (1, 2, 3)]
    document = capture(owner).document()
    assert document["lookups"] == [selected for selected, _ in reversed(published)]
    assert document["high_water"] == published[-1][1]["event_id"]
    assert document["has_more"] is False


def test_foreign_scope_action_and_phase_are_excluded(env):
    runtime, owner = env
    selected, _ = publish(owner)
    publish_as(owner, "9" * 64)
    prepare(owner)
    claim(owner)
    observe(owner)  # ADOPT_PLAN CANDIDATE source observation
    append_raw(runtime, hostile_payload(phase="ADOPTION"))
    assert capture(owner).document()["lookups"] == [selected]


def test_duplicate_work_ref_keeps_the_latest_selector(env):
    runtime, owner = env
    older = publish(owner, key="DUP", req="%040x" % 1)
    newer = publish(owner, key="DUP", req="%040x" % 2)
    document = capture(owner).document()
    assert document["lookups"] == [newer[0]]
    assert document["high_water"] == newer[1]["event_id"]


def test_ninth_distinct_work_sets_has_more_and_selects_latest_eight(env):
    runtime, owner = env
    published = [publish(owner, key="W%d" % number, req="%040x" % number)
                 for number in range(1, 10)]
    document = capture(owner).document()
    assert document["lookups"] == [selected for selected, _ in reversed(published[1:])]
    assert document["has_more"] is True
    assert document["high_water"] == published[-1][1]["event_id"]


def test_more_than_64_raw_rows_set_has_more_without_new_selectors(env):
    runtime, owner = env
    for number in range(1, 66):
        publish(owner, req="%040x" % number)
    document = capture(owner).document()
    assert document["lookups"] == [create_lookup(req="%040x" % 65)]
    assert document["has_more"] is True


def test_oversized_row_payload_is_unavailable(env):
    runtime, owner = env
    publish(owner)
    append_raw(runtime, hostile_payload(padding="x" * 70000))
    with pytest.raises(ValueError) as caught:
        capture(owner)
    assert unavailable(caught.value)


def test_selected_metadata_budget_is_unavailable(env):
    runtime, owner = env
    for number in range(5):
        append_raw(runtime, hostile_payload(req="%040x" % (100 + number),
                                            key="BULK%d" % number,
                                            padding="x" * 55000))
    with pytest.raises(ValueError) as caught:
        capture(owner)
    assert unavailable(caught.value)


def test_malformed_owned_match_is_rejected_not_dropped(env):
    runtime, owner = env
    publish(owner)
    append_raw(runtime, hostile_payload(
        identity=hostile_identity() | {"surprise": "x"}))
    with pytest.raises(ValueError) as caught:
        capture(owner)
    assert unavailable(caught.value)
    append_raw(runtime, hostile_payload(
        identity=hostile_identity(req="not-hex-at-all")))
    with pytest.raises(ValueError) as caught:
        capture(owner)
    assert unavailable(caught.value)


def test_selected_row_without_its_original_chain_is_unavailable(env):
    runtime, owner = env
    append_raw(runtime, hostile_payload(key="NOCHAIN", req="e" * 40))
    with pytest.raises(ValueError) as caught:
        capture(owner)
    assert unavailable(caught.value)


def test_capture_and_check_write_no_events_or_jobs(env):
    runtime, owner = env
    publish(owner)
    before = runtime.store.list_events()
    candidates = capture(owner)
    assert candidates.document() and candidates.check(SCOPE) is True
    assert runtime.store.list_events() == before
    assert runtime.jobs.list_jobs() == []


def test_check_rejects_late_new_matching_selector(env):
    runtime, owner = env
    publish(owner)
    candidates = capture(owner)
    publish(owner, key="LATE", req="%040x" % 2)
    with pytest.raises(ValueError) as caught:
        candidates.check(SCOPE)
    assert unavailable(caught.value)


def test_check_ignores_unmatched_activity(env):
    runtime, owner = env
    publish(owner)
    candidates = capture(owner)
    publish_as(owner, "9" * 64, key="FOREIGN")
    prepare(owner)
    claim(owner)
    observe(owner)
    append_raw(runtime, hostile_payload(phase="ADOPTION"))
    assert candidates.check(SCOPE) is True


def test_check_rejects_foreign_principal(env):
    runtime, owner = env
    publish(owner)
    candidates = capture(owner)
    with pytest.raises(ValueError) as caught:
        candidates.check("9" * 64)
    assert unavailable(caught.value)


def test_check_rejects_replaced_store(env, tmp_path):
    runtime, owner = env
    publish(owner)
    candidates = capture(owner)
    owner.store = Runtime.at(tmp_path / "other").store
    with pytest.raises(ValueError) as caught:
        candidates.check(SCOPE)
    assert unavailable(caught.value)


def test_check_rejects_replaced_source_method(env):
    runtime, owner = env
    publish(owner)
    candidates = capture(owner)
    owner._events = lambda identity, connection=None: []
    with pytest.raises(ValueError) as caught:
        candidates.check(SCOPE)
    assert unavailable(caught.value)


def test_check_rejects_withdrawn_guard(env):
    runtime, owner = env
    publish(owner)
    state = {"open": True}
    candidates = capture(owner, guard=lambda: state["open"])
    state["open"] = False
    with pytest.raises(ValueError) as caught:
        candidates.check(SCOPE)
    assert unavailable(caught.value)


def test_document_is_deeply_detached(env):
    runtime, owner = env
    selected, receipt = publish(owner)
    candidates = capture(owner)
    document = candidates.document()
    document["lookups"][0]["work_ref"] = "WS:TAMPER"
    document["has_more"] = True
    assert candidates.document() == {"schema": DOCUMENT_SCHEMA, "lookups": [selected],
                                     "has_more": False,
                                     "high_water": receipt["event_id"]}
    assert candidates.check(SCOPE) is True


def test_candidates_are_not_caller_mintable(env):
    _, owner = env
    with pytest.raises(TypeError):
        CreatedProjectCandidates()
    # A fabricated environment constructs but holds no authority: the private
    # seal gates every method, so nothing can be exercised or claimed.
    forged = CreatedProjectCandidates(_seal=object(), _owner=owner, _store=owner.store,
                                      _principal_scope=SCOPE, _guard=lambda: True,
                                      _events=owner._events, _snapshot=None)
    with pytest.raises(ValueError) as caught:
        forged.document()
    assert unavailable(caught.value)
    with pytest.raises(ValueError) as caught:
        forged.check(SCOPE)
    assert unavailable(caught.value)


def test_capture_fails_closed_on_wrong_owner_scope_or_guard(env):
    runtime, owner = env
    for events in (runtime.store, object(), None):
        with pytest.raises(ValueError) as caught:
            capture_created_project_candidates(events, SCOPE, guard=lambda: True)
        assert unavailable(caught.value)
    for scope in ("short", "g" * 64, "G" * 64, None):
        with pytest.raises(ValueError) as caught:
            capture(owner, scope=scope)
        assert unavailable(caught.value)
    with pytest.raises(ValueError) as caught:
        capture_created_project_candidates(owner, SCOPE, guard=None)
    assert unavailable(caught.value)


def test_capture_requires_the_trusted_read_seam(env):
    runtime, owner = env
    publish(owner)
    retained = runtime.store.list_events()
    with pytest.raises(ValueError) as caught:
        capture(owner, guard=lambda: False)
    assert unavailable(caught.value)
    calls = []

    def failing():
        calls.append(True)
        return len(calls) < 2

    with pytest.raises(ValueError) as caught:
        capture(owner, guard=failing)
    assert unavailable(caught.value)
    assert runtime.store.list_events() == retained  # no read mutated anything


def test_candidates_expose_no_mutator_and_are_frozen(env):
    runtime, owner = env
    publish(owner)
    candidates = capture(owner)
    assert {name for name in dir(candidates) if not name.startswith("_")} == {
        "check", "document"}
    with pytest.raises(dataclasses.FrozenInstanceError):
        candidates._snapshot = None
    assert runtime.jobs.list_jobs() == []
